# FEAT-152: Редизайн страницы локации по макету Claude Design

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-07-17 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-152-location-page-redesign.md` → `DONE-FEAT-152-location-page-redesign.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Редизайн страницы локации по макету из Claude Design.
Макет сохранён в репозитории: `features/design-refs/FEAT-152-location-redesign-LocationPage.dc.html`.
Нужно сделать очень похоже на макет, но с оговорками пользователя (см. Бизнес-правила).

### Бизнес-правила (требования пользователя)
1. **Максимальная близость к макету** по структуре и внешнему виду.
2. **НЕ делать сильное затемнение** картинки локации на общем фоне (в макете затемнение слишком сильное).
3. **Цвета фонов оставить текущие** (те, что сейчас используются на сайте) — в макете фоны слишком тёмные.
4. **Учесть состояния страницы:** когда персонаж в бою и когда не в бою (в текущей странице эти состояния есть — сохранить их поведение в новом дизайне).
5. Допустимы расхождения в количестве информации между макетом и текущей страницей — все расхождения (чего не хватает в макете / что лишнее) фиксировать и задавать вопросы пользователю через PM. **Не выкидывать и не добавлять функционал молча.**

### UX / Пользовательский сценарий
1. Игрок открывает страницу локации.
2. Видит новую страницу в дизайне по макету: изображение локации, информация, действия, посты и т.д.
3. Весь существующий функционал страницы продолжает работать (переходы, бои, сбор ресурсов, посты и др. — точный состав определит Analyst).
4. Если персонаж в бою — страница отражает это состояние, как сейчас (но в новом дизайне).

### Edge Cases
- Персонаж в бою / не в бою — разные состояния страницы.
- Мобильная адаптивность (360px+) — обязательна по правилам проекта.

### Вопросы к пользователю (если есть)

Ответы пользователя по Discrepancy List (2026-07-17):

- [x] **A1 Хлебные крошки (Страна/Регион/Район/Локация) + регион в шапке** → **ДА, добавить.** Требуется расширение locations-service (`/client/details` должен отдавать названия страны/региона/района).
- [x] **A2 Выдвижной чат с каналами (Общий/Локация/Отряд/Торговля)** → **НЕ НУЖЕН ВООБЩЕ.** Убрать из дизайна, отдельную фичу не планировать.
- [x] **A3 Кнопка «Ответить» на постах** → **НЕ делать сейчас.** Убрать из дизайна.
- [x] **A4 Баннер боя** → **ПОЛНАЯ версия из макета:** противник, «Раунд N · ваш ход», кнопка «Вернуться к бою». Требуется расширение battle-service (in-battle endpoint должен отдавать данные противника/раунда/чей ход).
- [x] **A5 Полоски HP у мобов** → **ДА, добавить.** Требуется доработка backend (отдавать текущее HP мобов для карточек на странице локации).
- [x] **A9 Шрифт Cormorant Garamond для заголовков** → **НЕТ.** Использовать текущий шрифт сайта.
- [x] **A10 Блокировка «Кто здесь» во время боя** → **Оставить доступным** (как сейчас): в бою блокируются только действия (атака/обмен и т.п.), список и профили доступны.
- [x] **B14 Фон страницы** → **Гибрид:** hero-шапка с картинкой локации как в макете + картинка локации остаётся фоном всей страницы с МЯГКИМ затемнением (как сейчас, не как в макете).
- [x] **B15 Сворачиваемые секции** → **Оставить сворачиваемые** (текущее поведение, но в новом стиле).

**Указание пользователя по завершению (2026-07-17):** после PASS ревью оформить все изменения **одним коммитом** и **запушить в `main`** (запустит CI/CD деплой на прод).

