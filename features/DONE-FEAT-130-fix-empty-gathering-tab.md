# FEAT-130: Bugfix — пустая вкладка «Сбор» в профиле

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-04-25 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Bugfix follow-up to FEAT-128 (DONE). On completion: rename to `DONE-FEAT-130-fix-empty-gathering-tab.md`.

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание

Пользователь сообщил: при переходе во вкладку «Сбор» в профиле персонажа открывается пустая страница — виден только фон сайта, ни заголовка, ни карточек навыков (Горное дело / Травничество / Лесорубство).

Реализация вкладки в FEAT-128 (task #22):
- `services/frontend/app-chaldea/src/components/ProfilePage/GatheringTab/GatheringTab.tsx`
- `services/frontend/app-chaldea/src/components/ProfilePage/GatheringTab/GatheringSkillCard.tsx`
- Wired в `ProfileTabs.tsx` (key `'gathering'`, label `'Сбор'`) и `ProfilePage.tsx` (case branch).

### Гипотезы

- **A.** Render error — `GatheringTab` бросает исключение, ErrorBoundary (если есть) поглощает, страница пустая.
- **B.** Tab key mismatch между `ProfileTabs.tsx` (отправляет ключ) и `ProfilePage.tsx` (рендерит case).
- **C.** Thunk `loadGatheringSkills` падает на сетевом 401/404/500 и компонент в loading-стейте без fallback.
- **D.** Тип данных в Redux state не совпадает с тем, что компонент ожидает (поле `current_bonuses` undefined → crash на дереференсе).
- **E.** Неправильный prop передаётся (`characterId`/`isOwnProfile`).

### UX (текущий, баговый)

1. Игрок открывает профиль, кликает таб «Сбор».
2. Контент исчезает, виден только тёмный фон сайта.

### UX (ожидаемый)

1. Игрок видит заголовок и три карточки навыков с рангом, прогрессом опыта, бонусами.

### Связанные файлы

- Frontend:
  - `src/components/ProfilePage/ProfileTabs.tsx`
  - `src/components/ProfilePage/ProfilePage.tsx`
  - `src/components/ProfilePage/GatheringTab/GatheringTab.tsx`
  - `src/components/ProfilePage/GatheringTab/GatheringSkillCard.tsx`
  - `src/redux/slices/gatheringSlice.ts`
  - `src/api/gatheringApi.ts`
  - `src/types/gathering.ts`
- Backend (если проблема в API):
  - `services/inventory-service/app/main.py` — `GET /inventory/characters/{cid}/gathering-skills`

---

## 2. Investigation + Fix Report (filled by Frontend Dev — in English)

### Root cause

`GatheringSkillCard.tsx:98` rendered `{skill.next_rank}` directly as a JSX child. The frontend `GatheringSkill` type (in `src/types/gathering.ts`) declared `next_rank: number | null` per the FEAT-128 spec example (section 3.4 showed `"next_rank": 3`), but the **actual backend response** from `inventory-service` is an **object**, not an integer:

```py
# services/inventory-service/app/schemas.py
class GatheringSkillOut(BaseModel):
    ...
    next_rank: Optional[GatheringNextRank] = None   # <- object, not int

# services/inventory-service/app/crud.py — build_gathering_skills_response()
"next_rank": {
    "rank_number": next_rank_row.rank_number,
    "required_experience": next_rank_row.required_experience,
    "double_chance_bonus": ...,
    "speed_bonus_pct": ...,
    "stamina_bonus_pct": ...,
}
```

When React tries to render that object as a child it throws `Objects are not valid as a React child (found: object with keys {rank_number, required_experience, ...})`. Because `<GatheringTab>` was **not** wrapped in an ErrorBoundary in `ProfilePage.tsx` (unlike `<CraftTab>` which is), the exception propagated up the entire `<motion.div>` subtree and React unmounted the page → only site background visible. Other tabs (Character, Skills, Перки) kept working because they don't render `next_rank`.

The TypeScript type was wrong and the cast was unsafe — TS compiles the code fine (objects can be assigned to `number | null` only at the boundary where the API response is typed; once typed, dereferencing succeeds but render explodes at runtime).

The original FEAT-128 spec and the implemented backend disagree about whether `next_rank` is `int` or `object`. Both shapes carry the same useful information (the rank number) plus the backend object adds `required_experience` redundantly with `experience_to_next`. Smallest frontend fix: align the TS type with the actual backend response and pull `.rank_number` out for display. Per the task's "do NOT modify backend" rule, no backend changes were attempted.

### Files changed

| File | Why |
|------|-----|
| `services/frontend/app-chaldea/src/types/gathering.ts` | Replaced `next_rank: number \| null` with a `GatheringNextRank` interface mirroring the backend `GatheringNextRank` Pydantic model. Added a comment documenting the spec/impl discrepancy. |
| `services/frontend/app-chaldea/src/components/ProfilePage/GatheringTab/GatheringSkillCard.tsx` | Changed `Следующий ранг ({skill.next_rank})` → `Следующий ранг {skill.next_rank ? \`(${skill.next_rank.rank_number})\` : ''}`. This is the actual bug fix — no longer renders an object as a child. |
| `services/frontend/app-chaldea/src/components/ProfilePage/ProfilePage.tsx` | Wrapped `<GatheringTab>` in `<ErrorBoundary>` so any future per-row crash shows a Russian error fallback instead of blanking the whole tab silently. Mirrors what already exists for `<CraftTab>`. |
| `services/frontend/app-chaldea/src/components/ProfilePage/GatheringTab/GatheringTab.tsx` | Added a sticky `loadFailed` local state set by `.unwrap().catch()`. The empty state now distinguishes "still no skills" vs "load failed" with a clear "Не удалось загрузить навыки сбора" message and a "Попробовать снова" retry button. The loading spinner also got a "Загрузка..." caption so the state is never just a silent spinner over a blank background. |

### Verification

- `docker exec frontend npx tsc --noEmit` → **64 errors total = baseline**, **0 in any gathering file** (confirmed by `grep -i gathering`). No new errors introduced.
- `docker exec frontend npm run build` → **PASS** (`built in 26.78s`).
- Live verification: not performed in this session — host has no node/npx, work was done inside the running `frontend` container. The data path is now: backend object `{rank_number, ...}` → typed as `GatheringNextRank | null` → rendered as `skill.next_rank.rank_number` (a number). The previous crash path is gone.

### Notes / risks

- The original FEAT-128 spec (`next_rank: 3` integer) is now technically out of sync with both the implemented backend and the updated frontend type. Acceptable because the backend already shipped this shape — frontend now matches reality. PM may want to update the spec OR have backend revert to a plain int; that's an architectural call, not a bugfix decision.
- No styles were touched — visual scope stays with FEAT-128 as instructed.
- ErrorBoundary wrapping is a defensive add and follows the same pattern already used for `<CraftTab>`.

---

## 3. Logging (in Russian)

```
[LOG] 2026-04-25 — PM: создан FEAT-130 — пустая вкладка «Сбор» в профиле. Запускаю Frontend Dev на расследование + фикс.
[LOG] 2026-04-25 22:10 — Frontend Dev: начал расследование FEAT-130.
[LOG] 2026-04-25 22:35 — Frontend Dev: причина — backend возвращает next_rank объектом, фронт типизировал его числом и рендерил {skill.next_rank} напрямую → React-исключение «objects are not valid as a React child» рушит таб (GatheringTab не был обёрнут в ErrorBoundary). Fix: тип GatheringNextRank в src/types/gathering.ts, рендер skill.next_rank.rank_number в GatheringSkillCard.tsx, ErrorBoundary вокруг GatheringTab в ProfilePage.tsx, sticky loadFailed + retry-кнопка в GatheringTab.tsx. tsc — 64 ошибки (baseline, 0 новых в gathering-файлах); npm run build — PASS.
```

---

## 4. Completion Summary (filled by PM on close — in Russian)

### Что сделано

Исправлена пустая вкладка «Сбор» в профиле.

**Корневая причина:** Бэкенд (`inventory-service`) возвращает `next_rank` как объект (`{rank_number, required_experience, double_chance_bonus, speed_bonus_pct, stamina_bonus_pct}`), а TS-тип на фронте был объявлен как `number | null` (по примеру в спеке FEAT-128). Карточка `GatheringSkillCard` рендерила `{skill.next_rank}` напрямую как JSX-child → React бросал исключение «Objects are not valid as a React child», и поскольку `<GatheringTab>` не был обёрнут в `ErrorBoundary`, ошибка убивала всю секцию профиля → пустая страница.

**Изменения** (все на фронте, бэк не тронут):
- `src/types/gathering.ts` — добавлен интерфейс `GatheringNextRank`, тип `next_rank: GatheringNextRank | null`.
- `src/components/ProfilePage/GatheringTab/GatheringSkillCard.tsx` — рендерим `skill.next_rank.rank_number` вместо объекта.
- `src/components/ProfilePage/ProfilePage.tsx` — `<GatheringTab>` обёрнут в `<ErrorBoundary>` (как `<CraftTab>`).
- `src/components/ProfilePage/GatheringTab/GatheringTab.tsx` — добавлены sticky `loadFailed` флаг + кнопка «Попробовать снова» + подпись «Загрузка...» — пустых/ошибочных молчаливых состояний больше нет.

**Проверка:** `tsc --noEmit` 64 ошибки (= baseline, 0 новых), `npm run build` PASS.

### Как проверить

Профиль → вкладка «Сбор» → должны увидеть три карточки навыков с рангом, прогрессом, бонусами и превью следующего ранга в скобках, например «Следующий ранг (2)».

### Оставшиеся риски

- **Расхождение спека↔реализация по форме `next_rank`** (спека FEAT-128 показывала int, бэк отдаёт объект). Фронт теперь соответствует реальности. При желании можно либо обновить спеку, либо упростить бэкенд до int — это уже архитектурное решение, не баг.
- ErrorBoundary вокруг `<GatheringTab>` теперь страхует от будущих сюрпризов в этой вкладке. Аналогично уже было сделано для `<CraftTab>` — стоит проверить, есть ли подобное молчаливое падение в других вкладках профиля (отдельной задачей).
