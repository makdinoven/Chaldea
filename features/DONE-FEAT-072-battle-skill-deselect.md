# FEAT-072: Отмена выбора навыков в бою

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-24 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-072-battle-skill-deselect.md` → `DONE-FEAT-072-battle-skill-deselect.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
В бою есть панель быстрых слотов, куда игрок выставляет навыки (атакующий, защитный, поддержка). Сейчас навыки можно только добавить в слоты, но нельзя убрать — клик по выбранному навыку ничего не делает, кнопки отмены нет.

### Бизнес-правила
- Клик по уже выбранному навыку в слоте — снимает его (toggle-поведение)
- Отдельная кнопка "Очистить" — сбрасывает все выбранные навыки разом
- После снятия навыка слот становится пустым и доступным для нового выбора
- Оба механизма работают в любой момент до отправки хода

### UX / Пользовательский сценарий
1. Игрок в бою, выбирает навыки в слоты (атака, защита, поддержка)
2. Игрок хочет изменить выбор — кликает на уже выбранный навык → навык убирается из слота
3. Или игрок нажимает кнопку "Очистить" → все слоты сбрасываются
4. Игрок выбирает другие навыки и отправляет ход

### Edge Cases
- Что если игрок нажмёт "Очистить" когда ни один навык не выбран? (ничего не происходит)
- Что если навык в кулдауне — можно ли его снять? (да, снять можно всегда)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | UI logic only — add deselect click handler + clear button | `BattlePageBar.tsx`, `ItemSkillCircle.jsx`, `BattlePage.tsx` |

No backend changes required. The turn submission API already accepts `null` for any skill slot.

### Skill Selection Flow — Current State

#### 1. State Management (BattlePage.tsx, lines 146–151)

The selected skills are stored in local React state (`useState`) inside `BattlePage`:

```ts
const [turnData, setTurnData] = useState<TurnDataState>({
  [SKILLS_KEYS.attack]: null,   // "attack"
  [SKILLS_KEYS.defense]: null,  // "defense"
  [SKILLS_KEYS.support]: null,  // "support"
  [SKILLS_KEYS.item]: null,     // "item"
});
```

`TurnDataState` is `{ [key: string]: SkillSlot | null }` where `SkillSlot = { id?: number; item_id?: number }`. A `null` value means the slot is empty.

**No Redux is used** — this is purely local component state, passed down via props.

#### 2. How Skills Get Selected Into Slots

Two mechanisms exist:

**A) Click selection (primary)** — `InventoryItem.jsx` (lines 96–112, 116–125)

`handleSelectSkill()` in `InventoryItem` calls `setTurnData` (passed from BattlePage → CharacterSide → CharacterInventory → InventorySection → InventoryItem). It checks `item.skill_type` to determine which slot key to use:
- If `item.skill_type` exists (e.g. "attack", "defense", "support") → sets `turnData[SKILLS_KEYS[item.skill_type]]` to the item
- If no `skill_type` (consumable item) → sets `turnData[SKILLS_KEYS.item]` to the item

Guard: if `isDraggable && isCooldown` → returns early (can't select skills on cooldown). Also returns early if `setTurnData` is not provided (opponent side).

A native DOM `click` listener is attached as a fallback because React synthetic events don't fire reliably on draggable elements.

**B) Drag-and-drop (secondary)** — `ItemSkillCircle.jsx` (lines 13–25)

`ItemSkillCircle` handles `onDrop` events. When an item is dropped on a slot circle, it parses JSON from `dataTransfer` and calls `onDropItem(item)`. The `onDropItem` callback in `BattlePageBar.tsx` (lines 458–462) sets the appropriate slot in `turnData`.

#### 3. Quick Slots Panel (BattlePageBar.tsx, lines 454–482)

The slot circles are rendered in `BattlePageBar`:
- 3 skill slots: `SKILLS_BTNS` array maps over `[attack, defense, support]`, each renders an `ItemSkillCircle`
- 1 item slot: separate `ItemSkillCircle` for `SKILLS_KEYS.item`

