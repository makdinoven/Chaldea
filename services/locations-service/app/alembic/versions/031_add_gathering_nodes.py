"""Add gathering_nodes and gathering_sessions tables

Revision ID: 031_add_gathering_nodes
Revises: 030_no_quick_move
Create Date: 2026-04-25

Creates two new tables for the location resource gathering feature (FEAT-128):
  * gathering_nodes      — admin-configured ore/herb/wood nodes attached to a Location
  * gathering_sessions   — per-character active/finished gathering sessions on a node

Cross-service columns (result_item_id, character_id, tool_inventory_item_id) are
plain INT columns with NO ForeignKey declared — items / characters / inventory_items
are owned by other services and the codebase convention (LocationLoot, npc_shop_items)
is to NOT declare cross-service SQLAlchemy ForeignKeys.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '031_add_gathering_nodes'
down_revision = '030_no_quick_move'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = insp.get_table_names()

    if 'gathering_nodes' not in existing_tables:
        op.create_table(
            'gathering_nodes',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column(
                'location_id',
                sa.BigInteger(),
                sa.ForeignKey('Locations.id', ondelete='CASCADE', name='fk_gathering_nodes_location'),
                nullable=False,
            ),
            sa.Column('node_name', sa.String(length=120), nullable=False),
            sa.Column(
                'category',
                sa.Enum('ore', 'herb', 'wood', name='gathering_node_category'),
                nullable=False,
            ),
            # Cross-service: items table is owned by inventory-service — no FK.
            sa.Column('result_item_id', sa.Integer(), nullable=False),
            sa.Column(
                'result_quantity_per_gather',
                sa.Integer(),
                nullable=False,
                server_default=sa.text('1'),
            ),
            sa.Column('stamina_per_gather', sa.Integer(), nullable=False),
            sa.Column('daily_bank_max', sa.Integer(), nullable=False),
            sa.Column('current_bank', sa.Integer(), nullable=False),
            sa.Column(
                'allow_concurrent_gather',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('0'),
            ),
            sa.Column('depleted_at', sa.TIMESTAMP(), nullable=True),
            sa.Column('restore_at', sa.TIMESTAMP(), nullable=True),
            sa.Column(
                'is_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('1'),
            ),
            sa.Column(
                'created_at',
                sa.TIMESTAMP(),
                nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.Column(
                'updated_at',
                sa.TIMESTAMP(),
                nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
            ),
            sa.CheckConstraint('stamina_per_gather >= 1', name='ck_gathering_nodes_stamina_min'),
            sa.CheckConstraint('daily_bank_max >= 1', name='ck_gathering_nodes_daily_bank_min'),
            mysql_engine='InnoDB',
        )
        op.create_index(
            'ix_gathering_nodes_location',
            'gathering_nodes',
            ['location_id'],
        )
        op.create_index(
            'ix_gathering_nodes_category',
            'gathering_nodes',
            ['category'],
        )
        op.create_index(
            'ix_gathering_nodes_restore_at',
            'gathering_nodes',
            ['restore_at'],
        )

    if 'gathering_sessions' not in existing_tables:
        op.create_table(
            'gathering_sessions',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column(
                'node_id',
                sa.Integer(),
                sa.ForeignKey('gathering_nodes.id', ondelete='CASCADE', name='fk_gathering_sessions_node'),
                nullable=False,
            ),
            # Cross-service: characters live in character-service — no FK.
            sa.Column('character_id', sa.Integer(), nullable=False),
            # Cross-service: inventory items live in inventory-service — no FK.
            # null = "without tool"
            sa.Column('tool_inventory_item_id', sa.Integer(), nullable=True),
            sa.Column(
                'started_at',
                sa.TIMESTAMP(),
                nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.Column('complete_at', sa.TIMESTAMP(), nullable=False),
            sa.Column(
                'effective_speed_bonus_pct',
                sa.Float(),
                nullable=False,
                server_default=sa.text('0'),
            ),
            sa.Column(
                'effective_double_chance_pct',
                sa.Float(),
                nullable=False,
                server_default=sa.text('0'),
            ),
            sa.Column(
                'effective_stamina_bonus_pct',
                sa.Float(),
                nullable=False,
                server_default=sa.text('0'),
            ),
            sa.Column('stamina_paid', sa.Integer(), nullable=False),
            sa.Column(
                'status',
                sa.Enum(
                    'active',
                    'completed',
                    'cancelled',
                    'interrupted_by_battle',
                    'inventory_full',
                    name='gathering_session_status',
                ),
                nullable=False,
                server_default=sa.text("'active'"),
            ),
            sa.Column('finished_at', sa.TIMESTAMP(), nullable=True),
            sa.Column('result_quantity', sa.Integer(), nullable=True),
            sa.Column('xp_awarded', sa.Integer(), nullable=True),
            mysql_engine='InnoDB',
        )
        op.create_index(
            'ix_gathering_sessions_character',
            'gathering_sessions',
            ['character_id'],
        )
        op.create_index(
            'ix_gathering_sessions_node',
            'gathering_sessions',
            ['node_id'],
        )
        op.create_index(
            'ix_gathering_sessions_status',
            'gathering_sessions',
            ['status'],
        )
        op.create_index(
            'ix_gathering_sessions_complete_at',
            'gathering_sessions',
            ['complete_at'],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = insp.get_table_names()

    # Sessions first (FK -> gathering_nodes), then nodes.
    if 'gathering_sessions' in existing_tables:
        op.drop_index('ix_gathering_sessions_complete_at', table_name='gathering_sessions')
        op.drop_index('ix_gathering_sessions_status', table_name='gathering_sessions')
        op.drop_index('ix_gathering_sessions_node', table_name='gathering_sessions')
        op.drop_index('ix_gathering_sessions_character', table_name='gathering_sessions')
        op.drop_table('gathering_sessions')

    if 'gathering_nodes' in existing_tables:
        op.drop_index('ix_gathering_nodes_restore_at', table_name='gathering_nodes')
        op.drop_index('ix_gathering_nodes_category', table_name='gathering_nodes')
        op.drop_index('ix_gathering_nodes_location', table_name='gathering_nodes')
        op.drop_table('gathering_nodes')
