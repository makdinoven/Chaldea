# FEAT-164: Восстановление в покое и сытость от еды

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-17 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-164-slug.md` → `DONE-FEAT-164-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Первый этап ребаланса профессий. Сейчас в игре нет никакого пассивного восстановления: после боя здоровье, мана, энергия и выносливость остаются как есть, лечиться можно только зельями. Добавляем восстановление в состоянии покоя и механику «сытости» от еды повара, которая его ускоряет. Цель — сделать повара нужным каждому игроку.

### Бизнес-правила
- **Восстановление в покое:** 5% от максимума в час реального времени, одинаково для здоровья, маны, энергии и выносливости. Не выше максимума.
- Восстановление идёт только в покое: персонаж **не в бою, не в подземелье, не на сборе ресурсов**. Время, проведённое в этих состояниях, не засчитывается.
- Считается «лениво», без фоновых задач/крона: хранится момент последнего пересчёта, при чтении/изменении ресурсов персонажа досчитывается накопленное восстановление. Значение, которое видит игрок, всегда актуально.
- **Сытость:** еда (предмет, созданный поваром) при употреблении даёт эффект «Сытость» ровно на **24 часа реального времени**.
- Одновременно активна только **одна** сытость. Пока сытость активна, съесть новую еду нельзя — ошибка «Вы уже наелись».
- Сытость ускоряет восстановление в покое в зависимости от редкости еды: обычная +50%, редкая +100%, эпическая +150%, легендарная +200%. Легендарная — максимальная редкость для еды. Итог: 5% в час × (1 + бонус).
- Сытость также может давать бонус к характеристикам (настраивается у предмета еды в админке). Бонус действует, пока активна сытость.
- Бонус сытости к восстановлению должен настраиваться/выводиться из редкости — админ заводит еду в админке, отдельно прописывать бонус восстановления не обязательно.
- Бонусов за место (таверна, дом) **нет** — это будущая отдельная большая фича «дом игрока».

### UX / Пользовательский сценарий
1. Игрок выходит из боя с 30% здоровья.
2. Пока он в покое, здоровье/мана/энергия/выносливость растут на 5% в час; игрок видит актуальные значения в профиле.
3. Игрок съедает еду из инвентаря — появляется активный эффект «Сытость» с оставшимся временем и описанием бонусов.
4. Восстановление ускоряется согласно редкости еды; через 24 часа эффект пропадает.
5. Если игрок в бою/подземелье/на сборе — восстановление не идёт.

### Edge Cases
- Персонаж уже на максимуме — ничего не копится «про запас».
- Максимум ресурса изменился (снял экипировку) — текущее значение не превышает новый максимум.
- Сытость закончилась посреди периода покоя — до момента окончания считаем с бонусом, после — без.
- Персонаж вошёл в бой: перед началом боя восстановление должно быть досчитано, чтобы в бой ушли актуальные значения.
- Персонаж погиб / здоровье 0 — восстанавливается так же (если нет иных правил в коде — архитектор уточнит).
- Мобы/NPC — не затрагиваются (у мобов свой респавн).

### Вопросы к пользователю (если есть)
- [x] Скорость восстановления → 5% в час
- [x] Разная ли скорость для ресурсов → одинаково
- [x] Бонус за место → нет, будущая фича «дом»
- [x] Длительность сытости → ровно 24 часа реального времени
- [x] Бонус еды к восстановлению → по редкости: обычная +50%, редкая +100%, эпическая +150%, легендарная +200%
- [x] Редкости расходников → у еды, зелий, свитков, книг и т.п. максимум — легендарная. Мифическая, божественная и демоническая — только для снаряжения (админка не должна позволять их для расходников)
- [x] Что считается едой → отдельный признак «еда» у предмета в админке; еда может продаваться у NPC и выпадать в луте, не только создаваться поваром
- [x] Еда с мгновенным восстановлением → можно: при употреблении применяется и восстановление, и сытость
- [x] Когда можно есть → в бою нельзя; в подземелье и на сборе можно
- [x] Таймер сытости → идёт всегда (в бою/подземелье/на сборе тоже), на паузу встаёт только восстановление
- [x] Бонусы сытости → любые модификаторы, как у экипировки (характеристики, сопротивления, крит и т.д.)
- [x] Новая еда при активной сытости → запрет с сообщением «Вы уже наелись» (без замены)
- [x] Порядок редкостей → легендарная, мифическая, божественная и демоническая — один уровень с разным назначением (легендарная — сбалансированная, мифическая — под PvP, божественная/демоническая — против злых/добрых богов в будущем). Отдельного «старшинства» между ними нет
- [x] Ограничение редкости → **всё, что создаётся крафтом**, — максимум легендарная. Мифическое, божественное и демоническое бывает только у снаряжения. **Уточнение пользователя:** рецепты снаряжения (оружие, броня, украшения и т.п.) МОГУТ быть мифическими, божественными и демоническими — ограничение до легендарной касается только крафта не-снаряжения. Сюда же — нерасходуемые не-снаряжения (ресурсы, камни, руны и т.п.) и трансмутация: её цепочка заканчивается на легендарной
- [x] Лобби подземелья (группа собирается, вход не начат) → считается покоем, восстановление идёт

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Summary
No passive regeneration exists anywhere (confirmed: no scheduler, no timestamp column, no code path that raises `current_*` over time). Resources live only in `character_attributes` (owned by character-attributes-service, sync SQLAlchemy). **Two services write `current_*` with raw SQL that bypasses character-attributes-service** (battle-service at battle end, character-service on mob respawn), and **one service reads them with raw SQL** (party-service). Every other consumer goes through `GET /attributes/{id}`, which is the natural catch-up point. The time-buff system (`active_buffs`) exists in inventory-service, supports replace-on-same-type, but carries only one float `value`, has no stat-bonus concept, and only `xp_bonus` (crafting XP) is consumed anywhere. Stat bonuses today are applied **permanently and additively** via `POST /attributes/{id}/apply_modifiers` (equip/unequip, perks), so a time-limited stat bonus needs an explicit removal step at expiry.

### Affected Services
| Service | Type of Changes (expected) | Files |
|---------|----------------|-------|
| character-attributes-service | regen state (timestamp column), catch-up helper, hook into reads/writes, rest-state detection | `app/models.py`, `app/crud.py`, `app/main.py`, `app/schemas.py`, `app/constants.py`, new Alembic migration (`008_…`) |
| inventory-service | satiety buff on food use (replace semantics, 24h, rarity → bonus), stat bonus apply/remove, admin fields | `app/main.py` (`use_item` 1004, `use_buff_item` 3636, `get_active_buffs` 3703), `app/crud.py` (1931-2006), `app/models.py` (`Items` 53-55, `ActiveBuff` 344), `app/schemas.py` (188-191, 1139-1170), maybe Alembic `021_…` |
| battle-service | regen must be settled before battle snapshot; end-of-battle raw SQL write must keep regen bookkeeping consistent | `app/main.py` 196 (`build_participant_info`), 1837-1861, 1904-1914, 4002-4027 |
| character-service | `full_profile` reads via HTTP (no change needed if GET catches up); mob respawn raw SQL (mobs excluded, but must not break) | `app/main.py` 1868-2005, `app/crud.py` 1730-1744 |
| party-service | reads `current_health/current_mana` directly from DB → shows stale values unless regen is persisted or routed through HTTP | `app/crud.py` 64-85, 159-161 |
| locations-service / dungeon-service | read `current_stamina` via `GET /attributes/{id}` and spend via `consume_stamina` — benefit automatically if those endpoints catch up | locations `app/main.py` 1260, 1340, 1548, 1600; `app/crud.py` 7168-7215, 7387, 7545; dungeon `app/http_clients.py` 153-230, `app/gameplay.py` 1829-1852, 2658, 2844 |
| frontend | show satiety buff (24h timer, bonuses), admin food config, refresh of resource values | see §5 below |

### 1. Every read/write of `current_*` / `max_*`

**Owner: character-attributes-service** (`services/character-attributes-service/app/`)
- Model `models.py:18-27` (`current_health/mana/energy/stamina`, `max_*`; all `Integer`). No timestamp columns on the table at all (no `updated_at`).
- `crud.py:16-38` `compute_derived_stats` — recomputes `max_*` from base stats and clamps `current_*` to max. Used by `recalculate_attributes` (`crud.py:178`), `POST /{id}/recalculate` (`main.py:936`), `POST /admin/recalculate_all` (`main.py:1026`, batch over ALL rows incl. mobs; **ignores equipment modifiers**).
- `crud.py:68-107` `create_character_attributes` — sets `current_* = max_*` on creation (called from `POST /attributes/` `main.py:72` and RabbitMQ consumer `rabbitmq_consumer.py:47`).
- `crud.py:151-176` `refund_stamina` (row lock) → `POST /{id}/refund_stamina` `main.py:840`.
- `crud.py:526-620` `_apply_modifiers_internal` (perks) — changes `max_*` and shifts `current_*` by the same diff, clamped.
- `main.py:336-341` **`GET /attributes/{id}`** — plain read, returns ORM row. Main read path for everyone (see consumers below).
- `main.py:346-540` `POST /{id}/upgrade` (auth + ownership) — adds to max and current.
- `main.py:542-697` **`POST /{id}/apply_modifiers`** (`with db.begin()` + `with_for_update`) — equip/unequip/gems/sharpening; shifts max and current by the same diff, clamps to `[0, max]`. This is where "max dropped after unequip" is already handled (current is clamped).
- `main.py:700-731` **`POST /{id}/recover`** (row lock) — adds `*_recovery`, capped at max. Callers: inventory `use_item`, dungeon rest rooms/heals.
- `main.py:801-837` **`POST /{id}/consume_stamina`** — **no row lock** (plain read → subtract → commit). Callers: locations-service movement (`main.py:1340`, `1600`), gathering start (`crud.py:7168`), dungeon corridors (`gameplay.py:1852`).
- `main.py:879-933` `PUT /admin/{id}` — admin sets any field incl. `current_*` directly.
- `main.py:1155` `POST /internal/{id}/reconcile-perks` → perk evaluator → `_apply_modifiers_internal` (changes max/current).

**Raw-SQL writers outside the owner (bypass any hook placed in character-attributes-service):**
- battle-service `app/main.py:1837-1861` — end of every battle: `UPDATE character_attributes SET current_health/mana/energy/stamina = <Redis final values>` for all participants (incl. mobs).
- battle-service `app/main.py:1904-1914` — `pvp_training` loser: `SET current_health = 1`.
- battle-service `app/main.py:4002-4027` — admin force-finish / timeout sweeper (`_force_finish…`, FEAT-163): same UPDATE if Redis state exists.
- character-service `app/crud.py:1730-1744` — lazy mob respawn: `SET current_* = max_*` (mobs only).
- (locations-service `crud.py:5076` and character-service `crud.py:2134-2146, 2505` touch only `passive/active_experience`.)

**Raw-SQL readers outside the owner:**
- party-service `app/crud.py:64-85` — batched `SELECT current_health, max_health, current_mana, max_mana FROM character_attributes` (FEAT-151), surfaced in `crud.py:159-161` → frontend `PartyMemberCard.tsx:72`. **Will show pre-regen values** unless regen is persisted by someone else first.
- character-service `app/crud.py:1680-1706` (`_get_mob_hp_map`, mobs only), `crud.py:2801`, `2924` (`SELECT *` for NPC/mob admin views).

**HTTP readers of `GET /attributes/{id}`:**
- **battle-service** `battle_engine.py:26-31` `fetch_full_attributes` ← `main.py:196` `build_participant_info`, the single funnel for all battle starts: `_assemble_battle` (`main.py:621`, used by create/party/mob/dungeon battle endpoints at 773, 846, 941, 1015), `respond_to_pvp_invitation` (`main.py:3257`, snapshot at 3378), `pvp_attack` (`main.py:3558`, 3675), `admin_approve_join_request` (`main.py:4376`, 4445). The snapshot's `current_*`/`max_*` are copied into Redis state and never re-read from MySQL during the battle. → If `GET /attributes/{id}` settles regen, battle start automatically gets up-to-date values (edge case "перед началом боя досчитать").
- Note the ordering: `create_battle` (`crud.py:16`) inserts `battles`/`battle_participants` **before** `build_participant_info` fetches attributes, so at snapshot time the character is already "in battle" by the shared-DB check. A catch-up that skips in-battle characters would skip exactly this call; the regen accrued *up to* battle creation must still be credited (settle-then-stop semantics, not "skip if in battle").
- character-service `main.py:1926` (`GET /characters/{id}/full_profile` → `attributes.{health,mana,energy,stamina}.{current,max}` at 1984-2000), `main.py:1379`, `main.py:2844`.
- locations-service `main.py:1260`, `1548` (movement stamina check), `main.py:2600` (charisma), `crud.py:7198` (gathering stamina check).
- dungeon-service `http_clients.py:153` ← `gameplay.py:1158`, `1829`, `2841`, `2948`.
- frontend `profileSlice.ts:374-382` `fetchAttributes` → `GET /attributes/{id}`.

