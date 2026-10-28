"""Player houses (FEAT-180), stage 6a: profession rooms, cellar, garden rooms, bath.

* `house_room_type` (house_plot_rooms, house_rooms, house_build_costs) drops the
  generic 'workshop' for six profession rooms (forge, alchemy_lab, kitchen,
  jewelry, enchanting, study) and gains cellar, garden, greenhouse, apiary, bath.
  A workshop becomes the room of its profession (none or unknown: a forge of the
  blacksmith); a template workshop becomes a forge; a cell that allowed a
  workshop allows the six profession rooms. Build costs: every profession room
  copies the workshop's (gold, hours, materials), a cellar copies the storage's,
  the garden rooms and the bath get the default 200/800/2500 gold, 6/24/72 h.
* `house_garden_beds` — planted beds; `house_bath_uses` — the last bath of a character.

Downgrade drops the tables, turns profession rooms back into workshops and
cellars into storages, deletes garden rooms and baths (with their furniture rows)
and their template rooms and costs, restores the workshop costs from the forge's.

Revision ID: 051_house_rooms_6a
Revises: 050_house_plan
Create Date: 2026-10-28

"""
from alembic import op
import sqlalchemy as sa

revision = '051_house_rooms_6a'
down_revision = '050_house_plan'
branch_labels = None
depends_on = None

OLD_TYPES = ('hall', 'bedroom', 'storage', 'workshop')
PROFESSION_ROOMS = {'forge': 'blacksmith', 'alchemy_lab': 'alchemist', 'kitchen': 'cook',
                    'jewelry': 'jeweler', 'enchanting': 'enchanter', 'study': 'scholar'}
GARDEN_AND_BATH = ('garden', 'greenhouse', 'apiary', 'bath')
NEW_TYPES = ('hall', 'bedroom', 'storage', 'cellar', *GARDEN_AND_BATH, *PROFESSION_ROOMS)
TABLES = ('house_plot_rooms', 'house_rooms', 'house_build_costs')
# level: (gold, build hours)
DEFAULT_COSTS = {1: (200, 6), 2: (800, 24), 3: (2500, 72)}


def _set_enum(types) -> None:
    values = ",".join(f"'{t}'" for t in types)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} MODIFY COLUMN room_type ENUM({values}) NOT NULL")


def _copy_costs(conn, source: str, target: str) -> None:
    """Copies the cost rows (and their materials) of one room type to another that has none."""
    for cost_id, level, gold, hours in conn.execute(sa.text(
            "SELECT id, level, gold, build_hours FROM house_build_costs WHERE room_type = :t"), {"t": source}).fetchall():
        if conn.execute(sa.text("SELECT 1 FROM house_build_costs WHERE room_type = :t AND level = :l"),
                        {"t": target, "l": level}).first():
            continue
        conn.execute(sa.text("INSERT INTO house_build_costs (room_type, level, gold, build_hours) "
                             "VALUES (:t, :l, :g, :h)"), {"t": target, "l": level, "g": gold, "h": hours})
        new_id = conn.execute(sa.text("SELECT LAST_INSERT_ID()")).scalar()
        conn.execute(sa.text("INSERT INTO house_build_cost_items (cost_id, item_id, quantity) "
                             "SELECT :n, item_id, quantity FROM house_build_cost_items WHERE cost_id = :c"),
                     {"n": new_id, "c": cost_id})


def _map_cells(conn, convert) -> None:
    for cell_id, allowed in conn.execute(sa.text(
            "SELECT id, allowed_types FROM house_plot_cells WHERE allowed_types IS NOT NULL")).fetchall():
        types = []
        for t in allowed.split(","):
            for new in convert(t):
                if new not in types:
                    types.append(new)
        conn.execute(sa.text("UPDATE house_plot_cells SET allowed_types = :a WHERE id = :c"),
                     {"a": ",".join(types) or None, "c": cell_id})


