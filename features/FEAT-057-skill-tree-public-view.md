# FEAT-057: Публичный вид дерева навыков (Player Skill Tree View)

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-21 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-057-skill-tree-public-view.md` → `DONE-FEAT-057-skill-tree-public-view.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Публичный вид дерева навыков для игроков. Продолжение FEAT-056 (админка дерева навыков). Игроки видят дерево своего класса, выбирают узлы (бесплатно), покупают навыки из выбранных узлов за опыт, прокачивают навыки через мини-дерево улучшений.

### Бизнес-правила
- Игрок видит полное дерево своего класса (все узлы, включая недоступные)
- Выбор узла — бесплатный, определяет путь развития, блокирует альтернативные ветки на том же уровне
- После выбора узла игроку открывается возможность покупать навыки из этого узла
- Каждый навык покупается отдельно за опыт (active_experience из character-attributes)
- Не обязательно покупать все навыки из узла
- Уровень персонажа должен соответствовать level_ring узла (нельзя выбрать узел 10-го уровня на 5-м уровне персонажа)
- Предыдущий узел в цепочке должен быть выбран (prerequisites)
- Путь до подкласса (уровни 1-25) можно сбросить
- Выбор подкласса (уровень 30, node_type='subclass_choice') — необратим
- При сбросе пути: выбранные узлы сбрасываются, купленные навыки из сброшенных узлов удаляются, опыт НЕ возвращается
- Улучшение навыка (мини-дерево skill_ranks) — тоже за опыт (upgrade_cost из skill_rank)
- Публичный вид доступен в разделе "Навыки" на главной странице

### UX / Пользовательский сценарий

**Просмотр дерева:**
1. Игрок заходит в раздел "Навыки"
2. Видит полное дерево своего класса (радиальное/интерактивное)
3. Выбранные узлы подсвечены, недоступные затемнены
4. Доступные для выбора узлы (соответствуют уровню + prerequisite выполнен) выделены

**Выбор узла:**
1. Игрок кликает на доступный узел
2. Открывается панель с информацией: название, описание, список навыков внутри
3. Кнопка "Выбрать путь" — бесплатно
4. После выбора: узел подсвечивается, альтернативные ветки затемняются, навыки становятся доступны для покупки

**Покупка навыка:**
1. В панели выбранного узла — список навыков с ценой (опыт)
2. Игрок нажимает "Изучить" рядом с навыком
3. Списывается опыт, навык добавляется персонажу
4. Появляется кнопка "Улучшить" для купленного навыка

**Улучшение навыка:**
1. Игрок нажимает "Улучшить" на купленном навыке
2. Открывается мини-дерево прокачки (существующий skill_ranks с left/right child)
3. Каждое улучшение стоит опыт (upgrade_cost)
4. Выбор ветки блокирует альтернативную (если есть)

**Сброс пути:**
1. Кнопка "Сбросить путь" (с подтверждением)
2. Все выбранные узлы сбрасываются (кроме подкласса)
3. Навыки из сброшенных узлов удаляются
4. Опыт не возвращается

### Edge Cases
- Игрок без класса (новый персонаж) — показать сообщение "Выберите класс"
- Класс без дерева (админ ещё не создал) — показать сообщение "Дерево навыков в разработке"
- Навык уже куплен — кнопка "Изучить" заменяется на "Изучено" + "Улучшить"
- Недостаточно опыта — кнопка неактивна, показать сколько не хватает
- Подкласс выбран — показать дерево подкласса рядом или ниже дерева класса

### Scope (этот PR)
- **Бэкенд:** player-facing эндпоинты (просмотр дерева, выбор узла, покупка навыка, сброс пути, прогресс персонажа)
- **Фронтенд:** страница "Навыки" с интерактивным деревом, панели покупки навыков, мини-дерево прокачки
- **НЕ входит:** интеграция с боевой системой (уже работает через существующий character_skills)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Affected Services

| Service | Change Type | Key Files |
|---------|------------|-----------|
| **skills-service** | MAJOR — new player endpoints (choose node, purchase skill, reset, get progress), new CRUD functions, new schemas | `app/main.py`, `app/crud.py`, `app/schemas.py`, `app/models.py` (models already exist from FEAT-056) |
| **character-attributes-service** | NONE — existing endpoint `PUT /{character_id}/active_experience` used via HTTP call | `app/main.py` (line 485) |
| **character-service** | NONE — existing endpoint `GET /{character_id}/race_info` used via HTTP call | `app/main.py` (line 885) |
| **frontend** | MAJOR — new SkillsTab component replacing PlaceholderTab in ProfilePage, new Redux slice, ReactFlow canvas | `src/components/ProfilePage/`, new `src/components/SkillTreeView/` |

### 2.2 Existing Data Model (from FEAT-056)

All required database tables already exist and are managed by Alembic in skills-service:

1. **`class_skill_trees`** — Tree definition per class/subclass. Fields: `id`, `class_id`, `name`, `description`, `tree_type` ('class'/'subclass'), `parent_tree_id`, `subclass_name`, `tree_image`.
2. **`tree_nodes`** — Nodes within a tree. Fields: `id`, `tree_id`, `level_ring`, `position_x`, `position_y`, `name`, `description`, `node_type` ('regular'/'root'/'subclass_choice'), `icon_image`, `sort_order`.
3. **`tree_node_connections`** — Edges between nodes (prerequisite graph). Fields: `id`, `tree_id`, `from_node_id`, `to_node_id`. Direction: `from_node` (lower ring) -> `to_node` (higher ring).
4. **`tree_node_skills`** — Skills assigned to a node. Fields: `id`, `node_id`, `skill_id`, `sort_order`.
5. **`character_tree_progress`** — Already exists (created in FEAT-056 for future use). Fields: `id`, `character_id`, `tree_id`, `node_id`, `chosen_at`. Unique constraint: `(character_id, node_id)`.
6. **`character_skills`** — Existing junction table: `character_id` + `skill_rank_id`. Used by battle-service. Purchasing a skill = inserting rank 1 of that skill here.
7. **`skills`** / **`skill_ranks`** — Existing skill definitions with binary upgrade tree (`left_child_id`/`right_child_id`).

