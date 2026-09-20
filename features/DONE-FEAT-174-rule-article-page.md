# FEAT-174: Правило открывается отдельной страницей, а не модалкой

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-20 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-174-slug.md` → `DONE-FEAT-174-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас текст правила показывается модалкой поверх экрана (`RuleOverlay`). Пользователю это
не нравится. Правило должно открываться **отдельной страницей**, где текст занимает всю
страницу, на подложке **в стиле профиля персонажа: тёмный фон с золотой обводкой**.

Вторая половина задачи: **оформление текста правил должно быть на уровне ролевых постов
персонажей**.

### Бизнес-правила
- Клик по карточке правила ведёт на отдельную страницу, а не открывает модалку.
- Подложка страницы — тёмный фон с золотой обводкой, как в профиле персонажа. Конкретные
  классы берём существующие из дизайн-системы, ничего не изобретаем.
- Текст правила занимает страницу целиком.
- Возможности оформления в правилах = возможностям оформления в ролевых постах.
- Список правил раздела (`/guide/:section`) и сам выбор разделов (`/guide`) остаются как есть —
  это результат FEAT-173, переделывать их не надо.

### Важная находка PM (проверено по коду 2026-09-20, Analyst обязан перепроверить)
**Редактор у правил и у ролевых постов — уже один и тот же компонент.**
`components/CommonComponents/WysiwygEditor/WysiwygEditor.tsx` (tiptap) используется и в
`Admin/RulesAdminPage/RuleForm.tsx:150`, и в `pages/LocationPage/PostCreateForm.tsx`,
и в `UserProfilePage/WallSection.tsx`, и в `Admin/ArchiveAdminPage/ArchiveArticleForm.tsx`.

Значит «редактор не позволяет» — скорее всего **не про набор, а про показ**:
- посты чистятся через `utils/sanitizePostHtml.ts` — курируемый список тегов, атрибутов
  и классов (`archive-link`, `editor-link`);
- правило чистится голым `DOMPurify.sanitize(rule.content)` без настроек
  (`RulesPage/RuleOverlay.tsx:48`), и рисуется без тех стилей, которыми оформлены посты.

Analyst должен установить **точно**, в чём разница между тем, что видит автор поста, и тем,
что видит читатель правила: разные ли наборы кнопок у редактора (пропсы/варианты), разный ли
санитайзер, разные ли CSS-стили контейнера. От ответа зависит объём работы: если редактор
общий, задача сводится к странице + единому показу, и это заметно меньше, чем кажется.

### UX / Пользовательский сценарий
1. Игрок открывает раздел руководства → видит карточки правил (как сейчас).
2. Кликает карточку → попадает на страницу правила, а не в модалку.
3. Читает текст во всю страницу на тёмной подложке с золотой обводкой.
4. Возвращается к списку раздела.
5. Админ оформляет правило так же свободно, как игрок оформляет ролевой пост, и читатель
   видит это оформление.

### Edge Cases
- Несуществующий id правила в адресе.
- Правило с пустым текстом.
- Старые правила, написанные до задачи: их HTML не должен ни потеряться, ни поехать.
- Прямая ссылка на правило и возврат «назад» в браузере.

### Вопросы к пользователю (если есть)
- [x] **Прямой адрес на правило — нужен.** Адрес вида `/guide/:section/:id`: ссылку можно
      кинуть другому игроку и положить в закладки. Значит страница обязана открываться
      по прямому заходу, а не только переходом из списка.
- [x] **Заголовок и картинка — шапкой сверху.** Формулировка пользователя: «давай попробуем
      пока шапкой» — то есть решение пробное, переделать потом недорого.
- [x] **Про редактор (пользователь, 2026-09-20):** «раздел правил делал полгода назад, может
      сразу прикрутили одинаковый способ ввода». Подтверждает находку PM: редактор изначально
      общий с постами, и задача про оформление — скорее про показ, чем про набор.
- [x] **Санитайзер правил НЕ трогаем.** Прямое решение пользователя: «санитайзер не трогаем».
      Правило по-прежнему чистится свободным дефолтом `DOMPurify.sanitize`, строгая политика
      постов (`sanitizePostHtml`) к правилам **не применяется**. Причина: правила пишут админы,
      а не игроки, и ужесточение сломало бы оформление уже написанных правил (вылетели бы
      таблицы, `target`, размеры шрифта). Это снимает риск «старые правила поедут».
      **Никакой миграции контента в этой задаче нет.**
- [x] **Кнопку «Ссылка на статью Архива» правилам добавить.** Прямое решение пользователя:
      «кнопку архива добавь». Это `enableArchiveLinks` в `RuleForm.tsx:150` плюс обёртка
      `ArchiveLinkPreview` при показе — иначе ссылка будет обычным `<a>` с перезагрузкой
      страницы и без ховер-превью, то есть кнопка появится, а толку от неё не будет.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

_All claims below were re-verified against the code on 2026-09-20. Line numbers are as of that
read. Where the PM brief was wrong, it is marked **CORRECTION**._

### 2.1 Headline answer: what actually differs between a post and a rule

The PM's finding is confirmed — `WysiwygEditor` is one shared component — but the conclusion
"не про набор, а про показ" is only **half** right. There is exactly **one** toolbar difference,
and the sanitiser difference runs the **opposite** way from what the brief assumed.

| Axis | Roleplay post | Rule | Verdict |
|---|---|---|---|
| Editor component | `WysiwygEditor` | `WysiwygEditor` | **identical** |
| Extension set | StarterKit(-bulletList) + `BulletListNoInputRule`, Underline, `ResizableImage`, TextAlign, TextStyle, Color, Highlight, Link | same | **identical** (`WysiwygEditor.tsx:331-353`) |
| `enableArchiveLinks` prop | `true` — `PostCreateForm.tsx:575-579`, `PostEditModal.tsx:374` | **not passed** → defaults to `false` (`RuleForm.tsx:150`, default at `WysiwygEditor.tsx:315`) | **THE ONLY toolbar difference** |
| Sanitiser | `sanitizePostHtml` — strict allow-list (`PostCard.tsx:435`) | bare `DOMPurify.sanitize(rule.content \|\| '')` (`RuleOverlay.tsx:48`) | rule is **MORE** permissive, not less |
| Prose CSS class | `prose-rules` (`PostCard.tsx:428`) | `prose-rules` (`RuleOverlay.tsx:46`) | **identical** |
| Archive-link runtime | wrapped in `<ArchiveLinkPreview>` (`PostCard.tsx:427,437`) | **not wrapped** | **real difference** |
| Container | full-width card, `whitespace-pre-wrap break-words`, `text-white/[0.88] text-sm sm:text-[14.5px]`, blockquote overrides | `modal-content` (max-width **700px**, `RuleOverlay.tsx:24` + `index.css:256-266`), `max-h-[80vh]`, `text-white text-base leading-relaxed` | **real difference** |

**So the "правила оформляются хуже" feeling comes from three things, none of them the editor's
tag set:**
1. no Archive-link button in the rules editor (`enableArchiveLinks` not passed);
2. no `ArchiveLinkPreview` wrapper at render, so an archive link in a rule would be a plain
   `<a href="/archive/...">` — full page reload, no hover preview;
3. the rule is squeezed into a 700px-wide, 80vh-tall modal instead of a page.

#### 2.1.1 `enableArchiveLinks` — exact consumer matrix (verified)

| Consumer | Line | `enableArchiveLinks` |
|---|---|---|
| `pages/LocationPage/PostCreateForm.tsx` | 575-579 | **yes** |
| `pages/LocationPage/PostEditModal.tsx` | 374 | **yes** |
| `Admin/ArchiveAdminPage/ArchiveArticleForm.tsx` | 309 | **yes** |
| `Admin/RulesAdminPage/RuleForm.tsx` | 150 | **no** |
| `UserProfilePage/WallSection.tsx` | 149 (edit), 279 (create) | **no** |

`enableArchiveLinks` is the **only** prop that changes the toolbar
(`WysiwygEditor.tsx:59-63` — the props are `content`, `onChange`, `enableArchiveLinks`; there is
no "variant"/"compact"/"minimal" prop anywhere). When false it drops the `ArchiveLink` tiptap mark
from the extension list (`:352`) and hides the `BookOpen` toolbar button (`:633-660`). Everything
else — B/I/U/S, colour, highlight, H1-H3, alignment, bullet/ordered list, blockquote, dash picker,
external link, image — is unconditional.

#### 2.1.2 Sanitiser diff, tag by tag — **CORRECTION to the brief**

The brief expected the rule's bare `DOMPurify.sanitize` to *lose* formatting. It does not.
Verified against `node_modules/dompurify@3.3.3/dist/purify.cjs.js`:

- `style` **attribute** is in DOMPurify's default HTML allow-list (`purify.cjs.js:202`) → colour,
  highlight, text-align and image sizing all survive a bare sanitize.
