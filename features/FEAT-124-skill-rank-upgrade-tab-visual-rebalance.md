# FEAT-124: Ребаланс визуала вкладки улучшений навыка (публичный модуль навыков)

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-04-07 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (PM)

### Описание
В публичном модуле навыков (просмотр игроком), на вкладке «улучшения навыка» (список рангов навыка) визуал не соответствует красоте основного публичного дерева навыков — выглядит плоско и невыразительно. Нужно привести вкладку к стилю дерева: золотые рамки, «воздушные» прозрачные фоны, декоративные элементы, акценты на текущем ранге.

### Бизнес-правила
- Только визуальные изменения. Логика, данные, API — не трогаем.
- Сохранить всю текущую информацию о рангах (название, описание, стоимость, эффекты, кулдаун и т.д.).
- Дизайн соответствует Design System (`docs/DESIGN-SYSTEM.md`): `gold-text`, `gold-outline`, `hover-gold-overlay`, токены Tailwind.
- Адаптивность 360px+ (T5).
- Если файл `.jsx` — мигрировать на `.tsx` (T3). Если SCSS — мигрировать на Tailwind (T1).

### UX / Визуальные идеи (от PM, согласованы с пользователем)
1. **Карточки рангов** вместо плоского списка/таблицы — каждый ранг отдельная карточка с золотой обводкой.
2. **Текущий ранг** ярко подсвечивается (золотой бордер + glow), будущие приглушены, прошлые — с галочкой.
3. **Шапка карточки**: крупная римская цифра ранга (I, II, III…) золотом слева как декор; название — `gold-text`; справа бейдж стоимости прокачки с иконкой.
4. **Контент**: описание курсивом приглушённым цветом; числовые параметры (урон, кд, мана и т.п.) — иконка + число в ряд; дельта от предыдущего ранга подсвечена зелёным (+5).
5. **Связь с деревом**: вертикальная золотая линия слева, соединяющая карточки рангов (метафора ветки прокачки); декоративные ромбы/звёзды между карточками.
6. **Иконка навыка** крупно сверху вкладки в золотой рамке.
7. **Hover** — `hover-gold-overlay`. Плавное появление карточек.

### Референс
- Скрин текущего состояния: `services/frontend/img_114.png`
- Образец стиля: основное публичное дерево навыков (тот же модуль).

### Edge Cases
- Навык с одним рангом — карточка без соединительной линии.
- Длинные описания — карточка корректно растягивается.
- Очень узкий экран (360px) — карточки в одну колонку, римская цифра не наезжает на текст.
- Ранг без числовых параметров — секция с иконками скрыта.

### Вопросы к пользователю
- Никаких — пользователь дал зелёный свет на «попробовать и посмотреть».

---

## 2. Analysis Report (Codebase Analyst)

### Target Component (the "skill rank upgrades tab")

The screenshot `services/frontend/img_114.png` shows a modal dialog titled "УДАР ВОИНА" with a rank mini-tree (three green circle nodes connected by a gold line) and a "Текущий ранг" info box at the bottom. This is **not** a tab in the tab-strip sense — it is rendered as a modal dialog, but functionally it is the "skill rank upgrades view" the brief refers to.

- **File:** `services/frontend/app-chaldea/src/components/SkillTreeView/SkillUpgradeModal.tsx`
- **Format:** `.tsx` already (T3 OK — no JSX->TSX migration needed)
- **Styling:** Pure Tailwind + existing `@layer components` classes (`modal-overlay`, `modal-content`, `gold-outline`, `gold-outline-thick`, `gold-text`, `gold-scrollbar`, `btn-blue`, `btn-line`). No SCSS module attached. **T1 OK** — no SCSS to migrate. New work must stay in Tailwind.
- **Animation:** Already uses `motion/react` (`AnimatePresence`, scale+fade). Consistent with design system section 12.
- **Trigger / parent:** Opened from `SkillPurchaseCard.tsx` (same folder) when the player clicks the "upgrade" affordance on a purchased/chosen skill. `SkillPurchaseCard` is itself rendered inside `NodeDetailPanel.tsx` (the side panel on the Skill Tree page).
- **Route:** The whole flow lives on the `/skill-tree` route, mounted via `SkillTreePage.tsx` in the same folder. The Profile page's `ProfilePage/SkillsTab/SkillsTab.tsx` is a *different*, separate component (shows already-learned skills grid + a detail modal) and is **not** the target of this feature.

### Public Skill-Tree Visual Reference (to mirror)

The style the brief wants the upgrade view to match lives in the same module:

| Role | File |
|------|------|
| Page shell | `services/frontend/app-chaldea/src/components/SkillTreeView/SkillTreePage.tsx` |
| Tree canvas (gold connections, animated hex nodes) | `services/frontend/app-chaldea/src/components/SkillTreeView/PlayerTreeCanvas.tsx` |
| Individual tree node | `services/frontend/app-chaldea/src/components/SkillTreeView/PlayerNodeComponent.tsx` |
| Side detail panel | `services/frontend/app-chaldea/src/components/SkillTreeView/NodeDetailPanel.tsx` |
| Per-skill purchase card | `services/frontend/app-chaldea/src/components/SkillTreeView/SkillPurchaseCard.tsx` |

Key visual tokens already used in the tree and available for reuse in the upgrade view:

- `gray-bg gold-outline relative rounded-card` — standard floating panel chrome (see `NodeDetailPanel.tsx:113`)
- `gold-outline gold-outline-thick` — thick 2px gold border for active/modal surfaces (`SkillUpgradeModal.tsx:180`)
- `gold-text text-xl font-medium uppercase` — headings
- `gold-scrollbar` — scroll containers
- `shadow-[0_0_10px_rgba(240,217,92,0.4)]` — gold glow used on hoverable/available rank nodes (already in `SkillUpgradeModal.tsx:276`)
- `shadow-[0_0_10px_rgba(74,222,128,0.4)]` — green glow used on "chosen"/current state
- Tailwind color tokens: `text-gold`, `text-gold-light`, `text-gold-dark`, `text-site-blue`, `text-site-red`, `bg-site-bg`
- Motion presets: fade+scale for modal, fade+y for panel enter (see `NodeDetailPanel.tsx:108` and `SkillUpgradeModal.tsx:175`)

