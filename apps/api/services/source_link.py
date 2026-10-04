"""The source link an uploader gives with every file, kept as its first comment.

A delivered file is a render: the artwork it came from lives in Figma or Canva,
and nothing in the file records where. Without that link a revision means
guessing, or asking the editor who made it. So the link is required at
/upload/initiate — the one moment the uploader is still present — and stored as a
comment rather than a column, because that is where the people who need it look.

It is attached to the VERSION, not just the asset: v2 of a hook is usually a
different frame, so v1's source must not be read as v2's.

Internal, not public: a share link's audience is the client, and the working file
is not theirs to open.
"""
import uuid

from ..models.comment import Comment, CommentVisibility

PREFIX = "Source: "

# Guests reach assets through share links; the working file is not part of what
# was shared with them.
VISIBILITY = CommentVisibility.internal.value


def normalize(value) -> str:
    """The link as given, trimmed. Raises when there is nothing there.

    Anything non-blank is accepted on purpose. A source may be a Figma file, a
    Canva design, a Drive folder or a path in a shared volume, and rejecting the
    odd one out would block a delivery over a rule nobody agreed to.
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("source_url is required — say which Figma or Canva file this was made from")
    return text


def source_comment(
    *,
    asset_id: uuid.UUID,
    version_id: uuid.UUID,
    author_id: uuid.UUID,
    source_url: str,
) -> Comment:
    """The first comment on a freshly uploaded version, naming its source."""
    return Comment(
        asset_id=asset_id,
        version_id=version_id,
        author_id=author_id,
        body=f"{PREFIX}{normalize(source_url)}",
        visibility=VISIBILITY,
    )


def parse(body) -> "str | None":
    """The link out of a source comment's body, or None when it is not one."""
    if not body or not body.startswith(PREFIX):
        return None
    return body[len(PREFIX):].strip() or None


def links_by_version(rows) -> dict:
    """{version_id: link} from (version_id, body) rows ordered oldest first.

    The first source comment on a version wins: it is the one written at upload.
    """
    out: dict = {}
    for version_id, body in rows:
        if version_id in out:
            continue
        link = parse(body)
        if link:
            out[version_id] = link
    return out
