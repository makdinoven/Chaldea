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
| POST | `/inventory/` | Создать инвентарь + слоты экипировки для персонажа. **FEAT-167 (задача #18): только межсервисный вызов**, требует `X-Internal-Token` (fail-closed: пустой `INTERNAL_SERVICE_TOKEN` → 503 «Internal service token не настроен», неверный/отсутствующий заголовок → 401 «Недействительный internal token»). Единственный вызывающий — character-service `crud.send_inventory_request` (стартовый набор при создании персонажа). До FEAT-167 роут не имел ни одной зависимости: анонимный запрос через gateway доходил до обработчика (422 по схеме, а не 401) и позволял создавать инвентарь и слоты экипировки для произвольного `character_id`. Nginx вторым слоем — точный блок `location = /inventory/` с `limit_except GET HEAD`; остальные роуты `/inventory/` не затронуты |
| GET | `/inventory/{id}/items` | Предметы в инвентаре. **FEAT-171 (I1): приватно** — `get_optional_user` + `require_private_access`: владелец, admin/moderator с `characters:read` и НПС (`user_id IS NULL`). Чужому/гостю → 403 «Эти данные доступны только владельцу персонажа», несуществующему персонажу → 404 «Персонаж не найден» (проверяется первой). Админский редактор персонажей проходит по ветке admin |
| POST | `/inventory/{id}/items` | Админская выдача предмета (с учётом стаков). FEAT-167: JWT + разрешение `items:update` |
| POST | `/inventory/internal/characters/{id}/items` | FEAT-167: та же выдача для межсервисных вызовов, только `X-Internal-Token` (fail-closed: пустой env → 503, неверный заголовок → 401) |
| DELETE | `/inventory/{id}/items/{item_id}?quantity=N` | Убрать предмет |

### Экипировка
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/{id}/equipment` | Слоты экипировки. FEAT-167: у каждого слота есть `effective_damage` — фактический урон оружия в этом слоте. **FEAT-171 (I2): приватно**, та же зависимость и те же коды, что у `/items`. Тело для владельца/админа прежнее, вместе с рядами `fast_slot_*`. Этим закрыт обход гейта быстрых слотов из FEAT-169 |
| GET | `/inventory/{id}/equipment/public` | **FEAT-171 (I2p): публичная витрина** — `[{slot_type, item: PublicItemCard\|null}]`, доступна всем, включая гостей. Ряды пояса (`fast_slot_*`) отсекаются **на уровне запроса** (`slot_type NOT LIKE 'fast_slot_%'` в `crud.get_public_equipment_slots`), а не пост-фильтром. Ни `effective_damage`, ни `enhancement_*`, ни `socketed_gems`, ни `current_durability`, ни `is_enabled`, ни `item_id`, ни `character_id`. Несуществующий персонаж → 404 |
| POST | `/inventory/{id}/equip` | Экипировать предмет (транзакция с модификаторами) |
| POST | `/inventory/{id}/unequip` | Снять предмет (обратные модификаторы) |
| POST | `/inventory/{id}/use_item` | Использовать расходник (еду — нельзя, 400 «Еду нужно съесть») |
| POST | `/inventory/{id}/eat-food` | FEAT-164: съесть еду `{inventory_item_id}` → сытость на 24 ч (JWT + владелец) |
| GET | `/inventory/characters/{id}/fast_slots` | Быстрые слоты (пояс). **FEAT-169: JWT + владение** — читать чужой пояс нельзя (401 без токена, 404 «Персонаж не найден», 403 «Вы можете управлять только своими персонажами»). Для сервисов есть internal-двойник (см. ниже) |

### Каталог предметов
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/items?q=&item_types=&exclude_types=&resource_subcategory=&page=&page_size=` | Поиск предметов (пагинация); `resource_subcategory` — FEAT-165, неизвестное значение → 422 |
| POST | `/inventory/items` | Создать предмет (включая `gathering_tool` с `tool_category` + 3 бонуса). FEAT-168: принимает вложенные `effects` / `damage_entries` |
| GET | `/inventory/items/{id}` | Предмет по ID. **FEAT-171 (I3): отдаёт тонкую `PublicItemCard`** — `{id, name, description, image_url, rarity, type}`, остаётся анонимным. Жирный шаблон (все `*_modifier`, `price`, `effects`, `damage_entries`, `consumable_action`, `coating_*`) переехал на двойники: для сервисов — `GET /inventory/internal/items/{id}`, для админки — `GET /inventory/admin/items/{id}` |
| GET | `/inventory/admin/items/{id}` | **FEAT-171 (ревью #1):** полная `Item` по JWT с правом `items:read` — для редактора предметов (`ItemsAdminPage/ItemForm`) и экрана рецептов. Тело идентично internal-двойнику и тому, что `GET /inventory/items/{id}` отдавал до FEAT-171. Нужен отдельно от internal-двойника, потому что nginx закрывает префикс `/inventory/internal/` снаружи и браузер туда не попадёт. Форма читает предмет отсюда и потом шлёт `PUT /inventory/items/{id}`: на тонком теле PUT записал бы обратно значения по умолчанию и затёр бы данные предмета |
| PUT | `/inventory/items/{id}` | Обновить предмет (FEAT-165: настройки переработки, переставшие подходить к подкатегории предмета, удаляются в той же транзакции — и как у сырья, и как у результата); FEAT-168: `effects` / `damage_entries` заменяются целиком, но только если клиент их прислал) |
| GET / PUT | `/inventory/admin/items/{id}/conversions` | FEAT-165: настройки переработки сырья (`items:read` / `items:update`), PUT заменяет весь набор |
| DELETE | `/inventory/items/{id}` | Удалить предмет |
| GET | `/inventory/{id}/items?item_type=gathering_tool&category=pickaxe` | Фильтр по типу + tool_category (FEAT-128, для модалки выбора инструмента) |
| GET | `/inventory/items/bulk?ids=1,2,3` | Массовый резолв предметов (FEAT-154). **FEAT-171:** отдаёт `PublicItemCard`; поведение и тело не изменились |

### Публичная карточка предмета (FEAT-171 §3.3)

`ItemBulkResponse` повышена до **единственного публичного документа предмета** и получила алиас
`PublicItemCard`: `{id, name, description, image_url, rarity, type}` — ни цены, ни модификаторов,
ни заточки, ни вставок, ни прочности. Строится ровно одной проекцией
`schemas.public_item_card(row)` (`services/inventory-service/app/schemas.py`); любой второй
рукописный список полей — FAIL на ревью. Сейчас проекцию использует `GET /inventory/items/bulk`
(модалка паспорта персонажа), `GET /inventory/{id}/equipment/public` и
`GET /inventory/items/{id}` (Pass B, задача #8).

### Добыча ресурсов (FEAT-128)

#### Player-facing (auth required)
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/characters/{character_id}/gathering-skills` | Навыки добычи из БД (Горное дело/Травничество/Лесорубство/Собирательство), lazy-create rows на первом запросе. Видимо read-only на чужих профилях |

#### Internal (FEAT-169: `verify_internal_token` в самом сервисе, Nginx — второй слой)
Все `/inventory/internal/*` требуют заголовок `X-Internal-Token`. Fail-closed: пустой
`INTERNAL_SERVICE_TOKEN` → 503 «Internal service token не настроен», отсутствующий/неверный
заголовок → 401 «Недействительный internal token».

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/inventory/internal/characters/{cid}/fast_slots` | FEAT-169: пояс персонажа для межсервисных вызовов (battle-service снимает снапшот на старте боя). Ответ идентичен игровому маршруту; проверки владения нет намеренно — у мобов и НПС нет владельца |
| GET | `/inventory/internal/characters/{cid}/items` | **FEAT-171 (I1i):** инвентарь персонажа для межсервисных вызовов (dungeon-service). Тело идентично `GET /inventory/{cid}/items`, включая фильтры `item_type` / `category`. Проверки владения нет намеренно |
| GET | `/inventory/internal/characters/{cid}/equipment` | **FEAT-171 (I2i):** экипировка персонажа для межсервисных вызовов (battle-service: движок боя и расчёт прочности). Тело идентично `GET /inventory/{cid}/equipment` — вместе с `fast_slot_*` и `effective_damage`. Проверки владения нет намеренно — у мобов и НПС нет владельца |
| GET | `/inventory/internal/items/{item_id}` | **FEAT-171 (I3i):** полная карточка предмета (жирная `Item` со всеми `*_modifier`, `effects[]`, `damage_entries[]`) для battle-service и dungeon-service. Тело идентично сегодняшнему `GET /inventory/items/{item_id}` |
| POST | `/inventory/internal/characters/{cid}/revalidate-equipment` | Пересчёт допустимости надетого после выбора/сброса подкласса. Вызывает skills-service |
| POST | `/inventory/internal/characters/{cid}/consume_item` | Списание 1 расходника в бою. Вызывает battle-service |
| POST | `/inventory/internal/update-durability` | Прочность экипировки после боя. Вызывает battle-service |
| POST | `/inventory/internal/characters/{cid}/gathering/award` | Атомарная транзакция: SELECT FOR UPDATE на character_inventory + tool + character_gathering_skills, добавление ресурса (с обработкой full-inventory), декремент durability, добавление XP, rank-up loop. Вызывается locations-service на finalize |
| POST | `/inventory/internal/characters/{cid}/free_slots_check` | Возвращает `{free_slot_count, is_full}`. Вызывается locations-service на старте добычи (preflight) |
| GET | `/inventory/internal/characters/{cid}/xp-multiplier?buff_type=` | FEAT-168: множитель опыта по активному баффу (`{character_id, buff_type, multiplier}`), с учётом зонтичного `character_xp_bonus`. Защищён `verify_internal_token` (401 без `X-Internal-Token`), 400 на неизвестный `buff_type`, 404 если персонажа нет. Вызывают character-service и locations-service перед записью опыта персонажа |
| GET | `/inventory/internal/characters/{cid}/xp-multipliers?buff_types=a,b` | FEAT-168 #6: батч-вариант, `{character_id, multipliers: {тип: множитель}}`. Та же защита; 400 на пустой список, неизвестный тип или больше 8 типов |

## Видимость приватных данных персонажа (FEAT-171, Pass A)

`app/visibility.py` — копия общего предиката из FEAT-171 §3.1 (ещё три такие же живут в
character-service, character-attributes-service и skills-service; согласованность держится
параметризованным тестом-матрицей, а не общим пакетом):

- `can_view_private(db, character_id, user)` — 404 «Персонаж не найден», если персонажа нет
  (проверяется ПЕРВОЙ, чтобы 403 против 404 нельзя было использовать как оракул существования);
  `user_id IS NULL` (НПС/моб) → `True`; владелец → `True`; admin/moderator с разрешением
  `characters:read` → `True`; иначе `False`.
- `require_private_access(db, character_id, user)` — жёсткая обёртка, 403 «Эти данные доступны
  только владельцу персонажа».

`auth_http.get_optional_user` (+ `OAUTH2_SCHEME_OPTIONAL`) возвращает `None` вместо 401 при
отсутствующем или невалидном токене. Синхронная `def` — FastAPI уводит её в threadpool.

**Pass B (задача #8) — что закрыто в inventory-service:**

| Маршрут | Было | Стало |
|---------|------|-------|
| `GET /inventory/{id}/items` | анонимно, полный инвентарь | 403 чужому, тело владельца/админа не изменилось |
| `GET /inventory/{id}/equipment` | анонимно, вместе с поясом и цифрами | 403 чужому, тело владельца/админа не изменилось |
| `GET /inventory/{id}/equipment/public` | — | новый публичный маршрут без пояса и без цифр |
| `GET /inventory/items/{id}` | жирная `Item` анонимно | тонкая `PublicItemCard`; жирная — на internal-двойнике и на `GET /inventory/admin/items/{id}` |
| `GET /inventory/admin/items/{id}` | — | новый маршрут админки: жирная `Item` по праву `items:read` (ревью #1) |
| `GET /inventory/{id}/equipment-rules` | анонимно, у несуществующего id — 200 | остаётся анонимным (справочные данные), но несуществующий персонаж → 404 |

**`GET /inventory/{id}/equipment-rules` остаётся публичным намеренно** (FEAT-171 ревью #1,
issue 6). Это справочные данные, а не данные персонажа: весь ответ выводится из класса и
подкласса (`class_id`, `subclass_key`, списки разрешённых категорий брони и оружия), а класс с
подклассом уже публичны — их отдают `GET /characters/{id}/public`, `/short_info` и
`/characters/list`. Ни одного числа персонажа и ни одной его вещи в ответе нет, поэтому гейт был
бы строже публичной анкеты и без пользы сломал бы страницу-витрину. Выровнена только дисциплина
ошибок: несуществующий `character_id` теперь отвечает 404 «Персонаж не найден», как и остальные
character-scoped маршруты фичи, а не 200 «ограничений нет».

Не тронуты: `/inventory/items/bulk`, `/inventory/{id}/item-detail/{row}` (жирная карточка
владельца), `/inventory/characters/{id}/fast_slots`, `/inventory/{id}/active-buffs`
и весь каталог `/inventory/items` (открытость каталога — осознанное решение пользователя,
FEAT-171 §3.4 D9).

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
- **buff_type / buff_value / buff_duration_minutes** — книги опыта, **устаревшая одиночная форма**. FEAT-168: `buff_type` больше не свободная строка, а белый список из 8 типов (см. «Книги опыта»); всё остальное → 422. FEAT-168 #6: настоящий источник — таблица `item_xp_buffs`, эти колонки читаются только у предметов без строк в ней
- **consumable_action / coating_turns / coating_bonus_damage** (FEAT-168, миграция 024, все nullable): как расходник применяется в бою — NULL/`instant`, `weapon_coating` (яд на оружие, тогда `coating_turns` 1..50 и `coating_bonus_damage` 0..10000 обязательны), `cleanse`. VARCHAR, а не ENUM: изменение ENUM блокирует таблицу `items` (грабли FEAT-165)

### item_effects (FEAT-168, миграция 024)
- id, item_id (FK items CASCADE, индекс), target_side (`self`/`enemy`/`ally`/`all_allies`), effect_name, description, chance (0..100), duration (0..100), magnitude (−10000..10000), attribute_key
- Форма строки — зеркало `skill_perk_effects` из skills-service, чтобы battle-service отдавал её в `buffs.apply_new_effects` без перевода. Не больше 20 строк на предмет

### item_damage_entries (FEAT-168, миграция 024)
- id, item_id (FK items CASCADE, индекс), damage_type, amount (−10000..10000), description, weapon_slot (по умолчанию `no_weapon` — свитки считаются без оружия), target_side (по умолчанию `enemy`), chance (0..100), aoe_shape, aoe_falloff (0..100), aoe_max_targets (1..10)
- **aoe_shape** — только те формы, которые реально реализует `resolve_aoe_targets` в battle-service: `single` (одна цель), `splash` (оба соседа по строю), `cleave` (следующий), `all` (все враги), `random_n` (ещё `aoe_max_targets - 1` случайных). Любое другое значение → 422: форма, которую движок не знает, молча превратилась бы в удар по одной цели. Этот же список — кнопки в админке (`ItemEffectSections.tsx`)
- Форма строки — зеркало `skill_perk_damage`, идёт напрямую в `battle_engine.compute_damage_with_rolls`. Не больше 10 строк на предмет

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
- **Эндпоинты:** `GET/PUT/DELETE /inventory/admin/equipment-rules` (`items:read` / `items:update`), `GET /inventory/{id}/equipment-rules` — что может носить персонаж (для подсветки в инвентаре): анонимный маршрут, справочные данные по классу/подклассу; несуществующий персонаж → 404 (FEAT-171 ревью #1).

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

## Походный рюкзак (FEAT-178, миграция 028)

Плащ с `items.is_backpack = true`, надетый в слот `cloak` (`backpack.py`). Вместимость в стопках по редкости:
обычный 4, редкий 6, эпический 8, легендарный и выше 10. Упакованное лежит в `character_backpack`
(character_id, item_id, quantity) — отдельно от `character_inventory`, поэтому обмен, продажа, аукцион и крафт его
не видят. Класть можно только `consumable`.

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/inventory/{cid}/backpack` | надетый рюкзак, вместимость, содержимое, весь пояс (включая пустые слоты), `in_dungeon` |
| POST | `/inventory/{cid}/backpack/pack` `{inventory_item_id, quantity}` | из сумки в рюкзак (вне подземелья) |
| POST | `/inventory/{cid}/backpack/unpack` `{backpack_item_id, quantity}` | из рюкзака в сумку (вне подземелья) |
| POST | `/inventory/{cid}/backpack/use` `{backpack_item_id}` | вне боя: еда → сытость, книга → бафф, иначе восстановление (без него — 400 «положите на пояс») |
| POST | `/inventory/internal/characters/{cid}/backpack/add` `{item_id, quantity}` | X-Internal-Token; лидер подземелья раздаёт находки; 409 нет рюкзака/места |

В забеге (блокировка подземелья) сумка закрыта: `use_item`, `use-buff-item`/`eat-food` без `from_backpack` и
надевание на пояс из сумки — 409 «только вещи из походного рюкзака». На пояс — `equip` с `backpack_item_id`;
снятое с пояса в забеге уходит обратно в рюкзак. Рюкзак, покидающий слот плаща, высыпает содержимое в сумку; в
забеге его не снять (409).

## Кладовая дома (FEAT-180, миграция 029)

Вещи в кладовой дома игрока лежат в `house_storage` (house_id, item_id, quantity и состояние предмета:
опознан, заточка, бонусы, камни, прочность — при хранении ничего не теряется). Дом, хозяин и права жильцов —
в таблицах locations-service (`houses`, `house_plots`, `house_rooms`, `house_residents`), читаются сырым SQL
(`house_storage.py`). Вместимость — 30 стопок на каждую комнату-кладовую; простые стопки досыпаются до
`max_stack_size`, предмет с состоянием занимает свою стопку. Хозяин кладёт и берёт, жилец — как разрешил
хозяин (`can_put` / `can_take`); нужно стоять в локации дома, не быть в бою и в подземелье.

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/inventory/houses/{hid}/storage?character_id=` | права, `capacity`, `used`, `at_house`, содержимое |
| POST | `/inventory/houses/{hid}/storage/put` `{character_id, inventory_item_id, quantity}` | из сумки в кладовую (409 нет кладовой / нет места) |
| POST | `/inventory/houses/{hid}/storage/take` `{character_id, storage_item_id, quantity}` | из кладовой в сумку |

В замороженном за неуплату налога доме (`houses.status = 'frozen'`) кладовую можно только смотреть (`frozen`
в ответе, 409 на «положить/взять»), а мастерская не даёт бонуса. Изъятый дом не находится (404).
Роутер подключён раньше общего `router` (`/inventory/{character_id}/...`). Тесты: `tests/test_house_storage.py`.

### Мастерская и уровни кладовой (FEAT-180, этап 2)

`house_workshop.py` читает комнаты домов из таблиц locations-service; уровень комнаты берётся с учётом
завершившегося улучшения (`ROOM_LEVEL_SQL`). Кладовая даёт 30 / 45 / 60 стопок по уровню, комната уровня 0
(строится) — ничего. Мастерская, чья специализация совпадает с профессией персонажа, в доме, которым он
может пользоваться (хозяин или жилец, впущенный в эту комнату), в локации, где он стоит, даёт: опыт
профессии за крафт и переработку +10 / 20 / 30 %, шанс удвоения при переработке +5 / 10 / 15 п.п. по уровню.
Ответы крафта и переработки несут `workshop_level`. Тесты: `tests/test_house_workshop.py`.

### Мебель (FEAT-180, этап 3, миграция 030)

`items.item_type` получил `furniture`; новые колонки `furniture_room_type` (VARCHAR, hall/bedroom/storage/
workshop), `furniture_sleep_bonus`, `furniture_storage_stacks`, `furniture_xp_bonus_pct`,
`furniture_refine_bonus_pct`. Валидатор: комната обязательна для мебели и запрещена прочим типам; бонус
допустим только для своей комнаты (сон — спальня, стопки — кладовая, опыт и переработка — мастерская),
неотрицательный и в разумных пределах. Редкость — как у прочего не-снаряжения (до легендарной). Поставленная
мебель лежит в `house_furniture` (locations-service); `house_workshop` прибавляет её стопки к кладовой и её
проценты к мастерской.

### Дома, этап 6а (миграция 031): профильные комнаты, погреб, кухня, семена

- Мастерская теперь одна из шести профильных комнат (`house_workshop.PROFESSION_ROOM_TYPES`: forge, alchemy_lab,
  kitchen, jewelry, enchanting, study); бонус даёт комната, у которой `workshop_profession_id` совпадает с
  профессией. Бонусы уровней и мебели (группа `workshop`) прежние.
- Погреб (`cellar`) — часть кладовой дома: 50 / 75 / 100 стопок по уровню + мебель-хранилище в нём
  (`CELLAR_STACKS_BY_LEVEL`). Кладовая работает и в доме, где есть только погреб.
- Кухня: еда, съеденная, когда персонаж стоит в локации активного дома и может пользоваться построенной кухней
  (хозяин или впущенный жилец), держит сытость 30 / 36 / 48 ч вместо 24 (лучшая кухня;
  `house_workshop.kitchen_satiety_hours`). `eat-food` (и `backpack/use`, который вызывает его) передаёт
  `duration_hours` в attributes; ответ получил `satiety_hours`, сообщение — «Сытость на N ч».
- Семена: `items.seed_result_item_id`, `seed_result_quantity` (1..100), `seed_grow_hours` (1..720),
  `seed_room_type` (garden | greenhouse | apiary), `seed_herbalism_xp` (0..10000) — все заданы или все NULL,
  только у `resource` (валидатор `ItemCreate._validate_seed`). Админ-создание и правка проверяют, что
  результат существует и не равен самому семени (400). Если правка делает предмет не-ресурсом, поля семени
  обнуляются. Сажают и собирают в locations-service (`/locations/houses/rooms/{id}/plant|harvest`); урожай
  приходит через `gathering/award` (`herbalism`).

### Дома, этап 6б (миграция 032): благословения, элитные трофеи, свиток возвращения

- **Множитель опыта.** `crud.get_xp_multiplier` прибавляет (один раз за вызов, не на каждом шаге цепочки
  «тип → зонтик») `house_workshop.house_xp_bonus`: благословение библиотеки (`house_buffs`, `library` /
  `character_xp`) — к любому опыту персонажа (`character_xp_bonus` и пять частных); святилища `post_xp` — к
  `character_xp_post_bonus`, `gathering_xp` — к `gathering_xp_bonus` (`regen` — в attributes-service); трофеи —
  к `character_xp_battle_bonus`: +1 % за элитный трофей в трофейных залах активного дома, где персонаж хозяин
  или жилец (зал не больше своих мест 5/10/15, лучший дом, максимум 15 %). Истёкшие строки не считаются; нет
  таблиц (схемы тестов других фич) — 0.
- **Предметы.** `items.is_elite_trophy` — только ресурс с подкатегорией «Трофеи» (иначе 422 «Элитным может
  быть только трофей…»), `items.is_home_teleport` — только свиток (422 «Свитком возвращения домой может быть
  только свиток»). Оба в схеме предмета (создание/правка/выдача); правка, сменившая тип, сбрасывает флаг.
  Свиток возвращения крафтит мистик обычным рецептом. `use_item` его не тратит (400).
- **Свиток возвращения** (`home_teleport.py`):
  - `GET /inventory/{cid}/home-teleport/targets` (JWT, свой персонаж) → `[{house_id, name, location_id,
    location_name, circle_level, keep_chance}]` — активные дома, где персонаж хозяин или жилец, впущенный в
    построенный круг возвращения (лучший круг дома).
  - `POST /inventory/{cid}/home-teleport {inventory_item_id, house_id}` — строка сумки персонажа со свитком
    (404 / 400 «Это не свиток возвращения домой»), дом из списка целей (403), не в его локации (400 «Вы уже в
    локации этого дома»), не в блокировке (сон, чтение, подземелье…, 409), не в бою и не на добыче (400).
    Перенос — character-service `POST /characters/internal/{cid}/home-teleport {location_id}`; его 400/409
    передаются как есть, недоступность → 503/502 «Не удалось перенести персонажа — попробуйте ещё раз». Свиток
    тратится только после успешного переноса, если круг его не сохранил (`CIRCLE_KEEP_CHANCE` {1: 0, 2: 0.15,
    3: 0.30}, `home_teleport.keep_roll`). Ответ `{location_id, location_name, scroll_kept}`.
- Тесты: `tests/test_house_6b.py`.

### Дома, этап 7: присутствие в комнате

- **Кладовая**: класть и брать можно, только стоя в построенной кладовой или погребе этого дома
  (`characters.house_room_id`, ставит locations-service) — иначе 403 «Сначала перейдите в кладовую или погреб
  этого дома» (после проверок прав, заморозки, наличия кладовой и локации). В ответе кладовой — `in_storage`.
  Смотреть содержимое — как раньше (хозяин и жильцы, где угодно).
- **Мастерская**: бонус крафта и переработки даёт только профильная комната, в которой персонаж стоит
  (`_usable_rooms(..., in_room=True)`); прежние условия (активный дом в локации персонажа, хозяин или впущенный
  жилец, построена) остались.
- **Кухня** — без изменений: еда, съеденная в локации дома, где у персонажа есть доступная кухня, сытит
  30/36/48 ч по лучшей кухне (`kitchen_satiety_hours` → `duration_hours` в attributes-service), стоять в кухне не
  нужно.
- **Свиток возвращения**: у целей появился `room_id` (лучший круг дома); персонаж прибывает, стоя в нём
  (`move_home` передаёт `house_room_id` в character-service). Ответ `POST /inventory/{cid}/home-teleport` —
  `{location_id, location_name, house_id, house_room_id, scroll_kept}`.
- Тесты: `tests/test_house_storage.py`, `tests/test_house_workshop.py`, `tests/test_house_6b.py`.

## Золото: обмен и аукцион через реестр экономики (FEAT-181)

Деньги inventory-service ходят только через общий реестр (правила вызова — `docs/services/character-service.md`,
раздел «Economy ledger»). Файлы `app/econ_core.py`, `app/econ_ledger.py` (sync) и `app/tests/econ_contract_cases.py` —
**побайтовые копии** канонических файлов character-service; править их можно только там и копировать сюда (CI
`econ-contract-copies` сверяет sha256). Таблицы реестра (`econ_*`) принадлежат character-service: inventory лишь пишет в
них строки через `econ_ledger.post_operation` внутри своей транзакции. Прямых `UPDATE characters SET currency_balance`
и записи в `gold_transactions` в сервисе больше нет (`log_gold_transaction` удалён).

| Действие | op_type | Проводки | Защита от гонок |
|---|---|---|---|
| Обмен (`execute_trade`) | `trade`, ключ `trade:<id>` | инициатор → цель, цель → инициатор (одна операция) | `trade/{id}/confirm` берёт строку обмена `FOR UPDATE`; статус ставится условным `UPDATE … WHERE status IN ('pending','negotiating')` (второе выполнение → 400 «Этот обмен уже завершён или отменён»); `lock_characters` обоих; нехватка → 400 «У инициатора/второго участника недостаточно золота для обмена» |
| Ставка (`place_bid`) | `auction_bid` | ставящий → `auction_escrow`; `auction_escrow` → прежний лидер (`refund`) | лот `FOR UPDATE`; списание условное → 400 «Недостаточно …» |
| Выкуп (`execute_buyout`) | `auction_buyout`, ключ `auction_buyout:listing:<id>` | покупатель → эскроу; эскроу → прежний лидер (`refund`); эскроу → `auction_storage` 95 %; эскроу → казна региона лота (или «Казна Скитальцев») 5 % (`commission`) + налоговая нога регион → страна | лот `FOR UPDATE` |
| Истечение с победителем (`expire_stale_listings`) | `auction_settlement`, ключ `auction_settlement:listing:<id>` | эскроу → хранилище 95 %; эскроу → казна 5 % (+ налог) | истёкшие лоты `FOR UPDATE` |
| Отмена лота со ставкой | `auction_refund`, ключ `auction_refund:cancel:<id>` | эскроу → ставивший (`refund`) | лот `FOR UPDATE` |
| Получение выручки (`claim_from_storage`) | `auction_claim` | `auction_storage` → персонаж (одна операция на все выбранные записи) | записи склада `FOR UPDATE` — повторный параллельный claim ничего не находит |

- Комиссия: `AUCTION_COMMISSION_PERCENT = 5`, доля продавца `price * 95 // 100` (целочисленно, как прежний `floor`).
- `auction_listings.location_id / region_id` (миграция **033_auction_listing_region**, индекс `ix_auction_listings_region`)
  заполняются при выставлении лота по текущей локации продавца (он стоит у аукциониста) через
  `econ_ledger.resolve_location`. У старых лотов NULL → комиссия идёт в мировую казну.
- Под-инварианты: баланс счёта `auction_escrow` = Σ `current_bid` активных лотов с лидером; `auction_storage` =
  Σ `auction_storage.gold_amount`. Тесты, которые кладут строки в эти таблицы напрямую, обязаны пополнить счёт
  (`admin_emission`), как это делает genesis.
- Название валюты в уведомлениях и ошибках — из `econ_settings` (`crud.money_text` → «150 зол.»,
  `crud.not_enough_money_message` → «Недостаточно золота»), кэш 60 с.
- Тесты: `tests/test_gold_transactions.py` (проводки обмена и аукциона, инварианты после каждого сценария);
  `conftest.py` создаёт таблицы реестра и иерархии мира из `econ_contract_cases.SQLITE_DDL`.

## Быстрые слоты

- Только от экипировки: сумма `fast_slot_bonus` надетых предметов (пояс), базы нет (`BASE_FAST_SLOTS = 0`, миграция 027 привела к этому всех существующих персонажей)
- Максимум 10 слотов
- Пересчёт (`recalc_fast_slots`) при каждом equip/unequip
- При уменьшении доступных слотов: лишние предметы возвращаются в инвентарь (без проверки лимита сумки — ничего не теряется)
- В слоте лежит ровно один предмет: при надевании он списывается из сумки, в бою расходуется сам слот

`GET /inventory/internal/characters/{cid}/fast_slots` (FEAT-169; игровой близнец — `GET /inventory/characters/{cid}/fast_slots`) (FEAT-168, additive): вместе со `slot_type / item_id / quantity / name / image` слот теперь отдаёт `health/mana/energy/stamina_recovery`, `consumable_action`, `coating_turns`, `coating_bonus_damage`, `effects[]` и `damage_entries[]`. battle-service снимает с этого ответа снапшот в состояние боя на старте, поэтому у боёв, начатых до деплоя, новых ключей нет — читать только через `.get(..., default)`.

## Коммуникация

### RabbitMQ (исходящие)
- `rabbitmq_publisher` → очередь `general_notifications`: обмен (`publish_notification_sync`) и аукцион (`publish_auction_notification`) отправляют `category: "trade"` (настройки уведомлений notification-service).

### HTTP (исходящие)
- `character-attributes-service:8002` -> POST `/attributes/{id}/apply_modifiers` (при equip/unequip, заточке и вставке/извлечении у надетого предмета)
- `character-attributes-service:8002` -> POST `/attributes/{id}/recover` (при use_item)
- `character-attributes-service:8002` -> POST `/attributes/internal/{id}/satiety` (при eat-food, sync httpx, timeout 5 с; FEAT-169: с `X-Internal-Token`)
- `character-attributes-service:8002` -> POST `/attributes/cumulative_stats/increment` (накопительные характеристики для перков)
- `character-attributes-service:8002` -> POST `/attributes/internal/{id}/reconcile-perks` (после equip/unequip, sync и async варианты; FEAT-169: с `X-Internal-Token`)
- `character-service:8005` -> POST `/characters/internal/evaluate-titles` (после equip/unequip)
- `locations-service:8006` -> POST `/locations/quests/internal/auto-progress` (событие `collect` при добавлении предметов в инвентарь, `main.py`; FEAT-170: с `X-Internal-Token` из `_internal_token_headers()`, env читается в момент вызова). Ошибка проглатывается (WARNING) — забытый заголовок остановит прогресс заданий молча

### ⚠️ Правило: никаких блокирующих HTTP-вызовов в `async def` (ревью #5 FEAT-168)

inventory-service запускается **одним воркером uvicorn**. Блокирующий `httpx.post` внутри `async def`
замораживает не текущий запрос, а **весь сервис** на время вызова (до таймаута).

Это не «просто медленно». character-service, обрабатывая `evaluate-titles`, **ходит обратно сюда** за
`GET /inventory/internal/characters/{cid}/xp-multiplier`. Пока event loop заморожен, этот запрос никто не
обслуживает: у character-service срабатывает пятисекундный таймаут, срабатывает fail-open (множитель 1.0)
— и игрок молча теряет книгу опыта, за которую заплатил. Ревью #5 измерило: надевание предмета, открывающее
титул с пассивным опытом, занимало **5429 мс**, опыт начислялся 1000 вместо 2000.

Поэтому «fire-and-forget» вызовы существуют в двух вариантах:

| Вызов | Для `def` обработчиков (threadpool) | Для `async def` обработчиков |
|---|---|---|
| накопительные характеристики | `_track_cumulative_stats` | `_track_cumulative_stats_async` |
| пересчёт перков | `_reconcile_perks` | `_reconcile_perks_async` |
| пересчёт титулов | — | `_evaluate_titles_async` (только async) |

`apply_modifiers_in_attributes_service` и `recover_in_attributes_service` асинхронны с самого начала.
Оставшиеся блокирующие `httpx` в `main.py` (`_add_item_to_inventory_core`, `eat_food`, синхронные варианты
из таблицы) вызываются **только** из синхронных обработчиков, которые FastAPI выполняет в threadpool —
там блокировка event loop невозможна. `auth_http.get_current_user_via_http` тоже синхронный `def`, то есть
тоже threadpool.

Правило закреплено статическими тестами (`tests/test_outgoing_internal_headers.py`,
`TestNoBlockingHttpOnTheEventLoop`): они разбирают `main.py` в AST и падают, если блокирующий клиентский
вызов или синхронный `_track_cumulative_stats` / `_reconcile_perks` окажется внутри `async def`. Юнит-тесты
мокают HTTP-границу и **саму взаимоблокировку увидеть не могут** — поэтому проверяется форма кода, которая
делает её невозможной.

### check_not_gathering integration (FEAT-128)
Защитная проверка `is_character_gathering` (raw SQL `SELECT 1 FROM gathering_sessions WHERE character_id=:cid AND status='active' AND complete_at > NOW()`) добавлена в action-эндпоинты: `equip`, `unequip`, `craft`, `refine`, `sharpen`, `insert-gem`, `extract-gem`, `identify`, `use-buff-item`, `use_item`. Возвращает 400 «Действие заблокировано во время добычи» если у персонажа активная сессия. Зеркальный паттерн `is_character_in_battle`.

FEAT-168: `use_item` был единственным «использовать предмет» роутом без `check_not_in_battle` — проверка добавлена, в бою расходники применяются только из быстрых слотов через battle-service.

## Урон оружия (FEAT-167)

Урон оружия **не входит** в общую характеристику `character_attributes.damage`. Он считается отдельно по слоту, ровно один раз.

- `crud.compute_item_damage(item, enhancement_bonuses, gem_items, current_durability, max_durability)` — **единственный источник числа**: `items.damage_modifier` + заточка по `damage_modifier` (+1 за очко) + сумма `damage_modifier` вставленных камней/рун; `0.0`, если предмет сломан (`max_durability > 0` и `current_durability <= 0`).
- `crud.build_modifiers_dict(..., slot_type=...)` берёт значение ключа `"damage"` из `compute_item_damage` (арифметика не может разойтись) и **выбрасывает** этот ключ для слотов `main_weapon` / `additional_weapons`. `slot_type` обязателен во всех местах, где модификаторы применяются к **надетому** предмету: снятие при ревалидации, экипировка (старый и новый предмет), снятие, заточка, вставка и извлечение камня, ремонт сломанного, обнуление прочности, экипировка/снятие NPC. Без `slot_type` урон оружия снова утечёт в атрибут.
- `GET /inventory/{id}/equipment` отдаёт `effective_damage` по каждому слоту (`crud.get_equipment_slots_with_damage`): 0.0 для пустого слота, неоружейного слота и сломанного оружия. Это число читают battle-service (`fetch_weapons`) и профиль на фронтенде — одна формула на все три значения урона (основной / дополнительный / без оружия).
- Заточка и камни **на самом оружии** принадлежат этому оружию; на броне и украшениях — по-прежнему идут в `damage`.
- Одноразовый пересчёт: миграция `023_weapon_damage_backfill` вычитает фактический урон надетого оружия из `character_attributes.damage` (кламп на 0, предупреждение в лог по аномалиям, downgrade прибавляет обратно). Пишет в таблицу char-attrs намеренно — только inventory-service знает заточку, камни и прочность.

## Книги опыта (FEAT-168)

Восемь типов баффа в таблице `active_buffs` (одна строка на `(character_id, buff_type)`, upsert обновляет длительность и никогда не складывается, протухание ленивое):

| `buff_type` | Что ускоряет | Кто читает |
|---|---|---|
| `xp_bonus` | опыт профессии (семантика не менялась) | `crud.award_profession_xp` |
| `gathering_xp_bonus` | опыт сбора | `crud.award_gathering` — множитель применяется после масштабирования XP по частично влезшему стаку |
| `character_xp_bonus` | **весь** опыт персонажа (зонтичный тип) | складывается со всеми пятью типами ниже |
| `character_xp_battle_bonus` | опыт персонажа за бои / PvE | character-service `crud.add_rewards_to_character` |
| `character_xp_post_bonus` | опыт персонажа за отыгрыш (посты) | locations-service `crud.award_post_xp_and_log` |
| `character_xp_quest_bonus` | опыт персонажа за задания | locations-service `crud.add_experience` |
| `character_xp_title_bonus` | опыт персонажа за титулы (только пассивный) | character-service `crud._grant_title_xp` |
| `character_xp_pass_bonus` | опыт персонажа за боевой пропуск | battle-pass-service → `add_rewards` c `xp_source` |

`crud.get_xp_multiplier(db, character_id, buff_type="xp_bonus")` — единственная точка чтения; значение по умолчанию сохраняет поведение всех вызовов, написанных до FEAT-168. **Зонтичное правило:** для точечного источника множитель = `1.0 + value(точечный) + value(character_xp_bonus)` (таблица `schemas.XP_BUFF_PARENTS`), то есть 25 % за задания вместе с 10 % на весь опыт дают ×1.35. Сложение живёт в сервисе, а не у вызывающих. `crud.get_xp_multipliers(...)` — батч-вариант. Сообщение `use-buff-item` собирается по словарю `BUFF_TYPE_LABELS` (`main.py`), а не хардкодом «XP».

### item_xp_buffs (FEAT-168 #6, миграция 025)
- id, item_id (FK items CASCADE, индекс), buff_type (белый список выше), value (>0, ≤10.0 — доля, 0.25 = +25 %), duration_minutes (1..10080); уникальность `(item_id, buff_type)`, не больше 8 строк на предмет
- Один предмет может ускорять несколько видов опыта сразу — админка редактирует список, а не одно поле. Только `consumable`/`scroll`, не еда
- Старые колонки `items.buff_type / buff_value / buff_duration_minutes` **оставлены и по-прежнему работают**: `crud.get_item_xp_buffs` отдаёт строки таблицы, а если их нет — одну строку из старых колонок. Миграция переносит существующие книги в новую таблицу; сохранение списка из админки — **в том числе пустого** — очищает старые колонки, чтобы у предмета не было двух источников правды (иначе удаление последней строки воскрешало бы старый бафф). Клиент, который поле `xp_buffs` вообще не прислал, работает как раньше: старая тройка не трогается
- `POST /inventory/{cid}/use-buff-item` применяет все строки разом (по `apply_buff` на тип, независимые сроки); ответ сохранил старые одиночные поля и получил список `buffs`
- Откат миграции = `DROP TABLE item_xp_buffs`; старые колонки не трогались, поэтому всё, что работало до фичи, переживает откат
- **Перенос старых книг (миграция 025) фильтрует данные.** До FEAT-168 `items.buff_type` был свободной строкой, поэтому на проде могут лежать значения, которых нет в белом списке. Строка с неизвестным/пустым типом или с прибавкой не в диапазоне `0 < value <= 10` **пропускается** (старые колонки при этом не трогаются, ничего не теряется), длительность вне `1..10080` минут **обрезается** в диапазон. Каждый пропуск и каждое обрезание пишутся в лог миграции с id предмета и причиной
- **Схемы ответа (`ItemXpBuffOut`, `ItemEffectOut`, `ItemDamageOut`) намеренно не наследуют валидаторы запроса.** Иначе одна кривая строка в базе превращала бы обычное чтение `GET /inventory/items/{id}` в 500. Валидация — только на записи; чтение обязано отдавать то, что лежит в базе

## Известные проблемы

1. **Race conditions** - `with_for_update()` только в unequip, не в equip
2. **Нет composite unique constraint** на (character_id, slot_type) в equipment_slots
3. **build_modifiers_dict()** пропускает нулевые значения (может быть ошибкой)
4. **Fast slots 5-10 не полностью поддержаны** в is_item_compatible_with_slot
5. **RabbitMQ закомментирован**
6. **Нет аутентификации** на части эндпоинтов (`GET /inventory/{id}/items`, `/inventory/internal/*` кроме нового роута выдачи — защищены только через Nginx)

### Цена надевания / снятия (2026-10-16)

`/equip` в обычный слот ждёт только `cumulative_stats/increment` — тот сам пересчитывает перки и
титулы; раньше после него перки и титулы вызывались ещё раз, последовательно. Быстрый слот и
`/unequip` ждут пересчёт перков (он двигает показатели профиля), а проверка титулов идёт фоном
после ответа (`_in_background`). Локально: equip ~0,45 с → ~0,25 с.

### Правка надетого предмета (2026-10-16)

`PUT /inventory/items/{id}` считает модификаторы каждого надетого экземпляра до и после правки
(с заточкой, камнями, прочностью — как equip) и фоном отправляет разницу носителям
(`_settle_wearers`, затем пересчёт перков). Раньше разница не применялась: equip прибавлял старые
числа, unequip вычитал новые, и характеристики носителя навсегда уезжали (на проде: уязвимость к
тьме у персонажа 989, исправлена вручную).


## Блокировка активности (FEAT-175)

`check_not_activity_locked` (`main.py`, через `app/activity_lock.py`): обмен (`trade/propose`,
`trade/{id}/items`, `trade/{id}/confirm` — проверяются обе стороны) и ремёсла (`crafting/{cid}/craft`,
`sharpen`, `refine`, `insert-gem`, `extract-gem`). Инвентарь, экипировка, аукцион, изучение
рецептов, опознание и ремонт остаются доступными.

Формулировки отказа одинаковы во всех сервисах (`activity_lock.lock_message`):
«Персонаж находится в подземелье» / «Персонаж без сознания до HH:MM МСК» (для второго
участника — «Цель …», «Целевой персонаж …», «Другой участник обмена …»). Код ответа — **409**.
Колонки `characters.dungeon_session_id` / `characters.unconscious_until` пишет только
character-service; остальные сервисы читают их из общей БД (как блокировку боя). В тестах
сервисов с таблицами-зеркалами `characters` conftest по умолчанию подменяет чтение на
«не заблокирован»; настоящий запрос проверяют тесты с маркером `real_activity_lock`.
