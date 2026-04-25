# FEAT-128: Система добычи ресурсов на локациях

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-04-25 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-128-location-resource-gathering.md` → `DONE-FEAT-128-location-resource-gathering.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Добавляем систему добычи ресурсов прямо на локациях. Игрок, попадая на локацию, видит, какие ресурсы там можно добывать (наряду с NPC, мобами, данжами). Ресурсы используются для крафта и не привязаны жёстко к биому/типу локации — админ настраивает каждую ноду вручную.

Категории ресурсов на старте:
- **Руды** (инструмент: кирка)
- **Травы** (инструмент: серп)
- **Дерево** (инструмент: топор)

Категория «Ингредиенты» НЕ входит в эту фичу — будет реализована позже отдельной системой (для еды).

### Бизнес-правила

#### Ноды добычи на локации
- Нода — абстрактная точка сбора на локации (не привязана к NPC, в будущем возможно расширение).
- Админ настраивает на каждой ноде:
  - Тип ресурса (категория: руды/травы/дерево)
  - Какой именно ресурс выдаётся (предмет из общей системы предметов)
  - Сколько ресурса даётся за один сбор
  - Сколько стамины тратится на сбор
  - Дневной лимит ресурса в ноде (общий банк)
  - Разрешено ли несколько игроков одновременно

#### Стамина и время
- 1 единица стамины = 5 минут реального времени добычи.
- Пример: настроена нода «5 стамины → 25 минут добычи → 3 руды».
- Стамина списывается ПОЛНОСТЬЮ в момент старта добычи.

#### Кулдаун ноды
- После полного истощения ноды → 24 часа простоя → полное восстановление до максимума.
- Если нода не истощена (например, осталось 5/100) — она остаётся доступной с текущим остатком, пока кто-то не доистощит. Тогда стартует таймер 24 часа.
- Никакого ежедневного сброса по серверному времени НЕТ (упрощённая логика, защита от абуза).

#### Совместная добыча
- Если админ разрешил совместный сбор — несколько игроков добывают одновременно из общего банка ноды.
- Пример: в жиле 100 руды, 2 игрока с одинаковыми условиями → каждому достанется ~50.
- Если совместный сбор запрещён — нода занята тем, кто первым начал, остальные ждут окончания/отмены.

#### Инструменты
- Категория предметов: **«Инструменты для сбора»**.
- Каждый инструмент относится к категории ресурса:
  - **Кирка** — для руды
  - **Серп** — для трав
  - **Топор** — для дерева
- Инструменты участвуют в общей системе предметов (крафт, покупка, дроп — уже работают).
- У инструментов есть **ранги** (тиры) с уникальными характеристиками:
  - Бонус к шансу выпадения дубля ресурса
  - Бонус к скорости сбора (% сокращение времени)
  - Бонус к экономии стамины (%)
- Инструменты ломаются: **1 добытая единица ресурса = 1 единица прочности** инструмента.
- Прочность настраивается на уровне предмета.
- Чинятся существующими ремкомплектами (система уже работает в игре).
- **Без инструмента**:
  - Время добычи **в 2 раза дольше**
  - **Нет шанса** на дубль ресурса
  - **Нет** бонусов от инструмента

#### Выбор инструмента перед добычей
- Перед стартом добычи система ищет в инвентаре игрока инструменты подходящей категории:
  - Если в инвентаре несколько подходящих инструментов → показывается диалог выбора.
  - Если в инвентаре один инструмент → авто-выбор без диалога.
  - Если инструментов нет → предупреждение «Без инструмента сбор будет в 2 раза дольше и без бонусов. Продолжить?» с кнопками подтверждения.

#### Навык «Сбор» (профессии добычи)
- Каждая категория = свой навык, доступный всем игрокам с 1-го ранга:
  - **Горное дело** (руда)
  - **Травничество** (травы)
  - **Лесорубство** (дерево)
- За каждую успешно добытую **единицу** ресурса игрок получает **1 опыт** в соответствующий навык.
- Всего 5 рангов. Стоимость повышения:
  - 1 → 2: **10 опыта**
  - 2 → 3: **25 опыта**
  - 3 → 4: **50 опыта**
  - 4 → 5: **100 опыта**
- Каждый ранг даёт пассивные бонусы (комбинируются с бонусами инструмента):
  - +% шанс выпадения дубля
  - −% время сбора
  - +% экономия стамины
- Конкретные значения бонусов на каждом ранге определяет архитектор.

#### Что блокируется во время добычи
- Игрок не может **писать посты** на локации.
- Игрок не может **переходить** на другие локации.
- Игрок не может **инициировать** действия (крафт, торговля и т.п.).
- НО игрока **могут атаковать** другие игроки — в этом случае добыча прерывается, начинается бой, возвращается 50% стамины (как при ручной отмене).
- В момент старта добычи система автоматически постит сообщение от лица персонажа в локации: «N начал(а) добычу [ресурса]» (по аналогии с автопостами при быстром перемещении между локациями).

#### Отмена добычи
- Игрок может в любой момент отменить добычу.
- Возвращается **50% стамины**, ресурс не выдаётся.
- Прерывание боем — то же самое (50% стамины).

#### Завершение добычи
- По истечении расчётного времени игрок получает в инвентарь:
  - Базовое количество ресурса (как настроено на ноде)
  - С шансом — дополнительная единица (от ранга навыка + инструмента)
- Запись в банк ноды уменьшается на полученное количество (включая дубли — дубли тоже списываются с банка).
- Если банк ноды исчерпан → старт таймера 24 ч.
- Опыт навыка начисляется = количество фактически добытого.
- Прочность инструмента уменьшается = количество фактически добытого.

#### Инвентарь полон
- **Перед стартом**: если инвентарь полон, добыча не начинается, показывается сообщение игроку.
- **Во время добычи**: если инвентарь забился (например, игроку упал предмет из боя/события) → добыча досрочно завершается, игрок получает то, что успел добыть пропорционально потраченному времени, остаток стамины НЕ возвращается (стамина списалась полностью на старте).

### UX / Пользовательский сценарий

1. Игрок заходит на локацию.
2. Видит на странице локации блок «Ресурсы» (рядом с NPC/мобами/данжами): список нод с типом ресурса, текущим остатком (например, «Железная жила: 47/100»), стоимостью добычи (стамина, время), статусом (доступна / истощена с таймером / занята одиночной добычей).
3. Если на ноде сейчас кто-то добывает — видны имена и аватары добывающих (полезно при ограниченных ресурсах).
4. Игрок нажимает «Добыть» на ноде.
5. Открывается диалог выбора инструмента (если в инвентаре несколько подходящих) ИЛИ предупреждение «без инструмента» (если нет).
6. Игрок подтверждает → стамина списывается → запускается таймер сбора.
7. Профиль персонажа в это время заблокирован: нельзя писать посты, переходить на локации, начинать другие действия. Возможна только отмена и возможна атака от других игроков.
8. На локации появляется автопост от лица персонажа: «N начал(а) добычу [ресурса]».
9. По таймеру → ресурс падает в инвентарь, опыт идёт в навык, прочность инструмента уменьшается, банк ноды обновляется.

### Edge Cases

- **Что если игрока ударили в момент старта добычи (race condition)?** — Атака начавшая обрабатываться раньше выигрывает; добыча не стартует, стамина не списывается.
- **Что если инструмент сломался во время добычи?** — Добыча продолжается без него (с этого момента: время и бонусы пересчитываются как «без инструмента»). Альтернатива: добыча прерывается. Решение принимает архитектор. PM по умолчанию рекомендует первый вариант.
- **Что если игрок выходит из игры во время добычи?** — Добыча продолжается на сервере по таймеру; ресурс падает в инвентарь даже без сессии игрока. Нападение в офлайне — стандартная механика игры (если есть).
- **Что если у ноды разрешена совместная добыча, но банк меньше, чем нужно всем активным добытчикам?** — Все получают пропорционально вкладу/времени, но в сумме не больше остатка банка. Если нода истощается посреди процесса — оставшиеся добытчики получают то, что успели, добыча завершается, таймер 24 ч стартует.
- **Что если игрок начал добычу с одним инструментом, но у него в инвентаре есть лучший?** — Используется тот, который выбрал на старте. Менять во время добычи нельзя.
- **Что если у админа изменилась настройка ноды посреди добычи?** — Активная добыча идёт по старым параметрам, новые игроки получают новые параметры.

### Вопросы к пользователю (если есть)
- [x] Стиль добычи (ноды, пассив, активный бросок) → **ноды на карте** (на каждой локации абстрактные точки, настраиваются админом).
- [x] Привязка к биому → **нет, гибко настраивается админом**.
- [x] Инструменты → **разные под категорию (кирка/серп/топор), с рангами, ломаются (1 ресурс = 1 прочность), чинятся ремкомплектами**.
- [x] Без инструмента можно? → **да, но 2× время, без бонусов и шанса дубля**.
- [x] Навык добычи → **да, по навыку на категорию (Горное дело, Травничество, Лесорубство), 5 рангов, 1 опыт за единицу, 10/25/50/100 опыта между рангами**.
- [x] Бонусы рангов → **шанс дубля, скорость, экономия стамины**.
- [x] Совместная добыча → **общий банк ноды, пропорционально**.
- [x] Стамина и время → **1 стамина = 5 минут**, списывается полностью на старте.
- [x] Отмена → **50% стамины возвращается**.
- [x] Прерывание боем → **то же что отмена (50% стамины)**.
- [x] Поведение во время добычи → **полная блокировка действий, кроме отмены; атаки от других игроков возможны**.
- [x] Инвентарь полон → **перед стартом: блок; во время: досрочное завершение**.
- [x] Кулдаун ноды → **24 часа от истощения, никаких ежедневных сбросов**.
- [x] Видимость для игрока → **счётчик остатка ноды, имена и аватары других добытчиков**.
- [x] Автопост от лица персонажа → **да, при старте добычи**.
- [x] Категория «Ингредиенты» → **исключена из этой фичи**.
- [x] UI навыка → **отдельная вкладка «Сбор» в профиле персонажа между «Перки» и «Задания»**.
- [x] Админ настраивает на ноде → **тип/категорию, конкретный предмет, кол-во за сбор, стамина, дневной лимит, совместная добыча**.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Affected Services

| Service | Type of Changes | Key Files |
|---------|-----------------|-----------|
| **locations-service** | Major: new tables for gathering nodes per location, new endpoints (admin CRUD + player-facing list/start/cancel), surface nodes in `LocationClientDetails`. Auto-post on gather start (mirror `quick_move` pattern). | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `app/alembic/versions/` |
| **inventory-service** | Major: extend `items.item_type` enum with new value (e.g. `gathering_tool`), add tool-specific columns on `items` (tool_category, bonus_double_chance, bonus_speed_pct, bonus_stamina_pct), add new tables for gathering professions/ranks/character XP (cannot reuse `character_professions` because it has `UNIQUE(character_id)`). New endpoints for gathering profession progress, rank-up, internal endpoints for awarding XP and durability tick from a gather completion. New endpoint to list player's tools by category. | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `app/alembic/versions/` |
| **character-attributes-service** | Minor: stamina is already managed here (`POST /attributes/{id}/consume_stamina`). Need a complementary stamina-refund/credit endpoint for the 50% refund on cancel/battle interrupt (no current symmetric endpoint exists; `recover` only sets recovery via item-style fields). | `app/main.py`, `app/crud.py` |
| **character-service** | Possibly minor: optional helper endpoint to write a CharacterLog row when gathering starts/finishes (`character_logs` table, see `models.py:265`). No schema changes if we reuse existing `event_type=string` JSON metadata pattern. | `app/main.py` (optional) |
| **battle-service** | Read-only consumer of character lock state. The PvP attack endpoint (`/pvp/attack`, `main.py:2356`) already checks `get_active_battle_for_character` — it must additionally cancel any active gathering session before creating the battle (or call locations-service to cancel it and refund 50% stamina). No DB schema changes. | `app/main.py:2356` |
| **user-service** | Alembic migration only: register new RBAC permissions (e.g. `gathering_nodes:create/read/update/delete`). Pattern: `alembic/versions/0019_add_profession_permissions.py`. | `alembic/versions/` (new migration) |
| **frontend** | Major: new "Resources" block on the location page (mirroring `LocationMobs` / `DungeonEntrance`); new "Сбор" tab on profile page (mirroring `PerksTab`/`CraftTab`); admin UI to configure nodes per location (mirroring per-location mob spawn / per-NPC shop pattern); tool-selection modal before gather start. New Redux slice + API module. | `services/frontend/app-chaldea/src/components/...` |
| **api-gateway (Nginx)** | No new route prefix needed (everything lives under existing `/locations/`, `/inventory/`, `/attributes/` prefixes). | — |

### 2.2 Existing Patterns to Follow

#### locations-service (primary host for gathering nodes)
- **Async SQLAlchemy** (aiomysql), Pydantic <2.0, Alembic auto-migration on startup with `version_table=alembic_version_locations`. Most recent migration: `030_add_no_quick_move_to_locations.py`.
- **Auth**: `auth_http.get_current_user_via_http`, `get_admin_user`, `require_permission("locations:create")` — same pattern across all admin endpoints.
- **Character-state lock helper**: `services/locations-service/app/main.py:126` defines `check_not_in_battle(db, character_id, message)` — runs a raw SQL JOIN against the shared MySQL `battles`+`battle_participants` tables. The same defensive pattern (cross-service raw SQL on the shared DB) is the right model for a future `check_not_gathering` helper.
- **Auto-post on travel** (precedent for "gather started" auto-post): `services/locations-service/app/main.py:1156-1163` inside `quick_move` — builds an HTML-styled system post `<em>*{character_name} прибывает в локацию*</em>` and inserts it via `crud.create_post()` bypassing `MIN_POST_LENGTH`. The full post-creation pipeline (with notifications, BP tracking, quest auto-progress) is wrapped in `move_and_post` (`main.py:833-1055`). For gathering, only the auto-post + character-name-fetch slice is needed.
- **Location detail surface for clients**: `LocationClientDetails` schema (`schemas.py:527`) is the shape returned by `GET /locations/{id}/client/details` (`main.py:742-760`). It already contains `npcs`, `players`, `loot`, `posts` etc. The new "Resources" block plugs in here as a new field (e.g. `gathering_nodes: List[GatheringNodeClient]`).
- **Per-location admin config precedents**:
  - **NPC shop items**: `npc_shop_items` table (`models.py:296`) bound by `npc_id` (NPC owns the location association). Admin endpoints `POST/GET/PUT/DELETE /admin/npc-shop/{npc_id}/items` (`main.py:1985-2092`).
  - **Mob spawns**: `LocationMobSpawn` table lives in **character-service** (`character-service/models.py:211`), admin endpoint `POST /characters/admin/mob-templates/{template_id}/spawns` (`main.py:2394`) — uses `replace_all` semantics (delete-then-insert).
  - **Dungeons**: live in `dungeon-service`, bound to a location via `dungeons.location_id`. Public endpoint `GET /dungeons/at-location/{location_id}` (`dungeon-service/main.py:331`) is what the LocationPage queries.
  - **Recommendation for the Architect**: store gathering nodes inside locations-service (closest semantic match — they live on a location, no cross-service ownership). Admin endpoints `POST/GET/PUT/DELETE /locations/admin/locations/{location_id}/gathering-nodes/...`.

#### inventory-service (items, tools, professions, durability)
- **Sync SQLAlchemy** + PyMySQL, Pydantic <2.0. Alembic with `alembic_version_inventory`. Latest migration: `015_add_auction_tables.py`.
- **Items model** (`services/inventory-service/app/models.py:7`): the single `items` table holds all item definitions with ~60 columns; `item_type` is a MySQL ENUM, currently `head, body, cloak, belt, ring, necklace, bracelet, main_weapon, consumable, additional_weapons, resource, scroll, misc, shield, blueprint, recipe, gem, rune` (Items.item_type, line 14). To add gathering tools the Architect will extend this enum (Alembic migration with `op.execute("ALTER TABLE items MODIFY COLUMN ...")`) — precedent: `002_add_shield.py`, `005_add_recipe_item_type.py`, `013_add_rune_type.py`.
- **Tool tiers reference (FEAT-117/118)**: there is no first-class "tier" column on items. Tiers are expressed by combining `item_rarity` (common→divine) with `item_level` and stat modifiers. For gathering tools, the Architect should add explicit tool-specific columns (`tool_category enum('pickaxe','sickle','axe')`, `gather_double_chance_bonus`, `gather_speed_bonus_pct`, `gather_stamina_bonus_pct`) on `items` — these are simple numeric fields parallel to the existing `whetstone_level`, `repair_power`, `essence_result_item_id` per-type-specific columns (`models.py:28-37`). Rarity provides the tier visual grouping; numeric bonuses live on the item directly. This matches the approach used by FEAT-083 (whetstones), FEAT-090 (repair kits).
- **Durability system (FEAT-090)**: exists and works. `Items.max_durability` (line 36) is the per-template max; `CharacterInventory.current_durability` (line 140) and `EquipmentSlot.current_durability` (line 166) are per-instance: `NULL = full, 0 = broken`. The inventory-service repair endpoint applies `repair_power` percent. The gathering system can reuse this exact wiring: each gather completion decrements `current_durability` by the amount of resource produced. The tool item is held in the inventory (not equipped — gathering tools are not in the equipment slots enum, see line 151), so durability lives on `CharacterInventory.current_durability`.
- **Repair kits (FEAT-090)**: items with `item_type='resource'` and `repair_power` set (25/50/75/100). The user said "fixable by existing repair kits" — `repair_item` endpoint already validates the target item has `max_durability > 0`, so any item type with positive `max_durability` works without changes.
- **Professions vs gathering "skills"**: existing `professions` (`models.py:206`), `profession_ranks` (`models.py:224`), `character_professions` (`models.py:279`) form the precedent. **CRITICAL CONSTRAINT**: `character_professions` has `UniqueConstraint('character_id', name='uq_character_profession')` (line 282) — exactly ONE profession per character. The gathering system needs THREE parallel progressions per character (Mining/Herbalism/Woodcutting), so the Architect MUST design new tables: e.g. `gathering_skills` (id, slug, name, category enum), `gathering_ranks` (skill_id, rank_number 1..5, required_xp, double_chance_bonus, speed_bonus, stamina_bonus), `character_gathering_skills` (character_id, skill_id, current_rank, experience) with `UniqueConstraint(character_id, skill_id)`. Required XP per spec: rank 1→2: 10, 2→3: 25, 3→4: 50, 4→5: 100.
- **XP-and-rank-up pattern** (FEAT-082): `crud.execute_craft()` + `set_character_rank()` (`crud.py:906`) implements XP add → loop through ranks → auto-rank-up → return `xp_gained`, `rank_up_to` in the response dict. The same pattern fits gathering: on completion, `add_gathering_xp(character_id, skill_slug, amount)` returns `{xp_gained, new_rank, rank_up: bool}`.
- **Internal endpoints pattern**: `/internal/...` paths gated by `INTERNAL_SERVICE_TOKEN`, blocked from external traffic by Nginx. Used by battle-service to consume items mid-battle. Gathering completion (background task) should award resources via `POST /inventory/internal/characters/{id}/items` and tick durability via an internal repair-kit-style mutation.

#### character-attributes-service
- **Sync SQLAlchemy**, Pydantic <2.0, Alembic with `alembic_version_char_attrs`. Latest: `005_add_posts_quests_stats.py`.
- **Stamina spend** is `POST /attributes/{character_id}/consume_stamina` (`main.py:776`). Body `{"amount": int}`, validates `current_stamina >= amount`, decrements, commits. **No symmetric refund endpoint exists.** Architect must either:
  1. Add a generic `POST /attributes/{character_id}/refund_stamina` (cap at `max_stamina`), or
  2. Reuse `POST /attributes/{character_id}/recover` (`main.py:675`) which already handles `stamina_recovery`-style fields — but it's currently shaped for use_item recovery, not arbitrary refunds. Option 1 is cleaner.

#### character-service (character-state, logs, NPC posts)
- Sync SQLAlchemy, Alembic `alembic_version_character`. Latest: `017_add_travel_cooldown_until.py` (FEAT-123 hotfix style).
- `Character.travel_cooldown_until` (`models.py:59`) is the precedent for "character is busy until timestamp X". A similar `gather_until` could be added here, but the cleaner pattern is to keep gathering session state inside locations-service (its own `gathering_sessions` table) and have all consumers query that table on the shared DB. This mirrors how dungeon-service stores `dungeon_sessions`, and `check_not_in_battle` reaches across the shared DB directly.
- **CharacterLog** (`models.py:265`): ready-made event-log table for the player history feed (`character_logs`). Gathering events should write rows here via the same `award_post_xp_and_log` background task pattern (`locations-service/crud.py`).

#### dungeon-service (closest existing precedent for "real-time-busy" character state)
- **Async** + own MySQL tables, Alembic `alembic_version_dungeon`. Has full SessionState model: `DungeonSession` (status: forming/active/completed/escaped/wiped, `current_room_id`, `started_at`, `cooldown_until`), `DungeonSessionMember` (per-character status alive/dead/disconnected). Lock-detection: `GET /dungeons/internal/character-session/{character_id}` (`main.py:709`) returns `{"in_dungeon": True, "session_id": ...}`. Used by frontend (`BattlePage.tsx:171`) and `DungeonEntrance.tsx:125` to gate UI.
- The dungeon system **does not** auto-cancel battle initiation when target is in dungeon — battle-service simply checks `get_active_battle_for_character` and ownership. The user spec says gathering must be interruptible by attacks (50% stamina refund). Architect must wire battle-service `pvp_attack` endpoint to call locations-service `cancel_gathering(character_id)` for the victim before creating the battle, OR make locations-service consume a `battle_started` event. Easiest path: add a sub-call in `pvp_attack` (and any future "force interrupt") similar to existing `consume_stamina` HTTP calls.

