# FEAT-151: Редизайн вкладок профиля (Навыки, Отряд, Сбор, Задания, Бои, Крафт, Титулы)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-07-17 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Продолжение редизайна профиля персонажа (после FEAT-148 главная, FEAT-149 вкладка «Персонаж»).
Нужно привести 7 вкладок страницы `/profile` к новому дизайну из Claude Design мокапа:
**Навыки, Отряд, Сбор, Задания, Бои, Крафт, Титулы**.

Источник дизайна (распакованный HTML мокапа):
`/tmp/claude-1000/-home-dudka-chaldea/dcfe6743-aef7-43e7-b245-05377ea53dc4/scratchpad/CharacterProfile.dc.html`

Карта секций мокапа (строки файла):
- SKILLS TAB — 265–338 (карточки навыков: пипсы уровня /4, чипы энергия/мана/КД, бейдж «перк», фильтр по типу, кнопка «Дерево навыков», счётчик, чип очков перков)
- QUESTS TAB — 340–473 (master-detail: журнал слева, детали справа; фильтры по типу; задачи с прогресс-барами; награды; «Сдать задание» / «Отказаться»)
- PARTY TAB — 539–739 (3 состояния: участник / лидер / без отряда; карточки участников; «Пригласить с локации»; входящие приглашения; создание отряда)
- GATHERING TAB — 741–778 (3 карточки навыков сбора: ранг /5, XP-бар, текущие бонусы, превью след. ранга)
- BATTLES TAB — 780–897 (активный бой: очередь ходов + HP/MP союзников и врагов; 4 стат-плитки; чипы-фильтры тип/результат; строки истории; пагинация)
- TITLES TAB — 899–927 (фильтры Все/Полученные/Закрытые; карточки с редкостью, статусами Активен/Получен/Закрыт)
- CRAFT TAB — 929–1041 (рейл профессий с рангами; карточка профессии с пилюлями рангов; секции механик; сетка рецептов с материалами have/need)

**Из мокапа берём расположение элементов и композицию, но:**
- стили — только наша дизайн-система (`docs/DESIGN-SYSTEM.md`, токены `tailwind.config.js`, классы `@layer components` из `index.css`, паттерн `PanelShell` из FEAT-149);
- иконки — только существующие в проекте (`src/assets/icons/equipment/*`, `lucide-react`, картинки навыков/предметов с бэкенда), НЕ инлайн-SVG из мокапа;
- данные — реальные данные проекта (см. решения ниже), плейсхолдерные сущности мокапа (роли «нужен лекарь», перк-ветки и т.п.) не выдумываем.

Вкладки «Перки», «Логи персонажа» и прочие страницы НЕ трогаем. Таб-бар (`ProfileTabs.tsx`) не меняем.

### Решения пользователя по рассинхронам (уже согласовано)
- [x] **Отряд** → **Обогатить бэкенд**: party-API должен отдавать класс, уровень, HP/MP участников (через character-service / character-attributes-service). Роли (ДПС/Лекарь) в игре не существуют — вместо чипа роли показываем чип класса; «нужен лекарь» в приглашениях опускаем.
- [x] **Бои** → **Полная карточка активного боя**: подтянуть состояние боя из battle-service (участники обеих сторон, HP/MP, очередь ходов, локация/ход) — новый или расширенный endpoint.
- [x] **Навыки** → **Расширить список API**: `GET /skills/characters/{id}/skills` должен дополнительно отдавать базовые `cost_energy`, `cost_mana`, `cooldown` для карточек списка.
- [x] **Крафт** → **Рейл всех профессий**: показывать все 4 профессии как в мокапе; активная — выбранная персонажем, остальные затемнены, клик по чужой предлагает смену профессии (существующая модалка смены с предупреждением о потере прогресса).

### Бизнес-правила
- Вся текущая функциональность вкладок сохраняется (сдача/отказ от заданий, создание/роспуск/покидание отряда, приглашения, аватар отряда, крафт, заточка, сокеты, трансмутация, экстракция, переплавка, смена профессии, выбор/снятие титула, пагинация боёв, фильтры).
- Титулы: сохраняем прогресс-бары условий у закрытых титулов и бейджи XP-наград (в мокапе их нет, но это ценные существующие фичи); добавляем фильтры Все/Полученные/Закрытые из мокапа; редкости — реальные (common/rare/legendary).
- Задания: переводим в master-detail макет (журнал слева / детали справа), на мобильных — одна колонка.
- Все новые/изменённые компоненты — TypeScript + Tailwind, без React.FC, адаптивность от 360px, ошибки API показываются пользователю по-русски.

### Edge Cases
- Отряд: участник со статусом `invited` (ещё не принял); участник офлайн/на другой локации; отряд из 1 человека; персонаж без отряда и без приглашений.
- Бои: активного боя нет; бой завершился между запросами (404/гонка); история пуста; фильтр без результатов.
- Навыки: у персонажа 0 навыков; навык без стоимости (0/0/0).
- Крафт: профессия ещё не выбрана (экран выбора профессии — оформить в стиле мокапа, в мокапе его нет); рецептов нет; материалов не хватает.
- Титулы: 0 титулов; фильтр «Закрытые» пуст.
- Сбор: максимальный ранг (нет next_rank).

### Вопросы к пользователю (если есть)
- [x] Все вопросы по рассинхронам заданы и отвечены (см. «Решения пользователя»).

### Дополнение от пользователя (2026-07-17, после Review #1)
- [x] **Обновить дизайн-систему: затемнение блоков как в макете.** Фоновый цвет блоков берём из макета (`rgba(9,10,16,.62)` у панелей) вместо текущего светло-серого `rgba(35,35,41,0.9)` — повышаем контраст. Обновить токен `site.bg` и все места дизайн-системы, где зашит старый цвет (gray-bg, `--gray-background` и т.п.). Непрозрачные поверхности (модалки/дропдауны) — тёмный вариант из макета (`rgba(14,15,21,.98)`), не полупрозрачный.
- [x] **Глобальное затемнение фона** — добавить НЕагрессивный градиент-оверлей поверх background-main.png (в макете: `linear-gradient(180deg, rgba(5,6,10,.55) → .82 → .96)`; взять мягче, без сильного затемнения книзу).
- [x] **Основной цвет фона** — из макета: `#05060a` (вместо текущего) как base background-color под картинкой.
- [x] **Проверки адаптива в браузере больше НЕ выполнять** (эмуляция 360px и т.п.) — ни в задачах, ни в ревью. Десктопная live-проверка остаётся.
- [x] **Горизонтальный скролл на мобильных слишком высокий** — уменьшить высоту горизонтального скроллбара для мобильных экранов (в макете у `tabs-sc` высота 3px; сделать медиазапрос для `gold-scrollbar`-классов). Входит в T14.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| party-service (port 8014) | enrich member payload (class, level, HP/MP) — response-shape only | `services/party-service/app/crud.py`, `app/schemas.py`, (`app/main.py` unchanged routes) |
| battle-service (port 8010) | active-battle preview: reuse `GET /battles/{id}/state` or add a light preview endpoint; expose `location_id` | `services/battle-service/app/main.py`, `app/schemas.py`, `app/redis_state.py` (read-only) |
| skills-service (port 8003) | add base `cost_energy`/`cost_mana`/`cooldown` to list items — additive | `services/skills-service/app/crud.py` (`serialize_character_skill`), `app/schemas.py` (`CharacterSkillRead`) |
| frontend | redesign of 7 profile tabs | `services/frontend/app-chaldea/src/components/ProfilePage/*` (see Frontend map below) |

No changes needed in character-service / character-attributes-service — they already expose all required data (or the data is readable from shared tables).

### 2.1 Party API enrichment (class, level, HP/MP of members)

**Service:** party-service — NOT battle-service. Nginx routes `location /party/` → `party-service_backend` (upstream port **8014**), `docker/api-gateway/nginx.conf:68, :293`; `/party/internal/` is blocked externally with 403 (`nginx.conf:289`). Frontend `src/api/squads.ts` builds an axios client with `baseURL "/party"` (relative → goes through the gateway) + Bearer token from localStorage (`squads.ts:6-30`).

