"""Add posts:history permission for the admin post edit history (FEAT-160)

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-14

Adds:
- RBAC permission: posts:history

DELIBERATELY GRANTED TO NO ROLE AT ALL — the empty grant IS the feature, not an
oversight. Do not "fix" this migration by attaching the permission to a role.

Why the empty grant works:
`crud.get_effective_permissions` (services/user-service/crud.py:14-35) hands the
role `admin` EVERY row of the `permissions` table, computed by selecting the
table itself. Every other role gets only its explicit `role_permissions` rows
plus `user_permissions` overrides. So a permission registered with zero
`role_permissions` rows is, by construction:

  * held by every admin, automatically and for ever, including admins created
    later;
  * held by no moderator, no editor, no plain player;
  * delegable to one named person through `user_permissions` — the user can hand
    post history to a specific trusted moderator without a code change or a
    deploy.

That last property is exactly why a grantable permission was chosen over a hard
role check (`get_strict_admin_user`): the business rule is "admins only", but it
must stay delegable.

Precedent: 0028_add_characters_teleport_permission.py (`characters:teleport`,
FEAT-162) established this pattern for the same reason. This is its second
instance.

Why the name is `posts:history` and not `moderation:post_history`:
The admin tile «Модерация постов» (AdminPage.tsx:33) renders from
`hasModuleAccess(perms, 'moderation')` — i.e. ANY `moderation:*` permission —
while the route itself demands `moderation:read` (App.tsx:221-222). A delegated
holder of `moderation:post_history` would therefore see the tile and be bounced
back to /home on click: exactly the FEAT-158 bug, re-created by a naming choice.
A separate `posts` module avoids it. Single-action modules are already normal
here (`photos:upload`, `battles:manage`, `mobs:manage`), and the admin tile list
(AdminPage.tsx:18-36) is a hardcoded array, so a new module adds no stray tile.

Pattern follows 0028 (idempotent SELECT-then-INSERT, no hardcoded ids).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None

MODULE = "posts"
ACTION = "history"
DESCRIPTION = "Просмотр истории правок постов (админ)"


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
