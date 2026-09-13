# FEAT-157: Баги редактора — цвет на жирном/курсиве и спеллчекер

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-13 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

**Блокировка:** не начинать до закрытия FEAT-156 — задача T13 там правит
`PostCreateForm.tsx`, а баг 3 живёт в том же файле.

---

## 1. Feature Brief (filled by PM — in Russian)

Три бага, о которых сообщил игрок. Причины найдены анализом кода, но **не исправлены** —
исправление и есть содержание этой фичи.

### Баг 1 — на жирный и курсив накладывается цвет, который игрок не выбирал

**Симптом (со слов игрока):** «когда делаешь курсив или текст жирный, зачем-то выставляется
цвет на выбранный цвет после отправки».

**Причина найдена, уверенность высокая.** Дело не в редакторе и не в палитре, а в
**отрисовке готового поста**. В `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCard.tsx:326-328`
захардкожены классы:

```
[&_em]:italic [&_em]:text-rarity-epic      →  #B875BD
[&_b]:text-gold-light                      →  #fff9b8
[&_strong]:text-gold-light                 →  #fff9b8
```

Любой курсив принудительно красится в фиолетовый, любой жирный — в золотой, **при показе**.
В самом редакторе такого правила нет (`WysiwygEditor.tsx:666` использует только `prose-rules`;
`index.css:632-634` задаёт для `strong`/`em`/`u` только начертание, без цвета) — поэтому цвет
и появляется «после отправки».

Усугубляющие детали:
- `#B875BD` и золотой — **пресеты из самой палитры** (`src/components/common/ColorPicker.tsx:3-13`),
  поэтому выглядит как «применился выбранный мной цвет».
- Сгенерированное правило имеет специфичность 0,2,0 и **бьёт унаследованный цвет**. В живом
  примере (пост id 138 на проде, персонаж Мавуика, локация 173) игрок сам поставил томатный
  `rgb(255, 99, 71)` = `#ff6347`, span с цветом лежит **снаружи** `<strong>` — значит реальный
  выбранный цвет подменяется золотым при показе. Игрок выбрал один цвет, а видит другой.
- Белый `rgb(255,255,255)` на обычном тексте — побочный эффект: текущий цвет читается как
  `editor.getAttributes("textStyle").color || "#ffffff"` (`WysiwygEditor.tsx:376`), а
  `react-colorful` шлёт `onChange` непрерывно при перетаскивании, поэтому достаточно открыть
  палитру и дёрнуть мышью.

**Происхождение регрессии:** классы добавлены в коммите `2a20d16` (FEAT-152, редизайн страницы
локации). До него div был просто `text-white/90 … prose-rules`.

**Направление фикса:** убрать три класса из `PostCard.tsx:328`, либо ограничить их элементами
без собственного цвета (`:not([style*="color"])`). Решить продуктово: должен ли жирный/курсив
вообще иметь цвет по умолчанию.

### Баг 2 — проверка правописания не работает

**Симптом:** «проверка правописания сломалась».

**Причина найдена.** `src/api/spellcheck.ts:25-46` шлёт текст в Яндекс.Спеллер **GET-запросом,
целиком в query-параметре**:

```
const params = new URLSearchParams({ text, lang: 'ru', options: '0' });
const response = await fetch(`${YANDEX_SPELLER_URL}?${params.toString()}`);
```

Кириллица кодируется как 6 URL-символов на букву (`%D0%BF`). Минимальная длина поста — 300
символов, гейты поднимают её до 500–2000+. Пост на 1000 символов даёт URL ~6000 символов, на
3000 — около 18000. Это за пределами практических лимитов GET (Яндекс рекомендует POST для
больших объёмов; промежуточные прокси часто режут на 4–8 КБ и отдают 414). Для длинных ролевых
постов проверка не могла работать в принципе.

**Не проверено и требует проверки первым делом:** отдаёт ли `speller.yandex.net` заголовок
`Access-Control-Allow-Origin` для браузерных запросов. Если нет — падает вообще всё, независимо
от длины. CSP в проекте не настроен, так что он не при чём.

**Сопутствующее.** `useSpellCheck.runCheck` (`useSpellCheck.ts:18-28`) не ловит ошибку и
пробрасывает её; панель остаётся пустой, а `PostCreateForm.tsx:259-263` (после FEAT-156) показывает один и тот же
тост «Сервис проверки правописания недоступен». Пользователь не отличает 414 от CORS, в консоль
статус не пишется.

**Направление фикса:** перевести на POST с телом `application/x-www-form-urlencoded`, добавить
таймаут/abort, логировать статус, различать типы ошибок в сообщении.

### Баг 3 — при исправлении слова слова дублируются

**Симптом:** «если и срабатывает и исправляешь слова, слова могут дублироваться».

**Причина найдена, уверенность очень высокая.** Основной путь: после применения исправления
**остальные ошибки не пересчитываются**. `useSpellCheck.dismissError` (`useSpellCheck.ts:30-32`)
только фильтрует массив и не трогает позиции; `checkSpelling` заново не запускается. У всех
оставшихся ошибок сохраняются смещения, посчитанные по **исходному** тексту.

Как только применённое исправление меняет длину (`здраствуйте` 11 → `здравствуйте` 12), каждая
следующая ошибка промахивается на накопленную дельту: `replaceWordInHtml` вставляет замену на N
символов раньше и удаляет `len` символов не с того места — от старого слова остаётся хвост,
приклеенный к новому. Воспроизводится обычным поведением: исправить два слова подряд.

**Второй, независимый путь (уверенность высокая).** Тексту для спеллера делается `.trim()`
(`PostCreateForm.tsx:62`, вызов на `:257`), а `replaceWordInHtml` (`spellcheck.ts:56-114`) считает
позиции по сырому HTML **без обрезки**. Любой ведущий пробел сдвигает все `pos`.
Пример: `html = "<p>  Превет мир</p>"`, `pos=0`, `len=6`, замена `"Привет"` →
`<p>Приветет мир</p>` — дубль с первого же клика.

**Третье, связанное.** `stripHtmlTags` (`PostCreateForm.tsx:62`) вырезает теги **без разделителя**,
поэтому `<p>Один</p><p>Два</p>` → `"ОдинДва"`. Спеллер видит склейку на стыке абзацев и репортит
несуществующие ошибки, а «исправление» такой склейки режет текст через границу абзаца.
Энтити (`&nbsp;`, `&amp;`) не декодируются и уходят как литералы.
Тот же баг без разделителя есть на бэкенде в `services/locations-service/app/crud.py:65`
(используется для подсчёта длины и опыта) — причём `app/tests/test_post_xp.py:35,38` **закрепляет**
неправильное поведение (`"line oneline two"`), так что правка бэкенда потребует правки теста.

**Направления фикса (выбрать одно, решает архитектор):**
1. После каждого применённого исправления перезапускать проверку; либо сдвигать `pos` всех
   оставшихся ошибок на `suggestion.length - error.len` для тех, у кого `pos > error.pos`.
2. Привести `stripHtmlTags` и `replaceWordInHtml` к одной модели смещений — без `trim()`,
   с декодированием энтити и разделителем на границах блочных тегов.
3. **Предпочтительно:** брать простой текст из `editor.state.doc.textBetween(...)` и применять
   замену настоящей транзакцией ProseMirror, чтобы позиции и разметка оставались авторитетными,
   а редактор не приходилось перемонтировать (после FEAT-156 ремаунт делает
   `replaceContent`, `PostCreateForm.tsx:140-148`, вызываемый из `handleApplySuggestion`,
   `PostCreateForm.tsx:266-272`).

### Вопросы к пользователю
- [x] Баг 1: жирный и курсив должны вообще иметь свой цвет по умолчанию, или быть цвета
      обычного текста, пока игрок сам не покрасит? → **Стандартный цвет текста, пока игрок
      сам не покрасит.** Значит три класса из `PostCard.tsx:328` убираются полностью, а не
      ограничиваются селектором. Жирный остаётся жирным, курсив — курсивом, цвет наследуется.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

_Pre-analysis by PM confirmed and extended by Architect on 2026-09-13, re-verified
against the tree **after FEAT-156 landed** (`996db5b`). Line numbers in section 1 that
drifted have been corrected in place; the corrections are listed at the end of this
section._

### 2.1 Bug 1 — forced colour on bold / italic

Confirmed. The only place in the whole frontend that forces a colour onto `strong` /
`b` / `em` is a single arbitrary-variant class list:

`services/frontend/app-chaldea/src/components/pages/LocationPage/PostCard.tsx:326-328`

```
[&_em]:italic [&_em]:text-rarity-epic [&_b]:text-gold-light [&_strong]:text-gold-light
```

