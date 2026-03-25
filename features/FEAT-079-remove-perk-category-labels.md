# FEAT-079: Убрать надписи категорий с публичной карты перков

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-25 |
| **Author** | PM (Orchestrator) |
| **Priority** | LOW |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-079-remove-perk-category-labels.md` → `DONE-FEAT-079-remove-perk-category-labels.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Убрать текстовые надписи категорий ("Бой", "Торговля", "Исследование" и т.д.) с публичной карты перков в профиле персонажа. Надписи визуально не нравятся, карта должна быть чище.

### Бизнес-правила
- Убрать только текстовые лейблы категорий на публичном виде карты перков
- Остальная функциональность карты не меняется

### UX / Пользовательский сценарий
1. Игрок открывает карту перков
2. Видит дерево перков без текстовых надписей категорий
3. Перки по-прежнему группированы визуально, просто без текстовых подписей

---

## 2–3. Analysis & Architecture

Skipped — trivial frontend-only UI change. Remove category label rendering from perk tree component.

---

## 4. Tasks

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Remove category labels from public perk map | Frontend Developer | TODO | PerkTree component | — | No category text labels visible on public perk map |
| 2 | Review | Reviewer | TODO | all | #1 | Build passes, no visual regression |

---

## 5. Review Log

_(pending)_

---

## 6. Logging

```
[LOG] 2026-03-25 — PM: фича создана, запускаю фронтенд-разработчика
[LOG] 2026-03-25 — Frontend Dev: начал задачу #1. Нашёл компонент PerkTree.tsx, убрал SVG-рендеринг текстовых лейблов категорий (строки 533-553) и неиспользуемый useMemo categoryLabels (строки 382-403). Мобильный вид (flat list) оставлен без изменений — там лейблы служат заголовками секций. Node.js не доступен в окружении, проверка tsc/build невозможна, но изменение тривиальное (удаление JSX и memo). Задача #1 завершена.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

_(pending)_