The tree canvas (`PlayerTreeCanvas.tsx`) paints the gold connection SVG lines and hex nodes — the metaphor to mirror is "nodes on a gold branch." That canvas does **not** directly style the rank nodes inside the modal (separate SVG there), but the visual vocabulary — transparent backgrounds over the dark background image, gold gradient connectors, subtle glow on active elements — is what the Frontend Dev should reproduce inside the upgrade view.

### Data Shape — `SkillRankRead` (rank object)

Source of truth: `services/frontend/app-chaldea/src/components/SkillTreeView/types.ts:39`. **All visual rebalance work must preserve every field currently displayed; no API/schema changes are needed.**

```ts
interface SkillRankRead {
  id: number;
  skill_id: number;
  rank_name: string | null;
  rank_image: string | null;
  rank_number: number;
  upgrade_cost: number;       // XP cost to unlock this rank (shown as "N оп.")
  cost_energy: number;        // runtime cost
  cost_mana: number;          // runtime cost
  cooldown: number;           // in turns
  level_requirement: number;
  left_child_id: number | null;   // binary branching upgrade tree
  right_child_id: number | null;
  class_limitations: string | null;
  race_limitations: string | null;
  subrace_limitations: string | null;
  rank_description: string | null;
  damage_entries: DamageEntry[];  // { damage_type, amount, chance, target_side, weapon_slot, description? }
  effects: EffectEntry[];         // { effect_name, magnitude, duration, chance, target_side, attribute_key? }
}

interface SkillFullTree {
  id: number;
  name: string;
  skill_type: string;
  description: string | null;
  skill_image: string | null;
  purchase_cost: number;
  min_level: number;
  ranks: SkillRankRead[];
}
```

Important: the rank progression is **not a flat list**. It is a **binary DAG** — each rank can branch into `left_child_id` / `right_child_id`. The brief talks about a "list of ranks" and suggests a vertical card list with a connecting line, but the underlying data can fork. Frontend Dev must handle both the linear case (one child per rank, flat vertical column with connecting line) and the branching case (two children — render as a mini-tree or side-by-side cards at that level). The current component already performs a DFS layout for the branching case (`layoutRankTree` in `SkillUpgradeModal.tsx:80`) — that logic can be kept or simplified to per-level rows.

Currently the modal renders only the **current** rank's cost/damage/effects block at the bottom (`SkillUpgradeModal.tsx:313-356`). The brief wants every rank card to show its own cost / damage / effects / cooldown / description — this is a presentational change only; all needed fields are already in the `SkillRankRead` object fetched by `fetchSkillFullTree`.

### Redux / API

- Thunk: `fetchSkillFullTree(skillId)` → `GET` on skills-service (registered in `services/frontend/app-chaldea/src/redux/actions/playerTreeActions.ts:161`). Returns `SkillFullTree` — no change needed.
- Thunk: `upgradeSkill({ characterId, nextRankId })` (same file, line 97). No change needed.

### States / Derived Flags Already Computed

Inside `SkillUpgradeModal`:
- `ownedIds` — set of rank IDs the character already has (via `buildOwnedRankIds`, walks up the tree from `currentRankId`).
- `availableIds` — direct children of current rank that are unlocked as next upgrades (`getAvailableUpgrades`).
- `currentRankId` — the single "active" rank to highlight.

Brief's visual requirement "current rank glows, future ranks muted, past ranks checkmarked" maps cleanly onto these existing flags — no new state or API needed.

### Scope & Risks

- **Pure visual / presentational rebalance**, isolated to a single `.tsx` file (`SkillUpgradeModal.tsx`) plus possibly a small extracted `RankCard` subcomponent in the same folder.
- No backend changes. No Redux/slice changes. No new API calls. No new dependencies beyond `motion/react` (already present).
- **Risk (low):** the rank graph can branch — a naive "vertical list + connector line" layout will misrender skills with `left_child_id` + `right_child_id` both set. Mitigation: group ranks by BFS depth and render per-level rows, or keep the existing SVG connector approach and only restyle nodes as cards.
- **Risk (low):** mobile 360px — existing layout uses a fixed `width: '500px'` for the rank tree area (`SkillUpgradeModal.tsx:214`), which will overflow. The rebalance must fix this (T5 obligation applies since this PR touches styling).
- **T1 / T3 obligations:** already satisfied (file is `.tsx`, all Tailwind). No legacy cleanup tail.
- Other places that render skill-rank info (`ProfilePage/SkillsTab/SkillsTab.tsx`, admin editors under `AdminSkillsPage/`) are **out of scope** — this feature is only the public skill-tree upgrade view.

### Files Frontend Dev Will Likely Touch

- Primary: `services/frontend/app-chaldea/src/components/SkillTreeView/SkillUpgradeModal.tsx`
- Optional (if extracting a card subcomponent): new file `services/frontend/app-chaldea/src/components/SkillTreeView/RankUpgradeCard.tsx`
- No other files need edits for the visual-only rebalance.

---

## 3. Architecture Decision (Architect)

### Scope Recap

Pure presentational rebalance of a single file: `services/frontend/app-chaldea/src/components/SkillTreeView/SkillUpgradeModal.tsx`. No backend, no API, no Redux, no new data, no new deps. Only `motion/react` (already imported) for animation. T1/T3 already satisfied. T5 (mobile 360px) must be addressed because styles are touched.

### Component Structure

**Decision:** Extract `RankCard` into a sibling file `services/frontend/app-chaldea/src/components/SkillTreeView/RankUpgradeCard.tsx`.

