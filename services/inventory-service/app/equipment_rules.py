"""
Class / subclass equipment rules: which armor classes and weapon kinds a
character may wear, per hand.

Scopes:
  - class row (subclass_key NULL) — applies until the character picks a subclass
  - subclass row — applies once the subclass is chosen (the class row is ignored)
No row for the scope = no restrictions.

Rule lists hold tokens: "category:<weapon category>" or "kind:<weapon kind>" for
hands, plain armor class values for armor. Items without a kind / armor class
are never restricted.

Two-handed weapons (categories in TWO_HANDED_CATEGORIES) always take the main
hand and lock the off-hand, regardless of rules.

The character's class lives in `characters` (character-service) and the chosen
subclass in skills-service tree progress; both are read from the shared DB.
"""
import json
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

import models
import schemas

MAIN_HAND = "main_weapon"
OFF_HAND = "additional_weapons"
HAND_SLOTS = (MAIN_HAND, OFF_HAND)

ARMOR_RULE_TYPES = schemas.ARMOR_SUBCLASS_TYPES

TWO_HANDED_CATEGORIES = frozenset({"two_handed", "polearm"})

CATEGORY_TOKEN = "category:"
KIND_TOKEN = "kind:"

ALL_KINDS = frozenset(schemas.WEAPON_KIND_CATEGORY)
ALL_CATEGORIES = frozenset(schemas.WEAPON_KIND_CATEGORY.values())
TWO_HANDED_KINDS = frozenset(
    kind for kind, cat in schemas.WEAPON_KIND_CATEGORY.items() if cat in TWO_HANDED_CATEGORIES
)


def scope_key(class_id: int, subclass_key: Optional[str]) -> str:
    return subclass_key if subclass_key else f"class:{class_id}"


def is_two_handed(item: models.Items) -> bool:
    return item.weapon_subclass in TWO_HANDED_KINDS


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def validate_hand_tokens(tokens: Iterable[str], off_hand: bool) -> List[str]:
    """Normalise and validate hand tokens; raises ValueError with a Russian message."""
    clean: List[str] = []
    for token in tokens:
        if token.startswith(CATEGORY_TOKEN):
            category = token[len(CATEGORY_TOKEN):]
            if category not in ALL_CATEGORIES:
                raise ValueError(f"Неизвестная категория оружия: {category}")
            if off_hand and category in TWO_HANDED_CATEGORIES:
                raise ValueError("Двуручное и древковое оружие нельзя разрешить в доп. руке")
        elif token.startswith(KIND_TOKEN):
            kind = token[len(KIND_TOKEN):]
            if kind not in ALL_KINDS:
                raise ValueError(f"Неизвестный вид оружия: {kind}")
            if off_hand and kind in TWO_HANDED_KINDS:
                raise ValueError("Двуручное и древковое оружие нельзя разрешить в доп. руке")
        else:
            raise ValueError(f"Некорректное правило оружия: {token}")
        if token not in clean:
            clean.append(token)
    return clean


def expand_hand_tokens(tokens: Iterable[str]) -> Set[str]:
    kinds: Set[str] = set()
    for token in tokens:
        if token.startswith(CATEGORY_TOKEN):
            category = token[len(CATEGORY_TOKEN):]
            kinds.update(k for k, c in schemas.WEAPON_KIND_CATEGORY.items() if c == category)
        elif token.startswith(KIND_TOKEN):
            kinds.add(token[len(KIND_TOKEN):])
    return kinds


def _load_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    value = json.loads(raw)
    return [str(v) for v in value] if isinstance(value, list) else []


def rule_to_dict(rule: models.EquipmentRule) -> dict:
    return {
        "scope_key": rule.scope_key,
        "class_id": rule.class_id,
        "subclass_key": rule.subclass_key,
        "armor_classes": _load_list(rule.armor_classes),
        "main_hand": _load_list(rule.main_hand),
        "off_hand": _load_list(rule.off_hand),
        "updated_at": rule.updated_at,
    }


# ---------------------------------------------------------------------------
# Character scope
# ---------------------------------------------------------------------------

@dataclass
class CharacterScope:
    class_id: Optional[int]
    subclass_key: Optional[str]
    is_npc: bool


def load_character_scope(db: Session, character_id: int) -> Optional[CharacterScope]:
    row = db.execute(
        text("SELECT id_class, is_npc FROM characters WHERE id = :cid"),
        {"cid": character_id},
    ).fetchone()
    if row is None:
        return None
    subclass = db.execute(
        text(
            "SELECT tn.subclass_key FROM character_tree_progress ctp "
            "JOIN tree_nodes tn ON tn.id = ctp.node_id "
            "WHERE ctp.character_id = :cid AND tn.node_type = 'subclass_choice' "
            "AND tn.subclass_key IS NOT NULL "
            "ORDER BY ctp.id DESC LIMIT 1"
        ),
        {"cid": character_id},
    ).fetchone()
    return CharacterScope(
        class_id=row[0],
        subclass_key=subclass[0] if subclass else None,
        is_npc=bool(row[1]),
    )


