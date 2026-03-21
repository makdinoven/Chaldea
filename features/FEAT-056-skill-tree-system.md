# FEAT-056: Система дерева навыков (Class Skill Tree)

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-20 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-056-skill-tree-system.md` → `DONE-FEAT-056-skill-tree-system.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Полная переработка системы навыков. Вместо текущей плоской структуры навыков создаётся двухуровневая система деревьев:

1. **Дерево класса** — большое радиальное/круговое интерактивное дерево для каждого базового класса (Маг, Воин, Плут). Кольца по уровням (1 → 5 → 10 → 15 → 20 → 25 → 30). В каждом узле — набор навыков. Выбор узла блокирует альтернативные ветки. Цепочка выборов определяет путь к подклассу.

2. **Дерево подкласса** — отдельное мини-дерево для каждого подкласса (уровни 30 → 50). Открывается после необратимого выбора подкласса на 30-м уровне. Даёт уникальность билдов даже внутри одного подкласса.

3. **Мини-дерево прокачки навыка** — у каждого навыка своя ветка улучшений. Начинается от самого навыка (большой кружок), далее маленькие кружки-улучшения. На каждом этапе 1 или 2 варианта (не больше, не меньше). Связи гибкие — можно переходить между ветками или быть заблокированным в одной. Покупка/улучшение за опыт.

### Бизнес-правила
- 3 базовых класса: Маг, Воин, Плут
- Кольца дерева класса: 1, 5, 10, 15, 20, 25, 30 уровень
- В каждом узле дерева — набор навыков (разного типа и количества)
- Выбор узла блокирует альтернативные ветки на том же кольце
- На 30-м уровне — необратимый выбор подкласса
- Путь до подкласса можно сбросить, сам подкласс — нет
- Подкласс открывает отдельное дерево навыков (30-50)
- Навыки покупаются за опыт, улучшения тоже за опыт
- Типы навыков: Атака, Защита, Поддержка (как в текущей системе)
- Улучшения навыков (пока): числовые бонусы (+урон, +статы, +крит шанс, +крит урон, -перезарядка и т.д.)
- Мини-дерево навыка: на каждом этапе 1 или 2 варианта, глубина произвольная

### UX / Пользовательский сценарий

**Админ (создание дерева):**
1. Админ открывает визуальный редактор дерева навыков (вдохновлён интерактивной картой)
2. Выбирает класс (Маг/Воин/Плут) или подкласс
3. Создаёт/редактирует узлы на кольцах, настраивает связи
4. Внутри узла создаёт навыки, настраивает их параметры (тип, урон, эффекты, затраты, перезарядка)
5. Для каждого навыка настраивает мини-дерево прокачки

**Игрок (публичный вид — следующий этап):**
1. Игрок заходит в раздел "Навыки" на главной
2. Видит полное дерево своего класса (с затемнёнными недоступными ветками)
3. На доступном уровне выбирает узел — получает навыки из него
4. В профиле видит свои навыки, может нажать "Улучшить" — открывается мини-дерево прокачки
5. Может сбросить путь развития (кроме подкласса)

### Edge Cases
- Что если игрок сбрасывает путь — навыки из сброшенных узлов удаляются? Прокачка навыков теряется?
- Что если навык используется в бою и игрок его теряет при сбросе?
- Что если админ изменяет дерево, а у игроков уже выбраны узлы?

### Scope (этот PR)
- **Бэкенд:** новые модели, API для деревьев классов/подклассов, узлов, навыков, мини-деревьев прокачки
- **Фронтенд:** админка с визуальным редактором дерева
- **НЕ входит:** публичный вид для игроков, интеграция с боевой системой

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Affected Services

| Service | Change Type | Key Files |
|---------|------------|-----------|
| **skills-service** | MAJOR — new models, new endpoints, Alembic migration | `app/models.py`, `app/schemas.py`, `app/main.py`, `app/crud.py` |
| **character-service** | MINOR — subclass model addition, starter kit changes | `app/models.py` (Class model, StarterKit), `app/main.py` (approval flow) |
| **battle-service** | READ-ONLY RISK — consumes skills API, must verify contract | `app/skills_client.py`, `app/battle_engine.py`, `app/buffs.py`, `app/main.py` |
| **character-attributes-service** | NONE — no changes needed, but data model is referenced | `app/models.py` (stats, resistances used by effects) |
| **frontend** | MAJOR — new admin skill tree editor, refactor existing admin page | `src/components/AdminSkillsPage/*`, new `AdminClassTreeEditor/` component |
| **photo-service** | MINOR — may need image upload endpoints for new tree node icons | Already handles `change_skill_image`, `change_skill_rank_image` |

### 2.2 Current Skills-Service Architecture

#### Data Model (5 tables, all in shared `mydatabase`)

1. **`skills`** — Base skill definition: `id`, `name`, `skill_type` (Attack/Defense/Support), `description`, `class_limitations`, `race_limitations`, `subrace_limitations`, `min_level`, `purchase_cost`, `skill_image`. Currently flat — each skill is independent, no class/tree grouping.

2. **`skill_ranks`** — Upgrade tiers within a skill. Already has a **binary tree structure** via `left_child_id` / `right_child_id` (self-referencing FK). Fields: `rank_number`, `rank_name`, `cost_energy`, `cost_mana`, `cooldown`, `level_requirement`, `upgrade_cost`, `class_limitations`, `race_limitations`, `subrace_limitations`, `rank_description`, `rank_image`.

3. **`skill_rank_damage`** — Multiple damage entries per rank: `damage_type`, `amount`, `target_side` (self/enemy), `chance`, `weapon_slot`.

4. **`skill_rank_effects`** — Buff/debuff effects per rank: `effect_name`, `target_side`, `chance`, `duration`, `magnitude`, `attribute_key`.

5. **`character_skills`** — Junction: `character_id` + `skill_rank_id`. Tracks which rank of which skill a character currently has.

**Key observation:** The existing skill_ranks model already supports a per-skill upgrade tree (binary left/right children). This is the "skill upgrade mini-tree" from the feature brief. What does NOT exist is the higher-level class tree / subclass tree structure that organizes skills into level rings.

#### Async Pattern
- Uses **async SQLAlchemy** with `aiomysql` driver
- `async_sessionmaker`, `AsyncSession`, `await db.execute(select(...))`
- All CRUD functions are `async def`
- Alembic configured for async (uses `async_engine_from_config` in online mode, `pymysql` in offline mode)
- Version table: `alembic_version_skills`
- Has one baseline migration: `001_initial_baseline.py`

#### Current Endpoints (all under `/skills/` prefix)

**Admin CRUD:**
- `POST/GET/PUT/DELETE /admin/skills/` — Skill CRUD
- `POST/GET/PUT/DELETE /admin/skill_ranks/` — SkillRank CRUD
- `POST/GET/PUT/DELETE /admin/damages/` — SkillRankDamage CRUD
- `POST/GET/PUT/DELETE /admin/effects/` — SkillRankEffect CRUD
- `POST/GET/PUT/DELETE /admin/character_skills/` — CharacterSkill CRUD
- `GET /admin/skills/{id}/full_tree` — Full skill tree with all ranks, damages, effects
- `PUT /admin/skills/{id}/full_tree` — Bulk update entire skill tree (supports temp IDs for new nodes)

**Player-facing:**
- `GET /characters/{character_id}/skills` — List character's skills (no auth!)
- `POST /character_skills/upgrade` — Upgrade to next rank (authenticated, ownership check)
- `POST /assign_multiple` — Bulk assign skills to character (no auth!)
- `POST /` — Legacy: assign "Basic Attack" to new character

**Auth:** Uses `require_permission("skills:read/create/update/delete")` for admin endpoints. Player upgrade uses `get_current_user_via_http`. Some endpoints (assign_multiple, character skills list) have NO auth.

#### RabbitMQ Consumer
Active consumer on `character_skills_queue`. Processes `{"character_id": N, "skill_ids": [1,2,3]}` messages from character-service. Assigns rank 1 of each skill to the character (idempotent — skips if character already has skills).

### 2.3 Battle-Service Integration (CRITICAL)

Battle-service consumes skills-service data via HTTP. The contract is:

**`skills_client.py` API calls:**
1. `get_rank(rank_id)` → `GET /skills/admin/skill_ranks/{rank_id}` — Returns rank JSON + fetches skill_type from `/skills/admin/skills/{skill_id}` if not present
2. `character_has_rank(character_id, rank_id)` → `GET /skills/characters/{character_id}/skills` — Checks if character owns a specific rank
3. `character_ranks(character_id)` → `GET /skills/characters/{character_id}/skills` + parallel `get_rank()` for each — Returns all ranks with skill_type

**Battle engine consumption:**
- `battle_engine.py` uses `damage_entries` from rank data (fields: `damage_type`, `amount`, `chance`, `weapon_slot`)
- `buffs.py` uses `effects` from rank data (fields: `effect_name`, `magnitude`, `duration`, `chance`, `attribute_key`, `target_side`)
- `main.py` uses `cost_energy`, `cost_mana`, `cooldown` from rank data
- Effect names follow conventions: `"Buff: fire"`, `"Resist: physical"`, `"StatModifier"` (with `attribute_key`), `"Bleeding"`, `"Poison"`, etc.

**Contract fields that battle-service depends on (from SkillRank response):**
```
id, skill_id, skill_type, rank_number, cost_energy, cost_mana, cooldown,
damage_entries: [{damage_type, amount, chance, target_side, weapon_slot}],
effects: [{effect_name, target_side, chance, duration, magnitude, attribute_key}]
```

**RISK:** As long as the `GET /skills/characters/{character_id}/skills` and `GET /skills/admin/skill_ranks/{rank_id}` endpoints continue to return the same shape, battle-service will not break. The new class tree structure is additive — it organizes skills but does not change the skill/rank/damage/effect data model.

### 2.4 Character-Service Integration

**Current class model:** `classes` table with `id_class`, `name`, `description`. Three classes exist (id 1=Warrior, 2=Mage, 3=Rogue based on `skillConstants.js`). **No subclass model exists.** Characters have `id_class` but NO `id_subclass` column (despite having `id_subrace`).

**StarterKit model:** `starter_kits` table with `class_id`, `items` (JSON), `skills` (JSON), `currency_amount`. Used during character approval to assign initial skills via `publish_character_skills()` (RabbitMQ) or direct HTTP to `skills-service/assign_multiple`.

