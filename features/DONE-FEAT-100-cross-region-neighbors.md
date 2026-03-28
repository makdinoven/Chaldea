# FEAT-100: Кросс-региональное соседство через стрелки

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-28 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-100-cross-region-neighbors.md` → `DONE-FEAT-100-cross-region-neighbors.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Расширение системы стрелок перехода (FEAT-099): когда обе стороны парных стрелок соединены с локациями путями (ArrowNeighbor), автоматически создавать реальное соседство (LocationNeighbor) между этими локациями. Это позволяет игроку перемещаться напрямую из локации одного региона в локацию другого через список соседей, без необходимости использовать карту.

Также: подсветка пути на карте соседнего региона — если игрок на локации A и смотрит карту региона B через стрелку, путь от стрелки к локации B подсвечивается как "активный".

### Бизнес-правила
- Когда админ соединяет обе стороны парных стрелок с локациями (A→Стрелка1 в регионе 1, Стрелка2→B в регионе 2), автоматически создаётся LocationNeighbor(A, B)
- При удалении любого ArrowNeighbor — удаляется соответствующий кросс-региональный LocationNeighbor
- При удалении стрелки — удаляются все связанные кросс-региональные LocationNeighbor
- Игрок видит локацию B в списке соседей локации A и может переместиться напрямую
- На карте: если игрок на локации A (регион 1) и смотрит карту региона 2 через стрелку, путь стрелка→B подсвечивается как активный
- Энергия перемещения между кросс-региональными соседями: сумма energy_cost обоих ArrowNeighbor

### UX / Пользовательский сценарий

**Админ:**
1. Создал парные стрелки между регионами 1 и 2 (уже есть из FEAT-099)
2. В регионе 1: проложил путь от локации A к стрелке1
3. В регионе 2: проложил путь от стрелки2 к локации B
4. Система автоматически создала соседство A↔B

**Игрок:**
1. Находится на локации A в регионе 1
2. В списке соседей видит локацию B (из другого региона)
3. Может переместиться в B напрямую
4. На карте региона 1: видит подсвеченный путь A→стрелка
5. Кликает стрелку → открывается карта региона 2
6. На карте региона 2: видит подсвеченный путь стрелка→B (потому что игрок "связан" через стрелку)
7. Понимает полный маршрут: A → стрелка → стрелка → B

### Edge Cases
- Одна сторона стрелки ещё не соединена с локацией — кросс-соседство не создаётся (ждём вторую сторону)
- Несколько локаций соединены с одной стрелкой — создаются N×M кросс-соседств
- Стрелка удалена — все кросс-соседства удаляются
- ArrowNeighbor обновлён (другая локация) — старое кросс-соседство удаляется, новое создаётся

### Вопросы к пользователю (если есть)
- Нет открытых вопросов

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| locations-service | CRUD logic extension, new API response fields | `app/crud.py`, `app/models.py`, `app/schemas.py`, `app/main.py` |
| frontend | Arrow edge highlight logic, types | `RegionInteractiveMap.tsx`, `WorldPage.tsx`, `worldMapSlice.ts` |

### Existing Patterns

- **locations-service**: Async SQLAlchemy (aiomysql), Pydantic <2.0, Alembic present (auto-migration on startup).
- **Frontend**: TypeScript, React 18, Redux Toolkit, Tailwind CSS. RegionInteractiveMap is already `.tsx`.

### Current State of Relevant Code

#### 1. Models (`services/locations-service/app/models.py`)

**LocationNeighbor** (line 139):
```python
class LocationNeighbor(Base):
    __tablename__ = "LocationNeighbors"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    location_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    neighbor_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    energy_cost = Column(Integer, nullable=False)
    path_data = Column(JSON, nullable=True)
```

**RegionTransitionArrow** (line 423):
- Fields: `id`, `region_id`, `target_region_id`, `paired_arrow_id` (self-FK), `x`, `y`, `label`
- `paired_arrow_id` links two arrows bidirectionally (arrow1.paired_arrow_id = arrow2.id and vice versa).

**ArrowNeighbor** (line 435):
- Fields: `id`, `location_id` (FK to Locations), `arrow_id` (FK to arrows, CASCADE), `energy_cost`, `path_data`
- Represents a path from a location to an arrow on the same region's map.

**Key relationship**: ArrowNeighbor cascade-deletes when its arrow is deleted (FK ondelete='CASCADE').

#### 2. CRUD Functions (`services/locations-service/app/crud.py`)

**`create_arrow_neighbor(session, arrow_id, data)`** (line 3604):
- Creates/upserts an ArrowNeighbor row (location_id + arrow_id).
- Does NOT currently check for paired arrow or create cross-region LocationNeighbors.
- This is the trigger point: after creating an ArrowNeighbor, we need to check if the paired arrow also has ArrowNeighbors and if so, create LocationNeighbor pairs.

