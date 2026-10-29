# FEAT-184: Экономика, этап 4 — банки

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-10-29 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Продолжение FEAT-181 (общая модель — раздел 1 `features/FEAT-181-world-economy.md`), FEAT-182 (живые регионы,
`features/DONE-FEAT-182-economy-living-regions.md`) и FEAT-183 (торговцы НПС,
`features/DONE-FEAT-183-economy-npc-merchants.md`).

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
В мире нет банков: деньги лежат только у игроков, торговцев, в казнах и кошельках жителей. Этап 4 добавляет банк
региона: игрок кладёт марки на вклад и получает процент, берёт займ, переводит вклад в банк другого региона или
другому игроку. Банк живёт и без игроков: жители региона в 6-часовом пересчёте держат часть сбережений на вкладе и
берут займы (числами), поэтому у банка есть доход и честная ставка.

Деньги по-прежнему не появляются и не исчезают: все движения — проводки в книге счетов (FEAT-181), сумма мира = 0.

### Бизнес-правила (согласовано с пользователем 2026-10-29, «Делай как рекомендуешь»)
- **Банк один на регион.** Свой счёт банка региона (вид счёта в книге). У региона в админке галочка «Банк есть»;
  «Заполнить регионы по шаблонам» включает её столице и порту, остальным — вручную.
- **Стартовый капитал** банк получает из казны региона (решение прошлых этапов).
- **Доступ через НПС-банкира.** Новая роль НПС «Банкир». В профиле банкира кнопка «Банк» (как «Магазин» у
  торговца). У любого банкира региона — один и тот же банк. Нужен тот же гейт, что у лавки: пост с обращением к
  НПС (FEAT-145). Персонаж должен стоять в локации банкира. Мёртвый банкир не работает (как мёртвый торговец).
- **Вклады двух видов:**
  - *до востребования* — положить/снять в любой момент, маленький процент, начисляется каждые 6 часов;
  - *срочный* на 7 / 14 / 28 реальных дней — процент выше; досрочное снятие: процент сгорает, сумма
    возвращается целиком.
- **Вклад привязан к банку региона.** Снять его можно только в этом банке (у его банкира). Перевести в банк
  другого региона можно с комиссией в казну.
- **Ставки.** Админ задаёт базовые ставки (вклады обоих видов, займы); банк сам снижает ставки по вкладам, если
  мало зарабатывает на займах. Проценты платятся только со счёта банка: пустой банк процентов не платит.
- **Займы:** один активный займ на персонажа; потолок суммы зависит от уровня персонажа; срок 7 / 14 / 28 дней;
  ставка фиксируется при выдаче; гасить можно досрочно и частями. Займ выдаётся из денег банка (нет денег — нет
  займа).
- **Просрочка — мягкая (без изъятия домов и вещей):** пени каждые 6 часов; метка «Должник» (видна самому игроку
  и админам); новые займы не выдаются; банк сам списывает долг с вкладов персонажа и с его кошелька, но не больше,
  чем там есть (баланс не уходит в минус).
- **Переводы другому игроку:** перевод марок на вклад другого игрока (в том же банке или в другом регионе), с
  комиссией в казну.
- **Банк без игроков:** в 6-часовом пересчёте кошелёк жителей региона держит часть сбережений на вкладе и берёт
  займы (агрегатные числа), получает/платит проценты. Это двигает доход банка и ставку.
- **Админка «Экономика»:** вкладка про банки — капитал, вклады, займы, должники, ставки; настройка ставок и
  параметров; ручные действия по необходимости.
- **Игрок видит:** в окне банка — свои вклады и займ в этом банке, ставки, кнопки; где-то в профиле/кошельке —
  сводку по всем своим вкладам и займу (в каком регионе что лежит).

### UX / Пользовательский сценарий
1. Игрок приходит в город, говорит с банкиром (пост с обращением), открывает «Банк».
2. Видит ставки, свои вклады в этом банке, займ (если есть).
3. Кладёт 1000 ṃ до востребования — через 6 часов набегает процент; снимает когда хочет.
4. Открывает срочный вклад на 14 дней под больший процент; по окончании срока забирает сумму с процентом.
5. Берёт займ на 7 дней; гасит частями. Если просрочил — пени, метка «Должник», банк списывает с вкладов/кошелька.
6. Переводит вклад в банк другого региона или отправляет марки другому игроку — с комиссией.

### Edge Cases
- Банк пуст: процентов нет, займов нет, снять вклад — нужно решить (вклады игроков всегда должны быть
  снимаемы: их деньги лежат на счёте банка; банк не может отдать в займы больше, чем позволяет резерв).
- Регион потерял галочку «Банк есть» / банкир умер / банкира убрали: вклады не пропадают; снять — у банкира того
  же региона, если он есть; иначе — нужно решить (перевод в другой банк должен оставаться возможным?).
- Персонаж удалён с вкладом / с долгом.
- Срочный вклад закончился, а игрок не пришёл — деньги ждут (переходят в до востребования?).
- Параллельные операции (двойной клик, два вкладыша), идемпотентность пересчёта.
- Огромные суммы, отрицательные/нулевые суммы, перевод самому себе.

### Вопросы к пользователю
- [x] Где банк → НПС-банкир, банк общий на регион.
- [x] Какие регионы → галочка «Банк есть», шаблоны «столица» и «порт» включают её сами.
- [x] Гейт поста → как у лавки.
- [x] Вклады → до востребования + срочный 7/14/28 дн., досрочно — без процента.
- [x] Ставки → базовые от админа, банк снижает при малом доходе; пустой банк не платит.
- [x] Займы → один, потолок от уровня, 7/14/28 дн., фикс. ставка, гашение досрочно и частями.
- [x] Просрочка → пени, метка «Должник» (видна игроку и админам), запрет новых займов, автосписание с вкладов и
  кошелька не больше остатка.
- [x] Переводы игроку → да, на вклад, с комиссией в казну.
- [x] Банк без игроков → жители держат вклады и берут займы числами в 6-часовом пересчёте.

### Решения PM по открытым краевым случаям (по рекомендации, пользователь может переиграть)
- **Вклады игроков всегда снимаемы.** Банк выдаёт займы (игрокам и жителям) только из денег сверх суммы вкладов
  игроков + резерв; поэтому снятие вклада игроком никогда не упирается в «нет денег».
- **Банкира нет / умер / галочку сняли:** вклады не пропадают. У любого живого банкира (в любом регионе) игрок
  видит все свои вклады и может перевести вклад из другого банка сюда (с комиссией) и снять. Без галочки «Банк
  есть» банк региона не принимает новые вклады и не выдаёт займы, проценты не начисляет; снятие и перевод — можно.
- **Срочный вклад закончился** → проценты начисляются, вклад сам становится вкладом до востребования.
- **Удаление персонажа:** его вклады уходят в казну региона банка; непогашенный займ списывается как убыток банка.
- **Комиссии банка в казну** облагаются как обычный доход казны (10 % регион → страна, по правилам книги).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Base read: FEAT-181 §3 (ledger), FEAT-182 §3.3–3.5 (tick), FEAT-183 §3.1–3.13 (merchants, lock order), the code
below. Paths are relative to `services/`. Working tree has uncommitted FEAT-183 follow-ups (dead-merchant closed shop:
`locations-service/app/main.py`, `crud.py`, `tests/test_npc_merchants.py`; `economyLabels.ts`, `NpcShopEditor.tsx`,
`userSlice.ts`) — developers must build on them, not overwrite.

### 2.1 Affected Services

| Service | Type of change | Files |
|---|---|---|
| character-service (recommended owner) | new bank tables (migration `031_…`), pure `econ_bank.py`, tick step, player bank API, admin bank API, region flag, deletion hook, sim params | `app/models.py`, `app/alembic/versions/031_*.py`, `app/econ_tick.py`, new `app/econ_bank.py`, new `app/economy_bank_crud.py`, `app/economy_api.py` (or new router), `app/schemas.py` (`ECON_SIM_PARAM_BOUNDS` :1881, `EconSimParamsIn` :2197), `app/econ_sim.py` (`SimParams` :53), `app/economy_sim_crud.py` (`fill_regions` :318, `update_region` :235, `_region_item` :169), `app/economy_crud.py` (summary :152, kind sets :26–33), `app/crud.py` (`post_character_deletion` :2449) |
| all 4 econ_core holders | new account kind(s) + op types (+ maybe leg types) — byte-identical | `{character,inventory,locations,dungeon}-service/app/econ_core.py`, `…/tests/econ_contract_cases.py` (×4) |
| locations-service | region deletion must close the bank account(s) (and decide deposits) | `app/crud.py:2352-2356` (`_close_treasury` of purse/treasury on region delete) |
| user-service | only if new permissions are chosen (see 2.9) | `alembic/versions/0033_*.py`, `tests/test_rbac_permissions.py` |
| frontend | banker role, «Банк» button + modal, wallet summary, admin «Банки» tab, labels | `constants/npc.ts`, `components/pages/LocationPage/NpcProfileModal.tsx`, new `BankModal.tsx`, `components/Admin/EconomyPage/*`, `economyLabels.ts`, `types/economy.ts`, `api/economyAdmin.ts`, profile `components/ProfilePage/CharacterTab/CharacterPanel.tsx:138` |

No nginx change if the API lives under `/characters/…` (economy router is mounted at `character-service/app/main.py:4558-4559`).

### 2.2 Q1 — Which service should own banks

**Recommendation: character-service** (owner of tables + player endpoints + tick step + admin).

| Need | character-service | locations-service |
|---|---|---|
| 6 h tick, ledger owner, `econ_*` tables, sim params | yes — `econ_tick.py`, `models.py:443-713` | would cross-write from the tick |
| Character level (loan cap) | local column `characters.level` (`models.py:61`) | raw SQL read |
| NPC role / status / location | local `npc_role` (`models.py:65`), `npc_status` (:66), `current_location_id` (:63) | raw SQL read |
| Ownership check | `verify_character_ownership` (`main.py:65`) | `verify_character_ownership` |
| Activity lock (FEAT-175) | `activity_lock.lock_for_character` (`activity_lock.py:72`) / `lock_message` (:81) | `check_not_activity_locked` (`main.py:177`) |
| Same-location check | `characters.current_location_id` (as teleport, `crud.py:3716-3721`) | `crud.get_character_location` / `get_npc_location` |
| FEAT-145 NPC gate | **not local**: `action_gates` table is owned by locations (`models.py:197-211`). Options: raw SQL read of `action_gates` (shared DB, same predicate as `crud._gate_match_clause` `crud.py:1195-1207`: `character_id, location_id=NPC location, action_type='npc_dialogue', status='open', target_ref = npc_id OR NULL`), or the existing internal HTTP `GET /locations/internal/action-gate` (`main.py:3982-3997`, `X-Internal-Token`, "no caller today"; client pattern `character-service/app/locations_client.py:151-190`) | `_require_npc_gate` (`main.py:841-854`) |
| Region of the NPC | `econ_ledger.resolve_location` (`econ_ledger.py:105`) | same (async) |

Precedent for a role-gated NPC money flow in character-service: teleport master (`crud.py:3624-3780`, role check,
same location, activity lock, `post_operation`) — it has **no** FEAT-145 gate; the shop gate is check-only (not
consumed, `main.py:848`). Bank tables in character-service avoid a third cross-owner write path (FEAT-183 already has
character-service writing `npc_shop_items`). locations-service would be the alternative only if the gate must stay
single-sourced there; then the tick would have to write bank tables owned by locations.

### 2.3 Q2 — Ledger fit (accounts, negatives, conservation)

**Ledger facts (`character-service/app/econ_core.py`):**
- Account = `(kind, ref_id)`, unique (`models.py:470-473` `uq_econ_accounts_kind_ref`); kinds are VARCHAR(32) values
  validated against `ACCOUNT_KINDS` (:45-49). `REF_KINDS` (:52) need `ref_id > 0`, others are singletons (`ref_id = 0`)
  (`validate_account` :397-408). So **per-entity accounts are supported** (e.g. `bank` ref = region id, or
  `bank_deposit` ref = deposit row id). Accounts are created lazily by `get_or_create_account` (`econ_ledger.py:157`);
  the name snapshot comes from `SQL_ACCOUNT_NAME[kind]` (:581-586; missing kind → name NULL, harmless).
- Balance of `character` lives in `characters.currency_balance`; every other kind in `econ_accounts.balance`.
- Negative rule: `NEGATIVE_ALLOWED_KINDS` (:64-66 — treasuries + sources). Non-negative accounts are guarded by the
  conditional UPDATE (`SQL_APPLY_ACCOUNT` :593-596, `SQL_DEBIT_CHARACTER` :588-591) → `InsufficientFunds`. A bank kind
  left out of that set is automatically "empty bank pays nothing".
- Taxes: an inflow `src ∈ TAX_SOURCE_KINDS (:72) → region_treasury` auto-adds a 10 % `region → country` leg. A
  player's commission (`character → region`) is taxed automatically; a `bank → region` inflow is taxed only if the bank
  kind is added to `TAX_SOURCE_KINDS` (decision for Architect; `apply_tax=False` per call also exists).
- `SOURCE_KINDS`/`SOURCE_OP_TYPES` (:69, :117): bank ops can never touch emission/adjustment — fine.
- Conservation: world sum is checked by `economy_crud.get_summary` (`economy_crud.py:152-194`): `held` sums **every**
  non-source kind generically (:171), so a new kind needs no invariant code; totals/labels (:196-203) and the frontend
  summary need a new line. Sub-invariants exist for escrow/storage (:175-179) — the same pattern fits a bank
  sub-invariant (e.g. Σ open deposits vs bank balance + outstanding loans).
- Kind sets in admin API to review: `EMISSION_TARGET_KINDS` (:26), `REGION_ACCOUNT_KINDS` (:29, journal region tag),
  `ADJUST_FORBIDDEN_KINDS` (:32 — likely add bank kinds), kind filter `economy_api.py:130` (uses `core.ACCOUNT_KINDS`).

**Two modelling options (decision for Architect; FEAT-181 §3 reserved names `bank` (region), `bank_deposit` / `loan`
(character) — `FEAT-181-world-economy.md:410`):**

| | A: one `bank` account per region + business rows | B: per-deposit ledger accounts |
|---|---|---|
| Ledger | `bank` (ref = region id, non-negative). Deposit/withdraw = `character ↔ bank`; interest = `bank → (deposit row)` i.e. just a number added to the row; loans `bank → character`, repay `character → bank` | `bank_deposit` (ref = deposit id) holds player money; `bank` (ref = region) holds capital |
| Fits brief «деньги вкладов лежат на счёте банка, банк даёт в долг из них с резервом» | **yes** — one pool, reserve rule is arithmetic over rows | no — deposit money is not lendable unless moved to `bank` |
| Per-player claim | business table (deposit principal + accrued); ledger sees only the pool | ledger sees each deposit |
| Accrued interest | moves no money until paid (interest = bank owes more) or posted `bank → bank`? impossible (src≠dst) → keep as row number, money moves on withdrawal | `bank → bank_deposit` each tick (one posting leg per deposit) |
| Resident aggregate deposits/loans | numbers on a per-region bank row; money `population_purse ↔ bank` | same, plus a pseudo deposit |
| Sub-invariant | `bank.balance + Σ loans principal_outstanding (+resident loans) ≥ Σ deposit claims` (solvency, not equality) | equality per account |

Note: with A, «вклад привязан к банку региона» and cross-bank transfer = `bank(A) → bank(B)` + commission
`bank(A) → region_treasury` (or `character →` if paid from wallet). Player→player transfer onto another player's deposit
= `character(A) → bank(X)` + new/increased deposit row of B, or a pure row move when funded from A's deposit in the same
bank (no money move — only the commission leg).