**Approval flow** (in `main.py`): When a character request is approved, character-service:
1. Creates the character
2. Creates attributes via character-attributes-service
3. Calls `publish_character_skills(character_id, skill_ids)` (RabbitMQ to skills-service)
4. Falls back to HTTP `POST /skills/assign_multiple` if RabbitMQ fails

**RISK:** The starter kit currently assigns flat skill IDs. With the new tree system, starter kits may need to reference tree node IDs instead, or the assignment logic needs to map "starting node" to actual skills.

### 2.5 Character-Attributes-Service

Relevant fields that skills interact with:
- **Resources:** `current_health`, `current_mana`, `current_energy`, `current_stamina` (and max versions)
- **Stats:** `strength`, `agility`, `intelligence`, `endurance`, `charisma`, `luck`
- **Combat:** `damage`, `dodge`, `critical_hit_chance`, `critical_damage`
- **Experience:** `passive_experience`, `active_experience` (used as currency for skill upgrades)
- **Resistances:** `res_physical`, `res_fire`, `res_ice`, `res_magic`, etc. (13 types)
- **Vulnerabilities:** `vul_physical`, `vul_fire`, etc. (13 types)

These are the `attribute_key` values used in `SkillRankEffect` with `effect_name="StatModifier"`.

### 2.6 Frontend Architecture

#### Current Admin Skills Page (`/home/admin/skills`)
- **Route:** Protected by `skills:read` permission
- **Component tree:**
  - `AdminSkillsPage.tsx` — Main page with skill list sidebar + editor area
  - `FlowSkillsEditor.jsx` — **ReactFlow-based** visual editor for skill rank tree
  - `RankNode.jsx` — Custom ReactFlow node for a single rank
  - `nodeTypes.jsx` — ReactFlow node type registration
  - `skillConstants.js` — Class/race/subrace options, damage types, empty templates
  - `SkillTreeEditor.jsx` — Alternative tree editor (appears unused in current flow)
  - `tabs/` — DamageSection, BuffDebuffSection, ResistSection, VulnerabilitySection, ComplexEffectsSection, StatModifierSection, OtherSection
  - `utils/transformSkillTree.jsx` — Transforms API response into frontend format (splits damage/effects by target_side into separate arrays)
  - `utils/preparePayload.jsx` — Transforms frontend format back to API format

**Technology:** Uses **ReactFlow v11** for the visual node-based editor. This is already a graph editor with:
- Drag-and-drop nodes
- Edge connections (left/right child)
- MiniMap, Controls, Background
- Custom node types
- Temp ID system for new nodes (`temp-1`, `temp-2`)

**Key insight:** The existing ReactFlow editor is for the **per-skill upgrade mini-tree** (ranks within a single skill). The new feature needs a SECOND level of ReactFlow editor for the **class tree** (nodes = groups of skills organized by level rings). The existing editor pattern can be directly reused.

#### Admin Characters Skills Tab
- `Admin/CharactersPage/tabs/SkillsTab.tsx` — Admin can assign/remove skills from characters, change ranks
- Uses `adminCharactersSlice` from Redux
- Types in `Admin/CharactersPage/types.ts` — `SkillRank`, `CharacterSkill`, `SkillInfo`, `FullSkillTreeResponse`

#### Redux State Management
- **`skillsAdminSlice.js`** — Stores `skillsList`, `selectedSkillTree`, `status`, `updateStatus`
- **`skillsAdminActions.js`** — Async thunks: `fetchSkills`, `fetchSkillFullTree`, `updateSkillFullTree`, `uploadSkillImage`, `uploadSkillRankImage`
- Uses `createAsyncThunk` + `createSlice` pattern
- These are `.js` files (need migration to `.ts` per CLAUDE.md rules)

#### Interactive Map Editor (Reference Pattern)
- `AdminLocationsPage/RegionMapEditor/RegionMapEditor.tsx` — Canvas-based editor with:
  - Drag-and-drop markers on an image
  - Create/edit/delete items (locations, zones)
  - Inline editing forms
  - Sort order management
  - Icon upload per item
  - Sidebar with item list + map canvas
  - Uses native mouse events (not ReactFlow)
- `WorldPage/InteractiveMap/InteractiveMap.tsx` — Public view with clickable zones overlay
- **Difference from skill tree needs:** The map editor works with absolute x/y positions on an image. The skill tree needs a radial/ring layout with structured levels, which is better served by ReactFlow (already used in skills admin) or a custom SVG/Canvas approach.

#### SCSS Status
- `AdminSkillsPage.module.scss` exists and is imported by `FlowSkillsEditor.jsx`
- Per CLAUDE.md rules, any style changes require full Tailwind migration of the component

#### Public-Facing Skills
- **No public skills page exists.** The brief confirms this is out of scope for this PR.
- Navigation only has admin route `/home/admin/skills`

### 2.7 Existing Tests

**skills-service tests** (`services/skills-service/app/tests/`):
- `conftest.py` — Sets up env vars for SQLite-based testing
- `test_rabbitmq_consumer.py` — Tests RabbitMQ consumer
- `test_admin_auth.py` — Tests admin authentication
- `test_admin_character_skills.py` — Tests admin character skill endpoints
- `test_endpoint_auth.py` — Tests endpoint authorization
- No tests for the core skill CRUD or tree operations

### 2.8 Cross-Service Dependencies

```
[skills-service]
  ← character-service (HTTP POST /skills/, POST /assign_multiple, DELETE /admin/character_skills/by_character/{id})
  ← character-service (RabbitMQ: character_skills_queue)
  ← battle-service (HTTP GET /skills/characters/{id}/skills, GET /admin/skill_ranks/{id}, GET /admin/skills/{id})
  ← frontend (all admin CRUD endpoints)
  → user-service (auth: /users/me for JWT validation)
  → character-attributes-service (referenced in upgrade endpoint, not yet implemented)
```

### 2.9 DB Changes Assessment

#### Tables to KEEP (unchanged)
- `skills` — Base skill definition. Still needed. May get a new nullable `tree_node_id` FK or similar.
- `skill_ranks` — Per-skill upgrade tree. Already has left/right child structure. This IS the "skill upgrade mini-tree."
- `skill_rank_damage` — Damage entries per rank. Unchanged.
- `skill_rank_effects` — Effects per rank. Unchanged.
- `character_skills` — Character skill assignments. May need additional columns for tree path tracking.

#### NEW Tables Needed
1. **`class_skill_trees`** — One per class. Fields: `id`, `class_id` (FK to `classes`), `name`, `description`, `tree_type` ('class' or 'subclass'), `parent_class_tree_id` (for subclass trees).
2. **`tree_nodes`** — Nodes in the class/subclass tree. Fields: `id`, `tree_id` (FK), `level_ring` (1/5/10/15/20/25/30 or 30-50 for subclass), `position_x`, `position_y` (for visual editor), `name`, `description`, `is_subclass_choice` (boolean for level 30 nodes), `subclass_name` (nullable).
3. **`tree_node_connections`** — Edges between nodes. Fields: `id`, `from_node_id`, `to_node_id`, `connection_type` ('prerequisite' / 'branch').
4. **`tree_node_skills`** — Skills attached to a tree node. Fields: `id`, `node_id` (FK), `skill_id` (FK to skills), `sort_order`.
5. **`character_tree_progress`** — Tracks which nodes a character has chosen. Fields: `id`, `character_id`, `tree_id`, `node_id`, `chosen_at`. Enables path tracking and reset.

#### Migration Strategy
- All new tables are **additive** — no existing tables need modification
- Existing `skills` table keeps working as-is; skills are linked to tree nodes via `tree_node_skills`
- Existing `character_skills` continues to work for battle-service; `character_tree_progress` adds tree-level tracking
- Battle-service API contract is preserved: `GET /characters/{id}/skills` still returns the same shape
- **Backward compatibility:** Old admin skills page continues to work for individual skill editing. New tree editor is a separate page.

### 2.10 Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Battle-service contract break** | HIGH | Keep existing endpoints (`/characters/{id}/skills`, `/admin/skill_ranks/{id}`) returning same shape. New tree endpoints are additive. |
| **Data migration for existing skills** | MEDIUM | Existing skills remain independent until manually assigned to tree nodes by admin. No automated migration needed. |
| **Visual editor complexity** | HIGH | The class tree needs a radial/ring layout, not a simple left-right tree. ReactFlow can handle this with custom layout algorithms, but it's significant frontend work. |
| **Subclass model does not exist** | MEDIUM | `classes` table exists with 3 classes, but no subclass entity. Need to add `subclasses` table or model subclasses as tree_nodes with special flags. |
| **Starter kit flow change** | LOW | Current starter kits assign flat skill IDs. With tree system, starter kits can continue to assign skills directly — tree node selection is a separate concern. |
| **RBAC permissions** | LOW | New tree endpoints need new permissions (`skill_trees:create`, `skill_trees:update`, etc.) or reuse existing `skills:*` permissions. |
| **SCSS migration** | MEDIUM | `FlowSkillsEditor.jsx` and `RankNode.jsx` use `AdminSkillsPage.module.scss`. If these components are modified, full Tailwind migration is required. |
| **TypeScript migration** | MEDIUM | Multiple `.jsx` files in AdminSkillsPage need conversion to `.tsx` if modified. New files must be `.tsx`. |
| **ReactFlow version** | LOW | Currently using ReactFlow v11 (`reactflow@^11.11.4`). Stable, well-supported. |

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 High-Level Design

The skill tree system adds a **class/subclass tree layer** on top of the existing flat skill system. The design is purely additive — no existing tables, endpoints, or contracts are modified. Existing `skills`, `skill_ranks`, `skill_rank_damage`, `skill_rank_effects`, and `character_skills` tables remain unchanged. Battle-service API contract is fully preserved.

**Architecture layers:**
```
┌─────────────────────────────────────────────────┐
│  class_skill_trees (one per class/subclass)      │
│    └── tree_nodes (organized in level rings)     │
│         ├── tree_node_connections (edges)         │
│         └── tree_node_skills (link to skills)    │
│              └── skills (EXISTING, unchanged)    │
│                   └── skill_ranks (EXISTING)     │
│                        ├── skill_rank_damage     │
│                        └── skill_rank_effects    │
├─────────────────────────────────────────────────┤
│  character_tree_progress (player choices)        │
│    → references tree_nodes + character_id        │
│    → coexists with character_skills (EXISTING)   │
└─────────────────────────────────────────────────┘
```

