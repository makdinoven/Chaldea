# FEAT-187: Экономика — события регионов (кризисы и благоприятные модификаторы)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-10-30 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Продолжение экономики: FEAT-181 (книга счетов), FEAT-182 (живые регионы), FEAT-183 (торговцы), FEAT-184 (банки),
FEAT-186 (лорное население в масштабе 1:100).

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Нужны модификаторы регионов — кризисы (засуха, чума, магическая катастрофа, потоп…) и благоприятные события
(урожайный год, благоприятная магическая аномалия…). Событие — временный модификатор рычагов, которые уже есть в
расчёте региона (производство/потребление по группам, запасы, цены, стабильность, достаток, казна, торговцы, банк);
остальное делает расчёт сам (засуха → меньше еды → голод → цены и стабильность).

### Бизнес-правила (согласовано с пользователем 2026-10-30)
1. **Шаблоны событий** заводит админ в «Экономике»: название, иконка, художественный текст для игроков,
   длительность (диапазон), область (регион / соседние регионы / страна / весь мир), набор эффектов, в каких шаблонах
   регионов и в какие игровые сезоны случается, вес/вероятность, хорошее/плохое. Поставляется стартовый набор
   (засуха, потоп, чума, магическая катастрофа, обвал в шахте, мор скота, набег, бунт; урожайный год, благоприятная
   магическая аномалия, богатая жила, ярмарка, праздник, удачный улов) — тексты на русском.
2. **Эффекты** (собираются из рычагов): производство группы ×N; потребление группы ×N; разовая потеря доли запасов
   групп; стабильность/достаток ± за пересчёт; множитель цен группы; доход казны ×N; разовый расход казны
   (восстановление — честной проводкой, деньги не исчезают); торговцы не докупают; банк: паника (жители забирают
   вклады) или бум займов; «больные жители» — временно меньше работников.
3. **Запуск — и случайно, и вручную (Q1):** в каждом пересчёте у региона шанс события по его шаблону и текущему
   игровому сезону; админ может запустить любое событие руками на регион/область и отменить активное.
4. **Частота (Q4): в среднем одно событие на регион за игровой сезон** (игровой календарь уже есть: сезоны и
   праздники; не хардкодить год — см. календарь в коде). Частота — настройка.
5. **Население (Q2): кризис может навсегда менять лорное население** (например, чума убила N %), и, по смыслу,
   благоприятные события могут его увеличивать — через эффект «население ±%» в шаблоне. Изменение пишется в историю.
6. **Распространение (Q3): да** — у шаблона шанс перекинуться на соседние регионы (соседство — по переходам между
   регионами / по стране; уточняется анализом).
7. **Цепочки:** событие может повышать шанс других (потоп → чума; засуха/голод → бунт); бунт — не случайный, а при
   долгой низкой стабильности.
8. **Видимость для игрока:** активные события в карточке региона (иконка, текст, сколько ещё продлится). Ленты
   новостей пока НЕ делаем (Q6) — пользователь планирует газету; но история событий хранится так, чтобы газета потом
   могла её читать.
9. **Монстры от катастроф — позже (Q5)**, не в этой фиче.
10. Админка: вкладка/раздел событий — шаблоны (CRUD), активные события (список, отмена, ручной запуск), история;
    гайд «Как настроить» и подсказки «?» дополнить.
11. Деньги не появляются и не исчезают (инвариант книги счетов), всё — проводками.

### UX
1. Регион попал в засуху: в карточке «☀ Засуха — урожай погибает, ещё 6 дней». Еда у торговцев дорожает.
2. Через пару пересчётов регион голодает, стабильность падает; если долго — бунт.
3. Админ в «Экономике → События» видит активные события по регионам, может отменить или запустить своё.

### Edge Cases
- Несколько событий в одном регионе одновременно (стекинг эффектов, лимиты множителей).
- Событие на регион без пересчёта (нет шаблона/населения).
- Отмена события админом посреди действия; ручной запуск поверх активного такого же.
- Изменение шаблона события, пока активны его экземпляры.
- Население не может уйти в 0/минус из-за эффектов.
- Ручной «Пересчитать сейчас» не должен ускорять события (время, а не число прогонов).

### Вопросы к пользователю
- [x] Q1 Кто запускает → и случайно, и вручную.
- [x] Q2 Кризис меняет население навсегда → да.
- [x] Q3 Распространение на соседей → да.
- [x] Q4 Частота → раз в игровой сезон (в среднем на регион).
- [x] Q5 Монстры → позже.
- [x] Q6 Лента новостей → нет, будет газета позже; история событий должна быть пригодна для неё.
- [x] Вопросы архитектора 1–5 (отмена не откатывает разовые итоги; повторный ручной запуск отклоняется; без
  переходов — соседи по стране; расход только из положительной казны; правка шаблона не меняет идущие события) →
  пользователь 2026-10-30: «Со всем согласен».

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

All paths below are relative to `services/character-service/app/` unless stated otherwise.

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service | new tables + migration 033, pure modifier/roll module, tick events pass, sim hooks, admin + public API | `models.py`, `alembic/versions/033_*.py`, `econ_sim.py`, `econ_tick.py`, new `econ_events.py` (pure) + `economy_events_crud.py`, `economy_sim_crud.py` (card), `economy_api.py`, `schemas.py`, `econ_core.py` (new op type, see risk R1) |
| locations-service / inventory-service / dungeon-service | only if a new ledger op type is added: byte-identical copy of `econ_core.py` | `app/econ_core.py` (same md5 in all 4 services) |
| frontend | new admin tab «События», card events block, guide + hints, journal label | `components/Admin/EconomyPage/*`, `components/WorldPage/RegionEconomyCard.tsx`, `api/regionEconomy.ts`, `types/economy.ts` |
| user-service | none — reuse `economy:read` / `economy:settings` (`user-service/alembic/versions/0032_add_economy_permissions.py`) | — |

### Existing Patterns
- character-service: **sync** SQLAlchemy, Pydantic v1, Alembic (latest `alembic/versions/032_econ_population_scale.py`, version table `alembic_version_character`). Revision ids ≤ 32 chars.
- Economy layering: pure math (`econ_sim.py`, `econ_merchant.py`, `econ_bank.py` — no DB) ← runner (`econ_tick.py`: load / lock / store / post) ← CRUD (`economy_*_crud.py`) ← router (`economy_api.py`, `_run_write`/`_read` wrappers, `require_permission("economy:*")`).
- Params: frozen `SimParams` (econ_sim.py:58) stored as JSON in `econ_sim_settings.params`; missing keys → defaults (`from_mapping`, :122) — a new key (e.g. `event_rate_per_season`) needs **no migration**, only `schemas.ECON_SIM_PARAM_BOUNDS` (schemas.py:1885) + `EconSimParams` schema (:2234) + frontend `EconomyTick.tsx` param defs + `paramHints.ts SIM_PARAM_HINTS` (typed `Record<keyof EconSimParams>` → TS forces a hint).
- `price_mult` stored in `econ_region_goods` is read **directly by SQL in locations-service** (`locations-service/app/econ_core.py:966` `SQL_REGION_MARKET`, `market_mult` :782) for player shop prices → a price effect written into the stored `price_mult` reaches player shops with zero cross-service change.

### Q1. Where each effect hooks (keep `simulate_region` pure: pass modifiers in)
`simulate_region` (econ_sim.py:398) copies inputs (`replace(good)`, :418) and never writes back `production_per_1000` / `consumption_mult` (the runner stores only stock/norm/price/last_* — econ_tick.py:678-690). Proposal: a frozen `RegionModifiers` dataclass (all identity by default) passed as `mods=None` kwarg; `None` → bit-identical to today (all existing sim/tick tests stay green).

| Effect | Hook | Notes |
|---|---|---|
| production ×N per group | runner: multiply `GoodState.production_per_1000` of the copy before the call (econ_tick.py:664), or inside sim at `potential` (econ_sim.py:435) | Changing the input copy also moves norms of input groups (`norm_stock` counts processing use, :255) — consistent. Not persisted (column never written back). |
| consumption ×N per group | same: multiply `GoodState.consumption_mult` of the copy | Flows into demand (`demand_tick` :278), food need/hunger (:462) and norm (:255) automatically. |
| «больные жители» (fewer workers) | one `labor_mult` applied to all `potential` (econ_sim.py:435) or to every production_per_1000 copy | Consumption unchanged (people still eat). |
| one-shot stock loss (share of groups) | runner, before the sim: reduce `GoodState.stock` (and the locked `EconRegionGood` row) once; flag on the event row | Must be once per event, not per tick (see idempotency). Loss is goods, not money — no ledger. |
| price mult per group | inside sim **after** step 7 (econ_sim.py:475): `good.price_mult *= mods.price[code]` (decide whether to clamp to `price_max`) | Recomputed from stock/norm every tick (no compounding); step 8 income (:478) then uses it; trend `prev_price_mult` (:420) stays meaningful. Column `Numeric(6,3)`. |
| treasury income ×N | step 8, `tax = min(purse, floor(income × tax_rate × mult))` (econ_sim.py:480) | Only changes the purse→region amount — conserved. Country leg is applied by the ledger on top. |
| stability / prosperity ± per tick | after step 9 (:497) / step 10 (:506), clamp 0..100 | Alternative: shift `stab_target`/`prosp_target` (smoother). Per-step effect → a manual run applies one extra delta (acceptable: manual run is a real step anyway). |
| one-shot treasury expense | runner, in the region transaction after `region_tick` (econ_tick.py:695-701): `post_operation(op_type=<new region_event>, legs=[Leg(region_treasury → population_purse)], idempotency_key="region_event:<event_id>", apply_tax=False)` | **Recipient = the region's population purse** («восстановление» = wages to locals): money stays in the region, no tax leg (src is not a TAX_SOURCE kind, econ_core.py:85), `region_treasury` may go negative (`NEGATIVE_ALLOWED_KINDS`, :74) → treasury_after<0 already triggers the `stab_debt_penalty`. Positive one-shots (ярмарка) = purse → treasury would be taxed to the country (TAX_SOURCE). |
| merchants don't restock | runner: pass `dataclasses.replace(params, merchant_take_share=0.0)` to `_merchant_step` (econ_tick.py:718) → `by_take = 0` (econ_merchant.py:290) → no restock; residents still buy | **Zero change to `econ_merchant.py`.** |
| bank panic / loan boom | `_bank_pass` (econ_tick.py:937) → `tick_bank(params=…)` (economy_bank_crud.py:1045/1060): per-region `replace(params, bank_resident_deposit_share=0)` (panic: residents withdraw toward 0, econ_bank.py ~:631-646, limited by bank balance, time-weighted by `bank_resident_adjust`) / `bank_resident_loan_share × N` (boom, limited by `lendable`) | Bank pass runs after the region loop in its own transactions → needs a `{region_id: modifiers}` map computed once per run (events pass) and passed in. Player deposits sit in the separate `bank_deposits` vault — unaffected. |
| population ±% (permanent) | runner, one-shot, inside the region transaction **before** `simulate_region`: update locked `econ_regions.population` | See Q4. |

### Tick structure & where the events pass fits
- `run_tick` (econ_tick.py:777): claim (auto `_claim_auto` :551 slot-unique / manual `_claim_manual` :583, `slot=NULL`) → `_prepare_merchants` (:822) → region loop, **one transaction per region** (`_process_region` :609, skipped when `last_run_id == run_id`) → banks (`_prepare_banks`/`_bank_pass`/`_collection_pass`, :850-853) → finish + `purge_old` (:313).
- Suggested: a new **events pass** between `_prepare_merchants` and the region loop (own short transactions): expire ended events (by wall clock), roll new auto events (**only when `run.slot is not None`**), spread, chains, riot check; then load `{region_id: active events}` once and hand them to `_process_region` and `_bank_pass`. One-shot effects are applied inside the region transaction (atomic with the region row) and flagged on the event row.
- Lock order (econ_tick.py docstring :36-40): `econ_regions → econ_region_goods → npc_shop_items → econ_banks → bank_deposits → bank_loans → characters → econ_accounts`. New `econ_region_events` rows: lock them **after `econ_region_goods`, before `npc_shop_items`** (or only read them in the region transaction and update one-shot flags by id). The events pass creating rows for neighbour regions touches only the events table (no `econ_regions` lock) → no cross-region deadlock.

