# FEAT-017: Визуальная доработка Drag & Drop

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-16 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-017-dnd-visual-polish.md` → `DONE-FEAT-017-dnd-visual-polish.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Два визуальных недочёта в Drag & Drop инвентаря (FEAT-016):

1. **Недоступные слоты не затемняются:** При перетаскивании предмета совместимые слоты пульсируют (правильно), но несовместимые слоты выглядят так же как обычно. Нужно затемнить/приглушить несовместимые слоты, чтобы визуально показать, что туда нельзя.

2. **Быстрые слоты показывают количество из инвентаря:** При установке зелья в быстрый слот отображается число предметов из инвентаря (например "25"), создавая ложное ощущение, что в слоте 25 штук. В быстрых слотах бейдж количества нужно убрать.

### Бизнес-правила
- Несовместимые слоты должны быть визуально приглушены во время drag
- В быстрых слотах не показывать количество предметов

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Both issues are localized to two components in `ProfilePage/EquipmentPanel/`:

- **EquipmentSlot.tsx** — already uses `useCompatibleSlots()` to apply `slot-pulse-compatible` class on compatible slots, but does nothing for incompatible ones during active drag.
- **FastSlots.tsx** — same pattern for compatible slots. Additionally renders a quantity badge (`slot.quantity > 1`) on filled fast slots, which is misleading since each fast slot holds exactly 1 item.
- **InventoryDndContext.tsx** — provides `useCompatibleSlots()` (string[] of compatible slot types) and `useActiveDrag()` (DragItemData | null when drag is active). Both hooks are already exported and available.

No cross-service or API changes needed. Pure visual adjustments.

---

## 3. Architecture Decision (filled by Architect — in English)

**Fix 1 — Dim incompatible slots:** Use `useActiveDrag()` hook to detect active drag state. When drag is active and the slot is NOT in the compatible slots list, apply Tailwind utility classes `opacity-30 brightness-50` for visual dimming. No new CSS classes needed.

**Fix 2 — Remove quantity badge:** Remove the conditional quantity badge rendering (`{slot.quantity > 1 && ...}`) from the filled fast slot in `FastSlots.tsx`.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

- [x] **Task 1:** In `EquipmentSlot.tsx` — import `useActiveDrag`, compute `isIncompatible` flag, apply `opacity-30 brightness-50` when drag is active and slot is not compatible.
- [x] **Task 2:** In `FastSlots.tsx` — import `useActiveDrag`, compute `isIncompatible` flag, apply dimming to both empty and filled enabled fast slots when incompatible.
- [x] **Task 3:** In `FastSlots.tsx` — remove the quantity badge from filled fast slots.
- [x] **Task 4:** Build verification — `tsc --noEmit` and `npm run build` pass (no new errors).

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-16
**Result:** PASS

#### Code Review

**Dimming logic (EquipmentSlot.tsx lines 67-69):**
- `isCompatible = compatibleSlots.includes(slot.slot_type)` — correct
- `isDragActive = activeDrag !== null` — correct, sourced from `useActiveDrag()` context
- `isIncompatible = isDragActive && !isCompatible` — correct: dimming only when drag is active AND slot is not compatible
- Applied via `opacity-30 brightness-50` Tailwind utilities — standard classes, no custom CSS needed

**Dimming logic (FastSlots.tsx lines 29-33):**
- `isIncompatible = isDragActive && !isDisabled && !isCompatible` — correct: disabled slots are excluded (they have their own `opacity-30` styling at line 86)
- Dimming applied to both empty (line 100) and filled (line 107) enabled fast slots — correct

**Drag end/cancel cleanup (InventoryDndContext.tsx):**
- `handleDragEnd` (line 127-128): `setActiveDragData(null); setCompatibleSlots([])` — clears state correctly
- `handleDragCancel` (line 196-197): same cleanup — correct
- When `activeDrag` becomes `null`, `isDragActive = false`, so `isIncompatible = false` — dimming removed automatically

**Quantity badge removal (FastSlots.tsx):**
- Old code `{slot.quantity > 1 && <span>...</span>}` completely removed from render output — confirmed
- `quantity` field retained only in data model (interface, merging) — no visual rendering

**Code standards:**
- [x] Both files are `.tsx` — no `.jsx` violations
- [x] No `React.FC` usage — components use `function` declarations and arrow functions with typed props
- [x] All new styles use Tailwind utilities — no SCSS/CSS additions
- [x] No hardcoded secrets or URLs
- [x] No `any` types
- [x] No TODO/FIXME stubs
- [x] No backend changes — QA not required

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (10 pre-existing errors in unrelated files: Admin/Request, AdminLocationsPage, AdminSkillsPage, LocationPage — none in FEAT-017 files)
- [x] `npm run build` — PASS (built in 4.17s, warnings only for pre-existing SCSS deprecations)
- [x] `py_compile` — N/A (no backend changes)
- [x] `pytest` — N/A (no backend changes)
- [x] `docker-compose config` — N/A (no docker changes)

#### Live Verification Results
- Page tested: `/profile` (via nginx gateway on port 80)
- Page loads: HTTP 200 OK confirmed
- Source files verified: `opacity-30` and `brightness-50` classes present in EquipmentSlot.tsx (1 occurrence each) and FastSlots.tsx (3 and 2 occurrences respectively — covering empty and filled slot paths)
- Quantity badge: fully removed from FastSlots render output, confirmed via grep
- No new SCSS/CSS files added

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-16 19:00 — PM: фича создана, запускаю анализ и исправление
[LOG] 2026-03-16 19:10 — Frontend Dev: начал работу над FEAT-017
[LOG] 2026-03-16 19:12 — Frontend Dev: Fix 1 — добавлено затемнение несовместимых слотов в EquipmentSlot.tsx и FastSlots.tsx (opacity-30 brightness-50 при активном drag)
[LOG] 2026-03-16 19:13 — Frontend Dev: Fix 2 — убран бейдж количества из быстрых слотов в FastSlots.tsx
[LOG] 2026-03-16 19:15 — Frontend Dev: сборка прошла успешно (npm run build OK, tsc ошибки только в нерелевантных файлах)
[LOG] 2026-03-16 19:15 — Frontend Dev: статус изменён на REVIEW
[LOG] 2026-03-16 19:25 — Reviewer: начал проверку FEAT-017
[LOG] 2026-03-16 19:30 — Reviewer: код проверен — логика затемнения корректна, бейдж количества удалён, tsc и build пройдены
[LOG] 2026-03-16 19:30 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Несовместимые слоты затемняются (`opacity-30 brightness-50`) при перетаскивании предмета
- Убран бейдж количества из быстрых слотов (каждый слот = 1 предмет)

### Оставшиеся риски / follow-up задачи
- Нет
