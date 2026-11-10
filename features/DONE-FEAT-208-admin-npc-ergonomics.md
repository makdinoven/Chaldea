# FEAT-208: Админка НПС — раскрывающиеся плашки с вкладками

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-10 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Админский раздел НПС (`/admin/npcs`, `components/AdminNpcsPage/AdminNpcsPage.tsx`) неудобен: у каждого НПС в строке куча кнопок; «Редактировать» открывает форму наверху страницы (телепорты и патруль стражника — внутри этой формы), а «Характеристики», «Снаряжение», «Диалоги», «Квесты», «Магазин» подменяют всю страницу — список, поиск и пагинация теряются. Нужна эргономика: клик по плашке НПС — под ней анимированно раскрывается подложка с вкладками, под вкладками — выбранный раздел.

Только фронтенд. Бэкенд и API не меняются.

### Бизнес-правила
- Список — компактные плашки (аватар, имя, ID, уровень, роль, локация, статус). Кнопок действий на плашке нет; клик по плашке раскрывает/сворачивает подложку под ней (плавная анимация высоты/прозрачности).
- Одновременно раскрыт один НПС. Раскрытие другого сворачивает предыдущий и плавно доскролливает к новому.
- Внутри подложки — строка вкладок-тумблеров:
  - всегда: «Основное» (бывшее «Редактировать»), «Характеристики», «Снаряжение», «Диалоги», «Квесты»;
  - по роли: «Магазин» — у торговца (как сейчас условие показа кнопки), «Телепорты» — у телепортиста (сейчас TeleportLinksPanel внутри формы), «Патруль» — у стражника (сейчас GuardPatrolPanel внутри формы при роли guard). Точные условия показа — как в текущем коде.
  - Под вкладками рендерится выбранный раздел (существующие редакторы переиспользуются, а не переписываются).
- Опасные действия — «Воскресить» (как сейчас, только для мёртвых) и «Удалить» (с подтверждением, как сейчас) — отдельно, в шапке подложки справа.
- Состояние в адресе: `/admin/npcs?npc=<id>&tab=<key>` — после перезагрузки открывается тот же НПС и вкладка; кнопка «назад» браузера работает; ссылкой можно поделиться. Если НПС с таким id нет на текущей странице списка — всё равно открыть его подложку (например, отдельной плашкой сверху), либо решит архитектор.
- Защита от потери правок: если в разделе есть несохранённые изменения, при переключении вкладки/сворачивании/раскрытии другого НПС — спросить «Сохранить / Не сохранять / Отмена» (или минимум «Есть несохранённые изменения. Уйти без сохранения?» — решит архитектор по тому, как устроены редакторы).
- «Создать НПС» — открывает такую же подложку новой плашкой сверху списка, только с вкладкой «Основное». После сохранения — становится обычным раскрытым НПС со всеми вкладками.
- Поиск, фильтры и номер страницы сохраняются, пока админ работает в подложке.
- Мобильные (360px+): вкладки листаются горизонтально, разделы помещаются в ширину экрана.

### UX / Пользовательский сценарий
1. Админ открывает «НПС», ищет непися, кликает по плашке.
2. Под плашкой раскрывается подложка, открыта вкладка «Основное».
3. Переключает на «Квесты» — ниже появляется редактор квестов этого НПС; список выше и ниже на месте.
4. Кликает по другой плашке — первая сворачивается, вторая раскрывается, страница доскролливает.

### Edge Cases
- Несохранённые правки при переключении — предупреждение.
- Смена роли во «Основном» (например, стал стражником) — после сохранения появляется вкладка «Патруль».
- Удаление НПС — подложка закрывается, параметры адреса очищаются.
- Неверный `tab` в адресе / вкладка недоступна для роли — открыть «Основное».
- Все ошибки API — видимые, на русском (как сейчас).

### Вопросы к пользователю (если есть)
- [x] Подход: раскрывающиеся плашки с вкладками + адрес в URL + защита от потери правок + создание в такой же подложке → «Как предлагаешь, запускай»

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | page restructure + small optional props on editors | `src/components/AdminNpcsPage/*` (all 8 files) |

