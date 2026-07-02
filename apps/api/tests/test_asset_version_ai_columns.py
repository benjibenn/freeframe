from apps.api.models.asset import AssetVersion


def test_asset_version_has_ai_cache_columns():
    cols = AssetVersion.__table__.columns.keys()
    assert "ai_summary" in cols
    assert "ai_transcript" in cols
    assert "ai_analyzed_at" in cols
