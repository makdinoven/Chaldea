# FEAT-165: Переработка профессий — сырьё, переработка, камни заточки, Мистик

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-17 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-165-slug.md` → `DONE-FEAT-165-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Этап 2 из 3 ребаланса профессий (этап 1 — DONE-FEAT-164, восстановление и сытость). Цель — связать профессии между собой так, чтобы каждая была нужна другим: у профессий появляется переработка сырья, камни заточки делают три профессии, ресурсы делятся на подкатегории. Источник: наброски пользователя `.idea/img_14.png`, `.idea/img_15.png`.

На проде сейчас: 0 рецептов, 0 чертежей, 0 камней/рун/огранок, 7 игроков с профессией (все ранг 1: 3 кузнеца, 2 алхимика, 2 книжника). Ранги: Ученик (0), Подмастерье (500), Мастер (2000).

### Бизнес-правила

**Профессии (одна на персонажа, как сейчас):**

| Профессия | Крафт по рецептам | Дополнительно |
|---|---|---|
| Кузнец | оружие, броня, шлемы (лёгкие, средние, тяжёлые) | камни заточки для оружия, брони и шлема; ремкомплекты; переработка: руда → слитки |
| Алхимик | зелья, пояса | переработка: алхимические реагенты → эссенции |
| Повар | еда | переработка: ингредиенты → алхимические реагенты |
| Зачарователь | руны, оружие магов | камни заточки для плаща и пояса («зачарования»); своей переработки нет — так задумано |
| Ювелир | кольца, ожерелья, браслеты, огранки | камни заточки для колец, ожерелий, браслетов; переработка: руда → магическая пыль |
| Мистик (переименование «Книжник») | книги, свитки, тканевая броня и шлемы | переработка: трофеи → материалы |

- Категории брони: ткань < лёгкая < средняя < тяжёлая. Кузнец — лёгкая/средняя/тяжёлая, Мистик — только ткань. Что кто крафтит, задаётся рецептами в админке; отдельная жёсткая проверка в коде не требуется, если архитектор не решит иначе.
- «Книжник» переименовывается в «Мистик» (у существующих игроков профессия сохраняется).

**Рецепты:**
- Рецепт изучается один раз и навсегда; после изучения в окне профессии видны нужные материалы. **Одноразовых чертежей больше нет** (убрать механику чертежей / одноразовости).
- У рецепта нет своей редкости — она берётся у получаемого предмета (сделано в FEAT-164).

**Переработка (новая механика):**

| Кто | Из чего | Во что | Пропорция |
|---|---|---|---|
| Кузнец | руда | слиток | 2 → 1 |
| Алхимик | алхимические реагенты | эссенция | 2 → 1 |
| Повар | ингредиент | алхимические реагенты | 1 → 2 |
| Ювелир | руда | магическая пыль | 1 → 1 |
| Мистик | трофей (ресурсы с монстров: кожа и т.п.) | материал | 1 → 1 |

- Переработка берёт **один вид** сырья за раз. Что получается из конкретного сырья — **настраивается в админке у предмета-сырья**, отдельно для каждой профессии (руду перерабатывают и кузнец, и ювелир): 2 медные руды → 1 медный слиток; 1 медная руда → 1 магическая пыль (какая — тоже задаёт админ).
- Качество результата соответствует качеству сырья (через выставленный в админке предмет-результат).
- Переработка **всегда успешна**.
- **Бонус количества:** с шансом, зависящим от ранга, результат удваивается: Ученик 5%, Подмастерье 10%, Мастер 20% (константы, легко поменять).
- За переработку начисляется **опыт профессии** (опыт — только за создание: крафт и переработка; за заточку опыта нет ни у кого).
- Нельзя перерабатывать в бою и во время сбора (как остальные действия профессий).
- Реагенты повара идут алхимику: в эссенции или в зелья (через рецепты).
- Эссенции нужны зачарователю и Мистику; пыль — зачарователю и кузнецу; материалы — кузнецу и алхимику; слитки — ювелиру; руны вставляются в снаряжение кузнеца и Мистика (всё это через рецепты).

**Удаляемые механики:**
- Извлечение эссенции из кристаллов (алхимик, 75%) — убрать. Кристаллы стихий как категорию убрать.
- Трансмутация 5 → 1 уровнем выше (алхимик) — убрать.
- Переплавка украшений (ювелир) — убрать.

**Камни заточки:**
- Каждую вещь можно заточить до +15, с теми же шансами и распределением характеристик, что сейчас.
- Камни для разных частей снаряжения: кузнец — оружие, броня, шлем; зачарователь — плащ и пояс; ювелир — кольцо, ожерелье, браслет (у украшений сейчас заточки нет — добавить).
- **Точить может любой игрок, у которого есть подходящий камень** (сейчас — только кузнец). Камень должен подходить к типу вещи.

**Вставка (гнёзда):**
- Руны (зачарователь) — в оружие, броню, шлем, плащ. **Пояс убрать** из списка для вставки.
- Огранки (ювелир) — в кольцо, ожерелье, браслет.
- Пояс — это быстрые слоты (зелья и т.п.), вставок нет. Заточка пояса остаётся (камень зачарователя).
- **Вставлять** руны и огранки может любой игрок, у которого они есть; **извлекать** — только ювелир (огранки) и зачарователь (руны).

**Подкатегории ресурсов (в модуле предметов, админка + фильтры):**
- Сырьё: руда, травы, древесина, ингредиенты, трофеи.
- Продукты переработки: слитки, магическая пыль, эссенции, алхимические реагенты, материалы.
- Расходники профессий: точильные камни (камни заточки), ремкомплекты.
- Переработка принимает только нужную подкатегорию (кузнец/ювелир — руда, алхимик — реагенты, повар — ингредиенты, Мистик — трофеи).
- Древесина — пока ни для чего (на будущее: постройка домов).

**Сбор:**
- Новый, четвёртый вид сбора — **ингредиенты** (для повара), рядом с рудой, травами и древесиной. Выращивание в доме — будущая фича, не в этом этапе. Ингредиенты также продаются у торговцев (обычные предметы магазина, админ настроит).

**Редкость:** всё, что не снаряжение, — максимум легендарная (сделано в FEAT-164; новые подкатегории подчиняются тому же правилу).

### UX / Пользовательский сценарий
1. Кузнец открывает вкладку крафта, выбирает «Переработка», кладёт медную руду → получает медные слитки (иногда вдвое больше), видит начисленный опыт.
2. Ювелир перерабатывает ту же руду в магическую пыль 1:1.
3. Любой игрок с камнем заточки для украшений точит своё кольцо.
4. Админ заводит руду, указывает подкатегорию «руда» и в настройках переработки — что получает кузнец и что ювелир.
5. Игрок-«Книжник» после обновления видит профессию «Мистик».

### Edge Cases
- Нечётное количество руды при 2 → 1: перерабатывается только кратное количество, остаток остаётся.
- У сырья не настроен результат для этой профессии → понятная ошибка, ничего не списывается.
- Переполнение инвентаря результатом → поведение как в текущем крафте.
- Существующие на проде кристаллы стихий, трансмутированные ресурсы, эссенции — предметы остаются в инвентарях, но механики с ними пропадают (архитектор: предложить, что с ними делать; при необходимости вопрос к пользователю).
- Существующие точильные камни (3 шт., сейчас «общие» для кузнеца) — определить, к каким частям снаряжения они теперь относятся.

### Вопросы к пользователю (если есть)
- [x] Реагенты повара = ингредиенты алхимика → да; идут в эссенции или в зелья по рецепту
- [x] Старые механики алхимика → убрать (кристаллы, трансмутация)
- [x] Переработка смешанного сырья → нет, только один вид; результат задаётся в админке
- [x] Шанс неудачи → нет, всегда успешно; бонус к количеству есть
- [x] Откуда ингредиенты → новый вид сбора + торговцы; в будущем выращивание в доме
- [x] Древесина → для будущей постройки домов
- [x] Зачарователь без переработки → так задумано
- [x] Опыт за переработку → да
- [x] Подкатегории → список согласован, кристаллы убираем
- [x] Кто точит → любой, у кого есть камень
- [x] Пояс → без вставок, только быстрые слоты; заточка камнем зачарователя
- [x] Переплавка украшений у ювелира → убрать (и «Ювелирный лом» как механику)
- [x] Инструмент для сбора ингредиентов → не нужен, и без штрафа за его отсутствие
- [x] Название навыка сбора ингредиентов → «Собирательство»
- [x] Опыт за переработку → 5/12/25/50 за порцию по редкости (пока так, возможно поправим)
- [x] Шанс удвоения → бросается на каждую порцию
- [x] Вставка рун и огранок → доступна **любому игроку** с руной/огранкой (как заточка); **извлечение** — только профессии (ювелир — огранки, зачарователь — руны). Опыта за вставку/извлечение нет
- [x] Прокачка сбора ингредиентов → да, своя прокачка и бонусы по рангам, как у руды, трав и лесоруба
- [x] Опыт за заточку → никому; опыт профессии только за создание (крафт по рецепту и переработку)
- [x] Существующие 3 точильных камня → группа кузнеца (оружие, броня, шлем)
- [x] Названия камней других групп → рабочие: зачарователь — «Камень чар» (из наброска пользователя), ювелир — «Гравировальный резец» (подтверждено пользователем; в коде это только подпись группы, сами предметы админ называет как хочет)
- [x] Старые предметы (кристаллы, трансмутированные ресурсы, лом, эссенции стихий) → миграцией не трогать, админ удалит сам
- [x] Изучение рецептов → из предмета-рецепта, а также базовые рецепты выдаются автоматически при получении ранга (настройка в админке, `auto_learn_rank`, уже есть — проверить, что работает). Скрытый бесплатный `learn-recipe` без предмета — закрыть
- [x] Пропорции переработки → гибко: админ задаёт для каждого сырья и профессии, сколько сырья уходит и сколько результата получается (значения из таблицы выше — лишь примеры по умолчанию)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Summary
Almost everything lives in **inventory-service** (sync SQLAlchemy, Pydantic v1, Alembic head `021_add_item_is_food`, version table `alembic_version_inventory`) plus the live **frontend CraftTab**. The gathering fourth type also touches **locations-service** (async, Alembic head `042_recommended_level_ranges`), because the gathering nodes live there. Nothing else in the code refers to the slug `scholar` (it appears only in the seed data of migration 004). Prod has no blueprints. Only `photo-service` also relies on `items.blueprint_recipe_id`, and only for **recipe** items. Findings that matter for the design:
- "+15" already exists. `MAX_ENHANCEMENT_POINTS = 15` is the whole-item budget and `MAX_STAT_SHARPEN = 5` is the cap per stat. So the new work is: jewelry becomes sharpenable, stones get slot groups, and the blacksmith-only check goes away.
- Whetstones have **no slot-group field** today. They are ordinary `resource` items recognised only by `whetstone_level` (1/2/3 → 25/50/75%).
- Resource "subcategory" does not exist in the DB. The admin UI *infers* a "resource kind" (plain / repair kit / whetstone / crystal) from whichever field is filled in.
- The rank-up loop is copy-pasted **7 times** (`crud.execute_craft` plus 6 endpoints in `main.py`).
- **Pre-existing hole:** `POST /inventory/crafting/{cid}/learn-recipe` (`main.py:1990-2026`) lets any owner learn any active recipe of their profession and rank **for free**, without a recipe item. The frontend never calls it (the thunk `craftingSlice.learnRecipe` is never dispatched), but it can be reached through the gateway. It conflicts with "the recipe is learned once" if learning is supposed to cost a recipe item.

### Affected Services
| Service | Type of Changes (expected) | Files |
|---|---|---|
| inventory-service | remove blueprints, essence extraction and transmutation (and maybe smelting); sharpening rework; sockets without belt; resource subcategory + refining config + refining endpoint; rename scholar; new gathering skill + tool category; migrations 022+ | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `app/alembic/versions/022_…`, tests |
| locations-service | 4th node category (enum + Literal + mapping dicts) | `app/models.py:667-670`, `app/schemas.py:1536`, `app/crud.py:6316-6320, 6892-6901`, new Alembic `043_…`, `tests/test_gathering.py` |
| photo-service | none if `items.blueprint_recipe_id` stays (it still links recipe items) | `crud.py:260-263` (reads it) |
| frontend | CraftTab (new "Переработка" section, remove alchemist sections, sharpening for everyone), item admin (subcategory + refining config), recipes admin, gathering UI/admin, item constants, auction filter | see §8 |
| docs | `docs/services/inventory-service.md`, `locations-service.md`, `frontend.md` | — |

### 1. Professions, XP, recipes, blueprints
- Models (`inventory-service/app/models.py`):
  - `Profession` 244 (`name`, `slug` unique, `icon` URL from the DB, `sort_order`, `is_active`);
  - `ProfessionRank` 262 (`rank_number`, `name`, `required_experience`);
  - `Recipe` 279-302 (`required_rank`, `result_item_id`, `result_quantity`, `rarity` derived from the result item, `xp_reward`, **`is_blueprint_recipe`** 292, `auto_learn_rank` 294);
  - `RecipeIngredient` 305;
  - `CharacterProfession` 317 (one per character, `current_rank`, `experience`);
  - `CharacterRecipe` 333 (learned forever).
- Seed data: migration `004_add_professions_crafting.py:138-146` (6 professions; `('Книжник','scholar',…)` at 145) and the ranks at 150-158 (Ученик 0 / Подмастерье 500 / Мастер 2000).
- Public endpoints (`main.py`):
  - `GET /professions` 1577, `GET /professions/{cid}/my` 1586, `POST …/choose` 1635, `POST …/change` 1670 (resets rank and XP, keeps recipes);
  - crafting: `GET /crafting/{cid}/recipes` 1908, `POST …/craft` 1920 (requires the recipe to be learned **or** `blueprint_item_id`, 1953-1974), `POST …/learn-recipe` 1990 (free, see above), `POST …/learn-from-item` 2029 (consumes 1 item with `item_type='recipe'` and `blueprint_recipe_id == recipe_id`).
- Admin endpoints: `/admin/professions*` 1714-1877 (permissions `professions:read/create/update/delete/manage`) and `/admin/recipes*` 2112-2335 (the response includes `is_blueprint_recipe`).
- crud:
  - `choose_profession` 1261 and `change_profession` 1305 auto-learn the `auto_learn_rank == 1` recipes;
  - `set_character_rank` 1350 and `auto_learn_recipes_for_rank` 1380;
  - `create_recipe` 1485: **when `auto_learn_rank` is not set, it auto-creates an item with `item_type='recipe'`, `blueprint_recipe_id=recipe.id`, rarity `common`**;
  - `update_recipe` 1530 keeps that item in sync; `delete_recipe` ~1590 removes it from every inventory;
  - `get_available_recipes_for_character` 1613 merges learned recipes with **blueprint-sourced** ones (1656-1692, `source="blueprint"`);
  - `execute_craft` 1763 consumes the ingredients (FOR UPDATE), **consumes the blueprint** (1814-1830), adds the result via `_add_items_to_inventory` (1039, **no inventory capacity check at all**; this is the "overflow as in current craft" behaviour), awards XP (`xp_reward` or `RARITY_XP_MAP` 27) × `get_xp_multiplier` 2018, and runs the rank-up loop 1850-1866.
