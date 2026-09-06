"""Seed the universal subrace placeholder skill (id 7)

Revision ID: 009_subrace_skill
Revises: 008_skill_categories
Create Date: 2026-09-06

character-service hands every approved character a universal "subrace" skill
on top of its class starter kit (`SUBRACE_SKILL_ID = 7` in
`services/character-service/app/main.py`). That row was dropped from the
`skills` table at some point, so approvals have been logging "Навык 7 не
найден" and silently granting the class kit alone.

This migration restores a placeholder under the same explicit id so the
mechanic works again. It is a stopgap: a later feature replaces it with real
per-race skills and passives.

Safety notes:
- id 7 is free in the production data (ids run 1..243 with 4 and 7 missing)
  and AUTO_INCREMENT sits at 244, so an explicit insert collides with nothing.
- `skills.name` is UNIQUE, so the insert is guarded on both id and name.
- `skill_type` is stored lowercase ("support"), matching the 64 support skills
  already in the table — the column has no lowercase-only constraint, so a
  lone differently-cased row would silently fall out of any case-sensitive
  filter, GROUP BY or DISTINCT built on it.
- Idempotent: re-running `upgrade` inserts nothing when the row is already
  there. `downgrade` removes the row only when it is still this placeholder
  (matched on id *and* name), so a hand-made real skill is never destroyed.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009_subrace_skill'
down_revision = '008_skill_categories'
branch_labels = None
depends_on = None


SKILL_ID = 7
SKILL_NAME = "Выживание"
SKILL_TYPE = "support"
SKILL_DESCRIPTION = (
    "Базовый навык выживания, которому обучают каждого новобранца Скитальцев: "
    "умение найти воду и укрытие, развести огонь и продержаться в дороге до "
    "следующего привала."
)
SKILL_COST_ENERGY = 8
SKILL_COOLDOWN = 3


def upgrade() -> None:
    bind = op.get_bind()

    existing = bind.execute(
        sa.text(
            "SELECT id FROM skills WHERE id = :skill_id OR name = :name LIMIT 1"
        ),
        {"skill_id": SKILL_ID, "name": SKILL_NAME},
    ).first()
    if existing is not None:
        # Either the placeholder is already seeded, or someone claimed the id
        # or the (unique) name in the meantime — leave the data alone.
        return

    bind.execute(
        sa.text(
            """
            INSERT INTO skills (
                id, name, skill_type, description,
                class_limitations, subclass_limitations,
                race_limitations, subrace_limitations, is_mob_skill,
                min_level, purchase_cost, skill_image,
                cost_energy, cost_mana, cooldown, level_requirement
            ) VALUES (
                :skill_id, :name, :skill_type, :description,
                NULL, NULL,
                NULL, NULL, 0,
                1, 0, NULL,
                :cost_energy, 0, :cooldown, 1
            )
            """
        ),
        {
            "skill_id": SKILL_ID,
            "name": SKILL_NAME,
            "skill_type": SKILL_TYPE,
            "description": SKILL_DESCRIPTION,
            "cost_energy": SKILL_COST_ENERGY,
            "cooldown": SKILL_COOLDOWN,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text("DELETE FROM skills WHERE id = :skill_id AND name = :name"),
        {"skill_id": SKILL_ID, "name": SKILL_NAME},
    )
