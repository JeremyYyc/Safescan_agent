"""LangGraph model -> tools -> model subgraph using the P4 tool registry."""
import asyncio
import json
import logging
import time
from typing import TypedDict,Any
from uuid import uuid4
from langgraph.graph import StateGraph,START,END
from openai import AsyncOpenAI, APIStatusError
import httpx
from app.settings import get_settings
from app.llm_registry import get_generation_params,get_model_name
from app.tools.registry import TOOLS,ToolContext,execute_tool
from app.report_errors import model_request_failure

logger = logging.getLogger(__name__)

class ToolBudgetExceeded(RuntimeError): pass

class ModelState(TypedDict,total=False):
    messages:list[dict]
    pending:list[Any]
    content:str
    rounds:int
    calls:int
    seen:dict

def _message_metrics(messages):
    """Return request-size diagnostics without retaining or logging content."""
    text_chars=0;image_count=0;image_payload_chars=0
    for message in messages:
        content=message.get('content') if isinstance(message,dict) else None
        if isinstance(content,str):
            text_chars+=len(content)
        elif isinstance(content,list):
            for item in content:
                if not isinstance(item,dict): continue
                if item.get('type')=='text' and isinstance(item.get('text'),str):
                    text_chars+=len(item['text'])
                elif item.get('type')=='image_url':
                    image_count+=1
                    image=item.get('image_url')
                    url=image.get('url') if isinstance(image,dict) else image
                    if isinstance(url,str): image_payload_chars+=len(url)
    encoded=json.dumps(messages,ensure_ascii=False,default=str).encode('utf-8')
    return {'message_count':len(messages),'text_chars':text_chars,'image_count':image_count,
            'image_payload_chars':image_payload_chars,'message_bytes':len(encoded)}

def _provider_error_code(error):
    body=getattr(error,'body',None)
    details=body.get('error',body) if isinstance(body,dict) else None
    return details.get('code') if isinstance(details,dict) else None

def build_model_graph(client,tier,allowed_tools,context,trace=None,call_id=None):
    settings=get_settings()
    call_id=call_id or uuid4().hex[:16]
    async def model(state):
        model_name=get_model_name(tier);round_number=state.get('rounds',0)
        kwargs={'model':model_name,'messages':state['messages'],**get_generation_params(tier)}
        if allowed_tools:
            kwargs.update(tools=[TOOLS[n].schema() for n in allowed_tools],tool_choice='auto')
        metrics=_message_metrics(state['messages']);started=time.monotonic()
        logger.info(
            'LLM request start call_id=%s chat_id=%s tier=%s model=%s round=%s '
            'message_count=%s text_chars=%s image_count=%s image_payload_chars=%s '
            'message_bytes=%s allowed_tools=%s',
            call_id,context.chat_id,tier,model_name,round_number,metrics['message_count'],
            metrics['text_chars'],metrics['image_count'],metrics['image_payload_chars'],
            metrics['message_bytes'],len(allowed_tools),
        )
        try:
            response=await client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.warning(
                'LLM request failed call_id=%s chat_id=%s tier=%s model=%s round=%s '
                'elapsed_ms=%s error_type=%s status=%s provider_code=%s message_bytes=%s '
                'text_chars=%s image_count=%s image_payload_chars=%s',
                call_id,context.chat_id,tier,model_name,round_number,
                round((time.monotonic()-started)*1000),type(exc).__name__,
                getattr(exc,'status_code',None),_provider_error_code(exc),metrics['message_bytes'],
                metrics['text_chars'],metrics['image_count'],metrics['image_payload_chars'],
            )
            raise
        message=response.choices[0].message
        requested=message.tool_calls or []
        usage=getattr(response,'usage',None)
        logger.info(
            'LLM request complete call_id=%s chat_id=%s tier=%s model=%s response_model=%s '
            'round=%s elapsed_ms=%s finish_reason=%s tool_calls=%s input_tokens=%s '
            'output_tokens=%s total_tokens=%s',
            call_id,context.chat_id,tier,model_name,getattr(response,'model',None),round_number,
            round((time.monotonic()-started)*1000),getattr(response.choices[0],'finish_reason',None),
            len(requested),getattr(usage,'prompt_tokens',None),
            getattr(usage,'completion_tokens',None),getattr(usage,'total_tokens',None),
        )
        if requested and (state.get('rounds',0)>=settings.TOOL_MAX_ROUNDS or state.get('calls',0)+len(requested)>settings.TOOL_MAX_CALLS):
            raise ToolBudgetExceeded('Model exceeded the tool-call budget')
        history=state['messages']
        if requested:
            history=history+[{'role':'assistant','content':message.content,'tool_calls':[
                {'id':c.id,'type':'function','function':{'name':c.function.name,'arguments':c.function.arguments}} for c in requested]}]
        return {'pending':requested,'content':message.content or '','messages':history}
    async def tools(state):
        messages=list(state['messages']);seen=dict(state.get('seen',{}))
        for call in state['pending']:
            identity=(call.function.name,call.function.arguments)
            if call.id in seen:
                previous,result=seen[call.id]
                if previous!=identity: raise ValueError('Conflicting repeated tool call ID')
            else:
                result=await execute_tool(call.function.name,call.function.arguments,context,allowed_tools)
                seen[call.id]=(identity,result)
            content=json.dumps(result,ensure_ascii=False,default=str)
            if len(content)>settings.TOOL_MAX_OUTPUT_CHARS:
                content=json.dumps({'ok':False,'error':{'code':'tool_output_too_large'}})
            messages.append({'role':'tool','tool_call_id':call.id,'content':content})
            if trace: trace('tool_call',{'name':call.function.name,'call_id':call.id,'ok':result['ok']})
        return {'messages':messages,'seen':seen,'calls':state.get('calls',0)+len(state['pending']),'rounds':state.get('rounds',0)+1}
    graph=StateGraph(ModelState)
    graph.add_node('model',model);graph.add_node('tools',tools)
    graph.add_edge(START,'model')
    graph.add_conditional_edges('model',lambda s:'tools' if s.get('pending') else END,{'tools':'tools',END:END})
    graph.add_edge('tools','model')
    return graph.compile()

async def complete(messages,tier='L2',*,allowed_tools=(),context=None,client=None,trace=None):
    s=get_settings();owned=client is None
    client=client or AsyncOpenAI(api_key=s.require_secret('DASHSCOPE_API_KEY'),base_url=s.QWEN_BASE_URL,
        timeout=httpx.Timeout(s.QWEN_READ_TIMEOUT_SECONDS,connect=s.QWEN_CONNECT_TIMEOUT_SECONDS),max_retries=2)
    try:
        graph=build_model_graph(client,tier,allowed_tools,context or ToolContext(),trace,
                                call_id=uuid4().hex[:16])
        state=await graph.ainvoke({'messages':list(messages),'calls':0,'rounds':0,'seen':{}},
                                 config={'recursion_limit':2*s.TOOL_MAX_ROUNDS+4})
        return state.get('content','')
    except APIStatusError as exc:
        raise model_request_failure(exc, tier) from None
    finally:
        if owned: await client.close()

def complete_sync(messages,tier='L2',**kwargs):
    try: asyncio.get_running_loop()
    except RuntimeError: return asyncio.run(complete(messages,tier,**kwargs))
    raise RuntimeError('Use await complete() from async code')
