"""Adapter around the protected backend/app video report pipeline."""
from app.report_errors import require_report_content
from app.workflow.graph import ReportServices

from .repository import ReportRepository


class ReportPipelineServices(ReportServices):
    def __init__(self, repository: ReportRepository, job: dict, storage_backend) -> None:
        super().__init__()
        self.repository = repository
        self.job = job
        self.storage_backend = storage_backend

    def authorize(self, state):
        # API authorization and file/report binding were persisted before claim.
        self.storage_backend.record(state["video_asset_id"])
        return {}

    def title(self, state):
        # The property API already owns the user-visible title; report JSON title
        # remains produced by the unchanged writer.
        return {}

    def persist(self, state):
        require_report_content(state.get("draft_report"))
        report_id = self.repository.persist_pipeline_result(
            self.job,
            state["draft_report"],
            state["draft_report"].get("regions", []) or [],
            state.get("representative_images", []) or [],
            bool(state.get("validation", {}).get("valid")),
        )
        return {"report_id": report_id}
