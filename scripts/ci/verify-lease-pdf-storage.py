#!/usr/bin/env python3
"""Read-only audit of every lease document's current private MinIO PDF.

Execute inside the property service (which already has its DB and MinIO env):
  docker exec -i safescan_agent-property-leasing-service-1 python - \
    --expected-leases 1880 --expected-documents 1880 < scripts/ci/verify-lease-pdf-storage.py

Only read-only SQL, S3 HEAD and S3 GET are used. Missing files are reported, never
generated. Checks cover the exact current renderer/data/template object key,
content type, document/terms metadata, complete content SHA-256, PDF magic and
page count. Output contains counts and document UUIDs, not renter information.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
from io import BytesIO
import json
import sys

from minio.error import S3Error
from pypdf import PdfReader
import sqlalchemy as sa

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.tables import Lease, LeaseDocument
from app.services.lease_pdf import LeasePdfStore, RENDERER_VERSION, TEMPLATE_DIR, build_record


@lru_cache(maxsize=5)
def template_for(state):
    content = (TEMPLATE_DIR / f"{state.lower()}.pdf").read_bytes()
    return content, len(PdfReader(BytesIO(content)).pages)


def expected_key(record):
    # Deliberately calculate the lookup without calling ensure(): that method
    # repairs missing objects and must never be used by a read-only verifier.
    template, _ = template_for(record["state"])
    fingerprint = hashlib.sha256(
        RENDERER_VERSION.encode()
        + json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        + template
    ).hexdigest()
    return (f"lease-contracts/{record['lease_id']}/{record['document_id']}/"
            f"v{record['document_version']}-{fingerprint}.pdf")


def verify_object(store, record):
    key = expected_key(record)
    info = store.client.stat_object(store.bucket, key)
    metadata = {key.lower(): value for key, value in info.metadata.items()}
    expected_metadata = {
        "x-amz-meta-document-id": record["document_id"],
        "x-amz-meta-terms-digest": record["terms_digest"],
        "x-amz-meta-renderer": RENDERER_VERSION,
    }
    if info.content_type != "application/pdf":
        raise ValueError("content_type")
    if any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise ValueError("document_metadata")
    response = store.client.get_object(store.bucket, key)
    try:
        content = response.read()
    finally:
        response.close()
        response.release_conn()
    if len(content) != info.size or not content.startswith(b"%PDF-"):
        raise ValueError("pdf_magic_or_size")
    if hashlib.sha256(content).hexdigest() != metadata.get("x-amz-meta-sha256"):
        raise ValueError("content_digest")
    pages = len(PdfReader(BytesIO(content)).pages)
    if pages <= template_for(record["state"])[1]:
        raise ValueError("missing_personalized_pages")
    return len(content), pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-leases", type=int)
    parser.add_argument("--expected-documents", type=int)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("batch size must be positive")
    store = LeasePdfStore(get_settings())
    factory = get_session_factory()
    with factory() as db:
        db.execute(sa.text("SET TRANSACTION READ ONLY"))
        leases = db.scalar(sa.select(sa.func.count()).select_from(Lease))
        documents = db.scalar(sa.select(sa.func.count()).select_from(LeaseDocument))
        missing_documents = db.scalar(sa.select(sa.func.count()).select_from(Lease).where(
            ~sa.exists(sa.select(LeaseDocument.id).where(LeaseDocument.lease_id == Lease.id))))
    counts = Counter()
    by_state = defaultdict(Counter)
    lease_states = Counter()
    failures = []
    after_id = 0
    while True:
        with factory() as db:
            db.execute(sa.text("SET TRANSACTION READ ONLY"))
            rows = db.execute(sa.select(LeaseDocument, Lease).join(
                Lease, Lease.id == LeaseDocument.lease_id).where(LeaseDocument.id > after_id)
                .order_by(LeaseDocument.id).limit(args.batch_size)).all()
            if not rows:
                break
            for document, lease in rows:
                counts["scanned"] += 1
                lease_states[lease.status] += 1
                state = "unknown"
                try:
                    record = build_record(db, lease, document)
                    state = record["state"]
                    by_state[state]["scanned"] += 1
                    size, pages = verify_object(store, record)
                    counts["verified"] += 1
                    counts["bytes"] += size
                    by_state[state]["verified"] += 1
                    by_state[state]["pages"] += pages
                except Exception as exc:
                    counts["failed"] += 1
                    by_state[state]["failed"] += 1
                    if len(failures) < 20:
                        failures.append({"document_id": str(document.public_id),
                                         "state": state,
                                         "reason": exc.code if isinstance(exc, S3Error) else type(exc).__name__})
                after_id = document.id
        print(json.dumps({"progress": counts["scanned"], "verified": counts["verified"],
                          "failed": counts["failed"]}), flush=True)
    expectations_match = ((args.expected_leases is None or leases == args.expected_leases)
                          and (args.expected_documents is None or documents == args.expected_documents))
    complete = (counts["failed"] == 0 and counts["scanned"] == documents
                and counts["verified"] == documents and missing_documents == 0 and expectations_match)
    print(json.dumps({"read_only": True, "renderer": RENDERER_VERSION,
                      "leases": leases, "documents": documents,
                      "leases_without_documents": missing_documents, "counts": dict(counts),
                      "by_state": {state: dict(values) for state, values in sorted(by_state.items())},
                      "document_lease_states": dict(lease_states), "failures": failures,
                      "complete": complete}, ensure_ascii=False), flush=True)
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