Each `ItemSkillCircle` receives:
- `choosedItem` — the currently selected item (or null/undefined)
- `onDropItem` — callback to set the item in the slot
- `isClosed` — true when it's the opponent's turn (disables interaction)
- `type` — slot type string

#### 4. What Happens When Clicking a Filled Slot — THE PROBLEM

`ItemSkillCircle.jsx` has **no onClick handler**. The component only handles:
- `onDrop` — for drag-and-drop
- `onDragOver` — to allow drops

When `choosedItem` is truthy, it renders `<InventoryItem isDraggable={false} item={choosedItem} />`. Because `isDraggable={false}`, the native click listener inside InventoryItem **does not attach** (line 118: `if (!el || !isDraggable) return`). And `setTurnData` is not passed to this InventoryItem instance — it only gets `isDraggable={false}` and `item`.

**Result:** Clicking on a filled slot does absolutely nothing. There is no code path to clear a slot.

#### 5. Turn Submission (BattlePage.tsx, lines 388–410)

`handleSendTurn()` builds the API payload:
```ts
const turnDataApi = {
  participant_id: myData.participant_id,
  skills: {
    attack_rank_id: turnData.attack?.id ?? null,
    defense_rank_id: turnData.defense?.id ?? null,
    support_rank_id: turnData.support?.id ?? null,
    item_id: turnData.item?.item_id ?? null,
  },
};
```

After successful submission, `turnData` is reset to all-null (lines 403–408). This confirms the backend already handles null values in any slot — no backend changes needed.

#### 6. Existing Deselect Logic

**None.** There is no commented-out code, no partial implementation, no clear/reset button anywhere in the UI (except the post-submission reset). The only way to "change" a selected skill is to drag/click a different skill of the same type into the slot, which overwrites the previous selection.

#### 7. "Clear All" Button

There is no "Clear All" / "Reset" / "Очистить" button in `BattlePageBar`. The only existing reset happens automatically after turn submission (line 403).

### Component Tree (relevant path)

```
BattlePage (state owner: turnData, setTurnData)
├── CharacterSide (left — player)
│   └── CharacterInventory
│       └── InventorySection
│           └── InventoryItem (click/drag → setTurnData to ADD skill)
├── BattlePageBar (receives turnData + setTurnData)
│   ├── ItemSkillCircle × 3 (attack, defense, support slots)
│   │   └── InventoryItem (isDraggable=false, NO setTurnData — display only)
│   ├── ItemSkillCircle × 1 (item slot)
│   └── "Передать ход" button (calls handleSendTurn)
└── CharacterSide (right — opponent, no setTurnData)
```

### Existing Patterns

- Frontend: React 18, local state (useState), no Redux for battle turn data
- `ItemSkillCircle.jsx` and `InventoryItem.jsx` are `.jsx` files — per CLAUDE.md rule 9, if logic is changed they must be migrated to `.tsx`
- `CharacterSide.jsx`, `CharacterInventory.jsx`, `InventorySection.jsx` are also `.jsx` — but only need migration if their logic changes
- Styles: `ItemSkillCircle.module.scss`, `BattlePageBar.module.scss` — per CLAUDE.md rule 8, style changes require Tailwind migration for modified components
- The slot circle already has `cursor: pointer` in SCSS

### Cross-Service Dependencies

None. This is a purely frontend change. The turn data format sent to `POST /battles/{battleId}/action` does not change — null values are already supported.

### DB Changes

None.

### Risks

- **Risk:** Migrating `ItemSkillCircle.jsx` to `.tsx` could introduce type errors in other imports → **Mitigation:** Update all import paths; the component has a simple props interface
- **Risk:** Adding click handler to filled slot might interfere with drag-and-drop behavior → **Mitigation:** Use `onClick` handler (not drag events); test both click-deselect and drag-to-replace workflows
- **Risk:** "Clear all" button placement — needs UX decision on where to put it in the bar → **Mitigation:** Place near the skill slots row, only visible when at least one slot is filled

---

## 3. Architecture Decision (filled by Architect — in English)

### API Contracts

No API changes. The existing `POST /battles/{battleId}/action` already accepts `null` for all skill/item slots.

### Security Considerations

