"""
Perk condition evaluator — checks unearned perks against character state
and auto-unlocks perks whose conditions are fully met.

Called from the cumulative stats increment endpoint after stats are updated.
"""

import logging
from sqlalchemy.orm import Session

import models
import crud

logger = logging.getLogger(__name__)


def compare(current_value, operator: str, target_value) -> bool:
    """
    Compare current_value against target_value using the given operator.
    Supports: '>=', '<=', '==', '>', '<'
    Returns False for unknown operators.
    """
    try:
        current_value = float(current_value)
        target_value = float(target_value)
    except (TypeError, ValueError):
        return False

    if operator == ">=":
        return current_value >= target_value
    elif operator == "<=":
        return current_value <= target_value
    elif operator == "==":
        return current_value == target_value
    elif operator == ">":
        return current_value > target_value
    elif operator == "<":
        return current_value < target_value
    return False


def _fetch_character_level(character_id: int) -> int | None:
    """
    Fetch character level from character-service via HTTP.
    Returns the level as int, or None if the call fails.
    """
    from config import settings
    import httpx

    try:
        url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/full_profile"
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("level")
    except Exception as e:
        logger.warning(
            f"Не удалось получить уровень персонажа {character_id} из character-service: {e}"
        )
    return None


def _fetch_gold_balance(character_id: int) -> int | None:
    """Fetch current gold balance from character-service."""
    from config import settings
    import httpx

    try:
        url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/full_profile"
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("currency_balance")
    except Exception as e:
        logger.warning(f"Failed to fetch gold balance for character {character_id}: {e}")
    return None


def _fetch_quest_completed(character_id: int, quest_id: int) -> bool:
    """Check if character completed a specific quest via locations-service."""
    from config import settings
    import httpx

    try:
        url = f"{settings.LOCATIONS_SERVICE_URL}/locations/quests/internal/check-completed"
        resp = httpx.get(url, params={"character_id": character_id, "quest_id": quest_id}, timeout=5.0)
        if resp.status_code == 200:
            return resp.json().get("completed", False)
    except Exception as e:
        logger.warning(f"Failed to check quest completion for character {character_id}, quest {quest_id}: {e}")
    return False



def check_condition(
    condition: dict,
    cumulative_stats: models.CharacterCumulativeStats | None,
    attributes: models.CharacterAttributes | None,
    character_level: int | None,
    character_id: int = None,
    db: Session = None,
) -> bool:
    """
    Check a single perk condition against character state.

    Condition types:
      - cumulative_stat: compare cumulative_stats.<stat> with value
      - attribute: compare attributes.<stat> with value
      - character_level: compare character level with value
      - quest: check quest completion (stat=quest_id for specific, stat=completed_count for total)
      - perk_count: compare number of unlocked perks with value
      - has_perk: check if character has a specific perk (value = perk_id)
      - skill_level: compare skill rank level with value (stat = skill_id)
      - gold_balance: compare current gold balance with value
      - admin_grant: always False (only manually granted)
      - unknown: always False (extensible)
    """
    ctype = condition.get("type")
    stat = condition.get("stat")
    operator = condition.get("operator", ">=")
    value = condition.get("value")

    if ctype == "cumulative_stat":
        if cumulative_stats is None or not stat:
            return False
        current = getattr(cumulative_stats, stat, None)
        if current is None:
            return False
        return compare(current, operator, value)

    elif ctype == "attribute":
        if attributes is None or not stat:
            return False
        current = getattr(attributes, stat, None)
        if current is None:
            return False
        return compare(current, operator, value)

    elif ctype == "character_level":
        if character_level is None:
            return False
        return compare(character_level, operator, value)

    elif ctype == "quest":
        if not stat or character_id is None:
            return False
        if stat == "completed_count":
            # Use cumulative stat (quests_completed) — no HTTP needed
            if cumulative_stats is None:
                return False
            current = getattr(cumulative_stats, "quests_completed", 0) or 0
            return compare(current, operator, value)
        elif stat == "quest_id":
            # Check if specific quest is completed
            return _fetch_quest_completed(character_id, int(value))
        return False

    elif ctype == "perk_count":
        if db is None or character_id is None:
            return False
        count = (
            db.query(models.CharacterPerk)
            .filter(models.CharacterPerk.character_id == character_id)
            .count()
        )
        return compare(count, operator, value)

    elif ctype == "has_perk":
        if db is None or character_id is None:
            return False
        perk_id = int(value) if value is not None else None
        if perk_id is None:
            return False
        exists = (
            db.query(models.CharacterPerk)
            .filter(
                models.CharacterPerk.character_id == character_id,
                models.CharacterPerk.perk_id == perk_id,
            )
            .first()
        )
        return exists is not None

    elif ctype == "gold_balance":
        if character_id is None:
            return False
        balance = _fetch_gold_balance(character_id)
        if balance is None:
            return False
        return compare(balance, operator, value)

    elif ctype == "admin_grant":
        # Only manually granted by admin
        return False

    # Unknown condition type — extensible, return False
    return False