**econ_core additions (all 4 copies byte-identical + CI `econ-contract-copies`, `scripts/check_econ_copies.sh` groups
`econ_core`, `econ_contract_cases` ×4, sync ledger ×2 (character, inventory), async ledger ×2 (locations, dungeon)):**
- `KIND_BANK` (+ `KIND_BANK_DEPOSIT` / `KIND_LOAN` only for option B) → `ACCOUNT_KINDS`, `REF_KINDS`,
  `AccountRef.bank(region_id)` factory, `SQL_ACCOUNT_NAME[KIND_BANK] = "SELECT name FROM Regions WHERE id = :ref_id"`;
  decide `TAX_SOURCE_KINDS` membership.
- New op types in `OP_TYPES` (e.g. `bank_deposit`, `bank_withdraw`, `bank_interest`, `bank_transfer`, `loan_issue`,
  `loan_repay`, `loan_penalty`/`loan_collect`, `bank_capital`, `bank_tick` for the residents' step). Leg types: existing
  `main`/`commission` probably suffice (`commission` already in `CALLER_LEG_TYPES` :136).
- Pure maths (interest/penalty/rate adjustment) can stay in character-service `econ_bank.py` (like `econ_sim`,
  `econ_merchant`) if only character-service uses it — `econ_core` only needs what other services must know.
- `econ_ledger.py` (sync/async) needs **no change** (generic over kinds).
- `tests/econ_contract_cases.py` (×4) needs cases for the new kind: non-negative bank debit → `InsufficientFunds`;
  taxed/untaxed commission to treasury; transfer between two banks; reversal. Every service's `test_econ_contract.py`
  runs them.
- Frontend: `types/economy.ts` `EconAccountKind` union + `economyLabels.ts` (`ACCOUNT_KIND_LABELS` :36-46, kind lists
  :75-93, op/leg labels).

### 2.4 Q3 — Tick structure and where a bank step plugs in

`econ_tick.run_tick` (`econ_tick.py:746-857`): claim slot (`econ_tick_runs`, `UNIQUE(slot)`, `slot = floor(unix/21600)`;
manual run = `slot NULL`, an **extra** step) → grant plan fixed in the run row → `_prepare_merchants` (:860, own
session, best-effort) → per participating region (`SQL_PARTICIPATING` :244-248: `template_code IS NOT NULL AND
population > 0`) **one transaction** `_process_region` (:578-725):

1. `econ_regions` row `FOR UPDATE`; skip if `last_run_id == run_id` (idempotency guard, :600-602);
2. `econ_region_goods` `FOR UPDATE` (:604-607);
3. merchants: `lock_merchants` (:405-429) locks shop rows (asc id) then NPC `characters` (asc id) **before** any account;
4. `simulate_region` → row updates → `region_tick` posting, key `region_tick:<run>:r:<region>` (:664-673);
5. merchant step in `session.begin_nested()` SAVEPOINT (:681-699), key `merchant_trade:<run>:r:<region>`; failure →
   savepoint rollback + `merchant_failures`, region still commits;
6. history row → COMMIT (:701-712). `DuplicateOperation` → "already" (:714-718).

Bank step fit: a third SAVEPOINT after the merchant step (key `bank_tick:<run>:r:<region>`), with its rows locked
**in phase 3** (before the `region_tick` posting locks purse/treasury/country accounts), mirroring FEAT-183's rule.
`RunSummary` (:95) gains bank counters; `econ_tick_runs.error` is parsed for merchant failures by prefix (:73-75,
`merchant_failures_from_error` :432) — same trick avoids a migration.

Caveats:
- **Only simulated regions tick.** A region with «Банк есть» but no template/population would never accrue interest,
  penalties or collect debt → the flag must imply simulation, or the bank step needs its own loop over bank regions.
- Manual «Пересчитать сейчас» = an extra step → per-run accrual would pay extra interest; missed slots are never caught
  up (no interest for downtime). Accrual tied to real elapsed time (e.g. `last_accrued_at` on the row) avoids both.
- Tick kill switches: env `ECON_TICK_ENABLED` and `econ_sim_settings.tick_enabled` (`econ_scheduler.py:1-12`); with the
  tick off, deposits/loans freeze — maturity of term deposits / loans must be computed from timestamps, not from ticks.
- New params: add to `econ_sim.SimParams` (:53-98, defaults; missing JSON keys fall back), bounds in
  `schemas.ECON_SIM_PARAM_BOUNDS` (:1881) + `EconSimParamsIn` (:2197); `EconomyTick.tsx` renders the params form.
  No migration needed for params (FEAT-183 precedent). Per-region values (bank flag, current rates, resident
  deposits/loans, capital start) need columns — `econ_regions` has none (`models.py:594-613`).

### 2.5 Q4 — NPC roles («Банкир»)

- Backend: **no enumeration/validation** — `characters.npc_role` is `String(50)` (`models.py:65`); `NpcCreate` /
  `NpcUpdate.npc_role: Optional[str]` (`schemas.py:745`, :766). Only hard-coded checks: `'mob'`, `'teleport_master'`
  (`crud.py:3627`, `main.py:3108-3115` purges links when the role changes), `'auctioneer'` (`inventory-service/app/
  crud.py:2610`). A `'banker'` value works without backend change; role checks go in the bank endpoints.
- Frontend: `src/constants/npc.ts` — `NPC_ROLES` (select in `AdminNpcsPage.tsx:455-459`), `NPC_ROLE_LABELS`,
  `NPC_ROLE_ICONS`. Add `{ value: 'banker', label: 'Банкир' }` + icon.
- Button: `NpcProfileModal.tsx` shows «Торговля» when `GET /locations/npcs/{id}/shop` is non-empty (:84-94, :262) and
  role-based buttons for `auctioneer` (:282) / `teleport_master` (:302), all behind `isCharacterHere`. «Банк» fits the
  role-based pattern (`npc.npc_role === 'banker' && isCharacterHere`).
- Dead NPCs: `GET /characters/npcs/by_location` already hides `npc_status='dead'` (`main.py:3220-3243`) — the button
  is unreachable from the location page, but the endpoint must still refuse (409, as `SHOP_CLOSED_MESSAGE`
  `locations-service/app/main.py:2711-2717`).

### 2.6 Q5 — Level, deletion, existing transfers

- Level: `characters.level` (`character-service/app/models.py:61`, Integer default 1); no global max constant in code.
- **Deletion — one path:** admin `DELETE /characters/{id}` (`main.py:1431-1470`, `characters:delete`) →
  `crud.post_character_deletion` (`crud.py:2449-2468`): whole wallet → treasury of the character's location (else world
  treasury), op `character_deleted`, key `character_deleted:c:<id>`, account deactivated, same transaction as the row
  delete. Nothing knows about deposits/loans → a bank hook must go here (deposit claims → ? ; open loan → written off by
  the bank). With option A deposits are not ledger accounts, so forgetting the hook breaks no world invariant but
  leaves orphan claims / solvency drift.
