MAX_TAGS = 50
MAX_TAG_LEN = 50


def normalize_tags(raw) -> list[str]:
    """Trim, collapse internal whitespace, lowercase, dedupe (order-preserving)."""
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        tag = " ".join(item.strip().lower().split())[:MAX_TAG_LEN]
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= MAX_TAGS:
            break
    return out
