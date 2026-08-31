"""LangGraph model -> tools -> model subgraph using the P4 tool registry."""
import asyncio
import json
from typing import TypedDict,Any
from langgraph.graph import StateGraph,START,END
from openai import AsyncOpenAI
import httpx
from app.settings import get_settings
from app.llm_registry import get_generation_params,get_model_name
from app.tools.registry import TOOLS,ToolContext,execute_tool

class ToolBudgetExceeded(RuntimeError): pass

class ModelState(TypedDict,total=False):
    messages:list[dict]
    pending:list[Any]
    content:str
    rounds:int
    calls:int
    seen:dict

def build_model_graph(client,tier,allowed_tools,context,trace=None):
    settings=get_settings()
    async def model(state):
        kwargs={'model':get_model_name(tier),'messages':state['messages'],**get_generation_params(tier)}
        if allowed_tools:
            kwargs.update(tools=[TOOLS[n].schema() for n in allowed_tools],tool_choice='auto')
        response=await client.chat.completions.create(**kwargs)
        message=response.choices[0].message
        requested=message.tool_calls or []
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
        graph=build_model_graph(client,tier,allowed_tools,context or ToolContext(),trace)
        state=await graph.ainvoke({'messages':list(messages),'calls':0,'rounds':0,'seen':{}},
                                 config={'recursion_limit':2*s.TOOL_MAX_ROUNDS+4})
        return state.get('content','')
    finally:
        if owned: await client.close()

def complete_sync(messages,tier='L2',**kwargs):
    try: asyncio.get_running_loop()
    except RuntimeError: return asyncio.run(complete(messages,tier,**kwargs))
    raise RuntimeError('Use await complete() from async code')
