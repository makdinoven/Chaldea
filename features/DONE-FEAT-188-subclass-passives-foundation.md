# FEAT-188: Пассивки подклассов — фундамент (подкласс персонажа + загрузка пассивки в бой) и первая пассивка «Ярость» Берсерка

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-10-31 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-188-slug.md` → `DONE-FEAT-188-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Первые два шага плана из `docs/SUBCLASS-PASSIVES.md` (там же — согласованный с
пользователем дизайн всех 21 пассивки и цифры):

1. **Подкласс персонажа как общий факт.** Подкласс уже фактически фиксируется:
   это выбранный узел `subclass_choice` в `character_tree_progress` (skills-service),
   его `subclass_key`. inventory-service сейчас читает это сырым SQL по чужой таблице
   (`equipment_rules.load_character_scope`). Нужен единый, официальный способ узнать
   подкласс персонажа для других сервисов.
2. **Загрузка пассивки в бой.** На старте боя (и при вступлении в идущий бой) для
   каждого участника-персонажа определяется подкласс → его пассивка, и она кладётся
   в состояние боя. Реестр пассивок (ключ, название, описание, цифры-константы) —
   в одном месте.
3. **Первая живая пассивка — «Ярость» Берсерка** (доказательство, что механизм
   работает): **+4% урона за каждые 10% потерянного HP** (≈ +36% у края).
   Вампиризм ниже 25% HP — **НЕ в этой фиче** (нужна новая механика вампиризма).
   Остальные 20 пассивок только регистрируются (описание есть, эффекта нет).
4. **Видимость пассивки для игрока — везде:** в бою (значок у участника с
   подсказкой), в профиле персонажа, в дереве навыков (на подклассе).

### Бизнес-правила
- Одна пассивка на подкласс; без ступеней по уровню.
- Подкласс = выбранный узел `subclass_choice`. Игрок сменить подкласс сам не может
  (обычный сброс дерева подкласс сохраняет); снимает только полный сброс админом.
  Так и задумано.
- Персонаж без подкласса (ещё не дошёл / моб) — без пассивки, бой работает как раньше.
- Пассивка фиксируется на старте боя (как инициатива) и в течение боя не меняется.
- «Ярость»: бонус считается от текущего % потерянного HP в момент удара, шагами по
  10% (потеряно 0–9% → 0, 10–19% → +4%, ..., 90–99% → +36%). Бонус — к проценту
  урона, как прочие процентные баффы.
- Цифры всех пассивок — константы в одном месте (тюнинг правкой одной строки).
- Пассивки никогда не увеличивают длительность оглушения/паралича (на будущее).

### UX / Пользовательский сценарий
1. Игрок с выбранным подклассом видит его пассивку (название + описание) в профиле
   и в дереве навыков на подклассе.
2. В бою у участника с пассивкой — значок; при наведении/тапе — название и описание.
3. Берсерк, теряя HP, бьёт сильнее; в логе боя видно, что урон усилен пассивкой.

### Edge Cases
- Бой уже шёл до деплоя → у участников нет пассивки в состоянии; бой не должен падать.
- skills-service недоступен на старте боя → бой стартует без пассивок (не падает), с логом ошибки.
- Подкласс есть, но пассивка для него ещё «без эффекта» → показываем описание, эффекта нет.
- Мобы — без пассивок.
- Вступление в идущий бой — новичку тоже грузится пассивка.

### Вопросы к пользователю
- [x] Смена подкласса только через полный сброс админом — так и задумано? → Да.
- [x] Первая живая пассивка → Берсерк («Ярость», без вампиризма).
- [x] Где показывать пассивку → Везде (бой, профиль, дерево навыков).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| skills-service | passive registry (or passive fields on `SubclassDef`), new internal "subclass of character(s)" route, optionally passive on public `GET /skills/subclasses` | `app/subclasses.py`, `app/main.py`, `app/schemas.py` (`SubclassRead` :268), `app/crud.py` |
| battle-service | load subclass/passive at battle start + on join, store per participant, Berserk damage hook, log field, expose to client | `app/main.py`, `app/skills_client.py`, `app/redis_state.py`, (new constants module or reuse of the skills registry copy) |
| inventory-service | optional: switch `load_character_scope` raw SQL to the official source (not required for this feature) | `app/equipment_rules.py:124-145` |
| frontend | badge+tooltip in battle (3D card, 2D fallback, maybe turn queue), passive in profile, passive on subclass in skill tree, log line | see Frontend table below |
| nginx | none — `/skills/internal/` already blocked (`nginx.conf:343`, `nginx.prod.conf:360`) | — |
| DB | none needed — subclass is derivable (see below) | — |

### 1. Battle participant state — all entry points
Per-participant data is gathered by **one function** `build_participant_info(char_id, participant_id)` (`battle-service/app/main.py:312-359`): sequential HTTP calls `fetch_full_attributes` (char-attrs `/attributes/internal/{id}`, **fatal** → 500), `character_skills` (skills-service, soft-fail → `[]`), `get_fast_slots`, `get_character_profile`, `get_equipment_durability` (all soft-fail with `logger.warning`). Its return dict is the **snapshot** entry (name, avatar, attributes, skills, fast_slots, equipment_durability). `class_id` is NOT fetched at start — it is read per action via `fetch_character_class_id` (raw SQL on `characters`, `main.py:170`, called at `main.py:2626`).

Then a `participants_payload` list is built from the snapshot and passed to `init_battle_state` (`redis_state.py:162-235`), which whitelists keys into `state["participants"][pid]` (hp, mana, energy, stamina, max_*, fast_slots, cooldowns, totals, equipment_durability). **A new field must be added in the payload AND in the dict literal of `init_battle_state` (redis_state.py:215-232)** — it is not copied through automatically.

| Entry point | Route / function | Path to state |
|---|---|---|
| Generic create (incl. admin-created / tests) | `POST /battles/` `create_battle_endpoint` main.py:855 | `_assemble_battle` main.py:769 |
| Mob attack | `POST /battles/mob-attack` main.py:976 | `_assemble_battle` (call :1002) |
| Party mob attack | `POST /battles/party/mob-attack` main.py:1013 | `_assemble_battle` (:1102) |
| Pack attack / party pack | main.py:1135 / :1188 | `_assemble_battle` (:1177 / :1275) |
| Admin-approved forced PvP request | `POST /battles/admin/pvp-requests/{id}/approve` main.py:1397 | `_assemble_battle` (:1417) |
| Dungeon (ambush/rooms/boss, from dungeon-service) | `POST /battles/internal/dungeon` main.py:1443 (internal token) | `_assemble_battle` (:1486) |
| PvP party start | `POST /battles/pvp/party/{id}/start` main.py:6546 | `_assemble_battle` (:6575) |
| PvP invitation accepted (duel / party-vs-party) | `respond_to_pvp_invitation` main.py:4021 | **inline copy** of payload build + `init_battle_state` (main.py:4130-4171) |
| PvP attack | `POST /battles/pvp/attack` main.py:4324 | **inline copy** (main.py:4429-4470) |
| Join in progress | `admin_approve_join_request` main.py:5127 | `build_participant_info` (:5195) + **hand-written participant dict** inserted into loaded state (:5198-5218), `turn_order.append`, snapshot appended in Mongo + Redis cache (:5221-5239) |

So: 1 shared builder (`_assemble_battle`) + 2 inline duplicates + 1 join path = **4 places** that construct participant state; `build_participant_info` is the single common point for all of them (snapshot level). The only "join" path is admin join-request approval (only place creating `BattleParticipant` outside `crud.create_battle`).

Mob/NPC detection: `characters.is_npc` (raw SQL, e.g. main.py:829 in `_assemble_battle`, :5243 in join). `build_participant_info` does not know `is_npc`. autobattle-service gets NPCs registered after state init.

**Old in-progress states:** every reader of optional per-participant keys uses `.get(...)` with defaults — precedent `dropped_out` (FEAT-163), `weapon_coating` (FEAT-168, comment "в боях, начатых до деплоя, ключа нет"), `max_hp` `.get("max_hp", 0)` in runtime builders. Same pattern applies to a passive key; a missing key ⇒ "no passive". Snapshots (`battle:{id}:snapshot`, Redis TTL 24h + Mongo `battle_snapshots`) are also old-shape for pre-deploy battles. State TTL 48h (`redis_state.py:27`).

Runtime responses are built by **5 hand-written dict builders** that whitelist participant keys: `get_state_internal` main.py:1589, `get_state` :1662, `spectate_battle` :1750 (≈:1835), `admin_get_battle_state` :4679 (≈:4724), `_build_runtime` :5637 (WS). The **snapshot** list is returned unmodified in all of them (`SpectateStateResponse.snapshot`/`AdminBattleStateResponse.snapshot` are `Optional[list]`, schemas.py:247/:301), so a key added to `build_participant_info`'s return dict reaches the client with no builder edits; a key added only to Redis state needs edits in all 5 builders.

