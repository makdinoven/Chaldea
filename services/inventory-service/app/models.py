from sqlalchemy import Column, Integer, String, Enum, Boolean, DECIMAL, Text, ForeignKey, Float, DateTime, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

# FEAT-165 enum values. Migration 022 keeps its own copies; a test compares them.
RESOURCE_SUBCATEGORIES = (
    # raw materials
    'ore', 'herb', 'wood', 'ingredient', 'trophy',
    # refined products
    'ingot', 'magic_dust', 'essence', 'reagent', 'material',
    # profession consumables
    'whetstone', 'repair_kit',
)
WHETSTONE_GROUPS = ('weapon_armor', 'cloak_belt', 'jewelry')
GATHERING_CATEGORIES = ('ore', 'herb', 'wood', 'ingredient')

# Определяем модель для хранения инвентаря персонажа
class Items(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    image = Column(String(255), nullable=True)
    # Uncropped original; `image` holds the square icon cut from it
    full_image = Column(String(255), nullable=True)
    item_level = Column(Integer, nullable=False,default=0)
    item_type = Column(Enum(
        'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet', 'weapon',
        'consumable', 'resource', 'scroll', 'misc',
        'recipe', 'gem', 'rune', 'gathering_tool'
    ), nullable=False)
    # Links a recipe item (item_type='recipe') to its recipe. Name kept for
    # compatibility (photo-service reads it); blueprints were removed in FEAT-165.
    blueprint_recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='SET NULL'), nullable=True)
    item_rarity = Column(Enum(
        'common', 'rare', 'epic', 'legendary', 'mythical', 'divine', 'demonic'
    ), nullable=False)
    price = Column(Integer, nullable=True)
    max_stack_size = Column(Integer, default=1)
    is_unique = Column(Boolean, nullable=False, default=False)
    description = Column(Text)

    whetstone_level = Column(Integer, nullable=True, default=None)  # 1=common(25%), 2=rare(50%), 3=legendary(75%)
    # FEAT-165: which gear a sharpening stone fits (see crud.SHARPEN_GROUP_TYPES)
    whetstone_group = Column(
        Enum(*WHETSTONE_GROUPS, name='whetstone_group_enum'),
        nullable=True,
    )
    # FEAT-165: resource subcategory, only for item_type='resource'; NULL = «Прочее»
    resource_subcategory = Column(
        Enum(*RESOURCE_SUBCATEGORIES, name='resource_subcategory_enum'),
        nullable=True,
        index=True,
    )

    socket_count = Column(Integer, default=0)  # Количество слотов для камней/рун

    identify_level = Column(Integer, nullable=True, default=None)  # Scroll identify level: 1=common/rare, 2=epic/mythical, 3=legendary/divine/demonic

    max_durability = Column(Integer, default=0, server_default="0")  # 0 means no durability system
    repair_power = Column(Integer, nullable=True)  # For repair kits: 25/50/75/100 (% of max_durability restored)

    # Gathering tool fields (only meaningful when item_type='gathering_tool')
    tool_category = Column(
        Enum('pickaxe', 'sickle', 'axe', name='tool_category_enum'),
        nullable=True,
    )
    gather_double_chance_bonus = Column(Float, nullable=False, default=0.0, server_default="0")
    gather_speed_bonus_pct = Column(Float, nullable=False, default=0.0, server_default="0")
    gather_stamina_bonus_pct = Column(Float, nullable=False, default=0.0, server_default="0")

    fast_slot_bonus = Column(Integer, default=0)  # Сколько дополнительных быстрых слотов даёт предмет

    # Buff fields (for consumable buff items like XP books)
    buff_type = Column(String(50), nullable=True)
    buff_value = Column(Float, nullable=True)
    buff_duration_minutes = Column(Integer, nullable=True)

    # FEAT-164: food — eaten via /eat-food, gives "Сытость" for 24h
    is_food = Column(Boolean, nullable=False, default=False, server_default="0")

    # FEAT-168: how a consumable is used in battle.
    # NULL / 'instant' — applied immediately; 'weapon_coating' — poison on the
    # weapon (see coating_* below); 'cleanse' — removes effects.
    # VARCHAR and not ENUM on purpose: an ENUM change locks `items` (FEAT-165).
    consumable_action = Column(String(20), nullable=True)
    coating_turns = Column(Integer, nullable=True)
    coating_bonus_damage = Column(Float, nullable=True)

    armor_subclass = Column(
        Enum('cloth', 'light_armor', 'medium_armor', 'heavy_armor', name="armor_subclass_enum"),
        nullable=True,
        comment="Подкласс брони: Ткань, Легкая, Средняя или Тяжелая"
    )

    weapon_subclass = Column(
        Enum(
            # Одноручное
            'sword', 'hatchet', 'mace', 'sabre', 'dagger', 'espada', 'tanto', 'war_pick',
            # Полуторное
            'bastard_sword', 'axe', 'katana', 'broadsword', 'rapier', 'war_hammer',
            # Двуручное
            'zweihander', 'maul', 'battle_axe', 'scythe', 'nodachi',
            # Древковое
            'halberd', 'glaive', 'pike', 'spear', 'naginata',
            # Стрелковое
            'bow', 'pistol', 'musket',
            # Щиты
            'buckler', 'targe', 'tower_shield',
            # Другое
            'lute', 'knuckledusters',
            # Магическое
            'staff', 'grimoire', 'amulet', 'rod', 'magic_weapon', 'catalyst', 'wand',
            name="weapon_subclass_enum"
        ),
        nullable=True,
        comment="Вид оружия; категория (одноручное, полуторное, ...) выводится из вида"
    )

    primary_damage_type = Column(
        Enum('physical','catting','crushing','piercing', 'magic', 'fire', 'ice','watering','electricity','wind','sainting','damning', name="primary_damage_type_enum"),
        nullable=True,
        comment="Основной тип урона, применимо для оружия (main_weapon, additional_weapons)"
    )

    # Модификаторы характеристик
    strength_modifier = Column(Integer, default=0)
    agility_modifier = Column(Integer, default=0)
    intelligence_modifier = Column(Integer, default=0)
    endurance_modifier = Column(Integer, default=0)
    health_modifier = Column(Integer, default=0)
    energy_modifier = Column(Integer, default=0)
    mana_modifier = Column(Integer, default=0)
    stamina_modifier = Column(Integer, default=0)
    charisma_modifier = Column(Integer, default=0)
    luck_modifier = Column(Integer, default=0)
    damage_modifier = Column(Integer, default=0)
    dodge_modifier = Column(Integer, default=0)

    res_effects_modifier = Column(Float, default=0.0)
    res_physical_modifier = Column(Float, default=0.0)
    res_catting_modifier = Column(Float, default=0.0)
    res_crushing_modifier = Column(Float, default=0.0)
    res_piercing_modifier = Column(Float, default=0.0)
    res_magic_modifier = Column(Float, default=0.0)
    res_fire_modifier = Column(Float, default=0.0)
    res_ice_modifier = Column(Float, default=0.0)
    res_watering_modifier = Column(Float, default=0.0)
    res_electricity_modifier = Column(Float, default=0.0)
    res_wind_modifier = Column(Float, default=0.0)
    res_sainting_modifier = Column(Float, default=0.0)
    res_damning_modifier = Column(Float, default=0.0)
    critical_hit_chance_modifier = Column(Float, default=0.0)
    critical_damage_modifier = Column(Float, default=0.0)

    health_recovery = Column(Integer, default=0)
    energy_recovery = Column(Integer, default=0)
    mana_recovery = Column(Integer, default=0)
    stamina_recovery = Column(Integer, default=0)

    vul_effects_modifier = Column(Float, default=0.0)
    vul_physical_modifier = Column(Float, default=0.0)
    vul_catting_modifier = Column(Float, default=0.0)
    vul_crushing_modifier = Column(Float, default=0.0)
    vul_piercing_modifier = Column(Float, default=0.0)
    vul_magic_modifier = Column(Float, default=0.0)
    vul_fire_modifier = Column(Float, default=0.0)
    vul_ice_modifier = Column(Float, default=0.0)
    vul_watering_modifier = Column(Float, default=0.0)
    vul_electricity_modifier = Column(Float, default=0.0)
    vul_sainting_modifier = Column(Float, default=0.0)
    vul_wind_modifier = Column(Float, default=0.0)
    vul_damning_modifier = Column(Float, default=0.0)

    # Связи
    inventories = relationship("CharacterInventory", back_populates="item")
    equipment_slots = relationship("EquipmentSlot", back_populates="item")
    blueprint_recipe = relationship("Recipe", foreign_keys=[blueprint_recipe_id], back_populates="blueprint_items")
    # FEAT-168: battle effect payload of a consumable/scroll
    effects = relationship(
        "ItemEffect", back_populates="item",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    damage_entries = relationship(
        "ItemDamageEntry", back_populates="item",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    # FEAT-168 #6: XP книги — сколько и какого опыта ускоряет предмет
    xp_buffs = relationship(
        "ItemXpBuff", back_populates="item",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class ItemXpBuff(Base):
    """FEAT-168 #6: one XP-acceleration row of an item.

    Replaces the single `items.buff_type/buff_value/buff_duration_minutes`
    triple with a list, so one book can accelerate several XP sources at once.
    The legacy columns stay in place and are still honoured for items that have
    no rows here (see `crud.get_item_xp_buffs`).
    """
    __tablename__ = "item_xp_buffs"
    __table_args__ = (
        UniqueConstraint("item_id", "buff_type", name="uq_item_xp_buff_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)

    buff_type = Column(String(50), nullable=False)
    # Доля: 0.25 = +25 %
    value = Column(Float, nullable=False, default=0.0, server_default="0")
    duration_minutes = Column(Integer, nullable=False, default=60, server_default="60")

    item = relationship("Items", back_populates="xp_buffs")


class ItemEffect(Base):
    """FEAT-168: one battle effect row of an item.

    Row shape mirrors skills-service `skill_perk_effects` so battle-service can
    hand it to `buffs.apply_new_effects` without any translation.
    """
    __tablename__ = "item_effects"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)

    target_side = Column(String(10), nullable=False, default="self", server_default="self")
    effect_name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    chance = Column(Integer, nullable=False, default=100, server_default="100")
    duration = Column(Integer, nullable=False, default=1, server_default="1")
    magnitude = Column(Float, nullable=False, default=0.0, server_default="0")
    attribute_key = Column(String(50), nullable=True)

    item = relationship("Items", back_populates="effects")


class ItemDamageEntry(Base):
    """FEAT-168: one damage row of an item (damage scrolls, thrown flasks).

    Row shape mirrors skills-service `skill_perk_damage` so battle-service can
    feed it to `battle_engine.compute_damage_with_rolls` unchanged.
    """
    __tablename__ = "item_damage_entries"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)

    damage_type = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False, default=0.0, server_default="0")
    description = Column(Text, nullable=True)
    # Scrolls default to unarmed math — no equipped weapon is involved.
    weapon_slot = Column(String(20), nullable=False, default="no_weapon", server_default="no_weapon")
    target_side = Column(String(10), nullable=False, default="enemy", server_default="enemy")
    chance = Column(Integer, nullable=False, default=100, server_default="100")
    aoe_shape = Column(String(12), nullable=False, default="single", server_default="single")
    aoe_falloff = Column(Integer, nullable=False, default=50, server_default="50")
    aoe_max_targets = Column(Integer, nullable=False, default=3, server_default="3")

    item = relationship("Items", back_populates="damage_entries")

# Определяем модель для хранения инвентаря персонажа
class CharacterInventory(Base):
    __tablename__ = "character_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    quantity = Column(Integer, default=1)
    is_identified = Column(Boolean, default=True, server_default="1")
    enhancement_points_spent = Column(Integer, default=0, server_default="0")
    enhancement_bonuses = Column(Text, nullable=True)  # JSON string: {"strength_modifier": 3, "damage_modifier": 5}
    socketed_gems = Column(Text, nullable=True)  # JSON string: [42, null, 15] — item IDs of gems in sockets
    current_durability = Column(Integer, nullable=True)  # NULL = full, 0 = broken

    item = relationship("Items", back_populates="inventories")


class EquipmentRule(Base):
    """What a class (subclass_key NULL) or subclass may wear. See equipment_rules.py."""
    __tablename__ = "equipment_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # "class:<id>" for the class row, the subclass key otherwise — one row per scope
    scope_key = Column(String(60), nullable=False, unique=True)
    class_id = Column(Integer, nullable=False, index=True)
    subclass_key = Column(String(50), nullable=True)
    armor_classes = Column(Text, nullable=False, default="[]")  # JSON list of armor classes
    main_hand = Column(Text, nullable=False, default="[]")  # JSON list of "category:x" / "kind:y"
    off_hand = Column(Text, nullable=False, default="[]")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


# Таблица слотов экипировки
class EquipmentSlot(Base):
    __tablename__ = 'equipment_slots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    slot_type = Column(Enum(
        'head', 'body', 'cloak', 'belt', 'ring',
        'necklace', 'bracelet', 'main_weapon', 'additional_weapons',
        'fast_slot_1', 'fast_slot_2', 'fast_slot_3', 'fast_slot_4',
    'fast_slot_5', 'fast_slot_6', 'fast_slot_7', 'fast_slot_8',
    'fast_slot_9', 'fast_slot_10'
    ), nullable=False)

    item_id = Column(Integer, ForeignKey('items.id'), nullable=True)
    item = relationship("Items", back_populates="equipment_slots")

    is_enabled = Column(Boolean, default=True)
    enhancement_points_spent = Column(Integer, default=0, server_default="0")
    enhancement_bonuses = Column(Text, nullable=True)  # JSON string: {"strength_modifier": 3, "damage_modifier": 5}
    socketed_gems = Column(Text, nullable=True)  # JSON string: [42, null, 15] — item IDs of gems in sockets
    current_durability = Column(Integer, nullable=True)  # NULL = full, 0 = broken


