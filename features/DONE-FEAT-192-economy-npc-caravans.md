# FEAT-192: Экономика, этап 5б — караваны НПС

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-01 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Продолжение экономики: FEAT-181 (книга счетов), FEAT-182 (живые регионы), FEAT-183 (торговцы НПС), FEAT-184 (банки),
FEAT-186 (масштаб населения), FEAT-187 (события регионов), FEAT-191 (монетный двор и квота). Этап 5: 5а — монетный
двор (готово), **5б (эта) — караваны НПС**, 5в — заказы через гильдию торговцев.

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас товары между регионами не перемещаются: регион с хроническим дефицитом так и живёт с высокими ценами, а у
соседа тот же товар лежит излишком и дешевеет (FEAT-182, «выравнивание цен — этап 5»). Караваны НПС возят товары
из регионов, где их много и они дешёвые, туда, где их мало и они дорогие, — и тем самым выравнивают запасы и цены.
Деньги по-прежнему движутся только проводками книги счетов.

### Бизнес-правила (согласовано с пользователем 2026-11-01)
- **Внутри страны** караваны ходят между участвующими в пересчёте регионами всегда.
- **Между странами** — только если админ разрешил торговлю для этой пары стран (не все страны торгуют друг с
  другом). По умолчанию — запрещено.
- Караваны работают в 6-часовом пересчёте, как остальная экономика.
- Видимость для игроков по умолчанию — цифры в карточке региона (без отдельной ленты новостей: мировые события
  позже пойдут в газету, историю храним).

### Решения пользователя (2026-11-01, «всё как предлагаешь»)
1. **Время в пути:** внутри страны караван идёт 1 пересчёт, между странами — 2. Пока едет — товар «в пути» (ни у
   кого), игроки видят «в пути».
2. **Кто платит:** жители покупателя (кошелёк населения) платят жителям продавца, без посредника. Если жителям не
   хватает денег на **продовольствие**, недостающее доплачивает казна региона-покупателя.
3. **Пошлина между странами:** % задаётся для каждой пары стран вместе с разрешением торговли, по умолчанию 10 %;
   идёт в казну страны-покупателя. Внутри страны пошлины нет.
4. **Объём:** за пересчёт караван вывозит не больше X % излишка продавца (настройка, по умолчанию 25 %) и не больше,
   чем покупателю нужно до нормы. У продавца всегда остаётся не меньше нормы.
5. **Товары:** все 12 групп.
6. **Маршруты:** внутри страны — между любыми регионами, участвующими в пересчёте (не только соседями); между
   странами — любые регионы разрешённых пар.
7. **Риски:** караваны пока всегда доходят. «Набег» и «Бунт» в регионе останавливают его караваны (как торговцев).
   Грабёж/охрана игроками — потом.
8. **Видимость игрокам:** словами в карточке региона («караваны везут продовольствие из Х», «вывозят руду в Y»), без
   цифр — как вся карточка. Цифры — в админке, новая вкладка «Караваны».
9. **Разрешение торговли:** одна галочка на пару стран, в обе стороны (+ % пошлины). Блокады регионов и эмбарго
   отдельных товаров — потом.
10. **Руда в столицы** и рост чеканки двора — так задумано, не ограничивать.
11. **Ручной пересчёт:** караваны ходят и при «Пересчитать сейчас», не только по расписанию.

### UX / Пользовательский сценарий
1. Игрок открывает карточку региона: видит строки про караваны — что везут сюда и откуда, что вывозят и куда, что в пути.
2. Админ во вкладке «Экономика → Караваны»: таблица пар стран (галочка «торгуют» + % пошлины), список караванов
   в пути и последних доставок с цифрами, параметры (доля излишка и т.п.), раздел и шаг чек-листа в гайде.

### Edge Cases
- Регион перестал участвовать / удалён, пока караван в пути → товар не теряется молча: доставка отменяется,
  деньги/товар корректно возвращаются (решит архитектор, главное — сумма мира 0 и без потерь).
- Админ запретил торговлю пары, пока караван в пути → уже идущий караван доезжает.
- Повторный/возобновлённый пересчёт не отправляет и не доставляет караван дважды (идемпотентность).
- В регионе «Набег»/«Бунт» → его караваны не отправляются (идущие доезжают).
- Жителям и казне не хватает денег на продовольствие → везут столько, сколько могут оплатить.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Paths below are relative to `services/character-service/app/` unless stated otherwise.

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | new pure math module (caravan step), new tick pass, new table(s) for country-pair trade + caravan log, admin API, card field, sim params, Alembic `035_*` | `econ_tick.py`, `econ_sim.py` (params), new `econ_caravan.py` (pure) + crud, `economy_api.py`, `schemas.py`, `models.py`, `economy_sim_crud.py` (`region_card`), `alembic/versions/` |
| character / inventory / locations / dungeon (econ_core copies) | **only if** a new op type / account kind is needed — byte-identical copies ×4, CI `scripts/check_econ_copies.sh` | `econ_core.py` ×4 |
| frontend | admin tab/section, guide section + checklist step, region card line, op-type label | `components/Admin/EconomyPage/*`, `components/WorldPage/RegionEconomyCard.tsx`, `api/regionEconomy.ts`, `api/economyAdmin.ts`, `types/economy.ts` |
| locations-service | **none expected** — its tables (`Regions`, `Countries`, `region_transition_arrows`) are read by raw SQL from character-service, as FEAT-187 already does | — |
| user-service | none if existing `economy:read` / `economy:settings` suffice (see 6) | — |

### Existing Patterns
- character-service: sync SQLAlchemy, Pydantic v1, Alembic present (`alembic_version_character`, head **`034_econ_mint`**, `alembic/versions/034_econ_mint.py:24`; local DB confirmed at `034_econ_mint`).
- Economy = "pure math module + tick runner that only loads / stores / posts": `econ_sim.py` (regions), `econ_merchant.py` (merchants), `econ_events.py` (events), `econ_mint.py`, `econ_bank.py`; runner `econ_tick.py`. Each new mechanic so far = pure module + one pass in `run_tick` + `RunSummary` counters + error prefix in `econ_tick_runs.error` + admin tab + guide section.
- Tables owned by locations-service are read with raw `text()` SQL and guarded by table-existence checks for SQLite tests (`economy_events_crud.py:155-182`).
- Sim tunables live in one JSON row `econ_sim_settings.params` → `econ_sim.SimParams` dataclass (`econ_sim.py:60-160`, `from_mapping` ignores unknown keys, so new params need no migration); admin edits them in «Настройки/Пересчёт» with hints in `paramHints.ts`.
- Per-country admin settings without FK precedent: `econ_mints` (`models.py:922-932`, `country_id` PK, no FK to `Countries`).

---

### 1. Region goods model and the tick

**Tables** (`models.py`):
- `econ_goods_groups` (`:534-546`) — 12 global groups: `base_price`, `norm_per_1000`, `norm_days`, elasticities, `is_food`. Seed `alembic/versions/028_econ_living_regions.py:46-57`: food(2), ore_metal(10), wood(5), herbs(8), hides_textiles(10), magic(40), weapons(120), armor(100), jewelry(200), potions(30), tools(40), household(80) (base prices in brackets).
- `econ_group_inputs` (`:549-559`) — production chains (processed groups eat raw ones).
- `econ_region_templates` / `econ_template_goods` (`:562-591`) — 8 templates: `capital, port, mining, agrarian, forest, magic, fortress, rural` (`028:74-88`).
- `econ_regions` (`:594-618`) — per region: `template_code`, lore `population`, `tax_rate`, stability, prosperity, hunger, satisfaction, `last_*` money numbers, `last_run_id` (tick idempotency guard), `low_stability_since`.
- `econ_region_goods` (`:621-640`) — PK (region_id, group_code): `production_per_1000`, `consumption_mult`, **`stock` Numeric(16,3)** (abstract float units, not items), `norm_stock`, `price_mult`, `prev_price_mult`, `last_produced/consumed/demand/spoiled`.
- `econ_region_history` (`:666-689`) — one row per region per run, `goods` JSON `{code: {stock, price_mult, produced, consumed}}`.
- Participation: `template_code IS NOT NULL AND population > 0` and the `Regions` row exists (`econ_tick.py:315-325`).

**Per-tick math** — `econ_sim.simulate_region` (`econ_sim.py:430-...`), one region, pure:
1. multipliers (stability, hunger); 2–3. production (raw first, processed limited by input stocks, inputs consumed) — `production_per_1000 × pop/1000 × m × e_g × dt`, `dt = 0.25` day;
4. demand `demand_tick` (`:310-322`) — norm × consumption_mult × pop × prosperity factor × `price_mult^(-price_elasticity)` × dt;
5. consumption = `min(stock, demand × affordability)`, affordability from population purse vs. cost/day; hunger from food;
6. `norm_stock = norm_days × (household demand/day + input use/day)` (`:287-307`); **stock cap = `stock_cap_mult (3.0) × norm`, excess is spoiled** (`last_spoiled`);
7. **price**: `price_mult = clamp((stock/norm)^(-0.631), 0.5, 3.0)` (`price_mult`, `:260-267`; params `price_exponent/price_min/price_max`, `:63-67`); then event `price` mods multiply it (stored value includes event mods!);
8. money: `income = Σ produced × base_price × price_mult`; `tax = min(purse, income × tax_rate)`; wages; 9–10. stability/prosperity.
- Population used in math = lore / `population_scale` (100) (`sim_population`, `:270-279`).
- Card thresholds: shortage `price_mult ≥ 1.6`, surplus `≤ 0.7` (`SHORTAGE_MULT/SURPLUS_MULT`, `econ_sim.py:49-50`); per-group levels `:45-48`.
- So "surplus/cheap" vs "deficit/expensive" is fully expressed by `stock/norm_stock` (or `price_mult`). Note: stock above 3×norm is destroyed each tick — a natural source for caravans. Goods consumption itself does **not** move money (only affordability gates it); money moves only via tax/wages/grant.

**Tick runner** — `econ_tick.run_tick` (`econ_tick.py:1122-1274`), order:
1. claim run (`_claim_auto` slot = floor(unix/21600) UNIQUE, or `_claim_manual` slot NULL) + grant plan (`:1147-1160`);
2. `_prepare_merchants` (`:1167`);
3. `_events_pass` (`:1169`) — expiry always; random rolls / spreading / chains / riots **only in scheduled runs** (slot set);
4. `_quota_pass` (`:1173`) — season quota emission → region treasuries;
5. **region loop** (`:1177-1201`) — `_process_region` (`:658-878`), one transaction per region: `econ_regions` FOR UPDATE (skip if `last_run_id == run_id`) → goods rows FOR UPDATE → active events FOR UPDATE + one-shots → merchant rows → `simulate_region` → rows updated → `region_tick` posting (key `region_tick:<run>:r:<region>`) → event expense ops → merchant SAVEPOINT (`merchant_trade` op, stock deltas) → history row → COMMIT;
6. `_mint_pass` (`:1204`) — per country: capital `econ_regions` → capital `econ_region_goods('ore_metal')` → `econ_mint_seasons` (`economy_mint_crud.lock_capital`, `:317`), ore above threshold removed from stock → `mint_court` op;
7. `_prepare_banks` / `_bank_pass` / `_collection_pass` (`:1207-1214`);
8. run row finalised; `error` built from prefixes (`:1223-1240`, prefixes `:111-118`); `purge_old`.
- **Global lock order** (docstring `econ_tick.py:53-63`, FEAT-191 3.12): `econ_regions → econ_region_goods → econ_region_events (asc id) → econ_mint_seasons → npc_shop_items (asc id) → econ_banks (asc region_id) → bank_deposits → bank_loans → character_inventory → characters → econ_accounts (asc id, done by post_operation)`. Every existing transaction locks **one** region; a caravan transaction would be the first to lock **two** regions → needs a rule "econ_regions ascending region_id, then their goods rows ascending (region_id, group_code)". Within one process runs are serial (only one live run, `RunInProgress`), and locations/inventory/dungeon only *read* `econ_regions/econ_region_goods` without locks (`econ_core.py:971-982`), so deadlock exposure is limited to admin PUTs (`economy_sim_crud.update_region`) and mint (single region).