- NPC deletion: same path (NPC cash goes to the place's treasury).
- Region deletion (locations `crud.py:2340-2360`): closes purse and treasury into the country (`_close_treasury`
  :4883-4903, op `treasury_closed`). A bank account would be left active and orphaned unless added there; FEAT-182
  `econ_tick.purge_orphans` (:276) deletes economy rows of deleted regions — bank rows need a policy (deposit claims!).
- **No player→player money transfer exists.** The only P2P gold movement is the item trade gold side
  (`inventory-service/app/crud.py:1147-1165`, op `trade`, key `trade:<id>`). Nothing to reuse beyond the ledger.

### 2.7 Q6 — Time

- Terms are **real** days (7/14/28) → plain naive-UTC datetimes like the rest of the economy (`econ_tick._utcnow`
  :145, `_naive_utc` :149, DB `DATETIME`). No game-calendar dependency.
- Game calendar exists only in locations-service (`crud.compute_game_time` :3213, `DAYS_PER_YEAR = 196`; frontend
  `utils/gameTime.ts`); houses use it for tax periods (`houses.py:2071` `TAX_PERIOD_DAYS = 49`). Not needed here.
- Slots: `TICK_SECONDS = 21600` (`econ_tick.py:59`); slot start helpers `slot_of` / `slot_start` (:158-166).

### 2.8 Q7 — Test patterns

- character-service: **SQLite in-memory** per test (`StaticPool`), character-service metadata + conftest hierarchy
  (Countries/Regions/Districts/Locations DDL added by an `after_create` hook, `tests/conftest.py:57-92`), migration-028
  seed loaded via `importlib` (`test_econ_tick_merchants.py:39-42`), foreign tables from
  `econ_contract_cases.MERCHANT_SQLITE_DDL`; money is seeded by emission postings (ledger stays closed; direct writes
  need `econ_ledger.allow_direct_balance_write`). Models to copy: `test_econ_tick_merchants.py` (tick step),
  `test_econ_merchants_api.py` (admin API via `TestClient`, permission matrix), `test_econ_merchant.py` (pure maths),
  `test_econ_contract.py` (shared cases). SQLite has no `FOR UPDATE` / SAVEPOINT (`econ_core.supports_for_update`,
  `econ_ledger._savepoint` :53-64) → races are not testable there; concurrency must be argued + unit-tested via
  idempotency keys / conditional updates.
- locations-service tests mock the async engine (`tests/conftest.py:23-38`) and use aiosqlite for econ files.
- user-service RBAC: `tests/test_rbac_permissions.py:1300-1380` (economy section with hard-coded counts).
- CI: pytest per service; dungeon/battle have `--timeout=30` (`.github/workflows/ci.yml:63`), job timeout 6 min (:87).
  character-service has no per-test timeout but a heavy tick test suite already runs there.

### 2.9 RBAC

Economy permissions: user-service migration `alembic/versions/0032_add_economy_permissions.py` (`economy:read|emit|
adjust|settings`, moderator gets `read`), tests `test_rbac_permissions.py:1300-1380` (explicit seed + counts — CLAUDE.md
§10.13: a new permission must be seeded and asserted there). FEAT-183 added **no** permissions (merchants tab =
`economy:read`, funding = `settings`+`emit` via `require_all_permissions`, `economy_api.py:239-245`). Bank admin can
follow the same mapping (read / settings for rates / adjust-like manual actions) without a user-service migration;
a new `economy:bank` permission would need migration 0033 + test section.

### 2.10 Frontend touch points

- Admin: `EconomyPage.tsx` tab union + `TAB_LABEL` + `tabs` list (:22-88); new `EconomyBanks.tsx` like
  `EconomyMerchants.tsx`; region flag in `RegionEconomyEditor.tsx` / `EconomyRegions.tsx`; params block in
  `EconomyTick.tsx`; labels `economyLabels.ts`; API `api/economyAdmin.ts`; types `types/economy.ts`.
- Player: modal like `NpcShopModal.tsx` (TS+Tailwind, 590 lines, uses `useCurrency`); balance in header
  `CharacterChip.tsx:50` (`user.character.currency_balance`) and profile `CharacterPanel.tsx:138`; Redux sync after a
  money action: `userSlice.ts` matcher on `profile/fetchProfile/fulfilled` (uncommitted, :203-214) or
  `setCharacterAfterTeleport`-style reducer (:148-163). Wallet/deposit summary + «Должник» mark naturally live in the
  profile panel. Region card `components/WorldPage/RegionEconomyCard.tsx` (public `GET
  /characters/economy/regions/{id}/card`, `economy_sim_crud.region_card` :705) could show «Банк есть» / rates.
- Currency text: `hooks/useCurrency.ts` (`format(n, short)`).

### 2.11 Risks

| Risk | Mitigation (for Architect) |
|---|---|
| **Deadlock: player bank flow vs tick.** A player transfer locks bank rows → characters → accounts (bank, treasury, country via tax). If the tick locks bank rows **after** the `region_tick` posting (which holds purse/treasury/country), a cycle appears | Lock bank/deposit/loan rows in phase 3 of `_process_region` (with merchants), before any account; global order extended to `econ_regions → econ_region_goods → npc_shop_items → bank rows (asc) → characters (asc) → econ_accounts (asc)`; player flows never lock `econ_regions` |
| **Deadlock: characters not locked in one ascending batch.** Merchant step locks NPC rows (`lock_merchants`); debt collection would then lock player rows — not globally ascending; a shop buy locks player+NPC ascending → cycle | Lock NPC + debtor player rows in one `lock_characters` call, or do debt collection in a separate transaction after the region commit |
| Cross-bank operations (transfer A→B, collecting debt from deposits in other regions) during per-region ticks | Lock bank rows of several regions in ascending id; or restrict tick collection to the same bank and run cross-bank collection outside the region transaction |
| Double click / concurrent deposits | Row `FOR UPDATE` + conditional debits (ledger); "one active loan" needs a DB-level guarantee (MySQL has no partial unique index → e.g. nullable unique `active_character_id` column) |
| Interest drift from manual runs / downtime | Time-based accrual (`last_accrued_at`) instead of per-run |
| Starting capital from treasury can drive the treasury negative (allowed kind) | Cap by treasury balance or accept (stage-1 rule) |
| Bank in a non-simulated region never ticks | Tie the flag to simulation or loop bank regions separately |
| Region/character deletion leaves bank account / claims orphaned | Hooks in `crud.post_character_deletion` (character) and locations `crud.py:2352` + `econ_tick.purge_orphans` (region) |
| econ_core edit must be byte-identical ×4 (CI fails otherwise); contract cases ×4 | Edit canonical, copy verbatim, run `sh scripts/check_econ_copies.sh` |
| Migrations order | character-service `031` (bank tables + `econ_regions` columns); locations-service changes only code (unless bank rows live there); user-service `0033` only for a new permission. Revision ids ≤ 32 chars (memory: MySQL gotchas). Deploy in one push; tick step must survive missing tables (SAVEPOINT + log, FEAT-183 §3.13 pattern) |
| CI time | Keep SQLite fixtures small; pure maths in a separate module tested without DB |
| Prod data | Pre-beta, data loss acceptable; banks start empty — only capital transfer from treasuries on «Заполнить регионы» / flag toggle |
| Sensitive data | Other players' deposits must not be exposed: player→player transfer endpoint returns only own state; recipient lookup by character id/name without balances |

### 2.12 Open questions for PM (edge cases from section 1 still marked «нужно решить»)

1. Empty bank / withdrawal guarantee: is a reserve rule enough, or must withdrawals always succeed (bank may go below
   the deposit total only through loans)?
2. Bank flag removed / no living banker in the region: may the player withdraw or transfer elsewhere via any banker?
3. Matured term deposit not collected: auto-convert to demand deposit?
4. Deleted character with deposits (to treasury? to the bank?) and with a loan (bank writes it off?).
5. Is a commission paid into a region treasury taxed 10 % to the country like other inflows (automatic for
   `character → region`)?

---

## 3. Architecture Decision (filled by Architect — in English)

Scope: **stage 4 «Banks»** — one bank per region behind NPC bankers, demand and term deposits for players, one loan
per character, soft overdue handling with auto-collection, transfers between banks and to other players, residents'
aggregate deposits/loans in the 6 h tick, admin «Банки» tab. Caravans, mint, notifications about due loans — later.
Everything is in **character-service** (analyst §2.2): tables, pure maths, tick passes, player and admin API. No
locations-service, nginx or user-service change; battle-pass-service gets a 3-line anti-abuse filter (3.16).

### 3.0 Questions for PM (product decisions not covered by section 1) — design uses the recommended answers

**2026-10-29: пользователь согласился со всеми рекомендациями Q1–Q5 («Согласен, делай»).**

| # | Question | Recommendation (used in this design) |
|---|----------|--------------------------------------|
| Q1 | Default numbers (admin can change them any time in «Пересчёт» → «Банки»). | Вклад до востребования **0,1 %/день** (≈ 0,7 % в неделю); срочный 7 дн. **0,2 %/день** (1,4 % за срок), 14 дн. **0,25 %/день** (3,5 %), 28 дн. **0,3 %/день** (8,4 %); займ **0,5 %/день** (3,5 % за 7 дней); пени **+1 %/день** сверху; потолок займа **500 + 250 × уровень** (ур. 1 — 750, ур. 30 — 8 000); комиссия перевода **2 %, минимум 1 ṃ**; минимальная сумма операции **10 ṃ**; стартовый капитал банка **20 000 ṃ** из казны (не больше, чем в казне есть). |
| Q2 | How is the recipient of a transfer to another player chosen? | By **exact character name** (players only, not NPCs). If several player characters share the name → refusal «Найдено несколько персонажей с таким именем». The sender sees nothing about the recipient's deposits. |
| Q3 | Depositing 1 minute before the 6 h recount would earn a full period of interest. | Interest for a period is paid on the **smallest balance the deposit had during that period** (a fresh deposit earns from the next full period; a top-up earns from the next period). Loans are the other way round: interest is counted to the minute, so early repayment saves interest. |
| Q4 | An unpaid overdue debt grows with penalties forever. | Penalties stop when the debt reaches **2 × the loan amount** (param). An admin can write a loan off by hand. |
| Q5 | The bank keeps its profit (loan interest − deposit interest − nothing else). | It accumulates in the bank (more money to lend, higher rates); an admin can move surplus to the region treasury with «Вернуть капитал в казну». No automatic drain (YAGNI). |

### 3.1 Key decisions

1. **Owner: character-service** — it owns the ledger, `econ_*`, the tick, sim params, `characters.level / npc_role /
   npc_status / current_location_id`, ownership and activity-lock helpers. New tables `econ_banks`, `bank_deposits`,
   `bank_loans` (migration `031_econ_banks`). The FEAT-145 NPC gate stays single-sourced in locations-service and is
   asked over the existing internal endpoint `GET /locations/internal/action-gate` (fail-closed).
2. **Money model = two ledger accounts per bank region (hybrid of analyst options A/B):**
   - `bank` (ref = region id, non-negative) — **the bank's own money**: starting capital, residents' deposits, loan
     repayments and interest. Loans (players and residents) and all interest are paid **only** from here.
   - `bank_deposits` (ref = region id, non-negative) — **the vault of player deposits**. Holds exactly
     Σ (`amount` + `interest_accrued`) of the open player deposit rows of that bank (new summary sub-invariant, like
     auction escrow). It is never lent → **a player deposit is always withdrawable** (PM decision) by construction,
     not by a reserve formula. Interest moves real money `bank → bank_deposits`, so the journal shows it and «empty
     bank pays nothing» is enforced by the ledger (non-negative `bank`).
   - Residents' deposits/loans are **numbers on `econ_banks`** (liability / receivable), money moves
     `population_purse ↔ bank`. A reserve `ceil(resident_deposits × bank_reserve_ratio)` stays in `bank` and is never
     lent nor used for interest.
   - Player loans are receivables on `bank_loans` rows (no ledger account); issuing = `bank → character`.
3. **Time-based accrual.** Every deposit/loan row and the bank row carry `accrued_at`; interest =
   `base × rate_day × elapsed_seconds / 86400` + a Decimal carry. Manual «Пересчитать сейчас» pays only the elapsed
   minutes, downtime is caught up on the next run, maturity/overdue are pure timestamp comparisons (work with the tick
   switched off).
4. **Tick: separate passes after the region loop, not a SAVEPOINT inside the region transaction.** Reasons: (a) a
   bank must accrue in regions **without simulation** (flag set on a non-templated region, or a region that left the
   simulation); (b) debt collection locks the debtor's deposit rows in other banks and the player's `characters` row —
   inside the region txn the `region_tick` posting already holds purse/treasury/country accounts → lock-order
   violation (analyst risk #1/#2). So: **bank pass** — one transaction per bank (interest, maturity, loan accrual,
   residents, rate factor; op `bank_tick`); then **collection pass** — one transaction per overdue loan (op
   `loan_collect`). Both idempotent (row `last_run_id` guard + ledger keys). A failure rolls back that bank / loan
   only and is retried next run (time-based accrual loses nothing).
5. **One global lock order** (3.8): `econ_regions → econ_region_goods → npc_shop_items → econ_banks (asc region_id)
   → bank_deposits (asc id) → bank_loans (asc id) → characters (asc id) → econ_accounts (asc id)`. **Rule:** every
   statement that changes `bank(X)` / `bank_deposits(X)` balances or rows of bank X holds `econ_banks(X) FOR UPDATE`
   first (exception: collection may draw from deposit rows of bank Y — it locks `econ_banks(Y)` too).
6. **Rates.** Admin sets global base rates (sim params). Per bank `deposit_rate_factor ∈ [factor_min, 1]` follows the
   bank's loan income vs its deposit cost (3.6). Demand rate = base × factor (current); a term deposit and a loan fix
   their rate at opening/issue.
7. **Flag «Банк есть» = `econ_banks.is_enabled`.** On: new deposits, loans, deposit interest, residents. Off:
   withdrawals (at this region's banker), transfers out, repayments, loan interest/penalties, maturity and collection
   keep working; deposit interest stops; residents wind their deposits/loans down to 0. First switch-on seeds
   capital from the region treasury once.
8. **Bankers.** Role `banker` (free string, no backend enum). Any living banker serves the bank of **his** region
   (the location → region resolution of `econ_ledger.resolve_location`); at any banker a player sees **all** own
   deposits/loan and may: withdraw deposits of this bank; transfer own demand deposits between any banks (destination
   must be enabled); send money to another player; take a loan here; repay his loan (whichever bank). Dead banker →
   409; NPCs hidden as dead are not reachable anyway.
9. **RBAC: no new permission.** Bank tab = `economy:read`; flag, capital moves, loan write-off, bank params =
   `economy:settings`. No user-service migration, `test_rbac_permissions.py` untouched.
10. **Player request idempotency:** optional `request_id` (UUID from the modal) → ledger key
    `bank:<op>:c<character>:<request_id>`; a double submit answers 409 «Операция уже выполнена». The `econ_banks` row
    lock serialises all player operations of one bank, `uq_bank_loans_active` guarantees one loan per character.

### 3.2 Ledger postings per flow

`T(R)` = treasury of region R (`region_treasury`); `W` = world treasury; `B(R)` = `bank`; `V(R)` = `bank_deposits`;
`P(R)` = `population_purse`; `C` = player character; X = the banker's region; L = the loan's region.

| Flow | Op type | Legs (src → dst, leg_type) | Tax | Idempotency key |
|---|---|---|---|---|
| Deposit (demand top-up / new demand / new term) at X | `bank_deposit` | `C → V(X)` main | none (dst not a treasury) | `bank:dep:c<C>:<request_id>` or none |
| Withdraw demand / matured term at X | `bank_withdraw` | `V(X) → C` main | — | `bank:wd:c<C>:<rid>` |
| Early close of a term deposit at X | `bank_withdraw` | `V(X) → C` main (amount) + `V(X) → B(X)` interest (forfeited accrued) | — | same |
| Own transfer deposit A → B (at banker in X) | `bank_transfer` | `V(A) → V(B)` main + `V(A) → T(X)` commission | commission taxed 10 % `T(X) → country` (V in `TAX_SOURCE_KINDS`) | `bank:tr:c<C>:<rid>` |
| Send to player, from wallet | `bank_transfer` | `C → V(B)` main + `C → T(X)` commission | 10 % (character is a tax source) | `bank:send:c<C>:<rid>` |
| Send to player, from own demand deposit in A | `bank_transfer` | `V(A) → V(B)` main + `V(A) → T(X)` commission | 10 % | same |
| Take loan at X | `loan_issue` | `B(X) → C` main | — | `bank:loan:c<C>:<rid>` |
| Repay loan (any banker) | `loan_repay` | `C → B(L)` main | — | `bank:repay:c<C>:<rid>` |
| Tick bank pass of X | `bank_tick` | `B(X) → V(X)` interest (player interest), `B(X) → P(X)` interest (residents' deposit interest), `P(X) → B(X)` interest (residents' loan interest), net `P(X) ↔ B(X)` main (residents' deposits in/out + loans issued/repaid, netted to one leg) | none (`apply_tax=False`; no treasury leg) | `bank_tick:<run>:b:<X>` |
| Tick collection of loan L | `loan_collect` | `V(Y) → B(L)` main per deposit bank Y (aggregated), `C → B(L)` main | — | `loan_collect:<run>:l:<loan_id>` |
| Capital seed (first switch-on / fill) | `bank_capital` | `T(X) → B(X)` main, amount `min(bank_start_capital, max(0, T(X)))` | — | `bank_capital:r:<X>:seed` |
| Admin capital in / out | `bank_capital` | `T(X) → B(X)` / `B(X) → T(X)` main | `apply_tax=False` | `bank_capital:r:<X>:p<last posting id of B(X)>:<in|out>:<amount>` |
| Character deletion | `character_deleted` (existing op, same key) | existing `C → treasury` leg + `V(Y) → T(Y)` main per bank Y with open deposits (destination `W` instead of `T(Y)` when region Y is deleted) | 10 % as for the wallet part | `character_deleted:c:<id>` (unchanged) |
| Orphan bank (region deleted) | `treasury_closed` (existing) | `B(X) → W` main | `apply_tax=False` | `bank_closed:r:<X>` |

Loan write-off, resident liability/receivable changes, maturity, merges — no money moves (rows only). World invariant
unchanged (no source accounts in any bank op).

### 3.3 DB changes — character-service migration `031_econ_banks` (revision id 14 chars)

```sql
CREATE TABLE econ_banks (
  region_id            BIGINT       NOT NULL PRIMARY KEY,          -- Regions.id (no FK, like econ_regions)
  is_enabled           TINYINT(1)   NOT NULL DEFAULT 0,             -- «Банк есть»
  deposit_rate_factor  DECIMAL(5,4) NOT NULL DEFAULT 1.0000,        -- 3.6, in [bank_rate_factor_min, 1]
  resident_deposits    BIGINT       NOT NULL DEFAULT 0,             -- bank owes the residents
  resident_loans       BIGINT       NOT NULL DEFAULT 0,             -- residents owe the bank
  resident_dep_carry   DECIMAL(16,6) NOT NULL DEFAULT 0,
  resident_loan_carry  DECIMAL(16,6) NOT NULL DEFAULT 0,
  accrued_at           DATETIME     NULL,                           -- residents' accrual clock
  capital_seeded_at    DATETIME     NULL,
  last_run_id          BIGINT       NULL,                           -- bank pass guard
  last_tick_at         DATETIME     NULL,
  last_stats           JSON         NULL,                           -- counters of the last bank pass (3.7)
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT ck_econ_banks_res CHECK (resident_deposits >= 0 AND resident_loans >= 0)
);

CREATE TABLE bank_deposits (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY,
  character_id      INT          NOT NULL,                          -- characters.id (no FK; deletion hook closes rows)
  region_id         BIGINT       NOT NULL,                          -- the bank
  kind              VARCHAR(8)   NOT NULL,                          -- demand | term
  status            VARCHAR(8)   NOT NULL DEFAULT 'open',           -- open | closed
  amount            BIGINT       NOT NULL DEFAULT 0,
  interest_base     BIGINT       NOT NULL DEFAULT 0,                -- smallest amount since accrued_at (Q3)
  interest_accrued  BIGINT       NOT NULL DEFAULT 0,                -- term only: credited, burnt on early close
  interest_total    BIGINT       NOT NULL DEFAULT 0,                -- lifetime credited (display)
  interest_carry    DECIMAL(16,6) NOT NULL DEFAULT 0,
  rate_day          DECIMAL(8,6) NULL,                              -- term: fixed at opening; demand: NULL (current)
  term_days         SMALLINT     NULL,                              -- 7 | 14 | 28 (kept after conversion)
  opened_at         DATETIME     NOT NULL,
  matures_at        DATETIME     NULL,
  accrued_at        DATETIME     NOT NULL,
  closed_at         DATETIME     NULL,
  demand_owner_id   INT          NULL,                              -- = character_id while kind=demand AND open
  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_bank_deposits_bank FOREIGN KEY (region_id) REFERENCES econ_banks (region_id),
  CONSTRAINT uq_bank_deposits_demand UNIQUE (region_id, demand_owner_id),   -- one open demand deposit per bank
  KEY ix_bank_deposits_region_status (region_id, status),                   -- explicit FK index (memory: MySQL FK gotcha)
  KEY ix_bank_deposits_char_status (character_id, status),
  CONSTRAINT ck_bank_deposits_kind CHECK (kind IN ('demand', 'term')),
  CONSTRAINT ck_bank_deposits_status CHECK (status IN ('open', 'closed')),
  CONSTRAINT ck_bank_deposits_amounts CHECK (amount >= 0 AND interest_accrued >= 0 AND interest_base >= 0)
);

CREATE TABLE bank_loans (
  id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
  character_id        INT          NOT NULL,
  region_id           BIGINT       NOT NULL,                        -- the lending bank
  status              VARCHAR(12)  NOT NULL DEFAULT 'active',       -- active | overdue | closed | written_off
  principal           BIGINT       NOT NULL,
  debt                BIGINT       NOT NULL,                        -- outstanding incl. interest + penalties
  interest_total      BIGINT       NOT NULL DEFAULT 0,
  penalty_total       BIGINT       NOT NULL DEFAULT 0,
  paid_total          BIGINT       NOT NULL DEFAULT 0,              -- voluntary repayments
  collected_total     BIGINT       NOT NULL DEFAULT 0,              -- auto-collection
  written_off         BIGINT       NOT NULL DEFAULT 0,
  rate_day            DECIMAL(8,6) NOT NULL,                        -- fixed at issue
  penalty_rate_day    DECIMAL(8,6) NOT NULL,                        -- fixed at issue (added on top after due_at)
  term_days           SMALLINT     NOT NULL,
  issued_at           DATETIME     NOT NULL,
  due_at              DATETIME     NOT NULL,
  accrued_at          DATETIME     NOT NULL,
  interest_carry      DECIMAL(16,6) NOT NULL DEFAULT 0,
  closed_at           DATETIME     NULL,
  closed_by_user_id   INT          NULL,                            -- admin write-off
  note                VARCHAR(500) NULL,                            -- write-off comment
  active_character_id INT          NULL,                            -- = character_id while active|overdue, else NULL
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_bank_loans_bank FOREIGN KEY (region_id) REFERENCES econ_banks (region_id),
  CONSTRAINT uq_bank_loans_active UNIQUE (active_character_id),     -- one active loan per character (NULLs free)
  KEY ix_bank_loans_region_status (region_id, status),              -- FK index
  KEY ix_bank_loans_char (character_id),
  KEY ix_bank_loans_status_due (status, due_at),
  CONSTRAINT ck_bank_loans_amounts CHECK (principal > 0 AND debt >= 0),
  CONSTRAINT ck_bank_loans_status CHECK (status IN ('active', 'overdue', 'closed', 'written_off'))
);
```
ORM models `EconBank`, `BankDeposit`, `BankLoan` in `models.py` (`_EconId` BIGINT/INTEGER variant for SQLite ids,
`server_default`s so `create_all` in SQLite tests builds them; DECIMAL → `Numeric`). Downgrade: drop the three tables
(bank / vault ledger accounts stay with their balances — downgrade only with empty banks; documented). No data
migration: banks start empty. `econ_regions` unchanged. Revision `031_econ_banks`, down `030_currency_short_mark`.

### 3.4 Shared contract change (`econ_core.py`, 4 byte-identical copies — CI `econ-contract-copies`)

| Constant / function | Change |
|---|---|
| `KIND_BANK = "bank"`, `KIND_BANK_DEPOSITS = "bank_deposits"` | add to `ACCOUNT_KINDS` and `REF_KINDS` (ref = region id); **not** in `NEGATIVE_ALLOWED_KINDS` |
| `AccountRef.bank(region_id)`, `AccountRef.bank_deposits(region_id)` | factories |
| `SQL_ACCOUNT_NAME[KIND_BANK]`, `[KIND_BANK_DEPOSITS]` | `SELECT name FROM Regions WHERE id = :ref_id` |
| `TAX_SOURCE_KINDS` | **+ `KIND_BANK_DEPOSITS`** (commission from a deposit and the deletion payout are taxed 10 % like wallet money, PM decision). `KIND_BANK` is **not** added (capital return is not income; bank ops never post `bank → region` except `bank_capital` with `apply_tax=False`) |
| `OP_BANK_DEPOSIT`, `OP_BANK_WITHDRAW`, `OP_BANK_TRANSFER`, `OP_BANK_TICK`, `OP_BANK_CAPITAL`, `OP_LOAN_ISSUE`, `OP_LOAN_REPAY`, `OP_LOAN_COLLECT` (`"bank_deposit"`, `"bank_withdraw"`, `"bank_transfer"`, `"bank_tick"`, `"bank_capital"`, `"loan_issue"`, `"loan_repay"`, `"loan_collect"`) | add to `OP_TYPES` (not source ops) + `BANK_OP_TYPES = frozenset({...all 8})` |
| `LEG_INTEREST = "interest"` | add to `LEG_TYPES` and `CALLER_LEG_TYPES` |

`econ_ledger.py` (sync/async) — no change. `tests/econ_contract_cases.py` (4 copies) gains bank scenarios, run by every
`test_econ_contract.py`: (a) `C → V(R)` then `V(R) → C` round trip, balances back; (b) debit of `V(R)` or `B(R)` above
balance → `InsufficientFunds`, nothing moved; (c) `V(A) → T(X)` commission → generated 10 % `T(X) → country`;
`C → T(X)` commission taxed; `B(X) → T(X)` with `apply_tax=False` untaxed and with default tax untaxed (bank not a
tax source); (d) `V(A) → V(B)` + commission in one op, sum of the world unchanged; (e) reversal mirrors all legs;
(f) `interest` leg accepted from callers; `AccountRef.bank(0)` rejected (ref kind). `scripts/check_econ_copies.sh`
unchanged. Pure bank maths stays in character-service (`econ_bank.py`) — no other service needs it.

### 3.5 Sim params (`econ_sim.SimParams` defaults, `schemas.ECON_SIM_PARAM_BOUNDS`, `EconSimParamsIn` Optional fields; no migration)

| param | default | bounds | meaning |
|---|---|---|---|
| `bank_demand_rate_day` | 0.001 | 0 … 0.05 | base demand-deposit rate per day (× factor) |
| `bank_term_rate_day_7` | 0.002 | 0 … 0.05 | base term rate, 7 days (× factor at opening) |
| `bank_term_rate_day_14` | 0.0025 | 0 … 0.05 | 14 days |
| `bank_term_rate_day_28` | 0.003 | 0 … 0.05 | 28 days |
| `bank_loan_rate_day` | 0.005 | 0 … 0.1 | loan rate per day (players and residents), fixed at issue |
| `bank_penalty_rate_day` | 0.01 | 0 … 0.1 | added to the loan rate after `due_at` |
| `bank_debt_cap_mult` | 2.0 | 1 … 10 | interest + penalties stop at `principal × mult` (Q4) |
| `bank_loan_cap_base` | 500 | 0 … 1e9 | loan cap = base + per_level × level |
| `bank_loan_cap_per_level` | 250 | 0 … 1e9 | |
| `bank_min_amount` | 10 | 1 … 1e6 | minimum deposit / withdrawal-from-demand / transfer / loan / repay (repay of the whole rest is always allowed) |
| `bank_transfer_fee_rate` | 0.02 | 0 … 0.5 | commission share, `ceil` |
| `bank_transfer_fee_min` | 1 | 0 … 1e6 | minimum commission |
| `bank_start_capital` | 20000 | 0 … 1e9 | capital taken from the treasury at first switch-on |
| `bank_reserve_ratio` | 0.2 | 0 … 1 | share of residents' deposits never lent / never used for interest |
| `bank_rate_cover` | 1.25 | 0.5 … 5 | the bank wants loan income ≥ cover × deposit cost |
| `bank_rate_factor_min` | 0.2 | 0 … 1 | lowest deposit-rate factor |
| `bank_rate_smoothing` | 0.25 | 0 … 1 | factor moves this share toward its target per pass |
| `bank_resident_deposit_share` | 0.2 | 0 … 0.9 | residents keep this share of their savings (purse + deposits) in the bank |
| `bank_resident_loan_share` | 0.1 | 0 … 0.9 | residents' loan target as a share of the purse |
| `bank_resident_adjust` | 0.25 | 0 … 1 | per 6 h the residents move this share of the gap to their targets |

Ints (`bank_loan_cap_*`, `bank_min_amount`, `bank_transfer_fee_min`, `bank_start_capital`) are `int` fields. Player
endpoints read params with `econ_tick.load_params` (same JSON).

### 3.6 Pure maths — new `app/econ_bank.py` (no DB; Decimal; explicit rounding)

Rounding rule: what the bank **pays** (interest) → `ROUND_FLOOR`; what the player **pays** (commission) →
`ROUND_CEILING`; reserve → `ROUND_CEILING`; interest owed **to** the bank (loans) → `ROUND_FLOOR` with the fraction kept
in `interest_carry` (exact over time). Carries are quantized to 6 dp (`ROUND_FLOOR`). `DAY = 86400`.

```
accrue(base:int, rate_day:Decimal, seconds:int, carry:Decimal) -> (int, Decimal)
    exact = Decimal(base) * rate_day * seconds / DAY + carry ; i = floor(exact) ; return i, q6(exact - i)
demand_rate(params, factor) -> Decimal            = base_demand * factor
term_rate(params, term_days, factor) -> Decimal   = base_term[term] * factor   (term ∈ {7,14,28} else ValueError)
reserve(resident_deposits, ratio) -> int          = ceil(resident_deposits * ratio)
lendable(bank_balance, resident_deposits, params) -> int = max(0, bank_balance - reserve(...))
loan_cap(level, params) -> int                    = cap_base + cap_per_level * max(1, level)
transfer_fee(amount, params) -> int               = max(fee_min, ceil(amount * fee_rate))
is_overdue(loan, now) -> bool                     = status in (active, overdue) and debt > 0 and now >= due_at
accrue_loan(loan: LoanState, now, params) -> LoanAccrual(interest, penalty, debt, carry, status)
    split [accrued_at, now) at due_at: before -> rate_day; after -> rate_day + penalty_rate_day (penalty part
    reported separately); compounding on the running debt per segment; debt never above principal * debt_cap_mult
    (excess dropped, carry reset); status 'overdue' when now >= due_at and debt > 0.
prorata(dues: Sequence[int], available: int) -> (List[int], skipped)   floor(due * available / total) when short
plan_collection(debt, deposits: [(id, kind, amount, interest_accrued)], wallet) -> CollectionPlan
    order: demand deposits (asc id), then term deposits (asc id) taking interest_accrued first, then amount;
    then wallet; every take ≤ what is there; total ≤ debt.
rate_factor_next(factor, income, cost_base, params) -> Decimal
    target = 1 if cost_base == 0 else clamp(income / (cost_base * cover), factor_min, 1)
    return q4(clamp(factor + (target - factor) * smoothing, factor_min, 1))
bank_step(BankInput) -> BankOutput        # the whole bank pass for one bank, below
```

`bank_step` (input: `now`, `enabled`, `simulated`, `params`, `factor`, `bank_balance`, `purse_balance`, residents
`{deposits, loans, dep_carry, loan_carry, accrued_at}`, open deposits of this bank ascending id, active/overdue loans
of this bank ascending id):
1. **Loans** (always): `accrue_loan` each → new debt/status/carry; `income = Σ interest + Σ penalty`.
2. **Deposit dues** (only when `enabled`): per deposit `end = min(now, matures_at)` (term) else `now`;
   `seconds = max(0, end − accrued_at)`; rate = row `rate_day` (term) or `demand_rate(factor)`;
   `due, carry = accrue(interest_base, rate, seconds, carry)`. Residents (enabled and simulated):
   `due_res = accrue(resident_deposits, demand_rate, seconds_bank, dep_carry)`. `cost_base` = the same dues computed
   with factor 1 for demand/residents and the fixed rate for term. When disabled: dues 0, carries 0.
3. **Pay**: `available = lendable(bank_balance, resident_deposits)`; `pays = prorata(dues + [due_res], available)`;
   when short, the unpaid part is forfeited (carries of shortened rows set to 0) → `stats.interest_skipped`.
   Demand: `amount += pay`; term: `interest_accrued += pay`; both `interest_total += pay`. `bank_balance −= Σ pays`.
4. **Maturity**: term rows with `matures_at ≤ now` (ascending id): `amount += interest_accrued`, `interest_accrued = 0`;
   if the same character has an open demand row in this bank (existing or just converted) → merge into it (term row
   closed, amount 0) else convert in place (`kind='demand'`, `rate_day=NULL`, `demand_owner_id=character_id`).
5. **Clocks**: every row `accrued_at = now`; demand `interest_base = amount` (after interest/merge); term
   `interest_base = amount` (unchanged).
6. **Residents**: `k = min(1, adjust × seconds_bank / 21600)`; targets are 0 when not (`enabled` and `simulated`).
   a) loan interest `due_l = accrue(resident_loans, loan_rate, seconds_bank, loan_carry)`; paid `min(due_l, purse)`
      `P → B` (interest), unpaid forgiven (carry 0); `income += paid`;
   b) deposits: `target_d = floor((purse + resident_deposits) × deposit_share)`; `dd = trunc((target_d −
      resident_deposits) × k)`; `dd > 0` → `in = min(dd, purse)` `P → B`; `dd < 0` → `out = min(−dd, bank_balance)`
      `B → P`; `resident_deposits ±=`;
   c) loans: `target_l = floor(purse × loan_share)` (purse after a, b); `dl = trunc((target_l − resident_loans) × k)`;
      `dl > 0` → `issue = min(dl, lendable(bank_balance, resident_deposits))` `B → P`; `dl < 0` → `repay = min(−dl,
      purse)` `P → B`; `resident_loans ±=`.
   *Changed by B3:* the residents' moves (b, c) round **away from zero** (`ROUND_UP`) instead of `trunc` —
   `ceil(|gap| × k) ≤ |gap|` for `k ≤ 1`, so it never overshoots, while `trunc` left a wind-down stuck at a few coins.
   `seconds_bank` = `TICK_SECONDS` (21600) when `econ_banks.accrued_at` is NULL (first pass); the factor (7) is updated
   only when `seconds_bank > 0` (a second manual run at the same instant changes nothing).
   *Changed by Q1:* `rate_factor_next` rounds the smoothed **step** away from zero (4 dp) and never past the target —
   with HALF_UP the factor stalled 0.0001–0.0002 short (0.9999 never returned to 1.0000).
   *Changed by fix (B5 bug, factor smoothed per run):* smoothing (7) and the residents' `k` (6) are **time-weighted**:
   `w(share, seconds) = 1 − (1 − share) ** periods`, `periods = min(seconds_bank / 21600, 4)` (`MAX_CATCHUP_PERIODS`
   — after a long downtime they catch up at most one day); `k = w(adjust)`, factor step `= (target − factor) ×
   w(smoothing)`. The away-from-zero rounding fades for short runs: a step (coins / 0.0001) rounds away only when its
   fraction is ≥ `1 − periods`, otherwise toward zero — at one full period (or more) identical to before, at elapsed 0
   nothing moves, a run seconds after the previous one moves only what is proportional (no forced 1 coin / 0.0001).
   Two half-periods ≈ one period. `rate_factor_next(..., seconds=21600)` takes the elapsed seconds.
