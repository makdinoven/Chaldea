"""FEAT-187: region events — templates, instances (active + permanent history), riot clock.

* `econ_event_templates` — admin-defined events (crises / boons): effects built from the sim levers
                           (econ_events), applicability (region templates, game seasons), weight, duration range,
                           scope, spreading, chains. Seeded with the 14 starter templates of EVENT_TEMPLATES.
* `econ_region_events`   — one row per event instance in one region: the active state AND the history the future
                           newspaper reads. Never purged; no FK to Regions / econ_regions / econ_tick_runs (history
                           outlives them); a snapshot of the template is taken at start. `origin_key` makes automatic
                           starts idempotent, `active_key` ('r<region>:<code>' while active) allows one active instance
                           per template and region.
* `econ_regions.low_stability_since` — the riot clock (set / cleared by the tick).

New sim params (`events_enabled`, `event_*`) need no migration — missing keys of the stored params JSON fall back to
econ_sim.SimParams defaults.

FK columns get explicit indexes before their FKs (MySQL would otherwise create implicit ones that a later DROP INDEX
cannot remove). Every statement is re-runnable (MySQL DDL is not transactional). Downgrade drops both tables and the
column — the event history is lost.

Revision ID: 033_econ_region_events
Revises: 032_econ_population_scale
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "033_econ_region_events"
down_revision = "032_econ_population_scale"
branch_labels = None
depends_on = None


_TABLE_OPTS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"


def _e(type_, **fields):
    return {"type": type_, **fields}


# Starter set (section 3.9). Durations in days; region_templates / seasons [] = any.
EVENT_TEMPLATES = [
    {
        "code": "drought", "name": "Засуха", "icon": "sun", "kind": "bad",
        "player_text": "Солнце выжигает поля — урожай гибнет, хлеб дорожает.",
        "admin_note": "Летний неурожай: меньше еды и трав, еда дорожает; может вызвать мор скота.",
        "trigger_kind": "random", "weight": 3, "duration_min_days": 6, "duration_max_days": 12,
        "scope": "region", "spread_chance": 0.25,
        "region_templates": ["agrarian", "rural", "forest", "capital", "mining", "fortress", "magic"],
        "seasons": ["summer", "lughnasad"],
        "effects": [
            _e("production", groups=["food"], mult=0.5),
            _e("production", groups=["herbs"], mult=0.7),
            _e("price", groups=["food"], mult=1.15),
            _e("stability", delta=-0.5),
        ],
        "chains": [{"code": "livestock", "chance": 0.15}],
    },
    {
        "code": "flood", "name": "Потоп", "icon": "waves", "kind": "bad",
        "player_text": "Реки вышли из берегов: склады затоплены, поля под водой.",
        "admin_note": "Разовая потеря запасов и расход казны на восстановление; после потопа возможна чума.",
        "trigger_kind": "random", "weight": 2, "duration_min_days": 3, "duration_max_days": 6,
        "scope": "region", "spread_chance": 0.2,
        "region_templates": ["port", "agrarian", "rural", "forest"],
        "seasons": ["spring", "beltane", "autumn"],
        "effects": [
            _e("stock_loss", groups=["food"], share=0.25),
            _e("stock_loss", groups=["wood"], share=0.15),
            _e("stock_loss", groups=["household"], share=0.1),
            _e("production", groups=["food"], mult=0.7),
            _e("treasury_expense", share=0.1),
            _e("stability", delta=-1),
        ],
        "chains": [{"code": "plague", "chance": 0.3}],
    },
    {
        "code": "plague", "name": "Чума", "icon": "skull", "kind": "bad",
        "player_text": "Мор косит жителей: работать некому, лекари не справляются.",
        "admin_note": "Меньше работников, спрос на зелья и травы, навсегда уносит 3 % населения.",
        "trigger_kind": "random", "weight": 1, "duration_min_days": 10, "duration_max_days": 20,
        "scope": "region", "spread_chance": 0.35,
        "region_templates": [], "seasons": [],
        "effects": [
            _e("labor", mult=0.75),
            _e("consumption", groups=["potions"], mult=2),
            _e("consumption", groups=["herbs"], mult=1.5),
            _e("stability", delta=-1.5),
            _e("prosperity", delta=-1),
            _e("population", pct=-0.03),
            _e("treasury_expense", share=0.05),
        ],
        "chains": [],
    },
    {
        "code": "magic_disaster", "name": "Магическая катастрофа", "icon": "zap", "kind": "bad",
        "player_text": "Вырвавшаяся магия отравила источники силы — реагенты рассыпаются в прах.",
        "admin_note": "Удар по магическим материалам и зельям, потеря магических запасов, жертвы среди жителей.",
        "trigger_kind": "random", "weight": 1, "duration_min_days": 5, "duration_max_days": 10,
        "scope": "region", "spread_chance": 0.1,
        "region_templates": ["magic", "capital"], "seasons": [],
        "effects": [
            _e("production", groups=["magic"], mult=0.3),
            _e("production", groups=["potions"], mult=0.6),
            _e("stock_loss", groups=["magic"], share=0.4),
            _e("stability", delta=-2),
            _e("population", pct=-0.01),
            _e("treasury_expense", share=0.15),
        ],
        "chains": [],
    },
    {
        "code": "mine_collapse", "name": "Обвал в шахте", "icon": "pickaxe", "kind": "bad",
        "player_text": "Своды главной шахты обрушились — рудокопы под завалами.",
        "admin_note": "Добыча руды падает, казна платит за разбор завалов.",
        "trigger_kind": "random", "weight": 3, "duration_min_days": 4, "duration_max_days": 8,
        "scope": "region", "spread_chance": 0,
        "region_templates": ["mining", "fortress"], "seasons": [],
        "effects": [
            _e("production", groups=["ore_metal"], mult=0.4),
            _e("stability", delta=-1),
            _e("population", pct=-0.005),
            _e("treasury_expense", share=0.1),
        ],
        "chains": [],
    },
    {
        "code": "livestock", "name": "Мор скота", "icon": "beef", "kind": "bad",
        "player_text": "Падёж скота: пастбища пустеют, шкур и мяса всё меньше.",
        "admin_note": "Меньше еды и шкур; часто приходит вслед за засухой.",
        "trigger_kind": "random", "weight": 2, "duration_min_days": 6, "duration_max_days": 12,
        "scope": "region", "spread_chance": 0.3,
        "region_templates": ["agrarian", "rural", "forest"], "seasons": [],
        "effects": [
            _e("production", groups=["food"], mult=0.75),
            _e("production", groups=["hides_textiles"], mult=0.5),
            _e("stock_loss", groups=["hides_textiles"], share=0.1),
            _e("prosperity", delta=-0.5),
        ],
        "chains": [],
    },
    {
        "code": "raid", "name": "Набег", "icon": "swords", "kind": "bad",
        "player_text": "Разбойники разорили окрестности: склады разграблены, дороги опасны.",
        "admin_note": "Грабёж складов, спрос на оружие и броню, торговцы не подвозят товар.",
        "trigger_kind": "random", "weight": 2, "duration_min_days": 2, "duration_max_days": 4,
        "scope": "region", "spread_chance": 0,
        "region_templates": ["fortress", "rural", "port", "agrarian"], "seasons": [],
        "effects": [
            _e("stock_loss", groups=["food"], share=0.15),
            _e("stock_loss", groups=["weapons"], share=0.2),
            _e("stock_loss", groups=["ore_metal"], share=0.1),
            _e("consumption", groups=["weapons"], mult=1.5),
            _e("consumption", groups=["armor"], mult=1.3),
            _e("merchants_halt"),
            _e("stability", delta=-2),
            _e("prosperity", delta=-1),
            _e("population", pct=-0.005),
            _e("treasury_expense", share=0.1),
        ],
        "chains": [],
    },
    {
        "code": "riot", "name": "Бунт", "icon": "flame", "kind": "bad",
        "player_text": "Жители взбунтовались: лавки закрыты, сборщиков налогов гонят прочь.",
        "admin_note": "Не случается случайно — начинается после долгой низкой стабильности.",
        "trigger_kind": "low_stability", "weight": 1, "duration_min_days": 3, "duration_max_days": 6,
        "scope": "region", "spread_chance": 0.1,
        "region_templates": [], "seasons": [],
        "effects": [
            _e("labor", mult=0.7),
            _e("tax_income", mult=0.5),
            _e("merchants_halt"),
            _e("bank_panic"),
            _e("prosperity", delta=-1.5),
            _e("treasury_expense", share=0.1),
        ],
        "chains": [],
    },
    {
        "code": "harvest", "name": "Урожайный год", "icon": "wheat", "kind": "good",
        "player_text": "Небывалый урожай — амбары ломятся, хлеб дешевеет.",
        "admin_note": "Больше еды и трав, немного растёт население.",
        "trigger_kind": "random", "weight": 3, "duration_min_days": 10, "duration_max_days": 20,
        "scope": "region", "spread_chance": 0.2,
        "region_templates": ["agrarian", "rural", "forest", "port"],
        "seasons": ["summer", "lughnasad", "autumn"],
        "effects": [
            _e("production", groups=["food"], mult=1.4),
            _e("production", groups=["herbs"], mult=1.2),
            _e("stability", delta=0.5),
            _e("prosperity", delta=0.5),
            _e("population", pct=0.003),
        ],
        "chains": [],
    },
    {
        "code": "magic_anomaly", "name": "Благоприятная магическая аномалия", "icon": "sparkles", "kind": "good",
        "player_text": "Над краем мерцает сияние — магия течёт щедро, реагенты наливаются силой.",
        "admin_note": "Больше магических материалов и зелий, магия дешевеет.",
        "trigger_kind": "random", "weight": 1, "duration_min_days": 5, "duration_max_days": 10,
        "scope": "region", "spread_chance": 0.1,
        "region_templates": ["magic", "capital", "forest"], "seasons": [],
        "effects": [
            _e("production", groups=["magic"], mult=1.8),
            _e("production", groups=["potions"], mult=1.3),
            _e("price", groups=["magic"], mult=0.85),
            _e("prosperity", delta=0.5),
        ],
        "chains": [],
    },
    {
        "code": "rich_vein", "name": "Богатая жила", "icon": "gem", "kind": "good",
        "player_text": "Рудокопы наткнулись на богатую жилу — металла вдоволь.",
        "admin_note": "Больше руды и украшений, казна получает больше налогов.",
        "trigger_kind": "random", "weight": 2, "duration_min_days": 10, "duration_max_days": 20,
        "scope": "region", "spread_chance": 0,
        "region_templates": ["mining", "fortress"], "seasons": [],
        "effects": [
            _e("production", groups=["ore_metal"], mult=1.7),
            _e("production", groups=["jewelry"], mult=1.2),
            _e("tax_income", mult=1.15),
            _e("prosperity", delta=0.5),
        ],
        "chains": [],
    },
    {
        "code": "fair", "name": "Ярмарка", "icon": "store", "kind": "good",
        "player_text": "Большая ярмарка: купцы со всех земель, торг идёт бойко.",
        "admin_note": "Оживлённая торговля: спрос на роскошь, больше налогов, бум займов.",
        "trigger_kind": "random", "weight": 2, "duration_min_days": 2, "duration_max_days": 4,
        "scope": "region", "spread_chance": 0,
        "region_templates": ["capital", "port", "agrarian"],
        "seasons": ["lughnasad", "autumn", "samhain"],
        "effects": [
            _e("consumption", groups=["jewelry", "household"], mult=1.2),
            _e("consumption", groups=["hides_textiles"], mult=1.1),
            _e("price", groups=["household", "jewelry"], mult=0.9),
            _e("tax_income", mult=1.3),
            _e("loan_boom", mult=1.5),
            _e("prosperity", delta=1),
            _e("stability", delta=0.5),
        ],
        "chains": [],
    },
    {
        "code": "festival", "name": "Праздник", "icon": "party-popper", "kind": "good",
        "player_text": "Народ празднует — песни, угощения и щедрые гуляния.",
        "admin_note": "Праздник на всю страну в дни календарных праздников.",
        "trigger_kind": "random", "weight": 3, "duration_min_days": 2, "duration_max_days": 3,
        "scope": "country", "spread_chance": 0,
        "region_templates": [], "seasons": ["beltane", "lughnasad", "samhain", "imbolc"],
        "effects": [
            _e("consumption", groups=["food", "jewelry"], mult=1.2),
            _e("tax_income", mult=1.1),
            _e("stability", delta=2),
            _e("prosperity", delta=1),
        ],
        "chains": [],
    },
    {
        "code": "good_catch", "name": "Удачный улов", "icon": "fish", "kind": "good",
        "player_text": "Сети полны рыбы — порт пахнет солью и достатком.",
        "admin_note": "Больше еды и шкур в портовых регионах, еда дешевеет.",
        "trigger_kind": "random", "weight": 3, "duration_min_days": 5, "duration_max_days": 10,
        "scope": "region", "spread_chance": 0,
        "region_templates": ["port"], "seasons": ["spring", "summer", "autumn"],
        "effects": [
            _e("production", groups=["food"], mult=1.3),
            _e("production", groups=["hides_textiles"], mult=1.2),
            _e("price", groups=["food"], mult=0.9),
            _e("prosperity", delta=0.5),
        ],
        "chains": [],
    },
]


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def upgrade() -> None:
    conn = op.get_bind()

    if not _has_column(conn, "econ_regions", "low_stability_since"):
        conn.execute(sa.text("ALTER TABLE econ_regions ADD COLUMN low_stability_since DATETIME NULL"))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_event_templates (
          id                 INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
          code               VARCHAR(32)   NOT NULL,
          name               VARCHAR(100)  NOT NULL,
          icon               VARCHAR(32)   NOT NULL DEFAULT 'alert',
          kind               VARCHAR(4)    NOT NULL,
          player_text        VARCHAR(500)  NOT NULL,
          admin_note         VARCHAR(1000) NULL,
          trigger_kind       VARCHAR(16)   NOT NULL DEFAULT 'random',
          weight             DECIMAL(7,2)  NOT NULL DEFAULT 1.00,
          duration_min_days  DECIMAL(6,2)  NOT NULL,
          duration_max_days  DECIMAL(6,2)  NOT NULL,
          scope              VARCHAR(12)   NOT NULL DEFAULT 'region',
          spread_chance      DECIMAL(5,4)  NOT NULL DEFAULT 0,
          region_templates   JSON          NULL,
          seasons            JSON          NULL,
          effects            JSON          NOT NULL,
          chains             JSON          NULL,
          is_enabled         TINYINT(1)    NOT NULL DEFAULT 1,
          updated_by_user_id INT           NULL,
          created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          CONSTRAINT uq_econ_event_templates_code UNIQUE (code),
          CONSTRAINT ck_eet_kind CHECK (kind IN ('good', 'bad')),
          CONSTRAINT ck_eet_trigger CHECK (trigger_kind IN ('random', 'low_stability', 'manual')),
          CONSTRAINT ck_eet_scope CHECK (scope IN ('region', 'neighbours', 'country', 'world')),
          CONSTRAINT ck_eet_duration CHECK (duration_min_days > 0 AND duration_max_days >= duration_min_days),
          CONSTRAINT ck_eet_numbers CHECK (weight >= 0 AND spread_chance >= 0 AND spread_chance <= 1)
        ) {_TABLE_OPTS}
    """))

    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS econ_region_events (
          id                   BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
          region_id            BIGINT        NOT NULL,
          region_name          VARCHAR(255)  NULL,
          country_id           BIGINT        NULL,
          template_id          INT           NULL,
          template_code        VARCHAR(32)   NOT NULL,
          name                 VARCHAR(100)  NOT NULL,
          icon                 VARCHAR(32)   NOT NULL,
          kind                 VARCHAR(4)    NOT NULL,
          player_text          VARCHAR(500)  NOT NULL,
          trigger_kind         VARCHAR(16)   NOT NULL,
          effects              JSON          NOT NULL,
          chains               JSON          NULL,
          spread_chance        DECIMAL(5,4)  NOT NULL DEFAULT 0,
          origin               VARCHAR(8)    NOT NULL,
          parent_event_id      BIGINT        NULL,
          root_event_id        BIGINT        NULL,
          generation           SMALLINT      NOT NULL DEFAULT 0,
          origin_key           VARCHAR(96)   NULL,
          active_key           VARCHAR(48)   NULL,
          status               VARCHAR(10)   NOT NULL DEFAULT 'active',
          started_at           DATETIME      NOT NULL,
          ends_at              DATETIME      NOT NULL,
          ended_at             DATETIME      NULL,
          game_segment         VARCHAR(16)   NULL,
          run_id               BIGINT        NULL,
          started_by_user_id   INT           NULL,
          cancelled_by_user_id INT           NULL,
          cancel_comment       VARCHAR(500)  NULL,
          applied_at           DATETIME      NULL,
          applied_run_id       BIGINT        NULL,
          population_before    INT           NULL,
          population_after     INT           NULL,
          outcome              JSON          NULL,
          created_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY ix_ere_template (template_id),
          KEY ix_ere_parent (parent_event_id),
          KEY ix_ere_region_status (region_id, status),
          KEY ix_ere_status_ends (status, ends_at),
          KEY ix_ere_root (root_event_id),
          KEY ix_ere_started (started_at),
          KEY ix_ere_ended (ended_at),
          CONSTRAINT uq_ere_origin_key UNIQUE (origin_key),
          CONSTRAINT uq_ere_active_key UNIQUE (active_key),
          CONSTRAINT fk_ere_template FOREIGN KEY (template_id)
            REFERENCES econ_event_templates (id) ON DELETE SET NULL,
          CONSTRAINT fk_ere_parent FOREIGN KEY (parent_event_id)
            REFERENCES econ_region_events (id) ON DELETE SET NULL,
          CONSTRAINT ck_ere_status CHECK (status IN ('active', 'ended', 'cancelled')),
          CONSTRAINT ck_ere_origin CHECK (origin IN ('random', 'manual', 'spread', 'chain', 'riot')),
          CONSTRAINT ck_ere_time CHECK (ends_at >= started_at)
        ) {_TABLE_OPTS}
    """))

    for t in EVENT_TEMPLATES:
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
    # Children first; whole tables are dropped (never drop an FK-backing index on its own).
    for table in ("econ_region_events", "econ_event_templates"):
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
    if _has_column(conn, "econ_regions", "low_stability_since"):
        conn.execute(sa.text("ALTER TABLE econ_regions DROP COLUMN low_stability_since"))