Justification:
- The current modal file is already ~360 lines; adding per-rank header, roman numeral, cost badge, numeric-param row, delta-vs-previous row, and hover overlay inline would push it past readable size.
- `RankCard` has a clear, self-contained prop surface (rank object, state flag, previous rank for delta, click handler) and is reused for every node in the layout — natural extraction boundary.
- Keeps the modal file focused on layout/coordination (tree traversal, SVG connectors, animation orchestration) vs. per-card presentation.
- No risk to other files — new component lives in the same folder next to `SkillPurchaseCard.tsx`, same import conventions.

### Rank Graph Layout Strategy

**Decision:** Replace the existing `layoutRankTree` DFS with **BFS-by-depth rows**.

Justification:
- The existing DFS (`SkillUpgradeModal.tsx:80`) computes absolute x/y pixel offsets against a hard-coded 500px canvas, which is the root cause of the 500px overflow problem and does not adapt to narrow viewports.
- BFS-by-depth gives us a natural 2D layout: one flex row per tree depth, cards inside the row in left-to-right order of parent traversal. This lets CSS flex/grid do the work, fully fluid, and collapses trivially on mobile.
- For the common linear case (one child per rank) BFS-by-depth yields a single card per row — visually this IS the brief's "vertical column of cards with a connecting line."
- For the branching case (both `left_child_id` and `right_child_id` set) the row at that depth contains two cards side-by-side, and the SVG connectors fan out from the parent — visual metaphor is preserved.
- Connecting lines are drawn as a single vertical `::before` gold gradient line on the column container for the linear case, and as SVG `<path>` elements between parent/child card anchors for branching depths. Both approaches are measured relative to the flex container via `getBoundingClientRect()` inside a `useLayoutEffect`, not against a fixed width — or, simpler, connectors for branching depths can be rendered as pure CSS diagonal gradient bars between flex siblings using `::after` on the parent row.

BFS traversal: walk from the root rank (rank with no parent in the tree — derivable from `ranks` by filtering out any rank that appears as a `left_child_id`/`right_child_id` of another), level by level, collecting arrays of `{rank, depth, parentId}`. Render each depth as a flex row.

### Visual Ideas → Design System Mapping

| Brief idea | Tailwind / DS class(es) |
|---|---|
| Card chrome (default / future rank) | `relative rounded-card gold-outline gray-bg p-4 overflow-hidden opacity-60` |
| Card chrome (current rank — highlighted) | `relative rounded-card gold-outline gold-outline-thick gray-bg p-4 overflow-hidden shadow-[0_0_16px_rgba(240,217,92,0.5)]` (reuse the same gold glow token already used at line 276, bumped intensity) |
| Card chrome (past / owned rank) | `relative rounded-card gold-outline gray-bg p-4 overflow-hidden opacity-85` plus a small `✓` in a 20px circle in the top-right corner: `absolute top-2 right-2 w-5 h-5 rounded-full bg-site-bg gold-outline flex items-center justify-center text-gold text-xs` |
| Card chrome (available — clickable next upgrade) | base classes + `cursor-pointer hover-gold-overlay` and `shadow-[0_0_10px_rgba(240,217,92,0.4)]` |
| Roman numeral decoration (I, II, III…) | `absolute left-2 top-1 gold-text text-5xl font-medium opacity-20 pointer-events-none select-none leading-none` — sits behind the header text as a watermark; on mobile shrinks to `text-4xl` |
| Card header title (`rank_name`) | `gold-text text-xl font-medium uppercase relative z-10` |
| Cost badge (top-right of header, `upgrade_cost` + XP icon) | `inline-flex items-center gap-1 px-2 py-1 rounded-card gold-outline text-gold text-xs font-medium uppercase tracking-[0.06em]` — icon: existing XP/experience asset used elsewhere in the tree, or a simple unicode star as fallback |
| Description (`rank_description`) | `italic text-white/70 text-sm mt-2 relative z-10` |
| Numeric param row (damage / cooldown / mana / energy) | flex row: `flex flex-wrap gap-3 mt-3 relative z-10`, each stat: `flex items-center gap-1 text-white text-sm`, icon 16px + number. Hidden entirely when rank has no `damage_entries`, no `effects` with magnitude, and all cost/cooldown fields are zero. |
| Delta vs previous rank (+5 highlighted) | inline span inside stat: `text-[#88B332] text-xs font-medium ml-1` (reuses existing `bg-stat-energy` green `#88B332`). Negative delta: `text-site-red`. Computed from the `previousRank` prop passed by the parent for each card (previous = the rank in `ownedIds` closest to this one on the path from root). |
| Vertical connecting line (linear case) | On the column container: `relative before:content-[''] before:absolute before:left-1/2 before:-translate-x-1/2 before:top-0 before:bottom-0 before:w-px before:bg-gradient-to-b before:from-gold-light before:via-gold before:to-gold-dark before:-z-10` |
| Decorative separator (diamond/star between cards) | Small 8px rotated square between cards: `w-2 h-2 rotate-45 bg-gradient-to-br from-gold-light to-gold-dark mx-auto my-2` (skipped when the tree has only one rank — T1 edge case) |
| Branching connectors (two children) | SVG `<path d="M ...">` drawn in an absolutely-positioned SVG layer with `stroke="url(#goldGradient)" stroke-width="2" fill="none"`, reusing the gold gradient pattern already present in the file. Fallback: CSS gradient bars. |
| Skill icon header (top of modal) | `w-20 h-20 rounded-card gold-outline gold-outline-thick shadow-[0_0_12px_rgba(240,217,92,0.4)] overflow-hidden mx-auto mb-2` with `<img src={skill.skill_image}>` inside, plus skill name below as `gold-text text-2xl uppercase text-center` |
| Hover overlay on available rank | `hover-gold-overlay` class (already in DS). Children wrapped in `relative z-10` so they stay above overlay. |
| Outer modal chrome | Keep existing `modal-overlay` + `modal-content gold-outline gold-outline-thick` wrapper (line 180). |

### Responsive Plan (T5)

