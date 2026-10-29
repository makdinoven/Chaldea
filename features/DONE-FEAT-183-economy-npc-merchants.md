# FEAT-183: Экономика, этап 3 — торговцы НПС

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-10-29 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Продолжение FEAT-181 (общая модель — раздел 1 `features/FEAT-181-world-economy.md`) и FEAT-182 (живые регионы,
`features/DONE-FEAT-182-economy-living-regions.md`; контракт чтения для этапа 3 — там же, 3.9).

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас торговец НПС — витрина с ценами из админки: игрок платит в казну региона, продажа торговцу оплачивается из
казны, своих денег и живого склада у торговца нет, цены не зависят от того, что творится в регионе.

Этап 3 делает торговца участником экономики: у него своя касса (баланс НПС), свой склад, цены зависят от
региона, и он торгует не только с игроками, но и с жителями региона в фоне (раз в 6 часов, вместе с пересчётом).

### Бизнес-правила (черновик, уточняется вопросами ниже)
- Касса торговца = баланс персонажа-НПС (он уже есть в книге счетов, решение FEAT-181 Q4).
- Покупка игроком у торговца: деньги игрока → касса торговца (налог по правилам книги счетов).
- Продажа игроком торговцу: касса торговца → игрок; если денег в кассе нет — торговец не может купить.
- Цены в лавке зависят от цены группы товара в регионе (×0,5–×3); предметы вне рынка — по фиксированной цене.
- Фоновая торговля раз в 6 часов: торговец продаёт жителям и закупает у региона, деньги ходят между кассой и
  кошельком жителей, товар — между складом торговца и запасом региона.
- Деньги по-прежнему не появляются и не исчезают (инвариант книги счетов).

### UX / Пользовательский сценарий
1. Игрок заходит к торговцу: видит товары с ценой и остатком, цена отличается от региона к региону.
2. В голодном регионе еда дорогая и её мало; в шахтёрском руда дешёвая.
3. Игрок продаёт торговцу вещь — торговец платит из кассы; бедный торговец может отказать.
4. Через 6 часов склад торговца меняется: что-то раскупили жители, что-то он докупил.

### Edge Cases
- Торговец без региона / в регионе без симуляции.
- Касса торговца пуста или огромна.
- Предмет вне рынка (свитки, рецепты, квестовые, легендарные+).
- Админ правит ассортимент/цены вручную.

### Вопросы к пользователю (2026-10-29: «Делай как рекомендуешь» — все ответы по рекомендации PM)
- [x] Касса пуста, игрок продаёт → **торговец отказывает** («У меня сейчас нет на это денег»), без частичной цены.
- [x] Цены → цена из админки = **базовая**, регион двигает её ×0,5–×3 по цене группы товара; вне рынка (свитки,
  рецепты, квестовые, легендарные+) — фиксированная цена.
- [x] Склад → **конечный остаток** у каждого товара; раз в 6 часов торговец докупает у региона (касса → кошелёк
  жителей, товар списывается с запаса региона); мало группы в регионе — докупит мало.
- [x] Что берёт у игрока → только **свой ассортимент + вещи тех же групп товаров** (кузнец — оружие/броня, травник —
  травы/зелья); купленное у игрока **оставляет и перепродаёт**.
- [x] Фоновая торговля → жители раз в 6 часов покупают у торговца (кошелёк жителей → касса, товар со склада уходит
  в регион); **налог с выручки торговца в казну региона** по ставке налога региона.
- [x] Торговец вне живого региона (регион без шаблона, без региона, данж, служебная локация) → **как сейчас**:
  фиксированные цены, платит/получает казна; в новой экономике только торговцы живых регионов.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Scope: stage 3 «NPC merchants» (own cash, own stock, region-dependent prices, 6 h background trade). Line numbers are
against `main` @ `297dc24`. DB numbers come from the **local** dev DB (`fogdatabase`), which is an outdated copy of the
lore — the real assortment lives on prod; **re-count on prod before sizing migrations/seeding** (not done: read-only, no prod).

### 2.0 Factual answers for product questions (current behaviour)

| Question | Answer today |
|---|---|
| Does a merchant have finite stock? | **Optional per row.** `npc_shop_items.stock` NULL = unlimited, integer = finite. It only ever **decreases** (player buys); nothing restocks it except an admin edit. Selling to the merchant does **not** add to it. |
| Do players sell arbitrary items to any merchant? | **No.** Only items that appear in **that NPC's own shop list** with `is_active = 1 AND sell_price > 0` (`crud.find_sell_price_for_item` `locations-service/app/crud.py:4632-4645`). Stock (even 0) is not checked. Anything else → 400 «Этот NPC не покупает данный предмет». The sell tab in the UI only lists inventory items matching the shop's `sell_price > 0` rows (`NpcShopModal.tsx:202-207`). |
| What sell price is paid? | The row's fixed `sell_price` × quantity, **no** charisma bonus, no dependency on item enhancement/sockets/durability (inventory removes bag rows by quantity, `inventory-service/app/main.py:669-699`; equipped items cannot be sold). Admin UI pre-fills `sell = floor(items.price·0.5)`, `buy = items.price` (`NpcShopEditor.tsx:117-120`). |
| Who receives / pays the money now? | Buy: player → **treasury of the NPC's region** (+10 % region → country tax). Sell: region treasury → player (treasury may go negative). The merchant's own `currency_balance` is **never touched**. |
| Charisma? | Buy only: discount `min(charisma·0.2, 50) %`, `ceil(buy_price·(1−d))` (`locations-service/app/main.py:2721-2725, 2832-2839`). At 250 charisma a 50 % discount meets the default 50 % sell price → buy→sell at the same merchant is break-even. |
| How many merchants have shops? | Locally **1 shop row in total** (NPC 33 «Петя», item 1 «Зелье здоровья (малое)», buy 20 / sell 10 / stock 98). 146 NPCs have `npc_role = 'merchant'` (spread over 13 regions), 14 of them with gold > 0 (max 8 000, Σ merchants 25 640). Prod numbers unknown. |

### 2.1 Affected Services

| Service | Type of changes | Files |
|---|---|---|
| locations-service | shop buy/sell legs (player ↔ NPC cash instead of treasury), dynamic price on read/buy/sell, stock handling, admin shop CRUD (new fields), owner of `npc_shop_items` → Alembic migration (head `052_house_rooms_6b`) | `app/models.py:461-471`, `app/schemas.py:1040-1095`, `app/main.py:2617-3010`, `app/crud.py:4263-4390, 4414-4545, 4594-4645`, `app/econ_core.py` (copy), `app/econ_ledger.py` (async canonical) |
| character-service | tick runner (merchant step), possibly new merchant tables/settings + admin API, economy summary/journal labels; owns `econ_*` tables → migration after `029_currency_marks` | `app/econ_tick.py:369-481`, `app/econ_sim.py:345-480`, `app/economy_sim_crud.py:556-610` (effective item group), `app/economy_api.py`, `app/economy_crud.py:150-200`, `app/models.py`, `app/econ_core.py` (canonical) |
| inventory-service / dungeon-service | only the byte-identical `econ_core.py` (and `econ_contract_cases.py`) copies if the contract changes | `app/econ_core.py`, `app/tests/econ_contract_cases.py` |
| frontend | player shop modal (stock, dynamic price, «торговцу нечем платить»), admin shop editor (new semantics of price/stock), economy admin (merchants view, op-type/kind labels) | `components/pages/LocationPage/NpcShopModal.tsx`, `NpcProfileModal.tsx:84-95`, `components/AdminNpcsPage/NpcShopEditor.tsx`, `AdminNpcsPage.tsx:377,548,759,855`, `components/Admin/EconomyPage/*` (`economyLabels.ts`, Journal, Summary) |
| user-service | only if a new permission (e.g. merchant settings) is introduced → migration + `test_rbac_permissions.py` section | — |

### 2.2 Current NPC shop end-to-end

**Table** `npc_shop_items` (locations-service `models.py:461-471`, migration `018_add_npc_shop_items.py`):
`id BIGINT PK, npc_id INT (index, no FK), item_id INT (no FK), buy_price INT NOT NULL, sell_price INT NOT NULL DEFAULT 0,
stock INT NULL, is_active BOOL DEFAULT 1, created_at`. No unique `(npc_id, item_id)` — the same item can appear twice
(sell lookup takes `LIMIT 1`). No updated_at, no per-region data.

**Admin** (`main.py:2620-2689`, all `Depends(get_admin_user)` = admin + moderator, no granular permission):
`POST /locations/admin/npc-shop/{npc_id}/items`, `GET …/{npc_id}/items` (incl. inactive), `PUT /locations/admin/npc-shop/items/{id}`
(buy/sell/stock/is_active; `stock` may be set to NULL), `DELETE …/items/{id}`. Schemas `NpcShopItemCreate/Update`
(`schemas.py:1040-1050`) have **no bounds** (negative prices/stock accepted). crud `create/get_admin/update/delete`
(`crud.py:4266-4347`) commit inside. Frontend: `AdminNpcsPage/NpcShopEditor.tsx` (opened only for `npc_role === 'merchant'`,
`AdminNpcsPage.tsx:759,855`; the backend does not check the role).

**Public read** `GET /locations/npcs/{npc_id}/shop[?character_id=]` (`main.py:2742-2783`): active rows + item card
(`crud.get_npc_shop_items_player` `crud.py:4350-4380`, raw SQL join `items`). Without `character_id` → `NpcShopItemPublicRead`
(base prices, stock); with it → visibility gate (`visibility.require_private_access`) + `discounted_buy_price` from charisma
(HTTP to character-attributes `/attributes/internal/{id}`, `main.py:2696-2718`). `NpcProfileModal.tsx:84-95` calls it to
decide whether to show the «Магазин» button (non-empty list).

**Buy** `POST /locations/npcs/{npc_id}/shop/buy` (`main.py:2786-2921`):
1. ownership, activity lock, FEAT-145 gate «пост-намерение Диалог с НПС» (`_require_npc_gate` `main.py:840-853`);
2. player must be at the NPC's `current_location_id` (`crud.get_npc_location` `crud.py:4594-4603`, `is_npc = 1`; no `npc_status` check);
3. shop row active & belongs to the NPC; `quantity ≥ 1` (no upper bound); **stock check is a plain read** (`:2830`);
4. charisma discount → `total_price`;
5. `crud.charge_character_op` (`crud.py:4414-4439`): one ledger op `npc_shop_buy`, leg `character → treasury_for_location(npc_location)`
   (region treasury, else world treasury «Казна Скитальцев»), +10 % tax leg region → country; **committed before** the HTTP call (`:2853`);
6. HTTP `POST inventory /inventory/internal/characters/{id}/items` (internal token); on non-200 / transport error →
   `_refund` = `crud.reverse_operation` (`crud.py:4442-4465`, op `npc_shop_buy_refund`, mirrors every leg incl. tax, no new tax);
7. `crud.decrement_stock` (`crud.py:4606-4618`: `UPDATE … SET stock = stock - :q WHERE id AND stock >= :q`, commits) **after** the
   item was delivered; its `False` result is ignored → two concurrent buyers of the last unit both pass step 3, both pay and
   both get the item (oversell; stock just stops at the value it had). `_track_cumulative_stats` (items_bought, total_gold_spent).