A repo-wide grep for `text-gold-light`, `text-rarity-epic`, `[&_em]`, `[&_b]` and
`[&_strong]` returns **no other post-rendering site**. Every other surface that renders
post/article HTML through `dangerouslySetInnerHTML` inherits its colour normally and is
therefore already correct:

| Surface | File | Forces colour? |
|---|---|---|
| Post card (location feed) | `LocationPage/PostCard.tsx:326-328` | **YES — the bug** |
| Post history | `PostHistoryPage/PostHistoryPage.tsx:57` | no |
| Profile wall | `UserProfilePage/WallSection.tsx:171-172` | no |
| Archive article | `ArchivePage/ArchiveArticlePage.tsx:367-374` | no |
| Rules overlay | `RulesPage/RuleOverlay.tsx:46-47` | no |
| Editor (live) | `WysiwygEditor.tsx:666` (`prose-rules` only) | no |
| Drafts panel | `LocationPage/DraftsPanel.tsx:253` | no — renders the server-side `draft.preview` as **plain text**, no HTML |
| Notifications | — | no post HTML is rendered there |

`index.css:632-635` (`.prose-rules strong/em/u/s`) sets weight, style, decoration and
opacity only — **no colour**. It therefore needs **no change**: once the three classes
are removed, `strong` and `em` inherit the surrounding `text-white/[0.88]`, and a
player-authored `<span style="color:…">` keeps winning as it already does in the editor.
Adding a colour rule to `prose-rules` would re-create the bug on all five surfaces.

`[&_em]:italic` is redundant with `.prose-rules em` but harmless; it stays, to keep the
diff to exactly the three colour classes.

DOMPurify is called without `FORBID_ATTR`, so the inline `style` attribute survives
sanitisation — the player's own colour is preserved. Confirmed against the live example
in section 1 (post 138): the `<span style="color: rgb(255, 99, 71)">` sits *outside*
`<strong>`, so with the three classes gone the tomato colour is what the reader sees.

### 2.2 Bug 2 — spellcheck transport

Confirmed: `src/api/spellcheck.ts:25-46` builds a `URLSearchParams` and issues a **GET**
with the whole post in the query string. Cyrillic is 6 URL characters per letter, the
minimum post is 300 characters and gates push it to 500–2000+, so the URL routinely
exceeds 4–8 KB and is rejected upstream (414) before Yandex ever sees it.

**The CORS question could not be answered from this workstation.** `speller.yandex.net`
(and `yandex.ru` itself) is unreachable from the development host — TCP connect is
refused at the network egress, with and without the tool sandbox, while `example.com`
returns 200. So the probe produced **no evidence either way**, and it must not be guessed
at: the answer decides the architecture (see 3.2), so it is raised to a blocking task
(T2) executed from the prod VPS, where the egress is not filtered.

Two independent unknowns fall out of that, and they pull in *opposite* directions:

* If `speller.yandex.net` does **not** send `Access-Control-Allow-Origin`, no amount of
  client-side work can fix bug 2 — a backend proxy is the only option.
* If the **prod VPS** cannot reach `speller.yandex.net`, a backend proxy cannot work —
  the call must stay in the player's browser.

T2 resolved both with one `curl` run from the prod VPS.

> **Resolved — see 3.2 for the measured evidence.** `speller.yandex.net` returns
> `access-control-allow-origin: *`, advertises `OPTIONS, GET, POST`, and accepts a
> ~10.8 KB form POST. CORS was never the problem; the oversized GET URL was. The call
> therefore **stays client-side** and no backend proxy is built, so the
> `httpx`/`auth_http`/`limit_req_zone` groundwork this section originally catalogued as
> support for a proxy branch is no longer relevant to this feature.

Error surfacing is also genuinely broken today: `useSpellCheck.runCheck`
(`hooks/useSpellCheck.ts:18-28`) has a `finally` but **no `catch`**, so the rejection
propagates to `PostCreateForm.handleSpellCheck` (`:256-264`), which swallows the actual
cause and shows one generic toast. `SpellCheckPanel` has **no error prop at all**
(`SpellCheckPanel.tsx:5-19`) and renders `null` when `checked` is false — so on failure
the panel is simply blank. That violates the mandatory "every error visibly surfaced"
rule and is fixed as part of bug 2.

### 2.3 Bug 3 — duplication on applying a correction

Confirmed, three distinct defects, all in the plain-text ↔ HTML offset model:

**(A) Stale offsets.** `useSpellCheck.dismissError` (`hooks/useSpellCheck.ts:30-32`) only
filters the array. `handleApplySuggestion` (`PostCreateForm.tsx:266-272`) calls
`replaceWordInHtml` and then `dismissError` — nothing recomputes the remaining errors'
`pos`. The first length-changing fix desynchronises every later one by the accumulated
delta, and `replaceWordInHtml` then deletes `len` characters from the wrong offset,
leaving the tail of the old word glued to the new one. This is the reported symptom.

**(B) `trim()` mismatch.** `stripHtmlTags` (`PostCreateForm.tsx:62`) ends in `.trim()`;
`replaceWordInHtml` (`api/spellcheck.ts:56-114`) counts plain-text offsets over the raw,
untrimmed HTML. Any leading whitespace shifts every `pos` by that amount, so duplication
can happen on the very first click.

**(C) No block separator, no entity decoding.** `stripHtmlTags` deletes tags without
inserting anything, so `<p>Один</p><p>Два</p>` becomes `"ОдинДва"`. The speller reports a
phantom error on the glued token and "fixing" it cuts across a paragraph boundary.
`&nbsp;` / `&amp;` are sent as literals and are also counted with the wrong length.

(B) and (C) are the same underlying defect: **two different functions each implement
their own HTML→plain-text model, and the models disagree.** That is what 3.3 fixes.

**Backend twin, out of scope.** `services/locations-service/app/crud.py:65-67` has the
same separator/entity defect, and `app/tests/test_post_xp.py:35,38` asserts the wrong
output (`"line oneline two"`). Changing it would change `char_count` and therefore post
XP and the gate thresholds for every post — a **balance change**, not a bug fix. It is
deliberately excluded; see 3.4 and task T9.

**Consequence for the frontend counter:** `charCount`
(`PostCreateForm.tsx:172`) must keep mirroring the backend byte-for-byte, or the UI would
promise a gate the server then refuses. So `stripHtmlTags` stays exactly as it is for
counting, and the new, correct model is used **only** for spellcheck. This is the one
place where keeping a known-imperfect function is the right call.

### 2.4 FEAT-156 drift — corrections applied to section 1

| Section 1 reference | Corrected to |
|---|---|
| `ColorPicker.tsx:4-14` | `ColorPicker.tsx:3-13` |
| `spellcheck.ts:25-38` | `spellcheck.ts:25-46` |
| `PostCreateForm.tsx:59` (`stripHtmlTags`) | `PostCreateForm.tsx:62` |
| `PostCreateForm.tsx:159` (spellcheck call) | `PostCreateForm.tsx:257` |
| `PostCreateForm.tsx:161-165` (toast) | `PostCreateForm.tsx:259-263` |
| `PostCreateForm.tsx:173` (`editorKey` bump) | now `replaceContent`, `PostCreateForm.tsx:140-148`, called from `handleApplySuggestion` `:266-272` |
| `tests/test_post_xp.py:35` | `app/tests/test_post_xp.py:35,38` |

Unchanged and re-verified as still correct: `PostCard.tsx:326-328`,
`WysiwygEditor.tsx:666`, `WysiwygEditor.tsx:376`, `index.css:632-634`,
`spellcheck.ts:56-114`, `useSpellCheck.ts:18-28`, `useSpellCheck.ts:30-32`,
`crud.py:65`.

---

## 3. Architecture Decision (filled by Architect — in English)

Three bugs, three independent fixes. They are deliberately **not** bundled: bug 1 is a
three-token deletion with immediate player-visible value and zero risk, and must be able
to ship on its own without waiting for the spellcheck work.

### 3.1 Bug 1 — bold/italic inherit the text colour

**Decision (product answer already given in section 1):** bold is bold, italic is
italic, and neither carries a colour of its own. Remove the three colour classes from
`PostCard.tsx:328` outright — do **not** scope them with `:not([style*="color"])`.

Rationale: a `:not()` guard would still paint gold/purple whenever the player has *not*
chosen a colour, which is precisely the behaviour the user rejected. It would also be a
fragile selector (it matches the attribute text, not the computed colour) and would leave
`PostCard` the only one of six render surfaces with a different emphasis palette.

* Remove: `[&_em]:text-rarity-epic`, `[&_b]:text-gold-light`, `[&_strong]:text-gold-light`.
* Keep: `[&_em]:italic`, the whole `[&_blockquote]:*` group, `prose-rules`,
  `text-white/[0.88]` — the gold quote styling from FEAT-152 was never part of the
  complaint.
