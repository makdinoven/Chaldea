# FEAT-182: Экономика, этап 2 — живые регионы

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-10-29 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Продолжение FEAT-181 (общая модель экономики — раздел 1 файла `features/FEAT-181-world-economy.md`;
этап 1 «Фундамент» — книга счетов, казны регионов и стран, налог 10 % в страну, валюта-настройка,
админка «Экономика» — выкачен 2026-10-29).

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Мир должен жить сам, без игроков (их мало): у каждого региона есть население, производство и
потребление товаров, запасы и цены, налоги в казну. Раз в 6 реальных часов регион пересчитывается.
Игроки потом (этап 3 — торговцы, этап 5 — заказы/караваны) влияют на эти числа, но не держат их на себе.

### Бизнес-правила
- **Экономическая единица — регион.** Обычно в регионе один крупный город или большая деревня, иногда
  несколько (их население складывается, отдельных рынков внутри региона нет); бывают регионы только из
  мелких деревень — естественные поставщики сырья.
- **Числа региона:** население; достаток 0–100; стабильность 0–100; налоговая ставка; казна региона
  (уже есть с этапа 1); **кошелёк населения** — все деньги жителей одним счётом (новый вид счёта книги).
- **12 групп товаров:** продовольствие, руда и металл, древесина, травы и реагенты, шкуры и ткани,
  магические материалы, оружие, броня и одежда, украшения, зелья, ремесленный инвентарь, быт и мебель.
  Предметы получают группу автоматически по типу/подкатегории, админ правит исключения. Вне рынка
  (фиксированная цена): свитки, рецепты, квестовые предметы, всё легендарное и выше.
- **По каждой группе у региона:** производство в сутки, потребление в сутки (население × норма ×
  поправка на достаток), запас, норма запаса (например недельное потребление), цена (от базовой:
  пусто — до ×3, завал — до ×0,5).
- **Продовольствие особое:** его потребляют все жители; дефицит еды = голод → бьёт по стабильности.
  Дорогие группы (украшения, магия) потребляются по достатку.
- **Цепочки:** готовое производится из сырья (кузницы едят руду: нет руды — оружие дорожает).
- **Пересчёт раз в 6 реальных часов** (числа заданы «в сутки», за шаг применяется четверть):
  1) производство пополняет запасы, кошелёк населения получает за выработку;
  2) жители потребляют — платят из кошелька, тратят запасы;
  3) цены пересчитываются от запасов;
  4) (этап 3: торговцы торгуют с фоновыми горожанами);
  5) казна собирает налог с населения, платит жалованье (обратно в кошелёк населения);
  6) караваны выравнивают цены между регионами — этап 5;
  7) пересчёт стабильности и достатка.
- **Закон сохранения золота из этапа 1 действует:** все потоки симуляции — проводки книги счетов
  (кошелёк населения ↔ казна региона ↔ казна страны). Налог региона в страну — как в этапе 1.
  Золото из ниоткуда не берётся: кошельки населения стартуют с эмиссии, которую делает админ.
- **Шаблоны регионов:** Столица, Портовый, Шахтёрский, Аграрный, Лесной, Магический, Пограничная
  крепость, Сельская округа — готовые профили производства/потребления. Админ выбирает шаблон, задаёт
  население и при желании правит отдельные числа.
- **Карточка региона для игроков:** состояние без сырых цифр казны, «город сыт / голодает»,
  «казна полна / пуста», дефициты и излишки, общий уровень цен.
- Всё настраивается в админке (раздел «Экономика»).

### Решения пользователя (из обсуждения FEAT-181)
- Экономика на регион; тик 6 ч; 12 групп устраивают; влияния игроков на казну пока нет.
- Прод ещё не в альфе — сохранность данных не важна.

### Edge Cases
- Регион без шаблона/населения — не симулируется (или симулируется нулями)?
- Кошелёк населения или казна кончились — что тогда (долг, голод, падение стабильности)?
- Пропущенные тики (сервис лежал) — догонять или нет?
- Удаление региона — счета закрываются как в этапе 1.

### Вопросы к пользователю
- [x] Деньги кончились → голод, падает стабильность, проседает производство; казна региона может уйти в минус (помощь страны). → Ок
- [x] Пропущенные тики → не догоняем, продолжаем с текущего. → Да
- [x] Регион без шаблона → в симуляции не участвует и игрокам ничего не показывает. → Да
- [x] Кнопка «Заполнить регионы по шаблонам» (население, запасы, стартовые деньги жителям эмиссией). → Да
- [x] Карточка региона для игроков → и слова («город сыт», «нехватка руды», «цены высокие»), и стрелки цен по группам. → И то и другое
- [x] Денежные потоки этапа 2 → деньги ходят только налогом (кошелёк населения → казна региона → 10 % в страну) и жалованьем/расходами казны (казна → кошелёк населения); товары двигаются только запасами (производство/потребление); торговля, где встречаются товары и деньги, — этап 3 (торговцы). → Да
- Из анализа: группы предметов в основном назначает админ (автоматика по типу/подкатегории покроет мало) — нужен экран «предмет → группа» с массовым выбором; у каждой группы базовая цена, предмет без своей цены берёт её.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Data measured on the local DB 2026-10-29 (geography matches prod: Мидденгерд / Шинзо / Орос / Юнион-Ист / Обратная
Экзоста; the item catalogue is tiny both locally and in the last prod dump — the user plans a bulk item import).

### 2.1 Affected services

| Service | Type of change | Files |
|---------|----------------|-------|
| character-service | stage-2 tables (region economy, goods groups, templates, tick log), tick runner (if hosted here), admin API, public region-card API, new account kind | `app/econ_core.py` (+ 3 byte-identical copies), `app/econ_ledger.py`, `app/economy_api.py`, `app/economy_crud.py`, `app/schemas.py` (FEAT-181 section at the end), `app/models.py`, `app/main.py` (startup), new Alembic migration `028_*` |
| inventory-service / locations-service / dungeon-service | only if `econ_core.py` changes (new kind / op types): copy byte-identically (CI `econ-contract-copies`, `scripts/check_econ_copies.sh`) | `app/econ_core.py`, `app/tests/econ_contract_cases.py` |
| locations-service | read-only source of `Regions` / `Countries` / `Districts`; region deletion already closes the treasury (`crud.py:4556`, `treasury_closed`) — would also have to close the new population purse; alternative tick host | `app/crud.py:2333` `delete_region`, `:4556` |
| user-service | new RBAC permissions if stage 2 gets its own (e.g. `economy:regions`) | Alembic migration + `test_rbac_permissions.py` explicit seed (CLAUDE.md §10.13) |
| frontend | admin tabs in «Экономика», player region card | `src/components/Admin/EconomyPage/*`, `src/api/economyAdmin.ts`, `src/types/economy.ts`, `src/components/WorldPage/WorldPage.tsx`, `src/components/pages/LocationPage/LocationHeader.tsx` |

### 2.2 Geography model (locations-service, `app/models.py`)

Hierarchy `Areas` (3) → `Countries` (6) → `Regions` (27) → `Districts` (328, self-nested via `parent_district_id`) →
`Locations` (2287, self-nested via `parent_id`; a location belongs to a district **or** directly to a region via
`Locations.region_id`).

- `Regions` (`models.py:51-75`): `id, name, country_id (NOT NULL, FK CASCADE), description (TEXT NOT NULL),
  map_image_url, image_url, entrance_location_id, leader_id, recommended_level_min/max, x, y`. **No type, size,
  population, wealth or any economic field.** Alembic owner: locations-service (async, `alembic_version_locations`).
- `Countries` (`:28-48`): `name, description, leader_id, map/emblem urls, area_id, x, y, is_hidden,
  recommended_level_min/max`. `description` holds joke admin placeholders — never show to players (memory note).
- `Districts` (`:78-112`): `marker_type ENUM('safe','dangerous','dungeon','farm')` — locally 307 safe / 21 dangerous,
  `farm` unused. `Locations.marker_type` — 1649 safe / 570 dangerous / 68 dungeon. Neither is a settlement-size marker.
- **Settlement convention (not a field):** the region's main city is a top-level district whose name is written in
  CAPITALS (ЭЙДОРБУРГ, ДАН-МОРДАН, КРОЙЦБУРГ…) and has its own city map (`Districts.map_image_url`). 23 of 27 regions
  have exactly one such district; 4 have none: «Фронтир» (id 27, empty), «Морские локации» (29, hidden country
  «Другое», 6 districts incl. «Цитадель»), «Каранемор» (32, empty), «Кахрам» (33, villages only). «Розмарра» (31) has a
  capitals district but no city map yet. This matches the brief's «regions of only small villages» case but is not
  machine-readable beyond the naming convention — population/template must be new admin-entered data.
- Per-region size today: 0–19 districts, 0–136 locations (typical 13–15 districts, ~100 locations).
- Region economy is already addressable in the ledger: `econ_accounts` has 27 `region_treasury` + 6 `country_treasury`
  rows (created by `economy_crud.ensure_treasury_accounts`, `economy_crud.py:75`).

Admin UI for regions: `src/components/AdminLocationsPage/AdminLocationsPage.tsx` (tree), form
`AdminLocationsPage/EditForms/EditRegionForm/EditRegionForm.tsx` (389 lines; name, country, entrance location,
leader, description, x/y, image, map — still legacy inline colours `text-[#8ab3d5]`, so adding economy fields here would
trigger the full Tailwind migration of the form, CLAUDE.md §10.8). Map editor `RegionMapEditor/RegionMapEditor.tsx`.
API: `POST /locations/regions/create`, `PUT /locations/regions/{id}/update`, `GET /locations/regions/{id}/details`
(public), `DELETE /locations/regions/{id}/delete` (`locations-service/app/main.py:304-340`), permissions
`locations:create|update|delete`.

### 2.3 Items → 12 goods groups (inventory-service owns `items`, `app/models.py:19-160`)

Fields usable for auto-assignment:

| Field | Values | Notes |
|-------|--------|-------|
| `item_type` ENUM | head, body, cloak, belt, ring, necklace, bracelet, weapon, consumable, resource, scroll, misc, recipe, gem, rune, gathering_tool, furniture | ENUM change on `items` locks the table (memory: alembic gotchas) — a group override column must be VARCHAR or live in a separate table |
| `resource_subcategory` ENUM (only `resource`) | raw: ore, herb, wood, ingredient, trophy; refined: ingot, magic_dust, essence, reagent, material; tools: whetstone, repair_kit; NULL = «Прочее» | labels and refining chains in `inventory-service/app/crud.py:105-123` (`REFINING_RULES`: blacksmith ore→ingot, jeweler ore→magic_dust, alchemist reagent→essence, cook ingredient→reagent, scholar/«Мистик» trophy→material) — a ready-made raw→product chain map |
| `item_rarity` ENUM | common, rare, epic, legendary, mythical, divine, demonic | non-equipment max legendary (`schemas.py:66` `is_rarity_allowed_for_type`); brief: legendary+ off-market |
| `is_food` bool | only allowed on `consumable` (`schemas.py:882-886`), never with `buff_type` | **this is how food differs from potions**: consumable + is_food=1 = food; consumable + is_food=0 (+ optional `buff_type` XP books, `consumable_action` coating/cleanse) = potions |
| `armor_subclass`, `weapon_subclass` | cloth/light/medium/heavy; ~40 weapon kinds | could split «броня и одежда» or refine weapon vs. magic focus |
| `furniture_room_type` | hall/bedroom/storage/workshop | furniture → «быт и мебель» |
| `tool_category` | pickaxe/sickle/axe (gathering_tool) | → «ремесленный инвентарь» together with whetstone/repair_kit |
| `seed_result_item_id` | set on seeds | seeds are `resource` with subcategory NULL |
| `blueprint_recipe_id` / `item_type='recipe'` | recipe link | off-market |
| flags `is_unique`, `is_backpack`, `is_elite_trophy`, `is_home_teleport` | | `is_unique` items are excluded by the dungeon generator already |

**There is no quest-item flag** (grep `quest_item|is_quest` — nothing). `quest_objectives.target_id` (plain int,
`objective_type` VARCHAR) may point to an item, so «quest item» can only be derived from objectives or set as an
admin exception. `misc` type has 0 items.

Local counts (66 items total; last prod dump 2026-09-06 had 39):
- by type: resource 42, furniture 7, scroll 4, consumable 3, weapon 3, body 3, cloak 2, recipe 1, belt 1; ring/necklace/
  bracelet/head/gem/rune/gathering_tool/misc 0.
