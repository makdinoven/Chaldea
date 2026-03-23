# FEAT-064: NPC Attack (Replace Training Battle) + NPC Skills in Admin

## Meta

| Field | Value |
|-------|-------|
| **Status** | OPEN |
| **Created** | 2026-03-23 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-064-npc-attack-and-skills.md` → `DONE-FEAT-064-npc-attack-and-skills.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Два изменения для NPC (не мобов):

1. **Замена "тренировочный бой" на "Нападение"**: на NPC можно только напасть (принудительный бой). При поражении NPC умирает — получает статус DEAD в админке и исчезает с локации. Штрафов для игрока пока нет (в будущем — система репутации).

2. **Навыки для NPC в админке**: Возможность назначать NPC навыки в админ-панели (аналогично мобам через MobTemplateSkill).

### Бизнес-правила
- NPC больше нельзя вызвать на тренировочный бой — только напасть.
- Нападение на NPC — принудительный бой, NPC не может отказаться.
- При смерти NPC → статус DEAD, исчезает с локации, без респауна.
- Штрафов для нападающего пока нет (будущее: репутация).
- В админке NPC должна быть возможность назначать навыки (как у мобов).

### UX / Пользовательский сценарий
1. Игрок видит NPC на локации.
2. Нажимает кнопку "Напасть" (вместо "Тренировочный бой").
3. Бой начинается принудительно.
4. При поражении NPC — NPC получает статус DEAD, исчезает.
5. В админке: управление навыками NPC аналогично мобам.

### Edge Cases
- Что если NPC уже в бою? → Кнопка неактивна / сообщение.
- Что если NPC уже мёртв? → Не показывается на локации.
- NPC без навыков → бой возможен, NPC просто атакует базовой атакой.

### Вопросы к пользователю
- [x] NPC и мобы — разные? → Да, NPC (npc_role='npc') отдельно от мобов (npc_role='mob').
- [x] Навыки для NPC в админке как у мобов? → Да.
- [x] Смерть NPC = статус DEAD, исчезает? → Да, без респауна.
- [x] Штрафы за убийство NPC? → Пока нет, в будущем репутация.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Port | Role in Feature | Changes Needed |
|---------|------|----------------|----------------|
| **character-service** | 8005 | NPC data, admin endpoints, NPC status | Add `npc_status` column to `characters`, new admin skill management endpoints, filter dead NPCs from location query |
| **battle-service** | 8010 | Battle creation, post-battle NPC death | New NPC attack endpoint (or modify existing PvP attack), post-battle hook to mark NPC dead |
| **autobattle-service** | 8011 | NPC AI in battle | Already auto-registers all `is_npc=True` characters — works for NPCs out of the box |
| **locations-service** | 8006 | Fetches NPCs for location display | No code changes needed (calls character-service which will filter dead NPCs) |
| **frontend** | 5555 | NPC attack button, admin skill editor | Add "Attack" button to NPC profile modal, build NPC skill management UI in admin |

### NPC vs Mob: Key Differences

NPCs and mobs share the `characters` table with `is_npc=True` but differ in architecture:

| Aspect | NPC (npc_role != 'mob') | Mob (npc_role = 'mob') |
|--------|------------------------|----------------------|
| **Creation** | Admin creates directly in `characters` table via `POST /characters/admin/npcs` | Admin creates `MobTemplate`, then spawning creates a `Character` record |
| **Template system** | No template — each NPC is unique | `MobTemplate` + `ActiveMob` tracking |
| **Status tracking** | No status field on `characters` table | `ActiveMob.status` enum: `alive`, `in_battle`, `dead` |
| **Skills storage** | `character_skills` table (shared with players) | `mob_template_skills` (template-level) + `character_skills` (copied at spawn time) |
| **Skills admin UI** | `NpcStatsEditor` — read-only skill display, no add/remove UI | `AdminMobSkills` — full search, add, remove, save via Redux + `PUT /admin/mob-templates/{id}/skills` |
| **Location filtering** | `GET /characters/npcs/by_location` filters `is_npc=True AND npc_role != 'mob'` | `GET /characters/mobs/by_location` uses `ActiveMob` join |
| **Death handling** | No death mechanism exists | `ActiveMob.status = 'dead'`, `killed_at` timestamp, optional respawn |
| **Battle initiation** | No direct battle mechanism from location page | `POST /battles/` with player + mob character_ids |

### Current NPC Battle Flow (NONE exists)

Currently there is **no way to initiate a battle with an NPC from the location page**. The NPC interaction flow is:

1. Player sees NPC in `PlayersSection` (right column: "НПС на локации")
2. Clicks NPC card → opens `NpcProfileModal`
3. Modal shows: profile info + "Поговорить" (dialogue), "Торговля" (shop), "Задания" (quests) buttons
4. **No battle/attack button exists**

The `PlayerActionsMenu` (FEAT-063) added PvP actions (training duel, attack) for **player-to-player** only. It checks `player.user_id !== currentUserId` and uses the PvP invite/attack system which validates `user_id` ownership. NPCs have `user_id=None`, so the existing PvP attack endpoint would fail at line 1556: `if attacker["user_id"] != current_user.id`.

### Battle Service: NPC Handling

