from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_, func
import models
import schemas


# Получить инвентарь по ID персонажа
def get_inventory_by_character_id(db: Session, character_id: int):
    return db.query(models.CharacterInventory).filter(models.CharacterInventory.character_id == character_id).first()


# Функция для создания инвентаря персонажа
def create_character_inventory(db: Session, inventory_data: schemas.CharacterInventoryBase):
    """
    Создает запись CharacterInventory и сохраняет ее в базе данных.
    """
    db_inventory = models.CharacterInventory(
        character_id=inventory_data.character_id,
        item_id=inventory_data.item_id,
        quantity=inventory_data.quantity
    )
    db.add(db_inventory)
    db.commit()
    db.refresh(db_inventory)
    return db_inventory


def create_default_equipment_slots(db: Session, character_id: int):
    """
    Создает стандартные слоты экипировки для персонажа.
    Все слоты, кроме fast_slot_X, включены (is_enabled=True).
    Все fast_slot_X по умолчанию отключены (is_enabled=False).
    """
    slot_types = [
        'head', 'body', 'cloak', 'belt', 'ring', 'necklace', 'bracelet',
        'main_weapon', 'additional_weapons', 'shield',
        'fast_slot_1', 'fast_slot_2', 'fast_slot_3', 'fast_slot_4',
        'fast_slot_5', 'fast_slot_6', 'fast_slot_7', 'fast_slot_8',
        'fast_slot_9', 'fast_slot_10'
    ]

    equipment_slots = []

    for slot_type in slot_types:
        if slot_type.startswith("fast_slot_"):
            # Если это быстрый слот, делаем is_enabled = False
            new_slot = models.EquipmentSlot(
                character_id=character_id,
                slot_type=slot_type,
                item_id=None,
                is_enabled=False
            )
        else:
            # Все остальные слоты включаем
            new_slot = models.EquipmentSlot(
                character_id=character_id,
                slot_type=slot_type,
                item_id=None,
                is_enabled=True
            )

        db.add(new_slot)
        equipment_slots.append(new_slot)

    db.commit()
    return equipment_slots


def get_inventory_items(db: Session, character_id: int):
    return db.query(models.CharacterInventory).filter(models.CharacterInventory.character_id == character_id).all()

def get_equipment_slots(db: Session, character_id: int):
    return db.query(models.EquipmentSlot).filter(models.EquipmentSlot.character_id == character_id).all()

def is_item_compatible_with_slot(item_type: str, slot_type: str) -> bool:
    """
    Проверяет, совместим ли тип предмета с типом слота.
    """
    slot_to_item_mapping = {
        'head': ['head'],
        'body': ['body'],
        'cloak': ['cloak'],
        'belt': ['belt'],
        'ring': ['ring'],
        'necklace': ['necklace'],
        'bracelet': ['bracelet'],
        'main_weapon': ['main_weapon'],
        'additional_weapons': ['additional_weapons'],
        'shield': ['shield'],
        'fast_slot_1': ['consumable'],
        'fast_slot_2': ['consumable'],
        'fast_slot_3': ['consumable'],
        'fast_slot_4': ['consumable'],
    }
    return item_type in slot_to_item_mapping.get(slot_type, [])

def find_equipment_slot_for_item(db: Session, character_id: int, item_obj: models.Items):
    fixed = {
        'head': 'head', 'body': 'body', 'cloak': 'cloak', 'belt': 'belt',
        'ring': 'ring', 'necklace': 'necklace', 'bracelet': 'bracelet',
        'main_weapon': 'main_weapon', 'additional_weapons': 'additional_weapons',
        'shield': 'shield',
    }
    if item_obj.item_type in fixed:
        return db.query(models.EquipmentSlot).filter_by(
            character_id=character_id,
            slot_type=fixed[item_obj.item_type]
        ).with_for_update().first()

    # для consumable/scroll/misc
    fast_slots = [f"fast_slot_{i}" for i in range(1, 11)]

    # 1) пробуем активные
    slot = (
        db.query(models.EquipmentSlot)
          .filter(
              models.EquipmentSlot.character_id == character_id,
              models.EquipmentSlot.slot_type.in_(fast_slots),
              models.EquipmentSlot.is_enabled == True,
              models.EquipmentSlot.item_id.is_(None),
          )
          .order_by(models.EquipmentSlot.slot_type)
          .with_for_update()
          .first()
    )
    if slot:
        return slot

    # 2) если нет активных — берём _первый_ свободный и включаем его
    slot = (
        db.query(models.EquipmentSlot)
          .filter(
              models.EquipmentSlot.character_id == character_id,
              models.EquipmentSlot.slot_type.in_(fast_slots),
              models.EquipmentSlot.item_id.is_(None),
          )
          .order_by(models.EquipmentSlot.slot_type)
          .with_for_update()
          .first()
    )
    if slot:
        slot.is_enabled = True
        db.add(slot)
        db.flush()
        return slot

    return None