**Where a caravan step can slot in** (facts for the Architect, not a decision):
- (a) **after the region loop, before the mint pass** — stocks/norms/prices are fresh for this run (same reasoning the mint uses, comment at `:1203`); but stored `price_mult` and the history row already written for this run would be stale until next run unless the pass recomputes `price_mult` with `econ_sim.price_mult` and patches/ignores history. Caravans moving `ore_metal` into a capital before the mint pass would feed the court mint (interaction with FEAT-191 R2 "auto-mint idle because capitals import ore").
- (b) **before the region loop** (after quota) — the region step then computes prices/consumption on the post-caravan stock naturally (no stale price), but decisions use previous-run prices/norms.
- (c) inside `_process_region` — not suitable: touches two regions, breaks the one-region-per-transaction design and `last_run_id` guard.
- Idempotency: region step uses `last_run_id`; merchants rely on the ledger UNIQUE key inside the same transaction (a `DuplicateOperation` rolls the goods deltas back, `:836-839`). A caravan that moves goods **without** money would have no ledger key → needs its own marker (e.g. UNIQUE `(run_id, …)` row). Manual runs (`slot NULL`) are real extra steps — decide whether caravans run in them (events don't roll there).
- Merchants also pull from region stock (`merchant_take_share` 0.25 of a group per tick, `econ_sim.py:102`, applied in `_merchant_step` `econ_tick.py:520-575`) — caravans compete for the same stock.

### 2. Money side

**Account kinds** (`econ_core.py:40-93`): `character`, `region_treasury` (ref region), `country_treasury` (ref country), `world_treasury`, `auction_escrow`, `auction_storage`, `emission`, `adjustment`, `population_purse` (ref region), `bank`, `bank_deposits` (ref region). Merchant cash = NPC **character** balance (`characters.currency_balance`). Negative allowed only for treasuries + sources (`:78-80`). `econ_accounts.kind` is VARCHAR(32), UNIQUE(kind, ref_id) (`models.py:458-474`) → a new account kind needs no DDL, but needs `econ_core` changes (×4 copies) and summary handling (`economy_crud.py:28-36, ~172` enumerates region kinds).
- **Tax rule**: any inflow into a `region_treasury` from `TAX_SOURCE_KINDS = {character, auction_*, population_purse, bank_deposits}` automatically gets a `region → country` tax leg of `country_tax_rate` (default 0.1) (`econ_core.py:87-90, 506-541`). `region_treasury → region_treasury` and `purse → purse` legs are **not** taxed.
- **Op types**: `OP_TYPES` (`econ_core.py:146-154`) is a closed frozenset validated in `validate_operation` (`:470`); `op_type` column is free VARCHAR(50) (`models.py:481`) → a new op (e.g. `caravan_trade`) = edit `econ_core.py` + copy ×4 (CI check), no migration. Operations may not touch `emission/adjustment` unless in `SOURCE_OP_TYPES` (`:157, 498`) — caravans must not create money.
- Frontend op label map `components/Admin/EconomyPage/economyLabels.ts:4-47` (`OP_TYPE_LABELS`) needs the new type.
- **How goods "belong"**: region stock is effectively owned by the residents — merchants pay the **population purse** wholesale when they take stock (`econ_merchant.py` docstring `:1-22`). Natural money postings for a caravan therefore: buyer region's purse (or treasury) → seller region's purse, plus optional duty/tariff legs → region/country treasury; if a carrier account (caravan owner) exists, legs go purse(A) → carrier → purse(B). Purse can't go negative (not in `NEGATIVE_ALLOWED_KINDS`) → buyer purse budget caps volume; `InsufficientFunds` must be avoided by computing amounts from locked balances (merchant step pattern).
- **World invariant**: Σ all balances = 0 (`econ_core.py` docstring `:24-27`); money only created from `emission/adjustment`. Any caravan posting between existing accounts keeps it; a pure goods transfer with no money also keeps it. Covered by `tests/test_econ_*` invariant assertions and the «Сводка» check.

### 3. Geography

- Hierarchy (locations-service `app/models.py`): `Areas` (`:14-25`) → `Countries` (`:28-48`, `area_id`, `x/y` on the area map) → `Regions` (`:51-75`, `country_id` NOT NULL CASCADE, `x/y` on the country map, `entrance_location_id`) → `Districts` → `Locations`. Two areas exist locally (country 11 is in area 2) — possibly separate continents/sea.
- **Region adjacency exists**: `region_transition_arrows` (`locations-service/app/models.py:604-614`, `region_id → target_region_id`, usually paired both ways) + `arrow_neighbors` (`:617-624`, location↔arrow with `energy_cost`). FEAT-187 already builds a region graph from it: `economy_events_crud.neighbour_map` (`:155-182`) — arrows both ways, fallback to "all participating regions of the same country" **only when a region has no arrows at all**, then filtered to participating regions.
- Location-level graph: `LocationNeighbors` (`:158-166`, `energy_cost`, `path_data`) incl. cross-region links (12 cross-region pairs locally; `Locations.region_id` is NULL for district locations → region resolution needs District join). Could yield an energy-cost distance, but heavy.
- **Coordinates are unusable for distance**: local DB has `Regions.x/y = 1,1` for almost all regions and `Countries.x/y = NULL`; region x/y are relative to each country's own map, not comparable across countries.
- **Local data facts** (local seed is stale per project memory; prod is the lore source — verify there): 34 arrows across 14 regions, **0 cross-country arrows**; participating regions: country 6 → 9 (capital, 2.5M), 10 (rural), 34 (agrarian); country 7 → 14 (mining), 15 (fortress). Region 9's only arrows go to non-participating region 11, so `neighbour_map` gives the capital **zero** participating neighbours (no fallback since it has arrows). An "only neighbours" rule built on the FEAT-187 helper would isolate it; a graph walk through non-participating regions, or "any region in the country", avoids that.
- **Hubs**: no generic hub/port flag. Available: template codes `capital`/`port` (`028:74-76`) and the per-country effective capital — `economy_mint_crud.resolve_capital` / `capital_of` (`:192-212`, override `econ_mints.capital_region_id`, else the single `capital`-template region). Could serve as the country's trade hub for inter-country routes.

### 4. Event interactions (FEAT-187)

- Effect types (`econ_events.py:40-77`): per-step `production, consumption, labor, price, tax_income, stability, prosperity, merchants_halt, bank_panic, loan_boom`; one-shot `stock_loss, treasury_expense, population`. Aggregation `aggregate` (`:178-243`); `merchant_params` turns `merchants_halt` into `merchant_take_share = 0` (`:246-250`).
- Seeded templates (`alembic/versions/033_econ_region_events.py:46-270`): drought, flood, plague, magic_disaster, mine_collapse, livestock, **raid** (stock_loss food/weapons/ore + `merchants_halt`), **riot** (`merchants_halt`), harvest, magic_anomaly (price ×0.85 magic), rich_vein, **fair** (price ×0.9 household/jewelry), festival (country scope), good_catch.
- There is **no "trade blocked/caravans" effect** today; `merchants_halt` is the closest (raid, riot). Options: reuse `merchants_halt` for caravans, or add a new effect type (`caravans_halt`) — new type = edit `EFFECT_TYPES/EFFECT_FIELDS`, schema validation, `EventEffectsBuilder.tsx`/`eventLabels.ts`.
- Event `price` mods are baked into stored `price_mult` (`econ_sim.py` step 7 tail). A caravan deciding by `price_mult` would chase a fair's discount or flee a magic anomaly; deciding by `stock/norm_stock` ignores event price mods. Famine-type events (drought, livestock) reduce food production → food deficit → caravans would naturally ship food in (desired relief behaviour). `stock_loss` one-shots are applied inside the region transaction before simulate.
- Spreading events already use the `neighbour_map` graph — a shared region graph helper would serve both.

### 5. Frontend

- Player card: `components/WorldPage/RegionEconomyCard.tsx` (214 lines, Tailwind/TS, used in `WorldPage.tsx:36`), API `api/regionEconomy.ts` (`RegionCardData`, optional fields `has_bank`, `has_mint`, `events` — pattern for an optional `caravans?` field). Backend `economy_sim_crud.region_card` (`:831-855`) via `GET /characters/economy/regions/{id}/card` (`economy_api.py:259-262`). **Contract: the player card is qualitative only — "no balances, no raw stock/price numbers"** (`economy_api.py:261`, `regionEconomy.ts:3-6`, card header comment `RegionEconomyCard.tsx:12`). The brief says «цифры в карточке региона» → conflicts with this rule (see business question B9).
- Admin page `components/Admin/EconomyPage/EconomyPage.tsx`: tabs `guide, summary, journal, actions, regions, goods, items, templates, merchants, banks, events, mint, tick, settings` (`TAB_LABEL :30-45`, render `:192-227`, intros `TAB_INTRO :51+`); tab ids also in `guideSections.ts` (`EconomyTabId`). A new tab «Караваны» (or a section in «Регионы»/«Монетный двор»-style per-country table) would hold: country-pair trade matrix (per-country rows like `EconomyMint.tsx`), last caravans list, counters. Run counters per run are shown in `EconomyTick.tsx` (via `economy_sim_crud._run_dict` `:771-788`, `_run_ops :764`).
- Region admin editor `RegionEconomyEditor.tsx` shows raw goods numbers — place for per-region "imported/exported last run".
- Guide: `EconomyGuide.tsx` (1393 lines) — checklist `Section id="checklist"` (`:724-816`, step list), sections `overview … mint` (`:817-1195`), recipes (`:1196+`); section ids/titles in `guideSections.ts` (`GUIDE_SECTION_IDS`, `GUIDE_SECTION_TITLE`) — add `caravans` (+ maybe `recipe-caravans`). Param hints `paramHints.ts` for new `SimParams`.

### 6. Alembic and RBAC

- character-service Alembic head: **`034_econ_mint`** (down `033_econ_region_events`); next would be `035_…` (revision id ≤ 32 chars, MySQL gotchas: FK indexes, see memory). Tables owned by locations-service must not get FKs (pattern: no FK, like `econ_mints`).
- Likely DB changes: country-pair trade table (e.g. pair `(country_a, country_b)` normalised a<b, `is_enabled`, optional tariff/limits, `updated_by/at`); a caravan log table (run_id, from/to region, group, units, value, status) — doubles as idempotency marker and history for the future «газета»; possibly new `SimParams` keys (no DDL).
- RBAC: user-service migration `0032_add_economy_permissions.py` defines `economy:read`, `economy:emit`, `economy:adjust`, `economy:settings` (test seed `user-service/tests/test_rbac_permissions.py:1300-1311`). Reads → `economy:read`, settings → `economy:settings`; no new permission needed unless the user wants a separate one (then CLAUDE.md §10.13 rule: migration + explicit test section).

### Cross-Service Dependencies
- character-service reads `Regions`, `Countries`, `region_transition_arrows` (locations-service tables) via SQL — no HTTP. Renames there would break caravans (same as events/mint today).
- `econ_core.py` copies ×4 (character/inventory/locations/dungeon) if op type / account kind added; CI job `econ-contract-copies`.
- No RabbitMQ / Redis involvement.

### Risks
- **Two-region transactions** — new lock pattern; must define ascending-id lock order and keep the region/mint/bank passes single-region → Mitigation: own pass with own transactions, lock both `econ_regions` rows in id order.
- **Oscillation / ping-pong** — moving too much flips surplus/deficit each tick (prices swing 0.5↔3.0) → cap volume (share of surplus above norm, share of deficit gap) and require a price/stock gap threshold.
- **Stale price/history** if the pass runs after the region loop → recompute `price_mult` for touched goods, decide what history shows.
- **Idempotency of goods-only moves** (no ledger key) on resumed runs → marker table with UNIQUE key per (run, route/group).
- **Purse cannot go negative** → amounts from locked balances; poor deficit regions (hungry, empty purse) can't buy → caravans won't relieve famine unless someone else pays (treasury/country) — business choice.
- **Graph sparsity** — arrows missing/one-sided; participating regions connected only via non-participating ones (local capital 9). Prod data unknown.
- **Perf** — N regions × 12 groups × pairs; fine for current scale (5 participating locally), but pair enumeration should be bounded (top-k routes).
- **Mint interaction** — ore shipped into capitals feeds the court mint (money creation) — may be desired, but tune.
- **econ_core copy drift** if an op type is added (CI catches).
- `docs/ISSUES.md:990` "no inter-region goods exchange until caravans" should be closed by this feature.

### Open technical questions for the Architect
1. Pass placement: before vs after the region loop (stale price/history vs previous-run signals); run in manual runs or scheduled only.
2. Decision signal: `stock/norm_stock` (ignores event price mods) vs stored `price_mult` (includes them).
3. Route model: complete graph within a country vs `region_transition_arrows` graph (with walk through non-participating regions, reusing/extracting `neighbour_map`); inter-country via capitals/hubs or any pair of regions.
4. Money: who pays whom (purse↔purse, treasury, carrier account); new op type `caravan_trade` (econ_core ×4) vs reuse; new account kind or not.
5. Idempotency + log table shape; retention (history purge like `purge_old`).
6. Event hook: reuse `merchants_halt` vs new `caravans_halt` effect.
7. Mint ordering (caravans before mint feeds ore to capitals).

### BUSINESS questions for the user (via PM)
- **B1. Travel time:** goods arrive instantly in the same 6 h recount, or caravans travel N recounts (in transit goods visible as «в пути»)? If travel time — by distance (neighbours = 1 recount, further = more) or fixed?
- **B2. Who owns the caravan and its profit:** (a) no owner — residents of the buying region pay residents of the selling region at a price between the two markets (pure transfer, no middleman); (b) a merchant guild / carrier earns the margin (where does that money go — region treasury, country treasury, a guild account, the NPC merchants of the origin region?).
- **B3. Who pays in the deficit region:** residents' purse (poor hungry regions can't afford relief) or the region treasury / country treasury may pay for food deliveries (relief)?
- **B4. Duties/tariffs between countries:** none, a fixed % for every enabled pair, or per-pair % set by the admin? Who receives it — exporter's country, importer's country, both? And domestic trade — untaxed or taxed like other region income?
- **B5. Volume caps:** how much may move per recount — a share of the surplus/deficit (e.g. up to 25 %), an absolute cap per route, a global cap? Should caravans leave the origin at least at norm (never create a shortage at home)?
- **B6. Which goods:** all 12 groups, or exclude some (e.g. food only inside a country, magic only to/from magic regions)? Should processed goods (weapons, jewelry) travel as well as raw?
- **B7. Routes:** inside a country — any region to any region, or only neighbours along the map (transition arrows), possibly through several regions? Between countries — any pair of regions, or only via capitals/border regions/ports?
- **B8. Risk/losses:** can caravans be robbed/lost (random chance, higher in regions with «Набег»/«Бунт», low stability, dangerous roads), and do events stop caravans (raid/riot like they stop merchants)? Is there a future hook for players (guarding caravans, robbing)?
- **B9. Visibility:** the player region card is currently words-only by design (no numbers). Show caravans as words («Караваны привезли продовольствие из Бриндлсвуда», «Вывоз: руда») or real numbers (units/marks)? Admin side — a list of last caravans per run + per-country-pair settings in a new «Караваны» tab, OK?
- **B10. Trade-pair settings:** pair is symmetric (A↔B one switch) or directional (A may sell to B but not buy)? Can the admin also forbid trade **inside** a country or for a specific region (blockade), or embargo a specific goods group between two countries?
- **B11. Mint interaction:** caravans bringing ore to capitals will feed the court mint (more marks minted). Desired?
- **B12. Manual «Пересчитать сейчас»:** should caravans run in manual recounts too, or only in the scheduled 6 h ones (like random events)?

