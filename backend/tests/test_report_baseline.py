"""Pre-refactor invariants. All model calls are replaced by deterministic fixtures."""
import inspect
from app.llm_registry import get_generation_params
from app.tools.validation_tools import validate_region_data, validate_report
from app.workflow.role_policy import AGENT_ORDER, _format_user_attributes
from app.tools.video_tools import filter_frames_with_stats


def test_generation_policy():
    assert [get_generation_params(t) for t in ('L1', 'L2', 'L3', 'VL')] == [
        {'temperature': .2, 'top_p': .8}, {'temperature': .4, 'top_p': .85},
        {'temperature': .35, 'top_p': .85}, {'temperature': .3, 'top_p': .85}]


def test_region_contract():
    region = dict(regionName=['Kitchen'], potentialHazards=['fire'],
                  colorAndLightingEvaluation=['bright'], suggestions=['clear stove'],
                  scores=[0, 1, 2, 3, 5])
    assert validate_region_data(region)[0]
    region['scores'] = [6, 1, 2, 3, 5]
    assert not validate_region_data(region)[0]
    assert not validate_report({'regions': []})['valid']


def test_filter_thresholds():
    params = inspect.signature(filter_frames_with_stats).parameters
    assert [params[k].default for k in ('hamming_distance_threshold', 'blur_threshold', 'brightness_threshold')] == [25, 50, 50.0]


def test_role_policy():
    assert AGENT_ORDER == ['HazardAgent', 'ComfortAgent', 'ComplianceAgent', 'ScoringAgent', 'RecommendationAgent', 'ReportWriterAgent']
    assert _format_user_attributes({'isChildren': True, 'isPets': True}) == 'Children, Pets.'



# The original three-attempt/no-extra-validation invariant is now exercised
# against the actual graph in test_graph.test_three_repairs_without_extra_final_validation.
