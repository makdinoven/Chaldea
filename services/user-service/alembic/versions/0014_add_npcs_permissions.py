"""Add npcs RBAC permissions (read, create, update, delete)

Revision ID: 0014
Revises: 0013
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Insert permissions without hardcoded IDs (auto-increment)
    perms = [
        ('npcs', 'read', 'Просмотр NPC'),
        ('npcs', 'create', 'Создание NPC'),
        ('npcs', 'update', 'Редактирование NPC'),
        ('npcs', 'delete', 'Удаление NPC'),
    ]

    perm_ids = []
    for module, action, description in perms:
        # Skip if already exists
        existing = conn.execute(
            sa.text("SELECT id FROM permissions WHERE module = :m AND action = :a"),
            {"m": module, "a": action}
        ).fetchone()
        if existing:
            perm_ids.append(existing[0])
            continue
        conn.execute(
            sa.text("INSERT INTO permissions (module, action, description) VALUES (:m, :a, :d)"),
            {"m": module, "a": action, "d": description}
        )
        new_id = conn.execute(sa.text("SELECT LAST_INSERT_ID()")).scalar()
        perm_ids.append(new_id)

    # role_permissions: Admin(4) all, Moderator(3) all, Editor(2) read only
    role_perm_pairs = []
    for pid in perm_ids:
        role_perm_pairs.append((4, pid))  # Admin
        role_perm_pairs.append((3, pid))  # Moderator
    role_perm_pairs.append((2, perm_ids[0]))  # Editor: read only

    for role_id, perm_id in role_perm_pairs:
        existing = conn.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role_id = :r AND permission_id = :p"),
            {"r": role_id, "p": perm_id}
        ).fetchone()
        if not existing:
            conn.execute(
                sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
                {"r": role_id, "p": perm_id}
            )


def downgrade() -> None:
    conn = op.get_bind()
    # Find permission IDs by module
    rows = conn.execute(
        sa.text("SELECT id FROM permissions WHERE module = 'npcs'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(pid) for pid in perm_ids)
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")
