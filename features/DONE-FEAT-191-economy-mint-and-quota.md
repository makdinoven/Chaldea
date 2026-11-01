# FEAT-191: Экономика, этап 5а — монетный двор и месячная квота

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-01 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Продолжение экономики: FEAT-181 (книга счетов), FEAT-182 (живые регионы), FEAT-183 (торговцы НПС), FEAT-184 (банки),
FEAT-186 (масштаб населения), FEAT-187 (события регионов). Этап 5 разбит на три фичи: **5а (эта) — монетный двор и
квота**, 5б — караваны НПС, 5в — заказы через гильдию торговцев.

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас новые марки появляются только из админской эмиссии (кнопка). Этап 5а даёт миру два штатных источника новых
денег, как договаривались в начале экономики: **монетный двор** (марки чеканятся из руды) и **фиксированную квоту
раз в игровой месяц**. Деньги по-прежнему движутся только проводками книги счетов; новые марки выходят со счёта
`emission`, сумма мира = 0.

### Бизнес-правила (согласовано с пользователем 2026-11-01)
- **Монетный двор один на страну, в столице.** Столица страны — регион, выбранный в админке (по умолчанию — регион
  страны с шаблоном «столица»; если таких несколько или ни одного — админ выбирает вручную, без двора страна не чеканит).
- **Двор работает двумя путями (оба):**
  1. *Сам, в 6-часовом пересчёте:* забирает часть руды/металла из запасов столичного региона (только излишек сверх
     нормы запаса, чтобы не морить ремесло) и чеканит марки по курсу «марок за единицу». Марки идут в **казну
     страны** (двор — государственный), дальше их разносят обычные гранты страны регионам.
  2. *Игроки:* персонаж приносит предмет-руду к НПС с новой ролью **«Монетчик»** в столице и получает марки. Какие
     предметы годятся и сколько за них дают — настраивается в админке (список «руда для чеканки» с курсом за штуку).
     Сданная руда пополняет запас руды/металла столичного региона. Доступ как у банкира/торговца: персонаж стоит в
     локации монетчика, пост с обращением к НПС (FEAT-145), мёртвый монетчик не работает.
- **Лимит чеканки** — общий на страну за игровой месяц (двор + игроки вместе), задаётся в админке. Исчерпан —
  двор в пересчёте не чеканит, монетчик отказывает с понятным сообщением («Монетный двор исчерпал лимит до …»).
- **Квота раз в игровой месяц:** фиксированная сумма (настройка в админке «Экономика → Настройки») один раз в начале
  каждого игрового месяца выпускается со счёта `emission` **сразу в казны регионов**, участвующих в симуляции,
  пропорционально населению. Повторный пересчёт в том же месяце квоту второй раз не выдаёт (идемпотентно).
- **«Игровой месяц» = сезон вместе с праздником после него (49 реальных дней, 4 раза в год)** — тот же период,
  что у событий регионов. В интерфейсе называть «сезон» (не «месяц»). По игровому календарю, год не хардкодить.
- **Порог двора — настройка:** двор в пересчёте берёт руду, только если запас столицы выше X % нормы (X в админке,
  по умолчанию 100 %); чеканит только то, что выше этого порога.
- **Чеканка игроком засчитывается как заработок** для заданий боевого пропуска «заработай N марок».
- Руда списывается в одной транзакции с выдачей марок: либо всё, либо ничего.
- Админская эмиссия остаётся как ручной инструмент.

### UX / Пользовательский сценарий
1. Игрок с рудой приходит в столицу к Монетчику, пишет пост с обращением, нажимает «Монетный двор».
2. Видит, какую руду принимают и по какому курсу, сколько осталось лимита в этом месяце; выбирает руду и количество.
3. Руда уходит из инвентаря, марки приходят на баланс; в истории операций — «Чеканка».
4. Админ в «Экономика» видит: столицу/двор каждой страны, курс и лимит, сколько отчеканено в этом месяце (двором и
   игроками), историю квот; может поменять параметры. В карточке региона-столицы игрок видит «Монетный двор».

### Edge Cases
- У страны нет столицы / столица не участвует в симуляции → двор не работает (и в пересчёте, и у монетчика —
  понятное сообщение); квота идёт только участвующим регионам.
- Руды в запасе столицы меньше нормы → двор в пересчёте ничего не берёт.
- Двойной клик / повтор запроса у монетчика → одна проводка (идемпотентность).
- Лимит кончается посреди сдачи игрока → принимается только то, что влезает (или отказ целиком — решит архитектор,
  главное без частичной потери руды).
- Месяц сменился, а пересчёт был пропущен → квота выдаётся при первом пересчёте нового месяца.

### Вопросы к пользователю (если есть)
- [x] Двор — двор сам + игроки? → Оба. Один на страну, в столице.
- [x] Квота куда? → Сразу в казны регионов; размер — настройка в админке.
- [x] Порядок частей 5а/5б/5в → на усмотрение PM: 5а → 5б → 5в.
- [x] Что такое «игровой месяц»? → сезон + праздник после него, 49 дней (вариант b аналитика).
- [x] Чеканка = заработок для боевого пропуска? → Да.
- [x] Двор в пересчёте простаивает → сделать порог настройкой (% нормы, по умолчанию 100 %).
- [x] Стартовые квота и лимит → нули (выключено), пользователь включит в админке сам.
- [x] Игрок сдаёт больше остатка лимита → **принимать сколько влезет**, остальная руда остаётся у игрока
  (решение 2026-11-01, меняет первоначальный «отказ целиком» архитектора).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

All paths below are relative to `services/`. CS = `character-service/app`.

### Affected Services

| Service | Type of changes | Files |
|---|---|---|
| character-service | new op types, mint/quota tick steps, Монетчик player API, admin API, new tables + migration 034 | `CS/econ_core.py` (canonical), `CS/econ_tick.py`, `CS/econ_sim.py` (or a new pure `econ_mint.py`), `CS/economy_api.py`, new `CS/economy_mint_crud.py` (pattern of `economy_bank_crud.py`), `CS/models.py`, `CS/schemas.py`, `CS/economy_sim_crud.py` (`region_card`, `_run_dict`), `CS/alembic/versions/034_*.py`, `CS/tests/econ_contract_cases.py` (canonical) |
| inventory-service | **byte copy only** of `econ_core.py` (+ `tests/econ_contract_cases.py`); per-service `tests/test_econ_contract.py` if new asserts are added | `inventory-service/app/econ_core.py`, `.../tests/econ_contract_cases.py` |
| locations-service | **byte copy only** (same two files) | `locations-service/app/econ_core.py`, `.../tests/econ_contract_cases.py` |
| dungeon-service | **byte copy only** (same two files) | `dungeon-service/app/econ_core.py`, `.../tests/econ_contract_cases.py` |
| battle-pass-service | maybe: decide whether player minting counts as «gold earned» for gold missions | `battle-pass-service/app/crud.py:408` `LEDGER_EXCLUDED_OP_TYPES` |
| user-service | only if a new permission is wanted (see 7) | `user-service/alembic/versions/0033_*`, `tests/test_rbac_permissions.py` |
| frontend | new NPC role, Монетчик modal, admin «Монетный двор» UI, quota setting, op labels, region card line, guide/hints | see section 6 below |

### 1. Ledger: how money is issued today, op/leg registry, copy contract

- Source accounts: `KIND_EMISSION` / `KIND_ADJUSTMENT` singletons (`CS/econ_core.py:46-47, 79-83`), may go negative (`NEGATIVE_ALLOWED_KINDS` :74). `AccountRef.emission()` :262.
- **Gate that matters for this feature:** `validate_operation` rejects any leg touching emission/adjustment unless `op_type in SOURCE_OP_TYPES` (`econ_core.py:493-494`); `SOURCE_OP_TYPES = {genesis, admin_emission, admin_adjust}` (:152). `COMMENT_REQUIRED_OP_TYPES = {admin_emission, admin_adjust}` (:155). New op types (e.g. `mint`, `monthly_quota`) must be (a) added as constants, (b) added to `OP_TYPES` (:141-149), (c) added to `SOURCE_OP_TYPES`. They should NOT go into `COMMENT_REQUIRED_OP_TYPES` (automatic ops have no admin comment).
- Tax: `emission` is not in `TAX_SOURCE_KINDS` (:88), so `emission -> region_treasury` / `-> country_treasury` legs generate no country tax even with `apply_tax=True`; all existing emission callers still pass `apply_tax=False` explicitly. A player-mint flow that also moves money between non-source accounts (e.g. a fee to the treasury) would need explicit thought about tax.
- Leg types: `LEG_TYPES` / `CALLER_LEG_TYPES` (:161-173). `main` is enough for mint and quota; a new leg type is not required.
- Today's emission callers (all `OP_ADMIN_EMISSION`):
  - admin button `POST /characters/admin/economy/emission` → `economy_api.py:198 post_emission` → `economy_crud.emit` (`economy_crud.py:433-445`), target restricted by `EMISSION_TARGET_KINDS` (:25), no idempotency key, comment required.
  - «Заполнить регионы» `economy_sim_crud.py:437-466` (emission ↔ purse/treasury, key `econ_fill:r:{rid}:p{last_posting}:t{last_posting}`).
  - «Пополнить кассы торговцев» `economy_merchants_crud.py:221-231` (key `merchant_fund:r:...`).
  - These are admin-triggered and reuse `admin_emission`; the new automatic flows need their own op types so the journal / summary can tell them apart.
- `post_operation` (`CS/econ_ledger.py:216-297`): validates, adds tax legs, inserts the journal row (UNIQUE `idempotency_key` → `DuplicateOperation`, :205-213), locks/applies accounts in fixed order (characters asc id, then `econ_accounts` asc id; `econ_core.apply_steps` :585-602), never commits. `econ_operations.op_type` is `VARCHAR(50)` (`CS/models.py:481`), `idempotency_key` `VARCHAR(128)` → **no DB migration needed for new op types**.
- **CI copy contract:** `scripts/check_econ_copies.sh` (job `econ-contract-copies`, `.github/workflows/ci.yml:116-124`, deploy `needs:` it at :129) sha256-compares:
  - `econ_core.py`: CS (canonical) → inventory-, locations-, dungeon-service;
  - `tests/econ_contract_cases.py`: CS (canonical) → same 3;
  - `econ_ledger.py` sync (CS → inventory) and async (locations → dungeon) — not affected unless the executor changes.
  Adding op types = edit `CS/econ_core.py` and copy byte-for-byte to 3 services. If contract cases are added (precedent: FEAT-187 `REGION_EVENT_OP_TYPE_NAME` + cases, `econ_contract_cases.py:727-738`), copy that file too, and each service's own (not byte-copied) `tests/test_econ_contract.py` gets the new asserts (precedent `CS/tests/test_econ_contract.py:249-252`, same lines in dungeon :253, inventory :292, locations). Note `CS/tests/test_econ_bank.py:246` asserts `len(BANK_OP_TYPES) == 8` — unaffected as long as new ops are not bank ops.
- Other op-type consumers: frontend `OP_TYPE_LABELS` (`frontend/.../Admin/EconomyPage/economyLabels.ts:5-41`); `economy_api.py:168-171` validates journal filters against `core.OP_TYPES` (automatic); `battle-pass-service/app/crud.py:408-418` `LEDGER_EXCLUDED_OP_TYPES` (sums postings into character accounts as «gold earned» for missions — a player `mint` posting would count unless excluded); `CS/crud.py:2362-2373` reward/deduct whitelists (not relevant).
- Summary: `economy_crud.get_summary` (:155-211) computes `issued = -(emission + adjustment)`; no per-op breakdown, so mint/quota appear only as a larger «issued».

### 2. The 6 h tick

