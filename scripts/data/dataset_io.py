"""Small, dependency-free readers for the existing standard-conforming SQL export."""
import hashlib
import json
from pathlib import Path
import re


def read_export(path, table):
    source = Path(path).read_text(encoding="utf-8")
    pattern = re.compile(r"INSERT INTO collected_data\." + re.escape(table) + r" \(([^)]+)\) VALUES \(")
    rows = []
    for match in pattern.finditer(source):
        pos, values = match.end(), []
        while True:
            while source[pos].isspace() or source[pos] == ",":
                pos += 1
            if source[pos] == ")":
                break
            if source[pos] == "'":
                pos += 1
                value = []
                while True:
                    if source[pos] == "'":
                        if source[pos + 1] == "'":
                            value.append("'")
                            pos += 2
                            continue
                        pos += 1
                        break
                    value.append(source[pos])
                    pos += 1
                values.append("".join(value))
            else:
                end = pos
                while source[end] not in ",)":
                    end += 1
                token = source[pos:end].strip()
                values.append({"NULL": None, "true": True, "false": False}.get(token, token))
                pos = end
        columns = [c.strip() for c in match[1].split(",")]
        if len(columns) != len(values):
            raise ValueError(f"Malformed {table}: {len(columns)} columns / {len(values)} values")
        row = dict(zip(columns, values))
        for key in ("metadata", "address", "license_info"):
            if row.get(key) is not None:
                row[key] = json.loads(row[key])
        for key in ("byte_size", "width", "height", "step_number", "english_words"):
            if row.get(key) is not None:
                row[key] = int(row[key])
        rows.append(row)
    return rows


def canonical_address(value):
    if isinstance(value, dict):
        value = " ".join(str(value.get(k, "")) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode"))
    value = re.sub(r"\b(?:australia|au)\b", "", (value or "").lower())
    aliases = {"street": "st", "road": "rd", "avenue": "ave", "drive": "dr", "terrace": "tce", "court": "ct"}
    return re.sub(r"[^a-z0-9]", "", " ".join(aliases.get(w, w) for w in re.findall(r"[a-z0-9]+", value)))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    with Path(path).open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
