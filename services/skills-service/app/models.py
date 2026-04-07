from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import Column, Integer, SmallInteger, String, Text, ForeignKey, Float, TIMESTAMP, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from database import Base

class Skill(Base):
    """
    Базовая информация о навыке (название, тип и т.д.).
    """
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    skill_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    class_limitations = Column(String(100), nullable=True)
    race_limitations = Column(String(100), nullable=True)
    subrace_limitations = Column(String(100), nullable=True)
    min_level = Column(Integer, default=1)
    purchase_cost = Column(Integer, default=0)
    skill_image = Column(Text, nullable=True)

    # Базовые числовые поля навыка (ранее жили на rank-0)
    cost_energy: Mapped[int] = mapped_column(Integer, default=0)
    cost_mana: Mapped[int] = mapped_column(Integer, default=0)
    cooldown: Mapped[int] = mapped_column(Integer, default=0)
    level_requirement: Mapped[int] = mapped_column(Integer, default=1)

    # Базовые damage_entries / effects (на самом навыке)
    base_damage = relationship("SkillBaseDamage", back_populates="skill", cascade="all, delete-orphan")
    base_effects = relationship("SkillBaseEffect", back_populates="skill", cascade="all, delete-orphan")
    perks = relationship("SkillPerk", back_populates="skill", cascade="all, delete-orphan")


class SkillBaseDamage(Base):
    __tablename__ = "skill_base_damage"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)

    damage_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    weapon_slot = Column(String(20), default="main_weapon")
    target_side: Mapped[str] = mapped_column(String(10), nullable=False, default="self")
    chance: Mapped[int] = mapped_column(Integer, default=100)

    skill = relationship("Skill", back_populates="base_damage")


class SkillBaseEffect(Base):
    __tablename__ = "skill_base_effects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)

    target_side: Mapped[str] = mapped_column(String(10), default="self")
    effect_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    chance: Mapped[int] = mapped_column(Integer, default=100)
    duration: Mapped[int] = mapped_column(Integer, default=1)
    magnitude: Mapped[float] = mapped_column(Float, default=0.0)
    attribute_key: Mapped[str] = mapped_column(String(50), nullable=True)

    skill = relationship("Skill", back_populates="base_effects")


class SkillPerk(Base):
    __tablename__ = "skill_perks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    perk_image: Mapped[str] = mapped_column(String(255), nullable=True)

    delta_cost_energy: Mapped[int] = mapped_column(Integer, nullable=True)
    delta_cost_mana: Mapped[int] = mapped_column(Integer, nullable=True)
    delta_cooldown: Mapped[int] = mapped_column(Integer, nullable=True)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    skill = relationship("Skill", back_populates="perks")
    damage_entries = relationship("SkillPerkDamage", back_populates="perk", cascade="all, delete-orphan")
    effects = relationship("SkillPerkEffect", back_populates="perk", cascade="all, delete-orphan")


class SkillPerkDamage(Base):
    __tablename__ = "skill_perk_damage"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_perk_id: Mapped[int] = mapped_column(ForeignKey("skill_perks.id", ondelete="CASCADE"), nullable=False)

    damage_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    weapon_slot = Column(String(20), default="main_weapon")
    target_side: Mapped[str] = mapped_column(String(10), nullable=False, default="self")
    chance: Mapped[int] = mapped_column(Integer, default=100)

    perk = relationship("SkillPerk", back_populates="damage_entries")


class SkillPerkEffect(Base):
    __tablename__ = "skill_perk_effects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_perk_id: Mapped[int] = mapped_column(ForeignKey("skill_perks.id", ondelete="CASCADE"), nullable=False)

    target_side: Mapped[str] = mapped_column(String(10), default="self")
    effect_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    chance: Mapped[int] = mapped_column(Integer, default=100)
    duration: Mapped[int] = mapped_column(Integer, default=1)
    magnitude: Mapped[float] = mapped_column(Float, default=0.0)
    attribute_key: Mapped[str] = mapped_column(String(50), nullable=True)

    perk = relationship("SkillPerk", back_populates="effects")


