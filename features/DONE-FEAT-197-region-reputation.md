# FEAT-197: Репутация региона (этап 1)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-03 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Репутация персонажа в каждом регионе — основа последствий в ролевой: «чёрное и белое», у каждого поступка свой вес, последствия разные (не торгуют / дают скидку, закрывают доступ, позже — стража, тюрьма). Этап 1 — каркас: хранение, вес действий, торговля, доступ, ручная правка, журнал.

### Общий план (этапы)
- **Этап 1 (эта фича):** репутация региона, вес действий, отголосок в соседние регионы страны, забывание отрицательной, влияние на торговлю, гейты доступа, ручная правка админом/ведущим с причиной, журнал, отображение игроку.
- **Этап 2 (потом):** стража (штраф/изгнание/атака по ступени), **тюрьма** (обязательно: проигрыш страже → заключение на N часов в локации-тюрьме, выйти нельзя), скрытность (броски на свидетелей, розыск, подозрение региона, отложенное раскрытие, маска, тайная дурная слава), слава (громкость: узнаваемость, крупные задания, титулы, повышает шанс свидетелей).
- **Отдельный модуль (будущее):** фракции и организации — ранги, награды, тематичные задания и заказы, своя репутация, тонкие настройки каждой фракции.

### Бизнес-правила этапа 1
- Репутация — число на пару (персонаж, регион), диапазон примерно −1000…+1000 (точный диапазон и пороги — настройки).
- **Ступени** (названия и пороги настраиваются): Враг, Недруг, Подозрительный, Чужак (≈0, стартовая), Знакомый, Уважаемый, Почитаемый, Герой края. Игрок видит **ступень и полоску**, без чисел.
- **Вес действий** — настраиваемая в админке таблица «действие → очки». Источники, существующие сейчас:
  - выполнение задания (вес зависит от задания — у задания поле веса/репутации; по умолчанию от «размера» задания), регион = регион квестодателя;
  - сдача товара по заказу гильдии (FEAT-193), регион заказа;
  - убийство мирного NPC (FEAT-064 «Нападение») — сильный минус в регионе NPC;
  - помощь в событиях региона — если есть подходящий хук; иначе на будущее;
  - (будущее: нападение на караван, преступления — уже предусмотреть тип действия, но без источника).
- **Ручная правка**: админ/ведущий (RBAC-разрешение) меняет репутацию персонажа в регионе на ±N с **обязательной причиной**; можно и через «действие» из таблицы.
- **Отголосок**: часть изменения (по умолчанию 20 %, настройка) применяется к остальным регионам той же страны.
- **Забывание**: только отрицательная репутация медленно ползёт к нулю (скорость — настройка), положительная не убывает.
- **Журнал**: каждое изменение (кто/что, регион, дельта, причина, итог) пишется в историю; игрок видит свою историю (без чисел — формулировки «Жители N стали относиться к вам лучше/хуже»? — на усмотрение архитектора, без утечки точных чисел), админ — с числами.
- **Торговля**: модификатор цены у торговцев региона по ступени — от «Уважаемого» и выше скидка (до −15 % у Героя), ниже «Чужака» — наценка; **«Враг» — обычные торговцы отказываются торговать** (теневые торговцы — будущий модуль). Модификатор складывается с харизмой (FEAT-195) — архитектор определяет порядок и защиту от арбитража (гильдия/перепродажа, см. FEAT-193 правило «гильдия платит ≥ лучшего бида, ≤ floor(ask×0.5)»).
- **Гейты доступа** по минимальной ступени (настраивается в админке на объекте): задания (квестодатель/задание), NPC (диалог/услуги), покупка дома в регионе, займы в банке, телепорт. Отказ — понятное русское сообщение.
- Отображение: вкладка/блок «Репутация» в профиле персонажа (по регионам), строка «Ваша репутация: Уважаемый» на карточке региона на карте мира.

### UX
1. Игрок сдаёт задание жителю — в журнале «Жители края Х стали относиться к вам лучше», полоска растёт; при переходе ступени — уведомление.
2. Игрок убивает мирного NPC — репутация в регионе резко падает, соседние регионы страны — слабее.
3. «Уважаемый» видит у торговцев скидку (в окне торговца видна причина: «скидка за репутацию»), «Подозрительный» — наценку, «Враг» — отказ с понятным текстом.
4. Задание/NPC с порогом репутации — недоступно с объяснением «нужна репутация: Уважаемый».
5. Админ в карточке персонажа видит репутацию по регионам с числами, может поправить с причиной.

### Edge Cases
- Персонаж ещё не бывал в регионе — репутация 0 (Чужак), строки нет до первого изменения.
- Регион без страны — отголоска нет.
- Регионы, не участвующие в экономике (без торговцев с кассой) — гейты и цены всё равно работают где применимо.
- Повторная сдача/отмена задания — без двойного начисления (идемпотентность по событию).
- Персонаж-NPC/моб — репутации нет.

### Решения пользователя (2026-11-03, после анализа)
- **Ступени и пороги** (диапазон −1000…+1000, всё настраивается, названия переименовываются в админке):
  Вне закона ≤ −600 · Изгой −599…−300 · На заметке −299…−100 · **Скиталец** −99…+99 (стартовая) · Знакомое лицо 100…299 · Свой человек 300…599 · Заступник 600…899 · Легенда края ≥ 900.
  Торговля: скидка от «Свой человек» (до −15 % у «Легенда края»), наценка от «На заметке» и ниже, «Вне закона» — обычные торговцы не торгуют.
- **Убийство NPC — вес по роли** (настраивается в админке, у конкретного NPC можно переопределить, включая положительный): разбойник +20, наёмник −30, обычные жители (торговец, кузнец, алхимик, бард, мудрец, жрец, целитель, охотник, странник, аукционист, банкир, монетчик, гильдия, мастер телепорта, герой) −150, стражник −300, правитель/король −1000. Нужно передавать убийцу и сделать событие идемпотентным.
- **Права:** новое разрешение на правку репутации (напр. `reputation:manage`), админ — автоматически, **модераторам** — выдать. Роли «ведущий» нет.
- **Вес задания:** новое поле «репутация за задание» в редакторе заданий, по умолчанию +10.

### Решения пользователя
- [x] Оси сейчас: только регион; фракции — отдельный модуль позже; слава — этап 2, если будет понятная польза
- [x] Ручная правка и автоматика — обе
- [x] Тюрьма — нужна (этап 2)
- [x] Забывание — только отрицательная
- [x] Этап 1: репутация региона, вес действий, торговля, доступ, ручная правка, журнал

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Nothing about reputation exists yet (grep `reputation|репутац` over code and docs: 0 hits). All paths below are relative to `services/`.

### 2.1 Geography: regions, countries, adjacency

- **Owner: locations-service** (`locations-service/app/models.py`). `Countries` (L28), `Regions` (L51), with `Regions.country_id` **NOT NULL**, FK CASCADE (L56). So every region has a country. The brief's edge case "region without a country" cannot happen in the data model; it only matters for `Countries.is_hidden` (L42). `Districts.region_id` (L83), `Locations.district_id` / `Locations.region_id` / `parent_id` (L120-126). A location belongs to a region through its own `region_id`, else its district's `region_id`, else its parent chain.
- **Canonical resolver (use this, do not write a new one):** `econ_core.SQL_RESOLVE_LOCATION` (`character-service/app/econ_core.py:687`, a byte-identical copy in 4 services) is a recursive CTE that returns `(region_id, country_id)`. It is wrapped by `econ_ledger.resolve_location`: sync in `character-service/app/econ_ledger.py:105`, async in `locations-service/app/econ_ledger.py:108`. There is a duplicate ORM walk in `locations-service/app/houses.py:557` (`_region_of_location`). `house_plots.region_id` is denormalised (`models.py:1065`).
- **Adjacency:** `region_transition_arrows` (`locations-service/app/models.py:604`). `economy_events_crud.neighbour_map` (`character-service/app/economy_events_crud.py:155`) already builds region neighbours from those arrows in both directions, falling back to same-country regions, but only for *economy-participating* regions. The brief's echo is "other regions of the same country", which needs only `SELECT id FROM Regions WHERE country_id = :c`. Adjacency is not required.

### 2.2 Where the consumers and sources live (ownership options)

| Concern | Service | Entry point |
|---|---|---|
| Quests (accept/complete/list) | locations-service (async) | `main.py:3228-3415`, `crud.py:5163/5237/5474` |
| NPC dialogue / shop (buy/sell) / NPC gate | locations-service | `main.py:841` `_require_npc_gate`, `main.py:2522`, `2787`, `2856`, `3034` |
| Houses (plot buy, resale) | locations-service | `houses.py:720`, `houses.py:2266` |
| Guild orders hand-in | character-service (sync) | `economy_api.py:1097`, `economy_guild_crud.py:605` |
| Bank loans | character-service | `economy_api.py:748`, `economy_bank_crud.py:773` |
| Teleport master | character-service | `main.py:4459`, `crud.py:3756` |
| NPC death (Нападение) | battle-service → character-service | `battle-service/app/main.py:2537` → `character-service/app/main.py:3959` |
| Econ 6h tick (decay host candidate) | character-service | `econ_tick.py:1302` (`run_tick`), `econ_scheduler.py` |
| Character journal | character-service | `models.py:384`, `crud.py:3626`, `main.py:4322/4360` |
| Notifications producer | character-service `producer.py` (aio_pika → `general_notifications`); locations-service `rabbitmq_publisher.py:45/60` | |
| Region card (world map) | character-service | `economy_api.py:265` `/characters/economy/regions/{id}/card` (public) |

Observations for the Architect (current state, not a decision):
- character-service already holds the whole economy layer (econ_* tables, tick, admin "Экономика" with RBAC `economy:*`), `characters` (is_npc, npc_role, npc_status), logs, the NPC-death endpoint, guild, bank and teleport. That covers 4 of the 5 sources/gates plus the tick and the journal.
- locations-service holds quests, shop, dialogue and houses: the hottest read paths for gates and pricing.
- **Shared-DB raw-SQL reads across owners are an established pattern.** locations-service reads character-service's `econ_settings`, `econ_sim_settings`, `econ_goods_groups`, `econ_accounts`, `econ_operations`, `econ_postings` (`locations-service/app/crud.py:4471/4751/4862`, `econ_core.py:705/1098`). character-service reads locations' `region_transition_arrows`, `Regions` and `Locations`. So whichever service owns the tables, the other can read tier/value by plain SQL without HTTP. Writes from a non-owner should go through an internal endpoint (`/…/internal/…` + `X-Internal-Token`, the pattern in `character-service/app/main.py:3959` and `4322`) or a shared write helper.
- HTTP already exists: locations → character-service (internal routes), character → locations (`character-service/app/locations_client.py:328` `check_npc_gate`), battle → character-service (internal).

### 2.3 Source hooks