- `class` is in the same default list → `editor-link` / `archive-link` survive.
- `ALLOW_DATA_ATTR` defaults to **true** (`purify.cjs.js:439,568`) → `data-archive-slug`,
  `data-color`, `data-type`, `data-align` all survive.
- Default tag list (`purify.cjs.js:188`) is a superset of everything tiptap emits
  (`figure`, `div`, `img`, `mark`, `blockquote`, headings, lists…).

So **a rule loses nothing today relative to a post**; the bare call is *looser* and additionally
permits `<form>`, `<input>`, `<button>`, `<select>`, `<textarea>`, `<style>`, `<audio>`,
`<video>`, arbitrary `class`, arbitrary CSS properties (`position`, `z-index`, `100vw`) and `id`
— exactly what `sanitizePostHtml.ts` was written to block (see its own doc comment, `:1-51`).

What `sanitizePostHtml` *would* strip if applied to rules as-is:
- **Tags** kept: `p br hr h1-h6 ul ol li blockquote pre code strong b em i s del strike u mark span a figure div img` (`sanitizePostHtml.ts:67-75`). Anything else (incl. `table`, `iframe`, `video`, `style`) is dropped.
- **Attributes** kept: `href rel class style src alt data-archive-slug data-color data-type data-align` (`:86-91`). No `id`, no `target`, no `width`/`height` attributes, no other `data-*` (`ALLOW_DATA_ATTR: false`, `:222`), no ARIA (`:223`).
- **Classes** kept: only `archive-link` and `editor-link` (`:152`). Every other class is removed.
- **CSS properties** kept, pinned per tag (`:125-138`): `color` (any tag), `background-color` (only `mark`), `text-align` (block tags + `figure`), `display:inline-block` / `max-width` / `margin*` (only `div`), `width` (`div`/`img`), `height` (`img`). Values must match `px/%/em/rem/auto/0` — **no `vw`/`vh`** — and must not contain `url(`, `expression(`, `image-set`, `--`, `@`, `\` (`:145`).

**Risk if the Architect decides to reuse `sanitizePostHtml` for rules:** admin-authored rules that
contain a `<table>`, an `<iframe>`, an `id`, a `target="_blank"`, a Tailwind class, or a
`font-size`/`vw` style **will visibly change**. This is the "старые правила не должны поехать"
edge case, and it is real. `Archive` has already met this problem and solved it differently —
`ArchiveArticlePage.tsx:164-167` uses `DOMPurify.sanitize(html, { ADD_ATTR: ['data-archive-slug'] })`,
i.e. defaults + one extra attribute, deliberately *not* the post policy. `sanitizePostHtml.ts:55-60`
explicitly says its instance is post-only and that archive/rules are "admin-authored" and
differently trusted. **This is a decision for the Architect / PM, not something to assume.**

#### 2.1.3 CSS — where the styles live

- `.prose-rules` is a single `@layer components` block in
  `services/frontend/app-chaldea/src/index.css:617-713`. It covers headings, `p`, `ul`/`ol`/`li`
  (incl. a specificity fix over the global `ul li{list-style:none}` reset, `:626-631`),
  `strong/em/u/s`, `blockquote` (gold left border, `:636-642`), the ResizableImage
  `figure[data-type="resizable-image"]` wrapper with left/center/right alignment
  (`:644-685`), legacy `img.editor-image` (`:687-693`), links (`a` and `a.editor-link` →
  `#76a6bd`, hover `#fff9b8`, `:694-704`), `mark` (`:705-710`), and `[style*="text-align: …"]`
  fallbacks (`:711-713`).
- **`prose-rules` is already the shared class.** It is used by: the editor body itself
  (`WysiwygEditor.tsx:666`), `PostCard.tsx:428`, `RuleOverlay.tsx:46`,
  `WallSection.tsx:172`, `ArchiveArticlePage.tsx:369`. The name is a leftover from rules; nothing
  post-specific exists as a separate stylesheet.
- `.archive-link` has **no CSS anywhere** (grepped `src/**` + `tailwind.config.js`): it is a
  behavioural hook only, styled by the generic `.prose-rules a` rule. Its behaviour comes from
  `ArchiveLinkPreview`, which attaches delegated listeners on `a[data-archive-slug]`
  (`ArchiveLinkPreview.tsx:182,196,207,242,269`) for hover preview + SPA `navigate()`.
- Post-only extras applied on top of `prose-rules` at `PostCard.tsx:428-430`:
  `text-white/[0.88] text-sm sm:text-[14.5px] leading-relaxed whitespace-pre-wrap break-words`
  plus arbitrary-variant blockquote overrides (`border-gold/50`, `pl-3.5`, italic, `text-white/75`)
  and `[&_em]:italic`. **`whitespace-pre-wrap` is the one that materially changes rendering** —
  it preserves authored newlines/spaces; the rule container does not have it.
- There are **no `.scss` files involved**. The only extra CSS files in `src/styles/` are
  `cosmetic-backgrounds.css` and `cosmetic-frames.css` — unrelated.

#### 2.1.4 tiptap extensions — are any post-only?

**No.** `ResizableImageExtension.tsx` (React NodeView, drag-resize, align) and
`ArchiveLinkExtension.ts` (a `Mark` named `archiveLink` emitting
`<a href="/archive/{slug}" data-archive-slug="{slug}" class="archive-link">`) both live in
`components/CommonComponents/WysiwygEditor/` and are imported by `WysiwygEditor.tsx:10-11`.
`ResizableImage` is always loaded (`:337`); `ArchiveLink` is loaded only when
`enableArchiveLinks` (`:352`). Neither is referenced by any post component directly.

### 2.2 Current `/guide` wiring (FEAT-173) and what has to be untangled

- `App/App.tsx:197` `<Route path="guide" element={<GuidePage />} />`
- `App/App.tsx:198` `<Route path="guide/:section" element={<GuideSectionPage />} />`
- `App/App.tsx:200` `<Route path="rules" element={<Navigate to="/guide" replace />} />`
- `App/App.tsx:201-204` `admin/rules` → `RulesAdminPage`, guarded by `ProtectedRoute requiredPermission="rules:read"`.
- There is **no** `/guide/:section/:id` route today. Adding a third segment is free: nginx has no
  `location` matching `/guide*` (only `= /rules`, `= /rules/` → `301 /guide`, and the `/rules/`
  prefix proxy — `nginx.conf:425,429,433`, `nginx.prod.conf:440,444,448`), and prod's SPA block
  does `try_files $uri $uri/ /index.html` (`nginx.prod.conf:567`). **No nginx change needed.**
- `GuideSectionPage.tsx` holds `selectedRule` state (`:17`), resets it on section change (`:27`),
  passes `setSelectedRule` to `RulesGrid` as `onSelect` (`:59`) and renders
  `<RuleOverlay rule={selectedRule} onClose={…} />` (`:63`). Untangling = drop the state, the
  import (`:6`) and line 63, and change what `RulesGrid` does on click.
- `RulesGrid.tsx` is a presentational grid whose card is a `<button onClick={() => onSelect(rule)}>`
  (`RulesGrid.tsx:28-29`). Turning the card into a `<Link>` requires knowing the section — the grid
  currently does not receive it, but `GameRule.section` is on every item (`api/rules.ts` type), so
  it can build `/guide/${rule.section}/${rule.id}` itself.
- `components/RulesPage/` contains **only** `RuleOverlay.tsx` and `RulesGrid.tsx` — there is no
  `RulesPage.tsx` any more (FEAT-173 removed it).

### 2.3 `RuleOverlay` blast radius

`RuleOverlay` has exactly **one** consumer: `GuideSectionPage.tsx:6` (import) and `:63` (render).
Nothing else in the repo references it (full-tree grep). Deleting it breaks nothing else.

### 2.4 Backend — is a new endpoint needed?

**No. `GET /rules/{rule_id}` already exists and is public.**

- `services/locations-service/app/main.py:1944-1950` — `@rules_router.get("/{rule_id}", response_model=schemas.GameRuleRead)`, no `Depends(require_permission…)`, returns 404 with `detail="Правило не найдено"`.
- `crud.get_rule_by_id` — `services/locations-service/app/crud.py:3107-3112`.
- `schemas.GameRuleRead` (`schemas.py:775-786`) returns `id, title, section, image_url, content, sort_order, created_at, updated_at` — everything a page needs, including `section` for breadcrumbs. Pydantic v1 (`orm_mode = True`) as expected.
- Route order is safe: `/list` is declared at `:1932`, before `/{rule_id}` at `:1944`. `/create`
  (POST), `/reorder` (PUT) and `/{rule_id}/update` differ by method/path, no shadowing.
- Frontend client **already has the function**: `api/rules.ts` `fetchRule(id)` → `GET /rules/{id}`.
  It is currently **unused anywhere in the app** (grep: only its own definition). It is wired to
  the same axios instance, so the response interceptor converts a 404 into
  `new Error("Правило не найдено")` — usable directly for the "несуществующий id" edge case.