### 2. Damage hook, HP storage, battle log
- Skill attack path (`_make_action_core`, main.py:2530): `attacker_buff_modifiers = aggregate_modifiers(active_effects[attacker])` → `percent_damage_buffs = build_percent_damage_buffs(...)` at **main.py:3345-3348**, once per attack, then `compute_damage_with_rolls(... percent_buffs=percent_damage_buffs ...)` per damage entry/AoE target at **main.py:3427-3441**.
- Item damage path (scrolls/flasks): `_item_pct_damage = build_percent_damage_buffs(_item_mods)` at **main.py:3112**, used at :3162-3174.
- `build_percent_damage_buffs` (buffs.py:455-466) maps `percent_damage` → key `"all"`, `percent_damage_<type>` → `<type>`.
- In `compute_damage_with_rolls` (battle_engine.py:117-210): `buff_pct = percent_buffs["all"] + percent_buffs[dmg_type]`; `raw *= 1 + buff_pct/100` **before** crit and resist. Log dict contains `damage_type, base, entry, buff_pct, after_buffs, dodged, hit_chance_failed, critical, crit_mul, resist_pct, final`.
- Cleanest hook: right after main.py:3348 (and :3112 for items) add the passive's percent to `percent_damage_buffs["all"]` — attacker HP does not change within one attack's loop, so evaluating once per attack == "at hit time". The bonus then appears inside the existing `buff_pct` automatically; to show the passive's own contribution a separate key is needed (the log dict is spread into the event via `**log`, main.py:3455-3458 / :3186-3190, so an extra key passed through is persisted).
- HP storage: `state["participants"][pid]["hp"]` (float; damage subtracts float `dealt`, main.py:3446, can go ≤0) and `["max_hp"]` (set at start from `attributes.max_health`, static for the battle). Pre-FEAT states may lack `max_hp` (builders default 0) ⇒ guard divide-by-zero; snapshot `attributes.max_health` is an alternative source.
- Periodic DoT ticks (`buffs.tick_periodic_effects`) do not go through `compute_damage_with_rolls` — unaffected.
- Battle log: `turn_events` list (main.py:2631), event `{"event": "damage", "source", "target", **log}`; persisted via Celery `save_log.delay(battle_id, turn_number, turn_events)` (main.py:2498, `tasks.py` → Mongo `battle_logs`) and returned in the action response. Frontend renders them in `useBattleBar.tsx::formatBattleEvent` (damage branch :673-718; `BattleEvent` type :120-150 already has `buff_pct`, `after_buffs`).

### 3. battle-service → skills-service today
- `battle-service/app/skills_client.py`: `get_resolved_skill` (`GET /skills/{id}/resolved`), `character_has_skill` and `character_skills` (`GET /skills/characters/{id}/skills`). Auth: **`Authorization: Bearer <INTERNAL_SERVICE_TOKEN>`** (`_service_headers`, :37), accepted by skills-service `allow_jwt_or_service_token` (auth_http.py:78). Token read at import time. No timeout set on these httpx clients (default 5s).
- Internal-route pattern in skills-service (FEAT-169/170/171): `POST /skills/internal/assign_multiple` main.py:635 with `Depends(verify_internal_token)` (auth_http.py:104-119: header **`X-Internal-Token`**, fail-closed 503 on empty env, 401 on mismatch; explicitly NOT accepted in Bearer position and vice versa — tested in `tests/test_internal_auth.py:309-347`). battle-service sends `X-Internal-Token` via `_internal_token_headers()` (main.py:73, battle_engine.py:26, inventory_client.py:10) for every other service. A new skills internal GET would therefore use `X-Internal-Token`, i.e. a different header than existing `skills_client` functions (the file already mixes both — `get_item` :136 uses `X-Internal-Token`).
- Route ordering caveat: router prefix `/skills`; public `GET /{skill_id}` (main.py:500) and `GET /{skill_id}/resolved` (:514) are generic. `/skills/subclasses` is registered before them on purpose (:414-415). A new GET like `/skills/internal/...` with ≥3 segments won't collide with `/{skill_id}/resolved` unless its 2nd segment is literally `resolved`; a 2-segment path (`/skills/internal`) would collide with `/{skill_id}` ⇒ register internal GETs before the generic ones.
- Subclass lookup query (proven): `character_tree_progress ctp JOIN tree_nodes tn ON tn.id = ctp.node_id WHERE ctp.character_id=:cid AND tn.node_type='subclass_choice' AND tn.subclass_key IS NOT NULL ORDER BY ctp.id DESC LIMIT 1` (inventory `equipment_rules.py:131-140`). Models: `TreeNode.subclass_key` (skills models.py:237), `CharacterTreeProgress` (:286, unique `(character_id,node_id)`). Registry lookup `subclasses.get_subclass(key)` (subclasses.py:182). Nothing in skills-service crud returns "character → subclass" today. A batch form (`character_ids=1,2,3`) would let `_assemble_battle` make one call per battle instead of one per participant; `_parse_bulk_ids` (main.py:430) is an existing bulk-id parser pattern (`/skills/bulk`).
- No shared code between services (each has its own image) ⇒ passive numbers needed by battle-service must either live in battle-service or be shipped in the HTTP response.

### 4. Who reads the subclass today
- inventory-service: raw SQL `equipment_rules.load_character_scope` (:124-145) → `rules_for_character`; exposed to the client as `subclass_key` in `GET /inventory/{character_id}/equipment-rules` (inventory main.py:921, schema `CharacterEquipmentRules` schemas.py:1177). Called by skills-service after `choose_node`/full reset (`revalidate-equipment`, skills main.py:801-815, :996-999, :1174).
- Frontend: `profileSlice.fetchEquipmentRules` (profileSlice.ts:546, dispatched :882) already holds `equipmentRules.subclass_key` (`utils/equipmentRules.ts:11`) on the profile page; skill tree derives the chosen subclass from `classTree.nodes` + progress (`SkillTreePage.tsx:319-325`); public registry via `api/subclasses.ts` (`GET /skills/subclasses`, used by `CreateCharacterPage/StepPath/SubclassPreview.tsx`).
- character-service / user-service / battle-service / autobattle / dungeon: **no reference to subclass** (grep). `GET /characters/{id}/profile` (used by battle `character_client.py`) has no subclass.
- Player tree reset keeps `subclass_choice` rows (skills main.py:1077-1088); admin `reset_full` deletes them (:1121-1175). Confirmed.

