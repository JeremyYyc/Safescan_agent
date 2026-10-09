"""Small, allowlisted UniLodge housing pilot; no account or enquiry actions."""
import argparse
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, urljoin, parse_qs
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import httpx
from PIL import Image

from collect import Fetcher, ROOT, USER_AGENT, digest, write_json

ORIGIN = "https://www.unilodge.com.au"
PAGES = {
    "kensington": ORIGIN + "/student-accommodation-sydney/kensington",
    "kensington-gallery": ORIGIN + "/student-accommodation-sydney/kensington/gallery",
    "indi-sydney": ORIGIN + "/student-accommodation-sydney/indi-sydney",
}
MEDIA_HOST = "image-tc.galaxy.tf"


def text(node):
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def stable_id(value):
    return digest(value.encode())[:20]


def parse_property(body, source):
    soup = BeautifulSoup(body, "html.parser")
    businesses = []
    for node in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(node.string or "null")
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") in ("LocalBusiness", "LodgingBusiness"):
                businesses.append(item)
    if not businesses:
        raise ValueError("missing_property_structured_data")
    business = businesses[0]
    pid = "unilodge-" + source["id"]
    building = {"id": pid, "name": business.get("name"), "source_company": "UniLodge",
                "relationship": "listed_on_company_website", "legal_owner": None,
                "source_url": source["url"], "retrieved_at": source["retrieved_at"],
                "address": business.get("address"), "geo": business.get("geo"),
                "jurisdiction": "AU-NSW", "units_available": None,
                "rights_status": "not_open_licensed_review_before_republication",
                "facilities": list(dict.fromkeys(text(n) for n in soup.select('[id^="facility-"] .popup__title') if text(n)))}
    rooms, assets = [], []
    for heading in soup.select("h3.thumb__title"):
        card = heading.find_parent(class_="thumb")
        if card is None:
            continue
        name = text(heading)
        rid = pid + "-" + stable_id(name)
        price = text(card.select_one(".thumb_price"))
        match = re.search(r"\$([\d,]+(?:\.\d+)?)", price)
        link = heading.find_parent("a")
        room = {"id": rid, "property_id": pid, "name": name, "record_type": "room_type",
                "unit_number": None, "availability": "not_confirmed", "area_sqm": None,
                "bathrooms": None, "bedrooms": None,
                "price_raw": price or None, "price_amount": float(match[1].replace(',', '')) if match else None,
                "currency": "AUD" if match else None,
                "price_period": None, "price_qualifier": "from" if match else None,
                "price_basis": "not_confirmed_per_person_or_apartment",
                "detail_url": urljoin(source["url"], link["href"]) if link else None,
                "source_url": source["url"], "retrieved_at": source["retrieved_at"],
                "photo_ids": [], "virtual_tour_ids": [], "floorplan_ids": [], "video_ids": []}
        bedrooms = re.fullmatch(r"(\d+) Bedroom Apartment", name)
        if bedrooms:
            room['bedrooms'] = int(bedrooms[1])
        room['provenance_type'] = 'public_listing'
        # Match explicit photo labels, never infer an individual apartment from a gallery.
        photos = [n for n in soup.find_all("img") if n.get("alt", "").strip() == name]
        if not photos:
            photos = card.find_all("img")[:1]
        seen = set()
        for node in photos[:2]:
            url = node.get("data-src") or node.get("src")
            if not url or urlsplit(url).hostname != MEDIA_HOST or url in seen:
                continue
            seen.add(url)
            aid = "photo-" + stable_id(url)
            assets.append({"id": aid, "property_id": pid, "room_type_id": rid,
                           "kind": "photo", "scope": "room_type_marketing", "source_url": source["url"],
                           "url": url, "label": node.get("alt") or name,
                           "association_basis": "exact_image_alt" if node.get("alt", "").strip() == name else "room_card",
                           "status": "url_only", "local_path": None,
                           "rights_status": "not_open_licensed_review_before_republication"})
            room["photo_ids"].append(aid)
        rooms.append(room)
    seen_tours = set()
    aliases = {"Studio Premium Apartment": "Studio Premium", "8 Bedroom Cluster Room": "7 or 8 Bedroom Shared Apartment"}
    for link in soup.select('a[href]'):
        url = link['href']
        host = urlsplit(url).hostname
        model = parse_qs(urlsplit(url).query).get("m", [None])[0]
        if host != "my.matterport.com" or not model or model in seen_tours:
            continue
        seen_tours.add(model)
        label = text(link)
        target_name = aliases.get(label, label)
        room = next((r for r in rooms if r["name"] == target_name), None)
        aid = "tour-" + stable_id(model)
        assets.append({"id": aid, "property_id": pid, "room_type_id": room['id'] if room else None,
                       "kind": "virtual_tour", "scope": "room_type_marketing" if room else "building_common_area",
                       "url": url, "label": label, "source_url": source['url'],
                       "association_basis": "source_link_label_alias" if label in aliases else "source_link_label",
                       "status": "external_link_not_downloaded", "local_path": None,
                       "rights_status": "third_party_viewer_not_a_download_license"})
        if room:
            room['virtual_tour_ids'].append(aid)
    return building, rooms, assets