### Q2. Game calendar
- Backend: `locations-service/app/crud.py:3196` `YEAR_SEGMENTS` — 4 seasons (spring/summer/autumn/winter, `type="season"`, 39 real days) alternating with 4 festivals (beltane/lughnasad/samhain/imbolc, `type="transition"`, 10 days) = 196 days/year; `compute_game_time(epoch, offset_days, now)` :3213 (pure). Config: table `game_time_config` (`epoch`, `offset_days`; model `locations-service/app/models.py:423`, default epoch 2026-03-19). Public `GET /locations/game-time` (`locations-service/app/main.py:2014`). Also `houses.py:2071` already uses «season + festival = 49 days» as a tax period.
- Frontend: `services/frontend/app-chaldea/src/utils/gameTime.ts` (`YEAR_SEGMENTS` :20, `SEGMENT_LABELS` :34 — «Весна…», «Белтайн…», `SEGMENT_ICONS`).
- character-service today: `locations_client.py` (async httpx, only `get_current_game_year`, docstring forbids re-implementing the calendar). The tick is **sync** in a daemon thread. Options for the architect: (a) read `game_time_config` from the shared DB with raw SQL + a mirrored pure segment function (no network in the tick; drift risk → contract test against the locations constants); (b) one sync HTTP `GET /locations/game-time` per run, fallback «season unknown → no season filter». Note: the public endpoint returns epoch/offset/server_time and `computed` — either way character-service only needs the current `segment_name`.
- Probability math: 1 tick = 6 h → 4 ticks/day. Season = 39 d = **156 ticks**; season + festival cycle = 49 d = **196 ticks**. «On average one event per region per game season» → `p_tick = rate / 196` (cycle) or `rate / 156` (if no events during festivals). Then pick one eligible template by weight (filtered by region template + current segment). Manual runs must **not** roll (they are extra steps, `slot NULL`, econ_tick.py:8-10) — otherwise «Пересчитать сейчас» accelerates events.

### Q3. Region adjacency
- `region_transition_arrows` (locations-service `models.py:604`): `region_id`, `target_region_id` (both FK `Regions.id`, CASCADE), `paired_arrow_id`. Neighbours of X = `SELECT target_region_id FROM region_transition_arrows WHERE region_id = X UNION SELECT region_id … WHERE target_region_id = X` (arrows may be one-sided). `arrow_neighbors` (:617) links arrows to locations — not needed.
- Country: `Regions.country_id` (NOT NULL). World: all participating regions (`SQL_PARTICIPATING`, econ_tick.py:266). No Area-level grouping in the econ code (Countries.area_id exists).
- character-service already reads `Regions` by raw SQL (econ_tick.py:266, :658) — same approach for arrows (shared DB, no HTTP). Tests: `region_transition_arrows` is **not** in the shared SQLite DDL (`tests/econ_contract_cases.py SQLITE_DDL`, which is byte-identical in 4 services) → add a local DDL in a character-service test/conftest rather than touching the shared file.
- Only participating regions (`template_code NOT NULL AND population > 0`) should receive spread events.

### Q4. Population
- Stored: `econ_regions.population` (lore number, `models.py:600`); edited by admin `PUT /admin/economy/regions/{id}` → `update_region` (economy_sim_crud.py:246, sets :261, recomputes norms :287) and by «Заполнить» (`fill_regions` :332, only rows with population 0). Sim uses `sim_population = population / population_scale` (econ_sim.py:238).
- History: `econ_region_history.population` per tick (`models.py:665`, written econ_tick.py:732) but purged after `history_retention_days` (60) and with runs beyond `KEEP_RUNS = 500` (econ_tick.py:71, :313) → **not suitable for a permanent newspaper history**; event history table must hold `population_before/after` itself, must not FK-cascade to `econ_tick_runs` (runs are purged), and must be excluded from `purge_old`.
- Changing it from the tick: update the locked row before `simulate_region` → norms (step 6, :468) and demand/production/treasury_target follow automatically next step. Side effects: purse is unchanged → after a plague per-capita liquidity rises (prosperity ↑, :501), stocks relative to the new norm rise (prices ↓); `starting_purse` (:317) is only used by «Заполнить», so a later fill with `return_purse_excess` would pull the «excess» back to emission — mention in the guide. Banks' resident targets depend on the purse, not population — unaffected. Clamp: never ≤ 0 (a 0 population drops the region out of `SQL_PARTICIPATING` and the tick skips it, econ_tick.py:624) — define a floor (e.g. ≥ 1 % of before or ≥ `population_scale`).

### Q5. Player region card
- Public `GET /characters/economy/regions/{region_id}/card` (economy_api.py:254, no auth, no response_model) → `economy_sim_crud.region_card` (:821) → pure `econ_sim.region_card` (:645, «no numbers» rule for money).
- Add `events: [{code, name, icon, text, kind: good|bad, started_at, ends_at}]` in `economy_sim_crud.region_card` (keep the pure card unchanged); remaining days computed on the frontend from `ends_at` (days are not money, OK to show). Decide whether the hidden shape (`participating=false`) also carries events.
- Frontend: `api/regionEconomy.ts` (`RegionCardData` — add optional `events`), `components/WorldPage/RegionEconomyCard.tsx` (141 lines, Tailwind already, rendered at `WorldPage.tsx:682` and `:851`). Icons: both `lucide-react` (used across EconomyPage) and `react-feather` are installed → store an icon **name** string and map it on the frontend.

### Q6. Admin UI
- `components/Admin/EconomyPage/EconomyPage.tsx`: `TAB_LABEL` (:28), `TAB_INTRO` (:47), `tabs` array (:123), render switch (:178-211); tab ids typed in `guideSections.ts` `EconomyTabId` (:53). Guide: `EconomyGuide.tsx` (1104 lines) with `GUIDE_SECTION_IDS`/`GUIDE_SECTION_TITLE` (`guideSections.ts:11/:33`), `GuideIntro`/`GuideLink`, `ParamHint` + `paramHints.ts` (647 lines). Journal op-type labels: `economyLabels.ts:31-36`.
- Permissions: read with `economy:read` (Moderator has it), template CRUD / manual start / cancel with `economy:settings` (Admin). If a treasury-expense effect is fired manually, it is a ledger move of the region's own money (not emission) → `economy:settings` suffices. No new RBAC rows needed (if the architect adds e.g. `economy:events`, the CLAUDE.md §10.13 rule applies: user-service migration + explicit seed in `test_rbac_permissions.py`).

### Q7. Tests & risks
- Test pattern: `tests/test_econ_tick.py:43` — SQLite in-memory + `StaticPool`, `models.Base.metadata.create_all`, seed groups/templates from the 028 migration module (`mig.GROUPS/TEMPLATES/DEFAULT_PARAMS`), `Countries/Regions` DDL added by `tests/conftest.py:62` `after_create` hook; `run_tick(factory, trigger=…, now=…)` with fixed clock; `_assert_ledger_closes` (sum of accounts = 0). Pure tests: `test_econ_sim.py`, `test_econ_merchant.py`, `test_econ_bank.py`.
- **R1 — new op type:** `econ_core.py` is byte-identical in character-, locations-, inventory-, dungeon-service (same md5); `OP_TYPES` (econ_core.py:136) validates every posting → a new `region_event` op type must be added to all 4 copies (+ `economyLabels.ts`). `econ_operations.op_type` is VARCHAR(50) — no DB migration.
- **R2 — idempotency of random rolls:** a resumed run (`_claim_auto` resume, :572) re-executes the events pass. Use a deterministic RNG seeded by `(slot, region_id)` (e.g. `random.Random(f"{slot}:{region_id}")`) **and** a unique key on auto-started events (e.g. `UNIQUE(origin_key)` = `auto:<slot>:<region>`), or a per-run «events done» marker. One-shots: a flag/`applied_run_id` on the event row inside the region transaction + ledger key `region_event:<event_id>` (DuplicateOperation already handled, :747).
- **R3 — manual runs:** no rolls, no spreading, no duration consumption; durations are wall-clock `ends_at`. Riot rule «долгая низкая стабильность» must also be time-based (e.g. `low_stability_since` on `econ_regions`), not «N history rows» — manual runs write history rows too.
- **R4 — stacking:** multiple events per region → multiply mults per group, sum deltas, clamp the product (e.g. 0.1…3) — define limits; a template edit while instances are active: snapshot effects on the instance or read live (decide).
- **R5 — non-simulated regions:** `_process_region` skips regions without template/population (:624) → effects never apply; refuse manual start there or allow «dormant» events.
- **R6 — bank pass separation:** bank modifiers must come from the same per-run map (regions and banks are separate transactions).
- **R7 — CI:** pytest per-test `--timeout=30` (`.github/workflows/ci.yml:63`); keep event tests on a few regions; avoid simulating 156+ ticks in one test — test the roll function pure with an injected RNG.
- **R8 — merchants bound to `params.merchant_take_share`** etc.: per-region `replace(params, …)` must not leak into the global `params` object (it is frozen — `replace` creates a copy, safe).

## 3. Architecture Decision (filled by Architect — in English)

Scope: **region events** — admin-defined templates (effects built from existing sim levers), instances per region
started randomly (scheduled 6 h runs only), by spreading to neighbours, by chains, by long low stability (riot) or by an
admin; effects applied by the tick (per-step modifiers + one-shot effects), shown on the player region card, kept
forever as history for the future newspaper. Everything is in **character-service** (tables, pure maths, tick, API);
the shared `econ_core.py` gains one op type (4 copies). No user-service / nginx / locations-service change
(locations-service is only *read*: `GET /locations/game-time` over HTTP, `region_transition_arrows` / `Regions` by SQL).
Monsters, newspaper feed, notifications — out of scope.

### 3.0 Questions for PM (product decisions not covered by section 1) — design uses the recommended answers

| # | Question | Recommendation (used in this design) |
|---|----------|--------------------------------------|
| Q1 | Admin cancels an event: are its **one-shot** results (dead population, lost stock, spent treasury) rolled back? | **No.** Cancel stops the ongoing effects only (production/prices/stability… from the next recount). One-shots are real history (money already moved by a posting); to compensate, the admin uses the existing tools (population edit, emission/adjust). The confirm dialog says so. |
| Q2 | Manual start of a template that is **already active** in the region. | **Refuse** with «В регионе уже идёт «{name}» — отмените его или дождитесь конца» (one active instance per template per region, also for random starts). For a multi-region start (country / world) such regions are skipped and listed. |
| Q3 | «Neighbours» of a region that has **no transition arrows**. | Fallback: other participating regions of the **same country**. With arrows — only arrow neighbours (both directions). |
| Q4 | Treasury expense when the treasury is empty or in debt. | Expense = share of the **positive** treasury balance (empty treasury → nothing spent, no new debt). Stability effects of the event still hit. |
| Q5 | Template edited while instances of it are running. | Instances keep the **snapshot** taken at start (name, text, icon, effects, chains, spread); edits apply to new starts only. Stable for the newspaper and predictable for the admin; the guide says so. |

### 3.1 Key decisions

1. **Owner: character-service.** It owns `econ_*`, the tick and the sim. New tables `econ_event_templates`,
   `econ_region_events` and column `econ_regions.low_stability_since` (migration `033_econ_region_events`), seeded
   with 14 starter templates.
2. **One table = active events + permanent history.** `econ_region_events` rows are never purged (not touched by
   `purge_old`, no FK to `econ_tick_runs` — runs are purged, no FK to `econ_regions` — region rows are purged);
   they carry snapshots (region/country name-independent ids + `region_name`, template name/text/icon/kind/effects)
   and outcomes (`population_before/after`, stock lost, treasury spent, operation id). The future newspaper reads this
   table (contract documented in `character-service.md`). Volume: ≈ 1 row per region per 49 days.
3. **Snapshot at start** (Q5): an instance copies `name, icon, kind, player_text, effects, chains, spread_chance,
   trigger_kind` from the template; the tick reads only the instance. Template delete → `template_id` SET NULL.
4. **Effects = pure aggregation into existing levers** (3.4). `simulate_region` gets `mods: Optional[RegionModifiers]
   = None`; `None` → the exact current code path (bit-identical results, all existing sim/tick tests unchanged).
   Production/consumption multiply the **input copies** inside the sim (never persisted — the runner does not write
   `production_per_1000` / `consumption_mult` back), price multiplies after step 7 (stored `price_mult` → player shops
   in locations-service follow with no cross-service change), tax income in step 8, stability/prosperity deltas after
   steps 9/10. Merchants and banks get a per-region `dataclasses.replace(params, …)` — **no change** to
   `econ_merchant.py` / `econ_bank.py`.
