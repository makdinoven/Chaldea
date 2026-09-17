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
| POST | `/inventory/{id}/use_item` | Использовать расходник (еду — нельзя, 400 «Еду нужно съесть») |
| POST | `/inventory/{id}/eat-food` | FEAT-164: съесть еду `{inventory_item_id}` → сытость на 24 ч (JWT + владелец) |
| GET | `/inventory/{id}/fast_slots` | Быстрые слоты |

### Каталог предметов
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/items?q=&item_types=&exclude_types=&resource_subcategory=&page=&page_size=` | Поиск предметов (пагинация); `resource_subcategory` — FEAT-165, неизвестное значение → 422 |
| POST | `/inventory/items` | Создать предмет (включая `gathering_tool` с `tool_category` + 3 бонуса) |
| GET | `/inventory/items/{id}` | Предмет по ID |
| PUT | `/inventory/items/{id}` | Обновить предмет (FEAT-165: настройки переработки, переставшие подходить к подкатегории предмета, удаляются в той же транзакции — и как у сырья, и как у результата) |
| GET / PUT | `/inventory/admin/items/{id}/conversions` | FEAT-165: настройки переработки сырья (`items:read` / `items:update`), PUT заменяет весь набор |
| DELETE | `/inventory/items/{id}` | Удалить предмет |
| GET | `/inventory/{id}/items?item_type=gathering_tool&category=pickaxe` | Фильтр по типу + tool_category (FEAT-128, для модалки выбора инструмента) |

### Добыча ресурсов (FEAT-128)

#### Player-facing (auth required)
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/characters/{character_id}/gathering-skills` | Навыки добычи из БД (Горное дело/Травничество/Лесорубство/Собирательство), lazy-create rows на первом запросе. Видимо read-only на чужих профилях |

