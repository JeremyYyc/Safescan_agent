import pytest
from app.services.maintenance import OPEN_STATES, TRANSITIONS

pytestmark = pytest.mark.unit


def test_frozen_state_machine():
    assert TRANSITIONS == {
        "open": {"cancelled"},
        "assigned": {"in_progress", "cancelled"},
        "in_progress": {"blocked", "completed", "cancelled"},
        "blocked": {"in_progress", "completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }
    assert OPEN_STATES == {"open", "assigned", "in_progress", "blocked"}