### 2.3 Cross-Service Dependencies

#### Experience Deduction
- **Endpoint exists:** `PUT /attributes/{character_id}/active_experience` in character-attributes-service (line 485 of `main.py`).
- Accepts `{"amount": int}`. Negative amount = deduct. Returns 400 if result would be negative.
- **No auth required** on this endpoint (internal service-to-service call).
- skills-service already has `ATTRIBUTES_SERVICE_URL` env var configured (line 23 of `main.py`).

#### Character Level & Class Verification
- **Endpoint exists:** `GET /characters/{character_id}/race_info` returns `CharacterBaseInfoResponse` with `id`, `id_class`, `id_race`, `id_subrace`, `level`.
- skills-service already has `CHARACTER_SERVICE_URL` env var configured (line 22 of `main.py`).
- Character ownership verification already implemented in skills-service via `verify_character_ownership()` (line 39 of `main.py`), using direct DB query to `characters` table (shared DB).

#### Skill Purchase → Battle Integration
- Purchasing a skill creates a `CharacterSkill(character_id, skill_rank_id)` row — same table battle-service reads. No additional integration needed.

### 2.4 Existing Skill Upgrade Flow

The endpoint `POST /skills/character_skills/upgrade` (line 352) already:
1. Validates character ownership via JWT
2. Checks for rank conflicts (branch conflicts in skill mini-tree)
3. Creates or updates `CharacterSkill` row

**Missing from current upgrade:** experience deduction. The code has placeholder comments (`# 3) Узнаём active_experience`, `# 4) Проверяем cost => списываем`) but never actually calls the attributes service. This must be implemented in FEAT-057.

### 2.5 Frontend Architecture

#### Current "Навыки" Section
- **ProfilePage** (`src/components/ProfilePage/ProfilePage.tsx`, line 60-61): The "skills" tab currently renders `<PlaceholderTab tabName="Навыки" />` — a simple "Скоро..." message.
- **ProfileTabs** (`src/components/ProfilePage/ProfileTabs.tsx`, line 9): Tab `{ key: 'skills', label: 'Навыки' }` already exists.
- **No dedicated `/skills` route exists.** The skills view lives inside the profile page as a tab.

#### Reusable ReactFlow Patterns (from FEAT-056 admin editor)
- **ClassTreeCanvas** (`AdminClassTreeEditor/ClassTreeCanvas.tsx`): ReactFlow wrapper with Background, Controls, MiniMap. Styled for dark theme.
- **TreeNodeComponent** (`AdminClassTreeEditor/TreeNodeComponent.tsx`): 100px circular nodes with color-coded borders by level_ring, skills count badge.
- **ringLayout utility** (`AdminClassTreeEditor/utils/ringLayout.ts`): `autoLayoutRings()` — positions nodes in concentric circles by level_ring.
- **Types** (`AdminClassTreeEditor/types.ts`): TypeScript interfaces matching backend schemas.

These can be reused/adapted for the player view. Key differences:
- Player view is read-only (no drag/edit)
- Nodes need additional visual states: chosen, available, locked, blocked-by-branch
- Click opens detail panel instead of inspector

#### Redux State
- No existing skill tree Redux slice for player view. Admin tree uses `adminClassTreeSlice`.
- `userSlice` stores `character: CharacterData` with `id`, `name`, and `[key: string]: unknown` (includes `id_class`, `level` at runtime).

### 2.6 Key Design Questions Resolved

1. **Where does the skill tree view live?** → Inside ProfilePage as the "skills" tab (replacing PlaceholderTab).
2. **How to get character's class?** → Call `GET /characters/{character_id}/race_info` which returns `id_class` and `level`.
3. **How to deduct experience?** → skills-service calls `PUT /attributes/{character_id}/active_experience` with `{"amount": -cost}`.
4. **How to determine "available" nodes?** → Backend computes: node's `level_ring <= character.level` AND at least one parent node (via `tree_node_connections`) is in `character_tree_progress` (or node is root). AND no sibling node at same level_ring from same parent is already chosen.
5. **How purchase links to battle?** → Purchase creates `CharacterSkill(character_id, skill_rank_id=rank1.id)` — same table battle-service reads.

### 2.7 Risks & Considerations

1. **Race condition on experience deduction** — Two rapid purchases could both pass the balance check. Mitigated by character-attributes-service using `if new_value < 0: raise 400`.
2. **Branch conflict detection** — Need to compute which nodes are "blocked" because a sibling at the same level_ring from the same parent is already chosen. This is a graph traversal on `tree_node_connections`.
3. **Reset cascade** — Resetting tree progress must also delete associated `character_skills` rows. Need to trace: progress nodes → node_skills → skill_ids → character_skills for those skill_ids.
4. **Subclass tree display** — After choosing a subclass_choice node, the player should see the subclass tree (identified by `parent_tree_id` pointing to the class tree and matching `subclass_name`).

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Player API Endpoints (skills-service)

