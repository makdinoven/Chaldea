"""Add origins module permissions for the origin admin CRUD (FEAT-154)

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-06

Adds:
- RBAC permissions: origins:read, origins:create, origins:update, origins:delete
- Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
- Moderator (role_id=3): origins:read, origins:update
- Editor   (role_id=2): origins:read

Pattern follows 0025_add_gathering_permissions.py (idempotent SELECT-then-INSERT).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("origins", "read",   "Просмотр происхождений персонажей"),
    ("origins", "create", "Создание происхождений персонажей"),
    ("origins", "update", "Изменение происхождений персонажей"),
    ("origins", "delete", "Удаление происхождений персонажей"),
]

# Role assignments: (role_id, list of actions)
# Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
# Moderator (role_id=3): read, update
# Editor (role_id=2): read only
ROLE_ACTIONS = {
    3: ["read", "update"],
    2: ["read"],
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
        sa.text("SELECT id FROM permissions WHERE module = 'origins'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(int(pid)) for pid in perm_ids)
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")