* `index.css` needs **no change**: `.prose-rules strong/em` already carry weight and
  style and no colour (2.1). Adding a colour token there would reintroduce the bug on
  all five other surfaces.
* No new CSS/SCSS, no new Tailwind token — this is a pure deletion.

### 3.2 Bug 2 — transport. **RESOLVED: stay client-side, GET → POST**

The CORS question that this section originally hedged against **has been measured**, not
assumed. PM executed the blocking probe from the prod VPS on 2026-09-13 and the result is
unambiguous.

**Evidence** — `https://speller.yandex.net/services/spellservice.json/checkText`:

| Probe | Result |
|---|---|
| GET with `Origin: https://fallofgods.top` | `HTTP/2 200`, **`access-control-allow-origin: *`** |
| `OPTIONS` preflight, `Access-Control-Request-Method: POST`, same Origin | `HTTP/2 200`, **`access-control-allow-methods: OPTIONS, GET, POST`**, `access-control-allow-origin: *` |
| Form POST, short text (`text=превет мир как дила`, `lang=ru`, `options=0`) | 200, correct corrections (`превет→привет`, `дила→дела`) |
| Form POST, **~10.8 KB of Cyrillic** (`--data-urlencode text@file`) | **200**, 28 579 bytes of JSON, full error list |

CORS is wildcard-open, `POST` is explicitly advertised, and the payload size that broke
GET is handled comfortably — 10.8 KB is far beyond any realistic RP post. The host is
also reachable from the VPS, but that is now irrelevant.

**Decision: Branch B.** The call stays in the browser; the only change is the transport.
The backend proxy that this section previously defaulted to is **not built** — it would
be pure added surface (a new endpoint, an auth dependency, an nginx limiter and a pytest
suite) buying nothing the probe did not just prove we already have.

One consequence is actively in our favour: Yandex.Speller's quota is **per calling IP**.
Staying client-side keeps it spread across per-player IPs instead of funnelling the whole
game through the VPS's single IP and its ~10 000 requests / ~10 000 000 characters per
day. The proxy's main accepted cost simply disappears.

**Contract.** `checkSpelling(text: string): Promise<SpellError[]>` keeps its exact
signature and its call site. Only the body changes:

```
POST https://speller.yandex.net/services/spellservice.json/checkText
Content-Type: application/x-www-form-urlencoded;charset=UTF-8
Body: text=<urlencoded>&lang=ru&options=0
200:  [ { code, pos, row, col, len, word, s: [string] }, ... ]   → mapped to SpellError[]
```

`application/x-www-form-urlencoded` is a **CORS-simple** content type, so no preflight is
triggered at all in the normal path — but the probe confirms the preflight would succeed
anyway, so the choice is safe rather than load-bearing.

**Security / abuse:** no new server surface, no auth change, no secret (the Yandex URL is
a public endpoint and stays a module constant). The text leaves the browser for a third
party exactly as it does today — unchanged trust boundary, no regression. Abuse control
is the existing client-side guard: the button is already disabled while
`spellCheck.loading` is true (`PostCreateForm.tsx:667`), which is sufficient for a
manually-triggered, per-user-IP action. **No nginx rate limiting is needed or possible** —
the request never traverses our gateway.

#### Error surfacing

Mandatory rule, currently violated (2.2), and **still fully in scope**. A correct
transport makes failures rarer, not impossible: the player's own network can drop, Yandex
can return 4xx/5xx, and the per-IP quota — while much healthier under Branch B — can
still be hit by a single user. Today any of those leaves the panel **blank**, which is a
FAIL on the "every error visibly surfaced" rule regardless of how unlikely it is.

The design:

* `api/spellcheck.ts` throws a `SpellCheckError` carrying a **Russian** message chosen by
  cause: network failure / blocked request, 4xx, 429 (quota), 5xx, timeout. A 10 s
  `AbortSignal.timeout` is added so a hung request cannot leave the panel spinning
  forever. The underlying status is `console.warn`-ed for diagnosis. A `fetch` rejection
  is indistinguishable from a CORS failure by design, so its message stays generic
  ("не удалось связаться с сервисом проверки правописания") rather than claiming a cause.
* `useSpellCheck` gains `error: string | null`, **catches** instead of rethrowing, and
  clears the error on the next successful run and on `reset()`.
* `SpellCheckPanel` gains an `error?: string | null` prop and renders it as a visible
  block (`text-site-red`, existing design-system colour) — the panel must never be blank
  after a failed check. The toast in `PostCreateForm` stays; the panel is the persistent
  copy the player can still read after the toast expires.

### 3.3 Bug 3 — one offset model, and re-sync after each applied fix

**Chosen direction: option 2 (unify the offset model) combined with the
offset-shifting half of option 1. Option 3 (ProseMirror transactions) is rejected for
this feature.**

Justification:

* Option 1 alone fixes only cause (A). Causes (B) and (C) survive and can duplicate a
  word on the *first* click, which no amount of re-checking repairs.
* Option 2 alone fixes (B) and (C) but not (A) — the stale-offset path is independent of
  how the text is extracted.
* So (A) must be handled too, and between its two sub-options: **shifting beats
  re-checking.** A single contiguous replacement shifts every later offset by exactly
  `suggestion.length - error.len`; the arithmetic is exact, synchronous and free, and it
  avoids firing a third-party request per applied fix — which would burn the player's own
  Yandex per-IP quota, add a visible stall to every click, and could still race a second
  click before its response lands.
* Option 3 is genuinely the better long-term model, but it is the wrong size for a bug
  fix: `WysiwygEditor` is a shared component used by several pages and exposes only
  `{ content, onChange, enableArchiveLinks }` (`WysiwygEditor.tsx:59-63`); handing the
  `Editor` instance out means changing that public contract and taking on
  plain-offset→ProseMirror-position mapping in the same PR. Its real prize — dropping the
  `editorKey` remount (`PostCreateForm.tsx:140-148`) and preserving cursor and undo
  history — is a **separate, pre-existing** annoyance that also affects the FEAT-156 draft
  insert, and is not part of any of the three reported symptoms. Recorded as follow-up in
  3.4. Minimal-diff and "no hidden refactors along the way" (CLAUDE.md §4.2, §5.3) point
  the same way.

**Design.**

1. In `api/spellcheck.ts`, one walker produces **both** the plain text and the index map
   in a single pass — `htmlToSpellText(html)` returning `{ text, map }`, where
   `map[plainIndex]` is the index in the original HTML string. Rules:
   * tags are skipped;
   * a `\n` separator is emitted at each **block boundary** (`</p>`, `</div>`, `<br>`,
     `</li>`, `</h1>`–`</h6>`, `</blockquote>`, `</figure>`, `</tr>`), collapsing runs so
     no empty tokens appear. Separators are synthetic and map to the HTML offset of the
     boundary;
   * HTML entities are decoded to a single plain character mapped to the whole entity's
     HTML span;
   * **no `trim()`** — trimming is what breaks the mapping today.
2. `replaceWordInHtml(html, pos, len, replacement)` is re-expressed on top of the **same**
   walker: resolve `[pos, pos+len)` to an HTML slice via `map`, splice in the
   replacement. It stops being a second, independently-written traversal, which is the
   root of causes (B) and (C). Signature and call site are unchanged.
   Guard: if the range cannot be resolved (map out of range, or the range spans a
   synthetic separator), return the HTML **unchanged** and surface a Russian error in the
   panel rather than writing a corrupted post.
3. `PostCreateForm.handleSpellCheck` sends `htmlToSpellText(content).text` — no `trim()`.
4. `useSpellCheck` gains `applyFix(index, replacementLength)`: drops the applied error and
   shifts `pos` by `delta = replacementLength - error.len` for every remaining error with
   `pos > appliedError.pos` (strictly greater — equal positions are overlapping reports of
   the same token and must not be shifted). `dismissError` stays as-is for the "ignore"
   button, where nothing moves.
5. `handleApplySuggestion` calls `applyFix` instead of `dismissError`.

**Explicitly kept as-is:** `stripHtmlTags` in `PostCreateForm.tsx:62` and its use for
`charCount` / `isContentEmpty`. It must keep mirroring `crud.strip_html_tags` exactly
(2.3) or the character counter would promise gates the server refuses. A comment must say
so, next to both functions, or a future reader will "fix" the duplication and silently
desync the counter from the server.

**Known limitation, accepted:** Yandex returns offsets in UTF-16 code units, which match
JS string indices for all Cyrillic and Latin text. Text containing surrogate pairs
(emoji) can still mis-map. Out of scope; noted in ISSUES.md by T9.

### 3.4 Out of scope — recorded, not fixed