#### Internal (no JWT, защищено Nginx + INTERNAL_SERVICE_TOKEN на API-gateway)
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/inventory/internal/characters/{cid}/gathering/award` | Атомарная транзакция: SELECT FOR UPDATE на character_inventory + tool + character_gathering_skills, добавление ресурса (с обработкой full-inventory), декремент durability, добавление XP, rank-up loop. Вызывается locations-service на finalize |
| POST | `/inventory/internal/characters/{cid}/free_slots_check` | Возвращает `{free_slot_count, is_full}`. Вызывается locations-service на старте добычи (preflight) |

## Таблицы БД

### items (каталог)
- Базовые: id, name (unique), image, item_level, description, price, max_stack_size, is_unique
- **image / full_image** (миграция 018): `full_image` — исходная картинка, `image` — квадратная иконка, вырезанная из неё photo-service. Оба поля пишет только photo-service; `full_image` отдаётся в `GET /items/{id}` и в аукционных ответах, через `PUT /items/{id}` не меняется. У старых предметов `full_image` = NULL — окна описания показывают `image`
- **item_type** enum: head, body, cloak, belt, ring, necklace, bracelet, weapon, consumable, resource, scroll, misc, recipe, gem, rune, **gathering_tool** (FEAT-128). Тип `shield` удалён миграцией 019 (щит — обычное оружие вида buckler/targe/tower_shield), тип `blueprint` — миграцией 022 (FEAT-165, одноразовых чертежей больше нет)
- **resource_subcategory** (FEAT-165, миграция 022, индекс) — только для `resource`, NULL = «Прочее»: сырьё `ore/herb/wood/ingredient/trophy`, продукты переработки `ingot/magic_dust/essence/reagent/material`, расходники профессий `whetstone/repair_kit`
- **whetstone_level** (1/2/3 → шанс 25/50/75 %) + **whetstone_group** (FEAT-165: `weapon_armor` / `cloak_belt` / `jewelry`) — только у подкатегории `whetstone` (оба обязательны); **repair_power** у ресурса — только у `repair_kit` (> 0)
- **socket_count > 0** — только weapon/head/body/cloak/ring/necklace/bracelet (у пояса гнёзд нет с FEAT-165)
- `essence_result_item_id` удалён миграцией 022 (извлечение эссенций убрано)
- **Поля для gathering_tool** (FEAT-128, NULL для других типов): `tool_category` enum(pickaxe/sickle/axe), `gather_double_chance_bonus` FLOAT, `gather_speed_bonus_pct` FLOAT, `gather_stamina_bonus_pct` FLOAT (все в диапазоне 0..50)
- **item_rarity** enum: common, rare, epic, legendary, mythical, divine, demonic
- **armor_subclass**: cloth, light_armor, medium_armor, heavy_armor — только для head/body (валидация в `ItemCreate`)
- **weapon_subclass** (вид оружия, миграция 019): 38 видов, каждый входит ровно в одну категорию — одноручное, полуторное, двуручное, древковое, стрелковое, щиты, другое, магическое. Категория не хранится, а берётся из `WEAPON_KIND_CATEGORY` (`schemas.py`, зеркало во фронте `constants/items.ts`). Только для main_weapon/additional_weapons. Под класс брони и вид/категорию оружия планируются ограничения экипировки по классу персонажа
- **res_\*/vul_\*/crit** — Float в БД и в схемах (раньше схема обрезала дробные до int)
- **blueprint_recipe_id** — связь предмета-рецепта (`item_type='recipe'`) с рецептом; принимается только для `recipe` (422), эндпоинт проверяет существование рецепта (400). Имя колонки историческое, её читает photo-service
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
- id, slug (UNIQUE: mining/herbalism/woodcutting/foraging), name, category (UNIQUE: ore/herb/wood/ingredient), description, icon, max_rank=5
- `foraging` «Собирательство» (категория `ingredient`) добавлен миграцией 022 (FEAT-165); ранги скопированы с `herbalism`. `GatheringAwardRequest.skill_slug` принимает все четыре слага

### item_conversions (FEAT-165, настройки переработки)
- id, source_item_id (FK items CASCADE), profession_id (FK professions CASCADE), source_quantity, result_item_id (FK items CASCADE), result_quantity (оба 1..100, CHECK), created_at, updated_at. UNIQUE(source_item_id, profession_id)

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

## Еда и сытость (FEAT-164)

- `items.is_food` (BOOLEAN, default 0, миграция `021_add_item_is_food`). Едой может быть только `consumable` без `buff_type` (валидатор `ItemCreate`). Еда использует обычные поля `*_modifier` (бонусы на время сытости) и `*_recovery` (мгновенное восстановление при поедании).
- `POST /inventory/{id}/eat-food`: владелец → не в бою (400 «Нельзя есть во время боя»; в подземелье и на сборе можно) → блокировка строки инвентаря → `is_food` (иначе 400 «Этот предмет нельзя съесть») → `POST character-attributes-service /attributes/internal/{id}/satiety` (модификаторы `build_modifiers_dict`, восстановление ×1, редкость предмета). Предмет списывается **только после 201**. 409 «Вы уже наелись» и 400 пробрасываются; недоступность/5xx сервиса атрибутов → 502 «Не удалось применить сытость, попробуйте позже», предмет остаётся. Ответ: `{success, message, satiety}`.
- Еда отклоняется в `use_item`, `use-buff-item` (400 «Еду нужно съесть»), при экипировке в быстрый слот (400 «Еду нельзя положить в быстрый слот») и во внутреннем `consume_item` (400 «Еду нельзя использовать в бою»).

## Ограничение редкости (FEAT-164)

- Мифическая, божественная и демоническая редкость — только у снаряжения (`head, body, cloak, belt, ring, necklace, bracelet, weapon`; `schemas.EQUIPMENT_ITEM_TYPES` / `EQUIPMENT_ONLY_RARITIES`, это множества, без порядка редкостей). Любой другой тип — максимум легендарная (400/422 «Мифическая, божественная и демоническая редкость доступны только для снаряжения»).
- **У рецептов нет своего качества** — оно есть только у результата. `POST/PUT /inventory/admin/recipes`: поле `rarity` в запросе устарело и игнорируется; `recipes.rarity` всегда записывается из редкости результирующего предмета (при создании и при каждом обновлении — нужен для `RARITY_XP_MAP` и фильтра `?rarity=`). Ответы по-прежнему содержат `rarity` (= редкость результата).
- Лимит проверяется по результату: не-снаряжение с мифической/божественной/демонической редкостью (только старые строки) → 400 «Крафт не может создавать предметы мифической, божественной или демонической редкости». Для снаряжения в результате эти редкости разрешены.
- Автосоздаваемый предмет-рецепт (`item_type='recipe'`) не имеет качества: хранится как `common` (колонка NOT NULL). Фронтенд скрывает редкость для `item_type` `recipe`.
- Трансмутация убрана в FEAT-165. Существующий на проде «Трансмутированный ресурс (мифический)» не тронут (миграция 021 только логирует такие предметы/рецепты).

## Профессии, крафт, переработка, заточка, гнёзда (FEAT-165)

Таблицы: `professions` (slug `scholar` теперь называется «Мистик», миграция 022), `profession_ranks`, `recipes` (колонка `is_blueprint_recipe` удалена), `recipe_ingredients`, `character_professions`, `character_recipes`, `item_conversions`.

**Опыт профессии — только за создание:** крафт по рецепту и переработку. Всё начисление идёт через `crud.award_profession_xp(db, cp, base_xp)` (множитель XP-баффа, повышение ранга, выдача базовых рецептов); без коммита, коммитит вызывающий. За заточку, вставку и извлечение камней/рун опыта нет.

**Рецепты:**
- Изучение: `POST /inventory/crafting/{cid}/learn-from-item` (тратит предмет-рецепт) или автоматически — базовые рецепты (`auto_learn_rank IS NOT NULL AND auto_learn_rank <= current_rank`, активные, своей профессии) через идемпотентный `crud.sync_auto_learned_recipes`. Он вызывается при выборе/смене профессии, админском `set-rank`, в `award_profession_xp` и лениво в `GET /professions/{cid}/my` и `GET /crafting/{cid}/recipes` (гонка двойной вставки гасится откатом, GET не падает). Так рецепт, созданный админом позже, доходит до уже прокачанных игроков.
- Бесплатный `POST /crafting/{cid}/learn-recipe` удалён (404).
- `POST /crafting/{cid}/craft` body `{recipe_id}` — рецепт должен быть изучен (лишнее поле `blueprint_item_id` игнорируется). Ответ без `blueprint_consumed`. `GET /crafting/{cid}/recipes` — только изученные, `source` всегда `"learned"`.

**Переработка** (константы в `crud.py`):
- `REFINING_RULES` (slug → подкатегория сырья, подкатегория результата): кузнец руда→слитки, ювелир руда→магическая пыль, алхимик реагенты→эссенции, повар ингредиенты→реагенты, Мистик (`scholar`) трофеи→материалы. У зачарователя переработки нет.
- `REFINE_DOUBLE_CHANCE_BY_RANK = {1: 0.05, 2: 0.10, 3: 0.20}` — шанс удвоения, бросается на каждый шаг (ранги выше таблицы берут верхнее значение); `REFINE_XP_BY_RARITY = {common: 5, rare: 12, epic: 25, legendary: 50}` — опыт за шаг по редкости результата.
- `GET /crafting/refining-rules` (JWT) — правила, привязанные к активным профессиям.
- `GET /crafting/{cid}/refine-info` (JWT + владелец) — сырьё из инвентаря (опознанные стопки, суммарно) с настроенным результатом для профессии персонажа; без профессии/правила → `can_refine: false` (200).
- `POST /crafting/{cid}/refine` `{source_item_id, quantity 1..9999}` (JWT + владелец, не в бою, не на сборе): одна транзакция, `FOR UPDATE` на стопках сырья; `шаги = quantity // source_quantity`, остаток не тратится; результат `result_quantity × (шаги + удвоенные)`; всегда успешно; без проверки места в инвентаре (как крафт). Ошибки до любой записи: 400 (нет профессии/правила, не та подкатегория, нет настройки, нет результата, не хватает сырья, меньше одного шага), 404 (нет предмета), 500 «Ошибка при переработке».
- `GET/PUT /admin/items/{id}/conversions` — проверки: сырьё = ресурс сырьевой подкатегории, которую принимает профессия; результат ≠ сырью, ресурс нужной подкатегории; без повторов профессий; не больше числа правил (5); количества 1..100 (422).

