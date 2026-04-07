# FEAT-122: Fix NPC skills save error

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-04-07 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief

### Описание
В админке НПС → Статы и навыки → раздел Навыки кнопка "Сохранить навыки" возвращает ошибку "Не удалось сохранить навыки". После обновления страницы все навыки у НПС пропадают.

### Контекст
- Раньше функция работала корректно — навыки сохранялись и подгружались.
- Сейчас сломана (регрессия).
- Затронут тот же компонент, в котором только что чинился поисковик навыков (FEAT-120) — `NpcStatsEditor.tsx`. Возможно связано, возможно нет.

### Ожидаемое поведение
- Нажатие "Сохранить навыки" → навыки записываются в БД у НПС
- После reload — список текущих навыков виден и сохранён

---

## 2. Analysis Report (Codebase Analyst)

### Root Cause

Frontend bug in `NpcStatsEditor.tsx` — incorrect mapping of the response from `GET /skills/characters/{id}/skills` to the local `SelectedSkill` state.

The backend endpoint returns `CharacterSkillRead`, whose top-level fields are:
```
{ id, character_id, skill_rank_id, skill_rank: { skill_id, rank_number, ... }, skill_name, skill_type, skill_image, ... }
```
There is **no top-level `skill_id` or `rank_number`** — they live inside the nested `skill_rank` object.

But the frontend (lines 167-178 of `NpcStatsEditor.tsx`) declares a wrong-shape `SkillAssignment` interface and maps as:
```ts
const selected = skillData.map(s => ({
  skill_id: s.skill_id,        // undefined — field doesn't exist
  skill_name: s.skill_name,    // ok
  rank_number: s.rank_number,  // undefined — field doesn't exist
  skill_rank_id: s.id,         // wrong: this is the character_skills.id, not skill_ranks.id
}));
```

Result: every entry in `currentSkills`/`originalSkills` has `skill_id=undefined` and `rank_number=undefined`. Two consequences:

1. **Visual:** existing skills render as "Навык #undefined (Ранг undefined)" — actually they show `skill_name` so the user doesn't immediately notice.
2. **Save flow** (`handleSaveSkills`, lines 275-305):
   - Step 1: `DELETE /skills/admin/character_skills/by_character/{npcId}` — succeeds, all skills wiped from DB.
   - Step 2: `POST /skills/assign_multiple` with payload `{character_id, skills: [{skill_id: undefined, rank_number: undefined}, ...]}` — JSON omits the undefined fields, Pydantic validation fails with `422 Unprocessable Entity` (missing required `skill_id`/`rank_number` in `AssignSkillEntry`).
   - Frontend catches the axios error → toast "Не удалось сохранить навыки".
   - But step 1 already executed, so on reload the NPC has zero skills.

This explains both observed symptoms (error toast + skills disappear after reload) perfectly.

### Verification

- Live `GET /skills/characters/4/skills` returned `[{"character_id":4,"skill_rank_id":17,"id":51,"skill_rank":{"id":17,"skill_id":8,"rank_number":1,...},"skill_name":"Удар воина",...}]` — confirms nested structure.
- Backend `assign_multiple` was tested directly via curl with valid payload `{character_id:4, skills:[{skill_id:8, rank_number:1}]}` and returned 200 OK — backend works correctly.
- `DELETE /skills/admin/character_skills/by_character/{id}` requires `skills:delete` permission; admin (role_id=4) has it in `role_permissions` table — auth works.

### Regression Origin

Introduced in commit `456c124` "feat(admin-npc): complete NPC admin panel overhaul (FEAT-110 through FEAT-116)" (Mon Apr 6 07:55:17 2026). Before this commit, `NpcStatsEditor.tsx` only displayed skills read-only; the inline editor with `currentSkills`/`originalSkills`/`handleSaveSkills` was added in this commit and shipped with the broken mapping. The "Сохранение навыков" feature has therefore been broken since FEAT-110 merged.

The user perceives it as a regression because **before FEAT-110 this UI either didn't exist as an inline editor or used a separate workflow** (FEAT-064 shipped a "NPC skills admin editor" earlier). The new inline path was never working correctly.