---

## 3. Architecture Decision (filled by Architect — in English)

All backend work is in **character-service** (sync SQLAlchemy). Other backend services only get the byte copy of
`econ_core.py` + `tests/econ_contract_cases.py`. No locations-/inventory-/user-service migration, no new RBAC
permission, no Nginx/Docker change. CS = `services/character-service/app`.

The user's 11 decisions in section 1 are final; the decisions below only fill the technical gaps.

### 3.1 Module layout

| Module | Kind | Content |
|---|---|---|
| `CS/econ_core.py` (canonical, byte-copied ×3) | constants + account kind | 3 op types + 1 singleton account kind `caravan_escrow` (3.4). Nothing else. |
| `CS/econ_caravan.py` (new) | pure, no DB | routes (3.3), matching / planning (3.5), price + duty math (3.6), re-clamp at execution (3.7). |
| `CS/economy_caravan_crud.py` (new) | DB | snapshot loading, dispatch + arrival executors (3.7/3.8), pairs read/write, admin lists, card lines, escrow sub-invariant. Pattern: `economy_mint_crud.py`. |
| `CS/econ_tick.py` | DB | `_caravan_pass` (3.2), `RunSummary` counters, `CARAVAN_ERROR_PREFIX`, final log line, lock-order docstring (3.9). |
| `CS/economy_api.py` | router | admin endpoints (3.11). |
| `CS/econ_sim.py` | params | new `SimParams` fields (3.10). |
| `CS/economy_crud.py` | DB | summary: escrow total + sub-invariant; `ADJUST_FORBIDDEN_KINDS` += `caravan_escrow`. |
| `CS/economy_sim_crud.py` | DB | `region_card` gets `caravans` in both shapes (3.12). |
| `CS/models.py`, `CS/schemas.py` | ORM / Pydantic v1 | 2 tables, schemas, `ECON_SIM_PARAM_BOUNDS` / `ECON_SIM_INT_PARAMS` entries, summary fields. |
| `CS/alembic/versions/035_econ_caravans.py` | migration | revision id `035_econ_caravans` (17 chars), down `034_econ_mint`. |

### 3.2 Where the pass runs and the caravan lifecycle

**Placement: one `_caravan_pass(session_factory, run_id, summary, params, start, groups, active_map)` right after
`_quota_pass` and before the region loop** (analyst option (b)). Order inside the pass: **arrivals first, then
dispatches.** Reasons:
- The region step then computes consumption, spoilage and `price_mult` on the post-caravan stock in the same run —
  no stale `price_mult`, no history row to patch (option (a) would leave both stale for a whole run).
- Decision inputs are the live `stock` (current state) and the `norm_stock` / `price_mult` stored by the previous
  run — exactly what the admin and the player card show right now. Previous-run norms are a fine signal (they move
  slowly).
- Arrivals before dispatches: the buyer's stock already contains what arrived, so the "need to norm" is not
  over-counted.
- Ore that arrives in a capital is minted by `_mint_pass` in the same run (user decision 10: allowed).
- Merchants (inside the region step) see the stock after caravans; since a seller always keeps ≥ norm (3.5), merchants
  never lose their share below norm because of caravans.

Runs in **scheduled and manual** runs (user decision 11) — both arrivals and dispatches. Pressing «Пересчитать
сейчас» several times makes caravans travel faster in real time; accepted (a recount is a recount).

