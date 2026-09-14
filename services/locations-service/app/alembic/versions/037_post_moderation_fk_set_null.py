"""post moderation FKs: ON DELETE CASCADE -> ON DELETE SET NULL (FEAT-158, bug 4).

``post_deletion_requests.post_id`` and ``post_reports.post_id`` were created by
``016_add_post_moderation`` as ``ON DELETE CASCADE``.  That made the one action
moderation exists for — approving a deletion / resolving a report, both of which
delete the post — destroy the moderation row itself mid-transaction; the
handler's following status UPDATE then raised ``StaleDataError`` and the whole
transaction rolled back.  Approve/resolve has therefore *always* returned 500.

Switching the rule to ``SET NULL`` keeps the decision history: the moderation
row survives the post with ``post_id IS NULL``.

Two details make this more than a one-liner:

* The original constraints are **unnamed** (declared inline in 016), so MySQL
  auto-generated their names.  We introspect them rather than hardcoding
  ``*_ibfk_1``, and skip a table cleanly if no ``post_id`` FK is present (an
  install may already have been repaired by hand).
* ``post_id`` is ``NOT NULL``, and MySQL rejects ``SET NULL`` on a NOT NULL
  column (ERROR 1830).  The column can only be altered while the FK is dropped,
  so the order per table is: drop FK -> make nullable -> create named FK.

``uq_post_report_user (post_id, user_id)`` is deliberately left alone: MySQL
allows repeated NULLs inside a unique index, so orphaned reports cannot collide
and a user can still report a new post afterwards.

**downgrade() is lossy by necessity.**  The original post ids are gone, so
orphaned rows cannot be re-linked; restoring ``NOT NULL`` + ``CASCADE`` requires
``DELETE FROM <table> WHERE post_id IS NULL`` first.  Rolling back therefore
discards exactly the audit rows this upgrade was added to preserve.

Revision ID: 037_post_moderation_fk_set_null
Revises: 036_add_post_drafts
Create Date: 2026-09-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '037_post_moderation_fk_set_null'
down_revision = '036_add_post_drafts'
branch_labels = None
depends_on = None


TABLES = (
    ('post_deletion_requests', 'fk_post_deletion_requests_post_id'),
    ('post_reports', 'fk_post_reports_post_id'),
)


def _post_id_fk_name(insp, table: str):
    """Return the name of the FK on `table.post_id`, or None if there is none."""
    for fk in insp.get_foreign_keys(table):
        if fk.get('constrained_columns') == ['post_id']:
            return fk.get('name')
    return None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    for table, fk_name in TABLES:
        if table not in existing_tables:
            continue
        current = _post_id_fk_name(insp, table)
        if current is None:
            # Already repaired by hand, or the FK was never created — nothing
            # to convert, and altering the column alone would be a silent
            # schema drift. Skip.
            continue
        op.drop_constraint(current, table, type_='foreignkey')
        op.alter_column(
            table, 'post_id',
            existing_type=sa.Integer(),
            nullable=True,
        )
        op.create_foreign_key(
            fk_name, table, 'posts',
            ['post_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    for table, _fk_name in TABLES:
        if table not in existing_tables:
            continue
        current = _post_id_fk_name(insp, table)
        if current is not None:
            op.drop_constraint(current, table, type_='foreignkey')
        # Lossy: rows whose post is gone cannot be re-linked, and NOT NULL
        # cannot be restored while they exist.
        op.execute(sa.text(f"DELETE FROM {table} WHERE post_id IS NULL"))
        op.alter_column(
            table, 'post_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.create_foreign_key(
            None, table, 'posts',
            ['post_id'], ['id'],
            ondelete='CASCADE',
        )