- Runner `CS/econ_tick.py:1099 run_tick`: load params → claim (`_claim_auto` :577 by `slot = floor(unix/21600)` UNIQUE, or `_claim_manual` :609 with `slot NULL`) → `_fill_plan` (:570) computes the **grant plan once at claim time** (`build_grant_plan` :305: per country `econ_sim.country_grants` = `country_grant_share` (0.25) × positive country balance split by population, `econ_sim.py:410-422`) and stores it in `econ_tick_runs.grant_plan` → `_prepare_merchants` → `_events_pass` → **region loop** `_process_region` (:635, one transaction per region) → `_prepare_banks` / `_bank_pass` / `_collection_pass` (own transactions) → run row finalised (:1191-1205) → `purge_old`.
- Region transaction lock order (module docstring :47-55 and `docs/services/character-service.md` 841+): `econ_regions → econ_region_goods → econ_region_events (asc id) → npc_shop_items (asc id) → econ_banks → bank_deposits → bank_loans → characters (asc id) → econ_accounts (asc id)`. `econ_regions` row FOR UPDATE, skipped if `last_run_id == run_id` (:661-668); goods rows FOR UPDATE (:670-673); `region_tick` op key `region_tick:{run_id}:r:{region_id}` (:777).
- **Where a mint step fits:** the auto-mint takes stock from the capital's `econ_region_goods('ore_metal')` row, so it naturally belongs **inside the capital region's transaction** after `simulate_region` updates the goods rows (around :733-747, after stocks/norms are recomputed) — the goods row is already locked there; posting `emission → country_treasury` touches only `econ_accounts` (last in lock order). Alternative: a separate pass after the region loop (like banks) that re-locks `econ_regions → econ_region_goods` of each capital. Either way the mint money reaches regions only via the **next** run's grant plan, because the grant plan is fixed at claim.
- **Monthly quota step:** emission → region treasuries of participating regions, pro-rata by population. Natural place: a separate pass at run start (after claim, before the region loop) or after the region loop, in its own transaction, idempotency key per game month (e.g. `monthly_quota:{year}:{month}` for one multi-leg operation, or per region `monthly_quota:{y}:{m}:r:{rid}`). Participating regions = `SQL_PARTICIPATING` (`econ_tick.py:292-302`: `template_code IS NOT NULL AND population > 0`, joined to existing `Regions`); `run.grant_plan` keys are the same list. Pro-rata split pattern with floor: `econ_sim.country_grants` (:410-422). Manual runs (`slot NULL`) also call `run_tick`; the month key makes them safe. Missed months: the brief wants «first tick of the new month» — with a per-month key only the current month is issued (missed earlier months are not caught up), consistent with how missed slots are never caught up (:7-8).
- Region goods storage: `econ_region_goods` (`CS/models.py:621-640`) PK `(region_id, group_code)`, `stock` / `norm_stock` `Numeric(16,3)` in **abstract region units** (not items). `norm_stock` is recomputed every tick by `econ_sim.norm_stock` (`econ_sim.py:282-302`: `norm_days × (household demand/day + input use by processing groups/day)`) and also by `economy_sim_crud._recompute_norms` (:102). Stock above `stock_cap_mult × norm` spoils (`econ_sim.py:505-510`). Group defs `econ_goods_groups` (`models.py:534-546`; `ore_metal` base_price 10, `028_econ_living_regions.py:46`); `ore_metal` is an input of weapons (3), armor (1), jewelry (1), tools (1) (`028`: `INPUTS`).
- Item → region units conversion already exists: `econ_core.units_per_item(base, group_base)` (:885-893) = item base price / group base price; `item_base_price` (:775-781).
- Templates: `econ_region_templates` (`models.py:562-577`) PK `code`; seed codes `capital, port, mining, agrarian, forest, magic, fortress, rural` (`028:73-89`). A region's template is `econ_regions.template_code` (`models.py:597`). «Capital» is identified **only by `template_code = 'capital'`** — no other flag. Admins can edit templates but not create codes via API (`economy_sim_crud.update_template` :637).
- **`Countries` has no capital field** (`locations-service/app/models.py:28-48`; table owned by locations-service, mirrored in `photo-service/models.py:37`). `Regions.country_id` NOT NULL (`locations-service/app/models.py:55`). A capital setting is best stored in a character-service econ table (keyed by country_id, no FK — same convention as `econ_regions.region_id`), avoiding a locations-service migration.
- Country treasury account: `AccountRef.country(id)` (`econ_core.py:238`), may go negative; created lazily or by `economy_crud.ensure_treasury_accounts`.
- **Important data fact:** the `capital` template's `ore_metal` production ratio is **0.8** («сырьё привозное», `028:94`), and capitals also consume ore_metal as input for weapons/armor/jewelry/tools at ratios 1.2-1.4. So in a capital ore_metal stock normally sits **below norm**; the «only surplus above norm» auto-mint will usually take nothing until caravans (5б) or players bring ore. See risks.

### 3. Game calendar — there is no «game month»

- The calendar lives only in locations-service: `locations-service/app/crud.py:3196-3250` `YEAR_SEGMENTS` (4 seasons × 39 real days + 4 festivals × 10 = `DAYS_PER_YEAR = 196`), `DAYS_PER_WEEK = 3`, `compute_game_time(epoch, offset_days, now)` → `{year, segment_name, segment_type, week, is_transition}`. Config row `game_time_config(epoch TIMESTAMP, offset_days INT)` (`locations-service/app/models.py:423-429`), public `GET /locations/game-time` (`locations-service/app/main.py:2014-2029`, returns epoch, offset_days, server_time, computed), admin PUT `:2053` can change epoch/offset at any time. Frontend mirror: `frontend/app-chaldea/src/utils/gameTime.ts`. character-service has only a segment-count constant (`CS/crud.py:233`) and reads the segment over HTTP (`CS/locations_client.py:155-180 get_game_segment_sync`, used by events `econ_tick.py:986-994`).
- **Nothing in the codebase (backend, frontend, docs) defines a game month.** grep for `game_month` / `месяц` finds only the FEAT-181 brief («квота на игровой месяц», `FEAT-181-world-economy.md:32`). A month definition must be decided (see Questions).
- Reliable detection once defined: compute a monotonically increasing period index from `elapsed_real_days = floor((now - epoch)/86400) + offset_days` (same formula as `compute_game_time`) and use it in the idempotency key; read `game_time_config` directly from the shared DB (one SQL row) or via `GET /locations/game-time` (HTTP, then the tick must tolerate the service being down — events already degrade gracefully). Caveat: an admin change of `offset_days` / `epoch` can move the index backwards (re-issuing an already issued month if keyed by index alone) or skip months — store the last issued period and only issue when the period is strictly greater, or key by period and accept the edge.

### 4. NPC roles — template for «Монетчик»

- Storage: `characters.npc_role VARCHAR(50)` free string (`CS/models.py:65`), **no backend whitelist** (schemas :745-818 have no validator). Admin NPC form sets it (`main.py:3085-3120` update path; teleport role cleanup precedent).
- Banker gate (`CS/economy_bank_crud.py:47 BANKER_ROLE = "banker"`, `:283-311 resolve_banker / with_region / banker_context`): fixed order — 1 JWT + ownership + not NPC (`_player_character` :271) → 2 NPC exists, `is_npc`, role matches (404) and `npc_status != "dead"` (409) → 3 activity lock on writes (`activity_lock.lock_message`) → 4 same `current_location_id` → 5 FEAT-145 gate → 6 location → region via `econ_ledger.resolve_location`.
- Router pattern (`CS/economy_api.py:603-725`): GET view without gate (`/economy/bank/npc/{npc_id}`), POST actions `async def` → `_bank_precheck` in threadpool with the read txn rolled back (:645-655) → `await locations_client.check_npc_gate(character_id, location_id, npc_id)` (`CS/locations_client.py:328-361`, `GET /locations/internal/action-gate`, fail-closed, `GateUnavailable` → 503) → `_bank_commit` re-runs the checks inside the write txn, runs the flow, commits, maps `EconomyApiError` / `IntegrityError` (409) / `EconomyError` (400) / `SQLAlchemyError` (500) (:658-681). Player idempotency: client `request_id` in the body → key `{prefix}:{character_id}:{request_id}` (`economy_bank_crud.py:528` etc.); `DuplicateOperation` → 409 `MSG_DUPLICATE` (:246-247).
- Merchant variant lives in locations-service (`locations-service/app/main.py:3033-3145 sell_to_npc`, gate `_require_npc_gate` :841).
- Frontend: roles list `frontend/app-chaldea/src/constants/npc.ts:1-45` (`NPC_ROLES`, `NPC_ROLE_LABELS`, `NPC_ROLE_ICONS`; banker added at :19 / :43) — used by `AdminNpcsPage.tsx`. NPC profile buttons `components/pages/LocationPage/NpcProfileModal.tsx`: shop button by `hasShop` probe (:88-96, :275), bank by `npc.npc_role === 'banker' && isCharacterHere && characterId` (:314-332) opening `BankModal/BankModal.tsx` (+ tabs `BankDepositsTab`, `BankLoanTab`, `BankTransfersTab`, `BankParts.tsx`, `bankFormat.ts`). A «Монетный двор» button + modal follow the same shape. Admin «Банки» tab lists bankers per region via `economy_bank_crud.bankers_by_region` (:1270-1280) — same query shape fits «монетчики столицы».

### 5. Inventory: removing ore, item → group, storing the ore list

- character-service today **never removes inventory items**; it only calls inventory-service for grants/reads (`CS/crud.py:93, 1135`, `CS/main.py:1487, 3165`, base URL `CS/config.py:9`).
- Available ways:
  1. `DELETE inventory-service /inventory/{character_id}/items/{item_id}?quantity=` (`inventory-service/app/main.py:669-702`) — **player JWT** + ownership, no internal-token variant, no idempotency, own commit. Used by locations-service `sell_to_npc` (:3085-3104) as a non-atomic two-phase flow with compensation `_return_sold_item` → `POST /inventory/internal/characters/{id}/items` with `X-Internal-Token` (:2719-2734); a failed compensation loses the item (documented residual risk).
  2. **Direct SQL on the shared `character_inventory` table inside the same DB transaction as the ledger posting** — precedent in locations-service `houses.py:1214-1240 _take_materials` (only plain stacks: `enhancement_points_spent = 0`, `socketed_gems IS NULL`, `current_durability IS NULL`; DELETE row or `quantity - :q`) and :2005-2030. This makes «ore out + marks in + stock up» atomic, which matches «без частичной потери руды». It bypasses inventory-service (table owned by it) — architectural decision.
- Item → group: `econ_core.auto_item_group` (:378-401): `item_type == 'resource'` + `resource_subcategory in {'ore','ingot'}` → `ore_metal` (:364); admin overrides in `econ_item_groups` (`CS/models.py:692-703`) via `effective_item_group` (:752-772); one-shot SQL `sql_item_market` (:975-982) returns type/subcategory/is_food/rarity/price/name/image + override. Admin UI «Предметы» tab edits overrides (`EconomyItemGroups.tsx`).
- Mint item list with per-item rate: no existing table. Natural shape: new character-service table keyed by `item_id` (no FK to `items`, same as `econ_item_groups`), with `marks_per_item` (+ enabled flag). Adding ore to the capital stock in region units would use `units_per_item(item_base_price(items.price, group base), group base)`.

### 6. Frontend admin economy UI and player card

