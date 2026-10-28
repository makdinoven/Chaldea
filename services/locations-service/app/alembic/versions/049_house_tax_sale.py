"""Player houses (FEAT-180), stage 4: tax, inheritance, sale, seizure.

* `houses`: plot_id becomes nullable (a seized house leaves its plot and stays as
  an archive), `status` active/frozen/seized, `tax_paid_through` (tax period
  index; existing houses count as paid for the current period — set lazily
  when NULL), `heir_character_id`, `sale_price`, `listed_at`, `former_plot_id`,
  `seized_at`, `seized_reason`;
* `house_settings` singleton with the tax rates (5 % of the plot price and
  50 gold per room level per season).

Downgrade drops the settings table and the columns; seized archives (plot_id
NULL) are deleted first, since plot_id becomes NOT NULL again.

Revision ID: 049_house_tax_sale
Revises: 048_house_furniture
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa

revision = '049_house_tax_sale'
down_revision = '048_house_furniture'
branch_labels = None
depends_on = None

_COLUMNS = ('seized_reason', 'seized_at', 'former_plot_id', 'listed_at', 'sale_price', 'heir_character_id',
            'tax_paid_through', 'status')


def upgrade() -> None:
    op.alter_column('houses', 'plot_id', existing_type=sa.BigInteger(), nullable=True)
    op.add_column('houses', sa.Column('status', sa.Enum('active', 'frozen', 'seized', name='house_status'),
                                      nullable=False, server_default='active'))
    op.add_column('houses', sa.Column('tax_paid_through', sa.Integer(), nullable=True))
    op.add_column('houses', sa.Column('heir_character_id', sa.Integer(), nullable=True))
    op.add_column('houses', sa.Column('sale_price', sa.Integer(), nullable=True))
    op.add_column('houses', sa.Column('listed_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('houses', sa.Column('former_plot_id', sa.BigInteger(), nullable=True))
    op.add_column('houses', sa.Column('seized_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('houses', sa.Column('seized_reason', sa.String(20), nullable=True))
    settings = op.create_table(
        'house_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tax_price_pct', sa.Float(), nullable=False, server_default='5'),
        sa.Column('tax_per_room_level', sa.Integer(), nullable=False, server_default='50'),
        mysql_engine='InnoDB',
    )
    op.bulk_insert(settings, [{'id': 1, 'tax_price_pct': 5.0, 'tax_per_room_level': 50}])


def downgrade() -> None:
    op.drop_table('house_settings')
    op.execute("DELETE f FROM house_furniture f JOIN house_rooms r ON r.id = f.room_id "
               "JOIN houses h ON h.id = r.house_id WHERE h.plot_id IS NULL")
    op.execute("DELETE FROM houses WHERE plot_id IS NULL")
    for col in _COLUMNS:
        op.drop_column('houses', col)
    op.alter_column('houses', 'plot_id', existing_type=sa.BigInteger(), nullable=False)
