"""Who may see, and who may move, an editor's status on a brief.

A brief can be assigned to several editors, each carrying their own pipeline
stage. Two rules govern that, and both are here rather than inline in the
router: they are the parts worth reading on their own, and they are the parts
this test suite can exercise without a database.
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
