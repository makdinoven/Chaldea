# FEAT-181: Экономика мира

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-10-29 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-181-world-economy.md` → `DONE-FEAT-181-world-economy.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Экономика мира сейчас мертва: золото существует только у игроков. Траты игроков (комиссия аукциона,
налог на дом, стройка, телепорт, покупки у НПС) просто исчезают, а награды (квесты, данжи, продажа
НПС) появляются из ничего. У торговцев НПС нет ни денег, ни живого склада. Банков, вкладов и кредитов нет.

Цель — золото с весом: каждая монета где-то лежит, мир живёт сам (игроков мало, экономика не может
держаться на них), а игроки на неё влияют.

### Общая модель (все этапы)
- **Закон сохранения золота.** Всё золото лежит на счетах: игрок, кошелёк населения региона, касса
  торговца, банк региона, казна региона, казна страны. Деньги только переходят со счёта на счёт
  (двойная запись: у каждой операции «откуда → куда»).
- **Эмиссия только из двух кранов**, оба кладут в казну страны: монетный двор (чеканка из золотой руды)
  и фиксированная квота на игровой месяц.
- **Казны:** у каждого региона своя казна; регион платит налог в казну своей страны. Сейчас 4 игровые
  страны, их число будет расти.
- **Экономическая единица — регион** (обычно в регионе один крупный город или большая деревня, иногда
  несколько; бывают регионы только из мелких деревень). Несколько поселений региона — одна экономика.
- **Симуляция региона** раз в 6 реальных часов: население, достаток, стабильность, налоговая ставка,
  12 групп товаров (продовольствие, руда и металл, древесина, травы и реагенты, шкуры и ткани,
  магические материалы, оружие, броня и одежда, украшения, зелья, ремесленный инвентарь, быт и мебель),
  производство/потребление/запас/норма/цена по каждой группе, шаблоны регионов. Свитки, рецепты,
  квестовые предметы и всё легендарное+ — вне рынка, по фиксированной цене.
- **Банк** в каждом регионе, где есть город: вклады (процент из доходов по кредитам), кредиты (просрочка
  пока мягкая: пени, долг на персонаже, запрет новых займов — без изъятия дома/вещей), перевод вклада
  между банками с комиссией в казну.
- **Название валюты** — настройка, а не захардкоженное «золото»: лорный администратор планирует другую
  валюту.
- Влияния игроков на казну (наместники и т.п.) пока нет — возможно в будущем.

### Этапы
1. **Фундамент (этот этап):** счета, двойная запись, казны регионов и стран, все существующие траты и
   выплаты идут через казну, название валюты — настройка, админ видит, где лежит всё золото мира.
2. Регион оживает: население, группы товаров, запасы, цены, тик 6 ч, шаблоны, карточка региона.
3. Торговцы НПС: касса, склад, цены от региона, фоновая торговля.
4. Банк: вклады, кредиты, переводы.
5. Монетный двор, караваны, заказы, события.

### Бизнес-правила этапа 1
- Каждое изменение баланса игрока — проводка между двумя счетами; сумма золота в мире меняется только
  эмиссией (и, на время перехода, явной админской корректировкой).
- Траты игроков уходят в казну региона, где они произошли (комиссия аукциона, налог и стройка дома,
  покупка дома/участка, телепорт, покупки у НПС, расходы в данжах и т.д.).
- Выплаты игрокам (награды квестов, золото из данжей, продажа НПС, стартовый набор) берутся из казны
  региона. Если в казне не хватает денег — поведение решает Architect (вероятно: на этапе 1 казна
  может уйти в минус/получить дотацию страны, чтобы не ломать игру до запуска симуляции).
- Регион отчисляет налог в казну страны.
- Стартовые казны заполняются начальной эмиссией (размер задаёт админ).
- Сделки игрок↔игрок (обмен, аукцион без комиссии) — прямой перевод между счетами игроков.
- Название валюты — одна настройка; весь пользовательский текст про валюту берёт его оттуда.
- Админ: сводка «где золото мира» (игроки / казны регионов / казны стран / прочее), журнал проводок,
  ручная эмиссия и корректировка (с разрешениями RBAC).

### UX / Пользовательский сценарий
1. Игрок почти ничего не замечает: баланс, покупки, награды работают как раньше.
2. Админ открывает раздел «Экономика» и видит, сколько золота у игроков, в каждой казне и всего в мире,
   и откуда оно пришло.

### Edge Cases
- Локация без региона/страны (служебные, данжи, дома) — куда идут деньги? (решает Architect)
- Гонки при одновременных проводках на одну казну.
- Существующее золото игроков на проде — должно стать «выпущенным» начальной эмиссией, чтобы сумма сошлась.
  Пользователь: прод ещё даже не в альфе, сохранность данных не важна — достаточно простой миграции
  (одна проводка начальной эмиссии), без сложных переходных режимов.
- Удаление персонажа — его золото не должно испариться без проводки.

### Вопросы к пользователю
- [x] Казны → регион + налог в страну. Сейчас 4 страны.
- [x] Эмиссия → и монетный двор из руды, и фиксированная квота.
- [x] Банк → свой в каждом регионе с городом.
- [x] Кредиты → пока мягко.
- [x] Влияние игроков → пока не нужно.
- [x] Перевод вклада между банками → с комиссией.
- [x] Тик → раз в 6 часов.
- [x] 12 групп товаров → устраивают.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Scope: stage 1 only (ledger, treasuries, routing of existing spend/payouts, currency name setting, admin overview).
All line numbers are against `main` @ `0c509ef`. DB numbers are from the **local** dev DB (`fogdatabase`), which is
known to be an outdated copy of prod lore — re-check counts on prod.

### 2.1 Affected Services

| Service | Type of changes | Files |
|---------|-----------------|-------|
| character-service | owner of `characters.currency_balance` + `gold_transactions`; natural home for the ledger tables/migration and the "post a transfer" helper; rewrite of add_rewards / deduct-gold / teleport / starter kit / admin adjust / delete | `app/models.py:46,412`, `app/crud.py:2351-2450,3560-3680`, `app/main.py:440-470,698-766,1410-1450,3794-3830,4137-4185`, new alembic migration |
| inventory-service | trades + whole auction (escrow, commission, storage) write balances with raw SQL | `app/crud.py:916-955,1087-1191,2573,2678-2760,2815-2850,3023-3180,3187-3380,3385-3440,3565-3670`, `app/main.py:1760-1830`, `app/models.py:533-585` |
| locations-service | NPC shop buy/sell, quest rewards, all house money; owns the world hierarchy (Countries/Regions/Districts/Locations) | `app/crud.py:4376-4500`, `app/main.py:2785-2990,3127-3220`, `app/houses.py:557-571,720-772,1249-1262,1311-1393,2186-2301` |
| dungeon-service | calls character-service add_rewards / deduct-gold over HTTP (events, rest, revive, merchant) | `app/http_clients.py:454-510`, `app/gameplay.py:3765-3830,3873-3915,3985-4010,4029-4080` |
| battle-service | calls add_rewards with `gold` (currently always 0) | `app/main.py:395-450` |
| battle-pass-service | gold rewards via add_rewards; earn_gold / spend_gold missions READ `gold_transactions` | `app/crud.py:395-433,518-555` |
| user-service | RBAC migration for new `economy:*` permissions + test | `alembic/versions/0032_*.py` (next after `0031_user_sessions.py`), `tests/test_rbac_permissions.py` |
| frontend | currency-name setting everywhere (~80 strings / ~41 files), new admin "Экономика" page | see 2.5 |
| character-attributes-service | read-only: perk condition `gold_balance` (`app/perk_evaluator.py:63-90`) — no change needed | — |
| party-, skills-, autobattle-, notification-, photo-, user-service (gold) | **no** balance writes found | — |

### 2.2 Existing Patterns

- character-service: sync SQLAlchemy ORM, Pydantic v1, Alembic (`alembic_version_character`). Gold changes are ORM read-modify-write (`character.currency_balance = x`), which SQLAlchemy emits as `UPDATE ... SET currency_balance = <absolute value>`.
- inventory-service: sync SQLAlchemy, but gold is touched with raw `text()` SQL on the shared `characters` table (relative `SET currency_balance = currency_balance ± :x`). Has its own copy of `log_gold_transaction` (raw INSERT, `crud.py:925`).
- locations-service: async SQLAlchemy (aiomysql), raw SQL helpers `deduct_currency` / `add_currency` (`crud.py:4411`, `:4459`) plus own `_log_gold_transaction` (`crud.py:4376`).
- dungeon-service / battle-service / battle-pass-service: never touch the table; they go through character-service internal HTTP (`X-Internal-Token`, nginx 403s `/characters/internal/` from outside).
- So there are **three** independent writer implementations (character ORM, inventory raw sync, locations raw async) and three copies of the "log a gold transaction" helper. Any ledger helper will have to exist in all three flavours (sync ORM / sync raw / async raw) or be centralised behind an internal HTTP endpoint — Architect's call.

### 2.3 COMPLETE inventory of balance changes

Legend: dir `+` = player receives, `−` = player pays. "Atomic" = balance change and the related game action commit in one DB transaction. "Target" = suggested mapping in the new model.

#### character-service

| # | Where | Trigger | Dir | Amount source | Current `transaction_type` | Atomic / locking | Target in new model |
|---|-------|---------|-----|---------------|---------------------------|------------------|---------------------|
| C1 | `main.py:451-470` (`crud.create_preliminary_character` `crud.py:437-473`) | Admin approves character request | + | starter kit `currency_amount` (`main.py:427`) | `starter_kit` | Same txn (flush). **Start location is resolved only later** (`main.py:529` `_resolve_start_location`) and can be NULL (8 local players have NULL location) | region treasury of start location → player; fallback account needed when location is NULL |
| C2 | `main.py:3794-3830` → `crud.add_rewards_to_character` `crud.py:2384-2450` (write at `:2414`) | Internal `POST /characters/{id}/add_rewards` | + | request `gold` | **always `battle_reward`** regardless of caller (`crud.py:2419-2422`) | ORM read-modify-write, no row lock → absolute SET can overwrite concurrent relative updates from inventory/locations (lost update). XP + gold one commit | region treasury → player; caller must pass its own type + location/region |
| C2a | caller: battle-service `main.py:436-446` | PvE win | + | `total_gold` — **always 0** since mob gold was disabled (`main.py:405-407`) | (battle_reward) | HTTP after battle, errors only logged | none today; keep path working |
| C2b | caller: dungeon-service `gameplay.py:3779-3830` → `http_clients.add_gold` `:454` | Dungeon event outcome with `gold` | + (leader only) | event `outcome_data.gold` | logged as `battle_reward` (mislabelled) | Dungeon commits its own state first (`:3824`), then HTTP; failure = gold silently lost (warning only) | treasury of dungeon's region (`dungeons.location_id` → region) → player |
| C2c | caller: battle-pass-service `crud.py:518-521,536-555` | BP reward claim | + | `reward.reward_value` | logged as `battle_reward` (mislabelled) | HTTP; raises on failure | Stage 1 decision: a region treasury (which?) or a country/"world" treasury — no natural location |
| C3 | `main.py:4137-4185` `POST /characters/internal/deduct-gold` | dungeon-service: rest `gameplay.py:3898`, revive `:4006`, dungeon merchant `:4063` | − | room config `gold_cost` / `revive_gold_cost` / merchant price × qty | `dungeon_expense` | **No lock**, ORM read-check-write (`:4159-4166`) → race + lost update. Dungeon flushes its state, calls HTTP, then commits; if the dungeon commit fails after a successful deduct the gold is gone with no refund | player → treasury of dungeon's region |
| C4 | `crud.py:3560-3680` (write `:3632`, log `:3634-3641`) | Player uses Teleport Master | − | `teleport_links.cost_gold` | `teleport` | `with_for_update()` on character (`:3576-3580`), one txn with the move — **the cleanest existing pattern** | player → treasury of the source NPC's region |
| C5 | `main.py:698-766` `PUT /characters/admin/{id}` (`require_permission("characters:update")`) | Admin edits balance | ± | absolute new value (`AdminCharacterUpdate.currency_balance`, `schemas.py:607-610`) | `admin_adjust` (logged **after** commit, in a separate try) | No lock; absolute SET | explicit admin adjustment posting (emission / burn account), with `economy:*` RBAC; frontend `Admin/CharactersPage/tabs/GeneralTab.tsx` edits this |
| C6 | `main.py:2948` (NPC create), `main.py:3030-3054` (NPC update via `setattr`) | Admin creates/edits NPC | ± | admin form | none | — | **NPC balances**: local 762 NPCs hold 51,360 gold (auctioneers 10,000/9,000, merchants 8,000…). Never spent or received anywhere — only displayed (`main.py:3007`). Decide: exclude from world sum / zero / migrate into stage-3 merchant cash |
| C7 | `crud.py:1761` | Mob spawn | 0 | — | — | — | no-op (mobs created with 0) |
| C8 | `main.py:1410-1450` `DELETE /characters/{id}` | Admin deletes character | − (all) | whole balance | **none** — balance disappears with the row | — | must post player → treasury (or "confiscated" account) **before** `db.delete`. Also orphans: `auction_storage.gold_amount`, active bids (escrowed gold) of the deleted character, `gold_transactions` rows (no FK) |