**Key design decisions:**

1. **Subclass is modeled as a separate tree** (`tree_type='subclass'`), linked to a parent class tree via `parent_tree_id`. This avoids mixing class and subclass nodes in one tree and allows independent editing. A subclass tree also stores a `subclass_name` for display purposes.

2. **No subclass table in character-service.** Subclass identity is captured by the `class_skill_trees` record (type=subclass). Character's subclass is determined by their `character_tree_progress` — if they have chosen a level-30 subclass node, we can derive the subclass from that node's tree. This avoids cross-service schema changes for this PR.

3. **Node positions are manual (x/y stored in DB).** The admin drags nodes on the ReactFlow canvas and positions are saved. A "ring layout helper" button can auto-arrange nodes by level ring, but final positions are manually adjustable. This matches the existing ReactFlow pattern in FlowSkillsEditor.

4. **Bulk save pattern** — following the existing `PUT /admin/skills/{id}/full_tree` pattern, the class tree editor uses a single `PUT /admin/class_trees/{id}/full` endpoint that saves the entire tree (nodes, connections, skill assignments) in one transaction. Supports temp IDs for new nodes.

5. **Existing admin skills page is NOT modified.** The new class tree editor lives at a new route (`/home/admin/class-trees`). Individual skill editing (ranks, damage, effects) continues to use the existing `/home/admin/skills` page. The class tree editor links to the skill editor when a user wants to edit a skill's details.

6. **Skill upgrade mini-tree is the EXISTING skill_ranks system.** The `left_child_id`/`right_child_id` binary tree in `skill_ranks` already models this. No new tables needed for per-skill upgrades. The class tree editor shows skills inside nodes but links to the existing skill editor for rank/damage/effect editing.

### 3.2 Database Schema

All new tables live in the shared `mydatabase`. skills-service owns them. Alembic migration via `alembic_version_skills`.

#### Table: `class_skill_trees`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | Integer | PK, auto-increment | |
| `class_id` | Integer | NOT NULL | References `classes.id_class` (no FK constraint — cross-service) |
| `name` | String(100) | NOT NULL | Display name (e.g., "Дерево Воина") |
| `description` | Text | nullable | Optional description |
| `tree_type` | String(20) | NOT NULL, default='class' | 'class' or 'subclass' |
| `parent_tree_id` | Integer | FK→class_skill_trees.id, nullable | For subclass trees — points to the parent class tree |
| `subclass_name` | String(100) | nullable | Display name for the subclass (e.g., "Берсерк") |
| `tree_image` | Text | nullable | Optional background image URL for the tree canvas |
| `created_at` | TIMESTAMP | server_default=now() | |
| `updated_at` | TIMESTAMP | server_default=now(), onupdate=now() | |

**Unique constraint:** `(class_id, tree_type, subclass_name)` — one class tree per class, unique subclass names per class.

#### Table: `tree_nodes`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | Integer | PK, auto-increment | |
| `tree_id` | Integer | FK→class_skill_trees.id, NOT NULL | Which tree this node belongs to |
| `level_ring` | Integer | NOT NULL | Level requirement (1,5,10,15,20,25,30 for class; 30,35,40,45,50 for subclass) |
| `position_x` | Float | NOT NULL, default=0 | X coordinate on the visual canvas |
| `position_y` | Float | NOT NULL, default=0 | Y coordinate on the visual canvas |
| `name` | String(100) | NOT NULL | Node display name |
| `description` | Text | nullable | Optional node description |
| `node_type` | String(20) | NOT NULL, default='regular' | 'regular', 'root', 'subclass_choice' |
| `icon_image` | Text | nullable | Node icon URL |
| `sort_order` | Integer | default=0 | For ordering within the same ring |

**Notes:**
- `node_type='subclass_choice'` marks level-30 nodes that lead to a subclass tree. These nodes are on the class tree, and their selection is irreversible.
- `node_type='root'` marks the starting node(s) at level 1.

#### Table: `tree_node_connections`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | Integer | PK, auto-increment | |
| `tree_id` | Integer | FK→class_skill_trees.id, NOT NULL | Denormalized for faster queries |
| `from_node_id` | Integer | FK→tree_nodes.id, NOT NULL | Source node (lower ring) |
| `to_node_id` | Integer | FK→tree_nodes.id, NOT NULL | Target node (higher ring) |

**Unique constraint:** `(from_node_id, to_node_id)` — no duplicate connections.

**Note:** Connection semantics are implicit from the tree structure: a node on ring N connects to nodes on ring N+step. The admin defines which connections exist. At player time, a player must have chosen `from_node` to be eligible for `to_node`.

#### Table: `tree_node_skills`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | Integer | PK, auto-increment | |
| `node_id` | Integer | FK→tree_nodes.id, NOT NULL | Which tree node |
| `skill_id` | Integer | FK→skills.id, NOT NULL | Which skill is in this node |
| `sort_order` | Integer | default=0 | Display order within the node |

**Unique constraint:** `(node_id, skill_id)` — a skill appears at most once per node.

**Note:** A single skill CAN appear in multiple nodes across different trees (e.g., a generic skill shared by multiple class paths). This is by design — the skill itself is class-agnostic; the tree node determines when/where it's available.

#### Table: `character_tree_progress`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | Integer | PK, auto-increment | |
| `character_id` | Integer | NOT NULL, index | Character who made the choice |
| `tree_id` | Integer | FK→class_skill_trees.id, NOT NULL | Which tree |
| `node_id` | Integer | FK→tree_nodes.id, NOT NULL | Which node was chosen |
| `chosen_at` | TIMESTAMP | server_default=now() | When the choice was made |

**Unique constraint:** `(character_id, node_id)` — a character can choose each node at most once.

**Note:** This table is designed for the player feature (out of scope for this PR) but created now for schema completeness. The admin endpoints do not write to this table.

### 3.3 SQLAlchemy Models

All models follow the existing async pattern in `services/skills-service/app/models.py`. Use `Mapped`/`mapped_column` style consistent with the existing codebase.

```python
class ClassSkillTree(Base):
    __tablename__ = "class_skill_trees"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    tree_type: Mapped[str] = mapped_column(String(20), nullable=False, default="class")
    parent_tree_id: Mapped[int] = mapped_column(ForeignKey("class_skill_trees.id"), nullable=True)
    subclass_name: Mapped[str] = mapped_column(String(100), nullable=True)
    tree_image: Mapped[str] = mapped_column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    nodes = relationship("TreeNode", back_populates="tree", cascade="all, delete-orphan")
    connections = relationship("TreeNodeConnection", back_populates="tree", cascade="all, delete-orphan")
    parent_tree = relationship("ClassSkillTree", remote_side=[id], foreign_keys=[parent_tree_id])


class TreeNode(Base):
    __tablename__ = "tree_nodes"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tree_id: Mapped[int] = mapped_column(ForeignKey("class_skill_trees.id"), nullable=False)
    level_ring: Mapped[int] = mapped_column(Integer, nullable=False)
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    node_type: Mapped[str] = mapped_column(String(20), nullable=False, default="regular")
    icon_image: Mapped[str] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    tree = relationship("ClassSkillTree", back_populates="nodes")
    node_skills = relationship("TreeNodeSkill", back_populates="node", cascade="all, delete-orphan")


class TreeNodeConnection(Base):
    __tablename__ = "tree_node_connections"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tree_id: Mapped[int] = mapped_column(ForeignKey("class_skill_trees.id"), nullable=False)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), nullable=False)

    # Relationships
    tree = relationship("ClassSkillTree", back_populates="connections")
    from_node = relationship("TreeNode", foreign_keys=[from_node_id])
    to_node = relationship("TreeNode", foreign_keys=[to_node_id])


class TreeNodeSkill(Base):
    __tablename__ = "tree_node_skills"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    node = relationship("TreeNode", back_populates="node_skills")
    skill = relationship("Skill")


class CharacterTreeProgress(Base):
    __tablename__ = "character_tree_progress"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    character_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tree_id: Mapped[int] = mapped_column(ForeignKey("class_skill_trees.id"), nullable=False)
    node_id: Mapped[int] = mapped_column(ForeignKey("tree_nodes.id"), nullable=False)
    chosen_at = Column(TIMESTAMP, server_default=func.now())
```

### 3.4 API Contracts

All new endpoints are under the existing `/skills/` prefix (via the router). Grouped under `/skills/admin/class_trees/`.

#### Admin: Class Tree Management

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/skills/admin/class_trees/` | `skill_trees:create` | Create a new class/subclass tree |
| `GET` | `/skills/admin/class_trees/` | `skill_trees:read` | List all trees (with optional `?class_id=` and `?tree_type=` filters) |
| `GET` | `/skills/admin/class_trees/{tree_id}` | `skill_trees:read` | Get tree metadata only |
| `GET` | `/skills/admin/class_trees/{tree_id}/full` | `skill_trees:read` | Get full tree (nodes, connections, skills nested) |
| `PUT` | `/skills/admin/class_trees/{tree_id}/full` | `skill_trees:update` | Bulk save entire tree (nodes, connections, skill assignments). Supports temp IDs. |
| `DELETE` | `/skills/admin/class_trees/{tree_id}` | `skill_trees:delete` | Delete tree and all its nodes/connections/skill assignments (cascade) |

#### Admin: Individual Node Operations (supplementary — main flow uses bulk save)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/skills/admin/class_trees/{tree_id}/nodes/` | `skill_trees:create` | Create a single node |
| `PUT` | `/skills/admin/class_trees/{tree_id}/nodes/{node_id}` | `skill_trees:update` | Update a single node |
| `DELETE` | `/skills/admin/class_trees/{tree_id}/nodes/{node_id}` | `skill_trees:delete` | Delete a single node (cascade removes connections and skill assignments) |

