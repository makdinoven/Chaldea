"""Player houses (FEAT-180), stage 6b: library, shrine, trophy hall, guest room, return circle.

* `house_room_type` (house_plot_rooms, house_rooms, house_build_costs) gains
  library, shrine, trophy_hall, guest_room, return_circle; each gets the default
  build costs 200/800/2500 gold, 6/24/72 h.
* `house_buffs` — a character's library / shrine blessing (one per source);
  `house_shrine_uses` — the last prayer of a character; `house_guests` — guests
  the owner invited.

Downgrade drops the tables, deletes the new rooms (their furniture / trophies
first, the cells' allowed types lose them) with their template rooms and costs,
and restores the ENUM.

Revision ID: 052_house_rooms_6b
Revises: 051_house_rooms_6a
Create Date: 2026-10-28

"""
from alembic import op
import sqlalchemy as sa

revision = '052_house_rooms_6b'
down_revision = '051_house_rooms_6a'
branch_labels = None
depends_on = None

OLD_TYPES = ('hall', 'bedroom', 'storage', 'cellar', 'garden', 'greenhouse', 'apiary', 'bath',
             'forge', 'alchemy_lab', 'kitchen', 'jewelry', 'enchanting', 'study')
NEW_ROOMS = ('library', 'shrine', 'trophy_hall', 'guest_room', 'return_circle')
TABLES = ('house_plot_rooms', 'house_rooms', 'house_build_costs')
# level: (gold, build hours)
DEFAULT_COSTS = {1: (200, 6), 2: (800, 24), 3: (2500, 72)}


def _set_enum(types) -> None:
    values = ",".join(f"'{t}'" for t in types)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} MODIFY COLUMN room_type ENUM({values}) NOT NULL")


def upgrade() -> None:
    conn = op.get_bind()
    _set_enum(OLD_TYPES + NEW_ROOMS)
    for room in NEW_ROOMS:
        for level, (gold, hours) in DEFAULT_COSTS.items():
            if not conn.execute(sa.text("SELECT 1 FROM house_build_costs WHERE room_type = :t AND level = :l"),
                                {"t": room, "l": level}).first():
                conn.execute(sa.text("INSERT INTO house_build_costs (room_type, level, gold, build_hours) "
                                     "VALUES (:t, :l, :g, :h)"), {"t": room, "l": level, "g": gold, "h": hours})

    op.create_table(
        'house_buffs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.Enum('library', 'shrine', name='house_buff_source'), nullable=False),
        sa.Column('kind', sa.Enum('character_xp', 'gathering_xp', 'regen', 'post_xp', name='house_buff_kind'),
                  nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint('character_id', 'source', name='uq_house_buff'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_shrine_uses',
        sa.Column('character_id', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('last_at', sa.TIMESTAMP(), nullable=False),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_guests',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('house_id', sa.BigInteger(), sa.ForeignKey('houses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('invited_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('house_id', 'character_id', name='uq_house_guest'),
        mysql_engine='InnoDB',
    )
    op.create_index('ix_house_guests_character', 'house_guests', ['character_id'])


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_index('ix_house_guests_character', table_name='house_guests')
    op.drop_table('house_guests')
    op.drop_table('house_shrine_uses')
    op.drop_table('house_buffs')

    gone = ",".join(f"'{t}'" for t in NEW_ROOMS)
    # Nobody reads or sleeps in a room that is about to vanish (character-service columns, if present).
    for clear in (
        "reading_since = NULL, reading_house_room_id = NULL WHERE reading_house_room_id",
        "asleep_since = NULL, sleep_regen_factor = NULL, sleep_house_room_id = NULL WHERE sleep_house_room_id",
    ):
        try:
            conn.execute(sa.text(f"UPDATE characters SET {clear} IN "
                                 f"(SELECT id FROM house_rooms WHERE room_type IN ({gone}))"))
        except Exception:  # pragma: no cover - the columns are gone already
            pass
    conn.execute(sa.text(f"DELETE FROM house_furniture WHERE room_id IN "
                         f"(SELECT id FROM house_rooms WHERE room_type IN ({gone}))"))
    conn.execute(sa.text(f"DELETE FROM house_rooms WHERE room_type IN ({gone})"))
    conn.execute(sa.text(f"DELETE FROM house_plot_rooms WHERE room_type IN ({gone})"))
    for cell_id, allowed in conn.execute(sa.text(
            "SELECT id, allowed_types FROM house_plot_cells WHERE allowed_types IS NOT NULL")).fetchall():
        types = [t for t in allowed.split(",") if t and t not in NEW_ROOMS]
        conn.execute(sa.text("UPDATE house_plot_cells SET allowed_types = :a WHERE id = :c"),
                     {"a": ",".join(types) or None, "c": cell_id})
    conn.execute(sa.text(f"DELETE FROM house_build_cost_items WHERE cost_id IN "
                         f"(SELECT id FROM house_build_costs WHERE room_type IN ({gone}))"))
    conn.execute(sa.text(f"DELETE FROM house_build_costs WHERE room_type IN ({gone})"))
    _set_enum(OLD_TYPES)