Note: `internal_unlink` (`main.py:1123`) does not delete the character — no money effect.

#### inventory-service (raw SQL on `characters`)

| # | Where | Trigger | Dir | Amount | Type | Atomic / locking | Target |
|---|-------|---------|-----|--------|------|------------------|--------|
| I1 | `crud.execute_trade` `crud.py:1087-1191` (writes `:1143-1150`, `:1167-1174`), called from `main.py:1813-1816` | Both sides confirm a trade | −/+ both sides | `trade.initiator_gold` / `target_gold` | `trade` (2 rows per direction) | One txn, **but** balance check `:1095-1104` is a plain SELECT and the UPDATE is unconditional; neither the trade row nor the characters are locked (`main.py:1792`) → balance can go negative / double execution under concurrent confirms | player ↔ player direct transfer |
| I2 | `crud.place_bid` `crud.py:3023-3180` | Bid | prev bidder + (`:3088-3100`, `auction_refund`), bidder − (`:3136-3145`, atomic conditional, `auction_buy`) | bid amount | `auction_refund` / `auction_buy` | listing `with_for_update()` (`:3051`) | bidder → **auction escrow** account; escrow → prev bidder |
| I3 | `crud.execute_buyout` `crud.py:3187-3380` | Buyout | prev bidder + (`:3240-3251`); buyer − (`:3286-3304`); seller gets `AuctionStorage.gold_amount = floor(price*0.95)` (`:3332-3344`) | buyout price | `auction_refund` / `auction_buy`; **no row for the 5 % commission** | one txn, listing locked | buyer → escrow; escrow → seller-storage (95 %) + **escrow → region treasury (5 % commission)** |
| I4 | `crud.expire_stale_listings` `crud.py:2678-2760` | Lazy expiry, called from read endpoints `:3704`, `:3742`, `:3803` | winning bid → seller storage `sale_gold` (`:2721-2733`) | `current_bid` | none (commission vanishes) | `with_for_update` on expired listings | escrow → seller storage (95 %) + escrow → treasury (5 %) |
| I5 | `crud.cancel_listing` `crud.py:3385-3440` (refund `:3423-3436`) | Seller cancels | + bidder | `current_bid` | `auction_refund` | listing locked | escrow → bidder |
| I6 | `crud.claim_from_storage` `crud.py:3565-3670` (credit `:3638-3660`) | Seller claims proceeds (requires auctioneer at location, `:3587`) | + | `AuctionStorage.gold_amount` | `auction_sell` | one txn | auction storage (held funds) → player |

Commission constant: `AUCTION_COMMISSION_RATE = 0.05` (`crud.py:2573`). **`auction_listings` has no location/region column** (`models.py:533-554`); listing creation requires an auctioneer at the seller's location (`deposit_to_auction_storage` `crud.py:2815`, check `:2841`), bids/buyouts do not. To route the commission to "the region where it happens" the region (or auctioneer location) must be stored on the listing at creation (new column, inventory-service Alembic).
Escrowed gold lives **outside player balances** in two places: active bids (`auction_listings.current_bid` where `status='active' AND current_bidder_id IS NOT NULL`) and unclaimed proceeds (`auction_storage.gold_amount`, local: 146). Both must be accounts (or counted) for the world sum to close.

#### locations-service (async raw SQL)

Helpers: `deduct_currency` `crud.py:4411-4456` — atomic `UPDATE … WHERE currency_balance >= :amount`, then **immediately `session.commit()`** (commits whatever else is pending in the session — houses rely on this), then a separate SELECT and a separate logging commit. `add_currency` `crud.py:4459-4500` — unconditional, commits. `_log_gold_transaction` `crud.py:4376-4408` — own commit, swallows errors (so a log row can be missing).

