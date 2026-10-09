"""Bounded evidence retrieval for manual review, never automatic acceptance."""
import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from PIL import Image
from bs4 import BeautifulSoup
from collect import Fetcher, USER_AGENT, digest, write_json


def prepare_homely(source, output):
    targets = []
    for name, filename, limit in [('hotham', '00.html', 8), ('elgin', '01.html', 6)]:
        path = source / filename
        soup = BeautifulSoup(path.read_bytes(), 'html.parser')
        graph = json.loads(soup.find('script', type='application/ld+json').text)['@graph']
        listing = next(n for n in graph if n.get('@type') == 'RealEstateListing')
        assets = [('layout', x['contentUrl']) for x in listing.get('associatedMedia', [])
                  if 'Floorplan' in x.get('name', '')]
        assets += [('gallery', x['url']) for x in listing['image'][:limit]]
        for i, (role, url) in enumerate(assets):
            targets.append({'id': name + '-' + str(i), 'kind': 'image', 'role': role,
                            'url': url, 'listing_url': listing['url'],
                            'source_html_sha256': digest(path.read_bytes())})
    write_json(output, targets)


def run(targets, output):
    if not 1 <= len(targets) <= 20:
        raise ValueError('expected_1_to_20_explicit_targets')
    output.mkdir(parents=True, exist_ok=False)
    client = Fetcher(hosts={urlsplit(t['url']).hostname for t in targets})
    rules, results = {}, []
    try:
        for i, target in enumerate(targets):
            record = {**target, 'status': 'failed', 'rights_status': 'unknown'}
            try:
                host = urlsplit(target['url']).hostname
                if host not in rules:
                    _, status, _, body = client.get('https://' + host + '/robots.txt')
                    (output / (host + '.robots.txt')).write_bytes(body)
                    if status != 200 and not (target['kind'] == 'image' and status in (404, 410)):
                        raise ValueError('robots_unverified_' + str(status))
                    parser = RobotFileParser()
                    parser.parse(body.decode(errors='replace').splitlines() if status == 200 else ['User-agent: *', 'Disallow:'])
                    rules[host] = parser
                final, status, headers, body = client.get(target['url'], permit=lambda u:
                    urlsplit(u).hostname in rules and rules[urlsplit(u).hostname].can_fetch(USER_AGENT, u))
                if status != 200:
                    raise ValueError('http_' + str(status))
                suffix = '.html'
                if target['kind'] == 'image':
                    with Image.open(BytesIO(body)) as im:
                        im.verify()
                    with Image.open(BytesIO(body)) as im:
                        record.update(width=im.width, height=im.height)
                        suffix = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}[im.format]
                elif 'text/html' not in headers.get('content-type', ''):
                    raise ValueError('not_html')
                path = output / (str(i).zfill(2) + suffix)
                path.write_bytes(body)
                record.update(status='success', final_url=final, local_path=path.name,
                              sha256=digest(body), retrieved_at=datetime.now(timezone.utc).isoformat())
            except Exception as exc:
                record['error'] = str(exc)
            results.append(record)
            write_json(output / 'outcomes.json', results)
            print(json.dumps(record), flush=True)
    finally:
        client.close()
        write_json(output / 'manifest.json', {'targets': targets, 'attempts': client.attempts,
                   'bytes': client.total_bytes, 'publication_status': 'not_released',
                   'files': {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--targets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-homely', type=Path)
    args = parser.parse_args()
    if args.prepare_homely:
        prepare_homely(args.prepare_homely, args.targets)
    else:
        run(json.loads(args.targets.read_text(encoding='utf-8')), args.output)
