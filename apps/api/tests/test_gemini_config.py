from apps.api.config import Settings


def test_gemini_defaults(monkeypatch):
    # Isolate from developer machines: a real GEMINI_API_KEY in .env or the shell
    # must not make the *defaults* test fail.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    s = Settings(
        database_url="postgresql://user:pass@localhost:5432/freeframe_test",
        redis_url="redis://localhost:6379/0",
        _env_file=None,
    )
    assert s.gemini_api_key is None
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.gemini_base_url == "https://generativelanguage.googleapis.com/v1beta"
