# FEAT-148: Редизайн главной страницы (layout по макету + новый хедер + адаптив)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-07-16 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Редизайн главной страницы на основе макета из Claude Design.
Референс-макет сохранён локально: **`features/design-refs/FEAT-mainpage-redesign-MainPage.dc.html`** (61 KB, полный HTML с инлайн-стилями и media queries для мобильной версии ≤760px и ≤420px). Мобильный макет (MobilePreview.dc.html) — это тот же MainPage.dc.html, отрендеренный во фрейме 390×844, т.е. адаптив описан media-запросами внутри основного макета.

Ключевые требования пользователя (дословно):
1. **Расположение элементов** — сделать такое же, как в макете (layout один в один).
2. **Хедер** — скопировать **один в один** как в макете (десктоп + мобильный вариант из media queries).
3. **Блок списка лидеров («Зал славы»)** — скопировать один в один по расположению/структуре.
4. **Типографику и обводки из макета НЕ переносить** — оставить текущие (шрифты, борды сайта как сейчас). Стилистика остаётся текущая (существующая дизайн-система сайта), меняется только расположение элементов и добавляется адаптив.
5. **В хедере вместо полосок (HP/MP-бары в макете)** — показать: уровень персонажа, количество монет, и по клику — возможность **смены активного персонажа**.
6. **Лидерборд — настоящий** (реальные данные, как в текущих mini-stats на главной), с **подстановкой аватарок персонажей**.
7. **Чат на мобильном** — должен открываться так же, как в макете (поведение мобильной chat-panel из MainPage.dc.html, класс `.chat-panel` в media queries: на мобильном панель чата раскрывается на полную ширину).

### Бизнес-правила
- Данные в хедере (уровень, монеты, аватар) — реального активного персонажа залогиненного пользователя.
- Клик по блоку персонажа в хедере открывает выбор/смену активного персонажа.
- Лидерборд использует реальные данные (как существующие mini-stats leaderboards), каждая строка — с аватаркой персонажа.
- Все пользовательские тексты — на русском.

### UX / Пользовательский сценарий
1. Игрок открывает главную страницу — видит новый layout по макету: хедер, hero-зону, блоки быстрых ссылок, зал славы (лидерборд), прочие блоки в том же расположении, что в макете.
2. В хедере видит свой аватар, уровень и монеты активного персонажа; по клику — переключение персонажа.
3. Лидерборд показывает реальных топ-персонажей с аватарками.
4. На мобильном (≤760px) страница перестраивается по мобильному макету (мобильный хедер, одноколоночная сетка).
5. На мобильном игрок открывает чат — он открывается так же, как в макете (мобильная chat-panel на полную ширину).

### Edge Cases
- Пользователь не залогинен — как выглядит хедер? (гостевой вариант — по текущему поведению сайта).
- У пользователя нет активного персонажа / один персонаж.
- У персонажа в лидерборде нет аватарки — нужен плейсхолдер.
- Экран 360px — всё должно помещаться (правило T5).

### Вопросы к пользователю (если есть)
- [x] Что показывать как «монеты» в хедере? → **Ответ: валюту персонажа (`currency_balance` активного персонажа).**
- [x] Как работает смена персонажа по клику? → **Ответ: выпадающий список персонажей прямо в хедере (смена в один клик, без ухода со страницы).**
- [x] Бейдж непрочитанных у кнопки чата? → **Ответ: без бейджа (реальный счётчик чата — отдельная задача в будущем).**
- [x] Новый хедер на всех страницах сайта? → **Ответ: да, на всех страницах (хедер общий, мобильный хедер добавляется впервые site-wide).**
- [x] Ширина контейнера: 1240px (текущая) или 1360px (макет)? → **Ответ: расширить до 1360px ВЕЗДЕ по сайту (site-wide).**
- [x] Убрать приклеенный язычок чата сбоку экрана? → **Ответ: да, убрать — чат открывается только из хедера (как в макете).**

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | main change: page layout, header (desktop + new mobile), hall-of-fame block, chat panel behavior | `src/components/HomePage/*` (HomePage.tsx, Stats/, Button/, HomePageButton/, Slider/, SmallHomePageButton/, LatestRoleplayPosts/), `src/components/CommonComponents/Header/*` (Header.tsx, NavLinks.tsx, MegaMenu.tsx, SearchInput.tsx, AvatarDropdown.tsx, NotificationBell.tsx, AdminMenu.tsx), `src/components/App/Layout/Layout.tsx`, `src/components/Chat/ChatWidget.tsx` |
| character-service | small additive change: expose character coins in `short_info` (for the header chip) | `app/main.py` (`get_short_info`, line ~1572) |
| user-service | small additive change: pass coins through `/users/me` character payload | `main.py` (`_fetch_character_short`, line ~114), `schemas.py` (`CharacterShort`, line ~56) |

### Current Main Page — component map

