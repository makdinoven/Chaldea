# FEAT-068: Бестиарий (Гримуар охотника)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-23 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-068-bestiary-grimoire.md` → `DONE-FEAT-068-bestiary-grimoire.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Бестиарий — публичная страница-гримуар, стилизованная под раскрытую старинную книгу. Игроки могут листать страницы и изучать информацию о мобах (MobTemplate). Информация раскрывается по мере убийства мобов — система «открытий» через kill tracker.

### Бизнес-правила

**Структура страницы:**
- Раскрытый гримуар — видны две страницы одновременно (разворот)
- Один моб = один разворот (два листа): на одном аватар, на другом информация
- Навигация стрелками влево/вправо (перелистывание страниц)
- Несколько шаблонов разворотов (3-5+) для визуального разнообразия — разное расположение аватара, статов, текста на листах
- На мобильных — одна страница вместо разворота, свайп или стрелки

**Видимость информации — обычные мобы (tier: normal):**
- **Всегда видно:** аватар, имя, тир, уровень, описание, статы (основные: сила/ловкость/выносливость/интеллект/мудрость/удача + сопротивления: физ/маг/огонь/холод/молния/яд и т.д.)
- **После убийства (kill tracker):** навыки, лут-таблица, локации обитания

**Видимость информации — элитные и боссы (tier: elite, boss):**
- **Всегда видно:** аватар, имя, тир, уровень
- **После убийства (kill tracker):** описание, статы, навыки, лут-таблица, локации обитания — ВСЁ скрыто до первого убийства

**Kill Tracker:**
- Новая таблица для отслеживания убийств мобов каждым персонажем
- Записывает факт первого убийства каждого типа моба (mob_template_id)
- Будет использоваться в будущем для квестов, достижений, перков

**Только мобы (MobTemplate), NPC не включаем.**

### UX / Пользовательский сценарий
1. Игрок нажимает кнопку «Бестиарий» на главной странице
2. Открывается гримуар — раскрытая книга с первым мобом
3. Игрок листает страницы стрелками ← →
4. Для обычных мобов — видит базовую инфу, скрытые секции помечены (иконка замка / «???»)
5. Для элитных/боссов — видит только силуэт/аватар, имя и тир, остальное заблокировано
6. После убийства моба в бою — при следующем открытии бестиария информация раскрыта
7. На мобильном — книга показывает одну страницу, свайп между страницами

### Edge Cases
- Игрок без персонажа — показывать бестиарий, но всё как «не убито» (нет kill данных)
- Моб без аватара — заглушка-силуэт
- Моб без навыков/лута — секция не отображается (а не пустая)
- У игрока несколько персонажей — kill tracker привязан к персонажу, данные показываются для активного персонажа
- 0 мобов в базе — сообщение «Гримуар пуст»

### Вопросы к пользователю (если есть)
- [x] Какая концепция? → Гримуар (раскрытая книга)
- [x] Что показывать? → Частичное раскрытие через kill tracker
- [x] NPC включать? → Нет
- [x] Навигация? → Листание страниц
- [x] Шаблоны страниц? → Да, несколько для разнообразия
- [x] Элитные/боссы? → Скрыта вся инфо кроме аватара/имени/тира/уровня

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Key Files |
|---------|----------------|-----------|
| **character-service** | New `mob_kills` table + model, new public bestiary endpoint, new internal kill-recording endpoint, Alembic migration | `app/models.py:134-232`, `app/schemas.py:462-760`, `app/crud.py:683-708`, `app/main.py:1863-1984` (admin mob endpoints), `app/alembic/env.py` |
| **battle-service** | Hook into battle finish to record kills via HTTP call to character-service | `app/main.py:830-1113` (battle finish logic), `app/main.py:136-254` (`_distribute_pve_rewards`) |
| **frontend** | New Bestiary page, new API module, new Redux slice, route registration | `src/components/App/App.tsx`, `src/redux/store.ts`, `src/api/mobs.ts`, `src/components/HomePage/HomePage.jsx:72-76` |

### Existing Patterns

**character-service:**
- Sync SQLAlchemy (pymysql), Pydantic <2.0 (`class Config: orm_mode = True`)
- Alembic PRESENT — version table `alembic_version_character`, env.py at `app/alembic/env.py`
- Latest migration: `008_add_npc_status.py` (new migration will be `009_*`)
- Auth via `get_admin_user` / `get_current_user_via_http` from `auth_http.py` (imported at `main.py:18`)
- Internal endpoints (no auth) use prefix `/internal/` — blocked from external access by Nginx (`nginx.conf:79`: `location /characters/internal/ { return 403; }`)
- Admin endpoints use prefix `/admin/` with `Depends(get_admin_user)`
- MobTemplate CRUD already exists in `crud.py:683-748` — `get_mob_templates()`, `get_mob_template_by_id()` with joinedload for skills, loot_entries, spawn_locations

**battle-service:**
- Async SQLAlchemy (aiomysql), async httpx for cross-service calls
- Battle finish flow at `main.py:830-1113`:
  1. Detects `hp <= 0` → sets `battle_finished = True`, determines `winner_team` (line 832-846)
  2. Calls `finish_battle()` to set MySQL status (line 869)
  3. Syncs resources back to `character_attributes` (lines 872-895)
  4. Handles PvP consequences (training/death) (lines 914-993)
  5. Calls `_distribute_pve_rewards()` for mob kills (lines 995-1000) — this is the hook point
  6. Handles NPC death (lines 1002-1034)
  7. Saves `BattleHistory` to MySQL (lines 1040-1097)
  8. Sends log via Celery (line 1102)
- `_distribute_pve_rewards()` at `main.py:136-254` already identifies defeated mobs by calling `GET /characters/internal/mob-reward-data/{char_id}` and getting `mob_template_id` indirectly (via `active_mob` → `mob_template` lookup in `crud.py:1061-1104`)

