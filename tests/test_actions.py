import pytest

from shopgym.env.actions import ActionError, parse_action


@pytest.mark.parametrize("raw, expected_type", [
    ({"type": "click", "element": "e12"}, "click"),
    ('{"type":"click","x":10,"y":20}', "click"),
    ({"type": "type", "element": "e5", "text": "hi", "submit": True}, "type"),
    ({"type": "press", "key": "Enter"}, "press"),
    ({"type": "scroll", "direction": "up"}, "scroll"),
    ({"type": "select", "element": "e7", "value": "price_asc"}, "select"),
    ({"type": "back"}, "back"),
    ({"type": "goto", "url": "/orders"}, "goto"),
    ({"type": "finish", "answer": "42"}, "finish"),
    ({"type": "finish"}, "finish"),
])
def test_valid_actions_parse(raw, expected_type):
    assert parse_action(raw).type == expected_type


@pytest.mark.parametrize("raw", [
    "not json",
    [],
    {"type": "explode"},
    {"type": "click", "element": "../etc"},
    {"type": "click", "element": "e1; drop"},
    {"type": "click", "x": "left", "y": 1},
    {"type": "click", "x": 5000, "y": 1},
    {"type": "goto", "url": "https://evil.example/"},
    {"type": "goto", "url": "//evil.example/"},
    {"type": "goto", "url": "/a\\b"},
    {"type": "scroll", "direction": "sideways"},
    {"type": "scroll", "amount": 10**9},
    {"type": "scroll", "amount": True},
    {"type": "press", "key": "x" * 31},
    {"type": "finish", "answer": 42},
])
def test_malformed_actions_are_rejected_before_the_browser(raw):
    with pytest.raises(ActionError):
        parse_action(raw)
