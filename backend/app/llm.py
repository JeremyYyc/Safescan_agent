"""Qwen OpenAI-compatible calls with a bounded, real function-calling loop."""
import asyncio
import json
from openai import AsyncOpenAI
import httpx
from app.settings import get_settings
from app.llm_registry import get_generation_params,get_model_name
from app.tools.registry import TOOLS,ToolContext,execute_tool

class ToolBudgetExceeded(RuntimeError): pass

async def complete(messages, tier='L2', *, allowed_tools=(), context=None, client=None, trace=None):
    s=get_settings();owned=client is None
    client=client or AsyncOpenAI(api_key=s.require_secret('DASHSCOPE_API_KEY'),base_url=s.QWEN_BASE_URL,
        timeout=httpx.Timeout(s.QWEN_READ_TIMEOUT_SECONDS,connect=s.QWEN_CONNECT_TIMEOUT_SECONDS),max_retries=2)
    history=list(messages);calls=0;seen={}
    try:
        for round_index in range(s.TOOL_MAX_ROUNDS+1):
            kwargs={'model':get_model_name(tier),'messages':history,**get_generation_params(tier)}
            if allowed_tools:
                kwargs['tools']=[TOOLS[name].schema() for name in allowed_tools]
                kwargs['tool_choice']='auto'
            response=await client.chat.completions.create(**kwargs)
            message=response.choices[0].message
            requested=message.tool_calls or []
            if not requested: return message.content or ''
            if round_index==s.TOOL_MAX_ROUNDS or calls+len(requested)>s.TOOL_MAX_CALLS:
                raise ToolBudgetExceeded('Model exceeded the tool-call budget')
            history.append({'role':'assistant','content':message.content,'tool_calls':[
                {'id':c.id,'type':'function','function':{'name':c.function.name,'arguments':c.function.arguments}} for c in requested]})
            for call in requested:
                calls+=1
                identity=(call.function.name,call.function.arguments)
                if call.id in seen:
                    previous,result=seen[call.id]
                    if previous!=identity: raise ValueError('Conflicting repeated tool call ID')
                else:
                    result=await execute_tool(call.function.name,call.function.arguments,context or ToolContext(),allowed_tools)
                    seen[call.id]=(identity,result)
                content=json.dumps(result,ensure_ascii=False,default=str)
                if len(content)>s.TOOL_MAX_OUTPUT_CHARS:
                    content=json.dumps({'ok':False,'error':{'code':'tool_output_too_large'}})
                history.append({'role':'tool','tool_call_id':call.id,'content':content})
                if trace: trace('tool_call',{'name':call.function.name,'call_id':call.id,'ok':result['ok']})
        raise ToolBudgetExceeded('Tool loop exhausted')
    finally:
        if owned: await client.close()

def complete_sync(messages,tier='L2',**kwargs):
    try: asyncio.get_running_loop()
    except RuntimeError: return asyncio.run(complete(messages,tier,**kwargs))
    raise RuntimeError('Use await complete() from async code')
