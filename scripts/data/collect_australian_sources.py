#!/usr/bin/env python3
"""Collect public listing facts, without inventing missing fields (stdlib only).

HTML snapshots are cached outside the repository. No login, booking or contact
actions are performed. Failed/blocked pages remain in collection_log.json.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class Node:
    def __init__(self, tag="root", attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def nodes(self, tag=None, cls=None):
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and (cls is None or cls in child.attrs.get("class", "").split()):
                    yield child
                yield from child.nodes(tag, cls)

    def text(self):
        if self.tag in ("script", "style", "noscript", "svg"):
            return ""
        return " ".join(x.text() if isinstance(x, Node) else x for x in self.children).strip()


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        if data.strip():
            self.current.children.append(data.strip())


def clean(value):
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def structured(source):
    for match in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', source, re.S):
        try:
            data = json.loads(match[1])
        except ValueError:
            continue
        for row in data if isinstance(data, list) else [data]:
            yield from row.get("@graph", [row])


def image_links(node, base):
    result = []
    for img in node.nodes("img"):
        src = img.attrs.get("data-src") or img.attrs.get("src", "")
        if src.startswith("data:") or not src or re.search(r"logo|icon|flag|avatar|\.svg(?:\?|$)", src, re.I):
            continue
        src = urljoin(base, src)
        if src not in [x["url"] for x in result]:
            result.append({"url": src, "alt": clean(img.attrs.get("alt", "")), "role": "marketing_image", "rights_status": "unknown"})
    return result


def studentone_images(doc, url, slug):
    location = slug.split("-")[0]
    images = [i for i in image_links(doc.root, url) if "cdn.sanity.io" in i["url"]]
    related = [i for i in images if location in i["alt"].lower() and "facilit" in i["alt"].lower()]
    # Shared site navigation can contain photographs of a different residence.
    return related[:10]


class Collector:
    def __init__(self, cache):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.log = []

    def fetch(self, url):
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".html")
        try:
            cached = path.exists()
            if cached:
                body = path.read_bytes()
            else:
                time.sleep(0.25)
                with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; SafeScanResearch/1.0)"}), timeout=40) as response:
                    body = response.read(12_000_000)
                path.write_bytes(body)
            self.log.append({"url": url, "status": "ok", "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "cached": cached})
            return body.decode("utf-8", errors="replace")
        except Exception as error:
            self.log.append({"url": url, "status": "unavailable", "error": str(error)})
            return None

    def many(self, urls):
        with ThreadPoolExecutor(max_workers=3) as pool:
            return list(zip(urls, pool.map(self.fetch, urls)))


def base_record(url, provider, name, address, city, region, source, geo=None):
    if isinstance(address, dict):
        address = clean(", ".join(str(address[k]) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode") if address.get(k)))
    return {"id": "au-20261031:" + hashlib.sha256(url.rstrip("/").encode()).hexdigest()[:20],
            "provider": provider, "name": clean(name), "city": city, "region": region,
            "address": clean(address) or None, "source_url": url, "geo": geo,
            "retrieved_on": "2026-10-31", "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "record_type": "building", "dataset_type": "student", "images": [], "room_types": [],
            "provenance": "public_listing", "unknown_fields_policy": "null; never filled as observed facts"}


def scape_record(url, source):
    schemas = list(structured(source))
    entry = next((x for x in schemas if "ApartmentComplex" in x.get("@type", [])), None)
    if not entry or not entry.get("address"):
        return None
    city = urlparse(url).path.split("/")[1].title()
    region = {"Sydney": "NSW", "Melbourne": "VIC", "Brisbane": "QLD", "Adelaide": "SA"}.get(city)
    row = base_record(url, "Scape", entry["name"], entry["address"], city, region, source, entry.get("geo"))
    doc = Document(source)
    for card in doc.root.nodes(cls="property-card"):
        title = next(card.nodes(cls="title"), None)
        detail = re.search(r"(\d+) Person\s*\|\s*(\d+) Bathroom\s*\|\s*Approx\.\s*([\d.]+) m²", card.text())
        if title is None or detail is None:
            continue
        name = clean(title.text())
        room_url = next((a.attrs["href"] for a in card.nodes("a") if a.attrs.get("aria-label") == "Explore Room"), url)
        beds = re.search(r"(\d+) Bed", name, re.I)
        row["room_types"].append({"name": name, "source_url": room_url,
            "bedrooms": int(beds[1]) if beds else (0 if "studio" in name.lower() else None),
            "bathrooms": int(detail[2]), "max_people": int(detail[1]),
            "area_sqm": float(detail[3]), "area_scope": "advertised_room_area; not whole shared apartment",
            "rent_basis": "person_per_week", "weekly_rent": None,
            "images": image_links(card, url)[:5]})
    # Property-specific hero from structured data, never navigation room photographs.
    if isinstance(entry.get("image"), str):
        row["images"] = [{"url": entry["image"], "role": "building_marketing", "rights_status": "unknown"}]
    row["features"] = [clean(x["name"]) for x in entry.get("amenityFeature", []) if x.get("value")]
    return row


def unilodge_record(url, source):
    entries = list(structured(source))
    entry = next((x for x in entries if x.get("@type") == "LocalBusiness" and x.get("address")), None)
    if not entry:
        return None
    city = urlparse(url).path.split("/")[1].replace("student-accommodation-", "").title()
    region = {"Brisbane": "QLD", "Sydney": "NSW", "Melbourne": "VIC", "Adelaide": "SA", "Perth": "WA", "Canberra": "ACT"}.get(city)
    row = base_record(url, "UniLodge", entry["name"], entry["address"], city, region, source, entry.get("geo"))
    if isinstance(entry.get("image"), str):
        row["images"] = [{"url": entry["image"], "role": "building_marketing", "rights_status": "unknown"}]
    doc = Document(source)
    seen = set()
    for a in doc.root.nodes("a"):
        href, name = a.attrs.get("href", ""), clean(a.text())
        if ("categoryInfo" not in href and "/rooms-apartments/" not in href) or not name or len(name) > 110:
            continue
        if name.lower() in {"apply now", "view room", "book now", "learn more", "read more"} or name in seen:
            continue
        seen.add(name)
        beds = re.search(r"(\d+)\s*(?:bed|bedroom)", name, re.I)
        row["room_types"].append({"name": name, "source_url": urljoin(url, href),
            "bedrooms": int(beds[1]) if beds else (0 if "studio" in name.lower() else None),
            "bathrooms": None, "max_people": None, "area_sqm": None, "area_scope": "unknown",
            "weekly_rent": None, "rent_basis": "unknown", "images": []})
    return row


def raywhite_record(url, source):
    entry = next((x for x in structured(source) if x.get("@type") == "Place" and x.get("address")), None)
    if not entry:
        return None
    address = entry["address"]
    region = address.get("addressRegion")
    row = base_record(url, "Ray White", clean(entry["name"]).split(" - ", 1)[-1], address,
                      address.get("addressLocality"), region, source, entry.get("geo"))
    row.update(record_type="specific_property", dataset_type="general")
    body = clean(Document(source).root.text())
    dimensions = re.search(r"(\d+)\s+Beds?\s+(\d+)\s+Baths?(?:\s+(\d+)\s+Cars?)?", body)
    if not dimensions:
        return None
    price = re.search(r"\$([\d,]+)(?:\.\d+)?\s*(?:Per Week|per week|pw|p/w)", body, re.I)
    images = [x for x in image_links(Document(source).root, url) if "rw-propertyimages" in x["url"]]
    if not images and entry.get("image"):
        images = [{"url": entry["image"], "role": "property_marketing", "rights_status": "unknown"}]
    row["images"] = images[:10]
    row["room_types"] = [{"name": "Entire property", "source_url": url, "bedrooms": int(dimensions[1]),
        "bathrooms": int(dimensions[2]), "parking_spaces": int(dimensions[3]) if dimensions[3] else None,
        "area_sqm": None, "area_scope": "unknown", "max_people": None,
        "weekly_rent": int(price[1].replace(",", "")) if price else None,
        "rent_basis": "property_per_week", "images": images[:10]}]
    # Preserve listing availability as a fact separate from synthetic historical occupancy.
    row["listed_available_from"] = next((e.get("startDate") for e in entry.get("event", []) if e.get("name") == "Available"), None)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", default="/tmp/safescan-public-pages-20261031")
    args = parser.parse_args()
    collector = Collector(args.cache)
    scape = collector.fetch("https://www.scape.com.au/brisbane/")
    urls = sorted({urljoin("https://www.scape.com.au", a.attrs["href"]).rstrip("/") + "/"
        for a in Document(scape or "").root.nodes("a")
        if re.fullmatch(r"(?:https://www.scape.com.au)?/(sydney|melbourne|brisbane|adelaide)/[^/?#]+/?", a.attrs.get("href", ""))})
    rows = []
    for url, source in collector.many(urls):
        if source and (row := scape_record(url, source)):
            rows.append(row)
    print("Scape:", len(rows), flush=True)
    unilodge_urls = []
    for city in ("brisbane", "melbourne", "adelaide", "perth"):
        root = "https://www.unilodge.com.au/student-accommodation-" + city
        source = collector.fetch(root)
        links = sorted({urljoin(root, a.attrs["href"]).rstrip("/") for a in Document(source or "").root.nodes("a")
            if re.fullmatch(r"(?:https://www.unilodge.com.au)?/student-accommodation-" + city + r"/[^/?#]+/?", a.attrs.get("href", ""))})
        unilodge_urls.extend(links[:16 if city == "brisbane" else 8])
    for url, source in collector.many(unilodge_urls):
        if source and (row := unilodge_record(url, source)):
            rows.append(row)
    print("With UniLodge:", len(rows), flush=True)
    for slug, address in (("adelaide-street", "363 Adelaide Street, Brisbane City QLD 4000"),
                          ("wharf-street", "38 Wharf Street, Brisbane City QLD 4000"),
                          ("elizabeth-street", "97 Elizabeth Street, Brisbane City QLD 4000")):
        url = "https://studentone.com/location/" + slug
        source = collector.fetch(url)
        if not source:
            continue
        doc = Document(source)
        row = base_record(url, "Student One", "Student One " + slug.replace("-", " ").title(), address, "Brisbane", "QLD", source)
        row["address_source_url"] = "https://studentone.com/help/faqs"
        row["images"] = studentone_images(doc, url, slug)
        # Names only, restricted to headings in this location page.
        for heading in list(doc.root.nodes("h3")) + list(doc.root.nodes("h4")):
            name = clean(heading.text())
            if re.search(r"studio|bedroom|bed apartment", name, re.I) and len(name) < 80:
                row["room_types"].append({"name": name, "source_url": url, "bedrooms": 0 if "studio" in name.lower() else None,
                    "bathrooms": None, "area_sqm": None, "area_scope": "unknown", "weekly_rent": None, "rent_basis": "person_per_week", "images": []})
        rows.append(row)
    collector.fetch("https://studentone.com/help/faqs")
    ray_urls = set()
    for host in ("raywhiteakg.com.au", "raywhitecitysouth.com.au", "raywhiteoakleigh.com.au", "raywhiteparramatta.com.au"):
        url = "https://" + host + "/properties/residential-for-rent"
        source = collector.fetch(url)
        links = sorted({urljoin(url, a.attrs["href"]) for a in Document(source or "").root.nodes("a")
                        if re.search(r"/properties/residential-for-rent/(?:qld|nsw|vic)/[^/]+/(?:house|apartment|unit|townhouse|studio|villa)/\d+", a.attrs.get("href", ""))})
        ray_urls.update(links[:12])
    ray_urls.add("https://raywhiteakg.com.au/properties/residential-for-rent/qld/regents-park-4118/house/3599145")
    for url, source in collector.many(sorted(ray_urls)):
        if source and (row := raywhite_record(url, source)):
            rows.append(row)
    # A normal access attempt is logged; do not retry or bypass access restrictions.
    collector.fetch("https://www.realestate.com.au/rent/in-brisbane+city,+qld+4000/list-1")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "public_sources.json").write_text(json.dumps(sorted(rows, key=lambda r: r["id"]), ensure_ascii=False, indent=2) + "\n")
    (args.output / "collection_log.json").write_text(json.dumps({"collected_at": datetime.now(timezone.utc).isoformat(),
        "requests": sorted(collector.log, key=lambda r: r["url"])}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"records": len(rows), "room_types": sum(len(r["room_types"]) for r in rows),
                      "providers": {p: sum(r["provider"] == p for r in rows) for p in sorted({r["provider"] for r in rows})}}))


if __name__ == "__main__":
    main()