**Battle creation** (`POST /battles/`): Creates a battle with arbitrary character_ids and teams. This is the endpoint used for mob battles. It does NOT check if participants are NPCs or players — it works for any character. After creation, it auto-registers `is_npc=True` characters with autobattle-service (lines 364-396).

**Post-battle rewards** (`_distribute_pve_rewards`): Only triggers for defeated mobs — it calls `GET /characters/internal/mob-reward-data/{char_id}` which checks `is_npc=True AND npc_role='mob'`. For non-mob NPCs (e.g., `npc_role='merchant'`), this returns 404 and no rewards are distributed.

**Post-battle consequences** (lines 903-921): Checks `battle_type` column:
- `pvp_training` → set loser HP to 1
- `pvp_death` → unlink character from user
- `pve` / `pvp_attack` → no special handling

**Key insight**: A new NPC attack can reuse the existing `POST /battles/` endpoint (same as mobs) since it already handles `is_npc` auto-registration with autobattle. The `battle_type` would be `pve` (default). A **new post-battle hook** is needed to detect defeated NPCs (not mobs) and mark them dead.

### NPC Death: No Status Field Exists

The `characters` table has **no status/alive/dead column**. Only `ActiveMob` has a `status` field. For NPCs, death needs a new mechanism:

**Option A**: Add `npc_status` column to `characters` table (e.g., `ENUM('alive', 'dead')`, default `'alive'`).
- Pros: Simple, direct on the Character model.
- Cons: Affects all characters (players too), though only checked for NPCs.

**Option B**: Add a separate `npc_status` table or reuse a field like `current_location_id = NULL` for dead NPCs.
- Cons: Less explicit, harder to query.

**Recommendation**: Option A — add `npc_status` column. The `get_npcs_by_location` endpoint (line 1832) already filters by `is_npc=True AND npc_role != 'mob'`. Adding `AND npc_status != 'dead'` is straightforward. Admin can see dead NPCs with a filter.

### NPC Admin: Current State

**File**: `services/frontend/app-chaldea/src/components/AdminNpcsPage/AdminNpcsPage.tsx`

Current admin features for NPCs:
- **List**: Paginated table with search by name, filter by role
- **Create/Edit**: Full form (name, role, class, race, level, sex, age, location, avatar, biography, etc.)
- **Delete**: Cascade cleanup (attributes, inventory, skills via HTTP calls)
- **Sub-editors**: Dialogues (`DialogueEditor`), Shop (`NpcShopEditor`), Quests (`QuestEditor`), Stats & Skills (`NpcStatsEditor`)

**NpcStatsEditor** (`services/frontend/app-chaldea/src/components/AdminNpcsPage/NpcStatsEditor.tsx`):
- Has two tabs: "Характеристики" (stats editing) and "Навыки" (skills display)
- **Stats tab**: Full attribute editing via `PUT /attributes/admin/{npcId}` + recalculate
- **Skills tab**: READ-ONLY — displays assigned skills but has no add/remove UI. Shows a message: "Навыки можно назначить через API: POST /skills/assign_multiple"

### Mob Skills Admin: Reference Pattern

**File**: `services/frontend/app-chaldea/src/components/Admin/MobsPage/AdminMobSkills.tsx`

The mob skill management UI provides:
1. **Current skills display**: Chip-style tags with skill name + rank, "x" to remove
2. **Skill search**: Debounced input → `GET /skills/admin/skills/?q={query}` → list of skills
3. **Rank selection**: Click skill → expand → show ranks → "Добавить"/"Убрать" toggle per rank
4. **Save**: `PUT /characters/admin/mob-templates/{id}/skills` with `{ skill_rank_ids: number[] }`
5. **Change detection**: Compare original vs current, show save button only if changed

**Backend endpoint**: `PUT /admin/mob-templates/{template_id}/skills` in character-service (line 1992) calls `crud.replace_mob_skills()` which deletes all `MobTemplateSkill` rows and re-inserts.

**Key difference for NPCs**: Mob skills are stored in `mob_template_skills` (template level). NPC skills are stored in `character_skills` (character level, shared with players). The NPC skill management needs to use `character_skills` directly — via skills-service API (`POST /skills/assign_multiple`, `DELETE /skills/admin/character_skills/by_character/{npc_id}`).

### NPC Skills: Existing Backend Support

Skills-service already has the needed endpoints:
- `GET /skills/characters/{character_id}/skills` — list assigned skills (used by NpcStatsEditor)
- `POST /skills/assign_multiple` — assign skills to a character (referenced in NpcStatsEditor placeholder text)
- `DELETE /skills/admin/character_skills/by_character/{character_id}` — delete all skills for a character (used by NPC delete cascade)
- `GET /skills/admin/skills/?q={query}` — search skills (used by AdminMobSkills)
- `GET /skills/admin/skills/{skill_id}/full_tree` — get skill ranks (used by AdminMobSkills)

**No new backend endpoints are needed for NPC skill management** — the frontend just needs to build a UI that calls existing skills-service endpoints directly (similar to AdminMobSkills but operating on `character_skills` instead of `mob_template_skills`).

### DB Changes Needed

