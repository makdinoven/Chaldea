# FEAT-171: Публичный профиль персонажа и закрытие приватных данных

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-19 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-171-slug.md` → `DONE-FEAT-171-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Закрытие последнего пункта из серии по безопасности (после DONE-FEAT-167/169/170). Сейчас через gateway **анонимно** отдаются чужие инвентарь, экипировка, характеристики, профиль и история чата. Это не порча данных, а утечка и разведка перед боем, но решать нужно продуктово: часть страниц должна остаться публичной.

Пользователь сформулировал правила (ниже). Смысл: **персонаж — витрина, его цифры — личное дело игрока.**

### Бизнес-правила

**Публично (видят все, включая гостей без входа):**
- Профиль персонажа: имя, раса/подраса, класс/подкласс, описание/анкета, аватар, титулы, история постов.
- **Уровень персонажа** — виден всем (он и так выводится в анкетах).
- **Надетая экипировка** — видно, что на персонаже надето. Предмет можно открыть и прочитать **название и описание**, но **характеристики предмета скрыты** (урон, бонусы, заточка, вставленные руны/огранки, прочность и т.п.).
- Переходы на профиль чужого персонажа должны работать **из всех мест**, откуда игрок туда попадает: топ/рейтинг, локация (клик по имени персонажа), профиль игрока со списком его персонажей, история постов, чат и т.п. Список точек входа собрать по коду — ничего не должно сломаться.

**Скрыто от чужих (видит только владелец персонажа и админ/модератор с правом):**
- Характеристики персонажа (сила, ловкость и т.д., производные, урон).
- Инвентарь.
- **Быстрые слоты (пояс)** — уже закрыты в FEAT-169, не регрессировать.
- Опыт: сколько до следующего уровня и общий опыт.
- Деньги (золото, алмазы).
- Дерево перков.
- Навыки и их прокачка.

**История чата** (`GET /notifications/chat/messages` и соседние чтения): закрыть от неавторизованных.

**Общее:**
- Ничего не должно сломаться для владельца и для админки: админ видит всё как раньше.
- Гостевые страницы (без входа) должны продолжать работать в объёме «публично» выше.
- Разделять надо **на уровне ответа API**, а не пряча данные в интерфейсе: сейчас фронтенд может получать полный объект и просто не рисовать его — это не защита.
- Ошибки по-русски; чужие приватные данные → 403, несуществующий персонаж → 404 (не раскрывать существование).

### UX / Пользовательский сценарий
1. Гость открывает профиль персонажа из топа — видит анкету, уровень, титулы, посты и надетую экипировку; может открыть меч и прочитать описание, но не видит его урон.
2. Игрок заходит на профиль чужого персонажа — то же самое, плюс ничего лишнего: ни характеристик, ни инвентаря, ни навыков, ни перков, ни денег.
3. Владелец открывает свой профиль — видит всё, как сейчас.
4. Админ открывает чужой профиль в админке — видит всё.

### Edge Cases
- Персонаж NPC/моб (нет владельца) — что публично? Скорее всего как у обычного персонажа.
- Персонаж в бою: противник не должен через профиль подсмотреть характеристики.
- Список персонажей в локации, топы, профиль игрока — там выводятся сводные данные, проверить, что в них не утекает приватное (например уровень можно, деньги нельзя).
- Старые клиенты/кеш: если ответ стал беднее, интерфейс не должен падать на отсутствующих полях.

### Вопросы к пользователю (если есть)
- [x] Профиль публичный → да
- [x] Характеристики и инвентарь → только владелец и админ
- [x] Экипировка → видна всем; название и описание предмета читаются, характеристики предмета скрыты
- [x] Быстрые слоты → скрыты
- [x] Уровень → публичный
- [x] Опыт (до уровня и общий), деньги, перки, навыки → скрыты от чужих
- [x] История чата → закрыть от неавторизованных
- [x] NPC/мобы → остаются ПУБЛИЧНЫМИ (бестиарий, модалка NPC). `user_id IS NULL` означает «у персонажа нет приватного слоя», а не «никому нельзя»

### Решения PM по вопросам Аналитика (§2.12) — авторитетные

- **Q1 — объём.** Только бэкенд-гейты + минимум фронтенда, чтобы текущий интерфейс не сломался.
  **Новая страница «чужой профиль персонажа» и разводка ссылок из топа/локации/профиля игрока —
  ВНЕ объёма**, это отдельная фича сразу следом. В FEAT-171 страницу не проектируем; следим только
  за тем, чтобы ничего работающее не сломалось.
- **Q2 — публичная карточка предмета:** название, описание, картинка, редкость. Без цены,
  характеристик, эффектов, заточки, вставок и прочности.
- **Q3 — `starting_attributes` становится ПРИВАТНЫМ** (владелец + админ). `granted_kit` — решение
  Архитектора (см. D4: остаётся публичным).
- **Q4 — (a)** `GET /characters/{id}/logs` → только владелец и админ. **(b)** `xp_earned` убрать из
  публичной истории постов.
- **Q5 — RBAC:** переиспользуем существующее разрешение `characters:read` + проверку роли.
  Новых разрешений, миграций и RBAC-сид-тестов НЕ добавляем.
- **Q6 — NPC/мобы публичны** (см. чекбокс выше).
- **Q7 — баг навигации** `UserProfilePage/CharactersSection.tsx:57` чиним в этой фиче, но минимально
  (страницы-то ещё нет) — см. задачу F1.
- **Дополнительно в объёме (живые дыры):** `GET /inventory/{id}/equipment` отдаёт пояс
  (`fast_slot_*` лежат в той же таблице) в обход гейта FEAT-169 — анонимно и с полными данными
  предметов; золото утекает анонимно через `full_profile`, `short_info` и
  `CharacterShort.currency_balance` на профиле игрока.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.0 Headline findings (read this first)

1. **There is no "someone else's character profile" page in the frontend today.**
   `ProfilePage` (`services/frontend/app-chaldea/src/components/ProfilePage/ProfilePage.tsx:29,34`) always
   takes `characterId` from `state.user.character.id`. The route is `profile` with **no** `:characterId`
   param (`components/App/App.tsx:339`). Every "look at another character" flow today is either a
   **passport modal** on `GET /characters/{id}/public`, or a jump to the **owner's user page**
   `/user-profile/:userId`. So §1's "переходы на профиль чужого персонажа должны работать из всех мест"
   is **not a regression-avoidance task, it is a new page**. See §2.6 and Q1.
2. **The leak is real and wider than §1 lists.** Anonymously, through the gateway, anyone can read
   another character's full inventory, full equipment **including the belt/fast slots** (which FEAT-169
   supposedly closed — see §2.4.1), every derived combat stat, resistances/vulnerabilities, perks,
   skills+levels+perk picks, gold (three separate routes), XP, and the whole chat history.
3. **Every frontend request already carries the JWT when the player is logged in**
   (`src/api/axiosSetup.ts:53-61`, request interceptor on the default axios instance). So an
   *optional-auth* endpoint will recognise the owner with **zero frontend changes**. This is the single
   biggest de-risker for this feature.
4. **The building blocks exist, but not in the services that need them.** `get_optional_user` exists in
   locations-service, user-service and notification-service; `verify_character_ownership` exists in six
   services but has **no admin bypass**; there is no shared "may this viewer see private data of
   character X" helper anywhere. See §2.5.
5. **Thirteen internal callers read the to-be-gated routes with no credentials at all** and will break
   the moment a gate lands. See §2.7 — this is the FEAT-169 "two passes" lesson again.

---

### 2.1 Affected services

| Service | Type of change | Files |
|---------|---------------|-------|
| inventory-service | split public/private views on 4 reads, new internal twins, optional-auth helper | `app/main.py`, `app/schemas.py`, `app/crud.py`, `app/auth_http.py` |
| character-attributes-service | gate 3 reads, optional-auth helper | `app/main.py`, `app/auth_http.py` |
| character-service | thin out 3 public reads (drop money/XP), decide on `/logs` | `app/main.py`, `app/schemas.py` |
| skills-service | gate 1 read (accept service token — caller already sends it) | `app/main.py` |
| user-service | drop `currency_balance` from the anonymous user profile | `main.py`, `schemas.py` |
| notification-service | require JWT on chat history | `app/chat_routes.py` |
| battle-service | move 4 anonymous cross-service reads onto internal/token paths | `app/battle_engine.py`, `app/inventory_client.py` |
| dungeon-service | move 2 anonymous cross-service reads onto internal paths | `app/http_clients.py` |
| locations-service / character-service (as callers) | send the token on A1/C1/C4 reads | `app/main.py`, `app/crud.py` |
| frontend | **new public character profile page** + wire up entry points | `components/App/App.tsx`, new page, `UserProfilePage/CharactersSection.tsx`, `LocationPage/PlayersSection.tsx`, `HomePage/Stats/*`, `Chat/ChatMessage.tsx` |

**No DB changes. No Alembic migration.** Nothing here is stored; it is purely response-shaping plus auth
dependencies. (If a *new* RBAC permission is chosen instead of reusing `characters:read` — see Q5 — that
**would** need a user-service migration plus an explicit seed row in
`test_rbac_permissions.py::TestAdminAutoPermissions`, per CLAUDE.md §10.13.)

---

### 2.2 Inventory of every read that exposes character data

Auth legend: **none** = anonymous through the gateway; **JWT** = `get_current_user_via_http`;
**own** = JWT + `verify_character_ownership`; **RBAC** = `require_permission(...)`;
**INT** = `verify_internal_token` (nginx also `return 403`s `/*/internal/*`).

#### character-service (`services/character-service/app/main.py`)

| # | Endpoint | Line | Auth | What it returns | Consumers |
|---|----------|------|------|-----------------|-----------|
| C1 | `GET /characters/{id}/full_profile` | 1911 | **none** | `name`, **`currency_balance`**, `level`, **`stat_points`**, `level_progress{current_exp_in_level, exp_to_next_level, progress_fraction}`, `attributes{health,mana,energy,stamina cur/max}`, `active_title(+rarity)`, `avatar` | FE `redux/slices/profileSlice.ts:380`; char-attrs `perk_evaluator.py:63,81` and `main.py:562` (**anonymous internal use**) |
| C2 | `GET /characters/{id}/profile` | 2156 | **none** | `character_photo`, `character_title(+rarity)`, `character_level`, `user_id`, `user_nickname`, `character_name`, `current_location_id`, `travel_cooldown_until` | no FE call site found |
| C3 | `GET /characters/{id}/public` | 2338 | **none** | passport: name, avatar, level, race/subrace/class names+image, sex/age/weight/height, appearance/biography/personality/background, origin, registered_at, skitaltsy_since_*, **`starting_attributes` snapshot**, **`granted_kit` snapshot**, user_id+username | FE `api/charactersPublic.ts:148` ← `CharactersListPage.tsx:195` |
| C4 | `GET /characters/{id}/short_info` | 2211 | **none** | id, name, avatar, level, location, race/class/subrace ids+names, is_npc, npc_role, biography, personality, sex, age, travel_cooldown_until, **`currency_balance`** | FE `LocationPage/NpcProfileModal.tsx:55`; user-service `main.py:116` (feeds `/users/me`, `/users/{id}/profile`, `/users/{id}/characters`); locations-service `crud.py:6854` |
| C5 | `GET /characters/{id}/race_info` | 2054 | **none** | id, id_class, id_race, … | FE `profileSlice.ts:396` |
| C6 | `GET /characters/{id}/titles` | 1837 | **none** | unlocked titles | FE `api/titles.ts:114` ← `TitlesTab.tsx:45` |
| C7 | `GET /characters/{id}/post-history` | 3841 | **none** | per post: id, location_id+name, content, `char_count`, **`xp_earned`**, created_at | FE `api/characterLogs.ts:57` ← `PostHistoryTab.tsx:122`, standalone route `post-history/:characterId` |
| C8 | `GET /characters/{id}/logs` | 3813 | **none** | character event log: `event_type`, `description`, free-form `metadata`, `created_at` | FE `api/characterLogs.ts:47` ← `LogsTab.tsx:99` |
| C9 | `GET /characters/by_location` | 2078 | **none** | `PlayerInLocation` (`schemas.py:389`): id, name, avatar, level, class_name, race_name, title(+rarity), user_id — **clean** | FE `api/squads.ts:153` ← `PartyTab.tsx:92`, LocationPage |
| C10 | `GET /characters/list` | 2244 | **none** | public roster: name, avatar, level, race/class, anketa text, age/sex/height/weight, origin, registered_at, user_id+username — **clean** | FE `api/charactersPublic.ts:160` ← `CharactersListPage` |
| C11 | `GET /characters/home-leaderboards` | 3296 | **none** | `LeaderboardEntry{character_id, name, avatar, value}` ×3 boards — **clean** | FE `api/homeStats.ts:22` ← `HomePage/Stats/Stats.tsx:38` |

#### character-attributes-service (`services/character-attributes-service/app/main.py`)

| # | Endpoint | Line | Auth | Returns | Consumers |
|---|----------|------|------|---------|-----------|
| A1 | `GET /attributes/{id}` | 357 | **none** | `CharacterAttributesResponse` (`schemas.py:41`): cur/max health+mana+energy+stamina, **`passive_experience`**, **`active_experience`**, dodge, crit chance, crit damage, damage, **13 `res_*` + 13 `vul_*`**. NB base stats (`strength`, `agility`, …) are in the model but **not** in this response schema — they surface only on the admin routes and in the POST-upgrade reply | FE `profileSlice.ts:437`; battle-service `battle_engine.py:29` (**anonymous**); character-service `main.py:1973`; locations-service `main.py:1302,1596,2666` + `crud.py:7350`; skills-service `main.py:799` |
| A2 | `GET /attributes/{id}/perks` | 332 | **none** | full perk tree + unlock status + progress. **Writes to the DB on GET** (`reconcile_perks`, `main.py:339-345`) — separate open ISSUES entry | FE `PerksTab.tsx:39` |
| A3 | `GET /attributes/{id}/cumulative_stats` | 1340 | **none** | pve_kills, pve/pvp points, wins/losses, damage totals, **`total_gold_earned` / `total_gold_spent`**, items bought/sold, posts, quests | no FE call site found |
| A4 | `GET /attributes/{id}/passive_experience` | 107 | **none** | total passive XP | character-service `main.py:1923` |
| A5 | `GET /attributes/{id}/rest-status` | 388 | **none** | regen eligibility + satiety buff detail | FE `profileSlice.ts:718`, `RestStatusPanel.tsx:65,79` |

#### inventory-service (`services/inventory-service/app/main.py`)

| # | Endpoint | Line | Auth | Returns | Consumers |
|---|----------|------|------|---------|-----------|
| I1 | `GET /inventory/{id}/items` | 361 | **none** | `List[CharacterInventory]` (`schemas.py:949`): row id + **full `Item` template** + `is_identified`, `enhancement_points_spent`, `enhancement_bonuses`, `socketed_gems`, `current_durability` | FE `profileSlice.ts:453`, `NpcAuctionModal.tsx:155`, `TradeItemSelector.tsx:59`; dungeon-service `http_clients.py:287` (**anonymous**) |
| I2 | `GET /inventory/{id}/equipment` | 773 | **none** | `List[EquipmentSlot]` (`schemas.py:1000` over `:976`): every slot **including `fast_slot_1..4`**, with `item_id`, `enhancement_points_spent`, `enhancement_bonuses`, `socketed_gems`, `current_durability`, **`effective_damage`** and the **full `Item` template** | FE `profileSlice.ts:469`; battle-service `battle_engine.py:45` **and** `inventory_client.py:58` (**anonymous**) |
| I3 | `GET /inventory/items/{item_id}` | 273 | **none** | full `Item` template (catalogue, not character-scoped) | battle-service `inventory_client.py:23`; dungeon-service `http_clients.py:306`. **No FE call site** |
| I4 | `GET /inventory/items/bulk?ids=` | 244 | **none** | `ItemBulkResponse` list | FE `api/bulk.ts:77` ← `CharactersListPage.tsx:205`, `StarterKitPreview` |
| I5 | `GET /inventory/{id}/equipment-rules` | 747 | **none** | what this class/subclass may wear — harmless | FE `profileSlice.ts:501` |
| I6 | `GET /inventory/characters/{id}/fast_slots` | 1346 | **own** | belt contents — **already closed (FEAT-169)**, but see §2.4.1 | FE `profileSlice.ts:485` |
| I7 | `GET /inventory/internal/characters/{id}/fast_slots` | 1328 | **INT** | same | battle-service |
| I8 | `GET /inventory/{id}/item-detail/{row_id}` | 3680 | **own** | `ItemDetailResponse` (`schemas.py:1775`): full `Item` + `current/max_durability`, `enhancement_points_spent`, `enhancement_bonuses`, `socketed_gems`, `socketed_items` | FE `profileSlice.ts:765` |
| I9 | `GET /inventory/{id}/active-buffs` | 3544 | **own** | active buffs | FE `profileSlice.ts:676` |

`Item` (`schemas.py:826` over `ItemBase:521`) is **fat**: name, description, image/full_image, type,
rarity, `item_level`, **`price`**, stack/unique flags, `socket_count`, `whetstone_level`,
`identify_level`, `max_durability`, `repair_power`, `primary_damage_type`, weapon/armor subclass,
~60 `*_modifier` fields (stats, 13 resistances, 13 vulnerabilities, crit, dodge, damage), recovery
values, buff fields, gathering-tool bonuses, `effects[]`, `damage_entries[]`, `xp_buffs[]`.

#### skills-service (`services/skills-service/app/main.py`)

| # | Endpoint | Line | Auth | Returns | Consumers |
|---|----------|------|------|---------|-----------|
| S1 | `GET /skills/characters/{id}/skills` | 373 | **none** | `CharacterSkillRead` (`schemas.py:214`): skill_id, **level**, **free_perk_points**, **selected_perk_ids**, `reset_available_at`, skill summary | FE `SkillsTab.tsx:97`, `SkillUpgradeModal.tsx:68`, admin `adminCharacters.ts:217`; battle-service `skills_client.py:80,104` — **already sends the service token in the Bearer position** |
| S2 | `GET /skills/class_trees/{tree}/progress/{char}` | 825 | **own** | chosen nodes + purchased skills — already closed | FE `SkillTreePage.tsx:154,185` |
| S3 | `/skills/class_trees/by_class/{id}` 810, `/skills/{id}` 469, `/bulk` 438, `/subclasses` 386 | | **none** | catalogue, not character-scoped — fine | FE |

#### user-service (`services/user-service/main.py`)

| # | Endpoint | Line | Auth | Returns | Consumers |
|---|----------|------|------|---------|-----------|
| U1 | `GET /users/{id}/profile` | 1554 | **optional JWT** (`get_optional_user`) | user profile + `character: CharacterShort` (`schemas.py:66`) which carries **`currency_balance`**, built from C4 | FE `api/userProfile.ts:42` ← `UserProfilePage` |
| U2 | `GET /users/{id}/characters` | 1505 | **none** | `UserCharacterItem`: id, name, avatar, level, rp_posts_count, last_rp_post_date, race/class/subrace — **clean** | FE `api/userProfile.ts:88` ← `CharactersSection`, `CharacterSwitchDropdown.tsx:46` |
| U3 | `GET /users/{id}/wall/posts` | 1198 | **none** | wall posts | FE `api/userProfile.ts:5` |
| U4 | `GET /users/me` | 258 | **JWT** | own everything incl. `balance`, `diamonds`, `character: CharacterShort` | FE |
| U5 | `GET /users/{id}` | 2205 | **none** | `UserRead` | many services |

Diamonds live only on `users` and are exposed only through U4 (JWT) and `/users/internal/{id}/diamonds`
(INT) — **no diamond leak**. Gold (`characters.currency_balance`) leaks through C1, C4 and U1.

#### notification-service

| # | Endpoint | Line | Auth | Returns |
|---|----------|------|------|---------|
| N1 | `GET /notifications/chat/messages?channel=` | `app/chat_routes.py:177` | **none** | paginated history of any channel: user_id, username, avatar, frame, background, content, reply, created_at. (`DELETE` on the same router is `require_permission("chat:delete")`, `POST` is JWT.) |
| N2 | messenger / tickets / notifications reads | `messenger_routes.py`, `ticket_routes.py`, `main.py:168,188` | JWT | fine |

`chat_routes.py:83` already contains a private `_get_optional_user` — the optional-auth pattern is
already in this very file.

#### battle-service / party-service — legitimate cross-character reads, **do not touch**

- `GET /battles/{id}/state` — `app/main.py:1467`, JWT — full state of both teams; FE `BattlePage.tsx:452`.
- `GET /battles/{id}/spectate` — `app/main.py:1555`, JWT — `attributes` + hp/mana/stamina/energy for
  **every** combatant; FE `api/battles.ts:178` ← `BattlePage.tsx:448` (spectator mode).
- `GET /battles/{id}/preview` — `app/main.py:1652`, JWT — hp/max_hp/mana/max_mana per side for the HP
  bars; FE `api/battles.ts:169` ← `BattlesTab.tsx:196`.
- `GET /battles/by-location/{id}` (4757), `GET /battles/character/{id}/in-battle` (3570, **none**),
  `GET /battles/battles/{id}/logs[/{turn}]` (3543/3559, **none**) — FE `BattlePageBar.tsx:473`.
- party-service `GET /party/by-location` (`app/main.py:213`, **none**) — names/avatars/leader only, clean.

**The battle and party UI never fetches an opponent's equipment or inventory.** Cross-character combat
visibility is hp/mana/stamina/energy plus the snapshot `attributes` the battle engine itself produced.
§1's "противник не должен через профиль подсмотреть характеристики" is therefore fully satisfiable
without touching battle-service.

---

### 2.3 Field-level public/private matrix (proposed, per §1)

**PUBLIC — anyone, including guests**

| Field group | Where it lives today |
|---|---|
| id, name, avatar | C3, C4, C9, C10 |
| race / subrace (+image, distinctive features), class / subclass | C3, C4, C10 |
| sex, age, height, weight, appearance, biography, personality, background | C3, C10 |
| origin, `registered_at`, `skitaltsy_since_year/segment` | C3 |
| **level** | C1, C3, C4, C9, C10 |
| active title (+rarity), full title list | C1, C6 |
| `current_location_id` | C2, C3, C4 |
| owner `user_id` + `username` | C2, C3, C10 |
| post history: location, content, char_count, created_at | C7 |
| worn equipment: which slot holds which item, item **name + description + icon (+rarity)** | I2 — needs a new thin view |
| `starting_attributes` / `granted_kit` passport snapshots | C3 — **see Q3, these are numbers** |