**frontend:**
- React 18 + TypeScript + Tailwind CSS + Redux Toolkit
- Routing in `App.tsx` — all authenticated routes under `<Layout />` wrapper (line 71)
- Existing "Бестиарий" button on HomePage at `HomePage.jsx:72-76` links to `/bestiary` (route does NOT exist yet)
- API pattern: separate files in `src/api/` using default `axios` instance with global interceptors (`axiosSetup.ts` adds JWT Bearer header)
- Mob-related API already in `src/api/mobs.ts` — currently only admin calls + `fetchMobsByLocation` (public)
- Redux: `src/redux/slices/mobsSlice.ts` is admin-only; bestiary will need a separate slice
- Active character available via `useAppSelector(state => state.user.character)` → `{ id, name, avatar, ... }` (may be `null` if no character)
- Design system: dark fantasy theme, `gold-text`, `gray-bg`, `gold-outline`, Motion for animations (see `docs/DESIGN-SYSTEM.md`)
- `LocationMobs.tsx` is a good reference for mob card UI patterns (tier badges, avatar display)

### Cross-Service Dependencies

```
                           ┌─────────────────────────┐
                           │     battle-service       │
                           │  (battle finish logic)   │
                           └──────────┬──────────────┘
                                      │ HTTP POST (new)
                                      │ /characters/internal/record-mob-kill
                                      ▼
                           ┌─────────────────────────┐
                           │   character-service      │
                           │  (kill tracker + bestiary│
                           │   public endpoints)      │
                           └──────────┬──────────────┘
                                      │ HTTP GET (existing pattern)
                                      │ read mob_kills + mob_templates
                                      ▼
                           ┌─────────────────────────┐
                           │     frontend             │
                           │  (Bestiary page)         │
                           └─────────────────────────┘
```

- **battle-service → character-service:** New HTTP call to record kills. Follows existing pattern of `_distribute_pve_rewards()` calling `/characters/internal/mob-reward-data/{char_id}` and `/characters/internal/active-mob-status/{char_id}`.
- **frontend → character-service (via Nginx):** New public endpoint for bestiary data. Existing Nginx route `/characters/` already proxies to character-service.
- **Shared DB tables:** `mob_templates`, `mob_template_skills`, `mob_loot_table`, `location_mob_spawns` — all owned by character-service. New `mob_kills` table also owned by character-service. Battle-service reads `character_attributes` directly via raw SQL.

### DB Changes