5. **One-shot effects** (`stock_loss`, `treasury_expense`, `population`) are applied **once per instance** inside
   the region transaction of the **first run (auto or manual) after the start**, guarded by `applied_at` on the
   locked event row (+ ledger key `region_event:e<id>` for money). A manual start therefore shows its one-shots at the
   next recount («Пересчитать сейчас» applies them at once) — this is not acceleration: one-shots happen once.
6. **Time, not runs.** Durations are wall clock (`ends_at`); expiry checks `ends_at <= now` in every run; random
   rolls, spreading, chains and riot checks happen **only in scheduled runs** (`run.slot IS NOT NULL`) with
   probabilities per 6 h slot; the riot rule uses `low_stability_since` (a timestamp). A manual recount is one real
   sim step (per-step deltas apply once more — acceptable, same as for every other lever) but never rolls.
7. **Idempotent rolls.** RNG = `random.Random(f"{slot}:{region_id}:{purpose}")` (str seeds are hashed with SHA-512 —
   stable across processes, independent of `PYTHONHASHSEED`) **and** `UNIQUE(origin_key)` on instances
   (`auto:<slot>:r<region>`, `spread:<slot>:e<source>`, `chain:<slot>:e<source>:<code>`, `riot:<slot>:r<region>`,
   `manual:<request_id>:r<region>`; scope expansions append `:r<target>`). A resumed run re-executes the events pass
   and inserts nothing twice. `UNIQUE(active_key)` (`r<region>:<template_code>` while active, NULL after) enforces
   «one active instance per template per region» against races (admin start ‖ tick).
8. **New ledger op type `region_event`** (justification, since reusing was preferred): the only fitting existing type
   is `region_tick`, but (a) the admin journal **hides `region_tick` by default** (FEAT-182), so a recovery expense
   would be invisible exactly where the admin looks for it; (b) `region_tick` keys are per run/region, while the
   expense must be idempotent **per event** across runs; (c) the newspaper/admin will filter the journal by op type.
   Cost: one constant in 4 byte-identical copies + one contract case (well-trodden FEAT-184 path). No new account
   kind, no new leg type, no DB migration (`op_type` is VARCHAR(50)), battle-pass unaffected (no character leg).
9. **Calendar from locations-service at runtime** (FEAT-154 rule in `locations_client.py`: the calendar is never
   re-implemented): one sync `GET /locations/game-time` per **scheduled** run (timeout 3 s) → `computed.segment_name`.
   Failure → segment unknown → only templates **without** a season filter are eligible (logged). Segment names
   (`spring, beltane, summer, lughnasad, autumn, samhain, winter, imbolc`) are an API vocabulary constant
   `GAME_SEGMENTS` for validation only — no segment lengths or epoch math in character-service. The «season» length
   for the frequency is a sim param `event_season_days = 49` (season 39 + festival 10, hint says so).
10. **Neighbours**: `region_transition_arrows` both directions (raw SQL, shared DB), fallback same country (Q3);
    only participating regions (`template_code NOT NULL AND population > 0`) ever receive events.
11. **RBAC: no new permission.** Read = `economy:read` (Moderator), templates CRUD / start / cancel =
    `economy:settings` (Admin). A treasury expense is the region's own money moving to its residents (not emission).
    No user-service migration, `test_rbac_permissions.py` untouched.

### 3.2 Ledger postings

