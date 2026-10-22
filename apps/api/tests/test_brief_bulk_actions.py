"""Bulk actions over briefs ticked in the folder listing.

A brief's files live in its submitters' own projects, so the caller cannot name
them; both endpoints resolve the set server-side with _brief_assets, the same
resolver the single-brief download uses. The route paths carry a "bulk/" segment
because submissions.py registers PATCH /submission-links/{link_id} first and
would otherwise read "bulk-stage" as a link id.
"""
import uuid
from unittest.mock import MagicMock, patch


def _link(title="Hook A"):
    l = MagicMock()
    l.id = uuid.uuid4()
    l.title = title
    l.deleted_at = None
    return l


def _asset():
    a = MagicMock()
    a.id = uuid.uuid4()
    a.task_stage_id = None
    a.deleted_at = None
    return a


def _as_admin(test_user):
    test_user.is_subadmin = True
    test_user.is_superadmin = False
    return test_user


def test_stamps_every_file_of_every_selected_brief(client, mock_db, auth_headers, test_user):
    _as_admin(test_user)
    l1, l2 = _link("Hook A"), _link("Hook B")
    a1, a2, a3 = _asset(), _asset(), _asset()
    stage_id = uuid.uuid4()
    with patch("apps.api.routers.brief_files._get_owned_link", side_effect=[l1, l2]), \
         patch("apps.api.routers.brief_files._brief_assets", side_effect=[[a1, a2], [a3]]):
        mock_db.first.return_value = MagicMock()  # the stage exists
        resp = client.patch(
            "/submission-links/bulk/stage",
            json={"link_ids": [str(l1.id), str(l2.id)], "task_stage_id": str(stage_id)},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 3, "briefs": 2}
    assert [a.task_stage_id for a in (a1, a2, a3)] == [stage_id] * 3


def test_route_is_not_swallowed_by_the_link_id_route(client, mock_db, auth_headers, test_user):
    # Guards the path shape itself: as "/submission-links/bulk-stage" this would
    # hit PATCH /submission-links/{link_id} and fail UUID parsing with a 422.
    _as_admin(test_user)
    with patch("apps.api.routers.brief_files._get_owned_link", return_value=_link()), \
         patch("apps.api.routers.brief_files._brief_assets", return_value=[]):
        resp = client.patch(
            "/submission-links/bulk/stage",
            json={"link_ids": [str(uuid.uuid4())], "task_stage_id": None},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 0, "briefs": 1}