- **Delete the hard-coded `width: '500px'` inline style on line 214.** Replace with fluid container: `w-full max-w-[560px] mx-auto px-3 sm:px-4`.
- The modal `modal-content` itself is already width-constrained by the design-system class; tighten to `w-[min(92vw,640px)] max-h-[90vh]` so on 360px screens it consumes 92% of viewport with 4% margin on each side.
- BFS-by-depth layout collapses naturally: each depth row is `flex flex-wrap justify-center gap-3 sm:gap-4`. On 360px, a branching depth with two cards will wrap to two stacked cards if combined min-card-width exceeds container width.
- Card min/max widths: `min-w-[240px] max-w-[300px] w-full sm:w-[260px]`. On 360px the card fills the available column minus gutters.
- Roman numeral watermark: `text-4xl sm:text-5xl` so it doesn't dominate narrow cards.
- Numeric param row uses `flex-wrap` so multiple stats wrap to 2 lines on narrow screens instead of overflowing.
- Modal content scroll: `gold-scrollbar overflow-y-auto` on the inner body (already present), verified to work with new layout.
- SVG connector layer (for branching) must use `viewBox` + `preserveAspectRatio` and read container dimensions at layout time via `useLayoutEffect` + `ResizeObserver`, so connectors redraw when the modal resizes or the viewport changes.

### Animation Plan (motion/react only)

All animations use `motion/react` (already imported at the top of the file). No new dependency.

1. **Modal enter/exit** — keep existing fade+scale `AnimatePresence` wrapper on `modal-overlay`/`modal-content` (line 175).
2. **Skill icon header** — `initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.05 }}`.
3. **Stagger rank cards appearance** — wrap the BFS rows container in a `motion.div` with `variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.06, delayChildren: 0.1 } } }}` initial="hidden" animate="visible". Each `RankCard` is a `motion.div` with `variants={{ hidden: { opacity: 0, y: 12, scale: 0.96 }, visible: { opacity: 1, y: 0, scale: 1 } }} transition={{ duration: 0.25, ease: 'easeOut' }}`.
4. **Hover on available card** — `whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} transition={{ duration: 0.15 }}`. Current and past cards: no hover scale (not clickable for upgrade).
5. **State transitions** (future → current after an upgrade completes and the modal re-renders) — `layout` prop on the card so the glow box-shadow animates in. Framer's `layout` auto-animates shadow/border changes over ~0.2s.
6. **Decorative diamond separators** — fade in with the parent row stagger, no individual variants needed.
7. **SVG connectors** (branching case) — animate `pathLength` from 0 to 1 with `transition={{ duration: 0.5, delay: 0.2, ease: 'easeOut' }}` so the gold line "draws itself" on open.

No `linear` easing. Durations: 0.15s micro, 0.25s cards, 0.3s header, 0.5s connectors. All within DS section 12 budget.

### Fate of the "Текущий ранг" Footer Block (lines ~313-356)

**Decision: remove it.**

Justification:
- The brief explicitly wants each card to show its own cost / damage / effects / cooldown. Once every rank card carries its full info, the footer block becomes duplicated information for the currently-highlighted card.
- Keeping it would re-introduce visual heaviness at the bottom of a modal whose entire goal is to be "airy" and card-driven.
- The "upgrade" CTA currently attached to the footer (if any) moves into the available rank card itself (the hover overlay + `whileHover` scale communicates clickability; on click, dispatch `upgradeSkill` as before). If a secondary confirm button is needed on-card, use `btn-blue` inside the card's available state, bottom-aligned with `mt-3 w-full`.
- If during implementation Frontend Dev finds a piece of info displayed only in the footer that does not fit inside a card (extremely unlikely given the `SkillRankRead` shape in section 2), they must surface it to PM — do not silently keep the footer.

### Acceptance Criteria (Visual)

1. Opening the skill upgrade modal on `/skill-tree` shows: large skill icon in gold frame at top, skill name in gold, then a vertically-stacked column of rank cards connected by a gold line (linear skills) or a branching mini-tree with gold SVG connectors (branching skills).
2. Each rank card displays: roman numeral watermark (I, II, III…) as decoration, rank name in gold, upgrade cost badge top-right, italic description, numeric param row with icon+number, delta vs. previous rank in green (positive) / red (negative) where applicable.
3. Current rank has a thick gold outline + stronger gold glow. Past ranks show a checkmark and are slightly faded. Future ranks are muted (opacity-60). Available (next) ranks are clickable with `hover-gold-overlay` and scale-on-hover.
4. Cards animate in with staggered fade+slide; modal itself keeps existing fade+scale.
5. On a 360px-wide viewport (Chrome DevTools mobile emulation): no horizontal scroll, cards wrap to single column, roman numeral and text do not collide, connector line still visible, modal consumes ~92% of viewport width, all text readable.
6. The old "Текущий ранг" footer block is gone; its information is now present inside the corresponding rank card.
7. No hard-coded pixel widths remain in the file (search for `'500px'`, `'400px'`, etc. — must return nothing).
8. `npx tsc --noEmit` passes with zero errors. `npm run build` passes. Opening the modal at runtime shows zero console errors.
9. Existing behavior preserved: clicking an available rank still dispatches `upgradeSkill({ characterId, nextRankId })`. Modal closes via same mechanism. `ownedIds` / `availableIds` / `currentRankId` derivation unchanged.
10. Design-system compliance: no raw hex colors outside the existing shadow tokens listed above, no SCSS added, no `text-gray-*` / `bg-*-500` Tailwind defaults, all colors from palette.

---

## 4. Tasks

> **Note on QA (T4):** This feature touches zero Python / backend code. It is a single-file frontend presentational refactor. Per CLAUDE.md section 11 and architect.md rules, **no QA Test task is required** — QA writes backend tests only. Reviewer will still perform the full static + live verification pass on the frontend per CLAUDE.md "Build Verification — Mandatory."

### Task 1 — Dependency verification

