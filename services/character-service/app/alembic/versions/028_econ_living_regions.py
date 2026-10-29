"""FEAT-182 stage 2: living regions — goods groups, chains, region templates, per-region
economy state, tick runs, history, item -> group overrides, simulation settings.

Tables (all owned by character-service; no FK to Regions / items — other owners):
* `econ_goods_groups`      — the 12 goods groups (seeded, edit only).
* `econ_group_inputs`      — production chains: 1 unit of a group needs `ratio` units of input.
* `econ_region_templates`  — 8 region profiles (seeded) with the settlement noun + its gender
                             («Город сыт», «Крепость сыта», «Округа голодает»).
* `econ_template_goods`    — 8 × 12 production / consumption multipliers (seeded, computed below).
* `econ_regions`           — economy state per region (no rows seeded: every region starts
                             outside the simulation, template NULL).
* `econ_region_goods`      — per region × group stock / price.
* `econ_tick_runs`         — one row per tick run (UNIQUE slot for auto runs).
* `econ_region_history`    — per region snapshot after every tick.
* `econ_item_groups`       — admin overrides of item -> group / off-market.
* `econ_sim_settings`      — singleton id=1: tick toggle + simulation params JSON.

Template goods seed: `production_per_1000 = ratio × need_per_1000`, where for finished groups
`need = norm · cmult` and for raw groups `need = norm · cmult + Σ(finished production · input ratio)`
(rounded to 3 decimals). Everything is self-contained here (no import of econ_core / econ_sim).

Every statement is re-runnable (CREATE TABLE IF NOT EXISTS + INSERT IGNORE) because MySQL DDL
is not transactional. Downgrade drops the tables; no ledger rows are touched.

Revision ID: 028_econ_living_regions
Revises: 027_world_economy
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "028_econ_living_regions"
down_revision = "027_world_economy"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"

# (code, name, base_price, norm_per_1000, norm_days, prosperity_elasticity, price_elasticity, is_food)
# Order = sort order = econ_core.GOODS_GROUPS.
GROUPS = [
    ("food", "Продовольствие", 2, 300, 7, 0, 0.1, 1),
    ("ore_metal", "Руда и металл", 10, 4, 14, 0.2, 0.3, 0),
    ("wood", "Древесина", 5, 15, 14, 0.2, 0.3, 0),
    ("herbs", "Травы и реагенты", 8, 4, 14, 0.3, 0.3, 0),
    ("hides_textiles", "Шкуры и ткани", 10, 5, 14, 0.3, 0.3, 0),
    ("magic", "Магические материалы", 40, 0.5, 21, 0.8, 0.5, 0),
    ("weapons", "Оружие", 120, 0.2, 21, 0.5, 0.5, 0),
    ("armor", "Броня и одежда", 100, 0.4, 21, 0.5, 0.5, 0),
    ("jewelry", "Украшения", 200, 0.1, 28, 1.0, 0.6, 0),
    ("potions", "Зелья", 30, 1.0, 14, 0.6, 0.4, 0),
    ("tools", "Ремесленный инвентарь", 40, 0.5, 21, 0.3, 0.4, 0),
    ("household", "Быт и мебель", 80, 0.4, 28, 0.6, 0.5, 0),
]
GROUP_CODES = [g[0] for g in GROUPS]
NORM = {g[0]: g[3] for g in GROUPS}

# Production chains: group -> [(input, units of input per unit of group)]. All inputs are raw groups.
INPUTS = {
    "weapons": [("ore_metal", 3)],
    "armor": [("hides_textiles", 2), ("ore_metal", 1)],
    "jewelry": [("ore_metal", 1), ("magic", 0.5)],
    "potions": [("herbs", 2)],
    "tools": [("ore_metal", 1), ("wood", 1)],
    "household": [("wood", 3), ("hides_textiles", 0.5)],
}

# (code, name, description, settlement_noun, noun_gender, default_population, tax_rate)
TEMPLATES = [
    ("capital", "Столица", "Крупный город: ремёсла и роскошь, сырьё привозное.",
     "Город", "m", 25000, 0.12),
    ("port", "Портовый", "Портовый город: рыба, ткани, шкуры; умеренное ремесло.",
     "Порт", "m", 12000, 0.10),
    ("mining", "Шахтёрский", "Горное поселение: много руды и инструментов, мало трав и еды.",
     "Город", "m", 6000, 0.10),
    ("agrarian", "Аграрный", "Земледельческий край: житница с избытком продовольствия.",
     "Край", "m", 8000, 0.08),
    ("forest", "Лесной", "Лесной край: древесина, травы, шкуры и мебель.",
     "Край", "m", 4000, 0.08),
    ("magic", "Магический", "Город магов: магические материалы и зелья, нужда в травах.",
     "Город", "m", 7000, 0.12),
    ("fortress", "Пограничная крепость", "Гарнизон на границе: оружие и броня, своей еды не хватает.",
     "Крепость", "f", 3000, 0.06),
    ("rural", "Сельская округа", "Мелкие деревни — поставщики сырья и еды.",
     "Округа", "f", 2500, 0.06),
]

# Production ratio per template (order = GROUP_CODES). > 1 specialty, < 1 chronic shortage.
RATIOS = {
    "capital":  [0.95, 0.8, 0.8, 0.8, 0.9, 1.0, 1.2, 1.2, 1.4, 1.2, 1.2, 1.3],
    "port":     [1.1, 0.7, 0.9, 1.0, 1.3, 0.8, 0.9, 1.0, 1.1, 1.0, 1.1, 1.1],
    "mining":   [0.9, 2.0, 1.0, 0.6, 0.8, 1.2, 1.3, 1.1, 1.2, 0.7, 1.4, 0.8],
    "agrarian": [1.5, 0.5, 1.0, 1.3, 1.3, 0.5, 0.6, 0.8, 0.5, 1.0, 0.9, 0.9],
    "forest":   [1.05, 0.5, 2.2, 1.6, 1.5, 1.0, 0.7, 0.9, 0.6, 1.2, 1.0, 1.6],
    "magic":    [0.95, 0.7, 0.8, 1.4, 0.7, 2.2, 0.7, 0.7, 1.4, 1.8, 0.9, 1.0],
    "fortress": [0.85, 1.1, 1.1, 0.8, 1.0, 0.6, 1.6, 1.6, 0.3, 1.0, 1.0, 0.5],
    "rural":    [1.3, 0.6, 1.3, 1.3, 1.2, 0.4, 0.4, 0.6, 0.3, 0.8, 0.8, 0.8],
}

# Consumption multipliers that differ from 1.0.
CMULT = {
    "capital": {"magic": 1.3, "jewelry": 1.3, "potions": 1.3, "household": 1.3},
    "port": {"jewelry": 1.1},
    "mining": {"food": 1.1, "tools": 1.5},
    "agrarian": {"jewelry": 0.6, "magic": 0.6},
    "magic": {"magic": 2.0, "potions": 1.5},
    "fortress": {"weapons": 3.0, "armor": 3.0, "potions": 2.0, "jewelry": 0.3, "household": 0.5},
    "rural": {"jewelry": 0.4, "magic": 0.4, "weapons": 0.5, "household": 0.7},
}

# econ_sim_settings.params defaults (FEAT-182 3.4) — a frozen copy of econ_sim.SimParams().to_dict()
# at the time of this migration. Validated/extended by schemas.EconSimParams (missing keys -> defaults).
DEFAULT_PARAMS = {
    "dt": 0.25,
    "price_min": 0.5,
    "price_max": 3.0,
    "price_exponent": 0.631,
    "stock_cap_mult": 3.0,
    "prod_price_elasticity": 0.15,
    "prod_price_min": 0.85,
    "prod_price_max": 1.3,
    "full_stability": 60.0,
    "hunger_prod_penalty": 0.5,
    "afford_days": 1.0,
    "treasury_reserve_days": 7.0,
    "treasury_release_ticks": 8,
    "country_grant_share": 0.25,
    "purse_start_days": 7.0,
    "stab_base": 85.0,
    "stab_hunger_w": 100.0,
    "stab_goods_w": 15.0,
    "stab_free_tax": 0.12,
    "stab_tax_w": 200.0,
    "stab_debt_penalty": 10.0,
    "stab_rate_up": 0.08,
    "stab_rate_down": 0.25,
    "prosp_rate": 0.05,
    "prosp_w_sat": 0.3,
    "prosp_w_liq": 0.4,
    "prosp_w_stab": 0.15,
    "prosp_hunger_w": 60.0,
    "prosp_liq_days": 14.0,
    "history_retention_days": 60,
}


def template_goods(template_code: str):
    """Return [(group_code, production_per_1000, consumption_mult)] for a template (3.4 rule)."""
    ratios = dict(zip(GROUP_CODES, RATIOS[template_code]))
    cmult = {code: CMULT.get(template_code, {}).get(code, 1.0) for code in GROUP_CODES}
    production = {}
    # Finished groups first: need = norm · cmult.
    for code in INPUTS:
        production[code] = ratios[code] * NORM[code] * cmult[code]
    # Raw groups: need = household need + inputs consumed by local finished production.
    for code in GROUP_CODES:
        if code in INPUTS:
            continue
        need = NORM[code] * cmult[code]
        for finished, inputs in INPUTS.items():
            for input_code, ratio in inputs:
                if input_code == code:
                    need += production[finished] * ratio
        production[code] = ratios[code] * need
    return [(code, round(production[code], 3), cmult[code]) for code in GROUP_CODES]


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_goods_groups (
          code                  VARCHAR(32)   NOT NULL PRIMARY KEY,
          name                  VARCHAR(100)  NOT NULL,
          sort_order            SMALLINT      NOT NULL DEFAULT 0,
          is_food               TINYINT(1)    NOT NULL DEFAULT 0,
          base_price            INT           NOT NULL,
          norm_per_1000         DECIMAL(10,3) NOT NULL,
          norm_days             DECIMAL(6,2)  NOT NULL,
          prosperity_elasticity DECIMAL(5,3)  NOT NULL DEFAULT 0,
          price_elasticity      DECIMAL(5,3)  NOT NULL DEFAULT 0,
          updated_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_group_inputs (
          group_code VARCHAR(32)  NOT NULL,
          input_code VARCHAR(32)  NOT NULL,
          ratio      DECIMAL(6,3) NOT NULL,
          PRIMARY KEY (group_code, input_code),
          KEY ix_econ_group_inputs_input (input_code),
          CONSTRAINT fk_egi_group FOREIGN KEY (group_code) REFERENCES econ_goods_groups (code),
          CONSTRAINT fk_egi_input FOREIGN KEY (input_code) REFERENCES econ_goods_groups (code),
          CONSTRAINT ck_egi_ratio CHECK (ratio > 0)
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_region_templates (
          code               VARCHAR(32)  NOT NULL PRIMARY KEY,
          name               VARCHAR(100) NOT NULL,
          description        VARCHAR(500) NULL,
          settlement_noun    VARCHAR(50)  NOT NULL,
          noun_gender        CHAR(1)      NOT NULL DEFAULT 'm',
          default_population INT          NOT NULL,
          tax_rate           DECIMAL(5,4) NOT NULL,
          sort_order         SMALLINT     NOT NULL DEFAULT 0,
          updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          CONSTRAINT ck_ert_noun_gender CHECK (noun_gender IN ('m', 'f', 'n'))
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_template_goods (
          template_code       VARCHAR(32)   NOT NULL,
          group_code          VARCHAR(32)   NOT NULL,
          production_per_1000 DECIMAL(12,3) NOT NULL DEFAULT 0,
          consumption_mult    DECIMAL(5,3)  NOT NULL DEFAULT 1,
          PRIMARY KEY (template_code, group_code),
          KEY ix_etg_group (group_code),
          CONSTRAINT fk_etg_template FOREIGN KEY (template_code) REFERENCES econ_region_templates (code)
            ON DELETE CASCADE,
          CONSTRAINT fk_etg_group FOREIGN KEY (group_code) REFERENCES econ_goods_groups (code)
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_regions (
          region_id       BIGINT       NOT NULL PRIMARY KEY,
          template_code   VARCHAR(32)  NULL,
          population      INT          NOT NULL DEFAULT 0,
          tax_rate        DECIMAL(5,4) NOT NULL DEFAULT 0.1000,
          stability       DECIMAL(5,2) NOT NULL DEFAULT 70,
          prosperity      DECIMAL(5,2) NOT NULL DEFAULT 50,
          hunger          DECIMAL(5,4) NOT NULL DEFAULT 0,
          satisfaction    DECIMAL(5,4) NOT NULL DEFAULT 1,
          treasury_target BIGINT       NOT NULL DEFAULT 0,
          last_income     BIGINT       NOT NULL DEFAULT 0,
          last_tax        BIGINT       NOT NULL DEFAULT 0,
          last_wages      BIGINT       NOT NULL DEFAULT 0,
          last_grant      BIGINT       NOT NULL DEFAULT 0,
          last_run_id     BIGINT       NULL,
          last_tick_at    DATETIME     NULL,
          updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY ix_econ_regions_template (template_code),
          CONSTRAINT fk_econ_regions_template FOREIGN KEY (template_code)
            REFERENCES econ_region_templates (code) ON DELETE SET NULL
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_region_goods (
          region_id           BIGINT        NOT NULL,
          group_code          VARCHAR(32)   NOT NULL,
          production_per_1000 DECIMAL(12,3) NOT NULL DEFAULT 0,
          consumption_mult    DECIMAL(5,3)  NOT NULL DEFAULT 1,
          stock               DECIMAL(16,3) NOT NULL DEFAULT 0,
          norm_stock          DECIMAL(16,3) NOT NULL DEFAULT 0,
          price_mult          DECIMAL(6,3)  NOT NULL DEFAULT 1,
          prev_price_mult     DECIMAL(6,3)  NOT NULL DEFAULT 1,
          last_produced       DECIMAL(14,3) NOT NULL DEFAULT 0,
          last_consumed       DECIMAL(14,3) NOT NULL DEFAULT 0,
          last_demand         DECIMAL(14,3) NOT NULL DEFAULT 0,
          last_spoiled        DECIMAL(14,3) NOT NULL DEFAULT 0,
          PRIMARY KEY (region_id, group_code),
          KEY ix_erg_group (group_code),
          CONSTRAINT fk_erg_region FOREIGN KEY (region_id) REFERENCES econ_regions (region_id) ON DELETE CASCADE,
          CONSTRAINT fk_erg_group FOREIGN KEY (group_code) REFERENCES econ_goods_groups (code)
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_tick_runs (
          id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
          slot           BIGINT       NULL,
          trigger_kind   VARCHAR(10)  NOT NULL,
          actor_user_id  INT          NULL,
          status         VARCHAR(10)  NOT NULL,
          grant_plan     JSON         NULL,
          regions_total  INT          NOT NULL DEFAULT 0,
          regions_done   INT          NOT NULL DEFAULT 0,
          regions_failed INT          NOT NULL DEFAULT 0,
          error          VARCHAR(500) NULL,
          started_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          heartbeat_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          finished_at    DATETIME     NULL,
          UNIQUE KEY uq_econ_tick_runs_slot (slot),
          KEY ix_econ_tick_runs_started (started_at)
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_region_history (
          id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
          run_id       BIGINT       NOT NULL,
          region_id    BIGINT       NOT NULL,
          created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          population   INT          NOT NULL,
          stability    DECIMAL(5,2) NOT NULL,
          prosperity   DECIMAL(5,2) NOT NULL,
          hunger       DECIMAL(5,4) NOT NULL,
          purse        BIGINT       NOT NULL,
          treasury     BIGINT       NOT NULL,
          income       BIGINT       NOT NULL,
          tax          BIGINT       NOT NULL,
          wages        BIGINT       NOT NULL,
          grant_amount BIGINT       NOT NULL,
          goods        JSON         NOT NULL,
          KEY ix_erh_run (run_id),
          KEY ix_erh_region_created (region_id, created_at),
          CONSTRAINT fk_erh_run FOREIGN KEY (run_id) REFERENCES econ_tick_runs (id) ON DELETE CASCADE
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_item_groups (
          item_id            BIGINT      NOT NULL PRIMARY KEY,
          group_code         VARCHAR(32) NULL,
          off_market         TINYINT(1)  NULL,
          updated_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          updated_by_user_id INT         NULL,
          KEY ix_eig_group (group_code),
          CONSTRAINT fk_eig_group FOREIGN KEY (group_code) REFERENCES econ_goods_groups (code)
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_sim_settings (
          id                 TINYINT    NOT NULL PRIMARY KEY,
          tick_enabled       TINYINT(1) NOT NULL DEFAULT 1,
          params             JSON       NOT NULL,
          updated_at         DATETIME   NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          updated_by_user_id INT        NULL
        ) {_TABLE_OPTS}
    """))

    _seed(conn)


