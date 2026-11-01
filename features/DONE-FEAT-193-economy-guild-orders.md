# FEAT-193: Экономика, этап 5в — заказы гильдии торговцев

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-01 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Продолжение экономики: FEAT-181 (книга счетов), FEAT-182 (живые регионы), FEAT-183 (торговцы НПС), FEAT-184 (банки),
FEAT-186 (масштаб населения), FEAT-187 (события регионов), FEAT-191 (монетный двор и квота), FEAT-192 (караваны).
Этап 5: 5а — монетный двор (готово), 5б — караваны (готово), **5в (эта) — заказы через гильдию торговцев**.

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Караваны НПС выравнивают запасы между регионами, но игроки в этом не участвуют. Заказы дают игрокам способ
закрывать нехватки регионов своими предметами и зарабатывать на этом: регион, которому чего-то не хватает,
выставляет заказ в гильдии торговцев, игрок приносит туда подходящие предметы и сразу получает марки.

### Бизнес-правила (согласовано с пользователем 2026-11-01)
- **Заказы выставляют только регионы** (НПС-заказы). Заказы игроков друг другу — не в этой фиче.
- Регион выставляет заказ на **группу товаров**, когда её запас ниже нормы. Объём заказа конечен (связан с
  нехваткой). Заказы обновляются каждый 6-часовой пересчёт; когда нехватка ушла — заказ закрывается сам.
- **Принимается любой предмет нужной группы** (эффективная группа предмета, как у монетчика). Плата зависит от
  стоимости предмета (его ценность в единицах запаса региона × местная цена) плюс надбавка.
- **Надбавка за заказ** — +20 % к местной цене по умолчанию, настраивается в админке.
- **Кто платит:** кошелёк населения региона; за продовольствие при нехватке денег у жителей доплачивает казна
  региона (как у караванов). Новые деньги заказы не создают.
- **Где сдавать:** у НПС с новой ролью «Гильдия торговцев» в этом же регионе (как банкир / монетчик).
- **Где видно:** у НПС гильдии (список заказов региона) + строчка в карточке региона «Гильдия ищет: древесину,
  зелья» (без цифр денег). Общей доски заказов по миру **нет** — чтобы игроки ходили по регионам.
- **Без личных лимитов** на игрока: кто первый принёс — тот и получил, пока объём заказа не исчерпан.
- **Не принимаются** предметы с заточкой, камнями, износом (как у монетчика — только «чистые» стопки).
- Сданный предмет исчезает из инвентаря, запас региона растёт на его ценность в единицах.

### UX / Пользовательский сценарий
1. Игрок видит в карточке региона «Гильдия ищет: древесину».
2. Подходит к НПС «Гильдия торговцев» в регионе, видит заказы: группа, сколько ещё нужно, цена.
3. Выбирает предметы из инвентаря подходящей группы и количество, видит сумму, сдаёт.
4. Предметы списываются, марки зачисляются, заказ уменьшается.

### Edge Cases
- Заказ исчерпан или закрылся между открытием окна и сдачей — понятная ошибка, ничего не списано.
- Сдаётся больше, чем осталось в заказе — принимается сколько влезает (или ошибка с числом — на усмотрение
  архитектора, как у монетчика: «принимает сколько влезает»).
- У жителей кончились деньги — заказ не может платить, его не показывают / закрывают.
- НПС гильдии мёртв — гильдия закрыта (как у торговцев/банкиров).
- Регион не участвует в симуляции — заказов нет.

### Вопросы к пользователю
- [x] Кто выставляет заказы → только регионы
- [x] Что принимать → любой предмет группы
- [x] Кто платит → кошелёк населения, за еду доплачивает казна
- [x] Надбавка → +20 %, настройка в админке
- [x] Где видно → у НПС гильдии + строчка в карточке региона, без общей доски
- [x] Лимиты → без личных лимитов; заточенное/с камнями/с износом не принимаем

### Решения пользователя после анализа (2026-11-01)
1. **Перепродажа (вариант «в»):** гильдия принимает любые предметы группы, но платит за предмет **не дороже, чем
   его можно купить у торговцев этого региона** — по самой низкой возможной цене (с максимальной скидкой за
   харизму) и ещё чуть ниже, чтобы «купил у торговца → сдал гильдии» всегда было в минус. Предметы, которых у
   торговцев региона нет, — с полной надбавкой +20 %. Перевозка из дешёвого региона в дорогой остаётся выгодной.
2. **Лимит трат жителей:** гильдия тратит за один пересчёт не больше 25 % кошелька населения (настройка в админке,
   как у караванов).
3. **Порог открытия заказа:** заказ открывается, только когда запас группы ниже **80 % нормы** (настройка в
   админке); слишком мелкие заказы не открываются (минимальный объём — на усмотрение архитектора, настройка).
4. **Боевой пропуск:** марки за заказы гильдии считаются «заработанными» (как у монетчика).
5. **Не принимаются вообще:** свитки, рецепты, квестовые предметы, всё легендарное и выше (вне рынка).
6. Караваны в пути вычитаются из объёма заказа (чтобы жители не платили дважды за одну нехватку).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

CS = `services/character-service/app`, FE = `services/frontend/app-chaldea/src`. Findings of DONE-FEAT-191 §2/§3 and
DONE-FEAT-192 §2/§3 are reused and not repeated; only what matters for guild orders is listed.

### Affected Services

| Service | Type of changes | Files |
|---|---|---|
| character-service | order recompute in the tick, guild player API (view + hand-in), admin read + params, card field, (probably) new table + migration `036_*` | `CS/econ_tick.py`, new `CS/econ_guild.py` (pure) + `CS/economy_guild_crud.py` (pattern `economy_mint_crud.py`), `CS/economy_api.py`, `CS/econ_sim.py` (SimParams), `CS/schemas.py`, `CS/models.py`, `CS/economy_sim_crud.py:832-859` (`region_card`), `CS/alembic/versions/036_*.py` |
| inventory / locations / dungeon | **byte copy only** of `econ_core.py` (+ `tests/econ_contract_cases.py`) if a new op type is added (it must be — see 7) | `*/app/econ_core.py`, `*/tests/econ_contract_cases.py`, own `tests/test_econ_contract.py` asserts |
| battle-pass-service | none unless the new op must be excluded from «earned gold» (`battle-pass-service/app/crud.py:411-421`) | — |
| frontend | role `guild` in NPC lists, button + modal in `NpcProfileModal`, card line, admin tab/section + guide, op label | see 5, 6 |
| locations / inventory / user-service | no code changes (reads of `Regions`, writes to `character_inventory` by raw SQL as the mint does) | — |

### Existing Patterns
- character-service: sync SQLAlchemy, Pydantic v1, Alembic head **`035_econ_caravans`** (`CS/alembic/versions/035_econ_caravans.py`), version table `alembic_version_character`. Next revision `036_…` (≤ 32 chars, no FK to foreign-owned tables).
- Economy = pure module + crud + one tick pass/step + `RunSummary` counters + error prefix (`CS/econ_tick.py:125-134`) + admin tab + guide section.
- Tunables = JSON `econ_sim_settings.params` → `econ_sim.SimParams` (no DDL; bounds `CS/schemas.py ECON_SIM_PARAM_BOUNDS`). A markup like 20 % fits here (`guild_markup_pct`); it does not create money, so it needs only `economy:settings` (the `MONEY_SIM_PARAMS` guard, `CS/economy_api.py:465`, is for emission params only).

### 1. Prices: how a handed-in item is valued
- Group base prices: `econ_goods_groups.base_price` (food 2, ore_metal 10, wood 5, herbs 8, hides_textiles 10, magic 40, weapons 120, armor 100, jewelry 200, potions 30, tools 40, household 80 — confirmed in local DB).
- Region multiplier: `econ_region_goods.price_mult`, written **only by the region step** (`CS/econ_tick.py:809`) from `econ_sim.price_mult` (`CS/econ_sim.py:269-276`): `clamp((stock/norm)^(-0.631), 0.5, 3.0)`, norm 0 → 1.0; afterwards multiplied by event `price` mods and re-clamped (`econ_sim.py:529`). So the stored value includes events (a «Ярмарка» ×0.9 can make a slightly-below-norm group cost < 1.0). Mint / caravan / merchant stock changes between ticks do **not** update `price_mult` → the «local price» is stable for the whole 6 h period.
- stock < norm ⇔ raw ratio < 1 ⇔ `price_mult` > 1 (before event mods).
- Item → group: `econ_core.effective_item_group` (`CS/econ_core.py:778-796`) over `auto_item_group` (:411-434) with admin overrides `econ_item_groups`; one SQL for everything `core.sql_item_market` (:1002-1008) + `item_market_from_row` (:963-966) → `ItemMarket(item_id, name, image, price, group, off_market)`. Off-market = scroll/recipe or rarity legendary+ (:388-389) — the guild should most likely reject `off_market` items (merchants treat them at mult 1).
- Item value: `item_base_price(items.price, group_base)` (:799-805, `items.price` if > 0 else group base) → `units_per_item(item_base, group_base)` (:875-883) = item_base / group_base region units. **Value in marks at local price = units × group_base × price_mult = item_base × price_mult**, so the guild payout per piece is `floor(item_base × price_mult × (1 + markup))`. The mint already does the unit part (`CS/economy_mint_crud.py:591-594`).
- Granularity: one item can be worth far more units than the order volume (an armor with price 1000 = 10 armor units; local deficits are often < 1 unit, e.g. jewelry 2.776/2.800). The architect must pick a rule: accept whole pieces while `units_left > 0` (last piece may overshoot) vs. only pieces that fit.

### 2. Mint player flow — what is reusable
`economy_mint_crud.mint` (`CS/economy_mint_crud.py:551-624`), all in one transaction, router commits:
1. lock `econ_regions` → `econ_region_goods` → counter row (`lock_capital` :317-328, `populate_existing` + FOR UPDATE, SQLite-safe via `_for_update`);
2. duplicate pre-check `core.SQL_SELECT_OPERATION_BY_KEY` with key `mint:{character_id}:{request_id}` (:563, :571);
3. item checks via `_item_markets` (:455-461) — effective group must match;
4. `_take_ore` (:524-548): `SELECT … FROM character_inventory WHERE character_id, item_id AND COALESCE(enhancement_points_spent,0)=0 AND socketed_gems IS NULL AND current_durability IS NULL ORDER BY id FOR UPDATE`, «not enough» → 400, then DELETE / `quantity - :q` per row. **Generic despite the name** — reusable as is (rename/move to a shared helper or import).
5. `goods.stock += units` (:591-594);
6. `econ_ledger.post_operation(...)` as the **last** step (locks `characters` then `econ_accounts`), `DuplicateOperation` → 409.
- Gate: `resolve_minter` (:409-424, steps 1-4: owner+player, NPC exists/`is_npc`/role (404), dead (409), activity lock on writes, same location), `with_region` (:427-432, `econ_ledger.resolve_location`), `_player_character` (:398-406), `_plain_have` (:464-473, «в сумке» counts), `_wallet` (:485-487), `_fmt` (:108). Router: `CS/economy_api.py:825-899` — GET view without gate; POST `async` → `_mint_precheck` in threadpool → `await locations_client.check_npc_gate` (no DB txn open, fail-closed 503/403) → `_mint_commit` re-runs checks + flow + commit, maps `EconomyApiError` / `IntegrityError` (409 `MSG_RETRY`) / `EconomyError` (400) / `SQLAlchemyError` (500). Request id type: bank `_BANK_REQ_ID`; partial acceptance precedent `MSG_PARTIAL` (:71) and `MintActionOut.requested/partial`.
- These helpers are role-specific only in the role constant and messages; the guild needs its own `GUILD_ROLE` and Russian texts, everything else copies 1:1.