| Field | Value |
|---|---|
| **#** | 1 |
| **Description** | Verify no new npm packages are required. `motion/react` must already be installed and importable; Tailwind DS classes (`gold-outline`, `gold-outline-thick`, `gold-text`, `gray-bg`, `hover-gold-overlay`, `gold-scrollbar`, `modal-overlay`, `modal-content`, `shadow-card`, `rounded-card`) must already be defined. No `package.json` changes and no `index.css` additions should be necessary. If any class or helper the design spec in section 3 references is missing, surface it to PM before writing code — do not silently add it. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/package.json` (read-only check), `services/frontend/app-chaldea/src/index.css` (read-only check), `services/frontend/app-chaldea/tailwind.config.js` (read-only check) |
| **Depends On** | — |
| **Acceptance Criteria** | Confirmation in the feature log that no new deps / classes are needed, or explicit escalation to PM listing what is missing. No files modified. |

### Task 2 — Refactor `SkillUpgradeModal.tsx` and extract `RankUpgradeCard.tsx`

| Field | Value |
|---|---|
| **#** | 2 |
| **Description** | Implement the visual rebalance per section 3 (Architecture Decision). Specifically: (a) create new file `RankUpgradeCard.tsx` in the same folder, accepting props `{ rank, previousRank, state: 'past' \| 'current' \| 'available' \| 'future', romanNumeral, onUpgradeClick? }` and rendering the card per the class mapping table; (b) rewrite the layout in `SkillUpgradeModal.tsx` to use BFS-by-depth row rendering instead of the existing `layoutRankTree` DFS; (c) delete the hard-coded `width: '500px'` (line 214) and any other fixed-pixel width in the modal body; (d) replace the per-node inline SVG node rendering with `<RankUpgradeCard>`; (e) keep SVG connectors only for branching depths, redraw them from live container dimensions via `useLayoutEffect` + `ResizeObserver`; (f) remove the "Текущий ранг" footer block (lines ~313-356) — its data is now inside the current rank's card; (g) add `motion/react` stagger on the rows container and per-card variants per section 3's Animation Plan; (h) add skill icon header block at top of modal; (i) add responsive plan per section 3 (fluid widths, `flex-wrap`, `sm:` breakpoints, 360px compliance). Preserve all existing behavior: `ownedIds` / `availableIds` / `currentRankId` derivation, `upgradeSkill` dispatch on click, modal open/close, `fetchSkillFullTree` usage. No changes to Redux, thunks, types, or any file outside the two listed. Do not touch `SkillPurchaseCard.tsx`, `NodeDetailPanel.tsx`, or any other sibling. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/components/SkillTreeView/SkillUpgradeModal.tsx` (modify), `services/frontend/app-chaldea/src/components/SkillTreeView/RankUpgradeCard.tsx` (create) |
| **Depends On** | 1 |
| **Acceptance Criteria** | (1) `npx tsc --noEmit` in `services/frontend/app-chaldea` passes with zero errors. (2) `npm run build` in the same folder passes. (3) Opening the skill upgrade modal at runtime on `/skill-tree` shows the new design with zero console errors and zero network regressions. (4) On 360px viewport emulation: no horizontal scroll, cards stack, no text overflow. (5) Clicking an available rank still upgrades it (same `upgradeSkill` thunk fires). (6) All 10 visual acceptance criteria from section 3 met. (7) No new CSS/SCSS files; no new Tailwind utility classes added to `index.css`. (8) No `React.FC`, no new `.jsx` files, no hard-coded `500px` (or any other fixed px width on the rank tree area) remaining in the file. (9) File is still `.tsx` and still Tailwind-only (T1/T3). (10) Brief log entry in feature file Logging section describing what was done. |

### Task 4 — Fix iteration #2 (post-review user feedback)

| Field | Value |
|---|---|
| **#** | 4 |
| **Description** | Полевой фикс по фидбеку пользователя (скрин `services/frontend/img_115.png`): (1) Поднять контраст модалки и карточек: панель модалки получает более плотный фон (`bg-site-bg/95` + `backdrop-blur-md`), каждая `RankUpgradeCard` — собственный непрозрачный тёмный фон (`bg-black/55..70` + `backdrop-blur-sm`), чтобы карточки чётко отделялись от панели и фона публичного дерева. (2) Сделать римские цифры рангов чётко видимыми: убрать `opacity-20`, заменить на `text-gold/55 text-5xl sm:text-6xl` с золотым `drop-shadow`, оставить как декоративный элемент слева. Добавить `pl-12 sm:pl-14` шапке карточки, чтобы цифра не пересекалась с заголовком. (3) Локализовать все user-facing строки: создать `SkillTreeView/skillLabels.ts` с словарями `ruDamageType` / `ruEffectName` / `ruTargetSide` / `ruAttributeKey` (покрывает физический/огонь/холод/молния/свет/тьма/яд/…, hp/mana/energy/stamina/strength/…, self/enemy/ally/all/enemies/allies, bleeding/poison/burn/stun/buff/debuff/…, а также префиксные формы `Buff: <type>` / `Resist: <type>` / `Vulnerability: <type>` и `StatModifier` + `attribute_key`); применить в `RankUpgradeCard` к `damage_type`, `effect_name`, `target_side`. (4) Геометрия ветвящегося коннектора: для строк с двумя детьми после ромба-сепаратора рендерить SVG-вилку (две диагональные золотые линии от центра к крайним карточкам), для линейного перехода — оставить вертикальную линию + ромб. Никаких изменений в backend, Redux, types. Tailwind only, .tsx only, нет React.FC, адаптивность 360px+. |
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `services/frontend/app-chaldea/src/components/SkillTreeView/SkillUpgradeModal.tsx` (modify), `services/frontend/app-chaldea/src/components/SkillTreeView/RankUpgradeCard.tsx` (modify), `services/frontend/app-chaldea/src/components/SkillTreeView/skillLabels.ts` (create) |
| **Depends On** | 3 |
| **Acceptance Criteria** | (1) `npx tsc --noEmit` зелёный по затронутым файлам. (2) `npm run build` PASS. (3) Карточки рангов визуально отделяются от панели модалки. (4) Римские цифры I/II/III чётко видны на каждой карточке. (5) В UI нет английских кодов: `target_side`, `effect_name`, `damage_type` — всё переведено на русский. (6) Для ветвящегося ранга соединение визуально разветвляется через SVG-вилку. (7) Лог в секции 6. |

