"""FEAT-194: social classes of the residents and the wealth norm (economy).

* `econ_region_templates.class_poor / class_middling / class_rich` — the template's default class mix
                         (DECIMAL(6,4), sum 1); seeded per template (capital 35/45/20 ... rural 60/35/5).
* `econ_regions.class_poor / class_middling / class_rich` — the live mix (DECIMAL(9,6): a mobility step is
                         ~1e-4 ... 1e-5); NULL = no classes (regions without a template). Backfilled from the template.
* `econ_regions.class_dpoor / class_drich` — the shift of the last recount (admin «сдвиг за пересчёт»).
* `econ_regions.wealth_norm / last_wealth_tax` — the purse norm of the region (written by every recount) and the
                         wealth tax of the last recount.
* `econ_region_history.class_* / wealth_norm / wealth_tax` — per-recount history (NULL for older rows).
* `econ_goods_groups.class_demand_poor / _middling / _rich` — per-capita demand weights of the three classes
                         (DECIMAL(6,3)), seeded per group.
* `econ_event_templates` — the one-shot effect `class_shift` is appended to Бунт / Набег / Чума / Богатая жила /
                         Ярмарка (only when the template has none yet) and the new bad event «Разорение» (`ruin`) is
                         inserted when missing.

New sim params (`classes_enabled`, `class_*`, `wealth_tax_rate`, `mob_*`, `grant_deficit_share`) need no migration.
No new ledger op type (the wealth tax rides in the `region_tick` purse -> treasury leg).

No FK, no ENUM. Every statement is re-runnable (MySQL DDL is not transactional; column adds check
information_schema first, data seeds are idempotent). Downgrade drops the added columns, removes `class_shift`
entries from the template effects and deletes `ruin` when no event instance uses it (otherwise disables it); event
instances keep their snapshots (older code skips the unknown effect type with a warning).

Revision ID: 037_econ_social_classes
Revises: 036_econ_guild_orders
"""

import json

import sqlalchemy as sa
from alembic import op


revision = "037_econ_social_classes"
down_revision = "036_econ_guild_orders"
branch_labels = None
depends_on = None


# template code -> (poor, middling, rich)
TEMPLATE_CLASSES = {
    "capital": (0.35, 0.45, 0.20),
    "port": (0.45, 0.42, 0.13),
    "mining": (0.55, 0.37, 0.08),
    "agrarian": (0.55, 0.38, 0.07),
    "forest": (0.50, 0.42, 0.08),
    "magic": (0.30, 0.50, 0.20),
    "fortress": (0.45, 0.48, 0.07),
    "rural": (0.60, 0.35, 0.05),
}

# goods group code -> per-capita demand weights (poor, middling, rich)
GROUP_CLASS_DEMAND = {
    "food": (1.0, 1.0, 1.2),
    "ore_metal": (0.6, 1.0, 1.3),
    "wood": (1.0, 1.0, 1.2),
    "herbs": (0.6, 1.0, 1.5),
    "hides_textiles": (0.8, 1.0, 1.5),
    "magic": (0.1, 0.8, 4.0),
    "weapons": (0.2, 1.0, 2.0),
    "armor": (0.4, 1.0, 2.0),
    "jewelry": (0.05, 0.6, 6.0),
    "potions": (0.3, 1.0, 2.0),
    "tools": (0.6, 1.0, 1.2),
    "household": (0.6, 1.0, 2.5),
}

# event template code -> class_shift delta appended to its effects
EVENT_CLASS_SHIFTS = {
    "riot": -0.03,
    "raid": -0.02,
    "plague": -0.02,
    "rich_vein": 0.02,
    "fair": 0.01,
}

