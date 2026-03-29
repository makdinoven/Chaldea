"""Add diamonds column to users and battlepass RBAC permissions

Revision ID: 0022
Revises: 0021
Create Date: 2026-03-29

Adds:
- diamonds column (Integer, default 0) to users table
- RBAC permissions: battlepass:read, battlepass:create, battlepass:update, battlepass:delete
- Admin gets all permissions automatically (no explicit assignment needed)
- Moderator and editor get battlepass:read
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("battlepass", "read", "Просмотр батл пасса в админке"),
    ("battlepass", "create", "Создание сезонов батл пасса"),
    ("battlepass", "update", "Редактирование сезонов, уровней и заданий"),
    ("battlepass", "delete", "Удаление сезонов батл пасса"),
]

# Role assignments: (role_id, list of actions)
# Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
# Moderator (role_id=3): read
# Editor (role_id=2): read
ROLE_ACTIONS = {
    3: ["read"],
    2: ["read"],
}


def upgrade() -> None:
    # 1. Add diamonds column to users
    op.add_column('users', sa.Column('diamonds', sa.Integer(), nullable=False, server_default='0'))

    # 2. Add battlepass RBAC permissions
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
    # Remove battlepass permissions
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM permissions WHERE module = 'battlepass'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(pid) for pid in perm_ids)
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")

    # Remove diamonds column
    op.drop_column('users', 'diamonds')
