# FEAT-049: Исправление багов экипировки — статы не добавляются/не снимаются корректно

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-19 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Баги в системе экипировки:
1. При одевании предметов характеристики не добавляются или добавляются не все
2. При снятии предметов некоторые статы остаются (не снимаются полностью)
3. Показатель "Урон" должен рассчитываться как: основной атрибут класса + урон основного оружия

### Бизнес-правила
- При экипировке предмета ВСЕ его модификаторы должны применяться к характеристикам персонажа
- При снятии предмета ВСЕ его модификаторы должны полностью сниматься
- Урон = основной атрибут класса + урон основного оружия
- Никаких "остаточных" статов после снятия предмета

### Edge Cases
- Что если предмет заменяется на другой в том же слоте? Старые статы снимаются, новые добавляются
- Что если предмет не имеет модификаторов? Ничего не должно меняться

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| inventory-service | Bug fix in `build_modifiers_dict` (falsy-zero check) | `app/crud.py` |
| character-attributes-service | No bugs found in `apply_modifiers` — logic is correct | `app/main.py` |
| character-service | Read-only (class definitions) | `app/models.py`, `app/presets.py` |
| frontend | Bug: attributes not re-fetched after equip/unequip; damage calculation missing | `src/redux/slices/profileSlice.ts`, `src/components/ProfilePage/StatsTab/DerivedStatsSection.tsx` |

### Existing Patterns

- **inventory-service**: sync SQLAlchemy, Pydantic <2.0, Alembic present
- **character-attributes-service**: sync SQLAlchemy, Pydantic <2.0, Alembic present
- **character-service**: sync SQLAlchemy, Pydantic <2.0, Alembic present
- **frontend**: React 18 + Redux Toolkit + TypeScript (migrated), Tailwind CSS

### Cross-Service Dependencies

- inventory-service → character-attributes-service `POST /attributes/{character_id}/apply_modifiers` (equip/unequip)
- frontend → inventory-service `POST /inventory/{characterId}/equip` and `POST /inventory/{characterId}/unequip`
- frontend → character-attributes-service `GET /attributes/{characterId}` (fetch stats)
- battle-service → character-attributes-service (reads `damage` attribute for combat)

### DB Changes

- No DB schema changes required. All bugs are in application logic and frontend state management.

### Bugs Found

#### BUG 1 (CRITICAL): `build_modifiers_dict` uses truthy check, skipping zero-value modifiers that were previously set

**File:** `services/inventory-service/app/crud.py`, lines 190-274 (function `build_modifiers_dict`)

The function uses `if item_obj.strength_modifier:` pattern for every modifier field. In Python, `if 0:` evaluates to `False`. Since the Items model defines all modifier columns with `default=0`, every modifier that has value `0` will be skipped (correct — no modifier to apply). However, this is NOT the root cause of the reported bug because items with `0` modifiers correctly should not be included.

**ACTUALLY — re-analysis:** The `if item_obj.X_modifier:` check is actually correct for the equip flow. When a modifier is `0`, it means "no bonus from this item for this stat," so it's correct to skip it. The real issue is elsewhere.

#### BUG 2 (CRITICAL): Frontend does NOT re-fetch attributes after equip/unequip

**File:** `services/frontend/app-chaldea/src/redux/slices/profileSlice.ts`

In the `equipItem` thunk (lines 327-344), after a successful equip, the code re-fetches:
- `fetchInventory(characterId)` ✅
- `fetchEquipment(characterId)` ✅
- `fetchFastSlots(characterId)` ✅
- **`fetchAttributes(characterId)` ❌ MISSING**

In the `unequipItem` thunk (lines 346-370), same issue:
- `fetchInventory(characterId)` ✅
- `fetchEquipment(characterId)` ✅
- `fetchFastSlots(characterId)` ✅
- **`fetchAttributes(characterId)` ❌ MISSING**

**Impact:** Even though the backend correctly applies/removes modifiers via the `apply_modifiers` endpoint, the frontend never re-fetches the updated attributes. The UI shows stale stat values until the user navigates away and comes back (triggering `loadProfileData` which does fetch attributes).

This is the PRIMARY cause of "stats not applied" — they ARE applied on the backend, but the frontend does not refresh the display.

#### BUG 3 (HIGH): Damage calculation is not implemented

**Requirement:** Damage = main class attribute + main weapon damage modifier