def return_item_to_inventory(db: Session, character_id: int, item_obj: models.Items):
    """
    Возвращаем 1 шт. предмета в инвентарь.
    Если max_stack_size>1, стакаем в существующий слот, иначе создаём новую запись.
    """
    if item_obj.max_stack_size > 1:
        # Ищем подходящий слот в инвентаре
        inv_slot = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.character_id == character_id,
            models.CharacterInventory.item_id == item_obj.id,
            models.CharacterInventory.quantity < item_obj.max_stack_size
        ).order_by(models.CharacterInventory.quantity.desc()).first()
        if inv_slot:
            inv_slot.quantity += 1
            db.add(inv_slot)
            db.flush()
            return

    # Если предмет нестекаемый или все стеки заполнены — создаём новый
    new_inv = models.CharacterInventory(
        character_id=character_id,
        item_id=item_obj.id,
        quantity=1
    )
    db.add(new_inv)
    db.flush()

def build_modifiers_dict(item_obj: models.Items, negative: bool = False) -> dict:
    """
    Формируем словарь модификаторов (ключ -> величина),
    основываясь на полях *_modifier у объекта Items.
    Если negative=True, то все значения умножаем на -1.
    """

    def val(x: int | float) -> int | float:
        return -x if negative else x

    mods = {}

    if item_obj.strength_modifier:
        mods["strength"] = val(item_obj.strength_modifier)
    if item_obj.agility_modifier:
        mods["agility"] = val(item_obj.agility_modifier)
    if item_obj.intelligence_modifier:
        mods["intelligence"] = val(item_obj.intelligence_modifier)
    if item_obj.endurance_modifier:
        mods["endurance"] = val(item_obj.endurance_modifier)
    if item_obj.health_modifier:
        mods["health"] = val(item_obj.health_modifier)
    if item_obj.energy_modifier:
        mods["energy"] = val(item_obj.energy_modifier)
    if item_obj.mana_modifier:
        mods["mana"] = val(item_obj.mana_modifier)
    if item_obj.stamina_modifier:
        mods["stamina"] = val(item_obj.stamina_modifier)
    if item_obj.charisma_modifier:
        mods["charisma"] = val(item_obj.charisma_modifier)
    if item_obj.luck_modifier:
        mods["luck"] = val(item_obj.luck_modifier)
    if item_obj.damage_modifier:
        mods["damage"] = val(item_obj.damage_modifier)
    if item_obj.dodge_modifier:
        mods["dodge"] = val(item_obj.dodge_modifier)

    # Сопротивления:
    if item_obj.res_effects_modifier:
        mods["res_effects"] = val(item_obj.res_effects_modifier)
    if item_obj.res_physical_modifier:
        mods["res_physical"] = val(item_obj.res_physical_modifier)
    if item_obj.res_catting_modifier:
        mods["res_catting"] = val(item_obj.res_catting_modifier)
    if item_obj.res_crushing_modifier:
        mods["res_crushing"] = val(item_obj.res_crushing_modifier)
    if item_obj.res_piercing_modifier:
        mods["res_piercing"] = val(item_obj.res_piercing_modifier)
    if item_obj.res_magic_modifier:
        mods["res_magic"] = val(item_obj.res_magic_modifier)
    if item_obj.res_fire_modifier:
        mods["res_fire"] = val(item_obj.res_fire_modifier)
    if item_obj.res_ice_modifier:
        mods["res_ice"] = val(item_obj.res_ice_modifier)
    if item_obj.res_watering_modifier:
        mods["res_watering"] = val(item_obj.res_watering_modifier)
    if item_obj.res_electricity_modifier:
        mods["res_electricity"] = val(item_obj.res_electricity_modifier)
    if item_obj.res_wind_modifier:
        mods["res_wind"] = val(item_obj.res_wind_modifier)
    if item_obj.res_sainting_modifier:
        mods["res_sainting"] = val(item_obj.res_sainting_modifier)
    if item_obj.res_damning_modifier:
        mods["res_damning"] = val(item_obj.res_damning_modifier)

    if item_obj.critical_hit_chance_modifier:
        mods["critical_hit_chance"] = val(item_obj.critical_hit_chance_modifier)
    if item_obj.critical_damage_modifier:
        mods["critical_damage"] = val(item_obj.critical_damage_modifier)

    if item_obj.vul_effects_modifier:
        mods["vul_effects"] = val(item_obj.vul_effects_modifier)
    if item_obj.vul_physical_modifier:
        mods["vul_physical"] = val(item_obj.vul_physical_modifier)
    if item_obj.vul_catting_modifier:
        mods["vul_catting"] = val(item_obj.vul_catting_modifier)
    if item_obj.vul_crushing_modifier:
        mods["vul_crushing"] = val(item_obj.vul_crushing_modifier)
    if item_obj.vul_piercing_modifier:
        mods["vul_piercing"] = val(item_obj.vul_piercing_modifier)
    if item_obj.vul_magic_modifier:
        mods["vul_magic"] = val(item_obj.vul_magic_modifier)
    if item_obj.vul_fire_modifier:
        mods["vul_fire"] = val(item_obj.vul_fire_modifier)
    if item_obj.vul_ice_modifier:
        mods["vul_ice"] = val(item_obj.vul_ice_modifier)
    if item_obj.vul_watering_modifier:
        mods["vul_watering"] = val(item_obj.vul_watering_modifier)
    if item_obj.vul_electricity_modifier:
        mods["vul_electricity"] = val(item_obj.vul_electricity_modifier)
    if item_obj.vul_sainting_modifier:
        mods["vul_sainting"] = val(item_obj.vul_sainting_modifier)
    if item_obj.vul_wind_modifier:
        mods["vul_wind"] = val(item_obj.vul_wind_modifier)
    if item_obj.vul_damning_modifier:
        mods["vul_damning"] = val(item_obj.vul_damning_modifier)

    # ПРИМЕЧАНИЕ: поля типа health_recovery / mana_recovery - это "расход" (consume)
    # Мы их используем только при "use_item", а не при "apply_modifiers" для экипировки.
    # Соответственно, здесь не добавляем их.
    return mods

