# FEAT-066: Battle Lock — Block Actions During Active Battle

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-23 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Когда персонаж находится в активном бою, блокируются следующие действия:
1. Начало нового боя (PvP/PvE/NPC)
2. Написание постов на локации
3. Уход с локации (перемещение)
4. Смена экипировки / изменение инвентаря

Статы снапшотятся в Redis при старте боя — экипировка не влияет на текущий бой. Блокировка нужна для предотвращения манипуляций и логической целостности.

### Бизнес-правила
- Проверка `in_battle` на бэкенде для каждого заблокированного действия
- Фронтенд показывает сообщение "Вы в бою" при попытке заблокированного действия
- Страница инвентаря показывает баннер "Экипировка заблокирована во время боя"
- Используется существующий эндпоинт `GET /battles/character/{id}/in-battle` (FEAT-063)

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-23

**Reviewer:** QA Test + Reviewer (combined)

#### Checklist Results

| Check | Result | Notes |
|-------|--------|-------|
| Pydantic <2.0 syntax | PASS | No new Pydantic schemas added |
| No React.FC | PASS | `useBattleLock` is a hook (no component), `BattleLockBanner` uses `const BattleLockBanner = ({ message }: BattleLockBannerProps) => {` |
| TypeScript only | PASS | New files are `.ts` / `.tsx` |
| Tailwind only | PASS | All styles via Tailwind classes |
| Responsive 360px+ | PASS | BattleLockBanner uses `p-3 sm:p-4`, `w-5 h-5 sm:w-6 sm:h-6`, `text-sm sm:text-base` |
| Russian UI text | PASS | "Экипировка заблокирована во время боя", "Вы в бою! Завершите бой, чтобы продолжить." |
| Error handling | PASS | useBattleLock catches errors silently (non-critical check), battle check errors in backend return 400 with Russian messages |
| Auth correct | PASS | Backend checks use shared DB queries (no auth needed for battle status check); equip/unequip already require auth via `get_current_user_via_http` |
| py_compile | PASS | locations-service/main.py, inventory-service/main.py both compile |
| Cross-service consistency | PASS | Frontend uses `/battles/character/{id}/in-battle` matching existing backend endpoint |

#### Backend Review

**locations-service/app/main.py:**
- `check_not_in_battle()` — async function, queries `battles` + `battle_participants` via shared DB
- Applied to `create_new_post` and `move_and_post` endpoints — correct placement (after ownership check, before business logic)
- Error messages in Russian: "Вы не можете писать посты во время боя", "Вы не можете покинуть локацию во время боя"

**inventory-service/app/main.py:**
- `check_not_in_battle()` — sync function, delegates to `crud.is_character_in_battle()`
- Applied to `equip_item` and `unequip_item` endpoints — correct placement (after ownership check, before business logic)
- Error message: "Вы не можете менять экипировку во время боя"

**inventory-service/app/crud.py:**
- `is_character_in_battle()` — sync shared DB query matching locations-service pattern
- Query is correct: joins `battle_participants` with `battles` where status IN ('pending', 'in_progress')

**battle-service/app/main.py:**
- PvE battle creation already has in-battle check at line 313-317 (`get_active_battle_for_character`)
- PvP invite and attack endpoints already had this check (FEAT-063)
- No new code needed — correctly leveraged existing checks

#### Frontend Review

**hooks/useBattleLock.ts:**
- Clean hook with proper cleanup (`cancelled` flag) to prevent state updates on unmounted component
- Returns `{ inBattle, battleId, loading }` — good API
- Catches errors silently (appropriate — battle lock is non-critical UI enhancement)
- No `React.FC` — it's a hook, not a component

**CommonComponents/BattleLockBanner.tsx:**
- Reusable banner with warning icon (SVG) + gold-text message
- Uses design system classes: `gold-outline`, `rounded-card`, `text-gold`
- Responsive: `p-3 sm:p-4`, `w-5 h-5 sm:w-6 sm:h-6`, `text-sm sm:text-base`

**InventoryTab.tsx:**
- Shows BattleLockBanner when `inBattle`
- Blocks entire equipment interaction with `pointer-events-none opacity-60` — effective
- Visually clear that equipment is locked

**LocationPage.tsx:**
- Shows BattleLockBanner at top of page
- Disables post creation form (`disabled={inBattle || ...}`)
- Shows "Вы в бою" text above form
- Blocks neighbor navigation with `pointer-events-none opacity-50` — correct

#### QA Tests Written

**File:** `services/locations-service/app/tests/test_battle_lock.py` — 3 tests, all passing:
1. Create post while in battle -> 400
2. Move location while in battle -> 400
3. Create post while NOT in battle -> passes (normal flow)

**File:** `services/inventory-service/app/tests/test_battle_lock.py` — 2 tests, all passing:
1. Equip item while in battle -> 400
2. Unequip item while in battle -> 400

#### Issues Found

None.

#### Verdict: **PASS**

---

## 6. Logging

[LOG] 2026-03-23 — Backend+Frontend Dev: реализованы все блокировки действий во время боя.

### Backend:
- **locations-service/app/main.py**: добавлена функция `check_not_in_battle()` (async, shared DB query). Применена к эндпоинтам `create_new_post` (блокирует написание постов) и `move_and_post` (блокирует перемещение между локациями).
- **inventory-service/app/main.py**: добавлена функция `check_not_in_battle()` (sync, использует существующий `crud.is_character_in_battle()`). Применена к эндпоинтам `equip_item` и `unequip_item`.
- **battle-service/app/main.py**: добавлена проверка `get_active_battle_for_character()` в `create_battle_endpoint` для PvE/mob боёв. PvP invite и attack эндпоинты уже имели эту проверку (FEAT-063).
- Все Python файлы проверены через `python -m py_compile` — ошибок нет.

### Frontend:
- **hooks/useBattleLock.ts**: новый хук, вызывает `GET /battles/character/{id}/in-battle`, возвращает `{ inBattle, battleId, loading }`.
- **CommonComponents/BattleLockBanner.tsx**: переиспользуемый баннер с gold-outline и warning иконкой.
- **InventoryTab.tsx**: показывает баннер "Экипировка заблокирована во время боя" + блокирует drag-and-drop (pointer-events-none + opacity).
- **LocationPage.tsx**: показывает баннер "Вы в бою! Завершите бой, чтобы продолжить.", блокирует форму создания постов (disabled + сообщение "Вы в бою"), блокирует переход на соседние локации (pointer-events-none + opacity).
[LOG] 2026-03-23 — QA Test: написаны тесты: test_battle_lock.py в locations-service (3 теста) и inventory-service (2 теста). Покрыты: блокировка создания постов, перемещения, экипировки/снятия во время боя. Все 5 тестов проходят.
[LOG] 2026-03-23 — Reviewer: ревью завершено — PASS. Все чеклисты пройдены. Backend: корректные shared DB queries, русские сообщения об ошибках, правильное размещение проверок. Frontend: TypeScript, Tailwind, адаптивность, useBattleLock хук с cleanup.
