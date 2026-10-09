"""Prepare and validate a portable knowledge-document delivery, without network I/O."""
import argparse
import csv
from html import escape
import json
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from collect import digest, write_json
from summarize_knowledge_docs import OUT, BASE, plain


def prepare():
    rows = json.loads((OUT/'documents.json').read_text(encoding='utf-8'))
    (OUT/'documents').mkdir(exist_ok=True)
    table = [['文档ID','中文标题','类型','英文单词数','字符数（含空白）','步骤数','适用范围','采集时间','许可/权属','正文文件','来源链接']]
    sections = []
    for r in rows:
        raw = r['source_metadata']
        official = r['group']=='official'
        kind = '官方住房与报修指引' if official else '维修操作教程'
        scope = raw.get('jurisdiction') or ('NSW' if official else '非澳洲专属，型号适用性需确认')
        rights = raw.get('rights_status') if official else raw.get('license')
        rights_url = raw.get('rights_url') if official else raw.get('license_url')
        rights_urls = rights_url if isinstance(rights_url,list) else ([rights_url] if rights_url else [])
        author = raw.get('publisher') if official else raw.get('author',{}).get('username')
        md = [f'# {r["title_zh"]}', '', r['title'], '', f'来源：[{author or "来源页面"}]({r["source_url"]})',
              f'许可/权属：{rights or "待确认"}', f'适用范围：{scope}', '']
        for url in rights_urls:
            md += [f'[许可说明]({url})', '']
        blocks = []
        if official:
            for section in raw['sections']:
                heading = section.get('heading') or ''
                if heading:
                    md += ['## '+heading, '']
                    blocks.append('<h3>'+escape(heading)+'</h3>')
                for block in section.get('blocks',[]):
                    text = block.get('text','')
                    md += [text, '']
                    blocks.append('<p>'+escape(text)+'</p>')
            source = BASE/'20260928T091936387926Z/raw'/(r['id']+'.html')
        else:
            intro = plain(raw.get('introduction'))
            md += [intro, '']
            blocks.append('<p>'+escape(intro)+'</p>')
            for step in raw['steps']:
                heading = f'步骤 {step["order"]}' + (': '+plain(step['title']) if step.get('title') else '')
                md += ['## '+heading, '']
                blocks.append('<h3>'+escape(heading)+'</h3>')
                for line in step.get('lines',[]):
                    text = plain(line.get('text_rendered') or line.get('text_raw'))
                    md += ['- '+text]
                    blocks.append('<p>'+escape(text)+'</p>')
                md.append('')
            source = BASE/'repair-pilot-20261005/raw'/(r['id']+'.json')
        dest = OUT/'source_snapshots'/r['group']/source.name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,dest)
        docpath = 'documents/'+r['id']+'.md'
        (OUT/docpath).write_text('\n'.join(md)+'\n',encoding='utf-8')
        table.append([r['id'],r['title_zh'],kind,r['english_words'],r['characters_with_whitespace'],r['steps'] if not official else None,scope,raw.get('retrieved_at'),rights,docpath,r['source_url']])
        license_link = ''.join(f' · <a href="{escape(url)}">许可说明</a>' for url in rights_urls)
        sections.append(f'<section id="doc-{r["id"]}"><h2>{escape(r["title_zh"])}</h2><p>{r["english_words"]} 词 · {escape(kind)} · {escape(str(scope))}</p><p><a href="{escape(r["source_url"])}">{escape(author or "原始来源")}</a>{license_link} · <a href="{docpath}">Markdown</a> · <a href="{r["text_path"]}">纯文本</a></p><p>{escape(rights or "权属待确认")}</p><details><summary>查看原文</summary>'+''.join(blocks)+'</details></section>')
    with (OUT/'总表.csv').open('w',encoding='utf-8-sig',newline='') as f:
        csv.writer(f).writerows(table)
    write_json(OUT/'workbook_input.json',table)
    (OUT/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>住房与维修知识文档</title><style>body{font:16px/1.65 sans-serif;max-width:1040px;margin:24px auto;padding:0 16px;color:#20252a;overflow-wrap:anywhere}h1{font-size:26px}h2{font-size:21px}h3{font-size:18px}section{border-top:1px solid #ccc;padding:16px 0}a{color:#12649a}summary{cursor:pointer}</style><h1>住房与维修知识文档</h1><p>11 篇，5,899 个英文单词，62 个教程步骤。正文为英文，中文仅用于目录标签。官方规则限 NSW 来源范围；教程不是已认证工单，未附成功下载的教程图片。采集快照未复核为当前规则。</p>'+''.join(sections)+'</html>',encoding='utf-8')
    readme = (OUT/'README.md').read_text(encoding='utf-8').split('## 交付状态')[0]
    readme += '''## 交付内容

- 总表.xlsx / 总表.csv：11 篇文档的标题、词数、步骤数、范围、许可、来源和正文路径。
- [index.html](index.html)：离线文档预览，展开每篇即可阅读。
- documents/：11 篇带标题、来源和步骤编号的 Markdown 正文。
- texts/：11 篇纯文本，作为词数统计输入。
- source_snapshots/：4 份官方 HTML 和 7 份 iFixit API 原始 JSON。
- documents.json / summary.json：结构化记录、原始元数据和长度统计。
- manifest.json / delivery_validation.json：文件哈希和交付检查。

中文标题是整理标签，正文未翻译。官方正文保留原有章节，教程恢复原步骤编号。Markdown 中的署名、编号不计入此前正文词数。

iFixit 共 62 个步骤，图片未下载成功；教程不是实际工单。许可及待确认使用条件沿用原记录，并未取得新的发布授权。本目录为独立于三套图片数据的第四套知识文档交付。

## 重新生成

从项目根目录依次运行 summarize_knowledge_docs.py、package_knowledge_docs.py prepare，再用内置 Node 和 artifact-tool 运行本目录 build_workbook.mjs，最后运行 package_knowledge_docs.py finalize。所有步骤离线，不重新采集。ZIP 位于本目录同级的 knowledge-documents-20261009.zip。
'''
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    print('Prepared 11 documents and 11 raw snapshots.')


def finalize():
    rows = json.loads((OUT/'documents.json').read_text(encoding='utf-8'))
    for r in rows:
        # Source text hashes use LF; Windows text exports may contain CRLF.
        body = (OUT/r['text_path']).read_text(encoding='utf-8')
        assert digest(body.encode('utf-8'))==r['text_sha256']
        assert (OUT/'documents'/(r['id']+'.md')).is_file()
    soup = BeautifulSoup((OUT/'index.html').read_text(encoding='utf-8'),'html.parser')
    assert len(soup.find_all('section'))==11
    for a in soup.find_all('a',href=True):
        if not a['href'].startswith(('https://','http://','#')):
            assert (OUT/a['href']).is_file(),a['href']
    assert len(list((OUT/'source_snapshots').rglob('*.html')))==4
    assert len(list((OUT/'source_snapshots').rglob('*.json')))==7
    with ZipFile(OUT/'总表.xlsx') as z:
        sheet = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        assert len(sheet.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'))==12
    write_json(OUT/'delivery_validation.json',{'documents':11,'source_snapshots':11,'tutorial_steps':62,'english_words':5899,'local_links':'passed','text_hashes':'passed','xlsx_rows':'passed'})
    # Explicit deliverable roots avoid following the runtime dependency junction.
    selected = [OUT/n for n in ['README.md','index.html','总表.xlsx','总表.csv','documents.json','summary.json','delivery_validation.json']]
    for name in ['texts','documents','source_snapshots']:
        selected.extend(p for p in (OUT/name).rglob('*') if p.is_file())
    write_json(OUT/'manifest.json',{p.relative_to(OUT).as_posix():digest(p.read_bytes()) for p in selected})
    target = OUT.with_suffix('.zip')
    with ZipFile(target,'w',ZIP_DEFLATED) as z:
        for p in selected+[OUT/'manifest.json']:
            z.write(p,OUT.name+'/'+p.relative_to(OUT).as_posix())
    with ZipFile(target) as z:
        assert z.testzip() is None
    print('Validated and packaged:',target, target.stat().st_size,'bytes')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['prepare','finalize'])
    args=parser.parse_args()
    globals()[args.phase]()
