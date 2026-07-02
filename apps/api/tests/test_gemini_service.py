from apps.api.services.gemini_service import Analysis, parse_analysis, parse_tags, build_match_prompt


def test_parse_analysis_valid_json():
    a = parse_analysis('{"summary": "a cat naps", "transcript": "meow"}')
    assert a == Analysis(summary="a cat naps", transcript="meow")


def test_parse_analysis_strips_code_fence():
    a = parse_analysis('```json\n{"summary": "x", "transcript": ""}\n```')
    assert a == Analysis(summary="x", transcript="")


def test_parse_analysis_malformed_falls_back_to_summary():
    a = parse_analysis("not json at all")
    assert a == Analysis(summary="not json at all", transcript="")


def test_parse_tags_keeps_only_palette_subset():
    assert parse_tags('["Unboxing", "NotInPalette"]', ["Unboxing", "Demo"]) == ["Unboxing"]


def test_parse_tags_is_case_insensitive_and_returns_canonical_casing():
    assert parse_tags('["unboxing", "DEMO"]', ["Unboxing", "Demo"]) == ["Unboxing", "Demo"]


def test_parse_tags_dedupes():
    assert parse_tags('["Demo", "demo"]', ["Demo"]) == ["Demo"]


def test_parse_tags_unwraps_result_envelope():
    assert parse_tags('{"result": "[\\"Demo\\"]"}', ["Demo"]) == ["Demo"]


def test_parse_tags_malformed_returns_empty():
    assert parse_tags("sorry, I cannot", ["Demo"]) == []


def test_build_match_prompt_includes_palette_and_context():
    p = build_match_prompt("a summary", "", ["Demo", "Unboxing"])
    assert '["Demo", "Unboxing"]' in p
    assert "Summary: a summary" in p
    assert "Transcript: (none)" in p
