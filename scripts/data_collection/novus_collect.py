"""Novus fixed-page personal research sample; no forms or recursive crawl."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from collect import Fetcher, USER_AGENT, digest, write_json

ORIGIN = 'https://www.novusaus.com'
PAGES = {'terms': ORIGIN + '/terms-of-use/', 'index': ORIGIN + '/find-your-home/result/',
         'sample': ORIGIN + '/find-your-home/novus-on-sturt/IRE4925059'}
HOSTS = {'www.novusaus.com', 'inspectre.blob.core.windows.net'}


def text(node):
    return ' '.join(node.get_text(' ', strip=True).split()) if node else ''


def parse(body, source):
    soup = BeautifulSoup(body, 'html.parser')
    address = soup.select_one('#currentAddress')
    if address is None:
        raise ValueError('missing_unit_address')
    block = address.parent
    def count(label):
        node = block.select_one('img[alt="' + label + '"]')
        if node is None:
            return None
        value = node.parent.select_one('.ma')
        return int(text(value)) if value and text(value).isdigit() else None
    area = next((re.fullmatch(r'(\d+(?:\.\d+)?)\s*m\s*2', text(n))
                 for n in block.select('.ma') if re.fullmatch(r'(\d+(?:\.\d+)?)\s*m\s*2', text(n))), None)
    price = next((re.fullmatch(r'\$([\d,]+(?:\.\d+)?) per week', text(n))
                  for n in block.select('strong') if re.fullmatch(r'\$([\d,]+(?:\.\d+)?) per week', text(n))), None)
    if not price:
        raise ValueError('missing_weekly_price')
    plan = soup.select_one('a.floorplan[href]')
    assets = {}
    if plan:
        url = urljoin(source['url'], plan['href'])
        assets[url] = {'url': url, 'kind': 'floorplan', 'association': 'unit_detail_link', 'downloaded': False}
    for node in soup.find_all(['img', 'a']):
        for key in ('src', 'data-src', 'href'):
            url = urljoin(source['url'], node.get(key, ''))
            if urlsplit(url).hostname == 'inspectre.blob.core.windows.net' and url not in assets:
                assets[url] = {'url': url, 'kind': 'gallery_candidate', 'association': 'indicative_not_exact_unit', 'downloaded': False}
    videos = sorted({urljoin(source['url'], n.get(k, '')) for n in soup.find_all(True)
                     for k in ('src', 'href', 'data-video', 'data-src')
                     if urlsplit(urljoin(source['url'], n.get(k, ''))).hostname in ('www.youtube.com', 'youtu.be', 'player.vimeo.com')})
    availability = next((text(n) for n in block.select('p') if text(n).startswith('Available ')), None)
    listing = re.search(r'/(IRE\d+)(?:[/?#]|$)', source['url'])
    if listing is None:
        raise ValueError('missing_listing_id')
    return {'source_id': 'novus', 'source_listing_id': listing[1], 'record_type': 'unit_listing',
            'source_url': source['url'], 'retrieved_at': source['retrieved_at'],
            'address': text(address), 'bedrooms': count('bed'), 'bathrooms': count('bath'),
            'parking_spaces': count('car'), 'area_sqm': format(Decimal(area[1]), 'f') if area else None,
            'area_scope': 'unspecified_listing_area', 'weekly_rent': format(Decimal(price[1].replace(',', '')), 'f'),
            'currency': None, 'currency_reason': 'dollar_symbol_only', 'period': 'week',
            'rent_basis': 'unit_listing_context_not_explicit_contract', 'lease_condition': None,
            'availability_raw': availability, 'availability_verified': False,
            'assets': list(assets.values()), 'video_links': videos,
            'rights_status': 'personal_noncommercial_download_only_other_use_unverified',
            'publication_status': 'not_released'}


class Probe:
    def __init__(self, output):
        self.output = output
        self.client = Fetcher(hosts=HOSTS)
        self.robots = {}
        self.events = []
        self.client.client.event_hooks['response'] = [lambda r: self.events.append({'url': str(r.url), 'status': r.status_code})]

    def get(self, url):
        host = urlsplit(url).hostname
        if host not in self.robots:
            _, status, _, body = self.client.get('https://' + host + '/robots.txt')
            (self.output / 'raw' / (host + '.robots.txt')).write_bytes(body)
            if status not in (200, 404, 410):
                raise ValueError('robots_unverified')
            rule = RobotFileParser()
            rule.parse(body.decode(errors='replace').splitlines() if status == 200 else ['User-agent: *', 'Disallow:'])
            self.robots[host] = rule
        return self.client.get(url, permit=lambda u: urlsplit(u).hostname in self.robots
                               and self.robots[urlsplit(u).hostname].can_fetch(USER_AGENT, u))


def collect(output):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'raw').mkdir()
    probe, pages = Probe(output), []
    try:
        for key, url in PAGES.items():
            final, status, headers, body = probe.get(url)
            if status != 200 or 'text/html' not in headers.get('content-type', ''):
                raise ValueError('html_fetch_failed:' + key + ':' + str(status))
            (output / 'raw' / (key + '.html')).write_bytes(body)
            meta = {'id': key, 'url': url, 'final_url': final, 'sha256': digest(body),
                    'retrieved_at': datetime.now(timezone.utc).isoformat()}
            pages.append(meta)
            if key == 'sample':
                write_json(output / 'sample.json', parse(body, meta))
            if key == 'index':
                links = sorted({urljoin(url, a['href']) for a in BeautifulSoup(body, 'html.parser').select('a[href]')
                                if re.search(r'/find-your-home/[^/]+/IRE\d+', a['href'])})
                write_json(output / 'index.json', {'url': url, 'retrieved_at': meta['retrieved_at'],
                           'visible_listing_urls': links, 'visible_listing_count': len(links),
                           'is_total_inventory': False})
    finally:
        probe.client.close()
        write_json(output / 'pages.json', pages)
        write_json(output / 'responses.json', probe.events)
        write_json(output / 'manifest.json', {'attempts': probe.client.attempts,
                   'script_sha256': digest(Path(__file__).read_bytes()),
                   'files': {str(p.relative_to(output)): digest(p.read_bytes()) for p in (output / 'raw').iterdir()},
                   'scope': 'personal_noncommercial_research_not_republication', 'publication_status': 'not_released'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args().output.resolve())
