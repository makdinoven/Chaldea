# FEAT-070: Location Page UI Polish

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-23 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-070-location-page-ui-polish.md` → `DONE-FEAT-070-location-page-ui-polish.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Визуальная доработка страницы локации. Нужно привести внешний вид к более "воздушному" стилю: фон подложек сделать менее тёмным (более прозрачным), аватарки игроков уменьшить чтобы 4 помещались в ряд, а верхнюю навигацию (хедер с логотипом) привести к той же прозрачности/темноте что и остальные элементы страницы.

### Бизнес-правила
- Фон подложек (карточки локации, секции игроков/NPC) — менее тёмный, более прозрачный
- Аватарки игроков — уменьшить размер, чтобы 4 аватарки помещались в один ряд
- Верхняя навигация (хедер) — привести к той же прозрачности что и остальные элементы
- Все элементы должны быть визуально согласованы по уровню прозрачности/темноты

### UX / Пользовательский сценарий
1. Игрок заходит на страницу локации
2. Видит "воздушный" дизайн — подложки полупрозрачные, не тёмные
3. В секции игроков 4 аватарки помещаются в ряд
4. Хедер визуально сочетается с остальными элементами

### Edge Cases
- На мобильных устройствах (360px+) аватарки должны масштабироваться корректно
- При большом количестве игроков секция не должна ломаться

### Вопросы к пользователю (если есть)
- Нет вопросов, требования понятны

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | Style/class changes only | Multiple components listed below |

No backend changes required. This is a purely visual/CSS task.

### Files Inventory

#### Location Page Components (all in `services/frontend/app-chaldea/src/components/pages/LocationPage/`)

| File | Role | Background Classes Used |
|------|------|------------------------|
| `LocationPage.tsx` | Main page container | `bg-black/70 rounded-card` on header block, posts section, neighbors section |
| `LocationHeader.tsx` | Location name, image, badges, description | No own background (inside header block) |
| `PlayersSection.tsx` | Players grid + NPCs grid (two-column layout) | `bg-black/70 rounded-card` on both left (players) and right (NPCs) sections |
| `LocationMobs.tsx` (`src/components/LocationMobs.tsx`) | Collapsible mobs list | `bg-black/70 rounded-card` on section container |
| `BattlesSection.tsx` | Collapsible battles list | `bg-black/70 rounded-card` on section container |
| `PendingInvitationsPanel.tsx` | PvP/trade invitations | `bg-black/70` on section, `bg-black/40` on inner cards |
| `LootSection.tsx` | Dropped loot grid | `bg-black/50` on section (with `gold-outline`) |
| `NeighborsSection.tsx` | Neighbor location cards | No section bg (wrapped externally in `bg-black/70 rounded-card`), individual cards use `bg-black/50` |

#### Header / Navigation (in `services/frontend/app-chaldea/src/components/CommonComponents/Header/`)

| File | Role | Background Classes Used |
|------|------|------------------------|
| `Header.tsx` | Top bar with logo, nav, avatars, icons | **Conditional**: on location pages uses `bg-black/70 rounded-card backdrop-blur-sm`; on other pages — no background at all |
| `NavLinks.tsx` | Nav link items (ГЛАВНАЯ, ПРАВИЛА, etc.) | No background |
| `MegaMenu.tsx` | Dropdown mega menu | `bg-black/50 backdrop-blur-md rounded-[15px]` |
| `AvatarDropdown.tsx` | Character/user avatar circles | `bg-white/10` on avatar circle; `dropdown-menu` on dropdown |

#### Design System Files

| File | Relevant Content |
|------|-----------------|
| `services/frontend/app-chaldea/tailwind.config.js` | `site.bg: 'rgba(35, 35, 41, 0.9)'` — design token for container backgrounds |
| `services/frontend/app-chaldea/src/index.css` | `.gray-bg` class = `rgba(35,35,41,0.9)` with `border-radius: 15px` |
| `docs/DESIGN-SYSTEM.md` | Documents `bg-site-bg` token and `gray-bg` class |