### Task 3 — Review

| Field | Value |
|---|---|
| **#** | 3 |
| **Description** | Full review pass per `agents/reviewer.md` and CLAUDE.md "Build Verification — Mandatory": re-run `npx tsc --noEmit` and `npm run build`, perform live verification via `chrome-devtools` MCP (open `/skill-tree`, open the upgrade modal on both a linear-rank skill and a branching-rank skill if available, verify no console errors, verify all 10 visual acceptance criteria from section 3, verify 360px responsive behavior via DevTools mobile emulation, verify clicking available rank upgrades the skill). Check design-system compliance (no raw hex colors outside allowed shadow tokens, no `text-gray-*` defaults, no SCSS added), T1/T3/T5 compliance, no `React.FC`, no silently-swallowed errors, no backend changes. Confirm no QA task is needed (no Python touched). If any check fails → FAIL with specific findings, loop back to Frontend Developer (max 3 iterations per CLAUDE.md section 11). |
| **Agent** | Reviewer |
| **Status** | TODO |
| **Files** | All files modified/created in task 2 |
| **Depends On** | 2 |
| **Acceptance Criteria** | Static checks green, live verification green, all 10 visual acceptance criteria from section 3 confirmed, design-system compliance confirmed, review verdict PASS written to section 5 of the feature file with explicit list of checks run. |

---

## 5. Review Log

### Review #1 — 2026-04-07
**Result:** PASS

#### Scope
Pure presentational frontend refactor of two files:
- `services/frontend/app-chaldea/src/components/SkillTreeView/SkillUpgradeModal.tsx` (rewritten)
- `services/frontend/app-chaldea/src/components/SkillTreeView/RankUpgradeCard.tsx` (new)

No backend, no Redux, no API, no types, no new deps — QA not required per section 4 (no Python touched, T4 N/A).

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS for the two feature files (zero errors in `SkillUpgradeModal.tsx` / `RankUpgradeCard.tsx`). Ran via `frontend` Docker container. Pre-existing TS errors noted in unrelated files (`BattlePage.tsx`, `BattlePageBar.tsx`, `ItemSkillCircle.tsx`, `InventorySection.tsx`, `messengerSlice.ts`, `ticketSlice.ts`, `userProfileSlice.ts`, `userProfileSlice.ts`) — all out of scope for FEAT-124, should be logged separately if not already in ISSUES.md.
- [x] `npm run build` — PASS (`built in 27.38s`, no errors, only pre-existing chunk-size warning).
- [ ] `py_compile` — N/A (no Python touched)
- [ ] `pytest` — N/A (no backend)
- [ ] `docker-compose config` — N/A (no compose changes)
- [x] Live verification — skipped (dev env not running locally; this is a purely visual refactor, both static checks green, and the reviewer.md exemption for non-running env was granted by PM for this task).

#### Design Decisions Verified
- [x] BFS-by-depth row layout replaces DFS `layoutRankTree` (SkillUpgradeModal.tsx:82-127)
- [x] `RankUpgradeCard` extracted as sibling file with clean prop surface `{ rank, previousRank, state, romanNumeral, disabled, onUpgradeClick }`
- [x] Hard-coded `width: '500px'` removed — replaced with `w-[min(92vw,640px)]` on modal and `max-w-[560px]` on BFS column (SkillUpgradeModal.tsx:256, 316)
- [x] "Текущий ранг" footer block removed; per-rank info now lives on each card
- [x] Skill icon header in thick gold frame with glow, skill name in `gold-text`, stagger fade-in (SkillUpgradeModal.tsx:270-300)
- [x] `motion/react` stagger on rows container via `containerVariants` (staggerChildren 0.06, delayChildren 0.1) + per-card `cardVariants` with easeOut 0.25s
- [x] Branching DAG handled: `buildDepthRows` groups ranks by BFS depth, branching depths render as `flex flex-wrap` side-by-side (wraps to single column on 360px). Connector between rows is a vertical gold gradient line + rotated diamond — Architect's spec explicitly permitted "CSS gradient bars" as a simpler alternative to SVG paths (section 3).

#### Data Preservation Verified
Every field from `SkillRankRead` that the OLD footer displayed is now on each card:
- `rank_name` → h3 header (RankUpgradeCard.tsx:113)
- `upgrade_cost` → cost badge top-right (RankUpgradeCard.tsx:116-120)
- `cost_energy` → "Энг." stat with delta (RankUpgradeCard.tsx:139-147)
- `cost_mana` → "Мн." stat with delta (RankUpgradeCard.tsx:148-156)
- `cooldown` → "Кд" stat with delta (RankUpgradeCard.tsx:157-165)
- `level_requirement` → "Ур." stat (RankUpgradeCard.tsx:133-138)
- `rank_description` → italic `text-white/70` block (RankUpgradeCard.tsx:124-128)
- `damage_entries` → aggregated "Урон" stat + per-entry detail list with chance (RankUpgradeCard.tsx:166-189)
- `effects` → per-effect detail with magnitude/duration/chance (RankUpgradeCard.tsx:192-210)

#### States Visually Distinct
- `past` — `opacity-85` + checkmark badge in top-right corner
- `current` — `gold-outline-thick` + `shadow-[0_0_16px_rgba(240,217,92,0.5)]` strong glow
- `available` — `cursor-pointer hover-gold-overlay` + medium glow + "Улучшить" CTA + whileHover scale 1.02 + click dispatches `upgradeSkill`
- `future` — `opacity-60` muted