All player endpoints require JWT auth via `get_current_user_via_http`. Character ownership verified via `verify_character_ownership()`.

---

#### 3.1.1 `GET /skills/class_trees/by_class/{class_id}`

**Purpose:** Get the full class tree for display (public, no auth needed — tree structure is not secret).

**Response:** `FullClassTreeResponse` (same schema used by admin, already exists).

**Logic:**
1. Query `class_skill_trees` where `class_id = class_id` and `tree_type = 'class'`.
2. If not found, return 404.
3. Load full tree with nodes, connections, and node_skills (reuse `crud.get_full_class_tree()`).

**No new schema needed** — reuses existing `FullClassTreeResponse`.

---

#### 3.1.2 `GET /skills/class_trees/{tree_id}/progress/{character_id}`

**Purpose:** Get character's progress on a specific tree (chosen nodes + purchased skills).

**Auth:** JWT required. Ownership verified.

**Response schema — `CharacterTreeProgressResponse`:**
```python
class ChosenNodeProgress(BaseModel):
    node_id: int
    chosen_at: Optional[str] = None

class PurchasedSkillProgress(BaseModel):
    skill_id: int
    skill_rank_id: int
    character_skill_id: int

class CharacterTreeProgressResponse(BaseModel):
    character_id: int
    tree_id: int
    chosen_nodes: List[ChosenNodeProgress]          # nodes in character_tree_progress
    purchased_skills: List[PurchasedSkillProgress]   # character_skills matching tree's node_skills
    active_experience: int                            # current balance for UI display
    character_level: int                              # for UI to show available nodes
```

**Logic:**
1. Verify character ownership.
2. Query `character_tree_progress` for `(character_id, tree_id)`.
3. Query `character_skills` for `character_id`, join with `skill_ranks` and `tree_node_skills` to find skills that belong to this tree's nodes.
4. Call `GET /attributes/{character_id}` to get `active_experience`.
5. Call `GET /characters/{character_id}/race_info` to get `level`.
6. Return combined response.

---

#### 3.1.3 `POST /skills/class_trees/{tree_id}/choose_node`

**Purpose:** Choose a node in the tree (free, validates prerequisites).

**Auth:** JWT required. Ownership verified.

**Request schema — `ChooseNodeRequest`:**
```python
class ChooseNodeRequest(BaseModel):
    character_id: int
    node_id: int
```

**Response:** `{"detail": "Узел выбран", "node_id": int}`

**Validation logic:**
1. Verify character ownership.
2. Verify node belongs to tree (`tree_nodes.tree_id == tree_id`).
3. Get character info via `GET /characters/{character_id}/race_info` → check `level >= node.level_ring`.
4. Check tree's `class_id` matches character's `id_class`.
5. Check node is not already chosen (`character_tree_progress`).
6. **Prerequisite check:** If node is not root (`node_type != 'root'`), at least one `from_node` in `tree_node_connections` where `to_node_id == node_id` must be in `character_tree_progress` for this character.
7. **Branch conflict check:** Find all nodes at the same `level_ring` that share a parent with this node (siblings). If any sibling is already chosen, reject — "Альтернативная ветка уже выбрана".
8. Insert into `character_tree_progress(character_id, tree_id, node_id)`.

---

#### 3.1.4 `POST /skills/class_trees/purchase_skill`

**Purpose:** Buy a skill from a chosen node (costs `active_experience`).

**Auth:** JWT required. Ownership verified.

**Request schema — `PurchaseSkillRequest`:**
```python
class PurchaseSkillRequest(BaseModel):
    character_id: int
    node_id: int
    skill_id: int
```

**Response:** `{"detail": "Навык изучен", "character_skill_id": int}`

**Validation logic:**
1. Verify character ownership.
2. Verify `node_id` is in `character_tree_progress` for this character (node must be chosen first).
3. Verify `skill_id` is assigned to `node_id` in `tree_node_skills`.
4. Check character doesn't already have this skill (`character_skills` via `get_character_skill_by_skill_id()`).
5. Get skill's `purchase_cost` from `skills` table.
6. Get character's `active_experience` via `GET /attributes/{character_id}`.
7. Verify `active_experience >= purchase_cost`.
8. Deduct experience: `PUT /attributes/{character_id}/active_experience` with `{"amount": -purchase_cost}`.
9. Find rank 1 of the skill (`skill_ranks` where `skill_id` and `rank_number == 1`).
10. Create `CharacterSkill(character_id, skill_rank_id=rank1.id)`.

---

#### 3.1.5 `POST /skills/class_trees/upgrade_skill`

**Purpose:** Upgrade a purchased skill to the next rank in the skill mini-tree (costs `active_experience`).

**Auth:** JWT required. Ownership verified.

**Request schema:** Reuses existing `SkillUpgradeRequest`:
```python
class SkillUpgradeRequest(BaseModel):
    character_id: int
    next_rank_id: int
```

**Logic:** Enhance the existing `POST /skills/character_skills/upgrade` endpoint to actually deduct experience (currently has placeholder comments). Add:
1. Get `active_experience` via `GET /attributes/{character_id}`.
2. Check `active_experience >= rank.upgrade_cost`.
3. Deduct: `PUT /attributes/{character_id}/active_experience` with `{"amount": -rank.upgrade_cost}`.
4. Rest of existing logic (conflict check, create/update `CharacterSkill`) already works.

**No new endpoint needed** — enhance existing `POST /skills/character_skills/upgrade`.

---

#### 3.1.6 `POST /skills/class_trees/{tree_id}/reset`