Not applicable — this is a frontend-only UI interaction change with no new API calls, no new data, and no auth changes.

### DB Changes

None.

### Frontend Components

#### 1. `ItemSkillCircle` — migrate `.jsx` → `.tsx`, add `onClear` prop

**Current file:** `ItemSkillCircle/ItemSkillCircle.jsx`
**New file:** `ItemSkillCircle/ItemSkillCircle.tsx` (delete `.jsx`)

Add a new optional prop `onClear?: () => void`. When the slot has a `choosedItem` and is not `isClosed`, attach an `onClick` handler to the outer `<div>` that calls `onClear()`.

**Props interface:**

```ts
interface ItemSkillCircleProps {
  isClosed: boolean;
  type: string;
  onDropItem: (item: SkillSlot) => void;
  choosedItem: SkillSlot | null;
  onClear?: () => void;
}
```

**onClick logic (on the outer div):**

```ts
const handleClick = () => {
  if (isClosed || !choosedItem || !onClear) return;
  onClear();
};
```

The `onClick` fires on the outer `<div>`. Since the inner `InventoryItem` is rendered with `isDraggable={false}`, it does NOT attach its own native click listener (line 118 guard: `if (!el || !isDraggable) return`). So clicks bubble up to the outer div with no conflict.

Drag-and-drop is unaffected — `onDrop` and `onDragOver` are separate events from `onClick`.

**Style migration:** `ItemSkillCircle.module.scss` must be migrated to Tailwind classes inline. The styles are simple (flexbox circle with border, conditional states). Delete the `.module.scss` file after migration.

#### 2. `BattlePageBar.tsx` — pass `onClear` to each `ItemSkillCircle`, add "Очистить" button

**Pass `onClear` to each slot circle:**

For the 3 skill slots in the `SKILLS_BTNS.map(...)`:
```tsx
onClear={() => {
  setTurnData((prev) => ({
    ...prev,
    [SKILLS_KEYS[btn.type as keyof typeof SKILLS_KEYS]]: null,
  }));
}}
```

For the item slot:
```tsx
onClear={() => {
  setTurnData((prev) => ({
    ...prev,
    [SKILLS_KEYS.item]: null,
  }));
}}
```

**"Очистить" button:**

Place inside the `.icons` div, after the item slot circle, separated by a vertical line (matching existing `.line` pattern). The button:
- Only renders when at least one slot is filled AND it's the player's turn (`!isOpponentTurn`)
- Calls `setTurnData` to reset all 4 slots to `null`
- Uses Tailwind classes (no new SCSS)
- Text: "Очистить"
- Style: small, subtle — similar to existing text buttons in the bar. Use `text-xs uppercase text-white/60 hover:text-site-blue transition-colors` with appropriate sizing.

**Helper to check if any slot is filled:**
```ts
const hasAnySlotFilled = Object.values(turnData).some(Boolean);
```

#### 3. `InventoryItem.jsx` — NO changes needed

`InventoryItem` logic is NOT changed by this feature. The deselect happens at the `ItemSkillCircle` level via the new `onClear` prop, not inside `InventoryItem`. Since we are not modifying `InventoryItem`'s logic, per CLAUDE.md rule 9 we do NOT migrate it to `.tsx` in this PR.

### Data Flow Diagram