**Patterns:** sync SQLAlchemy + Pydantic v1; character data is read via **raw SQL from the shared `characters` table** (`services/party-service/app/crud.py:14-52`, comment says this mirrors battle-service's approach); cross-service mutations use **sync `httpx`** (`app/main.py:46-71` — active/passive XP to attributes-service). Auth: every player endpoint uses `Depends(get_current_user_via_http)` (JWT validated by HTTP call to user-service) + `_require_owned` ownership check (`app/main.py:36-43`). Alembic present: `app/alembic/versions/001_initial_party.py`.

**Current schemas** (`services/party-service/app/schemas.py`):
- `MemberOut` (:30-42): `character_id, user_id, name, avatar, is_leader, status ("invited"|"accepted"), current_location_id`
- `PartyOut` (:45-53): `id, name, avatar, leader_character_id, members[]`
- `IncomingInvite` (:56-61): `party_id, party_name, party_avatar, leader_character_id, leader_name`

**Where member data is assembled:** `crud.build_party_out()` (`app/crud.py:104-125`) — fetches members, then ONE batched raw-SQL `IN (...)` query via `get_characters_map()` (`crud.py:33-52`, selects `id, user_id, current_location_id, name, avatar` from `characters`). Used by `/mine`, create, invite, respond, patch (`app/main.py:104,243,333,375,446`). Invites list assembles per-invite with `get_character_info` in a loop (`main.py:262-274`) — N+1 already exists there but N = pending invites (small).

**Data sources for enrichment:**
- **level**: `characters.level` (`services/character-service/app/models.py:52`) — same shared table party-service already SELECTs from; just add the column to the two raw-SQL queries in `crud.py`.
- **class name**: `characters.id_class` (`models.py:38`) JOIN `classes.name` (`classes` table: `id_class`, `name` — `services/character-service/app/models.py:89-93`). One LEFT JOIN in the same batched query.
- **current/max HP and mana**: table `character_attributes` keyed by `character_id` (`services/character-attributes-service/app/models.py:13,18-27`): `current_health, current_mana, max_health, max_mana` (also energy/stamina if wanted). Two options, both already precedented:
  - (a) **direct shared-table read** — one more batched raw-SQL `IN` query on `character_attributes` (matches party-service's existing pattern for `characters`); zero HTTP calls, no N+1;
  - (b) **HTTP** `GET http://character-attributes-service:8002/attributes/{character_id}` → `CharacterAttributesResponse` incl. `current_health/max_health/current_mana/max_mana` (`services/character-attributes-service/app/main.py:328-336`, `app/schemas.py:41-51`). Endpoint has **no auth**. This would be 1 call per member (party max 4, `PARTY_MAX_SIZE=4` in `app/config.py:17`) — acceptable but slower; party-service currently has no async httpx, only sync.
  - Choice (a) vs (b) is an Architect decision; (a) is consistent with how this exact service already reads cross-owned data.
- **N+1 assessment:** members are max 4; a single extra batched query (option a) keeps it O(1) queries. Invites list needs no HP/MP per the mock (only leader name), no change required there.

**Backward compatibility:** all new `MemberOut` fields are additive/Optional → safe. Consumers of `PartyOut`: frontend `squads.ts` only (grep found no other service calling `/party/mine`); internal endpoints (`/party/internal/*`) use separate schemas, untouched.

### 2.2 Active battle full state (battle-service)

**Patterns:** fully async (aiomysql + Motor + redis.asyncio), Pydantic v1, Celery. Alembic **present** (`services/battle-service/app/alembic/versions/001_initial_baseline.py` … `003_add_battle_history.py`) — note: CLAUDE.md §7 still lists battle-service as "without Alembic", stale.

**State storage** (`services/battle-service/app/redis_state.py`):
- Redis key `battle:{id}:state` (:46-47) — JSON: `turn_number, deadline_at, next_actor, first_actor, turn_order[], location_id, first_cycle, active_effects, participants{pid → {character_id, team, hp/mana/energy/stamina, max_*, fast_slots, cooldowns, …}}` (:131-166).
- Redis key `battle:{id}:snapshot` (cache, :22) with MongoDB fallback (`save_snapshot`/`load_snapshot`) — snapshot participants built once at battle start by `build_participant_info()` (`app/main.py:180-227`): `{participant_id, character_id, name, avatar, attributes (full, incl. max_health/max_mana/agility…), skills, fast_slots, equipment_durability}`. Name/avatar come from character-service `GET /characters/{id}/profile` (`app/character_client.py`); class is **NOT** in the snapshot.

**Existing REST endpoints:**
- `GET /battles/character/{character_id}/in-battle` (`app/main.py:2791-2800`) — **no auth**, returns `{in_battle, battle_id}`. Already used by BattlesTab.
- `GET /battles/{battle_id}/state` (`app/main.py:1308-1382`) — **JWT + participant-ownership check** (verifies one of the user's characters is in the battle, :1318-1337). Returns `{snapshot, runtime}`; runtime: `turn_number, deadline_at, current_actor, next_actor, first_actor, turn_order, total_turns, last_turn, participants{pid → hp/mana/energy/stamina/cooldowns/fast_slots/team/character_id}, active_effects, is_paused, paused_reason, rewards`. Note: unlike the internal/spectate variants, this runtime does **not** include `max_*` per participant (:1363-1375) — frontend BattlePage derives max values from `snapshot[].attributes`. Used by BattlePage for initial state + polling (`src/components/pages/BattlePage/BattlePage.tsx:440`); WS `/battles/ws/{battle_id}` then pushes `battle_state` messages (`src/hooks/useBattleWebSocket.ts:137`, message types :53-77).
- `GET /battles/{battle_id}/spectate` (`app/main.py:1385-1470`) — JWT + "has a character at the battle's location" check; runtime DOES include `max_*`. Frontend: `fetchBattleSpectateState` (`src/api/battles.ts:128-135`).
- `GET /battles/internal/{battle_id}/state` (`app/main.py:1248-1294`) — no JWT, blocked at nginx (`/battles/internal/` → 403, `nginx.conf:226`).
- `GET /battles/history/{character_id}` (`app/main.py:3482`) — history + stats + pagination (already used by BattlesTab).

**Everything the preview card needs is already in `GET /battles/{id}/state`:** combatant name+avatar (snapshot), hp/mana + max (snapshot attributes / runtime), side (`team`), turn order (`runtime.turn_order` — participant ids, map to names via snapshot), current turn (`turn_number`), current actor. **Gap:** `location_id` is stored in Redis state (`redis_state.py:139`) and on the `battles` MySQL row (used at `main.py:1402`), but is NOT returned by `/state`; location *name* would additionally need a locations-service lookup. Also the payload is heavy (full attributes + skills arrays per participant) — fine for the battle page, arguably heavy for a profile preview card. Architect should decide: reuse `/state` as-is (owner is always a participant, auth fits) + optionally add `location_id`/`location_name` to runtime (additive, safe), vs. add a dedicated lightweight `GET /battles/{battle_id}/preview`.

**Race/edge:** battle can finish between `/in-battle` and `/state` → `/state` returns 404 ("State not found") — frontend must handle it (listed in Edge Cases).

### 2.3 Skills list enrichment (skills-service)

**Patterns:** async SQLAlchemy (aiomysql), Pydantic v1, Alembic present (`app/alembic/versions/…`).

**Handler:** `GET /skills/characters/{character_id}/skills` → `list_skills_for_character` (`services/skills-service/app/main.py:331-337`), **no auth** on this read. Response model `List[CharacterSkillRead]` (`app/schemas.py:203-211`): `character_skill_id, skill_id, character_id, level, free_perk_points, selected_perk_ids, reset_available_at, skill{id,name,skill_type,skill_image}`.

**Where costs live:** base `cost_energy, cost_mana, cooldown` are columns on the `skills` table (`app/models.py:24-26`); perk deltas `delta_cost_energy/delta_cost_mana/delta_cooldown` on `skill_perks` (`app/models.py:82-84`). There is no `skill_levels` table — costs do not scale with level; only selected perks modify them. `GET /skills/{skill_id}/resolved` (`app/main.py:372-389`, `crud.resolve_character_skill` `app/crud.py:594-651`) computes base + Σ perk deltas, clamped ≥0.

**Minimal change:** the list query already `selectinload`s the `skill` relation (`crud.py:313-323`), so `serialize_character_skill()` (`crud.py:326-346`) can emit `cs.skill.cost_energy / cost_mana / cooldown` with **zero extra queries**. Add the 3 fields either to nested `CharacterSkillSummarySkill` (`schemas.py:193-200`) or flat on `CharacterSkillRead`. Per the user decision these are the **base** values (perk-adjusted values remain in the detail modal via `/resolved`; computing resolved values in the list would require loading each skill's perk pool — unnecessary). Fields are additive → backward compatible.

**Consumers of the endpoint (all tolerate additive fields):**
- frontend: `SkillsTab.tsx:69`, `SkillTreeView/SkillUpgradeModal.tsx:63`, `AdminNpcsPage/NpcStatsEditor.tsx:149`, `api/adminCharacters.ts:188`
- battle-service: `app/skills_client.py:80,104` (`character_skills()` — denormalizes `skill_type`/`skill_image`, ignores extra keys)

### 2.4 Frontend verification

Tab file map confirmed under `services/frontend/app-chaldea/src/components/ProfilePage/`: `SkillsTab/`, `PartyTab/`, `GatheringTab/`, `QuestLogTab.tsx` (single file, 11.7K), `BattlesTab/`, `CraftTab/` (13 files), `TitlesTab/`; shared `PanelShell.tsx` (2.2K), `ProfileTabs.tsx` (do not touch), `constants.ts`. Condensed inventory:
- **SkillsTab** — `SkillsTab.tsx` + `ResolvedSkillCard.tsx`; list from `GET /skills/characters/{id}/skills`; detail modal fetches `/skills/{id}/resolved` + `/skills/{id}`; links to `/skill-tree`.
- **PartyTab** — `PartyTab.tsx` (357 lines) + `api/squads.ts` (getMyParty, getIncomingInvites, getPlayersOnLocation, createParty, invitePlayer, respondInvite, leaveParty, disbandParty, updateParty, uploadSquadAvatar). States: none/member/leader; max 4.
- **GatheringTab** — redux `gatheringSlice`; 3 skills, ranks /5, bonuses + next_rank; already matches the mock.
- **QuestLogTab** — `GET /locations/quests/active?character_id=`, `POST /locations/quests/{id}/complete|abandon`; uses `BASE_URL` from `src/api/api.ts` (`QuestLogTab.tsx:5,58,80,100`) → goes through the gateway.
- **BattlesTab** — `BattlesTab.tsx` (432 lines); `GET /battles/history/{id}` (stats+pagination), `GET /battles/character/{id}/in-battle`.
- **CraftTab** — `craftingSlice` + `profileSlice`; 4 professions; sections per profession; change-profession modal exists (reuse for the profession rail click).
- **TitlesTab** — `TitlesTab.tsx` (344 lines) + `api/titles.ts`; rarities common/rare/legendary; keep condition progress bars + XP badges.
- Icons: `src/assets/icons/equipment/*`, `lucide-react` (`package.json:29`, v1.7.0 — old version, limited icon set; verify needed icons exist before use). Battle WS hook: `src/hooks/useBattleWebSocket.ts`.
- `squads.ts` uses relative baseURL `/party` (gateway); `BattlePage.tsx:440` uses `BASE_URL_BATTLES`; QuestLogTab uses `BASE_URL` — all through the nginx gateway.

### Cross-Service Dependencies (relevant to this feature)

- party-service → shared `characters` table (raw SQL); → character-attributes-service (`httpx`, XP endpoints; option (b) would add `GET /attributes/{id}`); → `character_attributes` shared table (option (a), new read).
- battle-service → character-attributes-service (`fetch_full_attributes`), character-service (`/characters/{id}/profile`), skills-service, inventory-service — all at battle START (snapshot); the preview endpoint reads only Redis/Mongo/MySQL, no new cross-service calls needed.
- skills-service list endpoint is consumed by battle-service `skills_client.py` — additive fields safe.
- frontend → gateway `/party/`, `/battles/`, `/skills/`, `/locations/`, `/characters/`, `/attributes/` (all routed in `docker/api-gateway/nginx.conf:81-300`).

### DB Changes

**None.** All three enrichments are response-shape only. Alembic status of touched services: party-service DONE, skills-service DONE, battle-service DONE (despite stale CLAUDE.md §7 note) — no migrations required either way.

### Risks

- **Party member HP/MP source choice** (shared-table read vs HTTP) — inconsistency risk if the wrong pattern is picked; both precedents exist in party-service. → Architect to decide; document choice.
- **`/battles/{id}/state` payload weight** for a profile preview (full snapshot with attributes + skills per participant) → acceptable to reuse, or add a light `preview` endpoint; if reusing, frontend must read max HP/MP from `snapshot[].attributes` because participant-facing runtime omits `max_*` (`main.py:1363-1375`).
- **Location name for the battle card**: `/state` returns neither `location_id` nor a name → additive runtime field (`location_id` is already in Redis state) + name lookup strategy needed (locations-service or omit name).
- **Battle finished race** between `/in-battle` and `/state` → handle 404 gracefully (already in Edge Cases).
- **skills list endpoint has no auth** (pre-existing; matches "most endpoints unauthenticated" tech debt) — additive fields don't worsen it.
- **lucide-react is v1.7.0** (very old) — icon availability must be checked per icon; upgrading is out of scope unless user approves.

### Open Questions for Architect

1. Party HP/MP: direct batched read of `character_attributes` (option a, recommended-by-pattern) or HTTP calls to attributes-service (option b)?
2. Battle preview: reuse `GET /battles/{battle_id}/state` (+ additive `location_id`/`location_name` in runtime) or a new lightweight `GET /battles/{battle_id}/preview`?
3. Skills costs: nested inside `skill{}` object or flat on the list item? (Nested keeps skill-owned data together; flat matches `ResolvedSkillRead` naming.)

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Resolutions of the Analyst's open questions

1. **Party HP/MP source → option (a): batched shared-table read of `character_attributes`.**
   Rationale: party-service already reads cross-owned data from the shared `characters` table via batched raw SQL (`crud.py:33-52`) — this is the service's established pattern, explicitly modeled on battle-service. Option (a) keeps `build_party_out()` at O(1) queries (2 batched `IN (...)` selects total), adds zero HTTP hops and no new failure mode (attributes-service downtime cannot break `/party/mine`). Option (b) would add up to 4 sync HTTP calls per request to an unauthenticated endpoint for data that lives one `SELECT` away in the same DB.

2. **Battle preview → new lightweight `GET /battles/{battle_id}/preview`.**
   Rationale: `/state` omits `max_*` in participant runtime and omits `location_id`/name entirely, and its payload carries full per-participant attributes, skills and fast-slot arrays — heavy and awkward for a profile card (frontend would have to dig max values out of `snapshot[].attributes` and we'd still need an additive `/state` change for location). A compact DTO endpoint reads the same Redis state + snapshot, applies the exact same JWT + participant-ownership check as `/state` (`main.py:1318-1337`), and resolves the location name with one shared-DB `SELECT name FROM Locations` (battle-service already raw-SQL-reads shared tables, e.g. `characters` at `main.py:1407`). No new cross-service HTTP calls.

3. **Skills costs → nested inside `skill{}` (`CharacterSkillSummarySkill`).**
   Rationale: `cost_energy/cost_mana/cooldown` are columns of the `skills` table — skill-owned **base** data; the nested summary object already mirrors skill columns (`id/name/skill_type/skill_image`). Placing them flat on `CharacterSkillRead` would falsely suggest per-character *resolved* values (that is `/skills/{id}/resolved`'s job). All consumers (frontend + battle-service `skills_client.py`) tolerate extra keys inside `skill`.

---

### 3.1 API Contracts

#### 3.1.1 party-service — enriched `MemberOut` (response-shape only, additive)

Applies to every endpoint that returns `PartyOut` (built by `crud.build_party_out()`): `GET /party/mine`, `POST /party`, `POST /party/{id}/invite`, `POST /party/{id}/respond`, `PATCH /party/{id}`. No route/auth changes. Invites list (`IncomingInvite`) is unchanged.

Schema change (`app/schemas.py`, Pydantic v1):

```python
class MemberOut(BaseModel):
    character_id: int
    user_id: int
    name: Optional[str] = None
    avatar: Optional[str] = None
    is_leader: bool
    status: str                      # "invited" | "accepted"
    current_location_id: Optional[int] = None
    # FEAT-151 — additive enrichment (all Optional → backward compatible):
    level: Optional[int] = None
    class_name: Optional[str] = None
    current_health: Optional[int] = None
    max_health: Optional[int] = None
    current_mana: Optional[int] = None
    max_mana: Optional[int] = None
```

Implementation (in `app/crud.py`, keep O(1) queries):
- Extend `get_characters_map()` (and `get_character_info()` for consistency):
  `SELECT c.id, c.user_id, c.current_location_id, c.name, c.avatar, c.level, cl.name AS class_name FROM characters c LEFT JOIN classes cl ON cl.id_class = c.id_class WHERE c.id IN :ids`
- New batched helper `get_attributes_map(db, character_ids)`:
  `SELECT character_id, current_health, max_health, current_mana, max_mana FROM character_attributes WHERE character_id IN :ids`
- `build_party_out()` merges both maps into members.

**Nullability decision:** a missing `character_attributes` row (attributes are created on character approval; a stale/aberrant character may lack one) or missing class ⇒ the corresponding fields are `null`. Frontend hides HP/MP bars and the class chip when `null` (never renders `0/0`).

`GET /party/mine` → `200` example:

```json
{
  "id": 3,
  "name": "Хранители Зари",
  "avatar": "https://s3.twcstorage.ru/.../party3.webp",
  "leader_character_id": 12,
  "members": [
    {
      "character_id": 12, "user_id": 5, "name": "Артур",
      "avatar": "https://s3.../12.webp", "is_leader": true,
      "status": "accepted", "current_location_id": 44,
      "level": 7, "class_name": "Воин",
      "current_health": 260, "max_health": 300,
      "current_mana": 40, "max_mana": 90
    },
    {
      "character_id": 20, "user_id": 9, "name": "Мира", "avatar": null,
      "is_leader": false, "status": "invited", "current_location_id": 51,
      "level": 4, "class_name": "Маг",
      "current_health": 110, "max_health": 140,
      "current_mana": 95, "max_mana": 120
    }
  ]
}
```

Status codes unchanged: `200`, `401` (invalid/missing JWT), `404` (no party for `/mine` — existing behavior), `403` (ownership).

#### 3.1.2 battle-service — new `GET /battles/{battle_id}/preview`

Async endpoint in `app/main.py`; schemas in `app/schemas.py` (Pydantic v1). Reads: MySQL `battles` row (status + `location_id` + `battle_type`), Redis runtime state (`get_battle_state`), snapshot via existing `load_snapshot` (Redis cache → Mongo fallback) for name/avatar only. Location name: `SELECT name FROM Locations WHERE id = :lid` on the shared DB (`await db.execute(text(...))`) → `null` if row missing or `location_id` is null. **No new cross-service HTTP calls.**

Request: `GET /battles/{battle_id}/preview`, header `Authorization: Bearer <JWT>`.

`200` response:

```json
{
  "battle_id": 17,
  "battle_type": "pvp",
  "turn_number": 4,
  "location_id": 44,
  "location_name": "Тёмный лес",
  "turn_order": [
    { "participant_id": "c12", "name": "Артур", "is_current": true },
    { "participant_id": "c33", "name": "Гоблин-вожак", "is_current": false }
  ],
  "participants": [
    {
      "participant_id": "c12",
      "character_id": 12,
      "name": "Артур",
      "avatar": "https://s3.../12.webp",
      "team": "A",
      "is_ally": true,
      "is_alive": true,
      "hp": 180, "max_hp": 300,
      "mana": 40, "max_mana": 90
    },
    {
      "participant_id": "c33",
      "character_id": null,
      "name": "Гоблин-вожак",
      "avatar": null,
      "team": "B",
      "is_ally": false,
      "is_alive": true,
      "hp": 45, "max_hp": 120,
      "mana": 0, "max_mana": 0
    }
  ]
}
```

Field sourcing:
- `turn_number`, `turn_order` (participant ids), per-participant `hp/mana/max_*`, `team` — Redis runtime state (`redis_state.py:131-166`; runtime participants DO store `max_*`, unlike the `/state` response).
- `name`, `avatar`, `character_id` — snapshot participants (`build_participant_info`); NPC participants may have `character_id: null`, `avatar: null`.
- `is_ally` — computed server-side: `participant.team == team of the requester's own participant` (requester's participant is found during the ownership check). Saves the frontend any team logic.
- `is_alive` — `hp > 0`.
- `turn_order[].name` — mapped from snapshot; `is_current` — matches runtime `next_actor` (the participant whose turn it is now).
- `battle_type` — from the `battles` MySQL row (e.g. `"pvp" | "pve" | "duel" | ...` — pass through as stored).

Pydantic schemas (`app/schemas.py`):

```python
class BattlePreviewTurnEntry(BaseModel):
    participant_id: str
    name: str
    is_current: bool = False

class BattlePreviewParticipant(BaseModel):
    participant_id: str
    character_id: Optional[int] = None
    name: str
    avatar: Optional[str] = None
    team: str
    is_ally: bool
    is_alive: bool
    hp: int
    max_hp: int
    mana: int
    max_mana: int

class BattlePreviewOut(BaseModel):
    battle_id: int
    battle_type: Optional[str] = None
    turn_number: int
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    turn_order: List[BattlePreviewTurnEntry] = []
    participants: List[BattlePreviewParticipant] = []
```

Status codes: `200`; `401` missing/invalid JWT; `403` none of the user's characters is a battle participant (mirror `/state` behavior/messages); `404` battle not found, battle not in `pending|in_progress`, or Redis state missing (Russian detail, e.g. `"Бой не найден или уже завершён"`). The `404` is the expected signal for the finished-battle race — see 3.5.

Nginx: no config change needed — `/battles/` prefix is already routed; `/battles/internal/` block does not match `/preview`.

#### 3.1.3 skills-service — base costs in the list (`GET /skills/characters/{character_id}/skills`)

Schema change only (`app/schemas.py`); `serialize_character_skill()` (`app/crud.py:326-346`) emits the three fields from the already-`selectinload`ed `cs.skill` — zero extra queries. Columns are `NOT NULL DEFAULT 0` (`app/models.py:24-26`), so plain `int = 0`:

```python
class CharacterSkillSummarySkill(BaseModel):
    id: int
    name: str
    skill_type: str
    skill_image: Optional[str] = None
    # FEAT-151 — base (non-perk-adjusted) costs for list cards:
    cost_energy: int = 0
    cost_mana: int = 0
    cooldown: int = 0
```

`200` response item example:

```json
{
  "character_skill_id": 5, "skill_id": 2, "character_id": 12,
  "level": 3, "free_perk_points": 1, "selected_perk_ids": [4],
  "reset_available_at": null,
  "skill": {
    "id": 2, "name": "Огненный шар", "skill_type": "attack",
    "skill_image": "https://s3.../fireball.webp",
    "cost_energy": 0, "cost_mana": 25, "cooldown": 2
  }
}
```

These are **base** values (user decision); perk-adjusted values remain in the detail modal via `/skills/{skill_id}/resolved`. Additive → all consumers safe (`SkillsTab`, `SkillUpgradeModal`, `NpcStatsEditor`, `adminCharacters.ts`, battle-service `skills_client.py`).

### 3.2 DB Changes

**None.** All three changes are response-shape only. No Alembic migrations. (Note: CLAUDE.md §7 "battle-service without Alembic" is stale — Alembic exists there; nothing to add.)

### 3.3 Security

| Endpoint | Auth | Notes |
|---|---|---|
| party `/party/mine`, `/party`, `/party/{id}/invite|respond`, `PATCH /party/{id}` | **unchanged** — JWT via `get_current_user_via_http` + `_require_owned` ownership | Enrichment exposes squadmates' class/level/HP/MP only to authenticated party members — acceptable in-game info |
| `GET /battles/{battle_id}/preview` | **JWT + participant-ownership check**, identical to `/state` (`main.py:1318-1337`) | Non-participants get `403`; no spectate variant in this feature. No rate limiting beyond gateway defaults — called once per tab mount, no polling |
| `GET /skills/characters/{id}/skills` | **stays as-is** (no auth — pre-existing tech debt, already tracked) | Additive fields are static game data (base costs), no new exposure |
| `GET /battles/character/{id}/in-battle` | unchanged (no auth, pre-existing) | Used before `/preview`, unchanged |

Input validation: `battle_id` is a path `int` (FastAPI-validated); no request bodies added anywhere. Error messages in Russian, no internals leaked.

### 3.4 Frontend Architecture

All new/rewritten files: TypeScript, Tailwind + design-system classes only, no `React.FC`, no new SCSS, responsive from 360px, `motion` fade-in presets per DESIGN-SYSTEM §12, every API call surfaces a Russian error message.

#### 3.4.1 Shared primitives — NEW `src/components/ProfilePage/shared/`

| File | Purpose | Design mapping |
|---|---|---|
| `FilterChips.tsx` | Generic pill-chip row: `{ key, label, dot?: string, count?: number }[]`, active key, `onChange`. Used by Skills (type filter), Quests (type filter), Battles (type + result rows), Titles (Все/Полученные/Закрытые), Party toggle. | `flex gap-2 overflow-x-auto gold-scrollbar pb-1`; chip = `shrink-0 rounded-full border px-4 py-2 text-xs font-medium transition-colors duration-200 ease-site`; inactive `border-white/15 text-white/65 hover:text-white`, active `border-gold/40 bg-gold/10 text-gold`; optional colored dot `w-2 h-2 rounded-full` |
| `SectionHeader.tsx` | Mini gold label + fading gold rule (mock's "Задачи / Награда / Рецепты / mechanic titles"). No such primitive exists yet — closest is `gradient-divider-h`, which is a full-width bottom border, not the mock's inline fading rule. | `flex items-center gap-2.5`: `<span class="gold-text text-[11px] font-medium uppercase tracking-[0.14em]">` + `<span class="flex-1 h-px bg-gradient-to-r from-gold/40 to-transparent">` |
| `StatTile.tsx` | Big mono-ish gold value + tiny label (Battles 4-tile stats row). | `gold-outline relative rounded-card bg-site-bg flex flex-col items-center gap-1 py-4 px-2`; value `gold-text text-2xl font-medium tabular-nums`, label `text-[10px] uppercase tracking-[0.06em] text-white/50 text-center` |
| `MiniStatBar.tsx` | Thin HP/MP bar with label and optional `cur/max` text (Party cards, ActiveBattleCard). | design-system `stat-bar` + `stat-bar-fill stat-bar-hp|stat-bar-mana`, height override `h-1.5`; label `text-[9px] font-medium` in `text-stat-hp`/`text-site-blue`; hidden entirely when values are `null` |
| `EmptyState.tsx` | Centered icon + message (empty quests detail, no invites, empty history/filter, 0 titles/skills). | `flex flex-col items-center justify-center gap-3 py-14 text-center`; lucide icon `text-white/20`, message `text-sm text-white/40` |

Card chrome convention (mock's `rgba(9,10,16,.62)` + gold hairline cards): framed panels → **`PanelShell`** (already encodes `gold-outline relative rounded-card bg-site-bg backdrop-blur shadow-card` + header row + `gold-scrollbar-wide` body); inner list cards → `relative rounded-card bg-black/30 border border-gold/[0.16] shadow-card`. Mock's `tabs-sc` horizontal scroll → `overflow-x-auto gold-scrollbar`. Rarity colors → existing `rarity-*` / `text-rarity-*`-style tokens (`bg-rarity-common|rare|legendary` etc. from tailwind.config).

#### 3.4.2 Icon strategy (verified against `node_modules/lucide-react` v1.7.0 — ALL present)

lucide-react imports: `Network` (skill tree button), `Zap` (energy chip), `Droplet` (mana chip), `Clock` (cooldown chip, craft buff), `Crown` (party leader), `Swords` (party/battle headers, empty battle state), `Users` (free slot), `UserPlus` (invite), `Plus` (create/invite buttons), `Trash2` (disband), `Check` (done objectives, invite accept, party benefits list), `CheckCircle` (no-invites empty state), `X` (decline), `Lock` (locked titles), `MapPin` (location hints), `BookOpen` (quest journal header), `Scroll` (quest empty state), `Star` (party-name input, quest XP reward), `ArrowRight` (go-to-battle), `Coins` (currency reward), `Sparkles` (transmutation/XP badge), `Pickaxe` (gathering header), `Hammer` (craft header), `History` (battle history). Verified present as `dist/esm/icons/*.js` (kebab-case files for each). Equipment/item imagery: backend item/skill images first, fallback to existing project SVGs `src/assets/icons/equipment/*` (`resource.svg`, `potion.svg`, `bag.svg`, …). **No inline SVGs copied from the mock.**

#### 3.4.3 Per-tab breakdown (mock line → component map)

**SkillsTab** (mock 265–338) — rewrite `SkillsTab/SkillsTab.tsx`; keep `ResolvedSkillCard.tsx` (detail modal) functionally as-is.
Header row: `gold-text` title + counter (`text-white/50 text-sm`), perk-points chip (`rounded-full border-gold/30 bg-gold/10 text-gold` + glow dot) shown when Σ `free_perk_points` > 0, «Дерево навыков» button → `btn-blue`-style Link to `/skill-tree` with `Network` icon. Type filter → `FilterChips` (Все / Атака / Защита / Поддержка with `bg-stat-hp`/`bg-site-blue`/`bg-stat-energy` dots). Cards grid `grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3.5`: card = inner-card chrome, 62px icon in gold-gradient frame (skill_image or type fallback), name, type badge, **level pips /4** (`w-5 h-1 rounded-full`, filled `bg-gold`, empty `bg-white/15`) + `level/4`, cost chips row from `skill.cost_energy/cost_mana/cooldown` (`Zap`/`Droplet`/`Clock`, always shown incl. 0), «перк» badge top-right when `selected_perk_ids.length > 0`. Click → existing resolved-skill modal. Empty: `EmptyState`.

**QuestsTab** (mock 340–473) — NEW dir `QuestsTab/` (`QuestsTab.tsx`, `QuestJournalList.tsx`, `QuestDetail.tsx`); **delete `QuestLogTab.tsx`**; update the import/usage in `ProfilePage.tsx`. Same API (`GET /locations/quests/active?character_id=`, `POST /locations/quests/{id}/complete|abandon`).
Header: gold title + count + green «готово к сдаче» chip when any quest complete. Type filter → `FilterChips`. Master-detail: `lg:grid lg:grid-cols-[346px_1fr] gap-4`, both columns are `PanelShell`s (journal: `bodyClassName` list with `gold-scrollbar-wide`, `PANEL_DESKTOP_HEIGHT_CLASS`-style capped height). Journal row: 42px icon frame, title, type label + thin progress bar, green `Check` when complete; active row `border-gold/40 bg-gold/[0.06]`. Detail: header (56px icon, title, type + «Выполнено» badges), description, «Задачи» `SectionHeader` + objectives with `Check`/circle + `cur/max` + `stat-bar` progress, «Награда» `SectionHeader` + chips (currency `Coins` gold chip, XP `Star` blue chip, item chips with images), actions: «Сдать задание» (green-tinted bordered button, only when complete) + «Отказаться» (ghost bordered, hover `text-site-red border-site-red`, with confirm — keep existing behavior). No selection → `EmptyState`. Mobile (<lg): single column — journal on top, detail below the list when a quest is selected.

**PartyTab** (mock 539–739) — rewrite as `PartyTab/PartyTab.tsx` (state machine: member / leader / no-party; data via existing `api/squads.ts`) + NEW `PartyMemberCard.tsx`, `PartyHeaderCard.tsx`, `InviteFromLocationPanel.tsx`, `PartyInvitesPanel.tsx`, `PartyCreateCard.tsx`. Update `squads.ts` `PartyMember` TS type with the 6 new optional fields.
`PartyMemberCard`: 54–62px round avatar in gradient frame (`Crown` badge above for leader), name, **class chip** (instead of mock's role chip; hidden when `class_name` null), `Ур. {level}`, `MiniStatBar` HP + MP with `cur/max` (hidden when null), online dot: green when `current_location_id === ownLocationId` else red + «На другой локации» (existing FEAT-144 logic); `status === "invited"` → card at `opacity-60` + «Приглашён» chip instead of bars. Leader view: gold party header card (`PartyHeaderCard` — avatar/name/«Лидер» chip/member count, existing rename+avatar upload entry points preserved), member grid + dashed «Свободный слот» placeholders (up to 4), red-tinted «Распустить отряд» (`Trash2`, keep confirm), right column `InviteFromLocationPanel` (PanelShell: location name with `MapPin`, players from `getPlayersOnLocation` + gold «Позвать» buttons, hint text). Member view: member grid + «Покинуть отряд». No-party view: `PartyCreateCard` (gold-tinted PanelShell: name input in bordered field with `Star` icon + char counter, benefits list with `Check`s, location hint, «Создать отряд» `btn-blue`) + `PartyInvitesPanel` (count badge in `text-site-red`, invite cards with Принять/Отклонить, `EmptyState` with `CheckCircle` when none).

**GatheringTab** (mock 741–778) — restyle `GatheringTab/GatheringTab.tsx` + `GatheringSkillCard.tsx` (data/redux unchanged — `gatheringSlice`). Card: inner-card chrome, 52px icon frame, name + `Ранг x/5`, XP bar (`stat-bar` + gold gradient fill `bg-gradient-to-r from-gold-dark to-gold-light`), «Текущие бонусы» label + rows, «След. ранг (N)» bordered-top footer or `gold-text` «Максимальный ранг» when maxed.

**BattlesTab** (mock 780–897) — rewrite `BattlesTab/BattlesTab.tsx` + NEW `BattlesTab/ActiveBattleCard.tsx`; extend `api/battles.ts` with `BattlePreview*` types + `fetchBattlePreview(battleId)` (JWT header, same client as `fetchBattleState`).
`ActiveBattleCard` (shown when `/in-battle` → true and `/preview` → 200): red-accent framed card (`relative rounded-card border border-site-red/40 bg-site-bg` + subtle red radial via `bg-[radial-gradient(...)]` is NOT allowed as freestyle — use `bg-site-red/[0.06]` tint layer), pulsing red dot + «Бой идёт» + `{location_name ?? 'Локация'} · Ход {turn_number}`; turn-order strip: «Очередь» label + 34px initial-circles from `turn_order` (current = gold `outline-gold` ring, others dimmed); two columns (`grid sm:grid-cols-2`): «Ваш отряд» (`is_ally`, green-tinted rows) / «Противники» (red-tinted rows) — each row: avatar, name, `MiniStatBar` HP `hp/max_hp` (+ MP for allies), dead → `opacity-50`; footer «Перейти к бою» `btn-blue` + `ArrowRight` → navigate `/battle/{battle_id}`. No active battle → slim bordered row «Нет активного боя». Stats: 4 × `StatTile` (Всего боёв / Победы / Поражения / Винрейт from existing history stats), `grid grid-cols-2 lg:grid-cols-4 gap-3`. Filters: two `FilterChips` rows (type; result), same client-side/param logic as today. History rows: date (`text-white/40 text-xs`), opponents (truncate), type badge, result pill (win `text-stat-energy bg-stat-energy/10` / loss `text-site-red bg-site-red/10` / draw neutral); pagination line preserved. Empty filter/history → `EmptyState` («Нет боёв по фильтру»).

**TitlesTab** (mock 899–927) — rewrite `TitlesTab/TitlesTab.tsx` (API `api/titles.ts` unchanged). Header + `FilterChips` (Все / Полученные / Закрытые — client-side). Cards grid: name colored by real rarity (`text-rarity-*` tokens: common → white, rare → `#76A6BD`, legendary → gold), rarity label, description, status row (Активен → gold glow dot; Получен; Закрыт → `Lock`, card `opacity-60`); **keep** condition progress bars on locked titles and XP-reward badges (user decision); keep select/unselect title actions. Empty filter → `EmptyState`.

**CraftTab** (mock 929–1041) — rewrite `CraftTab/CraftTab.tsx` shell + NEW `ProfessionRail.tsx`; restyle `ProfessionInfo.tsx`, `RecipeCard.tsx`, `RecipeList.tsx`, `ProfessionSelect.tsx`; restyle the section *chrome* of `SharpeningSection/GemSocketSection/RuneSocketSection/SmeltingSection/TransmutationSection/EssenceExtractionSection` (container + `SectionHeader`); their modals stay functionally as-is.
`ProfessionRail`: horizontal chip-rail of ALL 4 professions (icon + name + rank badge); active = gold border/bg; others `opacity-50 hover:opacity-80`; click on a non-active profession opens the **existing change-profession modal** (with its progress-loss warning). `ProfessionInfo`: mock 955–970 layout — 54px icon frame, name, `Ранг N · {rankName}` (gold), XP bar + `xp/next` text, rank pills row (passed ranks gold, current highlighted, future dimmed). Mechanic sections: `rounded-card border border-white/[0.07] bg-black/25 p-5` + `SectionHeader` + description; item grids unchanged logic. Recipes: `SectionHeader` «Рецепты» + count; `RecipeCard` per mock 1011–1037: 52px round icon (rarity ring), name + qty, rarity label, source badge, description, «Материалы» list with `have/need` (`text-stat-energy` when enough, `text-site-red` when short), craft button (disabled style when materials missing). No profession chosen → restyled `ProfessionSelect` as a mock-style screen: gold-framed `PanelShell`, heading, 4 profession cards (icon frame, name, short description, «Выбрать» button) — mock has no such screen; compose it from the same card chrome (user decision).

**Untouched:** `ProfileTabs.tsx`, `PerksTab/`, `LogsTab/`, `CharacterTab/`, `InventoryTab/`, `StatsTab/`, `CharacterInfoPanel/`, `EquipmentPanel/`, skill-tree pages.

### 3.5 Data Flow & Edge Cases

- **Battles data flow:** mount → `GET /battles/character/{id}/in-battle` (existing) → if `in_battle`, `GET /battles/{battle_id}/preview` (JWT). Fetch once per mount, no polling (profile card, not the battle page). **404 race** (battle ended between the two calls): treat as "no active battle" — render the slim empty row, optionally re-check `/in-battle` once; NO error toast for 404. 401/403 → redirect-to-login / hide card per existing axios interceptors; network/5xx → visible Russian error.
- **Party:** `/party/mine` 404 → no-party view (create + invites). Enriched fields `null` → hide bars/chips (no `0/0`). `invited` members → dimmed card + «Приглашён». Party of 1 → leader card + 3 dashed slots. Online/offline dot from `current_location_id` vs own location (existing logic).
- **Skills:** 0 skills → `EmptyState`; costs `0/0/0` → chips still rendered with 0 (mock behavior). Perk badge from `selected_perk_ids.length`.
- **Quests:** empty journal → `EmptyState` in journal panel + placeholder detail; selected quest disappears after Сдать/Отказаться → clear selection, refetch list.
- **Craft:** no profession → styled `ProfessionSelect` screen; no recipes → `EmptyState`; insufficient materials → red `have/need` + disabled craft button.
- **Titles:** 0 titles / empty «Закрытые» filter → `EmptyState`.
- **Gathering:** max rank → «Максимальный ранг» footer, no next-rank block.
- **Cross-service safety:** all three backend changes are additive; consumers verified in §2 (frontend + battle-service `skills_client` tolerate extra keys; `/party/internal/*` schemas untouched; no `/state` change at all — BattlePage/WS unaffected).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Execution plan: **T1–T3 backend in parallel** → **T4 (frontend wave 1: shared primitives + Skills)** → **T5–T9 (frontend wave 2, parallel — disjoint directories)**; QA **T10–T12** run right after their backend task, in parallel with frontend; **T13 Reviewer last**. Only T6 touches `ProfilePage.tsx` (QuestLogTab → QuestsTab import) — no file conflicts between parallel tasks.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| T1 | Enrich party `MemberOut` with `level`, `class_name`, `current_health/max_health`, `current_mana/max_mana` per §3.1.1: extend `get_characters_map()`/`get_character_info()` SQL (LEFT JOIN `classes`), add batched `get_attributes_map()` on `character_attributes`, merge in `build_party_out()`. All fields Optional, `null` when source row missing. Keep O(1) queries; no route/auth changes. | Backend Developer | DONE | `services/party-service/app/schemas.py`, `services/party-service/app/crud.py` | — | `GET /party/mine` returns new fields per §3.1.1 example; missing attributes row → `null`s (no error); `/party/internal/*` responses unchanged; `python -m py_compile` passes on modified files |
| T2 | New `GET /battles/{battle_id}/preview` per §3.1.2: JWT + participant-ownership check (mirror `/state` `main.py:1318-1337`), read Redis runtime state (incl. `max_*`) + snapshot (name/avatar) + `battles` row (`status`, `battle_type`, `location_id`), location name via shared-DB `SELECT name FROM Locations`; compute `is_ally`/`is_alive`/`turn_order[].is_current`; add `BattlePreviewOut` schemas. 404 (Russian detail) when battle absent/not active/state missing; `/state` untouched. | Backend Developer | DONE | `services/battle-service/app/main.py`, `services/battle-service/app/schemas.py` | — | Endpoint returns compact DTO per §3.1.2 example; 401/403/404 semantics as specced; no change to `/state` response; no new cross-service HTTP calls; `python -m py_compile` passes |
| T3 | Add base `cost_energy`, `cost_mana`, `cooldown` (int, default 0) to nested `CharacterSkillSummarySkill` per §3.1.3; emit them in `serialize_character_skill()` from the loaded `cs.skill` (zero extra queries). | Backend Developer | DONE | `services/skills-service/app/schemas.py`, `services/skills-service/app/crud.py` | — | `GET /skills/characters/{id}/skills` items include the 3 fields inside `skill{}`; `/resolved` unchanged; `python -m py_compile` passes |
| T4 | Frontend wave 1 — shared primitives + Skills tab: create `shared/FilterChips.tsx`, `SectionHeader.tsx`, `StatTile.tsx`, `MiniStatBar.tsx`, `EmptyState.tsx` per §3.4.1; rewrite `SkillsTab.tsx` per §3.4.3 (header + perk-points chip + tree button, type FilterChips, card grid with level pips /4 and cost chips from `skill.cost_*`/`cooldown`, «перк» badge, EmptyState). Icons from the verified lucide list only (§3.4.2). | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/ProfilePage/shared/*` (new), `.../SkillsTab/SkillsTab.tsx`, skills TS types where the list response is typed | T3 | Skills tab matches §3.4.3 on desktop + 360px; costs/cooldown chips show base values incl. 0; detail modal still opens; `npx tsc --noEmit` AND `npm run build` pass |
| T5 | Party tab redesign per §3.4.3: rewrite `PartyTab.tsx` (member/leader/no-party states), new `PartyMemberCard.tsx`, `PartyHeaderCard.tsx`, `InviteFromLocationPanel.tsx`, `PartyInvitesPanel.tsx`, `PartyCreateCard.tsx`; extend `PartyMember` type in `api/squads.ts` with the 6 optional fields. Class chip instead of role chip; HP/MP `MiniStatBar` hidden when `null`; keep all existing actions (create/invite/respond/leave/disband/rename/avatar). | Frontend Developer | DONE | `.../ProfilePage/PartyTab/*`, `src/api/squads.ts` | T1, T4 | All 3 states match mock composition; invited member dimmed + «Приглашён»; null enrichment → no bars/chip, no `0/0`; all party actions still work with visible Russian errors; `npx tsc --noEmit` AND `npm run build` pass |
| T6 | Quests tab → master-detail per §3.4.3: new `QuestsTab/` (`QuestsTab.tsx`, `QuestJournalList.tsx`, `QuestDetail.tsx`), delete `QuestLogTab.tsx`, update import in `ProfilePage.tsx`. Keep complete/abandon flows (with confirm) and refetch after actions; single column + detail below list under `lg`. | Frontend Developer | DONE | `.../ProfilePage/QuestsTab/*` (new), `.../ProfilePage/QuestLogTab.tsx` (delete), `.../ProfilePage/ProfilePage.tsx` | T4 | Journal/detail layout per mock 340–473; objectives progress + rewards chips rendered; Сдать/Отказаться work and clear selection; empty states per §3.5; `npx tsc --noEmit` AND `npm run build` pass |
| T7 | Battles tab redesign per §3.4.3: rewrite `BattlesTab.tsx`, new `ActiveBattleCard.tsx`; add `BattlePreview*` types + `fetchBattlePreview()` to `api/battles.ts`; 4× `StatTile`, two `FilterChips` rows, history rows + pagination, EmptyState. Preview fetched once per mount after `/in-battle`; **404 → silent fallback to «Нет активного боя»** (no toast); 5xx/network → Russian error. | Frontend Developer | DONE | `.../ProfilePage/BattlesTab/*`, `src/api/battles.ts` | T2, T4 | Active-battle card shows location · turn, turn-order strip with current-actor highlight, ally/enemy columns with HP(/MP) bars, «Перейти к бою» navigates to `/battle/{id}`; 404 race handled per §3.5; filters/pagination still work; `npx tsc --noEmit` AND `npm run build` pass |
| T8 | Craft tab redesign per §3.4.3: rewrite `CraftTab.tsx`, new `ProfessionRail.tsx` (all 4 professions, non-active dimmed, click → existing change-profession modal), restyle `ProfessionInfo.tsx` (rank pills + XP bar), `RecipeCard.tsx`/`RecipeList.tsx` (materials have/need), `ProfessionSelect.tsx` (styled no-profession screen), section chrome of the 6 mechanic sections via `SectionHeader` (modals' logic untouched). | Frontend Developer | DONE | `.../ProfilePage/CraftTab/CraftTab.tsx`, `ProfessionRail.tsx` (new), `ProfessionInfo.tsx`, `RecipeCard.tsx`, `RecipeList.tsx`, `ProfessionSelect.tsx`, `*Section.tsx` (chrome only) | T4 | Rail shows 4 professions with active highlight; switching profession still goes through the warning modal; recipes show have/need coloring + disabled craft when short; all craft/sharpen/socket/smelt/transmute/extract flows still work; `npx tsc --noEmit` AND `npm run build` pass |
| T9 | Titles + Gathering redesign per §3.4.3: rewrite `TitlesTab.tsx` (FilterChips Все/Полученные/Закрытые, rarity-colored cards, keep condition progress bars + XP badges + select/unselect actions, Lock on closed); restyle `GatheringTab.tsx` + `GatheringSkillCard.tsx` (rank /5, XP bar, bonuses, next-rank / «Максимальный ранг»). | Frontend Developer | DONE | `.../ProfilePage/TitlesTab/TitlesTab.tsx`, `.../ProfilePage/GatheringTab/*` | T4 | Filters work client-side with EmptyState when empty; rarity colors from rarity tokens; progress bars + XP badges preserved; max-rank gathering card per §3.5; `npx tsc --noEmit` AND `npm run build` pass |
| T10 | pytest for party enrichment in `services/party-service/app/tests/` (extend `test_party.py` or add `test_party_enrichment.py`, follow existing conftest patterns): members include level/class_name/HP/MP; missing `character_attributes` row → nulls without 500; batched queries (no per-member SQL); invites list unchanged. | QA Test | DONE | `services/party-service/app/tests/test_party_enrichment.py` (new) or `test_party.py` | T1 | New tests pass; existing party tests stay green (`pytest services/party-service`) |
| T11 | pytest for `GET /battles/{battle_id}/preview` in `services/battle-service/app/tests/` (follow `test_spectate.py`/`test_endpoint_auth.py` patterns, mocked Redis/Mongo per conftest): 200 shape (is_ally/max_*/turn_order/location_name), 401 without JWT, 403 non-participant, 404 finished/missing state, location_name null when Locations row absent. Add the endpoint to auth-coverage test if the suite enumerates endpoints. | QA Test | DONE | `services/battle-service/app/tests/test_battle_preview.py` (new) | T2 | New tests pass; existing battle tests stay green (`pytest services/battle-service`) |
| T12 | pytest for skills list costs in `services/skills-service/app/tests/` (extend `test_resolved_skill.py`-adjacent list coverage or add `test_character_skills_list.py`): list items expose base `cost_energy/cost_mana/cooldown` inside `skill{}`; values are base (not perk-adjusted) even with selected perks; defaults 0. | QA Test | DONE | `services/skills-service/app/tests/test_character_skills_list.py` (new) | T3 | New tests pass; existing skills tests stay green (`pytest services/skills-service`) |
| T13 | Final review: re-run `npx tsc --noEmit` + `npm run build` + all three services' pytest + `python -m py_compile` on touched backend files; **live verification** (MCP chrome-devtools with test admin account): open all 7 tabs at 1280px and 360px, verify zero console errors, party enrichment rendering, active-battle card (or empty row), quest master-detail actions, craft rail + profession switch modal, titles filters; verify cross-service contracts (§3.5) and design-system compliance (no React.FC, no new SCSS, tokens only); verify mandatory rules T1/T3/T5 of ISSUES.md-tracked migrations respected in touched files. | Reviewer | REVIEW #1: FAIL (2 issues) | — | T1–T12 | Review log written to section 5 with PASS, incl. automated check outputs and live-verification evidence |
| T14 | Design-system darkening per user decision (§1 «Дополнение от пользователя»): tailwind `site.bg` → mock panel color `rgba(9,10,16,0.62)`; opaque surfaces (modal-content, dropdown-menu, context-menu and other solid `rgba(35,35,41,…)` usages in index.css) → `rgba(14,15,21,0.98)`; `--gray-background` CSS var + any design-system hardcodes updated consistently; body: base `background-color: #05060a` + NON-aggressive dark gradient overlay over background-main.png; update docs/DESIGN-SYSTEM.md (§2 color table, body/bg note). No component-file changes — token/CSS-layer only. NO browser adaptive checks. | Frontend Developer | DONE | `tailwind.config.js`, `src/index.css`, `docs/DESIGN-SYSTEM.md` (+`src/global.scss` var only if needed) | — | `npx tsc --noEmit` + `npm run build` pass; grep shows no remaining `rgba(35, 35, 41` in design-system layers; desktop-only visual sanity |
| T15 | Review #2: re-verify Review #1 issues #1/#2 fixed + T14 design-system darkening applied consistently; automated checks re-run; **desktop-only** live walk of the 7 tabs (NO 360px/adaptive emulation — user decision); write Review #2 to §5. | Reviewer | REVIEW #2: PASS | — | T13, T14 + fixes | §5 Review #2 = PASS |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-07-17
**Result:** FAIL

#### Automated Check Results
- [x] `npx tsc --noEmit` — **PASS** (0 errors)
- [x] `npm run build` — **PASS** (exit 0; only pre-existing sass deprecation warnings + chunk-size warning)
- [x] `py_compile` — **PASS** (all 10 touched/new backend .py files, incl. tests)
- [x] `pytest` party-service — **PASS**: 28 passed (18 existing + 10 T10 enrichment tests, scratchpad venv, pydantic 1.x)
- [x] `pytest` battle-service — **PASS**: 376 passed (360 existing + 16 T11 preview tests, inside docker container)
- [x] `pytest` skills-service — **PASS**: 170 passed (163 existing + 7 T12 list-cost tests; known post-run process hang killed by timeout, unrelated to changes)
- [x] `docker compose config` — **PASS**
- [x] Live verification (chrome-devtools) — **DONE** (see below; 2 defects found)

#### Contract / Code Review
- §3.1.1 party `MemberOut`: 6 additive Optional fields, batched `get_attributes_map()` + LEFT JOIN `classes` — matches spec exactly, O(1) queries kept; `/party/internal/*` untouched; `squads.ts` `PartyMember` extended with matching optional nullable fields. OK.
- §3.1.2 `GET /battles/{id}/preview`: JWT + participant-ownership mirrors `/state`; compact DTO with `max_*` from Redis runtime, `is_ally`/`is_alive`, turn order with `is_current`, `location_name` via shared `Locations` read; Russian 404 detail. Curl-verified live: 401 without JWT, 404 `«Бой не найден»` with JWT for missing battle. Logged T2 deviation (numeric-string `participant_id`/`team` instead of the spec example's `"c12"`) is consistently typed in `api/battles.ts` and documented — accepted.
- §3.1.3 skills list: `cost_energy/cost_mana/cooldown` nested in `skill{}` (int, default 0, `or 0` on NULL) — verified live: `GET /skills/characters/1/skills` returns `{"cost_energy":15,"cost_mana":0,"cooldown":1}`. `/resolved` untouched. OK.
- Design system: no `React.FC`, no new SCSS, no console.log debris, no leftover `QuestLogTab` imports (only a comment mention), tokens only in all new/rewritten files (palette-color grep hits are exclusively in files NOT touched by this feature: `ResolvedSkillCard.tsx`, craft modals — pre-existing). Mechanic-section restyles are minimal-diff chrome-only as specced. Icon deviations (`Sprout`/`Axe` — logged in T9; `Shield` in SkillsTab — unlogged) all verified present in lucide-react v1.7.0; accepted.
- Error handling: every API call in touched files surfaces a Russian message (toast and/or inline) or is an explicitly silent expected case (preview 404 race, no-profession 404). OK.
- QA coverage: T10/T11/T12 exist, DONE, and their tests run green. OK.

#### Live Verification Results
- Environment: dev stack via gateway `http://localhost` (port 80), test admin account, character «Имяперсонажа» (id 1; has skills/attributes/inventory). Viewports 1280×900 and 360×780 (device emulation).
- **Навыки**: cards with 62px icon frames, level pips /4, cost chips incl. 0 (15/0/1, 8/0/3), tree button, detail modal opens with resolved data. **Defect #1 confirmed live**: «Атака» filter chip → «Нет навыков выбранного типа» although an Attack skill exists (see Issues).
- **Отряд**: no-party state per mock — `PartyCreateCard` (name input + counter, benefits, location hint, «Создать отряд») + `PartyInvitesPanel` EmptyState with CheckCircle. Member/leader states not exercised live (would require creating/disbanding a party — destructive; covered by 10 T10 pytest cases that run the real SQL against seeded shared tables).
- **Сбор**: 3 cards, distinct icons (Pickaxe/Sprout/Axe), «Ранг 1/5», XP bar 0/10, bonuses, «След. ранг (2)» footer.
- **Задания**: master-detail per mock (journal row select → detail with type badge, objectives 0/3 progress bar, reward chips Coins 50 / Star 25 XP, «Отказаться»); filter «Ежедневные» → empty-filter state + selection cleared; mobile 360px → single column, detail below journal. Exercised on a temporary quest created+accepted via admin API and fully cleaned up afterwards (abandoned + quest deleted). **Defect #2**: React key warning in console from `QuestDetail` (see Issues).
- **Бои**: «Нет активного боя» slim row, 4 StatTiles, both FilterChips rows (result filter «Победы» → correct `result=victory` request + «Нет боёв по фильтру» EmptyState), history empty state. Preview endpoint curl-verified (401/404 semantics). Active-battle card not exercised live (no runnable battle without heavy destructive setup); shape covered by 16 T11 tests.
- **Крафт**: no-profession `ProfessionSelect` screen per §3.4.3 (6 professions in DB, not 4 — components correctly iterate all); selected «Кузнец» for the sandbox character via the UI confirm modal; full state renders: rail (active gold, others dimmed «Не изучена»), `ProfessionInfo` (rank pills Ученик/Подмастерье/Мастер, XP 0/500), «Заточка» section chrome + SectionHeader, «Рецепты» + search + EmptyState. Rail click on «Алхимик» → change-profession modal with progress-loss warning and the clicked profession preselected → cancelled (no change performed).
- **Титулы**: header counter 0/0, FilterChips with counts switch correctly, EmptyState (DB has no titles seeded).
- Console: ZERO errors on Навыки/Отряд/Сбор/Бои/Крафт/Титулы. On Задания — the Defect #2 React key warning. One expected 404 (`/inventory/professions/{id}/my` before a profession is chosen — pre-existing handled pattern, silent by design).
- Mobile 360px: no horizontal overflow on any of the 7 tabs (`scrollWidth == 360` verified per tab); chips rails scroll horizontally.
- Screenshots: `/tmp/claude-1000/-home-dudka-chaldea/dcfe6743-aef7-43e7-b245-05377ea53dc4/scratchpad/review/` — `skills-1280.png`, `skills-modal.png`, `party-1280.png`, `gathering-1280.png`, `quests-1280.png`, `battles-1280.png`, `craft-1280.png`, `craft-rail-1280.png`, `craft-change-modal.png`, `titles-1280.png`, `quests-360.png`, `skills-360.png`, `craft-360.png`.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/ProfilePage/SkillsTab/SkillsTab.tsx:33-56, 124-130, 216-219` | **skill_type case mismatch.** The `skills.skill_type` column/API returns capitalized values (`'Attack'`/`'Defense'`/`'Support'` — verified in DB and live API), but `SKILL_TYPE_LABELS`, `SKILL_TYPE_BADGE`, `SKILL_TYPE_FALLBACK_ICON` and the `FilterChips` comparison (`cs.skill?.skill_type === typeFilter`) all use lowercase keys. Result (confirmed live): the new type filter ALWAYS returns «Нет навыков выбранного типа», type badges never render, fallback icon is always Swords. Fix: normalize once, e.g. `const skillType = (cs.skill?.skill_type ?? '').toLowerCase()` and filter on the normalized value (keep chip keys lowercase). | Frontend Developer | FIXED |
| 2 | `services/frontend/app-chaldea/src/components/ProfilePage/QuestsTab/questModel.ts:4-10` + `QuestDetail.tsx:82` | **Objective type/key mismatch.** locations-service `ObjectiveProgressRead` (`services/locations-service/app/schemas.py:972-979`) has `objective_id`, not `id`; the new `QuestObjective` interface declares `id: number` and `QuestDetail` uses `key={obj.id}` → `undefined` keys → React «unique key» console error (violates zero-console-errors rule). Fix: rename the interface field to `objective_id` and use it as the key (or key by index). | Frontend Developer | FIXED |

#### Pre-existing issues noted (NOT blocking, not caused by FEAT-151)
- `ResolvedSkillCard.tsx` and several craft modals (untouched by this feature) use non-token Tailwind palette colors (`red-500`, `sky-300`, `emerald-500`, …) and the same lowercase `skill_type` keys — the badge fallback there is also affected by the case mismatch. Candidate for a separate cleanup task.
- Test character «Артория» (id 2) lacks `character_attributes` / full-profile rows → 404 toasts on the «Персонаж» tab (data issue of the dev DB, CharacterTab is out of scope).
- `GET /inventory/professions/{id}/my` returns 404 as the normal "no profession yet" signal → logged as a browser console resource error by Chrome (handled silently by app code; pre-existing pattern).

### Review #2 — 2026-07-17
**Result:** PASS

Scope: Review #1 fixes #1/#2 + T14 design-system darkening. Verified via git diff on: `SkillsTab.tsx`, `QuestsTab/questModel.ts`, `QuestsTab/QuestDetail.tsx`, `tailwind.config.js`, `src/index.css`, `docs/DESIGN-SYSTEM.md`. Unrelated uncommitted FEAT-150 changes were committed separately (`6e964b4`) and excluded from this review.

#### Code Review of the Fixes
- **Fix #1 (skill_type case mismatch)** — correct. Single-point `normalizeSkillType()` helper (`SkillsTab.tsx:59`, toLowerCase, null-safe) applied at BOTH usage sites: the filter comparison (`:131`) and the per-card render (`:219`), from which `SKILL_TYPE_BADGE` / `SKILL_TYPE_LABELS` / `SKILL_TYPE_FALLBACK_ICON` lookups all derive. Chip keys stay lowercase. No other `skill_type` comparisons in the file bypass the helper.
- **Fix #2 (objective key)** — correct. `QuestObjective.objective_id: number` (`questModel.ts:5`) matches locations-service `ObjectiveProgressRead` (`schemas.py:972-979`); `key={obj.objective_id}` (`QuestDetail.tsx:82`). grep confirms zero remaining `obj.id` usages in `QuestsTab/`.
- **T14 darkening** — matches the user decision exactly, token/CSS-layer only, no component files touched:
  - `tailwind.config.js` `site.bg` → `rgba(9, 10, 16, 0.62)` (single-line diff);
  - `index.css`: `gray-bg` + `--gray-background` → `rgba(9,10,16,0.62)`; opaque floating surfaces (`dropdown-menu`, `modal-content`, `site-tooltip`, `context-menu` incl. its gradient-border fill, `category-icon-active` gradient fill) → `rgba(14,15,21,0.98)`;
  - `body`: `background-color: #05060a` + soft overlay `linear-gradient(180deg, rgba(5,6,10,0.35), rgba(5,6,10,0.55))` over background-main.png (deliberately softer than the mock per user decision);
  - mobile scrollbar: `@media (max-width: 640px)` sets `height: 3px` on `.gold-scrollbar` / `.gold-scrollbar-wide` `::-webkit-scrollbar` only — horizontal axis only, vertical widths and desktop untouched.
- **DESIGN-SYSTEM.md §2** — consistent with the actual new values: `bg-site-bg` table row, opaque-surfaces note (`rgba(14,15,21,.98)`), CSS-var block, new «Global page background» section (#05060a + soft gradient), §4 gray-bg description. No stale `rgba(35,35,41)` mentions anywhere in the doc.

#### Automated Check Results
- [x] `npx tsc --noEmit` — **PASS** (0 errors)
- [x] `npm run build` — **PASS** (exit 0; only pre-existing sass deprecation warnings + chunk-size warning, same as Review #1)
- [x] grep `rgba(35, 35, 41` / `rgba(35,35,41` across `src/` + `tailwind.config.js` — **0 occurrences**
- [x] `docker compose config` — **PASS**
- [x] `pytest` — **SKIPPED, justified**: backend unchanged since Review #1. File mtimes of all party/battle/skills service files (14:10–14:12) predate the frontend fixes and T14 (15:10–15:15); `git status` shows the identical backend file set Review #1 already tested green (party 28, battle 376, skills 170 passed).
- [x] Live verification (chrome-devtools, desktop only) — **PASS** (see below)

#### Live Verification Results (desktop 1280px+ only — NO adaptive emulation, per user decision)
- Environment: dev stack via gateway `http://localhost`, UI login with test admin (FEAT-150 `identifier` field works from the login form), character «Имяперсонажа» (id 1).
- **Darkening (T14) confirmed live via computed styles**: `body` → `rgb(5, 6, 10)` + `linear-gradient(rgba(5,6,10,0.35), rgba(5,6,10,0.55)), url(background-main.png)`; `--gray-background` and panel background → `rgba(9, 10, 16, 0.62)`. All profile panels/cards render visibly darker; no washed-out light-gray panels anywhere.
- **Навыки**: fix #1 confirmed live — filter «Атака» now returns «Мощный удар» (and only it); type badges «АТАКА» / «ПОДДЕРЖКА» render with correct colors; fallback icons per type.
- **Задания**: fix #2 confirmed live — on a temporary quest (created + accepted via admin API, 2 objectives) the detail opens with objectives 0/3, 0/2 progress bars and reward chips (Coins 50 / 25 XP); **zero React key warnings** in console. «Сдать»/«Отказаться» buttons present at panel bottom (`mt-auto`). Temp quest fully cleaned up afterwards (abandoned + deleted; admin quest list back to `[]`).
- **Отряд**: no-party state (PartyCreateCard + invites EmptyState) renders on the darker panels.
- **Сбор**: 3 cards, ranks 1/5, XP bars, bonuses, «След. ранг (2)» footers.
- **Бои**: «Нет активного боя» row, 4 StatTiles, both filter rows, empty-history state.
- **Титулы**: 0/0 counter, Все/Полученные/Закрытые chips, EmptyState.
- **Крафт**: profession rail (Кузнец active gold, 5 others dimmed «Не изучена»), ProfessionInfo with rank pills + XP 0/500, «Заточка» section, «Рецепты» + search + EmptyState. (Character kept the «Кузнец» profession selected during Review #1 — no destructive re-selection performed.)
- **Non-profile sanity (global darkening)**: home page renders correctly over the darkened background; header character dropdown opens near-opaque (`rgba(14,15,21,0.98)`) and fully readable.
- Console across the whole walk: **ZERO errors**. Only pre-existing noise: vite debug, React DevTools info, 2 React Router v7 future-flag warnings, and a pre-existing «form field should have id/name» DevTools a11y issue (login/search inputs, untouched by FEAT-151).
- Non-destructive only: no disband/abandon-of-real-data/profession-change confirm was performed; the only mutations were the temporary quest lifecycle, reverted completely.
- Screenshots: `/tmp/claude-1000/-home-dudka-chaldea/dcfe6743-aef7-43e7-b245-05377ea53dc4/scratchpad/review2/` — `home-1280.png`, `home-dropdown.png`, `skills-all.png`, `skills-filter-attack.png`, `party.png`, `gathering.png`, `quests-empty.png`, `quests-detail.png`, `battles.png`, `titles.png`, `craft.png`.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-07-17 — PM: фича создана; дизайн-мокап импортирован и разобран; рассинхроны согласованы с пользователем; запускаю Codebase Analyst
[LOG] 2026-07-17 14:00 — Analyst: анализ завершён. Затронуты party-service (обогащение участников: level+класс из shared-таблиц characters/classes, HP/MP из character_attributes — два варианта источника), battle-service (переиспользовать GET /battles/{id}/state, не хватает location_id в ответе), skills-service (добавить базовые cost_energy/cost_mana/cooldown в список — нулевая цена, relation уже загружен), frontend (7 вкладок). Изменений схемы БД нет; Alembic есть во всех трёх сервисах (заметка в CLAUDE.md §7 про battle-service устарела). Отчёт записан в секцию 2, три вопроса для Architect.
[LOG] 2026-07-17 14:45 — Architect: проектирование завершено. Решения по трём вопросам: (1) HP/MP отряда — батч-чтение shared-таблицы character_attributes (паттерн сервиса, O(1) запросов); (2) бои — новый лёгкий GET /battles/{battle_id}/preview (JWT + проверка участия, компактный DTO с max_*, is_ally, очередью ходов и location_name из shared-таблицы Locations; /state не трогаем); (3) стоимости навыков — вложенно в skill{} (int, default 0). Спроектированы 3 API-контракта, общие фронтенд-примитивы (FilterChips/SectionHeader/StatTile/MiniStatBar/EmptyState), покомпонентная разбивка 7 вкладок; все lucide-иконки проверены в node_modules (v1.7.0, все есть). Миграций БД нет. 13 задач: T1–T3 бэкенд (параллельно), T4 общие примитивы+Навыки, T5–T9 остальные вкладки (параллельная волна), T10–T12 QA, T13 Reviewer. Статус: IN_PROGRESS.
[LOG] 2026-07-17 14:13 — Backend Dev: задача T1 завершена. MemberOut расширен 6 Optional-полями (level, class_name, current_health/max_health, current_mana/max_mana); get_characters_map/get_character_info читают level + имя класса через LEFT JOIN classes; добавлен батчевый get_attributes_map по character_attributes (один IN-запрос), слияние в build_party_out — O(1) запросов. Отсутствующая строка атрибутов/класс → null без ошибки. В autouse-фикстуру test_party.py добавлен стаб get_attributes_map (shared-таблицы нет в SQLite). py_compile OK; все 18 существующих тестов party-service зелёные (venv с pydantic<2); smoke-тест обогащения на SQLite прошёл.
[LOG] 2026-07-17 15:30 — Backend Dev: задача T2 завершена. Добавлен GET /battles/{battle_id}/preview (JWT + проверка участия как в /state, компактный DTO: участники с max_*/is_ally/is_alive, очередь ходов с is_current, location_name из shared-таблицы Locations, 404 по-русски для завершённого/отсутствующего боя). Изменены main.py и schemas.py battle-service; py_compile OK, все 360 тестов сервиса прошли в контейнере, live-проверка: роут зарегистрирован, 401 без JWT.
[LOG] 2026-07-17 16:10 — QA: задача T10 завершена. Написан test_party_enrichment.py (10 тестов): в отличие от test_party.py, shared-таблицы characters/classes/character_attributes создаются в SQLite через raw DDL и гоняются НАСТОЯЩИЕ SQL-хелперы crud (LEFT JOIN classes, батчевые IN-запросы). Покрыто: обогащение участников (level/class_name/HP/MP, включая invited), отсутствующая строка character_attributes → 4 null-поля без 500, неизвестный/пустой класс → class_name null, батчинг (get_characters_map и get_attributes_map вызываются ровно по 1 разу на запрос при 4 участниках), обогащение ответа POST /party/, неизменность формы /party/invites/incoming. Все 28 тестов сервиса зелёные (18 старых + 10 новых, venv pydantic 1.10.26).
[LOG] 2026-07-17 14:18 — QA: задача T11 завершена. Написан tests/test_battle_preview.py (16 тестов по паттерну test_spectate.py, моки Redis/Mongo/БД): полная форма DTO (is_ally/is_alive/max_* из Redis, team/participant_id строками, очередь ходов с is_current от next_actor, battle_type из enum), перспектива противника, мёртвый участник, fallback-имя «Участник #pid» и NPC без character_id, пустой аватар → null, location_name null при отсутствии строки Locations, отсутствие запроса к Locations при location_id=null, Mongo-fallback снапшота, 401 без/с невалидным JWT, 403 «Вы не участвуете в этом бою», 404 (бой отсутствует / finished / forfeit / нет Redis-состояния, в т.ч. 404 раньше проверки участия). test_endpoint_auth.py эндпоинты не перечисляет циклом — 401/403 покрыты в новом файле. Прогон в контейнере battle-service: 376 passed (360 существующих + 16 новых). Багов в реализации T2 не обнаружено.
[LOG] 2026-07-17 16:20 — Backend Dev: задача T3 завершена. В CharacterSkillSummarySkill добавлены базовые cost_energy/cost_mana/cooldown (int, default 0), serialize_character_skill эмитит их из уже загруженного cs.skill — ноль дополнительных запросов; /resolved не тронут. Изменены schemas.py и crud.py skills-service. py_compile OK; полный набор тестов сервиса: 163 passed за 12.7s (локально процесс pytest после прогона не завершается сам из-за незакрытого фонового потока — killed по timeout, к изменению отношения не имеет).
[LOG] 2026-07-17 18:10 — Frontend Dev: задача T8 завершена. Вкладка «Крафт» переписана по мокапу: шапка «Мастерская» + ActiveBuffIndicator; новый ProfessionRail — все 4 профессии горизонтальным рейлом (gold-scrollbar на мобильных), активная с золотой подсветкой, остальные затемнены (opacity-50 hover:80), клик по неактивной открывает существующую модалку смены профессии с предупреждением о потере прогресса (модалка перенесена из ProfessionInfo в ProfessionRail, кликнутая профессия предвыбрана). ProfessionInfo рестайл: 54px золотая рамка иконки, «Ранг N · {rankName}», XP-бар с текстом xp/next, ряд пилюль рангов (пройденные — приглушённое золото, текущий — подсвечен, будущие — затемнены). RecipeCard по мокапу 1011–1037: 52px круглая иконка с rarity-кольцом, qty, лейбл редкости токенами, бейдж Чертёж/Выучен, материалы have/need (text-stat-energy / text-site-red), disabled-кнопка при нехватке. RecipeList: SectionHeader «Рецепты» + счётчик, EmptyState. ProfessionSelect: экран выбора в PanelShell с 4 карточками и «Выбрать» (модалка подтверждения сохранена). 6 секций механик — только хром: rounded-card border-white/[0.07] bg-black/25 p-5 + SectionHeader + описание; модалки/логика не тронуты. Проверки: npx tsc --noEmit — 0 ошибок; npm run build (отдельный outDir) — exit 0.
[LOG] 2026-07-17 17:05 — Frontend Dev: задача T4 завершена. Созданы 5 общих примитивов в ProfilePage/shared/ (FilterChips, SectionHeader, StatTile, MiniStatBar, EmptyState) строго по спецификации §3.4.1 — готовы к переиспользованию вкладками T5–T9. SkillsTab переписан по мокапу: шапка (gold-заголовок + счётчик, чип суммы очков перков с glow-точкой, кнопка «Дерево навыков» с иконкой Network), фильтр типов через FilterChips с цветными точками, сетка карточек (62px иконка в золотой рамке, пипсы уровня /4, чипы энергия/мана/КД из новых базовых полей skill.cost_*, бейдж «перк»), EmptyState для 0 навыков и пустого фильтра, stagger-анимации motion. Модалка ResolvedSkillCard функционально не тронута (открытие по клику сохранено). В types.ts (SkillTreeView) в skill{} добавлены cost_energy/cost_mana/cooldown. Проверки: npx tsc --noEmit — 0 ошибок, npm run build — успех (exit 0); live-эндпоинт /skills/characters/{id}/skills отдаёт новые поля.
[LOG] 2026-07-17 17:10 — QA: задача T12 завершена. Написан tests/test_character_skills_list.py (7 тестов по паттерну test_resolved_skill.py, aiosqlite in-memory): базовые cost_energy/cost_mana/cooldown внутри skill{}; парная проверка «список = base (5/10/2) vs /resolved = с перками (4/12/0)» при выбранных перках с дельтами; навык с нулевыми стоимостями → 0/0/0 без ошибки; unit-тест сериализатора на NULL-стоимости → 0; обратная совместимость (все legacy-ключи, free_perk_points/selected_perk_ids); пустой список для персонажа без навыков; нечисловой character_id → 422 (не 500). Полный прогон: 170 passed (163 старых + 7 новых), 0 failed; известное зависание процесса pytest после «passed» (фоновый поток RabbitMQ-теста) снято по timeout — к изменениям отношения не имеет. Багов в реализации T3 не обнаружено.
[LOG] 2026-07-17 17:40 — Frontend Dev: задача T9 завершена. TitlesTab переписан по мокапу: шапка (gold-заголовок + счётчик получено/всего), FilterChips Все/Полученные/Закрытые (клиентская фильтрация, счётчики на чипах), сетка карточек с именем в цвете редкости (rarity-токены common/rare/legendary), лейблом редкости и описанием; статус-строка Активен (золотая glow-точка) / Получен (stat-energy) / Закрыт (Lock, opacity-60); сохранены прогресс-бары условий у закрытых титулов (STAT_LABELS), XP-бейджи наград (чипы со Sparkles) и действия Выбрать/Снять с пер-титульным лоадингом; EmptyState для 0 титулов и пустых фильтров. GatheringTab/GatheringSkillCard рестайлены: карточка с inner-card chrome, 52px иконка категории в золотой рамке (Pickaxe/Sprout/Axe — проверены в lucide v1.7.0), Ранг x/5, XP stat-bar с золотым градиентом, «Текущие бонусы», футер «След. ранг (N)» / «Максимальный ранг»; поведение загрузки/ошибки/повтора сохранено, пустое состояние через EmptyState с кнопкой «Попробовать снова». Отклонение: для иконок категорий сбора добавлены Sprout и Axe сверх списка §3.4.2 (проверены тем же способом в node_modules — иначе все 3 навыка имели бы одну иконку). Проверки: npx tsc --noEmit — 0 ошибок; npm run build (уникальный outDir) — exit 0.
[LOG] 2026-07-17 17:55 — Frontend Dev: задача T5 завершена. PartyTab переписан по мокапу (3 состояния: участник / лидер / без отряда), созданы PartyMemberCard (54px аватар в золотой рамке, Crown у лидера, чип класса вместо чипа роли, Ур. N, MiniStatBar HP/MP с cur/max — скрыты при null-обогащении, без «0/0»; invited → opacity-60 + чип «Приглашён» вместо баров; онлайн-точка зелёная/красная по current_location_id против своей локации), PartyHeaderCard (золотая карточка отряда: аватар с загрузкой по клику для лидера, инлайн-переименование с Check/X, чип «Лидер», счётчик N/4), InviteFromLocationPanel (PanelShell: локация с MapPin, игроки с кнопкой «Позвать», подсказка, EmptyState), PartyInvitesPanel (бейдж счётчика в site-red, Принять/Отклонить, EmptyState с CheckCircle), PartyCreateCard (gold-tinted PanelShell: поле имени со Star и счётчиком символов, список преимуществ с Check, подсказка локации, «Создать отряд» btn-blue). PartyMember в api/squads.ts расширен 6 опциональными полями. Все действия FEAT-144 сохранены (create/invite/respond/leave/disband/rename/avatar, busy-guard, confirm на роспуск), ошибки API — toast по-русски. Панель приглашений видна и в отряде, если приглашения есть. Адаптивность: 1 колонка <lg, сетка участников 1→2 колонки от sm. Проверки: npx tsc --noEmit — 0 ошибок; npm run build (уникальный outDir /scratchpad/build-T5) — exit 0.
[LOG] 2026-07-17 18:05 — Frontend Dev: задача T6 завершена. Вкладка «Задания» переведена в master-detail по мокапу (340–473): новая директория QuestsTab/ (QuestsTab.tsx — шапка с gold-заголовком, счётчиком и зелёным чипом «N готово/готовы к сдаче», FilterChips Все/Обычные/Ежедневные/Повторяемые, сетка lg:grid-cols-[346px_1fr] из двух PanelShell с PANEL_DESKTOP_HEIGHT_CLASS; QuestJournalList.tsx — строки журнала: 42px иконка Scroll в золотой рамке, заголовок, цветной лейбл типа + тонкий прогресс-бар, зелёный Check у выполненных, подсветка активной строки, stagger-анимация; QuestDetail.tsx — хедер с 56px иконкой/заголовком/бейджами типа и «Выполнено», описание, SectionHeader «Задачи» с прогресс-барами stat-bar и cur/max, SectionHeader «Награда» с чипами Coins/Star/предметов с картинками, кнопки «Сдать задание» (только при выполнении) и «Отказаться» с confirm; questModel.ts — общие типы/лейблы/хелперы прогресса). QuestLogTab.tsx удалён, в ProfilePage.tsx — минимальная замена импорта и рендера. API прежний (GET /locations/quests/active, POST complete/abandon), после сдачи/отказа — сброс выбора + refetch. Пустые состояния: EmptyState в журнале (0 заданий / пустой фильтр) и в детали («Выберите задание из журнала»); ошибка загрузки — красный текст + кнопка «Повторить» + toast. Мобильные <lg: одна колонка, деталь под списком только при выбранном задании. Проверки: npx tsc --noEmit — 0 ошибок; npm run build (уникальный outDir /scratchpad/build-T6) — exit 0.
[LOG] 2026-07-17 18:15 — Frontend Dev: задача T7 завершена. BattlesTab переписан по мокапу: шапка (gold-заголовок «Бои» + счётчик), карточка активного боя ActiveBattleCard (новый файл: красная рамка border-site-red/40 + тонирующий слой bg-site-red/[0.06] без freestyle-градиентов, пульсирующая красная точка + «Бой идёт» + «{локация} · Ход N», полоса очереди ходов с 34px кругами-инициалами — текущий с золотой рамкой и outline-кольцом, остальные затемнены; колонки «Ваш отряд» (зелёный тинт, HP+MP через MiniStatBar) / «Противники» (красный тинт, только HP), мёртвые → opacity-50 + «Выбыл», футер «Перейти к бою» btn-blue + ArrowRight на существующий маршрут /location/{locationId}/battle/{battleId}). В api/battles.ts добавлены типы BattlePreview* (participant_id/team — числовые строки по отклонениям T2, логика сторон через is_ally) и fetchBattlePreview() на дефолтном axios-инстансе с JWT-интерцепторами. Поток: mount → /in-battle → при in_battle однократный /preview без поллинга; 404 (гонка завершения боя) → тихий фолбэк на строку «Нет активного боя» без тоста; 5xx/network → видимая красная строка с русской ошибкой (вкл. падение самого /in-battle). Статистика — 4× StatTile (grid-cols-2 lg:grid-cols-4), фильтры — два ряда FilterChips (типы с цветными точками / результаты) с сохранением текущей параметровой логики истории, строки истории рестайлены (дата mono, оппоненты truncate, бейдж типа в дизайн-токенах вместо yellow/purple, пилюля результата win/loss с нейтральным фолбэком), пагинация Назад/Далее + строка «Страница X из Y» сохранены, EmptyState для пустой истории (History) и пустого фильтра (Swords). Проверки: npx tsc --noEmit — 0 ошибок; npm run build (уникальный outDir /scratchpad/build-T7) — exit 0.
[LOG] 2026-07-17 19:10 — Reviewer: начал проверку T13 (автопроверки + код-ревью + live-верификация всех 7 вкладок на 1280px и 360px).
[LOG] 2026-07-17 20:05 — Reviewer: проверка завершена, результат FAIL (Review #1). Все автопроверки зелёные (tsc 0 ошибок, build OK, py_compile OK, pytest: party 28, battle 376, skills 170 passed). Live-верификация: 6 из 7 вкладок без ошибок консоли, композиция по мокапу, мобильная версия 360px без горизонтального скролла. Найдено 2 дефекта (оба Frontend): (1) SkillsTab — регистр skill_type: БД/API отдают 'Attack'/'Defense'/'Support', а фильтр/бейджи/иконки сравнивают с lowercase — новый фильтр по типу всегда пуст (подтверждено live); (2) QuestsTab — поле задачи в API называется objective_id, а не id → key={obj.id} undefined → React key warning в консоли. Детали, точные строки и скриншоты — в секции 5. Ожидаю фиксы Frontend Developer, затем Review #2.
[LOG] 2026-07-17 21:00 — Frontend Dev: исправлены оба дефекта Review #1. (1) SkillsTab: добавлен хелпер normalizeSkillType() (toLowerCase в одной точке), нормализация применена в фильтре и при рендере карточки — лейблы/бейджи/фолбэк-иконки и чипы фильтра работают с 'Attack'/'Defense'/'Support' из API. (2) QuestsTab: поле QuestObjective.id переименовано в objective_id (по схеме ObjectiveProgressRead locations-service), key={obj.objective_id} в QuestDetail; других использований obj.id в директории нет. Проверки: npx tsc --noEmit — 0 ошибок; npm run build — exit 0. Live (localhost, админ, персонаж id 1): фильтр «Атака» показывает «Мощный удар», бейджи АТАКА/ПОДДЕРЖКА рендерятся; деталь задания (временный квест с 2 задачами, создан и полностью удалён после проверки) — без React key warning, 0 ошибок консоли. Статусы дефектов в §5 → FIXED, готово к Review #2.
[LOG] 2026-07-17 21:30 — Frontend Dev: задача T14 завершена (затемнение дизайн-системы по мокапу, только токены/CSS-слой). tailwind site.bg и --gray-background → rgba(9,10,16,0.62) (полупрозрачные панели: gray-bg тоже). Непрозрачные плавающие поверхности → rgba(14,15,21,0.98): dropdown-menu, modal-content, site-tooltip, context-menu (фон + градиент-заливка рамки), category-icon-active (заливка трюка градиентной рамки — должна быть непрозрачной). body: background-color #05060a + мягкий НЕагрессивный оверлей linear-gradient(180deg, rgba(5,6,10,0.35), rgba(5,6,10,0.55)) поверх background-main.png (мягче мокапа по решению пользователя); cover/fixed/center работают по-прежнему. Дополнение пользователя: в index.css добавлен @media (max-width: 640px) — высота ГОРИЗОНТАЛЬНОГО скроллбара gold-scrollbar/gold-scrollbar-wide → 3px (height затрагивает только горизонтальную ось; десктоп и вертикальные ширины не тронуты). docs/DESIGN-SYSTEM.md обновлён (§2 таблица цветов + заметка про непрозрачные поверхности, блок CSS-переменных, заметка про глобальный фон #05060a + мягкий градиент, §4 gray-bg). global.scss не менялся (миксин использует var). Проверки: grep rgba(35,35,41) по всему src и tailwind.config.js — 0 вхождений (и в компонентах тоже); npx tsc --noEmit — 0 ошибок; npm run build (outDir scratchpad/build-T14) — exit 0. Компонентные файлы не тронуты.
[LOG] 2026-07-17 22:00 — Reviewer: начал Review #2 (T15): проверка фиксов #1/#2, T14-затемнение, автопроверки, desktop-only live-обход 7 вкладок.
[LOG] 2026-07-17 22:50 — Reviewer: Review #2 завершён, результат PASS. Фикс #1 (normalizeSkillType) и фикс #2 (objective_id) корректны в коде и подтверждены live: фильтр «Атака» возвращает «Мощный удар», бейджи типов рендерятся, деталь задания без React key warning. T14 применён точно по решению пользователя: site.bg/gray-bg/--gray-background → rgba(9,10,16,0.62); модалки/дропдауны/тултипы/контекстные меню → rgba(14,15,21,0.98); body #05060a + мягкий градиент 0.35→0.55; мобильный горизонтальный скроллбар 3px только для gold-scrollbar-классов; DESIGN-SYSTEM.md §2 согласован с фактическими значениями. Автопроверки: tsc 0 ошибок, build OK, grep старого цвета — 0 вхождений; pytest пропущен обоснованно (бэкенд после Review #1 не менялся — подтверждено mtimes и git status). Live desktop: все 7 вкладок + главная + дропдаун персонажей в шапке, 0 ошибок консоли, затемнение подтверждено computed-стилями браузера. Временный квест для проверки создан через admin API и полностью удалён после. Скриншоты в scratchpad/review2/. Адаптив-проверки в браузере не выполнялись (решение пользователя). Секция 5: Review #2 = PASS; T15 в секции 4 → PASS.
[LOG] 2026-07-17 — PM: Review #2 PASS, фича закрыта (DONE), файл переименован в DONE-FEAT-151-profile-tabs-redesign.md
[LOG] 2026-07-17 23:40 — Frontend Dev: follow-up по фидбеку пользователя — чипы-фильтры выглядели как голый текст без рамки. В дизайн-систему добавлены классы `chip-outline` (рамка 1px rgba(255,255,255,.1) + заливка rgba(255,255,255,.04) + текст .65, hover → #fff) и `chip-outline-active` (золотой градиент rgba(240,217,92,.2→.05), рамка gold/50, текст #fff9b8) — форма (радиус) задаётся вызывающим (`rounded-full` для пилюль, `rounded-card` для рейла). Мигрированы: shared/FilterChips (все вкладки: Навыки/Задания/Бои/Титулы; счётчик активного чипа → text-gold-light/70), CraftTab/ProfessionRail (сохранены opacity-50/hover-80 для неактивных и золотое имя активной профессии), InventoryTab/CategorySidebar (те же классы, круглые иконочные чипы). Бейджи/лейблы и экшен-кнопки (Выбрать/Снять) не тронуты — не тогглы. DESIGN-SYSTEM.md §4 дополнен сниппетом. Проверки: tsc 0 ошибок, build exit 0; live desktop (/profile): Бои — оба ряда чипов с рамкой и заливкой, активный золотой; Навыки/Титулы/Крафт/Инвентарь единообразны; 0 новых ошибок консоли. Скриншоты: scratchpad/feat151-chips-{battles,craft,skills,titles,inventory}.png.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **7 вкладок профиля** (`/profile`) приведены к дизайну из Claude Design мокапа CharacterProfile: Навыки, Отряд, Сбор, Задания, Бои, Крафт, Титулы. Композиция — из мокапа; стили — только дизайн-система проекта; иконки — только из проекта (equipment SVG, lucide-react v1.7.0, картинки с бэкенда).
- **Общие примитивы** `ProfilePage/shared/`: FilterChips, SectionHeader, StatTile, MiniStatBar, EmptyState — переиспользуются всеми вкладками.
- **Бэкенд (3 сервиса, только форма ответов, без изменений БД):**
  - party-service: участники отряда обогащены `level`, `class_name`, `current/max HP+mana` (батч-чтение shared-таблиц, O(1) запросов);
  - battle-service: новый лёгкий `GET /battles/{battle_id}/preview` (JWT + проверка участия) — стороны, HP/MP c max, очередь ходов, ход, локация;
  - skills-service: базовые `cost_energy/cost_mana/cooldown` в списке навыков персонажа.
- **Задания** переведены в master-detail (журнал/детали), функциональность сдачи/отказа сохранена; **Крафт** — рейл всех 4 профессий (смена через существующую модалку с предупреждением); **Титулы** — добавлены фильтры, сохранены прогресс-бары условий и XP-бейджи; **Бои** — полная карточка активного боя + стат-плитки + чипы-фильтры + пагинация.
- **Обновление дизайн-системы (по запросу пользователя):** панели затемнены до `rgba(9,10,16,0.62)` из мокапа (`site.bg`, `gray-bg`, `--gray-background`); непрозрачные поверхности (модалки/дропдауны/тултипы/контекстные меню) → `rgba(14,15,21,0.98)`; фон страницы `#05060a` + мягкий градиент-оверлей; высота горизонтального скроллбара на мобильных ≤640px → 3px. `docs/DESIGN-SYSTEM.md` обновлён.
- **Тесты:** party 28 passed (10 новых), battle 376 passed (16 новых), skills 170 passed (7 новых). Фронтенд: `tsc --noEmit` и `npm run build` чистые.
- **Ревью:** Review #1 — FAIL (2 бага: регистр `skill_type`, поле `objective_id`), исправлены; Review #2 — PASS с live-проверкой всех вкладок на десктопе (адаптив в браузере не проверялся по решению пользователя).

### Что изменилось от первоначального плана
- Роли участников отряда (ДПС/Лекарь) из мокапа не существуют в игре — заменены чипом класса (решение пользователя).
- «нужен лекарь» в приглашениях опущено (нет данных).
- Вкладки «Перки» и «История постов» из мокапа не входили в задачу и не тронуты; таб-бар не менялся.
- participant_id/team в preview — числовые строки (реальные данные), сторона определяется по `is_ally`.
- Иконки сбора: Pickaxe/Sprout/Axe (проверены в lucide v1.7.0).

### Оставшиеся риски / follow-up задачи
- Заметка в CLAUDE.md §7 «battle-service без Alembic» устарела (Alembic там есть) — стоит поправить отдельно.
- Памятка/скилл live-verification-auth упоминали `email` в теле логина — после FEAT-150 поле называется `identifier` (память обновлена, скилл — при следующем касании).
- Пре-существующие не-токен цвета в нетронутых файлах (ResolvedSkillCard, крафт-модалки) — вне скоупа, можно мигрировать при следующей правке этих файлов.
- У персонажа id 2 нет строк атрибутов (404-тосты на вкладке «Персонаж») — данные песочницы, не код.
- Побочный эффект ревью: тестовому персонажу id 1 выбрана профессия «Кузнец» (первичный выбор для проверки рейла), активный персонаж админа переключён на «Имяперсонажа».
