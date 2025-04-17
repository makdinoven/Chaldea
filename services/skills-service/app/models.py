from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float
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
