"""
Shared factories for the FEAT-165 tests (refining, conversions, auto-learn,
sharpening groups, sockets).

Rows are created through the real ORM models with the real column names
(`resource_subcategory`, `whetstone_group`, `item_conversions.*`) so a renamed
column breaks these tests instead of being silently ignored.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import text

import models
from auth_http import UserRead

OWNER = UserRead(id=1, username="owner", role="user", permissions=[])
OTHER_USER_ID = 999

# Default professions: (id, slug, name). Ids are stable for the tests.
PROFESSIONS = [
    (1, "blacksmith", "Кузнец"),
    (2, "alchemist", "Алхимик"),
    (3, "cook", "Повар"),
    (4, "enchanter", "Зачарователь"),
    (5, "jeweler", "Ювелир"),
    (6, "scholar", "Мистик"),
]
PROF_ID = {slug: pid for pid, slug, _ in PROFESSIONS}

# rank_number -> (name, required_experience)
RANKS = {1: ("Ученик", 0), 2: ("Подмастерье", 20), 3: ("Мастер", 100)}


def ensure_characters(db, rows=((1, OWNER.id, "Hero"), (2, OTHER_USER_ID, "Stranger"))):
    """(Re)create the shared `characters` table used by ownership checks."""
    db.execute(text("DROP TABLE IF EXISTS characters"))
    db.execute(text(
        """CREATE TABLE characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'TestChar',
            user_id INTEGER NOT NULL,
            current_location_id INTEGER DEFAULT 1,
            currency_balance INTEGER DEFAULT 0
        )"""
    ))
    for cid, uid, name in rows:
        db.execute(
            text("INSERT INTO characters (id, name, user_id) VALUES (:cid, :name, :uid)"),
            {"cid": cid, "name": name, "uid": uid},
        )
    db.commit()


def seed_professions(db, ranks=RANKS, inactive=()):
    for pid, slug, name in PROFESSIONS:
        db.add(models.Profession(
            id=pid, name=name, slug=slug, description="Test",
            sort_order=pid, is_active=slug not in inactive,
        ))
    db.flush()
    for pid, _, _ in PROFESSIONS:
        for number, (rank_name, xp) in ranks.items():
            db.add(models.ProfessionRank(
                profession_id=pid, rank_number=number,
                name=rank_name, required_experience=xp,
            ))
    db.commit()


def assign_profession(db, character_id, slug, rank=1, experience=0):
    cp = models.CharacterProfession(
        character_id=character_id, profession_id=PROF_ID[slug],
        current_rank=rank, experience=experience, chosen_at=datetime.utcnow(),
    )
    db.add(cp)
    db.commit()
    return cp


def make_item(db, item_id, name, item_type="resource", rarity="common",
              subcategory=None, max_stack=99, **kwargs):
    item = models.Items(
        id=item_id, name=name, item_level=1, item_type=item_type,
        item_rarity=rarity, max_stack_size=max_stack, is_unique=False,
        resource_subcategory=subcategory, **kwargs,
    )
    db.add(item)
    db.commit()
    return item


def make_stone(db, item_id, name, group, level=1):
    return make_item(
        db, item_id, name, "resource", subcategory="whetstone",
        whetstone_level=level, whetstone_group=group,
    )


def add_stack(db, character_id, item_id, quantity=1, **kwargs):
    row = models.CharacterInventory(
        character_id=character_id, item_id=item_id, quantity=quantity, **kwargs,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_conversion(db, source_item_id, slug, result_item_id,
                   source_quantity=1, result_quantity=1):
    row = models.ItemConversion(
        source_item_id=source_item_id, profession_id=PROF_ID[slug],
        source_quantity=source_quantity, result_item_id=result_item_id,
        result_quantity=result_quantity,
    )
    db.add(row)
    db.commit()
    return row


def make_recipe(db, recipe_id, slug, result_item_id, auto_learn_rank=None,
                required_rank=1, is_active=True, name=None):
    recipe = models.Recipe(
        id=recipe_id, name=name or f"Рецепт {recipe_id}",
        profession_id=PROF_ID[slug], required_rank=required_rank,
        result_item_id=result_item_id, result_quantity=1, rarity="common",
        is_active=is_active, auto_learn_rank=auto_learn_rank,
    )
    db.add(recipe)
    db.commit()
    return recipe


# --- DB read-back helpers ---------------------------------------------------

def owned_quantity(db, character_id, item_id):
    db.expire_all()
    rows = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id,
    ).all()
    return sum(r.quantity for r in rows)


def profession_state(db, character_id):
    db.expire_all()
    cp = db.query(models.CharacterProfession).filter(
        models.CharacterProfession.character_id == character_id
    ).first()
    return cp.current_rank, cp.experience


def learned_recipe_ids(db, character_id):
    db.expire_all()
    return sorted(
        r.recipe_id for r in db.query(models.CharacterRecipe)
        .filter(models.CharacterRecipe.character_id == character_id).all()
    )


def conversion_rows(db, source_item_id=None):
    db.expire_all()
    query = db.query(models.ItemConversion)
    if source_item_id is not None:
        query = query.filter(models.ItemConversion.source_item_id == source_item_id)
    return sorted(
        (
            (r.source_item_id, r.profession_id, r.source_quantity,
             r.result_item_id, r.result_quantity)
            for r in query.all()
        ),
    )


# --- locks --------------------------------------------------------------------

def put_in_battle(db, character_id):
    db.execute(text("INSERT INTO battles (id, status) VALUES (77, 'in_progress')"))
    db.execute(text(
        "INSERT INTO battle_participants (id, battle_id, character_id) VALUES (77, 77, :cid)"
    ), {"cid": character_id})
    db.commit()


def start_gathering(db, character_id):
    now = datetime.utcnow()
    db.execute(text(
        "INSERT INTO gathering_sessions "
        "(character_id, node_id, status, started_at, complete_at, stamina_paid) "
        "VALUES (:cid, 1, 'active', :sa, :ca, 5)"
    ), {
        "cid": character_id,
        "sa": now.strftime("%Y-%m-%d %H:%M:%S"),
        "ca": (now + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
    })
    db.commit()


def socketed(row):
    return json.loads(row.socketed_gems) if row.socketed_gems else []
