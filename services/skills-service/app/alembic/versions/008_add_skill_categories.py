"""Add subclass scoping and the mob-skill flag to skills

Revision ID: 008_skill_categories
Revises: 007_aoe_damage
Create Date: 2026-09-06

The admin skill list is being split into categories, and two of them had
nowhere to live:

- `subclass_limitations` — comma-separated subclass keys (see subclasses.py),
  matching how `class_limitations` already stores class ids. A skill scoped to
  a subclass belongs to that subclass alone, not to its parent class.
- `is_mob_skill` — mob skills are kept apart from the players' categories
  entirely, so the two never mix in a list or in a picker.

Both default to "no category", so every existing skill keeps the meaning it
has today. Inspector-guarded, like the migrations before it, so it is safe to
re-run against a partially migrated dev database.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008_skill_categories'
down_revision = '007_aoe_damage'
branch_labels = None
depends_on = None


TABLE = 'skills'
NEW_COLUMNS = (
    ('subclass_limitations', sa.String(length=255), True, None),
    ('is_mob_skill', sa.Boolean(), False, '0'),
)


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c['name'] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    for name, col_type, nullable, default in NEW_COLUMNS:
        if _has_column(inspector, TABLE, name):
            continue
        op.add_column(
            TABLE,
            sa.Column(name, col_type, nullable=nullable, server_default=default),
        )

    # The mob/player split is the first thing every admin list filters on.
    existing_indexes = {ix['name'] for ix in inspector.get_indexes(TABLE)}
    if 'ix_skills_is_mob_skill' not in existing_indexes:
        op.create_index('ix_skills_is_mob_skill', TABLE, ['is_mob_skill'])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_indexes = {ix['name'] for ix in inspector.get_indexes(TABLE)}
    if 'ix_skills_is_mob_skill' in existing_indexes:
        op.drop_index('ix_skills_is_mob_skill', table_name=TABLE)
    for name, _type, _nullable, _default in NEW_COLUMNS:
        if _has_column(inspector, TABLE, name):
            op.drop_column(TABLE, name)
