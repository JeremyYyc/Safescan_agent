"""Export PostgreSQL sample data and portable MinIO objects without network I/O."""
import json
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from collect import digest, write_json

BASE = Path('outputs/collected-data-20261009')
DOCS = Path('outputs/knowledge-documents-20261009')
OUT = Path('outputs/sql-minio-dataset-20261020')
BUCKET = 'safescan-media'
PREFIX = 'datasets/collection-20261009'


def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if '\x00' in value:
        raise ValueError('PostgreSQL text cannot contain NUL')
    return "'" + value.replace("'", "''") + "'"


def insert(table, columns, values, keys):
    updates = ', '.join(f'{c}=EXCLUDED.{c}' for c in columns if c not in keys)
    return (f'INSERT INTO collected_data.{table} ({", ".join(columns)}) VALUES '
            f'({", ".join(literal(v) for v in values)}) ON CONFLICT ({", ".join(keys)}) '
            + (f'DO UPDATE SET {updates};' if updates else 'DO NOTHING;'))


DDL = """
BEGIN;
SET LOCAL standard_conforming_strings = on;
CREATE SCHEMA IF NOT EXISTS collected_data;
CREATE TABLE IF NOT EXISTS collected_data.media_assets (
 id text PRIMARY KEY CHECK (length(id)=64), bucket text NOT NULL, object_key text NOT NULL,
 mime_type text NOT NULL, byte_size bigint NOT NULL CHECK(byte_size>0),
 width integer NOT NULL, height integer NOT NULL, source_url text,
 metadata jsonb NOT NULL, UNIQUE(bucket,object_key)
);
CREATE TABLE IF NOT EXISTS collected_data.housing_records (
 id text PRIMARY KEY, dataset_type text NOT NULL CHECK(dataset_type IN ('student','general')),
 name text NOT NULL, city text, region text, address jsonb, source_url text, metadata jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS collected_data.repair_cases (
 id text PRIMARY KEY, name text NOT NULL, category text, source_url text,
 actual_work_order boolean NOT NULL DEFAULT false CHECK(NOT actual_work_order), metadata jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS collected_data.housing_media (
 housing_id text REFERENCES collected_data.housing_records(id),
 media_id text REFERENCES collected_data.media_assets(id), role text,
 PRIMARY KEY(housing_id,media_id)
);
CREATE TABLE IF NOT EXISTS collected_data.repair_media (
 repair_id text REFERENCES collected_data.repair_cases(id),
 media_id text REFERENCES collected_data.media_assets(id), role text,
 PRIMARY KEY(repair_id,media_id)
);
CREATE TABLE IF NOT EXISTS collected_data.knowledge_documents (
 id text PRIMARY KEY, title text NOT NULL, title_zh text NOT NULL, document_type text NOT NULL,
 body text NOT NULL, english_words integer NOT NULL, source_url text NOT NULL,
 jurisdiction text, license_info jsonb, metadata jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS collected_data.knowledge_steps (
 document_id text REFERENCES collected_data.knowledge_documents(id), step_number integer CHECK(step_number>0),
 title text, body text NOT NULL, metadata jsonb NOT NULL, PRIMARY KEY(document_id,step_number)
);
"""


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    statements = ['-- PostgreSQL 17; UTF-8. No credentials, no business-table writes.', DDL]
    objects = {}
    groups = {}
    mime = {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp'}
    for group in ['repair','student','general']:
        folder = BASE/group
        records = json.loads((folder/'records.json').read_text(encoding='utf-8'))
        images = json.loads((folder/'images.json').read_text(encoding='utf-8'))
        groups[group] = {'records':len(records),'images':len(images),'associations':sum(len(r['image_ids']) for r in records)}
        for a in images:
            src = folder/a['path']
            sha = digest(src.read_bytes())
            assert sha == a['id']
            if sha not in objects:
                key = f'{PREFIX}/images/{sha}{src.suffix.lower()}'
                local = 'objects/'+sha+src.suffix.lower()
                dest = OUT/local
                dest.parent.mkdir(exist_ok=True)
                shutil.copy2(src,dest)
                objects[sha] = {'sha256':sha,'bucket':BUCKET,'object_key':key,'local_path':local,
                                'byte_size':src.stat().st_size,'content_type':mime[src.suffix.lower()]}
                statements.append(insert('media_assets',
                    ['id','bucket','object_key','mime_type','byte_size','width','height','source_url','metadata'],
                    [sha,BUCKET,key,mime[src.suffix.lower()],src.stat().st_size,a['width'],a['height'],a.get('url'),a],['id']))
        image_map = {a['id']:a for a in images}
        for r in records:
            rid = group+':'+r['id']
            if group=='repair':
                statements.append(insert('repair_cases',['id','name','category','source_url','actual_work_order','metadata'],
                                         [rid,r['name'],r.get('category'),r.get('source_url'),False,r],['id']))
            else:
                address = r.get('address')
                statements.append(insert('housing_records',['id','dataset_type','name','city','region','address','source_url','metadata'],
                                         [rid,group,r['name'],r.get('city'),r.get('region'),json.dumps(address,ensure_ascii=False) if address is not None else None,r.get('source_url'),r],['id']))
            for sha in r['image_ids']:
                assert sha in image_map
                table, fk = ('repair_media','repair_id') if group=='repair' else ('housing_media','housing_id')
                statements.append(insert(table,[fk,'media_id','role'],[rid,sha,image_map[sha].get('role')],[fk,'media_id']))
    docs = json.loads((DOCS/'documents.json').read_text(encoding='utf-8'))
    steps_count=0
    from summarize_knowledge_docs import plain
    for r in docs:
        raw=r['source_metadata']
        body=(DOCS/r['text_path']).read_text(encoding='utf-8')
        assert digest(body.encode('utf-8'))==r['text_sha256']
        license_info={k:raw.get(k) for k in ['license','license_url','rights_status','rights_url','usage_status']}
        statements.append(insert('knowledge_documents',
            ['id','title','title_zh','document_type','body','english_words','source_url','jurisdiction','license_info','metadata'],
            [r['id'],r['title'],r['title_zh'],r['group'],body,r['english_words'],r['source_url'],raw.get('jurisdiction'),license_info,r],['id']))
        for step in raw.get('steps',[]):
            text='\n'.join(plain(line.get('text_rendered') or line.get('text_raw')) for line in step.get('lines',[]))
            statements.append(insert('knowledge_steps',['document_id','step_number','title','body','metadata'],
                                     [r['id'],step['order'],plain(step.get('title')),text,step],['document_id','step_number']))
            steps_count+=1
    statements += ['CREATE INDEX IF NOT EXISTS housing_city_idx ON collected_data.housing_records(city);',
                   'CREATE INDEX IF NOT EXISTS repair_category_idx ON collected_data.repair_cases(category);',
                   'COMMIT;']
    (OUT/'dataset.sql').write_text('\n\n'.join(statements)+'\n',encoding='utf-8')
    write_json(OUT/'objects.json',list(objects.values()))
    write_json(OUT/'summary.json',{'groups':groups,'unique_objects':len(objects),'documents':len(docs),'steps':steps_count,
                                  'bucket':BUCKET,'object_prefix':PREFIX})
    shutil.copy2(Path(__file__).with_name('upload_dataset_minio.py'),OUT/'upload_images.py')
    (OUT/'requirements.txt').write_text('minio>=7.2,<8\n',encoding='utf-8')
    shutil.copy2(Path(__file__).with_name('SQL-MINIO-DELIVERY.zh-CN.md'),OUT/'README.md')
    for obj in objects.values():
        assert digest((OUT/obj['local_path']).read_bytes())==obj['sha256']
    write_json(OUT/'manifest.json',{p.relative_to(OUT).as_posix():digest(p.read_bytes()) for p in OUT.rglob('*') if p.is_file() and p.name!='manifest.json'})
    with ZipFile(OUT.with_suffix('.zip'),'w',ZIP_DEFLATED) as z:
        for p in OUT.rglob('*'):
            if p.is_file():
                z.write(p,OUT.name+'/'+p.relative_to(OUT).as_posix())
    with ZipFile(OUT.with_suffix('.zip')) as z:
        assert z.testzip() is None
    print(json.dumps({'groups':groups,'images':len(objects),'docs':len(docs),'steps':steps_count},indent=2))


if __name__=='__main__':
    build()
