# FEAT-166: Редизайн вкладок профиля персонажа под стиль вкладки инвентаря

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-166-slug.md` → `DONE-FEAT-166-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Первая вкладка профиля персонажа (персонаж/инвентарь) недавно получила новый дизайн. Остальные вкладки профиля и их страницы (включая вкладку крафта) остались в старом стиле, пользователь считает их некрасивыми. Нужно переделать **все остальные вкладки профиля и их внутренние страницы** в едином стиле с первой вкладкой.

Чисто визуальная задача: механики и данные не меняются. Вкладка крафта только что получила новые разделы (FEAT-165: переработка, извлечение рун/огранок, без кристаллов/трансмутации/переплавки) — её редизайнить уже с новым содержимым.

### Бизнес-правила
- Эталон стиля — текущая первая вкладка профиля (новый дизайн инвентаря): те же фоны/панели, заголовки, отступы, карточки, кнопки, шрифты, цвета, поведение на мобильных.
- Все вкладки профиля (кроме уже переделанной) и все их подстраницы/модалки приводятся к этому стилю.
- Функциональность не меняется: все действия, данные, ошибки остаются как есть.
- Обязательные правила фронтенда: Tailwind (старые SCSS мигрировать и удалить), TypeScript (затронутые .jsx → .tsx), без React.FC, адаптивность от 360px, дизайн-система (`docs/DESIGN-SYSTEM.md`), при необходимости расширить дизайн-систему общими компонентами.
- Если элементы нового дизайна повторяются — вынести в переиспользуемые компоненты.

### UX / Пользовательский сценарий
1. Игрок открывает профиль, переключает вкладки.
2. Все вкладки выглядят единообразно с первой вкладкой, на телефоне тоже.

### Edge Cases
- Пустые состояния, загрузка и ошибки — тоже в новом стиле.
- Мёртвые (нигде не используемые) компоненты профиля — удалить отдельным шагом.

### Вопросы к пользователю (если есть)
- [x] Что переделываем → все вкладки профиля и их страницы, на манер первой вкладки инвентаря
- [x] Оформление вкладок → всё содержимое в золотых панелях с шапкой (`PanelShell`), как на первой вкладке
- [x] Перки → переоформить шапку и окно перка, дерево аккуратно поместить в панель; проверить, что геометрия веток не сдвинулась
- [x] Длинные списки → на десктопе прокрутка внутри панели фиксированной высоты (как инвентарь), на мобильных прокручивается страница
- [x] Крафт → колонки, как на первой вкладке: слева профессия и переработка, справа рецепты (остальные блоки — на усмотрение архитектора в том же духе)
- [x] Общие окна (заточка, гнёзда, карточка навыка в бою) → переоформить, зная что изменятся и в других местах
- [x] Мёртвые компоненты профиля → удалить в этой задаче отдельным шагом
- [x] Когда → сразу после этапа 2 ребаланса профессий (FEAT-165), до этапа 3

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline: current working tree (FEAT-165 uncommitted). Frontend only — no backend/API/DB changes needed.

### 2.1 Page structure

- Route: `App.tsx:339` → `<Route path="profile" element={<ProfilePage />} />`.
- `components/ProfilePage/ProfilePage.tsx` — `activeTab` state (default `character`), `switch` at :62-94; tabs wrapped in `motion.div.-mt-12`. Global loading spinner / "Персонаж не найден" states live here.
- `ProfileTabs.tsx` — gold uppercase text tabs with a gradient underline + external link «История постов» (`/post-history/:id`, a separate page, not a tab).

| Tab key | Label | Component | Current layout pattern |
|---|---|---|---|
| character | Персонаж | `CharacterTab/CharacterTab.tsx` | **Reference** (FEAT-149): 3 `PanelShell` panels |
| skills | Навыки | `SkillsTab/SkillsTab.tsx` (368) | loose page header + grid of `bg-black/30 border-gold/[0.16]` cards |
| perks | Перки | `PerksTab/PerksTab.tsx` (83) + `PerkTree` (459) + `PerkNode` (221) + `PerkDetailModal` (382) | **oldest style**: `text-xl` heading, `space-y-4`; tree with painted backdrop (hand-tuned in 5 recent commits) |
| party | Отряд | `PartyTab/PartyTab.tsx` (301) + 5 sub-files | mixed: side panels are `PanelShell`, main column is loose cards |
| gathering | Сбор | `GatheringTab/GatheringTab.tsx` (145) + `GatheringSkillCard` (130) | loose header + card grid (modified by FEAT-165) |
| quests | Задания | `QuestsTab/QuestsTab.tsx` (229) + `QuestDetail` (207) + `QuestJournalList` (89) + `questModel.ts` | **closest already**: master-detail in two `PanelShell`s with `PANEL_DESKTOP_HEIGHT_CLASS` |
| battles | Бои | `BattlesTab/BattlesTab.tsx` (439) + `ActiveBattleCard` (179) | loose header, `StatTile`s, rows `bg-site-bg border` (no gold outline) |
| logs | Логи персонажа | `LogsTab/LogsTab.tsx` (238) | **old style**: native `<select>` `bg-black/60`, `option.bg-[#1a1a2e]`, `bg-black/50` rows, raw `yellow/green-*` colors, different spinner, `text-xl/2xl` empty heading |
| titles | Титулы | `TitlesTab/TitlesTab.tsx` (426, monolith) | loose header + card grid (`cardChrome` variants) |
| craft | Крафт | `CraftTab/CraftTab.tsx` (250) + 12 files | loose header «Мастерская» + stacked mixed-style blocks (see 2.3) |

All files are already `.tsx`; **there are no `.jsx`, `.scss` or `.css` files under `components/ProfilePage/`** (verified with `find`). The CLAUDE.md JSX→TSX and SCSS-removal rules therefore add no migration work here; this is a Tailwind class/composition redesign only.

### 2.2 Visual language of the reference tab (FEAT-149, `features/DONE-FEAT-149-profile-redesign.md`; primitives from `DONE-FEAT-151-profile-tabs-redesign.md`)

- **Layout** — `CharacterTab.tsx:27`: `grid grid-cols-1 lg:grid-cols-[392px_minmax(300px,352px)_1fr] gap-5 items-start`. Content always sits *inside panels*; nothing is placed directly on the page background.
- **Panel** — `PanelShell.tsx:36-66` (the key reusable piece):
  - shell: `gold-outline relative rounded-card bg-site-bg backdrop-blur-[10px] shadow-card flex flex-col min-w-0 w-full` (`bg-site-bg` = `rgba(9,10,16,0.62)`; `gold-outline` = 1px gold gradient ring at inset -3px, `index.css:24-41`);
  - header band: `gradient-divider-h relative flex items-center gap-2.5 px-5 py-4 bg-black/20 rounded-t-card` + 18px gold icon (project SVG or lucide `text-gold`, strokeWidth 1.8) + `h3.gold-text text-sm font-medium uppercase tracking-[0.12em]` + right-aligned `headerExtra` (counter `text-white/50 text-xs font-mono`);
  - body: `flex-1 min-h-0 p-4 lg:p-5 lg:overflow-y-auto gold-scrollbar-wide`;
  - fixed desktop height `PANEL_DESKTOP_HEIGHT_CLASS = lg:h-[calc(100vh-130px)]` (`PanelShell.tsx:7`), auto height below `lg`.
- **Identity band** (custom header) — `CharacterPanel.tsx:47-73`: gold gradient ring circle (`p-[2px] bg-gradient-to-b from-gold-light to-gold-dark shadow-[0_0_14px_rgba(240,217,92,0.35)]`, inner `bg-site-dark`), `gold-text text-xl uppercase` name, `text-xs text-white/75` meta line.
- **In-panel sections** — `SectionHeader` (`shared/SectionHeader.tsx`): `gold-text text-[11px] uppercase tracking-[0.14em]` + fading `from-gold/40` rule; sections stacked with `flex flex-col gap-6` (`IndicatorsPanel.tsx:43`) / `gap-[18px]` (`CharacterPanel.tsx:77`).
- **Labels/values** — label `gold-text text-xs font-medium uppercase tracking-[0.06em]`, value `text-white/85 text-sm`; numbers `font-mono tabular-nums`.
- **Bars** — `.stat-bar` / `.stat-bar-fill` (+ `stat-bar-hp/mana/...`), XP gold gradient (`CharacterPanel.tsx:93-100`).
- **Separators** — `border-y border-white/10 py-3` rows (`CharacterPanel.tsx:118`), `gradient-divider-h`.
- **Chips** — `.chip-outline` / `.chip-outline-active` round 36px icon chips (`CategorySidebar.tsx:25-29`); text pills in `shared/FilterChips.tsx`.
- **Item visuals** — circular cells in `grid-cols-[repeat(auto-fill,minmax(64px,1fr))] gap-3` (`ItemGrid.tsx:52`); empty state = faded icon `opacity-20` + `text-white/40 text-sm` (`ItemGrid.tsx:60-63`).
- **Buttons/modals** — `btn-blue`, `btn-line`, `modal-overlay` + `modal-content gold-outline gold-outline-thick` (portaled via `createPortal`).
- **Motion** — tab wrapper `initial {opacity:0,y:10}` 0.3s; staggered grids (`ItemGrid.tsx:9-19`).
- **Responsive** — single column below `lg`, panels auto-height, internal scrolls only on `lg+`, grids capped with `max-h-[516px]` on mobile, `max-w-[320px] mx-auto` for fixed-geometry blocks.
- Shared primitives already present (FEAT-151): `shared/EmptyState`, `FilterChips`, `MiniStatBar`, `SectionHeader`, `StatTile`.