Решения PM по умолчанию (без вопросов, пользователь проинформирован):
- A6 Счётчики «N игроков здесь» / «N постов» в hero — включить (данные уже есть).
- A7 Переключатель «Симуляция боя» — убрать (демо-элемент прототипа).
- A8 Кнопка «В избранное» с подписью в верхней панели — как в макете.
- A11 Шапка сайта из макета — вне скоупа, остаётся глобальный header (FEAT-148).
- B1–B13, B16 — весь текущий функционал страницы сохраняется и размещается в новом макете (B12: все 4 типа меток; B11: реальные картинки предметов в луте вместо эмодзи; B16: состояния загрузки/ошибок сохраняются).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| frontend | redesign of LocationPage and its sub-components (layout/styles only; all logic must be preserved) | `services/frontend/app-chaldea/src/components/pages/LocationPage/*` (LocationPage.tsx, LocationHeader.tsx, PlayersSection.tsx, NeighborsSection.tsx, BattlesSection.tsx, PartiesOnLocation.tsx, GatheringSection/*, LootSection.tsx, PostCard.tsx, PostCreateForm.tsx, Pending*Panel.tsx), `components/LocationMobs.tsx`, `components/LocationMobPacks.tsx`, `components/CommonComponents/BattleLockBanner.tsx`, `components/CommonComponents/GatheringLockBanner.tsx`, `components/DungeonPage/DungeonEntrance.tsx`, `hooks/useBodyBackground.js` |
| locations-service | **only if** breadcrumb (country/region/district names) is approved by the user — extend `/client/details` response | `services/locations-service/app/main.py`, `app/schemas.py`, `app/crud.py` |
| battle-service | **only if** enriched battle banner (opponent name / round / "your turn") is approved — current `/battles/character/{id}/in-battle` returns only `{in_battle, battle_id}` | `services/battle-service/app/...` (read-only extension) |

The redesign is **frontend-only** unless the user approves mock elements that need new data (see Discrepancy List A).

### Current Page — Full Functionality Inventory (must NOT be silently dropped)

Route: `/location/:locationId` (App.tsx). Main data source: `GET /locations/{id}/client/details` (locations-service) → `LocationData` (`types.ts`): neighbors, players, npcs, posts, loot, gathering_nodes, marker_type, no_quick_move, is_favorited.

1. **Loading / error states** — spinner; error text + "Назад" button.
2. **Back button** (navigate(-1)).
3. **Battle lock state** — `useBattleLock` (GET `/battles/character/{id}/in-battle`) → `BattleLockBanner` ("Вы в бою!..."), and `actionsLocked` disables: neighbors links (opacity+pointer-events), post form, quick move, gathering, dungeon entrance, "Собрать группу", join-battle buttons.
4. **Gathering lock state** — `useGatheringLock` (Redux gatheringSlice, poll 10s) → `GatheringLockBanner` with MM:SS countdown + "Отменить" (cancel thunk, inline error). Gathering also sets `actionsLocked`.
5. **LocationHeader** — round location image (gold-outline), name, favorite star toggle (optimistic, POST/DELETE `/locations/{id}/favorite`), `recommended_level` badge, `marker_type` badge with 4 variants (safe/dangerous/dungeon/farm → Безопасная/Опасная/Подземелье/Фарм with distinct colors), description.
6. **Page background** — `useBodyBackground(location.image_url)` sets the location image as full body background (note: .js hook).
7. **PlayersSection** — two cards side by side:
   - Players: character title (rarity-colored) above avatar, avatar, name, LVL; per-player `PlayerActionsMenu` (attack → training duel / death duel with min level 30 + marker-type rules, `DuelInviteModal`, `DeathDuelConfirmModal`; propose trade → `TradeModal`) — only for other players.
   - NPCs: avatar with role icon overlay + role label badge; click opens `NpcProfileModal` (dialogue, shop, auction, quests modals, `TeleportMenu`) gated by FEAT-145 `npc_dialogue` posts (`talkableNpcIds`, toast error otherwise); "Напасть" button on NPC (`useNpcAttack`).
8. **NeighborsSection** — collapsible section, horizontal-scroll cards (image, name, lvl, energy cost), navigates to neighbor page.
9. **LocationMobs** — standalone mobs (GET `/characters/mobs/by_location`): tier badges (normal/elite/boss), alive/in_battle status, attack solo (`/battles/mob-attack`) or as party (`/battles/party/mob-attack`), gated by `combat` gate posts (`gatedMobIds`).
10. **LocationMobPacks** (FEAT-147) — mob packs with member lists, pack battle solo/party.
11. **BattlesSection** — collapsible; polls `/battles/by-location/{id}` every 10s; "+ Собрать группу" → `PartyLobbyModal`; battle cards: type badges (PvE / PvP / PvP Тренировка / PvP Смертельный), "На паузе" badge, teams with participants (NPC highlighted, levels), "Наблюдать" (spectate route), "Подать заявку" → `JoinRequestModal` (disabled when already requested or inBattle).
12. **PartiesOnLocation** (FEAT-144) — squads present at location (party-service `/party/...`), avatar, name, member chips with leader star.
13. **GatheringSection** (FEAT-128) — node cards (`GatheringNodeCard` + `ToolSelectionModal`), start gathering via Redux thunk, one-shot completion toasts (qty/xp/rank-up/tool broke/inventory full/cancelled/interrupted).
14. **DungeonEntrance** — dungeons at location (Redux dungeonSlice + WebSocket), create session, invite co-located players, party run, enter dungeon. Rendered only when `isCharacterHere && !actionsLocked`.
15. **PendingInvitationsPanel** — incoming/outgoing PvP invitations + pending trades (poll 7s), accept/decline/cancel, `TradeModal`.
16. **PendingPartyInvitesPanel** — incoming party invites (poll 8s), accept → `PartyLobbyModal`.
17. **LootSection** — item-cell grid with rarity frames, quantity badge, name, "Подобрать" (POST `/locations/{id}/loot/{lootId}/pickup`). Shown only when loot exists.
18. **Movement / travel** (when viewing a *neighbor* location while not being there):
    - Choice UI: "Написать пост для перемещения" (cost `energy_cost`) vs "Быстрое перемещение" (cost ×2, `window.confirm`, POST `/locations/{id}/quick_move`, hidden when `no_quick_move`).
    - **Travel cooldown timer** (`travel_cooldown_until` from getMe) — live countdown "Перемещение будет доступно через N мин M сек", blocks both options.
    - After move: Redux `setCharacterLocation` + `getMe()` refresh.
19. **Posts section** ("Посты"):
    - `PostCreateForm`: WYSIWYG editor (`WysiwygEditor`), min 300 chars, FEAT-145 v2 **intent gates** (combat 200/npc_dialogue 500/gathering 500/dungeon 500 chars per target; targets fetched from mobs+packs, npcs, gathering nodes, dungeons), char counter + XP preview (~len/100), spell-check (`useSpellCheck` + `SpellCheckPanel`), **staff NPC-mode posting** (POST `/locations/posts/as-npc`), collapsed→expanded editor, click-outside close.
    - Gate status: GET `/locations/action-gate/status` → which gated actions are currently allowed (drives `talkableNpcIds`, `gatedMobIds`).
    - `PostCard`: title (rarity color), avatar, name, level, timestamp, rich HTML content, gate badges, like/unlike (optimistic, POST/DELETE `/locations/posts/{id}/like`), **tag player** dropdown (POST `/locations/{id}/tag-player` → notification), **report** (POST `.../report`, 409 handling), **request deletion** (POST `.../request-deletion`), char length display.
    - Staff (`isStaff(userRole)`) can always post; in-battle/gathering hints shown instead of form.

### Existing Patterns

- All LocationPage components are **already TypeScript + Tailwind** (fully migrated) — no .jsx/SCSS migration needed within the page itself. Exceptions in the dependency chain: `hooks/useBodyBackground.js` (plain JS — migrate to .ts if touched).
- No `React.FC` (per rule 11); animations via `motion/react` (AnimatePresence, collapsibles); toasts via `react-hot-toast`; icons are inline SVG (+ `react-feather` in PostCreateForm).
- Design system (`index.css` @layer components): `gold-text`, `gold-outline`, `btn-blue`, `btn-line`, `rounded-card`, `item-cell`, `rarity-*`, `gold-scrollbar`, `modal-overlay/modal-content` etc. Tailwind tokens (`tailwind.config.js`): `gold` (#f0d95c, light #fff9b8, dark #bcab4c), `site.blue` #76a6bd, `site.red` #F37753, `site.bg` rgba(9,10,16,.62), `rarity.*`, `stat.*` (hp #E94545, mana #76A6BD, energy #88B332, stamina #FFF9B8), `max-w-container` 1360px.
- **Current background approach**: body carries `background-main.png` with a *soft* overlay `linear-gradient(180deg, rgba(5,6,10,.35), rgba(5,6,10,.55))` — comment in index.css explicitly says FEAT-151 chose it "intentionally softer than the mock's 0.55→0.96 — user asked for a non-aggressive darkening". Section backgrounds are translucent `bg-black/60` cards. **Same requirement applies here (business rules 2–3).**
- On LocationPage, `useBodyBackground` swaps the body background to the location image itself.

### Mock Inventory (`FEAT-152-location-redesign-LocationPage.dc.html`)

Page bg in the mock: `#05060a` + heavy gradient (0.42→0.97) over an image, `background-attachment:fixed`. Fonts: Montserrat + **Cormorant Garamond** (serif hero title — new to the site).

1. Desktop + mobile **site header** (chat button w/ badge, logo, mega-menu nav, search, character pill with HP/mana bars + current location, notifications, messages, avatar) — this is the global site header (FEAT-148/151), not location-page content.
2. **Top bar**: "Назад" button, **breadcrumb** "Фолгард / Северные земли / Чащоба / Тёмный лес" (country/region/district/location), battle-state **toggle button** (mock-only simulation control), **favorite button with text label** ("В избранное"/"В избранном").
3. **Battle lock banner** (shown when inBattle): red gradient, pulsing sword icon, "Вы в бою!" + explanation, **current-battle mini-card (opponent avatar+name, "Раунд 3 · ваш ход")**, **"Вернуться к бою" button**.
4. **Hero banner** (360px, 300px @≤1000px, auto @≤560px): full-width location art, **two overlay gradients: vertical `rgba(4,5,9,.12)→.9` + horizontal left `rgba(4,5,9,.55)→0`** (user says this darkening is too strong — tone down), top-left badges (marker "Опасная зона" + "25+ LVL"), serif 62px title, description, meta-row: pulsing green dot + "**N игроков сейчас здесь**", "**N постов**", "Регион **Северные земли**".
5. **3-column row** (1fr @≤1000px): 
   - "Кто здесь" — **tab switcher Игроки/НПС with count pills** (single card instead of the current two cards), avatar grid (88px circles), LVL / NPC role badge;
   - "Соседние локации" — count pill, 2-col grid of image cards (image 104px, name, "N+ LVL", energy cost);
   - "Противники" — 2-col mob cards: image, name, LVL, **HP bar**, "Напасть" button.
   - All three get `opacity:.45; pointer-events:none` when inBattle (mock locks "Кто здесь" too — current page does NOT lock players/NPC browsing).
6. **Body grid** (1fr 400px; 1fr @≤1000px): left — "Хроника локации" heading + post count; **post create**: collapsed state (avatar + "Опишите действия Кайдена в Тёмном лесу…" + "Написать пост" button), in-battle replacement card ("Вы в бою — написание постов… после завершения боя"), expanded: author header ("пишет из «Локация»"), **formatting toolbar (Б/К/П/цитата/список)**, contentEditable editor, **gate grid** (4 groups with char costs and target chips — matches FEAT-145 exactly), counter "X / Y символов" + "≈ N XP за пост" + **progress bar**, "Проверить правописание", Отмена / Опубликовать (disabled until min length).
7. **Posts feed**: cards with title (colored), avatar ring, name, LVL badge, relative time, rich HTML body (bold/blockquote/em styled), gate badges, like (heart, coral #F37753 when liked), **"Ответить" (reply) button**, "N симв." counter.
8. **Right sidebar**: "Добыча ресурсов" (icon, name, "Запас: X / Y", "N стамины", "Собрать" button; green accent #88B332), "На земле" loot (icon, name, "×N · выронил <имя>", "Подобрать").
9. **Chat drawer** (fixed left panel, overlay): channels Общий/Локация/Отряд/Торговля, message list, input — opened from header chat button.
10. Mock states: only two — `inBattle: true/false` (prop toggle). No gathering state, no "viewing a non-current location" state, no travel cooldown, no empty states.

### Discrepancy List (critical deliverable)

**A) In the MOCK but ABSENT on the current page** (needs new data/features, or must be dropped — user decides):

| # | Mock element | Status / cost |
|---|--------------|---------------|
| A1 | Breadcrumb "Страна / Регион / Район / Локация" in top bar + "Регион …" in hero meta | `/client/details` returns only `district_id`/`region_id` (numeric, nullable) — **no names**. Needs locations-service response extension (names + links) or extra frontend fetches. |
| A2 | Chat drawer with channels (Общий/Локация/Отряд/Торговля) + chat buttons in header | **Feature does not exist anywhere** in the codebase. Whole new feature (out of scope?) |
| A3 | "Ответить" (reply) button on posts | No reply/comment functionality exists for location posts (backend + frontend). |
| A4 | Battle banner enrichment: opponent avatar/name, "Раунд N · ваш ход", "Вернуться к бою" button | `useBattleLock` already returns `battle_id` → "Вернуться к бою" is cheap (route exists: `/location/{locId}/battle/{battleId}`). Opponent/round/turn info needs an extra battle-service call. |
| A5 | HP bars on mob cards | `MobInLocation` payload has no HP fields (only name/level/tier/avatar/status). Needs character-service payload extension, or drop. |
| A6 | "N игроков сейчас здесь" (pulsing) and "N постов" hero counters | Derivable from existing payload (`players.length`, `posts.length`) — **no backend needed**, safe to add. |
| A7 | Battle-state toggle button "Симуляция боя" in top bar | Mock-only dev control for previewing states — should not be shipped (confirm). |
| A8 | Favorite as labeled button in top bar ("В избранное") | Currently a star icon next to the name. Pure layout change, data exists. |
| A9 | Serif font (Cormorant Garamond) for hero title | Site uses Montserrat everywhere; adding a second font family is a design-system decision. |
| A10 | Mock locks the "Кто здесь" block while in battle (opacity .45, no clicks) | Current page allows browsing players/NPC lists in battle (only actions are locked). Adopting mock behavior would REDUCE functionality — needs a decision. |
| A11 | Site header inside the mock (mega menu, search, char pill, chat badge) | Global header already exists (FEAT-148); mock's version includes a chat button that doesn't exist. Header is presumably out of scope for this feature. |

**B) On the CURRENT page but ABSENT in the mock** (risk of silent drop — user decides where each lives in the new layout):

| # | Current functionality | Notes |
|---|----------------------|-------|
| B1 | **Movement choice UI**: "post to move" vs "Быстрое перемещение" (×2 cost, `no_quick_move` flag) + **travel cooldown countdown** | Core travel mechanic; mock has no "viewing a neighbor location" state at all. |
| B2 | **BattlesSection** — active battles list: type/pause badges, teams, "Наблюдать", "Подать заявку", "+ Собрать группу" (PartyLobbyModal) | Entire block missing from mock. |
| B3 | **Mob packs** (LocationMobPacks, FEAT-147) with pack members and pack battles | Mock has only single mobs. |
| B4 | **PartiesOnLocation** — squads present at the location | Missing from mock. |
| B5 | **DungeonEntrance** — dungeon sessions, invites, party runs | Missing from mock (mock references dungeons only as a post gate). |
| B6 | **PendingInvitationsPanel** (PvP invites in/out + trades) and **PendingPartyInvitesPanel** | Missing from mock. |
| B7 | **GatheringLockBanner** + gathering state (countdown, cancel; gathering also locks actions) | Mock knows only the battle lock. |
| B8 | **NPC interactions**: NpcProfileModal (dialogue/shop/auction/quests/teleport), "Напасть" on NPC, npc_dialogue gate enforcement with toast | Mock NPC tab shows plain cards with no actions. |
| B9 | **PlayerActionsMenu** on players (duels: training/death ≥30 lvl, trade) | Mock player cards have no actions. |
| B10 | **Post actions**: tag player (notify), report, request deletion; **staff NPC-mode posting**; character titles with rarity colors above avatars | Mock posts only have like + (new) reply; mock shows titles on posts but not in "Кто здесь". |
| B11 | **Loot metadata**: item images (S3) + rarity frames + item-type placeholder icons | Mock uses emoji icons and "выронил <имя>" (dropped-by info EXISTS in payload as `dropped_by_character_id` but the current UI doesn't show the name; mock shows a name — would need character-name resolution). |
| B12 | **Marker types**: 4 variants (safe/dangerous/dungeon/farm) | Mock shows only "Опасная зона". Trivial to map, but colors/labels for all 4 must be designed. |
| B13 | **Gathering details**: tool selection modal, per-node card states, completion toasts | Mock has simplified rows ("Запас", stamina, "Собрать"); stamina cost and bank exist in `GatheringNode` payload. |
| B14 | Location image as **page body background** (`useBodyBackground`) | Mock instead uses the image twice: as page bg (heavily darkened, fixed) AND as hero banner. Business rules 2–3: keep current bg colors, don't over-darken. Decision needed: keep body-bg swap, or hero-only. |
| B15 | Collapsible sections (neighbors, battles are collapse/expand) | Mock's blocks are always open with internal scroll (fixed 460px row height). Behavior choice needed. |
| B16 | Loading / error / empty states for every block | Mock contains none; must be preserved. |

**C) States comparison ("in battle" vs not):**

- **Current page**: `inBattle` (useBattleLock) shows BattleLockBanner (yellow/gold info style) and merges with `isGathering` into `actionsLocked`: neighbors disabled, post form replaced by "Вы в бою"/"Идёт добыча" text, quick move blocked, gathering/dungeon/battle-join disabled. Players/NPC/battles/loot/posts remain browsable. Additional distinct states the mock lacks: **gathering lock**, **travel cooldown**, **not-my-location viewing** (no post form unless neighbor/staff), **no-character user** and **staff** variants.
- **Mock**: single `inBattle` boolean → red banner (with battle info + return button), post form → "Вы в бою" card, and `opacity:.45 + pointer-events:none` on: neighbors, mobs, gathering, **and "Кто здесь"** (stricter than current). Favorite/back/posts stay active. Mock's banner style (red, pulsing) vs current gold banner — style upgrade acceptable, but content (round/opponent) is new data (A4).
- **Redesign must**: keep both lock sources (battle + gathering) feeding `actionsLocked`, keep gathering banner, keep travel cooldown UI, and not lock player/NPC browsing unless the user explicitly wants A10.

### Cross-Service Dependencies (used by this page)

- locations-service: `/locations/{id}/client/details`, `/favorite`, `/posts/*` (like/report/request-deletion/as-npc), `/move_and_post`, `/quick_move`, `/loot/{id}/pickup`, `/tag-player`, `/action-gate/status`, gathering start/cancel/active.
- battle-service: `/battles/character/{id}/in-battle`, `/battles/by-location/{id}`, `/battles/{id}/join-request(s)`, `/battles/mob-attack`, `/battles/party/mob-attack`, pvp invitations, trades (via `api/pvp.ts`, `api/trade.ts`), dungeons (`api/dungeons.ts`), battle lobby (`api/party.ts`).
- character-service: `/characters/mobs/by_location`, mob packs.
- party-service: `/party/*` (squads on location, invites).
- user-service: `getMe` (travel cooldown, character location), roles for `isStaff`.
- Redux slices involved: `userSlice`, `gatheringSlice`, `dungeonSlice`, `teleportSlice` (+ local component state for everything else).

### DB Changes

- None for a frontend-only redesign. If A1 (breadcrumb names) is approved: no schema change, only response enrichment via joins in locations-service. If A3 (replies) or A2 (chat) approved: significant new backend features (separate feature files recommended).

### Risks

- Risk: silently dropping any of B1–B16 during redesign → Mitigation: Architect must map every inventory item to a place in the new layout; Reviewer checks against this list.
- Risk: mock's heavy darkening (page bg 0.42→0.97, hero 0.12→0.9) contradicts business rules 2–3 → Mitigation: reuse FEAT-151 precedent (soft 0.35→0.55 overlay); Architect to specify exact toned-down gradients; keep current `bg-black/60`-style translucent cards and existing bg colors.
- Risk: fixed heights in mock (460px row) break with real data (0 players, 50 players) → Mitigation: define min/max heights + empty states.
- Risk: `background-attachment:fixed` is broken on iOS Safari → mock itself falls back to `scroll` at ≤760px; keep that.
- Risk: polling components (BattlesSection 10s, PendingInvitations 7s, PartyInvites 8s) — layout must not remount them unnecessarily → Mitigation: keep component boundaries, change only markup/classes.
- Risk: touching `useBodyBackground.js` triggers TS-migration rule (T3) → migrate to `.ts` in same PR if modified.

**Special task fulfilled:** Discrepancy List above (A/B/C). PM should turn A1–A11, B14, B15, and A10 into user questions.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Summary of design decisions

| Topic | Decision |
|-------|----------|
| A1 breadcrumb | Additive extension of locations-service `GET /locations/{id}/client/details`: add `country_id`, `country_name`, `region_name`, `district_name` (all optional). Backward-compatible. |
| A4 battle banner | **No battle-service changes.** Reuse existing `GET /battles/{battle_id}/preview` (JWT + participant-ownership, already returns opponent name/avatar, `turn_number`, whose-turn via `turn_order[].is_current`). Frontend: new `useBattlePreview` hook chained after `useBattleLock`. Justification below (3.2). |
| A5 mob HP | Extend character-service `GET /characters/mobs/by_location` (and pack members in the packs endpoint) with `current_hp` / `max_hp` joined from the shared `character_attributes` table. No battle-service/Redis coupling. Source-of-truth analysis below (3.3). |
| DB changes | **None.** No Alembic work needed anywhere (battle-service untouched; character-service/locations-service changes are response-enrichment only). |
| Background (B14) | Hybrid: hero banner + `useBodyBackground` kept (migrated `.js`→`.ts`), soft FEAT-151-style overlay composed inside the hook. Toned-down hero gradients specified in 3.5. |
| Omitted per user | A2 chat drawer, A3 reply button, A7 battle-sim toggle, A9 serif font, mock's site header (A11), mock's "Кто здесь" battle lock (A10 — stays browsable). |

### 3.1 API contract — locations-service (A1)

**`GET /locations/{location_id}/client/details`** — extended response (additive only; all other fields unchanged). Handler `get_location_client_details` (`app/main.py`), CRUD `get_client_location_details` (`app/crud.py`), schema `LocationClientDetails` (`app/schemas.py`).

New optional fields in `LocationClientDetails` (Pydantic v1):

```python
country_id: Optional[int] = None
country_name: Optional[str] = None
region_name: Optional[str] = None
district_name: Optional[str] = None
```

Response example (fragment):

```json
{
  "id": 72, "name": "Тёмный лес", "district_id": 5, "region_id": 2,
  "district_name": "Чащоба",
  "region_name": "Северные земли",
  "country_id": 1, "country_name": "Фолгард",
  "...": "all existing fields unchanged"
}
```

Resolution logic in `get_client_location_details` (async, aiomysql, separate-query style as the rest of the function):
- If `loc.district_id` is set: `select(District.name, District.region_id)` → then `select(Region.name, Region.country_id)` → then `select(Country.id, Country.name)`.
- Else if `loc.region_id` is set (standalone location): resolve Region → Country only; `district_name = None`.
- Else: all four new fields `None`.
- Nested districts (`parent_district_id`): breadcrumb shows only the **direct** district name — parent-district chain walking is deliberately out of scope (keeps the query cheap; matches mock's 4-segment breadcrumb).
- Frontend renders breadcrumb segments as **plain text** (no links) — there are no dedicated country/region/district pages in the app's client routes; do not invent routes.

Status codes unchanged (200 / 404). Missing hierarchy rows must not break the endpoint (fields stay `None`).

### 3.2 API contract — battle banner (A4): reuse `GET /battles/{battle_id}/preview`

Existing endpoint (`battle-service app/main.py`, model `BattlePreviewOut`), **no changes**. Relevant response shape consumed by the frontend:

```json
{
  "battle_id": 421, "battle_type": "pve", "turn_number": 3,
  "location_id": 72, "location_name": "Тёмный лес",
  "turn_order": [ { "participant_id": 1, "name": "Кайден", "is_current": true } ],
  "participants": [
    { "participant_id": 1, "character_id": 10, "name": "Кайден", "avatar": "...",
      "team": 1, "is_ally": true,  "is_alive": true, "hp": 62, "max_hp": 90,
      "mana": 40, "max_mana": 80 },
    { "participant_id": 2, "character_id": 999, "name": "Теневой волк", "avatar": "...",
      "team": 2, "is_ally": false, "is_alive": true, "hp": 38, "max_hp": 55,
      "mana": 0, "max_mana": 0 }
  ]
}
```

**Justification for reuse instead of extending `/battles/character/{id}/in-battle`:**
1. `/preview` already returns everything the mock banner needs (opponent name+avatar, round = `turn_number`, whose-turn = `turn_order[].is_current` matched to my `character_id`). Zero new backend surface, zero new tests to invent, zero risk of breaking `useBattleLock` consumers.
2. `/in-battle` is an unauthenticated hot-path check used across the site; enriching it would add a Redis state + snapshot load to every in-battle poll, and would expose battle internals on an auth-less endpoint. `/preview` is JWT-guarded with participant-ownership — the correct security posture for this data.
3. The banner is only shown to a user who **is** a participant, so the ownership check always passes.

**Frontend consumption (`useBattlePreview(battleId)` hook):**
- Fetch when `useBattleLock` reports `inBattle && battleId`; refresh every 15 s while the banner is mounted (consistent with existing 7–10 s polls on the page).
- Opponent card: first participant with `is_ally === false && is_alive`; if more alive enemies exist, append "и ещё N".
- Turn line: find `turn_order` entry with `is_current`, map its `participant_id` to `participants[].character_id`; if it equals my `character.id` → "Раунд {turn_number} · ваш ход", else "Раунд {turn_number} · ход противника".
- "Вернуться к бою" → `navigate('/location/{location_id}/battle/{battle_id}')` (route exists in App.tsx); use `location_id` from the preview payload (battle may be at another location than the page being viewed).
- **Fallback (mandatory):** on any error / 4xx / pending battle without Redis state, render the banner *without* the opponent/round block but *with* the "Вернуться к бою" button (battleId from `useBattleLock`). Never block the page on this call; show the generic banner while loading.

### 3.3 API contract — character-service mob HP (A5)

**Source-of-truth analysis:** a mob is a `characters` row whose live vitals are in the shared `character_attributes` table (`current_health`, `max_health`). battle-service writes every participant's final HP back to `character_attributes` on battle finish, and character-service's lazy-respawn (inside `get_mobs_at_location`) resets `current_health = max_health` when a dead mob respawns. Therefore `character_attributes` is authoritative for every mob **not currently fighting**: a surviving mob correctly keeps its damage between battles. For a mob with `status = "in_battle"` the truly-live HP is only in battle-service Redis; fetching it would require per-mob HTTP fan-out to battle-service on every location-page load. **Decision:** show the last persisted value for in-battle mobs (the card already shows the "В бою" status; approximate HP there is acceptable) — documented behavior, no cross-service calls.

**`GET /characters/mobs/by_location?location_id={id}`** — extend `MobInLocation` (`app/schemas.py`) additively:

```python
current_hp: Optional[int] = None
max_hp: Optional[int] = None
```

```json
[ { "active_mob_id": 7, "character_id": 999, "name": "Теневой волк", "level": 27,
    "tier": "normal", "avatar": "...", "status": "alive",
    "current_hp": 43, "max_hp": 55 } ]
```

Implementation in `crud.get_mobs_at_location` (sync SQLAlchemy): after the existing mob query (and after the lazy-respawn pass), one batched query `SELECT character_id, current_health, max_health FROM character_attributes WHERE character_id IN (:ids)` (raw `text()` — cross-table read of another service's table is an established pattern in this codebase, e.g. battle-service/photo-service). Missing attributes row → both fields `None`; frontend then hides the HP bar.

**Pack members:** apply the same two fields to the pack-member schema used by the mob-packs by-location endpoint (same crud module, same batched join) so pack cards can show member HP consistently.

### 3.4 Data flow (page load)

```
LocationPage mount
 ├─ GET /locations/{id}/client/details ──────────── locations-service (+ breadcrumb names)
 ├─ GET /characters/mobs/by_location?location_id ── character-service (+ current_hp/max_hp)
 ├─ GET /characters/mob-packs/by_location ───────── character-service (+ member HP)
 ├─ useBattleLock: GET /battles/character/{cid}/in-battle ── battle-service (unchanged)
 │    └─ if in_battle: useBattlePreview: GET /battles/{bid}/preview (JWT) ── battle-service (unchanged)
 ├─ useGatheringLock (Redux poll, unchanged)
 ├─ GET /locations/action-gate/status (unchanged)
 └─ polls unchanged: /battles/by-location 10s, pending invites 7s, party invites 8s
```

No new inter-service HTTP calls; no queue/DB changes.

### 3.5 Frontend architecture

#### Page layout & component tree (desktop; every mock block and every B1–B16 item mapped)

```
LocationPage.tsx  (layout re-composition; all data/logic hooks preserved)
├─ (global site header — untouched, A11)
├─ LocationTopBar.tsx (NEW): Back btn · breadcrumb (plain text: Country / Region /
│    District / <Location> gold) · favorite labeled button "В избранное/В избранном"
│    (A1, A8; reuses existing handleToggleFavorite optimistic logic)
├─ BattleLockBanner (CommonComponents, redesigned — mock red style, B-compat props):
│    "Вы в бою!" + opponent mini-card + "Раунд N · ваш ход/ход противника"
│    + "Вернуться к бою" (A4; fallback per 3.2). Shown when inBattle.
├─ GatheringLockBanner (restyled to match banner language, green/gold accent;
│    keeps MM:SS countdown + "Отменить" + inline error) (B7)
├─ PendingInvitationsPanel + PendingPartyInvitesPanel (B6) — moved up here
│    (time-sensitive alerts belong next to banners); logic/polling untouched
├─ LocationHeader.tsx (redesigned into HERO, keeps filename):
│    location image banner, toned overlays (below), badges (marker ×4 variants
│    reusing MARKER_LABELS/MARKER_COLORS + "N+ LVL"), title (site font, white),
│    description, meta row: pulsing "N игроков сейчас здесь" (players.length),
│    "N постов" (posts.length), "Регион {region_name}" (A6, B12)
├─ 3-column row (grid-cols-1 lg:grid-cols-[1.25fr_1fr_1fr]):
│  ├─ PlayersSection.tsx (redesigned → "Кто здесь" tabs Игроки/НПС with count
│  │    pills; avatar grid; titles w/ rarity colors kept; PlayerActionsMenu,
│  │    duel/trade modals, NpcProfileModal + all NPC modals, npc "Напасть",
│  │    talkableNpcIds gating kept). NOT dimmed in battle (A10). (B8, B9)
│  ├─ NeighborsSection.tsx (redesigned → 2-col image cards: img, name, N+ LVL,
│  │    energy cost; collapsible kept (B15); dimmed by actionsLocked as now)
│  └─ LocationMobs.tsx (redesigned → "Противники" 2-col cards: image, name, LVL,
│       tier badge, HP bar (A5, stat-hp color), "Напасть"; combat-gate +
│       solo/party attack logic kept; dimmed by actionsLocked)
├─ LocationMobPacks.tsx (full-width below the row, restyled cards + member HP;
│    pack solo/party battles kept) (B3)
├─ BattlesSection.tsx (full-width, collapsible kept (B15); restyle only —
│    badges, teams, Наблюдать, Подать заявку, "+ Собрать группу"/PartyLobbyModal;
│    10s poll component boundary unchanged) (B2)
├─ DungeonEntrance (full-width; rendered when isCharacterHere && !actionsLocked
│    as now; restyle only) (B5)
└─ Body grid (grid-cols-1 lg:grid-cols-[1fr_400px]):
   ├─ LEFT column:
   │  ├─ Movement / travel block (B1, kept inline): "Написать пост для
   │  │    перемещения" vs "Быстрое перемещение" (×2, no_quick_move, confirm)
   │  │    + travel-cooldown countdown; same conditions as today
   │  ├─ "Хроника локации" heading + post count divider
   │  ├─ PostCreateForm.tsx (restyled: collapsed avatar row → expanded form with
   │  │    toolbar, gate grid, counter + progress bar + XP preview, spell-check
   │  │    button/panel, staff NPC-mode kept; in-battle/gathering replacement
   │  │    cards kept) (B10 partially, B16)
   │  └─ PostCard.tsx list (restyled: title rarity color, avatar ring, LVL badge,
   │       time, rich HTML, gate badges, like; "…" kebab = existing actions menu
   │       (tag player / report / request deletion); "N симв." counter; NO reply
   │       button (A3)) (B10)
   └─ RIGHT sidebar (renders ABOVE posts on <lg via order utilities):
      ├─ GatheringSection (restyled rows: icon/name/Запас X из Y/stamina/Собрать;
      │    ToolSelectionModal + Redux thunks + completion toasts kept) (B13)
      ├─ LootSection.tsx ("На земле": real item images + rarity frames +
      │    quantity, "Подобрать"; dropped-by NAME not added — no name data in
      │    payload, out of scope) (B11)
      └─ PartiesOnLocation.tsx (restyled compact list; leader star kept) (B4)
```

Loading / error / empty states (B16): page-level spinner + error+"Назад" kept; every card section defines an empty-state line (e.g. "Здесь пока никого нет", "Нет соседних локаций", "Противников нет") — mock's fixed 460px heights are replaced with `lg:max-h-[460px] overflow-y-auto` (gold scrollbar) + natural height on mobile, so 0-item and 50-item cases both work.

#### Background & styling spec (B14, business rules 2–3)

- `useBodyBackground.js` → **`useBodyBackground.ts`** (typed `(imageUrl?: string | null) => void`). The hook composes the FEAT-151 soft overlay with the image: `linear-gradient(180deg, rgba(5,6,10,.35), rgba(5,6,10,.55)), url(...)` — keeps current soft darkening even though inline style replaces the CSS default.
- **Do NOT** apply the mock's page gradient (0.42→0.97) or `background-attachment:fixed`.
- Hero overlays, toned down from the mock: vertical `linear-gradient(180deg, rgba(5,6,10,.10) 0%, rgba(5,6,10,.05) 35%, rgba(5,6,10,.65) 100%)`; horizontal `linear-gradient(90deg, rgba(5,6,10,.30) 0%, transparent 55%)`. Text legibility comes from text-shadow, not overlay strength.
- Cards: current tokens — `bg-black/60 rounded-card backdrop-blur-sm`, `gold-text` headings, `border-white/10` / `border-gold-dark` accents, `btn-blue`/`btn-line`, `stat-bar`/`stat-bar-hp` for HP bars, `rarity-*` frames, `item-cell`, `gold-scrollbar-wide`. No new fonts (A9), Montserrat only.
- Mobile 360px+: single column, hero `min-h-[220px] h-auto`, who-grid 2 cols, gate grid 1 col, banner buttons full-width — per mock's breakpoints translated to Tailwind `sm:`/`lg:`.

#### TypeScript type changes

- `LocationPage/types.ts` → `LocationData`: add `country_id?: number | null; country_name?: string | null; region_name?: string | null; district_name?: string | null;`
- `api/mobs.ts` → `MobInLocation`: add `current_hp?: number | null; max_hp?: number | null;` (same for pack member type in `api/mobPacks.ts`).
- `api/battles.ts`: add `BattlePreview` interface (shape of 3.2) + `fetchBattlePreview(battleId)`.
- New hook `hooks/useBattlePreview.ts`: `{ preview: BattlePreview | null, loading: boolean, error: boolean }`, 15 s refresh, silent-fail per 3.2.
- No Redux changes (all new data is component-local).

### 3.6 Security considerations

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /locations/{id}/client/details` | none/optional user (status quo) | Additive public game data only (place names). `location_id` path-typed int; existing 404 kept. No new writes. |
| `GET /characters/mobs/by_location` (+packs) | none (status quo) | HP is non-sensitive game data. `location_id` query-typed int. Batched `IN (:ids)` query must be parameterized (no string interpolation). |
| `GET /battles/{battle_id}/preview` | JWT + participant ownership (existing) | Unchanged; correct guard for battle internals. Frontend must display errors per project rule (banner fallback + no silent swallow: fallback banner still informs the user they are in battle). |
| No new endpoints, no new rate limits (status quo Nginx). No secrets/env changes → no DevSecOps task. |

### 3.7 Risks

- Every B1–B16 item is mapped above — Reviewer must diff the rendered page against the 3.5 tree (silent-drop guard).
- Polling components (BattlesSection, pending panels) keep their component boundaries — restyle markup only, do not lift state, to avoid remount/poll churn.
- `BattleLockBanner` is a shared CommonComponents file — Frontend Dev must grep all usages and keep new props optional (non-Location pages render the simple variant).
- In-battle mob HP is "last persisted", not live — documented product behavior (3.3).
- iOS Safari: no `background-attachment:fixed` used at all.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **locations-service breadcrumb (A1).** Add `country_id`, `country_name`, `region_name`, `district_name` (all `Optional`, default `None`) to `LocationClientDetails`; resolve names in `get_client_location_details` per 3.1 (district→region→country chain; standalone-location fallback via `region_id`; all-None when hierarchy missing). Async separate-query style, Pydantic v1. | Backend Developer | DONE | `services/locations-service/app/schemas.py`, `app/crud.py` | — | `py_compile` passes; response includes correct names for (a) location with district, (b) standalone location (district_id NULL, region_id set), (c) location with neither (fields null); all existing fields unchanged; 404 behavior unchanged. |
| 2 | **character-service mob HP (A5).** Add `current_hp`/`max_hp` (`Optional[int]`, default `None`) to `MobInLocation` and to the pack-member schema; populate in `get_mobs_at_location` (and packs crud) via one batched parameterized `SELECT character_id, current_health, max_health FROM character_attributes WHERE character_id IN (...)` **after** the lazy-respawn pass. Missing attributes row → `None`. | Backend Developer | DONE | `services/character-service/app/schemas.py`, `app/crud.py` | — | `py_compile` passes; alive mob returns persisted HP; respawned mob returns full HP; mob without attributes row returns nulls (no 500); pack members carry the same fields; existing fields unchanged. |
| 3 | **QA: locations-service tests.** Extend `app/tests/test_client_details.py` (mock-CRUD + schema patterns per existing `_make_client_details` helper): new fields present & typed; nulls accepted (backward compat); name-resolution unit coverage for the three cases of task 1. | QA Test | DONE | `services/locations-service/app/tests/test_client_details.py` | 1 | pytest green for locations-service; the three hierarchy cases + backward-compat (payload without new keys validates) covered. |
| 4 | **QA: character-service mob HP tests.** Tests for `mobs/by_location` (+packs) per existing character-service test patterns: HP fields populated from `character_attributes`, nulls when row missing, respawn reset still returns `max_health`, schema backward compat. | QA Test | DONE | `services/character-service/app/tests/` (extend mob tests) | 2 | pytest green for character-service; cases above covered. |
| 5 | **Frontend foundation: layout skeleton, top bar, hero, banners, hooks (FE-A).** Migrate `useBodyBackground.js`→`.ts` with soft-gradient compose (3.5); add `BattlePreview` type + `fetchBattlePreview` (`api/battles.ts`) + `hooks/useBattlePreview.ts` (15 s refresh, silent-fail); extend `types.ts` (breadcrumb fields); new `LocationTopBar.tsx` (back, plain-text breadcrumb, labeled favorite btn A8); redesign `LocationHeader.tsx` into hero (toned overlays, marker ×4 + LVL badges, title, description, meta counters A6, `region_name`); redesign `BattleLockBanner` (full mock version + fallback per 3.2, optional props — grep & keep other usages working); restyle `GatheringLockBanner` (countdown + Отменить kept); re-compose `LocationPage.tsx` per 3.5 order (pending panels moved below banners). Russian UI text, mobile 360px+, Tailwind tokens only. | Frontend Developer | DONE | `hooks/useBodyBackground.ts` (delete `.js`), `hooks/useBattlePreview.ts`, `api/battles.ts`, `LocationPage/types.ts`, `LocationPage/LocationTopBar.tsx` (new), `LocationPage/LocationHeader.tsx`, `LocationPage/LocationPage.tsx`, `CommonComponents/BattleLockBanner.tsx`, `CommonComponents/GatheringLockBanner.tsx` | 1 (breadcrumb data; UI must tolerate null fields) | `npx tsc --noEmit` + `npm run build` pass; breadcrumb shows names (hides null segments); hero matches mock with toned overlays; body bg = location image with soft overlay; in-battle banner shows opponent + "Раунд N · ваш ход/ход противника" + working "Вернуться к бою", degrades gracefully on preview error; gathering banner functional; no `React.FC`; responsive at 360px. |
| 6 | **Frontend 3-column row + full-width sections (FE-B).** Redesign `PlayersSection` (tabs Игроки/НПС + count pills; all player/NPC actions & modals kept; NOT dimmed in battle per A10), `NeighborsSection` (2-col image cards, collapsible kept, actionsLocked dim kept), `LocationMobs` (2-col cards + HP bars from `current_hp/max_hp`, hide bar when null; tier badges, gate + solo/party attack kept), `LocationMobPacks` (restyle + member HP), `BattlesSection` (restyle, collapsible + 10 s poll boundary kept), `DungeonEntrance` (restyle, render conditions kept), pending panels restyle. Extend `api/mobs.ts`/`api/mobPacks.ts` types. | Frontend Developer | DONE | `LocationPage/PlayersSection.tsx`, `NeighborsSection.tsx`, `components/LocationMobs.tsx`, `components/LocationMobPacks.tsx`, `LocationPage/BattlesSection.tsx`, `DungeonPage/DungeonEntrance.tsx`, `LocationPage/PendingInvitationsPanel.tsx`, `PendingPartyInvitesPanel.tsx`, `api/mobs.ts`, `api/mobPacks.ts` | 2, 5 | tsc + build pass; tabs switch with correct counts; every pre-existing action (duels, trade, NPC modals, attack, pack battles, spectate/join, dungeon, invites) works; HP bars render (and hide on null); empty states present; sections scroll internally at `lg:max-h-[460px]`; responsive 360px+. |
| 7 | **Frontend posts column + sidebar + final pass (FE-C).** Restyle body grid per 3.5: movement/travel block (choice UI, ×2 cost, `no_quick_move`, cooldown countdown — logic untouched), "Хроника локации" head, `PostCreateForm` (collapsed→expanded, toolbar, gate grid, counter+progress+XP, spell-check, staff NPC-mode, in-battle/gathering replacement cards), `PostCard` (kebab menu with tag/report/request-deletion, like, gate badges, NO reply), sidebar `GatheringSection` rows + `LootSection` (real images/rarity, no dropped-by name) + `PartiesOnLocation`; sidebar above posts on `<lg`. Full-page responsive + states sweep (loading/error/empty, in-battle, gathering, neighbor-view, staff, no-character). | Frontend Developer | DONE | `LocationPage/LocationPage.tsx`, `PostCreateForm.tsx`, `PostCard.tsx`, `LootSection.tsx`, `PartiesOnLocation.tsx`, `GatheringSection/*` | 6 | tsc + build pass; movement + cooldown works from a neighbor location; post create/publish with gates & XP preview works; all post actions work; gathering start→toasts and loot pickup work; every B1–B16 item visible/functional per 3.5 map; 360px clean. |
| 8 | **Review.** Re-run `py_compile`/pytest/tsc/build; live-verify via chrome-devtools (login per reference creds): both battle states, gathering state, neighbor-view + cooldown, breadcrumb, mob HP bars, banner with opponent/round/return-button, mobile viewport; diff rendered page against section 3.5 component map (B1–B16 silent-drop check); cross-service-validator on contracts 3.1–3.3; security checklist 3.6; zero console errors. | Reviewer | DONE | — | 3, 4, 7 | PASS only with all automated checks green + live verification clean + full B1–B16 checklist confirmed. |

**Parallelism:** Tasks 1 ∥ 2 (different services). Task 3 after 1 ∥ task 4 after 2. Task 5 can start once 1 lands (and in practice in parallel with 2–4). Tasks 5→6→7 are sequential (same files, one Frontend Developer). Task 8 last.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-07-17
**Result:** PASS

#### Automated Check Results
- [x] `py_compile` (locations-service crud/schemas, character-service crud/schemas) — PASS
- [x] `pytest` locations-service (in-container, `--asyncio-mode=auto`) — PASS: **605 passed**
- [x] `pytest` character-service (in-container, `--asyncio-mode=auto`) — PASS: **583 passed, 1 skipped**
- [x] `npx tsc --noEmit` — PASS
- [x] `npm run build` — PASS (only pre-existing SCSS deprecation + chunk-size warnings)
- [x] `docker compose config` — PASS (pre-existing env-var warnings only)
- [x] Live verification (MCP chrome-devtools + curl) — PASS (details below)

#### Contract verification (§3.1–3.3, live)
- `GET /locations/1/client/details` → `country_id: 2, country_name: "Союзная империя", region_name: "Уэймок", district_name: "Оливковые луга"` — all 4 new fields present, existing fields unchanged. Schema/crud diff reviewed: additive `Optional` fields, Pydantic v1, async separate-query style, all-None fallback branches present, 404 unchanged.
- `GET /characters/mobs/by_location?location_id=1` → mob with attributes row: `current_hp: 43, max_hp: 55`; mob without attributes row: both `null` (no 500). Batched query is fully parameterized (named binds, no value interpolation). Pack-member schema carries the same fields (verified in schemas + 24 QA tests).
- `GET /battles/{id}/preview` — reused unchanged (JWT + participant ownership); frontend `useBattlePreview` polls ~15 s, silent-fail fallback confirmed live (see below).

#### Live Verification Results (page `/location/1`, admin test account, character Артория)
- Console errors: **NONE** (only pre-existing React Router future-flag warnings and a pre-existing form-field a11y notice from the chat widget).
- Failed network requests: **NONE** (all XHR/fetch 200; the only non-200s observed were intentional negative tests / pre-existing data issues, see notes).
- **Top bar (A1, A8):** breadcrumb «Союзная империя / Уэймок / Оливковые луга / Врата крепости» (plain text, gold current segment); «Назад»; labeled favorite button — toggled «В избранное» → «В избранном» (POST 200), back (DELETE 200), optimistic.
- **Hero (A6, B12, B14):** location image hero with SOFT overlays; body background = location image composed with FEAT-151 soft gradient `rgba(5,6,10,.35)→.55` (verified via computed style, no `background-attachment:fixed`); marker badge «БЕЗОПАСНАЯ», «10+ LVL», title, description, «7 игроков сейчас здесь» (pulsing), «3 постов», «Регион Уэймок».
- **«Кто здесь» (B8, B9, A10):** tabs Игроки 7 / НПС 0 with count pills; НПС empty state «НПС отсутствуют на этой локации»; ДЕЙСТВИЕ menus present on other players; **stays browsable and enabled during battle (A10)** while neighbors/mobs sections dim (`pointer-events-none`).
- **Neighbors (B15):** collapsible; empty state «Нет соседних локаций»; with seeded neighbor — image card «Горнизон, 10+ LVL, 3 энергии», click navigates.
- **Mobs (A5):** 2-col cards, tier badge «Обычный», HP bar rendered for mob with data (43/55, `stat-bar-hp`), hidden for mob with null HP; combat gate «Нужен боевой пост» → after publishing a combat post targeting the wolf, «Напасть» appeared only for the gated target.
- **Battle state (A4) — verified LIVE, full flow:** published 300+ char combat post via the redesigned editor (gate chip, counter 395/300, «≈ 4 XP за пост», progress bar), attacked the mob → battle created («Бой начинается!», navigate to `/location/1/battle/2`). Back on the location page: **full red banner** — «Вы в бою!», opponent mini-card «Теневой волк (тест)», «Раунд 0 · ваш ход», «Вернуться к бою» → navigates to `/location/1/battle/2`. Post form replaced by «Вы в бою…» card; neighbors/mobs dimmed. **Graceful fallback also verified live:** with a battle whose Redis state was broken, `GET /battles/1/preview` returned 404 and the banner rendered without the opponent/round block but with a working «Вернуться к бою» — exactly per §3.2. Battles cleaned up via admin force-finish.
- **Movement/neighbor view (B1):** from location 2 (character at 1): choice cards «пост для перемещения — 3 выносливости» vs «Быстрое перемещение — 6 выносливости / Без написания поста» render; travel-cooldown UI code path intact but could not display live due to a **pre-existing** user-service bug (see Pre-existing issues).
- **Chronicle (B10, B16):** post created E2E; feed shows avatar ring, name, LVL badge, relative time, RP body, gate badge «Нападение на мобов», like, tag-player, kebab (Пожаловаться / Запросить удаление), «N симв.»; NO reply button (A3); staff NPC-mode toggle «Написать от НПС» present; empty state «Здесь пока нет постов…»; error path on failed submit shows toast with backend detail (code identical to pre-redesign, verified toast display on 400/500).
- **Sidebar (B4, B11, B13):** «На земле» — real item image, rarity frame, ×2 quantity, «Подобрать» → «Предмет подобран», section hides when empty; GatheringSection/PartiesOnLocation composed per §3.5 (sidebar `order-1` above posts on <lg — verified programmatically at 360px). Gathering/parties/dungeon/pack states could not be exercised live (no gathering nodes, parties, dungeons, or mob packs exist in the dev DB); verified via code review + type-check + the 24 pack-HP backend tests.
- **BattlesSection (B2):** collapsible, «+ Собрать группу» button, empty state «Нет активных боёв», 10 s poll boundary preserved (poll requests observed at steady cadence, no remounts).
- **Mobile 360×780 (mobile+touch emulation):** zero horizontal overflow (scrollWidth == clientWidth == 360, no offending elements), columns stack, sidebar above posts, mobs 2-col with HP bars, touch-sized buttons.
- **Mock comparison (side-by-side, file:// render):** layout structure, banner composition, «Кто здесь» tabs card, neighbors/mobs cards, chronicle composer with gate grid/counter/progress, sidebar «Добыча ресурсов»/«На земле» all match; approved deviations honored — soft darkening (rules 2–3), current site colors/fonts (A9), no chat drawer (A2), no reply (A3), no sim toggle (A7), global header untouched (A11), collapsible sections kept (B15).

#### Silent-drop checklist
- A1 ✔ A2 (absent ✔) A3 (absent ✔) A4 ✔ A5 ✔ A6 ✔ A7 (absent ✔) A8 ✔ A9 (site font ✔) A10 (browsable ✔) A11 (global header ✔)
- B1 ✔ B2 ✔ B3 ✔ (code+tests) B4 ✔ (code) B5 ✔ (code, render condition `isCharacterHere && !actionsLocked` preserved) B6 ✔ (panels mounted, polls 200) B7 ✔ (code; banner restyled, countdown+Отменить preserved) B8 ✔ B9 ✔ B10 ✔ B11 ✔ B12 ✔ (4 variants in MARKER maps) B13 ✔ (code) B14 ✔ B15 ✔ B16 ✔

#### Code standards
- No `React.FC`; no new `.jsx`; `useBodyBackground.js` → `.ts` migrated (T3); no new SCSS/CSS (T1); Tailwind tokens + design-system classes throughout; Russian UI text everywhere; errors surfaced via toasts; no TODO/FIXME added; Pydantic v1 syntax; sync/async styles respected per service; parameterized SQL; QA coverage present (tasks 3–4 DONE, 33+24 tests re-run green as part of full suites).

#### Pre-existing issues noted (NOT caused by FEAT-152, non-blocking)
1. **HIGH, added to `docs/ISSUES.md`:** `/users/me` never returns `travel_cooldown_until` — `CharacterShort` (`services/user-service/schemas.py`) lacks the field, Pydantic strips it although `main.py:154` supplies it. The travel-cooldown timer UI (kept intact by this feature) can never display. Predates FEAT-152 (frontend code identical at HEAD).
2. Dev-environment only: test character «Артория» (id 2) had no `character_attributes` row → `move_and_post` returned 404 «Character attributes not found». Fixed as dev data during review (row added) to enable E2E verification.
3. Dev-environment only: after the `.js`→`.ts` hook rename, the running Vite dev server kept a stale module-graph reference to `useBodyBackground.js` (404, blank page) until the frontend container was restarted. No code issue (imports are extensionless; tsc+build clean); prod builds are unaffected. Deploy note: dev machines may need a frontend restart after pulling.
4. Pre-existing bad dev data: some character avatars are literal `string`/`broken-url` values (relative-URL images in «Кто здесь»).

All checks passed. Changes are ready for completion.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-07-17 — PM: фича создана, макет LocationPage.dc.html импортирован из Claude Design в features/design-refs/, запускаю Codebase Analyst
[LOG] 2026-07-17 — PM: получены ответы пользователя по всем расхождениям (см. секцию 1), запускаю Architect
[LOG] 2026-07-17 15:57 — Analyst: анализ завершён. Страница локации полностью на TS+Tailwind (миграция не нужна). Редизайн в основном frontend-only. Составлен Discrepancy List: 11 пунктов «есть в макете, нет на странице» (A1–A11: хлебные крошки, чат, ответы на посты, HP мобов и др.), 16 пунктов «есть на странице, нет в макете» (B1–B16: перемещение/кулдаун, бои на локации, стаи мобов, отряды, данжи, приглашения, добыча и др.), сравнение состояний «в бою». Вопросы для пользователя переданы PM в секции 2.
[LOG] 2026-07-17 19:16 — Architect: проектирование завершено. 8 задач (2 backend ∥, 2 QA, 3 frontend последовательно, 1 review). Ключевые решения: A4 — без изменений battle-service, баннер боя использует существующий GET /battles/{id}/preview (уже отдаёт противника, номер раунда и чей ход); A5 — HP мобов из общей таблицы character_attributes (join в mobs/by_location + участники стай), для мобов «в бою» показывается последнее сохранённое HP; A1 — аддитивные поля country/region/district_name в /client/details. Изменений схемы БД нет, Alembic не требуется. Все пункты B1–B16 размечены по новому макету в секции 3.5.
[LOG] 2026-07-17 19:45 — Backend Dev: задача #2 завершена. В character-service добавлены поля current_hp/max_hp в MobInLocation и PackMemberInLocation (schemas.py); в crud.py добавлен хелпер _get_mob_hp_map (один батчевый параметризованный SELECT из общей таблицы character_attributes), подключён в get_mobs_at_location (после lazy-respawn) и get_packs_at_location (для агрегированных групп участников стаи HP суммируется по живым мобам группы; при отсутствии строк атрибутов — null). Проверено: py_compile OK, 71 существующий mob-тест зелёный в контейнере, ad-hoc проверка (HP заполняется / null без строки атрибутов / сумма по стае / обратная совместимость схем) — 4/4 passed.
[LOG] 2026-07-17 20:05 — Frontend Dev: начал задачу #5 (FE-A: хуки, топбар, hero, баннеры, каркас страницы)
[LOG] 2026-07-17 20:35 — Frontend Dev: задача #5 завершена. useBodyBackground мигрирован .js→.ts (мягкий градиент FEAT-151 компонуется с картинкой локации); новый хук useBattlePreview (15 c refresh, тихий fallback) — тип BattlePreview и fetchBattlePreview уже существовали в api/battles.ts с FEAT-151, повторно использованы без изменений; types.ts расширен полями хлебных крошек; новый LocationTopBar (Назад + текстовые крошки + кнопка «В избранное/В избранном»); LocationHeader переделан в hero-баннер (смягчённые оверлеи, 4 варианта меток, LVL-бейдж, счётчики игроков/постов, регион); BattleLockBanner — полная версия из макета (противник, «Раунд N · ваш ход/ход противника», «Вернуться к бою», graceful fallback; message-only вариант для InventoryTab сохранён); GatheringLockBanner рестайлинг (таймер + «Отменить» сохранены); LocationPage перекомпонован по 3.5 (баннеры → pending-панели → hero → 3 колонки → полноширинные секции → сетка постов+сайдбар, сайдбар выше постов на мобильных). Вся логика (избранное, кулдаун перемещения, quick move, гейты, лайки и пр.) сохранена. Проверено: npx tsc --noEmit OK, npm run build OK.
[LOG] 2026-07-17 19:22 — Backend Dev: задача #1 завершена. В /client/details добавлены поля country_id/country_name/region_name/district_name (schemas.py, crud.py locations-service). py_compile OK; live-проверка в dev-контейнере: все 3 случая иерархии (район / standalone / без иерархии) и 404 работают корректно. Внимание QA (задача #3): test_client_details.py::test_full_response_structure сейчас падает на строгом сравнении набора ключей — нужно добавить 4 новых поля в expected_keys.
[LOG] 2026-07-17 19:26 — QA: задача #3 завершена. Расширен test_client_details.py: +15 новых тестов хлебных крошек (схема: поля/дефолты/обратная совместимость; эндпоинт: полная цепочка район→регион→страна, standalone-локация, без иерархии, неизменность старых полей; unit-тесты резолвинга имён в crud с моками сессии, включая отсутствующие строки District/Country). Исправлен test_full_response_structure (добавлены 4 новых ключа в expected_keys). Прогон в контейнере как в CI (--asyncio-mode=auto): файл 33/33, весь сьют locations-service 605 passed.
[LOG] 2026-07-17 19:28 — QA: задача #4 завершена. Создан tests/test_mob_hp.py в character-service: 24 постоянных теста HP мобов (FEAT-152). Покрыто: HP из character_attributes в mobs/by_location (crud + эндпоинт, батчевый маппинг по нескольким мобам, «в бою» = последнее сохранённое HP); моб без строки атрибутов → current_hp/max_hp = null без 500; отсутствие самой таблицы (SQLite fallback _get_mob_hp_map → {}); респавн возвращает полное HP (чтение после lazy-respawn); суммирование HP по живым участникам группы стаи (20/30 + 10/30 → 30/60, мёртвые исключаются, частичные строки, мульти-шаблонные стаи, эндпоинт); обратная совместимость схем MobInLocation/PackMemberInLocation и все старые поля ответов; unit-тесты _get_mob_hp_map. Таблица character_attributes создаётся raw DDL в фикстуре (паттерн test_add_rewards.py). Прогон в контейнере как в CI (--asyncio-mode=auto): файл 24/24, весь сьют character-service 583 passed, 1 skipped.
[LOG] 2026-07-17 20:40 — Frontend Dev: начал задачу #6 (FE-B: 3-колоночный ряд + полноширинные секции)
[LOG] 2026-07-17 21:20 — Frontend Dev: начал задачу #7 (FE-C: колонка постов, сайдбар, финальный проход по адаптивности и состояниям)
[LOG] 2026-07-17 21:55 — Frontend Dev: задача #7 завершена. PostCard переделан под язык макета: шапка (аватар с золотой рамкой, титул с цветом редкости, имя, LVL-бейдж, относительное время, бейдж «НПС» для системных постов), kebab-меню «жалоба/запрос удаления» перенесено в шапку (открывается вниз), «Напасть»/PlayerActionsMenu рядом; RP-оформление тела поста (цитаты с золотой рамкой, курсив/жирный тонированы), гейт-бейджи раскрашены по типу действия; футер: лайк + тег игрока + счётчик «N симв.» (post.length); кнопки «Ответить» нет (A3). PostCreateForm: карточка bg-site-bg, свёрнутое состояние «Опишите действия {персонаж} в «{локация}»…» с аватаром и кнопкой «Написать пост», развёрнутое — заголовок автора «пишет из «{локация}»» (в НПС-режиме показывает выбранного НПС), гейт-сетка 2 колонки с глифами и цветами по типу, счётчик + прогресс-бар + «≈ N XP за пост», проверка правописания/Отмена/Опубликовать по макету; вся логика (гейты, мин. длина, НПС-режим, спеллчек, click-outside) не тронута. Блок перемещения: карточки выбора «пост/быстрое ×2» и таймер кулдауна рестайлены (жёлтые Tailwind-цвета заменены на токены золота), логика не тронута; заглушки «Вы в бою»/«Идёт добыча» — карточки с иконкой по макету. Сайдбар: GatheringSection → «Добыча ресурсов» (зелёный акцент, компактные ряды «Запас X / Y · N стамины · время», зелёная кнопка «Собрать», все статусы/таймеры/ToolSelectionModal/тосты сохранены); LootSection → «На земле» (ряды с реальными картинками в rarity-рамках, кол-во, имя цветом редкости, «Подобрать» золотым контуром); PartiesOnLocation → карточка с шапкой и счётчиком, чипы участников со звездой лидера. Состояния: ошибка страницы — карточка с иконкой и «Назад», пустая хроника — карточка «Здесь пока нет постов…». Адаптивность 360px+ проверена по всей странице (колонки складываются, сайдбар выше постов, кнопки full-width/иконки на мобильных). Проверено: npx tsc --noEmit OK, npm run build OK.
[LOG] 2026-07-17 22:10 — Reviewer: начал проверку (статус фичи переведён в REVIEW)
[LOG] 2026-07-17 23:40 — Reviewer: проверка завершена, результат PASS. Автопроверки: py_compile OK; pytest в контейнерах — locations-service 605 passed, character-service 583 passed/1 skipped; tsc и npm run build OK; docker compose config OK. Live-проверка через chrome-devtools (админ-аккаунт, персонаж Артория, /location/1): 0 ошибок консоли, 0 упавших запросов; крошки с реальными именами (Союзная империя/Уэймок/Оливковые луга), hero с мягким затемнением + фон страницы = картинка локации с градиентом FEAT-151, кнопка избранного (POST/DELETE 200), табы Кто здесь + пустые состояния, HP-бары мобов (данные — бар есть, null — скрыт), соседи, лут «Подобрать» E2E, пост с боевым гейтом опубликован E2E (счётчик/XP/прогресс). Состояние боя проверено ЖИВЬЁМ: атака моба → полный баннер (противник «Теневой волк», «Раунд 0 · ваш ход», «Вернуться к бою» ведёт в бой), форма постов заблокирована, «Кто здесь» доступен (A10); graceful fallback тоже проверен живьём (preview 404 → баннер без блока противника, кнопка работает). Добыча/отряды/данжи/стаи — проверены по коду и тестам (в dev-БД нет данных). Мобильная 360px — без переполнений, сайдбар выше постов. Сравнение с макетом — соответствует при одобренных отклонениях. Тестовые данные (мобы, сосед, лут, картинка локации) удалены после проверки.
[LOG] 2026-07-17 23:40 — Reviewer: обнаружен pre-existing баг (не связан с FEAT-152), добавлен в ISSUES.md (HIGH): /users/me не отдаёт travel_cooldown_until (CharacterShort в user-service срезает поле) — таймер кулдауна перемещения никогда не отображается. Также в dev-БД у персонажа Артория отсутствовала строка character_attributes (добавлена для проверки), а Vite dev-серверу после переименования useBodyBackground.js→.ts потребовался перезапуск контейнера frontend (устаревший кэш модулей; prod-сборка не затронута).
[LOG] 2026-07-17 21:10 — Frontend Dev: задача #6 завершена. PlayersSection переделан в единую карточку «Кто здесь» с табами Игроки/НПС и счётчиками (chip-outline), внутренний скролл; вся логика сохранена (титулы с цветами редкости, PlayerActionsMenu/дуэли/обмен, гейт npc_dialogue с тостом, «Напасть» на НПС, бейджи ролей); не затемняется в бою (A10). NeighborsSection — карточки с изображением в 2 колонки (картинка/имя/N+ LVL/цена энергии), сворачивание сохранено, по умолчанию раскрыт. LocationMobs — «Противники»: карточки 2 в ряд с картинкой, LVL, бейджем тира, HP-баром из current_hp/max_hp (null → бар скрыт, tooltip с числами), бейджем «В бою» (HP — последнее сохранённое, ожидаемо), кнопкой «Напасть» (красная, как в макете), гейт «Нужен боевой пост» и выбор соло/группой сохранены; секция затемняется при actionsLocked (однострочная правка обёртки в LocationPage по §3.5). LocationMobPacks — карточки стай с группами участников и СУММИРОВАННЫМ HP по живым мобам группы (например 30/60; null → бар скрыт). BattlesSection — рестайл шапки и карточек боёв, вся логика (poll 10 c, бейджи типов/паузы, команды, «Наблюдать», «Подать заявку», «Собрать группу»→PartyLobbyModal) не тронута. DungeonEntrance — рестайл секции/карточек, вся логика сессий/приглашений/отряда сохранена. Pending-панели — лёгкий рестайл под язык карточек. Типы current_hp/max_hp добавлены в api/mobs.ts (MobInLocation) и api/mobPacks.ts (PackMemberInLocation). Пустые состояния: «Здесь пока никого нет», «Нет соседних локаций», «Противников нет» (секции соседей/противников теперь показываются с пустым состоянием вместо скрытия — по §3.5). Проверено: npx tsc --noEmit OK, npm run build OK.
[LOG] 2026-07-17 — PM: ревью PASS, фича закрыта, оформляю единый коммит и пуш в main
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Полный редизайн страницы локации по макету Claude Design (`features/design-refs/FEAT-152-location-redesign-LocationPage.dc.html`) с учётом требований пользователя: мягкое затемнение, текущие цвета фонов и шрифт сайта, гибридный фон (hero-шапка + картинка локации фоном страницы).
- **locations-service:** `/locations/{id}/client/details` дополнен полями `country_id`, `country_name`, `region_name`, `district_name` (хлебные крошки). Обратно совместимо, без изменений схемы БД.
- **character-service:** `/characters/mobs/by_location` и стаи дополнены `current_hp`/`max_hp` (для стай — сумма по живым участникам группы). Обратно совместимо.
- **frontend:** новая компоновка LocationPage — верхняя панель (назад/крошки/избранное), полный баннер боя (противник, «Раунд N · ваш ход», «Вернуться к бою» через существующий `/battles/{id}/preview`), рестайл баннера добычи, hero с мягкими градиентами, 3 колонки («Кто здесь» с вкладками / соседи / противники с HP-полосками), стаи, бои, подземелья, колонка постов (перемещение + кулдаун, форма, карточки) и сайдбар (добыча, лут, отряды). `useBodyBackground` мигрирован .js→.ts. Весь функционал B1–B16 сохранён; A2/A3/A7/A9/A11 исключены по решению пользователя.
- **QA:** +15 тестов locations-service (605 всего), +24 теста character-service (583 всего) — все проходят.
- **Ревью:** PASS с первой итерации; живая проверка в браузере (консоль чистая, оба состояния баннера боя, мобильная вёрстка 360px, сверка с макетом).

### Что изменилось от первоначального плана
- A4 (баннер боя): battle-service не менялся — данные противника/раунда уже отдаёт защищённый `/battles/{battle_id}/preview` (решение Architect, дешевле и безопаснее).
- A5: для моба в бою показывается последнее сохранённое HP + бейдж «В бою» (live-HP из Redis потребовал бы HTTP fan-out — не оправдано).

### Оставшиеся риски / follow-up задачи
- **Баг (существовал до фичи, добавлен в `docs/ISSUES.md`, HIGH):** `/users/me` не отдаёт `travel_cooldown_until` (срезается схемой `CharacterShort`) — таймер кулдауна перемещения не может отобразиться. Отдельная задача.
- После pull на dev-машинах из-за переименования `useBodyBackground.js→.ts` может понадобиться `docker restart frontend` (stale-ссылка Vite dev-сервера). Prod-сборки не затронуты.
- Стаи/добыча/отряды/подземелья проверены кодом и тестами (в dev не было данных для live-проверки).