RUIN = {
    "code": "ruin", "name": "Разорение", "icon": "coins", "kind": "bad",
    "player_text": ("Купеческие дома разоряются один за другим: вчерашние богачи продают дома, "
                    "мастеровые идут в подёнщики."),
    "admin_note": ("Волна разорений: жители сползают в бедность (сдвиг классов вниз), "
                   "налогов меньше, падают достаток и стабильность."),
    "trigger_kind": "random", "weight": 1, "duration_min_days": 5, "duration_max_days": 10,
    "scope": "region", "spread_chance": 0,
    "region_templates": [], "seasons": [],
    "effects": [
        {"type": "class_shift", "delta": -0.06},
        {"type": "tax_income", "mult": 0.85},
        {"type": "prosperity", "delta": -1},
        {"type": "stability", "delta": -0.5},
    ],
    "chains": [],
}

_TEMPLATE_COLUMNS = (
    ("class_poor", "DECIMAL(6,4) NOT NULL DEFAULT 0.4500"),
    ("class_middling", "DECIMAL(6,4) NOT NULL DEFAULT 0.4500"),
    ("class_rich", "DECIMAL(6,4) NOT NULL DEFAULT 0.1000"),
)
_REGION_COLUMNS = (
    ("class_poor", "DECIMAL(9,6) NULL"),
    ("class_middling", "DECIMAL(9,6) NULL"),
    ("class_rich", "DECIMAL(9,6) NULL"),
    ("class_dpoor", "DECIMAL(9,6) NOT NULL DEFAULT 0"),
    ("class_drich", "DECIMAL(9,6) NOT NULL DEFAULT 0"),
    ("wealth_norm", "BIGINT NOT NULL DEFAULT 0"),
    ("last_wealth_tax", "BIGINT NOT NULL DEFAULT 0"),
)
_HISTORY_COLUMNS = (
    ("class_poor", "DECIMAL(9,6) NULL"),
    ("class_middling", "DECIMAL(9,6) NULL"),
    ("class_rich", "DECIMAL(9,6) NULL"),
    ("wealth_norm", "BIGINT NULL"),
    ("wealth_tax", "BIGINT NULL"),
)
_GROUP_COLUMNS = (
    ("class_demand_poor", "DECIMAL(6,3) NOT NULL DEFAULT 1.000"),
    ("class_demand_middling", "DECIMAL(6,3) NOT NULL DEFAULT 1.000"),
    ("class_demand_rich", "DECIMAL(6,3) NOT NULL DEFAULT 1.000"),
)


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def _add_columns(conn, table: str, columns) -> None:
    for name, ddl in columns:
        if not _has_column(conn, table, name):
            conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _drop_columns(conn, table: str, columns) -> None:
    for name, _ddl in reversed(columns):
        if _has_column(conn, table, name):
            conn.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {name}"))


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _effects(raw):
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw if isinstance(raw, list) else None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. templates: default class mix
    _add_columns(conn, "econ_region_templates", _TEMPLATE_COLUMNS)
    for code, (poor, middling, rich) in TEMPLATE_CLASSES.items():
        conn.execute(sa.text(
            "UPDATE econ_region_templates SET class_poor = :p, class_middling = :m, class_rich = :r "
            "WHERE code = :code AND class_poor = 0.4500 AND class_middling = 0.4500 AND class_rich = 0.1000"
        ), {"p": poor, "m": middling, "r": rich, "code": code})

    # 2. regions: live mix (backfilled from the template), shift of the last recount, wealth norm / tax
    _add_columns(conn, "econ_regions", _REGION_COLUMNS)
    conn.execute(sa.text(
        "UPDATE econ_regions e JOIN econ_region_templates t ON t.code = e.template_code "
        "SET e.class_poor = t.class_poor, e.class_middling = t.class_middling, e.class_rich = t.class_rich "
        "WHERE e.class_poor IS NULL"
    ))

    # 3. history
    _add_columns(conn, "econ_region_history", _HISTORY_COLUMNS)

    # 4. goods groups: per-class demand weights (only rows still at the column default)
    _add_columns(conn, "econ_goods_groups", _GROUP_COLUMNS)
    for code, (poor, middling, rich) in GROUP_CLASS_DEMAND.items():
        conn.execute(sa.text(
            "UPDATE econ_goods_groups SET class_demand_poor = :p, class_demand_middling = :m, "
            "class_demand_rich = :r WHERE code = :code AND class_demand_poor = 1.000 "
            "AND class_demand_middling = 1.000 AND class_demand_rich = 1.000"
        ), {"p": poor, "m": middling, "r": rich, "code": code})

    # 5. event templates: class_shift appended where missing, the new «Разорение»
    has_events = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = 'econ_event_templates'"
    )).scalar()
    if not has_events:
        return
    for code, delta in EVENT_CLASS_SHIFTS.items():
        row = conn.execute(sa.text("SELECT id, effects FROM econ_event_templates WHERE code = :code"),
                           {"code": code}).first()
        if row is None:
            continue
        effects = _effects(row[1])
        if effects is None or any(isinstance(e, dict) and e.get("type") == "class_shift" for e in effects):
            continue
        effects.append({"type": "class_shift", "delta": delta})
        conn.execute(sa.text("UPDATE econ_event_templates SET effects = :effects WHERE id = :id"),
                     {"effects": _json(effects), "id": int(row[0])})
    t = RUIN
    conn.execute(sa.text("""
        INSERT INTO econ_event_templates
          (code, name, icon, kind, player_text, admin_note, trigger_kind, weight, duration_min_days,
           duration_max_days, scope, spread_chance, region_templates, seasons, effects, chains, is_enabled)
        SELECT :code, :name, :icon, :kind, :player_text, :admin_note, :trigger_kind, :weight, :dmin,
               :dmax, :scope, :spread, :region_templates, :seasons, :effects, :chains, 1
        FROM DUAL
        WHERE NOT EXISTS (SELECT 1 FROM econ_event_templates WHERE code = :code)
    """), {
        "code": t["code"], "name": t["name"], "icon": t["icon"], "kind": t["kind"],
        "player_text": t["player_text"], "admin_note": t["admin_note"], "trigger_kind": t["trigger_kind"],
        "weight": t["weight"], "dmin": t["duration_min_days"], "dmax": t["duration_max_days"],
        "scope": t["scope"], "spread": t["spread_chance"],
        "region_templates": _json(t["region_templates"]), "seasons": _json(t["seasons"]),
        "effects": _json(t["effects"]), "chains": _json(t["chains"]),
    })