### 3. Orders: stored vs derived live; where the recompute fits
**Live derivation** (`need = norm_stock − stock` at hand-in time, no table):
- + no new table, no tick change, always consistent with stock;
- − not «finite / updated each tick»: every tick consumption lowers stock again, and even between ticks nothing caps it except stock reaching norm; after players fill to norm the order disappears and reappears as soon as consumption runs → effectively an unlimited standing buy order;
- − no place to store `units_total` / budget for the admin view and for «сколько ещё нужно»; concurrency is still safe (lock `econ_region_goods` row).
**Stored order rows** (e.g. `econ_guild_orders` PK `(region_id, group_code)`: `units_total`, `units_left`, `price_mult` snapshot, `run_id`, `opened_at`, `paid_total`):
- + matches the brief (finite volume set by the tick, closes itself when the tick sees no shortage), admin can see filled/paid, the card reads one table;
- + the hand-in locks one order row (`units_left` check-and-decrement under FOR UPDATE) → two players cannot over-fill;
- − migration + recompute code.
**Where the recompute fits:**
- (a) **inside `_process_region`** (`CS/econ_tick.py:680-897`) after the goods rows are updated (:803-814): the region row and its goods rows are already locked, the `last_run_id` guard (:705-707) makes it idempotent on resumed runs; order rows locked after `econ_region_goods` keeps the global order. Caveat: the merchant SAVEPOINT (:851-870) and the later `_mint_pass` (:1230) still change stock after it → recompute right before COMMIT using `merchant_stock`/final row stock; capital ore taken by the court mint afterwards is not reflected until the next tick (minor; court mint takes only above threshold, default 100 % of norm).
- (b) **separate `_orders_pass` after `_mint_pass`** (one txn per region: `econ_regions → econ_region_goods → order rows`): sees the final stock of the run, but needs its own idempotency (run_id on rows) and a resumed-run rule; one more pass and error prefix.
- Inputs worth subtracting: caravans in transit to the region (`econ_caravans` `status='in_transit'`, `to_region_id`, `SUM(units)` — the snapshot query already exists in `economy_caravan_crud.load_snapshot` :184-238). The caravan planner subtracts `inbound` from need; if orders do not, players and an already-paid caravan cover the same deficit and the buyer purse pays twice.
- Data fact (local DB): almost every group sits a hair under norm (ratio 0.98-0.999, `price_mult` 1.001-1.013), e.g. region 10 has 7 groups below norm, only wood is a real shortage (374.9/562.5, ×1.29). «Stock below norm → order» literally would open orders on nearly every group with sub-item volumes. A threshold (e.g. stock < X % of norm, or `price_mult ≥` the card's `SHORTAGE_MULT` 1.6 `CS/econ_sim.py:49`) and a minimum volume are needed — architect/user decision.

### 4. Payment source accounts; `split_payment`
- Accounts: `AccountRef.purse(region)` (population_purse, **not** negative-allowed), `AccountRef.region(region)` (treasury, may go negative) — `CS/econ_core.py:52-95, 255`.
- `econ_caravan.split_payment(cost, purse_left, treasury_left, is_food)` (`CS/econ_caravan.py:162-176`) — pure: purse first, treasury tops up **food only**, None if not coverable. Reusable directly (import from `econ_caravan`) for `purse → character` + `treasury → character` legs. Caravans also use `affordable_units` (:150-159) to shrink volume to the budget.
- Caravan budgets (`caravan_purse_share` 0.25, `caravan_treasury_food_share` 0.5, `econ_sim.py:147-149`) cap spending per run; for the guild a similar share cap is worth considering — a purse drained by hand-ins kills affordability → hunger → stability in the next region step (`econ_sim.simulate_region` step 5). Negative treasury pays nothing (caravan rule `max(0, treasury)`).
- Locking balances: caravans pre-lock accounts with `_lock_balances` (`economy_caravan_crud.py:261-269`) — **do not copy that for the guild**: the guild op also credits a character, and the ledger locks `characters` before `econ_accounts` (`econ_core.apply_steps`; lock order docstring `CS/econ_tick.py:53-63`). Pre-locking the purse before `post_operation` would invert the order. Safe alternative: plain read of purse/treasury for the budget (the `econ_regions` row lock already serialises guild hand-ins and the region tick of that region) — `post_operation`'s conditional UPDATE (`CS/econ_ledger.py:267-280`) still raises `InsufficientFunds` atomically if a concurrent writer (bank pass) drained the purse → map to a Russian 409.
- Tax: `purse → character` and `treasury → character` legs never trigger country tax (tax only fires on inflows into a region treasury, `econ_core.tax_region_ids` :521-528). Pass `apply_tax=False` explicitly as all econ callers do. No emission → world sum stays 0.

### 5. NPC roles and the player dialog
- Backend: `characters.npc_role VARCHAR(50)`, free string, no whitelist (`CS/schemas.py:745-818`). Each role module has its own constant (`economy_mint_crud.MINTER_ROLE = "minter"` :46; `economy_bank_crud.BANKER_ROLE`). Admin «Монетный двор» lists minters by SQL on `npc_role` (`economy_mint_crud._minters_by_country` :631-650) — same shape for guild masters per region (or `economy_bank_crud.bankers_by_region`).
- Frontend labels: `FE/constants/npc.ts` — `NPC_ROLES` (value/label, used by admin NPC form `AdminNpcsPage`), `NPC_ROLE_ICONS` (banker 🏦, minter ⚒️; merchant 🪙, auctioneer ⚖️ are taken — the guild needs an unused icon, e.g. 📜).
- Opening: `FE/components/pages/LocationPage/NpcProfileModal.tsx` — role-gated buttons `npc.npc_role === 'banker' && isCharacterHere && characterId` (:328) and `'minter'` (:348) open `BankModal` (:125) / `MintModal` (:136). New `GuildModal/` mirrors `MintModal/MintModal.tsx` (364 lines) + `MintParts.tsx`.

### 6. Region card
- Backend `economy_sim_crud.region_card` (`CS/economy_sim_crud.py:832-859`): hidden shape (:840-841) and participating shape (:857-859). Orders only exist in participating regions → add e.g. `guild_wants: List[str]` (group names, no numbers) to both shapes (`[]` in hidden), like `events`.
- Frontend `FE/api/regionEconomy.ts` (optional fields pattern :27-54, card contract «no numbers») and `FE/components/WorldPage/RegionEconomyCard.tsx`: the line fits next to `RegionCaravans` (:272) or with the institution lines `bankLine`/`mintLine` (:207-218, also rendered in the non-participating branch :220-226). «Гильдия ищет: древесину, зелья» needs accusative/lowercase group names — `econ_goods_groups.name` is nominative («Древесина»); either a backend phrase builder (as `econ_sim.region_card` phrases) or just «Гильдия ищет: древесина, зелья».

### 7. econ_core copy rule
- `validate_operation` rejects unknown op types (`CS/econ_core.py:485`), and `OP_TYPES` is a closed frozenset (:157-165). A new op (e.g. `guild_order`, legs `purse → character` + `region → character`, `LEG_MAIN`) **requires editing `econ_core.py`** and byte-copying it to inventory/locations/dungeon (`scripts/check_econ_copies.sh`, CI job `econ-contract-copies`), plus contract cases in `tests/econ_contract_cases.py` (×4) and per-service asserts (FEAT-191/192 precedent). Not in `SOURCE_OP_TYPES`, not comment-required. No new account kind needed. `op_type` VARCHAR(50) → no ledger DDL.
- Reusing an existing type (`npc_shop_sell` = NPC character → player) would mislabel the journal and the source account kind; not recommended.
- Other consumers: FE `components/Admin/EconomyPage/economyLabels.ts` `OP_TYPE_LABELS`; battle-pass `LEDGER_EXCLUDED_OP_TYPES` (`battle-pass-service/app/crud.py:411-421`) — the guild payout is a posting into a character account, so it **counts as earned gold** for battle-pass missions unless excluded (mint_player precedent: counted on purpose).

### 8. Risks
- **R1 Arbitrage with NPC merchants (important, needs a user decision).** Merchant ask = `ceil(buy_price × price_mult)` (`econ_core.market_ask` :830-832, `locations-service/app/crud.py:4328-4347`), minus charisma discount up to **50 %** (`discounted_ask` :866-872, `MAX_CHARISMA_DISCOUNT` 0.5 at 250 charisma, :728-729). The **same** region `price_mult` drives both. Guild pays `item_base × price_mult × 1.2`. `buy_price` = `item_base` for player-origin rows (`locations-service/app/crud.py:5006-5023`) and locally equals `items.price` for 4 of 6 admin rows. ⇒ buy at the merchant, hand in to the guild of the same region: profit ≈ `item_base × mult × (0.2 + discount)` per piece — **+20 % even with 0 charisma, up to 2.4× at max charisma**. The loop is self-feeding: merchants restock from the region stock (wholesale `merchant_wholesale_share` 0.5, `econ_sim.py:98`, paid to the purse) and the guild puts the item back into the stock paid from the same purse → a money pump from residents to the player, bounded only by order volume, merchant stock and purse. Cross-region (buy where `price_mult` 0.5, sell where 3.0) the spread is up to 7.2× — this is intended «player trader» gameplay, but large. Legacy merchants (non-participating region / not living) sell at mult 1, some with **unlimited** stock (`stock NULL`, local NPC 429). `character_inventory` has **no provenance column** (columns: id, character_id, item_id, quantity, enhancement_points_spent, enhancement_bonuses, socketed_gems, is_identified, current_durability) → «items bought from a merchant» cannot be excluded. Mitigation options for the user: (a) pay below the cheapest possible merchant ask in the region (i.e. ≤ `ask × (1 − 0.5)`, which kills the +20 % idea), (b) do not accept items that any living merchant of the same region sells, (c) pay the markup only on the part of the value that is not purchasable locally / cap per tick by a purse share, (d) accept the loop as a bounded mechanic (volume finite per tick), (e) pay at wholesale level (`× 0.5`) + markup.
- **R2 Items with price 0** are valued at the group base (`item_base_price` :799-805): locally 20/42 resources, all 3 weapons, 3/3 body armor, 7/7 furniture have price 0 → e.g. any price-0 weapon is worth 120 × mult × 1.2. Starter-kit items (granted free on character approval, `starter_kits.items`) can be sold too. Not a bug, but admins should know values come from `items.price` / group base.
- **R3 Lock order / deadlocks.** Hand-in: `econ_regions → econ_region_goods (asc group) → order row → character_inventory (asc id) → characters → econ_accounts` — consistent with the global order (`CS/econ_tick.py:53-63`, caravan update FEAT-192 3.9). The order table must be inserted into the docstring and `docs/services/character-service.md`, and the tick must lock order rows in the same position. Never pre-lock accounts (see 4). Order rows should be INSERTed only by the tick (or in their own short txn like `ensure_season_row` :288-303), never inside a hand-in.
- **R4 Double payment / idempotency.** Required client `request_id` → key `guild:{character_id}:{request_id}` (≤ 128 chars), pre-check + UNIQUE ledger key; inventory removal, stock/order update and posting in one txn (router rolls back on any error) — same guarantees as the mint.
- **R5 Price drift.** The stored `price_mult` is fixed until the next tick while players raise the stock → the guild keeps paying the shortage price for the whole period; acceptable if volume is finite (stored orders), unbounded with live derivation.
- **R6 Caravans in transit** cover the same shortage (see 3) — subtract inbound or accept the double purchase.
- **R7 Purse drain** → affordability/hunger effects; consider a per-tick budget share like caravans.
- **R8 Tiny orders** on groups a hair under norm (see 3) — need threshold and minimum.
- **R9 Off-market items** (legendary+, scrolls, recipes) have a group but no market — decide to reject.
- **R10 econ_core copy churn** — one op type constant only; keep everything else out of `econ_core`.
- **R11 Mint interaction** — at the capital ore can go to the guild (purse money, ×1.2 local price) or the minter (emission, fixed rate). If `mint_court_threshold_pct` < 100 the court mint itself creates an ore deficit that the guild then buys back from players. Not an exploit, worth documenting.

### Cross-Service Dependencies
- character-service writes `character_inventory` (owned by inventory-service) by raw SQL — already accepted for the mint (FEAT-191 3.8), document again.
- `locations_client.check_npc_gate` (FEAT-145 gate, `GET /locations/internal/action-gate`) — HTTP, fail-closed.
- `econ_core.py` ×4 byte copies; battle-pass reads the ledger (gold missions).
- No RabbitMQ/Redis.

### Questions that need the user's decision (via PM)
1. **Arbitrage (R1):** the guild pays local price +20 %, while merchants of the same region sell the same group at the local price (and cheaper with charisma, up to −50 %). Buying from a merchant and handing in to the guild is always profitable. Which fix: (a) guild pays less than the cheapest merchant price (drops the +20 % idea), (b) guild refuses items that local merchants sell, (c) keep +20 % but cap the order volume / purse share hard so the loop is small, (d) accept it?
2. **When is there a shortage?** Almost all groups sit just below norm (−0.1 … −2 %). Open an order only when stock is below e.g. 80 % of norm (or the card says «нехватка»), with a minimum volume?
3. Should handing in to the guild count as «earned marks» for battle-pass missions (mint precedent: yes)?
4. Legendary-and-higher items, scrolls, recipes — refuse at the guild?

## 3. Architecture Decision (filled by Architect — in English)

All backend work is in **character-service** (sync SQLAlchemy). inventory-/dungeon-service only get the byte copy of
`econ_core.py` + `tests/econ_contract_cases.py`; **locations-service** additionally gets a behaviour-neutral refactor
of its shop pricing so that the merchant bid / ask selection lives once, in `econ_core` (3.5). battle-pass-service gets
a comment + one test. No new RBAC permission, no Nginx/Docker change. CS = `services/character-service/app`,
FE = `services/frontend/app-chaldea/src`.

The user decisions in section 1 (incl. «Решения пользователя после анализа») and the PM correction of the payout cap
(2026-11-01, 3.5) are final; everything below fills technical gaps.

### 3.1 Module layout

| Module | Kind | Content |
|---|---|---|
| `CS/econ_core.py` (canonical, byte-copied ×3) | constants + pure merchant helpers | op type `guild_order` (3.8); pure shop helpers lifted from locations-service (3.5): `ask_discount_floor`, `effective_shop_stock`, `shop_row_prices`, `merchant_buys_groups`, `shop_row_bid`. Nothing guild-specific. |
| `CS/econ_guild.py` (new) | pure, no DB | order recompute (3.3), unit price (3.5), acceptance / partial maths (3.6), guild XP maths (3.6a). Reuses `econ_core` price helpers and `econ_caravan.split_payment`. |
| `CS/economy_guild_crud.py` (new) | DB | tick step helpers (lock / recompute / sweep), guild gate + view + hand-in flow (3.6), region merchant quotes (3.5), admin reads (3.10), card list (3.9). Pattern: `economy_mint_crud.py`. |
| `CS/economy_mint_crud.py` | DB | `_take_ore` → public `take_plain_stacks(...)` (generic; mint keeps calling it; guild imports it). No behaviour change. |
| `CS/econ_tick.py` | DB | guild step inside `_process_region` (3.2), `_guild_sweep` after the region loop, `RunSummary` counters, `GUILD_ERROR_PREFIX`, docstring lock order (3.7). |
| `CS/economy_api.py` | router | player GET/POST, admin GET (3.10). |
| `CS/econ_sim.py` | params | 9 `SimParams` fields (3.4). |
| `CS/economy_sim_crud.py` | DB | `region_card` gets `guild_wants` in both shapes (3.9). |
| `CS/models.py`, `CS/schemas.py` | ORM / Pydantic v1 | `EconGuildOrder`, `EconGuildXpDay`, 2 `EconRegion` columns, schemas, `ECON_SIM_PARAM_BOUNDS` / `ECON_SIM_INT_PARAMS`. |
| `CS/alembic/versions/036_econ_guild_orders.py` | migration | revision id `036_econ_guild_orders` (21 chars ≤ 32), down `035_econ_caravans`. |
| `locations-service/app/crud.py` | refactor only | `effective_stock`, `price_shop_row`, `_buys_groups`, `quote_bid` delegate to the new `econ_core` helpers; outputs unchanged. |

### 3.2 Where orders are recomputed — inside `_process_region`

**Decision: analyst option (a), inside `_process_region`, as the last step before the history row / COMMIT, in its
own SAVEPOINT** (same technique as the merchant step). Reasons:
- the region row, its goods rows (and with this feature its order rows) are already locked → the recompute and the
  per-run budget are atomic with the region's tick; the `last_run_id` guard makes resumed runs idempotent for free;
- the caravan pass runs **before** the region loop, so caravans dispatched in this run are already in
  `econ_caravans(in_transit)` and are subtracted (decision 6);
- `price_mult` / `norm_stock` were just written by this step → the order price snapshot equals the price merchants use
  for the next 6 h;
- no extra pass, no extra idempotency mechanism.

Inputs: final stock of each goods row **after** the merchant step (`merchant_stock.get(code, row.stock)` — merchants
restock from the region stock), `norm_stock`, `price_mult`, `is_food`, base price; `inbound[group]` = `SELECT
group_code, SUM(units) FROM econ_caravans WHERE status='in_transit' AND to_region_id=:r GROUP BY group_code`;
purse / treasury balances **after** the tick posting, event expenses and merchant postings (`account_balance`).
The court mint (`_mint_pass`, after the loop) may still take capital ore above its threshold — it never creates a
deficit below `mint_court_threshold_pct` of the norm, so with defaults (100 %) it cannot conflict; documented (R11).

**Lock placement:** the region's order rows (`status='open'`) are locked FOR UPDATE (ascending id) **right after the
event rows**, before the merchant step (global order 3.7); they are written at the end in the SAVEPOINT. New order
rows are INSERTed in the same transaction — safe because every writer of `econ_guild_orders` (region step, hand-in)
holds the region's `econ_regions` row lock first, so inserts on one region are serialised (no insert-intention
deadlock; documented like FEAT-192 3.7).

