"""Add gathering system: extend items.item_type ENUM with gathering_tool, add tool-specific columns, create gathering_skills / gathering_skill_ranks / character_gathering_skills tables, seed 3 skills x 5 ranks.

Revision ID: 016_add_gathering_system
Revises: 015_add_auction_tables
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


revision = '016_add_gathering_system'
down_revision = '015_add_auction_tables'
branch_labels = None
depends_on = None


# Full ENUM list AFTER this migration (existing values + 'gathering_tool')
ITEM_TYPE_ENUM_NEW = (
    "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
    "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
    "'blueprint','recipe','gem','rune','gathering_tool')"
)

# Previous ENUM list (BEFORE this migration) — used by downgrade()
ITEM_TYPE_ENUM_OLD = (
    "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
    "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
    "'blueprint','recipe','gem','rune')"
)


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
    ), {"tbl": table, "col": column})
    return result.scalar() > 0


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl"
    ), {"tbl": table})
    return result.scalar() > 0


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Extend items.item_type ENUM with 'gathering_tool' (idempotent)
    col_type = conn.execute(sa.text(
        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'items' AND COLUMN_NAME = 'item_type'"
    )).scalar()
    if col_type and "'gathering_tool'" not in col_type:
        op.execute(f"ALTER TABLE items MODIFY COLUMN item_type {ITEM_TYPE_ENUM_NEW} NOT NULL")

    # 2) Add tool-specific columns to items (only apply to gathering_tool rows; nullable category, numeric bonuses default 0)
    if not _column_exists(conn, "items", "tool_category"):
        op.add_column(
            "items",
            sa.Column(
                "tool_category",
                sa.Enum('pickaxe', 'sickle', 'axe', name='tool_category_enum'),
                nullable=True,
            ),
        )
    if not _column_exists(conn, "items", "gather_double_chance_bonus"):
        op.add_column(
            "items",
            sa.Column("gather_double_chance_bonus", sa.Float(), nullable=False, server_default="0"),
        )
    if not _column_exists(conn, "items", "gather_speed_bonus_pct"):
        op.add_column(
            "items",
            sa.Column("gather_speed_bonus_pct", sa.Float(), nullable=False, server_default="0"),
        )
    if not _column_exists(conn, "items", "gather_stamina_bonus_pct"):
        op.add_column(
            "items",
            sa.Column("gather_stamina_bonus_pct", sa.Float(), nullable=False, server_default="0"),
        )

    # 3) Create gathering_skills (catalog: 3 fixed skills)
    if not _table_exists(conn, "gathering_skills"):
        op.create_table(
            'gathering_skills',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('slug', sa.String(50), nullable=False, unique=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column(
                'category',
                sa.Enum('ore', 'herb', 'wood', name='gathering_skill_category_enum'),
                nullable=False,
                unique=True,
            ),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('icon', sa.String(255), nullable=True),
            sa.Column('max_rank', sa.Integer, nullable=False, server_default='5'),
            sa.Column('created_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP')),
        )

    # 4) Create gathering_skill_ranks (5 rows per skill)
    if not _table_exists(conn, "gathering_skill_ranks"):
        op.create_table(
            'gathering_skill_ranks',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('skill_id', sa.Integer, nullable=False),
            sa.Column('rank_number', sa.Integer, nullable=False),
            sa.Column('required_experience', sa.Integer, nullable=False, server_default='0'),
            sa.Column('double_chance_bonus', sa.Float, nullable=False, server_default='0'),
            sa.Column('speed_bonus_pct', sa.Float, nullable=False, server_default='0'),
            sa.Column('stamina_bonus_pct', sa.Float, nullable=False, server_default='0'),
            sa.ForeignKeyConstraint(['skill_id'], ['gathering_skills.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('skill_id', 'rank_number', name='uq_gathering_skill_rank'),
        )

    # 5) Create character_gathering_skills (per-character progress; lazy-created on first XP award)
    # NOTE: character_id is INT without FK because it's owned by character-service (cross-service convention).
    if not _table_exists(conn, "character_gathering_skills"):
        op.create_table(
            'character_gathering_skills',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer, nullable=False),
            sa.Column('skill_id', sa.Integer, nullable=False),
            sa.Column('current_rank', sa.Integer, nullable=False, server_default='1'),
            sa.Column('experience', sa.Integer, nullable=False, server_default='0'),
            sa.Column('experience_total', sa.Integer, nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['skill_id'], ['gathering_skills.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('character_id', 'skill_id', name='uq_character_gathering_skill'),
        )
        op.create_index(
            'ix_character_gathering_skills_character',
            'character_gathering_skills',
            ['character_id'],
        )

    # 6) Seed 3 skills (idempotent — skip if already seeded)
    seeded_count = conn.execute(sa.text("SELECT COUNT(*) FROM gathering_skills")).scalar()
    if not seeded_count:
        op.execute(
            "INSERT INTO gathering_skills (slug, name, category, description, max_rank) VALUES "
            "('mining',      'Горное дело',  'ore',  'Навык добычи руды',   5),"
            "('herbalism',   'Травничество', 'herb', 'Навык сбора трав',    5),"
            "('woodcutting', 'Лесорубство',  'wood', 'Навык рубки дерева',  5)"
        )

    # 7) Seed 5 ranks per skill (15 rows total, idempotent)
    rank_rows_count = conn.execute(sa.text("SELECT COUNT(*) FROM gathering_skill_ranks")).scalar()
    if not rank_rows_count:
        # rank_number, required_experience, double_chance_bonus, speed_bonus_pct, stamina_bonus_pct
        rank_bonuses = [
            (1,   0,  0.0,  0.0,  0.0),
            (2,  10,  4.0,  4.0,  4.0),
            (3,  25,  8.0,  8.0,  8.0),
            (4,  50, 12.0, 12.0, 12.0),
            (5, 100, 20.0, 20.0, 20.0),
        ]
        skills = conn.execute(sa.text(
            "SELECT id FROM gathering_skills ORDER BY id"
        )).fetchall()
        for (skill_id,) in skills:
            for (rn, req_xp, dc, sp, st) in rank_bonuses:
                conn.execute(
                    sa.text(
                        "INSERT INTO gathering_skill_ranks "
                        "(skill_id, rank_number, required_experience, "
                        " double_chance_bonus, speed_bonus_pct, stamina_bonus_pct) "
                        "VALUES (:sid, :rn, :req, :dc, :sp, :st)"
                    ),
                    {"sid": skill_id, "rn": rn, "req": req_xp, "dc": dc, "sp": sp, "st": st},
                )


def downgrade() -> None:
    conn = op.get_bind()

    # 1) Drop new tables in reverse dependency order
    if _table_exists(conn, "character_gathering_skills"):
        op.drop_index(
            'ix_character_gathering_skills_character',
            table_name='character_gathering_skills',
        )
        op.drop_table('character_gathering_skills')
    if _table_exists(conn, "gathering_skill_ranks"):
        op.drop_table('gathering_skill_ranks')
    if _table_exists(conn, "gathering_skills"):
        op.drop_table('gathering_skills')

    # 2) Drop tool-specific columns from items
    if _column_exists(conn, "items", "gather_stamina_bonus_pct"):
        op.drop_column("items", "gather_stamina_bonus_pct")
    if _column_exists(conn, "items", "gather_speed_bonus_pct"):
        op.drop_column("items", "gather_speed_bonus_pct")
    if _column_exists(conn, "items", "gather_double_chance_bonus"):
        op.drop_column("items", "gather_double_chance_bonus")
    if _column_exists(conn, "items", "tool_category"):
        op.drop_column("items", "tool_category")

    # 3) Restore items.item_type ENUM to its previous value list
    # NOTE: This will fail if any items with item_type='gathering_tool' exist.
    op.execute(f"ALTER TABLE items MODIFY COLUMN item_type {ITEM_TYPE_ENUM_OLD} NOT NULL")