| Flow | Op type | Legs | Tax | Idempotency key |
|---|---|---|---|---|
| One-shot treasury expense («восстановление») of event E in region R | `region_event` (new) | `T(R) → P(R)` main, amount `floor(max(0, treasury_after_region_tick) × share)` (Σ of the instance's `treasury_expense` effects, capped at 0.9) | none (`apply_tax=False`; dst is not a treasury) | `region_event:e<E>` |

Posted inside the region transaction **after** the `region_tick` posting (same accounts, already locked) and before the
merchant SAVEPOINT; amount 0 → no posting. `metadata = {event_id, template_code, run_id}`. `DuplicateOperation` →
treated as already applied. Nothing else in this feature moves money (stock loss = goods, population = a number).
World invariant unchanged.

### 3.3 DB changes — character-service migration `033_econ_region_events` (revision id 22 chars, down `032_econ_population_scale`)

```sql
ALTER TABLE econ_regions ADD COLUMN low_stability_since DATETIME NULL;   -- riot clock (3.6), set/cleared by the tick

CREATE TABLE econ_event_templates (
  id                 INT          AUTO_INCREMENT PRIMARY KEY,
  code               VARCHAR(32)  NOT NULL,                    -- stable slug, immutable (chains refer to it)
  name               VARCHAR(100) NOT NULL,                    -- «Засуха»
  icon               VARCHAR(32)  NOT NULL DEFAULT 'alert',    -- whitelist EVENT_ICONS (3.5)
  kind               VARCHAR(4)   NOT NULL,                    -- good | bad
  player_text        VARCHAR(500) NOT NULL,                    -- shown on the region card
  admin_note         VARCHAR(1000) NULL,
  trigger_kind       VARCHAR(16)  NOT NULL DEFAULT 'random',   -- random | low_stability | manual
  weight             DECIMAL(7,2) NOT NULL DEFAULT 1.00,       -- relative weight among eligible templates
  duration_min_days  DECIMAL(6,2) NOT NULL,
  duration_max_days  DECIMAL(6,2) NOT NULL,
  scope              VARCHAR(12)  NOT NULL DEFAULT 'region',   -- region | neighbours | country | world
  spread_chance      DECIMAL(5,4) NOT NULL DEFAULT 0,          -- chance to jump to one neighbour over the lifetime
  region_templates   JSON         NULL,                        -- econ_region_templates codes; NULL/[] = any
  seasons            JSON         NULL,                        -- GAME_SEGMENTS names; NULL/[] = any
  effects            JSON         NOT NULL,                    -- list of effects (3.4)
  chains             JSON         NULL,                        -- [{"code": "plague", "chance": 0.3}]
  is_enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  updated_by_user_id INT          NULL,
  created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_econ_event_templates_code UNIQUE (code),
  CONSTRAINT ck_eet_kind CHECK (kind IN ('good', 'bad')),
  CONSTRAINT ck_eet_trigger CHECK (trigger_kind IN ('random', 'low_stability', 'manual')),
  CONSTRAINT ck_eet_scope CHECK (scope IN ('region', 'neighbours', 'country', 'world')),
  CONSTRAINT ck_eet_duration CHECK (duration_min_days > 0 AND duration_max_days >= duration_min_days),
  CONSTRAINT ck_eet_numbers CHECK (weight >= 0 AND spread_chance >= 0 AND spread_chance <= 1)
);

CREATE TABLE econ_region_events (
  id                   BIGINT       AUTO_INCREMENT PRIMARY KEY,
  region_id            BIGINT       NOT NULL,                  -- Regions.id (no FK: history outlives regions)
  region_name          VARCHAR(255) NULL,                      -- snapshot at start (newspaper after a rename/delete)
  country_id           BIGINT       NULL,                      -- snapshot
  template_id          INT          NULL,
  template_code        VARCHAR(32)  NOT NULL,                  -- snapshot
  name                 VARCHAR(100) NOT NULL,                  -- snapshot
  icon                 VARCHAR(32)  NOT NULL,
  kind                 VARCHAR(4)   NOT NULL,
  player_text          VARCHAR(500) NOT NULL,
  trigger_kind         VARCHAR(16)  NOT NULL,
  effects              JSON         NOT NULL,                  -- snapshot (validated list)
  chains               JSON         NULL,
  spread_chance        DECIMAL(5,4) NOT NULL DEFAULT 0,
  origin               VARCHAR(8)   NOT NULL,                  -- random | manual | spread | chain | riot
  parent_event_id      BIGINT       NULL,                      -- source of a spread / chain
  root_event_id        BIGINT       NULL,                      -- first instance of a multi-region (scope) start
  generation           SMALLINT     NOT NULL DEFAULT 0,        -- spread depth
  origin_key           VARCHAR(96)  NULL,                      -- 3.1.7
  active_key           VARCHAR(48)  NULL,                      -- 'r<region>:<code>' while active, else NULL
  status               VARCHAR(10)  NOT NULL DEFAULT 'active', -- active | ended | cancelled
  started_at           DATETIME     NOT NULL,
  ends_at              DATETIME     NOT NULL,
  ended_at             DATETIME     NULL,
  game_segment         VARCHAR(16)  NULL,                      -- calendar segment at start (NULL = unknown)
  run_id               BIGINT       NULL,                      -- run that rolled it (no FK, runs are purged)
  started_by_user_id   INT          NULL,                      -- manual start
  cancelled_by_user_id INT          NULL,
  cancel_comment       VARCHAR(500) NULL,
  applied_at           DATETIME     NULL,                      -- one-shots done (3.1.5)
  applied_run_id       BIGINT       NULL,
  population_before    INT          NULL,                      -- only when a population effect applied
  population_after     INT          NULL,
  outcome              JSON         NULL,                      -- {"stock_lost": {code: units}, "treasury_expense": n, "operation_id": id}
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY ix_ere_template (template_id),                           -- explicit FK index (MySQL gotcha)
  KEY ix_ere_parent (parent_event_id),                         -- explicit FK index
  KEY ix_ere_region_status (region_id, status),
  KEY ix_ere_status_ends (status, ends_at),
  KEY ix_ere_root (root_event_id),
  KEY ix_ere_started (started_at),
  KEY ix_ere_ended (ended_at),
  CONSTRAINT uq_ere_origin_key UNIQUE (origin_key),
  CONSTRAINT uq_ere_active_key UNIQUE (active_key),
  CONSTRAINT fk_ere_template FOREIGN KEY (template_id) REFERENCES econ_event_templates (id) ON DELETE SET NULL,
  CONSTRAINT fk_ere_parent FOREIGN KEY (parent_event_id) REFERENCES econ_region_events (id) ON DELETE SET NULL,
  CONSTRAINT ck_ere_status CHECK (status IN ('active', 'ended', 'cancelled')),
  CONSTRAINT ck_ere_origin CHECK (origin IN ('random', 'manual', 'spread', 'chain', 'riot')),
  CONSTRAINT ck_ere_time CHECK (ends_at >= started_at)
);
```
ORM `EconEventTemplate`, `EconRegionEvent` (`_EconId` for BIGINT ids in SQLite, `server_default`s, `JSON`,
`Numeric`), `EconRegion.low_stability_since`. Seed: the module constant `EVENT_TEMPLATES` (3.9) inserted by
`upgrade()` (tests seed from the migration module like `028`'s `GROUPS/TEMPLATES`). Indexes before FKs in the
migration (MySQL FK-index gotcha). Downgrade: drop `econ_region_events`, `econ_event_templates`, the column
(history is lost on downgrade — documented). Revision id `033_econ_region_events` (22 ≤ 32).

### 3.4 Effects, aggregation, stacking — `econ_sim.RegionModifiers` + new pure `app/econ_events.py`

Effect JSON object: `{"type": …, "groups": [codes] | ["*"], "mult": x, "share": s, "delta": d, "pct": p}` — only the
fields of its type (Pydantic validator 3.8, unknown types in stored JSON skipped with a warning).

| type | fields (bounds) | when | lever |
|---|---|---|---|
| `production` | groups, mult 0…5 | every step | copy `production_per_1000 × m` (input use / norms follow) |
| `consumption` | groups, mult 0…5 | every step | copy `consumption_mult × m` (demand, hunger need, norm) |
| `labor` («больные жители») | mult 0…1.5 | every step | production of **all** groups × m (consumption unchanged) |
| `price` | groups, mult 0.2…5 | every step | after step 7: `price_mult = clamp(price_mult × m, price_min, price_max)` |
| `tax_income` | mult 0…5 | every step | step 8: `tax = min(purse, floor(income × tax_rate × m))` |
| `stability` | delta −10…10 | every step | after step 9: `clamp(stability + d, 0, 100)` |
| `prosperity` | delta −10…10 | every step | after step 10: `clamp(prosperity + d, 0, 100)` |
| `merchants_halt` | — | every step | merchant step with `replace(params, merchant_take_share=0.0)` (no restock; residents still buy) |
| `bank_panic` | — | bank pass | `replace(params, bank_resident_deposit_share=0.0)` (residents withdraw, time-weighted, limited by the bank's cash; player vault untouched) |
| `loan_boom` | mult 1…5 | bank pass | `bank_resident_loan_share = min(0.9, share × m)` |
| `stock_loss` | groups, share 0…0.9 | once | `stock × (1 − share)` on the locked goods rows before the sim |
| `treasury_expense` | share 0…0.9 | once | 3.2 posting after `region_tick` |
| `population` | pct −0.5…0.5 | once | lore population × (1 + pct), floor (below), before the sim |

`groups: ["*"]` = every group. Group codes are validated against `econ_goods_groups` on save. ≤ 12 effects per template.

```python
# econ_sim.py
@dataclass(frozen=True)
class RegionModifiers:
    production: Mapping[str, float] = field(default_factory=dict)   # group -> mult (labor already folded in)
    consumption: Mapping[str, float] = field(default_factory=dict)
    price: Mapping[str, float] = field(default_factory=dict)
    tax_income_mult: float = 1.0
    stability_delta: float = 0.0
    prosperity_delta: float = 0.0

def simulate_region(..., params=DEFAULT_PARAMS, mods: Optional[RegionModifiers] = None) -> SimResult
#   mods is None -> no extra statement executed (bit-identical). Missing group in a map -> 1.0.

# econ_events.py (pure, no DB)
EFFECT_TYPES, PER_STEP_TYPES, ONE_SHOT_TYPES, KINDS, TRIGGERS, SCOPES, ORIGINS, GAME_SEGMENTS, EVENT_ICONS
DAY = 86400; TICK_SECONDS = 21600
@dataclass(frozen=True) class Effect: type; groups: Tuple[str, ...] = (); mult=1.0; share=0.0; delta=0.0; pct=0.0
parse_effects(raw) -> List[Effect]                       # lenient (stored JSON); strict validation lives in schemas
@dataclass(frozen=True) class EventEffects: mods: RegionModifiers; merchants_halt: bool; bank_panic: bool;
                                            loan_boom_mult: float
aggregate(effect_lists: Sequence[Sequence[Effect]], group_codes, params) -> EventEffects
    # per group: product of production mults x product of labor mults; product of consumption / price mults;
    # every product clamped to [params.event_mult_min, params.event_mult_max] (only groups with an effect appear);
    # tax_income product clamped the same; stability / prosperity: sum, clamped to +-params.event_delta_max;
    # loan_boom: product, clamp [1, event_mult_max]; empty input -> EventEffects with identity mods
merchant_params(params, ev) -> SimParams                 # replace(...) only when merchants_halt, else params itself
bank_params(params, ev) -> SimParams                     # panic / boom as in the table, else params itself
one_shots(effects) -> OneShots(stock_loss: Dict[code, share], treasury_share, population_pct)
    # stock shares of several effects on one group combine as 1 - prod(1 - s); treasury shares sum, cap 0.9;
    # population pcts sum, clamp [-0.5, 0.5]
stock_after_loss(stock, share) -> (new_stock, lost)
treasury_expense(treasury_after, share) -> int           # floor(max(0, t) * share)
population_after(population, pct, scale) -> int          # round(pop * (1 + pct)); never below max(1, scale)
                                                         # (sim pop >= 1, region stays participating); pct 0 -> pop
tick_chance(params) -> float                             # clamp(event_rate_per_season * TICK_SECONDS /
                                                         #       (event_season_days * DAY), 0, 1)
per_tick_chance(lifetime_chance, duration_seconds) -> float  # 1 - (1 - c) ** (TICK_SECONDS / max(duration, TICK))
eligible(templates, *, region_template, segment, active_codes) -> list
    # enabled, trigger 'random', weight > 0, region_templates empty or contains region_template,
    # seasons empty or (segment known and in seasons), code not in active_codes
pick_weighted(rng, items) -> item | None
roll_duration_seconds(rng, min_days, max_days) -> int    # uniform, rounded to whole minutes
riot_due(low_since, last_riot_end, riot_active, now, after_days) -> bool
    # not riot_active and low_since is not None and now - max(low_since, last_riot_end or low_since) >= after_days
rng_for(slot, region_id, purpose) -> random.Random       # random.Random(f"{slot}:{region_id}:{purpose}")
```
Stacking example: drought (food ×0.5) + plague (labor ×0.75) → food production ×0.375; a third event with food ×0.2
→ 0.075 → clamped to 0.1. Two `stability −2` → −4 per step (cap ±10).

### 3.5 Sim params (`SimParams` defaults + `ECON_SIM_PARAM_BOUNDS` + `ECON_SIM_INT_PARAMS` + `EconSimParams*` Optional fields; no migration)

| param | default | bounds | meaning (hint text basis) |
|---|---|---|---|
| `events_enabled` | 1 (int) | 0 … 1 | 0 = no automatic starts (random, spread, chains, riots); running events still act; manual start works |
| `event_rate_per_season` | 1.0 | 0 … 10 | average random events per region per game season (before eligibility filters) |
| `event_season_days` | 49.0 | 1 … 400 | real days of one «season» for the frequency (calendar: season 39 + festival 10) |
| `event_max_active` | 3 (int) | 1 … 10 | random/spread/chain starts skip a region with this many active events (manual start and riot ignore it) |
| `event_mult_min` | 0.1 | 0.01 … 1 | lower clamp of a stacked multiplier |
| `event_mult_max` | 3.0 | 1 … 10 | upper clamp of a stacked multiplier |
| `event_delta_max` | 10.0 | 0 … 50 | cap of the summed stability / prosperity change per recount |
| `event_spread_max_depth` | 2 (int) | 0 … 5 | how many hops a spreading event may make (0 = no spreading) |
| `event_riot_stability` | 25.0 | 0 … 100 | stability below which the riot clock runs (card «Бунт» threshold = 25) |
| `event_riot_after_days` | 3.0 | 0.25 … 60 | days of continuous low stability before a riot starts |

At defaults: `tick_chance = 1 × 21600 / (49 × 86400) ≈ 0.0051` per region per scheduled slot → 196 slots per
49 days → on average **one roll success per region per season** (Q4). Frontend: block «События» in `EconomyTick.tsx`
+ `SIM_PARAM_HINTS` (TS forces a hint per key).

### 3.6 Tick integration (`econ_tick.py` + new `app/economy_events_crud.py` tick helpers + `locations_client.py`)

**Events pass** — new `_events_pass(session_factory, run_id, run_slot, summary, params, now)` in `run_tick` **after
`_prepare_merchants`, before the region loop**. Best effort: the whole pass in try/except (missing tables before 033,
any error → warning, `EVENTS_ERROR_PREFIX = "события — ошибка: "` appended to the run error, regions still tick).
1. **Expire** (every run, auto and manual): one transaction — `UPDATE econ_region_events SET status='ended',
   ended_at=ends_at, active_key=NULL WHERE status='active' AND ends_at <= :now` → `summary.events_ended`.
2. If `run_slot is None` (manual) or `params.events_enabled == 0` → skip steps 3–6 (go to 7).
3. `segment = locations_client.get_game_segment_sync()` (new; `httpx.Client(timeout=3)`, `GET
   {LOCATIONS_SERVICE_URL}/locations/game-time` → `computed.segment_name`; any error / bad shape → `None` + warning).
4. Load once (plain reads, one session): enabled templates; participating regions `(region_id, template_code,
   country_id, low_stability_since)`; active instances (snapshot of step 1's result) grouped by region; last ended
   riot (`trigger_kind='low_stability'`) `ended_at` per region; neighbour map (arrows both directions; fallback
   same-country participating regions).
5. Per participating region, ascending id — each **start** is its own short transaction via
   `start_event(session, template_or_snapshot, region_id, origin, origin_key, now, run_id, segment, parent=None,
   generation=0, scope=None, duration_seconds=None, user_id=None) -> StartResult` (shared with the admin start, 3.7):
   a. **Riot**: `riot_due(...)` with `params.event_riot_after_days` → pick (weighted, `rng_for(slot, r, "riot")`) an
      enabled `low_stability` template → origin `riot`, key `riot:<slot>:r<R>`. Ignores `event_max_active`.
   b. **Random**: skip when the region has ≥ `event_max_active` active; `rng = rng_for(slot, r, "auto")`;
      `rng.random() < tick_chance(params)` → `pick_weighted(rng, eligible(...))` → origin `random`, key
      `auto:<slot>:r<R>`.
   c. **Chains**: for each instance active at step 4 in this region (ascending id) and each `chains` entry whose
      template is enabled and not active in the region: `rng_for(slot, r, f"chain:{event_id}:{code}")`, chance
      `per_tick_chance(entry.chance, ends_at − started_at)` → origin `chain`, parent = source, key
      `chain:<slot>:e<source>:<code>`. Chains ignore season and region-template filters (the admin linked them
      explicitly) but respect `event_max_active`.
   d. **Spread**: for each instance active at step 4 with `spread_chance > 0` and `generation <
      event_spread_max_depth`: `rng_for(slot, r, f"spread:{event_id}")`, chance `per_tick_chance(spread_chance,
      duration)` → one neighbour picked uniformly among neighbours without that template active and below
      `event_max_active` → instance in the neighbour with the **source's snapshot**, origin `spread`, parent,
      `generation + 1`, fresh duration from the template range (template deleted → the source's duration), key
      `spread:<slot>:e<source>`. Spread instances use scope `region` (no re-expansion).
   Insert conflicts on `origin_key` / `active_key` (`IntegrityError`) → rollback that start, count as `skipped`
   (resume / race safe). Starts in step 5 never lock `econ_regions` (only `econ_region_events` inserts + plain reads).
6. **Scope expansion** (`start_event`): `region` → [R]; `neighbours` → [R] + neighbours; `country` → participating
   regions of R's country; `world` → all participating. One instance per target that does not already have the
   template active (others skipped); first instance = root, the rest carry `root_event_id`, origin of the root,
   origin_key `<key>:r<target>`, the **same** `started_at` / `ends_at`.
7. After the pass: `active_map = {region_id: [EventSnapshot]}` (status active, `ends_at > now`) loaded once → used by
   the bank pass (R6). Summary counters: `events_ended, events_started, events_spread, events_chained, riots_started,
   events_applied, event_expense_ops, events_failed` (in `RunSummary`, logged, returned by the manual-run endpoint).

**Region transaction** (`_process_region`, signature unchanged; lock order 3.6.1):
- after the goods rows: `SELECT … FROM econ_region_events WHERE region_id = :r AND status = 'active' AND ends_at >
  :now ORDER BY id FOR UPDATE` (skip silently when the table is missing — warning once);
- **one-shots** for rows with `applied_at IS NULL` (ascending id): population (`population_before/after` on the row,
  `region.population` updated **before** `simulate_region` → norms/demand follow), stock loss on the locked goods
  rows (`outcome.stock_lost`), `applied_at = now`, `applied_run_id = run_id`; the treasury share is remembered;
- `ev = econ_events.aggregate([parse_effects(row.effects) …], groups, params)`;
  `simulate_region(…, mods=ev.mods if rows else None)` → when no active events nothing changes;
- after the `region_tick` posting: per row with a remembered treasury share → `treasury_expense(result.treasury_after,
  share)` → `post_operation(op_type=core.OP_REGION_EVENT, legs=[Leg(T, P, amount)], apply_tax=False,
  idempotency_key=f"region_event:e{id}", region_id, metadata)` → `outcome.treasury_expense`, `outcome.operation_id`;
- merchant step gets `econ_events.merchant_params(params, ev)`;
- riot clock: `low_stability_since = (low_stability_since or now) if new stability < event_riot_stability else
  NULL` (every run — it is a timestamp);
- history row unchanged (population column already records the new lore number).
**Bank pass**: `_bank_pass(..., params_for=lambda region_id: econ_events.bank_params(params, ev_by_region[region_id]))`
→ `tick_bank(session, region_id, params=params_for(region_id), …)`; regions without events get `params` itself.

#### 3.6.1 Lock order (supersedes FEAT-184 3.8; `econ_tick.py` docstring + `character-service.md`)

`econ_regions → econ_region_goods → econ_region_events (asc id) → npc_shop_items (asc id) → econ_banks (asc
region_id) → bank_deposits (asc id) → bank_loans (asc id) → characters (asc id) → econ_accounts (asc id)`.

| Flow | Locks |
|---|---|
| region txn | region → goods → its active events → shop rows → NPC chars → accounts |
| events pass expiry / starts | event rows only (UPDATE by status/ends_at; INSERTs); reads of regions/templates/arrows are plain |
| admin start | template row (plain read) → INSERTs into `econ_region_events` (unique keys) |
| admin cancel | the event row `FOR UPDATE` only |
| admin region edit / fill (existing) | unchanged (never touch events) |
Holding nothing else while locking event rows, the events pass and admin flows cannot form a cycle with the region
transaction.

### 3.7 Admin & public API (`economy_api.py` router `/characters`, crud `economy_events_crud.py`)

| Method & path | Auth | Body → response | Errors (Russian) |
|---|---|---|---|
| `GET /characters/admin/economy/events/templates` | `economy:read` | → `List[EventTemplateOut]` (ordered kind, name) + `active_count` per template | — |
| `POST /characters/admin/economy/events/templates` | `economy:settings` | `EventTemplateIn` → `EventTemplateOut` 201 | code taken → 409 «Шаблон с кодом «{code}» уже есть»; unknown group / region template / chain code → 400 «Неизвестная группа товаров: {code}» / «Неизвестный шаблон региона: {code}» / «Цепочка ссылается на неизвестное событие: {code}»; chain to itself → 400 «Событие не может вызывать само себя» |
| `PUT /characters/admin/economy/events/templates/{template_id}` | `economy:settings` | `EventTemplateUpdate` (all of `In` except `code`) → `EventTemplateOut` | 404 «Шаблон события не найден»; same 400s |
| `DELETE /characters/admin/economy/events/templates/{template_id}` | `economy:settings` | → 204 | 404; referenced by chains of other templates → 409 «На это событие ссылаются цепочки: {names}» (running instances keep their snapshot) |
| `GET /characters/admin/economy/events/active?region_id=` | `economy:read` | → `List[RegionEventOut]` (status active, ends_at > now; ends_at asc) | — |
| `POST /characters/admin/economy/events/start` | `economy:settings` | `EventStartIn` → `EventStartOut {started: List[RegionEventOut], skipped: List[EventSkip{region_id, region_name, reason}]}` | template 404; region missing → 404 «Регион не найден»; region not participating → 409 «Регион не участвует в пересчёте — у него нет шаблона или населения»; nothing started (all skipped) → 409 with the first reason, e.g. «В регионе уже идёт «Засуха» — отмените его или дождитесь конца»; same `request_id` again → 409 «Событие уже запущено». Disabled templates **can** be started manually (any trigger). Ignores `event_max_active`. |
| `POST /characters/admin/economy/events/{event_id}/cancel` | `economy:settings` | `EventCancelIn {comment}` → `RegionEventOut` | 404 «Событие не найдено»; not active → 409 «Событие уже закончилось» |
| `GET /characters/admin/economy/events/history` | `economy:read` | query `region_id?, template_code?, kind?, status?, origin?, date_from?, date_to?, page=1, page_size=50 (≤200)` → `RegionEventsPage {items, total, page, page_size}` (started_at desc) | 422 on bad query |
| `GET /characters/economy/regions/{region_id}/card` (changed, public) | — | `+ events: List[RegionCardEvent]` in **both** shapes (`[]` when not participating) | — |
| `GET /characters/admin/economy/regions` (changed) | as is | item `+ active_events: List[EventBadge{name, icon, kind}]` | — |
| `GET/PUT /characters/admin/economy/sim`, `POST …/sim/run` (changed) | as is | 10 params of 3.5; run summary event counters | — |

Routes: declare `/events/templates…`, `/events/active`, `/events/start`, `/events/history` before
`/events/{event_id}/cancel` (int path; no collision with `/admin/economy/templates` — region templates). All writes via
`_run_write` (one transaction, `IntegrityError` on `active_key`/`origin_key` mapped to the 409s above); reads via
`_read`. Logs: ids only. Manual start = `start_event(origin='manual', origin_key=f"manual:{request_id}:r{R}" or NULL,
user_id)`, `segment` = `get_game_segment_sync()` (async endpoint → call it via `run_in_threadpool`; `None` is fine).
Optional `duration_days` overrides the roll (else rolled with `random.Random()` — manual starts need no seed).
Optional `scope` overrides the template scope.

### 3.8 Pydantic v1 schemas (`schemas.py`)

```python
EVENT_ICONS = ("sun", "cloud-rain", "waves", "skull", "biohazard", "zap", "sparkles", "pickaxe", "gem", "beef",
               "swords", "flame", "wheat", "fish", "store", "party-popper", "snowflake", "bug", "coins",
               "heart-pulse", "shield-alert", "alert")                         # mirrored in the frontend icon map
GAME_SEGMENTS = ("spring", "beltane", "summer", "lughnasad", "autumn", "samhain", "winter", "imbolc")
_EVENT_CODE = constr(regex=r"^[a-z][a-z0-9_]{1,31}$")

class EventEffectIn(BaseModel):
    type: Literal["production", "consumption", "labor", "price", "tax_income", "stability", "prosperity",
                  "merchants_halt", "bank_panic", "loan_boom", "stock_loss", "treasury_expense", "population"]
    groups: Optional[conlist(constr(regex=r"^(\*|[a-z][a-z0-9_]{0,31})$"), min_items=1, max_items=12)] = None
    mult: Optional[confloat(ge=0, le=5)] = None
    share: Optional[confloat(ge=0, le=0.9)] = None
    delta: Optional[confloat(ge=-10, le=10)] = None
    pct: Optional[confloat(ge=-0.5, le=0.5)] = None
    # root_validator: exactly the fields of the type (3.4 table), per-type bounds (labor <= 1.5, price >= 0.2,
    # loan_boom >= 1); extra fields -> «Лишнее поле «{f}» для эффекта «{label}»»; missing -> «Для эффекта «{label}»
    # нужно указать {field}»

class EventChainIn(BaseModel):
    code: _EVENT_CODE
    chance: confloat(ge=0, le=1)

class EventTemplateUpdate(BaseModel):
    name: constr(strip_whitespace=True, min_length=2, max_length=100)
    icon: str                                   # validator: in EVENT_ICONS -> «Неизвестная иконка»
    kind: Literal["good", "bad"]
    player_text: constr(strip_whitespace=True, min_length=3, max_length=500)
    admin_note: Optional[constr(max_length=1000)] = None
    trigger_kind: Literal["random", "low_stability", "manual"] = "random"
    weight: confloat(ge=0, le=1000) = 1.0
    duration_min_days: confloat(gt=0, le=365)
    duration_max_days: confloat(gt=0, le=365)    # validator: >= min -> «Максимальная длительность меньше минимальной»
    scope: Literal["region", "neighbours", "country", "world"] = "region"
    spread_chance: confloat(ge=0, le=1) = 0.0
    region_templates: conlist(constr(max_length=32), max_items=50) = []
    seasons: List[str] = []                     # validator: each in GAME_SEGMENTS, deduplicated
    effects: conlist(EventEffectIn, min_items=1, max_items=12)
    chains: conlist(EventChainIn, max_items=10) = []
    is_enabled: StrictBool = True

class EventTemplateIn(EventTemplateUpdate):
    code: _EVENT_CODE

class EventTemplateOut(EventTemplateIn):
    id: int
    active_count: int = 0
    updated_at: Optional[datetime]
    class Config: orm_mode = True

class EventStartIn(BaseModel):
    template_id: conint(gt=0)
    region_id: conint(gt=0, le=ECON_MAX_ID)
    scope: Optional[Literal["region", "neighbours", "country", "world"]] = None
    duration_days: Optional[confloat(gt=0, le=365)] = None
    request_id: Optional[constr(regex=r"^[A-Za-z0-9-]{8,64}$")] = None

class EventCancelIn(BaseModel):
    comment: str
    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)   # 3..500, Russian message

class RegionEventOut(BaseModel):
    id: int; region_id: int; region_name: Optional[str]; country_id: Optional[int]
    template_id: Optional[int]; template_code: str; name: str; icon: str; kind: str; player_text: str
    trigger_kind: str; effects: List[dict]; origin: str; parent_event_id: Optional[int]; root_event_id: Optional[int]
    generation: int; status: str; started_at: datetime; ends_at: datetime; ended_at: Optional[datetime]
    game_segment: Optional[str]; started_by_user_id: Optional[int]; cancelled_by_user_id: Optional[int]
    cancel_comment: Optional[str]; applied_at: Optional[datetime]
    population_before: Optional[int]; population_after: Optional[int]; outcome: Optional[dict]
    class Config: orm_mode = True

class EventSkip(BaseModel): region_id: int; region_name: Optional[str]; reason: str
class EventStartOut(BaseModel): started: List[RegionEventOut]; skipped: List[EventSkip]
class RegionEventsPage(BaseModel): items: List[RegionEventOut]; total: int; page: int; page_size: int
class RegionCardEvent(BaseModel): code: str; name: str; icon: str; kind: str; text: str; started_at: datetime; ends_at: datetime
class EventBadge(BaseModel): name: str; icon: str; kind: str
```
Plus `EconRegionItem.active_events: List[EventBadge] = []`, 10 Optional fields in `EconSimParams*`, run summary
counters (defaults 0). Group / region-template / chain-code existence is checked in the crud (needs the DB).

### 3.9 Starter templates (seeded by `033`, Russian texts; effects at a glance)

Durations in days; `R` = region templates (empty = any); `S` = seasons (empty = any); weight / spread / scope.

| code | name / icon / kind | player text | effects | dur | R | S | w / spread / scope | chains |
|---|---|---|---|---|---|---|---|---|
| `drought` | Засуха / sun / bad | «Солнце выжигает поля — урожай гибнет, хлеб дорожает.» | production food ×0.5, herbs ×0.7; price food ×1.15; stability −0.5 | 6–12 | agrarian, rural, forest, capital, mining, fortress, magic | summer, lughnasad | 3 / 0.25 / region | livestock 0.15 |
| `flood` | Потоп / waves / bad | «Реки вышли из берегов: склады затоплены, поля под водой.» | stock_loss food 0.25, wood 0.15, household 0.1; production food ×0.7; treasury_expense 0.1; stability −1 | 3–6 | port, agrarian, rural, forest | spring, beltane, autumn | 2 / 0.2 / region | plague 0.3 |
| `plague` | Чума / skull / bad | «Мор косит жителей: работать некому, лекари не справляются.» | labor ×0.75; consumption potions ×2, herbs ×1.5; stability −1.5; prosperity −1; population −3 %; treasury_expense 0.05 | 10–20 | any | any | 1 / 0.35 / region | — |
| `magic_disaster` | Магическая катастрофа / zap / bad | «Вырвавшаяся магия отравила источники силы — реагенты рассыпаются в прах.» | production magic ×0.3, potions ×0.6; stock_loss magic 0.4; stability −2; population −1 %; treasury_expense 0.15 | 5–10 | magic, capital | any | 1 / 0.1 / region | — |
| `mine_collapse` | Обвал в шахте / pickaxe / bad | «Своды главной шахты обрушились — рудокопы под завалами.» | production ore_metal ×0.4; stability −1; population −0.5 %; treasury_expense 0.1 | 4–8 | mining, fortress | any | 3 / 0 / region | — |
| `livestock` | Мор скота / beef / bad | «Падёж скота: пастбища пустеют, шкур и мяса всё меньше.» | production food ×0.75, hides_textiles ×0.5; stock_loss hides_textiles 0.1; prosperity −0.5 | 6–12 | agrarian, rural, forest | any | 2 / 0.3 / region | — |
| `raid` | Набег / swords / bad | «Разбойники разорили окрестности: склады разграблены, дороги опасны.» | stock_loss food 0.15, weapons 0.2, ore_metal 0.1; consumption weapons ×1.5, armor ×1.3; merchants_halt; stability −2; prosperity −1; population −0.5 %; treasury_expense 0.1 | 2–4 | fortress, rural, port, agrarian | any | 2 / 0 / region | — |
| `riot` | Бунт / flame / bad | «Жители взбунтовались: лавки закрыты, сборщиков налогов гонят прочь.» | labor ×0.7; tax_income ×0.5; merchants_halt; bank_panic; prosperity −1.5; treasury_expense 0.1 | 3–6 | any | any | trigger **low_stability**, 1 / 0.1 / region | — |
| `harvest` | Урожайный год / wheat / good | «Небывалый урожай — амбары ломятся, хлеб дешевеет.» | production food ×1.4, herbs ×1.2; stability +0.5; prosperity +0.5; population +0.3 % | 10–20 | agrarian, rural, forest, port | summer, lughnasad, autumn | 3 / 0.2 / region | — |
| `magic_anomaly` | Благоприятная магическая аномалия / sparkles / good | «Над краем мерцает сияние — магия течёт щедро, реагенты наливаются силой.» | production magic ×1.8, potions ×1.3; price magic ×0.85; prosperity +0.5 | 5–10 | magic, capital, forest | any | 1 / 0.1 / region | — |
| `rich_vein` | Богатая жила / gem / good | «Рудокопы наткнулись на богатую жилу — металла вдоволь.» | production ore_metal ×1.7, jewelry ×1.2; tax_income ×1.15; prosperity +0.5 | 10–20 | mining, fortress | any | 2 / 0 / region | — |
| `fair` | Ярмарка / store / good | «Большая ярмарка: купцы со всех земель, торг идёт бойко.» | consumption jewelry ×1.2, household ×1.2, hides_textiles ×1.1; price household ×0.9, jewelry ×0.9; tax_income ×1.3; loan_boom ×1.5; prosperity +1; stability +0.5 | 2–4 | capital, port, agrarian | lughnasad, autumn, samhain | 2 / 0 / region | — |
| `festival` | Праздник / party-popper / good | «Народ празднует — песни, угощения и щедрые гуляния.» | consumption food ×1.2, jewelry ×1.2; tax_income ×1.1; stability +2; prosperity +1 | 2–3 | any | beltane, lughnasad, samhain, imbolc | 3 / 0 / **country** | — |
| `good_catch` | Удачный улов / fish / good | «Сети полны рыбы — порт пахнет солью и достатком.» | production food ×1.3, hides_textiles ×1.2; price food ×0.9; prosperity +0.5 | 5–10 | port | spring, summer, autumn | 3 / 0 / region | — |

Chains in the seed: flood → plague 30 %, drought → livestock 15 %. «Засуха/голод → бунт» works through the sim
(hunger → stability → riot clock), not a chain (section 1 rule 7). `admin_note` of each seeded template explains its
intent in one Russian line.

### 3.10 Frontend

- **Types / API**: `src/types/economy.ts` (`EventEffect`, `EventEffectType`, `EventTemplate`, `RegionEvent`,
  `RegionEventsPage`, `EventStartIn/Out`, `EventBadge`, sim params + run counters), `src/api/economyAdmin.ts` (7 calls
  of 3.7), `src/api/regionEconomy.ts` (`RegionCardData.events?: RegionCardEvent[]`).
- **Labels / icons**: new `components/Admin/EconomyPage/eventLabels.ts` — effect type labels + units + `describeEffect
  (effect, groupNames) → «Производство: продовольствие ×0,5»`, origin labels («случайно», «вручную», «перекинулось»,
  «цепочка», «бунт»), scope / trigger / status labels, season labels re-used from `utils/gameTime.ts`
  `SEGMENT_LABELS`; new `src/components/common/EventIcon.tsx` (name → lucide-react component, fallback `alert`;
  the dev verifies each name exists in the installed lucide version and maps missing ones to a close icon).
- **Admin tab «События»** (`EconomyTabId` += `events`, `TAB_LABEL`, `TAB_INTRO` → guide section `events`): new
  `EconomyEvents.tsx` with segmented sub-views:
  - «Активные» — cards: icon, name, region (link-less), kind colour, origin badge, «ещё N дн. M ч», started/ends,
    one-shot outcome («население −1 234», «потеряно на складах…», «из казны на восстановление N»), «Отменить» (settings;
    dialog with comment + note «разовые последствия не откатываются»). Region filter.
  - «Запустить» — template select (all, disabled ones marked), region select (participating regions from
    `GET /admin/economy/regions`), scope override, optional duration, effect preview list; result toast lists started
    regions and skipped reasons; `request_id = crypto.randomUUID()` per submit.
  - «Шаблоны» — list (icon, name, kind, trigger, seasons, applicability, weight, enabled toggle, active count) +
    `EventTemplateEditor.tsx` modal: code (create only), name, icon picker grid, kind, player text with live card
    preview, admin note, trigger, weight, duration range, scope, spread %, region-template checkboxes, 8 season
    checkboxes, chains editor (event select + %), and `EventEffectsBuilder.tsx` (rows: type select → only its fields:
    groups multi-select incl. «все группы», ×mult / share % / ± delta / ± % population; add/remove; Russian inline
    validation mirroring 3.8 bounds). Delete with confirm.
  - «История» — filters (region, event, kind, status, origin, dates), paginated table (desktop) / cards (mobile).
  Settings-only controls hidden without `economy:settings`.
- **Other admin bits**: `EconomyRegions.tsx` — small event icons per region (`active_events`, tooltip name);
  `EconomyTick.tsx` — params block «События» (10 params) + run counters; `economyLabels.ts` — op `region_event`
  «Событие региона»; `paramHints.ts` — 10 hints; `EconomyGuide.tsx` + `guideSections.ts` — section `events` «События
  регионов» (what an event is, effects table in plain words, how often (one per season on average), seasons,
  spreading/chains/riot, one-shots and cancel, snapshot on edit, population changes and the «Заполнить» note) and
  recipe `recipe-events` «Событий слишком много / мало / не случаются» (rate, max active, `events_enabled`,
  applicability/seasons, calendar unreachable); checklist line; «?» `ParamHint`s in the editor fields.
- **Player card** `components/WorldPage/RegionEconomyCard.tsx`: block «События» above the phrases when `events` is
  non-empty: `EventIcon` + name (bad → site red/error token, good → gold/green token from `tailwind.config.js`) + text +
  «ещё N дн.» (< 1 day → «ещё N ч», < 1 h → «скоро закончится»), computed from `ends_at` vs now. No numbers about
  effects.
- All: TypeScript, Tailwind + design system classes (`gold-text`, `gray-bg`, `btn-blue`, `btn-line`,
  `input-underline`, `modal-overlay`, `modal-content`…), no `React.FC`, 360 px (forms stack, tables → cards,
  sub-view switcher scrolls horizontally), every API error toasted in Russian (server `detail` string as is; 422 →
  «Проверьте введённые данные»; no response → «Нет связи с сервером»).

### 3.11 Data flow

```
Scheduled run: claim slot → _prepare_merchants → _events_pass{ expire (UPDATE) → HTTP locations /game-time (segment)
  → per region: riot? / random roll / chains / spread → start_event INSERTs (unique keys) } → active_map
  → per region txn{ region → goods → events FOR UPDATE → one-shots (population, stock) → aggregate → simulate_region(mods)
  → rows → region_tick → region_event T→P (once per event) → merchants (merchant_params) → riot clock → history }
  → bank pass (bank_params per region) → collection → finish
Manual run: same, but _events_pass = expire only (no HTTP, no rolls).
Admin start: POST /events/start → economy:settings → start_event (scope expansion, INSERTs) → EventStartOut;
  one-shots at the next run.
Player: WorldPage → GET /characters/economy/regions/{id}/card → + events (active, ends_at > now) → RegionEconomyCard.
Newspaper (future): SELECT … FROM econ_region_events ORDER BY started_at (never purged, snapshots).
```

### 3.12 Security

- Admin endpoints: JWT via `require_permission` (`economy:read` / `economy:settings`), 401/403 as everywhere;
  ids `> 0`, enums via `Literal`, strings length-limited and stripped, codes by regex, numbers bounded (3.8), group /
  template / chain codes checked against the DB, JSON never passed raw to SQL (all statements parameterised).
- Player card: public as before, exposes only name/icon/kind/text/times — no effect numbers, no money.
- Abuse / stability: random starts only in scheduled slots (no farming via manual runs), unique keys make starts
  idempotent, stacked multipliers and deltas are clamped, population never ≤ 0 (region never silently drops out),
  treasury expense only from positive balance, cancel needs a comment (audit: `cancelled_by_user_id`).
- Rate limit: existing nginx `/characters/` zone. Logs: ids, codes and counts only.

### 3.13 Cross-service effects

- `econ_core.py` ×4 (+ `econ_contract_cases.py` ×4): `OP_REGION_EVENT = "region_event"` in `OP_TYPES` (not a source
  op). locations / inventory / dungeon only get the byte-identical copy; `scripts/check_econ_copies.sh` unchanged.
- locations-service: read-only use of `GET /locations/game-time` (existing public endpoint) and of the tables
  `region_transition_arrows`, `Regions` (raw SQL, as `Regions` already is). Player shop prices follow the stored
  `price_mult` (price effects) with no code change.
- battle-pass: `region_event` has no character legs → not counted by earn/spend missions.
- Economy journal / summary: new op label; invariant unaffected.

### 3.14 Residual risks / out of scope (developers add to `docs/ISSUES.md`)

- No newspaper feed / notifications yet; history is admin-only until the newspaper feature adds a public reader.
- Monsters spawned by catastrophes — later (Q5 of section 1).
- A manual recount applies one more step of per-step stability/prosperity deltas (as for every lever).
- Population changes are permanent; a later «Заполнить» with «вернуть излишек» may move the purse excess of a shrunk
  region back to emission (guide note).
- Calendar unreachable → seasonal templates do not roll in that slot (only season-free ones).
- Template deleted while a spread chain is running: further spreads reuse the source duration.

### 3.15 Deploy

One push. character-service `033` runs at start (auto-migration, seeds 14 templates); the tick tolerates the tables'
absence. After deploy: open «Экономика → События», review the starter set; optionally start «Засуха» manually on a
test region, «Пересчитать сейчас» → one-shots/`region_event` in the journal, card shows the event; summary «Сходится».

## 4. Tasks (filled by Architect, updated by PM — in English)

General for every task: **No commits, no pushes, no `git add`** (the user commits once at the end; a push to main
deploys to prod). Build on whatever is uncommitted in the working tree, never revert it. Backend: Pydantic v1,
sync SQLAlchemy in character-service, `python -m py_compile` on modified files, existing tests stay green (in
particular every `test_econ_sim.py` / `test_econ_tick.py` result must be unchanged — `mods=None` path), pytest per test
< 30 s (CI `--timeout=30`), docs `docs/services/character-service.md` section «Region events (FEAT-187)» (tables,
effects table, tick pass, lock order 3.6.1, API, the **newspaper contract** of 3.1.2), residual risks 3.14 into
`docs/ISSUES.md`. Frontend: `npx tsc --noEmit` and `npm run build` **inside the Docker frontend container** (no node on
host), Tailwind + design system (`docs/DESIGN-SYSTEM.md`), TypeScript, no `React.FC`, 360 px, every API error toasted
in Russian. No prod access.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| B1 | **Shared contract (canonical + copies):** `OP_REGION_EVENT = "region_event"` in character-service `econ_core.py` `OP_TYPES` (docstring line); contract case in `econ_contract_cases.py` (`region_event` `T(R) → P(R)` with `apply_tax=False` accepted, no tax leg, balances move; still rejected as a source op with a source account); add to the runner lists of `test_econ_contract.py`; copy both files verbatim into inventory-, locations-, dungeon-service and extend their runners. | Backend Developer | DONE | `services/{character,inventory,locations,dungeon}-service/app/econ_core.py`, `…/app/tests/econ_contract_cases.py`, `…/app/tests/test_econ_contract.py` | — | `sh scripts/check_econ_copies.sh` passes; contract tests green in all 4 services |
| B2 | **Schema, seed, pure maths:** migration `033_econ_region_events` (3.3: column, 2 tables, explicit FK indexes, CHECKs, uniques, seed `EVENT_TEMPLATES` of 3.9 as a module constant, downgrade) + ORM models; `econ_sim.RegionModifiers` + `mods=None` in `simulate_region` (3.4, no statement executed when `None`); 10 sim params (3.5) in `SimParams`, `ECON_SIM_PARAM_BOUNDS`, `ECON_SIM_INT_PARAMS`, `EconSimParams*`; new pure `app/econ_events.py` (3.4 API: constants, `Effect`, `parse_effects`, `aggregate`, `merchant_params`, `bank_params`, `one_shots`, `stock_after_loss`, `treasury_expense`, `population_after`, `tick_chance`, `per_tick_chance`, `eligible`, `pick_weighted`, `roll_duration_seconds`, `riot_due`, `rng_for`). | Backend Developer | DONE | `services/character-service/app/alembic/versions/033_econ_region_events.py`, `app/models.py`, `app/econ_sim.py`, `app/schemas.py` (params only), new `app/econ_events.py` | — | `alembic upgrade head` / `downgrade -1` / `upgrade head` on local MySQL OK, `SHOW CREATE TABLE` shows FKs + indexes, 14 templates seeded with Russian texts; py_compile OK; old sim/tick tests green unchanged |
| B3 | **Tick integration:** `locations_client.get_game_segment_sync()` (sync httpx, 3 s, `None` on any failure); `economy_events_crud.py` tick part (`start_event` with scope expansion and unique-key conflict handling, neighbour map arrows + same-country fallback, loaders, expiry); `_events_pass` in `run_tick` (3.6 steps 1–7, scheduled-only rolls, seeded RNG, origin keys, counters, `EVENTS_ERROR_PREFIX`, missing tables tolerated); `_process_region` events lock + one-shots + `mods` + `region_event` posting + `merchant_params` + riot clock; `_bank_pass(params_for=…)`; `RunSummary` counters; docstring lock order 3.6.1. | Backend Developer | DONE | `services/character-service/app/econ_tick.py`, new `app/economy_events_crud.py`, `app/locations_client.py` | B1, B2 | local: manual start of «Потоп» (via SQL or B4) + «Пересчитать сейчас» → stock lower once, `region_event` op T→P in the journal (second run: no second op), card prices/stability move; manual runs never create events; an auto slot with `event_rate_per_season` = 1000 starts ≤ 1 random event per region and a resumed run inserts nothing twice; expired events end by clock; invariant `ok` |
| B4 | **Admin & public API:** schemas 3.8; `economy_events_crud.py` admin part (templates list/create/update/delete with DB checks, active list, start via `start_event` with `request_id`, cancel, history with filters + pagination); routes 3.7 in `economy_api.py` (declaration order, `economy:read` / `economy:settings`, Russian errors exactly as 3.7); region card `events` (both shapes) in `economy_sim_crud.region_card`; admin regions list `active_events`; manual-run response counters; docs `character-service.md` «Region events (FEAT-187)» incl. newspaper contract; `docs/ISSUES.md` (3.14). | Backend Developer | DONE | `services/character-service/app/economy_api.py`, `app/economy_events_crud.py`, `app/economy_sim_crud.py`, `app/schemas.py`, `docs/services/character-service.md`, `docs/ISSUES.md` | B3 | curl via :80: templates CRUD (dup code 409, bad group 400, chain to unknown 400, delete referenced 409), start on a region (country scope → several instances with root), start on a non-participating region 409, duplicate active 409, same `request_id` 409, cancel (comment required, second cancel 409), history paging/filters; card shows events; 401 without token, moderator reads but gets 403 on writes |
| F1 | **Admin tab «События»** (3.10): `EconomyEvents.tsx` (Активные / Запустить / Шаблоны / История), `EventTemplateEditor.tsx`, `EventEffectsBuilder.tsx`, `eventLabels.ts`, `components/common/EventIcon.tsx`, tab wiring in `EconomyPage.tsx` / `guideSections.ts` (tab id), types + API. | Frontend Developer | DONE | `src/components/Admin/EconomyPage/{EconomyPage,EconomyEvents,EventTemplateEditor,EventEffectsBuilder}.tsx`, `eventLabels.ts`, `guideSections.ts`, new `src/components/common/EventIcon.tsx`, `src/types/economy.ts`, `src/api/economyAdmin.ts` | B4 contract (3.7, 3.8) — can start from the spec, live check after B4 | tsc + build pass; 360 px without horizontal overflow; effects builder shows only the fields of the chosen type and blocks out-of-bounds values with Russian messages; settings controls hidden for a moderator; start shows started + skipped; cancel dialog warns about one-shots |
| F2 | **Card, regions, params, guide** (3.10): events block in `RegionEconomyCard.tsx` (+ `api/regionEconomy.ts` type), icons in `EconomyRegions.tsx`, params block «События» + run counters in `EconomyTick.tsx`, 10 `SIM_PARAM_HINTS`, op label `region_event`, guide section `events` + recipe `recipe-events` + checklist line in `EconomyGuide.tsx`, `TAB_INTRO.events`. | Frontend Developer | DONE | `src/components/WorldPage/RegionEconomyCard.tsx`, `src/api/regionEconomy.ts`, `src/components/Admin/EconomyPage/{EconomyRegions,EconomyTick,EconomyGuide,EconomyPage}.tsx`, `paramHints.ts`, `economyLabels.ts`, `guideSections.ts` | F1 (types, EventIcon), B4 contract | tsc + build pass; 360 px; card shows «ещё N дн.» / «ещё N ч»; journal shows «Событие региона»; every new param has a «?» hint; guide links from the tab intro land on the section |
| Q1 | **QA pure + contract:** `test_econ_events.py` — `aggregate` (products, labor folded into every group, clamps min/max, delta cap, identity on empty), `merchant_params`/`bank_params` (no leak into the global params), `one_shots` combination, `stock_after_loss`, `treasury_expense` (negative/zero treasury → 0), `population_after` (floor = scale, ±50 %, 0 % unchanged), `tick_chance` (default ≈ 0.0051, mean over 196 seeded slots × many regions ≈ 1 ± tolerance, rate 0 → 0, clamp 1), `per_tick_chance`, `eligible` (template / season / unknown segment / active / trigger / disabled / weight 0), `pick_weighted` determinism, `roll_duration_seconds` bounds, `riot_due` cases, `rng_for` stable across calls; `simulate_region(mods=None)` equals the old result **and** `mods=RegionModifiers()` equals it too; each lever moves its output in the expected direction; contract case in 4 services. | QA Test | DONE | new `services/character-service/app/tests/test_econ_events.py`, `services/*/app/tests/test_econ_contract.py` (if needed) | B1, B2 | pytest green in 4 services; copies check passes |
| Q2 | **QA tick:** SQLite tick tests (fixed clock, few regions): scheduled run rolls with a forced rate (deterministic, ≤ 1 random per region per slot), manual run never rolls / spreads / chains, resumed run (same slot) inserts nothing new, expiry by `ends_at` in manual and auto runs, one-shots applied exactly once across 2 runs (population floor, stock loss, `region_event` op T→P untaxed, `_assert_ledger_closes`), merchants halt (no restock), bank panic / loan boom change only that bank's resident flows, spread to an arrow neighbour (local `region_transition_arrows` DDL in a character-service conftest/test — **not** the shared DDL) and same-country fallback, chain start, riot after `event_riot_after_days` of low stability by time (manual runs do not shorten it; riot not restarted until low again after its end), scope country/world skip already-active regions, stacking caps, calendar `None` → only season-free templates, events pass failure does not stop regions, missing tables tolerated. | QA Test | DONE | new `services/character-service/app/tests/test_econ_events_tick.py`, `app/tests/conftest.py` (local arrows DDL only if placed there) | B3 | pytest green; each test < 30 s |
| Q3 | **QA API:** RBAC (401, moderator read OK / write 403, admin OK), template CRUD validation (every 3.8 bound, per-type fields, unknown group/region template/chain/self-chain, dup code, delete referenced, immutable code), start (scope expansion + root ids, non-participating 409, duplicate active 409 + race via `active_key`, `request_id` 409, disabled template manual OK, duration override), cancel (comment, twice), active/history filters + pagination, card `events` in both shapes (no effect numbers), admin regions `active_events`, security (SQL-like strings in names/codes, huge numbers, wrong types → 422). | QA Test | DONE (B4: 67 tests + R1: 28 cases in `test_econ_events_admin_api.py`) | new `services/character-service/app/tests/test_econ_events_api.py` | B4 | pytest green; each test < 30 s |
| R1 | **Review + live on local:** 4 copies identical, `mods=None` bit-identical, lock order 3.6.1, security checklist, py_compile / pytest (character, inventory, locations, dungeon) / tsc / build re-run; **live**: «События» tab — edit a template, start «Засуха» on a region and «Праздник» with country scope, «Пересчитать сейчас» → one-shot outcome + `region_event` in the journal, card on the world page shows the events with remaining time, cancel one (comment), history lists all; sim params block saves; 360 px for the tab, editor and card; zero console errors; summary «Сходится». | Reviewer | DONE (PASS) | all | B1–B4, F1–F2, Q1–Q3 | Checklist passed, invariant `ok` after the live scenario |

Parallelism: B1 and B2 in parallel; B3 after both; B4 after B3 (shares `economy_events_crud.py` — B3 owns the tick
section incl. `start_event`, B4 the admin section). F1 may start from 3.7/3.8 right away (live check after B4); F2 after
F1. Q1 after B1 + B2; Q2 after B3; Q3 after B4. R1 last.

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-10-30
**Result:** PASS

#### Scope checked
Full uncommitted diff (backend character-service + 4 econ_core copies + contract cases, migration 033, frontend tab / card / params / guide).

#### Correctness / invariants
- **Money conservation:** the only new money flow is `region_event` (`T(R) -> P(R)`, single `main` leg, `apply_tax=False`, key `region_event:e<id>`), amount = `floor(max(0, treasury after region_tick) x share)` -> never from a non-positive treasury, never a new debt. Live: op 371 has exactly one `main` posting (72), invariant `ok` after the run.
- **Lock order 3.6.1:** region txn locks region -> goods -> its active events (`FOR UPDATE`, asc id) -> shop rows -> NPCs -> accounts; events pass / admin start only INSERT/UPDATE event rows with plain reads; admin cancel locks one event row. No cycle.
- **Idempotency:** `rng_for(slot, region, purpose)` (str seed, SHA-512), `UNIQUE(origin_key)` (`auto/riot/chain/spread:<slot>...`, scope suffix `:r<target>`), `UNIQUE(active_key)`; a resumed run re-rolls identically and `IntegrityError` -> skip; chains / spreading skip sources rolled by the same run. One-shots guarded by `applied_at` on the locked row + ledger key.
- **Scheduled-only rolls:** steps 2-6 run only when `slot is not None and events_enabled`; expiry (wall clock `ends_at <= now`) runs in every run. Live manual run: 0 started, 5 applied, 1 expense op.
- **Riot:** `low_stability_since` timestamp set / cleared in the region txn; `riot_due` counts from max(low_since, last riot end); ignores `event_max_active`; disabled riot templates excluded.
- **Spreading / chains:** per-slot chance derived from the lifetime chance; depth limit; arrows both directions with same-country fallback; only participating regions; spread keeps the source snapshot.
- **Population:** permanent, floor `max(1, population_scale)`, applied before `simulate_region`, before/after stored on the instance.
- **Merchant / bank overrides:** `dataclasses.replace` per region only (`merchant_params`, `bank_params` via `params_for`); global params untouched.
- **`mods=None`:** no new statement executed; existing sim / tick tests unchanged (only the param-seed test filter was extended for the new `event_*` keys).
- **Calendar fail-soft:** `get_game_segment_sync` (3 s, any error -> `None` + warning; unknown segment -> `None`); only season-free templates eligible then; called lazily once per scheduled run.
- **RBAC:** reads `economy:read`, writes `economy:settings` (tests: 401 without token, moderator 403 on writes). Pydantic v1 syntax; Russian errors.
- **Migration 033:** revision id 22 chars, down 032; explicit FK indexes before FKs; CHECKs / uniques; re-runnable DDL + seed; downgrade drops both tables and the column. Local MySQL at `033_econ_region_events`, `SHOW INDEX` matches the spec (downgrade not re-run by the reviewer to keep the live events; B2 logged up / down / up OK).
- **14 starter templates:** Russian texts fine; every group / region-template code exists in the local DB; effects sensible (flood -> plague 30 %, drought -> livestock 15 %; riot = `low_stability`; festival = country scope on festival segments).
- **Guide / hints:** checked against the code (rates, defaults, caps, riot rule, one-shot timing, snapshot on edit, fill-excess note, «Пересчёт» param labels) — factually correct, no text fixes needed.
- **Frontend rules:** TypeScript, Tailwind + design-system classes, no `React.FC`, no `alert`/`confirm` (ModalShell / ConfirmationModal), every API error toasted in Russian.

#### Q3 coverage
B4's 67 tests covered most of Q3. Small gaps were closed by the reviewer (28 new cases appended to `tests/test_econ_events_admin_api.py`, 95 pass in 9 s): `neighbours` scope (same-country fallback and arrow neighbours in both directions with a local `region_transition_arrows` table), race on `active_key` mapped to the Russian 409, the remaining 3.8 bounds / wrong types (weight, durations, note / name lengths, region templates, chains count / chance, delta / share / mult / pct, groups count / regex / empty, bad enums, 1e308), PUT validation 422, SQL- / HTML-like strings stored literally and echoed on the card, start wrong types. Q3 marked DONE.

#### Fixes made by the reviewer
| # | File | Fix |
|---|------|-----|
| 1 | `services/frontend/app-chaldea/src/components/Admin/EconomyPage/EconomyEvents.tsx:552` | Start confirmation read «…1 дн.. Разовые…» (double period after «дн.») -> «…1 дн.; разовые эффекты сработают…» |
| 2 | `services/character-service/app/tests/test_econ_events_admin_api.py` | Q3 gap tests (above) |

#### Notes (non-blocking)
- `origin_key` is VARCHAR(96): a 64-char `request_id` with very long region ids could in theory exceed it on a world-scope start; with real region ids the maximum is ~85. No action.
- A running instance of a template disabled later can still spread (it lives by its snapshot) — consistent with Q5; the «Включено» hint lists only random / chain / riot.
- Already in `docs/ISSUES.md` (B4): a manual event that ends before the first recount never applies its one-shots; approximate `events_ended` in the runs list.
- Compact population in the active list shows «24.0 к» (dot) — pre-existing `utils/compactNumber` format (FEAT-186), not this feature.

#### Automated Check Results
- [x] `py_compile` (all modified / new backend files) — PASS
- [x] pytest character-service `python -m pytest tests -q -p no:warnings` — PASS (3202 passed, 1 skipped, exit 0; reviewer-extended file 95 passed)
- [x] pytest inventory — PASS (2102 passed, 1 skipped, exit 0)
- [x] pytest locations `--asyncio-mode=auto` — PASS (2214 passed, exit 0)
- [x] pytest dungeon `--asyncio-mode=auto --timeout=30` — PASS (exit 0)
- [x] pytest battle-pass — PASS (164 passed, exit 0)
- [x] `sh scripts/check_econ_copies.sh` — PASS
- [x] `npx tsc --noEmit` (frontend container, EffectRunes filtered) — PASS (no errors)
- [x] `npx vite build --outDir /tmp/build-r7` — PASS
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, localhost, admin) — PASS

#### Live Verification Results
- Pages: `/admin/economy` (tab «События» — Активные / Запустить / Шаблоны / История; «Регионы»; «Пересчёт»; «Как настроить»), `/world/region/10`.
- Active list showed events 1–6 on regions 9/10/14/15/34 with one-shot outcomes (population, stock lost, treasury expense).
- Start via the form: «Засуха» on Шепшир (10), 1 day -> started, result block; again -> 409 «В регионе уже идёт «Засуха» — отмените его или дождитесь конца» (toast). «Праздник» country scope from 9 -> instances 13/14/15 on 9/10/34 with root 13; same `request_id` -> 409 «Событие уже запущено»; unknown region -> 404 «Регион не найден».
- «Потоп» on 15 + «Пересчитать сейчас» (run 58, manual): 0 started, 5 applied, 1 expense op (`region_event:e16`, 72, one untaxed leg), stock lost recorded; result line «События: разовых последствий: 5, расходов казны: 1…»; summary invariant `ok` («Сходится»).
- Cancel via dialog with comment (event 15) -> cancelled, comment + user stored, listed in «История».
- Template editor «Засуха»: out-of-range multiplier shows «Значение от 0 до 5»; weight 3 -> 4 saved; restored to 3.
- Regions list shows event badges; player card on `/world/region/10` lists «Праздник / Засуха / Мор скота» with texts and «ещё 11 ч / 23 ч / 9 дн.».
- 360 px (iframe): events sub-views, template editor modal and the world card — no horizontal overflow. Console errors: none. API responses: all as expected.

#### Data created on local (left in place: history is permanent by design, all expire within a day)
Events 12 (drought, region 10), 13–15 (festival country scope; 15 cancelled), 16 (flood on 15: stock loss + `region_event` op 371 of 72); manual run 58; template «Засуха» `updated_at` changed (weight restored to 3).

## 6. Logging (all agents — in Russian)

```
[LOG] 2026-10-30 — PM: фича создана, ответы пользователя на 6 вопросов записаны, запускаю анализ
[LOG] 2026-10-30 — Codebase Analyst: анализ готов — точки подключения эффектов в econ_sim/econ_tick, календарь (сезон 156 тиков, цикл 196), соседство по region_transition_arrows, риски (op type в 4 копиях econ_core, идемпотентность бросков, ручные пересчёты)
[LOG] 2026-10-30 — Architect: спроектировано — 2 новые таблицы + колонка (миграция 033, 14 стартовых шаблонов), чистый модуль econ_events, mods в simulate_region (без событий результат прежний), новый тип операции region_event, проход событий в пересчёте (броски только в плановых слотах), 8 API; 10 задач (B1–B4, F1–F2, Q1–Q3, R1), 5 вопросов к PM с рекомендациями
[LOG] 2026-10-30 — Backend Developer: B1 готово — тип операции region_event в econ_core (4 одинаковые копии, check_econ_copies проходит), 2 контрактных сценария (казна→кошелёк жителей без налога, идемпотентность по событию, без источников денег) + тест типа в 4 раннерах; pytest: inventory/locations/dungeon зелёные, character — 2 падения только из-за незавершённой B2 (новые event_* параметры ещё не в сиде миграции)
[LOG] 2026-10-30 — Backend Developer: B2 готово — миграция 033 (econ_event_templates + econ_region_events, колонка low_stability_since, 14 стартовых шаблонов с русскими текстами), ORM-модели, чистый модуль econ_events, RegionModifiers и mods=None в simulate_region (без событий результат побитово прежний), 10 параметров событий; миграция вверх/вниз/вверх на локальной MySQL ок, character-service: 3050 тестов зелёные
[LOG] 2026-10-30 — Frontend Developer: F1 готово — вкладка «События» (Активные с отменой и комментарием, Запустить с подтверждением и списком пропусков, Шаблоны с редактором и конструктором эффектов, История с фильтрами и страницами), EventIcon, eventLabels, типы и 8 API-функций, подсказки «?» к полям событий и каждому типу эффекта; tsc и build проходят, живая проверка — после B4 (эндпоинты пока 404)
[LOG] 2026-10-30 — Frontend Developer: F2 готово — блок «События» в карточке региона для игроков (иконка, название, текст, «ещё N дн./ч»), иконки событий в списке регионов, 10 параметров «События» в «Пересчёте» с подсказками «?», счётчики событий в списке пересчётов и итоге ручного, операция «Событие региона», раздел гайда «События регионов» + рецепт + шаг чек-листа, вступление вкладки; tsc и build проходят
[LOG] 2026-10-30 — QA Test: Q1 готово — tests/test_econ_events.py (41 тест, ~6 с): стекинг и лимиты, mods=None/пустые mods побитово как раньше, направление каждого рычага, разовые эффекты (0.9, «*», казна только из плюса, население с полом и лимитом роста), частота ≈1 событие на регион за сезон (сид), детерминизм rng между процессами, отбор по шаблону/сезону, взвешенный выбор, шанс распространения/цепочек за жизнь, бунт по часам; контракт region_event зелёный во всех 4 сервисах (locations/dungeon — с --asyncio-mode=auto, как в CI); багов в чистом модуле нет; падения test_econ_tick*/regions_api сейчас — из-за незавершённой B3 (_events_pass не определён)
[LOG] 2026-10-30 — Backend Developer: B3 готово — проход событий в пересчёте (окончание по часам в каждом прогоне; бунт/случайные/цепочки/распространение только в плановых слотах, броски по слоту+региону, уникальные origin_key — повторный прогон ничего не дублирует; сезон из locations-service только когда нужен, при сбое — только события без сезона), в транзакции региона блокировка событий, разовые эффекты один раз (население, запасы, расход казны операцией region_event казна→кошелёк без налога), mods в расчёте, параметры торговцев и банка, часы бунта; start_event с областью; счётчики в сводке. Тесты test_econ_tick_events.py (14), character: 3105 зелёных; на локальной MySQL: ручной запуск «Потопа» → запасы −25 % один раз, одна операция region_event, плановый прогон (принудительная частота) запустил 5 событий, повтор — 0, событие закончилось по часам, инвариант сходится
[LOG] 2026-10-30 — QA Test: Q2 готово — tests/test_econ_events_tick.py (30 тестов, ~5 с): броски точно по сиду (rng_for → eligible → pick_weighted → длительность), падение посреди планового прогона + возобновление — ничего не задвоено, разовые эффекты по одному разу; окончание по часам в плановых прогонах, ручные не ускоряют; распространение по стрелке в обе стороны, запасной вариант «та же страна», глубина, снимок источника; цепочки (лимит, выключенный шаблон, без фильтра сезона); бунт по времени + пауза после конца бунта, игнор лимита активных; население ± навсегда с полом, потеря запасов всех групп, расход казны = доля казны после пересчёта (сумма долей ≤ 0.9, одна проводка без налога, из долга — 0); стекинг с лимитами; торговцы/банк (паника, бум займов) только в своём регионе; календарь недоступен → только события без сезона; неучаствующие регионы; сбой прохода событий; счётчики сводки; после каждого сценария сумма мира 0 и инвариант сводки ok. Багов в B3 не найдено. Полный прогон character: 4 падения — проверки формы карточки/списка регионов (новые ключи events/active_events из идущей B4), не мои
[LOG] 2026-10-30 — Backend Developer: B4 готово — админ-API событий (шаблоны CRUD с проверкой групп/шаблонов регионов/цепочек, активные, ручной запуск с областью и request_id, отмена с комментарием, история с фильтрами и страницами), events в карточке региона (обе формы), active_events в списке регионов, счётчики событий в списке прогонов; русские 400/404/409; тесты test_econ_events_admin_api.py (67), обновлены ожидания формы в test_econ_regions_api/test_econ_banks_admin_api; character: весь набор зелёный; живая проверка через :80 пройдена; документация и остаточные риски в ISSUES.md (вкл. «ручное событие, закончившееся до пересчёта, не применяет разовые эффекты»)
[LOG] 2026-10-30 — Reviewer: проверка R1 завершена, результат PASS — деньги сходятся (region_event только казна→кошелёк без налога), порядок блокировок, идемпотентность, броски только в плановых прогонах; все тесты и сборка зелёные; живая проверка (запуск, область «страна», дубль 409, пересчёт, отмена, шаблон, карточка, 360 px, «Сходится»); добавлено 28 тестов API (Q3 закрыт), исправлена двойная точка в подтверждении запуска
```

## 7. Completion Summary (filled by PM on close — in Russian)

**Сделано (2026-10-30):** события регионов — кризисы и благоприятные модификаторы. 14 стартовых шаблонов (засуха,
потоп, чума, магическая катастрофа, обвал в шахте, мор скота, набег, бунт; урожайный год, благоприятная магическая
аномалия, богатая жила, ярмарка, праздник, удачный улов), редактор шаблонов с 13 видами эффектов. Случайный запуск
только в плановом 6-часовом пересчёте (≈ одно событие на регион за игровой сезон, по сезону календаря), ручной запуск
на регион / соседей / страну / мир и отмена. Длительность по реальному времени, распространение на соседей (переходы,
иначе страна), цепочки, бунт при долгой низкой стабильности, разовые итоги (потеря запасов, расход казны проводкой
`region_event`, население ± навсегда). История событий хранится навсегда — для будущей газеты. Игрок видит события в
карточке региона; админ — вкладка «События», значки в регионах, 10 параметров в «Пересчёте», раздел гайда.

- `econ_core.py` ×4: тип операции `region_event`; character-service: миграция 033, `econ_events.py`, проход событий в
  тике, API (8 эндпоинтов, права `economy:read` / `economy:settings`).
- Тесты: character 3202 (+28 от ревьюера), inventory 2102, locations 2214, dungeon, battle-pass 164; ревью PASS с живой
  проверкой.

**Остаточные риски:** `docs/ISSUES.md` → «События регионов» (в т.ч. ручное событие, истёкшее до пересчёта, не
применяет разовые итоги). **Монстры от катастроф** — отдельной задачей позже.
