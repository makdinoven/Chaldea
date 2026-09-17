"""FEAT-165 profession rework: refining, resource subcategories, stone groups.

Upgrade:
- guard: refuses to run while items with item_type='blueprint' exist;
- items.item_type loses 'blueprint'; recipes.is_blueprint_recipe is dropped
  (single-use blueprints are gone; items.blueprint_recipe_id stays, it links
  recipe items and photo-service reads it);
- items.essence_result_item_id (+ its FK) is dropped (essence extraction removed);
- items.resource_subcategory (+ index) and items.whetstone_group are added;
  existing whetstones become 'whetstone' / 'weapon_armor', repair kits become
  'repair_kit'. Legacy crystals, transmuted resources, jeweler junk and elemental
  essences are NOT touched (NULL = «Прочее»; the admin cleans them up by hand);
- new table item_conversions (refining config: source item x profession);
- gathering_skills.category gains 'ingredient' + skill 'foraging' with 5 ranks
  (copied from 'herbalism' when present, else the 016 defaults);
- profession 'scholar' is renamed to «Мистик» (by slug); seed descriptions are
  refreshed only where they still equal the 004 seed text;
- report only: belts that still have sockets or socketed runes.

Downgrade restores the old schema. Data loss on downgrade (documented):
resource subcategories, stone groups, the refining config and all 'foraging'
progress are deleted; essence_result_item_id comes back empty.

Revision ID: 022_profession_rework
Revises: 021_add_item_is_food
Create Date: 2026-09-18

"""
import logging

from alembic import op
import sqlalchemy as sa

revision = '022_profession_rework'
down_revision = '021_add_item_is_food'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

# Kept in sync with models.py (a test compares them)
ITEM_TYPES_OLD = [
    'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet', 'weapon',
    'consumable', 'resource', 'scroll', 'misc',
    'blueprint', 'recipe', 'gem', 'rune', 'gathering_tool',
]
ITEM_TYPES_NEW = [t for t in ITEM_TYPES_OLD if t != 'blueprint']

RESOURCE_SUBCATEGORIES = [
    'ore', 'herb', 'wood', 'ingredient', 'trophy',
    'ingot', 'magic_dust', 'essence', 'reagent', 'material',
    'whetstone', 'repair_kit',
]
WHETSTONE_GROUPS = ['weapon_armor', 'cloak_belt', 'jewelry']

GATHERING_CATEGORIES_OLD = ['ore', 'herb', 'wood']
GATHERING_CATEGORIES_NEW = GATHERING_CATEGORIES_OLD + ['ingredient']

FORAGING_SLUG = 'foraging'
FORAGING_NAME = 'Собирательство'
FORAGING_DESCRIPTION = 'Навык сбора ингредиентов'
FORAGING_CATEGORY = 'ingredient'
TEMPLATE_SKILL_SLUG = 'herbalism'
# rank_number, required_experience, double_chance_bonus, speed_bonus_pct, stamina_bonus_pct (016 defaults)
DEFAULT_GATHERING_RANKS = [
    (1, 0, 0.0, 0.0, 0.0),
    (2, 10, 4.0, 4.0, 4.0),
    (3, 25, 8.0, 8.0, 8.0),
    (4, 50, 12.0, 12.0, 12.0),
    (5, 100, 20.0, 20.0, 20.0),
]

ESSENCE_FK_NAME = 'fk_items_essence_result_item_id'
SUBCATEGORY_INDEX = 'ix_items_resource_subcategory'

SCHOLAR_SLUG = 'scholar'
SCHOLAR_OLD_NAME = 'Книжник'
SCHOLAR_NEW_NAME = 'Мистик'

# slug -> (004 seed description, FEAT-165 description)
PROFESSION_DESCRIPTIONS = {
    'blacksmith': (
        'Крафт снаряжения (броня, оружие) по чертежам, ремонт-комплекты, заточка',
        'Оружие, броня и шлемы; точильные камни для оружия, брони и шлема; ремкомплекты; '
        'переработка руды в слитки',
    ),
    'alchemist': (
        'Крафт зелий, ядов, трансмутация материалов',
        'Зелья и пояса; переработка алхимических реагентов в эссенции',
    ),
    'cook': (
        'Крафт еды с бонусами, восстановление выносливости',
        'Еда; переработка ингредиентов в алхимические реагенты',
    ),
    'enchanter': (
        'Создание рун, вставка и извлечение рун, слияние рун',
        'Руны и оружие магов; камни чар для плаща и пояса; вставка и извлечение рун',
    ),
    'jeweler': (
        'Крафт украшений, огранка камней, переплавка',
        'Кольца, ожерелья, браслеты и огранки; гравировальные резцы для украшений; '
        'переработка руды в магическую пыль',
    ),
}
SCHOLAR_OLD_DESCRIPTION = 'Книги опыта, магическое оружие, свитки заклинаний'
SCHOLAR_NEW_DESCRIPTION = 'Книги, свитки, тканевая броня и шлемы; переработка трофеев в материалы'