7. **Factor** (enabled only): `factor = rate_factor_next(factor, income, cost_base, params)`.
8. **Legs**: at most one leg per (src, dst, leg_type): `B → V` interest, `B → P` interest, `P → B` interest, and the
   **net** of the `main` resident flows as one `P → B` or `B → P` leg. Output carries row updates, resident state,
   factor, legs and stats `{interest_paid, interest_skipped, resident_interest_paid, loan_interest, penalties,
   resident_loan_interest, resident_in, resident_out, resident_issued, resident_repaid, matured, merged}`.

Guarantees (asserted by tests): `bank_balance`, `purse` never below 0; Σ player pays = `V` delta; reserve never
touched by interest or lending; deterministic for equal input; inputs not mutated.

### 3.7 Tick integration (`app/econ_tick.py` + new `app/economy_bank_crud.py`)

`run_tick` after the region loop (before the final run-row update):
1. `_prepare_banks` (own session, best effort): **orphan purge** — for every `econ_banks` row whose `Regions` row is
   gone: lock the row, `is_enabled = 0`, `resident_deposits = resident_loans = 0` (residents are gone), open loans of
   that bank → `written_off` (no money), post `treasury_closed` `B(X) → W` (key `bank_closed:r:<X>`, `apply_tax=False`)
   and deactivate `B(X)`. The vault `V(X)` stays: those deposits can still be transferred to another bank from any
   banker (and are paid out to `W` if the owner is deleted). Rows are kept (FK).
2. **Bank pass**: banks = `econ_banks` rows with `is_enabled = 1` OR open deposits OR active/overdue loans OR non-zero
   resident balances, ascending region id. Per bank one transaction: `econ_banks` row `FOR UPDATE` (skip when
   `last_run_id = run_id`) → open deposits `ORDER BY id FOR UPDATE` → active/overdue loans `ORDER BY id FOR UPDATE` →
   read `B(X)`, `P(X)` balances and the region's `econ_regions` simulated flag (plain read) → `econ_bank.bank_step`
   → row updates (rows whose `amount` hits 0 after a merge: `status='closed'`, `closed_at`, `demand_owner_id = NULL`)
   → `post_operation(op_type='bank_tick', legs, region_id=X, idempotency_key='bank_tick:<run>:b:<X>',
   apply_tax=False, metadata=stats)` → `last_run_id`, `last_tick_at`, `accrued_at`, `last_stats` → COMMIT. Exception →
   rollback that bank, log `region id + error class`, `bank_failures += 1`.
3. **Collection pass**: loans `status IN ('active','overdue') AND due_at <= now`, ascending id. Per loan one
   transaction: read (no lock) the debtor's open deposits' bank ids → `econ_banks` FOR UPDATE for {L} ∪ those (asc) →
   debtor's open deposits in those banks `ORDER BY id FOR UPDATE` → loan row FOR UPDATE (skip if no longer open) →
   `accrue_loan` to now → `plan_collection` with `lock_characters([debtor])` balance → row updates (deposit
   `amount`/`interest_accrued` down, `interest_base = min(interest_base, amount)`, emptied rows closed; loan `debt −=`,
   `collected_total +=`, `status = 'overdue'`, or `closed` + `active_character_id = NULL` at 0) → post `loan_collect`
   (key `loan_collect:<run>:l:<loan>`) → COMMIT. Nothing to take → only the status/accrual update.
4. `RunSummary` gains `banks_processed`, `bank_ops_posted`, `bank_failures`, `bank_failed_region_ids`,
   `bank_interest_paid`, `loans_overdue`, `loans_collected`, `collected_amount`, `banks_closed`. Run error text gets
   `BANK_ERROR_PREFIX = "банки — ошибка в регионах: "` (parsed like `MERCHANT_ERROR_PREFIX`, no migration).
5. Missing tables (tick deployed before `031`) → `_prepare_banks` / passes log a warning and skip; regions still tick.
The passes run in auto and manual runs; with the tick switched off nothing accrues (timestamps catch up later).

### 3.8 Lock order (supersedes FEAT-183 3.5; documented in `econ_tick.py` docstring and `character-service.md`)

`econ_regions → econ_region_goods → npc_shop_items (asc id) → econ_banks (asc region_id) → bank_deposits (asc id) →
bank_loans (asc id) → characters (asc id) → econ_accounts (asc id)`.