- Page `frontend/app-chaldea/src/components/Admin/EconomyPage/EconomyPage.tsx` (tabs `TAB_LABEL` :29-43, intro lines `TAB_INTRO` :49+, tab ids in `guideSections.ts`). Tabs: `EconomySettings.tsx` («Настройки» — currency forms + country tax from `econ_settings`, 196 lines), `EconomyTick.tsx` («Пересчёт» — sim params from `econ_sim_settings.params` with param defs incl. min/max/def, 921 lines), `EconomyBanks.tsx`, `EconomyEvents.tsx`, `EconomyGuide.tsx` («Как настроить», 1280 lines), `EconomyRegions.tsx` + `RegionEconomyEditor.tsx` + `RegionBankPanel.tsx` (per-region panel precedent), `EconomyJournal.tsx` (uses `opTypeLabel`), hints `paramHints.ts` (`SIM_PARAM_HINTS` keyed by `keyof EconSimParams`) + `ParamHint.tsx`, labels `economyLabels.ts` (`OP_TYPE_LABELS` :5-41). API `api/economyAdmin.ts`, types `types/economy.ts` (`EconSimParams` :412).
- Backend param bounds: `CS/schemas.py:1885 ECON_SIM_PARAM_BOUNDS` + optional-field body (:2246); new numeric params in `econ_sim.SimParams` (`econ_sim.py:57-150`) need no migration (JSON, missing keys default — precedent of every FEAT-183/184/186/187 param). The quota amount could be a sim param or a new `econ_settings` column (the «Настройки» tab is `econ_settings`; a column there needs a migration and a change to `econ_core.SQL_SELECT_SETTINGS`/`settings_from_row` — that would touch the byte-copied file again; a sim param or a separate table avoids that).
- Player region card: `frontend/.../components/WorldPage/RegionEconomyCard.tsx` (bank line :123-146, events :154), API/types `api/regionEconomy.ts` (`has_bank` :27/:44). Backend `CS/economy_sim_crud.py:830-851 region_card` returns `has_bank` and `events` in both shapes (hidden / participating) — a `mint` field would follow the same rule.
- No player-facing operation history exists (no endpoint, no UI). «В истории операций — «Чеканка»» can only mean the admin «Журнал» (label in `OP_TYPE_LABELS`) and the response message in the Монетчик modal.

### 7. Alembic and RBAC

- character-service head: **`033_econ_region_events`** (`CS/alembic/versions/033_econ_region_events.py:30-31`, down `032_econ_population_scale`); version table `alembic_version_character`. Next: `034_*` (keep revision id ≤ 32 chars). Raw-SQL DDL style with `_TABLE_OPTS` (`028:40`).
- No other service needs a migration if the capital/mint/quota state lives in character-service tables (Countries/Regions untouched; op types are VARCHAR).
- RBAC: economy permissions `economy:read|emit|adjust|settings` (`user-service/alembic/versions/0032_add_economy_permissions.py:25-28`; moderator gets `read`), tests `user-service/tests/test_rbac_permissions.py:1300-1345`. Existing endpoints: reads `economy:read`, config changes `economy:settings`, money creation buttons `economy:emit` or `require_all_permissions("economy:settings","economy:emit")` (`economy_api.py:247-253, 274, 440`). Mint/quota settings fit the existing set; no new permission needed unless the user wants one.

### 8. Tests and CI

- character-service economy tests (`CS/tests/`): `test_econ_tick.py`, `test_econ_tick_banks.py`, `test_econ_tick_events.py`, `test_econ_tick_merchants.py` (tick harness with SQLite session factory), `test_econ_bank_api.py` (player NPC flow: ownership, dead NPC, location, gate mock, idempotency), `test_econ_banks_admin_api.py`, `test_econ_regions_api.py`, `test_econ_sim.py`, `test_econ_core.py`, `test_econ_contract.py` + `econ_contract_cases.py`, `test_econ_ledger_helper.py`, `test_economy_api_sanity.py`, `test_econ_population_scale.py`.
- Contract runners in inventory/locations/dungeon `tests/test_econ_contract.py` run the shared cases.
- CI: `econ-contract-copies` job (sha256), per-service pytest matrix, deploy depends on both. Memory note: dungeon tests have a 30 s per-test timeout in CI.

### 9. Risks / open technical questions for the Architect

- **R1 «Game month» is undefined** → blocking for the quota and the mint limit; needs a user decision (see Questions).
- **R2 Auto-mint likely idle:** capital template produces ore_metal at 0.8 and consumes it as input → stock usually below norm, so «only surplus above norm» yields ~0. Not a bug, but the user should know (only player ore and caravans will feed the mint).
- **R3 Grant lag:** the grant plan is frozen at claim (`econ_tick.py:570-574`), so marks minted into a country treasury in run N are granted to regions from run N+1, 25 % per step (`country_grant_share`).
- **R4 Inventory atomicity:** the HTTP delete + compensation pattern can lose ore on a failed credit; direct `character_inventory` SQL in one transaction (houses.py precedent) is atomic but crosses table ownership. Architect decision.
- **R5 Lock order for the player mint flow:** must take `econ_regions(capital) → econ_region_goods(capital) → [new monthly-counter row] → characters → econ_accounts`, and the tick step must lock the same new counter row at the same position, or deadlocks with the region transaction are possible. The shared monthly limit (court + players) needs a lockable counter row (per country per period) — the check-and-increment must be under `FOR UPDATE`.
- **R6 Calendar config edits** (`PUT /locations/game-time/admin`) can move the period index backwards/forwards; keys/last-issued markers must handle it.
- **R7 econ_core copy churn:** every new constant/SQL in `econ_core.py` forces a 4-way byte copy; keep mint-specific SQL and math in character-service-only modules, put only the op-type constants into `econ_core`.
- **R8 Battle-pass gold missions** will count player minting as gold earned unless the new op type is added to `battle-pass-service/app/crud.py:408 LEDGER_EXCLUDED_OP_TYPES` — product decision (probably counting it is fine).
- **R9 Multiple capitals / none:** with template-based default, a country with 0 or ≥2 `capital` regions has no mint until an admin picks one; the capital row must be validated against `Regions.country_id` at use time (a region can be moved to another country or deleted — purge like `purge_orphans`).
- **R10 Region units vs items:** player ore adds `units_per_item` region units (value-based); an item with `price` 0 falls back to the group base (`item_base_price`). An ingot/ore whose group was overridden away from `ore_metal` in `econ_item_groups` should probably not be accepted into the ore stock — validate the effective group.

### Questions that need the user's decision (via PM)

1. **What is a «game month»?** The calendar has only years (196 real days), 8 segments (4 seasons × 39 days, 4 festivals × 10 days) and 3-day weeks — no months. Options: (a) one segment = one «month» (8 per year, unequal 39/10 days); (b) season + following festival = one period of 49 days (4 per year — matches `event_season_days = 49` already used by region events); (c) a fixed 196/12 ≈ 16.3-day month (12 per year, new concept, needs a name for UI «лимит до …»); (d) something else.
2. Should a player's minting count as «earned gold» for battle-pass gold missions?
3. (Info, not blocking) Auto-mint from capital stock will usually take nothing because capitals are ore-deficient by template — is that acceptable, or should the norm threshold be a configurable share (e.g. mint above 50 % of norm)?

---

## 3. Architecture Decision (filled by Architect — in English)

All backend work is in **character-service** (sync SQLAlchemy). Other backend services only get the byte copy of
`econ_core.py` + `tests/econ_contract_cases.py` and one battle-pass test. No locations-/inventory-service migration.
CS = `services/character-service/app`.

### 3.1 Module layout

| Module | Kind | Content |
|---|---|---|
| `CS/econ_core.py` (canonical, byte-copied ×3) | constants only | 3 new op types (3.2). **Nothing else** goes into econ_core (R7). |
| `CS/econ_mint.py` (new) | pure, no DB | season period math (3.3), court mint amount (3.6), quota split (3.7), item → region units. |
| `CS/economy_mint_crud.py` (new) | DB | capital resolution (3.4), season counter rows, Монетчик gate + player flow (3.8), admin reads/writes (3.9), region-card flag. Pattern: `economy_bank_crud.py`. |
| `CS/econ_tick.py` | DB | `_quota_pass` (before the region loop) and `_mint_pass` (after the region loop, before banks); `RunSummary` counters; docstring lock order. |
| `CS/economy_api.py` | router | player + admin endpoints (3.10); sim PUT money-param guard. |
| `CS/econ_sim.py` | params | new `SimParams` fields (3.5). |
| `CS/models.py`, `CS/schemas.py` | ORM / Pydantic v1 | 3 new tables, request/response schemas, `ECON_SIM_PARAM_BOUNDS` entries. |
| `CS/alembic/versions/034_econ_mint.py` | migration | revision id `034_econ_mint` (12 chars), down `033_econ_region_events`. |

### 3.2 Ledger: new op types (econ_core, copied byte-for-byte to inventory/locations/dungeon)

```python
OP_MINT_COURT = "mint_court"        # FEAT-191: court mint in the tick: emission -> country treasury
OP_MINT_PLAYER = "mint_player"      # FEAT-191: a player hands ore to a Монетчик: emission -> character
OP_SEASON_QUOTA = "season_quota"    # FEAT-191: once per game season: emission -> participating region treasuries
MINT_OP_TYPES = frozenset({OP_MINT_COURT, OP_MINT_PLAYER, OP_SEASON_QUOTA})
```
- Added to `OP_TYPES` and to `SOURCE_OP_TYPES` (they touch `emission`). **Not** in `COMMENT_REQUIRED_OP_TYPES`.
- All three use leg type `main`, `apply_tax=False` (emission is not a tax source anyway; explicit like other emission
  callers).
- `econ_operations.op_type` is VARCHAR(50) → no ledger migration.
- `tests/econ_contract_cases.py` (canonical, byte-copied): new cases — each of the 3 ops passes `validate_operation`
  with an `emission -> X` leg and no comment; `mint_player` with a `character -> X` leg only (no source) also passes
  (generic rule); a non-source op (e.g. `trade`) with an emission leg still fails. Each service's own
  `tests/test_econ_contract.py` gets asserts `"mint_court" in OP_TYPES`, `MINT_OP_TYPES <= SOURCE_OP_TYPES`,
  `not (MINT_OP_TYPES & COMMENT_REQUIRED_OP_TYPES)` (precedent: FEAT-187 `REGION_EVENT_OP_TYPE_NAME`).
- `scripts/check_econ_copies.sh` must pass (sha256 of the 4 copies of both files).

**Battle pass (user decision: player minting counts as earned gold).** `battle-pass-service/app/crud.py`
`_ledger_gold_sum` sums every posting INTO a `character` account since season start, except
`LEDGER_EXCLUDED_OP_TYPES`. `mint_player` posts `emission -> character`, so it is counted automatically **as long as
it is not added to that tuple** — no code change in battle-pass-service; only a one-line comment next to the tuple
(«FEAT-191: mint_player is deliberately NOT excluded — minting counts as earned gold») and a regression test.
`mint_court` / `season_quota` never touch a character account → never counted.

### 3.3 «Season» period (game calendar, 49 real days, 4 per year)

The calendar config `game_time_config(epoch, offset_days)` lives in the shared DB (owned by locations-service).
character-service **reads it directly** with one read-only SQL (`SELECT epoch, offset_days FROM game_time_config
ORDER BY id LIMIT 1`) — like the tick already joins `Regions`/`Countries`. Reason: the quota and the mint limit are
money-critical and must not depend on an HTTP call being up (the events pass tolerates a missing segment; we cannot).

`econ_mint.py` mirrors the calendar layout (a local copy of the `YEAR_SEGMENTS` list of
`locations-service/app/crud.py`, with a comment pointing to it and to `frontend/src/utils/gameTime.ts`):
- `elapsed_days = max(0, floor((now - epoch).total_seconds() / 86400) + offset_days)` — same formula as
  `compute_game_time`.
- Periods are consecutive *(season + following festival)* pairs of `YEAR_SEGMENTS`; `PERIOD_DAYS` is **derived**
  from the list (39 + 10 = 49) and a module-level assert checks `4 * PERIOD_DAYS == sum(real_days) == 196`.
- `SeasonPeriod(index, year, season, starts_at, ends_at)`: `index = elapsed_days // PERIOD_DAYS` (absolute, monotonic
  across years), `year = index // 4 + 1` (same year as the calendar — the lore offset is in `offset_days`, never
  hardcoded), `season = ("spring","summer","autumn","winter")[index % 4]`,
  `starts_at = epoch + timedelta(days=index * PERIOD_DAYS - offset_days)`, `ends_at = starts_at + 49 days` (naive UTC).
- `current_period(session, now) -> Optional[SeasonPeriod]` in `economy_mint_crud.py`; `None` when the config row is
  missing → the quota is skipped (warning) and the mint (court and players) is closed («Календарь мира недоступен»).
- **Calendar edits (R6):** keys use the absolute `index`. Moving the calendar back into an already used index reuses
  the existing counter row and the quota key (no second quota); moving forward skips periods (missed periods are never
  caught up — same as missed tick slots). Accepted edge, documented.
