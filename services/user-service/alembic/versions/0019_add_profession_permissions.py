"""Add professions module permissions for admin profession/recipe management

Revision ID: 0019
Revises: 0018
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("professions", "read", "Просмотр профессий и рецептов"),
    ("professions", "create", "Создание профессий и рецептов"),
    ("professions", "update", "Редактирование профессий и рецептов"),
    ("professions", "delete", "Удаление профессий и рецептов"),
    ("professions", "manage", "Управление профессиями игроков (установка ранга и т.д.)"),
]

# Role assignments: (role_id, list of actions)
# Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
# Moderator (role_id=3): read, create, update, manage
# Editor (role_id=2): read only
ROLE_ACTIONS = {
    3: ["read", "create", "update", "manage"],
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
        sa.text("SELECT id FROM permissions WHERE module = 'professions'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(pid) for pid in perm_ids)
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")