| Change | Table | Service | Migration |
|--------|-------|---------|-----------|
| Add `npc_status` column | `characters` | character-service | Alembic migration: `ALTER TABLE characters ADD COLUMN npc_status ENUM('alive', 'dead') NOT NULL DEFAULT 'alive'` |

No new tables needed. NPC skills already use `character_skills` table.

### Frontend Changes Needed

| Component | File | Change |
|-----------|------|--------|
| `NpcProfileModal` | `services/frontend/app-chaldea/src/components/pages/LocationPage/NpcProfileModal.tsx` | Add "Напасть" button that creates a battle via `POST /battles/` |
| `PlayersSection` / `NpcCard` | `services/frontend/app-chaldea/src/components/pages/LocationPage/PlayersSection.tsx` | No change — dead NPCs won't be returned by API |
| `NpcStatsEditor` | `services/frontend/app-chaldea/src/components/AdminNpcsPage/NpcStatsEditor.tsx` | Replace read-only skills tab with full add/remove/save UI (pattern from `AdminMobSkills`) |
| `AdminNpcsPage` | `services/frontend/app-chaldea/src/components/AdminNpcsPage/AdminNpcsPage.tsx` | Show `npc_status` (alive/dead) in table, add filter for status, add "resurrect" button for dead NPCs |
| `types.ts` | `services/frontend/app-chaldea/src/components/pages/LocationPage/types.ts` | No change needed — NpcInLocation type doesn't need status (dead ones are filtered server-side) |

### API Changes Needed

| Endpoint | Service | Change |
|----------|---------|--------|
| `GET /characters/npcs/by_location` | character-service | Add filter: `npc_status != 'dead'` |
| `GET /characters/admin/npcs` | character-service | Return `npc_status` field, add optional `status` query param |
| `PUT /characters/admin/npcs/{id}` | character-service | Allow setting `npc_status` (for resurrect) |
| `GET /characters/admin/npcs/{id}` | character-service | Return `npc_status` field |
| Post-battle hook in `main.py` | battle-service | After battle finishes, if defeated character is NPC (not mob): set `npc_status = 'dead'` |

### Cross-Service Impact

- **locations-service**: Calls `character-service` for NPC list — no code change needed, will automatically get filtered results.
- **battle-service**: Needs post-battle hook modification. The `_distribute_pve_rewards` already handles mob death via `ActiveMob.status`. NPC death needs a separate check.
- **autobattle-service**: Already handles all `is_npc=True` characters — no changes needed.
- **skills-service**: Already has all needed endpoints — no changes needed.

### Risks

1. **NPC attack on safe locations**: The PvP attack endpoint blocks attacks on safe locations. The NPC attack flow (via `POST /battles/`) has no such check. Decision needed: should NPC attacks be allowed on safe locations? The feature brief doesn't specify.

2. **NPC already in battle**: Need to check if NPC is already in an active battle before allowing attack. The `get_active_battle_for_character()` function exists in battle-service.

3. **Battle type for NPC attacks**: Using `POST /battles/` creates a `pve` type battle (default). The post-battle hook needs to handle NPC death for `pve` battles where the defeated character is an NPC (not mob). This must not interfere with the existing mob death flow.

4. **NPC skill management via skills-service**: The `POST /skills/assign_multiple` endpoint may require specific payload format. Need to verify the exact API contract.

5. **Alembic migration**: Adding `npc_status` to `characters` table affects character-service migration. Other services reading `characters` table directly (photo-service mirrors) should not be affected since the new column has a default value.

6. **No "in_battle" status for NPCs**: Mobs have `ActiveMob.status = 'in_battle'`. NPCs have no equivalent. The frontend should check the battle API (`GET /battles/character/{id}/in-battle`) to disable the attack button if the NPC is already fighting.

---

## 3. Architecture Decision (filled by Architect — in English)

### Overview

Two independent parts: (A) NPC Attack + Death system, (B) NPC Skills admin UI. Both are relatively small and well-scoped.

### Part A: NPC Attack + Death

#### DB Change: `npc_status` column

Add `npc_status` column to `characters` table via Alembic migration `008_add_npc_status.py` in character-service.

```sql
ALTER TABLE characters ADD COLUMN npc_status ENUM('alive', 'dead') NOT NULL DEFAULT 'alive';
```

- Column applies to ALL characters but is only semantically used for NPCs (`is_npc=True AND npc_role != 'mob'`).
- Default `'alive'` ensures backward compatibility — existing rows get `'alive'` automatically.
- The `Character` model in `models.py` must be updated to include this column.
- The `NpcUpdate` schema must include `npc_status: Optional[str] = None` to allow admin resurrect.

#### API Changes (character-service)

**1. `GET /characters/npcs/by_location/{location_id}`** — Add filter `npc_status != 'dead'`:
```python
# Add to existing filter chain:
models.Character.npc_status != 'dead',
```

**2. `GET /characters/admin/npcs`** — Add optional `npc_status` query param:
```python
npc_status: Optional[str] = Query(None, description="Filter by NPC status (alive/dead)")
```
Return `npc_status` in the response. Update `NpcListItem` schema to include `npc_status: Optional[str] = None`.

**3. `GET /characters/admin/npcs/{npc_id}`** — Add `npc_status` to the response dict:
```python
"npc_status": npc.npc_status,
```