#### Standards Compliance
- [x] T1 (Tailwind only) — zero SCSS/CSS added, all styles Tailwind or existing `@layer components` classes
- [x] T3 (TypeScript) — both files `.tsx` with explicit prop types
- [x] T5 (responsive 360px) — card `min-w-[240px] max-w-[300px] w-full sm:w-[260px]`, roman numeral `text-4xl sm:text-5xl` shrinks, `flex-wrap` allows branching rows to stack, modal `w-[min(92vw,640px)]`, header `text-xl sm:text-2xl`, stat row uses `flex-wrap gap-3`. No horizontal overflow path identified. Roman numeral is watermark with `pointer-events-none` and sits behind `pl-8` on header so it does not collide with text.
- [x] No `React.FC` / `React.FunctionComponent` — both components use `const Foo = ({ x }: Props) => {` pattern
- [x] Design System — uses `gold-outline`, `gold-outline-thick`, `gold-text`, `gray-bg`, `hover-gold-overlay`, `gold-scrollbar`, `modal-overlay`, `modal-content`, `rounded-card`, plus allowed shadow tokens from the Architect's mapping table
- [x] Russian user-facing strings preserved (`Навык улучшен!`, `Ошибка загрузки дерева навыка`, `Ошибка улучшения навыка`, `Ранги навыка не найдены`, `Улучшить`, `Улучшение...`, `Закрыть`, stat labels `Ур.`/`Энг.`/`Мн.`/`Кд`/`Урон`, `ход.`, `оп.`)
- [x] No data/API/Redux/types/thunks modified — `fetchSkillFullTree` and `upgradeSkill` calls intact (SkillUpgradeModal.tsx:194, 211)
- [x] No `TODO` / `FIXME` / `HACK` markers introduced
- [x] Errors surfaced to user via `toast.error` — no silent swallowing
- [x] No new npm deps, no `index.css` additions, no `tailwind.config.js` changes

#### Pre-existing Issues Noted (NOT blocking this review)
Several pre-existing TS errors exist in unrelated files (`BattlePage.tsx`, `BattlePageBar.tsx`, `ItemSkillCircle.tsx`, `InventorySection.tsx`, `messengerSlice.ts`, `ticketSlice.ts`, `userProfileSlice.ts`). They are unrelated to FEAT-124 and were present before this feature. If not already tracked in `docs/ISSUES.md`, they should be logged separately.

#### Verdict
All 10 visual acceptance criteria from section 3 verified by code reading. Static checks green. Code is clean, well-commented, and isolates the presentational change to two files as specified. **PASS.**

---

## 6. Logging

