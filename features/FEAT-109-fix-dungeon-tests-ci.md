# FEAT-109: Fix dungeon-service tests hanging in CI

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-03-30 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
CI/CD пайплайн зависает на тестах dungeon-service. Предыдущий коммит (3cce6ee) удалил `tests/__init__.py`, чтобы починить `from conftest import`, но теперь тесты зависают вместо быстрого падения.

### Проблемы
1. `test_admin_crud.py` и `test_room_positions.py` используют `from conftest import` — антипаттерн для pytest
2. `test_gameplay.py` ссылается на фикстуры (`mock_db`, `sample_session`, `sample_dungeon` и др.), которых нет в `conftest.py`
3. После удаления `__init__.py` все 83 теста собираются, но что-то зависает при выполнении

### Ожидаемый результат
- Все тесты dungeon-service проходят в CI без зависания
- CI pipeline завершается успешно

---

## 2. Analysis Report

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| dungeon-service | test fixes | `app/tests/conftest.py`, `app/tests/test_admin_crud.py`, `app/tests/test_room_positions.py`, `app/tests/test_gameplay.py` |

### Root Causes (from CI logs)
1. **FEAT-108 CI run (23761454174):** `from conftest import` caused `ModuleNotFoundError` — 83 items / 2 errors, fast fail
2. **Fix commit CI run (23761579309):** `__init__.py` removed → 0 collection errors → all tests run → **hang** on dungeon-service

### Key findings
- `test_gameplay.py` has 31 tests referencing fixtures: `mock_db`, `sample_session`, `sample_dungeon`, `sample_corridor`, `sample_redis_state`, `sample_room`, `sample_room_state` — NONE defined in conftest.py
- `test_sessions.py` and `test_session_state_map.py` define their OWN `mock_db` locally
- CI uses: Python 3.10.20, pytest 9.0.2, pytest-asyncio 1.3.0

---

## 4. Tasks

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Fix all dungeon-service test issues so CI passes | Backend Developer | TODO | `tests/*` | — | `pytest tests/ --asyncio-mode=auto -v` passes, no hangs |

---

## 6. Logging

```
[LOG] 2026-03-30 22:25 — PM: CI зависает на dungeon-service тестах, ран отменён, начато расследование
[LOG] 2026-03-30 22:30 — PM: анализ завершён — 3 проблемы найдены, запускаю Backend Developer
[LOG] 2026-03-30 22:45 — Backend Dev: начал задачу #1 — исправление тестов dungeon-service
[LOG] 2026-03-30 23:00 — Backend Dev: задача #1 завершена, изменено 6 файлов:
  - создан tests/helpers.py (вынесены _dungeon_payload, _room_payload, _corridor_payload из conftest)
  - conftest.py: импорт хелперов из helpers.py, добавлены 7 фикстур для test_gameplay.py (mock_db, sample_session, sample_dungeon, sample_corridor, sample_room, sample_room_state, sample_redis_state)
  - test_admin_crud.py: `from conftest import` → `from helpers import`
  - test_room_positions.py: `from conftest import` → `from helpers import`
  - requirements.txt: добавлен pytest-timeout
  - ci.yml: добавлен --timeout=30 для dungeon-service
```

---

## Phase 2 — Fix 14 failing tests (2026-03-30)

```
[LOG] 2026-03-30 23:30 — Backend Dev: начал исправление 14 падающих тестов
[LOG] 2026-03-30 23:55 — Backend Dev: исправлено 14 тестов в 4 файлах:

test_boss_chest_bugfix.py (6 fixes):
  - TestBossLootKeyFix (2 tests): добавлен mock_ss.update_session_state = AsyncMock() —
    _handle_open_chest для boss rooms вызывает update_session_state, который не был замокан
  - TestItemNamePopulation (2 tests): исправлен маппинг db.execute вызовов —
    _get_room_exits делает 3 вызова (corridors_from, corridors_to, visits), а не 1.
    Также добавлены name, location_id, stability_type, position_x/y в _make_dungeon/_make_room
  - TestTerminalStateGuard (2 tests): аналогичное исправление маппинга db.execute +
    добавлен второй участник team 2 в battle_state чтобы бой считался незавершённым

test_gameplay.py (1 fix):
  - test_initiate_room_battle: spawn_dungeon_mobs вызывается с dungeon.location_id=100, не 10

test_session_state_map.py (3 fixes):
  - TestSessionStateExploredRooms (3 tests): исправлен маппинг db.execute —
    _get_room_exits потребляет idx 5-7, inventory = idx 8, explored_rooms = idx 9

test_sessions.py (4 fixes):
  - TestInviteMember::test_invite_member_success: добавлен 3-й db.execute вызов для
    _build_session_response (запрос members из БД)
  - TestLeaveSession (2 tests): аналогично — db.execute side_effect вместо single return,
    чтобы _build_session_response получал список members, а не объект session
  - TestEnterDungeon::test_enter_dungeon_success: добавлены db.execute вызовы для
    member_count, members_list, existing_visit (enter_dungeon делает 5 DB вызовов до get_session_state)
```

