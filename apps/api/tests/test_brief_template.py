"""The brief template is admin-authored free-form config; normalization is the guard
that keeps a bad paste from producing an un-renderable or dangerous stored template.
These pin WHY each rule exists, not just that the function runs."""
from apps.api.routers import brief_template as bt


def test_drops_sections_without_a_path():
    # A section with no path can never resolve a value — it would render an empty
    # heading forever, so it must be dropped rather than stored.
    out = bt._normalize_sections([{"title": "Ghost", "as": "text"}])
    assert out == []


def test_drops_unknown_render_type():
    # Only text/bullets/table are renderable; anything else can't be displayed.
    out = bt._normalize_sections([{"path": "x", "as": "carousel"}])
    assert out == []


def test_assigns_id_when_missing():
    # Ids anchor React keys + reorder; a section pasted without one still needs a stable id.
    out = bt._normalize_sections([{"path": "overview", "as": "text"}])
    assert len(out) == 1 and out[0]["id"]


def test_table_keeps_good_columns_and_drops_keyless_ones():
    out = bt._normalize_sections([{
        "path": "rows", "as": "table",
        "columns": [{"key": "a", "header": "A"}, {"header": "no key"}, {"key": "b"}],
    }])
    cols = out[0]["columns"]
    assert [c["key"] for c in cols] == ["a", "b"]
    # A column missing a header falls back to its key so the table still has a label.
    assert cols[1]["header"] == "b"


def test_non_table_section_has_no_columns_key():
    out = bt._normalize_sections([{"path": "overview", "as": "text", "columns": [{"key": "x"}]}])
    assert "columns" not in out[0]