def delete_all_inventory_for_character(db: Session, character_id: int) -> dict:
    """
    Bulk delete all equipment_slots and character_inventory rows for a character.
    Returns counts of deleted rows.
    """
    slots_deleted = (
        db.query(models.EquipmentSlot)
        .filter(models.EquipmentSlot.character_id == character_id)
        .delete(synchronize_session="fetch")
    )
    items_deleted = (
        db.query(models.CharacterInventory)
        .filter(models.CharacterInventory.character_id == character_id)
        .delete(synchronize_session="fetch")
    )
    db.commit()
    return {"items_deleted": items_deleted, "slots_deleted": slots_deleted}


def recalc_fast_slots(db: Session, character_id: int):
    # 1) Смотрим, какие предметы надеты
    eq_slots = db.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id,
        models.EquipmentSlot.item_id.isnot(None)
    ).all()

    # 2) Суммируем бонусы
    BASE_FAST_SLOTS = 4  # если хотите, что по умолчанию 4 слота, то ставьте 4
    total_bonus = 0
    for s in eq_slots:
        # Находим item_id => item => item.fast_slot_bonus
        item_obj = db.query(models.Items).filter(models.Items.id == s.item_id).first()
        if item_obj and item_obj.fast_slot_bonus:
            total_bonus += item_obj.fast_slot_bonus

    available_fast_slots = BASE_FAST_SLOTS + total_bonus
    # Не больше 10
    if available_fast_slots > 10:
        available_fast_slots = 10
    if available_fast_slots < 0:
        available_fast_slots = 0

    # 3) Получаем все fast_slot_* (1..10)
    fast_slots = db.query(models.EquipmentSlot).filter(
        models.EquipmentSlot.character_id == character_id,
        models.EquipmentSlot.slot_type.in_([f"fast_slot_{i}" for i in range(1, 11)])
    ).order_by(models.EquipmentSlot.slot_type.asc()).all()

    # Сортировка: fast_slot_1, fast_slot_2, ...
    # Активируем первые N, остальные деактивируем
    count_enabled = 0
    for slot in fast_slots:
        count_enabled += 1
        if count_enabled <= available_fast_slots:
            # Включаем
            slot.is_enabled = True
        else:
            # Выключаем
            slot.is_enabled = False
            # если там что-то лежит -> снимаем
            if slot.item_id is not None:
                old_item = db.query(models.Items).filter(models.Items.id == slot.item_id).first()
                # возвращаем в инвентарь
                return_item_to_inventory(db, character_id, old_item)
                slot.item_id = None
        db.add(slot)

    db.commit()


