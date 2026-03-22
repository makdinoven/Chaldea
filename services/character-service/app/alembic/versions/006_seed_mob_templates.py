"""Seed 8 mob templates with base_attributes.

Revision ID: 006_seed_mob_templates
Revises: 005_add_mob_tables
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa
import json

revision = '006_seed_mob_templates'
down_revision = '005_add_mob_tables'
branch_labels = None
depends_on = None

# fmt: off
MOB_TEMPLATES = [
    {
        "name": "Дикий Волк",
        "description": "Свирепый хищник, обитающий в лесах и на равнинах. Нападает стаями.",
        "tier": "normal",
        "level": 2,
        "id_race": 6,       # Бистмен
        "id_subrace": 13,   # Зверолюд
        "id_class": 1,      # Воин
        "sex": "genderless",
        "base_attributes": json.dumps({
            "strength": 15, "agility": 20, "intelligence": 3,
            "endurance": 10, "health": 60, "energy": 30,
            "mana": 0, "stamina": 25, "charisma": 0, "luck": 5
        }),
        "xp_reward": 30,
        "gold_reward": 5,
        "respawn_enabled": True,
        "respawn_seconds": 300,
    },
    {
        "name": "Лесной Паук",
        "description": "Ядовитый паук, плетущий паутину среди деревьев. Атакует из засады.",
        "tier": "normal",
        "level": 3,
        "id_race": 6,       # Бистмен
        "id_subrace": 13,   # Зверолюд
        "id_class": 2,      # Плут
        "sex": "genderless",
        "base_attributes": json.dumps({
            "strength": 10, "agility": 25, "intelligence": 5,
            "endurance": 12, "health": 70, "energy": 35,
            "mana": 0, "stamina": 30, "charisma": 0, "luck": 8
        }),
        "xp_reward": 40,
        "gold_reward": 8,
        "respawn_enabled": True,
        "respawn_seconds": 300,
    },
    {
        "name": "Гоблин-разведчик",
        "description": "Хитрый гоблин, вооружённый кинжалом. Предпочитает внезапные атаки.",
        "tier": "normal",
        "level": 4,
        "id_race": 7,       # Урук
        "id_subrace": 16,   # Темный урук
        "id_class": 2,      # Плут
        "sex": "male",
        "base_attributes": json.dumps({
            "strength": 14, "agility": 22, "intelligence": 8,
            "endurance": 15, "health": 85, "energy": 40,
            "mana": 5, "stamina": 35, "charisma": 2, "luck": 10
        }),
        "xp_reward": 55,
        "gold_reward": 12,
        "respawn_enabled": True,
        "respawn_seconds": 600,
    },
    {
        "name": "Скелет-воин",
        "description": "Нежить, поднятая тёмной магией. Сражается мечом без страха и боли.",
        "tier": "normal",
        "level": 5,
        "id_race": 1,       # Человек (undead human)
        "id_subrace": 1,    # Норд
        "id_class": 1,      # Воин
        "sex": "genderless",
        "base_attributes": json.dumps({
            "strength": 20, "agility": 12, "intelligence": 3,
            "endurance": 22, "health": 110, "energy": 45,
            "mana": 0, "stamina": 40, "charisma": 0, "luck": 5
        }),
        "xp_reward": 70,
        "gold_reward": 15,
        "respawn_enabled": True,
        "respawn_seconds": 600,
    },
    {
        "name": "Болотный Тролль",
        "description": "Огромный тролль, обитающий в болотах. Обладает регенерацией и грубой силой.",
        "tier": "elite",
        "level": 8,
        "id_race": 7,       # Урук
        "id_subrace": 15,   # Северные
        "id_class": 1,      # Воин
        "sex": "male",
        "base_attributes": json.dumps({
            "strength": 40, "agility": 10, "intelligence": 5,
            "endurance": 35, "health": 250, "energy": 60,
            "mana": 0, "stamina": 50, "charisma": 0, "luck": 8
        }),
        "xp_reward": 150,
        "gold_reward": 40,
        "respawn_enabled": True,
        "respawn_seconds": 1800,
    },
    {
        "name": "Тёмный Маг",
        "description": "Могущественный колдун, владеющий разрушительной магией тьмы.",
        "tier": "elite",
        "level": 10,
        "id_race": 5,       # Демон
        "id_subrace": 12,   # Альб
        "id_class": 3,      # Маг
        "sex": "male",
        "base_attributes": json.dumps({
            "strength": 8, "agility": 18, "intelligence": 45,
            "endurance": 15, "health": 200, "energy": 50,
            "mana": 80, "stamina": 30, "charisma": 5, "luck": 12
        }),
        "xp_reward": 200,
        "gold_reward": 60,
        "respawn_enabled": True,
        "respawn_seconds": 1800,
    },
    {
        "name": "Огненный Элементаль",
        "description": "Существо из чистого пламени. Сжигает всё на своём пути.",
        "tier": "elite",
        "level": 12,
        "id_race": 5,       # Демон
        "id_subrace": 11,   # Левиаан
        "id_class": 3,      # Маг
        "sex": "genderless",
        "base_attributes": json.dumps({
            "strength": 25, "agility": 22, "intelligence": 40,
            "endurance": 28, "health": 300, "energy": 60,
            "mana": 90, "stamina": 40, "charisma": 0, "luck": 15
        }),
        "xp_reward": 280,
        "gold_reward": 80,
        "respawn_enabled": True,
        "respawn_seconds": 2700,
    },
    {
        "name": "Древний Дракон",
        "description": "Легендарное существо невероятной мощи. Победить его — подвиг, достойный героя.",
        "tier": "boss",
        "level": 20,
        "id_race": 3,       # Драконид
        "id_subrace": 7,    # Равагарт
        "id_class": 1,      # Воин
        "sex": "male",
        "base_attributes": json.dumps({
            "strength": 80, "agility": 35, "intelligence": 50,
            "endurance": 70, "health": 1500, "energy": 150,
            "mana": 100, "stamina": 120, "charisma": 10, "luck": 25
        }),
        "xp_reward": 1000,
        "gold_reward": 500,
        "respawn_enabled": False,
        "respawn_seconds": None,
    },
]
# fmt: on


def upgrade() -> None:
    conn = op.get_bind()

    for mob in MOB_TEMPLATES:
        # Idempotent: skip if a template with this name already exists
        exists = conn.execute(
            sa.text("SELECT 1 FROM mob_templates WHERE name = :name"),
            {"name": mob["name"]},
        ).fetchone()
        if exists:
            continue

        conn.execute(
            sa.text(
                "INSERT INTO mob_templates "
                "(name, description, tier, level, id_race, id_subrace, id_class, "
                "sex, base_attributes, xp_reward, gold_reward, respawn_enabled, respawn_seconds) "
                "VALUES (:name, :description, :tier, :level, :id_race, :id_subrace, :id_class, "
                ":sex, :base_attributes, :xp_reward, :gold_reward, :respawn_enabled, :respawn_seconds)"
            ),
            mob,
        )


def downgrade() -> None:
    conn = op.get_bind()
    names = [m["name"] for m in MOB_TEMPLATES]
    for name in names:
        conn.execute(
            sa.text("DELETE FROM mob_templates WHERE name = :name"),
            {"name": name},
        )