def _enum(values):
    return "ENUM(" + ",".join(f"'{v}'" for v in values) + ")"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set:
    return {c['name'] for c in _inspector().get_columns(table)}


def _table_exists(table: str) -> bool:
    return _inspector().has_table(table)


def _index_names(table: str) -> set:
    return {i['name'] for i in _inspector().get_indexes(table)}


def _scalar(sql: str, **params):
    return op.get_bind().execute(sa.text(sql), params).scalar()


def _rows(sql: str, **params):
    return op.get_bind().execute(sa.text(sql), params).fetchall()


def _exec(sql: str, **params):
    return op.get_bind().execute(sa.text(sql), params)


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def _guard_no_blueprints() -> None:
    rows = _rows("SELECT id FROM items WHERE item_type = 'blueprint' ORDER BY id")
    if rows:
        ids = ", ".join(str(r[0]) for r in rows)
        raise RuntimeError(
            f"Migration 022: {len(rows)} blueprint item(s) still exist (ids {ids}). "
            "Delete or convert them first."
        )


def _drop_essence_column() -> None:
    if 'essence_result_item_id' not in _columns('items'):
        return
    for fk in _inspector().get_foreign_keys('items'):
        if fk.get('constrained_columns') == ['essence_result_item_id']:
            op.drop_constraint(fk['name'], 'items', type_='foreignkey')
    op.drop_column('items', 'essence_result_item_id')


def _add_subcategory_columns() -> None:
    cols = _columns('items')
    if 'resource_subcategory' not in cols:
        op.execute(
            "ALTER TABLE items ADD COLUMN resource_subcategory "
            + _enum(RESOURCE_SUBCATEGORIES) + " NULL"
        )
    if 'whetstone_group' not in cols:
        op.execute(
            "ALTER TABLE items ADD COLUMN whetstone_group "
            + _enum(WHETSTONE_GROUPS) + " NULL"
        )
    if SUBCATEGORY_INDEX not in _index_names('items'):
        op.create_index(SUBCATEGORY_INDEX, 'items', ['resource_subcategory'])


def _backfill_subcategories() -> None:
    whetstones = _exec(
        "UPDATE items SET resource_subcategory = 'whetstone', whetstone_group = 'weapon_armor' "
        "WHERE whetstone_level IS NOT NULL AND item_type = 'resource' "
        "AND resource_subcategory IS NULL"
    ).rowcount
    kits = _exec(
        "UPDATE items SET resource_subcategory = 'repair_kit' "
        "WHERE repair_power IS NOT NULL AND item_type = 'resource' "
        "AND resource_subcategory IS NULL"
    ).rowcount
    logger.info("FEAT-165: %s whetstone(s) and %s repair kit(s) got a subcategory", whetstones, kits)

    odd = _rows(
        "SELECT id, name, item_type FROM items "
        "WHERE (whetstone_level IS NOT NULL OR repair_power IS NOT NULL) "
        "AND item_type <> 'resource'"
    )
    for row in odd:
        logger.warning(
            "FEAT-165: item id=%s name=%r type=%s has whetstone_level/repair_power "
            "but is not a resource — left unchanged",
            row[0], row[1], row[2],
        )


