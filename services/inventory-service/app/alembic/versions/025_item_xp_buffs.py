"""FEAT-168 #6: гибкие книги опыта — таблица item_xp_buffs.

Until now an item could accelerate exactly one kind of XP, through the
`items.buff_type / buff_value / buff_duration_minutes` triple, and the only
kind the backend understood was profession XP. The admin now picks *which* XP
sources an item accelerates and by how much, and may combine several in one
item — so the single triple becomes a child table.

Backward compatibility:
* the three legacy columns are **kept and left filled** — `crud.get_item_xp_buffs`
  falls back to them for any item without rows here;
* existing definitions are backfilled into the new table, so every book that
  worked before this revision keeps working and shows up in the new admin editor;
* `active_buffs` is untouched — new buff types are plain strings in the existing
  table, and live rows of type `xp_bonus` keep their meaning (profession XP).

Upgrade: create `item_xp_buffs`, backfill from the legacy columns.
Downgrade: drop the table. The legacy columns were never modified, so the
rollback loses only rows the admin created through the new editor.

Revision ID: 025_item_xp_buffs
Revises: 024_item_battle_effects
Create Date: 2026-09-18

"""
import logging

from alembic import op
import sqlalchemy as sa

revision = '025_item_xp_buffs'
down_revision = '024_item_battle_effects'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# INLINED on purpose (same rule as 023): a migration must not import app code
# that can change later. Mirror of `schemas.ALLOWED_BUFF_TYPES` /
# `schemas.MAX_XP_BUFF_*` as of FEAT-168; a test pins the two against each other.
ALLOWED_BUFF_TYPES = frozenset({
    'xp_bonus',
    'gathering_xp_bonus',
    'character_xp_bonus',
    'character_xp_battle_bonus',
    'character_xp_post_bonus',
    'character_xp_quest_bonus',
    'character_xp_title_bonus',
    'character_xp_pass_bonus',
})
MAX_XP_BUFF_VALUE = 10.0
MIN_XP_BUFF_DURATION_MINUTES = 1
MAX_XP_BUFF_DURATION_MINUTES = 7 * 24 * 60


def upgrade():
    op.create_table(
        'item_xp_buffs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('buff_type', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Float(), nullable=False, server_default='0'),
        sa.Column('duration_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.ForeignKeyConstraint(
            ['item_id'], ['items.id'],
            name='fk_item_xp_buffs_item', ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_id', 'buff_type', name='uq_item_xp_buff_type'),
    )
    op.create_index('ix_item_xp_buffs_item_id', 'item_xp_buffs', ['item_id'])

    _backfill_from_legacy_columns()


def _backfill_from_legacy_columns():
    """One row per item that already carried a *usable* buff definition.

    `items.buff_type` was an unvalidated free string before FEAT-168, so prod may
    hold rows the new schema would reject. Copying them verbatim would put
    unreadable data behind `GET /inventory/items/{id}`, so:

      * an unknown/empty `buff_type` or a `value` that is not > 0 (and <= the cap)
        is **skipped** — such a row accelerates nothing, and the legacy columns are
        left untouched, so nothing is destroyed and it stays visible in the DB;
      * a duration outside 1..10080 minutes is **clamped** into range — the book
        itself is meaningful, only its length is out of bounds.

    Every skipped and every clamped row is logged with its item id and the reason.
    """
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        """
        SELECT id, name, buff_type, buff_value, buff_duration_minutes
        FROM items
        WHERE buff_type IS NOT NULL
          AND buff_value IS NOT NULL
          AND buff_duration_minutes IS NOT NULL
        ORDER BY id
        """
    )).fetchall()
    if not rows:
        logger.info("FEAT-168 backfill: предметов с устаревшим баффом опыта нет, копировать нечего")
        return

    inserted = skipped = clamped = 0
    for row in rows:
        row = row._mapping
        item_id = row["id"]
        buff_type = (row["buff_type"] or "").strip()

        if buff_type not in ALLOWED_BUFF_TYPES:
            logger.warning(
                "FEAT-168 backfill: предмет %s (%r) пропущен — неизвестный тип баффа %r; "
                "устаревшие колонки оставлены как есть",
                item_id, row["name"], row["buff_type"],
            )
            skipped += 1
            continue

        try:
            value = float(row["buff_value"])
        except (TypeError, ValueError):
            value = None
        if value is None or not 0 < value <= MAX_XP_BUFF_VALUE:
            logger.warning(
                "FEAT-168 backfill: предмет %s (%r) пропущен — недопустимая прибавка к опыту %r",
                item_id, row["name"], row["buff_value"],
            )
            skipped += 1
            continue

        try:
            duration = int(row["buff_duration_minutes"])
        except (TypeError, ValueError):
            duration = None
        if duration is None:
            logger.warning(
                "FEAT-168 backfill: предмет %s (%r) пропущен — нечисловая длительность %r",
                item_id, row["name"], row["buff_duration_minutes"],
            )
            skipped += 1
            continue
        if not MIN_XP_BUFF_DURATION_MINUTES <= duration <= MAX_XP_BUFF_DURATION_MINUTES:
            fixed = min(max(duration, MIN_XP_BUFF_DURATION_MINUTES), MAX_XP_BUFF_DURATION_MINUTES)
            logger.warning(
                "FEAT-168 backfill: предмет %s (%r) — длительность %s мин вне диапазона, обрезана до %s",
                item_id, row["name"], duration, fixed,
            )
            duration = fixed
            clamped += 1

        conn.execute(
            sa.text(
                "INSERT INTO item_xp_buffs (item_id, buff_type, value, duration_minutes) "
                "VALUES (:iid, :bt, :val, :dur)"
            ),
            {"iid": item_id, "bt": buff_type, "val": value, "dur": duration},
        )
        inserted += 1

    logger.info(
        "FEAT-168 backfill: перенесено %s строк ускорения опыта, пропущено %s, обрезано по длительности %s",
        inserted, skipped, clamped,
    )


def downgrade():
    # The index is dropped with the table. Dropping it separately fails on MySQL
    # with «needed in a foreign key constraint» (errno 1553) — same trap as 024.
    op.drop_table('item_xp_buffs')