def evaluate_perks(db: Session, character_id: int) -> list[dict]:
    """
    Evaluate all active perks that the character does NOT yet have.
    For each perk whose ALL conditions are met, auto-unlock it and apply flat bonuses.

    Returns a list of dicts: [{"id": perk_id, "name": perk_name, "bonuses_applied": bool}, ...]
    """
    from sqlalchemy import and_

    # 1. Query all active perks that this character does NOT yet have
    earned_perk_ids_subquery = (
        db.query(models.CharacterPerk.perk_id)
        .filter(models.CharacterPerk.character_id == character_id)
        .subquery()
    )

    unearned_perks = (
        db.query(models.Perk)
        .filter(
            models.Perk.is_active == True,
            ~models.Perk.id.in_(earned_perk_ids_subquery),
        )
        .all()
    )

    if not unearned_perks:
        return []

    # 2. Fetch cumulative stats and attributes (one query each)
    cumulative_stats = crud.get_cumulative_stats(db, character_id)
    attributes = (
        db.query(models.CharacterAttributes)
        .filter(models.CharacterAttributes.character_id == character_id)
        .first()
    )

    # 3. Determine if we need character level (lazy fetch)
    needs_level = any(
        any(
            (c.get("type") if isinstance(c, dict) else c) == "character_level"
            for c in (perk.conditions or [])
        )
        for perk in unearned_perks
    )
    character_level = _fetch_character_level(character_id) if needs_level else None

    # 4. Evaluate each perk
    newly_unlocked = []

    for perk in unearned_perks:
        conditions = perk.conditions or []

        # Perk with no conditions should NOT auto-unlock (admin_grant only)
        if not conditions:
            continue

        # Check if ALL conditions contain only admin_grant type — skip
        condition_types = {
            (c.get("type") if isinstance(c, dict) else None)
            for c in conditions
        }
        if condition_types == {"admin_grant"}:
            continue

        # AND logic: all conditions must be true
        all_met = all(
            check_condition(
                c if isinstance(c, dict) else c,
                cumulative_stats,
                attributes,
                character_level,
                character_id=character_id,
                db=db,
            )
            for c in conditions
        )

        if not all_met:
            continue

        # 5. Unlock the perk — insert into character_perks
        # Check for race condition (another process may have inserted)
        existing = (
            db.query(models.CharacterPerk)
            .filter(
                models.CharacterPerk.character_id == character_id,
                models.CharacterPerk.perk_id == perk.id,
            )
            .first()
        )
        if existing:
            continue

        cp = models.CharacterPerk(
            character_id=character_id,
            perk_id=perk.id,
            is_custom=False,
        )
        db.add(cp)
        db.flush()

        # 6. Apply flat bonuses
        modifiers = crud.build_perk_modifiers_dict(perk, negative=False)
        bonuses_applied = False
        if modifiers:
            result = crud._apply_modifiers_internal(db, character_id, modifiers)
            bonuses_applied = bool(result)

        newly_unlocked.append({
            "id": perk.id,
            "name": perk.name,
            "bonuses_applied": bonuses_applied,
        })

        logger.info(
            f"Перк '{perk.name}' (id={perk.id}) автоматически разблокирован "
            f"для персонажа {character_id}, бонусы применены: {bonuses_applied}"
        )

    # Commit all unlocks and bonus applications
    if newly_unlocked:
        db.commit()

    return newly_unlocked