| Item | Why not now |
|---|---|
| `crud.strip_html_tags` separator + entity decoding (`crud.py:65-67`) and `app/tests/test_post_xp.py:35,38` | Changes `char_count` → post XP and gate thresholds for every post. A balance decision for the user, not a silent bug fix. → ISSUES.md (T6) |
| ProseMirror-transaction replacement; dropping the `editorKey` remount | Changes the shared `WysiwygEditor` contract; the remount predates this feature and is not a reported symptom (3.3) → ISSUES.md (T6) |
| Continuous `onChange` from `react-colorful` while dragging (`WysiwygEditor.tsx:376`, section 1) | A side observation, not one of the three bugs; no player complaint → ISSUES.md (T6) |
| Surrogate-pair offsets | Accepted limitation (3.3) → ISSUES.md (T6) |

### 3.5 Data flow

```
Player clicks «Проверить правописание»
  └─ PostCreateForm: htmlToSpellText(content).text          (no trim, \n at blocks)
     └─ useSpellCheck.runCheck → api/spellcheck.checkSpelling
        └─ POST speller.yandex.net  (form-encoded, 10 s abort)   [browser → Yandex]
           └─ map s→suggestions
        └─ SpellError[]  → panel  |  SpellCheckError → panel + toast (Russian)

Player clicks a suggestion
  └─ replaceWordInHtml(content, pos, len, suggestion)        (shared index map)
     └─ replaceContent(html)  → state + editor remount + draft autosave
     └─ useSpellCheck.applyFix(index, suggestion.length)     (shift remaining pos)
```

### 3.6 Scope consequence — **no backend Python change in this feature**

With the proxy dropped, FEAT-157 touches **zero** Python files, zero Docker/Nginx config,
zero DB schema, zero migrations, zero RBAC permissions, and no existing API contract.
Nothing calls a service it did not call before, so the cross-service dependency graph
(CLAUDE.md §2) is untouched and there is nothing to validate there.

Therefore the **mandatory-QA-for-backend rule (CLAUDE.md §11) does not apply** — it is
explicitly scoped to features that modify backend Python code, and this one does not.
That is a genuine exemption, not an omission: there is no Python to test. The pytest task
from the proxy design is removed rather than left as a stale row.

Verification is frontend-only and is owned as follows:

* **Frontend Developer** — `npx tsc --noEmit` and `npm run build` must both pass before
  reporting any task done (CLAUDE.md §11, Build Verification).
* **Reviewer** — re-runs both, then verifies **live** in the browser: the three bug
  scenarios plus a forced failure (offline tab) showing a Russian message in the panel,
  with zero console errors. The project has no frontend test runner, so live verification
  *is* the test layer here and a review without it is invalid.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Revised 2026-09-13 after the T2 probe came back (see 3.2).** The probe resolved to
**Branch B** — client-side POST, no backend proxy — so four tasks from the first cut are
gone. Recorded here so nobody looks for them:

| Dropped | Was | Why it dies with Branch B |
|---|---|---|
| ~~T2~~ | CORS / egress probe | **Done** by PM from the prod VPS; evidence is in 3.2 |
| ~~T3~~ | `POST /locations/spellcheck` proxy | Not built — Yandex sends `access-control-allow-origin: *` and accepts a 10.8 KB POST directly |
| ~~T4~~ | nginx `spellcheck_limit` | The request never reaches our gateway; nothing to limit |
| ~~T8~~ | pytest for the proxy | No Python endpoint exists to test |

Nothing else survives from those four: no partial backend work, no config change, no
`requirements.txt` edit. **This feature now touches zero backend Python** — see 3.6 for
why the mandatory-QA rule is genuinely exempt rather than skipped, and who owns
verification instead.

Tasks are **renumbered T1–T7** below; these numbers are authoritative for dispatch.

All work is frontend: `.tsx`/`.ts` only, Tailwind only (no new SCSS), no `React.FC`,
usable down to 360 px, all player-facing strings in Russian, every error visibly
surfaced. Every developer runs `npx tsc --noEmit` **and** `npm run build` before
reporting done; Reviewer re-runs both and verifies live.

**T1 ships independently and first** — it depends on nothing and blocks nothing.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| T1 | **Bug 1.** Delete the three forced-colour classes so bold and italic inherit the post's text colour. Keep `[&_em]:italic`, the `[&_blockquote]:*` group, `prose-rules` and `text-white/[0.88]`. Do not touch `index.css`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCard.tsx` (line ~328) | — | `[&_em]:text-rarity-epic`, `[&_b]:text-gold-light`, `[&_strong]:text-gold-light` are gone; nothing else in the className changed; no CSS/SCSS file added or edited; `npx tsc --noEmit` and `npm run build` pass; live: a post containing bold, italic and a player-chosen colour renders bold/italic in the inherited white and the coloured span in the player's colour |
| T2 | **Bug 2 — transport (Branch B).** In `checkSpelling` replace the GET-with-query-string by a `POST` to `https://speller.yandex.net/services/spellservice.json/checkText` with `Content-Type: application/x-www-form-urlencoded;charset=UTF-8` and body `text`/`lang=ru`/`options=0` (contract in 3.2). Signature and call site unchanged. Add a 10 s `AbortSignal.timeout`. Keep the URL as a module constant — no env var, no proxy. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/api/spellcheck.ts` | — (may run in parallel with T1) | A 2000-character Cyrillic post is checked successfully end-to-end; a ~10 KB post also succeeds; no request URL exceeds a few hundred characters; no preflight failure in the Network tab; tsc + build pass |
| T3 | **Bug 2 — visible failures.** Still fully in scope (3.2): failures are rarer under Branch B, not impossible — player network, Yandex 4xx/5xx, per-IP quota — and today the panel goes **blank**. Add `SpellCheckError` with a cause-specific **Russian** message (network/blocked, 4xx, 429 quota, 5xx, timeout) and `console.warn` of the status; a bare `fetch` rejection gets a generic message, not a guessed cause. `useSpellCheck` gains `error: string \| null`, **catches** instead of rethrowing, clears it on the next success and on `reset()`. `SpellCheckPanel` gains `error?: string \| null` and renders it visibly in `text-site-red` — never blank after a failure. Keep the existing toast; the panel is the copy that survives the toast. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/api/spellcheck.ts`, `src/hooks/useSpellCheck.ts`, `src/components/CommonComponents/SpellCheckPanel/SpellCheckPanel.tsx`, `src/components/pages/LocationPage/PostCreateForm.tsx` | T2 (same file) | With the tab offline the panel shows a Russian error **and** a toast, and is never blank; a forced 429 and a forced 5xx each show a distinct message; the error clears on the next successful check and on «Очистить поле»; no `React.FC`; no SCSS; panel readable and tappable at 360 px; tsc + build pass |
| T4 | **Bug 3, causes B+C.** In `api/spellcheck.ts` add the single-pass `htmlToSpellText(html) → { text, map }` walker per 3.3 (block-boundary `\n`, entity decoding, **no trim**, `map[plainIndex] → htmlIndex`) and re-express `replaceWordInHtml` on top of it — same signature, one traversal; an unresolvable range returns the HTML unchanged and surfaces a Russian error via the T3 path. Use `htmlToSpellText(content).text` in `handleSpellCheck`. **Leave `stripHtmlTags` and `charCount` alone**, and add a comment at both functions explaining that it deliberately mirrors `crud.strip_html_tags`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/api/spellcheck.ts`, `src/components/pages/LocationPage/PostCreateForm.tsx` | T3 (same files — run after, not in parallel) | `<p>  Превет мир</p>` corrects to `<p>  Привет мир</p>` on the first click, no duplication; `<p>Один</p><p>Два</p>` yields two separate tokens and no phantom error at the join; `&nbsp;`/`&amp;` do not shift offsets; a correction inside `<strong>` keeps the tag; `charCount` for the same content is identical to before the change; tsc + build pass |
| T5 | **Bug 3, cause A.** Add `applyFix(index, replacementLength)` to `useSpellCheck`: drop the applied error and shift `pos` by `replacementLength - error.len` for every remaining error with `pos > applied.pos` (strictly greater). Keep `dismissError` unchanged for «пропустить». Call `applyFix` from `handleApplySuggestion`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/hooks/useSpellCheck.ts`, `src/components/pages/LocationPage/PostCreateForm.tsx` | T4 | In a post with three misspellings where the first correction is **longer** than the original (`здраствуйте`→`здравствуйте`), applying all three in order yields exactly three corrected words and no duplicated fragments; same with a **shorter** replacement; «пропустить» on one error leaves the others' positions intact; tsc + build pass |
| T6 | Record the out-of-scope findings in `docs/ISSUES.md` per 3.4: backend `strip_html_tags` separator/entity defect + the test that enshrines it (MEDIUM — needs a balance decision, changes post XP and gate thresholds), the `editorKey` remount losing cursor/undo (LOW), continuous `onChange` from `react-colorful` while dragging (LOW), surrogate-pair spellcheck offsets (LOW). **Documentation only — do not fix any of them and do not touch any `.py` file.** | Frontend Developer | DONE | `docs/ISSUES.md` | — | Four entries present, each with service, `file:line` and priority; `git status` shows no change under `services/locations-service/` |
| T7 | Final review. Re-run `npx tsc --noEmit` and `npm run build`; verify **live** in the browser: (a) a post with bold + italic + a player colour renders with no imposed gold/purple, (b) a 2000-character Cyrillic post is checked successfully, (c) two sequential corrections — one lengthening, one shortening — produce no duplication, (d) an offline tab shows a Russian error in the panel, not a blank. Zero console errors. Check the security checklist and the mandatory frontend rules (TS-only, Tailwind-only, no `React.FC`, 360 px, Russian strings, visible errors). **No pytest run is required — this feature changes no Python (3.6); confirm that in the review rather than reporting a missing QA task.** | Reviewer | DONE | all of the above | T1, T3, T4, T5, T6 | Both automated check results **and** all four live scenarios are recorded in section 5; a review missing either half is invalid |