- UI wording: «сезон» (e.g. «Весна, 3-й год · до 12.11.2026»). Backend returns `season` code + `year` + dates; the
  frontend uses `SEGMENT_LABELS` from `utils/gameTime.ts`.

### 3.4 Capital of a country

New table `econ_mints` (one row per country, created lazily by the admin PUT; a country without a row = all
defaults). **Effective capital** (`capital_of(session, country_id) -> CapitalInfo`):
1. `econ_mints.capital_region_id` is set **and** `Regions.id` exists with `Regions.country_id = country_id` → that
   region (`source = "manual"`). A stale override (region deleted / moved to another country) is ignored and reported
   as a warning in the admin view.
2. else regions of the country whose `econ_regions.template_code = 'capital'`: exactly one → it (`source = "auto"`);
   0 or ≥ 2 → no capital (`source = "none"`, admin view lists the candidates).

**The mint works** in a country when: capital exists, `econ_mints.is_enabled` (default true when no row), the capital
participates (`econ_regions.template_code IS NOT NULL AND population > 0`), it has an `econ_region_goods` row
`ore_metal`, the effective season limit > 0 and the calendar is available. Otherwise both court and Монетчик are idle
(explicit reason string in the views).

### 3.5 Settings (no migration for numbers — sim params JSON)

New `econ_sim.SimParams` fields (missing keys fall back to defaults; bounds in `schemas.ECON_SIM_PARAM_BOUNDS`,
optional fields in the sim PUT body):

| Param | Type | Default | Bounds | Meaning |
|---|---|---|---|---|
| `quota_season_amount` | int | 0 | 0 … 1 000 000 000 | marks issued once per season into participating region treasuries (0 = off). Shown in «Настройки» tab. |
| `mint_season_limit` | int | 0 | 0 … 1 000 000 000 | default per-country season limit (court + players); a country row may override it. 0 = closed. |
| `mint_court_marks_per_unit` | float | 8.0 | 0.01 … 10 000 | marks per region unit of `ore_metal` taken by the court (ore_metal base price is 10). |
| `mint_court_threshold_pct` | float | 100.0 | 0 … 1000 | court takes ore only above this % of the capital's `norm_stock`. |

`ECON_SIM_INT_PARAMS` gets the two int ones. **Money-param guard:** `PUT /admin/economy/sim` keeps
`economy:settings`, but if the body changes `quota_season_amount`, `mint_season_limit` or `mint_court_marks_per_unit`
(value differs from stored) the caller must also hold `economy:emit` → 403 «Нужно право на эмиссию». Defaults 0 mean
the feature is dormant on deploy until the admin sets amounts (see Questions for PM, Q1).

Per-country and per-item settings live in tables (3.11). No new RBAC permission — `economy:read` for reads,
`economy:settings` + `economy:emit` (`require_all_permissions`) for writes that authorise new money (country limit,
items/rates), `economy:settings` for capital choice / enable flag (same endpoint → `require_all_permissions` for the
whole PUT; simpler and admins hold both).

### 3.6 Court mint (tick)

`_mint_pass(session_factory, run_id, summary, params, now)` runs **after the region loop, before `_prepare_banks`**,
one transaction per country, best effort (a failure rolls back that country, increments `summary.mint_failures`,
appends `MINT_ERROR_PREFIX = "чеканка — ошибка в странах: "` to the run error; other countries go on). Runs in
scheduled **and** manual runs (stock-based, the posting key is per run).

Per country with a working mint (3.4):
1. `ensure_season_row(country_id, period.index)` — own short transaction (`INSERT` the zero row, `IntegrityError` →
   rollback = already exists). Never inside a locking transaction (avoids MySQL insert-intention/gap-lock deadlocks).
2. Main transaction, lock order (3.12): `econ_regions(capital)` FOR UPDATE → `econ_region_goods(capital,'ore_metal')`
   FOR UPDATE → `econ_mint_seasons(country, index)` FOR UPDATE.
3. Re-check the capital still participates (else skip).
4. Pure `econ_mint.court_mint(stock, norm, threshold_pct, marks_per_unit, remaining)`:
   `excess = max(0, stock - norm * threshold_pct / 100)`; `marks = min(floor(excess * rate), remaining)`;
   `units = min(excess, ceil_3(marks / rate))` (3 decimals, never more than the excess); `marks <= 0` → nothing.
   `remaining = limit - minted_court - minted_players` (≥ 0).
5. `goods.stock -= units`; `season.minted_court += marks`, `season.ore_units_court += units`;
   `post_operation(op_type=mint_court, legs=[emission -> country(country_id), marks], apply_tax=False,
   region_id=capital, idempotency_key=f"mint_court:{run_id}:c{country_id}",
   metadata={run_id, period_index, units, rate, stock_before, norm})` → COMMIT. `DuplicateOperation` → rollback
   (another runner did it).
6. Marks reach regions through the normal country grants from the **next** run (grant plan frozen at claim — R3,
   documented in the admin guide).

`RunSummary` gets `mint_court_ops`, `mint_court_marks`, `mint_failures`; `quota_amount` (3.7). Logged in the final
run log line.

### 3.7 Season quota (tick)

`_quota_pass(session_factory, run_id, summary, params, now)` runs **after the claim / merchants / events
preparation, right before the region loop** (so this run's region steps already see the money), own transaction,
best effort (failure → logged, `QUOTA_ERROR_PREFIX = "квота — ошибка"` in the run error, retried by the next run).
1. `period = current_period(...)`; skip if `None` or `params.quota_season_amount <= 0`.
2. Cheap pre-check: `SELECT id FROM econ_operations WHERE idempotency_key = :k` → exists → skip.
3. Regions = `participating_regions(session)` (same list the grant plan uses). None → skip (warning).
4. Pure `econ_mint.split_quota(amount, {region_id: population})` — largest-remainder split: floors, then the leftover
   marks go one each to the largest fractional parts (ties → lower region id), so the legs sum to `amount` exactly;
   zero-amount legs are dropped.
5. One operation `season_quota`, legs `emission -> region(rid)`, `apply_tax=False`,
   `idempotency_key=f"season_quota:p{period.index}"`,
   `metadata={period_index, year, season, amount, regions: {rid: amt}, run_id}` → COMMIT. `DuplicateOperation` →
   rollback, skip. The ledger UNIQUE key is the idempotency guarantee (no extra table).
- Quota history for the admin = `econ_operations WHERE op_type = 'season_quota'` (newest first) + metadata.

### 3.8 Player mint at the Монетчик

NPC role **`minter`** (`characters.npc_role`, free string; label «Монетчик»). Gate = banker order (contract of
FEAT-184 3.9, `economy_bank_crud.resolve_banker` is the template):
1 JWT + ownership + player character → 2 NPC exists, `is_npc`, `npc_role == "minter"` (404), `npc_status != "dead"`
(409) → 3 activity lock (POST only) → 4 same `current_location_id` → 5 FEAT-145 gate (POST only,
`locations_client.check_npc_gate`, fail-closed, awaited with **no open DB transaction**) → 6 NPC location → region
(`econ_ledger.resolve_location`) → that region must be the **effective capital** of its country (else 409
`MSG_NO_MINT`) → mint working (else 409 `MSG_MINT_CLOSED` with the reason).

**Flow `mint(db, ctx, body)`** (all in one DB transaction, the router commits; "all or nothing"):
1. Before the transaction: `ensure_season_row` (own short commit, as in 3.6).
2. Lock `econ_regions(capital)` → `econ_region_goods(capital,'ore_metal')` → `econ_mint_seasons(country, index)`.
3. `_check_duplicate(key)` with `key = f"mint:{character_id}:{request_id}"` → 409 `MSG_DUPLICATE`.
4. Item: `econ_mint_items` row enabled, and the item's **effective group** (`econ_core.effective_item_group` via
   `sql_item_market`) is `ore_metal` (R10) → else 400 `MSG_ITEM_NOT_ACCEPTED`.
5. `marks = marks_per_item * quantity`; `remaining = limit - minted_court - minted_players`;
   `accepted = min(quantity, floor(remaining / marks_per_item))`; `accepted == 0` → 409 `MSG_LIMIT`; otherwise
   **partial acceptance** (user decision 2026-11-01): only `accepted` pieces are taken and paid for, the rest of the
   ore stays with the player; `marks = marks_per_item * accepted`.
6. Take ore (`accepted` pieces; the «not enough» check is against the REQUESTED `quantity`) — direct SQL on `character_inventory` (precedent `locations-service/app/houses.py _take_materials`), now
   **with `FOR UPDATE`**: `SELECT id, quantity ... WHERE character_id=:c AND item_id=:i AND
   COALESCE(enhancement_points_spent,0)=0 AND socketed_gems IS NULL AND current_durability IS NULL ORDER BY id
   FOR UPDATE`; short → 400 `MSG_NOT_ENOUGH`; then `DELETE` / `UPDATE quantity = quantity - :q` per row. (Only plain
   stacks; equipped items live in other tables and are never touched.)
7. `goods.stock += accepted * econ_core.units_per_item(econ_core.item_base_price(items.price, group_base),
   group_base)` (ore_metal group base from `econ_goods_groups`); `season.minted_players += marks`,
   `season.ore_units_players += units`.
8. `post_operation(op_type=mint_player, legs=[emission -> character(character_id), marks], apply_tax=False,
   location_id, region_id=capital, actor_user_id, idempotency_key=key,
   metadata={item_id, item_name, quantity (= accepted), requested, marks_per_item, period_index, npc_id, units})` —
   always the **last** DB step (locks `characters` then `econ_accounts`). `DuplicateOperation` → 409 `MSG_DUPLICATE`;
   the router rolls back so the ore is never lost.
- Response message: `"Отчеканено {marks fmt}: {item_name} × {accepted}"` (currency forms via the bank `_fmt` helper);
  a partial success answers `MSG_PARTIAL` (below).
- Cross-ownership note: character-service writes `character_inventory` (owned by inventory-service) — same accepted
  pattern as locations-service houses; documented in `docs/services/character-service.md` and
  `docs/services/inventory-service.md` («другие писатели таблицы»).

Russian texts (constants in `economy_mint_crud.py`, tests assert them):
`MSG_MINTER_NOT_FOUND = "Монетчик не найден"` (404), `MSG_MINTER_DEAD = "Монетчик больше не принимает посетителей"`
(409), `MSG_NOT_PLAYER = "Монетным двором пользуются только персонажи игроков"` (403), `MSG_NOT_OWNER` (bank text,
403), `MSG_WRONG_LOCATION = "Подойдите к монетчику — он в другой локации"` (400), `MSG_GATE_CLOSED` (bank text, 403),
`MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к монетчику, попробуйте позже"` (503),
`MSG_NO_MINT = "Монетный двор есть только в столице страны — этот монетчик ему не служит"` (409),
`MSG_MINT_CLOSED = "Монетный двор закрыт: {reason}"` (409; reasons: «у страны не выбрана столица», «столица не
участвует в экономике», «двор выключен», «лимит не задан», «календарь мира недоступен»),
`MSG_LIMIT = "Монетный двор исчерпал лимит до {date}"` (409, not a single piece fits),
`MSG_PARTIAL = "Принято {accepted} из {requested} шт. — лимит сезона исчерпан, остальная руда осталась у вас.
Отчеканено {marks}: {name} × {accepted}"` (200, partial success), `MSG_ITEM_NOT_ACCEPTED = "Монетный двор не принимает этот предмет"`
(400), `MSG_NOT_ENOUGH = "Не хватает: {name} — нужно {need}, есть {have} (принимаются только обычные стопки)"` (400),
`MSG_DUPLICATE = "Операция уже выполнена"` (409), `MSG_RETRY` (bank text, 409 on IntegrityError). `{date}` =
`ends_at` as `dd.mm.yyyy`.

