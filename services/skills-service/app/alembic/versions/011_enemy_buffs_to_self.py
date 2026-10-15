"""Move enemy-targeted buffs onto the caster (data fix)

Revision ID: 011_enemy_buffs_to_self
Revises: 010_effect_secondary_mag
Create Date: 2026-10-16

The effect audit of 2026-10-16 found skill and perk effects aimed at the ENEMY
with a POSITIVE value that strengthens them: +crit chance, +crit damage,
+dodge, +damage buff, +resist, +primary attribute. They were data-entry
mistakes — the designer meant the caster ("Прыжок за спину: крит +15" is a buff
for this very strike). Most of them used `dodge_chance` / `crit_damage`, which
the battle engine did not read until the same audit fixed those keys, so they
did nothing before; from now on they would have buffed the opponent. The user
decided to move every one of them onto the caster.

Rows are picked by what they are, not by id: the dev DB is an older prod dump
and ids may have drifted. Resource rows (`hp`, `mana`, `energy`, `stamina`) are
left alone — on an enemy the engine already turns a positive value into damage.
Damage-over-time, control and the debuff complex effects (Electrify, Freeze, …)
carry their direction in the name, so they are not touched either.

Downgrade is a no-op: once moved, a row cannot be told apart from an effect
that was authored on the caster in the first place.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '011_enemy_buffs_to_self'
down_revision = '010_effect_secondary_mag'
branch_labels = None
depends_on = None


TABLES = ('skill_base_effects', 'skill_perk_effects')

BUFFING_ENEMY_EFFECT = """
    target_side IN ('enemy', 'all_enemies')
    AND magnitude > 0
    AND (
        effect_name LIKE 'Buff:%'
        OR effect_name LIKE 'Resist:%'
        OR effect_name = 'MagicImpact'
        OR (effect_name = 'StatModifier'
            AND attribute_key NOT IN ('hp', 'mana', 'energy', 'stamina'))
    )
"""


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"UPDATE {table} SET target_side = 'self' WHERE {BUFFING_ENEMY_EFFECT}")


def downgrade() -> None:
    # Irreversible data fix — see the module docstring.
    pass
