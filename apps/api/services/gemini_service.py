import json
import re
from dataclasses import dataclass


@dataclass
class Analysis:
    summary: str
    transcript: str


PROMPT_ANALYZE = (
    'Watch this media asset carefully and return a JSON object with two fields: '
    '"summary" (3-5 sentences describing what happens, who/what is shown, the setting, '
    'mood, and any on-screen text) and "transcript" (a verbatim transcript of all spoken '
    'audio; empty string if there is no speech).'
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
