# FEAT-019: Кнопка "Снять" в контекстном меню для надетых предметов

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-16 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-019-unequip-context-menu.md` → `DONE-FEAT-019-unequip-context-menu.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
При клике на надетый предмет (в слоте экипировки или быстром слоте) открывается контекстное меню, но в нём нет кнопки "Снять". Нужно добавить опцию "Снять" для экипированных предметов, которая снимает предмет и возвращает его в инвентарь.

### Бизнес-правила
- Кнопка "Снять" отображается только для надетых предметов (экипировка + быстрые слоты)
- При нажатии "Снять" — предмет снимается и возвращается в инвентарь
- Для предметов в инвентаре (не надетых) кнопка "Снять" не показывается

### UX / Пользовательский сценарий
1. Игрок кликает по надетому предмету в слоте экипировки
2. Открывается контекстное меню
3. В меню есть кнопка "Снять"
4. Игрок нажимает "Снять"
5. Предмет снимается и возвращается в инвентарь

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Context menu (`ItemContextMenu.tsx`) already supports equip/use/drop actions. The `unequipItem` thunk exists in `profileSlice.ts` and requires `{ characterId, slotType }`. Equipment slots (`EquipmentSlot.tsx`) and fast slots (`FastSlots.tsx`) open the context menu but do not pass `slotType`, so the menu cannot distinguish equipped items from inventory items.

---

## 3. Architecture Decision (filled by Architect — in English)

Add optional `slotType` field to `ContextMenuState` in profileSlice. Pass it when opening context menu from equipment/fast slots. In `ItemContextMenu`, show "Снять" when `slotType` is present (item is equipped), hide "Надеть" in that case.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

1. Add `slotType?: string` to `ContextMenuState` and `openContextMenu` action in `profileSlice.ts`
2. Pass `slotType` from `EquipmentSlot.tsx` and `FastSlots.tsx` when dispatching `openContextMenu`
3. Add "Снять" button in `ItemContextMenu.tsx` when `slotType` is present; hide "Надеть" for equipped items

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-16
**Result:** PASS

#### Code Review
- [x] `slotType` flows correctly: EquipmentSlot/FastSlots pass `slotType: slot.slot_type` via `openContextMenu` -> stored in `ContextMenuState` -> read by `ItemContextMenu`
- [x] "Снять" only shows when `contextMenu.slotType` is truthy (equipped items)
- [x] "Надеть" hidden when `contextMenu.slotType` is present (line 95: `!contextMenu.slotType && EQUIPMENT_TYPES.has(itemType)`)
- [x] `unequipItem` dispatch uses correct params: `{ characterId, slotType: contextMenu.slotType! }` (non-null assertion safe due to guard)
- [x] `closeContextMenu` resets `slotType: undefined`
- [x] Toast messages in Russian ("Предмет снят")
- [x] No `React.FC` usage
- [x] No new SCSS/CSS files — all styles use existing Tailwind/design-system classes
- [x] All modified files are `.tsx` / `.ts`
- [x] No `any` types introduced
- [x] No hardcoded secrets or URLs
- [x] Frontend errors displayed to user via `toast.error`
- [x] No backend changes — QA not required

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (all errors are pre-existing in unrelated files: Request.tsx, LocationNeighborsEditor.tsx, AdminSkillsPage.tsx, LocationPage.tsx)
- [x] `npm run build` — PASS (built in 3.92s)
- [x] `py_compile` — N/A (no backend changes)
- [x] `pytest` — N/A (no backend changes)
- [x] `docker-compose config` — N/A (no docker changes)

#### Live Verification Results
- Backend endpoint tested: `POST /inventory/1/unequip?slot_type=body` — returns 200, item unequipped correctly
- Backend endpoint tested: `POST /inventory/1/equip` — returns 200, item re-equipped correctly
- Frontend accessible: `GET http://localhost` — returns 200
- Equipment endpoint: `GET /inventory/1/equipment` — returns 200 with slot data including `slot_type` field

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-16 21:00 — PM: фича создана, запускаю анализ
[LOG] 2026-03-16 21:10 — Frontend Dev: начал задачу — добавление кнопки "Снять" в контекстное меню
[LOG] 2026-03-16 21:15 — Frontend Dev: добавлен slotType в ContextMenuState и openContextMenu (profileSlice.ts)
[LOG] 2026-03-16 21:16 — Frontend Dev: передан slotType из EquipmentSlot.tsx и FastSlots.tsx
[LOG] 2026-03-16 21:17 — Frontend Dev: добавлена кнопка "Снять" в ItemContextMenu.tsx, скрыта "Надеть" для экипированных предметов
[LOG] 2026-03-16 21:20 — Frontend Dev: tsc --noEmit — 0 ошибок в изменённых файлах, npm run build — успешно
[LOG] 2026-03-16 21:20 — Frontend Dev: задача завершена, статус REVIEW
[LOG] 2026-03-16 21:30 — Reviewer: начал проверку
[LOG] 2026-03-16 21:35 — Reviewer: код-ревью пройден, все проверки выполнены
[LOG] 2026-03-16 21:36 — Reviewer: tsc --noEmit — ошибки только в нерелевантных файлах, npm run build — успешно
[LOG] 2026-03-16 21:37 — Reviewer: live-проверка backend эндпоинтов — unequip/equip работают корректно
[LOG] 2026-03-16 21:38 — Reviewer: проверка завершена, результат PASS
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Добавлена кнопка "Снять" в контекстное меню для надетых предметов (экипировка + быстрые слоты)
- Кнопка "Надеть" скрывается для уже экипированных предметов
- `slotType` передаётся из EquipmentSlot/FastSlots через Redux в контекстное меню

### Оставшиеся риски / follow-up задачи
- Нет
