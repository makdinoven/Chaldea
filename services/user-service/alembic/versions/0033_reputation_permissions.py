"""Add reputation module permissions for the admin «Репутация» section (FEAT-197)

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-03

Adds:
- RBAC permissions: reputation:read, reputation:manage, reputation:settings
- Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
- Moderator (role_id=3): reputation:read, reputation:manage (per-character adjust with a reason)
- Editor   (role_id=2): nothing
- reputation:settings (tiers, action weights, NPC roles) — admin only

Pattern follows 0032_add_economy_permissions.py (idempotent SELECT-then-INSERT).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("reputation", "read",     "Просмотр репутации персонажей и журнала изменений"),
    ("reputation", "manage",   "Ручное изменение репутации персонажа (с причиной)"),
    ("reputation", "settings", "Настройка ступеней, весов действий и ролей NPC для репутации"),
]

# Role assignments: (role_id, list of actions)
# Admin (role_id=4) gets all permissions automatically — no explicit assignment needed
# Moderator (role_id=3): read + manage
ROLE_ACTIONS = {
    3: ["read", "manage"],
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
        sa.text("SELECT id FROM permissions WHERE module = 'reputation'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(int(pid)) for pid in perm_ids)
        op.execute(f"DELETE FROM user_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")