**Change 2026-11-01 (after review #1, user decision — already folded into steps 5–8 and the texts above; the
original «reject the whole request» / `MSG_LIMIT_PARTIAL` design is gone):** partial acceptance. `accepted = min(quantity, floor(remaining / marks_per_item))`; `accepted == 0` → 409 `MSG_LIMIT` as
before. The «not enough ore» check stays against the REQUESTED quantity, but only `accepted` pieces are taken; stock,
counter and the `mint_player` posting use `accepted`. Same transaction, same lock order, same idempotency key.
`MintActionOut` gains `requested: int` and `partial: bool` (`quantity` / `marks` = accepted / paid); a partial success
answers `MSG_PARTIAL = "Принято {accepted} из {requested} шт. — лимит сезона исчерпан, остальная руда осталась у вас.
Отчеканено {marks}: {name} × {accepted}"`. `MSG_LIMIT_PARTIAL` removed. Frontend: the quantity input is capped only by
the bag and the 10 000 request cap; a hint «Двор примет только N шт. …» appears when the quantity exceeds
`max_by_limit`, the «Получите» preview counts the accepted pieces, the server message of a partial success stays shown
in the modal. Also review note 1: the admin country card returns `remaining = 0` when the mint is closed (player rule).

### 3.9 Region card

`economy_sim_crud.region_card` gets `"has_mint": bool` in **both** shapes (like `has_bank`): true when the region is
the effective capital of its country and the mint works (3.4). `api/regionEconomy.ts` type gets `has_mint`.

### 3.10 API contracts (router prefix `/characters`, all in `economy_api.py`)

Player (JWT `get_current_user_via_http`):

#### `GET /characters/economy/mint/npc/{npc_id}?character_id=` → `MintView` (steps 1, 2, 4, 6; no gate, no lock)
```json
{
  "npc_id": 1, "npc_name": "str", "country_id": 1, "country_name": "str",
  "region_id": 1, "region_name": "str",
  "working": true, "closed_reason": null,
  "period": {"index": 12, "year": 4, "season": "spring", "starts_at": "iso", "ends_at": "iso"},
  "limit": 50000, "minted_court": 1200, "minted_players": 300, "remaining": 48500,
  "items": [{"item_id": 5, "name": "str", "image": "str|null", "marks_per_item": 12, "have": 7,
             "max_by_limit": 4041}],
  "wallet": 1234
}
```
`have` = sum of plain stacks; `max_by_limit = floor(remaining / marks_per_item)`. Only enabled items whose effective
group is `ore_metal` are listed.

#### `POST /characters/economy/mint/npc/{npc_id}/mint` (async handler; precheck in threadpool → gate → commit in threadpool, exactly like `_bank_action`)
Request `MintIn`: `{"character_id": int ≥1, "item_id": int ≥1, "quantity": int 1…10000, "request_id": str}` —
`request_id` uses the bank `_BANK_REQ_ID` constrained type (required here, not optional).
Response `MintActionOut`: `{"message": "str", "operation_id": int, "marks": int, "quantity": int, "requested": int,
"partial": bool, "wallet": int, "view": MintView}` — `quantity` / `marks` = pieces actually accepted / marks paid,
`requested` = pieces asked for, `partial = quantity < requested` (rest of the ore stays in the bag). Errors per 3.8; `core.EconomyError` → 400 «Операция отклонена»; `SQLAlchemyError` → 500.

Admin:

#### `GET /characters/admin/economy/mint` (`economy:read`) → `MintAdminOut`
```json
{
  "period": {"index": 12, "year": 4, "season": "spring", "starts_at": "iso", "ends_at": "iso"} ,
  "params": {"mint_season_limit": 0, "mint_court_marks_per_unit": 8.0, "mint_court_threshold_pct": 100.0,
             "quota_season_amount": 0},
  "countries": [{
    "country_id": 1, "country_name": "str", "is_enabled": true,
    "capital_region_id": 3, "capital_region_name": "str", "capital_source": "auto|manual|none",
    "capital_override_id": null, "override_stale": false,
    "candidates": [{"region_id": 3, "name": "str", "template_code": "capital"}],
    "working": true, "closed_reason": null,
    "season_limit_override": null, "season_limit": 50000,
    "minted_court": 0, "minted_players": 0, "remaining": 50000,
    "ore_stock": 120.5, "ore_norm": 300.0,
    "minters": [{"npc_id": 9, "name": "str", "npc_status": "alive", "location_name": "str", "in_capital": true}]
  }]
}
```
All countries from `Countries` (LEFT JOIN `econ_mints`); `candidates` = all regions of the country (for the select),
capital-template ones first. `minters` = NPCs with role `minter` whose location is in a region of that country
(query shape of `economy_bank_crud.bankers_by_region`).

#### `PUT /characters/admin/economy/mint/countries/{country_id}` (`economy:settings` + `economy:emit`)
Request `MintCountryIn` (full replace, all keys required, nullable where noted):
`{"capital_region_id": int|null (null = auto), "season_limit": int 0…1e9 | null (null = default param), "is_enabled": bool}`.
Validation: country exists (404 «Страна не найдена»); a set region exists and belongs to the country (400 «Регион
не принадлежит этой стране»). Upsert `econ_mints`, `updated_by`/`updated_at`. Response: the country entry of
`MintAdminOut`.

#### `GET /characters/admin/economy/mint/items` (`economy:read`) → `List[MintItemOut]`
`[{"item_id", "name", "image", "item_type", "resource_subcategory", "effective_group", "marks_per_item",
"is_enabled", "valid"}]` — `valid = effective_group == 'ore_metal'` (invalid rows stay listed with a warning, the
player flow ignores them).

#### `PUT /characters/admin/economy/mint/items/{item_id}` (`economy:settings` + `economy:emit`)
Request `MintItemIn`: `{"marks_per_item": int 1…1 000 000, "is_enabled": bool}`. 404 «Предмет не найден»; 400
«Чеканить можно только руду и металл (группа «Руда и металл»)» when the effective group is not `ore_metal`. Upsert.
Response `MintItemOut`.

#### `DELETE /characters/admin/economy/mint/items/{item_id}` (`economy:settings` + `economy:emit`) → 204; 404 if absent.

#### `GET /characters/admin/economy/mint/quotas?limit=20` (`economy:read`, limit 1…100) → `List[QuotaOut]`
`[{"operation_id", "created_at", "period_index", "year", "season", "amount", "regions": int}]` from
`econ_operations` (`op_type='season_quota'`) newest first, plus nothing else (current period / amount are in
`GET /admin/economy/mint`).

#### `PUT /characters/admin/economy/sim` (existing) — new optional fields of 3.5 + the money-param guard.

#### `GET /characters/economy/regions/{region_id}/card` (existing) — `has_mint` added (additive, backward compatible).

### 3.11 DB changes — migration `034_econ_mint` (character-service, raw-SQL DDL, `_TABLE_OPTS`, re-runnable)

```sql
CREATE TABLE IF NOT EXISTS econ_mints (            -- per-country mint settings; no FK (Countries owned by locations)
  country_id INT NOT NULL PRIMARY KEY,
  capital_region_id INT NULL,                      -- NULL = auto (single 'capital'-template region)
  season_limit BIGINT NULL,                        -- NULL = sim param mint_season_limit
  is_enabled TINYINT(1) NOT NULL DEFAULT 1,
  updated_at DATETIME NULL, updated_by INT NULL
) <_TABLE_OPTS>;

CREATE TABLE IF NOT EXISTS econ_mint_items (       -- ore accepted from players; no FK to items (like econ_item_groups)
  item_id INT NOT NULL PRIMARY KEY,
  marks_per_item INT NOT NULL,
  is_enabled TINYINT(1) NOT NULL DEFAULT 1,
  updated_at DATETIME NULL, updated_by INT NULL
) <_TABLE_OPTS>;

CREATE TABLE IF NOT EXISTS econ_mint_seasons (     -- the lockable shared limit counter (court + players)
  country_id INT NOT NULL,
  period_index INT NOT NULL,
  minted_court BIGINT NOT NULL DEFAULT 0,
  minted_players BIGINT NOT NULL DEFAULT 0,
  ore_units_court DECIMAL(16,3) NOT NULL DEFAULT 0,
  ore_units_players DECIMAL(16,3) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL, updated_at DATETIME NULL,
  PRIMARY KEY (country_id, period_index)
) <_TABLE_OPTS>;
```
No FKs → no FK-index pitfalls. Downgrade: `DROP TABLE IF EXISTS` the three (settings and counters lost; ledger
operations stay). Nothing seeded: capital defaults are computed, items are added by the admin. Counter rows are never
purged (tiny: countries × 4 per year). Orphan `econ_mints` rows of deleted countries are ignored by the views.

### 3.12 Lock order (supersedes FEAT-187 3.6.1 — update `econ_tick.py` docstring and `character-service.md`)

`econ_regions → econ_region_goods → econ_region_events (asc id) → econ_mint_seasons → npc_shop_items (asc id) →
econ_banks (asc region_id) → bank_deposits (asc id) → bank_loans (asc id) → character_inventory (asc id) →
characters (asc id) → econ_accounts (asc id)`.
- Region transaction: unchanged (never touches `econ_mint_seasons` / `character_inventory`).
- Court mint transaction: `econ_regions → econ_region_goods → econ_mint_seasons → econ_accounts`.
- Player mint transaction: `econ_regions → econ_region_goods → econ_mint_seasons → character_inventory → characters
  → econ_accounts`.
- Quota transaction: `econ_accounts` only.
- inventory-service flows lock `character_inventory` before any ledger posting (characters/accounts) — consistent.
- `ensure_season_row` INSERTs are always in their own short transaction, never under other locks.

### 3.13 Security

- Player endpoints: JWT + ownership + player-only + NPC role/alive/location + activity lock + FEAT-145 gate
  (fail-closed). Idempotency by required `request_id` (UNIQUE ledger key) — double click = one posting, the second
  gets 409. Quantity bounded 1…10000; integer overflow impossible (`marks_per_item ≤ 1e6`, BIGINT counters).
  No rate limit beyond nginx defaults — every request is bounded by inventory and the season limit.
- Admin endpoints: `require_permission("economy:read")` for reads; money-authorising writes
  `require_all_permissions("economy:settings","economy:emit")`; sim PUT money-param guard. **No new permission** →
  no user-service migration, no RBAC test change.
- Errors: Russian, no internals (exceptions logged server-side, generic 500 text).
- SQL: parameterised `text()` only.

### 3.14 Frontend

- `src/constants/npc.ts` — role `{ value: 'minter', label: 'Монетчик' }`, icon `'🪙'`-like (pick one not used by
  merchant, e.g. `'⚒️'`).
- `components/pages/LocationPage/NpcProfileModal.tsx` — button «Монетный двор» when `npc.npc_role === 'minter' &&
  isCharacterHere && characterId` (same shape as the bank button) → `MintModal`.
- New `components/pages/LocationPage/MintModal/MintModal.tsx` (+ small parts file if needed): header (country,
  capital, «Сезон: Весна, 4-й год — до dd.mm.yyyy»), limit bar (отчеканено двором / игроками / осталось), closed
  reason banner, list of accepted ore (image, name, «N марок за шт.», «в сумке: X»), quantity input clamped to
  `min(have, 10 000)` (task #12: the season limit no longer caps the input — hint «Двор примет только N шт.» when the
  quantity exceeds `max_by_limit`), preview «получите N» for the accepted pieces, button «Отчеканить». `request_id` = `crypto.randomUUID()` per
  submit attempt (regenerated after a success). All errors shown in Russian (toast + inline), 409 duplicate shown as
  info. Uses `modal-overlay` / `modal-content`, `btn-blue`, `gold-text`, Tailwind only, 360px+.
- New `src/api/mint.ts` (player + admin calls) and types in `src/types/economy.ts` (`MintView`, `MintActionOut`,
  `MintAdminOut`, `MintCountry`, `MintItem`, `QuotaEntry`, new `EconSimParams` fields).
