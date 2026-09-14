from app.workflow.graph import ReportServices

from inspection_report_service.pipeline_adapter import ReportPipelineServices


def test_adapter_inherits_every_protected_video_and_report_policy_step() -> None:
    # Characterization guard: the service adapter may replace only authorization,
    # title and persistence. Video selection, prompts, scoring, validation, repair
    # and evidence association must remain the exact existing implementations.
    protected = {
        "extract", "filter", "select", "detect", "scene", "router", "hazard",
        "comfort", "compliance", "scoring", "recommendations", "write",
        "validate", "repair", "evidence",
    }
    assert protected.isdisjoint(ReportPipelineServices.__dict__)
    for name in protected:
        assert getattr(ReportPipelineServices, name) is getattr(ReportServices, name)


def test_adapter_does_not_define_a_pdf_renderer() -> None:
    assert "render_report_pdf" not in ReportPipelineServices.__dict__