def reconcile_perks(db: Session, character_id: int) -> dict:
    """
    Dynamic perk reconciliation (FEAT-143).

    A perk is ACTIVE iff ALL of its conditions are currently met. Auto-earned
    perks (is_custom=False) are GRANTED when their conditions hold and REVOKED
    when they stop holding — with flat bonuses applied / reversed on each flip
    (via _apply_modifiers_internal, so derived effects follow too).

    Monotonic conditions (cumulative_stat, character_level, quest) only ever grow,
    so once met the perk stays active. State conditions (attribute from gear,
    gold_balance) flip the perk on/off. Admin-granted perks (is_custom=True) and
    admin_grant-only perks are left untouched.

    Returns {"granted": [...], "revoked": [...]}.
    """
    all_perks = (
        db.query(models.Perk).filter(models.Perk.is_active == True).all()
    )
    if not all_perks:
        return {"granted": [], "revoked": []}

    char_perks = {
        cp.perk_id: cp
        for cp in db.query(models.CharacterPerk)
        .filter(models.CharacterPerk.character_id == character_id)
        .all()
    }

    cumulative_stats = crud.get_cumulative_stats(db, character_id)
    attributes = (
        db.query(models.CharacterAttributes)
        .filter(models.CharacterAttributes.character_id == character_id)
        .first()
    )
    needs_level = any(
        any(
            (c.get("type") if isinstance(c, dict) else None) == "character_level"
            for c in (perk.conditions or [])
        )
        for perk in all_perks
    )
    character_level = _fetch_character_level(character_id) if needs_level else None

    granted: list[dict] = []
    revoked: list[dict] = []

    for perk in all_perks:
        conditions = perk.conditions or []
        if not conditions:
            continue
        condition_types = {
            (c.get("type") if isinstance(c, dict) else None) for c in conditions
        }
        if condition_types == {"admin_grant"}:
            continue  # admin-only perks are never auto-managed

        held_cp = char_perks.get(perk.id)
        # Never auto-touch an admin-granted perk.
        if held_cp is not None and held_cp.is_custom:
            continue

        all_met = all(
            check_condition(
                c,
                cumulative_stats,
                attributes,
                character_level,
                character_id=character_id,
                db=db,
            )
            for c in conditions
        )

        if all_met and held_cp is None:
            cp = models.CharacterPerk(
                character_id=character_id, perk_id=perk.id, is_custom=False
            )
            db.add(cp)
            db.flush()
            modifiers = crud.build_perk_modifiers_dict(perk, negative=False)
            if modifiers:
                crud._apply_modifiers_internal(db, character_id, modifiers)
            granted.append({"id": perk.id, "name": perk.name})
            logger.info(
                f"Перк '{perk.name}' (id={perk.id}) активирован для персонажа {character_id}"
            )
        elif not all_met and held_cp is not None:
            modifiers = crud.build_perk_modifiers_dict(perk, negative=True)
            if modifiers:
                crud._apply_modifiers_internal(db, character_id, modifiers)
            db.delete(held_cp)
            revoked.append({"id": perk.id, "name": perk.name})
            logger.info(
                f"Перк '{perk.name}' (id={perk.id}) деактивирован для персонажа {character_id}"
            )

    if granted or revoked:
        db.commit()

    return {"granted": granted, "revoked": revoked}