# ---------------------------------------------------------------------------
# Trade CRUD
# ---------------------------------------------------------------------------

def get_character_location(db: Session, character_id: int) -> Optional[int]:
    """Get character's current_location from shared DB."""
    row = db.execute(
        text("SELECT current_location_id FROM characters WHERE id = :cid"),
        {"cid": character_id}
    ).fetchone()
    return row[0] if row else None


def get_character_name(db: Session, character_id: int) -> str:
    """Get character name from shared DB."""
    row = db.execute(
        text("SELECT name FROM characters WHERE id = :cid"),
        {"cid": character_id}
    ).fetchone()
    return row[0] if row else "Неизвестный"


def get_character_user_id(db: Session, character_id: int) -> Optional[int]:
    """Get user_id who owns the character."""
    row = db.execute(
        text("SELECT user_id FROM characters WHERE id = :cid"),
        {"cid": character_id}
    ).fetchone()
    return row[0] if row else None


def get_character_gold(db: Session, character_id: int) -> int:
    """Get character currency_balance from shared DB."""
    row = db.execute(
        text("SELECT currency_balance FROM characters WHERE id = :cid"),
        {"cid": character_id}
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def is_character_in_battle(db: Session, character_id: int) -> bool:
    """Check if character is in an active battle via shared DB."""
    row = db.execute(
        text(
            "SELECT 1 FROM battle_participants bp "
            "JOIN battles b ON bp.battle_id = b.id "
            "WHERE bp.character_id = :cid AND b.status IN ('pending', 'in_progress') "
            "LIMIT 1"
        ),
        {"cid": character_id}
    ).fetchone()
    return row is not None


def get_active_trade_between(
    db: Session, char_a: int, char_b: int
) -> Optional[models.TradeOffer]:
    """Find an existing active (non-terminal) trade between two characters."""
    return db.query(models.TradeOffer).filter(
        models.TradeOffer.status.in_(['pending', 'negotiating']),
        or_(
            and_(
                models.TradeOffer.initiator_character_id == char_a,
                models.TradeOffer.target_character_id == char_b,
            ),
            and_(
                models.TradeOffer.initiator_character_id == char_b,
                models.TradeOffer.target_character_id == char_a,
            ),
        )
    ).first()


def create_trade_offer(
    db: Session, initiator_id: int, target_id: int, location_id: int
) -> models.TradeOffer:
    trade = models.TradeOffer(
        initiator_character_id=initiator_id,
        target_character_id=target_id,
        location_id=location_id,
        status='pending',
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def get_trade_offer(db: Session, trade_id: int) -> Optional[models.TradeOffer]:
    return db.query(models.TradeOffer).filter(
        models.TradeOffer.id == trade_id
    ).first()


def update_trade_items(
    db: Session,
    trade: models.TradeOffer,
    character_id: int,
    items: List[schemas.TradeItemEntry],
    gold: int,
) -> models.TradeOffer:
    """Replace all items for one side and update gold. Resets both confirmed flags."""
    # Remove existing items for this character in this trade
    db.query(models.TradeOfferItem).filter(
        models.TradeOfferItem.trade_offer_id == trade.id,
        models.TradeOfferItem.character_id == character_id,
    ).delete(synchronize_session="fetch")

    # Add new items
    for entry in items:
        item_row = models.TradeOfferItem(
            trade_offer_id=trade.id,
            character_id=character_id,
            item_id=entry.item_id,
            quantity=entry.quantity,
        )
        db.add(item_row)

    # Update gold for the correct side
    if character_id == trade.initiator_character_id:
        trade.initiator_gold = gold
    else:
        trade.target_gold = gold

    # Reset confirmations
    trade.initiator_confirmed = False
    trade.target_confirmed = False

    # Move to negotiating if still pending
    if trade.status == 'pending':
        trade.status = 'negotiating'

    db.commit()
    db.refresh(trade)
    return trade


def confirm_trade(db: Session, trade: models.TradeOffer, character_id: int) -> bool:
    """Set confirmed flag for one side. Returns True if both sides now confirmed."""
    if character_id == trade.initiator_character_id:
        trade.initiator_confirmed = True
    else:
        trade.target_confirmed = True
    db.flush()
    return trade.initiator_confirmed and trade.target_confirmed


def execute_trade(db: Session, trade: models.TradeOffer) -> None:
    """
    Execute trade atomically: transfer items and gold between characters.
    Assumes caller manages the transaction (no commit here, caller commits).
    """
    initiator_id = trade.initiator_character_id
    target_id = trade.target_character_id

    # 1. Verify gold balances
    if trade.initiator_gold > 0:
        balance = get_character_gold(db, initiator_id)
        if balance < trade.initiator_gold:
            raise ValueError("У инициатора недостаточно золота для обмена")

    if trade.target_gold > 0:
        balance = get_character_gold(db, target_id)
        if balance < trade.target_gold:
            raise ValueError("У второго участника недостаточно золота для обмена")

    # 2. Verify items
    trade_items = db.query(models.TradeOfferItem).filter(
        models.TradeOfferItem.trade_offer_id == trade.id
    ).all()

    for ti in trade_items:
        total_qty = db.execute(
            text(
                "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
                "WHERE character_id = :cid AND item_id = :iid"
            ),
            {"cid": ti.character_id, "iid": ti.item_id}
        ).scalar()
        if total_qty < ti.quantity:
            char_name = get_character_name(db, ti.character_id)
            item_obj = db.query(models.Items).get(ti.item_id)
            item_name = item_obj.name if item_obj else f"#{ti.item_id}"
            raise ValueError(
                f"У {char_name} недостаточно предмета \"{item_name}\" "
                f"(нужно {ti.quantity}, есть {total_qty})"
            )

    # 3. Transfer items
    for ti in trade_items:
        # Determine sender and receiver
        if ti.character_id == initiator_id:
            receiver_id = target_id
        else:
            receiver_id = initiator_id

        # Remove from sender
        _remove_items_from_inventory(db, ti.character_id, ti.item_id, ti.quantity)
        # Add to receiver
        _add_items_to_inventory(db, receiver_id, ti.item_id, ti.quantity)

    # 4. Transfer gold
    if trade.initiator_gold > 0:
        db.execute(
            text("UPDATE characters SET currency_balance = currency_balance - :gold WHERE id = :cid"),
            {"gold": trade.initiator_gold, "cid": initiator_id}
        )
        db.execute(
            text("UPDATE characters SET currency_balance = currency_balance + :gold WHERE id = :cid"),
            {"gold": trade.initiator_gold, "cid": target_id}
        )

    if trade.target_gold > 0:
        db.execute(
            text("UPDATE characters SET currency_balance = currency_balance - :gold WHERE id = :cid"),
            {"gold": trade.target_gold, "cid": target_id}
        )
        db.execute(
            text("UPDATE characters SET currency_balance = currency_balance + :gold WHERE id = :cid"),
            {"gold": trade.target_gold, "cid": initiator_id}
        )

    # 5. Mark trade as completed
    trade.status = 'completed'


def _remove_items_from_inventory(
    db: Session, character_id: int, item_id: int, quantity: int
) -> None:
    """Remove quantity of item from character inventory, respecting stacks."""
    remaining = quantity
    slots = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id,
    ).order_by(models.CharacterInventory.quantity.asc()).all()

    for slot in slots:
        if remaining <= 0:
            break
        if slot.quantity <= remaining:
            remaining -= slot.quantity
            db.delete(slot)
        else:
            slot.quantity -= remaining
            remaining = 0
    db.flush()


def _add_items_to_inventory(
    db: Session, character_id: int, item_id: int, quantity: int
) -> None:
    """Add quantity of item to character inventory, respecting stacks."""
    item_obj = db.query(models.Items).get(item_id)
    if not item_obj:
        return
    max_stack = item_obj.max_stack_size
    remaining = quantity

    # Fill existing stacks first
    existing = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.character_id == character_id,
        models.CharacterInventory.item_id == item_id,
        models.CharacterInventory.quantity < max_stack,
    ).all()

    for slot in existing:
        if remaining <= 0:
            break
        space = max_stack - slot.quantity
        to_add = min(space, remaining)
        slot.quantity += to_add
        remaining -= to_add

    # Create new stacks
    while remaining > 0:
        to_add = min(remaining, max_stack)
        new_slot = models.CharacterInventory(
            character_id=character_id,
            item_id=item_id,
            quantity=to_add,
        )
        db.add(new_slot)
        remaining -= to_add

    db.flush()


