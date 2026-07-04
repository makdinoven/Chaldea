import enum

from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, ForeignKey,
    Enum, UniqueConstraint, func,
)

from database import Base

# BigInteger PKs don't autoincrement on SQLite (only "INTEGER PRIMARY KEY" does),
# which breaks the test DB. Use BIGINT on MySQL, INTEGER on SQLite.
_PK = BigInteger().with_variant(Integer, "sqlite")


class MemberStatus(str, enum.Enum):
    invited = "invited"
    accepted = "accepted"


class Party(Base):
    """A persistent squad (FEAT-144). Never auto-disbands; the leader owns it."""
    __tablename__ = "parties"

    id = Column(_PK, primary_key=True, autoincrement=True)
    name = Column(String(60), nullable=False)
    avatar = Column(String(255), nullable=True)            # S3 path of the squad symbol
    leader_character_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())


class PartyMember(Base):
    """Squad membership. `invited` may exist in several parties at once; only
    ONE `accepted` membership per character is allowed (enforced in crud, since
    MySQL has no partial unique index)."""
    __tablename__ = "party_members"

    id = Column(_PK, primary_key=True, autoincrement=True)
    party_id = Column(
        _PK, ForeignKey("parties.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    character_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    is_leader = Column(Boolean, default=False, nullable=False)
    status = Column(Enum(MemberStatus), default=MemberStatus.invited, nullable=False)
    joined_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("party_id", "character_id", name="uq_party_member"),
    )