### 5. Frontend files
| Area | File | Lang | Styles | Note |
|---|---|---|---|---|
| Battle page container (maps snapshot → `CharacterData`/`ArenaFighter`) | `components/pages/BattlePage/BattlePage.tsx` (1196 lines; `getResources` :271, `processState` :297, `arenaFighters` :746-789) | TSX | Tailwind | `ParticipantSnapshot`/`CharacterData` types in `battleTypes.ts` (TS) |
| 3D participant card (primary mode) | `Arena3D/FighterCard.tsx` (DOM via drei Html), type `ArenaFighter` in `Arena3D/arenaTypes.ts:130` | TSX | Tailwind | badge/tooltip goes here |
| 2D fallback card (no WebGL) | `CharacterSide/CharacterSide.tsx` | TSX | Tailwind | renders `CommonComponents/PlayerCard/PlayerCard.jsx` (**JSX + SCSS** — touching it forces TS + Tailwind migration; badge can sit in CharacterSide instead) |
| 2D resources | `CharacterSide/CharacterResourcesList/CharacterResourcesList.jsx` | **JSX + SCSS** | — | avoid touching |
| Turn queue | `BattlePageBar/BattlePageBar.tsx` :78-100 → `AvatarCircle.tsx` (has `badge` prop) ; logic in `BattlePageBar/useBattleBar.tsx` (`turnQueue` :335) | TSX | Tailwind | |
| Battle log | `useBattleBar.tsx::formatBattleEvent` (damage :673-718, `BattleEvent` :120-150), shown in `BattlePageBar.tsx:278` and 3D `Arena3D/hud/Chronicle.tsx:85` | TSX | Tailwind | one change covers both modes |
| Countdown timer | `BattlePageBar/CountdownTimer/CountdownTimer.jsx` | **JSX + SCSS** | — | not relevant, don't touch |
| Profile identity header (race / class) | `ProfilePage/CharacterTab/CharacterPanel.tsx` (`className` :46, header band) ; data `redux/slices/profileSlice.ts` | TSX | Tailwind | natural place for subclass + passive |
| Skill tree | `SkillTreeView/SkillTreePage.tsx`, `NodeDetailPanel.tsx`, `useNodePage.tsx` (subclass_choice node page), `Books3D/ChapterRibbon.tsx`, `Books3D/nodePageModel.ts` | TSX/TS | Tailwind (`PlayerTreeCanvas.tsx` imports only reactflow lib CSS) | node has `subclass_key` from `FullClassTreeResponse` |
| Registry API | `api/subclasses.ts` (`Subclass` interface) | TS | — | extend if passive fields added to `SubclassRead` |
| Public user profile (others' characters) | `UserProfilePage/CharactersSection.tsx` | TSX | Tailwind | optional |

No `.jsx` must be touched if badges are added in `FighterCard.tsx`, `CharacterSide.tsx`, `AvatarCircle.tsx`.

### 6. Tests to extend
- battle-service (`app/tests/`): `test_class_damage_luck.py` (direct `compute_damage_with_rolls` unit tests), `test_buffs.py` (`build_percent_damage_buffs`/aggregate), `test_redis_state.py` (`init_battle_state` written state), `test_join_requests.py` (approve path, `test_approve_join_request` :824), `test_pvp_invitations.py`, `test_pvp_attack.py`, `test_pack_attack.py`, `test_pve_rewards.py`, `test_activity_lock.py` (these mock `build_participant_info`/`_assemble_battle`), `test_skills_client.py` (client URL/headers), `test_internal_headers.py` + `test_feat171_outgoing_internal.py` (assert the header VALUE on every outgoing internal call — a new call must be added there), `test_weapon_damage_once.py`/`test_item_usage.py` (action-core damage flows).
- **22 battle test files replace `skills_client` with a `MagicMock` in `sys.modules`** (e.g. `test_join_requests.py:58,101`). A new `skills_client` coroutine imported into `main.py` will be a plain `MagicMock` there — awaiting it raises `TypeError`; only harmless if the call site catches `Exception` (which the edge case "skills down ⇒ no passive" requires anyway), but tests should set it to `AsyncMock` explicitly.
- skills-service: `test_internal_auth.py` (401/503/header-position matrix for internal routes, aiosqlite), `test_player_tree_endpoints.py` (fixtures with a `subclass_choice` node :219/:286 and reset preserving subclass :838), `test_class_tree_endpoints.py`, `test_internal_headers.py`.

### Existing Patterns
- battle-service: async SQLAlchemy (aiomysql) + raw `text()` SQL on shared tables, Redis JSON state, Mongo snapshots/logs, Alembic present (`alembic_version_battle`). Pydantic v1.
- skills-service: async SQLAlchemy, Alembic present, hardcoded registry in `subclasses.py` (frozen dataclass), Pydantic v1 `orm_mode`.
- Soft-fail per sub-fetch in `build_participant_info` (`try/except → logger.warning → default`) is the established pattern for non-critical participant data.

### Cross-Service Dependencies
- battle-service → skills-service (existing: `/skills/{id}/resolved`, `/skills/characters/{id}/skills`; new: internal subclass lookup).
- skills-service → inventory-service `revalidate-equipment` on subclass change (unchanged).
- autobattle-service reads battle `snapshot`/`runtime` via `/battles/internal/{id}/state` (`snap_me["attributes"]["max_health"]`, `percent_damage` effects, autobattle main.py:252,292) — extra keys are harmless.
- dungeon-service creates battles via `/battles/internal/dungeon` → `_assemble_battle` (gets passives automatically if added there).

### DB Changes
- None required: subclass = derivable from `character_tree_progress` + `tree_nodes`. (Plan step 2 "`character_subclass`" in `docs/SUBCLASS-PASSIVES.md` would be a denormalized column/table — Architect's call; if added, skills-service owns it and must keep it in sync on `choose_node` and admin `reset_full`.)

### Risks
- **Four construction sites** (shared `_assemble_battle`, two inline duplicates at main.py:4130 and :4429, join at :5198) → a passive added in one place and forgotten in another silently gives no passive in duels/PvP attack/joins → Mitigation: attach passive inside `build_participant_info` (common to all 4) and/or factor the payload/state dict; test each entry point.
- **Old Redis states / snapshots** without the key → Mitigation: `.get()` everywhere, missing = no passive (precedent FEAT-163/168); guard `max_hp` 0/missing.
- **skills-service down at start** → must not 500 the battle start (attributes fetch is the only fatal one) → soft-fail with `logger.error`, as in brief.
- **Silent-failure pattern** (MEMORY: typo + swallowed error + wrong fixture schema): a wrong header (Bearer vs `X-Internal-Token`) or wrong column name would just yield "no passive" everywhere with green tests → Mitigation: header-value test in `test_internal_headers.py`, and an integration-ish test that the lookup returns the real key for a seeded `subclass_choice` node.
- **Performance**: `build_participant_info` already does 5 sequential HTTP calls per participant, participants processed sequentially (up to 10 in 5v5). +1 call each adds latency; a batch endpoint (one call per battle) avoids it, but the join path is single-character anyway.
- **Mobs/NPCs**: they normally have no tree progress → no subclass; for explicit exclusion `is_npc` must be checked (not available inside `build_participant_info` today).
- **Damage hook placement**: passive must be added in both the skill path (main.py:3348) and item path (main.py:3112) if "all damage" is intended; it also multiplies coating bonus (added to `amount` before the formula) — consistent with other % buffs.
- **Pre-existing bug found** (unrelated, added to `docs/ISSUES.md` LOW): join-request approval registers NPC in autobattle at non-existent `/autobattle/register` without token (main.py ~5250).

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Summary of decisions

| # | Question | Decision |
|---|----------|----------|
| D1 | Where does "character → subclass" live? | **Derived, no new column/table.** Source = latest `character_tree_progress` row whose `tree_nodes.node_type='subclass_choice'` and `subclass_key IS NOT NULL` (same query as inventory `equipment_rules.py:131-140`). A denormalized `character_subclass` would need to be kept in sync on `choose_node` and admin `reset_full` (two write paths, one more silent-drift risk) and buys nothing: the lookup is one indexed join (unique `(character_id,node_id)`), run once per participant per battle start. Plan step 2 of `docs/SUBCLASS-PASSIVES.md` is satisfied by an **official skills-service endpoint** instead of a column. |
| D2 | How does battle-service get it? | New internal skills-service route `GET /skills/internal/characters/{character_id}/subclass` (`X-Internal-Token`, `verify_internal_token`). Called **per participant inside `build_participant_info`** — the single function common to all 4 construction sites incl. join. |
| D3 | Batch vs per participant | **Per participant.** (a) the join path is single-character anyway; (b) a batch call would need a second code path in `_assemble_battle` *and* both inline PvP duplicates — exactly the "added in one place, forgotten in another" risk; (c) cost is one more in-cluster GET (~5–20 ms) per participant, ≤ ~0.2 s for a 5v5, once per battle — acceptable. The new call gets an explicit timeout constant (3 s) so a hanging skills-service cannot stall battle start for long. |
| D4 | What the battle carries | **Snapshot** (return dict of `build_participant_info` → Mongo `battle_snapshots` + Redis snapshot cache, already returned verbatim by all 5 runtime builders and WS) carries display data: `subclass` `{key,name}` and `passive` `{key,name,description,implemented}` (or `null`). **Redis participant state** carries only `passive_key: str|None` for engine logic. Names/descriptions come from skills-service (single source); **no edits needed in the 5 runtime builders**. |
| D5 | Where numbers live | New module `services/battle-service/app/passives.py` — passive keys + numeric constants + pure functions. Player-facing name/description in the skills-service registry (`subclasses.py`). The Berserk description quotes the numbers (4% / 10% / 36%); docstrings of both files must point at each other ("change constants → update description"). |
| D6 | Mobs | The internal endpoint returns `is_npc` (from `characters.is_npc`); battle-service drops subclass/passive when `is_npc` is true. One place, covers all 4 sites (`build_participant_info` has no DB/`is_npc` today). |
| D7 | Rage scope | Added to the attacker's `"all"` percent-damage bucket in **both** the skill path (after `main.py:3348`) and the item path (after `main.py:3112`); evaluated once per attack from current HP (attacker HP does not change inside one attack loop ⇒ equals "at hit time"). DoT ticks unaffected (no `compute_damage_with_rolls`). Also multiplies the coating bonus — consistent with other % buffs. **No lifesteal.** |
| D8 | inventory-service `load_character_scope` | **Leave as is.** Switching would make inventory call skills-service while skills-service itself is calling inventory `revalidate-equipment` right after `choose_node`/`reset_full` (circular call inside one request + commit-visibility timing), and inventory is sync (hot equipment path). Not low-risk → out of scope; recorded as LOW tech debt in `docs/ISSUES.md` (task 1). |
| D9 | "Not yet active" passives | Registry carries `implemented: bool` (true only for `berserker_rage`). UI shows every description and, for `implemented=false`, a small muted note «пока не действует в бою». Honest UX for the brief's edge case "показываем описание, эффекта нет". (PM: trivial to drop if the user objects — one boolean + one label.) |
| D10 | Berserk description | Only the live part (rage). The vampirism sentence is added when the vampirism mechanic ships — a non-working effect in the description would mislead. |
| D11 | DB / permissions / nginx / compose | None. No migration, no new permission, `/skills/internal/` already blocked in both nginx configs, `INTERNAL_SERVICE_TOKEN` already wired for both services. |

### 3.1 Passive registry (skills-service `app/subclasses.py`)

Add a frozen dataclass `PassiveDef(key: str, name: str, description: str, implemented: bool = False)` and a field `passive: PassiveDef` on `SubclassDef`. Passive keys are stable identifiers (never rename once shipped — battle-service matches on them):

| Subclass key | Passive key | Name | implemented |
|---|---|---|---|
| warrior_inquisitor | `inquisitor_heresy_seal` | Печать ереси | false |
| warrior_paladin | `paladin_sacred_vow` | Священный обет | false |
| warrior_saber | `saber_monster_hunter` | Охотник на чудовищ | false |
| warrior_guardian | `guardian_retribution` | Возмездие | false |
| warrior_gladiator | `gladiator_arena` | Арена | false |
| warrior_berserker | `berserker_rage` | Ярость | **true** |
| warrior_agent | `agent_weak_spot` | Слабое место | false |
| rogue_lancer | `lancer_pin` | Пригвоздить | false |
| rogue_mechanic | `mechanic_shrapnel` | Шрапнель | false |
| rogue_archer | `archer_first_blood` | Первая кровь | false |
| rogue_assassin | `assassin_from_shadow` | Из тени | false |
| rogue_bard | `bard_rhythm` | Ритм | false |
| rogue_trickster | `trickster_deceit` | Обман | false |
| rogue_monk | `monk_harmony` | Гармония | false |
| mage_necromancer | `necromancer_blood_price` | Плата кровью | false |
| mage_etheriad | `etheriad_spirit_whisper` | Шёпот духов | false |
| mage_salamander | `salamander_kindling` | Разгорание | false |
| mage_caster | `caster_pure_energy` | Чистая энергия | false |
| mage_sparkmage | `sparkmage_chain_lightning` | Цепная молния | false |
| mage_auromancer | `auromancer_tide` | Прилив | false |
| mage_priest | `priest_faith` | Вера | false |

Descriptions: player-facing Russian text from the "Пассивка и цифры" column of `docs/SUBCLASS-PASSIVES.md` (full sentences, numbers kept). Berserk, e.g.: «Боль превращается в ярость: +4% к урону за каждые полные 10% потерянного здоровья (до +36%).» (no vampirism — D10). Helper `get_passive_for_subclass(key) -> Optional[PassiveDef]`. Update the module docstring (passives are now modeled).

### 3.2 API contracts

#### (A) Public, extended, backward compatible — `GET /skills/subclasses[?class_id=N]`
Response `List[SubclassRead]`; existing fields unchanged (consumers `SubclassPreview.tsx`, `EquipmentRulesAdminPage.tsx` unaffected):
```python
class PassiveRead(BaseModel):          # Pydantic v1
    key: str
    name: str
    description: str
    implemented: bool
    class Config:
        orm_mode = True

class SubclassRead(BaseModel):
    key: str
    class_id: int
    name: str
    description: str
    passive: Optional[PassiveRead] = None   # always filled for registry entries
    class Config:
        orm_mode = True
```
Auth: none (public static reference, unchanged). Rate limiting: existing nginx limits.

#### (B) New internal — `GET /skills/internal/characters/{character_id}/subclass`
- Auth: `Depends(verify_internal_token)` — header **`X-Internal-Token`** only (Bearer NOT accepted; 503 on empty env, 401 on missing/mismatch). Externally blocked by nginx `/skills/internal/` (already in both configs).
- Registration: in `skills-service/app/main.py` **before** generic `GET /{skill_id}` and `/{skill_id}/resolved`, with a comment why.
- Validation: `character_id: int` path (422 on non-int); `<= 0` → 404.
- Logic: `crud.get_character_subclass_key(db, character_id) -> Optional[str]` (async ORM select): `character_tree_progress ⨝ tree_nodes WHERE ctp.character_id=:cid AND tn.node_type='subclass_choice' AND tn.subclass_key IS NOT NULL ORDER BY ctp.id DESC LIMIT 1`. Existence + NPC flag via bound `SELECT is_npc FROM characters WHERE id=:cid` (skills-service already raw-reads `characters`).
- `200` `CharacterSubclassRead`:
  ```python
  class CharacterSubclassRead(BaseModel):
      character_id: int
      is_npc: bool
      subclass_key: Optional[str] = None     # raw key from the node
      subclass_name: Optional[str] = None    # None if key unknown to registry
      passive: Optional[PassiveRead] = None  # None if no subclass / unknown key
  ```
  Example: `{"character_id": 42, "is_npc": false, "subclass_key": "warrior_berserker", "subclass_name": "Берсерк", "passive": {"key": "berserker_rage", "name": "Ярость", "description": "…", "implemented": true}}`.
  No subclass yet → `200` with `subclass_key: null, passive: null` (not 404).
- `404 {"detail": "Персонаж не найден"}` — no `characters` row. `401`/`503` — auth.
- Rate limiting: not needed (not routable via nginx).

#### (C) battle-service client — `skills_client.get_character_subclass(character_id) -> dict`
`GET {SKILLS_URL}/skills/internal/characters/{id}/subclass` with header **`{"X-Internal-Token": INTERNAL_SERVICE_TOKEN}`** via a new helper `_internal_headers()` in `skills_client.py`. **Do NOT reuse `_service_headers()`** (sends `Authorization: Bearer`, which this endpoint rejects with 401 → swallowed → "no passive" everywhere). `httpx.AsyncClient(timeout=SUBCLASS_LOOKUP_TIMEOUT_S)` (named constant, 3.0), `raise_for_status()`, return JSON. Update the file header comment (the file now uses both header styles, and why).

### 3.3 battle-service design

**New module `app/passives.py`** (pure, no I/O):
```python
PASSIVE_BERSERKER_RAGE = "berserker_rage"
RAGE_HP_STEP_PCT = 10    # one step per full 10% of max HP lost
RAGE_PCT_PER_STEP = 4    # +4% outgoing damage per step
RAGE_MAX_STEPS = 9       # cap -> +36%

def rage_bonus_pct(hp, max_hp) -> int:
    # max_hp missing / <= 0 / non-numeric -> 0; hp clamped to [0, max_hp]
    # lost_pct = (max_hp - hp) * 100 / max_hp
    # steps = min(RAGE_MAX_STEPS, floor(lost_pct / RAGE_HP_STEP_PCT + 1e-9))
    # return steps * RAGE_PCT_PER_STEP

def passive_damage_bonus(participant_state: dict) -> Tuple[float, Optional[str]]:
    # key = participant_state.get("passive_key"); dispatch table {key: fn}
    # unknown / None / pct == 0 -> (0, None)
    # berserker_rage -> (rage_bonus_pct(p.get("hp", 0), p.get("max_hp", 0)), key)
```
Epsilon: `hp` is a float reduced by float `dealt`; `1e-9` makes "exactly 10% lost" one step.

**`build_participant_info`** (main.py:312) — 6th soft-fail block:
```
try:
    info = await get_character_subclass(char_id)
    if info.get("is_npc"): subclass = passive = None
    else:
        subclass = {"key": info["subclass_key"], "name": info.get("subclass_name")} if info.get("subclass_key") else None
        passive = info.get("passive")
except Exception as e:
    logger.error(f"Не удалось получить подкласс/пассивку персонажа {char_id}: {e}")
    subclass = passive = None
```
Return dict gains `"subclass"` and `"passive"` (both may be `None`). `logger.error` per brief. `except Exception` also absorbs the `TypeError` in the 22 tests that replace `skills_client` with a plain `MagicMock` → they stay green unchanged (passive is just `None`); tests that check passives set `AsyncMock` explicitly.

**Payload / state:**
- Helper `_passive_key_of(snap) -> Optional[str]` = `(snap.get("passive") or {}).get("key")`.
- Factor the identical per-participant payload dict (in `_assemble_battle` main.py:787-807, `respond_to_pvp_invitation` ~:4136-4156, PvP attack ~:4429-4470) into one helper `_participant_payload(snap, participant_objs) -> dict` that also sets `"passive_key": _passive_key_of(snap)`; use it at all 3 sites. Deliberate, scoped de-duplication — the mitigation for the analyst's #1 risk; behaviour of other keys byte-identical.
- `redis_state.init_battle_state`: add `"passive_key": p.get("passive_key")` to the participant dict literal (`.get` → callers/tests that omit it still work).
- Join (`admin_approve_join_request`, ~main.py:5198): add `"passive_key": _passive_key_of(participant_info)` to the hand-written dict. Snapshot append already carries `subclass`/`passive` (it appends `participant_info`).

**Damage hook** (`_make_action_core`):
- Skill path, right after main.py:3348: `_passive_pct, _passive_key = passive_damage_bonus(battle_state["participants"][str(request.participant_id)])`; if `_passive_pct > 0`: `percent_damage_buffs["all"] = percent_damage_buffs.get("all", 0) + _passive_pct`.
- Item path, right after main.py:3112: same, for the acting participant (`participants_map[me]` / `part`), into `_item_pct_damage`.
- Log: on every **non-dodged** `"damage"` event appended by those two loops (~main.py:3455 and ~:3186), when the pct > 0, add `"passive_key": <key>, "passive_pct": <pct>`. `buff_pct` already includes the passive; `passive_pct` shows its share. Dodge-only events unchanged.
- Old states: no `passive_key` → `(0, None)`; missing/0 `max_hp` → 0. No crash.

### 3.4 Data flow

```
Battle start (any of 4 sites) / join approval
 └─ battle-service build_participant_info(char_id)
      ├─ existing 5 calls (attributes fatal, rest soft)
      └─ GET skills-service /skills/internal/characters/{id}/subclass  [X-Internal-Token]
           ├─ MySQL: characters.is_npc
           ├─ MySQL: character_tree_progress ⨝ tree_nodes (subclass_choice)
           └─ registry subclasses.py → subclass name + PassiveDef
      → snapshot entry {..., subclass, passive} → Mongo battle_snapshots + Redis cache → client (badge)
      → _participant_payload → passive_key → Redis state participants[pid].passive_key
Attack (skill or item)
 └─ passives.passive_damage_bonus(attacker state) → +pct into percent_buffs["all"]
      → compute_damage_with_rolls (unchanged) → damage event {..., buff_pct, passive_key, passive_pct}
      → Celery save_log → Mongo battle_logs ; action response / WS → formatBattleEvent
Profile / skill tree
 └─ GET /skills/subclasses?class_id=N (public) → passive by subclass_key
      profile: subclass_key from existing profileSlice.equipmentRules
      tree:    subclass_key on subclass_choice nodes (FullClassTreeResponse)
```

### 3.5 Frontend design

- `api/subclasses.ts`: `export interface SubclassPassive { key: string; name: string; description: string; implemented: boolean }`; `Subclass.passive?: SubclassPassive | null`. Reuse `fetchSubclasses` (already throws a Russian message).
- **New shared component** `components/CommonComponents/PassiveBadge/PassiveBadge.tsx` (TSX + Tailwind): small round badge; hover (desktop) and tap toggle (touch) open a popover with name, description and, if `implemented === false`, muted «пока не действует в бою». Props `{ passive: { name: string; description: string; implemented?: boolean }; size?: 'sm' | 'md' }`. Closes on outside tap / Esc; popover stays inside a 360px viewport (max-w ~16rem, clamps). Used by both battle cards; profile/tree may reuse it or render inline text.
- **Battle** (`battleTypes.ts`, `BattlePage.tsx`, `Arena3D/arenaTypes.ts`, `Arena3D/FighterCard.tsx`, `CharacterSide/CharacterSide.tsx`): `ParticipantSnapshot` gains optional `subclass?: { key: string; name: string | null } | null; passive?: SubclassPassive | null` (old snapshots lack them). Map into `ArenaFighter.passive` (`arenaFighters`, BattlePage.tsx :746-789) and the 2D `CharacterSide` props. Badge in `FighterCard.tsx` (3D DOM via drei Html — verify the popover isn't clipped and receives pointer events) and in `CharacterSide.tsx` next to (not inside) `PlayerCard.jsx`. No badge when `passive` is null/absent. Do **not** touch `PlayerCard.jsx`, `CharacterResourcesList.jsx`, `CountdownTimer.jsx`. Turn queue not required.
- **Battle log** (`BattlePageBar/useBattleBar.tsx`): `BattleEvent` gains `passive_key?: string; passive_pct?: number`. Damage branch of `formatBattleEvent`: when `passive_pct > 0` append e.g. «· Ярость +12%»; name from `snapshotData.find(p => p.participant_id === event.source)?.passive?.name`, fallback «пассивка». Covers 2D bar and 3D Chronicle.
- **Profile** (`ProfilePage/CharacterTab/CharacterPanel.tsx`, optionally `redux/slices/profileSlice.ts`): when `equipmentRules.subclass_key` is set, show the subclass name near the class name and the passive (name + description; `PassiveBadge` or a compact expandable line). Registry via `fetchSubclasses(id_class)` (local effect or a small thunk — developer's choice); failure → visible Russian error. No subclass → nothing extra.
- **Skill tree** (`SkillTreeView/types.ts`, `SkillTreePage.tsx`, `NodeDetailPanel.tsx`, `useNodePage.tsx`, `Books3D/nodePageModel.ts`, optionally `Books3D/ChapterRibbon.tsx`): add `subclass_key?: string | null` to the tree node type (backend already sends it in `TreeNodeInTreeResponse`). Load the registry once per class in `SkillTreePage.tsx` (`fetchSubclasses(classTree.class_id)`, Russian error on failure) and pass a `Record<string, SubclassPassive>` down. On **every** `subclass_choice` node (chosen or not — preview before choosing) show «Пассивка: <name>» + description (+ «пока не действует в бою» if not implemented) — books view via `useNodePage`/`nodePageModel`, panel view via `NodeDetailPanel`.
- Rules: read `docs/DESIGN-SYSTEM.md` first; no `React.FC`; Tailwind only; design-system classes/tokens; 360px+; all errors in Russian; `npx tsc --noEmit` + `npm run build` inside Docker.

### 3.6 Security

| Endpoint | Auth | Rate limit | Validation | Authorization |
|---|---|---|---|---|
| `GET /skills/internal/characters/{id}/subclass` | `X-Internal-Token` (fail-closed) | n/a — not routable via nginx | int path param; ORM / bound `text()` only | service-only; returns no PII (subclass + is_npc) |
| `GET /skills/subclasses` (extended) | public, unchanged | existing nginx limits | optional int `class_id` | static registry, no user data |

Errors are generic Russian strings; the token/headers are never logged.

### 3.7 Cross-service validation

- `GET /skills/subclasses`: additive field → existing consumers unaffected.
- Snapshot entries +2 keys → autobattle (`snap_me["attributes"]`, autobattle main.py:252/292) unaffected; `SpectateStateResponse.snapshot` / `AdminBattleStateResponse.snapshot` are `Optional[list]` → pass through.
- Redis state +`passive_key` → readers use explicit keys; new reads use `.get`.
- Damage event +2 optional keys → `save_log` stores dicts as-is; frontend fields optional.
- inventory-service unchanged (D8); dungeon-service battles get passives via `_assemble_battle`.

### 3.8 Risks & mitigations

| Risk | Mitigation |
|---|---|
| Wrong header (Bearer) → 401 swallowed → "no passive" forever, green tests | Separate `_internal_headers()`; QA asserts **exact header name + value** of the new call, and the endpoint test asserts Bearer is rejected. |
| Wrong column / fixture schema (`is_npc` missing in a test `characters` table; wrong `node_type` literal) | QA builds the test `characters` table with `is_npc` as in prod and asserts the real `subclass_key` / `passive.key` for a seeded `subclass_choice` progress row (not just "200"). |
| One construction site forgotten | Fetch in `build_participant_info`; payload via one helper; QA covers `_assemble_battle`, PvP invitation, PvP attack, join. |
| Old in-progress battles | `.get` defaults, `max_hp` guard; QA test with a state lacking the key. |
| Description drifts from constants | Cross-referencing docstrings (D5). |
| Latency | +1 call/participant with 3 s timeout (D3). |

### 3.9 Rollback
Code-only, no schema. Revert the commits; in-flight battles keep an unused `passive_key`/`passive` key — harmless to old code.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Parallelism: tasks 1, 2 and 3 can start at once (contracts fixed in §3.2). Task 4 needs task 3's shared types/component. QA 5 after 1, QA 6 after 2. Reviewer last. **No agent runs `git commit` / `git push`.**

### Task 1 — skills-service: passive registry, public field, internal subclass endpoint
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/skills-service/app/subclasses.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `docs/services/skills-service.md`, `docs/ISSUES.md` |
| **Depends On** | — |
| **Description** | (1) Add `PassiveDef` + `SubclassDef.passive` for all 21 subclasses with the keys/names of §3.1, Russian descriptions from `docs/SUBCLASS-PASSIVES.md` (Berserk: rage only, no vampirism), `implemented=True` only for `berserker_rage`; helper `get_passive_for_subclass`; docstring cross-ref to `battle-service/app/passives.py`. (2) `PassiveRead`, nested `SubclassRead.passive`, `CharacterSubclassRead` (Pydantic v1, §3.2). (3) `crud.get_character_subclass_key` (async ORM) + bound-SQL `is_npc` read. (4) `GET /skills/internal/characters/{character_id}/subclass` with `Depends(verify_internal_token)`, registered before `/{skill_id}`; 404 «Персонаж не найден»; 200 with nulls when no subclass. (5) Docs: endpoint + registry in `skills-service.md`; LOW tech-debt entry in `docs/ISSUES.md` "inventory `equipment_rules.load_character_scope` still raw-reads skills tables instead of the official endpoint" (reason: D8). |
| **Acceptance Criteria** | `python -m py_compile` on all changed files passes (inside the container). `GET /skills/subclasses` returns 21 entries each with `passive.{key,name,description,implemented}`; old fields unchanged. Internal endpoint: correct header → 200 with real key for a character with a chosen `subclass_choice`; Bearer-only / missing / wrong token → 401; empty env → 503; unknown character → 404; NPC → `is_npc: true`. Route not shadowed by `/{skill_id}`. Existing skills-service tests still green. |

### Task 2 — battle-service: load passive into battle, Berserk «Ярость», log keys
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/battle-service/app/passives.py` (new), `app/skills_client.py`, `app/main.py`, `app/redis_state.py`, `docs/services/battle-service.md`, `docs/SUBCLASS-PASSIVES.md` |
| **Depends On** | — (contract §3.2-B fixed; may run in parallel with Task 1) |
| **Description** | Per §3.3: (1) `passives.py` with named constants (`RAGE_HP_STEP_PCT=10`, `RAGE_PCT_PER_STEP=4`, `RAGE_MAX_STEPS=9`, `PASSIVE_BERSERKER_RAGE`), `rage_bonus_pct`, `passive_damage_bonus` (dispatch table). (2) `skills_client.get_character_subclass` with new `_internal_headers()` → `X-Internal-Token` (NOT Bearer), timeout constant 3.0. (3) `build_participant_info`: soft-fail block, `logger.error`, NPC → no passive; return `subclass` + `passive`. (4) Helper `_participant_payload` used by `_assemble_battle` + both inline PvP builders, adds `passive_key`; `_passive_key_of`. (5) `init_battle_state` copies `p.get("passive_key")`. (6) Join path dict gets `passive_key`. (7) Damage hooks after main.py:3348 and :3112 add the bonus into `"all"`; non-dodged damage events get `passive_key` + `passive_pct` when > 0. (8) Docs: battle-service.md (passive loading, state key, log keys, soft-fail); in `docs/SUBCLASS-PASSIVES.md` mark plan steps 2–3 done (step 2 as "official endpoint, no column") and opora 1 ✅, Berserk rage live / vampirism pending. |
| **Acceptance Criteria** | `py_compile` passes. Existing battle-service test suite green (run inside container). Battles start normally when skills-service is unreachable (passive `None`, error logged). Snapshot entries contain `subclass`/`passive`; Redis participant state contains `passive_key` in all 4 construction paths. A berserker at 75% HP deals damage with `buff_pct` +8 vs full HP and the event has `passive_pct: 8`. Other 20 passives: zero effect. No change to `compute_damage_with_rolls`. |

### Task 3 — frontend: registry types, PassiveBadge, profile and skill tree
| Field | Value |
|---|---|
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `src/api/subclasses.ts`, `src/components/CommonComponents/PassiveBadge/PassiveBadge.tsx` (new), `src/components/ProfilePage/CharacterTab/CharacterPanel.tsx`, optionally `src/redux/slices/profileSlice.ts`, `src/components/SkillTreeView/types.ts`, `SkillTreePage.tsx`, `NodeDetailPanel.tsx`, `useNodePage.tsx`, `Books3D/nodePageModel.ts`, optionally `Books3D/ChapterRibbon.tsx` |
| **Depends On** | — (contract §3.2-A fixed; live check needs Task 1) |
| **Description** | Per §3.5: `SubclassPassive` type + `Subclass.passive`; `PassiveBadge` (hover + tap popover, «пока не действует в бою» for not implemented, Esc/outside close, fits 360px); profile shows subclass + passive when `equipmentRules.subclass_key` is set; skill tree shows «Пассивка: …» + description on every `subclass_choice` node in both the books view and the panel view; registry loaded via `fetchSubclasses(classId)` with visible Russian error on failure. |
| **Acceptance Criteria** | Read `docs/DESIGN-SYSTEM.md` first. No `React.FC`, no new SCSS, no `.jsx` touched. `npx tsc --noEmit` and `npm run build` pass (inside Docker). Berserk character: profile shows «Берсерк» + «Ярость» with description; tree's subclass node shows the passive; another subclass shows description + «пока не действует в бою»; character without subclass shows nothing extra. Layout OK at 360px. |

### Task 4 — frontend: battle badge and battle-log line
| Field | Value |
|---|---|
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `src/components/pages/BattlePage/battleTypes.ts`, `BattlePage.tsx`, `Arena3D/arenaTypes.ts`, `Arena3D/FighterCard.tsx`, `CharacterSide/CharacterSide.tsx`, `BattlePageBar/useBattleBar.tsx` |
| **Depends On** | 3 (uses `PassiveBadge` + `SubclassPassive`) |
| **Description** | Per §3.5: optional `subclass`/`passive` on `ParticipantSnapshot`, `passive` on `ArenaFighter`; `PassiveBadge` on 3D `FighterCard` and on 2D `CharacterSide` (outside `PlayerCard.jsx`); `BattleEvent.passive_key/passive_pct`; damage line appends «· <name> +N%» via the source participant's snapshot passive name (fallback «пассивка»). |
| **Acceptance Criteria** | `tsc --noEmit` + `npm run build` pass. Badge visible for participants with a passive in 3D and 2D mode, tooltip works by hover and tap, not clipped by the 3D canvas; mobs / old snapshots → no badge, no console errors. Berserker hit below 90% HP shows the passive segment in both the bar log and the 3D Chronicle. `PlayerCard.jsx`, `CharacterResourcesList.jsx`, `CountdownTimer.jsx` untouched. 360px OK. |

### Task 5 — QA: skills-service endpoint, auth, registry
| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | `services/skills-service/app/tests/test_internal_auth.py` (extend), new `app/tests/test_character_subclass_internal.py`, registry test (new or in an existing subclasses test) |
| **Depends On** | 1 |
| **Description** | Tests: (a) auth matrix for the new route — valid `X-Internal-Token` → 200; same secret as `Authorization: Bearer` only → 401; missing / wrong → 401; empty env (monkeypatch `auth_http.INTERNAL_SERVICE_TOKEN`) → 503. (b) Data: test `characters` table **includes `is_npc`** as in prod; seeded `subclass_choice` node with `subclass_key="warrior_berserker"` + progress row → response has `subclass_key`, `subclass_name="Берсерк"`, `passive.key="berserker_rage"`, `implemented=true` (assert values, not only status). No subclass → nulls; only a non-subclass node chosen → nulls; NPC → `is_npc=true`; unknown character → 404; unknown registry key on node → `subclass_key` set, `passive` null. Route-order test: the path is not handled by `/{skill_id}`. (c) Registry: 21 subclasses, all passive keys unique, exactly `{"berserker_rage"}` implemented, `GET /skills/subclasses` items contain `passive` with all 4 fields and old fields unchanged. (d) Security: non-int id → 422; SQL-ish id string → 422. |
| **Acceptance Criteria** | All new + existing skills-service tests pass (`pytest` inside the container). A deliberately wrong header in the fixture would fail the tests (header assertions are on the real header name). |

### Task 6 — QA: battle-service passive loading, rage math, hooks, old states
| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | new `services/battle-service/app/tests/test_subclass_passives.py`; extend `test_skills_client.py`, `test_internal_headers.py` and/or `test_feat171_outgoing_internal.py`, `test_redis_state.py`, `test_join_requests.py` |
| **Depends On** | 2 |
| **Description** | (a) Client: `get_character_subclass` hits `/skills/internal/characters/{id}/subclass` with header **`X-Internal-Token: <token value>`** and **no** `Authorization: Bearer`; add it to the outgoing-internal-header registry test. (b) `build_participant_info` with `AsyncMock` client: player → `subclass`/`passive` set; `is_npc=true` → both `None`; client raises (connection error / 401 / plain `MagicMock` → `TypeError`) → `None` and `logger.error` called, other fields intact, no exception. (c) `init_battle_state` writes `passive_key` (present and absent in payload → `None`). (d) Each construction path ends with `passive_key` in Redis state: `_assemble_battle`, PvP invitation accept, PvP attack, admin join approval (join: also snapshot appended with `passive`). (e) `rage_bonus_pct`: full HP 0; 9.99% lost 0; exactly 10% → 4; 19.9% → 4; 25% → 8; 50% → 20; 89.9% → 32; 90% → 36; 99% → 36; hp ≤ 0 → 36 (cap); hp > max_hp → 0; max_hp 0 / missing / None → 0; float HP after float damage (e.g. 100 → 89.99999) works. (f) `passive_damage_bonus`: no key / unknown key / other 20 keys → (0, None). (g) Integration through `_make_action_core` (style of `test_weapon_damage_once.py` / `test_item_usage.py`): berserker at 50% HP — skill attack damage event has `passive_pct: 20` and `buff_pct` +20 vs. baseline; item-damage event too; non-berserker → no `passive_pct`; old state without `passive_key` and without `max_hp` → attack resolves, no key. |
| **Acceptance Criteria** | All new + existing battle-service tests pass inside the container. Header test asserts the exact value. No test relies on the swallowed-error path to pass the "happy" cases. |

### Task 7 — Review
| Field | Value |
|---|---|
| **Agent** | Reviewer |
| **Status** | DONE |
| **Files** | all of the above |
| **Depends On** | 1, 2, 3, 4, 5, 6 |
| **Description** | Full review per `agents/reviewer.md`: contracts match §3.2 (incl. header = `X-Internal-Token`), no missed construction site, `.get` on all new state reads, constants only in `passives.py`, no lifesteal, inventory untouched, frontend rules (Tailwind, TS, no `React.FC`, design system, 360px, Russian errors, no `.jsx` touched), docs + ISSUES updated. Re-run `py_compile`, both pytest suites, `tsc --noEmit`, `npm run build` (inside Docker). Live: start a battle with a berserker character (see `reference_dungeon_test_run` / test creds) — badge + tooltip in 3D and 2D, log line with «Ярость +N%» after taking damage; profile and skill tree show the passive; stop skills-service → a new battle still starts. |
| **Acceptance Criteria** | All checks green, live verification with zero console errors; PASS/FAIL recorded in §5. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-10-31
**Result:** FAIL

One blocking runtime bug in the shared `PassiveBadge` popover: opening it (mouse hover, click or tap) sends React into an infinite update loop, and the whole app unmounts to a blank page. Reproduced live on the profile and on the 2D battle card. Backend, contracts, tests and the battle-log line all pass.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/CommonComponents/PassiveBadge/PassiveBadge.tsx:62-65` (interacts with `CommonComponents/InfoTooltip.tsx:76-79`) | **Blocking crash.** `PassiveBadge` passes a new `<PassiveInfo passive={passive} />` element to `useTooltip` on every render. `useTooltip`'s `useLayoutEffect` has `content` in its deps and, while open, calls `place()` → `setPos({...})` with a new object each time. Each re-render creates new `content`, the effect runs again, and the loop never stops. Live result: hovering the badge on `/profile`, or clicking it on the 2D battle card, throws "Maximum update depth exceeded" (thrown from `PassiveBadge`) and `#root` ends up with 0 children (blank page). The 3D card and the skill tree's `PassiveInfo` use the same component, so the 3D card's popover is also unusable (not clicked, to avoid another crash). Fix options: memoize the content in `PassiveBadge` (`useMemo(() => <PassiveInfo .../>, [passive.name, passive.description, passive.implemented])`), and/or make `place()` skip `setPos` when top/left are unchanged, and/or drop `content` from the effect deps. Existing `InfoTooltip`/`WithTooltip` callers mostly pass strings, so the bug only shows up with element content. A fix must be re-verified live by hovering and tapping in the profile, the 2D card and the 3D card. | Frontend Developer | FIXED (verified in Review #2) |

#### Code review (no issues beyond #1)
- Contracts: skills `CharacterSubclassRead`/`PassiveRead` (Pydantic v1, `orm_mode`) ↔ `skills_client.get_character_subclass` ↔ snapshot `subclass`/`passive` ↔ TS `ParticipantPassiveFields`/`SubclassPassive`: field names and types match. `SubclassRead.passive` is additive, so existing consumers are unaffected.
- Security: the new route uses `Depends(verify_internal_token)`. The client sends `X-Internal-Token` through a separate `_internal_headers()` and does not send Bearer. The route is registered before `/{skill_id}`. `is_npc` is read with bound `text()`. Live: `GET /skills/internal/characters/761/subclass` through the gateway → **403** (nginx `location /skills/internal/` in both configs).
- battle-service: all 4 construction sites are covered (`_participant_payload` used by `_assemble_battle` and both PvP inline paths; the join dict has `passive_key`). `init_battle_state` uses `.get`. Soft-fail uses `logger.error`. Hooks in both the skill path and the item path are evaluated once per attack. `passive_pct` is attached only to non-dodged damage events. Constants live only in `passives.py`. No lifesteal. `compute_damage_with_rolls` is unchanged. inventory-service is untouched.
- The 22 MagicMock battle test files are unaffected: the `except Exception` in `build_participant_info` absorbs the TypeError, and the full suite is green.
- Frontend rules: TSX only, no `.jsx`/SCSS touched (`PlayerCard.jsx`, `CharacterResourcesList.jsx`, `CountdownTimer.jsx` unchanged). Tailwind and design-system tokens (`gold-text`, `site-tooltip`, `rounded-card`, `text-site-red`). No `React.FC`. Registry errors are shown in Russian (toast on the tree, red line on the profile).
- docs/ISSUES.md: both new LOW entries are accurate. Verified that `main.py:5276` really posts to `/autobattle/register`, which does not exist in autobattle (only `/register` and `/internal/register`).

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container): PASS
- [x] `vite build` (frontend container, output to /tmp, removed afterwards): PASS
- [x] `py_compile` on all modified/new Python files (battle + skills): PASS
- [x] `pytest` skills-service (python:3.10-slim, `--asyncio-mode=auto`): **379 passed**
- [x] `pytest` battle-service (python:3.10-slim, `--asyncio-mode=auto`): **983 passed**
- [x] `docker compose config`: PASS
- [ ] Live verification: **FAIL** (issue #1)

#### Live Verification Results (localhost only)
- Setup (local DB): added a `character_tree_progress` row (761, tree 2, node 88 `warrior_berserker`) for admin's character 761 «Аэлис». Temporarily switched `users.current_character` 4 → 761 and restored it to 763 afterwards. The progress row is left in place for re-verification.
- Internal endpoint called from the battle-service container: 761 → `warrior_berserker`/«Ярость» `implemented=true`; 763 → `mage_salamander`/«Разгорание» `implemented=false`. PASS.
- `/profile`: header «Человек | Воин | Берсерк» plus a gold «Ярость» chip. PASS. **Hovering the chip crashes the app** (issue #1).
- `/skill-tree` (scheme/panel view): Берсерк node → «Пассивка: Ярость» plus description. Паладин node → «Священный обет» plus description plus «пока не действует в бою». PASS. The 3D book ink page was reviewed in code only.
- Battle 308 (`POST /battles/`, 761 vs mob 999907): snapshot contains `subclass`/`passive` for the berserker and `null` for the mob. Redis `participants.699.passive_key = berserker_rage`, mob `None`. HP was set to 180/250 in local Redis (28% lost). After a sword strike the turn-1 event has `buff_pct: 8, passive_key: berserker_rage, passive_pct: 8`, and the 2D log shows «Аэлис→Дикий Волк ⚔️−11 · Ярость +8%». PASS (N matches the HP lost). The mob's hit carries no passive keys.
- Badge: rendered on the berserker's 2D card and on the 3D `FighterCard`. No badge on the mob. **Clicking the 2D badge → "Maximum update depth exceeded", blank page** (issue #1).
- Network: `/battles/308/state` and `/battles/battles/308/logs/2` → 200. No 4xx/5xx observed on the API calls inspected.
- Console: the only errors are the crash from issue #1. Otherwise only React Router future-flag warnings (pre-existing).
- Not done because of issue #1: popover clipping and pointer events on 3D, and the 360px iframe layout check. These must be done on re-review. The battle was force-finished afterwards via the admin endpoint.

### Review #2 — 2026-10-31
**Result:** PASS

This re-review covers only the issue #1 fix and the live checks that Review #1 could not finish. The backend review from Review #1 still stands; the backend has not changed since.

#### Code review of the fix
- `InfoTooltip.tsx` `useTooltip`:
  - `place()` now updates position with `setPos(prev => same top/left ? prev : {...})`. Re-placing at the same spot returns the same state object, so React skips the re-render. This breaks the loop at its source, whatever content identity the caller passes.
  - The layout effect and the listener effect depend on `[open, hasContent, place]`, where `hasContent` is a boolean. Element identity no longer re-runs either effect.
  - A `ResizeObserver` on the bubble runs `place()` while it is open, which replaces the old "re-place on content change" behaviour. It is created after commit, when `tipRef` is set. It is disconnected in the same cleanup as the keydown, pointerdown, scroll (capture) and resize listeners. It re-attaches if the content goes from empty to non-empty while open, because `hasContent` is in the deps. It is guarded with `typeof ResizeObserver !== 'undefined'`. Its callback can't loop, because `place()` is idempotent.
  - The optional `zIndex` is additive.
- `PassiveBadge.tsx`: `content` is memoized on `name`, `description` and `implemented`. `onClick` calls `stopPropagation()` before `toggleByClick()`.
- Existing callers: `InfoTooltip`, `WithTooltip`, and the houses, TrophyHall and ParamHint pages. Their API is unchanged and they keep the same open/close semantics: hover for mouse, tap toggles, Escape closes, a tap outside closes, blur closes.
- Minor, non-blocking: if the anchor moves without a scroll, resize or bubble resize (for example a drei `<Html>` card moving with the camera), the open bubble does not follow. Before the fix it only re-placed when content identity changed, so this is not a regression.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container): PASS (exit 0)
- [x] `npx vite build --outDir /tmp/rev2-build` (frontend container): PASS (built in 49.5 s). The output was removed afterwards.

#### Live Verification Results (localhost only, admin, character 761 «Аэлис», Berserk)
- **(a) `/profile`:**
  - A real mouse hover over the «Ярость» chip opens the popover («Пассивка: Ярость» plus description) above the badge. Moving the mouse away closes it.
  - A real click keeps it open.
  - An emulated touch tap opens it, a second tap closes it, a tap outside closes it, and Escape closes it.
  - `#root` stays mounted. **Console errors: 0.** PASS.
- **(b) Battle 309 (761 vs mob 999907):**
  - 2D: a real click on the card badge opens the popover (z-index 1100), and the page stays alive. The target stays «Дикий волк».
  - Log: HP was 156/250 (37.6 % lost, no Redis edit needed). After «Удар воителя», the turn-1 event had `buff_pct: 12, passive_key: berserker_rage, passive_pct: 12`. The 2D log (turn 1) shows «Аэлис → Дикий Волк ⚔️ −14 КРИТ · Ярость +12%». PASS.
  - 3D (`/battle3d/309`): a real click on the `FighterCard` badge opens the popover fully visible above the card. It is portaled to `<body>` and sits above the canvas and the drei layers, with nothing clipped.
  - 3D touch tap: the popover opens inside the viewport and closes on a tap on the canvas.
  - The selection chips «ВЫ» / «ЦЕЛЬ» stay unchanged after tapping the badge. In 1v1 your own card is not selectable even with a defense skill chosen, so "the badge does not select the card" is confirmed through the unchanged chips plus the `stopPropagation()` in code. A selectable-ally case would need a team battle.
  - **Console errors: 0.** PASS.
- **(c) 390×844 same-origin iframe:**
  - `/profile`: no page-level horizontal overflow. The only elements past the edge are the profile tab strip buttons, which sit in an existing scrollable strip. The tapped popover spans 15–300 px and fits.
  - 2D battle: the popover spans 33–318 px and fits. The badge does not affect layout: hiding it changes no positions. The card and resource overlap at this width is **pre-existing** and already tracked in `docs/ISSUES.md` («страница боя на 360px вылезает за экран…», FEAT-166).
  - 3D battle: `scrollWidth` is 390, the popover spans 89–374 px over the table, and the controls at the bottom remain reachable.
  - No errors in any frame. PASS.
- **(d) Existing `InfoTooltip` (admin `/admin/economy` → «Пересчёт», `ParamHint`):** `ParamHint` passes a fresh element as content, which is the same pattern that used to loop.
  - A real hover opens it above the «i» button.
  - With it opened by tap, the bubble follows a 60 px page scroll and keeps the same gap.
  - Making the bubble taller re-places it through the `ResizeObserver`: the final position differs from a fixed-top grow. It returns to the original gap after shrinking.
  - A tap outside closes it.
  - Console errors: 0. PASS.

#### Local state changes (dev only)
- `users.current_character` for user 4: switched 763 → 761 for the test and **restored to 763**.
- Battle 309 was created (761 vs mob 999907), one turn was played via `POST /battles/309/action`, and it was then force-finished via `POST /battles/admin/309/force-finish`. DB status is `finished` and the Redis `battle:309:state` key is gone.
- No Redis edits. The `character_tree_progress` row (761, node 88) added in Review #1 is still in place.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-10-31 — PM: фича создана по итогам пересмотра пассивок, запускаю анализ
[LOG] 2026-10-31 20:21 — Analyst: анализ завершён — затронуты skills-service, battle-service, фронтенд (inventory опционально); найдено 4 места сборки участников боя (общий _assemble_battle, 2 дубля в PvP, вступление в бой), хук урона main.py:3348/3112; обнаружен баг (регистрация НПС в автобое при вступлении по несуществующему пути), добавлен в ISSUES.md
[LOG] 2026-10-31 20:40 — Architect: спроектировано 7 задач (2 backend, 2 frontend, 2 QA, ревью), 2 API-контракта (новый внутренний GET /skills/internal/characters/{id}/subclass и расширение GET /skills/subclasses полем passive); подкласс выводится из узла subclass_choice без новой колонки, пассивка грузится в build_participant_info (все 4 места сборки боя), числа «Ярости» — в battle-service/app/passives.py; inventory-service не трогаем
[LOG] 2026-10-31 21:00 — Backend Dev: начал задачу #1 (skills-service: реестр пассивок, внутренний эндпоинт подкласса)
[LOG] 2026-10-31 21:30 — Backend Dev: задача #1 завершена, изменено 6 файлов — PassiveDef для всех 21 подкласса (живая только berserker_rage, «Ярость» без вампиризма), поле passive в GET /skills/subclasses, новый GET /skills/internal/characters/{id}/subclass (X-Internal-Token, 404 «Персонаж не найден», без подкласса — null); py_compile ок, тесты skills-service 340 passed; в ISSUES.md добавлен LOW-долг про сырой SQL подкласса в inventory (решение D8)
[LOG] 2026-10-31 21:00 — Backend Dev: начал задачу #2 (battle-service: загрузка пассивки в бой, «Ярость» Берсерка)
[LOG] 2026-10-31 21:40 — Backend Dev: задача #2 завершена (battle-service), изменено 4 файла кода + 2 дока — новый passives.py («Ярость» +4% за 10% потерянного HP, до +36%), skills_client.get_character_subclass с X-Internal-Token и таймаутом 3 с, подкласс/пассивка в build_participant_info (мягкий отказ с logger.error, мобы без пассивки), общий хелпер _participant_payload вместо 3 копий, passive_key в init_battle_state и при вступлении в бой, хуки урона навыка и предмета, ключи passive_key/passive_pct в логе; py_compile ок, тесты battle-service 889 passed (в контейнере)
[LOG] 2026-10-31 21:10 — Frontend Dev: начал задачу #3
[LOG] 2026-10-31 21:50 — Frontend Dev: задача #3 завершена — тип SubclassPassive в api/subclasses.ts, хук useSubclassRegistry, новый общий компонент PassiveBadge (значок + всплывашка по наведению/тапу/фокусу, закрытие по Esc и тапу мимо, пометка «пока не действует в бою», параметр tooltipZIndex для 3D-карточек из задачи #4) и PassiveInfo; useTooltip из InfoTooltip.tsx экспортирован (+ опция zIndex); профиль: подкласс в строке «раса | класс | подкласс» и значок пассивки с названием; дерево навыков: «Пассивка: …» с описанием на каждом узле subclass_choice — в книгах (чернилами на странице) и в панели колеса; реестр грузится целиком один раз (на экране бывают деревья всех классов), ошибка — тостом / красной строкой в профиле; .jsx/SCSS не тронуты; tsc --noEmit и vite build в контейнере frontend — ок
[LOG] 2026-10-31 21:45 — QA: начал задачу #5 (тесты skills-service: внутренний эндпоинт подкласса, реестр пассивок)
[LOG] 2026-10-31 22:05 — QA: задача #5 завершена — новый файл tests/test_character_subclass_internal.py (39 тестов; test_internal_auth.py не трогал — матрица авторизации нового роута целиком в новом файле): без заголовка / Bearer с тем же секретом / неверный / пустой токен / токен в чужом заголовке → 401, пустой env → 503, без токена неизвестный id → 401 (не 404); реальные значения на тестовой таблице characters с is_npc и настоящих узлах subclass_choice без моков crud (Берсерк → «Ярость», implemented=true), только обычный узел / нет прогресса → null, NPC → is_npc=true, неизвестный ключ → ключ есть, пассивки нет, побеждает последний выбор, ключ на обычном узле и subclass_choice без ключа игнорируются; 404 для несуществующего/0/-1, 422 для нечисловых и SQL-подобных id, роут зарегистрирован раньше /{skill_id}; GET /skills/subclasses — 21 запись с passive из 4 полей, ключи уникальны, живая только berserker_rage, фильтр по классу 1/2/3 = 7; весь набор skills-service в контейнере — 379 passed (новый файл отдельно — 39 passed); багов не найдено
[LOG] 2026-10-31 22:00 — Frontend Dev: начал задачу #4 (значок пассивки в бою, строка «Ярость» в логе)
[LOG] 2026-10-31 22:30 — Frontend Dev: задача #4 завершена — поля subclass/passive в снимке участника (общий тип ParticipantPassiveFields в battleTypes.ts, подключён в BattlePage и useBattleBar), passive у ArenaFighter и CharacterData; значок PassiveBadge в правом верхнем углу 3D-карточки FighterCard и на 2D-карточке в CharacterSide (рядом с PlayerCard.jsx, не внутри; тап не выбирает цель); всплывашка порталится в body с z-1100 — выше слоёв drei Html (zIndexRange 30..0), отдельный tooltipZIndex не понадобился; в логе удара «· <название пассивки> +N%» при passive_pct > 0 (имя из снимка атакующего, иначе по ключу, иначе «пассивка») — и в 2D-панели, и в 3D-хронике; старые снимки/логи без ключей — как раньше; .jsx/SCSS не тронуты; tsc --noEmit и vite build в контейнере frontend — ок
[LOG] 2026-10-31 22:40 — QA: начал задачу #6 (тесты battle-service: пассивки подклассов)
[LOG] 2026-10-31 23:20 — QA: задача #6 завершена — новый tests/test_subclass_passives.py (89 тестов: математика «Ярости» с границами 10/90%, клампом и шумом float; диспетчер пассивок и сверка с реестром skills-service — implemented=True ровно у berserker_rage, описание Берсерка цитирует константы; реальный get_character_subclass — URL /skills/internal/characters/{id}/subclass, заголовок ровно X-Internal-Token со значением из env, без Bearer, таймаут 3 с; build_participant_info — пассивка у берсерка, None у НПС, мягкий отказ с logger.error при сетевой/HTTP-ошибке и plain MagicMock, сквозной 401 от настоящего клиента; _assemble_battle → настоящий init_battle_state → JSON в Redis; хуки урона навыка и предмета на реальных buffs и формуле урона: +20% в «all» и passive_pct у раненого берсерка, ничего у полного HP/не-берсерка/других 20 пассивок, уклонение без изменений, старое состояние без passive_key и max_hp не падает); дописаны PvP-атака, принятие PvP-приглашения и одобрение вступления (passive_key в состоянии и пассивка в снимке); мутационная проверка (Bearer вместо X-Internal-Token, удалённый хук, забытый ключ при вступлении) — тесты краснеют; полный прогон battle-service в контейнере: 983 passed (было 889); прод-код не менялся, багов в задаче #2 не найдено
[LOG] 2026-10-31 21:00 — Reviewer: начал проверку
[LOG] 2026-10-31 21:20 — Reviewer: проверка завершена, результат FAIL — бэкенд, контракты, тесты (skills 379, battle 983), tsc и сборка — ок; «Ярость +8%» в логе боя при 28% потерянного HP — ок; блокер: всплывашка PassiveBadge (PassiveBadge.tsx:62) уходит в бесконечный цикл обновлений и роняет всё приложение в пустую страницу — при наведении в профиле и по клику на значок в бою; нужен фикс фронтенда и повторная живая проверка (включая 3D и 360px)
[LOG] 2026-10-31 23:40 — Frontend Dev: начал исправление бага #1 из ревью (бесконечный цикл обновлений во всплывашке PassiveBadge)
[LOG] 2026-10-31 23:55 — Frontend Dev: баг #1 исправлен с двух сторон — useTooltip (InfoTooltip.tsx): place() больше не создаёт новый объект позиции, если top/left не изменились (setPos(prev => …)), эффект позиционирования зависит только от open и булева «есть ли контент», а не от identity элемента; изменение размеров всплывашки ловит ResizeObserver; PassiveBadge.tsx: контент всплывашки мемоизирован по name/description/implemented; другие вызовы useTooltip (InfoTooltip/WithTooltip) получают content пропсом от родителя и в цикл не попадали, их поведение не изменилось; tsc --noEmit и vite build в контейнере frontend — ок; живая проверка на localhost (персонаж 761): наведение и клик по значку «Ярость» в профиле — всплывашка открывается, закрывается по Esc и уходу мыши, страница не падает, ошибок в консоли 0; дерево навыков загружается без ошибок (там PassiveInfo без всплывашки); current_character админа возвращён на 763; бой (2D/3D, 360px) перепроверит ревьюер
[LOG] 2026-10-31 — Reviewer: начал повторную проверку (Review #2) — фикс всплывашки PassiveBadge/useTooltip и живые проверки, не завершённые в Review #1
[LOG] 2026-10-31 — Reviewer: повторная проверка завершена, результат PASS — tsc и vite build в контейнере ок; профиль: наведение/клик/тап по «Ярости», Esc и тап мимо — всплывашка работает, приложение не падает, 0 ошибок в консоли; бой 309 (Аэлис против волка): значок на 2D и 3D карточке открывает всплывашку, в 3D она не обрезается и выше канваса, тап по значку не меняет цель, в логе «· Ярость +12%» при 37% потерянного HP; 390px (iframe): профиль, 2D и 3D бой — всплывашка в пределах экрана (наложение карточек 2D-боя на узком экране — старый баг, уже в ISSUES.md); старая подсказка InfoTooltip (ParamHint в админке экономики) открывается, следует за прокруткой и перестраивается при изменении размера; бой 309 завершён через админку, current_character админа возвращён на 763
[LOG] 2026-10-31 — PM: ревью PASS, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Подкласс персонажа** — официальный внутренний эндпоинт `GET /skills/internal/characters/{id}/subclass` (skills-service, `X-Internal-Token`); подкласс по-прежнему выводится из выбранного узла `subclass_choice`, новой колонки и миграций нет.
- **Реестр пассивок** — все 21 пассивка (название + описание по `docs/SUBCLASS-PASSIVES.md`) в `subclasses.py`, поле `passive` в `GET /skills/subclasses`; живая только «Ярость».
- **Загрузка пассивки в бой** — в `build_participant_info` (все пути старта боя и вступление в идущий бой), мягкий отказ при недоступности skills-service, мобы без пассивок; `passive_key` в состоянии Redis.
- **«Ярость» Берсерка** — +4% урона за каждые полные 10% потерянного HP (до +36%), к навыкам и предметам; константы в `battle-service/app/passives.py`; в логе боя «· Ярость +N%».
- **Фронтенд** — общий `PassiveBadge`: профиль («раса | класс | подкласс» + значок), дерево навыков (колесо и книги), бой (2D и 3D карточки), пометка «пока не действует в бою» для неживых пассивок.
- **Тесты** — skills-service 379 passed (+39), battle-service 983 passed (+94).

### Что изменилось от первоначального плана
- Отдельная колонка `character_subclass` не понадобилась — подкласс выводится из прогресса дерева.
- Три копии сборки участника для Redis сведены в один хелпер `_participant_payload`.
- Ревью #1 нашло вылет приложения при открытии всплывашки значка (бесконечный цикл в `useTooltip`); исправлено, ревью #2 — PASS.

### Оставшиеся риски / follow-up задачи
- Вампиризм «Ярости» ниже 25% HP — ждёт механики вампиризма.
- Остальные 20 пассивок — следующие фичи (сначала на существующих модификаторах, затем щит/вампиризм/отражение/оплата HP, перескок, баф союзника, удар по своим).
- inventory-service читает подкласс сырым SQL (LOW в ISSUES.md); регистрация НПС в автобое при вступлении по несуществующему пути (LOW в ISSUES.md).
- Локально: персонаж 761 (Аэлис) стал Берсерком (строка `character_tree_progress` → узел 88), HP после тестов неполное.