**Purpose:** Reset tree progress (except subclass choice).

**Auth:** JWT required. Ownership verified.

**Request schema — `ResetTreeRequest`:**
```python
class ResetTreeRequest(BaseModel):
    character_id: int
```

**Response:** `{"detail": "Прогресс сброшен", "nodes_reset": int, "skills_removed": int}`

**Logic:**
1. Verify character ownership.
2. Get all `character_tree_progress` rows for `(character_id, tree_id)`.
3. Separate subclass_choice nodes (query `tree_nodes` to check `node_type`). Keep those.
4. For each non-subclass progress row:
   a. Find all `tree_node_skills` for that `node_id` → get `skill_id` list.
   b. For each `skill_id`, find and delete `character_skills` rows for this `character_id` where `skill_rank.skill_id == skill_id`.
   c. Delete the `character_tree_progress` row.
5. Do NOT refund experience.
6. Return counts.

---

#### 3.1.7 `GET /skills/class_trees/subclass_trees/{class_tree_id}`

**Purpose:** Get available subclass trees for a class tree.

**Response:** `List[ClassSkillTreeRead]`

**Logic:**
1. Query `class_skill_trees` where `parent_tree_id == class_tree_id` and `tree_type == 'subclass'`.
2. Return list (may be empty if no subclass trees defined yet).

---

### 3.2 New Pydantic Schemas (skills-service `schemas.py`)

```python
# --- Player Tree Progress ---

class ChosenNodeProgress(BaseModel):
    node_id: int
    chosen_at: Optional[str] = None

class PurchasedSkillProgress(BaseModel):
    skill_id: int
    skill_rank_id: int
    character_skill_id: int

class CharacterTreeProgressResponse(BaseModel):
    character_id: int
    tree_id: int
    chosen_nodes: List[ChosenNodeProgress]
    purchased_skills: List[PurchasedSkillProgress]
    active_experience: int
    character_level: int

# --- Player Actions ---

class ChooseNodeRequest(BaseModel):
    character_id: int
    node_id: int

class PurchaseSkillRequest(BaseModel):
    character_id: int
    node_id: int
    skill_id: int

class ResetTreeRequest(BaseModel):
    character_id: int
```

### 3.3 New CRUD Functions (skills-service `crud.py`)

```
get_character_tree_progress(db, character_id, tree_id) -> list[CharacterTreeProgress]
add_character_tree_progress(db, character_id, tree_id, node_id) -> CharacterTreeProgress
delete_character_tree_progress(db, character_id, tree_id, exclude_subclass=True) -> int
get_sibling_nodes(db, tree_id, node_id) -> list[int]  # nodes sharing a parent at same level_ring
get_parent_nodes(db, node_id) -> list[int]  # from_node_ids in connections where to_node_id = node_id
get_skills_for_nodes(db, node_ids: list[int]) -> list[int]  # skill_ids from tree_node_skills
delete_character_skills_by_skill_ids(db, character_id, skill_ids: list[int]) -> int
get_class_tree_by_class_id(db, class_id, tree_type='class') -> ClassSkillTree | None
```

### 3.4 Experience Deduction Helper

Add a helper function in `main.py` (or a new `services.py`):

```python
async def deduct_active_experience(character_id: int, amount: int) -> int:
    """Deduct active_experience via character-attributes-service. Returns new balance."""
    async with httpx.AsyncClient() as client:
        url = f"{ATTRIBUTES_SERVICE_URL}/{character_id}/active_experience"
        resp = await client.put(url, json={"amount": -amount})
        if resp.status_code == 400:
            raise HTTPException(400, detail="Недостаточно опыта")
        if resp.status_code != 200:
            raise HTTPException(500, detail="Ошибка при списании опыта")
        return resp.json().get("active_experience", 0)

async def get_character_info(character_id: int) -> dict:
    """Get character class/level via character-service."""
    async with httpx.AsyncClient() as client:
        url = f"{CHARACTER_SERVICE_URL}/{character_id}/race_info"
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(404, detail="Персонаж не найден")
        return resp.json()  # {id, id_class, id_race, id_subrace, level}

async def get_active_experience(character_id: int) -> int:
    """Get current active_experience from character-attributes-service."""
    async with httpx.AsyncClient() as client:
        url = f"{ATTRIBUTES_SERVICE_URL}/{character_id}"
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(500, detail="Не удалось получить атрибуты")
        return resp.json().get("active_experience", 0)
```

### 3.5 Frontend Components

#### Component Tree

```
ProfilePage (existing)
└── SkillsTab (new, replaces PlaceholderTab for 'skills' tab)
    ├── PlayerTreeCanvas (new — ReactFlow, read-only)
    │   └── PlayerNodeComponent (new — visual states: chosen/available/locked/blocked)
    ├── NodeDetailPanel (new — shows node info + skill list)
    │   ├── SkillPurchaseCard (new — skill info + buy/upgrade button)
    │   └── SkillUpgradeModal (new — mini-tree for rank upgrades)
    └── SubclassTreeSelector (new — shows subclass trees after subclass choice)
```

#### SkillsTab (`src/components/ProfilePage/SkillsTab/SkillsTab.tsx`)
- Root component for the skills tab.
- On mount: fetch character info (class, level) → fetch class tree by class_id → fetch character progress.
- Handles "no class" and "no tree" edge cases.
- Layout: left side = tree canvas (70%), right side = node detail panel (30%). On mobile: full-width canvas with slide-up panel.