| Flow | Locks, in order |
|---|---|
| region txn of the tick (unchanged) | region → goods → shop rows → NPC chars → accounts (never touches bank tables) |
| bank pass X | `econ_banks(X)` → deposits of X → loans of X → accounts (B, V, P of X) |
| collection of loan L | `econ_banks` {L, deposit banks} asc → debtor deposits → loan → debtor char → accounts |
| deposit / withdraw at X | `econ_banks(X)` → deposit row (or new) → char → accounts |
| own transfer A→B / send | `econ_banks` {A, B} asc → deposit rows (source, destination; new destination inserted last) asc → char (wallet source) → accounts (V(A), V(B), T(X), country) |
| loan issue at X / repay to L | `econ_banks(X|L)` → the character's loan rows → char → accounts |
| character deletion | `econ_banks` of all its deposits/loans asc → deposits → loans → char → accounts |
| admin flag / capital / write-off | `econ_banks(X)` (inserted if missing) → loan row → accounts |
| fill regions (`open_banks`) | region rows → `econ_banks` asc → accounts |
| orphan purge | `econ_banks(X)` → loans of X → accounts |

Player flows never lock `econ_regions` (simulated flag and region names are plain reads).

### 3.9 Player flows and API (character-service, `economy_api.py` router → under `/characters/economy/…`, mounted before the main router — no path collision, no nginx change)

Common banker check `_resolve_banker(db, npc_id, character)` (order fixed, tests assert it):
1. JWT (`get_current_user_via_http`) → `verify_character_ownership` (404/403); character must be a player (`is_npc=0`).
2. NPC: exists, `is_npc=1`, `npc_role='banker'` else **404 «Банкир не найден»**; `npc_status='dead'` → **409 «Банкир
   больше не принимает посетителей»**.
3. Activity lock: `activity_lock.lock_message(lock_for_character(character))` → **409** with that text (POST only).
4. Same location: `character.current_location_id == npc.current_location_id` else **400 «Подойдите к банкиру — он в
   другой локации»** (POST and GET).
5. FEAT-145 gate (POST only): new `locations_client.check_npc_gate(character_id, location_id, npc_id) -> bool` (async,
   `GET /locations/internal/action-gate?action_type=npc_dialogue&target_ref=<npc>`, `X-Internal-Token`, 5 s);
   `False` → **403 «Нужен пост-намерение «Диалог с НПС» с этим персонажем»** (same text as the shop); transport error /
   non-200 → **503 «Не удалось проверить обращение к банкиру, попробуйте позже»** (fail-closed). Endpoints are
   `async def`, the gate is awaited before the DB transaction starts.
6. Region: `econ_ledger.resolve_location(npc.current_location_id)`; none → **409 «Этот банкир не служит ни одному
   банку»**. Bank row may be missing → «no bank».

| Method & path | Body / query | Response | Notes / errors (Russian, besides the common ones) |
|---|---|---|---|
| `GET /characters/economy/bank/npc/{npc_id}?character_id=` | — | `BankView` | read-only, no gate; projected loan debt (accrued to now, not stored) |
| `POST …/bank/npc/{npc_id}/deposit` | `BankDepositIn` | `BankActionOut` | bank disabled/missing → 409 «В этом регионе банк не принимает вклады»; amount < min → 400 «Минимальная сумма — {N}»; term_days ∉ {7,14,28} → 422; > `MAX_TERM_DEPOSITS = 10` open term deposits → 409 «Не больше 10 срочных вкладов»; wallet short → 400 «Недостаточно {genitive}». Demand: top-up of the open demand row (new row: `interest_base = 0`) ; term: new row, `rate_day = term_rate(factor)`, `matures_at = now + term` |
| `POST …/bank/npc/{npc_id}/withdraw` | `BankWithdrawIn` | `BankActionOut` | deposit not own/open → 404 «Вклад не найден»; other bank → 400 «Этот вклад лежит в банке региона «{name}» — снять его можно только там или перевести сюда»; demand: `amount` 1..row amount (≥ min unless the whole rest), `interest_base = min(base, new amount)`, 0 → closed; term not matured: whole deposit, interest forfeited (message «Срочный вклад закрыт досрочно: проценты ({N}) сгорели»); term matured (time ≥ `matures_at`, even before the tick converted it): `amount + interest_accrued` |
| `POST …/bank/npc/{npc_id}/transfer` | `BankTransferIn` | `BankActionOut` | own **demand** deposit → own demand deposit in `to_region_id`; term → 400 «Срочный вклад нельзя перевести — дождитесь окончания срока или закройте его»; same bank → 400 «Вклад уже в этом банке»; destination disabled/missing → 409 «Банк региона «{name}» не принимает вклады»; `amount + fee` > deposit → 400 «На вкладе недостаточно средств с учётом комиссии {fee}»; commission → `T(X)` (the banker's region) |
| `POST …/bank/npc/{npc_id}/send` | `BankSendIn` | `BankActionOut` | recipient by exact name among players: none → 404 «Персонаж «{name}» не найден»; several → 409 «Найдено несколько персонажей с таким именем»; self → 400 «Нельзя перевести самому себе»; source `deposit` must be own demand deposit (any bank); destination = recipient's demand deposit in `to_region_id` (created if missing; recipient's `interest_base` unchanged); fee as transfer; response does **not** reveal the recipient's deposits |
| `POST …/bank/npc/{npc_id}/loan` | `BankLoanIn` | `BankActionOut` | bank disabled → 409 «Банк этого региона сейчас не выдаёт займы»; open loan → 409 «У вас уже есть займ — сначала погасите его» (also on `IntegrityError` of `uq_bank_loans_active`); overdue loan → 409 «Вы в списке должников — новые займы не выдаются» (only reachable via write-off race; kept explicit); amount > `loan_cap(level)` → 400 «Ваш лимит займа — {cap}»; amount > lendable → 409 «Банк сейчас может выдать не больше {lendable}» (0 → «У банка сейчас нет денег на займы»); rate/penalty fixed from params |
| `POST …/bank/npc/{npc_id}/repay` | `BankRepayIn` | `BankActionOut` | no open loan → 404 «Займ не найден»; accrue to now; `pay = min(amount, debt)`; wallet short → 400 «Недостаточно {genitive}»; debt 0 → `closed`, message «Займ погашен»; works at **any** banker (money goes to `B(L)`) and when the bank is disabled |
| `GET /characters/economy/bank/summary?character_id=` | — | `BankSummary` | JWT + ownership **or** `economy:read` admin; no banker, no gate |
| `GET /characters/economy/bank/regions` | — | `List[BankRegionOut]` | public: enabled banks `{region_id, name, country_name}` (transfer destinations) |

All POST handlers: one transaction; `InsufficientFunds` → 400 (message per flow); `DuplicateOperation` → 409
«Операция уже выполнена»; Pydantic errors → 422 (frontend maps to «Проверьте введённые данные»); commit then
`expire` the character so the response wallet is fresh. Logging: ids and amounts only.

### 3.10 Admin API (`economy_api.py`, new crud `economy_bank_crud.py` shared with 3.9/3.7)

| Method & path | Auth | Body → response |
|---|---|---|
| `GET /characters/admin/economy/banks` | `economy:read` | → `{items: [BankAdminItem], totals: {banks, enabled, own_funds, player_deposits, resident_deposits, player_loans_debt, resident_loans, debtors}}` — every `econ_banks` row + regions without a row are **not** listed (flag lives in the regions list) |
| `GET /characters/admin/economy/banks/{region_id}` | `economy:read` | → `BankAdminDetail` (item + open deposits ≤ 500 newest + open loans) ; 404 «Банк не найден» |
| `GET /characters/admin/economy/banks/debtors` (declared before `/{region_id}`) | `economy:read` | → `List[BankDebtorOut]` (active past due + overdue, debt desc) |
| `PUT /characters/admin/economy/banks/{region_id}` | `economy:settings` | `BankFlagIn {is_enabled, seed_capital=True}` → `BankAdminItem`; region must exist (404 «Регион не найден»); creates the row; first switch-on with `seed_capital` and `capital_seeded_at IS NULL` → `bank_capital` seed (3.2), `capital_seeded_at = now` (also when the treasury had 0 → seed 0, so re-toggling never seeds twice) |
| `POST /characters/admin/economy/banks/{region_id}/capital` | `economy:settings` | `BankCapitalIn {direction: in\|out, amount 1..1e9, comment 3..500}` → `{operation_id, bank_balance, treasury_balance}`; `in` > positive treasury → 400 «В казне региона только {N}»; `out` > lendable → 400 «Банк может вернуть не больше {N}» |
| `POST /characters/admin/economy/banks/loans/{loan_id}/write-off` | `economy:settings` | `BankWriteOffIn {comment 3..500}` → `BankLoanOut`; loan not open → 409 «Займ уже закрыт»; `written_off = debt`, `debt = 0`, `status = 'written_off'`, `active_character_id = NULL`, `closed_by_user_id`, `note` |
| `GET /admin/economy/regions` (changed) | as is | item + `bank_enabled: bool` |
| `POST /admin/economy/regions/fill` (changed) | as is (`settings` + `emit`) | `EconFillRequest.open_banks: StrictBool = True` → regions whose template ∈ `BANK_TEMPLATE_CODES = ("capital", "port")` get `is_enabled = 1` + one-time seed **after** the treasury top-up; response `+ banks_opened: List[int]` |
| `GET /economy/regions/{id}/card` (changed, public) | — | `+ has_bank: bool` |
| `GET /admin/economy/summary` (changed) | as is | `totals.banks`, `totals.bank_deposits`; `invariant.bank_deposits_expected` (Σ open rows `amount + interest_accrued`) vs `bank_deposits_actual` (Σ `V` balances) — part of `ok` |
| `GET/PUT /admin/economy/sim`, runs (changed) | as is | 20 bank params; run summary bank counters |

`economy_crud`: `REGION_ACCOUNT_KINDS += {bank, bank_deposits}`; `ADJUST_FORBIDDEN_KINDS += {bank, bank_deposits}`
(capital endpoint instead; vault must equal the rows); `EMISSION_TARGET_KINDS` unchanged (no emission into banks).

`BankAdminItem`: `region_id, region_name?, country_name?, enabled, simulated, bankers (alive NPCs with role banker
whose location resolves to the region), own_funds, vault, deposits_sum, vault_ok, deposits_count, term_count,
resident_deposits, resident_loans, reserve, lendable, loans_count, loans_debt, overdue_count, rate_factor,
demand_rate_day, term_rates [{term_days, rate_day}], capital_seeded_at?, last_tick_at?, last_stats: dict`.

### 3.11 Pydantic v1 schemas (`schemas.py`)

```python
BANK_TERMS = (7, 14, 28)
_BANK_REQ_ID = constr(regex=r"^[A-Za-z0-9-]{8,64}$")
_BANK_AMOUNT = conint(ge=1, le=1_000_000_000)

class BankDepositIn(BaseModel):
    character_id: conint(gt=0)
    kind: Literal["demand", "term"]
    term_days: Optional[int] = None          # validator: term -> in BANK_TERMS; demand -> must be None
    amount: _BANK_AMOUNT
    request_id: Optional[_BANK_REQ_ID] = None

class BankWithdrawIn(BaseModel):
    character_id: conint(gt=0)
    deposit_id: conint(gt=0)
    amount: Optional[_BANK_AMOUNT] = None    # demand: required (handler 400 «Укажите сумму»); term: ignored
    request_id: Optional[_BANK_REQ_ID] = None

class BankTransferIn(BaseModel):
    character_id: conint(gt=0)
    deposit_id: conint(gt=0)
    to_region_id: conint(gt=0)
    amount: _BANK_AMOUNT
    request_id: Optional[_BANK_REQ_ID] = None

class BankSendIn(BaseModel):
    character_id: conint(gt=0)
    source: Literal["wallet", "deposit"]
    deposit_id: Optional[conint(gt=0)] = None   # root validator: required iff source == 'deposit'
    recipient_name: constr(strip_whitespace=True, min_length=1, max_length=255)
    to_region_id: conint(gt=0)
    amount: _BANK_AMOUNT
    request_id: Optional[_BANK_REQ_ID] = None

class BankLoanIn(BaseModel):
    character_id: conint(gt=0)
    amount: _BANK_AMOUNT
    term_days: int                            # validator: in BANK_TERMS
    request_id: Optional[_BANK_REQ_ID] = None

class BankRepayIn(BaseModel):
    character_id: conint(gt=0)
    amount: _BANK_AMOUNT
    request_id: Optional[_BANK_REQ_ID] = None

class BankTermRate(BaseModel):
    term_days: int
    rate_day: float

class BankRatesOut(BaseModel):
    demand_rate_day: float                    # current (base x factor)
    term_rates: List[BankTermRate]            # for new term deposits
    loan_rate_day: float
    penalty_rate_day: float
    transfer_fee_rate: float
    transfer_fee_min: int
    min_amount: int

class BankDepositOut(BaseModel):
    id: int
    region_id: int
    region_name: Optional[str]                # None -> «удалённый регион»
    kind: str                                 # demand | term
    amount: int
    interest_accrued: int
    interest_total: int
    rate_day: Optional[float]                 # demand: current rate of its bank (0 when that bank is disabled)
    term_days: Optional[int]
    opened_at: datetime
    matures_at: Optional[datetime]
    matured: bool
    here: bool                                # in the banker's bank
    class Config: orm_mode = True

class BankLoanOut(BaseModel):
    id: int
    region_id: int
    region_name: Optional[str]
    status: str
    principal: int
    debt: int                                 # projected to now
    interest_total: int
    penalty_total: int
    paid_total: int
    collected_total: int
    rate_day: float
    penalty_rate_day: float
    term_days: int
    issued_at: datetime
    due_at: datetime
    overdue: bool
    class Config: orm_mode = True

class BankView(BaseModel):
    npc_id: int
    npc_name: str
    region_id: Optional[int]
    region_name: Optional[str]
    bank_enabled: bool
    rates: BankRatesOut                       # rates of this bank (factor 1 when no row)
    wallet: int
    deposits: List[BankDepositOut]            # ALL own open deposits, any bank, `here` first
    loan: Optional[BankLoanOut]
    debtor: bool
    loan_cap: int
    max_loan_now: int                         # 0 when disabled / has loan / debtor; else min(cap, lendable)
    loan_refusal: Optional[str]               # Russian reason when max_loan_now == 0
    bank_regions: List["BankRegionOut"]       # enabled banks (transfer destinations)

class BankRegionOut(BaseModel):
    region_id: int
    name: str
    country_name: Optional[str]

class BankActionOut(BaseModel):
    message: str                              # Russian, shown as a toast
    operation_id: Optional[int]
    wallet: int
    view: BankView

class BankSummary(BaseModel):
    character_id: int
    total_deposits: int                       # Σ amount + interest_accrued
    deposits: List[BankDepositOut]            # here = False
    loan: Optional[BankLoanOut]
    debtor: bool

class BankFlagIn(BaseModel):
    is_enabled: StrictBool
    seed_capital: StrictBool = True

class BankCapitalIn(BaseModel):
    direction: Literal["in", "out"]
    amount: _BANK_AMOUNT
    comment: str
    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)

class BankWriteOffIn(BaseModel):
    comment: str
    _comment = validator("comment", pre=True, allow_reuse=True)(_econ_comment)
```
Plus `BankAdminItem`, `BankAdminDetail` (`item`, `deposits: List[BankAdminDeposit]`, `loans: List[BankAdminLoan]` —
same fields as the player outs + `character_id`, `character_name`, `status`), `BankDebtorOut {loan_id, character_id,
character_name, region_id, region_name, debt, principal, due_at, overdue_days, penalty_total}`, `EconSummary`
totals/invariant fields (with defaults 0 for compatibility), `EconRegionItem.bank_enabled = False`,
`EconFillRequest.open_banks`, run summary counters. Validation messages in Russian (`_econ_comment` exists).

### 3.12 Deletions and degraded states

