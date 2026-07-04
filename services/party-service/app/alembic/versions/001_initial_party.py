"""Initial party-service schema: parties + party_members (FEAT-144 Ф1)."""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '001_initial_party'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'parties',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('avatar', sa.String(length=255), nullable=True),
        sa.Column('leader_character_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_parties_leader_character_id', 'parties', ['leader_character_id'])

    op.create_table(
        'party_members',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('party_id', sa.BigInteger(), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('is_leader', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('status', sa.Enum('invited', 'accepted', name='memberstatus'), nullable=False),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('party_id', 'character_id', name='uq_party_member'),
    )
    op.create_index('ix_party_members_party_id', 'party_members', ['party_id'])
    op.create_index('ix_party_members_character_id', 'party_members', ['character_id'])


def downgrade():
    op.drop_table('party_members')
    op.drop_index('ix_parties_leader_character_id', table_name='parties')
    op.drop_table('parties')