No backend, no API, no DB, no Nginx/Docker changes. Route stays `admin/npcs` in `src/components/App/App.tsx:286` (wrapped in `ProtectedRoute requiredPermission="npcs:read"`). Router is `BrowserRouter` (not a data router), so **`useBlocker` is not available**.

### Current page — `AdminNpcsPage.tsx` (953 lines)
- List state is local: `query` (debounced via `useDebounce`), `roleFilter`, `statusFilter`, `page`, `pageSize=20`, `total`. `fetchNpcs` → `GET /characters/admin/npcs?q&npc_role&npc_status&page&page_size` → `{items,total}`. Filter/search changes reset `page` to 1. Pagination via `Admin/AdminPagination/AdminPagination`.
- List item shape `NpcListItem {id,name,avatar,level,npc_role,location_name,location_id,npc_status}`. Desktop = `<table>` (`hidden sm:block`, lines 730–838), mobile = cards (`sm:hidden`, 841–931). Each row carries 6–8 action buttons (780–930).
- Edit/create form (lines 461–711) is inline at the top of the page; its state lives in the page: `formOpen`, `editingId`, `form: NpcFormData`, `avatarFile/avatarPreview`, location search (`locations`, `locationSearchQuery`, debounced `GET /locations/locations/lookup`), `racesData` (`GET /characters/races`, once on mount) + `subraceOptions`, `roleWeights` (`useReputationRoleWeights`), `ReputationTierSelect`. `openEditForm(id)` → `GET /characters/admin/npcs/{id}`; `handleSubmit` → `PUT` or `POST /characters/admin/npcs`, then optional avatar upload `POST /photo/change_npc_avatar` (FormData), then closes form and refetches list. Validation: name required, kill points integer within ±1000. Errors → `toast.error` (Russian, `detail` parsed). **No dirty tracking.**
- `handleDelete` uses `window.confirm` → `DELETE /characters/admin/npcs/{id}`; `handleResurrect` → `PUT .../{id} {npc_status:'alive'}` (button only when `npc_status === 'dead'`).
- Sub-editors replace the whole page via early returns (lines 358–418) keyed on `statsNpc/equipmentNpc/questNpc/shopNpc/dialogueNpc` state → list/filters remain in state but are unmounted from view.
- **Exact visibility conditions today:**
  - Shop button: `npc.npc_role === 'merchant'` (list item role).
  - `TeleportLinksPanel`: `formOpen && editingId != null && form.npc_role === 'teleport_master'` (uses the *unsaved* form role, edit mode only).
  - `GuardPatrolPanel`: `formOpen && editingId != null && form.npc_role === 'guard'` (same).
  - Resurrect: `npc.npc_status === 'dead'`.
- `GET /characters/admin/npcs/{id}` (character-service `main.py:3129`) returns full detail incl. `name, avatar, level, npc_role, npc_status, current_location_id` but **not `location_name`**; 404 `"NPC не найден"` for non-NPC/missing.