**Conclusion: zero backend changes, zero DB changes, zero Alembic migration, zero nginx changes.
This is a frontend-only feature** — unless the Architect decides rules need a slug instead of a
numeric id (there is no `slug` column on `game_rules`; that *would* be a migration).

### 2.5 Design-system classes for "dark background + gold outline" (existing, nothing invented)

The profile's real component is **`ProfilePage/PanelShell.tsx`**, documented in
`docs/DESIGN-SYSTEM.md:779-794` ("a gold-outlined, blurred panel with a header band", and
`:631` lists "Profile panel (gold ring + blur + header band) → PanelShell").

Its outer element (`PanelShell.tsx:44-46`):
```
gold-outline relative rounded-card bg-site-bg backdrop-blur-[10px] shadow-card flex flex-col min-w-0 w-full
```
Its header band (`:49`):
```
gradient-divider-h relative flex items-center gap-2.5 px-5 py-4 bg-black/20 rounded-t-card shrink-0
```
with the title as `gold-text text-sm font-medium uppercase tracking-[0.12em]` (`:52`), and the
default body (`:66`) `flex-1 min-h-0 p-4 lg:p-5 lg:overflow-y-auto gold-scrollbar-wide`.
`PANEL_DESKTOP_HEIGHT_CLASS = 'lg:h-[calc(100vh-130px)]'` (`:8`) — a fixed desktop height, which
an article page probably should **not** use.

Underlying definitions (all in `index.css`, `@layer components`):
- `.gold-outline` — `:24-41`, a `::after` pseudo with `inset:-3px` and the gold gradient mask; requires `position:relative` + a `border-radius` on the element.
- `.gold-outline-thick` — `:44-50`, 2px / `inset:-6px`, "for modals, active states".
- `.gray-bg` — `:53-56`, `rgba(9,10,16,0.62)` + `border-radius:15px`.
- `.gold-text` — `:14-19`, gold gradient clipped to text.
- `.gold-scrollbar-wide` — `:717+`.
- `.gradient-divider-h` — `:95-111`.
Tailwind tokens (`tailwind.config.js`): `bg-site-bg` = `rgba(9,10,16,0.62)` (`:29`),
`rounded-card` = `15px` (`:59`), `shadow-card` (`:65`), `max-w-container` = `1360px` (`:20`),
`text-gold` / `gold-light` / `gold-dark` (`:23-27`).

**Caveat for the Architect:** `PanelShell` lives in `src/components/ProfilePage/` and is used
**only inside `ProfilePage/`** (20 files, all under that folder). Importing it from
`components/GuidePage/` would be the first cross-folder use. The alternatives are (a) import it
anyway, (b) move/re-export it to `CommonComponents/`, or (c) write the page shell inline from the
same class string. This is an architectural call, not an analysis one.

Also note `docs/DESIGN-SYSTEM.md:890` — "Any modal rendered below a blurred or transformed
ancestor must be portaled": `backdrop-blur-[10px]` creates a containing block, so if the rule page
ever hosts a modal, it must be portaled.

### 2.6 Affected files (frontend only)

| File | Type of change |
|---|---|
| `src/components/App/App.tsx` | new route around `:197-198` |
| `src/components/GuidePage/GuideSectionPage.tsx` | drop `selectedRule` state + `RuleOverlay` import/render (`:6,17,27,59,63`) |
| `src/components/RulesPage/RulesGrid.tsx` | card becomes a link instead of `onSelect` |
| `src/components/RulesPage/RuleOverlay.tsx` | delete (single consumer) |
| **new** rule page component | uses `fetchRule` (already in `api/rules.ts`) |
| `src/components/Admin/RulesAdminPage/RuleForm.tsx:150` | add `enableArchiveLinks` (if archive links are wanted in rules) |
| `src/utils/sanitizePostHtml.ts` *or* a rules-specific sanitiser | only if the sanitiser is unified — see 2.1.2 risk |

### 2.7 Patterns and constraints to respect

- Frontend is TS-only for new files (`CLAUDE.md` §10.9) — every file touched here is already `.tsx`, so no `.jsx` migration burden.
- Tailwind only, no new SCSS (§10.8); `prose-rules` is an existing `@layer components` block, extending it is allowed (§10.10 permits extending the design system).
- No `React.FC` (§10.11) — all the existing components here already follow it.
- Mobile from 360px (§10.12): `RulesGrid` is `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`; the new page must not reintroduce a fixed width. Note `modal-content`'s `max-width: 700px` disappears with the modal — a full-width article needs its own readable max-width.
- Every API call needs a visible Russian error (`CLAUDE.md` §11 "Frontend Error Display"). `GuideSectionPage.tsx:30-35` shows the existing pattern: `toast.error` + inline `<p className="text-site-red">`.
- **QA:** no backend Python changes are planned → per `CLAUDE.md` §11 the mandatory-pytest rule does not bite. If the Architect adds anything backend, it does.

### 2.8 Risks

| Risk | Mitigation |
|---|---|
| Unifying the sanitiser silently degrades existing admin-written rules (tables, `iframe`, `id`, `target`, arbitrary classes, `font-size`) — see 2.1.2 | Do **not** apply `sanitizePostHtml` to rules without an explicit decision. Archive's precedent (`ArchiveArticlePage.tsx:164`) is defaults + `ADD_ATTR`. Ask PM. |
| Loosening the rules sanitiser further is a security cost: bare DOMPurify already allows `<form>`/`<input>`/`<style>` in a page every player reads | Rules are admin-authored (RBAC `rules:create`/`rules:update`), so the threat model is weaker than posts — but tightening is the safer direction, not loosening. |
| `whitespace-pre-wrap` (posts) vs not (rules) changes how existing rule HTML lays out if copied verbatim from `PostCard` | Decide deliberately; `pre-wrap` on old rule HTML may add blank lines. |
| Deleting `RuleOverlay` | Safe — single consumer (2.3). |
| Direct link `/guide/:section/:id` where the id belongs to a different section | `GameRuleRead.section` comes back with the rule; redirect or just render. Needs a product decision (PM question 1 already open). |
| `PanelShell` import from outside `ProfilePage/` sets a new precedent | Architect decides: import, relocate, or inline the class string. |
| Empty `content` (`content: string \| null` in `api/rules.ts`) | Explicit empty state, not a blank page. |

### 2.9 Open questions for PM

1. **Sanitiser policy for rules** — keep the loose default (+ `ADD_ATTR: ['data-archive-slug']`, like Archive), or adopt the strict post policy and accept that some old rules change? This is the single decision that determines whether "оформление как в постах" is a 1-line prop change or a content-migration risk.
2. Should the rules editor get the Archive-link button (`enableArchiveLinks` at `RuleForm.tsx:150`)? It is one prop, plus an `ArchiveLinkPreview` wrapper at render. PM's brief implies yes ("возможности = возможностям постов"), but it is not stated.
3. `WallSection.tsx` (profile wall) also lacks `enableArchiveLinks` **and** renders `post.content` with **no sanitiser at all** (`WallSection.tsx:173` — raw `dangerouslySetInnerHTML`). Same for `ProfilePage/PostHistoryTab/PostHistoryTab.tsx:79`. **These are pre-existing XSS holes unrelated to this feature** — flagged here, not fixed; added to `docs/ISSUES.md` (HIGH) as a separate task.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Verification of the analysis report

Every load-bearing claim of section 2 was re-checked against the code before designing on it.
Confirmed:

- `GET /rules/{rule_id}` is **public** (`locations-service/app/main.py:1944-1950`, no
  `Depends(require_permission…)`, 404 `detail="Правило не найдено"`), declared **after** `/list`
  (`:1932`) so there is no route shadowing. `schemas.GameRuleRead` (`schemas.py:775-786`) returns
  `id, title, section, image_url, content, sort_order, created_at, updated_at` — everything the page
  needs, `section` included.
- `fetchRule(id)` already exists in `src/api/rules.ts` and is used nowhere; it goes through the
  `rulesClient` interceptor that turns a 404 into `new Error("Правило не найдено")`.
- `RuleOverlay` has exactly one consumer — `GuideSectionPage.tsx` (import `:6`, render `:63`).
  Deleting it is safe.
- `RulesGrid` card is a `<button onClick={() => onSelect(rule)}>`; `GameRule.section` is on every
  item, so the grid can build the target URL itself.
- `PanelShell.tsx` lives in `components/ProfilePage/`, outer classes
  `gold-outline relative rounded-card bg-site-bg backdrop-blur-[10px] shadow-card flex flex-col min-w-0 w-full`,
  header band `gradient-divider-h … px-5 py-4 bg-black/20 rounded-t-card shrink-0`.
- Bare `DOMPurify.sanitize` keeps `style`, `class` and `data-*` (`ALLOW_DATA_ATTR` defaults to
  `true`), so `data-archive-slug` survives **without** any config — see 3.4.