def test_null_stage_clears_the_selection(client, mock_db, auth_headers, test_user):
    _as_admin(test_user)
    a1 = _asset()
    a1.task_stage_id = uuid.uuid4()
    with patch("apps.api.routers.brief_files._get_owned_link", return_value=_link()), \
         patch("apps.api.routers.brief_files._brief_assets", return_value=[a1]):
        resp = client.patch(
            "/submission-links/bulk/stage",
            json={"link_ids": [str(uuid.uuid4())], "task_stage_id": None},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    assert a1.task_stage_id is None


def test_one_forbidden_brief_fails_the_whole_call(client, mock_db, auth_headers, test_user):
    # Dropping it silently would report a success that restamped a partial set.
    from fastapi import HTTPException
    _as_admin(test_user)
    a1 = _asset()
    with patch("apps.api.routers.brief_files._get_owned_link",
               side_effect=[_link(), HTTPException(status_code=403, detail="Not your submission link")]), \
         patch("apps.api.routers.brief_files._brief_assets", return_value=[a1]):
        resp = client.patch(
            "/submission-links/bulk/stage",
            json={"link_ids": [str(uuid.uuid4()), str(uuid.uuid4())], "task_stage_id": None},
            headers=auth_headers,
        )
    assert resp.status_code == 403
    assert a1.task_stage_id is None  # nothing stamped


def test_stage_rejects_non_admin(client, mock_db, auth_headers, test_user):
    test_user.is_subadmin = False
    test_user.is_superadmin = False
    a1 = _asset()
    with patch("apps.api.routers.brief_files._brief_assets", return_value=[a1]):
        resp = client.patch(
            "/submission-links/bulk/stage",
            json={"link_ids": [str(uuid.uuid4())], "task_stage_id": None},
            headers=auth_headers,
        )
    assert resp.status_code == 403
    assert a1.task_stage_id is None


def test_stage_rejects_empty_and_oversized_selections(client, mock_db, auth_headers, test_user):
    _as_admin(test_user)
    empty = client.patch(
        "/submission-links/bulk/stage",
        json={"link_ids": [], "task_stage_id": None},
        headers=auth_headers,
    )
    assert empty.status_code == 422
    too_many = client.patch(
        "/submission-links/bulk/stage",
        json={"link_ids": [str(uuid.uuid4()) for _ in range(101)], "task_stage_id": None},
        headers=auth_headers,
    )
    assert too_many.status_code == 413


def test_stage_404s_on_a_missing_stage(client, mock_db, auth_headers, test_user):
    _as_admin(test_user)
    a1 = _asset()
    with patch("apps.api.routers.brief_files._get_owned_link", return_value=_link()), \
         patch("apps.api.routers.brief_files._brief_assets", return_value=[a1]):
        mock_db.first.return_value = None
        resp = client.patch(
            "/submission-links/bulk/stage",
            json={"link_ids": [str(uuid.uuid4())], "task_stage_id": str(uuid.uuid4())},
            headers=auth_headers,
        )
    assert resp.status_code == 404
    assert a1.task_stage_id is None


def test_download_puts_each_brief_in_its_own_folder(client, mock_db, auth_headers, test_user):
    # The whole point of the multi-brief ZIP: a flat archive of several briefs
    # cannot be sorted back out by hand.
    import io, zipfile
    _as_admin(test_user)
    l1, l2 = _link("Hook A"), _link("Hook B")
    a1, a2 = _asset(), _asset()
    a1.name = "French — French · EUR"
    a2.name = "Swedish — Swedish · SEK"
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(b"data")}
    with patch("apps.api.routers.brief_files._get_owned_link", side_effect=[l1, l2]), \
         patch("apps.api.routers.brief_files._brief_assets", side_effect=[[a1], [a2]]), \
         patch("apps.api.routers.brief_files._media", return_value=("k", "clip.mp4")), \
         patch("apps.api.services.s3_service.get_s3_client", return_value=s3):
        resp = client.post(
            "/submission-links/bulk/download",
            json={"link_ids": [str(l1.id), str(l2.id)]},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert all("/" in n for n in names), names
    assert {n.split("/")[0] for n in names} == {"Hook A", "Hook B"}


def test_download_disambiguates_briefs_sharing_a_title(client, mock_db, auth_headers, test_user):
    # Same title would otherwise collapse two briefs into one ZIP folder.
    import io, zipfile
    _as_admin(test_user)
    l1, l2 = _link("Hook A"), _link("Hook A")
    a1, a2 = _asset(), _asset()
    a1.name, a2.name = "French — EUR", "Swedish — SEK"
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(b"data")}
    with patch("apps.api.routers.brief_files._get_owned_link", side_effect=[l1, l2]), \
         patch("apps.api.routers.brief_files._brief_assets", side_effect=[[a1], [a2]]), \
         patch("apps.api.routers.brief_files._media", return_value=("k", "clip.mp4")), \
         patch("apps.api.services.s3_service.get_s3_client", return_value=s3):
        resp = client.post(
            "/submission-links/bulk/download",
            json={"link_ids": [str(l1.id), str(l2.id)]},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    folders = {n.split("/")[0] for n in zipfile.ZipFile(io.BytesIO(resp.content)).namelist()}
    assert folders == {"Hook A", "Hook A (2)"}


def test_download_404s_when_nothing_was_submitted(client, mock_db, auth_headers, test_user):
    # An empty ZIP looks like a successful download of nothing.
    _as_admin(test_user)
    with patch("apps.api.routers.brief_files._get_owned_link", return_value=_link()), \
         patch("apps.api.routers.brief_files._brief_assets", return_value=[]), \
         patch("apps.api.services.s3_service.get_s3_client", return_value=MagicMock()):
        resp = client.post(
            "/submission-links/bulk/download",
            json={"link_ids": [str(uuid.uuid4())]},
            headers=auth_headers,
        )
    assert resp.status_code == 404
