"""Add dungeon RBAC permissions

Revision ID: 0024
Revises: 0023
Create Date: 2026-03-29

Adds:
- RBAC permissions: dungeons:create, dungeons:edit, dungeons:delete, dungeons:view
- Admin gets all permissions automatically (no explicit assignment needed)
- Moderator gets dungeons:view, dungeons:create, dungeons:edit, dungeons:delete
- Editor gets dungeons:view
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("dungeons", "create", "Создание подземелий"),
    ("dungeons", "edit", "Редактирование подземелий"),
    ("dungeons", "delete", "Удаление подземелий"),
    ("dungeons", "view", "Просмотр подземелий в админке"),
]

# Role assignments: (role_id, list of actions)
# Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
# Moderator (role_id=3): all dungeon permissions
# Editor (role_id=2): view only
ROLE_ACTIONS = {
    3: ["create", "edit", "delete", "view"],
    2: ["view"],
}


def upgrade() -> None:
    conn = op.get_bind()

    for module, action, description in PERMISSIONS:
        # Insert permission (skip if already exists)
        existing = conn.execute(
            sa.text("SELECT id FROM permissions WHERE module = :m AND action = :a"),
            {"m": module, "a": action}
        ).fetchone()

        if existing:
            perm_id = existing[0]
        else:
            conn.execute(
                sa.text("INSERT INTO permissions (module, action, description) VALUES (:m, :a, :d)"),
                {"m": module, "a": action, "d": description}
            )
            perm_id = conn.execute(sa.text("SELECT LAST_INSERT_ID()")).scalar()

        # Assign to roles based on ROLE_ACTIONS mapping
        for role_id, actions in ROLE_ACTIONS.items():
            if action in actions:
                existing_rp = conn.execute(
                    sa.text("SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
                    {"r": role_id, "p": perm_id}
                ).fetchone()
                if not existing_rp:
                    conn.execute(
                        sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
                        {"r": role_id, "p": perm_id}
                    )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM permissions WHERE module = 'dungeons'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(pid) for pid in perm_ids)
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")