- `enableArchiveLinks` is the only prop that changes the toolbar
  (`WysiwygEditor.tsx:59-63, 315`); `RuleForm.tsx:150` does not pass it.

**Two corrections to section 2, both cosmetic:**

1. Paths: `PostCard.tsx`, `PostCreateForm.tsx`, `PostEditModal.tsx` and `ArchiveArticlePage.tsx`
   live under `src/components/**pages**/…` (`components/pages/LocationPage/PostCard.tsx`,
   `components/pages/ArchivePage/ArchiveArticlePage.tsx`). `GuidePage/` and `RulesPage/` sit
   directly under `src/components/`. Developers must use the real paths listed in section 4.
2. There is **no global `ScrollToTop`** in the app (grepped `ScrollToTop` and `scrollTo(0` across
   `src/**` — zero hits). React Router therefore keeps the list's scroll offset when navigating
   into the article. This is a new requirement the analysis did not raise — see 3.6.

### 3.1 Scope — what this feature is and is not

**Frontend-only.** Confirmed, and binding:

> **No agent may touch backend Python, Alembic migrations, the database, nginx configs, RBAC
> permissions, `docker-compose*.yml` or Dockerfiles in this feature.** The endpoint, the schema and
> the API client function all already exist and are sufficient. The SPA fallback already serves any
> depth of path (`try_files $uri $uri/ /index.html`, `nginx.prod.conf:567`) and no `location` block
> matches `/guide*`, so a third URL segment needs no proxy change. Rules are public reads — no auth,
> no new permission, no rate-limit decision. Anyone who finds themselves editing a `.py` file, a
> `nginx*.conf` or a compose file has left the scope of FEAT-174 and must stop and report to PM.

Consequently there is **no QA Test task with pytest** in this feature (`CLAUDE.md` §11: the
mandatory-pytest rule applies to features that modify backend Python code; this one modifies none).
That exemption is paid for by a **hardened live-verification duty on the Reviewer** — see 3.7 and
task 5.

### 3.2 Routing and URL contract

| | |
|---|---|
| New route | `/guide/:section/:id` → `GuideRulePage` |
| Declared at | `components/App/App.tsx`, immediately after `guide/:section` (`:198`) |
| Guard | none — public, like `/guide` and `/guide/:section` |
| `:section` | one of `site` / `roleplay` / `technobook` (`constants/guideSections.ts`) |
| `:id` | the numeric `game_rules.id` |

**The id is the identity; the section segment is decorative** (breadcrumb + readable URL). This is
the decision that makes every edge case fall out cleanly:

- **`:id` is not a positive integer** (`/guide/site/abc`) → do not call the API at all, render the
  "rule not found" state (3.5).
- **`:section` is not a known slug** (`/guide/rubbish/42`) → still fetch by id, then canonically
  redirect (below). Do **not** `Navigate to="/guide"` on an unknown section here — that would throw
  away a link that carries a perfectly valid rule id.
- **Section mismatch** (`/guide/site/42` where rule 42 is `technobook`) → after the rule loads,
  `<Navigate to={`/guide/${rule.section}/${rule.id}`} replace />`. Rationale: the link a player
  pasted keeps working (no dead end for a typo or for a rule an admin later moved between
  sections), the URL self-heals into its canonical form, and `replace` keeps the history stack
  clean so the browser Back button returns to whatever the player was on before, not to a redirect
  that bounces them forward again. Rejected alternatives: rendering the wrong breadcrumb (lies to
  the user), and 404-ing on mismatch (breaks every link to a rule that was moved between sections —
  a realistic admin action, since `RuleForm` can change `section`).
- Note `GuideSectionPage` keeps its own existing `isGuideSection` guard for `/guide/:section`
  untouched — that page has no id to fall back on, so redirecting to `/guide` is right there.

No slug column, no id→slug migration: `game_rules` has no `slug` and adding one would be a backend
change, which 3.1 forbids.

### 3.3 Page composition — "dark background + gold outline", header on top

Layout, outermost to innermost:

```
<div className="w-full max-w-container mx-auto">          ← same wrapper as GuidePage/GuideSectionPage
  ← «Раздел» back link (site-link text-sm)                 ← breadcrumb to /guide/{rule.section}
  <article  gold-outline relative rounded-card bg-site-bg  ← THE PANEL (PanelShell's class string)
            backdrop-blur-[10px] shadow-card
            overflow-hidden >
      ┌ HEADER BAND ────────────────────────────────┐
      │ cover image (rule.image_url) as a banner,   │  ← only when image_url is set
      │ dark gradient over it, <h1> gold-text on top│
      └─────────────────────────────────────────────┘
      ┌ BODY ───────────────────────────────────────┐
      │ ArchiveLinkPreview > div.prose-rules         │  ← the rule HTML, full page width
      └─────────────────────────────────────────────┘
  </article>
```

**Decision: do not import `PanelShell`, do not move it — reproduce its documented class string
inline in the new page.** Reasoning, in order of weight:

1. **It does not fit.** `PanelShell`'s header band is a one-line icon+title row
   (`px-5 py-4 bg-black/20`, small uppercase `text-sm` title, right-aligned `headerExtra`). The
   feature asks for a **cover band**: a wide image with a large title over it. Getting that out of
   `PanelShell` means either adding an image/banner prop to it — scope creep into `ProfilePage/`,
   a component shared by 20 files and specified in `DESIGN-SYSTEM.md` §18 — or passing no `title`
   and building the header inside `children`, which reuses only the outer `<section>` and gains
   nothing.
2. **Moving it to `CommonComponents/` is a 20-file import churn** plus a `DESIGN-SYSTEM.md` §18
   rewrite, all of it unrelated to this feature. That violates the minimal-diff rule and would
   collide with any other work under `ProfilePage/`.
3. **Importing it across folders** would set the precedent for `ProfilePage/`-scoped components
   being reached into from anywhere, while §18 explicitly frames them as the `/profile` language —
   and it would buy us only the outer `<section>` (see 1).
4. What we actually reuse is the **design-system token combination**, not the component:
   `gold-outline` + `rounded-card` + `bg-site-bg` + `backdrop-blur-[10px]` + `shadow-card`, all four
   defined in `index.css`/`tailwind.config.js`. Nothing is invented; the string is copied verbatim
   from `PanelShell.tsx:44-46` minus its flex/height plumbing.

**Do not use `PANEL_DESKTOP_HEIGHT_CLASS`, `overflow-y-auto` or `gold-scrollbar-wide` on this
page.** An article scrolls with the page, not inside a box — that inner-scroll box is exactly what
the user is complaining about in the modal (`max-h-[80vh]`). The panel is auto-height at every
breakpoint.

Header band specifics:

- With `rule.image_url`: a banner `div` with `bg-cover bg-center`, capped height
  (`h-40 sm:h-56 md:h-64`), a `bg-gradient-to-t from-black/80 via-black/40 to-transparent` overlay
  (same idiom as `RulesGrid`'s card) and the `<h1>` absolutely positioned over its lower area.
  `rounded-t-card` is handled by the panel's `overflow-hidden`.
- Without `image_url`: no banner; a plain title band in the `PanelShell` idiom —
  `gradient-divider-h relative px-5 py-4 bg-black/20` with the `<h1>` inside. A missing image must
  never leave an empty grey rectangle.
- Title: `gold-text` + `text-2xl sm:text-3xl font-medium uppercase` (the `gold-text` + uppercase
  pairing already used by `RuleOverlay:41` and `GuideSectionPage:46`), `break-words` so a long
  title cannot push the panel wide at 360px.
- `image_url` is admin-uploaded (`uploadRuleImage` → photo-service), used as a CSS
  `background-image` exactly as `RulesGrid` already does — no new trust surface.

Mobile (360px) is mandatory: single column throughout, body padding `p-4 sm:p-6 md:p-8`, banner
height steps up by breakpoint, no fixed pixel widths anywhere, `min-w-0` where a flex row is used.
The `modal-content` `max-width: 700px` is gone with the modal; the page is bounded by the existing
`max-w-container` (1360px) wrapper — that is the intended "во всю страницу" width, and no new
narrower reading measure is introduced, because the brief asks for full width.

### 3.4 Content rendering — sanitiser, wrapper, container classes

**Sanitiser: unchanged, per the user's explicit decision.** The new page renders

```
DOMPurify.sanitize(rule.content || '')
```

— the exact call from `RuleOverlay.tsx:48`, moved verbatim. `sanitizePostHtml` is **not** applied to
rules, and there is **no content migration** in this feature.

- This is not laziness: bare DOMPurify keeps `style`, `class` and `data-*` by default, so it is
  *more* permissive than the post policy. Swapping in `sanitizePostHtml` would strip `<table>`,
  `id`, `target`, `font-size`, `vw` units and every non-`archive-link`/`editor-link` class out of
  rules admins already wrote — i.e. it would cause the very "старые правила поехали" regression the
  feature must avoid.
- **`ADD_ATTR: ['data-archive-slug']` is deliberately *not* added**, unlike
  `ArchiveArticlePage.tsx:164`. With DOMPurify's default `ALLOW_DATA_ATTR: true` that option is a
  verified no-op here, and adding it would be "touching the sanitiser" for no behavioural gain.
- Security note for the record: rules are admin-authored behind `rules:create` / `rules:update`,
  so the threat model is an already-privileged author, not a player. Loosening is what we are *not*
  doing; tightening is a separate, deliberate decision the user has declined for now. The unrelated
  wall/post-history XSS holes the Analyst found stay in `docs/ISSUES.md` and stay out of this
  feature.

**Archive links.** Two halves, both required or neither is worth doing:

1. `RuleForm.tsx:150` passes `enableArchiveLinks` to `WysiwygEditor` → the `BookOpen` toolbar
   button and the `archiveLink` tiptap mark appear for rule authors.
2. The article page wraps its content `div` in `<ArchiveLinkPreview>` (default export,
   `components/CommonComponents/ArchiveLinkPreview/ArchiveLinkPreview.tsx`, takes only `children`
   and renders a `<div data-archive-tooltip>`). Without it an archive link in a rule is a plain
   `<a href="/archive/…">` → full page reload, no hover preview, styled like any other link. Usage
   copies `PostCard.tsx:426-438` / `ArchiveArticlePage.tsx:368-381`.

`ArchiveLinkPreview` portals its tooltip to `document.body` already, so the panel's
`backdrop-blur-[10px]` containing block (`DESIGN-SYSTEM.md:890`) is not a problem. Nothing else on
this page may render an in-place `modal-overlay`.

**Container classes — reproduce `RuleOverlay`'s, not `PostCard`'s.** The body div is:

```
prose-rules text-white text-base leading-relaxed break-words
```

- `prose-rules` is already the shared prose stylesheet (`index.css:617-713`) used by the editor
  itself, posts, the wall, archive articles and the old overlay — so what the admin sees while
  typing is what the reader gets. Nothing new is added to `index.css` by this feature.
- **`whitespace-pre-wrap` is explicitly forbidden here.** It is the one `PostCard` class that
  materially changes rendering: applied to existing tiptap rule HTML it resurrects the newlines
  between block tags as visible blank lines. Rules never had it; adding it is precisely the
  "старые правила поехали" failure mode.
- `PostCard`'s arbitrary-variant blockquote/`em` overrides are post-tuning and are **not** copied —
  `prose-rules` already styles `blockquote` with a gold left border (`index.css:636-642`), and
  copying the overrides would change how existing rules look.
- Net effect: a rule's HTML renders byte-for-byte as it does in today's modal, only wider and
  without the inner scrollbar. That is the regression guarantee for the "old rules" edge case, and
  it is directly testable by comparing a rule before/after.

### 3.5 States (all four are mandatory, all copy in Russian)

| State | Render |
|---|---|
| Loading | `<p className="text-white/60 text-base">Загрузка...</p>` — the `GuideSectionPage:50` idiom |
| Error (network/5xx) | inline `<p className="text-site-red text-base">{message}</p>` **and** `toast.error(message)` — the `GuideSectionPage:30-35` pattern. `CLAUDE.md` §11 forbids silent failures |
| Not found (404, or non-numeric id) | «Правило не найдено» + a `site-link` back to `/guide` (the section is unknown in this case). Not a blank page, not a redirect |
| Empty `content` (`null` / `''` / whitespace) | header renders normally; body shows «В этом правиле пока нет текста» in `text-white/60`. Never an empty gold box |

The axios interceptor in `api/rules.ts` already converts a 404 into
`Error("Правило не найдено")`, so distinguishing 404 from other failures follows the
`ArchiveArticlePage.tsx:150-155` precedent (message inspection). A simple, honest fallback is
acceptable: any error shows its Russian message; the 404 branch additionally drops the "back to
guide" link. Do not invent an English string anywhere on this page.

### 3.6 Navigation behaviour

- **Card → article:** `RulesGrid`'s card stops being a `<button onClick={onSelect}>` and becomes a
  `<Link to={`/guide/${rule.section}/${rule.id}`}>` with the identical class list (`image-card
  rounded-card shadow-card hover:shadow-hover … aspect-[16/9] relative overflow-hidden group`),
  `w-full text-left` replaced by `block`. Using `rule.section` (not the route param) means the grid
  always emits the canonical URL and needs no new prop. The `onSelect` prop is removed from
  `RulesGridProps`; `GuideSectionPage` is its only caller.
- **Direct hit / bookmark / pasted link:** works by construction — the page fetches by the route
  param in a `useEffect` keyed on `id`, never from router state, and never assumes the list was
  loaded first. No `location.state` passing of a preloaded rule: it would silently break the paste
  case. One extra `GET /rules/{id}` per open is the correct trade.
- **Browser Back:** returns to `/guide/:section`, which refetches its own list — no shared state to
  restore, nothing to unwind. The canonical redirect uses `replace` so it never traps Back.
- **Scroll position:** since the app has no global `ScrollToTop` (3.0), the article page scrolls
  itself to the top on mount / on `id` change (`window.scrollTo(0, 0)` in the same effect). This
  stays **local to the new page** — do not add a global scroll-restoration component, that would
  change behaviour on every route in the app and is out of scope.
- `RuleOverlay.tsx` is deleted, together with `GuideSectionPage`'s `selectedRule` state (`:17`),
  its reset inside `load()` (`:27`), the `onSelect` wiring (`:59`) and the render (`:63`). `motion`
  usage elsewhere in those files is untouched.

### 3.7 Verification strategy (replaces the missing pytest layer)

Because there is no backend change and therefore no pytest task, the only automated gates are
`npx tsc --noEmit` and `npm run build` (run inside the frontend container — the host has no node,
per project convention). Those cannot catch a broken route or a mangled rule, so the Reviewer's
live check is **not optional and is enumerated** in task 5: direct URL entry, Back button, section
mismatch redirect, non-existent id, image-less rule, empty rule, an old formatting-heavy rule
compared against `git stash`-era rendering, the archive-link round trip, and a 360px viewport pass —
each with a zero-console-error requirement. A review that reports only `tsc`/`build` results is
invalid.

### 3.8 Data flow

```
Player clicks a rule card in /guide/:section
  → <Link> → React Router → GuideRulePage mounts with {section, id}
  → id validated as a positive integer  (fail → «Правило не найдено»)
  → fetchRule(id)  →  GET /rules/{id}   (nginx → locations-service:8006, public)
      404 → interceptor → Error("Правило не найдено") → not-found state
      other error → Russian message inline + toast
      200 → GameRuleRead
          → rule.section !== section  → <Navigate replace> to the canonical URL
          → render: banner/title band, then
            ArchiveLinkPreview > div.prose-rules[dangerouslySetInnerHTML = DOMPurify.sanitize(content)]
Direct URL entry: identical from the "GuideRulePage mounts" step — no dependency on the list page.
```

No new endpoint, no new state in Redux (the page owns its `rule`/`loading`/`error` locally, exactly
as `GuideSectionPage` and `ArchiveArticlePage` do), no cross-service effect.

---

## 4. Task Specs (filled by Architect — in English)

**File ownership is disjoint by design** — no two tasks touch the same file, so 1-3 can run fully
in parallel.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| **1** | **Create the rule article page and register its route.** New `GuideRulePage` per §3.2-3.6: route param validation, `fetchRule`, canonical-section redirect, the four states, the gold panel with header band, `ArchiveLinkPreview`-wrapped `prose-rules` body, scroll-to-top on mount. Register `<Route path="guide/:section/:id" element={<GuideRulePage />} />` directly after the existing `guide/:section` route. | Frontend Developer | DONE | **create** `services/frontend/app-chaldea/src/components/GuidePage/GuideRulePage.tsx`; **modify** `services/frontend/app-chaldea/src/components/App/App.tsx` (route + import only) | — | `/guide/roleplay/{id}` opens the rule as a full page on a direct browser hit (not only via the list). Panel uses exactly `gold-outline relative rounded-card bg-site-bg backdrop-blur-[10px] shadow-card` — no new CSS, no `.scss`, no `index.css` edit, no `PanelShell` import, no `PANEL_DESKTOP_HEIGHT_CLASS`, no inner `overflow-y-auto`. Body is `prose-rules text-white text-base leading-relaxed break-words` and **contains no `whitespace-pre-wrap`**. Content is `DOMPurify.sanitize(rule.content \|\| '')` with **no options object**. Non-numeric id → no network call + «Правило не найдено». Mismatched section → `<Navigate replace>` to `/guide/{rule.section}/{id}`. Empty content → «В этом правиле пока нет текста». Error → inline `text-site-red` **and** `toast.error`, both Russian. No `image_url` → title band, no empty banner. Renders correctly at 360px with no horizontal scroll. No `React.FC`. `npx tsc --noEmit` and `npm run build` pass (run in the frontend container). |
| **2** | **Turn rule cards into links and retire the modal.** `RulesGrid`: card becomes a `<Link to={`/guide/${rule.section}/${rule.id}`}>` with the same visual classes; drop `onSelect` from props. `GuideSectionPage`: remove the `RuleOverlay` import, the `selectedRule` state, its reset in `load()`, the `onSelect` prop and the `<RuleOverlay …>` render. Delete `RuleOverlay.tsx`. Everything else on the section page (heading, back link, loading/error/empty states, grid) stays byte-identical — FEAT-173's list is not being redesigned. | Frontend Developer | DONE | **modify** `services/frontend/app-chaldea/src/components/RulesPage/RulesGrid.tsx`, `services/frontend/app-chaldea/src/components/GuidePage/GuideSectionPage.tsx`; **delete** `services/frontend/app-chaldea/src/components/RulesPage/RuleOverlay.tsx` | 1 (logical only — no shared files) | Clicking a card navigates to `/guide/{section}/{id}`; no modal opens anywhere. Cards remain keyboard-focusable and middle-click / "open in new tab" now works (that is the point of `<Link>`). Grid stays `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`. `grep -rn "RuleOverlay" services/frontend/app-chaldea/src` returns nothing. The `/guide/:section` page's own look and states are unchanged. `npx tsc --noEmit` and `npm run build` pass. |
| **3** | **Give the rules editor the Archive-link button.** Pass `enableArchiveLinks` to `WysiwygEditor` in `RuleForm` (the only change in this file). | Frontend Developer | DONE | **modify** `services/frontend/app-chaldea/src/components/Admin/RulesAdminPage/RuleForm.tsx` (line ~150) | — | The `BookOpen` "Ссылка на статью Архива" button appears in the rules editor toolbar in `/admin/rules`; inserting a link produces `<a href="/archive/{slug}" data-archive-slug="{slug}" class="archive-link">`. No other change in the file. `npx tsc --noEmit` and `npm run build` pass. |
| **4** | **Document the new surface.** One short subsection in `docs/DESIGN-SYSTEM.md` recording that the guide article page reuses the profile panel's token combination inline (and *why* `PanelShell` is not imported — §3.3), so the next developer does not "fix" it by reaching into `ProfilePage/`. Also note the banner-header variant. No new tokens, no new classes. | Frontend Developer | DONE | **modify** `docs/DESIGN-SYSTEM.md` | 1 | The doc names the exact class string, the file that uses it, and the one-line rationale. Nothing else in the doc changes. |
| **5** | **Review — static checks plus a mandatory live pass.** There is **no pytest task in this feature and that is correct** (`CLAUDE.md` §11: zero backend Python is touched). The live checklist below therefore replaces it and is **required**; a PASS reported without it is invalid. | Reviewer | DONE | all files from tasks 1-4 | 1, 2, 3, 4 | **Static:** `npx tsc --noEmit` and `npm run build` pass, results pasted. **Scope:** `git diff --stat` shows **no** `.py`, no `alembic/`, no `nginx*.conf`, no `docker-compose*.yml`, no `Dockerfile`, no `index.css`, no `.scss`. **Live (each with an empty browser console):** (a) click-through from `/guide/roleplay` opens the article; (b) the same URL pasted into a fresh tab renders identically; (c) browser Back returns to the section list; (d) `/guide/site/{id-of-a-technobook-rule}` lands on `/guide/technobook/{id}` and Back does not bounce; (e) `/guide/site/999999` and `/guide/site/abc` both show «Правило не найдено», no white screen; (f) a rule with no image shows a title band, not an empty banner; (g) a rule with empty content shows the Russian empty state; (h) **an existing formatting-heavy rule (headings, list, coloured text, image, blockquote) is compared against its pre-change rendering and nothing has shifted, lost formatting, or gained blank lines**; (i) an archive link inserted through the new toolbar button navigates without a full page reload and shows the hover preview; (j) 360px viewport: no horizontal scrollbar on the article page, the title wraps, the banner scales, the body is readable. **Security:** confirm the sanitiser call is still the bare `DOMPurify.sanitize(rule.content \|\| '')` — neither tightened to `sanitizePostHtml` nor given an options object. |

### Explicitly out of scope (do not do these)

- Any backend, migration, nginx, RBAC, compose or Dockerfile change (§3.1).
- Applying `sanitizePostHtml` to rules, or migrating existing rule HTML (user decision, §3.4).
- Moving or re-exporting `PanelShell` (§3.3).
- Adding a global `ScrollToTop` (§3.6).
- Redesigning `/guide` or `/guide/:section` (FEAT-173 output).
- Fixing the `WallSection` / `PostHistoryTab` missing-sanitiser XSS — it is already logged in
  `docs/ISSUES.md` as a separate HIGH item and must stay separate.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-20
**Result:** PASS

All four development tasks meet their acceptance criteria. No blocking issues found.

#### Automated Check Results
- [x] `npx tsc --noEmit` — **PASS** (run in the `frontend` container, `/app`; zero output, zero errors)
- [x] `npm run build` — **PASS** (`✓ built in 31.99s`; only the pre-existing >500 kB chunk-size warning, unchanged by this feature)
- [ ] `py_compile` — N/A (zero Python touched)
- [ ] `pytest` — N/A (zero backend Python touched; per `CLAUDE.md` §11 the mandatory-QA rule does not apply — §3.1 of this card, confirmed against the diff)
- [x] `docker-compose config` — N/A/PASS (no compose file is in the diff; nothing to validate for this feature)
- [x] Live verification — **PARTIAL** (HTTP level only; see the limitation note below)

#### Scope Check (`git status` + `git diff HEAD`)
```
docs/DESIGN-SYSTEM.md                                        | 30 +
 .../components/Admin/RulesAdminPage/RuleForm.tsx            |  2 +-
 .../src/components/App/App.tsx                              |  2 +
 .../src/components/GuidePage/GuideSectionPage.tsx           |  7 +-
 .../src/components/RulesPage/RuleOverlay.tsx                | 58 ----  (deleted)
 .../src/components/RulesPage/RulesGrid.tsx                  | 12 +-
 (new) .../src/components/GuidePage/GuideRulePage.tsx
```
No `.py`, no `alembic/`, no `nginx*.conf`, no `docker-compose*.yml`, no `Dockerfile`, no `index.css`,
no `.scss`. Scope of §3.1 respected exactly.

#### User-decision boundaries (each one a FAIL if broken — all held)
| Boundary | Verified at | Result |
|---|---|---|
| Bare sanitiser, **no options object** | `GuideRulePage.tsx:133` — `DOMPurify.sanitize(rule.content \|\| '')` | OK |
| `sanitizePostHtml` **not** applied to rules; no `ADD_ATTR` | grep over all three touched components — zero hits | OK |
| No `whitespace-pre-wrap` on the body | body class is `prose-rules text-white text-base leading-relaxed break-words` (`:131`) — the old modal's class set, not `PostCard`'s | OK |
| `PanelShell` not imported / not moved | only a explanatory comment mentions it (`:10`); `index.css` untouched; panel is the inline token string (`:14-15`) | OK |
| No fixed height / inner scroll | no `PANEL_DESKTOP_HEIGHT_CLASS`, no `overflow-y-auto`, no `max-h-*` anywhere in the file (grep) | OK |
| Scroll to top on mount / id change | `window.scrollTo(0, 0)` at the head of the effect keyed on `ruleId` (`:33`, `:67`) | OK |
| Body wrapped in `ArchiveLinkPreview` | `:129-136`; `enableArchiveLinks` added at `RuleForm.tsx:150` — both halves present, so the toolbar button is actually useful | OK |

#### Standards Check
- TypeScript, new file is `.tsx`, no `any`, no `React.FC` (both `GuideRulePage` and `RuleArticle` are plain arrow components with typed props).
- Tailwind only; zero new SCSS/CSS; every class used (`gold-outline`, `rounded-card`, `bg-site-bg`, `shadow-card`, `gradient-divider-h`, `gold-text`, `site-link`, `prose-rules`, `text-site-red`) is an existing design-system token.
- Responsive from 360px: single column, `h-40 sm:h-56 md:h-64` banner, `p-4 sm:p-6 md:p-8` body, `break-words` on the title and the body, panel `overflow-hidden`, no fixed pixel width anywhere. The grid keeps `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`.
- Error display: every failure path is visible and Russian — inline `text-site-red` **plus** `toast.error` for network/5xx (`:48-53`, `:87`), «Правило не найдено» for 404 and for a non-numeric id, «В этом правиле пока нет текста» for empty content. No silent catch.
- `RuleOverlay` fully retired: `grep -rn "RuleOverlay" services/frontend/app-chaldea/src` → no hits.
- Non-numeric id is guarded before any network call (`:159-163`), which also avoids FastAPI's 422 whose `detail` is an array — the axios interceptor would otherwise build an `Error` from an object.

#### Live Verification Results (HTTP level)
**Limitation, stated plainly:** the `chrome-devtools` MCP server is not available in this session
(the only MCP servers present are Claude Docs and Google Drive; `pencil` failed to connect), there is
no browser-automation tool, and the frontend has no test runner / jsdom in `package.json`, so
**nothing could be verified with actual rendering.** Items (a)-(c), (f)-(j) of the §3.7 checklist —
visual layout, console cleanliness, the before/after comparison of a formatting-heavy rule, the
archive-link hover preview, and the 360px pass — **were not observed in a browser**. They were
verified by code reading only. This is the one gap in this review and it should be closed by a human
eye before the feature is called done.

What *was* verified against the running stack (dev, `http://localhost`):
- SPA fallback serves the new 3-segment depth — `/guide/site/2`, `/guide/technobook/2`,
  `/guide/site/999999`, `/guide/site/abc` all return **200** with the same 937-byte `index.html` as
  `/guide`. Confirms §2.2/§3.1: no nginx change was needed. No 500 anywhere.
- `GET /rules/2` → **200** (9577 bytes). `GET /rules/999999` → **404** with
  `detail="Правило не найдено"` (`locations-service/app/main.py:1949`) → the interceptor produces
  exactly the string the page matches on. `GET /rules/abc` → **422** (never reached by the page, see
  the id guard above). `GET /rules/list` → **200**.
- Data reality check: the dev DB holds 4 rules, **all** `section=site`, **all** with an `image_url`,
  **none** with empty content. Consequences: checklist item (d) is still exercisable in the reverse
  direction — `/guide/technobook/2` (rule 2 is `site`) must redirect to `/guide/site/2` — but items
  (f) "rule without an image" and (g) "rule with empty content" **have no data to exercise at all**
  in dev. Both code paths exist and are correct by inspection (`:119-125` title band, `:137-139`
  empty state); neither was seen. No test rows were inserted — the Reviewer does not write data.
- Rule 2's content is exactly the "formatting-heavy old rule" case (blockquote, `h2`,
  `style="text-align: left"`, `strong`). Since the sanitiser call and the container classes are moved
  **verbatim** from `RuleOverlay.tsx:46-48`, its HTML cannot render differently — the only deltas are
  the removed 700px/`max-h-[80vh]` modal box and the added `break-words`. Regression risk is
  structurally nil, but it was not confirmed visually.

