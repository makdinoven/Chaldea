# FEAT-087: Система идентификации предметов + свитки книжника

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-087-identification-system.md` → `DONE-FEAT-087-identification-system.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Система неопознанных предметов. Предметы могут выпадать с мобов как "неопознанные" — игрок видит название и тип, но не видит статы. Неопознанный предмет нельзя экипировать. Для опознания нужен свиток идентификации, который крафтит книжник. Любой игрок может использовать свиток.

### Механика идентификации
- Предмет в инвентаре может быть отмечен как `is_identified = false`
- Неопознанный предмет: видно название, тип, редкость, изображение. Статы/модификаторы скрыты ("???")
- Неопознанный предмет **нельзя экипировать**
- Игрок нажимает "Опознать" на неопознанном предмете
- Если в инвентаре есть подходящий свиток — расходуется 1 свиток, предмет становится опознанным
- Если свитка нет — ошибка "Нет свитка идентификации"

### Свитки идентификации
Свитки разного качества для предметов разной редкости:

| Свиток | Опознаёт предметы редкости | item_rarity свитка |
|--------|---------------------------|-------------------|
| Свиток идентификации (обычный) | common, rare | common |
| Свиток идентификации (редкий) | epic, mythical | rare |
| Свиток идентификации (легендарный) | legendary, divine, demonic | legendary |

- Свитки — предметы item_type = "scroll", с маркером (поле `identify_max_rarity` или подобное)
- Книжник крафтит свитки по рецептам
- Свитки торгуются как обычные предметы

### Выпадение неопознанных предметов
- При выдаче предмета через лут (мобы, данжи) — можно пометить как неопознанный
- Не все предметы неопознанные — это настраивается при выдаче
- Ресурсы, расходники, свитки — всегда опознаны
- Админ может выдать предмет как опознанный или нет

### Бизнес-правила
- `is_identified` хранится per-instance на `character_inventory` (default True для совместимости)
- Любой игрок может использовать свиток (не только книжник)
- Свиток должен покрывать редкость предмета
- Свиток расходуется при опознании
- Торговля/обмен неопознанными предметами разрешена (покупатель получает неопознанный)
- Заточка/вставка камней в неопознанный предмет запрещена

### UX / Пользовательский сценарий
1. Игрок получает предмет с моба — в инвентаре он отмечен как "???" (неопознанный)
2. Видит название и тип, но статы скрыты
3. Нажимает правой кнопкой → "Опознать"
4. Система находит подходящий свиток в инвентаре
5. Подтверждение: "Потратить [свиток] для опознания [предмет]?"
6. Свиток расходуется, предмет опознан, статы видны
7. Теперь предмет можно экипировать

### Edge Cases
- Что если нет подходящего свитка? → Ошибка "Нет свитка идентификации для этой редкости"
- Что если предмет уже опознан? → Кнопка "Опознать" не показывается
- Что если пытается экипировать неопознанный? → Ошибка "Предмет не опознан"
- Что если пытается заточить неопознанный? → Ошибка "Предмет не опознан"

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

**Affected services:** inventory-service (backend), frontend (React)

**DB changes:**
- `character_inventory.is_identified` — Boolean, default True, backwards compatible
- `items.identify_level` — Integer, nullable, marks scroll items (1/2/3)
- 3 seed scroll items (item_type=scroll, identify_level=1/2/3)

**Cross-service impact:** Minimal. Other services read `character_inventory` but don't use `is_identified`. The column defaults to True so all existing items remain identified.

**Endpoints affected:**
- `POST /inventory/{cid}/identify` — new
- `POST /inventory/{cid}/equip` — added is_identified check
- `POST /inventory/{cid}/sharpen` — added is_identified check (inventory only)
- `POST /inventory/{cid}/gems/insert` — added is_identified check (inventory only)

---

## 3. Architecture Decision (filled by Architect — in English)

**Approach:** `is_identified` stored per-instance on `character_inventory` (not on `items`). This allows the same item definition to have both identified and unidentified instances in different inventories.

**Rarity → identify_level mapping:**
- Level 1: common, rare
- Level 2: epic, mythical
- Level 3: legendary, divine, demonic

**Scroll matching:** A scroll with identify_level >= required level can identify the item. The cheapest matching scroll is consumed first.

**Frontend:** Unidentified items show "???" overlay with greyscale, context menu shows "Опознать" action with confirmation modal. Double-click equip is blocked for unidentified items.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

- [x] T1: Alembic migration 011 — add is_identified, identify_level, seed scrolls
- [x] T2: Update models.py — add fields to CharacterInventory and Items
- [x] T3: Update schemas.py — add fields + IdentifyRequest/IdentifyResult
- [x] T4: Update crud.py — add RARITY_IDENTIFY_LEVEL mapping, find_identification_scroll
- [x] T5: Add POST /inventory/{cid}/identify endpoint
- [x] T6: Add is_identified checks to equip, sharpen, insert-gem endpoints
- [x] T7: Update profileSlice.ts — add is_identified to InventoryItem, identify_level to ItemData, identifyItem thunk
- [x] T8: Update ItemCell.tsx — greyscale + "???" overlay for unidentified items
- [x] T9: Update ItemContextMenu.tsx — "Опознать" action with confirmation

---

## 5. Review Log (filled by Reviewer — in English)

*Pending...*

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-26 — PM: фича создана, запускаю реализацию
[LOG] 2026-03-26 — Full-Stack Dev: реализована полная система идентификации — бэкенд (миграция, модели, схемы, эндпоинт, валидации) + фронтенд (визуальный индикатор, контекстное меню, Redux thunk)
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
