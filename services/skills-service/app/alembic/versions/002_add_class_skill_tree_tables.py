"""Add class skill tree tables (FEAT-056)

Revision ID: 002_class_skill_trees
Revises: 001_initial
Create Date: 2026-03-20

Creates 5 new tables for the class/subclass skill tree system:
- class_skill_trees
- tree_nodes
- tree_node_connections
- tree_node_skills
- character_tree_progress

All tables are additive — no existing tables are modified.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_class_skill_trees'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # class_skill_trees
    if 'class_skill_trees' not in existing_tables:
        op.create_table(
            'class_skill_trees',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('class_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('tree_type', sa.String(20), nullable=False, server_default='class'),
            sa.Column('parent_tree_id', sa.Integer(), nullable=True),
            sa.Column('subclass_name', sa.String(100), nullable=True),
            sa.Column('tree_image', sa.Text(), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['parent_tree_id'], ['class_skill_trees.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('class_id', 'tree_type', 'subclass_name', name='uq_class_tree_type_subclass'),
        )
        op.create_index(op.f('ix_class_skill_trees_id'), 'class_skill_trees', ['id'], unique=False)

    # tree_nodes
    if 'tree_nodes' not in existing_tables:
        op.create_table(
            'tree_nodes',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('tree_id', sa.Integer(), nullable=False),
            sa.Column('level_ring', sa.Integer(), nullable=False),
            sa.Column('position_x', sa.Float(), nullable=False, server_default='0'),
            sa.Column('position_y', sa.Float(), nullable=False, server_default='0'),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('node_type', sa.String(20), nullable=False, server_default='regular'),
            sa.Column('icon_image', sa.Text(), nullable=True),
            sa.Column('sort_order', sa.Integer(), server_default='0'),
            sa.ForeignKeyConstraint(['tree_id'], ['class_skill_trees.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_tree_nodes_id'), 'tree_nodes', ['id'], unique=False)

    # tree_node_connections
    if 'tree_node_connections' not in existing_tables:
        op.create_table(
            'tree_node_connections',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('tree_id', sa.Integer(), nullable=False),
            sa.Column('from_node_id', sa.Integer(), nullable=False),
            sa.Column('to_node_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['tree_id'], ['class_skill_trees.id']),
            sa.ForeignKeyConstraint(['from_node_id'], ['tree_nodes.id']),
            sa.ForeignKeyConstraint(['to_node_id'], ['tree_nodes.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('from_node_id', 'to_node_id', name='uq_connection_from_to'),
        )
        op.create_index(op.f('ix_tree_node_connections_id'), 'tree_node_connections', ['id'], unique=False)

    # tree_node_skills
    if 'tree_node_skills' not in existing_tables:
        op.create_table(
            'tree_node_skills',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('node_id', sa.Integer(), nullable=False),
            sa.Column('skill_id', sa.Integer(), nullable=False),
            sa.Column('sort_order', sa.Integer(), server_default='0'),
            sa.ForeignKeyConstraint(['node_id'], ['tree_nodes.id']),
            sa.ForeignKeyConstraint(['skill_id'], ['skills.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('node_id', 'skill_id', name='uq_node_skill'),
        )
        op.create_index(op.f('ix_tree_node_skills_id'), 'tree_node_skills', ['id'], unique=False)

    # character_tree_progress
    if 'character_tree_progress' not in existing_tables:
        op.create_table(
            'character_tree_progress',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('character_id', sa.Integer(), nullable=False),
            sa.Column('tree_id', sa.Integer(), nullable=False),
            sa.Column('node_id', sa.Integer(), nullable=False),
            sa.Column('chosen_at', sa.TIMESTAMP(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['tree_id'], ['class_skill_trees.id']),
            sa.ForeignKeyConstraint(['node_id'], ['tree_nodes.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('character_id', 'node_id', name='uq_character_node'),
        )
        op.create_index(op.f('ix_character_tree_progress_id'), 'character_tree_progress', ['id'], unique=False)
        op.create_index(op.f('ix_character_tree_progress_character_id'), 'character_tree_progress', ['character_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_character_tree_progress_character_id'), table_name='character_tree_progress')
    op.drop_index(op.f('ix_character_tree_progress_id'), table_name='character_tree_progress')
    op.drop_table('character_tree_progress')
    op.drop_index(op.f('ix_tree_node_skills_id'), table_name='tree_node_skills')
    op.drop_table('tree_node_skills')
    op.drop_index(op.f('ix_tree_node_connections_id'), table_name='tree_node_connections')
    op.drop_table('tree_node_connections')
    op.drop_index(op.f('ix_tree_nodes_id'), table_name='tree_nodes')
    op.drop_table('tree_nodes')
    op.drop_index(op.f('ix_class_skill_trees_id'), table_name='class_skill_trees')
    op.drop_table('class_skill_trees')
