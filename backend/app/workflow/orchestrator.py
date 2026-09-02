"""Application facade for the complete LangGraph report workflow."""
import asyncio
from uuid import uuid4
from app import storage
from app.tools.registry import ToolContext,tool_context
from app.workflow.graph import build_report_graph
from app.settings import get_settings

class WorkflowOrchestrator:
    def __init__(self,services=None):
        self.services=services

    def execute_workflow(self,video_asset_id,user_attributes,*,user_id,chat_id,trace_cb=None,cancel=None,
                         run_id=None,checkpoint_thread_id=None,resume=False):
        run_id=run_id or uuid4().hex
        initial={'run_id':run_id,'video_asset_id':video_asset_id,'user_attributes':user_attributes or {},
                 'user_id':user_id,'chat_id':chat_id,'iterations':0,'trace_log':[]}
        with storage.media_scope(user_id),tool_context(ToolContext(user_id,chat_id)):
            if not checkpoint_thread_id:
                graph=build_report_graph(self.services,trace_cb,cancel)
                return asyncio.run(graph.ainvoke(initial,config={'recursion_limit':64}))
            from langgraph.checkpoint.postgres import PostgresSaver
            database_url=get_settings().require_secret('DATABASE_URL').replace('postgresql+psycopg://','postgresql://',1)
            with PostgresSaver.from_conn_string(database_url) as saver:
                saver.setup()
                graph=build_report_graph(self.services,trace_cb,cancel,checkpointer=saver)
                return asyncio.run(graph.ainvoke(None if resume else initial,config={'recursion_limit':64,'configurable':{'thread_id':checkpoint_thread_id}}))

def result_payload(state):
    warning=state.get('warning')
    return {
        'run_id':state['run_id'],
        'regionInfo':[{'warning':[warning]}] if warning else state.get('draft_report',{}).get('regions',[]),
        'report':state.get('draft_report',{}),
        'representativeImages':[] if warning else state.get('representative_images',[]),
        'video_asset_id':state['video_asset_id'],
        'workflowLog':state.get('trace_log',[]),
        'validation':{'success':state.get('validation',{}).get('valid',False),'iterations':state.get('iterations',0)},
        'report_id':state.get('report_id'),
        'warning':warning,
        'frameStats':{'extracted':state.get('extracted_frame_count',0),
                      'retained':len(state.get('frames',[])),
                      'representative':len(state.get('representative_images',[])),
                      'rejected':state.get('filter_stats',{})},
    }
    
