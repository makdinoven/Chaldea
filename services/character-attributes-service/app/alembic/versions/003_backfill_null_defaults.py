"""Backfill NULL values with proper defaults for old characters

Revision ID: 003_backfill_null_defaults
Revises: 002_change_stamina_defaults
Create Date: 2026-03-22

"""
from alembic import op

revision = '003_backfill_null_defaults'
down_revision = '002_change_stamina_defaults'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Vulnerability fields
    for col in [
        'vul_effects', 'vul_physical', 'vul_catting', 'vul_crushing',
        'vul_piercing', 'vul_magic', 'vul_fire', 'vul_ice',
        'vul_watering', 'vul_electricity', 'vul_sainting', 'vul_wind',
        'vul_damning',
    ]:
        op.execute(f"UPDATE character_attributes SET {col} = 0.0 WHERE {col} IS NULL")

    # Resistance fields
    for col in [
        'res_effects', 'res_physical', 'res_catting', 'res_crushing',
        'res_piercing', 'res_magic', 'res_fire', 'res_ice',
        'res_watering', 'res_electricity', 'res_sainting', 'res_wind',
        'res_damning',
    ]:
        op.execute(f"UPDATE character_attributes SET {col} = 0.0 WHERE {col} IS NULL")

    # Combat stats
    op.execute("UPDATE character_attributes SET dodge = 5.0 WHERE dodge IS NULL")
    op.execute("UPDATE character_attributes SET critical_hit_chance = 20.0 WHERE critical_hit_chance IS NULL")
    op.execute("UPDATE character_attributes SET critical_damage = 125 WHERE critical_damage IS NULL")
    op.execute("UPDATE character_attributes SET damage = 0 WHERE damage IS NULL")

    # Experience
    op.execute("UPDATE character_attributes SET passive_experience = 0 WHERE passive_experience IS NULL")
    op.execute("UPDATE character_attributes SET active_experience = 0 WHERE active_experience IS NULL")

    # Resource fields
    op.execute("UPDATE character_attributes SET current_health = 100 WHERE current_health IS NULL")
    op.execute("UPDATE character_attributes SET max_health = 100 WHERE max_health IS NULL")
    op.execute("UPDATE character_attributes SET current_mana = 75 WHERE current_mana IS NULL")
    op.execute("UPDATE character_attributes SET max_mana = 75 WHERE max_mana IS NULL")
    op.execute("UPDATE character_attributes SET current_energy = 50 WHERE current_energy IS NULL")
    op.execute("UPDATE character_attributes SET max_energy = 50 WHERE max_energy IS NULL")
    op.execute("UPDATE character_attributes SET current_stamina = 100 WHERE current_stamina IS NULL")
    op.execute("UPDATE character_attributes SET max_stamina = 100 WHERE max_stamina IS NULL")


def downgrade() -> None:
    # No downgrade — we cannot know which values were originally NULL
    pass