def build_trade_state(db: Session, trade: models.TradeOffer) -> dict:
    """Build the full trade state response dict."""
    initiator_name = get_character_name(db, trade.initiator_character_id)
    target_name = get_character_name(db, trade.target_character_id)

    initiator_items = _get_trade_side_items(db, trade.id, trade.initiator_character_id)
    target_items = _get_trade_side_items(db, trade.id, trade.target_character_id)

    return {
        "trade_id": trade.id,
        "status": trade.status,
        "initiator": {
            "character_id": trade.initiator_character_id,
            "character_name": initiator_name,
            "items": initiator_items,
            "gold": trade.initiator_gold,
            "confirmed": trade.initiator_confirmed,
        },
        "target": {
            "character_id": trade.target_character_id,
            "character_name": target_name,
            "items": target_items,
            "gold": trade.target_gold,
            "confirmed": trade.target_confirmed,
        },
    }


def _get_trade_side_items(
    db: Session, trade_offer_id: int, character_id: int
) -> List[dict]:
    """Get item details for one side of a trade."""
    trade_items = db.query(models.TradeOfferItem).filter(
        models.TradeOfferItem.trade_offer_id == trade_offer_id,
        models.TradeOfferItem.character_id == character_id,
    ).all()

    result = []
    for ti in trade_items:
        item_obj = db.query(models.Items).get(ti.item_id)
        result.append({
            "item_id": ti.item_id,
            "item_name": item_obj.name if item_obj else "Неизвестный предмет",
            "item_image": item_obj.image if item_obj else None,
            "quantity": ti.quantity,
        })
    return result