### 2. Detecting "in battle", "in dungeon", "gathering" and their time bounds

| State | Detection today | Start timestamp | End timestamp |
|---|---|---|---|
| Battle | shared-DB: `battles b JOIN battle_participants bp` with `b.status IN ('pending','in_progress') AND bp.dropped_out_at IS NULL` — copies in inventory `crud.py:784`, character-service `main.py:809`, battle-service `crud.py:79-97`; HTTP `GET /battles/character/{id}/in-battle` (`battle-service main.py:3040`) | `battles.created_at` (`models.py:50`, `datetime.utcnow`). **`battle_participants` has no `joined_at`** — late joiners (join requests) have no own start time | **No `battles.finished_at`.** `finish_battle` (`crud.py:63`) only sets `status`; `battles.updated_at` (`onupdate`) is bumped by it but also by pause/resume. `battle_participants.dropped_out_at` (UTC_TIMESTAMP, `main.py:5063`, `5138`) for drop-outs. `battle_history.finished_at` (`models.py:180`) is written only on normal finish (`main.py:2080`), not on force-finish |
| Dungeon | shared-DB: `dungeon_sessions ds JOIN dungeon_session_members dsm` with `ds.status IN ('forming','active')` (character-service `main.py:824`); Redis key per character (`dungeon-service session_state.py:214-238`) | `dungeon_sessions.started_at` (set at start, `gameplay.py:674-676`), null while `forming`; `created_at`; `dungeon_session_members.joined_at` | `dungeon_sessions.finished_at` set on completed/escaped (`gameplay.py:2434, 3167, 3217, 3324, 3662`) and cooldown path (`3612`). **`wiped` (`gameplay.py:1566`) sets status without `finished_at`** until the cooldown path runs. Members leaving during `forming` are **deleted** (`gameplay.py:552`), no `left_at` |
| Gathering | shared-DB: `gathering_sessions WHERE status='active' AND complete_at > NOW()` (inventory `crud.py:798-814`); owned by locations-service `models.py:718-778` | `started_at` (TIMESTAMP, `CURRENT_TIMESTAMP`) | `complete_at` (planned), `finished_at` (actual, nullable; set by lazy finalize), statuses `completed/cancelled/interrupted_by_battle/inventory_full` |

Observations: all three states are only queryable as "is active **now**", via shared-DB SQL. Historical intervals are fully available only for gathering; dungeon is mostly available; battle has no reliable per-participant end time. Nothing in character-attributes-service currently reads `battles`, `dungeon_sessions` or `gathering_sessions` (it already does raw SQL on `characters`, `crud.py:192`, `main.py:1051`, so cross-table reads are an established pattern there). All timestamps are naive UTC (containers must stay UTC — `docker-compose.yml:1-20`).

