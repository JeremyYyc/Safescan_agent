"""Report DAG: deterministic video policy, specialist barriers, bounded repair loop."""
import asyncio
import copy
import logging
from datetime import datetime,timezone
from pathlib import Path
import re
from langgraph.graph import StateGraph,START,END
from app import db,storage
from app.llm import complete
from app.settings import get_settings
from app.prompts import report_prompts
from app.tools.registry import ToolContext,execute_tool
from app.workflow.state import WorkflowState
from app.workflow.role_policy import _plan_agents,_format_user_attributes,_parse_json_blob
from app.agents.scene_agent import SceneUnderstandingAgent
from app.agents.report_writer_agent import ReportWriterAgent
from app.agents.title_agent import TitleAgent

class WorkflowCancelled(RuntimeError): pass

logger = logging.getLogger(__name__)

class ReportServices:
    """Replaceable I/O boundary; prompts and report normalization remain unchanged."""
    def __init__(self): self.yolo=None

    def _model(self):
        if self.yolo is None:
            from ultralytics import YOLO
            self.yolo=YOLO(str(Path(__file__).resolve().parents[1]/'yolov8m.pt'))
        return self.yolo

    def authorize(self,s):
        chat=db.get_chat(s['chat_id'])
        if not chat or chat['user_id']!=s['user_id']: raise PermissionError('Chat not found')
        storage.record(s['video_asset_id'],s['user_id'])
        if db.chat_has_report(s['chat_id']): raise ValueError('Report already exists')
        return {}

    async def _tool(self,name,args,s,refs,model=None):
        context=ToolContext(s['user_id'],s['chat_id'],frozenset(refs),model)
        result=await execute_tool(name,args,context,[name])
        if not result['ok']: raise RuntimeError(f"{name}: {result['error']['code']}")
        return result['result']

    async def extract(self,s):
        frames=await self._tool('extract_video_frames',{'asset_id':s['video_asset_id']},s,[s['video_asset_id']])
        return {'frames':frames,'extracted_frame_count':len(frames)}

    async def filter(self,s):
        result=await self._tool('filter_video_frames',{'asset_ids':s['frames']},s,s['frames'])
        return {'frames':result['asset_ids'],'filter_stats':result['stats']}

    async def select(self,s):
        model=await asyncio.to_thread(self._model)
        refs=await self._tool('select_representative_images',{'asset_ids':s['frames']},s,s['frames'],model)
        return {'representative_images':refs}

    async def detect(self,s):
        refs=s['representative_images']
        result=await self._tool('detect_objects',{'asset_ids':refs},s,refs,self._model())
        return {'representative_images':result['asset_ids'],'yolo_summaries':result['summaries']}

    def scene(self,s):
        return {'region_evidence':SceneUnderstandingAgent().analyze_scene(
            s['representative_images'],s['user_attributes'],yolo_summaries=s['yolo_summaries'])}

    def router(self,s):
        return {'plan':_plan_agents(s['region_evidence'],s['user_attributes'])['agents']}

    async def _json(self,system,user):
        for attempt in range(3):
            try:
                text=await complete([{'role':'system','content':system},{'role':'user','content':user}],'L2')
                parsed=_parse_json_blob(text)
                return parsed if parsed is not None else text
            except Exception:
                if attempt==2: raise
                await asyncio.sleep(.8*(attempt+1))

    async def hazard(self,s):
        import json
        system=report_prompts.hazard_system_message(_format_user_attributes(s['user_attributes']))
        system+='\nOutput a JSON array with one entry per region: [{"region_name": "string", "general_hazards": ["string"], "specific_hazards": ["string"]}].'
        user='Region evidence JSON:\n'+json.dumps(s['region_evidence'],ensure_ascii=False)+'\n\nUser attributes JSON:\n'+json.dumps(s['user_attributes'] or {},ensure_ascii=False)
        value=await self._json(system,user)
        return {'hazards':value if isinstance(value,list) else []}

    async def comfort(self,s):
        value=await self._json(report_prompts.comfort_system_message(),report_prompts.comfort_user_prompt(s['region_evidence'],s['user_attributes'])) if 'ComfortAgent' in s['plan'] else {}
        return {'comfort':value if isinstance(value,dict) else {}}

    async def compliance(self,s):
        value=await self._json(report_prompts.compliance_system_message(),report_prompts.compliance_user_prompt(s['hazards'])) if 'ComplianceAgent' in s['plan'] else {}
        return {'compliance':value if isinstance(value,dict) else {}}

    async def scoring(self,s):
        value=await self._json(report_prompts.scoring_system_message(),report_prompts.scoring_user_prompt(s['hazards'],s['comfort'],s['user_attributes'])) if 'ScoringAgent' in s['plan'] else {}
        return {'scoring':value if isinstance(value,dict) else {}}

    async def recommendations(self,s):
        value=await self._json(report_prompts.recommendation_system_message(),report_prompts.recommendation_user_prompt(s['hazards'],s['scoring'],s['comfort'],s['user_attributes'])) if 'RecommendationAgent' in s['plan'] else {}
        return {'recommendations':value if isinstance(value,dict) else {}}

    def _write(self,s,instructions=None):
        return ReportWriterAgent().write_report(s['region_evidence'],s['hazards'],s['user_attributes'],s['scoring'],s['comfort'],s['compliance'],s['recommendations'],repair_instructions=instructions)

    def write(self,s): return {'draft_report':self._write(s)}

    async def validate(self,s):
        result=await self._tool('validate_report',{'report':s['draft_report']},s,[])
        return {'validation':result,'iterations':s.get('iterations',0)+1}

    def repair(self,s):
        validation=s['validation']
        instructions='The report has validation errors. Please fix the following:\n'
        for error in validation.get('errors',[]): instructions+=f'- {error}\n'
        instructions+='\nRepair hints:\n'
        for hint in validation.get('repair_hints',[]): instructions+=f'- {hint}\n'
        return {'draft_report':self._write(s,instructions)}

    def evidence(self,s):
        report=copy.deepcopy(s['draft_report']);regions=report.get('regions',[]) or []
        evidence=s['region_evidence']
        # Retain the original evidence association policy, including index fallback.
        def key(value): return re.sub(r'[_\\s]+',' ',str(value)).strip().lower()
        mapping={key(e['region_label']):e.get('image_paths') or [] for e in evidence if e.get('region_label')}
        for index,region in enumerate(regions):
            if not isinstance(region,dict): continue
            names=region.get('regionName');names=names if isinstance(names,list) else [names] if isinstance(names,str) and names.strip() else []
            images=next((mapping[key(n)] for n in names if n and mapping.get(key(n))),[])
            if images: region['evidenceImages']=images
            elif index<len(evidence) and evidence[index].get('image_paths'):
                region['evidenceImages']=evidence[index]['image_paths']
        return {'draft_report':report}

    def title(self,s):
        chat=db.get_chat(s['chat_id'])
        if chat and (not chat.get('title') or chat['title']=='New Chat'):
            try: return {'title':TitleAgent().summarize_title(s['draft_report']).strip()[:255]}
            except Exception: return {}
        return {}

    def persist(self,s):
        from app.persistence.database import get_connection
        with get_connection():
            if s.get('title'): db.update_chat_title(s['chat_id'],s['title'])
            rid=db.store_report(s['draft_report'].get('regions',[]) or [],s['video_asset_id'],s['draft_report'],s['representative_images'],s['chat_id'],s['user_id'])
            if not rid: raise RuntimeError('Report persistence failed')
        return {'report_id':rid}

    def no_frames(self,s):
        count = s.get('extracted_frame_count', 0)
        if not count:
            reason = 'No frames could be extracted from the video.'
        elif not s.get('frames'):
            stats = s.get('filter_stats', {})
            reasons = ', '.join(f'{key}={stats.get(key, 0)}' for key in ('similar', 'blurry', 'dark', 'sensitive'))
            reason = f'No usable frames remain after filtering {count} extracted frames ({reasons}).'
        else:
            reason = f'No representative images selected from {len(s["frames"])} usable frames.'
        return {'warning':reason + ' No report was generated. Please try a clearer video without visible faces.'}
    def no_evidence(self,s): return {'warning':'No region evidence generated'}

