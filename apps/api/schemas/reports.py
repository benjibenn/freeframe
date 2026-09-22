"""Response shapes for the superadmin reports page.

The payload carries FACTS, not counts: briefs with their submitters, submitters
with the day they accepted, and one row per file with its upload date. Every
number on the page is derived from these by the client.

That split is deliberate and was learned the hard way. The first version shipped
pre-aggregated all-time counts and let the client filter rows; a two-day date
range then kept a row whose last upload fell inside it and displayed that
person's LIFETIME totals next to the filter. Counts computed anywhere other than
where the filter is applied will eventually disagree with it.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReportSubmitter(BaseModel):
    user_id: uuid.UUID
    name: str
    # When this person accepted the brief — NOT when they uploaded anything.
    # Carried so a date range can scope "submissions" the same way it scopes
    # files, instead of leaving one all-time number in an otherwise scoped row.
    submitted_at: datetime


class ReportBriefRow(BaseModel):
    id: uuid.UUID
    title: str
    home_path: Optional[str] = None
    created_at: datetime
    is_enabled: bool
    persona_label: Optional[str] = None
    angle_label: Optional[str] = None
    submitters: list[ReportSubmitter]


class ReportUserRow(BaseModel):
    """Identity only. How many briefs this person worked on and how many files
    they delivered depends on the window being asked about, so it is derived
    where the window is known rather than fixed here."""

    user_id: uuid.UUID
    name: str
    email: str


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
    briefs: list[ReportBriefRow]
    users: list[ReportUserRow]
    files: list[ReportFileRow]
