"""Guide section for game rules (FEAT-173).

Rules are split into three guide sections: site / roleplay / technobook.
The ALTER itself backfills every existing row with 'site' (NOT NULL DEFAULT),
so no separate UPDATE pass is needed — existing rules land in «Правила сайта».

Downgrade is an unconditional DROP COLUMN. Unlike migration 043 (which shrinks
an ENUM and must refuse while doomed rows exist), here the whole column goes
away: every rule survives intact and the page reverts to one undivided list,
i.e. the exact pre-feature state. A fail-fast guard would break rollback the
moment an admin files one rule under «Технобук». The section assignments are
lost, which is inherent to removing the column.

Revision ID: 044_game_rule_section
Revises: 043_gathering_ingredient
Create Date: 2026-09-20

"""
from alembic import op

# Revision id kept <= 32 chars (alembic_version_locations.version_num).
revision = '044_game_rule_section'
down_revision = '043_gathering_ingredient'
branch_labels = None
depends_on = None

SECTIONS = ('site', 'roleplay', 'technobook')
DEFAULT_SECTION = 'site'


def _enum(values) -> str:
    return "ENUM(" + ",".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE game_rules ADD COLUMN section "
        f"{_enum(SECTIONS)} NOT NULL DEFAULT '{DEFAULT_SECTION}' AFTER title"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE game_rules DROP COLUMN section")
