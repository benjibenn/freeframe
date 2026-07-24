"""widen brief_template script columns to accept script_voiceover aliases

Revision ID: e5f6a7b8c9d0
Revises: 06f7c6e1b1dc
Create Date: 2026-07-24

The seeded template rendered the script column from field `script`, but briefs authored
by external AI writers emit `script_voiceover` (and occasionally `voiceover`). The render
column now supports a `keys` fallback list, so this migration upgrades the existing
singleton's script columns in-place: any column keyed `script` gains the alias list and
the header "Script (Voiceover & Subtitle)". Idempotent and header-preserving-agnostic —
it only rewrites columns still on the old single-key `script` shape.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = '06f7c6e1b1dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCRIPT_KEYS = ["script_voiceover", "script", "voiceover"]
SCRIPT_HEADER = "Script (Voiceover & Subtitle)"

brief_templates = sa.table(
    'brief_templates',
    sa.column('id', postgresql.UUID(as_uuid=True)),
    sa.column('sections', postgresql.JSONB()),
)


def _map_columns(sections, fn):
    changed = False
    new_sections = []
    for section in sections or []:
        if isinstance(section, dict) and isinstance(section.get('columns'), list):
            section = dict(section)
            new_cols = []
            for col in section['columns']:
                new_col, col_changed = fn(col)
                changed = changed or col_changed
                new_cols.append(new_col)
            section['columns'] = new_cols
        new_sections.append(section)
    return new_sections, changed


def _upgrade_col(col):
    if isinstance(col, dict) and col.get('key') == 'script' and not col.get('keys'):
        return {**col, 'keys': list(SCRIPT_KEYS), 'header': SCRIPT_HEADER}, True
    return col, False


def _downgrade_col(col):
    if isinstance(col, dict) and col.get('key') == 'script' and col.get('keys') == SCRIPT_KEYS:
        reverted = {k: v for k, v in col.items() if k != 'keys'}
        reverted['header'] = 'Script'
        return reverted, True
    return col, False


def _apply(fn):
    conn = op.get_bind()
    for row_id, sections in conn.execute(sa.select(brief_templates.c.id, brief_templates.c.sections)):
        new_sections, changed = _map_columns(sections, fn)
        if changed:
            conn.execute(
                brief_templates.update().where(brief_templates.c.id == row_id).values(sections=new_sections)
            )


def upgrade() -> None:
    _apply(_upgrade_col)


def downgrade() -> None:
    _apply(_downgrade_col)
