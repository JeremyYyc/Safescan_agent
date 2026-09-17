import json
from pathlib import Path

from app.main import app

target = Path(__file__).parents[3] / "docs/backend/openapi/tenant-portal-api.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
)