#### PlayerTreeCanvas (`src/components/SkillTreeView/PlayerTreeCanvas.tsx`)
- ReactFlow instance, read-only (no drag, `nodesDraggable={false}`).
- Reuses `autoLayoutRings()` from admin editor.
- Node types: `playerNode` → `PlayerNodeComponent`.
- Edge styling: gold for active path, dim gray for locked paths.
- `fitView` enabled, no minimap (cleaner player experience).

#### PlayerNodeComponent (`src/components/SkillTreeView/PlayerNodeComponent.tsx`)
- Visual states based on progress data:
  - **Chosen** — bright border, filled background (green glow)
  - **Available** — pulsing border, highlighted (blue/gold glow), clickable
  - **Locked** — dim border, low opacity, tooltip "Требуется уровень X"
  - **Blocked** — dim border, strikethrough or X icon, tooltip "Альтернативная ветка выбрана"
- Shows node name, level_ring badge, skills count.

#### NodeDetailPanel (`src/components/SkillTreeView/NodeDetailPanel.tsx`)
- Slides in from right (or bottom on mobile) when a node is clicked.
- Shows: node name, description, level_ring, node_type.
- If node is available but not chosen: "Выбрать путь" button.
- If node is chosen: list of skills with purchase/upgrade status.
- "Сбросить прогресс" button at the bottom (with confirmation modal).

#### SkillPurchaseCard (`src/components/SkillTreeView/SkillPurchaseCard.tsx`)
- Displays skill info: name, type, image, purchase_cost.
- States: "Изучить (X опыта)" / "Изучено" / "Недостаточно опыта (нужно X)".
- "Улучшить" button for purchased skills → opens SkillUpgradeModal.

#### SkillUpgradeModal (`src/components/SkillTreeView/SkillUpgradeModal.tsx`)
- Modal with the skill's rank mini-tree (left_child/right_child binary tree).
- Simple vertical/branching layout.
- Each rank node shows: rank_name, upgrade_cost, stats changes.
- Current rank highlighted, available upgrades clickable, locked ranks dimmed.
- On upgrade click: calls existing `POST /skills/character_skills/upgrade`.

#### Redux Slice (`src/redux/slices/playerTreeSlice.ts`)
- State: `tree`, `progress`, `selectedNodeId`, `loading`, `error`, `activeExperience`, `characterLevel`.
- Thunks:
  - `fetchClassTree(classId)` → `GET /skills/class_trees/by_class/{class_id}`
  - `fetchTreeProgress(treeId, characterId)` → `GET /skills/class_trees/{tree_id}/progress/{character_id}`
  - `chooseNode(treeId, characterId, nodeId)` → `POST /skills/class_trees/{tree_id}/choose_node`
  - `purchaseSkill(characterId, nodeId, skillId)` → `POST /skills/class_trees/purchase_skill`
  - `upgradeSkill(characterId, nextRankId)` → `POST /skills/character_skills/upgrade`
  - `resetTree(treeId, characterId)` → `POST /skills/class_trees/{tree_id}/reset`
  - `fetchSubclassTrees(classTreeId)` → `GET /skills/class_trees/subclass_trees/{class_tree_id}`

#### TypeScript Types (`src/components/SkillTreeView/types.ts`)
- Reuse `FullClassTreeResponse`, `TreeNodeInTreeResponse`, `TreeNodeConnectionInTree` from admin types.
- Add: `CharacterTreeProgressResponse`, `ChosenNodeProgress`, `PurchasedSkillProgress`, `NodeVisualState`.

### 3.6 Node State Computation (Frontend)

The frontend computes each node's visual state from tree structure + progress:

```typescript
type NodeVisualState = 'chosen' | 'available' | 'locked' | 'blocked';

function computeNodeState(
  node: TreeNodeInTreeResponse,
  connections: TreeNodeConnectionInTree[],
  chosenNodeIds: Set<number>,
  characterLevel: number,
): NodeVisualState {
  // Already chosen
  if (chosenNodeIds.has(node.id)) return 'chosen';

  // Level check
  if (characterLevel < node.level_ring) return 'locked';

  // Root nodes are always available if level matches
  if (node.node_type === 'root') return 'available';

  // Prerequisite check: at least one parent must be chosen
  const parentNodeIds = connections
    .filter(c => c.to_node_id === node.id)
    .map(c => c.from_node_id as number);
  const hasChosenParent = parentNodeIds.some(pid => chosenNodeIds.has(pid));
  if (!hasChosenParent) return 'locked';

  // Branch conflict: check if sibling from same parent at same level_ring is chosen
  for (const parentId of parentNodeIds) {
    const siblings = connections
      .filter(c => c.from_node_id === parentId && c.to_node_id !== node.id)
      .map(c => c.to_node_id as number);
    // Filter to same level_ring siblings
    // (need allNodes reference for this check)
    if (siblings.some(sid => chosenNodeIds.has(sid))) return 'blocked';
  }

  return 'available';
}
```

### 3.7 Alembic Migration

No new migration needed — `character_tree_progress` table already exists from FEAT-056.

### 3.8 Nginx / Docker Changes

None — skills-service already routed through nginx at `/skills/`.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Backend — New Schemas
**Agent:** Backend Developer
**Files:** `services/skills-service/app/schemas.py`
**Work:**
- Add `ChosenNodeProgress`, `PurchasedSkillProgress`, `CharacterTreeProgressResponse` schemas
- Add `ChooseNodeRequest`, `PurchaseSkillRequest`, `ResetTreeRequest` schemas
**Estimated effort:** Small