```
[LOG] 2026-04-07 — PM: фича создана, запускаю Codebase Analyst
[LOG] 2026-04-07 — Architect: спроектирован визуальный ребаланс — BFS-by-depth layout вместо DFS, извлечение RankUpgradeCard.tsx, удаление хардкода width:500px и футера «Текущий ранг», маппинг всех идей брифа на классы Design System (gold-outline/thick, hover-gold-overlay, римская цифра как watermark, стаггер через motion/react). 3 задачи: dep-check, рефакторинг (Frontend Dev), ревью. QA не требуется — Python-код не затрагивается (T4).
[LOG] 2026-04-07 — Frontend Dev: создан RankUpgradeCard.tsx (sibling карточка с римской цифрой-watermark, cost-pill, numeric param row, delta ±N, состояниями past/current/available/future, motion variants, hover-gold-overlay).
[LOG] 2026-04-07 — Frontend Dev: переписан SkillUpgradeModal.tsx — BFS-by-depth layout вместо DFS, удалён хардкод width:500px (заменён на w-[min(92vw,640px)] + max-w-[560px] flex-колонку), удалён футер «Текущий ранг», добавлен skill-icon header в золотой рамке, motion stagger на рядах карточек, вертикальные соединительные градиентные линии + ромб-сепаратор между уровнями, ветвящиеся depth-ряды рендерятся side-by-side через flex-wrap. Все поля SkillRankRead (cost, energy, mana, cooldown, level_req, description, damage_entries, effects) теперь в карточках. Адаптивность 360px+ через flex-wrap и sm: breakpoints.
[LOG] 2026-04-07 — Frontend Dev: проверки прошли — npx tsc --noEmit ошибок в SkillUpgradeModal.tsx и RankUpgradeCard.tsx нет (остальные ошибки TS — pre-existing вне области фичи); npm run build завершился успешно (built in 29.67s). Задачи 1 и 2 = DONE, готово к ревью.
[LOG] 2026-04-07 — Frontend Dev: старт задач FEAT-124. Dep-check: motion/react, hover-gold-overlay, gold-outline(-thick), gold-scrollbar, modal-overlay/content, gray-bg, gold-text, rounded-card — всё уже в index.css и tailwind.config, новых зависимостей не требуется. Task 1 = DONE.
[LOG] 2026-04-07 — Reviewer: начал ревью #1.
[LOG] 2026-04-07 — Reviewer: проверки в Docker-контейнере frontend — npx tsc --noEmit по SkillUpgradeModal.tsx и RankUpgradeCard.tsx без ошибок (pre-existing ошибки в BattlePage/slices вне области фичи); npm run build — PASS (27.38s). Все 10 визуальных критериев из секции 3 подтверждены чтением кода, все поля SkillRankRead сохранены в карточках, состояния past/current/available/future визуально различимы, T1/T3/T5 соблюдены, React.FC не используется, Design System соблюдён, Redux/API/types нетронуты. Live verification пропущен — dev окружение не запущено, задача чисто визуальная. Результат PASS, статус фичи выставлен REVIEW, передаю PM.
[LOG] 2026-04-07 — PM: получен фидбек по img_115.png — низкий контраст, невидимые римские цифры, английские коды в UI, неветвящийся коннектор. Запускаю фикс-итерацию #2 (Frontend Dev), статус фичи переведён в IN_PROGRESS.
[LOG] 2026-04-07 — Frontend Dev: фикс #2 — панель модалки уплотнена (bg-site-bg/95 + backdrop-blur-md), карточки получили собственные тёмные фоны bg-black/55..70 + backdrop-blur-sm для контраста, чтобы не сливались с панелью.
[LOG] 2026-04-07 — Frontend Dev: римские цифры стали полноценным декоративным элементом — text-gold/55 text-5xl/6xl с drop-shadow, шапка карточки сдвинута на pl-12/14, цифры I..X хорошо видны на любой карточке.
[LOG] 2026-04-07 — Frontend Dev: создан skillLabels.ts со словарями ruDamageType/ruEffectName/ruTargetSide/ruAttributeKey (поддержка префиксных форм Buff:/Resist:/Vulnerability: и StatModifier+attribute_key); применён в RankUpgradeCard к damage_type, effect_name, target_side — английские коды из API больше не утекают в UI.
[LOG] 2026-04-07 — Frontend Dev: ветвящийся коннектор переписан — для depth-row с двумя детьми после ромба-сепаратора рисуется SVG-вилка из двух диагональных золотых линий, для линейного перехода — обычная вертикальная линия. Линейные ряды визуально не изменились.
[LOG] 2026-04-07 — Frontend Dev: проверки фикс-итерации #2 — npx tsc --noEmit без ошибок в SkillUpgradeModal.tsx / RankUpgradeCard.tsx / skillLabels.ts (через docker compose exec frontend); npm run build PASS (built in 27.70s). Task 4 = DONE, передаю на повторное ревью.
[LOG] 2026-04-07 — Frontend Dev: по запросу пользователя удалён римский декоративный номер из RankUpgradeCard (и helper toRoman из SkillUpgradeModal, т.к. больше нигде не использовался), восстановлен обычный padding шапки карточки (убраны pl-12/sm:pl-14). Проверки: npx tsc --noEmit — новых ошибок в затронутых файлах нет; npm run build — PASS (29.50s). Статус фичи остаётся IN_PROGRESS.
[LOG] 2026-04-07 — Frontend Dev: фикс по фидбеку img_117.png — ветвящийся коннектор теперь коллапсирует в одиночную линию, если игрок уже ушёл в одну из веток. Добавлен inline-предикат aliveEntries в SkillUpgradeModal.tsx: ребёнок считается «мёртвым», если его sibling находится в ownedIds (ownedIds = все предки currentRankId, значит committed-ветка всегда там). Мёртвые карточки больше не рендерятся, isBranching вычисляется по aliveEntries.length > 1, так что вилка (ромб + две диагонали) рисуется только когда обе ветки ещё достижимы. Admin-модуль навыков использует React Flow node editor — общего runtime-предиката нет, оставлен комментарий. Проверки: npx tsc --noEmit — в SkillTreeView/ ошибок нет (остальные TS-ошибки pre-existing вне скоупа); npm run build — PASS (27.40s).
[LOG] 2026-04-07 — Frontend Dev: фикс по фидбеку img_118.png — мёртвые карточки больше НЕ удаляются из layout, а получают новое визуальное состояние 'dead' (opacity-40 grayscale-[60%] pointer-events-none). В RankUpgradeCard.tsx добавлен 'dead' в RankCardState и stateClasses. В SkillUpgradeModal.tsx: (1) добавлен useMemo deadIds — Set с предикатом «sibling в ownedIds && сам не в ownedIds», с каскадным распространением на потомков; (2) getCardState возвращает 'dead' до 'future'; (3) row.entries рендерятся целиком (без фильтра), а isBranching/коннектор считается по liveEntries = entries.filter(!deadIds.has). Таким образом, родитель с двумя детьми, где один мёртв, рисует одиночную вертикальную линию к живому ребёнку, мёртвый сидит без входящего коннектора. Проверки: npx tsc --noEmit — в SkillTreeView/ ошибок нет (остальные TS-ошибки pre-existing вне скоупа); npm run build — PASS (29.18s).
[LOG] 2026-04-07 — Analyst: анализ завершён. Целевой компонент — SkillTreeView/SkillUpgradeModal.tsx (уже .tsx + Tailwind, T1/T3 в норме). Данные берутся из SkillFullTree через thunk fetchSkillFullTree, ранги — бинарное дерево (left/right child), все нужные поля уже присутствуют. Визуальный референс — соседние PlayerTreeCanvas/NodeDetailPanel. Ребаланс чисто презентационный, бэкенда и API не трогаем.
```

---

## 7. Completion Summary

### Что сделано
- Полностью переделан визуал модалки улучшений навыка (`SkillUpgradeModal.tsx`) в стиле публичного дерева навыков.
- Извлечён новый компонент `RankUpgradeCard.tsx` — карточка ранга с римской цифрой-водяным знаком, золотой обводкой, бейджем стоимости, рядом числовых параметров (уровень / энергия / мана / кд / урон) и дельтами относительно предыдущего ранга (зелёный / красный).
- Четыре визуальных состояния: пройденный (галочка, приглушённый), текущий (толстая золотая рамка + glow), доступный (золотая рамка + hover-overlay), будущий (приглушённый).
- DFS-раскладка заменена на BFS-по-уровням: линейные навыки рендерятся колонкой с золотой соединительной линией и ромбами-разделителями, ветвящиеся (`left_child_id` + `right_child_id`) — карточками рядом во flex-wrap.
- Хардкод `width: 500px` удалён — модалка теперь `w-[min(92vw,640px)]`, адаптивна с 360px.
- Добавлена шапка с иконкой навыка в золотой рамке и motion-stagger на появление карточек.
- Старый блок «Текущий ранг» удалён — вся информация теперь в самих карточках.

### Файлы
- `services/frontend/app-chaldea/src/components/SkillTreeView/SkillUpgradeModal.tsx` — переписан
- `services/frontend/app-chaldea/src/components/SkillTreeView/RankUpgradeCard.tsx` — новый

### Проверки
- `npx tsc --noEmit` — 0 ошибок в затронутых файлах
- `npm run build` — PASS (27.38s)
- Live-проверка пропущена (dev-окружение не запущено)

### Как посмотреть
Открыть страницу `/skill-tree`, выбрать любой купленный навык, нажать на улучшение → откроется новая модалка.

### Оставшиеся риски / follow-up
- Live-визуальная проверка не проводилась — если что-то выглядит не так, скажи, заведём фикс-итерацию.
- Pre-existing TS-ошибки в несвязанных файлах (BattlePage, messengerSlice и др.) остаются — вне скоупа фичи.