- resources by subcategory: NULL 33 (essences, crystals, «Трансмутированный ресурс», «Ювелирный лом», herbs, vegetables,
  seeds, honey), repair_kit 4, whetstone 3, trophy 2. **No item uses ore/herb/wood/ingredient/ingot/… yet** — food
  (Морковь, Картофель, Мёд) and herbs (Мята, Шалфей, Кровавый мак) are `resource` with subcategory NULL and
  `is_food=0`; the 3 consumables are potions (is_food=0). So auto-assignment by subcategory classifies almost nothing
  today; the admin-exception path (or a data clean-up of subcategories) carries real weight.
- by rarity: common 40, rare 19, epic 2, legendary 4, mythical 1 (legendary+: 1 weapon, 4 resources).

Base prices:
- `items.price INT NULL` — set on 26/66 items (resource 22: 10–2500, avg 273; scroll 3; consumable 1; cloak 1; belt 1);
  0/NULL on all weapons, armour, furniture. Readers: dungeon generator merchant price (`dungeon-service/app/crud.py:570`,
  `generator.py:678`: `price or MERCHANT_PRICE_PER_LEVEL * level`), admin item form.
- `npc_shop_items` (locations-service, `models.py:461`): `npc_id, item_id, buy_price, sell_price, stock NULL,
  is_active` — locally **1 row** (potion, buy 20 = items.price, sell 10). CRUD `locations-service/app/crud.py:4262-4640`
  (`find_sell_price_for_item` at :4628). Stage 3 will need a base per item when price is NULL — a per-group base price is
  likely needed as fallback.
- Recipes: `recipes` (1 row) + `recipe_ingredients` — could feed «готовое из сырья» chains per item, but data is empty.

### 2.4 Background / periodic jobs

| Pattern | Where | Notes |
|---------|-------|-------|
| asyncio `while True` sweeper started in `@app.on_event("startup")`, kill-switch env, cancel on shutdown | dungeon-service `app/main.py:80-108` (`SWEEP_INTERVAL_SECONDS = 300`, `gameplay.py:104`; every step idempotent + row-locked, «single uvicorn worker» assumed) | closest template for an async tick |
| asyncio never-die loop with interval + kill switch | battle-service `app/main.py:6160-6192` (`_deadline_sweeper_loop`, `BATTLE_TIMEOUT_SWEEPER_ENABLED`) | |
| daemon `threading.Thread` started on startup | inventory-service `main.py:62`, character-attributes-service `main.py:58` (RabbitMQ consumers) | template for a **sync** loop in character-service |
| Celery beat | `celery-beat` container (`docker-compose.yml:142`) runs `tasks:celery_app beat` of battle-service, but **no `beat_schedule` is defined** (`battle-service/app/tasks.py` has only `save_log`) — effectively idle; broker RabbitMQ, battle-service code only |
| lazy catch-up on read | gathering nodes `lazy_restore_depleted_nodes` (`locations-service/app/crud.py:6403`, called at :2504); auction lazy expiry `expire_stale_listings` (`inventory-service/app/crud.py:2697`); house tax periods computed from game time (`locations-service/app/houses.py:2071-2100`, `TAX_PERIOD_DAYS = 49`) | catch-up computed from timestamps, nothing scheduled |

character-service has **no background task today** (only `crud.py:1329` loop is in-request). No repo code uses MySQL
`GET_LOCK` or `SKIP LOCKED`.

Workers: **every service runs one uvicorn process** (Dockerfiles `docker/*/Dockerfile` CMD, `docker-compose.yml`
240-616, `docker-compose.prod.yml` 102-271 — no `--workers`). Dev uses `--reload`: any code edit restarts the process,
so a «sleep 6 h then tick» loop would rarely fire in dev and could be killed mid-tick — the tick must be
wall-clock-scheduled from a persisted «last tick» and safe to abort (per-region transactions). Single-run guarantee
options available with existing tools: a tick table with a UNIQUE tick number (`floor(unix_time / 21600)`) inserted in
its own transaction as the claim; plus `econ_operations.idempotency_key` (UNIQUE, ≤128) per region/step, e.g.
`region_tick:<n>:r:<id>:<step>` — `post_operation` raises `DuplicateOperation` before any balance moves, so postings are
exactly-once even if two runners overlap (deploy restart, a future second worker).

Host candidates (facts for the Architect):
- **character-service** — owns all ledger tables and `economy_crud`, sync executor canonical here, admin API already
  here; would read `Regions`/`Countries` via raw SQL (already done in `economy_crud._treasury_tree`); needs a
  thread-based loop (no async in this service).
- **locations-service** — owns `Regions`, async executor canonical here, NPC shops (stage 3 price consumer) and houses
  live here; has no background loop either.
- New service — rejected in FEAT-181 3.1 (3.8 GB prod VPS, fragile deploy).

### 2.5 Game calendar

Implemented, computed not stored: `locations-service/app/crud.py:3186-3245` (`YEAR_SEGMENTS`: 4 seasons × 39 real days
+ 4 festivals × 10, `DAYS_PER_YEAR = 196`, `DAYS_PER_WEEK = 3`, `compute_game_time`), config singleton
`game_time_config(epoch, offset_days)` (`models.py:423`; local epoch 2026-01-01 20:00, offset 349988 ≈ lore year 1787),
public `GET /locations/game-time`, admin `GET|PUT /locations/game-time/admin` (`main.py:2013-2060`, `gametime:read|write`).
Frontend mirror `src/utils/gameTime.ts` (`DAYS_PER_YEAR` at :31), widget `components/WorldPage/GameTimeWidget.tsx`,
admin `components/Admin/GameTimeAdminPage.tsx`. Houses already reuse it for tax periods. Not in character-service — a
season-dependent production modifier would need the same formula (or the stage-1-style copy) there. Never hardcode the year.

### 2.6 Player-facing region card — candidate places

- **Region page** `/world/region/:regionId` → `components/WorldPage/WorldPage.tsx` (1045 lines, Tailwind). Region view
  renders the title + recommended level above `RegionInteractiveMap` (`WorldPage.tsx:840-862`) or `renderRegionContent()`
  when there is no map; region data from `redux/actions/regionsActions.js` (`fetchRegionDetails` →
  `GET /locations/regions/{id}/details`) into `redux/slices/regionsSlice.js` (still JS). A card fits under the title.
- **Location page** `/location/:locationId` → `components/pages/LocationPage/LocationHeader.tsx` meta row already shows
  «Регион <name>» (`:122-142`, `location.region_name`; `region_id` is used in `LocationTopBar.tsx:46-49` breadcrumbs).
  A compact badge/tooltip («город сыт», price level) can hang there.
- World graph map `components/WorldMapPage/*` (`LocationInspector.tsx`) — secondary option.
- The card should come from a new public endpoint (character-service, e.g. under `/characters/economy/…`, covered by the
  existing nginx `location /characters/`) returning qualitative states only — the region-details endpoint lives in
  another service.

### 2.7 Admin «Экономика» today

Frontend `src/components/Admin/EconomyPage/`: `EconomyPage.tsx` (tabs `summary | journal | actions | settings`,
`EconomyTab` union at :16, labels :18, permission-gated list at :54), `EconomySummary.tsx` (country → region treasury
tree), `EconomyJournal.tsx`, `EconomyActions.tsx` (+ `AccountPicker.tsx`), `EconomySettings.tsx`, `economyLabels.ts`
(Russian op-type labels — new op types need labels here). API `src/api/economyAdmin.ts`, types `src/types/economy.ts`,
route `/admin/economy` (`App.tsx:190`, `economy:read`), tile `Admin/AdminPage.tsx:46`. Stage 2 plugs in as new tabs
(«Регионы», «Товары», «Шаблоны») and a region drill-down from the summary tree.

Backend `character-service/app/economy_api.py` (router `prefix="/characters"`, mounted before the main router; `def`
endpoints; `_run_write` / `_read` helpers :48-75; RBAC via `require_permission`) and `economy_crud.py`. Points that must
learn about a new `population_purse` kind:
- `get_summary` (`economy_crud.py:150`) — `held` already sums every non-source kind, so the invariant stays correct,
  but there is no total for purses; `_system_accounts` (:242) lists every kind except character/region/country — 27
  purse rows would land in «system accounts».
- `SQL_ACCOUNTS_UNION` (:256) and `_account_infos` (:300) resolve names only for region/country treasuries — purse rows
  would show the snapshot `name` or NULL.
- `EMISSION_TARGET_KINDS` (:26) — treasuries only; the brief says purses start from admin emission → must be extended.
- `_region_of` (:399) — only `region_treasury`.

### 2.8 Ledger contract constraints for stage 2

- Kinds, op types and the source-op rule live in `econ_core.py` (`ACCOUNT_KINDS` :39, `REF_KINDS` :45,
  `NEGATIVE_ALLOWED_KINDS` :57, `SOURCE_OP_TYPES` :107, `TAX_SOURCE_KINDS` :65, `OP_TYPES` :97). A new kind / op type is
  a change to **all four byte-identical copies** + contract cases; validation rejects unknown kinds/op types.
