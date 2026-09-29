"""Who may see, and who may move, an editor's status on a brief.

A brief can be assigned to several editors, each carrying their own pipeline
stage. The rules governing that are here rather than inline in the router: they
are the parts worth reading on their own, and they are the parts this test suite
can exercise without a database.
"""
from typing import Any, Optional
import uuid


def visible_editors(
    editors: list[Any],
    viewer_id: Optional[uuid.UUID],
    is_admin: bool,
) -> list[Any]:
    """The editor rows this viewer is allowed to receive.

    Per-submitter isolation is what submission links are for: editors on one
    brief never see each other's uploads, so they must not see each other's
    names or progress either. Applied to the response body rather than the UI,
    because hiding a row on screen still ships it over the wire.

    Fails closed on a missing viewer id — that is the case where handing back
    the full list would go unnoticed.
    """
    if is_admin:
        return list(editors)
    if viewer_id is None:
        return []
    return [e for e in editors if e.id == viewer_id]


def visible_owner(
    assignee_id: Optional[uuid.UUID],
    owner_name: Optional[str],
    viewer_id: Optional[uuid.UUID],
    is_admin: bool,
) -> tuple[Optional[uuid.UUID], Optional[str]]:
    """The brief's internal owner as this viewer is allowed to receive it.

    An owner is routinely also an editor on their own brief, so passing this
    field through unconditionally hands editor B the name of editor A — the very
    leak `visible_editors` exists to stop, arriving by a different field instead.

    A non-admin sees the owner only when they are the owner. Seeing that a brief
    sits on your own desk discloses nothing about anyone else, and blanking it
    would leave an owner unable to tell they own it.

    Returned as a pair so the id and the name cannot be blanked separately: the
    id alone re-identifies the person anywhere else it is rendered.
    """
    if is_admin or (viewer_id is not None and assignee_id == viewer_id):
        return assignee_id, owner_name
    return None, None


def may_move_editor_stage(
    viewer_id: Optional[uuid.UUID],
    target_user_id: uuid.UUID,
    is_admin: bool,
) -> bool:
    """Whether this viewer may set `target_user_id`'s status on a brief.

    Admins move anyone: the board is their roll-up. Everyone else moves only
    themselves — two editors on one brief are doing separate work, and neither
    reports progress on the other's behalf.
    """
    return bool(is_admin or (viewer_id is not None and viewer_id == target_user_id))