def get_pending_trades_for_character(
    db: Session, character_id: int
) -> List[models.TradeOffer]:
    """Get all active (pending/negotiating) trades involving a character."""
    return db.query(models.TradeOffer).filter(
        models.TradeOffer.status.in_(['pending', 'negotiating']),
        or_(
            models.TradeOffer.initiator_character_id == character_id,
            models.TradeOffer.target_character_id == character_id,
        )
    ).order_by(models.TradeOffer.created_at.desc()).all()


def verify_item_ownership(
    db: Session, character_id: int, items: List[schemas.TradeItemEntry]
) -> Optional[str]:
    """
    Verify character owns all items in sufficient quantity.
    Returns error message string or None if all OK.
    """
    for entry in items:
        total_qty = db.execute(
            text(
                "SELECT COALESCE(SUM(quantity), 0) FROM character_inventory "
                "WHERE character_id = :cid AND item_id = :iid"
            ),
            {"cid": character_id, "iid": entry.item_id}
        ).scalar()
        if total_qty < entry.quantity:
            item_obj = db.query(models.Items).get(entry.item_id)
            item_name = item_obj.name if item_obj else f"#{entry.item_id}"
            return (
                f"Недостаточно предмета \"{item_name}\" "
                f"(нужно {entry.quantity}, есть {total_qty})"
            )
    return None
