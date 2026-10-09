"""Bounded source-fit experiment: fixed public pages and three linked UniLodge images.

Research evidence only. Unknown reuse rights remain unknown; no application import,
media publication, account actions, video download or recursive crawling.
"""
import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from PIL import Image

from collect import Fetcher, ROOT, USER_AGENT, digest, write_json


def targets():
    source = ROOT / 'data/collection-pilot/flagstaff-20260929-v1/room_types.json'
    room = next(r for r in json.loads(source.read_text(encoding='utf-8')) if r['name'] == 'Studio Standard')
    media = [room['photos'][i]['url'] for i in (1, 2, 5)]
    return ([{'id': 'home-' + name, 'url': 'https://www.homeapartments.com.au/home-' + name + '/floorplans',
              'kind': 'html'} for name in ('docklands', 'richmond', 'southbank', 'parramatta')]
            + [{'id': 'unilodge-index', 'url': 'https://www.unilodge.com.au/student-accommodation-australia', 'kind': 'html'}]
            + [{'id': 'unilodge-standard-' + str(i), 'url': url, 'kind': 'image',
                'discovery_file': str(source.relative_to(ROOT)), 'room_id': room['id']}
               for i, url in enumerate(media)])


def parse_home_index(body):
    cards = {}
    for node in BeautifulSoup(body, 'html.parser').select('.fp-container[id]'):
        badge = node.select_one('.fp-availability[data-original]')
        count = badge.get('data-original', '') if badge else ''
        cards[node['id']] = int(count) if count.isdigit() else None
    if not cards:
        raise ValueError('no_floorplan_cards')
    return {'floorplan_ids': sorted(cards), 'floorplan_card_count': len(cards),
            'availability_badge_sum': sum(n for n in cards.values() if n is not None),
            'missing_badges': sum(n is None for n in cards.values()),
            'is_verified_unique_unit_count': False}


def run(output, planned=None):
    planned = targets() if planned is None else planned
    output.mkdir(parents=True, exist_ok=False)
    (output / 'raw').mkdir()
    client = Fetcher(hosts={'www.homeapartments.com.au', 'www.unilodge.com.au', 'www.reserve.unilodge.com.au',
                            'image-tc.galaxy.tf', 'inspectre.blob.core.windows.net'})
    robots, outcomes, responses = {}, [], []
    client.client.event_hooks['response'] = [lambda r: responses.append({'url': str(r.url), 'status': r.status_code})]
    try:
        for target in planned:
            record = {**target, 'rights_status': 'unknown', 'state': 'failed'}
            try:
                host = urlsplit(target['url']).hostname
                if host not in robots:
                    _, status, _, body = client.get('https://' + host + '/robots.txt')
                    (output / 'raw' / (host + '.robots.txt')).write_bytes(body)
                    absent_media_rules = status in (404, 410) and target['kind'] == 'image'
                    if status != 200 and not absent_media_rules:
                        raise ValueError('robots_not_verified')
                    rule = RobotFileParser()
                    rule.parse(body.decode(errors='replace').splitlines() if status == 200 else ['User-agent: *', 'Disallow:'])
                    record['robots_status'] = status
                    robots[host] = rule
                final, status, headers, body = client.get(target['url'], permit=lambda u:
                    urlsplit(u).hostname in robots and robots[urlsplit(u).hostname].can_fetch(USER_AGENT, u))
                if status != 200:
                    raise ValueError('http_' + str(status))
                if target['kind'] == 'image':
                    if not headers.get('content-type', '').startswith('image/'):
                        raise ValueError('not_an_image')
                    with Image.open(BytesIO(body)) as image:
                        image.verify()
                    with Image.open(BytesIO(body)) as image:
                        record.update(width=image.width, height=image.height)
                        suffix = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}[image.format]
                else:
                    if 'text/html' not in headers.get('content-type', ''):
                        raise ValueError('not_html')
                    suffix = '.html'
                path = output / 'raw' / (target['id'] + suffix)
                path.write_bytes(body)
                record.update(state='success', status=status, final_url=final, sha256=digest(body),
                              retrieved_at=datetime.now(timezone.utc).isoformat(), local_path=str(path.relative_to(output)))
                if target['id'].startswith('home-'):
                    record.update(parse_home_index(body))
            except Exception as exc:
                record['error'] = str(exc)
            outcomes.append(record)
            print(json.dumps({k: v for k, v in record.items() if k in ('id', 'state', 'error', 'width', 'height')}), flush=True)
    finally:
        client.close()
        write_json(output / 'outcomes.json', outcomes)
        write_json(output / 'responses.json', responses)
        write_json(output / 'manifest.json', {'planned': planned, 'attempts': client.attempts,
                   'bytes': client.total_bytes, 'rights_status': 'unknown', 'publication_status': 'not_released',
                   'script_sha256': digest(Path(__file__).read_bytes()),
                   'files': {str(p.relative_to(output)): digest(p.read_bytes()) for p in sorted((output / 'raw').iterdir())}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