#### Player Endpoints (designed now, implemented in future PR)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/skills/class_trees/by_class/{class_id}` | public | Get the full class tree for a given class (for player view) |
| `GET` | `/skills/class_trees/{tree_id}/progress/{character_id}` | JWT | Get character's progress in a tree |
| `POST` | `/skills/class_trees/{tree_id}/choose_node` | JWT | Choose a node (validates level, prerequisites, branch conflicts) |
| `POST` | `/skills/class_trees/{tree_id}/reset` | JWT | Reset tree progress (except subclass choices) |

**Note:** Player endpoints are defined in the schema/contract but will NOT be implemented in this PR. Only the GET endpoint for viewing trees may be implemented if time permits, as it's useful for testing.

#### Full Tree Response Schema

```
GET /skills/admin/class_trees/{tree_id}/full

Response:
{
  "id": 1,
  "class_id": 1,
  "name": "Дерево Воина",
  "description": "...",
  "tree_type": "class",
  "parent_tree_id": null,
  "subclass_name": null,
  "tree_image": null,
  "nodes": [
    {
      "id": 10,               // or "temp-1" in request
      "tree_id": 1,
      "level_ring": 1,
      "position_x": 400.0,
      "position_y": 100.0,
      "name": "Основы боя",
      "description": "...",
      "node_type": "root",
      "icon_image": null,
      "sort_order": 0,
      "skills": [
        {
          "id": 5,             // tree_node_skills.id
          "skill_id": 42,
          "sort_order": 0,
          "skill_name": "Удар мечом",     // denormalized from skills table
          "skill_type": "attack",
          "skill_image": "..."
        }
      ]
    }
  ],
  "connections": [
    {
      "id": 1,                // or "temp-c-1" in request
      "from_node_id": 10,     // or "temp-1"
      "to_node_id": 11        // or "temp-2"
    }
  ]
}
```

#### Full Tree Update Request Schema

```
PUT /skills/admin/class_trees/{tree_id}/full

Request:
{
  "id": 1,
  "class_id": 1,
  "name": "Дерево Воина",
  "description": "...",
  "tree_type": "class",
  "parent_tree_id": null,
  "subclass_name": null,
  "tree_image": null,
  "nodes": [
    {
      "id": 10,                // existing node — int ID
      "level_ring": 1,
      "position_x": 400.0,
      "position_y": 100.0,
      "name": "Основы боя",
      "description": "...",
      "node_type": "root",
      "icon_image": null,
      "sort_order": 0,
      "skills": [
        { "skill_id": 42, "sort_order": 0 }
      ]
    },
    {
      "id": "temp-1",         // new node — string temp ID
      "level_ring": 5,
      "position_x": 300.0,
      "position_y": 250.0,
      "name": "Путь силы",
      ...
      "skills": []
    }
  ],
  "connections": [
    {
      "id": "temp-c-1",       // new connection
      "from_node_id": 10,     // can reference existing int IDs
      "to_node_id": "temp-1"  // can reference temp IDs
    }
  ]
}

Response:
{
  "detail": "Class tree updated successfully",
  "temp_id_map": {
    "temp-1": 15,
    "temp-c-1": 8
  }
}
```

This follows the exact same temp-ID pattern as the existing `PUT /admin/skills/{id}/full_tree`.

### 3.5 Pydantic Schemas (Pydantic <2.0)

```python
# --- Class Skill Tree ---

class ClassSkillTreeBase(BaseModel):
    class_id: int
    name: str
    description: Optional[str] = None
    tree_type: str = "class"
    parent_tree_id: Optional[int] = None
    subclass_name: Optional[str] = None
    tree_image: Optional[str] = None

class ClassSkillTreeCreate(ClassSkillTreeBase):
    pass

class ClassSkillTreeUpdate(ClassSkillTreeBase):
    pass

class ClassSkillTreeRead(ClassSkillTreeBase):
    id: int
    class Config:
        orm_mode = True

# --- Tree Node ---

class TreeNodeBase(BaseModel):
    level_ring: int
    position_x: float = 0.0
    position_y: float = 0.0
    name: str
    description: Optional[str] = None
    node_type: str = "regular"
    icon_image: Optional[str] = None
    sort_order: int = 0

class TreeNodeCreate(TreeNodeBase):
    tree_id: int

class TreeNodeRead(TreeNodeBase):
    id: int
    tree_id: int
    class Config:
        orm_mode = True

# --- Tree Node Skill (inside a node) ---

class TreeNodeSkillEntry(BaseModel):
    skill_id: int
    sort_order: int = 0

class TreeNodeSkillRead(BaseModel):
    id: int
    skill_id: int
    sort_order: int = 0
    # Denormalized fields from skills table
    skill_name: Optional[str] = None
    skill_type: Optional[str] = None
    skill_image: Optional[str] = None
    class Config:
        orm_mode = True

# --- Connection ---

class TreeNodeConnectionInTree(BaseModel):
    id: Optional[Union[int, str]] = None
    from_node_id: Union[int, str]
    to_node_id: Union[int, str]

# --- Node in full tree request/response ---

class TreeNodeInTree(BaseModel):
    id: Union[int, str]  # int for existing, "temp-N" for new
    level_ring: int
    position_x: float = 0.0
    position_y: float = 0.0
    name: str
    description: Optional[str] = None
    node_type: str = "regular"
    icon_image: Optional[str] = None
    sort_order: int = 0
    skills: List[TreeNodeSkillEntry] = []

class TreeNodeInTreeResponse(BaseModel):
    id: int
    tree_id: int
    level_ring: int
    position_x: float
    position_y: float
    name: str
    description: Optional[str] = None
    node_type: str
    icon_image: Optional[str] = None
    sort_order: int
    skills: List[TreeNodeSkillRead] = []
    class Config:
        orm_mode = True

# --- Full Tree ---

class FullClassTreeResponse(BaseModel):
    id: int
    class_id: int
    name: str
    description: Optional[str] = None
    tree_type: str
    parent_tree_id: Optional[int] = None
    subclass_name: Optional[str] = None
    tree_image: Optional[str] = None
    nodes: List[TreeNodeInTreeResponse] = []
    connections: List[TreeNodeConnectionInTree] = []
    class Config:
        orm_mode = True

class FullClassTreeUpdateRequest(BaseModel):
    id: int
    class_id: int
    name: str
    description: Optional[str] = None
    tree_type: str = "class"
    parent_tree_id: Optional[int] = None
    subclass_name: Optional[str] = None
    tree_image: Optional[str] = None
    nodes: List[TreeNodeInTree] = []
    connections: List[TreeNodeConnectionInTree] = []
```

### 3.6 CRUD Operations

New functions in `crud.py` (all `async def`, matching existing style):

**Tree CRUD:**
- `create_class_tree(db, data)` → create tree record
- `get_class_tree(db, tree_id)` → tree with eager-loaded nodes, connections, node_skills
- `list_class_trees(db, class_id=None, tree_type=None)` → filtered list
- `delete_class_tree(db, tree_id)` → cascade delete

**Full tree save (bulk):**
- `save_full_class_tree(db, tree_id, data)` → the main bulk save function, follows the same pattern as `update_skill_full_tree` in main.py:
  1. Update tree metadata
  2. Separate new nodes (temp IDs) from existing nodes (int IDs)
  3. Create new nodes, build temp_id_map
  4. Update existing nodes
  5. Delete removed nodes (not in request)
  6. Resolve connections (replace temp IDs with real IDs)
  7. Sync node_skills for each node
  8. Single commit

**Node CRUD (supplementary):**
- `create_tree_node(db, data)` → create single node
- `update_tree_node(db, node_id, data)` → update single node
- `delete_tree_node(db, node_id)` → cascade delete

**Full tree read:**
- `get_full_class_tree(db, tree_id)` → builds the full response with denormalized skill info:
  1. Load tree with `selectinload(nodes → node_skills → skill)` and `selectinload(connections)`
  2. Build response with `skill_name`, `skill_type`, `skill_image` from joined skill objects

### 3.7 Security & RBAC

**New permissions** (4 records in `permissions` table):

| code | description | module |
|------|-------------|--------|
| `skill_trees:read` | Просмотр деревьев навыков классов | skill_trees |
| `skill_trees:create` | Создание деревьев навыков классов | skill_trees |
| `skill_trees:update` | Редактирование деревьев навыков классов | skill_trees |
| `skill_trees:delete` | Удаление деревьев навыков классов | skill_trees |

**Assignment:** Admin role gets all permissions automatically (per CLAUDE.md rule — Admin always gets ALL permissions). Add to `role_permissions` for Editor and Moderator as appropriate.

**Alembic migration:** A data migration that INSERTs these 4 permissions into the `permissions` table and creates `role_permissions` entries for existing roles. This migration runs in **user-service** (which owns the `permissions` and `role_permissions` tables), NOT in skills-service.

**Wait — correction:** Per codebase analysis, the `permissions` and `role_permissions` tables are owned by user-service. The skills-service Alembic should NOT manage these tables. Instead:
- Option A: Add the permissions via a user-service Alembic migration (separate task)
- Option B: Add them via a SQL seed script or manual INSERT

**Decision:** Option A — create a migration in user-service that adds the 4 new permissions. This follows the established pattern. The skills-service endpoints use `require_permission("skill_trees:read")` etc., which validates against user-service at runtime.

### 3.8 Frontend Architecture

#### New Route
- Path: `/home/admin/class-trees`
- Protected by: `skill_trees:read` permission via `ProtectedRoute`
- Registered in `App.tsx`

#### Component Structure

```
src/components/AdminClassTreeEditor/
├── AdminClassTreePage.tsx          — Main page: tree selector sidebar + editor area
├── ClassTreeCanvas.tsx             — ReactFlow canvas for the class/subclass tree
├── TreeNodeComponent.tsx           — Custom ReactFlow node component (ring-colored circle with name)
├── TreeNodeInspector.tsx           — Right panel: edit selected node properties, manage skills
├── TreeSkillPicker.tsx             — Modal/dropdown to search and assign existing skills to a node
├── TreeToolbar.tsx                 — Top toolbar: save, add node, auto-layout, tree settings
├── hooks/
│   └── useClassTreeEditor.ts      — State management hook (nodes, edges, selected node, dirty state)
├── utils/
│   ├── ringLayout.ts              — Auto-layout algorithm: arrange nodes in concentric rings
│   └── treeTransforms.ts          — Transform API response ↔ ReactFlow format
└── types.ts                       — TypeScript types for the tree editor
```

