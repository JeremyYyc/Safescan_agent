from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List, Tuple

import json

GUIDE_PATH = Path(__file__).resolve().parent / "quick_guide.json"

_GUIDE_CACHE: Dict[str, object] = {
    "text": None,
    "sections": None,
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "is",
    "are", "was", "were", "be", "been", "being", "as", "at", "by", "from",
    "this", "that", "these", "those", "it", "its", "your", "you", "we", "our",
}

def load_guide_text() -> str:
    if _GUIDE_CACHE.get("text") is None:
        sections = load_guide_sections()
        flattened = []
        for section in sections:
            flattened.append(section.get("title", ""))
            flattened.append(section.get("summary", ""))
            flattened.extend(section.get("items", []))
            flattened.extend(section.get("steps", []))
        _GUIDE_CACHE["text"] = "\n".join([line for line in flattened if line]).strip()
    return _GUIDE_CACHE.get("text") or ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _tokenize(text: str) -> List[str]:
    ascii_tokens = re.findall(r"[a-z0-9]+", text.lower())
    cjk_tokens = re.findall(r"[\u4e00-\u9fff]", text)
    tokens = ascii_tokens + cjk_tokens
    return [token for token in tokens if token and token not in _STOPWORDS]


def _load_guide_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"title": "Safe-Scan Quick Guide", "sections": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"title": "Safe-Scan Quick Guide", "sections": []}


def load_guide_sections() -> List[Dict[str, str]]:
    if _GUIDE_CACHE.get("sections") is None:
        data = _load_guide_json(GUIDE_PATH)
        raw_sections = data.get("sections") if isinstance(data, dict) else []
        sections: List[Dict[str, str]] = []
        if isinstance(raw_sections, list):
            for entry in raw_sections:
                if not isinstance(entry, dict):
                    continue
                section = {
                    "id": str(entry.get("id") or ""),
                    "title": str(entry.get("title") or "Quick Guide"),
                    "summary": str(entry.get("summary") or ""),
                    "items": entry.get("items") if isinstance(entry.get("items"), list) else [],
                    "steps": entry.get("steps") if isinstance(entry.get("steps"), list) else [],
                }
                section["text"] = "\n".join(
                    [
                        section["title"],
                        section["summary"],
                        *[str(item) for item in section["items"]],
                        *[str(step) for step in section["steps"]],
                    ]
                ).strip()
                sections.append(section)
        _GUIDE_CACHE["sections"] = sections
    return _GUIDE_CACHE.get("sections") or []


def _score(query: str, doc: str) -> float:
    query_norm = _normalize(query)
    doc_norm = _normalize(doc)
    if not query_norm or not doc_norm:
        return 0.0
    if query_norm in doc_norm:
        return 1.0

    q_tokens = set(_tokenize(query_norm))
    d_tokens = set(_tokenize(doc_norm))
    if not q_tokens or not d_tokens:
        return 0.0
    overlap = len(q_tokens & d_tokens)
    return overlap / max(len(q_tokens), 1)


def _search_sections(
    query: str,
    sections: List[Dict[str, str]],
    top_k: int = 2,
) -> List[Tuple[Dict[str, str], float]]:
    scored: List[Tuple[Dict[str, str], float]] = []
    for section in sections:
        score = _score(query, section.get("text", ""))
        if score > 0:
            scored.append((section, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def search_guide(query: str, top_k: int = 2) -> List[Tuple[Dict[str, str], float]]:
    return _search_sections(query, load_guide_sections(), top_k=top_k)
