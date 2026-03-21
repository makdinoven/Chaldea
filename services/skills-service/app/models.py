from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float, TIMESTAMP, UniqueConstraint
from sqlalchemy.sql import func
from database import Base

class Skill(Base):
    """
    Базовая информация о навыке (название, тип и т.д.).
    Пример:
      - "Огненная вспышка"
      - skill_type="Attack"
    """
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    skill_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Attack, Defense, Support, ...
    description: Mapped[str] = mapped_column(Text, nullable=True)  # Общее описание навыка
    class_limitations = Column(String(100), nullable=True)
    race_limitations = Column(String(100), nullable=True)
    subrace_limitations = Column(String(100), nullable=True)
    min_level = Column(Integer, default=1)
    purchase_cost = Column(Integer, default=0)
    skill_image = Column(Text, nullable=True)

    # Ранги навыка
    ranks = relationship("SkillRank", back_populates="skill", cascade="all, delete-orphan")


class SkillRank(Base):
    """
    Конкретные ступени (ранги) в рамках одного навыка.
    Может иметь несколько типов урона (SkillRankDamage) и несколько эффектов (SkillRankEffect).
    """
    __tablename__ = "skill_ranks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)

    # Номер ранга (или уровень навыка)
    rank_name = Column(String(100), nullable=True)
    rank_number: Mapped[int] = mapped_column(Integer, default=1)

    # Возможное ветвление
    left_child_id: Mapped[int] = mapped_column(ForeignKey("skill_ranks.id"), nullable=True)
    right_child_id: Mapped[int] = mapped_column(ForeignKey("skill_ranks.id"), nullable=True)

    # Общие поля (стоимость, кулдаун, требования)
    cost_energy: Mapped[int] = mapped_column(Integer, default=0)
    cost_mana: Mapped[int] = mapped_column(Integer, default=0)
    cooldown: Mapped[int] = mapped_column(Integer, default=0)
    level_requirement: Mapped[int] = mapped_column(Integer, default=1)
    upgrade_cost: Mapped[int] = mapped_column(Integer, default=0)  # Стоимость прокачки (active_experience)

    # Ограничения по классу/рассе/подрассе
    class_limitations: Mapped[str] = mapped_column(String(100), nullable=True)   # "1,2,3"
    race_limitations: Mapped[str] = mapped_column(String(100), nullable=True)
    subrace_limitations: Mapped[str] = mapped_column(String(100), nullable=True)

    # Доп. описание ранга
    rank_description: Mapped[str] = mapped_column(Text, nullable=True)

    # ORM связи
    skill = relationship("Skill", back_populates="ranks", foreign_keys=[skill_id])
    left_child = relationship("SkillRank", foreign_keys=[left_child_id], remote_side=[id])
    right_child = relationship("SkillRank", foreign_keys=[right_child_id], remote_side=[id])

    # Записи урона (несколько типов)
    damage_entries = relationship("SkillRankDamage", back_populates="skill_rank",
                                  cascade="all, delete-orphan")

    # Эффекты, которые накладывает этот ранг
    effects = relationship("SkillRankEffect", back_populates="skill_rank",
                           cascade="all, delete-orphan")
    rank_image = Column(Text, nullable=True)

class SkillRankDamage(Base):
    """
    Описание урона, который наносит SkillRank (несколько типов урона).
    Пример: damage_type="fire", amount=10 => 10 огненного урона
    """
    __tablename__ = "skill_rank_damage"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_rank_id: Mapped[int] = mapped_column(ForeignKey("skill_ranks.id"), nullable=False)

    damage_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "physical", "fire", "ice", etc.
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    weapon_slot = Column(String(20), default="main_weapon")

    target_side: Mapped[str] = mapped_column(String(10), nullable=False, default="self")
    chance: Mapped[int] = mapped_column(Integer, default=100)

    skill_rank = relationship("SkillRank", back_populates="damage_entries")


class SkillRankEffect(Base):
    """
    Описание баф/дебаф эффектов, которые накладывает SkillRank.
    Может быть несколько таких записей, каждая со своей логикой, которую battle-service применяет.
    """
    __tablename__ = "skill_rank_effects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    skill_rank_id: Mapped[int] = mapped_column(ForeignKey("skill_ranks.id"), nullable=False)

    # На кого накладываем: "self" или "enemy"
    target_side: Mapped[str] = mapped_column(String(10), default="self")
    # Уникальное имя эффекта: "Bleeding", "Poison", "fire_damage_up", ...
    effect_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Шанс срабатывания эффекта (0..100)
    chance: Mapped[int] = mapped_column(Integer, default=100)

    # Длительность в ходах
    duration: Mapped[int] = mapped_column(Integer, default=1)

    # Величина (в процентах или в единицах), зависит от логики
    magnitude: Mapped[float] = mapped_column(Float, default=0.0)

    # (Опционально) К какому атрибуту относится изменение. Может быть "res_fire" или ""
    attribute_key: Mapped[str] = mapped_column(String(50), nullable=True)

    skill_rank = relationship("SkillRank", back_populates="effects")


class CharacterSkill(Base):
    """
    Связь: какой персонаж (character_id) владеет каким конкретным ранговым навыком (skill_rank_id).
    """
    __tablename__ = "character_skills"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    character_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    skill_rank_id: Mapped[int] = mapped_column(ForeignKey("skill_ranks.id"), nullable=False)

    # Для логики "один ранг" или "несколько" — зависит от геймдизайна
    skill_rank = relationship("SkillRank")


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