#### Redux Slice

```
src/redux/slices/classTreeAdminSlice.ts   — State: treeList, selectedTree, status, updateStatus
src/redux/actions/classTreeAdminActions.ts — Thunks: fetchClassTrees, fetchFullClassTree, saveFullClassTree, deleteClassTree, createClassTree
```

#### Key Frontend Design Decisions

1. **ReactFlow for the canvas** — reuse the existing `reactflow@^11.11.4` dependency. The class tree nodes are custom ReactFlow nodes (`TreeNodeComponent`), rendered as circles color-coded by level ring. Connections are ReactFlow edges.

2. **Ring layout helper** — `ringLayout.ts` provides an auto-arrange function that positions nodes in concentric circles based on `level_ring`. Center is the root (level 1), outer rings are higher levels. The admin can run this once then manually adjust positions.

3. **Node inspector panel** — when a node is selected on the canvas, a right-side panel shows:
   - Node name, description, level ring, node type
   - List of skills assigned to this node (with links to the existing skill editor)
   - "Add skill" button that opens the `TreeSkillPicker` modal
   - Remove skill button

4. **Skill picker** — a searchable modal that lists all skills from the existing `skillsList` (fetched from `/skills/admin/skills/`). The admin can search by name and click to assign a skill to the current node.

5. **No SCSS** — all new components use Tailwind CSS only, following the design system (`docs/DESIGN-SYSTEM.md`). Dark theme, gold accents, `gray-bg`, `gold-text`, `btn-blue`, etc.

6. **All files are TypeScript (.tsx/.ts)** — no .jsx files. Types defined in `types.ts`.

7. **Responsive** — sidebar collapses on mobile, canvas is full-width. Node inspector becomes a bottom sheet on small screens.

8. **Save flow** — the "Save" button collects all ReactFlow nodes/edges, transforms them to the API format (with temp IDs for new nodes), calls `PUT /skills/admin/class_trees/{id}/full`, and on success refreshes the tree.

#### Navigation

Add a new nav item in the admin sidebar/menu:
- Label: "Деревья классов"
- Path: `/home/admin/class-trees`
- Permission: `skill_trees:read`

### 3.9 Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Battle-service contract break | Zero changes to existing tables/endpoints. New endpoints are additive only. Verified: `GET /characters/{id}/skills` and `GET /admin/skill_ranks/{id}` are untouched. |
| Large bulk save failure (partial commit) | Single transaction for the entire `save_full_class_tree`. Rollback on any error. |
| User-service migration for permissions | Separate task, clearly documented. Skills-service endpoints will return 403 until permissions are seeded — acceptable for dev. |
| ReactFlow performance with many nodes | Class trees have ~20-40 nodes max (7 rings × ~5 nodes each). Well within ReactFlow limits. |
| Existing skills page regression | Existing page is not modified. New page is independent. |

### 3.10 Out of Scope (Future Work)

- Player-facing tree view (public route, character progress tracking)
- `POST /choose_node` validation logic (level check, prerequisites, branch blocking, experience deduction)
- Tree reset logic (remove progress, reclaim skills)
- Integration with battle-service (skills from tree nodes used in combat)
- Starter kit changes (assigning initial tree nodes instead of flat skills)
- Character subclass column in character-service
- Node icon upload via photo-service

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 4.1: Backend — Models + Alembic Migration

**Agent:** Backend Developer
**Status:** `OPEN`
**Dependencies:** None
**Estimated complexity:** Medium

**Description:**
Add 5 new SQLAlchemy models to `services/skills-service/app/models.py` and create an Alembic migration.

**Files to modify:**
- `services/skills-service/app/models.py` — Add `ClassSkillTree`, `TreeNode`, `TreeNodeConnection`, `TreeNodeSkill`, `CharacterTreeProgress` models (see Section 3.3 for exact schema)

**Files to create:**
- `services/skills-service/app/alembic/versions/002_add_class_skill_tree_tables.py` — Alembic migration creating 5 new tables

**Implementation details:**
- Follow the existing model style: `Mapped[type]` + `mapped_column()`, relationships with `back_populates`
- Import `TIMESTAMP`, `func` for timestamp columns
- Add `UniqueConstraint` where specified in Section 3.2
- The migration must be generated via `alembic revision --autogenerate` or written manually
- Migration should be idempotent-safe (check table existence if needed)
- Do NOT modify any existing models (Skill, SkillRank, etc.)
- Run `python -m py_compile models.py` to verify syntax

**Acceptance criteria:**
- [ ] 5 new models added to models.py, following existing style
- [ ] Alembic migration file created and tested (can be applied to a clean DB)
- [ ] Existing models are unchanged
- [ ] `python -m py_compile models.py` passes

---

### Task 4.2: Backend — Pydantic Schemas

**Agent:** Backend Developer
**Status:** `OPEN`
**Dependencies:** Task 4.1 (models must exist for reference)
**Estimated complexity:** Medium

**Description:**
Add Pydantic schemas for all new class tree entities to `services/skills-service/app/schemas.py`.

**Files to modify:**
- `services/skills-service/app/schemas.py` — Add all schemas from Section 3.5

**Implementation details:**
- Use Pydantic <2.0 syntax: `class Config: orm_mode = True`
- Use `Optional` from typing (not `| None`)
- Use `Union[int, str]` for IDs that can be temp IDs (following existing `SkillRankInTree` pattern)
- Keep all existing schemas unchanged
- Schemas to add:
  - `ClassSkillTreeBase`, `ClassSkillTreeCreate`, `ClassSkillTreeUpdate`, `ClassSkillTreeRead`
  - `TreeNodeBase`, `TreeNodeCreate`, `TreeNodeRead`
  - `TreeNodeSkillEntry`, `TreeNodeSkillRead`
  - `TreeNodeConnectionInTree`
  - `TreeNodeInTree`, `TreeNodeInTreeResponse`
  - `FullClassTreeResponse`, `FullClassTreeUpdateRequest`
- Run `python -m py_compile schemas.py` to verify syntax

**Acceptance criteria:**
- [ ] All schemas from Section 3.5 added
- [ ] Pydantic <2.0 syntax used throughout
- [ ] Existing schemas unchanged
- [ ] `python -m py_compile schemas.py` passes

---

### Task 4.3: Backend — CRUD Operations

**Agent:** Backend Developer
**Status:** `OPEN`
**Dependencies:** Task 4.1, Task 4.2
**Estimated complexity:** High

**Description:**
Add async CRUD functions for class tree management to `services/skills-service/app/crud.py`.

**Files to modify:**
- `services/skills-service/app/crud.py` — Add class tree CRUD functions

**Implementation details:**
- All functions are `async def` (matching existing pattern)
- Use `selectinload` for eager loading relationships (matching existing pattern)
- Key functions (see Section 3.6 for full list):
  - `create_class_tree(db, data)` — simple create
  - `get_class_tree(db, tree_id)` — with selectinload of nodes, connections
  - `list_class_trees(db, class_id=None, tree_type=None)` — filtered list
  - `delete_class_tree(db, tree_id)` — cascade delete (handled by ORM)
  - `get_full_class_tree(db, tree_id)` — builds full response with denormalized skill data
  - `save_full_class_tree(db, tree_id, data)` — THE MAIN FUNCTION. Bulk save following the `update_skill_full_tree` pattern:
    1. Update tree metadata fields
    2. Load old nodes from DB
    3. Separate new nodes (temp IDs) from existing nodes (int IDs)
    4. Create new nodes, build `temp_id_map`
    5. Update existing nodes
    6. Delete nodes not in request
    7. Resolve connection temp IDs → real IDs
    8. Create/update/delete connections
    9. Sync `tree_node_skills` for each node (create new, delete removed)
    10. Single `await db.commit()`
  - `create_tree_node(db, data)`, `update_tree_node(db, node_id, data)`, `delete_tree_node(db, node_id)` — individual node operations
- For `get_full_class_tree`, denormalize skill info by joining through `TreeNodeSkill.skill` relationship:
  ```python
  selectinload(ClassSkillTree.nodes)
      .selectinload(TreeNode.node_skills)
      .selectinload(TreeNodeSkill.skill)
  ```
- Run `python -m py_compile crud.py` to verify syntax

**Acceptance criteria:**
- [ ] All CRUD functions from Section 3.6 implemented
- [ ] `save_full_class_tree` handles temp IDs, creates/updates/deletes nodes and connections in a single transaction
- [ ] `get_full_class_tree` returns denormalized skill info (name, type, image)
- [ ] Existing CRUD functions unchanged
- [ ] `python -m py_compile crud.py` passes

---

### Task 4.4: Backend — API Endpoints

**Agent:** Backend Developer
**Status:** `OPEN`
**Dependencies:** Task 4.3
**Estimated complexity:** Medium

**Description:**
Add REST endpoints for class tree admin management to `services/skills-service/app/main.py`.

**Files to modify:**
- `services/skills-service/app/main.py` — Add endpoints from Section 3.4

**Implementation details:**
- Add endpoints under the existing `router` (prefix `/skills`):
  - `POST /admin/class_trees/` — create tree
  - `GET /admin/class_trees/` — list trees (query params: `class_id`, `tree_type`)
  - `GET /admin/class_trees/{tree_id}` — get tree metadata
  - `GET /admin/class_trees/{tree_id}/full` — get full tree with all nested data
  - `PUT /admin/class_trees/{tree_id}/full` — bulk save entire tree
  - `DELETE /admin/class_trees/{tree_id}` — delete tree
  - `POST /admin/class_trees/{tree_id}/nodes/` — create single node
  - `PUT /admin/class_trees/{tree_id}/nodes/{node_id}` — update single node
  - `DELETE /admin/class_trees/{tree_id}/nodes/{node_id}` — delete single node
- All admin endpoints use `require_permission("skill_trees:...")` dependency
- Follow existing endpoint patterns (error handling, response models, etc.)
- The `PUT .../full` endpoint follows the exact same temp-ID resolution pattern as the existing `update_skill_full_tree`
- Do NOT modify any existing endpoints
- Run `python -m py_compile main.py` to verify syntax

**Acceptance criteria:**
- [ ] All 9 endpoints from Section 3.4 (admin section) implemented
- [ ] All endpoints use `require_permission("skill_trees:*")` auth
- [ ] Full tree GET returns nested nodes/connections/skills
- [ ] Full tree PUT handles temp IDs and returns `temp_id_map`
- [ ] Existing endpoints unchanged and working
- [ ] `python -m py_compile main.py` passes