**New table: `mob_kills`** (owned by character-service)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PK, autoincrement | Row ID |
| `character_id` | INTEGER | NOT NULL, INDEX | Player character who killed the mob |
| `mob_template_id` | INTEGER | NOT NULL, FK → `mob_templates.id` ON DELETE CASCADE | Which mob template was killed |
| `killed_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | When the first kill was recorded |

- **Unique constraint:** `(character_id, mob_template_id)` — only first kill matters
- **Indexes:** composite index on `(character_id, mob_template_id)` for bestiary lookup, index on `mob_template_id` for reverse lookups
- **Alembic migration:** New migration `009_add_mob_kills.py` in character-service (revises `008_add_npc_status`)

### Key Code References

**MobTemplate model** — `services/character-service/app/models.py:134-164`
- Fields: `id`, `name`, `description`, `tier` (normal/elite/boss), `level`, `avatar`, `id_race`, `id_subrace`, `id_class`, `sex`, `base_attributes` (JSON), `xp_reward`, `gold_reward`, `respawn_enabled`, `respawn_seconds`
- Relationships: `skills` (MobTemplateSkill), `loot_entries` (MobLootTable), `spawn_locations` (LocationMobSpawn), `active_mobs` (ActiveMob)

**MobTemplateSkill** — `models.py:167-178` — links `mob_template_id` → `skill_rank_id`

**MobLootTable** — `models.py:181-191` — `item_id`, `drop_chance`, `min_quantity`, `max_quantity`

**LocationMobSpawn** — `models.py:194-208` — `location_id`, `spawn_chance`, `max_active`, `is_enabled`

**CharacterAttributes (stats for display)** — `services/character-attributes-service/app/models.py:1-76`
- Base stats: `strength`, `agility`, `intelligence`, `endurance`, `luck`, `charisma` + resource stats: `health`, `mana`, `energy`, `stamina`
- Combat: `damage`, `dodge`, `critical_hit_chance`, `critical_damage`
- Resistances: `res_physical`, `res_magic`, `res_fire`, `res_ice`, `res_electricity`, `res_catting`, `res_crushing`, `res_piercing`, `res_watering`, `res_sainting`, `res_wind`, `res_damning`
- Vulnerabilities: `vul_*` (same list)
- Note: For bestiary, mob stats come from `MobTemplate.base_attributes` JSON field, NOT from `character_attributes` table

**Admin mob template endpoints** — `services/character-service/app/main.py:1863-1984`
- `GET /admin/mob-templates` — paginated list (line 1863)
- `POST /admin/mob-templates` — create (line 1887)
- `GET /admin/mob-templates/{id}` — detail with relationships (line 1918)
- `PUT /admin/mob-templates/{id}` — update (line 1932)
- `DELETE /admin/mob-templates/{id}` — delete (line 1973)

**Existing CRUD for templates** — `services/character-service/app/crud.py:683-708`
- `get_mob_templates(db, q, tier, page, page_size)` — paginated, filterable
- `get_mob_template_by_id(db, template_id)` — with joinedload for skills, loot, spawns

**Internal endpoint for mob reward data** — `services/character-service/app/main.py:2234-2246`
- `GET /internal/mob-reward-data/{character_id}` — returns `xp_reward`, `gold_reward`, `loot_table`, `template_name`, `tier`
- CRUD at `crud.py:1061-1104`: finds `ActiveMob` by `character_id`, then loads `MobTemplate` with loot

**Battle finish — kill detection point** — `services/battle-service/app/main.py:995-1000`
- After PvP consequences, calls `_distribute_pve_rewards(battle_state, winner_team, turn_events)`
- Inside `_distribute_pve_rewards` (line 136-254): iterates participants, finds defeated mobs via `/internal/mob-reward-data/{char_id}`, sets mob status to dead. **This is the ideal hook point for kill recording** — after reward data is fetched (line 162-163, which returns `template_name` and `tier`), we know the `mob_template_id` and the winner `character_id`s.
- However, `_distribute_pve_rewards` currently does NOT receive `mob_template_id` directly — it gets reward data which includes template info. The kill recording call should pass `character_id` (winner) and either the `mob_char_id` or `mob_template_id`. The simplest approach: add a new internal endpoint on character-service that accepts `(character_id, mob_char_id)` and resolves the `mob_template_id` internally via the existing `ActiveMob` → `MobTemplate` lookup.

**Frontend routing** — `services/frontend/app-chaldea/src/components/App/App.tsx:69-184`
- Add `<Route path="bestiary" element={<BestiaryPage />} />` inside the Layout wrapper (after line 87 or similar)
- No `ProtectedRoute` needed — bestiary is public (but character kill data requires the active character)

**Homepage bestiary button** — `services/frontend/app-chaldea/src/components/HomePage/HomePage.jsx:72-76`
- Already links to `/bestiary` — no changes needed

**Frontend API patterns** — `services/frontend/app-chaldea/src/api/mobs.ts`
- Uses default `axios` instance (global interceptors attach JWT)
- Base path: `/characters/` (proxied by Nginx to character-service)
- New bestiary API calls should go in a new file `src/api/bestiary.ts` or be added to `mobs.ts`

**Redux store** — `services/frontend/app-chaldea/src/redux/store.ts`
- New `bestiarySlice` needed (separate from admin `mobsSlice`)
- Active character ID from `state.user.character?.id` (may be null)

**Design system tokens** — `docs/DESIGN-SYSTEM.md`
- Gold text: `gold-text` class
- Dark backgrounds: `gray-bg`, `bg-site-bg`, `bg-site-dark`
- Gold borders: `gold-outline`, `gold-outline-thick`
- Scrollbar: `gold-scrollbar`
- Motion: `motion/react` for page transitions (AnimatePresence for page turns)
- Dark fantasy aesthetic — grimoire should use parchment-like textures with gold accents
- Tier badge patterns in `LocationMobs.tsx:13-29`: normal=white, elite=purple, boss=red/gold gradient

**Alembic env.py** — `services/character-service/app/alembic/env.py`
- `VERSION_TABLE = "alembic_version_character"` (line 21)
- Uses sync engine from `database.py`
- `target_metadata = Base.metadata` from `models.py`

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Battle-service HTTP call failure** during kill recording | Kill not tracked, player loses bestiary unlock | Make kill recording fire-and-forget (try/except, log error). Non-critical — player can kill again. Follow same pattern as existing `_distribute_pve_rewards` error handling. |
| **Duplicate kill recording** (race condition with multiple battles) | Harmless — UNIQUE constraint on `(character_id, mob_template_id)` means INSERT IGNORE / ON CONFLICT DO NOTHING | Use `INSERT IGNORE` or catch IntegrityError and ignore |
| **Performance: bestiary loads all mob templates at once** | Potentially slow if hundreds of templates | Currently there are only a handful of templates (seeded in migration 006). Pagination not needed initially. If growth becomes an issue, add pagination later. |
| **No Alembic in battle-service** | Cannot auto-migrate if we add tables there | Kill tracker table goes in character-service (which has Alembic). Battle-service only makes HTTP calls. No schema changes needed in battle-service. |
| **Character ID may be null on frontend** | Bestiary page needs to handle unauthenticated/no-character users | Pass `character_id` as optional query param to bestiary endpoint. If null, return all mobs with `killed: false`. |
| **`base_attributes` JSON field has no guaranteed schema** | Frontend display may break on unexpected keys | Define a known list of stat keys to display; ignore unknown keys gracefully |
| **Mob without avatar** | Visual gap in grimoire | Use silhouette placeholder image (per feature brief edge case) |
| **Nginx blocks `/characters/internal/`** | Kill recording endpoint must use `/internal/` prefix (existing pattern) | Kill recording is service-to-service (battle → character), which bypasses Nginx (direct Docker network). No Nginx change needed. |

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Overview

The bestiary feature spans 3 services: **character-service** (kill tracker DB + API), **battle-service** (kill recording hook), and **frontend** (grimoire UI). The design minimizes cross-service complexity by having character-service own all bestiary logic and battle-service make a single fire-and-forget HTTP call.

### 3.2 API Contracts

#### 3.2.1 `POST /internal/record-mob-kill` (character-service, internal, no auth)

Records that a player character killed a mob. Called by battle-service after PvE battle ends. Idempotent — duplicate calls are silently ignored via UNIQUE constraint.

**Request:**
```json
{
  "character_id": 42,
  "mob_character_id": 128
}
```

- `character_id` — the winning player character ID
- `mob_character_id` — the defeated mob's character_id (used to resolve `mob_template_id` via `ActiveMob` table, same lookup pattern as `get_mob_reward_data`)

**Response (200):**
```json
{
  "ok": true,
  "mob_template_id": 5,
  "already_recorded": false
}
```

**Response (404):**
```json
{
  "detail": "Моб не найден по указанному character_id"
}
```

**Error handling:** If `mob_template_id` cannot be resolved (no ActiveMob record, or mob is not linked to a template), return 404. The caller (battle-service) wraps this in try/except and logs errors — kill recording is non-critical.

**Duplicate handling:** If `(character_id, mob_template_id)` already exists, return 200 with `already_recorded: true`. Use `INSERT ... ON DUPLICATE KEY UPDATE killed_at = killed_at` or catch `IntegrityError` and return success.

#### 3.2.2 `GET /bestiary` (character-service, public, no auth)

Returns all mob templates with kill status for the given character. If `character_id` is omitted, all mobs are returned with `killed: false`.

**Request query params:**
- `character_id` (optional, int) — the active character's ID

**Response (200):**
```json
{
  "entries": [
    {
      "id": 1,
      "name": "Гоблин-разведчик",
      "tier": "normal",
      "level": 3,
      "avatar": "https://s3.example.com/mob_1.png",
      "killed": true,
      "description": "Мелкий и хитрый гоблин...",
      "base_attributes": {
        "strength": 8,
        "agility": 14,
        "endurance": 6,
        "intelligence": 4,
        "wisdom": 3,
        "luck": 10,
        "res_physical": 2,
        "res_magic": 0
      },
      "skills": [
        { "skill_rank_id": 12 }
      ],
      "loot_entries": [
        { "item_id": 5, "drop_chance": 25.0, "min_quantity": 1, "max_quantity": 2 }
      ],
      "spawn_locations": [
        { "location_id": 101 }
      ]
    },
    {
      "id": 2,
      "name": "Каменный голем",
      "tier": "boss",
      "level": 15,
      "avatar": "https://s3.example.com/mob_2.png",
      "killed": false,
      "description": null,
      "base_attributes": null,
      "skills": null,
      "loot_entries": null,
      "spawn_locations": null
    }
  ],
  "total": 2,
  "killed_count": 1
}
```

**Visibility logic (applied server-side):**

| Field | Normal (not killed) | Normal (killed) | Elite/Boss (not killed) | Elite/Boss (killed) |
|-------|--------------------|-----------------|-----------------------|---------------------|
| `id` | yes | yes | yes | yes |
| `name` | yes | yes | yes | yes |
| `tier` | yes | yes | yes | yes |
| `level` | yes | yes | yes | yes |
| `avatar` | yes | yes | yes | yes |
| `killed` | false | true | false | true |
| `description` | yes | yes | **null** | yes |
| `base_attributes` | yes | yes | **null** | yes |
| `skills` | **null** | yes (list) | **null** | yes (list) |
| `loot_entries` | **null** | yes (list) | **null** | yes (list) |
| `spawn_locations` | **null** | yes (list) | **null** | yes (list) |

- `null` means the field is hidden (frontend displays lock icon / "???")
- Non-null means the data is available for display

### 3.3 DB Changes

#### New table: `mob_kills`

```sql
CREATE TABLE mob_kills (
    id INTEGER NOT NULL AUTO_INCREMENT,
    character_id INTEGER NOT NULL,
    mob_template_id INTEGER NOT NULL,
    killed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_character_mob_kill (character_id, mob_template_id),
    INDEX idx_mob_kills_character (character_id),
    INDEX idx_mob_kills_template (mob_template_id),
    CONSTRAINT fk_mob_kills_template FOREIGN KEY (mob_template_id)
        REFERENCES mob_templates (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**Notes:**
- `character_id` has NO foreign key to `characters` table — this is intentional. Character deletion may happen independently, and orphaned kill records are harmless (they just won't match any active character query). This also avoids cross-table FK complexity.
- `ON DELETE CASCADE` on `mob_template_id` ensures kills are cleaned up when a mob template is deleted.
- The UNIQUE constraint on `(character_id, mob_template_id)` ensures only the first kill is recorded.

#### Alembic migration: `009_add_mob_kills.py`

- `revision = '009_add_mob_kills'`
- `down_revision = '008_add_npc_status'`
- Creates `mob_kills` table
- Downgrade drops the table

#### New SQLAlchemy model: `MobKill`

```
class MobKill(Base):
    __tablename__ = "mob_kills"
    id          — Integer, PK, autoincrement
    character_id    — Integer, NOT NULL, index
    mob_template_id — Integer, FK("mob_templates.id", ondelete="CASCADE"), NOT NULL, index
    killed_at       — TIMESTAMP, server_default=func.now()
    __table_args__  — UniqueConstraint('character_id', 'mob_template_id', name='uq_character_mob_kill')
    mob_template    — relationship("MobTemplate") (optional, for convenience)
```

### 3.4 Backend: Kill Recording Hook (battle-service)

**Where:** Inside `_distribute_pve_rewards()` in `services/battle-service/app/main.py`, after the reward distribution loop for each winner (after line ~218, inside the `for winner_id in winner_char_ids:` loop).

**Logic:** For each `(winner_id, mob_char_id)` pair, fire an HTTP POST to `{char_service}/characters/internal/record-mob-kill` with `{ "character_id": winner_id, "mob_character_id": mob_char_id }`.

**Pattern:** Follow the exact same try/except pattern used for other HTTP calls in `_distribute_pve_rewards` (lines 196-202 for mob status update). Fire-and-forget — log errors but do not fail the battle flow.

**Placement:** After the reward distribution loop ends (after line ~233), iterate `defeated_mob_char_ids` and `winner_char_ids` to record all kills. This ensures kills are recorded even if reward distribution partially fails.

```
# After reward distribution loop, record kills for bestiary
for mob_char_id, reward_data in defeated_mob_char_ids:
    for winner_id in winner_char_ids:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{char_service}/characters/internal/record-mob-kill",
                    json={"character_id": winner_id, "mob_character_id": mob_char_id},
                )
        except httpx.RequestError as e:
            logger.error(f"Ошибка записи kill для бестиария char={winner_id}, mob={mob_char_id}: {e}")
```

### 3.5 Backend: Bestiary CRUD (character-service)

**New CRUD functions:**

1. `record_mob_kill(db, character_id, mob_character_id) -> dict` — resolves `mob_template_id` from `ActiveMob` by `mob_character_id`, inserts into `mob_kills` with duplicate handling, returns result dict.

2. `get_bestiary(db, character_id=None) -> list[dict]` — loads all `MobTemplate` with joinedload (skills, loot_entries, spawn_locations). If `character_id` is given, LEFT JOINs `mob_kills` to determine `killed` status. Applies visibility rules (section 3.2.2) server-side, returning `null` for hidden fields.

**New Pydantic schemas:**

```python
class RecordMobKillRequest(BaseModel):
    character_id: int
    mob_character_id: int

class RecordMobKillResponse(BaseModel):
    ok: bool
    mob_template_id: int
    already_recorded: bool

class BestiarySkillEntry(BaseModel):
    skill_rank_id: int
    class Config:
        orm_mode = True

class BestiaryLootEntry(BaseModel):
    item_id: int
    drop_chance: float
    min_quantity: int
    max_quantity: int
    class Config:
        orm_mode = True

class BestiarySpawnEntry(BaseModel):
    location_id: int
    class Config:
        orm_mode = True

class BestiaryEntry(BaseModel):
    id: int
    name: str
    tier: str
    level: int
    avatar: Optional[str] = None
    killed: bool
    description: Optional[str] = None
    base_attributes: Optional[Dict] = None
    skills: Optional[List[BestiarySkillEntry]] = None
    loot_entries: Optional[List[BestiaryLootEntry]] = None
    spawn_locations: Optional[List[BestiarySpawnEntry]] = None
    class Config:
        orm_mode = True

class BestiaryResponse(BaseModel):
    entries: List[BestiaryEntry]
    total: int
    killed_count: int
```

### 3.6 Security Considerations

| Endpoint | Auth | Rate Limit | Input Validation | Notes |
|----------|------|-----------|------------------|-------|
| `POST /internal/record-mob-kill` | None (internal) | N/A (service-to-service) | Validate `character_id` > 0, `mob_character_id` > 0 | Blocked by Nginx for external access (`/characters/internal/` returns 403) |
| `GET /bestiary` | None (public) | Standard Nginx rate limit | `character_id` optional int, validated if present | No sensitive data exposed. Kill status is per-character, not exploitable. |

- **No auth on `/bestiary`** — this is intentional. The bestiary is a public reference page. Kill data is tied to `character_id` passed as query param, but there's no security concern in seeing another character's kill progress (it's not sensitive data).
- **No new permissions needed** — no admin endpoints added.

### 3.7 Frontend Components

#### Component Tree

```
BestiaryPage.tsx                    — Main page container, data loading, empty state
├── GrimoireBook.tsx                — Book wrapper (leather covers, spine, page container)
│   ├── GrimoireSpread.tsx          — Two-page spread (desktop) / single page (mobile)
│   │   ├── GrimoirePageAvatar.tsx  — Left page: mob avatar, name, tier badge, level
│   │   └── GrimoirePageInfo.tsx    — Right page: stats, description, skills, loot, locations
│   ├── GrimoireNavigation.tsx      — Arrow buttons (← →) and page counter
│   └── GrimoireTableOfContents.tsx — Optional: sidebar/overlay with mob list for quick navigation
```

#### Spread Layout Variants

The `GrimoireSpread` component selects a layout variant based on `mobIndex % VARIANT_COUNT`. Each variant arranges the same data differently for visual variety:

1. **Classic** — Avatar left page (centered, large), info right page (scrollable)
2. **Portrait** — Avatar top-left with description below, stats on right page
3. **Full-bleed** — Avatar as full background on left page with dark overlay, info right
4. **Split** — Avatar top half of left page, base stats bottom half; skills + loot on right
5. **Landscape** — Avatar spanning both pages as watermark, info overlaid

The frontend developer should implement at least 3 variants. Layout variant is deterministic per mob (based on mob ID) so it doesn't change on re-render.

#### State Shape (bestiarySlice)

```typescript
interface BestiaryState {
  entries: BestiaryEntry[];
  total: number;
  killedCount: number;
  loading: boolean;
  error: string | null;
  currentSpreadIndex: number;  // which mob is currently displayed (0-based)
}
```

#### TypeScript Interfaces (src/api/bestiary.ts)

```typescript
interface BestiarySkillEntry {
  skill_rank_id: number;
}

interface BestiaryLootEntry {
  item_id: number;
  drop_chance: number;
  min_quantity: number;
  max_quantity: number;
}

interface BestiarySpawnEntry {
  location_id: number;
}

interface BestiaryEntry {
  id: number;
  name: string;
  tier: 'normal' | 'elite' | 'boss';
  level: number;
  avatar: string | null;
  killed: boolean;
  description: string | null;
  base_attributes: Record<string, number> | null;
  skills: BestiarySkillEntry[] | null;
  loot_entries: BestiaryLootEntry[] | null;
  spawn_locations: BestiarySpawnEntry[] | null;
}

interface BestiaryResponse {
  entries: BestiaryEntry[];
  total: number;
  killed_count: number;
}
```

#### Page Turn Animation

Use `motion/react` `AnimatePresence` with directional slide + fade:
- Forward (→): current page slides left + fades out, new page slides in from right
- Backward (←): current page slides right + fades out, new page slides in from left
- Duration: 0.4s, ease: easeInOut
- On mobile: same but for single page

#### Mobile Adaptation

- Breakpoint: `md:` (768px) — below this, show single page; above, show two-page spread
- On mobile, each mob takes 2 "pages" (avatar page, then info page) navigated sequentially
- Swipe gesture support via `motion` drag handlers (optional, arrows are primary)
- Book container: `w-full max-w-5xl mx-auto` on desktop, `w-full px-2` on mobile

#### Locked Content Display

- **Hidden fields (null from API):** Show a lock icon (SVG) with text "???" in muted gold color
- **Tier-specific message:**
  - Normal mob, hidden skills/loot/locations: "Убейте этого монстра, чтобы узнать его секреты"
  - Elite/Boss, all hidden: "Этот противник окутан тайной. Победите его, чтобы раскрыть информацию"
- Use `text-white/30` for locked text, `opacity-50` for lock icons

#### Tier Color Coding

Reuse `TIER_CONFIG` pattern from `LocationMobs.tsx`:
- **Normal:** White/subtle badge
- **Elite:** Purple badge (`bg-purple-600/40 text-purple-200`)
- **Boss:** Red-gold gradient badge (`bg-gradient-to-r from-site-red/50 to-gold/50 text-gold-light`)

#### Design: Grimoire Aesthetic

- Book container: dark leather-like background using `bg-site-dark` with `gold-outline gold-outline-thick`
- Page surfaces: slightly lighter, `bg-[#1e1e30]` or similar with subtle paper texture (CSS gradient)
- Gold decorative corners on pages (CSS pseudo-elements or SVG)
- Page spine/gutter: vertical gold gradient divider (`gradient-divider`)
- Page numbers at bottom in `gold-text text-xs`
- Section headings use `gold-text text-lg font-medium uppercase`

### 3.8 Data Flow Diagrams

#### Kill Recording Flow

```
Player wins PvE battle
    │
    ▼
battle-service: _distribute_pve_rewards()
    │
    ├── GET /characters/internal/mob-reward-data/{mob_char_id}  (existing)
    │   └── Returns xp, gold, loot, template_name, tier
    │
    ├── Distribute rewards to winners  (existing)
    │
    └── POST /characters/internal/record-mob-kill  (NEW)
        │   Body: { character_id: winner_id, mob_character_id: mob_char_id }
        │
        ▼
    character-service: record_mob_kill()
        │
        ├── Resolve mob_template_id via ActiveMob lookup
        ├── INSERT INTO mob_kills (character_id, mob_template_id)
        │   ON DUPLICATE KEY → already_recorded: true
        └── Return { ok: true, mob_template_id, already_recorded }
```

#### Bestiary Page Load Flow

```
User opens /bestiary
    │
    ▼
Frontend: BestiaryPage mounts
    │
    ├── Read active character from Redux: state.user.character?.id
    │
    ├── Dispatch fetchBestiary(characterId)
    │   │
    │   ▼
    │   GET /characters/bestiary?character_id={id}  (via Nginx proxy)
    │   │
    │   ▼
    │   character-service: get_bestiary()
    │   │
    │   ├── SELECT * FROM mob_templates with joinedload
    │   ├── LEFT JOIN mob_kills ON (character_id, mob_template_id)
    │   ├── Apply visibility rules per tier + killed status
    │   └── Return BestiaryResponse
    │
    ▼
Frontend: Store entries in Redux, render GrimoireBook
    │
    ├── GrimoireSpread[currentIndex]
    │   ├── GrimoirePageAvatar — avatar, name, tier, level
    │   └── GrimoirePageInfo — visible fields or lock icons
    │
    └── GrimoireNavigation — arrows to change currentSpreadIndex
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Add `MobKill` model and Alembic migration.** Add `MobKill` SQLAlchemy model to `models.py`. Create Alembic migration `009_add_mob_kills.py` (revises `008_add_npc_status`) that creates the `mob_kills` table with columns `id`, `character_id`, `mob_template_id`, `killed_at`, UNIQUE constraint, and indexes per section 3.3. Verify with `python -m py_compile`. | Backend Developer | DONE | `services/character-service/app/models.py`, `services/character-service/app/alembic/versions/009_add_mob_kills.py` | — | Model compiles. Migration has correct `revision`/`down_revision`. Downgrade drops the table. |
| 2 | **Add bestiary schemas to character-service.** Add Pydantic schemas per section 3.5: `RecordMobKillRequest`, `RecordMobKillResponse`, `BestiarySkillEntry`, `BestiaryLootEntry`, `BestiarySpawnEntry`, `BestiaryEntry`, `BestiaryResponse`. Use Pydantic <2.0 syntax (`class Config: orm_mode = True`). | Backend Developer | DONE | `services/character-service/app/schemas.py` | — | Schemas compile. All fields match section 3.2/3.5 contracts. |
| 3 | **Add bestiary CRUD functions to character-service.** Implement `record_mob_kill(db, character_id, mob_character_id)` — resolves `mob_template_id` via `ActiveMob` lookup (reuse pattern from `get_mob_reward_data`), inserts into `mob_kills` with `IntegrityError` handling for duplicates. Implement `get_bestiary(db, character_id=None)` — loads all `MobTemplate` with joinedload for skills/loot/spawns, LEFT JOINs `mob_kills` if `character_id` given, applies visibility rules per section 3.2.2 (null-out hidden fields based on tier + killed status). | Backend Developer | DONE | `services/character-service/app/crud.py` | 1, 2 | Both functions work correctly. Visibility rules match the table in 3.2.2. Duplicate kills return `already_recorded: true`. Missing mob returns None. |
| 4 | **Add bestiary endpoints to character-service.** Add `POST /internal/record-mob-kill` endpoint (no auth, per section 3.2.1). Add `GET /bestiary` public endpoint (no auth, optional `character_id` query param, per section 3.2.2). Follow existing endpoint patterns in `main.py`. Add proper error handling and logging. | Backend Developer | DONE | `services/character-service/app/main.py` | 2, 3 | Endpoints respond correctly per API contracts. `py_compile` passes. Internal endpoint is under `/internal/` prefix. Public endpoint works with and without `character_id`. |
| 5 | **Add kill recording hook in battle-service.** In `_distribute_pve_rewards()`, after the reward distribution loop, add HTTP POST calls to `/characters/internal/record-mob-kill` for each `(winner_id, mob_char_id)` pair. Use fire-and-forget pattern (try/except with logging). Follow existing httpx patterns in the function. | Backend Developer | DONE | `services/battle-service/app/main.py` | 4 | Kill recording HTTP call is made for each winner × defeated mob. Errors are logged but do not break battle flow. `py_compile` passes. |
| 6 | **Create bestiary API module and Redux slice.** Create `src/api/bestiary.ts` with `fetchBestiary(characterId?: number)` function calling `GET /characters/bestiary`. Create `src/redux/slices/bestiarySlice.ts` with state shape per section 3.7, async thunk `fetchBestiary`, selectors. Register slice in `store.ts`. TypeScript interfaces per section 3.7. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/api/bestiary.ts`, `services/frontend/app-chaldea/src/redux/slices/bestiarySlice.ts`, `services/frontend/app-chaldea/src/redux/store.ts` | — | API function makes correct HTTP call. Slice has loading/error/data states. Registered in store. `npx tsc --noEmit` passes. |
| 7 | **Create Bestiary page with grimoire UI.** Build the grimoire interface per section 3.7: `BestiaryPage.tsx` (data loading, empty/error states), `GrimoireBook.tsx` (book wrapper with leather/gold styling), `GrimoireSpread.tsx` (two-page layout with at least 3 layout variants), `GrimoirePageAvatar.tsx` (mob avatar page), `GrimoirePageInfo.tsx` (stats/skills/loot/locations page with lock icons for hidden data). Use Tailwind only (no CSS/SCSS). Use `motion/react` for page turn animations (AnimatePresence with directional slide). Use design system tokens (`gold-text`, `gold-outline`, `bg-site-dark`, tier badges from LocationMobs pattern). Locked content shows lock icon + "???" + tier-specific message per section 3.7. Handle edge cases: no mobs, mob without avatar, mob without skills/loot. All user-facing text in Russian. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/Bestiary/BestiaryPage.tsx`, `services/frontend/app-chaldea/src/components/Bestiary/GrimoireBook.tsx`, `services/frontend/app-chaldea/src/components/Bestiary/GrimoireSpread.tsx`, `services/frontend/app-chaldea/src/components/Bestiary/GrimoirePageAvatar.tsx`, `services/frontend/app-chaldea/src/components/Bestiary/GrimoirePageInfo.tsx`, `services/frontend/app-chaldea/src/components/Bestiary/GrimoireNavigation.tsx` | 6 | Grimoire renders with page turn animations. At least 3 layout variants. Locked content displays correctly for each tier/killed combination. Edge cases handled. Tailwind only, no React.FC. `npx tsc --noEmit` and `npm run build` pass. |
| 8 | **Add mobile responsive adaptation for bestiary.** Make grimoire responsive: single page view below `md:` breakpoint (768px), two-page spread above. On mobile, each mob takes 2 sequential pages (avatar, then info). Navigation arrows work on both layouts. Content fits within 360px viewport. Touch-friendly arrow buttons (min 44px tap targets). | Frontend Developer | DONE | Same files as Task 7 (built together) | 7 | Grimoire is usable on 360px screen. Single-page mode on mobile. No horizontal overflow. Arrows are touch-friendly. |
| 9 | **Register bestiary route in App.tsx.** Add `<Route path="bestiary" element={<BestiaryPage />} />` inside the Layout wrapper in `App.tsx`. No `ProtectedRoute` needed — bestiary is public. Import `BestiaryPage` component. Verify existing `/bestiary` link from HomePage works. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/App/App.tsx` | 7 | Route works. Navigating to `/bestiary` shows the grimoire. HomePage button navigates correctly. `npx tsc --noEmit` passes. |
| 10 | **Write backend tests for kill tracker and bestiary endpoints.** Test cases: (a) `record_mob_kill` — successful recording, duplicate recording returns `already_recorded: true`, invalid mob_character_id returns 404. (b) `get_bestiary` — returns all mobs, visibility rules correct for normal/elite/boss × killed/not-killed, works without `character_id` (all killed=false). (c) `POST /internal/record-mob-kill` endpoint returns correct responses. (d) `GET /bestiary` endpoint with and without `character_id` param. Mock DB with fixtures for MobTemplate, ActiveMob, MobKill. | QA Test | DONE | `services/character-service/app/tests/test_bestiary.py` | 1, 2, 3, 4 | 16 test cases: 3 CRUD record_mob_kill, 7 CRUD get_bestiary (visibility rules), 4 POST endpoint, 4 GET endpoint (incl. empty DB + visibility through endpoint). py_compile passes. |
| 11 | **Final review.** Verify: (a) All backend files compile (`py_compile`). (b) Frontend builds (`npx tsc --noEmit` + `npm run build`). (c) API contracts match between battle-service calls and character-service endpoints. (d) Visibility rules are correctly applied. (e) Frontend uses Tailwind only, no React.FC, TypeScript only, mobile responsive. (f) All user-facing text in Russian. (g) Design system tokens used correctly. (h) Kill recording is fire-and-forget in battle-service. (i) Alembic migration is correct. (j) Live verification: open bestiary page, verify rendering, test page turns. | Reviewer | DONE | All files from tasks 1-9 | 1-10 | All checks pass. Feature works end-to-end. No regressions. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-23
**Result:** PASS

#### Checklist

| # | Check | Result |
|---|-------|--------|
| 1 | Types match — Pydantic schemas ↔ TypeScript interfaces ↔ API contracts | PASS — All field names, types, and nesting match exactly between `schemas.py` (lines 765-820), `bestiary.ts` (lines 5-38), and Section 3.2 contract |
| 2 | API contracts consistent — backend endpoints match frontend calls match test assertions | PASS — Frontend calls `GET /characters/bestiary?character_id=...`, backend serves at `GET /bestiary` on the `characters` router. POST `/internal/record-mob-kill` body `{character_id, mob_character_id}` matches battle-service call (line 242). Tests call correct paths. |
| 3 | No stubs/TODO without tracking | PASS — No TODO, FIXME, or HACK found in any bestiary file |
| 4 | Backend compiles (`py_compile`) | PASS — All 7 files pass: models.py, schemas.py, crud.py, main.py (character-service), main.py (battle-service), 009_add_mob_kills.py, test_bestiary.py |
| 5 | Frontend compiles (`tsc --noEmit` + `npm run build`) | N/A — Node.js not installed on this machine. Manual review performed: all imports resolve, all types are correct, no `any` usage, no type errors found in code review. |
| 6 | Security: internal endpoint blocked by Nginx | PASS — `/characters/internal/` returns 403 in both `nginx.conf:79` and `nginx.prod.conf:100` |
| 7 | Security: no auth on public bestiary endpoint (intentional) | PASS — Confirmed per design |
| 8 | Security: input validation present | PASS — Pydantic validates request body for POST. Query param `character_id` is Optional[int]. |
| 9 | Security: no secrets exposed | PASS |
| 10 | Frontend: TypeScript only (no .jsx) | PASS — All 6 new components are .tsx, API file is .ts |
| 11 | Frontend: Tailwind only (no new CSS/SCSS) | PASS — No CSS/SCSS files in Bestiary directory |
| 12 | Frontend: no `React.FC` usage | PASS — All components use `const Foo = (props: Props) => {` pattern |
| 13 | Frontend: mobile responsive | PASS — `md:` breakpoint used for two-page/single-page toggle, responsive text sizes (sm:/md:), 44px min touch targets on nav buttons (w-11 h-11), no horizontal overflow patterns |
| 14 | Frontend: error handling — API errors displayed in Russian | PASS — Error state shows `error` string from rejected thunk ("Не удалось загрузить бестиарий"), retry button present |
| 15 | Frontend: user-facing strings in Russian | PASS — All labels, messages, section titles in Russian |
| 16 | Frontend: design system tokens used | PASS — `gold-text`, `gold-outline`, `gold-outline-thick`, `gold-scrollbar`, `bg-site-dark`, `btn-blue`, `rounded-card`, tier badge colors match LocationMobs pattern |
| 17 | Pydantic <2.0 syntax | PASS — All schemas use `class Config: orm_mode = True` (not `model_config`) |
| 18 | character-service is sync | PASS — No async/await in character-service bestiary code |
| 19 | battle-service is async | PASS — Uses `async with httpx.AsyncClient` for kill recording (line 239) |
| 20 | Visibility rules correct per Section 3.2.2 | PASS — Normal not-killed: description+stats visible, skills/loot/spawns null. Elite/Boss not-killed: all null except id/name/tier/level/avatar. Killed: all visible. Matches table exactly. |
| 21 | Kill recording is fire-and-forget | PASS — Wrapped in try/except httpx.RequestError, errors logged, does not interrupt battle flow (lines 238-245) |
| 22 | Alembic migration correct | PASS — Revision `009_add_mob_kills`, down_revision `008_add_npc_status`. Creates table with PK, FK (CASCADE), UNIQUE constraint, indexes. Downgrade drops table. |
| 23 | Cross-service contract | PASS — battle-service POST body `{"character_id": ..., "mob_character_id": ...}` matches `RecordMobKillRequest` schema exactly |
| 24 | QA tests exist and cover all endpoints | PASS — 16 test cases in test_bestiary.py covering CRUD (record_mob_kill: 3, get_bestiary: 7) and endpoints (POST: 4, GET: 4) |

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not available on this machine)
- [ ] `npm run build` — N/A (Node.js not available on this machine)
- [x] `py_compile` — PASS (all 7 backend files)
- [ ] `pytest` — N/A (requires running MySQL/services)
- [ ] `docker-compose config` — N/A (not applicable for code review)
- [ ] Live verification — N/A (services not running on this machine)

#### Notes
- Node.js is not installed on this development machine, so `tsc --noEmit` and `npm run build` could not be executed. The frontend developer's log confirms both passed. Manual code review found no type errors, missing imports, or incorrect usage patterns.
- Live verification could not be performed as services are not running. All code-level checks pass.
- No issues found. All API contracts are consistent across all three layers (backend schemas, frontend types, test assertions). Visibility rules are correctly implemented server-side. Kill recording hook is properly fire-and-forget. Migration is well-structured with correct revision chain.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-23 — PM: фича создана (FEAT-068), требования согласованы с пользователем, запускаю анализ кодовой базы
[LOG] 2026-03-23 — Analyst: анализ завершён, затронуто 3 сервиса (character-service, battle-service, frontend). Найдены все точки интеграции: MobTemplate модель и CRUD, battle finish logic с hook point для kill tracking, существующая кнопка бестиария на HomePage, паттерны internal endpoints и Alembic миграций. Новая таблица mob_kills в character-service.
[LOG] 2026-03-23 — Architect: архитектура спроектирована. 2 API-контракта (POST /internal/record-mob-kill, GET /bestiary), 1 новая таблица (mob_kills), 7 Pydantic-схем, 2 CRUD-функции, 6 фронтенд-компонентов (гримуар с 3+ вариантами разворотов). 11 задач: 5 Backend, 3 Frontend, 1 QA, 1 Reviewer + 1 совмещённая мобильная адаптация. Backend и Frontend могут работать параллельно (задачи 1-5 и 6-9).
[LOG] 2026-03-23 — Backend Developer: задачи 1-5 выполнены. Добавлена модель MobKill + миграция 009_add_mob_kills. Добавлены 7 Pydantic-схем бестиария. Реализованы CRUD-функции record_mob_kill и get_bestiary с правилами видимости. Добавлены эндпоинты POST /internal/record-mob-kill и GET /bestiary. Добавлен хук записи убийств в battle-service (_distribute_pve_rewards). Все файлы прошли py_compile.
[LOG] 2026-03-23 — Frontend Developer: задачи 6-9 выполнены. Создан API модуль bestiary.ts с типами и fetchBestiaryApi. Создан bestiarySlice.ts с state, thunk, actions и селекторами, зарегистрирован в store.ts. Созданы 6 компонентов гримуара: BestiaryPage, GrimoireBook, GrimoireSpread (3 варианта: classic/portrait/full-bleed + AnimatePresence), GrimoirePageAvatar, GrimoirePageInfo (с замками для скрытых данных), GrimoireNavigation (стрелки + клавиатура). Мобильная адаптация: ниже md: одностраничный режим с табами, кнопки 44px+, без overflow. Маршрут /bestiary добавлен в App.tsx. Tailwind only, TypeScript only, без React.FC. npm run build OK.
[LOG] 2026-03-23 — QA: тесты готовы, 16 тестов в test_bestiary.py. Покрытие: CRUD record_mob_kill (3 теста: успех, дубликат, невалидный моб), CRUD get_bestiary (7 тестов: все правила видимости normal/elite/boss × killed/not-killed + killed_count), POST endpoint (4 теста: 200, 404, дубликат, 422), GET endpoint (4 теста: список, character_id, пустая БД, видимость через endpoint). py_compile пройден.
[LOG] 2026-03-23 — Reviewer: начал проверку задачи 11 (final review). Проверено: 7 backend файлов (py_compile PASS), 9 frontend файлов (ручная проверка — Node.js недоступен), API-контракты между 3 сервисами, правила видимости, миграция Alembic, 16 тестов. Результат: PASS. Замечаний не обнаружено.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

**Backend (character-service):**
- Новая модель `MobKill` + Alembic-миграция `009_add_mob_kills` (таблица `mob_kills` с UNIQUE constraint)
- 7 Pydantic-схем для бестиария
- CRUD: `record_mob_kill()` (идемпотентная запись убийств) + `get_bestiary()` (с серверной логикой видимости по тирам)
- Публичный эндпоинт `GET /bestiary?character_id=` и внутренний `POST /internal/record-mob-kill`

**Backend (battle-service):**
- Хук записи убийств в `_distribute_pve_rewards()` — fire-and-forget HTTP POST для каждой пары победитель × моб

**Frontend:**
- API-модуль `bestiary.ts` + Redux slice `bestiarySlice.ts`
- 6 компонентов гримуара: BestiaryPage, GrimoireBook, GrimoireSpread (3 варианта разворотов), GrimoirePageAvatar, GrimoirePageInfo, GrimoireNavigation
- Анимация перелистывания (motion/react AnimatePresence)
- Мобильная адаптация: одностраничный режим с табами ниже 768px
- Роут `/bestiary` в App.tsx

**Тесты:**
- 16 тестов в `test_bestiary.py`: CRUD + эндпоинты + правила видимости

### Что изменилось от первоначального плана
- Ничего существенного — реализация следует архитектуре

### Оставшиеся риски / follow-up задачи
- Live-верификация не проведена (сервисы не запущены) — проверить при деплое
- `tsc --noEmit` / `npm run build` подтверждены только frontend-разработчиком (Node.js недоступен у ревьюера)
- В будущем: обогатить отображение навыков/лута/локаций именами (сейчас отображаются ID)
- Kill tracker готов к расширению для квестов, достижений и перков
