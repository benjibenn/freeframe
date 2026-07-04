import asyncio
import httpx
from apps.api.services.gemini_service import GeminiClient, Analysis


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_upload_file_returns_file_resource():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-Goog-Upload-Command") == "start":
            # Live API only issues X-Goog-Upload-URL on the /upload/v1beta path;
            # posting to /v1beta/files 200s without it (found in live verification).
            assert request.url.path == "/upload/v1beta/files", request.url.path
            return httpx.Response(200, headers={"X-Goog-Upload-URL": "https://up/2"}, json={})
        return httpx.Response(200, json={"file": {"name": "files/2", "uri": "https://g/v1beta/files/2", "state": "ACTIVE"}})
    gc = GeminiClient("k", "m", "https://g/v1beta", client=_mock_client(handler))
    f = asyncio.run(gc.upload_file(b"bytes", "video/mp4", "clip.mp4"))
    assert f["uri"] == "https://g/v1beta/files/2"


def test_wait_until_active_returns_when_active():
    def handler(request):
        return httpx.Response(200, json={"state": "ACTIVE"})
    gc = GeminiClient("k", "m", "https://g/v1beta", client=_mock_client(handler))
    asyncio.run(gc.wait_until_active("https://g/v1beta/files/2"))  # no raise


def test_analyze_media_parses_candidate_text():
    def handler(request):
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": '{"summary": "a cat", "transcript": "meow"}'}]}}]})
    gc = GeminiClient("k", "m", "https://g/v1beta", client=_mock_client(handler))
    assert asyncio.run(gc.analyze_media("https://g/v1beta/files/2", "video/mp4")) == Analysis("a cat", "meow")


def test_match_tags_filters_to_palette():
    def handler(request):
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": '["Unboxing", "Nope"]'}]}}]})
    gc = GeminiClient("k", "m", "https://g/v1beta", client=_mock_client(handler))
    assert asyncio.run(gc.match_tags("s", "t", ["Unboxing", "Demo"])) == ["Unboxing"]


def test_match_tags_empty_palette_skips_call():
    def handler(request):
        raise AssertionError("should not call Gemini with empty palette")
    gc = GeminiClient("k", "m", "https://g/v1beta", client=_mock_client(handler))
    assert asyncio.run(gc.match_tags("s", "t", [])) == []
