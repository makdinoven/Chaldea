"""Initial migration: create all dungeon tables

Revision ID: 001
Revises:
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- dungeons ---
    op.create_table(
        "dungeons",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("lore_text", sa.Text, nullable=True),
        sa.Column(
            "stability_type",
            sa.Enum("static", "unstable", "chaotic", name="dungeon_stability_type"),
            nullable=False,
            server_default="static",
        ),
        sa.Column(
            "danger_level",
            sa.Enum("safe", "deadly", name="dungeon_danger_level"),
            nullable=False,
            server_default="safe",
        ),
        sa.Column("location_id", sa.BigInteger, nullable=False),
        sa.Column("recommended_level", sa.Integer, nullable=True, server_default="1"),
        sa.Column("recommended_party_size", sa.Integer, nullable=True, server_default="1"),
        sa.Column("cooldown_hours", sa.Integer, nullable=False, server_default="24"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("mob_multiplier", sa.Float, nullable=False, server_default=sa.text("1.0")),
        sa.Column("loot_multiplier", sa.Float, nullable=False, server_default=sa.text("1.0")),
        sa.Column("stamina_multiplier", sa.Float, nullable=False, server_default=sa.text("1.0")),
        sa.Column("difficulty_modifier", sa.Float, nullable=False, server_default=sa.text("1.0")),
        sa.Column("disable_rest_rooms", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("disable_merchants", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("mana_core_chance", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("mana_core_item_id", sa.BigInteger, nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_dungeons_location", "dungeons", ["location_id"])
    op.create_index("idx_dungeons_active", "dungeons", ["is_active"])

    # --- dungeon_rooms ---
    op.create_table(
        "dungeon_rooms",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("dungeon_id", sa.BigInteger, sa.ForeignKey("dungeons.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "room_type",
            sa.Enum(
                "battle", "boss", "treasure", "trap", "event",
                "rest", "merchant", "fork", "teleport", "deadend",
                name="dungeon_room_type",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_entrance", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("is_boss_room", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("is_mana_core_room", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("room_config", sa.JSON, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now()),
    )
    op.create_index("idx_rooms_dungeon", "dungeon_rooms", ["dungeon_id"])
    op.create_index("idx_rooms_type", "dungeon_rooms", ["room_type"])

    # --- dungeon_corridors ---
    op.create_table(
        "dungeon_corridors",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("dungeon_id", sa.BigInteger, sa.ForeignKey("dungeons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_room_id", sa.BigInteger, sa.ForeignKey("dungeon_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_room_id", sa.BigInteger, sa.ForeignKey("dungeon_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stamina_cost", sa.Integer, nullable=False, server_default="5"),
        sa.Column("is_bidirectional", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("random_battle_chance", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("random_battle_mob_ids", sa.JSON, nullable=True),
        sa.Column("trap_chance", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("trap_config", sa.JSON, nullable=True),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now()),
    )
    op.create_index("idx_corridors_dungeon", "dungeon_corridors", ["dungeon_id"])
    op.create_index("idx_corridors_from", "dungeon_corridors", ["from_room_id"])
    op.create_index("idx_corridors_to", "dungeon_corridors", ["to_room_id"])
    op.create_unique_constraint("uq_corridor", "dungeon_corridors", ["from_room_id", "to_room_id"])

    # --- dungeon_sessions ---
    op.create_table(
        "dungeon_sessions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("dungeon_id", sa.BigInteger, sa.ForeignKey("dungeons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("leader_character_id", sa.BigInteger, nullable=False),
        sa.Column(
            "status",
            sa.Enum("forming", "active", "completed", "escaped", "wiped", name="dungeon_session_status"),
            nullable=False,
            server_default="forming",
        ),
        sa.Column("current_room_id", sa.BigInteger, sa.ForeignKey("dungeon_rooms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP, nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP, nullable=True),
        sa.Column("cooldown_until", sa.TIMESTAMP, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now()),
    )
    op.create_index("idx_sessions_dungeon", "dungeon_sessions", ["dungeon_id"])
    op.create_index("idx_sessions_status", "dungeon_sessions", ["status"])
    op.create_index("idx_sessions_leader", "dungeon_sessions", ["leader_character_id"])

    # --- dungeon_session_members ---
    op.create_table(
        "dungeon_session_members",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("dungeon_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column(
            "status",
            sa.Enum("alive", "dead", "disconnected", name="dungeon_member_status"),
            nullable=False,
            server_default="alive",
        ),
        sa.Column("joined_at", sa.TIMESTAMP, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_session_member", "dungeon_session_members", ["session_id", "character_id"])
    op.create_index("idx_members_session", "dungeon_session_members", ["session_id"])
    op.create_index("idx_members_character", "dungeon_session_members", ["character_id"])

    # --- dungeon_session_inventory ---
    op.create_table(
        "dungeon_session_inventory",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("dungeon_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.BigInteger, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("source_description", sa.String(255), nullable=True),
    )
    op.create_index("idx_inv_session", "dungeon_session_inventory", ["session_id"])

    # --- dungeon_room_visits ---
    op.create_table(
        "dungeon_room_visits",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("dungeon_id", sa.BigInteger, sa.ForeignKey("dungeons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.BigInteger, nullable=False),
        sa.Column("room_id", sa.BigInteger, sa.ForeignKey("dungeon_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_visited_at", sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column("last_visited_at", sa.TIMESTAMP, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("visit_count", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_unique_constraint("uq_visit", "dungeon_room_visits", ["dungeon_id", "character_id", "room_id"])
    op.create_index("idx_visits_char_dungeon", "dungeon_room_visits", ["character_id", "dungeon_id"])

    # --- dungeon_room_state ---
    op.create_table(
        "dungeon_room_state",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("dungeon_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("room_id", sa.BigInteger, sa.ForeignKey("dungeon_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_cleared", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("loot_collected", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("event_choice_index", sa.Integer, nullable=True),
        sa.Column("extra_data", sa.JSON, nullable=True),
    )
    op.create_unique_constraint("uq_room_state", "dungeon_room_state", ["session_id", "room_id"])
    op.create_index("idx_room_state_session", "dungeon_room_state", ["session_id"])


def downgrade() -> None:
    op.drop_table("dungeon_room_state")
    op.drop_table("dungeon_room_visits")
    op.drop_table("dungeon_session_inventory")
    op.drop_table("dungeon_session_members")
    op.drop_table("dungeon_sessions")
    op.drop_table("dungeon_corridors")
    op.drop_table("dungeon_rooms")
    op.drop_table("dungeons")