**Quest completion** (`locations-service/app/main.py:3276` `complete_quest`)
- Flow: ownership → activity lock → `check_quest_completable` → `complete_quest_record` (conditional `active→completed`, `crud.py:5474`; a concurrent second completion gets 404). Then gold via `pay_character(..., idempotency_key=f"quest_reward:cq:{cq_id}")` (`main.py:3341`), XP, a single `commit` (~L3353), then items over HTTP, then `_track_cumulative_stats` and auto-progress.
- Idempotency anchor: `character_quests.id` (`cq_id`). Repeatable quests delete the old row and create a new one on re-accept (`crud.py:5269-5276`), so each completion has a fresh `cq_id`. A key like `quest:cq:{cq_id}` is naturally unique. Abandon (`main.py:3402`) never grants anything, so it has no double-count risk. **The reputation write should be in the same transaction before the commit** (as the gold is) if the tables are local, or after the commit with the key if remote.
- Region: `quest.npc_id` → `characters.current_location_id` (`crud.get_npc_location`, `crud.py:4893`) → `resolve_location`. The same lookup is already done for the gold (`main.py:3330-3333`). The region is taken at completion time, and the NPC may have moved or died.
- **No quest "size" or weight field.** `quests` (`models.py:486`) has `quest_type` ('standard'|'daily'|'repeatable', `QuestEditor.tsx:76-80`), `min_level`, `reward_currency`, `reward_exp`, `reward_items`, and objectives. A default weight must be derived (e.g. from type, reward or objective count) or a new column `reputation_delta` NULL = default is needed. Admin: `POST/PUT /locations/admin/quests` (`main.py:3159/3197`, `crud.create_quest` 5026 / `update_quest` 5092), schemas `QuestCreate/QuestUpdate/QuestRead` (`schemas.py:1194/1206/1217`), UI `frontend/.../AdminNpcsPage/QuestEditor.tsx`.

**Guild order hand-in** (`character-service/app/economy_guild_crud.py:605` `hand_in`, router `economy_api.py:1064` `_guild_commit`)
- All of it runs in ONE sync transaction, committed in `_guild_commit` (L1072). The region is `ctx.region_id` (NPC location resolved, `guild_context` L415). The idempotency key is `guild:{character_id}:{request_id}` (L614, `KEY_HAND_IN` L54), and duplicates are pre-checked (L622) and enforced by the ledger. The posting is `econ_ledger.post_operation(... idempotency_key=key)` (~L706). A reputation write placed after the posting (step 10/10a) inherits that idempotency. Possible weight inputs: `acc.total`, `accepted`, `units`.

**NPC kill via «Нападение» (FEAT-064)**
- The FEAT-064 file is still `OPEN`, but the mechanics are live. The frontend `hooks/useNpcAttack.ts:42` creates `POST /battles/` with `battle_type:'pvp_attack'`. `battle-service/app/main.py:2537` (inside `_finalize_battle`, L2358; callers L4320 killing blow, L6586 timeout sweeper) iterates the losing participants with `hp<=0` that are `is_npc=1 AND npc_role != 'mob'`, and calls `PUT /characters/internal/npc-status/{id}` `{status:'dead'}` (`character-service/app/main.py:3959`).
- **Gaps:** (1) the request carries no killer, but `battle_state["participants"]` has the winner team, so the killers are winning participants with `is_npc=0`. (2) `update_npc_status` sets the status unconditionally and does not report a `alive→dead` transition, so it has no idempotency. A hook needs a conditional update (`WHERE npc_status='alive'`) or a key such as `npc_kill:{battle_id}:{npc_id}`. (3) Admin force-finish (`main.py:5391`) does not kill NPCs, which is consistent.
- "Peaceful" NPC: there is no flag. `npc_role` is free text (`models.py:65`, `String(50)`). Roles are listed in `frontend/.../constants/npc.ts` and include `bandit`, `mercenary` and `guard`. **Business question for PM:** do bandits count as "мирный"? Otherwise a per-NPC flag or role list is needed.
- NPC region: `characters.current_location_id` of the NPC at death → `resolve_location`.

**Region events** (`character-service/app/econ_events.py`, `economy_events_crud.py`)
- These are purely tick-driven (triggers `random|low_stability|manual`, `econ_events.py:28`). There is **no player-participation hook** and no character id anywhere in events. Per the brief this stays a future source; only reserve the action type.

**Future sources** (caravan attack, crimes): there is no code. Caravans live in `econ_caravan.py` / `economy_caravan_crud.py` (tick only, no player interaction).

### 2.4 Gate insertion points (min tier) and where admin edits the object

| Gate | Check point | Object / admin config today |
|---|---|---|
| Quest list | `crud.get_available_quests_for_npc` (`locations-service/app/crud.py:5163`) filters by `min_level`; add tier filter/flag here (or return `locked` + reason) | `quests` row; `QuestEditor.tsx`; `/admin/quests` |
| Quest accept | `crud.accept_quest` (`crud.py:5237`), next to the `min_level` check L5252-5256 (raises 400 "Требуется уровень N"), the same place for "нужна репутация: X" | same |
| Quest complete | `main.py:3276` (optional; tier could drop mid-quest — design decision) | same |
| NPC dialogue / shop / services | `_require_npc_gate` (`locations-service/app/main.py:841`, used by buy L2882 / sell L3059); dialogue open `main.py:2522` (inline gate L2543-2555). Guild calls it remotely via `locations_client.check_npc_gate` (`economy_api.py:1102`). Bank/mint/teleport do NOT pass this gate | `characters` row of the NPC (character-service `NpcUpdate` `schemas.py:761`, `PUT /characters/admin/npcs/{id}` `main.py:3082`, UI `AdminNpcsPage.tsx`) |
| House purchase | `houses.buy_house` (`locations-service/app/houses.py:720`) after the location check L729-731; resale `buy_listed_house` (`houses.py:2266`) | `house_plots` (`models.py:1060`); `POST/PUT /locations/houses/admin/plots` (`houses.py:1844/1855`); UI `Admin/HousesAdminPage/PlotFormModal.tsx` |
| Bank loan | `economy_bank_crud.take_loan` (`character-service/app/economy_bank_crud.py:773`) next to `loan_cap` (L792-795) | per-region `econ_banks` row (`models.py:743`); `PUT /characters/admin/economy/banks/{region_id}` (`economy_api.py:789`); UI `Admin/EconomyPage/EconomyBanks.tsx` / `RegionBankPanel.tsx` |
| Teleport | `crud.execute_teleport` (`character-service/app/crud.py:3756`) after the location check (~L3790); options list `crud.list_teleport_options_for_npc` (L3716) for display | `teleport_links` per link (`models.py:400`, only `cost_gold`) or the teleport-master NPC; `/admin/teleport-links` (`main.py:4478/4491`), `update_teleport_link_cost` (crud L3932); UI `AdminNpcsPage/TeleportLinksPanel.tsx` |

Regions for gates: quest → the quest-giver NPC's location; NPC → the NPC's location; house → `house_plots.region_id`/location; bank → `econ_banks.region_id` (= banker region, `with_region` L302); teleport → the source NPC's location (or the destination's, a design choice).

Dialogue options already have an unused `condition` JSON column (`locations-service/app/models.py` `DialogueOption.condition`). It is stored by `crud.py:4080/4161` and **never evaluated**. A tier condition could hook in there later.

### 2.5 Merchant pricing and arbitrage

- Only **locations-service** applies charisma: `_fetch_charisma` (`main.py:2741`, HTTP to character-attributes `/attributes/internal/{id}`). In `get_npc_shop` (L2787) a personal `discounted_buy_price` is shown only when `character_id` is passed. In `buy_from_npc` (L2856) the code is `discount = econ_core.charisma_discount_pct(charisma)`, then `unit_price = econ_core.discounted_ask(prices["ask"], discount)` (L2914-2916), and `discount_percent` is returned. **Selling (`sell_to_npc` L3034, `crud.quote_bids` L4628, `get_sell_offers` L4655) has no charisma.** The bid is fixed by `econ_core.market_bid`.
- **econ_core invariants** (`character-service/app/econ_core.py`):
  - `MAX_CHARISMA_DISCOUNT = 0.5` (L734).
  - `discounted_ask` (L895) clamps pct to **0..50** (a negative pct, i.e. a markup, is clamped to 0, so it cannot express a markup).
  - `market_bid` (L847) caps the bid at `ask_discount_floor(ask) = floor(ask*0.5)` (L860).
  - The guild pays `max(best_bid, min(offer, floor(cheapest_ask*0.5)))` (`econ_guild.unit_price`, `character-service/app/econ_guild.py:154`). Its quotes `region_quotes` (`economy_guild_crud.py:333`) use the raw ask with no charisma.
  - So the system relies on: **the lowest price anyone pays ≥ ceil(ask×0.5) ≥ floor(ask×0.5) ≥ any bid / guild price**. A reputation discount that pushes the total discount past 50 % breaks this, because the player could buy below the guild or merchant bid. Feeding `charisma_pct + rep_pct` into `discounted_ask` keeps it safe automatically (clamped at 50). A markup for low tiers needs a separate path (e.g. multiply ask before the discount, or a new function).
- **Byte-identical copies:** `econ_core.py` exists in character-, inventory-, locations- and dungeon-service (all md5 `1d75f73c…` today), guarded by CI job `econ-contract-copies` (`.github/workflows/ci.yml:116`, `scripts/check_econ_copies.sh`). The same applies to `tests/econ_contract_cases.py`. Any new pure price function in econ_core must be copied to all 4. Alternatively, keep reputation maths out of econ_core (locations-local), which avoids the copy churn but splits pricing logic.
- **Refuse to trade:** there is a precedent `_require_shop_open` → 409 "Торговец мёртв — лавка закрыта" (`main.py:2710-2718`). A tier refusal fits there (buy, sell, and probably `GET /shop` with `character_id`). `MerchantMarket.region_id` (`crud.py:4267/4286`) already resolves the merchant's region, both living and legacy.
- **Frontend price reason:** `frontend/.../pages/LocationPage/NpcShopModal.tsx:95-100` treats only `discounted_buy_price < buy_price` as a discount. `L279-313` shows a single "Скидка: N%" computed client-side. A markup (discounted > buy) is not displayed, and there is no source breakdown. The response `discount_percent` (buy) is also a single number. The schemas `NpcShopItemRead` / `ShopTransactionResponse` live in `locations-service/app/schemas.py`.

### 2.6 Journal and notifications
- `character_logs` (`character-service/app/models.py:384`: `event_type`, `description`, `metadata` JSON). The writer is `crud.create_character_log` (`crud.py:3626`), with the internal POST at `main.py:4322`. The owner reads it via `GET /characters/{id}/logs` (`main.py:4360`) **with metadata included**, so putting numeric deltas in metadata would leak numbers to the player (the brief says no numbers for players). A dedicated reputation history table, with admin-only numbers, avoids that. The frontend tab is `ProfilePage/LogsTab`.
- Notifications: JSON `{target_type:'user', target_value, message, category}` → queue `general_notifications`. The producer is `character-service/app/producer.py` (async aio_pika, `CATEGORY_PROGRESS`), with a sync variant `locations-service/app/rabbitmq_publisher.py:60`. Categories are in `notification-service/app/notification_categories.py:25-44`: `messages, social, trade, party, world, progress` (configurable), plus `battle, system`. A tier change fits `progress` (or `world`). Consumers need `user_id`, which comes from `characters.user_id`.

### 2.7 RBAC
- Pattern: user-service Alembic data migration, idempotent SELECT-then-INSERT, `ROLE_ACTIONS` map. See `user-service/alembic/versions/0032_add_economy_permissions.py` (last revision `0032`; the next is `0033`, and revision ids are limited to 32 chars). Admin gets everything automatically. Moderator=role_id 3, Editor=2.
- The test must be added explicitly: `user-service/tests/test_rbac_permissions.py` has a separate section per module (economy at L1300-1321 `_seed_economy_permissions`), per CLAUDE.md §10.13.
- Backend check: `require_permission("module:action")` exists in both `character-service/app/auth_http.py:79` and `locations-service/app/auth_http.py:73`.
- **No "ведущий" (GM) role exists.** Roles are admin/moderator/editor/user only. **Question for PM:** should "ведущий" map to moderator, or is a new role needed?
- Frontend admin sections are gated by `module` in `Admin/AdminPage.tsx:17-35`, and `hasModuleAccess` in `utils/permissions.ts`.

