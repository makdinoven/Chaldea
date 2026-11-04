# FEAT-198: Закон — розыск, стража, тюрьма (репутация, этап 2а)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-04 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Продолжение региональной репутации (FEAT-197, на проде c59c4af). Этап 2 разбит на 2а «Закон» (эта фича) и 2б «Тень» (скрытность, свидетели, маска, подозрение края, отложенное раскрытие, тайная дурная слава, слава-«громкость») — 2б отдельной фичей позже, но 2а должна оставить под неё точки расширения (преступление = событие, которое потом может пройти через проверку свидетелей).

Цель: у преступлений появляются последствия «здесь и сейчас» — розыск в крае, стража, которая встречает разыскиваемого, и тюрьма.

### Бизнес-правила
- **Розыск** — отдельная от репутации шкала по краю (персонаж × край). Репутация — долгосрочное отношение края; розыск — «тебя ловят сейчас». Преступление даёт и минус к репутации (как уже работает в FEAT-197), и розыск в крае преступления. Розыск со временем спадает («дело замяли»). Тяжесть розыска определяет штраф и срок.
- **Что считается преступлением сейчас:** только убийство NPC через «Нападение» (уже источник репутации в FEAT-197). Вес розыска — по роли NPC (как веса репутации; разбойник — не преступление). Нападение на игроков в мирных локациях — **пока не трогаем**. Источники будущего (налёт на караван и т.п.) — заложить типы, не реализовывать.
- **Стража — настоящие NPC с ролью «стражник»**, которых администратор расставляет по локациям. Убийство стражника — тяжёлое преступление (уже вес −300 репутации).
- **Встреча со стражей:** только когда разыскиваемый **сам заходит** в локацию, где стоит живой стражник (в будущем — патрули по зоне/городу, заложить возможность, не делать). Офлайн-поимки нет.
  - Обычный розыск — выбор: **заплатить штраф** (розыск снят), **сдаться** (тюрьма), **бежать** (проверка ловкости/удачи; провал → бой), **драться** (бой со стражником: победа → розыск растёт; поражение → тюрьма).
  - **«Вне закона»** (ступень репутации) — только два варианта: **сдаться** (тюрьма) или **бой**.
- **Тюрьма:** одна на край, администратор сам назначает локацию-тюрьму края в админке. Срок — **от 1 часа до 7 дней** (сначала было 1–48 ч, пользователь расширил) реального времени по тяжести розыска. В тюрьме: можно писать посты в тюремной локации; нельзя перемещаться, торговать, участвовать в боях, данжах, брать/сдавать задания. Досрочно: **залог** (платит сам или другой игрок за него), **побег** (проверка; провал → срок больше). После выхода розыск в этом крае снят.

### UX / Пользовательский сценарий
1. Игрок убивает мирного NPC через «Нападение» → репутация падает (FEAT-197) и появляется розыск в крае.
2. Позже игрок заходит в локацию края, где стоит стражник → окно встречи со стражей с вариантами (штраф / сдаться / бежать / драться; «Вне закона» — сдаться / драться).
3. Сдался или проиграл → персонаж перемещён в тюрьму края, таймер срока, ограничения; варианты залога и побега.
4. Срок истёк / залог / удачный побег → персонаж свободен, розыск снят (при побеге — см. архитектора/вопросы).
5. Игрок видит свой розыск (в профиле рядом с репутацией) и уведомления.

### Edge Cases
- В крае не назначена тюрьма → что делает стража? (вопрос архитектору → PM)
- Персонаж в бою/данже/группе в момент встречи.
- Группа заходит в локацию со стражей, разыскивается только часть.
- Стражник мёртв (после «Нападения») — не встречает.
- Залог за другого игрока — защита от злоупотреблений.

### Вопросы к пользователю
- [x] Что преступление сейчас → только убийство NPC; PvP пока не трогаем.
- [x] Стража → настоящие NPC с ролью «стражник».
- [x] Тюрьма → одна на край, назначает админ.
- [x] Срок → до 7 дней (2 ч / 12 ч / 24 ч / 72 ч / 168 ч по уровням).
- [x] Что можно в тюрьме → посты в тюремной локации; нельзя перемещение, торговля, бои, данжи, задания.
- [x] «Вне закона» → только «сдаться» или «бой».
- [x] Когда стража ловит → только при входе в локацию со стражником; патрули — в будущем.

### Решения пользователя по вопросам аналитика (2026-11-04)
1. «Вне закона» без розыска — стража тоже берёт (сдаться / бой).
2. В крае не назначена тюрьма — стража только штрафует или дерётся; «сдаться» недоступно (для «Вне закона» без тюрьмы — только бой).
3. Победа над стражником — **не убивает навсегда**: стражник выбывает на время (6 ч), потом возвращается; игроку −300 репутации и тяжёлый розыск (как за убийство). Прочие NPC — как раньше.
4. Телепорт у мастера телепортов — считается входом (стража встречает). **Телепорт свитком домой — НЕ считается**: это законный способ скрыться от стражи.
5. Окно встречи закрыто/проигнорировано — персонаж заблокирован на месте, окно всплывает снова; **если выбора нет 24 часа** — автоматически «сдался» (если тюрьмы нет — см. п.2: авто-штраф, а при нехватке денег — архитектор предлагает, вопрос PM).
6. Залог: платит любой игрок (включая других своих персонажей), **в любом банке** (у банкира любого края), присутствие в крае тюрьмы не нужно. Цена = штраф × 2.
7. Побег: попытка раз в 6 ч, проверка ловкости/удачи; провал → +50 % к оставшемуся сроку; успех → свобода, но розыск в крае становится тяжёлым и не снимается.
8. Штрафы и залог — в казну края (налог стране 10 % автоматически, как плата за телепорт).
9. Стафф (права `reputation:manage`) может освободить из тюрьмы / снять розыск с обязательной причиной; отдельных прав `law:*` не заводить.
10. Вес розыска — из весов репутации за убийство (только отрицательные, только «мирные»; разбойник не преступление); отдельной таблицы нет.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Nothing about wanted level or jail exists yet: grep `jail|wanted|тюрьм|розыск` over the service code finds 0 real hits. Paths below are relative to `services/`. FEAT-197 reputation is live (character-service owns `character_reputation`, `reputation_log`, `reputation_*`; locations-service reads it by SQL via `reputation_read.py`).

### 2.1 Crime source: NPC kill (already wired for reputation)
- Frontend `hooks/useNpcAttack.ts:42` → `POST /battles/` with `battle_type:'pvp_attack'` (`battle-service/app/main.py:996` `create_battle_endpoint` → `_assemble_battle` L912, which registers NPCs with autobattle). The server does **not** check that the NPC is alive; only the frontend list hides dead NPCs.
- The battle ends in `_finalize_battle` (`battle-service/app/main.py:2358`). Its callers are the killing blow in `_make_action_core` and the timeout sweeper `handle_expired_turn` (~L6498). In the NPC-death loop (~L2560-2610), every defeated `is_npc=1 AND npc_role!='mob'` gets `PUT /characters/internal/npc-status/{id}` `{status:'dead', battle_id, killer_character_ids}`.
- `character-service/app/main.py:3966` `update_npc_status` does a conditional `alive→dead` UPDATE. Only on a real transition does it call `reputation_crud.apply_npc_kill` (`reputation_crud.py:453`). Region = the NPC's location → `location_region`. Points come from `rc.kill_points(npc.reputation_kill_points, npc.npc_role, role_weights)`. The key is `npc_kill:{npc}:{battle}:{killer}`. Everything runs in one transaction, and `reputation_notify.publish_tier_changes` is called after the commit.
  - **Best hook for wanted:** right next to `apply_npc_kill`, in the same transaction, with the same key shape. It already has the region, the player killers (`is_npc=0`), the battle id and the role. Role weights live in `reputation_npc_role_weights` (seeded: bandit +20, mercenary −30, guard −300, ruler/king −1000, others/`*` −150). A wanted weight needs its own column or table. One option is "only negative kill points count as a crime", which leaves bandit out automatically, but that is the Architect's call.
  - Extension point for 2b: `reputation_core.py` already reserves actions `crime` (−50) and `caravan_attack` (−100) without sources (`reputation_core.py:38-46,94-100`). A "crime event" row (type, region, character, victim, battle, status) written before any wanted change would give 2b a place to slot in a witness check.
- `reputation_core.py` is byte-copied to locations-service and guarded by `scripts/check_econ_copies.sh:69-72`. Any wanted maths added there must land identically in both copies.

### 2.2 Guards
- Role `guard` («Стражник») already exists in `frontend/.../constants/npc.ts` (`NPC_ROLES`, icon 🛡️). `characters.npc_role` is free `String(50)` (`character-service/app/models.py:65`), and `npc_status` is an ENUM alive/dead (L66).
- Placement = the NPC's `current_location_id`, set in the admin NPC form (`AdminNpcsPage/AdminNpcsPage.tsx`; `PUT /characters/admin/npcs/{id}`; `NpcCreate/NpcUpdate` in `schemas.py:774-857`). Listing: `GET /characters/npcs/by_location` (`main.py:3245`) excludes dead NPCs and mobs. Side bug: `npc_role != 'mob'` also drops NPCs whose role is NULL (SQL NULL semantics).
- **There is no NPC respawn.** A dead guard stays dead until an admin sets it back to alive (NPC admin update). After kills, a region can end up with no live guards.

### 2.3 Every path that changes `characters.current_location_id`
| # | Path | File:line | Voluntary entry? | Notes |
|---|---|---|---|---|
| 1 | Move + post | `locations-service/app/main.py:1234` `move_and_post` | yes | Checks activity lock, battle and gathering (L1256-1259). Creates the **post first** (L1350), then `PUT /characters/internal/{id}/update_location` (L1382), cooldown, stamina, party leave-on-move (L1438), `_try_spawn_mob` background (L1477; precedent for an "on entry" hook). `actually_moving` (L1271) is false when posting in the current location. **The frontend uses this same endpoint for ordinary posts in the current location** (`LocationPage.tsx:479`), so it is also the "write a post" path for a jailed player. |
| 2 | Quick move | `locations-service/app/main.py:1526` `quick_move` | yes | Same checks; auto post; `update_location` L1642; `_try_spawn_mob` L1720. |
| 3 | Teleport master | `character-service/app/crud.py:3771` `execute_teleport` (router `main.py:4493`) | yes | Locks the row; activity-lock check L3795; reputation gates; fare via ledger `OP_TELEPORT`; sets the location at L3874. |
| 4 | Home teleport scroll | `inventory-service/app/home_teleport.py:130` → `character-service/app/main.py:1032` `internal_home_teleport` → `_prepare_move` (L906) + `crud.apply_admin_move` (L4092) | yes (into own house) | Decision needed: does a guard meet you at home? |
| 5 | Admin move | `character-service/app/main.py:947` (`characters:teleport`) → `_prepare_move` + `apply_admin_move` | no | Forced. **This is the template for "move to jail"**: refuses in battle or dungeon (409), cancels gathering, expires intents and the party in the old location (`locations_client.notify_character_left_location`), then a single-commit move plus a journal row. |
| 6 | Dungeon wipe knock-out | `character-service/app/main.py:~4222` `internal_knockout` (`return_location_id`) ← `dungeon-service/app/gameplay.py:2018` | no | Returns to the dungeon's location and sets `unconscious_until` (+1 h). Entering or leaving a dungeon itself never changes location (`gameplay.py:991` requires being on the dungeon location already). |
| 7 | Character approval (start location) | `character-service/app/main.py:524-527` `_resolve_start_location` | no | A new character has no wanted level. |
| 8 | Mob or NPC creation | `crud.py:1823`, `main.py:2994` | n/a | NPCs only. |
- **No group or party move exists.** party-service (`party-service/app/main.py`) has create/invite/respond/leave only. The battle-service pre-battle party is left on move (`/battles/internal/party/leave-on-move`, `main.py:7310`). So "the group enters" is always N individual moves, and an encounter is per character.
- `update_location` (internal, `main.py:2321`) is the single write used by #1 and #2. It blindly sets the value and clears `house_room_id`. There is no "travel/route" multi-hop feature; region arrows are map-only.

### 2.4 Activity lock = the natural jail lock
- `activity_lock.py` exists in 4 copies, which are **not** CI-guarded: character (canonical, pure), locations and battle (identical, async `get_activity_lock` / `check_not_activity_locked` reading `dungeon_session_id, unconscious_until, asleep_since, reading_since` by raw SQL), and inventory (sync variant). dungeon-service reads it via HTTP `http_clients.get_activity_lock` or the profile's `activity_lock`. Reasons: dungeon, unconscious (time-limited, "past = unlocked", **no cleanup job**), asleep, reading. 409 plus Russian text from `lock_message`.
- Adding a `jailed_until` column (plus jail region/location) and a `jail` reason to `compute_lock` gives **all existing checks at once**:
  - **locations-service:** post create (L869), tag player (L1209), move_and_post (L1257), quick_move (L1541), loot drop/pickup (L2168/2237), NPC buy/sell (L2895/3079), quest accept/complete (L3287/3363), gathering start (`crud.py:7998`), houses (`houses.py:747, 1293, 1487, 1732, 2305, 2493, 2640, 3077, 3125`).
  - **battle-service:** create (L1035), mob/pack attacks incl. party (L1136-1400), forced PvP request/approve (L1515/1551), PvP invite/respond (L4583/4791), `pvp_attack` attacker and victim (L5035), join requests (L5819/6057), battle party (L6990-7234).
  - **inventory-service:** player trade propose/accept (L1769-1876), crafting (L2604/3081/3255/3423/3518), home teleport.
  - **character-service:** teleport (`crud.py:3795`), home teleport (`main.py:1054`), bank/guild/mint resolvers (`economy_bank_crud.py:294`, `economy_guild_crud.py:408`, `economy_mint_crud.py:418`).
  - **dungeon-service:** entry (`gameplay.py:995`).
