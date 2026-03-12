# inventory-service

**Порт:** 8004
**Технологии:** FastAPI, SQLAlchemy (sync), PyMySQL, httpx
**Путь:** `/home/dudka/chaldea/services/inventory-service/`

## Назначение

Инвентарь персонажей, система экипировки, каталог предметов, быстрые слоты, использование расходников.

## Структура файлов

```
inventory-service/app/
├── main.py               # FastAPI app, 14 эндпоинтов
├── models.py             # 3 SQLAlchemy модели
├── schemas.py            # Pydantic схемы
├── crud.py               # Бизнес-логика (экипировка, модификаторы)
├── config.py             # Настройки
├── database.py           # SQLAlchemy подключение
├── rabbitmq_consumer.py  # ЗАКОММЕНТИРОВАН
└── requirements.txt
```

## API Endpoints (14 штук)

### Инвентарь
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/inventory/` | Создать инвентарь + слоты экипировки для персонажа |
| GET | `/inventory/{id}/items` | Предметы в инвентаре |
| POST | `/inventory/{id}/items` | Добавить предмет (с учётом стаков) |
| DELETE | `/inventory/{id}/items/{item_id}?quantity=N` | Убрать предмет |

### Экипировка
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/{id}/equipment` | Слоты экипировки |
| POST | `/inventory/{id}/equip` | Экипировать предмет (транзакция с модификаторами) |
| POST | `/inventory/{id}/unequip` | Снять предмет (обратные модификаторы) |
| POST | `/inventory/{id}/use_item` | Использовать расходник |
| GET | `/inventory/{id}/fast_slots` | Быстрые слоты |

### Каталог предметов
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/items?q=&page=&page_size=` | Поиск предметов (пагинация) |
| POST | `/inventory/items` | Создать предмет |
| GET | `/inventory/items/{id}` | Предмет по ID |
| PUT | `/inventory/items/{id}` | Обновить предмет |
| DELETE | `/inventory/items/{id}` | Удалить предмет |

## Таблицы БД

### items (каталог)
- Базовые: id, name (unique), image, item_level, description, price, max_stack_size, is_unique
- **item_type** enum: head, body, cloak, belt, ring, necklace, bracelet, main_weapon, consumable, additional_weapons, resource, scroll, misc
- **item_rarity** enum: common, rare, epic, legendary, mythical, divine, demonic
- **armor_subclass**: cloth, light_armor, medium_armor, heavy_armor
- **weapon_subclass**: 25 типов (one_handed_weapon, two_handed_weapon, daggers, bows, staffs, grimoires...)
- **primary_damage_type**: physical, catting, crushing, piercing, magic, fire, ice, watering, electricity, wind, sainting, damning
- **Модификаторы статов** (30+ полей): strength/agility/intelligence/endurance/health/energy/mana/stamina/charisma/luck/damage/dodge_modifier
- **Модификаторы сопротивлений** (13 полей): res_physical_modifier, res_fire_modifier, ...
- **Модификаторы уязвимостей** (13 полей): vul_physical_modifier, vul_fire_modifier, ...
- **Восстановление**: health/energy/mana/stamina_recovery
- **Крит**: critical_hit_chance_modifier, critical_damage_modifier
- **fast_slot_bonus** - доп. быстрые слоты от предмета

### character_inventory
- id, character_id, item_id (FK -> items), quantity

### equipment_slots
- id, character_id, slot_type (enum: head/body/cloak/belt/ring/necklace/bracelet/main_weapon/additional_weapons/fast_slot_1..10), item_id (FK), is_enabled

## Система экипировки (equip)

1. Проверить предмет и его совместимость со слотом
2. Если слот занят -> снять старый предмет (обратные модификаторы)
3. Уменьшить quantity в инвентаре
4. Применить модификаторы -> HTTP POST к attributes-service `/apply_modifiers`
5. Пересчитать быстрые слоты (fast_slot_bonus от экипировки)
6. Rollback при любой ошибке

## Быстрые слоты

- Базово 4 слота + бонусы от экипировки
- Максимум 10 слотов
- Пересчёт (`recalc_fast_slots`) при каждом equip/unequip
- При уменьшении доступных слотов: лишние предметы возвращаются в инвентарь

## Коммуникация

### HTTP (исходящие)
- `character-attributes-service:8002` -> POST `/attributes/{id}/apply_modifiers` (при equip/unequip)
- `character-attributes-service:8002` -> POST `/attributes/{id}/recover` (при use_item)

## Известные проблемы

1. **Race conditions** - `with_for_update()` только в unequip, не в equip
2. **Нет composite unique constraint** на (character_id, slot_type) в equipment_slots
3. **build_modifiers_dict()** пропускает нулевые значения (может быть ошибкой)
4. **Fast slots 5-10 не полностью поддержаны** в is_item_compatible_with_slot
5. **RabbitMQ закомментирован**
6. **Нет аутентификации** на эндпоинтах