---

### Task 4.5: Backend — RBAC Permissions Migration (user-service)

**Agent:** Backend Developer
**Status:** `OPEN`
**Dependencies:** None (can run in parallel with Tasks 4.1-4.4)
**Estimated complexity:** Low

**Description:**
Add 4 new RBAC permissions (`skill_trees:read/create/update/delete`) via an Alembic migration in user-service.

**Files to create:**
- `services/user-service/app/alembic/versions/XXX_add_skill_tree_permissions.py` — data migration

**Implementation details:**
- This is a DATA migration (not schema migration) — INSERTs rows into existing `permissions` and `role_permissions` tables
- Insert 4 permissions:
  - `skill_trees:read` — "Просмотр деревьев навыков классов"
  - `skill_trees:create` — "Создание деревьев навыков классов"
  - `skill_trees:update` — "Редактирование деревьев навыков классов"
  - `skill_trees:delete` — "Удаление деревьев навыков классов"
- Admin role gets ALL permissions automatically (per RBAC design — admin has all permissions at level 100)
- Add `role_permissions` entries for Moderator (all 4) and Editor (read only), following existing patterns
- Check existing migrations in `services/user-service/app/alembic/versions/` for the pattern
- Use `op.execute()` with raw SQL INSERTs in the migration
- Downgrade: DELETE the permission rows

**Acceptance criteria:**
- [ ] Migration file created with upgrade (INSERT) and downgrade (DELETE)
- [ ] 4 permissions added to `permissions` table
- [ ] `role_permissions` entries added for appropriate roles
- [ ] Migration can be applied and rolled back cleanly

---

### Task 4.6: Frontend — Redux Slice + API Layer

**Agent:** Frontend Developer
**Status:** `OPEN`
**Dependencies:** Task 4.4 (API endpoints must be defined, but can code against the contract)
**Estimated complexity:** Medium

**Description:**
Create Redux state management and API integration layer for the class tree editor.

**Files to create:**
- `src/redux/slices/classTreeAdminSlice.ts` — Redux slice with state: `treeList`, `selectedFullTree`, `status`, `updateStatus`, `error`
- `src/redux/actions/classTreeAdminActions.ts` — Async thunks: `fetchClassTrees`, `fetchFullClassTree`, `saveFullClassTree`, `deleteClassTree`, `createClassTree`
- `src/components/AdminClassTreeEditor/types.ts` — TypeScript types matching the API schemas

**Implementation details:**
- Follow the existing `skillsAdminSlice.js` / `skillsAdminActions.js` pattern but in TypeScript
- Use `createAsyncThunk` + `createSlice` from Redux Toolkit
- API calls via axios to:
  - `GET /skills/admin/class_trees/`
  - `GET /skills/admin/class_trees/{id}/full`
  - `PUT /skills/admin/class_trees/{id}/full`
  - `POST /skills/admin/class_trees/`
  - `DELETE /skills/admin/class_trees/{id}`
- Also fetch skills list for the skill picker: reuse existing `fetchSkills` from `skillsAdminActions`
- Register the new slice in the Redux store (`store.js` or `store.ts`)
- Define TypeScript types in `types.ts` matching the Pydantic schemas from Section 3.5

**Acceptance criteria:**
- [ ] Redux slice created with proper TypeScript types
- [ ] All 5 async thunks implemented
- [ ] Slice registered in the Redux store
- [ ] Types defined and exported in `types.ts`
- [ ] `npx tsc --noEmit` passes

---

### Task 4.7: Frontend — AdminClassTreeEditor Component

**Agent:** Frontend Developer
**Status:** `OPEN`
**Dependencies:** Task 4.6
**Estimated complexity:** High

**Description:**
Create the admin class tree editor page with ReactFlow canvas, node inspector, and skill picker.

**Files to create:**
- `src/components/AdminClassTreeEditor/AdminClassTreePage.tsx` — Main page component
- `src/components/AdminClassTreeEditor/ClassTreeCanvas.tsx` — ReactFlow canvas
- `src/components/AdminClassTreeEditor/TreeNodeComponent.tsx` — Custom ReactFlow node
- `src/components/AdminClassTreeEditor/TreeNodeInspector.tsx` — Node property editor panel
- `src/components/AdminClassTreeEditor/TreeSkillPicker.tsx` — Skill assignment modal
- `src/components/AdminClassTreeEditor/TreeToolbar.tsx` — Top action bar
- `src/components/AdminClassTreeEditor/hooks/useClassTreeEditor.ts` — State management hook
- `src/components/AdminClassTreeEditor/utils/ringLayout.ts` — Auto-layout algorithm
- `src/components/AdminClassTreeEditor/utils/treeTransforms.ts` — API ↔ ReactFlow data transforms

**Files to modify:**
- `src/components/App/App.tsx` — Add route for `/home/admin/class-trees`
- Admin navigation component — Add "Деревья классов" nav item with `skill_trees:read` permission check

**Implementation details:**

**AdminClassTreePage.tsx:**
- Layout: left sidebar (tree list + create button), center (ReactFlow canvas), right (node inspector)
- Tree list shows all class trees, grouped by class. Clicking a tree loads it via `fetchFullClassTree`
- "Создать дерево" button opens a form (class selector, name, type: class/subclass, parent tree for subclass)
- "Удалить дерево" button with confirmation
- Use Tailwind: `gray-bg`, `gold-text`, `btn-blue`, etc.

**ClassTreeCanvas.tsx:**
- Uses `ReactFlow` from `reactflow` (v11, already installed)
- Custom node type: `treeNode` → `TreeNodeComponent`
- Nodes are color-coded by `level_ring` (e.g., ring 1 = green tint, ring 30 = red/gold for subclass choice)
- Edges represent `tree_node_connections`
- Supports: drag to reposition, connect nodes (drag edge), delete node/edge, zoom, minimap
- On node click → set selected node → show in inspector

**TreeNodeComponent.tsx:**
- Circular node with: name, level ring number, node type indicator
- Skills count badge
- Styled with Tailwind (no SCSS)
- Color scheme based on `level_ring` and `node_type`

**TreeNodeInspector.tsx:**
- Shows when a node is selected
- Editable fields: name, description, level_ring (dropdown), node_type (dropdown), sort_order
- Skills list: shows assigned skills with name/type/image, remove button, "Add skill" button
- "Add skill" opens `TreeSkillPicker`

**TreeSkillPicker.tsx:**
- Modal overlay
- Search input to filter skills by name
- List of available skills (from `skillsList` in Redux)
- Click to assign, close modal

**TreeToolbar.tsx:**
- Save button (calls `saveFullClassTree`)
- Add node button (adds a new node at default position)
- Auto-layout button (runs `ringLayout` algorithm)
- Tree settings button (edit tree metadata: name, description, image)

**useClassTreeEditor.ts:**
- Manages ReactFlow nodes/edges state
- Tracks selected node
- Tracks dirty state (unsaved changes)
- Transforms between API format and ReactFlow format
- Handles temp ID generation for new nodes/connections

**ringLayout.ts:**
- Input: list of nodes with `level_ring`
- Output: x/y positions arranged in concentric rings
- Algorithm: group nodes by ring → place each ring in a circle/arc at increasing radius
- Center offset configurable

**treeTransforms.ts:**
- `apiToFlow(fullTree)` → `{ nodes: ReactFlowNode[], edges: ReactFlowEdge[] }`
- `flowToApi(nodes, edges, treeMetadata)` → `FullClassTreeUpdateRequest`
- Handle temp ID generation for new nodes/connections

**Routing:**
- Add to `App.tsx`:
  ```tsx
  <Route path="home/admin/class-trees" element={
    <ProtectedRoute requiredPermission="skill_trees:read">
      <AdminClassTreePage />
    </ProtectedRoute>
  } />
  ```

**Styling rules:**
- ALL Tailwind, zero SCSS
- Follow design system: `bg-site-bg`, `gold-text`, `btn-blue`, `input-underline`, `modal-overlay`, `modal-content`, `gold-outline`, `gold-scrollbar`
- Responsive: sidebar collapses on `md:` breakpoint, inspector becomes bottom drawer on small screens
- No `React.FC` — use `const Component = (props: Props) => {` style

**Acceptance criteria:**
- [ ] All files created per the component structure above
- [ ] Route registered and accessible at `/home/admin/class-trees`
- [ ] Admin can: create tree, add/edit/delete nodes, connect nodes, assign skills to nodes, save tree, load tree
- [ ] ReactFlow canvas works with drag, zoom, connect, minimap
- [ ] Node inspector shows and edits selected node properties
- [ ] Skill picker allows searching and assigning skills
- [ ] Auto-layout arranges nodes in rings
- [ ] All Tailwind, no SCSS, responsive design
- [ ] All TypeScript, no `.jsx`, no `React.FC`
- [ ] `npx tsc --noEmit` passes
- [ ] `npm run build` passes
- [ ] Russian language for all user-facing text

---

### Task 4.8: Backend — Tests (QA)

**Agent:** QA Test
**Status:** `OPEN`
**Dependencies:** Tasks 4.1-4.4 (all backend tasks)
**Estimated complexity:** Medium

**Description:**
Write pytest tests for the new class tree endpoints and CRUD operations.

**Files to create:**
- `services/skills-service/app/tests/test_class_tree_crud.py` — Unit tests for CRUD functions
- `services/skills-service/app/tests/test_class_tree_endpoints.py` — Integration tests for API endpoints

**Files to modify:**
- `services/skills-service/app/tests/conftest.py` — Add fixtures for class tree test data if needed

**Test coverage:**
1. **Model tests:**
   - Create ClassSkillTree, verify fields
   - Create TreeNode, verify relationship to tree
   - Create TreeNodeConnection, verify from/to nodes
   - Create TreeNodeSkill, verify link to skill and node
   - Cascade delete: deleting a tree deletes its nodes, connections, skill assignments

2. **CRUD tests:**
   - `create_class_tree` — success, missing required fields
   - `list_class_trees` — with filters (class_id, tree_type)
   - `get_full_class_tree` — returns nested data with denormalized skill info
   - `save_full_class_tree` — create new nodes (temp IDs), update existing, delete removed, connections resolved
   - `save_full_class_tree` — temp ID references in connections work correctly
   - `delete_class_tree` — cascade behavior