- **Character deletion** (`crud.post_character_deletion`, same transaction, first statements): lock banks of the
  character's open deposits and open loans (asc) → deposit rows → loan rows → existing `lock_characters`. Open
  deposits → `V(Y) → T(Y)` (`T(Y)` = `W` when `Regions` row of Y is gone) inside the **same** `character_deleted`
  operation as the wallet leg (legs list extended; posted when any leg > 0); rows `closed`, amounts 0. Open loan →
  `written_off` (bank's loss, no money). NPCs have no bank rows — no-op.
- **Region deleted** (locations-service unchanged): next tick purge (3.7 step 1). Until then player calls for that
  bank work as for a disabled bank (name shown as «удалённый регион»).
- **Flag removed / banker dead or removed / role changed**: deposits stay; withdraw at a living banker of that region
  (if any), or transfer to an enabled bank from any banker, then withdraw there. Loans can be repaid at any banker and
  are still collected.
- **Region leaves the simulation**: resident targets 0 → residents withdraw deposits and repay loans gradually; players
  unaffected.

### 3.13 Frontend

- **NPC role**: `src/constants/npc.ts` — `{ value: 'banker', label: 'Банкир' }`, icon `🏦` (admin NPC form picks it up).
- **Bank button**: `NpcProfileModal.tsx` — «Банк» button `npc.npc_role === 'banker' && isCharacterHere`, same markup
  as «Аукцион»/«Телепорт», opens `BankModal` (needs `characterId` from `state.user.character.id`).
- **Player bank modal** — new `components/pages/LocationPage/BankModal/`: `BankModal.tsx` (shell: header with banker
  avatar/name, region, «Банк закрыт» notice, wallet; tabs), `BankDepositsTab.tsx`, `BankLoanTab.tsx`,
  `BankTransfersTab.tsx`, `bankFormat.ts` (rate formatting: demand `«{rate×7×100} % в неделю»`, term `«{rate×term×100} %
  за {term} дней»`, Russian decimals); API `src/api/bank.ts`; types `src/types/bank.ts` (mirror 3.11). Tabs:
  - **Вклады**: «Здесь» — demand card (amount, interest earned, «Положить» / «Снять» with amount input + «Всё»),
    term cards (amount, accrued, matures date, «Забрать» when matured, «Закрыть досрочно» with a confirm stating
    burnt interest); «Открыть вклад» form (demand / term 7·14·28 with live projected interest); «В других банках» —
    list by region with «Перевести сюда» (amount + fee preview; hidden when this bank is disabled).
  - **Займ**: no loan → cap, available now, rate, 7/14/28 selector, amount with total-to-repay preview,
    `loan_refusal` text when 0; loan → debt, due date, overdue badge «Должник» (red error token of `tailwind.config.js` / design system), penalty
    total, «Погасить» (amount + «Всё»).
  - **Переводы**: «В другой банк» (own demand deposit → region select from `bank_regions`) and «Другому игроку»
    (source wallet / own demand deposit, recipient name, region select, amount, fee preview, confirm).
  - After every successful POST: replace state with `view`, toast `message`, `dispatch(fetchProfile(characterId))` →
    the existing `userSlice` matcher syncs the header balance. `request_id = crypto.randomUUID()` per submit
    (fallback: `Date.now()` + random hex ≥ 8 chars); buttons disabled while pending.
  - Every error toasted in Russian: server `detail` (string) as is; 422 → «Проверьте введённые данные»; no response →
    «Нет связи с сервером». Tailwind + design system (`modal-overlay`, `modal-content`, `gold-text`, `btn-blue`,
    `btn-line`, `input-underline`, `gray-bg`), 360 px (tabs scroll horizontally, cards stack), no `React.FC`.
- **Player summary — profile page** (`/profile` is own-only; it already shows the wallet; the public
  `UserProfilePage` and the header chip are not suitable — privacy / no room): new
  `components/ProfilePage/CharacterTab/BankSummary.tsx` rendered in `CharacterPanel.tsx` under the currency row:
  «Во вкладах: N» and «Долг: M» (when a loan exists) + «Должник» badge; click → small modal listing deposits by region
  (kind, amount, matures) and the loan (debt, due, bank). Read-only, hint «Операции — у банкира». Loads
  `GET /characters/economy/bank/summary`; error → Russian toast. Rendered only when the user has a character.
- **Admin «Экономика»**:
  - new tab **«Банки»** `EconomyBanks.tsx`: totals strip; table (desktop) / cards (mobile): region, «Банк есть»
    toggle (settings), bankers count (warning «нет банкира» when 0 and enabled), own funds / reserve / lendable,
    vault vs deposits (red «расхождение» when `!vault_ok`), resident deposits/loans, player loans/debt/overdue, rate
    factor and effective rates, last pass stats; expand → deposits + loans tables; actions «Капитал из казны» /
    «Вернуть капитал в казну» (dialog: amount + comment) and per loan «Списать долг» (comment); section «Должники»
    (`/banks/debtors`). Settings actions hidden without `economy:settings`.
  - `EconomyRegions.tsx` / `RegionEconomyEditor.tsx`: «Банк» badge + checkbox «Банк есть» (PUT banks flag; shows
    seeded capital in a toast).
  - `EconomyActions.tsx` fill dialog: checkbox «Открыть банки в столицах и портах» (default on) + `banks_opened` in
    the result.
  - `EconomyTick.tsx`: block «Банки» (20 params with hints, rates shown also as «% в день»), runs table column
    «Банки» (processed / failed / collected).
  - `EconomySummary.tsx`: totals «Банки (свои средства)», «Вклады игроков», invariant line «Вклады = хранилище».
  - `economyLabels.ts`: kinds `bank` «Банк региона», `bank_deposits` «Вклады игроков»; ops `bank_deposit` «Вклад в
    банк», `bank_withdraw` «Снятие со вклада», `bank_transfer` «Банковский перевод», `bank_tick` «Банк: проценты и
    жители», `bank_capital` «Капитал банка», `loan_issue` «Выдача займа», `loan_repay` «Погашение займа»,
    `loan_collect` «Взыскание долга»; leg `interest` «проценты». `src/types/economy.ts` (`EconAccountKind` + new
    types), `src/api/economyAdmin.ts`.
  - `components/WorldPage/RegionEconomyCard.tsx`: small «Банк» line when `has_bank`.

### 3.14 Data flow

```
Deposit:   BankModal → POST /characters/economy/bank/npc/{id}/deposit → JWT, owner, banker, lock, location
           → await locations /internal/action-gate → txn{ econ_banks(X) FOR UPDATE → demand row FOR UPDATE / insert
           → bank_deposit C→V(X) → row amount } COMMIT → BankActionOut → dispatch(fetchProfile) → header balance
Transfer:  … → txn{ econ_banks(A,B) → rows → bank_transfer V(A)→V(B), V(A)→T(X) commission (+10 % T(X)→country) }
Loan:      … → txn{ econ_banks(X) → loan check/insert (uq active) → loan_issue B(X)→C }
Tick:      run_tick: regions (unchanged) → _prepare_banks (orphans) → per bank txn{ econ_banks → deposits → loans →
           econ_bank.bank_step → rows → bank_tick legs } → per overdue loan txn{ banks → deposits → loan → char →
           loan_collect V(Y)→B(L), C→B(L) } → run row (+ bank counters)
Deletion:  DELETE /characters/{id} → post_character_deletion{ banks → deposits → loans → char → character_deleted
           C→T, V(Y)→T(Y) } → delete row → COMMIT
```

### 3.15 Security

- Player endpoints: JWT + ownership + player character + activity lock + banker role/alive + same location +
  FEAT-145 gate (fail-closed) ; ids `> 0`, amounts `1..1e9` (Pydantic + re-check before SQL), `term_days` whitelist,
  `request_id` regex, `recipient_name` ≤ 255 stripped and bound as a parameter (exact match, no LIKE). The view never
  shows the bank's cash beyond `max_loan_now`; other players' deposits are never returned; the summary is owner/admin.
- Money: only bank op types move `bank`/`bank_deposits`; both non-negative (ledger conditional update); vault ==
  rows checked by the summary invariant; loans only from `lendable`; collection never takes more than is there
  (no negative wallet); admin cannot `adjust` bank accounts; capital moves need `economy:settings` + comment; all
  SQL parameterised (`in_params`).
- Abuse: interest on the minimal balance (no tick-edge farming); loan interest to the minute; one loan per character
  (unique key); double submit → 409 via `request_id`; transfers cost a commission (no free laundering loop);
  battle-pass earn/spend missions ignore bank operations (3.16).
- Rate limit: existing nginx `/characters/` zone. Logs: ids and amounts only.

### 3.16 Cross-service effects

- **battle-pass-service** (`app/crud.py` `_ledger_gold_sum`): earn/spend missions count every posting into/out of a
  character account — deposit/withdraw or loan/repay cycling would farm them. Change `LEDGER_EXCLUDED_OP_TYPE`
  (`genesis`) to a tuple `LEDGER_EXCLUDED_OP_TYPES = ("genesis", "bank_deposit", "bank_withdraw", "bank_transfer",
  "loan_issue", "loan_repay", "loan_collect")` with `o.op_type NOT IN (…)` (comment: mirrors `econ_core.BANK_OP_TYPES`;
  battle-pass has no econ_core copy). Commission stays excluded too (small; documented).
- **locations-service**: no change (region delete leaves banks to the purge; shop untouched). The internal
  action-gate endpoint gets its first caller — update its docstring «No caller today» → character-service bank (doc
  only, optional).
- **Economy journal / accounts / summary**: new kinds/ops/leg labelled on the frontend; summary invariant extended.
- **Uncommitted FEAT-183 follow-ups** (`locations-service/app/{main,crud}.py`, `tests/test_npc_merchants.py`,
  `economyLabels.ts`, `NpcShopEditor.tsx`, `userSlice.ts`, docs) must be preserved — build on them, never revert.

### 3.17 Residual risks / out of scope (developers add to `docs/ISSUES.md`)

- No notification before a loan falls due / when it is collected (needs notification-service; future).
- A bank whose residents' deposits exceed its cash (residents withdraw more than it holds after heavy lending) pays
  residents partially (`resident_out` capped); players are unaffected (vault).
- Deposits of a deleted region's bank earn nothing and can only be transferred away.
- Recipient by name is ambiguous for duplicate names (409).
- Interest farming across many characters of one user is bounded only by the commission and rates.
- `bank_start_capital` taken right after the fill's treasury top-up lowers the treasury below its wage reserve
  (the next fill re-click tops it up again).

### 3.18 Deploy and migration ordering

One push. character-service `031_econ_banks` runs at start (auto-migration); the tick tolerates missing tables. No
other migrations. After deploy (local / prod): create banker NPCs (role «Банкир») in capitals/ports; «Заполнить
регионы» (with «Открыть банки…») or tick «Банк есть» per region; «Пересчитать сейчас» → `bank_tick` ops with
resident flows; summary «Сходится».

---

## 4. Tasks (filled by Architect, updated by PM — in English)

General for every task: **No commits, no pushes, no `git add`** (the user commits once at the end; a push to main
deploys to prod). The working tree holds **uncommitted FEAT-183 follow-ups** (`locations-service/app/main.py`,
`crud.py`, `tests/test_npc_merchants.py`, `docs/services/locations-service.md`, `docs/ISSUES.md`, `economyLabels.ts`,
`NpcShopEditor.tsx`, `userSlice.ts`) — build on them, never revert or overwrite. Backend: Pydantic v1,
`python -m py_compile` on modified files, existing tests stay green, docs `docs/services/character-service.md`
section «Banks (FEAT-184)» (incl. the lock order 3.8), residual risks of 3.17 into `docs/ISSUES.md`. Frontend:
`npx tsc --noEmit` and `npm run build` **inside the Docker frontend container** (no node on host), Tailwind + design
system (`docs/DESIGN-SYSTEM.md`), TypeScript, no `React.FC`, 360 px, every API error toasted in Russian. No prod access.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| B1 | **Shared contract (canonical):** `econ_core.py` per 3.4 (2 kinds in `ACCOUNT_KINDS`/`REF_KINDS`, factories, `SQL_ACCOUNT_NAME`, `KIND_BANK_DEPOSITS` in `TAX_SOURCE_KINDS`, 8 op types + `BANK_OP_TYPES`, `LEG_INTEREST` in both leg sets, module docstring); bank scenarios (a)–(f) in `tests/econ_contract_cases.py` and their runner lists in `test_econ_contract.py`. | Backend Developer | DONE | `services/character-service/app/econ_core.py`, `app/tests/econ_contract_cases.py`, `app/tests/test_econ_contract.py` | — | py_compile OK; character-service contract tests green; bank/vault debit above balance → `InsufficientFunds`; vault → treasury commission produces the 10 % country leg, `bank → treasury` does not |
| B2 | **Copies:** copy `econ_core.py` and `econ_contract_cases.py` verbatim into inventory-, locations-, dungeon-service; add the new case lists to their `test_econ_contract.py`. | Backend Developer | DONE | `services/{inventory,locations,dungeon}-service/app/econ_core.py`, `…/app/tests/econ_contract_cases.py`, `…/app/tests/test_econ_contract.py` | B1 | `sh scripts/check_econ_copies.sh` passes; contract tests green in all 4 services (dungeon with `--timeout=30`) |
| B3 | **Schema + pure maths:** migration `031_econ_banks` (3.3; FK indexes explicit, revision id ≤ 32 chars, downgrade drops tables) + ORM `EconBank`, `BankDeposit`, `BankLoan`; 20 bank params in `econ_sim.SimParams`, `ECON_SIM_PARAM_BOUNDS`, `EconSimParamsIn` (3.5); new pure `app/econ_bank.py` per 3.6 (dataclasses in/out, `accrue`, rates, reserve/lendable, loan cap, fee, `accrue_loan`, `prorata`, `plan_collection`, `rate_factor_next`, `bank_step`, legs builder). | Backend Developer | DONE | `services/character-service/app/alembic/versions/031_econ_banks.py`, `app/models.py`, `app/econ_sim.py`, `app/schemas.py`, new `app/econ_bank.py` | B1 | `alembic upgrade head` / `downgrade -1` / `upgrade head` on local MySQL OK, `SHOW CREATE TABLE` shows FKs + indexes; py_compile OK; a 120-pass loop (30 days) over a capital-like bank with players + residents keeps bank/purse ≥ 0, vault == Σ rows, reserve untouched, factor within bounds, debt ≤ 2 × principal |
| B4 | **Player bank API:** `economy_bank_crud.py` player part (banker resolution 3.9 in the fixed order, view, deposit, withdraw incl. early close / matured, own transfer, send to player, loan, repay, summary, enabled regions), `locations_client.check_npc_gate` (async, fail-closed), schemas 3.11 (player part), routes in `economy_api.py` under `/characters/economy/bank/…`, lock order 3.8, `request_id` idempotency, Russian errors exactly as 3.9. | Backend Developer | DONE | new `services/character-service/app/economy_bank_crud.py`, `app/economy_api.py`, `app/schemas.py`, `app/locations_client.py` | B2, B3 | curl on local (via :80): deposit demand + term, withdraw, early close burns interest (journal leg `interest` V→B), transfer to another bank with commission + 10 % country leg, send to another player by name, loan within cap, repay to 0 → closed; dead banker 409, wrong location 400, no post 403, locations down 503; double submit with the same `request_id` → 409; summary invariant `ok` |
| B5 | **Tick passes + deletion hook:** `_prepare_banks` (orphan purge), bank pass, collection pass (3.7) with locks per 3.8, `RunSummary` counters + `BANK_ERROR_PREFIX` parsing in the runs list; `crud.post_character_deletion` bank part (3.12); `econ_tick.py` docstring lock order. | Backend Developer | DONE | `services/character-service/app/econ_tick.py`, `app/economy_bank_crud.py` (tick helpers), `app/crud.py`, `app/economy_sim_crud.py` (runs list parsing if there) | B3, B4 | local: «Пересчитать сейчас» ×2 → one `bank_tick` per bank (interest B→V, resident flows P↔B), second manual run pays only minutes of interest; matured term converted/merged; overdue loan (due_at moved back in DB) → penalty, `loan_collect` from a deposit in another bank then wallet, wallet never < 0; rerun of the same run no-op; broken bank → other banks and regions still tick; deleting a character with deposits/loan → vault → treasury in `character_deleted`, loan written off; invariant `ok` |
| B6 | **Admin API + economy integration:** banks list/detail/debtors, flag PUT with one-time capital seed, capital in/out, loan write-off (3.10, `economy:read` / `economy:settings`); `fill_regions` `open_banks` (capital/port); regions list `bank_enabled`; region card `has_bank`; `economy_crud` summary totals + vault sub-invariant, `REGION_ACCOUNT_KINDS` / `ADJUST_FORBIDDEN_KINDS`; docs `character-service.md` «Banks (FEAT-184)» (tables, flows, postings 3.2, lock order 3.8, API); ISSUES (3.17). | Backend Developer | DONE | `services/character-service/app/economy_api.py`, `app/economy_bank_crud.py`, `app/economy_sim_crud.py`, `app/economy_crud.py`, `app/schemas.py`, `docs/services/character-service.md`, `docs/ISSUES.md` | B3, B4 | curl: flag on seeds capital once (re-toggle 0), capital out above lendable → 400, write-off clears «Должник», fill opens banks only for capital/port and reports `banks_opened`; 401 without token, 403 for a moderator on settings endpoints, moderator reads; summary shows banks/deposits and `ok` |
| B7 | **Battle-pass anti-abuse filter** (3.16): exclude the 6 bank op types from earn/spend ledger sums; small test update. | Backend Developer | DONE | `services/battle-pass-service/app/crud.py`, its existing gold-mission tests | — | py_compile OK; battle-pass pytest green; a deposit+withdraw pair does not change earn/spend progress |
| F1 | **Player bank modal** (3.13): banker role in `constants/npc.ts`, «Банк» button in `NpcProfileModal.tsx`, `BankModal/` (tabs Вклады / Займ / Переводы), `api/bank.ts`, `types/bank.ts`, header balance sync via `fetchProfile`, `request_id` per submit. | Frontend Developer | DONE | `src/constants/npc.ts`, `src/components/pages/LocationPage/NpcProfileModal.tsx`, new `src/components/pages/LocationPage/BankModal/*`, new `src/api/bank.ts`, new `src/types/bank.ts` | B4 contract (3.9, 3.11) | tsc + build pass; 360 px without horizontal overflow; header balance changes after a deposit; server texts toasted (403 gate, 409 loan refusals); early close asks for confirmation with the burnt interest |
| F2 | **Profile bank summary** (3.13): `BankSummary.tsx` in `CharacterPanel.tsx` (totals, «Должник» badge, detail modal). | Frontend Developer | DONE | new `src/components/ProfilePage/CharacterTab/BankSummary.tsx`, `CharacterPanel.tsx`, `src/api/bank.ts` (shared with F1) | B4 contract, F1 (api/types) | tsc + build pass; 360 px; hidden when there are no deposits and no loan; error toasted |
| F3 | **Admin «Банки» tab** (3.13): `EconomyBanks.tsx` (list, filters, expand, debtors, flag toggle, capital dialogs, write-off), tab in `EconomyPage.tsx`, labels in `economyLabels.ts`, types + API. | Frontend Developer | DONE | `src/components/Admin/EconomyPage/{EconomyPage,EconomyBanks}.tsx`, `economyLabels.ts`, `src/types/economy.ts`, `src/api/economyAdmin.ts` | B6 contract (3.10) | tsc + build pass; 360 px (mobile cards); actions hidden without `economy:settings`; journal shows «Банк: проценты и жители», «Взыскание долга», leg «проценты» |
| F4 | **Admin economy integration** (3.13): «Банк есть» in `EconomyRegions.tsx` / `RegionEconomyEditor.tsx`, fill option in `EconomyActions.tsx`, «Банки» params block + run column in `EconomyTick.tsx`, summary lines in `EconomySummary.tsx`, «Банк» line in `RegionEconomyCard.tsx`. | Frontend Developer | DONE | `src/components/Admin/EconomyPage/{EconomyRegions,RegionEconomyEditor,EconomyActions,EconomyTick,EconomySummary}.tsx`, `src/components/WorldPage/RegionEconomyCard.tsx`, types/API from F3 | B6 contract, F3 | tsc + build pass; 360 px; toggling the flag toasts the seeded capital; 20 params editable within bounds |
| Q1 | **QA contract + pure maths:** shared bank cases run in all 4 services; `test_econ_bank.py` — `accrue` rounding/carry, rates × factor, reserve/lendable, loan cap, fee ceil/min, `accrue_loan` across `due_at` and the debt cap, `prorata` (short bank, zero), `plan_collection` order and limits, `rate_factor_next` bounds/smoothing, `bank_step` guarantees (never negative, vault delta = Σ player pays, maturity convert vs merge, min-balance rule, disabled bank pays nothing and winds residents down, determinism, inputs not mutated, random worlds). | QA Test | DONE | `services/*/app/tests/test_econ_contract.py` (if needed), new `services/character-service/app/tests/test_econ_bank.py` | B1, B2, B3 | pytest green in all 4 services; copies check passes |
| Q2 | **QA player API:** every endpoint of 3.9 with mocked gate (open / closed / transport error), banker checks in order (missing, wrong role, dead, other location, activity lock), ownership 401/403/404, disabled bank, min amounts, term whitelist, early close vs matured, other-bank withdraw refusal, transfer fee + tax leg, send to player (not found / ambiguous / self / NPC), loan cap / lendable / one-loan unique / debtor, repay partial/full, `request_id` duplicate, summary owner vs admin, invariant after each money scenario, security cases (SQL-like names, huge/negative/zero amounts, wrong types → 422). | QA Test | DONE | new `services/character-service/app/tests/test_econ_bank_api.py` | B4 | pytest green; each test < 30 s |
| Q3 | **QA tick, deletion, admin:** bank pass on SQLite (one `bank_tick` per bank, time-based accrual: second run pays minutes only, idempotent rerun, failure isolation, non-simulated bank still accrues, orphan purge), collection pass (other-bank deposit then wallet, never negative, closes loan), deletion hook (vault → treasury in `character_deleted`, loan written off, deleted region → world), admin API RBAC (read vs settings, moderator), flag seed once, capital bounds, write-off, fill `open_banks`, summary vault sub-invariant (drift detected); battle-pass exclusion test (B7) if not covered there. | QA Test | DONE | new `services/character-service/app/tests/test_econ_bank_tick.py`, `test_econ_banks_admin_api.py` | B5, B6 (B7) | pytest green; whole character-service suite well under CI limits |
| R1 | **Review + live on local:** 4 copies identical, lock order 3.8 in every flow, security checklist, py_compile / pytest (character, inventory, locations, dungeon, battle-pass) / tsc / build re-run; **live**: create a banker in a capital, open bank via fill or flag, as a player: demand + term deposit, withdraw, early close, transfer to another bank, send to another player, loan + partial repay; «Пересчитать сейчас» → interest/resident flows; force a due date into the past → collection + «Должник» in profile and admin; delete a test character with deposits; summary «Сходится»; 360 px for the bank modal, profile summary, «Банки» tab; zero console errors. | Reviewer | TODO | all | B1–B7, F1–F4, Q1–Q3 | Checklist passed, invariant `ok` after the live scenario |

Parallelism: B1 first; B2 and B3 after B1 (parallel); B7 any time; B4 after B2 + B3; B5 and B6 after B4 (parallel,
both touch `economy_bank_crud.py` — B5 owns the tick helpers section, B6 the admin section; run sequentially if one
agent). F1 can start from the 3.9/3.11 contract (live check after B4); F2 after F1's api/types; F3 from 3.10 (live
after B6); F4 after F3. Q1 after B3, Q2 after B4, Q3 after B5 + B6. R1 last.

