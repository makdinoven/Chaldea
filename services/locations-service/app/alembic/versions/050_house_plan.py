"""Player houses (FEAT-180), stage 5: the house plan.

* `house_plots`: `max_rooms` gives way to a grid (`grid_w`, `grid_h`) and an
  `extension_price` for cells the owner adds;
* `house_plot_layers` (floor1 / floor2 / basement / yard, an optional unlock
  price) and `house_plot_cells` (a place for one room; 'extension' cells are
  bought first; `allowed_types` narrows the layer's room types);
* `house_plot_rooms.cell_id`, `house_rooms.cell_id` (unique per house);
* `house_layer_unlocks`, `house_cell_unlocks` — what an owner bought.

Existing plots get a free first floor of `max_rooms` open cells, three to a
row; template rooms and the rooms of the houses on them (archives included)
take the cells in their order.

Downgrade puts `max_rooms` back as the plot's cell count and drops the rest.

Revision ID: 050_house_plan
Revises: 049_house_tax_sale
Create Date: 2026-10-28

"""
from alembic import op
import sqlalchemy as sa

revision = '050_house_plan'
down_revision = '049_house_tax_sale'
branch_labels = None
depends_on = None

LAYERS = ('floor1', 'floor2', 'basement', 'yard')
ROW = 3


def upgrade() -> None:
    op.add_column('house_plots', sa.Column('grid_w', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('house_plots', sa.Column('grid_h', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('house_plots', sa.Column('extension_price', sa.Integer(), nullable=True))
    op.create_table(
        'house_plot_layers',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('plot_id', sa.BigInteger(), sa.ForeignKey('house_plots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('layer', sa.Enum(*LAYERS, name='house_layer'), nullable=False),
        sa.Column('unlock_price', sa.Integer(), nullable=True),
        sa.UniqueConstraint('plot_id', 'layer', name='uq_house_plot_layer'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_plot_cells',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('plot_id', sa.BigInteger(), sa.ForeignKey('house_plots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('layer', sa.Enum(*LAYERS, name='house_layer'), nullable=False),
        sa.Column('x', sa.Integer(), nullable=False),
        sa.Column('y', sa.Integer(), nullable=False),
        sa.Column('kind', sa.Enum('open', 'extension', name='house_cell_kind'), nullable=False,
                  server_default='open'),
        sa.Column('allowed_types', sa.String(255), nullable=True),
        sa.UniqueConstraint('plot_id', 'layer', 'x', 'y', name='uq_house_plot_cell'),
        mysql_engine='InnoDB',
    )
    op.add_column('house_plot_rooms', sa.Column('cell_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_house_plot_rooms_cell', 'house_plot_rooms', 'house_plot_cells',
                          ['cell_id'], ['id'], ondelete='CASCADE')
    op.add_column('house_rooms', sa.Column('cell_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_house_rooms_cell', 'house_rooms', 'house_plot_cells',
                          ['cell_id'], ['id'], ondelete='SET NULL')
    op.create_unique_constraint('uq_house_room_cell', 'house_rooms', ['house_id', 'cell_id'])
    op.create_table(
        'house_layer_unlocks',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('house_id', sa.BigInteger(), sa.ForeignKey('houses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('layer', sa.Enum(*LAYERS, name='house_layer'), nullable=False),
        sa.UniqueConstraint('house_id', 'layer', name='uq_house_layer_unlock'),
        mysql_engine='InnoDB',
    )
    op.create_table(
        'house_cell_unlocks',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('house_id', sa.BigInteger(), sa.ForeignKey('houses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cell_id', sa.BigInteger(), sa.ForeignKey('house_plot_cells.id', ondelete='CASCADE'),
                  nullable=False),
        sa.UniqueConstraint('house_id', 'cell_id', name='uq_house_cell_unlock'),
        mysql_engine='InnoDB',
    )

    conn = op.get_bind()
    for plot_id, max_rooms in conn.execute(sa.text("SELECT id, max_rooms FROM house_plots")).fetchall():
        width = max(1, min(ROW, max_rooms))
        conn.execute(sa.text("UPDATE house_plots SET grid_w = :w, grid_h = :h WHERE id = :p"),
                     {"w": width, "h": -(-max_rooms // width), "p": plot_id})
        conn.execute(sa.text("INSERT INTO house_plot_layers (plot_id, layer) VALUES (:p, 'floor1')"), {"p": plot_id})
        cells = []
        for i in range(max_rooms):
            conn.execute(sa.text("INSERT INTO house_plot_cells (plot_id, layer, x, y) VALUES (:p, 'floor1', :x, :y)"),
                         {"p": plot_id, "x": i % width, "y": i // width})
            cells.append(conn.execute(sa.text("SELECT LAST_INSERT_ID()")).scalar())
        templates = conn.execute(sa.text(
            "SELECT id FROM house_plot_rooms WHERE plot_id = :p ORDER BY sort_order, id"), {"p": plot_id}).fetchall()
        for (room_id,), cell_id in zip(templates, cells):
            conn.execute(sa.text("UPDATE house_plot_rooms SET cell_id = :c WHERE id = :r"), {"c": cell_id, "r": room_id})
        houses = conn.execute(sa.text(
            "SELECT id FROM houses WHERE plot_id = :p OR former_plot_id = :p"), {"p": plot_id}).fetchall()
        for (house_id,) in houses:
            rooms = conn.execute(sa.text(
                "SELECT id FROM house_rooms WHERE house_id = :h ORDER BY sort_order, id"), {"h": house_id}).fetchall()
            for (room_id,), cell_id in zip(rooms, cells):
                conn.execute(sa.text("UPDATE house_rooms SET cell_id = :c WHERE id = :r"),
                             {"c": cell_id, "r": room_id})

    op.drop_column('house_plots', 'max_rooms')


def downgrade() -> None:
    op.add_column('house_plots', sa.Column('max_rooms', sa.Integer(), nullable=False, server_default='1'))
    op.execute("UPDATE house_plots p SET max_rooms = GREATEST(1, "
               "(SELECT COUNT(*) FROM house_plot_cells c WHERE c.plot_id = p.id))")
    op.alter_column('house_plots', 'max_rooms', existing_type=sa.Integer(), server_default=None,
                    existing_nullable=False)
    op.drop_table('house_cell_unlocks')
    op.drop_table('house_layer_unlocks')
    op.drop_constraint('fk_house_rooms_cell', 'house_rooms', type_='foreignkey')
    op.drop_constraint('uq_house_room_cell', 'house_rooms', type_='unique')
    op.drop_column('house_rooms', 'cell_id')
    op.drop_constraint('fk_house_plot_rooms_cell', 'house_plot_rooms', type_='foreignkey')
    op.drop_column('house_plot_rooms', 'cell_id')
    op.drop_table('house_plot_cells')
    op.drop_table('house_plot_layers')
    op.drop_column('house_plots', 'extension_price')
    op.drop_column('house_plots', 'grid_h')
    op.drop_column('house_plots', 'grid_w')
