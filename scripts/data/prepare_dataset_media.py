#!/usr/bin/env python3
"""Download a bounded set of source marketing images and retain baseline objects."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time
from urllib.request import Request, urlopen
from urllib.parse import quote

from dataset_io import write_json


def image_info(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png", *struct.unpack(">II", data[16:24])
    if data[:3] == b"\xff\xd8\xff":
        pos = 2
        while pos + 9 < len(data):
            if data[pos] != 255:
                pos += 1
                continue
            while data[pos] == 255:
                pos += 1
            marker = data[pos]
            pos += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            size = int.from_bytes(data[pos:pos + 2], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[pos + 3:pos + 7])
                return "image/jpeg", "jpg", width, height
            if size < 2:
                break
            pos += size
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8X":
            return "image/webp", "webp", 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width, height = struct.unpack("<HH", data[26:30])
            return "image/webp", "webp", width & 0x3FFF, height & 0x3FFF
        if data[12:16] == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            return "image/webp", "webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise ValueError("Unsupported or invalid image format")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("/tmp/safescan-marketing-images-20261031"))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    (args.output / "objects").mkdir(parents=True, exist_ok=True)
    objects = json.loads((args.baseline / "objects.json").read_text())
    for row in objects:
        path = args.baseline / row["local_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Baseline object mismatch: " + str(path))
        shutil.copyfile(path, args.output / row["local_path"])
    candidates = {}
    for record in json.loads(args.sources.read_text()):
        groups = [(record["images"][:2], None)] + [(room.get("images", [])[:2], room["name"]) for room in record["room_types"]]
        for images, room_name in groups:
            for image in images:
                ref = {"housing_id": record["id"], "room_type": room_name,
                       "role": "room_type_marketing" if room_name else "building_marketing"}
                candidates.setdefault(image["url"], []).append(ref)

    def get(url):
        cache = args.cache / hashlib.sha256(url.encode()).hexdigest()
        try:
            if cache.exists():
                data = cache.read_bytes()
            else:
                time.sleep(0.2)
                encoded_url = quote(url, safe=":/?&=%#@+;,$!()*'[]~-._")
                with urlopen(Request(encoded_url, headers={"User-Agent": "Mozilla/5.0 (compatible; SafeScanResearch/1.0)"}), timeout=35) as response:
                    data = response.read(8_000_001)
                if len(data) > 8_000_000:
                    raise ValueError("Image exceeds 8 MB collection limit")
                cache.write_bytes(data)
            mime, ext, width, height = image_info(data)
            if min(width, height) < 120:
                raise ValueError("Image is too small")
            sha = hashlib.sha256(data).hexdigest()
            local = "objects/" + sha + "." + ext
            (args.output / local).write_bytes(data)
            return {"url": url, "status": "ok", "id": sha, "mime_type": mime, "byte_size": len(data),
                    "width": width, "height": height, "local_path": local, "refs": candidates[url]}
        except Exception as error:
            return {"url": url, "status": "unavailable", "error": str(error), "refs": candidates[url]}

    log, by_sha = [], {r["sha256"]: r for r in objects}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, row in enumerate(pool.map(get, sorted(candidates)), 1):
            log.append(row)
            if row["status"] == "ok" and row["id"] not in by_sha:
                item = {"sha256": row["id"], "bucket": "safescan-media",
                        "object_key": "datasets/au-execution-20261031/images/" + Path(row["local_path"]).name,
                        "local_path": row["local_path"], "byte_size": row["byte_size"], "content_type": row["mime_type"]}
                by_sha[row["id"]] = item
                objects.append(item)
            if index % 100 == 0:
                print("Images checked:", index, "/", len(candidates), flush=True)
    write_json(args.output / "media_collection_log.json", log)
    write_json(args.output / "objects.json", objects)
    expected_paths = {r["local_path"] for r in objects}
    for old in (args.output / "objects").iterdir():
        if old.is_file() and "objects/" + old.name not in expected_paths:
            old.unlink()
    print(json.dumps({"total_objects": len(objects), "new_unique_objects": len(objects) - 339,
                      "failed_urls": sum(r["status"] != "ok" for r in log)}))


if __name__ == "__main__":
    main()