def _create_item_conversions() -> None:
    if _table_exists('item_conversions'):
        return
    op.execute(
        """
        CREATE TABLE item_conversions (
          id INT AUTO_INCREMENT PRIMARY KEY,
          source_item_id INT NOT NULL,
          profession_id INT NOT NULL,
          source_quantity INT NOT NULL DEFAULT 1,
          result_item_id INT NOT NULL,
          result_quantity INT NOT NULL DEFAULT 1,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          CONSTRAINT uq_item_conversion UNIQUE (source_item_id, profession_id),
          CONSTRAINT fk_item_conv_source FOREIGN KEY (source_item_id)
            REFERENCES items(id) ON DELETE CASCADE,
          CONSTRAINT fk_item_conv_result FOREIGN KEY (result_item_id)
            REFERENCES items(id) ON DELETE CASCADE,
          CONSTRAINT fk_item_conv_prof FOREIGN KEY (profession_id)
            REFERENCES professions(id) ON DELETE CASCADE,
          CONSTRAINT ck_item_conv_qty CHECK (
            source_quantity BETWEEN 1 AND 100 AND result_quantity BETWEEN 1 AND 100
          )
        )
        """
    )
    op.create_index('ix_item_conversions_result', 'item_conversions', ['result_item_id'])


def _add_foraging_skill() -> None:
    op.execute(
        "ALTER TABLE gathering_skills MODIFY COLUMN category "
        + _enum(GATHERING_CATEGORIES_NEW) + " NOT NULL"
    )
    skill_id = _scalar("SELECT id FROM gathering_skills WHERE slug = :slug", slug=FORAGING_SLUG)
    if skill_id is None:
        taken = _scalar(
            "SELECT slug FROM gathering_skills WHERE category = :cat", cat=FORAGING_CATEGORY
        )
        if taken is not None:
            raise RuntimeError(
                f"Migration 022: gathering skill {taken!r} already uses category "
                f"{FORAGING_CATEGORY!r}; cannot add {FORAGING_SLUG!r}"
            )
        _exec(
            "INSERT INTO gathering_skills (slug, name, category, description, max_rank) "
            "VALUES (:slug, :name, :cat, :descr, :max_rank)",
            slug=FORAGING_SLUG, name=FORAGING_NAME, cat=FORAGING_CATEGORY,
            descr=FORAGING_DESCRIPTION, max_rank=len(DEFAULT_GATHERING_RANKS),
        )
        skill_id = _scalar("SELECT id FROM gathering_skills WHERE slug = :slug", slug=FORAGING_SLUG)

    if _scalar("SELECT COUNT(*) FROM gathering_skill_ranks WHERE skill_id = :sid", sid=skill_id):
        return

    template = _rows(
        "SELECT r.rank_number, r.required_experience, r.double_chance_bonus, "
        "r.speed_bonus_pct, r.stamina_bonus_pct "
        "FROM gathering_skill_ranks r JOIN gathering_skills s ON s.id = r.skill_id "
        "WHERE s.slug = :slug ORDER BY r.rank_number",
        slug=TEMPLATE_SKILL_SLUG,
    )
    ranks = [tuple(r) for r in template] or DEFAULT_GATHERING_RANKS
    for rn, req_xp, dc, sp, st in ranks:
        _exec(
            "INSERT INTO gathering_skill_ranks "
            "(skill_id, rank_number, required_experience, double_chance_bonus, "
            " speed_bonus_pct, stamina_bonus_pct) "
            "VALUES (:sid, :rn, :req, :dc, :sp, :st)",
            sid=skill_id, rn=rn, req=req_xp, dc=dc, sp=sp, st=st,
        )
    logger.info(
        "FEAT-165: skill %r got %d rank(s) (%s)", FORAGING_SLUG, len(ranks),
        f"copied from {TEMPLATE_SKILL_SLUG!r}" if template else "016 defaults",
    )


def _rename_scholar_to_mystic() -> None:
    """Rename by slug whatever the current name is (the name is unique)."""
    prof_id = _scalar("SELECT id FROM professions WHERE slug = :slug", slug=SCHOLAR_SLUG)
    if prof_id is None:
        logger.warning("FEAT-165: profession %r not found; nothing to rename", SCHOLAR_SLUG)
        return
    clash = _scalar(
        "SELECT id FROM professions WHERE name = :name AND id <> :id",
        name=SCHOLAR_NEW_NAME, id=prof_id,
    )
    if clash is not None:
        logger.warning(
            "FEAT-165: profession id=%s is already named %r; %r not renamed",
            clash, SCHOLAR_NEW_NAME, SCHOLAR_SLUG,
        )
        return
    _exec(
        "UPDATE professions SET name = :name, description = :descr WHERE id = :id",
        name=SCHOLAR_NEW_NAME, descr=SCHOLAR_NEW_DESCRIPTION, id=prof_id,
    )


