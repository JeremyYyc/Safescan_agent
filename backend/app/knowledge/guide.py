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
    raise NotImplementedError("Use BM25 scoring via _search_sections.")


def _bm25_scores(
    query_tokens: List[str],
    doc_tokens: List[List[str]],
    k1: float = 1.5,
    b: float = 0.75,
) -> List[float]:
    if not query_tokens or not doc_tokens:
        return []

    N = len(doc_tokens)
    doc_lens = [len(tokens) for tokens in doc_tokens]
    avgdl = sum(doc_lens) / max(N, 1)

    df = {}
    for tokens in doc_tokens:
        seen = set(tokens)
        for token in seen:
            df[token] = df.get(token, 0) + 1

    idf = {}
    for token, freq in df.items():
        idf[token] = max(0.0, (N - freq + 0.5) / (freq + 0.5))

    scores = [0.0] * N
    for idx, tokens in enumerate(doc_tokens):
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        dl = doc_lens[idx]
        for token in query_tokens:
            if token not in tf:
                continue
            numerator = tf[token] * (k1 + 1)
            denom = tf[token] + k1 * (1 - b + b * (dl / max(avgdl, 1)))
            scores[idx] += idf.get(token, 0.0) * (numerator / max(denom, 1e-6))
    return scores


def _search_sections(
    query: str,
    sections: List[Dict[str, str]],
    top_k: int = 2,
) -> List[Tuple[Dict[str, str], float]]:
    query_norm = _normalize(query)
    if not query_norm:
        return []

    docs = []
    for section in sections:
        docs.append(section.get("text", ""))
    doc_tokens = [_tokenize(doc) for doc in docs]
    query_tokens = _tokenize(query_norm)
    scores = _bm25_scores(query_tokens, doc_tokens)

    scored: List[Tuple[Dict[str, str], float]] = []
    for section, score in zip(sections, scores):
        if score > 0:
            scored.append((section, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def search_guide(query: str, top_k: int = 2) -> List[Tuple[Dict[str, str], float]]:
    return _search_sections(query, load_guide_sections(), top_k=top_k)