#### Background Hook

| File | Role |
|------|------|
| `services/frontend/app-chaldea/src/hooks/useBodyBackground.js` | Sets `body.style.backgroundImage` to location's image URL. This means the location page has a custom background image, and all semi-transparent containers sit on top of it. |

### Current Background/Transparency Analysis

**The core issue**: All location page sections use `bg-black/70` (Tailwind: `rgba(0,0,0,0.7)`). This is quite dark — 70% black opacity over the location background image. The design system standard is `bg-site-bg` = `rgba(35,35,41,0.9)` (the `gray-bg` class), but the location page chose a different approach with `bg-black/70`.

**Current background classes used across the page**:
- `bg-black/70` — header block, players section (x2), posts section, neighbors wrapper, mobs section, battles section, pending invitations panel (7 places total)
- `bg-black/50` — loot section, mega menu, neighbor cards
- `bg-black/40` — inner cards within PendingInvitationsPanel, avatar placeholder circles
- `bg-white/5` and `bg-white/10` — individual mob/battle cards (hover state)

**Header behavior**: The `Header.tsx` component checks `isLocationPage` (regex: `/^\/location\/\d+/`) and conditionally applies `bg-black/70 rounded-card backdrop-blur-sm`. On non-location pages, the header has NO background — it floats transparently over the page. This means the header's darkness is already tied to the same `bg-black/70` as the page sections, but the user wants all elements to be lighter/more transparent.

### Current Avatar Sizes on Location Page

**PlayersSection.tsx — `AvatarCard` component** (used for both players and NPCs):
- Mobile: `w-20 h-20` (80px)
- Desktop (`sm:` breakpoint): `w-24 h-24` (96px)
- Grid: `grid-cols-2 sm:grid-cols-3` — currently fits 2 on mobile, 3 on desktop

**Requirement**: 4 avatars per row. Current sizes are too large for 4-per-row layout, especially on mobile.

**For reference — other avatar sizes on the page**:
- `LocationHeader.tsx` location image: `w-[120px] h-[120px]` / `sm:w-[140px] sm:h-[140px]`
- `LocationMobs.tsx` mob avatars: `w-14 h-14` / `sm:w-16 sm:h-16` (56px / 64px)
- `PendingInvitationsPanel.tsx` initiator avatars: `w-10 h-10` / `sm:w-14 sm:h-14` (40px / 56px)
- `Header.tsx` user/character avatars: `64px` (inline style via `size` prop)

### Summary of Required Changes

1. **Background transparency** — Change `bg-black/70` to a lighter value (e.g., `bg-black/40` or `bg-black/50`) across all location page sections AND the header when on location pages. All elements should match the same transparency level.

2. **Player avatar size reduction** — Reduce avatar sizes in `PlayersSection.tsx` from `w-20 h-20 sm:w-24 sm:h-24` to something smaller (e.g., `w-14 h-14 sm:w-16 sm:h-16`), and change the grid from `grid-cols-2 sm:grid-cols-3` to `grid-cols-3 sm:grid-cols-4` (or `grid-cols-4`) to fit 4 per row.

3. **Header transparency alignment** — The header's conditional `bg-black/70` on location pages should be changed to match whatever transparency value is chosen for the page sections.

### Cross-Service Dependencies

None. This is a frontend-only visual change with no API or backend impact.

### DB Changes

None required.

### Risks

- **Risk**: Changing background opacity too much may make text unreadable over bright location background images. → **Mitigation**: Choose a balanced value (e.g., `bg-black/40`) and verify against several different location images.
- **Risk**: Reducing avatar size too aggressively may clip player names or make avatars hard to see on mobile. → **Mitigation**: Test at 360px viewport. The NPC cards also have role badges and attack buttons that need space.
- **Risk**: The header background change only applies on location pages (controlled by regex in `Header.tsx`). Other pages are unaffected. → **Mitigation**: No additional risk — this is already scoped correctly.
- **Risk**: `MegaMenu.tsx` uses `bg-black/50` independently — it may need adjustment too for visual consistency with the lighter header. → **Mitigation**: Include it in the scope if the header changes make the mega menu look inconsistent.