def _rename_mystic_to_scholar() -> None:
    if _scalar("SELECT COUNT(*) FROM professions WHERE name = :name", name=SCHOLAR_OLD_NAME):
        logger.warning("FEAT-165 downgrade: %r already exists; %r not renamed back", SCHOLAR_OLD_NAME, SCHOLAR_SLUG)
        return
    _exec(
        "UPDATE professions SET name = :old_name, description = :old_descr "
        "WHERE slug = :slug AND name = :new_name",
        old_name=SCHOLAR_OLD_NAME, old_descr=SCHOLAR_OLD_DESCRIPTION,
        slug=SCHOLAR_SLUG, new_name=SCHOLAR_NEW_NAME,
    )


def _swap_descriptions(old_index: int, new_index: int) -> None:
    for slug, texts in PROFESSION_DESCRIPTIONS.items():
        _exec(
            "UPDATE professions SET description = :new WHERE slug = :slug AND description = :old",
            new=texts[new_index], old=texts[old_index], slug=slug,
        )


def _report_belt_sockets() -> None:
    belts = _rows(
        "SELECT id, name, socket_count FROM items WHERE item_type = 'belt' AND socket_count > 0"
    )
    for row in belts:
        logger.warning(
            "FEAT-165: belt item id=%s name=%r has socket_count=%s (runes can no longer be inserted)",
            row[0], row[1], row[2],
        )
    for table in ('character_inventory', 'equipment_slots'):
        rows = _rows(
            f"SELECT t.id, t.character_id, t.socketed_gems FROM {table} t "
            "JOIN items i ON i.id = t.item_id "
            "WHERE i.item_type = 'belt' AND t.socketed_gems IS NOT NULL "
            "AND t.socketed_gems NOT IN ('', '[]')"
        )
        for row in rows:
            logger.warning(
                "FEAT-165: %s row id=%s (character %s) holds belt runes %s — extraction still allowed",
                table, row[0], row[1], row[2],
            )


def upgrade() -> None:
    _guard_no_blueprints()

    # 1. Blueprints out
    op.execute("ALTER TABLE items MODIFY COLUMN item_type " + _enum(ITEM_TYPES_NEW) + " NOT NULL")
    if 'is_blueprint_recipe' in _columns('recipes'):
        op.drop_column('recipes', 'is_blueprint_recipe')

    # 2. Essence extraction out
    _drop_essence_column()

    # 3-4. Subcategory + stone group
    _add_subcategory_columns()
    _backfill_subcategories()

    # 5. Refining config
    _create_item_conversions()

    # 6. Ingredient gathering
    _add_foraging_skill()

    # 7. Scholar -> Мистик, seed descriptions
    _rename_scholar_to_mystic()
    _swap_descriptions(old_index=0, new_index=1)

    # 8. Report only
    _report_belt_sockets()


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # 1. Professions
    _swap_descriptions(old_index=1, new_index=0)
    _rename_mystic_to_scholar()

    # 2. Ingredient gathering (cascades ranks and character progress)
    _exec("DELETE FROM gathering_skills WHERE category = :cat", cat=FORAGING_CATEGORY)
    op.execute(
        "ALTER TABLE gathering_skills MODIFY COLUMN category "
        + _enum(GATHERING_CATEGORIES_OLD) + " NOT NULL"
    )

    # 3. Refining config
    if _table_exists('item_conversions'):
        op.drop_table('item_conversions')

    # 4. Subcategory + stone group
    if SUBCATEGORY_INDEX in _index_names('items'):
        op.drop_index(SUBCATEGORY_INDEX, table_name='items')
    cols = _columns('items')
    if 'whetstone_group' in cols:
        op.drop_column('items', 'whetstone_group')
    if 'resource_subcategory' in cols:
        op.drop_column('items', 'resource_subcategory')

    # 5. Essence column (values are lost)
    if 'essence_result_item_id' not in _columns('items'):
        op.add_column('items', sa.Column('essence_result_item_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            ESSENCE_FK_NAME, 'items', 'items',
            ['essence_result_item_id'], ['id'], ondelete='SET NULL',
        )

    # 6. Blueprint recipe flag
    if 'is_blueprint_recipe' not in _columns('recipes'):
        op.add_column(
            'recipes',
            sa.Column('is_blueprint_recipe', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        )

    # 7. Blueprint item type back (original position)
    op.execute("ALTER TABLE items MODIFY COLUMN item_type " + _enum(ITEM_TYPES_OLD) + " NOT NULL")
