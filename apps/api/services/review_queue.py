"""The /review queue: which files are waiting, and what a reviewer needs beside each.

Review is a pipeline stage, not Asset.status. A file is waiting when its stage
is Review; approving moves it to Done, rejecting to Revision. The three are
found by NAME because admins rename and reorder stages. If one is missing the
queue refuses (409) rather than guessing which stage was meant.

The legacy Asset.status approve/reject path (MCP review_file, routers/approvals.py)
is untouched and separate. Flagged for cleanup; out of scope here.
"""

REVIEW = "Review"
DONE = "Done"
REVISION = "Revision"


class MissingStage(Exception):
    def __init__(self, name: str):
        super().__init__(f"Missing task stage: {name}")
        self.name = name


def resolve_review_stages(stages) -> dict:
    """{'review': id, 'done': id, 'revision': id} from stages ordered by position.

    Names compare trimmed and case-insensitive. With two stages of one name, the
    first in board order wins, so the answer never depends on row order in the DB.
    """
    by_name: dict = {}
    for s in stages:
        by_name.setdefault((s.name or "").strip().casefold(), s.id)
    out = {}
    for name in (REVIEW, DONE, REVISION):
        sid = by_name.get(name.casefold())
        if sid is None:
            raise MissingStage(name)
        out[name.lower()] = sid
    return out


def is_revision(stage) -> bool:
    return (stage.name or "").strip().casefold() == REVISION.casefold()