**PRIVATE — owner + admin/moderator only**

| Field group | Where it lives today |
|---|---|
| everything in `CharacterAttributesResponse` (hp/mana/energy/stamina, dodge, crit, damage, 26 res/vul) | A1 |
| `stat_points` | C1 |
| `passive_experience`, `active_experience`, `exp_to_next_level`, `current_exp_in_level`, `progress_fraction` | C1, A1, A4 |
| `currency_balance` (gold) | C1, C4, U1 |
| diamonds | U4 — already JWT |
| inventory (every row) | I1 |
| belt / fast slots | I6 **and the I2 hole** |
| perk tree + progress | A2 |
| skills, levels, `free_perk_points`, `selected_perk_ids`, tree progress | S1, S2 |
| cumulative stats incl. gold earned/spent | A3 |
| rest / satiety status | A5 |
| item numbers on a worn item: every `*_modifier`, `price`, `effects[]`, `damage_entries[]`, `xp_buffs[]`, `effective_damage`, `enhancement_*`, `socketed_gems`, `current/max_durability`, `socket_count`, `whetstone_level` | I2, I3, I4, I8 |
| character event log (`/logs`) | C8 — **see Q4** |
| `xp_earned` per post | C7 — **see Q4** |

**Proposed "public item view"** (the §1 "открыть меч и прочитать описание"):
`{id, name, description, image, full_image, item_type, item_rarity}` — and *nothing else*.
`item_level` and `weapon_subclass` / `armor_subclass` sit on the fence between flavour and stat — Q2.

---

### 2.4 The equipment case in detail

