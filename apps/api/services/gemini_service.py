import asyncio
import json
import re
from dataclasses import dataclass

import httpx

try:
    from ..config import settings
except ImportError:
    from config import settings


@dataclass
class Analysis:
    summary: str
    transcript: str


# The analysis is stored once per version and re-used for every future tag-matching
# pass (including palette labels that don't exist yet), so the summary must be
# exhaustive — details omitted here are permanently invisible to later re-tags
# unless the video is re-analyzed with force=True.
PROMPT_ANALYZE = (
    'Watch this media asset carefully and return a JSON object with two fields.\n'
    '"summary": an exhaustive, detailed description that will later be used to match '
    'topic tags WITHOUT re-watching the video, so capture everything: what happens '
    'scene by scene with approximate timestamps; every visible person (appearance, age '
    'range, clothing), object, animal, product, brand or logo; actions being performed; '
    'the setting and location; visual style (live action, animation, screen recording, '
    'test pattern, UGC, ad, etc.); colors, lighting and camera work (close-up, handheld, '
    'static, drone); ALL on-screen text, captions, watermarks and graphics verbatim; '
    'non-speech audio (music genre, tones, sound effects); and the overall mood and '
    'apparent purpose of the video. Prefer specific, concrete detail over brevity.\n'
    '"transcript": a verbatim transcript of all spoken audio, including who is speaking '
    'when distinguishable; empty string if there is no speech.'
)

ANALYZE_SCHEMA = {
    "type": "OBJECT",
    "properties": {"summary": {"type": "STRING"}, "transcript": {"type": "STRING"}},
    "required": ["summary", "transcript"],
}

MATCH_SCHEMA = {"type": "ARRAY", "items": {"type": "STRING"}}


def build_match_prompt(summary: str, transcript: str, palette: list[str]) -> str:
    return "\n".join([
        "You are auto-tagging a media asset for a media library.",
        "From the EXISTING tags listed below, choose every tag that applies to this asset.",
        "Rules: only use tags from the list, never invent new ones. If none apply, return [].",
        "Reply with ONLY a JSON array of the matching tag names (a subset of the list).",
        "",
        f"Existing tags: {json.dumps(palette)}",
        "",
        f"Summary: {summary}",
        "",
        f"Transcript: {transcript or '(none)'}",
    ])


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    return t


def parse_analysis(text: str) -> Analysis:
    try:
        data = json.loads(_strip_fences(text))
        if not isinstance(data, dict):
            raise ValueError
        return Analysis(summary=str(data.get("summary", "")), transcript=str(data.get("transcript", "")))
    except (json.JSONDecodeError, ValueError):
        return Analysis(summary=text.strip(), transcript="")


def parse_tags(text: str, palette: list[str]) -> list[str]:
    canonical = {p.lower(): p for p in palette}
    raw = _strip_fences(text)
    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []
    if isinstance(data, dict) and "result" in data:
        data = data["result"]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if not isinstance(item, str):
            continue
        key = item.strip().lower()
        if key in canonical and canonical[key] not in out:
            out.append(canonical[key])
    return out


def _extract_text(resp: dict) -> str:
    try:
        return resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return ""


class GeminiClient:
    def __init__(self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        # Resumable uploads live under /upload/v1beta, NOT /v1beta — posting to
        # {base}/files returns 200 without the X-Goog-Upload-URL header.
        self.upload_url = self.base_url.replace("/v1beta", "/upload/v1beta", 1) + "/files"
        self._client = client or httpx.AsyncClient(timeout=120.0)

    @classmethod
    def from_settings(cls, client: httpx.AsyncClient | None = None) -> "GeminiClient":
        return cls(settings.gemini_api_key, settings.gemini_model, settings.gemini_base_url, client)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def upload_file(self, data: bytes, mime_type: str, display_name: str) -> dict:
        start = await self._client.post(
            self.upload_url,
            params={"key": self.api_key},
            headers={
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(data)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": display_name}},
        )
        start.raise_for_status()
        upload_url = start.headers["X-Goog-Upload-URL"]
        finalize = await self._client.post(
            upload_url,
            headers={
                "X-Goog-Upload-Command": "upload, finalize",
                "X-Goog-Upload-Offset": "0",
                "Content-Type": mime_type,
            },
            content=data,
        )
        finalize.raise_for_status()
        return finalize.json()["file"]

    async def wait_until_active(self, file_uri: str, timeout_s: int = 120) -> None:
        for _ in range(max(1, timeout_s // 2)):
            r = await self._client.get(file_uri, params={"key": self.api_key})
            r.raise_for_status()
            state = r.json().get("state")
            if state == "ACTIVE":
                return
            if state == "FAILED":
                raise RuntimeError("Gemini file processing failed")
            await asyncio.sleep(2)
        raise TimeoutError("Gemini file did not become ACTIVE in time")

    async def analyze_media(self, file_uri: str, mime_type: str) -> Analysis:
        r = await self._client.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [
                    {"text": PROMPT_ANALYZE},
                    {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                ]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": ANALYZE_SCHEMA,
                    "temperature": 0.2,
                },
            },
        )
        r.raise_for_status()
        return parse_analysis(_extract_text(r.json()))

    async def match_tags(self, summary: str, transcript: str, palette: list[str]) -> list[str]:
        if not palette:
            return []
        r = await self._client.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": build_match_prompt(summary, transcript, palette)}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": MATCH_SCHEMA,
                    "temperature": 0.2,
                },
            },
        )
        r.raise_for_status()
        return parse_tags(_extract_text(r.json()), palette)
