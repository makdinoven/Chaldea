"""Initial baseline for character_attributes table

Revision ID: 001_initial_baseline
Revises:
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'character_attributes' not in existing_tables:
        op.create_table(
            'character_attributes',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer(), unique=True, index=True),
            sa.Column('passive_experience', sa.Integer(), server_default='0'),
            sa.Column('active_experience', sa.Integer(), server_default='0'),
            sa.Column('current_health', sa.Integer(), server_default='100'),
            sa.Column('current_mana', sa.Integer(), server_default='75'),
            sa.Column('current_energy', sa.Integer(), server_default='50'),
            sa.Column('current_stamina', sa.Integer(), server_default='50'),
            sa.Column('max_health', sa.Integer(), server_default='100'),
            sa.Column('max_mana', sa.Integer(), server_default='75'),
            sa.Column('max_energy', sa.Integer(), server_default='50'),
            sa.Column('max_stamina', sa.Integer(), server_default='50'),
            sa.Column('health', sa.Integer(), server_default='0'),
            sa.Column('mana', sa.Integer(), server_default='0'),
            sa.Column('energy', sa.Integer(), server_default='0'),
            sa.Column('stamina', sa.Integer(), server_default='0'),
            sa.Column('endurance', sa.Integer(), server_default='0'),
            sa.Column('strength', sa.Integer(), server_default='0'),
            sa.Column('agility', sa.Integer(), server_default='0'),
            sa.Column('intelligence', sa.Integer(), server_default='0'),
            sa.Column('luck', sa.Integer(), server_default='0'),
            sa.Column('charisma', sa.Integer(), server_default='0'),
            sa.Column('damage', sa.Integer(), server_default='0'),
            sa.Column('dodge', sa.Float(), server_default='5.0'),
            sa.Column('critical_hit_chance', sa.Float(), server_default='20.0'),
            sa.Column('critical_damage', sa.Integer(), server_default='125'),
            sa.Column('res_effects', sa.Float(), server_default='0.0'),
            sa.Column('res_physical', sa.Float(), server_default='0.0'),
            sa.Column('res_catting', sa.Float(), server_default='0.0'),
            sa.Column('res_crushing', sa.Float(), server_default='0.0'),
            sa.Column('res_piercing', sa.Float(), server_default='0.0'),
            sa.Column('res_magic', sa.Float(), server_default='0.0'),
            sa.Column('res_fire', sa.Float(), server_default='0.0'),
            sa.Column('res_ice', sa.Float(), server_default='0.0'),
            sa.Column('res_watering', sa.Float(), server_default='0.0'),
            sa.Column('res_electricity', sa.Float(), server_default='0.0'),
            sa.Column('res_sainting', sa.Float(), server_default='0.0'),
            sa.Column('res_wind', sa.Float(), server_default='0.0'),
            sa.Column('res_damning', sa.Float(), server_default='0.0'),
            sa.Column('vul_effects', sa.Float(), server_default='0.0'),
            sa.Column('vul_physical', sa.Float(), server_default='0.0'),
            sa.Column('vul_catting', sa.Float(), server_default='0.0'),
            sa.Column('vul_crushing', sa.Float(), server_default='0.0'),
            sa.Column('vul_piercing', sa.Float(), server_default='0.0'),
            sa.Column('vul_magic', sa.Float(), server_default='0.0'),
            sa.Column('vul_fire', sa.Float(), server_default='0.0'),
            sa.Column('vul_ice', sa.Float(), server_default='0.0'),
            sa.Column('vul_watering', sa.Float(), server_default='0.0'),
            sa.Column('vul_electricity', sa.Float(), server_default='0.0'),
            sa.Column('vul_sainting', sa.Float(), server_default='0.0'),
            sa.Column('vul_wind', sa.Float(), server_default='0.0'),
            sa.Column('vul_damning', sa.Float(), server_default='0.0'),
        )


def downgrade() -> None:
    op.drop_table('character_attributes')
