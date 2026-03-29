"""Add cosmetics tables, seed default frames/backgrounds, RBAC permissions

Revision ID: 0023
Revises: 0022
Create Date: 2026-03-29

Adds:
- cosmetic_frames table with ~15 default CSS frames
- cosmetic_backgrounds table with ~15 default CSS backgrounds
- user_unlocked_frames table (M2M)
- user_unlocked_backgrounds table (M2M)
- chat_background column on users table
- RBAC permissions: cosmetics:read, cosmetics:create, cosmetics:update, cosmetics:delete
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None

# --- Seed data ---

DEFAULT_FRAMES = [
    {"name": "Золотое свечение", "slug": "gold", "css_class": "frame-gold", "rarity": "common", "is_default": True},
    {"name": "Серебряное мерцание", "slug": "silver", "css_class": "frame-silver", "rarity": "common", "is_default": True},
    {"name": "Огненная пульсация", "slug": "fire", "css_class": "frame-fire", "rarity": "common", "is_default": True},
    {"name": "Радужный переливающийся контур", "slug": "rainbow", "css_class": "frame-rainbow", "rarity": "rare", "is_default": False},
    {"name": "Ледяной иней", "slug": "ice", "css_class": "frame-ice", "rarity": "rare", "is_default": False},
    {"name": "Теневая аура", "slug": "shadow", "css_class": "frame-shadow", "rarity": "rare", "is_default": False},
    {"name": "Электрические искры", "slug": "electric", "css_class": "frame-electric", "rarity": "epic", "is_default": False},
    {"name": "Изумрудное сияние", "slug": "emerald", "css_class": "frame-emerald", "rarity": "rare", "is_default": False},
    {"name": "Кровавый контур", "slug": "blood", "css_class": "frame-blood", "rarity": "epic", "is_default": False},
    {"name": "Звёздная пыль", "slug": "stardust", "css_class": "frame-stardust", "rarity": "epic", "is_default": False},
    {"name": "Неоновый контур", "slug": "neon", "css_class": "frame-neon", "rarity": "rare", "is_default": False},
    {"name": "Мистический туман", "slug": "mystic", "css_class": "frame-mystic", "rarity": "epic", "is_default": False},
    {"name": "Пламя феникса", "slug": "phoenix", "css_class": "frame-phoenix", "rarity": "legendary", "is_default": False},
    {"name": "Пустота", "slug": "void", "css_class": "frame-void", "rarity": "legendary", "is_default": False},
    {"name": "Божественное сияние", "slug": "divine", "css_class": "frame-divine", "rarity": "legendary", "is_default": False},
]

DEFAULT_BACKGROUNDS = [
    {"name": "Тёмно-синий градиент", "slug": "dark-blue", "css_class": "bg-msg-dark-blue", "rarity": "common", "is_default": True},
    {"name": "Фиолетовый туман", "slug": "purple-mist", "css_class": "bg-msg-purple-mist", "rarity": "common", "is_default": True},
    {"name": "Золотой блик", "slug": "golden-gleam", "css_class": "bg-msg-golden-gleam", "rarity": "rare", "is_default": False},
    {"name": "Огненный градиент", "slug": "fire-gradient", "css_class": "bg-msg-fire-gradient", "rarity": "rare", "is_default": False},
    {"name": "Ледяной градиент", "slug": "ice-gradient", "css_class": "bg-msg-ice-gradient", "rarity": "rare", "is_default": False},
    {"name": "Лесной зелёный", "slug": "forest-green", "css_class": "bg-msg-forest-green", "rarity": "common", "is_default": True},
    {"name": "Кровавый красный", "slug": "blood-red", "css_class": "bg-msg-blood-red", "rarity": "epic", "is_default": False},
    {"name": "Ночное небо", "slug": "night-sky", "css_class": "bg-msg-night-sky", "rarity": "epic", "is_default": False},
    {"name": "Мистический фиолетовый", "slug": "mystic-purple", "css_class": "bg-msg-mystic-purple", "rarity": "rare", "is_default": False},
    {"name": "Стальной серый", "slug": "steel-gray", "css_class": "bg-msg-steel-gray", "rarity": "common", "is_default": True},
    {"name": "Песчаная буря", "slug": "sandstorm", "css_class": "bg-msg-sandstorm", "rarity": "rare", "is_default": False},
    {"name": "Океанская глубина", "slug": "ocean-deep", "css_class": "bg-msg-ocean-deep", "rarity": "epic", "is_default": False},
    {"name": "Северное сияние", "slug": "aurora", "css_class": "bg-msg-aurora", "rarity": "legendary", "is_default": False},
    {"name": "Космическая пыль", "slug": "cosmic", "css_class": "bg-msg-cosmic", "rarity": "legendary", "is_default": False},
    {"name": "Тёмная пустота", "slug": "void-dark", "css_class": "bg-msg-void-dark", "rarity": "epic", "is_default": False},
]

PERMISSIONS = [
    ("cosmetics", "read", "Просмотр каталога косметики"),
    ("cosmetics", "create", "Создание косметики и выдача пользователям"),
    ("cosmetics", "update", "Редактирование косметики"),
    ("cosmetics", "delete", "Удаление косметики"),
]

# Role assignments: moderator (3) and editor (2) get cosmetics:read
# Admin (role_id=4) gets all permissions automatically
ROLE_ACTIONS = {
    3: ["read"],
    2: ["read"],
}


def upgrade() -> None:
    # 1. Create cosmetic_frames table
    op.create_table(
        'cosmetic_frames',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(50), nullable=False),
        sa.Column('type', sa.String(10), nullable=False, server_default='css'),
        sa.Column('css_class', sa.String(100), nullable=True),
        sa.Column('image_url', sa.String(500), nullable=True),
        sa.Column('rarity', sa.String(20), nullable=False, server_default='common'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_seasonal', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', name='uq_cosmetic_frames_slug'),
    )
    op.create_index('ix_cosmetic_frames_slug', 'cosmetic_frames', ['slug'])
    op.create_index('ix_cosmetic_frames_rarity', 'cosmetic_frames', ['rarity'])

    # 2. Create cosmetic_backgrounds table
    op.create_table(
        'cosmetic_backgrounds',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(50), nullable=False),
        sa.Column('type', sa.String(10), nullable=False, server_default='css'),
        sa.Column('css_class', sa.String(100), nullable=True),
        sa.Column('image_url', sa.String(500), nullable=True),
        sa.Column('rarity', sa.String(20), nullable=False, server_default='common'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', name='uq_cosmetic_backgrounds_slug'),
    )
    op.create_index('ix_cosmetic_backgrounds_slug', 'cosmetic_backgrounds', ['slug'])
    op.create_index('ix_cosmetic_backgrounds_rarity', 'cosmetic_backgrounds', ['rarity'])

    # 3. Create user_unlocked_frames table
    op.create_table(
        'user_unlocked_frames',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('frame_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False, server_default='default'),
        sa.Column('unlocked_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['frame_id'], ['cosmetic_frames.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'frame_id', name='uq_user_frame'),
    )

    # 4. Create user_unlocked_backgrounds table
    op.create_table(
        'user_unlocked_backgrounds',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('background_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False, server_default='default'),
        sa.Column('unlocked_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['background_id'], ['cosmetic_backgrounds.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'background_id', name='uq_user_background'),
    )

    # 5. Add chat_background column to users table
    op.add_column('users', sa.Column('chat_background', sa.String(50), nullable=True))

    # 6. Seed default frames
    frames_table = sa.table(
        'cosmetic_frames',
        sa.column('name', sa.String),
        sa.column('slug', sa.String),
        sa.column('type', sa.String),
        sa.column('css_class', sa.String),
        sa.column('rarity', sa.String),
        sa.column('is_default', sa.Boolean),
        sa.column('is_seasonal', sa.Boolean),
    )
    op.bulk_insert(frames_table, [
        {
            "name": f["name"],
            "slug": f["slug"],
            "type": "css",
            "css_class": f["css_class"],
            "rarity": f["rarity"],
            "is_default": f["is_default"],
            "is_seasonal": False,
        }
        for f in DEFAULT_FRAMES
    ])

    # 7. Seed default backgrounds
    backgrounds_table = sa.table(
        'cosmetic_backgrounds',
        sa.column('name', sa.String),
        sa.column('slug', sa.String),
        sa.column('type', sa.String),
        sa.column('css_class', sa.String),
        sa.column('rarity', sa.String),
        sa.column('is_default', sa.Boolean),
    )
    op.bulk_insert(backgrounds_table, [
        {
            "name": b["name"],
            "slug": b["slug"],
            "type": "css",
            "css_class": b["css_class"],
            "rarity": b["rarity"],
            "is_default": b["is_default"],
        }
        for b in DEFAULT_BACKGROUNDS
    ])

    # 8. Add RBAC permissions for cosmetics
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
    # Remove cosmetics permissions
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM permissions WHERE module = 'cosmetics'")
    ).fetchall()
    perm_ids = [r[0] for r in rows]
    if perm_ids:
        ids_str = ",".join(str(pid) for pid in perm_ids)
        op.execute(f"DELETE FROM role_permissions WHERE permission_id IN ({ids_str})")
        op.execute(f"DELETE FROM permissions WHERE id IN ({ids_str})")

    # Drop chat_background column from users
    op.drop_column('users', 'chat_background')

    # Drop tables in reverse order (respect FK constraints)
    op.drop_table('user_unlocked_backgrounds')
    op.drop_table('user_unlocked_frames')
    op.drop_table('cosmetic_backgrounds')
    op.drop_table('cosmetic_frames')
