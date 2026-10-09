"""Fixed three-city discovery batch; no login, inventory guessing or publication."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from collect import digest, write_json
from flagstaff_collect import parse_rooms, media_candidates, text

from source_fit_probe import run

PROPERTIES = [
    ('melbourne-central', 'Melbourne', 'VIC', 'https://www.unilodge.com.au/student-accommodation-melbourne/melbourne-central'),
    ('south-bank', 'Brisbane', 'QLD', 'https://www.unilodge.com.au/student-accommodation-brisbane/south-bank'),
    ('metro-adelaide', 'Adelaide', 'SA', 'https://www.unilodge.com.au/student-accommodation-adelaide/metro-adelaide'),
]


def collect(output):
    planned = [{'id': name, 'city': city, 'state_code': state, 'url': url, 'kind': 'html'}
               for name, city, state, url in PROPERTIES]
    run(output, planned)


def details(source, output):
    targets = []
    for item in json.loads((source/'outcomes.json').read_text(encoding='utf-8')):
        if item['state'] != 'success':
            continue
        soup = BeautifulSoup((source/item['local_path']).read_bytes(), 'html.parser')
        urls = set()
        for heading in soup.select('h3.thumb__title'):
            anchor = heading.find_parent('a')
            if not anchor:
                continue
            url = urljoin(item['url'], anchor.get('href', ''))
            if urlsplit(url).hostname == 'www.reserve.unilodge.com.au' and urlsplit(url).path == '/categoryInfo.html':
                urls.add(url)
        for url in sorted(urls):
            targets.append({'id': item['id']+'-'+digest(url.encode())[:10], 'property_id': item['id'],
                            'city': item['city'], 'state_code': item['state_code'], 'url': url, 'kind': 'html'})
    if len(targets)>20:
        raise ValueError('detail_batch_too_large')
    run(output, targets)
    process(source, output)


def process(source, output):
    rooms, errors, plans = [], [], []
    for item in json.loads((source/'outcomes.json').read_text(encoding='utf-8')):
        if item['state']=='success':
            plans.extend({**p, 'property_id':item['id']} for p in media_candidates((source/item['local_path']).read_bytes(),item) if p['kind']=='floorplan_candidate')
    for item in json.loads((output/'outcomes.json').read_text(encoding='utf-8')):
        if item['state']!='success':
            errors.append({'page':item['id'],'error':item.get('error')})
            continue
        body=(output/item['local_path']).read_bytes()
        soup=BeautifulSoup(body,'html.parser')
        blocks={text(b.find('h2')):b for b in soup.select('.ul_room') if b.find('h2')}
        try:
            found=parse_rooms(body,item,set(blocks),item['property_id'])
            for room in found:
                block=blocks[room['name']]
                description=text(block.select_one('.ul_description') or block)
                floor_text=re.findall(r'[^.!?]*(?:\b[Ll]evels?\s+\d+|\b\d+(?:st|nd|rd|th)\s+[Ff]loor)[^.!?]*',description)
                room.update(property_id=item['property_id'],city=item['city'],state_code=item['state_code'],
                            record_type='room_type',unit_number=None,assigned_floor=None,
                            floor_range_source_text=floor_text,description=description)
                rooms.append(room)
        except Exception as exc:
            errors.append({'page':item['id'],'error':str(exc)})
    ids=[r['id'] for r in rooms]
    if len(ids)!=len(set(ids)):
        raise ValueError('duplicate_room_type_ids')
    write_json(output/'room_types.json',rooms)
    write_json(output/'floorplan_candidates.json',plans)
    write_json(output/'parse_errors.json',errors)
    print(json.dumps({'rooms':len(rooms),'offers':sum(len(r['offers']) for r in rooms),'errors':errors},ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    if args.source:
        details(args.source.resolve(),args.output.resolve())
    else:
        collect(args.output.resolve())