**Заточка:** точить может любой персонаж (без профессии тоже). Камень должен подходить к предмету: `SHARPEN_GROUP_TYPES` — `weapon_armor` (оружие, броня, шлем), `cloak_belt` (плащ, пояс), `jewelry` (кольцо, ожерелье, браслет). `sharpen-info` отдаёт `sharpen_group` и только подходящие камни (`whetstone_group` у каждого). Неподходящий камень → 400 «Этот камень не подходит для этого предмета», камень не тратится. Бюджет 15 очков, +5 на стат, шансы по `whetstone_level` — без изменений. Ответ без полей опыта.

**Гнёзда:** вставлять может любой персонаж с камнем/руной: огранки (`gem`) → кольцо/ожерелье/браслет, руны (`rune`) → оружие/броня/шлем/плащ (`RUNE_INSERT_TYPES`); пояс → 400 «Этот тип предмета не поддерживает руны». Извлекать — только ювелир (огранки из украшений) и зачарователь (руны, включая старые руны в поясах, `RUNE_EXTRACT_TYPES`). `socket-info` доступен без профессии и отдаёт `insertable_type`, `can_insert`, `can_extract`, `extract_preservation_chance`; пояс показывается, только пока в нём есть руны. Ответы insert/extract без полей опыта.

**Удалено:** извлечение эссенций (`extract-info`, `extract-essence`), трансмутация (`transmute-info`, `transmute`), переплавка украшений (`smelt-info`, `smelt`). Старые предметы (кристаллы, трансмутированные ресурсы, «Ювелирный лом», эссенции стихий) не тронуты — подкатегория «Прочее», админ удалит сам.

