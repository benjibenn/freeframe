"""Tests for attaching brief reference media by URL.

The point of these is the SSRF guard, not the happy path. This feature makes the
server fetch a URL an authenticated caller chose, which is the classic way to turn
an ad-tooling endpoint into a port scanner for the internal network. Each test
below names the attack it forecloses; if one of them starts passing for the wrong
reason the guard has been hollowed out.
"""
import socket
import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.api.routers import mcp as mcp_router
from apps.api.services import url_fetch
from apps.api.services.url_fetch import RemoteFetchError, fetch_remote_file


def _resolves_to(*addresses: str):
    """Fake getaddrinfo returning the given addresses for any host."""
    def fake(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0)) for addr in addresses]
    return fake


def _serving(handler):
    """Swap httpx.Client for one backed by MockTransport, preserving the call shape
    url_fetch uses (keyword-only follow_redirects and timeout). The real class is
    captured first, or `make` would call its own patched self forever."""
    real_client = httpx.Client

    def make(**kwargs):
        return real_client(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            timeout=kwargs.get("timeout"),
        )
    return patch.object(url_fetch.httpx, "Client", make)


def _png(size: int = 32) -> httpx.Response:
    return httpx.Response(200, content=b"\x89PNG" + b"0" * (size - 4),
                          headers={"content-type": "image/png"})


IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")


# ── Address guards ───────────────────────────────────────────────────────────

def test_rejects_non_http_scheme():
    """file:// would read the server's own disk; gopher:// is the classic pivot."""
    with pytest.raises(RemoteFetchError, match="http"):
        fetch_remote_file("file:///etc/passwd", allowed_content_types=IMAGE_TYPES, max_bytes=1000)


@pytest.mark.parametrize(
    "address,expected",
    [
        ("127.0.0.1", "loopback"),
        ("10.0.0.5", "private"),
        ("192.168.1.10", "private"),
        ("169.254.169.254", "link-local"),  # cloud metadata, the crown jewels
    ],
)
def test_rejects_internal_addresses(address, expected):
    with patch("socket.getaddrinfo", _resolves_to(address)):
        with pytest.raises(RemoteFetchError, match=expected):
            fetch_remote_file("http://evil.test/x.png", allowed_content_types=IMAGE_TYPES, max_bytes=1000)


def test_rejects_when_any_resolved_address_is_internal():
    """A hostile name can answer with one public and one private record. Checking
    only the first would let the private one through on the next connection."""
    with patch("socket.getaddrinfo", _resolves_to("93.184.216.34", "10.0.0.5")):
        with pytest.raises(RemoteFetchError, match="private"):
            fetch_remote_file("http://mixed.test/x.png", allowed_content_types=IMAGE_TYPES, max_bytes=1000)


def test_redirect_to_internal_address_is_blocked():
    """The guard is worthless if the first hop can 302 to the metadata service, so
    every hop is re-validated rather than trusting the URL we were handed."""
    def handler(request):
        if request.url.host == "public.test":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        return _png()

    def resolve(host, port, *args, **kwargs):
        addr = "169.254.169.254" if host == "169.254.169.254" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))]

    with patch("socket.getaddrinfo", resolve), _serving(handler):
        with pytest.raises(RemoteFetchError, match="link-local"):
            fetch_remote_file("http://public.test/x.png", allowed_content_types=IMAGE_TYPES, max_bytes=1000)


# ── Content guards ───────────────────────────────────────────────────────────

def test_rejects_unsupported_content_type():
    def handler(request):
        return httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})

    with patch("socket.getaddrinfo", _resolves_to("93.184.216.34")), _serving(handler):
        with pytest.raises(RemoteFetchError, match="Unsupported content type"):
            fetch_remote_file("http://public.test/x", allowed_content_types=IMAGE_TYPES, max_bytes=1000)


def test_size_cap_counts_actual_bytes_not_content_length():
    """A hostile server can advertise a small Content-Length and then send a
    gigabyte, so the cap is enforced while reading rather than up front."""
    def handler(request):
        return httpx.Response(
            200,
            content=b"x" * 5000,
            headers={"content-type": "image/png", "content-length": "10"},
        )

    with patch("socket.getaddrinfo", _resolves_to("93.184.216.34")), _serving(handler):
        with pytest.raises(RemoteFetchError, match="larger than"):
            fetch_remote_file("http://public.test/x.png", allowed_content_types=IMAGE_TYPES, max_bytes=1000)


