"""posts: edited_at / edited_by_user_id — the «изменено» marker (FEAT-159, T1).

Posts were immutable until FEAT-159; editing one needs a durable, visible record
that it happened, because a line may have been quoted before the edit.

Two nullable columns, both written by exactly one code path (``crud.edit_post``):

* ``edited_at``          — when the post was last edited. NULL = never edited.
* ``edited_by_user_id``  — who edited it. Audit trail only; it is never sent to a
  client. The «изменено администратором» flag is *derived* in
  ``crud.get_post_details`` by comparing this value with the author's ``user_id``
  from character-service, so no third column is stored.

**Rejected alternative:** a generic
``updated_at TIMESTAMP ... ON UPDATE CURRENT_TIMESTAMP``. It fires on *any*
future write to the row — a backfill, an admin script, a column added later —
and would mark the whole table as «изменено». These columns mean one thing.

``edited_at`` must be an explicitly nullable TIMESTAMP with ``DEFAULT NULL``:
MySQL's ``explicit_defaults_for_timestamp=OFF`` legacy would otherwise turn the
first TIMESTAMP column of a table into ``NOT NULL DEFAULT CURRENT_TIMESTAMP ON
UPDATE CURRENT_TIMESTAMP``. ``posts.created_at`` already occupies that slot, but
we pass ``nullable=True`` + ``server_default=None`` explicitly rather than rely
on the column order.

Rollback drops both columns. The only data lost is the marker itself; post text,
authorship and ``created_at`` are untouched.

Revision ID: 038_post_edit_columns
Revises: 037_post_moderation_fk_set_null
Create Date: 2026-09-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '038_post_edit_columns'
down_revision = '037_post_moderation_fk_set_null'
branch_labels = None
depends_on = None


COLUMNS = ('edited_at', 'edited_by_user_id')


def _existing_columns() -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns('posts')}


def upgrade() -> None:
    existing = _existing_columns()

    if 'edited_at' not in existing:
        op.add_column(
            'posts',
            sa.Column('edited_at', sa.TIMESTAMP(), nullable=True, server_default=None),
        )
    if 'edited_by_user_id' not in existing:
        op.add_column(
            'posts',
            sa.Column('edited_by_user_id', sa.Integer(), nullable=True, server_default=None),
        )


def downgrade() -> None:
    existing = _existing_columns()

    for column in reversed(COLUMNS):
        if column in existing:
            op.drop_column('posts', column)