def upgrade() -> None:
    conn = op.get_bind()
    _set_enum(OLD_TYPES + tuple(t for t in NEW_TYPES if t not in OLD_TYPES))

    professions = {slug: pid for pid, slug in conn.execute(sa.text("SELECT id, slug FROM professions")).fetchall()}
    room_by_slug = {slug: room for room, slug in PROFESSION_ROOMS.items()}
    slugs = {pid: slug for slug, pid in professions.items()}
    for room_id, profession_id in conn.execute(sa.text(
            "SELECT id, workshop_profession_id FROM house_rooms WHERE room_type = 'workshop'")).fetchall():
        slug = slugs.get(profession_id)
        if slug not in room_by_slug:
            slug = 'blacksmith'
        conn.execute(sa.text("UPDATE house_rooms SET room_type = :t, workshop_profession_id = :p WHERE id = :r"),
                     {"t": room_by_slug[slug], "p": professions.get(slug), "r": room_id})
    conn.execute(sa.text("UPDATE house_plot_rooms SET room_type = 'forge' WHERE room_type = 'workshop'"))
    _map_cells(conn, lambda t: list(PROFESSION_ROOMS) if t == 'workshop' else [t])

    for room in PROFESSION_ROOMS:
        _copy_costs(conn, 'workshop', room)
    _copy_costs(conn, 'storage', 'cellar')
    for room in GARDEN_AND_BATH:
        for level, (gold, hours) in DEFAULT_COSTS.items():
            if not conn.execute(sa.text("SELECT 1 FROM house_build_costs WHERE room_type = :t AND level = :l"),
                                {"t": room, "l": level}).first():
                conn.execute(sa.text("INSERT INTO house_build_costs (room_type, level, gold, build_hours) "
                                     "VALUES (:t, :l, :g, :h)"), {"t": room, "l": level, "g": gold, "h": hours})
    conn.execute(sa.text("DELETE FROM house_build_cost_items WHERE cost_id IN "
                         "(SELECT id FROM house_build_costs WHERE room_type = 'workshop')"))
    conn.execute(sa.text("DELETE FROM house_build_costs WHERE room_type = 'workshop'"))
    _set_enum(NEW_TYPES)

    op.create_table(
        'house_garden_beds',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('room_id', sa.BigInteger(), sa.ForeignKey('house_rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('bed_no', sa.Integer(), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('seed_item_id', sa.Integer(), nullable=False),
        sa.Column('result_item_id', sa.Integer(), nullable=False),
        sa.Column('result_quantity', sa.Integer(), nullable=False),
        sa.Column('herbalism_xp', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('planted_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('ready_at', sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint('room_id', 'bed_no', name='uq_house_garden_bed'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_bath_uses',
        sa.Column('character_id', sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column('last_at', sa.TIMESTAMP(), nullable=False),
        mysql_engine='InnoDB',
    )


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_table('house_bath_uses')
    op.drop_table('house_garden_beds')
    _set_enum(NEW_TYPES + ('workshop',))

    gone = ",".join(f"'{t}'" for t in GARDEN_AND_BATH)
    professions = ",".join(f"'{t}'" for t in PROFESSION_ROOMS)
    conn.execute(sa.text(f"DELETE FROM house_furniture WHERE room_id IN "
                         f"(SELECT id FROM house_rooms WHERE room_type IN ({gone}))"))
    conn.execute(sa.text(f"DELETE FROM house_rooms WHERE room_type IN ({gone})"))
    conn.execute(sa.text(f"DELETE FROM house_plot_rooms WHERE room_type IN ({gone})"))
    for table in ('house_rooms', 'house_plot_rooms'):
        conn.execute(sa.text(f"UPDATE {table} SET room_type = 'workshop' WHERE room_type IN ({professions})"))
        conn.execute(sa.text(f"UPDATE {table} SET room_type = 'storage' WHERE room_type = 'cellar'"))
    _map_cells(conn, lambda t: ['workshop'] if t in PROFESSION_ROOMS else ['storage'] if t == 'cellar'
               else [] if t in GARDEN_AND_BATH else [t])

    _copy_costs(conn, 'forge', 'workshop')
    stale = ",".join(f"'{t}'" for t in NEW_TYPES if t not in OLD_TYPES)
    conn.execute(sa.text(f"DELETE FROM house_build_cost_items WHERE cost_id IN "
                         f"(SELECT id FROM house_build_costs WHERE room_type IN ({stale}))"))
    conn.execute(sa.text(f"DELETE FROM house_build_costs WHERE room_type IN ({stale})"))
    _set_enum(OLD_TYPES)
