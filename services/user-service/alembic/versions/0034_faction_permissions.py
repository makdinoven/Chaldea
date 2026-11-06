"""Add factions module permissions for the admin «Фракции» section (FEAT-205)

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-05

Adds:
- RBAC permissions: factions:read, factions:edit, factions:delete, factions:manage, factions:settings
- Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
- Moderator (role_id=3): factions:read, factions:edit, factions:manage
- Editor   (role_id=2): nothing
- factions:delete and factions:settings — admin only

Pattern follows 0033_reputation_permissions.py (idempotent SELECT-then-INSERT).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("factions", "read",     "Просмотр фракций, участников, заявок и выдачи наград"),
    ("factions", "edit",     "Создание и изменение фракций, званий, условий и враждебности"),
    ("factions", "delete",   "Удаление фракций и званий"),
    ("factions", "manage",   "Заявки, ручное изменение очков, исключение участников, повтор выдачи"),
    ("factions", "settings", "Настройка общих правил фракций (сроки, штрафы, проход)"),
]

# Role assignments: (role_id, list of actions)
# Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
# Moderator (role_id=3): read + edit + manage
ROLE_ACTIONS = {
    3: ["read", "edit", "manage"],
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
        sa.text("SELECT id FROM permissions WHERE module = 'factions'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(int(pid)) for pid in perm_ids)
        op.execute(f"DELETE FROM user_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")