Every state change that ends a rest period goes through code that could "settle" regen first: battle creation (battle-service → `GET /attributes`), gathering start (locations-service → `GET /attributes` then `consume_stamina`), dungeon start/corridor (dungeon-service → `GET /attributes` / `consume_stamina`). Ends of those states, however, are **not** signalled to character-attributes-service at all (battle end writes raw SQL; dungeon/gathering end don't touch attributes).

### 3. ActiveBuff / time-buff system end to end
- **Item definition:** `Items.buff_type` (String(50)), `buff_value` (Float, fraction: 0.5 = +50%), `buff_duration_minutes` (Int) — `inventory-service/app/models.py:53-55`, migration `012_add_time_buffs.py`. Schemas `schemas.py:188-191`.
- **Active state:** `active_buffs` (`models.py:344-356`): `character_id`, `buff_type`, `value`, `expires_at` (naive UTC), `source_item_name`, `created_at`; **`UNIQUE(character_id, buff_type)`** → at most one buff per type per character. No item_id, no rarity, no stat payload.
- **Use:** `POST /inventory/{cid}/use-buff-item` (`main.py:3636-3700`): JWT + ownership, `check_not_in_battle`, `check_not_gathering`, row-lock on inventory row, consume 1, `crud.apply_buff` (`crud.py:1949-1982`) = **upsert that replaces value and resets `expires_at`** (replace semantics already exist), commit. Response message hardcodes "+N% XP".
- **Read:** `GET /inventory/{cid}/active-buffs` (`main.py:3703-3728`, auth + ownership) → `{buffs:[{id, character_id, buff_type, value, expires_at, source_item_name, remaining_seconds}]}`; `crud.get_active_buffs` deletes expired rows on read (lazy expiry, `crud.py:1985-1998`). `crud.get_active_buff` (1934) same for one type.
- **Consumers:** only `get_xp_multiplier` (`crud.py:2001`) → profession/crafting XP (`crud.py:1831`, `main.py:2543, 2718, 2908, 3183, 3331, 3513`). Nothing in any other service reads `active_buffs`. battle-service `buffs.py` is an unrelated in-battle effect system.
- **Stat bonuses from buffs: not implemented anywhere.** `active_buffs` has no field for them and no code path applies/removes attribute changes on buff start/expiry. Expiry is only detected lazily inside inventory-service.
- **How item stats are applied on equip:** `crud.build_modifiers_dict` (`crud.py:500-…`) maps `*_modifier` columns → attribute keys (`strength`, `health`, `res_fire`, …; resource keys `health/mana/energy/stamina` are **points**, converted to max via multipliers 10/10/5/5 in `constants.py`), plus sharpening/gems/durability. `equip_item` (`main.py:716-870`) calls `apply_modifiers_in_attributes_service(+mods)` (`main.py:661-667`) inside its DB transaction; unequip calls it with `negative=True`. `apply_modifiers` is **additive and persisted** into base columns (`strength`, `health`, …). Perks use the same pattern with grant/revoke (`crud.py:508` `build_perk_modifiers_dict(negative=…)`, `770-830`). → A satiety stat bonus via this mechanism needs a guaranteed "minus" on expiry/replacement; nothing will run it automatically at the 24h mark (no scheduler; inventory-service has no Celery). Note also `recalculate_all` recomputes from base stats and would not know about a temporary bonus (it already ignores equipment).
- **Admin UI:** `ItemsAdminPage/ItemForm.tsx:458-488` "Бафф" section for `consumable` only (`itemFormRules.ts:144`), select from `BUFF_TYPE_OPTIONS` (`itemFormRules.ts:99-102`, only `xp_bonus`), value in %, duration in minutes. Item modifiers section is enabled only for equipment/jewelry/gem/rune (`itemFormRules.ts:138`) — **not for consumables**, so a food stat bonus has no admin UI today.

### 4. How food / consumables are used today
- `item_type` enum (`models.py:15-19`): `consumable` exists; **no "food" type, subtype or flag**. The "Повар" profession exists (`professions.slug='cook'`, seeded in `alembic/versions/004_add_professions_crafting.py:139-146`), and `recipes.profession_id` → `recipes.result_item_id` (`models.py:278-293`) is the only link between an item and the cook; items themselves do not know who crafts them.
- `item_rarity` enum (`models.py:21-23`): `common, rare, epic, legendary, mythical, divine, demonic`. **UI order** (`frontend/src/constants/items.ts:57-59`, `RARITY_ORDER`): `common < rare < epic < mythical < legendary < divine < demonic`; backend `RARITY_IDENTIFY_LEVEL` (`crud.py:1897-1901`) groups `epic+mythical` below `legendary+divine+demonic`. The brief lists legendary (+200%) before mythical (+250%) — **conflicts with the game's rarity order** (see open questions).
- `POST /inventory/{cid}/use_item` (`main.py:1004-1047`): JWT + ownership, `check_not_gathering` (**no `check_not_in_battle`**), allowed types `consumable/scroll/misc/resource`, finds the first inventory row by `item_id` (no row lock), decrements, **commits, then** calls `POST /attributes/{cid}/recover` with `*_recovery × quantity` (if that HTTP call fails the item is already gone). Returns plain `{"status":"ok"}`.
- Frontend `ItemContextMenu.tsx:179-217`: consumable with `buff_type` set → `useBuffItem` (`/use-buff-item`), otherwise `useItem` (`/use_item`). So today an item is either a recovery consumable or a buff item, never both, by UI choice (backend `use-buff-item` ignores `*_recovery`).
- In battle, consumables are used from fast slots through battle-service + `POST /inventory/internal/characters/{id}/consume_item` (`main.py:1444`); unaffected.

### 5. Frontend: where resources and buffs are shown
- Resources: `components/ProfilePage/CharacterInfoPanel/StatsPanel.tsx:24-60` (uses `state.profile.attributes` from `GET /attributes/{id}`, falls back to `full_profile`), rendered in `CharacterInfoPanel.tsx:20` and `CharacterTab/IndicatorsPanel.tsx:44`; `StatsTab/ResourceStatsSection.tsx` (via `StatsTab.tsx:60`); party view `PartyTab/PartyMemberCard.tsx:72` (party-service data); `BattlePage.tsx` (Redis battle state — unaffected). Admin editors: `Admin/CharactersPage/tabs/AttributesTab.tsx`, `MobsPage/MobStatsEditor.tsx`, `AdminNpcsPage/NpcStatsEditor.tsx`.
- Data loading: `redux/slices/profileSlice.ts` — `fetchProfile` (325, `full_profile`), `fetchAttributes` (374-382), `useItem` (523, refreshes attributes), `fetchActiveBuffs` (613-625), `useBuffItem` (637-645, refreshes buffs), `loadProfileData` (711-727 loads both). Values are loaded once per page load; no polling — the displayed resource value is "current as of load", ticking would require client-side extrapolation or periodic refetch (architect decision).
- Active buffs: `components/ProfilePage/CraftTab/ActiveBuffIndicator.tsx` — **rendered only in the Craft tab** (`CraftTab.tsx:203`), labels only `xp_bonus`, shows `+N% label` and a `M:SS` timer (`formatTime`, would print "1440:00" for 24h), refetches on expiry. Already Tailwind + TS. No buff display on the main character/inventory view.
- `ActiveBuff` TS type at `profileSlice.ts:182`.

### 6. Tests, Alembic, patterns
- character-attributes-service: sync SQLAlchemy, Pydantic v1, Alembic head `007_add_pve_points.py` (`alembic_version_char_attrs`). Tests use in-memory SQLite with `database.engine` patched per file (e.g. `tests/test_refund_stamina.py:27-50`), `TestClient`, `conftest.py` stubs `aio_pika`. Existing relevant tests: `test_refund_stamina.py` (incl. concurrency via threads), `test_recalculate.py`, `test_stats_formulas.py`, `test_upgrade_formulas.py`, `test_perks.py`.
- inventory-service: sync, Alembic head `020_add_equipment_rules.py` (`alembic_version_inventory`), SQLite + `Base.metadata.create_all` in `tests/conftest.py:128`. **No tests exist for buffs** (`use-buff-item`, `active-buffs`, `apply_buff`). Related: `test_battle_lock.py`, `test_gathering.py`, `test_consume_item.py`, `test_craft_xp.py`.
- battle-service: async, Alembic head `006_add_dropout_and_admin_freeze.py`; tests `test_pvp_consequences.py`, `test_npc_death.py`, `_feat163_harness.py` touch the end-of-battle UPDATE.
- Shared-DB lookups (`battles`, `dungeon_sessions`, `gathering_sessions`) are **not in the SQLite schema** of character-attributes-service tests — any new cross-table SQL must be backed by test fixtures creating those tables with the **real column names**, otherwise errors get swallowed and tests stay green (the recurring "silent failure" pattern: wrong column + `except: pass` + fixture of wrong schema).
- nginx: `/attributes/` is proxied publicly (`nginx.conf:196`, `nginx.prod.conf:216`); only `/attributes/internal/` is blocked.

### Cross-Service Dependencies
- inventory-service → character-attributes-service: `POST /{id}/apply_modifiers`, `POST /{id}/recover`, `POST /internal/{id}/reconcile-perks`, `POST /cumulative_stats/increment`.
- battle-service → character-attributes-service: `GET /attributes/{id}` (battle start); raw SQL UPDATE on `character_attributes` (battle end).
- locations-service / dungeon-service → character-attributes-service: `GET /attributes/{id}`, `POST /consume_stamina`, `POST /refund_stamina`, `POST /recover`.
- character-service → character-attributes-service: `GET /attributes/{id}` (full_profile); raw SQL on `character_attributes` (mob respawn).
- party-service → shared DB `character_attributes` (raw SELECT).
- Satiety lives in inventory-service while regen lives in character-attributes-service → regen calculation needs the satiety multiplier and its expiry time (either character-attributes-service reads `active_buffs` from the shared DB, or inventory-service pushes it).

### DB Changes (likely)
- `character_attributes`: new nullable timestamp (e.g. last regen settle time) and possibly a fractional-remainder column(s) — Alembic migration in character-attributes-service (`008`). Backfill strategy for existing rows needed (NULL = "start counting now" to avoid a huge retroactive heal on deploy).
- inventory-service: a way to mark food and to store satiety stat bonuses / applied state (new columns on `items` and/or `active_buffs`) — Alembic `021` if schema changes. `active_buffs` unique `(character_id, buff_type)` already supports "one satiety at a time" if satiety uses one fixed `buff_type`.
- No permission rows needed unless new admin endpoints are added.

### Risks
- **Raw-SQL overwrite at battle end** (battle-service 1837, 4002, 1909): writes Redis values without touching regen bookkeeping. If the regen timestamp stays at a pre-battle moment, the next read credits the whole battle duration as rest. → Architect must define how the timestamp is reset at battle end (update the timestamp in the same raw UPDATE, or derive exclusion from battle rows — but battles lack `finished_at`/per-participant join time).
- **Battle start ordering**: participants are inserted before attributes are fetched; an "exclude if in battle" check inside `GET /attributes` would skip settling exactly when it's needed. → settle up to "now" / up to battle `created_at`, then stop.
- **Concurrent writes / lost updates**: GET becoming a writer means concurrent GET + `apply_modifiers`/`recover`/battle-end UPDATE on the same row. `consume_stamina` has no row lock today. → settle under `with_for_update`, idempotent w.r.t. timestamp; consider settling inside the existing locked writers.
- **Rounding**: 5%/h of small maxima (e.g. max_energy 50 → 2.5/h; with 1-min polling → 0.04/min) — integer columns plus frequent reads will round away regen if the timestamp advances on every read. → carry fractional remainder or advance the timestamp only by the time "consumed" by whole points.
- **Stale reads**: party-service raw SELECT and any future raw readers see unsettled values.
- **Mobs/NPCs**: they share the table (`characters.is_npc`, character-service `models.py:61`); `recalculate_all` and GET don't distinguish them. → exclude by `characters.is_npc` (or by absence of `user_id`) to honour "мобы не затрагиваются".
- **Temporary stat bonus**: `apply_modifiers` is permanent; expiry has no trigger. A missed "minus" leaves permanent stats; replacement of one food by another must remove the old bonus first. Also resource-point bonuses change `max_*` and shift `current_*` (unequip-like clamp behaviour on expiry).
- **use_item atomicity**: item is committed as consumed before the `/recover` HTTP call; same shape must not be copied for satiety (item consumed but buff/bonus not applied).
- **Timezones**: all involved columns are naive UTC (`datetime.utcnow`, `NOW()`, `UTC_TIMESTAMP()`); mixing `datetime.now()` would silently shift regen.
- **Security (pre-existing, logged to ISSUES.md)**: `POST /attributes/{id}/recover`, `/apply_modifiers`, `/consume_stamina`, `/refund_stamina`, `PUT /{id}/passive_experience`, `PUT /{id}/active_experience` are reachable through the public gateway with no auth — anyone can already heal or buff any character; regen/satiety values are cosmetic until that is closed.

### Open questions for PM/user
1. **Rarity order conflict**: the game orders rarities `обычная < редкая < эпическая < мифическая < легендарная < божественная/демоническая`. The brief says legendary +200%, mythical +250%. Should it be mythical +200%, legendary +250% (following the game's order)?
2. **What counts as "food"**: items don't know they were made by a cook. Options: a new flag/type on the item set in admin ("еда"), or "any consumable with the satiety buff type". Can non-cook foods (NPC shop, loot) also give satiety?
3. **Food that also restores resources** (`health_recovery` etc.): should eating apply both the instant recovery and satiety? Today an item is either a recovery consumable or a buff item.
4. **Replace vs. forbid** when satiety is active (architect may decide, but user-visible).
5. **Eating in battle / dungeon / while gathering**: `use-buff-item` blocks battle and gathering; `use_item` blocks only gathering. Is eating allowed inside a dungeon?
6. **Does satiety's 24h keep ticking during battle/dungeon/gathering** (only regen pauses)? Assumed yes (real time).
7. **Satiety stat bonus scope**: all equipment-style modifiers (incl. resistances, crit), or only main stats?


---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Overview of the chosen design

| Concern | Decision |
|---|---|
| Where regen lives | **character-attributes-service** (owner of `current_*`/`max_*`). Lazy "settle" helper runs under the row lock on every read/write path of a character's attributes. |
| Where satiety lives | **character-attributes-service**, new table `character_satiety` (one row per character, `UNIQUE(character_id)`). Not in `active_buffs`: regen math, stat-bonus apply and stat-bonus removal must happen in **one transaction under one row lock** in the service that owns the stats — this is what makes expiry removal reliable without a scheduler. |
| What is food | New `items.is_food` flag (inventory-service). Food must be `item_type='consumable'`. Food reuses the existing `*_recovery` and `*_modifier` columns of `items`. |
| Eating | New `POST /inventory/{character_id}/eat-food` (inventory-service, JWT + ownership) → internal `POST /attributes/internal/{character_id}/satiety` (atomic: settle → reject if satiated → apply modifiers → apply instant recovery → insert satiety) → only on success the inventory row is decremented. |
| Busy (no regen) | Computed from shared-DB **intervals** (battle / dungeon / gathering) that overlap the settle window, not from a "busy now" flag. Rest time = window minus union of busy intervals. |
| Battle end | The 3 raw-SQL writers in battle-service additionally set `regen_anchor_at = UTC_TIMESTAMP()`. New `battle_participants.joined_at` gives the exact start of battle time for late joiners. |
| Rounding | Per-resource fractional carry columns (`regen_carry_*`), anchor always moves to `now` → lossless regardless of read frequency. |
| Mobs/NPCs | Skipped: `characters.is_npc = 1` → settle is a no-op (anchor stays NULL). |
| Rarity cap (non-equipment + crafting) | `mythical/divine/demonic` exist **only on equipment** (`head, body, cloak, belt, ring, necklace, bracelet, weapon`) and never come from crafting. Every other `item_type` (consumable, resource, scroll, misc, blueprint, recipe, gem, rune, gathering_tool, and any future non-equipment type) is capped at `legendary` (backend validator + admin UI). Recipes whose `rarity` or result item is above legendary are rejected. Transmutation chain ends at `legendary`. Legendary/mythical/divine/demonic are one tier with different purposes — **nothing in this design ranks them**; the cap is a set-membership check, not an ordering. |

### 3.1 Regen algorithm (character-attributes-service)

Constants (`app/constants.py`):
```python
REGEN_PERCENT_PER_HOUR = 5.0            # % of max per real hour, all 4 resources
SATIETY_DURATION_HOURS = 24
SATIETY_REGEN_BONUS_BY_RARITY = {"common": 0.5, "rare": 1.0, "epic": 1.5, "legendary": 2.0}
REGEN_RESOURCES = ("health", "mana", "energy", "stamina")
```

New module `app/regen.py` (sync, pure functions + one DB helper):

1. `merge_intervals(intervals) -> list[(start, end)]` and `overlap_seconds(window_start, window_end, intervals) -> float` — pure, unit-testable.
2. `load_busy_intervals(db, character_id, window_start, now) -> list[(start, end)]` — three parameterized raw-SQL queries; **`now` and `window_start` are passed as bind parameters** (no `NOW()`/`UTC_TIMESTAMP()` inside these queries, so the same SQL works on MySQL and in SQLite tests):
   - **Battle (active or dropped out):**
     ```sql
     SELECT COALESCE(bp.joined_at, b.created_at) AS s,
            COALESCE(bp.dropped_out_at, :now)     AS e
     FROM battle_participants bp JOIN battles b ON b.id = bp.battle_id
     WHERE bp.character_id = :cid
       AND ( (b.status IN ('pending','in_progress'))
          OR (bp.dropped_out_at IS NOT NULL AND bp.dropped_out_at > :ws) )
     ```
     Finished battles need no interval: battle end resets the anchor (3.3).
   - **Dungeon (only `active` counts; `forming` lobby = rest — confirmed by the user):**
     ```sql
     SELECT ds.started_at AS s,
            COALESCE(ds.finished_at, CASE WHEN ds.status = 'active' THEN :now ELSE ds.started_at END) AS e
     FROM dungeon_session_members dsm JOIN dungeon_sessions ds ON ds.id = dsm.session_id
     WHERE dsm.character_id = :cid AND ds.started_at IS NOT NULL AND ds.started_at < :now
       AND ( ds.status = 'active' OR ds.finished_at > :ws )
     ```
     (Legacy `wiped` rows with NULL `finished_at` collapse to a zero-length interval; dungeon-service is fixed to always set `finished_at` on wipe — task #6.)
   - **Gathering:**
     ```sql
     SELECT started_at AS s,
            status, complete_at, finished_at   -- end computed in Python:
            -- active   -> min(complete_at, now)
            -- otherwise -> COALESCE(finished_at, complete_at)
     FROM gathering_sessions
     WHERE character_id = :cid AND started_at < :now
       AND COALESCE(finished_at, complete_at) > :ws
     ```
     (`min(e, now)` is applied in Python, not SQL, for portability.)
   All intervals are clipped to `[window_start, now]` in Python.
3. `settle_regen(db, attr, now=None) -> bool` — **the only entry point**; caller must already hold `attr` via `with_for_update()` inside a transaction. Steps:
   1. If character is NPC (`SELECT is_npc FROM characters WHERE id=:cid`; missing row ⇒ treat as NPC/skip) → return False.
   2. `sat = character_satiety row` (if any).
   3. If `attr.regen_anchor_at is None` → set anchor = now, carries = 0, then go to step 7 (expiry) — no retroactive heal on deploy/creation.
   4. If `now <= anchor` → go to step 7.
   5. If all four `current_* >= max_*` → no interval queries needed; carries = 0.
      Else: `busy = load_busy_intervals(...)`. Split window at `t1 = clamp(sat.expires_at, anchor, now)` (if no satiety: `t1 = anchor`):
      - `bonus_h = (t1 - anchor - overlap(anchor, t1, busy)) / 3600`
      - `plain_h = (now - t1 - overlap(t1, now, busy)) / 3600`
      - For each resource r: if `current_r >= max_r`: `carry_r = 0`; else
        `gain = max_r * REGEN_PERCENT_PER_HOUR/100 * (bonus_h * (1 + sat.regen_bonus) + plain_h) + carry_r`;
        `whole = floor(gain)`; `current_r = min(max_r, current_r + whole)`; `carry_r = 0 if current_r == max_r else gain - whole`.
      - (Satiety `started_at` ≥ anchor is guaranteed because eating settles first.)
   6. `anchor = now`.
   7. **Expiry:** if `sat` and `sat.expires_at <= now` → apply `sat.modifiers` with `negative=True` through the existing `_apply_modifiers_internal` path (resource keys shift `max_*`/`current_*` and clamp, exactly like unequip), then `DELETE` the satiety row, all in the caller's transaction. Return True ("stats changed") so the endpoint can trigger perk reconciliation after commit.
   8. Errors in `load_busy_intervals` are **not swallowed silently**: log at ERROR with character id, skip steps 5–6 (no credit, anchor not moved — safe direction), still run step 7. Never `except: pass`.
   - Re-entrancy: `_apply_modifiers_internal` and perk evaluation do **not** call settle themselves; settle is invoked once at the endpoint/transaction boundary. Calling settle twice in a row is a no-op (idempotent: elapsed = 0, expired row already deleted).
   - Health at 0 regenerates like any other value (no existing rule forbids it).
   - `max_*` decreased → existing clamps in apply_modifiers keep `current ≤ max`; settle also never exceeds max.

Where `settle_regen` is called (all under `with_for_update`, commit at the end):
| Path | Change |
|---|---|
| `GET /attributes/{id}` | becomes lock → settle → commit → return (response schema unchanged) |
| new `GET /attributes/{id}/rest-status` | lock → settle → commit → build response |
| `POST /{id}/recover`, `/apply_modifiers`, `/refund_stamina`, `/upgrade`, `PUT /admin/{id}` | settle first, then existing logic (admin PUT: settle, then admin values overwrite; anchor stays `now`) |
| `POST /{id}/consume_stamina` | **add `with_for_update()`** (currently missing), settle, then existing check |
| `POST /internal/{id}/reconcile-perks` | settle first |
| `POST /attributes/internal/{id}/satiety` (new) | settle first |
| `POST /attributes/internal/settle-regen` (new, bulk) | settle each id |
| `create_character_attributes` | set `regen_anchor_at = utcnow()` |
| `POST /admin/recalculate_all`, `/{id}/recalculate` | unchanged (they only clamp) |

If settle reported an expiry (stats changed), the endpoint calls the perk evaluator after commit, wrapped in try/except with a WARNING log (same pattern as inventory `_reconcile_perks`).

### 3.2 Satiety

Rules: 24 h real time from eating, always ticking; one at a time; regen bonus by rarity (3.1 constants); stat modifiers = the food item's `*_modifier` columns (all keys supported by `apply_modifiers`: stats, resource points, damage, dodge, crit, res_*, vul_*); instant recovery = food's `*_recovery` × 1 (eat one item per call).

Removal paths (all idempotent because the row is deleted in the same transaction that subtracts the modifiers):
- expiry detected by any settle (any read of the character's attributes, including battle start, profile load, party list via bulk settle);
- no other removal path exists (no replacement — eating while satiated is rejected).
Accepted limitation: until someone reads the character after `expires_at`, the stale bonus still sits in the base columns; every consumer that *uses* stats (battle start, profile, dungeon, gathering) reads via `GET /attributes/{id}`, which settles first, so the stale bonus is never used in gameplay. Raw-SQL readers (party-service) are covered by bulk settle (task #7).

### 3.3 Battle-service changes

- `battle_participants.joined_at DATETIME NULL` (model default `datetime.utcnow`) — set for every insert path (create_battle, invitation accept, pvp_attack, join-request approve). NULL for historical rows ⇒ `COALESCE(joined_at, battles.created_at)`.
- The three raw updates (`main.py` ~1837 normal finish, ~1909 pvp_training loser, ~4002 force-finish/timeout) add `regen_anchor_at = UTC_TIMESTAMP()` to their `SET` list. `regen_carry_*` are left untouched.
- Battle start needs no change: `build_participant_info` → `GET /attributes/{id}` settles up to `joined_at` (the participant row already exists, so the interval `[joined_at, now]` is excluded, rest before it is credited — "settle-then-stop").

### 3.4 API Contracts

#### `GET /attributes/{character_id}` (changed behaviour, same contract)
Now settles regen + satiety expiry before returning. Response schema `CharacterAttributesResponse` unchanged (new columns are **not** exposed). 404 unchanged.

#### `GET /attributes/{character_id}/rest-status` (new, public read-only)
Path param: `character_id: int`. No body.
**Response 200:**
```json
{
  "character_id": 12,
  "is_resting": true,
  "busy_reason": null,
  "base_regen_percent_per_hour": 5.0,
  "regen_percent_per_hour": 10.0,
  "satiety": {
    "item_id": 345,
    "source_item_name": "Жаркое из кабана",
    "rarity": "rare",
    "regen_bonus_percent": 100,
    "modifiers": {"strength": 2, "res_fire": 1.5},
    "started_at": "2026-09-17T10:00:00",
    "expires_at": "2026-09-18T10:00:00",
    "remaining_seconds": 72000
  }
}
```
`busy_reason`: `null | "battle" | "dungeon" | "gathering"` (first match in that order, derived from intervals whose end == now). `satiety` is `null` when none. `regen_percent_per_hour` = base × (1 + bonus) while satiated (shown regardless of busy). NPC → 200 with `is_resting=false`, `busy_reason=null`, `satiety=null`. 404 `"Атрибуты персонажа не найдены"`.
Pydantic v1 schemas: `SatietyInfo`, `RestStatusResponse` (`class Config: orm_mode = True` where relevant). Must be registered **before** any conflicting `/{character_id}/...` catch-alls (none today; keep it explicit).

#### `POST /attributes/internal/{character_id}/satiety` (new, internal)
**Request:**
```json
{
  "item_id": 345,
  "source_item_name": "Жаркое из кабана",
  "rarity": "rare",
  "modifiers": {"strength": 2, "health": 1, "res_fire": 1.5},
  "recovery": {"health_recovery": 50, "mana_recovery": 0, "energy_recovery": 0, "stamina_recovery": 0}
}
```
Validation (Pydantic v1 `SatietyApplyRequest`): `rarity ∈ SATIETY_REGEN_BONUS_BY_RARITY` else 400 `"Недопустимая редкость еды"`; `modifiers` keys ⊆ the key set accepted by apply_modifiers (unknown key → 400), values numeric; `recovery` values ≥ 0 ints; `source_item_name` ≤ 200 chars.
**Response 201:** `{ "satiety": <SatietyInfo>, "stats_changed": true }`
**Errors:** 404 attributes not found; 409 `"Вы уже наелись"` (non-expired satiety exists after settle); 400 validation.
Transaction: lock attr → settle → check → apply modifiers (+) → apply recovery capped at (new) max → insert row with `started_at=now`, `expires_at=now+24h`, `regen_bonus` from rarity → commit → perk reconcile (best effort).

#### `POST /attributes/internal/settle-regen` (new, internal, bulk)
**Request:** `{ "character_ids": [1, 2, 3] }` (1..50 unique ints, else 422/400).
**Response 200:** `{ "settled": [1, 2], "missing": [3] }`. Each id settled in its own short transaction (lock → settle → commit) to avoid multi-row lock ordering issues.

#### `POST /inventory/{character_id}/eat-food` (new, public, JWT)
**Request:** `{ "inventory_item_id": 987 }`
**Response 200:**
```json
{
  "success": true,
  "message": "Вы поели: Жаркое из кабана. Сытость на 24 ч",
  "satiety": { "...": "SatietyInfo as above" }
}
```
**Errors:** 401/403 (auth/ownership, existing helpers); 400 `"Нельзя есть во время боя"` (`check_not_in_battle`); 404 `"Предмет не найден в инвентаре"`; 400 `"Этот предмет нельзя съесть"` (not `is_food`); 409 `"Вы уже наелись"` (passed through from attributes); 400 passthrough of attributes validation detail; 502 `"Не удалось применить сытость, попробуйте позже"` (attributes unreachable/5xx — inventory row is NOT decremented).
Flow: ownership → battle check (gathering and dungeon **allowed**) → lock inventory row (`with_for_update`) → load item, require `is_food` → build `modifiers = crud.build_modifiers_dict(item)` (no sharpening/gems/durability) and `recovery` from `*_recovery` → sync `httpx.post(.../internal/{cid}/satiety, timeout=5)` → on 201 decrement quantity (delete row at 0) → commit → return. If the commit fails after a 201, log ERROR (satiety granted, item not consumed — accepted, extremely unlikely).

#### Rarity cap rules (inventory-service, see 3.11)
Constants in `app/constants.py` (or wherever item enums/constants live in the service):
```python
EQUIPMENT_ITEM_TYPES = {"head", "body", "cloak", "belt", "ring", "necklace", "bracelet", "weapon"}
EQUIPMENT_ONLY_RARITIES = {"mythical", "divine", "demonic"}   # a set, NOT an ordering
```
Rule: `item_rarity in EQUIPMENT_ONLY_RARITIES` requires `item_type in EQUIPMENT_ITEM_TYPES` (the check is "type is not equipment", so any new non-equipment type is capped automatically).

#### Changed inventory endpoints
- `POST /inventory/items`, `PUT /inventory/items/{id}` — accept `is_food: bool = False`; validation in `ItemCreate` root validator:
  - `is_food=True` ⇒ `item_type == 'consumable'` else 400/422 `"Едой может быть только расходуемый предмет"`; `is_food=True` ⇒ `buff_type` must be empty (`"Еда не может быть баффовым предметом"`).
  - `item_type ∉ EQUIPMENT_ITEM_TYPES` and `item_rarity ∈ EQUIPMENT_ONLY_RARITIES` ⇒ 400/422 `"Мифическая, божественная и демоническая редкость доступны только для снаряжения"`.
  - `schemas.Item` (response) exposes `is_food`.
- `POST /inventory/{cid}/use_item` and `/use-buff-item`: reject `is_food` items with 400 `"Еду нужно съесть"` (prevents satiety bypass).
- `POST /inventory/admin/recipes`, `PUT /inventory/admin/recipes/{id}` (existing permissions unchanged): reject with 400 `"Крафт не может создавать предметы мифической, божественной или демонической редкости"` when `recipe.rarity ∈ EQUIPMENT_ONLY_RARITIES` **or** the result item's `item_rarity ∈ EQUIPMENT_ONLY_RARITIES` (applies to equipment results too). On update, validate the effective values (payload merged with the stored row).
- Transmutation (list of transmutable items + transmute endpoint, `main.py` ~2767–2940): `RARITY_CHAIN = {common: rare, rare: epic, epic: legendary}`; `'mythical'` removed from `TRANSMUTE_RESULT_NAMES`. Legendary resources are no longer listed as transmutable; transmuting one returns the existing "cannot transmute" 400.
- Fast slots / battle: equipping a food item into a `fast_slot_*` is rejected (400 `"Еду нельзя положить в быстрый слот"`), and `POST /inventory/internal/characters/{id}/consume_item` rejects `is_food` (defence in depth) — eating in battle is forbidden.

### 3.11 Existing data for the rarity cap
Prod has exactly one non-equipment item above legendary: the mythical transmutation resource («Трансмутированный ресурс (мифический)»). Decision: **leave the row untouched** (no rarity downgrade, no delete) — players may hold it in inventory/auction or it may be a recipe ingredient; downgrading would also clash semantically with the existing legendary transmutation resource. It becomes **unobtainable** because the transmutation chain stops at legendary. The validator applies only on admin create/update, so the row remains readable/usable; if an admin edits it, the save requires a rarity ≤ legendary (the admin UI shows the reason). Migration 021 only **logs** (does not modify) ids/names of non-equipment items and recipes with equipment-only rarity so the deploy log documents them.

### 3.12 User correction — recipe rarity cap (2026-09-17, overrides 3.0 / 3.4 / 4a / 10a where they conflict)
**Superseded (2026-09-17, later user decision):** recipes have no quality of their own — the admin form no longer sends `rarity`; the recipe's `rarity` in responses always equals the result item's rarity; the cap is enforced on the result item (non-equipment result with mythical/divine/demonic → 400). Rarity is not displayed for `recipe`/`blueprint` items anywhere in the UI. Earlier note: The recipe admin must **not** blanket-forbid mythical/divine/demonic. These rarities are allowed for a recipe whose result item is wearable equipment (`EQUIPMENT_ITEM_TYPES`); they are rejected/hidden only when the result item is a non-equipment type. Item form rule is unchanged: non-equipment item types are capped at legendary. Frontend (#10a) implements this; the backend recipe validator (#4a) and its tests (#12) must follow the same rule — PM to confirm with Backend Dev / QA.

### 3.5 Security Considerations
- `GET /attributes/{id}/rest-status` — public read like `GET /attributes/{id}` (profile data is public today); read-only apart from settle, which is deterministic and cannot be abused to gain resources (repeated calls are idempotent thanks to carry + anchor). No rate limit beyond the gateway defaults.
- `POST /attributes/internal/{id}/satiety` and `/internal/settle-regen` — under `/attributes/internal/`, already blocked by nginx in both `nginx.conf` and `nginx.prod.conf` (verified: `location /attributes/internal/`). No new gateway rules needed. **Does not worsen** the pre-existing ISSUES.md entry (public `/recover`, `/apply_modifiers`): no new public mutation endpoint is added.
- `POST /inventory/{cid}/eat-food` — JWT via `get_current_user_via_http` + `verify_character_ownership`; row lock prevents double-spend of one item; one-satiety rule enforced server-side under the attributes row lock (two parallel eats → second gets 409).
- Input validation: strict Pydantic schemas (above); all SQL parameterized; error messages in Russian, no internal details.
- Admin: item create/update keep `items:create` / `items:update`. **No new permissions → no RBAC migration.**

### 3.6 DB Changes

**character-attributes-service — `app/alembic/versions/008_add_regen_and_satiety.py`** (`down_revision = '007…'`):
```sql
ALTER TABLE character_attributes
  ADD COLUMN regen_anchor_at DATETIME NULL,
  ADD COLUMN regen_carry_health  FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN regen_carry_mana    FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN regen_carry_energy  FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN regen_carry_stamina FLOAT NOT NULL DEFAULT 0;

CREATE TABLE character_satiety (
  id INT AUTO_INCREMENT PRIMARY KEY,
  character_id INT NOT NULL,
  item_id INT NULL,
  source_item_name VARCHAR(200) NULL,
  rarity VARCHAR(20) NOT NULL,
  regen_bonus FLOAT NOT NULL,
  modifiers JSON NOT NULL,
  started_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL,
  CONSTRAINT uq_character_satiety_character UNIQUE (character_id),
  INDEX ix_character_satiety_expires_at (expires_at)
);
```
Backfill: none — `regen_anchor_at` stays NULL; first settle starts the clock (no retroactive heal). Idempotent guards (check column/table existence via inspector) as in earlier migrations.
Downgrade: drop table + columns. **Operational rollback note (in migration docstring):** before downgrading, strip active satiety bonuses: `UPDATE character_satiety SET expires_at = UTC_TIMESTAMP();` then call `POST /attributes/internal/settle-regen` for all `character_id`s in that table (or `GET /attributes/{id}` per id) so the negative modifiers are applied; otherwise the bonuses stay permanently in base stats.

**inventory-service — `app/alembic/versions/021_add_item_is_food.py`** (`down_revision='020…'`):
```sql
ALTER TABLE items ADD COLUMN is_food BOOLEAN NOT NULL DEFAULT 0;
```
Downgrade: drop column. No data changes. Existing consumables with mythical/divine/demonic rarity are **not** modified; the migration only logs (`print`/logger) their count; the admin must lower their rarity on next edit (validator will force it).

**battle-service — `app/alembic/versions/007_add_participant_joined_at.py`** (`down_revision='006…'`):
```sql
ALTER TABLE battle_participants ADD COLUMN joined_at DATETIME NULL;
```
Downgrade: drop column. Historical rows stay NULL (COALESCE to `battles.created_at`).

Mirror models: photo-service has no `character_attributes`/`items` column dependency for these fields (verify with grep in task #1/#4; add mirror columns only if its mirror model is used for INSERTs — it is not expected).

### 3.7 Frontend Components

- `redux/slices/profileSlice.ts`
  - types: `SatietyInfo`, `RestStatus` (mirrors 3.4), `is_food?: boolean` on the inventory item type.
  - state: `restStatus: RestStatus | null`, `restStatusError: string | null`.
  - thunks: `fetchRestStatus(characterId)` → `GET /attributes/{id}/rest-status`; `eatFood({characterId, inventoryItemId})` → `POST /inventory/{id}/eat-food`, on success dispatch `fetchAttributes`, `fetchRestStatus`, inventory refresh; rejects with backend `detail` (Russian) or `"Не удалось съесть предмет"`.
  - `loadProfileData` also dispatches `fetchRestStatus`.
- **New** `components/ProfilePage/CharacterInfoPanel/RestStatusPanel.tsx` (Tailwind, TS, no `React.FC`, design-system classes `gold-text`, `gray-bg` lightly, "airy" layout):
  - line "Восстановление: N% в час" (+ "приостановлено: в бою / в подземелье / на сборе ресурсов" when `!is_resting`);
  - satiety card when present: «Сытость» + item name coloured by rarity (existing rarity colour tokens), remaining time `«23 ч 15 мин»` (helper `formatHoursMinutes`, minutes granularity, `<1 мин` for the tail), `+100% к восстановлению`, list of stat modifiers with Russian labels (reuse the existing stat-label map used by item tooltips);
  - local 30 s ticker; when remaining hits 0 → refetch `fetchRestStatus` + `fetchAttributes`;
  - also refetches both every 5 minutes while mounted (keeps resource values current on a long-open page);
  - error from `restStatusError` shown as a small Russian message (no silent failure);
  - mobile: single column, wraps at 360px.
  - rendered in `CharacterInfoPanel.tsx` under `StatsPanel` (main profile view, visible next to the resources).
- `components/ProfilePage/InventoryTab/ItemContextMenu.tsx` — for `is_food` items show action «Съесть» (dispatch `eatFood`), hide «Использовать»; success toast with backend `message`, error toast with backend `detail` (e.g. «Вы уже наелись»).
- `components/ItemsAdminPage/itemFormRules.ts` + `ItemForm.tsx`:
  - checkbox «Еда» visible only for `consumable`; when checked: hide the «Бафф» section, enable the modifiers section (rule `modifiersEnabled = equipment types || is_food`), keep recovery fields; hint text «Сытость 24 ч, бонус к восстановлению по редкости: обычная +50%, редкая +100%, эпическая +150%, легендарная +200%».
  - rarity select: for `consumable/scroll/recipe/blueprint` only common/rare/epic/legendary are offered; switching type to one of these with a forbidden rarity resets rarity to `common` with a visible note; backend 400 detail displayed.
  - `is_food` included in the create/update payload and in the admin item type(s).
- Item tooltip / type line: show «Еда» for `is_food` consumables (small, where the item type line is already rendered). Only if that component is already TS/Tailwind; otherwise skip (not required).
- Party card (`PartyMemberCard.tsx`) — no change (backend bulk-settles before reading).

### 3.8 Data Flow Diagrams

Eating:
```
Player → ItemContextMenu «Съесть» → POST /inventory/{cid}/eat-food (JWT)
  inventory-service: ownership, not-in-battle, lock inventory row, is_food?
    → POST character-attributes-service /attributes/internal/{cid}/satiety
        lock character_attributes → settle_regen → satiety exists? 409 «Вы уже наелись»
        → apply +modifiers → recover → INSERT character_satiety → COMMIT → reconcile perks
    ← 201
  decrement inventory → COMMIT → 200 {message, satiety}
Frontend → fetchAttributes + fetchRestStatus + inventory refresh
```
Lazy regen + expiry (any read):
```
Frontend / battle-service / dungeon / locations / character-service
  → GET /attributes/{cid}
     lock row → is_npc? → busy intervals (battles, dungeon_sessions, gathering_sessions)
     → credit rest time (bonus part until expires_at, plain after) with carry
     → expired satiety? apply −modifiers, DELETE row → COMMIT → (perk reconcile)
```
Battle lifecycle:
```
battle-service create: INSERT battles, battle_participants(joined_at=now)
  → GET /attributes/{cid} (settles up to joined_at, busy after) → Redis snapshot
battle end / force-finish: UPDATE character_attributes SET current_*=…, regen_anchor_at=UTC_TIMESTAMP()
```
Party list:
```
party-service get members → POST /attributes/internal/settle-regen {ids} (best effort, 2 s timeout)
  → existing raw SELECT current_health/mana…
```

### 3.9 Cross-service validation
- `GET /attributes/{id}` response unchanged → battle-service `fetch_full_attributes`, character-service `full_profile`, locations-service, dungeon-service, frontend unaffected (only latency: +1–4 small indexed queries and a write).
- New columns have defaults → raw INSERTs elsewhere (none known for `character_attributes`/`items`/`battle_participants` outside owners) keep working. Reviewer greps for `INSERT INTO character_attributes`, `INSERT INTO items`, `battle_participants` raw inserts.
- character-service mob respawn raw UPDATE: untouched; mobs are skipped by settle.
- `recalculate_all` recomputes max from base stats that already contain satiety modifiers (same as equipment) → consistent.
- Deadlock risk: GET now takes `FOR UPDATE` on a single row; battle-service fetches participants sequentially per id; bulk settle uses one transaction per id. Acceptable.
- Timezones: all new timestamps naive UTC (`datetime.utcnow()` / `UTC_TIMESTAMP()`); busy queries use bind params.

### 3.10 Risks
1. **Satiety bonus left in stats if nobody reads the character after expiry** — harmless for gameplay (every gameplay read settles first) but visible via raw DB reads/admin SQL. Mitigated by bulk settle in party-service; admin `SELECT *` views for NPCs are unaffected (NPCs cannot eat).
2. **Cross-service non-atomicity of eating** — satiety applied but item not consumed if inventory commit fails after 201 (logged). Reverse (item lost, no satiety) is impossible by design.
3. **Existing non-equipment items / recipes with equipment-only rarity** (prod: one mythical transmutation resource) stay as-is and are only logged by migration 021; the item becomes unobtainable (chain ends at legendary); an admin editing it must choose a non-equipment-only rarity. Other runtime producers of items (e.g. essence extraction) output admin-configured items, which the item validator already covers — Reviewer greps for any other hardcoded `'mythical'`/`'divine'`/`'demonic'` producer.
4. **Dropped-out participant**: battle-end update resets anchor for all participants, so rest time between drop-out and battle end is lost (minor under-credit).
5. **Pre-fix `wiped` dungeon sessions** without `finished_at` are ignored (zero interval) — could over-credit only for sessions wiped after deploy and before task #6 ships (ship together).
6. **GET /attributes becomes a writer** — higher DB write load; settle is O(1) and interval queries are skipped when all resources are full.
7. **Pre-existing security issue** (public `/attributes/{id}/recover` etc.) still makes resources forgeable — tracked in ISSUES.md, not in scope.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | character-attributes-service: migration 008 (columns + `character_satiety` table, idempotent, downgrade + operational rollback note in docstring); model `CharacterSatiety` + new columns on `CharacterAttributes`; constants from 3.1 | Backend Developer | DONE | `services/character-attributes-service/app/alembic/versions/008_add_regen_and_satiety.py`, `app/models.py`, `app/constants.py` | — | `alembic upgrade head` and `downgrade -1` work on MySQL (container); `py_compile` passes; version table `alembic_version_char_attrs` |
| 2 | character-attributes-service: `app/regen.py` (`merge_intervals`, `overlap_seconds`, `load_busy_intervals`, `settle_regen` exactly per 3.1 incl. NPC skip, carry, satiety split, expiry removal via `_apply_modifiers_internal(negative)`, logged-not-swallowed query errors, bind-param `now`); wire settle into all paths of the 3.1 table (GET becomes lock+settle+commit; add `with_for_update` to `consume_stamina`; anchor on create); perk reconcile after expiry | Backend Developer | DONE | `app/regen.py` (new), `app/main.py`, `app/crud.py` | #1 | GET response schema unchanged; no `NOW()` in busy SQL; no bare `except: pass`; `py_compile` passes |
| 3 | character-attributes-service: new endpoints `GET /attributes/{id}/rest-status`, `POST /attributes/internal/{id}/satiety`, `POST /attributes/internal/settle-regen` with Pydantic v1 schemas and error texts from 3.4 | Backend Developer | DONE | `app/main.py`, `app/schemas.py`, `app/crud.py` | #2 | Contracts match 3.4 exactly; 409 «Вы уже наелись»; satiety apply is a single transaction; `py_compile` passes |
| 4 | inventory-service: migration 021 (`items.is_food`; logs — does not modify — non-equipment items and recipes with equipment-only rarity, see 3.11); model + `ItemBase`/`Item` schema field; `ItemCreate` validators (food ⇒ consumable, food ⇒ no buff_type, non-equipment type ⇒ rarity not in `EQUIPMENT_ONLY_RARITIES`, Russian messages); `EQUIPMENT_ITEM_TYPES` / `EQUIPMENT_ONLY_RARITIES` constants (sets, no ordering) | Backend Developer | DONE | `services/inventory-service/app/alembic/versions/021_add_item_is_food.py`, `app/models.py`, `app/schemas.py` | — | Create/update item with `is_food` persists and is returned; forbidden combos rejected with Russian detail; up/downgrade works; `py_compile` passes |
| 4a | inventory-service: recipe admin create/update reject equipment-only rarity (`recipe.rarity` or result item rarity, incl. equipment results; update validates merged values); transmutation `RARITY_CHAIN` ends at legendary and `'mythical'` removed from `TRANSMUTE_RESULT_NAMES`; grep for other hardcoded equipment-only-rarity producers and report | Backend Developer | DONE | `app/main.py` (~2150–2285, ~2767–2940), `app/crud.py` (`create_recipe`/`update_recipe`), `app/schemas.py` | #4 | Recipe with mythical/divine/demonic rarity or result → 400 with Russian detail; legendary resources not listed as transmutable and transmuting them → 400; existing mythical resource row untouched; `py_compile` passes |
| 5 | inventory-service: `POST /inventory/{cid}/eat-food` per 3.4 (sync httpx to attributes internal endpoint, item decremented only after 201, 409/400/502 mapping, perk reconcile best-effort); reject `is_food` in `use_item`, `use-buff-item`, fast-slot equip and internal `consume_item`; add attributes URL helper in existing style | Backend Developer | DONE | `app/main.py`, `app/schemas.py`, `app/crud.py` (if helpers needed) | #3, #4 | Eating while satiated returns 409 «Вы уже наелись» and item stays; attributes down → 502 and item stays; in battle → 400; allowed while gathering / in dungeon; `py_compile` passes |
| 6 | battle-service: migration 007 `battle_participants.joined_at`; model default `utcnow`; ensure every participant insert path sets it; add `regen_anchor_at = UTC_TIMESTAMP()` to the three raw `UPDATE character_attributes` statements. dungeon-service: set `finished_at` when a session becomes `wiped` | Backend Developer | DONE | `services/battle-service/app/alembic/versions/007_add_participant_joined_at.py`, `app/models.py`, `app/crud.py`, `app/main.py`; `services/dungeon-service/app/gameplay.py` | #1 (column must exist before deploy order matters — same release) | Raw UPDATEs contain the anchor reset; late-join path sets `joined_at`; wipe sets `finished_at`; `py_compile` passes; existing battle/dungeon tests still pass |
| 7 | party-service: before the batched raw SELECT of member resources, call `POST {ATTRIBUTES_SERVICE_URL}internal/settle-regen` (sync httpx, timeout 2 s, failure → WARNING log, continue) | Backend Developer | DONE | `services/party-service/app/crud.py` (or `main.py`, following existing httpx pattern) | #3 | Party member card values reflect regen; party-service works if attributes-service is down; `py_compile` passes |
| 8 | Update service docs: new endpoints, tables, regen/satiety rules, battle anchor reset, `joined_at`, `is_food` | Backend Developer | DONE | `docs/services/character-attributes-service.md`, `docs/services/inventory-service.md`, `docs/services/battle-service.md`, `docs/services/party-service.md` | #2–#7 | Docs describe contracts from 3.4 |
| 9 | Frontend: profileSlice types/state/thunks (`fetchRestStatus`, `eatFood`, `loadProfileData`); new `RestStatusPanel.tsx` in CharacterInfoPanel (timer «ч/мин», bonuses, busy note, 30 s ticker, 5 min refetch, refetch on expiry, error display); ItemContextMenu «Съесть» for `is_food` | Frontend Developer | DONE | `src/redux/slices/profileSlice.ts`, `src/components/ProfilePage/CharacterInfoPanel/RestStatusPanel.tsx` (new), `CharacterInfoPanel.tsx`, `src/components/ProfilePage/InventoryTab/ItemContextMenu.tsx` | #3, #5 (contract only — can start from 3.4) | Tailwind only, TS, no `React.FC`, works at 360px, all API errors shown in Russian; `npx tsc --noEmit` and `npm run build` pass (inside container) |
| 10 | Frontend admin: `is_food` checkbox (consumable only), modifiers section enabled for food, buff section hidden for food, rarity select offers mythical/divine/demonic only for equipment types (every non-equipment type → common..legendary; switching type resets a forbidden rarity with a visible note), no rarity ranking introduced, hint text, backend errors displayed; `is_food` in payload/types; «Еда» in item type line if that component is already TS | Frontend Developer | DONE | `src/components/ItemsAdminPage/ItemForm.tsx`, `src/components/ItemsAdminPage/itemFormRules.ts`, related admin item types | #4 (contract only) | Admin can create food with modifiers and recovery; cannot pick mythical/divine/demonic for any non-equipment type; tsc + build pass; mobile layout OK |
| 10a | Frontend recipe admin: rarity select without mythical/divine/demonic; result-item picker hides (or marks unavailable) items with equipment-only rarity; backend 400 detail displayed in Russian. **User correction (2026-09-17):** mythical/divine/demonic ARE offered when the result item is equipment (head/body/cloak/belt/ring/necklace/bracelet/weapon); hidden/blocked only for a non-equipment result (see 3.12) | Frontend Developer | DONE | `src/components/Admin/RecipesAdminPage/RecipesAdminPage.tsx`, `src/api/professions.ts` (types if needed) | #4a (contract only) | Such a recipe cannot be submitted from the UI; errors shown; Tailwind/TS rules respected for touched parts; tsc + build pass; mobile OK |
| 11 | QA: character-attributes-service tests — pure interval math; settle: rest credit, carry on small maxima (max_energy 50, many reads 1 min apart ⇒ total equals single read), cap at max + carry reset, NULL anchor ⇒ no retroactive heal, NPC skipped, busy exclusion for **each** of battle (active, dropped-out, late join via `joined_at`), dungeon (active, finished, forming lobby ⇒ regen credited), gathering (active, finished, overdue active), battle participant already inserted at GET ⇒ time before `joined_at` credited; satiety split at expiry mid-window; expiry removes modifiers exactly once (two consecutive GETs), resource-point modifiers shift/clamp max/current; satiety endpoint 201/409/400 + recovery; rest-status shape; settle-regen bulk; query-failure path logs and credits nothing. Fixtures must create `characters`, `battles`, `battle_participants`, `dungeon_sessions`, `dungeon_session_members`, `gathering_sessions` with the **real column names** from the owning models, and at least one test must fail if a busy query errors (guards the silent-failure pattern) | QA Test | DONE | `services/character-attributes-service/app/tests/test_regen.py`, `test_satiety.py` (+ conftest fixtures) | #2, #3 | `pytest` green in container |
| 12 | QA: inventory-service tests — item validators (food type, food+buff; mythical/divine/demonic rejected for **every** non-equipment type incl. resource/gem/rune/misc/gathering_tool/recipe/blueprint/scroll/consumable, and accepted for each equipment type); recipe admin create/update rejects equipment-only `rarity` and equipment-only result item (also for an equipment result, and on update via stored values); transmutation: legendary resource not listed and not transmutable, epic→legendary still works, no path yields mythical; eat-food: success (item decremented, correct modifiers/recovery payload sent — mock httpx), 409 passthrough with item kept, 502 with item kept, in-battle 400, gathering allowed, not-food 400, foreign character 403; use_item/use-buff-item/consume_item reject food | QA Test | DONE | `services/inventory-service/app/tests/test_food_satiety.py`, `test_item_rarity_rules.py`, `test_recipe_transmute_rarity_cap.py` | #4, #4a, #5 | `pytest` green |
| 13 | QA: battle-service — the three end-of-battle UPDATEs include the anchor reset (assert SQL executed/column updated in existing harness), `joined_at` set on create and late join; party-service — settle-regen called before SELECT and failure tolerated; dungeon-service — wipe sets `finished_at` | QA Test | DONE | `services/battle-service/app/tests/test_regen_anchor_reset.py`, `services/party-service/app/tests/test_settle_before_read.py`, `services/dungeon-service/app/tests/…` (existing style) | #6, #7 | `pytest` green in all three services |
| 14 | Review: contracts vs 3.4, migrations up/down, security (internal endpoints blocked by nginx, auth on eat-food), no silent failures, frontend rules (Tailwind/TS/no React.FC/mobile/Russian errors), build/tsc/pytest/py_compile re-run, live check: eat food → satiety visible with timer, second eat → «Вы уже наелись», resources grow after time shift (manipulate `regen_anchor_at` in dev DB), battle start/end anchor behaviour | Reviewer | TODO | all | #1–#13 (incl. #4a, #10a) | Checklist passed, live verification done |

Deploy note: tasks #1, #4, #6 migrations ship in the same release; order-independent (each service migrates its own tables; battle-service raw UPDATE requires #1's column, so character-attributes-service must be migrated before the first battle ends — both start in the same `docker compose up`; the existing UPDATE is inside try/except with an ERROR log, so a race would skip a resource sync — therefore #6 **must** retry the old UPDATE (without the anchor) when the anchored one fails with an unknown-column error, and log a WARNING).

### Backend implementation notes / deviations (Backend Developer, 2026-09-17)

1. **Recipe rarity cap — user correction (overrides 3.4 / #4a):** a recipe whose **result is equipment** may be mythical/divine/demonic. `_ensure_recipe_rarity_allowed` rejects equipment-only rarity (recipe `rarity` or result item rarity) **only when the result item is a non-equipment type**. Non-equipment items stay capped at legendary; transmutation still ends at legendary.
   - **Second user decision — recipes have no quality, only the result item does:**
     - `recipes.rarity` is derived from the result item's `item_rarity` in `crud.create_recipe` and on every `crud.update_recipe` (column kept for `RARITY_XP_MAP` / `?rarity=` filter). `RecipeCreate.rarity` / `RecipeUpdate.rarity` are now optional, deprecated and **ignored** (backward compatible: old payloads still validate).
     - The cap check `_ensure_recipe_rarity_allowed(result_item)` only looks at the result item (`schemas.is_rarity_allowed_for_type`); update checks the new or stored result item.
     - Auto-created recipe items (`item_type='recipe'`) are rarity-neutral: always stored as `common` (`crud.RECIPE_ITEM_RARITY`, NOT NULL column). Frontend contract: hide rarity for `item_type === 'recipe'` (and `'blueprint'`); do not send/show a recipe rarity selector; show the result item's rarity instead (response field `rarity` = result item rarity).
     - Existing rows are not backfilled: legacy recipes keep their stored rarity and legacy recipe items keep theirs until the recipe is next saved.
   - Migration 021 logs only recipes whose result is non-equipment (matches the corrected rule).
2. **Busy-interval SQL (3.1):** the `COALESCE(..., :now)` / `CASE` parts were moved from SQL to Python. SQL selects raw columns (`bp.joined_at, b.created_at, bp.dropped_out_at`; `ds.started_at, ds.finished_at, ds.status`; `started_at, status, complete_at, finished_at`) with the same WHERE filters and bind params. Reason: `COALESCE(DATETIME, bound string)` returns a string on MySQL/pymysql and SQLite; values are normalized by `regen.to_datetime` (accepts datetime or ISO string, so SQLite fixtures work).
3. **`is_npc` lookup failure** (e.g. a test DB without `characters`, or a transient DB error) is logged with `logger.exception` and treated as "no regen" (anchor untouched); satiety expiry still runs. Missing `characters` row ⇒ skipped, as designed.
4. **Satiety modifiers are applied/removed with `_apply_modifiers_internal(..., propagate_derived=False)`** — equipment-style (the public `apply_modifiers` used by equip does not propagate derived resists/dodge either), and the exact negation is subtracted on expiry.
5. **`consume_stamina`:** when stamina is insufficient, the settle result is still committed before the 400 is raised (the settle itself is a legitimate write).
6. **`POST /attributes/internal/{id}/satiety` 409 path** commits the settle (regen credit / expiry of an older satiety) before returning 409.
7. **`consume_item` (internal, battle)** rejects food with 400 «Еду нельзя использовать в бою» (message not specified in 3.4).
8. **`battle_participants.joined_at`** is set explicitly in `crud.create_battle` (one timestamp for all participants) and in the join-request approve path, plus a model default. The two raw end-of-battle UPDATEs and the pvp_training UPDATE go through `_execute_with_anchor_fallback` (retry without the anchor + WARNING only when the error mentions `regen_anchor_at` as an unknown column). The `SET current_health` prefix is kept first so the FEAT-163 fake-DB harness still matches.
10. **Fix after QA (float boundary):** `regen._credit_regen` now floors `gain + REGEN_FLOAT_EPSILON` (1e-9) and clamps carry with `max(0.0, gain - whole)`, so float error (e.g. 3599.9999999999995 s of rest) no longer defers a whole point by one read. The two strict-xfail marks in `test_regen.py` (`TestRestCredit::test_many_reads_match_single_read_at_integer_boundary`, `TestEndpointWiring::test_participant_inserted_before_get_exact_points`) were removed; both pass.
9. **party-service:** `crud.settle_regen` is called inside `get_attributes_map` (chunks of 50, timeout 2 s, WARNING on failure). `docs/services/party-service.md` does not exist, so it was not created (no new doc files); the behaviour is described in `docs/services/character-attributes-service.md`.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-17
**Result:** FAIL

The backend, migrations, cross-service contracts and tests are solid and verified live, but the main player-facing part of the feature (the rest/satiety panel) is never rendered.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/ProfilePage/CharacterInfoPanel/CharacterInfoPanel.tsx:23` | **BLOCKING.** `RestStatusPanel` was added to `CharacterInfoPanel`, but that panel is only rendered by `ProfilePage/InventoryTab/InventoryTab.tsx:59`, and **`InventoryTab` is not imported anywhere** (dead code since the FEAT-149 layout; `ProfilePage.tsx:65` renders `CharacterTab` → `CharacterPanel` / `IndicatorsPanel` / `InventoryPanel`). Confirmed live with headless Chromium on `/profile` (1440px and 360px) while the character had an active satiety: neither «Восстановление» nor «Сытость» is on the page. Players never see the regen rate, the satiety timer or its bonuses. Fix: render `<RestStatusPanel />` in `CharacterTab/IndicatorsPanel.tsx` (under the resource bars/StatsPanel), check it at 360px, and re-run tsc + build. | Frontend Developer | FIX_REQUIRED |
| 2 | `services/character-attributes-service/app/tests/test_regen.py:659-660`, `tests/test_satiety.py:420-421` | **Test-count discrepancy explained (non-blocking, recommended).** 343 passed + 10 skipped comes from a run with **only the service folder mounted**, not the full repo. In that layout the 6 `TestSharedSchemaMatchesOwners` owner-model checks (they guard exactly the silent-failure pattern: wrong column name in the busy-interval SQL) and the 2 nginx `/attributes/internal/` guard tests `pytest.skip()` because the sibling files are missing. The other 2 skips are the pre-existing SQLite `refund_stamina` concurrency tests. With the full repo mounted (the CI layout: `actions/checkout` + `cd services/.../app`) I got **351 passed, 2 skipped, 1 xpassed**. So CI does run the guards, but a run inside the service container (`/app` only) silently skips them. Recommendation: skip only when explicitly allowed (e.g. `pytest.fail` when `os.environ.get("CI")` is set, or fail unless `ALLOW_PARTIAL_CHECKOUT=1`) so a CI layout change can never turn the guards into silent skips. | QA Test | RECOMMENDED |
| 3 | `services/frontend/app-chaldea/src/components/ItemsAdminPage/ItemForm.tsx:274-276` | Minor, pre-existing pattern. The new item validators return **422** with `detail` as a list (`[{msg: "Мифическая…"}]`). The form only shows string `detail`, so a 422 would show the English axios text «Request failed with status code 422». Not reachable today because the UI blocks the same combinations client-side. Suggest extracting `detail[0].msg` for 422. | Frontend Developer | RECOMMENDED |

#### Pre-existing issues noted (not blocking)
- `services/character-attributes-service/app/tests/test_refund_stamina.py:207,265`: the skip reasons say "the test runs in CI / Verified on MySQL CI", but CI has no MySQL service, so these concurrency tests never run anywhere. Their text is misleading.
- The unauthenticated public `/attributes/{id}/recover` etc. are already tracked in ISSUES.md (added by the Analyst).

#### Verified OK
- **Contracts 3.4:** `GET /attributes/{id}` (schema unchanged), `GET /{id}/rest-status`, `POST /internal/{id}/satiety` (201/409/400/404), `POST /internal/settle-regen` (1..50 unique ids), `POST /inventory/{id}/eat-food` (JWT + ownership, 400 in battle, allowed while gathering, 409 passthrough, 502 on attributes failure; the item is decremented only after 201). Pydantic `SatietyInfo` matches the TS `SatietyInfo`/`RestStatus`/`EatFoodResult`; frontend URLs match the backend routes.
- **inventory → attributes payload:** `build_modifiers_dict` emits only non-zero keys, all within `VALID_FLAT_BONUS_KEYS`; `ATTRIBUTES_SERVICE_URL` (`…:8002/attributes/`) is set in compose and config for inventory and party.
- **Raw SQL vs real schema (`SHOW COLUMNS` on dev MySQL):** `battle_participants.joined_at/dropped_out_at`, `battles.status/created_at`, `dungeon_sessions.started_at/finished_at/status`, `dungeon_session_members.session_id/character_id`, `gathering_sessions.started_at/complete_at/status/finished_at`, `characters.is_npc` all exist. MySQL time_zone = SYSTEM = UTC (`NOW() == UTC_TIMESTAMP()`), so TIMESTAMP columns are consistent with `utcnow()`.
- **No silent swallows on local writes:** busy-query / is_npc failures are logged with `logger.exception` and no credit is given (safe direction); endpoint DB errors → 500 with a Russian message; the battle-service anchor fallback retries only on an unknown `regen_anchor_at` column and re-raises anything else (the outer handler logs ERROR, as before); party-service settle is best-effort with a WARNING (deliberate, as designed). All party-service endpoints are sync, so the sync httpx call does not block an event loop.
- **Migrations:** 008 / 021 / 007 applied automatically on `docker compose up` (`alembic_version_char_attrs=008_add_regen_and_satiety`, `alembic_version_inventory=021_add_item_is_food`, `alembic_version_battle=007_participant_joined_at`); `character_satiety` DDL matches 3.6 (unique + expires index).
- **Rarity cap:** no other hardcoded mythical/divine/demonic producer (grep); transmutation chain ends at legendary; recipe rarity derived from the result item, recipe items stored as `common`, rarity hidden for recipe/blueprint in the UI (per user decision).
- **Security:** nginx returns 403 for `/attributes/internal/*` (live); eat-food without a token → 401; no secrets; parameterized SQL; user-facing texts in Russian.
- **Frontend rules:** new/changed code is TS + Tailwind, no `React.FC`, no new SCSS; `RestStatusPanel` layout wraps (min-w-0, flex-wrap); API errors are shown (toast / `restStatusError`); the recipes admin no longer swallows the items-list error.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (0 errors)
- [x] `npm run build` (frontend container) — PASS
- [x] `py_compile` (31 changed/new .py files, python:3.10 container) — PASS
- [x] `pytest` (python:3.10 containers, full repo mounted, CI args) — PASS: character-attributes 351 passed / 2 skipped (SQLite concurrency) / 1 xpassed; inventory 732 passed; battle 515 passed; party 39 passed; dungeon 126 passed (exit 0). Service-only mount of character-attributes: 343 passed / 10 skipped / 1 xpassed (see issue #2).
- [x] `docker compose config` — PASS
- [ ] Live verification — **FAIL** (backend flow PASS, UI panel not rendered)

#### Live Verification Results
- API (via api-gateway, admin login, character 706): rest-status 200 (`is_resting=true`, 5%/h); 404 «Атрибуты персонажа не найдены» for an unknown id; creating a mythical consumable → 422 «Мифическая, божественная и демоническая редкость доступны только для снаряжения»; `is_food` on a resource → 422 «Едой может быть только расходуемый предмет»; rare food created (`is_food=true` in the response); `use_item` on food → 400 «Еду нужно съесть»; eat #1 → 200 «Вы поели: … Сытость на 24 ч» (strength +2, res_fire +1.5, 24h), eat #2 → **409 «Вы уже наелись»**, item kept (qty 1); rest-status shows the satiety, regen 10%/h.
- Regen: anchor −2h → HP 100→150 and MP 10→25 (10%/h with satiety), carry stored. Active battle joined 1h ago → only 1h credited (HP 100→125), rest-status `busy_reason="battle"`. Satiety `expires_at` in the past → modifiers removed exactly once (strength 22→20, res_fire 2.5→1; second GET unchanged), row deleted, rate back to 5%. Eat in battle → 400 «Нельзя есть во время боя»; eat while gathering → 200, rest-status `busy_reason="gathering"`.
- Browser (headless Chromium in a container on the compose network, `/profile`, 1440px and 360px): no HTTP ≥400, no horizontal overflow; the only console errors are the Vite HMR websocket (`ws://localhost:5555`, an artifact of loading the dev server through the gateway from a container, unrelated). **The rest/satiety panel is absent** (issue #1). The «Съесть» context-menu action was not clicked in the browser (verified through the API only).
- Test data cleaned up (test item deleted, satiety expired and removed, character 706 resources/anchor restored); the dev stack was stopped afterwards (it was not running before).

### Review #2 — 2026-09-17
**Result:** PASS

Both review #1 findings are fixed, the recommendations are applied, and the whole feature is verified in the browser.

#### Fixes verified
| # (review #1) | Verification | Status |
|---|---|---|
| 1 | `RestStatusPanel` is mounted in `ProfilePage/CharacterTab/IndicatorsPanel.tsx` under `StatsPanel` (the dead `CharacterInfoPanel.tsx` is back to its original content). Rendered live on `/profile` at 1440px and 360px. | FIXED |
| 2 | `tests/regen_shared_tables.py::skip_or_fail_missing` is used by the owner-model guards (`test_regen.py:661`) and the nginx guards (`test_satiety.py:422`). With only the service folder mounted and `CI=true`, the 8 guards **fail** («CI is set but … not found»); locally without `CI` they still skip with an explicit reason. The never-running `refund_stamina` concurrency tests are tracked in ISSUES.md (LOW). | FIXED |
| 3 | `ItemForm.tsx:133-150` `saveErrorMessage` shows list `detail[].msg` (without the Pydantic "Value error, " prefix) and a Russian network-error text; used by the submit handler (`:299`). | FIXED |

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS
- [x] `npm run build` (frontend container) — PASS
- [x] `pytest` character-attributes-service (whole repo mounted, `CI=true`, CI args) — PASS: 351 passed, 2 skipped (SQLite concurrency, tracked), 1 xpassed. Partial mount + `CI=true` → the 8 guards fail as intended. The other services were not changed since review #1 (their results are in review #1).
- [x] `docker compose config` — PASS (review #1, compose files unchanged)
- [x] Live verification — PASS

#### Live Verification Results
- Headless Chromium on the compose network, admin, character 706, `/profile` (the «Персонаж» tab).
- 1440px, before eating: «Восстановление: 5% в час», no satiety card.
- An epic food item was created via the admin API (2 pcs). Clicking the item opens the context menu with **«Съесть»** (and no «Использовать»); `ItemContextMenu` is mounted by `CharacterTab.tsx`. Clicking «Съесть» ate the item, and the panel updated without a reload: «Восстановление: 12.5% в час», card «Сытость · осталось 24 ч 0 мин · FEAT164 Ревью-жаркое (rarity colour) · +150% к восстановлению · Сила +1», strength 20→21.
- Clicking «Съесть» a second time → toast **«Вы уже наелись»** (seen on the screenshot), the item is kept (qty 1).
- 360px (mobile context): the panel and satiety card are visible and fit (card x 56–304 px), no horizontal overflow on either width.
- Console: the only non-HMR entry is the browser's own "Failed to load resource: 409" for the intended second eat (the expected error path, shown to the user as a toast); everything else is Vite HMR websocket noise (a container-access artifact). No other HTTP ≥400.
- Not captured: the text of the first (success) toast — the locator raced the toast animation; success was confirmed by the panel update and the inventory count.
- Cleanup: satiety expired and removed (strength back to 20), character 706 resources/anchor restored, test item deleted, stack stopped, `chaldea_default` network removed, no containers running.

#### Pre-existing issues noted (not blocking)
- `DELETE /inventory/items/{id}` returns 500 when the item is still in someone's inventory (FK `character_inventory_ibfk_1`, no check or handling in `delete_item`). Found while cleaning up; the test item was removed directly in MySQL. Added to ISSUES.md (LOW).

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-17 16:21 — PM: фича создана по итогам обсуждения ребаланса профессий (этап 1 из 3), запускаю анализ
[LOG] 2026-09-17 16:30 — Analyst: начал анализ: character-attributes, inventory, battle, dungeon, locations, party, frontend
[LOG] 2026-09-17 17:10 — Analyst: обнаружена уязвимость (публичные /attributes/{id}/recover, apply_modifiers и др. без авторизации), добавлена в ISSUES.md
[LOG] 2026-09-17 17:15 — Analyst: анализ завершён, затронуто 5 бэкенд-сервисов + фронтенд; есть открытые вопросы (порядок редкостей, что считать едой)
[LOG] 2026-09-17 17:20 — PM: пользователь ответил на вопросы аналитика (раздел 1 обновлён), запускаю архитектора
[LOG] 2026-09-17 17:30 — Architect: начал проектирование
[LOG] 2026-09-17 18:20 — Architect: сытость хранится в character-attributes-service (снятие бонусов атомарно при ленивом пересчёте), восстановление считается по интервалам боя/подземелья/сбора с дробным остатком
[LOG] 2026-09-17 18:25 — Architect: спроектировано 14 задач, 5 API-контрактов (3 новых эндпоинта атрибутов, eat-food, изменения предметов), 3 миграции; статус IN_PROGRESS
[LOG] 2026-09-17 18:50 — Architect: по ответам пользователя расширен лимит редкости: всё не-снаряжение и всё из крафта — максимум легендарная, трансмутация заканчивается на легендарной, мифический ресурс на проде остаётся, но становится недоступным; лобби подземелья = покой; добавлены задачи 4a и 10a, обновлены QA
[LOG] 2026-09-17 19:00 — Frontend Dev: начал задачи #9, #10, #10a
[LOG] 2026-09-17 19:40 — Frontend Dev: задача #9 завершена — profileSlice (fetchRestStatus, eatFood, restStatus), новая панель RestStatusPanel в профиле (скорость восстановления, пауза, сытость с таймером «ч/мин», бонусы, обновление раз в 5 мин и по окончании сытости), пункт «Съесть» в контекстном меню
[LOG] 2026-09-17 19:55 — Frontend Dev: задача #10 завершена — галочка «Еда» у расходуемых, для еды открыты модификаторы и скрыт бафф, мифическая/божественная/демоническая редкость только для снаряжения (при смене типа редкость сбрасывается с пояснением), «Еда» в строке типа предмета
[LOG] 2026-09-17 20:05 — Frontend Dev: по уточнению пользователя в рецептах мифическая/божественная/демоническая редкость доступна, если результат — снаряжение; для не-снаряжения скрыта и блокируется (раздел 3.12). Задача #10a завершена
[LOG] 2026-09-17 20:10 — Frontend Dev: tsc --noEmit и npm run build в контейнере frontend прошли без ошибок
[LOG] 2026-09-17 21:00 — Frontend Dev: по решению пользователя у рецептов нет своего качества: из админки рецептов убран выбор редкости (rarity не отправляется), качество результата показывается только для чтения, клиентская проверка опирается на редкость результирующего предмета; ошибки бэкенда выводятся
[LOG] 2026-09-17 21:10 — Frontend Dev: у рецептов и чертежей редкость скрыта везде (форма предмета, список предметов в админке, строка типа, ячейки инвентаря и перетаскивание, аукцион, лавка NPC, обмен, лут, редактор лавки NPC); tsc и build в контейнере прошли
[LOG] 2026-09-17 22:00 — Frontend Dev: исправления по ревью №1: панель восстановления/сытости перенесена в живой профиль (CharacterTab → IndicatorsPanel, под полосками ресурсов), из неиспользуемого CharacterInfoPanel убрана; проверено, что меню «Съесть» (ItemContextMenu), ячейки инвентаря и перетаскивание используются в текущем профиле; форма предмета показывает русские тексты ошибок 422 (список msg); tsc и build в контейнере прошли
[LOG] 2026-09-17 17:45 — PM: пользователь уточнил: всё, что крафтится, не выше легендарной; лобби подземелья = покой. Прошу архитектора поправить дизайн
[LOG] 2026-09-17 19:00 — Backend Dev: начал задачи #1–#8
[LOG] 2026-09-17 19:30 — Backend Dev: задачи #1–#3 завершены (character-attributes-service: миграция 008, regen.py, пересчёт во всех путях, эндпоинты rest-status / satiety / settle-regen)
[LOG] 2026-09-17 19:50 — Backend Dev: задачи #4, #4a, #5 завершены (inventory-service: is_food, миграция 021, лимит редкости, рецепты, трансмутация до легендарной, eat-food, запрет еды в use_item/use-buff-item/быстрых слотах/consume_item)
[LOG] 2026-09-17 19:55 — Backend Dev: по уточнению пользователя рецепты со снаряжением в результате могут быть мифическими/божественными/демоническими; предмет-рецепт при этом получает легендарную редкость (вопрос к PM)
[LOG] 2026-09-17 20:05 — Backend Dev: задачи #6, #7 завершены (battle-service: joined_at + миграция 007, сброс якоря восстановления в конце боя с откатом на старый UPDATE; dungeon-service: finished_at при вайпе; party-service: settle-regen перед чтением ресурсов)
[LOG] 2026-09-17 20:10 — Backend Dev: задача #8 завершена — обновлены docs/services/character-attributes-service.md, inventory-service.md, battle-service.md (party-service.md в репозитории нет)
[LOG] 2026-09-17 20:30 — Backend Dev: проверки: py_compile ок; pytest в контейнерах — attributes 233 passed, inventory 522 passed, battle 490 passed, party 28 passed, dungeon все зелёные; миграции 008/021/007 upgrade → downgrade → upgrade на MySQL ок (021 залогировал «Трансмутированный ресурс (мифический)», id=30); смоук settle_regen на dev-БД (с откатом) — SQL интервалов занятости рабочий
[LOG] 2026-09-17 20:45 — Backend Dev: по решению пользователя у рецептов нет качества: редкость рецепта берётся из результата, rarity в запросе игнорируется, предметы-рецепты хранятся как common
[LOG] 2026-09-17 21:15 — Backend Dev: исправлен баг округления в _credit_regen (эпсилон при floor, остаток не уходит в минус), сняты два strict-xfail в test_regen.py; тесты character-attributes-service: 343 passed, 10 skipped, 1 xpassed
[LOG] 2026-09-17 19:00 — PM: уточнение пользователя — рецепты снаряжения могут быть мифическими/божественными/демоническими; разработчики оповещены
[LOG] 2026-09-17 20:40 — QA: начал задачи #11–#13
[LOG] 2026-09-17 21:30 — QA: задача #11 завершена — character-attributes-service: test_regen.py, test_satiety.py + общий харнесс regen_shared_tables.py (таблицы боёв/подземелий/сбора/персонажей с реальными именами колонок, сверка с моделями сервисов-владельцев); мутационная проверка: опечатка в любой колонке запроса занятости роняет 55+ тестов
[LOG] 2026-09-17 21:35 — QA: найден баг округления: _credit_regen округляет вниз без эпсилона — при частых чтениях и при старте боя (микросекунды в now) очко восстановления приходит на одно чтение позже (не теряется, остаётся в carry); два теста помечены xfail(strict) до исправления
[LOG] 2026-09-17 21:40 — QA: тестовая модель characters в test_damage_from_class.py дополнена колонкой is_npc (как на проде), иначе create_all создавал таблицу без неё
[LOG] 2026-09-17 22:05 — QA: задача #12 завершена — inventory-service: test_item_rarity_rules.py, test_food_satiety.py, test_recipe_transmute_rarity_cap.py (рецепты — по новому правилу: редкость берётся из результата, предмет-рецепт всегда «обычный»)
[LOG] 2026-09-17 22:20 — QA: задача #13 завершена — battle-service test_regen_anchor_reset.py (+ учёт сброса якоря в харнессе FEAT-163, проверка joined_at у одобренной заявки), party-service test_settle_before_read.py (settle_regen замокан в test_party_enrichment.py), dungeon-service test_wipe_finished_at.py
[LOG] 2026-09-17 22:25 — QA: обнаружен посторонний хрупкий тест в battle-service (зависит от порядка файлов), добавлен в ISSUES.md
[LOG] 2026-09-17 22:30 — QA: прогоны в контейнерах: attributes 349 passed + 2 xfailed (новый баг) + 1 xpassed (старый), inventory 732 passed, battle 515 passed, party 39 passed, dungeon 126 passed
[LOG] 2026-09-17 23:00 — QA: по итогам ревью 8 сторожевых тестов (сверка колонок с моделями сервисов-владельцев, блокировка /attributes/internal/ в nginx) теперь падают при CI=true, если файлов другого сервиса нет; локально — пропуск с понятной причиной. CI (actions/checkout@v4) выкачивает весь репозиторий
[LOG] 2026-09-17 23:00 — QA: два старых пропускаемых теста конкурентности в test_refund_stamina.py не запускаются нигде (в CI нет MySQL) — добавлено в ISSUES.md
[LOG] 2026-09-17 23:05 — QA: attributes, весь репозиторий смонтирован: 351 passed, 2 skipped (старые), 1 xpassed — одинаково без CI и с CI=true (баг округления уже исправлен, xfail сняты); только app без репозитория: 8 skipped без CI, 8 failed с CI=true — как задумано
[LOG] 2026-09-17 22:45 — Reviewer: начал проверку
[LOG] 2026-09-17 23:40 — Reviewer: причина расхождения тестов найдена: 8 «лишних» пропусков — защитные тесты схемы/nginx, которые пропускаются при монтировании только папки сервиса; при полном репозитории (как в CI) — 351 passed, 2 skipped
[LOG] 2026-09-17 23:50 — Reviewer: живая проверка API пройдена (еда, «Вы уже наелись», восстановление, пауза в бою, снятие сытости); панель восстановления на странице профиля не отображается — компонент встроен в неиспользуемую вкладку
[LOG] 2026-09-17 23:55 — Reviewer: проверка завершена, результат FAIL (1 блокирующая проблема для Frontend Dev, 2 рекомендации)
[LOG] 2026-09-18 00:30 — Reviewer: начал повторную проверку (review #2)
[LOG] 2026-09-18 00:55 — Reviewer: панель восстановления и сытости видна в профиле (1440px и 360px); «Съесть» в контекстном меню работает, повторная попытка показывает «Вы уже наелись»; защитные тесты падают при CI без полного репозитория
[LOG] 2026-09-18 01:00 — Reviewer: обнаружен баг (удаление предмета, лежащего в инвентаре, → 500), добавлен в ISSUES.md
[LOG] 2026-09-18 01:05 — Reviewer: проверка завершена, результат PASS
[LOG] 2026-09-17 23:30 — PM: ревью #2 PASS, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Восстановление в покое: 5% в час от максимума здоровья, маны, энергии и выносливости; не идёт в бою, в подземелье и на сборе (лобби подземелья — покой); считается лениво, без фоновых задач; мобы не затрагиваются. После боя отсчёт сбрасывается.
- Сытость: признак «Еда» у предмета; еда даёт сытость ровно на 24 часа, мгновенное восстановление (если задано) и любые бонусы как у экипировки; бонус к восстановлению по редкости +50/+100/+150/+200%; вторая еда — «Вы уже наелись»; в бою есть нельзя. Бонусы снимаются ровно один раз по окончании.
- Редкости: не-снаряжение максимум легендарная; рецепты снаряжения могут быть мифическими/божественными/демоническими; у рецептов нет своей редкости (берётся у результата), предметы-рецепты без качества; трансмутация заканчивается на легендарной.
- Интерфейс: блок «Восстановление / Сытость» в профиле под ресурсами, пункт «Съесть» в меню предмета, галочка «Еда» и бонусы в админке предметов, админка рецептов без выбора редкости.
- Миграции: character-attributes 008, inventory 021, battle 007 (все с откатом). Около 450 новых тестов, все сервисы зелёные.

### Что изменилось от первоначального плана
- Решение «у рецепта нет своего качества» принято по ходу работы.
- Блок восстановления перенесён в новый профиль (первоначально попал в неиспользуемую вкладку — поймано на ревью).
- Исправлена ошибка округления восстановления; проверки-«охранники» в CI теперь падают, а не пропускаются.

### Оставшиеся риски / follow-up задачи
- HIGH в ISSUES.md: служебные эндпоинты /attributes/* (recover, apply_modifiers и др.) доступны без авторизации — стоит закрыть отдельной задачей.
- LOW в ISSUES.md: удаление предмета, который есть у кого-то в инвентаре, даёт 500; тесты конкурентности refund_stamina нигде не запускаются; нестабильный порядок тестов battle-service.
- Откат миграции 008 требует ручной процедуры (описана в миграции).
- Этап 2 (переработка профессий) и этап 3 (боевые эффекты зелий/свитков), затем редизайн всех вкладок профиля.
