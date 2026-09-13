"""Add characters:teleport permission for the admin character move (FEAT-162)

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-14

Adds:
- RBAC permission: characters:teleport

Deliberately assigned to NO role. Admin (role_id=4) receives every row of the
`permissions` table automatically via crud.get_effective_permissions, so admins
get it; every other role only gets its explicit `role_permissions` rows (plus
`user_permissions` overrides), so moderators do NOT get it.

This is the whole point of the migration: the existing `characters:*`
permissions (0007_add_remaining_permissions.py) are granted to both Admin and
Moderator, so none of them can express "admins only".

Pattern follows 0027_add_moderation_permissions.py (idempotent SELECT-then-INSERT).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None

MODULE = "characters"
ACTION = "teleport"
DESCRIPTION = "Перенос персонажа в произвольную локацию (админ)"


def upgrade() -> None:
    conn = op.get_bind()

    existing = conn.execute(
        sa.text("SELECT id FROM permissions WHERE module = :m AND action = :a"),
        {"m": MODULE, "a": ACTION}
    ).fetchone()

    if not existing:
        conn.execute(
            sa.text("INSERT INTO permissions (module, action, description) VALUES (:m, :a, :d)"),
            {"m": MODULE, "a": ACTION, "d": DESCRIPTION}
        )

    # No role_permissions rows on purpose — see the module docstring.


def downgrade() -> None:
    conn = op.get_bind()

    row = conn.execute(
        sa.text("SELECT id FROM permissions WHERE module = :m AND action = :a"),
        {"m": MODULE, "a": ACTION}
    ).fetchone()

    if row:
        perm_id = int(row[0])
        conn.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :p"), {"p": perm_id}
        )
        conn.execute(
            sa.text("DELETE FROM user_permissions WHERE permission_id = :p"), {"p": perm_id}
        )
        conn.execute(
            sa.text("DELETE FROM permissions WHERE id = :p"), {"p": perm_id}
        )
