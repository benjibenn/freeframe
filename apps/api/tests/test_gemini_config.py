from apps.api.config import Settings


def test_gemini_defaults():
    s = Settings(redis_url="redis://localhost:6379/0")
    assert s.gemini_api_key is None
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.gemini_base_url == "https://generativelanguage.googleapis.com/v1beta"