def downgrade() -> None:
    conn = op.get_bind()
    has_events = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = 'econ_event_templates'"
    )).scalar()
    if has_events:
        used = conn.execute(sa.text(
            "SELECT COUNT(*) FROM econ_region_events WHERE template_code = :code"), {"code": RUIN["code"]}).scalar()
        if used:
            conn.execute(sa.text("UPDATE econ_event_templates SET is_enabled = 0 WHERE code = :code"),
                         {"code": RUIN["code"]})
        else:
            conn.execute(sa.text("DELETE FROM econ_event_templates WHERE code = :code"), {"code": RUIN["code"]})
        for row in conn.execute(sa.text("SELECT id, effects FROM econ_event_templates")).fetchall():
            effects = _effects(row[1])
            if effects is None:
                continue
            kept = [e for e in effects if not (isinstance(e, dict) and e.get("type") == "class_shift")]
            if len(kept) != len(effects):
                conn.execute(sa.text("UPDATE econ_event_templates SET effects = :effects WHERE id = :id"),
                             {"effects": _json(kept), "id": int(row[0])})
    _drop_columns(conn, "econ_goods_groups", _GROUP_COLUMNS)
    _drop_columns(conn, "econ_region_history", _HISTORY_COLUMNS)
    _drop_columns(conn, "econ_regions", _REGION_COLUMNS)
    _drop_columns(conn, "econ_region_templates", _TEMPLATE_COLUMNS)