**Main gap vs. the other tabs:** the reference tab puts everything into gold-outlined, blurred `PanelShell` panels with a header band (icon + title + counter). The other tabs (except Quests and Party's side column) render a loose page-level `h3` header directly on the background and use *different* card surfaces: `rounded-card bg-black/30 border border-gold/[0.16] shadow-card` (Skills, Gathering, Titles, RecipeCard, ProfessionInfo, ProfessionSelect cards), `border-white/[0.07] bg-black/25` (Refining/Gem/Rune sections), `bg-site-bg border` (Battles rows), `bg-black/50 border-gold/10` (Logs). The first surface alone is repeated in 7+ files, which makes it the obvious candidate for a shared primitive.

### 2.3 Per-tab inventory (live vs dead)

**CraftTab (all live, FEAT-165 baseline)** — `CraftTab.tsx:187-246` renders: header «Мастерская» + `ActiveBuffIndicator` (102, gold-outline pills) → `ProfessionSelect` (137, already a `PanelShell` + cards + confirm modal, not portaled) **or** → `ProfessionRail` (173, chip-outline rail + change modal, not portaled) → `ProfessionInfo` (101, bg-black/30 card, rank pills) → `RefiningSection` (160, NEW, `border-white/[0.07] bg-black/25` block; opens `RefineModal` 197 NEW, portaled) → `GemSocketSection` (187, jeweler) / `RuneSocketSection` (188, enchanter): **near-identical copies** (only labels and the purple socket color differ), both open `GemSocketModal` (474, portaled) → `RecipeList` (93, SectionHeader + `input-underline` search + grid) → `RecipeCard` (148). `CraftConfirmModal` (108, not portaled, raw `text-green-400`). `SharpeningModal` (375, portaled, raw `green-900/300/500`) is **not** rendered by CraftTab; it opens only from `InventoryTab/ItemContextMenu.tsx:25` (character tab), and `GemSocketModal` opens from there too (:27). Both modals are therefore shared with the reference tab. Deleted by FEAT-165: `EssenceExtractionSection`, `SharpeningSection`, `SmeltingModal/Section`, `TransmutationSection`.

**Skills** — `SkillsTab.tsx` (live; skill cards inline, detail modal at :320-335, not portaled). `ResolvedSkillCard.tsx` (322) is **also used by `pages/BattlePage/SkillPicker/SkillPicker.tsx:10`** and has raw `red/emerald/amber/purple-*` colors, so restyling it also changes the battle page.

**Perks** — `PerksTab`, `PerkTree` (15 hex values incl. the `bg-[#04041a]` backdrop, per-branch geometry), `PerkNode` (6 hex), `PerkDetailModal` (raw purple/emerald). The user hand-tuned the tree geometry in commits 06af19d…84bd330.

**Party** — `PartyTab`, `PartyHeaderCard` (custom gradient card), `PartyMemberCard`, `PartyCreateCard`/`PartyInvitesPanel`/`InviteFromLocationPanel` (already PanelShell).

**Gathering** — `GatheringTab`, `GatheringSkillCard` (modified by FEAT-165; wait until FEAT-165 lands before touching them).

**Quests** — `QuestsTab`, `QuestDetail`, `QuestJournalList`, `questModel.ts`: already PanelShell, needs only alignment (header band, cards).

**Battles** — `BattlesTab` (inline pagination + history rows), `ActiveBattleCard`.

**Logs** — `LogsTab` single file; of the small tabs it needs the most visual work (native select, raw colors, `#1a1a2e`).

**Titles** — `TitlesTab`, a single 426-line file that renders its cards inline.

**Character tab internals (reference, out of scope)** — `CharacterTab/*`, `EquipmentPanel/EquipmentSlot.tsx`, `EquipmentPanel/FastSlots.tsx`, `CharacterInfoPanel/StatsPanel.tsx`, `CharacterInfoPanel/RestStatusPanel.tsx`, `StatsTab/{PrimaryStatsSection,StatDistributionPanel,DerivedStatsSection}.tsx`, `InventoryTab/{CategorySidebar,ItemGrid,ItemCell,ItemContextMenu,ItemDetailModal,RepairModal}.tsx`, `InventoryTab/dnd/*`.

**DEAD (not rendered anywhere; do not restyle, candidates for deletion):**
- `InventoryTab/InventoryTab.tsx`: ProfilePage does not import it (the admin `InventoryTab` is a different file)
- `CharacterInfoPanel/CharacterInfoPanel.tsx`, `CharacterInfoPanel/CharacterCard.tsx`: used only by the dead InventoryTab
- `EquipmentPanel/EquipmentPanel.tsx`: used only by the dead InventoryTab
- `StatsTab/StatsTab.tsx`, `StatsTab/ResourceStatsSection.tsx`: no importers
- `PlaceholderTab.tsx` is still wired in as the `default:` switch branch, but no entry in the current TABS list can reach it.

External consumers of ProfilePage modules: `constants.ts` (Admin, Auction, LocationPage) and `SkillsTab/ResolvedSkillCard.tsx` (BattlePage). Nothing else is imported from outside.

### 2.4 Reuse opportunities / design-system extension

1. **`ProfileCard`** (new `shared/` primitive) for the repeated card surface. Ideally switch it to the reference look (`bg-site-bg` + `gold-outline`, or a subtler variant) with `interactive`/`active`/`locked` variants (Titles' `cardChrome`, Skills/Recipe hover).
2. **`GoldIconFrame`** — the gold-gradient icon frame (`p-[2px] bg-gradient-to-b from-gold-light to-gold-dark` + inner `bg-site-dark`) is copy-pasted in Skills, Gathering, ProfessionInfo, ProfessionSelect, PartyHeaderCard, PartyMemberCard, RecipeCard (circle) and CharacterPanel (circle), at sizes 40/52/54/56/62px, square or circle.
3. **Tab layout** — a `PanelShell`-based pattern where every tab is one or more `PanelShell`s and the title + counter move into the header band. This replaces the loose `h3.gold-text ... tracking-[0.12em]` header duplicated in Skills/Party/Quests/Battles/Titles/Gathering/Craft.
4. **`LoadingState` / `ErrorState`** — the tabs use 4 different spinner variants (`w-7`/`w-8`/`border-4 border-white/30`) and 3 error layouts.
5. **`ProgressBar`** — progress bars are duplicated with custom `h-[9px]`, `h-1` and `.stat-bar` (ProfessionInfo, GatheringSkillCard, TitlesTab, PerkDetailModal); unify on `.stat-bar`.
6. **`SocketItemsSection`** — merge `GemSocketSection`/`RuneSocketSection` (identical structure) into one parametrised component.
7. **`ModalShell`** — modals repeat overlay + motion + `modal-content gold-outline gold-outline-thick`. Some are portaled (Refine/Sharpening/GemSocket/ItemDetail/Repair) and some are not (CraftConfirm, ProfessionRail/Select, Skills detail, PerkDetail). A shared portaled shell with a header band matching PanelShell would unify them.
8. **Status colors** — raw Tailwind `green/red/emerald/purple/amber/yellow-*` classes appear in Logs, SharpeningModal, CraftConfirmModal, ItemDetailModal, ResolvedSkillCard, Perk* and RuneSocketSection. The design system has `stat-energy` (green), `site-red`, `site-blue` and rarity tokens. Missing: a "rune/purple" accent (could reuse `rarity-epic`) and a "success" token.
9. **DESIGN-SYSTEM.md** documents neither `PanelShell`, nor the `shared/*` primitives, nor the "profile panel" pattern; §13 should be extended.

### 2.5 Risks

- **Parallel FEAT-165 review**: CraftTab/*, GatheringTab/*, `InventoryTab/ItemContextMenu.tsx` and `constants.ts` are modified and uncommitted, so any FEAT-165 review fix would conflict. Start implementation only after FEAT-165 is closed, as the brief already says.
- **Shared modals**: `SharpeningModal`/`GemSocketModal` open from the reference tab's context menu, and `ResolvedSkillCard` is used on the battle page. Restyling them is visible outside the tab being redesigned.
- **Perk tree**: its absolute geometry and painted backdrop were tuned by the user. Wrapping it in a panel with different padding or height may shift branch alignment (`PerkTree.tsx:303` `max-w-[760px] aspect-square`). Keep the tree internals untouched unless the user asks.
- **Fixed desktop heights** (`PANEL_DESKTOP_HEIGHT_CLASS`) suit master-detail tabs, but card-grid tabs with long lists (Skills/Titles/Recipes) would get internal scrolls. Needs a decision per tab.
- **Modals inside `PanelShell`**: `backdrop-blur` on the shell (and `motion.div` transforms) creates a containing block for `position: fixed` descendants. Non-portaled modals (`CraftConfirmModal`, the `ProfessionRail`/`ProfessionSelect` modals, Skills detail, `PerkDetailModal`) would be clipped or mispositioned once rendered inside a panel, so they must be portaled (`createPortal`). `ProfessionSelect` already renders its modal inside a PanelShell and should be verified live.
- **Mobile (360px)**: rails and filter rows must keep horizontal scroll, and `lg:grid-cols-[...]` layouts must collapse. Battles rows are already responsive; the Logs select has `sm:min-w`.
- No SCSS/JSX in scope, so the risk of breaking legacy styles is low. No backend changes, so no QA tasks are needed (frontend only). The reviewer's live check (desktop + 360px) is mandatory.

### 2.6 Size estimate & proposed split

Scope: about 45 live files / ~7 000 lines of TSX to restyle, with no logic changes. Proposed tasks (disjoint file sets, parallel-safe after T0):

| # | Task | Files | Size |
|---|---|---|---|
| T0 (first, blocking) | Shared primitives + DS docs: `ProfileCard`, `GoldIconFrame`, `LoadingState`/`ErrorState`, portaled `ModalShell`, possibly `ProgressBar`; extend `PanelShell` if needed; document in `docs/DESIGN-SYSTEM.md` §13; new tokens in `tailwind.config.js`/`index.css` if any | `ProfilePage/shared/*`, `PanelShell.tsx`, `index.css`, `tailwind.config.js`, `DESIGN-SYSTEM.md` | M |
| T1 | Craft tab + its sections/modals (incl. merging Gem/Rune sections, and the shared `SharpeningModal`/`GemSocketModal`) | `CraftTab/*` | L |
| T2 | Skills + Perks (tree: outer wrapper only) | `SkillsTab/*`, `PerksTab/*` | M (check BattlePage for `ResolvedSkillCard`) |
| T3 | Party + Gathering | `PartyTab/*`, `GatheringTab/*` | M |
| T4 | Quests + Battles | `QuestsTab/*`, `BattlesTab/*` | M |
| T5 | Logs + Titles + `ProfileTabs.tsx` + `ProfilePage.tsx` loading/empty states | `LogsTab/*`, `TitlesTab/*`, `ProfileTabs.tsx`, `ProfilePage.tsx` | M |
| T6 (optional) | Dead-code cleanup (see 2.3) | dead files | S |

Every task runs `npx tsc --noEmit` + `npm run build` in the frontend container; the reviewer checks live on desktop and at 360px.

### 2.7 Open questions (product)

1. Should every tab adopt the "everything inside gold panels" look (panel header band with title + counter), or keep open card grids on the background with the cards restyled to match?
2. Perks tab: the tree was hand-tuned recently. Restyle only the header/modal and place the tree in a panel, or leave the tab untouched?
3. Long lists (skills, titles, recipes, logs): fixed-height panels with internal scroll on desktop (like the inventory), or natural page scroll?
4. Craft tab composition: one panel per block stacked vertically, or a multi-column layout like the reference (e.g. profession info + refining on the left, recipes on the right)?
5. Shared modals (sharpening/sockets) and the skill card on the battle page: restyle them too, knowing this also changes the character tab and battle page?
6. Delete the dead profile components now (T6), or leave that for later?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Scope & constraints

- **Frontend only.** No backend, API, DB, Nginx, Docker or env changes. **No QA Test (pytest) tasks**: per CLAUDE.md, QA is mandatory only when backend Python code changes, and this feature changes none.
- **Baseline = current working tree (FEAT-165 uncommitted).** Implementation starts only after FEAT-165 is closed. If FEAT-165 review fixes land in `CraftTab/*`, `GatheringTab/*` or `InventoryTab/ItemContextMenu.tsx`, developers work on top of those fixes.
- **Visual only.** No new/removed actions, API calls, Redux state, validation or Russian texts. The only allowed "structural" changes are listed explicitly below: moving blocks into panels, merging `GemSocketSection`/`RuneSocketSection` into one parametrised component with identical behaviour, replacing the Logs native `<select>` with `FilterChips` (same options, same values, same handler), and portaling modals.
- No `.jsx`/`.scss` in `ProfilePage/` (analyst verified), so the TSX and SCSS migration rules add no work. Rules that still apply: Tailwind only, no `React.FC`, DS classes/tokens, mobile from 360px, and visible Russian errors (keep the existing toasts and error texts).
- **Reference is not touched.** `CharacterTab/*`, `PanelShell.tsx` markup, `InventoryTab/{CategorySidebar,ItemGrid,ItemCell,ItemContextMenu,ItemDetailModal,RepairModal}`, `EquipmentPanel/{EquipmentSlot,FastSlots}`, `CharacterInfoPanel/{StatsPanel,RestStatusPanel}` and live `StatsTab/*` sections stay unchanged. (`PanelShell.tsx` stays at `ProfilePage/PanelShell.tsx`; it is not moved, so the reference imports stay valid.)

### 3.1 Tab composition rule (applies to every tab)

1. The tab root stays a `motion.div` with the standard fade (`initial {opacity:0,y:10}`, 0.3s) and has **no loose page-level `h3` header**. Title, icon and counter move into the `PanelShell` header band (`title`, `icon`, `headerExtra`).
2. **Everything sits inside `PanelShell`s** (user decision). Multi-panel tabs use a `grid grid-cols-1 lg:grid-cols-[...] gap-5 items-start` grid, like `CharacterTab.tsx:27`. The fixed first column is **392px**, the same as the reference.
3. **Long lists** (user decision): on `lg+` the panel gets `PANEL_DESKTOP_HEIGHT_CLASS` and the list scrolls inside it. Filters and search sit in a fixed strip under the header (`PanelToolbar`), and the list fills the rest (`PanelScrollArea`). This is the same pattern as `InventoryPanel.tsx`. Below `lg`, panels have auto height and the page scrolls: no internal scroll and no `max-h` caps on lists.
4. Header band conventions: icon is lucide `size={18} strokeWidth={1.8} className="text-gold shrink-0"` (or a project SVG at `w-[18px] h-[18px]`). The counter uses `PanelCounter`. Extra header chips (perk points, "готово к сдаче", buffs) go into `headerExtra` and must wrap or truncate at 360px. If they don't fit, move them to the top of the toolbar strip on mobile (`hidden sm:flex` in the header + `sm:hidden` copy in the toolbar).
5. **Inner cards** use `ProfileCard`. We avoid nesting a second blurred gold ring inside a gold panel, because the design should stay "airy". **Icon/avatar frames** use `GoldIconFrame`. **Section titles inside a panel** use the existing `SectionHeader`, and sections are stacked with `flex flex-col gap-6`.
6. **Loading / error / empty** states use `LoadingState` / `ErrorState` / `EmptyState`. When a tab fails before it has data, the state is rendered **inside the tab's main `PanelShell`** (same title/icon), so the layout does not jump.
7. **Every modal uses `ModalShell`**, which renders through `createPortal(document.body)`. The reason: `PanelShell` has `backdrop-blur` and the tab wrapper has a `motion` transform, and both create a containing block that breaks `position: fixed`. **No `modal-overlay` may be rendered in place** inside a tab after this feature.
8. **Status colours → existing tokens** (no new Tailwind tokens):
   - success/green → `text-stat-energy` / `bg-stat-energy/..` / `border-stat-energy/..`
   - error/red → `text-site-red` (HP-like red → `text-stat-hp`)
   - rune/purple → `text-rarity-epic` / `bg-rarity-epic/..`
   - warning/amber/yellow → `text-gold` / `text-gold-light`
   - info/blue → `text-site-blue`
   - Raw `green-*/red-*/emerald-*/purple-*/amber-*/yellow-*` classes and `#hex` arbitrary values are removed from touched files. **Exception:** `PerkTree.tsx`/`PerkNode.tsx`, whose internals are frozen (see 3.3, Perks).
9. **Banned ad-hoc surfaces in touched files** (grep in acceptance criteria): `bg-black/30 border border-gold/[0.16]`, `border-white/[0.07] bg-black/25`, `bg-black/50`, `bg-black/60`, `bg-site-bg border` (as a card), `bg-[#`, `option` with `bg-[#1a1a2e]`, and hand-rolled spinners (`animate-spin` outside `LoadingState`). **Exception:** small inline button spinners, which may use `LoadingState size="xs"` or stay as is.

### 3.2 Shared primitives (T0) — `src/components/ProfilePage/shared/`

All new files are `.tsx`, have no `React.FC`, and are built only from DS classes/tokens. Their public API is fixed here so the parallel tasks can rely on it.

| File | Status | API | Markup / classes |
|---|---|---|---|
| `ProfileCard.tsx` | NEW | `{ as?: 'div' \| 'button' \| 'li'; variant?: 'default' \| 'accent' \| 'danger'; interactive?: boolean; active?: boolean; locked?: boolean; className?: string; children; ...rest (onClick, type, disabled, aria-*) }` | base `relative rounded-card border bg-white/[0.03] border-white/10 transition-colors duration-200 ease-site`; `interactive` → `cursor-pointer hover:border-gold/40 hover:bg-gold/[0.04]`; `active` → `border-gold/50 bg-gold/[0.06]`; `locked` → `opacity-60`; `accent` → `border-gold/30 bg-gradient-to-b from-gold/[0.08] to-transparent`; `danger` → `border-site-red/30 bg-site-red/[0.05]`. For motion lists, the caller wraps it in `motion.div` (stagger variants), or T0 exports `MotionProfileCard = motion.create(ProfileCard)` if forwardRef is used. Padding is left to the caller (default suggestion `p-3.5`). |
| `GoldIconFrame.tsx` | NEW | `{ size: number (px); shape?: 'circle' \| 'square'; glow?: boolean; src?: string \| null; alt?: string; fallback?: ReactNode; className?: string; children? }` | outer `p-[2px] bg-gradient-to-b from-gold-light to-gold-dark shrink-0` + `rounded-full` / `rounded-[10px]`, inline `style={{width:size,height:size}}`; `glow` → `shadow-[0_0_14px_rgba(240,217,92,0.35)]`; inner `w-full h-full bg-site-dark flex items-center justify-center overflow-hidden` with the same radius; `src` → `img object-cover w-full h-full`, else `fallback`/`children`. Replaces the copies in Skills, Gathering, ProfessionInfo/Select, RecipeCard, Party*, ActiveBattleCard, QuestJournalList/QuestDetail. |
| `LoadingState.tsx` | NEW | `{ size?: 'xs' \| 'sm' \| 'md'; label?: string; className?: string }` | wrapper `flex flex-col items-center justify-center gap-3 py-20` (xs/sm: `py-6`/inline, `xs` renders only the spinner `w-4 h-4` for buttons); spinner `border-2 border-gold border-t-transparent rounded-full animate-spin` (`md` `w-8 h-8`, `sm` `w-6 h-6`); optional `label` `text-sm text-white/40`. |
| `ErrorState.tsx` | NEW | `{ message: string; onRetry?: () => void; className?: string }` | `flex flex-col items-center justify-center gap-3 py-14 text-center`; `AlertTriangle size={32} strokeWidth={1.5} className="text-site-red/60"`; message `text-sm text-white/60`; the «Повторить» `btn-line` button is shown **only if `onRetry` is given**. Tabs pass `onRetry` only if they already had a retry, since adding one would change functionality. |
| `EmptyState.tsx` | MODIFY (additive) | add `hint?: string` | hint `text-xs text-white/30` under the message (needed by Logs' two-line empty text). Existing callers are unchanged. |
| `ModalShell.tsx` | NEW | `{ open: boolean; onClose: () => void; title?: string; icon?: ReactNode; size?: 'sm' \| 'md' \| 'lg'; closeOnBackdrop?: boolean (default true); dismissible?: boolean (default true; false hides X and ignores backdrop/Escape — for `loading` states like RefineModal); footer?: ReactNode; bodyClassName?: string; children }` | `createPortal(<AnimatePresence>{open && overlay}</AnimatePresence>, document.body)`; overlay `modal-overlay px-4` (`onClick` → close when allowed); panel `motion.div` fade+scale (DS §12 preset), `modal-content gold-outline gold-outline-thick !p-0 flex flex-col max-h-[90dvh]` + width `max-w-md`/`max-w-xl`/`max-w-3xl`, `onClick` stopPropagation; header band (only when `title`) identical to PanelShell: `gradient-divider-h relative flex items-center gap-2.5 px-5 py-4 bg-black/20 rounded-t-[15px] shrink-0` + icon + `h3.gold-text text-sm font-medium uppercase tracking-[0.12em]` + `ml-auto` close `X` button (`text-white/40 hover:text-white`, `aria-label="Закрыть"`); without `title` the X floats `absolute top-3 right-3`; body `flex-1 min-h-0 overflow-y-auto gold-scrollbar p-4 sm:p-6 ${bodyClassName}`; footer `shrink-0 px-4 sm:px-6 py-4 border-t border-white/10 flex flex-wrap justify-end gap-3` (buttons full-width on mobile: `w-full sm:w-auto` by callers); Escape key closes when dismissible; `role="dialog" aria-modal="true"`. |
| `ProgressBar.tsx` | NEW | `{ value: number; max: number; variant?: 'gold' \| 'hp' \| 'mana' \| 'energy' \| 'epic'; size?: 'sm' \| 'md'; label?: ReactNode; showValues?: boolean; className?: string }` | `stat-bar` (md = DS 9px, sm = `h-1.5 border-white/40`) + `stat-bar-fill` with `bg-gradient-to-r from-gold-dark to-gold-light` (gold) / `stat-bar-hp|mana|energy` / `bg-rarity-epic`; clamps 0–100%, `max<=0` → 0; values `text-[10px] font-mono tabular-nums text-white/50`. Replaces the custom `h-[9px]`/`h-1` bars in ProfessionInfo, GatheringSkillCard, TitlesTab, PerkDetailModal, Quests. `MiniStatBar` stays as is. |
| `PanelCounter.tsx` | NEW | `{ children; className? }` | `text-white/50 text-xs font-medium font-mono tabular-nums` (same as InventoryPanel's counter). |
| `PanelToolbar.tsx` | NEW | `{ children; className? }` | `shrink-0 px-4 lg:px-5 pt-3.5 pb-2 flex flex-wrap items-center gap-3` (filters/search strip under the header). |
| `PanelScrollArea.tsx` | NEW | `{ children; className? }` | `flex-1 min-h-0 px-4 lg:px-5 pt-2 pb-4 lg:overflow-y-auto gold-scrollbar-wide`. Used with `PanelShell bodyClassName="flex-1 min-h-0 flex flex-col"`. |
| `StatTile.tsx` | MODIFY | API unchanged | Swap the outer surface from `gold-outline bg-site-bg` to `ProfileCard` styling (`rounded-card border border-white/10 bg-white/[0.03]`), because it now sits inside a panel. Its only consumer is `BattlesTab`. |

`docs/DESIGN-SYSTEM.md` (T0): add **§18 "Profile Panels (FEAT-148/149/151/166)"**. It covers: the `PanelShell` API + `PANEL_DESKTOP_HEIGHT_CLASS`; the tab composition rule (3.1); the toolbar + scroll-area pattern with a code example; every shared primitive above (table + usage snippet); the `ModalShell` rule ("any modal rendered below a blurred/transformed ancestor must be portaled"); the status-colour → token mapping; and the banned ad-hoc surfaces. Also add a one-line pointer from §4 "Modals" and §13 to §18, and add `PanelShell`/`shared/*` to §14 "Where patterns come from".

### 3.3 Per-tab layouts

Widths below are for the 1360px container; 360px means a single column with auto-height panels.

**Craft (T1)**
- No profession: one full-width `PanelShell` «Выбор профессии» (`Hammer`), `headerExtra` = `ActiveBuffIndicator`. The body holds the existing profession cards as `ProfileCard interactive` + `GoldIconFrame size=56 square`, in a `grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3.5`. The confirm dialog uses `ModalShell size="sm"`. Auto height (short list).
- With a profession: `grid grid-cols-1 lg:grid-cols-[392px_1fr] gap-5 items-start`.
  - **Left** `PanelShell` «Мастерская» (`Hammer`), `className={PANEL_DESKTOP_HEIGHT_CLASS}`, default scrolling body. The body is `flex flex-col gap-6`:
    1. `ActiveBuffIndicator`, only if it renders (wrap-friendly pills);
    2. `ProfessionRail` (chip rail keeps horizontal scroll; the change-profession dialog uses `ModalShell`);
    3. `ProfessionInfo` (`GoldIconFrame size=52`, rank pills, XP via `ProgressBar variant="gold"`), with no card of its own: it is a section of the panel;
    4. `RefiningSection` under `SectionHeader` «Переработка», with rows as `ProfileCard` (opens `RefineModal` → `ModalShell`, `dismissible={!loading}`);
    5. jeweler/enchanter only: `SocketItemsSection variant="gem" | "rune"` under `SectionHeader` (existing Russian titles), with rows as `ProfileCard` and the rune socket accent `text-rarity-epic`.
  - **Right** `PanelShell` «Рецепты» (`BookOpen`), `headerExtra={<PanelCounter>{recipes.length}</PanelCounter>}`, `className={PANEL_DESKTOP_HEIGHT_CLASS}`, `bodyClassName="flex-1 min-h-0 flex flex-col"`. The `RecipeList` search input (`input-underline`) goes into `PanelToolbar`. The grid goes into `PanelScrollArea`: `grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-3.5`. `RecipeCard` becomes a `ProfileCard` (`locked` when it cannot be crafted, if that state exists today) with `GoldIconFrame size=48 circle`. Loading, error and empty use the shared states. `RecipeList`'s own `SectionHeader` is removed, because the panel header replaces it.
  - Mobile: left panel first, then recipes.
- Modals (T1): `CraftConfirmModal`, `RefineModal`, `GemSocketModal`, `SharpeningModal` and the ProfessionRail/ProfessionSelect dialogs all move to `ModalShell`, with titles from their existing Russian headings. Raw greens/reds/purples are mapped to tokens (3.1.8). Note that `SharpeningModal` and `GemSocketModal` also open from the reference tab's `ItemContextMenu`: **no prop/API changes**, and `ItemContextMenu.tsx` is not edited.
- `GemSocketSection.tsx` + `RuneSocketSection.tsx` → a new `SocketItemsSection.tsx` with `variant: 'gem' | 'rune'`. The variant config holds the item-type set (`JEWELRY_TYPES` from `GemSocketSection` — equal to `JEWELRY_SOCKET_TYPES` in `constants/professions.ts`, may reuse it / `RUNE_EXTRACT_TYPES` incl. legacy `belt`), the labels, the accent class and the modal mode. **The filtering/sorting/modal props must stay byte-for-byte equivalent** to today's two files. Both old files are deleted in T1 (this is a refactor, not dead code).

**Skills (T2)** — one full-width `PanelShell` «Навыки» (`Sparkles`), `headerExtra` = `PanelCounter filtered/total` + the existing perk-points chip. It uses `PANEL_DESKTOP_HEIGHT_CLASS` with toolbar + scroll area. `PanelToolbar`: `FilterChips` (flex-1, horizontal scroll) + the «Дерево навыков» link (`btn-blue`, `Network` icon, `w-full sm:w-auto`). Grid: `grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3.5`. The card is `ProfileCard as="button" interactive` + `GoldIconFrame size=62 square`, and the level pips, cost chips and «перк» badge are kept. The detail dialog uses `ModalShell size="md"` without a title (the name is inside `ResolvedSkillCard`), with the existing loading/error content. `ResolvedSkillCard.tsx`: tokens only (3.1.8), inner blocks → `ProfileCard`, no prop changes. It must be checked on the **BattlePage `SkillPicker`** at 1440/360 as well.

**Perks (T2)** — one full-width `PanelShell` «Перки» (`Star`), `headerExtra={<PanelCounter>{unlocked}/{total}</PanelCounter>}`. **Auto height, no internal scroll** (`bodyClassName="p-4 lg:p-5"`). This is a deliberate exception to 3.1.3: the tree is a fixed-geometry `aspect-square max-w-[760px]` block, not a list. `<PerkTree>` is rendered inside unchanged. **`PerkTree.tsx` and `PerkNode.tsx` are frozen: zero diff** (viewBox, `CENTER`, `ART_NUDGE_*`, `max-w-[760px]`, backdrop hex, mobile variant, empty branch). Loading/error use the shared states inside the panel. `PerkDetailModal` → `ModalShell size="md"` with the perk name as title (or the current heading), progress via `ProgressBar`, and purple/emerald mapped to tokens.
- **Geometry proof (mandatory):** *before* any T2 change, with the same account, take screenshots of the Perks tab at 1440×900, 1024×768 (the `md` desktop tree) and 360×780. *After* the change, take the same three shots. At 1440, the rendered tree circle diameter must stay 760px. At every width, the positions of the hub and the branch nodes relative to the circle must match (overlay or side-by-side crop of the circle). Store the screenshots in the scratchpad and list their paths plus the measured diameters in the Section 6 log. The Reviewer repeats the check.

**Party + Gathering (T3)**
- Party, member/leader view: `grid grid-cols-1 lg:grid-cols-[1fr_392px] gap-5 items-start` (the right column exists only when it does today: `hasRightColumn`; otherwise the left panel is full width).
  - **Left** `PanelShell` «Отряд» (`Users`), `headerExtra={<PanelCounter>{accepted}/{PARTY_MAX_SIZE}</PanelCounter>}`, `PANEL_DESKTOP_HEIGHT_CLASS`. The body is `flex flex-col gap-6`:
    - `PartyHeaderCard` restyled as an identity band like `CharacterPanel.tsx:47-73` (`GoldIconFrame circle glow` avatar, `gold-text text-xl uppercase` name, «Лидер» chip, with rename/avatar entry points kept), not a separate gradient card;
    - `SectionHeader` «Участники»;
    - member grid `grid-cols-1 sm:grid-cols-2 gap-3.5` of `PartyMemberCard` (`ProfileCard`, `locked` for `invited`, `GoldIconFrame circle size=54`, `MiniStatBar`s kept);
    - free slots keep the dashed placeholder, recoloured to `border-white/15` (a dashed border is part of the DS vocabulary here);
    - disband/leave buttons at the bottom (`w-full sm:w-auto`).
  - **Right** column `flex flex-col gap-5`: `InviteFromLocationPanel` and `PartyInvitesPanel` (already PanelShell). Align them: counters via `PanelCounter`, rows via `ProfileCard`, avatars via `GoldIconFrame`. `InviteFromLocationPanel` uses `PANEL_DESKTOP_HEIGHT_CLASS` when it is the only right panel; if both panels are shown, both have auto height with `lg:max-h-[calc((100vh-150px)/2)]` + scroll area.
  - No-party view: `grid grid-cols-1 lg:grid-cols-2 gap-5 items-start`. `PartyCreateCard` (PanelShell, input + benefits list, `btn-blue w-full sm:w-auto`) and `PartyInvitesPanel`, both auto height.
- Gathering: one full-width `PanelShell` «Навыки сбора» (`Pickaxe`), `headerExtra={<PanelCounter>{skills.length}</PanelCounter>}`, `PANEL_DESKTOP_HEIGHT_CLASS`, default scrolling body. Grid: `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4`. `GatheringSkillCard` → `ProfileCard` + `GoldIconFrame size=52 square` + `ProgressBar variant="gold"`. The existing empty `EmptyState` and loading render inside the panel. The `ErrorBoundary` wrapper in ProfilePage stays.

**Quests + Battles (T4)**
- Quests: `grid grid-cols-1 lg:grid-cols-[392px_1fr] gap-5 items-start` (was `346px`).
  - **Left** `PanelShell` «Задания» (`BookOpen`), `headerExtra` = counter + the «готово к сдаче» chip, toolbar + scroll area. `FilterChips` goes in `PanelToolbar` (horizontal scroll inside 392px). Journal rows use `ProfileCard as="button" interactive active={selected}` + `GoldIconFrame size=42` + `ProgressBar size="sm"`.
  - **Right** `PanelShell` «Детали» (`Scroll`), keeping the existing `hidden lg:flex` behaviour when nothing is selected. `QuestDetail` sections use `SectionHeader`, objective bars use `ProgressBar`, reward chips keep their tokens, and actions use `w-full sm:w-auto`.
  - `questModel.ts` is not changed.
  - Mobile: journal first, detail below when a quest is selected (current behaviour).
- Battles: `grid grid-cols-1 lg:grid-cols-[392px_1fr] gap-5 items-start`.
  - **Left** `PanelShell` «Сводка» (`Swords`), `headerExtra={<PanelCounter>{stats.total}</PanelCounter>}`, `PANEL_DESKTOP_HEIGHT_CLASS`, body `flex flex-col gap-6`:
    - `SectionHeader` «Текущий бой» + `ActiveBattleCard`, or the error/empty row as `ProfileCard variant="danger"` / `ProfileCard` with the same texts;
    - `SectionHeader` «Статистика» + `grid grid-cols-2 gap-3` of the 4 `StatTile`s (no `lg:grid-cols-4` any more).
    - `ActiveBattleCard` must fit a 392px column: use its narrow/stacked layout at all widths, with participant rows as `ProfileCard` (ally/enemy tint via `border-site-blue/30` / `border-site-red/30`) and avatars via `GoldIconFrame size=40 circle`.
  - **Right** `PanelShell` «История боёв» (`History`), toolbar with the two `FilterChips` rows, `PanelScrollArea` with history rows as `ProfileCard` (result colour → `text-stat-energy` / `text-site-red`). Pagination goes in a pinned footer `shrink-0 px-4 lg:px-5 py-3 border-t border-white/10` (buttons ≥ 36px touch targets).
  - Mobile: summary first.

**Logs + Titles + page chrome (T5)**
- Logs: one full-width `PanelShell` «Логи персонажа» (`Activity`), `headerExtra={<PanelCounter>{logs.length}/{total}</PanelCounter>}`, `PANEL_DESKTOP_HEIGHT_CLASS`, toolbar + scroll area.
  - Toolbar: the native `<select>` is replaced by `FilterChips` built from `EVENT_TYPE_FILTER_OPTIONS` (the same 5 options, `''` = «Все», calling the existing `handleFilterChange`).
  - Rows use `ProfileCard className="p-3 sm:p-4 flex items-start gap-3"`. The event icon circle colours map to tokens: rp_post → `bg-site-blue/15 text-site-blue`; battles → `bg-site-red/15 text-site-red`; item → `bg-gold/15 text-gold`; level → `bg-stat-energy/15 text-stat-energy`; default → `bg-white/10 text-white/60`.
  - «Загрузить ещё» (`btn-line`, inline `LoadingState size="xs"`) and «Показано X из Y» stay at the end of the scroll area.
  - Empty → `EmptyState` with message = the former heading and `hint` = the former sub-text (same strings, both filter/no-filter variants). Loading → `LoadingState`.
- Titles: one full-width `PanelShell` «Титулы» (`Award`), `headerExtra` = `PanelCounter` (earned/total, as the current counter shows), `PANEL_DESKTOP_HEIGHT_CLASS`, toolbar (`FilterChips`) + scroll area, grid `grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4`. `cardChrome` is replaced by `ProfileCard` (equipped/active title → `active`, not-earned → `locked`, rare/special → `accent`, following the current variant mapping 1:1). Progress uses `ProgressBar`. The dev may extract `TitleCard.tsx` into `TitlesTab/` (new file) to break up the 426-line monolith, with no logic change.
- `ProfileTabs.tsx`: keep the look (it is also the reference tab's bar). Only replace the hex underline `via-[#999]` with `via-gold/60`, and add `whitespace-nowrap shrink-0` to the tab buttons so the bar scrolls instead of wrapping at 360px.
- `ProfilePage.tsx`: global loading → `LoadingState`; "Персонаж не найден" → `EmptyState` (`UserX` icon, same text). The `PlaceholderTab` branch is left for T6.

### 3.4 Cross-cutting risks & mitigations

| Risk | Mitigation |
|---|---|
| Shared modals change on the character tab / battle page | T1 must also live-check `SharpeningModal`/`GemSocketModal` from the character tab's item context menu. T2 must live-check `SkillPicker` on BattlePage. No prop changes. |
| Perk tree geometry shift | `PerkTree.tsx`/`PerkNode.tsx` are frozen (zero diff, verified with `git diff --stat`), plus the mandatory before/after screenshots at 3 widths. |
| Tooltips/popovers clipped by `lg:overflow-y-auto` panels (e.g. `ActiveBuffIndicator`, cost-chip titles) | Each dev checks the hover tooltips in their tab at 1440. A clipped popover must be portaled or repositioned, without changing its content. |
| `ModalShell` exit animation / focus | `AnimatePresence` inside the portal. Callers pass `open` instead of conditional mounting where exit animation existed. Escape handling lives in one place. |
| Parallel conflicts | File sets in section 4 are disjoint. `shared/*`, `PanelShell.tsx` and `DESIGN-SYSTEM.md` are owned by T0 only. If a developer needs a primitive change, they report it to PM instead of editing `shared/`. |
| `SocketItemsSection` merge alters behaviour | The acceptance criterion requires identical item lists for jeweler/enchanter (compare before/after screenshots with the same inventory, incl. a legacy belt with a rune). |
| FEAT-165 not yet closed | T1/T3 do not start until FEAT-165 is DONE. They rebase onto its final state. |

### 3.5 Security

No new endpoints, requests or data flows, so auth/rate-limit/validation is unchanged. `ModalShell` renders only React children (no `dangerouslySetInnerHTML`). All existing error toasts/messages stay visible and in Russian.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Gate:** no task starts before FEAT-165 is DONE. **Order:** T0 → (T1, T2, T3, T4, T5 in parallel) → T6 → T7.
**No QA Test task:** this feature changes zero backend Python code (CLAUDE.md: QA is mandatory only for backend changes).
All paths below are relative to `services/frontend/app-chaldea/src/components/ProfilePage/` unless they start with `docs/` or `src/`.

**Common acceptance criteria (CAC), part of every T1–T6 task:**
1. `npx tsc --noEmit` and `npm run build` pass, run inside the frontend container (`docker compose exec frontend ...`; the host has no node).
2. No functional changes: same API calls, Redux actions, handlers, conditions, toasts and error messages. Every Russian UI string is preserved verbatim, except the header wording listed in 3.3.
3. No `React.FC` / `React.FunctionComponent`. Tailwind + DS classes only. No new CSS/SCSS files.
4. In touched files, `grep -nE "bg-black/(30|50|60)|border-gold/\[0\.16\]|border-white/\[0\.07\]|bg-\[#|#[0-9a-fA-F]{3,6}|(green|red|emerald|purple|amber|yellow)-[0-9]{2,3}"` returns nothing, except the documented exceptions (`PerkTree.tsx`/`PerkNode.tsx` are untouched, and `index.css` is not touched). No page-level loose `h3` tab headers are left, and no in-place (non-portaled) `modal-overlay`.
5. Uses only the shared primitives from 3.2. A developer needing a primitive change reports it to PM and does not edit `shared/*`.
6. Live check at **1440×900** and **360×780**: no horizontal page scroll, panels as in 3.3, internal scroll only on `lg+`, modals centred and fully usable at 360, **zero console errors**, and loading/empty/error states checked where they can be reproduced.
7. A Russian log line in Section 6.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| T0 | **Shared primitives + DS docs.** Implement the primitives exactly per 3.2 (APIs are a contract for T1–T5). Add `hint` to `EmptyState`; restyle `StatTile`'s surface. Write DESIGN-SYSTEM §18 (+ pointers in §4 Modals, §13, §14). Do **not** change `PanelShell.tsx` markup/API. Don't migrate any tab. | Frontend Developer | DONE | NEW `shared/ProfileCard.tsx`, `shared/GoldIconFrame.tsx`, `shared/LoadingState.tsx`, `shared/ErrorState.tsx`, `shared/ModalShell.tsx`, `shared/ProgressBar.tsx`, `shared/PanelCounter.tsx`, `shared/PanelToolbar.tsx`, `shared/PanelScrollArea.tsx`; MODIFY `shared/EmptyState.tsx`, `shared/StatTile.tsx`; `docs/DESIGN-SYSTEM.md` | FEAT-165 DONE | CAC 1, 3, 7; APIs match 3.2 exactly. `ModalShell` uses `createPortal(…, document.body)`, `AnimatePresence`, Escape, `dismissible`, and works at 360 (max-h 90dvh, body scroll). Existing `EmptyState`/`StatTile` callers compile unchanged. §18 documents every primitive with a usage snippet, the composition rule, the portal rule, the colour mapping and the banned surfaces. |
| T1 | **Craft tab** per 3.3 "Craft": two-column layout (left «Мастерская»: buffs, rail, profession info, refining, socket extraction; right «Рецепты» with toolbar search + scroll grid) and the no-profession panel. Merge Gem/Rune sections into `SocketItemsSection`. Move all craft modals (incl. the shared `SharpeningModal`/`GemSocketModal` and the ProfessionRail/Select dialogs) to `ModalShell`. Map colours to tokens. | Frontend Developer | DONE | `CraftTab/CraftTab.tsx`, `ActiveBuffIndicator.tsx`, `ProfessionSelect.tsx`, `ProfessionRail.tsx`, `ProfessionInfo.tsx`, `RefiningSection.tsx`, `RefineModal.tsx`, `RecipeList.tsx`, `RecipeCard.tsx`, `CraftConfirmModal.tsx`, `GemSocketModal.tsx`, `SharpeningModal.tsx`; NEW `CraftTab/SocketItemsSection.tsx`; DELETE `CraftTab/GemSocketSection.tsx`, `CraftTab/RuneSocketSection.tsx` | T0 | CAC 1–7. Jeweler and enchanter show identical item lists before/after (incl. a legacy belt with a rune for the enchanter). Craft, refine, socket/extract and profession change/select all still work end-to-end. `SharpeningModal` and `GemSocketModal` opened from the **character tab's item context menu** render correctly at 1440/360. `InventoryTab/ItemContextMenu.tsx` has no diff. `grep -rn "GemSocketSection\|RuneSocketSection" src` → no hits. |
| T2 | **Skills + Perks** per 3.3. Skills: single panel with toolbar + grid, `ProfileCard`/`GoldIconFrame`, detail dialog → `ModalShell`; `ResolvedSkillCard` tokens/surfaces only. Perks: panel with header counter (auto height), shared states, `PerkDetailModal` → `ModalShell` + `ProgressBar` + tokens. **`PerkTree.tsx` and `PerkNode.tsx` must have zero diff.** | Frontend Developer | DONE | `SkillsTab/SkillsTab.tsx`, `SkillsTab/ResolvedSkillCard.tsx`, `PerksTab/PerksTab.tsx`, `PerksTab/PerkDetailModal.tsx` | T0 | CAC 1–7. `git diff --stat -- PerksTab/PerkTree.tsx PerksTab/PerkNode.tsx` is empty. **Before/after screenshots** of the Perks tab at 1440×900, 1024×768 and 360×780 (before = taken prior to any T2 edit): tree circle diameter is 760px at 1440 in both, and hub/branch node positions relative to the circle are identical. Paths + measurements are logged in Section 6. The BattlePage `SkillPicker` (uses `ResolvedSkillCard`) is checked live in a battle at 1440/360, with no layout break and no console errors. The skill detail modal opens, loads and shows its error state. |
| T3 | **Party + Gathering** per 3.3. Party: left «Отряд» panel with an identity-band header, member grid and actions; right column panels aligned; no-party two-panel layout. Gathering: single panel grid with `ProfileCard`/`GoldIconFrame`/`ProgressBar`. | Frontend Developer | DONE | `PartyTab/PartyTab.tsx`, `PartyHeaderCard.tsx`, `PartyMemberCard.tsx`, `PartyCreateCard.tsx`, `PartyInvitesPanel.tsx`, `InviteFromLocationPanel.tsx`, `GatheringTab/GatheringTab.tsx`, `GatheringTab/GatheringSkillCard.tsx` | T0 | CAC 1–7. All three party states are verified live: no party (create + invites), leader (rename, avatar upload, invite, disband confirm) and member (leave). Invited members appear dimmed. Gathering empty/loaded states are checked. |
| T4 | **Quests + Battles** per 3.3. Quests: `392px_1fr` master-detail, toolbar filters in the journal panel, `ProfileCard`/`GoldIconFrame`/`ProgressBar`. Battles: «Сводка» (active battle + 2×2 stats) + «История боёв» (toolbar filters, scroll list, pinned pagination footer); `ActiveBattleCard` fits 392px. | Frontend Developer | DONE | `QuestsTab/QuestsTab.tsx`, `QuestsTab/QuestDetail.tsx`, `QuestsTab/QuestJournalList.tsx`, `BattlesTab/BattlesTab.tsx`, `BattlesTab/ActiveBattleCard.tsx` (`questModel.ts` not touched) | T0 | CAC 1–7. Quests: select/complete/abandon (with confirm) and filters work; on mobile the detail shows under the journal when a quest is selected. Battles: the active-battle card (or its empty/error row), filters and pagination work; «перейти в бой» still navigates; the 392px column has no overflow with 4+ participants. |
| T5 | **Logs + Titles + page chrome** per 3.3. Logs: panel, `FilterChips` instead of `<select>` (same options/handler), token colours, shared states, load-more. Titles: panel + toolbar + `ProfileCard` variants (optional `TitleCard.tsx` extraction). `ProfileTabs`: underline token + nowrap. `ProfilePage`: `LoadingState` / `EmptyState`. | Frontend Developer | DONE | `LogsTab/LogsTab.tsx`, `TitlesTab/TitlesTab.tsx`, optional NEW `TitlesTab/TitleCard.tsx`, `ProfileTabs.tsx`, `ProfilePage.tsx` (**do not** remove `PlaceholderTab` here) | T0 | CAC 1–7. Logs: every filter value gives the same request as before; «Загрузить ещё» and «Показано X из Y» work; both empty texts are shown (filter / no filter). Titles: equip/unequip (if present) and the filters work; the variant mapping is 1:1 with the old `cardChrome`. The tab bar scrolls horizontally at 360 without wrapping. The profile loading and "Персонаж не найден" states render. |
| T6 | **Dead-code removal** (separate step, after all redesign tasks). Delete exactly: `InventoryTab/InventoryTab.tsx`, `CharacterInfoPanel/CharacterInfoPanel.tsx`, `CharacterInfoPanel/CharacterCard.tsx`, `EquipmentPanel/EquipmentPanel.tsx`, `StatsTab/StatsTab.tsx`, `StatsTab/ResourceStatsSection.tsx`, `PlaceholderTab.tsx`. In `ProfilePage.tsx`, remove the `PlaceholderTab` import and make the switch `default:` return `null`. **Keep** (still live): `CharacterInfoPanel/StatsPanel.tsx`, `CharacterInfoPanel/RestStatusPanel.tsx`, `EquipmentPanel/EquipmentSlot.tsx`, `EquipmentPanel/FastSlots.tsx`, `StatsTab/{PrimaryStatsSection,StatDistributionPanel,DerivedStatsSection}.tsx`, `constants.ts` (used by Admin/Auction/LocationPage). Before deleting, re-verify each file has no importer (`grep -rnE "from ['\"].*/(InventoryTab/InventoryTab\|CharacterInfoPanel/CharacterInfoPanel\|CharacterCard\|EquipmentPanel/EquipmentPanel\|StatsTab/StatsTab\|ResourceStatsSection\|PlaceholderTab)['\"]" src`, noting that `UserProfilePage/CharactersSection.tsx` has an unrelated local `CharacterCard`). If deletion leaves exports in `ProfilePage/constants.ts` or redux selectors with no users, **list them in the log but don't delete them** (out of scope). Also update any doc that names the deleted files (`docs/` grep). | Frontend Developer | DONE | the 7 files above (DELETE), `ProfilePage.tsx`, docs mentioning them (if any) | T1, T2, T3, T4, T5 | CAC 1, 6, 7. After deletion, the grep above only matches the unrelated `UserProfilePage` local component. All 10 tabs still render. `git status` shows exactly these deletions plus the `ProfilePage.tsx` edit (+ docs). |
| T7 | **Final review.** Check that 3.1–3.3 are met tab by tab, CAC for each task, the security checklist (no new data flows), and that there are no QA tasks (frontend-only, justified). Re-run `npx tsc --noEmit` + `npm run build` in the container. **Live verification** of all 10 tabs at 1440×900 and 360×780, including: every modal (incl. Sharpening/GemSocket from the character tab and `SkillPicker` on BattlePage); the perk tree geometry, re-checked against T2's before-screenshots; zero console errors; no horizontal scroll. Grep the whole `ProfilePage/` for banned surfaces, in-place `modal-overlay` and `React.FC`. Confirm DESIGN-SYSTEM §18 matches the implemented primitives. | Reviewer | DONE | — | T0–T6 | Review log in Section 5 with command outputs + screenshots list. PASS only if all of the above hold. |
| T8 | **«История постов» becomes a real profile tab** (post-review addition, user request). Extract the content of `src/components/pages/PostHistoryPage/PostHistoryPage.tsx` into `PostHistoryTab/PostHistoryTab.tsx` restyled to §18 (`PanelShell` + header icon/title/counter, `PanelScrollArea`, `ProfileCard` post cards, `LoadingState`/`ErrorState`/`EmptyState`); add a `posts` tab to `ProfileTabs` (no external-link styling, `characterId` prop dropped) and to the `ProfilePage` switch; `PostHistoryPage` keeps its Back-link chrome and reuses the same component so `/post-history/:characterId` keeps working. No change to fetched data or Russian strings. | Frontend Developer | DONE | `PostHistoryTab/PostHistoryTab.tsx` (NEW), `ProfileTabs.tsx`, `ProfilePage.tsx`, `src/components/pages/PostHistoryPage/PostHistoryPage.tsx` | T7 | CAC 1–7. Switching to the tab does not navigate; no Back button in the tab; the standalone URL still renders the same list; `grep -rn "post-history" src` shows no other link left broken. |

---

## 5. Review Log (filled by Reviewer — in English)

**Verdict: PASS** (T7, 2026-09-18). Frontend-only feature confirmed: `git status` touches only
`services/frontend/app-chaldea/src/components/ProfilePage/**`, `docs/DESIGN-SYSTEM.md`,
`docs/ISSUES.md` and this feature file — **zero backend Python files**, so no pytest/QA task is
required (CLAUDE.md: QA is mandatory only when backend Python changes). 46 files changed,
+2376 / -3307.

#### Automated Check Results
- `npx tsc --noEmit` (inside the running `frontend` container, `/app`) — **PASS** (exit 0)
- `npm run build` (`vite build --outDir /tmp/rvdist`, same container) — **PASS** (exit 0, only the
  pre-existing >500 kB chunk-size warning; temporary outDir removed, repo `dist/` untouched)
- `py_compile` / `pytest` — **N/A** (no backend changes)
- `docker-compose config` — N/A (no compose / Nginx / env changes in this feature)
- Live verification (headless Chromium via Playwright container on `chaldea_default`) — **PASS**

#### Static / rule checks
- **Frozen files, zero diff:** `PerksTab/PerkTree.tsx`, `PerksTab/PerkNode.tsx`,
  `InventoryTab/ItemContextMenu.tsx`, `PanelShell.tsx` — `git diff --stat` empty for all four.
- **Banned surfaces** (CAC 4 grep over every touched file): no hits. The remaining hits inside
  `ProfilePage/` are all in untouched reference-tab files (`CharacterTab/AvatarEquipmentGrid.tsx`,
  `InventoryTab/ItemDetailModal.tsx`, `StatsTab/DerivedStatsSection.tsx`) — out of scope.
- **`React.FC` / `FunctionComponent`** — no occurrences in `ProfilePage/`.
- **In-place `modal-overlay`** — only `shared/ModalShell.tsx` (portaled) plus the two untouched
  reference modals (`ItemDetailModal`, `RepairModal`). No profile tab renders an overlay in place.
- **`animate-spin`** — only `shared/LoadingState.tsx` (+ untouched reference files).
- **No `.jsx` / `.css` / `.scss`** under `ProfilePage/`; no new dependencies
  (`package-lock.json` unchanged).
- **Dead code (T6):** all 7 files deleted, grep for importers is empty, `ProfilePage.tsx`
  `default:` returns `null`, and all 10 `TABS` keys are covered by the switch, so it is unreachable.
- **Socket merge (T1):** grep for `GemSocketSection|RuneSocketSection` → no hits;
  `SocketItemsSection` reproduces both deleted files 1:1 (gem: `JEWELRY_SOCKET_TYPES` +
  `socket_count > 0`, template socket count; rune: `RUNE_SOCKET_TYPES` + legacy `belt`,
  `max(socket_count, gems.length)`), same modal props, same Russian strings.
- **DESIGN-SYSTEM §18** matches the shipped primitives prop-for-prop (incl. `MotionProfileCard`,
  the `hasPaddingClass` class-conflict rule, the portal rule, the colour map, banned surfaces).

#### Live Verification Results
Account `chaldea@admin.com`, character 706. Test data was created for the run (items,
conversions, 3 jeweler recipes, 2 quests with objectives/progress, a 3-member party, a PvE
battle) and **fully removed afterwards**; profession / rank / XP, location and equipment restored.
Screenshots: `scratchpad/feat166/review/` (`d-*` = 1440x900, `m-*` = 360x780).

- **All 10 tabs at 1440x900 and 360x780** (`d-00..09-*.png`, `m-00..09-*.png`):
  `document.scrollWidth == innerWidth` on every tab at both widths (no horizontal page scroll),
  consistent gold `PanelShell` chrome with header band + counter everywhere, internal scroll only
  on `lg+`. **Zero console errors, zero pageerrors, zero 4xx/5xx** (only Vite HMR WebSocket noise).
- **Персонаж** (reference) unchanged; **Навыки** grid + skill dialog (`d4/m4-skill-modal.png`,
  Escape closes it); **Перки** panel; **Отряд** in all three states — leader with an invited
  (dimmed) member and the dashed free slot (`d-03`), member view (`d/m-party-member.png`) and the
  no-party two-panel view (`d/m-party-noparty.png`); **Сбор**; **Задания** list + detail with the
  selected card gold-active and the «готово к сдаче» chip moving into the toolbar on mobile
  (`m4-quest-detail.png`); **Бои** with a live battle — `ActiveBattleCard` fits the 392px column,
  ally/enemy tints, 2x2 stats, both filter rows, pinned pagination footer
  (`d/m-battles-active.png`); **Логи**; **Титулы**; **Крафт** with a profession
  (`d2-craft-loaded.png`, `m3-craft.png`).
- **Craft flows (jeweler):** change-profession dialog from the rail, refine dialog (+ «Макс.» and
  the summary), the gem extraction section and `GemSocketModal`, recipe search, craft confirm
  dialog — all open, close via X / backdrop / Escape / «Отмена», and fire **no unintended
  requests** (the captured non-GET request log is empty for every cancel path). The enchanter
  variant lists exactly «ТР166 Плащ 1/2 рун» and the legacy «ТР166 Пояс 1/1 рун» — identical to
  the old `RuneSocketSection`.
- **Shared modals from the Персонаж item menu:** «Заточить» → `SharpeningModal` and «Гнёзда» →
  `GemSocketModal` render correctly at 1440 and 360 (`m3-sharpen-modal.png`,
  `m3-sockets-modal.png`); measured rects stay inside the 360x780 viewport (top 40, bottom 740,
  width 328) — nothing clipped, the body scrolls and the footer buttons stack.
- **Battle page skill card:** `SkillPicker` → `ResolvedSkillCard` opens in its own modal at 1440
  and 360 with no console errors (`d/m-battle-skillcard.png`); the modal supplies the surface, so
  dropping the card's own wrapper is not a visible regression. The 360px horizontal overflow of
  the battle page itself reproduces and is **pre-existing** (already logged in `docs/ISSUES.md` as
  MEDIUM by PM; not introduced by this feature).
- **Logs filter parity (T5):** every chip issues exactly the old request —
  `…/logs?limit=50&offset=0` plus `&event_type=rp_post|pvp_battle|item_acquired|level_up`, and
  «Все» with no parameter. Same 5 options, same handler.
- **Perk tree geometry (T2, re-verified against T2's before-shots):** at 1440 and 1024 the circle
  is 760x760 and the SVG box is `[0,0,760,760]` both before and after; **all 100 node centres
  relative to the circle match exactly (0 diffs)**; at 360 the mobile list is 280x7588 with all
  100 button rects identical. Data: `scratchpad/feat166/before-measure.json` vs
  `scratchpad/feat166/review/review-measure.json`; shots `review-perks-{1440,1024,360}.png` and
  `review-perks-circle-{1440,1024}.png`.

#### Security checklist
No new endpoints, requests, params or data flows; no `dangerouslySetInnerHTML`; no secrets; no
auth / rate-limit surface touched. All error paths keep their Russian toasts and messages
(`ErrorState` renders «Повторить» only where a retry already existed), and nothing is silently
swallowed — the existing `toast.error` calls are intact.

#### Issues Found (none blocking)

| # | Severity | File:line | Description | Owner |
|---|---|---|---|---|
| 1 | MINOR | `BattlesTab/BattlesTab.tsx:447-460` | The `if (loading) return <spinner/>` early return is gone, so the two history filter rows are clickable during the very first load; a fast click can start a second `fetchHistory` concurrently with the initial one (previously impossible). Harmless in practice, but it is a behaviour change. | T4 |
| 2 | MINOR | `shared/ModalShell.tsx:57-64` | Escape now closes `SharpeningModal` / `GemSocketModal`, which had no Escape handler before. `InventoryTab/ItemDetailModal.tsx:188` has its own document-level Escape listener, so with the detail modal open behind, one Escape closes both. Verified not to throw; a UX nuance only. | T0 |
| 3 | NOTE | `CraftTab/RecipeCard.tsx:44` | `locked={!recipe.can_craft}` dims the whole card (`opacity-60`) and the icon's rarity ring was dropped — a new visual state vs. the old card. Looks deliberate; flagged for the user's taste. | T1 |
| 4 | NOTE | `PartyTab/PartyInvitesPanel.tsx:31` | The red "you have invites" badge became a neutral grey `PanelCounter`, weakening the urgency signal. | T3 |
| 5 | NOTE | `TitlesTab/TitleCard.tsx:26-30` | `ProgressBar` has no neutral variant, so condition bars on `common` titles are gold instead of the former white/60 (already logged by the developer in section 6). | T0/T5 |
| 6 | NOTE | `docs/DESIGN-SYSTEM.md:773` | §18 is inserted between §17 and «## 15. For AI Agents», continuing the file's pre-existing heading-order drift (14 → 16 → 17 → 18 → 15). Cosmetic. | — |

Environment note (not a code issue): while the live checks ran, another process on this dev
machine repeatedly mutated character 706 (profession switched to blacksmith, an item equipped,
one resource consumed, extra `parties` / `recipes` rows appearing). Every live check was therefore
re-seeded and re-verified immediately before its run, and the character's original state
(enchanter, rank 1, 0 XP, location NULL) has been restored.

---

### Review #2 (2026-09-18) — **PASS**

Scope: the two fixes from review #1, the new T8 «История постов» tab, and the approved perk-tree
rework (which supersedes the earlier "PerkTree byte-for-byte" rule).

#### Automated Check Results
- `npx tsc --noEmit` — **PASS** (exit 0); `npm run build` — **PASS** (exit 0, temp outDir, repo
  `dist/` untouched). Still frontend-only: no backend Python file is touched, so no pytest/QA.
- Rule greps on the newly changed files (`PostHistoryTab.tsx`, `TitleCard.tsx`, `BattlesTab.tsx`,
  `ProgressBar.tsx`, `PostHistoryPage.tsx`): no banned surfaces, no `React.FC`, no in-place
  `modal-overlay`, no new `.jsx/.css/.scss`. `PerkTree.tsx` keeps its documented exception
  (`bg-[#04041a]`, purple/emerald rarity classes) — the file is the §18 exception.
- The deleted asset has no references left: only `perksWheelBackdrop.png` is imported
  (`PerkTree.tsx:6`); `grep perksBackdrop` finds no path to the removed file.
- Dead helpers `lineHitsNode` / `distToSegment` are gone with no remaining references.
  `PerkNode.tsx` has no diff.

#### Fix verification (review #1 findings 1 and 5)
- **Battles filters during the initial load** — `BattlesTab.tsx:222-245` guards all three handlers
  with `if (loading) return`, and the toolbar gets `pointer-events-none opacity-50`
  (`:452`). Verified live under 4 s CDP latency: while the history request is in flight the chip's
  computed `pointer-events` is `none`, the panel spinner is up, and a **DOM-level `.click()` that
  bypasses pointer-events fires 0 `/battles/history` requests** — the handler guard holds. After
  the load the chips work normally (1 request, chip becomes active). Finding 1 → **fixed**.
- **Neutral progress bars** — `ProgressBar` gained `neutral` (`bg-white/60`), `TitleCard` maps
  `common → neutral`, and DESIGN-SYSTEM §18 documents it. Verified live with three seeded locked
  titles at 1440 and 360: common = `rgba(255,255,255,0.6)` (the pre-FEAT-166 white),
  rare = `rgb(118,166,189)`, legendary = gold gradient. Finding 5 → **fixed**.

#### T8 «История постов»
- `PostHistoryTab.tsx` is a faithful move of the old page body: same `fetchPostHistory` call, same
  200-char preview cut, same «Показать полностью» / «Свернуть» toggle, same date format, same
  «Постов пока нет» text (plus a new hint line, consistent with the Logs empty state), same
  `char_count` / `xp_earned` row. `PostHistoryPage.tsx` is now a thin wrapper that keeps «Назад к
  профилю» and delegates to the tab component; an invalid id renders `EmptyState`
  «Персонаж не найден».
- `ProfileTabs.tsx` now carries `{ key: 'posts', label: 'История постов' }` between «Логи
  персонажа» and «Титулы», the external `<Link>` and the `characterId` prop are gone, and
  `ProfilePage.tsx` routes `case 'posts'`.
- Live (3 seeded posts, one long, one with markup): tab renders in panel style with the counter,
  cards show the location link, date, char count and XP, expand/collapse works, and the standalone
  `/post-history/706` shows the same panel with the back link. Checked at 1440 and 360 — no
  horizontal scroll, zero console errors, no 4xx/5xx. `/post-history/abc` → «Персонаж не найден».

#### Perk tree rework
- Code: `BRANCH_BEARING` is now the even star (`-90 / -18 / 54 / 126 / -162`), `TREE_HALF = 566.4`
  is fixed, tiers are derived from the art's own rings (`ART_DISC_FRACTION 0.172`,
  `ART_RING_FRACTION 0.876`) with `MIN_NODE_SPACING = HEX_SIZE * 2.3`, `MAX_TIERS = 7`, and
  `BOUNDARY_CLEARANCE = 22` keeping fans out of the sector corridors.
- Measured live at 1440 and 1024 (`r2b-perks-circle-{1440,1024}.png`, wheel screenshotted only
  after `img.decode()`):
  - 100 nodes, 20 per branch, **every node's stroke colour maps to its own category** (0 unknown);
  - per branch, max angular offset from the sector centre is **30.44°**, i.e. **5.56° of clearance**
    to the 36° boundary — no node sits on a divider, every fan stays on its own colour;
  - 5 tiers at radii 94 / 146 / 199 / 252 / 305 (1/3/4/5/7 fan), identical for all five branches;
  - closest pair of node centres = 52.8 px against a 40.2 px node (**ratio 1.31**) — no overlap;
  - outermost extent 324.8 px inside the 380 px circle radius — **no clipping**, rim rings clear;
  - hub offset from the circle centre **(0, 0)**; the art is 818 px on a 760 px circle at offset
    (-28, -15), i.e. the painted inner disc is centred on the hub;
  - the 360 list variant is unchanged (280 × 7588 with 100 buttons, exactly the pre-rework
    baseline).
- Perk dialog and unlock flow: the modal opens from a wheel node and from the mobile list, shows
  rarity/category/conditions with `ProgressBar`, and closes on Escape. A perk granted via
  `POST /attributes/admin/perks/grant` immediately shows as unlocked — the panel counter goes to
  `3/100`, the node gains its unlocked ring (polygon histogram 97×2 / 3×3), and the dialog reads
  «Разблокирован · 17.09.2026 · Выдан администратором». The grant was revoked afterwards.
- Zero console errors / 4xx / 5xx on every perks view at 1440, 1024 and 360.

#### Issues Found in review #2 (none blocking)

| # | Severity | File:line | Description | Owner |
|---|---|---|---|---|
| 7 | NOTE | `src/assets/perksWheelBackdrop.png` | The new wheel art is 2.3 MB (1254×1254 PNG) and is imported into the bundle. On a cold load the wheel visibly paints in after the nodes (my first screenshot caught it half-decoded). Worth compressing (WebP / smaller raster) if perk-tab load speed matters. | T2 |
| 8 | NOTE | `PerksTab/PerkTree.tsx:1-2`, `PerksTab.tsx:1-2`, `docs/DESIGN-SYSTEM.md:908` | Comments and §18 still describe the perk tree as "frozen / do not touch" and as an exception only for its raw colours, although the layout was deliberately reworked in this iteration. Worth a one-line refresh so the next agent does not treat the file as untouchable. | T2 |
| 9 | NOTE | `ProfilePage/PostHistoryTab/PostHistoryTab.tsx:79` | Post bodies are still injected with `dangerouslySetInnerHTML` — unchanged from the old page (player-authored RP HTML), so not a regression, but it stays the one XSS-relevant spot in the profile. | — |

Environment note: `docs/ISSUES.md` in this working tree also carries unrelated FEAT-167 analyst
edits; only the battle-page 360px entry belongs to FEAT-166. The dev machine's other process again
switched character 706 to blacksmith during this pass — restored to enchanter (rank 1, 0 XP);
all review #2 test data (3 posts, 3 locked titles, the granted perk) was removed.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-18 02:00 — PM: фича создана, запускаю анализ (параллельно с ревью FEAT-165, анализ read-only)
[LOG] 2026-09-18 02:40 — Analyst: разобрана структура профиля (10 вкладок), эталон — вкладка «Персонаж» (PanelShell); SCSS и .jsx в профиле нет, задача сводится к Tailwind-классам и композиции
[LOG] 2026-09-18 02:45 — Analyst: найдены мёртвые компоненты (InventoryTab, CharacterInfoPanel/CharacterCard, EquipmentPanel, StatsTab/ResourceStatsSection), общие модалки (заточка/камни) и ResolvedSkillCard, который используется и на странице боя
[LOG] 2026-09-18 02:50 — Analyst: анализ завершён, предложено разбиение на задачи T0–T6 (сначала общие примитивы) и 6 продуктовых вопросов
[LOG] 2026-09-18 02:40 — PM: пользователь ответил на вопросы аналитика (раздел 1 обновлён); архитектор запускается после закрытия FEAT-165
[LOG] 2026-09-18 03:10 — Architect: начал проектирование (база — текущее рабочее дерево с FEAT-165)
[LOG] 2026-09-18 03:40 — Architect: спроектированы общие примитивы (ProfileCard, GoldIconFrame, LoadingState/ErrorState, ModalShell через портал, ProgressBar, PanelCounter/PanelToolbar/PanelScrollArea) и раскладки всех 9 вкладок; новых API и токенов нет
[LOG] 2026-09-18 03:45 — Architect: 8 задач (T0 примитивы → T1–T5 параллельно без пересечения файлов → T6 удаление мёртвого кода → T7 ревью); QA-задач нет — бэкенд не меняется; дерево перков заморожено, обязательны скриншоты до/после
[LOG] 2026-09-18 04:00 — Frontend Dev: T0 начат — общие примитивы профиля
[LOG] 2026-09-18 04:30 — Frontend Dev: созданы shared/ProfileCard (+MotionProfileCard, forwardRef), GoldIconFrame, LoadingState, ErrorState, ModalShell (портал в body, AnimatePresence, Escape, dismissible), ProgressBar, PanelCounter, PanelToolbar, PanelScrollArea; EmptyState получил hint, StatTile — плоская поверхность ProfileCard; API совпадает с 3.2
[LOG] 2026-09-18 04:35 — Frontend Dev: ModalShell — панели добавлены !overflow-visible (иначе overflow-x:hidden у modal-content обрезает золотую рамку) и !animate-none (анимацию ведёт motion, а не CSS fade-in); на API не влияет
[LOG] 2026-09-18 04:40 — Frontend Dev: DESIGN-SYSTEM.md — добавлен §18 «Profile Panels» (PanelShell, правило композиции, toolbar+scroll, таблица примитивов с примерами, правило портала, токены статусов, запрещённые поверхности), ссылки из §4, §13, §14
[LOG] 2026-09-18 04:50 — Frontend Dev: проверки в одноразовом контейнере frontend: npx tsc --noEmit — OK, npm run build — OK; package-lock.json не изменён, контейнеров не осталось; T0 готов, T1–T5 можно запускать
[LOG] 2026-09-18 06:10 — Frontend Dev: T5 готов — Логи и Титулы перенесены в PanelShell (тулбар + скролл-область), <select> в логах заменён на FilterChips (те же 5 опций и тот же обработчик), карточка титула вынесена в TitlesTab/TitleCard.tsx; ProfileTabs — золотое подчёркивание и nowrap; ProfilePage — LoadingState/EmptyState
[LOG] 2026-09-18 06:10 — Frontend Dev: T5 — в ProgressBar нет нейтрального (белого) варианта, полоски условий у обычных титулов теперь золотые; проверки в одноразовом контейнере: tsc --noEmit — OK, npm run build — OK, package-lock.json не изменён; визуальную проверку в браузере сделать не удалось (нет браузерного инструмента), Vite отдаёт изменённые модули без ошибок
[LOG] 2026-09-18 05:30 — Frontend Dev (T3): «Отряд» — левая панель PanelShell (счётчик в шапке, шапка отряда как identity-band с GoldIconFrame, секция «Участники», карточки ProfileCard, пунктирные свободные слоты border-white/15, кнопки w-full sm:w-auto); справа панели приглашений (PanelCounter, ProfileCard, GoldIconFrame; при двух панелях — lg:max-h половины высоты); без отряда — сетка из двух панелей, заголовок «Создать отряд» перенесён в шапку панели; загрузка — LoadingState внутри панели «Отряд»
[LOG] 2026-09-18 05:35 — Frontend Dev (T3): «Сбор» — одна панель «Навыки сбора» (счётчик, PANEL_DESKTOP_HEIGHT_CLASS, сетка 1/2/3 колонки), загрузка и пустое состояние внутри панели; GatheringSkillCard → ProfileCard + GoldIconFrame 52 + ProgressBar (макс. ранг = полная полоса, как раньше)
[LOG] 2026-09-18 05:40 — Frontend Dev (T3): одноразовый контейнер: npx tsc --noEmit — OK, npm run build — OK; grep запрещённых поверхностей/цветов по файлам T3 пуст; package-lock.json не изменён; dev-сервер Vite отдаёт все 8 модулей без ошибок. Визуальная проверка 1440/360 в браузере НЕ выполнена — браузерные инструменты недоступны в сессии, оставлено ревьюеру (T7)
[LOG] 2026-09-18 05:50 — Frontend Dev (T4): «Задания» — сетка 392px_1fr, панели «Задания» (фильтры в PanelToolbar, список в PanelScrollArea, счётчик + чип «готово к сдаче», на мобильном чип уходит в тулбар) и «Детали»; строки журнала — MotionProfileCard + GoldIconFrame + ProgressBar; в деталях GoldIconFrame, ProgressBar, спиннеры кнопок → LoadingState xs; загрузка/ошибка (с прежним «Повторить») внутри панели
[LOG] 2026-09-18 05:55 — Frontend Dev (T4): «Бои» — панели «Сводка» (Текущий бой + статистика 2×2, счётчик) и «История боёв» (два ряда фильтров в тулбаре, строки ProfileCard с цветной полосой результата, закреплённый футер пагинации, кнопки 36px); ActiveBattleCard — плоский ProfileCard danger, вертикальная раскладка, участники ProfileCard (союзники синие, враги красные), аватары GoldIconFrame 40
[LOG] 2026-09-18 06:00 — Frontend Dev (T4): одноразовый контейнер: npx tsc --noEmit — OK, npm run build — OK; grep запрещённых поверхностей/цветов/спиннеров по файлам T4 пуст; package-lock.json не изменён, контейнеров не осталось; Vite отдаёт 5 модулей без ошибок. Проверка 1440/360 в браузере НЕ выполнена — браузерные инструменты недоступны, оставлено ревьюеру (T7)
[LOG] 2026-09-18 06:10 — Frontend Dev (T1): «Крафт» — без профессии одна панель «Выбор профессии» (баффы в шапке, карточки MotionProfileCard + GoldIconFrame 56, сетка 1/2/3); с профессией сетка 392px_1fr: слева «Мастерская» (баффы, рейка, ProfessionInfo без своей карточки с GoldIconFrame 52 + ProgressBar, «Переработка», извлечение), справа «Рецепты» (счётчик, поиск в PanelToolbar, сетка в PanelScrollArea, RecipeCard → ProfileCard locked + GoldIconFrame 48); загрузка/ошибка/пусто — общие состояния
[LOG] 2026-09-18 06:15 — Frontend Dev (T1): GemSocketSection + RuneSocketSection объединены в SocketItemsSection (variant gem/rune, фильтрация и подсчёт гнёзд как раньше, руны — text/bg-rarity-epic), старые файлы удалены; все модалки (подтверждение крафта, переработка, камни, заточка, выбор/смена профессии) → ModalShell; зелёные/красные → stat-energy/site-red; ItemContextMenu.tsx не тронут
[LOG] 2026-09-18 06:20 — Frontend Dev (T1): одноразовый контейнер: npx tsc --noEmit — OK, npm run build — OK; grep запрещённых поверхностей/цветов/спиннеров/modal-overlay по CraftTab пуст, упоминаний GemSocketSection/RuneSocketSection нет; package-lock.json не изменён; Vite отдаёт все 13 модулей + ItemContextMenu без ошибок. Проверка 1440/360 и открытие модалок заточки/гнёзд из вкладки «Персонаж» в браузере НЕ выполнены — браузерные инструменты недоступны, оставлено ревьюеру (T7)
[LOG] 2026-09-18 06:00 — Frontend Dev: T0-доработка — ProfileCard выдаёт ровно одну пару рамка/фон (active > accent/danger > default, у активной карточки нет hover-подсветки); LoadingState/EmptyState/ErrorState и тело ModalShell не ставят свой padding, если вызывающий передал любой padding-класс (shared/classUtils.ts); API не менялся, `!`-переопределения работают; §18 дополнен разделом про конфликты классов; tsc и build — OK (SkillsTab.tsx T2 в процессе правки не компилируется, проверка шла на копии с его HEAD-версией)
[LOG] 2026-09-18 21:10 — Frontend Dev: T2 начат; скриншоты ДО сняты (Перки 1440/1024/360, Навыки и окна 1440/360) в scratchpad/feat166/before-*.png, замеры в before-measure.json
[LOG] 2026-09-18 21:40 — Frontend Dev: Навыки — одна панель «Навыки» (счётчик фильтр/всего, чип очков перков; на мобиле чип уходит в тулбар), тулбар с фильтрами и кнопкой дерева, сетка ProfileCard + GoldIconFrame, окно навыка через ModalShell; ResolvedSkillCard — токены, ProfileCard, общий SectionHeader, GoldIconFrame, без своей подложки (фон даёт модалка); пропсы не менялись
[LOG] 2026-09-18 21:45 — Frontend Dev: Перки — панель «Перки» (Star, счётчик открытых/всех, авто-высота), загрузка/ошибка внутри панели; на мобиле тело панели без отступа (p-0 md:p-4 lg:p-5), т.к. у мобильного списка дерева свой p-4 — ширина списка не меняется; PerkDetailModal → ModalShell (название в шапке) + ProgressBar + токены
[LOG] 2026-09-18 22:20 — Frontend Dev: геометрия дерева: PerkTree.tsx/PerkNode.tsx без диффа; круг 760×760 на 1440 и 1024 до и после, центры всех 100 узлов относительно круга совпадают 1:1, мобильный список 280px и позиции 100 кнопок совпадают (after-measure.json, after-perks-*.png, diff-circle-*.png — отличия только в фоне страницы за полупрозрачным верхом арта и в анимации свечения)
[LOG] 2026-09-18 22:30 — Frontend Dev: SkillPicker на странице боя проверен вживую на 1440/360 (after-battle-skillcard-*.png), ошибок в консоли нет; для проверки временно ставил персонажу 706 локацию 57, создавал бои с NPC 49 и завершал их (бои 200–204 завершены, локация возвращена в NULL). Обнаружено: на 360px страница боя сама по себе вылезает по ширине, карточки бойцов перекрывают слоты (не связано с T2) — передано PM для ISSUES.md
[LOG] 2026-09-18 22:40 — Frontend Dev: учтена доработка T0 (padding в bodyClassName заменяет дефолтный); tsc --noEmit и build в одноразовом контейнере — OK, package-lock.json не изменён, контейнеров не осталось; T2 готов
[LOG] 2026-09-18 23:00 — Frontend Dev: T6 — перед удалением grep: импортёры мёртвых файлов были только внутри самого мёртвого набора (InventoryTab → CharacterInfoPanel/EquipmentPanel, CharacterInfoPanel → CharacterCard, StatsTab → ResourceStatsSection), PlaceholderTab — только в ProfilePage; админский tabs/InventoryTab — другой файл
[LOG] 2026-09-18 23:05 — Frontend Dev: T6 — удалены InventoryTab/InventoryTab.tsx, CharacterInfoPanel/CharacterInfoPanel.tsx, CharacterInfoPanel/CharacterCard.tsx, EquipmentPanel/EquipmentPanel.tsx, StatsTab/StatsTab.tsx, StatsTab/ResourceStatsSection.tsx, PlaceholderTab.tsx; в ProfilePage убран импорт PlaceholderTab, default → null; пустых папок не осталось (FastSlots, EquipmentSlot, StatsPanel, RestStatusPanel и секции статов на месте); в docs/ упоминаний нет; осиротевших экспортов constants.ts и селекторов нет (CLASS_NAMES, selectEquipmentSlots и др. используются дальше)
[LOG] 2026-09-18 23:10 — Frontend Dev: T6 — повторный grep по src пуст; одноразовый контейнер: tsc --noEmit — OK, npm run build — OK; package-lock.json не изменён, контейнеров не осталось; T6 готов
[LOG] 2026-09-18 23:40 — Reviewer: статус REVIEW; подтверждено, что бэкенд не тронут (только ProfilePage/**, docs/DESIGN-SYSTEM.md, docs/ISSUES.md) — pytest не требуется
[LOG] 2026-09-18 23:55 — Reviewer: в контейнере frontend npx tsc --noEmit — OK, npm run build — OK (сборка во временный outDir, dist репозитория не тронут); PerkTree/PerkNode/ItemContextMenu/PanelShell — нулевой дифф; grep запрещённых поверхностей, React.FC, непортального modal-overlay и самодельных спиннеров по затронутым файлам — пусто
[LOG] 2026-09-19 00:35 — Reviewer: живая проверка всех 10 вкладок на 1440x900 и 360x780 (скриншоты в scratchpad/feat166/review): горизонтального скролла нет, панели единообразны, ошибок в консоли и 4xx/5xx нет; проверены окна навыка, перка и крафта (смена профессии, переработка, гнёзда, подтверждение), заточка и гнёзда из вкладки «Персонаж», карточка навыка на странице боя, все три состояния отряда, детали задания
[LOG] 2026-09-19 00:45 — Reviewer: чипы фильтров логов дают те же запросы, что старый select (event_type rp_post/pvp_battle/item_acquired/level_up и без параметра для «Все»); SocketItemsSection у зачарователя показывает плащ и легаси-пояс с руной — как старая RuneSocketSection
[LOG] 2026-09-19 00:50 — Reviewer: геометрия дерева перков совпадает с замерами ДО: круг 760x760 и SVG-бокс идентичны на 1440 и 1024, все 100 центров узлов без отличий, мобильный список 280x7588 и 100 кнопок 1:1
[LOG] 2026-09-19 01:00 — Reviewer: тестовые данные (предметы ТР166, конверсии, рецепты, 2 задания, отряд, бой) удалены, персонажу возвращены профессия «Зачарователь» (ранг 1, 0 XP), локация NULL и экипировка; вспомогательный docker-образ удалён, контейнеров не осталось
[LOG] 2026-09-19 01:05 — Reviewer: ревью PASS, раздел 5 заполнен; 6 замечаний без блокировки (фильтры «Боёв» кликабельны во время первой загрузки, Escape теперь закрывает общие окна заточки/гнёзд, затемнение недоступного рецепта, серый счётчик приглашений вместо красного, золотые полосы условий у обычных титулов, порядок §18 в DESIGN-SYSTEM)
[LOG] 2026-09-18 12:20 — Reviewer: ревью #2 — tsc --noEmit и npm run build в контейнере снова OK; grep по новым файлам (PostHistoryTab, TitleCard, BattlesTab, ProgressBar, PostHistoryPage) чист, старый perksBackdrop.png нигде не используется, PerkNode без диффа, мёртвые хелперы удалены без остатков
[LOG] 2026-09-18 12:35 — Reviewer: правки по замечаниям #1 проверены вживую: при задержке сети 4 с тулбар «Истории боёв» гасится (pointer-events-none), а DOM-клик в обход блокировки не даёт ни одного запроса — guard держит; полосы условий у обычных титулов снова белые (rgba(255,255,255,0.6)), у редких синие, у легендарных золотые
[LOG] 2026-09-18 12:50 — Reviewer: T8 проверен: вкладка «История постов» в панели (счётчик, карточки, ссылка на локацию, разворот длинного поста), отдельный /post-history/706 отдаёт тот же компонент с ссылкой «Назад к профилю», /post-history/abc — «Персонаж не найден»; 1440 и 360, без переполнения и без ошибок в консоли
[LOG] 2026-09-18 13:05 — Reviewer: дерево перков после переработки замерено на 1440 и 1024: 100 узлов по 20 на ветку, каждый узел своего цвета, максимальное отклонение от центра сектора 30.44° (запас до границы 5.56°), 5 ярусов (радиусы 94/146/199/252/305), минимальное расстояние между центрами 52.8 px при узле 40.2 px (нет наложений), крайний радиус 324.8 px внутри круга 380 px (нет обрезки), хаб в центре (0,0), арт 818 px на круге 760 px со смещением (-28,-15); мобильный список 280x7588 как и раньше
[LOG] 2026-09-18 13:15 — Reviewer: окно перка и разблокировка работают — выданный админом перк сразу виден (счётчик 3/100, кольцо на узле, в окне «Разблокирован · Выдан администратором»), перк отозван; тестовые посты и титулы удалены, профессия персонажа возвращена на «Зачарователь»
[LOG] 2026-09-18 13:20 — Reviewer: ревью #2 PASS; три новых замечания без блокировки (вес нового арта 2.3 МБ, устаревшие комментарии «дерево заморожено» в PerkTree/PerksTab/§18, сохранившийся dangerouslySetInnerHTML в постах — как было)
[LOG] 2026-09-18 06:30 — Frontend Dev (T4): фикс ревью — фильтры и пагинация «Истории боёв» больше не могут запустить параллельный запрос во время первичной загрузки: обработчики выходят при loading, тулбар на это время затемнён и не кликабелен (pointer-events-none); раскладка панелей и LoadingState сохранены; tsc --noEmit и npm run build в одноразовом контейнере — OK
[LOG] 2026-09-18 06:40 — Frontend Dev: ProgressBar получил вариант neutral (bg-white/60) для прогресса, который не должен читаться как награда; TitleCard вернул обычным титулам белую полосу условий (common: 'neutral'); §18 обновлён; tsc и build — OK
[LOG] 2026-09-19 02:10 — Frontend Dev (T8): «История постов» переведена из внешней ссылки в обычную вкладку профиля; контент вынесен в PostHistoryTab на §18-примитивы (PanelShell + счётчик, PanelScrollArea, ProfileCard, EmptyState/ErrorState/LoadingState), PostHistoryPage переиспользует его и сохраняет маршрут /post-history/:characterId; tsc --noEmit и npm run build в одноразовом контейнере — OK
[LOG] 2026-09-18 23:20 — Frontend Dev: диагностика рассинхрона арта и ветвей (старая картинка): развороту она не поддаётся — по кольцам узлов смещения секторов разного знака (внешнее кольцо: синий -16.9°, фиолетовый +23.0°, красный +7.4°, золотой -6.8°), лепестки — изогнутые «капли» неравной ширины (красный 73°, золотой 57°, синий 84°, зелёный 79°, фиолетовый 63°), а веер ветви — ровные 35°; из 100 узлов 3 оказывались на чужом цвете (внутренний фиолетовый — на красном, два внешних — на синем фоне неба)
[LOG] 2026-09-18 23:50 — Frontend Dev: по просьбе пользователя заменил фон перков на новую картинку (5 равных секторов): src/assets/perksWheelBackdrop.png; по посадке круга (МНК по ободу) центр колеса в файле — (621.7, 604.9) при центре изображения 626.5, поэтому ART_NUDGE_X=0.0038, ART_NUDGE_Y=0.0172, а обод на 0.930 полуразмера → ART_SCALE=1.0757 (обод садится на рамку). Секторы относительно этого центра: -162.0°, -89.5°, -18.0°, +52.0°, +125.0° — звезда 72° с точностью до 2°
[LOG] 2026-09-18 23:55 — Frontend Dev: соответствие ветвей и секторов: бой → красный (верх), торговля → золотой (вправо-вверх), исследование → синий (вправо-вниз), прогрессия → зелёный (влево-вниз), использование → фиолетовый (влево-вверх); все 100 узлов лежат на своём секторе (проверка по цвету арта вокруг каждого узла), минимальный зазор гексагона до границы сектора 4.3° (самый тесный — внешний узел торговли); поворот арта не нужен — оптимум -1° даёт лишь +0.8°
[LOG] 2026-09-19 00:05 — Frontend Dev: геометрия узлов не менялась — координаты всех 100 узлов относительно круга совпадают до знака с замерами до правки (before2-nodes.json ↔ after2-nodes.json, 1440 и 1024), PerkNode.tsx без диффа, круг 760×760; правки только в размещении арта в PerkTree.tsx (импорт, ART_NUDGE_*, ART_SCALE, комментарии); на 360px дерево показывает список без арта — без изменений; tsc и build в одноразовом контейнере — OK
[LOG] 2026-09-19 00:40 — Frontend Dev: BRANCH_BEARING сброшен на ровную звезду index*72-90 (бой -90, торговля -18, исследование 54, прогрессия 126, использование -162) — прежние значения были подогнаны под неровные лепестки старого арта; относительная раскладка внутри ветви, связи и круг 760px не менялись; старый ассет perksBackdrop.png удалён (ссылок на него в репозитории не осталось)
[LOG] 2026-09-19 00:55 — Frontend Dev: замер на отрендеренной странице (не по файлу): центр узлового круга (хаб) — (380.0, 380.0) в кропе 760×760, центр колеса по МНК-подгонке золотых обручей — внутренний (381.9, 379.7) R=65.2, внешний обод (379.2, 380.0) R=364.9, то есть расхождение (+1.9, -0.3) и (-0.8, 0.0) px — центры совпадают, вертикального сдвига нет. Впечатление «всё сидит выше» давали старые азимуты: торговля была на 8.5°, использование на 6.7° повёрнуты к красному сектору
[LOG] 2026-09-19 01:00 — Frontend Dev: после сброса азимутов все 5 ветвей симметричны: минимальный зазор гексагона до угловой границы сектора 12.8° у каждой (было 4.3–11.2°, самый тесный — торговля), внешний зазор до обода 28.1px у каждой, все 100 узлов лежат на своём цвете (проверка по цвету арта вокруг узла на самом рендере); кропы секторов до/после — sector-{before,after}-*.png; tsc и build в одноразовом контейнере — OK
[LOG] 2026-09-19 01:40 — Frontend Dev: данные перков не содержат ни тиров, ни предпосылок — в ответе /attributes/{id}/perks есть только id, name, category, rarity, conditions (has_perk не встречается ни разу), sort_order API вообще не отдаёт; связей в дереве не рисуется (функции lineHitsNode/distToSegment были мёртвым кодом, удалены). Поэтому «глубина» = порядок перков в ветви, как и раньше
[LOG] 2026-09-19 01:55 — Frontend Dev: раскладка перков переписана под секторы арта (v3): кадр фиксированный (TREE_HALF=566.4 — viewBox и посадка арта в px не изменились), полоса узлов идёт от диска в центре (0.172 half) до внутреннего обруча обода (0.876 half) с зазорами ART_CLEARANCE=20 и BOUNDARY_CLEARANCE=22 units, тиры равномерно по радиусу, количество узлов в тире пропорционально длине дуги (метод наибольших остатков), число тиров выбирается так, чтобы радиальный шаг был близок к угловому
[LOG] 2026-09-19 02:05 — Frontend Dev: проверка на рендере (1440): у каждой ветви 5 тиров на 94/146/199/252/305px с 1/3/4/5/7 узлами, все 100 узлов на своём цвете (замер по кольцу вплотную к гексагону), минимальное расстояние между центрами 52.8px при касании 25.6px (зазор 27.2px), до границы сектора 14.8px (2.8°), до центрального диска 13.6px, до внутреннего обруча обода 13.3px, до внешнего обода 45.4px — одинаково во всех пяти секторах; мобильный список не менялся; tsc и build — OK
[LOG] 2026-09-19 02:30 — Frontend Dev: замерены три центра арта по отдельности (МНК): обруч центрального диска в файле — (625.5, 605.8) r=96.9, невязка 1.0px; обод — (624.8, 620.3) r=581.8, невязка 0.7px (то есть сама картинка не концентрична: диск на 14.4px выше обода); точка схода пяти лучей ненадёжна — при исключении одного луча она гуляет на 11–12px, парные пересечения разлетаются от (352,353) до (405,361), так что ориентироваться на неё нельзя
[LOG] 2026-09-19 02:40 — Frontend Dev: арт выровнен по обручу диска (именно его глаз сравнивает с шестиугольником «ПЕРКИ»): ART_NUDGE_X 0.0038 → 0.0008, ART_NUDGE_Y 0.0172 → 0.0165, масштаб и раскладка не тронуты. На рендере (1440) центр обруча диска теперь (379.4, 379.5) против хаба (380, 380) — расхождение 0.8px (было +1.85px по X); обручи обода: внутренний (379.9, 376.9) r=330.7, внешний (378.2, 376.3) r=359.6 — максимальный вылет 363px при радиусе кадра 380px, то есть ничего не обрезается
[LOG] 2026-09-19 02:45 — Frontend Dev: после сдвига все 100 узлов на своём цвете (кольцо вплотную к гексагону), зазоры прежние: до границы сектора 14.8px, до диска 13.6px, до внутреннего обруча обода 13.3px, между узлами 52.8px; границы секторов по-прежнему проходят по пустым коридорам между веерами; скриншоты hub-before-1440.png / hub-after-1440.png (зум 3x с перекрестием на хабе), v5-crop-1440.png, v5-page-{1440,1024,360}.png; tsc и build — OK
[LOG] 2026-09-18 14:30 — PM: ревью #2 PASS, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Все вкладки профиля приведены к стилю первой вкладки: содержимое в золотых панелях с шапкой (иконка, название, счётчик), длинные списки прокручиваются внутри панели на компьютере, на мобильных прокручивается страница.
- Переделаны: Навыки, Перки, Отряд, Сбор, Задания, Бои, Логи, Титулы, Крафт, полоска вкладок и состояния загрузки страницы.
- Общие детали оформления вынесены в переиспользуемые компоненты (карточка, рамка иконки, состояния загрузки/ошибки/пустого списка, окно через портал, полоса прогресса, панельные обёртки) и описаны в `docs/DESIGN-SYSTEM.md` §18.
- Крафт разложен в две колонки: слева «Мастерская» (профессия, переработка, извлечение), справа «Рецепты» с поиском. Разделы извлечения ювелира и зачарователя объединены в один компонент. Все окна крафта, заточки и гнёзд — на общем окне с закрытием по Escape.
- В «Логах» выпадающий список заменён кнопками-фильтрами (те же варианты и тот же запрос).
- «История постов» стала обычной вкладкой профиля; отдельный адрес `/post-history/:characterId` работает и использует тот же компонент.
- Перки: новая подложка (пять ровных секторов по 72°), ветки выровнены по 72°, узлы разложены дугами по 5 уровням (1/3/4/5/7) и заполняют клин, подложка выровнена по внутреннему кругу (0,8 px от центра). Все 100 узлов лежат на своём цвете, ничего не обрезано, мобильный список не изменился.
- Удалены 7 неиспользуемых компонентов профиля и мёртвый код проверки линий в дереве перков.

### Что изменилось от первоначального плана
- Дерево перков изначально планировалось не трогать; по просьбе пользователя раскладку переделали под форму секторов, а подложку заменили на новую картинку.
- Добавлена задача T8 («История постов» как вкладка) по просьбе пользователя.
- Выяснилось, что у перков нет уровней и зависимостей, а связи между ними никогда не рисовались: уровень определяется порядком выдачи с сервера.

### Оставшиеся риски / follow-up задачи
- Картинка подложки перков весит 2,3 МБ и на холодной загрузке появляется позже узлов — можно сжать (WebP).
- Тексты постов выводятся как HTML (`dangerouslySetInnerHTML`) — не регрессия, но единственное такое место в профиле.
- Если у перков появятся настоящие уровни и требования, раскладка готова считать уровни по ним.
- В `docs/ISSUES.md` добавлен баг: страница боя на 360px вылезает за экран и карточки бойцов перекрывают слоты навыков (предсуществующий).