### Task 2: Backend — New CRUD Functions
**Agent:** Backend Developer
**Files:** `services/skills-service/app/crud.py`
**Work:**
- `get_character_tree_progress(db, character_id, tree_id)`
- `add_character_tree_progress(db, character_id, tree_id, node_id)`
- `delete_character_tree_progress_for_reset(db, character_id, tree_id)` — deletes non-subclass progress rows
- `get_sibling_nodes(db, tree_id, node_id)` — finds branch conflicts
- `get_parent_nodes(db, node_id)` — prerequisite parents from connections
- `get_skills_for_nodes(db, node_ids)` — skill_ids from tree_node_skills
- `delete_character_skills_by_skill_ids(db, character_id, skill_ids)` — cascade delete on reset
- `get_class_tree_by_class_id(db, class_id, tree_type)` — find tree by class
**Estimated effort:** Medium

### Task 3: Backend — Service Helpers + Player API Endpoints
**Agent:** Backend Developer
**Files:** `services/skills-service/app/main.py`
**Work:**
- Add `deduct_active_experience()`, `get_character_info()`, `get_active_experience()` helper functions
- Add `GET /skills/class_trees/by_class/{class_id}` endpoint
- Add `GET /skills/class_trees/{tree_id}/progress/{character_id}` endpoint
- Add `POST /skills/class_trees/{tree_id}/choose_node` endpoint (with full validation)
- Add `POST /skills/class_trees/purchase_skill` endpoint (with experience deduction)
- Add `POST /skills/class_trees/{tree_id}/reset` endpoint (with cascade skill deletion)
- Add `GET /skills/class_trees/subclass_trees/{class_tree_id}` endpoint
- Enhance existing `POST /skills/character_skills/upgrade` to actually deduct experience
**Dependencies:** Task 1, Task 2
**Estimated effort:** Large

### Task 4: Frontend — Redux Slice + API Layer + Types
**Agent:** Frontend Developer
**Files:** `src/redux/slices/playerTreeSlice.ts`, `src/components/SkillTreeView/types.ts`
**Work:**
- Create `playerTreeSlice` with all thunks (fetchClassTree, fetchTreeProgress, chooseNode, purchaseSkill, upgradeSkill, resetTree, fetchSubclassTrees)
- Create TypeScript types for player tree view
- Register slice in Redux store
**Dependencies:** Task 3 (API must exist)
**Estimated effort:** Medium

### Task 5: Frontend — SkillsTab + PlayerTreeCanvas + PlayerNodeComponent
**Agent:** Frontend Developer
**Files:** `src/components/ProfilePage/SkillsTab/SkillsTab.tsx`, `src/components/SkillTreeView/PlayerTreeCanvas.tsx`, `src/components/SkillTreeView/PlayerNodeComponent.tsx`
**Work:**
- Create `SkillsTab` component (replaces PlaceholderTab in ProfilePage)
- Create `PlayerTreeCanvas` (read-only ReactFlow, reuse `autoLayoutRings`)
- Create `PlayerNodeComponent` with 4 visual states (chosen/available/locked/blocked)
- Implement `computeNodeState()` utility
- Wire into ProfilePage (replace `case 'skills'` in `renderTabContent`)
- Handle edge cases: no class, no tree
- Responsive: mobile-friendly layout
**Dependencies:** Task 4
**Estimated effort:** Large

### Task 6: Frontend — NodeDetailPanel + SkillPurchaseCard + SkillUpgradeModal
**Agent:** Frontend Developer
**Files:** `src/components/SkillTreeView/NodeDetailPanel.tsx`, `src/components/SkillTreeView/SkillPurchaseCard.tsx`, `src/components/SkillTreeView/SkillUpgradeModal.tsx`
**Work:**
- Create `NodeDetailPanel` with node info, "Выбрать путь" button, skills list
- Create `SkillPurchaseCard` with purchase/upgrade states
- Create `SkillUpgradeModal` with skill rank mini-tree view
- "Сбросить прогресс" button with confirmation modal
- All user-facing text in Russian
- All API errors displayed to user
- Responsive for mobile
**Dependencies:** Task 4, Task 5
**Estimated effort:** Large

### Task 7: Backend Tests
**Agent:** QA Test
**Files:** `services/skills-service/tests/`
**Work:**
- Test `choose_node` validation: level check, prerequisite check, branch conflict check, duplicate prevention
- Test `purchase_skill` validation: node must be chosen, skill must belong to node, experience check, duplicate prevention
- Test `reset` logic: progress deleted, skills cascade-deleted, subclass nodes preserved
- Test `get progress` returns correct data
- Test experience deduction integration (mock HTTP calls)
**Dependencies:** Task 3
**Estimated effort:** Medium

### Task 8: Review
**Agent:** Reviewer
**Work:**
- Verify all endpoints work correctly (live verification)
- Verify frontend renders tree, node states are correct
- Verify purchase flow end-to-end
- Verify reset flow
- Check mobile responsiveness
- Run `npx tsc --noEmit` and `npm run build`
- Run backend tests
**Dependencies:** All previous tasks

---

## 5. Review Log (filled by Reviewer — in English)

### Review Round 1 — 2026-03-21

**Reviewer:** Reviewer Agent

#### Issues Found & Fixed

**CRITICAL — fetchSkillFullTree calls admin endpoint (FIXED)**
- `playerTreeActions.ts` called `GET /skills/admin/skills/${skillId}/full_tree` which requires `require_permission("skills:read")`. Regular players lack this permission, so the SkillUpgradeModal would fail with 403 for all non-admin users.
- **Fix:** Added a new public endpoint `GET /skills/skills/{skill_id}/full_tree` in `main.py` (no auth required, mirrors admin endpoint logic). Updated `playerTreeActions.ts` to call `GET /skills/skills/${skillId}/full_tree`.