### 2.8 Frontend touch points
- Profile tabs: `ProfilePage/ProfileTabs.tsx:7-17` (list) plus the `ProfilePage.tsx:68-95` switch. Add a `reputation` tab ("Репутация") as a new folder `ProfilePage/ReputationTab/` (TS + Tailwind).
- World map region card: `WorldPage/RegionEconomyCard.tsx` (fetch L198 via `api/regionEconomy.ts:118`, a **public** endpoint without character). The "Ваша репутация: X" line needs either a separate per-character fetch or a `character_id` param with a private-access check (see `visibility.require_private_access`). Note the card is rendered only for economy regions (`WorldPage.tsx`), while reputation applies to all regions.
- Merchant modal: `pages/LocationPage/NpcShopModal.tsx` (see 2.5). Its error toasts already exist for 409.
- Admin character page: `Admin/CharactersPage/AdminCharacterDetailPage.tsx:18-25` has `TABS` general/attributes/inventory/skills. Add a "Репутация" tab with numbers and manual edit plus reason.
- Admin editors for gate fields: `AdminNpcsPage/QuestEditor.tsx` (quests), `AdminNpcsPage/AdminNpcsPage.tsx` (NPC form L455), `AdminNpcsPage/TeleportLinksPanel.tsx` (links), `Admin/HousesAdminPage/PlotFormModal.tsx` (plots), `Admin/EconomyPage/EconomyBanks.tsx` / `RegionBankPanel.tsx` (banks). A tier/action-weight settings screen could live in the Economy admin (`Admin/EconomyPage/`, tabs in `EconomyPage.tsx`) or in a new admin section.

### 2.9 Decay background job
- `econ_tick.run_tick` (`character-service/app/econ_tick.py:1302`) runs on 6h slots (`TICK_SECONDS` L133) via the `econ_scheduler` thread, with passes for quota, caravans, regions, guild sweep, mint and banks (L1349-1410). **Caveats:** it is gated by `econ_sim_settings.tick_enabled` (`is_tick_enabled` L322), and manual runs (`trigger='manual'`, slot NULL) add extra steps. A decay pass hooked here would stop when the economy tick is disabled and speed up on manual runs, unless it is keyed on wall-clock time (`last_decay_at`) rather than "per run". There is no other generic scheduler in character-service. Lazy decay on read/write, computed from `updated_at`, is a scheduler-free alternative (current state only; the Architect decides).

### Affected Services
| Service | Type of Changes | Files |
|---|---|---|
| character-service (likely owner) | new tables plus Alembic `038_*`, reputation core module, player/admin/internal API, guild hand-in source, NPC-death source, bank and teleport gates, decay | `models.py`, `schemas.py`, new `reputation*.py`, `economy_guild_crud.py`, `economy_bank_crud.py`, `crud.py` (teleport), `main.py` (npc-status), `econ_tick.py` or own scheduler, `producer.py` |
| locations-service | quest source and gates, shop pricing and refusal, NPC dialogue/shop gate, house gate, quest/plot gate columns (Alembic `054_*`) | `main.py`, `crud.py`, `houses.py`, `models.py`, `schemas.py` |
| battle-service | pass the killer(s) and battle id to NPC death | `app/main.py:2537` |
| user-service | permission migration `0033` plus RBAC test section | `alembic/versions/`, `tests/test_rbac_permissions.py` |
| notification-service | none (existing `progress` category) | — |
| econ_core copies (if price maths goes there) | identical edit in 4 services plus contract cases | `*/app/econ_core.py`, `*/app/tests/econ_contract_cases.py` |
| frontend | ReputationTab, region card line, shop modal reason/markup/refusal, admin character tab, gate fields in 5 editors, settings (tiers/weights) | see 2.8 |

### Existing Patterns
- character-service: sync SQLAlchemy, Pydantic v1, Alembic (`alembic_version_character`, head `037_econ_social_classes`). The economy code style is a pure-maths module (`econ_*.py`) plus a DB module (`economy_*_crud.py`) plus a router (`economy_api.py`), with `EconomyApiError` → HTTPException and the threadpool used for sync work in async routes.
- locations-service: async SQLAlchemy (aiomysql), raw `text()` SQL for foreign tables, Alembic (`alembic_version_locations`, head `053_npc_shop_market`).
- Idempotency: ledger `idempotency_key` / conditional UPDATE (`complete_quest_record`). Internal endpoints use `/…/internal/…` plus `X-Internal-Token` (nginx 403 from outside).
- Private reads use `visibility.require_private_access` (owner or admin/moderator with `characters:read`); public views must not leak private numbers (the FEAT-171 charisma inversion precedent in the `get_npc_shop` docstring).

### Cross-Service Dependencies
- locations-service → character-service: reputation reads (SQL) and writes (internal HTTP or shared SQL) for quest completion, gates and pricing, if character-service owns it.
- battle-service → character-service: `PUT /characters/internal/npc-status/{id}` needs killer info, or a new internal "npc killed" endpoint.
- character-service → locations-service: `check_npc_gate` (already exists); `Regions`/`Locations` read by SQL (already exists).
- character-service → notification-service: RabbitMQ `general_notifications`.
- character-attributes-service: unchanged (charisma source).

### DB Changes (needed, shape for Architect)
- New: per (character_id, region_id) value table (UNIQUE pair; row created on the first change); history/journal table (actor user/system, action code, region, delta, echo flag, result, reason, idempotency key UNIQUE, created_at); settings (range, tier names/thresholds, echo %, decay speed, price modifiers per tier); action-weights table (code → points, including future types `caravan_attack` and `crime`).
- New columns (min tier, nullable = no gate): `quests` (plus an optional weight), NPC (`characters` or a side table), `house_plots`, `econ_banks`, `teleport_links` (or the NPC).
- Migrations in each owning service. MySQL gotchas: FK indexes, revision id ≤ 32 chars (memory `reference_alembic_mysql_gotchas`).

### Risks
- Arbitrage: a reputation discount stacked past 50 % breaks the bid ≤ floor(ask×0.5) and guild-cap invariants. Mitigation: clamp the combined discount at `MAX_CHARISMA_DISCOUNT` and add a contract test that the best combined discount still has ask ≥ every bid and guild price.
- A markup cannot go through `discounted_ask` (it clamps negative values to 0). Mitigation: a separate function, and the frontend must render a markup (it currently shows discounts only).
- econ_core drift: CI fails unless all 4 copies change byte-identically.
- Leaking numbers: owner-visible `character_logs.metadata` and personal shop prices. Mitigation: no numbers in player-facing payloads.
- Double application: NPC death has no idempotency today, and quest/guild need keyed writes. The echo writes several rows per event, so it needs one transaction.
- Decay tied to the econ tick stops when the tick is disabled and over-applies on manual runs.
- Cross-service write latency on hot paths (quest complete, shop). Prefer same-DB reads and keep HTTP off the money transaction (FEAT-181 rule: no transaction across HTTP).
- Open business questions for PM: (1) which NPC roles count as "мирный" (bandit/mercenary?); (2) "ведущий" = moderator, or a new role/permission holder?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Summary of key decisions

| # | Decision | Why |
|---|---|---|
| D1 | **character-service owns all reputation tables** and the single write function `reputation_crud.apply_reputation`. locations-service **reads** tier by raw SQL (established cross-owner read pattern, §2.2) and **writes** only through an internal HTTP endpoint. | character-service already hosts 4 of 5 sources/gates, the scheduler, journal and notifications; locations-service already reads `econ_*` tables by SQL. |
| D2 | **Fixed set of 8 tiers with stable codes** (`outlaw, outcast, watched, wanderer, familiar, trusted, defender, legend`). Admin edits name / lower threshold / price modifier / trade refusal, but cannot add or delete tiers. Gate columns store the tier **code**. | Gates on quests/NPCs/plots/banks/links reference tiers; a deletable tier would orphan them. Renaming stays free (user decision). |
| D3 | Pure maths (tier lookup, lazy decay, clamp, echo, progress) lives in a new **`reputation_core.py`**, byte-identical in character-service (canonical) and locations-service, added to `scripts/check_econ_copies.sh`. Only the price function goes into **`econ_core.py`** (4 copies + contract cases). | One formula for both readers; pricing invariants stay in the module that already guards them. |
| D4 | **Negative decay = lazy + materialised.** Every reader computes the *effective* value from `(value, decay_at, now, decay_per_day)`; a throttled pass in the econ scheduler thread (outside the `tick_enabled` gate, hourly, wall-clock catch-up) materialises it, writes the journal and fires tier-change notifications. | Exact regardless of econ tick on/off, manual runs, or scheduler downtime; no new scheduler. |
| D5 | Idempotency: journal table `reputation_log` with `UNIQUE(event_key, region_id)`. A duplicate `apply_reputation` call is a **silent no-op** (returns `duplicate=True`), never an error. NPC kill additionally uses a conditional `alive→dead` UPDATE. | Retry-safe internal HTTP; echo rows share the event key. |
| D6 | NPC kill: battle-service sends **all character ids of the winning team** + `battle_id`; character-service keeps only real players (`is_npc=0`). **Every player on the winning side** gets the full weight (no split). | Simple, predictable, party members share responsibility. Documented; see Q-list if the user wants a split. |
| D7 | Price: `econ_core.reputation_ask(ask, charisma_pct, reputation_pct)`. Discount tiers add to charisma and the **sum is clamped at 50 %** (existing `discounted_ask`); markup tiers apply on top of the charisma-discounted price (only ever raises the price). Sell bids and guild payouts are **unchanged**. | Keeps `min player price ≥ ceil(ask×0.5) ≥ floor(ask×0.5) ≥ every bid / guild price` (FEAT-183/193/195) by construction. |
| D8 | Gates: one NPC-level field (`characters.reputation_min_tier`) gates **every** NPC interaction (dialogue, shop, quests list/accept, guild, bank, mint, teleport master); object-level fields add narrower gates (quest, house plot, bank loans, teleport link). The region is always the region of the object/NPC. | Matches the user's list without a gate per endpoint per object. |
| D9 | Players never see numbers: player API returns tier code/name, a 0..1 progress fraction within the current tier band, and journal phrases. Numbers only on admin endpoints. Reputation is **private** (owner + staff via `visibility.require_private_access`). | Brief: "ступень и полоска, без чисел"; charisma-inversion precedent (FEAT-171). |

### 3.1 Data model (character-service, Alembic `038_reputation` — revision id ≤ 32 chars)

All tables in `mydatabase`, InnoDB, utf8mb4. No FK to `Regions` (owned by locations-service, same convention as other econ tables that store `region_id`); FK to `characters` with `ON DELETE CASCADE` where noted. Remember the MySQL gotcha: an FK column needs its own index (or be the leftmost column of a composite index).

