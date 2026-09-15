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
| POST | `/inventory/items` | Создать предмет (включая `gathering_tool` с `tool_category` + 3 бонуса) |
| GET | `/inventory/items/{id}` | Предмет по ID |
| PUT | `/inventory/items/{id}` | Обновить предмет |
| DELETE | `/inventory/items/{id}` | Удалить предмет |
| GET | `/inventory/{id}/items?item_type=gathering_tool&category=pickaxe` | Фильтр по типу + tool_category (FEAT-128, для модалки выбора инструмента) |

### Добыча ресурсов (FEAT-128)

#### Player-facing (auth required)
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/characters/{character_id}/gathering-skills` | 3-скилла payload (Горное дело/Травничество/Лесорубство), lazy-create rows на первом запросе. Видимо read-only на чужих профилях |

#### Internal (no JWT, защищено Nginx + INTERNAL_SERVICE_TOKEN на API-gateway)
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/inventory/internal/characters/{cid}/gathering/award` | Атомарная транзакция: SELECT FOR UPDATE на character_inventory + tool + character_gathering_skills, добавление ресурса (с обработкой full-inventory), декремент durability, добавление XP, rank-up loop. Вызывается locations-service на finalize |
| POST | `/inventory/internal/characters/{cid}/free_slots_check` | Возвращает `{free_slot_count, is_full}`. Вызывается locations-service на старте добычи (preflight) |

## Таблицы БД

### items (каталог)
- Базовые: id, name (unique), image, item_level, description, price, max_stack_size, is_unique
- **image / full_image** (миграция 018): `full_image` — исходная картинка, `image` — квадратная иконка, вырезанная из неё photo-service. Оба поля пишет только photo-service; `full_image` отдаётся в `GET /items/{id}` и в аукционных ответах, через `PUT /items/{id}` не меняется. У старых предметов `full_image` = NULL — окна описания показывают `image`
- **item_type** enum: head, body, cloak, belt, ring, necklace, bracelet, main_weapon, consumable, additional_weapons, resource, scroll, misc, blueprint, recipe, gem, rune, **gathering_tool** (FEAT-128). Тип `shield` удалён миграцией 019: щит — обычное оружие вида buckler/targe/tower_shield
- **Поля для gathering_tool** (FEAT-128, NULL для других типов): `tool_category` enum(pickaxe/sickle/axe), `gather_double_chance_bonus` FLOAT, `gather_speed_bonus_pct` FLOAT, `gather_stamina_bonus_pct` FLOAT (все в диапазоне 0..50)
- **item_rarity** enum: common, rare, epic, legendary, mythical, divine, demonic
- **armor_subclass**: cloth, light_armor, medium_armor, heavy_armor — только для head/body (валидация в `ItemCreate`)
- **weapon_subclass** (вид оружия, миграция 019): 38 видов, каждый входит ровно в одну категорию — одноручное, полуторное, двуручное, древковое, стрелковое, щиты, другое, магическое. Категория не хранится, а берётся из `WEAPON_KIND_CATEGORY` (`schemas.py`, зеркало во фронте `constants/items.ts`). Только для main_weapon/additional_weapons. Под класс брони и вид/категорию оружия планируются ограничения экипировки по классу персонажа
- **res_\*/vul_\*/crit** — Float в БД и в схемах (раньше схема обрезала дробные до int)
- **blueprint_recipe_id** — принимается в `ItemCreate` только для чертежа, эндпоинт проверяет существование рецепта (400)
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

### gathering_skills (FEAT-128, каталог)
- id, slug (UNIQUE: mining/herbalism/woodcutting), name, category (UNIQUE: ore/herb/wood), description, icon, max_rank=5

### gathering_skill_ranks (FEAT-128)
- id, skill_id (FK CASCADE), rank_number (1..5), required_experience (XP для входа в ранг: 0/10/25/50/100), double_chance_bonus, speed_bonus_pct, stamina_bonus_pct (значения 0/4/8/12/20). UNIQUE(skill_id, rank_number)