| # | Where | Trigger | Dir | Amount | Type | Atomic | Target |
|---|-------|---------|-----|--------|------|--------|--------|
| L1 | `main.py:2785-2890` (deduct `:2842`) | Buy from NPC shop (charisma discount `:2832-2838`) | − | `npc_shop_items.buy_price` × qty, discounted | `charisma_shop_buy` | Deduct commits first, then HTTP to inventory-service; compensating refund on failure (`:2868`, `:2883`, type `shop_buy_refund`) | player → treasury of NPC's region (stage 3: merchant cash) |
| L2 | `main.py:~2920-2995` (credit `:2980`) | Sell to NPC | + | `find_sell_price_for_item` × qty | `charisma_shop_sell` | Item removed via HTTP first, then credit (no compensation if credit fails) | treasury of NPC's region → player |
| L3 | `main.py:3127-3220` (credit `:3156`) | Complete quest | + | `quests.reward_currency` | `quest_reward` | Gold committed **before** `complete_quest_record` (~`:3217`) → concurrent double-complete can pay twice | treasury of quest's region (quest giver NPC location or player location) → player |
| L4 | `houses.py:720-772` (deduct `:763-766`) | Buy a free plot/house | − | `house_plots.price` | `house_purchase` | House rows + payment commit together (via deduct's commit) | player → treasury of plot's region (`house_plots.region_id` is cached) |
| L5 | `houses.py:1249-1262` `_pay_for_build`, callers `:1311` (build room), `:1337` (unlock layer), `:1366` (unlock cell/extension), `:1393` (upgrade room) | House construction | − | `house_build_costs.gold`, layer `unlock_price`, `extension_price` | `house_build` | Atomic with materials + room change | player → plot's region treasury |
| L6 | `houses.py:2186-2217` (deduct `:2209`) | Pay house tax | − | `_tax_state.due` | `house_tax` | Atomic | player → plot's region treasury |
| L7 | `houses.py:2267-2301` | Buy a house listed by another player | buyer − (`:2292`), seller + (`:2298`) | `houses.sale_price` | `house_purchase` + `house_sale` | **Not atomic**: buyer debit + ownership commit in one commit, seller credit in a second commit — crash in between = gold destroyed | player ↔ player direct transfer (single posting) |

House seizure (non-payment) moves no gold.

#### Summary of "where the money goes" for stage 1

- player → region treasury: C3 (dungeon rest/revive/merchant), C4 teleport, L1 NPC buy, L4/L5/L6 house purchase/build/tax, I3/I4 auction 5 % commission, C8 deletion (or a dedicated "confiscated" account).
- region treasury → player: C1 starter kit, C2b dungeon event gold, C2c battle-pass gold (no natural region), L2 NPC sell, L3 quest reward, (C2a mob gold — currently 0).
- player ↔ player: I1 trade, L7 house resale; auction via an escrow/held-funds account (I2–I6).
- admin: C5 adjustments (emission/burn), C6 NPC balances (decorative today).

### 2.4 `gold_transactions` today

- Model `character-service/app/models.py:412-427`; migration `character-service/app/alembic/versions/013_add_gold_transactions.py` (FEAT-102). Columns: `id INT PK`, `character_id INT NOT NULL` (no FK), `amount INT` (signed, + earn / − spend), `balance_after INT`, `transaction_type VARCHAR(50)`, `source VARCHAR(100)`, `metadata JSON`, `created_at DATETIME DEFAULT now()`. Indexes: `character_id`, `(character_id, created_at)`, `transaction_type`.
- It is **single-entry** (one side only, no counter-account). Writers: character-service `crud.log_gold_transaction` (`crud.py:2351`, swallows errors), inventory-service `crud.log_gold_transaction` (`crud.py:925`, swallows), locations-service `_log_gold_transaction` (`crud.py:4376`, separate commit, swallows).
- **Not every change writes a row:** missing for C6 (NPC balances), C8 (deletion), auction commission/escrow→storage (I3/I4); logging can silently fail in all three helpers; C5 logs after the commit. Local data: 128 rows; for 13 of 28 players `SUM(amount) != currency_balance` (balances predate the table / were set directly) → **history cannot be replayed to reconstruct balances; the migration must snapshot opening balances.**
- Types in use: `starter_kit`, `battle_reward`, `dungeon_expense`, `teleport`, `admin_adjust`, `trade`, `auction_buy`, `auction_refund`, `auction_sell`, `charisma_shop_buy`, `charisma_shop_sell`, `shop_buy_refund`, `quest_reward`, `house_purchase`, `house_build`, `house_tax`, `house_sale`.
- **Readers:** battle-pass-service `_progress_earn_gold` / `_progress_spend_gold` (`crud.py:395-433`) — `SUM(amount)` over `character_id IN (…) AND amount >0 / <0 AND created_at >= season_start`, **type-agnostic** (trades and auction refunds count as "earned"). If the ledger replaces this table (or changes sign semantics), these two queries must move to the new table with the same semantics, or `gold_transactions` must keep being written as a per-player view. Separate counters `total_gold_earned/spent` in character-attributes cumulative stats (fed by locations `_track_cumulative_stats`) are not a ledger and are unaffected.

### 2.5 World hierarchy

Owned by **locations-service** (`app/models.py:14-155`):
- `Areas` (3 locally: Эйдонэя, Саркос, Иркалл) → `Countries.area_id` (nullable).
- `Countries` (`id, name, leader_id, is_hidden, area_id, …`). Local: **6** — Мидденгерд (6 regions), Шинзо (6), Орос (5), Юнион-Ист (6) = the 4 playable; plus `Другое` (id 10, **is_hidden=1**, 1 region "Морские локации") and `Обратная Экзоста` (id 11, area Саркос, 3 regions). The brief says "4 countries" — the hidden/service country and the second-area country need a decision (treasury or not). Prod may differ.
- `Regions` (`country_id NOT NULL`, `leader_id`, `entrance_location_id`). Local: **27**.
- `Districts` (`region_id NOT NULL`, nested via `parent_district_id`). Local: 328.
- `Locations` (`district_id NULL`, `region_id NULL`, `parent_id` for subdistrict-type children). Local: 2287; **0 locations without a resolvable region** (via `COALESCE(district.region_id, location.region_id)`).
- Region of a location — two existing implementations:
  - SQL: `crud.py:8128-8145` `_location_breadcrumbs_query`: `Region.id = COALESCE(District.region_id, Location.region_id)`, `Country.id = Region.country_id`.
  - Python walk incl. `parent_id`: `houses.py:557-571` `_region_of_location`.
  - Other services read `Locations`/`Districts`/`Regions` from the shared DB with raw SQL (allowed pattern). A single shared SQL snippet / cached `location_id → (region_id, country_id)` resolver would be needed in character-, inventory- and locations-service.
- Locations "without region" in practice:
  - **Houses**: a character inside a house keeps `current_location_id = house_plots.location_id` and gets `house_room_id` (`houses.py:1120,1146`); `house_plots.region_id` is cached (`models.py:1048-1054`). → houses resolve fine.
  - **Dungeons**: `dungeons.location_id` (dungeon-service `models.py:25`) — local: all 5 dungeons at location 197 (region 9 Мэттанхейм). Dungeon sessions → dungeon → location → region. dungeon-service must pass it to character-service (today it passes only character_id + amount).
  - **Characters with NULL `current_location_id`** (8 local players, unapproved start) — starter kit, battle-pass and admin postings have no location.
  - Battle-pass rewards, admin actions, deletion — no location by nature.
  - Hidden country "Другое"/"Морские локации" — service-ish region.
- `characters.currency_balance` is `INT` (`models.py:46`); local max is 100,000,000 (test char Тамзи), local player total 101,137,997. World/treasury sums should use `BIGINT`.

### 2.6 Currency name hardcoded

- **Frontend** (`services/frontend/app-chaldea/src`): ~81 matches of `золот|зол.|монет` in ~41 files. Heaviest: `pages/HousesPage/HousePlan.tsx` (6), `HouseOwnership.tsx` (5), `Auction/AuctionListingDetail.tsx` (5), `pages/LocationPage/HousesSection.tsx` (4), `HouseTaxPanel.tsx` (4), `ProfilePage/PerksTab/PerkDetailModal.tsx` (4), `DungeonPage/DungeonRoom.tsx` (4), `Auction/AuctionStorageTab.tsx` (4), `NpcShopModal.tsx` (3), plus TradeModal, TeleportMenu, NpcAuctionModal, HouseBuild, BuyListedHouseDialog, AuctionMyListingsTab, AuctionListingCard, Admin TeleportLinksPanel, Admin PlotFormModal, AdminBattlePass/MissionsTab, `redux/slices/teleportSlice.ts`, HouseMarketPage, HouseFacade, RegionInteractiveMap, PerkTree. Balance itself is shown in `CommonComponents/Header/CharacterChip.tsx`, `MobileHeader.tsx`, `ProfilePage/CharacterTab/CharacterPanel.tsx` (from `userSlice` / `profileSlice`).
- **Backend user-facing text** (`золот|зол.|валют`, excluding tests/migrations): inventory-service ~24 (auction notifications `crud.py:2742-2770`, `3060-3070`, `3360-3365`, trade errors `crud.py:1099,1104`, `main.py:1765,1771`), dungeon-service ~11 (`gameplay.py` errors `:3899`, `:4007`, `:4064`, merchant message `:4078`, `generator_texts.py`), character-service ~7 (teleport `crud.py:3627`, deduct-gold `main.py:4163`, admin validation), locations-service ~7 (houses `houses.py:770,1258,2213,2296`, shop "Недостаточно валюты"), user-service ~7 (docstrings mostly), character-attributes 1.
- Russian needs several forms (nominative/genitive plural/abbreviation: «золото / золота / зол.»), so the setting is more than one string. No global "game settings" table exists; nearest precedents are singleton rows `house_settings` (locations `models.py:1292`, `houses.py:2342-2355`) and `game_time_config` (`models.py:424`). Frontend would need a public settings endpoint + a Redux/context value; backend messages in 4 services need to read it (or a cached HTTP lookup).

### 2.7 Admin RBAC patterns

- Permission migrations: user-service `alembic/versions/00NN_add_<module>_permissions.py`, idempotent SELECT-then-INSERT into `permissions(module, action, description)` + `role_permissions` for Moderator (role_id 3) / Editor (2); Admin (4) gets everything automatically. Template: `0026_add_origin_permissions.py`. Last revision `0031` → next `0032`. Suggested `economy:read`, `economy:emit`, `economy:adjust` (Architect decides).
- **Test obligation** (CLAUDE.md §10.13): add a `TestEconomyPermissions` section to `user-service/tests/test_rbac_permissions.py` (patterns at `:634` Perks, `:1057` Moderation, `:1205` PostsHistory).
- Backend check: `Depends(require_permission("economy:read"))` from each service's `auth_http.py` (e.g. `character-service/app/auth_http.py:79`).
- Frontend: tile in `components/Admin/AdminPage.tsx:18+` (`{label, path, description, module}` filtered by `hasModuleAccess`), route in `components/App/App.tsx` wrapped in `<ProtectedRoute requiredPermission="…">` (e.g. `:181-185`). New page in Tailwind + TS per design system.

### 2.8 Concurrency patterns in use

| Pattern | Where | Safe? |
|---------|-------|-------|
| `SELECT … FOR UPDATE` on character, check, write, one commit | teleport `crud.py:3576-3632` | yes |
| Atomic conditional `UPDATE … SET b=b-x WHERE id=? AND b>=x`, check rowcount | inventory bids/buyout `crud.py:3136,3286`; locations `deduct_currency` `crud.py:4424` | yes for the debit |
| Unconditional relative `UPDATE b=b+x` | inventory refunds/claims/trade credit; locations `add_currency` | yes for credits |
| ORM read-modify-write without lock (absolute SET) | add_rewards `crud.py:2414`, deduct-gold `main.py:4159-4166`, admin update `main.py:720-724` | **no** — lost updates against concurrent writers in other services |
| Plain SELECT check then unconditional debit | trade `crud.py:1095-1150` | **no** — can go negative |
| Row lock on the business object (listing / house / plot unique constraint) | auction `with_for_update`, house plot `IntegrityError` | yes |
| Payment committed before the business action / reward before completion mark | NPC shop buy (compensated), quest reward (not), house resale seller credit (not) | partially |

### 2.9 DB facts (local, read-only queries)

- players: 28, Σ balance 101,137,997 (dominated by test chars); NPCs: 762, Σ 51,360; negative balances: 0.
- active auction escrow: 0; `auction_storage` gold: 146.
- `gold_transactions`: 128 rows; per-type sums: battle_reward +1710, starter_kit +2582, quest_reward +31, house_sale +700, dungeon_expense −825, house_build −3370, house_purchase −1050, house_tax −306, teleport −20.
- countries 6 / regions 27 / districts 328 / locations 2287 / dungeons 5 / house plots 2.

### 2.10 Risks for stage 1

1. **Three writer stacks** (character ORM sync, inventory raw sync, locations raw async) + HTTP callers. The posting helper (debit A, credit B, insert ledger rows, in the caller's transaction) must be implemented for all three or centralised. Centralising behind character-service HTTP breaks atomicity of house/auction/trade transactions (today they commit gold together with the business row) — prefer shared-DB helpers in the caller's transaction, matching current practice.
2. **Hot treasury rows.** Every spend in a region updates one treasury row → row-lock contention and deadlock risk when a txn locks player row + treasury row in different orders (e.g. trade: two players; auction buyout: buyer, prev bidder, escrow, treasury). Mitigations for Architect: fixed lock order (by account id), keep the treasury UPDATE last and short, or append-only postings with treasury balance = materialised sum updated asynchronously. With ~30 players contention is low today; the stage-2 6-hour tick will also write treasuries.
3. **Lost updates already present**: C2/C3/C5 absolute SETs can overwrite a concurrent inventory/locations relative update → world sum drifts silently. Must become relative/locked as part of this stage, otherwise reconciliation fails.
4. **Non-atomic pairs**: house resale (L7), dungeon deduct-then-commit (C3), dungeon event gold after commit (C2b), NPC sell (L2), quest reward before completion (L3, double pay), trade without locks (I1). With double entry these become "money appears/vanishes" bugs visible in the world sum.
5. **Escrow outside balances**: auction bids and `auction_storage.gold_amount` must be ledger accounts (escrow / held funds) or the world sum will not close; commission needs a region → new column on `auction_listings` (inventory-service migration).
6. **Prod migration / initial emission**: `gold_transactions` history does not reconcile with balances (13/28 local players), so the migration must: create accounts, create treasury accounts for each region/country, then post a **genesis emission** = Σ player balances + Σ active bid escrow + Σ auction_storage gold (+ NPC balances if counted) into the matching accounts, plus the admin-chosen opening treasury emission. Must be idempotent (Alembic auto-runs on container start) and survive the CI deploy pattern (`down` + rebuild). Balances that change between snapshot and cut-over are an issue only if the migration runs while services are live — with auto-migration at startup it runs before the service accepts traffic, but other services (inventory/locations) may already be writing; plan for a reconciliation endpoint/job.
7. **Treasury insufficiency**: payouts (starter kit, quests, NPC sell, dungeon gold, BP) must not fail in stage 1 — allow negative treasury or auto-subsidy from country; document invariant (world sum = Σ emissions − Σ burns).
8. **No location** for: starter kit when start location is NULL, battle-pass rewards, admin adjustments, deletions, hidden country/region "Другое/Морские локации", second-area country "Обратная Экзоста". Need a fallback account (e.g. country treasury of origin country, or a "world"/crown account).
9. **Regions/countries are mutable** (admin can create/delete regions; `Regions.country_id` CASCADE delete; region moves between countries). Treasury accounts keyed by region_id need a policy for region deletion (balance → country) and creation (auto-create account).
10. **battle-pass earn/spend missions** read `gold_transactions` by sign; changing the table or adding treasury-side rows with a `character_id` would distort them. Keep per-player semantics.
11. **Character deletion** (C8) and orphaned escrow/storage of deleted characters must post to a defined account.
12. **INT overflow** on aggregates; use BIGINT for account balances and sums.
13. **Currency name** spans 4 backend services' error/notification strings and ~41 frontend files; Russian declension needs several forms; notifications already stored in DB keep the old name.
14. Tests: no tests for `POST /internal/deduct-gold` (`docs/ISSUES.md:581`); QA must cover posting helpers, world-sum invariant, concurrency (two spends on one treasury), migration genesis.

---

## 3. Architecture Decision (filled by Architect — in English)

Scope: **stage 1 «Фундамент»** only. Stages 2–5 (region simulation, NPC merchants, bank, mint/caravans) are
accommodated by the schema, not designed.

### 3.0 Open questions for the user — ANSWERED 2026-10-29: user accepted all six recommended answers

| # | Question | Recommended answer (used in this design) |
|---|----------|------------------------------------------|
| Q1 | Gold with no natural place (battle-pass rewards, payouts to a player with no location, character-deletion fallback, commission of legacy auction listings) needs one world-level account. What is it in lore? | One singleton account `world_treasury`, display name **«Казна Скитальцев»** (every player character is a Скиталец, so the order funds the battle pass and catches orphaned gold). The name is a DB field — renameable later. |
| Q2 | Region → country tax rate in stage 1. | **10 %** of every taxable inflow into a region treasury, forwarded instantly (3.4). Stored in `econ_settings.country_tax_rate`, admin-editable (0–50 %). Stage 2 may make it per-region. |
| Q3 | Default currency word forms (old texts: «100 золота», «зол.»). Russian counting needs one/few/many. | Name «Золото», genitive «золота», counting «золотой / золотых / золотых», short «зол.» → «1 золотой», «3 золотых», «Недостаточно золота». The lore admin edits them in «Экономика». |
| Q4 | NPC gold (762 NPCs, 51 360 locally; decorative today). | **Keep and count it**: NPCs are `characters`, their balances enter the genesis emission as ordinary character accounts. In stage 3 the merchant «касса» simply *is* the NPC's balance — no second migration. Admin edits of NPC gold become adjustment postings. |
| Q5 | Who may see / operate «Экономика». | `economy:read` → Admin + Moderator; `economy:emit`, `economy:adjust`, `economy:settings` → Admin only (Admin gets all automatically). |
| Q6 | Battle-pass «заработать/потратить золото» missions switch to the new ledger; old `gold_transactions` rows are not merged. | Accept (pre-alpha, data loss allowed): progress of these two mission types in the running season restarts from the deploy. |

### 3.1 Key decisions

1. **Ledger tables live in character-service** (owner of `characters.currency_balance`, Alembic-managed). No new
   microservice in stage 1: prod VPS has 3.8 GB without swap and the CI deploy already struggles. The schema is
   service-agnostic, so a future economy-service can adopt it.
2. **Atomicity through the shared DB, not HTTP.** Every service that changes gold *together with its own business rows*
   posts in its **own** DB transaction via a thin local helper over one SQL contract: character-service,
   inventory-service (sync), locations-service, dungeon-service (async). dungeon-service moves from HTTP to in-transaction
   posting (fixes pay-before-commit and lost event gold). battle-pass-service (and battle-service, gold always 0) keep
   calling `POST /characters/{id}/add_rewards`, which becomes **idempotent** via `idempotency_key`.
3. **One contract, few copies, CI-enforced identical:**
   - `app/econ_core.py` — pure, framework-free: account kinds, op types, leg types, SQL strings, validation, tax and
     netting/lock-order planning, Russian plural + currency formatting, exceptions. **Byte-identical in all 4 services.**
     Canonical copy: character-service.
   - `app/econ_ledger.py` — thin executor of `econ_core` plans. **Sync** (canonical character-service, copy
     inventory-service) and **async** (canonical locations-service, copy dungeon-service).
   - `app/tests/econ_contract_cases.py` — shared scenarios + portable SQLite DDL for the ledger tables, byte-identical in
     all 4 services; each service's `tests/test_econ_contract.py` runs them through its own executor.
   - CI job `econ-contract-copies` (sha256 compare of each copy group) fails the pipeline on divergence.
4. **Double entry with source accounts.** Money is created only by postings *from* `emission` (genesis, admin emission,
   future mint/quota) or `adjustment` (explicit admin correction); their balances go negative. World invariant:
   **Σ(all account balances, incl. characters) = 0**, i.e. *issued* = −(emission + adjustment) = *held*.
5. **Player balance storage stays in `characters.currency_balance`** (many readers: perks, header, profile, battle
   checks). A character's `econ_accounts` row exists for the journal/FKs; its `balance` column is unused (0) and the
   executor applies character deltas to `characters.currency_balance`. Column widened to BIGINT.
6. **Treasuries (region/country/world) and source accounts may go negative in stage 1**; character, escrow and
   auction-storage accounts never (conditional UPDATE). Why: there is no income model before the stage-2 simulation;
   payouts (quests, NPC sell, starter kit, dungeon gold) must not start failing; a negative treasury is visible to the
   admin as a deficit and can be topped up by emission. Stage 2 decides insufficiency behaviour.
7. **Region → country tax** = instant share of each taxable inflow, generated as an extra leg in the same operation (no
   scheduler in stage 1; deterministic, testable). The 6 h tick in stage 2 may replace it with a periodic sweep.
8. **Fixed lock order** (3.5): caller's business rows → `characters` by ascending id → `econ_accounts` by ascending id.
   The helper nets deltas per account before touching rows, so each row is locked once per operation.
9. **`gold_transactions` is frozen** (no new writes, kept read-only, dropped in a later stage). battle-pass earn/spend
   missions read `econ_postings` with the same semantics.
10. **Currency name** lives in `econ_settings` (character-service). Backends read it from the shared DB (60 s TTL cache);
    the frontend fetches a public endpoint into Redux and formats via `formatCurrency` / `useCurrency()`.

### 3.2 DB Changes

All in **character-service migration `027_world_economy`**, except the auction columns (inventory-service
`033_auction_listing_region`) and RBAC (user-service `0032`). Revision ids ≤ 32 chars. No ENUMs — kinds/op types are
VARCHAR validated in `econ_core`, so later stages add kinds without schema changes. FK columns get explicit indexes.

```sql
-- 1. Balances: BIGINT.
UPDATE characters SET currency_balance = 0 WHERE currency_balance IS NULL;
ALTER TABLE characters MODIFY currency_balance BIGINT NOT NULL DEFAULT 0;

-- 2. Global economy settings (singleton id=1).
CREATE TABLE econ_settings (
  id                 TINYINT      NOT NULL PRIMARY KEY,           -- always 1
  currency_name      VARCHAR(50)  NOT NULL DEFAULT 'Золото',       -- nominative: labels, titles
  currency_genitive  VARCHAR(50)  NOT NULL DEFAULT 'золота',       -- «Недостаточно золота»
  currency_one       VARCHAR(50)  NOT NULL DEFAULT 'золотой',      -- 1, 21, 101
  currency_few       VARCHAR(50)  NOT NULL DEFAULT 'золотых',      -- 2–4, 22–24
  currency_many      VARCHAR(50)  NOT NULL DEFAULT 'золотых',      -- 0, 5–20, 25
  currency_short     VARCHAR(20)  NOT NULL DEFAULT 'зол.',
  country_tax_rate   DECIMAL(5,4) NOT NULL DEFAULT 0.1000,         -- 0 … 0.5
  updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  updated_by_user_id INT NULL
);
INSERT INTO econ_settings (id) VALUES (1);

-- 3. Accounts: one row per (kind, ref_id).
CREATE TABLE econ_accounts (
  id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  kind           VARCHAR(32)  NOT NULL,
  ref_id         BIGINT       NOT NULL DEFAULT 0,   -- characters.id / Regions.id / Countries.id / 0 for singletons
  name           VARCHAR(255) NULL,                 -- singleton display name / treasury name snapshot
  balance        BIGINT       NOT NULL DEFAULT 0,   -- unused (0) for kind='character'
  allow_negative TINYINT(1)   NOT NULL DEFAULT 0,
  is_active      TINYINT(1)   NOT NULL DEFAULT 1,   -- 0 after region/country/character deletion; row is kept
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_econ_accounts_kind_ref (kind, ref_id),
  KEY ix_econ_accounts_kind (kind)
);

-- 4. Operation = one business event (journal header). Append-only.
CREATE TABLE econ_operations (
  id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  op_type         VARCHAR(50)  NOT NULL,
  idempotency_key VARCHAR(128) NULL,
  location_id     BIGINT       NULL,
  region_id       BIGINT       NULL,
  actor_user_id   INT          NULL,
  source_service  VARCHAR(32)  NOT NULL,
  comment         VARCHAR(500) NULL,          -- mandatory for admin ops
  metadata        JSON         NULL,          -- listing_id, trade_id, house_id, quest_id, session_id …
  created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_econ_operations_idem (idempotency_key),
  KEY ix_econ_operations_created (created_at),
  KEY ix_econ_operations_type_created (op_type, created_at),
  KEY ix_econ_operations_region_created (region_id, created_at)
);

-- 5. Postings = legs "from → to". Append-only; a reversal is a new operation.
CREATE TABLE econ_postings (
  id              BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
  operation_id    BIGINT      NOT NULL,
  from_account_id BIGINT      NOT NULL,
  to_account_id   BIGINT      NOT NULL,
  amount          BIGINT      NOT NULL,
  leg_type        VARCHAR(32) NOT NULL DEFAULT 'main',   -- main | refund | commission | tax
  created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_econ_postings_operation (operation_id),
  KEY ix_econ_postings_from_created (from_account_id, created_at),
  KEY ix_econ_postings_to_created (to_account_id, created_at),
  CONSTRAINT fk_econ_postings_operation FOREIGN KEY (operation_id)    REFERENCES econ_operations(id),
  CONSTRAINT fk_econ_postings_from      FOREIGN KEY (from_account_id) REFERENCES econ_accounts(id),
  CONSTRAINT fk_econ_postings_to        FOREIGN KEY (to_account_id)   REFERENCES econ_accounts(id),
  CONSTRAINT ck_econ_postings_amount    CHECK (amount > 0),
  CONSTRAINT ck_econ_postings_distinct  CHECK (from_account_id <> to_account_id)
);
```

**Account kinds (stage 1)** — constants in `econ_core`:

| kind | ref_id | balance in | negative allowed | created |
|------|--------|-----------|------------------|---------|
| `character` | characters.id (players **and** NPCs) | `characters.currency_balance` | no | genesis + lazily on first posting |
| `region_treasury` | Regions.id | `econ_accounts.balance` | yes | migration for existing regions + lazily |
| `country_treasury` | Countries.id | same | yes | migration + lazily |
| `world_treasury` | 0 | same | yes | migration, «Казна Скитальцев» (Q1) |
| `auction_escrow` | 0 | same | no | migration, «Ставки аукциона» |
| `auction_storage` | 0 | same | no | migration, «Хранилище аукциона» |
| `emission` | 0 | same | yes (source) | migration, «Эмиссия» |
| `adjustment` | 0 | same | yes (source) | migration, «Корректировки» |

Reserved for later stages without schema change: `population_purse` (region), `bank` (region), `bank_deposit` / `loan`
(character), `mint` (country), `caravan` … — just new constants. (Stage-3 merchant cash = NPC `character` account.)

**Sub-invariants** (checked by the admin summary):
- `auction_escrow.balance = Σ auction_listings.current_bid WHERE status='active' AND current_bidder_id IS NOT NULL`
- `auction_storage.balance = Σ auction_storage.gold_amount`
- per character: `currency_balance = Σ postings in − Σ postings out` (drift detector — catches any write bypassing the helper).

**Genesis (in migration 027, plain SQL, idempotent: skipped if an operation with `idempotency_key='genesis'` exists):**
1. Insert singleton accounts; `region_treasury` for every `Regions` row and `country_treasury` for every `Countries`
   row (guard with `information_schema` so an empty DB does not fail); names snapshotted.
2. Insert `character` accounts for every character with `currency_balance <> 0`.
3. One operation `op_type='genesis'`, `source_service='character-service'`, `comment='Начальная эмиссия'`.
4. Postings `emission → character` per positive balance (negative, none expected: `character → emission`);
   `emission → auction_escrow` (Σ active bids, if > 0); `emission → auction_storage` (Σ storage gold, if > 0).
5. Set balances of `emission`, `auction_escrow`, `auction_storage`. Treasuries start at 0 — the opening treasury
   emission is done by the admin in the UI (brief: «размер задаёт админ»).

Downgrade: drop the four tables, `MODIFY currency_balance INT` (lossless while balances < 2^31).

**inventory-service `033_auction_listing_region`:**
```sql
ALTER TABLE auction_listings ADD COLUMN location_id BIGINT NULL, ADD COLUMN region_id BIGINT NULL;
CREATE INDEX ix_auction_listings_region ON auction_listings (region_id);
```
Filled at listing creation from the auctioneer location (`deposit_to_auction_storage` already checks it). Legacy rows
stay NULL → their commission goes to `world_treasury`.

No migrations in locations-, dungeon-, battle-pass-service.

### 3.3 Posting helper contract (`econ_core.py` + `econ_ledger.py`)

```python
@dataclass(frozen=True)
class AccountRef:            # callers name accounts, never raw ids
    kind: str
    ref_id: int = 0
    # constructors: character(id), region(id), country(id), world(), escrow(), storage(), emission(), adjustment()

@dataclass(frozen=True)
class Leg:
    src: AccountRef
    dst: AccountRef
    amount: int              # int > 0; legs with 0 are dropped
    leg_type: str = "main"   # main | refund | commission  (tax legs are generated, never passed)

def post_operation(session, *, op_type, legs, source_service, location_id=None, region_id=None,
                   actor_user_id=None, comment=None, metadata=None, idempotency_key=None,
                   apply_tax=True) -> PostingResult      # (operation_id, {character_id: new_balance})
def resolve_location(session, location_id) -> (region_id | None, country_id | None)
def treasury_for_location(session, location_id | None) -> AccountRef     # region treasury, else world_treasury
def lock_characters(session, character_ids) -> {id: balance}             # SELECT … FOR UPDATE, ascending id
def get_currency_forms(session) -> CurrencyForms                         # 60 s TTL cache, DEFAULT_FORMS fallback
# Added in B1 (same names in the async executor):
def get_economy_settings(session) -> EconomySettings                     # (forms, country_tax_rate), same cache
def invalidate_settings_cache() -> None                                  # call after PUT settings (B3)
def get_or_create_account(session, ref) -> int                           # econ_accounts.id (admin API lookups)
def deactivate_account(session, ref) -> None                             # is_active=0 (C8, region/country delete)
def allow_direct_balance_write(session)                                  # ctx manager: bypass the ORM guard (fixtures)
def install_balance_guard(model_cls, attr="currency_balance", *, strict=True, session_cls=Session)  # sync only
# post_operation returns PostingResult(operation_id=None, balances={}) when every leg is 0 (nothing written).
# Re-exported from econ_ledger: AccountRef, Leg, PostingResult, CurrencyForms, EconomySettings, EconomyError,
#   InsufficientFunds, DuplicateOperation, format_currency, plural_ru.
# econ_core also exposes the op-type/kind constants (OP_*, KIND_*) and DEFAULT_FORMS.
# Guard: installed in models.py with BALANCE_GUARD_STRICT = False (warning only) — B2 flips it to True
#   once no ORM writer of currency_balance is left (21 tests of add_rewards/teleport/admin edit fail in strict mode today).
# econ_core (pure): plural_ru(n, one, few, many), format_currency(n, forms, short=False), CurrencyForms,
#   exceptions InsufficientFunds(account, needed), DuplicateOperation(operation_id), EconomyError
```
Async variant: same names, `async def`, `AsyncSession`. Region resolution SQL (one statement in `econ_core`):
`Locations` → `COALESCE(Districts.region_id, Locations.region_id)` → `Regions.country_id`, walking `Locations.parent_id`
up to 5 levels (recursive CTE) when both are NULL.

Algorithm (planned once in `econ_core.plan_operation`, executed by `econ_ledger`):
1. Validate: amounts are positive `int`, kinds and `op_type` known, `src != dst`; legs touching `emission` /
   `adjustment` only for `genesis`, `admin_emission`, `admin_adjust`.
2. **Tax** (if `apply_tax`): for every leg whose `dst` is a `region_treasury` and whose `src` is a `character`,
   `auction_escrow` or `auction_storage`, add leg `region → country_treasury(Regions.country_id)`,
   `amount = floor(amount × country_tax_rate)`, `leg_type='tax'` (dropped if 0). Admin ops use `apply_tax=False`.
3. Insert the `econ_operations` row **first** inside a SAVEPOINT — a duplicate `idempotency_key` raises
   `DuplicateOperation` before any balance moves; the caller's transaction stays usable.
4. Get-or-create account ids (SELECT; on miss INSERT in a SAVEPOINT; on duplicate re-SELECT).
5. **Net** deltas per account, apply in the fixed order (3.5):
   - character debit: `UPDATE characters SET currency_balance = currency_balance - :d WHERE id=:id AND currency_balance >= :d`
     (rowcount 0 → `InsufficientFunds`); credit `… + :d WHERE id=:id` (rowcount 0 → `EconomyError`).
   - other kinds: `UPDATE econ_accounts SET balance = balance + :delta WHERE id=:id AND (allow_negative=1 OR balance + :delta >= 0)`
     (rowcount 0 → `InsufficientFunds`).
6. Insert all `econ_postings` (one per leg, not netted — the journal keeps business meaning).
7. Read back touched characters' balances for the result.
8. **Never commits / rolls back.** The caller commits with its business rows, or rolls back on an exception.

Caller rules (documented in `docs/services/character-service.md` → «Economy ledger», referenced from the other services' docs):
- Nobody changes `characters.currency_balance` or `econ_accounts.balance` except through `post_operation`.
  character-service adds an ORM `before_flush` guard raising if a persistent `Character.currency_balance` is modified
  (new characters must be inserted with 0).
- Lock business rows first; call the helper as the last DB step before commit; never keep the transaction open across
  an HTTP call.
- Always pass `location_id` when known; pick the treasury with `treasury_for_location()`.
- Idempotency keys `<op_type>:<business id>`, e.g. `quest_reward:cq:123`, `battle_pass_reward:claim:55`,
  `dungeon_reward:s:7:r:3`.

**Op types (stage 1):** `genesis`, `admin_emission`, `admin_adjust`, `starter_kit`, `battle_reward`,
`battle_pass_reward`, `dungeon_reward`, `dungeon_expense`, `teleport`, `trade`, `auction_bid`, `auction_refund`,
`auction_buyout`, `auction_settlement`, `auction_claim`, `npc_shop_buy`, `npc_shop_buy_refund`, `npc_shop_sell`,
`quest_reward`, `house_purchase`, `house_build`, `house_tax`, `house_resale`, `character_deleted`, `treasury_closed`.

### 3.4 Mapping of every existing balance change (analysis 2.3 → new model)

| # | op_type | Legs | Concurrency / atomicity fix |
|---|---------|------|-----------------------------|
| C1 starter kit | `starter_kit` | `treasury_for_location(start location) → character` | resolve the start location **before** posting; character created with 0, kit posted after flush, one commit |
| C2 add_rewards (HTTP) | from request: `battle_reward` (default) / `battle_pass_reward` / `dungeon_reward` | payer `location` (default: `location_id` or character's current location → region, else world) or `world` | ORM absolute SET removed; duplicate `idempotency_key` → 200 `duplicate=true`, **neither XP nor gold** added |
| C2a battle-service | unchanged call, `gold=0` → no operation | — | no code change |
| C2b dungeon event gold | `dungeon_reward` in dungeon-service's txn | `region(dungeon.location_id) → leader` | posted before the dungeon commit, same txn (HTTP call removed) |
| C2c battle-pass | `battle_pass_reward` via HTTP, `payer='world'`, key from the claim | `world → character` | idempotent retry |
| C3 rest / revive / dungeon merchant | `dungeon_expense` in dungeon-service's txn | `character → region(dungeon location)` | conditional debit inside the dungeon txn; `/internal/deduct-gold` kept for compatibility, rewritten over the helper |
| C4 teleport | `teleport` | `character → region(source NPC location)` | keeps its lock; absolute write replaced |
| C5 admin balance edit | `admin_adjust` | delta > 0 `adjustment → character`; < 0 `character → adjustment` | delta computed under `lock_characters`; needs `economy:adjust` |
| C6 NPC create/edit gold | `admin_adjust` | as C5 | same permission rule |
| C8 character deletion | `character_deleted` | whole balance `character → treasury_for_location(current location)`; account inactive | same commit as `db.delete` |
| I1 trade | `trade` | `initiator → target` (initiator_gold), `target → initiator` (target_gold), one operation | trade row `FOR UPDATE` + status check-and-set (no double execution), `lock_characters([a, b])`, conditional debits (no negatives) |
| I2 bid | `auction_bid` | `bidder → escrow`; `escrow → prev bidder` (refund) | listing lock kept |
| I3 buyout | `auction_buyout` | `buyer → escrow` (price); `escrow → prev bidder` (refund); `escrow → storage` 95 %; `escrow → region(listing.region_id) or world` 5 % (commission, taxed) | one txn, listing lock kept |
| I4 lazy expiry with winner | `auction_settlement` | `escrow → storage` 95 %; `escrow → region/world` 5 % (commission) | listing lock kept |
| I5 cancel | `auction_refund` | `escrow → bidder` | — |
| I6 claim | `auction_claim` | `storage → character` | — |
| L1 NPC buy | `npc_shop_buy`; failure → `npc_shop_buy_refund` | `character → region(NPC location)`; refund reverses | commit → HTTP to inventory → compensating op (documented) |
| L2 NPC sell | `npc_shop_sell` | `region(NPC location) → character` | order unchanged (residual risk, 3.12) |
| L3 quest reward | `quest_reward`, key `quest_reward:cq:<id>` | `region(quest-giver NPC location, else player location) → character` | conditional status update of the quest record **first**, posting second, **one commit** → no double pay |
| L4 plot/house purchase | `house_purchase` | `character → region(plot.region_id)` | helper no longer commits → callers commit explicitly |
| L5 build / unlock / upgrade | `house_build` | `character → region(plot)` | same |
| L6 house tax | `house_tax` | `character → region(plot)` | same |
| L7 house resale | `house_resale` | `buyer → seller`, one operation | one commit with the ownership change |
| region deletion | `treasury_closed` | `region → country` (either sign) | in the `delete_region` txn before the delete; account inactive |
| country deletion | `treasury_closed` | each region → country, then `country → world` | in the `delete_country` txn |
| admin emission | `admin_emission` | `emission → region/country/world treasury` | `apply_tax=False` |

Region/country creation needs no hook — treasury accounts are created lazily.

### 3.5 Lock order and contention

In any transaction that moves gold: **(1)** business rows locked by the caller (`auction_listings`, trade, house/plot,
quest record, dungeon session) → **(2)** `characters` rows by ascending id (`lock_characters` / helper's ordered apply)
→ **(3)** `econ_accounts` rows by ascending id (region and its country in the same ordered pass). Because the helper nets
per account and sorts, no transaction holds a treasury row while waiting for a character row. Treasury rows are hot but
held only from the helper call to commit (no HTTP inside). With ~30 players this is ample; the stage-2 tick must use the
same order. No new deadlock retry loop in stage 1.

### 3.6 API Contracts (character-service)

New code in `app/economy_api.py` (router) + `app/economy_crud.py`, included from `main.py`. Covered by the existing
nginx `location /characters/` — **no nginx change**. Amounts are JSON integers. Errors in Russian.

#### `GET /characters/economy/currency` — public
Response `200`: `{ "name": "Золото", "genitive": "золота", "one": "золотой", "few": "золотых", "many": "золотых", "short": "зол." }`

#### `GET /characters/admin/economy/summary` — `economy:read`
```json
{
  "currency": { "name": "Золото", "genitive": "золота", "one": "золотой", "few": "золотых", "many": "золотых", "short": "зол." },
  "totals": { "issued": 101189503, "held": 101189503, "players": 101137997, "npcs": 51360,
              "escrow": 0, "auction_storage": 146, "region_treasuries": 0, "country_treasuries": 0, "world_treasury": 0 },
  "invariant": { "ok": true, "ledger_sum": 0, "escrow_expected": 0, "escrow_actual": 0,
                 "storage_expected": 146, "storage_actual": 146,
                 "drifting_characters": [ { "character_id": 5, "name": "…", "balance": 100, "ledger": 90 } ] },
  "countries": [ { "account_id": 12, "country_id": 1, "name": "Мидденгерд", "balance": 0, "is_active": true,
                   "regions": [ { "account_id": 30, "region_id": 9, "name": "Мэттанхейм", "balance": -120, "is_active": true } ] } ],
  "system_accounts": [ { "account_id": 1, "kind": "emission", "name": "Эмиссия", "balance": -101189503 } ],
  "settings": { "country_tax_rate": 0.1 }
}
```
`invariant.ok` = ledger_sum == 0 and both escrow/storage pairs equal and no drifting characters. `drifting_characters`
capped at 50. Current names come from `Countries`/`Regions` (snapshot name for deleted ones).

#### `GET /characters/admin/economy/accounts?kind=&q=&page=1&page_size=50` — `economy:read`
`{ "items": [ { "account_id", "kind", "ref_id", "name", "balance", "is_active" } ], "total", "page", "page_size" }`
(`q` searches character/region/country names; character balance from `characters`; `page_size ≤ 100`).

#### `GET /characters/admin/economy/operations` — `economy:read`
Query: `account_id?`, `character_id?`, `op_type?` (∈ OP_TYPES), `region_id?`, `date_from?`, `date_to?` (ISO dates),
`page=1`, `page_size=50 (≤ 100)`; ordered by `id DESC`.
```json
{ "items": [ { "id": 77, "op_type": "auction_buyout", "created_at": "2026-10-29T10:00:00", "source_service": "inventory-service",
               "location_id": 197, "region_id": 9, "actor_user_id": null, "comment": null, "metadata": { "listing_id": 3 },
               "postings": [ { "from": { "account_id": 40, "kind": "character", "ref_id": 5, "name": "Ашари" },
                               "to":   { "account_id": 4, "kind": "auction_escrow", "ref_id": 0, "name": "Ставки аукциона" },
                               "amount": 500, "leg_type": "main" } ] } ],
  "total": 1, "page": 1, "page_size": 50 }
```

#### `POST /characters/admin/economy/emission` — `economy:emit`
Request `{ "account_id": 30, "amount": 100000, "comment": "Стартовая казна" }`. Target kind ∈ {`region_treasury`,
`country_treasury`, `world_treasury`}; `1 ≤ amount ≤ 10^12`; comment 3–500 chars (stripped). Response `200`
`{ "operation_id": 78, "account_id": 30, "balance": 99880 }`. `400` wrong kind/validation, `404` unknown account.

#### `POST /characters/admin/economy/adjust` — `economy:adjust`
Request `{ "account_id": 40, "delta": -500, "comment": "Возврат за баг" }`. Any kind except `emission`, `adjustment`,
`auction_escrow`, `auction_storage`; `delta ≠ 0`, `|delta| ≤ 10^12`; comment required. Negative delta below zero on a
non-negative account → `400` «Недостаточно средств на счёте». Response as emission.

#### `GET /characters/admin/economy/settings` — `economy:read`; `PUT /characters/admin/economy/settings` — `economy:settings`
Body/response `{ "currency": { "name", "genitive", "one", "few", "many", "short" }, "country_tax_rate": 0.1 }`.
Forms 1–50 chars (short 1–20), stripped, `<` `>` rejected; rate 0–0.5. PUT clears character-service's cache; other
services pick it up within 60 s.

#### Changed internal/admin contracts (backward compatible — new fields optional)
- `POST /characters/{id}/add_rewards` (`X-Internal-Token`): request adds `gold_op_type: str = "battle_reward"`
  (∈ battle_reward, battle_pass_reward, dungeon_reward), `location_id: Optional[int]`,
  `payer: "location" | "world" = "location"`, `idempotency_key: Optional[str]` (≤ 128). Response adds `duplicate: bool = False`.
- `POST /characters/internal/deduct-gold`: request adds optional `location_id`, `op_type` (default `dungeon_expense`),
  `idempotency_key`. No caller remains after the dungeon change; kept for compatibility.
- `PUT /characters/admin/{id}`: shape unchanged; a changed `currency_balance` additionally requires `economy:adjust`
  (`403` «Недостаточно прав для изменения баланса») and is executed as `admin_adjust` (absolute target → delta under
  lock, comment «Правка в карточке персонажа»). Same for NPC create/update with non-zero balance.

### 3.7 Security Considerations
- **Authentication:** admin economy endpoints — JWT via user-service `/users/me` + `require_permission` (`economy:read|emit|adjust|settings`).
  Currency endpoint public (non-sensitive, read-only, cached). Internal endpoints keep `X-Internal-Token` + nginx 403.
- **Rate limiting:** existing nginx `/characters/` limits; no new zone (admin-only writes; the public GET is cheap).
- **Input validation:** Pydantic v1 validators (positive int amounts with upper bound, comment length, kind/op_type
  whitelists, dates); parameterised SQL only; currency forms reject `<`/`>`.
- **Authorization:** money can be created only from source accounts and only by `genesis`/admin op types (enforced in
  `econ_core`); balance edits in the character card need `economy:adjust`.
- **Audit:** every admin money action is an operation with `actor_user_id` + mandatory comment; journal is append-only
  (no update/delete endpoints). Error messages never leak SQL or stack traces.

### 3.8 Currency name rollout
- **Backend** (user-facing strings only; docstrings/logs untouched): character-service (teleport, deduct-gold, admin
  validation), inventory-service (auction notifications, trade errors), locations-service (houses, NPC shop),
  dungeon-service (`gameplay.py` errors, merchant message, player-facing `generator_texts.py`). Amounts via
  `format_currency(n, forms)`, «Недостаточно {forms.genitive}». Already-stored notifications stay as they are.
  character-attributes-service and user-service: comments/docstrings only — no change.
- **Frontend:** `src/api/economy.ts` (public GET), `src/redux/slices/economySlice.ts` (`currency: CurrencyForms`,
  `status`, `error`; thunk `fetchCurrencyForms` dispatched once in the app shell), `src/utils/currency.ts`
  (`pluralRu`, `formatCurrency(n, opts?)`, `DEFAULT_CURRENCY_FORMS`, module mirror `getCurrencyForms()` /
  `setCurrencyForms()` for non-React code such as `teleportSlice.ts`), `src/hooks/useCurrency.ts`
  (`{ forms, format }` from the slice, re-renders on load). Fetch failure → defaults **and** a Russian toast
  «Не удалось загрузить название валюты». Replace every hardcoded «золот…/зол./монет» in user-facing text (2.6 list);
  grep must come back clean except comments. Text replacement alone does not trigger the Tailwind migration; a `.jsx`
  file whose logic changes must become `.tsx`.

### 3.9 Frontend Components (admin)
- `src/components/Admin/EconomyPage/EconomyPage.tsx` — route `/admin/economy` in `App.tsx` with
  `<ProtectedRoute requiredPermission="economy:read">`; tile «Экономика» in `AdminPage.tsx` (module `economy`). Tabs:
  - `EconomySummary.tsx` — stat cards (Выпущено / На руках / Игроки / НПС / Ставки / Хранилище аукциона / Казны регионов /
    Казны стран / Казна Скитальцев), invariant badge («Сходится» / red with details + drift list), collapsible
    country → region tree with balances (negative highlighted).
  - `EconomyJournal.tsx` — filters (op type with Russian labels, account search via `/accounts`, region, date range),
    paginated (`AdminPagination`), each operation expandable to its legs; table on `md+`, cards below.
  - `EconomyActions.tsx` — «Эмиссия» (visible with `economy:emit`) and «Корректировка» (with `economy:adjust`): account
    picker, amount, mandatory comment, confirm dialog; refreshes the summary after success.
  - `EconomySettings.tsx` — currency forms with live preview (1 / 3 / 5 / 21 / short), tax rate in %; editable with
    `economy:settings`, read-only otherwise; on save re-dispatches `fetchCurrencyForms`.
  - API `src/api/economyAdmin.ts`, types `src/types/economy.ts`. Tailwind + design-system classes, no `React.FC`,
    360 px+, every error as a Russian toast.
- `Admin/CharactersPage/tabs/GeneralTab.tsx` — balance input editable only with `hasPermission('economy:adjust')`,
  otherwise read-only with hint «Баланс меняется через раздел «Экономика»»; 403 shown as toast.

### 3.10 Data Flow Diagrams
```
NPC shop buy:
Frontend → nginx → locations-service
  txn1 { resolve NPC location → region; post_operation(npc_shop_buy: char → region [+ region → country tax]) } COMMIT
  HTTP → inventory-service (add item)
  on failure: txn2 { post_operation(npc_shop_buy_refund: mirror of the buy legs — region → char, country → region tax) } COMMIT

Auction buyout:
Frontend → inventory-service txn { lock listing; post_operation(auction_buyout: buyer→escrow, escrow→prev bidder,
  escrow→storage 95 %, escrow→region 5 % [+ tax]); move item } COMMIT

Battle-pass reward:
battle-pass-service → POST /characters/{id}/add_rewards {gold, gold_op_type: battle_pass_reward, payer: world,
  idempotency_key} → character-service txn { post_operation(world → char) } COMMIT

Dungeon rest:
dungeon-service txn { update session; post_operation(dungeon_expense: char → region(dungeon location)) } COMMIT

Admin:
Frontend /admin/economy → nginx → character-service /characters/admin/economy/* → user-service /users/me (RBAC) → MySQL
```

### 3.11 Deploy and migration ordering
Deploy restarts everything (`down` + rebuild). If inventory/locations/dungeon come up before character-service has applied
027 (seconds), their money actions fail with a clean error until it has — accepted for pre-alpha. Old code cannot write
between the genesis snapshot and the new code (containers are down). No transitional modes, no dual writes to
`gold_transactions`.

### 3.12 Residual risks / out of scope (developers add them to `docs/ISSUES.md`)
- NPC sell (L2): item removed via HTTP before the credit — a failed credit loses the item (world sum unaffected).
- After a character deletion, its unclaimed `auction_storage` rows / active winning bids stay in the escrow/storage
  accounts (world sum still closes); cleanup is a later task.
- Hot treasury rows under the stage-2 tick — revisit then.
- `gold_transactions` to be dropped in a later stage.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

General for every backend task: Pydantic v1, `python -m py_compile` on all modified files, existing tests of the service
stay green, update `docs/services/<service>.md`, add found/remaining issues to `docs/ISSUES.md` (remove the ones fixed —
e.g. the missing deduct-gold tests entry once Q1 covers it). **No commits, no pushes** (PM/user commit at the end).

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| B1 | **Ledger foundation (character-service):** migration `027_world_economy` (BIGINT balance, 4 tables, singleton + treasury accounts, idempotent genesis per 3.2); ORM models for the 4 tables; canonical `econ_core.py` and sync `econ_ledger.py` per 3.3 (validation, tax legs, savepoint op insert + idempotency, get-or-create accounts, netting, ordered apply, conditional debits, region resolution, currency forms cache, plural/format); `before_flush` guard on `Character.currency_balance`; `tests/econ_contract_cases.py` (shared scenarios + SQLite DDL) | Backend Developer | DONE | `services/character-service/app/alembic/versions/027_world_economy.py`, `app/models.py`, `app/econ_core.py`, `app/econ_ledger.py`, `app/database.py` (guard hook, if that is where events live), `app/tests/econ_contract_cases.py`, `docs/services/character-service.md` («Economy ledger» section with caller rules) | — | `alembic upgrade head` on the local DB succeeds; re-running is a no-op; after it: Σ characters balance + Σ econ_accounts.balance = 0, escrow/storage accounts equal the auction sums; `downgrade -1` works; py_compile OK |
| B2 | **character-service writers over the helper:** C1 starter kit (resolve start location first), C2 `add_rewards` (new optional fields, payer, idempotency → `duplicate` skips XP and gold), C3 `deduct-gold` (new optional fields), C4 teleport, C5 admin balance edit (`economy:adjust` + delta under lock), C6 NPC create/update gold, C8 deletion posting in the same commit; remove `log_gold_transaction` usage; currency strings via `format_currency` | Backend Developer | DONE | `app/crud.py`, `app/main.py`, `app/schemas.py` | B1 | No remaining ORM/raw write to `currency_balance` outside the helper (grep); invariant holds after each flow (manual check via SQL); old callers without new fields still work |
| B3 | **Economy API (character-service):** public `GET /characters/economy/currency`; admin `summary`, `accounts`, `operations`, `emission`, `adjust`, `settings` GET/PUT per 3.6 with RBAC and validation; settings cache invalidation | Backend Developer | DONE | `app/economy_api.py` (new), `app/economy_crud.py` (new), `app/schemas.py` (economy schemas section), `app/main.py` (include_router only) | B1 (may run in parallel with B2 — different files; coordinate the two-line edits in `main.py`/`schemas.py`) | curl: endpoints return the 3.6 shapes; 401/403 without permission; emission changes treasury balance and summary stays `ok=true` |
| B4 | **inventory-service:** copy `econ_core.py` + sync `econ_ledger.py` verbatim from B1; migration `033_auction_listing_region` + model columns; set `location_id/region_id` at listing creation; I1 trade (row lock, status check-and-set, `lock_characters`, single `trade` operation, insufficient funds → 400 Russian); I2–I6 auction flows per 3.4 incl. 5 % commission to region/world treasury; drop the local `log_gold_transaction`; currency strings in notifications/errors | Backend Developer | DONE | `services/inventory-service/app/econ_core.py`, `app/econ_ledger.py`, `app/alembic/versions/033_auction_listing_region.py`, `app/models.py`, `app/crud.py`, `app/main.py`, `app/tests/econ_contract_cases.py` (copy), `docs/services/inventory-service.md` | B1 | Copies byte-identical to character-service; migration up/down OK; after bid → buyout → expiry → claim the summary invariant is `ok` and the commission appears in the region treasury with a tax leg; concurrent double confirm of a trade executes once |
| B5 | **locations-service:** copy `econ_core.py` from B1, write canonical **async** `econ_ledger.py`; replace `deduct_currency`/`add_currency`/`_log_gold_transaction` with the helper (no commits inside); every house flow commits explicitly (L4–L6); L7 resale as one `house_resale` operation; L1 NPC buy + compensating refund op; L2 NPC sell; L3 quest — conditional completion first, posting with idempotency key, one commit; region/country deletion `treasury_closed` postings in the delete txn; currency strings | Backend Developer | DONE | `services/locations-service/app/econ_core.py`, `app/econ_ledger.py`, `app/crud.py`, `app/main.py`, `app/houses.py`, `app/tests/econ_contract_cases.py` (copy), `docs/services/locations-service.md` | B1 | No direct `currency_balance` write left (grep); concurrent quest completion pays once; house resale atomic; invariant `ok` after shop/quest/house/region-delete flows |
| B6 | **dungeon-service:** copy `econ_core.py` (B1) and async `econ_ledger.py` (B5) verbatim; replace `http_clients.add_gold` / `deduct_gold` usages (event gold C2b, rest, revive, merchant C3) with in-transaction `post_operation` against `region(dungeon.location_id)`, before the dungeon commit; insufficient funds → existing Russian errors with `format_currency`; currency strings in `gameplay.py`/`generator_texts.py` | Backend Developer | DONE | `services/dungeon-service/app/econ_core.py`, `app/econ_ledger.py`, `app/gameplay.py`, `app/http_clients.py`, `app/generator_texts.py`, `app/tests/econ_contract_cases.py` (copy), `docs/services/dungeon-service.md` | B1, B5 | Copies identical to their canonicals; rest/revive/merchant/event gold write one operation each in the same txn as the session change; a failed dungeon commit leaves the balance untouched |
| B7 | **battle-pass-service:** gold rewards call `add_rewards` with `gold_op_type='battle_pass_reward'`, `payer='world'`, stable `idempotency_key` from the claim; `_progress_earn_gold` / `_progress_spend_gold` read `econ_postings` + `econ_accounts(kind='character')` (earned = postings **to** the characters, spent = postings **from** them, `created_at >= season start`, excluding `genesis`) | Backend Developer | DONE | `services/battle-pass-service/app/crud.py`, `app/http_clients.py` (or wherever the add_rewards call lives), `docs/services/battle-pass-service.md` | B1, B2 | Claim twice with the same key → gold paid once; earn/spend progress equals the ledger sums |
| B8 | **user-service RBAC:** migration `0032` adding `economy:read`, `economy:emit`, `economy:adjust`, `economy:settings` (idempotent, template `0026`); `economy:read` → Moderator (role 3); Admin automatic | Backend Developer | DONE | `services/user-service/alembic/versions/0032_add_economy_permissions.py` (revision id `'0032'`, down `'0031'`) | — | Migration up/down OK; `/users/me` of a moderator lists `economy:read` |
| D1 | **CI copy guard:** add a lightweight job (or step before the test matrix) `econ-contract-copies` that sha256-compares `econ_core.py` ×4, `tests/econ_contract_cases.py` ×4, sync `econ_ledger.py` (character ↔ inventory), async `econ_ledger.py` (locations ↔ dungeon); confirm no nginx change is needed for `/characters/economy/*` and `/characters/admin/economy/*` (both nginx files) | DevSecOps | DONE | `.github/workflows/ci.yml` (deploy must `needs` the new job), optionally `scripts/check_econ_copies.sh` | B4, B5, B6 | Job passes on identical copies and fails when one byte differs (verified locally with the script) |
| F1 | **Currency in the frontend:** `api/economy.ts`, `redux/slices/economySlice.ts` (+ store registration, fetch once in app shell, toast on failure, defaults), `utils/currency.ts`, `hooks/useCurrency.ts`; replace every hardcoded currency word/abbreviation in user-facing text (2.6 list: houses, auction, trade, NPC shop/auction, teleport + `teleportSlice`, dungeon room, perks, admin teleport/plot/battle-pass forms, header chip, mobile header, character panel) | Frontend Developer | DONE | `src/api/economy.ts`, `src/redux/slices/economySlice.ts`, `src/redux/store.*`, `src/utils/currency.ts`, `src/hooks/useCurrency.ts`, ~41 component files from 2.6 | B3 (contract fixed in 3.6 — coding may start in parallel; live check needs B3) | `grep -rniE "золот|зол\.|монет" src` returns only comments/defaults in `utils/currency.ts`; changing forms in DB changes UI text after reload; `npx tsc --noEmit` + `npm run build` pass |
| F2 | **Admin «Экономика»:** tile in `AdminPage.tsx`, protected route `/admin/economy`, `EconomyPage` with tabs Summary / Journal / Actions / Settings per 3.9; `GeneralTab.tsx` balance field gated by `economy:adjust` | Frontend Developer | DONE | `src/components/Admin/EconomyPage/*.tsx` (new), `src/api/economyAdmin.ts`, `src/types/economy.ts`, `src/components/Admin/AdminPage.tsx`, `src/components/App/App.tsx`, `src/components/Admin/CharactersPage/tabs/GeneralTab.tsx` | B3, B8, F1 | Works at 360 px; every API error toasted in Russian; emission/adjust update the summary; settings preview correct (1/3/5/21); tsc + build pass; no `React.FC`; Tailwind/design-system only |
| Q1 | **QA character-service:** contract tests (`test_econ_contract.py` over `econ_contract_cases`), unit tests of `econ_core` (plural forms, tax rounding, netting/order, validation incl. "no emission outside admin ops"), helper (insufficient funds, idempotency, lazy accounts, negative treasury allowed, escrow not), genesis logic (factor the SQL so it is testable or test via a migration fixture), economy API (shapes, RBAC 401/403, validation, invariant `ok`/drift detection), add_rewards (payer/location/world, duplicate skips XP+gold), deduct-gold, teleport, admin balance edit permission, deletion posting, ORM guard | QA Test | DONE | `services/character-service/app/tests/test_econ_*.py` | B1, B2, B3 | pytest passes; covers every flow C1–C8; includes security cases (SQL-injection-like `q`, `<script>` in currency forms rejected, unauthorized access) |
| Q2 | **QA inventory-service:** contract tests through the sync copy; trade (insufficient funds, double confirm executes once, negative balances impossible), bid/outbid refund, buyout with commission + tax legs + region/world fallback, lazy expiry settlement, cancel, claim; escrow/storage account sums match the auction tables after each scenario; migration columns set at listing creation | QA Test | DONE | `services/inventory-service/app/tests/test_econ_*.py` | B4 | pytest passes; invariant asserted after every scenario |
| Q3 | **QA locations-service + dungeon-service:** contract tests through both async executors; NPC buy (+ refund on inventory failure, mocked), NPC sell, quest reward (second completion pays nothing), house purchase/build/tax (atomic with business rows), house resale (one operation, rollback leaves both balances intact), region/country deletion postings; dungeon rest/revive/merchant/event gold in one txn, failure before commit leaves balance unchanged | QA Test | DONE | `services/locations-service/app/tests/test_econ_*.py`, `services/dungeon-service/app/tests/test_econ_*.py` | B5, B6 | pytest passes in both services (dungeon within the 30 s CI timeout per test) |
| Q4 | **QA battle-pass + RBAC:** add_rewards call payload (mocked HTTP) with key/op type/payer; earn/spend progress from `econ_postings` (genesis excluded, refunds/trades counted as today); `TestEconomyPermissions` section in `test_rbac_permissions.py` seeding the 4 new permissions explicitly (admin gets all, moderator only `economy:read`, editor none) with updated counters | QA Test | DONE | `services/battle-pass-service/app/tests/test_*gold*.py`, `services/user-service/tests/test_rbac_permissions.py` | B7, B8 | pytest passes in both services |
| R1 | **Review:** cross-service contract check (add_rewards/deduct-gold backward compatible, copies identical), grep that no code writes `currency_balance` outside the helpers, security checklist, all py_compile/pytest/tsc/build re-run; **live**: run migrations on local DB, open `/admin/economy` (desktop + 360 px), do emission, an NPC buy, a quest, an auction bid+buyout, a trade, a dungeon rest — summary invariant stays «Сходится» and the journal shows each operation with correct legs; currency rename reflects in UI and a backend error message | Reviewer | TODO | all | B1–B8, D1, F1, F2, Q1–Q4 | Checklist passed, zero console errors, invariant `ok` after the live scenario |

Parallelism: B1 and B8 start immediately. After B1: B2, B3, B4, B5 in parallel (B2/B3 share only the router include line).
B6 after B5; B7 after B2. F1 can start with B1 (contract fixed), F2 after B3+B8+F1. D1 after the copies exist.
QA tasks follow their backend tasks; R1 last.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-10-29
**Result:** FAIL (one blocking test-isolation bug; the feature itself works live)

#### Issues Found
| # | File:line | Description | Severity | Assigned To | Status |
|---|-----------|-------------|----------|-------------|--------|
| 1 | `services/locations-service/app/tests/test_econ_locations_flows.py:450` (helper `_complete_quest` :404) | `test_two_concurrent_completions_on_separate_connections_pay_once` runs two `_complete_quest` coroutines through `asyncio.gather`; each enters its own `patch.object(...)` stack on the same module attributes. The contexts interleave, so the second one saves the first one's mock as "original" and restores it on exit — `main.check_not_activity_locked`, `main._track_cumulative_stats`, `crud.get_character_xp_multiplier`, `crud/main.httpx.AsyncClient` stay mocked for the rest of the session. The full locations suite then fails **19 tests** in `test_xp_books.py`, `test_houses.py` (sleep/activity lock), `test_internal_headers.py`, `test_quest_complete_real_session.py` (`1704 passed, 19 failed`, reproduced twice; HEAD `0c509ef` = 1622 passed). Repro: `pytest 'tests/test_econ_locations_flows.py::TestQuestReward::test_two_concurrent_completions_on_separate_connections_pay_once' tests/test_xp_books.py` → 12 failed. CI runs the whole suite → **deploy would be blocked**. Fix: apply the patches once around the `gather` (split `_complete_quest` into "patch context" + "call"), never inside each concurrent coroutine. | BLOCKING | QA Test | FIX_REQUIRED |
| 2 | `services/frontend/app-chaldea/src/components/Admin/EconomyPage/EconomyJournal.tsx:50-52` | Journal "Сумма" adds every non-tax leg: a 60 buyout shows 150 (60 + 30 refund + 57 + 3), an outbid shows 55. Reads like the operation's value. Consider the largest `main` leg, or label the column «Оборот по проводкам». | LOW | Frontend Developer | OPTIONAL |
| 3 | `services/frontend/app-chaldea/src/components/Admin/EconomyPage/EconomyPage.tsx:65` | Admin intro text says «Каждая монета мира…» — generic noun, not the currency name; admin-only, harmless. | LOW | Frontend Developer | OPTIONAL |

#### Code review notes (no action)
- Contracts: `add_rewards` / `deduct-gold` new fields optional with defaults + whitelisting validators; battle-service call unchanged (gold=0 → no operation); battle-pass sends `gold_op_type=battle_pass_reward`, `payer=world`, stable key; dungeon-service no longer calls either (in-txn `_charge_gold`/`_pay_gold`). Frontend `types/economy.ts` matches 3.6 shapes (verified against live responses).
- `sh scripts/check_econ_copies.sh` → all 8 copies identical; CI `econ-contract-copies` job gates deploy.
- Writers: only `econ_core.SQL_DEBIT/CREDIT_CHARACTER` update `currency_balance` (plus migration NULL→0 and inserts with 0); `econ_accounts` balance only touched by the ledgers/genesis; no code writes `gold_transactions` (model kept read-only).
- Migrations: heads `027_world_economy` (17 chars), `033_auction_listing_region` (26), `0032`; downgrades present; FK columns indexed; genesis guarded by `idempotency_key='genesis'` + `INSERT IGNORE`.
- Security: every `/characters/admin/economy/*` route has `require_permission(economy:read|emit|adjust|settings)`; balance edits in the character/NPC cards additionally need `economy:adjust`; Pydantic validators with Russian messages; `<`/`>` rejected in forms; generic 500 messages; no secrets.
- Frontend: TS only, no `React.FC`, Tailwind/design-system classes, every API call surfaces a Russian error (toast or inline); currency grep clean except comments/examples.
- Known/logged gaps accepted: add_rewards XP-only idempotency (ISSUES.md), NPC sell order (ISSUES.md), auction notifications before commit (ISSUES.md).

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container, EffectRunes filtered) — PASS (no output)
- [x] `npx vite build` — PASS (built in 55 s)
- [x] `py_compile` (27 changed non-test files) — PASS
- [ ] `pytest` — FAIL: character 1735 passed/1 skipped; inventory 1807/1 skipped; **locations 1704 passed, 19 failed** (issue #1; failing files pass in isolation); dungeon 434 passed (exit 0, `--timeout=30`); battle-pass 159; user 762/5 skipped; battle 885/4 skipped
- [x] `docker compose config` — PASS
- [x] Live verification — PASS

#### Live Verification Results (localhost, after restarting the 6 changed services + `nginx -s reload`)
- `/admin/economy` desktop: summary «Сходится», tree, system accounts, journal with expandable legs; 360 px (iframe): no page horizontal scroll (tab bar scrolls inside its own container); console errors: NONE.
- Emission 50 → Мэттанхейм (op 31, `emission → region`), validation 422 Russian, no token 401.
- NPC buy (op 32): Ашари → region 9 19 + tax 1 → Мидденгерд.
- Quest (temporary quest 9113, deleted after): region 9 → Ашари 7; second completion 404, paid once.
- Trade (op 34): one operation, both directions; repeat confirm 400; oversize gold → «Недостаточно золота».
- Auction: bid (op 35 → escrow), outbid (op 36 with refund leg), buyout 60 (op 37: refund 30, storage 57, commission 3 → region, tax floor 0), claim 57 (op 38); escrow/storage sub-invariants equal after each step; bid 10^13 → 422 «Слишком большая сумма».
- Dungeon rest: not re-run (would disturb the open run); B6's ops 27/28 in the journal show `character → region 9` 50 + tax 5 and `region → character` 50.
- Currency renamed to «Крона/крон/крона/кроны/крон/кр.»: admin UI shows «101 189 608 крон», «142 кроны»; inventory-service error became «Недостаточно крон» within the 60 s cache; restored to the original forms, error back to «Недостаточно золота».
- Clean-up: test emission reversed by `admin_adjust −50` (op 39); final summary ok, ledger_sum 0, no drift, issued back to 101 189 558; Годрик moved back to location 197.

---

### Review #2 — 2026-10-29 (PM re-check after fixes)
**Result:** PASS

- Blocking issue fixed: `test_econ_locations_flows.py` — quest patches are applied once around the concurrent
  `asyncio.gather` (`_quest_patches()` + `_call_complete_quest`), no mocks leak into later tests.
  Full locations suite: **1723 passed**.
- LOW fixed: `EconomyJournal.tsx` «Сумма» = largest leg (chained legs are no longer double-counted);
  `EconomyPage.tsx` intro no longer says «монета».
- Frontend `tsc --noEmit` clean, `vite build` OK. Other suites unchanged since Review #1 (all green).

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-10-29 — PM: фича создана, модель согласована с пользователем, начинаю этап 1 (фундамент), запускаю анализ
[LOG] 2026-10-29 01:34 — Analyst: анализ завершён — найдено ~25 точек изменения баланса в 3 сервисах-писателях (character, inventory, locations, + HTTP из dungeon/battle/battle-pass), иерархия мира (6 стран / 27 регионов локально), ~80 мест с «золото/зол.» во фронте и ~55 в бэке, риски: гонки «прочитал-записал» в character-service, неатомарные пары списание/зачисление, эскроу аукциона вне балансов игроков
[LOG] 2026-10-29 01:42 — Architect: спроектирован этап 1 — двойная запись (счета/операции/проводки) в character-service, общий контракт econ_core + тонкие помощники в 4 сервисах (атомарно в своей транзакции, копии сверяет CI), казны регионов/стран/«Казна Скитальцев», налог 10% в страну с каждого поступления, казны могут уйти в минус, порядок блокировок, начальная эмиссия в миграции; 7 API-контрактов, 16 задач (8 бэкенд, 1 DevSecOps, 2 фронтенд, 4 QA, ревью); 6 вопросов к пользователю с рекомендациями в 3.0
[LOG] 2026-10-29 — PM: пользователь согласился со всеми 6 рекомендациями архитектора, запускаю B1, B8, F1
[LOG] 2026-10-29 — Backend Dev: B8 готово — миграция user-service 0032 добавляет economy:read/emit/adjust/settings (идемпотентно), economy:read выдан модератору, админ получает всё автоматически; upgrade/downgrade/повторный upgrade проверены локально, тесты user-service зелёные (754 passed, 5 skipped)
[LOG] 2026-10-29 — Frontend Dev: F1 готово — api/economy.ts, economySlice (грузится один раз в App, при ошибке тост «Не удалось загрузить название валюты» и формы по умолчанию), utils/currency.ts (pluralRu/formatCurrency + зеркало для не-React кода), хук useCurrency; слово валюты заменено в 44 файлах (дома, аукцион, обмен, магазин НПС, телепорт, данж, перки/титулы, награды БП, админ-формы, шапка); миграций .jsx→.tsx не потребовалось; tsc и vite build проходят
[LOG] 2026-10-29 — Backend Dev: B1 готово — миграция 027_world_economy (BIGINT баланс, 4 таблицы, казны 27 регионов и 6 стран, genesis на 101 189 503 из эмиссии; сумма мира = 0, эскроу 0 и хранилище 146 сходятся, повторный прогон и downgrade/upgrade чистые), econ_core.py + econ_ledger.py + tests/econ_contract_cases.py (16 сценариев зелёные на SQLite, живая проверка на MySQL с откатом), страж баланса пока только предупреждает — строгий режим включает B2; тесты сервиса 1295 passed
[LOG] 2026-10-29 03:25 — Backend Dev: B5 готово — locations-service: econ_core.py (копия) + канонический async econ_ledger.py (те же имена, что у sync, без зависимостей от сервиса — dungeon копирует как есть), контрактные сценарии зелёные через async-исполнитель; deduct_currency/add_currency/_log_gold_transaction заменены обёртками charge_character/pay_character/transfer_between_characters (без коммитов); покупка у НПС + компенсирующий возврат, продажа НПС, квест (сначала условная сдача, ключ quest_reward:cq:<id>, один коммит), покупка/стройка/налог дома с явным коммитом, перепродажа дома одной операцией house_resale под блокировкой строки дома, закрытие казн при удалении региона/страны; тексты валюты из настроек; тесты сервиса 1673 passed; живая проверка на локальной БД (покупка, покупка с возвратом, продажа, квест дважды, стройка) — сумма мира 0 после каждого шага; остаточный риск продажи НПС добавлен в ISSUES.md
[LOG] 2026-10-29 03:45 — Backend Dev: B5 доработка — возврат при сбое покупки у НПС теперь зеркалит все ноги покупки, включая налог страны (crud.reverse_operation, apply_tax=False): казны региона и страны возвращаются точно к исходному; тест добавлен
[LOG] 2026-10-29 — Backend Dev: B4 готово — в inventory-service скопированы econ_core/econ_ledger/econ_contract_cases (sha256 совпадают с character-service), миграция 033_auction_listing_region (вверх/вниз проверены), регион лота пишется при выставлении; обмен — блокировка строки обмена, условная смена статуса, lock_characters, одна операция trade; ставка/перебитие/выкуп/истечение/отмена/получение — через эскроу и хранилище, комиссия 5% в казну региона (или «Казну Скитальцев») с налогом 10% в страну; log_gold_transaction удалён, валюта в текстах из настроек; тесты 1696 passed; живой прогон на локальной БД (ставка → перебитие → выкуп → получение → обмен): сумма мира 0, эскроу/хранилище сходятся, комиссия 25 → регион 15 (+23), налог 2 → страна 7
[LOG] 2026-10-29 — Backend Dev: B3 готово — API экономики в character-service (economy_api.py + economy_crud.py, схемы в schemas.py, роутер подключён перед основным): публичная валюта, сводка с инвариантом и деревом казн, счета с поиском, журнал с фильтрами, эмиссия, корректировка, настройки (валидация форм, запрет < >, ставка 0–0.5, сброс кеша); права economy:read/emit/adjust/settings; nginx менять не нужно; живая проверка через nginx: 401 без токена, эмиссия 1000 в казну региона и откат корректировкой — инвариант «ok»; 5 санити-тестов зелёные, остальные падения набора — от незавершённого B2 (crud.log_gold_transaction)
[LOG] 2026-10-29 — Backend Dev: B2 готово — все писатели золота character-service идут через post_operation: стартовый набор (казна стартовой локации, после разрешения локации), add_rewards (новые необязательные поля gold_op_type/location_id/payer/idempotency_key, повтор ключа → duplicate без опыта и золота), deduct-gold (location_id/op_type/ключ), телепорт, правка баланса админом и золото НПС (admin_adjust под блокировкой, нужно economy:adjust), удаление персонажа и НПС (character_deleted в той же транзакции); gold_transactions больше не пишется, log_gold_transaction удалён; страж баланса строгий; тесты 1314 passed, живой прогон на локальной БД — сумма мира = 0 после каждого шага
[LOG] 2026-10-29 — QA: Q1 готово — в character-service 6 новых файлов test_econ_* (421 тест): контрактные сценарии через sync-исполнитель, econ_core (формы 1/2/5/11/21/111, округление налога, неттинг и порядок блокировок, запрет эмиссии вне админ-операций), помощник (откат при нехватке средств, идемпотентность, ленивые счета, минус у казн и запрет у эскроу/хранилища, обновление ORM, страж баланса), genesis миграции 027 на SQLite через прокладку, API экономики (формы ответов, 401/403 по каждому праву, валидация, дрейф и расхождение эскроу, закрытый счёт, <script> в формах, инъекции в q), add_rewards/deduct-gold/телепорт/правка баланса/золото НПС/удаление — после каждого сценария сумма мира 0 и нет дрейфа; весь набор 1735 passed. Замечания без правки: ключ идемпотентности add_rewards защищает только награды с золотом (повтор награды «только опыт» с тем же ключом начислит опыт дважды); страж баланса срабатывает на запись того же значения в просроченный атрибут
[LOG] 2026-10-29 — Backend Dev: B7 готово — battle-pass-service: золото и опыт наград идут в add_rewards с gold_op_type=battle_pass_reward, payer=world и ключом battle_pass_reward:u:{user}:l:{level}:{track} (повторный/параллельный клейм платит один раз); задания «заработать/потратить золото» читают econ_postings + econ_accounts(kind=character) без genesis; тесты 151 passed (зеркала gold_transactions заменены на зеркала журнала); живая проверка: earn совпал с суммой журнала без genesis, повтор ключа → duplicate, баланс +3 один раз; создан docs/services/battle-pass-service.md
[LOG] 2026-10-29 — QA: Q4 готово — battle-pass: добавлены тесты полного тела add_rewards через клейм (idempotency_key, gold_op_type=battle_pass_reward, payer=world; ключ премиум-дорожки отличается; после сбоя доставки повторный клейм шлёт тот же ключ), прогресс earn/spend по журналу (genesis исключён и для трат, возвраты аукциона и обмены считаются с обеих сторон, граница начала сезона включительна); user-service: раздел TestEconomyPermissions (явный сид 4 прав, сверка с миграцией 0032; админ — все 4, модератор — только economy:read, редактор/игрок — ничего); battle-pass 159 passed, user-service 762 passed, 5 skipped
[LOG] 2026-10-29 — QA: Q2 готово — inventory-service: test_econ_contract.py (контрактные сценарии через sync-копию, 46 тестов) и test_econ_inventory.py (63 теста: обмен через эндпоинты, двойное подтверждение, нехватка денег после предложения, ставки/перебития/повышение своей ставки, выкуп с комиссией 5% и налогом, округления, ставка налога из настроек, регион лота через район/родителя/«Казну Скитальцев», истечение, отмена, двойное получение, чужие записи склада, 401/403, отрицательные и огромные суммы); инвариант мира и эскроу/хранилища проверяются после каждого сценария; весь набор 1805 passed, 1 skipped; найден баг: ставка выше MAX_AMOUNT даёт 500 вместо 400 (деньги не двигаются) — добавлен в ISSUES.md
[LOG] 2026-10-29 — Backend Dev: B6 готово — dungeon-service: econ_core.py, async econ_ledger.py и econ_contract_cases.py скопированы байт-в-байт (sha256 совпадают с каноническими); add_gold/deduct_gold по HTTP удалены, вместо них _charge_gold/_pay_gold в gameplay.py — отдых, воскрешение, торговец (dungeon_expense: персонаж → казна региона подземелья) и золото события (dungeon_reward, ключ dungeon_reward:s:<сессия>:r:<комната>) проводятся в той же транзакции, что и изменение забега, до коммита; упавший коммит откатывает и проводку; тексты ошибок/сообщений с названием валюты из настроек; «монеты» в generator_texts.py — предметы обстановки, не валюта, оставлены; тесты: test_econ_contract.py (общие сценарии через async-исполнитель) + test_econ_dungeon.py (9 сценариев на настоящем ledger), весь набор зелёный; живая проверка на локальной MySQL (данж 2, Ашари 763): списание 50 → регион 9 +45, страна +5, выплата по ключу дважды платит один раз, откат не меняет баланс, нехватка → отказ; сумма мира 0
[LOG] 2026-10-29 02:30 — Frontend Dev: F2 готово — раздел «Экономика» (/admin/economy, economy:read, плитка в админке): Сводка (итоги, значок «Сходится»/расхождение со списком, дерево страна → регионы, системные счета), Журнал (фильтры по типу/региону/счёту/датам, раскрытие проводок, таблица на md+, карточки на мобильных, время в часовом поясе зрителя), Действия (эмиссия economy:emit и корректировка economy:adjust с выбором счёта и подтверждением), Настройки (формы валюты с живым предпросмотром 1/3/5/21, ставка налога в %, после сохранения валюта перезагружается в economySlice); баланс в карточке персонажа — только с economy:adjust и отправляется лишь при изменении; tsc и vite build проходят; живая проверка: эмиссия 100 в казну Мэттанхейма и корректировка −100 обратно, 360 px без горизонтальной прокрутки, ошибок в консоли нет
[LOG] 2026-10-29 — PM: баг «огромная ставка → 500» исправлен (лимит цен в схемах аукциона + EconomyError → 400), удалён из ISSUES.md; inventory 1807 passed
[LOG] 2026-10-29 — DevSecOps: D1 готово — scripts/check_econ_copies.sh (POSIX sh, sha256sum: econ_core ×4, econ_contract_cases ×4, sync econ_ledger character↔inventory, async econ_ledger locations↔dungeon; при расхождении называет файл и оба хеша, exit 1) и job econ-contract-copies в ci.yml, deploy теперь ждёт его (needs); матрица тестов не тронута; локально: на текущем дереве проходит, с дописанным байтом в копию dungeon падает с именем файла, копия восстановлена (sha256 совпадает); nginx менять не нужно — location /characters/ в обоих конфигах покрывает /characters/economy/* и /characters/admin/economy/*
[LOG] 2026-10-29 — QA: Q3 готово — locations-service: test_econ_locations_flows.py (49 тестов на настоящем async-ledger): покупка у НПС через маршрут (цена с харизмой, налог стране, возврат при отказе/недоступности инвентаря — все казны точно к исходному, склад не трогается), продажа НПС, НПС без региона → «Казна Скитальцев», чужой персонаж → 403, нулевое/отрицательное/огромное количество; награда квеста из региона квестодателя, проигранная гонка статуса ловится ключом (409, ни золота, ни опыта второй раз), две одновременные сдачи на разных соединениях платят один раз; дома — покупка/стройка/открытие слоя и клетки/улучшение/налог: падение между проводкой и коммитом не оставляет ни золота, ни дома/комнаты/разблокировки, перепродажа одной операцией без налога, сбой и нехватка денег оставляют оба баланса и владельца, участок без региона платит миру, лимиты цены продажи; удаление региона/страны — treasury_closed в той же транзакции (плюс и минус казны, откат при сбое удаления). dungeon-service: test_econ_dungeon_flows.py (14 тестов): сбой коммита отдыха/воскрешения откатывает и золото, и изменение забега, нехватка → участник мёртв, склад и мешок торговца целы, количество × цена одной операцией с налогом, огромное количество → 409, не-лидер → 403, выплата события с уже использованным ключом не платит, но выбор записан; инвариант мира 0 после каждого сценария. locations 1723 passed, dungeon 434 passed. Багов не найдено (замечание: ShopBuyRequest.quantity без верхней границы — огромное количество отклоняется как нехватка денег, деньги не двигаются)
[LOG] 2026-10-29 04:30 — Reviewer: проверка R1 завершена — FAIL. Живой прогон чистый (эмиссия, магазин НПС, квест, обмен, ставка/перебитие/выкуп/получение, переименование валюты в UI и в ошибке бэкенда, 360 px, консоль без ошибок; сумма мира 0 после каждого шага, тестовая эмиссия откачена). Блокер: тест параллельной сдачи квеста в locations (test_econ_locations_flows.py:450) оставляет моки после себя — весь набор locations падает на 19 тестах, CI заблокирует деплой. Остальные наборы зелёные, tsc/build/py_compile проходят
[LOG] 2026-10-29 — PM: исправлен блокирующий тест локаций и две мелочи админки, локации 1723 passed, ревью PASS
[LOG] 2026-10-29 — PM: этап 1 выкачен на прод (0c509ef..109b5a6), бэкап /root/backup-pre-feat181-20261029-0337.sql.gz, CI зелёный, миграции character 027 / inventory 033 / user 0032, сумма золота мира = 0, nginx перезагружен. Дальше — этап 2
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_pending_
