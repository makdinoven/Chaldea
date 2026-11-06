# FEAT-206: Фракции — этап 2 (экономика фракций)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-06 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Встраиваем фракции (FEAT-205, этап 1 — сделан, лежит в рабочей копии, ещё НЕ запушен) в экономику мира (FEAT-181…194: двойная бухгалтерия/ledger, казны регионов и стран, кошелёк населения, тик 6 ч, торговцы, рынок региона по 12 группам товаров, марки). У каждой фракции — своя казна и «условные участники» (NPC-масса), которые имитируют экономическую жизнь фракции. Марки не появляются из воздуха и не исчезают — всё через ledger.

### Бизнес-правила (решения пользователя + варианты PM по умолчанию)
**Казна (решение пользователя):** у каждой фракции свой счёт в общей книге (как у регионов/стран). Пополняется: взносы участников, доход по профилю фракции, пожертвования игроков. Тратится: жалованье участникам, закупки для интенданта, награды игрокам марками.

**Условные участники (решение пользователя):** число NPC-членов фракции (например, 300). Раз в 6 часов фракция «живёт» (в существующем экономическом тике).
- Доходы (вариант PM): взносы участников — из кошелька населения края штаба фракции; доход по профилю шаблона (например, торговцы — от оборота рынка края, убийцы — «заказы», храм — пожертвования населения) — тоже из кошелька населения/казны края по правилам шаблона, без эмиссии.
- Расходы (вариант PM): жалованье участникам — обратно в кошелёк населения края штаба; закупка товаров для интенданта — с рынка края штаба по региональной цене (деньги уходят в регион, товар — из запаса региона).
- **Шаблоны фракций** (как шаблоны регионов): «Орден», «Гильдия торговцев», «Тёмная гильдия», «Храм», «Академия» — задают профиль доходов/расходов и стартовые числа. Админ назначает шаблон и может переопределить числа.
- **Богатство фракции 0–100** (вариант PM): от казны относительно её нормы; влияет на рост/убыль числа участников (медленно) и на бюджет закупок интенданта. Игрокам показывать словами (например «Процветает / Держится / Бедствует»), без чисел; админ видит числа.

**Пожертвования игроков (решение пользователя — «пополнение казны»):** игрок-участник жертвует марки в казну → получает очки фракции (вариант PM: курс — настройка, по умолчанию 10 марок = 1 очко; дневной лимит очков с пожертвований — настройка). Пожертвование предметов — НЕ в этом этапе (вариант PM; можно позже).

**Награды марками за звание (решение пользователя):** платятся из казны фракции. Если в казне не хватает — **долг**: звание даётся, деньги выплачиваются, когда казна пополнится (очередь по времени, частичные выплаты допустимы — вариант PM). Игрок видит долг фракции перед ним во вкладке.

**Интендант (вариант PM, «как предлагаешь» на этапе обсуждения):** NPC с ролью «Интендант», привязанный к фракции (в её штабе или любой локации). Ассортимент задаёт админ: предмет, цена, минимальное звание, запас (конечный). Покупать могут только участники нужного звания; скидка по званию (настройка ранга, например 0/5/10/15 %). Деньги за покупку — в казну фракции. Пополнение запаса — в тике: закупка с рынка края (для предметов из групп рынка) за счёт казны в пределах бюджета от богатства; предметы вне рынка (свитки, рецепты, легендарные) — пополняет только админ.

**Админка:** вкладка экономики во фракции (казна, приток/отток за тик, участники, богатство, шаблон, долги, история операций), редактор шаблонов, ассортимент интенданта, настройки (курс пожертвований, лимиты), кнопка «Заполнить по шаблону» (стартовая казна — как у регионов: из эмиссии через admin-операцию ledger с комментарием).

**Игроку:** во вкладке «Фракции» — богатство словами, кнопка «Пожертвовать», долг фракции перед игроком; страница интенданта (покупка по званию). В каталоге — богатство словами (у тайных — скрыто).

### Edge Cases
- Казна пустая → жалованье/закупки не платятся (участники медленно уходят), награды марками → в долг.
- Регион штаба не задан / фракция без штаба → доходы/расходы, завязанные на край, не идут (решит архитектор: требовать штаб для экономики).
- Удаление/скрытие фракции с деньгами в казне — решит архитектор (вариант: деньги остаются, фракция не тикает).
- Тайная фракция: богатство и интендант не раскрывают её не-членам.
- Сумма денег мира сохраняется (тесты на инвариант ledger, как в FEAT-181+).
- Все сроки — обратным отсчётом, не «до ЧЧ:ММ».

### Вопросы к пользователю
- [x] Своя казна + условные участники → Да (пользователь)
- [x] Марки за звание при пустой казне → в долг (пользователь)
- [x] Остальное — варианты PM приняты (курс 10 марок = 1 очко + дневной лимит, интендант с ассортиментом от админа, шаблоны, богатство словами).

**Решения по вопросам аналитика (пользователь: «Как предлагаешь», 2026-11-06):**
- [x] Закупки интенданта с рынка края → платит в КОШЕЛЁК НАСЕЛЕНИЯ края (как обычные торговцы), не в казну края.
- [x] Пожертвования → считаются заработанными очками: ДА, штраф −50 % у враждебных фракций применяется. Жертвовать можно откуда угодно (кнопка во вкладке фракции).
- [x] Марки добавлены к званию позже → ретроактивно НЕ платим (награда звания — один раз в момент получения).
- [x] Долг фракции перед игроком → сохраняется при выходе/исключении/скрытии фракции и выплачивается при пополнении казны. Игрок видит долг ЧИСЛОМ; богатство фракции — только словами.
- [x] Не-член кликает интенданта тайной фракции → «Этот человек с вами не разговаривает»; ни фракции, ни товаров.
- [x] Неуплата жалованья → участники уходят до 5 %/тик, пока казна пуста; при здоровой казне приходят до 1 %/тик; границы числа участников — настройка админа (по умолчанию 10…5000).
- [x] Боевой пропуск → марки за звание считаются «заработанными»; пожертвования и покупки у интенданта — «потраченными».
- [x] Фракция без штаба / штаб вне симулируемого края → нет тика (взносы/жалованье/закупки), но пожертвования, продажи интенданта и марки за звания работают.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Paths are relative to `services/`. Line numbers are as of the uncommitted working tree on top of `34e0d0d` (FEAT-205
present but not pushed). **Note:** `features/DONE-FEAT-205-factions-core.md` contains only §1, §2 and §7 — the FEAT-205
Architecture Decision (§3, referenced from code as «FEAT-205 §3.x» and from `docs/services/character-service.md:2473`
as `features/FEAT-205-factions-core.md §3`) is not in the repo any more. The code itself is the stage-1 contract.

### Affected Services

| Service | Type of changes | Files |
|---------|-----------------|-------|
| character-service (owner) | new account kind + op types in the ledger contract, faction-economy tables (migration 046), faction step in the 6 h tick, donation / debt / quartermaster flows, admin economy API, wealth words in catalog / tab | `app/econ_core.py` (canonical, ×4 copies), `app/econ_tick.py`, new `app/faction_econ_*.py` (following the `econ_*`/`economy_*_crud` split), `app/faction_crud.py`, `app/faction_rewards.py`, `app/faction_api.py`, `app/economy_crud.py`, `app/models.py`, `app/schemas.py`, `app/alembic/versions/046_*.py`, `app/tests/econ_contract_cases.py` (×4 copies) |
| locations-service | byte-identical `econ_core.py` copy (+ `tests/econ_contract_cases.py`); only if the quartermaster shop is built there: shop endpoints | `app/econ_core.py`, `app/tests/econ_contract_cases.py`, maybe `app/main.py` |
| inventory-service / dungeon-service | byte-identical `econ_core.py` + `tests/econ_contract_cases.py` copies only (CI `econ-contract-copies`) | `app/econ_core.py`, `app/tests/econ_contract_cases.py` |
| battle-pass-service | decision only: should faction ops count for «заработай / потрать марки» tasks | `app/crud.py:413-423` (`LEDGER_EXCLUDED_OP_TYPES`) |
| user-service | RBAC permissions (migration 0035) + test section | `alembic/versions/0035_*.py`, `tests/test_rbac_permissions.py` |
| frontend | profile tab (wealth words, donate, debt), catalog wealth, quartermaster modal + new NPC role, admin faction economy tab / templates / assortment, economy labels | see §6 below |

### Existing Patterns
- character-service: sync SQLAlchemy, Pydantic v1, Alembic head **`045_factions_core`** (`app/alembic/versions/045_factions_core.py:20-21`). All world-economy code lives here (not in locations-service). Raw parameterised SQL + ORM mix; every money move only via `econ_ledger.post_operation`.
- locations-service: async; owns NPC shops (`npc_shop_items`), quests, houses; has the async ledger copy (`app/econ_ledger.py`, canonical async).
- Shared contract files are **byte-identical copies** guarded by CI (`.github/workflows/ci.yml:116-129`, `scripts/check_econ_copies.sh`): `econ_core.py` ×4 (character, inventory, locations, dungeon), `tests/econ_contract_cases.py` ×4, sync `econ_ledger.py` ×2, async ×2. Any new account kind / op type = edit canonical `character-service/app/econ_core.py` and copy byte-for-byte.

---

### 1. World economy — current state

**Ledger (FEAT-181, migration `027_world_economy`)**
- Tables: `econ_accounts` (`models.py:473`; `kind VARCHAR(32)`, `ref_id`, `balance`, `allow_negative`, `is_active`, UNIQUE(kind, ref_id)), `econ_operations` (`models.py:492`; `op_type VARCHAR(50)`, `idempotency_key VARCHAR(128)` UNIQUE, `comment`, `metadata` JSON, `actor_user_id`, `region_id`), `econ_postings` (`models.py:517`; legs, `leg_type`, CHECK amount>0). Character money stays in `characters.currency_balance` (account row kind `character` with balance 0), ORM writes to it are blocked by a strict guard (`models.py:1780-1785`, `econ_ledger.install_balance_guard` `econ_ledger.py:322`).
- Contract `econ_core.py`: account kinds `:46-68` (`character, region_treasury, country_treasury, world_treasury, auction_escrow, auction_storage, emission, adjustment, population_purse, bank, bank_deposits, caravan_escrow`); `REF_KINDS` (ref_id>0) `:71`; singleton names `:77`; `NEGATIVE_ALLOWED_KINDS` `:87` (treasuries + sources); `SOURCE_KINDS = {emission, adjustment}` `:92`; `TAX_SOURCE_KINDS` `:97` (a leg X→region_treasury from these kinds gets an auto +10 % region→country `tax` leg, `add_tax_legs` `:549`); op types `:105-175` grouped in frozensets (`BANK_OP_TYPES`, `MINT_OP_TYPES`, `CARAVAN_OP_TYPES`, `GUILD_OP_TYPES`, `LAW_OP_TYPES`); `SOURCE_OP_TYPES` `:178` (only these may touch emission/adjustment); `COMMENT_REQUIRED_OP_TYPES = {admin_emission, admin_adjust}` `:181`; leg types `:187-199`; `SQL_ACCOUNT_NAME` per kind `:656-663` (name snapshot at lazy account creation).
- Executor `econ_ledger.post_operation` (`econ_ledger.py:217-298`): validate → tax legs → journal row (idempotency: `DuplicateOperation` on reused key, `:189-214`) → lazy `get_or_create_account` (`:157`) → conditional UPDATEs (non-negative accounts raise `InsufficientFunds`) → postings. Never commits; caller locks business rows first, posts last, commits; no HTTP inside a transaction (`:7-11`).
- Invariant: `sum(characters.currency_balance) + sum(econ_accounts.balance) = 0` + sub-invariants (auction, vault, caravan escrow) in `economy_crud.get_summary` (`economy_crud.py:156-227`); tests use local `_assert_invariant` helpers (e.g. `tests/test_econ_character_flows.py:124`, `test_econ_tick_banks.py:116`, `test_econ_guild_api.py:330`) and the cross-service `tests/econ_contract_cases.py` (runner checks each op-type group: e.g. caravan escrow kind rules at `:826-865`).

**Treasuries / purse.** `AccountRef.region/country/purse/world` (`econ_core.py:252-277`). Region treasury and country treasury may go negative; `population_purse` (ref = region_id) may NOT. `treasury_for_location` (`econ_ledger.py:115`) resolves location → region → else world treasury.

**Region tick (FEAT-182, `econ_tick.py`)** — docstring `:1-60` is the authoritative description.
- Scheduler: daemon thread `econ_scheduler.py`, poll 60 s; `run_scheduled_once` (`:91-105`) = reputation decay → law pass → **faction pass (FEAT-205, every 5 min, NOT economy)** → if DB toggle `econ_sim_settings.tick_enabled` → `econ_tick.run_tick`. Env `ECON_TICK_ENABLED`; never under pytest.
- Claim: auto run inserts `econ_tick_runs(slot = floor(unix/21600))`, UNIQUE(slot) (`models.py:677-697`, `_claim_auto` `econ_tick.py:721`); dead run resumed after 10 min heartbeat staleness; missed slots never caught up; manual run (`POST /admin/economy/sim/run`, `economy_api.py:503`) = slot NULL extra step.
- Order in `run_tick` (`econ_tick.py:1302-1486`): prepare merchants → events pass → **quota pass** (season, own tx) → **caravan pass** → region loop (`_process_region` `:779`, one tx per region: `econ_regions` FOR UPDATE, skip if `last_run_id == run_id`, goods, events, guild, merchants; one `region_tick` op with legs purse→treasury (tax+wealth tax), country→treasury (grant), treasury→purse (wages) `:950-964`, key `region_tick:<run>:r:<region>`) → guild sweep → **mint pass** (`_mint_pass` `:1625-1658`: one tx per country, key `mint_court:<run>:c<country>`, `DuplicateOperation` → skip, failures counted + retried next run) → bank pass → collection pass → run row closed with error summary.
- Global lock order (docstring `:44-50`): `econ_regions → econ_region_goods → econ_region_events → npc_shop_items (asc id) → econ_banks → bank_deposits → bank_loans → characters (asc id) → econ_accounts (asc id)`.
- Participating region = `econ_regions.template_code IS NOT NULL AND population > 0` (`SQL_PARTICIPATING` `econ_tick.py:412-416`).