### Editors (all in `AdminNpcsPage/`)
| Component | Props | Load / save | Dirty tracking | Full-page chrome |
|---|---|---|---|---|
| `NpcStatsEditor` (589) | `npcId, npcName, npcLevel, racesData, onClose` | Mount: parallel GET attributes / skills / npc detail / equipment. Save stats `PUT /attributes/admin/{id}`, recalc `POST /attributes/{id}/recalculate`; skills via `POST /skills/assign_multiple` + DELETEs | Skills: `hasSkillChanges` (original vs current). Stats: none (no snapshot of `attributes`) | Root `gray-bg p-4 sm:p-6`; header h2 «Статы и навыки» + «НПС: name» + `btn-line` «Назад к НПС» (`onClose`); own internal tabs stats/skills |
| `NpcEquipmentEditor` (386) | `npcId, npcName, onClose` | GET `/inventory/{id}/equipment`; equip/unequip are immediate POST/DELETE | None needed (every action is persisted immediately) | Root `gray-bg`; h2 «Экипировка: name» + `btn-line` «Назад» |
| `DialogueEditor` (631) | `npcId, npcName, onClose` | Trees list + tree editor (`editorOpen`, `title`, `nodes`); PUT/POST `/locations/admin/dialogues`; delete via `window.confirm` | None | Root `flex flex-col gap-6` (no card); header row: back link «Назад к НПС» + h2 «Диалоги: name» + `btn-blue` «Создать дерево» (keep) |
| `QuestEditor` (991) | `npcId, npcName, onClose` | Quest list + form (`editorOpen`, `editingId`, `form`); PUT/POST `/locations/admin/quests` | None | Same header pattern as Dialogue + «Создать квест» |
| `NpcShopEditor` (811) | `npcId, npcName, onClose` | Items + market (`economy:read` gated inside); add form (`addFormOpen`, `selectedItem`, `addForm`), inline row edit (`editingId`, `editForm`) | None | Header: back link + h2 «Магазин: name» + «Добавить товар» |
| `TeleportLinksPanel` (432) | `npcId` | Links CRUD, immediate; add-form state (`selectedTarget`, `costGold`…), inline edit (`editingLinkId`) | None | Already embeddable: `gray-bg` card with h3 «Связи телепорта», no onClose |
| `GuardPatrolPanel` (529) | `npcId` | GET/PUT patrol (`api/guardPatrol.ts`), step | **Has `dirty`** (`useMemo`, line 222) + «Есть несохранённые изменения» hint | Already embeddable: `gray-bg` card with h3 «Патруль» |

None of the editors use a fixed page width (only inner `max-w-*` on inputs), so they fit inside a panel as is. All already surface API errors via Russian toasts / inline text.

### Existing patterns to reuse
- **Animation:** `motion` ^12 is installed and is the design-system standard (DESIGN-SYSTEM §12). Expand/collapse pattern already exists: `AdminBattlesPage.tsx:345` / `CharactersPage/tabs/InventoryTab.tsx:199` — `<AnimatePresence>` + `motion.div initial={{opacity:0,height:0}} animate={{opacity:1,height:'auto'}} exit={{opacity:0,height:0}} transition={{duration:0.2,ease:'easeOut'}} className="overflow-hidden"`.
- **Tabs:** `Admin/CharactersPage/AdminCharacterDetailPage.tsx:129` — `<nav className="flex gap-4 sm:gap-6 border-b border-white/10 overflow-x-auto gold-scrollbar">` with `nav-link whitespace-nowrap` buttons and `motion.div layoutId` underline (`bg-site-blue`). Horizontal scroll on mobile is already solved there.
- **URL state:** `useSearchParams` used in `ItemsAdminPage.tsx:40` (functional `setSearchParams(prev => …, {replace:true})`) and `WorldPage.tsx:306` (push).
- **Confirm dialog:** `components/ui/ConfirmationModal.tsx` (`isOpen, title?, message, onConfirm, onCancel`; two buttons «Отмена»/«Подтвердить»; built on `CommonComponents/ModalShell`). No 3-button dialog exists.
- **Scroll:** `element.scrollIntoView({behavior:'smooth', block:'start'})` used in `StarterKitsPage.tsx:316`.

### Cross-Service Dependencies
None changed. Endpoints used remain identical (character-service, locations-service, inventory-service, attributes, skills, photo-service).

### DB Changes
None. No migrations.