### Dispatch order

* **T1**, **T2** and **T6** have no dependencies and start immediately, in parallel.
  **T1 is mergeable and shippable on its own** — highest value per unit of risk in the
  feature, and it must not wait for the spellcheck work.
* **T2 → T3 → T4 → T5** are strictly sequential: every one of them touches
  `api/spellcheck.ts` and/or `PostCreateForm.tsx`, so running them concurrently would
  guarantee conflicts. All four are the same agent, so this is one continuous stream.
* **T7** last.

### QA note

No QA Test task appears in this table **by design, not by oversight**. The feature
modifies no backend Python (3.6), which is the single stated exception to the mandatory-QA
rule in CLAUDE.md §11. Frontend verification is owned by the Frontend Developer (tsc +
build, per task) and the Reviewer (live browser verification, T7). If any Python file
does end up touched during implementation, this exemption lapses and a pytest task must
be added before review.

### Open questions for PM

None. The one unknown in the original design — CORS and egress — was measured rather than
guessed, and its answer removed the only contingent branch.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-13

**Result: PASS** (with two recorded residual risks, neither blocking — see below)

Every T1–T6 claim was re-verified independently by execution, not by reading the
implementer's report.

#### Scope confirmation — the QA exemption still holds

`git status` shows ten modified files. Three of them are **not** this feature and were
excluded from review, as instructed:

| File | Owner |
|---|---|
| `services/locations-service/app/main.py` | FEAT-158 (`get_admin_user` -> `require_permission("moderation:*")`) |
| `services/locations-service/app/crud.py` | FEAT-158 (`expire_action_gates_for_post`) |
| `services/frontend/app-chaldea/src/components/Admin/AdminPage.tsx` | FEAT-158 (tile filter) |
| `services/user-service/alembic/versions/0027_add_moderation_permissions.py` (untracked) | FEAT-158 |

FEAT-157's own footprint is **frontend-only**: `PostCard.tsx`, `api/spellcheck.ts`,
`hooks/useSpellCheck.ts`, `SpellCheckPanel.tsx`, `PostCreateForm.tsx`, plus `docs/ISSUES.md`.
**Zero `.py` files, zero Docker/Nginx, zero migrations, zero DB, zero RBAC** —
`git status --porcelain docker/ docker-compose.yml docker-compose.prod.yml` returns empty.
The §3.6 exemption from the mandatory-QA rule is therefore **genuine**, and no missing
pytest task is reported.

#### Automated Check Results

- [x] `npx tsc --noEmit` (inside `frontend` container) — **PASS**, `TSC_EXIT=0`, no output
- [x] `npm run build` (inside `frontend` container) — **PASS**, `BUILD_EXIT=0`,
      `✓ built in 47.41s`; only the pre-existing >500 kB chunk-size advisory
- [x] `py_compile` — **N/A** (no Python in this feature)
- [x] `pytest` — **N/A** (§3.6 exemption, confirmed above)
- [x] `docker-compose config` — **N/A** (no compose/Docker file touched; `git status` on
      `docker/`, `docker-compose.yml`, `docker-compose.prod.yml` is empty)
- [x] Walker executed under `vite-node` in the container, 19 assertions — **ALL PASS**
- [ ] Live verification in a real browser — **NOT POSSIBLE** (see "Live verification" below)

#### T1 — bug 1, forced colour on bold/italic

- `PostCard.tsx:330` now reads `[&_em]:italic` only. The three classes
  `[&_em]:text-rarity-epic`, `[&_b]:text-gold-light`, `[&_strong]:text-gold-light` are gone
  **entirely**, not scoped — matches 3.1. `[&_blockquote]:*`, `prose-rules` and
  `text-white/[0.88]` are byte-identical to before.
- `src/index.css` is **untouched** (`git status --porcelain src/index.css` empty).
  `.prose-rules strong/em/u/s` (`index.css:632-635`) still set weight/style/decoration and
  **no colour**.
- Repo-wide grep for `[&_em]` / `[&_b]` / `[&_strong]` / `[&_i]` across `src/` returns
  exactly one hit: the surviving `[&_em]:italic`. No other surface reintroduces a colour.
- All five other post-rendering surfaces spot-checked at their `dangerouslySetInnerHTML`
  container: `PostHistoryPage.tsx:55` (`text-white`), `WallSection.tsx:171`
  (`prose-rules text-white/80`), `ArchiveArticlePage.tsx:367` (`prose-rules`),
  `RuleOverlay.tsx:46` (`prose-rules text-white`), `WysiwygEditor` (`prose-rules`).
  None forces emphasis colour. (Note: the analysis in 2.1 lists
  `pages/UserProfilePage/WallSection.tsx` and `pages/RulesPage/RuleOverlay.tsx`; the actual
  paths are `components/UserProfilePage/` and `components/RulesPage/`. Documentation-only
  drift, no code impact.)
- **Verified in the compiled artefact**, which is the closest thing to a browser available
  here: `grep` over `dist/assets/index-*.css` yields exactly
  `.\[\&_em\]\:italic em{font-style:italic}` and **no**
  `[&_em]:text-rarity-epic` / `[&_strong]:text-gold-light` rule anywhere in the bundle.
- Render-only change, so it applies retroactively to every existing post. Confirmed.

#### T2 — bug 2, transport

- `api/spellcheck.ts:73` is the **only** `fetch` to the speller in the whole `src/` tree
  (grep for `speller` / `YANDEX` returns the constant, the fetch and comments only).
  `method: 'POST'`, `Content-Type: application/x-www-form-urlencoded;charset=UTF-8`,
  body `text`/`lang=ru`/`options=0`. **No query string remains** — no stray GET.
- 10 s abort implemented with `AbortController` + `setTimeout` (not `AbortSignal.timeout`,
  to avoid a DOM-lib version dependency) and a `timedOut` flag so a timeout gets its own
  Russian message instead of the generic network one. `clearTimeout` in `finally`. Correct.
- URL is a module constant; **no backend proxy, no nginx change, no env var** — verified by
  the empty `git status` on `docker/` and the absence of any new endpoint.
- Signature `checkSpelling(text: string): Promise<SpellError[]>` unchanged.

#### T3 — bug 2, visible failures

- `SpellCheckError` carries a Russian message per cause: timeout, network/blocked
  (deliberately generic — a `fetch` rejection is indistinguishable from CORS), 429 quota,
  >=500, other 4xx with the code, malformed/non-array JSON. Each path `console.warn`s.
- `useSpellCheck` **catches** instead of rethrowing, exposes `error: string | null`, clears
  it at the start of each `runCheck` and in `reset()`. `runCheck` additionally *returns* the
  message so the toast does not read a stale closure value — a good call.
- `PostCreateForm.handleSpellCheck` toasts the returned message; `resetForm` (`:311`) and
  the other two clear paths (`:329`, `:343`) call `spellCheck.reset()`, so «Очистить поле»
  clears the error.
- **The `!checked` branch was specifically checked:** `SpellCheckPanel.tsx` builds
  `errorBlock` *before* the guard and the guard is now `if (!checked) return errorBlock;` —
  it can no longer return bare `null` while an error is set. The error block is also
  rendered in the "Ошибок не найдено" and the error-list branches. **The panel cannot go
  blank after a failure.** `role="alert"`, `text-site-red`, `break-words`,
  `mx-2 sm:mx-4` — readable and non-overflowing at 360 px.

#### T4 + T5 — bug 3, executed not read

