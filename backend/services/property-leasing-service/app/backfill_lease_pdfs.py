"""Idempotently materialize every lease document in private MinIO storage.

Run once: python -m app.backfill_lease_pdfs
Keep future/changed documents materialized: python -m app.backfill_lease_pdfs --watch
No signed terms, document UUIDs or business rows are modified.
"""

import argparse
import json
import logging
import time

import sqlalchemy as sa

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.tables import Lease, LeaseDocument
from app.services.lease_pdf import LeasePdfStore, build_record


LOGGER = logging.getLogger(__name__)


def backfill(*, batch_size: int = 100, store=None, session_factory=None) -> dict:
    store = store or LeasePdfStore(get_settings())
    factory = session_factory or get_session_factory()
    result = {"scanned": 0, "generated": 0, "existing": 0, "failed": 0}
    after_id = 0
    while True:
        with factory() as db:
            rows = db.execute(sa.select(LeaseDocument, Lease).join(
                Lease, Lease.id == LeaseDocument.lease_id).where(LeaseDocument.id > after_id)
                .order_by(LeaseDocument.id).limit(batch_size)).all()
            if not rows:
                break
            for document, lease in rows:
                result["scanned"] += 1
                try:
                    _, created = store.ensure(build_record(db, lease, document))
                    result["generated" if created else "existing"] += 1
                except Exception:
                    result["failed"] += 1
                    LOGGER.exception("Could not materialize lease document %s", document.public_id)
                after_id = document.id
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=300)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if args.batch_size < 1 or args.interval < 1:
        parser.error("batch size and interval must be positive")
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            result = backfill(batch_size=args.batch_size)
            print(json.dumps(result), flush=True)
            if not args.watch:
                raise SystemExit(1 if result["failed"] else 0)
        except Exception:
            if not args.watch:
                raise
            LOGGER.exception("Lease PDF backfill pass failed; retrying")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
