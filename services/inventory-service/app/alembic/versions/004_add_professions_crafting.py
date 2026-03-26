"""Add professions, recipes, and crafting tables. Extend items.item_type with blueprint.

Revision ID: 004_add_professions_crafting
Revises: 003_add_trade_tables
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = '004_add_professions_crafting'
down_revision = '003_add_trade_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1) Create professions table
    if 'professions' not in existing_tables:
        op.create_table(
            'professions',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(100), nullable=False, unique=True),
            sa.Column('slug', sa.String(50), nullable=False, unique=True),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('icon', sa.String(255), nullable=True),
            sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        )

    # 2) Create profession_ranks table
    if 'profession_ranks' not in existing_tables:
        op.create_table(
            'profession_ranks',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('profession_id', sa.Integer, nullable=False),
            sa.Column('rank_number', sa.Integer, nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('required_experience', sa.Integer, nullable=False, server_default='0'),
            sa.Column('icon', sa.String(255), nullable=True),
            sa.ForeignKeyConstraint(['profession_id'], ['professions.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('profession_id', 'rank_number', name='uq_profession_rank'),
        )

    # 3) Create recipes table
    if 'recipes' not in existing_tables:
        op.create_table(
            'recipes',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(200), nullable=False, unique=True),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('profession_id', sa.Integer, nullable=False),
            sa.Column('required_rank', sa.Integer, nullable=False, server_default='1'),
            sa.Column('result_item_id', sa.Integer, nullable=False),
            sa.Column('result_quantity', sa.Integer, nullable=False, server_default='1'),
            sa.Column('rarity', sa.String(20), nullable=False, server_default="'common'"),
            sa.Column('icon', sa.String(255), nullable=True),
            sa.Column('is_blueprint_recipe', sa.Boolean, nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default='1'),
            sa.Column('auto_learn_rank', sa.Integer, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['profession_id'], ['professions.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['result_item_id'], ['items.id'], ondelete='CASCADE'),
        )

    # 4) Create recipe_ingredients table
    if 'recipe_ingredients' not in existing_tables:
        op.create_table(
            'recipe_ingredients',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('recipe_id', sa.Integer, nullable=False),
            sa.Column('item_id', sa.Integer, nullable=False),
            sa.Column('quantity', sa.Integer, nullable=False, server_default='1'),
            sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='CASCADE'),
        )

    # 5) Create character_professions table
    if 'character_professions' not in existing_tables:
        op.create_table(
            'character_professions',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer, nullable=False),
            sa.Column('profession_id', sa.Integer, nullable=False),
            sa.Column('current_rank', sa.Integer, nullable=False, server_default='1'),
            sa.Column('experience', sa.Integer, nullable=False, server_default='0'),
            sa.Column('chosen_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['profession_id'], ['professions.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('character_id', name='uq_character_profession'),
        )

    # 6) Create character_recipes table
    if 'character_recipes' not in existing_tables:
        op.create_table(
            'character_recipes',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('character_id', sa.Integer, nullable=False),
            sa.Column('recipe_id', sa.Integer, nullable=False),
            sa.Column('learned_at', sa.DateTime, nullable=False,
                       server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('character_id', 'recipe_id', name='uq_character_recipe'),
        )

    # 7) Extend items.item_type ENUM with 'blueprint'
    op.execute(
        "ALTER TABLE items MODIFY COLUMN item_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield',"
        "'blueprint') "
        "NOT NULL"
    )

    # 8) Add blueprint_recipe_id nullable column to items
    columns = [c['name'] for c in inspector.get_columns('items')]
    if 'blueprint_recipe_id' not in columns:
        op.add_column('items', sa.Column('blueprint_recipe_id', sa.Integer, nullable=True))
        op.create_foreign_key(
            'fk_items_blueprint_recipe', 'items',
            'recipes', ['blueprint_recipe_id'], ['id'],
            ondelete='SET NULL'
        )

    # 9) Seed 6 professions
    op.execute(
        "INSERT INTO professions (name, slug, description, icon, sort_order) VALUES "
        "('Кузнец', 'blacksmith', 'Крафт снаряжения (броня, оружие) по чертежам, ремонт-комплекты, заточка', NULL, 1),"
        "('Алхимик', 'alchemist', 'Крафт зелий, ядов, трансмутация материалов', NULL, 2),"
        "('Повар', 'cook', 'Крафт еды с бонусами, восстановление выносливости', NULL, 3),"
        "('Зачарователь', 'enchanter', 'Создание рун, вставка и извлечение рун, слияние рун', NULL, 4),"
        "('Ювелир', 'jeweler', 'Крафт украшений, огранка камней, переплавка', NULL, 5),"
        "('Книжник', 'scholar', 'Книги опыта, магическое оружие, свитки заклинаний', NULL, 6)"
    )

    # 10) Seed 3 ranks per profession (18 rows total)
    # Get profession IDs
    rows = conn.execute(sa.text("SELECT id, slug FROM professions ORDER BY sort_order")).fetchall()
    for prof_id, slug in rows:
        op.execute(
            f"INSERT INTO profession_ranks (profession_id, rank_number, name, description, required_experience) VALUES "
            f"({prof_id}, 1, 'Ученик', 'Начальный ранг профессии', 0),"
            f"({prof_id}, 2, 'Подмастерье', 'Средний ранг профессии', 500),"
            f"({prof_id}, 3, 'Мастер', 'Высший ранг профессии', 2000)"
        )


def downgrade() -> None:
    # Drop FK and column from items
    op.drop_constraint('fk_items_blueprint_recipe', 'items', type_='foreignkey')
    op.drop_column('items', 'blueprint_recipe_id')

    # Revert items.item_type ENUM (remove 'blueprint')
    op.execute(
        "ALTER TABLE items MODIFY COLUMN item_type "
        "ENUM('head','body','cloak','belt','ring','necklace','bracelet',"
        "'main_weapon','consumable','additional_weapons','resource','scroll','misc','shield') "
        "NOT NULL"
    )

    # Drop tables in reverse dependency order
    op.drop_table('character_recipes')
    op.drop_table('character_professions')
    op.drop_table('recipe_ingredients')
    op.drop_table('recipes')
    op.drop_table('profession_ranks')
    op.drop_table('professions')