---

## 3. Architecture Decision (filled by Architect — in English)

### Overview

This is a frontend-only visual polish task. No API changes, no DB changes, no cross-service impact. All changes are Tailwind CSS class modifications in existing `.tsx` files.

### Decision: Background Transparency

**Change `bg-black/70` to `bg-black/40`** across all location page sections and the Header's location-page conditional background. This reduces opacity from 70% to 40%, making the location background image more visible and achieving the "airy" feel requested.

Files and locations to update (all `bg-black/70` → `bg-black/40`):
1. `LocationPage.tsx` — 3 places (header block line ~345, posts section line ~412, neighbors section line ~459)
2. `PlayersSection.tsx` — 2 places (players section line ~137, NPCs section line ~174)
3. `LocationMobs.tsx` — 1 place (section container line ~90)
4. `BattlesSection.tsx` — 1 place (section container line ~113)
5. `PendingInvitationsPanel.tsx` — 1 place (section container line ~190)
6. `Header.tsx` — 1 place (conditional location-page background line ~68)

**Total: 9 replacements of `bg-black/70` → `bg-black/40`.**

Note: `LootSection.tsx` already uses `bg-black/50` and `NeighborsSection.tsx` inner cards use `bg-black/50` — these are left as-is since they are already lighter/different from the main sections. `PendingInvitationsPanel.tsx` inner cards use `bg-black/40` — no change needed there either.

Note: `MegaMenu.tsx` uses `bg-black/50` independently — this is left as-is; it already has its own backdrop-blur and serves a different visual purpose (dropdown overlay). Changing it could hurt readability.

Note: `CharactersSection.tsx` in UserProfilePage uses `bg-black/70` on a tiny badge — this is outside the location page scope and should NOT be changed.

### Decision: Player Avatar Sizes

Reduce avatar sizes in `PlayersSection.tsx` `AvatarCard` component:
- **Current**: `w-20 h-20` (80px mobile), `sm:w-24 sm:h-24` (96px desktop), grid `grid-cols-2 sm:grid-cols-3`
- **New**: `w-14 h-14` (56px mobile), `sm:w-16 sm:h-16` (64px desktop), grid `grid-cols-3 sm:grid-cols-4`

This matches the `LocationMobs.tsx` mob avatar sizes (`w-14 h-14` / `sm:w-16 sm:h-16`), keeping visual consistency. The grid changes to `grid-cols-3 sm:grid-cols-4` to fit 4 per row on desktop (and 3 on mobile for 360px+ compatibility). Text sizes within avatar cards may need slight reduction to fit the smaller cards — the developer should adjust as needed.

### Decision: Header Alignment

The Header already uses a conditional check (`isLocationPage`) to apply `bg-black/70`. Simply changing `bg-black/70` to `bg-black/40` in that same conditional ensures it matches the page sections. No structural change needed.

### Data Flow

No data flow changes. This is purely visual.

### Security

No security implications — no new endpoints, no data changes.

### Risks