### character_gathering_skills (FEAT-128)
- id, character_id, skill_id (FK CASCADE), current_rank (default 1), experience (toward NEXT rank, resets on rank-up), experience_total (lifetime), created_at, updated_at. UNIQUE(character_id, skill_id). Lazy-создаётся на первом обращении/первом начислении XP.

## Система экипировки (equip)

1. Проверить предмет и его совместимость со слотом
2. Если слот занят -> снять старый предмет (обратные модификаторы)
3. Уменьшить quantity в инвентаре
4. Применить модификаторы -> HTTP POST к attributes-service `/apply_modifiers`
5. Пересчитать быстрые слоты (fast_slot_bonus от экипировки)
6. Rollback при любой ошибке

## Ограничения экипировки по классу и подклассу

Код: `app/equipment_rules.py`, таблица `equipment_rules` (миграция 020).

- **Тип `weapon`** (миграция 019) заменил `main_weapon`/`additional_weapons` как **тип предмета**; слоты `main_weapon`/`additional_weapons` не изменились. В какую руку идёт оружие, решают правила.
- **Области правил:** строка класса (`scope_key = "class:<id>"`) действует, пока подкласс не выбран; строка подкласса (`scope_key = <subclass_key>`) — после выбора, строка класса тогда игнорируется. Нет строки = без ограничений.
- **Подкласс персонажа** читается из общей БД: `character_tree_progress` + `tree_nodes` (`node_type='subclass_choice'`), класс — `characters.id_class`. NPC и мобы (`is_npc`) не ограничиваются.
- **Содержимое строки:** `armor_classes` (для head/body), `main_hand` / `off_hand` — токены `category:<категория>` или `kind:<вид>`. Предметы без вида/класса брони не ограничиваются.
- **Двуручность:** виды категорий `two_handed` и `polearm` берутся только в основную руку, при надевании снимают предмет из доп. руки, пока надеты — доп. рука заблокирована. В `off_hand` такие токены запрещены (400).
- **Надевание:** `POST /inventory/{id}/equip` принимает `slot_type` (только для оружия); без него сервер выбирает свободную разрешённую руку.
- **Автоснятие** (`_revalidate_equipment`, пропускается во время боя) запускается: после сохранения правил (все игроки класса, фоном), после правки предмета с изменением типа/вида/класса брони (носящие его, фоном), из skills-service после выбора подкласса и после полного админского сброса дерева (`POST /inventory/internal/characters/{id}/revalidate-equipment`).
- **Эндпоинты:** `GET/PUT/DELETE /inventory/admin/equipment-rules` (`items:read` / `items:update`), `GET /inventory/{id}/equipment-rules` — что может носить персонаж (для подсветки в инвентаре).

## Быстрые слоты

- Базово 4 слота + бонусы от экипировки
- Максимум 10 слотов
- Пересчёт (`recalc_fast_slots`) при каждом equip/unequip
- При уменьшении доступных слотов: лишние предметы возвращаются в инвентарь

## Коммуникация

### HTTP (исходящие)
- `character-attributes-service:8002` -> POST `/attributes/{id}/apply_modifiers` (при equip/unequip)
- `character-attributes-service:8002` -> POST `/attributes/{id}/recover` (при use_item)

### check_not_gathering integration (FEAT-128)
Защитная проверка `is_character_gathering` (raw SQL `SELECT 1 FROM gathering_sessions WHERE character_id=:cid AND status='active' AND complete_at > NOW()`) добавлена в 11 action-эндпоинтов: `equip`, `unequip`, `craft`, `sharpen`, `extract-essence`, `transmute`, `insert-gem`, `extract-gem`, `smelt`, `identify`, `use-buff-item`, `use_item`. Возвращает 400 «Действие заблокировано во время добычи» если у персонажа активная сессия. Зеркальный паттерн `is_character_in_battle`.

## Известные проблемы

1. **Race conditions** - `with_for_update()` только в unequip, не в equip
2. **Нет composite unique constraint** на (character_id, slot_type) в equipment_slots
3. **build_modifiers_dict()** пропускает нулевые значения (может быть ошибкой)
4. **Fast slots 5-10 не полностью поддержаны** в is_item_compatible_with_slot
5. **RabbitMQ закомментирован**
6. **Нет аутентификации** на эндпоинтах