---

## 5. Review Log (filled by Reviewer — in English)

### R1 — 2026-10-29 — **PASS** (no blocking findings)

Scope: the whole uncommitted diff (FEAT-184 + the FEAT-183 follow-ups: dead merchant = closed shop in
locations-service `main.py:2710-2716` / `crud.py:4568,4688`; header balance matcher in `userSlice.ts:204-214` —
both correct, verified live for the bank flows).

#### Money flows / invariants — OK
- Every flow matches 3.2: deposit `C→V`, withdraw `V→C` (+ early close `V→B` interest, matured `B→V` final
  interest then `V→C`), transfer/send `V(A)→V(B)` + commission to `T(X)` (taxed via `TAX_SOURCE_KINDS`),
  loan `B→C`, repay `C→B(L)`, tick `B↔V/P` with `apply_tax=False`, collection `V(Y)→B(L)` + `C→B(L)`, deletion
  `V(Y)→T(Y)|W` inside `character_deleted`. Each row change of a vault is mirrored by exactly one leg; summary
  sub-invariant `bank_deposits_expected == actual` is part of `ok` (`economy_crud.py:185-197`).
- Reserve rule holds by construction: player deposits live in `bank_deposits` (never lent, never debited for
  interest); loans/interest/capital-out use `lendable(bank)` only (`economy_bank_crud.py:792,990,1502`).
- Live after every scenario: world sum 0, invariant `ok`, vault == Σ open rows (1340 → 2036).

#### Specific questions
- **Q3 «factor stays 0.8»**: with no loan income and deposits owed, the target factor is `bank_rate_factor_min`
  (0.2); the old per-run smoothing moved 25 % of the gap per call → `1 − 0.25 × 0.8 = 0.8` on *every* manual run,
  even seconds apart. Now `rate_factor_next` uses `time_weight(smoothing, seconds)` and `_round_step` truncates
  short runs (`econ_bank.py:102-132, 387-407`); `bank.accrued_at` is advanced every pass
  (`economy_bank_crud.py:1078`). Live: two «Пересчитать сейчас» 1 s apart — run 1 moved region 9 0.6500 → 0.6392
  (≈30 min elapsed), run 2 changed nothing and posted no `bank_tick` (0 ops). Fixed.
- **Recipient by name vs MySQL collation**: `characters.name` is `utf8mb4_0900_ai_ci` → case- **and**
  ё/е-insensitive (live: «годрик» → Годрик). Acceptable and player-friendly; the ambiguity refusal still works
  because `LIMIT 3` counts all collation matches (`economy_bank_crud.py:697-702`). Consequence: names that differ
  only by case/ё become unaddressable (409) — already in ISSUES (risk 4). Non-blocking notes below.
- **Matured term withdraw (B5) vs tick**: no double pay. Both paths hold `econ_banks(X) FOR UPDATE`; the withdraw
  pays `[accrued_at, matures_at)` and closes the row (`economy_bank_crud.py:620-640, 979-991`); if the tick ran
  first it already paid up to `min(now, matures_at)`, set `accrued_at = now ≥ matures_at` and converted the row to
  demand, so the withdraw takes the demand path. Live: withdraw 1 day after maturity paid 1002 (1000 + 2), the
  other term was paid 2 by the tick and merged — `interest_total` 2 each.

#### Lock order 3.8 — OK, no cycle found
deposit/withdraw/loan (`econ_banks(X)` → row → `lock_characters` → ledger), transfer/send (banks asc → rows asc,
new row last → char → accounts), repay/write-off (bank(L) → loan → char), bank pass (bank → deposits → loans →
accounts; never characters), collection (banks {L ∪ deposit banks} asc → deposits → loan → char), deletion hook
(banks → deposits → loans before `lock_characters`, `crud.py:2448-2477`), fill (`lock_banks` before postings,
`economy_sim_crud.py:362-363`). Player flows never lock `econ_regions`; banks run outside the region txn.

#### Idempotency / security — OK
`request_id` → ledger key, checked after the bank lock (live duplicate → 409), tick keys per run/bank/loan +
`last_run_id` guard, seed key `bank_capital:r:X:seed` + `capital_seeded_at` (live: on/off/on seeded once, 1520 =
whole treasury). JWT + ownership + player-only + banker role/alive + activity lock + location + FEAT-145 gate
fail-closed (live: no post → 403) awaited with no open transaction; amounts `conint(strict, 1..1e9)` (live −5 →
422), parameterised SQL / `in_params`; admin reads `economy:read`, changes `economy:settings`; bank kinds
forbidden for `adjust`; logs ids/amounts only. Pydantic v1 everywhere. Migration 031: InnoDB, explicit FK indexes,
`IF NOT EXISTS`, downgrade drops children first, revision id 14 chars; local MySQL at `031_econ_banks`.
battle-pass excludes the 8 bank op types with bound params. Frontend: TS, Tailwind + design-system classes, no
`React.FC`, `useCurrency` for amounts, every error toasted in Russian, `skipForbiddenToast` for game-rule 403s.

#### Non-blocking notes (no fix required for this feature)
1. `economy_bank_crud.py:765` — the send message echoes the typed `recipient_name` («годрик получит …»); use the
   DB name of the recipient. Docs 3.9/`character-service.md` say «exact name» — say «без учёта регистра и ё».
2. `BankDepositsTab.tsx` — the matured term button says «Забрать 1 000 ṃ», the payout includes the last
   partial-period interest (1002). Cosmetic.
3. Race (LOW): `send` to a recipient who is being deleted at the same moment can create an open deposit row for
   the deleted character (the deletion hook only locks banks where he already had positions). Invariant stays
   `ok`, the money sits in the vault. Worth an ISSUES line.
4. Admin «Банки» → «Последний пересчёт» shows the stats of the latest pass only; a manual run seconds after a
   real one shows «движения не было». Cosmetic.
5. Trivial typo fixed by the reviewer: `econ_tick.py:872` `error ="; "` → `error = "; "`.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (no output besides the known EffectRunes filter)
- [x] `vite build` (frontend container) — PASS
- [x] `py_compile` — PASS (character 13 files incl. migration, locations 3, battle-pass 1)
- [x] pytest character-service — PASS (exit 0, 2946 passed, 1 skipped, 194 s)
- [x] pytest inventory — PASS (exit 0, 2099 passed); locations — PASS (exit 0, 2211 passed); dungeon
  (`--timeout=30`) — PASS (exit 0); battle-pass — PASS (exit 0, 164 passed)
- [x] `scripts/check_econ_copies.sh` — PASS (all copies identical)
- [x] `docker compose config` — PASS
- [x] Live verification — PASS