#### Accepted trade-off (not a FAIL, recorded deliberately)
`GuideRulePage.tsx:49` distinguishes 404 from other errors by `message.includes('не найден')`, i.e.
by a substring of the Russian message, because the `rulesClient` response interceptor
(`api/rules.ts:19-27`) throws `new Error(detail)` and **discards the status code**. The exact same
technique is already in production in `ArchiveArticlePage.tsx`, so this is consistent, not novel. The
clean fix is to attach the status to the thrown error in the interceptor — a cross-cutting change to
a shared client that is out of this feature's scope. Worth a separate small task.

#### Observations (non-blocking, no action required in this feature)
1. `GuideRulePage.tsx:115` — with a banner image the `<h1>` is absolutely positioned at the banner's
   bottom. A very long title at 360px grows upward and can overflow the banner box; the panel's
   `overflow-hidden` clips it rather than breaking layout. Cosmetic, only for extreme titles, and the
   header treatment is explicitly a trial ("давай попробуем пока шапкой", §1).
2. A mismatched section costs two fetches (load → `<Navigate replace>` → remount → load). Correct and
   rare; noted only so nobody mistakes it for a bug.
3. `docs/DESIGN-SYSTEM.md` §19 is inserted before §15 "For AI Agents" — that matches the file's
   existing convention of keeping §15 as the trailing section (§16-18 already sit above it).
