# FEAT-088: Книжник — книги опыта (тайм-баффы)

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-088-xp-books-time-buffs.md` → `DONE-FEAT-088-xp-books-time-buffs.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Книжник крафтит книги опыта — расходуемые предметы, дающие временный бонус к получаемому XP. Это первая реализация системы тайм-баффов в игре.

### Механика
- Книжник создаёт книги опыта по рецептам (через существующую систему крафта)
- Любой игрок может использовать книгу из инвентаря
- При использовании: книга расходуется, активируется бафф "+N% XP" на M минут
- Бафф действует на XP персонажа (XP за убийство мобов — когда система будет, пока только XP профессии за крафт)
- Одновременно может быть активен только один бафф XP (новый заменяет старый)

### Типы книг опыта (примеры, создаются через админку)
| Книга | Бонус XP | Длительность | Редкость |
|-------|----------|-------------|----------|
| Книга ученика | +25% | 30 минут | common |
| Книга знаний | +50% | 30 минут | rare |
| Книга мудрости | +100% | 30 минут | epic |
| Великий том знаний | +50% | 60 минут | legendary |

### Система тайм-баффов (новая, универсальная)
- Новая таблица `active_buffs` в inventory-service:
  - `id`, `character_id`, `buff_type` (строка, например "xp_bonus"), `value` (float, например 0.25 для +25%), `expires_at` (datetime), `source_item_name` (строка), `created_at`
- При проверке баффа: если `expires_at > now()` — бафф активен
- Просроченные баффы удаляются при следующем запросе или по крону
- Система универсальна — в будущем можно добавить другие баффы (скорость, удача и т.д.)

### Поля на предметах для книг
- Книги — item_type = "consumable" (или новый тип "book")
- Нужны новые поля на items: `buff_type` (string, nullable), `buff_value` (float, nullable), `buff_duration_minutes` (int, nullable)
- Если эти поля заполнены — предмет является баффовым

### Применение бонуса XP
- При крафте (execute_craft, sharpen, extract-essence, transmute) — проверить активный бафф "xp_bonus"
- Если есть: `xp_earned = base_xp * (1 + buff_value)`
- Пример: base 10 XP, бафф +50% → 10 * 1.5 = 15 XP

### Бизнес-правила
- Любой игрок может использовать книгу (не только книжник)
- Книжник крафтит книги по рецептам
- Один активный XP-бафф одновременно (новый заменяет старый)
- Бафф привязан к персонажу, не к аккаунту
- Длительность начинается с момента использования
- Бафф виден в UI (иконка + таймер обратного отсчёта)

### UX / Пользовательский сценарий
1. Игрок получает книгу опыта (крафт/покупка/обмен)
2. В инвентаре правый клик → "Использовать"
3. Книга расходуется, появляется бафф
4. На экране виден индикатор баффа: "+50% XP | 29:45"
5. XP за крафт увеличивается пока бафф активен
6. Когда время истекает — бафф исчезает, индикатор пропадает

### Edge Cases
- Что если уже есть активный бафф? → Заменяется новым
- Что если бафф истёк? → Автоматически перестаёт действовать
- Что если сервер перезапустился? → Бафф хранится в БД с expires_at, восстанавливается

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected services
- **inventory-service** — main service: new table, new columns on items, new endpoints, XP multiplier integration
- **frontend** — profileSlice state/thunks, ItemContextMenu buff action, ActiveBuffIndicator component in CraftTab

### XP award locations (all in inventory-service)
1. `crud.py:execute_craft()` — recipe XP reward (line ~1587)
2. `main.py` sharpen endpoint — fixed 10 XP (line ~1927)
3. `main.py` extract-essence endpoint — fixed 10 XP (line ~2099)
4. `main.py` transmute endpoint — TRANSMUTE_XP (line ~2287)
5. `main.py` insert-gem endpoint — GEM_XP_REWARD (line ~2539)
6. `main.py` extract-gem endpoint — GEM_XP_REWARD (line ~2676)
7. `main.py` smelt endpoint — GEM_XP_REWARD (line ~2856)

### DB impact
- New table: `active_buffs` (character_id, buff_type, value, expires_at, source_item_name)
- New columns on `items`: buff_type, buff_value, buff_duration_minutes

### No cross-service impact
All changes are within inventory-service + frontend. No API contract changes for other services.

---

## 3. Architecture Decision (filled by Architect — in English)

### Approach
- Universal time-buff system via `active_buffs` table with UNIQUE(character_id, buff_type)
- Buff items are regular `items` with `buff_type`/`buff_value`/`buff_duration_minutes` fields set
- XP multiplier applied at each XP-awarding location via `crud.get_xp_multiplier()`
- Expired buffs cleaned up lazily on read queries
- Frontend: countdown timer via `setInterval`, auto-refresh on expiry

### API
- `POST /inventory/{character_id}/use-buff-item` — consume item, activate buff
- `GET /inventory/{character_id}/active-buffs` — list active buffs with remaining_seconds

---

## 4. Tasks (filled by Architect, updated by PM — in English)

- [x] Migration 012: active_buffs table + buff columns on items
- [x] Models: ActiveBuff model, buff fields on Items
- [x] Schemas: ActiveBuffOut, UseBuffItemRequest, UseBuffItemResult, ActiveBuffsResponse
- [x] CRUD: get_active_buff, apply_buff, get_active_buffs, get_xp_multiplier
- [x] XP multiplier integration in all 7 XP-awarding locations
- [x] Endpoint: POST use-buff-item
- [x] Endpoint: GET active-buffs
- [x] Frontend: ActiveBuff types + profileSlice state/thunks/selectors
- [x] Frontend: ActiveBuffIndicator component with countdown timer
- [x] Frontend: ItemContextMenu buff item action
- [x] Frontend: CraftTab integration

---

## 5. Review Log (filled by Reviewer — in English)

*Pending...*

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-26 — PM: фича создана, запускаю реализацию
[LOG] 2026-03-26 — Full-Stack Dev: реализован backend (миграция, модели, схемы, CRUD, эндпоинты, XP множитель во всех 7 местах)
[LOG] 2026-03-26 — Full-Stack Dev: реализован frontend (типы, thunks, ActiveBuffIndicator, ItemContextMenu с поддержкой баффов)
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