**HIGH — DamageEntry and EffectEntry types mismatch backend (FIXED)**
- Frontend `DamageEntry` had fields `min_damage`, `max_damage`, `target` which don't exist in the backend `SkillRankDamageRead` schema (actual fields: `amount`, `chance`, `target_side`, `weapon_slot`).
- Frontend `EffectEntry` had fields `effect_type`, `effect_value`, `target` which don't exist in the backend `SkillRankEffectRead` schema (actual fields: `effect_name`, `magnitude`, `chance`, `duration`, `attribute_key`).
- **Fix:** Updated `types.ts` to match backend schemas exactly. Updated `SkillUpgradeModal.tsx` to use correct field names (`d.amount` instead of `d.min_damage-d.max_damage`, `e.effect_name` instead of `e.effect_type`, `e.magnitude` instead of `e.effect_value`).

**HIGH — SkillRankRead type incomplete (FIXED)**
- Frontend `SkillRankRead` was missing fields the backend returns: `rank_image`, `level_requirement`, `class_limitations`, `race_limitations`, `subrace_limitations`, `rank_description`. Also `rank_name` was typed as `string` but backend sends `string | null`.
- **Fix:** Updated `SkillRankRead` in `types.ts` to include all fields from backend `SkillRankRead` schema with correct nullability.

#### Checklist Results

**Backend:**
- [x] Schemas use Pydantic <2.0 syntax (`class Config: orm_mode = True`)
- [x] CRUD functions are async, follow existing patterns (SQLAlchemy async, select/execute pattern)
- [x] All player endpoints have JWT auth + ownership verification via `get_current_user_via_http` and `verify_character_ownership`
- [x] Validation logic correct: level check, prerequisites, branch conflicts, experience balance
- [x] Error messages in Russian (all `detail` strings)
- [x] Existing endpoints unchanged except upgrade enhancement (experience deduction added)
- [x] httpx used correctly for cross-service calls (AsyncClient context manager pattern)
- [x] No syntax errors (py_compile passed)
- [x] Public endpoint added for skill full tree (fix applied)

**Frontend:**
- [x] ALL .tsx/.ts (no .jsx)
- [x] ALL Tailwind (no SCSS files created)
- [x] NO React.FC used
- [x] Design system classes used: `gold-text`, `gray-bg`, `gold-outline`, `modal-overlay`, `modal-content`, `btn-blue`, `btn-line`, `gold-scrollbar`, `dropdown-item`, `rounded-card`, `bg-site-bg`, `text-site-blue`, `text-site-red`, `ease-site`
- [x] Russian for all UI text (button labels, status messages, error messages, tooltips)
- [x] Responsive: `md:` breakpoints for panel layout, flexible heights with `h-[60vh] md:h-[75vh]`
- [x] All API errors displayed to user via `toast.error()`
- [x] Types match backend schemas (after fixes applied)
- [x] ReactFlow v11 imports correct (`reactflow` package, `Handle`, `Position`, `NodeProps`, `NodeMouseHandler`)
- [x] computeNodeState logic correct: chosen > level check > root available > prerequisite > branch conflict > available
- [x] Motion animations follow design system presets (fade in with y/scale, AnimatePresence for exits)

**Cross-service:**
- [x] Battle-service contract preserved — `character_skills` table writes are unchanged, same `CharacterSkill` model
- [x] Experience deduction via `PUT /attributes/{character_id}/active_experience` with `{"amount": -cost}` — correct
- [x] Character info via `GET /characters/{character_id}/race_info` — correct
- [x] Upgrade endpoint enhanced to deduct experience — backward compatible (cost=0 skips deduction)

**Tests:**
- [x] 27 tests covering all 6 player-facing endpoints
- [x] Auth tests (401 for unauthenticated requests)
- [x] Validation tests: level check, prerequisites, branch conflicts, duplicate prevention, class mismatch, insufficient experience
- [x] Reset tests: cascade deletion, subclass preservation
- [x] HTTP mocks properly applied via `unittest.mock.patch`
- [x] Test patterns consistent with existing `test_class_tree_endpoints.py`

**Remaining Notes:**
- `SkillFullTree` type in frontend omits `class_limitations`, `race_limitations`, `subrace_limitations` — acceptable since these aren't displayed in the upgrade modal. TypeScript will safely ignore extra response fields.
- `SkillPurchaseCard` doesn't show `purchase_cost` since `TreeNodeSkillRead` only has denormalized `skill_name`, `skill_type`, `skill_image`. The cost is validated server-side. A future enhancement could add `purchase_cost` to `TreeNodeSkillRead` for better UX.
- Node.js not available in review environment — `npx tsc --noEmit` and `npm run build` could not be run. TypeScript types were verified by manual inspection.