**Current state:**
- `character_attributes.damage` is stored as `Column(Integer, default=0)` — it starts at 0 and is only modified by item `damage_modifier` via `apply_modifiers`.
- There is NO logic anywhere that calculates damage based on class + main attribute.
- The `classes` table has `id_class` (1=Воин, 2=Плут, 3=Маг) but there is NO mapping from class to "main attribute" (e.g., Warrior→strength, Rogue→agility, Mage→intelligence).
- The battle-service (`battle_engine.py` line 66) reads `attacker_attr["damage"]` as the base and adds `weapon["damage_modifier"]` — so it relies on the `damage` attribute already containing the correct base value.

**What needs to be defined:**
1. A class-to-main-attribute mapping (e.g., class 1 → strength, class 2 → agility, class 3 → intelligence)
2. Where to calculate: the damage should be recalculated whenever equipment changes or stats are upgraded. Options:
   - **Backend (recommended):** In `apply_modifiers` or a separate endpoint, recalculate `damage = main_class_attribute_value + weapon_damage_modifier`
   - **Frontend:** Calculate on display only (not persisted — battle-service would use wrong value)

**Note:** The battle-service already adds `weapon.damage_modifier` on top of `attr.damage` (line 67-68, 131), so if we store `damage = main_attribute_value` in DB, the weapon bonus would be double-counted in battle. The design needs clarification from the user/architect.

#### BUG 4 (LOW): Inconsistency — `ItemData` TypeScript interface missing resistance/vulnerability modifiers

**File:** `services/frontend/app-chaldea/src/redux/slices/profileSlice.ts`, lines 8-41

The `ItemData` interface includes basic modifiers (strength, agility, etc.) but does NOT include:
- `res_effects_modifier`, `res_physical_modifier`, `res_catting_modifier`, etc.
- `vul_effects_modifier`, `vul_physical_modifier`, etc.
- `critical_hit_chance_modifier`, `critical_damage_modifier`

This means the frontend `ItemData` type doesn't match the full backend schema. However, this is a **display-only issue** — the backend handles modifier application regardless of what the frontend knows about the item's fields.

### Backend equip/unequip flow analysis (NO bugs found in backend logic)

**Equip flow** (`services/inventory-service/app/main.py`, lines 218-309):
1. Validates item exists and is in inventory ✅
2. Finds appropriate equipment slot ✅
3. If slot occupied: returns old item to inventory, sends negative modifiers for old item ✅
4. Removes item from inventory, places in slot ✅
5. Sends positive modifiers for new item via `apply_modifiers_in_attributes_service` ✅
6. Commits transaction, then recalculates fast slots ✅

**Unequip flow** (`services/inventory-service/app/main.py`, lines 315-371):
1. Finds slot and validates item exists ✅
2. Returns item to inventory ✅
3. Sends negative modifiers via `apply_modifiers_in_attributes_service` ✅
4. Clears slot ✅
5. Commits, recalculates fast slots ✅

**`build_modifiers_dict`** (`services/inventory-service/app/crud.py`, lines 178-278):
- Covers ALL modifier fields from the Items model ✅
- Correctly negates values when `negative=True` ✅
- Uses `if item_obj.X_modifier:` which skips `0` and `None` values — correct behavior (no modifier to apply) ✅

**`apply_modifiers` endpoint** (`services/character-attributes-service/app/main.py`, lines 293-446):
- Handles health/mana/energy/stamina with multiplier logic ✅
- Handles all simple stats via loop over `simple_keys` list ✅
- `simple_keys` list covers all resistance and vulnerability fields ✅
- Field names match between `build_modifiers_dict` keys and `CharacterAttributes` model columns ✅

