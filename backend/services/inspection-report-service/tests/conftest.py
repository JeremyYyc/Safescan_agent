import os
from pathlib import Path
import sys


SERVICE_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = SERVICE_ROOT.parents[1]
COMMON = BACKEND_ROOT / "packages" / "safescan-common" / "src"
for value in (str(SERVICE_ROOT), str(BACKEND_ROOT), str(COMMON)):
    if value not in sys.path:
        sys.path.insert(0, value)

os.environ.setdefault("INSPECTION_REPORT_DATABASE_URL", "postgresql+psycopg://x:x@localhost/report_test")
os.environ.setdefault("AUTH_SECRET", "report-test-secret-that-is-long-enough")
os.environ.setdefault("MINIO_ACCESS_KEY", "report-test")
os.environ.setdefault("MINIO_SECRET_KEY", "report-test-secret")
