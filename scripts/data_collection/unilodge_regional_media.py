"""Explicit page-linked media shortlist, bounded by region; offline dataset export."""
import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path
from urllib.parse import urlsplit

from collect import ROOT, digest, write_json
from flagstaff_collect import media_candidates
from source_fit_probe import run

SOURCE=ROOT/'data/collection-pilot/unilodge-regions-20260929'
DETAILS=ROOT/'data/collection-pilot/unilodge-regions-details-20260929'
# Associations are explicit research candidates, not inferred individual-unit evidence.
SELECTIONS={
 'melbourne-central': [
   ('Standard Studio','studio-standard-floorplan',None),
   ('Studio Queen','studio-queen-floorplan',None),
   ('2 Bedroom Apartment','2-bedroom-apartment-floorplan',None),
   ('6 Bedroom Apartment (Ensuite)','6-bedroom-apartment-floorplan',None)],
 'south-bank': [
   ('Standard','6bed-floorplan-web',None),
   ('Ensuite','2bed-floorplan-web',None),
   ('Multishare','2bed-multishare-floorplan-web',None)],
 'metro-adelaide': [
   ('Standard','1-bedroom-standard-unilodge','One Bedroom Standard'),
   ('Queen','1-bedroom-queen-unilodge',None),
   ('Deluxe Balcony','1-bedroom-deluxe-balcony-unilodge','One Bedroom Deluxe Balcony'),
   ('2 Bedroom Standard Share','2-bedroom-standard-unilodge','Two Bedroom Standard')]
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def prepare():
    rooms=read(DETAILS/'room_types.json')
    plans=read(DETAILS/'floorplan_candidates.json')
    properties=read(SOURCE/'outcomes.json')
    result=[]
    for prop, choices in SELECTIONS.items():
        meta=next(p for p in properties if p['id']==prop)
        gallery=media_candidates((SOURCE/meta['local_path']).read_bytes(),meta)
        for name, plan_token, label in choices:
            room=next(r for r in rooms if r['property_id']==prop and r['name']==name)
            matches=[p for p in plans if p['property_id']==prop and plan_token in urlsplit(p['url']).path]
            if len(matches)!=1:
                raise ValueError('ambiguous_or_missing_plan:'+prop+':'+name)
            if label:
                photos=[p for p in gallery if p['label'].strip()==label and '_wide.' in p['url']][:2]
            else:
                photos=[p for p in room['photos'] if not any(t in p['url'].lower() for t in ('floorplan','floor-plan','full-size'))][:2]
            result.append({'room_id':room['id'],'property_id':prop,'name':name,'city':room['city'],
                           'association_status':'page_labels_and_room_section_pending_visual_review',
                           'assets':[{'url':matches[0]['url'],'role':'layout','source_label':matches[0]['label']}]
                            +[{'url':p['url'],'role':'interior_candidate','source_label':p.get('label')} for p in photos]})
    return result


def collect(output):
    output.mkdir(parents=True,exist_ok=False)
    selections=prepare()
    write_json(output/'selections.json',selections)
    for prop in SELECTIONS:
        urls={a['url'] for r in selections if r['property_id']==prop for a in r['assets']}
        targets=[{'id':'asset-'+digest(url.encode())[:16],'url':url,'kind':'image'} for url in sorted(urls)]
        if len(targets)>15:
            raise ValueError('regional_media_limit')
        run(output/prop,targets)
        outcomes=read(output/prop/'outcomes.json')
        if any(any(t in o.get('error','') for t in ('forbidden','rate_limited','host_stopped')) for o in outcomes):
            raise ValueError('access_stop_no_further_regions')
    export(output)


def export(output):
    selections=read(output/'selections.json')
    rooms=read(DETAILS/'room_types.json')
    lookup={}
    outcome_paths=sorted(output.glob('*/outcomes.json'))
    for path in outcome_paths:
        for item in read(path):
            if item['state']=='success':
                local=path.parent/item['local_path']
                if digest(local.read_bytes())!=item['sha256']:
                    raise ValueError('hash_mismatch')
                lookup[item['url']]={**item,'local_path':local.relative_to(output).as_posix()}
    review_path=output/'visual_reviews.json'
    reviews=read(review_path) if review_path.exists() else {}
    hash_rooms={}
    for selection in selections:
        for asset in selection['assets']:
            if asset['url'] in lookup:
                hash_rooms.setdefault(lookup[asset['url']]['sha256'],set()).add(selection['room_id'])
    for room in rooms:
        selection=next((r for r in selections if r['room_id']==room['id']),None)
        room['downloaded_assets']=[]
        if selection:
            for a in selection['assets']:
                if a['url'] in lookup:
                    item={**lookup[a['url']],**a}
                    item['review']=reviews.get(item['sha256'],{'status':'pending'})
                    item['shared_with_room_type_ids']=sorted(hash_rooms[item['sha256']]-{room['id']})
                    room['downloaded_assets'].append(item)
        room['media_candidate_complete']=any(a['role']=='layout' for a in room['downloaded_assets']) and any(a['role']=='interior_candidate' for a in room['downloaded_assets'])
        room['media_review_complete']=media_complete(room['downloaded_assets'])
        room['media_review_with_people_complete']=media_complete(room['downloaded_assets'], include_people=True)
        room['media_missing']=[]
        if not any(a['review'].get('category')=='layout_complete' for a in room['downloaded_assets']):
            room['media_missing'].append('complete_layout')
        if not any(a['review'].get('category')=='interior' for a in room['downloaded_assets']):
            room['media_missing'].append('clear_no_person_interior')
        room['association_status']='source_room_type_sample_not_actual_unit'
        room['core_interior_count']=len({a['sha256'] for a in room['downloaded_assets'] if a['review'].get('category')=='interior' and a['review'].get('status')=='assistant_reviewed'})
        room['quality_notes']=[]
        if any(a['shared_with_room_type_ids'] for a in room['downloaded_assets']):
            room['quality_notes'].append('Source reuses media across room types; not unique unit evidence.')
        if room['property_id']=='metro-adelaide' and room['name']=='Deluxe Balcony':
            room['quality_notes'].append('Area conflict: saved room description says 32 SQM; plan label says Apartment 40m2. Do not reconcile without evidence.')
        room['human_approved']=False
        room['production_ready']=False
    write_json(output/'dataset.json',rooms)
    write_json(output/'complete_room_types.json',[r for r in rooms if r['media_review_complete']])
    write_json(output/'gaps.json',[{'id':r['id'],'city':r['city'],'name':r['name'],'missing':r['media_missing'],'notes':r['quality_notes']} for r in rooms if r['media_missing'] or r['quality_notes']])
    quotes=[{'room_type_id':r['id'],'city':r['city'],'source_url':r['source_url'],'retrieved_at':r['retrieved_at'],**q} for r in rooms for q in r['offers']]
    write_json(output/'offers.json',quotes)
    stats=[]
    for city in sorted({r['city'] for r in rooms}):
        subset=[r for r in rooms if r['city']==city]
        stats.append({'city':city,'room_types':len(subset),'offers':sum(len(r['offers']) for r in subset),
                      'media_candidates':sum(r['media_candidate_complete'] for r in subset),
                      'media_complete_assistant_review':sum(r['media_review_complete'] for r in subset),
                      'media_complete_including_people':sum(r['media_review_with_people_complete'] for r in subset),
                      'complete_with_two_core_interiors':sum(r['media_review_complete'] and r['core_interior_count']>=2 for r in subset),
                      'floor_range_records':sum(bool(r['floor_range_source_text']) for r in subset),'unit_numbers':0})
    summary={'regions':stats,'downloaded_files':len(lookup),'unique_hashes':len({a['sha256'] for a in lookup.values()}),
             'desired_scale':100,'not_a_quota':True,'rights_status':'unknown','publication_status':'not_released'}
    write_json(output/'summary.json',summary)
    esc=lambda v:escape(str(v),quote=True)
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UniLodge 区域数据集</title><style>
*{box-sizing:border-box}body{font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif;margin:0;color:#233034;background:#fff;letter-spacing:0}main{max-width:1200px;margin:auto;padding:26px 22px}h1{font-size:28px}h2{font-size:22px}h3{font-size:18px}section{padding:24px 0;border-top:1px solid #cdd7db}a{color:#086c78;overflow-wrap:anywhere}p{overflow-wrap:anywhere}.gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}figure{margin:0}img{width:100%;aspect-ratio:16/10;object-fit:contain;background:#f4f6f7}figcaption{font-size:13px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;min-width:720px}th,td{text-align:left;border-bottom:1px solid #d3dfe1;padding:9px}select{font:inherit;padding:6px}.notice{border-left:4px solid #ac741c;background:#fff6df;padding:12px}details{margin:12px 0}summary{cursor:pointer}.muted{color:#586870}@media(max-width:650px){.gallery{grid-template-columns:1fr}main{padding:18px 14px}}
</style><main><h1>UniLodge 区域房型数据集</h1><p class="notice">完整房型优先，目标约100条但不凑数。报价是房型子记录，不算额外房源。图片为样板间/示意内容，助手复核不等于独立人工签认或复用许可；没有具体房号。</p>'''
    html+='<p><a href="dataset.json">全部房型 JSON</a> · <a href="complete_room_types.json">完整媒体房型 JSON</a> · <a href="offers.json">报价明细</a> · <a href="summary.json">区域统计</a></p>'
    html+='<div class="scroll"><table><tr><th>城市</th><th>房型</th><th>报价</th><th>媒体组合已下载</th><th>助手复核完整</th><th>公开楼层范围</th><th>房号</th></tr>'
    for s in stats:
        html+='<tr>'+''.join('<td>'+esc(s[k])+'</td>' for k in ('city','room_types','offers','media_candidates','media_complete_assistant_review','floor_range_records','unit_numbers'))+'</tr>'
    html+='</table></div><p><label for="region">区域：</label><select id="region"><option value="all">全部城市</option>'+''.join('<option>'+esc(s['city'])+'</option>' for s in stats)+'</select></p>'
    for r in rooms:
        html+=f'<section data-city="{esc(r["city"])}"><h2>{esc(r["city"])} / {esc(r["property_id"])} / {esc(r["name"])}</h2><p>{"媒体复核完整" if r["media_review_complete"] else "媒体待补或待复核"} · {len(r["offers"])} 条报价 · 面积 {esc(r["area_sqm"])} / {esc(r["area_scope"])} · <a href="{esc(r["source_url"])}" target="_blank" rel="noopener noreferrer">官网房型</a></p>'
        html+='<p>楼层范围：'+esc('；'.join(r['floor_range_source_text']) or '未公开/未提取到')+'；具体楼层与房号：未知。</p>'
        for note in r['quality_notes']:
            html+='<p class="notice">'+esc(note)+'</p>'
        html+='<div class="gallery">'
        for a in r['downloaded_assets']:
            html+=f'<figure><a href="{esc(a["local_path"])}" target="_blank"><img src="{esc(a["local_path"])}" loading="lazy" alt="{esc(r["name"]+" "+a["role"])}"></a><figcaption>{esc(a["role"])} · {a["width"]}×{a["height"]} · {esc(a["review"].get("note","待视觉复核"))}</figcaption></figure>'
        html+='</div><details><summary>租期报价与房型原文</summary><div class="scroll"><table><tr><th>金额 $</th><th>周期</th><th>币种/计价对象</th><th>方案</th></tr>'
        for q in r['offers']:
            html+='<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (q['amount'],q['period'],str(q['currency'])+' / '+str(q['basis']),q['lease_label']))+'</tr>'
        html+='</table></div><p>'+esc(r['description'])+'</p></details></section>'
    html+='''<script>document.getElementById('region').addEventListener('change',e=>{document.querySelectorAll('section[data-city]').forEach(s=>s.hidden=e.target.value!=='all'&&s.dataset.city!==e.target.value)});</script></main></html>'''
    (output/'index.html').write_text(html,encoding='utf-8')
    write_json(output/'export_manifest.json',{'script_sha256':digest(Path(__file__).read_bytes()),
        'inputs':{str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in [DETAILS/'room_types.json',output/'selections.json']+outcome_paths+([review_path] if review_path.exists() else [])},
        'outputs':{n:digest((output/n).read_bytes()) for n in ('dataset.json','complete_room_types.json','offers.json','summary.json','gaps.json','index.html')}})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def media_complete(assets, include_people=False):
    reviewed=[a for a in assets if a.get('review',{}).get('status')=='assistant_reviewed']
    interiors={'interior', 'interior_with_people'} if include_people else {'interior'}
    return (any(a['role']=='layout' and a['review'].get('category')=='layout_complete' for a in reviewed)
            and any(a['role']=='interior_candidate' and a['review'].get('category') in interiors for a in reviewed))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--export-only',action='store_true')
    args=parser.parse_args()
    (export if args.export_only else collect)(args.output.resolve())