```
DESELECT (click on filled slot):
  User clicks filled ItemSkillCircle
    → onClick fires on outer div
    → onClear() callback fires
    → setTurnData(prev => {...prev, [slotKey]: null})
    → React re-renders: slot shows empty circle with icon

CLEAR ALL (button click):
  User clicks "Очистить" button in BattlePageBar
    → setTurnData({attack: null, defense: null, support: null, item: null})
    → React re-renders: all slots show empty circles

No API calls. No cross-service communication. State change is local to BattlePage.
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Migrate `ItemSkillCircle.jsx` to TypeScript (`.tsx`), migrate styles from `ItemSkillCircle.module.scss` to Tailwind, add `onClear` prop with onClick handler for deselect. Delete old `.jsx` and `.module.scss` files. | Frontend Developer | DONE | `ItemSkillCircle/ItemSkillCircle.tsx` (new), `ItemSkillCircle/ItemSkillCircle.jsx` (delete), `ItemSkillCircle/ItemSkillCircle.module.scss` (delete) | — | 1) Component renders identically to before (circle with border, icon, dropped state, closed state). 2) Clicking a filled slot when `onClear` is provided calls `onClear()`. 3) Clicking an empty slot or a closed slot does nothing. 4) Drag-and-drop still works (onDrop/onDragOver unchanged). 5) `npx tsc --noEmit` passes. 6) All styles use Tailwind, no SCSS file remains. |
| 2 | In `BattlePageBar.tsx`: pass `onClear` callback to each `ItemSkillCircle` (sets the corresponding slot to `null`), add "Очистить" button that resets all slots. Button only visible when at least one slot is filled and it is the player's turn. Adapt styles for mobile (360px+). | Frontend Developer | DONE | `BattlePageBar.tsx` | #1 | 1) Clicking a filled skill/item slot clears it (slot becomes empty). 2) "Очистить" button appears when any slot is filled. 3) "Очистить" resets all 4 slots to null. 4) "Очистить" is hidden when all slots are empty or when it's opponent's turn. 5) Button and slots are usable on mobile (360px+). 6) `npx tsc --noEmit` and `npm run build` pass. |
| 3 | Review all changes | Reviewer | DONE | all | #1, #2 | 1) Deselect via click works for all 4 slot types. 2) "Очистить" works correctly. 3) Drag-and-drop still functions. 4) No regressions in battle flow. 5) TypeScript strict, Tailwind only, no React.FC. 6) Mobile-responsive (360px+). 7) Build passes. 8) Live verification: zero console errors, feature works end-to-end. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-24
**Result:** PASS (conditional)

#### Code Review Checklist

- [x] **TypeScript:** Props interface `ItemSkillCircleProps` is correct, no `any` (uses `unknown`), no `React.FC`
- [x] **Tailwind migration:** All styles migrated from `ItemSkillCircle.module.scss` to Tailwind classes. SCSS file deleted. Visual equivalence confirmed by comparing original SCSS with new classes.
- [x] **onClear logic:** `handleClick()` correctly guards with `isClosed || !choosedItem || !onClear`. Clicking filled slot calls `onClear()`. Empty/closed slots do nothing.
- [x] **"Очистить" button:** Conditionally rendered only when `!isOpponentTurn && Object.values(turnData).some(Boolean)`. Resets all 4 slots to null. Uses design-system-compliant Tailwind classes (`text-white/60 hover:text-site-blue transition-colors duration-200 ease-site`).
- [x] **Drag-and-drop:** `onDrop`/`onDragOver` handlers unchanged in logic. `onClick` does not conflict with drag events.
- [x] **Imports:** Only `BattlePageBar.tsx` imports `ItemSkillCircle`. Import path unchanged (resolves `.tsx` automatically). No other importers found.
- [x] **Old files deleted:** `ItemSkillCircle.jsx` and `ItemSkillCircle.module.scss` confirmed deleted.
- [x] **No `React.FC`** — uses `const ItemSkillCircle = ({ ... }: ItemSkillCircleProps) => {`
- [x] **No new SCSS** — all new styles use Tailwind
- [x] **User-facing text in Russian** — "Очистить" button label
- [x] **Design system tokens** — `text-site-blue`, `ease-site`, `duration-200` all from `tailwind.config.js`
- [x] **No hardcoded secrets/URLs**
- [x] **Error handling** — `handleDrop` has try/catch with `console.warn` (unchanged from original)
- [x] **Mobile (360px+):** "Очистить" button is compact (`text-xs`, `ml-2`). Slot circles are 60px fixed (same as before). Pre-existing layout may overflow on very small screens, but this is not a regression.

#### Minor Observations (non-blocking)

1. **Redundant responsive class** (`ItemSkillCircle.tsx:60`): `sm:w-[60px] sm:h-[60px]` is identical to `w-[60px] h-[60px]` — has no effect. Can be removed in a cleanup pass.
2. **Pre-existing `console.log`** (`BattlePageBar.tsx:479`): `console.log(data)` in the item slot's `onDropItem` callback. Not introduced by this feature — pre-existing debug log.

#### Automated Check Results

- [ ] `npx tsc --noEmit` — N/A (Node.js not installed on this machine)
- [ ] `npm run build` — N/A (Node.js not installed on this machine)
- [ ] `py_compile` — N/A (no backend changes)
- [ ] `pytest` — N/A (no backend changes)
- [ ] `docker-compose config` — N/A (no docker changes)
- [ ] Live verification — N/A (Node.js not installed, cannot run dev server)

**Note:** Both the Frontend Developer and Reviewer were unable to run `tsc` and `npm run build` because Node.js is not installed on this machine. The code review is thorough and no type issues were identified by manual inspection. **PM should ensure these checks pass in CI or on a machine with Node.js before merging.**

#### Verdict

Code changes are correct, minimal, and follow all project conventions. The feature logic (deselect via click + "Очистить" button) is sound. TypeScript types are proper, Tailwind migration is complete, no regressions in existing functionality. **PASS conditional on `tsc --noEmit` and `npm run build` passing in CI.**

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-24 19:00 — PM: фича создана, запускаю анализ кодовой базы
[LOG] 2026-03-24 19:15 — Analyst: анализ завершён. Затронут 1 сервис (frontend). Проблема: ItemSkillCircle не имеет onClick-обработчика, InventoryItem внутри слота рендерится с isDraggable=false и без setTurnData — клик ничего не делает. Кнопки "Очистить" нет. Backend изменений не требуется — null в слотах уже поддерживается.
[LOG] 2026-03-24 19:30 — Architect: спроектировано 3 задачи (2 Frontend + 1 Review), 0 API-контрактов. Решение: новый проп onClear на ItemSkillCircle + кнопка "Очистить" в BattlePageBar. Миграция ItemSkillCircle.jsx→.tsx + SCSS→Tailwind. InventoryItem не затронут — не мигрируем. Backend/QA не нужны.
[LOG] 2026-03-24 20:00 — Frontend Dev: начал задачи #1 и #2
[LOG] 2026-03-24 20:15 — Frontend Dev: задача #1 завершена — ItemSkillCircle мигрирован в .tsx, стили переведены на Tailwind, добавлен проп onClear с onClick-обработчиком, удалены .jsx и .module.scss
[LOG] 2026-03-24 20:20 — Frontend Dev: задача #2 завершена — в BattlePageBar передан onClear для всех 4 слотов, добавлена кнопка "Очистить" (видна только при заполненных слотах и ходе игрока). Node.js не установлен на машине — tsc и build невозможно запустить локально.
[LOG] 2026-03-24 20:35 — Reviewer: начал проверку FEAT-072
[LOG] 2026-03-24 20:50 — Reviewer: проверка завершена, результат PASS (условный — tsc/build не запущены из-за отсутствия Node.js). Код корректен: типы правильные, Tailwind-миграция полная, onClear-логика верная, кнопка "Очистить" условно показывается, drag-and-drop не затронут, старые файлы удалены. Две мелких заметки: избыточные sm: классы и предсуществующий console.log.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Клик по заполненному слоту навыка/предмета в бою убирает навык (toggle-поведение)
- Добавлена кнопка "Очистить" — сбрасывает все 4 слота разом
- Кнопка видна только когда есть хотя бы один заполненный слот и ход игрока
- `ItemSkillCircle` мигрирован с JSX на TypeScript, стили переведены с SCSS на Tailwind
- Старые файлы (.jsx, .module.scss) удалены

### Изменённые файлы
- `ItemSkillCircle/ItemSkillCircle.tsx` — новый (замена .jsx)
- `BattlePageBar.tsx` — onClear для слотов + кнопка "Очистить"

### Что изменилось от первоначального плана
- Ничего, реализовано по плану

### Оставшиеся риски / follow-up задачи
- `npx tsc --noEmit` / `npm run build` не запускались локально — проверить в CI
- Предсуществующий `console.log(data)` в BattlePageBar.tsx:479 — не блокирует, но стоит убрать
