"""Add titles module permissions for admin title management

Revision ID: 0018
Revises: 0017
Create Date: 2026-03-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("titles", "read", "Просмотр списка титулов"),
    ("titles", "create", "Создание титулов"),
    ("titles", "update", "Редактирование титулов"),
    ("titles", "delete", "Удаление титулов"),
    ("titles", "grant", "Выдача титулов игрокам"),
]

# Role assignments: (role_id, list of actions)
# Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
# Moderator (role_id=3): read, create, update, grant
# Editor (role_id=2): read only
ROLE_ACTIONS = {
    3: ["read", "create", "update", "grant"],
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
        sa.text("SELECT id FROM permissions WHERE module = 'titles'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(pid) for pid in perm_ids)
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")
