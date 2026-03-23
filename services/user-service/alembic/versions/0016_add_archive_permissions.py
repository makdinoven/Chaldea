"""Add archive permissions for lore/wiki system

Revision ID: 0016
Revises: 0015
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("archive", "read", "Просмотр статей архива в админ-панели"),
    ("archive", "create", "Создание статей и категорий архива"),
    ("archive", "update", "Редактирование статей и категорий архива"),
    ("archive", "delete", "Удаление статей и категорий архива"),
]


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

        # Assign to Admin (role_id=4) and Moderator (role_id=3)
        for role_id in (4, 3):
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
        sa.text("SELECT id FROM permissions WHERE module = 'archive'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(pid) for pid in perm_ids)
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")
