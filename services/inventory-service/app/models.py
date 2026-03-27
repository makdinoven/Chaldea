from sqlalchemy import Column, Integer, String, Enum, Boolean, DECIMAL, Text, ForeignKey, Float, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

# Определяем модель для хранения инвентаря персонажа
class Items(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    image = Column(String(255), nullable=True)
    item_level = Column(Integer, nullable=False,default=0)
    item_type = Column(Enum(
        'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet', 'main_weapon',
        'consumable','additional_weapons', 'resource', 'scroll', 'misc', 'shield',
        'blueprint', 'recipe', 'gem', 'rune'
    ), nullable=False)
    blueprint_recipe_id = Column(Integer, ForeignKey('recipes.id', ondelete='SET NULL'), nullable=True)
    item_rarity = Column(Enum(
        'common', 'rare', 'epic', 'legendary', 'mythical', 'divine', 'demonic'
    ), nullable=False)
    price = Column(Integer, nullable=True)
    max_stack_size = Column(Integer, default=1)
    is_unique = Column(Boolean, nullable=False, default=False)
    description = Column(Text)

    whetstone_level = Column(Integer, nullable=True, default=None)  # 1=common(25%), 2=rare(50%), 3=legendary(75%)

    essence_result_item_id = Column(Integer, ForeignKey('items.id', ondelete='SET NULL'), nullable=True)

    socket_count = Column(Integer, default=0)  # Количество слотов для камней/рун

    identify_level = Column(Integer, nullable=True, default=None)  # Scroll identify level: 1=common/rare, 2=epic/mythical, 3=legendary/divine/demonic

    max_durability = Column(Integer, default=0, server_default="0")  # 0 means no durability system
    repair_power = Column(Integer, nullable=True)  # For repair kits: 25/50/75/100 (% of max_durability restored)

    fast_slot_bonus = Column(Integer, default=0)  # Сколько дополнительных быстрых слотов даёт предмет

    # Buff fields (for consumable buff items like XP books)
    buff_type = Column(String(50), nullable=True)
    buff_value = Column(Float, nullable=True)
    buff_duration_minutes = Column(Integer, nullable=True)

    armor_subclass = Column(
        Enum('cloth', 'light_armor', 'medium_armor', 'heavy_armor', name="armor_subclass_enum"),
        nullable=True,
        comment="Подкласс брони: Ткань, Легкая, Средняя или Тяжелая"
    )

    weapon_subclass = Column(
        Enum(
            # Варианты для воинов:
            'one_handed_weapon', 'two_handed_weapon', 'maces', 'axes', 'battle_axes', 'hammers', 'polearms', 'scythes',
            # Варианты для плутов:
            'daggers', 'twin_daggers', 'short_swords', 'rapiers', 'spears', 'bows', 'firearms', 'knuckledusters',
            # Варианты для магов:
            'one_handed_staffs', 'two_handed_staffs', 'grimoires', 'catalysts', 'spheres', 'wands', 'amulets',
            'magic_weapon',
            name="weapon_subclass_enum"
        ),
        nullable=True,
        comment="Подкласс оружия, в зависимости от типа персонажа (воины, плуты, маги)"
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
    essence_result_item = relationship("Items", foreign_keys=[essence_result_item_id], remote_side=[id])

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


# Таблица слотов экипировки
class EquipmentSlot(Base):
    __tablename__ = 'equipment_slots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    slot_type = Column(Enum(
        'head', 'body', 'cloak', 'belt', 'ring',
        'necklace', 'bracelet', 'main_weapon', 'additional_weapons', 'shield',
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
    is_blueprint_recipe = Column(Boolean, nullable=False, default=False)
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