**Lifecycle (one row in `econ_caravans`, 3.13):**
```
dispatch (run N): status=in_transit, travel_runs = 1 (same country) | 2 (pair), runs_left = travel_runs,
                  last_run_id = N, buyer pays into escrow, seller stock -= units
each later run R (arrival phase, R != last_run_id): runs_left -= 1, last_run_id = R
   runs_left > 0  -> still in transit (only the caravan row is touched)
   runs_left == 0 -> finish in the same transaction: delivered (3.8) or cancelled (3.8)
```
Domestic: dispatched in run N, arrives in run N+1 (before N+1's region step) — the goods are «в пути» during N's
region step and are consumed by nobody. Foreign: arrives in run N+2.
`runs_left` / `last_run_id` make the decrement idempotent: the row is locked and only decremented when
`last_run_id <> current run`.

**Resumed runs** (`_claim_auto` resumes a dead run of the same slot): the pass runs again. To never move goods into or
out of a region that has **already ticked in this run**, the pass skips such regions: they are excluded from the
dispatch snapshot, and a caravan whose destination (or origin, for a cancel) has `econ_regions.last_run_id = run_id`
is left with `runs_left = 0` and finished by the next run. Dispatch duplicates are impossible anyway (UNIQUE key,
3.7).

`params.caravans_enabled = 0` stops **dispatching** only; caravans already on the road still advance and arrive
(nothing is stranded in escrow).

Best effort like the mint: each dispatch / arrival is its own transaction; a failure rolls back that caravan only,
increments `summary.caravan_failures`, the run error gets `CARAVAN_ERROR_PREFIX = "караваны — ошибка: "` + count;
the region loop always runs. A failure of the whole snapshot load skips dispatching for this run (arrivals still run).

### 3.3 Routes and travel time

`route(from_country, to_country, pairs, params) -> Optional[Route(travel_runs, duty_pct)]` (pure):
- same country → `Route(params.caravan_travel_domestic (1), 0)` — no duty inside a country (decision 3);
- different countries and the normalised pair `(min, max)` exists in `econ_trade_pairs` with `is_enabled = 1` →
  `Route(params.caravan_travel_foreign (2), pair.duty_pct)`;
- otherwise `None` (brief: between countries «по умолчанию — запрещено»).
Any participating region to any participating region (decision 6) — no adjacency graph, no hubs. A region without a
`Regions` row or without a country never trades.

### 3.4 Money: escrow, payment at dispatch, settlement at arrival

**Decision: the buyer pays at dispatch into a new singleton account `caravan_escrow` («Караваны в пути»); the money
is released at arrival** (seller's purse + duty to the buyer's country) **or refunded in full on a cancel.**
Why not pay the seller directly at dispatch: a cancel (destination left / deleted) would need a refund out of the
seller's purse, which may already be spent (tax, wages) and cannot go negative → money or goods would be lost. Why
not pay at arrival: the buyer's purse may be empty by then, the goods are already on the road. Escrow gives "buyer
commits once, seller gets paid only for delivered goods, cancel is always lossless" and a checkable sub-invariant
(escrow balance = Σ paid of in-transit caravans), exactly like `auction_escrow`.

`econ_core.py` (canonical, copied byte-for-byte to inventory/locations/dungeon):
```python
# FEAT-192: money of caravans on the road (paid by the buyer at dispatch, released at arrival). Never negative.
KIND_CARAVAN_ESCROW = "caravan_escrow"         # + ACCOUNT_KINDS; singleton (not in REF_KINDS)
SINGLETON_NAMES[KIND_CARAVAN_ESCROW] = "Караваны в пути"
AccountRef.caravan_escrow() -> AccountRef(KIND_CARAVAN_ESCROW, 0)
OP_CARAVAN_DISPATCH = "caravan_dispatch"       # buyer purse (+ buyer region treasury for food) -> escrow
OP_CARAVAN_DELIVERY = "caravan_delivery"       # escrow -> seller purse (value) + escrow -> buyer country (duty)
OP_CARAVAN_CANCEL = "caravan_cancel"           # escrow -> the buyer accounts that paid (full refund)
CARAVAN_OP_TYPES = frozenset({OP_CARAVAN_DISPATCH, OP_CARAVAN_DELIVERY, OP_CARAVAN_CANCEL})
OP_TYPES |= CARAVAN_OP_TYPES                   # NOT in SOURCE_OP_TYPES, NOT comment-required
```
`caravan_escrow` is **not** in `NEGATIVE_ALLOWED_KINDS`, **not** in `TAX_SOURCE_KINDS`, **not** in `SOURCE_KINDS`.
The account row is created lazily (singleton path of `SINGLETON_NAMES`, like the auction accounts); no seed needed.

**Legs** (all `LEG_MAIN`, every call passes `apply_tax=False` explicitly):

| Op | Legs | Key |
|---|---|---|
| `caravan_dispatch` | `purse(buyer) -> escrow` = `paid_purse`; `region(buyer) -> escrow` = `paid_treasury` (food only, may be 0 → leg dropped) | `caravan:c<id>:pay` |
| `caravan_delivery` | `escrow -> purse(seller)` = `value`; `escrow -> country(buyer_country)` = `duty` (0 → dropped) | `caravan:c<id>:done` |
| `caravan_cancel` | `escrow -> purse(buyer)` = `paid_purse`; `escrow -> region(buyer)` = `paid_treasury` | `caravan:c<id>:back` |

`paid_purse + paid_treasury = value + duty` always. Fallback targets when an account owner is gone (its `Regions` row
deleted → locations-service already closed its purse/treasury into the country; posting there again would revive a
dead account): seller purse → **seller's country treasury** (`from_country_id` stored on the row); buyer purse /
treasury → **buyer's country treasury** (`to_country_id`); a country whose `Countries` row is gone →
**world treasury**. So every leg has a live target.

**Tax check (asked by PM):** the automatic country tax only fires on inflows **into a `region_treasury` from a
`TAX_SOURCE_KINDS` account**. Our only inflow into a region treasury is the cancel refund `escrow -> region(buyer)`,
and `caravan_escrow` is not a tax source → no tax; plus `apply_tax=False` everywhere. Purse→escrow, treasury→escrow,
escrow→purse, escrow→country are never taxed by the rule. Domestic trade is untaxed; the duty is the only levy
(decision 3). **No emission legs → world sum stays 0; `economy:emit` is not needed anywhere in this feature.**

**Agreed price:** `unit_price = group.base_price × seller.price_mult` (the seller's stored market price at
dispatch, includes the seller's event price mods — a «Ярмарка» discount makes its goods cheaper to import, a
magic anomaly makes them dearer; that is the market). `value = floor(units × unit_price)`,
`duty = floor(value × duty_pct / 100)` — paid **on top** by the buyer (importer pays the import duty into its own
country; the seller still gets the full `value`). Rounding down keeps `value + duty ≤ budget` without a loop.

**Food subsidy (decision 2):** for groups with `is_food = 1` the buyer's region treasury pays what the purse budget
cannot: `paid_purse = min(cost, purse_left)`, `paid_treasury = cost - paid_purse ≤ treasury_left`. Non-food goods are
paid only from the purse. If both budgets are short → `units` shrink to what is affordable (edge case «везут
столько, сколько могут оплатить»).

**Budgets per buyer per run** (snapshot balances, running totals across all its caravans of this run):
`purse_left = floor(max(0, purse) × caravan_purse_share)`, `treasury_left = floor(max(0, treasury) ×
caravan_treasury_food_share)` (treasury may be negative in the ledger — a negative treasury pays nothing). At execution
the parts are re-clamped against the **locked** balances (3.7) so `InsufficientFunds` cannot happen.

### 3.5 Matching algorithm (pure, deterministic, bounded)

`plan_caravans(markets, groups, inbound, pairs, params) -> List[CaravanPlan]`.

Inputs (snapshot, 3.7): per participating region not yet ticked this run — `country_id`, `halted` (export stop),
`purse`, `treasury`, per group `stock`, `norm_stock`, `price_mult`; `inbound[(region, group)]` = Σ units of
in-transit caravans **to** that region (after this run's arrivals); enabled pairs.

```
group order: is_food desc, then code asc            (food is bought first — it may use the treasury)
per region: purse_left, treasury_left as in 3.4
count = 0
for g in groups:
  supply[s] = floor3(caravan_surplus_share × (stock_s − norm_s))   s: not halted, norm_s > 0, stock_s > norm_s
  need[b]   = floor3(norm_b − stock_b − inbound[b,g])               b: norm_b > 0, value > 0
  buyers ordered by (stock_b + inbound[b,g]) / norm_b asc, then region_id asc   (most deprived first)
  for b in buyers:
    sellers = [s ≠ b with supply[s] > 0 and route(s, b) is not None]
              ordered by travel_runs asc, unit_price asc, region_id asc         (near and cheap first)
    for s in sellers:
      if count == caravan_max_per_run: stop the whole plan
      want   = min(need[b], supply[s])
      budget = purse_left[b] + (treasury_left[b] if g.is_food else 0)
      units  = min(want, affordable_units(budget, unit_price, duty_pct))       # floor3(budget / (price × (1+duty%)))
      value, duty = price_caravan(units, unit_price, duty_pct)
      if units <= 0 or value < caravan_min_value: continue
      split cost into paid_purse / paid_treasury; decrease purse_left / treasury_left / supply[s] / need[b]
      emit CaravanPlan(from=s, to=b, group=g, units, unit_price, value, duty, duty_pct, travel_runs, paid_*); count += 1
      if need[b] <= 0 or budget exhausted: break
```
Properties (asserted by QA): a seller never goes below its norm (`supply ≤ share × surplus`), a buyer never above its
norm counting goods already on the road (`need` subtracts `inbound`) — so a region is never both seller and buyer of a
group and surplus/deficit cannot flip back and forth (no ping-pong); per seller per group per run at most
`caravan_surplus_share` of the surplus leaves (decision 4); same input → same plan (stable sort keys, no RNG).
Signal = `stock / norm_stock`, not `price_mult` (user rules are stated in norm terms; event price mods do not
trigger shipments). `norm_stock = 0` (region never ticked) → the group is skipped for that region.

**Bound:** O(groups × buyers × sellers) ≤ 12 × R² comparisons per run (R = participating regions, a handful to a few
dozen), plus at most `caravan_max_per_run` (default 200) dispatch transactions. Arrivals ≤ caravans in transit
(≤ 2 × max per run with the default travel times).

**Export stop (decision 7):** a region with an active instance carrying `merchants_halt` («Набег», «Бунт» — reuse
the existing effect, no new effect type) does not **send** caravans (`halted = econ_events.aggregate(...)
.merchants_halt` from the `active_map` the events pass already returns). It still **receives** (a raided region may
import food — same as merchants: restock stops, residents still buy). Caravans on the road are not affected.

### 3.6 Pure helpers in `econ_caravan.py`
- `route(...)` (3.3); `floor3(x)`; `price_caravan(units, unit_price, duty_pct) -> (value, duty)`;
  `affordable_units(budget, unit_price, duty_pct) -> float`; `split_payment(cost, purse_left, treasury_left,
  is_food) -> (paid_purse, paid_treasury)`; `plan_caravans(...)` (3.5);
  `clamp_dispatch(plan, seller_stock, seller_norm, purse_balance, treasury_balance) -> Optional[CaravanPlan]` (3.7).
- Dataclasses `RegionMarket`, `GoodMarket`, `PairRule`, `Route`, `CaravanPlan` (frozen). No DB, no time, no RNG.

### 3.7 Dispatch execution (`economy_caravan_crud.dispatch(session_factory, run_id, plan, now)`)
Snapshot (one read-only session, then rollback): `participating_regions` + `Regions.country_id`, `econ_regions.
last_run_id` (exclude regions already ticked in this run), all `econ_region_goods` of those regions, purse and
treasury balances, `inbound` = `SELECT to_region_id, group_code, SUM(units) FROM econ_caravans WHERE status =
'in_transit' GROUP BY …`, enabled pairs. → pure plan.

Per plan item, **one transaction**:
1. Lock `econ_regions` of both regions FOR UPDATE **ascending region_id**; re-check both participate and
   `last_run_id <> run_id` (else skip).
2. Lock the seller's goods row `(from, group)` FOR UPDATE (goods rows ascending `(region_id, group_code)` — only one
   here); re-check the route (pair still enabled — plain read of `econ_trade_pairs`).
3. Pure `clamp_dispatch`: `units ≤ plan.units`, `units ≤ stock − norm` (seller keeps ≥ norm), `paid_purse ≤ purse
   balance` (locked read via the ledger helper), `paid_treasury ≤ max(0, treasury)`; recompute value/duty/parts;
   below `caravan_min_value` → skip.
4. `INSERT econ_caravans` (status `in_transit`, `last_run_id = run_id`); UNIQUE `(dispatch_run_id, from_region_id,
   to_region_id, group_code)` → `IntegrityError` → rollback, counted as "already" (resumed run). Inserts happen with
   only the two region rows + one goods row locked; runs are serial (`RunInProgress`) and nobody else inserts caravans,
   so the FEAT-191 insert-intention concern does not apply (documented).
5. `seller goods.stock -= units` (rounded to 3 decimals).
6. `post_operation(caravan_dispatch, legs 3.4, region_id=buyer, apply_tax=False, idempotency_key=f"caravan:c{id}:pay",
   metadata={run_id, caravan_id, from, to, group, units, unit_price, value, duty, duty_pct})` — last DB step
   (locks `econ_accounts`); store `dispatch_op_id` → COMMIT. `DuplicateOperation` → rollback.

### 3.8 Arrival execution (`economy_caravan_crud.advance_and_finish(session_factory, run_id, now)`)
Read in-transit rows (no lock) ordered by id. Per row:
- **Advance only** (`runs_left − 1 > 0` for this run): one short transaction — lock the caravan row FOR UPDATE, if
  `status = in_transit` and `last_run_id <> run_id` → `runs_left -= 1`, `last_run_id = run_id` → COMMIT.
- **Finish** (it reaches 0 in this run, or it is already 0 from a postponed resumed run): one transaction — lock
  `econ_regions` of `from` and `to` (those that still exist) ascending → their goods rows `(region, group)` ascending →
  the caravan row FOR UPDATE; re-check `status = in_transit` and (`last_run_id <> run_id` or `runs_left = 0`); if the
  destination or the origin already ticked in this run → set `runs_left = 0`, `last_run_id = run_id`, COMMIT, finish
  next run. Then:
  - **Delivered** when the destination still participates (`Regions` row + `econ_regions` participating + goods row
    for the group): `dest.stock += units`; `caravan_delivery` op (key `caravan:c<id>:done`, targets with the 3.4
    fallbacks); `status = delivered`, `finished_at`, `finished_run_id`, `finish_op_id`. A disabled pair or a halted
    region does **not** stop it (decisions: «уже идущий караван доезжает»). The seller's region being deleted
    meanwhile does not stop it either (payment goes to the seller's country, 3.4).
  - **Cancelled** otherwise (destination left the simulation or was deleted): goods go back to the origin
    (`origin.stock += units`) if the origin still has its `Regions` row and goods row (participating or not);
    else they are written off (`goods_returned = 0`, logged warning — both ends vanished, there is nobody to hold
    them). Money: `caravan_cancel` full refund (key `caravan:c<id>:back`, 3.4 fallbacks). `status = cancelled`,
    `cancel_reason` = `'destination_left'` | `'destination_deleted'`.
  Money is never lost in any branch; goods are lost only when both regions are gone (documented in the guide).

### 3.9 Lock order (supersedes FEAT-191 3.12 — update `econ_tick.py` docstring and `character-service.md`)
`econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) → econ_region_events (asc id) →
econ_caravans (asc id) → econ_mint_seasons → npc_shop_items (asc id) → econ_banks (asc region_id) → bank_deposits
(asc id) → bank_loans (asc id) → character_inventory (asc id) → characters (asc id) → econ_accounts (asc id)`.
- Caravan dispatch: `econ_regions ×2 asc → econ_region_goods(seller) → [insert econ_caravans] → econ_accounts`.
- Caravan finish: `econ_regions ×≤2 asc → econ_region_goods ×≤2 asc → econ_caravans(row) → econ_accounts`.
- Caravan advance: `econ_caravans(row)` only.
- First transaction type that locks **two** `econ_regions` rows — ascending id rule is mandatory. Other lockers of
  `econ_regions` (region step, mint, admin `update_region`, player mint) lock a single region → no cycle. Runs are
  serial, so tick-vs-tick contention cannot happen; only admin PUTs / player mint can wait.
- `econ_trade_pairs` is never locked (plain reads; the admin PUT is a single-row upsert in its own transaction).

### 3.10 Settings (sim params JSON — no migration for numbers)

| Param | Type | Default | Bounds | Meaning |
|---|---|---|---|---|
| `caravans_enabled` | int | 1 | 0 … 1 | 0 = no new caravans (those on the road still arrive) |
| `caravan_surplus_share` | float | 0.25 | 0 … 1 | X: share of the seller's surplus above norm that may leave per recount, per group (decision 4) |
| `caravan_purse_share` | float | 0.25 | 0 … 1 | share of the buyer's purse caravans may spend per recount (all groups) |
| `caravan_treasury_food_share` | float | 0.5 | 0 … 1 | share of the buyer's positive treasury that may top up **food** per recount |
| `caravan_travel_domestic` | int | 1 | 1 … 8 | recounts on the road inside a country (decision 1) |
| `caravan_travel_foreign` | int | 2 | 1 … 8 | recounts on the road between countries (decision 1) |
| `caravan_min_value` | int | 10 | 1 … 1 000 000 | smaller deals are not sent (no dust caravans) |
| `caravan_max_per_run` | int | 200 | 1 … 5 000 | hard cap of dispatches per recount (performance bound) |

All edited via the existing `PUT /characters/admin/economy/sim` (`economy:settings`); no money-param guard (no
emission). Int keys go into `ECON_SIM_INT_PARAMS`. Hints in `paramHints.ts`.

### 3.11 API contracts (router prefix `/characters`, `economy_api.py`, Pydantic v1)

#### `GET /characters/admin/economy/caravans/overview` (`economy:read`) → `CaravanOverviewOut`
```json
{
  "params": {"caravans_enabled": 1, "caravan_surplus_share": 0.25, "caravan_purse_share": 0.25,
             "caravan_treasury_food_share": 0.5, "caravan_travel_domestic": 1, "caravan_travel_foreign": 2,
             "caravan_min_value": 10, "caravan_max_per_run": 200},
  "escrow": {"balance": 1234, "expected": 1234, "ok": true},
  "in_transit": {"count": 7, "value": 1100, "duty": 34},
  "last_run": {"run_id": 812, "dispatched": 5, "delivered": 4, "cancelled": 0},
  "countries": [{"country_id": 6, "name": "str", "participating_regions": 3}],
  "pairs": [{"country_a": 6, "country_b": 7, "name_a": "str", "name_b": "str",
             "is_enabled": false, "duty_pct": 10.0, "updated_at": null}]
}
```
`countries` = all `Countries` rows ordered by name; `pairs` = every unordered pair of those countries (`a < b`), LEFT
JOIN `econ_trade_pairs` (missing row → `is_enabled=false, duty_pct=10.0`). `last_run` = newest finished
`econ_tick_runs` row, counters from `econ_caravans` (`dispatch_run_id` / `finished_run_id`) — no run-table columns.

#### `PUT /characters/admin/economy/caravans/pairs` (`economy:settings`) → `TradePairOut`
Request `TradePairIn`: `{"country_a": int ≥1, "country_b": int ≥1, "is_enabled": bool, "duty_pct": float 0…100}`.
Normalised to `a < b`. Errors: `a == b` → 400 «Страна не может торговать сама с собой»; unknown country → 404
«Страна не найдена». Upsert `econ_trade_pairs` with `updated_by` / `updated_at`; `duty_pct` rounded to 2 decimals.
Changes apply to **new** dispatches only (caravans on the road keep their stored duty).

#### `GET /characters/admin/economy/caravans?status=in_transit|delivered|cancelled|all&region_id=&group_code=&limit=50&offset=0` (`economy:read`) → `CaravanListOut`
`status` regex-validated (default `all`), `region_id ≥ 1` (matches from **or** to), `group_code` must be a known
group (400 otherwise), `limit 1…200`, `offset ≥ 0`. Newest first (`id desc`).
```json
{"total": 40, "items": [{
  "id": 1, "status": "in_transit", "group_code": "food", "group_name": "Продовольствие",
  "from_region_id": 10, "from_region_name": "str|null", "from_country_id": 6, "from_country_name": "str|null",
  "to_region_id": 9, "to_region_name": "str|null", "to_country_id": 6, "to_country_name": "str|null",
  "units": 12.5, "unit_price": 1.6, "value": 20, "duty": 0, "duty_pct": 0.0,
  "paid_purse": 20, "paid_treasury": 0, "travel_runs": 1, "runs_left": 1,
  "dispatch_run_id": 812, "finished_run_id": null, "cancel_reason": null, "goods_returned": null,
  "created_at": "iso", "finished_at": null}]}
```
Names are LEFT JOINs (deleted region/country → `null`, frontend shows «удалён»).

#### `GET /characters/economy/regions/{region_id}/card` (existing, same auth) — additive field `caravans` (3.12).
#### `GET /characters/admin/economy/summary` (existing) — additive `totals.caravan_escrow`, `invariant.caravan_escrow_expected` / `caravan_escrow_actual`; `invariant.ok` also requires them equal (expected = `SUM(paid_purse + paid_treasury)` of `in_transit` rows).
#### `PUT /characters/admin/economy/sim` (existing) — the 8 optional fields of 3.10.

No player write endpoints. No new permission (`economy:read` / `economy:settings`), `economy:emit` not used.

### 3.12 Player card (words only — decision 8)
`region_card` (both shapes) gets:
```json
"caravans": {
  "incoming": [{"group_code": "food", "group_name": "Продовольствие", "region_id": 10, "region_name": "str",
                "country_name": "str|null", "foreign": false, "in_transit": true}],
  "outgoing": [ ...same shape... ]
}
```
Source: `econ_caravans` where the region is `to` (incoming) / `from` (outgoing) and `status = 'in_transit'` **or**
(`status = 'delivered'` and `finished_at ≥ now − CARD_RECENT_HOURS (24)`). Deduplicated per (group, other region);
`in_transit = true` wins; ordered in-transit first, then by the group order; at most `CARD_MAX_LINES = 6` per list.
Cancelled caravans are not shown. Hidden shape (non-participating) → both lists empty. **No units, prices or money.**
`country_name` / `foreign` only filled for another country. Deleted other region → the entry is dropped.

Frontend wording (`RegionEconomyCard.tsx`, block «Караваны», lowercase group name):
- incoming in transit: «Везут {группа} из {регион}» (+ « ({страна})» when foreign) + badge «в пути»;
- incoming recent: «Привезли {группа} из {регион}»;
- outgoing in transit: «Вывозят {группа} в {регион}» + «в пути»; outgoing recent: «Вывезли {группа} в {регион}».
Block hidden when both lists are empty.

### 3.13 DB changes — migration `035_econ_caravans` (raw-SQL DDL, `_TABLE_OPTS`, re-runnable, like 034)
```sql
CREATE TABLE IF NOT EXISTS econ_trade_pairs (     -- symmetric pair, country_a < country_b (app-enforced); no FK (Countries owned by locations)
  country_a INT NOT NULL,
  country_b INT NOT NULL,
  is_enabled TINYINT(1) NOT NULL DEFAULT 0,
  duty_pct DECIMAL(5,2) NOT NULL DEFAULT 10.00,
  updated_at DATETIME NULL, updated_by INT NULL,
  PRIMARY KEY (country_a, country_b)
) <_TABLE_OPTS>;

CREATE TABLE IF NOT EXISTS econ_caravans (        -- one caravan; idempotency marker + history (kept, future «газета»)
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  dispatch_run_id INT NOT NULL,
  from_region_id INT NOT NULL, to_region_id INT NOT NULL,
  from_country_id INT NOT NULL, to_country_id INT NOT NULL,
  group_code VARCHAR(32) NOT NULL,
  units DECIMAL(16,3) NOT NULL,
  unit_price DECIMAL(14,4) NOT NULL,
  value BIGINT NOT NULL, duty BIGINT NOT NULL DEFAULT 0, duty_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
  paid_purse BIGINT NOT NULL DEFAULT 0, paid_treasury BIGINT NOT NULL DEFAULT 0,
  travel_runs TINYINT NOT NULL, runs_left TINYINT NOT NULL, last_run_id INT NOT NULL,
  status VARCHAR(16) NOT NULL,                    -- in_transit | delivered | cancelled
  cancel_reason VARCHAR(32) NULL, goods_returned TINYINT(1) NULL,
  dispatch_op_id BIGINT NULL, finish_op_id BIGINT NULL,
  created_at DATETIME NOT NULL, finished_at DATETIME NULL, finished_run_id INT NULL,
  UNIQUE KEY uq_econ_caravans_dispatch (dispatch_run_id, from_region_id, to_region_id, group_code),
  KEY ix_econ_caravans_status (status, id),
  KEY ix_econ_caravans_to (to_region_id, status),
  KEY ix_econ_caravans_from (from_region_id, status),
  KEY ix_econ_caravans_finished (finished_at)
) <_TABLE_OPTS>;
```
No FKs (no FK-index pitfalls; regions/countries owned by locations-service; runs are purged). No ENUM. Nothing
seeded (pairs default "off" by absence; the escrow account is lazy). `status` is a free VARCHAR validated in code.
**Retention:** caravan rows are **kept** (brief: «историю храним» for the future newspaper); `purge_old` does not touch
them; the `finished_at` index allows a purge later. Size estimate: ≤ 200 rows/run × 4 runs/day — tens of bytes each.
**Downgrade:** `DROP TABLE IF EXISTS econ_caravans, econ_trade_pairs`. Before a downgrade with caravans on the road
the escrow would be left with money → documented: run with `caravans_enabled = 0` until nothing is in transit,
then downgrade. Ledger rows stay.

### 3.14 Frontend
- `src/api/regionEconomy.ts` — `RegionCardData.caravans?: {incoming: CaravanCardLine[]; outgoing: CaravanCardLine[]}`
  (optional, like `events`); `RegionEconomyCard.tsx` — block «Караваны» (3.12 wording), Tailwind, 360px+.
- `src/api/economyAdmin.ts` + `src/types/economy.ts` — `getCaravanOverview`, `putTradePair`, `listCaravans`, types
  (`CaravanOverview`, `TradePair`, `CaravanRow`, `CaravanList`), 8 new `EconSimParams` fields, summary
  `caravan_escrow` total + invariant fields.
- New admin tab **«Караваны»** `components/Admin/EconomyPage/EconomyCaravans.tsx`: params card (8 params via sim PUT,
  `ParamHint`); escrow check line (green «сходится» / red «расходится: ожидается X, на счёте Y»); in-transit counters
  and last-run counters; **trade pairs** list (each pair: «Страна A ↔ Страна B», checkbox «торгуют», duty % input,
  «Сохранить»; filter input by country name; note «внутри страны караваны ходят всегда, пошлины нет»); **caravans
  list** with status tabs (в пути / доставлены / отменены / все), region and group filters, pagination; on mobile rows
  become cards. Every request error shown in Russian (toast + inline), 403 → «Недостаточно прав».
- `EconomyPage.tsx` (`TAB_LABEL.caravans = 'Караваны'`, `TAB_INTRO`, render), `guideSections.ts` (`EconomyTabId`
  `caravans`, guide ids `caravans`, `recipe-caravans`), `EconomyGuide.tsx`: section «Караваны» (who sells / who buys —
  norm rule, X %, travel 1 / 2 recounts, payment into «Караваны в пути» and release at arrival, food top-up from the
  treasury, duty to the importer's country, raid/riot stop exports, cancel rules incl. «товар списан» when both
  regions vanished, ore feeds the court mint, manual recounts move caravans too); checklist step «Открыть торговлю
  между странами (если нужно)»; recipe «Как открыть торговлю между двумя странами».
- `paramHints.ts` (8 params), `economyLabels.ts`: `OP_TYPE_LABELS` `caravan_dispatch: 'Караван: оплата'`,
  `caravan_delivery: 'Караван: доставка'`, `caravan_cancel: 'Караван: возврат'`; account-kind label `caravan_escrow:
  'Караваны в пути'`. `EconomySummary.tsx`: total «Караваны в пути» + invariant row.
- All touched files are `.tsx`/`.ts`; no `React.FC`; design-system classes (`gold-text`, `btn-blue`, `input-underline`,
  `gray-bg` …); responsive.

### 3.15 Data flow
```
econ_scheduler (6 h) / «Пересчитать сейчас» → run_tick: claim → merchants prep → events pass (active_map)
  → _quota_pass
  → _caravan_pass:
       arrivals: in-transit rows → advance (runs_left−1) | finish: lock regions asc → goods asc → caravan →
                 dest.stock += units + caravan_delivery (escrow → seller purse, escrow → buyer country duty)
                 | cancel: origin.stock += units + caravan_cancel (escrow → buyer purse/treasury)
       dispatch: snapshot → econ_caravan.plan_caravans (pure) → per plan: lock regions asc → seller goods →
                 clamp → INSERT econ_caravans → seller.stock −= units → caravan_dispatch (buyer → escrow)
  → region loop (prices/consumption on post-caravan stock) → _mint_pass → banks → done
Player → GET /characters/economy/regions/{id}/card → words «везут / привезли / вывозят / вывезли»
Admin → «Экономика → Караваны» → overview / pairs PUT / list; sim PUT for params
```
No HTTP between services, no queues; reads of `Regions` / `Countries` by SQL as today.

### 3.16 Security
- Admin reads `require_permission("economy:read")`; pair PUT `require_permission("economy:settings")`; sim params via
  the existing endpoint. No new permission → no user-service migration / RBAC test change.
- Input validation: Pydantic v1 (`conint(ge=1)`, `confloat(ge=0, le=100)`), status regex, group code checked
  against `econ_goods_groups`, limit/offset bounds. Parameterised `text()` SQL only.
- Player card: no new data class — words only, no balances/numbers (existing contract).
- No money creation: QA asserts world sum 0 and the escrow sub-invariant after dispatch / arrival / cancel.
- Errors in Russian, internals only in server logs.

### 3.17 Risks
- **Two-region locks** — new pattern; mitigated by the strict ascending rule (3.9) and serial runs.
- **Resumed runs** — handled by skipping regions already ticked in this run + UNIQUE dispatch key + guarded decrement.
- **Purse drain** — buyers spend up to 25 % of the purse per recount; food first. Tunable.
- **Ore → capitals → court mint** grows emission (decision 10 — intended).
- **History growth** — rows kept forever by decision; index ready for a future purge.
- **econ_core copies** (×4) — CI `check_econ_copies.sh`; any test that counts `ACCOUNT_KINDS` / `OP_TYPES` must be
  updated.
- **Prod geography unknown** — the design needs no adjacency data, only `Regions.country_id`.
- `docs/ISSUES.md` entry «no inter-region goods exchange until caravans» (~line 990) is closed by this feature.

### Questions for PM (non-blocking — defaults chosen, tell me if the user wants otherwise)
1. **Budgets I added** (not in the brief): residents spend at most **25 % of their purse per recount** on caravans
   (all goods); the treasury tops up food with at most **50 % of its positive balance per recount**; deals below
   **10 marks** are not sent; at most **200 caravans per recount**. All are admin params.
2. **Raid/riot:** the struck region stops **exporting**, but caravans may still **bring** goods into it (e.g. food
   relief after a raid) — same as merchants (restock stops, residents still buy). If the user wants a full blockade
   (no imports either) it is a one-line change.
3. **Duty is paid on top by the buyer** (the seller always gets the full price; the importer's residents pay price +
   duty, the duty goes to the importer's country) — the natural reading of decision 3.
4. **Payment timing:** the buyer pays when the caravan leaves (money sits in «Караваны в пути»), the seller is paid on
   arrival; a cancelled caravan refunds the buyer in full.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Ledger: escrow kind + op types + copies.** Canonical `econ_core.py`: `KIND_CARAVAN_ESCROW` (ACCOUNT_KINDS, singleton name «Караваны в пути», not negative / not tax source / not source), `AccountRef.caravan_escrow()`, `OP_CARAVAN_DISPATCH/DELIVERY/CANCEL`, `CARAVAN_OP_TYPES` in `OP_TYPES` only (3.4). Contract cases in canonical `tests/econ_contract_cases.py` (each caravan op passes with `purse -> escrow` / `escrow -> purse` / `escrow -> country` legs and no comment; a caravan op with an emission leg fails; escrow cannot go negative). Byte-copy both files to inventory/locations/dungeon; asserts in each service's `tests/test_econ_contract.py` (`CARAVAN_OP_TYPES <= OP_TYPES`, disjoint from `SOURCE_OP_TYPES` and `COMMENT_REQUIRED_OP_TYPES`, escrow not in `NEGATIVE_ALLOWED_KINDS`/`TAX_SOURCE_KINDS`). `economy_crud.py`: `ADJUST_FORBIDDEN_KINDS` += escrow; summary `totals.caravan_escrow`, `invariant.caravan_escrow_expected/actual` folded into `ok` (expected from `econ_caravans`, guarded by table existence for SQLite until #2 lands); summary schema fields. | Backend Developer | DONE | `services/{character,inventory,locations,dungeon}-service/app/econ_core.py`, `services/*/app/tests/econ_contract_cases.py` (4), `services/*/app/tests/test_econ_contract.py` (4), `CS/economy_crud.py`, `CS/schemas.py` | — | `bash scripts/check_econ_copies.sh` passes; `py_compile` passes; existing contract + summary tests green in all 4 services (update any test counting kinds/op types). |
| 2 | **Migration + models + params + pure module.** Migration `035_econ_caravans` (3.13: docstring, re-runnable DDL, downgrade). ORM `EconTradePair`, `EconCaravan`. `SimParams` 8 fields + `ECON_SIM_PARAM_BOUNDS` / `ECON_SIM_INT_PARAMS` / sim PUT body (3.10). New pure `econ_caravan.py` (3.3, 3.5, 3.6): dataclasses, `route`, `floor3`, `price_caravan`, `affordable_units`, `split_payment`, `plan_caravans`, `clamp_dispatch`. | Backend Developer | DONE | `CS/alembic/versions/035_econ_caravans.py`, `CS/models.py`, `CS/econ_sim.py`, `CS/schemas.py`, `CS/econ_caravan.py` (new) | #1 | Revision id ≤ 32 chars, down `034_econ_mint`; `alembic upgrade head` → `downgrade -1` → `upgrade head` in the character-service container; `py_compile`; plan deterministic for the same input. |
| 3 | **Caravan CRUD + tick pass + card.** `economy_caravan_crud.py`: snapshot loader (participating, not ticked this run, goods, balances, inbound, enabled pairs, halts from `active_map`), `dispatch` (3.7), `advance_and_finish` (3.8, delivered / cancelled with fallbacks), admin reads (overview, list), pair upsert, `card_caravans(region_id, now)`, `escrow_expected`. `econ_tick.py`: `_caravan_pass` after `_quota_pass`, before the region loop (arrivals then dispatch), `RunSummary` counters `caravans_dispatched/delivered/cancelled/failed`, `caravan_value`, `CARAVAN_ERROR_PREFIX`, final log line, docstring lock order (3.9). `economy_sim_crud.region_card`: `caravans` in both shapes (3.12). Use the `economy_crud` expected-escrow helper from here (replace the #1 guard if convenient). | Backend Developer | DONE | `CS/economy_caravan_crud.py` (new), `CS/econ_tick.py`, `CS/economy_sim_crud.py`, `CS/economy_crud.py` | #2 | `py_compile`; in the dev container: with two regions of one country (surplus/deficit) a manual recount dispatches, the next manual recount delivers; summary invariant `ok`; a second resume of the same run moves nothing twice; existing `test_econ_tick*.py` green. |
| 4 | **Router + schemas.** Endpoints 3.11: `GET /admin/economy/caravans/overview`, `PUT /admin/economy/caravans/pairs`, `GET /admin/economy/caravans` (validation, Russian errors); card schema `caravans`; summary additive fields (if not done in #1). Pydantic v1: `TradePairIn`, `TradePairOut`, `CaravanOverviewOut`, `CaravanOut`, `CaravanListOut`, `CaravanCardLine`, `RegionCaravansOut`. | Backend Developer | DONE | `CS/economy_api.py`, `CS/schemas.py` | #3 | `py_compile`; endpoints in `/docs`; curl in dev: enable a pair, see it in overview; list filters work; 400/404 texts as specified. |
| 5 | **Docs.** `docs/services/character-service.md`: caravans section (tables, endpoints, op types, escrow account + sub-invariant, pass placement, lock order 3.9, params). `docs/ARCHITECTURE.md` if it lists economy tables/accounts. `docs/ISSUES.md`: close the «no inter-region goods exchange until caravans» entry. | Backend Developer | DONE | `docs/services/character-service.md`, `docs/ARCHITECTURE.md`, `docs/ISSUES.md` | #4 | Docs match the implemented contracts. |
| 6 | **Frontend: player card.** `RegionCardData.caravans?` type; «Караваны» block in `RegionEconomyCard.tsx` with the 3.12 wording, «в пути» badge, hidden when empty; words only, no numbers. | Frontend Developer | DONE | `src/api/regionEconomy.ts`, `src/components/WorldPage/RegionEconomyCard.tsx` | #4 (contract only — can start from 3.12) | `npx tsc --noEmit` + `npm run build` pass in the container; Tailwind only, no `React.FC`, 360px OK. |
| 7 | **Frontend: admin.** New tab «Караваны» `EconomyCaravans.tsx` (3.14: params, escrow check, counters, trade pairs, caravans list with filters/pagination, mobile cards); `EconomyPage.tsx` tab label/intro/render; `guideSections.ts` + `EconomyGuide.tsx` (section «Караваны», checklist step, recipe «Как открыть торговлю между двумя странами»); `paramHints.ts` (8); `economyLabels.ts` (3 op labels + escrow kind label); `EconomySummary.tsx` (escrow total + invariant row); API + types. All errors visible in Russian. | Frontend Developer | DONE | `src/components/Admin/EconomyPage/EconomyCaravans.tsx` (new), `EconomyPage.tsx`, `guideSections.ts`, `EconomyGuide.tsx`, `paramHints.ts`, `economyLabels.ts`, `EconomySummary.tsx`, `src/api/economyAdmin.ts`, `src/types/economy.ts` | #4 (contract only), #6 (shared types) | `tsc` + `build` pass; admin can enable a pair with a duty, edit params, browse caravans; 403/400 visible; mobile layout OK. |
| 8 | **QA: pure math + contract.** `test_econ_caravan.py`: `route` (same country / enabled pair / disabled / missing pair / normalised order), `price_caravan` + `affordable_units` (floors, `value + duty ≤ budget`, duty 0/10/100 %), `split_payment` (food uses treasury, non-food never), `plan_caravans` (seller keeps ≥ norm, ≤ X % of surplus, buyer ≤ norm incl. inbound, most deprived first, near/cheap seller first, halted region does not export but imports, `norm = 0` skipped, min value, max per run, food first, budget shrink, determinism), `clamp_dispatch` (stock / balance changes between plan and lock). Contract cases run in all 4 services. | QA Test | DONE | `CS/tests/test_econ_caravan.py` (new) | #1, #2 | pytest green in character-, inventory-, locations-, dungeon-service. |
| 9 | **QA: tick pass.** `test_econ_tick_caravans.py` (SQLite tick harness of `test_econ_tick*.py`; add tables to fixtures): domestic arrives after 1 recount, foreign after 2; forbidden pair → nothing; stock moved exactly; money legs (purse → escrow → seller purse; duty → buyer country; food top-up from treasury) and **world sum 0 + escrow sub-invariant** after every step; no country tax leg on any caravan op; manual runs move caravans; resumed run: no double dispatch / double decrement / double delivery, regions already ticked are skipped/postponed; pair disabled mid-transit → still delivered with stored duty; raid/riot (`merchants_halt`) stops exports only; destination leaves sim → cancel, goods back, full refund; destination deleted → refund to its country; origin deleted → delivered, seller country paid; both gone → goods written off, money refunded; can't pay → partial units; `caravans_enabled = 0` → no dispatch but arrivals continue; one failing caravan does not stop others or the region loop; `RunSummary` counters + error prefix. | QA Test | DONE | `CS/tests/test_econ_tick_caravans.py` (new), `CS/tests/conftest.py` (if needed) | #3 | pytest green; existing tick tests green. |
| 10 | **QA: API + security.** `test_econ_caravan_api.py`: overview (pairs default off/10 %, escrow block, last-run counters), PUT pairs (normalisation, same-country 400, unknown 404, duty bounds 422, persistence), list filters/pagination/validation (bad status 422, unknown group 400, SQL-injection-like `group_code` rejected), permissions (no auth 401, `economy:read` cannot PUT 403, `economy:settings` can), sim PUT accepts the 8 params with bounds; region card `caravans` in both shapes, words only (no numeric fields), recent/in-transit/dedup/limit, deleted region dropped; summary invariant fields. | QA Test | DONE | `CS/tests/test_econ_caravan_api.py` (new) | #4 | Full character-service pytest green in the container. |
| 11 | **Review.** Contracts vs 3.11/3.12, lock order 3.9, idempotency (UNIQUE dispatch, guarded decrement, ledger keys), escrow sub-invariant and world sum, no tax/emission legs, econ copies script, migration up/down, frontend rules (Tailwind, TS, no `React.FC`, mobile, Russian errors, design system), docs. **Live:** in Chrome on localhost — admin enables a pair, sets params; two manual recounts deliver a domestic caravan (and a foreign one after the second); «Караваны» tab shows it; region card shows «везут … / привезли …»; «Сводка» invariant OK; journal shows the 3 op labels; zero console errors. | Reviewer | TODO | all | #1–#10 | All automated checks (py_compile, pytest of 4 econ services, `check_econ_copies.sh`, tsc, build) + live verification pass. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-01
**Result:** FAIL (two small frontend defects; backend, ledger, migration, docs and tests are clean)

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/WorldPage/RegionEconomyCard.tsx:118-122` | Player card text is ungrammatical: `caravanText` puts the nominative group name after the verb, so players see «Везут руда и металл из «Мэттанхейм»», «Везут древесина …», «Везут броня и одежда …» (seen live on `/world/region/34`). The guide (`EconomyGuide.tsx`, «Что видят игроки») and spec 3.12 promise «Вывозят руду в …». Fix: an accusative label map per `group_code` on the frontend (12 groups: продовольствие, руду и металл, древесину, травы и реагенты, шкуры и ткани, магические материалы, оружие, броню и одежду, украшения, зелья, ремесленный инвентарь, быт и мебель), with the current lower-cased name as fallback for unknown codes. | Frontend Developer | FIX_REQUIRED |
| 2 | `services/frontend/app-chaldea/src/components/Admin/EconomyPage/EconomyCaravans.tsx:336, :385` | Trade-pair row collapses when the duty is invalid (e.g. 150): the error `<p className="... md:basis-full">` is a third child of an `md:flex-row` `<li>` **without** `flex-wrap`, so `basis-full` squeezes the name column to ~1 character wide (the country names render one letter per line). Fix: add `md:flex-wrap` to the `<li>` (line 336) or move the error under the duty input. Save is correctly disabled, nothing is sent. | Frontend Developer | FIX_REQUIRED |

#### Non-blocking notes (no fix required for PASS)
- **QA note on resumed runs — acceptable, track it.** After a crashed run is resumed, `load_snapshot` re-reads the (already reduced) seller stock and `plan_caravans` computes a fresh `caravan_surplus_share` of the remaining surplus; the UNIQUE key `(run, from, to, group)` blocks only the same route, so a seller can send a second share to a *different* buyer. Bounds still hold where it matters: the seller keeps ≥ norm (`clamp_dispatch`), buyers stay ≤ norm counting `inbound`, money is exact (escrow, ledger keys). Only decision 4's "≤ X % of surplus per recount" can be exceeded (at most X·(1−X) extra, 18.75 % at defaults), and only on a crash-resume of the same slot — rare. Recommendation: add a LOW entry to `docs/ISSUES.md`, or a cheap fix in `economy_caravan_crud.load_snapshot` (treat `(seller, group)` pairs that already have a row with `dispatch_run_id = run_id` as non-sellers for this run).
- Guide hardcodes default values (`EconomyGuide.tsx:1285` «25 %», «50 %»; `:1324-1325` `format(10, true)`, «200 караванов») — becomes stale if the admin changes params; consider «по умолчанию …» or reading `c.params`.
- `EconomyGuide.tsx:524` «… ${open} пар из …» — «1 пар» case agreement (cosmetic).
- Card shows at most 6 lines per side with in-transit first, so recent «Привезли …» lines are often hidden behind «Везут …» lines (by design 3.12; noted only).

#### Verified OK
- **Spec / user decisions 1–11:** travel 1 / 2 recounts (live: domestic delivered in the next run, foreign #37 after 2), buyer purse pays, treasury tops up food only (live: 1 treasury leg 269), per-pair duty on top to the buyer's country (live: 296 value + 44 duty = floor 15 %), ≤ X % surplus / seller ≥ norm / buyer ≤ norm incl. inbound, all 12 groups, any-to-any domestic, enabled pairs only abroad (default off), raid/riot stop exports only, words-only card, one symmetric checkbox + duty, ore to capitals not limited, manual recounts move caravans.
- **Ledger:** only `main` legs (live query: purse→escrow 39, treasury→escrow 1, escrow→purse 25, escrow→country 1); no tax/emission legs, `apply_tax=False` everywhere, ops not in `SOURCE_OP_TYPES`, escrow not negative/tax source/source, in `ADJUST_FORBIDDEN_KINDS`. Escrow sub-invariant held after every live run (21566 → 9413 → 2888 → 1053 = Σ paid of in-transit rows); «Сводка» «Караваны в пути: сходится». Idempotency keys `caravan:c<id>:pay|done|back`, UNIQUE dispatch key, guarded decrement (`last_run_id`).
- **Locks:** dispatch `econ_regions ×2 asc → goods(seller) → INSERT → econ_accounts asc`; finish `regions asc → goods asc → caravan row → accounts`; advance caravan row only. Every other locker of `econ_regions` (region step, mint pass, player mint, admin `update_region`) locks a single region then its goods → no cycle; runs are serial. `econ_trade_pairs` never locked.
- **Migration 035:** id `035_econ_caravans` (17 chars), down `034_econ_mint`, re-runnable raw DDL, no FKs/ENUM, downgrade drops both tables; ORM matches DDL; local DB at head.
- **RBAC / validation:** reads `economy:read`, pair PUT `economy:settings`, no new permission; `TradePairIn` strict ints ≥ 1, duty 0…100, `extra=forbid`; status regex, group checked against `econ_goods_groups`, limit ≤ 200; Russian errors; parameterised SQL only.
- **econ_core copies** byte-identical (×4), contract cases in all 4 services.
- **Frontend rules:** TS only, Tailwind + design-system classes, no `React.FC`, no `any`, every request error shown via Russian toast/inline; 360px: no horizontal overflow on the «Караваны» tab and on `/world/region/34` (scrollWidth = clientWidth = 345 in a 360px frame).
- **Docs:** `docs/services/character-service.md` (+115 lines: tables, endpoints, legs, escrow, pass placement, lock order, params), `docs/ISSUES.md` entry closed.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (no output)
- [x] `npm run build` (frontend container) — PASS (built in 55 s; only the existing chunk-size warning)
- [x] `py_compile` — PASS (all 11 changed/new character-service modules + 3 new test files; econ_core + contract files in inventory/locations/dungeon)
- [x] `pytest` character-service `--asyncio-mode=auto` — PASS, 3632 passed / 1 skipped
- [x] econ contract tests — PASS: inventory 352, locations 339, dungeon all green
- [x] `scripts/check_econ_copies.sh` — PASS («All economy ledger copies are identical»)
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, localhost) — PASS functionally, 2 UI defects above

#### Live Verification Results
- Pages: `/admin/economy` (tabs «Караваны», «Сводка», «Как настроить», «Пересчёт»), `/world/region/34`.
- Console errors: NONE. API: all `/characters/...` calls 200 (overview, list with status/region/group filters, sim/run ×3, summary, region card).
- Workflow: enabled pair Мидденгерд ↔ Шинзо with 15 % and saved (row shows «торгуют · пошлина 15 %»); 3 manual recounts (runs 69–71): run 69 delivered the 24 caravans of scheduled run 68 and sent 15 (1 foreign 7→6 with duty 44), run 70 delivered domestic ones and advanced the foreign one, run 71 delivered the foreign one (seller purse 296, buyer country 44). List: 67 total / 57 delivered / 0 cancelled; filters work. Guide section «Караваны НПС», checklist step and recipe present with live status. Region card shows the «Караваны» block, words only, «в пути» badges.

#### Data changed on the local dev DB
- Reverted: trade pair 6 ↔ 7 (row deleted; `econ_trade_pairs` empty again, as before). Sim params not changed.
- Left behind (normal economy steps): manual tick runs 69, 70, 71 with their region steps (stocks, purses, treasuries, history rows); 43 new caravan rows (ids 25–67; 10 still in transit, escrow 1053 = expected) and their `caravan_dispatch` / `caravan_delivery` operations. The 24 caravans of run 68 were created by the scheduled run before the review.

### Review #1 fixes (PM, 2026-11-01) — PASS
- Card wording: `RegionEconomyCard.tsx` — `GROUP_ACCUSATIVE` map by `group_code` («Везут руду и металл из …»), fallback to lowercased name. Verified live on `/world/region/34`.
- Trade-pair row: `md:flex-wrap` on the `<li>` in `EconomyCaravans.tsx`; with duty 150 the row stays intact and «От 0 до 100» sits on its own line. Verified live (nothing saved).
- Guide status line agreement: «Пар стран с открытой торговлей: N из M».
- Resumed-run note fixed (not just tracked): `economy_caravan_crud.load_snapshot` caps the snapshot stock at norm for every (seller, group) that already dispatched in this run, so a resumed run cannot ship a second share. New test `test_resumed_pass_does_not_ship_a_second_share_from_the_same_seller` (fails without the fix).
- Checks: character-service 3633 passed, 1 skipped; `tsc --noEmit` + `npm run build` OK; no console errors.
- Not fixed (cosmetic): the guide quotes default values (25 %/50 %, 10 marks, 200 caravans) literally.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-01 — PM: фича создана (FEAT-192, этап 5б экономики — караваны НПС), запускаю анализ кодовой базы параллельно с вопросами пользователю
[LOG] 2026-11-01 — Analyst: анализ завершён — затронуты character-service (тик, новая математика, таблицы пар стран и журнала караванов, миграция 035), фронтенд (админка, справочник, карточка региона), econ_core ×4 только при новом типе операции; составлен список из 12 бизнес-вопросов
[LOG] 2026-11-01 — Architect: спроектировано 11 задач (5 backend, 2 frontend, 3 QA, ревью) и 3 новых API-контракта + 3 дополненных; проход караванов перед циклом регионов (сначала прибытия, потом отправки), оплата при отправке на новый счёт «Караваны в пути» и выплата продавцу при доставке, таблицы пар стран и караванов (миграция 035), блокировки двух регионов по возрастанию id; 4 неблокирующих вопроса к PM о значениях по умолчанию
[LOG] 2026-11-01 — Backend Dev: начал задачи #1–#5
[LOG] 2026-11-01 — Backend Dev: задача #1 завершена — счёт «Караваны в пути» (caravan_escrow) и 3 типа операций в econ_core ×4, контрактные кейсы ×4, подинвариант в сводке, счёт запрещено корректировать
[LOG] 2026-11-01 — Backend Dev: задача #2 завершена — миграция 035_econ_caravans (econ_trade_pairs, econ_caravans), модели, 8 параметров пересчёта, чистый модуль econ_caravan.py; upgrade → downgrade → upgrade в контейнере прошли
[LOG] 2026-11-01 — Backend Dev: задача #3 завершена — economy_caravan_crud.py (снимок, отправка, прибытие/отмена, админ-чтения, строки карточки), проход караванов в тике перед циклом регионов, счётчики RunSummary и префикс ошибки
[LOG] 2026-11-01 — Backend Dev: задача #4 завершена — эндпоинты overview / pairs / список караванов, схемы Pydantic v1, поле caravans в карточке региона
[LOG] 2026-11-01 — Backend Dev: задача #5 завершена — раздел «NPC caravans» в docs/services/character-service.md, запись в ISSUES.md про обмен товарами закрыта
[LOG] 2026-11-01 — Backend Dev: проверки — py_compile, pytest character-service 3428 passed, econ-контракт inventory/locations/dungeon зелёные, check_econ_copies.sh ок; живой прогон 8 пересчётов на копии dev-БД (внутри страны, между странами с пошлиной, отмена), копия удалена; в dev-БД изменений не осталось
[LOG] 2026-11-01 — Frontend Dev: начал задачи #6 и #7 (по контракту из раздела 3, бэкенд параллельно)
[LOG] 2026-11-01 — Frontend Dev: задача #6 завершена — блок «Караваны» в карточке региона (везут / привезли / вывозят / вывезли, метка «в пути», только слова), тип caravans в regionEconomy.ts
[LOG] 2026-11-01 — Frontend Dev: задача #7 завершена — вкладка «Экономика → Караваны» (состояние и проверка счёта «Караваны в пути», 8 параметров, пары стран с галочкой и пошлиной, список караванов с фильтрами и страницами), раздел гайда «Караваны НПС», шаг чек-листа, рецепт «Как открыть торговлю между двумя странами», подсказки параметров, подписи операций и счёта, строка в «Сводке»; tsc и build в контейнере прошли
[LOG] 2026-11-01 20:55 — QA: начал тесты караванов заново (прошлая попытка прервана отключением питания, файлов не было)
[LOG] 2026-11-01 20:55 — QA: задача #8 завершена — test_econ_caravan.py, 81 тест чистой математики (маршруты, цены и пошлина с округлением, бюджеты, split_payment, план: норма продавца, ≤ X % излишка, нужда покупателя с учётом «в пути», продовольствие первым, внутренние раньше иностранных, мин. сумма, лимит за пересчёт, детерминизм, clamp_dispatch)
[LOG] 2026-11-01 20:55 — QA: задача #9 завершена — test_econ_tick_caravans.py, 43 теста прохода в тике (1 и 2 пересчёта в пути, пошлина в казну страны-покупателя, доплата казны за еду, повтор/возобновление без двойных отправок и доставок, отсрочка при уже пересчитанном регионе, Набег/Бунт останавливают только вывоз, отключение пары в пути, отмены с возвратом товара и денег, удалённые регионы/страны, списание при исчезновении обоих, сбои по одному каравану); после каждого шага сумма мира 0 и счёт «Караваны в пути» сходится
[LOG] 2026-11-01 20:55 — QA: задача #10 завершена — test_econ_caravan_api.py, 80 тестов API (overview, PUT пар с нормализацией/400/404/422, фильтры и валидация списка, инъекции, RBAC 401/403, 8 параметров пересчёта с границами, сводка, карточка региона только словами)
[LOG] 2026-11-01 20:55 — QA: багов в реализации не найдено; character-service полностью 3632 passed / 1 skipped, econ-контракт inventory 352, locations 339, dungeon 339 — зелёные, check_econ_copies.sh ок
[LOG] 2026-11-01 20:50 — Reviewer: начал проверку
[LOG] 2026-11-01 21:20 — Reviewer: автоматические проверки зелёные (py_compile, pytest 3632/1 skipped, контракт ×3, копии econ_core, tsc, build, compose); вживую 3 ручных пересчёта — доставка внутри страны за 1, между странами за 2 с пошлиной 15 % в казну страны-покупателя, счёт «Караваны в пути» сходится после каждого шага, ошибок в консоли нет, 360px без переполнения
[LOG] 2026-11-01 21:20 — Reviewer: проверка завершена, результат FAIL — 2 мелких дефекта фронтенда: неграмотные строки в карточке региона («Везут руда и металл»), ломается строка пары стран при ошибке пошлины; замечание QA о возобновлённом пересчёте признано допустимым (завести LOW в ISSUES.md или дешёвый фикс); пара стран 6↔7 откатана, в dev-БД остались пересчёты 69–71 и караваны 25–67
[LOG] 2026-11-01 — PM: замечания ревью исправлены (падеж в карточке, строка пары стран, фраза в гайде, повторная доля продавца при продолжении пересчёта + тест); проверено вживую; фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

Этап 5б экономики готов: караваны НПС возят товары из регионов с излишком в регионы с дефицитом.

- Внутри страны — всегда, 1 пересчёт в пути; между странами — только для пар, открытых админом, 2 пересчёта, пошлина (по умолчанию 10 %) в казну страны-покупателя.
- Платят жители покупателя жителям продавца; деньги ждут на счёте «Караваны в пути»; за еду при нехватке доплачивает казна.
- Продавец вывозит не больше 25 % излишка за пересчёт и не опускается ниже нормы; «Набег»/«Бунт» останавливают вывоз.
- Регион выпал из пересчёта — караван отменяется, товар и деньги возвращаются.
- Игрокам — строки словами в карточке региона; админу — вкладка «Караваны», строка в «Сводке», раздел/шаг/рецепт в гайде.
- Миграция character-service `035_econ_caravans`; 3 новых операции и счёт в econ_core (копии синхронизированы).
- Тесты: character-service 3633 passed; ревью + исправления, живая проверка в Chrome.