def build_report_graph(services=None,trace=None,cancel=None):
    import inspect
    services=services or ReportServices()
    graph=StateGraph(WorkflowState)
    semaphore=asyncio.Semaphore(get_settings().AGENT_MAX_CONCURRENCY)
    def node(name,method=None):
        fn=getattr(services,method or name)
        async def invoke(state):
            if cancel and cancel.is_set(): raise WorkflowCancelled('Workflow cancelled')
            if trace: trace({'step':name+'_start','details':{}})
            async with semaphore:
                result=await fn(state) if inspect.iscoroutinefunction(fn) else await asyncio.to_thread(fn,state)
            if cancel and cancel.is_set(): raise WorkflowCancelled('Workflow cancelled')
            details = {'run_id':state.get('run_id')}
            if name == 'extract':
                details['output_count'] = len(result.get('frames', []))
            elif name == 'filter':
                details.update(input_count=len(state.get('frames', [])), output_count=len(result.get('frames', [])),
                               rejected=result.get('filter_stats', {}))
            elif name in ('select', 'detect'):
                details.update(input_count=len(state.get('frames' if name == 'select' else 'representative_images', [])),
                               output_count=len(result.get('representative_images', [])))
            if name in ('extract', 'filter', 'select', 'detect'):
                logger.info('Video stage %s: %s', name, details)
            if result.get('warning'):
                logger.warning('Workflow stopped run_id=%s: %s', state.get('run_id'), result['warning'])
            entry={'step':name+'_complete','timestamp':datetime.now(timezone.utc).isoformat(),'details':details}
            if trace: trace(entry)
            return {**result,'trace_log':[entry]}
        graph.add_node(name,invoke)
    for name in ('authorize','extract','filter','select','detect','scene','router','hazard','comfort','compliance','scoring','recommendations','write','validate','repair','evidence','title','persist','no_frames','no_evidence'): node(name)
    node('write_retry','write')
    graph.add_node('stage_two',lambda s:{})
    graph.add_edge(START,'authorize');graph.add_edge('authorize','extract');graph.add_edge('extract','filter')
    graph.add_conditional_edges('filter',lambda s:'select' if s.get('frames') else 'no_frames',{'select':'select','no_frames':'no_frames'})
    graph.add_edge('select','detect')
    graph.add_conditional_edges('detect',lambda s:'scene' if s.get('representative_images') else 'no_frames',{'scene':'scene','no_frames':'no_frames'})
    graph.add_conditional_edges('scene',lambda s:'router' if s.get('region_evidence') else 'no_evidence',{'router':'router','no_evidence':'no_evidence'})
    graph.add_edge('router','hazard');graph.add_edge('router','comfort')
    graph.add_edge(['hazard','comfort'],'stage_two')
    graph.add_edge('stage_two','compliance');graph.add_edge('stage_two','scoring')
    graph.add_edge(['compliance','scoring'],'recommendations');graph.add_edge('recommendations','write')
    graph.add_conditional_edges('write',lambda s:'validate' if isinstance(s.get('draft_report'),dict) and s['draft_report'].get('regions') else 'write_retry',{'validate':'validate','write_retry':'write_retry'})
    graph.add_edge('write_retry','validate')
    graph.add_conditional_edges('validate',lambda s:'evidence' if s['validation']['valid'] else 'repair',{'evidence':'evidence','repair':'repair'})
    # Preserve three attempts and the original unvalidated final repair behavior.
    graph.add_conditional_edges('repair',lambda s:'evidence' if s['iterations']>=3 else 'validate',{'evidence':'evidence','validate':'validate'})
    graph.add_edge('evidence','title');graph.add_edge('title','persist');graph.add_edge('persist',END)
    graph.add_edge('no_frames',END);graph.add_edge('no_evidence',END)
    return graph.compile()