**4. `PUT /characters/admin/npcs/{npc_id}`** — Already uses `data.dict(exclude_unset=True)` + `setattr` loop. Adding `npc_status` to `NpcUpdate` schema is sufficient — no endpoint code change needed.

**5. New internal endpoint: `PUT /characters/internal/npc-status/{character_id}`** — Used by battle-service to mark NPC dead after battle. No auth required (internal). Returns 404 if character not found or not an NPC.

```python
@router.put("/internal/npc-status/{character_id}")
def update_npc_status(character_id: int, status: str = Body(..., embed=True), db = Depends(get_db)):
    npc = db.query(Character).filter(Character.id == character_id, Character.is_npc == True, Character.npc_role != 'mob').first()
    if not npc:
        raise HTTPException(404, "NPC not found")
    npc.npc_status = status
    db.commit()
    return {"ok": True}
```

#### Battle Flow: NPC Attack

**Frontend initiates battle** using existing `POST /battles/` — same endpoint used for mobs:
```json
{
  "players": [
    { "character_id": <player_char_id>, "team": 0 },
    { "character_id": <npc_char_id>, "team": 1 }
  ]
}
```

This works because:
- `POST /battles/` validates ownership (player's character must belong to current user) — passes since player owns their character.
- Auto-registers `is_npc=True` characters with autobattle-service — works for NPCs.
- Default `battle_type` = `pve` — correct for NPC attack.
- No safe-location restriction in this endpoint (unlike PvP attack).

**Post-battle NPC death hook** in battle-service `main.py` — add after the existing PvP consequences block (after line ~960). After battle finishes with a winner, for each defeated participant:
1. Check if the defeated character is an NPC (not mob): query `SELECT is_npc, npc_role FROM characters WHERE id = :cid`
2. If `is_npc=True AND npc_role != 'mob'` → call `PUT /characters/internal/npc-status/{char_id}` with `{"status": "dead"}`
3. This is separate from the existing mob death flow (`_distribute_pve_rewards` → `active-mob-status`) and does not interfere with it.

#### Frontend: Attack Button

**Location 1: NpcProfileModal** — Add "Напасть" button always visible (NPCs can be attacked on ANY location). The button:
- Calls `GET /battles/character/{npcId}/in-battle` first to check if NPC is already in battle → if yes, show toast "НПС уже в бою".
- Calls `POST /battles/` with player + NPC character_ids on teams 0 and 1.
- On success, navigates to `/battle/{battle_id}`.
- Uses red-tinted styling to differentiate from interaction buttons (gold): `border border-site-red/50 bg-site-red/10 text-site-red hover:bg-site-red/20 hover:border-site-red/80`.

**Location 2: NpcCard in PlayersSection** — Add a small "Напасть" action button below the NPC card (under role label). This mirrors how `PlayerActionsMenu` works for players but is simpler — just a single button, no dropdown needed. Only shown if user has a character (`currentCharacterId != null`).

The NpcCard currently takes `npc` and `onClick` (opens modal). We extend it to also accept `currentCharacterId` and render an attack button. The attack button handler is the same logic as in NpcProfileModal (check in-battle, create battle, navigate).

To avoid duplication, extract the attack logic into a shared hook: `useNpcAttack(npcId, currentCharacterId)` that returns `{ attacking, handleAttack }`.

#### Edge Cases

- **NPC already in battle**: Check via `GET /battles/character/{npcId}/in-battle` before creating battle. Show "НПС уже в бою" toast if true.
- **Player already in battle**: `POST /battles/` will reject (existing validation in battle-service). Show error from response.
- **NPC is dead**: Dead NPCs are filtered out of `GET /characters/npcs/by_location` — player never sees them. If somehow accessed, the battle will still work but won't matter since the NPC won't be visible.

### Part B: NPC Skills in Admin

#### No backend changes needed

All required endpoints exist in skills-service:
- `GET /skills/characters/{character_id}/skills` — list current skills
- `POST /skills/assign_multiple` — assign skills (`{ character_id, skills: [{ skill_id, rank_number }] }`)
- `DELETE /skills/admin/character_skills/by_character/{character_id}` — clear all skills
- `GET /skills/admin/skills/?q={query}` — search skills
- `GET /skills/admin/skills/{skill_id}/full_tree` — get skill with ranks

#### Frontend: NpcSkillsEditor

Replace the read-only skills tab content in `NpcStatsEditor` with a full skill management UI. Two approaches:

**Option chosen: Inline in NpcStatsEditor** — The skills tab already exists in NpcStatsEditor. Replace the read-only content with the full editor UI directly (no separate component file). The NpcStatsEditor is already scoped to a single NPC and has `npcId` prop.

The skill editor UI follows the `AdminMobSkills` pattern:
1. **Current skills display**: Chip tags with skill name + rank + "x" remove button.
2. **Search**: Debounced input → `GET /skills/admin/skills/?q={query}`.
3. **Rank expansion**: Click skill → load full tree → show ranks with "Добавить"/"Убрать" buttons.
4. **Save**: On save, call `DELETE /skills/admin/character_skills/by_character/{npcId}` then `POST /skills/assign_multiple` with the full list. This "replace all" approach matches the mob pattern.
5. **Change detection**: Compare original skill_rank_ids vs current, show save button only on change.

**Key difference from AdminMobSkills**: AdminMobSkills uses Redux (`mobsSlice.updateMobSkills`). NPC skills will use direct axios calls (no Redux slice needed — NPC admin is already pure axios). The save flow:
1. `DELETE /skills/admin/character_skills/by_character/{npcId}` — clear existing
2. `POST /skills/assign_multiple` — assign new set
3. Refresh skill list via `GET /skills/characters/{npcId}/skills`

#### Admin NPC List: Status Column + Resurrect

In `AdminNpcsPage.tsx`:
- Add `npc_status` to `NpcListItem` interface.
- Show status badge in the NPC table row (green "Жив" / red "Мёртв").
- Add status filter dropdown next to role filter.
- For dead NPCs, show a "Воскресить" button that calls `PUT /characters/admin/npcs/{id}` with `{ npc_status: "alive" }`.

### Design System Usage

| Element | Classes |
|---------|---------|
| Attack button (modal) | `border border-site-red/50 bg-site-red/10 text-site-red hover:bg-site-red/20 hover:border-site-red/80 rounded-card` |
| Attack button (card) | `text-site-red text-[10px] sm:text-xs hover:text-white transition-colors` |
| Skill chips | `bg-white/[0.07] rounded-full px-3 py-1.5` (from AdminMobSkills) |
| Remove skill | `text-site-red hover:text-white` |
| Search input | `input-underline` |
| Save button | `btn-blue` |
| Status badge alive | `px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-xs` |
| Status badge dead | `px-2 py-0.5 rounded-full bg-site-red/20 text-site-red text-xs` |
| Resurrect button | `btn-line` |

### Risks & Mitigations

1. **Race condition: NPC attacked by two players simultaneously** — `POST /battles/` will create two separate battles. The second battle's post-battle hook will try to set `npc_status='dead'` on an already-dead NPC — harmless (idempotent). To prevent, the frontend checks `in-battle` before creating. Low risk.

2. **Migration on shared DB** — `ALTER TABLE characters ADD COLUMN` with default is an online DDL operation in MySQL 8.0. No downtime needed.

3. **`POST /skills/assign_multiple` payload format** — Verified: `{ character_id: int, skills: [{ skill_id: int, rank_number: int }] }`. The delete+reassign flow needs the skill_id and rank_number, not skill_rank_id. The NPC skills editor must store both when loading current skills (the `GET /skills/characters/{id}/skills` response includes `skill_id` and `rank_number`).

4. **NPC attack button on NpcCard** — Adding `currentCharacterId` prop to PlayersSection → NpcCard chain requires threading the prop through. PlayersSection already receives `currentCharacterId` as a prop — just need to pass it down.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task Table

| # | Description | Agent | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|-------|------------|---------------------|
| T1 | **Alembic migration: add `npc_status` column** | Backend Dev | `services/character-service/app/alembic/versions/008_add_npc_status.py`, `services/character-service/app/models.py` | — | Migration adds `npc_status ENUM('alive','dead') NOT NULL DEFAULT 'alive'` to `characters` table. Model updated. `python -m py_compile` passes. |
| T2 | **character-service: NPC status API changes** | Backend Dev | `services/character-service/app/main.py`, `services/character-service/app/schemas.py` | T1 | (1) `GET /npcs/by_location` filters out dead NPCs. (2) `GET /admin/npcs` supports `npc_status` query param and returns `npc_status`. (3) `GET /admin/npcs/{id}` returns `npc_status`. (4) `PUT /admin/npcs/{id}` accepts `npc_status`. (5) New `PUT /internal/npc-status/{id}` sets NPC status. All compile cleanly. |
| T3 | **battle-service: post-battle NPC death hook** | Backend Dev | `services/battle-service/app/main.py` | T2 | After battle finishes, defeated NPC characters (is_npc=True, npc_role != 'mob') get `npc_status='dead'` via HTTP call to character-service. Existing mob death flow unaffected. `python -m py_compile` passes. |
| T4 | **Frontend: NPC attack button + useNpcAttack hook** | Frontend Dev | `services/frontend/app-chaldea/src/hooks/useNpcAttack.ts` (new), `services/frontend/app-chaldea/src/components/pages/LocationPage/NpcProfileModal.tsx`, `services/frontend/app-chaldea/src/components/pages/LocationPage/PlayersSection.tsx` | T3 | (1) "Напасть" button in NpcProfileModal creates battle via `POST /battles/` and navigates to `/battle/{id}`. (2) "Напасть" button on NpcCard in PlayersSection (visible when user has character). (3) Button disabled/toast when NPC is in battle. (4) All files are TypeScript. (5) `npx tsc --noEmit` and `npm run build` pass. (6) Mobile-responsive (360px+). |
| T5 | **Frontend: NPC skills editor in admin** | Frontend Dev | `services/frontend/app-chaldea/src/components/AdminNpcsPage/NpcStatsEditor.tsx` | — | (1) Skills tab has full add/remove/save UI (search, rank selection, chips). (2) Save clears existing skills then assigns new set. (3) Change detection — save button only shows on change. (4) Pattern matches AdminMobSkills. (5) `npx tsc --noEmit` and `npm run build` pass. (6) Mobile-responsive. |
| T6 | **Frontend: NPC status in admin list + resurrect** | Frontend Dev | `services/frontend/app-chaldea/src/components/AdminNpcsPage/AdminNpcsPage.tsx` | T2 | (1) NPC table shows status badge (alive/dead). (2) Status filter dropdown. (3) "Воскресить" button for dead NPCs. (4) `npx tsc --noEmit` and `npm run build` pass. |
| T7 | **QA: Backend tests for NPC status and death** | QA Test | `services/character-service/tests/test_npc_status.py` (new), `services/battle-service/tests/test_npc_death.py` (new) | T2, T3 | (1) Test `GET /npcs/by_location` excludes dead NPCs. (2) Test `PUT /internal/npc-status/{id}` sets status. (3) Test admin endpoints return `npc_status`. (4) Test post-battle NPC death hook (mock). All tests pass with `pytest`. |

### Task Details

#### T1: Alembic migration + model update

**Migration file**: `008_add_npc_status.py`
```python
revision = '008_add_npc_status'
down_revision = '007_seed_mob_template_skills'

def upgrade():
    op.add_column('characters', sa.Column('npc_status', sa.Enum('alive', 'dead', name='npc_status_enum'), nullable=False, server_default='alive'))

def downgrade():
    op.drop_column('characters', 'npc_status')
```

**Model change** in `models.py`:
```python
npc_status = Column(Enum('alive', 'dead', name='npc_status_enum'), nullable=False, default='alive', server_default='alive')
```

#### T2: character-service API changes

5 changes in `main.py` + 2 schema changes in `schemas.py`. See Architecture Decision section for exact specifications.

**Schemas**:
- `NpcListItem`: add `npc_status: Optional[str] = None`
- `NpcUpdate`: add `npc_status: Optional[str] = None`

#### T3: battle-service post-battle hook

Add after the PvP consequences block (~line 960). For each defeated participant (hp <= 0, team != winner_team):
1. Query `SELECT is_npc, npc_role FROM characters WHERE id = :cid`
2. If `is_npc=True AND npc_role != 'mob'` → `PUT {CHARACTER_SERVICE_URL}/characters/internal/npc-status/{cid}` with body `{"status": "dead"}`
3. Log success/failure.

#### T4: Frontend attack button

**New file**: `useNpcAttack.ts` hook:
- Takes `npcId: number`, `npcName: string`, `currentCharacterId: number`
- Returns `{ attacking: boolean, handleAttack: () => Promise<void> }`
- Logic: check in-battle → create battle → navigate

**NpcProfileModal changes**:
- Import and use `useNpcAttack`
- Add "Напасть" button with sword SVG icon, red-tinted styling
- Always visible (no condition like hasDialogue/hasShop)
- Requires `currentCharacterId` from Redux store (already available via `useAppSelector`)

**PlayersSection changes**:
- Pass `currentCharacterId` to `NpcCard`
- NpcCard renders small attack button below role label when `currentCharacterId` is provided
- Import `useNpcAttack` in NpcCard, add `useNavigate`

#### T5: NPC skills editor

Replace the read-only skills section in NpcStatsEditor (lines 227-254) with full editor UI. Use the same visual pattern as AdminMobSkills:
- Chip tags for current skills
- Search input with debounce
- Expandable skill → rank list
- Add/remove rank toggles
- Save button (delete all + assign multiple)

Key data flow difference: AdminMobSkills uses `skill_rank_id` (integer IDs). NPC skills editor needs to work with `skill_id + rank_number` pairs for `POST /skills/assign_multiple`, but also track `skill_rank_id` for the current skills display (returned by `GET /skills/characters/{id}/skills`).

#### T6: Admin NPC status display

Minor changes to AdminNpcsPage:
- Add `npc_status` to `NpcListItem` interface
- Add status badge in table row
- Add status filter select (next to role filter)
- Add "Воскресить" button for dead NPCs (calls `PUT /admin/npcs/{id}` with `{ npc_status: "alive" }`, then refetch list)

#### Parallelization

- **T1** → **T2** → **T3** (sequential, backend chain)
- **T5** can run in parallel with T1-T3 (no backend dependency)
- **T4** depends on T3 (needs the post-battle hook to exist)
- **T6** depends on T2 (needs npc_status in API responses)
- **T7** depends on T2 and T3

```
T1 → T2 → T3 → T4
          ↘ T6
          ↘ T7
T5 (parallel, independent)
```

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-23

**Reviewer:** QA Test + Reviewer (combined)

#### Checklist

- [x] **Pydantic <2.0 syntax** — All schemas use `class Config: orm_mode = True`, `@validator`. No `model_config` usage. PASS.
- [x] **No React.FC** — Zero occurrences in all modified/new frontend files. PASS.
- [x] **TypeScript + Tailwind only** — All frontend files are `.tsx`/`.ts`. No SCSS/CSS imports. All styles are Tailwind utility classes. PASS.
- [x] **Responsive 360px+** — All components use `sm:` breakpoints, grid adapts (`grid-cols-2 sm:grid-cols-3`), mobile cards layout in AdminNpcsPage. PASS.
- [x] **Russian UI text** — All user-facing strings in Russian: "Напасть", "Атака...", "НПС уже в бою", "Не удалось начать бой", "Жив", "Мёртв", "Воскресить", etc. PASS.
- [x] **Error handling on API calls** — All API calls have try/catch with toast.error(). useNpcAttack extracts `detail` from AxiosError. NpcStatsEditor handles save errors. AdminNpcsPage handles all CRUD errors. PASS.
- [x] **Auth on public endpoints, no auth on internal** — `PUT /internal/npc-status/{id}` has no auth dependency (correct for internal). `GET /admin/npcs` uses `require_permission("npcs:read")`. `PUT /admin/npcs/{id}` uses `require_permission("npcs:update")`. PASS.
- [x] **NPC death flow doesn't break mob death flow** — NPC death hook runs AFTER PvE reward distribution. The SQL query explicitly filters `npc_role != 'mob'`. Mob death via `ActiveMob.status` and `_distribute_pve_rewards` is untouched. PASS.
- [x] **`python -m py_compile`** — All modified Python files compile cleanly: `models.py`, `schemas.py`, `main.py` (character-service), `main.py` (battle-service), migration `008_add_npc_status.py`. PASS.
- [x] **Cross-service API consistency** — Frontend `createBattle()` calls `POST /battles/` with `{players: [{character_id, team}]}` — matches backend. `useNpcAttack` checks `GET /battles/character/{id}/in-battle` — endpoint exists in battle-service. Admin resurrect calls `PUT /characters/admin/npcs/{id}` with `{npc_status: "alive"}` — `NpcUpdate` schema accepts this field. Internal hook calls `PUT /characters/internal/npc-status/{id}` with `{status: "dead"}` — `UpdateNpcStatusRequest` schema validates this. PASS.

#### Backend Review

**T1: Migration (008_add_npc_status.py)**
- Correct: `ENUM('alive','dead')`, `NOT NULL`, `server_default='alive'`.
- `down_revision` correctly points to `007_seed_mob_template_skills`.
- Downgrade drops column cleanly.
- PASS.

**T2: character-service API changes**
- `GET /npcs/by_location`: filter `npc_status != 'dead'` correctly added to query chain.
- `GET /admin/npcs`: `npc_status` query param added, filter applied when present.
- `GET /admin/npcs/{id}`: returns `npc_status` in response dict.
- `PUT /admin/npcs/{id}`: `NpcUpdate` schema has `npc_status` with validator restricting to `alive`/`dead`.
- `PUT /internal/npc-status/{id}`: No auth, validates NPC (is_npc=True, npc_role != 'mob'), uses `UpdateNpcStatusRequest` with validator, proper error handling with `SQLAlchemyError` catch and rollback.
- `NpcListItem` schema includes `npc_status: Optional[str] = None`.
- PASS.

**T3: battle-service post-battle hook**
- Placed AFTER PvE reward distribution (line ~991), correct order.
- Iterates defeated participants (hp <= 0, team != winner_team).
- SQL check: `is_npc = 1 AND (npc_role IS NULL OR npc_role != 'mob')` — correctly handles NPCs with NULL npc_role.
- HTTP call to character-service with timeout=10.0.
- Error handling: catches `httpx.RequestError` and general `Exception` separately.
- Logging: success and error paths both logged.
- PASS.

#### Frontend Review

**T4: useNpcAttack hook + attack buttons**
- Hook takes `npcId`, `npcName`, `currentCharacterId`.
- Checks `currentCharacterId` before proceeding.
- Checks NPC in-battle status via `GET /battles/character/{npcId}/in-battle`.
- Creates battle via `createBattle()` from `api/mobs.ts`.
- Navigates to `/location/${locationId}/battle/${battle_id}`.
- Error handling with Russian messages.
- NpcProfileModal: attack button shown only when `characterId` exists, red-tinted styling per design system, disabled state with spinner.
- PlayersSection: `NpcAttackButton` component, `e.stopPropagation()` to prevent opening modal, shown when `currentCharacterId != null`.
- PASS.

**T5: NPC skills editor in NpcStatsEditor**
- Full skill management: search with debounce, rank expansion, add/remove, chip tags.
- Save flow: DELETE all → POST assign_multiple → refresh. Matches architecture spec.
- Change detection via sorted string comparison of `skill_id:rank_number`.
- Save button only shown when `hasSkillChanges` is true.
- Uses design system classes: `bg-white/[0.07] rounded-full`, `input-underline`, `btn-blue`, `text-site-red`.
- PASS.

**T6: Admin NPC status display**
- `NpcListItem` interface includes `npc_status: string | null`.
- Status badges: green "Жив" / red "Мёртв" in both desktop table and mobile cards.
- Status filter dropdown next to role filter.
- "Воскресить" button for dead NPCs, calls `PUT /admin/npcs/{id}` then refetches.
- Both desktop and mobile layouts include status display.
- PASS.

#### QA Tests Written

**`services/character-service/app/tests/test_npc_status.py`** (T7):
- TestNpcsByLocationFiltering: dead NPCs excluded, alive NPCs returned, mobs excluded, empty location.
- TestInternalNpcStatus: set dead, set alive, 404 for nonexistent, 404 for player, 404 for mob, 422 for invalid status.
- TestAdminNpcListStatus: includes npc_status field, filter by status.
- TestAdminNpcResurrect: resurrect dead NPC, kill via admin.
- Total: 12 test cases.

**`services/battle-service/app/tests/test_npc_death.py`** (T7):
- test_npc_marked_dead_after_defeat: verifies HTTP PUT call to character-service.
- test_mob_not_affected_by_npc_death_hook: verifies no npc-status call for mobs.
- test_player_not_affected_by_npc_death_hook: verifies no npc-status call for players.
- Total: 3 test cases.

#### Verdict: **PASS**

All tasks T1-T7 implemented correctly. No blocking issues found. Code follows project conventions, design system, and mandatory rules (TypeScript, Tailwind, Pydantic v1, no React.FC, Russian UI text, error handling, responsive design).

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-23 — PM: фича создана (FEAT-064), запускаю анализ кодовой базы
[LOG] 2026-03-23 — Codebase Analyst: анализ завершён. Ключевые находки: (1) NPC не имеют статуса alive/dead — нужна новая колонка npc_status в characters, (2) боевой механизм для NPC отсутствует — NpcProfileModal не имеет кнопки атаки, (3) POST /battles/ подходит для создания боя с NPC (уже работает для мобов), (4) навыки NPC хранятся в character_skills, бэкенд skills-service уже имеет все нужные эндпоинты — нужен только фронтенд UI, (5) NpcStatsEditor показывает навыки read-only — нужно добавить add/remove как в AdminMobSkills
[LOG] 2026-03-23 — Architect: архитектура спроектирована. 7 задач: (T1) Alembic миграция npc_status, (T2) API изменения в character-service — фильтрация мёртвых NPC + internal endpoint, (T3) post-battle hook в battle-service — смерть NPC, (T4) фронтенд кнопка "Напасть" + хук useNpcAttack в NpcProfileModal и NpcCard, (T5) полный редактор навыков NPC в админке (паттерн AdminMobSkills), (T6) статус NPC в админ-списке + воскрешение, (T7) QA тесты. T5 параллелен остальным задачам. Бэкенд skills-service не требует изменений.
[LOG] 2026-03-23 — Backend Dev: T1 выполнена — Alembic миграция 008_add_npc_status добавляет колонку npc_status ENUM('alive','dead') DEFAULT 'alive' в characters. Модель Character обновлена.
[LOG] 2026-03-23 — Backend Dev: T2 выполнена — (1) GET /npcs/by_location фильтрует мёртвых NPC, (2) GET /admin/npcs поддерживает фильтр npc_status и возвращает его, (3) GET /admin/npcs/{id} возвращает npc_status, (4) PUT /admin/npcs/{id} принимает npc_status для воскрешения, (5) PUT /internal/npc-status/{id} — новый internal endpoint для battle-service. Схемы NpcListItem и NpcUpdate обновлены, добавлена UpdateNpcStatusRequest.
[LOG] 2026-03-23 — Backend Dev: T3 выполнена — post-battle hook в battle-service: после распределения наград проверяет побеждённых участников, если is_npc=True AND npc_role != 'mob' — вызывает PUT /characters/internal/npc-status/{id} с status=dead. Существующий flow смерти мобов не затронут. Все файлы прошли py_compile.
[LOG] 2026-03-23 — Frontend Dev: T4 выполнена — (1) создан хук useNpcAttack.ts (проверка in-battle, createBattle, навигация к /battle/{id}), (2) кнопка "Напасть" в NpcProfileModal с красным стилем и иконкой молнии, показывается при наличии characterId, (3) кнопка "Напасть" под NPC-аватарами в PlayersSection через компонент NpcAttackButton, (4) все файлы TypeScript, стили Tailwind, адаптивность 360px+.
[LOG] 2026-03-23 — Frontend Dev: T5 выполнена — заменена read-only вкладка навыков в NpcStatsEditor на полный редактор: поиск навыков с debounce, раскрытие рангов, добавление/удаление chip-тегами, сохранение через DELETE + POST /skills/assign_multiple, детектирование изменений. Паттерн из AdminMobSkills адаптирован для character_skills.
[LOG] 2026-03-23 — Frontend Dev: T6 выполнена — (1) колонка npc_status в NpcListItem interface, (2) статус-бейджи "Жив"/"Мёртв" в таблице и мобильных карточках, (3) фильтр по статусу в шапке списка, (4) кнопка "Воскресить" для мёртвых NPC через PUT /admin/npcs/{id} с npc_status='alive'.
[LOG] 2026-03-23 — QA Test: T7 выполнена — написаны тесты: (1) test_npc_status.py для character-service (12 тестов: фильтрация мёртвых NPC, internal endpoint, админ-список со статусом, воскрешение), (2) test_npc_death.py для battle-service (3 теста: смерть NPC после боя, мобы не затронуты, игроки не затронуты). Все файлы прошли py_compile.
[LOG] 2026-03-23 — Reviewer: Review #1 завершён — PASS. Все задачи T1-T7 реализованы корректно. Чеклист пройден полностью: Pydantic <2.0, TypeScript, Tailwind, no React.FC, Russian UI, error handling, адаптивность, auth, кросс-сервисная консистентность. Никаких блокирующих проблем не обнаружено.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
