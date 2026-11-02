# FEAT-194: Экономика — классы жителей и норма богатства

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-02 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Продолжение экономики: FEAT-181 (книга счетов), FEAT-182 (живые регионы), FEAT-183 (торговцы), FEAT-184 (банки),
FEAT-186 (масштаб населения), FEAT-187 (события), FEAT-191 (монетный двор и квота), FEAT-192 (караваны),
FEAT-193 (заказы гильдии + правки банков).

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас регион описывается одним числом населения, а деньги жителей (кошелёк населения) почти ни на что не влияют:
налог считается только от производства, потребление денег не двигает, поэтому большие кошельки лежат мёртвым грузом
(на проде кошелёк ≈ 6 дней дохода). Если включить квоту/чеканку или игроки принесут деньги, регионы могут бесконечно
богатеть. Пользователь хочет, чтобы:
- регионы различались составом жителей — бедные / зажиточные / богатые;
- этот состав влиял на богатство региона, налоги, стабильность и покупательную способность;
- регионы **не богатели бесконечно**, но и **не выравнивались** между собой: столица остаётся богатой, бедный край —
  бедным, пока что-то не изменится.

### Бизнес-правила (согласовано с пользователем 2026-11-01/02)
- У каждого участвующего региона есть **доли трёх классов**: бедные, зажиточные, богатые (в сумме 100 %).
  Стартовые доли задаёт шаблон региона (столица — больше богатых, шахтёрский — больше бедных и т. п.), админ может
  поправить их под лор.
- **Доли двигаются сами** (медленно): часть людей переходит вверх при процветании, сытости и деньгах на жителя выше
  нормы; вниз — при голоде, долгах, дороговизне и нехватке денег.
- **Норма богатства** (объединено с этой фичей по решению пользователя): нормальный уровень денег жителей зависит от
  состава классов. Регион с излишком денег сверх нормы «остывает» (богатые платят налог с накоплений; излишек частично
  уходит из мира — «траты на храмы, праздники, заморских купцов»), бедный — подтягивается (квота сезона идёт только
  регионам ниже нормы, пропорционально нехватке).
- **Влияние классов:**
  - **спрос**: бедные — еда, быт, немного инструментов; зажиточные — плюс оружие, броня, зелья, инструменты;
    богатые — плюс украшения, магические материалы, всё дорогое;
  - **налог**: бедные почти не платят, зажиточные — основная база, богатые платят много, в том числе с накоплений;
  - **стабильность**: много бедных — недовольство; голод бьёт по бедным первым; богатые недовольны высокими налогами;
  - **покупательная способность**: при росте цен бедные первыми перестают покупать, богатые покупают и дорогое.
- **Видимость:** игрокам — **слова и полоска из трёх цветов, без процентов** («Бедный край: много бедняков»,
  «Богатый город»). Админу — точные доли, сдвиги за пересчёт, деньги на жителя по классам.
- Все коэффициенты — настройки в админке с подсказками «?» и разделом гайда.

### UX
1. Игрок открывает регион → в карточке строка вроде «Зажиточный город» и полоска бедные/зажиточные/богатые.
2. Админ в «Экономике» видит доли по регионам, может задать стартовые доли шаблонам и поправить конкретный регион.

### Edge Cases
- Регион без шаблона / не участвует — классов нет.
- Существующие регионы на проде при выкатке получают доли по своему шаблону.
- Сумма долей всегда 100 %, ни одна доля не уходит в минус.

### Вопросы к пользователю
- [x] Двигаются ли классы сами → да, медленно
- [x] Что видят игроки → слова и полоска, без процентов
- [x] Объединить с нормой богатства → да

### Решения пользователя после анализа (2026-11-02, «всё как предлагаешь, в 4 убери сжигание»)
1. **Карточка:** первая фраза «Бедный/Скромный/Зажиточный/Богатый регион» (сейчас от процветания) заменяется
   классовой (напр. «Зажиточный город, много бедняков») + полоска; процветание остаётся в других фразах
   («Регион процветает» / «в упадке»), без двух похожих «Богатый …».
2. **Полоска без цифр:** игроку уходят грубые слова по каждому классу («мало / средне / много»), страница рисует
   ширину; точные проценты не отдаются даже в API (правило «никаких цифр в карточке» сохраняется).
3. **Квота сезона:** «ниже нормы» = деньги жителей + казна региона ниже нормы; квота делится только между такими
   регионами пропорционально нехватке; если ниже нормы никого нет — квота за сезон не выдаётся.
4. **Излишок сверх нормы:** **только** налог с накоплений богатых — по умолчанию 2 % излишка за пересчёт идёт в казну
   региона (настройка). **Сжигания (ухода денег из мира) нет** — новый тип операции не нужен.
5. **Гранты страны:** небольшой перевес в пользу регионов ниже нормы (настройка, по умолчанию 25 % пула гранта
   делится по нехватке, остальное — по населению).
6. **Сброс долей:** «Применить шаблон» сбрасывает доли классов к шаблону; «Заполнить регионы» сохраняет вручную
   поправленные доли, плюс отдельная галочка «сбросить и классы».
7. **События:** новый эффект событий — прямой сдвиг долей классов (например «Разорение» — вниз, «Золотая жила» /
   «Ярмарка» — вверх).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

All paths below are relative to `services/character-service/app/` unless stated otherwise.

### 2.1 Affected services

| Service | Change | Files |
|---|---|---|
| character-service | sim math, tick, quota split, new op type, migration 037, admin/player API | `econ_sim.py`, `econ_tick.py`, `econ_mint.py`, `econ_core.py`, `econ_bank.py` (opt.), `econ_merchant.py` (opt.), `economy_sim_crud.py`, `economy_api.py`, `schemas.py`, `models.py`, `alembic/versions/037_*.py`, tests |
| inventory-, locations-, dungeon-service | **only** if a new ledger op type is added: byte-identical `econ_core.py` + `tests/econ_contract_cases.py` copies (CI `econ-contract-copies`, `scripts/check_econ_copies.sh`) | `app/econ_core.py`, `app/tests/econ_contract_cases.py` |
| frontend | admin tabs Regions / Templates / Tick params / Guide, op label, player region card | see 2.8 |
| battle-pass-service | none (a purse→emission op never touches a `character` account, `battle-pass-service/app/crud.py:395-428`) | — |

Patterns: character-service = sync SQLAlchemy, Pydantic v1, Alembic (`alembic_version_character`, head `036_econ_guild_orders`). Sim math is pure (`econ_sim.py`), tick only loads/stores/posts (`econ_tick.py:1-100` docstring has the global lock order).

### 2.2 How the region simulation works today (`econ_sim.simulate_region`, `econ_sim.py:450-585`)

- Population: lore number in `econ_regions.population`; math uses `sim_population = pop / population_scale` (`:290-299`, default scale 100, so Хикари 4M -> 40k).
- **Demand** (`demand_tick`, `:330-342`): `norm_per_1000 × consumption_mult × pop_k × prosp_factor × price_factor × dt`; `prosp_factor = 1 + prosperity_elasticity × (prosperity-50)/50` (group elasticities seeded in `alembic/versions/028_econ_living_regions.py:45-57`: food 0 … jewelry 1.0, magic 0.8). Prosperity is already a crude "wealth mix" lever on luxury demand.
- **Affordability** (`:512-513`): one scalar for the whole region: `afford = clamp(purse / (cost_day × afford_days), 0, 1)` applied identically to every group (`:514-517`). With purse ≈ 7 days of needs `afford` is pinned at 1 — the purse has **no effect** above one day of needs.
- **Consumption moves no money.** Goods leave the stock but nothing is debited from the purse. The purse only moves via: tax (out), wages (in) in `region_tick`; merchants (`econ_merchant.py:192-203`: purse→NPC purchases, NPC→purse restock + upkeep); caravans (dispatch purse→escrow, delivery escrow→seller purse); guild orders (purse→character); bank resident step (`econ_bank.py:640-680`); event treasury expense (treasury→purse, `econ_tick.py:866-881`).
- **Hunger** (`:519-524`): food consumed vs food need, one number for the region. **Satisfaction** (`:525-527`): non-food value got/wanted.
- **Norm stock** (`norm_stock`, `:307-327`): `norm_days × (household_demand_day + processing input use)`; `household_demand_day` (`:302-304`) assumes prosperity 50 / price 1. **Any class demand multiplier must also enter `norm_stock`** (and `needs_cost_day`, `starting_purse`, `starting_goods`), otherwise prices drift permanently (stock vs a norm that no longer equals demand).
- **Money** (`:542-555`): `income = Σ produced × base_price × price_mult` (production value only); `tax = min(purse, floor(income × tax_rate × tax_income_mult))`; `country_tax = floor(tax × country_tax_rate)`; `treasury_target = floor(tax × (1/dt) × treasury_reserve_days)` (Хикари: ~1.3k × 4 × 7 ≈ 36k); `wages = max(0, net_tax + grant + (treasury - target) // release_ticks)` (`wage_amount`, `:427-432`). So tax→treasury→wages is a near round trip; nothing ever leaves the purse for good.
- **Stability** (`:557-568`): `stab_base − hunger_w×hunger − goods_w×(1−sat) − tax_w×max(0, tax−free_tax) − debt_penalty`, moves by `stab_rate_up/down`, then event delta.
- **Prosperity** (`:570-579`): target `100×(w_sat×sat + w_liq×liq + w_stab×stab/100) − hunger_w×hunger`, `liq = min(1, purse_after / (cost_day × prosp_liq_days))` (14 days). With purse ≈ 6-7 days, liq ≈ 0.5 — the only place where a bigger purse helps, and it is capped at 1.
- `RegionState` (`:219-229`) holds population, tax_rate, stability, prosperity, hunger, satisfaction, treasury_target — no class data. `SimResult` (`:248-260`).
- `RegionModifiers` (events, `:232-245`): production/consumption/price maps, tax_income_mult, stability_delta, prosperity_delta. `mods=None` must stay bit-identical (`tests/test_econ_events.py:58`, `tests/test_econ_events_basic.py:66`) — the same discipline should apply to classes (no class row → old math).
- `SimParams` (`:59-176`): flat dataclass, `from_mapping` ignores unknown / fills missing keys, so new params need no seed migration (pattern used since FEAT-183).

### 2.3 Tick runner (`econ_tick.py`)

- Participating = `template_code IS NOT NULL AND population > 0` (`SQL_PARTICIPATING`, `:361-371`).
- Grant plan (`build_grant_plan`, `:374-390`, `econ_sim.country_grants` `econ_sim.py:435-445`): 25 % of the country balance split by **population**.
- `_process_region` (`:704-955`): lock `econ_regions` → goods → events → guild orders → merchants; one-shot event effects (population change `:758-762`); `simulate_region` (`:811-816`); write region columns (`:818-842`); one `region_tick` op with legs purse→treasury (tax; ledger adds the 10 % country leg), country→treasury (grant), treasury→purse (wages), key `region_tick:<run>:r:<id>` (`:848-857`); event expense ops; merchant SAVEPOINT; guild SAVEPOINT (`guild_crud.guild_step` sets `guild_budget` from the purse, `economy_guild_crud.py:209-217`); history row (`:919-929`).
- Season quota (`_quota_pass`, `:1377-1420`): once per game season, one `season_quota` op emission→**region treasuries** split by `econ_mint.split_quota(amount, populations)` (`econ_mint.py:132-152`, largest remainder, exact sum). Idempotency = ledger key `season_quota:p<period>`; if the pass posts nothing (e.g. no region qualifies) the next tick of the season tries again.
- Caravan pass (before the region loop): buyer budget = `caravan_purse_share × purse` (+ treasury share for food) (`econ_caravan.py:199-206`).
- Bank pass (after the loop): residents' deposit target = `bank_resident_deposit_share × (purse + deposits)`, loan target = `bank_resident_loan_share × purse` (`econ_bank.py:652-680`); `resident_rescale` uses the fill `purse_target` (`econ_bank.py:212-237`).
- Merchant step: region purse budget `floor(purse × merchant_purse_share)`, residents buy `resident_share(price_mult)` of each row (`econ_merchant.py:217-262`) — not group/class aware.