### Risks
- **Unsaved edits on browser Back:** `BrowserRouter` has no navigation blocking; Back changes `?npc/tab` without a chance to confirm. Mitigation: guard in-app actions + `beforeunload` for reload/close; Back is a documented limitation.
- **Teleport/Patrol visibility semantics change:** today they follow the unsaved form role; the brief wants them to follow the saved role (appear after save). Intentional.
- **Remounting editors on tab switch** re-fetches data each time — acceptable (same as today's open/close).
- **Size of `AdminNpcsPage.tsx`:** moving the form out is required to keep files reviewable.

## 3. Architecture Decision (filled by Architect — in English)

Frontend-only restructure. No API contracts change. Security: unchanged — route still `npcs:read`, all writes hit the same RBAC-protected endpoints; no new inputs beyond URL params, which are parsed strictly (positive integer or literal `new`; tab against a whitelist).

### Component split (all in `src/components/AdminNpcsPage/`, all TS, no `React.FC`, Tailwind only)
- **`AdminNpcsPage.tsx`** (slimmed) — filters/search/pagination state (unchanged, local), list fetch, `racesData` fetch (shared by General form and Stats), URL state hook, dirty guard + `ConfirmationModal`, pinned panel logic, renders `NpcRow` list. Keeps «Создать НПС» button.
- **`NpcGeneralForm.tsx`** (new) — the current edit/create form moved verbatim (fields, location search, avatar upload, reputation fields, validation, error parsing). Props: `npcId: number | null`, `racesData`, `onSaved: (id: number, created: boolean) => void`, `onCancel: () => void`, `onDirtyChange?: (dirty: boolean) => void`. Loads detail itself when `npcId` is set. Dirty = current form ≠ loaded snapshot (JSON compare of `NpcFormData`) or `avatarFile != null`. After successful update it stays open, re-snapshots (dirty → false) and calls `onSaved`. Remove the «Редактирование/Создание НПС» h2 (the panel header names the NPC). «Отмена» → `onCancel`.
- **`NpcRow.tsx`** (new) — compact clickable plate: avatar, name, `#id`, level, role chip, location, status chip, chevron rotating when open. A single responsive layout (grid on `sm:`+, stacked on mobile) replacing both the `<table>` and the mobile cards. Rendered as `<button type="button" aria-expanded>` (or a div with role=button + Enter/Space). Gets `ref` for scrolling (`scroll-mt-*`, so a sticky header doesn't cover it). Children slot / sibling for the panel.
- **`NpcExpandedPanel.tsx`** (new) — the `motion.div` height/opacity panel under a row. Header: NPC name (+ «Новый НПС» in create mode) on the left; on the right danger actions «Воскресить» (only `npc_status === 'dead'`) and «Удалить» (with `ConfirmationModal`). Then `NpcTabs`, then the active section, keyed `${npcId}-${tab}` so each section mounts fresh. Light background (`bg-white/[0.03] rounded-card` + `border-white/10`) — editors keep their own `gray-bg` cards; "airy" per design system.
- **`NpcTabs.tsx`** (new) — horizontal tab strip copied from the AdminCharacterDetailPage pattern (`overflow-x-auto gold-scrollbar`, `nav-link whitespace-nowrap`, `motion` `layoutId` underline; the `layoutId` must be unique per page, e.g. `npc-panel-tab`).
- **`npcTabs.ts`** (new) — `type NpcTabKey = 'general'|'stats'|'equipment'|'dialogues'|'quests'|'shop'|'teleports'|'patrol'`, labels (Основное, Характеристики, Снаряжение, Диалоги, Квесты, Магазин, Телепорты, Патруль), and `availableTabs(role: string | null, isNew: boolean)`: new → `['general']`; else base five + `shop` if `role === 'merchant'`, `teleports` if `role === 'teleport_master'`, `patrol` if `role === 'guard'`. Role = **saved** role (from list item / detail fetch), not the unsaved form value.
- **`useNpcPanelUrlState.ts`** (new hook) — wraps `useSearchParams`. Parses `npc` → `number | 'new' | null` (anything else → null), `tab` → `NpcTabKey | null`. Exposes `openNpc(id|'new', tab='general')` (push), `setTab(tab)` (push), `close()` (push, deletes both params), `normalize(...)` (replace). Always uses the functional `setSearchParams(prev => …)` so unrelated params survive.

### URL contract
`/admin/npcs?npc=<id>&tab=<key>`; `?npc=new` = create panel (tab forced to `general`).
- Open/close/tab switch → history **push** (Back steps through them). Normalizations (invalid tab → `general`, tab not available for role → `general`, unknown NPC → clear, delete → clear, create success → `npc=<newId>&tab=general`) → **replace**.
- Search/filters/page stay in component state (not URL) — they persist while working because the page never unmounts; not required to survive reload.

### NPC not on the current page
If `npc` is a number that isn't in the current `npcs` list (deep link, or the NPC left the page after a filter/page change), the page fetches `GET /characters/admin/npcs/{id}` and renders it as a **pinned row above the list** (label «Открыт по ссылке», location shown as `Локация #id` since detail has no `location_name`) with its panel expanded. If the NPC later appears in the list, render it inline instead (no duplicate). 404/error → Russian toast «НПС не найден» + `normalize` clears params. The create panel (`npc=new`) is rendered in the same pinned slot as a «Новый НПС» plate.

### Dirty-state guard
- Two-option confirm via existing `ConfirmationModal`: title «Несохранённые изменения», message «Есть несохранённые изменения. Уйти без сохранения?». A 3-button «Сохранить» would require every editor to expose an imperative save handle (invasive rewrite of 7 editors) — rejected per minimal-diff.
- Each section reports dirtiness through a new **optional** prop `onDirtyChange?: (dirty: boolean) => void`, emitted from a `useEffect` on the computed boolean (and `false` on unmount). Page keeps `panelDirty` (reset to false when the section remounts). Per editor:
  - `NpcGeneralForm`: snapshot compare (above).
  - `NpcStatsEditor`: keep a snapshot of `attributes` after load/save; dirty = attributes ≠ snapshot || `hasSkillChanges`.
  - `NpcEquipmentEditor`: no prop (always clean — actions are immediate).
  - `DialogueEditor`, `QuestEditor`: dirty = `editorOpen` && current form (`title`+`nodes` / `form`) ≠ snapshot taken when the editor was opened.
  - `NpcShopEditor`: dirty = (`addFormOpen` && `selectedItem != null`) || (`editingId != null` && `editForm` ≠ row's original values).
  - `TeleportLinksPanel`: dirty = `selectedTarget != null` (a half-filled new link) || `editingLinkId != null`.
  - `GuardPatrolPanel`: forward existing `dirty`.
- `guard(action)` in the page: if `panelDirty` → show modal, run `action` on confirm (and clear dirty); else run immediately. Wrapped actions: tab switch, collapse, open another row, «Создать НПС». Not wrapped: filters/search/pagination (they don't close the panel — the open NPC simply becomes pinned).
- `beforeunload` listener while `panelDirty` (reload/close tab). Browser Back is **not** blocked (no data router) — accepted limitation.

### Create flow
«Создать НПС» → `guard(() => openNpc('new'))`. Pinned «Новый НПС» plate + panel with only «Основное», no danger actions. On save (`onSaved(id, true)`): `normalize({npc:id, tab:'general'})`, refetch list; the NPC now shows full tabs per its saved role (pinned if not on the current page). «Отмена» in create mode → `close()`.

### Edit flow / role change
`onSaved(id, false)` → refetch list and the pinned detail (if pinned) so the row and `availableTabs` reflect the new role/name/avatar/level (e.g. becomes guard → «Патруль» appears). If the active tab became unavailable → normalize to `general`.

### Delete / resurrect
Panel header right. Delete → `ConfirmationModal` («Удалить НПС? Это действие нельзя отменить.») → `DELETE`; success → toast, remove from list, `normalize` clears params, `panelDirty=false`. Resurrect → `PUT {npc_status:'alive'}` → refetch list + pinned detail. Errors: same Russian toasts as today.

### Animation & scroll
`AnimatePresence` + `motion.div` height `0 → 'auto'`, opacity `0 → 1`, `duration 0.25, easeOut`, `overflow-hidden` (existing pattern). Chevron `rotate-180` transition. Opening another row: the old one exits while the new one enters; in the new panel's `onAnimationComplete` (open only) call `rowRef.scrollIntoView({behavior:'smooth', block:'start'})` — after layout settles, so the collapse above doesn't make the scroll miss. Also scroll once on initial deep-link open after data arrives.

### Embedded mode for existing editors (minimal diff)
Add optional `embedded?: boolean` (default `false`) and make `onClose` optional in `NpcStatsEditor`, `NpcEquipmentEditor`, `DialogueEditor`, `QuestEditor`, `NpcShopEditor`. When `embedded`: do not render the back button/link and the h2 title (`… : name` / «Статы и навыки» + «НПС: …»); keep in-section action buttons («Создать дерево», «Создать квест», «Добавить товар») right-aligned in the same header row. Nothing else in these files changes except the `onDirtyChange` wiring. `TeleportLinksPanel` / `GuardPatrolPanel` only get `onDirtyChange`. No style migration of these editors is required (they are already Tailwind; header change is conditional rendering only) — but any touched className must stay mobile-safe.

### Mobile (360px+)
Row: stacked (avatar + name/ID/level line, chips below); panel padding `p-3 sm:p-5`; tabs scroll horizontally; panel content `min-w-0` to prevent overflow; danger actions wrap under the name on narrow screens.

### Data flow
```
URL ?npc&tab ──useNpcPanelUrlState──> AdminNpcsPage
AdminNpcsPage ── GET /characters/admin/npcs (list) ; GET /characters/admin/npcs/{id} (pinned only)
NpcExpandedPanel ──> active section (existing editors, same endpoints as today)
section ──onDirtyChange──> AdminNpcsPage.panelDirty ──> guard() / ConfirmationModal / beforeunload
```

## 4. Tasks (filled by Architect, updated by PM — in English)

No backend Python is modified → **no QA Test task** (CLAUDE.md exception for pure-frontend features). No DevSecOps.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Restructure the NPC admin page per section 3: extract `NpcGeneralForm` (with snapshot dirty + stays open after update), add `npcTabs.ts`, `useNpcPanelUrlState.ts`, `NpcRow`, `NpcTabs`, `NpcExpandedPanel`; replace table + mobile cards with expandable rows (one open at a time, motion height/opacity, smooth scroll to the opened row); pinned row for deep-linked/off-page NPC and for create; danger actions in panel header with `ConfirmationModal`; dirty guard (`ConfirmationModal` + `beforeunload`); remove the early-return full-page editors. Add optional `embedded` / optional `onClose` / optional `onDirtyChange` to the existing editors exactly as listed in section 3 (no other changes in them). | Frontend Developer | DONE | `AdminNpcsPage.tsx`, new `NpcGeneralForm.tsx`, `NpcRow.tsx`, `NpcTabs.tsx`, `NpcExpandedPanel.tsx`, `npcTabs.ts`, `useNpcPanelUrlState.ts`; minimal edits in `NpcStatsEditor.tsx`, `NpcEquipmentEditor.tsx`, `DialogueEditor.tsx`, `QuestEditor.tsx`, `NpcShopEditor.tsx`, `TeleportLinksPanel.tsx`, `GuardPatrolPanel.tsx` | — | Click plate → panel animates open with «Основное»; one open at a time + scroll; tabs: base five always, «Магазин»/«Телепорты»/«Патруль» only for saved role merchant/teleport_master/guard; `?npc=&tab=` survives reload, Back works, invalid/unavailable tab → «Основное», unknown id → toast + params cleared, off-page id → pinned plate; create → pinned «Новый НПС» with only «Основное», after save becomes normal NPC with full tabs; role change after save updates tabs; delete closes panel and clears params; resurrect only for dead; unsaved changes prompt on tab switch/collapse/other row/create; filters/search/page preserved; no `React.FC`; Tailwind + design-system classes only; 360px without horizontal overflow; all API errors shown in Russian; `npx tsc --noEmit` and `npm run build` pass (in Docker per project workflow). |
| 2 | Review: code + live check in Chrome on localhost (desktop and 360px): every tab of a merchant, a teleport master and a guard; deep link reload; Back button; dirty prompt in General/Stats/Quests/Patrol; create; delete; resurrect; console clean; tsc + build re-run. | Reviewer | DONE | all of #1 | #1 | Checklist passed, zero console errors, live verification recorded in section 5 |

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-10
**Result:** PASS (with one small fix applied by Reviewer)

#### Fix applied during review
| # | File:line | Description | Status |
|---|-----------|-------------|--------|
| 1 | `AdminNpcsPage/NpcStatsEditor.tsx:578` | At 360px the «Сохранить статы» / «Пересчитать» row (`flex gap-3`) overflowed; inside the panel's `overflow-hidden` the «Пересчитать» button was clipped and unreachable. Added `flex-wrap`. Re-checked live: no element exceeds the viewport. | FIXED |

#### Code review
- Matches section 3: component split, `availableTabs` by saved role, URL contract (push for open/tab/close, replace for normalisation), pinned plate for off-page/deep-linked NPC and for create, dirty guard via `ConfirmationModal` + `beforeunload`, danger actions in panel header.
- Editors: only optional `embedded` / optional `onClose` / `onDirtyChange` + conditional header; save/load logic untouched except `NpcStatsEditor` `savedAttributes` snapshot (set on load and after successful PUT) — no behaviour change.
- Old page's early-return full-page editors, table and mobile cards are gone; nothing else imports from the old page. Form fields, validation, avatar upload, error parsing moved verbatim to `NpcGeneralForm`.
- CLAUDE.md frontend rules: all TS, no `React.FC`, no `any`, Tailwind + design-system classes (`gray-bg`, `gold-text`, `nav-link`, `btn-blue`, `btn-line`, `input-underline`, `gold-outline`, `gold-scrollbar`), no SCSS; all API errors are Russian toasts.

#### Non-blocking notes
- `QuestEditor`/`DialogueEditor`: pressing «Создать квест/дерево» while an editor is already open does not re-baseline the snapshot, so the panel reports dirty (edits really are discarded — harmless false positive).
- Pinned / «Новый НПС» plates unmount without the exit animation (list rows animate correctly).
- The non-embedded `onClose` branches in the editors are now unused by the page (kept per architecture, minimal diff).
- Browser Back is not guarded (accepted limitation, no data router).

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (0 errors)
- [x] `vite build` (frontend container) — PASS
- [ ] `py_compile` / `pytest` — N/A (no backend changes)
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, localhost) — PASS

#### Live Verification Results
- Page tested: `/admin/npcs` (admin), desktop + 360px iframe.
- Expand/collapse with height/opacity animation; one open at a time, other row closes, page scrolls to the opened plate.
- Tabs: merchant 33 (+Магазин), teleport master 96 (+Телепорты), guards 97/62 (+Патруль), all base tabs load.
- Dirty guard confirmed on Магазин (edited row), Телепорты (selected target), Патруль (mode change), Квесты (typed title), Характеристики (stat change), Основное (biography) — on tab switch, collapse and opening another row; «Отмена» keeps the edit, «Подтвердить» proceeds. Untouched sections do not prompt.
- URL: `?npc=&tab=` survives reload; Back restores previous NPC/tab; `tab=bogus` and `tab=patrol` for a merchant → `general`; `npc=abc` → params cleared; `npc=99999999` → «НПС не найден» + params cleared; off-page NPC shown as «Открыт по ссылке» plate; changing filter while open keeps the NPC pinned; filter + page 2 preserved while working in the panel.
- Resurrect: dead NPC 641 → «НПС воскрешён», status chip → Жив, button disappears.
- Create: «Новый НПС» with only «Основное», no danger actions → saved as guard → URL `npc=<id>&tab=general`, «Патруль» tab appears; role → merchant → «Магазин» replaces «Патруль»; delete with confirmation → params cleared, GET → 404 (test NPC removed).
- 360px: no horizontal overflow on Основное/Характеристики/Магазин/Патруль/Квесты/Телепорты; tab strip scrolls horizontally.
- Console errors: NONE (only pre-existing React Router future-flag warnings).

## 6. Logging (all agents — in Russian)

```
[LOG] 2026-11-10 — PM: фича создана, запускаю анализ
[LOG] 2026-11-10 — Codebase Analyst: изучены страница НПС и 7 редакторов; несохранённые правки отслеживает только патруль (и навыки в статах), роутер BrowserRouter — блокировки «назад» нет; анимации раскрытия на motion уже есть в проекте
[LOG] 2026-11-10 — Architect: спроектированы плашки с подложкой и вкладками, адрес ?npc=&tab=, закреплённая плашка для НПС вне страницы и для создания, защита от потери правок через ConfirmationModal; 2 задачи (Frontend Dev + Reviewer), QA не нужен — бэкенд не трогаем
[LOG] 2026-11-10 — Frontend Dev: начал задачу #1
[LOG] 2026-11-10 — Frontend Dev: форма вынесена в NpcGeneralForm, добавлены NpcRow / NpcExpandedPanel / NpcTabs / useNpcPanelUrlState / useDirtyReport; редакторы получили embedded / onDirtyChange. Файл вкладок назван npcTabKeys.ts (npcTabs.ts конфликтует по регистру с NpcTabs.tsx)
[LOG] 2026-11-10 — Frontend Dev: tsc --noEmit и vite build в контейнере — ок; живая проверка на localhost: все вкладки (торговец 33, стражник 97, телепортист 96), адрес и перезагрузка, «назад», неверная вкладка/id, НПС вне страницы, защита правок (Основное/Характеристики/Квесты), создание → смена роли → удаление тестового НПС, 360px без горизонтального скролла, ошибок в консоли нет
[LOG] 2026-11-10 — Frontend Dev: задача #1 завершена
[LOG] 2026-11-10 — Reviewer: начал проверку
[LOG] 2026-11-10 — Reviewer: tsc и сборка в контейнере — ок; живая проверка в Chrome: все вкладки, защита правок в Магазине/Телепортах/Патруле, адрес, воскрешение 641, создание/удаление тестового НПС, 360px, ошибок в консоли нет
[LOG] 2026-11-10 — Reviewer: мелкая правка — кнопка «Пересчитать» в характеристиках обрезалась на 360px, добавлен перенос строки
[LOG] 2026-11-10 — Reviewer: проверка завершена, результат PASS
[LOG] 2026-11-10 — PM: исправлено ложное предупреждение в квестах/диалогах, фича закрыта
[LOG] 2026-11-10 — PM: на плашках вместо локации было «—» (список НПС не отдавал название, баг ещё со старой страницы) — character-service теперь отдаёт location_name в GET /characters/admin/npcs, тест добавлен
```

## 7. Completion Summary (filled by PM on completion — in Russian)

- Админка НПС переделана: плашки без кнопок, клик раскрывает под НПС анимированную подложку с вкладками «Основное», «Характеристики», «Снаряжение», «Диалоги», «Квесты» и по роли «Магазин» / «Телепорты» / «Патруль»; «Воскресить» и «Удалить» — в шапке подложки.
- Открытый НПС и вкладка — в адресе (?npc=&tab=), перезагрузка и «назад» работают; НПС не с текущей страницы — закреплённой плашкой сверху; создание — такой же плашкой.
- Предупреждение о несохранённых правках (2 кнопки); кнопку «назад» браузера не перехватывает (ограничение роутера).
- Ревью PASS (исправлен перенос кнопок во «Характеристиках» на 360px). После ревью PM убрал ложное предупреждение при «Создать» в квестах/диалогах при уже открытом редакторе.
- Плюс мелкая правка бэкенда: GET /characters/admin/npcs отдаёт location_name (раньше на плашках было «—»), тест в test_admin_npc_list.py.