class CharacterSkill(Base):
    """Связь персонажа с навыком (плоская, без рангов)."""
    __tablename__ = "character_skills"
    __table_args__ = (
        UniqueConstraint("character_id", "skill_id", name="uq_character_skill"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    character_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    reset_available_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    skill = relationship("Skill")
    selected_perks = relationship("CharacterSkillPerk", back_populates="character_skill",
                                  cascade="all, delete-orphan")


class CharacterSkillPerk(Base):
    __tablename__ = "character_skill_perks"
    __table_args__ = (
        UniqueConstraint("character_skill_id", "skill_perk_id", name="uq_char_skill_perk"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    character_skill_id: Mapped[int] = mapped_column(
        ForeignKey("character_skills.id", ondelete="CASCADE"), nullable=False,
    )
    skill_perk_id: Mapped[int] = mapped_column(
        ForeignKey("skill_perks.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    selected_at = Column(DateTime, server_default=func.now())

    character_skill = relationship("CharacterSkill", back_populates="selected_perks")
    perk = relationship("SkillPerk")


# ====================================================================
# (Legacy SkillRank* classes removed in FEAT-125)
# ====================================================================

# ====================================================================
# Class Skill Tree models (FEAT-056)
# ====================================================================

class ClassSkillTree(Base):
    """
    Дерево навыков класса или подкласса.
    tree_type='class' — основное дерево класса (кольца 1-30).
    tree_type='subclass' — дерево подкласса (кольца 30-50).
    """
    __tablename__ = "class_skill_trees"
    __table_args__ = (
        UniqueConstraint("class_id", "tree_type", "subclass_name", name="uq_class_tree_type_subclass"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    tree_type: Mapped[str] = mapped_column(String(20), nullable=False, default="class")
    parent_tree_id: Mapped[int] = mapped_column(ForeignKey("class_skill_trees.id"), nullable=True)
    subclass_name: Mapped[str] = mapped_column(String(100), nullable=True)
    tree_image: Mapped[str] = mapped_column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    nodes = relationship("TreeNode", back_populates="tree", cascade="all, delete-orphan")
    connections = relationship("TreeNodeConnection", back_populates="tree", cascade="all, delete-orphan")
    parent_tree = relationship("ClassSkillTree", remote_side=[id], foreign_keys=[parent_tree_id])


class TreeNode(Base):
    """
    Узел дерева навыков класса/подкласса.
    level_ring — уровень кольца (1, 5, 10, 15, 20, 25, 30 для класса; 30-50 для подкласса).
    node_type — 'regular', 'root', 'subclass_choice'.
    """
    __tablename__ = "tree_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tree_id: Mapped[int] = mapped_column(ForeignKey("class_skill_trees.id"), nullable=False)
    level_ring: Mapped[int] = mapped_column(Integer, nullable=False)
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    node_type: Mapped[str] = mapped_column(String(20), nullable=False, default="regular")
    icon_image: Mapped[str] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    tree = relationship("ClassSkillTree", back_populates="nodes")
    node_skills = relationship("TreeNodeSkill", back_populates="node", cascade="all, delete-orphan")


class TreeNodeConnection(Base):
    """
    Связь между узлами дерева навыков (ребро графа).
    from_node (нижнее кольцо) -> to_node (верхнее кольцо).
    """
    __tablename__ = "tree_node_connections"
    __table_args__ = (
        UniqueConstraint("from_node_id", "to_node_id", name="uq_connection_from_to"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tree_id: Mapped[int] = mapped_column(ForeignKey("class_skill_trees.id"), nullable=False)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), nullable=False)

    # Relationships
    tree = relationship("ClassSkillTree", back_populates="connections")
    from_node = relationship("TreeNode", foreign_keys=[from_node_id])
    to_node = relationship("TreeNode", foreign_keys=[to_node_id])


class TreeNodeSkill(Base):
    """
    Привязка навыка к узлу дерева. Один навык может быть в нескольких узлах разных деревьев.
    """
    __tablename__ = "tree_node_skills"
    __table_args__ = (
        UniqueConstraint("node_id", "skill_id", name="uq_node_skill"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    node = relationship("TreeNode", back_populates="node_skills")
    skill = relationship("Skill")


class CharacterTreeProgress(Base):
    """
    Прогресс персонажа по дереву навыков — какие узлы выбраны.
    Таблица создаётся сейчас для полноты схемы, активно используется в будущих PR.
    """
    __tablename__ = "character_tree_progress"
    __table_args__ = (
        UniqueConstraint("character_id", "node_id", name="uq_character_node"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    character_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tree_id: Mapped[int] = mapped_column(ForeignKey("class_skill_trees.id"), nullable=False)
    node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), nullable=False)
    chosen_at = Column(TIMESTAMP, server_default=func.now())
