"""Add stat_preset and image columns to subraces, image column to races.
Seed existing 16 subraces stat_presets from presets.py data.

Revision ID: 002_add_race_subrace_columns
Revises: 001_initial_baseline
Create Date: 2026-03-19

"""
from alembic import op
import sqlalchemy as sa
import json

revision = '002_add_race_subrace_columns'
down_revision = '001_initial_baseline'
branch_labels = None
depends_on = None


# Stat presets for all 16 subraces (from presets.py)
SUBRACE_PRESETS = {
    1: {"strength": 20, "agility": 20, "intelligence": 10, "endurance": 10,
        "health": 10, "energy": 10, "mana": 0, "stamina": 10, "charisma": 0, "luck": 10},
    2: {"strength": 10, "agility": 30, "intelligence": 20, "endurance": 0,
        "health": 5, "energy": 5, "mana": 5, "stamina": 20, "charisma": 5, "luck": 10},
    3: {"strength": 10, "agility": 20, "intelligence": 10, "endurance": 20,
        "health": 0, "energy": 10, "mana": 0, "stamina": 10, "charisma": 0, "luck": 30},
    4: {"strength": 0, "agility": 30, "intelligence": 20, "endurance": 0,
        "health": 5, "energy": 10, "mana": 0, "stamina": 5, "charisma": 20, "luck": 10},
    5: {"strength": 15, "agility": 15, "intelligence": 15, "endurance": 15,
        "health": 0, "energy": 10, "mana": 10, "stamina": 5, "charisma": 0, "luck": 15},
    6: {"strength": 5, "agility": 15, "intelligence": 20, "endurance": 10,
        "health": 0, "energy": 0, "mana": 10, "stamina": 10, "charisma": 10, "luck": 20},
    7: {"strength": 30, "agility": 0, "intelligence": 0, "endurance": 30,
        "health": 20, "energy": 10, "mana": 0, "stamina": 10, "charisma": 0, "luck": 0},
    8: {"strength": 10, "agility": 30, "intelligence": 10, "endurance": 10,
        "health": 10, "energy": 5, "mana": 5, "stamina": 0, "charisma": 0, "luck": 20},
    9: {"strength": 20, "agility": 0, "intelligence": 20, "endurance": 10,
        "health": 20, "energy": 20, "mana": 5, "stamina": 5, "charisma": 0, "luck": 0},
    10: {"strength": 20, "agility": 0, "intelligence": 20, "endurance": 10,
         "health": 20, "energy": 20, "mana": 5, "stamina": 5, "charisma": 0, "luck": 0},
    11: {"strength": 30, "agility": 20, "intelligence": 0, "endurance": 0,
         "health": 10, "energy": 10, "mana": 0, "stamina": 10, "charisma": 0, "luck": 20},
    12: {"strength": 0, "agility": 20, "intelligence": 40, "endurance": 0,
         "health": 0, "energy": 20, "mana": 20, "stamina": 0, "charisma": 0, "luck": 0},
    13: {"strength": 20, "agility": 20, "intelligence": 0, "endurance": 20,
         "health": 5, "energy": 10, "mana": 10, "stamina": 5, "charisma": 0, "luck": 10},
    14: {"strength": 0, "agility": 40, "intelligence": 10, "endurance": 10,
         "health": 5, "energy": 10, "mana": 0, "stamina": 5, "charisma": 10, "luck": 10},
    15: {"strength": 40, "agility": 10, "intelligence": 0, "endurance": 30,
         "health": 10, "energy": 5, "mana": 0, "stamina": 5, "charisma": 0, "luck": 0},
    16: {"strength": 30, "agility": 20, "intelligence": 0, "endurance": 20,
         "health": 10, "energy": 10, "mana": 0, "stamina": 0, "charisma": 0, "luck": 10},
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Add columns to subraces table
    existing_columns = [c['name'] for c in inspector.get_columns('subraces')]
    if 'stat_preset' not in existing_columns:
        op.add_column('subraces', sa.Column('stat_preset', sa.JSON(), nullable=True))
    if 'image' not in existing_columns:
        op.add_column('subraces', sa.Column('image', sa.String(255), nullable=True))

    # Add image column to races table
    existing_race_columns = [c['name'] for c in inspector.get_columns('races')]
    if 'image' not in existing_race_columns:
        op.add_column('races', sa.Column('image', sa.String(255), nullable=True))

    # Seed stat_presets for existing 16 subraces
    for subrace_id, preset in SUBRACE_PRESETS.items():
        preset_json = json.dumps(preset)
        op.execute(
            sa.text(
                "UPDATE subraces SET stat_preset = :preset WHERE id_subrace = :sid"
            ).bindparams(preset=preset_json, sid=subrace_id)
        )


def downgrade() -> None:
    op.drop_column('subraces', 'stat_preset')
    op.drop_column('subraces', 'image')
    op.drop_column('races', 'image')
