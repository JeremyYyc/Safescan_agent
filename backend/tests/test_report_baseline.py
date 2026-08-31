"""Pre-refactor invariants. All model calls are replaced by deterministic fixtures."""
import inspect
from app.llm_registry import get_generation_params
from app.tools.validation_tools import validate_region_data, validate_report
from app.workflow.react_loop import ReactRepairLoop
from app.workflow.agent_team import AGENT_ORDER, _format_user_attributes
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


def test_repair_policy_three_attempts_no_extra_final_validation():
    class Validator:
        calls = 0
        def validate_report(self, report):
            self.calls += 1
            return {'valid': False, 'errors': ['fixture'], 'repair_hints': ['repair']}
    class Writer:
        calls = 0
        def write_report(self, *args, **kwargs):
            self.calls += 1
            return {'version': self.calls}
    validator, writer = Validator(), Writer()
    result = ReactRepairLoop(validator, writer).execute_repair_loop({}, [], [], {}, {}, {}, {}, {})
    assert result == ({'version': 3}, False, 3)
    assert validator.calls == writer.calls == 3