```sql
CREATE TABLE character_reputation (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  character_id  INT NOT NULL,                 -- FK characters.id ON DELETE CASCADE
  region_id     INT NOT NULL,
  value         INT NOT NULL DEFAULT 0,       -- materialised value, clamped to [min_value, max_value]
  decay_at      DATETIME NULL,                -- anchor from which negative decay accrues; NULL when value >= 0
  updated_at    DATETIME NOT NULL,
  UNIQUE KEY uq_char_rep (character_id, region_id),
  KEY ix_char_rep_decay (decay_at)
);

CREATE TABLE reputation_log (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  character_id    INT NOT NULL,               -- FK characters.id ON DELETE CASCADE
  region_id       INT NOT NULL,
  action          VARCHAR(40) NOT NULL,       -- reputation_actions.code, or 'decay'
  event_key       VARCHAR(191) NOT NULL,      -- idempotency key (shared by origin + echo rows)
  is_echo         TINYINT(1) NOT NULL DEFAULT 0,
  origin_region_id INT NULL,                  -- for echo rows
  requested_delta INT NOT NULL,
  applied_delta   INT NOT NULL,               -- after clamping
  value_after     INT NOT NULL,
  tier_before     VARCHAR(20) NOT NULL,
  tier_after      VARCHAR(20) NOT NULL,
  reason          VARCHAR(500) NULL,          -- staff-visible only
  actor_user_id   INT NULL,                   -- NULL = system
  created_at      DATETIME NOT NULL,
  UNIQUE KEY uq_rep_log_event (event_key, region_id),
  KEY ix_rep_log_char (character_id, created_at),
  KEY ix_rep_log_cap (character_id, region_id, action, created_at)
);

CREATE TABLE reputation_settings (              -- single row id=1
  id              INT PRIMARY KEY,
  min_value       INT NOT NULL DEFAULT -1000,
  max_value       INT NOT NULL DEFAULT 1000,
  echo_pct        DECIMAL(5,2) NOT NULL DEFAULT 20.00,   -- 0..100
  decay_per_day   DECIMAL(8,2) NOT NULL DEFAULT 5.00,    -- points/day toward 0, negatives only; 0 = off
  decay_last_run_at DATETIME NULL,
  updated_at      DATETIME NOT NULL
);

CREATE TABLE reputation_tiers (                 -- exactly 8 rows, codes fixed
  code            VARCHAR(20) PRIMARY KEY,
  sort_order      INT NOT NULL UNIQUE,          -- 1 = lowest
  name            VARCHAR(60) NOT NULL,
  min_value       INT NULL,                     -- lower bound inclusive; NULL only for the lowest tier
  price_pct       DECIMAL(5,2) NOT NULL DEFAULT 0, -- >0 discount, <0 markup (range -100..50)
  trade_refused   TINYINT(1) NOT NULL DEFAULT 0
);

CREATE TABLE reputation_actions (
  code            VARCHAR(40) PRIMARY KEY,
  name            VARCHAR(100) NOT NULL,        -- Russian label, shown to players in the journal
  points          INT NOT NULL DEFAULT 0,
  daily_cap       INT NULL,                     -- max positive points per (character, region, action) per UTC day; NULL = none
  is_builtin      TINYINT(1) NOT NULL DEFAULT 0,-- referenced from code: cannot be deleted / renamed code
  has_source      TINYINT(1) NOT NULL DEFAULT 0,-- informational: an automatic source exists
  sort_order      INT NOT NULL DEFAULT 0
);

CREATE TABLE reputation_npc_role_weights (
  role            VARCHAR(50) PRIMARY KEY,      -- characters.npc_role, '*' = fallback for any other / NULL role
  points          INT NOT NULL
);

ALTER TABLE characters
  ADD COLUMN reputation_min_tier   VARCHAR(20) NULL,   -- NPC gate (players: ignored)
  ADD COLUMN reputation_kill_points INT NULL;          -- per-NPC override of the role weight
ALTER TABLE econ_banks    ADD COLUMN loan_min_reputation_tier VARCHAR(20) NULL;
ALTER TABLE teleport_links ADD COLUMN min_reputation_tier     VARCHAR(20) NULL;
```

**Seeds (in the migration):**
- Settings row: −1000…+1000, echo 20 %, decay 5 points/day (**default to confirm**, see questions).
- Tiers (user decision 2026-11-03) with price defaults:

| code | name | min_value | price_pct | trade_refused |
|---|---|---|---|---|
| outlaw | Вне закона | NULL (≤ −600) | 0 | 1 |
| outcast | Изгой | −599 | −25 (markup) | 0 |
| watched | На заметке | −299 | −10 (markup) | 0 |
| wanderer | Скиталец | −99 | 0 | 0 |
| familiar | Знакомое лицо | 100 | 0 | 0 |
| trusted | Свой человек | 300 | 5 | 0 |
| defender | Заступник | 600 | 10 | 0 |
| legend | Легенда края | 900 | 15 | 0 |

  Tier of value v = the highest-`sort_order` tier whose `min_value ≤ v` (lowest tier when none). Settings validation: thresholds strictly increasing by `sort_order`, all within `[min_value, max_value]`, the `wanderer` band contains 0 (start tier), `price_pct` in −100..50, `trade_refused` allowed on any tier.
- Actions: `quest_complete` «Выполнено задание» +10 (builtin, source); `guild_delivery` «Поставка по заказу гильдии» +2, daily_cap 20 (builtin, source); `npc_kill` «Убийство жителя» 0 (builtin, source — points come from role weights); `region_event_help` «Помощь краю» +5 (builtin, no source); `caravan_attack` «Нападение на караван» −100 (builtin, no source); `crime` «Преступление» −50 (builtin, no source); `admin_manual` «Решение властей» 0 (builtin; delta given explicitly). Admin may add custom actions (non-builtin) for manual use.
- NPC role weights (user decision): bandit +20, mercenary −30, guard −300, ruler −1000, king −1000; merchant, blacksmith, alchemist, bard, sage, priest, healer, hunter, wanderer, auctioneer, banker, minter, guild, teleport_master, hero −150; `*` (any other / NULL role) −150.

**locations-service, Alembic `054_reputation_gates`:**
```sql
ALTER TABLE quests      ADD COLUMN reputation_reward   INT NULL,         -- NULL = action 'quest_complete' points (default +10)
                        ADD COLUMN min_reputation_tier VARCHAR(20) NULL;
ALTER TABLE house_plots ADD COLUMN min_reputation_tier VARCHAR(20) NULL; -- gates purchase AND resale of houses on the plot
```
Rollback: each migration's `downgrade()` drops exactly what it added. No backfill: no row = 0 = Скиталец.

**ORM mirrors:** character-service models for all new tables/columns; locations-service adds the two columns to `Quest` / `HousePlot` models only (reads the character-service tables via `text()` SQL).

### 3.2 `reputation_core.py` (pure, no I/O; canonical in character-service, byte copy in locations-service)

- `Tier` (code, sort_order, name, min_value, price_pct, trade_refused) and `Settings` (min_value, max_value, echo_pct, decay_per_day) value objects.
- `clamp(v, s)`.
- `effective_value(value, decay_at, now, decay_per_day) -> int`: for `value < 0` and `decay_at` set: `min(0, value + floor(decay_per_day × elapsed_seconds / 86400))`; else `value`.
- `materialise_decay(value, decay_at, now, per_day) -> (new_value, new_decay_at, points)`: advances `decay_at` by exactly `points / per_day` days (fractions are not lost on frequent runs); `new_decay_at = None` when the value reaches 0.
- `tier_for(value, tiers)`, `tier_rank(code, tiers)`, `meets(value, min_code, tiers)` (unknown / NULL min code = no gate).
- `progress(value, tier, tiers, s) -> float 0..1` within the tier band (outer tiers use `min_value`/`max_value` of settings as the open bound).
- `echo_delta(delta, echo_pct) -> int` = truncation toward zero of `delta × pct / 100`.
- `tier_price_pct(value, tiers) -> Decimal` (signed) and `trade_refused(value, tiers) -> bool`.
- SQL constants used by both services: `SQL_SELECT_SETTINGS`, `SQL_SELECT_TIERS`, `SQL_SELECT_VALUE` (by character_id + region_id) so locations-service reads identically.

### 3.3 Write path: `reputation_crud.apply_reputation` (character-service, sync, caller's transaction)

