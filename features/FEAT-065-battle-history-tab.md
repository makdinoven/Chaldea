# FEAT-065: Battle History Tab in Character Profile

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-23 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Новая вкладка «Бои» в профиле персонажа (после «Задания»). Отображает текущий бой и полную историю боёв. Вкладка видна всем — и владельцу, и другим игрокам.

### Бизнес-правила
- Вкладка показывает: (1) текущий активный бой, (2) историю всех завершённых боёв.
- История хранится в MySQL (таблица `battle_history`) для быстрого доступа. MongoDB-логи остаются для детальных данных.
- История показывает: дата, противник(и), тип боя, результат (победа/поражение).
- Награды (XP, золото, лут) НЕ показываются — только победа/поражение.
- Статистика: всего боёв, побед, поражений, винрейт.
- Вкладка видна другим игрокам (публичная).
- Хранятся все бои за всё время.
- Пагинация для истории.

### UX / Пользовательский сценарий
1. Игрок открывает профиль персонажа (свой или чужой).
2. Переключается на вкладку «Бои» (после «Задания»).
3. Видит блок «Текущий бой» — карточка активного боя с кнопкой «Перейти к бою» (или «Нет активного боя»).
4. Ниже — статистика (всего/побед/поражений/винрейт).
5. Ниже — список завершённых боёв с пагинацией.
6. Опциональные фильтры: по типу (PvE/PvP), по результату (победа/поражение).

### Edge Cases
- Персонаж без боёв → "Ещё не участвовал в боях".
- Персонаж в бою → показать карточку с кнопкой перехода.
- Очень длинная история → пагинация (20 записей на страницу).

### Вопросы к пользователю
- [x] Эндпоинт для истории? → Делать как лучше (MySQL summary table).
- [x] Видна другим? → Да.
- [x] Глубина хранения? → Все бои за всё время (MySQL, легковесно).
- [x] Награды в истории? → Нет, только победа/поражение.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1. Character Profile Page

**Location:** `services/frontend/app-chaldea/src/components/ProfilePage/`

**Tab system:**
- `ProfileTabs.tsx` — renders a static `TABS` array with `{ key, label }` objects. Currently: `character`, `skills`, `quests`, `logs`, `titles`, `craft`.
- `ProfilePage.tsx` — owns `activeTab` state, uses a `switch` in `renderTabContent()` to pick the component. Most tabs after `quests` are `PlaceholderTab` stubs.
- Adding a new tab = (1) add entry to `TABS` array in `ProfileTabs.tsx`, (2) add `case` in `ProfilePage.tsx` switch, (3) create the tab component.