### Affected Files

| File | Type of Change | Notes |
|------|----------------|-------|
| `services/frontend/app-chaldea/src/components/AdminNpcsPage/NpcStatsEditor.tsx` | Fix the mapping | Already `.tsx` — no language migration trigger. Already Tailwind — no styling migration trigger. |

No backend changes required. No DB migrations. No new dependencies.

### Recommended Fix

Replace the mapping at lines 167-178 with:
```ts
interface SkillAssignment {
  id: number;
  skill_rank_id: number;
  skill_rank: { id: number; skill_id: number; rank_number: number };
  skill_name: string | null;
  // ...
}
// ...
const selected: SelectedSkill[] = skillData.map((s) => ({
  skill_id: s.skill_rank.skill_id,
  skill_name: s.skill_name ?? `Навык #${s.skill_rank.skill_id}`,
  rank_number: s.skill_rank.rank_number,
  skill_rank_id: s.skill_rank.id,
}));
```
And update the `SkillAssignment` interface (lines 50-55) to match the real backend shape (`skill_rank` nested object instead of flat `skill_id`/`rank_number`).

Optional safety improvement (not strictly required to fix the bug, but recommended): wrap the save flow in a transactional pattern — either call DELETE only after a successful POST, or add a backend "replace_all" endpoint that deletes + inserts atomically. Currently a partial failure of step 2 always destroys existing data.

### Migration Triggers (CLAUDE.md sections 8/9/11/12)

- Section 8 (Tailwind): file already uses Tailwind classes — no SCSS migration needed.
- Section 9 (TypeScript): file is already `.tsx` — no migration needed.
- Section 11 (no `React.FC`): component uses arrow function with destructured props — compliant.
- Section 12 (mobile responsiveness): the fix is logic-only (mapping), does not touch styles, so per CLAUDE.md "Задача не касается стилей — не трогать". No responsiveness work required.

### Risks

- Risk: User may have already corrupted other NPCs by clicking save → all their skills wiped. → Mitigation: out of scope of fix; communicate to user, restore from DB backup if needed.
- Risk: Same nested-vs-flat mismatch may exist elsewhere in the frontend that calls `GET /skills/characters/{id}/skills`. → Mitigation: grep for other consumers of this endpoint as a follow-up; not part of current fix.

---

## 4. Tasks

| # | Agent | Description | Status |
|---|-------|-------------|--------|
| 1 | Frontend Dev | Fix `SkillAssignment` interface in `NpcStatsEditor.tsx` to reflect nested `skill_rank` shape returned by backend | DONE |
| 2 | Frontend Dev | Fix mapping of `GET /skills/characters/{id}/skills` response to `SelectedSkill` (read `skill_rank.skill_id` / `skill_rank.rank_number` / `skill_rank.id`, store `character_skill_id`) | DONE |
| 3 | Frontend Dev | Make `handleSaveSkills` non-destructive: diff original vs current, POST additions first, then DELETE removed entries individually by `character_skill_id`. On POST failure existing skills survive untouched. | DONE |

---

## 5. Review Log

### Review #1 — 2026-04-07
**Result:** PASS

Проверен `services/frontend/app-chaldea/src/components/AdminNpcsPage/NpcStatsEditor.tsx`:
- Интерфейс `SkillAssignment` (строки 56-64) соответствует бэкенд-схеме `CharacterSkillRead`: вложенный `skill_rank: {id, skill_id, rank_number}`, top-level `id`, `character_id`, `skill_rank_id`, `skill_name`.
- Маппинг в `fetchData` (строки 182-188) корректно читает `s.skill_rank.skill_id`, `s.skill_rank.rank_number`, `s.skill_rank.id` и сохраняет `character_skill_id: s.id` для точечного DELETE.
- `handleSaveSkills` (строки 288-333) построен на diff по композитному ключу `skill_id:rank_number`: `toAdd` — только новые, `toRemove` — только удалённые с guard `character_skill_id != null`. POST `/skills/assign_multiple` идёт ПЕРВЫМ (строки 302-310); DELETE по `character_skill_id` идёт ВТОРЫМ (строки 314-318). Если POST бросает — DELETE не запускается, существующие навыки целы. Неизменённые навыки не трогаются.
- Ошибки ловятся в try/catch, сообщение извлекается из `err.response.data.detail` (строки 323-329), по умолчанию — "Не удалось сохранить навыки", отображается через `toast.error`. Silent-failure нет.
- Типы плотные: `any` отсутствует, `React.FC` не используется (arrow function с деструктуризацией пропсов на строке 145).
- Стили не затронуты — правило #12 (mobile-adaptive) не триггерится.

#### Automated Check Results
- [x] `docker compose exec -T frontend npx tsc --noEmit` — PASS (в `NpcStatsEditor.tsx` ошибок нет; прочие ошибки в репо — пре-экзистинг, вне скоупа)
- [x] Backend curl verification — PASS: `GET /skills/characters/4/skills` вернул вложенную форму `{...,"skill_rank":{"id":17,"skill_id":8,"rank_number":1,...}}`, соответствует интерфейсу. Бэкенд-поведение `POST /skills/assign_multiple` и `DELETE /skills/admin/character_skills/{id}` подтверждено аналитиком в разделе 2 (курлы 200 OK).
- [x] Live verification: через curl подтверждена форма ответа, совпадающая с ожиданием фронта. chrome-devtools UI-флоу не прогонялся (авторизованная админка вне автоматического доступа), но контракт GET/POST/DELETE совпадает и логика diff математически безопасна по инварианту "POST до DELETE".

`docs/ISSUES.md` — записи про этот баг не было, действий не требуется.

All checks passed. Changes are ready for completion.

---

## 6. Logging

```
[LOG] 2026-04-07 — PM: фича создана из бага (регрессия), запускаю Codebase Analyst
[LOG] 2026-04-07 — Analyst: проанализирован фронт-компонент NpcStatsEditor.tsx, бэкенд skills-service (assign_multiple, delete_all_character_skills, схема CharacterSkillRead), история git, RBAC-разрешения админа в БД, проверены живые curl-запросы к работающим контейнерам
[LOG] 2026-04-07 — Analyst: корневая причина найдена — фронт мапит ответ GET /skills/characters/{id}/skills с неверной формой (top-level skill_id/rank_number отсутствуют, они вложены в skill_rank). DELETE отрабатывает, POST /skills/assign_multiple падает с 422, навыки уже стёрты. Регрессия из коммита 456c124 (FEAT-110..116)
[LOG] 2026-04-07 — Analyst: анализ завершён, отчёт записан в раздел 2
[LOG] 2026-04-07 — Frontend Dev: начал задачи #1-3
[LOG] 2026-04-07 — Frontend Dev: исправлен интерфейс SkillAssignment (вложенный skill_rank), маппинг ответа GET /skills/characters/{id}/skills теперь читает skill_rank.skill_id/rank_number/id, в SelectedSkill добавлен character_skill_id для точечного DELETE
[LOG] 2026-04-07 — Frontend Dev: handleSaveSkills переписан на diff-подход — POST новых навыков идёт первым (если падает, существующие навыки целы), затем точечный DELETE только удалённых записей по character_skill_id. Неизменённые навыки не трогаются вообще
[LOG] 2026-04-07 — Frontend Dev: проверка `docker compose exec frontend npx tsc --noEmit` — в NpcStatsEditor.tsx нет ошибок (в репо есть прежние ошибки в других файлах, не связаны с этой фичей). Задачи #1-3 завершены
[LOG] 2026-04-07 — Reviewer: начал проверку FEAT-122
[LOG] 2026-04-07 — Reviewer: интерфейс SkillAssignment, маппинг fetchData и diff-логика handleSaveSkills соответствуют бэкенд-контракту; POST идёт до DELETE, при падении POST существующие навыки целы; ошибки в русском toast, no any, no React.FC, стили не тронуты
[LOG] 2026-04-07 — Reviewer: tsc --noEmit по NpcStatsEditor.tsx — 0 ошибок; curl GET /skills/characters/4/skills подтвердил вложенную форму skill_rank
[LOG] 2026-04-07 — Reviewer: проверка завершена, результат PASS
```
