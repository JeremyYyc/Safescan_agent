"""Bounded, offline collection of the reviewed NSW source list."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
USER_AGENT = "SafeScanResearch/0.1"
HOSTS = {"www.fire.nsw.gov.au", "www.nsw.gov.au"}
MAX_BYTES = 5 * 1024 * 1024


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def allowed(url: str, hosts=None) -> bool:
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname in (HOSTS if hosts is None else hosts)
            and parsed.port in (None, 443) and not parsed.username and not parsed.password)


class Fetcher:
    def __init__(self, hosts=None):
        self.hosts = HOSTS if hosts is None else set(hosts)
        self.client = httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
        self.attempts = 0
        self.total_bytes = 0
        self.last_request = {}
        self.stopped = set()

    def close(self):
        self.client.close()

    def get(self, url: str, permit=None):
        for _ in range(6):
            if not allowed(url, self.hosts):
                raise ValueError("redirect_or_url_outside_allowlist")
            if permit is not None and not permit(url):
                raise ValueError("robots_disallowed_or_redirect_unverified")
            host = urlsplit(url).hostname
            if host in self.stopped:
                raise ValueError("host_stopped")
            for retry in range(3):
                if self.attempts >= 30 or self.total_bytes >= 50 * 1024 * 1024:
                    raise ValueError("run_budget_exhausted")
                time.sleep(max(0, 2 - (time.monotonic() - self.last_request.get(host, 0))))
                self.last_request[host] = time.monotonic()
                self.attempts += 1
                try:
                    with self.client.stream("GET", url) as response:
                        body = bytearray()
                        for part in response.iter_bytes():
                            self.total_bytes += len(part)
                            if len(body) + len(part) > MAX_BYTES or self.total_bytes > 50 * 1024 * 1024:
                                raise ValueError("response_budget_exceeded")
                            body.extend(part)
                        status, headers = response.status_code, dict(response.headers)
                    if status == 403:
                        self.stopped.add(host)
                        raise ValueError("host_forbidden")
                    if status == 429:
                        # Stop rather than retry before an arbitrary Retry-After deadline.
                        self.stopped.add(host)
                        raise ValueError("host_rate_limited_retry_after=" + headers.get("retry-after", "unknown"))
                    if status >= 500 and retry < 2:
                        continue
                    break
                except httpx.TransportError:
                    if retry == 2:
                        raise
            if status in (301, 302, 303, 307, 308):
                url = urljoin(url, headers.get("location", ""))
                continue
            return url, status, headers, bytes(body)
        raise ValueError("too_many_redirects")


def extract(body: bytes, url: str) -> dict:
    soup = BeautifulSoup(body, "html.parser")
    root = soup.select_one("main") or soup.select_one('[role="main"]') or soup.select_one("article")
    warnings = []
    if root is None:
        root = soup.body or soup
        warnings.append("main_container_missing")
    heading = root.find("h1") or soup.find("h1") or soup.title
    title = heading.get_text(" ", strip=True) if heading else ""
    rights = []
    for link in soup.find_all("a", href=True):
        label = link.get_text(" ", strip=True).lower()
        if any(word in label for word in ("copyright", "license", "licence", "terms of use")):
            rights.append(urljoin(url, link["href"]))
    dates = {}
    for key, names in {
        "published_at": ("article:published_time", "datePublished", "dcterms.created"),
        "source_updated_at": ("article:modified_time", "dateModified", "dcterms.modified"),
    }.items():
        dates[key] = None
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                dates[key] = tag["content"]
                break
    for node in root.select("script, style, nav, footer, header, form, button, noscript, .breadcrumb, .breadcrumbs, .nsw-socials"):
        node.decompose()
    sections = []
    current = {"heading": title, "heading_path": [title], "blocks": []}
    heading_stack = []
    for node in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
        if node.name in ("p", "li") and node.find_parent(["li", "td", "th"]):
            continue
        text = " ".join(node.get_text(" ", strip=True).split())
        if not text:
            continue
        if node.name.startswith("h") and node.name != "th":
            if current["blocks"]:
                sections.append(current)
            level = int(node.name[1])
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
            current = {"heading": text, "heading_path": [h[1] for h in heading_stack], "blocks": []}
        else:
            current["blocks"].append({"type": "list_item" if node.name == "li" else "paragraph", "text": text,
                                      "links": [{"text": a.get_text(" ", strip=True), "url": urljoin(url, a["href"])} for a in node.find_all("a", href=True)]})
    if current["blocks"]:
        sections.append(current)
    sections = [s for s in sections if s["heading"] not in {"Related information", "Related rules and guidance"}]
    content = "\n\n".join(" > ".join(s["heading_path"]) + "\n" + "\n".join(b["text"] for b in s["blocks"]) for s in sections)
    if len(content) < 300:
        warnings.append("short_content")
    if not title:
        warnings.append("missing_title")
    return {"title": title, "sections": sections, "content_text": content,
            "rights_url": sorted(set(rights)), "extraction_warnings": warnings, **dates}


def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect(output: Path, source_ids=None):
    sources = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
    if source_ids:
        unknown = set(source_ids) - {s["id"] for s in sources}
        if unknown:
            raise ValueError(f"unknown_source_ids: {sorted(unknown)}")
        sources = [s for s in sources if s["id"] in source_ids]
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    fetcher = Fetcher()
    robots = {}
    outcomes, documents = [], []
    try:
        for source in sources:
            url, sid = source["url"], source["id"]
            try:
                origin = "https://" + urlsplit(url).netloc
                if origin not in robots:
                    _, status, _, body = fetcher.get(origin + "/robots.txt")
                    (raw / (urlsplit(url).hostname + ".robots.txt")).write_bytes(body)
                    if status != 200:
                        raise ValueError(f"robots_unverified_http_{status}")
                    parser = RobotFileParser()
                    parser.parse(body.decode("utf-8", errors="replace").splitlines())
                    robots[origin] = parser
                if not robots[origin].can_fetch(USER_AGENT, url):
                    raise ValueError("robots_disallowed")
                def permit(target):
                    target_origin = "https://" + urlsplit(target).netloc
                    return target_origin in robots and robots[target_origin].can_fetch(USER_AGENT, target)
                final, status, headers, body = fetcher.get(url, permit=permit)
                if status != 200:
                    raise ValueError(f"http_{status}")
                if "text/html" not in headers.get("content-type", ""):
                    raise ValueError("non_html_pending")
                (raw / f"{sid}.html").write_bytes(body)
                fields = extract(body, final)
                record = {"document_id": sid, "source_id": sid, "source_url": url,
                          "final_url": final, "publisher": source["publisher"],
                          "document_type": source["document_type"], "topics": source["topics"],
                          "jurisdiction": "AU-NSW", "language": "en",
                          "retrieved_at": datetime.now(timezone.utc).isoformat(),
                          "http_status": status, "content_type": headers.get("content-type"),
                          "etag": headers.get("etag"), "last_modified": headers.get("last-modified"),
                          "raw_sha256": digest(body), "text_sha256": digest(fields["content_text"].encode()),
                          "rights_status": "pending_review", "review_status": "pending_review",
                          "provenance_type": "official_publication", **fields}
                record["extractor_version"] = "1.1"
                documents.append(record)
                outcomes.append({"source_id": sid, "status": "collected", "characters": len(fields["content_text"]), "warnings": fields["extraction_warnings"]})
            except (ValueError, httpx.HTTPError) as exc:
                outcomes.append({"source_id": sid, "status": "failed", "error": str(exc)})
            print(json.dumps(outcomes[-1]), flush=True)
    finally:
        fetcher.close()
    (output / "documents.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in documents), encoding="utf-8")
    # Shared index keeps stable identities and unique content versions across runs.
    index_path = output.parent / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    new_versions = 0
    for doc in documents:
        versions = index.setdefault(doc["document_id"], [])
        if doc["text_sha256"] not in versions:
            versions.append(doc["text_sha256"])
            new_versions += 1
    write_json(index_path, index)
    summary = {"outcomes": outcomes, "attempts": fetcher.attempts, "bytes": fetcher.total_bytes,
               "collected": len(documents), "new_versions": new_versions,
               "failed": len(sources) - len(documents), "published": 0}
    write_json(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", action="append", help="Collect only named source IDs; repeatable.")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "collection-pilot" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    args = parser.parse_args()
    if args.dry_run:
        print((HERE / "sources.json").read_text(encoding="utf-8"))
        print("Limits: 30 attempts, 50 MiB/run, 5 MiB/response, >=2s/host; no publishing.")
    else:
        raise SystemExit(collect(args.output.resolve(), args.source))
