"""Validate portable deliverables and create one archive per dataset."""
import csv
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from PIL import Image
from collect import digest, write_json

ROOT = Path('outputs/collected-data-20261009')
results = []
for group in ['repair', 'student', 'general']:
    folder = ROOT/group
    records = json.loads((folder/'records.json').read_text(encoding='utf-8'))
    images = json.loads((folder/'images.json').read_text(encoding='utf-8'))
    ids = {r['id'] for r in records}
    hashes = {a['id'] for a in images}
    for a in images:
        p = folder/a['path']
        assert digest(p.read_bytes()) == a['id']
        with Image.open(p) as im:
            im.verify()
        assert set(a['record_ids']) <= ids
    assert all(set(r['image_ids']) <= hashes and r['image_count'] > 0 for r in records)
    soup = BeautifulSoup((folder/'index.html').read_text(encoding='utf-8'), 'html.parser')
    assert len(soup.find_all('img')) == sum(r['image_count'] for r in records)
    assert all((folder/im['src']).exists() for im in soup.find_all('img'))
    with (folder/'总表.csv').open(encoding='utf-8-sig', newline='') as f:
        assert len(list(csv.reader(f))) == len(records)+1
    with ZipFile(folder/'总表.xlsx') as z:
        ns = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        for i, count in [(1,len(records)),(2,len(images))]:
            root = ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml'))
            assert len(root.findall('.//m:sheetData/m:row', ns)) == count+1
    included = [p for p in folder.rglob('*') if p.is_file() and p.name not in {'workbook_input.json','manifest.json'} and not p.name.endswith('.inspect.ndjson')]
    write_json(folder/'manifest.json', {p.relative_to(folder).as_posix():digest(p.read_bytes()) for p in included})
    with ZipFile(ROOT/(group+'.zip'), 'w', ZIP_DEFLATED) as z:
        for p in included+[folder/'manifest.json']:
            z.write(p, group+'/'+p.relative_to(folder).as_posix())
    with ZipFile(ROOT/(group+'.zip')) as z:
        assert z.testzip() is None
    results.append({'dataset':group,'records':len(records),'images':len(images),'validation':'passed','zip_bytes':(ROOT/(group+'.zip')).stat().st_size})
write_json(ROOT/'delivery_validation.json', results)
print(json.dumps(results, indent=2))
