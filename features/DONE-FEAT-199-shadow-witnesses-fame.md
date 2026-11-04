# FEAT-199: Тень — свидетели, скрытые преступления, маска, дурная слава, слава (репутация, этап 2б)

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
Продолжение FEAT-197 (репутация краёв, на проде c59c4af) и FEAT-198 («Закон»: розыск, стража, тюрьма — готов, не запушен, лежит в рабочем дереве). Пользователь (2026-11-04): «Делай все по этапам дальше до конца» — ушёл отдыхать, поэтому недостающие бизнес-решения принимает PM разумными значениями по умолчанию (все числа — редактируемые настройки в админке), список решений ниже; пользователь проверит по возвращении.

Исходная идея пользователя: «в мире существуют плохие фракции подпольного мира, их действия очевидно портят репутацию, но что если он делает что-то скрытно? Нужно подумать о механиках того, что персонаж может скрывать свои злодеяния». Ранее согласовано (память): свидетели (место, ловкость/удача, подкласс Ассасин/Фокусник/Агент, маска, размер группы); замечен → репутация + розыск; не замечен → подозрение края + отложенное раскрытие; маска → «неизвестный в маске»; тайная дурная слава видна только подполью; слава как «громкость» (узнают, крупные квесты, титулы, выше шанс свидетелей).

### Бизнес-правила (решения PM по умолчанию)
- **Свидетели.** Каждое преступление (сейчас — убийство мирного NPC через «Нападение»; FEAT-198 пишет `law_crimes` с точкой расширения `register_crime`) проходит проверку свидетелей. Шанс быть замеченным = база по месту (город/поселение высоко, дикие места низко — по типу локации, если он есть; иначе база края) − ловкость/удача (эффективные значения с капом FEAT-195) − бонус подкласса (Ассасин, Фокусник, Агент) − маска + размер группы нападающих + слава (узнаваемость), с границами (мин 5 %, макс 95 %). Бросок на сервере.
  - **Замечен** → всё как сейчас (FEAT-197/198): минус репутации, розыск.
  - **Не замечен** → репутация и розыск сейчас не меняются; у края растёт **подозрение** (общая шкала края, видна всем как «В крае неспокойно»); преступление остаётся **нераскрытым**.
- **Отложенное раскрытие.** Нераскрытое преступление в течение N дней (по умолчанию 3) раз в сутки проверяется на раскрытие (шанс растёт с подозрением края, падает с маской). Раскрыто → применяются отложенные репутация и розыск + уведомление «Ваше преступление раскрыто». Прошло N дней без раскрытия → дело закрыто навсегда.
- **Маска.** Предмет-маска (надетая) — при замеченном преступлении свидетели видят «неизвестного в маске»: персонаж не получает репутацию/розыск сразу, но подозрение края растёт сильнее, а преступление уходит в нераскрытые с пониженным шансом раскрытия. Как отметить предмет маской — по анализу (флаг на предмете или существующий слот).
- **Тайная дурная слава.** Каждое преступление (замеченное или нет) копит скрытую шкалу «дурная слава» персонажа (общую, не по краю). Её видят только сам игрок (в профиле, как «Слухи в подполье») и стафф; задел под будущие фракции подполья — без механик сейчас.
- **Слава («громкость»).** Общая публичная шкала персонажа, растёт от положительных поступков (задания, рост репутации) и громких дел; ступени с названиями (напр. Безвестный → Знакомое имя → Известный → Знаменитый → Легенда). Видна всем в профиле (это публичная известность). Эффект сейчас: увеличивает шанс быть замеченным при преступлении (тебя узнают). Задел: крупные квесты/титулы по ступени славы — поле «мин. слава» у заданий (как пороги репутации).
- **Подозрение края** спадает со временем; видно игрокам как текстовое состояние края на карте мира/в карточке края.
- Все веса/шансы/сроки — настройки в админке (раздел «Репутация», права как у FEAT-197/198: настройки — `reputation:settings`, ручные правки — `reputation:manage`).

### UX / Пользовательский сценарий
1. Игрок в маске нападает на торговца в глухой локации → бросок свидетелей → не замечен → «Никто не видел» (подсказка игроку), край «неспокоен».
2. Через день — бросок раскрытия → раскрыто → уведомление, репутация и розыск применяются.
3. Профиль: публичная «Слава» (ступень), личные «Слухи в подполье» (дурная слава), розыск/репутация как раньше.
4. Админ: настройки шансов, список нераскрытых преступлений, ручное раскрытие/закрытие дела.

### Edge Cases
- Групповое убийство: бросок на каждого участника или общий? (архитектор; по умолчанию общий бросок на группу, последствия каждому).
- Стражник убит/выбит скрытно — то же правило.
- Маска снята между преступлением и раскрытием — учитывается состояние на момент преступления.
- Персонаж удалён/NPC — пропуск.

### Вопросы к пользователю
- Пользователь недоступен; решения выше — PM по умолчанию, все параметры правятся в админке. Вынести на подтверждение по возвращении.

### Решения PM по вопросам аналитика (2026-11-04, пользователь недоступен — на подтверждение по возвращении)
1. **Группа:** один бросок свидетелей на убийство; шанс считается по **наименее скрытному** участнику (худшие ловкость/удача, без подкласса, без маски), плюс бонус за размер группы. Если замечены — участники **без маски** получают последствия сразу, участники **в маске** уходят в «неизвестный в маске» (отложенное раскрытие). Если не замечены — все уходят в нераскрытые.
2. **Маска:** флаг `is_mask` на предмете слота «голова» (занимает слот шлема) — ок.
3. **База шанса** — по `marker_type` локации (safe = поселение высоко, farm = средне, dangerous = дико низко, dungeon = очень низко), значения в настройках. Отдельного поля на локации не делаем.
4. **Слава:** отдельные источники с весами в настройках: выполнение задания (по умолчанию +5 славы; у задания может быть своё значение), положительный рост репутации (вес 0.5 от очков), заказы гильдии — 0 (чтобы не фармили). **«Мин. слава» у заданий делаем сейчас** (как порог репутации).
5. Игрок **не видит список** своих нераскрытых преступлений — только подсказку «Никто не видел» / «Свидетели видели лишь неизвестного в маске» и уведомление о раскрытии. Список — только у стаффа.
6. Шансы бегства и побега FEAT-198 перевести на **эффективные статы** (с капом FEAT-195) — да, заодно.
7. Особые случаи всегда «замечены»: бой при встрече со стражей, побег из тюрьмы.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline: FEAT-197 (on prod, c59c4af) + FEAT-198 (law; uncommitted, in the working tree — character `039_law`, locations `055`, battle `009`). All paths below are relative to `services/`.

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-service (owner of everything new) | witness step in the crime path, deferred apply, suspicion/infamy/fame state, settings, scheduler steps, notifications, player + admin + public reads | `app/law_crud.py` (`register_crime` L307-353, `apply_npc_crimes` L356-387, `attributes_of` L156-162, `admin_character` L1095), `app/law_core.py` (statuses L41-43 already reserve `pending_witness` / `unwitnessed`), `app/reputation_crud.py` (`apply_reputation` L363-450, `npc_kill_points` L453, `apply_npc_kill` L459-483), `app/main.py` (`update_npc_status` L4003-4073; public passport L2627; profile L2400), `app/law_pass.py` (`run_pass` ~L160), `app/econ_scheduler.py` (`run_scheduled_once` L81-94), `app/law_notify.py`, `app/law_api.py`, `app/reputation_api.py` (internal apply L190), `app/economy_sim_crud.py` (`region_card` L948), `app/models.py` (`LawCrime` L1267), `app/schemas.py`, new Alembic `040_*` |
| inventory-service | mask flag on items (column + schema validator + admin form) | `app/models.py` (`Items` L19-32, `EquipmentSlot` L355-369), `app/schemas.py` (flag validators L860-880), new Alembic `034_*` (pattern: `028_camp_backpack.py`) |
| locations-service | only if «мин. слава» quest gate / fame reward is built now (задел) | `app/models.py` `Quest` L489-505, `app/schemas.py` L1247-1280/L1370, `app/crud.py` `get_available_quests_for_npc` L5205 / `accept_quest` L5287, `app/reputation_read.py` `quest_gates` L159, `app/main.py` `complete_quest` L3422 (`_apply_quest_reputation` L3381/L3537); Alembic `056_*` |
| battle-service | **none required** (already sends `battle_id` + `killer_character_ids`; `battles.law_encounter_id` readable by SQL) | `app/main.py` L2701-2735 (NPC-death loop) |
| frontend | profile blocks, public fame, region «неспокойно», admin tabs, item form flag | see §2.9 |
| skills-service / character-attributes-service | none (read by raw SQL) | — |

### Existing Patterns
- character-service: sync SQLAlchemy, raw `text()` reads of other services' tables (precedent: `character_attributes`, `character_inventory`, `items`, `Locations`, `Regions`, `battles`), Pydantic v1, Alembic (`alembic_version_character`, last = `039_law`), settings = single-row tables (`law_settings`, `reputation_settings`), admin via `require_permission("reputation:read|manage|settings")` in `law_api.py` / `reputation_api.py`, private reads via `visibility.require_private_access`, randomness `secrets.SystemRandom()` (`law_crud.rng()` L79) with chance/roll logged in `law_log`.
- inventory-service: sync, Alembic (`alembic_version_inventory`, last = `033_auction_listing_region`). Boolean flags on `items` are the established way to mark a special kind of item (`is_backpack` on cloaks, `is_home_teleport` on scrolls, `is_elite_trophy`, `is_food`) with a root validator tying the flag to an `item_type`.
- locations-service: async (aiomysql), reads character-service tables by SQL (`reputation_read.py`).
- All write paths of FEAT-197/198 run in the **caller's transaction**, are idempotent by an event key + UNIQUE, and notify only **after commit** (sync pika, best effort).

### 2.1 The crime path today and where the witness roll goes

Flow: battle-service `_finalize_battle` (main.py L2701-2735) → for each defeated non-mob NPC `PUT /characters/internal/npc-status/{npc}` `{status:'dead', battle_id, killer_character_ids:[all chars of the winning team]}` → character-service `update_npc_status` (main.py L4003):
1. guard → `law_crud.knock_out_guard` (conditional KO, L390), else conditional `alive→dead` UPDATE (L4043-4046);
2. on a real transition: `reputation_crud.apply_npc_kill` (L4048) → per player killer `apply_reputation(action='npc_kill', idem_key='npc_kill:{npc}:{battle}:{killer}', delta=kill_points)` (with 20 % echo to the country);
3. `law_crud.apply_npc_crimes` (L4052) → per player killer `register_crime(crime_type npc_kill|guard_defeat, points=crime_weight(kill_points), floor=heavy_wanted if guard, key='crime:npc_kill:{npc}:{battle}:{killer}')`;
4. commit, then `publish_tier_changes` + `publish_wanted_changes`.

Other `register_crime` caller: jail escape success (law_crud.py L884, `points=0, floor=heavy_wanted`) — witnessed by definition (keep it always `reported`).

**Key finding: `register_crime` alone is NOT the right single insertion point for 2b**, although its docstring says so (L317-318). The reputation of the same kill is applied *before* it, by `apply_npc_kill`, so gating only `register_crime` would still apply reputation immediately, contradicting the brief («не замечен → репутация и розыск сейчас не меняются»). The roll must sit **in `update_npc_status` between the transition and both applies** — or, cleaner, in a new orchestrator `law_crud.npc_kill_consequences(db, npc, battle_id, killer_ids)` that replaces the two calls at L4048-4053:
- resolve `points = npc_kill_points(npc)`; if `points >= 0` (bandit +20 etc.) → **not a crime**: apply reputation at once exactly as now, no roll (fame source, see 2.5);
- if the battle is a guard encounter fight (`SELECT law_encounter_id FROM battles WHERE id=:b` IS NOT NULL) → always witnessed (current behaviour);
- else roll witnesses (one group roll per `(npc, battle)` — PM default), with the roll + chance stored;
- witnessed & not masked → `apply_npc_kill` + `apply_npc_crimes` unchanged;
- unwitnessed / masked → write the `law_crimes` rows with a non-applied status and a **snapshot of what to apply later**, skip both applies, raise region suspicion, add infamy (infamy also on witnessed).

