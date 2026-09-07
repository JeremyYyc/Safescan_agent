#!/usr/bin/env python3
"""只读静态校验 v2 用例；不调用 Dify、不对回答语义作自动评分。"""
import hashlib, json, re
from collections import Counter
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]

def validate(base=BASE, root=ROOT):
    issues=[]
    cases=[json.loads(s) for s in (base/'manifest.v2.jsonl').read_text().splitlines() if s.strip()]
    profiles={p.stem:json.loads(p.read_text()) for p in (base/'profiles').glob('*.json')}
    docs={p.name.split('_',1)[0]:p for p in (root/'dify/Internal_kb').glob('*/*.md')}
    old_ids=set()
    for p in (root/'dify/Internal_kb_testcases').glob('0*/*.testcases.md'):
        old_ids.update(re.findall(r'TC-SC-[A-Z]+-\d{3}-\d{2}',p.read_text()))
    required={'spec_version','case_id','scenario_id','title','origin_case_ids','test_goal','question_type','difficulty',
              'question','corpus_profile','user_context','required_targets','preferred_sources','claims',
              'forbidden_claims','expected_behavior','insufficient_evidence_behavior','pass_criteria'}
    goals={'document_lookup','business_qa','cross_document_qa','insufficient_evidence','access_boundary'}
    ids=[c['case_id'] for c in cases]
    if len(ids)!=len(set(ids)): issues.append('duplicate case_id')
    for name,p in profiles.items():
        entries=p['documents']
        if len(entries)!=len({d['doc_id'] for d in entries}):issues.append(f'{name}: duplicate document')
        for d in entries:
            path=root/d['path']
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=d['sha256']:
                issues.append(f'{name}: snapshot mismatch {d["doc_id"]}')
        digest=hashlib.sha256(''.join(d['doc_id']+d['sha256'] for d in sorted(entries,key=lambda d:d['doc_id'])).encode()).hexdigest()
        if p['local_snapshot_sha256']!=digest or p['snapshot_id']!=f'{name}-{digest[:16]}':issues.append(f'{name}: snapshot id mismatch')
        if name=='emp_only' and {d['doc_id'] for d in entries}!={f'SC-EMP-{i:03d}' for i in range(1,10)}:issues.append('emp_only scope incorrect')
        if name=='internal_full' and {d['doc_id'] for d in entries}!=set(docs):issues.append('internal_full scope incorrect')
    def evidence(e,cid,available):
        doc=e.get('doc_id')
        if doc not in docs:issues.append(f'{cid}: missing source {doc}');return
        if doc not in available:issues.append(f'{cid}: source outside profile {doc}')
        text=docs[doc].read_text()
        excerpt=e.get('excerpt','')
        if not excerpt or excerpt not in text:issues.append(f'{cid}: excerpt mismatch {doc} {e.get("clause")}')
        lines=text.splitlines();line=e.get('source_line',0)
        if not (1<=line<=len(lines)) or not excerpt.startswith(lines[line-1]):issues.append(f'{cid}: source line mismatch')
        if not re.match(r'^'+re.escape(e.get('clause',''))+r'(?=[.\s])',excerpt.lstrip('# *').replace('**','')):
            issues.append(f'{cid}: clause mismatch {doc}')
    for c in cases:
        cid=c['case_id']
        if required-set(c):issues.append(f'{cid}: missing {required-set(c)}')
        if c['spec_version']!='2.0' or c['test_goal'] not in goals:issues.append(f'{cid}: version/goal')
        if c['corpus_profile'] not in profiles:issues.append(f'{cid}: unknown profile');continue
        available={d['doc_id'] for d in profiles[c['corpus_profile']]['documents']}
        if not set(c['origin_case_ids'])<=old_ids:issues.append(f'{cid}: bad legacy link')
        if not set(c['preferred_sources'])<=available:issues.append(f'{cid}: preferred source outside profile')
        clids=[x['claim_id'] for x in c['claims']]
        if len(clids)!=len(set(clids)):issues.append(f'{cid}: duplicate claim id')
        for cl in c['claims']:
            req=cl['requirement'];opts=cl['evidence_options']
            if req not in {'required','optional','gap_expected'}:issues.append(f'{cid}: bad requirement')
            if req in {'required','optional'} and not opts:issues.append(f'{cid}: unsupported claim')
            if req=='gap_expected' and opts:issues.append(f'{cid}: gap with evidence')
            for opt in opts:
                if not opt.get('all_of'):issues.append(f'{cid}: empty AND group')
                for e in opt.get('all_of',[]):evidence(e,cid,available)
        for e in c['required_targets']: evidence(e,cid,available)
        if c['test_goal'] in {'document_lookup','cross_document_qa'} and not c['required_targets']:issues.append(f'{cid}: targets missing')
        if c['test_goal']=='business_qa' and c['required_targets']:issues.append(f'{cid}: natural QA hard target')
        if c['test_goal']=='insufficient_evidence' and not any(x['requirement']=='gap_expected' for x in c['claims']):issues.append(f'{cid}: gap missing')
        if c['test_goal']=='access_boundary':
            if not c.get('authorization_assertions'):issues.append(f'{cid}: auth assertions missing')
            if c['user_context']['allowed_kbs'] or c['claims']:issues.append(f'{cid}: denial fixture invalid')
            if c.get('positive_control_case_id') not in ids:issues.append(f'{cid}: missing positive control')
        elif not c['claims']:issues.append(f'{cid}: empty claims')
        files=list((base/'scenarios').rglob(c['scenario_id']+'.testcases.md'))
        if len(files)!=1 or f'## {cid} ' not in files[0].read_text():issues.append(f'{cid}: missing readable case')
    print(f'cases: {len(cases)}; profiles: {len(profiles)}; goals: {dict(Counter(c["test_goal"] for c in cases))}')
    if issues:
        for issue in issues:print('FAIL:',issue)
    else:print('STATIC PASS: 字段、ID、范围、快照、证据摘录及可读文件一致；不代表语义或 Dify 在线验收通过。')
    return issues

if __name__=='__main__':
    raise SystemExit(1 if validate() else 0)