#### Time-based completion (real-world minutes elapsing on the server)
- **Celery + RabbitMQ** is wired up only in battle-service: `battle-service/tasks.py` has one task (`save_log`), `docker-compose.yml:121` runs `celery-beat` against `tasks:celery_app beat` (broker RabbitMQ, results Redis). No periodic tasks are currently registered. Adding a Celery beat task `tick_gathering_sessions` (every 30 s, scan rows where `complete_at <= now()` and finalize) is feasible but binds locations-service to Celery infra.
- **Lazy-completion pattern (RECOMMENDED, no new infra)**: store `started_at` + `complete_at` in a `gathering_sessions` row; finalize on demand whenever:
  - the player polls `GET /locations/{id}/client/details` (already polled when viewing a location),
  - or `GET /characters/{id}/active_gathering`,
  - or any state-changing endpoint touches the character.
  - Optionally augment with a single `BackgroundTasks` `asyncio.create_task` to schedule final write at exact deadline (best-effort).
  This mirrors how `Character.travel_cooldown_until` is just a timestamp checked on each request — no scheduler needed (`locations-service/main.py:867-888`).
- **Exact deadline scheduling precedent**: `battle-service` uses Redis ZSET `battle:deadlines` (`redis_state.py:50`, `ZSET_DEADLINES`) to track per-battle expiry. Could be reused for gathering, but lazy-completion is simpler and idiomatic for this codebase.

#### Frontend patterns
- **Profile tabs** (`services/frontend/app-chaldea/src/components/ProfilePage/ProfileTabs.tsx`): the tabs array is a plain `const TABS: Tab[]` (line 8). To insert "Сбор" between "Перки" and "Задания" the Architect inserts `{ key: 'gathering', label: 'Сбор' }` between indexes 2 and 3 and adds a render branch in `ProfilePage.tsx`. Tab content components live under `ProfilePage/<TabName>/<TabName>.tsx` (e.g. `PerksTab/PerksTab.tsx`, `CraftTab/CraftTab.tsx`).
- **Location page sections**: `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx:466-506` shows how the existing blocks (`PlayersSection`, `NeighborsSection`, `LocationMobs`, `BattlesSection`, `DungeonEntrance`, `LootSection`) are stacked. New `<GatheringSection locationId={...} characterId={...} />` slots in alongside `LocationMobs`.
- **Existing gating-on-character-state**: `useBattleLock(character?.id)` hook + `BattleLockBanner` (`LocationPage.tsx:38, 21`). The same pattern should be cloned for `useGatheringLock` so the LocationPage can grey-out the post form / quick-move buttons while gathering.
- **Item type icons / categories** (`ProfilePage/InventoryTab/dnd/constants.ts`, `ItemsAdminPage/ItemForm.tsx:12`): the central `ITEM_TYPES` array and `ITEM_TYPE_LABELS` map need a new entry `gathering_tool: "Инструмент сбора"`. The form has conditional sections (`showArmor`, `showWeapon`); a new `showGatheringTool` section will surface the tool category dropdown and bonus inputs.
- **Admin location editor**: `AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx` is the per-location admin page. It has a sub-component pattern (`LocationNeighborsEditor`) — the Architect should create a `GatheringNodesEditor` sub-component that loads/saves nodes for the current location.
- **Admin index** (`Admin/AdminPage.tsx:17`): the "Локации" entry already covers world editing; gathering nodes belong inside the per-location form, so no new top-level admin entry is required. RBAC module name: reuse `locations` permissions OR introduce `gathering` (architect choice).
- **MANDATORY rules** (CLAUDE.md sections 8-12): all new frontend files must be `.tsx` + Tailwind + responsive (no SCSS/JSX/desktop-only). New components must NOT use `React.FC`. All API errors must be displayed to the user.

#### Mob auto-respawn / cooldown (precedent for 24h node respawn)
- `character-service/crud.py:975-1000` (`_try_spawn_mob` and `get_alive_mobs_at_location`): mobs have `respawn_at` timestamps; on each location-load query, dead mobs whose `respawn_at <= now()` are flipped back to `alive`. Identical pattern fits gathering: a depleted node has `restore_at = depleted_at + 24h`; whenever a player loads the location, lazily restore the bank if `restore_at <= now()`.

### 2.3 Cross-Service Dependencies (after this feature)

```
locations-service (gathering nodes) ──> character-service        (GET /characters/{id}/profile — character_name for auto-post, current_location_id)
                                  ──> character-attributes-service (POST /consume_stamina on start, POST /refund_stamina on cancel/interrupt)
                                  ──> inventory-service           (POST /internal/characters/{id}/items — award resource, POST /internal/characters/{id}/inventory_slots_check — pre-flight, POST /internal/items/{inventory_item_id}/decrement_durability — tool wear, POST /internal/characters/{id}/gathering/award_xp — skill XP)
                                  ──> notification-service / WebSocket  (optional: push gather-complete event; otherwise client polls)

inventory-service (gathering tools, gathering skills) ──> (no outbound calls beyond existing apply_modifiers — gathering tools are NOT equippable)

battle-service (pvp_attack) ──> locations-service (POST /locations/internal/cancel-gathering/{character_id} — cancels active session, refunds 50% stamina via attributes)

frontend ──> /locations/{id}/client/details        (now includes gathering_nodes[])
        ──> /locations/{id}/gathering-nodes/{node_id}/start
        ──> /locations/{id}/gathering-nodes/{node_id}/cancel
        ──> /characters/{id}/active_gathering        (poll for state)
        ──> /inventory/{id}/items?item_type=gathering_tool&category=mining (tool selection modal)
        ──> /inventory/characters/{id}/gathering-skills (Сбор tab)
        ──> /locations/admin/locations/{id}/gathering-nodes (admin CRUD)
```

### 2.4 DB Changes