`GET /inventory/{id}/equipment` (`main.py:773`) → `crud.get_equipment_slots_with_damage`
(`crud.py:440-465`) → per slot: `EQUIPMENT_SLOT_FIELDS` (`crud.py:433`) =
`id, character_id, slot_type, item_id, is_enabled, enhancement_points_spent, enhancement_bonuses,
socketed_gems, current_durability`, plus `item` (the full fat `Item`), plus `effective_damage`
(computed from the template damage + that weapon's sharpening + its gems, zeroed when broken).

So **today this endpoint returns, anonymously, the complete private set** — sharpening, sockets,
durability and the exact weapon damage the battle engine will use — for any character id. This is the
richest single leak in the feature.

A public slot should be `{slot_type, item: {id, name, description, image, full_image, item_type,
item_rarity}}`: no `effective_damage`, no `enhancement_*`, no `socketed_gems`, no `current_durability`,
no modifiers.

**Where the item card comes from.** The "open the sword and read it" flow needs a card, and today there
are three sources, none of which fits a public viewer:

- **I8 `GET /inventory/{id}/item-detail/{row_id}`** is the *owner's* card — JWT + `verify_character_ownership`
  (`main.py:3691`) — and it is deliberately full. It must **stay** owner-only. This is the strongest
  argument that public and private item cards are **two different documents**, not one gated one.
- **I3 `GET /inventory/items/{item_id}`** is the catalogue template: anonymous, fat, and — notably —
  **has no frontend caller at all**; its only callers are battle-service (`inventory_client.py:23`) and
  dungeon-service (`http_clients.py:306`). That makes it the cleanest candidate to put behind the
  internal token while adding a *separate* thin public route for the card.
- **I4 `GET /inventory/items/bulk`** *is* used by the frontend (`CharactersListPage` passport at
  `:205`, starter-kit preview) and is equally fat. Whatever thin shape is chosen must cover I4 too, or
  the public passport keeps leaking full templates through the granted-kit block.

Recommendation to the Architect: a **public/private split** (new thin route + keep the fat one for
owner/admin/internal), not a flat gate.

#### 2.4.1 Live regression: the belt leaks through the equipment route

`fast_slot_1..4` are rows in the **same `equipment_slots` table** with `slot_type` in
`{fast_slot_1..4}` (see `crud.is_item_compatible_with_slot`, `crud.py:482-486`), and
`crud.get_equipment_slots` (`crud.py:429-430`) filters **only** by `character_id`. FEAT-169 closed
`GET /inventory/characters/{id}/fast_slots` but left `GET /inventory/{id}/equipment` wide open — and
that route returns the belt rows with the full item payload, `coating_*`, `effects[]` and
`damage_entries[]` included.

**The FEAT-169 fast-slot gate is bypassable today with one anonymous request.** §1's "уже закрыты в
FEAT-169, не регрессировать" is already violated by a neighbouring route. Whatever shape the public
equipment view takes must exclude `fast_slot_*` outright, and the private one must be gated.

---

### 2.5 Auth plumbing — what exists, what must be built

**Exists:**

- `get_current_user_via_http(token)` — near-identical copy in 11 `auth_http.py` files (e.g.
  `character-service/app/auth_http.py:24`): calls user-service `GET /users/me`, returns
  `UserRead{id, username, role, permissions[]}`, 401 on failure, 503 if user-service is down.
- `get_admin_user` (`…/auth_http.py:46`) — `role in ("admin", "moderator")`, else 403.
- `require_permission("module:action")` (`…/auth_http.py:58`) — membership test on `user.permissions`.
- `verify_internal_token` (`…/auth_http.py:81`) — `X-Internal-Token` header, **fail-closed**: unset env
  → 503 for everyone.
- `allow_jwt_or_service_token` — **skills-service only** (`app/auth_http.py:61`): accepts a JWT *or* the
  internal secret in the *Bearer* position, returning `None` for the service caller. battle-service's
  `skills_client._service_headers()` (`app/skills_client.py:37-40`) already sends exactly that, so S1
  can adopt this dependency with **zero caller changes**. (Note the deliberate comment at
  `skills-service/app/auth_http.py:78-82`: this must not be merged with `verify_internal_token`.)
- `verify_character_ownership(db, character_id, user_id)` — character-service `main.py:61`,
  inventory-service `main.py:68`, character-attributes-service `main.py:64`, locations-service
  `main.py:160`, battle-service `main.py:152`. Raises 404 "Персонаж не найден" when the row is missing
  and 403 "Вы можете управлять только своими персонажами" when `user_id` differs.
  **No admin bypass. NPCs/mobs (`user_id IS NULL`) 403 for everybody.**
- **Optional auth exists in exactly three places:**
  - `locations-service/app/main.py:208` `get_optional_user` + `OAUTH2_SCHEME_OPTIONAL`
    (`main.py:29`, `auto_error=False`), consumed at `main.py:1115` (`/locations/{id}/client/details`);
  - `user-service/main.py:96` `get_optional_user` (local JWT decode, `optional_oauth2_scheme` at `:93`),
    consumed at `main.py:1557` (`/users/{id}/profile`);
  - `notification-service/app/chat_routes.py:83` `_get_optional_user`.

**Must be built — nothing like it exists today:**

1. `get_optional_user` in **character-service, character-attributes-service, inventory-service,
   skills-service** — copy the locations-service shape (`OAuth2PasswordBearer(tokenUrl="token",
   auto_error=False)`, return `None` on a missing/invalid token instead of 401). Best placed in each
   `app/auth_http.py` next to `get_current_user_via_http`.
2. A shared **`can_view_private(db, character_id, user) -> bool`** predicate:
   character must exist (else **404 "Персонаж не найден"** — §1 requires not revealing existence), then
   `user is not None and (user.id == owner_id or user.role in ("admin","moderator") or
   "<perm>" in user.permissions)`. `verify_character_ownership` cannot be reused as-is: it raises
   instead of returning a flag and has no admin path.
3. Admin path check: admin UI mostly uses **dedicated** routes already — `/characters/admin/*`,
   `/attributes/admin/{id}`, `/attributes/{id}/recalculate`
   (`api/adminCharacters.ts:107,117,133`; `components/Admin/CharactersPage/tabs/AttributesTab.tsx`;
   `components/AdminNpcsPage/NpcStatsEditor.tsx:148,320`; `components/Admin/MobsPage/MobStatsEditor.tsx:101,124,142`)
   — so §1's "админ видит всё как раньше" is mostly already satisfied by a separate surface; the
   predicate just must not *break* admins who land on a player route.

---

### 2.6 Frontend: entry points and the guest surface

**Router:** `components/App/App.tsx`. **Guard:**
`components/CommonComponents/ProtectedRoute/ProtectedRoute.tsx:21-66` — redirects to `/` when the Redux
`role` is falsy (i.e. for guests), plus optional `requiredRole` / `requiredPermission`.

**Guest-reachable, character-relevant routes:** `characters` (`:121`), `characters/list` (`:122` —
passport browsing), `world/*` (`:135-138`), `location/:locationId` (`:139`), `bestiary` (`:141`),
`archive/*` (`:142-143`), `post-history/:characterId` (`:319`), `players` / `players/online`
(`:337-338`), `user-profile[/:userId]` (`:340-341`), `chat/history` (`:336`),
`location/:locationId/battle/:battleId/spectate` (`:346-349`), and `profile` (`:339` — not
router-protected but self-gated: `ProfilePage.tsx:29,34` yields `null` for a guest and renders the
"Персонаж не найден" empty state at `:48-56`).
**Protected:** `/map`, `my-requests`, `requestsPage`, every `admin/*`, `admin/tickets*`.

**Entry points to "another character" as they exist today:**

| # | Place | file:line | What it actually does |
|---|---|---|---|
| E1 | Characters list → card click | `components/pages/CharactersPage/CharactersListPage.tsx:190-220` (`openDetail`) | Opens a **passport modal**: `GET /characters/{id}/public` (`:195`) + `/inventory/items/bulk` + skills bulk (`:205`) |
| E2 | Characters list → owner nickname | `CharactersListPage.tsx:245-251` | `<Link to="/user-profile/{user_id}">` — goes to the **user**, not the character |
| E3 | Location "Кто здесь" → player card | `components/pages/LocationPage/PlayersSection.tsx:339-362` | **Not clickable.** Only `PlayerActionsMenu` (trade / duel / attack) |
| E4 | Location → NPC card | `PlayersSection.tsx:376-391` → `LocationPage/NpcProfileModal.tsx:55` | Modal on `GET /characters/{npcId}/short_info` |
| E5 | User profile → "Персонажи" card | `components/UserProfilePage/CharactersSection.tsx:57-60` | **Bug:** `<Link to="/profile">` is hardcoded — clicking someone else's character silently opens **your own** profile |
| E6 | User profile → friends / wall | `FriendsSection.tsx:69,89-90,154,167-168,207,220-221`, `WallSection.tsx:100-101,116-117` | `<Link to="/user-profile/{id}">` |
| E7 | Chat message → author | `components/Chat/ChatMessage.tsx:47,55,61-63` | `<Link to="/user-profile/{user_id}">` |
| E8 | Post history page | route `post-history/:characterId` (`App.tsx:319`), `components/pages/PostHistoryPage/PostHistoryPage.tsx:12-13,32` | Renders **any** character's post history by id; **no in-app link points at another id** |
| E9 | Home leaderboard | `components/HomePage/Stats/Stats.tsx`, `Podium.tsx`, `RankRow.tsx` | Entries are **not clickable at all** |
| E10 | Battle / party | `BattlePage.tsx:452`, `api/battles.ts:169,178`, `api/party.ts`, `api/squads.ts:150-162` | Shows others' names/avatars/HP; never navigates to a profile |

So §1's list of entry points that "должны работать" is mostly **aspirational**: E1 and E4 are modals,
E2/E6/E7 land on the *user* page, E5 is broken, E3 and E9 are dead, E8 works only by typing a URL.

**What breaks if responses get thinner.** Every consumer below reads the **own** character, so the owner
path must keep byte-identical payloads — this is the main regression risk:

| Consumer | file:line | Depends on |
|---|---|---|
| `loadProfileData` fan-out | `redux/slices/profileSlice.ts:812-836` | C1, C5, A1, I1, I2, I6, I5, I9, A5 |
| `CharacterInfoPanel` / header | consumes `full_profile` | `currency_balance`, `stat_points`, `level_progress`, hp/mana/energy/stamina |
| `StatsTab`, `EquipmentPanel`, `InventoryTab` | ProfilePage tabs | A1, I1, I2 |
| `SkillsTab` | `SkillsTab.tsx:97-98` | S1 |
| `PerksTab` | `PerksTab.tsx:39` | A2 |
| `TitlesTab` | `TitlesTab.tsx:45` | C6 |
| `LogsTab` / `PostHistoryTab` | `LogsTab.tsx:99`, `PostHistoryTab.tsx:122` | C8, C7 |
| `CharactersListPage` passport | `:195`, `:205` | C3 + `/inventory/items/bulk` |
| `UserProfilePage` | `api/userProfile.ts:42` | U1 — Frontend Dev must confirm nothing renders `character.currency_balance` before it is dropped |
| `CharacterSwitchDropdown` | `:46` | U2 |
| `NpcProfileModal` | `:55` | C4 (NPC) |
| `TradeItemSelector` / `NpcAuctionModal` | `:59` / `:155` | I1 (own items) |

Because `api/axiosSetup.ts:53-61` attaches the Bearer token to **every** outgoing request on the default
axios instance, **no frontend change is needed just to keep the owner's own profile working** under
optional auth. Note also that the 403 branch raises a toast (`axiosSetup.ts`), so a 403 on a page a
guest legitimately opens is user-visible noise — prefer a thinner 200 there.

---

### 2.7 Cross-service callers that will break on a naive gate

These hit the to-be-gated routes **with no credentials at all**:

| Caller | file:line | Target | Today |
|---|---|---|---|
| battle-service `battle_engine.fetch_full_attributes` | `app/battle_engine.py:29` | A1 | anonymous |
| battle-service `battle_engine.fetch_weapons` | `app/battle_engine.py:45` and `:52` | I2 + I3 | anonymous |
| battle-service `inventory_client.get_equipment_durability` | `app/inventory_client.py:58` | I2 | anonymous |
| battle-service `inventory_client.get_item` | `app/inventory_client.py:23` | I3 | anonymous |
| dungeon-service `get_character_items` | `app/http_clients.py:287` | I1 | anonymous |
| dungeon-service item lookup | `app/http_clients.py:306` | I3 | anonymous |
| character-attributes-service `perk_evaluator` | `app/perk_evaluator.py:63,81`; `app/main.py:562` | C1 | anonymous |
| character-service | `app/main.py:1923`, `:1973` | A4, A1 | anonymous |
| locations-service | `app/main.py:1302,1596,2666`; `app/crud.py:7350` | A1 | anonymous |
| locations-service `_fetch_character_brief_map` | `app/crud.py:6854` | C4 | anonymous |
| skills-service | `app/main.py:799` | A1 | anonymous |
| user-service `_fetch_character_short` | `main.py:116` | C4 | anonymous |
| battle-service `skills_client` | `app/skills_client.py:80,104` | S1 | **already sends the service token** |

All 13 services already carry `INTERNAL_SERVICE_TOKEN` in both compose files (FEAT-169 task #1), and
most already have an `_internal_token_headers()` helper — so the plumbing exists; the work is the
call-site edits plus new `/internal/` twins for I1, I2, A1, C1, C4 (and possibly I3).

**Six of these callers swallow errors with a WARNING** (the FEAT-169 finding repeats): a forgotten header
produces silent degradation rather than a visible failure. QA must assert the header on the real client
function (`call.kwargs["headers"]["X-Internal-Token"]`), not merely that nothing crashed.
**Order matters: teach every caller first, gate second.**

---

### 2.8 Test blast radius

Roughly **80 test call sites** across `services/*/app/tests` and `services/user-service/tests` hit these
routes anonymously — `test_endpoint_auth.py`, `test_perks.py`, `test_regen.py`, `test_satiety.py`,
`test_recalculate.py`, `test_stats_formulas.py`, `test_public_character.py`, `test_equip_locking.py`,
`test_npc_equipment.py`, `test_item_out_schemas_serve_stored_rows.py`, `test_pve_rewards.py`,
`test_cumulative_stats.py`, and others. Adding a dependency to A1/I1/I2/S1/C1 turns them red. The
FEAT-169 precedent: move service-shaped tests onto the internal twin, give player-shaped tests a
dependency override. Budget a QA task per service.

---

### 2.9 NPC / mob characters

NPCs and mobs are rows in the **same `characters` table**: `is_npc = True`
(`character-service/app/models.py:61`) and, critically, `user_id` is nullable and **NULL** for them
(`models.py:48`). They flow through **the same endpoints**: C4 `short_info` (E4 NPC modal),
C3 `/public` (the API client documents "Also serves NPCs — see `is_npc`",
`api/charactersPublic.ts:32`), `/characters/list?include_npcs=true`, `/characters/npcs/by_location`
(`main.py:2917`), `/characters/mobs/by_location` (`main.py:3283`), `/characters/bestiary`
(`main.py:3755`), plus A1/I1/I2/S1 for the battle engine.

Because `user_id IS NULL`, **any owner-based predicate refuses every viewer on an NPC** — the NPC
passport modal and NPC rows in the characters list would break for everyone. FEAT-169 hit exactly this
and solved it with an internal twin carrying no ownership check. §1 leaves this open. **See Q6.**

---

### 2.10 Risks

| Risk | Mitigation |
|---|---|
| A naive gate on A1/I1/I2/C1/C4 breaks battle, dungeons, locations, skills and the login flow (`/users/me` → C4) | Two passes, FEAT-169 style: add `/internal/` twins and teach all callers to send the header **first**, gate **second**. §2.7 is the checklist |
| The owner's own profile loses fields and the UI crashes on `undefined` | Owner path must return byte-identical payloads; optional auth + the axios interceptor makes this automatic. QA should assert "owner response == pre-change response" field-for-field |
| NPC/mob surfaces break because `user_id IS NULL` | Q6 + the FEAT-169 internal-twin precedent |
| `GET /users/{id}/profile` keeps leaking gold via `CharacterShort.currency_balance` even after C1/C4 are fixed | U1 already has `get_optional_user`; drop the field on the non-owner branch, and drop it from C4 unless a caller needs it (only `/users/me` legitimately does) |
| A 403 on a page a guest legitimately opens raises a red toast (`axiosSetup.ts` 403 handler) | Prefer a **thinner 200** for profile-shaped reads; reserve 403 for explicitly private routes (inventory, perks, skills, fast slots, cumulative stats) |
| `GET /attributes/{id}/perks` **writes on GET** and transitively calls two services (`main.py:339-345`) | Pre-existing separate ISSUES entry; JWT reduces but does not remove the amplifier. Cheap to fix while the route is being touched — flag to Architect |
| ~80 anonymous test calls go red | A QA task per service, not an afterthought |
| §1 assumes entry points that do not exist (E3, E5, E8, E9) and a page that does not exist at all | Q1 — size the frontend scope before cutting tasks |
| A "thin" public schema that silently drifts from the fat one (ISSUES.md rule from FEAT-154) | Derive the public schema from the private one (explicit field subset) rather than hand-maintaining two parallel models |

---

### 2.11 Patterns confirmed

- **sync** SQLAlchemy: character-service, inventory-service, character-attributes-service, user-service.
- **async** (aiomysql): skills-service, locations-service, battle-service.
- **Pydantic v1** everywhere (`class Config: orm_mode = True`); `response_model` already strips
  undeclared fields — which is why `strength`/`agility` never reach the player via A1.
- Alembic present in all nine owning services; **no migration needed here** (unless Q5 mints a
  permission).
- nginx blocks `/*/internal/*` with `return 403` in **both** `nginx.conf` and `nginx.prod.conf`;
  everything else under `/characters/`, `/attributes/`, `/inventory/`, `/skills/`, `/users/`,
  `/notifications/` is proxied straight through.
- Frontend TS migration: `profileSlice.ts`, `charactersPublic.ts`, `userProfile.ts`, `characterLogs.ts`,
  `CharactersSection.tsx`, `ProfilePage.tsx` are already TypeScript; `api/characters.js` is legacy JS.

---

### 2.12 Questions that need the user's decision

- **Q1 — the missing page.** There is no "чужой профиль персонажа" page today (§2.0 #1, §2.6). Is
  FEAT-171 (a) backend gating + thinning only, with the public page as a follow-up feature, or (b) also
  the new public character page plus links from the leaderboard, location, user profile and chat? The
  scope differs by roughly a whole frontend feature.
- **Q2 — the public item card.** Exactly `{name, description, icon, rarity}`? May it also show
  `item_type`, `item_level`, weapon/armor subclass — flavour that borders on a stat? Is `price` hidden?
- **Q3 — the passport snapshots.** `GET /characters/{id}/public` already publishes `starting_attributes`
  (the frozen FEAT-155 stat snapshot) and `granted_kit` to everyone, by design. §1 says characteristics
  are private. Do the **starting** numbers stay public (a historical record, not the current build), or
  become private too?
- **Q4 — two things §1 does not mention.** (a) `GET /characters/{id}/logs` — the character event log with
  free-form metadata (loot, gold, XP). Public or owner-only? (b) `xp_earned` per post in the public post
  history — §1 says post history is public but XP is private; drop the field from the public view?
- **Q5 — the admin path.** Reuse the existing `characters:read` permission (already granted to moderator,
  `user-service/alembic/versions/0007_add_remaining_permissions.py:64`) together with the
  `admin`/`moderator` role check, or mint a new permission such as `characters:view_private`? A new
  permission means a migration **and** an explicit seed row in
  `test_rbac_permissions.py::TestAdminAutoPermissions` (CLAUDE.md §10.13).
- **Q6 — NPCs and mobs** (§1 already flags it). They live in the same table with `user_id IS NULL`, so an
  ownership predicate refuses everyone. Options: (a) NPCs fully public — anyone may read an NPC's stats
  and equipment; (b) NPCs public for the same fields as players, their numbers admin-only; (c) NPC reads
  move to internal/admin routes. The bestiary and the NPC profile modal argue for at least some NPC data
  staying public.
- **Q7 — the navigation bug at `CharactersSection.tsx:57`** (§2.6 E5): fix inside FEAT-171 as part of
  "entry points must work", or log it in ISSUES.md and leave it? It is the natural entry point for the
  new public page, so folding it in looks right.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Scope statement

FEAT-171 is **backend gating + response thinning**, plus the *minimum* frontend needed to keep the
UI that exists today correct against thinner payloads. **The new public character-profile page and
the rewiring of entry points (leaderboard, location, user profile, chat, post history) are OUT OF
SCOPE** — a follow-up feature. Nothing here creates a new page. Everything here must leave every
currently-working screen working.

**No DB changes. No Alembic migration. No new RBAC permission** (Q5: reuse `characters:read`).

---

### 3.1 The core primitive — `can_view_private`

One predicate decides everything. It is small, boring and must be **identical in every service**.

```python
# Canonical reference implementation (sync services).
# character-service / character-attributes-service / inventory-service: app/visibility.py
# skills-service: async twin in app/visibility.py (AsyncSession + await db.execute)

CHARACTER_PRIVATE_PERMISSION = "characters:read"          # Q5 — existing permission, no migration
PRIVILEGED_ROLES = ("admin", "moderator")

def can_view_private(db, character_id: int, user: Optional[UserRead]) -> bool:
    """May `user` (or nobody, if None) see the PRIVATE layer of this character?

    404 if the character does not exist  — §1: never reveal existence.
    True  for an NPC/mob (`user_id IS NULL`) — Q6: an NPC has no private layer.
    True  for the owner.
    True  for admin/moderator that also holds `characters:read`.
    False otherwise (guest, or another player).
    """
    row = db.execute(
        text("SELECT user_id FROM characters WHERE id = :cid"), {"cid": character_id}
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    owner_id = row[0]
    if owner_id is None:                                   # NPC / mob — public (Q6)
        return True
    if user is None:
        return False
    if user.id == owner_id:
        return True
    return (
        user.role in PRIVILEGED_ROLES
        and CHARACTER_PRIVATE_PERMISSION in (user.permissions or [])
    )
```

And one thin wrapper for the **hard-gated** routes, so the 403 message is identical everywhere:

```python
def require_private_access(db, character_id: int, user) -> None:
    if not can_view_private(db, character_id, user):
        raise HTTPException(status_code=403, detail="Эти данные доступны только владельцу персонажа")
```

**D1 — why a copy per service, not a shared package.** The repo has no shared Python library; every
service already carries a near-identical `auth_http.py` copy. Inventing a package here would be a
cross-cutting refactor inside a security feature — exactly the "hidden refactor along the way"
CLAUDE.md §5 forbids. So: **four copies** (character-service, character-attributes-service,
inventory-service, skills-service), each in `app/visibility.py`, each opening with the docstring
`"Mirror of features/FEAT-171 §3.1. Keep the four copies byte-identical in behaviour."`
**Consistency is enforced by QA, not by imports:** task Q6 runs the *same* parametrised matrix
against all four services (guest / other player / owner / admin / NPC / missing id), so a copy that
drifts goes red.

> **Update (task 26).** The review fix for the NPC-shop side door (task 22) added a **fifth** copy in
> locations-service, so the docstrings now read *"Keep the five copies byte-identical in behaviour"*
> and list all five files, and `test_feat171_predicate_parity.py` exists in **five** services, the
> locations one being the async twin of the skills-service file.

**D2 — `verify_character_ownership` is not touched.** It raises instead of returning a flag and has
no admin path. Changing it would silently widen ~30 write endpoints. `can_view_private` is
additive and lives beside it.

**D3 — `get_optional_user` where it is missing.** Add to `app/auth_http.py` of character-service,
character-attributes-service, inventory-service and skills-service, copying the locations-service
shape:

```python
OAUTH2_SCHEME_OPTIONAL = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

def get_optional_user(token: Optional[str] = Depends(OAUTH2_SCHEME_OPTIONAL)) -> Optional[UserRead]:
    """Same as get_current_user_via_http, but returns None instead of raising."""
    if not token:
        return None
    try:
        return get_current_user_via_http(token)
    except HTTPException:
        return None
```

It is a **sync `def`**, so FastAPI runs it in the threadpool even on `async def` handlers — no event
loop blocking, including in skills-service. (Do **not** copy locations-service's inline
`import requests` — reuse the module's existing client.)

**This is the single biggest de-risker (§2.0 #3):** `api/axiosSetup.ts:53-61` already attaches the
Bearer token to **every** request, so under optional auth the owner keeps byte-identical payloads
with **zero frontend changes**.

---

### 3.2 Three gating styles — and when each is used

| Style | Behaviour | Used when |
|---|---|---|
| **A. Optional-auth, thinned 200** | `get_optional_user` → `can_view_private` → the handler returns the FULL shape or the PUBLIC shape. Never 403. | The route is reachable by guests today and is profile-shaped (a 403 here would fire the red toast in `axiosSetup.ts`). |
| **B. Hard gate** | `get_optional_user` → `require_private_access` → 404 missing / 403 stranger / 200 full. | The route has **no** legitimate guest consumer: inventory, perks, skills, attributes, cumulative stats, rest status, event log. |
| **C. Internal twin** | New `/internal/...` path behind `verify_internal_token` (nginx already `return 403`s `/*/internal/*`), returning today's full payload unchanged. | A sibling service needs the data with no user in context. |

**D4 — two shapes on one path.** For style A, declare `response_model=None` on the route and have
the handler return an explicitly constructed Pydantic object — `schemas.FullProfileResponse(...)`
or `schemas.PublicProfileResponse(...)`. FastAPI then serialises the model's own fields, so a
private field is **absent from the JSON**, not `null`. Document both in `responses={200: {...}}`
for OpenAPI. Do **not** use `Union[...]` as a `response_model` (Pydantic v1 coerces to the first
match) and do **not** use `response_model_exclude_none` (it would also swallow legitimately-null
public fields such as `avatar`).

**D5 — public shapes are derived, never hand-copied.** ISSUES/FEAT-154 lesson. Each public schema
is built by exactly **one** projection function per service (e.g. `schemas.public_item_card(row)`,
`crud.to_public_equipment_slot(slot)`), and every public path calls that function. A second
hand-written field list anywhere is a review FAIL.

---

### 3.3 The public item card — one document, reused everywhere

`ItemBulkResponse` (`inventory-service/app/schemas.py:2084`) **already is** exactly the Q2 shape:

```python
{ "id": int, "name": str, "description": str|None,
  "image_url": str|None, "rarity": str|None, "type": str|None }
```

**D6 — `ItemBulkResponse` is promoted to THE canonical public item card.** Alias it
`PublicItemCard = ItemBulkResponse`, extract the row→card mapping (today inlined at `main.py:253`)
into `schemas.public_item_card(row)`, and make every public path use it:

- `GET /inventory/items/bulk` (I4) — already correct, only refactored onto the projection.
  **The passport modal therefore needs no change.**
- the public equipment view (§3.4),
- `GET /inventory/items/{item_id}` (I3) — its `response_model` changes from the fat `Item` to
  `PublicItemCard` (see §3.4).

`type` is kept (it is already public through `/items/bulk` today, carries no numbers, and the UI
needs it to pick the slot icon). `item_level`, `price`, weapon/armor subclass, every `*_modifier`,
`effects[]`, `damage_entries[]`, `xp_buffs[]`, `socket_count`, `whetstone_level`, durability — all
excluded.

---

### 3.4 Per-endpoint contract

Legend: **A/B/C** = gating style from §3.2. "unchanged" = not touched by this feature.

#### character-service

| # | Path | Style | Public payload | Private-only fields (owner / admin / NPC) |
|---|---|---|---|---|
| C1 | `GET /characters/{id}/full_profile` | **A** | `id`, `name`, `level`, `active_title`, `active_title_rarity`, `avatar` | `currency_balance`, `stat_points`, `level_progress{}`, `attributes{}` — **absent** for strangers |
| C1i | `GET /characters/internal/{id}/full_profile` | **C** *(new)* | — | today's full body, unchanged |
| C2 | `GET /characters/{id}/profile` | unchanged | already clean | — |
| C3 | `GET /characters/{id}/public` | **A** | everything it returns today **except** the two fields opposite; `granted_kit` + `granted_kit_is_snapshot` **stay public** | `starting_attributes`, `starting_attributes_is_snapshot` → **absent** for strangers |
| C4 | `GET /characters/{id}/short_info` | **drop field** | today's body **minus `currency_balance`** (unconditionally — see D7) | — |
| C4i | `GET /characters/internal/{id}/short_info` | **C** *(new)* | — | today's body **including `currency_balance`** |
| C5 | `GET /characters/{id}/race_info` | unchanged | clean | — |
| C6 | `GET /characters/{id}/titles` | unchanged | public per §1 | — |
| C7 | `GET /characters/{id}/post-history` | **A** | `id`, `location_id`, `location_name`, `content`, `char_count`, `created_at` | `xp_earned` → **absent** for strangers (Q4b) |
| C8 | `GET /characters/{id}/logs` | **B** | — | whole route: owner + admin only (Q4a) |
| C9/C10/C11 | `by_location`, `list`, `home-leaderboards` | unchanged | clean | — |

**D7 — `currency_balance` leaves `short_info` for everyone, including the owner.** `short_info` is
called server-to-server by user-service and locations-service, never by the owner's browser with
their own JWT in a context that needs gold; making it optional-auth would give
`_fetch_character_short` (which holds no user token) a thinner body and silently break
`/users/me` → the header coin counter. The internal twin C4i carries gold; user-service calls the
twin. This is the one place where a *hard* field removal beats optional auth.

#### character-attributes-service

| # | Path | Style | Note |
|---|---|---|---|
| A1 | `GET /attributes/{id}` | **B** | no guest consumer: the frontend reads it only on the owner's own ProfilePage |
| A1i | `GET /attributes/internal/{id}` | **C** *(new)* | for battle-service, character-service, locations-service ×4, skills-service |
| A2 | `GET /attributes/{id}/perks` | **B** | perk tree is private per §1 |
| A3 | `GET /attributes/{id}/cumulative_stats` | **B** | includes gold earned/spent; no FE caller |
| A4 | `GET /attributes/{id}/passive_experience` | **B** | only caller is character-service → moves to A4i |
| A4i | `GET /attributes/internal/{id}/passive_experience` | **C** *(new)* | called by C1 / C1i |
| A5 | `GET /attributes/{id}/rest-status` | **B** | owner-only panel |

**D8 — A2 keeps its write-on-GET.** `reconcile_perks` firing inside a GET (`main.py:339-345`) is a
pre-existing ISSUES entry. The hard gate narrows the amplifier to authenticated owners/admins,
which is enough for this feature; converting it to a read-only GET is a separate task and must
**not** be smuggled in here (CLAUDE.md §5.2).

#### inventory-service

| # | Path | Style | Note |
|---|---|---|---|
| I1 | `GET /inventory/{id}/items` | **B** | admin character editor (`api/adminCharacters.ts:145`) passes via the admin branch |
| I1i | `GET /inventory/internal/characters/{id}/items` | **C** *(new)* | for dungeon-service `http_clients.py:287` |
| I2 | `GET /inventory/{id}/equipment` | **B** | **closes the belt hole**; owner/admin payload stays byte-identical, `fast_slot_*` rows included as today. Admin editor (`adminCharacters.ts:154`) passes via the admin branch |
| I2p | `GET /inventory/{id}/equipment/public` | **new public route** | anonymous; `List[PublicEquipmentSlot]`, `fast_slot_*` **excluded at the query level** |
| I2i | `GET /inventory/internal/characters/{id}/equipment` | **C** *(new)* | for battle-service `battle_engine.py:45` and `inventory_client.py:58` |
| I3 | `GET /inventory/items/{item_id}` | **thin** | `response_model` becomes `PublicItemCard`; stays anonymous. ~~No FE caller today (verified)~~ — **wrong, see D10**: the admin item editor calls it |
| I3a | `GET /inventory/admin/items/{item_id}` | **admin** *(new, review #1)* | fat `Item`, `require_permission("items:read")` — the editor's door (D10) |
| I3i | `GET /inventory/internal/items/{item_id}` | **C** *(new)* | fat `Item`, for battle-service `inventory_client.py:23` and dungeon-service `http_clients.py:306` |
| I4 | `GET /inventory/items/bulk` | unchanged behaviour | refactored onto `public_item_card` (D6) |
| I5 | `GET /inventory/{id}/equipment-rules` | **stays public** | reference data, not character data — see D11 (review #1 finding 6); only the 404 discipline is added |
| I6–I9 | fast_slots, item-detail, active-buffs | unchanged | already owner-gated; `item-detail` **stays the owner's fat card** |

`PublicEquipmentSlot`:

```python
class PublicEquipmentSlot(BaseModel):
    slot_type: str
    item: Optional[PublicItemCard] = None
    class Config: orm_mode = True
```

Nothing else. No `effective_damage`, no `enhancement_points_spent`, no `enhancement_bonuses`, no
`socketed_gems`, no `current_durability`, no `is_enabled`, no `item_id` echo, no `character_id`.
The fast-slot exclusion is a **filter in the query/projection**
(`slot_type NOT LIKE 'fast_slot_%'`), not a frontend concern — §1's "не регрессировать FEAT-169".

**D9 — known residual, deliberately out of scope.** `GET /inventory/items` (catalogue list,
`main.py:135`) still returns every `*_modifier` of every item anonymously, so a determined stranger
can look up the *template* stats of a worn item by name. What FEAT-171 protects is the
**instance** data (sharpening, sockets, durability, `effective_damage`) and the *linkage* between a
character and a numeric build. Closing the catalogue would break four admin screens and is a
product decision — raised to the user as question **U-A** (§3.9), logged, not implemented here.

**D10 — one item, three views** (added after review #1, finding 1). I3's "no FE caller today
(verified)" was **wrong**: `api/items.ts::fetchItem` calls `GET /inventory/items/{id}`, hidden
behind the axios `baseURL` (`api/client.ts:19`), and seeds `ItemsAdminPage/ItemForm` — which then
`PUT`s the form back. A thin seed therefore did not merely hide numbers, it **wrote defaults over
real item data on every save**. The internal twin cannot be the fix: nginx `return 403`s
`/inventory/internal/`, so no browser can reach it. So the item now has exactly three doors, and
each one has a single audience:

| Door | Auth | Body | Audience |
|---|---|---|---|
| `GET /inventory/items/{id}` | anonymous | `PublicItemCard` (6 keys) | the public card — "открыть меч и прочитать описание" |
| `GET /inventory/internal/items/{id}` | `X-Internal-Token` | fat `Item` | battle-service, dungeon-service |
| `GET /inventory/admin/items/{id}` | JWT + `items:read` | fat `Item` | the item editor, the recipes screen |

No new permission and no migration: `items:read` is what `ProtectedRoute` already demands of the
`/admin/items` route (`App.tsx:170`) and what `GET /admin/items/{id}/conversions` already uses, so
whoever can open the editor can already read this. The admin body is asserted **equal to the
internal twin's**, so the two fat doors cannot drift apart.

**D11 — `GET /inventory/{id}/equipment-rules` stays public** (added after review #1, finding 6 —
the one character-scoped GET the feature never decided on). It is **reference data keyed by a
character, not data about the character**: the entire response (`class_id`, `subclass_key`,
`armor_classes`, `main_hand_kinds`, `off_hand_kinds`, `two_handed_kinds`) is derived from the
class and subclass, and both are already public through C3 `/public`, C4 `short_info` and C10
`/characters/list`. Nothing in the body is a number of this character, a possession, or anything
the §2.3 matrix lists as private. Gating it would be **stricter than the public passport** while
protecting nothing, and would break the inventory greying-out on the very showcase page FEAT-172
is about to build. What *is* fixed is the error discipline the reviewer flagged: a missing
`character_id` used to answer 200 "no restrictions" and now answers **404 «Персонаж не найден»**,
like every other character-scoped route in this feature.

#### skills-service

| # | Path | Style | Note |
|---|---|---|---|
| S1 | `GET /skills/characters/{id}/skills` | **B'** | dependency becomes `allow_jwt_or_service_token` (already exists, `auth_http.py:61`); `None` = service caller → allow; a real user → `await can_view_private(...)`. **battle-service already sends the token → zero caller changes** |
| S2/S3 | tree progress / catalogue | unchanged | — |

#### user-service

| # | Path | Change |
|---|---|---|
| U1 | `GET /users/{id}/profile` | `_fetch_character_short` switches to the internal twin C4i (so gold is available); the response **omits `character.currency_balance`** unless `current_user` is the profile owner or `role in ("admin","moderator")`. Already has `get_optional_user` |
| U4 | `GET /users/me` | unchanged — gold keeps flowing to the header coin counter, now via C4i |
| U2/U3/U5 | — | unchanged |

#### notification-service

| # | Path | Change |
|---|---|---|
| N1 | `GET /notifications/chat/messages` | `Depends(get_current_user_via_http)` — **401 for guests** (§1). `POST`/`DELETE` already gated |

---

### 3.5 Execution order — the FEAT-169/170 two-pass law

A gate that lands before its callers have credentials takes down battles, dungeons, locations,
skills **and the login flow** (`/users/me` → C4). Therefore, non-negotiably:

```
PASS A  (tasks B1–B4, no user-visible change, independently deployable)
        add get_optional_user + visibility.py to the 4 services
        add every internal twin: C1i, C4i, A1i, A4i, I1i, I2i, I3i
        teach all 13 anonymous callers to use the twin / send X-Internal-Token
                 ↓  merged and green
PASS B  (tasks B5–B9)
        apply the gates and thin the public shapes
                 ↓
PASS C  frontend (F1–F4) + QA (Q1–Q7) + review
```

**Caller → target mapping for Pass A** (§2.7, all 13):

| Caller | file:line | Today | After Pass A |
|---|---|---|---|
| battle-service `battle_engine.fetch_full_attributes` | `battle_engine.py:29` | A1 anon | **A1i** + token |
| battle-service `battle_engine.fetch_weapons` | `battle_engine.py:45`, `:52` | I2, I3 anon | **I2i**, **I3i** + token |
| battle-service `inventory_client.get_equipment_durability` | `inventory_client.py:58` | I2 anon | **I2i** + token |
| battle-service `inventory_client.get_item` | `inventory_client.py:23` | I3 anon | **I3i** + token |
| dungeon-service `get_character_items` | `http_clients.py:287` | I1 anon | **I1i** + token |
| dungeon-service item lookup | `http_clients.py:306` | I3 anon | **I3i** + token |
| char-attrs `perk_evaluator` | `perk_evaluator.py:63,81`; `main.py:562` | C1 anon | **C1i** + token |
| character-service | `main.py:1923` | A4 anon | **A4i** + token |
| character-service | `main.py:1973` | A1 anon | **A1i** + token |
| locations-service | `main.py:1302,1596,2666`; `crud.py:7350` | A1 anon | **A1i** + token |
| locations-service `_fetch_character_brief_map` | `crud.py:6854` | C4 anon | **C4i** + token |
| skills-service | `main.py:799` | A1 anon | **A1i** + token |
| user-service `_fetch_character_short` | `main.py:116` | C4 anon | **C4i** + token |
| battle-service `skills_client` | `skills_client.py:80,104` | S1 + service token | **unchanged** |

`INTERNAL_SERVICE_TOKEN` is already in both compose files and every service has an
`_internal_token_headers()` helper (FEAT-169). **No DevSecOps task is required.**

**Six of these callers swallow failures with a WARNING** — a forgotten header degrades silently
instead of failing loudly. QA must assert the header on the client function itself
(`call.kwargs["headers"]["X-Internal-Token"]`), not merely that nothing crashed.

---

### 3.6 Frontend — the minimum, nothing more

No new page, no new route, no new API client beyond what is listed.

| # | File | Change |
|---|---|---|
| F1 | `components/UserProfilePage/CharactersSection.tsx:57` | **Navigation bug.** `<Link to="/profile">` is hardcoded, so clicking someone else's character opens your own. Minimal fix while the public page does not exist: keep the `<Link to="/profile">` **only** when the card is the viewer's own *active* character (`char.id === state.user.character?.id`); every other card renders as a **non-interactive `<div>`** with the same markup (no `group-hover` affordance, no pointer cursor). Add `// TODO(FEAT-172): link to /character/:id once the public profile page exists`. |
| F2 | `components/ProfilePage/PostHistoryTab/PostHistoryTab.tsx:97`, `api/characterLogs.ts:26` | `xp_earned` becomes `xp_earned?: number`; render the `+N XP` span only when it is a number |
| F3 | `redux/slices/profileSlice.ts:120-121` + `ProfilePage/CharacterTab/CharacterPanel.tsx:109,122`, `IndicatorsPanel.tsx:33` | `currency_balance`, `stat_points`, `level_progress`, `attributes` become optional on the `FullProfile` type; guard the renders (`?? 0`, and `(profile.currency_balance ?? 0).toLocaleString('ru-RU')`). ProfilePage only ever loads the **own** character, so this is type-safety for `tsc --noEmit`, not a behaviour change |
| F4 | `components/Chat/ChatPanel.tsx:43-45`, `components/Chat/ChatHistoryPage.tsx`, `components/App/App.tsx:336` | Chat history is now 401 for guests: `ChatPanel` must **not** dispatch `fetchMessages` when `isAuthenticated === false` and must render a Russian empty state («Войдите в аккаунт, чтобы читать чат»); wrap the `chat/history` route in `<ProtectedRoute>` |
| F5 | `api/charactersPublic.ts:84-91`, `CommonComponents/CharacterPassport/adapters.ts:214,232` | `starting_attributes` can now be absent for a stranger: mark it and `starting_attributes_is_snapshot` optional. `adapters.ts` already handles the `null` case (pre-FEAT-155 rows) — **verify, do not rewrite**. The passport's item resolution goes through `/inventory/items/bulk`, which is unchanged, so the modal keeps working |
| F6 | `api/userProfile.ts`, `components/pages/LocationPage/NpcProfileModal.tsx` | `CharacterShort.currency_balance` / `short_info.currency_balance` may be absent — confirm nothing on the user profile or the NPC modal renders it (analysis found no render site); make the type optional |

Styling rules (CLAUDE.md §10.8/10.10/10.12): F1 and F4 touch markup, so those components must be
Tailwind-only (`CharactersSection.tsx` already is), keep the Design System classes they use, and
stay correct at 360px. No new `.scss`. No `React.FC`. All files touched are already `.tsx`.

**Explicitly NOT in this feature:** a `/character/:id` route, a public profile page, clickable
leaderboard rows (E9), clickable location player cards (E3), chat/user-profile link retargeting
(E6/E7), post-history entry points (E8).

---

### 3.7 Data flow — a stranger opens a public surface

```
Guest / other player                      Owner / admin
────────────────────                      ─────────────
GET /characters/7/public                  GET /characters/7/public
  (no token | other user's token)           Authorization: Bearer <jwt>  (axios interceptor)
        │                                          │
        ▼                                          ▼
get_optional_user -> None | UserRead       get_optional_user -> UserRead
        │                                          │
        ▼                                          ▼
can_view_private(db, 7, user)              can_view_private(db, 7, user)
  row missing        -> 404                  owner_id == user.id            -> True
  owner_id IS NULL   -> True  (NPC)          role in (admin,moderator)
  user is None       -> False                  and "characters:read"        -> True
  other player       -> False
        │                                          │
        ▼                                          ▼
CharacterPublicResponsePublic              CharacterPublicResponse
(starting_attributes ABSENT)               (identical to today, byte for byte)
```

Cross-service path, unchanged for the engine:

```
battle-service --X-Internal-Token--> GET /attributes/internal/{id}        (A1i)
               --X-Internal-Token--> GET /inventory/internal/characters/{id}/equipment (I2i)
               --Bearer <service>--> GET /skills/characters/{id}/skills   (S1, already)
user-service   --X-Internal-Token--> GET /characters/internal/{id}/short_info (C4i, gold included)
```

---

### 3.8 Security review of the design

- **Authentication.** Style A/B routes take `get_optional_user`; style C routes take
  `verify_internal_token` (fail-closed: unset env → 503 for everyone). N1 takes a hard JWT.
- **Authorization.** Single predicate (§3.1). Admin path = role **and** `characters:read`; Admin
  automatically holds every permission (CLAUDE.md §10.13), Moderator already has `characters:read`
  from `0007_add_remaining_permissions.py:64`. No new permission ⇒ no migration ⇒ no RBAC seed test.
- **Existence disclosure.** Missing character → **404 «Персонаж не найден»** on every gated route,
  checked *before* the ownership branch, so 403-vs-404 cannot be used as an oracle.
- **Input validation.** `character_id` / `item_id` stay path ints; all queries stay parameterised
  (`text(... :cid)`); no string-built SQL is introduced.
- **Error messages.** Russian, non-leaking: 403 «Эти данные доступны только владельцу персонажа»,
  404 «Персонаж не найден», 401 «Не удалось подтвердить учётные данные» (existing text).
- **Rate limiting.** Not added. These are reads that were already open; nginx has no per-route
  limiter today and adding one is a separate DevSecOps concern.
- **Defence in depth.** Response shaping is **server-side only**. A field a stranger may not see
  never enters the JSON — the frontend "just not rendering it" is explicitly not the mechanism
  (§1), and QA asserts **absence of the key**, not absence of pixels.
- **Residual risks:** D9 (open item catalogue) and the NPC decision (Q6) — an NPC/mob's numbers stay
  readable by anyone, which is today's behaviour and the bestiary depends on it.

---

### 3.9 Open questions for the user (non-technical, do not block implementation)

- **U-A.** `GET /inventory/items` returns the full catalogue — every modifier, damage entry and
  effect of every item — anonymously (four admin screens use it). Hiding the numbers on a *worn*
  item therefore hides the linkage, not the numbers themselves: a stranger can still look the sword
  up by name. Should the catalogue stay open reference data (current assumption), or become a
  separate closing task?
- **U-B.** NPCs and mobs stay fully public per Q6, which means anyone can read a mob's attributes,
  equipment and skills before a fight. That is today's behaviour and the bestiary relies on it —
  confirm it is intended, or raise a follow-up to hide mob numbers.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

> **Order is a safety property, not a preference.** Tasks 1–5 (Pass A) add capability and change
> nothing a user can see. Tasks 6–11 (Pass B) close the doors. A Pass B task merged before task 5
> takes down battles, dungeons, location travel and the login flow. Reviewer must verify the order
> was respected.

### Pass A — plumbing and internal twins (no user-visible change)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **character-service auth plumbing + internal twins.** Add `get_optional_user` + `OAUTH2_SCHEME_OPTIONAL` to `auth_http.py` (§3.1 D3). Add `app/visibility.py` with `can_view_private` / `require_private_access` exactly as in §3.1 (NPC ⇒ True, 404 before 403). Add `GET /characters/internal/{character_id}/full_profile` and `GET /characters/internal/{character_id}/short_info`, both `Depends(verify_internal_token)`, both returning **today's** full bodies (short_info twin **includes `currency_balance`**). Reuse the existing handler bodies — no logic fork. | Backend Developer | DONE | `services/character-service/app/auth_http.py`, `app/visibility.py` (new), `app/main.py` | — | `python -m py_compile` passes; twins return 401 without the header, 503 when `INTERNAL_SERVICE_TOKEN` is unset, and a body identical to the public route (plus gold) with it; no existing route changed |
| 2 | **character-attributes-service auth plumbing + internal twins.** Same `get_optional_user` + `app/visibility.py`. Add `GET /attributes/internal/{character_id}` and `GET /attributes/internal/{character_id}/passive_experience`, both `Depends(verify_internal_token)`, bodies identical to A1/A4 today. | Backend Developer | DONE | `services/character-attributes-service/app/auth_http.py`, `app/visibility.py` (new), `app/main.py` | — | as task 1 |
| 3 | **inventory-service auth plumbing + internal twins.** Same `get_optional_user` + `app/visibility.py`. Add `GET /inventory/internal/characters/{character_id}/items`, `GET /inventory/internal/characters/{character_id}/equipment`, `GET /inventory/internal/items/{item_id}` — `Depends(verify_internal_token)`, bodies identical to I1/I2/I3 today (equipment twin keeps `fast_slot_*` and `effective_damage`). Follow the service's existing `/internal/characters/...` naming. **Также сделано заранее (часть задачи #8, без изменения поведения):** `ItemBulkResponse` повышена до `PublicItemCard` + проекция `schemas.public_item_card(row)`, `/inventory/items/bulk` переведён на неё. | Backend Developer | DONE | `services/inventory-service/app/main.py`, `app/auth_http.py`, `app/visibility.py` (new) | — | as task 1; the equipment twin is byte-identical to `GET /inventory/{id}/equipment` |
| 4 | **skills-service auth plumbing.** Add `get_optional_user` to `auth_http.py` and an **async** `app/visibility.py` (`AsyncSession`, `await db.execute`) with the same semantics as §3.1. No internal twin — S1 keeps its path and gains `allow_jwt_or_service_token` in task 10. **Pass A:** предикат `main.require_character_skills_access` написан, но НЕ подключён к маршруту — ничего не отказывает. | Backend Developer | DONE | `services/skills-service/app/auth_http.py`, `app/visibility.py` (new) | — | `py_compile` passes; unit-level: NPC ⇒ True, missing id ⇒ 404, stranger ⇒ False |
| 5 | **Teach every anonymous caller (the 13 of §3.5).** Repoint each call site at the internal twin and send `X-Internal-Token` via the service's existing `_internal_token_headers()`. Exact list in §3.5. **Do not add any gate in this task.** Where a caller currently swallows the error with a WARNING, leave the swallow but make the log line name the twin URL. | Backend Developer | TODO | `services/battle-service/app/battle_engine.py`, `app/inventory_client.py`; `services/dungeon-service/app/http_clients.py`; `services/locations-service/app/main.py`, `app/crud.py`; `services/character-service/app/main.py`; `services/character-attributes-service/app/perk_evaluator.py`, `app/main.py`; `services/skills-service/app/main.py`; `services/user-service/main.py` | 1, 2, 3 | Every one of the 13 sites hits an `/internal/` path with the header; `grep` finds **no** remaining anonymous call to A1/A4/C1/C4/I1/I2/I3 from another service; `py_compile` passes in all six services |

### Pass B — gates and response thinning

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 6 | **character-service gates + thinning.** C1 `full_profile` → style A: new `schemas.PublicProfileResponse` (id, name, level, active_title, active_title_rarity, avatar), `response_model=None`, handler returns one of two explicitly-built models (§3.2 D4) — `currency_balance`, `stat_points`, `level_progress`, `attributes` **absent** for strangers. C3 `/public` → style A: `starting_attributes` + `starting_attributes_is_snapshot` absent for strangers; `granted_kit` stays public. C4 `short_info` → **remove `currency_balance` from the public body** (D7). C7 `post-history` → style A, `xp_earned` absent for strangers. C8 `/logs` → style B (403 «Эти данные доступны только владельцу персонажа»). C2/C5/C6/C9/C10/C11 untouched. | Backend Developer | DONE | `services/character-service/app/main.py`, `app/schemas.py` | 5 | Owner/admin bodies byte-identical to pre-change; guest body contains none of the private keys; missing id ⇒ 404 on every touched route; NPC id ⇒ full body for anyone; `py_compile` passes |
| 7 | **character-attributes-service gates.** A1, A2, A3, A4, A5 → style B (`get_optional_user` + `require_private_access`). Do **not** change `reconcile_perks` behaviour on A2 (D8). Admin routes `/attributes/admin/*` untouched. | Backend Developer | DONE | `services/character-attributes-service/app/main.py` | 5 | guest ⇒ 403, stranger ⇒ 403, owner ⇒ 200 unchanged, admin ⇒ 200, NPC ⇒ 200 for anyone, missing ⇒ 404 |
| 8 | **inventory-service gates + public equipment + public item card.** I1, I2 → style B. New `GET /inventory/{character_id}/equipment/public` → `List[schemas.PublicEquipmentSlot]`, anonymous, **`fast_slot_*` excluded at the query/projection level** (§3.4). Promote `ItemBulkResponse` to `PublicItemCard` and extract `schemas.public_item_card(row)`; use it in `/items/bulk` (no behaviour change) and in the new public equipment view (D5/D6). I3 `GET /inventory/items/{item_id}` → `response_model=schemas.PublicItemCard`. I5–I9 untouched; `item-detail` stays the owner's fat card. | Backend Developer | DONE | `services/inventory-service/app/main.py`, `app/schemas.py`, `app/crud.py` | 5 | `/equipment` 403s a stranger and returns the owner's current body unchanged; `/equipment/public` contains **no** `fast_slot_*` row and no `effective_damage` / `enhancement_*` / `socketed_gems` / `current_durability` / any `*_modifier`; exactly one projection function builds the public card; `py_compile` passes |
| 9 | **user-service: stop the gold leak on the user profile.** `_fetch_character_short` calls C4i (done in task 5); U1 `GET /users/{id}/profile` omits `character.currency_balance` unless `current_user` is the profile owner or `role in ("admin","moderator")`. `/users/me` keeps gold. | Backend Developer | DONE | `services/user-service/main.py`, `services/user-service/schemas.py` | 5 | stranger/guest response has no `currency_balance` key inside `character`; owner and admin do; `/users/me` unchanged; header coin counter still works |
| 10 | **skills-service: gate S1.** `GET /skills/characters/{id}/skills` swaps to `Depends(allow_jwt_or_service_token)`; `None` (service caller) ⇒ allow; a `UserRead` ⇒ `await can_view_private(...)` else 403. No caller changes (battle-service already sends the token). **Отклонение:** перед гейтом пришлось доделать хвост задачи #5 — `skills-service/app/main.py::get_active_experience` всё ещё читал A1 анонимно; переведён на A1i с `X-Internal-Token`. | Backend Developer | DONE | `services/skills-service/app/main.py` | 4, 5 | service token ⇒ 200, owner ⇒ 200, admin ⇒ 200, stranger ⇒ 403, guest ⇒ 401, NPC ⇒ 200, missing ⇒ 404 |
| 11 | **notification-service: close chat history.** `GET /notifications/chat/messages` requires `get_current_user_via_http`. Nothing else in `chat_routes.py` changes. | Backend Developer | DONE | `services/notification-service/app/chat_routes.py` | — | guest ⇒ 401 with a Russian message; authenticated ⇒ unchanged body |

### Pass C — frontend (minimum to keep today's UI correct)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 12 | **Fix the broken character-card navigation (§3.6 F1).** `<Link to="/profile">` is hardcoded, so clicking another player's character opens your own. Link only the viewer's own **active** character to `/profile`; render every other card as a non-interactive `<div>` with identical markup minus the hover/pointer affordance. Add the `TODO(FEAT-172)` comment. Do **not** invent a `/character/:id` route. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/UserProfilePage/CharactersSection.tsx` | — | Clicking someone else's character navigates nowhere; your own active character still opens `/profile`; Tailwind-only, correct at 360px; `npx tsc --noEmit` and `npm run build` pass |
| 13 | **Survive the thinner payloads (§3.6 F2, F3, F5, F6).** Make `xp_earned`, `currency_balance`, `stat_points`, `level_progress`, `attributes`, `starting_attributes`, `starting_attributes_is_snapshot`, `CharacterShort.currency_balance` optional in the TS types and guard every render site (`?? 0`, conditional spans). **Verify** — do not rewrite — that the passport modal renders correctly when `starting_attributes` is absent (`adapters.ts` already handles the null case for pre-FEAT-155 rows) and that nothing on the user profile or the NPC modal renders gold. **Отклонение:** `api/userProfile.ts` вообще не типизирован, а `CharacterShort` во фронтенде (`redux/slices/userProfileSlice.ts:77`) никогда не содержал `currency_balance` — менять нечего, проверено. `NpcProfileModal` золото не рендерит (тип `NpcDetail` без него). `IndicatorsPanel:33` уже был через `?? 0`. **Доработка по ревью (BLOCKER #1):** `api/items.ts::fetchItem` переведён с похудевшего публичного `GET /inventory/items/{id}` на админскую дверь `GET /inventory/admin/items/{id}` — иначе редактор предмета грузил тонкую карточку и следующим PUT затирал реальные данные. | Frontend Developer | DONE | `redux/slices/profileSlice.ts`, `api/characterLogs.ts`, `api/charactersPublic.ts`, `api/userProfile.ts`, `components/ProfilePage/PostHistoryTab/PostHistoryTab.tsx`, `components/ProfilePage/CharacterTab/CharacterPanel.tsx`, `components/ProfilePage/CharacterTab/IndicatorsPanel.tsx`, `components/CommonComponents/CharacterPassport/adapters.ts`, `components/pages/LocationPage/NpcProfileModal.tsx` | 6, 8, 9 | Owner's ProfilePage renders exactly as before; passport modal of another player's character opens with no console error and no stat block; `tsc --noEmit` + `npm run build` pass |
| 14 | **Chat history for guests (§3.6 F4).** `ChatPanel` must not dispatch `fetchMessages` when `isAuthenticated === false`; show a Russian empty state instead. Wrap the `chat/history` route in `<ProtectedRoute>`. No silent failures: a real chat error still shows a toast. **Отклонение:** `ChatHistoryPage.tsx` менять не пришлось — `ProtectedRoute` уводит гостя раньше, чем страница смонтируется. | Frontend Developer | DONE | `components/Chat/ChatPanel.tsx`, `components/Chat/ChatHistoryPage.tsx`, `components/App/App.tsx` | 11 | A logged-out visitor opening the chat widget sees the Russian prompt and **no** 401 toast; a logged-in user sees the chat unchanged; Tailwind-only, 360px-correct; `tsc --noEmit` + `npm run build` pass |

### Pass D — QA (mandatory; backend changed in 9 services)

Every QA task below must, for each touched endpoint, run the **five-viewer matrix** —
*guest / another player / owner / admin(moderator) / NPC(`user_id IS NULL`)* plus *missing id ⇒ 404* —
and must assert that a private field is **absent from `response.json()`** (`assert "currency_balance"
not in body`), never merely that it is falsy or unrendered. Each task also repairs the existing
anonymous call sites in that service's suite (~80 across the repo, §2.8): service-shaped tests move
to the internal twin, player-shaped tests get a dependency override.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 15 | **character-service tests.** Matrix for C1, C3, C4, C7, C8 + the two internal twins (missing header ⇒ 401, unset env ⇒ 503). Assert `currency_balance`/`stat_points`/`level_progress`/`attributes` absent on the guest `full_profile`, `starting_attributes` absent on a stranger's `/public`, `granted_kit` still present, `xp_earned` absent on a stranger's post history, `/logs` 403 for a stranger. Assert `short_info` never carries gold while the twin always does. **Сделано:** `app/tests/test_feat171_character_visibility.py` — 120 тестов (матрица гость/чужой/владелец/админ/модератор с правом и без/NPC + несуществующий id на C1, C3, C4, C7, C8, двойники C1i/C4i: нет заголовка ⇒ 401, чужой ⇒ 401, пустой секрет ⇒ 503, JWT админа двойник не открывает). Приватные ключи проверяются на ОТСУТСТВИЕ, класс `TestThePrivateKeysAreReallyAbsent` доказывает, что у владельца те же ключи есть (иначе `not in` проходил бы вхолостую). | QA Test | DONE | `services/character-service/app/tests/` | 6 | new tests pass; the whole service suite is green |
| 16 | **character-attributes-service tests.** Matrix for A1–A5 + twins. Repair `test_perks.py`, `test_regen.py`, `test_satiety.py`, `test_recalculate.py`, `test_stats_formulas.py`, `test_cumulative_stats.py`. **Сделано:** `app/tests/test_feat171_attributes_visibility.py` — 117 тестов (матрица на A1–A5 × 6 зрителей + NPC + 404 раньше 403, двойники A1i/A4i, тела двойника и владельца сравниваются побайтово, D8: `reconcile_perks` всё ещё вызывается на GET и чужой его не триггерит). Существующие тесты чинить не пришлось — их уже починил Backend Dev, вся сюита зелёная. | QA Test | DONE | `services/character-attributes-service/app/tests/` | 7 | as above |
| 17 | **inventory-service tests — including the belt hole.** Matrix for I1, I2, I2p, I3, I4 + three twins. **Dedicated regression test: `GET /inventory/{id}/equipment/public` returns no row whose `slot_type` starts with `fast_slot_`, on a character that has all four belt slots filled** — the FEAT-169 bypass must be provably closed. Assert the public slot dict has exactly `{slot_type, item}` and the public item card exactly `{id, name, description, image_url, rarity, type}`. Repair `test_equip_locking.py`, `test_npc_equipment.py`, `test_item_out_schemas_serve_stored_rows.py`. **Сделано:** `app/tests/test_feat171_inventory_visibility.py` — 103 теста. Регрессия пояса закрыта тремя способами: (1) все четыре быстрых слота заполнены и в `/equipment/public` нет ни одной строки `fast_slot_*`, (2) перехват SQL через `before_cursor_execute` доказывает, что отсечение идёт `NOT LIKE` в запросе, а не пост-фильтром, (3) `test_the_regression_assertion_really_bites` нейтрализует `crud.FAST_SLOT_LIKE_PATTERN` и требует, чтобы пояс снова потёк — иначе тест перестал что-либо проверять. | QA Test | DONE | `services/inventory-service/app/tests/` | 8 | as above, plus the belt regression test fails on the pre-fix code |
| 18 | **skills-service + user-service + notification-service tests.** S1 matrix incl. the service-token path; U1 gold absent for guest/stranger and present for owner/admin, `/users/me` unchanged; N1 401 for a guest. **Сделано:** `skills-service/app/tests/test_feat171_skills_visibility.py` (22), `user-service/tests/test_feat171_profile_gold.py` (15), `notification-service/app/tests/test_feat171_chat_history_auth.py` (14). В skills матрица гоняется через НАСТОЯЩИЙ `allow_jwt_or_service_token` (подменён только сетевой вызов в user-service), поэтому ветка «`None` = сервис» проверена с обеих сторон: сервисный токен проходит, гость без токена получает 401, а почти-верный токен не считается сервисным. | QA Test | DONE | `services/skills-service/app/tests/`, `services/user-service/tests/`, `services/notification-service/app/tests/` | 9, 10, 11 | as above |
| 19 | **Caller-side header tests (the FEAT-169 lesson).** For each of the 13 call sites in §3.5, assert on the real client function that the request went to the `/internal/` path **and** carried `X-Internal-Token` (`call.kwargs["headers"]["X-Internal-Token"]`). Six of these callers swallow errors with a WARNING, so "nothing crashed" proves nothing. **Сделано:** шесть файлов `test_feat171_outgoing_internal.py` (battle 20, dungeon 15, locations 25, character-service 10, char-attrs 22, skills 10) + проверки C4i в `user-service/tests/test_feat171_profile_gold.py`. У dungeon-, locations- и user-service таких тестов не было вовсе. Два вызова написаны прямо в теле эндпоинта (`locations.move_and_post`, `quick_move`) и ещё один в `char-attrs.upgrade_attributes` — у них нет клиентской функции, поэтому они закреплены разбором AST самих хендлеров (URL двойника + `headers=_internal_token_headers()`). **Уточнение к §3.5:** три чтения dungeon-service ошибку НЕ проглатывают — они превращают её в `HTTPException(502)`; сообщение при этом обвиняет соседний сервис, а не токен, поэтому заголовок всё равно проверяется по записанному запросу. | QA Test | DONE | `services/battle-service/app/tests/`, `services/dungeon-service/app/tests/`, `services/locations-service/app/tests/`, `services/character-service/app/tests/`, `services/character-attributes-service/app/tests/`, `services/skills-service/app/tests/`, `services/user-service/tests/` | 5 | every site asserted; a deliberately removed header turns the test red |
| 20 | **Predicate parity matrix.** One parametrised test per service (4 copies of `can_view_private`) proving identical behaviour on the same six inputs: missing id ⇒ 404, NPC ⇒ True, guest ⇒ False, stranger ⇒ False, owner ⇒ True, moderator-with-`characters:read` ⇒ True, and moderator **without** the permission ⇒ False. Guards against the copies drifting (§3.1 D1). **Сделано:** `test_feat171_predicate_parity.py` в четырёх сервисах, по 39 тестов в каждом, файлы отличаются только sync/async обёрткой. Ключевые строки матрицы — модератор БЕЗ `characters:read` ⇒ False и редактор С правом ⇒ False: они ловят подмену `and` на `or` в отдельной копии. | QA Test | DONE | `services/character-service/app/tests/`, `services/character-attributes-service/app/tests/`, `services/inventory-service/app/tests/`, `services/skills-service/app/tests/` | 6, 7, 8, 10 | identical assertions pass in all four services |

### Pass E — review

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 21 | **Final review.** *(Review #1 FAIL → 6 findings fixed → Review #2 **PASS**, see §5.)* Re-run `py_compile` in all nine backend services, the full pytest suites, `npx tsc --noEmit` and `npm run build`. **Live verification is mandatory:** as a guest, as another player, as the owner and as an admin, confirm through the gateway (curl / chrome-devtools) that (a) the private keys are absent from the JSON, (b) `/inventory/{id}/equipment/public` carries no belt row, (c) the owner's ProfilePage, the passport modal, the NPC modal, the location page, a battle and the login flow all still work with zero console errors. Verify Pass A landed before Pass B, that no new RBAC permission or migration was added, that response shaping is server-side everywhere, and that ISSUES.md entries fixed here (belt-through-equipment, gold leaks, `CharactersSection` link) are removed. | Reviewer | DONE | all of the above | 12–20 | PASS only with automated results **and** live verification recorded in §5 |

### Pass F — review fixes (from §5)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 22 | **Close the NPC-shop side door (§5 review #1, finding 3).** `GET /locations/npcs/{npc_id}/shop?character_id=X` was anonymous while calling `GET /attributes/internal/{X}` with `X-Internal-Token`: `discounted_buy_price` inverts back into `charisma` (live 20 → 19 ⇒ charisma 30). locations-service is now a *trusted proxy* to private attributes, so it needs the same viewer predicate as its siblings. Added `services/locations-service/app/visibility.py` (async copy of §3.1, fifth copy) and gated every locations-service route that answers with something computed from one named character's private state: shop (only when `character_id` is passed), `/npcs/{id}/quests`, `/quests/active`, `/action-gate/status`, `/npcs/{id}/dialogue` (only when `character_id` is passed). Viewer comes from the existing `get_optional_user`, so no frontend change. **Contract:** guest without `character_id` keeps the public shop window (base prices, no `discounted_buy_price` key); with `character_id` — 403 for a guest/stranger, 404 for a missing character, unchanged behaviour for owner/admin. No internal caller was touched: all cross-service traffic already goes to `/locations/*/internal/*`. | Backend Developer | DONE | `services/locations-service/app/visibility.py` (new), `app/main.py`, `app/tests/test_feat171_shop_gate.py` (new), `app/tests/test_charisma_discount.py`, `docs/services/locations-service.md` | 21 | guest/stranger ⇒ 403 and no `discounted_buy_price` in the body; `_fetch_charisma` is never awaited for an anonymous caller; owner/admin ⇒ 200 with the discount unchanged; missing id ⇒ 404; NPC (`user_id IS NULL`) ⇒ 200; `py_compile` + real import + full locations-service pytest green |
| 23 | **Give the admin item editor its fat route back, and decide `/equipment-rules` (§5 review #1, findings 1 and 6).** §3.4 claimed I3 has no frontend caller; it has one — `api/items.ts::fetchItem` behind the axios `baseURL`, feeding `ItemsAdminPage/ItemForm` and `RecipesAdminPage`. Thinning I3 made the edit form seed itself from a six-key card, and the following `PUT /inventory/items/{id}` wrote the form defaults back — editing any item zeroed its modifiers, price, `effects[]` and `damage_entries[]`. The internal twin cannot serve a browser (nginx 403s `/inventory/internal/`), so this is a **third view of one item**: **`GET /inventory/admin/items/{item_id}`**, `Depends(require_permission("items:read"))`, `response_model=schemas.Item` — the same permission that already guards the `/admin/items` route (`App.tsx:170`) and `GET /admin/items/{id}/conversions`, and the same body as the internal twin. `GET /inventory/items/{item_id}` stays the thin public card; the internal twin stays for services. **Finding 6 — `GET /inventory/{character_id}/equipment-rules` stays public**: it is reference data, not character data (the whole body is derived from class and subclass, both already published by `/characters/{id}/public`, `/short_info` and `/characters/list`; no number and no possession of the character appears in it). Only the error discipline is aligned with the rest of the feature — a missing `character_id` now answers 404 «Персонаж не найден» instead of 200 «no restrictions». Frontend repoints `fetchItem` at the new path (separate task). | Backend Developer | DONE | `services/inventory-service/app/main.py`, `app/tests/test_feat171_admin_item_route.py` (new), `docs/services/inventory-service.md` | 21 | guest ⇒ 401, player/moderator/admin **without** `items:read` ⇒ 403, anyone **with** it ⇒ 200; the body carries every field of `schemas.Item` (asserted against the schema, not a copied list) and is byte-identical to the internal twin; `GET /inventory/items/{id}` is still the six-key card; `/equipment-rules` still 200 for a guest and 404 for a missing character; `py_compile` + real import + full inventory-service pytest green |
| 24 | **Gate the battle log (§5 review #1, finding 2).** `GET /battles/battles/{id}/logs` and `.../logs/{turn_number}` had **no** auth dependency at all and are proxied by nginx, so a guest walking sequential `battle_id`s read `{"event":"pve_rewards","xp":30,"gold":5}` and `{"event":"skill_use","skill_id":9003}` — the XP, gold and skills §1 declares private. Added `services/battle-service/app/battle_visibility.py` (`can_view_battle_logs` / `require_battle_log_access`) and put both routes behind JWT + that predicate. **Who may still read:** a **participant** (owns a character in `battle_participants`, finished battles included), a **co-located spectator while the battle is still active** (`battles.location_id` — verbatim the rule of `GET /{battle_id}/spectate`, which the same page already uses to load the state these logs annotate), and **admin/moderator holding `characters:read`** — role alone is not enough, the same split as `can_view_private`. 404 «Бой не найден» before 403. **The spectator snapshot is a separate code path** (`main.py:1555` + `build_participant_info:305` + the WS push at `:5288` ship `attributes`/`skills`/`fast_slots` to any co-located player): not folded in — it needs a product decision on what a spectator should see — filed in `docs/ISSUES.md` (MEDIUM) with the note that the two rules must be narrowed **together**. No frontend change: `BattlePageBar.tsx` uses the default axios instance, which already attaches the Bearer token. | Backend Developer | DONE | `services/battle-service/app/battle_visibility.py` (new), `app/main.py`, `app/tests/test_feat171_battle_log_auth.py` (new), `docs/services/battle-service.md`, `docs/ISSUES.md` | 21 | guest ⇒ 401, outsider ⇒ 403, participant / co-located spectator / admin+perm ⇒ 200, moderator without `characters:read` ⇒ 403, spectator of a **finished** battle ⇒ 403, missing battle ⇒ 404; every rejection asserted to contain **none** of the log payload; `py_compile` + real import + full battle-service pytest green |
| 25 | **Stop `GET /users/{id}` handing out e-mail addresses, and fix the two user-service MINORs (§5 review #1: the pre-existing PII finding, #4 and #5).** **(a) PII:** `GET /users/{user_id}` had no auth and returned `UserRead`, i.e. a real person's `email`, to anyone; `GET /users/admins` returned every administrator's address in one anonymous request. New public base `schemas.UserPublicRead` = `{id, username, role, avatar, registered_at}`; `UserRead` now **extends** it with `email` alone. `/users/{id}` gained `get_optional_user` and serves the fat schema only to the account owner and to admin/moderator holding `users:read`; `/users/admins` serves the public one (its only consumer, notification-service's `get_admins()`, reads `id`). No internal twin needed — every cross-service caller (`character-service/app/main.py:2252,2369,2476`, `locations-service/app/crud.py:6892`) reads `username` only; every neighbouring user route checked for the same leak (`/users/all` → `UserPublicItem`, `/admin/list` → `require_admin`, `/users/me` → owner). 404 detail translated to Russian. **(b) §5 #4 inverted inheritance:** `UserProfileStrangerResponse` is now the base and `UserProfileResponse` extends it, so a future private field cannot leak by default; plus a defensive `.dict()` at the call site, because Pydantic v1 would keep a `CharacterShort` **instance** (and its gold) through a `CharacterShortPublic` field. **(c) §5 #5:** U1's gold rule is now `owner or (role in admin/moderator **and** characters:read)` — the `can_view_private` formula; a moderator whose permission is revoked no longer sees gold here while getting 403 on `/characters/{id}/full_profile`. | Backend Developer | DONE | `services/user-service/main.py`, `services/user-service/schemas.py`, `services/user-service/tests/test_feat171_review_fixes.py` (new), `tests/test_feat171_profile_gold.py`, `docs/services/user-service.md`, `docs/ISSUES.md` | 21 | guest / stranger / moderator-without-`users:read` ⇒ no `email` key at all (nor any other sensitive key); owner / admin / moderator-with-`users:read` ⇒ `email` present, so the `not in` assertions are not vacuous; `/users/admins` carries no `email`; the public card still carries `username` for the internal callers; moderator without `characters:read` ⇒ no `currency_balance` on U1, with it ⇒ present; both schema pairs asserted by inheritance **direction**; `py_compile` + real import + full user-service pytest green |

| 26 | **Close the three non-blocking residuals of review #2 (§5).** **(1) The fifth predicate copy joins the anti-drift net:** `test_feat171_predicate_parity.py` now exists in locations-service too — the same 39-test matrix, byte-identical to the skills-service file (the async shim is the only difference), so all five copies of `can_view_private` are pinned by the same assertions. **(2) The guest shop window omits the key instead of nulling it:** `schemas.NpcShopItemPublicRead` is now the base (id, npc_id, item_id, buy_price, sell_price, stock, is_active, item card, created_at) and `NpcShopItemRead` extends it with `discounted_buy_price` alone — same public-base inheritance direction as task 25, so a future private field on the personal price list cannot leak into the guest view by default. `GET /locations/npcs/{npc_id}/shop` is `response_model=None` and returns one of the two explicitly-built models (style A); the dict-vs-ORM row normalisation moved into `_shop_item_fields()` and is now driven by the schema's `__fields__` rather than a hand-copied field list. Both affected tests now assert **absence** (`"discounted_buy_price" not in body[0]`), not `is None`. **(3) The map is correct again:** all five `visibility.py` docstrings say "keep the **five** copies byte-identical" and list the five paths plus the per-service parity file; the same header was applied to all five parity tests, and §3.1 D1 carries an update note. | Backend Developer | DONE | `services/locations-service/app/tests/test_feat171_predicate_parity.py` (new), `services/locations-service/app/main.py`, `app/schemas.py`, `app/visibility.py`, `app/tests/test_feat171_shop_gate.py`, `app/tests/test_charisma_discount.py`, `services/{character,character-attributes,inventory,skills}-service/app/visibility.py`, the four existing `test_feat171_predicate_parity.py` | 21 | the locations parity matrix passes and **bites** (`and`→`or` in the locations copy ⇒ red, restored byte-exact by sha256); the guest shop body has no `discounted_buy_price` key at all; owner/admin discount unchanged; `py_compile` + real module import + the full suites of all five touched services green |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-19
**Result:** FAIL

The security core of this feature is **correct and provably works**. The five-viewer matrix,
the belt regression, the 404-before-403 ordering, the NPC passthrough, the internal twins and
the whole Pass A caller migration all verified live against a freshly recreated stack. The
failure is not in the gating — it is one **destructive collateral regression** (the admin item
editor) plus two live leaks of exactly the data §1 declares private that this feature left open.

---

#### Automated Check Results
- `npx tsc --noEmit` — **PASS** (exit 0, no output; run in a disposable `frontend` container)
- `npm run build` — **PASS** (exit 0, 3417 modules, 33.0 s)
- `py_compile` / module import — **PASS** (verified by Backend Dev per service; containers confirmed
  to carry the new code after `--force-recreate`: `visibility.py` present in all four services,
  `equipment/public` present in inventory-service)
- `pytest` — **PASS** as recorded in §6 (9 suites, 649 new tests, zero red). Not re-executed in full
  by the Reviewer; the live matrix below is an independent check of the same properties.
- `docker-compose config` — **PASS**
- Live verification — **PASS for the gates, FAIL overall** (see Issues Found)

#### Live Verification Results

Stack recreated with `docker compose up -d --force-recreate`; all 24 containers healthy and
confirmed to be running the new code (not a stale `--reload` image). Six viewers were used:
guest (no token), another player, the owner, an admin, a moderator **with** `characters:read`
and a moderator **with the permission explicitly denied** (`user_permissions.granted = 0`).
Target: character 18 (level 50, gold 105), temporarily reassigned to a disposable owner account.
All test accounts and the character's original `user_id` have been restored — see "Test data".

**1. Five-viewer matrix — the private keys are genuinely ABSENT, not null.**

| Route | guest | stranger | owner | admin | mod +perm | mod −perm |
|---|---|---|---|---|---|---|
| C1 `full_profile` | 200 thin | 200 thin | 200 full | 200 full | 200 full | 200 thin |
| C3 `/public` | 200 (no `starting_attributes`) | 200 | 200 full | 200 full | 200 full | 200 thin |
| C4 `short_info` | 200 no gold | 200 | 200 | 200 | 200 | 200 |
| C7 `post-history` | 200 no `xp_earned` | 200 | 200 +xp | 200 +xp | 200 +xp | 200 |
| C8 `/logs` | **403** | **403** | 200 | 200 | 200 | **403** |
| A1–A5 (5 routes) | **403** | **403** | 200 | 200 | 200 | **403** |
| I1 `items`, I2 `equipment` | **403** | **403** | 200 | 200 | 200 | **403** |
| I2p `equipment/public` | 200 | 200 | 200 | 200 | 200 | 200 |
| S1 `skills` | **401** | **403** | 200 | 200 | 200 | **403** |
| U1 `/users/{id}/profile` | 200 no gold | 200 no gold | 200 +gold | 200 +gold | 200 | 200 |
| N1 chat history | **401** RU | 200 | 200 | 200 | 200 | 200 |

Guest/stranger/moderator-without-permission bodies contain **none** of
`currency_balance`, `stat_points`, `level_progress`, `attributes`, `passive_experience`,
`active_experience`, `exp_to_next_level`, `starting_attributes`, `xp_earned`,
`effective_damage`, `enhancement_*`, `socketed_gems`, `current_durability`, `price`,
`total_gold_earned`. The same keys are present for owner/admin/mod+perm, which proves the
`not in` assertions are not passing vacuously. Exact guest `full_profile` body:
`{active_title, active_title_rarity, avatar, id, level, name}` — level is public as required.
The `characters:read` split is real: the same moderator flips from 200 to 403 on every hard-gated
route when the permission is denied.

**2. The belt hole is provably closed (the headline regression of §2.4.1).**
Character 19 has `fast_slot_1..4` filled plus `main_weapon` and `cloak` in the DB.
`GET /inventory/19/equipment/public` as a **guest** returns 9 slots, **zero** `fast_slot_*` rows,
and shows the two worn items as
`{"id":7,"name":"Плащ вора","description":"Тёмный плащ…","image_url":null,"rarity":"common","type":"cloak"}`
— name + description + icon + rarity and nothing else, exactly per Q2. The private
`GET /inventory/19/equipment` returns **403 «Эти данные доступны только владельцу персонажа»**.
The owner's own `/equipment` still returns all 19 rows including `fast_slot_1..10`, unchanged.

**3. Owner and admin are untouched.** Owner `full_profile` still carries gold 105, `stat_points`,
`level_progress` and `attributes`; `/users/me` still returns `character.currency_balance = 105`,
so the header coin counter keeps working through the C4i twin. Twenty-one owner-side reads
(profile, attributes, perks, rest-status, inventory, equipment, equipment-rules, fast_slots,
active-buffs, skills, titles, logs, post-history, cumulative_stats, professions, crafting recipes,
gathering-skills, chat, `/users/me`) all returned 200. Browser: `/profile` renders with gold 105
visible and **zero** HTTP ≥ 400.

**4. 404 before 403 — no existence oracle within the gate.** Character id 999999 returns **404
«Персонаж не найден»** on all 19 character-scoped routes, for guest, stranger and owner alike;
403 is never reached for a missing row. Note the residual, which is a deliberate design choice and
not a defect: for a guest an *existing* private character answers 403 while a missing one answers
404, so existence is still distinguishable — acceptable here because `GET /characters/list`
publishes the roster anyway. Two untouched routes answer 200 for a missing id
(`/characters/{id}/titles`, `/inventory/{id}/equipment-rules`) — pre-existing, noted below.

**5. NPCs and mobs stay public (Q6).** All 17 character-scoped reads on NPC 33 (`user_id IS NULL`)
return 200 to a guest, including `/attributes/33`, `/attributes/33/perks`, `/inventory/33/items`
and `/inventory/33/equipment`. The bestiary and NPC modal surfaces are intact.

**6. nginx blocks every new internal path.** All seven twins
(`/characters/internal/{id}/full_profile`, `/characters/internal/{id}/short_info`,
`/attributes/internal/{id}`, `/attributes/internal/{id}/passive_experience`,
`/inventory/internal/characters/{id}/items`, `/inventory/internal/characters/{id}/equipment`,
`/inventory/internal/items/{id}`) return **403** through the gateway for both a guest and an admin
JWT. The prefix `location` blocks that cover them are `nginx.conf:133 / :250 / :311` and
`nginx.prod.conf:154 / :269 / :327`; no regex `location` can pre-empt them (all require digits or a
literal segment).

**7. Pass A really works — the engines were exercised, not assumed.** The *real* cross-service
client functions were invoked **inside their own containers**, with the container's real
`INTERNAL_SERVICE_TOKEN`, against the live gated services:

```
battle_engine.fetch_full_attributes(18)        -> OK, 52 keys (charisma=30)   [A1i]
battle_engine.fetch_weapons(18)                -> OK, fat item, effective_damage=18.0  [I2i + I3i]
inventory_client.get_equipment_durability(18)  -> OK                          [I2i]
inventory_client.get_item(1)                   -> OK, 80 keys, damage_entries present  [I3i]
skills_client.character_skills(18)             -> OK, n=1                     [S1 service token]
dungeon http_clients.get_character_items(18)   -> OK                          [I1i]
dungeon http_clients.get_character_attributes(18) -> OK, 52 keys              [A1i]
```

This is the decisive proof that the two-pass law was respected and that battles and dungeons will
not fight blind. Supporting evidence: a 40-minute sweep of **all 13 service logs** found **zero**
401/403/500 in locations-service, battle-service, dungeon-service, party-service,
battle-pass-service and autobattle-service. Every 401/403 in the logs traces to a Reviewer probe.

**8. The three inline call sites QA could only pin with an AST walk are genuinely covered.**
`locations.move_and_post`, `locations.quick_move` and `char-attrs.upgrade_attributes` have no
client function, so an AST assertion on the handler body is the right instrument. Independently
corroborated at runtime: locations-service and character-attributes-service produced **no**
401/403 against the newly gated routes during the whole session, which they would have if any of
the three were still anonymous.

**9. Frontend.** `tsc --noEmit` and `npm run build` both exit 0. F1 (CharactersSection link fix),
F2/F3/F5/F6 (optional types + guarded renders) and F4 (guest-safe chat) are implemented as
designed; no `React.FC`, no `any`, no new `.jsx`, no new SCSS, responsive at 360 px, and errors for
authenticated users still reach a toast. Browser: a guest visiting `/post-history/18`, `/bestiary`,
`/world`, `/location/1`, `/players`, `/user-profile/49` produces **no 403 and no 500** — the only
recurring 401 is the pre-existing `notifications/messenger/unread-count` poll, which is unrelated
to this feature.

**10. `GET /attributes/{id}/perks` still writes on read.** Confirmed live (D8, deliberate). The
open ISSUES.md entry for it is intact and was **not** silently closed — correct.

**ISSUES.md bookkeeping verified:** the belt-through-equipment entry and the gold-leak entry are
marked DONE with an accurate "Исправлено" note, the `CharactersSection` navigation entry is gone,
the `reconcile_perks` write-on-GET entry remains open, and a new LOW entry was added for the
English 401 string in notification-service. All correct.

---

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/inventory-service/app/main.py:294-302` + `services/frontend/app-chaldea/src/components/ItemsAdminPage/ItemForm.tsx:213-227` (via `src/api/items.ts:67-70`, baseURL `src/api/client.ts:19`) | **BLOCKER — destructive admin regression.** §3.4 claims I3 has "No FE caller today (verified)"; that verification is wrong — `fetchItem()` calls `GET /inventory/items/{id}`, the URL is just hidden behind the axios `baseURL`. Live: an **admin** now receives only `{id,name,description,image_url,rarity,type}`. `ItemForm` seeds the edit form with `{...initialState(String(loaded.item_type)), ...loaded}`; `item_type` is `undefined`, and the thin keys do not even match the form's names (`type`/`rarity`/`image_url` vs `item_type`/`item_rarity`/`image`). Every modifier, `price`, `effects[]` and `damage_entries[]` falls back to the `initialState` default, and the subsequent `PUT /items/{id}` writes those defaults back — **editing any item silently zeroes its real data.** Needs an admin-authenticated fat route (the internal twin is unusable: nginx 403s `/inventory/internal/`) and `fetchItem` repointed at it. | Backend Developer + Frontend Developer | FIX_REQUIRED |
| 2 | `services/battle-service/app/main.py:3543`, `:3559` | **BLOCKER against §1's acceptance criteria — guest-readable XP, gold and skills.** `GET /battles/battles/{id}/logs` and `.../logs/{turn}` have **no auth dependency at all** and are proxied by nginx (only `/battles/internal/` is denied). Verified live with **no token**: battle 1 returns `{"event":"pve_rewards","xp":30,"gold":5,"items":[]}` and battle 11 returns `{"event":"skill_use","who":21,"skill_id":9003,"kind":"attack"}`. `battle_id` is a small sequential integer, so the whole history is enumerable. This is exactly the data §1 lists as private (опыт, деньги, навыки), reachable by a guest. Pre-existing and consciously excluded by §2.2 ("battle-service — do not touch"), so **PM must decide**: fold a participant/spectator gate into FEAT-171, or accept the criterion as unmet and raise it as the immediate follow-up. It cannot simply go unrecorded. | Backend Developer (PM decision on scope) | FIX_REQUIRED |
| 3 | `services/locations-service/app/main.py:2668` (`_fetch_charisma`), `:2694`, `:2701` (`get_npc_shop`) | **HIGH — the new gate is bypassed through a trusted proxy.** `GET /locations/npcs/{npc_id}/shop?character_id=X` has no auth and no ownership check, yet now calls the hardened `GET /attributes/internal/{X}` **with `X-Internal-Token` on an anonymous caller's behalf** and returns `discounted_buy_price`. Verified live as a **guest**: `buy_price` 20 → `discounted_buy_price` 19, which inverts to `charisma = 30` (confirmed against the owner's own `/attributes/18`). FEAT-171 closed A1's front door and left this side door open — and made it *more* effective, because locations-service now holds the token. Fix: require JWT + `verify_character_ownership(character_id)` before honouring `character_id`, else return undiscounted prices. | Backend Developer | FIX_REQUIRED |
| 4 | `services/user-service/schemas.py:188-195` | **MINOR — inverted inheritance direction.** Everywhere else the public schema is the base and the fat one extends it, so a new field cannot leak by default. `UserProfileStrangerResponse(UserProfileResponse)` inherits **every** field of the fat model and only narrows `character`; any private field added to `UserProfileResponse` later is auto-inherited by the stranger response. Safe today only because `_fetch_character_short` returns a **dict** — if it is ever changed to return a `CharacterShort` instance, Pydantic v1's `isinstance` shortcut keeps the subclass **and its `currency_balance`**, silently. Invert the pair (or add `.dict()` at the call site plus a comment). | Backend Developer | FIX_REQUIRED |
| 5 | `services/user-service/main.py:1663-1665` | **MINOR — inconsistent privilege rule.** U1 gates gold on `role in ("admin","moderator")` alone, while `visibility.can_view_private` additionally requires `characters:read`. A moderator whose permission is revoked still sees gold here but not on `/characters/{id}/full_profile`. Verified live (the mod−perm account gets 403 on the C-series yet is not filtered on U1). Align U1 with the predicate. | Backend Developer | FIX_REQUIRED |
| 6 | `services/inventory-service/app/main.py:808-811` | **MINOR — the one character-scoped GET the feature never decided on.** `GET /inventory/{character_id}/equipment-rules` is fully anonymous, with no visibility gate and no 404/403 discipline (a missing id returns 200). It exposes the character's class/subclass and doubles as an existence probe. Class is plausibly public — but it should be an explicit line in §3.4, not an omission. | Architect (decision) + Backend Developer | FIX_REQUIRED |

#### Pre-existing issues noted (do NOT block this feature — for `docs/ISSUES.md`)

- **`GET /users/{user_id}` returns `email` to anonymous callers** — `services/user-service/main.py:2254-2259`, no auth dependency, `UserRead` includes `email` (`schemas.py:50-59`). Verified live: `GET /users/7` with no token returns a real e-mail address. Listed as U5 "auth: none" in §2.2 and outside this feature's written scope, but it is PII and worse than anything FEAT-171 closed. Two reviewed handlers call it service-to-service, so it needs an internal twin or an e-mail-free public schema rather than a flat gate. Priority HIGH.
- **Anonymous per-character reads in locations-service** — `main.py:3059` `/quests/active?character_id=`, `:3036` `/npcs/{id}/quests?character_id=`, `:3798` `/action-gate/status?character_id=`, `:2501` `/npcs/{id}/dialogue?character_id=`. Quest progress and gate state of any character, to a guest. Priority MEDIUM.
- **Spectator snapshot ships the full private block** — `services/battle-service/app/main.py:1555` and the WS push at `:5288`: auth is JWT + "you have a character at this location", **not** participation. `build_participant_info` (`:305`) includes `attributes`, `skills` with levels, `fast_slots` and `equipment_durability`. Any player can walk to a location and read another player's full build. Priority MEDIUM — needs a product decision on what a spectator should see.
- **`GET /battles/character/{id}/in-battle`** (`main.py:3570`) — docstring says "internal", but the path is not under `/internal/`, so it is gateway-reachable and discloses battle presence + `battle_id`. Combined with issue #2 it is an enumeration handle. Priority LOW.
- **`GET /inventory/characters/{id}/gathering-skills`** (`inventory main.py:2313`) — JWT but no ownership check, so any logged-in player reads another character's gathering ranks/xp. Deliberate per FEAT-128; if it stays, list it in the public layer. Priority LOW.
- **`/skills/{skill_id}/resolved`** (`skills main.py:514-533`) — admin/moderator bypass on role alone, without `characters:read`; now the looser of two sibling paths. Priority LOW.
- **`notification-service/app/chat_routes.py:84-91`** — `_get_optional_user` now has zero call sites and is subtly broken (binds the `auto_error=True` scheme). Dead code, safe to delete.
- **`GET /attributes/{id}/perks` writes on GET** — confirmed still present, correctly recorded as an open ISSUES.md entry, correctly out of scope per D8.

#### Observations (no action required)

- **§2.2's claim that base stats are absent from A1's response schema is wrong.** `GET /attributes/{id}` returns `strength`, `agility`, `endurance`, `intelligence`, `luck` and `charisma` (52 keys, verified live). Harmless now that A1 is hard-gated — but it is precisely why issue #3 works, and the field matrix in §2.3 should be corrected.
- **Stranger and owner `full_profile` are not the same shape minus keys** — `PublicProfileResponse` adds `id`, which `FullProfileResponse` does not have. Additive and harmless.
- **A stranger's `full_profile` still does the owner's expensive work** — `_build_full_profile` makes two internal HTTP calls and runs `crud.check_and_update_level` (a **DB write**) before the six public fields are projected out. An anonymous request can therefore force a level recalculation for any character id. Pre-existing shape, but the stranger branch could read straight from the `characters` row.
- **`get_optional_user` swallows an invalid/expired token and returns `None`**, so an owner with a stale JWT gets 403 rather than 401 and the client has no refresh signal.
- **`PublicItemCard` is an alias of `ItemBulkResponse`, not a distinct model** — a field added to the bulk card for one caller silently lands in the public equipment view too. The single-projection rule (D5/D6) is otherwise honoured exactly: `schemas.public_item_card()` is the only row→card mapping in the service.
- **There is no guest UI surface today.** A logged-out visitor is bounced to the login screen on every interior route (pre-existing; no page component was touched by this feature), so F4's Russian chat prompt is defensive rather than user-visible right now. It is correctly implemented for when the public pages of FEAT-172 land.

#### Test data (review #1)

All review data removed: the five disposable accounts (ids 49–53) deleted, the
`user_permissions` deny row deleted, `characters.id = 18` restored to `user_id = 7` with its
original level 50 and location 15, `users.current_character` cleared, temporary scripts removed
from the battle-service and dungeon-service containers, no `*-run-*` containers left behind.
No commits were made; the working tree is exactly as the implementers left it.

---

### Review #2 — 2026-09-20
**Result:** PASS

All six findings from review #1 are fixed, plus two PII leaks the implementers found on their own
initiative. Everything was re-verified live on a freshly recreated stack with a fresh set of six
viewers; nothing from review #1 regressed. **Task 21 (Final review) is DONE.**

#### Automated Check Results
- `py_compile` — **PASS** on every changed Python file (locations `main.py` + `visibility.py`,
  `battle_visibility.py` + battle `main.py`, inventory `main.py`, user-service `main.py` + `schemas.py`)
- `pytest` — QA files exist for every fix and were run by the implementers; the live matrix below is
  an independent check of the same properties
- `docker-compose config` — **PASS**
- Containers confirmed to carry the new code after `--force-recreate`
  (`inventory/main.py` has `admin/items`, `battle_visibility.py` and `locations/visibility.py` present)
- Live verification — **PASS**, including the browser click-through review #1 asked for

#### Live Verification Results

**FIX 1 — the item now has three doors, one audience each.** Verified on item 39
(«Броня Скитальца», 80 keys, 18 non-zero numeric fields, `strength_modifier` 1000):

| Door | guest | stranger | owner | admin | mod+perm | mod−perm |
|---|---|---|---|---|---|---|
| `/inventory/admin/items/39` | 401 | 403 | 403 | 200 (80 keys) | 200 | 200 |
| `/inventory/items/39` (public) | 200 (6 keys) | 200 | 200 | 200 | 200 | 200 |
| `/inventory/internal/items/39` | 403 | 403 | 403 | 403 | 403 | 403 |

The admin body carries 14 non-zero `*_modifier` fields plus `price`, `effects` and `damage_entries`;
the public body is exactly `{id, name, description, image_url, rarity, type}`. Missing item on the
admin door → 404 (after the 401/403, so no oracle). `items:read` is permission **id 6**, already
present in `0006_add_rbac_tables.py` — **no migration and no `TestAdminAutoPermissions` seed row are
required**, CLAUDE.md §10.13 is not triggered. Note the audience split is correct but worth stating:
the admin door is gated on `items:read`, so a moderator without `characters:read` still opens it —
that is right, it is an item route, not a character route.

**The browser click-through the frontend dev could not do — done, and it is the decisive proof.**
Logged in as admin, opened `/admin/items`, clicked «Изменить» on row 39, and read the form inputs
back out of the DOM:

```
name=Броня Скитальца  price=0  item_level=15
strength_modifier=1000  agility_modifier=300  max_durability=100  health_modifier=300
```

The real fat values are in the form — under the old thin card these were all `undefined`/defaults.
Then clicked «Сохранить» (no HTTP ≥ 400, no console error, returned to the list with the row still
«Броня / Средняя броня / Редкий») and re-read the item through the admin door:
**`AFTER: 80 keys` / `DIFF: NONE`.** The destructive regression is gone end-to-end, in the browser,
not just by curl. Item 39 verified untouched in the DB afterwards (`item_level` 15,
`strength_modifier` 1000).

**FIX 2 — battle logs.** `GET /battles/battles/{id}/logs` verified on battles 1 and 11:
guest **401**, stranger **403**, a logged-in non-participant **403**, moderator **without**
`characters:read` **403**, admin and moderator **with** it **200**, missing battle **404**.
The `pve_rewards {xp, gold}` and `skill_use {skill_id}` events that a guest read in review #1 are now
unreachable without a token. `battle_visibility.py` checks 404 before 403, checks participants before
the spectator rule, closes the spectator window once `status` leaves `pending`/`in_progress`, and
uses the **same** `role ∧ characters:read` formula as `visibility.py`.

**Judgement on the spectator snapshot being left out:** *acceptable for this feature.* The snapshot
(`main.py:1555`, `build_participant_info`, the WS push) is a different audience from the log route —
authenticated, location-bound and live-battle-only — and narrowing it needs a product decision about
what a spectator should legitimately see. Crucially it is **recorded, not dropped**: a new ISSUES.md
entry describes the exact fields (`attributes`, `skills` with levels, `fast_slots`,
`equipment_durability`) and explicitly warns that the log gate deliberately mirrors the `/spectate`
rule, so the two must be narrowed **together** or the spectator's log panel breaks. That is the right
call and the right note.

**FIX 3 — the locations side doors are shut.** With `character_id` supplied: guest **403**,
stranger **403**, moderator without the permission **403**, owner/admin/mod+perm **200** — on the NPC
shop, `/quests/active`, `/action-gate/status`, NPC quests and the NPC dialogue route. The gate runs
**before** `_fetch_charisma`, so no internal attribute call is made on an unauthorised caller's
behalf. The charisma oracle is dead: a guest can no longer obtain a discount at all, while the owner
still gets `discounted_buy_price = 19` on a `buy_price` of 20. The **public shop window stayed open**
for everyone without `character_id` (200 for all six viewers) — no guest page was broken. The three
newly-gated routes all take `character_id` as a *required* parameter, so there was never an anonymous
call to regress.

**Judgement on `client/details` being left open:** *correct.* I verified in review #1 that
`PlayerInLocation` carries only id/name/avatar/level/class/race/title/user_id — no private field
crosses it. The new ISSUES.md entry is honest about the real residual (an anonymous caller can name
someone else's `character_id` and hasten `finalize_due_sessions`), and correctly notes it is
idempotent, discloses nothing, and that gating it would take the location page away from guests. LOW
is the right severity.

**FIX 4/5 — user-service.** Gold on `/users/{id}/profile` now follows the permission, not the role:
guest **no key**, stranger **no key**, moderator **without** `characters:read` **no key**, owner /
admin / moderator **with** it → key present. Inheritance is public-base everywhere now
(`UserPublicRead → UserRead`, `CharacterShortPublic → CharacterShort`,
`UserProfileStrangerResponse → UserProfileResponse`), which closes the "a future private field leaks
by default" hazard I raised, and the added `.dict()` is at the right call site — it defuses exactly
the Pydantic-v1 `isinstance` short-circuit that would otherwise have carried a gold-bearing
`CharacterShort` through a `CharacterShortPublic`-typed field with no error.

**EXTRA — both PII leaks closed.** `GET /users/7`: the `email` **key is absent** for guest, stranger
and even a moderator; only the account owner and an admin/moderator with `users:read` receive it
(verified: the admin sees `email`, everyone else's body is
`{avatar, id, registered_at, role, username}`). `GET /users/admins`, which anonymously returned
**every administrator's e-mail address**, now returns the same public shape for all six viewers.
No internal caller regressed — all four cross-service readers of `/users/{id}` take only `username`,
which `UserPublicRead` still carries.

**FIX 6 — `equipment-rules`.** Public for all six viewers (the decision), and a missing character now
returns **404** like every other route.

**No regression from review #1.** Re-ran the core matrix: C1 `full_profile` (guest/stranger/mod−perm
6 keys, owner/admin/mod+perm 9), `/logs`, `/attributes/{id}`, `/inventory/{id}/items`,
`/inventory/{id}/equipment` (owner still 19 rows including the belt),
`/inventory/{id}/equipment/public` (9 rows, no belt, public to all), `/skills/.../skills`, chat
history — all exactly as in review #1. NPC 33 still fully public to a guest on attributes, items,
equipment and `short_info`. **Zero 5xx in any of the ten services' logs.**

**Five predicate copies agree.** The three sync copies are byte-identical; the two async twins
(skills-service, locations-service) differ only in `async def` / `await db.execute()` /
`AsyncSession` and the docstring — identical constants, identical SQL, identical branch order, and
identical Russian 403/404 strings.

**ISSUES.md bookkeeping verified.** The e-mail entry is struck through with an accurate
"Исправлено" note; the spectator snapshot and the `client/details` residual are filed as new entries
with correct severities and honest reasoning; earlier FEAT-171 entries remain correctly marked.

#### Residual notes (non-blocking — do not hold the feature)

| # | File:line | Note |
|---|---|---|
| 1 | `services/locations-service/app/tests/` | **The fifth `can_view_private` copy is not in the parity matrix.** `test_feat171_predicate_parity.py` exists in character-service, char-attrs, inventory and skills, but not locations-service. The module docstring names tests as the enforcement mechanism for the copy-paste, so the newest copy is the one outside it. Behaviour is covered indirectly by `test_feat171_shop_gate.py`; adding the async parity file would close the loop. Worth a follow-up, not a blocker. |
| 2 | `services/locations-service/app/main.py:2716` docstring | The guest shop window ships `discounted_buy_price: null` rather than omitting the key (`NpcShopItemRead.discounted_buy_price: Optional[int] = None`, plain `response_model`). **No value leaks** — `null` is not invertible — but the docstring and the fix report both say "no key at all". One kwarg or a doc correction. |
| 3 | `character-service`, `character-attributes-service`, `inventory-service` `app/visibility.py:1,3-4` | Docstrings still say "keep the **four** copies" and do not list locations-service. There are five. Cosmetic, but it is the only map a maintainer has. |
| 4 | `battle_visibility.py:66-73` | 403-vs-404 remains an existence oracle for an *authenticated* caller walking sequential `battle_id`s. Consistent with the rest of the feature and leaks no content; noted only because the `visibility.py` docstring claims "never reveal existence". |

Everything else from review #1's "Pre-existing issues noted" list stands as filed in ISSUES.md.

#### Test data (review #2)

Removed: the five disposable accounts (ids 54–58) deleted, the `user_permissions` deny row deleted,
`characters.id = 18` restored to `user_id = 7` (level 50, location 15), `users.current_character`
cleared. Item 39 confirmed byte-identical after the browser save (`DIFF: NONE`, and
`item_level = 15` / `strength_modifier = 1000` re-checked directly in MySQL). No leftover containers.
No commits.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-19 18:30 — PM: фича создана (публичный профиль + приватные данные), запускаю анализ
[LOG] 2026-09-19 18:35 — Analyst: начал анализ, собираю карту всех чтений данных персонажа по 13 сервисам
[LOG] 2026-09-19 18:55 — Analyst: найдено анонимных чтений: 11 в character-service, 5 в char-attrs, 5 в inventory, 1 в skills, 3 в user-service, 1 в notification (история чата)
[LOG] 2026-09-19 19:05 — Analyst: обнаружена регрессия FEAT-169 — GET /inventory/{id}/equipment анонимно отдаёт и быстрые слоты (fast_slot_1..4) целиком, гейт пояса обходится одним запросом; добавлено в ISSUES.md
[LOG] 2026-09-19 19:10 — Analyst: обнаружена утечка золота через GET /users/{id}/profile (CharacterShort.currency_balance) и GET /characters/{id}/short_info; добавлено в ISSUES.md
[LOG] 2026-09-19 19:20 — Analyst: карта фронтенда — страницы «чужой профиль персонажа» НЕТ вообще, ProfilePage всегда читает свой character.id; часть точек входа из §1 не существует или сломана
[LOG] 2026-09-19 19:25 — Analyst: обнаружен баг навигации — UserProfilePage/CharactersSection.tsx:57 ведёт на «/profile» (свой профиль) вместо профиля выбранного персонажа; добавлено в ISSUES.md
[LOG] 2026-09-19 19:35 — Analyst: 13 межсервисных вызывающих ходят в гейтируемые маршруты без токена — нужен порядок в два прохода, как в FEAT-169; ~80 анонимных вызовов в тестах станут красными
[LOG] 2026-09-19 19:40 — Analyst: анализ завершён — затронуто 9 сервисов + фронтенд, миграций не требуется; 7 вопросов к пользователю в §2.12
[LOG] 2026-09-19 19:50 — PM: решения по Q1–Q7 зафиксированы в §1; объём — бэкенд-гейты + минимум фронтенда, новая публичная страница персонажа вынесена в отдельную фичу
[LOG] 2026-09-19 19:55 — Architect: начал проектирование, опираюсь на матрицу полей и таблицы вызывающих из §2
[LOG] 2026-09-19 20:10 — Architect: спроектирован общий предикат can_view_private (404 при отсутствии, владелец, админ/модератор по characters:read, NPC с user_id IS NULL = публичен) — по копии в 4 сервисах, согласованность держится параметризованным тестом-матрицей, а не общим пакетом
[LOG] 2026-09-19 20:15 — Architect: get_optional_user добавляется в character-service, char-attrs, inventory и skills; JWT уже летит с каждым запросом фронтенда, поэтому владелец получает прежние ответы без единой правки клиента
[LOG] 2026-09-19 20:25 — Architect: выбраны три стиля закрытия — тонкий 200 по optional-auth для анкетных маршрутов, жёсткий 403 для инвентаря/перков/навыков/атрибутов/логов, internal-двойники для сервисов; два ответа на одном пути делаются через response_model=None и явную сборку модели, чтобы приватные поля ОТСУТСТВОВАЛИ в JSON, а не были null
[LOG] 2026-09-19 20:30 — Architect: публичная карточка предмета — это уже существующая ItemBulkResponse (id, name, description, image_url, rarity, type); она объявлена единственным публичным документом предмета, поэтому модалка паспорта не меняется вовсе
[LOG] 2026-09-19 20:35 — Architect: дыра с поясом закрывается двумя способами сразу — /inventory/{id}/equipment уходит под гейт, а новый /equipment/public отфильтровывает fast_slot_* на уровне запроса; золото уходит из short_info и из профиля игрока, для /users/me заведён internal-двойник с балансом
[LOG] 2026-09-19 20:40 — Architect: granted_kit решено оставить ПУБЛИЧНЫМ — это список id выданных предметов (имена резолвятся уже тонким bulk), то есть запись о вступлении, а не характеристики; starting_attributes закрыт, как и просил пользователь
[LOG] 2026-09-19 20:45 — Architect: зафиксирован закон двух проходов — сначала двойники и обучение 13 вызывающих, потом гейты; порядок вынесен в критерий приёмки и в чек-лист ревью
[LOG] 2026-09-19 20:50 — Architect: проектирование завершено — 21 задача (11 backend, 3 frontend, 6 QA, 1 review), 7 новых internal-маршрутов, 1 новый публичный маршрут, миграций и новых разрешений нет; два продуктовых вопроса (открытый каталог предметов, публичность цифр NPC) вынесены в §3.9
[LOG] 2026-09-19 21:10 — Backend Dev: начал задачу #5 (Pass A) — перевожу вызывающих в battle, dungeon, locations и user-service на internal-двойники
[LOG] 2026-09-19 21:35 — Backend Dev: переведено 12 вызовов из §3.5 (battle ×4, dungeon ×2, locations ×5, user ×1) на пути /attributes/internal, /inventory/internal и /characters/internal с X-Internal-Token; гейты не трогал
[LOG] 2026-09-19 21:40 — Backend Dev: найдены два вызывающих СВЕРХ списка §2.7, которые тоже сломались бы на Pass B — dungeon-service `get_character_attributes` (http_clients.py:164 → A1) и battle-service `skills_client.get_item` (skills_client.py:137 → I3); переведены на двойники, отмечено как отклонение от §3.5
[LOG] 2026-09-19 21:50 — Backend Dev: у вызывающих с проглоченной ошибкой лог-строка теперь называет URL двойника (locations `_read_current_stamina`, `_fetch_character_brief_map`, `_fetch_charisma`, user-service `_fetch_character_short` — там WARNING раньше вообще не было)
[LOG] 2026-09-19 22:05 — Backend Dev: задача #5 завершена — 8 файлов кода + 3 теста с устаревшими URL; pytest зелёный: battle 763, dungeon 155, locations 1354, user 586; документация battle/locations/user обновлена
[LOG] 2026-09-19 21:10 — Backend Dev: начал задачи #1 и #2 (Pass A, character-service и character-attributes-service) — только обвязка и internal-двойники, ни одного гейта
[LOG] 2026-09-19 21:25 — Backend Dev: задача #1 завершена — в character-service добавлены OAUTH2_SCHEME_OPTIONAL + get_optional_user, app/visibility.py (копия §3.1, побайтово совпадает с inventory-service), двойники GET /characters/internal/{id}/full_profile и /internal/{id}/short_info; тела вынесены в общие хелперы _build_full_profile / _build_short_info, чтобы не разошлись с публичными маршрутами
[LOG] 2026-09-19 21:35 — Backend Dev: задача #2 завершена — в character-attributes-service добавлены те же get_optional_user и visibility.py, двойники GET /attributes/internal/{id} и /internal/{id}/passive_experience через хелперы _build_full_attributes / _build_passive_experience
[LOG] 2026-09-19 21:45 — Backend Dev: часть задачи #5 по моим сервисам — character-service читает A1i и A4i с X-Internal-Token, char-attrs читает C1i из perk_evaluator (уровень и золото) и из POST /{id}/upgrade; анонимных вызовов между этими двумя сервисами не осталось
[LOG] 2026-09-19 21:50 — Backend Dev: починены две устаревшие проверки — sweep в test_internal_auth.py запрещал любой закрытый GET (теперь исключение для /attributes/internal/ и двойники явно перечислены в ожидаемых), а test_outgoing_internal_headers_feat170 требовал отсутствия заголовка на чтениях перков (теперь требует двойник и заголовок)
[LOG] 2026-09-19 22:00 — Backend Dev: проверки зелёные — py_compile и реальный импорт модулей в контейнерах, pytest в Docker: character-service 1076 passed / 1 skipped, character-attributes-service 478 passed / 2 skipped / 1 xpassed
[LOG] 2026-09-19 21:20 — Backend Dev: начал задачи #3 и #4 (Pass A: inventory-service и skills-service), гейты в этом проходе не ставлю
[LOG] 2026-09-19 21:35 — Backend Dev: добавлены get_optional_user + OAUTH2_SCHEME_OPTIONAL в auth_http.py обоих сервисов и app/visibility.py (в inventory — синхронный, в skills — асинхронный близнец), семантика дословно по §3.1: 404 раньше 403, НПС публичен, владелец, admin/moderator с characters:read
[LOG] 2026-09-19 21:50 — Backend Dev: в inventory-service добавлены три internal-двойника — GET /inventory/internal/characters/{id}/items, /equipment и /internal/items/{id}, все за verify_internal_token; тела вынесены в общие функции и идентичны публичным маршрутам (в экипировке остаются fast_slot_* и effective_damage, в предмете — жирная Item)
[LOG] 2026-09-19 21:55 — Backend Dev: ItemBulkResponse повышена до PublicItemCard, маппинг вынесен в единственную проекцию schemas.public_item_card(row), /inventory/items/bulk переведён на неё без изменения поведения — модалка паспорта работает как прежде
[LOG] 2026-09-19 22:00 — Backend Dev: в skills-service подготовлен предикат require_character_skills_access (сервисный токен пропускается, пользователь идёт через can_view_private), но он НЕ подключён к GET /skills/characters/{id}/skills — по закону двух проходов гейт ставит задача #10
[LOG] 2026-09-19 22:15 — Backend Dev: проверки в Docker — py_compile и реальный импорт модулей прошли; pytest inventory-service 1396 passed, skills-service 253 passed; задачи #3 и #4 завершены, документация сервисов обновлена
[LOG] 2026-09-19 22:20 — Backend Dev: начал задачи #7 и #10 (Pass B, гейты в char-attrs и skills)
[LOG] 2026-09-19 22:25 — Backend Dev: проверил хвост Pass A — skills-service `get_active_experience` (main.py, бывшая строка 799) ДЕЙСТВИТЕЛЬНО остался анонимным чтением `GET /attributes/{id}`; переведён на двойник `/attributes/internal/{id}` с X-Internal-Token ДО постановки гейта, иначе покупка и прокачка навыков упали бы от собственного гейта
[LOG] 2026-09-19 22:35 — Backend Dev: задача #7 — пять игровых GET'ов char-attrs (`/{id}`, `/{id}/perks`, `/{id}/cumulative_stats`, `/{id}/passive_experience`, `/{id}/rest-status`) закрыты `get_optional_user` + `visibility.require_private_access`: 404 «Персонаж не найден» раньше проверки владения, NPC публичен, админ/модератор с characters:read проходит
[LOG] 2026-09-19 22:40 — Backend Dev: подтверждено, что админская синхронизация уровня (character-service main.py, ветка «level» in update_data) читает /passive_experience, пробрасывая JWT админа — под гейтом она проходит, ломать нечего
[LOG] 2026-09-19 22:45 — Backend Dev: отмечено в документации и в коде: `GET /attributes/{id}/perks` по-прежнему ПИШЕТ в БД на GET (reconcile_perks) — по D8 это отдельная задача, здесь только сужен круг вызывающих
[LOG] 2026-09-19 22:55 — Backend Dev: задача #10 — S1 `GET /skills/characters/{id}/skills` переведён на `allow_jwt_or_service_token` + `require_character_skills_access`; сервисный токен пропускается, вызывающих менять не пришлось
[LOG] 2026-09-19 23:10 — Backend Dev: починены упавшие тесты — char-attrs: test_internal_auth (класс «чтения открыты» переименован и переучен на гейт владения + новая проверка 403 на пяти путях), test_perks (owner_client вместо public_client), test_cumulative_stats, test_recalculate (админ проходит гейт), test_satiety (404 «Персонаж не найден» вместо «Атрибуты не найдены» + отдельный тест на обе ветки); skills: test_character_skills_list (+ тест 404 вместо 403 на чужом id), test_class_tree_endpoints, test_player_tree_endpoints; в общий харнесс regen_shared_tables.add_character добавлен параметр user_id
[LOG] 2026-09-19 23:20 — Backend Dev: проверки в Docker (весь репозиторий примонтирован, аргументы как в CI, CI=true) — py_compile и реальный импорт модулей прошли; pytest: character-attributes-service 480 passed / 2 skipped / 1 xpassed, skills-service 254 passed; документация обоих сервисов обновлена
[LOG] 2026-09-19 20:10 — PM: пользователь подтвердил: каталог предметов остаётся открытым, данные NPC публичны
[LOG] 2026-09-19 22:20 — Backend Dev: начал задачи #6, #9 и #11 (Pass B: character-service, user-service, notification-service)
[LOG] 2026-09-19 22:35 — Backend Dev: задача #6 — full_profile и post-history переведены на optional-auth с response_model=None; чужой получает явно собранную PublicProfileResponse / PublicPostHistoryItem, поэтому currency_balance, stat_points, level_progress, attributes и xp_earned в JSON ОТСУТСТВУЮТ, а не равны null
[LOG] 2026-09-19 22:40 — Backend Dev: паспорт /public разделён наследованием — CharacterPublicStrangerResponse (без starting_attributes и starting_attributes_is_snapshot) и наследник CharacterPublicResponse с ними; granted_kit остался публичным, второго списка полей не появилось (§3.2 D5)
[LOG] 2026-09-19 22:45 — Backend Dev: short_info потерял currency_balance для всех (D7), /logs закрыт жёстко — чужому 403, несуществующему персонажу 404 раньше проверки владения
[LOG] 2026-09-19 22:50 — Backend Dev: задача #9 — CharacterShort разделена на CharacterShortPublic + наследника с золотом, добавлена UserProfileStrangerResponse; /users/{id}/profile отдаёт баланс только владельцу профиля и админу/модератору, /users/me не изменился
[LOG] 2026-09-19 22:55 — Backend Dev: задача #11 — история чата закрыта от гостей; чтобы сообщение было по-русски, добавлена зависимость require_chat_reader (схема с auto_error=False), гость получает 401 «Войдите в аккаунт, чтобы читать чат»
[LOG] 2026-09-19 23:05 — Backend Dev: починены существующие тесты — test_character_logs (зритель = владелец, несуществующий персонаж теперь 404), test_public_character и test_starting_attributes_snapshot (паспорт со стартовыми характеристиками смотрится глазами владельца/админа), test_short_info_extended (проверки золота переехали на internal-двойник + проверка отсутствия ключа в публичном теле)
[LOG] 2026-09-19 23:15 — Backend Dev: проверки в Docker — py_compile и реальный импорт модулей во всех трёх сервисах; pytest: character-service 1077 passed / 1 skipped, user-service 581 passed / 5 skipped, notification-service 248 passed; временным смоук-тестом подтверждены формы для гостя, владельца и NPC, файл удалён
[LOG] 2026-09-19 23:20 — Backend Dev: обнаружен баг вне задачи — notification-service отдаёт английское «Could not validate credentials» при недействительном токене; добавлен в ISSUES.md (LOW). Утечка золота из ISSUES.md закрыта как DONE, документация трёх сервисов обновлена
[LOG] 2026-09-19 22:30 — Backend Dev: начал задачу #8 (Pass B, inventory-service) — гейты на I1/I2, публичная экипировка и тонкая карточка предмета
[LOG] 2026-09-19 22:40 — Backend Dev: GET /inventory/{id}/items и GET /inventory/{id}/equipment переведены на get_optional_user + require_private_access: 404 «Персонаж не найден» проверяется раньше 403 «Эти данные доступны только владельцу персонажа», НПС (user_id IS NULL) публичен, тело владельца и админа не изменилось ни на байт — вместе с рядами fast_slot_*
[LOG] 2026-09-19 22:45 — Backend Dev: проверено, что админский редактор персонажей продолжает работать — ветка admin/moderator срабатывает по characters:read, а админ получает все разрешения автоматически (user-service crud.get_effective_permissions); тест с модератором без разрешения даёт 403, с разрешением — 200
[LOG] 2026-09-19 22:50 — Backend Dev: добавлен публичный маршрут GET /inventory/{id}/equipment/public → List[PublicEquipmentSlot] {slot_type, item}; пояс отсекается В ЗАПРОСЕ (crud.get_public_equipment_slots, slot_type NOT LIKE 'fast_slot_%'), а не пост-фильтром — живая дыра из §3.4 закрыта, запись в ISSUES.md помечена DONE
[LOG] 2026-09-19 22:55 — Backend Dev: GET /inventory/items/{id} похудел до PublicItemCard через ту же единственную проекцию schemas.public_item_card; жирный шаблон остался только на двойнике /inventory/internal/items/{id}. /items/bulk, /item-detail, /fast_slots и /active-buffs не тронуты
[LOG] 2026-09-19 23:05 — Backend Dev: починены упавшие вызовы в тестах — 27+8 чтений жирного предмета переведены на internal-двойник (test_item_out_schemas_serve_stored_rows, test_item_full_image, test_item_xp_buffs, test_item_battle_effects, test_item_rarity_rules), а игровые тесты инвентаря и экипировки получили новую фикстуру conftest.private_viewer (сеет characters и подменяет get_optional_user) вместо ухода на двойник — test_gathering ×6, test_weapon_damage ×8
[LOG] 2026-09-19 23:20 — Backend Dev: проверки в Docker — py_compile и реальный импорт main прошли, pytest inventory-service 1395 passed / 1 skipped (было 1396 total, ни одного нового красного); отдельно прогнан временный матричный прогон (гость/чужой/владелец/модератор с правом и без/НПС/несуществующий + отсутствие fast_slot_* в публичной экипировке) — всё зелёное, постоянные тесты пишет QA в задаче #17; задача #8 завершена, документация сервиса обновлена
[LOG] 2026-09-19 23:30 — Frontend Dev: начал задачи #12, #13 и #14 (Pass C) — минимум фронтенда под похудевшие ответы
[LOG] 2026-09-19 23:40 — Frontend Dev: задача #12 — карточка персонажа в чужом профиле больше не ведёт на свой профиль: ссылка на /profile остаётся только у собственного активного персонажа (сверка `char.id` с `state.user.character?.id`), остальные карточки рендерятся как неинтерактивный `<div>` с той же разметкой; `group` снят, поэтому `group-hover:` подсветка и курсор-ссылка пропали сами собой; добавлен комментарий TODO(FEAT-172)
[LOG] 2026-09-19 23:45 — Frontend Dev: задача #13 — `stat_points`, `currency_balance`, `level_progress`, `attributes` стали необязательными в `CharacterProfile`, `xp_earned` — в `PostHistoryItem`, `starting_attributes` и `starting_attributes_is_snapshot` — в `CharacterPublic`; защищены две точки рендера в `CharacterPanel` (`?? 0`) и чип «+N XP» в `PostHistoryTab` (рисуется только при числе)
[LOG] 2026-09-19 23:50 — Frontend Dev: проверено, а не переписано — паспорт чужого персонажа уже корректно скрывает блок характеристик (`toStats(undefined)` даёт `undefined`, та же ветка, что и для `null` у персонажей до FEAT-155); в `adapters.ts` добавлен только `?? false`, чтобы тип не стал `boolean | undefined`; `StatsPanel` уже читал `profile?.attributes?.` через опциональные цепочки
[LOG] 2026-09-19 23:52 — Frontend Dev: золото чужого персонажа на фронтенде нигде не рисовалось — `CharacterShort` в `userProfileSlice` его не содержит, `NpcProfileModal` тоже; `CharacterChip` и `MobileHeader` берут баланс из `/users/me`, который не изменился
[LOG] 2026-09-19 23:55 — Frontend Dev: задача #14 — `ChatPanel` не дёргает историю чата без авторизации и показывает «Войдите в аккаунт, чтобы читать чат»; тост об ошибке тоже подавлен только для гостя, реальные ошибки у авторизованного по-прежнему видны; маршрут `chat/history` обёрнут в `ProtectedRoute`
[LOG] 2026-09-20 00:05 — Frontend Dev: проверил остальные экраны на закрытые эндпоинты — все чтения `/attributes/{id}`, `/inventory/{id}/items|equipment`, `/skills/characters/{id}/skills`, `/characters/{id}/logs` идут либо по своему персонажу, либо из админки, либо по НПС/мобу (публичны по Q6); у гостя исчезают ровно две вещи: чип «+N XP» в истории постов и блок стартовых характеристик в паспорте
[LOG] 2026-09-20 00:15 — Frontend Dev: проверки в одноразовом контейнере (`docker compose run --rm --no-deps frontend`) — `npx tsc --noEmit` EXIT=0, `npm run build` EXIT=0 (собрано за 31 с); package-lock.json не изменился, контейнеров не осталось
[LOG] 2026-09-20 00:18 — Frontend Dev: баг навигации исправлен, запись про `CharactersSection.tsx` удалена из ISSUES.md
[LOG] 2026-09-20 00:35 — Frontend Dev: по замечанию PM кнопка «История» в `ChatHeader` скрыта от гостя (новый проп `isAuthenticated`) — раньше она молча отбрасывала на страницу входа; заодно проверены остальные гостевые контролы: `ChatInput` уже показывает «Войдите, чтобы писать», действия над игроками и НПС в локации скрыты за `currentCharacterId != null`, `ProfilePage` у гостя отдаёт пустое состояние без запросов, паспорт в `/characters/list` ходит только в неизменившийся `/inventory/items/bulk` — новых редиректов и ошибок не найдено; `tsc --noEmit` и `npm run build` в одноразовом контейнере зелёные
[LOG] 2026-09-20 01:05 — Frontend Dev: BLOCKER #1 из ревью — `api/items.ts::fetchItem` (строка 67) переведён с `GET /inventory/items/{id}` на `GET /inventory/admin/items/{id}`; вызывающих ровно два, оба админские (`ItemsAdminPage/ItemForm.tsx:213`, `Admin/RecipesAdminPage.tsx:171`), не-админских потребителей `fetchItem` нет, токен уходит сам через интерцепторы `api/client.ts`
[LOG] 2026-09-20 01:15 — Frontend Dev: живая проверка на поднятом стеке через api-gateway — публичная карточка отдаёт 6 ключей, админская 80 (`item_type`, `price`, `effects`, `damage_entries`, `xp_buffs`, все `*_modifier`), без токена 401, несуществующий id 404 «Предмет не найден»; на предмете #39 «Броня Скитальца» с 14 ненулевыми модификаторами прогнан цикл «загрузить → сохранить тем же PUT → перечитать»: расхождений НЕТ, регрессия обнуления данных подтверждена закрытой (то же самое на предмете #1)
[LOG] 2026-09-20 01:20 — Frontend Dev: браузерная проверка через расширение недоступна в этой сессии; вместо неё подтверждено, что dev-сервер Vite уже отдаёт исправленный модуль (`http://frontend:5555/src/api/items.ts` содержит `/admin/items/${id}`), то есть редактор в браузере ходит в новую дверь; `tsc --noEmit` TSC=0, `npm run build` BUILD=0
[LOG] 2026-09-20 01:05 — QA: начал Pass D (задачи #15–#20) — пятизрительная матрица, отсутствие приватных ключей, регрессия пояса, заголовки у вызывающих и матрица паритета предиката
[LOG] 2026-09-20 01:20 — QA: задача #20 — `test_feat171_predicate_parity.py` положен в character-service, char-attrs, inventory и skills, по 39 одинаковых тестов; файлы отличаются только sync/async обёрткой, ключевые строки — модератор БЕЗ characters:read и редактор С правом (оба False), они ловят подмену `and` на `or`
[LOG] 2026-09-20 01:40 — QA: задача #17 — 103 теста на inventory; пояс закрыт трижды: нет строк fast_slot_* в /equipment/public при всех четырёх заполненных слотах, перехват SQL доказывает NOT LIKE в запросе (а не пост-фильтр), и отдельный тест нейтрализует crud.FAST_SLOT_LIKE_PATTERN и требует, чтобы пояс снова потёк
[LOG] 2026-09-20 01:55 — QA: задача #15 — 120 тестов на character-service (C1, C3, C4, C7, C8 + двойники C1i/C4i); приватные ключи проверяются на ОТСУТСТВИЕ, а парный класс доказывает, что у владельца те же ключи есть — иначе `not in` проходил бы вхолостую
[LOG] 2026-09-20 02:05 — QA: задача #16 — 117 тестов на char-attrs (A1–A5 × шесть зрителей + NPC + 404 раньше 403, двойники A1i/A4i, тело двойника сравнивается с телом владельца); отдельно закреплено D8 — reconcile_perks всё ещё пишет на GET, но чужой его больше не триггерит
[LOG] 2026-09-20 02:20 — QA: задача #18 — skills 22, user-service 15, notification 14; в skills матрица гоняется через настоящий allow_jwt_or_service_token, поэтому ветка «None = сервисный вызов» проверена с обеих сторон: сервисный токен проходит, гость без токена получает 401, почти-верный токен сервисным не считается
[LOG] 2026-09-20 02:45 — QA: задача #19 — шесть файлов test_feat171_outgoing_internal.py (battle 20, dungeon 15, locations 25, character-service 10, char-attrs 22, skills 10) плюс проверки C4i в user-service; у dungeon-, locations- и user-service таких тестов не было вообще
[LOG] 2026-09-20 02:50 — QA: три вызова написаны прямо в теле эндпоинта (locations.move_and_post, locations.quick_move, char-attrs.upgrade_attributes) — клиентской функции у них нет, поэтому они закреплены разбором AST: URL двойника плюс headers=_internal_token_headers()
[LOG] 2026-09-20 02:55 — QA: уточнение к §3.5 — три чтения dungeon-service ошибку НЕ проглатывают, а превращают в HTTPException(502); сообщение обвиняет соседний сервис, а не токен, так что заголовок всё равно проверяется по записанному запросу (то же у skills: 500, у character-service: 404)
[LOG] 2026-09-20 03:20 — QA: каждый новый гейт проверен «на красноту» — 15 точечных поломок продакшен-кода (фильтр пояса, гейты A1/I2/S1/logs, обе формы ответа C1 и U1, `and`→`or` в копии предиката, снятые заголовки у battle/dungeon/locations/skills/char-attrs/user); каждая давала красный, каждый файл восстановлен ПОБАЙТОВО по sha256, git checkout/restore/stash не использовались
[LOG] 2026-09-20 03:40 — QA: полные сюиты в Docker (весь репозиторий примонтирован, аргументы как в CI, CI=true) — character-service 1246 passed / 1 skipped, character-attributes-service 658 passed / 2 skipped / 1 xpassed, inventory-service 1538 passed, skills-service 325 passed, user-service 601 passed, notification-service 262 passed, battle-service 783 passed, locations-service 1379 passed, dungeon-service 170 passed; добавлено 649 тестов, ни одного красного, продакшен-код не менялся
[LOG] 2026-09-20 04:00 — Reviewer: начал финальную проверку, пересоздал стек (up -d --force-recreate) и убедился, что контейнеры несут новый код, а не подхваченный --reload
[LOG] 2026-09-20 04:10 — Reviewer: завёл шесть зрителей (гость, чужой игрок, владелец, админ, модератор С правом characters:read и модератор БЕЗ него через user_permissions.granted=0) и прогнал собственную матрицу по 21 маршруту, не полагаясь на матрицу QA
[LOG] 2026-09-20 04:20 — Reviewer: приватные ключи у гостя, чужого и модератора без права ОТСУТСТВУЮТ на всех маршрутах; у владельца, админа и модератора с правом те же ключи есть — значит проверки «not in» не проходят вхолостую; уровень персонажа публичен, как и требовалось
[LOG] 2026-09-20 04:25 — Reviewer: дыра с поясом закрыта живьём — у персонажа 19 в БД заполнены fast_slot_1..4, а гость в /inventory/19/equipment/public видит только плащ и кинжал с полями {id,name,description,image_url,rarity,type} и ни одной строки fast_slot_*; приватная экипировка даёт 403 по-русски
[LOG] 2026-09-20 04:30 — Reviewer: владелец и админ не пострадали — золото 105, stat_points, level_progress и attributes на месте, /users/me отдаёт баланс через двойник C4i, 21 владельческое чтение вернуло 200, страница /profile в браузере рисуется без единой ошибки ≥400
[LOG] 2026-09-20 04:35 — Reviewer: 404 раньше 403 подтверждён на 19 маршрутах для всех зрителей; NPC 33 полностью публичен для гостя; все семь internal-двойников отдают 403 на gateway даже под JWT админа
[LOG] 2026-09-20 04:45 — Reviewer: закон двух проходов проверен не на словах — реальные клиентские функции вызваны ВНУТРИ своих контейнеров с настоящим INTERNAL_SERVICE_TOKEN: battle fetch_full_attributes (52 ключа), fetch_weapons (effective_damage 18), get_item (80 ключей), skills_client, dungeon get_character_items и get_character_attributes — всё работает, бои и подземелья не ослепли
[LOG] 2026-09-20 04:50 — Reviewer: sweep логов всех 13 сервисов за 40 минут — в locations, battle, dungeon, party, battle-pass и autobattle НОЛЬ 401/403/500; каждый 401/403 в логах объясняется моей собственной пробой
[LOG] 2026-09-20 04:55 — Reviewer: три вызова, закреплённых разбором AST, подтверждены косвенно — locations и char-attrs не дали ни одного отказа по своим же гейтам, чего не случилось бы при забытом заголовке
[LOG] 2026-09-20 05:05 — Reviewer: БЛОКЕР — §3.4 утверждает, что у I3 нет фронтового вызывающего («verified»), но он есть: api/items.ts:67 ходит в GET /inventory/items/{id} через baseURL '/inventory'. Админский редактор предметов (ItemForm.tsx:213) заполняет форму похудевшей карточкой, теряет item_type, цену, модификаторы, effects и damage_entries, а последующий PUT записывает дефолты обратно — тихая порча данных предмета
[LOG] 2026-09-20 05:10 — Reviewer: БЛОКЕР по критериям §1 — GET /battles/battles/{id}/logs вообще без авторизации; гость без токена читает pve_rewards {xp:30, gold:5} и skill_use {skill_id}, то есть опыт, деньги и навыки. Маршрут был известен аналитику и сознательно оставлен вне объёма — нужно решение PM: закрывать здесь или выносить немедленным следом
[LOG] 2026-09-20 05:15 — Reviewer: HIGH — новый гейт обходится через доверенный прокси: GET /locations/npcs/{id}/shop?character_id= без авторизации ходит в /attributes/internal/{id} с X-Internal-Token за анонима и отдаёт discounted_buy_price; живьём 20 → 19 разворачивается в харизму 30
[LOG] 2026-09-20 05:20 — Reviewer: три MINOR — перевёрнутое наследование UserProfileStrangerResponse (новое приватное поле утечёт само), проверка золота в U1 по роли без characters:read, и неохваченный фичей анонимный /inventory/{id}/equipment-rules
[LOG] 2026-09-20 05:25 — Reviewer: обнаружены баги вне фичи, добавлены в отчёт для ISSUES.md — анонимный GET /users/{id} отдаёт email (HIGH), анонимные чтения квестов и гейтов в locations, снапшот зрителя в бою с attributes/skills/fast_slots, мёртвый _get_optional_user в chat_routes
[LOG] 2026-09-20 05:30 — Reviewer: бухгалтерия ISSUES.md проверена — пояс и золото помечены DONE с достоверным описанием, запись про навигацию CharactersSection удалена, запись про запись-на-GET в /perks корректно оставлена открытой (D8)
[LOG] 2026-09-20 05:35 — Reviewer: тестовые данные убраны — пять учёток удалены, персонаж 18 возвращён владельцу (user_id=7, уровень 50, локация 15), временные скрипты из контейнеров удалены, коммитов не делал
[LOG] 2026-09-20 05:40 — Reviewer: проверка завершена, результат FAIL — ядро фичи (гейты, пояс, двойники, порядок проходов) проверено живьём и работает, но блокируют регрессия админского редактора предметов и две живые утечки приватных данных
[LOG] 2026-09-20 09:00 — Reviewer: начал ревью #2, снова пересоздал стек и убедился, что контейнеры несут правки (admin/items в inventory, battle_visibility.py, locations/visibility.py)
[LOG] 2026-09-20 09:10 — Reviewer: пять копий предиката сверены — три синхронные побайтово одинаковы, две асинхронные отличаются только async/await и докстрингом; константы, SQL, порядок веток и русские тексты 403/404 совпадают
[LOG] 2026-09-20 09:20 — Reviewer: фикс #1 проверен — у предмета теперь три двери с разной аудиторией: админская отдаёт 80 ключей и 14 ненулевых модификаторов админу и модератору с items:read, гостю 401, чужому и владельцу 403; публичная всем шесть ключей; internal 403 на gateway. Разрешение items:read уже существует (id 6) — миграция и сид-тест по §10.13 не нужны
[LOG] 2026-09-20 09:35 — Reviewer: сделал то, что не смог фронтендер — клик-через в браузере: вошёл админом, открыл /admin/items, нажал «Изменить» у предмета 39 и прочитал ЗНАЧЕНИЯ ПОЛЕЙ ФОРМЫ — strength_modifier=1000, agility_modifier=300, item_level=15, max_durability=100, health_modifier=300, то есть жирные данные реально доехали до UI
[LOG] 2026-09-20 09:40 — Reviewer: нажал «Сохранить» — ни одного ответа ≥400, ни одной ошибки в консоли, вернуло к списку; перечитал предмет через админскую дверь: 80 ключей, DIFF: NONE. Разрушительная регрессия закрыта от начала до конца, а не только по curl
[LOG] 2026-09-20 09:50 — Reviewer: фикс #2 — логи боя: гость 401, чужой 403, модератор БЕЗ characters:read 403, админ и модератор С правом 200, несуществующий бой 404; события pve_rewards {xp, gold} и skill_use, которые гость читал в ревью #1, больше без токена недоступны
[LOG] 2026-09-20 09:55 — Reviewer: снапшот наблюдателя оставлен вне фичи — считаю это приемлемым: аудитория другая (авторизованный игрок в той же локации и только пока бой идёт), сужать надо продуктовым решением, и главное — запись в ISSUES.md перечисляет конкретные поля и честно предупреждает, что гейт логов намеренно повторяет правило /spectate и сужать их надо ВМЕСТЕ
[LOG] 2026-09-20 10:05 — Reviewer: фикс #3 — все пять дверей locations закрыты при переданном character_id (гость и чужой 403, владелец и админ 200), гейт стоит ДО _fetch_charisma, оракул харизмы мёртв, а публичная витрина лавки без character_id осталась открытой для всех шести зрителей — гостевую страницу не сломали
[LOG] 2026-09-20 10:10 — Reviewer: решение оставить client/details открытым признаю верным — в ответе нет ни одного приватного поля, остаточный риск (аноним ускоряет финализацию чужих сессий добычи) идемпотентен и честно описан в ISSUES.md как LOW
[LOG] 2026-09-20 10:20 — Reviewer: фиксы #4/#5 — золото теперь следует за правом, а не за ролью (модератор без characters:read ключа не получает), наследование развёрнуто на публичную базу во всех парах схем, .dict() стоит в нужном месте и гасит именно ту ловушку Pydantic v1, о которой я писал
[LOG] 2026-09-20 10:25 — Reviewer: сверх списка — email больше не уходит чужому ни в GET /users/{id} (ключа НЕТ в JSON), ни в GET /users/admins, который раньше одним анонимным запросом отдавал адреса всех администраторов; межсервисные вызывающие берут оттуда только username и не пострадали
[LOG] 2026-09-20 10:30 — Reviewer: фикс #6 — equipment-rules остался публичным по решению, но на несуществующего персонажа теперь 404, как и везде
[LOG] 2026-09-20 10:35 — Reviewer: регрессий нет — прогнал матрицу ревью #1 заново, все гейты, пояс, публичная экипировка и публичность НПС ведут себя как прежде; в логах десяти сервисов ноль 5xx
[LOG] 2026-09-20 10:40 — Reviewer: бухгалтерия ISSUES.md проверена — запись про email закрыта с достоверным описанием, снапшот наблюдателя и остаток по client/details заведены новыми записями с верными приоритетами
[LOG] 2026-09-20 10:45 — Reviewer: остались четыре непреграждающие мелочи — пятая копия предиката не включена в матрицу паритета, discounted_buy_price у гостя приходит как null, а не отсутствует (значение не утекает), докстринги «четыре копии» устарели, и 403-vs-404 в логах боя остаётся оракулом существования для авторизованного
[LOG] 2026-09-20 10:50 — Reviewer: тестовые данные убраны — учётки 54–58 удалены, персонаж 18 возвращён владельцу (user_id=7, уровень 50, локация 15), предмет 39 сверен в MySQL после сохранения из браузера и не изменился; коммитов не делал
[LOG] 2026-09-20 10:55 — Reviewer: ревью #2 завершено, результат PASS — задача #21 закрыта, фича готова к завершению
[LOG] 2026-09-20 06:10 — Backend Dev: начал задачу #22 — HIGH из ревью, боковая дверь в магазине NPC
[LOG] 2026-09-20 06:25 — Backend Dev: добавлен `locations-service/app/visibility.py` (пятая копия предиката, async) — сервис стал доверенным прокси к приватным атрибутам, значит ему нужен тот же гейт, что и соседям
[LOG] 2026-09-20 06:40 — Backend Dev: закрыты пять персональных чтений — `/npcs/{id}/shop` (только когда передан `character_id`), `/npcs/{id}/quests`, `/quests/active`, `/action-gate/status`, `/npcs/{id}/dialogue` (только когда передан `character_id`); зритель берётся из уже существующего `get_optional_user`, фронтенд не трогали
[LOG] 2026-09-20 06:45 — Backend Dev: контракт витрины — гость без `character_id` по-прежнему видит лавку и базовые цены, поля `discounted_buy_price` в ответе нет вовсе; с чужим `character_id` — 403, с несуществующим — 404, владелец и админ получают скидку как раньше
[LOG] 2026-09-20 06:55 — Backend Dev: внутренних вызывающих у этих маршрутов нет — battle, dungeon, inventory и char-attrs ходят только в `/locations/*/internal/*`, поэтому «сначала научить вызывающих» не потребовалось
[LOG] 2026-09-20 07:05 — Backend Dev: тесты — новый `test_feat171_shop_gate.py` (25 тестов: гость/чужой/владелец/админ/модератор без права/NPC/несуществующий + отдельная проверка, что числа 19 нет в ответе гостю и `_fetch_charisma` за анонима не зовётся); в `test_charisma_discount.py` четыре теста витрины переведены на фикстуру владельца
[LOG] 2026-09-20 07:15 — Backend Dev: проверки — py_compile и настоящий импорт модуля в контейнере зелёные, вся сюита locations-service в Docker 1405 passed (было 1380)
[LOG] 2026-09-20 07:20 — Backend Dev: обнаружен смежный долг, добавлен в ISSUES.md — `client/details` анонимно принимает чужой `character_id` и ускоряет финализацию его сессий добычи (приватного не раскрывает, идемпотентно, гейт отнял бы у гостя страницу локации)
[LOG] 2026-09-20 07:25 — Backend Dev: задача #22 завершена, обновлены `docs/services/locations-service.md` (новый раздел про персональные чтения) и строка про игровой двойник `action-gate/status`
[LOG] 2026-09-20 07:40 — Backend Dev: начал задачу #23 (ревью #1, находки 1 и 6) — подтвердил ошибку §3.4: `api/items.ts::fetchItem` действительно зовёт `GET /inventory/items/{id}`, URL прятался за baseURL axios; internal-двойник браузеру недоступен, nginx закрывает префикс `/inventory/internal/`
[LOG] 2026-09-20 07:50 — Backend Dev: добавлен `GET /inventory/admin/items/{item_id}` — жирная `Item` под `require_permission("items:read")`, тем же правом, что уже охраняет страницу `/admin/items` и `GET /admin/items/{id}/conversions`; новых разрешений и миграций не потребовалось. Публичная тонкая карточка на `GET /inventory/items/{id}` и internal-двойник остались как есть — у предмета теперь ровно три двери, каждая под свою аудиторию (D10)
[LOG] 2026-09-20 07:55 — Backend Dev: решение по находке 6 — `GET /inventory/{id}/equipment-rules` ОСТАЁТСЯ публичным: это справочные данные по классу и подклассу, а класс с подклассом и так публичны (C3, C4, C10); ни одного числа и ни одной вещи персонажа в ответе нет, гейт был бы строже публичной анкеты. Выровнена только дисциплина ошибок — несуществующий персонаж теперь 404, а не 200 «ограничений нет» (D11)
[LOG] 2026-09-20 08:10 — Backend Dev: тесты — новый `test_feat171_admin_item_route.py` (23 теста): матрица гость/игрок/модератор/админ с правом `items:read` и без, 404 по-русски на несуществующий предмет, полнота жирного тела проверяется ПО СХЕМЕ `schemas.Item` (а не списком полей руками), равенство телу internal-двойника и контрольный тест, что публичный маршрут всё ещё тонкий — иначе проверки полноты проходили бы вхолостую; плюс четыре теста на `/equipment-rules` (гость и чужой ⇒ 200, в теле ничего кроме правил класса, несуществующий ⇒ 404)
[LOG] 2026-09-20 08:20 — Backend Dev: проверки — py_compile и настоящий импорт модуля в контейнере зелёные, вся сюита inventory-service в Docker 1571 passed (было 1548), падений в соседних тестах нет
[LOG] 2026-09-20 08:25 — Backend Dev: задача #23 завершена, обновлён `docs/services/inventory-service.md` (новая строка каталога, таблица «что закрыто» и блок про equipment-rules); фронтенду нужно перевести `fetchItem` на `GET /inventory/admin/items/{id}` — отдельная задача
[LOG] 2026-09-20 08:40 — Backend Dev: начал задачи #24 и #25 (ревью #1, находка 2, две MINOR по user-service и утечка e-mail из списка предсуществующих)
[LOG] 2026-09-20 08:50 — Backend Dev: подтвердил находку 2 по коду — у обоих маршрутов логов боя не было НИ ОДНОЙ зависимости, а nginx режет только /battles/internal/; battle_id — маленькое последовательное число, так что вся история боёв перебиралась анонимно
[LOG] 2026-09-20 09:00 — Backend Dev: задача #24 — добавлен app/battle_visibility.py; читать логи могут участник боя (в том числе завершённого), наблюдатель из той же локации ПОКА бой активен и админ/модератор с правом characters:read; роли самой по себе мало, 404 «Бой не найден» проверяется раньше 403
[LOG] 2026-09-20 09:05 — Backend Dev: правило наблюдателя списано дословно с GET /{battle_id}/spectate намеренно — панель логов живёт на той же странице, что и состояние боя, которое наблюдатель уже читает; сузить логи, не сузив spectate, значило бы сломать панель и не закрыть при этом более богатую утечку
[LOG] 2026-09-20 09:10 — Backend Dev: снапшот наблюдателя (build_participant_info отдаёт attributes, skills, fast_slots и equipment_durability любому соседу по локации, плюс тот же push в WS) — ОТДЕЛЬНЫЙ путь кода, в объём фикса не взят: нужно продуктовое решение, что наблюдателю положено видеть. Добавлено в ISSUES.md (MEDIUM) с пометкой, что сужать оба правила надо вместе
[LOG] 2026-09-20 09:15 — Backend Dev: фронтенд не менялся — BattlePageBar ходит через дефолтный инстанс axios, которому axiosSetup уже добавляет Bearer-токен; гостевой страницы боя не существует
[LOG] 2026-09-20 09:25 — Backend Dev: тесты #24 — test_feat171_battle_log_auth.py, 32 теста: восьмизрительная матрица на обоих маршрутах плюс сам предикат (404 на несуществующий бой, нормализация Enum-статуса, короткое замыкание привилегированной ветки). В каждом отказе проверяется, что в теле нет ни pve_rewards, ни skill_use, ни 9003, ни gold — гейт, отдающий логи вместе с ошибкой, не прошёл бы
[LOG] 2026-09-20 09:40 — Backend Dev: задача #25 — GET /users/{id} действительно отдавал e-mail живого человека без токена, а GET /users/admins — адреса ВСЕХ админов одним анонимным запросом; публичной базой стала UserPublicRead, приватная UserRead теперь её наследник и добавляет только email
[LOG] 2026-09-20 09:45 — Backend Dev: двойник не понадобился — проверил всех межсервисных вызывающих /users/{id} (character-service ×3, locations-service ×1): все читают только username, фронтенд этот маршрут не зовёт вовсе. Соседние маршруты проверены на ту же утечку: /users/all отдаёт UserPublicItem без e-mail, /admin/list под require_admin, /users/me — свой собственный
[LOG] 2026-09-20 09:55 — Backend Dev: MINOR #4 — наследование перевёрнуто: UserProfileStrangerResponse стала базой, UserProfileResponse её расширяет; плюс защитный .dict() в обработчике, потому что Pydantic v1 пропустил бы ЭКЗЕМПЛЯР CharacterShort вместе с золотом через поле типа CharacterShortPublic
[LOG] 2026-09-20 10:00 — Backend Dev: MINOR #5 — золото на U1 теперь требует роль И право characters:read (формула can_view_private), e-mail на /users/{id} — роль И users:read. Существующий test_feat171_profile_gold.py пришлось дополнить настоящими строками ролей и разрешений: раньше модератор проходил по одной легаси-строке роли — ровно та дыра, которую чинили
[LOG] 2026-09-20 10:10 — Backend Dev: тесты #25 — test_feat171_review_fixes.py, 36 тестов: приватные ключи проверяются на ОТСУТСТВИЕ у гостя/чужого/модератора без права и на наличие у владельца/админа (иначе not in проходил бы вхолостую), направление наследования проверяется на самом наследовании, а не на сегодняшнем списке полей
[LOG] 2026-09-20 10:25 — Backend Dev: проверки в Docker (весь репозиторий примонтирован, аргументы как в CI, CI=true) — py_compile по всем изменённым файлам зелёный, модули реально импортируются (обе сюиты поднимают main); battle-service 815 passed (было 783), user-service 630 passed (было 601), ни одного красного и ни одной починки соседних тестов
[LOG] 2026-09-20 10:30 — Backend Dev: задачи #24 и #25 завершены; обновлены docs/services/battle-service.md (новый раздел про гейт логов), docs/services/user-service.md (две строки каталога и правило characters:read на U1) и docs/ISSUES.md (утечка e-mail закрыта как DONE в HIGH, снапшот наблюдателя — MEDIUM, in-battle вне /internal/ — LOW)
[LOG] 2026-09-20 11:05 — Backend Dev: начал задачу #26 — три остаточных замечания ревью #2 (пятая копия предиката вне матрицы, discounted_buy_price: null вместо отсутствия ключа, докстринги про «четыре копии»)
[LOG] 2026-09-20 11:20 — Backend Dev: остаток #1 — матрица паритета добавлена в locations-service: файл скопирован с асинхронного близнеца skills-service, отличий, кроме общей шапки, нет вовсе (diff пустой); 39 тестов, все пять копий can_view_private теперь под одними и теми же утверждениями
[LOG] 2026-09-20 11:35 — Backend Dev: проверка «на красноту» — в locations-копии предиката `and` заменён на `or`: 8 failed, 31 passed (обе строки «модератор БЕЗ права» и «право без роли», test_role_and_permission_is_an_and_not_an_or и 403-обёртка «DID NOT RAISE»). Файл восстановлен ПОБАЙТОВО, sha256 до и после совпадает (d2bc259b…); git checkout/restore/stash НЕ использовались
[LOG] 2026-09-20 11:50 — Backend Dev: остаток #2 — витрина лавки теперь не отдаёт `discounted_buy_price: null`, а не отдаёт ключ вовсе: NpcShopItemPublicRead стала базой, NpcShopItemRead её расширяет единственным приватным полем (то же направление наследования, что в задаче #25), маршрут переведён на response_model=None и явную сборку одной из двух моделей
[LOG] 2026-09-20 11:55 — Backend Dev: заодно убран рукописный список полей в обработчике — нормализация строки (dict из crud или ORM/мок) собрана в _shop_item_fields() по __fields__ схемы, так что новое поле не забудут добавить в одну из двух веток
[LOG] 2026-09-20 12:00 — Backend Dev: оба теста переписаны с `.get(...) is None` на проверку ОТСУТСТВИЯ ключа (`"discounted_buy_price" not in body[0]` плюс проверка по сырому тексту ответа) — иначе утверждение проходило бы и при null, ровно то, на что указал ревью
[LOG] 2026-09-20 12:10 — Backend Dev: остаток #3 — все пять докстрингов visibility.py переписаны: «Keep the five copies byte-identical», список из пяти путей с пометкой sync/async и указанием на test_feat171_predicate_parity.py; та же шапка проставлена во всех пяти файлах матрицы, в §3.1 D1 добавлена заметка об обновлении
[LOG] 2026-09-20 12:30 — Backend Dev: проверки в Docker (весь репозиторий примонтирован, аргументы как в CI, CI=true) — py_compile по всем десяти изменённым/новым файлам зелёный, модули реально импортируются (`import visibility, main` в locations-service). Сюиты: locations 1444 passed, character-service 1246 passed/1 skipped, char-attrs 658 passed/2 skipped/1 xpassed, inventory 1571 passed, skills 325 passed — ни одного красного
[LOG] 2026-09-20 12:35 — Backend Dev: задача #26 завершена; docs/services/locations-service.md править не пришлось — там уже было написано, что ключа у гостя нет, теперь это правда
[LOG] 2026-09-20 05:30 — PM: ревью #2 PASS, остатки закрыты, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Профиль персонажа остался публичным**: имя, раса, класс, описание, аватар, титулы, история постов и уровень видны всем, включая гостей.
- **Надетая экипировка видна всем**, предмет можно открыть и прочитать название и описание, но характеристики предмета скрыты. Быстрые слоты не отдаются вовсе.
- **Скрыто от чужих** (видит владелец и админ/модератор с правом): характеристики, инвентарь, опыт и прогресс уровня, деньги, перки, навыки, журнал событий, стартовые характеристики. Опыт за пост убран из публичной истории.
- **История чата** только для вошедших, с понятным русским отказом.
- Резали **в ответе сервера**, а не в интерфейсе: приватные поля именно отсутствуют в ответе, а не приходят и прячутся.
- Работа шла в два прохода: сначала служебные близнецы маршрутов и перевод 14 внутренних вызовов, потом сами ограничения. Иначе сломались бы бои, подземелья, прокачка навыков и вход в игру.
- NPC и мобы остались публичными (бестиарий), каталог предметов тоже — оба решения приняты осознанно и записаны.

### Найдено и исправлено по ходу (всё предсуществующее, кроме первого пункта)
- **Мы сами чуть не сломали админку предметов**: тонкая карточка ломала редактор, и сохранение обнулило бы характеристики предмета. Поймано на ревью, для админа сделана отдельная дверь с полными данными. Проверено в браузере на предмете с 14 характеристиками.
- **Магазин NPC выдавал харизму гостю** через цену со скидкой; заодно закрыты задания NPC, журнал заданий, ворота действия и диалог.
- **Журнал боя читался анонимно**: опыт, золото и использованные навыки перебором по номеру боя.
- **Запрос пользователя анонимно отдавал почту**, а список администраторов — почты всех администраторов сразу.
- Быстрые слоты утекали через запрос экипировки в обход защиты FEAT-169.
- Золото утекало тремя путями.

### Оставшиеся риски / follow-up задачи
- **Страницы чужого персонажа в игре нет** — переходы из топа, локации и профиля игрока ведут либо в карточку-анкету, либо к владельцу. Это следующая задача (FEAT-172).
- Снимок боя для зрителя по-прежнему содержит характеристики, навыки и пояс участников — записано в ISSUES.md, менять вместе с правилом доступа к журналу боя.
- `GET /attributes/{id}/perks` по-прежнему пишет в базу при чтении.
- Отличие 403 от 404 позволяет узнать, существует ли персонаж; список персонажей и так публичен.
