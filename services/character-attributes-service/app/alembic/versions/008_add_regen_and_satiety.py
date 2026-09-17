"""Add passive regen bookkeeping and character_satiety (FEAT-164)

- character_attributes.regen_anchor_at (NULL = clock not started yet; the first
  settle starts it, so there is no retroactive heal on deploy)
- character_attributes.regen_carry_{health,mana,energy,stamina} — fractional
  remainder of passive regen, so frequent reads never round regen away
- character_satiety — one active "Сытость" per character (food effect, 24h),
  holding the stat modifiers that were added to the base columns

No backfill.

OPERATIONAL ROLLBACK NOTE: satiety stat bonuses live inside the base stat
columns of character_attributes. Before running `downgrade`, strip them:
    UPDATE character_satiety SET expires_at = UTC_TIMESTAMP();
then call POST /attributes/internal/settle-regen for all character_id values in
character_satiety (or GET /attributes/{id} per id) so the negative modifiers are
applied and the rows deleted. Otherwise the bonuses stay in base stats forever.

Revision ID: 008_add_regen_and_satiety
Revises: 007_add_pve_points
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

revision = '008_add_regen_and_satiety'
down_revision = '007_add_pve_points'
branch_labels = None
depends_on = None

_CARRY_COLUMNS = (
    'regen_carry_health',
    'regen_carry_mana',
    'regen_carry_energy',
    'regen_carry_stamina',
)


def _existing_columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    return {c['name'] for c in inspector.get_columns(table)}


def _table_exists(table: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table in inspector.get_table_names()


def upgrade() -> None:
    columns = _existing_columns('character_attributes')
    if 'regen_anchor_at' not in columns:
        op.add_column(
            'character_attributes',
            sa.Column('regen_anchor_at', sa.DateTime(), nullable=True),
        )
    for name in _CARRY_COLUMNS:
        if name not in columns:
            op.add_column(
                'character_attributes',
                sa.Column(name, sa.Float(), nullable=False, server_default='0'),
            )

    if not _table_exists('character_satiety'):
        op.create_table(
            'character_satiety',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('item_id', sa.Integer(), nullable=True),
            sa.Column('source_item_name', sa.String(200), nullable=True),
            sa.Column('rarity', sa.String(20), nullable=False),
            sa.Column('regen_bonus', sa.Float(), nullable=False),
            sa.Column('modifiers', sa.JSON(), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('character_id', name='uq_character_satiety_character'),
        )
        op.create_index(
            'ix_character_satiety_expires_at', 'character_satiety', ['expires_at'],
        )


def downgrade() -> None:
    if _table_exists('character_satiety'):
        op.drop_index('ix_character_satiety_expires_at', table_name='character_satiety')
        op.drop_table('character_satiety')

    columns = _existing_columns('character_attributes')
    for name in reversed(_CARRY_COLUMNS):
        if name in columns:
            op.drop_column('character_attributes', name)
    if 'regen_anchor_at' in columns:
        op.drop_column('character_attributes', 'regen_anchor_at')