Ran a fresh, independently written harness under `vite-node` inside the `frontend`
container, importing the real `htmlToSpellText` / `replaceWordInHtml` and a faithful
re-implementation of `useSpellCheck.applyFix`. **19 assertions, all PASS:**

| Case | Input | Result |
|---|---|---|
| Leading space, first click | `<p>  Превет мир</p>`, pos=2 | `<p>  Привет мир</p>` — **no duplication on the first click** |
| Three sequential, deltas +1 / +1 / 0 | `здраствуйте друзя мои карова` | `<p>здравствуйте друзья мои корова</p>` |
| Three sequential, deltas 0 / +1 / 0 | `карова балшая превет` | `<p>корова большая привет</p>` |
| Three sequential, **shortening first** (-1) | `ввсем превет друззя` | `<p>всем привет друзья</p>` |
| Block separator | `<p>Один</p><p>Два</p>` | text = `"Один\nДва"` — two tokens, no phantom join |
| Fix in the **second** paragraph | same | `<p>Один</p><p>Три</p>` |
| Range spanning the synthetic `\n` | pos=2 len=5 | HTML returned **unchanged** (fail-safe) |
| Entities | `<p>А&nbsp;Б&amp;В превет</p>` | text `"А Б&В превет"`; fix lands correctly, entities preserved |
| Word inside `<strong>` | `<p><strong>превет</strong> мир</p>` | `<p><strong>привет</strong> мир</p>` — tag kept |
| Word split by `<em>` | `<p>пре<em>вет</em> мир</p>` | `<p>привет<em></em> мир</p>` — valid, empty tag left behind (cosmetic only) |
| Out-of-range / negative pos | — | HTML unchanged |

The three-sequential cases are exactly the scenario that produced the reported duplication
(earlier corrections changing length); they are clean.

`stripHtmlTags` / `charCount` — **confirmed untouched**:
`PostCreateForm.tsx` still has `html.replace(/<[^>]*>/g, '').trim()`, which mirrors
`crud.strip_html_tags` (`crud.py:65-67`, `re.sub(r'<[^>]*>', '', html).strip()`)
byte-for-byte, and `git diff services/locations-service/app/crud.py` shows
`strip_html_tags` was not touched by anyone. Executed parity spot-check:
`stripHtmlTags("<p>Один</p><p>Два</p>") === "ОдинДва"` (7 chars) — the legacy gluing is
deliberately preserved, so the counter still matches the server. Both functions carry the
required "do not unify" comment.

`handleApplySuggestion` surfaces an unresolvable range through `spellCheck.setError` **and**
a toast in Russian, and leaves the post untouched. Correct per 3.3.

#### Standards / security checklist

- [x] TypeScript only — no `.jsx` created or modified; all five files are `.ts`/`.tsx`
- [x] Tailwind only — no `.scss`/`.css` file added or edited (`index.css` untouched)
- [x] No `React.FC` / `React.FunctionComponent` in any touched file
- [x] No `any`
- [x] No `TODO` / `FIXME` / `HACK` introduced
- [x] 360 px — the new error block uses `mx-2 sm:mx-4`, `break-words`, no fixed width
- [x] All player-facing strings Russian
- [x] Every failure path visibly surfaced (panel + toast); nothing swallowed
- [x] No new server surface, no new endpoint, no auth change, no secret, no rate-limit need
- [x] No new SCSS, no new dependency, no `package.json` change
- [x] XSS unchanged: `PostCard` still sanitises with DOMPurify; removing colour classes
      does not widen the sanitiser
- [x] Cross-service contracts untouched (no HTTP call added or changed)

#### Live verification — what could NOT be done, stated explicitly

