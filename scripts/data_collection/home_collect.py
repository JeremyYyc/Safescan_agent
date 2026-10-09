"""Bounded HOME public-page pilot. No login, application or enquiry actions."""
import argparse
import json
import html
import re
from io import BytesIO
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
import httpx
from PIL import Image
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

from collect import Fetcher, ROOT, USER_AGENT, digest, write_json

ORIGIN = "https://www.homeapartments.com.au"
URL = ORIGIN + "/home-docklands/floorplans/east-%7C-2-bed-%7C-2-bath-%7C-c04"


def fetch(output):
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    client = Fetcher(hosts={"www.homeapartments.com.au"})
    try:
        _, status, _, body = client.get(ORIGIN + "/robots.txt")
        if status != 200:
            raise ValueError(f"robots_unverified_{status}")
        (output / "raw/robots.txt").write_bytes(body)
        robots = RobotFileParser()
        robots.parse(body.decode().splitlines())
        final, status, headers, body = client.get(URL, permit=lambda u: robots.can_fetch(USER_AGENT, u))
        if status != 200 or "text/html" not in headers.get("content-type", ""):
            raise ValueError(f"page_http_or_type_{status}")
        (output / "raw/c04.html").write_bytes(body)
        write_json(output / "source.json", {"url": URL, "final_url": final,
                   "retrieved_at": datetime.now(timezone.utc).isoformat(), "sha256": digest(body),
                   "rights_status": "unverified_not_open_licensed_no_republication"})
    finally:
        client.close()
    print(str(output), flush=True)


def gallery(output):
    soup = BeautifulSoup((output / 'raw/c04.html').read_bytes(), 'html.parser')
    node = soup.select_one('.fppartial-image[data-modal-url]')
    if node is None:
        raise ValueError('missing_gallery_link')
    client = Fetcher(hosts={'www.homeapartments.com.au'})
    try:
        _, status, _, body = client.get(ORIGIN + '/robots.txt')
        if status != 200:
            raise ValueError('robots_unverified')
        robots = RobotFileParser()
        robots.parse(body.decode().splitlines())
        url = urljoin(URL, node['data-modal-url'])
        final, status, _, body = client.get(url, permit=lambda u: robots.can_fetch(USER_AGENT, u))
        if status != 200:
            raise ValueError(f'gallery_http_{status}')
        (output / 'raw/gallery.html').write_bytes(body)
        write_json(output / 'gallery-source.json', {'url': url, 'final_url': final,
                   'retrieved_at': datetime.now(timezone.utc).isoformat(), 'sha256': digest(body)})
        print('Saved public gallery response', flush=True)
    finally:
        client.close()


def parse(body, gallery_body, source):
    soup = BeautifulSoup(body, 'html.parser')
    section = soup.select_one('.floorplan-section[data-id]')
    if section is None:
        raise ValueError('missing_floorplan_section')
    name = section['data-name']
    beds = re.search(r'\b(\d+) Bed\b', name)
    baths = re.search(r'\b(\d+) Bath\b', name)
    rid = 'home-docklands-' + section['data-id']
    room = {'id': rid, 'property_id': 'home-docklands', 'name': name,
            'bedrooms': int(beds[1]) if beds else None,
            'bathrooms': int(baths[1]) if baths else None,
            'description': ''.join(n.get_text() for n in section.select('[name="less-info"], [name="more-info"]')),
            'source_url': source['url'], 'retrieved_at': source['retrieved_at']}
    units = []
    for row in section.select('tr.unit-container'):
        def cell(selector):
            node = row.select_one(selector)
            if node is None:
                raise ValueError('missing_unit_cell')
            return ' '.join(str(n).strip() for n in node.find_all(string=True, recursive=False)).strip()
        price = row.select_one('.td-card-rent').get_text(' ', strip=True)
        number = re.search(r'\$([\d,]+(?:\.\d+)?)', price)
        units.append({'id': 'home-docklands-' + row['id'], 'room_type_id': rid,
                      'unit_number_raw': cell('.td-card-name'), 'area_sqm': float(cell('.td-card-sqft')),
                      'price_raw': price, 'price_amount': float(number[1].replace(',', '')) if number else None,
                      'currency': 'AUD' if number else None, 'price_period': 'week' if '/Week' in price else None,
                      'availability': 'listed_on_public_page_not_booking_verified',
                      'source_url': source['url'], 'retrieved_at': source['retrieved_at'],
                      'provenance_type': 'public_listing_snapshot'})
    assets = []
    gallery_soup = BeautifulSoup(gallery_body, 'html.parser')
    for node in gallery_soup.select('.carousel-item img[src]'):
        url = node['src']
        if urlsplit(url).hostname != 'resource.rentcafe.com':
            continue
        label = node.get('alt', '')
        is_plan = label.strip().lower() == 'floor plan'
        assets.append({'id': digest(url.encode())[:20], 'url': url, 'label': label,
                       'kind': 'floorplan' if is_plan else 'marketing_image',
                       'scope': 'room_type' if is_plan else 'mixed_display_apartment_and_building_gallery',
                       'room_type_id': rid, 'unit_id': None,
                       'association_basis': 'source_room_type_gallery_not_individual_unit',
                       'source_url': source['url'], 'status': 'url_only', 'local_path': None,
                       'rights_status': source['rights_status']})
    return room, units, list({a['id']: a for a in assets}.values())