- Route: `/home` → `HomePage` (`src/components/HomePage/HomePage.tsx`, .tsx + Tailwind), rendered inside `Layout` (`src/components/App/Layout/Layout.tsx`) which mounts global `Header`, `Footer`, `ChatWidget`, `ConnectionStatus`. Route `/` is the guest `StartPage` (separate landing, out of scope).
- `HomePage.tsx` renders a 2-column grid: left = 3 large nav cards + 4 small cards (`Button.jsx`), right = `Slider.jsx` (hardcoded slides) + `LatestRoleplayPosts.tsx`; below the grid — `Stats.tsx` (mini-stats leaderboards, commit ddfa185).
- `Stats.tsx`: fetches `GET /characters/home-leaderboards?limit=3` via `src/api/homeStats.ts`; 3 boards (symbols_daily / pvp / pve), each entry already includes `character_id, name, avatar, value`; avatar fallback `stats_user_img.png`; error state with retry button (RU text).
- `LatestRoleplayPosts.tsx`: real data from `GET /locations/posts/latest?limit=5` (`src/api/api.ts`, `LatestRoleplayPost`) — already contains `character_photo`, `character_title(+rarity)`, `character_level`, `character_name`, `location_id/name`, `created_at`, `likes_count`, `content`. This covers everything the design's "Живая лента" cards show. Auto-refresh every 30s.
- `Footer.tsx` (.tsx + Tailwind): already implements the design's footer counters — `GET /users/stats` → `total_users` ("Наёмников") + `online_users` ("В мире сейчас") with links to `/players` and `/players/online`.
- Header (`CommonComponents/Header/Header.tsx`, .tsx + Tailwind, max-w-[1240px]): logo, `NavLinks` (Главная with `MegaMenu` — same 5 categories as the design's mega menu, Правила, События, Тикет), `SearchInput`, character `AvatarDropdown` (links: Профиль / current location / "Сменить персонажа" → `/selectCharacter`), user `AvatarDropdown`, `NotificationBell`, messages icon with unread badge (`messengerSlice.selectTotalUnread`), `AdminMenu`. **No mobile variant exists — the header is a single desktop row (no burger, no responsive collapse); the design's mobile header (≤760px) must be built from scratch.**
- Redux slices involved: `userSlice` (username, avatar, `character {id, name, avatar, level, current_location, travel_cooldown_until}` from `/users/me`, `getMe` thunk), `messengerSlice` (unread count), `notificationSlice` (bell), `chatSlice` (chat open/close, channels, messages, ban). Leaderboards and latest posts are local component state (plain axios), not Redux.

### Design Reference — block map (`features/design-refs/FEAT-mainpage-redesign-MainPage.dc.html`)

1. **Desktop header `.hdr`** (hidden ≤760px): left — chat button with unread badge, logo, nav (Главная + mega menu with 5 columns, Правила, События, Тикет); right — search input, **character chip** (avatar in gold ring + name + HP/MP bars + location link → per brief bars are replaced with **level + coins**, click = switch active character), notification bell with badge, messages icon, user avatar. Data: active character (name/avatar/level/coins/location) from `/users/me`, unread counts, notifications.
2. **Mobile header `.hdr-m`** (shown ≤760px): top bar = burger (with total-unread badge) · logo · chat button · user avatar; **character+location strip** below (avatar, name, bars→level/coins, location link); collapsible menu = search + accordion nav sections (Главная / Игровой мир / Руководство / Магазин / Сообщество) + two wide buttons (Уведомления, Сообщения) with badges.
3. **Main grid `.m-grid`** 38%/62% (1 col ≤760px): left "Куда отправимся" — 3 large nav cards (Игровой мир / Руководство / Магазин, same sublinks as current `buttonsData`); right "Главное сейчас" — hero slider (min-height 440px, dots + arrows in the top bar, tag top-right, title/desc/Читать bottom). Static content — same as current `HomePage.tsx` data.
4. **Quick links `.ql-grid`** — full-width row of 4 small cards (Предложения / Администрация / Бестиарий / Поиск игрока), 4→2 (≤760px)→1 (≤420px) columns. Same as current `smallButtons`.
5. **Живая лента `.feed-grid`** — full-width, 2-col grid (1 col ≤760px) of post cards: avatar + title + name + LVL on the left, location/time/text/likes on the right; "Онлайн" pulse dot in the section title. Fully covered by existing `LatestRoleplayPosts` data.
6. **Зал славы (Hall of Fame)** — full-width block: banner (`stats_bg.png`) with the active-board title + 3 tab pills (Символов за сутки / PvP-очки / PvE-очки); **podium** for top-3 (center = rank 1, larger avatar with gold ring/glow, pedestals of different heights, medal-colored rank numbers) + **rest list** (rows: rank, avatar, name, value). Needs top-6 per board → existing endpoint supports `?limit=` up to 10. Design uses initials in colored circles — real implementation uses avatars (present in the API) + placeholder.
7. **Footer** — "Наёмников: N | В мире сейчас: M" — identical to existing `Footer.tsx`.
8. **Chat panel `.chat-panel`** — fixed left slide-in, width 400px / max-width 92vw, with dark overlay backdrop (click = close), header with close button, channel tabs (Общий/Локация/Отряд/Торговля), scrollable messages, input with send button. **≤760px: full width (`width:100%; max-width:100%`)**. Opens from the header chat buttons (desktop top-left, mobile top bar).

### Current Chat implementation vs design

- All chat components are **.tsx + Tailwind** (no SCSS): `Chat/ChatWidget.tsx` (container + always-visible tab toggle button glued to the panel edge, fixed top-left of viewport), `ChatPanel.tsx`, `ChatHeader.tsx` (channel tabs), `ChatMessages.tsx`, `ChatMessage.tsx`, `ChatInput.tsx`. State in `chatSlice` (`toggleChat`, `selectChatIsOpen`, channels, ban check). Mounted globally in `Layout.tsx`, so it exists on every page including `/home`.
- Current behavior: slide-in from the left via negative margin, width `85vw` mobile / `360-400px` desktop, **no overlay backdrop**, opened via its own glued tab button (there is no chat button in the header).
- To match the design: (a) add a chat open button (with styling per current design system) to the new desktop and mobile headers dispatching `toggleChat`; (b) mobile ≤760px panel must be **100% width** (currently 85vw); (c) add overlay backdrop with click-to-close as in the reference; (d) decide the fate of the current glued tab button (design has none — header buttons replace it). Internal structure (tabs/messages/input) already matches the reference layout.
- No chat **unread counter** exists in `chatSlice` (badge "3" on the design's chat button is mock data; only messenger has `selectTotalUnread`).

### Data availability (backend)

| Data | Source | Status |
|------|--------|--------|
| Character level | `characters.level` → `GET /characters/{id}/short_info` → `/users/me` `character.level` → `userSlice` | **exists** |
| Character coins | `characters.currency_balance` (character-service). Returned by `/characters/{id}/full_profile`, admin endpoints, teleport responses — but **NOT in `short_info` and NOT in `/users/me`** | **backend change needed** (additive: add `currency_balance` to `short_info` response + user-service `CharacterShort` schema + `_fetch_character_short`) |
| Active character + switching | `users.current_character`; list: `GET /users/{user_id}/characters` (user-service main.py:1489); switch: `PUT /users/{user_id}/update_character` (main.py:557) + re-dispatch `getMe()` — pattern in `SelectCharacterPage.tsx` | **exists** |
| Leaderboards | `GET /characters/home-leaderboards?limit=1..10` (character-service main.py:2568, crud.py:2700) — 3 boards, entries `{character_id, name, avatar, value}`; reads `character_logs` + `character_cumulative_stats` directly (same DB); NPCs excluded, zero rows omitted | **exists** (design podium+rest needs limit=6) |
| Leaderboard avatars | `characters.avatar` (full photo-service/S3 URL) already in the response; frontend fallback `stats_user_img.png` | **exists** |
| Current location in header chip | `/users/me` `character.current_location {id, name}` | **exists** |
| Live feed | `GET /locations/posts/latest` | **exists** |
| Footer counters | `GET /users/stats` | **exists** |
| Notifications / messages badges | `notificationSlice` / `messengerSlice.selectTotalUnread` | **exists** |
| Chat unread badge | — | **does not exist** (see Questions) |

### Existing Patterns

- character-service: sync SQLAlchemy, Pydantic <1.x style, Alembic present (`alembic_version_character`). `short_info` is a plain dict endpoint (no response_model) — adding a key is trivially backward-compatible. Has tests dir (`app/tests/test_home_leaderboards.py`) — QA pattern established.
- user-service: sync SQLAlchemy, Alembic present. `/users/me` aggregates via httpx call to character-service `_fetch_character_short`; `CharacterShort` Pydantic schema ignores unknown keys, so char-service can ship first (no lockstep deploy).
- Frontend: mandatory Tailwind (T1) + TypeScript (T3) + mobile adaptivity (T5) + design system (`docs/DESIGN-SYSTEM.md`, `index.css` @layer components: `gold-text`, `gray-bg`, `btn-blue`, `nav-link`, `rounded-card` etc.) + no `React.FC`. Per brief: **take only layout/adaptivity from the reference, keep current typography/borders/design tokens** (do not import Google Fonts/Montserrat/Cormorant or the gold-gradient inline styles from the mock).
- **T1/T3 debt in touched components:** `HomePage/Button/Button.jsx` (+`Button.module.scss`), `HomePageButton/HomePageButton.jsx` (+scss), `Slider/Slider.jsx` (+scss), `SmallHomePageButton/SmallHomePageButton.jsx` (+scss), `Slider/ArrowButton|CircleButton|SliderArrowButton|SliderCircleButton` (.jsx + .module.scss each). Any of these touched during the redesign **must** be migrated to .tsx + Tailwind in the same PR (rule 8/9 of CLAUDE.md). Header/, Stats, LatestRoleplayPosts, Footer, Chat/* are already .tsx + Tailwind.

### Cross-Service Dependencies

- user-service `/users/me` → character-service `GET /characters/{id}/short_info` (httpx) → locations-service `GET /locations/{id}/details`. Adding `currency_balance` to `short_info` affects only these consumers; additive JSON key is safe (grep shows `short_info` is also consumed with `.get()` access patterns).
- Frontend → character-service `/characters/home-leaderboards` (public, no auth) — increasing `limit` from 3 to 6 is within the endpoint's `le=10` bound; no backend change.
- Frontend → user-service `/users/{id}/characters` + `/users/{id}/update_character` (JWT) for the switcher.
- character-service leaderboards read `character_cumulative_stats` (owned by character-attributes-service) directly in the shared MySQL DB — unchanged.

### DB Changes

- **None.** `characters.currency_balance`, `characters.level`, `characters.avatar`, `users.current_character` all exist. No Alembic migrations required.

### Assets referenced by the design — all present in `src/assets/`

`background-main.png`, `logo_fog.png`, `homepagebutton1.png`, `homepagebutton2.png`, `homepagebutton3.png`, `sliderimg1.png`, `smallhomebutton1.png`…`smallhomebutton4.png`, `stats_bg.png` — **all exist**, plus `stats_user_img.png` (avatar placeholder). Nothing missing. (`support.js` and Google Fonts links in the mock are Claude-Design scaffolding — do not carry over.)

### Risks

- **Header is global** (`Layout.tsx` renders it on every page, not just `/home`) → redesigning it (character chip, chat button, mobile burger) changes the whole site's shell. Mitigation: keep component API self-contained, verify key pages (location, profile, admin) after the change; the mobile header actually fixes an existing site-wide gap (no responsive header today).
- Removing the ChatWidget glued tab button in favor of header buttons changes chat discoverability on non-home pages too (widget is global). Mitigation: header is also global, so the entry point remains on every page.
- `/users/me` payload grows (coins): `getMe` is re-dispatched on every route change (`Header` useEffect) — negligible, but keep the addition to a single scalar field.
- Slider/Button/small-button .jsx→.tsx+Tailwind migration in the same PR increases diff size; mitigation: mechanical migration, no logic changes beyond layout.
- Backward compatibility: additive-only API changes; deploy character-service before/with user-service (schema tolerates missing key anyway).
- Leaderboard `limit=6`: boards may return fewer than 3 rows (zero-activity rows omitted) → podium must handle 0–2 entries gracefully (current Stats shows "Пока пусто").

### Questions for PM

1. **"Монеты" in the header chip** — assume the active character's gold (`characters.currency_balance`)? The user account also has `balance` and `diamonds` (premium) in `/users/me`. Recommendation: character `currency_balance`; please confirm.
2. **Character switching UX in the header** — the design has no switcher UI (chip is static). Options: (a) click on the chip opens an inline dropdown listing the user's characters (data: `GET /users/{id}/characters`, switch via `PUT /update_character`, as in `SelectCharacterPage`), or (b) click navigates to the existing `/selectCharacter` page. Brief says "по клику — возможность смены активного персонажа", which suggests (a) an in-header dropdown; please confirm.
3. **Chat unread badge** on the header chat button (design shows "3") — no chat unread counter exists in the backend/`chatSlice`. Omit the badge for now, or is a real unread counter in scope (separate backend work)?
4. **Header applies site-wide** (all pages share `Layout`) — confirm the redesigned header + mobile header replaces the current one everywhere, not only on the main page.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 Scope Summary

- **Backend:** one small additive change — expose `currency_balance` in character-service `short_info` and pass it through user-service `/users/me` (`CharacterShort`). No DB changes, no migrations, no new endpoints.
- **Frontend:** rewrite the global Header (desktop layout per reference + brand-new mobile header ≤ md), rewrite the main page layout per reference (grid, quick links, live feed, hall-of-fame), adjust chat panel behavior (header-driven open, overlay backdrop, full-width on mobile), and migrate all touched `.jsx` HomePage subcomponents to `.tsx` + Tailwind (T1/T3).
- **Styling rule (per brief):** copy **only element positioning/layout and responsive behavior** from `features/design-refs/FEAT-mainpage-redesign-MainPage.dc.html`. All typography, colors, borders, shadows come from the **current design system** (`docs/DESIGN-SYSTEM.md`: `gold-text`, `rounded-card`, `shadow-card`, `text-site-blue`, `dropdown-menu`, etc.). Do NOT import Montserrat/Cormorant fonts or the mock's inline gradients where an existing token/class covers it.

### 3.2 API Contract Changes (additive only)

#### character-service — `GET /characters/{character_id}/short_info` (modified, additive)

File: `services/character-service/app/main.py` (`get_short_info`, line ~1573). Plain-dict endpoint (no response_model) — add one key:

```python
return {
    ...existing keys...,
    "currency_balance": ch.currency_balance,   # int, character gold
}
```

- Status codes unchanged (200 / 404).
- Backward compatible: all known consumers (`user-service _fetch_character_short`, others using `.get()`) tolerate extra keys.

#### user-service — `GET /users/me` (modified, additive)

1. `services/user-service/main.py` — `_fetch_character_short` (line ~114), add to the returned dict:
   ```python
   "currency_balance": ch_json.get("currency_balance"),
   ```
2. `services/user-service/schemas.py` — `CharacterShort` (line ~56), Pydantic v1 style:
   ```python
   currency_balance: Optional[int] = None
   ```

Resulting `/users/me` payload: `character.currency_balance: int | null`. `null` when character-service is older/unavailable — frontend must handle gracefully (hide the coins chip element).

Note: `_fetch_character_short` is also reused by `GET /users/{id}/characters` and `/users/{id}/profile`; `UserCharacterItem`/profile schemas are NOT extended (field silently dropped there) — no contract change for those endpoints.

**Deploy order:** character-service first or together with user-service (user-service tolerates the missing key). No lockstep required. Rollback = revert commits; no migration to roll back.

#### Reused existing endpoints (no changes)

| Endpoint | Used for |
|---|---|
| `GET /users/{user_id}/characters` (user-service:1489) | header character-switch dropdown (id, name, avatar, level per character) |
| `PUT /users/{user_id}/update_character` (user-service:557, JWT + ownership/moderator check) | switching active character from the dropdown |
| `GET /characters/home-leaderboards?limit=6` (character-service:2568, `limit` ≤ 10 already supported) | Hall of Fame podium (top-3) + rest list (ranks 4–6) |
| `GET /locations/posts/latest?limit=6` | «Живая лента» feed cards |
| `GET /users/stats` | footer counters (already implemented in `Footer.tsx`) |

### 3.3 Frontend Component Architecture

Breakpoint decision: the reference uses 760px/420px; we use standard Tailwind breakpoints — **`md:` (768px)** as the desktop/mobile header and grid switch, **`sm:`/`min-[420px]`-equivalent** for the quick-links 2→1 col step (use `sm:` = 640px unless it visibly breaks; content must fit at 360px per T5).

#### Header (site-wide, rewritten) — `src/components/CommonComponents/Header/`

| Component | Status | Notes |
|---|---|---|
| `Header.tsx` | **rewritten** | Renders `<DesktopHeader>` (`hidden max-md:… → md:flex`) + `<MobileHeader>` (`md:hidden`). Keeps existing `getMe()`-on-route-change and `fetchUnreadCount()` effects. |
| Desktop layout (in `Header.tsx`) | rewritten | Per reference `.hdr`: left = **chat button** (dispatch `toggleChat`, NO badge) · logo · `NavLinks` (existing, with `MegaMenu`); right = `SearchInput` · **CharacterChip** · `NotificationBell` · messages icon (keep existing `selectTotalUnread` badge) · user `AvatarDropdown` · `AdminMenu`. |
| `CharacterChip.tsx` | **new** | Pill per reference `.hdr-chip`: gold-ring avatar + column [name / **level + coins** (replaces mock HP/MP bars) / location link → `/location/{id}`]. Coins value = `character.currency_balance` from `userSlice`; hide the coins element when `null`/`undefined`. Click on chip toggles `CharacterSwitchDropdown`. No character → fallback chip with dropdown «Создать» / «Выбрать» (current behavior). |
| `CharacterSwitchDropdown.tsx` | **new** | On open: `GET /users/{id}/characters` (reuse `api/userProfile.ts` fetcher). Lists characters (avatar, name, level), active one highlighted and non-clickable. Click on another → `PUT /users/{id}/update_character` (Bearer token) → `dispatch(getMe())` → close. Loading/error states with Russian messages (mandatory error display). Footer links: «Профиль персонажа» → `/profile`, «Управление персонажами» → `/selectCharacter`. Use `dropdown-menu`/`dropdown-item` classes + Motion dropdown preset (design system §12). Close on outside click / Esc. |
| `MobileHeader.tsx` | **new** | Per reference `.hdr-m`: top bar = burger (badge = `selectTotalUnread` + notifications unread) · logo · chat button (dispatch `toggleChat`) · user avatar (`AvatarDropdown`); **character strip** below (avatar, name, level + coins, location link; tap → same `CharacterSwitchDropdown`); collapsible menu = search input + accordion nav sections (same link data as `NavLinks`/`MegaMenu` — extract shared nav data to `Header/navData.ts` to avoid duplication) + two wide buttons «Уведомления» (→ existing notifications view) and «Сообщения» (→ `/messages`) with badges + admin entry when `role` allows. |
| `NavLinks.tsx` / `MegaMenu.tsx` / `SearchInput.tsx` / `AvatarDropdown.tsx` / `NotificationBell.tsx` / `AdminMenu.tsx` | reused | Already .tsx + Tailwind. Touch only if the new layout requires prop tweaks. |
| `redux/slices/userSlice.ts` | **modified** | `CharacterData`: add `level?: number | null; currency_balance?: number | null;` (typing only — payload flows through already). |

Chat entry point decision: **the glued tab button in `ChatWidget.tsx` is removed**; chat opens only from the header chat buttons (desktop + mobile), matching the reference. Header is global (Layout), so chat stays reachable on every page.

#### Main page — `src/components/HomePage/`

| Component | Status | Notes |
|---|---|---|
| `HomePage.tsx` | **rewritten** | New layout per reference: `main` grid `md:grid-cols-[38%_1fr]` (1 col mobile) — left «Куда отправимся» = 3 large nav cards; right «Главное сейчас» = hero slider (min-h ~440px). Below: full-width quick-links grid (4 → 2 → 1 cols), full-width «Живая лента» (2 → 1 col) with «Онлайн» pulse dot, full-width Hall of Fame section, keeping existing data sources. Each section gets a `SectionTitle` row (small gold uppercase label + gradient rule) — new tiny shared component in `HomePage/`. HomePage owns all section wrappers/titles and mounts `<HallOfFame />` as a black-box card. |
| `Button/Button.jsx` + `.module.scss`, `HomePageButton/HomePageButton.jsx` + `.module.scss`, `SmallHomePageButton/SmallHomePageButton.jsx` + `.module.scss` | **migrated → .tsx + Tailwind, SCSS deleted** (T1/T3) | Layout per reference cards: large card = bg image, bottom gradient, gold title, sublink row with gradient divider; small card = centered gold label over image. Visual tokens from design system. |
| `Slider/Slider.jsx` + `.module.scss` and `Slider/ArrowButton|CircleButton|SliderArrowButton|SliderCircleButton` (each .jsx + .module.scss) | **migrated → .tsx + Tailwind, SCSS deleted**; redundant button variants consolidated | New hero-slider layout: controls (arrows + dots) in the top-left bar, tag top-right, title/desc/«Читать» bottom-left. Slide content stays the current hardcoded data. |
| `LatestRoleplayPosts/LatestRoleplayPosts.tsx` | **modified** | Re-layout to reference feed cards (left column: title/avatar/name/LVL; right: location + time + 3-line-clamped text + likes), keep existing fetch/auto-refresh/error handling. |
| `Stats/Stats.tsx` (→ Hall of Fame) | **rewritten** (stays .tsx) | See below. |

#### Hall of Fame — `src/components/HomePage/Stats/` (owned exclusively by its task)

- `Stats.tsx` rewritten as the Hall of Fame **card** (may be renamed to `HallOfFame.tsx` with subcomponents `Podium.tsx`, `RankRow.tsx` in the same dir; update the single import in `HomePage.tsx` at integration time).
- Data: `GET /characters/home-leaderboards?limit=6` via existing `src/api/homeStats.ts` (bump limit param 3 → 6). One fetch, three boards; tab switch is client-side (no refetch).
- Layout per reference: banner (`stats_bg.png` + dark gradient) with active-board title + 3 pill tabs; **podium** (order: rank2 · rank1 center/larger/gold ring+glow · rank3, pedestal heights 96/132/76, medal-colored rank numerals); **rest list** rows (rank, avatar, name, value) for ranks 4–6.
- Real avatars (`entry.avatar`) with `stats_user_img.png` placeholder — no initials circles from the mock.
- Empty/partial states: board with 0 entries → «Пока пусто» (keep current UX); 1–2 entries → render podium slots that exist, no crash; keep error + retry state.
- Row click → character profile (keep current behavior if such navigation exists; otherwise rows are non-interactive).

#### Chat — `src/components/Chat/`

| Component | Status | Notes |
|---|---|---|
| `ChatWidget.tsx` | **modified** | Remove the glued tab toggle button. Add overlay backdrop behind the open panel (`modal-overlay`-style fixed layer, click → `toggleChat`), panel slides in from the left. Panel width: `md:w-[400px]`, **`max-md:w-full`** (reference: `width:100%; max-width:100%` ≤760px). |
| `ChatPanel.tsx` / `ChatHeader.tsx` / others | reused | Internal structure (header with close button, channel tabs, messages, input) already matches the reference; touch only if the full-width mobile layout needs sizing fixes. Ensure the close button in `ChatHeader` works (mandatory since the glued tab is gone). |
| `ChatToggleButton.tsx` | check usage | If it is only used by the removed glued tab — delete it. |

`Layout.tsx` — the content container widens to **1360px** (see 3.3.1); Header/ChatWidget mounting unchanged.

#### 3.3.1 Site-wide container width: 1240px → 1360px (user decision)

The user confirmed expanding the content container to **1360px site-wide** (matching the reference), not only on the main page.

Current state: there is **no shared width token** — `max-w-[1240px]` is hardcoded in ~45 places across ~30 `.tsx` files: `App/Layout/Layout.tsx` (the global content wrapper), `CommonComponents/Header/Header.tsx`, `RulesPage/RulesPage.tsx`, `Messenger/MessengerPage.tsx`, `ItemsAdminPage/ItemsAdminPage.tsx`, `AdminNpcsPage/AdminNpcsPage.tsx`, `AdminModerationPage/AdminModerationPage.tsx`, `Tickets/AdminTicketsPage.tsx`, and the `Admin/*` subtree (AdminPage, RulesAdminPage, ArchiveAdminPage, TitlesPage, BattlesPage, StarterKitsPage, PerksPage, ProfessionsAdminPage, DungeonsPage×3, RecipesAdminPage, AdminCosmetics, AdminBattlePass, CharactersPage×2, RbacAdminPage, MobsPage×3). No occurrences in `.jsx`/SCSS/CSS or `tailwind.config.js`.

Decision: **introduce a design token instead of a new magic number.**
- `tailwind.config.js` → `theme.extend.maxWidth: { container: '1360px' }`.
- Mechanical sweep: replace every `max-w-[1240px]` with `max-w-container` (all files above, incl. `Layout.tsx`); the new Header/MobileHeader use `max-w-container` from the start.
- Future width changes become a one-line config edit; `docs/DESIGN-SYSTEM.md` gets a one-row addition to the tokens table.

Assignment: the sweep belongs to **Task 3** (header task) — it already owns `Header.tsx` (the only file shared with the sweep), and the remaining replacements are logic-free. Nested page-level `max-w-[1240px]` wrappers inside Layout's container are replaced too, for consistency. Risk: pages were designed for 1240px — content simply gains breathing room (containers are `mx-auto` + fluid grids); Reviewer spot-checks key pages at 1440px and 1280px viewports.

### 3.4 Data Flow

```
Page load / route change
  Header useEffect → dispatch(getMe())
    → user-service GET /users/me  ──httpx──→ character-service GET /characters/{id}/short_info   (now incl. currency_balance)
                                  ──httpx──→ locations-service GET /locations/{id}/details        (location name for chip)
    → userSlice.character {id, name, avatar, level, currency_balance, current_location}
    → CharacterChip (desktop) / MobileHeader strip render name · level · coins · location link

Character switch (header dropdown)
  chip click → CharacterSwitchDropdown opens → GET /users/{userId}/characters (list w/ avatar, name, level)
  → user clicks character N → PUT /users/{userId}/update_character {current_character: N}  (JWT)
  → 200 → dispatch(getMe()) → chip re-renders with new character; errors shown in RU

Hall of Fame
  HallOfFame mount → GET /characters/home-leaderboards?limit=6 → 3 boards cached in component state
  → tab click switches board client-side (podium top-3 + rest 4-6)

Chat
  header chat button (desktop/mobile) → dispatch(toggleChat) → ChatWidget panel + overlay
  overlay click / ChatHeader close → toggleChat; ≤md panel is 100% width
```

No queues, no async jobs, no cross-service call changes beyond the one additive JSON key.

### 3.5 Security Considerations

- **No new endpoints.** No auth model changes, no new rate-limiting surface.
- **`currency_balance` exposure:** `short_info` is public (no auth) — adding gold makes it publicly readable per character. This is **not a new exposure**: `GET /characters/{id}/full_profile` already returns `currency_balance` publicly. Accepted.
- **Character switch** uses the existing `PUT /users/{id}/update_character`: JWT required, ownership enforced (self or admin/moderator), membership of the target character validated via `UserCharacter` — frontend must send the Bearer token (as `SelectCharacterPage` does) and surface 401/403/400 errors in Russian.
- **Input validation:** no new inputs on backend. Frontend dropdown sends only a numeric `current_character` from the fetched list.
- **No secrets, no logging changes.** Error messages must not leak internals (reuse existing messages).

### Questions for PM — RESOLVED (user answers recorded in section 1)

1. **Content container width:** → **User decided: expand to 1360px SITE-WIDE.** Implemented via a new `max-w-container` token + sweep of all hardcoded `max-w-[1240px]` usages — see section 3.3.1; assigned to Task 3.
2. **Glued chat tab removal:** → **User confirmed: remove.** Chat opens only from the header buttons (Task 6, as designed).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Parallelism: **Tasks 1, 3, 4, 5 start in parallel** (no shared files; contract for coins is fixed in section 3.2, frontend hides coins while the field is absent). Task 2 after 1; Task 6 after 3 (chat entry point moves to the header); Task 7 last.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Expose character coins: add `currency_balance` to character-service `short_info` response; pass it through user-service `_fetch_character_short` + add `currency_balance: Optional[int] = None` to `CharacterShort` (Pydantic v1). Additive only, no schema/DB changes. | Backend Developer | DONE | `services/character-service/app/main.py` (get_short_info ~1573); `services/user-service/main.py` (_fetch_character_short ~114); `services/user-service/schemas.py` (CharacterShort ~56) | — | `GET /characters/{id}/short_info` returns `currency_balance` (int); `GET /users/me` returns `character.currency_balance`; existing keys untouched; `python -m py_compile` passes on all modified files; existing tests still pass. |
| 2 | QA: tests for the coins contract. character-service: `short_info` includes correct `currency_balance` (extend `test_short_info_extended.py` or new test). user-service: `/users/me` maps `currency_balance` from mocked character-service response, and returns `null`/omits gracefully when the key is absent from short_info (old character-service). | QA Test | DONE | `services/character-service/app/tests/test_short_info_extended.py` (or new file); `services/user-service/tests/` (new/extended test, mock httpx like existing `/me` tests) | 1 | New tests pass; full pytest suites of both services green; missing-key case covered (proves no lockstep deploy needed). |
| 3 | Global header rewrite (desktop + mobile, site-wide via Layout). Desktop per reference `.hdr`: chat button (dispatch `toggleChat`, NO badge) · logo · NavLinks/MegaMenu · search · **CharacterChip** (avatar, name, **level + coins**, location link) · NotificationBell · messages icon (keep unread badge) · user AvatarDropdown · AdminMenu. New `MobileHeader` (`md:hidden`) per `.hdr-m`: burger with unread badge, logo, chat button, user avatar; character strip; collapsible menu (search + accordion nav from shared `navData.ts` + «Уведомления»/«Сообщения» buttons with badges). New `CharacterSwitchDropdown`: list via `GET /users/{id}/characters`, one-click switch via `PUT /users/{id}/update_character` + `getMe()` re-dispatch, RU error display, guest/no-character fallback. Positioning from the mock; ALL visual tokens from the current design system; no `React.FC`; fits 360px. **Plus container-width sweep (section 3.3.1):** add `maxWidth.container: '1360px'` token to `tailwind.config.js`, replace ALL `max-w-[1240px]` occurrences (~45 across ~30 files, incl. `Layout.tsx`) with `max-w-container`; new header uses `max-w-container`; add the token row to `docs/DESIGN-SYSTEM.md`. | Frontend Developer | DONE | `Header/Header.tsx` (rewrite); new: `Header/CharacterChip.tsx`, `Header/CharacterSwitchDropdown.tsx`, `Header/MobileHeader.tsx`, `Header/navData.ts`; `redux/slices/userSlice.ts` (CharacterData typing); reuse `api/userProfile.ts`; `tailwind.config.js`, `App/Layout/Layout.tsx` + ~28 page files with `max-w-[1240px]` (mechanical sweep, list in 3.3.1); `docs/DESIGN-SYSTEM.md` (token row) | — (coins render once Task 1 deployed; hide while `undefined`) | Header matches reference layout on desktop and ≤768px on every page; chip shows real level/coins/location of the active character (coins hidden when null); switch works in one click and updates chip without reload; errors shown in Russian; `grep -r "max-w-\[1240px\]" src/` returns zero matches, site container is 1360px everywhere; `npx tsc --noEmit` + `npm run build` pass. |
| 4 | Main page layout rewrite + T1/T3 migrations. `HomePage.tsx`: grid `md:[38%_1fr]` («Куда отправимся» = 3 large cards / «Главное сейчас» = hero slider min-h 440px), full-width quick links (4→2→1 cols), full-width «Живая лента» (2→1 col, «Онлайн» pulse), full-width Hall of Fame section wrapper mounting existing `<Stats />`; new shared `SectionTitle`. Migrate to .tsx + Tailwind and delete SCSS: `Button`, `HomePageButton`, `SmallHomePageButton`, `Slider` + its 4 arrow/circle button subcomponents (consolidate duplicates). Re-layout `LatestRoleplayPosts.tsx` cards per reference (keep fetch/refresh/errors). Do NOT touch `Stats/` internals (Task 5 owns that dir). | Frontend Developer | DONE | `HomePage/HomePage.tsx`; `HomePage/SectionTitle.tsx` (new); `HomePage/Button/*`, `HomePage/HomePageButton/*`, `HomePage/SmallHomePageButton/*`, `HomePage/Slider/*` (.jsx→.tsx, .module.scss deleted); `HomePage/LatestRoleplayPosts/LatestRoleplayPosts.tsx` | — | Layout matches reference on desktop/760/420/360px; zero remaining `.jsx`/`.module.scss` under `HomePage/` except `Stats/`; slider/cards keep current content and links; visual style = current design system; `npx tsc --noEmit` + `npm run build` pass. |
| 5 | Hall of Fame card (owns `HomePage/Stats/` dir only). Rewrite as reference block: banner (`stats_bg.png`) + active-board title + 3 pill tabs; podium top-3 (rank1 center, larger gold-ring avatar + glow, pedestals 132/96/76, medal-colored numerals); rest list ranks 4–6. Data: `homeStats.ts` with `limit=6`, single fetch, client-side tab switch. Real avatars + `stats_user_img.png` placeholder. Handle 0 entries («Пока пусто»), 1–2 entries (partial podium), error + retry (RU). | Frontend Developer | DONE | `HomePage/Stats/Stats.tsx` (rewrite; optional rename to `HallOfFame.tsx` + `Podium.tsx`/`RankRow.tsx` in same dir — coordinate the single import in `HomePage.tsx` with Task 4 owner at integration); `src/api/homeStats.ts` (limit param) | — (integration import touch-up after 4) | Block matches reference layout incl. mobile (podium compresses per `.podium` media rule); real top-6 data with avatars on all 3 tabs; empty/partial/error states work; `npx tsc --noEmit` + `npm run build` pass. |
| 6 | Chat panel behavior per reference: remove the glued tab toggle from `ChatWidget.tsx` (delete `ChatToggleButton.tsx` if orphaned); add click-to-close overlay backdrop behind the open panel; panel width `md:w-[400px]`, **full width below md**; verify close button in `ChatHeader` and full-width mobile layout of tabs/messages/input. Chat must open from the new header buttons on every page. | Frontend Developer | DONE | `Chat/ChatWidget.tsx`; `Chat/ChatToggleButton.tsx` (likely delete); `Chat/ChatPanel.tsx` (only if sizing fixes needed) | 3 | No glued tab anywhere; chat opens via header buttons (desktop + mobile) on any page; overlay click and close button both close it; ≤768px panel is 100% width, no horizontal scroll at 360px; `npx tsc --noEmit` + `npm run build` pass. |
| 7 | Final review: re-run `pytest` (both backend services), `npx tsc --noEmit`, `npm run build`; live verification via chrome-devtools (admin test account): home page desktop + 760/420/360px emulation, header on other pages (location, profile, admin), coins value correct vs DB, character switch round-trip, leaderboard tabs with real avatars, mobile chat full-width open/close, zero console errors / failed network calls. Container sweep: zero `max-w-[1240px]` left in `src/`, content is 1360px site-wide; spot-check key pages (admin tables, messenger, rules) at 1440px and 1280px viewports for layout regressions. Verify T1/T3 (no new .jsx/SCSS in touched scope), no `React.FC`, design-system compliance, RU error messages. | Reviewer | TODO | — | 1,2,3,4,5,6 | PASS verdict in section 5 with recorded check results + live-verification evidence; all FAIL findings looped back per pipeline (max 3 iterations). |
| 8 | Fix pre-existing tsc errors (64, tech-debt surfaced by dependency refresh) | Frontend Developer | DONE | `src/api/{archive,battlePassAdmin,perks,professions,rules,squads,titles}.ts`; `Admin/GameTimeAdminPage.tsx`; `AdminLocationsPage/*` + `EditForms/*`; `CommonComponents/LocationSearch/LocationSearch.jsx`, `Modal/Modal.jsx`, `Tooltip/Tooltip.jsx` (JSDoc types only); `redux/actions/{country,region,district,location}EditActions.js` (JSDoc thunk args); `AdminPathEditor/PathEditorCanvas.tsx`; `ItemsAdminPage/ItemForm.tsx`; `redux/slices/{profileSlice,messengerSlice,ticketSlice,userProfileSlice}.ts`; `WorldPage/WorldPage.tsx`; `pages/BattlePage/*`; deleted 5 orphaned Grimoire components (`Bestiary/Grimoire{Book,Spread,Navigation,PageInfo,PageAvatar}.tsx`, dead since FEAT-068 scroll redesign) | — | `npx tsc --noEmit` → 0 errors total; `npm run build` passes; runtime behavior unchanged (types/JSDoc only + dead-code removal). |

**Sequencing notes for PM:**
- Launch 1, 3, 4, 5 in parallel (background agents). Launch 2 when 1 is done; launch 6 when 3 is done.
- Tasks 4 and 5 share one integration point (the `Stats` import in `HomePage.tsx`): task 4 keeps mounting `<Stats />`; if task 5 renames the component, the import is updated by whichever task finishes second (or by task 6/PM as a follow-up edit) — never both editing `HomePage.tsx` simultaneously.
- Commits: task 1 as `feat(character-service,user-service)`, frontend tasks as separate `feat(frontend)` commits, QA as `test(...)`.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-07-16
**Result:** FAIL (1 blocking issue; everything else passed)

#### Automated Check Results
- [x] `py_compile` (character-service/app/main.py, user-service/main.py, user-service/schemas.py, both test files) — **PASS** (compiled via `compile()`; `__pycache__` is root-owned from docker, so `python -m py_compile` can't write bytecode on the host — cosmetic env issue only)
- [x] `pytest` character-service — **PASS**: 559 passed, 1 skipped (venv with Pydantic v1 per service requirements)
- [x] `pytest` user-service — **PASS**: 445 passed (venv per service requirements, mysqlclient skipped — tests use SQLite/pymysql, as QA noted)
- [x] `npx tsc --noEmit` — **PASS**: 0 errors project-wide (Task 8 debt confirmed fixed)
- [x] `npm run build` — **PASS** (exit 0)
- [x] `docker-compose config` — **PASS** (valid; DB_* warnings are from the local stale `.env`, see Environment Notes)
- [x] `grep -r "max-w-[1240px]" src/` — **0 matches**; `max-w-container` token (1360px) present in `tailwind.config.js`, documented in `docs/DESIGN-SYSTEM.md`
- [x] No `React.FC`, no TODO/FIXME/HACK, no `.jsx`/`.module.scss` left under `HomePage/` (Stats/ included), deleted components (`ChatToggleButton`, `HomePageButton`, `SmallHomePageButton`, `Slider/*Button` variants, 5 `Grimoire*` files) have zero remaining importers (tsc-proven)

#### Code Review
- Backend contract additive and correct: `short_info` → `currency_balance` (character-service `app/main.py` ~1600), passed through `_fetch_character_short` + `CharacterShort.currency_balance: Optional[int] = None` (Pydantic v1 style). No lockstep deploy needed — covered by user-service tests (missing-key → None).
- Pydantic ↔ TS consistency: `userSlice.CharacterData` extended with `level?: number | null; currency_balance?: number | null` — matches payload; chip hides coins/level when null.
- Switch flow follows `SelectCharacterPage` pattern (`PUT /users/{id}/update_character` with Bearer from `accessToken`, then `getMe()`); Russian error display present (toast + inline retry in `CharacterSwitchDropdown`); loading/empty/error states all covered.
- Hall of Fame: single fetch `limit=6` (`HOME_LEADERBOARDS_LIMIT`), client-side tabs, partial-podium/empty/error+retry states, avatar placeholder fallback via `onError`.
- Chat: glued tab removed, overlay backdrop (click-to-close), X button in `ChatHeader` (`aria-label="Закрыть чат"`), panel `md:w-[400px]` / full width below md, z-index layering above header.
- Task 8 diffs spot-checked — types/JSDoc only, no runtime changes; `config.headers || {}` no-op guard removal is behavior-neutral on axios 1.x.
- Design system: `dropdown-menu`/`dropdown-item`/`nav-link`/`gold-text`/`gray-bg`/`btn-blue`/`gold-scrollbar`/`image-card`/`hover-gold-overlay` + config tokens used throughout; no new SCSS; mock typography/gradients not imported.

#### Live Verification Results (chrome-devtools, admin account, dev stack via nginx :80)
- Pages tested: `/home` (1440 / 1280 / 1024 / 800 / 760 / 420-emulated / 360-emulated), `/messages`, `/admin` (1440).
- **Coins contract live:** `/users/me` → `character.currency_balance = 100` = DB value; `short_info` includes `currency_balance`; chip shows "Ур. 1 · 100 · Врата крепости".
- **Character switch round-trip:** dropdown lists 2 characters (active highlighted + disabled), one-click switch to "Артория" updated chip (Ур. 12, 2 500, avatar) without reload, switched back OK; `PUT /update_character` → 200 both ways.
- **Hall of Fame:** real top-6 on all 3 tabs (seeded local test data), podium 2·1·3 with crown/gold ring/glow, medal numerals, pedestal heights, ranks 4–6 list; real avatar URLs render, broken URLs fall back to `stats_user_img.png`; tab switch client-side (no refetch).
- **Live feed:** 2-col grid with "Онлайн" pulse; renders real post.
- **Mobile header (≤768):** burger + badge, logo, chat button, avatar; character strip with level/coins/location; accordion nav (all 5 mega-menu sections + static links + АДМИНКА for staff); inline notifications panel with "Отметить все как прочитанные"; Уведомления/Сообщения buttons with badges.
- **Chat:** opens from desktop and mobile header buttons; X-close, overlay-click-close, reopen — all verified; panel full-width at ≤768 (745/760px incl. scrollbar), 400px on desktop.
- **Guest header:** fallback chip "Персонаж" with Создать/Выбрать dropdown, no crash.
- **No horizontal scroll** at 1440/1280/1100/760/420/360. **Horizontal scroll present at 768–~1085px** — see issue #1.
- **Console:** zero errors on all tested pages (only pre-existing React Router v7 future-flag warnings). **Network:** all XHR/fetch 200 (one transient 403 on `/party/invites/incoming` was caused by the reviewer's synthetic seed character missing `user_id`; re-test with correct ownership → 200; pre-existing polling code, unrelated to the feature).
- Container sweep: `/messages` and `/admin` reflow correctly at 1360px, header aligned with content.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `src/components/CommonComponents/Header/Header.tsx:59-115` | Desktop header (`hidden md:flex`) does not fit between 768px and ~1085px: both clusters are `flex-shrink-0`, so total min-width ≈ 1085px (1021px at 800vw) → **horizontal page scroll on EVERY page at tablet/small-laptop widths** (T5 violation: content must not exceed viewport). Measured: scrollWidth 1021 @ 800px, 1085 @ 1024px; fits from ~1085px. Fix options: allow shrinking/truncation (drop `flex-shrink-0` on the right cluster, tighter gaps, hide `SearchInput` below `lg`), or switch to the mobile header up to `lg` instead of `md`. Must be verified at 768, 800, 1024 px with zero horizontal scroll. | Frontend Developer | FIXED |
| 2 | `src/components/HomePage/Button/Button.tsx:63-74` | LOW (non-blocking, fix along with #1 if cheap): large-card sublink labels clip mid-word at 360px ("ПЕРСОНАЖ", "КОНСУЛЬТА") — no truncate/ellipsis or size step-down on the sublink row. Cosmetic only, content reachable via card click. | Frontend Developer | FIXED |

#### Fix #1 (Frontend Developer, 2026-07-16) — applied after Review #1

- **Issue #1** — header desktop/mobile boundary moved from `md` (768px) to **`lg` (1024px)**: `Header.tsx` desktop header is now `hidden lg:flex`, `MobileHeader.tsx` is `lg:hidden` (mobile header is fluid and fits any width). The roomier spacing tier shifted one step up (`lg:` gap/padding modifiers → `xl:` in `Header.tsx` and `NavLinks.tsx`), and the decorative `SearchInput` renders only from `xl` (1280px) via a `hidden xl:block` wrapper in `Header.tsx` (`SearchInput.tsx` itself untouched — reused by `ArchivePage`). Live-measured (chrome-devtools, admin account, worst-case header with AdminMenu): zero horizontal scroll at 360/420/768/800/900/1024/1080/1280/1440; desktop header intrinsic width 969px at 1024vw (128px slack between clusters), search visible again from 1280 (26px slack, same as pre-fix). Full reference layout (incl. search) intact at ≥1280px.
- **Issue #2** — `Button.tsx` sublinks: font step-down at base (`text-[11px] tracking-[0.02em]`, restoring `text-[13px] tracking-[0.06em]` from `sm:`) + `min-w-0` on the button and `block truncate` on the label span. At 360px only the longest label («Консультант») ellipsizes cleanly; no mid-word clipping.
- Checks: `npx tsc --noEmit` — 0 errors; `npm run build` — exit 0.

#### Pre-existing issues noted (not blocking, not caused by this feature)
- `SearchInput` (desktop) and the mobile menu search are decorative — no submit/navigation logic. Pre-existing behavior kept as-is (parity).
- Local dev environment drift (machine-specific, NOT repo bugs, NOT for ISSUES.md): the local `.env` lacks `DB_*`/`JWT_SECRET_KEY` keys (see `.env.example`); the local MySQL volume (created 2026-03-11) was initialized with the pre-cb24665 hardcoded credentials, so current `.env` values don't match it; host port 8001 is occupied by an unrelated project (`creative_generator`), which blocks photo-service's port binding and therefore nginx startup (hard upstream dependency). For this review the stack was run with a supplementary env file, photo-service was started without the host port, and `alembic_version_user` was advanced 0010→0011 (rows 32/33 already existed). Local DB also received seeded test data for verification (6 test characters, character_logs, character_cumulative_stats, second character linked to admin) — harmless, removable.

#### QA Coverage
- Task 2 DONE: 3 tests character-service (`test_short_info_extended.py::TestShortInfoCurrencyBalance`), 9 tests user-service (`tests/test_me_currency_balance.py`) incl. missing-key tolerance. Both suites green. Coverage adequate for the backend change.

**Verdict: FAIL — re-review required after issue #1 is fixed (single localized fix in `Header.tsx`; everything else already passes and will not need re-testing beyond the 768–1085px range + a smoke check).**

### Review #2 — 2026-07-16
**Result:** PASS

Scope: re-verification of Fix #1 (issues #1 and #2 from Review #1) + smoke of the previously verified flows. All Review #1 findings are resolved; no new issues.

#### Automated Check Results
- [x] `npx tsc --noEmit` — **PASS** (0 errors project-wide)
- [x] `npm run build` — **PASS** (exit 0)
- Backend untouched since Review #1 (`git status` unchanged for `services/*-service`) — pytest results from Review #1 remain valid (559 + 445 passed).

#### Code Review of the fix
- `Header.tsx`: desktop header now `hidden lg:flex` (line 59), spacing tier `lg:` → `xl:`; `SearchInput` wrapped in `hidden xl:block` (line 88; `SearchInput.tsx` itself untouched — still reused by other pages).
- `MobileHeader.tsx`: `lg:hidden` (line 156) — fluid mobile header now covers 0–1023px.
- `Button.tsx`: sublinks `min-w-0` + `text-[11px] tracking-[0.02em]` at base, `sm:text-[13px] sm:tracking-[0.06em]`; label span `block truncate` (lines 69–72).

#### Live Verification Results (chrome-devtools, admin account — worst-case header incl. AdminMenu)
| Viewport | Header variant | scrollWidth vs viewport | Notes |
|---|---|---|---|
| 360 (emulated, mobile) | mobile | 360 = 360, no h-scroll | sublinks fully visible, only «Консультант» → «КОНСУЛЬТА…» ellipsizes cleanly (issue #2 fixed) |
| 768 | mobile | 753 < 768, no h-scroll | issue #1 range fixed |
| 800 | mobile | 785 < 800, no h-scroll | issue #1 range fixed |
| 1024 | desktop | 1009 ≥ content; header intrinsic 969px, fits | search hidden (by design until xl) |
| 1280 | desktop | 1265, no h-scroll | search visible again — full reference layout |
| 1440 | desktop | 1425, no h-scroll | — |
- Smoke: character-switch dropdown opens (list + «Управление персонажами»), chat opens/closes from the header (overlay + X), Hall of Fame renders all 3 boards with seeded data (podium + ranks 4–6), footer counters OK.
- Console: **zero errors**; network: leaderboards/posts/me/stats all 200.

All acceptance criteria of tasks 1–6 and 8 are met. Feature is ready for completion (status → DONE, pending PM close-out). Reminder for PM: nothing is committed yet — the whole feature is in the working tree; local reviewer-seeded test data (6 characters + logs/stats in the local MySQL volume) can be removed or kept, it does not affect the repo.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-07-16 — PM: фича создана, макеты импортированы из Claude Design (features/design-refs/FEAT-mainpage-redesign-MainPage.dc.html), запускаю Codebase Analyst
[LOG] 2026-07-16 — Analyst: анализ завершён. Затронут в основном frontend (HomePage, глобальный Header, Chat, Layout); нужен небольшой additive-бэкенд: добавить currency_balance в short_info (character-service) и прокинуть через /users/me (user-service). Лидерборд с аватарками, смена персонажа, живая лента, счётчики футера — эндпоинты уже есть. Все ассеты макета в репо. БД-изменений нет. 4 вопроса к PM (монеты, UX смены персонажа, бейдж чата, глобальность хедера) — см. Questions for PM в секции 2.
[LOG] 2026-07-16 — Architect: проектирование завершено. 1 additive API-контракт (currency_balance в short_info + /users/me), без миграций БД. 7 задач: 1 backend, 1 QA (обязательный), 4 frontend (хедер desktop+mobile+смена персонажа; главная страница + миграции .jsx→.tsx/Tailwind; Зал славы; поведение чата), 1 review. Задачи 1/3/4/5 параллельно, 2 после 1, 6 после 3, 7 последняя. 2 вопроса к PM с дефолтами (ширина контейнера 1240 vs 1360; удаление приклеенной кнопки чата) — см. Questions for PM в секции 3.
[LOG] 2026-07-16 — Architect: получены ответы пользователя, вопросы закрыты. Контейнер расширяется до 1360px на всём сайте: добавлен раздел 3.3.1 — новый токен max-w-container в tailwind.config.js + механическая замена всех ~45 хардкодов max-w-[1240px] (~30 файлов, включая Layout.tsx). Свип включён в задачу 3 (хедер) — единственный конфликтный файл Header.tsx уже принадлежит ей, параллельность 1/3/4/5 не нарушена. Приклеенная кнопка чата удаляется (задача 6, как спроектировано). Обновлены критерии приёмки задач 3 и 7 (grep-проверка отсутствия 1240px, спот-чек страниц на 1440/1280px).
[LOG] 2026-07-16 17:44 — Backend Dev: задача #1 завершена. Добавлен currency_balance в ответ GET /characters/{id}/short_info (character-service), прокинут через _fetch_character_short и схему CharacterShort (user-service) — теперь /users/me возвращает character.currency_balance. Изменения аддитивные, без миграций. py_compile пройден для всех 3 файлов; pytest локально не запустить (на хосте Pydantic v2, контейнеры не подняты) — статически проверено, что существующие тесты не фиксируют точный набор ключей short_info.
[LOG] 2026-07-16 17:50 — Frontend Dev: начал задачу #5 (Зал славы, каталог HomePage/Stats/).
[LOG] 2026-07-16 17:58 — Frontend Dev: задача #5 завершена. Stats.tsx переписан как карточка «Зал славы»: баннер stats_bg.png с заголовком активной доски и 3 pill-табами (Символов за сутки / PvP / PvE), пьедестал топ-3 (новый Podium.tsx: ранг 1 в центре с золотым кольцом и свечением, постаменты 132/96/76, медальные цифры), список рангов 4–6 (новый RankRow.tsx). Данные: один запрос /characters/home-leaderboards?limit=6 (homeStats.ts: добавлена константа HOME_LEADERBOARDS_LIMIT=6), переключение табов на клиенте. Реальные аватарки с фолбэком stats_user_img.png; состояния: загрузка, ошибка+«Повторить», «Пока пусто», частичный пьедестал (1–2 записи). Адаптив: пьедестал сжимается ≤768px (по .podium из макета), аватарки уменьшаются <420px — влезает в 360px. Импорт HomePage не менялся (./Stats/Stats). Проверки: npm run build — OK; npx tsc --noEmit — в моих файлах 0 ошибок (64 ранее существовавших ошибки в чужих файлах на main, к задаче не относятся). Попутно починено окружение: node_modules/dist были root-owned (созданы docker-контейнером) — владелец исправлен, npm install выполнен.
[LOG] 2026-07-16 17:52 — Frontend Dev: начал задачу #4 (layout главной страницы + миграции T1/T3 в HomePage/).
[LOG] 2026-07-16 18:25 — Frontend Dev: задача #4 завершена. HomePage.tsx переписан по макету: верхняя сетка md:[38%_1fr] («Куда отправимся» — 3 больших карточки, «Главное сейчас» — hero-слайдер min-h 440px c управлением в верхней панели и «Читать» внизу), полноширинные быстрые ссылки (4→2→1 колонок: md / min-[420px] / base), «Живая лента» (2→1 колонки, пульс «Онлайн» в заголовке секции), секция «Зал славы» монтирует <Stats /> как чёрный ящик. Новый общий SectionTitle.tsx (золотой лейбл + градиентная линия). Миграции: Button и Slider переписаны на .tsx + Tailwind (SCSS удалён); CircleButton мигрирован на .tsx на прежнем пути (его импортирует CreateCharacterPage/Pagination — API сохранён); мёртвые дубликаты HomePageButton/, SmallHomePageButton/, Slider/ArrowButton/, Slider/SliderArrowButton/, Slider/SliderCircleButton/ удалены (нигде не импортировались — консолидация, а не переписывание мёртвого кода). LatestRoleplayPosts: сетка 2 колонки, limit 5→6, карточки по макету (min-h 150px, широкая колонка аватара), заголовок секции перенесён в HomePage; fetch/автообновление/ошибки не тронуты. Под HomePage/ не осталось .jsx/.scss (кроме Stats/ — задача #5). max-w-container внутри HomePage не нужен — контейнер даёт Layout.tsx (задача #3). Проверки: npm run build — OK (9.8s), npx tsc --noEmit — 0 ошибок в моих файлах; 64 ошибки в чужих файлах воспроизводятся и на HEAD с текущими node_modules (проверено во временном worktree) — к задаче не относятся.
[LOG] 2026-07-16 17:51 — Frontend Dev: начал задачу #3 (глобальный хедер desktop+mobile, смена персонажа, свип ширины контейнера).
[LOG] 2026-07-16 18:40 — Frontend Dev: задача #3 завершена. Header.tsx переписан по макету .hdr: слева кнопка чата (dispatch toggleChat, без бейджа) · лого · NavLinks/MegaMenu; справа поиск · CharacterChip · NotificationBell · иконка сообщений (бейдж непрочитанных сохранён) · аватар пользователя · AdminMenu. Новый CharacterChip.tsx: золотое кольцо-аватар + имя / Ур. + монеты (currency_balance; скрываются при null/undefined) / ссылка на локацию; клик открывает CharacterSwitchDropdown.tsx — список персонажей (GET /users/{id}/characters), смена в один клик (PUT /users/{id}/update_character + повторный getMe()), активный подсвечен, ошибки по-русски (toast + inline retry), закрытие по Esc/клику вне; гость и «без персонажа» — фолбэк-дропдаун Создать/Выбрать (текущее поведение). Новый MobileHeader.tsx (md:hidden, впервые на сайте): верхняя панель бургер (бейдж = сообщения+уведомления) / лого / кнопка чата / аватар; полоса персонажа (аватар, имя, Ур.+монеты, ссылка на локацию, тап = тот же дропдаун смены); раскрывающееся меню — поиск, аккордеон-навигация из общего navData.ts (Главная + 5 категорий мегаменю + Правила/События/Тикет + Админка для staff), широкие кнопки «Уведомления» (инлайн-список с «Отметить все как прочитанные») и «Сообщения» с бейджами. navData.ts извлечён как единый источник навигации (NavLinks использует его же). userSlice: CharacterData дополнен level/currency_balance. Свип ширины: токен maxWidth.container=1360px в tailwind.config.js, все 45 вхождений max-w-[1240px] в ~30 файлах заменены на max-w-container (grep = 0 совпадений), строка токена добавлена в docs/DESIGN-SYSTEM.md. Проверки: npm run build — OK (9.05s, exit 0); npx tsc --noEmit — 0 ошибок в моих файлах (64 ошибки в 28 чужих файлах воспроизводятся на чистом HEAD во временном worktree — pre-existing, к задаче не относятся).
[LOG] 2026-07-16 18:50 — Frontend Dev: начал задачу #6 (поведение панели чата по макету).
[LOG] 2026-07-16 19:00 — Frontend Dev: задача #6 завершена. ChatWidget.tsx переписан: приклеенный «язычок» чата удалён — чат открывается только кнопками в хедере (десктоп + мобильный, обе уже диспатчат toggleChat); добавлен оверлей-фон за открытой панелью (fixed inset-0, bg-black/50 + blur, клик = закрыть, плавная opacity — как в макете, z-70/z-80 поверх хедера z-50); панель теперь fixed с transform-слайдом слева, ширина md:w-[400px] на десктопе и 100% ниже md (правило .chat-panel из макета). В ChatHeader добавлена кнопка закрытия (крестик, aria-label «Закрыть чат») — проброшена через onClose из ChatWidget→ChatPanel; ранее кнопки закрытия не было вовсе (закрывал только язычок). Осиротевший ChatToggleButton.tsx удалён (нигде не импортировался). Внутренняя структура чата (табы каналов, сообщения, инпут) не тронута — все ширины флюидные (min-w-0/max-w-full), горизонтального скролла на 360px нет. Проверки: npm run build — OK (exit 0); npx tsc --noEmit — 0 ошибок в файлах Chat/*, в чужих файлах осталось 57 pre-existing ошибок (было 64 — параллельный агент чинит).
[LOG] 2026-07-16 19:20 — Frontend Dev: задача #8 завершена. Исправлены все 64 pre-existing ошибки tsc в 28 файлах (техдолг, вскрытый обновлением node_modules; lockfile-диff тривиален — devOptional→dev у @types/react той же версии, откат не помог бы). Только типы, поведение в рантайме не изменено: (1) 7 файлов api/* — удалён no-op guard `config.headers || {}` (в axios 1.x headers в интерсепторе всегда AxiosHeaders); (2) GameTimeAdminPage — тип иконок react-feather заменён на родной Icon; (3) JSDoc-типы аргументов thunk'ов в 4 .js-файлах redux/actions (RTK выводил ThunkArg=undefined) и JSDoc-пропсы у LocationSearch.jsx, Modal.jsx, Tooltip.jsx, CountdownTimer.jsx (комментарии, код не тронут); (4) типы выровнены с фактическим рантаймом: PathEditorCanvas (map_x/map_y опциональны), ItemForm (max_durability number|string — форма хранит строки), profileSlice (опциональные поля синтетических пустых слотов; добавлен отсутствовавший socketed_items: SocketedItemDetail[] — бэкенд его возвращает, тип отставал), WorldPage (RouteParams interface→type для useParams), BattlePage/BattlePageBar (SkillSlot с индекс-сигнатурой, опциональные isCooldown/setTurnData), messenger/ticket/userProfile slices (каст void-ThunkArg, типизированные предикаты addMatcher); (5) удалены 5 осиротевших компонентов Bestiary/Grimoire* — мертвы с редизайна FEAT-068, импортировали несуществующие экспорты bestiarySlice (GrimoireMagic жив, не тронут); (6) убраны 2 мёртвых пропса (allowClear, countryId), которые LocationSearch никогда не читал. Проверки: npx tsc --noEmit — 0 ошибок во всём проекте; npm run build — OK (8.98s, exit 0). Header/HomePage/Stats/Chat не тронуты (принадлежат задачам 3–6).
[LOG] 2026-07-16 18:20 — Reviewer: начал проверку (задача #7).
[LOG] 2026-07-16 19:55 — Reviewer: автоматические проверки пройдены полностью: pytest character-service 559 passed / user-service 445 passed (venv с Pydantic v1), tsc — 0 ошибок во всём проекте, npm run build — OK, py_compile — OK, grep max-w-[1240px] — 0 совпадений, React.FC/TODO/остатки .jsx+.scss — не найдены. Контракт currency_balance согласован (Pydantic ↔ TS).
[LOG] 2026-07-16 20:30 — Reviewer: живая проверка выполнена (chrome-devtools, админ-аккаунт). Работают: монеты/уровень/локация в чипе (значение сверено с БД), смена персонажа туда-обратно без перезагрузки, Зал славы с реальными данными и аватарками (подиум + список, табы), живая лента, мобильный хедер (бургер, аккордеон, полоса персонажа, уведомления), чат из хедера на десктопе и мобильном (оверлей, крестик, полная ширина ≤768), гостевой фолбэк, /messages и /admin на 1360px. Консоль — 0 ошибок, сеть — все запросы 200. Для запуска локального стека потребовалось восстановить окружение (устаревший .env, старые креды MySQL-волюма, занятый порт 8001) — детали в Review Log, к репозиторию не относится; в локальную БД добавлены тестовые персонажи для проверки лидерборда.
[LOG] 2026-07-16 20:40 — Reviewer: проверка завершена, результат FAIL. 1 блокирующая проблема: десктопный хедер не помещается на ширинах 768–~1085px (оба кластера flex-shrink-0, мин. ширина ~1085px) → горизонтальный скролл на ВСЕХ страницах на планшетных ширинах (нарушение T5). Назначено Frontend Developer, файл Header.tsx. Плюс 1 необязательное косметическое замечание (обрезка подписей карточек на 360px, Button.tsx). Всё остальное — PASS; после фикса нужна точечная перепроверка 768/800/1024px.
[LOG] 2026-07-16 21:20 — Frontend Dev: исправлены замечания Review #1. Проблема #1 (блокирующая): граница десктопного/мобильного хедера перенесена с md (768px) на lg (1024px) — Header.tsx теперь hidden lg:flex, MobileHeader lg:hidden; просторные отступы сдвинуты на ступень выше (lg:→xl: в Header.tsx и NavLinks.tsx), декоративный SearchInput показывается только с xl (1280px, обёртка hidden xl:block в Header.tsx; сам компонент не тронут — используется в ArchivePage). Живая проверка (chrome-devtools, админ-аккаунт — худший случай с AdminMenu): горизонтального скролла нет на 360/420/768/800/900/1024/1080/1280/1440; на 1024 запас между кластерами 128px, на 1280 поиск снова виден (запас 26px, как до фикса); полный макет хедера сохранён на ≥1280px. Проблема #2 (косметическая): подссылки больших карточек (Button.tsx) — уменьшение шрифта на базе (11px, 13px с sm:) + min-w-0/truncate; на 360px обрезки посреди слова нет, самая длинная подпись («Консультант») аккуратно обрезается многоточием. Статусы в таблице секции 5 обновлены на FIXED. Проверки: npx tsc --noEmit — 0 ошибок; npm run build — OK (exit 0).
[LOG] 2026-07-16 21:05 — Reviewer: начал повторную проверку (Review #2) после фикса Frontend Developer.
[LOG] 2026-07-16 21:20 — Reviewer: Review #2 завершён, результат PASS. Обе проблемы исправлены и проверены вживую: граница хедера перенесена md→lg (мобильный хедер на планшетах 768–1023px, горизонтального скролла нет на 360/768/800/1024/1280/1440; поиск появляется с 1280px, полный референс-layout сохранён), подписи карточек на 360px больше не обрезаются посреди слова (truncate с многоточием). tsc — 0 ошибок, build — OK, консоль — 0 ошибок, смоук основных сценариев (смена персонажа, чат из хедера, Зал славы) — OK. Фича готова к закрытию PM.
[LOG] 2026-07-16 18:20 — QA: задача #2 завершена. 12 новых тестов на контракт currency_balance: character-service — 3 теста в test_short_info_extended.py (значение в short_info, дефолт 0, аддитивность ключей); user-service — 9 тестов в новом tests/test_me_currency_balance.py (схема CharacterShort терпит отсутствующий ключ → None без ValidationError; _fetch_character_short с замоканным httpx; /users/me со значением и без ключа — lockstep-деплой не нужен). Полные сьюты прогнаны в venv с Pydantic v1 (как в CI): character-service 559 passed / 1 skipped, user-service 445 passed. На хосте Pydantic v2, поэтому использованы отдельные venv по requirements.txt сервисов (для user-service локально пропущен mysqlclient — нет системных MySQL-заголовков; тесты используют SQLite/pymysql, в CI ставится полный requirements).
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Главная страница** перестроена по макету из Claude Design: сетка 38%/62% (навигационные карточки + слайдер), быстрые ссылки 4→2→1 колонки, живая лента на всю ширину, Зал славы. Визуальный стиль — текущая дизайн-система (типографика/обводки из макета не переносились).
- **Новый хедер (site-wide)**: десктоп один в один по макету (кнопка чата, лого, навигация с мега-меню, поиск, чип персонажа, колокольчик, сообщения, аватар). Вместо HP/MP-баров из макета — уровень и монеты персонажа; клик по чипу открывает дропдаун смены персонажа (один клик, без перезагрузки).
- **Мобильный хедер — впервые на сайте** (бургер с бейджем, лого, чат, аватар; полоса персонажа; аккордеон-меню с поиском и кнопками Уведомления/Сообщения). Граница десктоп/мобайл — 1024px (планшеты получают мобильный хедер).
- **Зал славы**: баннер + вкладки + подиум топ-3 + список 4–6, реальные данные `GET /characters/home-leaderboards?limit=6` с аватарками и плейсхолдером.
- **Чат**: язычок сбоку удалён, открытие только из хедера; оверлей с закрытием по клику + кнопка «Закрыть»; на мобильном — панель на всю ширину.
- **Бэкенд** (3 строки, additive): `currency_balance` добавлен в `short_info` (character-service) и `CharacterShort` → `/users/me` (user-service). 12 новых pytest-тестов, оба сервиса зелёные (559+445 passed).
- **Ширина контейнера 1360px по всему сайту** через токен `max-w-container` (45 замен, задокументировано в DESIGN-SYSTEM.md).
- **T1/T3-миграции**: Button/Slider/CircleButton → .tsx+Tailwind, SCSS удалён; удалены мёртвые компоненты (HomePageButton, SmallHomePageButton, 3 слайдер-кнопки, 5 файлов Bestiary/Grimoire*).

### Что изменилось от первоначального плана
- Добавлена задача 8 (по решению пользователя): исправлены все 64 pre-existing TS-ошибки (техдолг, вскрывшийся после починки stale node_modules) — `tsc --noEmit` теперь 0 ошибок по проекту.
- Ревью №1 — FAIL (хедер не влезал на 768–1085px); исправлено сдвигом границы md→lg + скрытием поиска ниже xl. Ревью №2 — PASS.

### Оставшиеся риски / follow-up задачи
- Реальный счётчик непрочитанных для кнопки чата — отдельная будущая задача (пользователь решил: пока без бейджа).
- Монеты в хедере появятся после деплоя бэкенда (фронт корректно скрывает элемент при отсутствии поля — lockstep не нужен).
- Скролл-лок фона при открытом чате на мобильном отсутствует (как и раньше, косметика).
- Локальное окружение ревьюера: подсеяны тестовые персонажи в локальную MySQL, локальный `.env` требовал обновления по `.env.example` — это не изменения репозитория.
