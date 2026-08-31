import pytest
from app.workflow import chat_graph as graph


@pytest.mark.parametrize('intent,allowed,kind,expected', [
    (graph.INTENT_GUIDE, True, 'report', 'guide'),
    (graph.INTENT_REPORT, True, 'report', 'report'),
    (graph.INTENT_REPORT, True, 'bot', 'multi_report'),
    (graph.INTENT_SMALLTALK, True, 'bot', 'smalltalk'),
    (graph.INTENT_SAFETY, True, 'bot', 'safety'),
    (graph.INTENT_SAFETY, False, 'bot', 'refusal'),
])
def test_explicit_conditional_routes(intent, allowed, kind, expected):
    assert graph.route_answer({'intent': intent, 'allowed': allowed, 'chat_type': kind}) == expected
    assert expected in graph.build_chat_graph().nodes


def test_smalltalk_limit_does_not_call_model(monkeypatch):
    monkeypatch.setattr(graph, '_build_smalltalk_limit_reply', lambda: 'limit')
    assert graph.smalltalk({'remaining_smalltalk': 0}) == {'reply': 'limit'}
