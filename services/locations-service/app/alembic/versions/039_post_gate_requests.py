"""post_gate_requests — moderation requests for retro-added intent gates
(FEAT-159, Phase B, T7).

A gate the player forgot at publication can be added during an edit, but it does
**not** fire: the edit only files a row here, and the mechanic unlocks solely if
an admin approves it (then, and only then, ``crud.create_action_gates`` runs).

**Why a new table rather than reusing ``post_deletion_requests``.** That table
has the right shape but cannot carry the gate payload, and its approve branch
*deletes the post* — the single most dangerous place in this service to bolt on
a "grant rights" conditional. Minimal diff means minimal *risk*, not minimal
table count (FEAT-159 section 3.7).

``post_id`` is nullable with ``ON DELETE SET NULL``, the policy migration 037
established for the other two moderation tables (FEAT-158, bug 4): a moderation
decision must outlive the post it is about. ``location_id`` cascades — a deleted
location has no gates to grant.

No unique index enforces "one pending request per post": MySQL has no partial
unique index, and ``UNIQUE(post_id, status)`` would forbid a second *rejected*
row. The guard is code-level (409 in ``crud.edit_post``), which is adequate
because the symbol budget already counts pending requests, so even a duplicate
that slipped through could not buy anything.

Rollback: ``DROP TABLE post_gate_requests``. Phase A is unaffected.

Revision ID: 039_post_gate_requests
Revises: 038_post_edit_columns
Create Date: 2026-09-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '039_post_gate_requests'
down_revision = '038_post_edit_columns'
branch_labels = None
depends_on = None


TABLE = "post_gate_requests"
QUEUE_INDEX = "idx_pgr_queue"
POST_INDEX = "idx_pgr_post"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE in inspector.get_table_names():
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # Nullable + SET NULL: the decision history survives the post (policy of
        # migration 037).
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.BigInteger(), nullable=False),
        # The requester (the editing user — an admin may file it on someone
        # else's post, so this is not derivable from character_id).
        sa.Column("user_id", sa.Integer(), nullable=False),
        # [{"action_type": "...", "targets": [...]}] — the gates to grant on
        # approval. Same shape as crud.normalize_gates output.
        sa.Column("gates", sa.JSON(), nullable=False),
        # pending | approved | rejected | expired
        sa.Column(
            "status", sa.String(length=20),
            server_default="pending", nullable=False,
        ),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(),
            server_default=sa.func.now(), nullable=False,
        ),
        # Explicitly nullable with no server default: with MySQL's legacy
        # explicit_defaults_for_timestamp=OFF an unqualified TIMESTAMP can be
        # turned into NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE
        # CURRENT_TIMESTAMP. created_at already occupies that slot, but we do
        # not rely on column order.
        sa.Column(
            "reviewed_at", sa.TIMESTAMP(),
            nullable=True, server_default=None,
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"],
            name="fk_post_gate_requests_post_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["Locations.id"],
            name="fk_post_gate_requests_location_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
    )
    op.create_index(QUEUE_INDEX, TABLE, ["status", "created_at"])
    op.create_index(POST_INDEX, TABLE, ["post_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        return

    # DROP TABLE removes the indexes and both foreign keys with it. Dropping
    # them first is not only redundant but impossible: `idx_pgr_post` backs the
    # `post_id` FK, and MySQL refuses with ERROR 1553 ("Cannot drop index ...:
    # needed in a foreign key constraint").
    op.drop_table(TABLE)