def test_rejects_empty_body():
    def handler(request):
        return httpx.Response(200, content=b"", headers={"content-type": "image/png"})

    with patch("socket.getaddrinfo", _resolves_to("93.184.216.34")), _serving(handler):
        with pytest.raises(RemoteFetchError, match="empty"):
            fetch_remote_file("http://public.test/x.png", allowed_content_types=IMAGE_TYPES, max_bytes=1000)


def test_http_error_is_reported_as_caller_fixable():
    def handler(request):
        return httpx.Response(404, content=b"nope", headers={"content-type": "text/plain"})

    with patch("socket.getaddrinfo", _resolves_to("93.184.216.34")), _serving(handler):
        with pytest.raises(RemoteFetchError, match="404"):
            fetch_remote_file("http://public.test/x.png", allowed_content_types=IMAGE_TYPES, max_bytes=1000)


def test_video_family_prefix_matches_any_video_subtype():
    """Videos are allowed by family, so an unlisted subtype still gets through
    rather than failing on a codec we forgot to enumerate."""
    def handler(request):
        return httpx.Response(200, content=b"ftyp", headers={"content-type": "video/x-flv"})

    with patch("socket.getaddrinfo", _resolves_to("93.184.216.34")), _serving(handler):
        data, content_type = fetch_remote_file(
            "http://public.test/clip", allowed_content_types=("video/",), max_bytes=1000
        )
    assert data == b"ftyp"
    assert content_type == "video/x-flv"


def test_successful_fetch_returns_bytes_and_type():
    def handler(request):
        return _png()

    with patch("socket.getaddrinfo", _resolves_to("93.184.216.34")), _serving(handler):
        data, content_type = fetch_remote_file(
            "https://public.test/a.png", allowed_content_types=IMAGE_TYPES, max_bytes=1000
        )
    assert data.startswith(b"\x89PNG")
    assert content_type == "image/png"


def test_content_type_parameters_are_ignored():
    """'image/png; charset=binary' is still an image; matching the raw header
    would reject perfectly good CDN responses."""
    def handler(request):
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png; charset=binary"})

    with patch("socket.getaddrinfo", _resolves_to("93.184.216.34")), _serving(handler):
        _, content_type = fetch_remote_file(
            "https://public.test/a.png", allowed_content_types=IMAGE_TYPES, max_bytes=1000
        )
    assert content_type == "image/png"


# ── MCP tool argument handling ───────────────────────────────────────────────

def test_add_reference_rejects_unknown_kind():
    with pytest.raises(ValueError, match="kind must be"):
        mcp_router.add_brief_reference(link_id=str(uuid.uuid4()), url="http://x.test/a.png", kind="gif")


def test_remove_reference_requires_a_kind():
    with pytest.raises(ValueError, match="kind must be"):
        mcp_router.remove_brief_reference(link_id=str(uuid.uuid4()), kind="")


def test_remove_reference_rejects_negative_index():
    """A negative index would slice from the end and silently drop the wrong
    attachment rather than failing."""
    with pytest.raises(ValueError, match="0 or greater"):
        mcp_router.remove_brief_reference(
            link_id=str(uuid.uuid4()), kind="image", index=-1
        )


def test_auto_kind_falls_back_to_video_when_image_route_refuses():
    """auto must not give up on the first refusal: an mp4 URL is rejected by the
    image route on content type, and should then be attached as a video."""
    link = MagicMock()
    link.id = uuid.uuid4()
    link.title = "t"
    link.home_project_id = None
    link.home_folder_id = None
    link.home_path = None
    link.submission_count = 0
    link.is_enabled = True
    link.token = "tok"
    link.created_at = None
    link.reference_image_count = 0
    link.reference_video_count = 1

    calls = []

    def fake_call(fn, **kwargs):
        calls.append(fn.__name__)
        if fn.__name__ == "add_reference_image_from_url":
            raise ValueError("Unsupported content type video/mp4")
        return link

    with patch.object(mcp_router, "_call", fake_call), patch.object(mcp_router, "_require_scope", lambda s: None):
        out = mcp_router.add_brief_reference(
            link_id=str(link.id), url="http://public.test/clip.mp4"
        )

    assert calls == ["add_reference_image_from_url", "add_reference_video_from_url"]
    assert out["attached"] == "video"
    assert out["reference_video_count"] == 1