- Admin `components/Admin/EconomyPage/`: new tab **«Монетный двор»** `EconomyMint.tsx` — period header; params card
  (default limit, court rate, court threshold % — via sim PUT); countries table/cards (capital select with
  auto/candidates, limit override, enabled toggle, minted court/players/remaining, ore stock vs norm, minters list,
  warnings for no capital / stale override / no minter); ore items editor (item search like `EconomyItemGroups`,
  rate, enabled, delete, invalid-group warning); quota history list. `EconomySettings.tsx` — card «Квота сезона»
  (`quota_season_amount` via sim PUT, hint text). `EconomyPage.tsx` (`TAB_LABEL`, `TAB_INTRO`), `guideSections.ts`
  + `EconomyGuide.tsx` (section «Монетный двор и квота»: capital rule, court threshold, grant lag of one recount,
  shared limit, minter placement), `paramHints.ts` (4 params), `economyLabels.ts` `OP_TYPE_LABELS`:
  `mint_court: 'Чеканка (двор)'`, `mint_player: 'Чеканка'`, `season_quota: 'Квота сезона'`.
- `components/WorldPage/RegionEconomyCard.tsx` — line «Монетный двор» when `has_mint` (like the bank line).
- Files touched that are `.jsx`/SCSS: none expected (all listed files are `.tsx`/`.ts`). No `React.FC`.

### 3.15 Data flow

```
Player → MintModal → POST /characters/economy/mint/npc/{id}/mint → Nginx → character-service
   ├─ threadpool: precheck (JWT via user-service /users/me, ownership, NPC, lock, location) → rollback
   ├─ HTTP locations-service GET /locations/internal/action-gate (FEAT-145, fail-closed)
   └─ threadpool, ONE transaction in MySQL: ensure counter (own commit) → lock capital region/goods/counter →
      character_inventory DELETE/UPDATE → goods.stock += units → counter += marks →
      econ_operations/econ_postings (emission → character) → COMMIT
battle-pass-service (gold missions) reads econ_postings → mint_player counted as earned.

econ_scheduler (6 h) → run_tick: claim → merchants prep → events pass → _quota_pass (emission → region treasuries,
   once per season key) → region loop → _mint_pass (capital ore surplus → emission → country treasury) → banks → done
   next run: country grants (25 %) carry the minted marks to regions.
```

### 3.16 Risks

- **R2 (user informed):** with threshold 100 % the court is mostly idle in ore-deficient capitals; the admin lowers
  the threshold or players/caravans bring ore.
- Cross-ownership write to `character_inventory` (accepted precedent) — if inventory-service later adds
  derived caches of the bag, the mint flow must call them.
- Reading `game_time_config` directly couples character-service to a locations-service table (read-only, one row).
- Default 0 settings → nothing happens until the admin configures (Q1).

### Questions for PM

1. **(Non-blocking, defaults.)** Defaults are «off» until the admin sets them: `quota_season_amount = 0`,
   `mint_season_limit = 0` (court and Монетчик closed). Court rate default 8 marks per region unit of ore (80 % of
   the ore_metal base price 10). If the user wants concrete starting numbers on prod (quota per season, limit per
   country), the developer can put them as defaults — please give numbers; otherwise the admin sets them in the UI.