**Deferred application can reuse the same functions idempotently:**
- Reputation: `reputation_crud.apply_reputation(db, character_id, region_id, action='npc_kill', idem_key='npc_kill:{npc}:{stamp}:{killer}', delta=<snapshot>, reason=…)` — exactly the key `apply_npc_kill` would have used, so a reveal racing a (hypothetical) direct apply is a silent `duplicate`. It takes `region_id` directly (no NPC lookup needed at reveal time). Note the `stamp` is `battle_id` or `t{YYYYmmddHHMMSS}` when no battle (L476) — the deferred row must store the exact key string, not re-derive it.
- Wanted: split `register_crime` into (a) insert row and (b) `_apply_crime_wanted(db, crime, floor, settings, levels)` (current L340-353). The reveal does a conditional `UPDATE law_crimes SET status='reported', resolved_at=:now WHERE id=:id AND status IN ('unwitnessed','masked')` → only rowcount==1 applies (idempotent across pass workers / staff clicks), then calls (b). `law_log` key `law:crime:{id}` (already unique) is a second guard.
- What must be snapshotted on the crime row because it can change before reveal: reputation delta (role weights / per-NPC override are admin-editable), the reputation idem key, the floor (`guard_defeat` → `heavy_wanted` — or recompute from `crime_type` at reveal), the masked flag, witness chance/roll, reveal deadline and next roll time. NPC name for the reputation journal reason can be read at reveal (NPC rows are not deleted on death; fallback «NPC #id»).
- `law_crimes.status` is `VARCHAR(20)` (no ENUM) and already indexed (`ix_law_crime_status`) → new statuses (`unwitnessed`, `masked`, `revealed`→reuse `reported`, `closed`) need no ALTER of a type; the reserved `CRIME_PENDING_WITNESS` is unnecessary because the roll is synchronous.
- Notifications on reveal: `reputation_notify.publish_tier_changes` + `law_notify.publish_wanted_changes` + a new «Ваше преступление раскрыто» notice — all after the pass item's commit.
- Edge: `characters` FK `ON DELETE CASCADE` on `law_crimes.character_id` → a deleted character's pending crimes vanish (matches «пропуск»). `apply_reputation` returns `skipped='npc'` for NPCs.

### 2.2 Location "type" for the witness base chance
- **No settlement/wilderness flag exists.** Closest fields (locations-service `models.py`):
  - `Locations.marker_type` ENUM `('safe','dangerous','dungeon','farm')` **NOT NULL default 'safe'** (L131); `Districts.marker_type` same ENUM, nullable (L92); `Locations.type` is only `location|subdistrict` (L125) — hierarchy, not semantics.
  - `Regions` has no type; `econ_regions` (character-service `models.py` L614) has `template_code` (economic profile: settlement noun like «город/деревня», `population`, `stability`) — region-level only.
- Important: NPC «Нападение» goes through `POST /battles/` (`useNpcAttack.ts` L42 → battle-service `create_battle_endpoint` L1018) which has **no safe-location check** (only `/pvp/attack` L5190 and `/pvp/forced-request` L1536 refuse `safe`). So NPC kills DO happen in `safe` locations (towns) — `marker_type` is usable: `safe` = settlement (high), `farm` = medium, `dangerous` = wild (low), `dungeon` = very low. Read by SQL from character-service exactly like `econ_core.SQL_NPC_PLACE` (L1151: `LEFT JOIN Locations l ON l.id = c.current_location_id`).
- Risk: `safe` is the column default, so locations an admin never classified count as "settlement". Acceptable (pre-beta, admin-editable); mention in the admin hint. A dedicated `Locations.witness_pct` override (nullable) would be an optional extension — not needed.

### 2.3 Inputs of the roll
- **Agility / luck:** `law_crud.attributes_of` (L156) reads raw `character_attributes.agility, luck`. The stored value already includes gear modifiers (inventory equip calls attributes `apply_modifiers`, which adds to the columns), but **not** the FEAT-195 conversion: caps apply to what a stat converts into (`character-attributes-service/app/stat_caps.py`, eff(x) = x ≤100; 100+(x−100)·0.5 ≤200; 150+(x−200)·0.25). FEAT-198's flee/escape chance uses raw values (its §L9 "caps apply naturally" is inaccurate — minor inconsistency, not a bug to fix here). For the witness roll use effective values: character-service has a Decimal twin `econ_core._effective_stat_dec` (L875, private, part of the byte-identical econ_core group) — either expose a public `effective_stat` there (touches 4 econ_core copies + `scripts/check_econ_copies.sh`) or add character-service as a 4th `stat_caps.py` copy to the `stat_caps` check group (L64-67). Architect decision; the second is cleaner.
- **Subclass:** stored in skills-service tables: latest `character_tree_progress` row whose `tree_nodes.node_type='subclass_choice'` with non-null `subclass_key`. Ready SQL in inventory-service `app/equipment_rules.py` ~L126-137 (`SELECT tn.subclass_key FROM character_tree_progress ctp JOIN tree_nodes tn ON tn.id = ctp.node_id WHERE ctp.character_id=:cid AND tn.node_type='subclass_choice' AND tn.subclass_key IS NOT NULL ORDER BY ctp.id DESC LIMIT 1`); official HTTP twin `GET /skills/internal/characters/{id}/subclass` (skills `main.py` L437). Keys (stable, never renamed — `skills-service/app/subclasses.py`): **`warrior_agent`** «Агент» (L140), **`rogue_assassin`** «Ассасин» (L200), **`rogue_trickster`** «Фокусник» (L229). Use the SQL (same transaction, no HTTP).
- **Party size:** `killer_character_ids` = every character of the winning team; `apply_npc_crimes` already filters `is_npc=0` (L375). Group size = that player count. In practice the UI «Нападение» sends 1 player vs the NPC (`useNpcAttack.ts`), but `POST /battles/` accepts teams up to `BATTLE_MAX_TEAM_SIZE`, so groups are possible.
- **Fame** (attacker's recognisability) — new state, see 2.5.
- Group roll + per-member modifiers: the roll is per `(npc, battle)`; with several attackers the architect must define how individual agility/subclass/mask combine (e.g. worst member = most visible, or average). Masks are naturally per member (a masked member is "unknown", an unmasked one is recognised).

### 2.4 Masks
- `items.item_type` is a MySQL **ENUM** (`head, body, cloak, belt, ring, necklace, bracelet, weapon, consumable, resource, scroll, misc, recipe, gem, rune, gathering_tool, furniture`, models L28-32). Changing it = ALTER on `items` (the FEAT-165 lock problem noted in the model comments L105-109 and in memory "Грабли миграций"). **Do not add a `mask` item_type / slot.**
- `equipment_slots.slot_type` ENUM includes `head` (L360-366). Recommended: boolean `items.is_mask` (NOT NULL, server_default 0), allowed only with `item_type='head'` (root validator like `is_backpack`→cloak in `schemas.py` L880). Migration pattern: `inventory-service/app/alembic/versions/028_camp_backpack.py` (`op.add_column('items', sa.Column('is_backpack', sa.Boolean(), nullable=False, server_default=sa.text('0')))`); next revision `034_item_mask` (≤ 32 chars). A mask therefore costs the helmet slot — a natural trade-off.
- "Wears a mask now" by SQL from character-service: `SELECT 1 FROM equipment_slots es JOIN items i ON i.id = es.item_id WHERE es.character_id = :c AND es.item_id IS NOT NULL AND i.is_mask = 1 LIMIT 1` (character-service already reads `items` / `character_inventory` by SQL: `crud.py` L2818, `economy_mint_crud.py` L473). Snapshot it on the crime row (brief: state at crime time). Equipment cannot change during a battle, so reading it at npc-status time (battle end) is equivalent.
- Touch points for the flag: inventory `models.py`, `schemas.py` (create/update/read + validator), frontend `ItemsAdminPage/ItemForm.tsx`, `itemFormRules.ts`, `CommonComponents/ItemTypeLine.tsx` (show «Маска»). photo-service mirror models do not need it.
- Deploy-order risk: if character-service's mask SQL runs before inventory `034` is applied → «Unknown column is_mask». Mitigate like the FEAT-198 lock readers: treat the error as "no mask" (or deploy together; migrations auto-run on start).

### 2.5 Fame and infamy
- **Positive sources available today:**
  - Quest completion: locations-service `complete_quest` (main.py L3422) → after commit `POST /characters/internal/reputation/apply` (`_apply_quest_reputation` L3381, called L3537, key `quest_reward:cq:{id}`), handled by `reputation_api.post_internal_apply` (L190). **Caveat:** it is skipped when the quest giver resolves to no region or `reputation_reward == 0` (L3493-3495) — so "fame from quests" hooked only on reputation would miss those quests; a dedicated fame call (or a fame field in the same internal request) is more robust.
  - Every reputation increase passes through `reputation_crud.apply_reputation` (L363): quest (+10 default), guild delivery (+2, cap 20/day/region, `economy_guild_crud.hand_in`), bandit kill (+20 via `apply_npc_kill`), staff adjust. A hook "origin row, `applied_delta > 0`, `actor_user_id is None`, not echo" there covers all automatic sources in one place; a per-action fame weight (or a global ratio) avoids guild spam dominating.
  - Titles exist (`titles` / `character_titles`, conditions `cumulative_stat|attribute|character_level|admin_grant`, crud.py L3355-3529) — a future `fame_tier` condition fits there (задел, not now).
- **Storage:** nothing exists. Options: columns on `characters` (`fame`, `infamy`) or a new `character_fame` table (+ log). The law/reputation precedent is separate tables + journal; ladder of named tiers like `law_levels` / `reputation_tiers` (fixed codes, editable names/thresholds).
- **Where fame is shown publicly:** `ProfilePage` (`/profile`) is **owner-only** (always the user's own selected character, ProfilePage.tsx L35). Other players see a character via (a) the public passport `GET /characters/{id}/public` (main.py L2627; `CharacterPublicStrangerResponse` schemas.py L137 — add `fame_tier_name` here, it is the stranger-safe base class) rendered by `CommonComponents/CharacterPassport` in `pages/CharactersPage/CharactersListPage.tsx` (detail modal ~L447); (b) `UserProfilePage/CharactersSection.tsx` cards (level + active title; data from user-service's user profile, which gets characters from character-service — `PublicProfileResponse`/`public_profile()` schemas.py ~L404-430 is the stranger projection of the full profile). Owner's private «Слухи в подполье» belongs in `ProfilePage/ReputationTab/ReputationTab.tsx` next to the FEAT-198 «Розыск» block, served by the private `GET /characters/{id}/law` (law_api.py L218, `require_private_access`) — extend `law_crud.player_state`.
- **«Мин. слава» gate pattern (FEAT-197):** `quests.min_reputation_tier VARCHAR(20)` (locations models L505) + schema validator against fixed codes (schemas L1248-1265) + list keeps gated quests with `locked_reason` (crud L5252-5281) + `accept_quest` 403 (crud L5308-5311) + `reputation_read.quest_gates` (raw SQL of character-service tables, L159) + frontend `QuestEditor.tsx` / `NpcQuestsModal.tsx`. A `min_fame_tier` column would copy this 1:1 (locations Alembic `056`, a small `fame_read` in locations-service reading the fame table by SQL). Brief says "задел" — the architect should decide whether to build the gate now or only the data model.

### 2.6 Region-level public state («подозрение края»)
- Public region card: `GET /characters/economy/regions/{region_id}/card` (economy_api.py L266, no auth) → `economy_sim_crud.region_card` (L948). It already returns non-economic fields **in both shapes** (participating and hidden): `has_bank`, `has_mint`, `events`, `caravans`, `guild_wants`. Adding `suspicion: {code, label}|null` there (both shapes) is the natural place; frontend `WorldPage/RegionEconomyCard.tsx` (rendered at WorldPage.tsx L686 and L858, next to `RegionReputationLine` L684/L856).
- Storage: no existing column. Either a new character-service table `region_suspicion(region_id PK, value, decay_at, updated_at)` with lazy linear decay (same maths as `law_core.effective_wanted/materialise`), or columns on `econ_regions` (but that row exists only for simulated regions — a separate table works for every region; recommended).
- Reveal chance "grows with suspicion" → read the effective region suspicion at roll time.

### 2.7 Scheduler hook
- `econ_scheduler.run_scheduled_once` (L81-94) calls `run_reputation_decay` then `run_law_pass` before the `tick_enabled` switch; the scheduler runs only when `ECON_TICK_ENABLED` is set (L27/L41) and not under pytest.
- `law_pass.run_pass` (law_pass.py ~L160): claim via `law_settings.pass_last_run_at` (55 s throttle, L41-48), steps tuple `(_expired_encounters, _lost_callbacks, _served_terms, _guard_recovery)`, each item its own transaction, errors logged per item. Add a step `_reveal_crimes`: select `status IN ('unwitnessed','masked') AND next_roll_at <= now` (index on `(status, next_roll_at)` advisable), lock row, roll (log chance/roll in `law_log`), reveal → apply (2.1) or advance `next_roll_at += 1 day`; `expires_at <= now` → `closed`. Daily cadence must come from a per-row `next_roll_at`, not from the pass interval. Suspicion decay: lazy (no step needed), like wanted.

### 2.8 Notifications
- `law_notify.py`: `Notice(user_id, message, ws_type, category, data)` + `publish([...])` after commit; categories `system` (mandatory) / `progress`; ws_types `law_encounter|law_jailed|law_released|law_wanted|law_resolved`. New ws_types e.g. `law_unseen` («Похоже, никто не видел…» — the only channel for the immediate hint, because battle-service ignores the npc-status response body), `law_revealed` (system: «Ваше преступление раскрыто»), `fame_tier` (progress). notification-service categories: `notification_categories.py` L25-30 (`progress`, `world`, … + `system`).

### 2.9 Admin areas to extend (frontend + API)
- `Admin/ReputationPage/ReputationPage.tsx` TABS (L14-18: «Ступени и общие», «Действия», «Роли НПС», «Закон») + `LawSettingsTab.tsx` → new settings (witness weights, reveal days/chance, mask effect, suspicion and fame ladders) either as a section of «Закон» or a new tab «Тень и слава»; list of unresolved crimes (new admin endpoint, `reputation:read`) with «Раскрыть»/«Закрыть дело» (`reputation:manage`, reason + `request_id`, like `/admin/law/characters/{id}/release` law_api.py L172).
- `Admin/CharactersPage/tabs/LawPanel.tsx` (crime type labels L30-33, crimes list from `law_crud.admin_character` L1095-1121) → show status/witness chance/roll/mask, infamy and fame numbers, per-crime reveal/close buttons.
- API clients: `src/api/law.ts`, `src/api/lawAdmin.ts`, `src/api/reputation.ts`, `src/api/regionEconomy.ts`; item form `ItemsAdminPage/ItemForm.tsx`.
- RBAC: no new permissions needed if reused (`reputation:read|manage|settings`, FEAT-198 L10); then `test_rbac_permissions.py` unchanged.

### Cross-Service Dependencies
```
battle-service ──HTTP──> character-service PUT /characters/internal/npc-status/{id}   (unchanged contract; response additive only)
locations-service ──HTTP──> character-service POST /characters/internal/reputation/apply (quest; fame hook here or a new field)
character-service ──SQL read──> Locations.marker_type, Regions (locations-service)
character-service ──SQL read──> character_attributes (attributes-service)
character-service ──SQL read──> equipment_slots + items.is_mask (inventory-service)   [NEW cross-owner read]
character-service ──SQL read──> character_tree_progress + tree_nodes (skills-service)  [NEW cross-owner read]
character-service ──SQL read──> battles.law_encounter_id (battle-service)
locations-service ──SQL read──> character-service fame table (only if «мин. слава» gate is built)
character-service ──pika──> general_notifications → notification-service
```

### DB Changes
- character-service Alembic `040_*` (≤ 32 chars, down_revision `039_law`):
  - `law_crimes` add: `reputation_delta INT NULL`, `reputation_key VARCHAR(191) NULL`, `wanted_floor INT NULL`, `masked TINYINT(1) NOT NULL DEFAULT 0`, `witness_chance_pct DECIMAL(5,2) NULL`, `witness_roll_pct DECIMAL(5,2) NULL`, `reveal_until DATETIME NULL`, `next_roll_at DATETIME NULL`, `reveal_attempts INT NOT NULL DEFAULT 0` (+ index `(status, next_roll_at)`); existing rows stay `reported`.
  - `law_settings` add witness/reveal/mask/suspicion/fame columns (or a separate single-row `shadow_settings`).
  - new `region_suspicion` (region_id PK, no FK to Regions), new fame/infamy storage (`character_fame` with FK `characters.id ON DELETE CASCADE` — remember: FK column needs its own index or leftmost of a composite), fame tiers table (fixed codes), optional `fame_log` (idempotency `UNIQUE(event_key)`).
- inventory-service Alembic `034_item_mask`: `items.is_mask BOOLEAN NOT NULL DEFAULT 0` (no ENUM change).
- locations-service Alembic `056_*` only if `quests.min_fame_tier` (and/or `fame_reward`) is built now.
- No battle-service, user-service migrations (no new permissions).

### Risks
- **Insertion point** (2.1): gating only `register_crime` leaves reputation immediate — must restructure `update_npc_status` / `apply_npc_kill`+`apply_npc_crimes` together. Existing FEAT-197/198 tests (`test_reputation_npc_kill.py`, `test_law_*`, `tests/law_world.py`) assume immediate application → they must force "witnessed" (settings with base 100 % / min=max, or an injectable RNG — `law_crud.rng()` is already a seam).
- **Determinism / double roll:** battle-service retries npc-status; the alive→dead transition guard already makes the second call a no-op, so the roll happens once. Store the roll on the crime row; never re-roll on duplicates.
- **Positive kills** (bandit +20) must bypass the roll; `points <= 0 and not floor` currently returns before any row is written (L322) — keep that.
- **Guard encounter fights** must stay always-witnessed (detect via `battles.law_encounter_id`); otherwise a player could escape the heavy wanted of a guard defeat by luck.
- **Cross-owner reads** of skills/inventory tables: tests run on SQLite with per-test schemas — fixtures must create `equipment_slots`, `items(is_mask)`, `character_tree_progress`, `tree_nodes`, `Locations.marker_type` (memory: "фикстура не той схемы" silent-failure pattern repeated 4 times — make the readers fail loudly in tests, or at least log, not swallow).
- **Deploy skew** inventory `034` vs character code (2.4) — tolerant reader or same deploy.
- **Stat caps**: FEAT-198 flee/escape use raw stats; using effective stats for witnesses only is inconsistent but correct per brief; reconciling flee/escape is a separate (tiny) decision.
- **`marker_type` default 'safe'** inflates witness chance in unclassified locations.
- **Fame inflation** from guild deliveries if every positive reputation delta feeds fame — needs a weight or a cap.
- **Public exposure:** fame is public (passport); infamy, crimes, suspicion numbers must never leak (only owner/staff; region shows a text state only). Unwitnessed crimes must not be visible to the player as a list either — otherwise they learn exactly when they are "safe"? (brief: the player gets only the «Никто не видел» hint and the reveal notice — confirm).
- econ_core / reputation_core byte-copy groups: only touched if `effective_stat` goes into econ_core (prefer the stat_caps copy route).

---

## 3. Architecture Decision (filled by Architect — in English)

Baseline: FEAT-197 (prod) + FEAT-198 (uncommitted working tree: character `039_law`, locations `055`, battle `009`). All paths relative to `services/`. PM decisions 1–7 in §1 are FINAL and implemented as written below.

### 3.0 Summary of key decisions

| # | Decision | Why |
|---|---|---|
| S1 | **One crime orchestrator** `shadow_crud.npc_kill_consequences(...)` replaces the two calls (`apply_npc_kill` + `apply_npc_crimes`) in `update_npc_status`. It classifies the kill, rolls witnesses **before** both reputation and wanted, and either applies both at once (today's behaviour) or writes a deferred crime snapshot. | §2.1: gating only `register_crime` would still apply reputation immediately. |
| S2 | **Not rolled, always "witnessed":** positive/zero kills (bandit +20 etc. — not a crime, reputation applied as now), fights of a guard **encounter** (`battles.law_encounter_id IS NOT NULL`), jail escapes (`register_crime` direct path, `reported`), and everything when `shadow_settings.witness_enabled = 0` (kill switch). A guard knocked out via plain «Нападение» **is** rolled (brief edge case «Стражник выбит скрытно — то же правило»). | PM decision 7 + brief. |
| S3 | **Deferred crime = the same `law_crimes` row** with new statuses `unwitnessed` / `masked` (later `reported` on reveal, `closed` on expiry/staff close) and a **snapshot** of everything needed to apply later (reputation delta + exact idem key + reason, wanted floor, mask flag, chance, roll, reveal deadline, next roll time). | `status` is VARCHAR(20) (no ENUM change); one table for staff lists; FEAT-198 left this extension point. |
| S4 | **Idempotent reveal**: conditional `UPDATE law_crimes SET status='reported' … WHERE id=:id AND status IN ('unwitnessed','masked')` → only rowcount = 1 applies; reputation via `apply_reputation` with the **stored** key (`npc_kill:{npc}:{stamp}:{killer}` — identical to the immediate path, so any double apply is a silent `duplicate`); wanted via the new split-out `apply_crime_wanted` (log key `law:crime:{id}` is the second guard). | Safe across pass workers, staff double clicks and races. |
| S5 | **Witness chance** = per-member individual chance; the **group chance = the highest individual chance (least stealthy member) + size bonus**, clamped 5–95 %. One roll per kill event `(npc, battle)`. Effective agility/luck through FEAT-195 caps via a **4th byte copy of `stat_caps.py`** in character-service. | PM decision 1; analyst recommendation for the stat copy. |
| S6 | **Mask** = `items.is_mask` boolean on `item_type='head'` items only (inventory `034_item_mask`, no ENUM change). Worn = SQL over `equipment_slots` + `items`, read at npc-status time (= crime time: equipment is frozen in battle). Missing column (deploy skew) → logged WARNING + "no mask". | PM decision 2; memory «ENUM на items». |
| S7 | **Region suspicion** = new `region_suspicion` row per region with **lazy linear decay** (reuse `law_core.effective_wanted` / `materialise` maths), public as a **text state only** on the region card. | Brief; same pattern as wanted. |
| S8 | **Daily reveal rolls** driven by per-row `next_roll_at` in a new `law_pass` step; chance grows with the region's effective suspicion and is multiplied down for masked crimes; after `reveal_days` without reveal the case is `closed` forever. | Brief; cadence independent of the 55 s pass interval. |
| S9 | **Renown** (one table `character_renown`: `fame` public, `infamy` hidden) + one journal `renown_log` (UNIQUE key = idempotency) + fixed-code ladders in `renown_tiers` (scale `fame` / `infamy`, editable name/threshold, fame tiers carry a `witness_pct`). Players see tier names only (no numbers), consistent with FEAT-197/198. | Brief + PM decision 4; precedent of fixed-code tier tables. |
| S10 | **Fame sources:** quest completion (new internal `POST /characters/internal/fame/apply`, default +5 or `quests.fame_reward`), positive automatic reputation × `fame_rep_ratio` 0.5 (hook in `apply_reputation`; `guild_delivery` uses `fame_guild_ratio` 0; `quest_complete` excluded — the quest has its own fame source), staff adjust. **Infamy:** every crime row (witnessed or not, incl. jail escape) in `register_crime`/`record_crime`. | PM decision 4; avoids double counting quests and guild farming. |
| S11 | **Quest gate `min_fame_tier` + `fame_reward`** built now (locations `056_quest_fame`), mirroring the FEAT-197 reputation gate 1:1 (`locked_reason`, accept 403). | PM decision 4. |
| S12 | **No new permissions**: settings `reputation:settings`, staff reveal/close/adjust `reputation:manage`, staff reads `reputation:read`. RBAC test unchanged. | Brief. |
| S13 | FEAT-198 flee/escape chance switched to **effective** agility/luck. | PM decision 6. |

### 3.1 Data model

#### character-service, Alembic `040_shadow_renown` (down_revision `039_law`; id 16 chars)

No FK to `Regions`/`Locations`. FK to `characters` with `ON DELETE CASCADE`; every FK column has its own index or is the leftmost column of an index/PK.

```sql
ALTER TABLE law_crimes
  ADD COLUMN reputation_delta    INT NULL,            -- snapshot of the kill reputation (negative); NULL = none
  ADD COLUMN reputation_key      VARCHAR(191) NULL,   -- EXACT apply_reputation idem key ('npc_kill:{npc}:{stamp}:{killer}')
  ADD COLUMN reputation_reason   VARCHAR(255) NULL,   -- staff-visible journal reason built at crime time
  ADD COLUMN wanted_floor        INT NULL,            -- heavy floor snapshot (guard_defeat), NULL = none
  ADD COLUMN masked              TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN witness_chance_pct  DECIMAL(5,2) NULL,   -- NULL for rows not rolled (escape, legacy)
  ADD COLUMN witness_roll_pct    DECIMAL(5,2) NULL,   -- NULL when forced witnessed
  ADD COLUMN reveal_until        DATETIME NULL,       -- created_at + reveal_days
  ADD COLUMN next_roll_at        DATETIME NULL,       -- next daily reveal roll
  ADD COLUMN reveal_attempts     INT NOT NULL DEFAULT 0,
  ADD COLUMN revealed_at         DATETIME NULL;
CREATE INDEX ix_law_crime_reveal ON law_crimes (status, next_roll_at);
-- existing rows stay 'reported'; statuses now: reported | unwitnessed | masked | closed

CREATE TABLE shadow_settings (                      -- single row id = 1
  id                            INT PRIMARY KEY,
  witness_enabled               TINYINT(1) NOT NULL DEFAULT 1,   -- 0 = every crime witnessed (2a behaviour)
  witness_base_safe_pct         DECIMAL(5,2) NOT NULL DEFAULT 70.00,  -- Locations.marker_type 'safe' (settlement)
  witness_base_farm_pct         DECIMAL(5,2) NOT NULL DEFAULT 45.00,
  witness_base_dangerous_pct    DECIMAL(5,2) NOT NULL DEFAULT 25.00,
  witness_base_dungeon_pct      DECIMAL(5,2) NOT NULL DEFAULT 15.00,
  witness_base_default_pct      DECIMAL(5,2) NOT NULL DEFAULT 50.00,  -- no location / unknown marker
  witness_stealth_per_point_pct DECIMAL(6,3) NOT NULL DEFAULT 0.100,  -- minus per effective (agility + luck) point
  witness_agent_pct             DECIMAL(5,2) NOT NULL DEFAULT 10.00,  -- warrior_agent «Агент»
  witness_assassin_pct          DECIMAL(5,2) NOT NULL DEFAULT 15.00,  -- rogue_assassin «Ассасин»
  witness_trickster_pct         DECIMAL(5,2) NOT NULL DEFAULT 15.00,  -- rogue_trickster «Фокусник»
  witness_mask_pct              DECIMAL(5,2) NOT NULL DEFAULT 10.00,  -- minus for a worn mask
  witness_group_per_extra_pct   DECIMAL(5,2) NOT NULL DEFAULT 10.00,  -- plus per attacker beyond the first
  witness_min_pct               DECIMAL(5,2) NOT NULL DEFAULT 5.00,
  witness_max_pct               DECIMAL(5,2) NOT NULL DEFAULT 95.00,
  reveal_days                   INT NOT NULL DEFAULT 3,               -- 1..30
  reveal_base_pct               DECIMAL(5,2) NOT NULL DEFAULT 15.00,
  reveal_per_suspicion_pct      DECIMAL(6,3) NOT NULL DEFAULT 0.400,  -- plus per effective suspicion point
  reveal_mask_factor_pct        DECIMAL(5,2) NOT NULL DEFAULT 50.00,  -- masked crime: chance × factor/100
  reveal_min_pct                DECIMAL(5,2) NOT NULL DEFAULT 1.00,
  reveal_max_pct                DECIMAL(5,2) NOT NULL DEFAULT 90.00,
  suspicion_max                 INT NOT NULL DEFAULT 100,
  suspicion_unwitnessed         INT NOT NULL DEFAULT 10,              -- per unwitnessed kill event
  suspicion_masked              INT NOT NULL DEFAULT 20,              -- per kill event with a masked member
  suspicion_decay_per_day       DECIMAL(8,2) NOT NULL DEFAULT 5.00,
  suspicion_uneasy_at           INT NOT NULL DEFAULT 20,              -- «В крае неспокойно»
  suspicion_alarmed_at          INT NOT NULL DEFAULT 50,              -- «Край встревожен»
  suspicion_fear_at             INT NOT NULL DEFAULT 80,              -- «Край охвачен страхом»
  infamy_ratio                  DECIMAL(6,3) NOT NULL DEFAULT 1.000,  -- infamy = max(min_gain, floor(wanted_points × ratio))
  infamy_min_gain               INT NOT NULL DEFAULT 10,
  fame_quest_default            INT NOT NULL DEFAULT 5,
  fame_rep_ratio                DECIMAL(6,3) NOT NULL DEFAULT 0.500,
  fame_guild_ratio              DECIMAL(6,3) NOT NULL DEFAULT 0.000,
  updated_at                    DATETIME NOT NULL
);

CREATE TABLE region_suspicion (
  region_id   INT PRIMARY KEY,                       -- no FK (locations-service table)
  value       INT NOT NULL DEFAULT 0,                -- materialised, 0..suspicion_max
  decay_at    DATETIME NULL,                         -- NULL at 0
  updated_at  DATETIME NOT NULL
);

CREATE TABLE character_renown (
  character_id INT PRIMARY KEY,                      -- FK characters.id ON DELETE CASCADE (PK = index)
  fame         INT NOT NULL DEFAULT 0,               -- >= 0, public as tier
  infamy       INT NOT NULL DEFAULT 0,               -- >= 0, owner + staff only
  updated_at   DATETIME NOT NULL
);

CREATE TABLE renown_tiers (                          -- fixed codes; name/min_value/witness_pct editable
  scale       VARCHAR(10) NOT NULL,                  -- 'fame' | 'infamy'
  code        VARCHAR(20) NOT NULL,
  sort_order  INT NOT NULL,
  name        VARCHAR(60) NOT NULL,
  min_value   INT NOT NULL,                          -- tier 1 = 0
  witness_pct DECIMAL(5,2) NOT NULL DEFAULT 0,       -- fame only: added to the witness chance (recognisability)
  PRIMARY KEY (scale, code),
  UNIQUE KEY uq_renown_tier_order (scale, sort_order)
);

CREATE TABLE renown_log (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  event_key     VARCHAR(191) NOT NULL,               -- 'fame:quest:cq:{id}', 'fame:rep:{rep key}', 'infamy:crime:{id}', 'renown:staff:{request_id}'
  character_id  INT NOT NULL,                        -- FK characters.id ON DELETE CASCADE (leftmost of ix)
  scale         VARCHAR(10) NOT NULL,
  source        VARCHAR(30) NOT NULL,                -- quest | reputation | crime | staff
  delta         INT NOT NULL,                        -- applied (after clamp at 0)
  value_after   INT NOT NULL,
  tier_before   VARCHAR(20) NOT NULL,
  tier_after    VARCHAR(20) NOT NULL,
  ref_id        BIGINT NULL,                         -- crime id / character_quest id
  reason        VARCHAR(500) NULL,                   -- staff only
  actor_user_id INT NULL,
  created_at    DATETIME NOT NULL,
  UNIQUE KEY uq_renown_log_key (event_key),
  KEY ix_renown_log_char (character_id, created_at)
);
```

**Seeds:** settings row with the defaults above; tiers:

| scale | code | sort | name | min_value | witness_pct |
|---|---|---|---|---|---|
| fame | nameless | 1 | Безвестный | 0 | 0 |
| fame | familiar | 2 | Знакомое имя | 50 | 2 |
| fame | known | 3 | Известный | 200 | 5 |
| fame | famous | 4 | Знаменитый | 600 | 10 |
| fame | legend | 5 | Легенда | 1500 | 15 |
| infamy | none | 1 | О вас не говорят | 0 | 0 |
| infamy | whispers | 2 | Шёпот в тавернах | 100 | 0 |
| infamy | rumored | 3 | О вас ходят слухи | 400 | 0 |
| infamy | notorious | 4 | Дурная слава | 1000 | 0 |
| infamy | dreaded | 5 | Имя, которое произносят шёпотом | 2500 | 0 |

Settings validation: percentages 0..100, every `min ≤ max`; per-point values 0..10; `reveal_days` 1..30; suspicion increments 0..`suspicion_max`, `suspicion_max` 1..10000, thresholds strictly increasing `1 ≤ uneasy < alarmed < fear ≤ max`; ratios 0..10; `fame_quest_default` 0..1000; `infamy_min_gain` 0..1000; tiers: exactly the 5 codes per scale, tier 1 `min_value = 0`, strictly increasing, `witness_pct` 0..50 (ignored for infamy). A change of `suspicion_decay_per_day` materialises all rows with `value > 0` at the old rate first (same pattern as wanted).

Rollback: `downgrade()` drops the 4 new tables, the index and the 11 columns. Legacy rows unaffected (`reported`).

ORM: `ShadowSettings`, `RegionSuspicion`, `CharacterRenown`, `RenownTier`, `RenownLog` + new `LawCrime` columns. Loader returns model defaults when the settings row is missing (tests/SQLite).

#### inventory-service, Alembic `034_item_mask` (down_revision `033_auction_listing_region`)

```sql
ALTER TABLE items ADD COLUMN is_mask BOOLEAN NOT NULL DEFAULT 0;   -- pattern 028_camp_backpack, NO item_type ENUM change
```
Rollback: drop the column.

#### locations-service, Alembic `056_quest_fame` (down_revision `055_region_jail_location`)

```sql
ALTER TABLE quests ADD COLUMN min_fame_tier VARCHAR(20) NULL,   -- one of the 5 fame codes, NULL = no gate
                   ADD COLUMN fame_reward  INT NULL;            -- NULL = shadow_settings.fame_quest_default; 0 = none
```
Rollback: drop both columns.

No battle-service / user-service migrations.

### 3.2 `shadow_core.py` (pure, character-service only — no copies)

- Constants: subclass keys `SUBCLASS_AGENT='warrior_agent'`, `SUBCLASS_ASSASSIN='rogue_assassin'`, `SUBCLASS_TRICKSTER='rogue_trickster'`; marker types `safe|farm|dangerous|dungeon`; scales `fame|infamy`; fixed tier codes; suspicion codes `calm|uneasy|alarmed|fear` with labels («В крае спокойно» — not shown, «В крае неспокойно», «Край встревожен», «Край охвачен страхом»); renown sources.
- `ShadowSettings` value object + `settings_from_row(row|None)`; `RenownTier`.
- `base_pct(marker_type, s)`.
- `member_chance(base, s, eff_agility: Decimal, eff_luck: Decimal, subclass_key, masked: bool, fame_witness_pct) -> Decimal` (unclamped):
  `base − (max(0,eff_agility)+max(0,eff_luck)) × stealth_per_point − subclass_pct − (masked ? mask_pct : 0) + (masked ? 0 : fame_witness_pct)` — **a masked member is anonymous, so their fame does not count**.
- `group_chance(member_chances, n_players, s) -> Decimal` = `clamp(max(member_chances) + group_per_extra × (n−1), min, max)`, 2 decimals.
- `reveal_chance(effective_suspicion, masked, s) -> Decimal` = `clamp((reveal_base + susp × per_suspicion) × (masked ? factor/100 : 1), reveal_min, reveal_max)`.
- `suspicion_state(value, s) -> (code, label)|None` (None for calm).
- `renown_tier_for(value, tiers)`, `renown_progress(value, tier, tiers) -> float 0..1` (top tier = 1.0).
- `infamy_gain(wanted_points, s)` = `max(infamy_min_gain, floor(wanted_points × infamy_ratio))`.
- `fame_from_reputation(action, applied_delta, s)` = 0 unless `applied_delta > 0`; `quest_complete` → 0; `guild_delivery` → `floor(delta × fame_guild_ratio)`; other → `floor(delta × fame_rep_ratio)`.
- Suspicion decay: reuse `law_core.effective_wanted` / `law_core.materialise` (identical maths; no new function).
- Rolls: `law_core.roll_succeeds(chance, rng)` (existing).

`law_core.chance(...)`: accept Decimal points (`max(0, _dec(agility)) + max(0, _dec(luck))` instead of `int(...)`); integer inputs give identical results.

### 3.3 Effective stats (stat_caps 4th copy)

- New byte copy `character-service/app/stat_caps.py`; canonical docstring (character-attributes-service) updated to list character-service as a copy, then re-copied byte-identically to battle, dungeon and character services; `scripts/check_econ_copies.sh` group `stat_caps` gets the 4th path (and the hint text mentions it).
- `law_crud.effective_attributes_of(db, character_id) -> (Decimal, Decimal)` = `effective_stat(agility)`, `effective_stat(luck)` of the raw `character_attributes` values (already include gear), quantised to 2 decimals.
- `flee_chance` / `escape_chance` use `effective_attributes_of` (PM decision 6). The witness roll uses it too.

### 3.4 Write path — the crime orchestrator (character-service `shadow_crud.py`, sync, caller's transaction, no commit)

**Readers (all parameterised `text()`, no exception swallowing except the one mask fallback):**
- `location_marker(db, location_id) -> Optional[str]`: `SELECT marker_type FROM Locations WHERE id=:l`.
- `subclass_of(db, character_id) -> Optional[str]`: the SQL from inventory `equipment_rules.py` (`character_tree_progress` ⨝ `tree_nodes`, `node_type='subclass_choice'`, latest).
- `wears_mask(db, character_id) -> bool`: `SELECT 1 FROM equipment_slots es JOIN items i ON i.id = es.item_id WHERE es.character_id=:c AND es.item_id IS NOT NULL AND i.is_mask = 1 LIMIT 1`, executed inside `db.begin_nested()`. **Only** an error whose message mentions the `is_mask` column (MySQL «Unknown column», SQLite «no such column») → `logger.warning(...)` + False. Anything else re-raises.
- `is_guard_encounter_battle(db, battle_id) -> bool`: `SELECT law_encounter_id FROM battles WHERE id=:b` not NULL.
- `fame_witness_pct(db, character_id, tiers)`: fame tier of `character_renown.fame` (0 without a row).

**`npc_kill_consequences(db, npc, *, battle_id, killer_ids, now=None) -> KillOutcome`** with `KillOutcome(tier_changes, wanted_changes, fame_changes, notices)`:
1. `players` = killer ids with `is_npc=0`, ≠ npc (same filter as today); `region_id = reputation_crud.location_region(npc.current_location_id)`; no players / no region → empty outcome.
2. `points = reputation_crud.npc_kill_points(db, npc)`; `is_guard`; `crime_points = law_core.crime_weight(points)`; `floor = heavy_wanted if is_guard else None`.
3. **Not a crime** (`crime_points <= 0 and not floor`): `reputation_crud.apply_npc_kill(...)` exactly as today (bandit positive → fame via the hook §3.6). Return.
4. **Forced** = `not witness_enabled` or `battle_id and is_guard_encounter_battle(battle_id)` → `witnessed=True`, `chance=100`, `roll=None`, masks ignored (the guards know who you are).
5. Otherwise, per player: `(eff_agi, eff_luck) = effective_attributes_of`, `subclass_of`, `wears_mask`, `fame_witness_pct`; `member_chance(...)` with `base = base_pct(location_marker(npc.current_location_id))`; `chance = group_chance(...)`; **one** roll `law_core.roll_succeeds(chance, law_crud.rng())`.
6. `stamp = battle_id or t{YYYYmmddHHMMSS}` (as today); per player:
   - `rep_key = f"npc_kill:{npc.id}:{stamp}:{killer}"`, `reason` = the string `apply_npc_kill` builds today, `crime_key = f"crime:npc_kill:{npc.id}:{stamp}:{killer}"` (both unchanged).
   - **Immediate** (`witnessed and (forced or not masked)`): `apply_reputation(action='npc_kill', idem_key=rep_key, delta=points, reason)` (factor the per-killer body of `apply_npc_kill` into `apply_npc_kill_for(db, npc, killer_id, region_id, points, stamp, now)` and reuse it) + `law_crud.register_crime(... status='reported', witness_chance/roll, reputation snapshot stored for staff)`.
   - **Deferred**: `register_crime(... status = 'masked' if (witnessed and masked) else 'unwitnessed', reputation_delta=points, reputation_key=rep_key, reputation_reason=reason, wanted_floor=floor, masked=<worn mask>, witness_chance_pct, witness_roll_pct, reveal_until=now+reveal_days, next_roll_at=now+24h)` — no reputation, no wanted now. Notice per player: unwitnessed → `law_unseen`; masked → `law_masked`.
7. **Suspicion** (once per kill event, only if any row was deferred): `add_suspicion(db, region_id, suspicion_masked if any masked-deferred else suspicion_unwitnessed, now)` (lock/ensure row, materialise, clamp to max, decay anchor as wanted).
8. Infamy is added inside `register_crime` (below) for **every** row, witnessed or not.

**`law_crud` changes (split of `register_crime`):**
- `record_crime(db, *, ..., status=CRIME_REPORTED, snapshot fields…) -> (crime|None, duplicate)`: today's steps 1–2 (positive/skip, NPC skip, duplicate pre-check, insert) + `renown_crud.add_infamy(db, character_id, infamy_gain(points), key=f"infamy:crime:{crime.id}", ref_id=crime.id)`.
- `apply_crime_wanted(db, crime, *, floor, settings, levels, now) -> WantedChange`: today's 2a block (lock wanted, `add_wanted`, `wanted_applied`, `resolved_at`, log `law:crime:{id}`).
- `register_crime(...)` keeps its signature (+ new optional kwargs) and = `record_crime` + `apply_crime_wanted` only when `status == 'reported'`. Jail escape and any other caller are unchanged → always reported.
- `apply_npc_crimes` is no longer called from `update_npc_status` (keep it only if other code/tests use it; otherwise delete — developer checks with grep).
- `CRIME_PENDING_WITNESS` is removed (unused; the roll is synchronous). New constants `CRIME_MASKED='masked'`, `CRIME_CLOSED='closed'`, `CRIME_OPEN=(unwitnessed, masked)`; log actions `reveal`, `reveal_fail`, `crime_closed`, `staff_reveal`, `staff_close`.

**`main.update_npc_status`**: replace the two calls with `outcome = shadow_crud.npc_kill_consequences(...)`; after commit `reputation_notify.publish_tier_changes(outcome.tier_changes)`, `law_notify.publish_wanted_changes(outcome.wanted_changes)`, `renown_notify`/`law_notify.publish(outcome.notices + fame notices)`. Response unchanged (additive only if anything). Battle-service retries stay no-ops through the conditional `alive→dead` / KO transition, so the roll happens exactly once.

### 3.5 Reveal (character-service `shadow_crud.py` + `law_pass.py`)

**`reveal_crime(db, crime_id, *, now, chance=None, roll=None, actor_user_id=None, reason=None) -> Optional[RevealResult]`** (caller's transaction):
1. `UPDATE law_crimes SET status='reported', revealed_at=:now WHERE id=:id AND status IN ('unwitnessed','masked')`; rowcount ≠ 1 → `None` (already revealed/closed — no-op).
2. Reload the row. If `reputation_delta` and `reputation_key`: `apply_reputation(character_id, region_id, action='npc_kill', idem_key=reputation_key, delta=reputation_delta, reason=reputation_reason)` (character gone → cascade deleted the row anyway; `skipped='npc'` harmless).
3. `apply_crime_wanted(crime, floor=wanted_floor, …)` → `WantedChange`.
4. `law_log` row: `reveal` (system, key `law:reveal:{id}`, chance/roll) or `staff_reveal` (key `law:staff_reveal:{id}`, actor + reason).
5. Return `RevealResult(tier_changes, wanted_change, user_id, region_name)`; the caller commits and then publishes tier/wanted changes + notice `law_revealed`.

**`close_crime(db, crime_id, *, now, actor_user_id=None, reason=None) -> bool`**: conditional `UPDATE … SET status='closed', resolved_at=:now WHERE id=:id AND status IN (open)`; log `crime_closed` (system, key `law:closed:{id}`) or `staff_close` (key `law:staff_close:{id}`). **No notification to the player** (PM decision 5: the player never learns which cases exist).

**`law_pass` step `_reveal_crimes`** (appended to the steps tuple; same claim/throttle; each item its own transaction; errors logged per item):
- `SELECT id FROM law_crimes WHERE status IN ('unwitnessed','masked') AND next_roll_at <= :now ORDER BY next_roll_at LIMIT 200` (index `ix_law_crime_reveal`).
- Per id: lock the row (`FOR UPDATE`; re-check status), `susp = effective suspicion of crime.region_id at now`, `chance = reveal_chance(susp, masked, s)`, `ok, roll = roll_succeeds(chance, law_crud.rng())`.
  - ok → `reveal_crime(..., chance, roll)`.
  - fail → `reveal_attempts += 1`, log `reveal_fail` (key `law:reveal_roll:{id}:{attempt}`, chance/roll), `next_roll_at += 24 h` (from the previous `next_roll_at`, so downtime catches up one roll per pass); if the new `next_roll_at > reveal_until` → `close_crime` (system).
- Commit, then notifications. With `reveal_days = 3`: rolls at +1 d, +2 d, +3 d, then closed.
- Suspicion decay needs no step (lazy).

### 3.6 Renown (character-service `renown_crud.py`)

- `load_renown_tiers(db, scale)`, `renown_of(db, character_id) -> (fame, infamy)` (0,0 without a row).
- `add_renown(db, *, character_id, scale, delta, source, event_key, ref_id=None, reason=None, actor_user_id=None, now) -> Optional[RenownChange]`: NPC → skip; duplicate pre-check on `renown_log.event_key` (+ UNIQUE as the hard guard) → None; ensure + lock the `character_renown` row; `new = max(0, old + delta)`; write log with tier before/after; return `RenownChange(character_id, user_id, scale, tier_before, tier_after, direction)` only when the tier changed. `add_fame` / `add_infamy` wrappers.
- **Reputation hook** (`reputation_crud.apply_reputation`, after the origin row is written): if `actor_user_id is None` and the origin `applied_delta > 0` → `gain = fame_from_reputation(action, applied_delta, s)`; `gain > 0` → `add_fame(source='reputation', event_key=f"fame:rep:{idem_key}")`. `ApplyResult` gets `fame_changes: list` (default empty); a helper `fame_changes_of(results)`. Callers that already publish tier changes also publish fame tier changes after commit: `update_npc_status` (via the orchestrator), `reputation_api.post_internal_apply`, the guild commit (ratio 0 by default, still wired), staff adjust (no fame — actor set). Reveal applies negative deltas → never fame.
- Quest fame: internal endpoint §3.7.
- Notifications (`law_notify.publish`, category `progress`, ws_type `fame_tier`) only for fame tier **up**: «Ваша слава растёт: теперь вы — «{tier}»». Infamy changes are silent (see open question Q3).

### 3.7 API contracts (character-service unless stated; Pydantic v1; Russian errors)

**Player / public**
- `GET /characters/{character_id}/public` (existing passport, no auth): `CharacterPublicStrangerResponse` + `fame_tier_code: str`, `fame_tier_name: str` (always present; «Безвестный» without a row). Inherited by the full response automatically. No number.
- `GET /characters/{character_id}/renown` (private: `visibility.require_private_access` — owner or staff with `characters:read`) → 200
  ```json
  {"fame": {"tier_code": "known", "tier_name": "Известный", "progress": 0.35, "next_tier_name": "Знаменитый"},
   "rumors": {"tier_code": "whispers", "tier_name": "Шёпот в тавернах"}}
  ```
  No numbers; no crime list (PM decision 5). 404 unknown character, 403 stranger.
- `GET /characters/renown/fame-tiers` (no auth; for editors and the profile legend) → `[{"code","name","sort_order"}]`.
- `GET /characters/economy/regions/{region_id}/card` (existing, no auth): both shapes get `"suspicion": {"code": "uneasy", "label": "В крае неспокойно"} | null` (null = calm). No numbers.

**Admin** (prefix `/characters/admin/shadow`, router `shadow_api.py`)

| Method/path | Permission | Body / response |
|---|---|---|
| `GET /settings` | `reputation:read` | `{settings:{…all shadow_settings fields}, fame_tiers:[{code,sort_order,name,min_value,witness_pct}], infamy_tiers:[{code,sort_order,name,min_value}]}` |
| `PUT /settings` | `reputation:settings` | same shape, validation §3.1; 400 with a Russian message |
| `GET /crimes?status=open\|unwitnessed\|masked\|closed\|all&region_id=&character_id=&page=1&page_size=20` | `reputation:read` | `{items:[{id, character_id, character_name, crime_type, region_id, region_name, location_id, location_name, victim_id, victim_name, status, masked, witness_chance_pct, witness_roll_pct, reputation_delta, wanted_points, wanted_floor, reveal_attempts, next_roll_at, reveal_until, created_at, resolved_at, revealed_at}], total}`; default `status=open`; `page_size ≤ 50` |
| `POST /crimes/{id}/reveal` | `reputation:manage` | `{reason: 3..500 trimmed, request_id: UUID}` → 200 `{message: "Преступление раскрыто", crime:{…row}}`; 404 unknown; 409 «Дело уже раскрыто или закрыто». Applies + notifies the player like the pass. |
| `POST /crimes/{id}/close` | `reputation:manage` | `{reason, request_id}` → 200 `{message: "Дело закрыто", crime}`; 404 / 409 as above; no player notification |
| `GET /regions/suspicion` | `reputation:read` | `[{region_id, region_name, value (effective), code, label}]` for rows with value > 0 |
| `POST /characters/{id}/renown-adjust` | `reputation:manage` | `{scale: "fame"\|"infamy", delta: int −10000..10000 ≠ 0, reason, request_id}` → `{scale, value_before, value_after, tier_before, tier_after, duplicate}`; key `renown:staff:{request_id}`; 400 for an NPC |

Existing `GET /characters/admin/law/characters/{id}` (`law_crud.admin_character`): each crime gets `status, masked, witness_chance_pct, witness_roll_pct, reputation_delta, wanted_floor, reveal_attempts, next_roll_at, reveal_until, revealed_at`; the response gets `renown: {fame, fame_tier_name, infamy, infamy_tier_name}` and `renown_log: [last 50]`.

**Internal** (`verify_internal_token`, nginx 403 on `/characters/internal/`)
- `POST /characters/internal/fame/apply` `{character_id: int, source: "quest", idempotency_key: str ≤191, points: Optional[int] 0..1000 (null = fame_quest_default), ref_id: Optional[int]}` → 200 `{applied: bool, duplicate: bool, tier_changed: bool}`; 404 unknown character; NPC → `applied=false`. Publishes a fame tier-up after its commit.
- `PUT /characters/internal/npc-status/{id}`: contract unchanged (battle-service unchanged).

**locations-service**
- Quest admin schemas `QuestCreate/QuestUpdate/QuestRead` + `min_fame_tier: Optional[str]` (validated against the fixed fame code tuple `FAME_TIER_CODES` in a new `fame_read.py`) + `fame_reward: Optional[int]` (0..1000).
- `fame_read.py` (async raw SQL): `fame_tier(session, character_id)` from `character_renown` + `renown_tiers WHERE scale='fame'`; `fame_gate_message(code, tiers)` → «Нужна слава: {name}». Read only when some listed quest has `min_fame_tier` (no read otherwise).
- `get_available_quests_for_npc`: a quest failing the fame gate stays listed with `locked_reason` «Нужна слава: Известный» (reputation reason takes precedence if both fail). `accept_quest`: 403 with the same text. Completion not gated.
- `complete_quest`: after the commit and next to `_apply_quest_reputation` (independent of the region): if `quest.fame_reward != 0` → `_apply_quest_fame(character_id, cq_id, quest.fame_reward)` → `POST /characters/internal/fame/apply` `{source:"quest", idempotency_key:"fame:quest:cq:{cq_id}", points: fame_reward|null, ref_id: cq_id}`, 1 retry, failure logged, never fails completion (same helper style).

**inventory-service**
- `Items.is_mask` (Boolean, default False); `is_mask: bool = False` in the item create/update/read schemas next to `is_backpack`; root validator: `is_mask` only with `item_type == 'head'` → 422/400 «Маской может быть только предмет для головы». Equip logic unchanged (a mask is a helmet).

### 3.8 Notifications (`law_notify.Notice`, after commit, best effort)

| ws_type | category | text |
|---|---|---|
| `law_unseen` | progress | «Похоже, никто не видел, что произошло» |
| `law_masked` | progress | «Свидетели видели лишь неизвестного в маске» |
| `law_revealed` | system | «Ваше преступление в крае «{region}» раскрыто — стража знает, кто это был» (+ the usual reputation tier / wanted notices) |
| `fame_tier` | progress | «Ваша слава растёт: теперь вы — «{tier}»» |

The frontend shows notifications generically; no ws-type special handling is required (optionally refresh the profile renown on `law_revealed` / `fame_tier`).

### 3.9 Frontend

All TypeScript, Tailwind + design-system classes, 360 px+ adaptive, no `React.FC`, every API error shown in Russian, no numbers of fame/infamy/suspicion for players.

- `src/api/shadow.ts` (player: `getRenown`, `getFameTiers`) and `src/api/shadowAdmin.ts` (settings, crimes, reveal, close, suspicion list, renown adjust). Extend `api/regionEconomy.ts` (`suspicion`) and the passport type (`fame_tier_code/name`), `api/lawAdmin.ts` types (crime fields, renown).
- `ProfilePage/ReputationTab/ReputationTab.tsx`: block «Слава» (tier name + progress bar + next tier name, short hint «Чем громче имя, тем легче вас узнать») and block «Слухи в подполье» (tier name, note «Видно только вам»), next to «Розыск».
- `CommonComponents/CharacterPassport/CharacterPassport.tsx`: line «Слава: {tier}».
- `WorldPage/RegionEconomyCard.tsx`: when `suspicion` is not null, a muted warning line with the label (both card shapes).
- `pages/LocationPage/NpcQuestsModal.tsx`: verify the existing `locked_reason` rendering covers «Нужна слава…» (no code change expected).
- Admin:
  - `Admin/ReputationPage/ReputationPage.tsx`: new tabs «Тень и слава» (`ShadowSettingsTab.tsx`: all settings grouped Свидетели / Раскрытие / Подозрение / Дурная слава / Слава, the two 5-tier tables, hint that unclassified locations count as «safe»; read-only without `reputation:settings`) and «Нераскрытые дела» (`UnresolvedCrimesTab.tsx`: filterable paged list, «Раскрыть» / «Закрыть дело» with a mandatory reason modal, buttons only with `reputation:manage`, `request_id` per submit; plus the regions-suspicion list).
  - `Admin/CharactersPage/tabs/LawPanel.tsx`: crime status labels («Замечено», «Не замечено», «В маске», «Закрыто»), chance/roll/mask columns, per-crime reveal/close for open rows, fame/infamy numbers + tiers, renown log, «Изменить славу / дурную славу» form with reason.
  - `ItemsAdminPage/ItemForm.tsx` + `itemFormRules.ts`: checkbox «Маска (скрывает лицо при преступлениях)» shown only for `head`; reset when the type changes. `CommonComponents/ItemTypeLine.tsx`: «Маска» for `is_mask`.
  - `AdminNpcsPage/QuestEditor.tsx`: «Мин. слава» select (from `GET /characters/renown/fame-tiers`, empty = без ограничения) and «Слава за задание» (placeholder «по умолчанию: 5», 0 = нет).

### 3.10 Security

- New player reads: `renown` private (owner/staff); public passport exposes only the fame tier name; region card only a text state; fame-tiers list has names only. Infamy, crime rows, chances, rolls, suspicion numbers never reach players.
- Admin: `require_permission` per §3.7; reason 3..500 trimmed; UUID `request_id`; actor recorded in `law_log` / `renown_log`; conditional status UPDATE makes reveal/close idempotent.
- Internal fame endpoint: internal token + nginx 403; `idempotency_key ≤ 191`; points bounded.
- Randomness server-only (`law_crud.rng()` = `secrets.SystemRandom`); chance + roll stored on the crime row and in `law_log`.
- Validation: settings bounds (§3.1), tier codes fixed sets (both services), `is_mask` only on head, quest `fame_reward` 0..1000, `page_size ≤ 50`, filters typed (ints / enum of statuses).
- SQL: parameterised `text()` only. No new nginx config; no new player write endpoints (no rate-limit change).

### 3.11 Data flow

```
Kill:   battle-service _finalize_battle → PUT /characters/internal/npc-status/{npc} {dead, battle_id, killer_ids}
          character-service TX: alive→dead (or guard KO) → shadow_crud.npc_kill_consequences
             ├─ not a crime → apply_reputation (+ fame hook)
             ├─ forced (guard encounter / switch off) or witnessed & unmasked → apply_reputation + register_crime(reported) + infamy
             └─ unwitnessed / masked → register_crime(unwitnessed|masked, snapshot) + infamy + region_suspicion += n
          COMMIT → pika: tier / wanted / law_unseen / law_masked / fame_tier
Reveal: econ scheduler → law_pass._reveal_crimes (next_roll_at <= now)
          TX per crime: lock, chance(suspicion, mask), roll → reveal_crime (conditional UPDATE → apply_reputation(stored key) + apply_crime_wanted)
                         or attempts+1 / next_roll_at += 1 d / closed after reveal_until
          COMMIT → pika: law_revealed + tier / wanted
Quest:  locations complete_quest COMMIT → POST /characters/internal/fame/apply {fame:quest:cq:N} → TX add_fame → COMMIT → pika fame_tier
Reads:  locations quest list/accept → SQL character_renown + renown_tiers (fame gate)
        character-service → SQL Locations.marker_type, character_attributes, equipment_slots+items.is_mask,
                            character_tree_progress+tree_nodes, battles.law_encounter_id
```

### 3.12 Rollout

- Migrations auto-run: character `040_shadow_renown`, inventory `034_item_mask`, locations `056_quest_fame`; ship in the **same deploy as FEAT-198** (both uncommitted; `040` depends on `039`).
- Order: inventory `034` ideally before character-service serves kills; skew is tolerated by the mask fallback (WARNING log, "no mask"). locations reads `character_renown` only for quests with `min_fame_tier` set (a column that exists only after `056`, set by admins after deploy) → no skew read. battle-service unchanged.
- Live at deploy: witnesses on (`witness_enabled=1`); everyone starts with fame/infamy 0, suspicion 0. Existing crimes stay `reported`. Kill switch = `witness_enabled=0` in the admin.
- Copies: `stat_caps` ×4 (CI guard), `econ_core` untouched, `reputation_core` untouched.
- Residual risks: (1) `marker_type` default `safe` makes unclassified locations "settlements" (admin hint); (2) quest fame lost if the internal HTTP fails twice (logged, key makes replay safe); (3) the «Никто не видел» hint tells the player the roll result (by design, brief).

### 3.13 Tests impact (existing FEAT-197/198 suites)

- Kill-path tests (`test_reputation_npc_kill.py`, `test_law_*.py`, `tests/law_world.py`) assume immediate application → force "witnessed" through the RNG seam: patch `law_crud.rng` to return an object whose `random()` is `0.0` (roll 0.00 < min 5 %) — provide a shared fixture/helper (e.g. `force_witnessed` in `law_world.py`/`conftest.py`); or set `witness_enabled=0` where the test is not about witnesses.
- SQLite schemas must include what the new readers query: `Locations.marker_type`, `equipment_slots`, `items(id, item_type, is_mask)`, `character_tree_progress`, `tree_nodes`, `battles.law_encounter_id` (memory «фикстура не той схемы»: readers fail loudly, so a missing table fails the test rather than silently passing).
- FEAT-198 flee/escape chance assertions recomputed for effective stats (identical for stats ≤ 100).

### 3.14 Open business questions (defaults applied — do not block; for user confirmation)

- **Q1 — Fame decay:** fame and infamy never decay (default). Alternative: slow decay like reputation.
- **Q2 — Quest reputation also feeding fame:** excluded (a quest gives only its direct +5 fame) to avoid double counting. Alternative: also × 0.5 of its +10 reputation.
- **Q3 — Infamy tier notifications:** none (owner just sees «Слухи в подполье» change). Alternative: a quiet «О вас заговорили в подполье» notice.
- **Q4 — Masked members' fame:** a masked member's fame does not raise the witness chance (anonymous). Alternative: fame always counts.
- **Q5 — Mask inside a guard-encounter fight:** ignored (always witnessed and identified).
- **Q6 — Default numbers** (bases 70/45/25/15, stealth 0.1 per point, subclass 10/15/15, mask −10, group +10, reveal 15 % + 0.4×suspicion, mask ×0.5, 3 days, suspicion +10/+20, decay 5/day, fame ladder 0/50/200/600/1500, infamy ladder 0/100/400/1000/2500) — all editable in the admin.
- **Q7 — Reveal and suspicion:** a reveal does not lower region suspicion (only time does). Alternative: subtract the crime's increment on reveal.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**All developer tasks: NO commits, NO pushes, NO `git add` (the user commits once at the end).** Backend: `python -m py_compile` on every modified file + the service test suite inside its container. Frontend: `npx tsc --noEmit` and `npm run build` inside the frontend container. User-facing text in Russian.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **character-service shadow core:** migration `040_shadow_renown` (§3.1: law_crimes columns + index, `shadow_settings`, `region_suspicion`, `character_renown`, `renown_tiers`, `renown_log`, seeds); ORM models; `shadow_core.py` (§3.2) incl. `law_core.chance` Decimal points; `stat_caps.py` 4th copy (canonical docstring updated, re-copied to all 4) + `scripts/check_econ_copies.sh`; `law_crud.effective_attributes_of` and effective flee/escape (§3.3); `register_crime` split into `record_crime` + `apply_crime_wanted` with infamy, new statuses/log actions (§3.4); `renown_crud.py` (§3.6) + fame hook in `apply_reputation` (`ApplyResult.fame_changes`); `shadow_crud.py` readers, `npc_kill_consequences`, suspicion, `reveal_crime`, `close_crime` (§3.4–3.5); rewire `update_npc_status`; notices in `law_notify` (§3.8). No commits/pushes/`git add`. | Backend Developer | DONE | `character-service/app/alembic/versions/040_shadow_renown.py`, `app/models.py`, `app/shadow_core.py`, `app/shadow_crud.py`, `app/renown_crud.py`, `app/stat_caps.py`, `app/law_core.py`, `app/law_crud.py`, `app/law_notify.py`, `app/reputation_crud.py`, `app/main.py`, `character-attributes-service/app/stat_caps.py`, `battle-service/app/stat_caps.py`, `dungeon-service/app/stat_caps.py`, `scripts/check_econ_copies.sh` | — | Migration up/down on MySQL, id ≤ 32, FK columns indexed, no ENUM change; `check_econ_copies.sh` passes; bandit kill → no roll, rep + fame; guard-encounter battle → always reported; unwitnessed/masked → no rep/wanted, snapshot stored with the exact keys, suspicion raised once per event, infamy on every crime incl. escape; group chance = max member + size bonus, clamped; repeated npc-status → no second roll; mask fallback only for the missing column (WARNING); py_compile passes. |
| 2 | **character-service API + pass:** `shadow_api.py` (admin settings/crimes/reveal/close/suspicion/renown-adjust, internal `fame/apply`, public `renown/fame-tiers`, private `{id}/renown`) exactly per §3.7; passport `fame_tier_code/name`; region card `suspicion` (both shapes); `law_crud.admin_character` crime fields + renown; `law_pass._reveal_crimes` (§3.5); fame-change publishing in `reputation_api.post_internal_apply` and the guild commit; router include. No commits/pushes/`git add`. | Backend Developer | DONE | `app/shadow_api.py`, `app/main.py`, `app/schemas.py`, `app/law_pass.py`, `app/law_crud.py`, `app/economy_sim_crud.py`, `app/reputation_api.py`, `app/economy_api.py` (guild commit, if it lives there) | 1 | Contracts per §3.7; RBAC per the admin table; reveal/close idempotent (second call 409, no double apply); the pass rolls once per `next_roll_at`, closes after `reveal_until`, runs with the econ tick disabled; no numbers / crime list in player payloads; notifications after commit; py_compile passes. |
| 3 | **inventory-service mask flag:** migration `034_item_mask`; `Items.is_mask`; schemas create/update/read + validator (head only). No commits/pushes/`git add`. | Backend Developer | DONE | `inventory-service/app/alembic/versions/034_item_mask.py`, `app/models.py`, `app/schemas.py` | — | Up/down clean; `is_mask` on a non-head item → validation error in Russian; existing item routes unchanged; py_compile passes. |
| 4 | **locations-service fame gate + reward:** migration `056_quest_fame`; `Quest` columns; schemas with code/bounds validation; `fame_read.py`; quest list `locked_reason` + accept 403; `_apply_quest_fame` after the completion commit (1 retry, never fails completion). No commits/pushes/`git add`. | Backend Developer | DONE | `locations-service/app/alembic/versions/056_quest_fame.py`, `app/models.py`, `app/schemas.py`, `app/fame_read.py`, `app/crud.py`, `app/main.py` | contract of 2 | Gated quest listed with «Нужна слава: …» and 403 on accept; no fame read when no quest is gated; completion calls the internal endpoint with key `fame:quest:cq:{id}` and `points` = `fame_reward`/null, skipped for 0; py_compile passes. |
| 5 | **Frontend player side:** `api/shadow.ts`; types for passport/region card; ReputationTab «Слава» + «Слухи в подполье»; CharacterPassport fame line; RegionEconomyCard suspicion line; verify NpcQuestsModal shows the fame `locked_reason`. No commits/pushes/`git add`. | Frontend Developer | DONE | `src/api/shadow.ts`, `src/api/regionEconomy.ts`, `ProfilePage/ReputationTab/ReputationTab.tsx`, `CommonComponents/CharacterPassport/CharacterPassport.tsx`, `WorldPage/RegionEconomyCard.tsx`, `pages/LocationPage/NpcQuestsModal.tsx` (only if needed) | 2, 4 | TS + Tailwind + design system; 360 px adaptive; no `React.FC`; no numbers shown; errors in Russian; tsc + build pass. |
| 6 | **Frontend admin:** Reputation admin tabs «Тень и слава» and «Нераскрытые дела»; LawPanel crime statuses/chance/roll/mask, reveal/close, renown numbers + adjust; ItemForm «Маска» (head only) + `itemFormRules.ts` + `ItemTypeLine.tsx`; QuestEditor «Мин. слава» + «Слава за задание». No commits/pushes/`git add`. | Frontend Developer | DONE | `src/api/shadowAdmin.ts`, `src/api/lawAdmin.ts`, `Admin/ReputationPage/ReputationPage.tsx`, `Admin/ReputationPage/ShadowSettingsTab.tsx`, `Admin/ReputationPage/UnresolvedCrimesTab.tsx`, `Admin/CharactersPage/tabs/LawPanel.tsx`, `ItemsAdminPage/ItemForm.tsx`, `ItemsAdminPage/itemFormRules.ts`, `CommonComponents/ItemTypeLine.tsx`, `AdminNpcsPage/QuestEditor.tsx` | 2, 3, 4 | Moderator: can reveal/close/adjust with a reason but settings are read-only; reason required; the mask checkbox only for head; tsc + build pass. |
| 7 | **QA character-service:** `shadow_core` units (member/group chance incl. clamps, subclass keys, mask, masked-fame anonymity, group bonus; reveal chance with suspicion + mask factor; suspicion state thresholds; infamy gain; fame-from-reputation per action; renown tiers/progress); orchestrator (bandit not rolled; guard-encounter forced; switch off; witnessed unmasked = immediate rep + wanted with unchanged keys; unwitnessed/masked snapshots; group: one roll, masked member deferred while unmasked applied; suspicion once per event; infamy for all incl. jail escape; duplicate npc-status no re-roll; mask column-missing fallback WARNING + other errors raise); reveal (pass success/fail/close after 3 rolls, catch-up, conditional idempotency, stored key → rep `duplicate` on replay, wanted floor for guard); staff reveal/close (RBAC 403 for editor/user, reason required, 409 second time, no player notice on close); renown (fame hook, guild ratio 0, quest excluded, internal fame endpoint idempotent, staff adjust); private renown 403/404, public passport tier only, region card text only, no numbers to players; settings validation; effective flee/escape; **update existing FEAT-197/198 tests** with the `force_witnessed` fixture and the new fixture tables; SQL-injection strings in filters/reason. | QA Test | DONE | `character-service/app/tests/test_shadow_*.py`, `test_renown_*.py`, `tests/conftest.py`, `tests/law_world.py`, existing `test_reputation_npc_kill.py`, `test_law_*.py` | 1, 2 | All new and existing tests pass in the container. |
| 8 | **QA inventory + locations + copies:** inventory `is_mask` validator (head ok, other types rejected, default false, read schema exposes it); locations fame gate (locked_reason, accept 403, reputation reason precedence, no read without gates), quest fame call (mocked HTTP: key/points/null default, skip on 0, retry once, failure does not fail completion), schema validation of `min_fame_tier`/`fame_reward`; `sh scripts/check_econ_copies.sh`. | QA Test | DONE | `inventory-service/app/tests/test_item_mask.py`, `locations-service/app/tests/test_quest_fame.py` | 3, 4 | All pass in their containers; the copies check passes. |
| 9 | **Docs:** `docs/services/character-service.md` (shadow tables, orchestrator, reveal step, endpoints), `inventory-service.md` (`is_mask`), `locations-service.md` (fame gate/reward), `docs/ARCHITECTURE.md` (tables, flow), `docs/ISSUES.md` (remove the FEAT-198 raw-stats inconsistency if listed). No commits/pushes/`git add`. | Backend Developer | DONE | `docs/…` | 1–4 | Docs match the implemented contracts. |
| 10 | **Final review:** code vs §3; cross-service contracts (character ↔ locations ↔ inventory ↔ battle unchanged); `check_econ_copies.sh`; py_compile + all affected test suites; tsc + build. **Live verification on localhost** (Chrome allowed): set a head item as mask; kill a merchant via «Нападение» in a `dangerous` location with witness settings forcing "unseen" → «Никто не видел» notice, no reputation/wanted change, region card «В крае неспокойно»; same with a mask and forced "seen" → «неизвестный в маске»; staff «Раскрыть» in «Нераскрытые дела» → reputation + wanted applied once and «раскрыто» notice; force `next_roll_at` in the past → the pass reveals or closes; witnessed unmasked kill → immediate as before; guard-encounter fight still witnessed; profile shows «Слава» and «Слухи в подполье» (no numbers), passport of another character shows only the fame tier; quest with `min_fame_tier` locked, completion raises fame; admin settings save; zero console errors; no numbers/crime lists in player network responses. | Reviewer | DONE | — | 1–9 | PASS only with automated results + live verification recorded in §5. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-04
**Result:** PASS

Scope: FEAT-199 changes on top of the uncommitted FEAT-198 tree (FEAT-198 regression covered by the full suites + live law flows below). No code changes were made by the reviewer.

#### Checks
- [x] Types match (Pydantic ↔ TS interfaces) — `renown.ts`, `shadowAdmin.ts`, `lawAdmin.ts`, passport/region-card types match `shadow_api` / `law_api` / `economy_sim_crud` payloads (verified live)
- [x] API contracts consistent (backend ↔ frontend ↔ tests); §3.7 paths/permissions as designed (`reputation:read|manage|settings`, no new permissions → RBAC test unchanged)
- [x] Cross-service: battle-service `npc-status` contract unchanged (additive `knocked_out_until` from FEAT-198 only); locations → `POST /characters/internal/fame/apply` (internal token, 1 retry, after commit, never fails completion); character-service SQL reads of `Locations.marker_type`, `equipment_slots`+`items.is_mask` (tolerant only to the missing column), `character_tree_progress`+`tree_nodes`, `battles.law_encounter_id`; locations SQL reads `character_renown`/`renown_tiers` only when a quest has `min_fame_tier`
- [x] Idempotency: reveal/close = conditional status UPDATE (2nd call 409), reputation re-applied with the stored `npc_kill:{npc}:{stamp}:{killer}` key, wanted log key `law:crime:{id}`; fame keys `fame:quest:cq:{id}` (replay → `duplicate:true`), `fame:rep:{idem}`, `infamy:crime:{id}`, `renown:staff:{request_id}`
- [x] Migrations: character `040_shadow_renown` (17 chars; FKs on `character_renown` PK / leftmost of `ix_renown_log_char`; no ENUM; downgrade drops all), inventory `034_item_mask` (add/drop column, no ENUM change), locations `056_quest_fame` (add/drop 2 columns); all applied on local MySQL (`alembic_version_*` = 040 / 034 / 056)
- [x] `stat_caps.py` ×4 byte-identical; `sh scripts/check_econ_copies.sh` — all copies identical
- [x] No stubs/TODO; Pydantic v1; sync character/inventory, async locations kept
- [x] Frontend: all touched files `.tsx/.ts`, no `React.FC`, no new SCSS/CSS, design-system classes, errors shown in Russian (toast + inline status on settings validation)
- [x] Security: player payloads carry tier names only (`/renown` → names + 0..1 progress; passport → `fame_tier_code/name`; region card → `{code,label}`; `/law` has no crime list); infamy owner/staff only; `/characters/internal/fame/apply` → 403 at the gateway, 401 without token inside the network; settings validated server-side (400 Russian), status filter whitelisted (422 on `x' OR 1=1`), reason 3..500 (422), all SQL parameterised `text()`
- [x] QA tasks 7–8 DONE, tests present for every new endpoint/flow

#### Automated Check Results
- [x] `python -m py_compile` — PASS (96 changed/new .py files)
- [x] `npx tsc --noEmit` (frontend container) — PASS, 0 errors
- [x] `npm run build` (frontend container) — PASS (built in 1m 5s; only the usual chunk-size warning)
- [x] pytest character-service — 8178 passed, 1 skipped
- [x] pytest locations-service (`--asyncio-mode=auto`) — 2738 passed, 3 skipped
- [x] pytest battle-service (`--asyncio-mode=auto`) — 1840 passed, 10 skipped
- [x] pytest inventory-service — 2382 passed, 1 skipped
- [x] pytest user-service — 771 passed, 5 skipped
- [x] pytest dungeon-service `test_econ_contract.py` + `test_feat175_entry.py` (+ `test_stat_caps_dungeon.py`) — 509 passed, 1 skipped (junit, exit 0)
- [x] `sh scripts/check_econ_copies.sh` — PASS
- [x] `docker compose config` — PASS
- [x] Live verification — PASS

#### Live Verification Results (http://localhost via gateway, Chrome, admin, character Ашари #763 at «Холм Эха» #197 `dangerous`, region Мэттанхейм #9, NPC merchant «Петя» #33)
- Admin «Тень и слава»: min 50 > max 10 → inline + toast «Шанс свидетелей: минимум больше максимума» (no request sent); min=max=0 → PUT 200, saved. API: `reveal_days=99` → 400 «Срок раскрытия: от 1 до 30 дней»; non-increasing fame thresholds → 400.
- Unwitnessed kill (real «Напасть» → battle 327 → battle-service → npc-status): crime `unwitnessed`, chance 0 / roll 54, snapshot −150 + key `npc_kill:33:327:763`; reputation / wanted unchanged; region suspicion 10; infamy +150; notification «Похоже, никто не видел, что произошло».
- Mask: ItemForm «Маска» checkbox only for «Шлем», reset when type → «Броня» and back; created item `is_mask=1`; API `is_mask` on `body` → 422 «Маской может быть только предмет для головы». Equipped; witness forced 100 → crime `masked` (chance 100), no rep/wanted, suspicion +20 → 30, notice «Свидетели видели лишь неизвестного в маске»; region card / world page `/world/region/9` shows «В крае неспокойно».
- «Нераскрытые дела»: both cases listed with chance/roll/mask/consequences/countdowns; reveal modal blocks empty reason; reveal with reason → status `reported`, reputation −150 (+20 % echo to 5 regions), wanted 150, `law:staff_reveal:1` with actor/reason, notices tier + «Ваше преступление в крае «Мэттанхейм» раскрыто…» + wanted; second reveal → 409 «Дело уже раскрыто или закрыто»; unknown id → 404.
- Law pass (`run_pass(claim=False)`): due masked crime → `reveal_fail` chance 13.50 (= (15+0.4·30)·0.5 ✔), attempts 1, next_roll +24 h; forced past `reveal_until` → `closed`, no player notification; a second pass does nothing.
- Witnessed unmasked kill (battle 329): `reported` at once, reputation −150 and wanted +150 immediately, suspicion unchanged, infamy +150.
- QuestEditor: «Мин. слава» = «Знакомое имя», «Слава за задание» = 60 → saved; list `locked_reason` «Нужна слава: Знакомое имя», accept 403 same text. LawPanel «Изменить славу» +50 with reason → fame 50, notice «Ваша слава растёт: теперь вы — «Знакомое имя»»; accept 200, complete 200 → `fame:quest:cq:9314` +60 → 110; internal replay → `applied:false, duplicate:true`.
- Profile «Репутация»: «Слава: Знакомое имя», bar 40 % (110 in 50..200 ✔), «Дальше: Известный»; «Слухи в подполье: О вас ходят слухи · Видно только вам»; «Розыск» block intact (FEAT-198). Passport (`/characters/list` → Ашари): «Слава — Знакомое имя», no rumours. Anonymous `/characters/763/renown` → 401.
- LawPanel crime list shows «Замечено / Закрыто / Раскрыто», маска, chance/roll, attempts; renown numbers + journal.
- Mobile 360 px iframe: «Тень и слава» and «Нераскрытые дела» — no horizontal overflow.
- Console errors on all visited screens: NONE; all shadow/renown requests 200 (only pre-existing 404 of `/characters/assets/avatars/avatar.png`).
- Not exercised live (covered by tests): guard-encounter fight forced witnessed; successful reveal by the pass; private `/renown` 403 for a non-staff stranger.
- Local data restored: full mysqldump taken before, restored after; Redis `battle:326..329:*` keys and Mongo `battle_snapshots`/`battle_logs` of test battles 326–329 deleted (ids will be reused after restore). The admin password hash was reset for login and is back to the dump value.

#### Notes (non-blocking)
- `post_reveal`, `post_renown_adjust`, `post_internal_fame` are `async def` with sync DB work — consistent with the already tracked debt «~93 эндпоинта character-service объявлены `async def`…» in `docs/ISSUES.md`.
- Pre-existing bugs met during the live run are already tracked in `docs/ISSUES.md` (MEDIUM «Нападение на воскрешённого NPC с нулевым здоровьем…» — Петя #33 had `current_health=0`, battle 326 stuck and was force-finished; «карточка персонажа в админке по прямой ссылке»). Nothing new added.

#### Issues Found
None.

---

## 6. Logging (filled by all agents — in Russian)

Running log of progress updates. Each agent writes brief Russian entries here.

```
[LOG] 2026-11-04 — PM: фича создана; пользователь ушёл отдыхать и поручил вести этапы до конца — решения по умолчанию приняты PM; запускаю анализ
[LOG] 2026-11-04 — Codebase Analyst: анализ завершён (раздел 2): бросок свидетелей должен стоять в update_npc_status до apply_npc_kill и apply_npc_crimes (иначе репутация применится сразу); отложенное раскрытие переиспользует apply_reputation и вынесенный шаг розыска из register_crime с теми же ключами; место — Locations.marker_type, подклассы — warrior_agent/rogue_assassin/rogue_trickster по SQL, маска — флаг items.is_mask на шлеме (без ENUM), подозрение края — в публичной карточке края, раскрытие — шаг law_pass; есть открытые вопросы
[LOG] 2026-11-04 — PM: на 6 вопросов аналитика приняты решения по умолчанию (§1); запускаю архитектора
[LOG] 2026-11-04 — Architect: спроектировано 10 задач (4 backend, 2 frontend, 2 QA, документация, ревью): оркестратор преступления вместо двух вызовов в update_npc_status, отложенный снимок в law_crimes и идемпотентное раскрытие, формула свидетелей по marker_type с эффективными статами (4-я копия stat_caps), маска items.is_mask, подозрение края, тайная дурная слава и публичная слава со ступенями, порог «мин. слава» у заданий; 9 API-контрактов, 3 миграции (character 040, inventory 034, locations 056); 7 открытых вопросов с решениями по умолчанию
[LOG] 2026-11-04 — Backend Developer: задача 3 готова — inventory 034_item_mask (items.is_mask, только для головы, «Маской может быть только предмет для головы»; при смене типа в PUT флаг сбрасывается); миграция up/down/up на MySQL чистая; тест головы миграций обновлён на 034; набор inventory 2333 passed
[LOG] 2026-11-04 — Backend Developer: задача 4 готова — locations 056_quest_fame (min_fame_tier, fame_reward), fame_read.py (чтение character_renown/renown_tiers только при наличии порога, без строк — сид-лестница), «Нужна слава: …» в списке (причина репутации приоритетнее) и 403 при принятии, _apply_quest_fame после коммита (2 попытки, ключ fame:quest:cq:{id}, пропуск при 0); миграция up/down/up чистая; два старых теста подправлены под новый POST; набор locations 2612 passed
[LOG] 2026-11-04 — Backend Developer: задачи 1–2 выполнены (character-service): миграция 040_shadow_renown (вверх/вниз/вверх на локальной MySQL), shadow_core/shadow_crud/renown_crud/shadow_api, оркестратор убийства вместо apply_npc_kill+apply_npc_crimes (apply_npc_crimes удалён), отложенный снимок и идемпотентное раскрытие, шаг law_pass._reveal_crimes, слава/дурная слава, подозрение края в карточке края, слава в паспорте, 4-я копия stat_caps; бегство/побег на эффективных статах; старые тесты убийств переведены на фикстуру force_witnessed; полный набор тестов character-service зелёный
[LOG] 2026-11-04 — Backend Developer: отклонения от §3 (мелкие): add_renown возвращает RenownResult (поле change = RenownChange или None) — нужно для ответа staff-правки; apply_npc_crimes удалён (других вызовов нет); «сильное» подозрение (suspicion_masked) берётся, если среди отложенных есть участник в маске (в т.ч. незамеченный); у принудительно «замеченных» witness_chance_pct = 100, roll = NULL; столбец Locations.marker_type в тестах добавлен в мир rep_world, а не в conftest (конфликт с тестами экономики); фильтр списка дел дополнительно принимает status=reported. Тесты: 7917 passed, 1 skipped
[LOG] 2026-11-04 — QA Test: задача 8 готова — inventory test_item_mask.py (49 тестов: маска только на голове, сообщение на русском, флаг в создании/правке/чтении admin+internal, публичная карточка без флага, смена типа сбрасывает флаг, миграция 034 вверх/вниз/вверх) и locations test_quest_fame.py (126 тестов: «Нужна слава: …» в списке и 403 при принятии, порог без региона, приоритет причины репутации, неизвестный код = без порога, пустые ступени → сид-лестница, без порогов слава не читается, валидация кодов/наград с инъекциями, вызов fame/apply после коммита с ключом fame:quest:cq:{id}, points null/число, 0 = без вызова, ретрай только 5xx/сеть, сбой не ломает сдачу, миграция 056); полные наборы: inventory 2382 passed / 1 skipped, locations 2738 passed / 3 skipped; check_econ_copies.sh — все копии идентичны; багов не найдено
[LOG] 2026-11-04 — Backend Developer: задача 9 готова — документация по коду: character-service.md (новый раздел «Shadow»: миграция 040, модули, формула свидетелей, оркестратор, отложенные дела и шаг раскрытия, подозрение края, слава/дурная слава, API, уведомления, 4-я копия stat_caps; поправлены разделы FEAT-197/198 — register_crime разделён, статусы law_crimes, эффективные статы бегства/побега, 5-й шаг прохода, паспорт и карточка края), inventory-service.md (items.is_mask, 034), locations-service.md (056, fame_read, порог «Нужна слава», _apply_quest_fame), ARCHITECTURE.md (таблицы, потоки, список копий), character-attributes-service.md (копия stat_caps); в ISSUES.md записи про сырые статы не было — не трогал
[LOG] 2026-11-04 — Frontend Developer: задача 5 готова — api/renown.ts (fetchRenown, fetchFameTiers; файл назван renown.ts по указанию PM вместо shadow.ts), во вкладке «Репутация» профиля блоки «Слава» (ступень, полоска, следующая ступень, без чисел) и «Слухи в подполье» («Видно только вам»), строка «Слава» в паспорте (fromCharacterPublic, кроме NPC), строка подозрения края в карточке края (обе формы, «неспокойно» — золотом, сильнее — красным); NpcQuestsModal выводит locked_reason как есть — «Нужна слава: …» покрыт без правок; уведомления общие, правок не нужно; tsc и build в контейнере проходят
[LOG] 2026-11-04 — Frontend Developer: задача 6 готова — api/shadowAdmin.ts (настройки, дела, раскрыть/закрыть, подозрение краёв, правка славы, публичные ступени славы), типы lawAdmin.ts (поля снимка дела, renown, renown_log); в админке «Репутация» вкладки «Тень и слава» (все настройки по группам, флаг броска свидетелей, две лестницы по 5 ступеней; без reputation:settings — только просмотр) и «Нераскрытые дела» (подозрение краёв с числами; дела с фильтрами статус/край/ID персонажа, страницы по 20, обратный отсчёт до броска и закрытия; «Раскрыть»/«Закрыть дело» только с reputation:manage, через окно с обязательной причиной и новым request_id на каждую отправку); в карточке персонажа «Закон»: статусы «Замечено/Не замечено/В маске/Закрыто/Раскрыто», шанс/бросок/маска/попытки, раскрыть/закрыть по открытым делам, слава и дурная слава с числами, журнал славы, форма «Изменить славу / дурную славу» с причиной; новые записи журнала закона (раскрытие, закрытие); ItemForm — галочка «Маска» только для головы (сброс при смене типа, в payload is_mask только для head), ItemTypeLine — «Маска»; QuestEditor — «Слава за задание» (плейсхолдер «по умолчанию: 5», 0..1000) и «Мин. слава» (ступени из GET /characters/renown/fame-tiers, пусто = без ограничения); tsc и build в контейнере проходят (вместе с файлами задачи 5)
[LOG] 2026-11-04 — QA Test: задача 7 готова — 261 новый тест в character-service: test_shadow_core.py (формулы свидетелей/раскрытия/подозрения/славы, валидация настроек, миграция 040 против ORM), test_shadow_kill.py (оркестратор: база по marker_type, эффективные статы с капом, подклассы, маска, слава, группа — один бросок по слабейшему + размер, границы 5–95; всегда «замечено» для бандита/боя со стражей/выключателя/побега; отложенный снимок с теми же ключами; подозрение один раз на событие; дурная слава на каждое преступление; повторный npc-status без второго броска; запасной путь без столбца is_mask, прочие ошибки откатывают всё), test_shadow_reveal.py (идемпотентное раскрытие/закрытие, шаг law_pass: ежедневный бросок, шанс от подозрения, маска ×0.5, закрытие после 3 неудач, догон после простоя, сбой одного дела не мешает другим; стафф: RBAC, причина, 404/409, без уведомления при закрытии), test_shadow_api.py (настройки, список дел, подозрение краёв, правка славы с повтором request_id, приватная слава без чисел, паспорт — только ступень, карточка края — только текст, SQL-инъекции), test_renown_fame.py (источники славы, внутренний эндпоинт задания, уведомления только о росте славы); помощник tests/shadow_world.py; RabbitMQ и HTTP замоканы; реальных багов не найдено; полный набор character-service: 8178 passed, 1 skipped
[LOG] 2026-11-04 20:20 — Reviewer: начал проверку; снят полный дамп локальной БД
[LOG] 2026-11-04 20:30 — Reviewer: автоматические проверки зелёные (py_compile 96 файлов; character 8178, locations 2738, battle 1840, inventory 2382, user 771, dungeon 509 passed; копии идентичны; tsc и build в контейнере проходят; compose config ок)
[LOG] 2026-11-04 20:40 — Reviewer: живая проверка на localhost пройдена: незамеченное убийство через «Напасть», маска (ItemForm → надета → «неизвестный в маске»), подозрение края на карте, раскрытие стаффом (один раз, 409 на повтор), шаг law_pass (провал броска, закрытие без уведомления), замеченное убийство сразу, порог «Нужна слава» и слава за задание, профиль/паспорт без чисел, 0 ошибок в консоли; новых багов нет (встреченные уже в ISSUES.md)
[LOG] 2026-11-04 20:50 — Reviewer: локальные данные восстановлены из дампа, тестовые бои вычищены из Redis/Mongo; проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

**Статус: DONE (2026-11-04), ревью PASS.** Решения по бизнес-вопросам принимал PM (пользователь поручил вести этапы до конца) — на подтверждение пользователю; все числа правятся в админке.

### Что сделано
- Убийство мирного NPC проходит бросок свидетелей: база по типу локации (безопасная 70 %, ферма 45, опасная 25, данж 15) − ловкость/удача (с капом) − подкласс (Агент 10, Ассасин/Фокусник 15) − маска 10 + слава; группа — самый заметный участник +10 за каждого лишнего; 5–95 %. Бандиты, бой со стражей, побег из тюрьмы — всегда «замечено»; есть общий выключатель.
- Не замечено → репутация/розыск отложены, «Похоже, никто не видел…», растёт подозрение края («В крае неспокойно / встревожен / охвачен страхом» на карточке края). Раз в сутки бросок раскрытия (15 % + подозрение, у маски вдвое меньше), через 3 дня дело закрыто навсегда. Раскрытие применяет последствия ровно один раз.
- Маска — галочка у предметов головы: свидетели видят «неизвестного в маске», последствия откладываются.
- «Слухи в подполье» (дурная слава) — копится от всех преступлений, видна только владельцу и стаффу.
- Слава — публичная (паспорт + профиль): задания (+5 или своё значение), положительная репутация ×0.5, гильдия 0; ступени Безвестный → Знакомое имя → Известный → Знаменитый → Легенда; повышает шанс, что узнают. Порог «Нужна слава: …» у заданий.
- Админка: «Тень и слава», «Нераскрытые дела» (раскрыть/закрыть с причиной), подозрение краёв, слава/дурная слава в карточке персонажа. Бегство/побег «Закона» считаются по эффективным статам.

### Оставшиеся риски / follow-up
- Локации без выставленного типа считаются безопасными (высокий шанс свидетелей) — стоит разметить типы.
- Новые админ-/внутренние эндпоинты async с синхронной БД (как уже записано в ISSUES).
- Деплой вместе с FEAT-198: миграции character 039→040, inventory 034, locations 055→056, battle 009.