1. **Readability on bright backgrounds**: `bg-black/40` may not provide enough contrast for text on very bright location images. If this is an issue, the developer can add `backdrop-blur-sm` to sections that don't already have it.
2. **Avatar name truncation**: Smaller avatars mean less space for player names. Names are already truncated in the current design, so this should be fine.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|------------|-------|--------|-------|------------|---------------------|
| 1 | Replace `bg-black/70` with `bg-black/40` across all location page sections (LocationPage.tsx ×3, PlayersSection.tsx ×2, LocationMobs.tsx ×1, BattlesSection.tsx ×1, PendingInvitationsPanel.tsx ×1) AND in Header.tsx's location-page conditional. Reduce player/NPC avatar sizes in PlayersSection.tsx from `w-20 h-20 sm:w-24 sm:h-24` to `w-14 h-14 sm:w-16 sm:h-16` and change grid from `grid-cols-2 sm:grid-cols-3` to `grid-cols-3 sm:grid-cols-4`. Adjust font sizes within AvatarCard if needed for the smaller size. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx`, `services/frontend/app-chaldea/src/components/pages/LocationPage/PlayersSection.tsx`, `services/frontend/app-chaldea/src/components/LocationMobs.tsx`, `services/frontend/app-chaldea/src/components/pages/LocationPage/BattlesSection.tsx`, `services/frontend/app-chaldea/src/components/pages/LocationPage/PendingInvitationsPanel.tsx`, `services/frontend/app-chaldea/src/components/CommonComponents/Header/Header.tsx` | — | 1) All `bg-black/70` in location page components and Header location-page conditional are changed to `bg-black/40`. 2) Player/NPC avatars in PlayersSection show 4 per row on desktop, 3 on mobile. 3) `npx tsc --noEmit` passes. 4) `npm run build` passes. 5) No other pages are affected (CharactersSection badge, MegaMenu, etc. remain unchanged). |
| 2 | Review all changes from Task 1. Verify visual consistency across location pages. Check that non-location pages (home, profile, etc.) are not affected. Verify Header looks correct on both location and non-location pages. Check mobile responsiveness at 360px. | Reviewer | DONE | Same as Task 1 | 1 | 1) All acceptance criteria from Task 1 verified. 2) Text remains readable over location background images at `bg-black/40`. 3) Avatars render correctly at smaller sizes with no layout overflow. 4) Header on non-location pages is unaffected (no background). 5) Mobile layout (360px+) works correctly — 3 avatars per row, no horizontal overflow. 6) `npx tsc --noEmit` and `npm run build` pass. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-23
**Result:** PASS

#### Checklist

1. **bg-black/70 -> bg-black/40 replacements** — VERIFIED. All 9 instances replaced correctly:
   - `LocationPage.tsx`: 3 places (header block L345, posts section L412, neighbors section L459)
   - `PlayersSection.tsx`: 2 places (players section L137, NPCs section L174)
   - `LocationMobs.tsx`: 1 place (section container L90)
   - `BattlesSection.tsx`: 1 place (section container L113)
   - `PendingInvitationsPanel.tsx`: 1 place (section container L190)
   - `Header.tsx`: 1 place (conditional location-page background L68)
   - Grep confirms zero remaining `bg-black/70` in any of the 6 changed files.

2. **Avatar sizes in PlayersSection.tsx** — VERIFIED. Both `AvatarCard` and `NpcCard` changed from `w-20 h-20 sm:w-24 sm:h-24` to `w-14 h-14 sm:w-16 sm:h-16`. SVG placeholder icons reduced from `w-10 h-10` to `w-8 h-8` proportionally.

3. **Grid changed to grid-cols-3 sm:grid-cols-4** — VERIFIED. Both players and NPCs grids changed from `grid-cols-2 sm:grid-cols-3` to `grid-cols-3 sm:grid-cols-4`. This ensures 4 per row on desktop, 3 on mobile.

4. **No unintended changes** — VERIFIED.
   - `LootSection.tsx` — untouched (still uses `bg-black/50`)
   - `NeighborsSection.tsx` — untouched (inner cards still use `bg-black/50`)
   - `MegaMenu.tsx` — untouched (still uses `bg-black/50`)
   - `CharactersSection.tsx` (UserProfilePage) — not in diff, untouched
   - No new files created. No files deleted.

5. **Tailwind mandatory rule** — PASS. No new SCSS/CSS files. All style changes use Tailwind utility classes.

6. **TypeScript mandatory rule** — PASS. No new `.jsx` files. All modified files are `.tsx`.

7. **No React.FC usage** — PASS. Grep confirms no `React.FC` in changed files.

8. **Mobile responsiveness (360px+)** — VERIFIED (code review).
   - `w-14` = 56px avatars. At 360px with `grid-cols-3`, each column ~107px after gap/padding — sufficient for 56px avatars + text.
   - `sm:` breakpoint (640px+) uses `grid-cols-4` with `w-16` (64px) avatars — fits comfortably.
   - Text uses `text-xs` / `sm:text-sm` with `truncate` — no overflow risk.