def download(output, assets):
    client = Fetcher(hosts={'resource.rentcafe.com'})
    (output / 'media').mkdir(exist_ok=True)
    try:
        _, status, _, body = client.get('https://resource.rentcafe.com/robots.txt')
        (output / 'raw/media-robots.txt').write_bytes(body)
        robots = RobotFileParser()
        if status == 200:
            robots.parse(body.decode(errors='replace').splitlines())
        elif status in (404, 410):
            robots.parse(['User-agent: *', 'Disallow:'])
        else:
            raise ValueError(f'media_robots_unverified_{status}')
        for asset in assets[:14]:
            try:
                existing = output / asset['local_path'] if asset.get('local_path') else None
                if existing and existing.exists() and digest(existing.read_bytes()) == asset.get('sha256'):
                    continue
                final, status, headers, body = client.get(asset['url'], permit=lambda u: robots.can_fetch(USER_AGENT, u))
                if status != 200 or not headers.get('content-type', '').startswith('image/'):
                    raise ValueError(f'media_http_or_type_{status}')
                with Image.open(BytesIO(body)) as im:
                    im.verify()
                with Image.open(BytesIO(body)) as im:
                    width, height, fmt = im.width, im.height, im.format
                suffix = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}.get(fmt)
                if not suffix:
                    raise ValueError('unsupported_image_format')
                sha = digest(body)
                path = output / 'media' / (sha + suffix)
                path.write_bytes(body)
                asset.update(status='downloaded', local_path=path.relative_to(output).as_posix(),
                             sha256=sha, width=width, height=height, bytes=len(body), final_url=final)
            except (ValueError, OSError, httpx.HTTPError) as exc:
                asset.update(status='failed', error=str(exc))
            print(asset['kind'] + ': ' + asset['status'], flush=True)
    finally:
        client.close()


def process(output, media=False):
    source = json.loads((output / 'source.json').read_text(encoding='utf-8'))
    room, units, assets = parse((output / 'raw/c04.html').read_bytes(), (output / 'raw/gallery.html').read_bytes(), source)
    old_path = output / 'assets.json'
    old = {a['id']: a for a in json.loads(old_path.read_text(encoding='utf-8'))} if old_path.exists() else {}
    for asset in assets:
        previous = old.get(asset['id'], {})
        if previous.get('status') == 'downloaded':
            asset.update({k: previous[k] for k in ('status', 'local_path', 'sha256', 'width', 'height', 'bytes', 'final_url')})
    error = None
    if media:
        try:
            download(output, assets)
        except (ValueError, OSError, httpx.HTTPError) as exc:
            error = str(exc)
    building = {'id': 'home-docklands', 'name': 'Home Docklands', 'source_company': 'HOME',
                'relationship': 'listed_on_brand_website', 'legal_owner': None, 'source_url': source['url']}
    for key, value in [('properties', [building]), ('room_types', [room]), ('units', units), ('assets', assets)]:
        write_json(output / (key + '.json'), value)
    summary = {'properties': 1, 'room_types': 1, 'units': len(units), 'assets': len(assets),
               'floorplans': sum(a['kind'] == 'floorplan' for a in assets),
               'downloaded_images': sum(a['status'] == 'downloaded' for a in assets),
               'videos': 0, 'download_error': error, 'rights_status': source['rights_status'],
               'limitations': ['Marketing images are not unit inspection evidence',
                              'Public listing snapshot, not verified live inventory',
                              'Empty video modal is not a video asset', 'No maintenance records']}
    write_json(output / 'summary.json', summary)
    esc = lambda value: html.escape(str(value), quote=True)
    rows = ''.join('<tr>' + ''.join(f'<td>{esc(u[k])}</td>' for k in ('unit_number_raw', 'area_sqm', 'price_amount', 'price_period')) + '</tr>' for u in units)
    figures = ''.join(f'<figure><a href="{esc(a["url"])}"><img src="{esc(a["local_path"])}" alt="{esc(a["label"])}"></a><figcaption>{esc(a["kind"])}: {esc(a["label"])}</figcaption></figure>' for a in sorted(assets, key=lambda a: a['kind'] != 'floorplan') if a['local_path'])
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HOME Docklands sample</title><style>body{font:16px/1.5 system-ui;margin:0;color:#202b28;background:#f6f8f7}main{max-width:1100px;margin:auto;padding:24px}h1{font-size:28px}h2{font-size:21px}a{color:#076753}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ccd4ce}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}figure{margin:0}img{width:100%;aspect-ratio:4/3;object-fit:contain;background:white}p,figcaption{overflow-wrap:anywhere}section{padding:20px 0;border-top:1px solid #ccd4ce}</style><main>'
    page += f'<h1>HOME Docklands</h1><p>{esc(room["name"])} | <a href="{esc(source["url"])}">Official source</a></p><p>Captured: {esc(source["retrieved_at"])}</p><p>Local research sample. Reuse rights unverified. Display-apartment and building images, not individual-unit evidence. Prices and availability may change.</p><section><h2>Listed apartments</h2><table><thead><tr><th>Apartment</th><th>Sq.m.</th><th>AUD</th><th>Period</th></tr></thead><tbody>{rows}</tbody></table></section><section><h2>Floorplan and gallery</h2><div class="gallery">{figures}</div></section><section><h2>Source description</h2><p>{esc(room["description"])}</p></section></main></html>'
    (output / 'preview.html').write_text(page, encoding='utf-8')
    print(json.dumps(summary), flush=True)
    return 1 if error or any(a['status'] == 'failed' for a in assets) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--gallery', type=Path)
    parser.add_argument('--process', type=Path)
    parser.add_argument('--download-media', action='store_true')
    parser.add_argument("--output", type=Path, default=ROOT / "data/collection-pilot" / ("home-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
    args = parser.parse_args()
    if args.process:
        raise SystemExit(process(args.process.resolve(), args.download_media))
    elif args.gallery:
        gallery(args.gallery.resolve())
    else:
        fetch(args.output.resolve())