- Rank-up loop duplicates: `main.py` 2591 (sharpen), 2766 (essence), 2956 (transmute), 3230 (insert-gem), 3378 (extract-gem), 3560 (smelt). This is a natural candidate for one helper that the refining endpoint also uses.
- **What "single-use blueprint" means today:**
  - `items.item_type='blueprint'` together with `items.blueprint_recipe_id`. While such an item is in the inventory, its recipe shows up as `source="blueprint"` and can be crafted without learning it; each craft consumes one blueprint.
  - `recipes.is_blueprint_recipe` is **only stored and echoed back**; no logic reads it.
  - The same column `items.blueprint_recipe_id` is **also** the link for recipe items (`item_type='recipe'`), used by `learn-from-item`, `crud.get_recipe_item` 1901, `update_recipe`/`delete_recipe`, photo-service `crud.py:263` and the frontend `ItemContextMenu.tsx:244-253` ("Изучить"). **The column must stay** (it could be renamed later, but photo-service reads it with raw SQL).
- Removing blueprints touches:
  - **Backend:**
    - the enum value `'blueprint'` (`models.py:16-20`, `schemas.py:23`);
    - `ItemCreate` validator `schemas.py:297` (message "Рецепт можно привязать только к чертежу");
    - `_ensure_blueprint_recipe_exists` `main.py:157`;
    - craft branch 1953-1966, `CraftRequest.blueprint_item_id` `schemas.py:888-890`, `CraftResult.blueprint_consumed` 897, `RecipeOut.source` / `blueprint_item_id` 844-845;
    - `execute_craft` 1814-1830, `get_available_recipes…` 1656-1692;
    - `RecipeCreate` / `RecipeUpdate` / `RecipeAdminOut.is_blueprint_recipe` 867/883/922, the `Recipe.is_blueprint_recipe` column, and the `Recipe.blueprint_items` relationship (models 300; it stays valid for recipe items).
  - **Frontend:**
    - `constants/items.ts:9,27,48,90`, `ProfilePage/constants.ts:28`, `Auction/AuctionFilters.tsx:24`;
    - `ItemsAdminPage/ItemForm.tsx:94,184,221-231,665-670` and `itemFormRules.ts:150,175,246`;
    - `CraftTab/CraftConfirmModal.tsx:12`, `RecipeCard.tsx:90-95`, `CraftTab.tsx:143`;
    - `craftingSlice.ts:192-198`, `types/professions.ts:94-95,102,122,164`.
  - **Tests:** `test_crafting.py` (22 hits), `test_item_type_rules.py` (13), `test_craft_xp.py` (3), 1 each in `conftest.py`, `test_endpoint_auth.py`, `test_item_rarity_rules.py`, `test_unequip_shield.py`, `test_recipe_transmute_rarity_cap.py`.
  - **Data:** prod has 0 blueprints (brief). Loot tables and NPC shops store only `item_id` (no type checks anywhere outside inventory-service), so there are no other code dependencies.
  - Shrinking the MySQL ENUM needs `SELECT COUNT(*) FROM items WHERE item_type='blueprint'` = 0 first (fail-fast or convert).

### 2. Sharpening
- Constants in `crud.py:42-46`: `MAX_ENHANCEMENT_POINTS=15`, `MAX_STAT_SHARPEN=5`, `WHETSTONE_CHANCE={1:.25,2:.5,3:.75}`, `SHARPENABLE_TYPES={'head','body','cloak','belt','weapon'}` (already `'weapon'` after migration 019). The stat lists are at 64-78 (`MAIN_STAT_FIELDS` +1 per success; `FLOAT_STAT_FIELDS` +0.1; crit chance +0.5; crit damage +1.0).
- Where the increments are applied:
  - on equip, `build_modifiers_dict` `crud.py:602-619` (generic for any slot, so jewelry would work unchanged);
  - on sharpening an already equipped item, the delta at `main.py:2561-2576`.
- Data: `character_inventory` / `equipment_slots` `.enhancement_points_spent`, `.enhancement_bonuses` (JSON text; migration 007). It travels with the item, and the auction snapshots it (`crud.py:2330-2349`).
- Endpoints:
  - `GET /crafting/{cid}/sharpen-info/{row}?source=` `main.py:2342`: **no profession check**, but it returns 400 for non-`SHARPENABLE_TYPES`. It lists **all** whetstones in the inventory (`whetstone_level IS NOT NULL`, 2417-2435).
  - `POST /crafting/{cid}/sharpen` 2447 does: **blacksmith-only gate at 2459-2464** → type check 2500 → per-stat cap 2512 (message "(+5)") → budget check 2521 → stone validity is just "has `whetstone_level`" (2533). The stone is always consumed; success is rolled; **profession XP 10 goes to the blacksmith** (2580-2603).
  - Letting anyone sharpen raises a question: who gets XP when a non-blacksmith sharpens? (No profession → no XP; a profession other than blacksmith → XP to that profession?) This is for the architect or the user.