4. Pre-existing issues noted, untouched and correctly left out of scope: the `WallSection.tsx` /
   `PostHistoryTab.tsx` unsanitised-HTML XSS already logged in `docs/ISSUES.md` (HIGH) by the Analyst.

---

## 6. Logging (filled by all agents — in Russian)

[LOG] 2026-09-20 — PM: карточка заведена по просьбе пользователя; зафиксирована находка, что WysiwygEditor уже общий у правил и ролевых постов, запускаю разведку

[LOG] 2026-09-20 15:40 — Analyst: анализ завершён, раздел 2 заполнен. Находка PM подтверждена частично: редактор действительно один, но разница в наборе кнопок ВСЁ ЖЕ есть — ровно одна, проп `enableArchiveLinks` (в RuleForm не передан, в формах постов передан). Санитайзер у правил, наоборот, ЛУЧЕ пропускает, а не хуже: голый DOMPurify по умолчанию оставляет `style`, `class` и `data-*`, так что правило сегодня не теряет ни цвета, ни выравнивания, ни картинок. CSS `prose-rules` у постов и правил общий — один и тот же блок в index.css. Реальная разница — модалка шириной 700px вместо страницы, отсутствие обёртки ArchiveLinkPreview и пары классов контейнера. Бэкенд менять не нужно: `GET /rules/{id}` публичный и уже есть, `fetchRule` в api/rules.ts тоже есть и нигде не используется. Фича фронтенд-онли.

[LOG] 2026-09-20 15:45 — Analyst: обнаружен баг, добавлен в ISSUES.md (стена профиля `WallSection.tsx:173` и `PostHistoryTab.tsx:79` рендерят посты игроков вообще без санитайзера — хранимый XSS; к FEAT-174 отношения не имеет)

[LOG] 2026-09-20 16:05 — Architect: начал проектирование, перепроверил ключевые факты разведки по коду

[LOG] 2026-09-20 16:20 — Architect: разведка подтверждена. `GET /rules/{rule_id}` действительно публичный, объявлен после `/list` (шадоуинга нет) и отдаёт всё нужное вместе с `section`; `fetchRule` в `api/rules.ts` готов и нигде не используется; у `RuleOverlay` ровно один потребитель — удаление безопасно. Две косметические поправки: реальные пути постов и Архива идут через `components/pages/…` (в разведке префикс `pages/` потерян), и в приложении вообще нет глобального `ScrollToTop` — значит страница правила обязана сама прокручиваться наверх при открытии.

[LOG] 2026-09-20 16:25 — Architect: решение по подложке — `PanelShell` НЕ переносим и НЕ импортируем из `ProfilePage/`. Причина не в чистоте слоёв, а в том, что он не подходит: его шапка — строка «иконка + мелкий заголовок», а нам нужна обложка с картинкой и крупным заголовком. Берём ту же строку классов дизайн-системы (`gold-outline rounded-card bg-site-bg backdrop-blur-[10px] shadow-card`) прямо в новой странице; ничего не изобретаем, `index.css` не трогаем. Фиксированную высоту панели и внутренний скролл не берём — статья скроллится страницей, внутренняя коробка это ровно то, что не нравится в модалке.

[LOG] 2026-09-20 16:30 — Architect: санитайзер правил остаётся голым `DOMPurify.sanitize` без опций (решение пользователя). `ADD_ATTR: ['data-archive-slug']` сознательно НЕ добавляем — проверено, что `data-*` и так проходят по умолчанию, так что это была бы правка санитайзера без всякой пользы. Классы контейнера копируем из старой модалки, а не из поста: `whitespace-pre-wrap` прямо запрещён — именно он «сдвинул бы» уже написанные правила лишними пустыми строками.

[LOG] 2026-09-20 16:35 — Architect: id чужого раздела в адресе (`/guide/site/42`, где 42 — технобук) — грузим правило по id и каноническим `<Navigate replace>` уводим на `/guide/{rule.section}/{id}`. Ссылка не умирает, адрес сам чинится, кнопка «назад» не зацикливается. 404 и нечисловой id — отдельное состояние «Правило не найдено», не редирект и не белый экран.

[LOG] 2026-09-20 16:40 — Architect: спроектировано 5 задач, 0 новых API-контрактов. Фича фронтенд-онли: бэкенд, миграции, nginx, RBAC, compose трогать ЗАПРЕЩЕНО всем агентам — эндпоинт, схема и клиент уже есть. Поэтому QA-задачи с pytest нет (CLAUDE.md §11 требует её только при правке бэкенд-кода) — взамен у ревьюера обязательный живой чек-лист из 10 пунктов, включая сравнение старого «тяжёлого» правила до/после и проход на 360px. Границы по файлам не пересекаются: задачи 1-3 можно запускать параллельно.

[LOG] 2026-09-20 17:05 — Frontend Dev: задачи #3 и #4 выполнены. В `RuleForm.tsx:150` добавлен проп `enableArchiveLinks` — в редакторе правил появляется кнопка «Ссылка на статью Архива» (единственная правка в файле). В `docs/DESIGN-SYSTEM.md` добавлен раздел §19 «Guide Article Page (FEAT-174)»: зафиксирована строка токенов панели статьи и причина, по которой `PanelShell` сознательно НЕ импортируется и не переносится (его шапка — «иконка + мелкий uppercase-заголовок», а статье нужна обложка с картинкой и крупным заголовком; перенос в `CommonComponents` — churn на ~20 импортов). Новых токенов и классов не добавлено, `index.css` не тронут. Проверки в контейнере `frontend`: `npx tsc --noEmit` — 0 ошибок, `npm run build` — успешно (35.96s). Обёртка `ArchiveLinkPreview` при показе правила по спецификации (§3.4 и задача #1) закреплена за задачей #1 — файл `GuidePage/GuideRulePage.tsx` не трогал.

