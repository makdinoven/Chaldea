# FEAT-178: Походный рюкзак и инвентарь подземелья

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-10-25 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
По опыту прохождения: найденное в рейде использовать нельзя, а из своего инвентаря в данже доступно вообще всё.
Вводим «Походный рюкзак» — то, что персонаж берёт с собой, и переделываем инвентарь подземелья в иконки с контекстным меню.

### Бизнес-правила
- Рюкзак — предмет-плащ (надевается в слот «Плащ») с отметкой «Походный рюкзак». Продаётся, выдаётся и т.д., как обычный предмет.
- Вместимость по редкости: обычный 4, редкий 6, эпический 8, легендарный и выше 10 слотов (слот = стопка).
- В рюкзак кладутся только расходники. Складывать и выкладывать — только вне подземелья.
- В подземелье из своего инвентаря доступно только содержимое рюкзака: использовать вне боя, переложить в быстрый слот вне боя.
- В бою — как раньше, с пояса (быстрые слоты).
- Лидер может сразу передать участнику найденный расходник — он ложится в рюкзак участника (нет места/рюкзака — нельзя).
- Снятый или заменённый рюкзак (вне подземелья) отдаёт содержимое в инвентарь. В подземелье рюкзак не снять.
- Инвентарь подземелья: иконки, сетка, контекстное меню по клику.

### Вопросы к пользователю
- [x] Что класть → только расходники
- [x] Бой → с пояса; вне боя → из рюкзака, из рюкзака можно в быстрый слот
- [x] Пояс в бою → как есть
- [x] Как получать → продаётся, выдаётся
- [x] Вместимость → 4/6/8/10
- [x] Слот → «Плащ»

---

## 3. Design (English)

- `items.is_backpack` (bool) on cloak items; capacity derived from rarity (`backpack_capacity`).
- `character_backpack` table (character_id, item_id, quantity) — packed items live outside `character_inventory`,
  so trades, sales, auction and crafting never touch them.
- inventory-service: GET backpack, pack/unpack (outside a run), internal add (dungeon give), `from_backpack`
  on use_item / use-buff-item / eat-food / equip (fast slot). In a dungeon run the bag is closed: only backpack rows.
  Fast slot item unequipped in a run goes back to the backpack.
- dungeon-service: leader gives a found consumable to a member's backpack.
- frontend: admin item checkbox; backpack in the profile inventory; dungeon inventory redesign (grid + context menu).

## 6. Logging

[LOG] 2026-10-25 — PM: фича открыта, правила согласованы с пользователем
[LOG] 2026-10-25 — Backend: inventory-service — рюкзак (миграция 028, backpack.py, эндпоинты, закрытая сумка в забеге), 19 тестов; dungeon-service — передача находок лидером, 8 тестов
[LOG] 2026-10-25 — Frontend: галочка в админке предметов, рюкзак в профиле, новый инвентарь данжа (иконки, меню по клику)
[LOG] 2026-10-25 — PM: живая проверка на локальном забеге: передача себе/участнику без рюкзака, на пояс и обратно, использование из рюкзака