def download_photos(output, assets):
    client = Fetcher(hosts={MEDIA_HOST})
    media = output / "media"
    media.mkdir(exist_ok=True)
    try:
        _, status, _, body = client.get(f"https://{MEDIA_HOST}/robots.txt")
        (output / "raw" / "media-robots.txt").write_bytes(body)
        robots = RobotFileParser()
        if status == 200:
            robots.parse(body.decode(errors="replace").splitlines())
        elif status in (404, 410):
            robots.parse(["User-agent: *", "Disallow:"])
        else:
            raise ValueError(f"media_robots_unverified_{status}")
        for asset in [a for a in assets if a['kind'] == 'photo'][:16]:
            try:
                existing = output / asset['local_path'] if asset.get('local_path') else None
                if existing and existing.exists() and digest(existing.read_bytes()) == asset.get('sha256'):
                    continue
                final, status, headers, body = client.get(asset['url'], permit=lambda u: robots.can_fetch(USER_AGENT, u))
                if status != 200 or not headers.get('content-type', '').startswith('image/'):
                    raise ValueError(f"media_http_or_type_{status}")
                with Image.open(BytesIO(body)) as image:
                    image.verify()
                with Image.open(BytesIO(body)) as image:
                    width, height, fmt = image.width, image.height, image.format
                suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(fmt)
                if not suffix:
                    raise ValueError("unsupported_image_format")
                sha = digest(body)
                local = media / (sha + suffix)
                local.write_bytes(body)
                asset.update(status="downloaded", local_path=local.relative_to(output).as_posix(),
                             sha256=sha, bytes=len(body), width=width, height=height, final_url=final)
            except (ValueError, OSError, httpx.HTTPError) as exc:
                asset.update(status="failed", error=str(exc))
            print(json.dumps({"asset": asset['id'], "status": asset['status']}), flush=True)
    finally:
        client.close()