**Field name consistency check:**
- inventory-service sends: `"res_catting"`, `"res_watering"`, `"res_sainting"` (from `build_modifiers_dict`)
- character-attributes-service model has: `res_catting`, `res_watering`, `res_sainting` (column names)
- character-attributes-service `simple_keys` includes: `"res_catting"`, `"res_watering"`, `"res_sainting"` ✅
- **All field names are CONSISTENT** between services. The typos (catting/watering/sainting) are consistent everywhere, so they don't cause bugs — they're just misspelled consistently (tracked in ISSUES.md #13).

### Risks

- **Risk:** Damage calculation design needs user/architect input — where to calculate and how to avoid double-counting with battle-service. → **Mitigation:** Architect must define the formula and decide backend vs frontend calculation.
- **Risk:** Adding `fetchAttributes` to equip/unequip thunks adds an extra HTTP call per action. → **Mitigation:** Minimal performance impact — one additional GET request.
- **Risk:** The `delete_all_inventory` admin endpoint (line 576-592) explicitly states it does NOT reverse attribute modifiers from equipped items. This means admin bulk-delete corrupts character stats. → **Mitigation:** Out of scope for this feature but should be tracked.

---

## 3. Architecture Decision (filled by Architect — in English)

### Overview

This is a **frontend-only fix**. The backend equip/unequip logic is confirmed correct by the analysis report. Two issues need fixing:

1. **BUG 1 (Critical):** `equipItem` and `unequipItem` thunks do not dispatch `fetchAttributes()` after success, so the UI shows stale attribute values.
2. **BUG 2 (Feature):** Damage display should show `main class attribute value + main weapon damage_modifier` as a **visual-only frontend calculation** (not persisted to DB).

### API Contracts

No new or modified API endpoints. Existing endpoints used:
- `GET /attributes/{characterId}` — already exists, will be called after equip/unequip (same as `useItem` thunk already does)

### Security Considerations

No security changes. No new endpoints. No new data exposure.

### DB Changes

None.

### Frontend Changes

#### Fix 1: Add `fetchAttributes` to equip/unequip thunks

**File:** `src/redux/slices/profileSlice.ts`

In both `equipItem` and `unequipItem` thunks, add `thunkAPI.dispatch(fetchAttributes(characterId))` to the `Promise.all` array, matching the existing pattern in `useItem` thunk (line 389).

**Before (equipItem):**
```ts
await Promise.all([
  thunkAPI.dispatch(fetchInventory(characterId)),
  thunkAPI.dispatch(fetchEquipment(characterId)),
  thunkAPI.dispatch(fetchFastSlots(characterId)),
]);
```

**After (equipItem):**
```ts
await Promise.all([
  thunkAPI.dispatch(fetchInventory(characterId)),
  thunkAPI.dispatch(fetchEquipment(characterId)),
  thunkAPI.dispatch(fetchFastSlots(characterId)),
  thunkAPI.dispatch(fetchAttributes(characterId)),
]);
```

Same change for `unequipItem`.

#### Fix 2: Frontend damage calculation display

**Approach:** Visual-only calculation on the frontend. The `damage` value from `CharacterAttributes` (which equals `0 + sum of all equipped items' damage_modifiers`) will be **replaced** in the display with a calculated value:

```
displayDamage = mainClassAttributeValue + equippedMainWeaponDamageModifier
```

**Why frontend-only (not backend):**
- The user explicitly requested "visual only, do not write to DB"
- The battle-service already has its own damage calculation in `battle_engine.py` that reads `attr.damage` + `weapon.damage_modifier` — changing the DB value would require refactoring battle logic
- Keeping it frontend-only avoids cross-service impact

**Class-to-attribute mapping constant:**

**File:** `src/components/ProfilePage/constants.ts`

```ts
/** Maps class ID to the attribute key used as the base for damage calculation */
export const CLASS_MAIN_ATTRIBUTE: Record<number, keyof CharacterAttributes> = {
  1: 'strength',     // Воин
  2: 'agility',      // Плут
  3: 'intelligence',  // Маг
};
```

**Damage calculation utility:**

**File:** `src/components/ProfilePage/StatsTab/DerivedStatsSection.tsx`

The component currently receives only `attributes`. It needs additional data:
- `raceInfo.id_class` — to determine the character's class (available in Redux as `selectRaceInfo`)
- `equipment` — to find the main weapon's `damage_modifier` (available in Redux as `selectEquipment`)

**Modified component signature:**
```ts
interface DerivedStatsSectionProps {
  attributes: CharacterAttributes;
  classId: number | null;
  mainWeaponDamageModifier: number;
}
```

**Damage override logic inside the component:**
```ts
// For the 'damage' stat, calculate: main attribute value + weapon damage modifier
if (stat === 'damage' && classId != null) {
  const mainAttrKey = CLASS_MAIN_ATTRIBUTE[classId];
  const mainAttrValue = mainAttrKey ? (attributes[mainAttrKey] as number ?? 0) : 0;
  displayDamage = mainAttrValue + mainWeaponDamageModifier;
}
```

**Data flow for props:**
- `StatsTab.tsx` already has access to Redux selectors. It will extract `classId` from `selectRaceInfo` and `mainWeaponDamageModifier` from `selectEquipment` (find slot where `slot_type === 'main_weapon'` and read `item.damage_modifier`), then pass them as props to `DerivedStatsSection`.

### Data Flow Diagram

```
User clicks Equip/Unequip
  → Frontend dispatches equipItem/unequipItem thunk
    → POST /inventory/{id}/equip (or /unequip)
      → inventory-service applies modifiers via character-attributes-service ✅ (no change)
    → thunk dispatches fetchAttributes(characterId) ← NEW
      → GET /attributes/{characterId}
      → Redux state updated with fresh attributes
  → DerivedStatsSection renders:
      damage = CLASS_MAIN_ATTRIBUTE[classId] value + mainWeapon.damage_modifier
      (visual override, DB value ignored for display)
```

### Risks

- **Risk:** Frontend damage display will differ from DB `damage` value and from battle-service calculation. → **Mitigation:** This is by design — user requested visual-only. A tooltip or label can clarify this is "estimated damage" if needed in the future.
- **Risk:** If a new class is added without updating `CLASS_MAIN_ATTRIBUTE`, damage will fall back to showing the raw DB value. → **Mitigation:** The constant is easy to extend; the fallback is safe (shows `attributes.damage` as before).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Add `fetchAttributes(characterId)` to the `Promise.all` in both `equipItem` and `unequipItem` thunks, matching the existing pattern in `useItem` | Frontend Developer | DONE | `src/redux/slices/profileSlice.ts` | — | After equip/unequip, the StatsTab immediately shows updated attribute values without page reload |
| 2 | Add `CLASS_MAIN_ATTRIBUTE` constant mapping class IDs to attribute keys in `constants.ts`. Modify `StatsTab.tsx` to extract `classId` from `selectRaceInfo` and `mainWeaponDamageModifier` from `selectEquipment` (slot_type `main_weapon` → `item.damage_modifier`), pass as props to `DerivedStatsSection`. Modify `DerivedStatsSection.tsx` to accept new props and override damage display: `damage = mainAttributeValue + mainWeaponDamageModifier` | Frontend Developer | DONE | `src/components/ProfilePage/constants.ts`, `src/components/ProfilePage/StatsTab/StatsTab.tsx`, `src/components/ProfilePage/StatsTab/DerivedStatsSection.tsx` | #1 | Damage stat in "Боевые характеристики" section shows calculated value based on class main attribute + weapon modifier. Warrior shows strength-based, Rogue agility-based, Mage intelligence-based. Without weapon equipped, shows just the main attribute value |
| 3 | Review all changes: verify fetchAttributes is called after equip/unequip, verify damage calculation is correct and visual-only (no backend/DB changes), verify TypeScript types, verify Tailwind-only styles, verify mobile responsiveness of any changed UI, run `npx tsc --noEmit` and `npm run build` | Reviewer | DONE | all | #1, #2 | All checks pass, no regressions, damage displays correctly for all 3 classes |

**Note:** No QA Test task is needed — there are zero backend changes. All fixes are frontend-only.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-19
**Result:** PASS

#### Checklist

**1. profileSlice.ts — fetchAttributes in equip/unequip:**
- [x] `fetchAttributes(characterId)` added to `Promise.all` in `equipItem` (line 336) — CORRECT
- [x] `fetchAttributes(characterId)` added to `Promise.all` in `unequipItem` (line 363) — CORRECT
- [x] Pattern matches `useItem` thunk (line 391) which already had `fetchAttributes` — CONSISTENT
- [x] `fetchAttributes` is defined in the same file (line 258) — no separate import needed

**2. constants.ts — CLASS_MAIN_ATTRIBUTE:**
- [x] Maps 1 → `'strength'` (Воин) — CORRECT
- [x] Maps 2 → `'agility'` (Плут) — CORRECT
- [x] Maps 3 → `'intelligence'` (Маг) — CORRECT
- [x] Type is `Record<number, string>` — acceptable (matches usage with `as keyof CharacterAttributes` cast in consumer)

**3. StatsTab.tsx — data extraction and prop passing:**
- [x] `selectRaceInfo` imported and used — CORRECT
- [x] `selectEquipment` imported and used — CORRECT
- [x] `classId` extracted as `raceInfo?.id_class ?? null` — CORRECT (safe null handling)
- [x] `mainWeaponSlot` found via `equipment.find((slot) => slot.slot_type === 'main_weapon')` — CORRECT
- [x] `mainWeaponDamageModifier` extracted as `mainWeaponSlot?.item?.damage_modifier ?? 0` — CORRECT (defaults to 0 when no weapon)
- [x] Props `classId` and `mainWeaponDamageModifier` passed to `DerivedStatsSection` — CORRECT

**4. DerivedStatsSection.tsx — damage calculation:**
- [x] Props interface updated with `classId: number | null` and `mainWeaponDamageModifier: number` — CORRECT
- [x] No `React.FC` used — uses `({ attributes, classId, mainWeaponDamageModifier }: DerivedStatsSectionProps)` — CORRECT
- [x] `getDisplayDamage()` function: falls back to `attributes.damage` when `classId == null` — CORRECT
- [x] Falls back to `attributes.damage` when `CLASS_MAIN_ATTRIBUTE[classId]` is undefined (unknown class) — CORRECT
- [x] Calculates `mainAttrValue + mainWeaponDamageModifier` when class is known — CORRECT per spec
- [x] Cast `attributes[mainAttrKey as keyof CharacterAttributes] as number` is safe (all CharacterAttributes fields are numbers) — CORRECT
- [x] Only `damage` stat display is overridden (line 48: `stat === 'damage' ? getDisplayDamage() : rawValue`) — no other stats affected — CORRECT
- [x] `CLASS_MAIN_ATTRIBUTE` correctly imported from `../constants` — CORRECT

**5. General compliance:**
- [x] No backend changes — CONFIRMED (all changes in `services/frontend/app-chaldea/src/`)
- [x] No DB changes — CONFIRMED
- [x] All files are TypeScript (`.ts` / `.tsx`) — CORRECT
- [x] All styles use Tailwind classes only, no new SCSS/CSS — CORRECT
- [x] No `React.FC` usage — CORRECT
- [x] No new `any` types — CORRECT
- [x] No hardcoded secrets or URLs — CORRECT
- [x] Error handling preserved (all thunks still have catch blocks with Russian messages) — CORRECT
- [x] No QA tests needed — zero backend changes confirmed

**6. Potential concerns (non-blocking):**
- `CLASS_MAIN_ATTRIBUTE` typed as `Record<number, string>` rather than `Record<number, keyof CharacterAttributes>` as the architect specified. This is mitigated by the `as keyof CharacterAttributes` cast at the usage site in DerivedStatsSection.tsx (line 36). Not blocking — works correctly at runtime.

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (all errors are pre-existing in unrelated files: Admin pages, LocationPage, WorldPage. Zero errors in FEAT-049 files)
- [x] `npm run build` — PASS (built successfully in 31.51s, no errors)
- [ ] `py_compile` — N/A (no backend changes)
- [ ] `pytest` — N/A (no backend changes)
- [ ] `docker-compose config` — N/A (no docker changes)
- [ ] Live verification — SKIPPED (no running application available; Node.js not installed on host, app runs in Docker containers which are not currently running)

#### Note on Live Verification
Live verification could not be performed — the application is containerized and containers are not currently running on this machine. The code review and automated build checks confirm correctness. Live testing should be done after deployment.

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-19 — PM: фича создана, запускаю анализ
[LOG] 2026-03-19 — Analyst: анализ завершён, затронуто 4 сервиса. Найдено 4 бага: (1) фронтенд не обновляет атрибуты после equip/unequip — основная причина проблемы, (2) расчёт урона не реализован, (3) нет маппинга класс→основной атрибут, (4) ItemData на фронтенде не содержит resistance/vulnerability модификаторов. Бэкенд equip/unequip логика корректна — все модификаторы передаются и применяются правильно.
[LOG] 2026-03-19 — Architect: спроектировано 3 задачи (2 frontend + 1 review). Бэкенд изменений нет — оба бага frontend-only. BUG 1: добавить fetchAttributes в equip/unequip thunks. BUG 2: визуальный расчёт урона на фронтенде (класс→атрибут + damage_modifier оружия). Статус → IN_PROGRESS.
[LOG] 2026-03-19 — Frontend Dev: начал задачи #1 и #2
[LOG] 2026-03-19 — Frontend Dev: задача #1 завершена — добавлен fetchAttributes(characterId) в Promise.all для equipItem и unequipItem thunks в profileSlice.ts
[LOG] 2026-03-19 — Frontend Dev: задача #2 завершена — добавлен CLASS_MAIN_ATTRIBUTE в constants.ts, StatsTab.tsx передаёт classId и mainWeaponDamageModifier в DerivedStatsSection, компонент рассчитывает урон как основной атрибут класса + damage_modifier оружия
[LOG] 2026-03-19 — Frontend Dev: верификация npx tsc --noEmit и npm run build не выполнена — Node.js не установлен на машине. Код проверен визуально на корректность типов.
[LOG] 2026-03-19 — Reviewer: начал проверку FEAT-049
[LOG] 2026-03-19 — Reviewer: проверены все 4 файла: profileSlice.ts, constants.ts, StatsTab.tsx, DerivedStatsSection.tsx
[LOG] 2026-03-19 — Reviewer: npx tsc --noEmit и npm run build выполнены через Docker (node:20-alpine). Ошибки tsc — только в старых файлах (Admin, LocationPage, WorldPage). В файлах FEAT-049 ошибок нет. Build прошёл успешно.
[LOG] 2026-03-19 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_Pending..._