#### Live Verification Results (local stack, http://localhost; never prod)
- Setup: banker NPC «Банкир Ревизор R1» (id 1000001) in location 1183 (region 15 Хикари, not the B5 region 9);
  `PUT /admin/economy/banks/15` on/off/on → seeded once (1520 ṃ, the whole treasury). Character 765
  «Проверка FEAT155» (admin's own test character, made current for the UI). FEAT-145 gate: first POST without a
  gate → 403 with the shop text; then an `action_gates` row (`npc_dialogue`, target = banker, open) was inserted
  in SQL — the same row a «Диалог с НПС» post creates.
- API through the gateway: demand 1000, duplicate `request_id` 409, term 7 d 500, withdraw 200, withdraw 5 → 400
  «Минимальная сумма — 10», early close, transfer 100 → Мэттанхейм (fee 2), send 50 from wallet to «Годрик», send
  20 from deposit to «годрик», self → 400, unknown → 404, loan 300, second loan 409, repay 100, repay all
  «Займ погашен», summary, debtors list (due date moved back in SQL → «Должник», debt 306 incl. 3 penalty).
- UI (Chrome): location → НПС → banker profile «Банк» → modal (deposits, «Должник» badge, rates), «Забрать» on a
  matured term → toast «Срочный вклад забран: 1002 марки», header balance 97 904 → 98 906 without reload; «Займ»
  and «Переводы» tabs; `/profile` «Во вкладах 1 777 ṃ / Долг 306 ṃ / Должник» + detail modal; admin «Экономика»
  summary («Сходится», bank cards) and «Банки» tab (both banks, flags, rates, «банкиров: 1»). 360 px checked in a
  360-px iframe: location page `scrollWidth` 345, bank modal 313 px wide, no element overflow on all three tabs.
  Console errors: none.
- «Пересчитать сейчас» ×2: run 1 — 2 banks, 2 `bank_tick`, interest 2, matured+merged 1, loan collected 306 from
  the demand deposit (loan closed); run 2 (1 s later) — 0 ops, factor unchanged. Invariant `ok` throughout.
- Local test data left (dev DB only): bank row of region 15 (enabled, own funds ≈ 1527) with deposits of 765
  (demand 1373 in 15, 100 in 9) and of «Годрик» 764 (70 in 15); closed loans 2–3, closed term rows; ledger ops.
  Removed: banker NPC 1000001 (admin delete), gate row 183; `users.current_character` of user 4 restored to 763.

---

## 6. Logging (all agents — in Russian)

```
[LOG] 2026-10-29 — PM: фича создана, требования согласованы с пользователем («Делай как рекомендуешь»), запускаю анализ кодовой базы
[LOG] 2026-10-29 18:53 — Analyst: анализ завершён — рекомендован character-service как владелец банков; затронуты character-, locations-service, все 4 копии econ_core, фронтенд (user-service только при новых правах); найдены риски дедлоков в тике и 5 открытых вопросов
[LOG] 2026-10-29 19:45 — Architect: спроектирован этап 4 (разделы 3–4): банки целиком в character-service (3 новые таблицы, миграция 031); у банка два счёта — свои деньги и хранилище вкладов игроков (вклады никогда не идут в займы, всегда снимаемы); начисление по времени; отдельные проходы банков и взыскания после пересчёта регионов, общий порядок блокировок расширен; новые виды счетов/операций в econ_core (×4); 20 параметров; новых прав нет; фильтр банковских операций в заданиях боевого пропуска. 16 задач (7 backend, 4 frontend, 3 QA, ревью), 5 вопросов пользователю с рекомендациями
[LOG] 2026-10-29 20:30 — Backend Dev: B1 готово — в econ_core (канон, character-service) добавлены счета bank / bank_deposits (по региону, без минуса; вклады — источник налога), 8 банковских операций + BANK_OP_TYPES, нога interest; 10 банковских сценариев контракта + проверки констант; три старых теста использовали «bank» как несуществующий вид счёта — заменён на unknown_kind. Тесты character-service: 2679 passed. Копии в 3 других сервиса — задача B2 (до неё CI-проверка копий красная)
[LOG] 2026-10-29 — Backend Dev: B7 готово — в battle-pass-service задания «заработать/потратить золото» больше не считают банковские операции (вклады, снятия, переводы, займы, погашения, взыскания; плюс bank_tick/bank_capital для полноты), фильтр NOT IN на связанных параметрах; 5 новых тестов, pytest 164 passed
[LOG] 2026-10-29 — Backend Dev: B3 готово — миграция 031_econ_banks (econ_banks, bank_deposits, bank_loans; явные индексы под FK, CHECK-и) применена/откачена/применена на локальной MySQL; ORM-модели EconBank/BankDeposit/BankLoan; 20 параметров bank_* в SimParams, границах и схеме админки; чистый модуль econ_bank.py (начисление по времени с переносом остатка, ставки, резерв, лимит займа, комиссия, пени с потолком 2× долга, пропорциональная выплата, план взыскания, фактор ставки, полный шаг банка и проводки). Отличие от 3.6: жители двигаются к цели с округлением от нуля (иначе сворачивание застревает на мелочи). 13 базовых тестов в test_econ_bank.py (вкл. 120 проходов = 30 дней); тесты character-service: 2717 passed
[LOG] 2026-10-29 — Backend Dev: B2 готово — econ_core.py и econ_contract_cases.py скопированы байт-в-байт в inventory-, locations-, dungeon-service (check_econ_copies.sh зелёный); в их test_econ_contract.py добавлены test_bank_account_kinds и test_bank_op_types_and_interest_leg; старых тестов с «bank» как неизвестным видом счёта в этих сервисах не нашлось. pytest: inventory 2099 passed, locations 2211 passed, dungeon exit=0
[LOG] 2026-10-29 — Frontend Dev: F1 готово — роль НПС «Банкир» (🏦), кнопка «Банк» в профиле банкира, окно банка BankModal/ (вкладки «Вклады» / «Займ» / «Переводы»: пополнение и снятие вклада до востребования, срочные 7/14/28 с прогнозом дохода, досрочное закрытие с подтверждением о сгоревших процентах, «Перевести сюда» из других банков, займ с превью суммы к возврату, погашение частями, переводы в другой банк и другому игроку с комиссией и подтверждением), api/bank.ts + types/bank.ts (включая summary для F2), request_id на каждую отправку, после операции fetchProfile → баланс в шапке. Все ошибки — тостом по-русски (403 гейта — текст сервера). tsc и build в Docker зелёные; живая проверка — после B4
[LOG] 2026-10-29 — Frontend Dev: F3 готово — вкладка «Банки» в админской «Экономике» (EconomyBanks.tsx): сводка по банкам, поиск и фильтр (работают / закрыты / есть должники / требуют внимания), таблица на широком экране и карточки на мобильном, переключатель «Банк есть» (закрытие с подтверждением), «Открыть банк в регионе» с опцией стартового капитала, раскрытие банка → вклады и займы игроков, «Капитал из казны» / «Вернуть капитал в казну», «Списать долг», раздел «Должники»; действия скрыты без economy:settings. Типы и API — в types/economy.ts и api/economyAdmin.ts; в economyLabels.ts добавлены виды счетов bank / bank_deposits, 8 банковских операций и нога «проценты». tsc чистый, сборка проходит; живая проверка — после B6
[LOG] 2026-10-29 — Backend Dev: B4 готово — API игрока банка в character-service: окно банка у банкира (GET), вклад до востребования/срочный, снятие (досрочное закрытие сжигает проценты ногой interest в банк), перевод своего вклада в другой банк и отправка игроку по имени (комиссия сверх суммы в казну региона банкира, налог 10 % в страну), займ в пределах лимита уровня и свободных денег банка, погашение частями у любого банкира, сводка по всем вкладам, список открытых банков. Проверки банкира в порядке 3.9, гейт FEAT-145 через внутренний эндпоинт locations-service (закрыт по умолчанию, без открытой транзакции), порядок блокировок 3.8, request_id → 409 на повтор. Контракт совпадает с F1 (api/bank.ts, types/bank.ts). Новый economy_bank_crud.py с разделами под тик (B5) и админку (B6); тесты test_econ_bank_api.py — 19 шт.; character-service: 2770 passed; живая проверка: /bank/regions, /bank/summary, реальный вызов гейта (ответ false без поста)
[LOG] 2026-10-29 — Frontend Dev: F4 готово — в «Регионах» значок «Банк» у регионов с банком; в «Заполнить регионы по шаблонам» галочка «Открыть банки в столицах и портах» (по умолчанию включена) и список открытых банков в итоге (диалог заполнения живёт в EconomyRegions.tsx, EconomyActions.tsx менять не пришлось — банковские счета и так не попадают в эмиссию/корректировку); в редакторе региона новый блок «Банк» (RegionBankPanel.tsx): галочка «Банк есть», опция стартового капитала, закрытие с подтверждением, тост с полученным капиталом, цифры банка — без сброса несохранённых правок региона; в «Пересчёте» блок «Банки» (20 параметров с подсказками, ставки дополнительно в «% в день / в неделю / за срок»), колонка «Банки» в истории и банковские счётчики в итоге ручного пересчёта; в сводке карточки «Банки (свои средства)», «Вклады игроков» и строка «Вклады = хранилище»; на карточке региона в мире строка про банк при has_bank. tsc чистый, сборка проходит; живая проверка — после B6
[LOG] 2026-10-29 — QA: Q1 готово — test_econ_bank.py расширен до 47 тестов (матрица accrue/ставок/резерва/потолка/комиссии, займ через срок и потолок долга, prorata, порядок взыскания, фактор ставки, bank_step: сроки/слияние/резерв/жители/выключенный банк/повторный запуск, 400 случайных миров); банковские кейсы контракта зелёные во всех 4 сервисах, копии идентичны. Найден и исправлен баг в econ_bank.rate_factor_next: из-за округления q4 HALF_UP фактор «застревал» на 0,0001–0,0002 от цели (после падения не возвращался к 1,0000) — шаг теперь округляется от нуля, без перескока цели.
```
[LOG] 2026-10-29 — Frontend Dev: F2 готово — сводка банка в профиле (панель «Персонаж», под строкой с марками): «Во вкладах: N», «Долг: M» (красным при просрочке) и метка «Должник»; клик — окно со списком вкладов по регионам (вид, сумма, начислено, срок) и займом (долг, вернуть до, пени, банк), подсказка «Операции — у банкира». Скрыта, когда нет ни вкладов, ни займа; ошибка загрузки — тостом по-русски. tsc и build в Docker зелёные; живая проверка — после B4
[LOG] 2026-10-29 — Backend Dev: B5 готово — банки в 6-часовом пересчёте после регионов, каждый шаг в своей транзакции: закрытие банков удалённых регионов (деньги банка → Казна Скитальцев, займы списаны), проход банка (econ_bank.bank_step, одна операция bank_tick на банк, защита last_run_id), взыскание просроченных займов (вклады в любых банках → кошелёк, не в минус; loan_collect); 9 счётчиков в RunSummary, BANK_ERROR_PREFIX, в списке запусков bank_ops_posted / bank_failures / loans_collected; удаление персонажа выплачивает вклады в казну (или в Казну Скитальцев для удалённого региона) в той же операции character_deleted и списывает займ; снятие созревшего срочного вклада до тика теперь доплачивает проценты последнего периода. 14 тестов в test_econ_tick_banks.py; ручной пересчёт на локальной MySQL ×2 (жители, взыскание, сумма мира 0). В ISSUES.md — фактор ставки сглаживается за запуск, а не за время
[LOG] 2026-10-29 — Backend Dev: B6 готово — админ-API банков (список с итогами, карточка банка с вкладами и займами, должники, флаг «Банк есть» с разовым стартовым капиталом из казны, капитал из казны/в казну с проверкой резерва, списание долга), «Заполнить регионы» открывает банки в столицах и портах (banks_opened), bank_enabled в регионах, has_bank в карточке региона, в сводке банки/вклады и проверка «вклады = хранилище», банковские счета запрещены для корректировки. bankers — список {npc_id, name}, должники — простой список. Новый test_econ_banks_admin_api.py (25 тестов), поправлены ожидания формы в 3 старых тестах; character-service: 2925 passed; живая проверка через шлюз на локальной БД (401, флаг, капитал, 400 сверх lendable, карточка, сводка ok) — тестовая строка банка удалена. Документация «Banks (FEAT-184)» и риски 3.17 в ISSUES.md
[LOG] 2026-10-29 — QA: Q2 готово — test_econ_bank_api.py расширен с 19 до 135 тестов: 401/403/404 и чужой персонаж во всех операциях, НПС как игрок, порядок проверок банкира (владелец → банкир → мёртв → блокировка → локация → гейт → регион), гейт на каждом POST (закрыт 403 / недоступен 503) и сам клиент check_npc_gate (обрыв, таймаут, не-200, кривой ответ — всё отказ), 43 случая 422 (дробные/логические/строковые числа, ноль, минус, огромные суммы, SQL-подобные строки), SQL-подобные имена получателя, повтор request_id → 409 во всех шести операциях, отключённый банк и банк без строки, правило резерва (снятие вкладов при пустом банке, резерв жителей не выдаётся, вклады игроков не выдаются займами), математика комиссии и налога 10 %, один займ на персонажа между банками, гашение у любого банкира, проценты по займу «до минуты», просрочка → «Должник» и потолок долга ×2; после каждого денежного сценария — сумма мира 0 и хранилище = открытые вклады. Багов в коде B4 не найдено.
[LOG] 2026-10-29 — Backend Dev: исправлен баг B5 — фактор ставки и движение жителей теперь зависят от прошедшего времени (1 − (1 − доля)^периоды, догон не больше суток); пересчёт через секунды больше не роняет фактор 1,0 → 0,8 и не двигает жителей на 1 монету, на ровно 6 ч всё как раньше. Тесты в test_econ_bank.py (подряд идущие запуски, две половины = период, ограничение долгого простоя), 3 старых ожидания для простоя в сутки пересчитаны; запись удалена из ISSUES.md
[LOG] 2026-10-29 — QA: Q3 готово — test_econ_tick_banks.py +10 тестов (повторные ручные пересчёты не двигают фактор, два полупериода ≈ один, долгий простой догоняет не больше суток для фактора и жителей, проценты за весь простой; взыскание из трёх банков включая выключенный, пустой кошелёк, списанный займ не взыскивается; удаление персонажа с пустым кошельком и вкладами в трёх банках включая удалённый регион + последующая очистка банка-сироты), test_econ_banks_admin_api.py +7 (роль admin/user без прав, посев один раз при переключениях и заполнении, посев из пустой казны, вывод капитала не больше доступного и без вкладов игроков, списание текущего займа, банки только в столицах/портах с жителями, «Пересчитать сейчас» → счётчики банков в ответе и в списке запусков). Сумма мира = 0 и хранилище = открытые вклады после каждого сценария. Багов не найдено. Весь набор character-service зелёный.
[LOG] 2026-10-29 21:40 — Reviewer: R1 — PASS. Проверены проводки, порядок блокировок, идемпотентность, безопасность, миграция 031, копии econ_core, фильтр боевого пропуска, фронтенд; все тесты (character, inventory, locations, dungeon, battle-pass), tsc и сборка зелёные. Живая проверка на локальном стенде: банкир в Хикари, вклады, снятие, досрочное закрытие, перевод, отправка игроку, займ, погашение, просрочка → «Должник» → взыскание, «Пересчитать сейчас» дважды (фактор не скачет), сводка «Сходится», ошибок в консоли нет. Блокирующих замечаний нет, 4 мелких — в разделе 5; исправлена опечатка в econ_tick.py

---

## 7. Completion Summary (filled by PM on close — in Russian)

**Сделано (2026-10-29):** банк региона — вклады до востребования и срочные (7/14/28 дн.), займы с пенями и мягкой
просрочкой («Должник», автосписание с вкладов и кошелька), перевод вклада в другой банк и перевод другому игроку с
комиссией в казну. Доступ через НПС-банкира (новая роль «Банкир», кнопка «Банк», гейт поста как у лавки). Банк живёт
и без игроков: жители держат вклады и берут займы в 6-часовом пересчёте. Деньги игроков лежат в отдельном
хранилище и никогда не выдаются в займы — снять вклад можно всегда. Ставки сами снижаются, если банк мало
зарабатывает; изменения ставки и жителей идут по прошедшему времени (двойной ручной пересчёт ничего не ломает).

- character-service: миграция `031_econ_banks` (3 таблицы), `econ_bank.py` (чистая математика), `economy_bank_crud.py`,
  игровой и админский API банков, три прохода банков в тике, хук удаления персонажа, 20 параметров «Банки».
- `econ_core.py` ×4: виды счетов `bank` / `bank_deposits`, 8 типов операций, нога `interest`.
- battle-pass: банковские операции не считаются в заданиях «заработай/потрать».
- frontend: окно банка (Вклады / Займ / Переводы), сводка в профиле, вкладка «Банки» в админке, галочка «Банк есть»,
  открытие банков при «Заполнить регионы», блок параметров, сводка и карточка региона.
- Тесты: character 2946, inventory 2099, locations 2211, dungeon, battle-pass 164 — всё зелёное; ревью PASS с живой
  проверкой на локальном стенде.

**Остаточные риски:** `docs/ISSUES.md` → «Банки: остаточные риски (FEAT-184)».
**После выкатки на прод:** назначить роль «Банкир» нужным НПС, включить банки (галочка или «Заполнить регионы»).
