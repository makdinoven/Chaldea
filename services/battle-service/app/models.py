# battle-service/app/models.py
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Column, Integer, DateTime, ForeignKey, Enum as SQLEnum, String
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from database import Base


class BattleStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    finished = "finished"
    forfeit = "forfeit"


class Battle(Base):
    __tablename__ = "battles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    status: Mapped[BattleStatus] = mapped_column(
        SQLEnum(BattleStatus), default=BattleStatus.in_progress
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    participants = relationship(
        "BattleParticipant",
        back_populates="battle",
        cascade="all, delete-orphan",
    )
    turns = relationship(
        "BattleTurn",
        back_populates="battle",
        cascade="all, delete-orphan",
    )


class BattleParticipant(Base):
    """
    Один персонаж-участник в бою. team — любое целое (0 или 1 для 1×1,
    0,1,2… для FFA).
    """
    __tablename__ = "battle_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    battle_id: Mapped[int] = mapped_column(
        ForeignKey("battles.id"), index=True
    )
    character_id: Mapped[int] = mapped_column(index=True)
    team: Mapped[int] = mapped_column(Integer, default=0)

    battle = relationship("Battle", back_populates="participants")


class BattleTurn(Base):
    """
    Действие одного участника за ход.
    В 1×1 turn_number идёт 0,1,2…; actor_id — FK на battle_participants.id
    """
    __tablename__ = "battle_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    battle_id: Mapped[int] = mapped_column(
        ForeignKey("battles.id"), index=True
    )
    actor_participant_id: Mapped[int] = mapped_column(
        ForeignKey("battle_participants.id"), index=True
    )

    turn_number: Mapped[int] = mapped_column(Integer)

    attack_rank_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    defense_rank_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    support_rank_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    deadline_at: Mapped[datetime] = mapped_column(DateTime)

    battle = relationship("Battle", back_populates="turns")