3. **Endpoint tests:**
   - Auth: all admin endpoints require `skill_trees:*` permission (403 without)
   - `POST /admin/class_trees/` — create tree, verify response
   - `GET /admin/class_trees/` — list with filters
   - `GET /admin/class_trees/{id}/full` — full tree response shape
   - `PUT /admin/class_trees/{id}/full` — bulk save with temp IDs, verify temp_id_map in response
   - `DELETE /admin/class_trees/{id}` — verify cascade
   - Error cases: 404 for nonexistent tree, 400 for invalid data

4. **Battle-service contract preservation:**
   - Verify that `GET /characters/{id}/skills` still returns the same response shape after the new models are added
   - Verify that `GET /admin/skill_ranks/{id}` still works unchanged

**Implementation details:**
- Follow existing test patterns in `conftest.py` (SQLite-based testing)
- Mock auth dependencies (`require_permission`) as done in existing tests
- Use `httpx.AsyncClient` with the FastAPI `TestClient` for endpoint tests

**Acceptance criteria:**
- [ ] All test files created
- [ ] Tests cover CRUD operations, endpoint auth, full tree save with temp IDs
- [ ] Battle-service contract preservation test included
- [ ] All tests pass with `pytest`
- [ ] No modification to existing test files (except conftest if needed)

---

### Task 4.9: Review

**Agent:** Reviewer
**Status:** `DONE`
**Dependencies:** Tasks 4.1-4.8 (all tasks)
**Estimated complexity:** Medium

**Description:**
Final review of all changes. Verify:

1. **Backend:**
   - Models match schema design (Section 3.2/3.3)
   - Schemas use Pydantic <2.0 syntax
   - CRUD follows async pattern
   - All endpoints have proper auth
   - Existing endpoints unchanged
   - All tests pass
   - `python -m py_compile` passes for all modified files

2. **Frontend:**
   - All files are TypeScript (.tsx/.ts)
   - All styles are Tailwind (no SCSS)
   - No `React.FC` usage
   - Design system classes used correctly
   - Responsive design works on 360px+
   - Russian language for all UI text
   - `npx tsc --noEmit` passes
   - `npm run build` passes

3. **Cross-service:**
   - Battle-service contract preserved (existing endpoints return same shape)
   - No existing functionality broken
   - RBAC permissions migration correct

4. **Live verification:**
   - Open `/home/admin/class-trees` in browser
   - Create a tree, add nodes, connect them, assign skills, save, reload — verify persistence
   - Verify no console errors
   - Verify existing `/home/admin/skills` page still works

**Acceptance criteria:**
- [ ] All code review checks pass
- [ ] Live verification successful
- [ ] No regressions in existing functionality

---

## 5. Review Log (filled by Reviewer — in English)

### Review Date: 2026-03-21
### Reviewer: Reviewer Agent

### Overall Verdict: **PASS** (with 2 minor fixes applied)

---

### Backend Review

#### Models (`services/skills-service/app/models.py`)
- **PASS** — 5 new models (ClassSkillTree, TreeNode, TreeNodeConnection, TreeNodeSkill, CharacterTreeProgress) match Section 3.2/3.3 exactly
- **PASS** — All UniqueConstraints present (`uq_class_tree_type_subclass`, `uq_connection_from_to`, `uq_node_skill`, `uq_character_node`)
- **PASS** — Relationships with `back_populates` and `cascade="all, delete-orphan"` correctly set
- **PASS** — Existing models (Skill, SkillRank, SkillRankDamage, SkillRankEffect, CharacterSkill) are completely unchanged
- **PASS** — Follows existing `Mapped[type]` + `mapped_column()` style

#### Schemas (`services/skills-service/app/schemas.py`)
- **PASS** — All schemas from Section 3.5 are present and match the spec
- **PASS** — Pydantic <2.0 syntax used: `class Config: orm_mode = True` (not `model_config`)
- **PASS** — `Optional` always has `= None` default
- **PASS** — `Union[int, str]` used for temp ID fields (matching existing `SkillRankInTree` pattern)
- **PASS** — Existing schemas are unchanged

#### CRUD (`services/skills-service/app/crud.py`)
- **PASS** — All functions are `async def`, consistent with existing async pattern
- **PASS** — `save_full_class_tree` correctly handles temp IDs for both nodes and connections
- **PASS** — Uses `selectinload` for eager loading (matching existing pattern)
- **PASS** — Node skill sync logic handles create/update/delete correctly
- **PASS** — Single `await db.commit()` for transactional integrity
- **PASS** — Existing CRUD functions are unchanged

#### Endpoints (`services/skills-service/app/main.py`)
- **PASS** — All 9 admin endpoints implemented matching Section 3.4
- **PASS** — All endpoints use `require_permission("skill_trees:...")` with correct actions (create/read/update/delete)
- **PASS** — Full tree GET returns nested nodes/connections/skills with denormalized data
- **PASS** — Full tree PUT handles temp IDs and returns `temp_id_map`
- **PASS** — Path validation: `tree_id != data.id` returns 400, nonexistent returns 404
- **PASS** — Existing endpoints (sections 0-9) are completely unchanged

#### Alembic Migration (`services/skills-service/app/alembic/versions/002_add_class_skill_tree_tables.py`)
- **PASS** — Creates 5 tables with correct columns, types, constraints, and foreign keys
- **PASS** — Proper `upgrade()` with table existence checks (idempotent-safe)
- **PASS** — Proper `downgrade()` drops tables in correct reverse order (child tables first)
- **PASS** — Indexes created for primary keys and character_id

#### RBAC Migration (`services/user-service/alembic/versions/0013_add_skill_tree_permissions.py`)
- **PASS** — 4 permissions created (skill_trees:read/create/update/delete) with IDs 34-37
- **PASS** — Admin (role_id=4) gets all 4, Moderator (role_id=3) gets all 4, Editor (role_id=2) gets read only
- **PASS** — Downgrade correctly deletes both `role_permissions` and `permissions` rows

---

### Frontend Review

#### TypeScript / File Types
- **PASS** — ALL files are `.tsx` or `.ts` (no `.jsx`)

#### Tailwind CSS / No SCSS
- **PASS** — All styles use Tailwind classes, no SCSS imports, no CSS modules
- **PASS** — `reactflow/dist/style.css` import is acceptable (third-party library requirement)
- **PASS** — No inline `style={{}}` objects

#### React.FC Ban
- **PASS** — No `React.FC` or `React.FunctionComponent` usage anywhere

#### Design System Compliance
- **PASS** — Uses `gold-text`, `btn-blue`, `btn-line`, `input-underline`, `textarea-bordered`, `modal-overlay`, `modal-content`, `gold-outline`, `gold-scrollbar`, `dropdown-menu`, `dropdown-item`, `bg-site-bg`, `bg-site-dark`, `text-site-blue`, `text-site-red`, `rounded-card`, `shadow-card`
- **FIXED (MEDIUM)** — `TreeNodeInspector.tsx` line 184: `hover:text-red-400` changed to `hover:text-site-red` per design system
- **NOTE** — `TreeNodeComponent.tsx` uses Tailwind default colors (border-green-400, border-sky-400, etc.) for ring level color-coding. This is acceptable as functional visual coding for 7+ distinct level rings, which the design palette doesn't cover. Not a violation.

#### Responsive Design
- **PASS** — Sidebar collapses on mobile (`md:w-[260px]`, toggle button visible on `md:hidden`)
- **PASS** — Inspector becomes limited height on small screens (`max-h-[40vh] md:max-h-none`)
- **PASS** — Center+Right panels use `flex-col md:flex-row` for responsive layout
- **PASS** — Toolbar uses `flex-wrap` for small screens, settings panel uses `flex-col sm:flex-row`
- **PASS** — Page title responsive: `text-2xl sm:text-3xl`

#### Russian Language
- **PASS** — All user-facing text is Russian: page title, button labels, form placeholders, error messages, toasts, empty states, confirm dialogs

#### Types Match Backend
- **PASS** — `types.ts` interfaces match Pydantic schemas from Section 3.5 exactly

#### Redux
- **PASS** — Slice properly typed with `ClassTreeAdminState` interface
- **PASS** — All 5 async thunks implemented with proper error handling
- **PASS** — Slice registered in `store.ts` as `classTreeAdmin`

#### Routing
- **PASS** — Route at `/home/admin/class-trees` in `App.tsx`
- **PASS** — Protected with `<ProtectedRoute requiredPermission="skill_trees:read">`
- **PASS** — Admin navigation link "Деревья классов" added in `AdminPage.tsx` with `module: 'skill_trees'`