2. **(Resolved 2026-11-01.)** When the player's request does not fit the remaining limit — the user chose partial
   acceptance: as many pieces as fit are taken, the rest stays with the player (see the change note in 3.8, task #12).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Ledger op types + copies.** Add `OP_MINT_COURT`, `OP_MINT_PLAYER`, `OP_SEASON_QUOTA`, `MINT_OP_TYPES` to canonical `econ_core.py`, include in `OP_TYPES` and `SOURCE_OP_TYPES` (not comment-required) — 3.2. Add contract cases to canonical `tests/econ_contract_cases.py`. Byte-copy both files to inventory/locations/dungeon. Add the 3 asserts to each service's own `tests/test_econ_contract.py`. Add the FEAT-191 comment next to `LEDGER_EXCLUDED_OP_TYPES` in battle-pass (no tuple change). | Backend Developer | DONE | `services/character-service/app/econ_core.py`, `services/{inventory,locations,dungeon}-service/app/econ_core.py`, `services/*/app/tests/econ_contract_cases.py` (4), `services/{character,inventory,locations,dungeon}-service/app/tests/test_econ_contract.py`, `services/battle-pass-service/app/crud.py` (comment only) | — | `bash scripts/check_econ_copies.sh` passes; `py_compile` passes; existing contract tests green in all 4 services; `test_econ_bank.py` `len(BANK_OP_TYPES)==8` still holds. |
| 2 | **Migration + models + params + pure math.** Migration `034_econ_mint` (3.11) with docstring, re-runnable DDL, downgrade. ORM models `EconMint`, `EconMintItem`, `EconMintSeason`. `SimParams` fields + `ECON_SIM_PARAM_BOUNDS` / `ECON_SIM_INT_PARAMS` / sim PUT body fields (3.5). New pure `econ_mint.py`: calendar mirror + `SeasonPeriod` / `period_of(epoch, offset_days, now)` (3.3), `court_mint(...)` (3.6), `split_quota(...)` largest-remainder (3.7). | Backend Developer | DONE | `CS/alembic/versions/034_econ_mint.py`, `CS/models.py`, `CS/econ_sim.py`, `CS/schemas.py`, `CS/econ_mint.py` (new) | #1 | Revision id ≤32 chars, down = `033_econ_region_events`; `alembic upgrade head` + `downgrade -1` + `upgrade head` work in the character-service container; `py_compile` passes; period math matches `locations-service compute_game_time` (season/year) for sample dates. |
| 3 | **Mint CRUD + tick passes.** `economy_mint_crud.py`: `current_period`, `capital_of`, `mint_status` (working + reason), `ensure_season_row`, locking helpers in the 3.12 order, Монетчик gate (`resolve_minter`, `minter_context`), `build_view`, flow `mint` (3.8, all Russian constants), admin reads/writes (3.10), `has_mint_for_region`. `econ_tick.py`: `_quota_pass` before the region loop, `_mint_pass` after it and before banks (3.6/3.7), `RunSummary` counters, error prefixes, final log line, docstring lock order (3.12). `economy_sim_crud.region_card`: `has_mint` in both shapes. | Backend Developer | DONE | `CS/economy_mint_crud.py` (new), `CS/econ_tick.py`, `CS/economy_sim_crud.py` | #2 | `py_compile` passes; manual tick in the dev container with quota > 0 posts one `season_quota` op and a second manual run posts none; court mint posts `mint_court` only above the threshold and never above the limit; existing tick tests stay green. |
| 4 | **Router + schemas.** Endpoints of 3.10: player GET view / POST mint (async, `_bank_action`-style precheck → gate → commit; error mapping), admin GET mint, PUT country, GET/PUT/DELETE items, GET quotas; money-param guard in `PUT /admin/economy/sim`. Pydantic v1 schemas `MintIn` (required `request_id`), `MintView`, `MintActionOut`, `MintAdminOut`, `MintCountryOut`, `MintCountryIn`, `MintItemIn`, `MintItemOut`, `QuotaOut`, `SeasonPeriodOut`; region card schema/dict gets `has_mint`. | Backend Developer | DONE | `CS/economy_api.py`, `CS/schemas.py` | #3 | `py_compile`; endpoints visible in `/docs`; curl in dev: admin config → player mints ore → balance + inventory + stock + counter change in one go; double POST with same `request_id` → one posting, 409 on the second. |
| 5 | **Docs.** `docs/services/character-service.md`: mint/quota section (tables, endpoints, op types, season period, lock order 3.12, cross-table write to `character_inventory`, read of `game_time_config`). `docs/services/inventory-service.md`: character-service as another writer of `character_inventory`. `docs/services/battle-pass-service.md` (or its gold-missions part): `mint_player` counts as earned. `docs/ARCHITECTURE.md` if it lists economy tables. | Backend Developer | DONE | `docs/services/character-service.md`, `docs/services/inventory-service.md`, `docs/services/battle-pass-service.md`, `docs/ARCHITECTURE.md` | #4 | Docs match the implemented contracts. |
| 6 | **Frontend: player side.** NPC role `minter` (label «Монетчик», icon); «Монетный двор» button in `NpcProfileModal`; new `MintModal` (3.14) with clamped quantity, preview, `request_id`, visible Russian errors; `api/mint.ts`, types; `RegionEconomyCard` «Монетный двор» line + `has_mint` type. | Frontend Developer | DONE | `src/constants/npc.ts`, `src/components/pages/LocationPage/NpcProfileModal.tsx`, `src/components/pages/LocationPage/MintModal/MintModal.tsx` (new), `src/api/mint.ts` (new), `src/types/economy.ts`, `src/api/regionEconomy.ts`, `src/components/WorldPage/RegionEconomyCard.tsx` | #4 (contract only — can start from 3.10 in parallel with #3/#4) | `npx tsc --noEmit` and `npm run build` pass (in container); Tailwind + design-system classes, no `React.FC`, works at 360px; live: a character at a minter in the capital mints ore, wallet updates, errors show in Russian. |
| 7 | **Frontend: admin side.** Tab «Монетный двор» `EconomyMint.tsx` (period, params card, countries, ore items editor, quota history); «Квота сезона» card in `EconomySettings.tsx`; `EconomyPage.tsx` tab label/intro; guide section; `paramHints.ts`; `OP_TYPE_LABELS` for the 3 ops; admin API calls in `api/mint.ts` / `api/economyAdmin.ts`; `EconSimParams` fields. UI wording «сезон». | Frontend Developer | DONE | `src/components/Admin/EconomyPage/EconomyMint.tsx` (new), `EconomySettings.tsx`, `EconomyPage.tsx`, `guideSections.ts`, `EconomyGuide.tsx`, `paramHints.ts`, `economyLabels.ts`, `src/api/mint.ts`, `src/api/economyAdmin.ts`, `src/types/economy.ts` | #4 (contract), #6 (shared api/types file) | `tsc` + `build` pass; admin can pick a capital, set limit, add/remove ore with a rate, set quota and threshold; 403 / 400 errors visible in Russian; mobile layout OK. |
| 8 | **QA: pure math + contract + battle-pass.** `test_econ_mint.py`: `period_of` (boundaries day 48/49, year rollover at 196, offset_days, negative elapsed clamp, ends_at), parity with locations `compute_game_time` season names, `court_mint` (below/at/above threshold, threshold 0/50/100, rate rounding, units never > excess, remaining cap, zero cases), `split_quota` (sum exact, ties, zero population dropped). Contract cases run in all 4 services. Battle-pass `test_gold_missions.py`: a `mint_player` posting into a character account counts as earned; `mint_court`/`season_quota` do not touch characters. | QA Test | DONE | `CS/tests/test_econ_mint.py` (new), `services/battle-pass-service/app/tests/test_gold_missions.py` | #1, #2 | pytest green in character-, inventory-, locations-, dungeon-, battle-pass-service. |
| 9 | **QA: tick passes.** `test_econ_tick_mint.py` (tick harness of `test_econ_tick*.py`, SQLite; add `game_time_config` + `econ_mint*` tables to the fixtures): quota issued once per season (second run, manual run, resumed run → no second op), split by population, only participating regions, amount 0 / no calendar → skipped; quota in a new season issued again; court mint: capital auto (single template) / manual override / none / 2 candidates / stale override; threshold respected; stock decreased by `units`; counter incremented; shared limit with players respected; disabled country skipped; duplicate key on re-run; a failing country does not stop others; `RunSummary` counters. | QA Test | DONE | `CS/tests/test_econ_tick_mint.py` (new), `CS/tests/conftest.py` (if fixtures needed) | #3 | pytest green; existing `test_econ_tick*.py` still green. |
| 10 | **QA: player + admin API.** `test_econ_mint_api.py` (pattern `test_econ_bank_api.py`): gate order (ownership 403, NPC not minter 404, dead 409, activity lock 409, wrong location 400, gate closed 403 / unavailable 503, minter outside the capital 409, mint closed reasons 409); success: inventory rows removed/decremented (multi-stack), stock += units, counter += marks, `mint_player` posting emission→character, wallet updated; atomicity: posting failure → ore not removed; not enough ore 400; non-plain stacks ignored; item disabled / wrong effective group 400; limit exhausted 409; does not fit → 409 with N and nothing taken; idempotency (same `request_id` twice → one op, 409); security (SQL-injection-like `request_id` rejected by validation, other user's character 403, unauthenticated 401). Admin: permissions (read vs settings+emit, sim money-param guard 403 without `economy:emit`), PUT country validation (foreign region 400, unknown country 404), items upsert/delete/invalid group 400, quotas list; region card `has_mint` both shapes. | QA Test | DONE | `CS/tests/test_econ_mint_api.py` (new), `CS/tests/test_econ_mint_admin_api.py` (new) | #4 | pytest green in character-service (full suite in container). |
| 11 | **Review.** Full review: contracts vs 3.10, lock order 3.12, atomicity of the player flow, idempotency (quota per season, court per run, player per request), econ copies (`check_econ_copies.sh`), battle-pass behaviour, migration up/down, frontend rules (Tailwind, TS, no `React.FC`, mobile, Russian errors, design system), docs. Live: admin configures capital/limit/ore/quota in UI, manual tick issues the quota once, player mints at a Монетчик in the capital (Chrome on localhost), journal shows «Чеканка» / «Квота сезона». | Reviewer | DONE | all | #1–#10 | All automated checks (py_compile, pytest of 5 services, tsc, build, copies script) + live verification pass; zero console errors. |
| 12 | **Partial acceptance (user decision after review #1) + review note 1.** Backend flow/schema (`requested`, `partial`, `MSG_PARTIAL`), admin `remaining = 0` for a closed mint, MintModal input/hint/preview/partial message, tests (partial across stacks, counters/stock/wallet by accepted only, ore stays, idempotent retry, 0-fit 409, admin remaining), docs. | Backend + Frontend Developer | DONE | `CS/economy_mint_crud.py`, `CS/schemas.py`, `CS/tests/test_econ_mint_api.py`, `CS/tests/test_econ_mint_admin_api.py`, `src/components/pages/LocationPage/MintModal/MintModal.tsx`, `src/types/economy.ts`, `docs/services/character-service.md` | #11 | py_compile; full character-service pytest; tsc + build in container. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-01 — **PASS**

Scope: all uncommitted FEAT-191 changes (character-service econ_core/econ_mint/economy_mint_crud/econ_tick/econ_sim/
economy_api/economy_sim_crud/models/schemas, migration 034, 3 econ_core copies + contract cases, battle-pass comment +
tests, frontend player + admin, docs). The bundled inventory-service equip level check was glanced at only (separate,
already verified): reads `characters.level` without locks, no lock-order impact.

#### Spec conformance (section 1)
- Period = season + festival, 49 days, absolute index; UI says «сезон» everywhere (admin tab, settings card, modal).
  Live: index 7148 → «Весна, 1788-й год — до 10.11.2026», consistent with `compute_game_time` (day 40 of the year =
  Beltane, the festival after spring). Year not hardcoded.
- Court threshold is a setting (`mint_court_threshold_pct`, default 100). Shared country season limit (court + players).
- `mint_player` is not in battle-pass `LEDGER_EXCLUDED_OP_TYPES` → counts as earned gold (comment + 5 tests).
- Atomic ore removal: `_take_ore` (FOR UPDATE, plain stacks) + stock + counter + posting in one transaction; the router
  rolls back on any error. Live: the not-enough / limit-partial / bad-item paths left inventory untouched.
- Limit overflow → whole request refused with «примет не больше N шт.» (architect choice, UI clamps).
- Admin emission kept as is.

#### Ledger
- 3 op types in `OP_TYPES` + `SOURCE_OP_TYPES`, not comment-required; all `apply_tax=False`; each op is
  `emission -> X` only, so the world sum stays 0.
- Idempotency: quota `season_quota:p<index>` (pre-check + UNIQUE key), court `mint_court:<run>:c<country>`, player
  `mint:<character>:<request_id>` (request_id regex-constrained, required). Live: same request_id twice → 200 then 409
  «Операция уже выполнена», one posting.
- Lock order 3.12 respected: court `econ_regions → econ_region_goods → econ_mint_seasons → econ_accounts`; player
  `… → econ_mint_seasons → character_inventory → characters → econ_accounts`; `ensure_season_row` in its own short
  transaction; region transaction untouched. No flow found that locks `characters` before `character_inventory` or
  `econ_region_goods` after `character_inventory` (inventory-/locations-service checked) → no deadlock cycle.
  The duplicate pre-check reads a snapshot taken before the lock wait, but the UNIQUE key on the posting is the real
  guard (second request ends in 400 not-enough or 409 duplicate, never a second posting) — acceptable.

#### Migration 034
- Revision id `034_econ_mint` (12 chars), down `033_econ_region_events`, re-runnable `CREATE TABLE IF NOT EXISTS`,
  downgrade drops the 3 tables. No FKs → no FK-index pitfalls. Applied on the dev DB (`alembic_version_character` =
  `034_econ_mint`).

#### RBAC / security
- Reads `economy:read`; country / items writes `require_all_permissions(settings, emit)`; sim PUT money-param guard
  (403 «Нужно право на эмиссию» only when a money param actually changes). No new permission → no user-service change.
- Player: JWT + ownership + player-only + minter role/alive + activity lock + location + FEAT-145 gate (fail-closed,
  awaited without an open transaction) + capital check. Live: other character → 400 wrong location; minter outside the
  capital → 409 MSG_NO_MINT; foreign region as capital → 400; injection-like request_id → 422. Parameterised `text()`
  only; Russian, non-leaking error texts.

#### Copies, frontend, docs
- `scripts/check_econ_copies.sh` → all identical.
- Frontend: all new/changed files `.ts`/`.tsx`, Tailwind only, no `React.FC`, design-system classes (`modal`-shell,
  `btn-blue`, `btn-line`, `gold-text`, `input-underline`, `rounded-card`), every API call has a Russian toast/inline
  error. 360px: admin tab and MintModal have no horizontal overflow (iframe 360×740, `scrollWidth` 341).
- Docs: character-service (new section, lock order, cross-table write, game_time_config read), inventory-service
  (other writers of `character_inventory`), battle-pass-service updated.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (exit 0)
- [x] `npm run build` (`vite build`, frontend container) — PASS
- [x] `py_compile` on every changed/new .py — PASS
- [x] pytest character-service (`--asyncio-mode=auto`) — PASS, 3392 passed / 1 skipped
- [x] pytest battle-pass-service — PASS, 169 passed
- [x] pytest inventory-service (full, incl. the equip level fix) — PASS, 2110 passed
- [x] pytest locations-service / dungeon-service `test_econ_contract.py` — PASS (335 / 335, rc 0)
- [x] `scripts/check_econ_copies.sh` — PASS
- [x] `docker compose config -q` — PASS
- [x] Live verification (Chrome, localhost) — PASS

#### Live Verification Results
- `/admin/economy` → «Монетный двор»: season header, params card (limit saved 0 → 1000), countries (Мидденгерд auto
  capital «Мэттанхейм», ore 3 181,6 / norm 2 093,7, minter listed; other countries «нет столицы» warnings), ore editor
  (search by «Руда и металл», add with rate 10), quota history (1 entry). «Настройки» → «Квота сезона» card with the last
  issue line. All requests 200.
- `/world/region/9`: line «⚒️ Монетный двор — монетчик чеканит из руды марки» shown (has_mint true).
- `/location/197`: NPC «Петя» with badge «Монетчик» → «Монетный двор» button → MintModal; minted 3 pcs → toast,
  wallet 18 366 → 18 396 (header updated), bag 5 → 2, limit bar «игроки: 30 марок, осталось 970». API error paths
  checked (see above).
- Console errors: NONE. Network: no 4xx/5xx except the intentionally provoked ones.

#### Test data created and reverted
NPC 33 role `merchant → minter → merchant`; `econ_item_groups` override item 31 → ore_metal (deleted); +4 item 31 for
character 763 (net back to 1 piece); `mint_season_limit` param (key removed again); `econ_mint_items` 31 and
`econ_mints` 6 (deleted); 2 `mint_player` ops #450/#451 (postings and ops deleted, character balance −40, emission
account +40 → back to −101 980 175); capital ore stock −4 units (back to 3 181.578); season counter (6, 7148) reset to 0.
No tick ran during the test.

#### Non-blocking notes (no action required for PASS)
1. `economy_mint_crud.py:665` — admin country card returns `remaining = limit − minted` even when the mint is closed
   (e.g. a country without a capital shows «осталось 1 000 из 1 000»), while the player view zeroes it (`:493`).
   Cosmetic; could hide the bar for closed countries.
2. Analyst risk R2 does not hold on the current data: the capital's ore stock (3 181) is above its norm (2 094), so
   with threshold 100 % the court will start minting (up to the limit) at the first tick after a limit is set. Worth
   telling the user before setting the prod limit.
3. Local dev DB still holds leftovers of the backend developer's live check: `season_quota` operation #435 (10 000
   marks to 5 regions) and the zero counter row (6, 7148). Local only, harmless.

### Review #2 — 2026-11-01 — **PASS** (focused re-review of task #12)

Scope: partial acceptance at the Монетчик (user decision) + review #1 note 1 (admin `remaining = 0` for a closed mint).
Files: `CS/economy_mint_crud.py`, `CS/schemas.py`, `CS/tests/test_econ_mint_api.py`, `CS/tests/test_econ_mint_admin_api.py`,
`MintModal/MintModal.tsx`, `types/economy.ts`, `docs/services/character-service.md`.

#### Backend
- `economy_mint_crud.py:582-586` — `accepted = min(quantity, remaining // marks_per_item)`; `accepted <= 0` → 409
  `MSG_LIMIT` before anything is touched (0-fit unchanged). `marks = marks_per_item * accepted`.
- `:589` `_take_ore(..., accepted, need=quantity)` (`:524-548`) — the «not enough» check is against the REQUESTED
  quantity, only `accepted` pieces are removed (rows FOR UPDATE, ascending id, plain stacks only).
- `:591-597` stock / `minted_players` / `ore_units_players` grow by the accepted amount only; `:600-611` the
  `mint_player` posting (`emission -> character`, `marks` = accepted × rate) is still the last DB step, metadata
  carries `quantity` = accepted and `requested`. Ledger leg is emission → character, so the world sum stays 0.
- Lock order unchanged: `lock_capital` (regions → goods → mint_seasons) → `character_inventory` → posting
  (characters → econ_accounts). Same transaction, same idempotency key `mint:{character}:{request_id}`; the router
  still rolls back on any error.
- `:612-624` response `requested` / `partial`; `MSG_PARTIAL` (`:71-72`) Russian. `MSG_LIMIT_PARTIAL` is gone from code.
- `schemas.py:2848-2856` `MintActionOut` gains `requested: int`, `partial: bool` (Pydantic v1) — matches
  `types/economy.ts:1017-1029`.
- Admin `:678-679` — `remaining` = 0 when `status.working` is false (same rule as the player view `:494`). Note 1 fixed.
- Tests (`test_econ_mint_api.py:345-443`): partial with stacks / across 3 stacks, exact fit not partial, need-check
  against requested, idempotent retry of a partial (one op, 409 on the second), 0-fit still 409 and nothing taken,
  posting failure keeps all the ore, shared limit court + players; invariant (world sum 0) asserted.
  `test_econ_mint_admin_api.py:146` admin remaining 0 for no-capital and disabled countries.

#### Frontend
- `MintModal.tsx:41` input capped only by bag and 10 000; `:96-98` preview counts accepted pieces; `:319-323` hint
  «Двор примет только N шт. …»; `:350-354` partial server message stays in the modal; errors still via toast + inline
  (`bankErrorText`). TS, Tailwind only, no `React.FC`, design-system classes. Button disabled when 0 pieces fit.

#### Docs / spec
- `docs/services/character-service.md:1151-1159` describe partial acceptance, `requested` / `partial`, need-check.
- Feature file 3.8 (steps 5–8, Russian texts), 3.10 (`MintActionOut`), 3.14 (input cap) and «Questions for PM» Q2
  rewritten by the reviewer so the spec no longer mentions whole refusal / `MSG_LIMIT_PARTIAL` (Review #1 text kept
  as history).

#### Automated Check Results
- [x] `py_compile` (economy_mint_crud, schemas, both test files; in the character-service container) — PASS
- [x] pytest character-service, full suite `--asyncio-mode=auto` — PASS, 3399 passed / 1 skipped
- [x] `npx tsc --noEmit` (frontend container) — PASS (rc 0)
- [x] `npm run build` (frontend container) — PASS (built in 1m 57s)
- [x] `docker compose config -q` — PASS
- [x] Live verification (Chrome, localhost) — PASS

#### Live Verification Results
- Setup: NPC 33 «Петя» → `minter`, `econ_item_groups` 31 → ore_metal, `econ_mint_items` (31, 10/шт.),
  `econ_mints` (6, auto capital, season_limit 30), character 763 item 31 stack 1 → 5.
- `/location/197` → НПС → Петя (badge «Монетчик») → «Монетный двор»: limit «осталось 30 марок из 30», «в сумке: 5»,
  note «До конца сезона двор примет не больше 3 шт.». «Всё (5)» → hint «Двор примет только 3 шт. — лимит сезона,
  остальная руда останется у вас.», preview «30 марок (за 3 из 5 шт.)».
- «Отчеканить» → in-modal note «Принято 3 из 5 шт. — лимит сезона исчерпан, остальная руда осталась у вас.
  Отчеканено 30 марок: Ювелирный лом × 3»; wallet 18 366 → 18 396 (modal and header); bag 2; limit bar «игроки: 30,
  осталось 0»; hint «Лимит сезона исчерпан», button disabled.
- DB: one op #452 `mint_player` (metadata quantity 3, requested 5), one posting 30 emission → character 763;
  inventory 2; capital ore stock +3.000; counter (6, 7148) minted_players 30 / units 3.000.
- 0-fit via API (same session): 409 «Монетный двор исчерпал лимит до 10.11.2026», no new op.
- 360px (iframe 360×740): modal fits, no horizontal overflow (`scrollWidth` 345).
- Console errors: NONE.

#### Test data created and reverted
NPC 33 role `merchant → minter → merchant`; `econ_item_groups` 31, `econ_mint_items` 31, `econ_mints` 6 deleted;
op #452 + posting #1555 deleted; character 763 balance −30 (18 366), emission account +30 (−101 980 175);
capital ore stock −3 (3 181.578); counter (6, 7148) back to 0 / 0.000, `updated_at` NULL; inventory row 435 back to 1.
No tick ran during the test (last run id 67 before and after).

#### Non-blocking notes
- None new. `btn-blue` disabled state looks almost identical to enabled (design-system class, pre-existing, not
  task #12).

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-01 — PM: фича создана (FEAT-191, этап 5а экономики), решения пользователя записаны, запускаю анализ кодовой базы
[LOG] 2026-11-01 15:01 — Codebase Analyst: анализ завершён. Затронуты character-service (основная работа, миграция 034), копии econ_core в inventory/locations/dungeon, фронтенд. Главное: «игрового месяца» в календаре нет (только сезоны/праздники/недели) — нужен выбор пользователя; столица у страны нигде не хранится; в столицах руды обычно меньше нормы, автоматическая чеканка будет простаивать
[LOG] 2026-11-01 — PM: ответы пользователя: «месяц» = сезон+праздник (49 дн.), чеканка игроком = заработок для БП, порог двора — настройка (% нормы, по умолчанию 100). Запускаю архитектора
[LOG] 2026-11-01 — Architect: спроектировано 11 задач (5 бэкенд, 2 фронтенд, 3 QA, ревью), 9 API-контрактов (2 игровых, 6 админских, доработка sim PUT и карточки региона). Новые операции mint_court / mint_player / season_quota, миграция 034_econ_mint (3 таблицы), «сезон» = 49 дней из календаря (чтение game_time_config напрямую), новых прав нет. Два неблокирующих вопроса: стартовые числа квоты/лимита (по умолчанию 0 = выключено) и отказ целиком при нехватке лимита
[LOG] 2026-11-01 17:10 — Backend Dev: начал задачи #1–#5
[LOG] 2026-11-01 17:20 — Backend Dev: задача #1 завершена — операции mint_court / mint_player / season_quota в econ_core (+ кейсы контракта), копии в inventory/locations/dungeon побайтно совпадают (check_econ_copies.sh ok), комментарий в battle-pass
[LOG] 2026-11-01 17:40 — Backend Dev: задача #2 завершена — миграция 034_econ_mint (3 таблицы, up/down/up проверены в контейнере), модели, 4 параметра пересчёта, чистый econ_mint.py (сезон 49 дн. сверен с compute_game_time на 1500 датах)
[LOG] 2026-11-01 18:10 — Backend Dev: задача #3 завершена — economy_mint_crud.py (столица, статус двора, счётчик сезона, Монетчик, админка), проходы квоты и двора в тике, has_mint в карточке региона. Живая проверка на dev-БД: ручной пересчёт выдал квоту 10 000 одной операцией на 5 регионов, второй пересчёт — ничего
[LOG] 2026-11-01 18:30 — Backend Dev: задача #4 завершена — 7 эндпоинтов (2 игровых, 5 админских) + защита денежных параметров в PUT /sim (403 «Нужно право на эмиссию»); живая проверка чеканки двором и игроком на MySQL с откатом
[LOG] 2026-11-01 18:40 — Backend Dev: задача #5 завершена — документация character-service / inventory-service / battle-pass-service; в существующих тестах карточки региона добавлен ключ has_mint, в тесте сида параметров — префиксы mint_/quota_
[LOG] 2026-11-01 — Frontend Dev: начал задачи #6 и #7 (по контракту 3.10, параллельно с бэкендом)
[LOG] 2026-11-01 — Frontend Dev: задача #6 завершена — роль НПС «Монетчик», кнопка «Монетный двор» в профиле НПС, окно MintModal (сезон, лимит, руда, количество с ограничением, request_id, ошибки по-русски), строка «Монетный двор» в карточке региона, api/mint.ts и типы
[LOG] 2026-11-01 — Frontend Dev: задача #7 завершена — вкладка «Монетный двор» (параметры, страны со столицей/лимитом/выключателем, монетчики, список руды с курсом, история квот), карточка «Квота сезона» в «Настройках», раздел гайда, подсказки, подписи операций. tsc и build в контейнере проходят; живую проверку отложил до готовности бэкенда
[LOG] 2026-11-01 — QA: начал тесты для character-service и battle-pass-service (задачи #8–#10)
[LOG] 2026-11-01 — QA: задача #8 готова — test_econ_mint.py (35 тестов: границы сезона 48/49, смена года на 196, offset_days, сверка с compute_game_time на ~2300 датах, court_mint, split_quota, типы операций) + 5 тестов в battle-pass test_gold_missions.py (mint_player засчитывается как заработок, mint_court/season_quota — нет); контрактные кейсы зелёные во всех 4 сервисах, check_econ_copies.sh ok
[LOG] 2026-11-01 — QA: задача #9 готова — test_econ_tick_mint.py (28 тестов): квота один раз за сезон (повторный/ручной/авто/возобновлённый пересчёт), доли по населению, только участвующие регионы, новый сезон, пропущенные сезоны не догоняются, без календаря/без суммы — пропуск, сбой квоты с повтором; двор: столица авто/вручную/нет/две/устаревшая, порог, лимит общий с игроками, выключенная страна, повтор того же пересчёта, сбой одной страны не мешает другим, счётчики RunSummary
[LOG] 2026-11-01 — QA: задача #10 готова — test_econ_mint_api.py (52 теста: порядок проверок, успех с несколькими стопками, атомарность при сбое проводки, лимит и отказ целиком, идемпотентность, 401/403/422, инъекции) и test_econ_mint_admin_api.py (33 теста: права read / settings+emit, защита денежных параметров /sim, страна, руда, квоты, has_mint в карточке региона, поиск руды item-groups?group=ore_metal работает)
[LOG] 2026-11-01 — QA: тесты готовы, 148 новых тестов в character-service + 5 в battle-pass, все проходят; полный прогон character-service 3392 passed / 1 skipped, battle-pass-service 169 passed; багов в реализации не найдено
[LOG] 2026-11-01 — Reviewer: начал финальное ревью (задача #11)
[LOG] 2026-11-01 — Reviewer: автопроверки пройдены — py_compile, pytest character-service 3392/1 skip, battle-pass 169, inventory 2110, контракты locations/dungeon 335, check_econ_copies.sh, tsc и vite build в контейнере, docker compose config
[LOG] 2026-11-01 — Reviewer: живая проверка в Chrome — вкладка «Монетный двор», карточка «Квота сезона», строка в карточке региона, чеканка у Монетчика (3 шт. → 30 марок), ошибки (нехватка, лимит, дубль, чужая столица) по-русски; на 360px без переполнения; ошибок в консоли нет. Все тестовые данные откачены
[LOG] 2026-11-01 — Reviewer: вердикт PASS, три некритичных замечания в разделе 5
[LOG] 2026-11-01 — Developer: по новому решению пользователя монетчик принимает сколько влезает в лимит сезона (остальная руда остаётся у игрока), ответ сообщает «Принято N из M шт.»; ни одной штуки не влезает — по-прежнему 409. Исправлено замечание 1 ревью: в админке у закрытого двора остаток = 0
[LOG] 2026-11-01 — Developer: окно монетчика — количество ограничено только сумкой, подсказка «Двор примет только N шт.», «Получите» считает принятые штуки, сообщение о частичном приёме остаётся в окне
[LOG] 2026-11-01 — Developer: тесты обновлены (+7 игровых, +1 админский); полный прогон character-service 3399 passed / 1 skipped; tsc и build фронтенда в контейнере проходят; документация character-service обновлена
[LOG] 2026-11-01 — Reviewer: начал повторную проверку задачи #12 (частичный приём у монетчика, остаток 0 у закрытого двора в админке)
[LOG] 2026-11-01 — Reviewer: автопроверки пройдены — py_compile, pytest character-service 3399 / 1 skip, tsc и vite build в контейнере, docker compose config
[LOG] 2026-11-01 — Reviewer: живая проверка в Chrome — лимит 30 марок, сдал 5 руды: принято 3, 30 марок, 2 руды остались в сумке, подсказка и сообщение о частичном приёме в окне, на 360px без переполнения, ошибок в консоли нет; 0 влезающих штук — 409. Тестовые данные откачены
[LOG] 2026-11-01 — Reviewer: в разделе 3 убраны устаревшие упоминания «отказа целиком» и MSG_LIMIT_PARTIAL; вердикт PASS
[LOG] 2026-11-01 — PM: гайд «Как настроить» дополнен: шаг чек-листа «Монетный двор и квота сезона», рецепт «Монетный двор не чеканит или съедает весь лимит», исправлены устаревшие фразы (частичная приёмка, двор не простаивает); tsc/build OK, проверено в Chrome
[LOG] 2026-11-01 — PM: фича закрыта (DONE), выкатывается вместе с фиксом уровня на экипировке
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

Этап 5а экономики готов: монетный двор (по одному на страну, в столице) и квота раз в сезон.

- **Период** — сезон + праздник после него (49 дней), в интерфейсе «сезон».
- **Двор в пересчёте** берёт руду из запаса столицы выше X % нормы (настройка, по умолчанию 100 %), чеканит марки в казну страны; лимит сезона общий с игроками.
- **Монетчик** (новая роль НПС, только в столице): игрок сдаёт руду из админского списка по курсу; руда, запас, счётчик и марки — одной транзакцией; если не влезает в лимит — принимается сколько влезет, остальное остаётся у игрока. Засчитывается как заработок для боевого пропуска.
- **Квота сезона** — из эмиссии в казны участвующих регионов пропорционально населению, один раз за сезон.
- Админка «Экономика»: вкладка «Монетный двор», карточка «Квота сезона» в «Настройках»; в карточке региона — строка «Монетный двор».
- Стартовые квота и лимит = 0 (выключено), включает пользователь в админке.
- Миграция character-service `034_econ_mint`; 3 новых типа операций в econ_core (копии синхронизированы).
- Проверки: character-service 3399 passed, battle-pass 169, inventory 2110; tsc/build OK; два ревью PASS с живой проверкой в Chrome, тестовые данные откачены.
- Внимание: на текущих данных запас руды столицы выше нормы — двор начнёт чеканить в первом пересчёте после установки лимита.

