# FEAT-085: Алхимик — трансмутация материалов

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-085-alchemist-transmutation.md` → `DONE-FEAT-085-alchemist-transmutation.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Алхимик может преобразовывать материалы — конвертировать несколько обычных ресурсов в один более редкий. Это создаёт ценность для алхимика как переработчика ресурсов.

### Механика трансмутации
- Алхимик выбирает ресурс из своего инвентаря
- Указывает количество для трансмутации (минимум N штук)
- Получает 1 ресурс следующей редкости
- Формула: 5 ресурсов одной редкости → 1 ресурс следующей редкости (того же типа, если есть, или универсальный)

### Цепочка редкости
common (5шт) → rare (5шт) → epic (5шт) → legendary (5шт) → mythical

### Бизнес-правила
- Только алхимик может трансмутировать
- Нужно минимум 5 единиц одного ресурса
- Результат — 1 единица того же ресурса, но следующей редкости
- Если ресурс уже mythical/divine/demonic — трансмутация невозможна
- Трансмутация всегда успешна (без шанса неудачи)
- Даёт XP профессии (15 XP за трансмутацию)

### UX / Пользовательский сценарий
1. Алхимик открывает таб "Крафт"
2. Видит раздел "Трансмутация" (рядом с экстракцией)
3. Видит ресурсы из инвентаря с количеством
4. Выбирает ресурс, видит: "5x Железная руда (common) → 1x Железная руда (rare)"
5. Нажимает "Трансмутировать"
6. 5 обычных ресурсов исчезают, 1 редкий появляется

### Edge Cases
- Что если ресурс уже максимальной редкости? → Не показывать кнопку трансмутации
- Что если менее 5 единиц? → Кнопка неактивна, показать "Нужно минимум 5"
- Что если ресурс не стакается (max_stack=1)? → Нужно 5 отдельных стаков

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected services
- **inventory-service** — new endpoints + migration (owns crafting/profession logic)
- **frontend** — new TransmutationSection component, Redux state, API layer

### Existing patterns used
- Essence extraction (FEAT-084): same endpoint structure, auth checks, XP award, rank-up logic
- Alembic migration chain: 008 -> 009
- Frontend: EssenceExtractionSection pattern (Redux thunk + component)

### Design decision
Transmutation produces generic "Transmuted Resource" items (4 pre-seeded, one per target rarity) rather than trying to create same-name items with different rarities. This avoids item catalog bloat and complex item cloning logic.

---

## 3. Architecture Decision (filled by Architect — in English)

### Backend
- **Migration 009**: Seeds 4 transmuted resource items (rare, epic, legendary, mythical)
- **GET /inventory/crafting/{character_id}/transmute-info**: Returns all resource items with transmutable rarity
- **POST /inventory/crafting/{character_id}/transmute**: Consumes 5 resources, produces 1 higher-rarity generic resource, awards 15 XP
- Rarity chain: common->rare->epic->legendary->mythical (divine/demonic excluded)
- Constants: TRANSMUTE_COST=5, TRANSMUTE_XP=15

### Frontend
- TransmutationSection.tsx: grid of transmutable resources with rarity badges, conversion preview, transmute button
- Shown for alchemists in CraftTab (after EssenceExtractionSection)
- Redux: transmuteInfo/transmuteLoading/transmuteError state + thunks + selectors

---

## 4. Tasks (filled by Architect, updated by PM — in English)

- [x] T1: Alembic migration 009 — seed 4 transmuted resource items
- [x] T2: Backend schemas (TransmuteRequest, TransmuteResult, TransmuteItemInfo, TransmuteInfoResponse)
- [x] T3: Backend endpoints (transmute-info GET, transmute POST)
- [x] T4: Frontend types (TransmuteItemInfo, TransmuteInfoResponse, TransmuteRequest, TransmuteResult)
- [x] T5: Frontend API functions (fetchTransmuteInfo, transmuteItem)
- [x] T6: Redux slice (state, thunks, selectors for transmutation)
- [x] T7: TransmutationSection.tsx component
- [x] T8: CraftTab.tsx integration

---

## 5. Review Log (filled by Reviewer — in English)

*Pending...*

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-26 — PM: фича создана, запускаю реализацию
[LOG] 2026-03-26 — Full-Stack Dev: реализация завершена — миграция 009, бэкенд эндпоинты (transmute-info, transmute), фронтенд (типы, API, Redux, TransmutationSection, интеграция в CraftTab). Python py_compile пройден.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
