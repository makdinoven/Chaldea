"""Add privacy settings and site background to users

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-22

Adds to `users`:
- wall_view_privacy      VARCHAR(10) NOT NULL DEFAULT 'all'  (all|friends|nobody)
- wall_post_privacy      VARCHAR(10) NOT NULL DEFAULT 'all'  (all|friends|nobody)
- friends_list_privacy   VARCHAR(10) NOT NULL DEFAULT 'all'  (all|friends|nobody)
- friend_request_privacy VARCHAR(10) NOT NULL DEFAULT 'all'  (all|nobody)
- show_online            BOOLEAN     NOT NULL DEFAULT true
- site_background_url    VARCHAR(512) NULL

Plain strings (not ENUM) on purpose: values are validated in the API layer, and
widening an ENUM on MySQL later needs a table rebuild. Existing rows get the
server defaults, i.e. everything stays public exactly as before.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


_AUDIENCE_COLUMNS = (
    'wall_view_privacy',
    'wall_post_privacy',
    'friends_list_privacy',
    'friend_request_privacy',
)


def upgrade() -> None:
    for name in _AUDIENCE_COLUMNS:
        op.add_column(
            'users',
            sa.Column(name, sa.String(10), nullable=False, server_default='all'),
        )
    op.add_column(
        'users',
        sa.Column('show_online', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'users',
        sa.Column('site_background_url', sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'site_background_url')
    op.drop_column('users', 'show_online')
    for name in reversed(_AUDIENCE_COLUMNS):
        op.drop_column('users', name)
