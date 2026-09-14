"""post_versions — the text a post had BEFORE each edit (FEAT-160, T2).

A row is **not** a snapshot of the post after an edit, it is the text that the
edit *destroyed*. Storing the "after" text would lose the original at the very
first edit — and the original wording is precisely what gets quoted and then
disputed (FEAT-160 section 3.4). The current text is never copied here; it is
read live from ``posts.content``. Hence the deliberate off-by-one: a row's
``edited_by_user_id`` / ``created_at`` describe the edit that *replaced* the
stored text, not the edit that produced it.

**Why ``post_id`` is NOT NULL + ON DELETE CASCADE, unlike migrations 037/039.**
Those tables (``post_deletion_requests``, ``post_reports``, ``post_gate_requests``)
hold **staff decisions** — evidence of what a moderator did — so they are
nullable with ``ON DELETE SET NULL`` and keep their value after the post is
gone. A ``post_versions`` row is the opposite kind of thing: it is **a copy of
the post's own content**. Once the post is deleted — very often deleted *by
moderation, for that content* — an orphaned row is not an audit trail, it is a
surviving copy of removed text sitting in an admin view with nothing to attach
it to. It would quietly defeat the deletion. ``NOT NULL`` makes the orphan state
unrepresentable rather than merely unlikely, and the DB-level cascade means no
future deletion path can forget to clean up (FEAT-160 section 3.3).

**``is_original`` is meaningful only on ``version_no = 1``.** History starts
accruing only from this deployment, so for a post edited *before* it the earliest
text is simply gone and cannot be recovered afterwards. Whether the first row
recorded for a post really holds the original is therefore decided at write time:
``is_original = (posts.edited_at IS NULL)``. On every later row the column is
meaningless and must be ignored. The API turns the ``version_no = 1`` flag into
``original_available`` so the UI can say «Более ранние версии не сохранились»
instead of implying the post was never edited.

No separate ``idx_post_versions_post``: the unique key's leading column is
``post_id``, which serves both the foreign key and every query this feature makes.

Rollback: ``DROP TABLE post_versions``. Nothing else in the system reads it.

Revision ID: 040_post_versions
Revises: 039_post_gate_requests
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '040_post_versions'
down_revision = '039_post_gate_requests'
branch_labels = None
depends_on = None


TABLE = "post_versions"
UNIQUE_KEY = "uq_post_versions_post_version"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE in inspector.get_table_names():
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # NOT NULL + CASCADE: a version is part of the post, not a record about
        # it. See the module docstring.
        sa.Column("post_id", sa.Integer(), nullable=False),
        # 1 = the oldest stored text. Computed as MAX(version_no) + 1 under the
        # SELECT ... FOR UPDATE that already serialises edits of one post; the
        # unique key below is the backstop.
        sa.Column("version_no", sa.Integer(), nullable=False),
        # The post's content as it was BEFORE the edit recorded by this row.
        sa.Column("content", sa.Text(), nullable=False),
        # Who performed the edit that replaced `content` (the author, or an
        # admin editing somebody else's post).
        sa.Column("edited_by_user_id", sa.Integer(), nullable=False),
        # Only meaningful on version_no = 1: does this row hold the true
        # original, or had the post already been edited before history existed?
        sa.Column(
            "is_original", sa.Boolean(),
            server_default=sa.text("1"), nullable=False,
        ),
        # When the edit that replaced `content` happened.
        sa.Column(
            "created_at", sa.TIMESTAMP(),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"],
            name="fk_post_versions_post_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "version_no", name=UNIQUE_KEY),
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        return

    # DROP TABLE takes the unique key and the foreign key with it. Dropping the
    # index first is impossible anyway: uq_post_versions_post_version backs the
    # post_id FK, and MySQL refuses with ERROR 1553 ("Cannot drop index ...:
    # needed in a foreign key constraint").
    op.drop_table(TABLE)