### 2.4 Ledger: is there a sink? (`econ_core.py`, 4 byte-identical copies)

- Money is created/destroyed only through the source kinds `emission` / `adjustment` (`econ_core.py:33`, `SOURCE_KINDS :92`). `validate_operation` (`:482-524`) only forbids **non-source op types** from touching a source account in **either direction** (`:519-520`); direction is not checked. `SOURCE_OP_TYPES = {genesis, admin_emission, admin_adjust} | MINT_OP_TYPES` (`:174`, MINT = mint_court, mint_player, season_quota `:139`).
- **No automatic sink exists.** The only money leaving the world is admin-driven: `admin_emission` with purse→emission / treasury→emission legs in «Заполнить → вернуть излишек» (`economy_sim_crud.py:340-500`, legs at `:449-452`) — requires a comment (`COMMENT_REQUIRED_OP_TYPES :177`), so not usable by the tick; and `admin_adjust`.
- A tick-driven burn therefore needs a **new op type** (e.g. `wealth_drain`), added to `OP_TYPES` and `SOURCE_OP_TYPES` (not comment-required), with `apply_tax=False`. Consequences:
  - edit `econ_core.py` in all 4 services + keep sha256 identical (`scripts/check_econ_copies.sh`, CI job `econ-contract-copies`, `.github/workflows/ci.yml:116-124`); contract cases (`tests/econ_contract_cases.py`, also ×4) have runner checks of op-type sets (`:772` MINT set == / ⊂ SOURCE, `:814` non-source ops may not touch emission) — add a case for the new type; `tests/test_econ_core.py:161-172` parametrize over `SOURCE_OP_TYPES` automatically.
  - Alternative avoiding the copy churn: put the new op type into `MINT_OP_TYPES`-like set inside character-service only — **not possible**, `OP_TYPES` lives in econ_core; any new op type touches all 4 copies (FEAT-187/191/192/193 all did this).
  - Summary (`economy_crud.get_summary`, `:156-227`): `issued = −Σ sources`, invariant `ledger_sum == 0` — a burn keeps the invariant and simply lowers «Выпущено»; no code change required, but a «Сожжено/ушло из мира» line would be nice (mint page shows issued quota per season, `economy_mint_crud.py:790`).
  - Battle-pass earned gold (`battle-pass-service/app/crud.py:395-428`) counts only postings into `character` accounts — unaffected.
  - Frontend op label map `frontend/.../Admin/EconomyPage/economyLabels.ts:44` (add the Russian label), journal filters.
- «Rich pay tax on savings» can instead be a purse→treasury leg (ordinary money move, taxed 10 % to the country by the ledger because `population_purse ∈ TAX_SOURCE_KINDS`, `econ_core.py:97-99`). It can ride inside the existing `region_tick` op (no new type). Only the part that "leaves the world" needs the new source op type; it cannot be a leg of `region_tick` without making `region_tick` a source op (not advisable) — post it as its own op with key `wealth_drain:<run>:r:<region>` in the same region transaction (after `region_tick`, before merchants).

### 2.5 Templates and region rows (DB)

- `econ_region_templates` (`models.py:562-577`): code, name, description, settlement_noun, noun_gender, default_population, tax_rate, sort_order. 8 templates seeded in 028 (`:73-90`: capital, port, mining, agrarian, forest, magic, fortress, rural), populations ×100 by 032. Per-group data lives in `econ_template_goods` (production_per_1000, consumption_mult; seeded from RATIOS/CMULT `028:93-115`).
- `econ_regions` (`models.py:594-621`): population, tax_rate, stability, prosperity, hunger, satisfaction, treasury_target, last_income/tax/wages/grant, last_run_id, last_tick_at, low_stability_since, guild_budget, guild_food_budget. No class columns.
- `econ_region_history` (`models.py:669-692`): population, stability, prosperity, hunger, purse, treasury, income, tax, wages, grant_amount, goods JSON.
- Other services read `econ_regions` only by explicit columns (`SQL_REGION_ECON` = region_id, template_code, population, tax_rate in econ_core ×4 `:1068-1072`; locations crud `:4280`) — adding columns is safe. The contract DDL in `econ_contract_cases.py:1207-1212` creates a 4-column `econ_regions`; it only needs changing if econ_core starts reading class columns (it should not).
- Proposed storage (for the Architect): 3 share columns on `econ_region_templates` (defaults) and `econ_regions` (live, DECIMAL(5,4)), plus history columns (or a JSON) for the admin "shift per recount"; backfill `econ_regions` from their template in migration 037; NULL/absent = classes off (non-templated regions).

### 2.6 Admin API / UI for regions, templates, fill

- `economy_sim_crud.py`: `SQL_REGIONS` + `_region_item` (`:167-207`, positional row indices — adding columns shifts them), `list_regions` (`:210`), `get_region` (`:223`), `update_region` (`:254-297`, body `schemas.EconRegionUpdateRequest` `schemas.py:2083-2113`), `apply_template` (`:300`; should it reset shares?), `region_history` (`:315-337`), `_template_dict` / `list_templates` / `update_template` (`:614-680`, body `EconTemplateUpdateRequest` `schemas.py:2221+`), `fill_regions` (`:340-500`): purse target = `econ_sim.starting_purse` = `purse_start_days × needs_cost_day(base prices)` (`econ_sim.py:369-377`); treasury target from a dry-run `simulate_region`; «вернуть излишек» returns the part above it to emission. **This purse target is the natural place for the class-dependent "wealth norm"** (one function used by both the fill and the tick's drain/quota).
- `sim_state` / `update_sim` (`:792-830`) + params validation `schemas.ECON_SIM_PARAM_BOUNDS` (`schemas.py:1888-1987`), `ECON_SIM_INT_PARAMS` (`:1989-1998`), `EconSimParamsIn` (`:2277-2371`) — every new coefficient is added in 3 schema places + `SimParams`.
- Endpoints (`economy_api.py`): `GET /economy/regions/{id}/card` (`:265`, public), `GET/PUT /admin/economy/regions[/{id}]` (`:271-318`), `POST …/regions/fill` (`:279`), apply-template (`:319`), history (`:333`), `GET/PUT /admin/economy/templates[/{code}]` (`:363-380`), `GET/PUT /admin/economy/sim` (`:460-497`). Permissions already exist (`economy:read`, `economy:settings`, `economy:emit`) — no new RBAC rows needed unless a separate permission is wanted.

### 2.7 Player region card

- `economy_sim_crud.region_card` (`:833-862`) → `econ_sim.region_card` (`econ_sim.py:718-764`): states + labels for food, treasury, stability, prosperity, price_level, shortages/surpluses, phrases, groups.
- **Collision:** prosperity already produces «Бедный / Скромный / Зажиточный / Богатый {noun}» (`_PROSPERITY_ADJ`, `econ_sim.py:596-601`, thresholds `:39-41`) and that is the first phrase. The class wording from the brief («Зажиточный город», «Бедный край: много бедняков») would duplicate/contradict it.
- **Hard test rule:** the card must contain no numbers except `region_id` (`tests/test_econ_regions_api.py:984-990` `_numbers(card) == [(".region_id", 10)]`, `CARD_KEYS` exact set `:988`; hidden-shape equality in `tests/test_econ_regions_api.py:1012` and `tests/test_econ_banks_admin_api.py:446`). A 3-colour bar therefore has to be sent as coarse level words (e.g. per class `few|some|many`, or a fixed set of bar presets) that the frontend maps to widths — or the rule is deliberately relaxed.
- Frontend: `frontend/app-chaldea/src/api/regionEconomy.ts:8-60` (types), `components/WorldPage/RegionEconomyCard.tsx` (phrase tone uses `card.prosperity` etc., `:30-64`).

### 2.8 Frontend admin touch points

`components/Admin/EconomyPage/`: `EconomyRegions.tsx` (table `:345-430`, fill dialog `:32-180`), `RegionEconomyEditor.tsx` (region form), `EconomyTemplates.tsx` (template form), `EconomyTick.tsx` (param groups mirror schema bounds, `:41-80`), `paramHints.ts` («?» hints), `EconomyGuide.tsx` + `guideSections.ts` (guide section), `economyLabels.ts` (op label), `regionBits.tsx`; `types/economy.ts` (`EconRegionItem` `:185`, `EconRegionUpdate` `:242`, `EconRegionHistoryRow` `:304`, `EconRegionTemplate` `:357`, `EconSimParams` `:419`). Rule set: TS, Tailwind, mobile, no `React.FC`.

### 2.9 Events (FEAT-187) — plug-in points

`econ_events.py:41-78`: per-step types production, consumption, labor, price, tax_income, stability, prosperity, merchants_halt, bank_panic, loan_boom; one-shots stock_loss, treasury_expense, population. `aggregate` → `RegionModifiers` (`:184-240`). Classes plug in for free through prosperity/stability/hunger (mobility reacts to them). A dedicated effect (e.g. `class_shift` one-shot «разорение»/«бум», or per-step `mobility` mult) would need: `EFFECT_TYPES`, `EFFECT_FIELDS`, `EFFECT_BOUNDS`, `RegionModifiers`, frontend `EventEffectsBuilder.tsx` + `eventLabels.ts`. Treasury expense (`treasury -> purse`) currently pumps money into the purse — with a wealth norm it would partly be drained again; fine.

### 2.10 Prod calibration (memory note)

Хикари: pop 4M (sim 40k), income ≈ 10.9k/tick, tax 12 % ≈ 1.3k/tick, treasury target ≈ 36k, purse ≈ 243k ≈ 7 days of needs at base prices ≈ 5.6 days of income. Today the purse has no economic effect above 1 day of needs (afford) / caps at 14 days (liq). A wealth norm based on "days of needs" by class (e.g. poor 2, middling 7, rich 30 days) would put the current purse inside the norm of a balanced region, so no drain would start at rollout unless shares are skewed.

### 2.11 Everything that must become class-aware

1. `econ_sim.SimParams` — new coefficients (class demand mults per group or per class "basket", tax weights, wealth norm days per class, drain rate / burn share, mobility rates & thresholds, stability weights).
2. `econ_sim.RegionState` + `econ_tick.region_state()` (`econ_tick.py:334-340`) — shares.
3. `demand_tick`, `household_demand_day`, `norm_stock`, `needs_cost_day`, `starting_purse`, `starting_goods` — class demand factor (must be consistent everywhere or prices drift).
4. `template_production_per_1000` (`econ_sim.py:401-424`) + `test_template_production_rule_matches_migration_seed` — templates were balanced for class-free demand; class factors should be normalized so a template at its default mix gives factor 1.0 per group, or templates need recalibration.
5. Affordability/consumption (`:511-517`) — per-class afford (poor drop first when prices rise / purse low), hunger per class (poor first), satisfaction.
6. Tax (`:546-549`) — class-weighted base + wealth tax on savings above norm; `treasury_target` derives from tax, so wages/reserve shift too.
7. Stability target (`:557-563`) — poor share, poor hunger, rich vs tax rate.
8. Prosperity liq (`:571-572`) — relative to the class wealth norm instead of fixed 14 days.
9. New mobility step (shares drift, sum 100 %, clamp ≥ 0) + new drain step and its op (`econ_tick._process_region`, new op key).
10. `econ_mint.split_quota` + `econ_tick._quota_pass` — weights = deficit below norm (purse? treasury? see questions).
11. `econ_sim.country_grants` / `build_grant_plan` — keep by population or weight by deficit (decide).
12. `economy_sim_crud.fill_regions` — purse target = wealth norm; set shares from template?; `econ_bank.resident_rescale` uses that target.
13. Bank residents (`econ_bank.py:652-680`), merchants resident buying (`econ_merchant.py:217-262`), caravan buyer budget (`econ_caravan.py:199-206`), guild budget (`econ_guild.budgets` `:105-115`) — all read the purse only; they stay correct without change (demand differences reach them through stock/price). Optional refinement only.
14. Region history row (`econ_tick.py:919-929`, model, `region_history` dict, `tests/test_econ_regions_api.py:588` exact key set).
15. Admin regions/templates API + schemas + UI; player card + type; guide + hints; op label.
16. `econ_core.py` ×4 + `econ_contract_cases.py` ×4 for the burn op type.
17. Docs: `docs/services/character-service.md`, `docs/ARCHITECTURE.md` economy section.

### 2.12 Risks

- **Migration of prod regions:** backfill shares from the template; regions without a template stay NULL. Changing demand/tax formulas shifts every live region at the first tick (norms, prices, treasury_target). Mitigate: class factors normalized to 1.0 at the template default mix, so a region at its template mix computes ≈ today; a "no classes" path bit-identical to the current math.
- **Drain is irreversible money destruction** (source op) — must be idempotent per run/region (ledger key), bounded per tick (share of excess), never below the norm; it lowers `issued` in the summary.
- **Quota idempotency:** with deficit weighting, "no region below norm" means nothing is posted and the pass retries every tick of the season — decide skip-for-the-season vs retry.
- **Tests with exact shapes/values:** `test_econ_sim.py:61-69` (seed-param exclusion prefixes — add the new prefix), `:82` template production rule, `:448/:474` 40-tick bounds & stress, events bit-identity tests, `test_econ_regions_api.py:423` (fill result keys), `:588` (history keys), `:605/:659` (groups/templates key sets), `:984-1012` (card keys + no numbers), `test_econ_banks_admin_api.py:446` (hidden card), `test_econ_mint.py:237+` (`split_quota` by population), contract runner set checks.
- **Card overlap** with the prosperity label (2.7) and the no-numbers rule.
- **Performance:** negligible — O(groups × 3) extra math per region per 6 h tick, one more posting per region with excess; ~tens of regions.
- **Lock order:** the drain posting touches purse + emission accounts inside the region transaction after `region_tick` — same accounts class as today; no new locks.

## 3. Architecture Decision (filled by Architect — in English)

All backend work is in **character-service** (sync SQLAlchemy, Pydantic v1). **No new ledger op type** (decision 4:
no burn) → `econ_core.py` ×4 and `tests/econ_contract_cases.py` ×4 are **not touched**; inventory-, locations-,
dungeon-, battle-pass-service are unaffected (they read `econ_regions` by explicit columns only). No new RBAC
permission, no Nginx/Docker change. CS = `services/character-service/app`, FE = `services/frontend/app-chaldea/src`.

The user decisions in section 1 («Решения пользователя после анализа», 1–7) are final; everything below fills the
technical gaps. Guiding rules:
- **Kill switch / bit-identity.** A region «has classes» iff `params.classes_enabled = 1` **and** its three share
  columns are not NULL. Without classes every function runs today's statements unchanged (same discipline as
  `mods=None` of FEAT-187); the existing bit-identity tests stay green and get a twin for classes.