**Region templates + «Заполнить по шаблону» (FEAT-182/186).** `econ_region_templates` (`models.py:581`, code PK, seeded by migration, defaults: population, tax, class mix) + `econ_template_goods` (`:603`); per-region state `econ_regions` (`:617`, incl. `treasury_target`, `last_income/tax/wages/grant`, `last_run_id`, FEAT-193 `guild_budget`, FEAT-194 `wealth_norm`). Admin: `GET/PUT /admin/economy/templates[/{code}]` (`economy_api.py:366-385`, edit only, no create), `POST /admin/economy/regions/{id}/apply-template` (`:322`), `POST /admin/economy/regions/fill` (`:281-297`, needs BOTH `economy:settings` and `economy:emit` via `require_all_permissions` `:255-262`). `economy_sim_crud.fill_regions` (`economy_sim_crud.py:425-~570`): top-up = `max(0, target − balance)`, one `admin_emission` op per region with mandatory comment, key `econ_fill:r:<region>:p<last purse posting>:t<last treasury posting>` (stable per account state → re-click emits 0), `apply_tax=False`; FEAT-186 can also return the excess to `emission`.

**Goods groups / market (FEAT-182/183).** `econ_goods_groups` (`models.py:549`, 12 groups, `base_price`, norms, elasticities, class demand) ; `econ_region_goods` (`:655`, `stock` DECIMAL(16,3) abstract units, `norm_stock`, `price_mult`). Item → group: `econ_core.auto_item_group` (`econ_core.py:421-448`) + admin overrides `econ_item_groups` (`models.py:732`, `group_code`, `off_market`), effective via `effective_item_group` (`:794`). **Off-market** = `item_type in {scroll, recipe}` or rarity ≥ legendary (`:398-399`) — exactly the brief's «вне рынка (свитки, рецепты, легендарные)». Price helpers: `market_ask` `:846`, `wholesale_price` `:870`, `units_per_item(base_ask, group_base)` (used in `econ_merchant.py:246`), `shop_row_prices` `:1087`.

**NPC merchants (FEAT-183).** `npc_shop_items` (locations-service `models.py:467-489`: `npc_id`, `item_id`, `buy_price/sell_price` = base prices at mult 1, `stock` finite, `restock_target`, `origin` admin|player). **Any NPC with an active `npc_shop_items` row is a merchant** (`econ_tick.SQL_MERCHANT_NPCS` `:514`); "living" when the NPC's location resolves to a participating region (`econ_core.merchant_status` `:994-1014`). Living merchants own cash (`characters.currency_balance` of the NPC), sell at region prices, restock in the tick from the **region stock** paying the **wholesale price to the population purse** (`econ_merchant.py:1-21`, step 3), residents buy from them (purse budget `merchant_purse_share`). Admin cash top-up via emission: `POST /admin/economy/merchants/fund` (`economy_api.py:448`).
- Player buy flow (locations-service `main.py:3049-3231`): ownership + activity lock + FEAT-145 NPC dialogue gate + same location + reputation terms + charisma discount; ONE tx: conditional stock take (`crud.take_shop_stock` `crud.py:5047`) then payment (`charge_player_to_merchant` `crud.py:5064`: player→NPC + NPC→region `trade_tax`; legacy: `charge_character_op` `:4855` player→treasury); commit; then HTTP `POST /inventory/internal/characters/{cid}/items` (not idempotent); on failure compensation = stock back + `reverse_operation` (`npc_shop_buy_refund`, treasury fallback).

**Social classes / wealth norm (FEAT-194).** `econ_classes.py` (pure), `econ_regions.class_*`, `wealth_norm` (purse norm), wealth tax rides in the `region_tick` purse→treasury leg (`econ_tick.py:950-952`). Player-facing words only (`econ_sim.region_card`, `TREASURY_LABELS` `econ_sim.py:820`, `treasury_state(treasury, target)` `:855-858` with shares 1.0 / 0.4) — **the ready pattern for «богатство фракции словами»**; public card `GET /characters/economy/regions/{id}/card` (`economy_api.py:267`, `economy_sim_crud.region_card` `:948`).

**Mint / quota (FEAT-191)** — the only non-admin emission: `mint_court`, `mint_player`, `season_quota` (∈ `SOURCE_OP_TYPES`, `MINT_OP_TYPES`, no comment), docs `docs/services/character-service.md:1149-1222`. **Caravans (FEAT-192)** — purse→`caravan_escrow`→seller purse/duty, own pass before the region loop. **Guild orders (FEAT-193)** — per-region allowance as a share of the purse (`guild_purse_share`, `econ_sim.py:163`), hand-in in character-service writes `character_inventory` directly (cross-ownership, `economy_guild_crud.py:10-23`), daily XP cap table `econ_guild_xp_days(character, day)` — reusable pattern for a **daily donation-points limit**.

**Admin economy (frontend `components/Admin/EconomyPage/*`, backend `economy_api.py`).** Permissions `economy:read|emit|adjust|settings` (user-service `0032`). Emission `POST /admin/economy/emission` (`economy_api.py:209`, `economy_crud.emit` `economy_crud.py:440`: only to `EMISSION_TARGET_KINDS` `:26` = region/country/world treasury + purse), adjust `POST /admin/economy/adjust` (`:224`, `ADJUST_FORBIDDEN_KINDS` `:35`), both with mandatory comment (`COMMENT_REQUIRED_OP_TYPES`). Journal `GET /admin/economy/operations` filters by `account_id`, `character_id`, `op_type`, `region_id`, dates (`economy_api.py:163-194`) — enough for a faction «история операций» by account_id. Accounts list (`economy_crud.list_accounts` `:308`, `SQL_ACCOUNTS_UNION` `:290` joins names only for region/country kinds — a faction kind falls back to the stored `a.name`). Summary totals per kind are hard-coded (`get_summary` `:162-209`); unknown kinds still count in `held` and appear in `_system_accounts` (`:272-279`). Frontend labels: `EconomyPage/economyLabels.ts` (`OP_TYPE_LABELS` `:5`, `ACCOUNT_KIND_LABELS` `:53`, `EMISSION_KINDS` `:100`, `ADJUST_KINDS` `:108`, `ALL_ACCOUNT_KINDS` `:117`), type union `types/economy.ts:21`.

### 2. A «faction treasury» account and a faction step in the tick

**Account kind.** Fits as a new REF kind (ref_id = `factions.id`) e.g. `faction_treasury`: add to `ACCOUNT_KINDS`, `REF_KINDS`, `SQL_ACCOUNT_NAME` (`SELECT name FROM factions WHERE id = :ref_id`), an `AccountRef.faction()` constructor; decide NEGATIVE_ALLOWED (brief implies **not** — empty treasury → `InsufficientFunds` → debt) and TAX_SOURCE (irrelevant unless a faction pays into a region treasury: then `faction→region` legs would get the 10 % country tax only if the kind is in `TAX_SOURCE_KINDS`). `kind` is VARCHAR(32) and `op_type` VARCHAR(50) — **no DB migration needed** for the ledger itself (account rows are created lazily). Cost: the 4 byte-identical `econ_core.py` copies + 4 `econ_contract_cases.py` copies + contract case(s) for the new kind/ops (pattern: caravan block `econ_contract_cases.py:826-865`).
**Op types** (one frozenset, e.g. `FACTION_OP_TYPES`): dues purse→faction, profile income (purse/region→faction), wages faction→purse, quartermaster restock faction→purse (or →region, see Q), quartermaster sale character→faction, donation character→faction, rank marks reward faction→character, plus admin start capital via the existing `admin_emission` (requires adding the kind to `EMISSION_TARGET_KINDS`, `economy_crud.py:26`, and to the frontend `EMISSION_KINDS`). None of them is a source op. Battle-pass «earn marks» counts every posting to a character except `LEDGER_EXCLUDED_OP_TYPES` (`battle-pass-service/app/crud.py:413`) → faction rewards would count, donations would count as «spent» unless excluded (Q).
**Tick step.** Best fit = its own pass in `run_tick` **after the region loop** (like `_mint_pass`, `econ_tick.py:1625`): one transaction per faction (ascending id), so a failing faction is rolled back alone, counted in `RunSummary` and the run `error` text. Idempotency: ledger key `faction_tick:<run_id>:f<faction_id>` (+ `DuplicateOperation` → skip) and a `last_run_id` column on the faction-economy row (same as `econ_regions.last_run_id`) so a resumed run skips done factions. Locks inside that transaction must respect the global order: `econ_regions(hq) → econ_region_goods(hq)` (only if restocking from the market) → faction-economy row → quartermaster stock rows → characters (debt payouts, asc id) → accounts (by `post_operation`). Running after the regions means it uses this run's fresh prices/purse; dues/wages from the purse do not interfere with `region_tick` maths of the same run. Manual run (slot NULL) also steps factions. The tick only runs when the DB toggle is on; the 5-min `faction_pass` (conditions/outbox) is separate and must stay non-economic.
**HQ region:** `factions.hq_location_id` (`models.py:1584`, nullable) → `econ_ledger.resolve_location` (`econ_ledger.py:105`) → region; participating check as in `SQL_PARTICIPATING`.

### 3. NPC roles, shops and a «Интендант»

- `characters.npc_role` is a free `String(50)` (migration `003_add_npc_fields.py`), **no backend validation**; role list is frontend-only `constants/npc.ts:1-49` (labels + icons). Role-specific windows are opened in `pages/LocationPage/NpcProfileModal.tsx` by `npc.npc_role === 'banker' | 'minter' | 'guild' | 'teleport_master'` (`:341-403`), each with its own modal (`BankModal/`, `MintModal/`, `GuildModal/`) and a character-service API (`/characters/economy/bank|mint|guild/npc/{npc_id}`); the role is re-checked server-side (`economy_bank_crud.py:289`, `economy_guild_crud.py:403`). The guild hand-in also checks the FEAT-145 dialogue gate via `locations_client.check_npc_gate` (`economy_api.py:1103-1114`).
- The ordinary «Магазин» button appears when `GET /locations/npcs/{id}/shop` is non-empty (`NpcProfileModal.tsx:91-100`). **Reusing `npc_shop_items` for the quartermaster is risky:** the tick treats every NPC with active shop rows as a merchant (`SQL_MERCHANT_NPCS`), so residents would buy from him, he would restock with his own cash, get funded by «Пополнить кассы», sell to non-members via the public shop and use region `price_mult`. The established alternative is the banker/mint/guild pattern: a separate assortment table in character-service, its own modal and endpoints, role `quartermaster` (new value in `constants/npc.ts`).
- Binding NPC↔faction: nothing exists except `factions.leader_npc_ids` JSON (`models.py:1585`). A new binding (column or table) is needed.
- Delivering bought items: options already in the codebase — (a) HTTP `POST /inventory/internal/characters/{cid}/items` after commit with compensation (NPC-shop pattern) or via an outbox (faction rewards `faction_rewards.py:167-183`, «uncertain» on timeouts); (b) direct `character_inventory` write in the same transaction (guild pattern, cross-ownership).
- Market vs fixed-price items: effective group via `econ_item_groups` override → `auto_item_group`; `off_market` items (scroll / recipe / legendary+ / admin flag) never trade on the market → «пополняет только админ». Restock from the region stock converts items to abstract units with `units_per_item(base_ask, group_base)`; a living merchant's restock is region stock −, money **to the population purse** at `wholesale_price` (`econ_merchant.py` step 3), not to the region treasury.

### 4. Faction stage-1 extension points

- **Rank rewards** (`faction_crud.grant_rank` `faction_crud.py:414-443`): once per (character, rank) forever (`faction_rank_grants` UNIQUE, `models.py:1700-1716`); creates `faction_reward_deliveries` outbox rows (`models.py:1719-1738`, kinds `xp|title|item|voucher` `faction_core.py:60-65`), delivered post-commit by `faction_rewards.deliver_pending` and retried by the 5-min pass (`faction_pass.py:150-153`). A marks reward fits as a new column `faction_ranks.reward_marks` + a new step in `grant_rank`. The outbox semantic (max attempts → `failed`, backoff ≤ 24 h, `faction_rewards.py:37-43,133-139`) does **not** match an open-ended debt; a separate debt row/queue (character, faction, grant_id, amount, paid, created_at) paid FIFO with partial payments from the tick and/or after donations is the natural fit; the payout itself is a ledger op `faction→character` that can live inside the rank-up transaction (no HTTP) when the treasury has money. Rank-up notification text is built from `reward_parts` (`faction_crud.py:395-411`) — add marks / «в долг» there. Note: ranks already granted before stage 2 will never pay a newly added marks reward (grant is once).
- **Points from donations:** `change_points` (`faction_crud.py:716-726`, clamps at 0, logs with `event_key` → UNIQUE(event_key, faction_id) idempotency `models.py:1760`), then `recheck_ranks` (`:492-522`) for auto rank-ups; quest flow applies the hostile penalty (`quest_completed` `:729`, `fc.hostile_penalty`) — whether donations trigger it is a product question. New log event type needed (`faction_core.py:45-58`) and history text (`faction_crud.history_text` `:981`).
- **Player tab:** `ProfilePage/FactionsTab/FactionsTab.tsx` (239 lines) → `FactionMembershipCard.tsx` (180; warning banner `:128`, next-rank `:130`, «Покинуть» `:146`) — place for wealth words, «Пожертвовать», debt. Data from `faction_crud.private_view` (`:911-978`) → add fields there. Countdown helper `secondsToDate` (`api/factions.ts:270`).
- **Catalog:** `pages/FactionsPage/FactionCard.tsx` (member count hidden for secret factions `:33-34`) fed by `faction_crud.catalog` / `_catalog_items` (`:824-892`) — add a wealth word, hidden for secret factions to non-members.
- **Admin:** `Admin/FactionsPage/FactionsAdminPage.tsx` (sub-tabs `:14-22`: factions, hostility, applications, members, settings) and `FactionEditor.tsx` (single page with sections «Основное», `RanksEditor`, `ConditionsEditor`, «Враждебность», `:195-317`) — economy can be a new section or sub-tab; templates editor = new sub-tab; rank marks field in `RankFormModal.tsx` (`:64-106`). Settings row `faction_settings` (`models.py:1766-1777`, bounds `faction_core.SETTINGS_BOUNDS` `:104`, admin `GET/PUT /admin/factions/settings` with `factions:settings`) — natural home for donation rate / daily limit. Admin character card `Admin/CharactersPage/tabs/FactionsTab.tsx` lists deliveries (`:144-150`) — place to show debts.
- **API wrappers:** `faction_api._read/_write` (`faction_api.py:71-97`) + `_dispatch` post-commit; owner check `_require_owner` (`:62-68`); admin perms `factions:read|edit|delete|manage|settings` (`:47-51`).
- **Delete/hide:** `delete_faction` refuses when members/applications/grants exist (`faction_admin_crud.py:187-203`); `is_active=false` = hidden. A treasury with money needs a rule (account `deactivate_account` exists, `econ_ledger.py:179`; `treasury_closed` op type exists for region/country closure).

