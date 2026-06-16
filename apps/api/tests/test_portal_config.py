"""portal_enabled is true only when both Authentik portal settings are present."""
from apps.api.config import Settings


def _base(**over):
    defaults = dict(
        database_url="postgresql://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        jwt_secret="x",
    )
    defaults.update(over)
    return Settings(**defaults)


def test_portal_disabled_when_unset():
    s = _base()
    assert s.portal_enabled is False


def test_portal_enabled_requires_both():
    assert _base(authentik_api_base="https://sso").portal_enabled is False
    assert _base(authentik_service_token="tok").portal_enabled is False
    assert _base(
        authentik_api_base="https://sso", authentik_service_token="tok"
    ).portal_enabled is True
