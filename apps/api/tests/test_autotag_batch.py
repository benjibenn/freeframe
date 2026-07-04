import uuid
from unittest.mock import MagicMock, patch
import apps.api.tasks.autotag_tasks as at


def _asset(keywords):
    a = MagicMock(); a.id = uuid.uuid4(); a.deleted_at = None; a.keywords = keywords
    return a


def test_batch_skips_already_tagged_when_flag_set():
    tagged, untagged = _asset(["x"]), _asset([])
    ver = MagicMock(); ver.id = uuid.uuid4()
    db = MagicMock(); q = MagicMock(); db.query.return_value = q
    q.filter.return_value = q; q.order_by.return_value = q
    # asset lookups then version lookup for the untagged one
    # Note: the version query requires processing_status==ready (mock doesn't evaluate filters)
    q.first.side_effect = [tagged, untagged, ver]
    with patch("apps.api.tasks.autotag_tasks.SessionLocal", return_value=db), \
         patch("apps.api.tasks.autotag_tasks.send_task_safe") as send:
        at.autotag_batch([str(tagged.id), str(untagged.id)], skip_if_tagged=True)
    assert send.call_count == 1                       # WHY: tagged asset skipped, only untagged enqueued
    assert send.call_args[0][1] == str(untagged.id)