**`delete_arrow_neighbor(session, location_id, arrow_id)`** (line 3707):
- Deletes a single ArrowNeighbor row.
- Does NOT currently clean up cross-region LocationNeighbors.

**`delete_transition_arrow(session, arrow_id)`** (line 3564):
- Deletes both arrows in a pair. ArrowNeighbor rows cascade-delete via FK.
- Does NOT currently clean up cross-region LocationNeighbors (they won't cascade because LocationNeighbor references Locations, not arrows).

**`add_neighbor(session, location_id, neighbor_id, energy_cost, path_data)`** (line 653):
- Creates bidirectional LocationNeighbor (forward + reverse) with upsert logic.
- This is the existing function to reuse for creating cross-region neighbors.

**`update_location_neighbors(session, location_id, neighbors)`** (line 1044):
- Replaces ALL neighbors for a location. WARNING: This deletes all existing neighbors first, including cross-region ones. This could be a problem — if an admin uses this to edit regular neighbors, it would wipe cross-region neighbors too.

**`get_region_full_details(session, region_id)`** (line 271):
- Returns: `map_items` (including arrows with `paired_arrow_id`, `target_region_id`), `neighbor_edges`, `arrow_edges`.
- Arrow map items include `paired_arrow_id` in the response (line 457).
- Arrow edges include `location_id`, `arrow_id`, `energy_cost`, `path_data`.
- Does NOT currently include any info about the paired arrow's ArrowNeighbors (what locations are connected on the other side).

**`get_client_location_details(session, location_id)`** (line 1278):
- Returns neighbor list by querying `LocationNeighbor.location_id == location_id`.
- Returns `id`, `name`, `recommended_level`, `image_url`, `energy_cost` for each neighbor.
- Cross-region neighbors will automatically appear here once LocationNeighbor rows are created.

#### 3. Frontend — Arrow Edge Highlighting (`RegionInteractiveMap.tsx`)

**Current `isActive` logic for arrow edges** (line 287, 401):
```typescript
const isActive = currentLocationId != null && edge.location_id === currentLocationId;
```
- Only highlights when the player's current location is the one directly connected to the arrow in THIS region.
- Does NOT highlight when the player is on a location in ANOTHER region connected via the paired arrow.

**What's needed**: When viewing region B's map, if the player is at location A in region 1, and A connects to arrow1, and arrow1's paired arrow is arrow2 in region B, then arrow2's edges should be highlighted.

**Data flow**: `WorldPage.tsx` passes `currentLocationId` (from `userCharacter.current_location.id`) to `RegionInteractiveMap`. The map currently has no way to know about cross-region connections because the API doesn't return paired arrow neighbor data.

#### 4. Frontend — Neighbor List on Location Page

`NeighborsSection.tsx` and `LocationPage.tsx` use `LocationData.neighbors` (type `NeighborLocation[]`). This data comes from `get_client_location_details()` which queries `LocationNeighbors` table. Once cross-region LocationNeighbor rows exist, they will automatically appear in this list with no frontend changes needed.

### Cross-Region Neighbor Sync Algorithm

When `create_arrow_neighbor(arrow_id=A1, location_id=locA)` is called:

1. Get arrow A1, find `paired_arrow_id` -> A2
2. If A2 is null, stop (no pair yet)
3. Query all ArrowNeighbors where `arrow_id = A2` -> list of `{location_id: locB, energy_cost: costB}`
4. For each locB: create LocationNeighbor(locA, locB) with `energy_cost = costA + costB`
5. Also check all OTHER ArrowNeighbors of A1 (besides the one just created) to create N*M cross-neighbors

When `delete_arrow_neighbor(arrow_id=A1, location_id=locA)` is called:

1. Get arrow A1, find `paired_arrow_id` -> A2
2. Query all ArrowNeighbors where `arrow_id = A2` -> list of locB's
3. Delete LocationNeighbor(locA, locB) for each locB (both directions)

When `delete_transition_arrow(arrow_id)` is called:

1. Before deleting arrows, find all ArrowNeighbors of both arrows
2. For each pair (locA from arrow1, locB from arrow2): delete LocationNeighbor(locA, locB)
3. Then proceed with existing deletion logic

### LocationNeighbor Model — No Schema Change Needed

The existing `LocationNeighbor` model has all needed fields: `location_id`, `neighbor_id`, `energy_cost`, `path_data`. No new columns required. Cross-region neighbors are just regular LocationNeighbor rows where the two locations happen to be in different regions.

However, **there's a distinction problem**: how to identify which LocationNeighbors were auto-created by the arrow system vs manually created by admin. This matters for:
- `update_location_neighbors()` which wipes all neighbors — should it preserve cross-region auto-created ones?
- Preventing admins from accidentally deleting cross-region neighbors via the neighbor editor.

**Option A**: Add a `source` column to LocationNeighbor (`manual` | `arrow_auto`) — requires migration.
**Option B**: Add a separate table `cross_region_neighbor_link` that tracks which LocationNeighbor rows were auto-created.
**Option C**: Don't track — just re-sync after `update_location_neighbors()` runs. Simpler but fragile.

**Recommendation**: Option A is cleanest. A nullable `source` column (default `manual`) with an Alembic migration. Existing rows get `manual`, auto-created get `arrow_auto`. The `update_location_neighbors()` function can then skip/preserve `arrow_auto` rows.

### API Response Enhancement for Frontend Highlighting

`GET /regions/{id}/details` needs to return additional data so the frontend can determine cross-region highlighting. Two approaches:

**Approach 1 — Return paired arrow neighbors in arrow_edges**:
Add a field to each arrow map item: `paired_arrow_neighbors: [{location_id, energy_cost}]` — the locations connected to the paired arrow in the other region. The frontend can then check: "is my currentLocationId in any arrow's `paired_arrow_neighbors`? If yes, highlight that arrow's edges."

**Approach 2 — Return a `cross_region_active_arrows` list**:
A separate field in the response: `cross_region_active_arrows: [arrow_id, ...]` computed server-side given a `current_location_id` query param. Cleaner for the frontend but requires passing the player's location to the region details endpoint.

**Recommendation**: Approach 1 is simpler and doesn't require auth/state in the region details endpoint. The data is small (just location IDs per arrow) and can be cached.

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| `update_location_neighbors()` wipes cross-region auto-neighbors | Admin editing regular neighbors destroys arrow-based connections | Add `source` column; skip `arrow_auto` rows in bulk update |
| N*M explosion if many locations connect to one arrow | Many LocationNeighbor rows created | Document that arrows should typically connect 1-2 locations each |
| Energy cost stale if ArrowNeighbor energy_cost changes | Cross-region neighbor has wrong energy_cost | Re-sync on `create_arrow_neighbor` (it's an upsert) — recalculate all affected LocationNeighbors |
| `delete_transition_arrow` cascade-deletes ArrowNeighbors before we can read them | Can't find which cross-region neighbors to clean up | Read ArrowNeighbors BEFORE deleting arrows, then clean up LocationNeighbors |
| No path_data for cross-region LocationNeighbor | Neighbor edge won't render on map (but it's cross-region so it shouldn't) | Set `path_data = null` for cross-region neighbors — they're not on any single region map |

### Summary of Changes Needed

**Backend (locations-service/app/crud.py)**:
1. Add helper function `sync_cross_region_neighbors(session, arrow_id)` that recalculates all cross-region LocationNeighbors for a given arrow pair.
2. Call it at end of `create_arrow_neighbor()`.
3. Add cleanup logic at start of `delete_arrow_neighbor()` (before deleting the ArrowNeighbor row).
4. Add cleanup logic at start of `delete_transition_arrow()` (before deleting arrows).
5. Modify `update_location_neighbors()` to preserve `arrow_auto` neighbors (if source column is added).

**Backend (locations-service/app/models.py)**:
1. (If Option A chosen) Add `source` column to `LocationNeighbor`.

**Backend (locations-service/app/crud.py — get_region_full_details)**:
1. For each arrow, query its paired arrow's ArrowNeighbors and include as `paired_arrow_neighbors` in the arrow map item.

**Frontend (RegionInteractiveMap.tsx)**:
1. Extend `MapItem` interface to include `paired_arrow_neighbors?: {location_id: number}[]`.
2. Update `isActive` logic for arrow edges: also active if `currentLocationId` is in the arrow's `paired_arrow_neighbors`.

**Alembic**:
1. (If Option A chosen) Migration to add `source` column to `LocationNeighbors` table.

**No changes needed**:
- Location page / NeighborsSection — will automatically show cross-region neighbors once LocationNeighbor rows exist.
- Travel/movement logic — uses LocationNeighbor rows, will work automatically.

---

## 3. Architecture Decision (filled by Architect — in English)

### Overview

This feature auto-creates bidirectional `LocationNeighbor` rows when both sides of paired transition arrows have `ArrowNeighbor` connections to locations. No new endpoints needed — we extend existing CRUD functions and the region details API response.

### 3.1 DB Schema Change

**Add `is_auto_arrow` column to `LocationNeighbors` table:**

```sql
ALTER TABLE LocationNeighbors ADD COLUMN is_auto_arrow TINYINT(1) NOT NULL DEFAULT 0;
```

- Type: `Boolean` (MySQL `TINYINT(1)`), NOT NULL, default `False`
- Purpose: Distinguish auto-created cross-region neighbors from manually created ones
- Existing rows keep `is_auto_arrow=False` (manual neighbors)
- Auto-created cross-region neighbors get `is_auto_arrow=True`

**Model change** (`services/locations-service/app/models.py`):
```python
class LocationNeighbor(Base):
    # ... existing columns ...
    is_auto_arrow = Column(Boolean, nullable=False, default=False, server_default="0")
```

**Alembic migration 024** (`app/alembic/versions/024_add_is_auto_arrow_to_location_neighbors.py`):
- Revision: `024_add_is_auto_arrow_to_location_neighbors`
- Down revision: `023_add_region_transition_arrows`
- Adds `is_auto_arrow` column with server_default=`0`
- Rollback: drop the column

### 3.2 Backend CRUD Changes

All changes in `services/locations-service/app/crud.py`.

#### 3.2.1 New helper: `sync_cross_region_neighbors(session, arrow_id)`

Core sync function that recalculates ALL cross-region LocationNeighbors for a given arrow pair.

**Algorithm:**
1. Load the arrow, get `paired_arrow_id`. If no pair, return.
2. Query all ArrowNeighbors of this arrow -> `local_ans` (list of `{location_id, energy_cost}`)
3. Query all ArrowNeighbors of the paired arrow -> `remote_ans`
4. If either list is empty, return (no cross-region neighbors possible).
5. Delete all existing `is_auto_arrow=True` LocationNeighbors where `location_id` in local_location_ids AND `neighbor_id` in remote_location_ids (or vice versa). This is a clean-slate approach for this arrow pair.
6. For each `(locA, costA)` in `local_ans` x `(locB, costB)` in `remote_ans`:
   - Create LocationNeighbor(location_id=locA, neighbor_id=locB, energy_cost=costA+costB, path_data=null, is_auto_arrow=True)
   - Create LocationNeighbor(location_id=locB, neighbor_id=locA, energy_cost=costA+costB, path_data=null, is_auto_arrow=True)
7. Flush (caller commits).

**Why not reuse `add_neighbor()`**: `add_neighbor()` does bidirectional upsert with path_data serialization and commits. Our helper needs batch creation without intermediate commits, and the `is_auto_arrow=True` flag. Direct creation of LocationNeighbor rows is cleaner.

#### 3.2.2 New helper: `cleanup_cross_region_neighbors_for_arrow(session, arrow_id)`

Deletes all auto-arrow LocationNeighbors linked to a specific arrow pair. Used before deletion operations.

**Algorithm:**
1. Load arrow, get `paired_arrow_id`. If no pair, return.
2. Get location_ids from ArrowNeighbors of this arrow -> `local_ids`
3. Get location_ids from ArrowNeighbors of paired arrow -> `remote_ids`
4. Delete LocationNeighbor rows where `is_auto_arrow=True` AND ((location_id in local_ids AND neighbor_id in remote_ids) OR (location_id in remote_ids AND neighbor_id in local_ids))
5. Flush.

#### 3.2.3 Extend `create_arrow_neighbor()`

After creating/upserting the ArrowNeighbor row (and before the final commit), call:
```python
await sync_cross_region_neighbors(session, arrow_id)
```

This handles all cases: first connection, updating energy_cost, N*M expansion.

#### 3.2.4 Extend `delete_arrow_neighbor()`

Before deleting the ArrowNeighbor row, cleanup cross-region neighbors for the specific location being disconnected:
1. Get arrow's `paired_arrow_id`. If no pair, skip.
2. Query ArrowNeighbors of paired arrow -> `remote_ids`
3. Delete LocationNeighbor rows where `is_auto_arrow=True` AND ((location_id=locA AND neighbor_id in remote_ids) OR (location_id in remote_ids AND neighbor_id=locA))
4. Then proceed with existing delete logic.

Note: We don't call the full `sync_cross_region_neighbors` here because we need to delete only neighbors for the specific location being disconnected, not re-sync everything. The ArrowNeighbor row still exists at query time so `sync` would re-create what we're trying to delete.

#### 3.2.5 Extend `delete_transition_arrow()`

Before nullifying paired_arrow_id and deleting arrows (which cascade-deletes ArrowNeighbors):
1. Call `cleanup_cross_region_neighbors_for_arrow(session, arrow_id)` — reads ArrowNeighbors while they still exist.
2. Then proceed with existing deletion logic.

#### 3.2.6 Modify `update_location_neighbors()`

Change the delete step to preserve auto-arrow neighbors:
```python
# OLD: delete ALL neighbors
await db.execute(
    delete(LocationNeighbor).where(
        (LocationNeighbor.location_id == location_id)
        | (LocationNeighbor.neighbor_id == location_id)
    )
)

# NEW: delete only manual neighbors
await db.execute(
    delete(LocationNeighbor).where(
        ((LocationNeighbor.location_id == location_id)
         | (LocationNeighbor.neighbor_id == location_id))
        & (LocationNeighbor.is_auto_arrow == False)
    )
)
```

### 3.3 API Response Enhancement

**In `get_region_full_details()`**, extend each arrow's map_item to include `paired_location_ids`:

After querying arrow_edges, for each arrow that has a `paired_arrow_id`:
1. Query ArrowNeighbors of the paired arrow.
2. Add `paired_location_ids: [loc_id_1, loc_id_2, ...]` to the arrow's map_item dict.

This is a small additional query (all paired arrow IDs are known). Batch it: collect all paired_arrow_ids, query all ArrowNeighbors for those IDs in one query, group by arrow_id.

**Response shape change** (arrow map_items only):
```json
{
  "id": 5,
  "name": "-> Region 2",
  "type": "arrow",
  "paired_arrow_id": 6,
  "target_region_id": 2,
  "paired_location_ids": [101, 102]  // NEW — locations connected to the paired arrow
}
```

No schema change needed — the response is a raw dict, not a Pydantic model.

### 3.4 Frontend Highlighting Logic

**File: `RegionInteractiveMap.tsx`**

1. Extend `MapItem` interface:
```typescript
interface MapItem {
  // ... existing fields ...
  paired_location_ids?: number[];  // NEW
}
```

2. Extend `ArrowEdge` interface:
```typescript
interface ArrowEdge {
  location_id: number;
  arrow_id: number;
  energy_cost?: number;
  path_data?: PathWaypoint[] | null;
  paired_location_ids?: number[];  // NEW — inherited from parent arrow's map_item
}
```

Actually, simpler approach: the `paired_location_ids` lives on the arrow map_item, not on the arrow_edge. The arrow_edge has `arrow_id` which maps to a map_item. So:

3. Build a lookup map: `arrowPairedLocations: Map<number, number[]>` from map_items where `type === "arrow"` and `paired_location_ids` exists.

4. Update `isActive` logic for arrow edges (lines 287 and 401):
```typescript
// OLD:
const isActive = currentLocationId != null && edge.location_id === currentLocationId;

// NEW:
const pairedLocIds = arrowPairedLocations.get(edge.arrow_id) || [];
const isActive = currentLocationId != null && (
  edge.location_id === currentLocationId ||
  pairedLocIds.includes(currentLocationId)
);
```

This means: "highlight this arrow edge if the player is at the location directly connected to this arrow, OR if the player is at a location connected to the paired arrow on the other side."

### 3.5 Data Flow Diagram

```
Admin creates ArrowNeighbor (locA -> arrow1):
  create_arrow_neighbor(arrow1, locA)
    -> upsert ArrowNeighbor row
    -> sync_cross_region_neighbors(arrow1)
       -> find paired arrow2
       -> query ArrowNeighbors of arrow2 -> [locB, locC]
       -> create LocationNeighbor(locA, locB, costA+costB, is_auto_arrow=True)
       -> create LocationNeighbor(locA, locC, costA+costC, is_auto_arrow=True)
    -> commit

Player views region 2 map:
  get_region_full_details(region2)
    -> returns arrow map_items with paired_location_ids: [locA]
    -> frontend: isActive for arrow2's edges = currentLocationId in [locA]
    -> arrow2->locB edge is highlighted (player is at locA, connected via arrow pair)

Player at locA sees neighbors:
  get_client_location_details(locA)
    -> queries LocationNeighbors where location_id = locA
    -> returns locB, locC (cross-region) + any manual neighbors
    -> no code change needed
```

### 3.6 Security Considerations

- No new endpoints — no new auth/rate-limiting concerns.
- `create_arrow_neighbor`, `delete_arrow_neighbor`, `delete_transition_arrow` are already admin-only endpoints (behind `get_admin_user` dependency).
- `update_location_neighbors` is already admin-only.
- `get_region_full_details` is public (no auth) — the new `paired_location_ids` field is non-sensitive (just location IDs).
- No input validation changes needed — all inputs go through existing validated endpoints.

### 3.7 Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `update_location_neighbors()` deletes auto-arrow neighbors | Filter by `is_auto_arrow=False` in delete clause |
| N*M explosion with many ArrowNeighbors per arrow | Documented limitation; typical use is 1-2 locations per arrow |
| Energy cost becomes stale if ArrowNeighbor cost is updated | `create_arrow_neighbor` is an upsert — `sync_cross_region_neighbors` recalculates all affected pairs |
| `delete_transition_arrow` cascade-deletes ArrowNeighbors before we read them | Call `cleanup_cross_region_neighbors_for_arrow` BEFORE arrow deletion |
| `path_data=null` for cross-region neighbors | These neighbors span two regions — they don't render as edges on any single map. `path_data=null` is correct. |

### 3.8 Rollback Plan

1. Revert code changes (CRUD functions return to original behavior).
2. Run Alembic downgrade to drop `is_auto_arrow` column.
3. Any auto-created LocationNeighbor rows with `is_auto_arrow=True` will lose their flag but remain as regular neighbors. To fully clean up, run: `DELETE FROM LocationNeighbors WHERE is_auto_arrow = 1` before downgrade.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Alembic migration + model change

| Field | Value |
|-------|-------|
| **#** | 1 |
| **Description** | Add `is_auto_arrow` Boolean column to `LocationNeighbor` model and create Alembic migration 024. Column: `is_auto_arrow`, Boolean, NOT NULL, default=False, server_default="0". |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/locations-service/app/models.py`, `services/locations-service/app/alembic/versions/024_add_is_auto_arrow_to_location_neighbors.py` |
| **Depends On** | — |
| **Acceptance Criteria** | (1) `LocationNeighbor` model has `is_auto_arrow` column. (2) Migration 024 exists with down_revision=023, adds the column with server_default. (3) Downgrade drops the column. (4) `python -m py_compile` passes on both files. |

### Task 2: Backend CRUD — cross-region neighbor sync logic

| Field | Value |
|-------|-------|
| **#** | 2 |
| **Description** | Implement cross-region neighbor auto-sync in `crud.py`: (1) Add `sync_cross_region_neighbors(session, arrow_id)` helper that creates bidirectional `is_auto_arrow=True` LocationNeighbor rows for all location pairs across paired arrows, with energy_cost = sum of both ArrowNeighbor costs. (2) Add `cleanup_cross_region_neighbors_for_arrow(session, arrow_id)` helper that deletes all auto-arrow LocationNeighbors for an arrow pair. (3) Call sync at end of `create_arrow_neighbor()` before commit. (4) Add cleanup in `delete_arrow_neighbor()` before deleting the row — only for the specific location being disconnected. (5) Add cleanup in `delete_transition_arrow()` before arrow deletion. (6) Modify `update_location_neighbors()` delete clause to filter by `is_auto_arrow == False`. See section 3.2 for detailed algorithms. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/locations-service/app/crud.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | (1) Creating ArrowNeighbors on both sides of a paired arrow creates LocationNeighbor rows with `is_auto_arrow=True` and correct summed energy_cost. (2) Deleting an ArrowNeighbor removes only the affected cross-region neighbors. (3) Deleting a transition arrow cleans up all related cross-region neighbors. (4) `update_location_neighbors()` preserves auto-arrow neighbors. (5) `python -m py_compile` passes. |

### Task 3: Backend API — paired_location_ids in region details

| Field | Value |
|-------|-------|
| **#** | 3 |
| **Description** | In `get_region_full_details()`, extend arrow map_items to include `paired_location_ids`. After building arrow map_items, collect all `paired_arrow_id` values, batch-query ArrowNeighbors for those IDs, and add `paired_location_ids: [loc_id, ...]` to each arrow's map_item dict. This enables the frontend to know which locations on the other side of a paired arrow are connected. |
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/locations-service/app/crud.py` |
| **Depends On** | 1 |
| **Acceptance Criteria** | (1) Arrow map_items in the response include `paired_location_ids` list. (2) If no paired arrow or no ArrowNeighbors on the other side, `paired_location_ids` is an empty list. (3) `python -m py_compile` passes. |

### Task 4: Frontend — arrow edge cross-region highlighting

| Field | Value |
|-------|-------|
| **#** | 4 |
| **Description** | In `RegionInteractiveMap.tsx`: (1) Add `paired_location_ids?: number[]` to `MapItem` interface. (2) Build a lookup `Map<number, number[]>` from arrow map_items (`arrow_id -> paired_location_ids`). (3) Update all `isActive` checks for arrow edges (lines ~287 and ~401): also active if `currentLocationId` is in the arrow's `paired_location_ids`. This highlights the path from arrow to location when the player is on a connected location in the other region. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/components/WorldPage/RegionInteractiveMap/RegionInteractiveMap.tsx`, `services/frontend/app-chaldea/src/redux/slices/worldMapSlice.ts`, `services/frontend/app-chaldea/src/redux/actions/worldMapActions.ts` |
| **Depends On** | 3 |
| **Acceptance Criteria** | (1) When player is at locA (region 1) connected to arrow1, and views region 2 map, arrow2's edges to locB are highlighted. (2) Existing same-region highlighting still works. (3) `npx tsc --noEmit` and `npm run build` pass. |

### Task 5: QA — backend tests for cross-region neighbor sync

| Field | Value |
|-------|-------|
| **#** | 5 |
| **Description** | Write pytest tests for cross-region neighbor sync logic: (1) Test `create_arrow_neighbor` on both sides creates LocationNeighbor with `is_auto_arrow=True` and correct energy_cost. (2) Test creating ArrowNeighbor on one side only does NOT create LocationNeighbor. (3) Test N*M: multiple locations per arrow create correct number of cross-region neighbors. (4) Test `delete_arrow_neighbor` removes only affected cross-region neighbors. (5) Test `delete_transition_arrow` cleans up all cross-region neighbors. (6) Test `update_location_neighbors` preserves auto-arrow neighbors. (7) Test `get_region_full_details` returns `paired_location_ids` in arrow map_items. |
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | `services/locations-service/app/tests/test_cross_region_neighbors.py` |
| **Depends On** | 2, 3 |
| **Acceptance Criteria** | All tests pass with `pytest`. Tests cover all 7 scenarios listed above. |

### Task 6: Review

| Field | Value |
|-------|-------|
| **#** | 6 |
| **Description** | Final review of all changes: code quality, cross-service contract integrity, migration correctness, frontend build verification, live verification. |
| **Agent** | Reviewer |
| **Status** | TODO |
| **Files** | All files from tasks 1-5 |
| **Depends On** | 1, 2, 3, 4, 5 |
| **Acceptance Criteria** | (1) All `python -m py_compile` checks pass. (2) `npx tsc --noEmit` and `npm run build` pass. (3) No regressions in existing neighbor/arrow functionality. (4) Live verification: create paired arrows with ArrowNeighbors, verify cross-region LocationNeighbors appear, verify map highlighting, verify cleanup on deletion. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-28
**Result:** FAIL

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/locations-service/app/alembic/versions/024_add_is_auto_arrow_to_location_neighbors.py:13` | **BLOCKING**: Migration revision ID `024_add_is_auto_arrow_to_location_neighbors` is 43 characters, but `alembic_version_locations.version_num` column is `varchar(32)`. Migration fails at runtime with `DataError: (1406, "Data too long for column 'version_num'")`. All other migrations use <=32 char revision IDs (e.g., `023_add_region_transition_arrows` = 32 chars). **Fix**: Shorten revision ID to <=32 chars, e.g., `024_add_is_auto_arrow` (21 chars). Also rename the file accordingly. | Backend Developer | FIX_REQUIRED |

#### Code Review Summary

**Backend logic — PASS (contingent on migration fix):**
- `sync_cross_region_neighbors()`: Correctly implements clean-slate + N*M bidirectional creation. Properly handles early returns (no pair, no local/remote ArrowNeighbors). Energy cost summation is correct.
- `cleanup_cross_region_neighbors_for_arrow()`: Correct — reads ArrowNeighbors before deletion, filters by `is_auto_arrow=True`, handles both directions.
- `create_arrow_neighbor()`: Calls `sync_cross_region_neighbors` after both upsert and insert paths — correct.
- `delete_arrow_neighbor()`: Inline cleanup targets only the specific `location_id` being disconnected, not full pair — correct per spec.
- `delete_transition_arrow()`: Calls `cleanup_cross_region_neighbors_for_arrow` before arrow deletion — correct (ArrowNeighbors still readable at that point).
- `update_location_neighbors()`: Delete clause correctly filters `is_auto_arrow == False` — preserves auto-arrow neighbors.
- `get_region_full_details()`: Batch query for `paired_location_ids` is efficient (single query for all paired arrow IDs). Response shape is correct.
- Model `LocationNeighbor.is_auto_arrow`: Correct definition with `server_default="0"`.

**Frontend — PASS:**
- `MapItem` interface correctly adds `paired_location_ids?: number[]` (optional).
- `arrowPairedLocations` lookup `Map<number, number[]>` built correctly from arrow map_items.
- `isActive` logic for arrow edges correctly checks both `edge.location_id === currentLocationId` (same region) AND `pairedLocIds.includes(currentLocationId)` (cross-region). Applied consistently in both motion path and visual rendering sections.
- `RegionMapItem` in `worldMapSlice.ts` and `fetchRegionDetails` return type in `worldMapActions.ts` both include `paired_location_ids?: number[]` — types are consistent.
- No `React.FC` usage, no new SCSS, all Tailwind.
- No new `.jsx` files created.

**Tests — PASS:**
- 24 tests covering all 7 scenarios from spec: auto-creation, N*M pairs, ArrowNeighbor deletion, arrow deletion, update_location_neighbors preservation, API paired_location_ids, and unit tests for sync/cleanup helpers.
- Unit tests for `sync_cross_region_neighbors` verify bidirectional creation with correct energy costs and N*M expansion.
- Unit tests for `cleanup_cross_region_neighbors_for_arrow` verify early returns for missing arrow/pair/empty IDs.

**Security — PASS:**
- No new endpoints. All affected functions are behind existing admin auth.
- `paired_location_ids` in public API is non-sensitive data (just location IDs).

**Alembic migration — FAIL (see issue #1):**
- Migration logic itself is correct (idempotent with `inspect` check, proper downgrade).
- But revision ID exceeds `varchar(32)` column limit — migration cannot be applied.

#### Automated Check Results
- [ ] `npx tsc --noEmit` — PASS (no errors in FEAT-100 files; pre-existing errors in BattlePage, SkillsTab, etc. are unrelated)
- [ ] `npm run build` — PASS (built in 20.19s)
- [x] `py_compile` — PASS (models.py, crud.py, migration file all pass)
- [x] `pytest` — PASS (24/24 tests pass)
- [ ] `docker-compose config` — N/A (no compose changes)
- [ ] Live verification — FAIL (500 on `/locations/regions/10/details` due to migration not applied — `is_auto_arrow` column missing from DB)

#### Live Verification Results
- Endpoint tested: `GET /locations/regions/10/details`
- Result: HTTP 500 — `OperationalError: (1054, "Unknown column 'LocationNeighbors.is_auto_arrow' in 'field list'")`
- Root cause: Migration 024 failed to apply because revision ID (43 chars) exceeds `alembic_version_locations.version_num` varchar(32) limit
- After migration fix and successful application, the endpoint should work correctly (code logic is sound)

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-28 — PM: фича создана (FEAT-100), запускаю анализ
[LOG] 2026-03-28 — Analyst: анализ завершён, затронуто 2 сервиса (locations-service, frontend). Изучены: модели LocationNeighbor/ArrowNeighbor/RegionTransitionArrow, CRUD-функции create/delete_arrow_neighbor и delete_transition_arrow, get_region_full_details, get_client_location_details, фронтенд RegionInteractiveMap.tsx (логика isActive для arrow edges), NeighborsSection.tsx. Ключевые находки: (1) нужна sync-функция для авто-создания LocationNeighbor при связке обеих сторон парных стрелок, (2) update_location_neighbors() затирает ВСЕ соседей — нужен механизм защиты авто-созданных, (3) API regions/details нужно расширить данными о paired_arrow_neighbors для подсветки на фронте, (4) NeighborsSection автоматически покажет кросс-региональных соседей без изменений.
[LOG] 2026-03-28 — Architect: спроектировано 6 задач (3 backend, 1 frontend, 1 QA, 1 review). Архитектура: добавление is_auto_arrow колонки в LocationNeighbors (миграция 024), sync/cleanup хелперы в crud.py, расширение get_region_full_details paired_location_ids, подсветка на фронте через lookup map. Минимальный дифф — нет новых эндпоинтов, нет новых таблиц.
[LOG] 2026-03-28 — Backend Dev: задача #1 завершена — добавлена колонка is_auto_arrow в модель LocationNeighbor и создана Alembic-миграция 024. py_compile пройден.
[LOG] 2026-03-28 — Backend Dev: задача #2 завершена — реализованы sync_cross_region_neighbors() и cleanup_cross_region_neighbors_for_arrow() хелперы; интегрированы в create_arrow_neighbor, delete_arrow_neighbor, delete_transition_arrow; update_location_neighbors сохраняет auto-arrow записи. py_compile пройден.
[LOG] 2026-03-28 — Backend Dev: задача #3 завершена — get_region_full_details() возвращает paired_location_ids в arrow map_items через batch-запрос ArrowNeighbors парных стрелок. py_compile пройден.
[LOG] 2026-03-28 — Frontend Dev: задача #4 завершена — добавлен paired_location_ids в MapItem/RegionMapItem интерфейсы и fetchRegionDetails тип; построен lookup arrowPairedLocations; обновлена логика isActive для arrow edges (motion paths + visual rendering) — подсветка работает и для кросс-региональных связей. Node.js недоступен в текущем окружении — tsc/build верификация не выполнена (требуется проверка на CI или в Docker).
[LOG] 2026-03-28 — QA: задача #5 завершена — написаны 24 теста для cross-region neighbor sync логики. Покрыто: (a) авто-создание кросс-региональных соседей при ArrowNeighbor на обеих сторонах, (b) N×M пары, (c) удаление при delete ArrowNeighbor, (d) удаление при delete arrow, (e) update_location_neighbors сохраняет auto-arrow, (f) paired_location_ids в API ответе, (g) unit-тесты sync/cleanup хелперов. Все 24 теста проходят, py_compile пройден.
[LOG] 2026-03-28 — Reviewer: начал проверку FEAT-100. Проверены все изменённые файлы (модель, миграция, CRUD, API, фронтенд, тесты).
[LOG] 2026-03-28 — Reviewer: проверка завершена, результат FAIL. Блокирующая проблема: revision ID миграции 024 (43 символа) превышает лимит varchar(32) колонки alembic_version_locations.version_num. Миграция не применяется, сервис падает с 500 на endpoint regions/details. Бэкенд-логика и фронтенд корректны. Требуется укоротить revision ID.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