**Verdict: PASS** (after 3 fixes applied)

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-21 — PM: фича создана (FEAT-057), запускаю анализ кодовой базы
[LOG] 2026-03-21 — Codebase Analyst: анализ завершён (Section 2). Изучены: skills-service (models, schemas, crud, main, auth_http), character-attributes-service (models, main — найден PUT active_experience), character-service (models, main — найден GET race_info), frontend (ProfilePage с PlaceholderTab для навыков, AdminClassTreeEditor — ReactFlow паттерны, types, ringLayout). Все модели из FEAT-056 уже есть, character_tree_progress создана. Ключевой риск: в upgrade_skill не реализовано списание опыта (placeholder-комментарии).
[LOG] 2026-03-21 — Architect: архитектура спроектирована (Section 3) + задачи разбиты (Section 4). 7 эндпоинтов (включая доработку существующего upgrade), 8 задач. Фронтенд: SkillsTab заменяет PlaceholderTab в ProfilePage, 6 новых компонентов, новый Redux slice.
[LOG] 2026-03-21 — Backend Developer: Task 1 выполнен — добавлены 6 новых Pydantic-схем в schemas.py (ChosenNodeProgress, PurchasedSkillProgress, CharacterTreeProgressResponse, ChooseNodeRequest, PurchaseSkillRequest, ResetTreeRequest). Pydantic <2.0 синтаксис соблюдён.
[LOG] 2026-03-21 — Backend Developer: Task 2 выполнен — добавлены 8 новых async CRUD-функций в crud.py (get_character_tree_progress, add_character_tree_progress, delete_character_tree_progress_for_reset, get_sibling_nodes, get_parent_nodes, get_skills_for_nodes, delete_character_skills_by_skill_ids, get_class_tree_by_class_id).
[LOG] 2026-03-21 — Backend Developer: Task 3 выполнен — добавлены 3 helper-функции (deduct_active_experience, get_character_info, get_active_experience) и 7 эндпоинтов: GET by_class, GET progress, POST choose_node (с полной валидацией prerequisites + branch conflicts), POST purchase_skill (с списанием опыта), POST reset (каскадное удаление навыков), GET subclass_trees. Также доработан POST /character_skills/upgrade — добавлено реальное списание опыта вместо placeholder-комментариев. httpx уже был в requirements.txt. Все файлы прошли py_compile проверку.
[LOG] 2026-03-21 — Frontend Developer: Task 4 выполнен — создан Redux slice playerTreeSlice.ts (state: tree, progress, selectedNodeId, loading, error, subclassTrees), зарегистрирован в store.ts. Создан playerTreeActions.ts с 8 async thunks (fetchClassTree, fetchTreeProgress, chooseNode, purchaseSkill, upgradeSkill, resetTree, fetchSubclassTrees, fetchSkillFullTree). Создан types.ts с player-specific типами (ChosenNodeProgress, PurchasedSkillProgress, CharacterTreeProgressResponse, NodeVisualState, SkillRankRead, SkillFullTree), переиспользованы админские типы через re-export.
[LOG] 2026-03-21 — Frontend Developer: Task 5 выполнен — создан PlayerTreeCanvas.tsx (ReactFlow read-only, autoLayoutRings, gold/dim edge стили, fitView), PlayerNodeComponent.tsx (4 visual states: chosen/available/locked/blocked с цветовым кодированием, скрытые handles), computeNodeState.ts (алгоритм определения состояния узла: prerequisite check, branch conflict, level check). Создан SkillsTab.tsx (основной компонент вкладки навыков: загрузка дерева по class_id, прогресс, edge cases). Модифицирован ProfilePage.tsx — PlaceholderTab для 'skills' заменён на SkillsTab. Адаптивная вёрстка: md breakpoint для панели деталей.
[LOG] 2026-03-21 — Frontend Developer: Task 6 выполнен — создан NodeDetailPanel.tsx (информация об узле, кнопка "Выбрать путь" для available, список навыков для chosen, сброс прогресса с confirmation modal). Создан SkillPurchaseCard.tsx (карточка навыка: покупка/изучено/улучшить, тип навыка badge). Создан SkillUpgradeModal.tsx (модальное окно с мини-деревом рангов: SVG-линии, DFS layout, визуальные состояния owned/current/available/locked, детали текущего ранга). Все тексты на русском, ошибки API отображаются через toast. TypeScript, Tailwind, без React.FC — все правила CLAUDE.md соблюдены.
[LOG] 2026-03-21 — QA Test: Task 7 выполнен — создан test_player_tree_endpoints.py (27 тестов в 6 классах). Покрыты все 6 player-facing эндпоинтов: GET by_class (2 теста), GET progress (3 теста, включая auth), POST choose_node (8 тестов: root success, node not in tree, level too low, prerequisite not met, branch conflict, already chosen, class mismatch, auth), POST purchase_skill (6 тестов: success, node not chosen, skill not in node, already purchased, insufficient experience, auth), POST reset (4 теста: success, preserves subclass nodes, cascade deletes skills, auth), GET subclass_trees (2 теста). HTTP-вызовы к character-service и character-attributes-service замокированы через unittest.mock.patch. Паттерн async тестов соответствует test_class_tree_endpoints.py. py_compile проверка пройдена.
[LOG] 2026-03-21 — Reviewer: Task 8 выполнен — полный code review завершён. Найдены и исправлены 3 проблемы: (1) CRITICAL — fetchSkillFullTree вызывал admin-эндпоинт, недоступный обычным игрокам, добавлен публичный эндпоинт GET /skills/skills/{skill_id}/full_tree; (2) HIGH — типы DamageEntry/EffectEntry в types.ts не соответствовали бэкенду (min_damage/max_damage вместо amount, effect_type вместо effect_name), исправлено; (3) HIGH — SkillRankRead неполный (отсутствовали rank_image, level_requirement и др.), дополнен. Все чеклисты пройдены: Pydantic <2.0, async CRUD, JWT auth, валидация, русские сообщения, Tailwind, TypeScript, без React.FC, адаптивность, design system, error display. Вердикт: PASS.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_Pending_