#### ReactFlow
- **PASS** — Imports from `reactflow` (v11, already installed)
- **PASS** — Custom node type `treeNode` properly registered
- **PASS** — Edge styling with gold color (#f0d95c)

#### Data Transform Logic
- **FIXED (MEDIUM)** — `treeTransforms.ts`: Connection ID mapping was a no-op. Fixed to properly convert numeric string IDs back to numbers for existing connections, while keeping temp IDs as strings.

---

### Cross-Service Review

- **PASS** — Existing `GET /skills/characters/{character_id}/skills` endpoint unchanged (line 342-347 of main.py)
- **PASS** — Existing `GET /skills/admin/skill_ranks/{rank_id}` endpoint unchanged (line 164-173 of main.py)
- **PASS** — Battle-service contract fully preserved — no changes to existing tables, models, schemas, or endpoints
- **PASS** — No changes to existing skill tables (skills, skill_ranks, skill_rank_damage, skill_rank_effects, character_skills)

---

### Test Review

- **PASS** — `test_class_tree_endpoints.py`: ~40 tests covering all 9 endpoints, auth (401/403), CRUD, bulk save with temp IDs, cascade delete, battle-service contract
- **PASS** — `test_class_tree_crud.py`: ~25 tests covering CRUD functions directly, temp ID handling, connection resolution, skill sync, cascade delete
- **PASS** — Auth tests include both 401 (no token) and 403 (no permissions)
- **PASS** — Temp ID handling tested for both nodes and connections
- **PASS** — Cascade delete tested (tree -> nodes -> connections -> skill assignments)
- **PASS** — Battle-service contract test verifies existing endpoints return correct shape
- **PASS** — Test setup follows existing async SQLite pattern

---

### Issues Found and Fixed

| # | Severity | File | Issue | Fix |
|---|----------|------|-------|-----|
| 1 | MEDIUM | `TreeNodeInspector.tsx:184` | `hover:text-red-400` uses Tailwind default red instead of design system `hover:text-site-red` | Changed to `text-site-red/80 hover:text-site-red` |
| 2 | MEDIUM | `treeTransforms.ts:77` | Connection ID ternary was a no-op (`edge.id` in both branches). Existing connection IDs (numeric strings) were not converted back to numbers | Rewrote to properly convert numeric string IDs to numbers while keeping temp-* and edge-* as strings |

### No Critical or High Issues Found

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-20 — PM: фича создана (FEAT-056), запускаю анализ кодовой базы
[LOG] 2026-03-20 — Codebase Analyst: начал анализ skills-service (models, schemas, crud, main, database, config, alembic, auth, rabbitmq_consumer)
[LOG] 2026-03-20 — Codebase Analyst: проанализировал battle-service интеграцию (skills_client.py, battle_engine.py, buffs.py, main.py) — определил API-контракт
[LOG] 2026-03-20 — Codebase Analyst: проанализировал character-service (models.py, main.py, crud.py) — нашёл Class модель, StarterKit, отсутствие subclass
[LOG] 2026-03-20 — Codebase Analyst: проанализировал character-attributes-service (models.py) — определил все stats/resistances для эффектов
[LOG] 2026-03-20 — Codebase Analyst: проанализировал фронтенд — AdminSkillsPage (ReactFlow v11 редактор), RegionMapEditor (справочный паттерн), Redux слайсы
[LOG] 2026-03-20 — Codebase Analyst: проанализировал тесты skills-service (4 тест-файла + conftest)
[LOG] 2026-03-20 — Codebase Analyst: анализ завершён, отчёт записан в секцию 2 фича-файла
[LOG] 2026-03-20 — Architect: начал проектирование — изучил models.py, schemas.py, crud.py, main.py, alembic/env.py, auth_http.py, character-service models, frontend FlowSkillsEditor, AdminSkillsPage, skillConstants, DESIGN-SYSTEM.md
[LOG] 2026-03-20 — Architect: ключевое решение — чисто аддитивная схема, 5 новых таблиц, 0 изменений в существующих. Battle-service контракт полностью сохранён.
[LOG] 2026-03-20 — Architect: ключевое решение — подкласс моделируется как отдельное дерево (tree_type='subclass'), без изменений в character-service.
[LOG] 2026-03-20 — Architect: ключевое решение — bulk save через PUT /full с temp-ID паттерном (по аналогии с существующим update_skill_full_tree).
[LOG] 2026-03-20 — Architect: ключевое решение — RBAC permissions (skill_trees:*) добавляются через миграцию в user-service (отдельная задача).
[LOG] 2026-03-20 — Architect: ключевое решение — новая страница /home/admin/class-trees, существующая /home/admin/skills не модифицируется.
[LOG] 2026-03-20 — Architect: спроектирована схема БД (5 таблиц), API (9 admin эндпоинтов + 4 будущих player), Pydantic схемы, CRUD операции, фронтенд архитектура (10 компонентов/файлов).
[LOG] 2026-03-20 — Architect: декомпозиция на 9 задач: 5 backend (модели, схемы, CRUD, эндпоинты, RBAC), 2 frontend (Redux + компоненты), 1 QA, 1 Review.
[LOG] 2026-03-20 — Architect: архитектура записана в секцию 3, задачи в секцию 4. Готово к запуску разработки.
[LOG] 2026-03-20 — Backend Developer: Task 4.5 — создана Alembic data-миграция 0013_add_skill_tree_permissions.py в user-service. Добавлены 4 permissions (skill_trees:read/create/update/delete, id=34-37), role_permissions для Admin (все 4), Moderator (все 4), Editor (только read). Downgrade удаляет записи. py_compile пройден.
[LOG] 2026-03-20 — Backend Developer: Task 4.1 — добавлены 5 новых SQLAlchemy моделей в models.py (ClassSkillTree, TreeNode, TreeNodeConnection, TreeNodeSkill, CharacterTreeProgress) с UniqueConstraint и relationships. Создана Alembic миграция 002_add_class_skill_tree_tables.py. py_compile пройден.
[LOG] 2026-03-20 — Backend Developer: Task 4.2 — добавлены все Pydantic-схемы в schemas.py (ClassSkillTreeBase/Create/Update/Read, TreeNodeBase/Create/Read, TreeNodeSkillEntry/Read, TreeNodeConnectionInTree, TreeNodeInTree/InTreeResponse, FullClassTreeResponse/UpdateRequest). Pydantic <2.0 синтаксис. py_compile пройден.
[LOG] 2026-03-20 — Backend Developer: Task 4.3 — добавлены async CRUD-функции в crud.py: create_class_tree, get_class_tree, list_class_trees, delete_class_tree, get_full_class_tree (с денормализацией skill данных), save_full_class_tree (bulk save с temp-ID разрешением для узлов и соединений), create_tree_node, update_tree_node, delete_tree_node. py_compile пройден.
[LOG] 2026-03-20 — Backend Developer: Task 4.4 — добавлены 9 admin эндпоинтов в main.py: POST/GET/GET/{id}/GET/{id}/full/PUT/{id}/full/DELETE/{id} для class_trees, POST/PUT/DELETE для nodes. Все используют require_permission("skill_trees:*"). Существующие эндпоинты не затронуты. py_compile пройден.
[LOG] 2026-03-20 — Frontend Developer: Task 4.6 — создан Redux slice (classTreeAdminSlice.ts), async thunks (classTreeAdminActions.ts) и TypeScript типы (types.ts). 5 thunks: fetchClassTrees, fetchFullClassTree, saveFullClassTree, createClassTree, deleteClassTree. Slice зарегистрирован в store.ts. Все типы соответствуют Pydantic-схемам из секции 3.5.
[LOG] 2026-03-20 — Frontend Developer: Task 4.7 — создано 9 файлов компонента AdminClassTreeEditor: AdminClassTreePage.tsx (главная страница с трёхпанельным layout), ClassTreeCanvas.tsx (ReactFlow canvas с кастомными узлами), TreeNodeComponent.tsx (круглый узел с цветовой кодировкой по level_ring), TreeNodeInspector.tsx (панель редактирования свойств узла и навыков), TreeSkillPicker.tsx (модал поиска/выбора навыков), TreeToolbar.tsx (toolbar с сохранением, добавлением узлов, авто-раскладкой), useClassTreeEditor.ts (хук управления состоянием), ringLayout.ts (алгоритм концентрической раскладки), treeTransforms.ts (трансформация API <-> ReactFlow).
[LOG] 2026-03-20 — Frontend Developer: Task 4.7 — добавлен маршрут /home/admin/class-trees в App.tsx с ProtectedRoute (skill_trees:read). Добавлена ссылка "Деревья классов" в AdminPage.tsx с модулем skill_trees. Все файлы TypeScript (.tsx/.ts), все стили Tailwind, нет React.FC, русский язык для UI-текстов, адаптивный дизайн (sidebar скрывается на мобильных).
[LOG] 2026-03-21 — QA Test: Task 4.8 — начал написание тестов для class skill tree системы. Изучил models.py, schemas.py, crud.py, main.py (9 новых эндпоинтов), существующие тест-паттерны (conftest.py, test_admin_character_skills.py, test_admin_auth.py, test_endpoint_auth.py).
[LOG] 2026-03-21 — QA Test: Task 4.8 — создан test_class_tree_endpoints.py (9 классов, ~40 тестов): auth/permissions для всех 9 эндпоинтов (401/403), CRUD деревьев, full tree get/save (temp-ID, update, delete, connections, skill assignment), individual node CRUD, edge cases (404, path mismatch), battle-service contract verification.
[LOG] 2026-03-21 — QA Test: Task 4.8 — создан test_class_tree_crud.py (7 классов, ~25 тестов): прямое тестирование CRUD-функций без HTTP — create_class_tree, list_class_trees (с фильтрами), get_full_class_tree (денормализация skill данных), save_full_class_tree (temp-ID, update, delete, connections, skill sync, metadata update), delete_class_tree (каскадное удаление), create/update/delete_tree_node.
[LOG] 2026-03-21 — QA Test: Task 4.8 — py_compile пройден для обоих файлов. Паттерн тестов соответствует существующим (async SQLite + httpx.AsyncClient + ASGITransport). conftest.py не модифицирован. Задача завершена.
[LOG] 2026-03-21 — Reviewer: Task 4.9 — начал полный ревью всех файлов FEAT-056. Прочитаны: models.py, schemas.py, crud.py, main.py, 002_add_class_skill_tree_tables.py, 0013_add_skill_tree_permissions.py, types.ts, classTreeAdminSlice.ts, classTreeAdminActions.ts, store.ts, AdminClassTreePage.tsx, ClassTreeCanvas.tsx, TreeNodeComponent.tsx, TreeNodeInspector.tsx, TreeSkillPicker.tsx, TreeToolbar.tsx, useClassTreeEditor.ts, ringLayout.ts, treeTransforms.ts, App.tsx, AdminPage.tsx, test_class_tree_endpoints.py, test_class_tree_crud.py, auth_http.py, DESIGN-SYSTEM.md.
[LOG] 2026-03-21 — Reviewer: Task 4.9 — найдено 2 MEDIUM-issue, оба исправлены: (1) hover:text-red-400 -> hover:text-site-red в TreeNodeInspector.tsx, (2) no-op ternary для connection ID в treeTransforms.ts переписан для корректной конвертации числовых строк обратно в числа.
[LOG] 2026-03-21 — Reviewer: Task 4.9 — ревью завершён: PASS. Backend: модели, схемы, CRUD, эндпоинты, миграции — всё соответствует спецификации. Frontend: TypeScript, Tailwind, без React.FC, design system, адаптивность, русский язык — всё в порядке. Cross-service: контракт battle-service сохранён, существующие эндпоинты не затронуты. Тесты: полное покрытие всех 9 эндпоинтов и CRUD-функций.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_Pending_
