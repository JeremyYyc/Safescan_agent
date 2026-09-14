import json
from pathlib import Path

from inspection_report_service.main import app


target = Path(__file__).resolve().parents[3] / "docs/backend/openapi/inspection-report-service.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