### 5. Player paying marks — reusable patterns

- `law_crud.pay_fine` (`law_crud.py:936-956`): character→region treasury, `op_type=law_fine`, key `law_fine:<encounter>`, `InsufficientFunds` → 400 with `_insufficient_message`, `DuplicateOperation` → treated as already paid. Simplest template for a donation.
- Bank (`economy_bank_crud.py:229-235`, schema `_BANK_REQ_ID` regex `schemas.py:2553`): client `request_id` → key `bank:<op>:c<cid>:<request_id>`, pre-check → 409 «уже выполнено». Frontend generates `newRequestId()` (`pages/LocationPage/BankModal/bankFormat.ts:42-48`) per click, double-click guard `pendingRef` (`BankModal.tsx:71-90`), then `dispatch(fetchProfile)` to refresh the header balance. Same in Mint/Guild modals. **Best fit for «Пожертвовать».**
- Teleport fee (`crud.py:3886`, `OP_TELEPORT`), house tax / purchase (locations-service async `houses.py:2323` `_charge(... "house_tax")`) — async variants, not needed if donations live in character-service.

### 6. Migrations and RBAC

- Alembic heads now: character-service **045_factions_core** (next `046_*`; revision ids ≤ 32 chars — MySQL gotcha), locations-service **058_quest_faction_vouchers**, user-service **0034** (next `0035`), inventory-service **035_item_stealth_modifier** (no change expected). The ledger needs no schema change (VARCHAR kinds / op types).
- New tables likely (character-service): faction economy state (treasury target / members count / wealth / template / last tick values / last_run_id), faction templates (seeded, like `econ_region_templates`), debts, quartermaster binding + assortment, daily donation counter, history per tick (like `econ_region_history`). No FK to locations/items (house rule for cross-service ids).
- RBAC: existing `factions:*` (0034: moderator read/edit/manage) and `economy:*` (0032: moderator read). «Заполнить по шаблону» for regions requires `economy:settings` + `economy:emit` together — the faction start capital should keep the emission behind `economy:emit`. Whether a new `factions:economy` permission is needed or `factions:settings` + `economy:emit` suffice is an Architect decision. Any new permission → 0035 migration + explicit seed section in `user-service/tests/test_rbac_permissions.py` (CLAUDE.md §10.13).

### Cross-Service Dependencies
- character-service → inventory-service `POST /inventory/internal/characters/{cid}/items` (quartermaster item delivery, if HTTP), already used by `faction_rewards`.
- character-service → locations-service `check_npc_gate` (FEAT-145 dialogue gate, `locations_client`), if the quartermaster requires it like the guild.
- Shared DB reads: `Locations`/`Regions` (HQ region), `items` + `econ_item_groups` (market group), `econ_region_goods` (region stock/prices) — all already read by character-service.
- Ledger contract copies: inventory, locations, dungeon services must receive the identical `econ_core.py` / `econ_contract_cases.py` (CI fails otherwise) — even though they never use the new kind.

### Risks
- **Contract drift:** 8 files must change byte-identically → Mitigation: one task edits canonical + copies, runs `sh scripts/check_econ_copies.sh`.
- **Money conservation:** new flows from purse/region into a non-negative faction account and back → Mitigation: invariant tests per flow (`_assert_invariant` pattern), no source ops except admin emission.
- **Purse competition:** dues/profile income/restock take from the same `population_purse` that merchants (`merchant_purse_share` 5 %), caravans (25 %), guild (25 %) and wealth tax use → a large faction (300 members) in a small region can drain it → Mitigation: cap as a share of the purse per tick, like the other consumers; architect sizes.
- **Quartermaster via `npc_shop_items` would turn him into a living merchant** (see §3) → separate table.
- **Lock order / deadlocks** between the tick faction step (region goods → faction → accounts) and player flows (quartermaster buy, donation: faction row → characters → accounts) → keep the documented global order.
- **Secret factions leak** via a visible NPC role «Интендант» (location NPC list shows role label/icon to everyone), wealth words, journal operations → hide/neutral label for non-members.
- **Debt + «once forever» grants:** debt must survive leave/expel/rejoin and faction hiding; unpaid debts must not block the tick.
- **Item delivery non-idempotent** (inventory HTTP) → compensation or outbox with «uncertain».
- **Battle-pass side effect:** faction reward marks count as «earned», donations / quartermaster purchases as «spent» unless excluded.
- **Missing FEAT-205 §3** in the repo → stage-2 Architect cannot reference the stage-1 contract by section; recreate a short summary in FEAT-206 §3.

### Open questions for PM (product)
1. Restock purchases: money to the **region treasury** (brief) or to the **population purse** (how living merchants already pay for region stock)?
2. Do donations trigger the hostile-faction penalty (−50 % in hostile factions) like quest points? Must the player be anywhere specific (HQ / near the quartermaster) to donate, or from the profile tab anywhere?
3. Marks reward for ranks: retroactive for members who already hold the rank when the admin adds marks later? (Grants are once-forever, so by default — no.)
4. Debt when the player leaves / is expelled / the faction is hidden: still paid, frozen, or cancelled? Does the player see debt amounts in numbers (it is their money) while wealth stays words-only?
5. Can quartermaster items be bought by members of a secret faction only after the NPC reveals it — i.e. what do non-members see when they click a secret faction's quartermaster (generic «Интендант» with no shop / hidden role)?
6. Wages: paid only from the treasury to the HQ purse (abstract), or should NPC members also «leave» when the treasury cannot pay (brief: slowly)? Minimum/maximum member count bounds?
7. Battle-pass: should faction reward marks count toward «заработай марки» and donations/quartermaster purchases toward «потрать марки»?
8. Factions without HQ or with an HQ in a non-participating region: no economy at all (no dues/wages/restock), but donations, quartermaster sales and rank rewards still work?

---

## 3. Architecture Decision (filled by Architect — in English)

Stage 1 contract = `features/DONE-FEAT-205-factions-core.md` §3 (referenced below as «205 §3.x»). Everything here
extends it; nothing in it is re-designed.

### 3.0 Open questions for PM

No blocking questions — all user decisions of §1 are covered. Product-visible defaults chosen by the Architect (each is
a setting or a one-line change; PM may confirm them with the user in the final report):

1. **Tick spending priority:** inflows (dues, profile) → **wages** → **player debts (FIFO)** → quartermaster restock.
   Wages first keeps the NPC mass alive; debts are paid before the faction buys goods.