@dataclass
class EffectiveRules:
    """What a character may wear. None in a field = unrestricted."""
    class_id: Optional[int]
    subclass_key: Optional[str]
    armor_classes: Optional[Set[str]]
    main_hand_kinds: Optional[Set[str]]
    off_hand_kinds: Optional[Set[str]]

    @property
    def restricted(self) -> bool:
        return self.armor_classes is not None

    def to_response(self) -> dict:
        def sorted_or_none(values):
            return sorted(values) if values is not None else None

        return {
            "restricted": self.restricted,
            "class_id": self.class_id,
            "subclass_key": self.subclass_key,
            "armor_classes": sorted_or_none(self.armor_classes),
            "main_hand_kinds": sorted_or_none(self.main_hand_kinds),
            "off_hand_kinds": sorted_or_none(self.off_hand_kinds),
            "two_handed_kinds": sorted(TWO_HANDED_KINDS),
        }


UNRESTRICTED = EffectiveRules(None, None, None, None, None)


def rules_for_character(db: Session, character_id: int) -> EffectiveRules:
    # No rules configured anywhere — skip the cross-service lookups entirely
    if db.query(models.EquipmentRule.id).first() is None:
        return UNRESTRICTED

    scope = load_character_scope(db, character_id)
    # NPCs and mobs are dressed by admins without restrictions
    if scope is None or scope.is_npc or scope.class_id is None:
        return UNRESTRICTED

    rule = (
        db.query(models.EquipmentRule)
        .filter(models.EquipmentRule.scope_key == scope_key(scope.class_id, scope.subclass_key))
        .first()
    )
    if rule is None:
        return EffectiveRules(scope.class_id, scope.subclass_key, None, None, None)

    data = rule_to_dict(rule)
    return EffectiveRules(
        class_id=scope.class_id,
        subclass_key=scope.subclass_key,
        armor_classes=set(data["armor_classes"]),
        main_hand_kinds=expand_hand_tokens(data["main_hand"]),
        off_hand_kinds=expand_hand_tokens(data["off_hand"]),
    )


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def armor_allowed(rules: EffectiveRules, item: models.Items) -> bool:
    if rules.armor_classes is None or item.item_type not in ARMOR_RULE_TYPES or not item.armor_subclass:
        return True
    return item.armor_subclass in rules.armor_classes


def hand_allowed(rules: EffectiveRules, item: models.Items, slot_type: str) -> bool:
    """Whether a weapon may sit in the given hand (ignores what the other hand holds)."""
    if slot_type == OFF_HAND and is_two_handed(item):
        return False
    kinds = rules.main_hand_kinds if slot_type == MAIN_HAND else rules.off_hand_kinds
    if kinds is None or not item.weapon_subclass:
        return True
    return item.weapon_subclass in kinds


def allowed_hands(rules: EffectiveRules, item: models.Items) -> List[str]:
    return [slot for slot in HAND_SLOTS if hand_allowed(rules, item, slot)]


def forbidden_equipped_slots(
    db: Session, character_id: int, rules: EffectiveRules
) -> List[Tuple[models.EquipmentSlot, str]]:
    """Occupied slots whose item the character may no longer wear, with the reason."""
    slots = (
        db.query(models.EquipmentSlot)
        .filter(
            models.EquipmentSlot.character_id == character_id,
            models.EquipmentSlot.item_id.isnot(None),
        )
        .with_for_update()
        .all()
    )
    by_type = {s.slot_type: s for s in slots}
    items = {
        i.id: i
        for i in db.query(models.Items).filter(models.Items.id.in_([s.item_id for s in slots])).all()
    } if slots else {}

    result: List[Tuple[models.EquipmentSlot, str]] = []
    for slot in slots:
        item = items.get(slot.item_id)
        if item is None:
            continue
        if slot.slot_type in ARMOR_RULE_TYPES and not armor_allowed(rules, item):
            result.append((slot, "armor"))
        elif slot.slot_type in HAND_SLOTS and item.item_type == "weapon" and not hand_allowed(rules, item, slot.slot_type):
            result.append((slot, "weapon"))

    main = by_type.get(MAIN_HAND)
    off = by_type.get(OFF_HAND)
    if main and off and items.get(main.item_id) is not None and is_two_handed(items[main.item_id]):
        if all(s is not off for s, _ in result):
            result.append((off, "two_handed"))
    return result