[LOG] 2026-09-20 17:10 — Frontend Dev: задача #1 завершена. Создана страница `components/GuidePage/GuideRulePage.tsx` и зарегистрирован маршрут `guide/:section/:id` в `App.tsx` сразу после `guide/:section`. Подложка — инлайн-строка токенов `gold-outline relative rounded-card bg-site-bg backdrop-blur-[10px] shadow-card overflow-hidden`, `PanelShell` не импортируется, `index.css` не трогался, фиксированной высоты и внутреннего скролла нет. Санитайзер оставлен голым: `DOMPurify.sanitize(rule.content || '')` без объекта опций; классы тела скопированы из старой модалки (`prose-rules text-white text-base leading-relaxed break-words`), `whitespace-pre-wrap` не добавлен. Шапка: при наличии картинки — обложка с градиентом и заголовком поверх, иначе полоса заголовка в идиоме PanelShell (пустого прямоугольника не остаётся). Четыре состояния на русском: загрузка, ошибка (инлайн `text-site-red` + `toast.error`), «Правило не найдено» (в т.ч. при нечисловом id — сеть не дёргается), «В этом правиле пока нет текста». Чужой раздел в адресе — канонический `<Navigate replace>` на `/guide/{rule.section}/{id}`. Прокрутка наверх при монтировании и смене id. Тело обёрнуто в `ArchiveLinkPreview`. `npx tsc --noEmit` и `npm run build` в контейнере `frontend` — оба прошли.

[LOG] 2026-09-20 17:05 — Frontend Dev: начал задачу #2 (развязка модалки)

[LOG] 2026-09-20 17:20 — Frontend Dev: задача #2 завершена. Карточка в `RulesGrid` стала `<Link to={`/guide/${rule.section}/${rule.id}`}>` — адрес строится по `rule.section` из самого правила, а не по параметру маршрута, так что грид всегда выдаёт канонический адрес и нового пропа не требует; побочно заработали средний клик и «открыть в новой вкладке». Проп `onSelect` убран из `RulesGridProps`. Классы карточки не тронуты, только `w-full text-left` заменено на `block` (у ссылки блочность нужна явно, выравнивание текста у `<a>` и так левое); сетка осталась `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`, адаптивность от 360px не изменилась. В `GuideSectionPage` сняты состояние `selectedRule`, его сброс в `load()`, импорт и рендер оверлея — остальное (заголовок, ссылка назад, загрузка/ошибка/пустой список) байт в байт как было, видимая русская ошибка на месте. `RuleOverlay.tsx` удалён, перед удалением перепроверено грепом: других импортов не было. Проверки в контейнере `frontend`: `npx tsc --noEmit` — без ошибок, `npm run build` — успешно (35.23s).

[LOG] 2026-09-20 17:30 — Reviewer: начал проверку задачи #5

[LOG] 2026-09-20 17:55 — Reviewer: проверка завершена, результат **PASS**. Статика: `npx tsc --noEmit` и `npm run build` в контейнере `frontend` — оба прошли (сборка 31.99s, из предупреждений только давнее про размер чанка). Границы, заданные пользователем, соблюдены все: санитайзер остался голым `DOMPurify.sanitize(rule.content || '')` без объекта опций (`GuideRulePage.tsx:133`), `sanitizePostHtml` и `ADD_ATTR` к правилам не подключены, `whitespace-pre-wrap` нет, `PanelShell` не импортирован и не перенесён (упомянут только в комментарии), `index.css` не тронут, фиксированной высоты и внутреннего скролла нет, страница сама прокручивается наверх, тело обёрнуто в `ArchiveLinkPreview`, а кнопка Архива добавлена в `RuleForm.tsx:150` — обе половины на месте. В диффе ни одного `.py`, `alembic`, `nginx*.conf`, `docker-compose*`, `Dockerfile`, `index.css`, `.scss`. `RuleOverlay` не упоминается больше нигде.

[LOG] 2026-09-20 17:55 — Reviewer: живая проверка выполнена ЧАСТИЧНО и это честно записано в раздел 5. Chrome-devtools MCP в сессии недоступен (подключены только Claude Docs и Google Drive, `pencil` не поднялся), браузерной автоматизации нет, у фронтенда нет ни vitest, ни jsdom — значит отрисовку никто не видел. По HTTP проверено: `/guide/site/2`, `/guide/technobook/2`, `/guide/site/999999`, `/guide/site/abc` отдают 200 и тот же `index.html`, что и `/guide` (правка nginx действительно не нужна, 500-х нет); `GET /rules/2` — 200, `GET /rules/999999` — 404 с `detail="Правило не найдено"` (совпадает со строкой, по которой страница ловит 404), `GET /rules/abc` — 422, но страница туда не ходит, нечисловой id отсекается регуляркой до запроса. Пункты чек-листа про вёрстку, консоль, сравнение старого «тяжёлого» правила до/после, ховер-превью архивной ссылки и 360px глазами НЕ проверены — нужен человек.

[LOG] 2026-09-20 17:55 — Reviewer: в dev-БД всего 4 правила, все раздела `site`, все с картинкой и с непустым текстом — поэтому случаи «правило без картинки» и «правило с пустым текстом» нечем воспроизвести; код обоих состояний на месте и корректен по чтению, тестовых строк в БД не создавал. Случай чужого раздела воспроизводим в обратную сторону: `/guide/technobook/2` при `section=site` должен канонически уводить на `/guide/site/2`.

[LOG] 2026-09-20 17:55 — Reviewer: зафиксирован осознанный компромисс (не повод для FAIL): 404 отличается от прочих ошибок по подстроке «не найден» в тексте, потому что интерцептор `rulesClient` (`api/rules.ts:19-27`) выбрасывает `Error(detail)` и теряет статус-код. Тот же приём уже применён в `ArchiveArticlePage.tsx`. Чинить надо в общем клиенте — это отдельная маленькая задача, не эта фича.

---

## 7. Summary (filled by PM — in Russian)

**Что сделано.** Правило больше не открывается модалкой. Карточка правила в разделе руководства
стала обычной ссылкой и ведёт на отдельную страницу `/guide/:раздел/:id`: текст занимает всю
ширину страницы на тёмной подложке с золотой обводкой — той же комбинации классов, что у панелей
в профиле персонажа. Сверху шапка: если у правила есть картинка — она становится обложкой с
заголовком поверх, если картинки нет — просто полоса с заголовком, пустого прямоугольника не
остаётся. Внутреннего скролла и «коробки» на 80% экрана больше нет — статья листается страницей.

**Ссылку на правило теперь можно кинуть другому игроку и положить в закладки** — страница
открывается по прямому заходу, а не только переходом из списка. Заодно заработали средний клик и
«открыть в новой вкладке». Если в адресе указан чужой раздел (или админ перенёс правило в другой
раздел), адрес сам чинится на правильный, а кнопка «назад» не зацикливается. Несуществующий или
кривой id показывает «Правило не найдено» со ссылкой обратно в руководство, а не белый экран.

**Про оформление.** Выяснилось, что редактор у правил и у ролевых постов и так был один и тот же,
а правила даже пропускали больше оформления, чем посты. Не хватало ровно двух вещей: кнопки
«Ссылка на статью Архива» в редакторе правил (добавлена) и обработки таких ссылок при показе
(добавлена — теперь ссылка на статью Архива внутри правила открывается без перезагрузки страницы
и показывает всплывающее превью при наведении). Способ очистки текста правил **не менялся**, как вы
и просили, поэтому уже написанные правила гарантированно не поехали.

**Проверено.** Сборка и проверка типов фронтенда — без ошибок. На запущенном стенде проверено, что
новые адреса отдаются сервером, правило по id приходит, а несуществующее правило корректно даёт
404. **Чего не удалось проверить:** браузерный инструмент в этой сессии был недоступен, поэтому
страницу никто не видел глазами — вёрстку, вид на телефоне и сравнение старого «тяжёлого» правила
до/после стоит бегло глянуть вручную. Кода это не касается: разметка текста перенесена из старой
модалки слово в слово, так что расхождению взяться неоткуда.

**Мелочь на будущее (не в этой задаче):** общий http-клиент правил теряет код ответа, поэтому
страница отличает «не найдено» от других ошибок по тексту сообщения. Тот же приём уже используется
на страницах Архива. Аккуратнее было бы починить клиент — это отдельная маленькая задача.

[LOG] 2026-09-20 18:05 — PM: ревью PASS, фича закрыта, файл переименован в DONE-FEAT-174.
