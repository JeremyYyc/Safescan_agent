"""On-demand PDF subgraph: load -> normalize -> render -> store -> reference."""
from io import BytesIO
from typing import TypedDict,Any
from fastapi import HTTPException
from langgraph.graph import StateGraph,START,END
from app import db,storage
from app.pdf.report_pdf import render_report_pdf
from app.persistence.database import get_connection

class PdfState(TypedDict,total=False):
    chat_ref:str
    user_id:int
    chat_id:int
    chat:dict
    report:dict
    pdf_bytes:bytes
    asset_id:str
    report_id:int

def load_report(s):
    cid=db.resolve_chat_internal_id(s['chat_ref'])
    chat=db.get_chat(cid) if cid else None
    if not chat or chat['user_id']!=s['user_id']: raise HTTPException(404,'Chat not found')
    report=(db.get_latest_report_assets(cid) or {}).get('report_json')
    if not isinstance(report,dict) or not report: raise HTTPException(404,'Report data not found')
    return {'chat_id':cid,'chat':chat,'report':report}

def normalize(s):
    from app.api.report import _normalize_report_for_pdf
    # Analysis reports have already passed the report validation workflow. PDF
    # export must be deterministic and must not make another paid model request.
    return {'report':_normalize_report_for_pdf(s['report'])}

def render(s):
    buffer=BytesIO();render_report_pdf(s['report'],buffer)
    return {'pdf_bytes':buffer.getvalue()}

def store(s):
    # Temporary bytes only exist between render and store, never in disk files.
    return {'asset_id':storage.put(s['pdf_bytes'],'application/pdf',user_id=s['user_id'],category='reports'),'pdf_bytes':b''}

def reference(s):
    from app.api.report import _extract_report_preview_text
    title=(s['chat'].get('title') or '').strip() or s['report'].get('title') or f"Report {s['chat_id']}"
    with get_connection():
        rid=db.store_pdf_report(user_id=s['user_id'],source_path=s['asset_id'],title=str(title),
            extracted_text=_extract_report_preview_text(s['report']),origin_chat_id=s['chat_id'],pdf_kind='exported',derived_from_report_id=db.get_latest_report_id(s['chat_id']))
        if not rid: raise RuntimeError('PDF metadata persistence failed')
        db.add_chat_report_ref(s['chat_id'],rid,s['chat_id'],'active')
    return {'report_id':rid}

def build_pdf_graph():
    graph=StateGraph(PdfState)
    stages=[('load',load_report),('normalize',normalize),('render',render),('store',store),('reference',reference)]
    for name,fn in stages: graph.add_node(name,fn)
    graph.add_edge(START,'load')
    for (left,_),(right,_) in zip(stages,stages[1:]): graph.add_edge(left,right)
    graph.add_edge('reference',END)
    return graph.compile()

def export_pdf(chat_ref,user_id):
    with storage.media_scope(user_id):
        state=build_pdf_graph().invoke({'chat_ref':chat_ref,'user_id':user_id})
        return {'report_id':state['report_id'],'pdf_url':state['asset_id'],
                'download_url':f"/api/reports/pdf/{state['report_id']}/download"}