- `TAX_SOURCE_KINDS` = character / escrow / storage: a `population_purse → region_treasury` leg would **not** be
  auto-taxed to the country unless the kind is added (or the tick posts the country tax explicitly with
  `apply_tax=False`). Stage 1 forwards tax instantly per inflow (FEAT-181 3.1 #7); the brief keeps «as in stage 1».
- `AccountRef` has constructors only for stage-1 kinds; `allow_negative` comes from `NEGATIVE_ALLOWED_KINDS` (purse
  negative or not is a design choice).
- Lock order (FEAT-181 3.5): business rows → `characters` asc → `econ_accounts` asc. `post_operation` never commits.
- Tests: character-service uses in-memory SQLite (`tests/conftest.py`) with portable copies of
  `Countries/Regions/Districts/Locations` DDL from `tests/econ_contract_cases.py`; any new tick SQL joining `Regions`
  must stay SQLite-compatible or be guarded. CI: 6-minute step timeout per service (`.github/workflows/ci.yml:87`),
  dungeon-service additionally `--timeout=30` per test.

### 2.9 Risks

- **Treasury contention.** Region and country treasury rows are hot (every NPC purchase, teleport, quest reward, house
  tax posts into them). A tick that runs all regions in one transaction would hold 27 region + 6 country rows locked
  for its whole duration and block player payments → run **one transaction per region** (non-money stock/price rows
  first, then one `post_operation` with all legs of that region netted), country rows touched briefly. Volume is small:
  27 regions × 12 groups = 324 stock/price rows and a handful of operations per region per tick (≈ 100–150 operations
  and a few hundred postings per tick, ~600 operations/day) — fine for MySQL, but `econ_operations`/`econ_postings`
  grow ~200 k rows/year; the journal UI filters by op type, so tick ops need their own op types (and maybe a filter
  default that hides them).
- **Gold-flow semantics are underspecified.** «Кошелёк населения получает за выработку» and «жители платят из кошелька»
  must be ledger legs between two existing accounts; if production pay and consumption payment both close on the same
  purse, they net to zero and the only real flows are purse ↔ treasury (tax, wages). Who pays for production (treasury?
  nobody — i.e. non-monetary?) and who receives consumption money must be decided by the Architect/PM, otherwise gold
  conservation breaks or the numbers are cosmetic.
- **Insufficient funds.** Stage 1 lets treasuries go negative; purses — to be decided (brief edge case). A conditional
  debit failing mid-tick raises `InsufficientFunds` and rolls back that region's whole step unless the tick caps
  amounts to the available balance first.
- **Missed ticks / restarts.** Dev `--reload` and prod deploy `down` restart every service; without a persisted tick
  number the tick either never fires or double-fires. Catch-up policy (run missed ticks vs. skip) is an open brief question.
- **Stage-3 coupling.** NPC shop prices (`npc_shop_items.buy_price/sell_price`, locations-service) will read the region
  group price; if the tick lives in character-service, locations-service needs a cross-table SQL read (shared DB,
  like `econ_core` does) or an HTTP call. Item → group mapping must be readable by locations-service too; `items.price`
  is NULL for most items, so a per-group base price fallback is needed.
- **New kind touches 4 services.** Any `econ_core` change ships in four services + CI hash check; a forgotten copy fails CI.
- **Region deletion.** `delete_region` (`locations-service/app/crud.py:2333`, `treasury_closed` at :4556) closes only
  the treasury; a purse and region economy rows (in character-service, no FK across ownership) must be closed/cleaned
  too, or the tick must skip deleted regions.
- **Tests/CI.** A background thread/task started on app startup would run inside pytest `TestClient` — needs a kill
  switch env (as dungeon `DUNGEON_SWEEPER_DISABLED`, battle `BATTLE_TIMEOUT_SWEEPER_ENABLED`) and the tick logic must be
  a callable pure-ish function testable without sleeping (6-min CI step).
- **Data reality.** Only 66 items, almost none with `resource_subcategory`; food/herbs are untagged resources. Auto-
  assignment will put most items into a fallback; admin exceptions UI is essential. Population/templates do not exist
  anywhere — 27 regions need initial admin input (4 regions have no city: «Фронтир», «Морские локации», «Каранемор»,
  «Кахрам» → candidates for «Сельская округа» or «не симулируется»).
- **Frontend rules.** `regionsSlice.js` / `regionsActions.js` are JS; adding logic there forces a TS migration;
  `EditRegionForm.tsx` styling forces a Tailwind migration if touched.

---

## 3. Architecture Decision (filled by Architect — in English)

Scope: **stage 2 «Живые регионы»**. Stage 3 (NPC merchants) is accommodated by the data model and a documented read
contract (3.9), not implemented.

### 3.0 Open questions for the user — answered 2026-10-29: all three as recommended (Q1 yes, Q2 Admin only, Q3 yes)

| # | Question | Recommended answer (used in this design) |
|---|----------|------------------------------------------|
| Q1 | Admin button «Пересчитать сейчас» — does it advance the world by an **extra** step (stocks, prices, taxes move), or only preview? | **Extra real step**, Admin only, logged as a manual run in the journal. Needed to watch/verify the simulation without waiting 6 h; the regular 6 h schedule is not shifted. |
| Q2 | Who assigns item → group: Admin only, or also Editors (who maintain items)? | **Admin only** for now (`economy:settings`, no new permissions, no user-service migration). Can be widened later with a dedicated permission. |
| Q3 | «Город сыт» — regions without a city (Сельская округа, крепость). | The phrase uses a **settlement noun per template** (default: «Город», «Порт», «Край», «Крепость», «Округа») with its grammatical gender: «Город сыт», «Крепость сыта», «Округа голодает». Editable in the template. |

### 3.1 Key decisions

1. **Host: character-service.** It owns the ledger tables, the canonical sync executor, `economy_crud` and the whole
   «Экономика» admin API; the tick is ~90 % ledger + new economy tables, so placing it elsewhere would mean
   cross-service writes into character-service tables or splitting the admin API across services. `Regions`/`Countries`
   are read by raw SQL on the shared DB (already done in `economy_crud._treasury_tree`). The game calendar is **not**
   needed in stage 2 (no seasonal modifiers — deferred, see 3.13). locations-service (async, owns `Regions`) is rejected:
   it would own a scheduler that writes character-service tables. Celery beat is rejected: it runs battle-service code
   only. A new service is rejected (FEAT-181 3.1). Background job = **daemon thread** (character-service is sync).
2. **Money in stage 2 moves only purse ↔ treasury ↔ country** (binding user answer). Production and consumption change
   **stock only**; the population purse is the region's liquidity: if it cannot cover one day of needs, people cannot buy
   → hunger (3.4 step 5). Flows per region per tick, all in **one ledger operation** `region_tick`:
   - `population_purse → region_treasury` — tax (`tax_rate × income`, capped by the purse); the existing tax rule adds
     `region_treasury → country_treasury` 10 % automatically (new kind is added to `TAX_SOURCE_KINDS`);
   - `country_treasury → region_treasury` — **country grant** (recycles the 10 % so purses do not drain into countries);
   - `region_treasury → population_purse` — wages/spending.
3. **Treasury may go negative** (stage-1 payouts already allow it; the tick itself never pushes it below 0 — the wage rule
   releases only the surplus over a reserve target). Country subsidy is the simple proportional grant above (no
   deficit-specific logic). **Purse never goes negative** (`allow_negative = 0`; tax capped by the balance).
4. **Wall-clock tick, single-run guaranteed:** slot = `floor(unix_time / 21600)` (UTC 00/06/12/18). Claim = INSERT into
   `econ_tick_runs` with `UNIQUE(slot)`; each region = one transaction guarded by `econ_regions.last_run_id` (business
   row) + ledger `idempotency_key = region_tick:<run_id>:r:<region_id>`. A crash mid-run is resumed by any process after
   a stale heartbeat (10 min). **Missed slots are never caught up**: only the current slot is ever claimed.
5. **Kill switches:** env `ECON_TICK_ENABLED` (default **off** in code → pytest never starts the thread; set `"1"` in both
   compose files) + DB toggle `econ_sim_settings.tick_enabled` (admin UI, default on). Manual run works regardless of
   both (admin action).
6. **All tunables are data:** groups, chains, templates, per-region parameters and global simulation params
   (`econ_sim_settings.params` JSON validated by a Pydantic schema with defaults — adding a param needs no migration).
7. **Simulation math is a pure module** (`app/econ_sim.py`, no DB), the runner (`app/econ_tick.py`) only loads/stores and
   posts — the math is unit-testable without SQL or sleeping.
8. **Item → group:** pure auto rule `auto_item_group(...)` in `econ_core` (so stage 3 in locations-service gets the same
   answer) + admin overrides in `econ_item_groups`. Unassigned items (auto rule returns nothing, no override) are treated
   as off-market by stage 3 and highlighted in the admin screen.
9. **No quest-item flag is introduced** in `items`: «квестовый» = manual off-market override; the admin screen shows a hint
   badge «в заданиях» for items referenced by `quest_objectives` (`collect`/`deliver`) so the admin can bulk-mark them.
10. **RBAC: no new permissions.** View = `economy:read`; edit templates/groups/items/regions/sim settings and run a manual
    tick = `economy:settings`; «Заполнить по шаблонам» = `economy:settings` **and** `economy:emit` (it emits money).
11. **Region deletion:** locations-service closes the purse into the country treasury (`treasury_closed`) in the
    `delete_region` transaction (it already closes the treasury there). Economy rows (`econ_regions`, `econ_region_goods`,
    history) are owned by character-service and are **lazily purged by the tick** when their `Regions` row is gone
    (no cross-owner DELETE from locations-service; the tick and the card already ignore missing regions).

### 3.2 Ledger contract change (`econ_core.py`, all 4 copies — CI `econ-contract-copies`)

| Constant / function | Change |
|---|---|
| `KIND_POPULATION_PURSE = "population_purse"` | add to `ACCOUNT_KINDS`, `REF_KINDS` (ref = `Regions.id`), `TAX_SOURCE_KINDS`; **not** in `NEGATIVE_ALLOWED_KINDS` |
| `AccountRef.purse(region_id)` | new constructor |
| `SQL_ACCOUNT_NAME[KIND_POPULATION_PURSE]` | `SELECT name FROM Regions WHERE id = :ref_id` (snapshot) |
| `OP_REGION_TICK = "region_tick"` | add to `OP_TYPES`. Not a source op. |
| `GOODS_GROUPS` | ordered tuple of the 12 codes (3.3) |
| `auto_item_group(item_type, resource_subcategory, is_food, item_rarity) -> (group_code \| None, off_market: bool)` | pure rule (3.6) |
| `OFF_MARKET_ITEM_TYPES`, `OFF_MARKET_RARITIES` | `{scroll, recipe}`, `{legendary, mythical, divine, demonic}` |

`econ_ledger.py` (sync and async) needs **no change** (generic over kinds). `tests/econ_contract_cases.py` gets two new
shared scenarios: (a) `purse → region` inflow generates a 10 % tax leg; (b) a purse debit above its balance raises
`InsufficientFunds`; plus pure cases for `auto_item_group`. `scripts/check_econ_copies.sh` stays as is (same file set).

character-service `economy_crud.py` learns the kind: `EMISSION_TARGET_KINDS` += purse; `_region_of` returns `ref_id` for
purses; `SQL_ACCOUNTS_UNION` / `_account_infos` resolve the name from `Regions` for `population_purse` too (frontend
renders «Кошелёк жителей — <регион>» by kind); `_system_accounts` excludes `population_purse`; summary `totals` gains
`population_purses` (held already counts it → invariant unchanged); each region node in the tree gains optional
`purse_account_id`, `purse_balance`. Admin adjust is allowed on purses (not in `ADJUST_FORBIDDEN_KINDS`).

### 3.3 DB Changes — character-service migration `028_econ_living_regions`

All new tables owned by character-service, ORM models in `models.py` (portable types so the SQLite test `create_all`
builds them). No FK to `Regions`/`items` (other owners; same choice as the ledger). FK columns get explicit indexes.
Seeds are inserted by the migration from Python tables (3.5); downgrade drops the tables (no ledger rows touched).

```sql
CREATE TABLE econ_goods_groups (
  code                  VARCHAR(32)   NOT NULL PRIMARY KEY,   -- food, ore_metal, …
  name                  VARCHAR(100)  NOT NULL,               -- «Продовольствие»
  sort_order            SMALLINT      NOT NULL DEFAULT 0,
  is_food               TINYINT(1)    NOT NULL DEFAULT 0,       -- exactly one row = 1 (food)
  base_price            INT           NOT NULL,               -- gold per unit; item fallback price (stage 3)
  norm_per_1000         DECIMAL(10,3) NOT NULL,               -- household consumption, units/day per 1000 inhabitants
  norm_days             DECIMAL(6,2)  NOT NULL,               -- norm stock = N days of consumption
  prosperity_elasticity DECIMAL(5,3)  NOT NULL DEFAULT 0,      -- demand × (1 + e·(prosperity−50)/50)
  price_elasticity      DECIMAL(5,3)  NOT NULL DEFAULT 0,      -- demand × price_mult^(−e)
  updated_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE econ_group_inputs (                              -- production chains: 1 unit of group needs ratio units of input
  group_code  VARCHAR(32)  NOT NULL, input_code VARCHAR(32) NOT NULL, ratio DECIMAL(6,3) NOT NULL,
  PRIMARY KEY (group_code, input_code), KEY ix_econ_group_inputs_input (input_code),
  CONSTRAINT fk_egi_group FOREIGN KEY (group_code) REFERENCES econ_goods_groups(code),
  CONSTRAINT fk_egi_input FOREIGN KEY (input_code) REFERENCES econ_goods_groups(code)
);
CREATE TABLE econ_region_templates (
  code               VARCHAR(32)  NOT NULL PRIMARY KEY,       -- capital, port, mining, agrarian, forest, magic, fortress, rural
  name               VARCHAR(100) NOT NULL, description VARCHAR(500) NULL,
  settlement_noun    VARCHAR(50)  NOT NULL DEFAULT 'Город', noun_gender CHAR(1) NOT NULL DEFAULT 'm',  -- m | f | n
  default_population INT          NOT NULL, tax_rate DECIMAL(5,4) NOT NULL,
  sort_order         SMALLINT     NOT NULL DEFAULT 0,
  updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE econ_template_goods (
  template_code VARCHAR(32) NOT NULL, group_code VARCHAR(32) NOT NULL,
  production_per_1000 DECIMAL(12,3) NOT NULL DEFAULT 0,        -- units/day per 1000 inhabitants at full stability
  consumption_mult    DECIMAL(5,3)  NOT NULL DEFAULT 1,
  PRIMARY KEY (template_code, group_code), KEY ix_etg_group (group_code),
  CONSTRAINT fk_etg_template FOREIGN KEY (template_code) REFERENCES econ_region_templates(code) ON DELETE CASCADE,
  CONSTRAINT fk_etg_group    FOREIGN KEY (group_code)    REFERENCES econ_goods_groups(code)
);
CREATE TABLE econ_regions (                                   -- one row per region that has (or had) economy data
  region_id       BIGINT       NOT NULL PRIMARY KEY,          -- Regions.id (no FK, other owner)
  template_code   VARCHAR(32)  NULL,                          -- NULL = not simulated, invisible to players
  population      INT          NOT NULL DEFAULT 0,            -- 0 = not simulated
  tax_rate        DECIMAL(5,4) NOT NULL DEFAULT 0.1000,
  stability       DECIMAL(5,2) NOT NULL DEFAULT 70,
  prosperity      DECIMAL(5,2) NOT NULL DEFAULT 50,
  hunger          DECIMAL(5,4) NOT NULL DEFAULT 0,             -- last tick, 0..1
  satisfaction    DECIMAL(5,4) NOT NULL DEFAULT 1,             -- last tick, non-food goods 0..1
  treasury_target BIGINT       NOT NULL DEFAULT 0,             -- reserve target used by the wage rule
  last_income BIGINT NOT NULL DEFAULT 0, last_tax BIGINT NOT NULL DEFAULT 0,
  last_wages  BIGINT NOT NULL DEFAULT 0, last_grant BIGINT NOT NULL DEFAULT 0,
  last_run_id     BIGINT       NULL,                          -- per-region idempotency of the non-money part
  last_tick_at    DATETIME     NULL,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY ix_econ_regions_template (template_code),
  CONSTRAINT fk_econ_regions_template FOREIGN KEY (template_code) REFERENCES econ_region_templates(code) ON DELETE SET NULL
);
CREATE TABLE econ_region_goods (
  region_id BIGINT NOT NULL, group_code VARCHAR(32) NOT NULL,
  production_per_1000 DECIMAL(12,3) NOT NULL DEFAULT 0,        -- copied from template, admin-editable
  consumption_mult    DECIMAL(5,3)  NOT NULL DEFAULT 1,
  stock           DECIMAL(16,3) NOT NULL DEFAULT 0,
  norm_stock      DECIMAL(16,3) NOT NULL DEFAULT 0,            -- recomputed each tick
  price_mult      DECIMAL(6,3)  NOT NULL DEFAULT 1,
  prev_price_mult DECIMAL(6,3)  NOT NULL DEFAULT 1,            -- trend arrow
  last_produced DECIMAL(14,3) NOT NULL DEFAULT 0, last_consumed DECIMAL(14,3) NOT NULL DEFAULT 0,
  last_demand   DECIMAL(14,3) NOT NULL DEFAULT 0, last_spoiled  DECIMAL(14,3) NOT NULL DEFAULT 0,
  PRIMARY KEY (region_id, group_code), KEY ix_erg_group (group_code),
  CONSTRAINT fk_erg_region FOREIGN KEY (region_id) REFERENCES econ_regions(region_id) ON DELETE CASCADE,
  CONSTRAINT fk_erg_group  FOREIGN KEY (group_code) REFERENCES econ_goods_groups(code)
);
CREATE TABLE econ_tick_runs (
  id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  slot          BIGINT       NULL,                            -- floor(unix/21600) for auto runs, NULL for manual
  trigger_kind  VARCHAR(10)  NOT NULL,                        -- auto | manual
  actor_user_id INT          NULL,
  status        VARCHAR(10)  NOT NULL,                        -- running | done | partial | failed
  grant_plan    JSON         NULL,                            -- {region_id: grant} fixed at run start (resume-safe)
  regions_total INT NOT NULL DEFAULT 0, regions_done INT NOT NULL DEFAULT 0, regions_failed INT NOT NULL DEFAULT 0,
  error         VARCHAR(500) NULL,
  started_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  heartbeat_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at   DATETIME     NULL,
  UNIQUE KEY uq_econ_tick_runs_slot (slot), KEY ix_econ_tick_runs_started (started_at)
);
CREATE TABLE econ_region_history (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  run_id BIGINT NOT NULL, region_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  population INT NOT NULL, stability DECIMAL(5,2) NOT NULL, prosperity DECIMAL(5,2) NOT NULL, hunger DECIMAL(5,4) NOT NULL,
  purse BIGINT NOT NULL, treasury BIGINT NOT NULL, income BIGINT NOT NULL, tax BIGINT NOT NULL,
  wages BIGINT NOT NULL, grant_amount BIGINT NOT NULL,
  goods JSON NOT NULL,                                        -- {code: {"stock": x, "price_mult": y, "produced": p, "consumed": c}}
  KEY ix_erh_run (run_id), KEY ix_erh_region_created (region_id, created_at),
  CONSTRAINT fk_erh_run FOREIGN KEY (run_id) REFERENCES econ_tick_runs(id) ON DELETE CASCADE
);
CREATE TABLE econ_item_groups (                               -- admin overrides only; absent row = auto rule
  item_id    BIGINT      NOT NULL PRIMARY KEY,                -- items.id (no FK, inventory-service owns items)
  group_code VARCHAR(32) NULL,                                -- NULL = use auto group
  off_market TINYINT(1)  NULL,                                -- NULL = auto (scroll/recipe/legendary+), 1/0 = forced
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  updated_by_user_id INT NULL,
  KEY ix_eig_group (group_code),
  CONSTRAINT fk_eig_group FOREIGN KEY (group_code) REFERENCES econ_goods_groups(code)
);
CREATE TABLE econ_sim_settings (
  id TINYINT NOT NULL PRIMARY KEY,                            -- always 1
  tick_enabled TINYINT(1) NOT NULL DEFAULT 1,
  params JSON NOT NULL,                                       -- 3.4 defaults; validated by schemas.EconSimParams
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  updated_by_user_id INT NULL
);
```
The migration does **not** create `econ_regions` rows: every region starts outside the simulation (template NULL).
`group_code` values are validated against `econ_core.GOODS_GROUPS` in schemas; groups and templates are a fixed set (edit
only, no create/delete endpoints).

### 3.4 Simulation model (`app/econ_sim.py`, pure; `dt = 0.25` day)

Global params (`econ_sim_settings.params`, defaults; all admin-editable with bounds):

| param | default | meaning |
|---|---|---|
| `price_min` / `price_max` | 0.5 / 3.0 | price multiplier clamp |
| `price_exponent` | 0.631 (= ln2/ln3) | `price_mult = clamp(r^(−k))`, r = stock / norm_stock → r=1 ×1, r=3 ×0.5, r≈0.18 ×3 |
| `stock_cap_mult` | 3.0 | stock above `3 × norm` is lost («излишек вывезен/испорчен», `last_spoiled`) |
| `prod_price_elasticity` | 0.15 | production × clamp(1 + 0.15·(price_mult − 1), 0.85, 1.30) |
| `full_stability` | 60 | production × (0.5 + 0.5·min(1, stability/60)) |
| `hunger_prod_penalty` | 0.5 | production × (1 − 0.5·hunger_prev) |
| `afford_days` | 1.0 | affordability a = clamp(purse / (needs_cost_per_day × afford_days), 0, 1) |
| `treasury_reserve_days` | 7 | treasury_target = 7 days of gross tax (last tick tax × 4 × 7) |
| `treasury_release_ticks` | 8 | wages release `(treasury − target)/8` per tick |
| `country_grant_share` | 0.25 | each tick a country gives 25 % of its positive balance to its simulated regions, ∝ population |
| `purse_start_days` | 7 | «Заполнить»: purse topped up to 7 days of needs at base prices |
| `stab_base`, `stab_hunger_w`, `stab_goods_w`, `stab_free_tax`, `stab_tax_w`, `stab_debt_penalty` | 85, 100, 15, 0.12, 200, 10 | stability target (below) |
| `stab_rate_up` / `stab_rate_down` | 0.08 / 0.25 | share of the gap closed per tick |
| `prosp_rate` | 0.05 | prosperity: share of the gap closed per tick |
| `history_retention_days` | 60 | older `econ_region_history` rows purged by the run |

Per region per tick (inputs: region row, 12 goods rows, groups, chains, purse/treasury balances, grant; output: new rows,
`income`, `tax`, `wages`, phrases data). `pop_k = population / 1000`.

1. **Multipliers:** `M = (0.5 + 0.5·min(1, stability/full_stability)) × (1 − hunger_prod_penalty·hunger_prev)`;
   per group `E_g = clamp(1 + prod_price_elasticity·(price_mult_g − 1), 0.85, 1.30)`.
2. **Raw production** (groups without inputs: food, ore_metal, wood, herbs, hides_textiles, magic):
   `produced = production_per_1000 · pop_k · M · E_g · dt`; `stock += produced`.
3. **Processed production** in fixed order weapons → armor → jewelry → potions → tools → household:
   `potential` as in 2; `limit = min(stock_input / ratio)` over inputs; `produced = min(potential, limit)`; inputs
   deducted, `stock += produced` («нет руды — оружие дорожает»).
4. **Demand:** `demand_g = norm_per_1000 · consumption_mult · pop_k · (1 + prosperity_elasticity·(prosperity − 50)/50)
   · price_mult^(−price_elasticity) · dt` (prosperity factor floored at 0.1).
5. **Affordability & consumption:** `needs_cost_day = Σ demand_g/dt · base_price · price_mult`;
   `a = clamp(purse / (needs_cost_day · afford_days), 0, 1)`; `consumed_g = min(stock_g, demand_g · a)`; stock −= consumed.
   `hunger = clamp(1 − consumed_food / (norm_food · consumption_mult_food · pop_k · dt), 0, 1)` (pure need, so expensive
   food or an empty purse both show up as hunger). `satisfaction = Σ_{non-food} consumed·base_price / Σ demand·base_price`.
6. **Norm & cap:** `norm_stock_g = norm_days · (household demand/day at prosperity 50, price ×1 + Σ processed
   production_per_1000·pop_k·ratio for groups using g as input)`; stock above `stock_cap_mult · norm` → `spoiled`.
7. **Prices:** `price_mult = clamp(max(stock/norm, 0.01)^(−price_exponent), price_min, price_max)` (norm 0 → 1.0);
   `prev_price_mult` keeps the old value.
8. **Money (integers, floor):** `income = Σ produced_g · base_price_g · price_mult_g` (new prices);
   `tax = min(purse, floor(income · tax_rate))`; `net_tax = tax − floor(tax · country_tax_rate)`;
   `treasury_target = tax · 4 · treasury_reserve_days`;
   `wages = max(0, net_tax + grant + floor((treasury_before − treasury_target) / treasury_release_ticks))`.
   This rule never drives the treasury negative from a non-negative start and pulls it back toward the target when
   stage-1 payouts made it negative (wages shrink → purse drains via tax → hunger/stability fall — the user's rule).
9. **Stability:** `target = clamp(stab_base − stab_hunger_w·hunger − stab_goods_w·(1 − satisfaction)
   − stab_tax_w·max(0, tax_rate − stab_free_tax) − (stab_debt_penalty if treasury < 0), 0, 100)`;
   moves by `stab_rate_up` (if target > current) or `stab_rate_down` of the gap.
10. **Prosperity:** `liq = min(1, purse_after / (needs_cost_day · purse_start_days))`;
    `target = clamp(100·(0.45·satisfaction + 0.25·liq + 0.15·stability/100) − 60·hunger, 0, 100)`; moves `prosp_rate` of the gap.
    (Negative feedback: richer → more luxury demand → lower satisfaction → lower prosperity.)

    **Changed by B4:** with the weights above (and `liq` over 7 days) a balanced region settled at prosperity ≈ 80, so
    every region read as «богатый» and luxury demand (×(1+e·0.6)) ran ~1.3–1.5× the template norm, eating the specialty
    surplus of e.g. the capital (jewelry/household stayed at ×1.0). The weights became params with new defaults:
    `target = clamp(100·(prosp_w_sat·satisfaction + prosp_w_liq·liq + prosp_w_stab·stability/100) − prosp_hunger_w·hunger)`,
    `liq = min(1, purse_after / (needs_cost_day · prosp_liq_days))`; defaults `prosp_w_sat 0.30`, `prosp_w_liq 0.40`,
    `prosp_w_stab 0.15`, `prosp_hunger_w 60`, `prosp_liq_days 14` → balanced region ≈ 55–60 («зажиточный»), «богатый»
    (≥ 75) needs a purse well above the starting 7 days. Max target stays 85. `EconSimParams` (B6) must include them.
    Also exposed as params (same values as the formulas above): `dt 0.25`, `prod_price_min 0.85`, `prod_price_max 1.30`.

Group defaults (seeded):

| code | name | base price | norm /1000/day | norm days | prosp. el. | price el. | inputs per unit |
|---|---|---|---|---|---|---|---|
| food | Продовольствие | 2 | 300 | 7 | 0 | 0.1 | — |
| ore_metal | Руда и металл | 10 | 4 | 14 | 0.2 | 0.3 | — |
| wood | Древесина | 5 | 15 | 14 | 0.2 | 0.3 | — |
| herbs | Травы и реагенты | 8 | 4 | 14 | 0.3 | 0.3 | — |
| hides_textiles | Шкуры и ткани | 10 | 5 | 14 | 0.3 | 0.3 | — |
| magic | Магические материалы | 40 | 0.5 | 21 | 0.8 | 0.5 | — |
| weapons | Оружие | 120 | 0.2 | 21 | 0.5 | 0.5 | ore_metal 3 |
| armor | Броня и одежда | 100 | 0.4 | 21 | 0.5 | 0.5 | hides_textiles 2, ore_metal 1 |
| jewelry | Украшения | 200 | 0.1 | 28 | 1.0 | 0.6 | ore_metal 1, magic 0.5 |
| potions | Зелья | 30 | 1.0 | 14 | 0.6 | 0.4 | herbs 2 |
| tools | Ремесленный инвентарь | 40 | 0.5 | 21 | 0.3 | 0.4 | ore_metal 1, wood 1 |
| household | Быт и мебель | 80 | 0.4 | 28 | 0.6 | 0.5 | wood 3, hides_textiles 0.5 |

Needs ≈ 1 gold per inhabitant per day (food 60 %). A 25 000 capital: income ≈ 25 000/day, tax 12 % ≈ 3 000/day
into the treasury, purse start ≈ 175 000 — big enough to be stable, small next to nothing players see.

Templates — the seed stores `production_per_1000 = ratio × need_per_1000`, where for finished groups
`need = norm · cmult` and for raw groups `need = norm · cmult + Σ(finished production · input ratio)` (computed in the
migration from the two tables below, rounded to 3 decimals). Ratio > 1 = specialty (surplus, cheap), < 1 = chronic
shortage settling at a higher price via production elasticity (e.g. food 0.85 → ≈ ×1.75 price, ≈ 5 % undernourishment).

| template (code) | noun | pop | tax | food | ore | wood | herbs | hides | magic | weap | armor | jewel | potion | tools | house |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Столица (capital) | Город m | 25000 | 0.12 | 0.95 | 0.8 | 0.8 | 0.8 | 0.9 | 1.0 | 1.2 | 1.2 | 1.4 | 1.2 | 1.2 | 1.3 |
| Портовый (port) | Порт m | 12000 | 0.10 | 1.1 | 0.7 | 0.9 | 1.0 | 1.3 | 0.8 | 0.9 | 1.0 | 1.1 | 1.0 | 1.1 | 1.1 |
| Шахтёрский (mining) | Город m | 6000 | 0.10 | 0.9 | 2.0 | 1.0 | 0.6 | 0.8 | 1.2 | 1.3 | 1.1 | 1.2 | 0.7 | 1.4 | 0.8 |
| Аграрный (agrarian) | Край m | 8000 | 0.08 | 1.5 | 0.5 | 1.0 | 1.3 | 1.3 | 0.5 | 0.6 | 0.8 | 0.5 | 1.0 | 0.9 | 0.9 |
| Лесной (forest) | Край m | 4000 | 0.08 | 1.05 | 0.5 | 2.2 | 1.6 | 1.5 | 1.0 | 0.7 | 0.9 | 0.6 | 1.2 | 1.0 | 1.6 |
| Магический (magic) | Город m | 7000 | 0.12 | 0.95 | 0.7 | 0.8 | 1.4 | 0.7 | 2.2 | 0.7 | 0.7 | 1.4 | 1.8 | 0.9 | 1.0 |
| Пограничная крепость (fortress) | Крепость f | 3000 | 0.06 | 0.85 | 1.1 | 1.1 | 0.8 | 1.0 | 0.6 | 1.6 | 1.6 | 0.3 | 1.0 | 1.0 | 0.5 |
| Сельская округа (rural) | Округа f | 2500 | 0.06 | 1.3 | 0.6 | 1.3 | 1.3 | 1.2 | 0.4 | 0.4 | 0.6 | 0.3 | 0.8 | 0.8 | 0.8 |

Consumption multipliers (`cmult`, default 1.0): capital — magic, jewelry, potions, household 1.3; port — jewelry 1.1;
mining — food 1.1, tools 1.5; agrarian — jewelry 0.6, magic 0.6; magic — magic 2.0, potions 1.5; fortress — weapons 3.0,
armor 3.0, potions 2.0, jewelry 0.3, household 0.5; rural — jewelry 0.4, magic 0.4, weapons 0.5, household 0.7.

Starting state on «apply template»/«fill»: stability 70, prosperity 50, hunger 0, stock = norm_stock (r = 1, all prices
×1), purse topped up to `purse_start_days × needs_cost_day(base prices)`.

### 3.5 Tick runner and scheduler (`app/econ_tick.py`, `app/econ_scheduler.py`)

```
run_tick(session_factory, *, trigger, actor_user_id=None, now=None) -> RunSummary
  claim:  auto   → INSERT econ_tick_runs(slot=floor(now/21600), 'auto', 'running') ; IntegrityError → return None
                   (or, if the slot row is 'running' with heartbeat older than 10 min: UPDATE … SET heartbeat_at=now
                    WHERE id=:id AND heartbeat_at < :stale — rowcount 1 → resume, else return None)
          manual → refuse (RunInProgress → 409) if any run is 'running' with a fresh heartbeat; INSERT (slot NULL, 'manual')
          grant_plan computed once (country positive balance × share, split ∝ population of its simulated regions),
          stored in the run row; commit.
  purge:  DELETE econ_regions (+ goods by cascade / explicit delete on SQLite) whose region_id is not in Regions.
  for region_id in simulated regions (template_code NOT NULL AND population > 0 AND region exists), ascending:
      txn: SELECT econ_regions … FOR UPDATE (skip if last_run_id = run.id) → goods rows FOR UPDATE
           → read purse/treasury balances → econ_sim.simulate_region(...) → UPDATE region + goods rows
           → post_operation(op_type='region_tick', legs=[purse→region tax, country→region grant, region→purse wages],
                            region_id, source_service='character-service', idempotency_key=f'region_tick:{run.id}:r:{region_id}',
                            metadata={'run_id', 'tax', 'grant', 'wages', 'income', 'hunger'})
           → INSERT econ_region_history → COMMIT
      on any exception: rollback, regions_failed += 1, log (region id + error class), continue
      heartbeat: UPDATE run SET heartbeat_at, regions_done, regions_failed (own short txn)
  finish: status = done | partial (some failed) | failed (all failed); purge history older than retention; keep last 500 runs.
```
- Lock order per region: `econ_regions` → `econ_region_goods` → (helper) `econ_accounts` ascending — no `characters`.
  The region treasury / country rows are held only from `post_operation` to commit (milliseconds).
- `DuplicateOperation` inside a region txn = already posted by an overlapping runner → rollback that region, count as done.
- `InsufficientFunds` on the purse (race with an admin adjust) → rollback the region, counted failed, retried next tick.
- SQLite: no `FOR UPDATE` (use `econ_core.supports_for_update`), purge with explicit goods delete.
- **Scheduler:** `start_scheduler()` called from `@app.on_event("startup")` only when `ECON_TICK_ENABLED in ("1","true")`;
  module-level guard so one thread per process; daemon thread; first check after 30 s, then every
  `ECON_TICK_POLL_SECONDS` (default 60); each iteration reads `econ_sim_settings.tick_enabled`, calls
  `run_tick(trigger='auto')`; never dies (catch-all + log). With `--reload` the old process (and its thread) dies, the
  new one finds the claimed slot → no duplicate; a run killed mid-way is resumed after 10 min by the stale-heartbeat rule.
- On deploy, if the current slot has not run yet, it runs on startup (continue from now); earlier slots are skipped.

### 3.6 Item → group

`auto_item_group` (econ_core, pure): off-market if `item_type ∈ {scroll, recipe}` or `item_rarity ∈ {legendary, mythical,
divine, demonic}` (group still returned if derivable). Groups: `consumable` → `food` if `is_food` else `potions`;
`resource` by subcategory: `ore, ingot` → ore_metal; `wood` → wood; `herb, reagent` → herbs; `ingredient` → food;
`trophy` → hides_textiles; `magic_dust, essence, material` → magic; `whetstone, repair_kit` → tools; NULL → `food` if
`is_food` else **none**; `weapon` → weapons; `head, body, cloak, belt` → armor; `ring, necklace, bracelet, gem` → jewelry;
`rune` → magic; `gathering_tool` → tools; `furniture` → household; `misc` → none.
Effective = override row (`group_code`/`off_market` when not NULL) else auto. **Item market price (stage 3 contract):**
`item_base = items.price if > 0 else group.base_price`; off-market or no group → `item_base` (fixed);
otherwise `item_base × price_mult(region, group)` when the region is simulated, else `item_base`.

### 3.7 API Contracts (character-service, `economy_api.py` router, covered by nginx `location /characters/` — no nginx change)

All amounts JSON integers, decimals JSON numbers; Russian errors; `def` endpoints via `_run_write`/`_read`.

**Public**
- `GET /characters/economy/regions/{region_id}/card` → `200` always (unknown or not simulated →
  `{"region_id": 9, "participating": false}`):
```json
{ "region_id": 9, "participating": true, "updated_at": "2026-10-29T12:00:05",
  "food":       { "state": "fed",    "label": "Город сыт" },          // fed | tight | hunger: hunger <0.03 | <0.15 | ≥0.15
  "treasury":   { "state": "full",   "label": "Казна полна" },        // full ≥1×target | ok ≥0.4 | low ≥0 | debt <0  (target 0 → ok)
  "stability":  { "state": "calm",   "label": "Спокойно" },           // calm ≥70 | uneasy ≥45 | unrest ≥25 | riot
  "prosperity": { "state": "wealthy","label": "Зажиточный край" },     // rich ≥75 | wealthy ≥50 | modest ≥25 | poor
  "price_level":{ "state": "high",   "label": "Цены высокие" },       // demand-value-weighted mean mult: low <0.85 | normal <1.2 | high <1.8 | very_high
  "shortages": ["Руда и металл"], "surpluses": ["Древесина"],        // price_mult ≥1.6 / ≤0.7
  "phrases": ["Город сыт", "Нехватка: руда и металл", "Цены высокие"],
  "groups": [ { "code": "food", "name": "Продовольствие", "level": "normal", "trend": "up" } ] }
                // level: very_low ≤0.6 | low ≤0.85 | normal | high ≥1.2 | very_high ≥1.8 ; trend vs prev_price_mult (±3 %): up | down | flat
```
  Food labels use the template noun and gender: m «сыт / недоедает / голодает», f «сыта / недоедает / голодает».
  No balances, no raw stock/price numbers. No auth (non-sensitive, cheap, existing nginx rate limit).

**Admin (`economy:read` for GET, `economy:settings` for writes unless stated)**

| Method & path | Body / query | Response |
|---|---|---|
| `GET /characters/admin/economy/regions` | — | `{ items: [ { region_id, name, country_id, country_name, template_code, template_name, population, tax_rate, stability, prosperity, hunger, satisfaction, purse, treasury, treasury_target, last_income, last_tax, last_wages, last_grant, last_tick_at, simulated } ] }` — every `Regions` row (LEFT JOIN `econ_regions`) |
| `GET /characters/admin/economy/regions/{id}` | — | region item + `goods: [ { group_code, name, production_per_1000, consumption_mult, stock, norm_stock, price_mult, prev_price_mult, last_produced, last_consumed, last_demand, last_spoiled } ]` (404 unknown region) |
| `PUT /characters/admin/economy/regions/{id}` | `{ template_code: str\|null, population: 0..10_000_000, tax_rate: 0..0.5, stability?: 0..100, prosperity?: 0..100, goods?: [ { group_code, production_per_1000: 0..100000, consumption_mult: 0..10, stock?: ≥0 } ] }` | detail. Creating the row from a template copies template goods; changing template does **not** silently overwrite goods (use apply-template) |
| `POST /characters/admin/economy/regions/{id}/apply-template` | `{ reset_stocks: bool = true }` | detail; copies template goods/tax, keeps population; stocks → norm if `reset_stocks` |
| `POST /characters/admin/economy/regions/fill` — **`economy:settings` + `economy:emit`** | `{ region_ids?: [int] (default: all with a template), population_from_template: bool = false (only rows with population 0), reset_stocks: true, fund_purses: true, comment: 3..500 }` | `{ regions: n, operation_id \| null, emitted: int }` — applies template goods, stocks = norm, then **one** `admin_emission` operation with one `emission → population_purse` leg per region, amount = `max(0, target − current purse)` (re-click does not inflate). Regions without template → 400 if listed explicitly |
| `GET /characters/admin/economy/regions/{id}/history` | `limit=1..200 (40)` | `{ items: [history rows, newest first] }` |
| `GET /characters/admin/economy/goods-groups` / `PUT …/goods-groups/{code}` | `{ name 1..100, base_price 1..1_000_000, norm_per_1000 0..100000, norm_days 0.5..365, prosperity_elasticity 0..3, price_elasticity 0..3, inputs: [ { input_code, ratio 0.001..100 } ] }` (no self/cycles; raw groups may get inputs) | group(s) |
| `GET /characters/admin/economy/templates` / `PUT …/templates/{code}` | `{ name, description?, settlement_noun 1..50, noun_gender m\|f\|n, default_population, tax_rate, goods: [ { group_code, production_per_1000, consumption_mult } ] }` | template(s) incl. goods |
| `GET /characters/admin/economy/item-groups` | `q?, item_type?, group?` (code \| `none`), `source?` (auto\|manual), `off_market?`, `page, page_size ≤100` | `{ items: [ { item_id, name, item_type, item_rarity, resource_subcategory, is_food, price, image, auto_group, auto_off_market, override_group, override_off_market, group, off_market, in_quests } ], total, page, page_size }` — raw SQL over `items` + `econ_item_groups` + `quest_objectives` |
| `PUT /characters/admin/economy/item-groups` | `{ item_ids: [1..500 ints], group_code?: code\|null, off_market?: bool\|null, reset?: bool }` — fields absent = unchanged, `null` = back to auto, `reset` deletes overrides | `{ updated: n }` |
| `GET /characters/admin/economy/sim` | — | `{ tick_enabled, env_enabled, params: {...}, current_slot_start, next_slot_at, running: run\|null, runs: [last 20 runs] }` |
| `PUT /characters/admin/economy/sim` | `{ tick_enabled: bool, params: EconSimParams }` | as GET |
| `POST /characters/admin/economy/sim/run` | — | run summary `{ id, trigger_kind, status, regions_total, regions_done, regions_failed, started_at, finished_at }`; 409 «Пересчёт уже идёт» |

**Added by B6 (fill):** body option `treasury_to_reserve: bool = true` — the fill also tops up each region treasury to its wage reserve
target (`treasury_target` of a dry-run `simulate_region` step from the filled state, also stored in `econ_regions.treasury_target`)
with the same idempotent `max(0, target − balance)` rule. Reason (found by B5): wages stay 0 until a treasury reaches its 7-day reserve,
so after a fill purses only shrink for ~a week. **Deviation from «one operation»:** the fill posts **one `admin_emission` per region**
(purse leg + treasury leg, `region_id` set so the journal filters by region), idempotency key
`econ_fill:r:<region>:p<last purse posting id>:t<last treasury posting id>` (two concurrent identical clicks → same key → second skipped).
Response: `{ regions, operation_id (last op or null), operation_ids, emitted, emitted_purses, emitted_treasuries, skipped_no_population }`
(`operation_id`/`emitted`/`regions` keep the F1 shape). Regions with population 0 get goods but no money. Validation errors are 422
(FastAPI) with Russian `msg`; GETs of goods-groups/templates return `{items}`.
| `GET /characters/admin/economy/operations` (changed) | `+ exclude_op_type?` (∈ OP_TYPES) | unchanged shape |
| `GET /characters/admin/economy/summary` (changed) | — | `+ totals.population_purses`, region nodes `+ purse_account_id, purse_balance` |

### 3.8 locations-service

`delete_region`: before closing the treasury, `_close_treasury(session, AccountRef.purse(region_id),
AccountRef.country(region.country_id), {...})` (purse → country, untaxed since dst is a country; deactivates the purse).
`econ_core.py` copy updated. Nothing else in stage 2 (stage 3 will read 3.9).

### 3.9 Stage-3 read contract (documented in `docs/services/character-service.md`)

locations-service reads via raw SQL on the shared DB (pattern of `econ_core`): `econ_regions` (simulated =
`template_code IS NOT NULL AND population > 0`), `econ_region_goods.price_mult`, `econ_goods_groups.base_price`,
`econ_item_groups` + `items` fields → `econ_core.auto_item_group` → price per 3.6. Stage 3 will add these SQL strings to
`econ_core` (shared contract) rather than hand-copying them.

### 3.10 Frontend

Admin `src/components/Admin/EconomyPage/` (Tailwind/design system, TS, no `React.FC`, 360 px, every error toast in
Russian, desktop table / mobile cards):
- `EconomyPage.tsx` tabs: Сводка · Журнал · Действия · **Регионы** · **Товары** · **Предметы** · **Шаблоны** · **Пересчёт** · Настройки.
- `EconomyRegions.tsx` — list (template, population, stability/prosperity bars, hunger badge, purse/treasury, last tick),
  filter «только в симуляции»; button «Заполнить регионы по шаблонам» (visible with settings+emit; confirm dialog with
  comment; shows emitted sum). `RegionEconomyEditor.tsx` drill-down: template select + apply, population, tax, stability,
  prosperity, 12-row goods table (editable production/consumption/stock, read-only norm/price/last flows), history table
  of the last ticks (stock & price per group, stability, hunger, tax/wages).
- `EconomyGoodsGroups.tsx` — 12 groups with base price, norms, elasticities, chain inputs editor.
- `EconomyItemGroups.tsx` — paginated item list with filters (type, group incl. «без группы», source, off-market,
  search), multi-select checkboxes + «выбрать все на странице», bulk bar: set group / off-market on/off / reset to auto;
  badges «авто», «вручную», «в заданиях», «вне рынка».
- `EconomyTemplates.tsx` — template list + editor (noun/gender, default population, tax, 12-row production/consumption).
- `EconomyTick.tsx` — status (env + DB toggle, next slot time), toggle, «Пересчитать сейчас» (confirm), last runs table,
  simulation params form.
- `EconomySummary.tsx` — purse total card «Кошельки жителей», purse balance per region row; `EconomyJournal.tsx` —
  checkbox «Скрыть пересчёты регионов» (default on → `exclude_op_type=region_tick`); `economyLabels.ts` — `region_tick`
  «Пересчёт региона», kind `population_purse` «Кошелёк жителей»; `AccountPicker` shows purses.
- API `src/api/economyAdmin.ts` (+ functions), types `src/types/economy.ts`.

Player: new `src/components/WorldPage/RegionEconomyCard.tsx` (fetch via new `src/api/regionEconomy.ts`, local state, no
Redux; renders nothing when `participating=false`; on error a small inline Russian message «Не удалось загрузить
состояние региона» + toast), mounted in `WorldPage.tsx` region view under the title (both map and no-map branches).
Shows phrases as chips and a compact 12-group grid with arrows (lucide icons; `very_*` double arrow, trend as small
secondary icon), tooltip with group name. `regionsSlice.js`/`regionsActions.js` and `EditRegionForm.tsx` are **not** touched.

### 3.11 Security

- Admin endpoints: JWT via user-service `/users/me` + `require_permission` (3.1 #10). Public card: no auth, read-only,
  integer path param, returns only qualitative states (no balances) — existing nginx `/characters/` rate limit.
- Validation: Pydantic v1 bounds listed in 3.7; codes whitelisted against `econ_core.GOODS_GROUPS` / template codes;
  text fields stripped, `<`/`>` rejected; bulk lists ≤ 500; SQL parameterised (LIKE with `!` escape as in stage 1).
- Money: only `region_tick` (purse/treasury/country, no source accounts) and the existing `admin_emission` (fill) move
  gold; `econ_core` keeps rejecting source accounts outside admin ops. Fill and manual run record `actor_user_id`.

### 3.12 Data flow

```
Auto tick:  character-service thread (every 60 s) → INSERT econ_tick_runs(slot) [claim] → per region txn
            { econ_regions/goods FOR UPDATE → econ_sim → UPDATE rows → post_operation(region_tick: purse→region (+10 % region→country),
              country→region grant, region→purse wages) → history } COMMIT → heartbeat
Fill:       Admin UI → POST /characters/admin/economy/regions/fill → txn { goods/stocks from templates;
            post_operation(admin_emission: emission→purse × N) } COMMIT
Card:       WorldPage → GET /characters/economy/regions/{id}/card → econ_regions + goods + templates + econ_accounts (read)
Delete:     locations-service delete_region txn { treasury_closed purse→country; treasury_closed region→country; delete rows }
            → next tick purges orphan econ_regions rows
```

### 3.13 Residual risks / out of scope (developers add to `docs/ISSUES.md`)
- No seasonal production modifiers (calendar lives in locations-service) — later stage.
- No inter-region goods flow until caravans (stage 5): chronic shortages settle at high prices by design.
- `econ_operations` grows ~110 ops/day from ticks — fine; journal hides them by default.
- Manual runs accelerate the world (admin-only, logged).
- Template/group sets are fixed (edit only); adding a 13th group = migration + `econ_core` change.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

General for every backend task: Pydantic v1, `python -m py_compile` on modified files, existing tests stay green,
update `docs/services/<service>.md` (character-service: new «Economy simulation (FEAT-182)» section + stage-3 read
contract), add remaining risks to `docs/ISSUES.md`. **No commits, no pushes.** Frontend: `npx tsc --noEmit` and
`npm run build` inside Docker (no node on host).

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| B1 | **Ledger contract (canonical):** `econ_core.py` per 3.2 (purse kind, `AccountRef.purse`, `OP_REGION_TICK`, `GOODS_GROUPS`, `auto_item_group`, off-market sets); new shared scenarios in `tests/econ_contract_cases.py`; `economy_crud.py` purse awareness (emission target, names, system accounts, summary totals + tree purse fields, `_region_of`); operations `exclude_op_type` | Backend Developer | DONE | `services/character-service/app/econ_core.py`, `app/tests/econ_contract_cases.py`, `app/economy_crud.py`, `app/economy_api.py`, `app/schemas.py` | — | py_compile OK; existing econ tests green; emission into a purse works and summary stays `ok`; purse shows with region name in accounts/journal |
| B2 | **Copies + region deletion:** copy `econ_core.py` and `econ_contract_cases.py` verbatim to inventory-, locations-, dungeon-service; locations `delete_region` closes the purse into the country treasury before the treasury close (3.8) | Backend Developer | DONE | `services/{inventory,locations,dungeon}-service/app/econ_core.py`, `…/app/tests/econ_contract_cases.py`, `services/locations-service/app/crud.py`, `docs/services/locations-service.md` | B1 | `sh scripts/check_econ_copies.sh` passes; each service's contract tests green; deleting a region with a funded purse moves it to the country, invariant `ok` |
| B3 | **Schema + seed:** migration `028_econ_living_regions` (all tables of 3.3, seeds of groups/chains/templates/template goods computed per 3.4, `econ_sim_settings` row with default params), ORM models | Backend Developer | DONE | `services/character-service/app/alembic/versions/028_econ_living_regions.py`, `app/models.py` | — (parallel with B1) | `alembic upgrade head` / `downgrade -1` / upgrade again OK on local MySQL; 12 groups, 8 templates × 12 goods seeded; FK columns indexed; revision id ≤ 32 chars |
| B4 | **Simulation math:** pure `econ_sim.py` per 3.4 (dataclasses in/out, params with defaults, `simulate_region`, `norm_stock`, `price_mult`, card-state helpers incl. Russian phrases with noun gender) | Backend Developer | DONE | `services/character-service/app/econ_sim.py` | — (contract fixed here) | py_compile OK; a 40-tick loop over each template from the starting state stays bounded (prices within 0.5..3, stability/prosperity 0..100, no NaN), specialty groups cheap, food-short templates settle without collapse |
| B5 | **Tick runner + scheduler:** `econ_tick.py` (claim, resume, grant plan, per-region txn, orphan purge, history, retention) and `econ_scheduler.py` (env-gated daemon thread, startup hook in `main.py`) per 3.5 | Backend Developer | DONE | `app/econ_tick.py`, `app/econ_scheduler.py`, `app/main.py` | B1, B3, B4 | Manual call on local DB runs all simulated regions, posts one `region_tick` op each, invariant `ok`; second auto call in the same slot is a no-op; killing mid-run and restarting resumes only unfinished regions; nothing starts when `ECON_TICK_ENABLED` is unset |
| B6 | **Economy API:** all new endpoints of 3.7 (regions list/detail/update/apply-template/fill/history, goods-groups, templates, item-groups GET/PUT, sim GET/PUT/run, public card) with schemas, RBAC, validation | Backend Developer | DONE | `app/economy_api.py`, `app/economy_crud.py` (or new `app/economy_sim_crud.py`), `app/schemas.py` | B1, B3, B4, B5 | curl on local: shapes as 3.7; 401/403 without permission; fill emits once (re-click emits 0), manual run returns summary, 409 while running; card has no balances; `participating=false` for regions without a template |
| D1 | **Env:** `ECON_TICK_ENABLED: "1"` (and optional `ECON_TICK_POLL_SECONDS`) for character-service in `docker-compose.yml` and `docker-compose.prod.yml`; confirm no nginx change needed | DevSecOps | DONE | `docker-compose.yml`, `docker-compose.prod.yml` | — | Both compose files valid (`docker compose config`); env visible in the container |
| F1 | **Admin foundation:** types + API functions for all 3.7 endpoints; new tabs wired in `EconomyPage.tsx`; `EconomyRegions.tsx` + `RegionEconomyEditor.tsx` (incl. fill button and history); summary purse card/column; journal «Скрыть пересчёты регионов»; labels for `region_tick`/`population_purse`; AccountPicker purses | Frontend Developer | DONE | `src/types/economy.ts`, `src/api/economyAdmin.ts`, `src/components/Admin/EconomyPage/{EconomyPage,EconomyRegions,RegionEconomyEditor,EconomySummary,EconomyJournal,AccountPicker}.tsx`, `economyLabels.ts` | B6 contract (3.7) — coding in parallel, live check after B6 | tsc + build pass; 360 px OK; errors toasted in Russian; no `React.FC`; fill → purses appear in summary |
| F2 | **Admin catalogues:** `EconomyGoodsGroups.tsx`, `EconomyTemplates.tsx`, `EconomyItemGroups.tsx` (bulk selection, filters, badges) | Frontend Developer | DONE | `src/components/Admin/EconomyPage/{EconomyGoodsGroups,EconomyTemplates,EconomyItemGroups}.tsx` | F1 | tsc + build pass; bulk assign 20 items in one request; reset to auto works; 360 px OK |
| F3 | **Admin tick tab:** `EconomyTick.tsx` (status, toggle, manual run with confirm, runs table, params form) | Frontend Developer | DONE | `src/components/Admin/EconomyPage/EconomyTick.tsx` | F1 | tsc + build pass; manual run shows result and refreshes; 409 shown as toast |
| F4 | **Player region card:** `RegionEconomyCard.tsx` + `api/regionEconomy.ts`, mounted in `WorldPage.tsx` region view | Frontend Developer | DONE | `src/components/WorldPage/RegionEconomyCard.tsx`, `src/api/regionEconomy.ts`, `src/components/WorldPage/WorldPage.tsx` | B6 contract | Card shows phrases + 12 arrows for a simulated region, nothing for others; no numbers of money; 360 px OK; tsc + build pass |
| Q1 | **QA contract:** tests of the new kind/op type/`auto_item_group` in character-service (`test_econ_*`), contract cases pass in all 4 services; locations-service region deletion closes the purse (invariant asserted) | QA Test | DONE | `services/character-service/app/tests/test_econ_core*.py`, `services/locations-service/app/tests/test_econ_*.py` | B1, B2 | pytest green in all 4 services |
| Q2 | **QA simulation + tick:** unit tests of `econ_sim` (price curve endpoints, chain input limit, affordability → hunger, stability/prosperity moves, wage rule never makes treasury negative, template 40-tick stability); runner tests on SQLite (one op per region, idempotent rerun/resume, `DuplicateOperation` path, failing region isolated, purse never negative, grant split, orphan purge, history retention, scheduler not started without env). Add portable `items`/`quest_objectives` DDL to conftest if needed | QA Test | DONE | `services/character-service/app/tests/test_econ_sim.py`, `test_econ_tick.py`, `tests/conftest.py` | B4, B5 | pytest green; each test < 30 s; whole service step well under CI 6 min |
| Q3 | **QA API:** every 3.7 endpoint — shapes, RBAC 401/403 (fill needs both permissions), validation bounds, `<script>` in names rejected, SQL-injection-like `q`, bulk > 500 rejected, fill idempotent top-up, card hides balances and returns `participating=false`, operations `exclude_op_type` | QA Test | DONE | `services/character-service/app/tests/test_econ_regions_api.py` | B6 | pytest green |
| R1 | **Review + live:** cross-service check (4 copies identical, CI script), security checklist, py_compile/pytest/tsc/build re-run; **live on local**: assign templates to 3–4 regions, «Заполнить регионы по шаблонам», run «Пересчитать сейчас» 3+ times — stock/price/stability/prosperity change in the editor/history, journal shows `region_tick` ops with tax + 10 % + wages legs, summary invariant stays «Сходится»; edit a region to starve (production food 0) → hunger and «голодает» on the player card at `/world/region/:id`; region without template shows no card; 360 px for admin tabs and the card; zero console errors | Reviewer | DONE | all | B1–B6, D1, F1–F4, Q1–Q3 | Checklist passed, invariant `ok` after the live scenario |

Parallelism: B1, B3, B4, D1 start immediately; B2 after B1; B5 after B1+B3+B4; B6 after B5 (can start schemas early).
F1 starts with the 3.7 contract, F2/F3 after F1, F4 any time. Q1 after B2, Q2 after B5, Q3 after B6. R1 last.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-10-29
**Result:** PASS

Scope: whole uncommitted diff of FEAT-182 (35 modified + 17 new files): character-service (econ_core, econ_sim, econ_tick,
econ_scheduler, economy_api, economy_crud, economy_sim_crud, models, schemas, main, migration 028, tests), econ_core +
contract-case copies in inventory/locations/dungeon, locations `delete_region`, both compose files, frontend admin
«Экономика» tabs + player `RegionEconomyCard`, docs.

#### Code review
- **Contract/copies:** `sh scripts/check_econ_copies.sh` — all 8 copies identical. New kind `population_purse` (REF, taxed
  like a player inflow, never negative), `region_tick` op, `GOODS_GROUPS`, `auto_item_group` match 3.2/3.6.
- **Tick (econ_tick.py):** claim via `UNIQUE(slot)`, stale-heartbeat resume by conditional UPDATE (rowcount 1), manual runs
  serialised on the `econ_sim_settings` row + live-run check → 409; grant plan frozen in the run row; one txn per region with
  lock order `econ_regions` → `econ_region_goods` → `econ_accounts` asc (inside `post_operation`), no `characters`; per-region
  idempotency = `last_run_id` + ledger key `region_tick:<run>:r:<region>`; `DuplicateOperation` → counted done, any other
  error → rollback + continue. Fill locks `econ_regions` rows ascending first, then accounts — same order, no deadlock path.
  The purse is read without a lock and debited under the lock: a concurrent admin adjust can only raise `InsufficientFunds`
  → region retried next tick (documented). Manual + auto overlap can step a region twice — acceptable (manual = extra step).
- **Scheduler:** env-gated (`ECON_TICK_ENABLED`), never under pytest, daemon thread, catch-all loop, DB toggle per iteration.
- **Migration 028:** revision id 23 chars; every FK column has its own index (`ix_econ_group_inputs_input`, `ix_etg_group`,
  `ix_econ_regions_template`, `ix_erg_group`, `ix_erh_run`, `ix_eig_group`; composite PKs cover the leading FK columns);
  re-runnable DDL, downgrade drops tables children-first, no ledger rows touched.
- **Security:** every admin endpoint has `require_permission` (`economy:read` GET, `economy:settings` writes, fill =
  settings AND emit via `require_all_permissions`); the public card returns only qualitative states (verified live: no
  digits); item-groups filters whitelisted (item_type/group/source), `q` length-capped and LIKE-escaped, all SQL
  parameterised (`in_params` placeholders for IN lists); bulk ≤ 500; text fields reject `<`/`>` (covered by Q3); errors in
  Russian, no internals.
- **Frontend:** all new files TS/TSX, Tailwind + design-system classes, no `React.FC`, no SCSS, no `window.confirm` (custom
  modals), every API call has a Russian toast/inline error; WorldPage only mounts the card (both branches).
- **QA:** Q1–Q3 present and green (sim 56, tick 26, API 212 + contract cases in 4 services).

#### Fix made by Reviewer
| # | File | Change |
|---|------|--------|
| 1 | `services/character-service/app/econ_tick.py` `_claim_auto` | Read the slot row before the claiming INSERT. Before: the scheduler polls every 60 s and every poll after the slot was taken did a failing INSERT, burning one `econ_tick_runs` AUTO_INCREMENT id per minute (~1 440/day; visible as gaps in «№» of the runs table, e.g. runs 19/20 missing live). The INSERT + `IntegrityError` path stays the real claim for the two-process race. Character tests re-run: 2112 passed; live: AUTO_INCREMENT unchanged across scheduler polls. |

#### Non-blocking notes (UX, for a later pass)
- «Предметы»: the bulk-action bar appears above the list on the first checkbox and pushes rows down ~110 px — a second
  quick click lands on another row. Consider a sticky/bottom bar or reserving its height.
- Player card on desktop: in the 4-column goods grid long group names are truncated («Продово…», «Ремесленный…»); the
  tooltip has the full name. Fine at 360 px (1 column).

#### Automated Check Results
- [x] `sh scripts/check_econ_copies.sh` — PASS (8/8 identical)
- [x] `py_compile` — PASS (all modified/new Python in character, locations, inventory, dungeon)
- [x] `pytest` — PASS: character 2112 passed / 1 skipped (before and after the fix); locations 1797 passed; inventory
  1876 passed / 1 skipped; dungeon 502 tests, exit 0 (`--timeout=30`; this suite prints no summary line)
- [x] `npx tsc --noEmit` — PASS (no errors besides the known EffectRunes filter)
- [x] `vite build` — PASS (built in 53 s; only the usual chunk-size warning)
- [x] `docker compose config` (dev and dev+prod) — PASS
- [x] Live verification — PASS

#### Live Verification Results
- character-service recreated (`ECON_TICK_ENABLED=1` in the container), nginx reloaded; log: «economy tick scheduler
  started (first check in 30s, then every 60s)».
- Регионы: Загрея (34) assigned «Аграрный», population 8000 via the editor (goods created, stock = norm); with the existing
  9 Мэттанхейм / 10 Шепшир / 14 Тэппу-Гаки / 15 Хикари → 5 simulated. «Заполнить регионы по шаблонам» (custom modal with
  comment) → 5 regions, 54 321 to purses + 7 761 to treasuries, 5 `admin_emission` ops.
- «Пересчитать сейчас» ×3 via UI (runs 16–18, 5/5 done) + ×3 via API (21–23): stability/prosperity/treasury/purse and
  per-group stock/price move every run in the editor history (e.g. Загрея stability 71.2 → 72.3 → 73.3, food stock 17 100
  → 17 398 → 17 694, price ×0.989 → ×0.978 → ×0.968).
- Журнал with «Скрыть пересчёты регионов» unchecked shows «Пересчёт региона» ops; op #94 legs: Кошелёк жителей → Загрея
  249, Загрея → Мидденгерд 24 (налог), Мидденгерд → Загрея 20 (грант), Загрея → Кошелёк жителей 261.
- Summary invariant «Сходится» (ledger_sum 0) after the fill, after every run and at the end; purse total card present.
- Starvation: Загрея food production 0 + stock 0 saved in the editor, 3 runs → card at `/world/region/34`: «Край голодает ·
  Волнения · Казна полна · Нехватка: продовольствие · Цены очень высокие», food «очень дорого»; no digits in the card.
  Region without a template (`/world/region/11` Геттенхорн) → no card (`participating:false`). Загрея restored afterwards
  (apply-template, stocks to norm).
- Предметы: 2 items bulk-assigned «Продовольствие» (badge «вручную»), then «Сбросить к авто» → back to «без группы / авто».
  Товары and Шаблоны tabs render. Пересчёт: toggle off/on persisted, param «Хранить историю» 60 → 61 saved (restored to 60).
- RBAC: no token → 401 on the admin list and on fill; card with a non-int id → 422.
- 360 px (same-origin 360 px iframe — the Chrome window could not be resized): all 9 admin tabs and the player card —
  document scrollWidth 341, no element overflowing the viewport.
- Console errors: none (admin tabs, region editor, player region page).

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-10-29 — PM: фича создана (этап 2 экономики), запускаю анализ
[LOG] 2026-10-29 04:00 — Analyst: анализ завершён — 27 регионов без полей населения/типа, 66 предметов (группы выводятся из item_type/resource_subcategory/is_food, кроме еды-ресурсов), фоновых планировщиков с расписанием нет (только циклы-сборщики в dungeon/battle), все сервисы на одном воркере uvicorn; затронуты character-service, locations-service, фронтенд (админка «Экономика», карточка региона); новый вид счёта требует правки всех 4 копий econ_core
[LOG] 2026-10-29 — PM: пользователь ответил на 6 вопросов, запускаю архитектора
[LOG] 2026-10-29 — Architect: спроектировано 15 задач (6 backend, 1 devsecops, 4 frontend, 3 QA, 1 ревью), ~20 API-контрактов; тик в character-service (поток + слот 6 ч + идемпотентность по региону), новый вид счёта «кошелёк жителей», 9 новых таблиц в миграции 028, баланс шаблонов задан; 3 вопроса пользователю с рекомендованными ответами
[LOG] 2026-10-29 — PM: пользователь принял все три рекомендации архитектора (ручной пересчёт = настоящий шаг, группы назначает только админ, род поселения в шаблоне); запускаю B1, B3, B4, D1
[LOG] 2026-10-29 — Backend Dev: B4 готов — чистый модуль econ_sim.py (тик региона, цены, нормы запаса, жалованье/гранты, фразы карточки с родом поселения); прогон 40 и 400 тиков по 8 шаблонам: цены в 0,5–3, без NaN, кошелёк не уходит в минус, казна не уходит в минус от жалованья, профильные товары дешевеют, крепость/шахтёрский при нехватке еды выходят на «недоедает» без обвала; веса достатка вынесены в параметры и снижены (иначе все регионы «богатые») — отмечено в 3.4
[LOG] 2026-10-29 — Frontend Dev: F4 готов — карточка региона для игроков (RegionEconomyCard.tsx + api/regionEconomy.ts) под названием региона в обеих ветках WorldPage: фразы состояния с цветом по тревожности и 12 групп товаров со словом уровня цены и стрелкой ▲/▼/—, без денежных чисел; participating=false — ничего не рисуется, ошибка — мелкая надпись «Не удалось загрузить состояние региона» + тост; tsc и сборка проходят
[LOG] 2026-10-29 — Backend Dev: B1 готов — в econ_core добавлены вид счёта population_purse (облагается налогом как платёж игрока, в минус не уходит), AccountRef.purse, операция region_tick, 12 групп товаров и auto_item_group; 5 новых общих сценариев + 34 случая автогруппы в econ_contract_cases; economy_crud: эмиссия в кошелёк, имена кошельков по региону, итог population_purses и поля кошелька в дереве сводки, фильтр журнала exclude_op_type; тесты character-service: 1780 passed. Копии econ_core в 3 других сервисах ещё старые (это B2) — до B2 CI-проверка копий падает
[LOG] 2026-10-29 — Backend Dev: B3 готов — миграция character-service 028_econ_living_regions: 10 новых таблиц (группы товаров, цепочки, шаблоны регионов с родом «поселения», товары шаблонов, регионы, товары регионов, прогоны тика, история, переопределения предметов, настройки симуляции), засеяно 12 групп, 10 связей цепочек, 8 шаблонов × 12 товаров (сверено с econ_sim.template_production_per_1000), настройки = SimParams по умолчанию; ORM-модели в models.py; upgrade/downgrade/upgrade на локальной БД — ок, pytest зелёный (1780)
[LOG] 2026-10-29 — Frontend Dev: F1 готов — типы и API-функции для всех эндпоинтов 3.7, новые вкладки «Регионы / Товары / Предметы / Шаблоны / Пересчёт» (Товары, Предметы, Шаблоны, Пересчёт — заглушки под F2/F3), список регионов и редактор региона (шаблон, население, налог, 12 товаров, история пересчётов), кнопка «Заполнить регионы по шаблонам» (нужны economy:settings + economy:emit), кошельки жителей в сводке и в выборе счёта, в журнале «Скрыть пересчёты регионов» (по умолчанию включено); tsc и сборка в Docker проходят, живая проверка — после B6
[LOG] 2026-10-29 07:35 — Backend Dev: B5 готов — econ_tick.py (захват слота через UNIQUE(slot), доигрывание упавшего прогона после 10 минут без heartbeat, план грантов в строке прогона, одна транзакция и одна операция region_tick на регион, сломанный регион откатывается и не мешает остальным, уборка удалённых регионов, история и её срок хранения; ручной пересчёт run_manual с отказом RunInProgress → 409) и econ_scheduler.py (поток-демон только при ECON_TICK_ENABLED и не под pytest, DB-рубильник tick_enabled); хук startup в main.py. Проверено на локальной БД: ручной и авто-прогоны по 4 регионам, по одной операции на регион, повтор в том же слоте — no-op, имитация падения после 2 регионов → доигрывание только 2 оставшихся, инвариант сходится; pytest 1780 passed. Остаточные риски тика добавлены в ISSUES.md. Локально оставлены тестовые регионы 9, 10, 14, 15 с шаблонами
[LOG] 2026-10-29 — Backend Dev: B2 готов — econ_core.py и econ_contract_cases.py скопированы байт-в-байт в inventory/locations/dungeon (check_econ_copies.sh проходит); в контрактные тесты трёх сервисов добавлен прогон ITEM_GROUP_CASES (новые сценарии CASES подхватываются сами); delete_region в locations сначала закрывает кошелёк жителей в казну страны без налога, потом казну региона, инвариант 0; +3 теста (кошелёк с золотом, пустой кошелёк, удаление страны). pytest: locations 1765, inventory 1846 (+1 skip), dungeon 443 — всё зелёное
[LOG] 2026-10-29 — Frontend Dev: F3 готов — вкладка «Пересчёт» (EconomyTick.tsx): статус расписания (переключатель в БД, предупреждение, если планировщик не запущен на сервере, следующий слот в местном времени, последний прогон, ход текущего прогона с опросом раз в 5 с), переключатель автопересчёта, «Пересчитать сейчас» с подтверждением (настоящий шаг мира, расписание не сдвигается), итог прогона + обновление сводки, 409 — тост «Пересчёт уже идёт»; таблица последних прогонов (вручную/по расписанию, регионы ok/ошибки, длительность, текст ошибки; карточки на мобильных); форма 30 параметров в 6 разделах с подсказками и значениями по умолчанию, проверкой границ и пар мин/макс, «Отменить изменения» и «Вернуть по умолчанию»; без economy:settings — только просмотр. Границы параметров на фронте — мои допущения (бэкенд B6 проверяет сам). tsc и сборка в Docker проходят; живая проверка — после B6
[LOG] 2026-10-29 — Frontend Dev: F2 готов — вкладки «Товары» (12 групп: базовая цена, норма потребления и запаса, эластичности, редактор цепочки сырья с проверкой на дубли и замыкание цепочки), «Шаблоны» (карточки шаблонов с профильными товарами; редактор: название, описание, слово поселения и род м/ж/ср с предпросмотром фраз «Город сыт / Крепость сыта», население, налог, производство/потребление по всем 12 группам) и «Предметы» (поиск, фильтры тип/группа вкл. «без группы»/источник/рынок, страницы по 50, отметки «авто», «вручную», «вне рынка», «в заданиях», авто-группа при ручной замене; выбор чекбоксами между страницами + «выбрать все на странице», панель массовых действий — назначить группу/вернуть к авто-группе, убрать с рынка/вернуть на рынок, сбросить к авто — одним запросом, не больше 500); без economy:settings — только просмотр (право читается внутри вкладок, EconomyPage не тронут); tsc и сборка в Docker проходят; живая проверка — после B6
[LOG] 2026-10-29 — QA: Q2 готов — test_econ_sim.py (56 тестов: кривая цены и зажимы, норма запаса, лимит цепочки по сырью и порядок переработки, кошелёк → голод, стабильность/достаток, жалованье не уводит казну в минус, гранты ≤ пула, фразы карточки по роду м/ж/ср без чисел, 40 тиков по каждому из 8 шаблонов и стресс-сценарии без NaN) и test_econ_tick.py на SQLite (26 тестов: одна операция на регион, повтор в слоте → None, доигрывание после устаревшего heartbeat только незаконченных регионов, DuplicateOperation = готов, сломанный регион → partial, InsufficientFunds откатывает регион, кошельки/казны не в минусе, раздел грантов, уборка сирот, срок хранения истории, RunInProgress, планировщик не стартует без env и под pytest); conftest не трогал; весь набор character-service: 1900 passed, 1 skipped; багов в econ_sim/econ_tick не найдено
[LOG] 2026-10-29 — QA: Q1 готов — в общие сценарии econ_contract_cases добавлено 10 случаев (налог с кошелька как с игрока, обнуление кошелька до 0, списание кошелька покрыто жалованьем в той же операции, грант/жалованье без налога, повтор ключа region_tick → DuplicateOperation, region_tick не трогает adjustment/emission, admin_adjust на кошельке не уводит в минус, кошелёк без id региона, подставные/неизвестные типы операций) и 19 пограничных случаев auto_item_group; файл скопирован байт-в-байт во все 4 сервиса, check_econ_copies.sh проходит. character: +4 теста API (корректировка кошелька, закрытый кошелёк, скрытие region_tick в журнале, exclude_op_type с инъекциями → 400); locations: +3 (откат удаления региона сохраняет кошелёк, долг казны + кошелёк в одном удалении, кошелёк не уходит в минус через async-реестр); inventory: +1 (все значения enum items покрыты правилом групп). pytest: character 1874 passed, locations 1797, inventory 1876 (+1 skip), dungeon — всё зелёное. Багов в коде не найдено
[LOG] 2026-10-29 07:50 — Backend Dev: B6 готов — все эндпоинты 3.7 (регионы: список/карточка/правка/применить шаблон/история/заполнить; группы товаров; шаблоны; предметы → группы с массовой правкой до 500; настройки симуляции и «Пересчитать сейчас» с 409 при идущем пересчёте; публичная карточка региона без чисел денег) в economy_api.py + новый economy_sim_crud.py + схемы; права economy:read / economy:settings, заполнение — settings + emit. «Заполнить» доливает кошельки и (новая опция treasury_to_reserve, по умолчанию вкл.) казну до резерва жалованья — иначе жалованье неделю нулевое; одна эмиссия на регион, повторный клик даёт 0. Проверено вживую через gateway: заполнение 52 082 → повтор 0, после пересчёта жалованье идёт (Мэттанхейм 768–775 за шаг), 3 одновременных пересчёта → 200 + 409 + 409, инвариант сходится; 401/403 (заполнение без emit или без settings → 403); pytest 1900 passed
[LOG] 2026-10-29 — Frontend Dev: админка подогнана под B6 — в «Заполнить регионы по шаблонам» галочка «Пополнить казну до резерва жалованья» (по умолчанию вкл., treasury_to_reserve), итог раздельно: жителям / в казны / регионы без денег из-за нулевого населения; типы EconFillBody/EconFillResult/EconTickRun дополнены полями ответа; границы параметров на вкладке «Пересчёт» выровнены с ECON_SIM_PARAM_BOUNDS (было шире: price_min от 0,01, хранение истории до 3650 дней и т.п.); остальные вызовы economyAdmin.ts сверены с economy_api.py — расхождений нет; tsc и сборка в Docker проходят
[LOG] 2026-10-29 — QA: Q3 готов — test_econ_regions_api.py (212 тестов): все эндпоинты 3.7 — формы ответов, 401/403 (заполнение — только settings + emit вместе), границы всех 30 параметров симуляции, целые поля, лишние ключи 422, пары мин/макс 400, налог/население/род, `<script>` в названиях → 422, сырьё само для себя и круг в цепочке → 400, SQL-инъекции в поиске безопасны, массовая правка > 500 → 422, сброс нельзя совмещать, «нечего менять» 400, отметка «в заданиях»; частичная правка товаров региона, применение шаблона; заполнение — повтор даёт 0, только недостающая сумма, treasury_to_reserve вкл/выкл, регионы с населением 0 без денег, явный регион без шаблона 400; карточка без чисел денег и participating=false; лимиты истории; пересчёт — итог и 409; exclude_op_type; инвариант ledger (сумма 0) после каждого движения денег. Таблицы items/quest_objectives — только в фикстуре файла, conftest не тронут. Весь набор character-service: 2112 passed, 1 skipped; багов не найдено
[LOG] 2026-10-29 10:20 — Reviewer: проверка завершена, результат PASS — копии econ_core идентичны, py_compile/pytest (character 2112, locations 1797, inventory 1876, dungeon 502)/tsc/сборка зелёные; вживую: шаблон «Аграрный» Загрее, «Заполнить» (5 регионов), 6 пересчётов, в журнале налог + 10 % стране + грант + жалованье, инвариант сходится, голод → «Край голодает» на карточке, регион без шаблона без карточки, 360 px и консоль без ошибок. Исправил сам: тик по расписанию раз в минуту сжигал номер прогона неудачной вставкой — теперь сначала проверяет слот. Мелкие UX-замечания — в Review Log
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

Этап 2 экономики «Живые регионы» готов локально (не закоммичен, не выкачен).

- Регион с шаблоном живёт сам: раз в 6 часов пересчитываются запасы 12 групп товаров, цены (×0,5–×3), голод, стабильность и достаток; пропущенные отрезки не догоняются, упавший пересчёт доделывается.
- Деньги ходят только через книгу счетов: налог кошелёк жителей → казна региона (+10 % в страну), помощь страны 25 % казны по населению, жалованье казна → кошелёк. Новый вид счёта «кошелёк жителей».
- Админка «Экономика»: вкладки Регионы, Товары, Предметы, Шаблоны, Пересчёт; «Заполнить регионы по шаблонам» (жителям + казна до резерва, повторно — только недостающее); «Пересчитать сейчас».
- Игрок видит карточку региона на странице мира: фразы («Крепость сыта», «Нехватка: …») и стрелки цен по 12 группам, без чисел.
- Тесты: character 2112, locations 1797, inventory 1876, dungeon 502 — зелёные; ревью PASS с живой проверкой.
- Мелочи с ревью исправлены: панель массовых действий в «Предметах» закреплена внизу экрана и не сдвигает список; в карточке региона названия групп переносятся, не обрезаются (до 3 колонок).