```
apply_reputation(db, *, character_id, region_id, action, idem_key,
                 delta=None, reason=None, actor_user_id=None, echo=True, now=None) -> ApplyResult
ApplyResult = {duplicate: bool, skipped: str|None, changes: [RegionChange], tier_changes: [TierChange]}
TierChange  = {character_id, user_id, region_id, region_name, tier_before, tier_after, direction}
```
Steps (no commit inside; the caller commits; notifications only after the caller's commit):
1. Character must exist and be a player (`is_npc = 0`) → else `skipped='npc'` (NPC/mob have no reputation).
2. Action must exist; `delta = delta if delta is not None else action.points`; `delta == 0` → `skipped='zero'`.
3. Duplicate pre-check: `SELECT 1 FROM reputation_log WHERE event_key=:k AND region_id=:origin` → `duplicate=True`, return. (The UNIQUE constraint is the hard guarantee: an `IntegrityError` at flush is translated to `duplicate=True` by the caller wrapper `apply_reputation_tx` for internal endpoints.)
4. Daily cap (only automatic positive deltas, `actor_user_id is None`): `remaining = cap − SUM(applied_delta>0 today, same char/region/action, is_echo=0)`; delta reduced to `remaining`; `≤0` → `skipped='cap'`.
5. Target regions: origin + (if `echo` and `echo_delta != 0`) all other regions with the same `country_id` (`SELECT id, name FROM Regions WHERE country_id = (SELECT country_id FROM Regions WHERE id=:r)`). Unknown region id → 400-type `ReputationError` (caller maps).
6. Ensure rows exist (`INSERT … ON DUPLICATE KEY UPDATE id=id`; SQLite test path: insert-if-missing), then lock all target rows `SELECT … FOR UPDATE` **ordered by region_id** (deadlock-free lock order; use the existing `_for_update(db)` helper style for SQLite).
7. For each row: materialise decay (`reputation_core.materialise_decay`), `old_tier`, `new_value = clamp(value + d)`, set `decay_at` (now if it turned negative from ≥0, None if ≥0, unchanged otherwise), write a `reputation_log` row (`is_echo`, requested/applied delta, `tier_before/after`, reason, actor). Record `TierChange` when the tier code changes.
8. Echo uses the **requested** origin delta (so a capped "Легенда" still echoes), is never echoed again and does not count toward daily caps.

`reputation_notify.publish_tier_changes(changes)` — **sync pika** publisher (character-service already has `pika` in requirements; locations-service `rabbitmq_publisher.py:60` is the reference) to `general_notifications`, category `progress`, best-effort (log and swallow). Messages (Russian, no numbers): up — «Жители края «{region}» теперь считают вас: {tier}», down — «Жители края «{region}» стали относиться к вам хуже: теперь вы — {tier}». Decay up — «Жители края «{region}» понемногу забывают ваши проступки: теперь вы — {tier}». `user_id` from `characters.user_id`.

### 3.4 Sources

| Source | Where | Key | Region | Delta |
|---|---|---|---|---|
| Quest completion | `locations-service/app/main.py` `complete_quest`, **after** the existing commit (FEAT-181: no transaction across HTTP), next to the item grants: `POST /characters/internal/reputation/apply` with 1 retry; failure → `logger.error` (residual risk, key makes a later retry safe). | `quest_reward:cq:{cq_id}` (journal table is separate from the ledger, no clash) | resolve the quest-giver NPC location exactly as the gold does (`get_npc_location` → char location fallback) → `econ_ledger.resolve_location` → `region_id`; no region → skip | `quest.reputation_reward` if not NULL else omitted (action default +10). Value may be 0 / negative. |
| Guild delivery | `character-service/app/economy_guild_crud.py` `hand_in`, new step 10b after XP, same transaction; router `_guild_commit` publishes tier changes after `db.commit()` | `guild:{character_id}:{request_id}` (= ledger key) | `ctx.region_id` | action `guild_delivery` points, daily cap applies |
| NPC kill | battle-service `_finalize_battle` NPC-death loop: body `{status:'dead', battle_id, killer_character_ids:[winning-team character_ids]}`. character-service `update_npc_status`: conditional `UPDATE … SET npc_status='dead' WHERE id=:id AND npc_status='alive'`; only on a real transition and when killers are given → `apply_reputation` per killer with `is_npc=0`, same transaction; tier changes published after commit | `npc_kill:{npc_id}:{battle_id}:{killer_id}` | NPC's `current_location_id` → `econ_ledger.resolve_location` | `npc.reputation_kill_points` ?? role weight ?? `*` weight |
| Manual (staff) | `POST /characters/admin/reputation/characters/{id}/adjust` | `admin:{user_id}:{request_id}` | body | `delta` or `action_code` points; `echo` flag in body (default **false**: staff edits target one region exactly) |
| Decay | scheduler pass, see 3.6 | `decay:{character_id}:{region_id}:{iso decay_at before}` | row | materialised points (`action='decay'`, no echo) |
| Region events / caravan / crime | none in stage 1 — action codes seeded only | — | — | — |

`UpdateNpcStatusRequest` gets two **optional** fields → backwards compatible; `status='alive'` (resurrection by admin) never touches reputation.

### 3.5 API contracts

All character-service routes are under `/characters` (nginx prefix already routed). Pydantic v1. Errors in Russian.

**Player (auth via `get_current_user_via_http` + `visibility.require_private_access`: owner or admin/moderator with `characters:read`; 404 unknown character, 403 stranger):**

- `GET /characters/{character_id}/reputation?region_id=` → 200
  ```json
  {"regions":[{"region_id":3,"region_name":"…","country_id":1,"country_name":"…",
               "tier_code":"trusted","tier_name":"Свой человек","progress":0.42,
               "trade_refused":false}],
   "tiers":[{"code":"outlaw","name":"Вне закона","sort_order":1}, …]}
  ```
  Without `region_id`: rows that exist (visited regions). With `region_id`: exactly one entry, defaulting to Скиталец (`progress` of value 0) when there is no row; 404 for an unknown region. No numeric value anywhere.
- `GET /characters/{character_id}/reputation/history?region_id=&page=1&page_size=20` (page_size ≤ 50) → `{"items":[{"created_at","region_id","region_name","direction":"up|down","action_name","text","tier_after_name","tier_changed":bool}],"total":N}`. `text` is server-built Russian: «Жители края «X» стали относиться к вам лучше/хуже»; staff `reason` and numbers are **not** included.

**Admin (character-service, `require_permission`):**

| Method/path | Permission | Body / response |
|---|---|---|
| `GET /characters/admin/reputation/settings` | `reputation:read` | `{settings:{min_value,max_value,echo_pct,decay_per_day}, tiers:[…all fields]}` |
| `PUT /characters/admin/reputation/settings` | `reputation:settings` | same shape (tiers by code, exactly the 8 codes); validation per 3.1; changing `decay_per_day` first materialises all decaying rows with the old rate (same transaction) |
| `GET /characters/admin/reputation/actions` | `reputation:read` | list |
| `POST /characters/admin/reputation/actions` | `reputation:settings` | `{code:^[a-z][a-z0-9_]{2,39}$, name 1..100, points −1000..1000, daily_cap ≥1|null}` 201 / 409 duplicate code |
| `PUT /characters/admin/reputation/actions/{code}` | `reputation:settings` | `{name, points, daily_cap, sort_order}` |
| `DELETE /characters/admin/reputation/actions/{code}` | `reputation:settings` | 409 for builtin; log rows keep the code string |
| `GET/PUT /characters/admin/reputation/npc-roles` | `reputation:read` / `reputation:settings` | `[{role, points}]`, PUT replaces the full set; `*` must stay |
| `GET /characters/admin/reputation/characters/{id}` | `reputation:read` | `[{region_id, region_name, country_name, value (effective), tier_code, tier_name, updated_at}]` |
| `GET /characters/admin/reputation/characters/{id}/history?region_id&page&page_size` | `reputation:read` | full log rows incl. deltas, reason, actor username |
| `POST /characters/admin/reputation/characters/{id}/adjust` | `reputation:manage` | `{region_id, delta?: int −2000..2000 ≠0, action_code?: str, reason: str 3..500 (trimmed, required), echo: bool=false, request_id: UUID}` — exactly one of `delta` / `action_code`; 400 when target is an NPC; 200 `{changes:[{region_id, value_before, value_after, tier_before, tier_after}], duplicate}` |

NPC admin (`PUT /characters/admin/npcs/{id}`, `NpcUpdate`/read schemas): add `reputation_min_tier: Optional[str]` and `reputation_kill_points: Optional[int]` (−1000..1000); bank admin (`PUT /characters/admin/economy/banks/{region_id}`): `loan_min_reputation_tier`; teleport link admin (`/admin/teleport-links`): `min_reputation_tier`. Every tier field is validated against the 8 codes (or null). locations-service admin: `QuestCreate/QuestUpdate/QuestRead` + `reputation_reward: Optional[int]` (−1000..1000) + `min_reputation_tier`; plot create/update schemas + `min_reputation_tier`. Validation of the code in locations-service: against the `reputation_tiers` codes read by SQL (or the fixed code tuple in `reputation_core`).

**Internal (character-service, `verify_internal_token`, prefix `/characters/internal/` = 403 from outside by nginx):**
- `POST /characters/internal/reputation/apply` `{character_id, region_id, action, idempotency_key ≤191, delta?: int, reason?: str}` → 200 `{applied: bool, duplicate: bool, skipped: str|null}`; 404 unknown region/action. Publishes tier changes after its commit.
- `PUT /characters/internal/npc-status/{id}` — extended as in 3.4.

**Player-visible changes in locations-service:**
- `GET /locations/npcs/{npc_id}/quests…` (available list, `crud.get_available_quests_for_npc`): quests whose tier gate fails stay in the list with `locked_reason: "Нужна репутация: Свой человек"` (new optional field; `null` otherwise). `min_level` behaviour unchanged.
- `accept_quest`: 403 «Нужна репутация: {tier}» for quest gate or NPC gate. Completion is **not** gated (a tier drop mid-quest does not void the work).
- Shop personal view `GET /npcs/{id}/shop?character_id`: each `NpcShopItemRead` gets `price_reasons: [{source:"charisma"|"reputation", percent: float, label: str}]` (percent signed: + discount, − markup; reputation percent is the **applied** share after the 50 % cap; label e.g. «Скидка за репутацию (Заступник)», «Наценка за репутацию (На заметке)», «Скидка за харизму»). `discounted_buy_price` may now be **greater** than `buy_price`. `ShopTransactionResponse` gets the same `price_reasons`; `discount_percent` stays (charisma+reputation net, for backward compatibility).
- `trade_refused` tier (Вне закона): `GET shop?character_id`, `GET sell-offers`, `POST buy`, `POST sell` → **409** «Торговцы этого края отказываются иметь с вами дело (репутация: Вне закона)». Public shop view (no character) unchanged.

### 3.6 Decay scheduler

`reputation_decay.run_pass(session_factory, now)` called from `econ_scheduler.run_scheduled_once` **before** the `is_tick_enabled` check (decay is not economy). Throttle: `reputation_settings.decay_last_run_at` claimed with a conditional UPDATE (`WHERE decay_last_run_at IS NULL OR decay_last_run_at <= now − 3600 s`) so several workers / restarts never double-run; manual econ ticks do **not** call it. Processes rows `WHERE value < 0 AND decay_at IS NOT NULL` in batches of 500, each batch its own transaction, rows locked; materialises via `reputation_core.materialise_decay`; writes a `decay` log row only when points > 0; publishes tier changes after each batch commit. Because readers use `effective_value`, gates/prices are exact even if the scheduler is off (env not set) — the pass only materialises and notifies. Also `apply_reputation` and the decay-rate settings change materialise first.

### 3.7 Gates (read helpers)

- character-service `reputation_crud.require_tier(db, character_id, region_id, min_code)` and `require_npc_tier(db, character_id, npc_id)` → raise `ReputationGateError(403, "Нужна репутация: {tier_name}")`; mapped in routers.
- locations-service `reputation_read.py` (async, raw `text()` using `reputation_core` SQL constants): `get_tier(session, character_id, region_id)`, `require_tier(...)`, `require_npc_tier(session, character_id, npc_id)`; no HTTP.

| Gate | Field | Check point | Region |
|---|---|---|---|
| NPC (all interactions) | `characters.reputation_min_tier` | locations: dialogue open (`main.py:2522`), `_require_npc_gate` (buy/sell), sell-offers, quest list (`locked_reason`) + accept; character-service: guild precheck (`_guild_precheck`), banker actions (deposit/loan/repay — read-only window still viewable but shows the lock), minter POST, teleport (`list_teleport_options_for_npc` marks locked, `execute_teleport` refuses) | NPC's location |
| Quest | `quests.min_reputation_tier` | list (`locked_reason`) + accept | quest-giver NPC location |
| House plot | `house_plots.min_reputation_tier` | `houses.buy_house` and `houses.buy_listed_house` (plot of the house) | `house_plots.region_id` |
| Bank loan | `econ_banks.loan_min_reputation_tier` | `economy_bank_crud.take_loan` next to `loan_cap` | bank region |
| Teleport link | `teleport_links.min_reputation_tier` | `execute_teleport` + options list (locked flag + reason) | source NPC region |

Gate failures are 403 with the Russian message. Staff bypass: **none** (staff play characters like players).

### 3.8 Pricing (econ_core, 4 byte-identical copies)

```
MAX_REPUTATION_MARKUP_PCT = Decimal(100)
def reputation_ask(ask, charisma_pct, reputation_pct) -> int:
    rep = clamp(reputation_pct, -MAX_REPUTATION_MARKUP_PCT, MAX_CHARISMA_DISCOUNT*100)
    if rep >= 0: return discounted_ask(ask, charisma_pct + rep)          # total discount clamped 0..50
    base = discounted_ask(ask, charisma_pct)
    return max(1, ceil(base * (1 + (-rep)/100)))
def reputation_discount_split(charisma_pct, reputation_pct) -> (charisma_applied, reputation_applied)  # for the UI reasons
```
Contract cases (`tests/econ_contract_cases.py`, 4 copies): for a grid of ask × charisma (0..cap) × reputation (−100..+50): `reputation_ask ≥ ceil(ask×0.5)`, `≥ market_bid(…)` for the same ask, `≥ floor(ask×0.5)` (guild cap); markup never lowers the price; rep=0 equals `discounted_ask`. locations-service `get_npc_shop` / `buy_from_npc` call `reputation_ask` with the tier `price_pct` of the merchant's region (`MerchantMarket.region_id`; legacy merchant without region → NPC location → `resolve_location`; no region → 0). Sell side (`sell_to_npc`, `quote_bids`, `get_sell_offers`) and guild prices are untouched except the outlaw refusal.

### 3.9 Frontend

All new/changed components: TypeScript, Tailwind, design system classes, 360 px+ adaptive, no `React.FC`, every API error shown in Russian.
- `api/reputation.ts` — typed client for player + admin endpoints.
- `ProfilePage/ReputationTab/ReputationTab.tsx` (+ `ProfileTabs.tsx`, `ProfilePage.tsx` switch): regions grouped by country, tier name + bar (progress), tier scale legend; journal list below (paged). Tab visible only to the owner/staff (private data).
- `WorldPage/RegionReputationLine.tsx`, rendered in `WorldPage.tsx` next to both `RegionEconomyCard` usages, for **every** region when a character is selected: «Ваша репутация: Свой человек».
- `LocationPage/NpcShopModal.tsx`: render `price_reasons` (discount green, markup red), crossed-out base price for both directions; 409 refusal shown as the modal message. Migrate the touched parts to Tailwind/TS per CLAUDE.md §10.8.
- `LocationPage/NpcQuestsModal.tsx`: locked quests greyed with `locked_reason`, accept button disabled.
- Teleport options UI and banker loan UI: show lock reason (fields already returned).
- Admin: `Admin/ReputationPage/` (new section «Репутация», module `reputation`, `AdminPage.tsx` + route with `ProtectedRoute`): tabs «Ступени и общие» (settings + 8 tiers), «Действия» (weights, caps, custom actions), «Роли NPC». `Admin/CharactersPage/AdminCharacterDetailPage.tsx`: new tab «Репутация» (numbers per region, adjust form with mandatory reason, `request_id` generated per submit, echo checkbox, history table).
- Editors: `QuestEditor.tsx` («Репутация за задание», placeholder «по умолчанию: 10»; «Мин. репутация»), `AdminNpcsPage.tsx` NPC form («Мин. репутация», «Репутация за убийство», placeholder = role weight), `PlotFormModal.tsx`, `EconomyBanks.tsx`/`RegionBankPanel.tsx` («Мин. репутация для займа»), `TeleportLinksPanel.tsx`. A shared `ReputationTierSelect.tsx` (options from settings, empty = «без ограничения»).
- `utils/permissions.ts` / admin menu: module `reputation`.

### 3.10 Security

- Player reads: auth + private-access gate; no numbers; staff reason hidden.
- Internal routes: `X-Internal-Token` + nginx 403 on `/characters/internal/` (existing). No new nginx config.
- Admin: `require_permission` per row of 3.5; manual edit requires a reason; `request_id` makes double-submit idempotent; actor recorded.
- Validation: tier codes against the fixed set, delta bounds, string lengths, settings monotonicity; `event_key` length ≤ 191.
- Rate limiting: existing nginx limits suffice (no new public write endpoint for players).
- SQL: parameterised `text()` only.

### 3.11 RBAC (user-service migration `0033_reputation_permissions`)

Permissions `reputation:read`, `reputation:manage`, `reputation:settings`. Moderator (role_id 3): `read` + `manage` (user decision). `reputation:settings` → admin only (automatic) — **to confirm** (Q3). Editor: none. `test_rbac_permissions.py`: new explicit section seeding the three permissions + moderator grants, asserting admin has all and moderator has exactly read+manage.

### 3.12 Data flow (quest example)

```
Player → POST /locations/quests/{id}/complete (locations)
  └─ tx: complete_quest_record + gold + XP → COMMIT
  └─ HTTP POST /characters/internal/reputation/apply {key quest_reward:cq:N, region, delta?}
        character-service tx: apply_reputation (origin + echo rows, log) → COMMIT
        → pika → general_notifications → notification-service → SSE (only on tier change)
Player opens shop → locations reads reputation_* by SQL → reputation_core.effective_value → tier → econ_core.reputation_ask
```

### 3.13 Rollout & risks

- Migrations auto-run on container start: character-service `038`, locations-service `054`, user-service `0033`. Order-independent (locations reads character tables only at request time; until `038` runs, `reputation_read` must treat a missing table as "no reputation" only if trivially possible — not required, both deploy together).
- No backfill. Deploy note: battle-service and character-service changes are backward compatible in either order (optional fields).
- Residual risks: (1) quest reputation lost if the internal HTTP call fails twice (logged; same class as item grants); (2) `econ_core` copy churn — CI guard catches drift; (3) markup pushes `discounted_buy_price > buy_price`: old frontends would just show no discount.

### 3.14 Business questions — ANSWERED by user 2026-11-03 (these OVERRIDE any conflicting default above)

- **A1:** Ask side as proposed: discounts Свой человек 5 %, Заступник 10 %, Легенда края 15 %; markups На заметке +10 %, Изгой +25 %; Вне закона → refusal. **NEW: low tiers ALSO lower what merchants pay the player (sell bids), mirroring the markup:** На заметке −10 %, Изгой −25 % (Вне закона refuses anyway). High tiers do NOT raise bids (no arbitrage). Store as a separate editable per-tier `sell_pct` (0 / −10 / −25, never > 0). Apply in locations `sell_to_npc`, `quote_bids`, `get_sell_offers` (and any NPC buy-from-player path) via a new econ_core helper `reputation_bid(bid, reputation_sell_pct) -> int` = `floor(bid × (1 + pct/100))`, clamped pct ∈ [−100, 0], result ≥ 0; contract case: never exceeds the original bid. Shown in `price_reasons`. Guild payouts unchanged.
- **A2:** Decay **10 points/day** (−600 → 0 ≈ 60 real days). Only negative decays.
- **A3:** `reputation:settings` (tiers, weights, NPC roles) — **admin only**. Moderators: read + manage (per-character adjust with reason).
- **A4:** Guild delivery +2 per hand-in, cap 20/day/region — OK. **Вне закона also closes the merchant guild** (orders list/accept/hand-in refused, 403 «Нужна репутация: …» style message «Гильдия не работает с теми, кто вне закона»).
- **A5:** Party kill — **full weight to every winner**.
- **A6:** Reputation is **private** (owner + staff only).

### 3.14-old Open business questions (historical)

- Q1: Markup defaults На заметке +10 %, Изгой +25 %; discounts Свой человек 5 %, Заступник 10 %, Легенда 15 %? Should low tiers also **lower what merchants pay** (sell bids)? Default: no.
- Q2: Decay speed default 5 points/day (−600 → 0 in ~120 real days)?
- Q3: Who edits tiers/weights (`reputation:settings`) — admin only, or moderators too?
- Q4: Guild delivery +2 per hand-in with 20/day/region cap — OK? Does «Вне закона» also close the merchant guild (default: only NPC gates; guild is not a "trader" refusal)?
- Q5: Party kill — full weight to every winner (default) or split?
- Q6: Can other players see someone's reputation in their profile? Default: private (owner + staff).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

All developer tasks: no commits, no pushes, no `git add` (user commits once at the end). Backend: `python -m py_compile` on modified files. Frontend: `npx tsc --noEmit` and `npm run build` inside the frontend container.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | Reputation core in character-service: migration `038_reputation` (tables, columns, seeds §3.1), ORM models, `reputation_core.py` (§3.2), `reputation_crud.py` with `apply_reputation`, gates, effective reads (§3.3, 3.7), `reputation_notify.py` (sync pika). Add `reputation_core` group to `scripts/check_econ_copies.sh` (copy goes to locations in task 4). | Backend Developer | DONE | `character-service/app/alembic/versions/038_reputation.py`, `app/models.py`, `app/reputation_core.py`, `app/reputation_crud.py`, `app/reputation_notify.py`, `scripts/check_econ_copies.sh` | — | Migration upgrades/downgrades cleanly on MySQL; seeds match §3.1; apply is idempotent per (event_key, region), clamps, echoes to same-country regions only, detects tier changes, skips NPCs, honours daily caps; lock order by region_id; py_compile passes. |
| 2 | character-service API + sources: player endpoints, admin endpoints, internal `/reputation/apply`, extended `npc-status` (conditional transition + kill reputation), guild hand-in step 10b, gates in guild/bank (incl. loan field)/mint/teleport (incl. link field), NPC/bank/teleport admin schema fields, decay pass in `econ_scheduler` (§3.6). Notifications after commit. | Backend Developer | DONE | `app/main.py`, `app/schemas.py`, new `app/reputation_api.py` (router), `app/economy_api.py`, `app/economy_guild_crud.py`, `app/economy_bank_crud.py`, `app/economy_mint_crud.py`, `app/crud.py` (teleport, NPC admin), `app/reputation_decay.py`, `app/econ_scheduler.py` | 1 | Contracts exactly per §3.5; `UpdateNpcStatusRequest` backward compatible; second death report / second hand-in gives no extra reputation; decay pass runs with tick disabled and is throttled; all gate refusals 403 «Нужна репутация: …»; no numbers in player responses. |
| 3 | econ_core: `reputation_ask`, `reputation_discount_split`, `MAX_REPUTATION_MARKUP_PCT` + contract cases (§3.8); copy byte-identically to inventory, locations, dungeon services. | Backend Developer | DONE | `{character,inventory,locations,dungeon}-service/app/econ_core.py`, `{…}/app/tests/econ_contract_cases.py` | — | `sh scripts/check_econ_copies.sh` passes; contract invariants hold over the grid; existing econ tests in all 4 services stay green. |
| 4 | locations-service: migration `054_reputation_gates`, model columns, `reputation_core.py` copy, async `reputation_read.py`; quest source (internal HTTP after commit, 1 retry); quest list `locked_reason` + accept gate; NPC tier gate in dialogue/`_require_npc_gate`/sell-offers; house buy + resale gates; shop pricing via `reputation_ask` + `price_reasons` + outlaw 409; quest/plot admin schema fields with code validation. | Backend Developer | DONE | `locations-service/app/alembic/versions/054_reputation_gates.py`, `app/models.py`, `app/schemas.py`, `app/main.py`, `app/crud.py`, `app/houses.py`, `app/reputation_core.py`, `app/reputation_read.py` | 1, 3 (contract: 2's internal endpoint) | No HTTP inside money transactions; quest reputation keyed `quest_reward:cq:{id}`; `discounted_buy_price` can exceed `buy_price` with a markup reason; outlaw gets 409 on personal shop/sell-offers/buy/sell; public shop unchanged; py_compile passes. |
| 5 | battle-service: send `battle_id` and `killer_character_ids` (winning team character ids) in the NPC-death call. | Backend Developer | DONE | `battle-service/app/main.py` (NPC-death loop in `_finalize_battle`) | — (contract §3.4) | Payload extended; behaviour otherwise unchanged; py_compile passes. |
| 6 | user-service: migration `0033_reputation_permissions` (read/manage/settings; moderator read+manage), idempotent like `0032`. | Backend Developer | DONE | `user-service/alembic/versions/0033_reputation_permissions.py` | — | Upgrade/downgrade idempotent; admin gets all automatically. |
| 7 | Frontend player side: `api/reputation.ts`, profile «Репутация» tab, `RegionReputationLine` on the world map, `NpcShopModal` price reasons + markup + refusal, `NpcQuestsModal` locked quests, teleport/bank lock reasons. | Frontend Developer | DONE | `src/api/reputation.ts`, `ProfilePage/ReputationTab/*`, `ProfilePage/ProfileTabs.tsx`, `ProfilePage.tsx`, `WorldPage/RegionReputationLine.tsx`, `WorldPage/WorldPage.tsx`, `LocationPage/NpcShopModal.tsx`, `LocationPage/NpcQuestsModal.tsx`, teleport/bank modals | 2, 4 | TS + Tailwind + adaptive 360px; no numbers shown; all errors visible in Russian; tsc + build pass. |
| 8 | Frontend admin: «Репутация» admin section (settings/tiers, actions, NPC roles), admin character «Репутация» tab (numbers, adjust with reason, history), gate/weight fields in QuestEditor, NPC form, PlotFormModal, bank panel, TeleportLinksPanel; shared `ReputationTierSelect`; module `reputation` in permissions/menu. | Frontend Developer | DONE | `Admin/ReputationPage/*`, `Admin/AdminPage.tsx`, router, `Admin/CharactersPage/AdminCharacterDetailPage.tsx` (+ new tab component), `AdminNpcsPage/QuestEditor.tsx`, `AdminNpcsPage/AdminNpcsPage.tsx`, `Admin/HousesAdminPage/PlotFormModal.tsx`, `Admin/EconomyPage/EconomyBanks.tsx`/`RegionBankPanel.tsx`, `AdminNpcsPage/TeleportLinksPanel.tsx`, `utils/permissions.ts` | 2, 4, 6 | Moderator sees section and can adjust but not edit settings (per §3.11); reason required in UI; tsc + build pass. |
| 9 | QA character-service: `reputation_core` unit tests (tiers, decay materialisation without fraction loss, echo truncation, progress); `apply_reputation` (idempotency, clamp, echo same country only, NPC skip, daily cap, tier-change notifications mocked); endpoints (private access 403/404, no numbers in player payload, admin RBAC 403, adjust requires reason, request_id idempotent); npc-status conditional transition + kill weights (role / override / `*` / bandit positive, only `is_npc=0` killers, repeat call no-op); guild hand-in reputation; bank/teleport/mint/guild gates; decay pass with tick disabled + throttle; security cases (SQL injection in codes, oversized reason). | QA Test | DONE | `character-service/app/tests/test_reputation_*.py` | 1, 2 | All new tests pass in container together with the existing suite. |
| 10 | QA locations-service: shop pricing with discount/markup/cap and `price_reasons`, outlaw 409 on all four player trade routes, public shop unchanged; quest list `locked_reason`, accept gate, quest completion calls internal apply with the right key/region/delta (mocked HTTP, retry once, failure does not fail completion); house buy/resale gates; NPC dialogue gate; admin schema validation of tier codes. | QA Test | DONE | `locations-service/app/tests/test_reputation_*.py` | 3, 4 | Tests pass; `check_econ_copies.sh` passes. |
| 11 | QA econ_core contract + battle-service + user-service: contract cases run in all 4 services; battle-service test that NPC-death payload carries `battle_id` and winning-team ids; `test_rbac_permissions.py` explicit reputation section (CLAUDE.md §10.13). | QA Test | DONE | `*/app/tests/econ_contract_cases.py` consumers, `battle-service/app/tests/test_npc_death_reputation.py`, `user-service/tests/test_rbac_permissions.py` | 3, 5, 6 | All pass; RBAC counts updated explicitly. |
| 12 | Docs: `docs/services/character-service.md`, `locations-service.md`, `battle-service.md` (new endpoints/tables/payload), `docs/ARCHITECTURE.md` table list. | Backend Developer | DONE | `docs/…` | 2, 4, 5 | Docs match the implemented contracts. |
| 13 | Final review: code review against §3, cross-service contract check, all tests, `check_econ_copies.sh`, tsc + build; **live verification** on localhost: complete a quest → tier bar and journal move; admin adjust with reason; reputation <−600 → merchant refuses with Russian text; Свой человек → discount reason in shop; gated quest/NPC/house/loan/teleport refuse with «Нужна репутация: …»; NPC kill via «Нападение» lowers reputation once; no numbers in player network responses; zero console errors. | Reviewer | DONE | — | 1–12 | PASS only with automated results + live verification recorded in section 5. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-04
**Result:** PASS

#### Code review (vs §3 / §3.14)
- **Ownership / write path:** single `reputation_crud.apply_reputation`, no commit inside; UNIQUE(event_key, region_id) + pre-check, IntegrityError on the internal/admin routes answered as `duplicate`; rows created then locked `FOR UPDATE` ordered by region_id; echo = trunc(delta×pct) to same-country regions only, never re-echoed; daily cap only for automatic positive deltas; NPC targets skipped. Decay is lazy (`effective_value`) + hourly throttled pass before the `tick_enabled` gate; decay-rate change materialises with the old rate first.
- **Sources:** quest — region read inside the tx, internal HTTP **after** the commit, key `quest_reward:cq:{id}`, 1 retry on network/5xx, never fails completion. Guild — step 10b in the same tx, same key as the ledger posting, tier notifications popped and published after commit. NPC kill — conditional `alive→dead` UPDATE, kill reputation only on a real transition, players only, full weight to every winner (A5); NULL-role fix correct (`or_(IS NULL, != 'mob')`, matches battle-service's own query). No HTTP inside any money transaction.
- **Gates:** NPC gate (dialogue, buy/sell, sell-offers, quest list/accept, guild/bank/mint writes, teleport), quest, house buy + resale, bank loan, teleport link — all 403 «Нужна репутация: X»; outlaw → 409 on personal shop / sell-offers / buy / sell, guild refused (A4). PM's `has_region` fix for regionless quest givers is correct (no region = no gate, consistent with `gate_failure`).
- **Pricing (A1):** `reputation_ask` (discount summed with charisma under the 50 % cap, markup on top), `reputation_bid` (pct ∈ [−100, 0], never above the bid), guild payouts untouched; 4 econ_core copies + contract cases identical.
- **Contracts:** battle → character-service `npc-status` body extended with optional fields (backward compatible); locations → `/characters/internal/reputation/apply` matches `ReputationApplyIn`; TS types match Pydantic schemas (`price_reasons`, `locked_reason`, `reputation_lock`, admin shapes).
- **Security:** player reads behind auth + `require_private_access`; no reputation values in player payloads (tier/progress/phrases only; staff reason hidden); admin routes `require_permission` read/manage/settings; internal route token + nginx `/internal/` block; all SQL parameterised (`_in` builds named placeholders); tier codes validated against the fixed tuple (SQL-injection-like codes → 422); reason 3..500 required; `request_id` UUID idempotent.
- **Migrations:** `038_reputation` (14 chars), `054_reputation_gates`, `0033` — ids ≤ 32; FK columns lead an index; re-runnable upgrade, exact downgrade; RBAC moderator = read+manage, settings admin-only (A3); RBAC test section added explicitly.
- **Frontend:** all new files `.tsx/.ts`, Tailwind + design-system classes, no `React.FC`, no SCSS touched; errors shown in Russian (toasts / inline / refusal panel); admin tabs scroll horizontally at 360 px.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (exit 0)
- [x] `npm run build` (frontend container) — PASS (built in 1m58s)
- [x] `py_compile` — PASS (56 modified/new .py files)
- [x] `pytest` character-service — PASS: 7645 passed, 1 skipped
- [x] `pytest` locations-service (`--asyncio-mode=auto`) — PASS: 2486 passed (former strict-xfails for the NULL-role and regionless-gate bugs now pass as regular tests)
- [x] `pytest` battle-service (`--asyncio-mode=auto`) — PASS: 1710 passed, 10 skipped
- [x] `pytest` user-service — PASS: 771 passed, 5 skipped
- [x] inventory-service econ tests — PASS: 517 passed; dungeon-service `test_econ_contract.py` — PASS (exit 0)
- [x] `sh scripts/check_econ_copies.sh` — PASS (all copies identical, incl. reputation_core)
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome + API on localhost) — PASS

#### Live Verification Results (localhost, admin user, character Ашари #763, merchant Петя #33, region Мэттанхейм #9)
- Quest with `reputation_reward=350` created on Петя, accepted, completed → region 9 Скиталец → **Свой человек**, echo +70 to the 5 other regions of the country; profile tab «Репутация» shows tiers + bars, journal shows «Жители края «Мэттанхейм» стали относиться к вам лучше … теперь вы: Свой человек» and echo phrases. Player responses contain only tier names / progress / phrases — no values.
- Shop as «Свой человек»: chips «Скидка за харизму: −5%», «Скидка за репутацию (Свой человек): −5%», crossed-out base prices; public shop has no `price_reasons`.
- NPC kill via internal `PUT /characters/internal/npc-status/33` with token (`battle_id`, `killer_character_ids=[763,33]`): 1st call `killed:true`, −150 in region 9 (Свой человек → Знакомое лицо), −30 echo ×5, NPC killer ignored; 2nd call `killed:false`, no new rows. (A real «Нападение» on Петя could not finish — pre-existing data/battle bug, see below.)
- Admin card → «Репутация»: per-region numbers, adjust −900 with reason → toast «200 → −700», SSE notification «…стали относиться к вам хуже: теперь вы — Вне закона», journal row with reason/actor. Same `request_id` replayed → `duplicate:true`; blank reason → 422 Russian.
- Вне закона: personal shop / sell-offers / buy → 409 «Торговцы этого края отказываются иметь с вами дело (репутация: Вне закона)»; shop modal shows the refusal panel with «Уйти».
- Gates (temporarily set, then restored): quest `min_reputation_tier=legend` → list shows locked «Нужна репутация: Легенда края» (greyed in NpcQuestsModal), accept 403; NPC gate legend → sell-offers/buy/accept 403; house plot 1 gate → buy 403; bank region 9 loan gate (Петя temporarily banker) → view `loan_refusal` + loan POST 403. Teleport: no teleport links exist locally — covered by `test_reputation_gate_teleport.py`.
- Admin «Репутация» section (3 tabs), world map region 9 «Ваша репутация: Свой человек», 360 px iframe check — rendered; zero console errors; all reputation API calls 200 (except the deliberate 422).
- **Local data restored:** reputation rows/log of #763 deleted (tables were empty before), quests 9114/9115 + character_quest 9313 deleted, `quests_completed` decremented, Петя back to merchant/alive/no gate, bank/plot gates NULL. Battle #324 (accidental attack on Петя) was force-finished via admin endpoint and left as history; a few tier-change notifications remain in user 4's feed.

#### Non-blocking notes
1. Personal `GET /npcs/{id}/shop?character_id` does not apply the NPC tier gate (only the outlaw refusal), so a gated merchant still lists items; buy/sell/sell-offers refuse correctly. Matches §3.7's list, cosmetic.
2. `killer_character_ids` is capped at `max_items=50`; a larger winning team would get 422 and the NPC would not be marked dead (unrealistic today).
3. Player `progress` is a 3-decimal fraction; with known thresholds it approximates the value (~±0.2 pt). Per D9 by design; rounding to 2 decimals would blur it further.

#### Pre-existing issues noted (added to `docs/ISSUES.md`, LOW)
- «Нападение» on an NPC with `current_health = 0` creates a battle that never finalizes (Петя locally: alive, HP 0).
- Direct link `/admin/characters/:id` is blank when the character is not on the first list page.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-03 — PM: фича создана, этапы и решения пользователя зафиксированы; запускаю анализ
[LOG] 2026-11-03 — PM: пользователь утвердил ступени, веса ролей NPC, права (модераторы), поле веса задания; запускаю архитектора
[LOG] 2026-11-03 01:56 — Analyst: анализ завершён — затронуто 5 сервисов (character, locations, battle, user, frontend) + копии econ_core; два вопроса к PM: какие NPC «мирные», кто такой «ведущий» в RBAC
[LOG] 2026-11-03 02:20 — Architect: начал проектирование
[LOG] 2026-11-03 02:55 — Architect: спроектировано 13 задач, ~20 API-контрактов; владелец — character-service, 8 фиксированных ступеней, ленивое забывание + почасовой проход планировщика; 6 бизнес-вопросов к PM (наценки, скорость забывания, права на настройки, гильдия, делёж за убийство, видимость репутации)
[LOG] 2026-11-03 — PM: пользователь ответил на 6 вопросов (§3.14): скупка у низких ступеней −10/−25 %, забывание 10/день, настройки только админ, гильдия закрыта для «Вне закона», полный вес каждому победителю, репутация приватна; запускаю бэкенд
[LOG] 2026-11-03 — Backend Dev: задача 3 готова — в econ_core добавлены reputation_ask, reputation_discount_split, reputation_bid (скупка, A1) и MAX_REPUTATION_MARKUP_PCT; контрактные кейсы + сетки свойств, раннеры в 4 сервисах; копии идентичны (check_econ_copies.sh ок); econ-тесты зелёные: character 6069, inventory 505, locations 515, dungeon — все
[LOG] 2026-11-03 — Backend Dev: задача 5 готова — battle-service шлёт battle_id и killer_character_ids (все персонажи победившей команды) в npc-status; test_npc_death.py зелёный
[LOG] 2026-11-03 — Backend Dev: задача 6 готова — миграция user-service 0033 (reputation:read/manage/settings, модератору read+manage); upgrade → downgrade → upgrade на локальной БД прошли
[LOG] 2026-11-03 — Backend Dev: задача 1 готова — миграция character-service 038_reputation (6 таблиц, 4 колонки, сиды ступеней с sell_pct, действий, весов ролей NPC; upgrade/downgrade/upgrade на MySQL прошли), ORM-модели, reputation_core.py (чистая математика, копия для locations — в задаче 4), reputation_crud.py (apply_reputation с идемпотентностью, отголоском, дневным лимитом, гейтами), reputation_notify.py; группа reputation_core в check_econ_copies.sh (упадёт, пока задача 4 не положит копию в locations)
[LOG] 2026-11-03 — Backend Dev: задача 2 готова — игровые/админские/внутренние эндпоинты репутации (reputation_api.py), npc-status с условным переходом alive→dead и репутацией за убийство, гильдия (+2 за сдачу, «Вне закона» — отказ), гейты в банке (вкл. займ по ступени), монетном дворе, телепорте (вкл. ступень на связи), поля в админке NPC/банка/телепорта, проход забывания в econ_scheduler (до проверки tick_enabled, раз в час); живая проверка внутреннего apply на локалке пройдена
[LOG] 2026-11-03 — Backend Dev: полный набор тестов character-service в контейнере — 7421 passed, 1 skipped; в test_econ_banks_admin_api.py добавлен новый ключ loan_min_reputation_tier в ожидаемый набор полей
[LOG] 2026-11-03 — QA: задача 9 готова — 8 файлов тестов репутации в character-service (ядро и паритет миграции 038 с ORM/сидами, apply_reputation, API игрока/админа/внутренний, убийство NPC, забывание и планировщик, гильдия, банк/монетчик, телепорт), 224 теста (223 passed + 1 xfail); RabbitMQ везде замокан
[LOG] 2026-11-03 — QA: задача 11 (часть battle + user) готова — test_npc_death_reputation.py (5 тестов: battle_id и отсортированные уникальные id победителей), раздел репутации в test_rbac_permissions.py (8 тестов, счётчики обновлены явно); прогоны econ_core-контракта в locations — за задачей 10
[LOG] 2026-11-03 — QA: обнаружен баг, добавлен в ISSUES.md — NPC с пустой ролью не умирает через npc-status (фильтр npc_role != 'mob' отсекает NULL), тест помечен xfail(strict)
[LOG] 2026-11-03 — QA: полные прогоны в контейнерах — character-service 7644 passed, 1 skipped, 1 xfailed; battle-service 1710 passed, 10 skipped; user-service 771 passed, 5 skipped
[LOG] 2026-11-03 — Backend Dev: задача 4 готова (после отключения света продолжена с миграции и копии reputation_core) — миграция 054_reputation_gates (quests.reputation_reward/min_reputation_tier, house_plots.min_reputation_tier; применилась при старте контейнера), копия reputation_core (check_econ_copies.sh ок), reputation_read.py (чтение репутации SQL-ом, без HTTP); цены у торговцев через reputation_ask + price_reasons, скупка у низких ступеней через reputation_bid, «Вне закона» — 409 на личной витрине/скупке/покупке/продаже; гейт NPC в диалоге/торговле/скупке/заданиях; список заданий с locked_reason, принятие — 403; гейт участка на покупку и перекупку дома; репутация за задание — внутренний вызов после коммита с 1 повтором; живая проверка чтений на MySQL пройдена
[LOG] 2026-11-03 — Backend Dev: в conftest.py locations добавлена автофикстура «репутация нейтральна» (как у блокировки активности; маркер real_reputation включает настоящие чтения) и tests/reputation_sqlite.py с SQLite-таблицами для QA (задача 10); в test_xp_books.py у фейкового задания добавлены npc_id/reputation_reward, в test_feat171_shop_gate.py замокан merchant_market (личная витрина теперь читает регион), в test_npc_merchants.py набор полей sell-offers дополнен base_unit_price/price_reasons; полный прогон locations — 2314 passed, check_econ_copies.sh ок
[LOG] 2026-11-03 — Backend Dev: задача 12 готова — документация по коду: character-service.md (раздел «Region reputation»: 6 таблиц и колонки 038, правила, apply_reputation, источники, npc-status с battle_id/killer_character_ids и killed, проход забывания, уведомления, API игрока/админа/internal, гейты), locations-service.md (054, гейты, цены reputation_ask/reputation_bid, price_reasons, 409 «Вне закона», репутация за задание), battle-service.md (тело npc-status), user-service.md (права 0033), ARCHITECTURE.md (таблицы, связи, домен)
[LOG] 2026-11-03 — Frontend Dev: задача 7 готова — api/reputation.ts; вкладка «Репутация» в профиле (регионы по странам, ступень + полоска без чисел, шкала ступеней, журнал с подгрузкой); строка «Ваша репутация: …» на карте мира для каждого региона при выбранном персонаже; у торговца причины цены (скидка зелёным, наценка/урезанная скупка красным с зачёркнутой базой), отказ «Вне закона»/гейт — сообщением на всё окно; заблокированные задания серые с причиной; причины блокировки у телепорта, банкира, монетчика (гильдия — через closed_reason); 403 «Нужна репутация» при открытии диалога показывается; tsc и build в контейнере прошли
[LOG] 2026-11-03 — Frontend Dev: задача 8 готова — раздел админки «Репутация» (модуль reputation, маршрут /admin/reputation под reputation:read; вкладки «Ступени и общие», «Действия», «Роли НПС»; без reputation:settings — только просмотр), вкладка «Репутация» в карточке персонажа (числа по регионам, правка числом или действием с обязательной причиной, request_id на каждую отправку, галочка отголоска, журнал с фильтром по региону; правка видна только с reputation:manage), общий ReputationTierSelect (названия из настроек, без права чтения — стандартные), поля в редакторе заданий, форме НПС (плейсхолдер — вес роли), участке дома, банке (регион и вкладка «Банки»), связях телепорта; клиент api/reputationAdmin.ts
[LOG] 2026-11-03 — Frontend Dev: tsc --noEmit и npm run build в контейнере frontend прошли (вместе с текущими файлами задачи 7)
[LOG] 2026-11-04 — QA: задача 10 готова — test_reputation_trade.py (цены у торговца: скидки/наценки/кап 50 % и price_reasons, публичная витрина без изменений, другой край не влияет, ленивое забывание, правка ступеней из таблицы; покупка; скупка −10/−25 %, урезание до 0 = «не покупает», высокие ступени скупку не поднимают; sell-offers; «Вне закона» — 409 на витрине/скупке/покупке/продаже; гейт NPC в торговле и диалоге; SQL-подобные коды) и test_reputation_gates.py (список заданий с locked_reason, принятие 403, внутренний вызов после коммита с ключом quest_reward:cq:N, регион квестодателя, delta, повтор только на сеть/5xx, сбой не ломает сдачу; гейт участка на покупку и перекупку дома; валидация кодов ступеней 422 вкл. SQL-инъекции; миграция 054) — 172 теста (170 passed + 2 xfail strict)
[LOG] 2026-11-04 — QA: обнаружен баг, добавлен в ISSUES.md — задание с порогом у квестодателя без края заперто навсегда (reputation_read.quest_gates проверяет порог задания при значении 0 вместо «нет края = нет порога»); два теста помечены xfail(strict)
[LOG] 2026-11-04 — QA: правки разработчика в test_xp_books / test_feat171_shop_gate / test_npc_merchants проверены — легитимны (новые поля фейка, мок региона торговца для мок-БД, расширенный набор полей без денег торговца), регрессий не прячут
[LOG] 2026-11-04 — QA: задача 11 закрыта — контрактные прогоны econ_core в locations входят в полный набор; полный прогон locations-service в контейнере — 2484 passed, 2 xfailed; check_econ_copies.sh — все копии идентичны
[LOG] 2026-11-04 01:05 — Reviewer: начал проверку (код, контракты, миграции, безопасность, фронтенд)
[LOG] 2026-11-04 01:20 — Reviewer: тесты в контейнерах зелёные — character 7645, locations 2486, battle 1710, user 771, inventory econ 517, dungeon econ ок; check_econ_copies, tsc, build, compose config — ок
[LOG] 2026-11-04 01:40 — Reviewer: живая проверка на локалке — задание подняло до «Свой человек» с отголоском, скидка за репутацию в лавке, убийство NPC снижает один раз, правка админом с причиной, «Вне закона» — отказ торговца, гейты задания/NPC/дома/займа — «Нужна репутация: …»; консоль без ошибок; тестовые данные возвращены
[LOG] 2026-11-04 01:45 — Reviewer: обнаружены 2 сторонних бага, добавлены в ISSUES.md (бой с NPC без HP не завершается; пустая админ-карточка по прямой ссылке)
[LOG] 2026-11-04 01:45 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

**Статус: DONE (2026-11-04), ревью PASS.**

Сделано — этап 1 репутации регионов:
- Репутация по каждому краю (−1000…+1000), 8 ступеней от «Вне закона» до «Легенды края»; старт — «Скиталец». Отголосок 20 % в края той же страны. Забывается только отрицательная, 10 очков в день.
- Источники: задания (+10 по умолчанию, вес настраивается в задании), сдача заказов гильдии (+2, не больше 20 в день на край), убийство NPC через «Нападение» (вес по роли или свой у NPC, полный каждому победителю, один раз), ручная правка стаффом с причиной.
- Последствия: скидки 5/10/15 % (вместе с харизмой не больше 50 %), наценки +10/+25 % и сниженная скупка −10/−25 %; «Вне закона» — торговцы и гильдия отказывают. Пороги репутации у NPC, заданий, участков домов, займов в банке и телепортов («Нужна репутация: …»).
- Игрок видит вкладку «Репутация» в профиле (ступень, полоска, журнал, без чисел) и строку на карте мира. Админка: раздел «Репутация» (ступени, действия, роли NPC — только админ), вкладка в карточке персонажа (числа, правка с причиной — модераторы тоже), поля порогов и весов в редакторах.
- Попутно исправлено: NPC без роли не умирал после «Нападения»; задание с порогом у квестодателя вне края запиралось навсегда.

Проверено: тесты character 7645, locations 2486, battle 1710, user 771, econ inventory/dungeon; копии econ_core/reputation_core идентичны; tsc + build; живая проверка на локалке по всему чек-листу.

Остатки (не блокируют): личный список товаров не закрыт гейтом NPC (покупка/продажа закрыты); победителей в одном убийстве не больше 50; LOW-баги в ISSUES.md («Нападение» на NPC с 0 HP, прямая ссылка на карточку персонажа в админке, фильтр NPC без роли в списках).
Деплой: миграции применятся сами (character 038, locations 054, user 0033), пересчёт не нужен.