- **Gaps (not lock-checked today):** auction endpoints (`inventory-service/app/main.py:4445-4519` → `crud.create_auction_listing` / `place_bid` / `execute_buyout` / deposit / claim). Only deposit and listing require an auctioneer at the location (`crud.py:2608`); bids and buyout work from anywhere. Also quest abandon (`locations main.py:3487`), NPC dialogue choose (L2575), and party-service invites.
- **Conflict with "posts allowed in jail":** posting goes through `move_and_post` / `/posts/`, and both reject any lock. The jail reason needs an exception there when `destination == current_location` (= the jail). Movement is already guaranteed by the lock, and `/posts/` already requires the character to be in the location (L873-883). Equipment and consumables are not lock-checked (only battle-checked), so they stay usable in jail.
- **Frontend:** `/users/me` → `character.activity_lock` (`user-service/main.py:356`; `character-service/main.py:2463`), `hooks/useActivityLock.ts` (type `ActivityLockReason` = 4 values), and the `LocationPage.tsx:75-76, 905-917` banner, which disables actions. A new `jail` reason needs an icon/text, the countdown (the unconscious branch already does `until`), and the post form must stay enabled in the jail location.

### 2.5 Battle vs guard (programmatic) and outcome routing
- Create: the closest template is `internal_create_dungeon_battle` (`battle-service/app/main.py:1584`, internal token, no JWT, explicit teams, its own lock exemption) calling `_assemble_battle(..., dungeon_session_id=...)`. Battles are tagged by `battles.dungeon_session_id` (migration `008_add_dungeon_session_id.py`), and the end is reported via `_notify_dungeon_battle_end` (L1669, fire-and-forget POST with 3 retries) plus a polling fallback `GET /battles/internal/{id}/result` (L1694; `winner_team` from `battle_history`, `aborted` for force-finish). A guard battle can copy this shape: a nullable tag column (e.g. `law_encounter_id`) and a callback to character-service with `winner_team`, `defeated_characters` and `aborted`.
- `battle_type` is a MySQL ENUM on `battles`, `battle_history` and `battle_parties` (`models.py:48/188/255`). A new type value means ALTERing 3 enum columns. Reusing `pvp_attack` avoids that. `is_pvp` stats only count `pvp_training/pvp_death` (L707).
- Loss for the player: `winner_team != player's team`. Timeout = a loss (`by_timeout`, L2365). Admin force-finish (`_force_finish_battle` L5403) has no winner, so `aborted`.
- **Side effect to decide:** if the player wins, the guard (an NPC, not a mob) reaches `hp<=0` and the existing loop marks it **dead** and applies the −300 kill reputation (plus wanted, if hooked there). That matches "победа → розыск растёт", but it also permanently removes the guard (no respawn). If guard battles should be non-lethal, the loop must skip tagged battles.
- `finish_battle` sets the status to finished before the consequences run (`battle-service/app/crud.py:69`), so character-service `_is_in_battle` (`main.py:877`) will not block a jail move started from the callback. The guard itself may be in another battle (`create_battle` refuses "Персонаж уже в бою"); the encounter needs a fallback for that.

### 2.6 Flee and escape checks
- Stats: `character_attributes.agility` and `.luck` (`character-attributes-service/app/models.py:37/39`), with soft cap 100 and hard cap 200 since FEAT-195. character-service already reads `character_attributes` by raw SQL (`crud.py:2033/2623/2838`). HTTP alternative: `GET /attributes/internal/{id}` (L422). There is no existing generic "skill check" helper; a pure function plus a server-side RNG is needed.

### 2.7 Fines, bail and gold
- All gold moves go through `econ_ledger.post_operation` (`character-service/app/econ_ledger.py:217`; balance guard, `idempotency_key`, `InsufficientFunds`). Pattern: teleport fare `character → payer_account(region of NPC)` (`crud.py:3851-3862`). `treasury_for_location` (L115) = region treasury, else world treasury.
- New op types (e.g. `law_fine`, `law_bail`) must go into `econ_core.OP_TYPES` (`econ_core.py:162`). That file has **4 byte-identical copies** (character, inventory, locations, dungeon) under the CI guard, plus `tests/econ_contract_cases.py`. Tax: region-treasury inflows from a character are taxed 10 % to the country automatically (`apply_tax=True`).

### 2.8 Jail location per region
- `Regions` is owned by locations-service (`models.py:51`). It already has `entrance_location_id` (FK `Locations.id ON DELETE SET NULL`), which is the same pattern a `jail_location_id` would follow. Admin: `PUT /locations/regions/{id}/update` (`main.py:312`, `locations:update`), schemas `RegionBase/RegionCreate/RegionUpdate` (`schemas.py:225-281`), UI `AdminLocationsPage/EditForms/EditRegionForm/EditRegionForm.tsx` (already edits `entrance_location_id`). Alembic head `054_reputation_gates`.
- Alternative: a character-service table keyed by `region_id`, like `econ_banks` (`models.py:752`). But `econ_regions` only covers economy regions, and jail must work for all regions.
- Validation is needed so the jail location belongs to that region (`econ_core.SQL_RESOLVE_LOCATION` / `reputation_crud.location_region`, `reputation_crud.py:166`).

### 2.9 Timers and schedulers
- character-service `econ_scheduler` thread (`econ_scheduler.py`; env `ECON_TICK_ENABLED` default 1, poll 60 s) calls `reputation_decay.run_pass` **before** the economy `tick_enabled` switch (L62-75), throttled by a conditional UPDATE claim (`reputation_decay.py` `claim_run`). This is the host for a law pass: release notifications on term end, and materialising wanted decay.
- The lock itself can be lazy (`jailed_until` in the past = free), as with `unconscious_until`. Wanted decay can be lazy too (`effective_value(value, decay_at, now, per_day)`, `reputation_core`). Celery exists only in battle-service, for `save_log`.

### 2.10 Notifications
- `reputation_notify.py` (sync pika → `general_notifications`, after commit, best-effort; `user_id` from `characters.user_id`). Categories are in `notification-service/app/notification_categories.py:25-46`: configurable `messages, social, trade, party, world, progress`, and mandatory `battle, system`. Jail and capture are probably `system` (mandatory) or `progress`.

### 2.11 Frontend touch points
- Entry: `LocationPage.tsx` `handleSubmitPost` (L476, `move_and_post`) and `handleQuickMove` (L567). After success they dispatch `setCharacterLocation` and `getMe`. The encounter modal must open from the move response or from a "pending encounter" fetch on LocationPage mount, so a refresh cannot dodge it.
- Modals: `pages/LocationPage/*Modal.tsx` (e.g. `DeathDuelConfirmModal.tsx`, `NpcShopModal.tsx`) with design-system classes `modal-overlay` / `modal-content`. The battle route is `battlePath(locationId, battleId)` (`utils/battlePath.ts`). After a lost guard fight, the "back to location" target is stale because the player has been moved to jail.
- Profile: `ProfilePage/ReputationTab/ReputationTab.tsx` + `api/reputation.ts` (wanted per region next to the tier). Admin: `Admin/CharactersPage/AdminCharacterDetailPage.tsx` (Reputation tab: add wanted/jail with manual release?), `Admin/ReputationPage/*` (settings tabs: wanted weights, fine/term scale), `EditRegionForm.tsx` (jail location), `AdminNpcsPage.tsx` (role `guard` already selectable).

### 2.12 RBAC
- user-service head `0033_reputation_permissions` (`reputation:read/manage/settings`). New law settings can reuse `reputation:settings`, or a new migration `0034_*` can add something like `law:*`, plus an explicit section in `tests/test_rbac_permissions.py` (CLAUDE.md §10.13).

### Affected Services
| Service | Type of Changes | Files |
|---|---|---|
| character-service (owner) | wanted / jail / encounter tables (Alembic `039_*`), law core + crud + API, wanted hook in `update_npc_status`, jail lock columns, forced move to jail, fine/bail ledger ops, scheduler pass, notifications | `models.py`, `activity_lock.py`, `main.py` (npc-status, profile), `reputation_crud.py`/new `law_*.py`, `econ_scheduler.py`, `econ_core.py` |
| locations-service | encounter trigger after a move (`move_and_post`, `quick_move`), jail exception for posting in jail, `Regions.jail_location_id` (`055_*`), region admin schema | `main.py`, `activity_lock.py`, `models.py`, `schemas.py`, `crud.py` |
| battle-service | internal guard battle create + end callback (tag column `009_*`), optional non-lethal guard, jail reason in `activity_lock.py` | `main.py`, `models.py`, `activity_lock.py` |
| inventory-service | jail reason in lock copy; lock checks on auction routes | `activity_lock.py`, `main.py`/`crud.py` |
| inventory/locations/dungeon | econ_core copies (new op types) | `*/app/econ_core.py` |
| user-service | permissions migration (if new) + RBAC test | `alembic/versions/0034_*`, `tests/test_rbac_permissions.py` |
| frontend | encounter modal, jail banner/timer/bail/escape, wanted in profile, admin settings, region jail field | see 2.11 |

### Existing Patterns
- character-service: sync SQLAlchemy, Pydantic v1, `/characters/internal/*` + `X-Internal-Token`, economy-style pure module + crud + router, notifications after commit. locations-service and battle-service: async raw `text()` for foreign tables. Forced move = `_prepare_move` + `apply_admin_move`. Battle linking = tag column + callback + polling fallback (dungeon).

### Cross-Service Dependencies
```
locations-service (move_and_post / quick_move) ──HTTP──> character-service POST /characters/internal/law/on-enter (new)
character-service ──HTTP──> battle-service POST /battles/internal/guard (new, like /internal/dungeon)
battle-service ──HTTP──> character-service callback on guard-battle end (new) + existing PUT /internal/npc-status
character-service ──HTTP──> locations-service (cancel gathering / notify_character_left_location) via _prepare_move
character-service ──pika──> notification-service (general_notifications)
inventory/teleport (character-service) ──> on-enter hook if teleports count as entry
```

### DB Changes (shape for the Architect)
- character-service: wanted per (character_id, region_id) with value + decay anchor (UNIQUE pair); law settings (fine/term scale, decay speed, flee/escape formula params, bail limits); wanted weights per NPC role (column on `reputation_npc_role_weights` or a new table); crime/law log (idempotency key UNIQUE; extension point for 2b); pending encounter (character, region, guard, location, status, battle_id, created_at; one active per character); jail record (character, region, location, until, bail, escape attempts); `characters.jailed_until` (+ `jail_region_id`) for the lock.
- locations-service: `Regions.jail_location_id` (FK SET NULL, own index).
- battle-service: nullable tag column on `battles` (avoids altering the 3 `battle_type` enums).
- econ_core: new OP types (4 copies). MySQL gotchas: FK index, revision id ≤ 32 chars.

### Risks
- **Encounter dodging / races:** the move is "post first, location second" via HTTP, and the encounter is created after. A refresh, a second tab or an immediate quick move could slip through. Mitigation: create a persisted pending encounter (and an `encounter` lock reason) in the same request that moved the character; it must be resolved before anything else.
- **Pending encounter ignored:** the player closes the tab. A timeout rule is needed (auto-surrender? stays forever?). This is a user decision.
- **Region without a jail:** fine-only? No encounter? Use a neighbouring or capital region's jail? User decision.
- **Dead guard / guard busy:** no respawn, so a killed guard is gone until an admin revives it. A guard already in battle cannot be fought. Choose another live guard or skip the encounter.
- **Winning kills the guard:** the existing NPC-death loop makes every won guard fight lethal (−300 rep, more wanted, guard lost forever). Decide lethal vs non-lethal.
- **Posting in jail:** both post paths reject every lock; an explicit jail exception is needed for the current location only.
- **Party:** no group moves, so each member's encounter is individual. A wanted member who is jailed leaves the pre-battle party through the move side effects.
- **In battle / dungeon at entry:** impossible via normal moves (both refuse), and the jail move uses `_prepare_move`, which refuses in battle or dungeon (the guard battle is already finished at callback time).
- **Callback loss:** battle → character-service callback is fire-and-forget. Needs a retry/polling fallback (dungeon precedent) or an idempotent reconcile in the scheduler, or a lost fight never jails.
- **Auction gap:** auction routes ignore the activity lock today. Add checks there, or jailed players can still trade.
- **econ_core / reputation_core copy churn:** CI fails unless the copies stay byte-identical.
- **Bail abuse:** a player's own alts can bail them out, and paying for strangers raises the question of whether the payer must be in the region or the jail location. Needs a rule (e.g. not the same `user_id`, cooldown, payer location).
- Prisoners are immune to «Нападение», because `pvp_attack` refuses locked victims. Probably desirable; confirm.

### Open questions for PM / user
1. Does an «Вне закона» character with **zero** wanted also get stopped by guards (the tier alone triggers), or only when wanted > 0?
2. Region without a jail: does the guard only fine, skip, or send the player to another region's jail?
3. Is a won guard fight lethal (guard dies and stays dead; no respawn exists) or does the guard just "lose" and stay alive?
4. Does teleporting (teleport master, home scroll) into a location with a guard trigger the encounter, or only walking (move / quick move)?
5. What if the player ignores the encounter window: auto-surrender after N minutes, or does everything stay blocked until they choose?
6. Bail: may the player's own other characters (same account) pay? Must the payer be in the jail location or region? How is the price formed (fine × k)?
7. Escape: how often may it be tried? On success, is wanted cleared or increased? On failure, how much longer is the term?
8. Where do fines and bail go: the region treasury (like the teleport fare, taxed 10 % to the country) or another account?
9. Can staff release a prisoner or clear wanted manually (moderator `reputation:manage`?), and is a separate `law:*` permission wanted?
10. Wanted weights: derive them from the reputation kill points (negative only), or keep a separate editable per-role wanted table?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Summary of key decisions

