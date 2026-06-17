"""brief_import_fallback_email is an optional setting (None when unset)."""
from apps.api.config import Settings


def _base(**over):
    d = dict(database_url="postgresql://u:p@localhost/db", redis_url="redis://localhost:6379/0", jwt_secret="x")
    d.update(over)
    return Settings(**d)


def test_fallback_email_defaults_none():
    assert _base().brief_import_fallback_email is None


def test_fallback_email_set():
    assert _base(brief_import_fallback_email="cf@team.test").brief_import_fallback_email == "cf@team.test"