# Trade system models
class TradeOffer(Base):
    __tablename__ = "trade_offers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    initiator_character_id = Column(Integer, nullable=False)
    target_character_id = Column(Integer, nullable=False)
    location_id = Column(Integer, nullable=False)
    initiator_gold = Column(Integer, nullable=False, default=0)
    target_gold = Column(Integer, nullable=False, default=0)
    initiator_confirmed = Column(Boolean, nullable=False, default=False)
    target_confirmed = Column(Boolean, nullable=False, default=False)
    status = Column(
        Enum('pending', 'negotiating', 'completed', 'cancelled', 'expired', name='trade_status_enum'),
        nullable=False,
        default='pending'
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship("TradeOfferItem", back_populates="trade_offer", cascade="all, delete-orphan")


class TradeOfferItem(Base):
    __tablename__ = "trade_offer_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_offer_id = Column(Integer, ForeignKey('trade_offers.id', ondelete='CASCADE'), nullable=False)
    character_id = Column(Integer, nullable=False)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    trade_offer = relationship("TradeOffer", back_populates="items")
    item = relationship("Items")


# Profession system models
class Profession(Base):
    __tablename__ = "professions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    slug = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    icon = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    ranks = relationship("ProfessionRank", back_populates="profession", cascade="all, delete-orphan")
    recipes = relationship("Recipe", back_populates="profession", cascade="all, delete-orphan")
    character_professions = relationship("CharacterProfession", back_populates="profession", cascade="all, delete-orphan")


class ProfessionRank(Base):
    __tablename__ = "profession_ranks"
    __table_args__ = (
        UniqueConstraint('profession_id', 'rank_number', name='uq_profession_rank'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    profession_id = Column(Integer, ForeignKey('professions.id', ondelete='CASCADE'), nullable=False)
    rank_number = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    required_experience = Column(Integer, nullable=False, default=0)
    icon = Column(String(255), nullable=True)

    profession = relationship("Profession", back_populates="ranks")


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    profession_id = Column(Integer, ForeignKey('professions.id', ondelete='CASCADE'), nullable=False)
    required_rank = Column(Integer, nullable=False, default=1)
    result_item_id = Column(Integer, ForeignKey('items.id', ondelete='CASCADE'), nullable=False)
    result_quantity = Column(Integer, nullable=False, default=1)
    rarity = Column(String(20), nullable=False, default='common')
    xp_reward = Column(Integer, nullable=True)
    icon = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    auto_learn_rank = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    profession = relationship("Profession", back_populates="recipes")
    result_item = relationship("Items", foreign_keys=[result_item_id])
    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    blueprint_items = relationship("Items", foreign_keys="[Items.blueprint_recipe_id]", back_populates="blueprint_recipe")
    character_recipes = relationship("CharacterRecipe", back_populates="recipe", cascade="all, delete-orphan")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    item_id = Column(Integer, ForeignKey('items.id', ondelete='CASCADE'), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    recipe = relationship("Recipe", back_populates="ingredients")
    item = relationship("Items")


class CharacterProfession(Base):
    __tablename__ = "character_professions"
    __table_args__ = (
        UniqueConstraint('character_id', name='uq_character_profession'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    profession_id = Column(Integer, ForeignKey('professions.id', ondelete='CASCADE'), nullable=False)
    current_rank = Column(Integer, nullable=False, default=1)
    experience = Column(Integer, nullable=False, default=0)
    chosen_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    profession = relationship("Profession", back_populates="character_professions")


class CharacterRecipe(Base):
    __tablename__ = "character_recipes"
    __table_args__ = (
        UniqueConstraint('character_id', 'recipe_id', name='uq_character_recipe'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='CASCADE'), nullable=False)
    learned_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    recipe = relationship("Recipe", back_populates="character_recipes")


class ActiveBuff(Base):
    __tablename__ = "active_buffs"
    __table_args__ = (
        UniqueConstraint('character_id', 'buff_type', name='uq_character_buff_type'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    buff_type = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    source_item_name = Column(String(200), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# Auction system models
class AuctionListing(Base):
    __tablename__ = "auction_listings"
    __table_args__ = (
        Index('ix_auction_listings_status_expires', 'status', 'expires_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    seller_character_id = Column(Integer, nullable=False, index=True)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    enhancement_data = Column(Text, nullable=True)  # JSON string
    start_price = Column(Integer, nullable=False)
    buyout_price = Column(Integer, nullable=True)
    current_bid = Column(Integer, nullable=False, default=0)
    current_bidder_id = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default='active', index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)

    item = relationship("Items")
    bids = relationship("AuctionBid", back_populates="listing", cascade="all, delete-orphan")


class AuctionBid(Base):
    __tablename__ = "auction_bids"

    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(Integer, ForeignKey('auction_listings.id', ondelete='CASCADE'), nullable=False, index=True)
    bidder_character_id = Column(Integer, nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default='active')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    listing = relationship("AuctionListing", back_populates="bids")


class AuctionStorage(Base):
    __tablename__ = "auction_storage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False, index=True)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=True)
    quantity = Column(Integer, nullable=False, default=0)
    enhancement_data = Column(Text, nullable=True)  # JSON string
    gold_amount = Column(Integer, nullable=False, default=0)
    source = Column(String(20), nullable=False)
    listing_id = Column(Integer, ForeignKey('auction_listings.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    item = relationship("Items")


class ItemConversion(Base):
    """FEAT-165 refining config: what a profession gets from one raw item."""
    __tablename__ = "item_conversions"
    __table_args__ = (
        UniqueConstraint('source_item_id', 'profession_id', name='uq_item_conversion'),
        CheckConstraint(
            'source_quantity BETWEEN 1 AND 100 AND result_quantity BETWEEN 1 AND 100',
            name='ck_item_conv_qty',
        ),
        Index('ix_item_conversions_result', 'result_item_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_item_id = Column(Integer, ForeignKey('items.id', ondelete='CASCADE', name='fk_item_conv_source'), nullable=False)
    profession_id = Column(Integer, ForeignKey('professions.id', ondelete='CASCADE', name='fk_item_conv_prof'), nullable=False)
    source_quantity = Column(Integer, nullable=False, default=1)
    result_item_id = Column(Integer, ForeignKey('items.id', ondelete='CASCADE', name='fk_item_conv_result'), nullable=False)
    result_quantity = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    source_item = relationship("Items", foreign_keys=[source_item_id])
    result_item = relationship("Items", foreign_keys=[result_item_id])
    profession = relationship("Profession")


# Gathering system models
class GatheringSkill(Base):
    __tablename__ = "gathering_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(50), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    category = Column(
        Enum(*GATHERING_CATEGORIES, name='gathering_skill_category_enum'),
        nullable=False,
        unique=True,
    )
    description = Column(Text, nullable=True)
    icon = Column(String(255), nullable=True)
    max_rank = Column(Integer, nullable=False, default=5, server_default='5')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    ranks = relationship("GatheringSkillRank", back_populates="skill", cascade="all, delete-orphan")
    character_progress = relationship("CharacterGatheringSkill", back_populates="skill", cascade="all, delete-orphan")


class GatheringSkillRank(Base):
    __tablename__ = "gathering_skill_ranks"
    __table_args__ = (
        UniqueConstraint('skill_id', 'rank_number', name='uq_gathering_skill_rank'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(Integer, ForeignKey('gathering_skills.id', ondelete='CASCADE'), nullable=False)
    rank_number = Column(Integer, nullable=False)
    required_experience = Column(Integer, nullable=False, default=0, server_default='0')
    double_chance_bonus = Column(Float, nullable=False, default=0.0, server_default='0')
    speed_bonus_pct = Column(Float, nullable=False, default=0.0, server_default='0')
    stamina_bonus_pct = Column(Float, nullable=False, default=0.0, server_default='0')

    skill = relationship("GatheringSkill", back_populates="ranks")


class CharacterGatheringSkill(Base):
    __tablename__ = "character_gathering_skills"
    __table_args__ = (
        UniqueConstraint('character_id', 'skill_id', name='uq_character_gathering_skill'),
        Index('ix_character_gathering_skills_character', 'character_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # No FK on character_id — owned by character-service (cross-service shared-DB convention)
    character_id = Column(Integer, nullable=False)
    skill_id = Column(Integer, ForeignKey('gathering_skills.id', ondelete='CASCADE'), nullable=False)
    current_rank = Column(Integer, nullable=False, default=1, server_default='1')
    experience = Column(Integer, nullable=False, default=0, server_default='0')
    experience_total = Column(Integer, nullable=False, default=0, server_default='0')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    skill = relationship("GatheringSkill", back_populates="character_progress")