**Sell** `POST /locations/npcs/{npc_id}/shop/sell` (`main.py:2924-3010`): same gates and location check → `find_sell_price_for_item`
→ HTTP `DELETE inventory /inventory/{cid}/items/{item_id}?quantity=` **with the player's JWT** (bag rows only, largest stack
first) → `crud.pay_character` (`crud.py:4498-4520`) op `npc_shop_sell`, leg `treasury → character` (no tax: dst is a character)
→ commit. The sold item is destroyed (does not go to the merchant's stock or inventory). Known residual risk in
`docs/ISSUES.md` («Продажа НПС: предмет снимается до зачисления золота»): the item is removed before the credit.

**Player UI** `components/pages/LocationPage/NpcShopModal.tsx` (TS, Tailwind): tabs Купить/Продать; buy shows price
(+discount), «В наличии: N» when stock is set, qty input `max = stock ?? 999` (`:299-380`), client-side balance check (`:131`);
sell tab = inventory ∩ shop rows with `sell_price > 0`; every error toasted in Russian; currency via `useCurrency`.

**Not related:** dungeon-service merchant rooms (`gameplay.py:456-460, 4093-4140`) — price/stock in the room JSON
(`extra.merchant_stock`), paid via character-service `deduct-gold` (`dungeon_expense` → treasury of the dungeon's region),
no NPC character. NPC auctioneers (`npc_role = 'auctioneer'`, inventory-service auction) do not use `npc_shop_items`; their
balances (Σ 19 000 locally) stay decorative. Auction flows are unaffected.

### 2.3 NPCs as characters (merchant cash)

- `characters.currency_balance BIGINT` (`character-service/app/models.py:49`), `is_npc`, `npc_role` (free string; `merchant`
  is the admin form default), `npc_status alive|dead`, `current_location_id` (nullable). Ledger account kind `character`
  covers players **and** NPCs (FEAT-181 Q4): the balance lives in `characters.currency_balance` (the `econ_accounts` row
  of kind `character` keeps `balance = 0`); debits are conditional (`SQL_DEBIT_CHARACTER … WHERE currency_balance >= :amount`,
  `econ_core.py:579-583`) → **an NPC can never go negative**; `InsufficientFunds` is raised instead.
- World summary already counts NPC gold (`economy_crud.py:155-171`, `totals.npcs`) → the invariant needs no change.
- Admin edits of NPC gold: create `main.py:2945-3000` (inserted with 0, then `admin_set_balance`), update `main.py:3085-3125`;
  both need `economy:adjust` (`_require_balance_permission`) and post `admin_adjust` from/to the **adjustment** source
  account (money created/destroyed, comment «правка в карточке НПС»). Frontend field `AdminNpcsPage.tsx:548`.
- NPC deletion (`main.py:3144-3205`): `crud.post_character_deletion` (`crud.py:2448-2468`) moves the whole balance to the
  treasury of the NPC's location (`character_deleted`) — but **`npc_shop_items` rows of the deleted NPC are not removed**
  (orphans; harmless today because `get_npc_location` 404s).
- NPC → region: `characters.current_location_id` → `econ_core.SQL_RESOLVE_LOCATION` (`econ_core.py:605-620`, district or
  location region, up to 5 parents) → `treasury_for_location` (`locations-service/app/econ_ledger.py:108-121`); no region →
  world treasury. Locally 1 of 146 merchants has no location. NPCs can be moved by admins (region of a merchant can change).
- Local DB: 146 merchants, 14 with cash > 0 (0…8 000); simulated regions: 5 (`econ_regions` with template), purses Σ 317 266
  (a capital purse starts ≈ 175 000) — merchant cash is 1–2 orders of magnitude smaller than purses.

### 2.4 Items, prices and goods groups

- `items.price INT NULL` (inventory-service `models.py:39`) is the only per-item price. Locally 66 items: 36 NULL, 2 zero,
  28 > 0 (10…2 500). Used only for display (`ItemDetailModal.tsx:583`), admin item form (`ItemForm.tsx:545`), the shop
  editor prefill, and FEAT-182's stage-3 price rule. **No canonical sell/buy price exists in business logic.**
- FEAT-182 3.6 (stage-3 contract): `item_base = items.price if > 0 else econ_goods_groups.base_price`; off-market or no
  group → `item_base` (fixed); else `item_base × econ_region_goods.price_mult` when the region is simulated
  (`template_code IS NOT NULL AND population > 0`), else `item_base`.
- `econ_core.auto_item_group(item_type, resource_subcategory, is_food, item_rarity)` (`econ_core.py:337-364`, all 4 copies)
  + overrides `econ_item_groups(item_id, group_code NULL, off_market NULL)`. **The "effective" merge (override over auto)
  exists only in character-service** (`economy_sim_crud.py:556-605`, Python over raw SQL); locations-service has no
  equivalent. FEAT-182 3.9 promised to put the read SQL into `econ_core` and document the contract in
  `docs/services/character-service.md` — **neither was done** (grep finds no such section/SQL). Stage 3 must add it.
- Off-market: `scroll`, `recipe`, rarity `legendary|mythical|divine|demonic` (`econ_core.py:314-315`), plus manual override;
  items with no group (`misc`, resources without subcategory, …) are treated as off-market by contract.
- Units: region goods are **abstract units** priced at `base_price` (food 2, ore 10, weapons 120, jewelry 200, …, seeded in
  `028_econ_living_regions`); a concrete item has its own `items.price` (e.g. ore 2 500). There is no item → units
  conversion anywhere.

### 2.5 Region simulation hooks

- Tick (`character-service/app/econ_tick.py`), sync, daemon thread `econ_scheduler.py`, slot every 6 h, per region one
  txn in `_process_region` (`:369-481`): `econ_regions` FOR UPDATE → `econ_region_goods` FOR UPDATE (`:383-394`) → read purse
  and treasury (`account_balance`, `:403-406`) → pure `econ_sim.simulate_region` (`econ_sim.py:345-480`) → update rows →
  **one** `region_tick` operation (`:440-449`, legs purse→region tax, country→region grant, region→purse wages, key
  `region_tick:<run>:r:<region>`) → history row → commit. Exceptions roll back the region only.
- Documented lock order (`econ_tick.py:21-22`): business rows (`econ_regions` → `econ_region_goods`) → ledger
  (`post_operation`: `characters` ascending, then `econ_accounts` ascending, `econ_core.apply_steps` `:514-534`). The tick
  touches **no `characters` rows today**; a merchant step would add NPC character locks inside the region txn.
- Natural plug-in points: (a) inside the same txn after `simulate_region` (prices already recomputed; purse balance after the
  tick = `result.purse_after`) with extra legs in the same `region_tick` op or a second op with its own idempotency key
  (`merchant_trade:<run>:r:<region>`); (b) a separate pass after all regions (own txn per merchant/region). The brief's
  order (FEAT-182 §1: «3) цены… 4) торговцы… 5) налог/жалованье») is *between* prices and tax, but in `simulate_region`
  steps 7 (prices) and 8 (money) are one function — inserting between them means splitting the pure function or feeding
  merchant results in.
- `econ_sim` reusable pieces: `price_mult(stock, norm, params)` (`:187`), `norm_stock`, `demand_tick` (`:225`),
  `needs_cost_day` (`:240`), `SimParams` JSON in `econ_sim_settings.params` (new params need no migration, but the Pydantic
  `EconSimParams` must list them). Money in stage 2 flows only purse ↔ treasury ↔ country; consumption is
  stock-only (residents do not pay producers) — merchant trade is the first place where goods and money meet.
- `econ_region_goods.stock` / `price_mult` are written only by the tick and admin edits; nothing in locations-service writes them.

### 2.6 Ledger contract (`econ_core.py`, 4 byte-identical copies, CI job `econ-contract-copies`)

- Kinds (`econ_core.py:30-48`): `character`, `region_treasury`, `country_treasury`, `world_treasury`, `auction_escrow`,
  `auction_storage`, `emission`, `adjustment`, `population_purse`. Merchant cash = existing `character` kind (no new kind).
- Op types (`:74-109`): include `npc_shop_buy`, `npc_shop_buy_refund`, `npc_shop_sell`, `region_tick`. Background trade
  needs either new op types (e.g. merchant ↔ residents) or reuse of `region_tick`; anything new must be added to `OP_TYPES`
  in **all 4 copies** (`character-service` canonical; `inventory-service`, `locations-service`, `dungeon-service`) +
  `tests/econ_contract_cases.py` (4 copies), checked by `scripts/check_econ_copies.sh` (sha256). Async ledger canonical
  = locations-service, copy in dungeon-service.
- Tax rule (`add_tax_legs`, `:465-481`): only inflows **into a region treasury** from `character`, `auction_*`,
  `population_purse` are taxed 10 % to the country. Consequently: player → NPC (char → char), purse → NPC, NPC → purse are
  all **untaxed** under the current rules; an NPC → region treasury payment (e.g. a trade tax / licence) would be taxed.
  If the brief's «налог по правилам книги счетов» means a sales tax on player→merchant purchases, a new leg/rule is needed.
- Refund helper `reverse_operation` (`locations crud.py:4442`) is leg-generic → works for char→char buys unchanged.
- Battle-pass earn/spend missions read `econ_postings` for the player's character accounts op-agnostically
  (`battle-pass-service/app/crud.py:396-445`) — player→NPC payments keep counting as spending.

### 2.7 Cross-service dependencies

- frontend → locations-service shop endpoints (only caller; no other service calls `/npcs/{id}/shop*`; no service other
  than locations-service reads `npc_shop_items`).
- locations-service → character-attributes (charisma), → inventory-service (internal add item; public delete with player JWT).
- character-service tick → would need to read/write merchant data. If the stock stays in `npc_shop_items` (owned by
  locations-service), the tick would write another service's table (shared DB makes it possible; precedent: locations-service
  writes ledger tables; `econ_regions` reads `Regions`). Ownership is an Architect decision.
- nginx: shop routes are under `/locations/` — no change unless a new route prefix is introduced.

### 2.8 DB changes likely

- locations-service migration (owner of `npc_shop_items`): new semantics/columns (e.g. price mode fixed/market, restock
  target, max stock, updated_at), possibly UNIQUE `(npc_id, item_id)` (check duplicates on prod first), bounds.
- character-service migration (owner of `econ_*`): merchant-level settings if the tick owns them (per-merchant cash target,
  markup/spread, which groups he trades), history/journal of background trades.
- Seed/migration of existing rows: current `buy_price`/`sell_price` are admin numbers that would become a fixed override
  or be dropped in favour of the market price — product decision; locally only 1 row, prod unknown.

### 2.9 Risks and open technical questions

1. **Stock race (existing bug, becomes critical with finite merchant stock):** stock checked by a plain read, decremented
   after delivery, result ignored → oversell. Needs a conditional reserve/decrement before the HTTP call with compensation.
