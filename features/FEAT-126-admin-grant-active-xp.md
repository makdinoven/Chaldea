# FEAT-126: Админская выдача активного опыта + отображение в профиле

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-04-08 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief

### Описание
Запрос пользователя: "Добавь возможность персонажам через админку накидывать активный опыт, который используется для прокачки навыков. И выведи отображение количества опыта в профиль персонажа, возле золота."

Активный опыт (`character_attributes.active_experience`) используется для прокачки навыков. Админам нужен механизм выдавать/снимать его произвольному персонажу. Дополнительно игроки должны видеть своё текущее количество активного опыта в профиле персонажа — рядом с золотом.

### Бизнес-правила
- Выдавать активный опыт может только админ (разрешение `characters:update`).
- Поддерживается как выдача (`delta > 0`), так и снятие (`delta < 0`).
- Итоговое значение клампается до 0 — активный опыт не может быть отрицательным.
- Операция логируется в `character-service` как `admin_experience_change`.
- Отображение в профиле — read-only, показывает текущее значение `active_experience`.

### Edge Cases
- Персонаж без строки в `character_attributes` → 404.
- Очень большое отрицательное `delta` → клампается до 0, не падает.

---

## 2. Analysis Report

### Affected Services
| Service | Type of Changes | Files |
|---------|-----------------|-------|
| character-attributes-service | new admin endpoint | `app/schemas.py`, `app/crud.py`, `app/main.py` |
| frontend | admin UI + profile readout | TBD |

### Existing Patterns
- Sync SQLAlchemy service, router prefix `/attributes`.
- Admin auth: `Depends(require_permission("characters:update"))` from `auth_http.py`.
- Experience changes already logged via fire-and-forget HTTP to `character-service`.

---

## 3. Architecture Decision

### API Contract

#### `POST /attributes/admin/{character_id}/grant_active_xp`
Auth: admin (`characters:update`).

**Request:**
```json
{ "delta": 100 }
```
**Response 200:**
```json
{ "character_id": 1, "active_experience": 100 }
```
**Errors:** 404 if attributes row not found.

Delta semantics: added to current value, result clamped at 0.

---

## 4. Tasks

| # | Description | Agent | Status | Files | Depends On |
|---|-------------|-------|--------|-------|------------|
| 1 | Backend admin endpoint `POST /attributes/admin/{character_id}/grant_active_xp` | Backend Developer | DONE | `schemas.py`, `crud.py`, `main.py` | — |
| 2 | Admin UI: input/button to grant active_experience on character admin page | Frontend Developer | DONE | `AttributesTab.tsx`, `api/adminCharacters.ts` | #1 |
| 3 | Profile display: показать текущий active_experience рядом с золотом | Frontend Developer | DONE | `ProfilePage/CharacterInfoPanel/CharacterCard.tsx`, `redux/slices/profileSlice.ts` | — |

---

## 6. Logging

```
[LOG] 2026-04-08 — PM: фича создана по запросу пользователя, задача #1 отдана Backend Dev
[LOG] 2026-04-08 — Backend Dev: добавлен endpoint POST /attributes/admin/{character_id}/grant_active_xp, schemas GrantActiveXpRequest/Response, crud.grant_active_experience (sync, with_for_update, clamp >= 0)
[LOG] 2026-04-08 — Backend Dev: py_compile OK, сервис перезапущен, логи чистые
[LOG] 2026-04-08 — Backend Dev: smoke-тесты на char_id=1: delta=+100 → 100, delta=-50 → 50, delta=-99999 → 0 (clamp сработал). Задача #1 DONE
[LOG] 2026-04-08 — Frontend Dev: задача #2 — в AttributesTab добавлена секция "Выдача активного опыта" (поле с default=100, кнопка "Изменить опыт"), api-метод grantActiveXp, тост с новым значением или с detail из 4xx. tsc по тронутым файлам чистый, npm run build OK. Задача #2 DONE
[LOG] 2026-04-08 — Frontend Dev: задача #3 — в тип CharacterAttributes добавлено поле active_experience (уже приходит из /attributes/{id}), в CharacterCard через selectAttributes выведен блок "Опыт:" рядом с золотом (flex-wrap, Tailwind, gold-text, адаптивно). tsc по затронутым файлам чистый, npm run build OK. Задача #3 DONE, статус фичи → REVIEW.
[LOG] 2026-04-08 — Frontend Dev: доп. фикс — в LeftColumn.tsx (вкладка "Персонаж" на ProfilePage) добавлен блок "Опыт:" рядом с золотом по аналогии с CharacterCard (flex-wrap, gold-text, toLocaleString ru-RU, адаптивно). tsc по LeftColumn чистый, npm run build OK.
```

---

## 7. Completion Summary

Ожидает завершения задач #2 и #3.
