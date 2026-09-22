"""Response shapes for the superadmin reports page.

One request returns every pivot the page offers (totals, per-brief, per-user and
the flat file list) because they are four readings of the SAME join — brief →
submission → per-submitter project → asset. Splitting them into four endpoints
would re-walk that join four times and let the tabs disagree about the numbers
when uploads land mid-session.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReportTotals(BaseModel):
    brief_count: int
    submission_count: int
    file_count: int
    # Distinct people who have accepted at least one brief, NOT the total user
    # count — the report is about work done, not accounts that exist.
    submitter_count: int
    # A brief nobody has uploaded a file against yet. Counted on files, not on
    # submissions: accepting a link and never delivering still means "awaiting".
    briefs_awaiting_work: int


class ReportBriefRow(BaseModel):
    id: uuid.UUID
    title: str
    home_path: Optional[str] = None
    created_at: datetime
    is_enabled: bool
    persona_label: Optional[str] = None
    angle_label: Optional[str] = None
    submission_count: int
    file_count: int
    # Ids as well as names: the page filters by submitter, and two editors can
    # share a display name while their ids never collide.
    submitter_ids: list[uuid.UUID]
    submitter_names: list[str]
    last_upload_at: Optional[datetime] = None


class ReportUserRow(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    # No separate submission count: `uq_submissions_link_user` makes one
    # submission per (brief, person), so the two numbers are always equal.
    brief_count: int
    file_count: int
    last_upload_at: Optional[datetime] = None


class ReportFileRow(BaseModel):
    asset_id: uuid.UUID
    name: str
    created_at: datetime
    project_id: uuid.UUID
    brief_id: uuid.UUID
    brief_title: str
    user_id: uuid.UUID
    user_name: str


class ReportPayload(BaseModel):
    totals: ReportTotals
    briefs: list[ReportBriefRow]
    users: list[ReportUserRow]
    files: list[ReportFileRow]
