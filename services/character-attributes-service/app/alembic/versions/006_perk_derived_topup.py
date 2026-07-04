"""Top up derived stat contributions for perks granted before derived
propagation existed (FEAT-143).

Legacy perks applied only the RAW flat bonus (e.g. +5 strength) without the
derived effects those points normally grant (physical resistances, dodge, etc.).
This one-time migration adds the missing derived contributions for every
currently-held perk, so the stored attributes match what the perk should give.
Future grants/revokes already handle derived, so this runs once (alembic guards
it by the version table).
"""
from alembic import op
import sqlalchemy as sa
import json

# revision identifiers
revision = '006_perk_derived_topup'
down_revision = '005_add_posts_quests_stats'
branch_labels = None
depends_on = None

B = 0.1          # STAT_BONUS_PER_POINT
END_MULT = 0.2   # ENDURANCE_RES_EFFECTS_MULTIPLIER
PHYS = ["res_physical", "res_catting", "res_crushing", "res_piercing"]
MAG = ["res_magic", "res_fire", "res_ice", "res_watering",
       "res_electricity", "res_wind", "res_sainting", "res_damning"]


def _derived_from_flat(flat: dict) -> dict:
    """Derived deltas a perk's primary-attribute flat bonuses should have granted."""
    out: dict = {}

    def add(k, v):
        out[k] = out.get(k, 0.0) + v

    s = flat.get("strength", 0) or 0
    if s:
        for f in PHYS:
            add(f, s * B)
    i = flat.get("intelligence", 0) or 0
    if i:
        for f in MAG:
            add(f, i * B)
    a = flat.get("agility", 0) or 0
    if a:
        add("dodge", a * B)
    e = flat.get("endurance", 0) or 0
    if e:
        add("res_effects", e * END_MULT)
    lk = flat.get("luck", 0) or 0
    if lk:
        add("dodge", lk * B)
        add("critical_hit_chance", lk * B)
        add("res_effects", lk * B)
    return out


def _accumulate(conn) -> dict:
    rows = conn.execute(sa.text(
        "SELECT cp.character_id, p.bonuses "
        "FROM character_perks cp JOIN perks p ON cp.perk_id = p.id"
    )).fetchall()
    per_char: dict = {}
    for character_id, bonuses in rows:
        if not bonuses:
            continue
        try:
            b = bonuses if isinstance(bonuses, dict) else json.loads(bonuses)
        except (ValueError, TypeError):
            continue
        flat = (b or {}).get("flat", {}) or {}
        deltas = _derived_from_flat(flat)
        if not deltas:
            continue
        acc = per_char.setdefault(character_id, {})
        for k, v in deltas.items():
            acc[k] = acc.get(k, 0.0) + v
    return per_char


def _apply(conn, per_char: dict, sign: str) -> None:
    for character_id, deltas in per_char.items():
        # Column names are fixed/whitelisted (resist/dodge/crit) — safe to inline.
        set_clause = ", ".join(f"{k} = {k} {sign} :{k}" for k in deltas)
        params = {**deltas, "cid": character_id}
        conn.execute(
            sa.text(f"UPDATE character_attributes SET {set_clause} WHERE character_id = :cid"),
            params,
        )


def upgrade():
    conn = op.get_bind()
    _apply(conn, _accumulate(conn), "+")


def downgrade():
    conn = op.get_bind()
    _apply(conn, _accumulate(conn), "-")