def render_preview(output, buildings, rooms, assets):
    esc = lambda v: html.escape(str(v if v is not None else "Unknown"), quote=True)
    lookup = {a['id']: a for a in assets}
    sections = []
    for building in buildings:
        items = []
        for room in [r for r in rooms if r['property_id'] == building['id']]:
            photos = ''.join(f'<a href="{esc(lookup[aid]["url"])}"><img src="{esc(lookup[aid]["local_path"])}" alt="{esc(room["name"])}" loading="lazy"></a>' for aid in room['photo_ids'] if lookup[aid].get('local_path'))
            tours = ' '.join(f'<a href="{esc(lookup[aid]["url"])}">3D tour</a>' for aid in room['virtual_tour_ids'])
            items.append(f'<article><h3>{esc(room["name"])}</h3><p>{esc(room["price_raw"])} | period: {esc(room["price_period"])} | availability: unconfirmed</p><div class="photos">{photos}</div><p>{tours}</p></article>')
        shared = ' '.join(f'<a href="{esc(a["url"])}">{esc(a["label"])}</a>' for a in assets if a['property_id'] == building['id'] and a['kind'] == 'virtual_tour' and not a['room_type_id'])
        sections.append(f'<section><h2>{esc(building["name"])}</h2><p>{esc(building["address"])}</p><p><a href="{esc(building["source_url"])}">Source listing</a> | captured {esc(building["retrieved_at"])}</p><p>{shared}</p><div class="rooms">{"".join(items)}</div></section>')
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UniLodge housing sample</title><style>body{margin:0;background:#f5f7f8;color:#17232a;font:15px/1.5 system-ui}main{max-width:1180px;margin:auto;padding:24px}h1{font-size:28px}h2{font-size:22px}h3{font-size:18px;margin:0}section{padding:24px 0;border-top:1px solid #cbd5db}.rooms{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:20px}article{background:white;border:1px solid #d4dce0;padding:14px;border-radius:4px}.photos{display:grid;grid-template-columns:1fr 1fr;gap:8px}img{width:100%;aspect-ratio:4/3;object-fit:contain;background:#eef1f3}p{overflow-wrap:anywhere}a{color:#05695e}</style><main><h1>UniLodge housing sample</h1><p>Source-company portfolio sample. Room types, not confirmed vacant units. Marketing photos are not inspection evidence. External tours are links, not local videos. Local research preview; reuse rights remain unverified.</p>' + ''.join(sections) + '</main></html>'
    (output / 'preview.html').write_text(page, encoding='utf-8')


def process(output, download=False):
    pages = json.loads((output / 'pages.json').read_text(encoding='utf-8'))
    buildings, rooms, assets = [], [], []
    for source in pages:
        if source['id'] not in ('kensington', 'indi-sydney') or source['status'] != 200:
            continue
        b, r, a = parse_property((output / 'raw' / (source['id'] + '.html')).read_bytes(), source)
        buildings.append(b)
        rooms.extend(r)
        assets.extend(a)
    assets = list({a['id']: a for a in assets}.values())
    old_path = output / 'assets.json'
    old = {a['id']: a for a in json.loads(old_path.read_text(encoding='utf-8'))} if old_path.exists() else {}
    for a in assets:
        if a['id'] in old and old[a['id']].get('status') == 'downloaded':
            a.update({k: old[a['id']][k] for k in ('status','local_path','sha256','bytes','width','height','final_url')})
    download_error = None
    if download:
        try:
            download_photos(output, assets)
        except (ValueError, httpx.HTTPError) as exc:
            download_error = str(exc)
    for name, records in [('properties', buildings), ('room_types', rooms), ('assets', assets)]:
        write_json(output / (name + '.json'), records)
    summary = {'source_company': 'UniLodge', 'properties': len(buildings), 'room_types': len(rooms),
               'download_error': download_error,
               'asset_kinds': dict(Counter(a['kind'] for a in assets)),
               'downloaded_photos': sum(a['status'] == 'downloaded' for a in assets),
               'media_bytes': sum(a.get('bytes', 0) for a in assets),
               'local_videos': 0, 'floorplans': 0, 'real_unit_numbers': 0,
               'limitations': ['Room-type listings, not unit inventory', 'Price period and occupant basis need verification',
                               'Common listing platform does not establish common legal ownership',
                               'Copyright retained by sources; no open licence established']}
    write_json(output / 'housing-summary.json', summary)
    render_preview(output, buildings, rooms, assets)
    print(json.dumps(summary), flush=True)
    return 1 if download_error or any(a['status'] == 'failed' for a in assets) else 0


def fetch_pages(output):
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    client = Fetcher(hosts={"www.unilodge.com.au"})
    records = []
    try:
        final, status, headers, body = client.get(ORIGIN + "/robots.txt")
        if status != 200:
            raise ValueError(f"robots_http_{status}")
        (raw / "robots.txt").write_bytes(body)
        robots = RobotFileParser()
        robots.parse(body.decode().splitlines())
        for key, url in PAGES.items():
            final, status, headers, body = client.get(url, permit=lambda u: robots.can_fetch(USER_AGENT, u))
            path = raw / f"{key}.html"
            path.write_bytes(body)
            record = {"id": key, "url": url, "final_url": final, "status": status,
                      "content_type": headers.get("content-type"), "sha256": digest(body),
                      "retrieved_at": datetime.now(timezone.utc).isoformat(), "raw_path": str(path)}
            records.append(record)
            print(json.dumps(record), flush=True)
        write_json(output / "pages.json", records)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--process", type=Path, help="Parse a saved pilot directory instead of requesting pages.")
    parser.add_argument("--download-media", action="store_true", help="Fetch at most 16 page-linked photos; no video download.")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "collection-pilot" / ("housing-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
    args = parser.parse_args()
    if args.process:
        raise SystemExit(process(args.process.resolve(), args.download_media))
    else:
        fetch_pages(args.output.resolve())
        raise SystemExit(process(args.output.resolve(), args.download_media))