**Failure:** an exception in the guild step rolls back the SAVEPOINT only (orders and budget keep their previous
values), logs, `summary.guild_failures += 1`, `GUILD_ERROR_PREFIX = "гильдия — ошибка в регионах: "` + ids in the run
error; the region itself is ticked. The merchant step's `DuplicateOperation` path skips the guild step too (another
runner did the region).

**Sweep:** `_guild_sweep(session_factory, run_id, summary)` after the region loop (before `_mint_pass`), one short
transaction: close every `open` order whose region no longer participates (`econ_regions` row gone / `template_code
IS NULL` / `population <= 0`) → `close_reason='region_left'`, and zero those regions' budgets. Hand-ins re-check
participation anyway (3.6), so the sweep is cosmetic for the admin view. Runs in scheduled and manual runs.

### 3.3 Order recompute (pure `econ_guild.plan_orders`)

Per goods group of the region (deterministic, no RNG):
```
covered   = stock + inbound[g]
threshold = norm × guild_open_threshold_pct / 100
volume    = floor3(norm − covered)                              # fill to the FULL norm (not to the threshold)
value     = volume × group.base_price × price_mult              # marks at the local price, no markup
open iff  guild_enabled = 1 and norm > 0 and covered < threshold and value ≥ guild_min_order_value
          and payable(g)                                        # some budget exists for this group (3.4)
```
`payable(g)` = `guild_budget > 0`, or for food `guild_budget + guild_food_budget > 0`. Same rule every tick (no
hysteresis — simple, stateless, testable).

Applying the plan to the stored rows (one open row per (region, group) at most):
- open wanted, open row exists → **refresh** it: `units_total = units_left = volume` (the tick re-measures the real
  shortage; cumulative `units_filled / pieces / paid_*` counters stay), `price_mult` / `markup_pct` snapshot,
  `last_run_id = run_id`, `updated_at`;
- open wanted, no open row → INSERT a new row (`status='open'`, `open_key='r{region}:{group}'`, `opened_run_id`);
- not wanted, open row exists → close: `status='closed'`, `open_key=NULL`, `closed_at`, `closed_run_id`,
  `close_reason` ∈ `no_shortage` (covered ≥ threshold or value < min), `no_money`, `disabled` (`guild_enabled=0`
  or `norm = 0`);
- a row that was `filled` between ticks stays closed; if the shortage persists a **new** row opens (history kept).

**Budget (decision 2), stored on `econ_regions` (lockable, 3.4):** at the same point the step sets
`guild_budget = floor(max(0, purse) × guild_purse_share)` and `guild_food_budget = floor(max(0, treasury) ×
guild_treasury_food_share)` — a fresh allowance per run, not accumulated. `guild_enabled = 0` → both 0 and all open
orders closed (`disabled`).

### 3.4 Settings (sim params JSON — no migration for numbers) and the budget columns

| Param | Type | Default | Bounds | Meaning |
|---|---|---|---|---|
| `guild_enabled` | int | 1 | 0 … 1 | 0 = no orders (all open ones close on the next recount) |
| `guild_markup_pct` | float | 20.0 | 0 … 200 | markup over the local price (decision «+20 %») |
| `guild_open_threshold_pct` | float | 80.0 | 1 … 100 | an order exists only while stock (+ caravans on the road) < this % of the norm |
| `guild_min_order_value` | int | 50 | 1 … 1 000 000 | smaller shortages (volume × base price × local mult, marks) open no order |
| `guild_purse_share` | float | 0.25 | 0 … 1 | share of the residents' purse the guild may spend per recount (decision 2) |
| `guild_treasury_food_share` | float | 0.25 | 0 … 1 | share of the positive region treasury that may top up **food** orders per recount |
| `guild_xp_per_mark` | float | 0.1 | 0 … 10 | XP per mark paid for an item **no** merchant of the region sells (3.6a) |
| `guild_xp_per_mark_merchant_items` | float | 0.05 | 0 … 10 | XP per mark paid for an item a merchant of the region sells (3.6a) |
| `guild_xp_daily_cap` | int | 200 | 0 … 1 000 000 | max base guild XP per character per UTC day (both rates together); 0 = guild XP off |

(9 params in total.) All via the existing `PUT /characters/admin/economy/sim` (`economy:settings`); none creates money → no
`MONEY_SIM_PARAMS` guard. Int keys into `ECON_SIM_INT_PARAMS`. Hints in `paramHints.ts`.

`econ_regions` gets `guild_budget BIGINT NOT NULL DEFAULT 0` and `guild_food_budget BIGINT NOT NULL DEFAULT 0`
(the lockable per-run budget — the hand-in already locks this row first, so no extra lock and no new lock position).

### 3.5 Unit price per item (PM correction 2026-11-01 — final rule)