**The `claude-in-chrome` extension is not connected in this session** ("Browser tools are
not available… the Claude in Chrome extension is not set up"), and the `chrome-devtools`
MCP is likewise unavailable. The following four scenarios from T7 therefore **were not
executed in a real browser**:

| T7 scenario | Status | Substitute evidence actually obtained |
|---|---|---|
| (a) bold + italic + player colour render with no imposed gold/purple | **not run in browser** | Compiled `dist/assets/index-*.css` contains only `em{font-style:italic}` for `[&_em]`; no `text-rarity-epic`/`text-gold-light` emphasis rule exists in the bundle, so no such rule can be applied at runtime |
| (b) a 2000-character Cyrillic post checked successfully end-to-end | **not run** | `speller.yandex.net` is unreachable from this workstation *and* from inside the `frontend` container (`wget: can't connect to remote host (213.180.204.29): Connection refused`), which independently reproduces the Architect's finding in 2.2. Transport verified statically only |
| (c) two sequential corrections, one lengthening one shortening, no duplication | **not run in browser** | Executed against the real functions under `vite-node` — four multi-step sequences, all correct (table above). This is stronger than a single browser click-through for the offset arithmetic, but does not cover the React state round-trip through `replaceContent` |
| (d) offline tab shows a Russian error in the panel, not a blank | **not run** | Verified by reading control flow: `errorBlock` is computed before every `return` in `SpellCheckPanel`, including the `!checked` guard; `useSpellCheck` catches and always sets `error`. No code path can render a blank panel after a failure |

Reachability that *was* checked: `http://localhost/` -> **200**, `http://localhost:5555/` ->
**200**. Console-error count could not be observed without a browser.

**Recommendation to PM:** before closing, have someone open a location page in a browser
and do one manual pass of (a)–(d). Only (b) genuinely requires it — the live speller round
trip cannot be reached from this environment at all.

#### Residual risks — recorded, not blocking

1. **Yandex `pos` semantics across the new `\n` separators.** `htmlToSpellText` now emits
   `\n` at block boundaries; the previous `stripHtmlTags` produced no newlines at all, so
   this is new behaviour on the wire. If Yandex.Speller's `pos` did not count line breaks,
   every correction in the second and later paragraphs would misapply. Yandex documents
   `pos` as the absolute position in the submitted text (with `row`/`col` supplied
   separately, which would be redundant otherwise), and every mainstream client library
   slices the original text by `pos` — so this is almost certainly fine. It **could not be
   measured**: the host and all containers are cut off from `speller.yandex.net`. One
   multi-paragraph check on prod settles it.
2. **Astral code points delivered as numeric entities.** Executed:
   `htmlToSpellText('<p>A&#128512;B превет</p>')` gives `text.length = 11` but
   `map.length = 10` — `push()` iterates the decoded chunk by code point while `text`
   counts UTF-16 units. Consequence is **fail-safe, not corrupting**: the following
   `replaceWordInHtml` returns the HTML unchanged and the player gets the Russian
   «Не удалось применить исправление…» message. A literal emoji typed in the post (the
   realistic case) works correctly — verified: `<p>Привет 😀 превет мир</p>` corrects to
   `<p>Привет 😀 привет мир</p>`. This is within the limitation already accepted in 3.3 and
   recorded in `docs/ISSUES.md`; no new entry filed.

#### T6

`docs/ISSUES.md` contains all four required entries, each with service, `file:line`,
priority and a "why not now" rationale: `strip_html_tags` separator/entities + the test
that enshrines it (MEDIUM), the `editorKey` remount (LOW), continuous `react-colorful`
`onChange` (LOW), surrogate-pair offsets (LOW). No `.py` file under
`services/locations-service/` was touched by this feature.

#### Issues Found

None blocking. Nothing was fixed by the Reviewer — no change was needed.

#### Pre-existing issues noted

None new. The HIGH entry about moderation returning 500 that also appears in this
`docs/ISSUES.md` diff belongs to FEAT-158 and is outside this review.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-13 — PM: фича создана по трём багам от пользователя, причины найдены анализом кода
[LOG] 2026-09-13 — PM: старт отложен до закрытия FEAT-156 (конфликт по PostCreateForm.tsx)
[LOG] 2026-09-13 — Architect: начал проектирование, FEAT-156 закрыт (996db5b), блокировка снята
[LOG] 2026-09-13 — Architect: перепроверил все ссылки раздела 1 после FEAT-156; семь ссылок уехали (stripHtmlTags 59→62, вызов 159→257, тост 161-165→259-263, бамп editorKey 173→replaceContent 140-148, ColorPicker 4-14→3-13, spellcheck.ts 25-38→25-46, путь теста tests/→app/tests/) — поправил прямо в разделе 1, таблица правок в 2.4
[LOG] 2026-09-13 — Architect: баг 1 — grep по всему фронту: цвет на strong/b/em навязывает ТОЛЬКО PostCard.tsx:328. Остальные пять мест рендера HTML поста (история постов, стена профиля, архив, правила, редактор) чистые; prose-rules в index.css цвет не задаёт и править его НЕ надо
[LOG] 2026-09-13 — Architect: баг 2 — CORS проверить с этой машины НЕ удалось: speller.yandex.net и сам yandex.ru недоступны с хоста (connection refused на уровне сети, и в песочнице, и без неё; example.com при этом 200). Гадать нельзя — вынес в блокирующую задачу T2: один curl с прод-VPS отвечает сразу на два вопроса (есть ли ACAO и достижим ли хост с сервера)
[LOG] 2026-09-13 — Architect: решение по багу 2 — бэкенд-прокси POST /locations/spellcheck в locations-service (ветка A) по умолчанию; сигнатура checkSpelling(text) не меняется, поэтому ветка B (клиентский POST) отличается только телом одной функции и на остальные задачи не влияет. Таблица решений на все четыре исхода T2 — в 3.2
[LOG] 2026-09-13 — Architect: баг 3 — выбрал вариант 2 + сдвиг смещений из варианта 1. Вариант 1 в одиночку не лечит дубль с первого клика, вариант 2 в одиночку не лечит устаревшие смещения. Вариант 3 (транзакции ProseMirror) отклонён: ломает публичный контракт общего WysiwygEditor ради устранения ремаунта, который не входит ни в один из трёх симптомов — вынесен в ISSUES.md
[LOG] 2026-09-13 — Architect: бэкенд-близнец strip_html_tags (crud.py:65) осознанно оставлен как есть — правка меняет char_count, а значит опыт за пост и пороги гейтов. Это баланс, а не багфикс; фронтовый charCount обязан и дальше зеркалить бэкенд, иначе счётчик будет врать про гейты. В ISSUES.md (T9)
[LOG] 2026-09-13 — Architect: спроектировано 10 задач, 1 новый API-контракт, миграций и изменений БД нет. T1 (баг 1) не зависит ни от чего и может уехать в прод отдельно и первой
[LOG] 2026-09-13 — Architect: статус → IN_PROGRESS
[LOG] 2026-09-13 — PM: выполнил T2 с прод-VPS. Результат однозначен: GET с Origin → 200 и access-control-allow-origin: *; OPTIONS-префлайт → 200, access-control-allow-methods: OPTIONS, GET, POST; форма-POST коротким текстом → 200 с верными исправлениями; форма-POST на ~10.8 КБ кириллицы → 200 и 28 579 байт JSON
[LOG] 2026-09-13 — Architect: ветка B зафиксирована — остаёмся на клиенте, меняется только GET → POST. Бэкенд-прокси НЕ строим: проба доказала, что он не даёт ничего, чего у нас уже нет. Бонусом: квота Яндекса считается по IP, а на клиенте она размазана по IP игроков, а не собрана в один IP сервера
[LOG] 2026-09-13 — Architect: сняты четыре задачи старой нумерации — T2 (проба, сделана), T3 (прокси), T4 (nginx rate limit), T8 (pytest на прокси). Ни одна не выживает при ветке B: запрос вообще не идёт через наш шлюз, так что лимитировать нечего, а тестировать некую ручку некуда
[LOG] 2026-09-13 — Architect: фича теперь не трогает ни одного .py файла — ни Docker, ни Nginx, ни БД, ни миграций, ни RBAC. Правило обязательного QA (CLAUDE.md §11) не применяется по его же единственному исключению; это явно зафиксировано в 3.6 и в заметке под таблицей задач, чтобы Ревьюер не счёл это забывчивостью. Проверка вместо QA: tsc + build на Frontend Dev, живая проверка в браузере на Ревьюере
[LOG] 2026-09-13 — Architect: видимая ошибка в панели ОСТАЁТСЯ в скоупе (теперь T3): сеть игрока, 4xx/5xx Яндекса и квота никуда не делись, а сейчас любой сбой оставляет панель пустой
[LOG] 2026-09-13 — Architect: задачи перенумерованы T1–T7, все разработчицкие — на Frontend Developer. T1 (баг 1) по-прежнему ни от чего не зависит и едет первой и отдельно. Решения по багу 3 (вариант 2 + сдвиг смещений, htmlToSpellText, stripHtmlTags не трогаем) остались без изменений
[LOG] 2026-09-13 — Frontend Dev: начал T2–T5 (спеллчекер), файлы api/spellcheck.ts, hooks/useSpellCheck.ts, SpellCheckPanel.tsx, PostCreateForm.tsx
[LOG] 2026-09-13 — Frontend Dev: T2 готова — checkSpelling теперь шлёт form-POST (application/x-www-form-urlencoded;charset=UTF-8, text/lang=ru/options=0) вместо GET с текстом в query; добавлен таймаут 10 с через AbortController (AbortSignal.timeout не используем, чтобы не зависеть от версии DOM-либы). Сигнатура и место вызова не менялись, URL остался модульной константой, прокси не строим
[LOG] 2026-09-13 — Frontend Dev: T3 готова — добавлен класс SpellCheckError с русским сообщением по причине (сеть/блокировка — обобщённо, 4xx, 429 — квота, 5xx, таймаут, битый ответ), статус пишется в console.warn. useSpellCheck ловит вместо проброса, даёт error: string | null, чистит его при новом успешном запуске и в reset(); runCheck возвращает сообщение, чтобы тост не читал устаревшее состояние из замыкания. В SpellCheckPanel добавлен проп error и видимый красный блок (border/bg site-red, role="alert", break-words) — панель больше никогда не бывает пустой после сбоя
[LOG] 2026-09-13 — Frontend Dev: T4 готова — в api/spellcheck.ts добавлен однопроходный walker htmlToSpellText(html) → { text, map, mapEnd, synthetic }: теги пропускаются, на границах блоков (</p>, <br>, </li>, </h1>–</h6>, </blockquote>, </figure>, </tr> и др.) вставляется перенос строки со схлопыванием серий, энтити декодируются, trim НЕ делается. replaceWordInHtml переписан поверх того же walker'а — теперь это один обход, а не два расходящихся; теги внутри заменяемого диапазона сохраняются, неразрешимый диапазон (выход за текст или попадание на синтетический разделитель) возвращает HTML без изменений и поднимает русскую ошибку в панель. handleSpellCheck шлёт htmlToSpellText(content).text. stripHtmlTags и charCount НЕ тронуты — рядом с обеими функциями оставлен комментарий, почему они намеренно зеркалят crud.strip_html_tags и почему их нельзя «объединить»
[LOG] 2026-09-13 — Frontend Dev: T5 готова — в useSpellCheck добавлен applyFix(index, replacementLength): удаляет применённую ошибку и сдвигает pos у оставшихся с pos > applied.pos на replacementLength - error.len (строго больше — совпадающие pos это отчёты о том же токене). dismissError остался как есть для «Пропустить». handleApplySuggestion вызывает applyFix вместо dismissError
[LOG] 2026-09-13 — Frontend Dev: проверка — npx tsc --noEmit и npm run build внутри контейнера frontend, оба EXIT=0 (build: ✓ built in 52.05s). Дополнительно прогнал walker вживую через vite-node на 9 кейсах: «<p>  Превет мир</p>» → «<p>  Привет мир</p>» с первого клика без дубля; «<p>Один</p><p>Два</p>» → два токена, разделённых переносом строки; фантомной ошибки на стыке нет, диапазон через разделитель возвращает HTML без изменений; &nbsp;/&amp; не сдвигают смещения; исправление внутри <strong> сохраняет тег; слово, разорванное тегом, тоже чинится; три подряд исправления (+1, +1, 0) дают «здравствуйте друзья мои корова», укорачивающая замена (-1) — «корова большая привет», дублей нет
[LOG] 2026-09-13 — Frontend Dev: начал T1 и T6
[LOG] 2026-09-13 — Frontend Dev: T1 — из PostCard.tsx убраны три класса `[&_em]:text-rarity-epic`, `[&_b]:text-gold-light`, `[&_strong]:text-gold-light`. `[&_em]:italic`, группа `[&_blockquote]:*`, `prose-rules` и `text-white/[0.88]` оставлены без изменений; index.css не тронут, новых стилей не добавлено. Жирный и курсив теперь наследуют цвет поста, а выбранный игроком цвет больше не перекрывается
[LOG] 2026-09-13 — Frontend Dev: T6 — в docs/ISSUES.md добавлены четыре записи: strip_html_tags без разделителя + тест, закрепляющий поведение (MEDIUM, нужно решение по балансу), ремаунт редактора через editorKey (LOW), непрерывный onChange у react-colorful (LOW), смещения на суррогатных парах (LOW). Дубликатов не было; ни один .py файл не тронут
[LOG] 2026-09-13 — Frontend Dev: проверка в контейнере frontend — `npx tsc --noEmit` без ошибок (exit 0), `npm run build` успешен (exit 0, built in 45.36s). T1 и T6 → DONE
[LOG] 2026-09-13 — Reviewer: начал T7. Сверил границы фичи: из десяти изменённых файлов три (locations-service main.py/crud.py, AdminPage.tsx) и новая миграция user-service принадлежат FEAT-158 и в ревью не входят
[LOG] 2026-09-13 — Reviewer: подтвердил освобождение от обязательного QA — FEAT-157 не трогает ни одного .py, ни Docker, ни Nginx, ни миграций, ни БД, ни RBAC; git status по docker/ и обоим compose-файлам пуст. Отсутствие pytest-задачи нарушением не считаю
[LOG] 2026-09-13 — Reviewer: автопроверки в контейнере frontend — npx tsc --noEmit exit 0 (без вывода), npm run build exit 0 (built in 47.41s). Оба PASS
[LOG] 2026-09-13 — Reviewer: баг 1 перепроверен независимо. В PostCard.tsx:330 остался только [&_em]:italic, три цветовых класса убраны полностью. index.css не тронут, prose-rules цвет не задаёт. Grep по всему src/ находит [&_em]/[&_b]/[&_strong] ровно один раз. Пять остальных поверхностей рендера HTML поста чистые. Дополнительно проверил собранный бандл: в dist/assets/index-*.css есть только em{font-style:italic}, правил text-rarity-epic/text-gold-light на em/strong нет вообще
[LOG] 2026-09-13 — Reviewer: баг 2 — в src/ ровно один fetch к спеллеру, POST с form-urlencoded телом, query-строки не осталось; таймаут 10 с через AbortController с отдельным русским сообщением. Прокси, nginx-правил и env-переменных нет
[LOG] 2026-09-13 — Reviewer: проверил ветку !checked в SpellCheckPanel — errorBlock считается ДО всех return, guard теперь возвращает errorBlock, а не голый null. Панель после сбоя пустой быть не может; ошибка чистится при новом успешном запуске и в reset(), который вызывает «Очистить поле»
[LOG] 2026-09-13 — Reviewer: баг 3 проверен ИСПОЛНЕНИЕМ, а не чтением. Прогнал собственную независимую проверку через vite-node в контейнере на реальных htmlToSpellText/replaceWordInHtml плюс точная копия applyFix — 19 утверждений, все PASS. В том числе: абзац с ведущим пробелом чинится с первого клика без дубля; три последовательных исправления с дельтами +1/+1/0, 0/+1/0 и −1/0/0 дают ровно исправленный текст без дублей; исправление во втором абзаце попадает в цель; диапазон через синтетический разделитель возвращает HTML без изменений; энтити не сдвигают смещения; тег внутри заменяемого слова сохраняется
[LOG] 2026-09-13 — Reviewer: stripHtmlTags и charCount не тронуты, регулярка байт-в-байт совпадает с crud.strip_html_tags; исполнением подтвердил, что «<p>Один</p><p>Два</p>» по-прежнему даёт «ОдинДва» (7 символов), то есть счётчик не разошёлся с сервером
[LOG] 2026-09-13 — Reviewer: живая проверка в браузере НЕВОЗМОЖНА — расширение Claude in Chrome в этой сессии не подключено, chrome-devtools тоже недоступен. Явно зафиксировал в разделе 5, какие четыре сценария не выполнены в реальном браузере и чем каждый заменён. Отдельно: speller.yandex.net недоступен и с хоста, и изнутри контейнера (connection refused на 213.180.204.29), поэтому сквозная проверка спеллчекера здесь недостижима в принципе
[LOG] 2026-09-13 — Reviewer: зафиксировал два остаточных риска (не блокирующие): семантика pos у Яндекса при новых переносах строк между абзацами — измерить нечем, проверяется одним прогоном на проде; и рассинхрон map/text при астральных символах, заданных числовой энтити — поведение fail-safe, исправление просто не применяется с русским сообщением, укладывается в уже записанное в ISSUES.md ограничение
[LOG] 2026-09-13 — Reviewer: T6 проверен — в docs/ISSUES.md все четыре записи на месте, с сервисом, file:line и приоритетом; .py-файлы locations-service этой фичей не тронуты
[LOG] 2026-09-13 — Reviewer: проверка завершена, результат PASS. Блокирующих проблем нет, править было нечего. Рекомендация PM: перед закрытием один ручной проход сценариев (a)-(d) в браузере, обязателен по сути только (b) — живой запрос к спеллеру из этого окружения недостижим
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

**Баг 1 — цвет на жирном и курсиве.** Из `PostCard.tsx` удалены три захардкоженных класса,
принудительно красившие любой `<em>` в фиолетовый и любой `<strong>`/`<b>` в золотой **при
отрисовке поста**. Правка касается только отображения, поэтому **действует задним числом на все
существующие посты**: выбранный игроком цвет больше не подменяется, а неокрашенный текст остаётся
обычного цвета. Проверено в собранном бандле — правил `text-rarity-epic`/`text-gold-light` на
`em`/`strong` там больше нет вообще.

**Баг 2 — проверка правописания.** Запрос переведён с GET (текст в адресной строке) на форменный
POST с таймаутом 10 секунд. Причина поломки была в том, что кириллица в URL занимает 6 символов на
букву, а минимальная длина поста — 300 символов: длинные ролевые посты не пролезали в принципе.
Прокси на бэкенде **не понадобился** — PM замерил с прода, что Яндекс отдаёт
`access-control-allow-origin: *` и разрешает POST, а тело на 10.8 КБ обрабатывает нормально.
Заодно квота Яндекса считается по IP, и при запросе из браузера у каждого игрока она своя.

**Баг 3 — дублирование слов.** Две независимые причины, обе устранены:
- Текст для спеллера обрезался по краям, а замена искала позицию по необрезанному HTML — дубль
  возникал с первого же клика, если абзац начинался с пробела.
- После применения исправления позиции остальных ошибок **не пересчитывались**, и каждая
  следующая правка уезжала на накопленную разницу, оставляя хвост старого слова.

Введён единый проход `htmlToSpellText`, на котором теперь выражена и замена — две функции больше
не могут разойтись. Позиции оставшихся ошибок сдвигаются на `длина замены - длина ошибки`.

**Сверх того:** панель проверки раньше просто пустела при любом сбое. Теперь показывает конкретное
русское сообщение, разное для обрыва связи, таймаута, превышения лимита и отказа сервиса.

### Что изменилось от первоначального плана

- **Прокси, правка nginx и тесты к ним выкинуты** после замера CORS с прода. Из десяти задач
  осталось семь, и в фиче не осталось ни строчки Python.
- Из-за этого **QA-задач нет** — правило обязательного pytest не применяется, потому что не
  затронуты ни Python, ни Docker, ни nginx, ни БД, ни миграции, ни RBAC. В файле это зафиксировано
  явно, чтобы отсутствие тестов не выглядело недосмотром.
- Переход на транзакции ProseMirror **отклонён**: он потребовал бы менять публичный контракт
  общего редактора ради исправления багов, а его главный приз (сохранение курсора и истории
  отмен) не входит ни в один из трёх симптомов. Записано в `ISSUES.md` как отдельный долг.
- `stripHtmlTags` **намеренно не тронут** — счётчик символов обязан совпадать с бэкендовым
  `crud.strip_html_tags` байт в байт, иначе он обещал бы гейты, которые сервер потом не выдаст.

### Проверка

- `npx tsc --noEmit` и `npm run build` — зелёные.
- Логика замен проверена **исполнением**, а не чтением: 19 утверждений, включая ведущий пробел,
  три последовательных исправления с удлинением и с сокращением, правку во втором абзаце,
  слово, разорванное тегом, и энтити.
- **Замер с прода:** текст `Один
Превет мир` → Яндекс вернул `pos: 5`, то есть перенос строки
  он считает. Это снимает единственный остаточный риск, отмеченный ревьюером: новые разделители
  абзацев не сдвигают позиции.

### Оставшиеся риски / follow-up

- **В браузере ничего не проверялось** — расширение Chrome в сессии не подключено, а
  `speller.yandex.net` недоступен и с машины, и из контейнера. Стоит один раз прощёлкать руками:
  курсив и жирный на старом посту, проверка правописания на длинном посту, два исправления подряд,
  и сообщение об ошибке при отключённой сети.
- **Астральные символы через числовую ссылку** (`&#128512;`) ломают карту смещений, но
  **безопасно**: замена не применяется, игрок видит русское сообщение. Живой эмодзи работает.
  Записано в `ISSUES.md`.
- Четыре записи в `ISSUES.md`: разделители в `strip_html_tags` (правка сдвинет опыт и пороги
  гейтов — решение за пользователем), перемонтирование редактора после исправления, палитра
  `react-colorful`, красящая текст при простом перетаскивании, и суррогатные пары.