**Data flow:**
- `ProfilePage` reads `state.user.character` (the logged-in user's active character) and uses `character.id` as `characterId`.
- All data is loaded via `loadProfileData(characterId)` thunk in `profileSlice.ts`, which dispatches parallel fetches to multiple services.
- **Important:** The current profile page is **own-character only** — it reads from `state.user.character` and has no route parameter for viewing another character. Route: `/profile`.
- There is a separate `UserProfilePage` at `/user-profile/:userId` for viewing other users, but it does not have character tabs.
- Implication: The battles tab will initially work for the own character. Viewing another character's battles requires the `characterId` prop, which is already passed to each tab component — so data fetching is character-id-based and will work for any character_id once a public profile route is added.

**Existing tab pattern (QuestLogTab):**
- Receives `{ characterId }` prop.
- Uses local `useState` + `useEffect` + `useCallback` for data fetching (not Redux).
- Uses `axios` directly with `BASE_URL`.
- Follows Tailwind styling, responsive design with `sm:` breakpoints.
- Shows loading spinner, empty state, and error toasts.
- This is the ideal pattern to follow for the battles tab.

### 2.2. Battle System — Data Storage

**MySQL models** (`services/battle-service/app/models.py`):
- `Battle` — id, status (pending/in_progress/finished/forfeit), battle_type (pve/pvp_training/pvp_death/pvp_attack), created_at, updated_at.
- `BattleParticipant` — id, battle_id (FK), character_id, team.
- `BattleTurn` — id, battle_id (FK), actor_participant_id (FK), turn_number, skill IDs, timestamps.
- `PvpInvitation` — for PvP invite flow.

**MongoDB** (via Motor):
- `battle_logs` collection — stores per-turn event logs (saved by Celery task `save_log`).
- `battle_snapshots` collection — stores full participant snapshots at battle start.
- MongoDB is used for detailed replay data only. Not suitable for fast history queries.

**Redis:**
- Runtime battle state (HP, mana, effects, turn order). TTL-based, ephemeral.
- Cleaned up 5 minutes after battle finishes.

**No existing battle history table or query.** The only way to reconstruct history currently would be to JOIN `battles` + `battle_participants`, but there is no `winner_team` or `result` stored in MySQL — the winner is determined in-memory during the action endpoint and never persisted to the `battles` table.

### 2.3. Battle Finish Flow

**Location:** `services/battle-service/app/main.py`, lines ~817–1042.

The finish flow inside the `POST /battles/{battle_id}/action` endpoint:
1. After processing an action, checks if any participant HP <= 0 (line 820–835).
2. Sets `battle_finished = True`, determines `winner_team` from the surviving team.
3. Calls `finish_battle(db_session, battle_id)` — sets `battles.status = 'finished'` in MySQL (line 858).
4. Syncs final resources to `character_attributes` table (lines 861–884).
5. Handles PvP consequences (training: set loser HP to 1; death: unlink character).
6. Distributes PvE rewards via `_distribute_pve_rewards()`.
7. Saves log via Celery.
8. Returns `ActionResponse` with `battle_finished=True, winner_team=<int>`.

**Critical finding:** `winner_team` is never stored in MySQL. It exists only in the response and the Redis state (which expires in 5 minutes). This is the gap that `battle_history` will fill.

### 2.4. Existing Endpoints

- `GET /battles/character/{character_id}/in-battle` — returns `{ in_battle: bool, battle_id: int|null }`. Already exists (FEAT-063). Public, no auth. This will be reused for the "current battle" card.
- No endpoint for battle history exists.

### 2.5. Alembic Status

battle-service **has Alembic configured**:
- `alembic.ini` in `services/battle-service/app/`
- `env.py` uses async engine (aiomysql), `version_table="alembic_version_battle"`.
- 2 existing migrations: `001_initial_baseline` and `002_add_battle_type_and_pvp_invitations`.
- Dockerfile CMD: `alembic upgrade head && uvicorn ...` (auto-migration on container start).
- `requirements.txt` includes `alembic`.

New migration will be `003_add_battle_history`.

### 2.6. Nginx Routing

Battle-service is routed at `/battles/` (no rewrite). The new endpoint `GET /battles/history/{character_id}` will be accessible at `/battles/history/{character_id}` from the frontend. Internal endpoints under `/battles/internal/` are blocked (403).

### 2.7. Cross-Service Impact

- **No changes to other services' APIs.** The new table and endpoint are entirely within battle-service.
- **Frontend:** Only `ProfilePage` and `ProfileTabs` are modified (adding a tab). No Redux slice changes needed — the battles tab will use local state like `QuestLogTab`.
- **character-service:** The battles tab will need character names for opponents. Two options: (a) store opponent names in `battle_history` at write time (denormalized), or (b) fetch from character-service at read time. Option (a) is preferred — names rarely change, and it avoids N+1 HTTP calls when reading history.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1. New Table: `battle_history`

Owned by battle-service. Lightweight summary table — one row per participant per battle.

```sql
CREATE TABLE battle_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    battle_id INT NOT NULL,
    character_id INT NOT NULL,
    character_name VARCHAR(100) NOT NULL,
    opponent_names JSON NOT NULL,          -- ["Goblin", "Wolf"] or ["PlayerName"]
    opponent_character_ids JSON NOT NULL,   -- [123, 456]
    battle_type ENUM('pve', 'pvp_training', 'pvp_death', 'pvp_attack') NOT NULL,
    result ENUM('victory', 'defeat') NOT NULL,
    finished_at DATETIME NOT NULL,
    INDEX idx_character_id (character_id),
    INDEX idx_character_finished (character_id, finished_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**Design decisions:**
- One row per character per battle (not one row per battle). This makes queries trivial: `WHERE character_id = ? ORDER BY finished_at DESC`.
- `opponent_names` and `opponent_character_ids` are JSON arrays — denormalized at write time for fast reads. Names are snapshotted at battle completion.
- `character_name` stored for potential cross-character search (not needed now, but cheap to include).
- `finished_at` — copied from the battle's `updated_at` timestamp at finish time.
- No FK to `battles` table — keeps it decoupled and allows future cleanup of old battles without affecting history.
- Composite index `(character_id, finished_at DESC)` for efficient paginated queries.

### 3.2. SQLAlchemy Model

```python
# In models.py
class BattleResult(str, Enum):
    victory = "victory"
    defeat = "defeat"

class BattleHistory(Base):
    __tablename__ = "battle_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    battle_id: Mapped[int] = mapped_column(Integer, index=True)
    character_id: Mapped[int] = mapped_column(Integer, index=True)
    character_name: Mapped[str] = mapped_column(String(100))
    opponent_names: Mapped[str] = mapped_column(JSON)
    opponent_character_ids: Mapped[str] = mapped_column(JSON)
    battle_type: Mapped[BattleType] = mapped_column(
        SQLEnum(BattleType), nullable=False
    )
    result: Mapped[BattleResult] = mapped_column(
        SQLEnum(BattleResult), nullable=False
    )
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

### 3.3. Populating `battle_history`

**Where:** In `main.py`, inside the `if battle_finished:` block (after line 858, after `finish_battle()`).

**Logic:**
```python
# After finish_battle(db_session, battle_id):
# Collect participant data for history
battle_type_str = None
bt_result = await db_session.execute(
    text("SELECT battle_type FROM battles WHERE id = :bid"),
    {"bid": battle_id},
)
bt_row = bt_result.fetchone()
if bt_row:
    battle_type_str = bt_row[0]

for pid_str, pdata in battle_state["participants"].items():
    char_id = pdata["character_id"]
    char_name = pdata.get("name", f"Character {char_id}")
    is_winner = pdata["team"] == winner_team and pdata["hp"] > 0
    result = "victory" if is_winner else "defeat"

    # Collect opponent info (other team participants)
    opp_names = []
    opp_ids = []
    for other_pid, other_pdata in battle_state["participants"].items():
        if other_pid != pid_str:
            opp_names.append(other_pdata.get("name", f"Character {other_pdata['character_id']}"))
            opp_ids.append(other_pdata["character_id"])

    history_entry = BattleHistory(
        battle_id=battle_id,
        character_id=char_id,
        character_name=char_name,
        opponent_names=opp_names,
        opponent_character_ids=opp_ids,
        battle_type=battle_type_str,
        result=result,
        finished_at=datetime.utcnow(),
    )
    db_session.add(history_entry)

await db_session.commit()
```

**Important finding:** Redis `battle_state["participants"]` does NOT contain `name` — only `character_id`, `team`, `hp`, `mana`, `energy`, `stamina`, `max_*`, `fast_slots`, `cooldowns`. Character names must be fetched separately.

**Solution:** Query the `characters` table directly (shared DB) at battle finish time:
```python
char_ids = [pdata["character_id"] for pdata in battle_state["participants"].values()]
names_result = await db_session.execute(
    text("SELECT id, name FROM characters WHERE id IN :ids"),
    {"ids": tuple(char_ids)},
)
names_map = {row[0]: row[1] for row in names_result.fetchall()}
```
This is a single query on the shared DB, acceptable for a one-time write at battle end. The `characters` table is in the same `mydatabase` instance.

### 3.4. New Endpoint: `GET /battles/history/{character_id}`

**Route:** `GET /battles/history/{character_id}`
**Auth:** None (public endpoint — battle history is visible to all).
**Nginx:** Passes through existing `/battles/` location block.

**Query parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| page | int | 1 | Page number (1-indexed) |
| per_page | int | 20 | Items per page (max 50) |
| battle_type | str? | null | Filter: "pve", "pvp_training", "pvp_death", "pvp_attack" |
| result | str? | null | Filter: "victory", "defeat" |

**Response schema:**
```python
class BattleHistoryItem(BaseModel):
    battle_id: int
    opponent_names: list[str]
    opponent_character_ids: list[int]
    battle_type: str
    result: str  # "victory" or "defeat"
    finished_at: datetime

class BattleStats(BaseModel):
    total: int
    wins: int
    losses: int
    winrate: float  # 0.0 to 100.0, rounded to 1 decimal

class BattleHistoryResponse(BaseModel):
    history: list[BattleHistoryItem]
    stats: BattleStats
    page: int
    per_page: int
    total_count: int
    total_pages: int
```

**Implementation:**
```python
@router.get("/history/{character_id}", response_model=BattleHistoryResponse)
async def get_battle_history(
    character_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    battle_type: str | None = Query(None),
    result: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Build WHERE clause
    conditions = ["character_id = :cid"]
    params = {"cid": character_id}

    if battle_type:
        conditions.append("battle_type = :bt")
        params["bt"] = battle_type
    if result:
        conditions.append("result = :res")
        params["res"] = result

    where = " AND ".join(conditions)

    # Stats query (unfiltered — always show overall stats)
    stats_result = await db.execute(
        text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result = 'victory' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'defeat' THEN 1 ELSE 0 END) as losses
            FROM battle_history
            WHERE character_id = :cid
        """),
        {"cid": character_id},
    )
    stats_row = stats_result.fetchone()
    total = stats_row[0] or 0
    wins = stats_row[1] or 0
    losses = stats_row[2] or 0
    winrate = round((wins / total) * 100, 1) if total > 0 else 0.0

    # Count query (with filters)
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM battle_history WHERE {where}"),
        params,
    )
    total_count = count_result.scalar() or 0
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    # Paginated history query
    offset = (page - 1) * per_page
    rows = await db.execute(
        text(f"""
            SELECT battle_id, opponent_names, opponent_character_ids,
                   battle_type, result, finished_at
            FROM battle_history
            WHERE {where}
            ORDER BY finished_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": per_page, "offset": offset},
    )

    history = [
        BattleHistoryItem(
            battle_id=row[0],
            opponent_names=row[1],  # JSON auto-parsed
            opponent_character_ids=row[2],
            battle_type=row[3],
            result=row[4],
            finished_at=row[5],
        )
        for row in rows.fetchall()
    ]

    return BattleHistoryResponse(
        history=history,
        stats=BattleStats(total=total, wins=wins, losses=losses, winrate=winrate),
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
    )
```

### 3.5. Frontend Component: `BattlesTab`

**File:** `services/frontend/app-chaldea/src/components/ProfilePage/BattlesTab/BattlesTab.tsx`

**Pattern:** Follow `QuestLogTab.tsx` — local state, axios, Tailwind, responsive.

**Props:** `{ characterId: number }`

**Data fetching:**
1. On mount, fetch two endpoints in parallel:
   - `GET /battles/character/{characterId}/in-battle` — for current battle card.
   - `GET /battles/history/{characterId}?page=1&per_page=20` — for history + stats.
2. On filter/page change, re-fetch history endpoint only.

**UI structure:**
```
BattlesTab
├── CurrentBattleCard (if in_battle)
│   └── "Перейти к бою" button (link to /location:X/battle/:battleId)
│   └── Or "Нет активного боя" message
├── StatsBar (total / wins / losses / winrate)
├── Filters (battle_type dropdown, result dropdown)
├── HistoryList
│   └── BattleHistoryCard × N
│       ├── Date (finished_at)
│       ├── Opponent names
│       ├── Battle type badge
│       └── Result badge (victory=green, defeat=red)
└── Pagination (page buttons)
```

**Design system classes to use:**
- `gold-text` for section headers
- `bg-black/50 rounded-card` for cards (like QuestLogTab)
- `border-gold/20` for card borders
- `text-site-blue` for interactive elements
- `btn-blue` or custom for pagination buttons
- `text-green-400` / `bg-green-500/20` for victory
- `text-site-red` / `bg-site-red/10` for defeat
- Responsive: `sm:` breakpoints for layout adjustments

**Integration in ProfilePage:**
1. `ProfileTabs.tsx` — add `{ key: 'battles', label: 'Бои' }` after `quests` entry.
2. `ProfilePage.tsx` — add `case 'battles': return <BattlesTab characterId={characterId} />;` and import.

### 3.6. Alembic Migration

**File:** `services/battle-service/app/alembic/versions/003_add_battle_history.py`

```python
revision = '003_battle_history'
down_revision = '002_add_pvp'

def upgrade():
    op.create_table(
        'battle_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('battle_id', sa.Integer(), nullable=False),
        sa.Column('character_id', sa.Integer(), nullable=False),
        sa.Column('character_name', sa.String(100), nullable=False),
        sa.Column('opponent_names', sa.JSON(), nullable=False),
        sa.Column('opponent_character_ids', sa.JSON(), nullable=False),
        sa.Column('battle_type',
                  sa.Enum('pve', 'pvp_training', 'pvp_death', 'pvp_attack',
                          name='battletype'),
                  nullable=False),
        sa.Column('result',
                  sa.Enum('victory', 'defeat', name='battleresult'),
                  nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_bh_character_id', 'battle_history', ['character_id'])
    op.create_index('idx_bh_character_finished', 'battle_history',
                    ['character_id', sa.text('finished_at DESC')])

def downgrade():
    op.drop_table('battle_history')
```

**Note:** The `battletype` enum already exists from migration 002. Reuse it (do not create a new one). The `battleresult` enum is new.

### 3.7. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| `name` field not in Redis battle_state | **Confirmed:** name is NOT in Redis state. Solution: query `characters` table directly (shared DB) — single query, acceptable at battle end. |
| Battle finish fails mid-way, history not written | History INSERT is best-effort — wrap in try/except, log errors. Battle finish itself is more critical. |
| JSON parsing of `opponent_names` in response | MySQL JSON type + SQLAlchemy handles this natively. Test with aiomysql. |
| Profile page is own-character only | Battles tab works with any `characterId` prop. Public profile viewing is a separate feature. |
| Existing battles have no history | Only new battles will be recorded. No backfill needed (no historical winner data exists). |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### T1: Database Migration + Model (Backend Developer)
**Service:** battle-service
**Files to modify:**
- `services/battle-service/app/models.py` — add `BattleResult` enum and `BattleHistory` model
- `services/battle-service/app/alembic/versions/003_add_battle_history.py` — new migration

**Acceptance criteria:**
- `BattleHistory` model with all fields defined in section 3.2
- `BattleResult` enum (victory/defeat) added to `models.py`
- Migration creates `battle_history` table with proper indexes
- Migration is idempotent (checks if table exists before creating)
- `python -m py_compile models.py` passes

**Estimated effort:** Small

---

### T2: Populate battle_history on Battle Finish (Backend Developer)
**Service:** battle-service
**Files to modify:**
- `services/battle-service/app/main.py` — add history INSERT logic in the `if battle_finished:` block (after `finish_battle()` call, around line 858)

**Dependencies:** T1

**Implementation details:**
- After `finish_battle(db_session, battle_id)`, insert one `BattleHistory` row per participant
- Determine result from `winner_team` and participant's team
- Get character names from battle_state or fallback to DB query on `characters` table
- Collect opponent names/IDs for each participant
- Wrap in try/except — log errors but do not break the battle finish flow
- Get `battle_type` from the battles table (query is already done later in the same block for PvP consequences — reuse or move up)

**Acceptance criteria:**
- After every battle finish, `battle_history` has one row per participant
- Each row has correct result (victory/defeat), opponent data, battle_type
- Errors in history writing do not break battle finish
- `python -m py_compile main.py` passes

**Estimated effort:** Medium

---

### T3: Battle History Endpoint (Backend Developer)
**Service:** battle-service
**Files to modify:**
- `services/battle-service/app/main.py` — add `GET /battles/history/{character_id}` endpoint
- `services/battle-service/app/schemas.py` — add `BattleHistoryItem`, `BattleStats`, `BattleHistoryResponse` schemas

**Dependencies:** T1

**Implementation details:**
- Endpoint as specified in section 3.4
- Paginated query with optional filters (battle_type, result)
- Stats always unfiltered (overall character stats)
- No auth required (public endpoint)
- Validate `per_page` max 50
- Return empty results gracefully (no 404)

**Acceptance criteria:**
- Endpoint returns paginated history with stats
- Filters work correctly
- Empty history returns `{ history: [], stats: { total: 0, wins: 0, losses: 0, winrate: 0.0 }, ... }`
- `python -m py_compile main.py` and `python -m py_compile schemas.py` pass

**Estimated effort:** Medium

---

### T4: Frontend Battles Tab Component (Frontend Developer)
**Service:** frontend
**Files to create:**
- `services/frontend/app-chaldea/src/components/ProfilePage/BattlesTab/BattlesTab.tsx`
**Files to modify:**
- `services/frontend/app-chaldea/src/components/ProfilePage/ProfileTabs.tsx` — add "Бои" tab
- `services/frontend/app-chaldea/src/components/ProfilePage/ProfilePage.tsx` — add battles case + import

**Dependencies:** T3

**Implementation details:**
- Follow `QuestLogTab.tsx` pattern (local state, axios, Tailwind)
- Fetch `/battles/character/{characterId}/in-battle` and `/battles/history/{characterId}` on mount
- Show current battle card with "Перейти к бою" link
- Show stats bar (total/wins/losses/winrate)
- Show filter dropdowns (battle type, result)
- Show paginated history list with battle cards
- Handle empty states, loading, errors with Russian messages and toast
- Responsive design with `sm:` / `md:` breakpoints
- Use design system classes per section 3.5
- TypeScript only (`.tsx`), no `React.FC`
- `npx tsc --noEmit` and `npm run build` must pass

**Acceptance criteria:**
- Tab appears in profile after "Задания"
- Current battle card shows when character is in battle
- History list renders with opponent names, type badges, result badges, dates
- Filters update the list
- Pagination works
- Empty state shows "Ещё не участвовал в боях"
- Mobile-responsive (360px+)
- No console errors

**Estimated effort:** Large

---

### T5: QA Tests (QA Test)
**Service:** battle-service
**Files to create:**
- `services/battle-service/app/tests/test_battle_history.py`

**Dependencies:** T1, T2, T3

**Test cases:**
1. **Model test:** BattleHistory model can be instantiated with all required fields
2. **Endpoint — empty history:** GET `/battles/history/999` returns empty list + zero stats
3. **Endpoint — pagination:** Verify page/per_page parameters work correctly
4. **Endpoint — filters:** Verify battle_type and result filters
5. **Endpoint — stats calculation:** Verify wins/losses/winrate math
6. **Endpoint — per_page limit:** Verify per_page > 50 is clamped or rejected
7. **Schema validation:** BattleHistoryResponse schema validates correctly
8. **Integration — battle finish writes history:** (if possible with test DB) Verify history rows are created on battle finish

**Estimated effort:** Medium

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-23

**Reviewer:** QA Test + Reviewer (combined)

#### Checklist Results

| Check | Result | Notes |
|-------|--------|-------|
| Pydantic <2.0 syntax | PASS | `class Config: orm_mode = True` used in BattleHistoryItem |
| No React.FC | PASS | BattlesTab uses `const BattlesTab = ({ characterId }: BattlesTabProps) => {` |
| TypeScript only | PASS | All new frontend files are `.tsx` / `.ts` |
| Tailwind only | PASS | No CSS/SCSS files created, all styles via Tailwind |
| Responsive 360px+ | PASS | Uses `grid-cols-2 sm:grid-cols-4`, `flex-col sm:flex-row`, responsive text sizes |
| Russian UI text | PASS | All user-facing strings in Russian |
| Error handling | PASS | `toast.error('Не удалось загрузить историю боёв')` on fetch failure |
| Auth correct | PASS | History endpoint is public (no auth), matches spec |
| py_compile | PASS | models.py, schemas.py, main.py all compile |
| Cross-service consistency | PASS | Frontend calls `/battles/history/{characterId}` matching backend route |

#### Backend Review

**models.py:**
- `BattleResult` enum and `BattleHistory` model correctly defined
- JSON columns for `opponent_names` and `opponent_character_ids` (denormalized, correct design)
- `Column(JSON, nullable=False)` syntax differs from other columns which use `Mapped[]` — cosmetic inconsistency but functionally correct

**schemas.py:**
- `BattleHistoryItem`, `BattleStats`, `BattleHistoryResponse` — all fields match the architecture spec
- `orm_mode = True` in Config — correct Pydantic v1 syntax

**main.py — populate logic:**
- History INSERT wrapped in try/except — does not break battle finish flow (correct)
- Character names queried from shared DB `characters` table — single query, acceptable
- Handles case where `names_map` is empty gracefully with fallback `f"Персонаж #{char_id}"`

**main.py — history endpoint:**
- Stats always unfiltered (uses only `:cid`), filters apply to count/paginated queries — correct
- `per_page` max 50 enforced via `Query(ge=1, le=50)` — correct
- Pagination math: `total_pages = max(1, ...)` prevents 0 pages — correct
- JSON parsing: `isinstance(row[1], list)` guard added for `opponent_names` — defensive, good

**Migration (003_add_battle_history.py):**
- Idempotent: checks `if 'battle_history' not in existing_tables` — correct
- Reuses existing `battletype` enum (`create_type=False`) — correct
- Proper indexes: `idx_bh_character_id` and `idx_bh_character_finished`
- Downgrade properly drops indexes before table — correct

#### Frontend Review

**BattlesTab.tsx:**
- Follows QuestLogTab pattern (local state, axios, Tailwind) — consistent
- Two parallel fetches on mount: in-battle check + history — correct
- Filters re-fetch only history (not in-battle) — correct
- Pagination with ellipsis rendering — good UX
- Empty state messages vary by filter state — good
- Design system classes used: `gold-text`, `bg-black/50`, `rounded-card`, `border-gold/20`, `btn-blue`
- Color coding: green for victory, red for defeat, type-specific colors — correct

**ProfileTabs.tsx:**
- "Бои" tab added after "Задания" — matches spec

**ProfilePage.tsx:**
- `case 'battles'` added, import present — correct

#### QA Tests Written

**File:** `services/battle-service/app/tests/test_battle_history.py` — 13 tests, all passing:
1. Empty history returns zero stats
2. History with data returns correct items
3. Pagination params (page/per_page/offset/limit)
4. Total pages calculation
5. Filter by battle_type
6. Filter by result (victory)
7. Filter by result (defeat)
8. Stats calculation (wins/losses/winrate)
9. Stats zero battles (no division by zero)
10. Stats are unfiltered even with filters applied
11. per_page > 50 rejected (422)
12. per_page = 50 accepted
13. per_page = 0 rejected (422)

#### Issues Found

None.

#### Verdict: **PASS**

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-23 — PM: фича создана (FEAT-065), запускаю анализ
[LOG] 2026-03-23 — Codebase Analyst + Architect: анализ завершён, архитектура спроектирована. Ключевые находки: (1) winner_team не сохраняется в MySQL — это главный gap, который закрывает battle_history; (2) battle-service уже имеет Alembic с 2 миграциями; (3) профиль пока только для своего персонажа, но tab принимает characterId и будет работать для любого; (4) паттерн QuestLogTab — идеальный шаблон для BattlesTab. Разбито на 5 задач (T1-T5).
[LOG] 2026-03-23 — Backend Developer: T1 выполнен — добавлен enum BattleResult и модель BattleHistory в models.py; создана миграция 003_add_battle_history.py (идемпотентная, переиспользует существующий enum battletype, создаёт новый battleresult). Индексы: character_id, (character_id, finished_at DESC).
[LOG] 2026-03-23 — Backend Developer: T2 выполнен — в блоке if battle_finished (main.py) после PvE rewards и NPC death, перед save_log, добавлена логика записи истории: запрос имён персонажей из characters, определение result по winner_team, INSERT BattleHistory для каждого участника. Обёрнуто в try/except — ошибки не ломают завершение боя.
[LOG] 2026-03-23 — Backend Developer: T3 выполнен — добавлены Pydantic-схемы (BattleHistoryItem, BattleStats, BattleHistoryResponse) в schemas.py; эндпоинт GET /battles/history/{character_id} в main.py с пагинацией, фильтрами (battle_type, result), нефильтрованной статистикой. Публичный, без авторизации. Все файлы прошли py_compile.
[LOG] 2026-03-23 — Frontend Developer: T4 выполнен — создан BattlesTab.tsx (TypeScript, Tailwind, local state + axios, без React.FC). Компонент: карточка активного боя с кнопкой «Перейти к бою», блок статистики (4 карточки: всего/побед/поражений/винрейт), фильтры по типу боя и результату, список истории с цветными бейджами (тип боя + результат), пагинация. Адаптивность 360px+ (grid-cols-2/4, flex-col/row). Интеграция: вкладка «Бои» добавлена в ProfileTabs.tsx после «Задания», case «battles» добавлен в ProfilePage.tsx.
[LOG] 2026-03-23 — QA Test: T5 выполнен — написано 13 тестов в test_battle_history.py. Покрыты: пустая история, данные, пагинация, фильтры по типу и результату, расчёт статистики, лимит per_page (max 50). Все тесты проходят.
[LOG] 2026-03-23 — Reviewer: ревью завершено — PASS. Все чеклисты пройдены: Pydantic <2.0, TypeScript, Tailwind, адаптивность, русский текст, обработка ошибок, py_compile. Замечаний нет.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