2. **Concurrency player buy vs tick:** both sides lock the NPC `characters` row via the ledger; the tick additionally holds
   `econ_regions`/`econ_region_goods` (and possibly shop rows). A deadlock-free design needs one global order, e.g.
   `econ_regions → econ_region_goods → npc_shop_items → characters (asc) → econ_accounts (asc)`, and player flows must
   never lock region rows after characters. The tick's region txn will hold NPC rows for its duration (ms–s) → player buys
   at that merchant wait briefly.
3. **Units mismatch:** region stock is abstract units at `base_price`; merchant stock is concrete items at `items.price`.
   Background trade needs a conversion rule (e.g. value-based: units = item price / group base price) or the merchant
   stock must be abstract per group. Undecided.
4. **Cash scale:** merchant cash (0…8 000 locally, most 0) vs purses (~10⁵) and region income (~25 000/day capital). Without
   seeding, merchants with 0 cash cannot buy from players at all; with huge cash (admin typo) they drain purses/regions.
   Funding source for initial cash = emission (`admin_emission`, needs a comment) or treasury transfer — decision.
5. **NPC without region / region not simulated:** price falls back to `item_base` by contract; background trade must skip
   (no purse); world-treasury NPCs still need a defined money flow.
6. **Off-market items & charisma:** fixed price; with a market price the charisma discount plus `sell = 50 %` default allows
   break-even buy→sell; dynamic prices across regions allow player arbitrage (possibly desired, stage-5 caravans). Need a
   buy/sell spread rule relative to the market price.
7. **Admin manual prices** vs market prices: which wins, and whether `stock` stays admin-editable when the tick also
   rewrites it (lost updates between admin PUT and tick).
8. **Sell order risk** (ISSUES.md MEDIUM) gets worse: with merchant cash the credit can now fail with `InsufficientFunds`
   *after* the item was removed → must check/lock merchant cash before removing the item, or pay first and compensate.
9. **Shop visibility:** the «Магазин» button depends on a non-empty active list; if rows with stock 0 are hidden or the
   merchant is broke, the UX must still show the shop (empty or "нечем платить").
10. **Unvalidated admin input** (negative prices/stock) and **orphan shop rows** after NPC deletion — small, fix in passing.
11. **Contract copies:** any `econ_core` change (new op types, effective-group SQL) must be byte-identical in 4 services or CI fails.
12. **Tests:** locations-service has shop tests (`tests/test_econ_locations_flows.py`, `test_charisma_discount.py`,
    `test_feat171_shop_gate.py`) asserting `npc_shop_buy` pays the region treasury — they will need updating.

---

## 3. Architecture Decision (filled by Architect — in English)

Scope: **stage 3 «NPC merchants»**: merchant cash = NPC balance, finite stock with 6 h restock from the region, prices
from the region, buying from players inside the merchant's goods groups, 6 h background trade with residents, sales tax.
Merchants outside living regions keep today's model (fixed price, treasury pays / receives). Banks, caravans, mint —
later stages.

### 3.0 Open questions for the user — answered 2026-10-29: all four as recommended («Со всем согласен»)

| # | Question | Recommended answer (used in this design) |
|---|----------|------------------------------------------|
| Q1 | Where does a merchant's **starting cash** come from? Today almost all merchants have 0 and could not buy anything from players. | **New money from the mint (emission), by an admin button** «Пополнить кассы торговцев» (same as «Заполнить регионы»): each living merchant is topped up to a target ≈ the cost of **two full restocks** of his shop. Re-clicking adds nothing. Admins can still edit a single NPC's money by hand as today. |
| Q2 | Is the merchant tax paid on **every** sale (to players too) or only on the background trade with residents? | **Every sale**: whatever the merchant takes in — from players or from residents — is taxed at the region's tax rate into the region treasury (and the treasury forwards its usual 10 % to the country). A player's price does not change because of the tax; it is the merchant's cost. |
| Q3 | Prices differ between regions, so a player can buy cheap in one region and sell dear in another. Allowed? | **Yes — that is trade**, limited by the merchant's stock and cash. At **one** merchant at one moment, buying and selling back is never profitable, even with maximum charisma (the buy-back price is capped at the best possible discounted price). |
| Q4 | A successful merchant keeps earning (he sells to residents dearer than he restocks). What does he do with surplus money? | **Spends it in the region**: when his cash is above 3× his target, a quarter of the excess goes to the residents' purse each 6 h (wages, household). So money does not pile up in merchants and an admin typo (huge cash) drains slowly instead of flooding the region. |

### 3.1 Key decisions

1. **Ownership — split by existing owners, no new tables outside them.**
   - `npc_shop_items` (stock, base prices, restock target) stays **owned by locations-service** (Alembic migration
     `053_npc_shop_market`). Player buy/sell, the shop window and the admin shop editor stay there.
   - The **background trade** (resident purchases, restock, merchant upkeep) runs in **character-service** inside the
     existing 6 h region tick (it owns `econ_*`, the tick, the ledger and the region transaction). It writes
     `npc_shop_items.stock` (and inserts nothing) through raw SQL **defined in `econ_core`** — the shared-DB cross-write
     precedent is locations-service writing ledger tables. No merchant table in character-service: per-merchant state is
     the NPC balance (cash), the shop rows (stock) and the ledger operation (journal); all tunables are new keys of
     `econ_sim_settings.params` (JSON, no migration).
2. **A merchant is "living"** iff (pure rule + SQL in `econ_core`, used identically by both services): the NPC exists,
   `is_npc = 1`, `npc_status <> 'dead'`, has a `current_location_id`, that location's `marker_type <> 'dungeon'`, the
   location resolves to a region (`SQL_RESOLVE_LOCATION`) and that region is simulated (`econ_regions.template_code IS NOT
   NULL AND population > 0`). Otherwise the merchant is **legacy** with a reason code `no_location | no_region | dungeon |
   not_simulated | dead`. Legacy = today's money flow (treasury of the NPC's place pays / receives, admin fixed prices,
   only rows with `sell_price > 0` are bought, no restock, no resident trade) — plus the two bug fixes of 3.6 that apply to
   every merchant. The status is computed on every request (an NPC moved by an admin or a region taken out of the
   simulation switches mode immediately; nothing to migrate).
3. **Concrete item ↔ abstract region goods = value-based.** `units_per_item = base_ask / group.base_price` (float), where
   `base_ask` is the row's admin base price (`buy_price`) or, for an item not in the assortment, `item_base`
   (`items.price` if > 0 else `group.base_price`, FEAT-182 3.6). One item therefore always trades against exactly its
   own value in region units, so money and goods move consistently (restock cost = units × base × price_mult ×
   wholesale share).
4. **Prices** (pure functions in `econ_core`, Decimal maths, 3.3): `mult` = the region's `price_mult` of the item's
   effective group for a living merchant and an on-market item; **1** otherwise (off-market, no group, legacy).
   - ask (merchant sells) = `max(1, ceil(base_ask × mult))`; charisma discount on top as today (`min(cha×0.2, 50) %`,
     `ceil`), so the player pays `ceil(ask × (1 − d))`;
   - bid (merchant buys) = `min(floor(base_bid × mult), floor(ask × (1 − MAX_CHARISMA_DISCOUNT)))`, `base_bid` = row
     `sell_price` (admin; 0 = «does not buy this item»), or `floor(item_base × merchant_bid_share)` (default 0.5) for a
     same-group item outside the assortment. bid < 1 → «не покупает». The cap guarantees **bid ≤ the cheapest possible
     ask at the same merchant** → no buy→sell-back profit (Q3). It applies to legacy merchants too (only changes rows
     where an admin set `sell_price > buy_price/2`).
   - wholesale (merchant restocks from the region) = `max(1, floor(base_ask × mult × merchant_wholesale_share))`
     (default 0.5) — merchant margin ≈ 50 % minus tax.