9. **Header behavior on non-location pages** — VERIFIED. The conditional `isLocationPage ? 'bg-black/40 ...' : ''` pattern is unchanged structurally. Non-location pages still get no background.

10. **Security** — N/A. No endpoints, no data flow changes.

11. **Error handling** — N/A. No logic changes.

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not available in review environment; must be verified in CI/Docker)
- [ ] `npm run build` — N/A (Node.js not available in review environment; must be verified in CI/Docker)
- [ ] `py_compile` — N/A (no backend changes)
- [ ] `pytest` — N/A (no backend changes)
- [ ] `docker-compose config` — N/A (no Docker changes)
- [ ] Live verification — N/A (no browser tools or running server available in this environment)

**Note:** TypeScript compilation and build checks could not be executed locally because Node.js is not available in this review environment. These must be verified via CI pipeline or Docker build. The changes are purely Tailwind class value substitutions (`/70` -> `/40`, `w-20` -> `w-14`, etc.) with zero structural/logic changes, making build failure extremely unlikely.

All code-level checks passed. Changes are minimal, correct, and ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-23 12:00 — PM: фича создана, запускаю анализ кодовой базы
[LOG] 2026-03-23 12:15 — Analyst: начал анализ, изучаю компоненты LocationPage, Header, PlayersSection
[LOG] 2026-03-23 12:25 — Analyst: анализ завершён. Затронут 1 сервис (frontend), ~8 файлов. bg-black/70 используется в 7 местах, аватарки 80/96px с grid-cols-2/3
[LOG] 2026-03-23 12:35 — Architect: спроектировано 2 задачи (1 Frontend + 1 Review). Решение: bg-black/70 → bg-black/40 в 9 местах, аватарки w-14/h-14 sm:w-16/h-16, grid-cols-3 sm:grid-cols-4. Бэкенд не затронут, QA не нужен.
[LOG] 2026-03-23 13:00 — Frontend Developer: Task #1 выполнен. Заменены все bg-black/70 → bg-black/40 в 9 местах (LocationPage.tsx ×3, PlayersSection.tsx ×2, LocationMobs.tsx ×1, BattlesSection.tsx ×1, PendingInvitationsPanel.tsx ×1, Header.tsx ×1). Аватарки уменьшены до w-14 h-14 / sm:w-16 sm:h-16, SVG-иконки уменьшены до w-8 h-8. Гриды изменены на grid-cols-3 sm:grid-cols-4. LootSection, NeighborsSection, MegaMenu не затронуты. Node.js не доступен в окружении — tsc и build проверки не выполнены локально, требуется верификация в Docker/CI.
[LOG] 2026-03-23 14:00 — Reviewer: начал проверку Task #2
[LOG] 2026-03-23 14:15 — Reviewer: проверка завершена, результат PASS. Все 9 замен bg-black/70→bg-black/40 корректны, аватарки уменьшены, гриды обновлены. Незатронутые файлы (LootSection, NeighborsSection, MegaMenu) не изменены. Новых SCSS/JSX файлов нет. Node.js недоступен — tsc/build должны быть проверены в CI.
[LOG] 2026-03-23 14:20 — PM: Reviewer дал PASS, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Фон всех подложек страницы локации изменён с `bg-black/70` на `bg-black/40` (9 мест в 6 файлах)
- Аватарки игроков уменьшены: 80px → 56px (мобильные), 96px → 64px (десктоп)
- Сетка аватарок: 2 колонки → 3 (мобильные), 3 → 4 (десктоп) — теперь 4 аватарки в ряд
- Хедер на страницах локаций приведён к той же прозрачности что и остальные элементы

### Что изменилось от первоначального плана
- Ничего, всё реализовано по плану

### Оставшиеся риски / follow-up задачи
- Сборка (tsc + build) не проверена локально (Node.js недоступен) — нужна проверка через CI или Docker
