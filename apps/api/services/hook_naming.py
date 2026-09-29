"""Auto-naming for assets uploaded into a request's per-submitter project.

Submitters don't get to name their uploads: inside a project provisioned by a
submission link every NEW asset is called "Hook N". N is scoped to that one
project, so each submitter's sequence starts at Hook 1 and they never see (or
collide with) another submitter's numbering.

Only brand-new assets consume a number. A re-upload of an existing hook goes
through POST /assets/{id}/versions, which adds a version and never renames, so
revisions don't advance the counter.
"""
import re
import uuid

from sqlalchemy.orm import Session

from ..models.asset import Asset

_HOOK_NAME = re.compile(r"^hook\s+(\d+)$")


def variation_names(brief_json) -> list[str]:
    """Deliverable names a brief prescribes for submitted assets.

    Walks brief_json -> final_deliverable -> hook_variations[] -> variation,
    collecting non-empty strings. Briefs come from a free-form paste flow and
    predate this naming scheme, so any missing or misshapen level yields [] —
    which callers treat as "no prescribed names, fall back to Hook N".
    """
    if not isinstance(brief_json, dict):
        return []
    deliverable = brief_json.get("final_deliverable")
    if not isinstance(deliverable, dict):
        return []
    variations = deliverable.get("hook_variations")
    if not isinstance(variations, list):
        return []
    names = []
    for row in variations:
        if isinstance(row, dict):
            name = row.get("variation")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return names


# Language goes first so a reviewer scanning the asset list sees one locale
# grouped together, which is how localised work gets reviewed — a pass over all
# the German cuts, then all the Swedish.
_LANGUAGE_SEPARATOR = " — "


def output_languages(brief_json) -> list[str]:
    """Languages a brief asks for the same deliverables in.

    Same defensive walk as variation_names, for the same reason: brief_json comes
    from a free-form paste flow, so a missing or misshapen key yields [] rather
    than raising — callers read that as "this request is single-language".
    """
    if not isinstance(brief_json, dict):
        return []
    raw = brief_json.get("output_languages")
    if not isinstance(raw, list):
        return []
    return [lang.strip() for lang in raw if isinstance(lang, str) and lang.strip()]


def requires_language(brief_json) -> bool:
    """Whether the uploader has to say which language their file is.

    One language is not a choice: asking would be a dropdown with a single
    option, and stamping it onto every name adds a prefix that distinguishes
    nothing. Only a brief listing two or more makes the question real.
    """
    return len(output_languages(brief_json)) > 1


def compose_name(language, name: str) -> str:
    """Prefix a deliverable name with its language, when there is one."""
    return f"{language}{_LANGUAGE_SEPARATOR}{name}" if language else name


def strip_language(name: str, language) -> str | None:
    """`name` without its language prefix, or None if it is another language's.

    Returning None rather than the untouched name is what makes hook numbering
    per-language: a Swedish upload counts only the Swedish hooks, so it becomes
    Swedish Hook 1 alongside German Hook 1 instead of continuing to Hook 4. The
    pairing is the point — the two are the same idea in two locales.
    """
    text = (name or "").strip()
    if not language:
        return text
    prefix = f"{language}{_LANGUAGE_SEPARATOR}"
    if text.casefold().startswith(prefix.casefold()):
        return text[len(prefix):]
    return None


def next_hook_number(names) -> int:
    """One past the highest "Hook N" in `names` (1 when there are none).

    Uses the max rather than a count so that renaming or deleting a hook can't
    hand the same number to two different assets — a gap in the middle stays a
    gap.
    """
    highest = 0
    for name in names:
        match = _HOOK_NAME.match(" ".join((name or "").strip().lower().split()))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def next_hook_name(db: Session, project_id: uuid.UUID, language=None) -> str:
    """The name to give the next new asset uploaded to this submission project.

    Callers must hold a lock on the project row (SELECT ... FOR UPDATE): a
    multi-file selection initiates every upload concurrently, and without
    serialization they would all read the same highest number.

    With a language, only that language's existing hooks are counted and the
    result carries the prefix, so the sequences run in parallel rather than
    interleaving.
    """
    names = db.query(Asset.name).filter(
        Asset.project_id == project_id,
        Asset.deleted_at.is_(None),
    ).all()
    bare = [
        stripped
        for (name,) in names
        if (stripped := strip_language(name, language)) is not None
    ]
    return compose_name(language, f"Hook {next_hook_number(bare)}")
