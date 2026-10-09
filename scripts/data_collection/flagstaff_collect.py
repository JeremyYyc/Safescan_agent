"""Fixed-page Flagstaff metadata pilot. Never downloads media or submits forms."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import tinycss2

from collect import Fetcher, ROOT, USER_AGENT, digest, write_json

MAIN = 'https://www.unilodge.com.au'
RESERVE = 'https://www.reserve.unilodge.com.au'
PAGES = {
    'property': MAIN + '/student-accommodation-melbourne/melbourne-flagstaff',
    'terms': MAIN + '/terms-conditions',
    'studios': RESERVE + '/categoryInfo.html?category=488',
    'two-bedroom': RESERVE + '/categoryInfo.html?category=489',
    'four-bedroom': RESERVE + '/categoryInfo.html?category=490',
}
TARGETS = {'Studio Standard', 'Studio Terrace', 'Studio Queen',
           '2 Bedroom Apartment', '4 Bedroom Apartment'}


def text(node):
    return ' '.join(node.get_text(' ', strip=True).split()) if node else ''


def parse_rooms(body, source, target_names=None, id_prefix='flagstaff'):
    soup = BeautifulSoup(body, 'html.parser')
    rooms = []
    for block in soup.select('.ul_room'):
        name = text(block.find('h2'))
        if name not in (TARGETS if target_names is None else target_names):
            continue
        rid = id_prefix + '-' + digest(name.encode())[:16]
        content = text(block.select_one('.ul_description') or block)
        area = re.search(r'(?:Each|The)\s+(\d+(?:\.\d+)?)\s*m[²2]\s+(studio|bedroom)', content, re.I)
        offers = []
        for stay in block.select('.ul_stay'):
            price = stay.select_one('.ul_stayPrice .price')
            if price is None:
                raise ValueError('stay_missing_price:' + name)
            amount = Decimal(text(price).replace(',', ''))
            if not amount.is_finite() or amount < 0:
                raise ValueError('invalid_price')
            def value(selector):
                node = stay.select_one(selector)
                return node.get('value') if node else None
            offers.append({'amount': format(amount, 'f'), 'currency': None,
                           'currency_reason': 'dollar_symbol_only_verify_AUD',
                           'period': 'week' if '/ week' in text(stay.select_one('.ul_stayPrice')) else None,
                           'basis': 'person' if 'Weekly Rent is per person' in content else None,
                           'lease_label': text(stay.select_one('.ul_rateTitle')),
                           'default_start': value('.fromDateCustom'), 'default_end': value('.toDateCustom'),
                           'date_semantics': 'page_form_defaults_not_confirmed_contract',
                           'residents': value('input[name="room1Adults"]')})
        tours = sorted({urljoin(source['url'], a['href']) for a in block.select('a[href]')
                        if urlsplit(urljoin(source['url'], a['href'])).hostname == 'my.matterport.com'})
        photos = []
        # Galleries are CSS backgrounds, not img tags; parse declarations structurally.
        for node in block.select('.roomImages [style]'):
            for declaration in tinycss2.parse_declaration_list(node['style'], skip_whitespace=True, skip_comments=True):
                if declaration.type != 'declaration' or declaration.lower_name != 'background-image':
                    continue
                for token in declaration.value:
                    url = token.value if token.type == 'url' else None
                    if token.type == 'function' and token.lower_name == 'url':
                        values = [t.value for t in token.arguments if t.type == 'string']
                        url = values[0] if len(values) == 1 else None
                    if url:
                        url = urljoin(source['url'], url)
                        if urlsplit(url).scheme == 'https' and urlsplit(url).hostname == urlsplit(source['url']).hostname:
                            photos.append({'url': url, 'label': None, 'association': 'room_section_unverified',
                                           'kind': 'unclassified_gallery_media', 'downloaded': False})
        for image in block.select('img'):
            url = image.get('data-src') or image.get('src')
            if url and urlsplit(urljoin(source['url'], url)).hostname == 'image-tc.galaxy.tf':
                photos.append({'url': urljoin(source['url'], url), 'label': image.get('alt'),
                               'association': 'room_section_unverified', 'downloaded': False})
        rooms.append({'id': rid, 'name': name, 'source_url': source['url'],
                      'retrieved_at': source['retrieved_at'], 'source_sha256': source['sha256'],
                      'area_sqm': float(area[1]) if area else None,
                      'area_scope': ('bedroom' if area[2].lower() == 'bedroom' else 'studio') if area else 'unknown',
                      'bedding': text(block.select_one('.choicesBedding')) or None,
                      'max_guests_raw': text(block.select_one('.choicesMax')) or None,
                      'room_features': [text(item) for section in block.select('.choicesSection')
                                        if text(section.find('h3')) == 'Room Features' for item in section.select('li')],
                      'offers': offers, 'photos': list({p['url']: p for p in photos}.values()),
                      'vr_links': tours, 'rights_status': 'unknown', 'human_approved': False,
                      'photo_caveat': 'generic_display_photos_not_individual_unit_evidence',
                      'missing': ['currency_confirmation', 'floorplan_association_review', 'interior_photo_review']
                                 + ([] if offers else ['no_stay_period_offered'])})
    if not rooms:
        raise ValueError('no_target_room_sections')
    return rooms


def media_candidates(body, source):
    items = {}
    for node in BeautifulSoup(body, 'html.parser').select('img'):
        label = node.get('alt', '')
        url = node.get('data-src') or node.get('src')
        if not url or urlsplit(urljoin(source['url'], url)).hostname != 'image-tc.galaxy.tf':
            continue
        url = urljoin(source['url'], url)
        items[url] = {'url': url, 'label': label, 'source_url': source['url'],
                      'kind': 'floorplan_candidate' if re.search(r'floor\s*plan', label, re.I) else 'photo_candidate',
                      'room_id': None, 'association_status': 'pending', 'downloaded': False}
    return list(items.values())


def process(output):
    pages = json.loads((output / 'pages.json').read_text(encoding='utf-8'))
    rooms, assets = [], []
    for source in pages:
        if source.get('state') != 'success':
            continue
        body = (output / 'raw' / (source['id'] + '.html')).read_bytes()
        if digest(body) != source['sha256']:
            raise ValueError('snapshot_hash_mismatch')
        if source['id'] in ('studios', 'two-bedroom', 'four-bedroom'):
            rooms.extend(parse_rooms(body, source))
        elif source['id'] == 'property':
            assets = media_candidates(body, source)
    names = [r['name'] for r in rooms]
    if len(names) != len(set(names)):
        raise ValueError('duplicate_room_name')
    summary = {'planned_rooms': 5, 'parsed_rooms': len(rooms), 'missing_rooms': sorted(TARGETS-set(names)),
               'offers': sum(len(r['offers']) for r in rooms),
               'rooms_with_offers': sum(bool(r['offers']) for r in rooms),
               'floorplan_link_candidates': sum(a['kind'] == 'floorplan_candidate' for a in assets),
               'room_vr_links': sum(len(r['vr_links']) for r in rooms),
               'unique_vr_links': len({u for r in rooms for u in r['vr_links']}),
               'room_gallery_link_records': sum(len(r['photos']) for r in rooms),
               'unique_room_gallery_urls': len({p['url'] for r in rooms for p in r['photos']}),
               'downloaded_media': 0, 'rights_status': 'unknown', 'publication_status': 'not_released'}
    for name, value in [('room_types', rooms), ('media_candidates', assets), ('summary', summary)]:
        write_json(output / (name + '.json'), value)
    write_json(output / 'analysis_manifest.json', {
        'parser_sha256': digest(Path(__file__).read_bytes()),
        'outputs': {n: digest((output / n).read_bytes()) for n in ('room_types.json', 'media_candidates.json', 'summary.json')},
        'page_hashes': {p['id']: p['sha256'] for p in pages if p.get('state') == 'success'}})
    print(json.dumps(summary, indent=2))


def collect(output):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'raw').mkdir()
    client = Fetcher(hosts={urlsplit(u).hostname for u in PAGES.values()})
    rules, pages, events = {}, [], []
    client.client.event_hooks['response'] = [lambda r: events.append({
        'url': str(r.url), 'status': r.status_code, 'observed_at': datetime.now(timezone.utc).isoformat()})]
    try:
        for origin in (MAIN, RESERVE):
            _, status, _, body = client.get(origin + '/robots.txt')
            (output / 'raw' / (urlsplit(origin).hostname + '.robots.txt')).write_bytes(body)
            if status != 200:
                raise ValueError('robots_unverified')
            rule = RobotFileParser()
            rule.parse(body.decode(errors='replace').splitlines())
            rules[urlsplit(origin).hostname] = rule
        for key, url in PAGES.items():
            row = {'id': key, 'url': url, 'state': 'failed'}
            try:
                final, status, headers, body = client.get(url, permit=lambda u:
                    urlsplit(u).hostname in rules and rules[urlsplit(u).hostname].can_fetch(USER_AGENT, u))
                if status != 200 or 'text/html' not in headers.get('content-type', ''):
                    raise ValueError('invalid_response:' + str(status))
                (output / 'raw' / (key + '.html')).write_bytes(body)
                row.update(state='success', final_url=final, status=status, sha256=digest(body),
                           retrieved_at=datetime.now(timezone.utc).isoformat())
            except Exception as exc:
                row['error'] = str(exc)
            pages.append(row)
    finally:
        client.close()
        write_json(output / 'pages.json', pages)
        write_json(output / 'fetch_responses.json', events)
        write_json(output / 'run.json', {'planned_pages': PAGES, 'attempts_including_robots': client.attempts,
                   'response_events': len(events), 'bytes': client.total_bytes, 'rights_status': 'unknown',
                   'scope': 'fixed_public_html_research_no_media_download_no_publication',
                   'script_sha256': digest(Path(__file__).read_bytes())})
    process(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--process', type=Path)
    args = parser.parse_args()
    if args.process:
        process(args.process.resolve())
    elif args.output:
        collect(args.output.resolve())
    else:
        parser.error('--output or --process required')
