"""The 'keywords' rule in _apply_smart_filter is what makes tag-backed collections
work: a slot's keyword becomes a smart collection that lists every asset carrying it.
The harness mocks the DB (no SQL executes), so we verify the rule contributes its
filter clause; the JSONB-containment semantics mirror the proven assets list endpoint."""
import uuid
from unittest.mock import MagicMock

from apps.api.routers.metadata import _apply_smart_filter


def _chain() -> MagicMock:
    """A mock Session whose query/filter chain returns itself, like conftest's."""
    m = MagicMock()
    m.query.return_value = m
    m.filter.return_value = m
    return m


def test_keyword_rule_adds_one_filter_clause():
    pid = uuid.uuid4()

    no_kw = _chain()
    _apply_smart_filter(no_kw, pid, {})

    one_kw = _chain()
    _apply_smart_filter(one_kw, pid, {"keywords": ["hook"]})

    # Exactly one extra .filter() beyond the base project/deleted clause.
    assert one_kw.filter.call_count == no_kw.filter.call_count + 1


def test_multiple_keywords_are_anded():
    pid = uuid.uuid4()

    one_kw = _chain()
    _apply_smart_filter(one_kw, pid, {"keywords": ["hook"]})

    two_kw = _chain()
    _apply_smart_filter(two_kw, pid, {"keywords": ["hook", "b-roll"]})

    # Each listed keyword contributes its own containment filter (AND semantics).
    assert two_kw.filter.call_count == one_kw.filter.call_count + 1