## Быстрые слоты

- Базово 4 слота + бонусы от экипировки
- Максимум 10 слотов
- Пересчёт (`recalc_fast_slots`) при каждом equip/unequip
- При уменьшении доступных слотов: лишние предметы возвращаются в инвентарь

## Коммуникация

### HTTP (исходящие)
- `character-attributes-service:8002` -> POST `/attributes/{id}/apply_modifiers` (при equip/unequip, заточке и вставке/извлечении у надетого предмета)
- `character-attributes-service:8002` -> POST `/attributes/{id}/recover` (при use_item)
- `character-attributes-service:8002` -> POST `/attributes/internal/{id}/satiety` (при eat-food, sync httpx, timeout 5 с)

### check_not_gathering integration (FEAT-128)
Защитная проверка `is_character_gathering` (raw SQL `SELECT 1 FROM gathering_sessions WHERE character_id=:cid AND status='active' AND complete_at > NOW()`) добавлена в action-эндпоинты: `equip`, `unequip`, `craft`, `refine`, `sharpen`, `insert-gem`, `extract-gem`, `identify`, `use-buff-item`, `use_item`. Возвращает 400 «Действие заблокировано во время добычи» если у персонажа активная сессия. Зеркальный паттерн `is_character_in_battle`.

## Известные проблемы

1. **Race conditions** - `with_for_update()` только в unequip, не в equip
2. **Нет composite unique constraint** на (character_id, slot_type) в equipment_slots
3. **build_modifiers_dict()** пропускает нулевые значения (может быть ошибкой)
4. **Fast slots 5-10 не полностью поддержаны** в is_item_compatible_with_slot
5. **RabbitMQ закомментирован**
6. **Нет аутентификации** на эндпоинтах
