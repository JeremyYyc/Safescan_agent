"""Export existing knowledge text and reproducible length statistics offline."""
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup
from collect import digest, write_json

BASE = Path('data/collection-pilot')
OUT = Path('outputs/knowledge-documents-20261009')
LABELS = {
    'nsw-rental-standards': '租赁住房最低标准',
    'nsw-urgent-repairs': '紧急维修',
    'nsw-repair-process': '如何推进租赁住房维修',
    'nsw-landlord-maintenance': '房东维修与维护责任',
    104072: '修补石膏板墙洞', 39117: '维修漏水水龙头',
    182837: '用湿式吸尘器疏通水槽', 44146: '更换马桶排水阀片',
    140776: '紧固松动的马桶座圈', 105443: '拆卸洗衣机以检修排水泵',
    67174: '更换门锁锁芯',
}


def plain(text):
    text = BeautifulSoup(text or '', 'html.parser').get_text(' ', strip=True)
    text = re.sub(r'\[video\|[^\]]*\]', '', text)
    text = re.sub(r'\[(?:product|guide|link)\|[^\]]*\|([^\]]+)\]', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'texts').mkdir(exist_ok=True)
    rows = []
    def add(key, kind, title, body, source, raw, steps=0):
        row = {'id':str(key), 'group':kind, 'title_zh':LABELS[key], 'title':title,
               'english_words':len(re.findall(r"\b[A-Za-z]+(?:['’-][A-Za-z]+)*\b", body)),
               'characters_with_whitespace':len(body),
               'characters_without_whitespace':len(re.sub(r'\s','',body)),
               'steps':steps,'source_url':source, 'text_path':'texts/'+str(key)+'.txt',
               'source_metadata':raw, 'text_sha256':digest(body.encode('utf-8'))}
        (OUT/row['text_path']).write_text(body,encoding='utf-8')
        rows.append(row)
    source = BASE/'20260928T091936387926Z/documents.jsonl'
    for line in source.read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        add(r['source_id'],'official',r['title'],r['content_text'].strip(),r['source_url'],r)
    for r in json.loads((BASE/'repair-pilot-20261005/records.json').read_text(encoding='utf-8')):
        parts = [plain(r.get('introduction'))]
        for step in r['steps']:
            if step.get('title'):
                parts.append(plain(step['title']))
            parts += [plain(line.get('text_rendered') or line.get('text_raw')) for line in step.get('lines',[])]
        add(r['guide_id'],'ifixit',r['title'],'\n\n'.join(s for s in parts if s),r['source_url'],r,len(r['steps']))
    write_json(OUT/'documents.json',rows)
    totals = {}
    for group in ['official','ifixit','all']:
        rr = [r for r in rows if group=='all' or r['group']==group]
        totals[group] = {'documents':len(rr), **{k:sum(r[k] for r in rr) for k in ['english_words','characters_with_whitespace','characters_without_whitespace','steps']}}
    write_json(OUT/'summary.json',totals)
    lines = ['# 住房与维修知识文档长度盘点', '', '统计日期：2026-10-09。仅使用已有采集快照，未重新抓取或核实当前规则。', '',
             '## 统计口径', '',
             '- 原文均为英文，“字数”以英文单词数为主，同时提供包含空白的字符数。单词只统计英文字母组成的词，保留词内连字符和撇号，不计纯数字。',
             '- 官方文档直接统计已提取正文 content_text，包含标题、章节标题及帮助/联系方式，不重复统计 sections。',
             '- iFixit 统计简介与步骤文字，去掉 HTML、视频标记、裸链接；不计重复摘要、工具清单、作者及图片地址。',
             '- 多次抓取的官方快照不重复计数，采用最后一批保存的 4 篇。', '',
             '## 逐篇统计', '', '| 文档 | 英文单词 | 字符（含空白） | 步骤 |', '| --- | ---: | ---: | ---: |']
    for r in rows:
        lines.append(f'| [{r["title_zh"]}]({r["text_path"]}) | {r["english_words"]:,} | {r["characters_with_whitespace"]:,} | {r["steps"] or "不适用"} |')
    lines += ['', '## 汇总', '']
    for group,label in [('official','官方住房与维修流程文档'),('ifixit','iFixit 维修教程'),('all','合计')]:
        t=totals[group]
        lines.append(f'- {label}：{t["documents"]} 篇，{t["english_words"]:,} 个英文单词，{t["characters_with_whitespace"]:,} 个字符。')
    lines += ['', '## 交付状态', '',
              '本目录是知识文档的初步交付整理：texts/ 为逐篇纯文本，documents.json 保留原始元数据、来源和许可，summary.json 为统计。现有官方文档中 3 篇直接涉及维修，另 1 篇为住房最低标准。', '',
              'iFixit 共 62 个步骤，图片未下载成功；教程不是实际工单。原记录中的许可及待确认使用条件保持不变。此统计是知识文档交付的准备阶段，完整打包使用 package_knowledge_docs.py。']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write_json(OUT/'manifest.json',{p.relative_to(OUT).as_posix():digest(p.read_bytes()) for p in OUT.rglob('*') if p.is_file() and p.name!='manifest.json'})
    print(json.dumps({'documents':[{k:r[k] for k in ['id','english_words','characters_with_whitespace','steps']} for r in rows],'totals':totals},indent=2))


if __name__ == '__main__':
    main()