- **No jump at rollout.** Every class factor (demand per group, income tax) is normalised against the region's
  **template default mix**, so a region sitting at its template mix computes factor exactly `1.0` (x/x is exact in
  IEEE; the shares are copied from the same DECIMAL values). New effects (wealth tax, class stability terms,
  mobility) are zero at rollout with the default settings (worked example 3.12).
- **One wealth norm** (3.4), computed by one pure function and stored per region each tick (`econ_regions.wealth_norm`):
  used by the fill, the wealth tax, the per-class money split / affordability, mobility, the quota split and the
  grant tilt.

### 3.1 Module layout

| Module | Kind | Content |
|---|---|---|
| `CS/econ_classes.py` (new) | pure, no DB, imports nothing from `econ_sim` (avoids a cycle; params are passed duck-typed) | `ClassMix` (poor, middling, rich), `CLASSES = ("poor","middling","rich")`; `demand_weights` / `demand_factors` (3.3), `class_parts`; `wealth_norm_parts` / `wealth_norm` (3.4); `split_money`, `class_afford`, `allocate` (rich → middling → poor) (3.5); `tax_factor`, `wealth_tax` (3.6); `stability_terms` (3.7); `mobility_score`, `shift`, `mobility` (3.8); `deficit` (3.9); card helpers `class_state`, `class_bar`, `class_phrase` (3.11); `class_report` for the admin (3.13). |
| `CS/econ_sim.py` | pure | `GroupDef.class_demand: Tuple[float, float, float] = (1.0, 1.0, 1.0)`; `RegionState.classes / class_base: Optional[ClassMix] = None`; optional `factors` argument on `household_demand_day`, `norm_stock`, `demand_tick`, `needs_cost_day`, `starting_goods` (None → today's statement); `starting_purse(..., classes=None, class_base=None)` → wealth norm when classes are given; class path inside `simulate_region` (3.2); new `SimResult` fields (default values keep old callers working); `country_grants(..., deficits=None)` (3.10); 23 `SimParams` fields (3.14); `region_card(..., classes=None)` (3.11). |
| `CS/econ_events.py` | pure | one-shot effect `class_shift` (3.15). |
| `CS/econ_mint.py` | pure | `split_by_deficit(amount, deficits)` (3.9); `split_quota` kept unchanged (still used by tests / nothing else). |
| `CS/econ_tick.py` | DB | `region_state(row, base=None)` reads the shares; template bases loaded once per run; one-shot `class_shift`; class columns / `wealth_norm` / deltas written; wealth tax inside the `region_tick` tax leg; history columns; `build_grant_plan` and `_quota_pass` by deficit (3.9, 3.10); docstring paragraph. Lock order **unchanged**. |
| `CS/economy_sim_crud.py` | DB | regions list/detail (class fields + `class_report`), `update_region` (shares), `apply_template` (resets shares), `fill_regions` (`reset_classes`, purse target = wealth norm), templates (shares), goods groups (class demand), `region_history` (new keys), `region_card` (classes block). |
| `CS/models.py`, `CS/schemas.py` | ORM / Pydantic v1 | columns of 3.16; request/response fields; `ECON_SIM_PARAM_BOUNDS` / `ECON_SIM_INT_PARAMS` / `EconSimParamsIn`; `EVENT_EFFECT_LABELS["class_shift"]`. |
| `CS/alembic/versions/037_econ_social_classes.py` | migration | revision id `037_econ_social_classes` (23 chars ≤ 32), down `036_econ_guild_orders` (3.16). |

### 3.2 Class path of `simulate_region` (order of the existing steps kept)

`has_classes = params.classes_enabled and region.classes is not None`; `base = region.class_base or region.classes`
(a region whose template row vanished normalises against itself → factors 1.0). When `has_classes` is false nothing
below runs.

| Step | Today | Class path |
|---|---|---|
| 0 | — | `F = demand_factors(groups, mix, base)` per group (3.3); `norm_total, norm_parts = wealth_norm(groups, goods_in, pop, mix, base, params)` from the **input** goods (event consumption mods do not move the norm). |
| 1–3 production | unchanged | unchanged |
| 4 demand | `demand_tick(...)` | `demand_tick(..., factor=F[g])` — the total demand per group = today's × `F[g]` |
| 5 afford / consumption | one scalar `afford` | per class: `money_k = split_money(purse, norm_parts)` (∝ the class norm), `cost_k` = class part of the demand at current prices, `afford_k = clamp(money_k / (cost_k × afford_days), 0, 1)`; per group the class parts `D_g × w_kg / Σw_g` are served from the stock **rich → middling → poor** (`allocate`), each up to `part × afford_k`. `SimResult.affordability` = demand-value-weighted mean of `afford_k` (admin only). |
| 5 hunger | `1 − food_consumed / need` | per class `hunger_k = 1 − food_consumed_k / need_k` (`need_k` = today's need × class part); region `hunger = 1 − Σ consumed / Σ need_k` (= today at the default mix). |
| 6–7 norms, prices | `norm_stock(...)` | `norm_stock(..., factors=F)`: household part × `F[g]`; processing input use unchanged. |
| 8 money | `tax = min(purse, floor(income × rate [× mods]))` | `tax = min(purse, floor(income × rate [× mods] × tax_factor(mix, base)))` (3.6); `wealth_tax = wealth_tax(purse − tax, norm_total, params)`; `country_tax = floor((tax + wealth_tax) × country_rate)` (one ledger leg, 3.6); `treasury_target` from **income tax only** (unchanged formula on `tax`); `wages = wage_amount(tax − floor(tax × rate), grant, treasury, target)` — the wealth tax does **not** return as wages in the same tick; `purse_after = purse − tax − wealth_tax + wages`; `treasury_after = treasury + tax + wealth_tax − country_tax + grant − wages`. |
| 9 stability | today's target | `− stability_terms(...)` (3.7), then the event delta as today. |
| 10 prosperity | unchanged (liq stays `purse_after / (cost_day × prosp_liq_days)`) | unchanged — deliberate: a region with a higher norm (capital) keeps reading as more prosperous; prosperity = short-term well-being, classes = structure. |
| 11 mobility (new) | — | `new_mix, dpoor, drich = mobility(mix, stability, prosperity, hunger, purse_after / norm_total, params)` (3.8). |

New `SimResult` fields (defaults keep every caller / test that builds it valid): `wealth_tax: int = 0`,
`wealth_norm: int = 0` (no-class path: `starting_purse` of today, 3.4), `class_hunger: Optional[Tuple] = None`,
`class_afford: Optional[Tuple] = None`, `class_delta: Tuple[float, float] = (0.0, 0.0)` (poor, rich); `region.classes`
of the returned `RegionState` = the new mix. `SimResult.tax` keeps its meaning (income tax).

### 3.3 Demand per class (data on `econ_goods_groups`)

Each goods group gets three per-capita weights `class_demand_poor / _middling / _rich` (DECIMAL(6,3), editable in
«Группы товаров»). Seed (brief: poor — food, household, a few tools; middling — + weapons, armour, potions, tools;
rich — + jewellery, magic, everything expensive):

| group | poor | middling | rich |
|---|---|---|---|
| food | 1.0 | 1.0 | 1.2 |
| ore_metal | 0.6 | 1.0 | 1.3 |
| wood | 1.0 | 1.0 | 1.2 |
| herbs | 0.6 | 1.0 | 1.5 |
| hides_textiles | 0.8 | 1.0 | 1.5 |
| magic | 0.1 | 0.8 | 4.0 |
| weapons | 0.2 | 1.0 | 2.0 |
| armor | 0.4 | 1.0 | 2.0 |
| jewelry | 0.05 | 0.6 | 6.0 |
| potions | 0.3 | 1.0 | 2.0 |
| tools | 0.6 | 1.0 | 1.2 |
| household | 0.6 | 1.0 | 2.5 |

```
w_kg       = s_k × c_kg / Σ_j base_j × c_jg          # class part weight (base = template default mix)
F_g        = Σ_k w_kg                                # demand factor; = 1.0 exactly at the template mix
D_kg       = D_g × w_kg / F_g                        # class part of the group's total demand D_g (F_g = 0 → parts 0)
Σ_j base_j × c_jg == 0 → F_g = 1, parts split by s_k  # guard
```
Template production (`template_production_per_1000`, its seed test) is unchanged: templates stay balanced for their
own default mix. Editing a template's shares re-bases all its regions (balance kept); editing one region's shares
moves only that region's demand (intended — guide note).

### 3.4 The wealth norm (one definition)

Per class: `norm_days_k` days of **that class's** needs at base prices (×1, prosperity 50) per resident:
```
basecost_k   = Σ_g household_demand_day(g) × w_kg × base_price_g        # marks/day of class k, whole region
norm_part_k  = class_norm_days_k × basecost_k
wealth_norm  = floor(Σ_k norm_part_k)                                    # purse norm of the region
money norm   = wealth_norm + treasury_target                             # used by the quota / grant deficit (3.9)
```
Defaults `class_norm_days_poor / _middling / _rich = 3 / 7 / 21`. Resulting purse norms (computed for the 8 seeded
templates at sim population 40 000, base prices): capital 9.98 days of total needs, magic 10.1, port 8.3, fortress
7.2, forest 7.2, mining 7.0, agrarian 6.7, rural 6.0 — around today's `purse_start_days = 7`, but the capital's norm
is ~1.7× the rural one («столица остаётся богатой, бедный край — бедным»). Per resident: poor ≈ 2.4–2.7 marks,
middling ≈ 6.8–8.4, rich ≈ 31–40 (sim units).

No-class path: `wealth_norm = starting_purse(...)` of today (`purse_start_days × needs at base prices`) — so the quota /
grant deficit also works with `classes_enabled = 0`. The tick writes `econ_regions.wealth_norm` every run (and the
fill / apply-template write it too); readers outside the region transaction (quota, grant plan, admin) use the stored
value — at most one tick old. A region never ticked since the migration has `wealth_norm = 0` → never «below norm»
until its first tick (harmless, see 3.9).

### 3.5 Purchasing power

`split_money(purse, norm_parts)`: the purse is split between classes in proportion to their norm parts (largest
remainder not needed — floats, the split is only used for ratios). So every class holds the same fraction
`r = purse / wealth_norm` of its own norm, and class k has `r × norm_days_k` days of its needs at base prices. The poor
(3 days) therefore drop out first when prices rise or the purse shrinks: at `r = 1` the poor still buy everything up
to a price level ×3 of their basket; at `r = 0.3` they afford ~90 % of their basket at ×1 prices while the middling
(2.1 days) and the rich (6.3 days) still buy everything. Shortage of stock is served rich → middling → poor, so hunger hits the poor first. Affordability
and allocation affect **goods only** — consumption still moves no money (unchanged FEAT-182 rule; merchants /
caravans / guild move money as today).

### 3.6 Taxes

**Income tax (class-weighted):** `tax_factor = Σ s_k × t_k / Σ base_k × t_k`, `t = class_tax_w_poor / _middling /
_rich = 0.3 / 1.0 / 2.0` (poor pay little, middling base, rich more) — `1.0` at the template mix, so today's tax is
reproduced at rollout. Example: capital 0.35/0.45/0.20 → 0.33/0.45/0.22 gives ×1.036.

**Wealth tax:** `wealth_tax = floor(wealth_tax_rate × max(0, (purse − tax) − wealth_norm))`, default rate **0.02 per
tick**, never more than the purse left after the income tax. It goes purse → region treasury **in the same tax leg**
of the `region_tick` operation (leg amount `tax + wealth_tax`; no new op type, no new key). **Country 10 %: applies as
today** — the ledger adds the `region → country` leg on every purse → treasury inflow; the sim predicts it on the
combined amount, so prediction and ledger agree. Rationale: an exemption would need a per-leg `apply_tax` exception in
`econ_core` (×4); and the country cut is exactly the inter-region redistribution channel (3.10). Ledger metadata of
`region_tick` gains `"wealth_tax"` (only when classes are on). `econ_regions.last_tax` stays the income tax; new
`last_wealth_tax`.

**Why the wealth tax is not paid back as wages in the same tick:** today `wages = net_tax + grant + release`, a round
trip. If the wealth tax entered `net_tax` it would come straight back and do nothing. It is therefore kept out of
the wage formula; it raises the treasury above `treasury_target` and returns through the existing slow release
`(treasury − target) // treasury_release_ticks` (8).

**Equilibrium (honest):** within one region money is conserved by every internal flow (taxes, wages, consumption,
merchants' upkeep). With an excess `E = purse − wealth_norm > 0` and no external inflow:
- per tick the purse pays `0.02 E`, the treasury keeps `0.018 E`, the country gets `0.002 E`;
- the treasury surplus `S` settles where inflow = release: `0.018 E = S / 8` → `S ≈ 0.14 E`. So ~13 % of the excess
  is parked as public money (spent by guild food orders, caravans, event recovery, the bank seed) and ~87 % stays in
  the purse;
- the only leak is the country cut (≈ 0.2 % of the excess per tick, ≈ 0.8 %/day) → country treasury → next ticks'
  grants (25 % of the country balance per tick), of which `grant_deficit_share` (25 %) goes to below-norm regions and
  the rest by population. So an excess is slowly **pooled across the country**, not destroyed and not equalised: the
  norms themselves stay different (class mix);
- the main absorber is **mobility** (3.8): money above the norm pushes classes up, which raises the norm until `r ≈ 1`
  (a capital that got richer gets more rich residents, not an ever-growing purse).
Nothing can explode: every flow is a fraction < 1 of a non-negative balance; the wealth tax is capped by the purse;
`treasury_target` is computed from the income tax only (a wealth-tax-based target would feed back into wages);
shares are bounded (3.8). New money enters the world only through quota / mint / players / admin, and the quota only
reaches regions below their money norm (3.9). Players' money brought into a region does stay in the world — it ends up
partly in classes (higher norm), partly in the country pool.

### 3.7 Stability

```
stab_target −= class_stab_poor_w × max(0, poor − class_stab_poor_threshold)        # many poor → unrest
            +  class_stab_poor_hunger_w × poor × hunger_poor                       # hunger weighs more on the poor
            +  class_stab_rich_tax_w × rich × max(0, tax_rate − class_stab_rich_free_tax)   # rich hate high taxes
```
(on top of today's terms, before the clamp). Defaults 40 / 0.60 / 50 / 100 / 0.12 → **0 at rollout**: no template
default has poor > 0.60, no fed region has `hunger_poor > 0`, no template tax exceeds 0.12. Example: rural region with
poor drifting to 0.70 → −4; a famine with `hunger_poor = 0.5` and poor 0.5 → −12.5 extra; capital at tax 0.20 with
rich 0.2 → −1.6 (on top of today's −16 tax term).

### 3.8 Mobility (slow, bounded, sum = 1)

```
score = clamp( mob_w_prosperity × (prosperity − 50) / 50
             + mob_w_money      × clamp(r − 1, −1, 1)          # r = purse_after / wealth_norm (0 when norm = 0)
             + mob_w_stability  × clamp((stability − 50) / 50, −1, 1)
             − mob_w_hunger     × clamp(hunger / 0.15, 0, 1), −1, 1)          # 0.15 = card «голодает»
dz = mob_dead_zone
score >  dz: up   = mob_rate_up   × (score − dz) / (1 − dz)  → poor→middling: up × poor;  middling→rich: up × mob_rich_factor × middling
score < −dz: down = mob_rate_down × (−score − dz) / (1 − dz) → rich→middling: down × rich; middling→poor: down × middling
```
`shift(mix, up, down, rich_factor, smin, smax)` (shared by mobility and the event effect): flows are computed from the
old shares, then capped so that **no share is pushed below `class_share_min` or above `class_share_max`** (a share the
admin set outside the bounds is never pushed further out); poor and rich are rounded to 6 decimals and **middling =
1 − poor − rich** (Decimal) → the sum is exactly 1, no share negative. Returns the new mix and `(dpoor, drich)` for
the admin «сдвиг за пересчёт» (stored on `econ_regions`).

Defaults: weights 0.4 / 0.4 / 0.2 / 1.0, dead zone 0.1, `mob_rate_up` 0.001, `mob_rate_down` 0.0015 (falling is
faster than rising), `mob_rich_factor` 0.5, bounds 0.02 / 0.90. Time scale: a strong boom (score 0.5) moves ~3 pp
of the poor up per game season (196 ticks); the maximum (score 1) ~6.6 pp; a famine (score −1) moves ~13 pp of the
middling down per season. A normal region (prosperity ≈ 50, r ≈ 1, stability ≈ 70, fed) has score ≈ 0.08 → inside
the dead zone → no drift at rollout. Feedback: more rich → higher norm → lower `r` → the money term brakes; more poor
→ lower norm → higher `r` → pushes back up. Regions therefore settle at the mix their money supports and do **not**
converge to one mix (prosperity/stability/production differ).

### 3.9 Season quota by deficit (decision 3)

`deficit_i = max(0, wealth_norm_i + max(0, treasury_target_i) − max(0, purse_i) − treasury_i)` from the stored
columns and current balances (plain reads, no locks — like today's population read). `econ_mint.split_by_deficit(
amount, deficits)`:
- regions with `deficit > 0` only; issued `X = min(amount, Σ deficits)`; largest-remainder split ∝ deficit; each
  share capped at its deficit (exact sum = X);
- `Σ deficits == 0` (nobody below norm) → nothing.

**Season marking — decision: retry each tick within the season (no marker).** The ledger key `season_quota:p<period>`
stays the only idempotency guarantee: the quota is issued once, at the **first tick of the season when some region
is below its norm**; until then every tick re-checks (one SELECT of ~tens of rows + balances per 6 h — negligible).
Why not mark the season as «skipped»: a region that falls below norm in the middle of the season (famine, raid,
players taking money out) should still be helped by that season's quota — that is the purpose of the quota; a marker
row would need a new table or a zero-leg operation the ledger does not allow. The unissued part (`amount − X` when
deficits are small) is **not** carried over: the quota is a cap, not an obligation («новые деньги только туда, где их
не хватает»). Metadata of the `season_quota` op gains `deficits` (per region) and `requested` (= amount). Also fixes a
rollout corner: right after the migration all `wealth_norm` are 0 → nobody below norm → the pass simply waits for the
first region tick.

Log/summary: `quota_amount` as today; an INFO line «season quota waits: no region below its norm» once per run.

### 3.10 Country grants with a deficit tilt (decision 5)

`econ_sim.country_grants(balance, populations, params, deficits=None)`: `pool = floor(max(0, balance) ×
country_grant_share)` as today. `deficits is None` → today's statement (bit-identical). Otherwise
`tilt = floor(pool × grant_deficit_share)` (default 0.25) split ∝ deficit among regions with `deficit > 0`, each capped
at its deficit (floor per region); `rest = pool − Σ tilt grants` split by population as today (floor). No region below
norm → the whole pool by population. Sum ≤ pool always. `build_grant_plan` reads `wealth_norm`, `treasury_target`
and the two balances per participating region at claim time; the plan is still fixed in the run row (a resumed run
grants the same).

### 3.11 Player card (decisions 1, 2)

`econ_sim.region_card(..., classes: Optional[ClassMix] = None)`. `classes is None` (classes off / no shares) → today's
card byte-for-byte. With classes the participating card gets one new key:
```
"classes": {"state": "poor|modest|wealthy|rich", "label": "Зажиточный город, много бедняков",
            "bar": {"poor": "few|some|many", "middling": "few|some|many", "rich": "few|some|many"}}
```
- `index = middling × 0.5 + rich`; state: `< 0.25` poor, `< 0.32` modest, `< 0.40` wealthy, else rich (module
  constants like the other card thresholds). Seeded defaults read: capital/magic «Богатый город», port «Зажиточный
  порт», fortress/forest/mining/agrarian «Скромн…», rural «Бедная округа».
- Adjective = the existing `_PROSPERITY_ADJ` (gendered) + noun; tail «, много бедняков» when `poor ≥ 0.5` and state
  ≠ poor, else «, много богачей» when `rich ≥ 0.18` and state ≠ rich.
- Bar words (thresholds per class, because the rich are naturally few): poor/middling `few < 0.30 ≤ some < 0.50 ≤ many`;
  rich `few < 0.08 ≤ some < 0.18 ≤ many`. **No numbers** leave the API (test `_numbers(card)` unchanged).
- `phrases[0]` = `classes.label`. `prosperity.label` becomes a state phrase without the adjective: rich «{Noun}
  процветает», wealthy «{Noun} живёт в достатке», modest «{Noun} живёт скромно», poor «{Noun} в упадке»; only rich
  and poor are appended to `phrases` (after the food phrase) — no second «Богатый …». `prosperity.state` unchanged.
- Hidden card shape unchanged (no `classes` key).

Frontend: `RegionCardData.classes?: RegionCardClasses | null`; a 3-segment bar (poor — muted `bg-white/25`, middling
`bg-site-blue/70`, rich `bg-gold/80`) whose widths come from a word→weight map (poor/middling `few 20 · some 35 · many
55`, rich `few 6 · some 14 · many 24`, normalised to 100 %) + a legend «бедные — много · зажиточные — средне · богатые
— мало». `phraseTone` also matches `card.classes` (state `poor` → gold tone).

### 3.12 Worked example — Хикари (prod numbers, section 2.10)

Assumed capital template (tax 12 %, mix 0.35 / 0.45 / 0.20); sim population 40 000; needs ≈ 34.7 k/day; income ≈
10.9 k/tick; income tax ≈ 1.3 k/tick; treasury target ≈ 36 k; purse ≈ 243 k; treasury ≈ target.

**A — rollout (shares = template):** demand factors 1.0 → identical demand, norms, prices; tax factor 1.0 → tax 1.3 k
as before; wealth norm ≈ 9.98 × 34.7 k ≈ **346 k** (r = 0.70) → wealth tax 0; class stability terms 0; mobility score
≈ 0.4×0 + 0.4×(−0.30) + 0.2×0.5 − 0 ≈ −0.02 → dead zone, no drift. Money norm 346 k + 36 k = 382 k vs 279 k →
deficit ≈ 103 k → Хикари is a quota / grant-tilt candidate. The card changes wording only: «Богатый город» (class) and
— if prosperity is high — «Город процветает».

**B — players bring +200 k into the purse (443 k, excess ≈ 95 k over 346 k):**

| tick | wealth tax | country cut (incl. income-tax cut) | wages | purse | treasury | purse+treasury |
|---|---|---|---|---|---|---|
| 0 | — | — | — | 443 000 | 36 000 | 479 000 |
| 1 | 1 894 | 319 | 1 170 | 440 976 | 37 705 | 478 681 |
| 2 | 1 853 | 315 | 1 383 | 439 206 | 39 160 | 478 366 |
| 3 | 1 818 | 311 | 1 565 | 437 653 | 40 402 | 478 055 |
| 4 | 1 787 | 308 | 1 720 | 436 286 | 41 461 | 477 747 |
| 8 | 1 695 | 299 | 2 142 | 432 203 | 44 336 | 476 539 |

(Without classes the same region today: purse+treasury loses only the 130/tick income-tax cut, the purse stays
≈ 443 k forever.) Mobility: r ≈ 1.27 → score ≈ 0.11 + 0.1 + prosperity term ≈ 0.25 → up ≈ 1.7·10⁻⁴/tick → the poor
share falls ≈ 1 pp per season, the norm rises, the excess melts from both sides; the region stays richer than before
but never «runs away».

**C — the mix drifts to 0.33 / 0.45 / 0.22:** demand ×1.004 food … ×1.065 magic, ×1.08 jewellery (luxury prices up
until production reacts); tax ×1.036 (1.30 k → 1.35 k); wealth norm +5.7 % (346 k → ≈ 366 k).

### 3.13 Admin (decision 6)

- **Regions list** (`GET /characters/admin/economy/regions`): per item `class_poor`, `class_middling`, `class_rich`
  (float | null), `class_base` ({poor, middling, rich} | null — the template defaults), `class_dpoor`, `class_drich`
  (last recount shift, signed), `wealth_norm` (int), `last_wealth_tax` (int), `money_vs_norm` (float | null =
  purse / wealth_norm). SQL columns appended at the **end** of `SQL_REGIONS` (positional indices of `_region_item`
  stay valid).
- **Region detail** (`GET …/regions/{id}`): + `classes` = `class_report(...)` or null: per class `{share, base_share,
  norm_days, norm_per_resident, money_per_resident, needs_per_resident_day, afford}` (afford at current prices,
  per sim resident), `wealth_norm`, `money_norm` (+ treasury target), `deficit`, `r`.
- **Region PUT** (`EconRegionUpdateRequest`): optional `class_poor`, `class_middling`, `class_rich` — all three or none
  (400 «Укажите все три доли»), each 0…1, sum 1 ± 0.001 (400 «Сумма долей должна быть 100 %»); stored poor / rich at
  6 decimals, middling = 1 − poor − rich. Omitted → kept; a row without shares that has (or gets) a template copies
  the template's shares; template removed → shares kept (unused while not participating).
- **«Применить шаблон»** (`POST …/apply-template`): also resets the shares to the template and zeroes `class_dpoor /
  drich`; recomputes `wealth_norm`.
- **«Заполнить регионы»** (`EconFillRequest.reset_classes: StrictBool = False`): shares kept unless `reset_classes`
  (rows with NULL shares always get the template's); the purse target = `wealth_norm` (classes on) / `starting_purse`
  (off); the treasury probe runs with the classes. Response gains `classes_reset: [region ids]`; metadata of the fill op
  `purse_target` already carries the norm.
- **Templates** (`EconTemplateUpdateRequest` + `_template_dict`): `class_poor`, `class_middling`, `class_rich`
  (required on PUT? — **optional**, None → kept, so an older admin build does not break), same validation; stored at 4
  decimals, middling derived.
- **Goods groups** (`EconGoodsGroupUpdateRequest` + `_group_dict`): `class_demand_poor / _middling / _rich`, optional,
  0…20 each (`ECON_MAX_CLASS_DEMAND = 20`), None → kept.
- **History** (`GET …/regions/{id}/history`): + `class_poor`, `class_middling`, `class_rich` (null for old rows),
  `wealth_norm`, `wealth_tax`.
- **Sim params**: 22 new keys via the existing `PUT /characters/admin/economy/sim` (`economy:settings`), bounds 3.14;
  cross-field check `class_share_min < class_share_max` (400 «Нижняя граница доли класса должна быть меньше верхней»).
  None of them creates money → no `MONEY_SIM_PARAMS` guard.

### 3.14 Settings (`SimParams`, sim params JSON — no seed migration)

| Param | Type | Default | Bounds | Meaning |
|---|---|---|---|---|
| `classes_enabled` | int | 1 | 0 … 1 | 0 = the whole class layer off (today's math, norm = `purse_start_days`) |
| `class_norm_days_poor` | float | 3 | 0 … 365 | wealth norm of a poor resident, days of his needs at base prices |
| `class_norm_days_middling` | float | 7 | 0 … 365 | same, middling |
| `class_norm_days_rich` | float | 21 | 0 … 365 | same, rich |
| `wealth_tax_rate` | float | 0.02 | 0 … 0.2 | share of the purse excess above the norm taxed into the treasury per recount |
| `class_tax_w_poor` | float | 0.3 | 0 … 5 | income-tax weight of the poor (normalised to the template mix) |
| `class_tax_w_middling` | float | 1.0 | 0 … 5 | same, middling |
| `class_tax_w_rich` | float | 2.0 | 0 … 5 | same, rich |
| `class_stab_poor_threshold` | float | 0.6 | 0 … 1 | poor share above which unrest starts |
| `class_stab_poor_w` | float | 40 | 0 … 500 | stability points per 1.0 of poor share above the threshold |
| `class_stab_poor_hunger_w` | float | 50 | 0 … 500 | extra stability loss per (poor share × poor hunger) |
| `class_stab_rich_free_tax` | float | 0.12 | 0 … 1 | tax rate the rich accept |
| `class_stab_rich_tax_w` | float | 100 | 0 … 2000 | stability loss per (rich share × tax above that) |
| `mob_rate_up` | float | 0.001 | 0 … 0.05 | max share of a class moving up per recount |
| `mob_rate_down` | float | 0.0015 | 0 … 0.05 | max share moving down per recount |
| `mob_rich_factor` | float | 0.5 | 0 … 1 | middling → rich moves at this fraction of the poor → middling rate |
| `mob_dead_zone` | float | 0.1 | 0 … 0.9 | weaker signals move nobody |
| `mob_w_prosperity` | float | 0.4 | 0 … 5 | weight of prosperity in the mobility signal |
| `mob_w_money` | float | 0.4 | 0 … 5 | weight of money vs the norm |
| `mob_w_stability` | float | 0.2 | 0 … 5 | weight of stability |
| `mob_w_hunger` | float | 1.0 | 0 … 5 | weight of hunger (downward only) |
| `class_share_min` / `class_share_max` | float | 0.02 / 0.90 | 0 … 0.3 / 0.4 … 1 | mobility / events never push a share outside |
| `grant_deficit_share` | float | 0.25 | 0 … 1 | share of the country grant pool split by deficit (3.10) |

(23 keys incl. both bounds.) `classes_enabled` into `ECON_SIM_INT_PARAMS`. «?» hints for all in `paramHints.ts`;
new group «Классы жителей и норма богатства» in `EconomyTick.tsx`. `test_econ_sim.py` seed-exclusion prefixes get
`class_`, `classes_`, `wealth_`, `mob_`, `grant_deficit`.

### 3.15 Events: one-shot `class_shift` (decision 7)

`econ_events`: `ONE_SHOT_TYPES += ("class_shift",)`, `EFFECT_FIELDS["class_shift"] = ("delta",)`,
`EFFECT_BOUNDS["class_shift"] = ("delta", -0.3, 0.3)`; `OneShots.class_shift: float` (sum per instance, clamp ±0.3);
`OneShots.empty` updated. Meaning: `delta > 0` → `shift(mix, up=delta, down=0, ...)` (that share of the poor moves to
middling, `delta × mob_rich_factor` of the middling to rich); `delta < 0` → `shift(mix, 0, −delta, ...)`; same bounds
as mobility. Applied in `_process_region` with the other one-shots (once per instance, `applied_at`), only when the
region has classes; `outcome.class_shift = {"before": [p, m, r], "after": [p, m, r]}`. Schemas
`EVENT_EFFECT_LABELS["class_shift"] = "Сдвиг классов"` (validation through the shared EFFECT tables). Frontend
`EventEffectsBuilder` / `eventLabels`: «Сдвиг классов», value as signed % («+2 % вверх» / «−3 % вниз»).

Seed changes (migration 037, data only, idempotent — appended only when the template has no `class_shift` yet;
admin-edited templates get the effect appended as well, pre-beta rule):

| template | added effect |
|---|---|
| `riot` «Бунт» | `class_shift −0.03` (богатые бегут, средние беднеют) |
| `raid` «Набег» | `class_shift −0.02` |
| `plague` «Чума» | `class_shift −0.02` |
| `rich_vein` «Богатая жила» | `class_shift +0.02` |
| `fair` «Ярмарка» | `class_shift +0.01` |
| **new** `ruin` «Разорение» (bad, random, weight 1, 5–10 days, any template, no season, icon `coins`) | `class_shift −0.06`, `tax_income ×0.85`, `prosperity −1` (per step), `stability −0.5` (per step); player text «Купеческие дома разоряются один за другим: вчерашние богачи продают дома, мастеровые идут в подёнщики.» |

### 3.16 DB changes — migration `037_econ_social_classes` (raw-SQL DDL, `_TABLE_OPTS`, re-runnable like 034–036)

```sql
-- every ADD COLUMN only if missing (information_schema check)
ALTER TABLE econ_region_templates ADD COLUMN class_poor     DECIMAL(6,4) NOT NULL DEFAULT 0.4500;
ALTER TABLE econ_region_templates ADD COLUMN class_middling DECIMAL(6,4) NOT NULL DEFAULT 0.4500;
ALTER TABLE econ_region_templates ADD COLUMN class_rich     DECIMAL(6,4) NOT NULL DEFAULT 0.1000;
-- seeds (UPDATE … WHERE code = :code): capital .35/.45/.20, port .45/.42/.13, mining .55/.37/.08,
-- agrarian .55/.38/.07, forest .50/.42/.08, magic .30/.50/.20, fortress .45/.48/.07, rural .60/.35/.05

ALTER TABLE econ_regions ADD COLUMN class_poor     DECIMAL(9,6) NULL;     -- NULL = no classes
ALTER TABLE econ_regions ADD COLUMN class_middling DECIMAL(9,6) NULL;
ALTER TABLE econ_regions ADD COLUMN class_rich     DECIMAL(9,6) NULL;
ALTER TABLE econ_regions ADD COLUMN class_dpoor    DECIMAL(9,6) NOT NULL DEFAULT 0;   -- last recount shift
ALTER TABLE econ_regions ADD COLUMN class_drich    DECIMAL(9,6) NOT NULL DEFAULT 0;
ALTER TABLE econ_regions ADD COLUMN wealth_norm    BIGINT NOT NULL DEFAULT 0;
ALTER TABLE econ_regions ADD COLUMN last_wealth_tax BIGINT NOT NULL DEFAULT 0;
UPDATE econ_regions e JOIN econ_region_templates t ON t.code = e.template_code
   SET e.class_poor = t.class_poor, e.class_middling = t.class_middling, e.class_rich = t.class_rich
 WHERE e.class_poor IS NULL;                                                -- backfill from the template

ALTER TABLE econ_region_history ADD COLUMN class_poor DECIMAL(9,6) NULL, class_middling …, class_rich …,
                                ADD COLUMN wealth_norm BIGINT NULL, ADD COLUMN wealth_tax BIGINT NULL;

ALTER TABLE econ_goods_groups ADD COLUMN class_demand_poor     DECIMAL(6,3) NOT NULL DEFAULT 1.000;
ALTER TABLE econ_goods_groups ADD COLUMN class_demand_middling DECIMAL(6,3) NOT NULL DEFAULT 1.000;
ALTER TABLE econ_goods_groups ADD COLUMN class_demand_rich     DECIMAL(6,3) NOT NULL DEFAULT 1.000;
-- seeds per code: table 3.3

-- econ_event_templates: append class_shift effects (Python: read JSON, append if absent, UPDATE) + INSERT `ruin`
-- WHERE NOT EXISTS (columns as in 033)
```
DECIMAL(9,6) on the live shares because a mobility step is ~10⁻⁴…10⁻⁵ (DECIMAL(5,4) would round it away). No FK, no
ENUM. **Downgrade:** drop the added columns; remove `class_shift` entries from template effects; delete `ruin` when no
`econ_region_events` row uses it, otherwise set `is_enabled = 0`. Event instances keep their snapshots (old code skips
the unknown type with a warning). SQLite test DB: ORM models carry the columns.

### 3.17 Data flow
```
econ_scheduler / «Пересчитать сейчас» → run_tick
  → claim: build_grant_plan (pool → 25 % by deficit [stored wealth_norm + treasury_target vs balances], rest by population)
  → _quota_pass: period key exists? → done; deficits → split_by_deficit → season_quota emission → region treasuries
                 (nobody below norm → retry next tick)
  → _caravan_pass (unchanged)
  → region loop / _process_region: lock region → goods → events (one-shots incl. class_shift on the share columns)
       → simulate_region (class path: factors, norm, per-class afford & allocation, class tax, wealth tax,
         stability terms, mobility) → write region (shares, deltas, wealth_norm, last_wealth_tax) + goods
       → region_tick op: purse→treasury (tax + wealth_tax; ledger +10 % country), country→treasury grant,
         treasury→purse wages → merchants → guild → history row (+ shares, norm, wealth tax) → COMMIT
  → guild sweep → mint → banks (unchanged)
Admin → PUT region / template / goods group / fill / apply-template → economy_sim_crud (locks as today)
Player → GET /characters/economy/regions/{id}/card → classes {state, label, bar words}
```

### 3.18 Security
- No new endpoint. Admin writes keep `economy:settings` (regions/templates/groups/sim) and `economy:emit` (fill) as
  today; reads `economy:read`. Validation in Pydantic v1 (`_econ_number`, all-three-or-none shares, sum check);
  parameterised `text()` SQL only.
- Player card: words only (no shares, no money) — enforced by the existing no-numbers test.
- No money creation path added; the quota stays capped by the admin's season amount; world sum 0 asserted by QA.

### 3.19 Risks
- **Behaviour drift at rollout** — mitigated by normalisation (factors exactly 1.0 at the template mix), dead zone,
  zero-at-default stability terms; the only immediate changes are the wealth tax in regions whose purse already
  exceeds the (new, lower) norm — rural / agrarian / mining regions with purse ≈ 7 days vs norm 6–7 days pay ≈ 2 % of a
  small excess — and the quota/grant targeting. Kill switch `classes_enabled = 0`.
- **Per-class affordability** can raise hunger in poor regions with very high food prices and a purse well below norm
  (intended «poor drop first»); visible in the admin class report.
- **Template share edits re-base demand** of every region of that template — guide note.
- **Exact-shape tests** to update: `test_econ_sim.py` seed prefixes; `test_econ_regions_api.py` (fill result keys,
  history keys, groups/templates key sets, card `CARD_KEYS` — `classes` only when classes on); `test_econ_mint.py`
  quota tests that assume population split (the tick quota now uses deficits; `split_quota` itself unchanged);
  `test_econ_tick_mint.py`; grant-plan tests; events type lists.
- **No econ_core change** — the contract copies stay byte-identical (`check_econ_copies.sh` must still pass untouched).

### 3.20 Implementation notes / deviations (Backend Developer)

- **Share validation → 400 in the CRUD, not in Pydantic.** Validation errors of this API are 422; to give the 400s
  of 3.13 («Укажите все три доли», «Сумма долей должна быть 100 %») the all-three / sum checks live in
  `economy_sim_crud._class_shares` (region PUT and template PUT). Per-field bounds 0…1 stay in the schema (422,
  «Доля бедных: от 0 до 1»).
- **Class food need.** `need_k = today's food need × w_k` (the class's own per-capita weight, Σ = need × F_food), not
  `× w_k / F` — so a rich-heavy region whose food demand is ×F does not read as «fed» when only `need` is served. At the
  template mix both definitions are identical (F = 1).
- **`class_dpoor / class_drich`** = the whole change of the recount (event `class_shift` + mobility), from the stored
  shares before the step to the stored shares after it.
- **Event label** `EVENT_EFFECT_LABELS["class_shift"] = "сдвиг классов"` (lower case like the other labels — it is
  only used inside validation messages «Для эффекта «…»»).
- **Template shares in migration 037** are seeded only while the row is still at the column default
  (0.45 / 0.45 / 0.10), goods-group class weights only while at 1 / 1 / 1 — a re-run never overwrites admin edits.
- **Region PUT does not recompute `wealth_norm`** (the stored value is written by the recount, the fill and
  «Применить шаблон»); shares changed by PUT show up in the norm at the next recount. Norms of goods rows
  (`norm_stock`) are recomputed with the new class factors right away.
- **Helpers added** (no contract change): `econ_sim.class_factors`, `econ_sim.region_wealth_norm`,
  `econ_sim.class_report` (inputs for `econ_classes.class_report`), `econ_sim.prosperity_phrase`;
  `econ_tick.region_classes / load_class_bases / class_base_of / store_classes / region_deficits`;
  `econ_classes.event_shift / decimals / class_card`.
- **API shapes = section 3.11 / 3.13 exactly** (checked with the frontend contract): region list fields, detail
  `classes` = `{classes: {poor|middling|rich: {share, base_share, norm_days, norm_per_resident, money_per_resident,
  needs_per_resident_day, afford}}, wealth_norm, money_norm, deficit, r}` (`r` null when the norm is 0), history keys,
  template / goods-group fields, fill `reset_classes` → `classes_reset`, event outcome `class_shift {before, after}`,
  card `classes {state, label, bar}` with `phrases[0]` = class label.
- **Existing tests updated where the contract changed:** `test_econ_sim.py` (seed-exclusion prefixes),
  `test_econ_regions_api.py` (list / detail / fill / history / groups / templates key sets, card `classes` key and
  phrases), `test_econ_tick_mint.py` (the quota now needs a region below its norm: helper `_below_norm`; expected
  split by deficit; two new tests — waits while nobody is below the norm and retries, capped at the total deficit).

### Questions for PM (non-blocking — defaults chosen)
1. **Quota cap:** the season quota is capped at the total deficit (regions are lifted at most to their norm); the rest
   of the season amount is not issued. It is issued once, at the first tick of the season when anyone is below norm
   (retried each tick until then). Alternative: drip it over the season — more complex, not proposed.
2. **Country 10 % on the wealth tax:** applies (it is the channel that pools excess across the country). Say if the
   wealth tax should stay 100 % in the region.
3. **Prosperity liquidity** stays measured in absolute days of needs (14), not vs the class norm — a capital keeps
   looking more prosperous than a poor province with the same relative money.
4. **Event seeds:** class shifts added to Бунт −3 %, Набег −2 %, Чума −2 %, Богатая жила +2 %, Ярмарка +1 % and a new
   bad event «Разорение» −6 %. Edit / extend in the admin if the lore wants others.
5. **Template defaults** (poor / middling / rich): Столица 35/45/20, Портовый 45/42/13, Шахтёрский 55/37/8, Аграрный
   55/38/7, Лесной 50/42/8, Магический 30/50/20, Крепость 45/48/7, Сельская округа 60/35/5.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Migration + models + params.** Migration `037_econ_social_classes` (3.16: docstring, re-runnable DDL with column-exists checks, template / group seeds, region backfill from template, event-template JSON appends + `ruin` insert, downgrade). ORM columns on `EconRegionTemplate`, `EconRegion`, `EconRegionHistory`, `EconGoodsGroup`. `SimParams` 23 fields (3.14) + `ECON_SIM_PARAM_BOUNDS` / `ECON_SIM_INT_PARAMS` / `EconSimParamsIn`; `update_sim` cross-check `class_share_min < class_share_max`. **Do not touch `econ_core.py`. Do not commit or push.** | Backend Developer | DONE | `CS/alembic/versions/037_econ_social_classes.py` (new), `CS/models.py`, `CS/econ_sim.py` (params only), `CS/schemas.py`, `CS/economy_sim_crud.py` (`update_sim`) | — | Revision id ≤ 32 chars, down `036_econ_guild_orders`; in the container `alembic upgrade head` → `downgrade -1` → `upgrade head` clean; every templated region has shares = its template; `py_compile`. |
| 2 | **Pure math.** New `econ_classes.py` (3.1, 3.3–3.8, 3.11, 3.13 report). `econ_sim`: `GroupDef.class_demand`, `RegionState.classes / class_base`, optional `factors` on the demand/norm helpers, `starting_purse` with classes (= wealth norm), class path of `simulate_region` exactly per 3.2 (no-class path untouched statement-for-statement), new `SimResult` fields, `country_grants(..., deficits=None)` (3.10), `region_card(..., classes=None)` (3.11, prosperity phrases). `econ_mint.split_by_deficit` (3.9). `econ_events` one-shot `class_shift` (3.15). | Backend Developer | DONE | `CS/econ_classes.py` (new), `CS/econ_sim.py`, `CS/econ_mint.py`, `CS/econ_events.py` | #1 | `py_compile`; all existing `test_econ_sim.py`, `test_econ_events*.py`, `test_econ_mint.py` green unchanged (bit-identity of the no-class path). |
| 3 | **Tick integration.** `econ_tick`: `region_state(row, base)` with shares; template class bases loaded once per run and passed to `_process_region`; `load_groups` reads `class_demand`; one-shot `class_shift` applied with the other one-shots (only when the region has classes; outcome before/after); write shares / `class_dpoor` / `class_drich` / `wealth_norm` / `last_wealth_tax`; tax leg = `tax + wealth_tax`, metadata `wealth_tax`; history columns; `build_grant_plan` with deficits (3.10); `_quota_pass` with `split_by_deficit`, retry rule and metadata (3.9); docstring paragraph «Social classes (FEAT-194)» (lock order unchanged). | Backend Developer | DONE | `CS/econ_tick.py` | #2 | `py_compile`; existing `test_econ_tick*.py` green (fixtures without shares behave as before); dev container: manual recount writes `wealth_norm`, shares unchanged at default mix (dead zone), ledger world sum 0. |
| 4 | **Admin + card CRUD/API.** `economy_sim_crud`: regions list/detail fields + `class_report` (3.13; columns appended to `SQL_REGIONS`), `update_region` shares (validation, copy from template), `apply_template` resets shares + deltas + norm, `fill_regions` `reset_classes` + wealth-norm purse target + `classes_reset`, templates and goods groups (optional fields, None → kept), `region_history` keys, `region_card` passes `classes` (only when `classes_enabled` and shares present). Schemas: request fields + validators (all-three-or-none, sum 1 ± 0.001, bounds), `EconFillRequest.reset_classes`, `EVENT_EFFECT_LABELS["class_shift"]`. | Backend Developer | DONE | `CS/economy_sim_crud.py`, `CS/schemas.py`, `CS/economy_api.py` (only if a signature changes) | #3 | `py_compile`; curl in dev: PUT region shares 0.5/0.4/0.1 → stored, middling derived; bad sum → 400 Russian; apply-template resets; fill with/without `reset_classes`; card shows `classes` words and no numbers. |
| 5 | **Docs.** `docs/services/character-service.md`: classes section (columns, params, formulas 3.2–3.10, wealth tax in the `region_tick` leg, quota/grant by deficit, card contract, event effect); `docs/ARCHITECTURE.md` economy paragraph; remove/close the «норма богатства» idea wherever listed in `docs/ISSUES.md` (if present). | Backend Developer | DONE | `docs/services/character-service.md`, `docs/ARCHITECTURE.md`, `docs/ISSUES.md` (if applicable) | #4 | Docs match the implemented contracts. |
| 6 | **Frontend: player card.** `api/regionEconomy.ts`: `RegionCardClasses`, `classes?: … \| null`; `RegionEconomyCard.tsx`: class bar (3.11 word→weight widths, colours, legend «бедные — много …»), `phraseTone` includes `card.classes`; Tailwind only, 360px+, no `React.FC`; renders nothing extra when `classes` is absent. | Frontend Developer | DONE | `src/api/regionEconomy.ts`, `src/components/WorldPage/RegionEconomyCard.tsx` (+ optional new `RegionClassBar.tsx`) | #4 (contract only — can start from 3.11) | `npx tsc --noEmit` + `npm run build` pass in the container; mobile OK. |
| 7 | **Frontend: admin.** Types (`EconRegionItem`, region detail `classes` report, `EconRegionUpdate`, `EconRegionHistoryRow`, `EconRegionTemplate`, goods group, `EconSimParams` 23 keys, fill body `reset_classes`, event effect). `EconomyRegions.tsx`: column/card «Классы» (mini bar + Б/З/Бг %), «Сдвиг за пересчёт» (signed pp), «Деньги / норма» (%), fill dialog checkbox «Сбросить и классы к шаблону». `RegionEconomyEditor.tsx`: classes panel (3 % inputs with live sum, «как в шаблоне» hint, class report table: share, norm days, norm/money per resident, afford, deficit), apply-template text notes the reset. `EconomyTemplates.tsx`: 3 share inputs. `EconomyGoodsGroups.tsx`: 3 class-demand inputs. `EconomyTick.tsx`: group «Классы жителей и норма богатства». `paramHints.ts` (23). `guideSections.ts` + `EconomyGuide.tsx`: section «Классы жителей и норма богатства» (shares, demand per class normalised to the template, wealth norm, wealth tax → treasury and why money is not destroyed, mobility, quota/grants by deficit, card words, events, kill switch). `EventEffectsBuilder.tsx` + `eventLabels.ts`: «Сдвиг классов». All errors visible in Russian; 403 → «Недостаточно прав». | Frontend Developer | DONE | `src/types/economy.ts`, `src/api/economyAdmin.ts`, `src/components/Admin/EconomyPage/{EconomyRegions,RegionEconomyEditor,EconomyTemplates,EconomyGoodsGroups,EconomyTick,EconomyGuide,EventEffectsBuilder}.tsx`, `paramHints.ts`, `guideSections.ts`, `eventLabels.ts`, `regionBits.tsx` (shared bar) | #4 (contract), #6 (shared types) | `tsc` + `build` pass; admin edits shares on region/template/group; mobile layout OK; design-system classes. |
| 8 | **QA: pure math.** New `test_econ_classes.py`: factors exactly 1.0 at the template mix and the guard for zero weights; class parts sum to the total; wealth norm per template (± table 3.4) and the no-class fallback; `split_money` proportional; per-class afford (poor drop first when r or prices change); allocation rich → middling → poor under shortage and per-class hunger; tax factor; wealth tax (0 below norm, capped by purse, rate); stability terms 0 at defaults and signs; mobility dead zone, up/down, rich factor, bounds (min/max, admin-set out-of-bounds never pushed further), sum exactly 1 after rounding; card state/label/bar thresholds and gender, tail rules, prosperity phrases, **no numbers**. `test_econ_sim.py`: bit-identity of the no-class path (`classes=None` and `classes_enabled=0` give the same `SimResult` as before), class path at the template mix ≈ no-class path (demand/norm/tax equal within 1e-9, wages unchanged when no excess), 40-tick bounds/stress with classes; seed prefixes. `test_econ_mint.py`: `split_by_deficit` (cap at deficit, exact sum, nobody below → {}). `country_grants` with deficits (tilt, caps, sum ≤ pool, None = old). `test_econ_events.py`: `class_shift` parse/bounds/one_shots sum. | QA Test | DONE | `CS/tests/test_econ_classes.py` (new), `CS/tests/test_econ_sim.py`, `CS/tests/test_econ_mint.py`, `CS/tests/test_econ_events.py` | #2 | pytest green in character-service. |
| 9 | **QA: tick + API.** `test_econ_tick_classes.py` (SQLite harness): shares stay at default mix after a tick (dead zone), move with a forced boom / famine, deltas stored; wealth tax posted in the tax leg with the 10 % country leg, `last_wealth_tax`, treasury surplus released later (not same-tick wages), world sum 0; `wealth_norm` written; event `class_shift` applied once (resumed run idempotent), outcome before/after; region without shares / `classes_enabled=0` ticks as before; quota by deficit (only below-norm regions, cap, no region below → nothing posted and the next tick retries, key once per period); grant plan tilt. API tests: regions list/detail/history fields; PUT shares validation (all-three, sum, bounds, Russian 400s), copy from template; apply-template reset; fill `reset_classes` and purse target = norm; templates / goods groups optional fields (None keeps); sim PUT 23 params with bounds + min<max; card `classes` words both on and off (key absent when off), `_numbers(card)` still only `region_id`; hidden card unchanged; permissions (403 without `economy:settings`); SQL-injection-like strings rejected. Update the existing exact-shape assertions (fill keys, history keys, groups/templates key sets, card keys). | QA Test | DONE | `CS/tests/test_econ_tick_classes.py` (new), `CS/tests/test_econ_classes_api.py` (new), `CS/tests/test_econ_regions_api.py`, `CS/tests/test_econ_banks_admin_api.py`, `CS/tests/test_econ_tick_mint.py` | #4 | Full character-service pytest green in the container; `scripts/check_econ_copies.sh` passes (no copy changed). |
| 10 | **Review.** Contracts vs 3.11/3.13, math vs 3.2–3.10 (normalisation exact at the template mix, wealth tax outside same-tick wages, `treasury_target` from income tax only, quota retry + cap, grant tilt), migration up/down + backfill, no `econ_core` change, bit-identity tests, frontend rules (TS, Tailwind, no `React.FC`, mobile, Russian errors, design system), docs. **Live (Chrome on localhost):** migration applied; admin regions tab shows shares / shifts / money vs norm; edit a region's shares and a template's shares; fill with «сбросить и классы»; a manual recount keeps default-mix regions still, posts a wealth tax in a region whose purse was topped above norm (journal: tax leg + country leg); quota with an amount set goes only to below-norm regions; player card shows «… город, много бедняков»-style phrase and the 3-colour bar with no numbers; event «Разорение» started manually shifts shares; zero console errors. | Reviewer | TODO | all | #1–#9 | All automated checks (py_compile, character-service pytest, `check_econ_copies.sh`, tsc, build) + live verification pass. |

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-02
**Result:** PASS (no blocking issues; trivial fixes applied by the Reviewer, notes below)

#### Automated Check Results
- [x] `py_compile` (all modified/new backend files incl. migration 037 and tests) — PASS
- [x] `pytest` character-service full suite in the container (`--asyncio-mode=auto`) — PASS, 7297 passed / 1 skipped; class suites re-run after the Reviewer's fixes — 262 passed
- [x] `scripts/check_econ_copies.sh` — PASS, all copies identical; `git diff` shows no change to any `econ_core.py` / `econ_contract_cases.py` / `econ_ledger.py`
- [x] Alembic 037: `downgrade -1` (columns dropped, `ruin` deleted, `class_shift` removed from templates) → `upgrade head` clean; backfill gives every templated region exactly its template mix; dev class values restored afterwards
- [x] `npx tsc --noEmit` (frontend container) — PASS, 0 errors (also after the guide edits)
- [x] `npm run build` (`vite build` in the container) — PASS
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, localhost) — PASS

#### Invariants verified in code
- No-class path: every pre-FEAT-194 statement in `econ_sim.simulate_region` is kept verbatim behind `if not has_classes` / `factors is None` (`econ_sim.py:647-652, 655-660, 679-690, 711-724, 785-792`); the only addition there is the `wealth_norm=starting_purse(...)` result field, which does not feed back. Bit-identity fingerprints in `test_econ_classes.py` green.
- Factors exactly 1.0 at the template mix: `econ_classes.demand_weights` / `tax_factor` compute numerator and denominator in the same order (`econ_classes.py:81-97, 190-197`); confirmed live — a region at its template mix gives identical consumption/prices/tax with classes on and off (scratch comparison, see rollout section).
- Wealth tax: only above the norm (`econ_classes.wealth_tax`, `econ_classes.py:200-205`), inside the single `purse→treasury` leg of `region_tick` (`econ_tick.py:953`); `treasury_target` and wages from the income tax only (`econ_sim.py:741-744`). Live: Загрея leg 455 = tax 146 + wealth tax 309, country leg 45 = floor(455 × 0.1); summary invariant `ok`, `ledger_sum` 0.
- Mobility: bounded flows from the old shares, capped by `class_share_min/max`, poor/rich rounded to 6 dp and middling = 1 − poor − rich (`econ_classes.py:240-295`); dead zone holds fortress/agrarian still on dev.
- Quota: `split_by_deficit` caps at Σ deficit, only deficit > 0, nothing posted when nobody is below → retried next tick, period key remains the only marker (`econ_mint.py:155-166`, `econ_tick.py:1510-1527`).
- Grant tilt: `grant_deficit_share` of the pool by deficit, capped per region, rest by population, `deficits=None` = old statement (`econ_sim.py:515-541`).
- Card: `classes` = {state, label, bar words}; `phrases[0]` = class label, prosperity phrase without adjective; no numbers (API checked live: only `region_id` and date parts of `updated_at`).

#### Live Verification Results
- Player `/world/region/10` (Шепшир, rural): «Бедный регион» (gold tone) first, then «Регион сыт» …; 3-colour bar + legend «бедные — много, зажиточные — средне, богатые — мало», no numbers. Region 9 card via API: «Богатый регион», «Регион процветает» as a separate phrase.
- Admin «Регионы»: column «Классы» (mini bar, «Б 60 · З 35 · Бг 5 %», shift «сдвиг: Б +0,007 · Бг −0,001 п. п.»), «% нормы» under the purse.
- Region editor: classes panel with live sum; 50/35/5 → «Сумма: 89,97 % — Сумма долей должна быть 100 %» (client); API: bad sum → 400 «Сумма долей должна быть 100 %», one share → 400 «Укажите все три доли», negative → 422 «Доля бедных: от 0 до 1»; class report table (norm/money/needs per resident, «покупает»).
- Templates: share summary per card + share inputs; saving unchanged template OK. Goods group «Продовольствие»: «Спрос по классам» 1 / 1 / 1,2. «Пересчёт»: group «Классы жителей и норма богатства» with «?» hints. Events → Шаблоны: «Сдвиг классов −3 % вниз (разово)» … and «Разорение». Guide section present.
- Manual recount (run 84): 5/5 regions, `region_tick` metadata carries `wealth_tax`, summary «Сходится».
- Mobile 360 px (same-origin iframe): world card and admin regions/editor — `scrollWidth == clientWidth` (no horizontal overflow), class report switches to a card layout.
- Console errors: none.

#### Trivial fixes applied by the Reviewer
| File:line | Fix |
|---|---|
| `services/character-service/app/econ_sim.py:704, 714` | whitespace typos `want =sum(` / `cap =params` → `want = sum(` / `cap = params` (no-class path text restored to the original statement) |
| `services/character-service/app/economy_sim_crud.py:933` | `params =econ_sim` → `params = econ_sim` |
| `services/frontend/app-chaldea/src/components/Admin/EconomyPage/EconomyGuide.tsx:210, 620, 929, 1061, 1526, 1695` | stale guide texts: grant «по числу жителей» → quarter by deficit; fill / «Стартовый кошелёк» «7 дней» → wealth norm; «Квота не пришла» now says only regions below the norm get a share |

#### Non-blocking notes
1. `econ_sim.py:353-387` + `econ_classes.py:163-168` — per-class affordability has a cliff the old scalar did not have: the poor buy fully only while `purse / wealth_norm ≥ price_level_of_poor_basket × afford_days / class_norm_days_poor` (≈ 1/3 at prices ×1). Below that the poor lose consumption sharply (dev sweep at r = 0.15: hunger 0.24–0.32 vs 0 without classes, stability −7…−11, consumption −24…−29 %). Intended («poor drop first») but see the rollout section.
2. Editing a template's shares re-bases its regions immediately (their own shares stay, so factors ≠ 1); documented in the guide — intended per 3.3.
3. Region PUT does not refresh `wealth_norm` until the next recount (3.20 deviation) — fine.

#### Rollout risk on prod (assessment)
Method: read-only scratch simulation in the dev container (`simulate_region` with classes on vs `classes_enabled=0`, every dev region set to its template mix, purse swept r = 0.15 … 1.5 of the new norm, plus 40 ticks forward), against the prod numbers in section 2.10 / 3.12.
- **At the template mix nothing jumps**: demand, consumption, norms, prices and income tax are identical (max Δ 0) for r ≥ ~0.35; stability/prosperity identical; class stability terms are 0 for all seeded templates and taxes ≤ 12 %.
- **Хикари-like capital** (purse ≈ 7 days of needs, norm ≈ 10 days → r ≈ 0.70): no wealth tax, no drift (score in the dead zone), no change except card wording and becoming a quota / grant-tilt candidate.
- **Rural / agrarian / mining / fortress with purse ≈ 7 days** (norms 6–7 days → r ≈ 1.0–1.2): a small wealth tax (2 % of a ~1-day excess per recount → treasury, released back slowly), no visible price/stability change; mobility signal at most at the dead-zone edge, drift ≤ ~0.01 pp per recount.
- **Only risk:** a prod region whose purse is below ~1/3 of its new norm (≈ 2–3 days of needs, e.g. a purse drained by caravans/guild/banks or never filled) — the poor start going hungry on the first recount (hunger up to ~0.3, stability −7…−11 per the sweep, mix drifts down ~0.05 pp/recount). On dev, Шепшир sits exactly at that edge (r = 0.34). Recommendation for the rollout: after deploy check «Регионы» → «% нормы»; any region under ~40 % → «Заполнить регионы по шаблонам» (fund purses; classes kept) or set the season quota, which now goes precisely to such regions. If prod purses are still the inflated pre-FEAT-186 values (r ≫ 1), the wealth tax would move 2 %/recount of the excess into treasuries and mobility would push classes up at the max rate (~6.6 pp/season) — the 2026-10-29 «Заполнить … вернуть излишек» step must have been done first.
- Conclusion: **safe to roll out** for regions with purse ≥ ~40 % of the new norm (all prod regions per the memory figures); no jump in prices/consumption/stability and no noticeable class drift on the first recounts. Kill switch `classes_enabled = 0` reverts the math instantly.

All checks passed. Changes are ready for completion.

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-02 — PM: фича создана, требования согласованы с пользователем, запускаю анализ
[LOG] 2026-11-02 — Codebase Analyst: анализ симуляции регионов и денежных потоков готов (раздел 2): кошелёк сейчас влияет только на доступность и ликвидность, автоматического «стока» денег нет — для сжигания излишка нужен новый тип операции в econ_core (4 копии); составлен список мест для учёта классов и рисков
[LOG] 2026-11-02 — Architect: спроектировано 10 задач (миграция 037, новый чистый модуль econ_classes, классовый спрос/налог/норма богатства/мобильность, квота и гранты по нехватке, событие «сдвиг классов», карточка игрока словами, админка); econ_core не меняется, новых эндпоинтов и прав нет
[LOG] 2026-11-02 — Frontend Dev: задача #6 готова — карточка региона: фраза класса первой, полоска бедные/зажиточные/богатые из слов «мало/средне/много» (ширины по таблице 3.11, без цифр), легенда; без `classes` карточка как раньше (новый RegionClassBar.tsx)
[LOG] 2026-11-02 — Frontend Dev: задача #7 готова — админка: «Регионы» (колонка «Классы» с мини-полоской, Б/З/Бг %, сдвиг за пересчёт, % нормы у денег жителей, галочка «Сбросить и классы к шаблону» в заполнении), редактор региона (доли с живой суммой и «подставить как в шаблоне», отчёт по классам, норма и налог с накоплений, история), шаблоны (3 доли), группы товаров (спрос по классам), «Пересчёт» (группа из 23 параметров с подсказками «?» и проверкой нижняя < верхняя граница), событие «Сдвиг классов» (в процентах, итог до/после), раздел гайда и рецепт; поправлены тексты про квоту и дотацию «по населению»
[LOG] 2026-11-02 — Frontend Dev: tsc --noEmit и npm run build в контейнере проходят
[LOG] 2026-11-02 — Backend Dev: начал задачи #1–#5
[LOG] 2026-11-02 — Backend Dev: задача #1 готова — миграция 037 (доли классов у шаблонов и регионов, сдвиг за пересчёт, норма и налог с накоплений, история, спрос классов у групп, «сдвиг классов» в событиях + «Разорение»), модели, 23 параметра; upgrade → downgrade -1 → upgrade в контейнере чисто, регионы dev получили доли своих шаблонов
[LOG] 2026-11-02 — Backend Dev: задача #2 готова — новый econ_classes.py, классовый путь simulate_region (без классов — прежние инструкции), квота по нехватке, гранты с перевесом, эффект class_shift, карточка словами
[LOG] 2026-11-02 — Backend Dev: задача #3 готова — тик пишет доли / сдвиг / норму / налог с накоплений (в той же ноге налога region_tick), история, гранты и квота по нехватке (никого ниже нормы — ждём следующий пересчёт)
[LOG] 2026-11-02 — Backend Dev: задача #4 готова — админ-API регионов / шаблонов / групп / заполнения / истории и карточка игрока; проверено на dev (400 на неверные доли, сброс шаблоном, заполнение с «сбросить и классы»)
[LOG] 2026-11-02 — Backend Dev: задача #5 готова — раздел «Social classes and the wealth norm» в docs/services/character-service.md, абзац в ARCHITECTURE.md; в ISSUES.md идеи «нормы богатства» не было
[LOG] 2026-11-02 — Backend Dev: 4 ручных пересчёта на dev — сумма мира 0; крепость и аграрный край в мёртвой зоне (доли не двигаются), цены и налоги как раньше; столица и шахтёрский (кошелёк dev в 1,7 и 3 раза выше нормы) платят налог с накоплений и медленно богатеют; полный pytest character-service зелёный, копии econ_core не менялись
[LOG] 2026-11-02 — QA Test: задача #8 готова — новый test_econ_classes.py (134 теста): факторы ровно 1.0 у каждого шаблона, путь «без классов» (NULL-доли и classes_enabled=0) побитово совпадает с эталонными отпечатками старого econ_sim (24 сценария), норма богатства по шаблонам (таблица 3.4), деньги и доступность по классам, раздача при нехватке богатые→зажиточные→бедные, голод по классам, налоги, налог с накоплений, стабильность, мобильность (мёртвая зона, границы, сумма ровно 1), карточка словами без цифр, квота и гранты по нехватке, «сдвиг классов» и «Разорение», 800 пересчётов от двойной нормы — не разгоняется
[LOG] 2026-11-02 — QA Test: задача #9 готова — test_econ_tick_classes.py (16 тестов: тик на SQLite — доли стоят на месте, налог с накоплений в той же ноге налога с 10 % стране и не возвращается зарплатой в том же тике, мобильность, событие применяется один раз, квота только регионам ниже нормы и раз за сезон, перевес грантов, 30 пересчётов — сумма мира 0), test_econ_classes_api.py (56 тестов: поля списка/деталей/истории, проверки долей 400/422, сброс шаблоном, заполнение с reset_classes, шаблоны и группы, карточка без цифр, 401/403, инъекции), +8 тестов «сдвиг классов» в test_econ_events_admin_api.py
[LOG] 2026-11-02 — QA Test: багов не найдено; замечание — перекрёстная проверка class_share_min < class_share_max недостижима (границы 0…0.3 и 0.4…1 не пересекаются), это защитная проверка, не ошибка
[LOG] 2026-11-02 — Reviewer: начал проверку
[LOG] 2026-11-02 — Reviewer: py_compile, полный pytest character-service (7297 passed), check_econ_copies, tsc, vite build, compose config — всё зелёное; миграция 037 вниз/вверх чисто, доли dev восстановлены
[LOG] 2026-11-02 — Reviewer: живая проверка в Chrome: карточка игрока (фраза класса + полоска без цифр), «Регионы», редактор с отчётом и ошибками на русском, шаблоны, группы товаров, «Пересчёт» с подсказками, «Сдвиг классов» и «Разорение», ручной пересчёт (налог с накоплений в той же ноге, сводка сходится), 360 px, ошибок в консоли нет
[LOG] 2026-11-02 — Reviewer: мелкие правки — пробелы в econ_sim/economy_sim_crud, устаревшие тексты гайда (гранты «по числу жителей», кошелёк «7 дней», квота)
[LOG] 2026-11-02 — Reviewer: риск выкатки — при долях шаблона цены/потребление/стабильность не меняются; голод бедных только в регионах с кошельком ниже ~1/3 новой нормы — после выкатки проверить «% нормы» в «Регионах»
[LOG] 2026-11-02 — Reviewer: проверка завершена, результат PASS
[LOG] 2026-11-02 — PM: ревью PASS, фича закрыта (DONE), отчёт пользователю
```

## 7. Completion Summary (filled by PM on completion — in Russian)

**Сделано (2026-11-02):**
- У каждого региона доли бедных / зажиточных / богатых; стартовые — по шаблону (столица 35/45/20, магический 30/50/20,
  порт 45/42/13, лесной 50/42/8, шахтёрский 55/37/8, аграрный 55/38/7, крепость 45/48/7, сельская округа 60/35/5),
  админ правит регион и шаблон; «Применить шаблон» сбрасывает доли, «Заполнить» — только с галочкой.
- Норма богатства: запас денег на N дней покупок по классам (бедные 3, зажиточные 7, богатые 21 день) — столица
  ≈ 10 дней, село ≈ 6. Сверх нормы — налог с накоплений 2 % излишка за пересчёт в казну. Сжигания нет.
- Классы влияют на спрос по группам, налог с дохода (0,3 / 1,0 / 2,0), стабильность, покупательную способность
  (при нехватке первыми не получают бедные). Доли двигаются сами медленно, с «мёртвой зоной», в пределах 2–90 %.
- Квота сезона — только регионам ниже нормы, по нехватке; четверть грантов страны — по нехватке.
- События: «Сдвиг классов» (Бунт, Набег, Чума, Богатая жила, Ярмарка) и новое «Разорение».
- Карточка: «Бедный регион / Зажиточный город…» + полоска без цифр; админка — доли, отчёт по классам, 24 настройки.
- При стандартном составе шаблона цены, налог и жалованье — как раньше; выключатель `classes_enabled`.
- Миграция character 037. Ревью PASS, проверено вживую.

**После выкатки:** проверить в «Регионы» колонку «% нормы»; регионам ниже ~40 % нормы дать «Заполнить» или квоту.