def _seed(conn) -> None:
    for sort_order, (code, name, base_price, norm, days, prosp_el, price_el, is_food) in enumerate(GROUPS, 1):
        conn.execute(sa.text(
            "INSERT IGNORE INTO econ_goods_groups "
            "(code, name, sort_order, is_food, base_price, norm_per_1000, norm_days, "
            " prosperity_elasticity, price_elasticity) "
            "VALUES (:code, :name, :sort, :food, :price, :norm, :days, :pe, :pre)"
        ), {"code": code, "name": name, "sort": sort_order, "food": is_food, "price": base_price,
            "norm": norm, "days": days, "pe": prosp_el, "pre": price_el})

    for group_code, inputs in INPUTS.items():
        for input_code, ratio in inputs:
            conn.execute(sa.text(
                "INSERT IGNORE INTO econ_group_inputs (group_code, input_code, ratio) "
                "VALUES (:g, :i, :r)"
            ), {"g": group_code, "i": input_code, "r": ratio})

    for sort_order, (code, name, descr, noun, gender, pop, tax) in enumerate(TEMPLATES, 1):
        conn.execute(sa.text(
            "INSERT IGNORE INTO econ_region_templates "
            "(code, name, description, settlement_noun, noun_gender, default_population, tax_rate, sort_order) "
            "VALUES (:code, :name, :descr, :noun, :gender, :pop, :tax, :sort)"
        ), {"code": code, "name": name, "descr": descr, "noun": noun, "gender": gender,
            "pop": pop, "tax": tax, "sort": sort_order})
        for group_code, production, cmult in template_goods(code):
            conn.execute(sa.text(
                "INSERT IGNORE INTO econ_template_goods "
                "(template_code, group_code, production_per_1000, consumption_mult) "
                "VALUES (:t, :g, :p, :c)"
            ), {"t": code, "g": group_code, "p": production, "c": cmult})

    conn.execute(sa.text(
        "INSERT IGNORE INTO econ_sim_settings (id, tick_enabled, params) VALUES (1, 1, :params)"
    ), {"params": json.dumps(DEFAULT_PARAMS)})


def downgrade() -> None:
    conn = op.get_bind()
    # Children first; whole tables are dropped (never drop an FK-backing index on its own).
    for table in (
        "econ_region_history",
        "econ_tick_runs",
        "econ_item_groups",
        "econ_region_goods",
        "econ_regions",
        "econ_template_goods",
        "econ_region_templates",
        "econ_group_inputs",
        "econ_sim_settings",
        "econ_goods_groups",
    ):
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