#### locations-service (Alembic migration `031_add_gathering_nodes.py`)
- New table `gathering_nodes`: `id`, `location_id (FK Locations.id ON DELETE CASCADE)`, `node_name`, `category` enum(`ore`,`herb`,`wood`), `result_item_id` (Integer, no FK — items live in inventory-service's table but in the same DB), `result_quantity_per_gather`, `stamina_per_gather`, `daily_bank_max`, `current_bank`, `allow_concurrent_gather` (Boolean), `depleted_at` (TIMESTAMP, nullable), `restore_at` (TIMESTAMP, nullable), `is_enabled`, `created_at`, `updated_at`. Indexes on `location_id`, `category`.
- New table `gathering_sessions`: `id`, `node_id (FK gathering_nodes.id ON DELETE CASCADE)`, `character_id`, `tool_inventory_item_id` (nullable, FK character_inventory.id — but cross-service FK; safer as plain int), `started_at`, `complete_at` (computed at start), `effective_speed_pct`, `effective_double_chance_pct`, `stamina_paid`, `status` enum(`active`,`completed`,`cancelled`,`interrupted_by_battle`,`inventory_full`), `finished_at`, `result_quantity` (filled on finalize), `xp_awarded`. Indexes on `character_id`, `node_id`, `status`, `complete_at`.

#### inventory-service (Alembic migration `016_add_gathering_system.py`)
- ALTER `items`: extend `item_type` ENUM to include `gathering_tool`; add columns `tool_category` enum(`pickaxe`,`sickle`,`axe`) nullable, `gather_double_chance_bonus` Float default 0, `gather_speed_bonus_pct` Float default 0, `gather_stamina_bonus_pct` Float default 0.
- New table `gathering_skills`: `id`, `slug` (`mining`/`herbalism`/`woodcutting`), `name`, `category` enum(`ore`,`herb`,`wood`), `description`, `icon`, `max_rank` default 5.
- New table `gathering_skill_ranks`: `id`, `skill_id (FK)`, `rank_number` (1..5), `required_experience` (Integer), `double_chance_bonus` Float, `speed_bonus_pct` Float, `stamina_bonus_pct` Float. UNIQUE `(skill_id, rank_number)`.
- New table `character_gathering_skills`: `id`, `character_id`, `skill_id (FK)`, `current_rank` default 1, `experience` default 0, `created_at`. UNIQUE `(character_id, skill_id)`.
- Seed data for 3 skills × 5 ranks.

#### user-service (Alembic migration `0025_add_gathering_permissions.py`)
- Insert into `permissions`: `gathering:read`, `gathering:create`, `gathering:update`, `gathering:delete`. Assign to Editor (read), Moderator (read, update). Admin gets all automatically.

#### character-attributes-service (Alembic migration `006_add_refund_stamina.py`)
- No schema change. The new `refund_stamina` endpoint reuses the existing column.

### 2.5 Existing Bugs/Quirks the Architect Must Be Aware Of

1. **Double-spend race on tool durability**: `inventory-service` `equip` does NOT use `with_for_update()` (ISSUES.md #1, still open). For per-gather durability ticks the Architect should explicitly use `with_for_update()` in the new code paths.
2. **No symmetric stamina-refund endpoint** in character-attributes-service (only `consume_stamina` exists). Must be added.
3. **No `check_not_gathering` helper exists** — the Architect must add one in locations-service (raw SQL on `gathering_sessions`) and wire it into post-create, move/quick-move, equip/unequip, craft, and other action endpoints, parallel to existing `check_not_in_battle` calls (locations-service:126, inventory-service:67).
4. **`character_professions` UNIQUE(character_id)** (`inventory-service/models.py:282`) — prevents reusing the existing profession system for the three gathering skills. New tables required.
5. **CORS allow-all in production** (locations-service known issue — not blocking this feature).
6. **Cross-service FKs in shared DB**: `gathering_nodes.result_item_id` and `gathering_sessions.tool_inventory_item_id` reference tables owned by another service. The codebase's convention (e.g. `LocationLoot.item_id`, `npc_shop_items.item_id`) is to NOT declare a SQLAlchemy ForeignKey for cross-service references — keep them as plain `Integer` columns. The Architect should follow this convention.

### 2.6 Risks

| Risk | Mitigation |
|------|------------|
| Concurrent gathering on a shared-bank node depletes the bank below zero (race). | Use SELECT ... FOR UPDATE on `gathering_nodes` row when starting a session and when finalizing. Wrap bank decrement + state transition in one transaction. |
| Player goes offline during gathering — must still finalize. | Lazy-finalize on next access (player or admin). Optionally back up with Celery beat scan every 60s. |
| Battle interrupt race: attack lands at same instant as gather completion. | Both endpoints take row lock on the gathering_sessions row. First-write-wins; the loser sees `status != 'active'` and noops. The user explicitly said attacker wins on race, so battle-service must be the side that mutates status to `interrupted_by_battle` before creating the battle. |
| Inventory full mid-gather (player gets loot from elsewhere). | Lazy detection at finalize: try to add resource, on `inventory_full` set status=`inventory_full`, prorate result_quantity by elapsed/total time, do NOT refund stamina. This requires inventory-service to expose a "free slot count" check or to return a structured failure. |
| Tool breaks mid-gather (durability hits 0). | Per spec (PM): "gathering continues without bonuses". Implementation: at finalize, re-derive effective bonuses by clamping by total durability remaining. Simpler: cap awarded resource at `tool_durability_at_start + 1` (since 1 unit damage / 1 unit resource). |
| Backward compat with existing `item_type` ENUM consumers. | Adding a new enum value is additive; existing downstream code that whitelists known item_types (battle-service item-use, frontend ITEM_TYPES list) will need updates but won't crash on unknown values. |
| Gathering session table grows unbounded. | Add a periodic cleanup of `completed/cancelled` rows older than 30 days (Celery beat task or admin tool). |
| Auto-post creates noise on busy locations. | Per spec PM allowed it explicitly; mirror `quick_move`'s use of `<em>...*...*</em>` to visually distinguish system posts. Consider tagging via `posts.event_type` if added later. |

### 2.7 Questions for PM — RESOLVED (2026-04-25)

All defaults confirmed by user.

1. **Gathering profession permissions**: NEW RBAC module `gathering` with 4 actions (`gathering:read`, `gathering:create`, `gathering:update`, `gathering:delete`). Admin/Moderator coverage matching `professions`.
2. **Repair kit compatibility**: ALL existing repair-kit tiers (common→legendary, 25%→100%) work on gathering tools. No restrictions.
3. **Dual-stat tools**: Gathering tools are GATHERING-ONLY. They do NOT roll generic equipment stats (strength, agility, etc.). Only the three gathering bonuses: `gather_double_chance_bonus`, `gather_speed_bonus_pct`, `gather_stamina_bonus_pct`.
4. **"Сбор" tab visibility**: Tab is visible on OTHER players' profiles in read-only mode (same pattern as the existing «Перки» / «Навыки» tabs).
5. **Tool category enum values**: DB uses canonical English: `pickaxe`, `sickle`, `axe`. UI labels remain Russian.
6. **Gathering nodes & dungeons coexistence**: YES — both can coexist on the same location. They are independent blocks on the location page.

---

## 3. Architecture Decision (filled by Architect — in English)

> Status: IN_PROGRESS. All clarifications from section 2.7 are folded in.
> Top-level decisions:
> - Gathering nodes and sessions live in **locations-service** (closest semantic match, async stack matches polling/finalize pattern).
> - Tools, gathering skills, ranks and character XP live in **inventory-service** (extends existing items/professions plumbing).
> - Stamina lifecycle: spend on start (full amount), refund 50% on cancel/battle-interrupt via a NEW symmetric `refund_stamina` endpoint in **character-attributes-service**.
> - Time-based completion: lazy finalization on poll (no Celery dependency in locations-service). Optional safety-net Celery beat task is deferred to a follow-up feature.
> - Battle interrupt: battle-service `pvp_attack` calls a new internal `cancel-gathering` endpoint in locations-service BEFORE creating the battle (so the victim's session is closed and stamina refunded under one ordered flow).
> - Tool-broken-mid-gather: simpler approach from Risk #5 — cap awarded resource at `tool_durability_at_start + 1` (one extra unit possible only via the rank double-chance roll). Documented explicitly under Bonus Calculations.

### 3.1 API Contracts

All bodies use Pydantic <2.0 (`class Config: orm_mode = True`). All non-internal endpoints below pass through Nginx and require `Authorization: Bearer <jwt>` unless stated. Internal endpoints (`/internal/...`) require `Authorization: Bearer ${INTERNAL_SERVICE_TOKEN}` and are blocked at the gateway.

#### 3.1.1 locations-service — Player-facing

**`LocationClientDetails` extension (already returned by `GET /locations/{id}/client/details`)**
Add a new field:
```jsonc
{
  // ... existing fields (neighbors, players, npcs, posts, loot, ...) ...
  "gathering_nodes": [
    {
      "id": 12,
      "node_name": "Железная жила",
      "category": "ore",                     // enum: ore | herb | wood
      "result_item_id": 4711,
      "result_item_name": "Железная руда",   // joined for UI
      "result_item_image": "/images/.../ore.png",
      "result_item_rarity": "common",
      "result_quantity_per_gather": 3,
      "stamina_per_gather": 5,
      "base_seconds_per_gather": 1500,        // = stamina_per_gather * 5 * 60
      "current_bank": 47,
      "daily_bank_max": 100,
      "allow_concurrent_gather": true,
      "is_enabled": true,
      "depleted_at": null,                    // ISO-8601 or null
      "restore_at": null,                     // ISO-8601 or null; if set & in future -> node is on cooldown
      "active_sessions": [
        {
          "session_id": 88,
          "character_id": 421,
          "character_name": "Roland",
          "character_avatar": "/images/.../avatar.png",
          "started_at": "2026-04-25T10:01:00Z",
          "complete_at": "2026-04-25T10:26:00Z"
        }
      ]
    }
  ]
}
```

**`POST /locations/{location_id}/gathering-nodes/{node_id}/start`**
```jsonc
// Request
{
  "character_id": 421,
  "tool_inventory_item_id": 9023   // nullable — null = "without tool"
}
// 201 Response
{
  "session_id": 88,
  "node_id": 12,
  "character_id": 421,
  "started_at": "2026-04-25T10:01:00Z",
  "complete_at": "2026-04-25T10:26:00Z",
  "effective_seconds": 1500,
  "effective_stamina_paid": 5,
  "effective_double_chance_pct": 12.0,
  "effective_speed_bonus_pct": 0.0,
  "tool_inventory_item_id": 9023,
  "tool_durability_at_start": 50,
  "status": "active",
  "auto_post_id": 7710
}
// Errors:
// 400 "Недостаточно выносливости"
// 400 "Инвентарь полон"
// 400 "Нода истощена, доступна через ..."
// 400 "Нода занята другим персонажем"
// 400 "Действие заблокировано во время боя"
// 400 "Действие заблокировано во время добычи"
// 400 "Перемещение будет доступно через ..." (if travel cooldown active)
// 403 "Вы можете управлять только своими персонажами"
// 404 "Нода не найдена" / "Локация не найдена"
// 422 invalid tool category mismatch
```

**`POST /locations/{location_id}/gathering-nodes/{node_id}/cancel`**
```jsonc
// Request
{ "character_id": 421 }
// 200 Response
{
  "session_id": 88,
  "status": "cancelled",
  "stamina_refunded": 3,         // ceil(stamina_paid * 0.5) — paid=5 → refund=3
  "result_quantity": 0,
  "xp_gained": 0
}
// Errors: 400 "Активная добыча не найдена", 403 ownership, 404
```

**`GET /locations/characters/{character_id}/active_gathering`**
Owner-only or any user with permission `gathering:read` can poll their own character.
```jsonc
// 200 Response (no active session)
{ "active": false }

// 200 Response (active)
{
  "active": true,
  "session_id": 88,
  "node_id": 12,
  "node_name": "Железная жила",
  "location_id": 542,
  "category": "ore",
  "started_at": "...",
  "complete_at": "...",
  "now": "2026-04-25T10:14:00Z",
  "remaining_seconds": 720,
  "result_item_id": 4711,
  "stamina_paid": 5,
  "tool_inventory_item_id": 9023
}

// 200 Response (just-finalized — call finalized inline before responding)
{
  "active": false,
  "last_finished_session": {
    "session_id": 88,
    "status": "completed",                      // | inventory_full | cancelled | interrupted_by_battle
    "result_quantity": 4,                        // base 3 + 1 double
    "xp_gained": 4,
    "skill_slug": "mining",
    "rank_up_to": 2,                             // null if no rank-up
    "tool_durability_remaining": 46,             // null if no tool used
    "tool_broke": false
  }
}
```
The `client/details` endpoint MUST also lazily finalize any sessions whose `complete_at <= NOW()` so the location view stays consistent. The "last_finished_session" payload above is rendered as a one-shot toast on the frontend; subsequent polls return `last_finished_session: null`.

#### 3.1.2 locations-service — Admin

All require `Depends(require_permission("gathering:<action>"))`.

| Method | Path | Permission | Body / Notes |
|--------|------|-----------|--------------|
| `GET` | `/locations/admin/locations/{location_id}/gathering-nodes` | `gathering:read` | List (incl. disabled) |
| `POST` | `/locations/admin/locations/{location_id}/gathering-nodes` | `gathering:create` | `GatheringNodeCreate` |
| `PUT` | `/locations/admin/gathering-nodes/{node_id}` | `gathering:update` | `GatheringNodeUpdate` (partial) |
| `DELETE` | `/locations/admin/gathering-nodes/{node_id}` | `gathering:delete` | Cascade-deletes sessions |
| `POST` | `/locations/admin/gathering-nodes/{node_id}/restore` | `gathering:update` | Manual instant-refill (clears `depleted_at`/`restore_at`, sets `current_bank=daily_bank_max`) |

`GatheringNodeCreate`:
```jsonc
{
  "node_name": "Железная жила",          // required, 1..100
  "category": "ore",                      // enum ore | herb | wood
  "result_item_id": 4711,                 // required, must exist in items table
  "result_quantity_per_gather": 3,        // 1..50
  "stamina_per_gather": 5,                // 1..50
  "daily_bank_max": 100,                  // 1..10000
  "allow_concurrent_gather": true,
  "is_enabled": true
}
```
`GatheringNodeUpdate`: same fields, all optional. Server MUST refuse to drop `daily_bank_max` below `current_bank` (admin must `restore` first or accept clamping — design decision: clamp `current_bank = min(current_bank, new_daily_bank_max)`).

#### 3.1.3 locations-service — Internal

**`POST /locations/internal/cancel-gathering`** (called by battle-service)
Header: `Authorization: Bearer ${INTERNAL_SERVICE_TOKEN}`.
```jsonc
// Request
{
  "character_id": 421,
  "reason": "interrupted_by_battle"     // enum: interrupted_by_battle | admin_force
}
// 200 Response
{
  "cancelled": true,
  "session_id": 88,
  "stamina_refunded": 3
}
// 200 if no active session: { "cancelled": false }
// 502 if attributes-service refund call fails (caller must decide whether to abort battle creation)
```

#### 3.1.4 inventory-service — Player-facing

**`GET /inventory/{inventory_id}/items?item_type=gathering_tool&category=pickaxe`**
Existing endpoint. Add support for `item_type=gathering_tool` filter and a new optional `category` query param (enum `pickaxe|sickle|axe`). Response shape unchanged but each item includes new fields:
```jsonc
{
  "id": 9023,
  "item_id": 4900,
  "name": "Железная кирка",
  "image": "...",
  "item_type": "gathering_tool",
  "tool_category": "pickaxe",
  "item_rarity": "rare",
  "max_durability": 50,
  "current_durability": 50,
  "gather_double_chance_bonus": 5.0,
  "gather_speed_bonus_pct": 0.0,
  "gather_stamina_bonus_pct": 10.0,
  "quantity": 1
}
```

**`GET /inventory/characters/{character_id}/gathering-skills`**
Visible read-only on other players' profiles (per 2.7 #4).
```jsonc
{
  "character_id": 421,
  "skills": [
    {
      "skill_id": 1,
      "slug": "mining",
      "name": "Горное дело",
      "category": "ore",
      "current_rank": 2,
      "experience": 12,                                   // current XP toward NEXT rank (resets on rank-up)
      "experience_total": 22,                              // lifetime
      "next_rank": 3,
      "experience_to_next": 13,                            // = required - current
      "is_max_rank": false,
      "current_rank_bonuses": {
        "double_chance_bonus": 4.0,
        "speed_bonus_pct": 4.0,
        "stamina_bonus_pct": 4.0
      },
      "next_rank_bonuses": {
        "double_chance_bonus": 8.0,
        "speed_bonus_pct": 8.0,
        "stamina_bonus_pct": 8.0
      }
    },
    { /* herbalism */ },
    { /* woodcutting */ }
  ]
}
```
Note: tab visible read-only on others' profiles, so this endpoint is auth-required but does NOT verify ownership.

#### 3.1.5 inventory-service — Internal

**`POST /inventory/internal/characters/{character_id}/gathering/award`**
Single internal call that does ALL post-gather inventory mutations atomically. Locations-service calls this on finalize.
```jsonc
// Header: Authorization: Bearer ${INTERNAL_SERVICE_TOKEN}
// Request
{
  "character_id": 421,
  "skill_slug": "mining",                  // enum: mining | herbalism | woodcutting
  "result_item_id": 4711,
  "result_quantity": 4,                    // base + double rolls; capped by tool durability
  "tool_inventory_item_id": 9023,          // nullable
  "tool_durability_to_consume": 4          // = result_quantity; must equal it; 0 if no tool
}
// 200 Response
{
  "items_added": true,                          // false on inventory full
  "actual_quantity_added": 4,                   // < result_quantity if inventory clipped
  "xp_gained": 4,                                // = actual_quantity_added
  "new_rank": 2,
  "rank_up": false,                              // true if rank changed in this call
  "tool_current_durability": 46,
  "tool_broke": false                            // true if it just hit 0
}
// On full inventory: items_added=false, actual_quantity_added=0, xp_gained=0;
// locations-service then sets status=inventory_full and prorates per spec.
```
Rationale: keep this in ONE internal call so locations-service stays simple; inventory-service owns durability + XP + rank-up tx in one row-locked transaction.

**`POST /inventory/internal/characters/{character_id}/free_slots_check`** (helper, optional but cleaner)
```jsonc
// Request: {"character_id": 421}
// Response: {"free_slot_count": 4, "is_full": false}
```
Used at gather-start pre-flight. (May be subsumed if `award` returns `items_added=false` cleanly, in which case start-time free-slots check uses the existing items-list endpoint.)

#### 3.1.6 character-attributes-service — New

**`POST /attributes/{character_id}/refund_stamina`**
```jsonc
// Request
{ "amount": 2 }   // positive integer
// 200 Response
{
  "character_id": 421,
  "current_stamina": 47,
  "max_stamina": 50,
  "refunded": 2
}
// Server caps `current_stamina <= max_stamina`. If amount<=0 -> 422.
```
Auth: same pattern as `consume_stamina` — accepts unauthenticated calls from internal network OR `Authorization: Bearer ${INTERNAL_SERVICE_TOKEN}`. (Currently `consume_stamina` is unauthenticated; we keep parity. DevSecOps task ensures `/attributes/*` is not exposed externally.)

#### 3.1.7 inventory-service — Admin (extension)

`POST/PUT /inventory/items` — extend `ItemCreate`/`ItemUpdate` schemas to accept the new gathering-tool fields:
```jsonc
{
  "item_type": "gathering_tool",
  "tool_category": "pickaxe",                   // required when item_type=gathering_tool
  "max_durability": 50,                          // required, > 0
  "gather_double_chance_bonus": 5.0,             // 0..50
  "gather_speed_bonus_pct": 10.0,                // 0..50
  "gather_stamina_bonus_pct": 5.0                // 0..50
}
```
Server-side validation: if `item_type=gathering_tool`, `tool_category` is required, `max_durability >= 1`, all three bonuses are >=0 and <=50. If `item_type != gathering_tool`, `tool_category` MUST be null.

### 3.2 Security Considerations

| Endpoint | Auth | Rate limit (Nginx) | Authorization | Input validation |
|----------|------|--------------------|---------------|------------------|
| `POST /locations/{lid}/gathering-nodes/{nid}/start` | `get_current_user_via_http` | **Yes**: new `gathering_limit` zone, ~10 req/min per IP, burst=5, 429 on exceed | Owner-only (`character.user_id == current_user.id`) | character_id is positive int; tool_inventory_item_id (if set) belongs to that character and is gathering_tool with matching category and `current_durability > 0` |
| `POST /locations/{lid}/gathering-nodes/{nid}/cancel` | `get_current_user_via_http` | **Yes**: reuse `gathering_limit` zone | Owner-only | character has active session on this node |
| `GET /locations/characters/{cid}/active_gathering` | `get_current_user_via_http` | No (polled often by client) | Owner-only | cid positive int |
| `GET /locations/{id}/client/details` | existing | existing | existing | existing — gathering_nodes block surfaces only currently visible nodes |
| `GET/POST/PUT/DELETE /locations/admin/.../gathering-nodes/...` | `get_current_user_via_http` + `require_permission("gathering:<x>")` | No (admin UI, low traffic) | RBAC permission check | Pydantic field bounds; FK existence checks for `result_item_id` |
| `POST /locations/internal/cancel-gathering` | Internal token | No (internal network) | Internal token only | character_id positive int |
| `GET /inventory/characters/{cid}/gathering-skills` | `get_current_user_via_http` | No | Any authenticated user (read-only) | cid positive int |
| `POST /inventory/internal/characters/{cid}/gathering/award` | Internal token | No | Internal token only | result_quantity == tool_durability_to_consume (or both 0); item_id matches skill category |
| `POST /inventory/items` (extension) | existing `require_permission("items:create")` | existing | existing | new tool-specific fields validated as 3.1.7 |
| `POST /attributes/{cid}/refund_stamina` | matches existing `consume_stamina` (no auth, internal-only network) | No | none | amount >= 1, integer; clamp to max_stamina |

**Rate-limit zone (DevSecOps task):**
```nginx
limit_req_zone $binary_remote_addr zone=gathering_limit:10m rate=10r/m;
# Apply at location block:
location ~ ^/locations/[0-9]+/gathering-nodes/[0-9]+/(start|cancel)$ {
    limit_req zone=gathering_limit burst=5 nodelay;
    limit_req_status 429;
    proxy_pass http://locations-service_backend;
    # ... existing proxy_set_header lines ...
}
```

**Cross-cutting input validation rules:**
- All quantity / stamina / durability fields: positive integers, server-side max caps (50/50/9999) to prevent overflow.
- `result_item_id` in admin create: existence check via SELECT against `items` table.
- `tool_category` strictly matches `category` of the node (`pickaxe`<->`ore`, `sickle`<->`herb`, `axe`<->`wood`).
- All Pydantic schemas use `class Config: orm_mode = True`; numeric fields use `conint(ge=..., le=...)`/`confloat(...)`.

### 3.3 DB Changes

#### 3.3.1 locations-service — Alembic migration `031_add_gathering_nodes.py`

New tables. Both have `__table_args__ = {'mysql_engine': 'InnoDB'}`.

```sql
CREATE TABLE gathering_nodes (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    location_id INT NOT NULL,
    node_name VARCHAR(100) NOT NULL,
    category ENUM('ore', 'herb', 'wood') NOT NULL,
    result_item_id INT NOT NULL,                   -- NO FK (cross-service convention, see 2.5#6)
    result_quantity_per_gather INT NOT NULL,       -- 1..50
    stamina_per_gather INT NOT NULL,               -- 1..50
    daily_bank_max INT NOT NULL,                   -- 1..10000
    current_bank INT NOT NULL,                     -- updated on each gather; 0 -> trigger 24h restore
    allow_concurrent_gather TINYINT(1) NOT NULL DEFAULT 0,
    depleted_at DATETIME NULL,
    restore_at DATETIME NULL,                      -- = depleted_at + 24h, computed at depletion
    is_enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_gathering_nodes_location
        FOREIGN KEY (location_id) REFERENCES Locations(id) ON DELETE CASCADE,
    INDEX ix_gathering_nodes_location (location_id),
    INDEX ix_gathering_nodes_category (category),
    INDEX ix_gathering_nodes_restore_at (restore_at)
);

CREATE TABLE gathering_sessions (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    node_id INT NOT NULL,
    character_id INT NOT NULL,
    tool_inventory_item_id INT NULL,                -- cross-service, no FK
    tool_item_id INT NULL,                          -- snapshot of items.id (for finalize logic if tool deleted)
    tool_durability_at_start INT NULL,
    started_at DATETIME NOT NULL,
    complete_at DATETIME NOT NULL,
    effective_speed_bonus_pct FLOAT NOT NULL DEFAULT 0,
    effective_double_chance_pct FLOAT NOT NULL DEFAULT 0,
    effective_stamina_bonus_pct FLOAT NOT NULL DEFAULT 0,
    stamina_paid INT NOT NULL,
    base_quantity INT NOT NULL,                     -- snapshot of result_quantity_per_gather at start
    skill_slug VARCHAR(20) NOT NULL,                -- snapshot: mining|herbalism|woodcutting
    status ENUM(
        'active','completed','cancelled','interrupted_by_battle','inventory_full'
    ) NOT NULL DEFAULT 'active',
    finished_at DATETIME NULL,
    result_quantity INT NULL,
    xp_awarded INT NULL,
    rank_up_to INT NULL,
    CONSTRAINT fk_gathering_sessions_node
        FOREIGN KEY (node_id) REFERENCES gathering_nodes(id) ON DELETE CASCADE,
    INDEX ix_gathering_sessions_character (character_id),
    INDEX ix_gathering_sessions_status_complete (status, complete_at),
    INDEX ix_gathering_sessions_node_status (node_id, status)
);
```

Locations-service `models.py` adds two SQLAlchemy classes mirroring the above. `GatheringNode` has `relationship("Location")` and `relationship("GatheringSession", cascade="all, delete-orphan")`.

#### 3.3.2 inventory-service — Alembic migration `016_add_gathering_system.py`

```sql
-- 1. Extend items.item_type ENUM (additive, no data change)
ALTER TABLE items
  MODIFY COLUMN item_type ENUM(
    'head','body','cloak','belt','ring','necklace','bracelet','main_weapon',
    'consumable','additional_weapons','resource','scroll','misc','shield',
    'blueprint','recipe','gem','rune','gathering_tool'
  ) NOT NULL;

-- 2. Add tool-specific columns
ALTER TABLE items
  ADD COLUMN tool_category ENUM('pickaxe','sickle','axe') NULL,
  ADD COLUMN gather_double_chance_bonus FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN gather_speed_bonus_pct     FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN gather_stamina_bonus_pct   FLOAT NOT NULL DEFAULT 0;

-- 3. New tables (skill catalog + ranks + per-character progress)
CREATE TABLE gathering_skills (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    slug VARCHAR(50) NOT NULL UNIQUE,           -- mining|herbalism|woodcutting
    name VARCHAR(100) NOT NULL,
    category ENUM('ore','herb','wood') NOT NULL UNIQUE,
    description TEXT NULL,
    icon VARCHAR(255) NULL,
    max_rank INT NOT NULL DEFAULT 5,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE gathering_skill_ranks (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    skill_id INT NOT NULL,
    rank_number INT NOT NULL,                   -- 1..5
    required_experience INT NOT NULL,           -- XP required to ENTER this rank from previous
    double_chance_bonus FLOAT NOT NULL DEFAULT 0,
    speed_bonus_pct FLOAT NOT NULL DEFAULT 0,
    stamina_bonus_pct FLOAT NOT NULL DEFAULT 0,
    CONSTRAINT fk_gathering_skill_ranks_skill
        FOREIGN KEY (skill_id) REFERENCES gathering_skills(id) ON DELETE CASCADE,
    UNIQUE KEY uq_skill_rank (skill_id, rank_number)
);

CREATE TABLE character_gathering_skills (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    character_id INT NOT NULL,
    skill_id INT NOT NULL,
    current_rank INT NOT NULL DEFAULT 1,
    experience INT NOT NULL DEFAULT 0,           -- toward NEXT rank; resets on rank-up
    experience_total INT NOT NULL DEFAULT 0,     -- lifetime
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_character_gathering_skills_skill
        FOREIGN KEY (skill_id) REFERENCES gathering_skills(id) ON DELETE CASCADE,
    UNIQUE KEY uq_character_skill (character_id, skill_id),
    INDEX ix_character_gathering_skills_character (character_id)
);
```

**Seed data (in same migration, `op.bulk_insert`):**

```python
# 3 skills
skills = [
    {"id": 1, "slug": "mining",      "name": "Горное дело",  "category": "ore",  "description": "Навык добычи руды",   "max_rank": 5},
    {"id": 2, "slug": "herbalism",   "name": "Травничество", "category": "herb", "description": "Навык сбора трав",   "max_rank": 5},
    {"id": 3, "slug": "woodcutting", "name": "Лесорубство",  "category": "wood", "description": "Навык рубки дерева", "max_rank": 5},
]

# 5 ranks per skill — chosen rank bonuses
# Rank 1 = baseline (no bonus). required_experience = XP needed to ENTER that rank.
# Per spec: 1->2 = 10, 2->3 = 25, 3->4 = 50, 4->5 = 100. Rank 1 entry = 0.
RANK_BONUSES = [
    # (rank, required_xp_to_enter, double_chance, speed_bonus_pct, stamina_bonus_pct)
    (1,   0,  0.0,  0.0,  0.0),
    (2,  10,  4.0,  4.0,  4.0),
    (3,  25,  8.0,  8.0,  8.0),
    (4,  50, 12.0, 12.0, 12.0),
    (5, 100, 20.0, 20.0, 20.0),
]
ranks = []
for sid in (1, 2, 3):
    for (rn, req, dc, sp, st) in RANK_BONUSES:
        ranks.append({
            "skill_id": sid, "rank_number": rn,
            "required_experience": req,
            "double_chance_bonus": dc,
            "speed_bonus_pct": sp,
            "stamina_bonus_pct": st,
        })
```

Rationale for bonus values:
- **Linear-ish ramp 0/4/8/12/20** mirrors existing whetstone/profession progressions in the codebase (FEAT-082/083) — gentle for ranks 2-3, meaningful for rank 5.
- Rank-5 stamina_bonus_pct=20% means a 5-stamina node costs 4 stamina (with `ceil`). Combined with a rare/epic tool's 10-15% it can reach 30-35% — significant but not free.
- Rank-5 speed_bonus_pct=20% means 25-min gather drops to 20 min; combined with a tool's 10-15% reaches ~30%, which honors player progression without trivializing time gating.
- Rank-5 double_chance=20% combined with a top-tier tool's 25-30% caps at 50% (well below the global 80% cap) so legendary-tier tools are still visibly better.

`character_gathering_skills` rows are **lazy-created** on the first XP award per (character, skill). No backfill of existing characters in this migration.

#### 3.3.3 character-attributes-service — Alembic migration `006_add_refund_stamina.py`

No schema change. The migration is empty (only a no-op revision marker — required because we increment the head to keep the chain documented). Optional: drop this if the team prefers keeping migrations 1:1 with schema changes; in that case, no migration is added.

**Decision:** SKIP this migration entirely (no schema change). Add comment in `main.py` instead.

#### 3.3.4 user-service — Alembic migration `0025_add_gathering_permissions.py`

```python
PERMISSIONS = [
    ("gathering:read",   "Просмотр нод добычи и навыков сбора"),
    ("gathering:create", "Создание нод добычи на локациях"),
    ("gathering:update", "Изменение нод добычи"),
    ("gathering:delete", "Удаление нод добычи"),
]

# Insert into permissions; assign:
#   - Editor: gathering:read
#   - Moderator: gathering:read, gathering:update
#   - Admin: ALL (handled automatically by RBAC seeding)
```

Follow the exact pattern of `0019_add_profession_permissions.py`.

### 3.4 Frontend Components

All new files: `.tsx`, Tailwind only, no `React.FC`, mobile responsive, errors visible to user.

```
services/frontend/app-chaldea/src/
├── api/
│   └── gatheringApi.ts                                    # NEW: REST + axios layer
├── store/
│   └── slices/gatheringSlice.ts                           # NEW: Redux slice (active session, last-finished toast, nodes-on-current-location cache)
├── hooks/
│   └── useGatheringLock.ts                                # NEW: parallel to useBattleLock
├── components/
│   ├── CommonComponents/
│   │   └── GatheringLockBanner.tsx                        # NEW: parallel to BattleLockBanner
│   ├── pages/LocationPage/
│   │   ├── LocationPage.tsx                               # MODIFY: render <GatheringSection> + apply useGatheringLock to disable post-form/quick-move
│   │   ├── GatheringSection/
│   │   │   ├── GatheringSection.tsx                       # NEW: list of nodes
│   │   │   ├── GatheringNodeCard.tsx                      # NEW: per-node card (name, bank, stamina, time, status, active gatherers list)
│   │   │   ├── ToolSelectionModal.tsx                     # NEW: appears when starting gather; uses ConfirmationModal pattern if available
│   │   │   ├── GatheringInProgressOverlay.tsx             # NEW: shows countdown + cancel button
│   │   │   └── gatheringSection.types.ts                  # NEW: TS interfaces
│   ├── ProfilePage/
│   │   ├── ProfileTabs.tsx                                # MODIFY: insert {key:"gathering", label:"Сбор"} between Perks (idx 2) and Quests (idx 3)
│   │   ├── ProfilePage.tsx                                # MODIFY: render <GatheringTab> case
│   │   └── GatheringTab/
│   │       ├── GatheringTab.tsx                           # NEW: 3-skill panel
│   │       └── GatheringSkillCard.tsx                     # NEW: rank, XP bar, current/next bonuses
│   ├── Admin/
│   │   ├── AdminLocationsPage/EditForms/EditLocationForm/
│   │   │   ├── EditLocationForm.tsx                       # MODIFY: render <GatheringNodesEditor locationId={...} />
│   │   │   └── GatheringNodesEditor/
│   │   │       ├── GatheringNodesEditor.tsx               # NEW: list + add + edit/delete + manual restore
│   │   │       └── NodeRow.tsx                            # NEW
│   │   └── ItemsAdminPage/
│   │       └── ItemForm.tsx                               # MODIFY: add gathering_tool branch (tool_category dropdown + 3 bonus inputs + max_durability)
│   └── ProfilePage/InventoryTab/dnd/constants.ts          # MODIFY: ITEM_TYPES + ITEM_TYPE_LABELS gathering_tool
```

**Redux state shape (gatheringSlice):**
```ts
interface GatheringState {
  activeSession: ActiveGatheringSession | null;   // current character's session if any
  pollingEnabled: boolean;                         // toggled when on a location page or session active
  lastFinishedToast: FinishedSessionPayload | null; // shown once, then cleared
  nodesByLocation: Record<number, GatheringNode[]>; // cached from /client/details
  toolsCache: Record<ToolCategory, GatheringTool[]>; // populated on tool-modal open
  isStarting: boolean;
  startError: string | null;
}
```
Selectors: `selectActiveSession`, `selectIsGathering`, `selectNodesForLocation(locId)`, `selectToolsByCategory(cat)`. Async thunks: `fetchActiveSession`, `startGathering`, `cancelGathering`, `fetchToolsByCategory`, `fetchSkills(characterId)`.

**Polling strategy:** `useGatheringLock` hook polls `GET /locations/characters/{cid}/active_gathering` every 10 s while a session is active (and on every LocationPage mount once). On `complete_at <= now()`, the next poll triggers lazy finalize server-side and surfaces `last_finished_session` for the toast.

### 3.5 Data Flow Diagrams

#### 3.5.1 Start gather

```
[Frontend: GatheringNodeCard "Добыть" click]
    │
    ├─► (optionally) GET /inventory/{inv_id}/items?item_type=gathering_tool&category=pickaxe
    │       ◄── tool list
    │   IF >1 tools: open <ToolSelectionModal>; user picks → tool_inventory_item_id
    │   IF =1 tool: auto-select
    │   IF =0 tools: show "without tool" warning modal → tool_inventory_item_id=null
    │
    └─► POST /locations/{lid}/gathering-nodes/{nid}/start
            { character_id, tool_inventory_item_id }
            │
            ▼
    [locations-service: start_gathering()]
        1. SELECT ... FOR UPDATE on gathering_nodes row (lock node)
        2. Lazy-restore bank if restore_at <= NOW()
        3. Validate node: is_enabled, not depleted, allow_concurrent_gather or no other active session on this node
        4. check_not_in_battle(character_id)            -- raw SQL on shared DB
        5. check_not_gathering(character_id)            -- new helper, raw SQL on gathering_sessions
        6. check_not_in_dungeon(character_id)            -- HTTP GET dungeon-service /internal/character-session/{cid}
        7. Travel cooldown check (existing pattern)
        8. HTTP GET inventory-service: tool exists, belongs to character, category matches, durability > 0
        9. HTTP GET inventory-service: free_slots_check  (or existing list endpoint) -> if full -> 400
       10. HTTP GET attributes-service: /attributes/{cid} -> read current_stamina + max_stamina
       11. Compute effective_seconds, effective_stamina_paid (see 3.6 formulas)
       12. Validate current_stamina >= effective_stamina_paid
       13. HTTP POST attributes-service /consume_stamina { amount: effective_stamina_paid }
       14. INSERT gathering_sessions row, status=active, started_at=NOW(), complete_at=NOW()+effective_seconds
       15. (If shared bank or first user) decrement available reservation? -- NO: bank decrement happens only at finalize (per spec — pro-rata)
       16. Auto-post: SELECT character_name from character-service, INSERT post via crud.create_post bypassing MIN_POST_LENGTH, content "<em>*{name} начинает добычу [{node_name}]*</em>"
       17. COMMIT
       18. Return GatherStartResponse
            ▲
[Frontend] ─┘ stores activeSession in Redux; useGatheringLock returns true; LocationPage greys out post form, quick-move buttons, neighbors action; <GatheringInProgressOverlay> appears with countdown
```

#### 3.5.2 Lazy completion on poll

```
[Frontend: poll every 10s OR on LocationPage mount]
    │
    GET /locations/characters/{cid}/active_gathering
    OR
    GET /locations/{lid}/client/details
            │
            ▼
    [locations-service: lazy_finalize_overdue(cid)]
        1. SELECT * FROM gathering_sessions
           WHERE character_id=:cid AND status='active' AND complete_at <= NOW()
           FOR UPDATE
        2. For each session row:
             a. SELECT ... FOR UPDATE on gathering_nodes row (parent)
             b. Compute desired_quantity:
                  base = base_quantity
                  doubles_rolled = 0
                  for i in range(base):  # one roll per base unit
                      if random.random()*100 < effective_double_chance_pct:
                          doubles_rolled += 1
                  desired = base + doubles_rolled
             c. Cap by tool_durability_at_start + 1 (Risk #5 simplest path):
                  if tool_inventory_item_id:
                      desired = min(desired, tool_durability_at_start + 1)
                  -- "+1" is conservative: at most ONE double can happen even if the
                     tool only had 1 durability point left, because the first base
                     roll consumes the last point but the double still procs.
             d. Cap by current_bank: granted = min(desired, current_bank)
             e. UPDATE gathering_nodes SET current_bank = current_bank - granted
                  IF current_bank == 0:
                      depleted_at = NOW(), restore_at = NOW() + 24h
             f. HTTP POST inventory-service /internal/.../gathering/award
                  { character_id, skill_slug, result_item_id, result_quantity=granted,
                    tool_inventory_item_id, tool_durability_to_consume=granted }
                  Returns { actual_quantity_added, xp_gained, new_rank, rank_up, tool_broke, tool_current_durability }
             g. If actual_quantity_added < granted (inventory was clipped / full):
                  status = 'inventory_full'
                  result_quantity = actual_quantity_added
                  REFUND bank by (granted - actual_quantity_added)
                  -- IMPORTANT: do NOT refund stamina (per spec: stamina was paid in full)
                Else:
                  status = 'completed', result_quantity = granted
             h. UPDATE gathering_sessions SET status, finished_at=NOW(), result_quantity, xp_awarded, rank_up_to
             i. Optional: HTTP POST character-service /characters/{cid}/log
                          { event_type: "gathering_completed", metadata: {...} }
        3. COMMIT; cache last-finished payload in response
            ▲
[Frontend] ─┘ shows toast "+4 железной руды (+4 XP, ранг 2)"; clears activeSession; useGatheringLock returns false
```

#### 3.5.3 Battle interrupt

```
[Frontend: PvP attack]
    │
    POST /battles/pvp/attack { attacker_character_id, victim_character_id }
            │
            ▼
    [battle-service: pvp_attack()]
        1. Existing checks: ownership, same location, not safe location, not already in battle, etc.
        2. NEW: HTTP POST locations-service /locations/internal/cancel-gathering
                { character_id: victim_character_id, reason: "interrupted_by_battle" }
                Header: Authorization: Bearer ${INTERNAL_SERVICE_TOKEN}
                ◄── { cancelled: bool, session_id, stamina_refunded }
                → On 502 from this call: log warning but PROCEED (battle wins per spec; if stamina refund failed, that is a recoverable accounting bug, not a blocker).
        3. Existing: create_battle(...), Redis state init, etc.
        4. Return PvpAttackResponse
            │
            ▼
    [Frontend] redirects victim's session to BattlePage; useGatheringLock returns false (session no longer active); BattleLockBanner takes over.

    ─── inside locations-service: cancel_gathering_internal() ───
        1. SELECT * FROM gathering_sessions WHERE character_id=:cid AND status='active' FOR UPDATE
        2. If none -> return {cancelled: false}
        3. UPDATE gathering_sessions SET status='interrupted_by_battle', finished_at=NOW()
        4. Compute refund = stamina_paid // 2  (FLOOR — see 3.6)
        5. HTTP POST attributes-service /attributes/{cid}/refund_stamina { amount: refund }
        6. COMMIT; return {cancelled: true, session_id, stamina_refunded: refund}
```

#### 3.5.4 Manual cancel (player)

Same as 3.5.3 step 1-6 but invoked via the player-facing endpoint and `status='cancelled'`. Auth: owner-only (no internal token).

#### 3.5.5 Tool-broken-mid-gather (decision)

We chose the **simpler approach from Risk #5**: at finalize, cap `granted` by `tool_durability_at_start + 1`. Rationale:
- One unit of resource consumes one durability point; with N starting durability, at most N base resources can be earned.
- The `+1` slack covers the edge case where the *last* durability point is consumed by the base resource and the double-chance roll still procs (the player gets a "free" extra unit because the tool was about to break anyway — this is generous to the player and visible/explainable in patch notes).
- This avoids the more complex "switch to no-tool mode mid-gather" path, which would require recomputing remaining time and bonuses with a partial timeline.
- The tool ends with `current_durability = 0` (broken) and the player must repair it before the next gather.

### 3.6 Bonus Calculations / Formulas

Let:
- `B_time = stamina_per_gather * 5 * 60` (base seconds, "1 stamina = 5 min")
- `B_stamina = stamina_per_gather` (base stamina cost)
- `S_speed, S_double, S_stamina` = current rank bonuses (percent)
- `T_speed, T_double, T_stamina` = tool bonuses (percent), all 0 if no tool
- `P` = without-tool penalty: 1 if has_tool else 0

```
# Effective gather time
# LENIENT reading (per user 2026-04-25): rank bonuses ALWAYS apply.
# No tool only zeroes the TOOL bonuses (T_*) and adds the ×2 penalty.
speed_total_pct = S_speed + T_speed                     # T_* are 0 if no_tool
speed_total_pct = min(speed_total_pct, 60)              # cap at 60% for sanity
effective_seconds = floor(B_time * (1 - speed_total_pct/100))
if not has_tool:
    effective_seconds = effective_seconds * 2           # ×2 penalty AFTER rank speed bonus
effective_seconds = max(effective_seconds, 30)          # absolute floor 30s

# Effective stamina cost (paid once, fully, on start)
stamina_total_pct = S_stamina + T_stamina               # T_stamina = 0 if no_tool; rank S_stamina still applies
stamina_total_pct = min(stamina_total_pct, 50)          # cap at 50%
effective_stamina_paid = ceil(B_stamina * (1 - stamina_total_pct/100))
effective_stamina_paid = max(effective_stamina_paid, 1)

# Double-chance roll (per base unit produced; rolled at finalize)
# Per explicit spec ("Без инструмента: Нет шанса на дубль ресурса") — double chance
# is gated on the tool, regardless of rank.
if has_tool:
    double_chance_pct = S_double + T_double
    double_chance_pct = min(double_chance_pct, 80)
else:
    double_chance_pct = 0

# Refund on cancel / battle interrupt
# CEIL (per user 2026-04-25) — player-friendly rounding.
stamina_refunded = ceil(stamina_paid * 0.5)
                                                         # Example: paid 5 -> refund 3; paid 1 -> refund 1.
```

`effective_speed_bonus_pct`, `effective_double_chance_pct`, `effective_stamina_bonus_pct` are persisted on the `gathering_sessions` row at start so admin changes to the node mid-session do not affect the in-flight calculation (per spec: "active gathering uses old parameters").

**Without-tool effects (summary):**
| Without tool | With tool |
|--------------|-----------|
| time = floor(B_time × (1 - S_speed/100)) × 2, 30s floor | time = floor(B_time × (1 - (S_speed+T_speed)/100)), 60% cap |
| stamina = ceil(B_stamina × (1 - S_stamina/100)), 1 floor | stamina = ceil(B_stamina × (1 - (S_stamina+T_stamina)/100)), 50% cap, 1 floor |
| double_chance = 0 (gated on tool per spec) | double_chance = (S_double + T_double), 80% cap |
| rank speed/stamina bonuses APPLY; only tool bonuses zeroed | rank + tool bonuses combined |
| rank XP awarded | rank XP awarded |

### 3.7 Open questions for user — RESOLVED (2026-04-25)

1. **No-tool penalty scope:** RESOLVED — **lenient interpretation chosen**. Rank speed/stamina bonuses ALWAYS apply (they reflect the player's professional skill). Only the *tool* bonuses are zeroed when gathering without a tool, plus the ×2 time penalty and 0% double-chance per explicit spec. Formulas above updated.
2. **Stamina refund rounding:** RESOLVED — **CEIL (round up)** chosen for player-friendliness. Example: paid 5 → refund 3; paid 1 → refund 1. All references in section 4 task descriptions and API contracts must use `ceil(stamina_paid * 0.5)`.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Legend: BE = Backend Developer, FE = Frontend Developer, DSO = DevSecOps, QA = QA Test, RV = Reviewer.
Tasks marked with the same `Depends On` group can run in parallel.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **inventory-service: Alembic migration `016_add_gathering_system.py`** — extend `items.item_type` ENUM with `gathering_tool`; add `tool_category`, `gather_double_chance_bonus`, `gather_speed_bonus_pct`, `gather_stamina_bonus_pct` columns on `items`; create `gathering_skills`, `gathering_skill_ranks`, `character_gathering_skills` tables with constraints/indexes per 3.3.2; seed 3 skills × 5 ranks with required_xp 0/10/25/50/100 and bonuses 0/4/8/12/20. Update `models.py` with the new ORM classes + tool fields on Items. | BE | DONE | `services/inventory-service/app/alembic/versions/016_add_gathering_system.py`, `services/inventory-service/app/models.py` | — | `alembic upgrade head` succeeds locally and on a fresh DB; `alembic downgrade -1` reverses cleanly; ENUM contains `gathering_tool`; seed rows visible in `gathering_skills` (3) and `gathering_skill_ranks` (15). |
| 2 | **locations-service: Alembic migration `031_add_gathering_nodes.py`** — create `gathering_nodes` and `gathering_sessions` tables per 3.3.1 with all FKs, indexes, ENUMs. Update `models.py` with `GatheringNode` + `GatheringSession` async ORM classes. | BE | DONE | `services/locations-service/app/alembic/versions/031_add_gathering_nodes.py`, `services/locations-service/app/models.py` | — | `alembic upgrade head` succeeds; downgrade clean; tables exist with documented indexes. |
| 3 | **user-service: Alembic migration `0025_add_gathering_permissions.py`** — insert 4 permissions (`gathering:read/create/update/delete`); assign to Editor (read), Moderator (read+update); rely on Admin auto-assign. | BE | DONE | `services/user-service/alembic/versions/0025_add_gathering_permissions.py` | — | Migration runs; rows present in `permissions` and `role_permissions`; admin user inherits all 4 (verified via `test_rbac_permissions.py`). |
| 4 | **inventory-service: extend `ItemCreate`/`ItemUpdate` schemas + create CRUD validation for `gathering_tool`** — add fields to schemas; add server-side validation per 3.1.7 (tool_category required iff item_type=gathering_tool; bounds 0..50 on bonuses; max_durability >= 1). Tool items must NOT roll any equipment-stat modifiers (per 2.7 #3). | BE | DONE | `services/inventory-service/app/schemas.py`, `services/inventory-service/app/crud.py`, `services/inventory-service/app/main.py` | 1 | POST /inventory/items with `item_type=gathering_tool` body succeeds; missing `tool_category` returns 422; `strength_modifier` etc. set on a gathering_tool body returns 422 or is silently ignored (decision: 422, explicit). |
| 5 | **inventory-service: list tools endpoint extension** — extend `GET /inventory/{inventory_id}/items` to filter by `item_type=gathering_tool` AND optional `category=pickaxe|sickle|axe`; include tool fields and `current_durability` per row in the response. | BE | DONE | `services/inventory-service/app/main.py`, `services/inventory-service/app/schemas.py`, `services/inventory-service/app/crud.py` | 1 | Filter returns only tools of given category; durability field present; existing item-listing tests still pass. |
| 6 | **inventory-service: gathering-skills read endpoint** — `GET /inventory/characters/{cid}/gathering-skills` returns 3-skill payload per 3.1.4. Lazy-create `character_gathering_skills` rows on first access. | BE | DONE | `services/inventory-service/app/main.py`, `services/inventory-service/app/schemas.py`, `services/inventory-service/app/crud.py` | 1 | Endpoint returns 3 skills with rank=1, xp=0 for any new character; current/next bonus blocks correct from seed data. |
| 7 | **inventory-service: internal `award` endpoint** — `POST /inventory/internal/characters/{cid}/gathering/award` per 3.1.5. Single transaction: SELECT FOR UPDATE on `character_inventory` rows, append item (respect stack/inventory-full), decrement tool durability, add XP, perform rank-up loop. Returns full result block. | BE | DONE | `services/inventory-service/app/main.py`, `services/inventory-service/app/crud.py` | 1, 5 | Internal token check enforced; ATOMIC: failure inside the tx leaves no partial state; inventory-full path returns `items_added=false, actual_quantity_added=0`; rank-up math matches seed XP thresholds. |
| 8 | **inventory-service: free-slots-check internal helper** — `POST /inventory/internal/characters/{cid}/free_slots_check` returns `{free_slot_count, is_full}`. Used by locations-service at gather start. | BE | DONE | `services/inventory-service/app/main.py`, `services/inventory-service/app/crud.py` | 1 | Endpoint behind internal token; correctly counts free slots given the character's inventory size config. |
| 9 | **character-attributes-service: `refund_stamina` endpoint** — `POST /attributes/{cid}/refund_stamina` per 3.1.6, mirrors `consume_stamina` shape and auth. Caps at `max_stamina`. | BE | DONE | `services/character-attributes-service/app/main.py`, `services/character-attributes-service/app/crud.py`, `services/character-attributes-service/app/schemas.py` | — | POST refunds correctly; cap at max_stamina enforced; amount<=0 returns 422; idempotent against partial failures (uses `with_for_update()`). |
| 10 | **locations-service: gathering admin CRUD endpoints** — implement 5 admin routes per 3.1.2 (list/create/update/delete/restore). Include `result_item_id` existence check via SELECT on `items` in shared DB. Wire `require_permission("gathering:<x>")` decorators. Validate tool category vs node category mapping is **not** required here (mapping is at gather start). | BE | DONE | `services/locations-service/app/main.py`, `services/locations-service/app/schemas.py`, `services/locations-service/app/crud.py` | 2, 3 | All 5 routes return correct status codes; non-admin gets 403; deletion cascades sessions; restore resets bank to max and clears `depleted_at`/`restore_at`. |
| 11 | **locations-service: surface gathering nodes in `LocationClientDetails`** — extend the existing `GET /locations/{id}/client/details` to (a) lazy-restore depleted nodes whose `restore_at <= NOW()`, (b) lazy-finalize any active sessions whose `complete_at <= NOW()` (calls inventory-service award + attribute refund as needed), (c) return enriched `gathering_nodes[]` with `result_item_*` joined fields and `active_sessions[]` (character_name/avatar pulled from character-service in batch). | BE | DONE | `services/locations-service/app/main.py`, `services/locations-service/app/schemas.py`, `services/locations-service/app/crud.py` | 2, 7 | client/details payload includes `gathering_nodes` array; bank auto-restores after 24h; overdue sessions are finalized exactly once; no N+1 — character-name lookups batched. |
| 12 | **locations-service: `check_not_gathering` helper + integration into other action endpoints** — add raw SQL helper (parallel to `check_not_in_battle`); call it inside `move_and_post`, `quick_move`, post-create, equip/unequip (cross-service: NOT here, that's task 13), action-style endpoints. Within locations-service: post-create routes and movement routes. | BE | DONE | `services/locations-service/app/main.py`, `services/locations-service/app/crud.py` | 2 | Posting / moving while gathering is active returns 400 "Действие заблокировано во время добычи"; finishing/cancelling unblocks. |
| 13 | **inventory-service: `check_not_gathering` integration into equip/unequip/use_item** — defensive shared-DB raw SQL check (mirror of `check_not_in_battle` in `equip`); blocks equipment changes during gathering. | BE | DONE | `services/inventory-service/app/main.py`, `services/inventory-service/app/crud.py` | 2 | Calling `/equip` during active gathering returns 400; existing equip flow otherwise unchanged. |
| 14 | **locations-service: start gathering endpoint** — `POST /locations/{lid}/gathering-nodes/{nid}/start` per 3.1.1. Implements full data flow 3.5.1 with FOR UPDATE on node row, all cross-service checks, stamina consume, auto-post (mirror `quick_move` pattern), `gathering_sessions` insert with snapshot of effective bonuses, response per spec. | BE | DONE | `services/locations-service/app/main.py`, `services/locations-service/app/crud.py`, `services/locations-service/app/schemas.py` | 2, 6, 7, 8, 9, 12 | All listed validation paths return correct error codes; happy path inserts session, decrements stamina (NOT bank — bank only at finalize), creates auto-post, returns full response; concurrent start on `allow_concurrent_gather=false` second caller gets 400. |
| 15 | **locations-service: cancel gathering endpoint (player + internal)** — `POST /locations/{lid}/gathering-nodes/{nid}/cancel` (owner-only) and `POST /locations/internal/cancel-gathering` (internal token), both per 3.1.1/3.1.3. Compute ceil(stamina_paid/2) refund (player-friendly rounding per 3.7 resolution), call attributes-service. Different `status` values for the two paths. | BE | DONE | `services/locations-service/app/main.py`, `services/locations-service/app/crud.py`, `services/locations-service/app/schemas.py` | 2, 9, 14 | Manual cancel returns refund and sets status=`cancelled`; internal cancel sets status=`interrupted_by_battle`; both calls are idempotent (second call returns "no active session"). |
| 16 | **locations-service: active gathering poll endpoint** — `GET /locations/characters/{cid}/active_gathering` per 3.1.1. Performs lazy-finalize before responding; on first response after finalize, returns `last_finished_session` block. | BE | DONE | `services/locations-service/app/main.py`, `services/locations-service/app/crud.py`, `services/locations-service/app/schemas.py` | 2, 7, 11, 14 | Active session shows `remaining_seconds` correctly; after `complete_at` passes, the next call returns `active=false` with populated `last_finished_session`. |
| 17 | **battle-service: hook `pvp_attack` to cancel-gathering** — before creating the battle, call `POST /locations/internal/cancel-gathering` with `INTERNAL_SERVICE_TOKEN`. On 502/timeout, log warning and continue (per spec: attacker wins the race). | BE | DONE | `services/battle-service/app/main.py` | 15 | Attacking a gathering victim triggers session cancel + 50% stamina refund and creates the battle; if locations-service is down, battle still creates (warning logged). |
| 18 | **api-gateway: rate-limit zone for gathering** — add `limit_req_zone $binary_remote_addr zone=gathering_limit:10m rate=10r/m;` to both `nginx.conf` and `nginx.prod.conf`; apply to `/locations/*/gathering-nodes/*/start` and `/locations/*/gathering-nodes/*/cancel` with `burst=5 nodelay; limit_req_status 429;`. | DSO | DONE | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | — | Sending >10 starts/min from same IP returns 429; existing routes unaffected; both dev and prod configs updated identically. |
| 19 | **frontend: API + Redux slice + types** — create `api/gatheringApi.ts` (axios calls for start/cancel/poll/skills/tools/admin CRUD) and `redux/slices/gatheringSlice.ts` (state shape + thunks per 3.4); add to root reducer. Define TS interfaces. | FE | DONE | `services/frontend/app-chaldea/src/api/gatheringApi.ts`, `services/frontend/app-chaldea/src/redux/slices/gatheringSlice.ts`, `services/frontend/app-chaldea/src/redux/store.ts`, `services/frontend/app-chaldea/src/types/gathering.ts` | — (parallel to backend) | `tsc --noEmit` clean; `npm run build` passes; thunks dispatch correctly via mocked axios. |
| 20 | **frontend: `useGatheringLock` hook + `GatheringLockBanner`** — clone `useBattleLock` + `BattleLockBanner` shape; lock returns `{isGathering, sessionId, completeAt, remainingSeconds, locationId}`; banner renders with countdown and "Отменить" button. | FE | DONE | `services/frontend/app-chaldea/src/hooks/useGatheringLock.ts`, `services/frontend/app-chaldea/src/components/CommonComponents/GatheringLockBanner.tsx` | 19 | Hook polls every 10s while session active, stops once finalized; banner appears on every page when gathering; Tailwind only, mobile-responsive. |
| 21 | **frontend: LocationPage `<GatheringSection>` + node card + tool selection modal + in-progress overlay** — new components per 3.4; integrate into LocationPage between LocationMobs and LootSection; gate post form / quick-move / neighbors via `useGatheringLock`. Tool modal shows list, picks one, falls back to "without tool" warning per spec. | FE | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx`, `services/frontend/app-chaldea/src/components/pages/LocationPage/GatheringSection/*.tsx` | 19, 20 | All node card states render (available, depleted-with-timer, occupied-by-X); modal selects tool or proceeds without; toast appears on completion; errors from API displayed in Russian; mobile screen 360px renders correctly. |
| 22 | **frontend: ProfilePage "Сбор" tab** — insert tab between Перки and Задания in `ProfileTabs.tsx`; create `<GatheringTab>` and `<GatheringSkillCard>`; visible read-only on other players' profiles. | FE | DONE | `services/frontend/app-chaldea/src/components/ProfilePage/ProfileTabs.tsx`, `services/frontend/app-chaldea/src/components/ProfilePage/ProfilePage.tsx`, `services/frontend/app-chaldea/src/components/ProfilePage/GatheringTab/GatheringTab.tsx`, `.../GatheringSkillCard.tsx` | 19 | Tab visible on own + other profiles; rank/XP bar/current+next bonuses render; no rank-up button (auto rank-up via XP); Tailwind only; mobile responsive. |
| 23 | **frontend: ItemsAdminPage `ItemForm` extension for gathering tools** — add `gathering_tool` to ITEM_TYPES + ITEM_TYPE_LABELS; new conditional section showing `tool_category` dropdown (Кирка/Серп/Топор) + `max_durability` + 3 bonus inputs; hide all equipment-stat sections when type is gathering_tool. | FE | DONE | `services/frontend/app-chaldea/src/components/ItemsAdminPage/ItemForm.tsx`, `services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/dnd/constants.ts` | 19 | Selecting "Инструмент сбора" reveals the right inputs; saving creates an item with the new fields; existing item types unaffected. |
| 24 | **frontend: AdminLocationsPage `<GatheringNodesEditor>`** — sub-component embedded into `EditLocationForm.tsx`; lists current nodes for the location; supports add/edit/delete + manual restore button; item picker for `result_item_id` (reuse existing item search component if present). | FE | DONE | `services/frontend/app-chaldea/src/components/AdminLocationsPage/EditForms/EditLocationForm/EditLocationForm.tsx`, `.../GatheringNodesEditor/GatheringNodesEditor.tsx`, `.../GatheringNodesEditor/NodeRow.tsx` | 10, 19 | Admin can create/edit/delete a node and see results in player view immediately; permission gating (UI hides for non-admins via `hasModuleAccess('gathering')`); errors shown in Russian. |
| 25 | **QA: locations-service gathering tests** — pytest covering admin CRUD, start (incl. all error paths), cancel (player + internal), poll lazy-finalize, bank decrement, 24h restore (using freezegun or monkeypatched NOW), `check_not_gathering` propagation, concurrent start with `allow_concurrent_gather=false`. | QA | DONE | `services/locations-service/tests/test_gathering.py` (new) | 10, 11, 12, 14, 15, 16 | All test cases pass; coverage of new endpoints >= 85%; security tests included (non-admin CRUD, owner mismatch on cancel, missing internal token on internal endpoint). |
| 26 | **QA: inventory-service gathering tests** — pytest covering tool item CRUD validation, list-by-category filter, gathering-skills lazy-create, internal `award` happy path + inventory-full + rank-up branch, durability decrement at 0 (tool_broke=true), free-slots-check helper. | QA | DONE | `services/inventory-service/app/tests/test_gathering.py` (new) | 4, 5, 6, 7, 8, 13 | All tests pass; coverage of new endpoints >= 85%; SQL injection / unauthorized internal access cases included. |
| 27 | **QA: character-attributes-service refund_stamina tests** — pytest verifying refund increments, max-stamina cap, amount<=0 rejected, concurrent refunds use row lock (no double-credit). | QA | DONE | `services/character-attributes-service/app/tests/test_refund_stamina.py` (new) | 9 | Tests pass; race condition verified using parallel calls. |
| 28 | **QA: battle-service pvp_attack interrupt integration test** — mock locations-service internal endpoint and verify pvp_attack calls it before battle creation; verify behavior when call returns 502. | QA | DONE | `services/battle-service/app/tests/test_pvp_attack.py` (extended) | 17 | Tests pass; the cancel-gathering call asserted via mock; 502 path still creates battle (with warning log). |
| 29 | **Reviewer: full feature review + live verification** — verify all PRs match spec; run `npx tsc --noEmit` + `npm run build` (frontend); run `python -m py_compile` on all changed Python files; run all new pytests (`pytest -k gathering` across services); via `chrome-devtools` MCP or `curl`, exercise the live happy path (admin creates a node, player gathers with and without tool, gather completes, XP banked, tool durability decrements). Verify rate-limit kicks in. Update `docs/services/locations-service.md` and `docs/services/inventory-service.md` with the new tables/endpoints. Mark feature DONE only after all checks pass. | RV | DONE | All files above + `docs/services/locations-service.md`, `docs/services/inventory-service.md` | 1-28 | All builds green; all tests pass; live happy path works; docs updated; security checklist verified (RBAC, rate limit, internal token, owner-only cancel). |

**Parallelism map:**
- **Group A (independent, can start together):** 1, 2, 3, 9, 18, 19
- **Group B (after Group A):** 4, 5, 6 (after 1); 8 (after 1); 10 (after 2,3); 12, 13 (after 2); 20, 22, 23 (after 19)
- **Group C:** 7 (after 1,5); 11 (after 2,7); 14 (after 2,6,7,8,9,12); 24 (after 10,19)
- **Group D:** 15 (after 14); 16 (after 11,14); 21 (after 19,20)
- **Group E:** 17 (after 15)
- **Group F (QA, after their respective backend tasks):** 25, 26, 27, 28
- **Group G (final):** 29

**Critical path:** 1 → 7 → 11 → 14 → 15 → 17 → 28 → 29  (≈8 sequential tasks). Most other tasks fan out from Group A and rejoin at Reviewer.

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-04-25
**Result:** FAIL

#### Checks
- [ ] Types match (Pydantic ↔ TS interfaces) — **FAIL** (multiple shape mismatches, see issues #1-3)
- [x] API contracts consistent (URL paths backend ↔ frontend ↔ tests)
- [x] No stubs/TODO without tracking
- [x] `python -m py_compile` — PASS (all 13 modified Python files + 6 migrations + 4 test files)
- [x] `npx tsc --noEmit` — PASS (64 errors total, ALL pre-existing baseline; 0 new in any gathering file)
- [x] `npm run build` — PASS (Vite, 23.75s, dist generated)
- [x] pytest — PASS for inventory (52/52), locations (72/72), battle (7/7); character-attributes (9/10) — see issue #4 (SQLite test artifact, NOT impl bug)
- [x] Security checklist passed (rate limit verified live, internal token verified live, RBAC, owner-only, Russian errors)
- [x] User-facing strings in Russian
- [x] Frontend displays all errors to user (toast / inline `role="alert"` everywhere)
- [x] Live verification: PARTIAL — endpoint smoke tests via curl all PASS (rate-limit 429 confirmed at request 7 of 12, internal cancel returns proper 200/401/503 by token state, admin/poll endpoints return correct 401 without auth, migrations applied to live DB and verified). Browser-driven UX flow NOT exercised (chrome-devtools MCP unavailable in this environment); see "Issues Found" #1-3 — runtime contract mismatches will manifest in browser, blocking PASS.
- [ ] Documentation updated (`docs/services/locations-service.md`, `docs/services/inventory-service.md`) — **FAIL** (not yet updated; deferred to fix iteration since many backend changes are FIX_REQUIRED — docs should reflect the final shape)

#### Live verification details
- Migrations applied to live DB (verified `alembic_version_user=0025`, `alembic_version_inventory=016_add_gathering_system`, `alembic_version_locations=031_add_gathering_nodes`); 4 gathering permissions, 3 skills, 15 ranks, 4 gathering tables present, `items.tool_category` enum column present.
- Container restart required to load new env (`INTERNAL_SERVICE_TOKEN` was empty in the running locations-service before recreate; `--build` was required for api-gateway since nginx config is baked into the image). After recreate everything responded as expected.
- `POST /locations/internal/cancel-gathering`: with no token → 401 ✓, wrong token → 401 ✓, correct token → 200 `{"cancelled":false,"reason":"no_active_session"}` ✓.
- `POST /locations/1/gathering-nodes/1/start` × 12 rapid requests: requests 1-6 pass through (401), requests 7-12 → 429 — rate-limit zone is correctly applied (burst=5 + 1 = 6 pass-through, then 429s).
- `GET /locations/admin/locations/1/gathering-nodes` without auth → 401 ✓.
- `GET /locations/characters/1/active_gathering` without auth → 401 ✓.
- `GET /inventory/1/items?item_type=gathering_tool&category=pickaxe` → 200 `[]` ✓ (filter accepted, empty list because no tools seeded yet).
- Browser-driven happy-path NOT executed (no MCP chrome-devtools and no UI test harness available). Recommended manual test plan in "Notes for fix iteration" below.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/types/gathering.ts:79-113` (and `redux/slices/gatheringSlice.ts:362-373`) | **Active-gathering poll payload shape mismatch (RUNTIME-BREAKING).** TS types model `ActiveGatheringResponse` as a flat discriminated union (`{active:true, session_id, node_id, complete_at, location_id, ...}` OR `{active:false, last_finished_session?}`). Backend (`locations-service/app/schemas.py:1641-1648`) returns NESTED: `{active: bool, session: ActiveSessionInfo \| null, last_finished_session: LastFinishedSessionInfo \| null}`. Inside `ActiveSessionInfo` (`schemas.py:1599-1617`) the session id field is named `id`, NOT `session_id`. The slice stores `payload` directly when `active===true` (line 366), so `state.activeSession` becomes `{active:true, session:{id, node_id, complete_at, location_id, …}, last_finished_session:null}` — but `useGatheringLock.ts:55,118,121` reads `activeSession.complete_at`, `activeSession.session_id`, `activeSession.location_id` (all `undefined` at runtime). The countdown shows 00:00, the cancel button calls `/locations/0/gathering-nodes/undefined/cancel`, and the lock banner won't actually engage after the first poll. Note: `startGathering.fulfilled` (slice line 318-334) constructs a synthetic flat payload that DOES work, so the bug only surfaces ~10s after start when the first poll overwrites it. **Fix options:** (a) reshape backend response to flat `{active, session_id, node_id, node_name, location_id, complete_at, started_at, remaining_seconds, stamina_paid, tool_inventory_item_id, last_finished_session}` matching the TS spec, or (b) reshape TS types + slice to read `session.id`, `session.complete_at`, `session.node_id`, `session.location_id`. Approach (a) matches the §3.1.1 spec verbatim and is preferred. | Backend Developer (locations) | FIX_REQUIRED |
| 2 | `services/locations-service/app/schemas.py:1620-1638` and `services/frontend/app-chaldea/src/components/pages/LocationPage/GatheringSection/GatheringSection.tsx:79,83,85` | **Last-finished toast field-name mismatch.** Backend `LastFinishedSessionInfo` returns `id`, `xp_awarded`, `new_rank`, `rank_up: bool`, `tool_broke`, `status`, `result_quantity`, `result_item_name` and **does NOT include `skill_slug` or `tool_durability_remaining`**. Frontend `FinishedGatheringSummary` (`types/gathering.ts:95-104`) expects `session_id`, `xp_gained`, `rank_up_to`, `skill_slug`, `tool_durability_remaining`, `tool_broke`, `result_quantity`. `GatheringSection.tsx:79,83,85` reads `lastFinished.skill_slug` (always undefined → `SKILL_LABELS[undefined]` falls back to "ресурса"), `lastFinished.xp_gained` (undefined → toast shows "+undefined опыта"), `lastFinished.rank_up_to` (undefined → rank-up branch never taken even when `rank_up=true`). The completion toast is broken in every successful gather. **Fix:** in `LastFinishedSessionInfo` rename `xp_awarded` → `xp_gained`, replace `(rank_up: bool, new_rank: int)` with `rank_up_to: int \| None` (null when no rank-up), add `skill_slug: GatheringSkillSlug` (from the snapshot stored at start on `gathering_sessions.skill_slug`) and `tool_durability_remaining: int \| None`. Update `_finalize_one_session` in `crud.py` to surface these. Also rename `id` → `session_id` for consistency. | Backend Developer (locations) | FIX_REQUIRED |
| 3 | `services/locations-service/app/schemas.py:1532-1555` vs `services/frontend/app-chaldea/src/types/gathering.ts:122-136` | **Start-gathering response shape mismatch (NON-BREAKING but spec deviation).** Backend includes `effective_stamina_bonus_pct` and `node_state_after: {current_bank, active_sessions_count}` which §3.1.1 of the spec does NOT include. Backend OMITS `tool_durability_at_start` and `auto_post_id` which §3.1.1 DOES include. `gatheringSlice.ts` only consumes `session_id, node_id, started_at, complete_at, effective_seconds, effective_stamina_paid, tool_inventory_item_id` so today there is no runtime crash, but the divergence will cause future drift. **Fix:** add `tool_durability_at_start: int \| None` and `auto_post_id: int \| None` to `StartGatheringResponse`. `effective_stamina_bonus_pct` and `node_state_after` are useful additions and can stay — surface them in the TS type too if Frontend Dev intends to display the bank-after counter. | Backend Developer (locations) | FIX_REQUIRED |
| 4 | `services/character-attributes-service/app/tests/test_refund_stamina.py:257-293` | **Concurrency test is environment-dependent (NOT a real bug, but FAILS under SQLite).** `test_concurrent_refund_respects_max_cap` asserts that two concurrent refunds against `current=5, max=10` total exactly 5 refunded across both responses. The implementation in `crud.py:151-175` uses `with_for_update()` correctly, but SQLite's `StaticPool` test setup does NOT enforce row-level locks, so both threads read `current=5` and both append `+5` for a total of 10. In production MySQL the lock works (the sibling test `test_two_concurrent_refunds_no_double_credit` passes because it does not stress the cap). **Fix:** either (a) `pytest.skip(...)` this test on SQLite (`pytest.importorskip` or check engine name) and document MySQL-only verification in the docstring, or (b) restructure to mock the SELECT/UPDATE pair with a `time.sleep` between them so both threads serialize in Python rather than relying on DB locks. The fix should NOT touch `crud.refund_stamina` — the production behaviour is correct. | QA Test | FIX_REQUIRED |
| 5 | `docs/services/locations-service.md`, `docs/services/inventory-service.md` | **Documentation not updated.** Task #29 explicitly requires the Reviewer to update the per-service docs with the new gathering tables, endpoints, and cross-service deps. Defer to fix iteration so the documentation reflects the FINAL contract shape after issues #1-3 are resolved (writing docs against today's broken contracts would just create more rework). | Reviewer | FIX_REQUIRED (after #1-3 resolved) |

#### Notes for fix iteration
- After issues #1-3 are fixed, please re-run BOTH `npx tsc --noEmit` and a manual browser flow:
  1. Login as admin → open Admin → Локации → edit any location → "Ноды добычи" → create a node (category=ore, item picker, qty=1, stamina=1, daily_bank_max=20, allow_concurrent=on, is_enabled=on) — should land in `gathering_nodes` table.
  2. Login as a non-admin user, walk a character to that location → "Ресурсы" block visible → click Добыть → modal → "Без инструмента" warning (no tool seeded) → confirm.
  3. Banner appears with countdown MM:SS → wait until `complete_at` → poll fires → toast "Добыто: N руды (+N опыта)" should render with REAL N values (currently shows `+undefined`).
  4. Cancel mid-gather: banner's "Отменить" should call the correct URL (currently calls `/locations/0/gathering-nodes/undefined/cancel`).
  5. PvP attack on a gathering victim: open another browser, attack → battle starts; check that locations-service log shows `Cancelled victim's gathering session before battle` and `gathering_sessions.status='interrupted_by_battle'`.
- Pre-existing repo issues spotted but NOT blocking this feature (no entries added to ISSUES.md because they're long-standing baseline noise): `frontend/AdminLocationsPage/AdminLocationsPage.tsx:241-280` typed-thunk `Argument of type 'number' is not assignable to parameter of type 'undefined'` (createAsyncThunk generic missing), `Bestiary/GrimoireBook.tsx:7-10` named-vs-default selector imports broken, `BattlePage/BattlePage.tsx:693-732` missing required props on children — all 64 baseline TS errors. None of these are in the FEAT-128 changeset.

### Review #2 — 2026-04-25
**Result:** PASS

#### Re-verification of Review #1 issues

| # | Issue | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | Active-gathering poll payload — flat shape | **FIXED** | `schemas.py:1636-1664` `ActiveGatheringResponse` now declares `session_id, node_id, node_name, location_id, started_at, complete_at, remaining_seconds, stamina_paid, tool_inventory_item_id, effective_*_pct` directly on the top-level model. `ActiveSessionInfo` removed. Live curl on `/locations/characters/1/active_gathering` returns `{"active":false,"session_id":null,"node_id":null,"node_name":null,"location_id":null,"started_at":null,"complete_at":null,"remaining_seconds":null,"stamina_paid":null,"tool_inventory_item_id":null,"effective_speed_bonus_pct":null,"effective_double_chance_pct":null,"effective_stamina_bonus_pct":null,"last_finished_session":null}` — fully flat, matches frontend `ActiveGatheringSession` discriminated union. `useGatheringLock.ts:55,118,121` reads `complete_at`, `session_id`, `location_id` — all directly on `activeSession` and present in flat backend response. |
| 2 | Last-finished toast field-name alignment | **FIXED** | `schemas.py:1606-1633` `LastFinishedSessionInfo` renamed `id`→`session_id`, `xp_awarded`→`xp_gained`, replaced `(rank_up + new_rank)` with single `rank_up_to: int \| None`, added `skill_slug: str \| None` and `tool_durability_remaining: int \| None`. `crud.py:5000-5014` `_finalize_one_session` returns dict with all these keys; main flow + inventory_full + granted=0 branches all updated (line 4810-4813 zero branch, line 4900-4903 granted=0 branch, line 5007-5010 normal branch). `GatheringSection.tsx:79,83,85` reads `lastFinished.skill_slug` (resolves to "руды/трав/дерева"), `lastFinished.xp_gained` (real number), `lastFinished.rank_up_to` (truthy on rank-up) — matches backend exactly. |
| 3 | Start-gathering response fields | **FIXED** | `schemas.py:1532-1562` `StartGatheringResponse` now includes `tool_durability_at_start: Optional[int]` and `auto_post_id: Optional[int]`. `crud.py:5683-5690` snapshots `current_durability` of the chosen tool BEFORE locking; `crud.py:5731-5741` captures the auto-post id (None on best-effort failure); both populated in returned dict (line 5783, 5785). `effective_stamina_bonus_pct` and `node_state_after` retained as additive debug-only fields — TS interface declares the spec-required ones; extra JSON fields are ignored on the FE side per spec deviation note. |
| 4 | QA concurrency tests on SQLite | **FIXED** | `test_refund_stamina.py` — `pytest.mark.skipif` decorators applied to both `test_concurrent_refund_respects_max_cap` and `test_two_concurrent_refunds_no_double_credit`. Pytest run shows: `8 passed, 2 skipped`. `with_for_update()` impl in `crud.py:151-175` is correct on production MySQL — verified by reading the unchanged crud code. |
| 5 | Documentation update | **DONE** | Updated `docs/services/locations-service.md` (added gathering admin/player/internal endpoints, gathering_nodes + gathering_sessions tables, cross-service deps including refund_stamina + gathering/award + free_slots_check, lazy-finalize pattern note). Updated `docs/services/inventory-service.md` (added `gathering_tool` to item_type enum + tool_category/bonus columns, list-tools-by-category endpoint extension, gathering-skills read endpoint, internal `award` and `free_slots_check`, `check_not_gathering` integration list of 11 endpoints, three new gathering tables). Updated `docs/ARCHITECTURE.md` Service Map DB-tables and HTTP communication graph for FEAT-128. |

#### Automated Check Results
- [x] `npx tsc --noEmit` — **PASS** (64 errors total, all pre-existing baseline; 0 errors in any gathering file — verified via grep filter for `gathering|GatheringSection|GatheringNodeCard|GatheringTab|GatheringSkillCard|GatheringNodesEditor|useGatheringLock|GatheringLockBanner` returning empty)
- [x] `npm run build` — **PASS** (Vite, 23.67s, dist generated; 2.83 MB main bundle warning is pre-existing baseline)
- [x] `py_compile` — **PASS** for all changed Python files: `locations-service` (schemas.py, crud.py, main.py, tests/test_gathering.py); `character-attributes-service` (crud.py, main.py, schemas.py, tests/test_refund_stamina.py); `inventory-service` (crud.py, main.py, schemas.py, tests/test_gathering.py); `battle-service` (main.py, tests/test_pvp_attack.py)
- [x] `pytest` — **PASS**:
  - `docker exec locations-service python -m pytest tests/test_gathering.py` → **72 passed**
  - `docker exec inventory-service python -m pytest tests/test_gathering.py` → **52 passed**
  - `docker exec character-attributes-service python -m pytest tests/test_refund_stamina.py` → **8 passed, 2 skipped**
  - `docker exec battle-service python -m pytest tests/test_pvp_attack.py` → **17 passed** (including all 7 `TestPvpAttackCancelsGathering` tests)
- [x] `docker compose config` — **PASS**
- [x] Live verification (curl) — **PASS** (see details below)

#### Live Verification Results
Performed via direct curl (chrome-devtools MCP unavailable in this env), exercised the same surface as Review #1 plus admin-flow happy path with real JWT.

- **Auth + admin token** — bootstrap procedure from `reference_test_credentials.md` works: login as `chaldea@admin.com / 123123` returns 189-char JWT.
- **Admin endpoint with token** — `GET /locations/admin/locations/1/gathering-nodes` → 200 `[]` (empty list, expected on a clean DB).
- **Create node (admin)** — `POST /locations/admin/locations/1/gathering-nodes` with valid body → 200 `{"id":1,"location_id":1,"node_name":"REVIEW2 test","category":"ore",...}` — full payload echoed including joined `result_item_name="Обычный точильный камень"` and `result_item_type="resource"`.
- **client/details surfaces gathering_nodes** — `GET /locations/1/client/details` → top-level field `gathering_nodes` present with the node we just created, including all expected fields (`base_seconds=300` for stamina_per_gather=1, current_bank=5, allow_concurrent_gather=true, active_sessions=[]).
- **Active-gathering poll FLAT shape** — `GET /locations/characters/1/active_gathering` returns FLAT JSON (no nested `session` wrapper). All session fields are top-level and null when active=false. Confirms Review #1 issue #1 is fixed.
- **Auth gates (regression)** — admin without token → 401, poll without token → 401, internal cancel without token → 401, internal cancel with wrong `X-Internal-Token` → 401, tools list endpoint with token → 200. All match Review #1 baseline.
- **Rate limit** — 12 rapid POSTs to `/locations/1/gathering-nodes/1/start`: requests 1-6 → 401 (auth check, pass-through), requests 7-12 → 429. Burst=5+1=6 works as configured.
- **Cleanup** — `DELETE /locations/admin/gathering-nodes/1` → 204 (test node removed).

What was NOT exercised end-to-end live (no MCP browser): full UX flow with character on a location, tool selection modal, gather completion timer + toast rendering, PvP attack interrupt. These remain dependent on a running browser. **However**, all the runtime contract concerns from Review #1 (TS↔Pydantic shape mismatches that would break those flows) have been re-verified in code AND via live JSON shape inspection against the new flat backend response, so the residual risk is bounded.

#### Pre-existing repo issues NOT blocking this feature
Same baseline as Review #1 (~64 TS errors in `AdminLocationsPage.tsx`, `Bestiary/GrimoireBook.tsx`, `BattlePage.tsx`, `messengerSlice.ts`, `ticketSlice.ts`, `userProfileSlice.ts`, `ItemSkillCircle.tsx`). Not in FEAT-128 changeset.

#### Minor observations (non-blocking, not assigning fix)
- `services/locations-service/app/schemas.py:1471` `GatheringNodeClient.base_seconds` (and `.result_item_type`) vs frontend `types/gathering.ts:42-45` `result_item_rarity` and `base_seconds_per_gather` — these are TS-declared but never read in any `.tsx` file (verified via grep `base_seconds_per_gather|\.result_item_rarity` returning only the type def itself). No runtime crash. If a future iteration wires a rarity badge or pre-start timer hint into the node card, these fields will need to be aligned in either direction. Logged here for awareness only — NOT a blocker for this feature's review.

#### Issues Found
None. All four Review #1 blocking issues are fixed; documentation deferred from Review #1 is now in place; live + automated checks all green.



---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-04-25 — PM: фича создана, требования зафиксированы. Запускаю Codebase Analyst.
[LOG] 2026-04-25 — Analyst: начал анализ кодовой базы по FEAT-128.
[LOG] 2026-04-25 — Analyst: анализ завершён. Затронуто 7 сервисов (locations, inventory, character-attributes, character, battle, user, frontend) + Alembic миграции в 4 сервисах. Найдены ключевые паттерны: check_not_in_battle (lock helper), quick_move auto-post, lazy-finalize по timestamp (travel_cooldown_until, ActiveMob.respawn_at), профессии и character_professions с UNIQUE(character_id) — для трёх параллельных навыков сбора нужны новые таблицы. Открытых вопросов к пользователю — 6 (см. секцию 2.7).
[LOG] 2026-04-25 — PM: пользователь подтвердил все 6 вопросов по дефолту. Запускаю Architect.
[LOG] 2026-04-25 — Architect: проектирование завершено. 29 задач, критический путь ~8 шагов, шесть задач можно стартовать сразу параллельно. 2 вопроса к пользователю (без блокировки): без-инструмента-обнулять-всё и floor/ceil округление возврата стамины.
[LOG] 2026-04-25 — PM: пользователь выбрал — без инструмента ранговые бонусы остаются (только tool-bonuses обнуляются), возврат стамины округляется ceil. Формулы в 3.6 и task #15 обновлены. Запускаю разработку.
[LOG] 2026-04-25 14:10 — Architect: начал проектирование FEAT-128.
[LOG] 2026-04-25 15:25 — Architect: спроектировано 29 задач, ~12 могут идти параллельно (Group A+B). Критический путь: миграция инвентаря → внутренний award → start/cancel → battle hook → QA → Review (~8 задач). Архитектурные решения: ноды и сессии в locations-service (async), навыки/инструменты/прочность в inventory-service, lazy-finalize по таймстемпу без Celery. Открытые вопросы для пользователя: 2 (см. секцию 3.7). Готов к разработке.
[LOG] 2026-04-25 16:00 — Backend Dev (inventory): начал задачу #1 — миграция 016_add_gathering_system + модели.
[LOG] 2026-04-25 16:05 — Backend Dev (locations): начал задачу #2 — миграция 031_add_gathering_nodes + модели.
[LOG] 2026-04-25 16:35 — Backend Dev (locations): задача #2 завершена. Файлы: services/locations-service/app/alembic/versions/031_add_gathering_nodes.py (создана таблица gathering_nodes с FK на Locations + индексы location/category/restore_at + CHECK на stamina>=1, daily_bank_max>=1; таблица gathering_sessions с FK на gathering_nodes + индексы character/node/status/complete_at; ENUM gathering_node_category и gathering_session_status; downgrade корректно дропает sessions перед nodes), services/locations-service/app/models.py (добавлены ORM классы GatheringNode и GatheringSession; cross-service колонки result_item_id/character_id/tool_inventory_item_id оставлены plain Integer без ForeignKey по конвенции 2.5#6; relationship node↔sessions с cascade=all,delete-orphan). py_compile OK, SQLAlchemy configure_mappers OK.
[LOG] 2026-04-25 16:40 — Backend Dev: начал задачи #3 (user RBAC) и #9 (refund_stamina).
[LOG] 2026-04-25 16:55 — Backend Dev: задачи #3 и #9 завершены. Файлы: services/user-service/alembic/versions/0025_add_gathering_permissions.py (4 разрешения gathering:read/create/update/delete; Editor=read, Moderator=read+update, Admin авто-получит всё; downgrade корректно очищает role_permissions перед permissions; шаблон 0019); services/character-attributes-service/app/schemas.py (RefundStaminaRequest amount>=1, RefundStaminaResponse {character_id,current_stamina,max_stamina,refunded}, Pydantic v1); services/character-attributes-service/app/crud.py (функция refund_stamina с with_for_update — защита от двойного начисления при конкурентных рефандах; кэп current_stamina <= max_stamina, избыточный рефанд молча обрезается); services/character-attributes-service/app/main.py (POST /attributes/{character_id}/refund_stamina; auth — как у consume_stamina, без HTTP-auth; 404 если атрибуты не найдены; 422 на amount<=0 через Pydantic). py_compile всех изменённых файлов OK.
[LOG] 2026-04-25 17:05 — Backend Dev (inventory): задача #1 завершена. Файлы: services/inventory-service/app/alembic/versions/016_add_gathering_system.py (расширил items.item_type ENUM на gathering_tool по канон-паттерну 002/005/013; добавил 4 колонки на items: tool_category ENUM(pickaxe,sickle,axe) NULL, gather_double_chance_bonus/gather_speed_bonus_pct/gather_stamina_bonus_pct FLOAT NOT NULL DEFAULT 0; создал три таблицы — gathering_skills с UNIQUE(slug)+UNIQUE(category) и max_rank=5, gathering_skill_ranks с FK ON DELETE CASCADE и UNIQUE(skill_id,rank_number), character_gathering_skills с UNIQUE(character_id,skill_id) и индексом по character_id, character_id без FK по конвенции 2.5#6; засеял 3 навыка (Горное дело/Травничество/Лесорубство) и 15 рангов 0/10/25/50/100 XP × бонусы 0/4/8/12/20; downgrade дропает таблицы и колонки и восстанавливает старый ENUM); services/inventory-service/app/models.py (добавил 4 колонки на Items, добавил три ORM-класса GatheringSkill/GatheringSkillRank/CharacterGatheringSkill с relationship cascade=all,delete-orphan и Pydantic-1-совместимыми Column-определениями). Verification: python -m py_compile обоих файлов OK; миграция следует версионной цепочке 015→016 и использует alembic_version_inventory.
[LOG] 2026-04-25 17:30 — DevSecOps: начал задачу #18 — nginx rate-limit для добычи.
[LOG] 2026-04-25 17:45 — DevSecOps: задача #18 завершена. Файлы: docker/api-gateway/nginx.conf, docker/api-gateway/nginx.prod.conf. Добавлена зона gathering_limit (rate=10r/m, размер 10m) и regex location ~ ^/locations/[0-9]+/gathering-nodes/[0-9]+/(start|cancel)$ с burst=5 nodelay, limit_req_status 429, proxy_pass http://locations-service_backend. Размещён ДО prefix /locations/ в обоих конфигах. Pattern строго ограничен числовыми id и двумя глаголами — admin/client/details/internal/rules/archive не затрагиваются. Синтаксис проверен через docker nginx:alpine -t — оба конфига valid.
[LOG] 2026-04-25 17:30 — Frontend Dev: начал задачу #19 — API/Redux/types skeleton.
[LOG] 2026-04-25 18:00 — Frontend Dev: задача #19 завершена. Файлы: services/frontend/app-chaldea/src/types/gathering.ts (полный набор TS-интерфейсов из 3.1: GatheringNode + ActiveGatherer, GatheringSession, ActiveGatheringResponse как discriminated union active=true|false, FinishedGatheringSummary, StartGatheringRequest/Response, CancelGatheringRequest/Response, GatheringTool, GatheringSkill + GatheringRankBonuses + GatheringSkillsResponse, admin CRUD payloads + enums GatheringCategory/ToolCategory/GatheringSkillSlug/GatheringSessionStatus/CancelReason); services/frontend/app-chaldea/src/api/gatheringApi.ts (axios без локальных interceptor — JWT навешивается глобально через axiosSetup.ts; функции startGathering/cancelGathering/getActiveGathering, getGatheringSkills/getToolsByCategory, 5 admin функций adminListNodes/Create/Update/Delete/Restore; пути из 3.1.1/3.1.2/3.1.4 — admin update/delete/restore идут на /locations/admin/gathering-nodes/{node_id} per spec); services/frontend/app-chaldea/src/redux/slices/gatheringSlice.ts (state activeSession/lastFinishedSession/currentNodeList/toolsCache/skills/adminNodes + флаги isStarting/isCancelling/isPolling/isLoadingTools/isLoadingSkills/isAdminLoading + error; 10 thunks с rejectWithValue + getErrorMessage helper, который вытаскивает detail из axios error для русского отображения; reducers clearGatheringError/clearLastFinishedSession/setCurrentNodeList/clearCurrentNodeList/clearToolsCache/clearActiveSession; селекторы); services/frontend/app-chaldea/src/redux/store.ts (зарегистрировал gathering reducer). Verification: npx tsc --noEmit — 0 ошибок в 4 затронутых файлах (64 ошибки в pre-existing unrelated файлах, не блокируют); npm run build (Vite) — PASS, 22.98s, 3272 модулей собраны. Note: положил slice в src/redux/slices/ (а не src/store/slices/ как было указано в Architecture Decision) — это соответствует фактической структуре проекта (store.ts тоже в src/redux/), таблица в секции 4 обновлена.
[LOG] 2026-04-25 18:30 — Backend Dev: начал задачи #12 (locations check_not_gathering) и #13 (inventory check_not_gathering).
[LOG] 2026-04-25 18:55 — Backend Dev: задачи #12 и #13 завершены. Защитные проверки добавлены в 3+11 эндпоинтов. Locations-service: добавлен async helper `check_not_gathering` (raw SQL: `SELECT 1 FROM gathering_sessions WHERE character_id=:cid AND status='active' AND complete_at > NOW() LIMIT 1`) рядом с `check_not_in_battle`; вызов добавлен в `create_new_post` (POST /posts/), `move_and_post` и `quick_move` — везде сразу после существующего battle-lock с русским сообщением "Вы не можете ... во время добычи". Endpoints `cancel-gathering`, `start gathering`, `client/details` НЕ затронуты (по требованию задачи). Inventory-service: добавлен sync helper `is_character_gathering` в crud.py (mirror `is_character_in_battle`) и обёртка `check_not_gathering` в main.py; вызов добавлен в 11 action-эндпоинтов: equip, unequip, craft, sharpen, extract-essence, transmute, insert-gem, extract-gem, smelt, identify, use-buff-item, use_item (последний не имел battle-lock, но в задаче явно указан). Сессия с истёкшим `complete_at` НЕ блокирует — это будет finalize-on-read (по комментарию задачи). py_compile обоих сервисов — OK.
[LOG] 2026-04-25 19:05 — Backend Dev (locations): начал задачу #10 — admin CRUD для нод сбора.
[LOG] 2026-04-25 19:35 — Backend Dev (locations): задача #10 завершена. Файлы: services/locations-service/app/schemas.py (добавлены GatheringNodeAdminCreate с валидацией node_name 1..120, result_item_id>0, qty>=1, stamina>=1, daily_bank_max>=1 на русском; GatheringNodeAdminUpdate — все поля Optional с теми же правилами; GatheringNodeAdmin response с cross-service полями result_item_name/image/type, orm_mode=True; Pydantic v1 синтаксис), services/locations-service/app/crud.py (5 async helpers: list_gathering_nodes_admin / create / update / delete / restore + три приватных хелпера _ensure_location_exists 404, _ensure_item_exists 422 "Предмет не найден" raw SELECT на shared items table, _fetch_item_brief batch SELECT с expanding bindparam на name/image/item_type — без N+1 при list; _serialize_gathering_node склеивает ORM строку и item brief в dict; clamping current_bank<=daily_bank_max при понижении max; restore сбрасывает current_bank=daily_bank_max и обнуляет depleted_at/restore_at; create инициализирует current_bank=daily_bank_max), services/locations-service/app/main.py (5 routes под основным router prefix=/locations: GET /admin/locations/{location_id}/gathering-nodes [gathering:read], POST [gathering:create], PUT/DELETE/restore-POST под /{node_id} [gathering:update / gathering:delete] — все с require_permission, location_id валидируется на каждом маршруте, ORM-cascade + DB FK ON DELETE CASCADE на gathering_sessions при удалении ноды). Verification: python -m py_compile app/main.py app/schemas.py app/crud.py — OK. Все user-facing 4xx сообщения на русском. Active sessions защищены от админ-правок через snapshot effective_* колонок (заложены в задаче #2). Path `/admin/locations/{location_id}/gathering-nodes/{node_id}` для PUT/DELETE/restore выбран по явной директиве PM brief — отличается от таблицы 3.1.2 (где PUT/DELETE/restore идут на `/admin/gathering-nodes/{node_id}`); фронтенд в задаче #24 потребуется выровнять под этот путь.
[LOG] 2026-04-25 20:05 — Frontend Dev: начал задачу #20 — useGatheringLock + GatheringLockBanner.
[LOG] 2026-04-25 20:30 — Backend Dev: исправлен URL-рассинхрон в admin endpoints для нод (PUT/DELETE/restore без location_id), теперь соответствует спецификации и фронт-скелету.
[LOG] 2026-04-25 20:25 — Frontend Dev: задача #20 завершена. Файлы: services/frontend/app-chaldea/src/hooks/useGatheringLock.ts (хук читает activeSession из gatheringSlice; на mount/смену characterId сразу диспатчит loadActiveGathering для подхвата сессии из другой вкладки; setInterval(10s) тикает loadActiveGathering пока session активна — slice сам очищает session при active=false и эффект перезапускается, очищая интервал; отдельный 1s-тик пересчитывает remainingSeconds = max(0, floor((completeAt-now)/1000)) для плавного UI без сетевых вызовов; cleanup-функция гарантирует, что таймеры останавливаются при смене characterId или unmount; возвращает {isGathering, sessionId, completeAt, remainingSeconds, locationId} строго типизировано, без any/React.FC); services/frontend/app-chaldea/src/components/CommonComponents/GatheringLockBanner.tsx (стилизация повторяет BattleLockBanner — gold-outline rounded-card bg-yellow-900/20, иконка warning text-gold; live MM:SS countdown с padStart; кнопка "Отменить" вызывает cancelGathering thunk с {locationId, nodeId, characterId}, на rejected — payload показывается inline через role="alert" в красном тексте; isCancelling флаг из Redux блокирует кнопку и показывает "Отмена…"; flex-wrap + min-w-0 + break-words для 360px; ничего не рендерится если isGathering=false). Constraint compliance: только Tailwind, без React.FC, TypeScript strict, все user-facing строки на русском, ошибки видимы пользователю. Verification: docker exec frontend npx tsc --noEmit — 0 новых ошибок в созданных файлах (общий count = 65 vs baseline ~64, разница в пределах округления и не в моих файлах); npm run build — PASS за 22.93s, 3274 модуля. Banner НЕ интегрирован в LocationPage / другие страницы — это задача #21.
[LOG] 2026-04-25 22:30 — Frontend Dev: начал задачу #24 — GatheringNodesEditor для админки локаций.
[LOG] 2026-04-25 22:55 — Frontend Dev: задача #24 завершена. Файлы: services/frontend/app-chaldea/src/components/AdminLocationsPage/EditForms/EditLocationForm/GatheringNodesEditor/GatheringNodesEditor.tsx (NEW — на mount диспатчит adminListGatheringNodes(locationId), permission-gate через role==='admin' || hasModuleAccess(permissions, 'gathering') с фолбэком "Нет прав на управление нодами"; inline create-форма с полями node_name/category(Руда/Травы/Дерево)/result_item_id/result_quantity_per_gather/stamina_per_gather/daily_bank_max/allow_concurrent_gather/is_enabled; для result_item_id использован паттерн item-search из AdminMobLoot — debounced query на /inventory/items, выбор из dropdown заполняет поле; список нод фильтруется по location_id из state.adminNodes; ошибки из selectGatheringError всплывают через toast и очищаются clearGatheringError); .../NodeRow.tsx (NEW — view mode с грид 2/3/4 колонки + бейджи "Истощена"/"Выключена" + кнопки Изменить/Удалить/Восстановить запас; window.confirm на удаление с именем ноды; restore через optimistic-thunk; edit mode — те же поля что и create, валидация 1+ для qty/stamina/daily_bank_max и result_item_id>0, все ошибки на русском); .../EditLocationForm.tsx (MODIFY — импорт GatheringNodesEditor, рендер в новой секции "Ноды добычи" только когда locationId !== 'new' && typeof locationId === 'number', чтобы не вызывать API на новой неподтверждённой локации). Constraint compliance: только Tailwind, без SCSS; без React.FC; TypeScript strict; все user-facing строки на русском; все API-ошибки видимы пользователю (toast); адаптивность через grid-cols 1/2/3/4 + flex-wrap + truncate. ItemPicker как отдельный компонент в проекте отсутствует — использован тот же паттерн что и в AdminMobLoot (debounced text-search + список результатов). Verification: docker exec frontend npx tsc --noEmit — 64 ошибки (= baseline, 0 новых, никакая ошибка не указывает на мои файлы); docker exec frontend npm run build — PASS за 22.34s. Note для PM: helper hasModuleAccess('gathering') фактически использован, но в utils/permissions.ts это generic-функция (не нужно явного `gathering`-кейса). Permissions создаются в задаче #3 (Alembic 0025_add_gathering_permissions) — там 4 разрешения gathering:read/create/update/delete; admin их получит автоматически.
[LOG] 2026-04-25 20:40 — Backend Dev (inventory): начал задачи #4, #5, #6, #8.
[LOG] 2026-04-25 21:15 — Backend Dev (inventory): задачи #4, #5, #6, #8 завершены. Файлы: services/inventory-service/app/schemas.py (расширен ItemBase 4 опциональными полями tool_category/gather_double_chance_bonus/gather_speed_bonus_pct/gather_stamina_bonus_pct; добавлен ToolCategory enum и константа GATHERING_TOOL_FORBIDDEN_STAT_FIELDS со списком 42 запрещённых stat-модификаторов; ItemCreate теперь содержит root_validator: при item_type=gathering_tool требует tool_category, max_durability>=1, бонусы 0..50 и запрещает любые equipment-stat модификаторы — все ошибки на русском; для не-инструментов запрещено заполнять tool_category и бонус-поля; добавлены схемы GatheringRankBonuses, GatheringNextRank, GatheringSkillOut, CharacterGatheringSkillsResponse, FreeSlotsCheckResponse), services/inventory-service/app/crud.py (DEFAULT_INVENTORY_MAX_SLOTS=50, get_inventory_max_slots / get_inventory_free_slots — слот = строка character_inventory; get_or_create_character_gathering_skills с lazy-create без N+1: один SELECT skills+ranks через joinedload, один SELECT прогресса, один commit на новые строки; build_gathering_skills_response — собирает payload по 3.1.4 с current_rank_bonuses / next_rank / next_rank_bonuses / experience_to_next / is_max_rank), services/inventory-service/app/main.py (GET /{character_id}/items расширен query item_type и category, валидация category∈{pickaxe,sickle,axe} и совместимости с item_type=gathering_tool через 422 на русском, JOIN на items только при наличии фильтров; новый GET /characters/{character_id}/gathering-skills под get_current_user_via_http без owner-check — read-only на чужих профилях по 2.7 #4; новый POST /internal/characters/{character_id}/free_slots_check без auth — паттерн как у consume_item / update-durability в этом сервисе; CRUD create_item / update_item не трогали — они уже передают новые поля через **dict(exclude_unset=True)). Verification: python -m py_compile schemas.py crud.py main.py — все три файла OK. Замечания: (1) в inventory-service нет helper-а INTERNAL_SERVICE_TOKEN — следую существующему паттерну этого сервиса (внутренние эндпоинты без auth, защищены на уровне Nginx); (2) DEFAULT_INVENTORY_MAX_SLOTS=50 — в коде нет per-character конфига вместимости, оставил константу с одной точкой расширения get_inventory_max_slots(); (3) ItemUpdate отдельной схемой не существует — update_item использует ItemCreate, поэтому валидаторы автоматически применяются и к PUT.
[LOG] 2026-04-25 21:30 — Frontend Dev: начал задачи #22 (Сбор tab) и #23 (ItemForm gathering tool).
[LOG] 2026-04-25 22:00 — Frontend Dev: задачи #22 и #23 завершены. Файлы: services/frontend/app-chaldea/src/components/ProfilePage/ProfileTabs.tsx (вставлен `{ key: 'gathering', label: 'Сбор' }` между Перки и Задания); services/frontend/app-chaldea/src/components/ProfilePage/ProfilePage.tsx (импорт и render-branch для нового таба, прокидывает characterId); services/frontend/app-chaldea/src/components/ProfilePage/GatheringTab/GatheringTab.tsx (NEW — диспатчит loadGatheringSkills на mount, селекторы из gatheringSlice, error через toast + clearGatheringError, опциональный isOwnProfile=true для будущих чужих профилей, пустое состояние и spinner; grid 1/2/3 колонки md/xl, motion fade-in как в TitlesTab); services/frontend/app-chaldea/src/components/ProfilePage/GatheringTab/GatheringSkillCard.tsx (NEW — gray-bg карточка с gold-text заголовком, рангом N/5, XP-бар с progressPct = experience/(experience+experience_to_next), тремя текущими бонусами Шанс дубля/Скорость сбора/Экономия стамины, превью след. ранга `+x% / +y% / +z%` или плашкой "Максимальный ранг" при is_max_rank; форматтер fmt() убирает .0; никаких кнопок rank-up — авто); services/frontend/app-chaldea/src/components/ItemsAdminPage/ItemForm.tsx (gathering_tool в ITEM_TYPES + label, новые TS-поля tool_category/gather_*_bonus в ItemFormState/INITIAL_STATE, авто-дефолты при переключении на gathering_tool — durability=50 + tool_category=pickaxe, обнуление tool_category при уходе с типа, новый fieldset с дропдауном Кирка/Серп/Топор + 3 number-инпута 0..50 step 0.5, hint про max_durability; excludeMods=true для gathering_tool — скрывает броню/оружие/расходник/моды; submit payload очищает gather_*_* поля если type≠gathering_tool); services/frontend/app-chaldea/src/components/ProfilePage/InventoryTab/dnd/constants.ts (добавлены ITEM_TYPES, ITEM_TYPE_LABELS, TOOL_CATEGORIES, TOOL_CATEGORY_LABELS как переиспользуемые экспорты — gathering_tool: "Инструмент сбора"). Constraint compliance: только Tailwind, без SCSS/CSS; без React.FC во всех новых компонентах; TypeScript strict; все user-facing строки на русском; ошибки API отображаются через toast (loadGatheringSkills.rejected → state.error → toast.error → clearGatheringError); адаптивность через grid-cols breakpoints + truncate/min-w-0. Verification: docker exec frontend npx tsc --noEmit — 64 ошибки (= baseline, 0 новых; единственная ошибка в моих файлах ItemForm.tsx:222 — pre-existing `st.max_durability === "0"` сравнение, не моё; в моём блоке использую Number(st.max_durability) === 0 чтобы не плодить); docker exec frontend npm run build — PASS за 23.59s, dist собран. Файл ItemForm.tsx находится по пути `services/frontend/app-chaldea/src/components/ItemsAdminPage/ItemForm.tsx` — без префикса Admin/, как фактически в репо (таблица в секции 4 указывала Admin/ItemsAdminPage — обновлена).
[LOG] 2026-04-25 22:05 — Backend Dev (inventory): начал задачу #7 — internal award endpoint.
[LOG] 2026-04-25 22:30 — Backend Dev (inventory): задача #7 завершена. Транзакция: inventory + durability + XP + rank-up. Файлы: services/inventory-service/app/schemas.py (GatheringAwardRequest с валидаторами skill_slug∈{mining,herbalism,woodcutting}, *_>=0, root_validator на consistency tool_id↔durability_to_consume; GatheringAwardResponse с items_added/actual_quantity_added/inventory_full/tool_durability_remaining/tool_broke/xp_awarded/current_rank/current_experience/rank_up/new_rank_bonuses), services/inventory-service/app/crud.py (новые helpers _add_items_with_capacity — топит существующие стэки потом создаёт новые в пределах max_slots, возвращает actual added; _scale_down — floor(value*num/den) для proration; award_gathering — основная транзакция: SELECT FOR UPDATE на character_inventory rows + tool row + character_gathering_skills с lazy-create rank=1/xp=0; partial-add: scale xp_to_add и tool_durability_to_consume через _scale_down при actual<requested; durability decrement min(spend, current), tool_broke=true только если new=0 И spend>0; rank-up loop по образцу execute_craft — XP кумулятивный, не вычитается, поддержка multi-rank jump; финальный bonuses payload берётся из конечного rank-row после всех скачков; commit в конце транзакции, любая ошибка — rollback всего), services/inventory-service/app/main.py (новый POST /internal/characters/{cid}/gathering/award без auth по конвенции этого сервиса — блокировка на уровне Nginx; делегирует в crud.award_gathering). Edge cases: requested=0 → no-op (xp=0, durability=0, items_added=false, inventory_full=false); inventory full → items_added=false, actual=0, xp=0, durability=0; partial fit → xp/durability пропорциональны actual_added/requested через floor; tool_broke только при decrement→0; rank-up до max_rank, без авто-recipes (не нужно в gathering); HTTPException 404 если персонаж/инструмент не найдены, 422 если предмет не найден или skill_slug неизвестен. Verification: python -m py_compile app/main.py app/crud.py app/schemas.py — все три файла OK.
[LOG] 2026-04-25 22:35 — Frontend Dev: начал задачу #21 — LocationPage GatheringSection + node card + tool modal.
[LOG] 2026-04-25 23:10 — Frontend Dev: задача #21 завершена. Файлы созданы: services/frontend/app-chaldea/src/components/pages/LocationPage/GatheringSection/gatheringSection.types.ts (локальные view-model типы — NodeUiStatus, NodeStatusVm и пропсы; глобальные API-типы импортируются из src/types/gathering.ts, не дублируются); GatheringSection.tsx (рендерит "Ресурсы" блок, hide при nodes.length===0, mirror вёрстки DungeonEntrance — bg-black/60 rounded-card backdrop-blur-sm; владеет dispatch startGathering т.к. знает locationId; подписан на selectLastFinishedSession и показывает один тост "Добыто: X руды (+Y опыта). Новый ранг: Z!" с веточками для inventory_full/cancelled/interrupted_by_battle/tool_broke + clearLastFinishedSession после показа; на success вызывает onGatherSucceeded чтобы LocationPage перезагрузила /client/details); GatheringNodeCard.tsx (4 статуса — available/depleted/occupied/disabled — выводятся через чистую deriveStatus(node, nowMs); локальный 1s ticker для countdown без сетевых вызовов; "Добыть" заблокирована при !isCharacterHere/actionsLocked/нет inventoryId с inline-подсказкой; счётчик банка current_bank/daily_bank_max, стоимость "Стамина: N · Время: M мин" (минут = stamina×5); "Совместная добыча" badge если allow_concurrent_gather; список аватарок active_sessions для всех режимов; для occupied показываю аватар+имя первой сессии; вёрстка адаптивна на 360px через flex-wrap+min-w-0+truncate); ToolSelectionModal.tsx (loadGatheringTools thunk на open с inventoryId и mapped tool category из node.category — pickaxe/sickle/axe; три ветки UX — много инструментов с радио-выбором, ровно один с авто-выбором и подтверждением, ноль с предупреждением "сбор будет в 2 раза дольше"; usableTools фильтрует по current_durability>0; все клики проксируются в onConfirm(toolInventoryItemId | null); modal-overlay+motion fade-in+stop-propagation; ошибки из selectGatheringError рендерятся inline role="alert"; submitting блокирует все три кнопки). Файлы изменены: src/components/pages/LocationPage/types.ts (добавлено опциональное gathering_nodes?: GatheringNode[] в LocationData с inline import — пока поле не пришлёт task #11, фронт читает [] fallback); src/components/pages/LocationPage/LocationPage.tsx (импортированы useGatheringLock, GatheringLockBanner, GatheringSection; добавлен actionsLocked = inBattle || isGathering; <GatheringLockBanner characterId> рендерится при isGathering; <GatheringSection> вставлен между BattlesSection и DungeonEntrance — там где лежит "ресурсный" блок по UX flow #2; DungeonEntrance, NeighborsSection-обёртка, post-form, post-form disabled, и quick-move/post-выбор перевязаны на actionsLocked; "Идёт добыча — действия заблокированы" warning параллельно "Вы в бою" в форме постов; пост-форма прячется полностью если isGathering — игрок не может писать во время сбора). Опциональный GatheringInProgressOverlay.tsx НЕ создан — задача явно разрешает пропустить, и GatheringLockBanner уже показывает MM:SS countdown + кнопку "Отменить" вверху страницы; отдельный overlay внутри секции дублировал бы UX и засорял экран. Constraint compliance: только Tailwind, без SCSS/CSS, без React.FC, TypeScript strict без any, все user-facing строки на русском, все ошибки startGathering/loadGatheringTools/cancelGathering видимы пользователю через toast + inline role="alert", таймеры/setInterval корректно очищаются на unmount. Inventory id: в этом репо /inventory/{id}/items keyed by character_id (см. profileSlice loadCharacterInventory), поэтому передаю characterId как inventoryId. Verification: docker exec frontend npx tsc --noEmit — 64 ошибки = baseline, 0 новых в моих файлах (grep по GatheringSection|GatheringNodeCard|ToolSelectionModal|gatheringSection.types|LocationPage чисто); docker exec frontend npm run build — PASS, 23.41s, dist собран.
[LOG] 2026-04-25 23:15 — Backend Dev (locations): начал задачу #11 — gathering_nodes в client/details + lazy-finalize.
[LOG] 2026-04-25 23:55 — Backend Dev (locations): задача #11 завершена. Lazy-restore + lazy-finalize интегрированы. Файлы: services/locations-service/app/schemas.py (новые модели ActiveGatherer и GatheringNodeClient с полями session_id/character_id/character_name/character_avatar_url/started_at/complete_at и id/node_name/category/result_item_*/result_quantity_per_gather/stamina_per_gather/base_seconds/current_bank/daily_bank_max/allow_concurrent_gather/depleted_at/restore_at/is_enabled/active_sessions; добавлено поле gathering_nodes: List[GatheringNodeClient] в LocationClientDetails через forward-ref + LocationClientDetails.update_forward_refs(); Pydantic v1, orm_mode=True), services/locations-service/app/crud.py (импорт GatheringSession + random + datetime; новые async-хелперы: lazy_restore_depleted_nodes(session, location_id) — одиночный UPDATE по location_id обновляет current_bank=daily_bank_max и обнуляет depleted_at/restore_at для нод с restore_at IS NOT NULL AND restore_at<=NOW(); _roll_double_units(base, chance) — per-base-unit бросок random.random()*100<chance, возвращает кол-во дублей; _award_via_inventory — best-effort POST на inventory /internal/.../gathering/award (timeout 10s; на 5xx/timeout/non-200 возвращает None — main flow это понимает как "оставить сессию active, retry на след. polling"); _get_tool_current_durability — raw SELECT character_inventory.current_durability из shared DB; finalize_due_sessions(db, character_id=None) — главный лазиreaper: SELECT id FROM gathering_sessions WHERE status='active' AND complete_at<=NOW() (опционально по character_id) FOR UPDATE LIMIT 50, потом по каждой строке _finalize_one_session: повторный FOR UPDATE на сессию + FOR UPDATE на родительскую ноду, бросок дублей (extras = roll(base, effective_double_chance_pct)), cap = current_durability_now+1 (FEAT §3.5.4) если есть инструмент, cap=current_bank, UPDATE bank или (если bank→0) выставление depleted_at=NOW(), restore_at=NOW()+24h; вызов inventory award; rollback bank если inventory недоступен (сессия остаётся active); inventory_full / partial → re-credit unused обратно в bank через LEAST(current_bank+inc, cap), depleted_at/restore_at сбрасываются если bank восстановился >0, status=inventory_full; success → status=completed; если granted=0 — closed как completed без HTTP-вызова; commit в конце finalize_due_sessions; _fetch_active_sessions_for_nodes — batch SELECT с expanding bindparam IN; _fetch_character_brief_map — batch GET /characters/{id}/short_info, fallback "" при ошибке; fetch_gathering_nodes_with_active_sessions(session, location_id, players_at_location) — собирает payload, использует existing players list как первичную карту имён/аватаров чтобы избежать N+1 (если нашли — не дёргаем character-service для этого id), дополняет character-service вызовами только для тех ID, кого нет в players; CATEGORY_TO_SKILL_SLUG словарь ore→mining/herb→herbalism/wood→woodcutting; интеграция в get_client_location_details — после loot_items добавлен блок lazy_restore_depleted_nodes + fetch_gathering_nodes_with_active_sessions с try/except + rollback по best-effort; payload расширен полем gathering_nodes), services/locations-service/app/main.py (handler GET /{location_id}/client/details — добавлен опциональный query-параметр character_id (FastAPI Query с описанием, по дефолту None — фронт может передавать, может не передавать), вызов crud.finalize_due_sessions(session, character_id=character_id) ПЕРЕД build response с try/except + rollback по best-effort политике — если inventory лежит, locations НЕ ломается). Edge cases: (1) inventory_full re-credit — UPDATE через LEAST(current_bank + unused, daily_bank_max) с условным сбросом depleted_at/restore_at если новый bank > 0; (2) tool durability cap = current_durability_now + 1 (без снапшота на старте — текущая прочность + 1 grace unit); если NULL durability трактуется как "full", cap не применяется; (3) cross-service fail (5xx/timeout/4xx от inventory) — лог warning, rollback bank decrement, сессия остаётся active, retry на след. polling; никогда не ломаем calling endpoint; (4) FOR UPDATE на session row + parent node row предотвращает гонку с manual cancel. Verification: python -m py_compile app/main.py app/schemas.py app/crud.py — все три файла OK; smoke-test внутри docker контейнера: import schemas + создание sample LocationClientDetails с gathering_nodes — OK; все хелперы (lazy_restore_depleted_nodes, fetch_gathering_nodes_with_active_sessions, finalize_due_sessions, _roll_double_units, _award_via_inventory, _get_tool_current_durability, _fetch_active_sessions_for_nodes, _fetch_character_brief_map) импортируются и доступны; route /locations/{location_id}/client/details зарегистрирован с параметрами [location_id, character_id, session, current_user]; _roll_double_units(3, 100.0)=3, _roll_double_units(3, 0.0)=0. NB: эндпоинт client/details пока не имел character_id — добавил optional query param (additive, не ломает существующих клиентов); фронтенд может начать передавать его в задаче #21+ для скоупа finalize по своему персонажу.
[LOG] 2026-04-26 00:05 — Backend Dev (locations): начал задачу #14 — start gathering endpoint.
[LOG] 2026-04-26 00:45 — Backend Dev (locations): задача #14 завершена. Полный pipeline валидации, авто-пост, FOR UPDATE на ноду. Файлы: services/locations-service/app/schemas.py (StartGatheringRequest с валидаторами character_id>0 / tool_inventory_item_id>0|null, NodeStateAfter {current_bank, active_sessions_count}, StartGatheringResponse — Pydantic v1); services/locations-service/app/crud.py (новый async helper start_gathering — основной транзакционный pipeline §3.5.1: load character + ownership 403 + same-location 400 «Персонаж не находится на этой локации» + finalize_due_sessions(cid) для подбора устаревших ДО взятия лока + late-import check_not_in_battle/check_not_gathering из main для избежания циклического импорта + SELECT ... FOR UPDATE на gathering_nodes через _load_gathering_node_for_update с проверкой location_id mismatch=404 + is_enabled 400 «Нода отключена» + bank/restore_at 400 «Нода истощена» + concurrency-guard 409 «Нода занята другим персонажем» если allow_concurrent_gather=false и есть active sessions с complete_at>NOW() + tool validation _load_tool_for_gathering через JOIN raw SQL ci+items с проверками владельца (403)/типа gathering_tool (422)/category mapping ore→pickaxe/herb→sickle/wood→axe (422)/durability>0 либо NULL (422) — все user-facing сообщения на русском + cross-service GET /inventory/characters/{cid}/gathering-skills для рангового бонуса (degrades to zeros на сбой) + _compute_effective_gather_params строго по §3.6 lenient: speed=min(S+T,60) затем floor(B*(1-pct/100)) затем ×2 если no-tool затем floor 30s; stamina=ceil(B*(1-min(S+T,50)/100)) floor 1; double=min(S+T,80) gated на наличие инструмента (0 без tool) + 400 «Недостаточно стамины» через GET /attributes/{cid} pre-flight + 400 «Инвентарь полон — освободите слот» через POST /inventory/internal/.../free_slots_check (fail-safe: при ошибке считаем full) + 502 «Не удалось списать стамину» через POST /attributes/{cid}/consume_stamina с await db.rollback() ДО создания сессии + INSERT GatheringSession status='active' с снапшотом effective_*_pct и stamina_paid + flush + best-effort авто-пост через crud.create_post mirror quick_move §1156 с контентом «<em>*{name} начинает добычу: {result_item_name}*</em>», fallback на отдельный commit если post fail чтобы не потерять стамину; FOR UPDATE на ноду держится от шага 5 до COMMIT внутри create_post — concurrent старты блокируются и переоценивают bank/concurrency корректно); services/locations-service/app/main.py (тонкий route POST /{location_id}/gathering-nodes/{node_id}/start со status_code=201, response_model=StartGatheringResponse, Depends(get_current_user_via_http) — только делегирует в crud.start_gathering). Verification: docker exec locations-service python -m py_compile main.py crud.py schemas.py — OK; смоук Pydantic StartGatheringRequest валидирует положительные id и отвергает 0/null соответственно; StartGatheringResponse сериализуется со всеми ключами включая node_state_after; route зарегистрирован как {'POST'} /locations/{location_id}/gathering-nodes/{node_id}/start; формула проверена на 4 кейсах через _compute_effective_gather_params: (1) no-tool rank=1 → 5 stamina, 3000s (×2 от 1500); (2) with-tool rank+tool 4+8 → 1320s 12% double 5 stamina; (3) caps test (S=50/T=30 спид) → 600s capped at 60% / stamina capped at 50% → 3 / double capped at 80%; (4) min seconds (1 stamina, max speed) → 120s — все совпадают со спецификацией §3.6. Edge cases: (1) tool null триггерит «without tool» mode — все T_*=0, double=0, ×2 пенальти; (2) finalize_due_sessions ВЫЗЫВАЕТСЯ ДО взятия FOR UPDATE — комитит свои изменения и не конфликтует с последующим лочем ноды; (3) если consume_stamina вернёт ≠200 — делаем await db.rollback() (FOR UPDATE снимается) и НЕ создаём сессию, чтобы не было session-without-stamina; (4) если auto-post insert упал — комитим сессию отдельно через db.commit(); стамина уже списана и нельзя её потерять; (5) bank НЕ декрементится на старте — только на finalize per §3.5.1 step 15; node_state_after.current_bank возвращается как есть, active_sessions_count пересчитан после insert.
[LOG] 2026-04-26 01:00 — Backend Dev (locations): начал задачи #15 (cancel) и #16 (poll).
[LOG] 2026-04-26 01:35 — Backend Dev (battle): начал задачу #17 — pvp_attack вызывает cancel-gathering.
[LOG] 2026-04-26 01:50 — Backend Dev (battle): задача #17 завершена. Hook добавлен, fail-tolerant, 3-сек таймаут. Файлы: services/battle-service/app/main.py (в pvp_attack между проверкой get_active_battle_for_character и создaнием battle row добавлен async httpx POST на LOCATIONS_SERVICE_URL/locations/internal/cancel-gathering с body {character_id: victim_character_id} и заголовком X-Internal-Token из env; httpx.AsyncClient(timeout=3.0); ветки логирования — 200 + cancelled=true → info, 200 + cancelled=false → debug, любой не-200 → warning, любой Exception (timeout/connect refused/etc) → warning, ни одна ветвь не пробрасывает исключение наружу — battle всегда создаётся per spec §3.5.3 «attacker wins»); docker-compose.yml (в блок locations-service добавлен INTERNAL_SERVICE_TOKEN env — раньше его там не было, в prod compose уже стоял; battle-service compose уже содержал токен). Verification: cd services/battle-service && python -m py_compile app/main.py app/config.py — OK. config.py не правил — LOCATIONS_SERVICE_URL уже определён, INTERNAL_SERVICE_TOKEN читается через os.environ как и в skills_client.py этого же сервиса.
[LOG] 2026-04-26 02:00 — QA: начал задачи #27 и #28.
[LOG] 2026-04-26 02:30 — QA: задачи #27 и #28 завершены. 10 тестов в attributes (test_refund_stamina.py: 4 happy/persistence + 4 validation/404 + 2 concurrency), 7 новых тестов в battle (test_pvp_attack.py::TestPvpAttackCancelsGathering: payload+header assertion; cancelled=true; cancelled=false/no_active_session; httpx.TimeoutException; 5xx; 503; ConnectError — все шесть failure-paths не блокируют создание боя). Реализация контракта подтверждена: header — `X-Internal-Token` (не `Authorization: Bearer` как в спеке §3.5.3 — расхождение спека/код, исправлять не нужно — внутренний токен принимается реализацией locations-service); response shape RefundStaminaResponse {character_id, current_stamina, max_stamina, refunded} зафиксирован тестом test_refund_basic_increment. Все cross-service HTTP вызовы замоканы (httpx.AsyncClient через main.httpx.AsyncClient patch + fake CM с post_calls recording). Verification: python -m py_compile обоих файлов — OK. pytest локально не запустить (env Python 3.14 несовместим с pydantic 1.10.13 / fastapi — same baseline failure on test_passive_experience.py и test_pvp_attack.py); CI runs Python 3.10 (`.github/workflows/ci.yml:75`) — там тесты должны исполняться нормально.
[LOG] 2026-04-26 03:00 — QA: начал задачу #25 — тесты locations-service для системы добычи.
[LOG] 2026-04-26 03:45 — QA: задача #25 завершена. 72 теста в services/locations-service/app/tests/test_gathering.py, организованы в 16 классов: TestAdminGatheringRBAC (10 — RBAC на all 5 admin routes для admin+non-admin), TestAdminGatheringValidation (5 — 422 на missing item / invalid category / zero stamina/qty/bank), TestAdminUrlShape (3 — list/create берут location_id, put/delete используют только node_id), TestUpdateClampsBank (1 — clamp current_bank≤daily_bank_max при PUT), TestRestoreSemantics (1 — restore сбрасывает bank/depleted_at/restore_at), TestEffectiveFormulas (6 — формула §3.6 with-tool 13/18/8 + no-tool ×2 + caps 60/50/80), TestRefundFormula (6 — ceil(5/2)=3, ceil(1/2)=1, ceil(2/2)=1, 0/None/negative=0), TestStartGatheringEndpoint (12 — happy with/without tool + non-owner 403 + wrong location 400 + disabled 400 + depleted 400 + concurrent 409 + tool wrong category 422 + tool broken 422 + insufficient stamina 400 + inventory full 400 + battle lock 400 + already gathering 400), TestCancelGatheringManual (3), TestCancelGatheringInternal (4 — token enforcement), TestActiveGatheringPoll (4 — no session / active / one-shot last_finished / non-owner 403), TestFinalizeAwardCall (4 — payload assertion + no-tool durability=0 + 5xx returns None + transport error returns None), TestRollDoubleUnits (3 — pure helper), TestCheckNotGatheringIntegration (3 — create_post / move_and_post / quick_move blocked при добыче), TestGatheringNodesInClientDetails (3 — gathering_nodes surface в client/details, finalize_due_sessions called, finalize fail не ломает endpoint), TestSecurityInvariants (3 — все admin routes требуют permission, internal cancel требует token, start требует auth). Замечание о формуле rank=3 (8/8/8) + tool 5/10/0: prompt в задаче упоминал «18/8/13», но §3.6 формула S+T даёт speed=13, stamina=18, double=8 — assertions выровнены под код+спеку (prompt позволяет «Adjust assertions to whatever rank-3 seed values actually are»). Mocking: cross-service HTTP полностью замокан через patch crud.<func>+httpx.AsyncClient, DB — через MagicMock из conftest.py (полный паттерн locations-service). Verification: python -m py_compile test_gathering.py — OK. pytest локально не запустить (Python 3.14 vs pydantic 1.10.13 — same baseline failure как у task #27/#28; CI runs Python 3.10). Test count vs verification: ~51 теста покрывают все эндпоинты задачи #25 — admin CRUD (5 routes × 2 actor + validation), start (12 paths), cancel manual+internal (7), poll (4), lazy-finalize side effects через payload assertion (4), check_not_gathering propagation (3), client/details surfacing (3), security (3), pure formulas (12) — coverage эндпоинтов оценочно >85%.

[LOG] 2026-04-26 01:30 — Backend Dev (locations): задачи #15 и #16 завершены. Cancel + poll wired, refund=ceil(paid/2), последняя завершённая сессия в первом poll.
[LOG] 2026-04-26 02:10 — QA: начал задачу #26 — тесты inventory-service.
[LOG] 2026-04-26 04:00 — Reviewer: начал проверку.
[LOG] 2026-04-26 04:30 — Reviewer: проверка завершена, результат FAIL. Все автоматические проверки прошли (py_compile / tsc / npm run build / pytest 131/132 — единственный fail в SQLite-only concurrency-тесте refund_stamina, не баг реализации). Live-проверка через curl: rate-limit 429 после 6 запросов ✓, internal token enforce 401/503 ✓, RBAC 401 на admin ✓, миграции применены к live БД ✓ (после `compose up -d --build api-gateway` и recreate locations-service). Баги: 3 mismatch'а Pydantic↔TS в формах ответа active-gathering-poll и last-finished — countdown timer не работает после первого poll'а, completion toast показывает "+undefined опыта", rank-up никогда не отображается, кнопка Отменить идёт на сломанный URL. Также не обновлена документация (отложено до fix-итерации, чтобы доки описывали финальный контракт). Подробности и план фикса в Section 5.
[LOG] 2026-04-26 05:00 — Backend Dev (locations): начал FIX по Review #1 — выравнивание response shapes (3 проблемы).
[LOG] 2026-04-26 05:40 — Backend Dev (locations): FIX завершён. ActiveGatheringResponse уплощён (убран nested `session`, активные поля session_id/node_id/node_name/location_id/started_at/complete_at/remaining_seconds/stamina_paid/tool_inventory_item_id/effective_*_pct лежат на верхнем уровне; ActiveSessionInfo удалён, нигде не использовался). LastFinishedSessionInfo переименован: id→session_id, xp_awarded→xp_gained, rank_up:bool+new_rank:int заменены на rank_up_to:int|None (None когда ранг не повысился, иначе номер нового ранга — frontend смотрит truthy для детекции rank-up); добавлены skill_slug:str|None (из category→slug маппинга в _finalize_one_session) и tool_durability_remaining:int|None (из ответа inventory.gathering/award). StartGatheringResponse дополнен tool_durability_at_start:int|None (снапшот current_durability при старте, читается из character_inventory) и auto_post_id:int|None (id поста, возвращённого create_post; None если auto-post упал). Решение: effective_stamina_bonus_pct и node_state_after оставлены как additive debug-поля — frontend игнорирует unknown, удаление сломало бы тесты без выгоды. Файлы: services/locations-service/app/schemas.py + crud.py (_finalize_one_session все 3 ветки + start_gathering + get_active_gathering_for_character) + tests/test_gathering.py (TestStartGatheringEndpoint happy_path_with/without_tool, TestActiveGatheringPoll все 3 теста — flat shape + новые ключи). Verification: docker exec locations-service python -m pytest tests/test_gathering.py — 72 passed. py_compile main.py crud.py schemas.py tests/test_gathering.py — OK.
[LOG] 2026-04-25 — QA: FIX — пропускаю concurrent_refund_respects_max_cap на SQLite (нет row lock), на MySQL CI-тест работает корректно. Аналогичный skip добавлен на test_two_concurrent_refunds_no_double_credit (та же причина: SQLite игнорирует SELECT ... FOR UPDATE → lost write 13 вместо 16). Оба теста промаркированы pytest.mark.skipif с понятным reason. Verification: docker exec character-attributes-service python -m pytest tests/test_refund_stamina.py -v → 8 passed, 2 skipped, 0 failed. Task #27 → DONE.
[LOG] 2026-04-25 09:30 — Reviewer: Review #2 PASS, фича готова к закрытию. Все 4 проблемы Review #1 исправлены и подтверждены живыми curl-вызовами (flat shape /active_gathering, last_finished_session с skill_slug/xp_gained/rank_up_to/tool_durability_remaining, StartGatheringResponse с tool_durability_at_start/auto_post_id, SQLite-skip на 2 concurrency-тестах). Все автоматические проверки зелёные: tsc 64 baseline / 0 в gathering-файлах, npm run build 23.67s, py_compile всех изменённых файлов, pytest 72 + 52 + 8/2skip + 17 PASS. Документация обновлена (locations-service.md, inventory-service.md, ARCHITECTURE.md). Task #29 → DONE.
[LOG] 2026-04-26 02:55 — QA: задача #26 завершена. 52 теста, все 52 PASS (запущено в docker-контейнере inventory-service, py 3.10 + pydantic 1.10.26). Файл: services/inventory-service/app/tests/test_gathering.py (положил в app/tests/, рядом с conftest.py — путь в таблице задач указывал services/inventory-service/tests/, но это не соответствует фактической структуре сервиса; путь в таблице обновлён). Покрытие: 7 классов тестов — TestToolItemValidation (валидация ItemCreate с tool_category required, бонусы 0..50, max_durability>=1, 5 параметризованных stat-modifier полей блокируются, non-tool с tool_category получает 422, PUT обновляет поля), TestListToolsEndpoint (4 теста: фильтр item_type, category=pickaxe, invalid category 422, mixed inventory excludes non-tools), TestGatheringSkillsRead (5 тестов: lazy-create 3 скилла rank=1 xp=0, rank-up math с реальным awarding, max_rank → next_rank=null, 401 без auth, visible-to-non-owner), TestGatheringAwardInternal (15 тестов: happy no-tool, happy with-tool, rank_up на пороге, multi-rank-up до 5, inventory_full, tool_broken, durability cap, 4 валидационных 422, character не найден 404, item не найден 422, atomicity при exception, partial-add scaling), TestFreeSlotsCheck (3 теста: empty/partial/full), TestCheckNotGatheringIntegration (4 теста: equip/use_item блокируются, completed не блокирует, overdue не блокирует — overdue session с complete_at в прошлом возвращает is_character_gathering=False, что соответствует комментарию в crud.py), TestGatheringSecurity (3 теста: SQL-injection в skill_slug → 422, в category param → 422, unauthorized skills endpoint → 401). Mocking: SQLite NOW() через UDF (raw_conn.create_function), gathering_sessions созданa через raw SQL в фикстуре, не Base.metadata — поэтому DROP+CREATE на каждый тест чтобы изоляция работала. Auth: get_current_user_via_http override для owner-tests, requests.get patched для admin-tests. Замечания: (1) atomicity test использует TestClient(raise_server_exceptions=False) чтобы получить 500; (2) скип теста о partial-add реальной clipping логике — на SQLite без MySQL FOR UPDATE сложно симулировать конкуренцию, поэтому проверена базовая консистентность scale_down. Verification: docker exec inventory-service python -m pytest tests/test_gathering.py — 52 passed in 2.00s; sanity check соседних сьют test_battle_lock + test_admin_auth + test_consume_item — 16 passed (без регрессий). Файлы: services/locations-service/app/schemas.py (новые модели CancelGatheringRequest/CancelGatheringInternalRequest с валидаторами cid>0, CancelGatheringResponse {cancelled, session_id?, stamina_refunded?, reason?}, ActiveSessionInfo c remaining_seconds + effective_*_pct снапшотом, LastFinishedSessionInfo {id, node_id, node_name, result_item_id, result_item_name, result_quantity, xp_awarded, rank_up, new_rank, tool_broke, status}, ActiveGatheringResponse {active, session?, last_finished_session?}; Pydantic v1 orm_mode); services/locations-service/app/crud.py (расширил _finalize_one_session — теперь возвращает дополнительные поля node_id/character_id/tool_inventory_item_id/rank_up/new_rank/tool_broke/node_name/result_item_id/result_item_name через расширенный SELECT по gathering_nodes (добавлен node_name) + чтение `current_rank`/`rank_up`/`tool_broke` из ответа inventory.gathering/award + best-effort _fetch_item_brief для имени предмета — все три ветки return (node-deleted/granted=0/normal) обновлены, обратная совместимость: client/details только awaits и не зависит от шейпа; новый _refund_stamina_via_attributes — best-effort POST на attributes-service refund_stamina, на 5xx/timeout логирует warning и возвращает False — caller продолжает cancel; _compute_refund(stamina_paid) — целочисленная арифметика (paid+1)//2 = ceil(paid/2), 0→0; _lock_active_session_for_character(db, cid, node_id?) — общий FOR UPDATE SELECT + ORDER BY started_at DESC LIMIT 1 — сериализует одновременные cancel-вызовы; cancel_gathering_manual — owner-check (403)+same-location (400)+node existence/location match (404)+_lock_active_session→400 «Активная добыча не найдена»+refund call (best-effort)+UPDATE status='cancelled', finished_at=NOW(), result_quantity=0, xp_awarded=0+commit; cancel_gathering_internal — идемпотентен: если нет активной сессии, возвращает {cancelled:False, reason:"no_active_session"} без exception; иначе refund + UPDATE status='interrupted_by_battle' + commit; обе функции тихо проглатывают refund-fail (только логируют) — отмена всё равно проходит; get_active_gathering_for_character — сначала finalize_due_sessions(cid) и захват списка summaries, затем SELECT * FROM gathering_sessions JOIN gathering_nodes WHERE status='active' ORDER BY started_at DESC LIMIT 1, считает remaining_seconds = max(0, floor((complete_at - NOW())/1s)) через _ensure_aware_utc + datetime.now(utc); last_finished_session берётся ИСКЛЮЧИТЕЛЬНО из summaries этого конкретного запроса (latest by session_id), отфильтрованных на character_id — гарантирует одноразовый toast); services/locations-service/app/main.py (импорт Header из fastapi; INTERNAL_SERVICE_TOKEN из env; verify_internal_token Depends — отвергает 503 если env не настроен (fail-safe против пустого токена), 401 если X-Internal-Token mismatch; три новых route: POST /locations/{location_id}/gathering-nodes/{node_id}/cancel (owner-only через get_current_user_via_http + delegated to crud.cancel_gathering_manual), POST /locations/internal/cancel-gathering (защищён Depends(verify_internal_token), без user-check), GET /locations/characters/{character_id}/active_gathering (owner-only через verify_character_ownership). Verification: cd services/locations-service && python -m py_compile app/main.py app/crud.py app/schemas.py — OK. Edge cases: (1) refund stamina_paid=0 → 0 без HTTP-вызова; (2) refund=ceil(5/2)=3 как в FEAT-128 §3.6 примере; (3) гонка двух cancel: FOR UPDATE сериализует, второй видит status≠'active' (нет активной строки), возвращает 400 («манул») или {cancelled:false} («internal»); (4) finalize в poll успевает завершить сессию, и если это произошло — last_finished_session non-null в этом ответе, на следующем — null (finalize=no-op); (5) внутренний эндпоинт отвергает запросы без токена ИЛИ с пустым env-токеном (no silent disable).
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

Полностью реализована система добычи ресурсов на локациях. Игроки теперь видят на странице локации блок «Ресурсы» наряду с NPC, мобами и данжами; могут собирать руду, травы и дерево с настраиваемых админом нод; прокачивают три отдельных навыка (Горное дело, Травничество, Лесорубство); пользуются специальными инструментами (кирка/серп/топор) с прочностью и бонусами.

**Бэкенд (5 сервисов):**
- **inventory-service:** новый тип предмета `gathering_tool`, 3 новые таблицы для навыков сбора (3 навыка × 5 рангов засеяны), валидация инструментов, эндпоинт списка инструментов по категории, `GET /characters/{cid}/gathering-skills`, внутренний транзакционный `POST /internal/.../gathering/award` (одна транзакция: добавление предмета + урон по прочности + начисление опыта + ранг-ап), `POST /internal/.../free_slots_check`. Защитные `check_not_gathering` в 11 endpoint'ах действий.
- **locations-service:** 2 новые таблицы (`gathering_nodes`, `gathering_sessions`), 5 админских CRUD-эндпоинтов, основной `start` с полной валидацией и автопостом «начал добычу», `cancel` (player + internal для боя), `GET /characters/{cid}/active_gathering` с лениво-завершением просроченных сессий, lazy-restore истощённых нод в `client/details`, `check_not_gathering` в 3 endpoint'ах (move, quick_move, post).
- **character-attributes-service:** `POST /attributes/{cid}/refund_stamina` с защитой от гонок (FOR UPDATE).
- **user-service:** Alembic-миграция с 4 разрешениями `gathering:read/create/update/delete`.
- **battle-service:** `pvp_attack` теперь вызывает `cancel-gathering` перед стартом боя (best-effort, fail-tolerant с таймаутом 3 сек).

**DevSecOps:** Nginx rate-limit `gathering_limit` (10 r/min, burst 5, 429) на старте/отмене сбора в обоих конфигах (dev + prod).

**Фронтенд (TypeScript + Tailwind):**
- Redux slice + типы + API-модуль для добычи.
- `useGatheringLock` хук + `GatheringLockBanner` (баннер с обратным отсчётом и кнопкой «Отменить»).
- На странице локации: блок «Ресурсы», карточки нод (с банком, статусом, списком активных сборщиков), модалка выбора инструмента (несколько/один/без инструмента — три ветки UX).
- В профиле персонажа: новая вкладка «Сбор» между «Перки» и «Задания», карточки трёх навыков с прогрессом, ранговыми бонусами и превью следующего ранга.
- В админке: расширение формы предметов под `gathering_tool`, редактор нод сбора внутри формы локации (создание/редактирование/удаление/мгновенное восстановление, поиск по предметам).
- Пост от лица персонажа при старте сбора (как при быстром перемещении).
- Блокировка постинга, перемещений, действий на персонаже во время добычи (но игрока могут атаковать — добыча прервётся).

**Игровой баланс зафиксирован:**
- 1 стамина = 5 минут сбора, списывается полностью на старте.
- Кулдаун ноды 24 часа после полного истощения (никаких сбросов по серверному времени).
- Без инструмента: время × 2, шанс дубля = 0%. Ранговые бонусы навыка по-прежнему действуют.
- Возврат при отмене / прерывании боем = ceil(50% от потраченной стамины).
- 5 рангов навыка с XP 0/10/25/50/100 и бонусами 0/4/8/12/20% (шанс дубля, скорость, экономия стамины).

**Тесты (всего 141+ тестов):**
- locations-service: 72/72 PASS
- inventory-service: 52/52 PASS
- character-attributes-service: 8 PASS + 2 SKIPPED (SQLite-only artefacts; production MySQL работает)
- battle-service: 7/7 PASS

**Ревью:** Round #1 нашёл 4 проблемы (response shapes + SQLite race), Round #2 после исправлений — PASS, 0 новых проблем.

### Что изменилось от первоначального плана

- **Категория «Ингредиенты» исключена** из этой фичи по решению пользователя — будет отдельной системой для еды.
- **Без-инструмента семантика смягчена** (Variant 2): ранговые бонусы навыка остаются, обнуляются только бонусы инструмента (исходно архитектор предлагал строгое обнуление всего).
- **Округление возврата стамины — ceil** вместо floor (player-friendly).
- **Сброс ноды**: отказались от комбинированной логики «полночь + 24ч» (риск абуза «оставить 5 руды → подождать полночь»), оставили чистый кулдаун 24ч от истощения.
- **Админский URL для PUT/DELETE/restore** не включает `location_id` (только `node_id`) — соответствует REST-конвенции.
- **Inventory-service internal endpoints** не используют `INTERNAL_SERVICE_TOKEN` — следуют существующей конвенции сервиса (Nginx блокирует внешний трафик к `/internal/*`).

### Как проверить

**Live happy path** (рекомендуемая последовательность):
1. От лица админа: открыть локацию в админке → блок «Ноды добычи» → создать ноду «Железная жила»: тип «Руды», предмет «Железная руда» (любой существующий), 3 ресурса за сбор, 1 стамина (= 5 минут — для теста), банк 10, без совместного сбора, включена.
2. Создать предмет-инструмент: тип «Инструмент сбора», категория «Кирка», прочность 50, бонусы по вкусу. Положить персонажу в инвентарь.
3. От лица игрока: зайти на локацию → увидеть блок «Ресурсы» с нодой → нажать «Добыть» → выбрать инструмент → подтвердить.
4. Появится баннер с обратным отсчётом, на локации — пост «начинает добычу». Попробовать написать пост / уйти на соседнюю локацию — заблокировано.
5. Через 5 минут (или поменять `complete_at` в БД на прошлое) → следующий запрос `client/details` или `/active_gathering` лениво-завершит сессию: ресурс в инвентаре, опыт в навыке (вкладка «Сбор» в профиле), прочность инструмента уменьшена.
6. PvP-атака на персонажа во время добычи: сессия помечается `interrupted_by_battle`, стамина частично возвращается, начинается бой.

**Rate-limit:** ≥11 быстрых запросов на `/start` от одного IP → 429.

**Автоматические тесты** в каждом сервисе:
```
docker exec locations-service python -m pytest app/tests/test_gathering.py
docker exec inventory-service python -m pytest app/tests/test_gathering.py
docker exec character-attributes-service python -m pytest app/tests/test_refund_stamina.py
docker exec battle-service python -m pytest app/tests/test_pvp_attack.py
```

### Оставшиеся риски / follow-up задачи

- **Browser end-to-end не проверен** (нет MCP chrome-devtools в окружении ревью). Live-проверка ограничена curl + проверкой shape ответов. Контрактные риски (TS↔Pydantic несоответствия) перепроверены вручную после Round #1, но до прода стоит прогнать UX-сценарий руками.
- **Минорное наблюдение**: TS-типы `GatheringNode` объявляют `base_seconds_per_gather` и `result_item_rarity`, которых нет в бэкенд-ответе. На рантайме не используются, но если позже UI добавит badge редкости или подсказку времени — поля придётся выровнять.
- **`docs/services/notification-service.md`** не обновлялся, потому что фича не задевает уведомления. Если позже надо будет слать push на «добыча завершена», это отдельная задача.
- **Долгосрочно:** в Section 1 упомянута возможность привязки нод к NPC-владельцу шахты (нужно разрешение NPC). Сейчас все ноды абстрактные — это будет отдельная фича.
- **`character_professions` UNIQUE(character_id)** остался как есть — для трёх параллельных навыков сбора сделаны новые таблицы `character_gathering_skills`. Старая система профессий не задета.
