"""Assemble a brief title the playbook can read back.

The playbook derives a brief's persona, lens, hook and format from its title by
splitting on " - " (`parseTitle`, apps/web/lib/playbook.ts):

    YYYYMMDD - <sku> - <Persona> - <Lens> - <Hook> - <Format>

Nothing enforced that convention, so a title typed by hand could silently land a
brief in the coverage matrix with no persona and no lens at all — parseTitle
returns all-nulls for anything with fewer than six slots. Building the title from
its parts instead makes a malformed one impossible to create.

The hook is the only part allowed to contain " - ": parseTitle recovers it by
joining every slot between the lens and the format, so a separator there is
harmless. In any other part it would shift every field after it, so it is
refused rather than quietly escaped.

Angle is deliberately absent — it is not in the title at all. It lives in
SubmissionLink.angle_label, which is what the matrix's columns count.
"""
from datetime import date, datetime

SEPARATOR = " - "

# Order is the convention, not a preference: position is how the playbook
# identifies each field.
_ORDER = ("sku", "persona", "lens", "hook", "ad_format")


def _required(name: str, value) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{name} is required — a title missing a slot reads as having no persona or lens at all")
    # The hook is exempt: it is the slot parseTitle joins, so it may contain the
    # separator without displacing anything.
    if name != "hook" and SEPARATOR in text:
        raise ValueError(f"{name} must not contain {SEPARATOR!r} — it would shift every later part of the title")
    return text


def _stamp(date_str) -> str:
    if date_str is None:
        return date.today().strftime("%Y%m%d")
    text = str(date_str).strip()
    try:
        return datetime.strptime(text, "%Y%m%d").strftime("%Y%m%d")
    except ValueError:
        raise ValueError(f"date must be YYYYMMDD, got {date_str!r}") from None


def build_title(
    *,
    sku,
    persona,
    lens,
    hook,
    ad_format,
    date_str=None,
) -> str:
    """The six-slot title for a new brief. Today's date unless one is given.

    The date defaults rather than being required so an agent cannot stamp a brief
    with its own stale notion of today; pass one only to backdate deliberately.
    """
    parts = {"sku": sku, "persona": persona, "lens": lens, "hook": hook, "ad_format": ad_format}
    return SEPARATOR.join([_stamp(date_str), *(_required(n, parts[n]) for n in _ORDER)])