2. **A hidden faction (`is_active = 0`) does not tick** (economy frozen, money stays). Donations, quartermaster sales
   and debt payouts keep working for its existing members (205 §3.0 #6: hidden = only out of the catalog).
3. **Donation points:** 10 marks = 1 point, **daily cap 50 points per faction per character (UTC day)**. Marks above the
   cap are still accepted as a pure donation; the confirm dialog says «очков за сегодня больше не будет».
4. **One assortment per faction**, shared by all its quartermaster NPCs (one stock, one restock).
5. **Wealth words — 4 levels:** «Процветает» (≥75) / «Держится» (40–74) / «В затруднении» (15–39) / «Бедствует» (<15).
6. **Permissions:** new `factions:economy` (economy tab writes, templates, quartermasters, assortment, purchase
   retry/refund) — moderator gets it; «Заполнить по шаблону» additionally needs `economy:emit` (admin only), exactly
   like the region fill.
7. **Secret quartermaster label:** the NPC role label is set by the admin. If a secret faction's quartermaster has role
   `quartermaster`, everybody sees «Интендант» but non-members get «Этот человек с вами не разговаривает»; if the admin
   gives him a neutral role, non-members see no button at all (the probe, §3.8). The admin UI shows this hint.
8. **Non-members of a public faction** may open its quartermaster and see the assortment, all items locked with
   «Только для членов фракции «X»».
9. No admin endpoint to cancel a player debt (debts are the player's money; only paid out). Can be added later.

### 3.1 Overview and ownership

| Concern | Owner | Notes |
|---|---|---|
| Ledger kind `faction_treasury` + `FACTION_OP_TYPES` | shared contract `econ_core.py` (canonical character-service, ×4 byte-identical) + `tests/econ_contract_cases.py` (×4) | inventory / locations / dungeon get the copies only; each service's `tests/test_econ_contract.py` runner gets the new constant checks |
| Faction economy state, templates, debts, donations, quartermaster, tick step | **character-service** (sync, migration `046_faction_economy`) | new `faction_econ.py` (pure maths, no DB), `faction_econ_crud.py` (DB flows: settle, donate, tick step, admin economy), `faction_qm_crud.py` (quartermaster: view/buy/delivery/refund/restock helpers); routes added to `faction_api.py` |
| 6 h tick pass | character-service `econ_tick.py` | new `_faction_econ_pass` after `_mint_pass`, before the banks |
| 5 min pass | character-service `faction_pass.py` | + debt settle sweep, + quartermaster delivery retries (never economic simulation) |
| Permission `factions:economy` | user-service migration `0035` | + explicit seed section in `tests/test_rbac_permissions.py` |
| Item delivery | inventory-service | **no change** — existing `POST /inventory/internal/characters/{cid}/items` |
| Battle pass | battle-pass-service | **no change** — every faction op touching a character counts automatically (§3.11) |
| locations-service | only the byte-identical copies | NPC shops untouched; the quartermaster is NOT an `npc_shop_items` merchant |

No Nginx / Docker / env changes (all paths under `/characters/`).

### 3.2 Ledger contract (econ_core.py ×4, econ_contract_cases.py ×4)

```python
# FEAT-206: a faction's treasury (ref_id = factions.id). Never negative. Not a tax source.
KIND_FACTION_TREASURY = "faction_treasury"
ACCOUNT_KINDS |= {KIND_FACTION_TREASURY};  REF_KINDS |= {KIND_FACTION_TREASURY}
# NOT in NEGATIVE_ALLOWED_KINDS, NOT in TAX_SOURCE_KINDS, NOT in SOURCE_KINDS
AccountRef.faction(faction_id) -> AccountRef(KIND_FACTION_TREASURY, faction_id)
SQL_ACCOUNT_NAME[KIND_FACTION_TREASURY] = "SELECT name FROM factions WHERE id = :ref_id"

OP_FACTION_TICK = "faction_tick"            # 6 h step: purse/region -> faction (dues, profile), faction -> purse
                                            # (wages, quartermaster restock), faction -> characters (debt payouts)
OP_FACTION_DONATION = "faction_donation"    # character -> faction
OP_FACTION_QM_SALE = "faction_qm_sale"      # character -> faction (quartermaster purchase)
OP_FACTION_QM_REFUND = "faction_qm_refund"  # faction -> character (failed delivery compensation)
OP_FACTION_PAYOUT = "faction_payout"        # faction -> characters (debt queue: rank marks, deferred refunds)
FACTION_OP_TYPES = frozenset({...5...});  OP_TYPES |= FACTION_OP_TYPES
# none of them in SOURCE_OP_TYPES / COMMENT_REQUIRED_OP_TYPES
```

Edit the canonical character-service file, copy byte-for-byte to inventory / locations / dungeon; same for
`tests/econ_contract_cases.py`; `sh scripts/check_econ_copies.sh` must print only `ok`. New contract block (pattern of
the caravan block): `FACTION_OP_TYPE_NAMES`, `FACTION_TREASURY_KIND_NAME`, cases: (a) donation `character → faction`
untaxed, idempotent by key; (b) faction treasury never negative (`InsufficientFunds`), ref_id 0 rejected; (c) faction
ops may not touch emission/adjustment (`EconomyError`); (d) `admin_emission emission → faction` with comment is valid;
(e) a `faction_tick` op with purse→faction, faction→purse, faction→character legs nets correctly and the world sum
stays 0. Each service's runner asserts `FACTION_OP_TYPES == set(FACTION_OP_TYPE_NAMES)`, ⊂ `OP_TYPES`, disjoint from
`SOURCE_OP_TYPES`, kind ∈ `REF_KINDS`, ∉ `NEGATIVE_ALLOWED_KINDS` / `TAX_SOURCE_KINDS`. The contract DDL may add a
minimal `factions(id, name)` table (the name lookup is cosmetic and tolerant anyway).

character-service `economy_crud.py`: `EMISSION_TARGET_KINDS += faction_treasury` (admin emission / fill);
`faction_treasury` is NOT in `ADJUST_FORBIDDEN_KINDS` (admin may correct / drain it); `get_summary` gets a
`factions` total (sum of faction treasuries) next to the other per-kind totals (unknown kinds already count in `held`).
Account names: stored snapshot (`a.name`) — `SQL_ACCOUNTS_UNION` unchanged.

### 3.3 Data model — character-service migration `046_faction_economy`

No MySQL ENUMs (VARCHAR validated in code), explicit indexes on FK columns, revision id ≤ 32 chars. FKs to
`characters.id` / `factions.id` are `ON DELETE CASCADE`. `items` / NPC ids validated by raw SELECT (no cross-service
FK except `characters`, as in stage 1).

```sql
ALTER TABLE faction_ranks
  ADD reward_marks INT NOT NULL DEFAULT 0,           -- 0..1_000_000, paid via the debt queue on grant (§3.5)
  ADD qm_discount_pct INT NOT NULL DEFAULT 0;        -- 0..50, quartermaster discount for holders of this rank

ALTER TABLE faction_settings                          -- row id=1
  ADD donation_marks_per_point INT NOT NULL DEFAULT 10,   -- 1..10000
  ADD donation_points_daily_cap INT NOT NULL DEFAULT 50,  -- 0..100000 (0 = donations give no points)
  ADD econ_enabled BOOL NOT NULL DEFAULT 1,               -- global kill-switch of the faction tick step
  ADD econ_purse_share_pct INT NOT NULL DEFAULT 2,        -- 0..20: ALL factions of a region take at most this % of
                                                          --   its population purse per tick (dues + purse profile)
  ADD econ_treasury_share_pct INT NOT NULL DEFAULT 1,     -- 0..20: ... and this % of its POSITIVE region treasury
  ADD members_leave_pct INT NOT NULL DEFAULT 5,           -- 0..50: max loss per tick at 0 % wages paid
  ADD members_grow_pct INT NOT NULL DEFAULT 1,            -- 0..10: max growth per tick at wealth 100
  ADD qm_take_share_pct INT NOT NULL DEFAULT 5;           -- 0..50: a faction restock takes at most this % of a
                                                          --   goods group's HQ region stock per tick

CREATE TABLE faction_econ_templates (
  code VARCHAR(32) PK,                    -- ^[a-z0-9_]{2,32}$
  name VARCHAR(100) NOT NULL, description VARCHAR(500) NULL,
  params JSON NOT NULL,                   -- whitelisted keys, §3.4
  sort_order INT NOT NULL DEFAULT 0, updated_at DATETIME NOT NULL
);
-- seeded: order «Орден», merchants_guild «Гильдия торговцев», dark_guild «Тёмная гильдия», temple «Храм»,
--         academy «Академия» (params §3.4)

CREATE TABLE faction_economy (            -- 1:1 with factions; backfilled for existing factions, ensured on create
  faction_id INT PK FK→factions CASCADE,
  template_code VARCHAR(32) NULL FK→faction_econ_templates(code) ON DELETE RESTRICT (indexed),
  overrides JSON NULL,                    -- subset of the template keys
  econ_enabled BOOL NOT NULL DEFAULT 1,   -- per-faction switch
  members_count INT NOT NULL DEFAULT 0,   -- conditional NPC members
  members_carry DECIMAL(10,4) NOT NULL DEFAULT 0,   -- fractional growth/loss accumulator
  members_min INT NOT NULL DEFAULT 10, members_max INT NOT NULL DEFAULT 5000,   -- 0..100000, min <= max
  payout_seq INT NOT NULL DEFAULT 0,      -- idempotency counter of standalone payouts (faction_payout keys)
  last_run_id BIGINT NULL, last_tick_at DATETIME NULL,
  last_dues BIGINT NOT NULL DEFAULT 0, last_profile BIGINT NOT NULL DEFAULT 0,
  last_wages_due BIGINT NOT NULL DEFAULT 0, last_wages_paid BIGINT NOT NULL DEFAULT 0,
  last_restock BIGINT NOT NULL DEFAULT 0, last_debts_paid BIGINT NOT NULL DEFAULT 0,
  last_members_delta INT NOT NULL DEFAULT 0, last_wealth INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL
);

CREATE TABLE faction_econ_history (       -- one row per (run, faction)
  id BIGINT PK, run_id BIGINT NOT NULL, faction_id INT NOT NULL FK CASCADE,
  balance_before BIGINT, balance_after BIGINT, dues BIGINT, profile BIGINT, wages_due BIGINT, wages_paid BIGINT,
  restock_spent BIGINT, restock_items INT, debts_paid BIGINT, members_before INT, members_after INT, wealth INT,
  created_at DATETIME NOT NULL,
  UNIQUE (run_id, faction_id), INDEX (faction_id, id)
);

CREATE TABLE faction_debts (              -- the payout queue (rank marks, deferred refunds); survives leave/expel/hide
  id BIGINT PK,
  character_id INT NOT NULL FK→characters CASCADE, faction_id INT NOT NULL FK→factions CASCADE,
  source VARCHAR(10) NOT NULL,            -- rank | refund
  source_key VARCHAR(64) NOT NULL UNIQUE, -- "rank:g<grant_id>" | "refund:p<purchase_id>"
  amount BIGINT NOT NULL,                 -- > 0
  paid BIGINT NOT NULL DEFAULT 0,         -- 0..amount
  status VARCHAR(8) NOT NULL,             -- open | paid
  unpaid_notified BOOL NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL, paid_at DATETIME NULL,
  INDEX (faction_id, status, id), INDEX (character_id, status)
);

CREATE TABLE faction_donation_days (      -- daily points cap counter (pattern econ_guild_xp_days)
  character_id INT NOT NULL FK CASCADE, faction_id INT NOT NULL FK CASCADE (indexed), day DATE NOT NULL,
  marks BIGINT NOT NULL DEFAULT 0, points INT NOT NULL DEFAULT 0,
  PRIMARY KEY (character_id, faction_id, day)
);

CREATE TABLE faction_quartermasters (     -- NPC ↔ faction binding
  npc_id INT PK FK→characters CASCADE,    -- is_npc = 1 validated
  faction_id INT NOT NULL FK CASCADE (indexed), created_at DATETIME NOT NULL
);

CREATE TABLE faction_qm_items (           -- the faction's assortment (shared by its quartermasters)
  id INT PK, faction_id INT NOT NULL FK CASCADE,
  item_id INT NOT NULL,                   -- items.id (validated)
  price INT NOT NULL,                     -- 1..10_000_000, before rank discount
  min_rank_id INT NULL FK→faction_ranks ON DELETE RESTRICT (indexed),  -- must belong to the faction
  stock INT NOT NULL DEFAULT 0,           -- 0..100000
  restock_target INT NOT NULL DEFAULT 0,  -- 0..100000; tick restocks on-market items toward it (0 = never)
  is_active BOOL NOT NULL DEFAULT 1, sort_order INT NOT NULL DEFAULT 0, updated_at DATETIME NOT NULL,
  UNIQUE (faction_id, item_id), INDEX (faction_id, sort_order)
);

CREATE TABLE faction_qm_purchases (       -- purchase journal + item delivery outbox (one row per purchase)
  id BIGINT PK,
  character_id INT NOT NULL FK CASCADE (indexed), faction_id INT NOT NULL FK CASCADE (indexed),
  qm_item_id INT NULL FK→faction_qm_items ON DELETE SET NULL, npc_id INT NULL,
  item_id INT NOT NULL, quantity INT NOT NULL, price_total BIGINT NOT NULL,
  op_key VARCHAR(128) NOT NULL UNIQUE,    -- ledger key of the sale (= idempotency)
  status VARCHAR(10) NOT NULL,            -- pending | sending | done | failed | refunded
  attempts INT NOT NULL DEFAULT 0, next_attempt_at DATETIME NOT NULL,
  last_error VARCHAR(255) NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
  INDEX (status, next_attempt_at)
);
```

Backfill: one `faction_economy` row per existing faction (template NULL, members 0). Rollback: `downgrade()` drops the
7 tables in reverse FK order and the added columns. Faction treasury account rows / journal stay (harmless, the ledger
is append-only). Pre-beta data loss on rollback is acceptable.

Rank delete (205 §3.10) gets one more 409: «Звание используется в ассортименте интенданта» (RESTRICT FK).
Faction delete (205 §3.10) gets two more 409s: treasury balance ≠ 0 («В казне фракции остались марки — сначала
обнулите казну») and any `faction_debts` row; on delete the treasury account is `deactivate_account`-ed.

### 3.4 Pure rules — `faction_econ.py` (no DB)

**Params** (`FactionEconParams`, whitelisted keys, bounds; effective = code defaults ← template.params ← overrides;
unknown keys → 422; Pydantic validates on write, `from_mapping` tolerates/ignores broken stored JSON with a warning):

| key | bounds | meaning |
|---|---|---|
| `start_members` | 0..100000 int | members set by «Заполнить по шаблону» |
| `norm_per_member` | 1..100000 int | wealth norm = max(1, members × this) |
| `start_treasury_per_member` | 0..100000 int | fill target = members × this |
| `dues_per_member` | 0..1000 decimal | marks per member per tick, purse → treasury |
| `wage_per_member` | 0..1000 decimal | marks per member per tick, treasury → purse |
| `profile_kind` | `none` \| `members_purse` \| `income_share` \| `treasury_share` | profile income source |
| `profile_per_member` | 0..1000 decimal | `members_purse`: marks per member from the purse |
| `profile_rate` | 0..0.2 decimal | `income_share`: × `econ_regions.last_income` from the purse; `treasury_share`: × positive region treasury |
| `qm_budget_share` | 0..1 decimal | restock budget = floor(max(0, balance − 0.5 × norm) × this) |

**Seeded templates** (all floors of products; numbers are a starting balance, tuned later by the admin):

| code | name | start_members | norm/member | start/member | dues | wage | profile | qm_budget_share |
|---|---|---|---|---|---|---|---|---|
| `order` | Орден | 300 | 30 | 30 | 1.0 | 1.0 | `treasury_share` 0.005 (плата края за охрану) | 0.10 |
| `merchants_guild` | Гильдия торговцев | 200 | 40 | 40 | 1.5 | 1.0 | `income_share` 0.01 (оборот рынка) | 0.15 |
| `dark_guild` | Тёмная гильдия | 100 | 40 | 40 | 0.5 | 1.0 | `members_purse` 1.0 («заказы») | 0.10 |
| `temple` | Храм | 150 | 30 | 30 | 0.5 | 0.75 | `members_purse` 0.75 (пожертвования) | 0.05 |
| `academy` | Академия | 120 | 40 | 40 | 1.0 | 1.0 | `members_purse` 0.5 (плата за обучение) | 0.10 |

At baseline each template's inflow ≥ wages, so a faction with an uncapped purse slowly fills toward its norm; when the
regional cap binds (small region / many factions), wages exceed inflow, the treasury drains, members leave → a natural
equilibrium. Net purse drain per tick = dues + purse profile − wages − restock, bounded by `econ_purse_share_pct`
(default 2 %) for all factions of the region together — well below the other purse consumers (merchants 5 %,
caravans 25 %, guild 25 %) and mostly circular (wages and restock go back to the same purse).

**Wealth:** `wealth(balance, norm) = clamp(0, 100, round(50 × balance / norm))` (balance = norm → 50; ≥ 2 × norm →
100). `wealth_state`: `thriving` ≥75 / `stable` 40–74 / `struggling` 15–39 / `destitute` <15, labels
`WEALTH_LABELS = {thriving: «Процветает», stable: «Держится», struggling: «В затруднении», destitute: «Бедствует»}`
(pattern `econ_sim.TREASURY_LABELS` / `treasury_state`). No template → no wealth (null).

**Tick step plan** `plan_faction_step(state, params, settings, budgets, purse, region_treasury, last_income, balance,
open_debts, restock_rows) -> FactionStepPlan` (deterministic, inputs never mutated):
1. `dues_want = floor(members × dues_per_member)`; `profile_want` by kind (`members_purse`: floor(members ×
   profile_per_member); `income_share`: floor(last_income × rate); `treasury_share`: floor(max(0, region_treasury) ×
   rate)). Purse part (dues + purse profile) capped by `budgets.purse` (this faction's share of the regional cap,
   §3.6) and by the purse balance; treasury profile capped by `budgets.treasury` and by `max(0, region_treasury)`.
   When capped, dues and profile are scaled together proportionally.
2. `available = balance + dues + profile`.
3. `wages_due = floor(members × wage_per_member)`; `wages_paid = min(wages_due, available)`; `available −= wages_paid`.
4. Debts FIFO (ascending id): pay `min(remaining, available)` each, partial allowed, until `available = 0`.
5. Restock (only `restock_rows` = active, on-market, `restock_target > stock`, group present in the HQ region):
   `budget = min(available, floor(max(0, available − 0.5 × norm) × qm_budget_share))`; per row (ascending id):
   `price = econ_core.wholesale_price(items.price, good.price_mult, sim.merchant_wholesale_share)`,
   `units = econ_core.units_per_item(items.price, group.base_price)` (row skipped when 0),
   take cap per group = `floor_units(qm_take_share_pct % × group stock at step start)` shared by the faction's rows of
   that group; `n = min(target − stock, budget // price, cap_units // units)`; spend `n × price`, stock −`n × units`.
6. Members: `ratio = wages_paid / wages_due` (1 when wages_due = 0). If `ratio < 1`: `delta = −members × leave_pct %
   × (1 − ratio)`; else if `wealth_after ≥ 50`: `delta = +members × grow_pct % × (wealth_after − 50) / 50`; else 0.
   `carry += delta`; integer part applied; `members = clamp(members_min, members_max, members + int)`; the clamped
   remainder discarded (`carry` keeps only the fraction, sign preserved). `wealth_after` = wealth of the final balance
   against the norm of the members **before** the change.
7. Result: legs (all `LEG_MAIN`): `purse(hq) → faction` (dues + purse profile), `region(hq) → faction` (treasury
   profile), `faction → purse(hq)` (wages), `faction → purse(hq)` (restock — merchants' rule: the region's goods are
   paid to the residents' purse), `faction → character` per debt payment; region stock deltas; row stock deltas;
   debt row updates; new members / carry / wealth; numbers for the history row and `last_*` columns.

**Donation points:** `donation_points(marks_today_before, marks, per_point, cap, points_today_before)` →
`new_total = min(cap, (marks_today_before + marks) // per_point)`; `gain = max(0, new_total − points_today_before)`.
Fractions carry within the UTC day; marks above the cap give nothing.

**Quartermaster price:** `final_unit = max(1, floor(price × (100 − discount_pct) / 100))`, `total = final_unit × qty`.
Rank gate: member's rank `sort_order` ≥ `min_rank.sort_order` (no min rank → any member).

### 3.5 Rank reward marks and the debt queue (`faction_econ_crud.settle_debts`)

- `faction_crud.grant_rank` (205 §3.6, same transaction): if `rank.reward_marks > 0` → INSERT `faction_debts(source
  'rank', source_key 'rank:g<grant_id>', amount, status open)`. **Every** marks reward goes through the queue — no
  ledger op inside the many rank-up callers (join, approve, quest-completed, level-up hook, admin points, donation),
  FIFO fairness is automatic. `reward_parts` adds «+N марок». No retroactive pay: only new grants create rows.
- `faction_rewards.deliver_pending(character_id)` (already called post-commit after every rank-up) additionally calls
  `settle_debts` for the factions of that character's open debts (best effort, own transactions).
- `settle_debts(db, faction_id, now)` — **own transaction**: `faction_economy(fid)` FOR UPDATE → open debts of the
  faction ascending id FOR UPDATE → plan with the treasury balance (FIFO, partial) → one `faction_payout` op
  `faction → characters` (key `faction_payout:f<fid>:s<payout_seq+1>`, `payout_seq` incremented in the same tx,
  `apply_tax=False`) → rows updated (`paid`, `status`, `paid_at`) → commit. Nothing to pay → no op, no seq bump.
- Called: post-commit after a rank-up (above), after a donation, after a quartermaster sale, after a faction fill /
  admin emission into a faction account (economy_crud emit hook: if kind = faction → settle post-commit), by the 5-min
  pass (factions with open debts and a positive treasury — covers admin adjustments) and inside the tick step (§3.6).
- Notices (owner only, `faction_notify`, category progress): a debt still not fully paid after its first settle and
  `unpaid_notified = 0` → «Казна фракции «X» сейчас пуста: N марок за звание записаны в долг. Выплатим, когда казна
  пополнится» + flag; a previously-notified debt paid in full → «Фракция «X» выплатила долг: N марок». Partial payments
  are silent. Debts of left/expelled members and of hidden factions are paid the same way. Character deletion →
  CASCADE (money stays in the treasury).

### 3.6 Tick step — `econ_tick._faction_econ_pass` (in the 6 h tick)

Position in `run_tick`: after `_mint_pass`, before `_prepare_banks` (regions already ticked: fresh prices, purse after
tax/wages, `last_income`). Runs in scheduled and manual runs; never under pytest automatically (tests call
`run_tick(...)` / the pass directly).

1. **Plan (no locks, own session):** ticking factions = `faction_settings.econ_enabled = 1` AND `factions.is_active = 1`
   AND `faction_economy.econ_enabled = 1` AND `template_code IS NOT NULL` AND HQ set AND HQ location resolves
   (`econ_ledger.resolve_location`) to a **participating** region (`SQL_PARTICIPATING` rule). Group by HQ region; per
   region read purse / treasury balances; regional caps `purse_cap = floor(purse × econ_purse_share_pct %)`,
   `treasury_cap = floor(max(0, treasury) × econ_treasury_share_pct %)`; split each cap between the region's factions
   proportionally to their wants (floor, deterministic by faction id) → `budgets[fid]`. A resumed run recomputes the
   plan from the current balances (done factions are skipped, so the caps can only shrink).
2. **Per faction, ascending id — one transaction** (`_faction_step`): `econ_regions(hq)` FOR UPDATE → goods rows of the
   groups needed for restock FOR UPDATE (ascending group code) → `faction_economy(fid)` FOR UPDATE; **skip if
   `last_run_id == run_id`** → `faction_qm_items` restock rows ascending id FOR UPDATE → open `faction_debts` ascending
   id FOR UPDATE → read balances (purse / treasury / faction) → `faction_econ.plan_faction_step` → one `faction_tick`
   op (all legs of §3.4 #7, `apply_tax=False`, `region_id = hq region`, metadata {run_id, dues, profile, wages_due,
   wages_paid, restock: {qm_item_id: n}, debts: {debt_id: amount}}, key `faction_tick:<run_id>:f<fid>`) → stock rows,
   region goods stock, debt rows, `faction_economy` (members, carry, `last_*`, `last_run_id`, `last_tick_at`) →
   `faction_econ_history` row → COMMIT. `DuplicateOperation` → rollback, skip (another runner did it). Any other error
   → rollback, counted in `RunSummary.factions_failed` / `faction_failed_ids`, logged, retried next tick. Nothing to post
   (all legs 0) → still updates members / history / `last_run_id`.
3. Post-commit per faction: notices from the debt rules of §3.5 (published after commit, failures only logged).
4. `RunSummary` gets `factions_done`, `factions_failed`, `faction_failed_ids`, `faction_ops_posted`; run error text gets
   `FACTION_ERROR_PREFIX = "фракции — ошибка: "` + ids. `purge_old` deletes `faction_econ_history` older than
   `history_retention_days`.
5. Factions without HQ / with a non-simulated HQ / hidden / disabled / without template: **no step** (members and
   treasury frozen); donations, quartermaster sales, debt settles and rank marks still work.

**Global lock order** (supersedes the FEAT-193 one; documented in the `econ_tick.py` docstring and the
character-service doc): `econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) →
econ_region_events → econ_caravans → econ_guild_orders → econ_guild_xp_days → econ_mint_seasons → npc_shop_items →
econ_banks → bank_deposits → bank_loans → faction_members (asc id) → faction_economy (asc faction_id) →
faction_qm_items (asc id) → faction_debts (asc id) → faction_donation_days → faction_qm_purchases →
character_inventory → characters (asc id) → econ_accounts (asc id) → character_attributes`. Every faction economy flow
posts **one** ledger op per transaction (characters + accounts locked by `post_operation` in its fixed order), which is
why tick debt payouts are legs of the `faction_tick` op and not a second op.

### 3.7 Donations (`faction_econ_crud.donate`)

`POST /characters/{cid}/factions/{fid}/donate` `{amount: conint(strict, 1..1_000_000), request_id: ^[A-Za-z0-9-]{8,64}$}`.
Owner (`_require_owner`), not NPC (403), **active member** (404 «Вы не состоите в этой фракции»). From anywhere; no
activity-lock check (not a location action). Key `faction_donation:c<cid>:<request_id>`; pre-check
`operation_exists` → 409 «Это пожертвование уже выполнено» (bank pattern). One transaction:
`faction_members(cid, fid)` FOR UPDATE → `faction_donation_days(cid, fid, UTC day)` (row ensured in its own short
transaction first, pattern `ensure_xp_day_row`) FOR UPDATE → `faction_donation` op `character → faction`
(`InsufficientFunds` → 400 «Недостаточно марок») → day row += marks / points → if gain > 0: `change_points` with
`event_key faction:donate:<op_key>` + **hostile penalty** exactly as `quest_completed` (205 §3.4, key
`faction:donate:<op_key>:hostile:<A>`) → log event `donation` (new `EV_DONATION`, history text «Пожертвование N марок:
+P очков» / «Пожертвование N марок» when gain 0) → `recheck_ranks` → commit. Post-commit: notices, `deliver_pending`
(rank rewards), `settle_debts(fid)` if the faction has open debts.
Response `{points_delta, points_after, points_today, daily_cap, marks_today, rank_ups, new_balance}`.

### 3.8 Quartermaster (`faction_qm_crud.py`)

Binding = `faction_quartermasters` (source of truth); `characters.npc_role = 'quartermaster'` is only the visible label
(new frontend role «Интендант»). Assortment per faction (§3.0 #4). Not an `npc_shop_items` merchant: the region tick,
«Пополнить кассы» and the public shop never see it.

**Gate** (view + buy): owner & player; NPC exists, is_npc, bound, not dead (409 «Интендант мёртв»); same location as
the NPC (400 «Вы не рядом с интендантом»); buy only: activity lock (409); FEAT-145 dialogue gate via
`locations_client.check_npc_gate` awaited by the router before the transaction (guild pattern); then:
secret faction + not an active member → **403 «Этот человек с вами не разговаривает»** (no faction, no items, the
check is done before anything faction-specific is returned).

**Probe** `GET /characters/factions/quartermaster/npc/{npc_id}/probe?character_id=` → `{state: "none"|"silent"|"open"}`:
not bound → `none`; bound + (public faction, or active member of the secret one) → `open`; secret + non-member →
`silent` if `npc_role == 'quartermaster'`, else `none`. Ownership checked; no location check (cheap, read-only).

**View** `GET /characters/factions/quartermaster/npc/{npc_id}?character_id=` → `{npc: {id, name}, faction: {id, name,
emblem_url}, member: bool, rank: {id, name, discount_pct}|null, balance, items: [{qm_item_id, item: {id, name, image,
item_type, item_rarity}, price, final_price, stock, min_rank: {id, name}|null, locked_reason: str|null}]}` — active
rows with stock ≥ 0 (stock 0 shown as «Нет в наличии»), ordered by sort_order. `locked_reason`: non-member «Только для
членов фракции «X»», low rank «Нужно звание «Y»».

**Buy** `POST /characters/factions/quartermaster/npc/{npc_id}/buy` `{character_id, qm_item_id, quantity:
conint(strict, 1..99), request_id}`. Key `faction_qm:c<cid>:<request_id>` (pre-check → 409 «Покупка уже выполнена»).
Re-check membership + rank in the transaction; one transaction: `faction_qm_items(id)` FOR UPDATE (must belong to the
NPC's faction, active) → conditional `UPDATE ... SET stock = stock − :q WHERE id = :id AND stock >= :q` (0 rows → 409
«Недостаточно товара у интенданта») → `faction_qm_sale` op `character → faction` (400 «Недостаточно марок») → INSERT
`faction_qm_purchases` (status pending, op_key) → commit. Post-commit: deliver (below), `settle_debts(fid)` if needed.
Response `{purchase_id, delivered: bool, price_total, new_balance, message}` (`delivered=false` → «Предмет будет
доставлен в инвентарь в ближайшее время»).

**Delivery** (shared helper extracted from `faction_rewards` item delivery, 205 §3.6 semantics): claim
`pending → sending` (attempts+1) and commit before the HTTP call `POST /inventory/internal/characters/{cid}/items`
(timeout 5 s). 2xx → `done`. Definite failure (refused / 4xx / 5xx) → `pending` with backoff `2^attempts` min; after 5
attempts → **auto-refund**. Timeout / read error → `failed`, `last_error='uncertain'`, never auto-retried; admin
«Повторить» (→ pending) or «Вернуть деньги». Stale `sending` > 10 min → `failed` uncertain. Retries by the 5-min pass.
**Refund** (one transaction): purchase row FOR UPDATE (status pending|failed) → stock back (`stock + qty` on the qm row
if it still exists) → `faction_qm_refund` op `faction → character` key `faction_qm_refund:p<id>`; on
`InsufficientFunds` the refund becomes a debt (`source 'refund'`, key `refund:p<id>`, no op) → status `refunded` →
notice «Интендант не смог выдать «Item» — марки возвращены» / «…— марки вернут из казны фракции позже».

**Restock** = tick step §3.4 #5 (on-market rows only). Off-market items (`effective_item_group` off_market: scrolls,
recipes, legendary+, admin flag) — admin sets `stock` directly; validation rejects `restock_target > 0` for them (422
«Этот предмет не продаётся на рынке — запас пополняет только администратор»).

### 3.9 Secrecy (extends 205 §3.9)

- Wealth words: catalog item `wealth` = null for secret factions unless the requesting character is an active member;
  private tab shows wealth only for **active** memberships. Public `/factions/{id}/public` — wealth for non-secret only.
  Numbers (balance, norm, wealth 0–100, members_count) are admin-only.
- Quartermaster: §3.8 probe / 403 text; the view never returns faction data before the membership check passes.
- Debt amount is returned only in the private view (owner / staff); debts of secret factions appear only there.
- Journal: new `donation` event lives in the private `faction_log`; ledger ops are admin-only (no player ledger view
  exists). Notifications go only to the owner.

### 3.10 API contracts

Errors `{"detail": "<Russian>"}`; player endpoints JWT + ownership (403 «Это не ваш персонаж»); admin endpoints
`require_permission`. **Route order:** static admin paths (`/admin/factions/econ-templates…`, `/admin/factions/qm-…`,
`/admin/factions/debts…`) must be registered **before** `/admin/factions/{faction_id}`; quartermaster player paths
before `/{character_id}/factions`.

#### Player (character-service)

| Method & path | Request | Response | Errors |
|---|---|---|---|
| `GET /characters/{cid}/factions` (extended) | — | each membership + `wealth: {state, label}\|null` (active only), `debt: int` (open remaining, any status), `donation: {enabled, marks_per_point, daily_cap, points_today, marks_today, resets_in_seconds}\|null` (active only) | as before |
| `GET /characters/factions/catalog` (extended) | — | + `wealth: {state, label}\|null` (§3.9) | as before |
| `GET /characters/factions/{fid}/public` (extended) | — | + `wealth` (non-secret) | as before |
| `POST /characters/{cid}/factions/{fid}/donate` | §3.7 | §3.7 | 400, 403, 404, 409 |
| `GET /characters/factions/quartermaster/npc/{npc_id}/probe?character_id=` | — | `{state}` | 403 not own |
| `GET /characters/factions/quartermaster/npc/{npc_id}?character_id=` | — | §3.8 | 400 location, 403 silent/gate/not own, 404 not a quartermaster, 409 dead |
| `POST /characters/factions/quartermaster/npc/{npc_id}/buy` | §3.8 | §3.8 | 400, 403, 404, 409 |

#### Admin (character-service)

| Method & path | Permission | Contract |
|---|---|---|
| `GET /admin/factions/{fid}/economy` | factions:read | `{template_code, template_name, overrides, params (effective), econ_enabled, members_count, members_min, members_max, treasury: {account_id\|null, balance}, norm, wealth, wealth_label, hq: {location_id, location_name, region_id, region_name, simulated: bool}\|null, ticking: bool, not_ticking_reason\|null, last: {tick_at, dues, profile, wages_due, wages_paid, restock, debts_paid, members_delta}, debts: {open_count, open_total}, quartermasters: [{npc_id, name, npc_role}]}` |
| `PUT /admin/factions/{fid}/economy` | factions:economy | `{template_code\|null, overrides: {key: value}\|null (whitelist + bounds §3.4), econ_enabled, members_count 0..100000, members_min, members_max (min ≤ max, members clamped)}` |
| `POST /admin/factions/{fid}/economy/fill` | factions:economy **and** economy:emit (`require_all_permissions`) | `{comment: constr(3..500), set_members: bool}` → members := `start_members` when `set_members` or members = 0; treasury top-up `max(0, members × start_treasury_per_member − balance)` as one `admin_emission emission → faction` (comment, key `faction_fill:f<fid>:p<last posting id of the account or 0>` → a re-click emits 0); 409 «Сначала выберите шаблон». Post-commit settle. Returns `{members_count, emitted, balance}` |
| `GET /admin/factions/{fid}/economy/history?page&page_size≤50` | factions:read | `faction_econ_history` rows, newest first |
| `GET /admin/factions/{fid}/economy/operations?page&page_size≤50` | factions:read | `economy_crud.list_operations(account_id = faction account)` wrapper (empty page when no account yet) |
| `GET /admin/factions/{fid}/debts?status=open\|paid\|all&page` | factions:read | `[{id, character: {id, name}, source, amount, paid, status, created_at, paid_at}]` |
| `GET /admin/factions/econ-templates` | factions:read | list with params + `used_by` count |
| `POST /admin/factions/econ-templates`, `PUT /admin/factions/econ-templates/{code}`, `DELETE …/{code}` | factions:economy | `{code (create only), name 1..100, description ≤500, params, sort_order}`; delete → 409 «Шаблон используется» when referenced |
| `GET /admin/factions/{fid}/quartermasters`, `PUT /admin/factions/{fid}/quartermasters` | read / factions:economy | PUT `{npc_ids: [..] ≤ 10}` replaces the set; each must be an NPC; NPC bound to another faction → 409 «NPC уже интендант фракции «X»» |
| `GET /admin/factions/{fid}/qm-items` | factions:read | rows + item name/image, `off_market`, group |
| `POST /admin/factions/{fid}/qm-items`, `PUT /admin/factions/qm-items/{id}`, `DELETE /admin/factions/qm-items/{id}` | factions:economy | §3.3 bounds; item exists; min_rank of this faction; off-market + restock_target > 0 → 422; duplicate item → 409 |
| `GET /admin/factions/{fid}/qm-purchases?status=&page` | factions:read | purchases with character, item, status, last_error |
| `POST /admin/factions/qm-purchases/{id}/retry` / `…/refund` | factions:economy | retry: failed → pending + deliver inline; refund: pending\|failed → §3.8 refund; other states → 409 |
| `GET/PUT /admin/factions/settings` (extended) | read / factions:settings | + the 8 new fields with bounds §3.3 |
| `POST/PUT /admin/factions/…/ranks` (extended) | factions:edit | + `reward_marks` 0..1_000_000, `qm_discount_pct` 0..50 |
| `GET /admin/factions/characters/{cid}` (extended) | factions:read | + `debts`, `qm_purchases` |
| `POST /admin/economy/emission` (existing) | economy:emit | `faction_treasury` accepted as a target kind |

#### user-service migration `0035_faction_economy_perm`

Permission `factions:economy` («Экономика фракций»), moderator (role_id 3) gets it, editor none, admin automatic.
Idempotent, pattern 0034; `downgrade` deletes it. `tests/test_rbac_permissions.py`: explicit seed section +
`TestFactionEconomyPermission` (admin has it, moderator has it, editor/user not, migration lists exactly it) — CLAUDE.md
§10.13.

### 3.11 Battle pass

No code change. `battle-pass-service` counts every posting to/from a character account except
`LEDGER_EXCLUDED_OP_TYPES`: `faction_payout` (rank marks) and `faction_tick` debt legs → **earned**;
`faction_donation` and `faction_qm_sale` → **spent** — exactly the user decision. `faction_qm_refund` counts as earned
(same as the existing `npc_shop_buy_refund` precedent; rare). Backend Dev adds one comment line to the
`LEDGER_EXCLUDED_OP_TYPES` comment block documenting this decision (comment only).

### 3.12 Security

- Auth per §3.10; private data via `visibility.require_private_access`; quartermaster ownership + location + dialogue
  gate + membership/rank re-checked inside the buy transaction.
- Money: only ledger ops; non-negative faction account; no source ops except admin emission (comment + permission);
  idempotency keys for every op (client `request_id` for player writes, run/faction keys for the tick, `payout_seq`
  for payouts, purchase id for refunds); world invariant `sum(characters) + sum(accounts) = 0` must hold in every test.
- Validation: strict ints, bounds above, JSON param whitelist, existence checks (items, NPCs, ranks of the same
  faction, templates); parameterised SQL only.
- Rate limiting: application-level (request_id idempotency, daily points cap, stock row lock, one quartermaster
  purchase ≤ 99 items); no new Nginx zone (no amplifying action).
- No secrecy leaks per §3.9; errors Russian, no stack traces.

### 3.13 Frontend

TypeScript + Tailwind + design-system classes, no `React.FC`, 360 px, every API error shown in Russian, countdowns via
`RemainingText`, double-click guard (`pendingRef`) + `newRequestId()` per click for money actions, `fetchProfile`
after money changes (header balance).

- `src/api/factions.ts`: types + functions for every new/extended endpoint (player + admin).
- **Profile tab** `FactionMembershipCard.tsx`: wealth word (active), «Фракция должна вам: N марок» when `debt > 0`
  (also on former memberships), «Пожертвовать» (active) → new `DonateFactionDialog.tsx` (amount input, preview «+P
  очков» from `donation` info incl. daily cap left and «очков за сегодня больше не будет», cap reset countdown,
  confirm step, then refresh tab + profile). History renders the new `donation` event text from the backend.
- **Catalog** `FactionCard.tsx`: wealth word when present.
- **Quartermaster**: `constants/npc.ts` new role `quartermaster` «Интендант» (+icon); `NpcProfileModal.tsx` calls the
  probe for every NPC → button «Интендант» for `open` (opens `LocationPage/QuartermasterModal/QuartermasterModal.tsx`:
  faction header, rank + discount, items grid with final price, stock, lock reasons, quantity + buy with confirm,
  delivery-pending message) and for `silent` (shows «Этот человек с вами не разговаривает» inline, no request).
- **Admin** (`components/Admin/FactionsPage/*`): in `FactionEditor` a new section/tab «Экономика»
  (`FactionEconomyPanel.tsx`: overview numbers, template select + overrides form with hints, members/bounds, toggles,
  «Заполнить по шаблону» with comment — visible only with `factions:economy` + `economy:emit`, debts list, purchases
  list with retry/refund, history table, operations table, quartermasters multi-select with the secrecy hint);
  `QmAssortmentEditor.tsx` (rows: item picker, price, min rank, stock, restock target disabled for off-market items,
  active, order); new admin sub-tab «Шаблоны экономики» (`EconTemplatesTab.tsx`); `FactionSettingsTab.tsx` + the new
  settings; `RankFormModal.tsx` + `reward_marks`, `qm_discount_pct`; admin character `tabs/FactionsTab.tsx` + debts and
  quartermaster purchases. Buttons gated by `hasPermission`.
- **Economy admin labels** `EconomyPage/economyLabels.ts` + `types/economy.ts`: kind `faction_treasury` «Казна
  фракции» (ACCOUNT_KIND_LABELS, EMISSION_KINDS, ADJUST_KINDS, ALL_ACCOUNT_KINDS), op labels: `faction_tick` «Жизнь
  фракции», `faction_donation` «Пожертвование фракции», `faction_qm_sale` «Покупка у интенданта», `faction_qm_refund`
  «Возврат за покупку у интенданта», `faction_payout` «Выплата фракции»; summary shows the `factions` total.

### 3.14 Data flow

```
Rank-up (any flow) ─tx─► grant + deliveries + faction_debts(rank:g<id>) ─commit─► deliver_pending ─► settle_debts(fid)
      settle: tx faction_economy → debts FIFO → faction_payout (faction → chars) → commit → notices
Donate ─tx─► member → day row → faction_donation (char → faction) → points (+hostile) → ranks ─commit─► settle, deliver
QM buy ─gate(HTTP locations)─► tx stock − q → faction_qm_sale → purchase row ─commit─► HTTP inventory (claim first)
      definite fail ×5 → refund (or refund debt); uncertain → admin
6 h tick: … regions … → mint → _faction_econ_pass: plan caps per HQ region →
      per faction tx: econ_regions(hq) → goods → faction_economy → qm rows → debts → faction_tick op
      (purse/region → F dues+profile; F → purse wages, restock; F → chars debts) → history → commit
5 min pass: conditions watch (205) → reward retries (205) → qm delivery retries → settle factions with open debts
```

### 3.15 Cross-service validation

- `econ_core` additions are additive (new kind/op constants, one new `SQL_ACCOUNT_NAME` entry): inventory / locations /
  dungeon never reference them; byte-identical copies + runners keep CI `econ-contract-copies` green.
- `npc_shop_items`, NPC shop flows and the region merchant step are untouched.
- inventory internal endpoint reused unchanged; locations `check_npc_gate` reused unchanged.
- battle-pass reads the ledger generically — no change (§3.11).
- Existing faction responses only gain fields (frontend tolerant); rank/settings bodies gain optional fields with
  defaults (old admin clients keep working).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Every agent: No commits, no pushes, no `git add`, no `git stash`.** The user commits once at the end (push to main =
prod deploy). Backend devs run `python -m py_compile` on every modified file and run their service's tests in the
container; frontend devs run `npx tsc --noEmit` and `npm run build` inside the frontend container (no node on the host).
Each agent writes a Russian `[LOG]` line in §6.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **Ledger contract.** §3.2: `faction_treasury` kind, `AccountRef.faction`, `SQL_ACCOUNT_NAME`, `FACTION_OP_TYPES` in canonical `character-service/app/econ_core.py`, copied byte-for-byte to inventory/locations/dungeon; FEAT-206 block in canonical `tests/econ_contract_cases.py` + copies; runner checks in each service's `tests/test_econ_contract.py`; `economy_crud.EMISSION_TARGET_KINDS` + `get_summary` `factions` total (+ schema field); battle-pass comment line (§3.11). No commits/pushes/git add. | Backend Developer | DONE | `services/{character,inventory,locations,dungeon}-service/app/econ_core.py`, `…/app/tests/econ_contract_cases.py`, `…/app/tests/test_econ_contract.py`, `services/character-service/app/economy_crud.py`, `app/schemas.py`, `services/battle-pass-service/app/crud.py` (comment only) | — | `sh scripts/check_econ_copies.sh` all ok; contract tests pass in all 4 services; py_compile passes |
| 2 | **character-service: schema, pure rules, debt queue, rank marks.** Migration `046_faction_economy` + models (§3.3, templates seeded, backfill); `faction_econ.py` (§3.4: params/whitelist/bounds, templates math, wealth + words, step planner, donation points, qm price); `faction_econ_crud.settle_debts` + notices (§3.5); `grant_rank` debt rows + `reward_parts` marks; `deliver_pending` → settle hook; faction create ensures the economy row; rank/faction delete guards (§3.3); settings model/bounds extended; `faction_pass` settle sweep. No commits/pushes/git add. | Backend Developer | DONE | `services/character-service/app/alembic/versions/046_faction_economy.py`, `app/models.py`, `app/faction_econ.py`, `app/faction_econ_crud.py`, `app/faction_core.py`, `app/faction_crud.py`, `app/faction_admin_crud.py`, `app/faction_rewards.py`, `app/faction_pass.py`, `app/schemas.py` | 1 | Migration up/down clean on MySQL (container); rank-up with marks creates exactly one debt row per grant and pays it post-commit when the treasury has money; partial FIFO payouts; py_compile passes |
| 3 | **character-service: tick step.** `econ_tick._faction_econ_pass` + `_faction_step` (§3.6: ticking filter, regional caps split, one tx per faction, lock order, `faction_tick` op, restock from HQ market paying the purse, members dynamics, history, `last_run_id` resume, `DuplicateOperation` skip, summary/error prefix, purge); docstring lock order updated. No commits/pushes/git add. | Backend Developer | DONE | `services/character-service/app/econ_tick.py`, `app/faction_econ_crud.py`, `app/faction_qm_crud.py` (restock helpers) | 2 | Resumed run never double-posts; failing faction rolled back alone; non-simulated HQ / hidden / no template → no step; purse/treasury caps respected; py_compile passes |
| 4 | **character-service: player API.** Donations (§3.7), private view / catalog / public additions (§3.9, §3.10), quartermaster probe/view/buy + delivery outbox (shared item-delivery helper extracted from `faction_rewards`) + auto-refund / refund debt + 5-min pass retries (§3.8). No commits/pushes/git add. | Backend Developer | DONE | `app/faction_econ_crud.py`, `app/faction_qm_crud.py`, `app/faction_crud.py`, `app/faction_rewards.py`, `app/faction_pass.py`, `app/faction_api.py`, `app/schemas.py` | 2 | Same request_id twice → 409, no double charge; daily cap + hostile penalty correct; secret faction non-member gets the exact 403 text / probe none\|silent; delivery never duplicated on ambiguous errors; py_compile passes |
| 5 | **character-service: admin API.** All admin routes of §3.10 (economy view/update/fill with both permissions, history, operations wrapper, debts, templates CRUD, quartermasters, assortment with off-market rule, purchases retry/refund, settings + rank fields, admin character view); route order before `/{faction_id}`; `docs/services/character-service.md` section «Экономика фракций» (tables, ops, lock order, endpoints). No commits/pushes/git add. | Backend Developer | DONE | `app/faction_api.py`, `app/faction_econ_crud.py`, `app/faction_qm_crud.py`, `app/faction_admin_crud.py`, `app/schemas.py`, `docs/services/character-service.md` | 2 (4 for retry/refund helpers) | 403 without permission; fill needs factions:economy + economy:emit and re-click emits 0; validation 422/409 Russian; py_compile passes |
| 6 | **user-service: permission.** Migration `0035_faction_economy_perm` (`factions:economy`, moderator yes) + explicit seed section and `TestFactionEconomyPermission` in `tests/test_rbac_permissions.py`. No commits/pushes/git add. | Backend Developer | DONE | `services/user-service/alembic/versions/0035_faction_economy_perm.py`, `services/user-service/tests/test_rbac_permissions.py` | — | Migration idempotent; RBAC tests pass in the container |
| 7 | **Frontend: player.** `api/factions.ts` player types/functions; profile tab additions + `DonateFactionDialog`; catalog wealth; `constants/npc.ts` role; `NpcProfileModal` probe + `QuartermasterModal/*` (§3.13). No commits/pushes/git add. | Frontend Developer | DONE | `src/api/factions.ts`, `src/components/ProfilePage/FactionsTab/*`, `src/components/pages/FactionsPage/FactionCard.tsx`, `src/constants/npc.ts`, `src/components/pages/LocationPage/NpcProfileModal.tsx`, `src/components/pages/LocationPage/QuartermasterModal/*` | 4 | tsc + build pass; donate with confirm + preview + errors; quartermaster buy works at 360 px; «Этот человек с вами не разговаривает» shown for silent |
| 8 | **Frontend: admin.** `api/factions.ts` admin functions; `FactionEconomyPanel`, `QmAssortmentEditor`, `EconTemplatesTab`, settings + rank form fields, admin character tab debts/purchases; `economyLabels.ts` + `types/economy.ts` (§3.13). No commits/pushes/git add. | Frontend Developer | DONE | `src/api/factions.ts`, `src/components/Admin/FactionsPage/*`, `src/components/Admin/CharactersPage/tabs/FactionsTab.tsx`, `src/components/Admin/EconomyPage/economyLabels.ts`, `src/types/economy.ts` | 5, 7 (api module) | tsc + build pass; all admin flows work live; permission-gated buttons; mobile usable |
| 9 | **QA: character-service.** Tests (extend `tests/faction_world.py` with econ DDL — reuse econ test world helpers): contract cases; `faction_econ` pure maths (caps, scaling, wages ratio, FIFO partial, restock caps/budget, members carry/bounds, wealth words, donation points); tick step (resume/no double post, DuplicateOperation, failing faction isolated, non-simulated HQ/hidden/no template skipped, restock from region stock paying the purse, lock-order-sensitive paths smoke); debt queue (rank marks once, no retroactive, survives leave/expel/hide, notices once); donations (idempotency 409, insufficient 400, daily cap, hostile penalty, non-member 404); quartermaster (probe states, silent 403 text, location/dead/rank locks, discount, stock race, delivery ok / definite fail → refund / refund-as-debt / uncertain not retried, admin retry/refund); admin (permissions 403, fill double click emits 0, template whitelist 422, off-market restock 422, delete guards); **world invariant after every money flow**; secrecy (catalog/public/private wealth). No commits/pushes/git add. | QA Test | DONE | `services/character-service/app/tests/faction_world.py`, `app/tests/test_faction_econ_*.py` | 1–5 | All new tests pass in the container; full existing suite green |
| 10 | **QA: other services.** Run contract tests in inventory / locations / dungeon (copies + runners), `check_econ_copies.sh`, RBAC tests of task 6; battle-pass suite still green. No commits/pushes/git add. | QA Test | DONE | (tests only if a runner needs a fix) | 1, 6 | All green, results logged in §6 |
| 11 | **Review.** Full review vs §3 (money invariant, idempotency, lock order, secrecy, CLAUDE.md frontend rules), py_compile / tsc / build re-run, pytest in all touched services, live verification in Chrome on localhost (fill a faction, manual tick, donate, rank-up with marks → debt → payout, quartermaster buy, secret faction as non-member, admin tabs, 360 px). No commits/pushes/git add. | Reviewer | TODO | — | 1–10 | PASS with automated + live results in §5 |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-06
**Result:** FAIL (one MEDIUM lock-order issue; everything else passes)

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/character-service/app/faction_econ_crud.py:491-524` (`donate`) | Lock-order violation of the documented global order (§3.6, `econ_tick` docstring, and `post_operation`'s «lock business rows first, post last» contract). `donate` posts the `faction_donation` op (X-locks the character row + the faction treasury account) **before** `recheck_ranks` → `faction_crud.grant_rank` inserts the `faction_debts` row for a rank with `reward_marks`. A concurrent `settle_debts` / tick `faction_step` of the same faction holds next-key (gap) locks on that faction's open debts (`ix_faction_debts_queue`, `FOR UPDATE`) and then waits for the faction treasury account in its own `post_operation` → cycle: donate waits on the debt gap lock, settle waits on the treasury row. InnoDB resolves it by killing one transaction (donation → 500 «write failed», or the settle/tick step rolls back), no money is lost, but it is exactly the deadlock-prone ordering the design forbids. Fix: in `donate` do the day row update, `change_points` (+ hostile), `log_event` and `recheck_ranks` first, and call `econ_ledger.post_operation` **last** (an `InsufficientFunds` still rolls back the whole transaction via `_write`; `new_balance` comes from the posting result as now). Add a test asserting the order (e.g. a donation that triggers a marks rank-up still produces exactly one debt row and the op; optionally a spy on `post_operation` asserting no `faction_debts` insert happens after it). | Backend Developer | FIXED — `donate` now writes day row / points (+ hostile) / log / `recheck_ranks` (debt + grant inserts) first and calls `post_operation` last; the same problem in `faction_qm_crud.buy` (purchase row inserted after the ledger op) fixed the same way (purchase row first; `IntegrityError` on `uq_faction_qm_purchase_key` → 409 «уже выполнено»). Other flows checked: `settle_debts`, `refund`, `faction_step`, `fill_from_template` lock debts/rows before posting (only the append-only `faction_econ_history` insert follows the tick op — no other locker). LOW note fixed too: `post_donate` runs `_require_owner` in the threadpool. Tests: `TestDonations::test_lock_order_debt_insert_before_ledger_op`, `…test_insufficient_funds_after_rank_up_rolls_back_debt_and_points`, `TestBuy::test_lock_order_purchase_row_before_ledger_op`, `…test_insufficient_funds_leaves_no_purchase_row`, `…test_same_request_id_twice_is_409_once` (SQL/commit event spy + `post_operation` spy). |

#### Non-blocking notes (no action required for PASS)
- `faction_api.post_donate` (async) calls the sync `_require_owner` on the event loop — one short query, same as other async routes in the module; LOW.
- Host `node_modules` lacks `react-icons` (declared in `package.json`, used by pre-existing `Arena3D/EffectRunes.tsx`), so host `tsc`/`vite build` fail; inside the `frontend` container both pass. Not FEAT-206.
- Admin «Последний пересчёт: 06.11.2026, 02:45» is a past timestamp (allowed; countdowns are only for future deadlines — donation reset uses `RemainingText`).

#### Checklist
- [x] World money invariant — only `admin_emission` (fill, comment + `factions:economy`+`economy:emit`) touches the sources; every faction op is untaxed, never a source op; invariant tests after every flow; live: manual tick #101 → world sum 0 before and after, `get_summary.invariant.ok = true`.
- [x] Ledger idempotency keys — `faction_tick:<run>:f<fid>`, `faction_payout:f<fid>:s<seq>` (seq bumped in the same tx under `faction_economy` FOR UPDATE), `faction_qm_refund:p<id>`, `faction_fill:f<fid>:p<last posting>` (+ locking read for concurrent clicks).
- [x] request_id idempotency — donation `faction_donation:c<cid>:<rid>`, purchase `faction_qm:c<cid>:<rid>`, pre-check 409 + `DuplicateOperation` → 409; frontend keeps the key for retries, `pendingRef` guard.
- [x] Tick resumability / isolation — `last_run_id` skip, `DuplicateOperation` skip, one tx per faction, failure counted with `FACTION_ERROR_PREFIX`, pass wrapped so the run continues.
- [ ] Documented lock order — tick, settle, refund, buy follow it; **donate does not** (issue #1).
- [x] No HTTP inside DB transactions — quartermaster delivery claims and commits before the inventory call; dialogue gate awaited before the buy transaction; settle/deliver post-commit.
- [x] Regional caps protect the purse — `econ_purse_share_pct` / `econ_treasury_share_pct` split across factions of the HQ region, plus purse/treasury balance caps in the planner; restock capped by `qm_take_share_pct` of the group stock.
- [x] Debt queue — FIFO by id, partial payments, survives leave/expel/hide (no status filter on membership/faction), paid by tick (after wages), post-commit settles and the 5-min sweep; live: debt 10698 → 10393 → 10191 (tick paid 202).
- [x] Secrecy — catalog/public wealth null for secret non-members (live: catalog `[2, secret, null]`), private wealth only for active memberships, quartermaster probe none/silent/open, secrecy check before dead/location/lock checks, neutral-role secret QM answers like a plain NPC (404); ledger journal admin-only.
- [x] RBAC — `factions:economy` (0035, moderator yes, editor no), fill requires `factions:economy` AND `economy:emit`; explicit seed section + `TestFactionEconomyPermission`.
- [x] Input validation — strict ints/bounds in schemas and CRUD, JSON params whitelist, template code regex, item/rank/NPC existence, off-market restock 422, parameterised SQL only.
- [x] Migrations — 046: no ENUM, explicit FK indexes, information_schema guards (idempotent), revision id 19 chars, downgrade reverse order; 0035 idempotent SELECT-then-INSERT; local DB at `046_faction_economy`.
- [x] `sh scripts/check_econ_copies.sh` — all ok.
- [x] Pydantic v1 syntax.
- [x] Frontend — TS only, Tailwind + design-system classes (`btn-blue`, `btn-line`, `input-underline`, `gold-text`, `rounded-card`), no `React.FC`, no new CSS/SCSS, responsive `sm:` variants, all API errors shown in Russian (toast + inline), `RemainingText` for the donation reset.
- [x] Docs — `docs/services/character-service.md` «Фракции — этап 2, экономика фракций (FEAT-206)», lock order in the `econ_tick` docstring.

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (frontend container, 0 errors)
- [x] `npm run build` (`vite build`) — PASS (frontend container)
- [x] `py_compile` — PASS (all modified/new Python files)
- [x] `pytest` — PASS: character-service full suite 9600 passed, 1 skipped; inventory contract 452; locations contract 439 (`--asyncio-mode=auto -p no:cacheprovider`); dungeon contract green (exit 0, `--asyncio-mode=auto`); user-service 788 passed, 5 skipped; battle-pass-service 172 passed
- [x] `sh scripts/check_econ_copies.sh` — PASS
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, localhost) — PASS

#### Live Verification Results
- Pages tested: `/profile` → «Фракции», `/location/197` → НПС «Петя» → «Интендант», `/admin/factions` → faction 1 → «Экономика», «Шаблоны экономики»; API: `POST /characters/admin/economy/sim/run`, `/characters/admin/economy/summary`, catalog, probe/view.
- Profile tab: wealth «Бедствует» on the public faction, none on the secret one; «Фракция должна вам: 10 528 марок»; donation 50 → «+5 очков», journal entry, hostile-penalty line, debt reduced by 50 (post-commit settle).
- Quartermaster: probe `open` for NPC 33, `none` for an unbound NPC; modal shows rank «Магистр» −15 %, 100 → 85; bought 1 → «Покупка выполнена — предмет в инвентаре», stock 8 → 7, purchase «Выдано», 85 immediately paid out to the debt.
- Admin: overview/settings/fill/quartermasters/assortment/debts/purchases/history/operations all load (all requests 200); templates tab lists the 5 seeded templates.
- Manual tick: run #101 `done`, faction step dues 300 + profile 202, wages 300, debts paid 202; world sum 0 before and after; summary invariant ok.
- Console errors: NONE; network: no 4xx/5xx.

### Review #2 — 2026-11-06
**Result:** PASS

Issue #1 of Review #1 verified FIXED in code:
- `faction_econ_crud.donate`: day row, points (+ hostile penalty), log and `recheck_ranks` (grant + `faction_debts` insert) now run before `econ_ledger.post_operation`, which is the last statement; `InsufficientFunds` / `DuplicateOperation` → `FactionError` → `_write` rolls the whole transaction back.
- `faction_qm_crud.buy`: the `faction_qm_purchases` row is flushed before the `faction_qm_sale` op; `IntegrityError` on the request key → 409 «Покупка уже выполнена» (`IntegrityError` is imported).
- `faction_api.post_donate`: `_require_owner` now runs in the threadpool.
- New order tests are present in `test_faction_econ_flows.py` / `test_faction_econ_qm.py`.

#### Automated Check Results
- [x] `py_compile` — PASS (`faction_econ_crud.py`, `faction_qm_crud.py`, `faction_api.py`, both test files)
- [x] `pytest` character-service full suite in the container — PASS, 9605 passed, 1 skipped
- [x] Other checks unchanged since Review #1 (no changes outside character-service)

#### Live Verification Results
- Donation of 30 to faction 1 by Ашари (763) → 200, +3 points; the same `request_id` again → 409 «Это пожертвование уже выполнено».
- Quartermaster buy (NPC 33, qm_item 1, qty 1) → 200, delivered, 85; the same `request_id` again → 409 «Покупка уже выполнена»; stock 7 → 6.
- Post-commit debt settle paid out the 115 that came in (debt paid 9809 → 9924, balance back to 28 262, treasury 0).
- World sum: 0 before and 0 after; console errors NONE.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-06 — PM: фича создана (этап 2 фракций — экономика), этап 1 FEAT-205 в рабочей копии не запушен; запускаю анализ
[LOG] 2026-11-06 — Analyst: анализ завершён — основная работа в character-service (новый тип счёта в общей книге = правка econ_core ×4 копии + контрактные кейсы, шаг фракций в 6-часовом тике после регионов, миграция 046), копии контракта в inventory/locations/dungeon, права в user-service 0035, фронтенд; интенданта не делать через npc_shop_items (тик сочтёт его живым торговцем); 8 продуктовых вопросов для PM; в DONE-FEAT-205 нет раздела §3 архитектуры
[LOG] 2026-11-06 — Architect: спроектировано 11 задач (5 бэкенд, 2 фронтенд, 2 QA, ревью): счёт казны фракции в общей книге (копии контракта ×4), шаг фракций в 6-часовом тике после чеканки (одна транзакция на фракцию, доли кошелька края ограничены 2 %), очередь долгов для марок за звания, пожертвования с дневным лимитом, интендант с отдельным ассортиментом и выдачей через outbox, админка экономики; миграции character 046 и user 0035 (factions:economy); 9 решений по умолчанию вынесены PM на подтверждение
[LOG] 2026-11-06 — Backend Dev: задача #6 готова — миграция user-service 0035 (право factions:economy, модератору выдано, редактору нет), явный сид и TestFactionEconomyPermission в test_rbac_permissions.py; тесты user-service 788 passed, после рестарта alembic_version_user = 0035, строка в permissions есть (id 114, роль 3)
[LOG] 2026-11-06 — Backend Dev: задача #1 — тип счёта faction_treasury и 5 операций фракций в econ_core (4 побайтовые копии), контрактные кейсы ×4 + проверки в 4 раннерах, эмиссия в казну фракции, итог factions в сводке, комментарий в battle-pass; check_econ_copies — ok, контрактные тесты 4 сервисов зелёные
[LOG] 2026-11-06 — Backend Dev: задача #2 — миграция 046_faction_economy (7 таблиц, колонки званий/настроек, 5 шаблонов, бэкфилл), faction_econ.py (чистая математика), очередь долгов (марки за звания → долг → выплата FIFO после коммита и в 5-минутном проходе), защита удаления звания/фракции
[LOG] 2026-11-06 — Backend Dev: задача #3 — шаг фракций в 6-часовом тике (после чеканки, одна транзакция на фракцию, доли кошелька/казны края, закупки интенданта с рынка края, участники, история, защита от повторного прогона)
[LOG] 2026-11-06 — Backend Dev: задача #4 — пожертвования (лимит очков в день, штраф враждебным, идемпотентность), богатство словами в каталоге/вкладке, долг во вкладке, интендант (probe/просмотр/покупка, выдача через outbox, авто-возврат или долг)
[LOG] 2026-11-06 — Backend Dev: задача #5 — админ-API экономики (обзор/правка/«Заполнить по шаблону» с двумя правами, история, операции, долги, шаблоны, интенданты, ассортимент, покупки повтор/возврат), раздел в docs/services/character-service.md; миграция 046 применилась на локальной БД, ручной прогон тика с фракцией — ok, сумма мира 0
[LOG] 2026-11-06 — Frontend Dev: задача #7 — игрок: богатство словами во вкладке и каталоге, долг фракции числом (и у бывших фракций), «Пожертвовать» с подтверждением (сумма, очки за сегодня, дневной лимит, обратный отсчёт до сброса, request_id + защита от двойного клика), роль НПС «Интендант», проба интенданта в профиле НПС (open → лавка, silent → «Этот человек с вами не разговаривает»), лавка интенданта со скидкой звания, замками и подтверждением покупки
[LOG] 2026-11-06 — Frontend Dev: задача #8 — админка: вкладка «Экономика» фракции (казна, богатство числом, приток/отток, шаблон и свои числа, участники, «Заполнить по шаблону» при factions:economy + economy:emit, интенданты с подсказкой про тайные фракции, ассортимент с правилом «не с рынка», долги, покупки с повтором/возвратом, история пересчётов, операции казны), вкладка «Шаблоны экономики», новые настройки и поля звания (марки, скидка), долги и покупки в карточке персонажа, подписи faction_treasury и 5 операций в «Экономике» + итог «Казны фракций»
[LOG] 2026-11-06 — Frontend Dev: проверка — tsc и build в контейнере зелёные; вживую в Chrome: привязан интендант (НПС 33) и товар (зелье, мин. звание «Рыцарь»), новое звание «Магистр» с 20000 марок и скидкой 15 %, Ашари пожертвовала 100 марок → +10 очков → «Магистр» → долг 10698 (казна 9302 выплачена частично, «Бедствует»), покупка 2 зелий за 170 (скидка 15 %, выдано, 170 сразу ушли в погашение долга), silent проверен (временно, данные возвращены), 360 px без горизонтальной прокрутки, ошибок в консоли нет. Тестовые данные (звание «Магистр», интендант, ассортимент, долг) оставлены в локальной БД
[LOG] 2026-11-06 — QA: задача #9 — 285 новых тестов character-service (faction_world.py + econ-хелперы; test_faction_econ_core 90: чистая математика — параметры/границы, богатство и слова, доли края, масштабирование взносов, жалованье, уход −5 %/приток +1 % с остатком и границами, FIFO долгов, бюджет закупок и доля запаса, очки пожертвований, цена интенданта, случайный прогон 1500 входов на инварианты денег; test_faction_econ_flows 39: долг за звание → выплата, уведомления один раз, без ретро, долг переживает выход/исключение/скрытие, обход 5-мин, эмиссия админа гасит долг; пожертвования — лимит по UTC-дню, request_id 409, 400, враждебные −50 %, валидация/инъекции 422, чужой персонаж 403; test_faction_econ_tick 23: одна операция на фракцию за прогон, повтор run_id без двойных проводок, DuplicateOperation, падающая фракция откатывается одна, доли кошелька/казны края, закупки платят кошельку жителей, все причины «не тикает», уведомления о долге из тика, purge, интеграция с run_tick; test_faction_econ_qm 42: probe none/silent/open, тайная фракция 403 без утечки, гейты, скидка, запас, outbox (успех/повтор/авто-возврат после 5/возврат долгом/uncertain без повтора/stale/нет транзакции во время HTTP), админ повтор/возврат; test_faction_econ_admin 91: RBAC factions:economy, fill требует ещё economy:emit, повторный клик = 0, валидация 422/409, шаблоны, интенданты, ассортимент, защита удаления, настройки и поля звания, итог factions в сводке, секретность богатства, чужие долги не читаются, миграция 046 на эмуляции MySQL). Инвариант мира 0 после каждого денежного потока. Миграция 046 на локальной MySQL проверена (версия 046, 8 таблиц, 5 шаблонов, бэкфилл, индексы FK)
[LOG] 2026-11-06 — QA: полный прогон character-service — 9593 passed, 1 failed (test_reject_then_24h_reapply_cooldown — FEAT-205, «мигает» из-за часов, повторно 5/5 зелёный)
[LOG] 2026-11-06 — QA: «мигающий» TestRewards::test_no_transaction_is_open_during_the_http_call[item] — не баг продукта: часы контейнера Docker/WSL2 под нагрузкой шагают назад до 1,1 с (4 отката за 45 с), тесты FEAT-205 сравнивают два чтения now_utc() → доставка «ещё не наступила»; так же падали test_item_connect_error…, test_rewards_granted_once…, test_warning_then_clear (≈1 на 24 параллельных прогона). Обнаружен баг (тестовая инфраструктура), добавлен в ISSUES.md (LOW); новые тесты FEAT-206 передают явное время
[LOG] 2026-11-06 — QA: замечания (LOW, не блокеры): (1) тайный интендант с нейтральной ролью: probe = none, но GET/buy отвечают 403 «Этот человек с вами не разговаривает» (или 400/409) вместо 404 как у обычного НПС — не-член через API может узнать, что НПС чей-то тайный интендант (сама фракция не раскрывается); (2) PUT /admin/factions/{id}/economy: пропущенные template_code/overrides очищаются, а прочие поля сохраняются — частичное тело {"members_count":5} снимает шаблон (фронт шлёт форму целиком); (3) одновременный двойной клик «Заполнить по шаблону» — второй запрос получит 400 «Операция с марками отклонена» вместо emitted 0 (деньги не задваиваются); (4) у фракции без строки экономики причина «Экономика этой фракции выключена» вместо «Не выбран шаблон» (после бэкфилла недостижимо)
[LOG] 2026-11-06 — QA: задача #10 — check_econ_copies: все копии ok; контрактные тесты: inventory 452, locations 439, dungeon 439 (с --asyncio-mode=auto, как в CI), character 450 — зелёные; user-service test_rbac_permissions 117 passed (в т.ч. 8 TestFactionEconomyPermission); battle-pass-service 172 passed
[LOG] 2026-11-06 — Backend Dev: замечания QA исправлены — (1) тайный интендант для не-участника: проверка секретности перенесена до «мёртв / не рядом / блокировка активности»; при нейтральной роли (probe = none) просмотр и покупка отвечают ровно как обычный НПС (404 «Интендант не найден»), при роли «Интендант» (probe = silent) — прежний 403 «Этот человек с вами не разговаривает»; фронт не менялся (лавку открывает только при open); (2) PUT экономики фракции частичный: пропущенные template_code/overrides сохраняются, явный null очищает; (3) одновременный двойной клик «Заполнить по шаблону» — второй запрос получает emitted 0 (ключ проверяется блокирующим чтением, DuplicateOperation = «уже сделано»), деньги не задваиваются; (4) «мигающие» тесты FEAT-205: в фикстуре fw часы фракций не идут назад (steady_utcnow, им же пользуется now() тестов), в тестах outbox явный at=/now=; запись LOW в ISSUES.md удалена; документация сервиса обновлена. Новые тесты: 5 (секретность интенданта ×4, частичный PUT, одновременный двойной клик). Полный прогон character-service дважды: 9600 passed, 1 skipped
[LOG] 2026-11-06 — Reviewer: проверка завершена, результат FAIL (1 замечание MEDIUM): в пожертвовании операция с марками проводится до записи долга за новое звание — нарушен порядок блокировок, возможна взаимная блокировка с выплатой долгов/тиком той же фракции (деньги не теряются, но запрос падает); исправление — проводить операцию последней. Остальное в порядке: py_compile, tsc и сборка (в контейнере), pytest character 9600/1 skip, контракты inventory/locations/dungeon, user 788, battle-pass 172, check_econ_copies ok; вживую — пожертвование, покупка у интенданта, админка экономики/шаблоны/ассортимент, ручной тик #101 (сумма мира 0 до и после), ошибок в консоли нет
[LOG] 2026-11-06 — Backend Dev: замечание ревью #1 исправлено — в пожертвовании проводка марок теперь последняя (сначала строка дня, очки, штраф враждебным, журнал и проверка званий с записью долга), нехватка марок откатывает всё; та же ошибка найдена и исправлена в покупке у интенданта (строка покупки пишется до проводки, гонка одинакового request_id → 409); проверка владельца в пожертвовании вынесена из event loop; остальные потоки (выплата долгов, возврат, тик, «Заполнить») порядок соблюдают. 5 новых тестов (порядок записи по SQL-событиям, откат при нехватке, повтор покупки); документация сервиса обновлена. py_compile ok, полный прогон character-service: 9605 passed, 1 skipped
[LOG] 2026-11-06 — Reviewer: повторная проверка (ревью #2) — PASS: порядок блокировок в пожертвовании и покупке у интенданта исправлен (операция с марками последней), py_compile ok, character-service 9605 passed / 1 skipped; вживую пожертвование 30 и покупка у интенданта, повторы с тем же request_id → 409, сумма мира 0 до и после
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Казна фракции — отдельный счёт в общей книге (`faction_treasury`, 5 новых типов операций), контракт ledger обновлён во всех 4 сервисах, копии побайтно совпадают.
- Жизнь фракции в 6-часовом тике: взносы и доход по шаблону из кошелька населения края штаба, жалованье обратно, долги игрокам, закупки интенданта с рынка края; лимиты на край (2 % кошелька, 1 % казны за тик), динамика участников −5 %/+1 %, богатство 0–100 → 4 слова.
- 5 шаблонов фракций с переопределением чисел; «Заполнить по шаблону» через эмиссию с комментарием.
- Пожертвования (10 марок = 1 очко, лимит 50 очков в день, штраф враждебным), марки за звания из казны с очередью долгов (FIFO, частичные выплаты, долг переживает выход/исключение/скрытие).
- Интендант: роль NPC, ассортимент по званиям со скидкой, конечный запас, выдача через очередь с автовозвратом; тайный интендант не раскрывается.
- Админка: вкладка «Экономика» фракции, шаблоны, ассортимент, долги/покупки, история тиков и операций; право `factions:economy` (user 0035).
- 285 тестов QA + тесты на порядок блокировок; инвариант «сумма денег мира = 0» проверяется после каждого денежного действия.

### Что изменилось от первоначального плана
- Закупки интенданта платят в кошелёк населения края (как торговцы), а не в казну края — решение пользователя.
- Ревью #1 нашло нарушение порядка блокировок в пожертвовании (риск взаимной блокировки с тиком) — исправлено там и в покупке у интенданта; ревью #2 PASS.

### Оставшиеся риски / follow-up задачи
- Этап 3: закрытые локации/данжи фракций, пассивки, очки за убийство врагов фракции, членство как преступление.
- На проде фракций нет — их создаёт админ; экономике нужен шаблон и штаб.
- Пожертвование предметов — не сделано (договорились на потом).