| # | Decision | Why |
|---|---|---|
| L1 | **character-service owns all law state** (wanted, crimes, encounters, jail terms, settings, journal) in a new set of modules `law_core.py` (pure) + `law_crud.py` (sync, caller's transaction) + `law_api.py` (router) + `law_notify.py` + `law_pass.py` (scheduler). No copy of `law_core` in other services: only character-service computes wanted. Other services see the law **only through the activity lock** (two new `characters` columns). | Every crime source, the forced move, the ledger, reputation and the scheduler already live in character-service. Other services only need "is this character locked", and they already have that check everywhere (§2.4). |
| L2 | **Wanted = a separate positive scale per (character, region)**, 0..`max_wanted` (default 1000), with **lazy linear decay** toward 0 (`value − floor(per_day × elapsed / 86400)` since `decay_at`). It is not materialised by a scheduler: every reader computes the effective value, and every writer materialises it first. **5 fixed severity levels** (fixed codes, editable name/threshold/fine/term), the same idea as the 8 reputation tiers. | Simple, exact without a scheduler, mirrors the reputation pattern players and admins already know. Fixed codes keep the code stable (outlaw minimum level, "heavy" floor). |
| L3 | **Crime = an event row** (`law_crimes`) written in the same transaction as the NPC-kill reputation. In 2a every crime is `status='reported'` and immediately adds wanted. 2b slots a witness check in between (`status='pending_witness'` → resolved later) without touching the sources. Crime weight = `−kill_points` of the reputation weight (negative only, user decision 10). Future source types (`caravan_attack`, `pvp_attack`, `theft`) are reserved constants with no source. | User decision 10 + extension point for 2b. |
| L4 | **The guard encounter is created inside the same DB transaction that moves the character** (character-service `update_location` for move/quick move, `execute_teleport` for the teleport master). It sets `characters.law_encounter_id`, which is a **new activity-lock reason `law_encounter`**. A refresh, a second tab or a quick move cannot dodge it: the lock already blocks every other action, and `update_location` re-checks the lock under a row lock. The home-teleport scroll does not evaluate entry (user decision 4), but it is blocked while an encounter is pending, because it is lock-checked. | Atomic, no new client race. Reuses the lock checks that already exist across 5 services. |
| L5 | **Jail = activity-lock reason `jail`** driven by `characters.jailed_until` (lazy: a past value means free, like `unconscious_until`) + `characters.jail_region_id`. **Wanted in the region is cleared at sentencing**, so a lazy release is already fully correct. The scheduler only marks served terms and sends the "you are free" notification. Posting is the single exception: allowed in the **current** location only. | No release job needed for correctness, and the lock covers all the forbidden actions from §2.4 at once. |
| L6 | **Guard fight = an internal battle-service battle** (`POST /battles/internal/guard`, `battle_type='pvp_attack'`, the same type as «Нападение» on NPCs, so no ENUM change), tagged by a new nullable `battles.law_encounter_id`. Its end is reported by a callback to character-service plus a polling fallback in the law scheduler pass. This is the dungeon-battle pattern. | A proven pattern (FEAT-175), no ENUM ALTER on 3 tables. |
| L7 | **Guards are never killed permanently, whatever the fight.** In `update_npc_status`, an NPC with `npc_role='guard'` reported `dead` is instead **knocked out** for `guard_ko_hours` (default 6) via the NPC's own `unconscious_until`, with a conditional transition (idempotent). The kill reputation (−300) and the crime/wanted (raised to at least the "heavy" floor) apply on that transition. This covers both the encounter fight and «Нападение» on a guard (see Q2). KO'd NPCs are hidden from the NPC list, refused as battle targets and never meet anyone. The scheduler heals guards back to full HP when the KO ends, and the fight start heals the guard too. | User decision 3. One central place (character-service) and no lethal-loop special case in battle-service. |
| L8 | Money: **`law_fine`** and **`law_bail`** op types (econ_core, 4 copies) go from the character purse to the **region treasury of the encounter/jail region** (`treasury_for_location` of that region's jail/encounter location), `apply_tax=True` (10 % to the country, like the teleport fare). Idempotency keys are derived from the encounter or jail-term id. | User decision 8; the existing ledger guarantees. |
| L9 | Randomness: server-side `secrets.SystemRandom()`. Flee and escape chance = `clamp(base + (agility + luck) × per_point, min, max)` from `character_attributes` (raw SQL read; FEAT-195 caps apply naturally). The roll and the chance are written to `law_log`. | No client influence; the formula is editable in settings. |
| L10 | Permissions: **no new permissions** (user decision 9). Law settings = `reputation:settings` (admin only); staff release / clear wanted / cancel encounter = `reputation:manage`; staff reads = `reputation:read`. The RBAC test does not change, because there are no new permission rows. | User decision 9. |

### 3.1 Data model

#### character-service, Alembic `039_law` (revision id `039_law`, ≤ 32 chars)

No FK to `Regions` / `Locations` (owned by locations-service; same convention as `character_reputation`). FK to `characters` with `ON DELETE CASCADE`. **Every FK column has its own index, or is the leftmost column of a composite index** (MySQL gotcha).

```sql
CREATE TABLE character_wanted (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  character_id  INT NOT NULL,                  -- FK characters.id ON DELETE CASCADE (leftmost of uq)
  region_id     INT NOT NULL,
  value         INT NOT NULL DEFAULT 0,        -- materialised, 0..max_wanted
  decay_at      DATETIME NULL,                 -- decay anchor; NULL when value = 0
  updated_at    DATETIME NOT NULL,
  UNIQUE KEY uq_char_wanted (character_id, region_id),
  KEY ix_char_wanted_region (region_id)
);

CREATE TABLE law_settings (                      -- single row id = 1
  id                       INT PRIMARY KEY,
  max_wanted               INT NOT NULL DEFAULT 1000,
  decay_per_day            DECIMAL(8,2) NOT NULL DEFAULT 50.00,  -- 0 = off
  heavy_wanted             INT NOT NULL DEFAULT 600,   -- floor after guard defeat / successful escape
  outlaw_min_level         VARCHAR(20) NOT NULL DEFAULT 'criminal', -- severity used for an outlaw (jail term)
  encounter_timeout_hours  INT NOT NULL DEFAULT 24,    -- auto-resolution (user decision 5)
  guard_ko_hours           INT NOT NULL DEFAULT 6,     -- user decision 3
  flee_base_pct            DECIMAL(5,2) NOT NULL DEFAULT 20.00,
  flee_per_point_pct       DECIMAL(6,3) NOT NULL DEFAULT 0.250,  -- per (agility + luck) point
  flee_min_pct             DECIMAL(5,2) NOT NULL DEFAULT 5.00,
  flee_max_pct             DECIMAL(5,2) NOT NULL DEFAULT 85.00,
  escape_base_pct          DECIMAL(5,2) NOT NULL DEFAULT 5.00,
  escape_per_point_pct     DECIMAL(6,3) NOT NULL DEFAULT 0.150,
  escape_min_pct           DECIMAL(5,2) NOT NULL DEFAULT 2.00,
  escape_max_pct           DECIMAL(5,2) NOT NULL DEFAULT 50.00,
  escape_cooldown_hours    INT NOT NULL DEFAULT 6,     -- user decision 7
  escape_fail_extend_pct   DECIMAL(5,2) NOT NULL DEFAULT 50.00,  -- user decision 7
  max_remaining_jail_hours INT NOT NULL DEFAULT 168,   -- cap after an escape failure (Q4)
  bail_multiplier          DECIMAL(5,2) NOT NULL DEFAULT 2.00,   -- user decision 6
  pass_last_run_at         DATETIME NULL,              -- scheduler claim
  updated_at               DATETIME NOT NULL
);

CREATE TABLE law_levels (                        -- exactly 5 rows, codes fixed
  code        VARCHAR(20) PRIMARY KEY,           -- suspect, offender, criminal, villain, enemy
  sort_order  INT NOT NULL UNIQUE,               -- 1 = lightest
  name        VARCHAR(60) NOT NULL,
  min_value   INT NOT NULL,                      -- inclusive lower bound of wanted; level 1 >= 1
  fine        INT NOT NULL,                      -- gold, >= 0
  jail_hours  INT NOT NULL                       -- 1..168
);

CREATE TABLE law_crimes (                        -- crime events (2b extension point)
  id                   BIGINT AUTO_INCREMENT PRIMARY KEY,
  event_key            VARCHAR(191) NOT NULL,     -- idempotency
  crime_type           VARCHAR(30) NOT NULL,      -- npc_kill | guard_defeat | jail_escape | (reserved) caravan_attack, pvp_attack, theft
  character_id         INT NOT NULL,              -- FK characters.id ON DELETE CASCADE (leftmost of ix)
  region_id            INT NOT NULL,
  location_id          INT NULL,
  victim_character_id  INT NULL,                  -- NPC id (no FK: NPC rows may be deleted)
  battle_id            INT NULL,
  wanted_points        INT NOT NULL,              -- requested gain
  wanted_applied       INT NOT NULL DEFAULT 0,    -- after clamp; 0 until applied
  status               VARCHAR(20) NOT NULL,      -- 2a: 'reported' (applied at once); 2b: 'pending_witness' | 'unwitnessed'
  created_at           DATETIME NOT NULL,
  resolved_at          DATETIME NULL,
  UNIQUE KEY uq_law_crime_key (event_key),
  KEY ix_law_crime_char (character_id, created_at),
  KEY ix_law_crime_status (status)
);

CREATE TABLE law_encounters (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  character_id     INT NOT NULL,                 -- FK characters.id ON DELETE CASCADE (leftmost of ix)
  region_id        INT NOT NULL,
  location_id      INT NOT NULL,
  guard_npc_id     INT NULL,                     -- the guard who met the player (no FK)
  is_outlaw        TINYINT(1) NOT NULL,          -- snapshot at creation
  has_jail         TINYINT(1) NOT NULL,          -- snapshot (re-checked at choice time)
  level_code       VARCHAR(20) NOT NULL,         -- severity snapshot
  wanted_value     INT NOT NULL,                 -- effective wanted at creation (staff only)
  fine             INT NOT NULL,                 -- snapshot
  jail_hours       INT NOT NULL,                 -- snapshot
  flee_used        TINYINT(1) NOT NULL DEFAULT 0,
  status           VARCHAR(20) NOT NULL,         -- pending | fighting | fined | jailed | fled | won | auto_fined | cancelled | guard_gone
  battle_id        INT NULL,
  source           VARCHAR(20) NOT NULL,         -- move | quick_move | teleport
  created_at       DATETIME NOT NULL,
  expires_at       DATETIME NOT NULL,            -- created_at + encounter_timeout_hours
  fight_started_at DATETIME NULL,
  resolved_at      DATETIME NULL,
  KEY ix_law_enc_char (character_id, created_at),
  KEY ix_law_enc_status (status, expires_at),
  KEY ix_law_enc_battle (battle_id)
);

CREATE TABLE law_jail_terms (
  id                     INT AUTO_INCREMENT PRIMARY KEY,
  character_id           INT NOT NULL,           -- FK characters.id ON DELETE CASCADE (leftmost of ix)
  region_id              INT NOT NULL,
  location_id            INT NOT NULL,           -- the jail location at sentencing
  encounter_id           INT NULL,               -- NULL for staff-created terms (not in 2a)
  level_code             VARCHAR(20) NOT NULL,
  fine_base              INT NOT NULL,           -- the level fine at sentencing (bail = ceil(fine_base × bail_multiplier))
  bail_price             INT NOT NULL,
  started_at             DATETIME NOT NULL,
  until                  DATETIME NOT NULL,      -- mirrors characters.jailed_until
  status                 VARCHAR(20) NOT NULL,   -- serving | served | bailed | escaped | released
  escape_attempts        INT NOT NULL DEFAULT 0,
  next_escape_at         DATETIME NULL,          -- NULL = may try now
  bailed_by_character_id INT NULL,
  resolved_at            DATETIME NULL,
  notified               TINYINT(1) NOT NULL DEFAULT 0,  -- release notification sent
  KEY ix_law_jail_char (character_id, status),
  KEY ix_law_jail_status (status, until)
);

CREATE TABLE law_log (                           -- journal of every law change (staff view; idempotency)
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  event_key      VARCHAR(191) NOT NULL,
  character_id   INT NOT NULL,                   -- FK characters.id ON DELETE CASCADE (leftmost of ix)
  region_id      INT NULL,
  action         VARCHAR(30) NOT NULL,           -- crime | fine | surrender | jail | flee_ok | flee_fail | fight_won | fight_lost
                                                 -- | escape_ok | escape_fail | bail | served | auto_surrender | auto_fine
                                                 -- | staff_release | staff_clear | staff_cancel | guard_ko
  wanted_before  INT NULL,
  wanted_after   INT NULL,
  amount         INT NULL,                       -- gold for fine/bail
  chance_pct     DECIMAL(5,2) NULL,
  roll_pct       DECIMAL(5,2) NULL,
  ref_id         INT NULL,                       -- encounter / jail term / crime id
  reason         VARCHAR(500) NULL,              -- staff reason
  actor_user_id  INT NULL,                       -- NULL = system / player self
  created_at     DATETIME NOT NULL,
  UNIQUE KEY uq_law_log_key (event_key),
  KEY ix_law_log_char (character_id, created_at)
);

ALTER TABLE characters
  ADD COLUMN jailed_until      DATETIME NULL,   -- lock reason 'jail' while > now (lazy)
  ADD COLUMN jail_region_id    INT NULL,
  ADD COLUMN law_encounter_id  INT NULL;        -- lock reason 'law_encounter' while NOT NULL (no FK: avoids a cycle)
```

**Seeds:** the settings row with the defaults above. The levels (defaults **to confirm**, see Q1):

| code | name | min_value | fine | jail_hours |
|---|---|---|---|---|
| suspect | Подозреваемый | 1 | 50 | 2 |
| offender | Нарушитель | 100 | 150 | 12 |
| criminal | Преступник | 300 | 400 | 24 |
| villain | Злодей | 600 | 1000 | 72 |
| enemy | Враг края | 900 | 2500 | 168 |

With the existing reputation weights: one merchant kill gives 150 (Нарушитель). A guard defeat gives 300, raised to the heavy floor 600 (Злодей). A ruler kill gives 1000 (Враг края). Decay of 50/day takes 600 to 0 in 12 days.

Settings validation: levels have strictly increasing `min_value` by sort order, level 1 `min_value ≥ 1`, all `≤ max_wanted`; `jail_hours` 1..168; `fine` 0..1 000 000; percentages 0..100 with `min ≤ max`; `heavy_wanted` 1..max_wanted; `outlaw_min_level` one of the 5 codes; hours 1..168; `bail_multiplier` 1..10.

Rollback: `downgrade()` drops the 6 tables and the 3 columns. No backfill: everyone starts with wanted 0.

#### locations-service, Alembic `055_region_jail_location`

```sql
ALTER TABLE Regions ADD COLUMN jail_location_id INT NULL;
CREATE INDEX ix_regions_jail_location_id ON Regions (jail_location_id);
ALTER TABLE Regions ADD CONSTRAINT fk_regions_jail_location
  FOREIGN KEY (jail_location_id) REFERENCES Locations(id) ON DELETE SET NULL;
```
Same pattern as `entrance_location_id`. Rollback drops the FK, the index and the column.

#### battle-service, Alembic `009_battle_law_encounter`

```sql
ALTER TABLE battles ADD COLUMN law_encounter_id INT NULL;
CREATE INDEX ix_battles_law_encounter_id ON battles (law_encounter_id);
```

### 3.2 `law_core.py` (pure, character-service only)

- Value objects `Level(code, sort_order, name, min_value, fine, jail_hours)`, `LawSettings(...)`.
- `effective_wanted(value, decay_at, now, per_day) -> int` = `max(0, value − floor(per_day × secs / 86400))`; `materialise(value, decay_at, now, per_day) -> (new_value, new_decay_at)` advances the anchor by exactly the consumed points (no fraction loss, same as `reputation_core.materialise_decay`); `decay_at=None` at 0.
- `add_wanted(effective, gain, settings, floor=None) -> int` = `min(max_wanted, max(effective + gain, floor or 0))`.
- `level_for(value, levels) -> Level|None` (None for 0); `level_at_least(level, code, levels)`.
- `crime_weight(kill_points) -> int` = `−kill_points if kill_points < 0 else 0`.
- `options(is_outlaw, has_jail, flee_used) -> list[str]`, ordered:
  - not an outlaw: `fine`, `surrender` (only with a jail), `flee` (only if not used), `fight`;
  - an outlaw: `surrender` (only with a jail), `fight`.
- `chance(base, per_point, lo, hi, agility, luck) -> Decimal` (2 decimals); `roll_succeeds(chance, rng) -> (bool, roll)`.
- `extended_until(now, until, pct, cap_hours) -> datetime` = `now + min(remaining × (1 + pct/100), cap)`.
- `bail_price(fine_base, multiplier) -> int` = `max(1, ceil(fine_base × multiplier))`.
- Constants: `CRIME_NPC_KILL`, `CRIME_GUARD_DEFEAT`, `CRIME_JAIL_ESCAPE`, reserved `CRIME_CARAVAN_ATTACK`, `CRIME_PVP_ATTACK`, `CRIME_THEFT`; the statuses; `GUARD_ROLE = 'guard'`, `BANKER_ROLE = 'banker'`.

### 3.3 `activity_lock` (4 copies: character canonical, locations + battle async, inventory sync)

- New reasons `REASON_JAIL = "jail"` and `REASON_LAW_ENCOUNTER = "law_encounter"`.
- `compute_lock(..., jailed_until=None, law_encounter_id=None)` (new keyword arguments, backwards compatible). Priority: **jail** (`jailed_until > now`, with `until`) > **law_encounter** (id set) > unconscious > dungeon > asleep > reading. The returned dict gets one new key, `law_encounter_id` (None unless that reason applies), and `until` for jail.
- `lock_for_character` reads the two new attributes. The SQL in `get_activity_lock` (locations, battle, inventory) selects `jailed_until, law_encounter_id` as well.
- `lock_message`: jail → «Персонаж в тюрьме до HH:MM МСК»; law_encounter → «Персонажа остановила стража — сначала нужно решить, как поступить».
- The 4 files keep their current per-service variants. Only the shared logic changes identically. They are not CI-guarded, so the reviewer diffs them.

### 3.4 Write paths (character-service `law_crud.py`, sync, no commit inside unless stated)

**`load_wanted_for_update(db, character_id, region_id)`**: ensure the row (`INSERT … ON DUPLICATE KEY UPDATE id=id`, plus the SQLite test path), `SELECT … FOR UPDATE`, materialise decay.

**`register_crime(db, *, crime_type, character_id, region_id, points, event_key, location_id=None, victim_id=None, battle_id=None, floor=None, now)`**:
1. `points ≤ 0` and no floor → nothing (bandit = not a crime).
2. Insert the `law_crimes` row (`status='reported'`). A duplicate key → return `duplicate` (a pre-check plus the UNIQUE constraint as the hard guarantee).
3. **2a:** apply at once: lock the wanted row, `new = add_wanted(effective, points, floor)`, set `decay_at` (now if it was 0, unchanged otherwise; at 0 → None), `wanted_applied = new − old`, `resolved_at = now`, plus a `law_log` row `crime` (key `law:crime:{crime_id}`). Return `WantedChange(character_id, region_id, level_before, level_after)`, which feeds the notifications.
   **2b hook:** this is the single function where a witness step is inserted. It will write `status='pending_witness'` and skip step 3 until resolved.

**NPC kill hook (`main.update_npc_status`)**, in the same transaction, right after `reputation_crud.apply_npc_kill`:
- For each player killer (`is_npc=0`, the same list `apply_npc_kill` uses): `register_crime(crime_type='npc_kill' or 'guard_defeat', points=crime_weight(kill_points of this NPC), floor=heavy_wanted if guard else None, key='crime:npc_kill:{npc}:{battle_or_stamp}:{killer}')`. `kill_points` is resolved exactly as reputation resolves it (override ?? role weight ?? `*`); expose a small helper in `reputation_crud`, not a re-implementation.
- **Guard KO (L7):** when `npc.npc_role == 'guard'` and `status == 'dead'`, do not set `dead`. Run a conditional `UPDATE characters SET unconscious_until = :until WHERE id=:id AND npc_status='alive' AND (unconscious_until IS NULL OR unconscious_until <= :now)`. `knocked = rowcount == 1`, and that replaces `killed` as the trigger for the reputation and crime. Add a `law_log` `guard_ko` row on the NPC (key `law:guard_ko:{npc}:{battle}`). The response becomes `{"ok": true, "status": "alive", "killed": knocked, "knocked_out_until": iso|null}` (additive; battle-service only logs the status code).
- After commit: `reputation_notify.publish_tier_changes(...)` (existing) + `law_notify.publish_wanted_changes(...)`.

**Entry evaluation `evaluate_entry(db, character, location_id, source, now) -> Optional[Encounter]`** (called inside the moving transaction, character row already locked):
1. Skip if the character is an NPC, already has `law_encounter_id`, or is jailed.
2. `region_id = reputation_crud.location_region(db, location_id)`; none → skip.
3. `is_outlaw = reputation tier code in region == 'outlaw'` (effective reputation value via `reputation_crud`).
4. `wanted = effective_wanted(...)`; skip if `wanted == 0 and not is_outlaw`.
5. Guard = `SELECT id FROM characters WHERE is_npc=1 AND npc_role='guard' AND npc_status='alive' AND current_location_id=:loc AND (unconscious_until IS NULL OR unconscious_until <= :now) ORDER BY id LIMIT 1`; none → skip. A guard busy in another battle still "meets" the player; availability matters only for `fight` (see 3.5).
6. `level = level_for(wanted)`; if `is_outlaw`, raise it to at least `outlaw_min_level`. `has_jail = Regions.jail_location_id IS NOT NULL` (raw SQL).
7. Insert the `law_encounters` row (`pending`, snapshots, `expires_at`). Set `character.law_encounter_id`. Write a `law_log` row.
8. Return the public encounter DTO (3.6), which the router adds to its response. The notification (`law_notify`, category `system`, ws_type `law_encounter`) is sent after the caller's commit.

**Hook points:**
- `main.update_location` (internal, used by move_and_post + quick_move): lock the character row `FOR UPDATE`. If `activity_lock.lock_for_character(c)` reports `jail` or `law_encounter` → **409** with the lock message (anti-dodge; locations-service maps any non-200 to an error today — see 3.7 for the mapping change). When the location actually changes → `evaluate_entry(source=payload.get("source","move"))`. Response gets `"law_encounter": {...}|null` (additive).
- `crud.execute_teleport`: after the location is set and before the commit → `evaluate_entry(source='teleport')`. The teleport response schema gets `law_encounter: Optional[LawEncounterOut]`.
- **Not hooked:** home-teleport scroll (user decision 4), admin move, dungeon knock-out return, character approval.

### 3.5 Encounter resolution (character-service)

All choices: owner only. The encounter must be `pending` and belong to the character. `request_id` (UUID) is required, and `law_log` key `law:choice:{encounter_id}` makes a repeated choice a no-op (returns the current state). Re-validate at choice time: `has_jail` is re-read; if the region lost its jail, `surrender` → 409 «В этом крае больше нет тюрьмы» and the options are recomputed.

| Choice | Allowed when | Effect |
|---|---|---|
| `fine` | not an outlaw | One transaction: ledger `law_fine` (key `law_fine:{enc}`), purse → region treasury (`apply_tax=True`). `InsufficientFunds` → **400** «Недостаточно … для уплаты штрафа» (the encounter stays pending). Then wanted in the region → 0, encounter `fined`, clear `law_encounter_id`, log `fine`. |
| `surrender` | has_jail | `send_to_jail(encounter, level)` (below), status `jailed`. |
| `flee` | not an outlaw, `flee_used=0` | Roll with the flee chance. Success → encounter `fled`, lock cleared, the character **stays where they are**, wanted unchanged, log `flee_ok`. Failure → `flee_used=1`, log `flee_fail`, then **automatically `fight`**. If no guard is free for the fight, the encounter stays `pending` without the flee option, and the response says «Бежать не удалось — стража преградила путь». |
| `fight` | always | Pick a free guard: alive, not KO'd, at the location, not in an active battle (prefer `guard_npc_id`). None free but one alive and busy → **409** «Стражник сейчас занят — попробуйте чуть позже». No guard at all left → encounter `guard_gone`, lock cleared, response `{result:"guard_gone"}`. Otherwise: heal the guard to full (raw SQL on `character_attributes`, current = max for health/mana/energy/stamina), set status `fighting` + `fight_started_at` and commit, then call battle-service `POST /battles/internal/guard`. On an HTTP failure → revert to `pending` and answer 502 «Не удалось начать бой со стражей». Store `battle_id`. Response `{result:"fight", battle_id}`. |

**Guard battle end**: `POST /characters/internal/law/battle-result` `{battle_id, law_encounter_id, winner_team, aborted}` (internal token), idempotent through a conditional `UPDATE law_encounters SET status=… WHERE id=:id AND status='fighting'`:
- `aborted` (admin force-finish) → back to `pending` (`battle_id` cleared; the choice is offered again).
- Player's team won → `won`, lock cleared, log `fight_won`. The KO, −300 reputation and heavy wanted already came through the npc-status path (L7). The callback is sent after the NPC-death loop, and it does not depend on the npc-status call having succeeded.
- Player lost (including timeout) → has_jail ? `send_to_jail` (status `jailed`) : **forced fine** (see Q3 default: charge `min(fine, balance)` as `law_fine`, key `law_fine_forced:{enc}`; wanted → 0 only if the fine is paid in full; status `auto_fined`; lock cleared).
- `send_to_jail` runs `_prepare_move`. When the jail location == the current location, it skips the move side effects.

**`send_to_jail(db, encounter, level)`** (async router-level helper because of the HTTP side effects in `_prepare_move`):
1. Jail location = `Regions.jail_location_id` of the encounter region (re-read).
2. If it differs from the current location → `await _prepare_move(db, cid, from_loc, "jail")`, which cancels gathering and expires intents/party in the old location. It refuses in battle or dungeon, which cannot happen here: the guard battle is already `finished` at callback time.
3. One transaction, character row locked: `current_location_id = jail_loc`, `house_room_id = NULL`, travel cooldown reset (as `apply_admin_move`), a location-journal row of kind `jail`; `jailed_until = now + jail_hours`, `jail_region_id`; `law_encounter_id = NULL`; wanted in the region → 0 (log row); insert `law_jail_terms` (`serving`, `bail_price = bail_price(level.fine, multiplier)`, `next_escape_at = NULL`); encounter `jailed`; log `jail`.
4. After commit → notification (`system`, ws_type `law_jailed`): «Стража края «{region}» заключила вас под стражу до {HH:MM МСК}».
5. On a `_prepare_move` failure (502): the encounter stays as it is (`pending` / `fighting`) and the scheduler pass retries the jailing (`status='fighting'` with the battle finished, or the timeout). A player-triggered surrender returns 502 «Не удалось доставить в тюрьму, попробуйте ещё раз».

Implementation note: `apply_admin_move` is reused or extended with a `kind`/`journal` parameter. Do not copy-paste it.

**Timeout auto-resolution (law pass)**, `pending` with `expires_at <= now`:
- has_jail (re-read) → `send_to_jail` (log `auto_surrender`);
- no jail → forced fine (log `auto_fine`, rules as above). This applies to outlaws without a jail too: they cannot fight offline (Q3).
- Notification «Вы так и не ответили страже — …».

### 3.6 API contracts

All character-service routes live under `/characters` (already routed by nginx). Pydantic v1. Errors are in Russian. Player auth = `get_current_user_via_http`. "Owner" = `verify_character_ownership`-style (the character's `user_id` == the current user). "Private" = `visibility.require_private_access` (owner or staff with `characters:read`).

**Player — character-service (`law_api.py`)**

- `GET /characters/{character_id}/law` (private) → 200
  ```json
  {
    "wanted": [{"region_id": 3, "region_name": "…", "level_code": "offender", "level_name": "Нарушитель",
                "fine": 150, "jail_hours": 4, "decaying": true}],
    "encounter": null,
    "jail": null
  }
  ```
  Only regions with effective wanted > 0. No raw wanted numbers for players (the level is enough; consistent with reputation). `encounter` and `jail` use the shapes below.
- `GET /characters/{character_id}/law/encounter` (owner) → 200 `{"encounter": LawEncounterOut | null}`
  ```json
  LawEncounterOut = {"id": 12, "region_id": 3, "region_name": "…", "location_id": 55, "guard_name": "Стражник Орм",
    "guard_avatar": "…", "is_outlaw": false, "has_jail": true, "level_name": "Нарушитель", "fine": 150,
    "jail_hours": 4, "options": ["fine","surrender","flee","fight"], "flee_chance_pct": 42.5,
    "status": "pending", "battle_id": null, "expires_at": "2026-11-05T12:00:00"}
  ```
- `POST /characters/{character_id}/law/encounter/{encounter_id}/choice` (owner) body `{"choice": "fine|surrender|flee|fight", "request_id": "uuid"}` → 200
  ```json
  {"result": "fined|jailed|fled|fight|flee_failed_blocked|guard_gone", "message": "…",
   "battle_id": null, "jail": null, "encounter": null}
  ```
  400 insufficient gold or a choice not in `options`; 404 the encounter is not this character's; 409 not pending / guard busy / no jail any more; 502 battle or move failure.
- `GET /characters/{character_id}/law/jail` (private) → `{"jail": LawJailOut|null}`
  ```json
  LawJailOut = {"id": 7, "region_id": 3, "region_name": "…", "location_id": 90, "location_name": "Темница",
    "until": "…", "bail_price": 300, "can_escape_at": null, "escape_chance_pct": 18.0, "escape_attempts": 1}
  ```
  (`escape_chance_pct` and `bail_price` are shown to the owner. For staff the same.)
- `POST /characters/{character_id}/law/jail/escape` (owner) `{"request_id"}` → 200 `{"success": bool, "message": "…", "jail": LawJailOut|null}`. 409 when not jailed or on cooldown («Следующая попытка побега — в HH:MM МСК»). Success → term `escaped`, `jailed_until = now`, `register_crime('jail_escape', points=0, floor=heavy_wanted, key='crime:escape:{term}:{attempt}')`. Failure → `until = extended_until(...)` (both the term and `characters.jailed_until`), attempts+1, `next_escape_at = now + cooldown`. Both write a log row with chance and roll. Key `law:escape:{term}:{attempt_no}` → a double click is a no-op.
- `POST /characters/{character_id}/law/jail/bail` (owner, self-bail from jail) `{"request_id"}` → 200 `{"message", "jail": null}`. Ledger `law_bail` (key `law_bail:{term_id}` — one bail per term), purse → jail-region treasury; 400 insufficient; 409 not jailed. Term `bailed`, `jailed_until = now`.
- `GET /characters/law/prisoners?q=&page=1&page_size=20` (any authenticated user; page_size ≤ 50; `q` ≤ 50 chars, LIKE-escaped) → `{"items":[{"character_id","name","avatar","region_name","location_name","until","bail_price"}],"total"}`. Being in jail is public in-world (the prisoner stands in the jail location); wanted values are not exposed.
- `POST /characters/law/bail` `{"payer_character_id", "banker_npc_id", "prisoner_character_id", "request_id"}` → 200 `{"message": "…", "paid": 300}`. Checks: the payer is owned by the current user and is a player; the payer is not activity-locked; the banker is an alive NPC with `npc_role='banker'` at the **payer's current location** (any region, user decision 6) and passes `reputation_crud.require_npc_tier`; the prisoner has a `serving` term. Payer == prisoner is impossible (the prisoner is locked), but any other character, own alts included, may pay (user decision 6). Ledger `law_bail` (key `law_bail:{term_id}`): payer purse → **the jail region treasury** (`apply_tax=True`). A concurrent second bail → 409 «Залог уже внесён». Notifications: the prisoner gets «За вас внесли залог: {payer name}. Вы свободны»; the payer gets the response message.

**Admin — character-service** (prefix `/characters/admin/law`)

| Method/path | Permission | Body / response |
|---|---|---|
| `GET /settings` | `reputation:read` | `{settings:{…all law_settings fields except pass_last_run_at}, levels:[{code,sort_order,name,min_value,fine,jail_hours}]}` |
| `PUT /settings` | `reputation:settings` | the same shape (exactly the 5 codes). Validation per 3.1. A change of `decay_per_day` first materialises all rows with `value>0` at the old rate (same transaction). |
| `GET /characters/{id}` | `reputation:read` | `{wanted:[{region_id, region_name, value, level_code, level_name}], encounter: {...staff fields incl. wanted_value}|null, jail: {...}|null, crimes:[last 50], log:[last 100 incl. reason, actor username, chance/roll]}` |
| `POST /characters/{id}/release` | `reputation:manage` | `{reason: 3..500 trimmed, request_id: UUID}`. Ends a `serving` term (`released`, `jailed_until=now`) **and/or** cancels a `pending`/`fighting` encounter (`cancelled`, lock cleared; a running battle is left to finish, and its callback becomes a no-op because the status is no longer `fighting`). 409 when there is nothing to release. Log `staff_release`/`staff_cancel`, notification «Решением властей вы освобождены». |
| `POST /characters/{id}/clear-wanted` | `reputation:manage` | `{region_id: int|null (null = all regions), reason, request_id}`. Sets wanted → 0 and logs `staff_clear`. |

**Internal — character-service** (`verify_internal_token`; nginx 403 on `/characters/internal/`)
- `PUT /characters/internal/{id}/update_location`: body gets an optional `source: "move"|"quick_move"`. The response gets `law_encounter: LawEncounterOut|null`, and 409 when jailed or in an encounter (3.4).
- `PUT /characters/internal/npc-status/{id}`: guard KO + crime (3.4); the response is additive.
- `POST /characters/internal/law/battle-result`: 3.5; 200 `{"ok": true, "status": "<encounter status>", "duplicate": bool}`; 404 unknown encounter; 409 when `battle_id` ≠ the encounter's battle.

**battle-service**
- `POST /battles/internal/guard` (internal token) `{"law_encounter_id": int, "character_id": int, "guard_npc_id": int}` → 201 `BattleCreated`. The player is team 1 and must have the `law_encounter` lock with exactly this id (that is the lock exemption, like the dungeon exemption), not be in battle, and must not be locked otherwise. The guard is team 2 and must be an NPC with `npc_role='guard'`, alive, not KO'd (activity lock), and not in battle → else 409. `_assemble_battle(db, [player, guard], [1, 2], "pvp_attack", location_id=player's location)`, then set `battles.law_encounter_id`. The guard is registered with autobattle as usual.
- `_finalize_battle`: after the NPC-death loop, `_notify_law_battle_end(db, battle_id, winner_team, battle_state, aborted=False)` posts fire-and-forget with 3 retries to `/characters/internal/law/battle-result`. `_force_finish_battle` calls it with `aborted=True`. Both are no-ops when the tag is NULL.
- `GET /battles/internal/{id}/result`: the response gets `law_encounter_id` (additive).
- `POST /battles/` (`create_battle_endpoint`, «Нападение»): refuse an NPC participant that is `npc_status='dead'` or currently KO'd (`unconscious_until > now`) → 409 «Этот персонаж сейчас недоступен для боя». This also closes the analyst's "server does not check NPC alive" gap.

**locations-service**
- `move_and_post` / `quick_move`: pass `source` to `update_location`. A 409 from `update_location` is returned as 409 with its `detail` (instead of the generic 500). The responses get `law_encounter: Optional[dict]` (`PostResponse` and the quick-move response schema, additive).
- **Jail posting exception:** `move_and_post` and `POST /posts/` (create) replace `check_not_activity_locked` with a variant. If the lock reason is `jail` **and** `destination_location_id == current location`, it is allowed; any other lock or destination → 409 as today. The battle and gathering checks stay.
- **Lock gaps closed** (`check_not_activity_locked` → 409): NPC dialogue choose (`main.py` ~L2575). Quest abandon stays allowed (harmless).
- Regions admin: `RegionBase/RegionUpdate/RegionRead` + `jail_location_id: Optional[int]`. Validation on update: the location exists and resolves to **this** region (`econ_core.SQL_RESOLVE_LOCATION` / the same district→region resolution), else 400 «Локация тюрьмы должна находиться в этом крае». Permission is unchanged (`locations:update`). `GET` region details include the field.

**inventory-service**
- Auction write routes (`create listing`, `place bid`, `buyout`, `deposit`, `claim`) → `check_not_activity_locked` for the acting character → 409. This applies to any lock reason, consistent with all other trade routes.
- The lock copy reads the new columns: trade, crafting and home-teleport are already lock-checked.

**econ_core (4 copies)**: `OP_LAW_FINE = "law_fine"`, `OP_LAW_BAIL = "law_bail"`, `LAW_OP_TYPES` added into `OP_TYPES`. Contract cases unchanged unless they enumerate op types (then add them).

### 3.7 Scheduler: `law_pass.run_pass(session_factory, now)`

Called from `econ_scheduler.run_scheduled_once` **before** the economy `tick_enabled` switch (next to `reputation_decay.run_pass`). Throttle: a conditional UPDATE claim on `law_settings.pass_last_run_at` (≥ 55 s), so several workers never double-run. Steps, each item in its own transaction, errors logged per item:
1. **Expired encounters** (`pending`, `expires_at <= now`) → auto-resolution (3.5). The async `send_to_jail` is run through `asyncio.run(...)` per item: the scheduler thread has no loop.
2. **Lost callbacks:** `fighting` with `fight_started_at <= now − 2 min` → `GET /battles/internal/{battle_id}/result`. When finished, apply the same handler as the callback (idempotent). A 404 battle → back to `pending`.
3. **Served terms:** `serving` with `until <= now` → `served`, `resolved_at`, notification «Срок заключения окончен — вы свободны» (`notified=1`). The lock was already lazily free.
4. **Guard recovery:** guards whose `unconscious_until` passed in the last pass window, or any alive, non-KO'd guard not in battle with `current_health < max_health` → full heal (raw SQL on `character_attributes`). Optionally `unconscious_until = NULL`.
5. Wanted decay is **not** materialised here (lazy reads are exact; no level-down notification in 2a).

### 3.8 Notifications (`law_notify.py`, sync pika → `general_notifications`, after commit, best-effort)

Category `system` (mandatory) for: an encounter created (ws_type `law_encounter`), jailed (`law_jailed`), released / served / bailed / escaped / staff release (`law_released`), auto-resolution. Category `progress` for wanted level changes caused by a crime: «Вас разыскивают в крае «{region}»: {level_name}». The `ws_type` lets the frontend refresh `getMe`/law state. `user_id` comes from `characters.user_id`; NPCs are skipped.

### 3.9 Frontend

All new and changed components: TypeScript, Tailwind, design-system classes (`modal-overlay`, `modal-content`, `gold-text`, `btn-blue`, `btn-line`, …), 360 px+ adaptive, no `React.FC`, every API error shown in Russian.

- `src/api/law.ts`: typed client for the player and admin endpoints (`LawEncounterOut`, `LawJailOut`, `LawStateOut`, …).
- `hooks/useActivityLock.ts`: `ActivityLockReason` += `'jail' | 'law_encounter'`; expose `until` and `law_encounter_id`.
- `pages/LocationPage/GuardEncounterModal.tsx` (new). Opens when the activity lock reason is `law_encounter` (from `/users/me`, on mount and after `getMe`) or when a move/quick-move/teleport response carries `law_encounter`. It fetches `GET …/law/encounter` and shows the guard (avatar, name), the level, the fine, the jail term and the flee chance, with one button per `options` entry and a confirmation for `surrender`/`fight`. Closing the modal hides it, and a compact banner «Стража ждёт вашего решения» + «Ответить» stays. It reopens on every page load and focus while the lock persists. On `fight` → navigate to `battlePath(locationId, battle_id)`. On `jailed` → `getMe` + navigate to the jail location. Show the expiry («Если не ответить до HH:MM МСК — …»).
- `pages/LocationPage/JailBanner.tsx` (new). Replaces the generic lock banner for reason `jail`: countdown to `until`, the jail region, bail price + «Внести залог» (self-bail, confirm), «Попытаться бежать» (disabled until `can_escape_at`, showing the chance and the cooldown time), with the result message shown. When the term ends (countdown reaches 0) → `getMe`.
- `LocationPage.tsx`: for reason `jail` **in the current location** the post form stays enabled. Every other action stays disabled as today. `handleSubmitPost`/`handleQuickMove` read `law_encounter` from the response; the teleport flow (`TeleportMenu.tsx`) does the same.
- Battle end screen: «Вернуться в локацию» uses the character's **current** location from a fresh `getMe`, not the battle's location. After a lost guard fight the player is in jail. Locate the component that builds this link and change only that.
- `ProfilePage/ReputationTab/ReputationTab.tsx`: a «Розыск» block (per region: level name, «спадает со временем»; empty state «Вас нигде не разыскивают»), plus a jail status line if jailed. Private like the tab.
- `pages/LocationPage/BankModal/` → new tab `BankBailTab.tsx` «Залог»: prisoner search (debounced `GET /characters/law/prisoners`), list with bail price and remaining time, «Внести залог» with a confirmation showing the price; the payer = the current character; errors shown.
- Admin:
  - `Admin/ReputationPage/`: new tab «Закон» (`LawSettingsTab.tsx`): the settings form and the 5-level table (name, threshold, fine, term 1–168). Editable only with `reputation:settings`; read-only otherwise.
  - `Admin/CharactersPage/tabs/ReputationTab.tsx` (or a new `LawPanel.tsx` inside it): wanted per region (numbers), current encounter/jail, crimes and the law log; «Освободить» and «Снять розыск» (region select or all) with a mandatory reason; buttons only with `reputation:manage`; `request_id` generated per submit.
  - `AdminLocationsPage/EditForms/EditRegionForm/EditRegionForm.tsx`: «Тюрьма края», a select of the region's locations + «нет».
- No change is needed in the NPC admin: role `guard` already exists. The NPC list hides KO'd NPCs (backend, 3.10).

### 3.10 Other backend touch points

- character-service `GET /characters/npcs/by_location` (and any other player-facing NPC list in character-service) excludes NPCs with `unconscious_until > now`. This also fixes the NULL-role exclusion side bug: use `(npc_role IS NULL OR npc_role != 'mob')`, the same expression `update_npc_status` already uses.
- The profile `activity_lock` (`main.py` ~L2463) includes the new reasons automatically via `lock_for_character`. `/users/me` passes the dict through unchanged (verified `user-service/main.py:356`).

### 3.11 Security

- Player law reads are private (owner + staff). Choices, escape and self-bail are **owner only**. The bail by others requires the payer's ownership, the payer at a banker's location, and the payer not locked.
- Rate limiting: flee is limited by state (once per encounter); escape by the server-side cooldown (6 h); choices, bail and escape by `request_id` + deterministic ledger/log keys (a double submit charges once). The prisoner search is a read with `page_size ≤ 50` behind the existing nginx limits. No new nginx config.
- Randomness: server only (`secrets.SystemRandom`); chance and roll are logged.
- Validation: choice enum, UUID `request_id`, reason 3..500 trimmed, `q` ≤ 50 with LIKE wildcards escaped, settings bounds (3.1), region jail location must belong to the region.
- Players never see raw wanted numbers or staff reasons; staff see everything.
- Internal routes: `X-Internal-Token` + the nginx 403 on `/characters/internal/` and `/battles/internal/` (existing).
- SQL: parameterised `text()` only.
- Money: only via `econ_ledger.post_operation` (balance guard, `InsufficientFunds`, idempotency key, tax).

### 3.12 Data flow

```
Move:  Player → POST /locations/{dest}/move_and_post (locations)
         └─ post created → PUT /characters/internal/{id}/update_location {new_location_id, source}
              character-service TX: lock row; refuse if jail/encounter (409);
                set location; evaluate_entry → law_encounters + characters.law_encounter_id → COMMIT
              → pika (system, law_encounter)
         ← {…post, law_encounter} → frontend opens GuardEncounterModal
Fight: Player → POST /characters/{id}/law/encounter/{e}/choice {fight}
         character-service: status=fighting, heal guard → COMMIT
         → POST /battles/internal/guard (battle-service, tag law_encounter_id)
       … battle ends → _finalize_battle: NPC-death loop → PUT /characters/internal/npc-status/{guard}
              (guard: KO 6 h + rep −300 + crime guard_defeat, heavy wanted)
         → POST /characters/internal/law/battle-result {winner_team, aborted}
              lost → _prepare_move (locations HTTP) → TX: move to jail, jailed_until, wanted=0, term → COMMIT → pika
         (fallback: law_pass polls GET /battles/internal/{id}/result)
Crime: battle → PUT npc-status (dead) → TX: alive→dead, apply_npc_kill (rep), register_crime (wanted) → COMMIT → pika
Bail:  Payer at banker → POST /characters/law/bail → TX: ledger law_bail (payer → jail-region treasury, 10 % tax) + term bailed → COMMIT → pika to prisoner
```

### 3.13 Rollout

- Migrations auto-run on container start: character `039_law`, locations `055_region_jail_location`, battle `009_battle_law_encounter`. No user-service migration.
- **Deploy order:** all three services in one deploy. If they skew: locations and battle read `jailed_until, law_encounter_id` in their lock SQL, so **character-service `039` must be applied before** the new locations/battle/inventory code serves requests. Mitigation: the lock readers treat an "unknown column" error like the existing `regen_anchor_at` fallback (retry the old SELECT), so a skew cannot 500 every route. battle `009` is read only by battle-service itself.
- The feature is live at deploy: existing NPCs with role `guard` start meeting players with the **outlaw** tier at once (wanted starts at 0 for everyone). Admins must assign jail locations per region; without one, guards only fine or fight (user decision 2). Pre-beta: acceptable, no announcement gating.
- Copies: econ_core ×4 (`scripts/check_econ_copies.sh` must pass); activity_lock ×4 (not CI-guarded — reviewer diff).
- Residual risks: (1) the post is created before `update_location` refuses a dodging second move (an orphan post, cosmetic); (2) the callback and the polling both depend on battle-service and Redis; a battle stuck "in progress" forever keeps the encounter `fighting` until staff release it; (3) `_prepare_move` HTTP failure delays jailing to the next pass (the player stays locked by the encounter meanwhile, so nothing is dodged).

### 3.14-ANSWERED — User decisions 2026-11-04 (OVERRIDE anything conflicting in §1–§4)

- **A1:** Defaults accepted EXCEPT jail terms: **max term is 7 days (168 h)**. New seed terms: Подозреваемый **2 h**, Нарушитель **12 h**, Преступник **24 h**, Злодей **72 h**, Враг края **168 h** (fines unchanged 50/150/400/1000/2500). Validation `jail_hours` **1..168** everywhere (backend + admin UI); `max_remaining_jail_hours` default **168**. Decay 50/day, heavy floor 600, outlaw minimum = Преступник.
- **A2:** «Нападение» on a guard → also a 6 h KO (never a permanent death) — as designed.
- **A3:** No jail + cannot pay → take gold up to the fine; partial payment keeps the wanted — as designed.
- **A4:** Escape failure: +50 % of remaining, capped at max_remaining_jail_hours (168 h by default).
- **A5:** Successful escape: wanted ≥ heavy floor, decays normally — as designed.
- **A6:** Home scroll: usable BEFORE an encounter (arrival via scroll is never met); **blocked while an encounter is pending** — as designed.
- **A7 (CHANGED):** Flee success → the character is **moved back to the location they came from** (the encounter stores `from_location_id`; if unknown/invalid — stays), encounter closed, wanted unchanged; and **the same location's guards do not stop this character again for 1 hour** (per character × location cooldown, e.g. `law_encounter_cooldowns` or a column on the encounter row; checked in entry evaluation). The move back must not trigger a new encounter in the origin location (skip evaluation for this system move).

- **A8 (2026-11-04, countdowns):** time limits are shown to the player as a **live countdown** («осталось 2 д 05:13:20»), not «до HH:MM». Applies to: the jail banner, the guard-encounter auto-surrender timer, the escape cooldown, the unconscious lock (useActivityLock), AND **house buffs** (`HousesPage/HouseBuffs.tsx`, currently «до dd.mm hh:mm») — use one shared util/hook (e.g. `utils/formatRemaining.ts` + `hooks/useCountdown.ts`). Backend lock messages (activity_lock, 4 copies) must not say «до HH:MM МСК»; use a relative remaining text computed at request time («Персонаж в тюрьме — осталось 2 д 5 ч»), identical in all 4 copies.

### 3.14 Open business questions (historical — see 3.14-ANSWERED)

- **Q1 — Fine / term defaults:** levels Подозреваемый 50 g / 1 h, Нарушитель 150 / 4 h, Преступник 400 / 12 h, Злодей 1000 / 24 h, Враг края 2500 / 48 h; wanted decay 50/day; heavy floor 600; outlaw minimum level = Преступник (12 h). All editable in the admin, so a wrong default is cheap.
- **Q2 — «Нападение» on a guard:** default **also a 6 h KO**, not a permanent death (all guards are never permanently killed). The alternative: only the encounter fight is non-lethal and «Нападение» still kills guards forever.
- **Q3 — No jail in the region and the player cannot pay** (24 h timeout, or a lost guard fight, or an outlaw without a jail who never fights): default **forced fine = take all the gold up to the fine amount**. If paid in full the wanted is cleared; if partial the wanted stays (they will be stopped again). Alternatives: a debt; an extra wanted increase; a 1 h knock-out.
- **Q4 — Escape failure extension cap:** +50 % of the remaining term, capped so the remaining term never exceeds 48 h (default). The alternative: no cap.
- **Q5 — Successful escape wanted:** raised to at least the heavy floor (600) and **decays normally** (default). The alternative: frozen (no decay) until paid or served.
- **Q6 — Home-teleport scroll while an encounter is pending:** default **blocked** (decision 5: "заблокирован на месте"); the scroll only avoids being met at the destination. The alternative: the scroll may be used to escape a pending encounter.
- **Q7 — Flee success:** default the player **stays in the location**, encounter closed, wanted unchanged. The alternative: pushed back to the previous location, or wanted +X.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**All developer tasks: NO commits, NO pushes, NO `git add` (the user commits once at the end).** Backend: `python -m py_compile` on every modified file, plus the service test suite inside its container. Frontend: `npx tsc --noEmit` and `npm run build` inside the frontend container. User-facing text is in Russian.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **character-service law core:** migration `039_law` (6 tables, 3 `characters` columns, seeds, FK indexes; §3.1); ORM models; `law_core.py` (§3.2); canonical `activity_lock.py` with the `jail` + `law_encounter` reasons (§3.3); `law_crud.py` with wanted read/materialise, `register_crime`, `evaluate_entry` (§3.4); a `reputation_crud` helper for kill points; hooks in `update_npc_status` (crime + guard KO), `update_location` (row lock, 409 on jail/encounter, evaluate, response field) and `execute_teleport`; NPC list excludes KO'd NPCs + the NULL-role fix (§3.10). No commits/pushes/`git add`. | Backend Developer | DONE | `character-service/app/alembic/versions/039_law.py`, `app/models.py`, `app/law_core.py`, `app/law_crud.py`, `app/activity_lock.py`, `app/reputation_crud.py`, `app/main.py`, `app/crud.py`, `app/schemas.py` | — | Migration upgrades and downgrades on MySQL; revision id ≤ 32; every FK column indexed. Repeated npc-status report → no extra crime/wanted; bandit kill → no crime; guard → `unconscious_until` set, stays `alive`, −300 rep + wanted ≥ heavy; the encounter is created in the same commit as the location; a second move while locked → 409; home teleport not evaluated; py_compile passes. |
| 2 | **character-service law flows + API + scheduler:** `law_api.py` router (player, admin, internal endpoints exactly per §3.6); choices (§3.5) incl. guard pick/heal, battle-service call, `send_to_jail` reusing `_prepare_move` + an extended `apply_admin_move`; battle-result callback; escape; self-bail and banker bail; prisoners list; staff release / clear wanted; settings GET/PUT; `law_pass.py` (§3.7) hooked into `econ_scheduler` before the tick switch; `law_notify.py` (§3.8). No commits/pushes/`git add`. | Backend Developer | DONE | `app/law_api.py`, `app/law_crud.py`, `app/law_pass.py`, `app/law_notify.py`, `app/econ_scheduler.py`, `app/main.py` (router include, `_prepare_move`/`apply_admin_move` reuse), `app/crud.py`, `app/schemas.py`, `app/battle_client.py` (or the existing HTTP helper) | 1, 3 (op types), contract of 5 | Contracts exactly per §3.6; every money move goes through `post_operation` with a deterministic key (double submit = one charge); fines and bail to the right region treasury with tax; choices validated against `options`; RBAC per the §3.6 admin table; the pass is throttled, runs with the econ tick disabled, and is idempotent; notifications only after commit; py_compile passes. |
| 3 | **econ_core:** `OP_LAW_FINE`, `OP_LAW_BAIL`, `LAW_OP_TYPES` in `OP_TYPES`; copy byte-identically into the 4 services; update the contract cases only if they enumerate op types. No commits/pushes/`git add`. | Backend Developer | DONE | `{character,inventory,locations,dungeon}-service/app/econ_core.py` | — | `sh scripts/check_econ_copies.sh` passes; existing econ tests green in all 4 services. |
| 4 | **locations-service:** migration `055_region_jail_location` (FK SET NULL + index); `Region` model + `RegionBase/RegionUpdate/RegionRead` `jail_location_id` with the same-region validation; `activity_lock.py` copy (new reasons + SELECT + unknown-column fallback); jail posting exception in `move_and_post` and `POST /posts/`; pass `source` + map a 409 from `update_location` + `law_encounter` in the move/quick-move responses; lock check on NPC dialogue choose. No commits/pushes/`git add`. | Backend Developer | DONE | `locations-service/app/alembic/versions/055_region_jail_location.py`, `app/models.py`, `app/schemas.py`, `app/main.py`, `app/crud.py`, `app/activity_lock.py` | contract of 1 | A jailed character can post only in the current location; moving/posting elsewhere → 409 with the jail text; an encounter lock blocks posts; the region jail location from another region → 400; py_compile passes. |
| 5 | **battle-service:** migration `009_battle_law_encounter`; model column; `POST /battles/internal/guard` (§3.6) with the encounter-lock exemption; `_notify_law_battle_end` after the NPC-death loop in `_finalize_battle` and with `aborted=True` in `_force_finish_battle`; `law_encounter_id` in `/internal/{id}/result`; refuse dead/KO'd NPC participants in `create_battle_endpoint`; `activity_lock.py` copy (new reasons + SELECT + fallback). No commits/pushes/`git add`. | Backend Developer | DONE | `battle-service/app/alembic/versions/009_battle_law_encounter.py`, `app/models.py`, `app/main.py`, `app/activity_lock.py`, `app/schemas.py` | contract of 2 | The guard battle is created only for the matching encounter lock and a free, alive, non-KO'd guard; the callback carries `winner_team`/`aborted`; a battle without the tag sends nothing; «Нападение» on a KO'd guard → 409; py_compile passes. |
| 6 | **inventory-service:** `activity_lock.py` copy (new reasons + SELECT + fallback); `check_not_activity_locked` on the auction write routes (create listing, bid, buyout, deposit, claim). No commits/pushes/`git add`. | Backend Developer | DONE | `inventory-service/app/activity_lock.py`, `app/main.py` (and/or `app/crud.py`) | contract of 1 | A jailed character gets 409 on every auction write route and on trade/crafting; py_compile passes. |
| 7 | **Frontend player side:** `api/law.ts`; `useActivityLock` new reasons; `GuardEncounterModal.tsx` (reopens until resolved, all options, fight → battle, jailed → jail location); `JailBanner.tsx` (countdown, self-bail, escape with cooldown/chance); post form enabled in the jail location only; move/quick-move/teleport responses open the modal; battle end «back to location» uses the current location; profile ReputationTab «Розыск» block; BankModal «Залог» tab (prisoner search + pay). No commits/pushes/`git add`. | Frontend Developer | DONE | `src/api/law.ts`, `src/hooks/useActivityLock.ts`, `pages/LocationPage/GuardEncounterModal.tsx`, `pages/LocationPage/JailBanner.tsx`, `pages/LocationPage/LocationPage.tsx`, `pages/LocationPage/TeleportMenu.tsx`, `pages/LocationPage/BankModal/BankModal.tsx`, `pages/LocationPage/BankModal/BankBailTab.tsx`, `ProfilePage/ReputationTab/ReputationTab.tsx`, battle result component | 2, 4, 5 | TS + Tailwind + design system; adaptive at 360 px; no `React.FC`; every error shown in Russian; a refresh during an encounter reopens the modal; tsc + build pass. |
| 8 | **Frontend admin:** Reputation admin «Закон» tab (settings + 5 levels; read-only without `reputation:settings`); the character admin law panel (wanted numbers, encounter/jail, crimes, log, release / clear wanted with a mandatory reason, only with `reputation:manage`); EditRegionForm «Тюрьма края» select. No commits/pushes/`git add`. | Frontend Developer | DONE | `Admin/ReputationPage/*` (+ `LawSettingsTab.tsx`), `Admin/CharactersPage/tabs/ReputationTab.tsx` (+ `LawPanel.tsx`), `AdminLocationsPage/EditForms/EditRegionForm/EditRegionForm.tsx`, `src/api/law.ts` (admin part) | 2, 4 | A moderator sees the law panel and can release/clear but not edit settings; the reason is required; tsc + build pass. |
| 9 | **QA character-service:** `law_core` unit tests (decay without fraction loss, levels, options matrix incl. outlaw/no-jail/flee used, chance clamp, extension cap, bail price); `register_crime` (idempotent key, bandit/positive → nothing, clamp, heavy floor, crime row status); npc-status guard KO (conditional, repeat no-op, rep + wanted once, NPC stays alive) and a non-guard kill; `evaluate_entry` (no guard / KO'd guard / dead guard / wanted 0 non-outlaw → none; outlaw with 0 wanted → encounter; teleport hook; update_location 409 when locked); choices: fine (ledger op, tax, insufficient 400, wanted 0), surrender (move side effects mocked, jailed_until, wanted cleared, term), flee success/failure→fight (RNG mocked), fight (battle HTTP mocked, busy guard 409, guard_gone, 502 revert), battle-result (won/lost/lost-without-jail forced fine/aborted, idempotent); escape (cooldown 409, fail extends + cap, success heavy wanted, double click); bail self + banker (ownership, banker at payer location, locked payer 409, one bail per term, treasury of the jail region); prisoners list (LIKE escape, page cap); staff release/clear (RBAC 403 for editor/user, reason required, request_id idempotent); settings validation; law_pass (timeout auto-surrender / auto-fine, lost callback polling, served notifications, guard heal, throttle); private access 403/404, no raw wanted numbers in player payloads; SQL-injection strings in `q`/reason. | QA Test | DONE | `character-service/app/tests/test_law_*.py` | 1, 2, 3 | All new tests pass in the container together with the existing suite. |
| 10 | **QA locations / battle / inventory / econ:** locations: the jail posting exception (same location ok, another → 409, encounter lock → 409), 409 mapping from update_location, `law_encounter` pass-through, region jail-location validation, dialogue-choose lock; battle-service: internal guard endpoint (lock exemption only for the matching id, guard checks), callback payload after the NPC loop, aborted on force-finish, no callback without the tag, `/result` field, «Нападение» on a KO'd/dead NPC 409; inventory: auction routes 409 for a jailed character; all 4 `activity_lock` copies: reason priority and the unknown-column fallback; `check_econ_copies.sh`. | QA Test | DONE | `locations-service/app/tests/test_law_*.py`, `battle-service/app/tests/test_law_guard_battle.py`, `inventory-service/app/tests/test_law_lock.py` | 3, 4, 5, 6 | All pass in their containers; the econ copies check passes. |
| 11 | **Docs:** `docs/services/character-service.md` (law tables, endpoints, pass), `locations-service.md` (jail_location_id, the posting exception), `battle-service.md` (guard battle, tag, callback), `inventory-service.md` (auction locks), `docs/ARCHITECTURE.md` (tables + flows), `docs/ISSUES.md` (remove the "NPC alive not checked" / NULL-role issues if listed). No commits/pushes/`git add`. | Backend Developer | DONE | `docs/…` | 1–6 | Docs match the implemented contracts. |
| 12 | **Final review:** code vs §3; the cross-service contracts (character ↔ locations ↔ battle ↔ inventory); 4 activity_lock copies diffed; `check_econ_copies.sh`; py_compile + all test suites; tsc + build. **Live verification on localhost** (Chrome allowed): place a guard NPC, set a region jail; kill a merchant NPC via «Нападение» → wanted level in the profile and a notification; enter the guard's location → the modal; refresh → still locked and the modal reopens; fine (gold to the treasury); again → surrender → moved to jail, banner + countdown, a post in the jail works, moving/trading/auction/battle refused; escape (cooldown); bail from another character at a banker; fight → lose → jail; fight → win → guard hidden 6 h, −300 rep; an outlaw gets only surrender/fight; a region without a jail has no surrender; admin release/clear with a reason; the home scroll into a guarded location triggers nothing; zero console errors and no raw wanted numbers in player responses. | Reviewer | DONE | — | 1–11 | PASS only with automated results + live verification recorded in section 5. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-04
**Result:** PASS

#### Checks
- [x] Types match (Pydantic ↔ TS interfaces): `LawEncounterOut`, `LawJailOut`, `LawStateOut`, choice/escape/bail/prisoners, admin settings/character/release/clear match `api/law.ts` / `api/lawAdmin.ts`
- [x] API contracts consistent (backend ↔ frontend ↔ tests); cross-service: locations → `update_location` (`source`, 409 pass-through, `law_encounter`), character → `POST /battles/internal/guard`, battle → `POST /characters/internal/law/battle-result` (+ `/internal/{id}/result.law_encounter_id` polling), inventory auction locks
- [x] No stubs/TODO without tracking
- [x] `python -m py_compile` — OK (63 changed/new .py files)
- [x] `npx tsc --noEmit` — OK (frontend container; the host lacks `react-icons` in node_modules, unrelated)
- [x] `npm run build` (`vite build`) — OK
- [x] `pytest` — OK
- [x] Security checklist passed (rate limiting, input sanitization, auth, error messages)
- [x] Frontend displays all errors to user
- [x] User-facing strings in Russian

#### Code review notes
- **Decisions:** A1 seeds 2/12/24/72/168 h and 1..168 validation; A2 guard KO on «Нападение» too; A3 partial forced fine keeps the wanted; A4 the extension never shortens the term (QA fix verified); A5 heavy floor 600 after an escape; A6 the home scroll is not evaluated but is lock-blocked; A7 flee → moved back to `from_location_id` + 1 h per-location cooldown (the system move skips evaluation); A8 live countdowns via `formatRemaining` / `useCountdownTo` / `RemainingText` and relative «— осталось …» lock texts. All match.
- **activity_lock ×4:** the shared part (lines 1–133) is byte-identical in character/locations/battle/inventory; locations == battle; inventory differs only in sync vs async. Priority jail > law_encounter > unconscious > dungeon > asleep > reading; the unknown-column fallback is present.
- **Transactions:** fines and bail go only through `econ_ledger.post_operation` with deterministic keys (`law_fine:{enc}`, `law_fine_forced:{enc}`, `law_bail:{term}`); no HTTP inside a money transaction; `send_to_jail` rolls back before `_prepare_move` and re-locks the rows afterwards; `_fight` commits `fighting` before calling battle-service and reverts on failure; `update_location` locks the row and creates the encounter in the same commit as the move.
- **Security:** player reads are private (`require_private_access`); choices, escape and self-bail are owner-only; bail checks payer ownership, a banker at the payer's location and an unlocked payer; RBAC `reputation:read/manage/settings`; reason 3..500; LIKE escaped (live: `q="Аш%_"` → 0 rows); parameterised SQL only; no raw wanted numbers in player payloads (live). Migrations: 039 FKs indexed (leftmost), revision ids ≤ 32; 055 FK SET NULL + own index; 009 tag column + index.
- **Fixed by the reviewer:** `Admin/CharactersPage/tabs/LawPanel.tsx` had a local `formatRemaining` + `useNow` copy → now uses the shared `RemainingText` (expiry/term «истекло», next escape «через …» / «можно сейчас»). tsc + build re-run OK; verified live.
- **Minor, non-blocking (follow-up):**
  1. `law_flows.send_to_jail` accepts `ENC_OPEN` (pending **and** fighting) after re-locking, so a scheduler auto-resolve racing a player's «драться» exactly at the 24 h expiry could jail a character whose fight is starting (the battle create then answers 409). Narrow window; consider passing an expected status (`pending`) from `auto_resolve`.
  2. A guard KO is journaled by the FEAT-197 reputation log as «Убийство жителя / Убит NPC «…»» — wording only (the guard stays alive).
  3. `clear-wanted` with an explicit `region_id` answers «Розыск снят» even when the wanted was already 0 (cosmetic).
  4. The bank «Залог» tab could not be opened live: the banker opens only after a «Диалог с НПС» post (existing gate). The bail-by-another-character contract was verified through the same API the tab calls.
- **Pre-existing issues noted (added to `docs/ISSUES.md`, MEDIUM):** «Нападение» on a revived NPC with `current_health = 0` creates a battle that cannot end («Нет живых целей»; the 3D view shows «Вы выиграли» at once); the admin character card opened by a direct URL shows «Персонаж не найден» (it looks up page 1 of the list).

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (frontend container)
- [x] `npm run build` — PASS (frontend container, `vite build`)
- [x] `py_compile` — PASS (63 files)
- [x] `pytest` — PASS: character-service 7917 passed / 1 skipped; locations-service 2612 passed / 3 skipped (`--asyncio-mode=auto`); battle-service 1840 passed / 10 skipped (`--asyncio-mode=auto`); inventory-service 2333 passed / 1 skipped; user-service 771 passed / 5 skipped; dungeon-service `test_econ_contract.py` + `test_feat175_entry.py` 453 passed (junit, exit 0)
- [x] `sh scripts/check_econ_copies.sh` — PASS («All shared copies are identical»)
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome on http://localhost + in-page fetch) — PASS

#### Live Verification Results
Test data: guard «Фриц Шталь» (#62) moved between Мэттанхейм locations, a temporary banker (#60), region 9 jail = «Пшеничное Море» (#199) set through the admin EditRegionForm (a location of another region → 400 «Локация тюрьмы должна находиться в этом крае»). Character Ашари (#763), payer Аэлис (#761). **All local data was restored afterwards** from a full `mysqldump` taken before the run; test battle logs/snapshots were removed from Mongo and the battle keys from Redis.
- «Нападение» on the merchant Петя (battle 327) → crime `npc_kill` 150, «Нарушитель» in the profile «Розыск» block (no number, «спадает со временем»), notification «Вас разыскивают в крае «Мэттанхейм»: Нарушитель».
- move_and_post into the guard location → response `law_encounter` (no `wanted_value`); reload → banner «Стража ждёт вашего решения» + the modal reopens with a live auto-surrender countdown; a quick move while stopped → 409 «Персонаж остановлен стражей — …».
- Fine → 150 charged, region treasury +135, country +15, wanted 0, lock cleared.
- Again (quick_move) → surrender (with confirmation) → moved to the jail and redirected; JailBanner with a live countdown, bail price and escape chance; a post in the jail (move_and_post to the same location and `POST /posts/`) → 200; moving / quick move / auction bid / buyout / battle create → 409 «Персонаж в тюрьме — осталось 12 ч».
- Escape (16,3 %) failed → «срок увеличен, осталось 18 ч», cooldown countdown «Побег — через 05:59:59».
- Bail by Аэлис at the banker → 200 (300 gold); the same request_id again → the same answer; a new request → 409 «Залог уже внесён»; a non-banker NPC → 404 «Банкир не найден»; the prisoners search works.
- Flee (chance forced to 100 % via admin settings, then restored) → «вернулись в «Пшеничное Море»» (origin); re-entering that guard location within 1 h → no encounter (A7 cooldown).
- Fight → won (battle 328) → guard `unconscious_until` +6 h, still alive, hidden from `/npcs/by_location`; «Нападение» on it → 409 «Этот персонаж сейчас недоступен для боя»; reputation −300 (→ «Вне закона»); wanted 450 → 600 (heavy floor); encounter `won`; «Вернуться на страницу локации» → the current location.
- Outlaw with wanted 0 → options only surrender/fight (level «Преступник»); region jail removed → options only fight, surrender → 409 «В этом крае больше нет тюрьмы»; fine for an outlaw → 400.
- Admin «Закон» tab (settings + 5 levels) renders; the character law panel shows wanted numbers and the jail block with a live countdown; «Освободить» with a reason → released + notification; clear-wanted with a 2-char reason → 422, with a reason → 200.
- Self-bail from JailBanner at 360 px (iframe) → 800 charged, free; GuardEncounterModal and JailBanner fit 360 px.
- House buff (profile) shows a live «— осталось 1 д 01:59:45» countdown.
- Console errors: none on the location, profile, battle and admin pages.
- Not run live: fight → lose → jail (the test character one-shots the guard); covered by `test_law_choices.py` / battle callback tests.

---

## 6. Logging (filled by all agents — in Russian)

Running log of progress updates. Each agent writes brief Russian entries here.

```
[LOG] 2026-11-04 — PM: фича создана, решения пользователя по этапу 2а зафиксированы; запускаю анализ
[LOG] 2026-11-04 — Codebase Analyst: анализ завершён (раздел 2): точка преступления — update_npc_status/apply_npc_kill, тюрьма ложится на activity_lock, найдено 8 путей перемещения, шаблон боя — internal dungeon battle; 10 вопросов к пользователю
[LOG] 2026-11-04 — Architect: спроектировано (раздел 3, 4): розыск по краю с ленивым спадом и 5 ступенями тяжести, событие-преступление (точка расширения для 2б), встреча со стражей как блокировка в той же транзакции, что и вход, бой через internal guard battle с колбэком и опросом, тюрьма через activity_lock, залог/побег/штрафы через казну; 12 задач, ~20 API-контрактов; 7 открытых бизнес-вопросов с ответами по умолчанию
[LOG] 2026-11-04 — Backend Developer: задача 3 готова — law_fine/law_bail добавлены в econ_core, 4 копии идентичны (check_econ_copies.sh ok), econ-тесты зелёные (dungeon 454, character, locations)
[LOG] 2026-11-04 — Backend Developer: задача 4 готова — миграция locations 055_region_jail_location (FK SET NULL + индекс, up/down на MySQL ок), jail_location_id в моделях/схемах с проверкой «локация этого края» (400), посты в тюрьме только в текущей локации, 409 из update_location пробрасывается, law_encounter в ответах move/quick_move, блокировка в выборе диалога (необязательный character_id); тесты locations 2486 ок
[LOG] 2026-11-04 — Backend Developer: задача 5 готова — миграция battle 009_battle_law_encounter (up/down ок), POST /battles/internal/guard, колбэк закона после цикла смерти НПС и aborted при принудительном завершении, law_encounter_id в /internal/{id}/result, «Нападение» на мёртвого/оглушённого НПС → 409; живой прогон: бой создан, колбэк дошёл до character-service; тесты battle 1710 ок
[LOG] 2026-11-04 — Backend Developer: задача 6 готова — копия activity_lock (jail/law_encounter + откат на старый SELECT без колонок), проверка блокировки в 5 записывающих маршрутах аукциона; тесты inventory 2232 ок
[LOG] 2026-11-04 — Backend Developer: начал задачи 1–2 (character-service: закон)
[LOG] 2026-11-04 — Backend Developer: задача 1 готова — миграция 039_law (7 таблиц: character_wanted, law_settings, law_levels, law_crimes, law_encounters, law_jail_terms, law_log + 3 колонки characters; сиды сроков 2/12/24/72/168 ч; up/down/up на MySQL ок), модели, law_core.py, каноничный activity_lock.py (jail/law_encounter, общая часть байт-в-байт как у копий), law_crud.py (розыск, register_crime, нокаут стражника, evaluate_entry), хуки в update_npc_status / update_location (блокировка строки, 409) / execute_teleport, список NPC без нокаутированных + фикс NULL-роли
[LOG] 2026-11-04 — Backend Developer: задача 2 готова — law_api.py (все контракты §3.6), law_flows.py (выбор, тюрьма через _prepare_move + apply_admin_move(commit=False), колбэк боя, авторешение), law_pass.py в econ_scheduler до переключателя тика, law_notify.py, battle_client.py, BATTLE_SERVICE_URL в config; полный набор тестов character-service зелёный
[LOG] 2026-11-04 — Backend Developer: отклонения: удачное бегство от стражи → возврат в from_location_id (A7) + кулдаун 1 ч на пару персонаж×локация (колонки law_encounters.from_location_id/cooldown_until, кулдаун — константа law_core.FLEE_GUARD_COOLDOWN, не настройка); ключи идемпотентности игрока включают request_id (law:choice:{enc}:{request_id}, law:escape:{char}:{request_id}, law:bail:{char}:{request_id}) — иначе повторный выбор после «бежать не удалось»/отката боя был бы no-op; новый модуль law_flows.py; в два старых теста activity_lock добавлен ключ law_encounter_id (аддитивное поле контракта)
[LOG] 2026-11-04 — Frontend Developer: задача 8 готова — api/lawAdmin.ts (отдельный клиент админки); вкладка «Закон» на странице «Репутация» (LawSettingsTab: розыск/стража/тюрьма + 5 ступеней с названием, порогом, штрафом, сроком 1–168 ч; без reputation:settings — только просмотр); LawPanel во вкладке «Репутация» карточки персонажа (розыск по краям с числами, текущая встреча и тюрьма с живым обратным отсчётом, преступления, журнал; «Снять розыск» (край или все) и «Освободить» с обязательной причиной и новым request_id на каждую отправку, только с reputation:manage); «Тюрьма края» в EditRegionForm через EntityPicker (kind location), ошибки сохранения региона теперь показывают detail бэкенда (400 «локация другого края»). Обратный отсчёт в LawPanel — локальный (formatRemaining/useNow внутри файла): общий хук от задачи 7 ещё не появился, унифицировать на ревью. tsc и build в контейнере проходят
[LOG] 2026-11-04 — QA Test: задача 9 готова — 7 файлов test_law_* + общий мир tests/law_world.py (189 тестов: ядро/миграция/сиды 2-12-24-72-168, преступления и нокаут стражника, вход и 409, телепорт, выбор штраф/сдаться/бежать/драться, итог боя, побег/залог/узники, стафф и RBAC, проход планировщика, A7, A8, безопасность); полный набор character-service: 7913 passed, 1 skipped, 1 xfailed. Найден баг: law_core.extended_until при max_remaining_jail_hours меньше остатка срока СОКРАЩАЕТ срок после неудачного побега (зафиксирован xfail-тестом)
[LOG] 2026-11-04 — Backend Developer: задача 11 готова — документация обновлена по коду: character-service.md (таблицы 039_law, раздел «Law»: розыск, преступления, нокаут стражника, встреча, выбор, тюрьма/побег/залог, API игрока/админа/internal, проход планировщика, уведомления, деньги; update_location / npc-status / телепорт; новые причины блокировки и относительное «осталось …»), locations-service.md (055, посты в тюрьме, проброс 409, law_encounter, character_id в выборе диалога), battle-service.md (009, /internal/guard, колбэк, /result, отказ по мёртвому/оглушённому NPC), inventory-service.md (блокировка аукциона), ARCHITECTURE.md (таблицы, связи, поток); в ISSUES.md закрыт остаток про NULL-роль в /npcs/by_location; записи «сервер не проверяет, жив ли NPC» в ISSUES.md не было
[LOG] 2026-11-04 — Frontend Developer: задача 7 готова — api/law.ts (игрок), utils/formatRemaining.ts + useCountdownTo в hooks/useCountdown.ts + общий RemainingText (живые отсчёты A8: тюрьма, кулдаун побега, авто-сдача, без сознания, домашние баффы); useActivityLock: причины jail/law_encounter; JailBanner и «Стража ждёт вашего решения» + GuardEncounterModal в общей плашке блокировок (окно открывается снова при смене страницы/фокусе, скрыто на странице боя); посты в тюремной локации разрешены; move/quick-move/телепорт с law_encounter обновляют профиль → окно; «вернуться в локацию» после боя — текущая локация из свежего /users/me; блок «Розыск» в профиле; вкладка «Залог» в банке; NpcDialogueModal шлёт character_id. tsc и build в контейнере ок; живую проверку в Chrome провести не удалось (вкладка расширения не отвечала)
[LOG] 2026-11-04 — QA Test: задача 10 готова — тесты: locations test_law_locations.py (исключение для постов в тюрьме, 409 из update_location, law_encounter в move/quick_move, тюрьма края только из этого края, диалог с character_id, сверка 4 копий activity_lock), battle test_law_guard_battle.py (internal/guard, колбэк после цикла смерти NPC, aborted при force-finish, /result, «Нападение» на мёртвого/оглушённого NPC), inventory test_law_lock.py (5 маршрутов аукциона, откат без колонок на SQLite), character test_activity_lock_law_priority.py, law-кейсы в econ_contract_cases (4 копии); полные наборы: locations 2612, battle 1840, inventory 2333, dungeon econ+feat175 476 — зелёные, check_econ_copies ок; замечание: POST /battles/mob-attack не проверяет, что цель-NPC жива и не оглушена (можно напасть на оглушённого стражника)
[LOG] 2026-11-04 — Backend Developer: исправлены замечания QA — неудачный побег больше никогда не сокращает срок (max(текущий срок, now + min(остаток × (1+%), предел)), xfail снят); повтор request_id после отката боя (502) отвечает «Стража ждёт вашего решения», а «Бежать не удалось» — только если исходным выбором было бегство; A8: все тексты игрока в law-модуле (кулдаун побега, неудачный побег, сдача/авто-сдача, уведомления о встрече и заключении) — относительные сроки через format_remaining, без «до DD.MM HH:MM МСК»; internal npc-status → alive снимает нокаут (unconscious_until = NULL). Добавлены тесты, полный набор character-service зелёный
[LOG] 2026-11-04 — Reviewer: начал проверку
[LOG] 2026-11-04 — Reviewer: автопроверки зелёные (character 7917, locations 2612, battle 1840, inventory 2333, user 771, dungeon econ+feat175 453, check_econ_copies, py_compile, tsc, build); общая часть 4 копий activity_lock идентична
[LOG] 2026-11-04 — Reviewer: в LawPanel локальный обратный отсчёт заменён на общий RemainingText
[LOG] 2026-11-04 — Reviewer: живая проверка на localhost пройдена (розыск, стража, штраф, сдача, тюрьма, посты в тюрьме, отказы, побег, залог, бегство с возвратом, бой со стражником, вне закона, край без тюрьмы, админка, баффы дома); локальные данные восстановлены из дампа
[LOG] 2026-11-04 — Reviewer: обнаружено 2 сторонних бага, добавлены в ISSUES.md (бой с воскрешённым NPC без здоровья; карточка персонажа в админке по прямой ссылке)
[LOG] 2026-11-04 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

**Статус: DONE (2026-11-04), ревью PASS.**

### Что сделано
- Розыск по краям (0–1000, 5 уровней от «Подозреваемого» до «Врага края»), спадает 50/день; преступление (убийство мирного NPC) пишется отдельной записью — точка расширения для этапа 2б (свидетели).
- Стража — NPC с ролью «стражник»: встречает разыскиваемого (и «Вне закона») при входе в локацию и после телепорта у мастера; свиток домой — законный способ скрыться. Выбор: штраф / сдаться / бежать / драться («Вне закона» — сдаться/драться; без тюрьмы в крае — без «сдаться»). Встреча фиксируется на сервере — обновлением страницы не уйти; через 24 ч без выбора — авто-сдача (или принудительный штраф).
- Удачный побег от стражи — назад, откуда пришёл, и стража этой локации час не трогает. Победа над стражником — он выбывает на 6 ч (не умирает), −300 репутации, тяжёлый розыск.
- Тюрьма края (назначает админ): срок 2 ч / 12 ч / 24 ч / 72 ч / 7 дней по уровню; в тюрьме можно только писать посты в тюремной локации (перемещение, торговля, аукцион, бои, данжи, задания закрыты). Залог (штраф ×2) — сам или любой игрок у любого банкира; побег раз в 6 ч (провал +50 % срока, никогда не сокращает).
- Штрафы и залог — в казну края (10 % стране). Стафф с `reputation:manage` освобождает и снимает розыск с причиной; настройки — только админ.
- Живые таймеры обратного отсчёта: тюрьма, побег, встреча со стражей, «без сознания», бафы от дома; серверные отказы — «… — осталось 3 д 4 ч».
- Попутно: атака на мёртвого/выбывшего NPC запрещена везде; NPC без роли видны в локации.

### Что изменилось от первоначального плана
- Максимальный срок 7 дней вместо 48 ч (решение пользователя); бегство возвращает в прошлую локацию; везде обратный отсчёт вместо «до HH:MM».

### Оставшиеся риски / follow-up задачи
- Узкое окно: авто-решение через 24 ч одновременно с кликом «драться».
- Выбывший стражник пишется в журнал репутации как «Убит NPC» (только формулировка).
- «Розыск снят» показывается и при нулевом розыске.
- Поражение в бою со стражей → тюрьма проверено тестами, вживую не прогонялось; вкладка «Залог» у банкира проверена через API.
- Деплой: миграции character 039, locations 055, battle 009 применятся сами; нужно назначить тюрьмы краям и расставить стражников.