- Whetstone definition:
  - `items.whetstone_level` (models 29, migration 007 seeds 3 items with `item_type='resource'`: common / rare / legendary);
  - admin: `itemFormRules.ts` `ResourceKind "whetstone"`, `WHETSTONE_OPTIONS`, `detectResourceKind`.
  - Per-slot-group stones need a new item attribute (e.g. target group `weapon_armor` = weapon/body/head, `cloak_belt`, `jewelry` = ring/necklace/bracelet), validation in `sharpen` / `sharpen-info` (filter the stones by the item's type), and a migration that assigns the 3 existing stones to a group.
- Frontend:
  - `CraftTab/SharpeningSection.tsx` (hardcoded `SHARPENABLE_TYPES` 9-11 incl. belt, `MAX_POINTS` 13) is rendered **only when the slug is `blacksmith`** (`CraftTab.tsx:218-220`);
  - `SharpeningModal.tsx` (`MAX_POINTS=15`, stone picker). Both are live.
  - The "+N" badge is shown by `EquipmentPanel/EquipmentSlot.tsx:192-202`, `InventoryTab/ItemCell.tsx:199-209` and `ItemDetailModal.tsx:236`, and is generic.

### 3. Sockets
- Constants `crud.py:58-62`: `JEWELRY_TYPES={'ring','necklace','bracelet'}`, `ARMOR_WEAPON_TYPES={'head','body','cloak','belt','weapon'}` (**belt is here**), `SOCKETABLE_TYPES` (unused elsewhere), `GEM_PRESERVATION_CHANCES` by rank, `GEM_XP_REWARD=10`.
- Item types: `'gem'` (jeweler "огранки", migration 010) and `'rune'` (migration 013). `items.socket_count`; row `.socketed_gems` JSON list.
- Endpoints:
  - `GET socket-info` `main.py:2997`: jeweler/enchanter only; jeweler → `JEWELRY_TYPES` + gems, enchanter → `ARMOR_WEAPON_TYPES` + runes;
  - `POST insert-gem` 3110 (inserting consumes the stone and applies its modifiers if the item is equipped) and `POST extract-gem` 3269 (preservation roll by rank).
  - Who may insert or extract today: **only jeweler (gems → jewelry) and enchanter (runes → weapon/armor/cloak/belt)**. This matches the brief.
- Removing the belt affects:
  - `ARMOR_WEAPON_TYPES` (also used as `allowed_types` in extract-gem 3290; if it simply shrinks, runes already sitting in belts could no longer be extracted);
  - frontend `RuneSocketSection.tsx:9` (belt listed);
  - admin `itemFormRules.ts:162` (`sockets: equipment ? "runes"` with `EQUIPMENT_TYPES` incl. belt, 14-16), so the `socket_count` field is offered for belts;
  - the item validator has no socket rule by type (`socket_count` is accepted for any type).
  - Existing belts with `socket_count>0` or socketed runes need a data decision (prod: 0 runes, per the brief; belt `socket_count` unknown, so check it with SQL at migration time).

### 4. Removals: essence extraction, transmutation, smelting
- **Essence extraction:**
  - `GET extract-info` `main.py:2640` and `POST extract-essence` 2684 (alchemist, 75%);
  - column `items.essence_result_item_id` (models 31, self-FK `fk_items_essence_result_item_id`, relationship 147) plus schema field `ItemBase.essence_result_item_id`;
  - migration 008 seeded **7 "Кристалл …"** (common resources, price 50) and **7 "Эссенция огня/воды/воздуха/молнии/льда/света/тьмы"** (common resources, "извлечённая из кристалла…" in the description).
  - Frontend: `EssenceExtractionSection.tsx` (live for alchemist, `CraftTab.tsx:221-226`), `craftingSlice` extract thunks, state and selectors (221-246, 708-711), `api/professions.ts:158-178`, types; admin `ResourceKind "crystal"` + essence picker `ItemForm.tsx:175,210-218,643-660`.
  - Tests: `test_essence_extraction.py` (19 tests, delete).
  - The 7 essences could become the alchemist refining results (the "Эссенции" subcategory), but their descriptions mention crystals.
- **Transmutation:**
  - `RARITY_CHAIN` / `TRANSMUTE_RESULT_NAMES` / `TRANSMUTE_COST` / `TRANSMUTE_XP` `main.py:2808-2821`; `GET transmute-info` 2824 and `POST transmute` 2867 (look up the result item **by name**);
  - migration 009 seeded 4 "Трансмутированный ресурс (редкий/эпический/легендарный/мифический)"; the mythical one is id=30 on dev and is logged by 021.
  - Frontend: `TransmutationSection.tsx`, `craftingSlice` 247-272 and 713-716, `api/professions.ts:180-200`.
  - Tests: the transmute parts of `test_recipe_transmute_rarity_cap.py` (6 hits); the recipe-cap parts must stay.
- **Smelting (jeweler "переплавка"):**
  - `GET smelt-info/{row}` `main.py:3423`, `POST smelt` 3488; helpers `crud.find_recipe_for_item` 168, `calculate_smelt_returns` 183 (50% of recipe ingredients), `get_junk_item` 197 (looked up **by name** "Ювелирный лом", seeded by migration 010 as a common resource);
  - frontend `SmeltingSection.tsx` + `SmeltingModal.tsx` (live for jeweler), `craftingSlice` 338-363, api 372-392;
  - tests: the smelt cases in `test_gem_sockets.py` (e.g. 702-760).
  - **The brief does not list smelting among removals and does not list it for the jeweler either** → question below.
- Prod data (brief and task): 3 whetstones, 7 crystals, 4 transmuted resources, 1 jeweler junk item. All are plain `resource` rows; with `ON DELETE` rules they can sit in `character_inventory` (FK without cascade; `DELETE /items/{id}` returns 500 when the item is held, see ISSUES LOW), `auction_listings.item_id` (FK), `auction_storage`, `recipe_ingredients` (CASCADE), `trade_offer_items`, and loot/shop tables in other services (no FK). **Deleting these rows is risky; keeping them as ordinary resources (with a subcategory or "прочее") is safe.** Dropping `essence_result_item_id` needs the FK dropped first.

### 5. Item model: where a subcategory and refining config fit
- `items.item_type` is an ENUM without a name (models 16-20; MySQL ENUM changed with `ALTER … MODIFY` as in 010/013/016/019).
- Other enums: `tool_category_enum` (pickaxe/sickle/axe, models 42-45, `schemas.ToolCategory` 120-123), `armor_subclass_enum` (cloth / light / medium / heavy, 60-64; the "cloth for Мистик" rule is data only), `weapon_subclass_enum`, `item_rarity`.
- No resource subcategory column exists. The resource kinds are UI-only inference (`itemFormRules.ts:106-113` `ResourceKind`, `detectResourceKind` 125-130, select in `ItemForm.tsx:595-660`, payload reset `itemFormRules.ts:237-242`). The backend accepts `repair_power` / `whetstone_level` / `essence_result_item_id` on any type (no type-bound validator, unlike `tool_category`, `schemas.py:318-366`).
- Validators pattern: `ItemCreate` root validators `schemas.py:283-366` (type-bound fields, food/rarity, gathering tool). A new `resource_subcategory` (nullable, only for `item_type='resource'`) fits the same pattern. For the whetstone and repair-kit subcategories it could replace the inference.
- The per-profession "conversion result item" is 1:N per source item (the blacksmith **and** the jeweler refine ore) → either a side table (source_item_id, profession_id, result_item_id [+ ratios]) or a fixed set of nullable FK columns per refining profession on `items`. The existing precedent `essence_result_item_id` is a self-FK column. `ItemCreate`/`update_item` (`main.py:164, 250`) use `items:create/update`; no new permission is needed if the config is saved with the item.
- Admin list: `ItemsAdminPage/ItemList.tsx` loads the whole catalogue once and filters **client-side** by category, type, rarity and search (54-98); the categories are in `constants/items.ts:38-52` (`craft` = resource/blueprint/recipe/gem/rune). A subcategory filter is a local addition. `api/items.ts` `fetchAllItems({itemTypes})` is used by the essence picker (`ItemForm.tsx:213`). Backend `GET /inventory/items` (`main.py:127`) supports `item_type` and `category` filters (the latter only for tools, 281-317).
- Gathering nodes pick `result_item_id` without any type or subcategory validation (locations admin).

### 6. Gathering (FEAT-128; inventory migration 016 + locations migration 031)
- inventory-service:
  - `GatheringSkill.category` ENUM `('ore','herb','wood')` **unique** (models 421-427, migration 016:92-97), seeded as `mining` / `herbalism` / `woodcutting` with 5 ranks each (016:136-173);
  - `GatheringAwardRequest.skill_slug` validator hardcodes the 3 slugs (`schemas.py:1516-1520`);
  - `build_gathering_skills_response` `crud.py:3399` iterates the DB (generic); `award_gathering` `crud.py:~3570` resolves the skill by slug;
  - tool: `items.tool_category` ENUM pickaxe/sickle/axe (+ `ToolCategory`, `GET /items?category=` allowed set `main.py:294`).
- locations-service (owner of the nodes):
  - `GatheringNode.category` ENUM `gathering_node_category` `('ore','herb','wood')` (`models.py:667-670`, migration `031_add_gathering_nodes.py:46`);
  - `schemas.GatheringCategory = Literal["ore","herb","wood"]` 1536;
  - mappings `_CATEGORY_TO_SKILL_SLUG` `crud.py:6316` and `_GATHER_NODE_CATEGORY_TO_TOOL_CATEGORY` / `_SKILL_SLUG` 6892-6901. An unknown category gives a 422 in the tool validation (7011-7017). **A tool is optional** (`tool_inventory_item_id` may be None, 6489-6496).
- Frontend:
  - `types/gathering.ts:11,13` (category / slug unions);
  - admin `AdminLocationsPage/…/GatheringNodesEditor/GatheringNodesEditor.tsx:63` and `NodeRow.tsx:48,54`;
  - player side: `pages/LocationPage/GatheringSection/GatheringNodeCard.tsx:54`, `GatheringSection.tsx:55`, `ToolSelectionModal.tsx:33` (category→tool);
  - `ProfilePage/GatheringTab/GatheringSkillCard.tsx:19` (category→icon);
  - `constants/items.ts:221-226` (`TOOL_CATEGORIES`).
- A 4th type "ingredients" needs:
  - ENUM widen in **both** services (append-only ALTER on MySQL, safe);
  - a skill seed row + 5 rank rows (inventory);
  - the slug in the validator and the mappings;
  - a tool decision (new `tool_category` value, reuse an existing one, or no tool);
  - labels and icons on the frontend;
  - tests: `inventory-service/app/tests/test_gathering.py` (43 tests), `locations-service/app/tests/test_gathering.py`.

### 7. Rename Книжник → Мистик
- Code/config references to `scholar` or `Книжник`: **none** outside `004_add_professions_crafting.py:145` (seed) and old feature docs. No RBAC permission is per profession. Profession icons come from `professions.icon` (DB), not from the frontend. The frontend `constants/npc.ts:8-33` `blacksmith`/`alchemist` are **NPC roles** (character-service), unrelated.
- The rename is a data migration: `UPDATE professions SET name='Мистик', description=… WHERE slug='scholar'` (match by slug; the admin may have edited the name on prod). Changing the slug is optional (no code depends on it); keeping `scholar` avoids touching anything else. `CharacterProfession` references `profession_id`, so players keep the profession.

### 8. Frontend CraftTab: live vs dead
- Live path: `ProfilePage.tsx:21,88-92` renders `CraftTab` on the tab `craft` ("Крафт", `ProfileTabs.tsx:18`). `CraftTab.tsx` renders:
  - `ActiveBuffIndicator`, then `ProfessionSelect` (no profession) **or** `ProfessionRail` + `ProfessionInfo`;
  - by slug: blacksmith → `SharpeningSection`, alchemist → `EssenceExtractionSection` + `TransmutationSection`, jeweler → `GemSocketSection` + `SmeltingSection`, enchanter → `RuneSocketSection`;
  - then `RecipeList` → `RecipeCard`, and `CraftConfirmModal`.
  - The modals are opened from the sections: `SharpeningSection`→`SharpeningModal`, `GemSocketSection`/`RuneSocketSection`→`GemSocketModal`, `SmeltingSection`→`SmeltingModal`.
  - **All 17 files in `CraftTab/` are live**; none are imported elsewhere. There is no sharpen or socket entry in the item context menu.
- Dead: `ProfilePage/InventoryTab/InventoryTab.tsx` and `CharacterInfoPanel/CharacterInfoPanel.tsx` (the FEAT-164 lesson). `InventoryTab/ItemContextMenu.tsx` **is live** (imported by `CharacterTab/CharacterTab.tsx:3`) and holds "Изучить" for recipe items (`ItemContextMenu.tsx:243-256`, `profileSlice.learnRecipeFromItem` 605).
- `redux/slices/craftingSlice.ts` (733 lines): thunks for everything above (121-363) + selectors (689-733); `learnRecipe` thunk 206 is never dispatched.
- `types/professions.ts` (416 lines) and `api/professions.ts` (429 lines) hold types and calls for all mechanics.
- Admin: `Admin/RecipesAdminPage/RecipesAdminPage.tsx` (no `is_blueprint_recipe` UI; `auto_learn_rank` 57/71/205/313/330/524/790), `Admin/ProfessionsAdminPage/ProfessionsAdminPage.tsx` (edits name, slug and icon; the rename could also be done here, but a migration is safer).
- Rules to follow: the CraftTab components are already TS + Tailwind (checked: `CraftTab.tsx`, `SharpeningSection.tsx` use Tailwind and design-system classes).

### 9. Tests, Alembic, risks
- inventory-service tests to update or remove:
  - `test_essence_extraction.py` (remove);
  - `test_sharpening.py` (27 tests; the blacksmith gate "Non-blacksmith" section ~469, types incl. belt);
  - `test_gem_sockets.py` (42 tests; smelting cases; a belt socket case if any);
  - `test_crafting.py` / `test_craft_xp.py` (blueprint);
  - `test_item_type_rules.py` (blueprint type rules);
  - `test_recipe_transmute_rarity_cap.py` (transmute part);
  - `test_endpoint_auth.py`, `test_item_rarity_rules.py`, `test_unequip_shield.py`, `conftest.py` (single blueprint mentions);
  - `test_professions.py` (34 tests, rank-up and auto-learn; still valid);
  - `test_gathering.py` (4th skill).
  - Tests use SQLite + `Base.metadata.create_all`, so enum changes are picked up from the models.
- locations-service: `tests/test_gathering.py`.
- Alembic heads: inventory `021_add_item_is_food` → next `022_…` (revision id ≤ 32 chars, see ISSUES learning note); locations `042_recommended_level_ranges` → `043_…`.
- Risks:
  - **MySQL ENUM shrink** (`blueprint`) fails or truncates if rows still exist → follow the 019 pattern (widen → clean data → shrink) and check the counts. Appending enum values (`gathering` category, `tool_category`) is safe. Enum changes on `items` lock the table (small table, ~seconds).
  - **Dropping `essence_result_item_id`** needs the FK dropped first (`fk_items_essence_result_item_id`). The migration 008 downgrade then becomes inconsistent, which is acceptable but should be documented.
  - **Seeded rows referenced by name** (`Ювелирный лом`, `Трансмутированный ресурс …`): if the rows are kept, nothing breaks. If they are deleted: FK `character_inventory` (no cascade) → 500 / IntegrityError; auction rows (FK); loot and shop tables in other services (no FK → dangling ids).
  - **Existing whetstones**: they need a slot-group value, otherwise the new stone validation makes them unusable. The prod ids may differ from dev; match by `whetstone_level IS NOT NULL`.
  - **Belts with runes / socket_count** after removing belt from sockets: modifiers of socketed runes are still in the character stats; they need extraction or refund if any exist.
  - **Letting everyone sharpen**: XP attribution; `check_not_in_battle` / `check_not_gathering` stay; the non-profession path needs `cp=None` handling (the current code dereferences `cp.profession` / `cp.experience`).
  - **Refining**: row locks on the source stack (pattern: `with_for_update`, as in `transmute_item`); the source item may be spread over several stacks (`execute_craft` pattern 1780-1810); results via `_add_items_to_inventory` (no capacity limit today; gathering has a free-slot check `/internal/.../free_slots_check`, `main.py:1528`); the double roll with a named rank→chance constant; no `NOW()`-type issues.
  - **Free `learn-recipe` endpoint** (above): it contradicts "recipes are learned from recipe items / by rank" if that is the intent.
  - **Frontend**: remove the dead thunks and state together with the sections, otherwise `tsc` passes but unused code stays. `constants/items.ts` `RARITYLESS_ITEM_TYPES` and the `craft` category list include `blueprint`.
  - No cross-service HTTP contract changes except locations↔inventory `GatheringAwardRequest.skill_slug` (both sides must ship together; append-only).

### Open questions for PM/user
1. **Jewelry smelting ("переплавка украшений" → materials / "Ювелирный лом")**: the brief does not mention it. Keep it, or remove it along with transmutation and essence extraction?
2. **Ingredient gathering tool**: ore → pickaxe, herbs → sickle, wood → axe. For ingredients: a new tool (which one, what name?), one of the existing tools, or no tool?
3. **XP when a non-blacksmith sharpens**: no profession XP; XP to the sharpener's own profession; or XP only for the profession that makes that stone (blacksmith / enchanter / jeweler)?
4. **The 3 existing whetstones**: assign them to "оружие/броня/шлем" (blacksmith), or make them universal legacy stones for any gear?
5. **Old items** (7 crystals, 4 transmuted resources, "Ювелирный лом", 7 elemental essences): keep them as ordinary resources in a subcategory (the essences could become alchemist refining results), or delete them (only safe if nobody holds them)?
6. **Free recipe learning** (`learn-recipe` endpoint, not used by the UI): is a recipe learned only from a recipe item (plus auto-learn at a rank)? If yes, the endpoint should be removed.
7. **Refining ratio**: fixed per profession as in the brief table (blacksmith 2→1, jeweler 1→1, …), with the admin choosing only the result item? Or should the admin also set the ratio per raw item?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Overview and key decisions

One stage, three workstreams that meet only at the contracts below:
**inventory-service** (the bulk), **locations-service** (4th gathering category), **frontend**.
No new services, no Nginx/Docker/env changes (all new routes live under the existing `/inventory/` prefix), no new RBAC module.

| # | Decision | Why |
|---|----------|-----|
| D1 | Refining config is a **side table `item_conversions`** (source item × profession → ratio + result item), edited through dedicated admin endpoints guarded by the existing `items:read` / `items:update` permissions. | Ore is refined by two professions (1:N). A table beats N nullable columns and keeps the widely used `Item` schema unchanged. Existing permissions → no new `permissions` rows → no RBAC test change. |
| D2 | Which raw subcategory a profession may refine, and which product subcategory it must yield, is a **backend constant keyed by profession slug** (`REFINING_RULES`) and is **exposed by an endpoint** so the frontend never duplicates it. | The slug is already the code-level identity of professions (`blacksmith` check today). One source of truth. |
| D3 | Resource subcategory = new nullable ENUM column `items.resource_subcategory`, only valid for `item_type='resource'`. `NULL` = «Прочее» (legacy crystals, transmuted resources, «Ювелирный лом», elemental essences stay untouched, as the user decided). | Matches the existing type-bound validator pattern. |
| D4 | Whetstones: keep `items.whetstone_level` (chance tiers), add ENUM `items.whetstone_group` = `weapon_armor` \| `cloak_belt` \| `jewelry`. The 3 existing whetstones → `weapon_armor` + subcategory `whetstone`. Group labels are UI-only strings in **one** frontend constant. | Minimal model change; labels renameable without backend work. |
| D5 | **Anyone** may sharpen with a stone of the matching group. **No XP for sharpening.** Socket insert/extract also **stop giving XP** (the rule "profession XP only for creation: recipe craft + refining"). Who may insert/extract is unchanged (jeweler → gems → jewelry, enchanter → runes → weapon/body/head/cloak). | User answers. The socket XP removal follows from the same rule and is called out in the report. |
| D6 | All profession XP goes through **one helper** `crud.award_profession_xp(db, cp, base_xp)` (multiplier + rank-up loop + auto-learn). The 6 copy-pasted loops disappear with their endpoints (essence/transmute/smelt removed, sharpen/socket XP removed); craft and refine use the helper. | Removes duplication instead of adding a 7th copy. |
| D7 | Rank-based base recipes: new idempotent `crud.sync_auto_learned_recipes(db, cp)` learns **every active recipe of the character's profession with `auto_learn_rank IS NOT NULL AND auto_learn_rank <= current_rank`**. Called lazily on `GET /professions/{cid}/my` and `GET /crafting/{cid}/recipes`, and from `choose`, `change`, admin `set-rank` and `award_profession_xp`. | **Gap found:** today recipes are granted only at the moment of choosing/ranking up with `== rank`, so a base recipe the admin creates *now* never reaches the 7 existing rank-1 players. Lazy sync fixes this with no backfill job. |
| D8 | Free `POST /crafting/{cid}/learn-recipe` is **removed** (route deleted → 404/405). Learning = `learn-from-item` (recipe item) or D7. | User answer. |
| D9 | Blueprints removed entirely: enum value `blueprint`, `recipes.is_blueprint_recipe`, craft/recipe blueprint branches. `items.blueprint_recipe_id` **stays** (it links recipe items; photo-service reads it). | User answer + analysis. |
| D10 | Essence extraction, transmutation, jewelry smelting removed (endpoints, helpers, schemas, frontend sections). Column `items.essence_result_item_id` is **dropped** (FK first). Item rows are not touched. | The column is only used by the removed mechanic. |
| D11 | Runes: belt removed from insertable types. Extraction still accepts belts (legacy safety, prod has 0 runes). Validator: `socket_count > 0` only for weapon/head/body/cloak/ring/necklace/bracelet. | Brief. |
| D12 | 4th gathering category `ingredient`, skill slug `foraging` («Собирательство», working name), **same progression as the other 3** (skill row + 5 rank rows with the same XP thresholds and bonuses: rank XP, double chance, speed, stamina). **Toolless:** no tool accepted, **no ×2 time penalty, rank double-chance applies** (today double chance is gated on having a tool). | User decision #1. |
| D13 | Refining: always succeeds; input is a **quantity of one source item** (summed over the character's stacks); `batches = quantity // source_quantity`, the remainder is not consumed; **the double roll is per batch** (`REFINE_DOUBLE_CHANCE_BY_RANK = {1: 0.05, 2: 0.10, 3: 0.20}`); XP per batch by result rarity (`REFINE_XP_BY_RARITY = {common: 5, rare: 12, epic: 25, legendary: 50}`, × XP buff multiplier). No capacity check (same as craft). | Brief + edge cases. Named constants are easy to tune. |
| D14 | Scholar → «Мистик» is a data update **by slug** (`scholar` slug kept). Seed descriptions of the professions that mention removed mechanics are refreshed **only if still equal to the 004 seed text** (admin edits preserved). | Brief; no code depends on the slug. |
| D15 | Sharpening entry point for everyone = **«Заточить» in `ItemContextMenu`** (live: mounted by `CharacterTab`, opened from `InventoryPanel` cells and from `EquipmentSlot` via `AvatarEquipmentGrid`), which opens the existing `SharpeningModal`. The blacksmith-only `SharpeningSection` is removed from CraftTab. Same pattern as «Починить» → `RepairModal`. | Verified live path (not the dead `InventoryTab.tsx` / `CharacterInfoPanel.tsx`). |

### 3.1 Constants (inventory-service `crud.py`)

```python
# Sharpening groups (D4)
SHARPEN_GROUP_TYPES = {
    "weapon_armor": frozenset({"weapon", "body", "head"}),     # blacksmith stones
    "cloak_belt":   frozenset({"cloak", "belt"}),              # enchanter stones
    "jewelry":      frozenset({"ring", "necklace", "bracelet"}),  # jeweler stones
}
SHARPENABLE_TYPES = frozenset().union(*SHARPEN_GROUP_TYPES.values())
def sharpen_group_for_type(item_type) -> Optional[str]: ...

# Sockets (D11)
RUNE_INSERT_TYPES = frozenset({"head", "body", "cloak", "weapon"})
RUNE_EXTRACT_TYPES = RUNE_INSERT_TYPES | {"belt"}   # legacy extraction only
SOCKETABLE_TYPES = JEWELRY_TYPES | RUNE_INSERT_TYPES  # used by the socket_count validator
# ARMOR_WEAPON_TYPES is removed (replace usages)

# Refining (D2, D13)
RAW_SUBCATEGORIES = ("ore", "herb", "wood", "ingredient", "trophy")
PRODUCT_SUBCATEGORIES = ("ingot", "magic_dust", "essence", "reagent", "material")
TOOL_SUBCATEGORIES = ("whetstone", "repair_kit")
REFINING_RULES = {  # profession slug -> (accepted source subcategory, required result subcategory)
    "blacksmith": ("ore", "ingot"),
    "jeweler":    ("ore", "magic_dust"),
    "alchemist":  ("reagent", "essence"),
    "cook":       ("ingredient", "reagent"),
    "scholar":    ("trophy", "material"),   # «Мистик»
}
REFINE_DOUBLE_CHANCE_BY_RANK = {1: 0.05, 2: 0.10, 3: 0.20}
REFINE_XP_BY_RARITY = {"common": 5, "rare": 12, "epic": 25, "legendary": 50}
CONVERSION_QTY_MIN, CONVERSION_QTY_MAX = 1, 100
REFINE_MAX_QUANTITY = 9999
```

Removed: `WHETSTONE`-profession XP (`base_xp = 10`), `GEM_XP_REWARD`, `RARITY_CHAIN`/`TRANSMUTE_*` (main.py), `find_recipe_for_item`, `calculate_smelt_returns`, `get_junk_item`, `ARMOR_WEAPON_TYPES`.

### 3.2 DB changes

#### inventory-service — migration `022_profession_rework` (revision id ≤ 32 chars, down_revision `021_add_item_is_food`)

Follow the 019 style (`_enum()` helper, raw `ALTER … MODIFY`). Idempotent guards (`_columns()`, table existence) as in 016/021.

```sql
-- 0. Guard (fail-fast, before any change)
SELECT COUNT(*) FROM items WHERE item_type = 'blueprint';
--   > 0  -> raise RuntimeError("Migration 022: N blueprint items still exist (ids …). Delete or convert them first.")

-- 1. Blueprints out (widen/clean/shrink collapses to a plain shrink because the guard proved 0 rows)
ALTER TABLE items MODIFY COLUMN item_type ENUM('head','body','cloak','belt','ring','necklace','bracelet','weapon',
  'consumable','resource','scroll','misc','recipe','gem','rune','gathering_tool') NOT NULL;
ALTER TABLE recipes DROP COLUMN is_blueprint_recipe;

-- 2. Essence extraction out (FK first)
ALTER TABLE items DROP FOREIGN KEY fk_items_essence_result_item_id;   -- look the name up via inspector; skip if absent
ALTER TABLE items DROP COLUMN essence_result_item_id;

-- 3. Resource subcategory + whetstone group
ALTER TABLE items ADD COLUMN resource_subcategory ENUM(
  'ore','herb','wood','ingredient','trophy',
  'ingot','magic_dust','essence','reagent','material',
  'whetstone','repair_kit') NULL;
ALTER TABLE items ADD COLUMN whetstone_group ENUM('weapon_armor','cloak_belt','jewelry') NULL;
CREATE INDEX ix_items_resource_subcategory ON items (resource_subcategory);

-- 4. Backfill ONLY whetstones and repair kits (legacy crystals/essences/junk stay NULL = «Прочее»)
UPDATE items SET resource_subcategory='whetstone', whetstone_group='weapon_armor'
  WHERE whetstone_level IS NOT NULL AND item_type='resource';
UPDATE items SET resource_subcategory='repair_kit'
  WHERE repair_power IS NOT NULL AND item_type='resource' AND resource_subcategory IS NULL;
-- Log (logger.warning) any item with whetstone_level/repair_power whose item_type <> 'resource' (not modified).

-- 5. Conversion config
CREATE TABLE item_conversions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  source_item_id INT NOT NULL,
  profession_id INT NOT NULL,
  source_quantity INT NOT NULL DEFAULT 1,
  result_item_id INT NOT NULL,
  result_quantity INT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_item_conversion UNIQUE (source_item_id, profession_id),
  CONSTRAINT fk_item_conv_source FOREIGN KEY (source_item_id) REFERENCES items(id) ON DELETE CASCADE,
  CONSTRAINT fk_item_conv_result FOREIGN KEY (result_item_id) REFERENCES items(id) ON DELETE CASCADE,
  CONSTRAINT fk_item_conv_prof   FOREIGN KEY (profession_id) REFERENCES professions(id) ON DELETE CASCADE,
  CONSTRAINT ck_item_conv_qty CHECK (source_quantity BETWEEN 1 AND 100 AND result_quantity BETWEEN 1 AND 100)
);
CREATE INDEX ix_item_conversions_result ON item_conversions (result_item_id);

-- 6. 4th gathering skill (append-only enum widen is safe)
ALTER TABLE gathering_skills MODIFY COLUMN category ENUM('ore','herb','wood','ingredient') NOT NULL;
INSERT INTO gathering_skills (slug, name, category, description, max_rank)
  SELECT 'foraging','Собирательство','ingredient','Навык сбора ингредиентов',5
  WHERE NOT EXISTS (SELECT 1 FROM gathering_skills WHERE slug='foraging');
-- + 5 rank rows for that skill, copied from the 016 table (only if the skill has no ranks):
--   (1,0,0,0,0) (2,10,4,4,4) (3,25,8,8,8) (4,50,12,12,12) (5,100,20,20,20)
--   Better: copy the CURRENT rank rows of 'herbalism' if they exist (admin may have tuned them), else the 016 defaults.

-- 7. Scholar -> Мистик (by slug), guarded against the unique name
UPDATE professions SET name='Мистик',
       description='Книги, свитки, тканевая броня и шлемы; переработка трофеев в материалы'
  WHERE slug='scholar' AND NOT EXISTS (SELECT 1 FROM (SELECT id FROM professions WHERE name='Мистик') t);
-- Refresh seed descriptions only where description still equals the 004 seed text:
--   blacksmith: 'Оружие, броня и шлемы; точильные камни для оружия, брони и шлема; ремкомплекты; переработка руды в слитки'
--   alchemist:  'Зелья и пояса; переработка алхимических реагентов в эссенции'
--   cook:       'Еда; переработка ингредиентов в алхимические реагенты'
--   enchanter:  'Руны и оружие магов; камни чар для плаща и пояса; вставка и извлечение рун'
--   jeweler:    'Кольца, ожерелья, браслеты и огранки; гравировальные резцы для украшений; переработка руды в магическую пыль'

-- 8. Report only (no change): belts with socket_count > 0 or non-empty socketed_gems -> logger.warning
```

**Downgrade** (reverse order):
1. restore professions name/description where `slug='scholar' AND name='Мистик'` (→ 'Книжник' + 004 text); restore changed seed descriptions only where they equal the new text;
2. `DELETE FROM gathering_skills WHERE slug='foraging'` (cascades ranks and progress — documented data loss), then shrink the category enum back to 3 values;
3. `DROP TABLE item_conversions`;
4. drop index + `whetstone_group` + `resource_subcategory`;
5. re-add `essence_result_item_id INT NULL` + FK `fk_items_essence_result_item_id` (ON DELETE SET NULL) — values are lost (documented);
6. re-add `recipes.is_blueprint_recipe BOOL NOT NULL DEFAULT 0`;
7. widen `item_type` with `'blueprint'` in its original position (order of 019 `ITEM_TYPES_NEW`).

#### locations-service — migration `043_gathering_ingredient_category` (down_revision `042_recommended_level_ranges`)

```sql
ALTER TABLE gathering_nodes MODIFY COLUMN category ENUM('ore','herb','wood','ingredient') NOT NULL;
```
Downgrade: `SELECT COUNT(*) FROM gathering_nodes WHERE category='ingredient'` → if > 0 raise RuntimeError (fail-fast, the admin must delete/recategorise them); else shrink to 3 values. (Check the actual table name in `models.py`/031 before writing.)

#### ORM (`models.py`, inventory)
- `Items.item_type` enum without `'blueprint'`; drop `essence_result_item_id` + its relationship; add `resource_subcategory = Column(Enum(..., name='resource_subcategory_enum'), nullable=True, index=True)`, `whetstone_group = Column(Enum('weapon_armor','cloak_belt','jewelry', name='whetstone_group_enum'), nullable=True)`.
- `Recipe.is_blueprint_recipe` removed (keep `blueprint_items` relationship — still valid for recipe items; optionally rename the attribute later).
- New `ItemConversion` model (columns above, relationships `source_item`, `result_item`, `profession`).
- `GatheringSkill.category` enum + `'ingredient'`.
- locations `GatheringNode.category` enum + `'ingredient'`.

Tests use SQLite `create_all` → the ORM enums **must** match the migration exactly (the review compares them).

### 3.3 API contracts

All paths below are the full gateway paths (router prefix `/inventory`). Error messages are Russian. Pydantic v1.

#### 3.3.1 Items (changed, additive)

`GET/POST/PUT /inventory/items…` — `ItemBase` gains:
```json
{ "resource_subcategory": "ore | herb | wood | ingredient | trophy | ingot | magic_dust | essence | reagent | material | whetstone | repair_kit | null",
  "whetstone_group": "weapon_armor | cloak_belt | jewelry | null" }
```
and **loses** `essence_result_item_id`. `item_type` loses `blueprint`.

`ItemCreate` validators (new/changed, all 422 with Russian messages):
- `resource_subcategory` set and `item_type != 'resource'` → «Подкатегорию можно указать только для ресурса».
- `resource_subcategory == 'whetstone'` ⇔ (`whetstone_level` in {1,2,3} **and** `whetstone_group` set); `whetstone_level`/`whetstone_group` without that subcategory → «Уровень и группу камня заточки можно указать только для камня заточки». Missing ones → «Для камня заточки укажите уровень и группу».
- `repair_power` set on a `resource` requires subcategory `repair_kit` («Сила ремонта указывается только для ремкомплекта»); `repair_kit` requires `repair_power` > 0.
- `socket_count > 0` only for `SOCKETABLE_TYPES` («Слоты доступны только для оружия, брони, шлема, плаща и украшений»).
- `blueprint_recipe_id` only for `item_type='recipe'` («Рецепт можно привязать только к предмету-рецепту»).
- Rarity cap (FEAT-164) already covers resources.

`GET /inventory/items` gains optional query `resource_subcategory` (validated against the enum, 422 otherwise). Used by the admin result-item pickers.

#### 3.3.2 Refining rules — `GET /inventory/crafting/refining-rules`
Auth: `get_current_user_via_http` (any logged-in user; static data). Response 200:
```json
[ { "profession_id": 1, "profession_slug": "blacksmith", "profession_name": "Кузнец",
    "source_subcategory": "ore", "result_subcategory": "ingot" } ]
```
Built from `REFINING_RULES` joined to active professions by slug (a profession missing in the DB is skipped). Enchanter is absent by design.
**Fix (QA, 2026-09-18) — refining source ≠ "raw":** valid refining sources are the set of `source_subcategory` values in this response (`ore`, `reagent`, `ingredient`, `trophy`), **not** the «Сырьё» group: the alchemist's input `reagent` is a refined product. Response shape unchanged (the set is derivable from the list; a separate field would turn the list into an object). The frontend must show the conversions editor for a resource whose subcategory is any rule's `source_subcategory` (not `isRawSubcategory`). Backend: `crud.REFINING_SOURCE_SUBCATEGORIES`; the conversions PUT accepts a source with such a subcategory (else 400 «Перерабатывать можно только ресурсы с подкатегорией: …»), and each entry's profession must accept exactly that subcategory (unchanged).

#### 3.3.3 Admin conversions
`GET /inventory/admin/items/{item_id}/conversions` — `require_permission("items:read")`
`PUT /inventory/admin/items/{item_id}/conversions` — `require_permission("items:update")`, **replaces the whole set** for the source item (transaction).

PUT body:
```json
{ "conversions": [
  { "profession_id": 1, "source_quantity": 2, "result_item_id": 55, "result_quantity": 1 },
  { "profession_id": 5, "source_quantity": 1, "result_item_id": 71, "result_quantity": 1 } ] }
```
Response (both GET and PUT) 200:
```json
{ "source_item_id": 40, "conversions": [
  { "id": 3, "profession_id": 1, "profession_name": "Кузнец", "source_quantity": 2,
    "result_item": { "id": 55, "name": "Медный слиток", "image": "…", "item_rarity": "common" },
    "result_quantity": 1 } ] }
```
Validation: 404 source item not found; 400 source is not `resource` or its subcategory is not raw / not accepted by that profession («Кузнец не перерабатывает эту подкатегорию»); 400 duplicate `profession_id` in the list; 400 profession has no refining rule; 404 result item not found; 400 result not `resource` or its subcategory ≠ the rule's `result_subcategory` («Результат для профессии Кузнец должен иметь подкатегорию «Слитки»»); 400 result == source; 422 quantities outside 1..100; list max length = number of rules (5). Empty list = remove all conversions. Changing an item's subcategory away from a raw one via `PUT /items/{id}` deletes its conversions in the same transaction (keeps data consistent).
*Implementation notes (Backend Dev, #2):* an unknown `profession_id` → 404 «Профессия не найдена»; more than 5 entries → 400. The `PUT /items/{id}` cleanup (`crud.delete_stale_conversions`) also covers the item **as a result**: a row is dropped when the item stops being a `resource` of the subcategory that the row's profession yields, so refining never produces an item of the wrong kind.

#### 3.3.4 Player refining
`GET /inventory/crafting/{character_id}/refine-info` — auth + `verify_character_ownership`.
```json
{ "can_refine": true, "profession_slug": "blacksmith",
  "source_subcategory": "ore", "result_subcategory": "ingot",
  "double_chance_pct": 5,
  "sources": [
    { "source_item_id": 40, "name": "Медная руда", "image": "…", "item_rarity": "common",
      "owned_quantity": 7, "source_quantity": 2, "max_batches": 3,
      "result_item": { "id": 55, "name": "Медный слиток", "image": "…", "item_rarity": "common" },
      "result_quantity": 1, "xp_per_batch": 5 } ] }
```
No profession or a profession without a rule → `{ "can_refine": false, …nulls, "sources": [] }` (200, not an error — the UI hides the section). `sources` = items in the character's inventory (identified rows only, summed over stacks) that have a conversion for the character's profession; items with a config but 0 owned are not listed.

`POST /inventory/crafting/{character_id}/refine` — auth + ownership + `check_not_in_battle("Нельзя перерабатывать во время боя")` + `check_not_gathering("Нельзя перерабатывать во время добычи")`.
```json
{ "source_item_id": 40, "quantity": 7 }
```
`quantity`: int 1..`REFINE_MAX_QUANTITY` (422 otherwise). Flow (one transaction):
1. profession exists (400 «У персонажа нет профессии»), has a rule (400 «Ваша профессия не перерабатывает сырьё»);
2. source item exists (404) with `resource_subcategory == rule.source` (400 «Этот предмет нельзя переработать»);
3. conversion row for (source, profession) exists (400 «Для этого сырья не настроен результат переработки»); result item exists (500-safe: 400 «Результат переработки не найден» — never call `_add_items_to_inventory` with a missing item, it silently no-ops);
4. lock the character's stacks of the source item `with_for_update()`, sum quantities → `owned`; `quantity > owned` → 400 «Недостаточно сырья»;
5. `batches = quantity // source_quantity`; 0 → 400 «Нужно минимум N шт. для переработки»; consume `batches * source_quantity` across stacks (execute_craft pattern), leftover stays;
6. per batch roll `random.random() < REFINE_DOUBLE_CHANCE_BY_RANK[rank]` → `doubled_batches`; `total = result_quantity * (batches + doubled_batches)`; `_add_items_to_inventory`;
7. `award_profession_xp(db, cp, REFINE_XP_BY_RARITY[result_rarity] * batches)`; commit. ValueError → 400, other → rollback + 500 «Ошибка при переработке».

Response 200:
```json
{ "success": true, "source_item_id": 40, "consumed_quantity": 6, "leftover_quantity": 1,
  "batches": 3, "doubled_batches": 1,
  "result_item": { "id": 55, "name": "Медный слиток", "image": "…", "item_rarity": "common" },
  "result_quantity": 4,
  "xp_earned": 15, "new_total_xp": 115, "rank_up": false, "new_rank_name": null,
  "auto_learned_recipes": [] }
```
(`leftover_quantity` = `quantity - consumed_quantity`, i.e. of the requested amount.)

#### 3.3.5 `award_profession_xp` (crud helper, not an endpoint)
```python
def award_profession_xp(db, cp, base_xp: int) -> dict:
    # xp = int(base_xp * get_xp_multiplier(db, cp.character_id)); cp.experience += xp
    # rank-up loop over cp.profession.ranks; then sync_auto_learned_recipes(db, cp)
    # returns {"xp_earned", "new_total_xp", "rank_up", "new_rank_name", "auto_learned_recipes": [{"id","name"}]}
```
No commit inside (caller commits). `execute_craft` uses it (its response shape is unchanged except `blueprint_consumed` removed).

#### 3.3.6 Crafting / recipes (changed)
- `POST /inventory/crafting/{cid}/craft` body = `{ "recipe_id": int }` (`blueprint_item_id` removed; an extra field is ignored by Pydantic v1 → old clients don't break). Requires a learned recipe. Response: `blueprint_consumed` removed.
- `GET /inventory/crafting/{cid}/recipes`: calls `sync_auto_learned_recipes` first (commit), returns learned recipes only; `RecipeOut.source` is always `"learned"` (field kept for compatibility), `blueprint_item_id` removed.
- `GET /inventory/professions/{cid}/my`: calls `sync_auto_learned_recipes` first when a profession exists.
- `POST /inventory/crafting/{cid}/learn-recipe`: **removed**. `LearnRecipeRequest` stays (used by `learn-from-item`).
- `learn-from-item`: unchanged logic; add `check_not_in_battle`/`check_not_gathering` is NOT required (learning is instant) — leave as is.
- `choose` / `change` / admin `set-rank`: replace their inline auto-learn copies with `sync_auto_learned_recipes`. `auto_learn_recipes_for_rank` is removed (its callers go through the helper).
- Admin recipes: `is_blueprint_recipe` removed from `RecipeCreate`/`RecipeUpdate`/`RecipeAdminOut` (extra fields ignored on input).

#### 3.3.7 Sharpening (changed)
`GET /inventory/crafting/{cid}/sharpen-info/{row}?source=` — no profession check (unchanged). 400 if type not in `SHARPENABLE_TYPES` (now includes jewelry). Response adds `"sharpen_group": "weapon_armor|cloak_belt|jewelry"`; `whetstones` lists **only** stones with `whetstone_group == sharpen_group` (and `resource_subcategory == 'whetstone'` is implied by the validator; filter on `whetstone_level IS NOT NULL AND whetstone_group = :g`). Each whetstone entry adds `"whetstone_group"`.

`POST /inventory/crafting/{cid}/sharpen` body unchanged (`inventory_item_id`, `whetstone_item_id`, `stat_field`, `source`).
- Profession gate **removed** (character without a profession may sharpen).
- New check after loading the stone: `whetstone_item.whetstone_group != sharpen_group_for_type(item.item_type)` → 400 «Этот камень не подходит для этого предмета» (before consuming anything).
- XP block removed. Response **drops** `xp_earned`, `new_total_xp`, `rank_up`, `new_rank_name`; everything else unchanged. Equipped-item delta logic unchanged (works for jewelry, generic).
- Keep: ownership, battle/gathering locks, identification check, per-stat cap, 15-point budget, stone always consumed, chances by `whetstone_level`.

#### 3.3.8 Sockets (changed)

> **Contract change (user decision, 2026-09-18, implemented by Backend Dev in #2):** inserting is open to **any** character that holds the gem/rune (like sharpening); extraction stays profession-only. This supersedes the "who may insert is unchanged" part of D5 and the first bullet below.
> - `POST insert-gem` — no profession check. Target type decides what fits: ring/necklace/bracelet ← `gem` (else 400 «В украшение можно вставить только огранку»); weapon/body/head/cloak (`RUNE_INSERT_TYPES`) ← `rune` (else 400 «В этот предмет можно вставить только руну»); belt → 400 «Этот тип предмета не поддерживает руны»; any other type → 400 «Этот тип предмета не поддерживает камни и руны». Ownership, battle/gathering locks, identification, slot checks unchanged. Response `{success, item_name, gem_name, slot_index}`.
> - `POST extract-gem` — unchanged gate: jeweler → gems from jewelry, enchanter → runes from `RUNE_EXTRACT_TYPES` (incl. legacy belts); anyone else → 400. Slot index is checked against the stored sockets (legacy rows may hold more than the current `socket_count`). Response `{success, item_name, gem_name, gem_preserved, preservation_chance, slot_index}`.
> - `GET socket-info/{row}?source=` — no profession needed. 400 for types without sockets; a belt is returned only while it still holds runes (else 400 «Этот тип предмета не поддерживает руны»). Response adds:
>   `"insertable_type": "gem" | "rune"`, `"can_insert": bool` (false for belts), `"can_extract": bool` (character's profession matches: jeweler for gems, enchanter for runes), `"extract_preservation_chance": int | null` (by rank, only when `can_extract`). `socket_count` = number of listed slots; `available_gems` is empty when `can_insert` is false.

- ~~`socket-info`, `insert-gem`: enchanter allowed types = `RUNE_INSERT_TYPES`~~ (superseded above; belt → 400 «Этот тип предмета не поддерживает руны» still applies).
- `extract-gem`: enchanter allowed types = `RUNE_EXTRACT_TYPES` (belt still allowed); `socket-info` for a belt is allowed only when it has socketed runes (so the UI can extract legacy runes) — optional, prod has 0 runes; if it complicates the code, skip and log in ISSUES.
- XP removed from `insert-gem` / `extract-gem`; responses drop `xp_earned`, `new_total_xp`, `rank_up`, `new_rank_name` (check `InsertGemResult`/`ExtractGemResult`).

#### 3.3.9 Removed endpoints
`GET extract-info`, `POST extract-essence`, `GET transmute-info`, `POST transmute`, `GET smelt-info/{row}`, `POST smelt`, `POST learn-recipe` (+ their schemas). Frontend is the only caller (checked: no other service calls them).

#### 3.3.10 Gathering (cross-service, both sides ship together)
inventory `GatheringAwardRequest.skill_slug` accepts `{"mining","herbalism","woodcutting","foraging"}`. `GET /inventory/characters/{cid}/gathering-skills` returns the 4th skill automatically (DB-driven).

locations-service:
- `GatheringCategory = Literal["ore","herb","wood","ingredient"]`.
- `_CATEGORY_TO_SKILL_SLUG` and `_GATHER_NODE_CATEGORY_TO_SKILL_SLUG` gain `"ingredient": "foraging"`; `_GATHER_NODE_CATEGORY_TO_TOOL_CATEGORY` stays tool-only; new `TOOLLESS_GATHER_CATEGORIES = frozenset({"ingredient"})`.
- Start gathering (`POST …` existing route, body unchanged): for a toolless node, a non-null `tool_inventory_item_id` → 422 «Для сбора этого ресурса инструмент не нужен».
- `_compute_effective_gather_params(..., has_tool, tool_required: bool)`: the ×2 time penalty and the "double chance = 0" gate apply only when `tool_required and not has_tool`. For toolless nodes: rank speed/stamina/double bonuses apply with the same caps; tool bonuses = 0; durability consumption = 0.
- Player node payload (`/client/details`) adds `"tool_required": bool` per node (additive) so the UI does not hardcode the category.

### 3.4 Security

| Endpoint | Auth | Authorization | Locks | Validation |
|---|---|---|---|---|
| `GET refining-rules` | JWT (`get_current_user_via_http`) | any user | — | — |
| `GET/PUT admin/items/{id}/conversions` | JWT | `items:read` / `items:update` (existing; admin gets all automatically) | — | ids > 0, quantities 1..100, list ≤ 5, no duplicate profession, subcategory rules; result ≠ source |
| `GET refine-info` | JWT | `verify_character_ownership` | — | — |
| `POST refine` | JWT | ownership | not in battle, not gathering; `with_for_update` on source stacks | `quantity` 1..9999, subcategory + config checks before any write |
| `sharpen` / `sharpen-info` | JWT (unchanged) | ownership | battle/gathering (unchanged) | new stone-group check before consuming |
| sockets | unchanged | unchanged | unchanged | belt rule |
| locations gather start | unchanged | unchanged | unchanged | toolless → tool must be null |

- Rate limiting: no new Nginx rules (`/inventory/` is already covered by the gateway limits); refining is bounded by owned items and one transaction with row locks.
- No raw SQL with string interpolation (the ORM is used; the migration's SQL is static). Error messages never echo internal exceptions (500 → generic Russian text; details only in `logger.error`).
- Removing `learn-recipe` closes the free-learning hole.
- **RBAC:** no new permissions, therefore no `test_rbac_permissions.py` change (CLAUDE.md §10.13 does not apply).

### 3.5 Frontend design

Rules: TypeScript only, Tailwind + design-system classes (`gray-bg`, `gold-text`, `btn-blue`, `btn-line`, `chip-outline`, `input-underline`, `modal-overlay`, `modal-content`, `gold-outline`, `dropdown-item`, `rounded-card`), no `React.FC`, 360px+ layouts, every API error shown as a Russian toast/inline message. **CraftTab is not redesigned now** (separate future task) — only functional changes in the existing visual language.

#### Shared constants — new file `src/constants/professions.ts`
```ts
export type WhetstoneGroup = 'weapon_armor' | 'cloak_belt' | 'jewelry';
// UI labels only — rename here, nothing else changes
export const WHETSTONE_GROUP_LABELS: Record<WhetstoneGroup, string> = {
  weapon_armor: 'Точильный камень',       // blacksmith: оружие, броня, шлем
  cloak_belt: 'Камень чар',               // enchanter: плащ, пояс
  jewelry: 'Гравировальный резец',        // jeweler: кольца, ожерелья, браслеты
};
export const WHETSTONE_GROUP_TARGETS: Record<WhetstoneGroup, string> = {
  weapon_armor: 'оружие, броня, шлем', cloak_belt: 'плащ, пояс', jewelry: 'кольцо, ожерелье, браслет',
};
export const SHARPEN_GROUP_BY_ITEM_TYPE: Record<string, WhetstoneGroup> = {
  weapon: 'weapon_armor', body: 'weapon_armor', head: 'weapon_armor',
  cloak: 'cloak_belt', belt: 'cloak_belt',
  ring: 'jewelry', necklace: 'jewelry', bracelet: 'jewelry',
};
export const SHARPENABLE_ITEM_TYPES = new Set(Object.keys(SHARPEN_GROUP_BY_ITEM_TYPE));
export const RUNE_SOCKET_TYPES = new Set(['weapon', 'body', 'head', 'cloak']);
export const MAX_ENHANCEMENT_POINTS = 15;

export type ResourceSubcategory = 'ore'|'herb'|'wood'|'ingredient'|'trophy'
  |'ingot'|'magic_dust'|'essence'|'reagent'|'material'|'whetstone'|'repair_kit';
export const RESOURCE_SUBCATEGORY_LABELS: Record<ResourceSubcategory, string> = {
  ore: 'Руда', herb: 'Травы', wood: 'Древесина', ingredient: 'Ингредиенты', trophy: 'Трофеи',
  ingot: 'Слитки', magic_dust: 'Магическая пыль', essence: 'Эссенции', reagent: 'Алхимические реагенты', material: 'Материалы',
  whetstone: 'Камни заточки', repair_kit: 'Ремкомплекты',
};
export const RESOURCE_SUBCATEGORY_GROUPS = [
  { label: 'Сырьё', items: ['ore','herb','wood','ingredient','trophy'] },
  { label: 'Продукты переработки', items: ['ingot','magic_dust','essence','reagent','material'] },
  { label: 'Расходники профессий', items: ['whetstone','repair_kit'] },
] as const;
export const RESOURCE_SUBCATEGORY_NONE_LABEL = 'Прочее';
```
(`SHARPEN_GROUP_BY_ITEM_TYPE` duplicates a backend constant for the menu visibility only; the backend is authoritative and returns the group in `sharpen-info`.)

#### Types / API / Redux
- `types/professions.ts`: remove blueprint fields (`source` stays `'learned'`), essence/transmute/smelt types, sharpen XP fields, socket XP fields; add `RefiningRule`, `RefineInfo`, `RefineSource`, `RefineResult`, `ItemConversion`, `ItemConversionsPayload`; `SharpenInfo.sharpen_group`, `SharpenWhetstoneInfo.whetstone_group`.
- `api/professions.ts`: remove extract/transmute/smelt/learn-recipe calls; `craftItem` sends only `recipe_id`; add `getRefiningRules`, `getRefineInfo`, `refine`, admin `getItemConversions`, `putItemConversions` (the admin ones may live in `api/items.ts` next to the item calls — pick one and keep it consistent).
- `redux/slices/craftingSlice.ts`: remove essence/transmute/smelt thunks, state, selectors and the unused `learnRecipe` thunk; `craftItem` without `blueprintItemId`; add `fetchRefineInfo`, `refineItem` with `refineInfo`, `refineInfoLoading`, `refineLoading`, `refineError` + selectors. Refining conversions for the admin stay local component state (no slice), like the rest of the item admin form.
- `types/gathering.ts`: `GatheringCategory` + `'ingredient'`, `GatheringSkillSlug` + `'foraging'`, `GatheringNode.tool_required: boolean`.
- `constants/items.ts`, `ProfilePage/constants.ts`, `Auction/AuctionFilters.tsx`: remove `blueprint` everywhere (type lists, labels, icons, `RARITYLESS_ITEM_TYPES`, the `craft` category).

#### CraftTab (`components/ProfilePage/CraftTab/`)
- `CraftTab.tsx`: remove `SharpeningSection`, `EssenceExtractionSection`, `TransmutationSection`, `SmeltingSection` (delete the files, and `SmeltingModal.tsx`); keep `GemSocketSection` (jeweler) and `RuneSocketSection` (enchanter); add `<RefiningSection characterId />` for any character with a profession (it renders nothing when `can_refine` is false); `handleConfirmCraft` without blueprint.
- **New `RefiningSection.tsx`** — title «Переработка» + one-line hint («Руда → слитки», built from `RESOURCE_SUBCATEGORY_LABELS[source/result]`) + «Шанс двойного результата: N%». List of `sources` as rows/cards: icon, name (rarity color as elsewhere), «Есть: 7», ratio «2 → 1 {result name}», button «Переработать». Empty state: «Нет сырья для переработки ({subcategory label})». Loading spinner and error text. Layout: `grid grid-cols-1 sm:grid-cols-2 gap-3`, no fixed widths.
- **New `RefineModal.tsx`** — `modal-overlay` / `modal-content gold-outline gold-outline-thick`, `max-w-[420px] w-full mx-4`: source → result preview, quantity input (`input-underline`, `type=number`, `inputMode=numeric`, min = source_quantity, max = owned, step = source_quantity, plus «Макс.» button), computed «Будет израсходовано X, получите Y (+ шанс удвоения)», leftover note when not a multiple, confirm `btn-blue`, cancel `btn-line`. On success: toast «Получено: {name} ×{n}» (+ «Удвоение ×k» if any) and «+XP», rank-up / auto-learned recipes toasts (same as craft), refresh `refineInfo`, profession, recipes, inventory (`fetchInventory`). Errors → toast with backend `detail` or «Не удалось переработать».
- `RuneSocketSection.tsx`: use `RUNE_SOCKET_TYPES` (belt removed). `GemSocketModal`/sections: drop XP display if present.
- `RecipeCard.tsx`, `CraftConfirmModal.tsx`: remove blueprint badges/text.

#### Sharpening for everyone
- `InventoryTab/ItemContextMenu.tsx` (**live**, mounted by `CharacterTab`): new action «Заточить» when `SHARPENABLE_ITEM_TYPES.has(item.item_type)` and (`contextMenu.slotType` is set **or** `inventoryItem.is_identified !== false`) and `(inventoryItem.enhancement_points_spent ?? 0) < MAX_ENHANCEMENT_POINTS`. It opens `SharpeningModal` with `source = contextMenu.slotType ? 'equipment' : 'inventory'` and `rowId = inventoryItem.id` (for equipment the constructed item's `id` is the slot row id — same as `RepairModal`). The modal is rendered by the menu component like `RepairModal`. Fast slots (`FastSlots.tsx`) hold consumables only → the type check hides the action there.
- `CraftTab/SharpeningModal.tsx` (keep the location; import it from the menu): remove XP text and the `fetchCharacterProfession` refresh; use `MAX_ENHANCEMENT_POINTS` from constants; header shows «Нужен: {WHETSTONE_GROUP_LABELS[group]} ({targets})»; empty state when no matching stones: «Нет подходящих камней. Нужен «{label}»»; after success refresh inventory + equipment (already done). Make sure the modal is portaled / `fixed` so it works when opened from the context menu, fits 360px (`max-h-[90vh] overflow-y-auto`, stat list wraps).
- The dev must open the profile page, open the menu on an inventory item **and** on an equipped item, and see «Заточить» (live check, not only tsc).

#### Item admin (`components/ItemsAdminPage/`)
- `itemFormRules.ts`: drop `blueprint`, the `crystal` resource kind and the essence picker rules; replace the inferred `ResourceKind` with the real `resource_subcategory` field (select with groups + «Прочее» = null); `whetstone_level` + `whetstone_group` visible and required only for `whetstone`; `repair_power` only for `repair_kit`; payload reset clears hidden fields (send `null`); `socket_count` visible only for weapon/head/body/cloak/jewelry (belt removed); `blueprint_recipe_id` only for `recipe`.
- `ItemForm.tsx`: the new select + fields; **new `ItemConversionsEditor.tsx`** shown when the item is a `resource` with a raw subcategory **that at least one refining rule accepts** (rules from `GET refining-rules`): one block per matching profession — toggle «Настроить», `source_quantity` and `result_quantity` number inputs (1..100), result item picker filtered by `item_type=resource&resource_subcategory={rule.result_subcategory}`. Loads existing config via GET when editing; saved via PUT **after** the item save succeeds (for a new item — with the id from the create response). Save errors shown inline + toast; the item save itself is not rolled back (show «Предмет сохранён, но настройки переработки — нет: …»). For a new raw item show the editor too (it saves after create). When there is no matching rule (herb, wood), show a muted note «Эта подкатегория пока не перерабатывается».
- `ItemList.tsx`: add a subcategory filter (select, shown when the type filter is `resource` or category `craft`), client-side like the others, incl. «Прочее» (null).

#### Recipes admin
`Admin/RecipesAdminPage/RecipesAdminPage.tsx`: remove any `is_blueprint_recipe` from payload/types; show a hint next to `auto_learn_rank`: «Базовый рецепт: выдаётся автоматически всем с этим рангом (и уже имеющим его)».

#### Gathering
- Admin `GatheringNodesEditor.tsx`, `NodeRow.tsx`: category option «Ингредиенты» (`ingredient`).
- Player `GatheringNodeCard.tsx` / `GatheringSection.tsx` / `ToolSelectionModal.tsx`: when `node.tool_required === false`, «Собрать» starts gathering directly with `tool_inventory_item_id: null` (no tool modal, no "без инструмента" warning); category label/icon for `ingredient`; `NODE_CATEGORY_TO_TOOL` typed as `Partial<Record<…>>`.
- `ProfilePage/GatheringTab/GatheringSkillCard.tsx`: icon/label for `ingredient` (reuse an existing icon asset or a lucide/emoji-free SVG already used by the project; no new assets required).
- `constants/items.ts` `TOOL_CATEGORIES` unchanged.

### 3.6 Data flow

```
Refine:
Player → CraftTab.RefiningSection → GET /inventory/crafting/{cid}/refine-info → inventory-service → MySQL (professions, items, item_conversions, character_inventory)
Player → RefineModal → POST /inventory/crafting/{cid}/refine
       → inventory-service: ownership, battle/gathering locks → SELECT … FOR UPDATE character_inventory
       → consume source, add result (character_inventory), award_profession_xp (character_professions, character_recipes) → COMMIT
       (no cross-service calls)

Admin config:
Admin → ItemForm → PUT /inventory/items/{id} (items:update) → then PUT /inventory/admin/items/{id}/conversions (items:update)
      → user-service /users/me (existing RBAC check) → item_conversions (replace set)

Sharpen (any player):
CharacterTab → ItemContextMenu «Заточить» → SharpeningModal → GET sharpen-info → POST sharpen
      → inventory-service (stone group check, consume, roll) → if equipped: HTTP → character-attributes-service (existing delta call)

Gathering ingredients:
LocationPage → POST start (tool=null) → locations-service (toolless: no penalty) → attributes-service consume_stamina (existing)
finalize → HTTP POST inventory-service award (skill_slug='foraging') → gathering XP/rank + item
```

### 3.7 Cross-service validation
- `items` table is read by photo-service (image columns + `blueprint_recipe_id`, kept) and by locations-service raw SQL (`item_type`, `tool_category`, `gather_*`, kept). Dropping `essence_result_item_id` and `recipes.is_blueprint_recipe`: grep found no reader outside inventory-service (reviewer must re-grep incl. mirror models in photo-service).
- `item_type='blueprint'` is referenced nowhere outside inventory-service + frontend (grep).
- locations → inventory award contract: append-only slug; both services deploy together in one push (single `docker compose up --build`). Until an admin creates an `ingredient` node, no call carries `foraging`.
- `GET gathering-skills` response shape unchanged (one more element).
- Removed inventory endpoints: only the frontend calls them (grep over `services/`).
- Frontend build must not reference removed thunks/types (`tsc --noEmit`).

### 3.8 Risks and mitigations
- **Enum shrink** (`blueprint`) — guarded count check; prod has 0.
- **ORM ↔ migration enum drift** — SQLite tests use the ORM; a QA test compares the ORM enum values with the migration constants.
- **Silent failures** (project pattern) — `_add_items_to_inventory` returns silently for an unknown item → refine validates the result item first; tests must assert actual `character_inventory` rows and use the real column names (`resource_subcategory`, `whetstone_group`, `item_conversions.*`); conftest must build tables from the real models, not a hand-written schema.
- **Lazy auto-learn on GET** writes on a read path — idempotent (unique constraint `uq_character_recipe`); handle `IntegrityError` on a concurrent double insert by rollback + continue (do not 500 the GET).
- **Removed XP for sockets** — a behaviour change beyond sharpening; justified by the user's rule, reported explicitly.
- **Frontend dead code** — deleting sections without their thunks leaves unused code; the task requires removing both.
- **Deploy** — prod CI deploy takes the stack down during build (known); the migration is small (items ~hundreds of rows).
- **Known unrelated issue (for ISSUES.md):** `update_recipe` ignores explicit `null` (`if value is not None`), so an admin cannot switch a recipe from auto-learn back to item-learned; `DURABILITY_SLOT_TYPES` still lists `main_weapon`/`additional_weapons` (check whether the slot types still use these names before filing).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Parallelism: **#1 → #2** (same service, #2 builds on the model/migration of #1) run in parallel with **#3** (locations) and with **#4–#7** (frontend, coded against the contracts in §3.3). **#8–#9** (QA) start after #2/#3. **#10** docs after #2/#3. **#11** Review last.
Backend devs: `python -m py_compile` on every touched file; run the service's pytest inside Docker (no host Python/node, see memory). Frontend devs: `npx tsc --noEmit` and `npm run build` inside the frontend container. No commits during work (the user commits once at the end).

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **inventory: schema layer.** Migration `022_profession_rework` exactly as §3.2 (guards, blueprint enum shrink, drop `recipes.is_blueprint_recipe`, drop FK + `items.essence_result_item_id`, add `resource_subcategory` + index and `whetstone_group`, backfill whetstones → `whetstone`/`weapon_armor` and repair kits → `repair_kit`, `item_conversions` table, gathering category `ingredient` + `foraging` skill + 5 ranks (copy herbalism ranks, else 016 defaults), scholar → «Мистик» by slug, seed-description refresh only where unchanged, warning logs for belts with sockets) with a full downgrade. ORM updates in `models.py` (enums identical to the migration, `ItemConversion` model, relationships). Schemas in `schemas.py`: `ItemBase` fields (+`resource_subcategory`, +`whetstone_group`, −`essence_result_item_id`), `ItemType` without `blueprint`, new `ResourceSubcategory`/`WhetstoneGroup` enums, all `ItemCreate` validators from §3.3.1, conversion/refine/refining-rule schemas, `CraftRequest`/`CraftResult`/`RecipeOut`/`RecipeCreate`/`RecipeUpdate`/`RecipeAdminOut` blueprint fields removed, sharpen/socket result XP fields removed, removed-mechanic schemas deleted, `GatheringAwardRequest` accepts `foraging`. Constants in `crud.py` per §3.1. | Backend Developer | DONE | `services/inventory-service/app/alembic/versions/022_profession_rework.py`, `app/models.py`, `app/schemas.py`, `app/crud.py` (constants only) | — | `alembic upgrade head` and `alembic downgrade -1` then `upgrade head` again succeed on the dev MySQL; the 3 whetstones get `whetstone`/`weapon_armor`; `professions` row `scholar` is named «Мистик»; `foraging` skill has 5 ranks; migration refuses to run if a blueprint item exists; py_compile passes. |
| 2 | **inventory: logic + endpoints.** (a) `award_profession_xp` and `sync_auto_learned_recipes` helpers (§3.3.5, D7), used by `execute_craft`, refine, `choose_profession`, `change_profession`, `set_character_rank`; remove `auto_learn_recipes_for_rank` and every inline rank-up loop; lazy sync in `GET /professions/{cid}/my` and `GET /crafting/{cid}/recipes` (IntegrityError-safe). (b) Remove blueprints from craft/recipes (`execute_craft`, `get_available_recipes_for_character`, `_ensure_blueprint_recipe_exists`, recipe create/update). (c) Delete `learn-recipe`, `extract-info`, `extract-essence`, `transmute-info`, `transmute`, `smelt-info`, `smelt` and their helpers/constants. (d) Sharpening per §3.3.7 (no profession gate, stone-group check, jewelry sharpenable, no XP, `sharpen_group` in info, filtered stones). (e) Sockets per §3.3.8 (belt out of insert, legacy extract, no XP). (f) New endpoints `GET /crafting/refining-rules`, `GET /crafting/{cid}/refine-info`, `POST /crafting/{cid}/refine`, `GET/PUT /admin/items/{item_id}/conversions` per §3.3.2–3.3.4 (route order: the static `refining-rules` path must not be shadowed by `/{character_id}` routes). (g) `GET /items` `resource_subcategory` filter; `PUT /items/{id}` deletes conversions when the subcategory stops being raw/accepted. (h) Add the two unrelated findings of §3.8 to `docs/ISSUES.md` (after checking them). | Backend Developer | DONE | `services/inventory-service/app/main.py`, `app/crud.py`, `docs/ISSUES.md` | #1 | All contracts in §3.3 behave as specified (manual curl through the gateway with a dev token: refine 7 ore with 2→1 → 3 batches, leftover 1, XP > 0; non-blacksmith sharpens a ring with a jewelry stone; weapon stone on a ring → 400; `POST learn-recipe` → 404/405; creating an `auto_learn_rank=1` recipe makes it appear in an existing rank-1 character's `GET recipes`); `grep -n "blueprint_item_id\|is_blueprint_recipe\|essence_result_item_id\|transmute\|smelt\|GEM_XP_REWARD" app/*.py` is empty (outside alembic); no rank-up loop left outside `award_profession_xp`; existing tests that are not about removed features still pass; py_compile passes. |
| 3 | **locations: ingredient gathering.** Migration `043_gathering_ingredient_category` (+ guarded downgrade), `GatheringNode.category` enum, `GatheringCategory` Literal, skill-slug maps (`ingredient → foraging`), `TOOLLESS_GATHER_CATEGORIES`, 422 when a tool is sent for a toolless node, `_compute_effective_gather_params(..., tool_required)` (no ×2 penalty, rank double chance applies), `tool_required` in the player node payload, zero durability consumption. | Backend Developer | DONE | `services/locations-service/app/alembic/versions/043_gathering_ingredient_category.py`, `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py` (if the payload is built there) | — (ships together with #1/#2) | Admin can create an `ingredient` node; a player gathers it with no tool, time = base (with rank speed), double chance = rank bonus; sending a tool → 422; finalize awards `foraging` XP in inventory-service; ore/herb/wood behaviour unchanged; py_compile + existing gathering tests pass. |
| 4 | **frontend: shared types, constants, API, Redux.** New `src/constants/professions.ts` (§3.5, jeweler label «Гравировальный резец»); update `types/professions.ts`, `types/gathering.ts`, `api/professions.ts` (+ admin conversion calls in `api/items.ts` or `api/professions.ts`), `redux/slices/craftingSlice.ts` (remove essence/transmute/smelt/learnRecipe/blueprint, add refine state + thunks + selectors); remove `blueprint` from `constants/items.ts`, `ProfilePage/constants.ts`, `Auction/AuctionFilters.tsx`. | Frontend Developer | DONE | files listed | — (contracts §3.3) | `tsc --noEmit` passes; no references to removed thunks/types remain (`grep -rn "extractEssence\|transmute\|smelt\|blueprint" src` only hits `blueprint_recipe_id`). |
| 5 | **frontend: CraftTab + sharpening for everyone.** Remove the 4 dead sections + `SmeltingModal`; add `RefiningSection.tsx` + `RefineModal.tsx` (§3.5); belt removed from `RuneSocketSection`; blueprint UI removed from `RecipeCard`/`CraftConfirmModal`/`CraftTab`; «Заточить» in the live `InventoryTab/ItemContextMenu.tsx` for inventory and equipped items → `SharpeningModal` (group label, empty state, no XP, `MAX_ENHANCEMENT_POINTS`). No full redesign; design-system classes; 360px. | Frontend Developer | DONE | `components/ProfilePage/CraftTab/*`, `components/ProfilePage/InventoryTab/ItemContextMenu.tsx` | #4 | Live check on the dev site: a blacksmith refines ore (toasts with result + XP); a character **without** a profession sees «Заточить» on an inventory ring and on an equipped weapon and the modal lists only matching stones; the jeweler/enchanter sections still work; no console errors; 360px layout does not overflow; `tsc` + `npm run build` pass. |
| 6 | **frontend: item + recipe admin.** `itemFormRules.ts`/`ItemForm.tsx`: real `resource_subcategory` select (groups + «Прочее»), whetstone level + group (labels from constants), repair power for repair kits, crystal kind/essence picker/blueprint removed, sockets not offered for belts; new `ItemConversionsEditor.tsx` (rules from `refining-rules`, save after item save, inline errors); `ItemList.tsx` subcategory filter; `RecipesAdminPage.tsx` blueprint leftovers removed + auto-learn hint. | Frontend Developer | DONE | `components/ItemsAdminPage/ItemForm.tsx`, `itemFormRules.ts`, `ItemConversionsEditor.tsx` (new), `ItemList.tsx`, `components/Admin/RecipesAdminPage/RecipesAdminPage.tsx` | #4 | Admin creates «Медная руда» (ore) with blacksmith 2→1 «Медный слиток» and jeweler 1→1 «Магическая пыль», reloads and sees the config; the result picker offers only the matching subcategory; backend validation errors are shown; filter by subcategory works; `tsc` + build pass. |
| 7 | **frontend: gathering.** `ingredient` category in the admin node editor and the player node card (label «Ингредиенты», icon), direct start without the tool modal when `tool_required === false`, `foraging` card in `GatheringTab/GatheringSkillCard.tsx`. | Frontend Developer | DONE | `AdminLocationsPage/EditForms/EditLocationForm/GatheringNodesEditor/{GatheringNodesEditor,NodeRow}.tsx`, `pages/LocationPage/GatheringSection/{GatheringNodeCard,GatheringSection,ToolSelectionModal}.tsx`, `ProfilePage/GatheringTab/GatheringSkillCard.tsx` | #4 | Live: an ingredient node starts without a tool prompt; the profile shows the 4th skill with its rank/XP; ore nodes still ask for a tool; `tsc` + build pass. |
| 8 | **QA: inventory-service tests.** Update/remove per analysis §9 (delete `test_essence_extraction.py`; strip transmute/smelt/blueprint/learn-recipe cases; sharpening "non-blacksmith is rejected" becomes "non-blacksmith and no-profession succeed"; XP assertions for sharpen/sockets become "profession XP unchanged"). New tests: **refining** (2→1 with odd quantity leaves the remainder; 1→2; stacks spread over several rows; double roll with patched `random` → exact quantity; XP + rank-up + auto-learn via the helper; wrong subcategory, missing config, missing result item → 400 and **nothing consumed** (assert rows); in battle / gathering → blocked; other user's character → 403; quantity 0 / huge → 422; SQL-injection-like strings in body → 422); **admin conversions** (replace set, duplicate profession, wrong result subcategory, result == source, quantity bounds, no permission → 403, subcategory change deletes config); **sharpening groups** (each group accepts its types, mismatched stone → 400 and stone not consumed, jewelry sharpenable, equipped jewelry applies the delta via the mocked attributes call, no XP change); **sockets** (belt insert → 400, belt extract allowed, no XP); **auto-learn** (recipe created after the character reached rank 1 appears in `GET recipes`; rank-2 recipe does not appear at rank 1; appears after XP rank-up; inactive recipe never; idempotent on repeated GET); `learn-recipe` → 404/405; **item validators** (subcategory only for resource, whetstone requires level + group, repair kit requires power, socket_count on belt → 422, `blueprint` type → 422); **gathering** award with `foraging`. **Silent-failure guards:** fixtures create rows through the real ORM models with the real column names; at least one test reads back `item_conversions`, `items.resource_subcategory`, `items.whetstone_group` and `character_inventory` quantities from the DB (not only the response); a test asserts the ORM enum values of `item_type`, `resource_subcategory`, `whetstone_group`, `gathering_skills.category` equal the constants in migration 022 (import the migration module). | QA Test | DONE (1 test red = bug, see §6) | `services/inventory-service/app/tests/test_refining.py` (new), `test_item_conversions_admin.py` (new), `test_auto_learn_recipes.py` (new), `test_migration_022_enums.py` (new), `test_sharpening.py`, `test_gem_sockets.py`, `test_crafting.py`, `test_craft_xp.py`, `test_item_type_rules.py`, `test_recipe_transmute_rarity_cap.py`, `test_professions.py`, `test_gathering.py`, `test_endpoint_auth.py`, `test_item_rarity_rules.py`, `test_unequip_shield.py`, `conftest.py`; delete `test_essence_extraction.py` | #1, #2 | Full inventory-service pytest passes in Docker; the new tests fail if the refine query or the stone-group check is broken (verify by temporarily breaking one and reverting). |
| 9 | **QA: locations-service tests.** `_compute_effective_gather_params` for toolless (no penalty, rank double chance) vs tool categories (unchanged, incl. the no-tool penalty for ore); start on an ingredient node with a tool → 422; without a tool → session created with correct seconds/stamina; finalize sends `skill_slug='foraging'` to the mocked inventory call; `tool_required` in the node payload; ORM enum vs migration 043 constants. | QA Test | DONE | `services/locations-service/app/tests/test_gathering.py` (+ new file if cleaner) | #3 | Full locations-service pytest passes in Docker. |
| 10 | **Docs.** Update `docs/services/inventory-service.md` (new/removed endpoints, tables, constants, XP rule), `docs/services/locations-service.md` (4th category, toolless rule), `docs/services/frontend.md` (CraftTab sections, context-menu sharpening, admin conversions), `docs/ARCHITECTURE.md` if it lists the items/professions schema. | Backend Developer | DONE (PM: inventory/locations docs updated by devs; ARCHITECTURE.md and frontend.md have no stale references) | docs files | #2, #3 | Docs match the implemented contracts; removed endpoints are no longer documented. |
| 11 | **Review.** Full checklist incl. cross-service grep (§3.7), ORM ↔ migration enum equality, migration upgrade/downgrade on dev MySQL, py_compile, both services' pytest, `tsc` + `npm run build`, live verification (refine, sharpening from the context menu by a non-crafter on inventory + equipped items, admin conversion config, ingredient gathering, «Мистик» shown, `learn-recipe` closed), Tailwind/TS/no `React.FC`/360px rules, Russian error display, security table §3.4. | Reviewer | TODO | all | #1–#10 | Checklist passed, live verification with zero console/500 errors. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-18
**Result:** FAIL (one blocking frontend rule violation; everything else passes)

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/RefiningSection.tsx:112-142` | **360px layout broken (CLAUDE.md §10.12, blocking).** Each source card is one row: 48px icon + text + `btn-blue` «Переработать» (uppercase, `shrink-0`). At a 360px viewport the text column gets ~30px: the item name shows as «Р…», and «Есть: 2» and the result name wrap almost letter by letter (screenshot taken live). Fix: stack the button under the text on narrow screens (e.g. `flex-wrap` with the button `w-full sm:w-auto`, or `flex-col min-[420px]:flex-row`), then re-check at 360px. | Frontend Developer | FIX_REQUIRED |
| 2 | `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/SharpeningModal.tsx:215` | Stale label «Новые статы (2 поинта)», while every stat costs 1 point (backend `point_cost = 1`, rows show «1п»). Pre-existing text, but the modal is now shown to every player from the context menu. Change it to «Новые статы». | Frontend Developer | FIX_REQUIRED (trivial, non-blocking) |
| 3 | `services/frontend/app-chaldea/src/components/ItemsAdminPage/itemFormRules.ts:209` | Leftover `delete payload.essence_result_item_id;`. Harmless (Pydantic v1 ignores the extra field), but it is the last reference to the dropped column. | Frontend Developer | OPTIONAL |
| 4 | this file, §4 task #10 | Task #10 is still `TODO`, although `docs/services/inventory-service.md` and `locations-service.md` are updated and correct. `docs/services/frontend.md` has no CraftTab/sharpening section at all (nothing stale); a short note (refining section, «Заточить»/«Гнёзда» in the item context menu, conversions editor) is optional. | PM / Backend Developer | OPTIONAL |
| 5 | `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/RefineModal.tsx` («Опыт профессии: +N») | The preview shows `batches × xp_per_batch` without the XP-buff multiplier (the backend applies it). Cosmetic. | Frontend Developer | NOTE |

Outside this feature (logged, not blocking): `POST /inventory/{character_id}/items` has no auth at all (reachable through the gateway without a token). Added to `docs/ISSUES.md` as HIGH.

#### Contracts
- Backend ↔ frontend: the refining, conversions, sharpening (`sharpen_group`, `whetstone_group`) and socket-info (`insertable_type`, `can_insert`, `can_extract`, `extract_preservation_chance`) schemas, and the removed XP/blueprint fields, match `types/professions.ts`, `types/gems.ts`, `types/gathering.ts` and `api/*.ts`, as verified against the live responses. Route order is fine: `/crafting/refining-rules` is not shadowed.
- Cross-service: locations → inventory `skill_slug='foraging'` checked live end to end (a forced finalize awarded 1 foraging XP and 1 item). No service reads `items.essence_result_item_id`, `recipes.is_blueprint_recipe` or `item_type='blueprint'`. Repo-wide grep over `services/` and `docker/`, excluding alembic and tests, found only #3. photo-service raw SQL touches only `blueprint_recipe_id` (kept) for `item_type='recipe'`. locations raw SQL reads only `item_type='gathering_tool'`. No mirror enums of `item_type` or of the gathering category exist elsewhere.
- Removed endpoints: `POST learn-recipe` → 404 live. `extract-*`, `transmute*` and `smelt*` have no routes and no callers.
- Tests ↔ implementation: the new tests hit the real endpoints and read back DB rows (`item_conversions`, `resource_subcategory`, `whetstone_group`, `character_inventory`). The ORM enums are compared with the 022/043 constants.

#### Migrations / prod data
- The dev DB is a prod dump with the same counts as prod (3 whetstones, 4 repair kits, 7 crystals, 7 elemental essences, 4 transmuted resources, «Ювелирный лом», 0 blueprints, 0 belts with sockets). The heads are 022 and 043 (they applied on startup). `alembic downgrade -1 && alembic upgrade head` succeeds in both containers. The upgrade log shows "3 whetstone(s) and 4 repair kit(s) got a subcategory" and "foraging got 5 rank(s) (copied from 'herbalism')".
- 022 cannot fail on prod data. The blueprint guard passes (0 rows) and the enum shrink is safe after it. The essence FK is found by column through the inspector. The backfill touches only `resource` rows. Legacy items stay `NULL` («Прочее»). The scholar rename is by slug and guarded against a name clash. Descriptions are swapped only where they equal the 004 seed text. The belt report is read-only. The steps are idempotent, so a partial failure can be re-run. On dev, all 6 descriptions were refreshed and scholar → «Мистик».
- Note: the scholar description is overwritten unconditionally (by design, §3.2).
- CI: `timeout-minutes` 3 → 6 is justified. The inventory suite took 2m45s of test time here, so the old 3-minute limit was at risk.

#### Code standards / security
- Pydantic v1, sync inventory / async locations, no `React.FC`, no new SCSS/CSS or `.jsx`, no `any`. New components use Tailwind and design-system classes.
- Auth/ownership/locks as in §3.4. `refine` validates before writing and locks the stacks `with_for_update`. The conversions PUT validates before deleting: a rejected PUT keeps the stored set (verified live). The ORM is used and the migration SQL is static. 500s return generic Russian text. User-facing strings are in Russian. Every new API call shows its errors.
- All changed frontend components are live and were rendered in the run below: CraftTab (`RefiningSection`/`RefineModal`, jeweler/enchanter sections), CharacterTab → `ItemContextMenu` → `SharpeningModal`/`GemSocketModal`, `/admin/items` → `ItemForm` → `ItemConversionsEditor`, `/location/:id` gathering section, the profile tab «Сбор».

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (0 errors)
- [x] `npm run build` (frontend container, output to /tmp) — PASS
- [x] `py_compile` (changed inventory/locations modules, migrations, tests) — PASS
- [x] `pytest` inventory-service (python:3.10, whole repo mounted, `--asyncio-mode=auto`, `CI=true`) — PASS, 941 passed (165s)
- [x] `pytest` locations-service (same) — PASS, 1195 passed
- [x] `docker compose config` — PASS
- [ ] Live verification (API script + headless Chromium/Playwright on the compose network) — PASS except issue #1 (360px)

#### Live Verification Results
- Admin: created test ore, ingot, dust, reagent, essence, jewelry stone, ring, rune, cloak and ingredient. Ore conversions were saved (blacksmith 2→1, jeweler 1→1) and so was the reagent's (alchemist 2→1). The editor shows them after reload. A UI edit (blacksmith 3→1) persisted («Предмет сохранён»). A wrong result subcategory → 400 in Russian, and the old set was kept. A belt with sockets → 422. `blueprint` → 422. The subcategory filter works.
- Blacksmith: refining 7 ore → 3 batches, 6 consumed, 1 left over, 3 ingots, +15 XP. 1 ore → 400. Quantity 0 → 422. UI: the section and modal work (5 entered → 4 consumed, leftover note, result and XP toasts). The rail shows «Мистик».
- No profession: «Заточить» appears on both the inventory ring and the equipped ring, and the modal lists only the jewelry stone. API: weapon stone → 400 «Этот камень не подходит для этого предмета», stone not consumed. Jewelry stone → success, stone consumed. «Гнёзда» on the cloak → the rune was inserted. The filled slot shows «Извлекать рун может только зачарователь.» with no extract button. API extract → 400.
- Gathering: the 4th card «Собирательство» is shown. The ingredient node shows 10 min for 2 stamina (no ×2 penalty), and «Собрать» starts gathering directly (no tool modal, session without a tool, 600s). A tool → 422. `tool_required` is present in `/client/details`.
- Console: only Vite HMR websocket noise and the expected 404 of `/professions/{cid}/my` for a character without a profession. No 5xx.
- 360px: the refine and sharpen modals fit; the RefiningSection cards do not (#1).
- Cleanup: the test items, conversions, node, session, auto-post, gate and foraging progress were removed. Character 706 (profession enchanter r1/0, location, inventory, attributes) was restored. The stack was left running as found; the throwaway containers were removed.

### Review #2 — 2026-09-18
**Result:** PASS

Fixes from review #1:
| # | Status | Notes |
|---|--------|-------|
| 1 | FIXED | `RefiningSection.tsx`: the card uses `flex-wrap`, the text uses `flex-1 min-w-[10rem] break-words`, and the button is `w-full sm:w-auto`. Live at 360px with a 72-character ore name and a 60-character result name: no horizontal scroll (`scrollWidth` = 360), text column 164px, names wrap by words, and the button (224px) sits on its own row under the text. At 1440px the two cards sit side by side, the button stays inline (127px) and long names wrap over two lines. |
| 2 | FIXED | `SharpeningModal.tsx:215` → «Новые характеристики (1 очко)». |
| 3 | FIXED | `itemFormRules.ts`: no `essence_result_item_id` reference left. |
| 4 | FIXED | Task #10 is DONE. |
| 5 | FIXED | `RefineModal.tsx` → «Базовый опыт профессии: +N (без учёта баффов)». |

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (exit 0, no output)
- [x] `npm run build` — PASS
- [x] Backend unchanged since review #1 (py_compile / pytest results from #1 stand)
- [x] Live verification — PASS

#### Live Verification Results
- Test setup: character 706 temporarily became a blacksmith and got two ores (a long name and a short one), each with a blacksmith 2→1 conversion to an ingot with a long name, 7 of each in the inventory.
- Page `/profile` → «Крафт», viewports 360px and 1440px (headless Chromium on the compose network): the layout is correct, with zero console errors besides Vite HMR noise and no 4xx/5xx.
- Cleanup: the 3 test items and their conversions and inventory rows were deleted, and the character's profession was restored (enchanter, rank 1, 0 XP, original `chosen_at`). The throwaway browser container was removed.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-17 23:45 — PM: фича создана (этап 2 из 3 ребаланса профессий), запускаю анализ
[LOG] 2026-09-17 23:50 — Analyst: начал анализ: inventory-service (профессии, рецепты, заточка, гнёзда, эссенции, трансмутация, переплавка, сбор), locations-service (узлы сбора), фронтенд (вкладка крафта, админка предметов/рецептов, сбор)
[LOG] 2026-09-17 23:59 — Analyst: анализ завершён: затронуты inventory-service, locations-service и фронтенд; «+15» уже есть (бюджет 15 очков), у точильных камней нет привязки к частям снаряжения, подкатегорий ресурсов в БД нет; вся вкладка крафта живая; обнаружен бесплатный эндпоинт изучения рецептов; есть 7 вопросов к пользователю (переплавка ювелира, инструмент для ингредиентов, опыт за заточку, старые камни и предметы)
[LOG] 2026-09-18 00:30 — PM: пользователь ответил на вопросы аналитика (раздел 1 обновлён), запускаю архитектора
[LOG] 2026-09-18 00:35 — Architect: начал проектирование; учтены решения пользователя: у сбора ингредиентов своя прокачка как у остальных видов сбора, камень ювелира называется «Гравировальный резец»
[LOG] 2026-09-18 01:20 — Architect: спроектировано 11 задач (3 бэкенд, 4 фронтенд, 2 QA, документация, ревью) и 9 API-контрактов (переработка, настройки переработки в админке, правила переработки, изменения заточки, крафта, гнёзд и сбора); миграции inventory 022 и locations 043 с откатом
[LOG] 2026-09-18 01:20 — Architect: найден пробел: базовые рецепты по рангу не выдаются уже прокачанным игрокам, если админ создал рецепт позже; заложена ленивая досинхронизация
[LOG] 2026-09-18 01:20 — Architect: по правилу «опыт только за создание» убран опыт и за вставку/извлечение камней и рун (не только за заточку); точить можно через контекстное меню предмета
[LOG] 2026-09-18 02:00 — Backend Dev: начал задачу #3 (locations-service, сбор ингредиентов)
[LOG] 2026-09-18 02:40 — Backend Dev: задача #3 завершена, изменено 4 файла + миграция 043 (revision id сокращён до `043_gathering_ingredient` — полное имя длиннее 32 символов); категория `ingredient` → навык `foraging`, без инструмента и без штрафа, шанс удвоения по рангу работает; инструмент для такого узла → 422; `tool_required` в данных узла; миграция проверена на dev MySQL (upgrade → отказ отката при наличии узла ингредиентов → downgrade → upgrade); pytest 1151 passed
[LOG] 2026-09-18 03:10 — Frontend Dev: задачи #4–#7 выполнены: общие константы профессий (подписи групп камней в одном месте), типы/API/Redux под переработку, удалены чертежи, эссенции, трансмутация и переплавка
[LOG] 2026-09-18 03:10 — Frontend Dev: во вкладке крафта новая секция «Переработка» с окном выбора количества; «Заточить» и «Гнёзда» доступны всем в контекстном меню предмета (инвентарь и экипировка), извлечение — только ювелиру/зачарователю (по полю can_extract из socket-info)
[LOG] 2026-09-18 03:10 — Frontend Dev: админка предметов — подкатегория ресурса, группа камня заточки, редактор настроек переработки, фильтр по подкатегории; подсказка про базовые рецепты; сбор ингредиентов без выбора инструмента и 4-я карточка навыка
[LOG] 2026-09-18 03:10 — Frontend Dev: tsc --noEmit и vite build проходят (в одноразовом контейнере); живая проверка не проводилась — бэкенд #1/#2 ещё в работе, стек не поднят; package-lock.json откатан
[LOG] 2026-09-18 03:40 — Frontend Dev: секции ювелира и зачарователя во вкладке крафта переделаны под извлечение («Извлечение огранок» / «Извлечение рун»): показываются только предметы со вставленными огранками/рунами (включая старые пояса с рунами), добавлена подсказка, что вставка доступна всем через «Гнёзда»; tsc и build проходят, package-lock.json откатан
[LOG] 2026-09-18 02:00 — Backend Dev: начал задачи #1 и #2 (inventory-service)
[LOG] 2026-09-18 03:50 — Backend Dev: задача #1 завершена: миграция 022_profession_rework (чертежи, эссенции, подкатегории ресурсов, группы камней, таблица item_conversions, навык «Собирательство» с 5 рангами, «Книжник» → «Мистик»), модели и схемы; миграция проверена на dev MySQL: upgrade → downgrade -1 → upgrade, плюс отказ при наличии предмета-чертежа
[LOG] 2026-09-18 03:50 — Backend Dev: задача #2 завершена, изменено 4 файла кода (main.py, crud.py, schemas.py, models.py): переработка и её настройка в админке, заточка любым игроком подходящим камнем, опыт профессии только за крафт и переработку через один помощник, досинхронизация базовых рецептов, бесплатное изучение рецептов закрыто, эссенции/трансмутация/переплавка удалены
[LOG] 2026-09-18 03:50 — Backend Dev: по решению пользователя вставка огранок и рун открыта всем, извлечение — только ювелиру и зачарователю; socket-info отдаёт insertable_type / can_insert / can_extract / extract_preservation_chance (контракт записан в 3.3.8)
[LOG] 2026-09-18 03:50 — Backend Dev: старые тесты обновлены под новые правила (test_essence_extraction.py удалён), pytest inventory-service: 684 passed; живая проверка через gateway: refining-rules, фильтр по подкатегории, настройки переработки, learn-recipe → 404
[LOG] 2026-09-18 03:50 — Backend Dev: обнаружено 2 проблемы вне фичи, добавлены в ISSUES.md (update_recipe не сбрасывает auto_learn_rank в null; мёртвая константа DURABILITY_SLOT_TYPES)
[LOG] 2026-09-18 04:30 — Backend Dev: исправлен баг из QA — настройки переработки не принимали реагенты как сырьё алхимика; теперь допустимое сырьё берётся из правил профессий (руда, реагенты, ингредиенты, трофеи); формат refining-rules не менялся, фронтенду нужно показывать редактор и для реагентов (см. 3.3.2); pytest 941 passed
[LOG] 2026-09-18 04:30 — QA: начал задачи #8 и #9 (тесты inventory-service и locations-service)
[LOG] 2026-09-18 05:40 — QA: inventory-service — новые файлы test_refining.py, test_item_conversions_admin.py, test_auto_learn_recipes.py, test_sharpening_groups.py, test_resource_subcategory_rules.py, test_migration_022_enums.py (+ общие фабрики feat165_helpers.py); дополнены test_gem_sockets.py (руны, пояса, флаги socket-info; удалены неиспользуемые фикстуры лома и слитков) и test_gathering.py (навык «Собирательство», контракт с locations); conftest запоминает настоящие ENUM до подмены на String
[LOG] 2026-09-18 05:40 — QA: locations-service — новый файл test_gathering_ingredient.py: миграция 043 и ENUM модели, сбор без инструмента (без штрафа ×2, шанс удвоения по рангу), 422 при инструменте, finalize отправляет foraging, tool_required в данных узла
[LOG] 2026-09-18 05:40 — QA: проверка «тесты ловят поломку»: на копиях кода внутри контейнера сломано 8 мест в inventory (поиск настройки переработки, фильтр стаков, фильтр refine-info, проверка результата, группа камня, фильтр камней в sharpen-info, ENUM, подкатегория результата) и 6 в locations — каждый раз тесты падают; рабочий код не менялся
[LOG] 2026-09-18 05:40 — QA: прогон в Docker (python 3.10, --asyncio-mode=auto, также с CI=true): locations-service 1195 passed; inventory-service 940 passed, 1 failed — найден баг фичи: админка не даёт настроить переработку алхимика (реагенты → эссенции), см. отчёт
[LOG] 2026-09-18 05:40 — QA: баг: crud.replace_item_conversions принимает источником только RAW_SUBCATEGORIES, а источник алхимика «reagent» — продукт переработки → 400 «Перерабатывать можно только сырьё»; фронтенд (itemFormRules.isRawSubcategory → ItemForm) тоже не показывает редактор для реагентов; падающий тест test_item_conversions_admin.py::TestReplaceSet::test_alchemist_can_configure_reagent_to_essence; сама переработка алхимика работает (тест в test_refining.py)
[LOG] 2026-09-18 05:40 — QA: риск: полный прогон inventory-service в Docker на Windows занимает ~2 мин 40 с при лимите шага CI 3 минуты (до фичи ~2 мин 33 с)
[LOG] 2026-09-18 04:00 — Frontend Dev: баг исправлен — редактор настроек переработки в админке предметов показывался только для сырья, поэтому у реагентов (алхимик: реагенты → эссенции) его не было; теперь он показывается для любой подкатегории, которая указана исходной хотя бы в одном правиле переработки (список берётся из API), внутри — только профессии с подходящим правилом; tsc и build проходят, package-lock.json откатан
[LOG] 2026-09-18 06:00 — Reviewer: начал проверку
[LOG] 2026-09-18 06:30 — Reviewer: автопроверки пройдены: tsc и build без ошибок, py_compile ок, pytest inventory 941 passed (2 мин 45 с), locations 1195 passed; миграции 022 и 043 откатываются и накатываются заново, на данных как на проде 022 упасть не может
[LOG] 2026-09-18 07:40 — Reviewer: живая проверка: переработка, заточка без профессии (подходящий и неподходящий камень), вставка руны без профессии и запрет извлечения, «Собирательство» и сбор ингредиентов без инструмента, «Мистик», настройки переработки в админке — всё работает; тестовые данные удалены, персонаж восстановлен
[LOG] 2026-09-18 07:45 — Reviewer: обнаружен баг вне фичи (выдача предметов без авторизации через POST /inventory/{id}/items), добавлен в ISSUES.md
[LOG] 2026-09-18 07:50 — Reviewer: проверка завершена, результат FAIL — на экране 360px карточки в секции «Переработка» сжимаются (названия ломаются по буквам); мелочи: старая подпись «2 поинта» в окне заточки, остаток essence_result_item_id в форме предмета, статус задачи #10
[LOG] 2026-09-18 04:40 — Frontend Dev: исправлены замечания ревью: карточки «Переработки» на узком экране переносят кнопку на отдельную строку (текст больше не сжимается), подпись «Новые характеристики (1 очко)» в заточке, убран остаток essence_result_item_id, в окне переработки опыт подписан как базовый (без учёта баффов); tsc и build проходят, package-lock.json откатан; визуально на 360px не проверено — в dev-БД нет настроек переработки
[LOG] 2026-09-18 08:30 — Reviewer: начал повторную проверку (ревью #2)
[LOG] 2026-09-18 08:50 — Reviewer: tsc и build проходят; на 360px и 1440px карточки «Переработка» с длинными названиями не вылезают за экран, кнопка на узком экране переносится под текст; подпись в окне заточки, остаток в форме предмета и подсказка про опыт исправлены; тестовые данные удалены
[LOG] 2026-09-18 08:50 — Reviewer: проверка завершена, результат PASS
[LOG] 2026-09-18 04:00 — PM: ревью #2 PASS, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Переработка сырья: кузнец (руда → слитки), алхимик (реагенты → эссенции), повар (ингредиенты → реагенты), ювелир (руда → магическая пыль), Мистик (трофеи → материалы). Что и в каком количестве получается — настраивается в админке у каждого сырья для каждой профессии. Всегда успешно, шанс удвоения на каждую порцию 5/10/20% по рангу, опыт 5/12/25/50 по редкости.
- Опыт профессии — только за крафт и переработку (за заточку, вставку и извлечение — нет). Все начисления опыта через одну функцию.
- Базовые рецепты за ранг выдаются автоматически, в том числе тем, кто уже на этом ранге. Бесплатное скрытое изучение рецептов закрыто.
- Заточка доступна всем через меню предмета «Заточить»; камни трёх групп: «Точильный камень» (оружие, броня, шлем), «Камень чар» (плащ, пояс), «Гравировальный резец» (украшения — теперь тоже точатся). Три существующих камня отнесены к кузнецу.
- Вставка рун (оружие, броня, шлем, плащ) и огранок (украшения) — всем через «Гнёзда»; извлечение — только ювелир и зачарователь. Пояс без гнёзд, старые руны из поясов можно достать. Во вкладке крафта у ювелира и зачарователя — разделы извлечения.
- Подкатегории ресурсов в админке и фильтр по ним.
- Сбор ингредиентов: новый навык «Собирательство» с рангами и бонусами, без инструмента и без штрафа.
- Удалено: чертежи, извлечение эссенций из кристаллов, трансмутация, переплавка украшений. «Книжник» → «Мистик».
- Миграции: inventory 022, locations 043 (с откатом, проверены). Тесты: inventory 941, locations 1195 — зелёные. Лимит времени тестов в CI поднят с 3 до 6 минут.

### Что изменилось от первоначального плана
- Вставка рун/огранок открыта для всех (решение пользователя по ходу).
- Исправлен баг настройки переработки реагентов у алхимика (найден тестами).
- Карточки переработки поправлены под 360px (найдено на ревью).

### Оставшиеся риски / follow-up задачи
- HIGH в ISSUES.md: `POST /inventory/{character_id}/items` без авторизации (выдача любого предмета любому персонажу); плюс ранее найденные открытые служебные /attributes/* — закрыть до пуша на прод.
- MEDIUM: в админке нельзя снять у рецепта «выдаётся за ранг».
- Старые предметы (кристаллы, трансмутированные ресурсы, лом, эссенции стихий) остались — админ удаляет вручную.
- Этап 3 (боевые эффекты зелий/свитков) — после редизайна вкладок профиля (FEAT-166).