The guild **never pays less than a merchant of the region would pay** for the item, and its markup is capped at the
same level as the merchant bid cap (so «buy at max charisma → hand in» is never profitable). Per item, with
`m = order.price_mult` (the region's current `price_mult`, equal to the snapshot) and the region's merchants
(below):
```
item_base   = core.item_base_price(items.price, group.base_price)
offer       = floor(item_base × m × (1 + guild_markup_pct / 100))            # Decimal maths, floor
if some merchant of the region sells this item:
    cheapest_ask = min(ask of every sellable row of this item)               # ask = core.market_ask(buy_price, mult_of_row)
    offer        = min(offer, core.ask_discount_floor(cheapest_ask))         # floor(ask × (1 − MAX_CHARISMA_DISCOUNT))
best_bid    = max(core.shop_row_bid(...) over the region's merchants, default 0)
unit_price  = max(best_bid, offer)
unit_price ≤ 0  → item refused: MSG_NOT_WORTH (400)
```
- `ask_discount_floor(ask) = floor(ask × (1 − MAX_CHARISMA_DISCOUNT))` is the exact term `market_bid` already uses;
  `market_bid` is rewritten to call it (byte-identical results). Buying at max charisma costs
  `discounted_ask(ask, 50) = ceil(ask × 0.5) ≥ floor(ask × 0.5)` → no profit loop at the same merchant level.
- **«Merchants of the region»** = NPCs with at least one active `npc_shop_items` row, `npc_status <> 'dead'` (a dead
  merchant's shop is closed), whose location resolves to this region (`econ_tick.merchant_place`, which already
  returns `region_id` for living **and** legacy-in-region merchants, e.g. a dungeon merchant). Legacy merchants are
  included with mult 1 and their unlimited / finite stock (they are buyable / sellable in this region too) — the
  user's «include legacy merchants» point.
- **Sellable row (ask side)** — exactly what the player shop window shows (`get_npc_shop_items_player`): active row
  of a non-dead merchant; `origin='player'` rows only while `effective_shop_stock > 0`; admin rows count even at stock
  0 (they restock — conservative, keeps the price stable within a period). Row mult = `core.market_mult(living, group,
  off_market, region_mults)`.
- **Bid side** — `core.shop_row_bid(living, item, row, buys_groups, mults, group_base, bid_share)` = today's
  locations `quote_bid` unit price (row present: its capped bid if `sell_price > 0`; no row: living merchant buying
  the item's group via `default_bid(item_base, merchant_bid_share)` moved by the mult and capped; legacy without a row:
  0). `buys_groups = core.merchant_buys_groups(rows, items)`; `bid_share = core.merchant_bid_share(params JSON)`.
- **Single source of truth:** these pure helpers move from `locations-service/app/crud.py` into `econ_core`
  (`effective_shop_stock(living, stock)`, `shop_row_prices(living, item, buy_price, sell_price, mults) -> {group,
  off_market, market, mult, ask, bid, price_level}`, `merchant_buys_groups(rows, items)`, `shop_row_bid(...) -> int`,
  `ask_discount_floor(ask)`); locations' `effective_stock`, `price_shop_row`, `_buys_groups`, `quote_bid` become thin
  wrappers with unchanged signatures/outputs (its existing shop tests are the regression net). character-service's
  merchant step is not touched.
- Loader `economy_guild_crud.region_quotes(db, region_id, item_markets) -> {item_id: Quote(best_bid,
  cheapest_ask|None)}`: `SQL_MERCHANT_NPCS` → `merchant_place` per NPC (filter region / not dead) → their rows
  (`core.sql_lock_shop_rows(..., for_update=False)`) → `load_item_markets` for row items + requested items → region
  mults/bases (`core.SQL_REGION_MARKET`) + `bid_share`. Plain reads (no locks) — bounded by the number of merchants
  in one region (tens). Prices of merchants change only in the tick or by admin edits; a race with an admin edit is
  accepted.
- `item_base = 0` → `units_per_item = 0` → refused (`MSG_NOT_WORTH`). Items valued at the group base (price 0) are
  accepted at that value (R2, documented in the guide).

### 3.6 Player flow at the «Гильдия торговцев»

NPC role **`guild`** (`characters.npc_role`, free string; label «Гильдия торговцев», icon `📜`). Gate = banker/minter
order (FEAT-184 3.9 / FEAT-191 3.8): 1 JWT + ownership + player character (403) → 2 NPC exists, `is_npc`,
`npc_role == "guild"` (404), not dead (409) → 3 activity lock (POST only) → 4 same `current_location_id` (400) →
5 FEAT-145 gate (POST only, `locations_client.check_npc_gate`, fail-closed, awaited with **no open DB transaction**)
→ 6 NPC location → region (`econ_ledger.resolve_location`) → region participates (else 409 `MSG_GUILD_CLOSED`) and
`guild_enabled = 1` (else 409 `MSG_GUILD_CLOSED`).

**Eligibility of an item** (`econ_guild.refusal(...)`, first failing rule wins, each with a Russian reason):
effective group known and `not off_market` (scrolls, recipes, legendary+ and admin off-market overrides →
`MSG_ITEM_NOT_ACCEPTED`); not a quest item (`EXISTS quest_objectives q WHERE q.target_id = item AND q.objective_type
IN ('collect','deliver')` — the `economy_sim_crud.QUEST_ITEM_OBJECTIVES` rule → `MSG_QUEST_ITEM`); an **open** order
for the item's group in this region with `units_left > 0` (`MSG_NO_ORDER`); `unit_price > 0` (`MSG_NOT_WORTH`).
Only plain stacks count (`enhancement_points_spent = 0`, `socketed_gems IS NULL`, `current_durability IS NULL`) —
same as the mint; equipped items live elsewhere and are never touched.

**Flow `hand_in(db, ctx, body, xp_multiplier)`** — `ensure_xp_day_row` (own short commit, 3.6a) first, then one DB
transaction, router commits, all or nothing:
1. Lock `econ_regions(region)` FOR UPDATE → re-check participation / `guild_enabled`.
2. Duplicate pre-check `core.SQL_SELECT_OPERATION_BY_KEY`, key `guild:{character_id}:{request_id}` → 409
   `MSG_DUPLICATE`.
3. Item market (`sql_item_market`), eligibility rules above (group needed to pick the order).
4. Lock `econ_region_goods(region, group)` → lock the open order row by `open_key` FOR UPDATE (none / `units_left
   <= 0` → 409 `MSG_NO_ORDER`).
5. Quote (3.5) → `unit_price`; `u = units_per_item(item_base, group_base)` (> 0).
6. Money available (plain reads, **no account pre-lock** — the ledger locks characters → accounts itself):
   `purse_left = min(region.guild_budget, max(0, purse_balance))`, `treasury_left = min(region.guild_food_budget,
   max(0, treasury_balance))` if food else 0.
7. Pure `econ_guild.accept(quantity, units_left, u, unit_price, purse_left, treasury_left, is_food)`:
   `by_volume = ceil(units_left / u)` — **over-fill rule: whole pieces are accepted while the order still needs
   something; the last piece may overshoot** (an expensive item must not be unsellable to a small order; the money
   budget is the real cap); `by_money = floor((purse_left + treasury_left) / unit_price)`;
   `accepted = min(quantity, by_volume, by_money)`; `accepted = 0` → 409 `MSG_NO_MONEY` (by money) —
   `by_volume` is ≥ 1 whenever the order is open. `total = accepted × unit_price`;
   `(paid_purse, paid_treasury) = econ_caravan.split_payment(total, purse_left, treasury_left, is_food)` (never None
   by construction).
8. Take items: `economy_mint_crud.take_plain_stacks(db, character_id, item_id, quantity_requested_check=quantity,
   take=accepted, …)` — «not enough» is checked against the REQUESTED quantity (mint precedent) → 400
   `MSG_NOT_ENOUGH`; then only `accepted` pieces are removed (rows ascending id, FOR UPDATE).
9. `goods.stock += round3(accepted × u)`; order: `units_left = max(0, round3(units_left − accepted × u))`,
   `units_filled += accepted × u`, `pieces += accepted`, `paid_total += total`, `paid_treasury += paid_treasury`,
   `hand_ins += 1`, `updated_at`; `units_left == 0` → `status='filled'`, `open_key=NULL`, `closed_at`,
   `close_reason='filled'`. Region: `guild_budget -= paid_purse`, `guild_food_budget -= paid_treasury`.
9a. Lock `econ_guild_xp_days(character_id, today)` FOR UPDATE → XP maths (3.6a) → `xp += base_xp`.
10. `post_operation(op_type=guild_order, legs=[purse(region) → character, paid_purse; region(region) → character,
    paid_treasury], apply_tax=False, location_id, region_id, actor_user_id, idempotency_key=key,
    metadata={order_id, npc_id, item_id, item_name, group, quantity: accepted, requested, unit_price, units,
    price_mult, markup_pct, best_bid, cheapest_ask})` — **last** DB step. `DuplicateOperation` → 409
   `MSG_DUPLICATE`; `InsufficientFunds` (a concurrent bank pass drained the purse) → 409 `MSG_RETRY_MONEY`; router
   rolls back → items never lost, nothing paid twice.
10a. XP: `UPDATE character_attributes … passive_experience + granted` (3.6a). Router commits, then the level-up check.
- Success message `"Гильдия приняла {item_name} × {accepted} — получено {total fmt}"`; partial (accepted < requested)
  → 200 with `MSG_PARTIAL` naming why (`заказ почти закрыт` / `у жителей не хватает денег`); the rest stays in the bag.
- No price stability between GET and POST is promised: POST recomputes; the modal shows the server message.

Russian texts (constants in `economy_guild_crud.py`, tests assert them):
`MSG_GUILD_NOT_FOUND = "Гильдия торговцев не найдена"` (404), `MSG_GUILD_DEAD = "Гильдия торговцев закрыта — её
представитель больше не принимает посетителей"` (409), `MSG_NOT_PLAYER = "Гильдией пользуются только персонажи
игроков"` (403), `MSG_NOT_OWNER` (bank text, 403), `MSG_WRONG_LOCATION = "Подойдите к представителю гильдии — он в
другой локации"` (400), `MSG_GATE_CLOSED` (bank text, 403), `MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к
гильдии, попробуйте позже"` (503), `MSG_GUILD_CLOSED = "Гильдия не принимает заказы: {reason}"` (409; reasons «регион
не участвует в экономике», «заказы гильдии выключены»), `MSG_NO_ORDER = "Гильдии сейчас не нужны такие товары — заказ
закрыт или выполнен"` (409), `MSG_NO_MONEY = "У жителей сейчас нет денег на этот заказ — загляните после пересчёта"`
(409), `MSG_ITEM_NOT_ACCEPTED = "Гильдия не принимает этот предмет (свитки, рецепты, легендарное и выше — вне
рынка)"` (400), `MSG_QUEST_ITEM = "Квестовые предметы гильдия не принимает"` (400), `MSG_NOT_WORTH = "Гильдия не
может заплатить за этот предмет: торговцы региона продают его слишком дёшево"` (400), `MSG_NOT_ENOUGH` (mint text,
400), `MSG_PARTIAL = "Принято {accepted} из {requested} шт. — {why}, остальное осталось у вас. Получено {total}"`
(200), `MSG_DUPLICATE = "Операция уже выполнена"` (409), `MSG_RETRY` (bank text, 409 on IntegrityError),
`MSG_RETRY_MONEY = "Деньги жителей изменились во время сделки, попробуйте ещё раз"` (409).

Cross-ownership: character-service writes `character_inventory` (inventory-service table) — same accepted precedent as
the mint (FEAT-191 3.8); docs updated.

### 3.6a Experience for guild hand-ins (user requirement 2026-11-01, «как за выполненный квест»)

Only hand-ins against a regional guild order grant XP (selling to merchants never does — no change there).

**Amount** (one item line per request): `rate = guild_xp_per_mark_merchant_items (0.05)` if the item is sold by a
merchant of the region (the same «sellable row» set as the ask side of 3.5, i.e. `quote.cheapest_ask is not None`),
else `guild_xp_per_mark (0.1)`; `base_xp = floor(total_marks_paid × rate)` (Decimal, floor).
**Daily cap** (main protection against the «buy at break-even → hand in» XP farm): per character per **UTC calendar
day**, counted in base XP over both rates: `base_xp = min(base_xp, max(0, guild_xp_daily_cap − used_today))`;
`guild_xp_daily_cap = 0` → no guild XP at all. Default **200**: by the level curve (`level_thresholds`: lvl 2 = 200,
lvl 10 = 2716, lvl 20 = 10 232 total XP; ~470 XP per level around lvl 10, ~1 100 around lvl 20) that is one level a
day at the very start, about half a level at lvl 10 and a fifth at lvl 20 — a useful bonus for real traders, but
farming it with merchant-sold items needs ~4 000 marks of hand-ins a day (at 5 %), each piece losing up to 1 mark,
and is additionally bounded by the order volume and the residents' budget.
**XP book:** the quest book applies (`crud.XP_SOURCE_QUEST`, «как за квест»): granted XP = `crud.multiply_xp(base_xp,
multiplier)`; the cap counts **base** XP so a book still boosts a capped character. The multiplier is resolved by the
router **before** any DB transaction (`crud.get_character_xp_multiplier(character_id, XP_SOURCE_QUEST)` in the
threadpool precheck step — fail-open to 1.0, the FEAT-168 rule «no transaction waits on another service») and passed
into the commit step.

**Storage — new table `econ_guild_xp_days`** `(character_id, day)` PK, `xp` = base XP granted that day. The row is
created by `ensure_xp_day_row` in its **own short transaction** before the main one (INSERT, `IntegrityError` →
already exists; FEAT-191 `ensure_season_row` precedent — never inside the locking transaction), then locked FOR
UPDATE in the main transaction (lock position 3.7). Rows older than 7 days are deleted by `_guild_sweep`.

**Granting — same transaction as the hand-in, idempotent with the same `request_id`.** Hand-in steps 9a/10a (3.6):
after the stock/order/budget updates, `xp_day.xp += base_xp`; after `post_operation` (still in the transaction,
matching `add_rewards_to_character`, which also posts the ledger first and then touches XP):
`UPDATE character_attributes SET passive_experience = passive_experience + :granted WHERE character_id = :c` (direct
SQL on the shared DB — the same path `add_rewards_to_character` / locations `add_experience` use for quest XP).
rowcount 0 (no attributes row) → `granted = 0`, the day counter is not increased, warning logged; the hand-in still
succeeds. Base XP, granted XP, rate and multiplier go into the `guild_order` operation metadata (`xp_base`, `xp`,
`xp_rate`, `xp_multiplier`). Since all of it is in the one transaction guarded by the UNIQUE ledger key, a repeated
`request_id` (409) or any failure rolls XP back together with items and money.
**Level-up:** after the router's `db.commit()`, when `granted > 0`, the commit step calls
`crud.check_and_update_level(db, character_id, new_total_xp)` (the existing level-up path; it commits on its own). A
failure there is logged only — the XP is already stored and the next XP grant of any kind re-runs the check (same
behaviour as quest/battle rewards today).

**Responses:** `GuildView` gets `"xp": {"per_mark": 0.1, "per_mark_merchant_items": 0.05, "daily_cap": 200,
"left_today": 140, "multiplier": 1.0}` (`multiplier` resolved in the GET handler before its DB work; `left_today` in
base XP) and each offer gets `"xp_rate": 0.1` (the rate that applies to that item). Preview in the modal:
`floor(min(floor(total × xp_rate), left_today) × multiplier)` — the same formula as the server (`multiply_xp` floors
via `int()`). `GuildActionOut` gets `"xp": int` (granted) and `"xp_capped": bool` (base cut by the cap); the success
message appends `" и {xp} опыта"` when `xp > 0` and «(дневной лимит опыта гильдии исчерпан)» when capped to 0.

### 3.7 Lock order (supersedes FEAT-192 3.9 — update `econ_tick.py` docstring and `character-service.md`)
`econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) → econ_region_events (asc id) →
econ_caravans (asc id) → econ_guild_orders (asc id) → econ_guild_xp_days → econ_mint_seasons → npc_shop_items (asc id)
→ econ_banks (asc region_id) → bank_deposits (asc id) → bank_loans (asc id) → character_inventory (asc id) → characters
(asc id) → econ_accounts (asc id) → character_attributes`.
- `character_attributes` is last: `add_rewards_to_character` (quests/battles) already posts the ledger (characters →
  accounts) before updating XP, so the guild keeps that order.
- Region step: `econ_regions → goods → events → guild orders (open, asc id) → npc_shop_items → characters →
  econ_accounts`; budget columns live on the already-locked region row.
- Hand-in: `econ_regions → econ_region_goods(group) → econ_guild_orders(open row) → econ_guild_xp_days(character,
  day) → character_inventory → characters → econ_accounts → character_attributes`. `npc_shop_items` / `characters` of merchants are **read without locks**.
- Sweep: `econ_guild_orders` + `econ_regions` UPDATEs by region, regions ascending — it never locks goods; it only
  touches regions that no longer participate (no region step / hand-in runs on them) → no cycle.
- Inserts of order rows only under the region's `econ_regions` lock (3.2).

### 3.8 Ledger: new op type (econ_core, copied byte-for-byte to inventory/locations/dungeon)
```python
OP_GUILD_ORDER = "guild_order"   # FEAT-193: a player fills a region's guild order: purse (+ region treasury for food) -> character
GUILD_OP_TYPES = frozenset({OP_GUILD_ORDER})
OP_TYPES |= GUILD_OP_TYPES       # NOT in SOURCE_OP_TYPES, NOT comment-required
```
Legs `purse(region) → character` and `region(region) → character`, `LEG_MAIN`, `apply_tax=False` (no inflow into a
region treasury → never taxed anyway). No emission → world sum stays 0. No new account kind.
Contract cases (canonical `tests/econ_contract_cases.py`, byte-copied): `guild_order` with the two legs and no comment
passes; with an `emission` leg fails; plus cases for the lifted pure shop helpers (`ask_discount_floor`,
`shop_row_bid` row / no-row / legacy / off-market, `effective_shop_stock`, `market_bid` unchanged results).
Each service's own `tests/test_econ_contract.py`: `GUILD_OP_TYPES <= OP_TYPES`, disjoint from `SOURCE_OP_TYPES` and
`COMMENT_REQUIRED_OP_TYPES`. `scripts/check_econ_copies.sh` must pass.

**Battle pass (decision 4):** `guild_order` posts into a character account → counted as earned by
`_ledger_gold_sum` as long as it is **not** added to `LEDGER_EXCLUDED_OP_TYPES` — add only a comment line
(«FEAT-193: guild_order is deliberately NOT excluded — filling guild orders counts as earned gold») + a regression
test in `test_gold_missions.py`.

### 3.9 Region card (`guild_wants`, words only)
`region_card` (both shapes) gets `"guild_wants": [{"group_code": "wood", "group_name": "Древесина"}, …]`:
open orders of the region with `units_left > 0` and payable now (`guild_budget > 0`, or food with
`guild_budget + guild_food_budget > 0`), **only when the region has at least one non-dead NPC with role `guild` whose
location resolves to it** (no seller window → no misleading line). Ordered by the group order (`econ_goods_groups`
order used by the card), max 12. Hidden shape → `[]`. No units, no money.
Frontend (`RegionEconomyCard.tsx`, in the institutions area next to `bankLine` / `mintLine`, participating branch
only): «Гильдия ищет: древесину, зелья» using the existing `GROUP_ACCUSATIVE` map (fallback lowercase
`group_name`); hidden when empty.

### 3.10 API contracts (router prefix `/characters`, `economy_api.py`, Pydantic v1)

Player (JWT `get_current_user_via_http`):

#### `GET /characters/economy/guild/npc/{npc_id}?character_id=` → `GuildView` (gate steps 1, 2, 4, 6; no FEAT-145 gate, no lock)
```json
{
  "npc_id": 1, "npc_name": "str", "region_id": 3, "region_name": "str",
  "working": true, "closed_reason": null,
  "markup_pct": 20.0,
  "orders": [{"order_id": 7, "group_code": "wood", "group_name": "Древесина", "is_food": false,
              "units_total": 187.5, "units_left": 120.25, "filled_pct": 36, "payable": true}],
  "offers": [{"item_id": 5, "name": "str", "image": "str|null", "group_code": "wood", "order_id": 7,
              "have": 14, "unit_price": 7, "units_per_item": 1.0, "max_accept": 14,
              "capped_by_merchants": false}],
  "refused": [{"item_id": 9, "name": "str", "image": "str|null", "group_code": "wood", "have": 2,
               "reason": "Квестовые предметы гильдия не принимает"}],
  "xp": {"per_mark": 0.1, "per_mark_merchant_items": 0.05, "daily_cap": 200, "left_today": 140, "multiplier": 1.0},
  "wallet": 1234
}
```
Each `offers[]` entry also has `"xp_rate": 0.1|0.05` (3.6a). `orders` = open rows (payable or not; `payable=false` shown as «жителям нечем платить до пересчёта»). `offers` =
plain bag stacks whose effective group has an open order and that pass all rules; `max_accept = min(have, by_volume,
by_money, 10000)` (budget numbers themselves are not exposed). `refused` = bag items of wanted groups that fail a rule
(reason text). `working=false` → `orders/offers/refused = []` with `closed_reason`.

#### `POST /characters/economy/guild/npc/{npc_id}/hand-in` (async; precheck in threadpool → gate → commit in threadpool, exactly like the mint)
Request `GuildHandInIn`: `{"character_id": int ≥1, "item_id": int ≥1, "quantity": int 1…10000, "request_id": str}`
(`request_id` = bank `_BANK_REQ_ID` constrained type, required). Response `GuildActionOut`:
`{"message": str, "operation_id": int, "quantity": int, "requested": int, "partial": bool, "unit_price": int,
"total": int, "xp": int, "xp_capped": bool, "wallet": int, "view": GuildView}`. Errors per 3.6; `IntegrityError` → 409 `MSG_RETRY`;
`core.EconomyError` → 400 «Операция отклонена»; `SQLAlchemyError` → 500 generic.

Admin:

#### `GET /characters/admin/economy/guild?status=open|closed|all&region_id=&group_code=&limit=50&offset=0` (`economy:read`) → `GuildAdminOut`
```json
{
  "params": {"guild_enabled": 1, "guild_markup_pct": 20.0, "guild_open_threshold_pct": 80.0,
             "guild_min_order_value": 50, "guild_purse_share": 0.25, "guild_treasury_food_share": 0.25,
             "guild_xp_per_mark": 0.1, "guild_xp_per_mark_merchant_items": 0.05, "guild_xp_daily_cap": 200},
  "totals": {"open": 5, "units_left_value": 1400, "paid_last_7d": 3200, "hand_ins_last_7d": 41, "xp_last_7d": 900},
  "regions": [{"region_id": 3, "region_name": "str", "guild_budget": 500, "guild_food_budget": 120,
               "open_orders": 2, "masters": [{"npc_id": 9, "name": "str", "npc_status": "alive",
                                              "location_name": "str"}]}],
  "total": 40,
  "items": [{"id": 7, "region_id": 3, "region_name": "str|null", "group_code": "wood", "group_name": "Древесина",
             "status": "open", "close_reason": null, "units_total": 187.5, "units_left": 120.25,
             "units_filled": 70.0, "price_mult": 1.29, "markup_pct": 20.0, "pieces": 70, "paid_total": 455,
             "paid_treasury": 0, "hand_ins": 6, "opened_at": "iso", "updated_at": "iso", "closed_at": null}]
}
```
`regions` = participating regions (budgets + guild masters, empty `masters` → frontend warning «нет представителя
гильдии — заказы никто не примет»). `status` regex (default `open`), `group_code` must be a known group (400),
`region_id ≥ 1`, `limit 1…200`, `offset ≥ 0`; newest first. `paid_last_7d` / `hand_ins_last_7d` from
`econ_operations WHERE op_type='guild_order'`. Region names via LEFT JOIN (deleted → `null`).

#### `PUT /characters/admin/economy/sim` (existing) — the 9 optional fields of 3.4.
#### `GET /characters/economy/regions/{region_id}/card` (existing) — additive `guild_wants` (3.9).

No new permission; `economy:emit` not used.

### 3.11 DB changes — migration `036_econ_guild_orders` (raw-SQL DDL, `_TABLE_OPTS`, re-runnable like 034/035)
```sql
CREATE TABLE IF NOT EXISTS econ_guild_orders (    -- one order «opening»; history kept; no FK (regions owned by locations)
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  region_id INT NOT NULL,
  group_code VARCHAR(32) NOT NULL,
  open_key VARCHAR(48) NULL,                      -- 'r<region>:<group>' while open, NULL when closed/filled
  status VARCHAR(16) NOT NULL,                    -- open | filled | closed (validated in code)
  close_reason VARCHAR(32) NULL,                  -- filled | no_shortage | no_money | disabled | region_left
  units_total DECIMAL(16,3) NOT NULL,
  units_left DECIMAL(16,3) NOT NULL,
  units_filled DECIMAL(16,3) NOT NULL DEFAULT 0,
  price_mult DECIMAL(10,3) NOT NULL,
  markup_pct DECIMAL(6,2) NOT NULL,
  pieces INT NOT NULL DEFAULT 0,
  paid_total BIGINT NOT NULL DEFAULT 0,
  paid_treasury BIGINT NOT NULL DEFAULT 0,
  hand_ins INT NOT NULL DEFAULT 0,
  opened_run_id INT NOT NULL, last_run_id INT NOT NULL, closed_run_id INT NULL,
  opened_at DATETIME NOT NULL, updated_at DATETIME NULL, closed_at DATETIME NULL,
  UNIQUE KEY uq_econ_guild_orders_open (open_key),   -- MySQL allows many NULLs: at most one OPEN order per region/group
  KEY ix_econ_guild_orders_region (region_id, status),
  KEY ix_econ_guild_orders_status (status, id),
  KEY ix_econ_guild_orders_closed (closed_at)
) <_TABLE_OPTS>;

CREATE TABLE IF NOT EXISTS econ_guild_xp_days (   -- per-character daily guild XP counter (base XP, 3.6a)
  character_id INT NOT NULL,
  day DATE NOT NULL,                               -- UTC calendar day
  xp INT NOT NULL DEFAULT 0,
  PRIMARY KEY (character_id, day)
) <_TABLE_OPTS>;

ALTER TABLE econ_regions ADD COLUMN guild_budget BIGINT NOT NULL DEFAULT 0;        -- only if missing (information_schema check)
ALTER TABLE econ_regions ADD COLUMN guild_food_budget BIGINT NOT NULL DEFAULT 0;   -- only if missing
```
No FKs, no ENUM. Nothing seeded (budgets 0 until the first recount → no orders/hand-ins before it, which is correct).
Retention: rows kept (future «газета»); `purge_old` untouched; `closed_at` index ready for a later purge. Size: ≤ 12
groups × regions openings per run — tiny. **Downgrade:** drop the two columns + `DROP TABLE IF EXISTS
econ_guild_xp_days, econ_guild_orders`; ledger rows and granted XP stay. SQLite tests: models carry the columns/table; `open_key` UNIQUE works the same
(SQLite also allows many NULLs).

### 3.12 Frontend
- `constants/npc.ts`: `{ value: 'guild', label: 'Гильдия торговцев' }`, icon `'📜'`.
- `NpcProfileModal.tsx`: button «Гильдия торговцев» when `npc.npc_role === 'guild' && isCharacterHere &&
  characterId` → `GuildModal`.
- New `components/pages/LocationPage/GuildModal/GuildModal.tsx` (+ `GuildParts.tsx`): header (region), closed banner;
  «Заказы» list (group name, progress bar «выполнено N %», badge «жителям нечем платить до пересчёта» when
  `!payable`); «Что можно сдать» — offers (image, name, «N марок за шт.», note «цена ограничена ценами торговцев»
  when `capped_by_merchants`, «в сумке: X», quantity input clamped to `min(have, 10000)` with hint «гильдия примет до
  N шт.» when above `max_accept`, preview «получите M марок и K опыта» for the accepted pieces (3.6a formula; «опыт за сегодня исчерпан» when
`left_today = 0`; note «за товары, которые продают торговцы, опыта вдвое меньше» on offers with the lower rate),
button «Сдать»; the result message shows the granted XP); «Не принимается»
  list with the reason. `request_id = crypto.randomUUID()` per attempt (new after success). Every error visible in
  Russian (toast + inline), 409 duplicate as info, partial message kept in the modal. `modal-overlay` /
  `modal-content`, `btn-blue`, `gold-text`; Tailwind only; 360px+ (list rows stack on mobile).
- New `api/guild.ts` (player GET/POST + admin GET) and types in `types/economy.ts` (`GuildView`, `GuildOrder`,
  `GuildOffer`, `GuildRefused`, `GuildXpInfo`, `GuildActionOut`, `GuildAdminOut`, `GuildOrderRow`, `GuildRegionRow`,
  9 `EconSimParams` fields).
- `api/regionEconomy.ts`: `guild_wants?: {group_code: string; group_name: string}[]`; `RegionEconomyCard.tsx` line
  «Гильдия ищет: …» (3.9).
- Admin: new tab **«Гильдия»** `components/Admin/EconomyPage/EconomyGuild.tsx` — params card (9 params via sim PUT,
  `ParamHint`), totals, regions list (budgets, open orders, masters, warning when no master), orders list with status
  tabs (открытые / закрытые / все), region + group filters, pagination; mobile → cards; close reasons in Russian
  («выполнен», «нехватки нет», «нет денег», «выключено», «регион вышел из экономики»). `EconomyPage.tsx`
  (`TAB_LABEL.guild = 'Гильдия'`, `TAB_INTRO`), `guideSections.ts` + `EconomyGuide.tsx`: section «Гильдия торговцев»
  (threshold, full-norm volume, caravans in transit subtracted, price = local price + markup but never below what
  merchants pay and never above floor(cheapest ask × 0.5) of an item merchants sell, budget 25 % of the purse per
  recount + food top-up from the treasury, whole pieces / last piece may overshoot, excluded items, price-0 items
  valued at the group base, battle-pass counts it, XP 10 % / 5 % of the marks with the daily cap and the quest book),
checklist step «Поставить НПС с ролью „Гильдия торговцев“ в
  регионы», recipe «Как открыть гильдию в регионе»; `paramHints.ts` (9); `economyLabels.ts` `OP_TYPE_LABELS.
  guild_order = 'Заказ гильдии'`.
- All touched files `.ts/.tsx`, no `React.FC`, design-system classes.

### 3.13 Data flow
```
econ_scheduler / «Пересчитать сейчас» → run_tick: … → _quota_pass → _caravan_pass
  → region loop: _process_region: lock region → goods → events → open guild orders → simulate → post → merchants
       → SAVEPOINT guild step: inbound caravans + final stock + balances → econ_guild.plan_orders → refresh / insert /
         close orders; region.guild_budget / guild_food_budget = shares of purse / treasury → COMMIT
  → _guild_sweep (close orders of regions that left) → _mint_pass → banks → done
Player → GuildModal → POST /characters/economy/guild/npc/{id}/hand-in → Nginx → character-service
  ├─ threadpool precheck (JWT via user-service /users/me, ownership, NPC role/alive, lock, location) → rollback
  ├─ HTTP locations-service GET /locations/internal/action-gate (FEAT-145, fail-closed)
  └─ threadpool, ONE transaction: lock region → goods(group) → order → quote (plain reads of npc_shop_items) →
     xp day row → character_inventory DELETE/UPDATE → stock += units → order/budget/xp-day updated → guild_order
     posting (purse [+ treasury] → character) → character_attributes XP → COMMIT → level-up check
  (quest XP book multiplier resolved over HTTP in the precheck, before any transaction)
battle-pass-service reads econ_postings → guild_order counted as earned.
Player → GET region card → «Гильдия ищет: …».
```

### 3.14 Security
- Player endpoints: JWT + ownership + player-only + NPC role/alive/location + activity lock + FEAT-145 gate
  (fail-closed). Required `request_id` → UNIQUE ledger key: double submit = one posting, second 409. Quantity
  1…10000; `item_id ≥ 1`; money bounded by the stored budget; no client-supplied price, group or order id (the server
  derives the order from the item's group). The view exposes no purse / treasury / budget numbers. XP is server-side
  only (rate, cap, book), capped per character per day, rolled back with the hand-in.
- Admin: `require_permission("economy:read")`; params via the existing sim PUT (`economy:settings`). No new
  permission → no user-service migration / RBAC test change.
- Validation: Pydantic v1 (`conint`, constrained `request_id`), status regex, `group_code` checked against
  `econ_goods_groups`; parameterised `text()` SQL only.
- No money creation: QA asserts world sum 0 after hand-ins; no tax leg.
- Errors in Russian, internals only in logs.

### 3.15 Risks
- **Arbitrage** — closed by 3.5: the guild pays at most `floor(cheapest ask × 0.5)` for an item a regional merchant
  sells (≤ the max-charisma purchase price `ceil(ask × 0.5)`), and at least the merchant's own bid. Cross-region
  trade (buy cheap elsewhere, hand in here) stays profitable — intended player-trader gameplay.
- **XP farm** — merchant-sold items still give XP (5 %); the daily cap (200 base XP) bounds it; tunable / 0 = off.
- **Over-fill** — the last piece may overshoot the order (one piece at most); bounded by the per-run budget.
- **Purse drain** — ≤ 25 % of the purse (+ 25 % of a positive treasury for food) per recount; tunable.
- **Price drift** — the price is fixed for the period while stock rises (R5); volume is finite per run.
- **Locations refactor** — moving shop pricing into `econ_core` touches the live shop; behaviour-neutral, guarded by
  locations-service shop tests + contract cases.
- **R11 Mint interaction** — court mint threshold < order threshold could create an ore order in the capital; minor,
  documented in the guide.
- **econ_core copies ×4** — CI `check_econ_copies.sh`; tests counting `OP_TYPES` updated.

### Questions for PM (non-blocking — defaults chosen)
1. **Payout rule (PM correction applied):** `unit_price = max(best merchant bid in the region, min(item_base × local
   mult × 1.2, floor(cheapest ask × 0.5) if a regional merchant sells it))`. «Merchants of the region» include legacy
   ones located there (e.g. in a dungeon of the region) at mult 1; admin assortment rows count even when out of stock,
   player-resale rows only while in stock.
2. **Food top-up cap:** the treasury may top up food orders with at most **25 % of its positive balance per recount**
   (caravans use 50 %; together they could take 75 %).
3. **Minimum order:** shortages worth less than **50 marks** at the local price open no order.
4. **Over-fill:** the guild accepts whole pieces while the order still needs anything; the last piece may overshoot
   (otherwise an expensive armour could never be handed to a small armour order).
5. **Order volume:** fill to the **full norm** (not to the 80 % threshold); open/keep rule is the same every recount
   (no hysteresis). The card line shows only regions that actually have a «Гильдия торговцев» NPC.
6. **Guild XP:** 10 % / 5 % of the marks (user), daily cap default **200 base XP per character per UTC day**
   (≈ one level at lvl 1, ½ level at lvl 10, ⅕ at lvl 20); the quest XP book multiplies it and the cap counts XP
   before the book. «Merchant-sold» for the 5 % rate uses the same merchant set as the price cap (legacy merchants of
   the region included).
7. **Unidentified items** (`is_identified = 0`) are accepted like the mint does today (no extra rule) — say if they
   should be refused.

---

### 3.16 Implementation notes (Backend Developer, 2026-11-01)
- Admin list `status` accepts `open|filled|closed|all`; **`closed` lists closed AND filled** orders (the admin
  «закрытые» tab), `filled` alone is also accepted (PM request while the frontend was built).
- `GuildView.region_id` is nullable (an NPC whose location resolves to no region → `working=false`, reason «регион не
  участвует в экономике»).
- The hand-in prices with the order's snapshot `price_mult` **and** `markup_pct` (both written by the recount), so a
  markup change takes effect from the next recount — consistent with «price fixed for the period».
- The `character_attributes` row is checked (plain read) before the posting so the `guild_order` metadata carries the
  final `xp_base / xp`; the UPDATE itself still runs after the posting (3.6a order).
- `economy_mint_crud._take_ore` → public `take_plain_stacks(..., not_enough=MSG_NOT_ENOUGH)` (template parameter
  added so the guild can reuse it; mint behaviour unchanged).
- Additive contract changes required updating 4 exact-shape assertions in existing tests
  (`test_econ_sim.py` seed-key prefixes, card shapes in `test_econ_regions_api.py` ×2 and `test_econ_banks_admin_api.py`).

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **econ_core: op type + lifted shop helpers + copies + locations refactor.** Canonical `econ_core.py`: `OP_GUILD_ORDER`, `GUILD_OP_TYPES` in `OP_TYPES` only (3.8); pure helpers `ask_discount_floor`, `effective_shop_stock`, `shop_row_prices`, `merchant_buys_groups`, `shop_row_bid` (3.5) with `market_bid` rewritten via `ask_discount_floor` (identical results). Contract cases (guild op legs, emission leg fails, helper cases). Byte-copy both files to inventory/locations/dungeon; asserts in each `tests/test_econ_contract.py`. `locations-service/app/crud.py`: `effective_stock`, `price_shop_row`, `_buys_groups`, `quote_bid` delegate to the helpers (signatures/outputs unchanged). battle-pass `crud.py`: FEAT-193 comment next to `LEDGER_EXCLUDED_OP_TYPES` (no tuple change). | Backend Developer | DONE | `services/{character,inventory,locations,dungeon}-service/app/econ_core.py`, `services/*/app/tests/econ_contract_cases.py` (4), `services/*/app/tests/test_econ_contract.py` (4), `services/locations-service/app/crud.py`, `services/battle-pass-service/app/crud.py` | — | `bash scripts/check_econ_copies.sh` passes; `py_compile`; contract tests green in 4 services; **full locations-service shop tests green** (behaviour unchanged). **Do not commit or push.** |
| 2 | **Migration + models + params + pure module.** Migration `036_econ_guild_orders` (3.11: docstring, re-runnable DDL incl. column-exists checks, downgrade). ORM `EconGuildOrder`, `EconGuildXpDay`; `EconRegion.guild_budget`, `guild_food_budget`. `SimParams` 9 fields + `ECON_SIM_PARAM_BOUNDS` / `ECON_SIM_INT_PARAMS` / sim PUT body + sim out schema (3.4). New pure `econ_guild.py`: `plan_orders` (3.3), `unit_price` (3.5), `refusal` rules, `accept` (3.6, uses `econ_caravan.split_payment`), `guild_xp(total, rate, cap, used, multiplier) -> (base, granted, capped)` (3.6a). | Backend Developer | DONE | `CS/alembic/versions/036_econ_guild_orders.py`, `CS/models.py`, `CS/econ_sim.py`, `CS/schemas.py`, `CS/econ_guild.py` (new) | #1 | Revision id ≤ 32 chars, down `035_econ_caravans`; `alembic upgrade head` → `downgrade -1` → `upgrade head` in the container; `py_compile`; pure functions deterministic. |
| 3 | **Guild CRUD + tick step + card.** `economy_guild_crud.py`: lock/recompute/close helpers for the region step, `region_quotes` (3.5), gate `resolve_guild` / `guild_context`, `build_view` (incl. `xp` block / `xp_rate`), `ensure_xp_day_row`, `hand_in` (3.6 + XP 3.6a: xp-day lock, `character_attributes` UPDATE after the posting, metadata; all Russian constants), admin read (3.10), `card_guild_wants` (3.9), sweep. `economy_mint_crud._take_ore` → public `take_plain_stacks` (mint unchanged). `econ_tick.py`: lock open orders after events, SAVEPOINT guild step at the end of `_process_region` (3.2), `_guild_sweep` after the loop, `_guild_sweep` also deletes `econ_guild_xp_days` rows older than 7 days; `RunSummary` counters (`guild_opened/refreshed/closed/failures`), `GUILD_ERROR_PREFIX`, final log line, docstring lock order (3.7). `economy_sim_crud.region_card`: `guild_wants` both shapes. | Backend Developer | DONE | `CS/economy_guild_crud.py` (new), `CS/economy_mint_crud.py`, `CS/econ_tick.py`, `CS/economy_sim_crud.py` | #2 | `py_compile`; dev container: a region with wood < 80 % norm gets an open order after a manual recount, a second recount refreshes it (no duplicate open row), filling to norm closes it; existing `test_econ_tick*.py` and mint tests green. |
| 4 | **Router + schemas.** Endpoints 3.10: player GET view / POST hand-in (async precheck → gate → commit, error mapping like the mint; quest XP book multiplier resolved before any DB transaction and passed in; `check_and_update_level` after commit when XP > 0), admin GET guild; card schema `guild_wants`. Pydantic v1: `GuildHandInIn`, `GuildView`, `GuildOrderOut`, `GuildOfferOut`, `GuildRefusedOut`, `GuildActionOut`, `GuildAdminOut`, `GuildOrderRowOut`, `GuildRegionOut`, `GuildWantOut`. | Backend Developer | DONE | `CS/economy_api.py`, `CS/schemas.py` | #3 | `py_compile`; endpoints in `/docs`; curl in dev: hand-in moves items, stock, order, budget, wallet and XP in one go (level-up when crossing a threshold); same `request_id` twice → one posting + 409. |
| 5 | **Docs.** `docs/services/character-service.md`: guild section (table + budget columns, endpoints, op type, recompute placement, payout rule 3.5, lock order 3.7, params, `character_inventory` write). `docs/services/locations-service.md`: shop pricing helpers now in `econ_core`. `docs/services/inventory-service.md`: guild as another writer of `character_inventory`. `docs/services/battle-pass-service.md`: `guild_order` counts as earned. `docs/ARCHITECTURE.md` if it lists economy tables/ops. | Backend Developer | DONE | `docs/services/character-service.md`, `docs/services/locations-service.md`, `docs/services/inventory-service.md`, `docs/services/battle-pass-service.md`, `docs/ARCHITECTURE.md` | #4 | Docs match the implemented contracts. |
| 6 | **Frontend: player side.** NPC role `guild` (label, icon); button in `NpcProfileModal`; new `GuildModal` (+ parts) per 3.12 with clamped quantity, preview of marks **and XP** (3.6a formula, cap/lower-rate notes), `request_id`, granted XP in the result, partial message, visible Russian errors; `api/guild.ts`, types; `RegionEconomyCard` line «Гильдия ищет: …» + `guild_wants` type. | Frontend Developer | DONE | `src/constants/npc.ts`, `src/components/pages/LocationPage/NpcProfileModal.tsx`, `src/components/pages/LocationPage/GuildModal/GuildModal.tsx` (new), `GuildParts.tsx` (new), `src/api/guild.ts` (new), `src/types/economy.ts`, `src/api/regionEconomy.ts`, `src/components/WorldPage/RegionEconomyCard.tsx` | #4 (contract only — can start from 3.10) | `npx tsc --noEmit` + `npm run build` pass in the container; Tailwind + design-system classes, no `React.FC`, 360px OK. |
| 7 | **Frontend: admin side.** Tab «Гильдия» `EconomyGuild.tsx` (params, totals, regions with budgets/masters/warnings, orders list with tabs/filters/pagination, mobile cards); `EconomyPage.tsx` label/intro; guide section + checklist step + recipe; `paramHints.ts` (9, incl. the 3 XP params); `economyLabels.ts` (`guild_order`, close reasons); API + types. All errors in Russian, 403 → «Недостаточно прав». | Frontend Developer | DONE | `src/components/Admin/EconomyPage/EconomyGuild.tsx` (new), `EconomyPage.tsx`, `guideSections.ts`, `EconomyGuide.tsx`, `paramHints.ts`, `economyLabels.ts`, `src/api/guild.ts`, `src/types/economy.ts` | #4 (contract), #6 (shared files) | `tsc` + `build` pass; admin edits params and browses orders; mobile layout OK. |
| 8 | **QA: pure math + contract + battle-pass.** `test_econ_guild.py`: `plan_orders` (threshold boundary, inbound subtracted from volume and from the open check, full-norm volume, min value, norm 0, disabled, no budget → no_money, food payable via treasury budget only), `unit_price` (markup, ask cap `floor(ask×0.5)`, best bid floor wins over a lower offer, both, neither, price-0 item via group base, result ≤ 0), `refusal` order of rules, `accept` (by volume with last-piece overshoot, by money, purse/treasury split food vs non-food, zero), `guild_xp` (10 % vs 5 % rate, floor, cap reached / partly left / cap 0 = off, cap counts base XP and the book multiplies after the cap). Contract cases incl. lifted shop helpers run in 4 services. Battle-pass `test_gold_missions.py`: a `guild_order` posting into a character counts as earned. | QA Test | DONE | `CS/tests/test_econ_guild.py` (new), `services/battle-pass-service/app/tests/test_gold_missions.py` | #1, #2 | pytest green in character-, inventory-, locations-, dungeon-, battle-pass-service. |
| 9 | **QA: tick.** `test_econ_tick_guild.py` (SQLite tick harness): order opens below threshold, not above; volume = norm − stock − inbound caravans; refresh keeps one open row and counters; closes `no_shortage` / `no_money` / `disabled`; filled row → new row next run; budgets = shares of purse / positive treasury, negative treasury → 0; resumed run does nothing twice; sweep closes orders of a region that left; a failing guild step rolls back only itself (region still ticked, counter + error prefix). | QA Test | DONE | `CS/tests/test_econ_tick_guild.py` (new), `CS/tests/conftest.py` (if needed) | #3 | pytest green; existing tick tests green. |
| 10 | **QA: player + admin API + security.** `test_econ_guild_api.py`: gate order (403 owner/NPC player, 404 not guild, 409 dead, 409 activity lock, 400 wrong location, 403/503 FEAT-145, 409 region not participating / disabled); success (multi-stack removal, stock += units, order/budget decremented, `guild_order` legs purse→character, food uses treasury, wallet, world sum 0, no tax leg); partial by volume and by money; order filled → status `filled`; refusals (scroll, recipe, legendary, off-market override, quest item, other group, non-plain stack ignored, price 0 after cap → `MSG_NOT_WORTH`); merchant cap and merchant-bid floor through the DB loader (living + legacy-in-region merchant, dead merchant ignored, player-resale row only while in stock); not enough 400 with nothing taken; posting failure / `InsufficientFunds` → nothing taken; idempotency (same `request_id` → one op + 409, XP granted once); **XP**: non-merchant item 10 %, merchant-sold item (living and legacy-in-region) 5 %, daily cap across several hand-ins and both rates, next UTC day resets, cap 0 → no XP, quest book multiplier applied (mocked), XP rolled back with a failed posting, no `character_attributes` row → hand-in OK with 0 XP, level-up after crossing a threshold, metadata `xp*` fields, view `xp` block/`xp_rate`, response `xp`/`xp_capped`; SQL-injection-like `request_id` / `group_code` rejected; unauthenticated 401. View: offers/refused/max_accept, no budget numbers. Admin: permissions, filters/validation/pagination, regions masters; sim PUT accepts the 9 params with bounds; card `guild_wants` both shapes, hidden without a guild NPC / when not payable, words only. | QA Test | DONE | `CS/tests/test_econ_guild_api.py` (new), `CS/tests/test_econ_guild_admin_api.py` (new) | #4 | Full character-service pytest green in the container. |
| 11 | **Review.** Contracts vs 3.10/3.9, payout rule 3.5 (incl. PM correction), guild XP 3.6a (rates, cap, book, idempotency, level-up), lock order 3.7, atomicity + idempotency of the hand-in, budget never exceeded, world sum 0 / no tax, econ copies script, locations refactor behaviour-neutral, migration up/down, frontend rules (Tailwind, TS, no `React.FC`, mobile, Russian errors, design system), docs. **Live (Chrome on localhost):** admin sets params; a manual recount opens an order in a short region; card shows «Гильдия ищет: …»; a player at a «Гильдия торговцев» NPC hands in items (wallet, bag, order progress and XP update; partial and refusal messages visible); «Гильдия» admin tab shows the order; journal label «Заказ гильдии»; zero console errors. | Reviewer | DONE | all | #1–#10 | All automated checks (py_compile, pytest of character/inventory/locations/dungeon/battle-pass, `check_econ_copies.sh`, tsc, build) + live verification pass. |

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-02
**Result:** PASS

Scope: whole uncommitted tree — (A) FEAT-193 guild orders, (B) the two user-approved bank fixes (start capital only from
treasury excess over `treasury_target`; realized net interest income → region treasury, `bank_profit_to_treasury_share`).

#### Contract / logic checks
- Payout rule 3.5 + PM correction: `econ_guild.unit_price` = `max(best_bid, min(floor(base×mult×(1+markup)),
  floor(cheapest_ask×0.5)))` — matches; `ask_discount_floor` is the exact term `market_bid` used before (byte-identical).
  Live: health potion (sold by merchant «Петя») capped to 20, mana potion (not sold) 72 = floor(30×2.008×1.2).
- XP 3.6a: 10 % / 5 % rates via `quote.cheapest_ask`, daily cap on base XP, book after cap, XP inside the hand-in
  transaction after the posting, level-up after commit — matches. Live: 360 marks → 36 XP, 60 marks (merchant item) → 3 XP.
- Hand-in atomicity / idempotency: region lock → duplicate pre-check → goods → order → items → stock/order/budget →
  posting last → XP; UNIQUE ledger key. Live: same `request_id` twice → 200 then 409 «Операция уже выполнена».
- Budget never exceeded: `money_left = min(stored budget, live balance)`, `accept` bounds by money, budget decremented
  (live: 107 580 → 107 088 after 492 paid). No tax leg, zero legs skipped by `validate_operation` (postings `amount > 0`).
- API 3.10 / card 3.9 / Pydantic v1 schemas consistent with `types/economy.ts` and `api/guild.ts`.
- locations-service refactor (`price_shop_row`, `effective_stock`, `_buys_groups`, `quote_bid`) is behaviour-neutral
  (line-by-line equivalent; 2254 locations tests green). battle-pass: comment only + tests.
- Bank fixes: `seed_capital_available = max(0, treasury − treasury_target)`; `profit_to_treasury` bounded by `lendable`
  (reserve untouched), marks stored in `last_stats.marks` so nothing is back-dated; admin hints/labels updated; param in
  `ECON_SIM_PARAM_BOUNDS` + `EconSimParamsIn`.
- Frontend: TS only, Tailwind + design-system classes (`btn-blue`, `gold-text`, `input-underline`, `rounded-card`), no
  `React.FC`, every API call has a visible Russian error (toast + inline), duplicate 409 shown as info.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (0 errors)
- [x] `npm run build` — PASS
- [x] `py_compile` (all changed/new .py) — PASS
- [x] `pytest` — character-service 7056 passed / 1 skipped; locations 2254 passed; inventory 2144 passed / 1 skipped;
      battle-pass 172 passed; dungeon (CI args, `--timeout=30`) exit 0
- [x] `bash scripts/check_econ_copies.sh` — PASS (all copies identical)
- [x] alembic `036_econ_guild_orders`: downgrade -1 → upgrade head → upgrade head (no-op) — PASS
- [x] `docker compose config` — PASS
- [x] Flaky `test_econ_bank.py::test_step_random_worlds_guarantees`: 10 consecutive runs of the file green + green in the
      full suite. The test is a pure function with a fixed RNG seed; the reported failure line (~615) is inside the
      profit-sweep asserts that the bank-fix agent was editing at that moment → explained by the concurrent edit. The LOW
      entry QA added to `docs/ISSUES.md` was removed.

#### Live Verification Results (Chrome, localhost, admin + character «Ашари» 763)
- Admin «Экономика → Гильдия»: renders (totals, params, regions with «нет представителя» warnings, orders list with
  tabs/filters); params save (`guild_min_order_value` 50 → 40 → read back 40). Admin «Банки»: «прибыль отдана в казну»
  stat + new intro text shown.
- Created a temporary NPC with role «Гильдия торговцев» in loc. 197 (region 9 Мэттанхейм), lowered potions stock to 150,
  manual recount → one open order `potions` 288.265 units (= 455 − 166.735), price ×2.008, budgets set for all 5 regions.
- Player modal: orders with progress, offers with prices / «цена ограничена ценами торговцев» / XP preview; two hand-ins
  (mana ×5, health ×3) — wallet 18 366 → 18 786, bag, order progress (2 %), XP 29 735 → +39, ledger `guild_order`
  postings `population_purse → character`; refusal (off-market item) → 400 Russian text.
- Region card: «📜 Гильдия ищет: зелья».
- Mobile 360px (iframe): guild modal and admin guild tab — no horizontal overflow.
- Console errors: NONE; all `/characters/...` requests 200.
- Dev state restored: test NPC deleted, temporary action gate deleted, guild params removed from the sim JSON (defaults),
  potions stock restored, the test order closed. The four test hand-ins (items/marks/XP of «Ашари») stay in the dev DB.

#### Non-blocking notes (no change required)
| # | File:line | Note |
|---|-----------|------|
| 1 | `services/character-service/app/economy_guild_crud.py:665-690` | Hand-in locks `econ_guild_xp_days` AFTER `character_inventory`, while 3.7 / the module docstring put it before. No deadlock possible today (the XP row of a character is only locked by hand-ins, already serialized by the region lock; the sweep locks regions first), but the docstring and code disagree — align on the next touch. |
| 2 | `economy_api.py` `_guild_commit` / `economy_guild_crud.hand_in` | The XP day row is ensured for `today_utc()` and the hand-in computes its own `now`: a request crossing UTC midnight gets 0 XP (logged warning). Negligible. |

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-01 — PM: фича создана, требования согласованы с пользователем, запускаю анализ кодовой базы
[LOG] 2026-11-01 22:41 — Analyst: анализ завершён — вся логика в character-service (+ копии econ_core ×3 из-за нового типа операции), фронтенд: роль, окно гильдии, строка в карточке, админка. Найден арбитраж с торговцами НПС (купить у торговца → сдать в гильдию +20 %), нужны решения пользователя (вопросы в разделе 2)
[LOG] 2026-11-01 23:06 — Architect: спроектировано 11 задач, 3 новых эндпоинта + поле в карточке региона; заказы пересчитываются внутри шага региона, бюджет гильдии хранится в econ_regions, цена по правке PM: не ниже скупки торговцев и не выше floor(самой дешёвой цены × 0,5); формулы лавки переносятся в econ_core (locations — без изменения поведения); миграция 036_econ_guild_orders
[LOG] 2026-11-01 23:20 — Architect: по просьбе PM добавлен опыт за сдачу в гильдию: 10 % от марок (5 % за товары, которые продают торговцы региона), дневной лимит 200 базового опыта на персонажа, книга опыта квестов, в той же транзакции и с тем же request_id
[LOG] 2026-11-01 23:40 — Backend Dev: задача #1 завершена — тип операции guild_order и формулы лавки перенесены в econ_core (копии ×4 сверены скриптом), locations-service теперь вызывает их, все 2254 теста locations зелёные
[LOG] 2026-11-02 00:10 — Backend Dev: задача #2 завершена — миграция 036_econ_guild_orders (upgrade → downgrade → upgrade и повторный запуск проверены в контейнере), модели, 9 параметров, чистый модуль econ_guild.py
[LOG] 2026-11-02 00:40 — Backend Dev: задача #3 завершена — economy_guild_crud.py, шаг гильдии в тике (SAVEPOINT в конце шага региона) и уборка; на dev ручной пересчёт открыл заказы, второй обновил их без дублей, третий закрыл
[LOG] 2026-11-02 00:55 — Backend Dev: задача #4 завершена — 3 эндпоинта; сдача проверена на dev MySQL (с откатом): частичный приём, заказ выполнен, марки, опыт с книгой, повтор request_id → 409 «Операция уже выполнена»; фильтр «closed» в админке включает выполненные
[LOG] 2026-11-02 01:05 — Backend Dev: задача #5 завершена — документация character/locations/inventory/battle-pass обновлена (ARCHITECTURE.md экономику не перечисляет — без изменений)
[LOG] 2026-11-02 — PM: по данным прода (стартовый капитал банков забрал казны целиком → жалованье 0) пользователь одобрил два исправления банков в рамках этой выкатки: стартовый капитал только из излишка казны сверх treasury_target; чистый процентный доход банка каждый пересчёт уходит в казну (bank_profit_to_treasury_share=1.0). Сделано отдельным агентом (econ_bank.py, economy_bank_crud.py, тесты банков, админка банков). На проде капитал 14 банков возвращён в казны вручную (ops 1984–1997).
[LOG] 2026-11-02 — QA: задача #8 завершена — test_econ_guild.py (3217 тестов, вкл. перебор цен: гильдия никогда не платит меньше скупки торговца и не выше floor(цена×0,5); бюджет не превышается), +3 теста guild_order в battle-pass test_gold_missions.py; контрактные кейсы уже были, прогнаны в inventory/locations/dungeon, check_econ_copies.sh — ок
[LOG] 2026-11-02 — QA: задача #9 завершена — test_econ_tick_guild.py (25 тестов): порог, объём минус караваны, обновление без дублей, закрытия no_shortage/no_money/disabled, новый заказ после выполненного, бюджеты, повтор прогона, уборка, откат только шага гильдии
[LOG] 2026-11-02 — QA: задача #10 завершена — test_econ_guild_api.py (79) и test_econ_guild_admin_api.py (41): порядок проверок, сдача/частичная/выполнен, отказы, потолок и пол цены через торговцев (живой/легаси/мёртвый/чужой регион/перепродажа), идемпотентность, откаты, опыт 10 %/5 %, дневной лимит, книга, левел-ап, безопасность (401/403/422, инъекции, XSS), админка и карточка региона. Багов в реализации не найдено; полный прогон character-service 7056 passed, battle-pass 172 passed
[LOG] 2026-11-02 — QA: замечен нестабильный тест test_econ_bank.py::test_step_random_worlds_guarantees (упал в одном полном прогоне, отдельно и во втором полном прогоне зелёный) — к гильдии не относится
[LOG] 2026-11-02 00:15 — Reviewer: начал проверку (гильдия + две правки банков)
[LOG] 2026-11-02 00:15 — Reviewer: нестабильность test_step_random_worlds_guarantees объяснена параллельной правкой файла (10 прогонов подряд и полный набор зелёные), запись удалена из ISSUES.md
[LOG] 2026-11-02 00:15 — Reviewer: проверка завершена, результат PASS — все тесты, tsc/build, копии econ_core, миграция 036 вниз/вверх зелёные; вживую открыт заказ на зелья, две сдачи (марки, опыт, прогресс заказа), строка «Гильдия ищет: зелья», вкладки «Гильдия» и «Банки» в админке, без ошибок в консоли; тестовые настройки на dev возвращены
[LOG] 2026-11-02 — PM: фича закрыта (DONE), отчёт пользователю
```

## 7. Completion Summary (filled by PM on completion — in Russian)

**Сделано (2026-11-02):**
- Регионы с нехваткой (запас ниже 80 % нормы, за вычетом караванов в пути) выставляют заказы в гильдии торговцев; заказ
  обновляется каждый пересчёт и закрывается сам.
- Новая роль НПС «Гильдия торговцев»: игрок сдаёт «чистые» стопки предметов группы, получает марки из кошелька жителей
  (еду при нехватке доплачивает казна) и опыт: 10 % от марок, 5 % за предметы, которые продают торговцы региона;
  дневной лимит 200 базового опыта.
- Цена: местная цена +20 %, но не выше дешевейшей покупки у торговцев региона с полной скидкой и не ниже их закупочной
  цены — перепродажа «купил → сдал» не приносит денег.
- Гильдия тратит за пересчёт не больше 25 % кошелька жителей; новых денег не создаёт; марки идут в боевой пропуск.
- Строчка «Гильдия ищет: …» в карточке региона, вкладка «Гильдия» в админке, раздел гайда, 9 настроек.
- Банки (по данным прода): стартовый капитал — только из излишка казны сверх запаса; прибыль банка каждый пересчёт
  уходит в казну. На проде капитал 14 банков вручную возвращён в казны.
- Миграция character 036. Ревью PASS, проверено вживую.

**После выкатки:** назначить роль «Гильдия торговцев» нужным НПС в регионах; заказы откроются сами в первом пересчёте,
где у региона есть нехватка.