5. **Money legs** (no new account kind; NPC cash = `character` account, never negative by the ledger's conditional debit):
   - living buy `npc_shop_buy`: `player → NPC` (paid amount, `main`) + `NPC → region treasury` (`trade_tax`,
     `floor(paid × econ_regions.tax_rate)`) → the ledger adds `region → country` 10 % automatically (`character` is a
     tax source kind). Legacy buy: unchanged (`player → treasury`).
   - living sell `npc_shop_sell`: `NPC → player`; `InsufficientFunds` = refusal «У меня сейчас нет на это денег» (Q:
     no partial price). Legacy sell: unchanged (`treasury → player`).
   - tick `merchant_trade` (new op, one per region per run, key `merchant_trade:<run>:r:<region>`): per merchant
     `purse → NPC` (resident purchases), `NPC → region` (`trade_tax`), `NPC → purse` (restock payment), `NPC → purse`
     (upkeep, Q4). `metadata.merchants = {npc_id: {sold_items, sold_value, tax, restock_items, restock_value, upkeep}}`.
   - funding: existing `admin_emission` `emission → NPC` (Q1).
   World invariant unchanged (no source accounts in trade ops).
6. **Finite stock & restock.** `stock` stays `NULL = unlimited` **for legacy merchants only** (today's behaviour). For a
   living merchant `NULL` counts as **0** (nothing to sell until restocked); the tick writes a number. New column
   `restock_target` («норма склада») = how many units the merchant tries to hold; migration sets it to
   `COALESCE(stock, 10)`. Off-market rows of a living merchant are not restocked (no region goods to take them from) and
   not sold to residents — their stock is admin-managed as today.
7. **Buying from players (living):** item in the assortment with `sell_price > 0` → row bid; else if the item's effective
   group ∈ the merchant's groups (effective groups of his active, on-market `origin='admin'` rows) and the item is
   on-market → default bid; else (off-market not in assortment, other group, row with `sell_price = 0`) → 400 «Этот NPC
   не покупает данный предмет». Bought items **go to the merchant's stock**: existing row `stock += q`, or a new row
   `origin='player'`, `buy_price = item_base`, `sell_price = floor(item_base × bid_share)`, `restock_target = 0`
   (resold, never restocked; hidden from players and purged by the tick when its stock is 0). Requires
   `UNIQUE(npc_id, item_id)` (migration dedupes).
8. **One global lock order** (3.5) shared by player flows, the tick, admin funding and region fill:
   `econ_regions → econ_region_goods → npc_shop_items (asc id) → characters (asc id) → econ_accounts (asc id)`.
   Player flows **never lock region rows** (prices / tax rate are plain reads of the last tick's state).
9. **Tick integration:** inside the existing per-region transaction of `econ_tick._process_region`, **after** the
   `region_tick` posting (prices already recomputed, purse after tax/wages known), in a **SAVEPOINT**: a failing merchant
   step is rolled back alone and logged, the region step still commits. Order matches FEAT-181 «цены → торговцы → …»
   closely enough (tax/wages of the region are computed from production, not from merchant flows). Idempotency is
   inherited (`last_run_id` guard of the region row + ledger key in the same transaction). The math is a new **pure**
   module `app/econ_merchant.py` (unit-testable without SQL), like `econ_sim`.
10. **RBAC: no new permissions** (no user-service migration). Merchants tab = `economy:read`; «Пополнить кассы» =
    `economy:settings` + `economy:emit` (like «Заполнить регионы»); shop editor stays `get_admin_user` (admin +
    moderator) as today.
11. **No manual "restock now" button** (YAGNI): admins can type a stock number in the shop editor (goods are not
    conserved, only money is) or run the existing «Пересчитать сейчас».

### 3.2 DB Changes

**locations-service migration `053_npc_shop_market`** (owner of `npc_shop_items`; revision id ≤ 32 chars):
```sql
-- 1. Dedupe (npc_id, item_id): keep the lowest id, drop the rest (pre-beta, data loss allowed; log the count).
DELETE s FROM npc_shop_items s JOIN npc_shop_items k
  ON k.npc_id = s.npc_id AND k.item_id = s.item_id AND k.id < s.id;
-- 2. Sanitize old unvalidated input.
UPDATE npc_shop_items SET buy_price = 1 WHERE buy_price < 1;
UPDATE npc_shop_items SET sell_price = 0 WHERE sell_price < 0;
UPDATE npc_shop_items SET stock = 0 WHERE stock < 0;
-- 3. New columns.
ALTER TABLE npc_shop_items
  ADD COLUMN restock_target INT NOT NULL DEFAULT 0,               -- «норма склада», units the merchant tries to hold
  ADD COLUMN origin VARCHAR(16) NOT NULL DEFAULT 'admin',         -- admin | player (bought from players, resold only)
  ADD COLUMN updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
UPDATE npc_shop_items SET restock_target = COALESCE(stock, 10);
-- 4. One row per (npc, item).
ALTER TABLE npc_shop_items ADD CONSTRAINT uq_npc_shop_items_npc_item UNIQUE (npc_id, item_id);
```
Downgrade: drop the unique key and the 3 columns (deleted duplicates are not restored). ORM `NpcShopItem` gets the
columns (`server_default`s so the SQLite `create_all` in tests builds them). Existing semantics: `buy_price` /
`sell_price` = **base** prices at region multiplier 1; `stock` NULL = unlimited (legacy only).

**character-service: no migration.** New keys in `econ_sim_settings.params` (defaults in `econ_sim.SimParams`, bounds
in `ECON_SIM_PARAM_BOUNDS` / `EconSimParamsIn`):

| param | default | meaning |
|---|---|---|
| `merchant_bid_share` | 0.5 | default buy-back share of `item_base` for same-group items outside the assortment (also the admin prefill) |
| `merchant_wholesale_share` | 0.5 | restock price share of the market ask |
| `merchant_resident_share` | 0.2 | residents buy `share × price_mult` of a row's stock per tick … |
| `merchant_resident_share_max` | 0.6 | … capped at this share |
| `merchant_purse_share` | 0.05 | at most 5 % of the region purse is spent at merchants per tick (all merchants together) |
| `merchant_take_share` | 0.25 | merchants together take at most 25 % of a group's region stock per tick |
| `merchant_cash_target_mult` | 2.0 | cash target = 2 × wholesale value of a full restock at ×1 prices (Q1) |
| `merchant_cash_cap_mult` | 3.0 | upkeep starts above 3 × cash target (Q4) … |
| `merchant_cash_release` | 0.25 | … and releases 25 % of the excess per tick to the purse |

locations-service needs only `merchant_bid_share`; it reads it from `econ_sim_settings.params` via `econ_core` SQL
with the `econ_core` default as fallback (no dependency on `econ_sim`).

### 3.3 Ledger / shared contract change (`econ_core.py`, all 4 copies — CI `econ-contract-copies`)

| Constant / function | Change |
|---|---|
| `OP_MERCHANT_TRADE = "merchant_trade"` | add to `OP_TYPES` (not a source op) |
| `LEG_TRADE_TAX = "trade_tax"` | add to `LEG_TYPES` **and** `CALLER_LEG_TYPES` (callers pass it; distinct from the generated `tax`) |
| `MAX_CHARISMA_DISCOUNT = Decimal("0.5")`, `DEFAULT_MERCHANT_BID_SHARE = Decimal("0.5")`, `DEFAULT_RESTOCK_TARGET = 10` | constants |
| `MERCHANT_LEGACY_REASONS` | `no_location, no_region, dungeon, not_simulated, dead` |
| `effective_item_group(item_type, resource_subcategory, is_food, item_rarity, override_group, override_off_market) -> (group \| None, off_market)` | override over `auto_item_group`; **no group ⇒ off-market**. character-service `list_item_groups` switches to it (one rule) |
| `item_base_price(items_price, group_base_price) -> int` | `items.price` if > 0 else group base (FEAT-182 3.6) |
| `market_ask(base_ask, mult) -> int`, `market_bid(base_bid, mult, ask) -> int`, `wholesale_price(base_ask, mult, share) -> int`, `discounted_ask(ask, discount_pct) -> int`, `charisma_discount_pct(charisma) -> Decimal` (moved from locations `main.py`, same numbers), `units_per_item(base, group_base) -> float`, `trade_tax(amount, tax_rate) -> int` | pure pricing (3.1 #4); Decimal, deterministic rounding |
| `merchant_status(npc_row, region_row) -> (living: bool, reason \| None)` | pure predicate of 3.1 #2 |
| SQL `SQL_NPC_PLACE` | `SELECT c.id, c.is_npc, c.npc_status, c.current_location_id, l.marker_type FROM characters c LEFT JOIN Locations l ON l.id = c.current_location_id WHERE c.id = :id` |
| SQL `SQL_REGION_MARKET` | `econ_regions` (template, population, tax_rate) + `econ_region_goods` (group_code, price_mult) + `econ_goods_groups.base_price` for one region |
| SQL `sql_item_market(placeholders)` | `items` (type, subcategory, is_food, rarity, price, name, image) LEFT JOIN `econ_item_groups` for a list of ids |
| SQL `SQL_SIM_PARAMS` | `SELECT params FROM econ_sim_settings WHERE id = 1` |
| SQL `sql_lock_shop_rows(placeholders, for_update)`, `SQL_SHOP_STOCK_TAKE` (`UPDATE … SET stock = stock - :q WHERE id = :id AND stock >= :q`), `SQL_SHOP_STOCK_ADD` (`stock = COALESCE(stock, 0) + :q`), `SQL_SHOP_STOCK_SET` | shop-row statements used by both services |

`econ_ledger.py` (sync / async) needs **no change**. `tests/econ_contract_cases.py` (4 copies) gains: (a) `player → NPC`
+ `NPC → region` `trade_tax` → generated 10 % `region → country` tax leg, NPC net = paid − tax; (b) NPC debit above its
cash → `InsufficientFunds`, nothing moved; (c) reversal of (a) mirrors all legs, every balance back; (d) pure pricing
table (ask/bid/wholesale rounding, bid cap with 50 % discount, off-market/legacy mult 1, units mapping, trade tax,
`effective_item_group` override cases, `merchant_status` reasons). `scripts/check_econ_copies.sh` unchanged.

**Stage-3 read contract** (FEAT-182 3.9, never written — now done): documented in `docs/services/character-service.md`
«NPC merchants (FEAT-183)» and referenced from `docs/services/locations-service.md`: the SQL above + pure functions are
the only way either service computes a merchant price.

### 3.4 Background trade (`app/econ_merchant.py`, pure) and tick step (`app/econ_tick.py`)

Input per region: `tax_rate`, `purse` (after `region_tick`), goods `{code: stock, norm_stock, price_mult}`, group base
prices, params, merchants `[{npc_id, cash, rows: [{row_id, group, off_market, origin, base_ask, base_bid, stock (None→0),
restock_target}]}]` (ascending npc id, rows ascending id). Output: new stock per row, region stock delta per group, per
merchant `sold_value, tax, restock_value, upkeep` (ints) and the leg list. Guarantees (asserted in tests): no balance
goes negative, purse spend ≤ `floor(purse × merchant_purse_share)`, region stock never below 0.

Per merchant, per on-market row (off-market rows skipped):
1. **Residents buy:** `ask = market_ask(base_ask, mult)`; `n = floor(stock × min(resident_share × mult, resident_share_max))`,
   capped by the remaining purse budget `// ask`; `stock −= n`; region `stock_g += n × units`; `sold_value += n × ask`.
2. **Tax:** after the merchant's rows: `tax = trade_tax(sold_value, tax_rate)`.
3. **Restock:** `want = max(0, restock_target − stock)`; `fill = clamp(stock_g / norm_g, 0, 1)` (norm 0 → 1);
   `n = floor(want × fill)`, capped by the group take budget (`merchant_take_share × stock_g` at step start, shared by all
   merchants of the region) `// units` and by `cash_left // wholesale`; `stock += n`; region `stock_g −= n × units`;
   `restock_value += n × wholesale`. Cash left = cash + sold_value − tax − restock so far.
4. **Upkeep:** `cash_target = merchant_cash_target_mult × Σ_admin rows restock_target × wholesale(mult=1)`; if
   `cash_after > merchant_cash_cap_mult × cash_target` → `upkeep = floor((cash_after − cap) × merchant_cash_release)`.

**Changed by B5 (PM-approved, 2026-10-29):** (a) step 1 uses **round-half-up** instead of floor (`n = round_half_up(stock × min(resident_share × mult, resident_share_max))`, still ≤ row stock and the purse budget); (b) step 3 uses `n = ceil(want × fill)` when `want > 0` (still capped by the take budget, the remaining region stock and `cash_left // wholesale`) — with floor a row with a small target (≤ 4) froze (stock 4 of 5: residents buy 0, restock 0). (c) no upkeep when `cash_target = 0` (merchant without restockable admin rows keeps his cash for player buy-backs). (d) cash settles at ≈ `cap + income / cash_release` (slightly above the cap), not below it. `cash_target(rows, params)` in `econ_merchant` is also the top-up target of the fund endpoint (B6).

Runner step (in `_process_region`, after `region_tick` posting, inside `session.begin_nested()`):
1. merchants of the region = map built once per run (NPCs with active shop rows → `merchant_status` → region), passed in;
2. `SELECT … FROM npc_shop_items WHERE npc_id IN (…) ORDER BY id FOR UPDATE` → `lock_characters(npc_ids)` → item market
   info (`sql_item_market`) → pure step → `UPDATE npc_shop_items SET stock` (changed rows), `DELETE` player-origin rows
   with stock 0 → adjust the already-locked `econ_region_goods.stock` rows → `post_operation(op_type='merchant_trade',
   legs, region_id, idempotency_key='merchant_trade:<run>:r:<region>', metadata)`;
3. exception → rollback the savepoint, log `region id + error class`, `RunSummary.merchant_failures += 1`; the region
   still commits. History row is written after the step (stock reflects merchants).
Run start (`_fill_plan`): also purge orphan shop rows (`npc_id` not in `characters`). `RunSummary` gains
`merchant_ops_posted`, `merchant_failures` (admin «Пересчёт» tab shows them).

### 3.5 Lock order and contention (supersedes FEAT-181 3.5 / FEAT-182 3.5 for these flows)

`econ_regions → econ_region_goods → npc_shop_items (asc id) → characters (asc id) → econ_accounts (asc id)`.

| Flow | Locks, in order |
|---|---|
| tick region txn | region row → goods rows → shop rows of its living merchants → NPC characters → purse/treasury/country accounts |
| player buy | shop row (conditional stock UPDATE) → player + NPC characters (helper) → region/country (tax) |
| player sell | shop row (`SELECT … FOR UPDATE`, or INSERT of a player-origin row) → player + NPC → (legacy: treasury) |
| refund / compensation | shop row → characters → accounts |
| admin shop edit | shop row only |
| merchant funding / admin NPC gold edit | characters → accounts |
| region fill (FEAT-182) | region rows → accounts (unchanged) |

Player flows read prices / tax rate without locks (snapshot of the last tick; a price that changes during the request
is acceptable). The region txn holds a merchant's NPC row for milliseconds; a player buy at that merchant waits briefly.

### 3.6 Player flows (locations-service) — bug fixes included

Shared helper `crud.merchant_market(session, npc_id) -> MerchantMarket(living, reason, region_id, location_id,
tax_rate, mults {group: mult}, group_base {group: base}, bid_share)` (econ_core SQL + pure predicate).

**Buy** `POST /locations/npcs/{npc_id}/shop/buy` (gates unchanged; `quantity` 1..999 via schema):
1. Row check; living + `stock IS NULL` → treated as 0. Price = `discounted_ask(market_ask(...), charisma)` × q.
2. **One transaction:** finite stock → `SQL_SHOP_STOCK_TAKE` (rowcount 0 → 400 «Недостаточно товара на складе») **before**
   payment (**fixes the oversell race**); post `npc_shop_buy` (living: player→NPC + NPC→region `trade_tax`; legacy:
   player→treasury); `InsufficientFunds` → rollback → 400 «Недостаточно <валюты>»; commit.
3. HTTP add item. Failure → compensation txn: `SQL_SHOP_STOCK_ADD` + `reverse_operation`. If the reversal raises
   `InsufficientFunds` (the tick spent the NPC's cash meanwhile) → fallback refund `treasury_for_location → player`,
   `npc_shop_buy_refund`, `metadata.fallback = true`; any failure logged with ids (no money in logs beyond amounts).

**Sell** `POST /locations/npcs/{npc_id}/shop/sell` (`quantity` 1..999):
1. Price per 3.1 #4/#7 (legacy: only rows with `sell_price > 0`, capped bid). Living: **pre-check** NPC cash ≥ total
   (plain read) → else **409 «У меня сейчас нет на это денег»** — nothing removed.
2. HTTP DELETE inventory (player JWT, as today).
3. Transaction: lock/insert shop row → post `npc_shop_sell` (living NPC→player / legacy treasury→player) → stock += q
   (living; legacy rows keep today's behaviour: the item is destroyed) → commit.
4. On any exception in 3 (incl. `InsufficientFunds` from a concurrent drain): rollback, **return the item** via
   `POST /inventory/internal/characters/{cid}/items` (internal token), answer 409 with the same message. Return failure →
   `logger.error` with ids (residual, 3.12). This replaces the ISSUES entry «Продажа НПС: предмет снимается до зачисления
   золота» (credit failure no longer loses the item).

**Read** `GET /locations/npcs/{npc_id}/shop` (shape: still a list — `NpcProfileModal` keeps working): `buy_price` /
`sell_price` become the **current** prices; new fields `base_buy_price`, `base_sell_price`, `price_level`
(`low` ≤ 0.85 | `normal` | `high` ≥ 1.2 — same thresholds as the region card), `market: bool` (row priced by the region),
`in_stock: bool`; `stock` = effective (living NULL → 0). Player-origin rows with stock 0 are omitted; admin rows with
stock 0 stay (shown «нет в наличии», so the shop button does not disappear). `discounted_buy_price` (private view)
from the current ask. No cash, no restock target, no tax in the public view.

**New** `GET /locations/npcs/{npc_id}/shop/sell-offers?character_id=` — auth required + `visibility.require_private_access`
(owner / admin with `characters:read`): `[{item_id, unit_price, max_quantity}]` for the character's bag items
(`character_inventory`, raw SQL like `crud.py:7246`) that this merchant buys now (3.1 #7). No cash disclosed; refusal for
lack of cash happens on sell (409). The modal's sell tab uses it instead of computing from the shop list.

### 3.7 API Contracts

**locations-service admin** (`get_admin_user`, unchanged auth):

| Method & path | Change |
|---|---|
| `POST /locations/admin/npc-shop/{npc_id}/items` | body `{item_id ≥1, buy_price 1..1_000_000_000, sell_price 0..1_000_000_000, stock: null \| 0..100_000, restock_target 0..100_000 = 10}`; 404 unknown NPC (`is_npc = 1`), 404 unknown item, **409 «Этот предмет уже есть в магазине»** on duplicate; `origin='admin'` |
| `PUT /locations/admin/npc-shop/items/{id}` | same bounds (all optional; `stock` may be null); editing a player-origin row turns it into `origin='admin'` |
| `GET /locations/admin/npc-shop/{npc_id}/items` | rows + `restock_target, origin, group, off_market, market, ask, bid` (current prices) |
| **new** `GET /locations/admin/npc-shop/{npc_id}/market` | `{npc_id, living, reason, region_id, region_name, location_id, tax_rate, cash, buys_groups: [{code, name}]}` |

**character-service** (`economy_api.py`, covered by nginx `/characters/` — no nginx change):

| Method & path | Auth | Body / query → response |
|---|---|---|
| `GET /characters/admin/economy/merchants` | `economy:read` | `region_id?`, `living?` → `{items: [{npc_id, name, location_id, region_id, region_name, living, reason, cash, cash_target, rows: [{row_id, item_id, item_name, group, off_market, origin, base_buy, base_sell, ask, bid, stock, restock_target}], stock_value, last_trade: {run_id, at, sold_value, tax, restock_value, upkeep} \| null}], totals: {merchants, living, cash}}` — every NPC with shop rows; `last_trade` from the region's latest `merchant_trade` op metadata |
| `POST /characters/admin/economy/merchants/fund` | `economy:settings` **and** `economy:emit` | `{region_ids?: [int] ≤500, npc_ids?: [int] ≤500, comment 3..500}` (default: all living) → `{merchants, operation_ids, emitted, skipped: [{npc_id, reason}]}` — `lock_characters`, then one `admin_emission` per region with `emission → NPC` legs `max(0, cash_target − cash)`, `apply_tax=False`, key `merchant_fund:r:<region>:m<max posting id over those NPC accounts>` (re-click emits 0; two identical concurrent clicks → second `DuplicateOperation` → skipped). Legacy NPCs listed in `npc_ids` → skipped with reason |
| `GET/PUT /characters/admin/economy/sim` (changed) | as FEAT-182 | params include the 9 merchant keys |
| `POST …/sim/run` / runs (changed) | as FEAT-182 | run summary `+ merchant_ops_posted, merchant_failures` |

`economy_crud`: `EMISSION_TARGET_KINDS` stays (funding has its own endpoint); journal shows `merchant_trade` and the
`trade_tax` leg type (labels are frontend). Validation errors 422 with Russian `msg`, business errors 400/409 Russian.

### 3.8 Frontend

- **Player** `components/pages/LocationPage/NpcShopModal.tsx` (TS + Tailwind already; keep 360 px): buy tab shows current
  price, struck-through base price and a small `price_level` badge («дешевле обычного» / «дороже обычного», lucide arrow)
  when `market`; «Осталось: N» / «Нет в наличии» (buy disabled), quantity `max = stock` (or 999 when null); sell tab
  from `sell-offers` (item + unit price, qty ≤ `max_quantity`); 409 refusal toasted with the server text («У меня сейчас
  нет на это денег»); every error toasted in Russian; currency via `useCurrency`. `NpcProfileModal.tsx` untouched.
- **Admin shop editor** `components/AdminNpcsPage/NpcShopEditor.tsx`: header from `/market` (живой рынок региона X /
  обычный магазин + reason text, cash, tax rate, «скупает группы: …»); rows show base buy/sell, current ask/bid when
  `market`, stock, «Норма склада» (`restock_target`), badges «скуплено у игроков», «вне рынка»; add/edit forms with the
  bounds above (prefill `sell = floor(price × 0.5)`, `restock_target = 10`); 409 duplicate toasted.
- **Admin economy** `components/Admin/EconomyPage/`: new tab **«Торговцы»** `EconomyMerchants.tsx` (filter by region /
  living; desktop table + mobile cards: NPC, region, status/reason, cash vs target, stock value, last trade; expandable
  rows list; button «Пополнить кассы торговцев» for settings+emit with comment confirm dialog and emitted sum);
  `EconomyTick.tsx` params form gets a «Торговцы» block for the 9 params and shows merchant counters in the runs table;
  `economyLabels.ts`: op `merchant_trade` «Торговля с жителями», leg `trade_tax` «Налог с выручки»; types in
  `src/types/economy.ts`, API in `src/api/economyAdmin.ts`.
- Rules: no `React.FC`, Tailwind/design-system classes, 360 px, every API error toasted in Russian.

### 3.9 Data flow

```
Buy (living):  Modal → POST /locations/npcs/{id}/shop/buy → txn{ stock−=q (conditional) ; npc_shop_buy:
               player→NPC, NPC→region trade_tax (+10 % region→country) } COMMIT → HTTP inventory add
               └ fail → txn{ stock+=q ; reverse (fallback treasury→player) } COMMIT
Sell (living): Modal → GET sell-offers → POST sell → pre-check NPC cash → HTTP inventory DELETE (JWT)
               → txn{ shop row lock/insert ; npc_shop_sell NPC→player ; stock+=q } COMMIT
               └ fail → HTTP internal add item back → 409
Tick:          character-service region txn { region/goods FOR UPDATE → simulate → region_tick
               → SAVEPOINT{ shop rows FOR UPDATE → NPC chars → econ_merchant → stock/goods UPDATE →
                 merchant_trade: purse→NPC, NPC→region trade_tax(+10 %), NPC→purse restock, NPC→purse upkeep } → history } COMMIT
Fund:          Economy «Торговцы» → POST /characters/admin/economy/merchants/fund → lock NPCs → admin_emission emission→NPC
```

### 3.10 Deletions and moves

- **NPC deletion** (character-service): cash already goes to the place's treasury (`character_deleted`); shop rows become
  orphans → purged by the next tick run (no cross-owner DELETE from character-service's delete handler; player
  endpoints already 404 for a missing NPC).
- **Region deletion / region leaves the simulation / NPC moved to a dungeon or service location**: the merchant becomes
  legacy on the next request; his cash stays on the NPC (not lost, visible in the merchants tab), stock keeps its last
  number (no restock). Back in a living region → living again. Nothing to migrate.

### 3.11 Security

- Player endpoints: JWT + ownership + activity lock + FEAT-145 NPC gate + same-location check (unchanged); `quantity`
  1..999, ids > 0 (Pydantic). `sell-offers`: JWT + `require_private_access`. Public shop view never shows cash, restock
  target, tax or group internals; prices are not secret.
- Money: only `npc_shop_*`, `merchant_trade` and `admin_emission` move merchant cash; NPC can never go negative (ledger);
  no source accounts outside admin ops (econ_core rule). Funding records `actor_user_id` + mandatory comment.
- Admin: bounds of 3.7, item/NPC existence checks, text fields none (no XSS surface besides the comment, stripped,
  `<`/`>` rejected as in FEAT-182). SQL parameterised (`in_params`). Rate limit: existing nginx `/locations/`,
  `/characters/` zones.
- Abuse: buy→sell-back at one merchant not profitable (bid cap); stock oversell fixed; sell with a missing item cannot
  print money (item removed before payment; payment only after a successful DELETE).

### 3.12 Residual risks / out of scope (developers add to `docs/ISSUES.md`)

- Sell: if returning the item after a failed credit also fails, the item is lost (logged; needs inventory + DB down within
  ms). Returned item is a fresh base item (enhancement of a sold item is lost — it was being sold anyway).
- Buy refund fallback pays from the treasury when the NPC's cash was spent between purchase and refund (treasury may go
  negative, stage-1 rule).
- Speculation over time / between regions is possible by design (Q3), bounded by stock and cash.
- Player prices are read from the last tick without locks (price may change mid-request).
- Dungeon-service merchant rooms and NPC auctioneers stay outside the merchant model.
- Off-market rows of living merchants are not restocked (admin-managed stock).

### 3.13 Deploy and migration ordering

Deploy together (one push). locations `053` runs at locations-service start; the character-service tick step reads the
new columns — if it runs before `053` the SAVEPOINT fails, is logged and the regions still tick (self-healing next
slot). After deploy on local / prod: «Пополнить кассы торговцев», then «Пересчитать сейчас» (or wait 6 h) so living
merchants with `NULL` stock get their first restock.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

General for every task: **No commits, no pushes** (the user commits once at the end). Backend: Pydantic v1,
`python -m py_compile` on modified files, existing tests stay green (update the shop tests that assert
`npc_shop_buy → region treasury` for living merchants), update `docs/services/<service>.md`, add residual risks to
`docs/ISSUES.md` and rewrite/remove the «Продажа НПС: предмет снимается до зачисления золота» entry. Frontend:
`npx tsc --noEmit` and `npm run build` **inside Docker** (no node on host), Tailwind + design system, no `React.FC`,
360 px, every error toasted in Russian. No prod access.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| B1 | **Shared contract (canonical):** `econ_core.py` per 3.3 (`OP_MERCHANT_TRADE`, `LEG_TRADE_TAX` in both leg sets, constants, `effective_item_group`, `item_base_price`, pricing functions, `charisma_discount_pct`, `units_per_item`, `trade_tax`, `merchant_status`, SQL strings); new shared scenarios (a)–(d) in `tests/econ_contract_cases.py`; `economy_sim_crud.list_item_groups` uses `effective_item_group`. **No commits, no pushes.** | Backend Developer | DONE | `services/character-service/app/econ_core.py`, `app/tests/econ_contract_cases.py`, `app/economy_sim_crud.py` | — | py_compile OK; character-service econ tests green; pricing table of (d) passes (bid never above `floor(ask × 0.5)`) |
| B2 | **Copies:** copy `econ_core.py` and `econ_contract_cases.py` verbatim into inventory-, locations-, dungeon-service. **No commits, no pushes.** | Backend Developer | DONE | `services/{inventory,locations,dungeon}-service/app/econ_core.py`, `…/app/tests/econ_contract_cases.py` | B1 | `sh scripts/check_econ_copies.sh` passes; contract tests green in all 4 services |
| B3 | **locations schema + admin:** migration `053_npc_shop_market` (3.2), ORM columns, schemas with bounds, admin CRUD (`restock_target`, duplicate 409, NPC/item existence, player-origin → admin on edit), admin GET extra fields, new `GET /admin/npc-shop/{npc_id}/market`; `crud.merchant_market` helper (3.6). **No commits, no pushes.** | Backend Developer | DONE | `services/locations-service/app/alembic/versions/053_npc_shop_market.py`, `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py` | B2 | `alembic upgrade head` / `downgrade -1` / upgrade on local MySQL OK; duplicates removed, unique key present; curl: negative price → 422, duplicate → 409, `/market` shows living/reason for a merchant in a templated region and for one without region |
| B4 | **locations player flows:** GET shop (current prices, new fields, hiding rules), new `sell-offers`, buy (stock take before payment in the payment txn, living legs with `trade_tax`, compensation restoring stock + fallback refund), sell (bid rules 3.1 #4/#7, cash pre-check → 409, item-first, txn with row upsert + stock, item return on failure), `quantity` bounds; docs `locations-service.md` shop section; ISSUES update. **No commits, no pushes.** | Backend Developer | DONE | `services/locations-service/app/main.py`, `app/crud.py`, `app/schemas.py`, `docs/services/locations-service.md`, `docs/ISSUES.md` | B3 | curl on local: living merchant — buy moves player→NPC with tax legs (journal), stock decreases, price differs from base by region mult; broke merchant → 409 and item stays in inventory; same-group item sold → new player-origin row; legacy merchant behaves as before; summary invariant `ok` |
| B5 | **Pure merchant math:** `app/econ_merchant.py` per 3.4 (dataclasses in/out, legs builder) + 9 params in `econ_sim.SimParams`, `ECON_SIM_PARAM_BOUNDS`, `EconSimParamsIn`. **No commits, no pushes.** | Backend Developer | DONE | `services/character-service/app/econ_merchant.py`, `app/econ_sim.py`, `app/schemas.py`, `app/economy_sim_crud.py` (bounds if there) | B1 | py_compile OK; a 40-tick loop over a capital with 3 merchants keeps cash ≥ 0, purse spend within budget, region stock ≥ 0, cash converges below the cap |
| B6 | **Tick step + merchants API:** merchant step in `_process_region` (savepoint, run-level merchant map, locks per 3.5, stock/goods updates, `merchant_trade` op, player-origin cleanup), orphan shop-row purge, `RunSummary` counters; `GET /admin/economy/merchants`, `POST /admin/economy/merchants/fund` (3.7); docs `character-service.md` «NPC merchants (FEAT-183)» incl. the stage-3 read contract and the global lock order. **No commits, no pushes.** | Backend Developer | DONE | `services/character-service/app/econ_tick.py`, `app/economy_api.py`, `app/economy_sim_crud.py` (or new `app/economy_merchants_crud.py`), `app/schemas.py`, `docs/services/character-service.md`, `docs/ISSUES.md` | B3, B5 | manual run on local: one `merchant_trade` op per region with merchants (purse→NPC, NPC→region trade_tax + 10 %, NPC→purse), stocks restocked toward target limited by region stock, region goods change; rerun of the same run is a no-op; broken merchant data → region still ticks; fund emits once (re-click 0); 401/403 without permissions; invariant `ok` |
| F1 | **Player shop modal** per 3.8 (current/base price, price badge, stock, sell-offers sell tab, refusal toast). **No commits, no pushes.** | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/NpcShopModal.tsx` (+ small api/types file if useful) | B4 contract (3.6) | tsc + build pass; 360 px OK; «Нет в наличии» disables buy; 409 shows «У меня сейчас нет на это денег» |
| F2 | **Admin shop editor** per 3.8 (market header, restock target, current prices, badges, bounds, 409). **No commits, no pushes.** | Frontend Developer | DONE | `src/components/AdminNpcsPage/NpcShopEditor.tsx` | B3 contract (3.7) | tsc + build pass; 360 px OK; duplicate item toasted; living/legacy header correct |
| F3 | **Admin economy:** «Торговцы» tab (`EconomyMerchants.tsx`, list, filters, fund dialog), tick params «Торговцы» block + run counters, labels `merchant_trade` / `trade_tax`, types + API. **No commits, no pushes.** | Frontend Developer | DONE | `src/components/Admin/EconomyPage/{EconomyPage,EconomyMerchants,EconomyTick}.tsx`, `economyLabels.ts`, `src/types/economy.ts`, `src/api/economyAdmin.ts` | B6 contract (3.7) | tsc + build pass; 360 px OK; fund shows emitted sum, re-click 0; journal shows «Торговля с жителями» with «Налог с выручки» legs |
| Q1 | **QA contract:** shared scenarios (a)–(d) run in all 4 services; extra character-service unit tests of the pricing functions and `merchant_status` reasons. **No commits, no pushes.** | QA Test | DONE | `services/*/app/tests/test_econ_contract.py` (if runner changes), `services/character-service/app/tests/test_econ_merchant_pricing.py` | B1, B2 | pytest green in all 4 services; copies check passes |
| Q2 | **QA locations flows:** living vs legacy buy/sell legs and amounts (tax, 10 % country), stock race (second buy of the last unit refused, no payment), refund restores stock + cash (+ fallback when NPC cash gone), sell refusal with 0 cash makes no inventory call, item return on credit failure (mocked), same-group sale creates player-origin row, off-market/other-group refused, bid cap vs max charisma (no profit), `sell-offers` gate 401/403, quantity bounds, admin CRUD bounds/duplicate/`/market`; update existing shop tests; security cases (SQL-ish strings, negative ids). **No commits, no pushes.** | QA Test | DONE | `services/locations-service/app/tests/test_npc_merchants.py`, existing `test_econ_locations_flows.py`, `test_charisma_discount.py`, `test_feat171_shop_gate.py`, `tests/conftest.py` | B4 | pytest green; each test < 30 s |
| Q3 | **QA tick + merchants API:** `econ_merchant` unit tests (purse budget, take budget, fill ratio, cash cap/upkeep, never negative, off-market skipped); runner on SQLite (one `merchant_trade` op, goods moved both ways, idempotent rerun, savepoint isolation, legacy/dead/dungeon merchants skipped, orphan purge, player-origin cleanup); API RBAC 401/403 (fund needs both permissions), fund idempotent top-up, comment required, list shape. Add portable `npc_shop_items` / `Locations.marker_type` / `characters.npc_status` DDL to conftest if missing. **No commits, no pushes.** | QA Test | DONE | `services/character-service/app/tests/test_econ_merchant.py`, `test_econ_merchant_tick.py`, `test_econ_merchants_api.py`, `tests/conftest.py` | B5, B6 | pytest green; whole service step well under CI limits |
| R1 | **Review + live on local:** 4 copies identical, security checklist, py_compile / pytest (4 econ services) / tsc / build re-run; **live**: one merchant in a templated region and one in a region without template (or a dungeon); fund merchants; «Пересчитать сейчас» ×2 → stock restocked, `merchant_trade` ops with tax legs, region stock moved; as a player: prices differ from base by region, buy reduces stock, sell to the broke legacy/zeroed merchant → refusal and item kept, sell a same-group item → appears in the merchant's stock; legacy merchant unchanged; summary invariant «Сходится»; 360 px for modal, editor, merchants tab; zero console errors. **No commits, no pushes.** | Reviewer | DONE | all | B1–B6, F1–F3, Q1–Q3 | Checklist passed, invariant `ok` after the live scenario |

Parallelism: B1 first; B2 after B1; B3 after B2; B5 after B1 (parallel with B2/B3); B4 after B3; B6 after B3 + B5.
F1 after the B4 contract (coding can start from 3.6), F2 from 3.7, F3 from 3.7 (live check after B6). Q1 after B2, Q2
after B4, Q3 after B6. R1 last.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-10-29
**Result:** PASS

Scope: whole uncommitted FEAT-183 diff (36 modified + 11 new files) plus local commit `dc68337` («currency abbreviation is ṃ»: econ_core default short form x4, ORM default, migration `030_currency_short_mark` guarded by the old value both ways — fine).

#### Code review
- **Contract copies:** `sh scripts/check_econ_copies.sh` — all econ_core / econ_contract_cases / econ_ledger copies identical.
- **Lock order** `econ_regions → econ_region_goods → npc_shop_items asc → characters asc → econ_accounts asc` holds in every flow: tick locks shop rows (`sql_lock_shop_rows … ORDER BY id FOR UPDATE`) and NPC characters in `lock_merchants` *before* the `region_tick` posting, merchant op posted inside a SAVEPOINT; player buy = conditional `SQL_SHOP_STOCK_TAKE` → ledger (characters → accounts), never touches region rows; player sell = plain reads, commit, HTTP DELETE, then shop-row upsert/stock add → ledger; fund = `lock_characters` → `post_operation`. No inverse order found.
- **Idempotency:** `merchant_trade:<run>:r:<region>` in the region txn (re-run no-op, DuplicateOperation handled); fund key `merchant_fund:r:<region>:m<max posting id>:h<crc>` — live re-click emitted 0.
- **Security:** admin shop endpoints `get_admin_user`; merchants list `economy:read`; fund `require_all_permissions(economy:settings, economy:emit)` (401 without token verified live); `sell-offers` JWT + `require_private_access` (401 live); public shop exposes no cash / restock target / tax. Quantity 1..999 in schema and re-checked before SQL (negative q cannot turn a take into an add). All SQL parameterised (`in_params`, bound `:id`), no string-built values. NPC cash can never go negative (conditional debit); broke merchant → 409 before the inventory call; credit failure → rollback + item returned.
- **Migration 053:** dedupe keeps the active row with the lowest id (is_active is NOT NULL, so the comparison never hits NULL), sanitises negatives, adds columns idempotently (column/constraint existence checks), `restock_target = COALESCE(stock, 10)`, unique key; downgrade drops key + 3 columns (separate `npc_id` index remains, so dropping the unique index is safe on MySQL). Applied locally (`alembic_version_locations = 053_npc_shop_market`).
- **Frontend:** TS only, no `React.FC`, no `any`, Tailwind + design-system classes, every API error toasted in Russian (409 refusal in the merchant's voice, 422/no-response fallbacks), lucide icons; mobile cards for the merchants tab and the shop editor.
- **QA coverage:** Q1–Q3 present (pricing 158, tick/merchant 141, locations 138 + admin 41 tests), all new endpoints covered incl. RBAC.

#### Automated Check Results
- [x] `py_compile` (all modified/new .py incl. migration and tests) — PASS
- [x] `sh scripts/check_econ_copies.sh` — PASS
- [x] pytest character-service — PASS (2634 passed, 1 skipped, exit 0)
- [x] pytest locations-service — PASS (2194 passed, exit 0)
- [x] pytest inventory-service — PASS (2086 passed, 1 skipped, exit 0)
- [x] pytest dungeon-service (`--timeout=30`) — PASS (701 passed, exit 0; the summary line is not printed by this suite, counted from progress dots, no F/E)
- [x] `npx tsc --noEmit` (frontend container) — PASS (exit 0)
- [x] `npx vite build --outDir /tmp/build-check-r1` (frontend container) — PASS (exit 0). Note: on the host the build fails only because host `node_modules` lacks `react-icons` (in package.json, used by the unrelated `Arena3D/EffectRunes.tsx`) — environment, not this feature.
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, localhost) — PASS

#### Live Verification Results
- Admin → Экономика → Торговцы: 3 merchants — Петя #33 and Бенедикт #49 «живой рынок» (Мэттанхейм, налог 12 %), Тайчо Шейво #429 «обычный магазин — НПС находится в подземелье»; cash/target bars, stock value, last trade.
- «Пополнить кассы торговцев» (comment dialog, no browser confirm): emitted 108 to Петя (2752 → 2860 = target), Бенедикт skipped «касса уже не меньше нормы»; repeated fund → `emitted 0`, both `at_target`.
- Пересчёт → «Пересчитать сейчас» ×2 (runs 32, 33): «Торговцев: 2, продано жителям 22, закуплено 23/22, операций торговли 1»; shop stocks restocked to their targets (e.g. row 1: 97 → 98). Journal op 148 «Торговля с жителями»: purse → Петя 584, Петя → Мэттанхейм 70 «налог с выручки», Мэттанхейм → Мидденгерд 7 «налог», Петя → purse 272 (restock), Бенедикт legs incl. upkeep 211.
- Admin shop editor (Петя): living header (region, cash 3 335, tax 12 %, buys groups Зелья / Ремесленный инвентарь / Оружие), base vs «сейчас» prices, Запас / Норма склада, «вне рынка» and «скуплено у игроков» badges.
- Player (Ашари #763 at location 197): shop shows discounted current price, struck base («обычно 150»), price badge, «Осталось: N». Bought 1 «Зелье здоровья (малое)» for 18: balance 18 370 → 18 352, stock 98 → 97, NPC cash +18 −2 tax. Sold 1 «Зелье энергии (малое)» (same-group item not in the assortment) for 14 → new `origin='player'` row (stock 1) appears in the shop. NPC cash zeroed by admin adjust → selling again → toast «Петя: «У меня сейчас нет на это денег»», item count unchanged (4); cash restored.
- Legacy merchant #429: `/market` → `living=false, reason=dungeon`; public shop row unlimited (`stock null`), base prices, `market=false`. Buy/sell at a legacy merchant not clicked live (player cannot reach the dungeon location without moving the character) — covered by the locations tests and B4's live run.
- Summary invariant «Сходится» / `ok: true` before, during and after the scenario.
- 360 px (same-origin iframe): merchants tab (mobile cards), shop editor (cards), shop modal — no horizontal overflow (scrollWidth 341 ≤ viewport).
- Console errors: none; no 4xx/5xx resources on the economy page; shop / sell-offers / admin items / summary all 200.

#### Notes (non-blocking)
- After a sale the sell tab is blank for a split second while lists refresh (no spinner because the previous offers are cleared only by the refresh) — cosmetic.
- Pre-existing, unrelated: the desktop header coin count (`state.user.character`) is not refreshed after shop deals → added to `docs/ISSUES.md` (LOW «Шапка (десктоп): баланс не обновляется после сделки в лавке НПС»).

No fixes to feature code were needed.


---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-10-29 — Backend Dev: B5 готово — чистый модуль econ_merchant.py (покупки жителей в пределах бюджета кошелька, докупка с учётом заполненности и лимита взятия из запаса региона, налог с выручки, содержание сверх 3× нормы кассы, сборка проводок merchant_trade); 9 параметров торговцев в SimParams/границах/схеме. Прогон 40 тиков (столица, шахтёрский, крепость, 4 торговца): касса/кошелёк/запасы не уходят в минус, деньги сходятся каждый тик, огромная касса стекает к норме. Отступление: при норме кассы 0 содержание не списывается. Замечание: при малой норме склада (≤4) округление вниз останавливает торговлю ряда. pytest character-service: 2335 + 1 skip
[LOG] 2026-10-29 — Backend Dev: B5 доработка по решению PM — покупки жителей округляются по правилу half-up, докупка — вверх (ceil); ряды с малой нормой (3–5) больше не замерзают: в 40-тиковом прогоне торгуют каждый тик, кроме украшений в крепости (там во всём регионе ~2 единицы — нехватка, ожидаемо); все инварианты держатся; 3.4 дополнен пометкой «Changed by B5»; pytest character-service: 2335 + 1 skip
[LOG] 2026-10-29 — PM: фича создана (этап 3 экономики — торговцы НПС), запускаю анализ, параллельно уточняю правила с пользователем
[LOG] 2026-10-29 11:50 — Analyst: анализ завершён (раздел 2). Затронуты locations-service, character-service, фронтенд (+копии econ_core). Сейчас касса торговца не участвует, склад только убывает, продать можно лишь то, что есть в списке торговца с ценой продажи; найдена гонка остатка (перепродажа последней штуки), контракт чтения цен этапа 3 из FEAT-182 3.9 в доках/econ_core не оформлен
[LOG] 2026-10-29 13:10 — Architect: спроектирован этап 3 (разделы 3–4): склад торговца остаётся в locations-service, фоновая торговля — шаг внутри 6-часового пересчёта региона в character-service; цены и правила «живого» торговца — общий контракт econ_core; новая операция merchant_trade и проводка «налог с выручки»; единый порядок блокировок, исправлены гонка остатка и порядок продажи. 13 задач (6 backend, 3 frontend, 3 QA, ревью), 4 вопроса пользователю с рекомендованными ответами
[LOG] 2026-10-29 — PM: пользователь согласился со всеми рекомендациями архитектора (4 вопроса); запускаю B1
[LOG] 2026-10-29 — Backend Dev: B1 готово — в econ_core добавлены merchant_trade, нога trade_tax, константы, effective_item_group (нет группы ⇒ вне рынка), функции цен (ask/bid/опт/харизма/единицы/налог с выручки), merchant_status и общие SQL для лавки и тика; list_item_groups переведён на effective_item_group (предметы без группы теперь «вне рынка», тест обновлён); в econ_contract_cases — сценарии торговца (a)–(d) и отдельный SQLite-мир для проверки SQL. Отступления: причина not_npc, SQL_REGION_ECON отдельно от SQL_REGION_MARKET, несколько вспомогательных функций сверх 3.3
[LOG] 2026-10-29 — Backend Dev: B2 готово — econ_core.py и econ_contract_cases.py скопированы побайтно в inventory/locations/dungeon, во всех 4 test_econ_contract.py добавлены прогоны новых списков; check_econ_copies.sh зелёный; полные прогоны: character 2326+1 skip, inventory 2086+1 skip, locations 1996, dungeon 701 — всё зелёное
[LOG] 2026-10-29 — Backend Dev: B3 готово — миграция locations 053_npc_shop_market (дедуп (npc,item): остаётся активная строка с меньшим id, иначе меньший id; чистка отрицательных цен/остатков; restock_target = COALESCE(stock,10), origin, updated_at, UNIQUE); модель и схемы с границами; админка лавки: 404 на неизвестного НПС/предмет, 409 на дубль, правка строки «от игроков» делает её админской, в списке — группа, «вне рынка», текущие ask/bid; новый GET /locations/admin/npc-shop/{npc_id}/market; хелперы crud.merchant_market / price_shop_row / merchant_buy_groups для B4. upgrade/downgrade/upgrade на локальной MySQL — ок; живая проверка curl-ами — ок; новые тесты test_npc_shop_admin_market.py (41); полный прогон locations: 2037 зелёных
[LOG] 2026-10-29 — Frontend Dev: F2 готово — редактор лавки НПС: шапка состояния торговца (живой рынок региона / обычный магазин с причиной, касса через useCurrency, налог региона, скупаемые группы), поле «Норма склада», текущие цены «сейчас» рядом с базовыми у товаров на рынке, метки «вне рынка» / группа / «скуплено у игроков», проверка границ как в схемах бэкенда, 409-дубль и прочие ошибки — тостом по-русски (422 — своим текстом); названия групп подтягиваются из экономики при праве economy:read, иначе код/имя из buys_groups. tsc и vite build — ок
[LOG] 2026-10-29 — QA: Q1 готово — общие сценарии торговца (a)–(d), PRICING_CASES, BID_CAP_GRID, EFFECTIVE_GROUP_CASES, MERCHANT_STATUS_CASES и SQL-мир уже прогоняются во всех 4 сервисах (сделано в B2), общие кейсы не менялись; добавлен test_econ_merchant_pricing.py в character-service (158 тестов: границы округления, Decimal/int/str/float, ноль/минус/огромные суммы, харизма 0/250/огромная/мусор, потолок скупки и отсутствие выгоды «купил-продал», множитель 1 для «старых» и внерыночных, единицы при base ≤ 0, границы ставки налога с выручки, все причины merchant_status и их порядок, параметризация SQL и белый список ключа). Багов не найдено. check_econ_copies.sh зелёный; прогоны: character 2493+1 skip, inventory 2086+1 skip, locations 2037, dungeon 701 — все exit 0
[LOG] 2026-10-29 — Backend Dev: B6 готово — шаг торговцев в пересчёте региона (SAVEPOINT после region_tick; строки лавок и НПС блокируются до проводки по порядку 3.5; одна операция merchant_trade на регион; остатки лавок и запасы региона двигаются в обе стороны; проданные «от игроков» строки и строки удалённых НПС чистятся); RunSummary: merchants_processed, merchant_items_sold/restocked, merchant_ops_posted, merchant_failures, merchant_failed_region_ids, shop_rows_purged; API GET /characters/admin/economy/merchants и POST …/merchants/fund (новый модуль economy_merchants_crud.py); раздел «NPC merchants (FEAT-183)» в доке; остаточные риски в ISSUES. Локально: пополнение 2860 один раз (повтор 0), прогон 28 — merchant_trade с 8 ногами (налог с выручки + 10 % стране, докупка, содержание), повтор того же прогона — no-op, сломанный шаг (прогоны 29–30) откатился, регион посчитан; инвариант ok; pytest character-service: 2493 + 1 skip
[LOG] 2026-10-29 — Backend Dev: B4 готово — игровые потоки лавки: витрина отдаёт текущие цены (регион × база, харизма через econ_core), базовые цены, эффективный остаток, in_stock/market/price_level/living, пустые строки «от игроков» скрыты; новый GET /npcs/{id}/shop/sell-offers (JWT + гейт владельца); покупка — остаток снимается условно в транзакции оплаты до неё (гонка за последнюю штуку закрыта), у живого торговца игрок → НПС + налог с выручки в регион, при сбое выдачи — остаток и деньги назад (если кассы уже нет — из казны места); продажа — проверка кассы до снятия предмета (409 «У меня сейчас нет на это денег»), купленное идёт на склад (новая строка «от игроков» для вещей той же группы), при сбое зачисления предмет возвращается; количество 1..999 (схема + перепроверка, отрицательное q не доходит до SQL). Доки и ISSUES обновлены (запись о порядке продажи закрыта, остаточные риски B4 — в LOW). Отступление: иной сбой зачисления → 500 «Не удалось завершить продажу», а не 409. pytest locations: 2056 зелёных; живые проверки на :80 (НПС 33 живой, НПС 429 в данже — обычный) — ок, инвариант ok
[LOG] 2026-10-29 — Frontend Dev: F3 готово — в «Экономике» новая вкладка «Торговцы» (EconomyMerchants.tsx): фильтры по региону и типу (живой рынок / обычные магазины), итоги (торговцев, на живом рынке, деньги в кассах), таблица на десктопе и карточки на мобильных: НПС, регион и налог, статус с причиной, касса против нормы полоской, стоимость склада, последняя торговля (продано/налог/закуплено/содержание); строки раскрываются списком товаров (база и текущие цены, запас/норма, метки «скуплено у игроков», «вне рынка», «не продаётся»); кнопка «Пополнить кассы торговцев» (только при economy:settings + economy:emit) с обязательным комментарием и опцией «только выбранный регион», итог — тост и плашка с суммой эмиссии и причинами пропусков. Подписи причин вынесены в economyLabels.ts и используются и в NpcShopEditor. Во «Пересчёте» — блок «Торговцы» из 9 параметров с подсказками и границами, колонка «Торговцы» в списке прогонов, счётчики торговцев в итоге ручного пересчёта. Журнал: «Торговля с жителями» и нога «налог с выручки». Типы и API добавлены. tsc и vite build — ок; контракт GET merchants/sim сверен с живым бэкендом (curl через :80); пополнение вживую не нажималось (оставлено ревью)
[LOG] 2026-10-29 — Frontend Dev: F1 готово — модалка лавки игрока (NpcShopModal.tsx): во вкладке «Купить» текущая цена (со скидкой харизмы — зачёркнутая и зелёная), у товаров на рынке «обычно N» зачёркнутой базой и метка «дешевле обычного» / «обычная цена» / «дороже обычного» со стрелкой; «Осталось: N» / «Нет в наличии» (кнопка и поле количества выключены), у безлимитных строк ничего; количество ограничено остатком и 999. Вкладка «Продать» теперь строится по sell-offers (цена за штуку, «Можно продать: N», выбор количества ≤ max_quantity), подтверждение продажи считает по unit_price. Отказ 409 — тостом от имени торговца («Имя: «У меня сейчас нет на это денег»»), остальные ошибки — тостом по-русски (422 — «Неверное количество», нет ответа — «Нет связи с сервером»). После каждой сделки (и после неудачной продажи — предмет мог вернуться) обновляются витрина, sell-offers, сумка и баланс. NpcProfileModal не трогал. tsc и vite build — ок; вживую в браузере не проверял (оставлено ревью)
[LOG] 2026-10-29 — QA: Q3 готово — 141 новый тест в character-service: test_econ_merchant.py (84: бюджет кошелька и лимит взятия общие на регион, заполненность и докупка вверх, покупки жителей half-up, ряды с малой нормой торгуют каждый тик, норма/потолок кассы и содержание (без содержания при норме 0), ничего не уходит в минус, внерыночные/без группы/без строки региона пропускаются, проводки сходятся, порядок детерминирован, входы не меняются, 40 случайных миров), test_econ_tick_merchants.py (14: одна merchant_trade на регион с ногами + доля страны, товары в обе стороны, повтор прогона — no-op, занятый ключ и сбой шага/блокировки/проводки откатывают только торговцев, старые/мёртвые/данж пропущены, чистка сирот и проданных строк «от игроков», без таблицы лавок регионы считаются), test_econ_merchants_api.py (43: 401/403 — пополнение требует оба права, чтение — economy:read; форма списка и фильтры, пополнение один раз (повтор 0), причины пропуска, валидация комментария и id, одновременные клики — одна эмиссия, инвариант после каждого движения денег). Багов не найдено. conftest не менялся (marker_type/items/npc_shop_items добавляются в фикстурах). pytest character-service: 2634 + 1 skip, exit 0
[LOG] 2026-10-29 — QA: Q2 готово — новый test_npc_merchants.py (138 тестов) дополняет тесты B3/B4: налог с выручки по ставке региона со скидочной суммы, 10 % стране только при ≥ 1, без ноги при округлении в 0; регион без населения, мёртвый НПС и товар «вне рынка» у живого торговца; гонки на двух соединениях (последняя штука — платит один; касса на одну продажу — второй получает отказ или возврат предмета; первая продажа нового предмета — одна строка «от игроков»); возврат при реально потраченной кассе — из казны, двойной сбой — без двойного возврата; граница кассы 59/60, отказы (вне рынка, без группы, цена 0, неактивная строка, группы строк «от игроков» не расширяют скупку, неизвестный предмет) без вызова инвентаря; иной сбой зачисления — предмет возвращается внутренним маршрутом, 500; «купил-продал» при макс. харизме не выгоден (живой и обычный, 40 комбинаций, через строку «от игроков»); HTTP: 422 на строки/SQL-подобные/огромные значения, sell-offers 401/403/404 и касса не раскрывается, витрина (скрытие, набор полей), админка лавки 401/403, модератор ок, 409 дубль; миграция 053 — ревизия ≤ 32, дедуп проверен вручную на локальной MySQL во временной таблице (оставляет активную с меньшим id, чистит отрицательные). Инвариант суммы 0 после каждого денежного сценария. Багов не найдено. pytest locations: 2194 зелёных (exit 0), гонки 5 прогонов подряд стабильны
[LOG] 2026-10-29 — Reviewer: проверка завершена, результат PASS — копии econ_core идентичны, порядок блокировок и ключи идемпотентности соблюдены, миграция 053 безопасна; pytest: character 2634+1 skip, locations 2194, inventory 2086+1 skip, dungeon 701 (все exit 0), tsc и сборка в контейнере — ок; вживую: пополнение касс (108, повтор 0), два пересчёта с «Торговлей с жителями» и налогом с выручки, покупка/продажа у Пети, отказ разорившегося торговца с сохранением предмета, обычный торговец в данже, «Сходится», 360 px, ошибок в консоли нет; найден старый баг шапки — добавлен в ISSUES.md
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

Этап 3 экономики «Торговцы НПС» готов.

- Живой торговец (НПС в локации региона с шаблоном и населением, не в данже) торгует от своей кассы: игрок платит ему, он платит налог с выручки в казну региона (+10 % в страну); цены = цена из админки × множитель группы товара в регионе (×0,5–×3); вне рынка — фиксированно.
- Склад конечный; раз в 6 часов в пересчёте жители покупают у торговца, он докупает товар у региона до нормы, лишние деньги (больше 3 норм кассы) понемногу отдаёт жителям. Сбой торговца не валит пересчёт региона.
- Скупает только свой ассортимент и вещи тех же групп, перепродаёт их («скуплено у игроков»); без денег отвечает «У меня сейчас нет на это денег», вещь остаётся у игрока. Купить и сдать обратно никогда не выгодно.
- Исправлено: последний товар больше не продаётся двоим; при продаже сначала проверяются деньги, вещь при сбое возвращается.
- Админка: вкладка «Торговцы», «Пополнить кассы торговцев», параметры торговли в «Пересчёте», живой заголовок в редакторе лавки. Игрок: текущая цена, метка «дешевле/дороже обычного», остаток, вкладка продажи.
- Торговцы вне живых регионов (данжи, регионы без шаблона, мёртвые НПС) работают по-старому.
- Тесты: character 2634, locations 2194, inventory 2086, dungeon 701 — зелёные; ревью PASS с живой проверкой.
