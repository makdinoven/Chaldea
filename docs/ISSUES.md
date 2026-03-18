# Chaldea - Known Issues & Tech Debt

Файл с известными проблемами, багами и техническим долгом. Приоритеты: CRITICAL / HIGH / MEDIUM / LOW.

---

## CRITICAL

### 2. Эндпоинты без аутентификации (частично решено)
**Сервисы:** character-service, skills-service, inventory-service, locations-service, photo-service, character-attributes-service
**Описание:** Admin-эндпоинты теперь защищены JWT с проверкой роли (FEAT-011). Однако не-admin эндпоинты по-прежнему не требуют токена. Любой может:
- Менять текущего персонажа любого юзера (`PUT /users/{id}/update_character`)
- Загружать аватар любого пользователя (`POST /photo/change_user_avatar_photo`)
- Прокачивать атрибуты чужих персонажей
**Решение:** Добавить middleware или dependency для проверки JWT на пользовательских эндпоинтах во всех сервисах.

---

## HIGH

### 3. Баг: бой не завершается при HP <= 0
**Сервис:** battle-service
**Файл:** `services/battle-service/app/main.py`
**Описание:** Нет проверки, что HP участника упало до 0 или ниже. Бой продолжается бесконечно, урон уходит в отрицательные значения. Фронтенд сам проверяет HP и показывает modal, но на бэкенде бой не завершается (status не меняется на "finished").
**Решение:** После применения урона проверять HP <= 0, ставить `battle.status = "finished"`, возвращать winner в response.

### 4. Баг: кулдаун навыков не обновляется в dict
**Сервис:** battle-service
**Файл:** `services/battle-service/app/battle_engine.py:205`
**Описание:** `remaining -= 1` изменяет локальную переменную, но не записывает обратно в словарь кулдаунов. Навыки с кулдауном могут использоваться каждый ход.
**Решение:** `cd_map[rank_id] = remaining - 1`

### 5. Баг: дублирование enemy_effects в бою
**Сервис:** battle-service
**Файл:** `services/battle-service/app/main.py:478-501`
**Описание:** Enemy-эффекты применяются дважды (copy-paste ошибка). Дебаффы на врага работают с двойной силой.
**Решение:** Удалить дублирующий блок (строки 490-501).

### 6. Memory leak в autobattle-service
**Сервис:** autobattle-service
**Файл:** `services/autobattle-service/app/main.py`
**Описание:** `LAST_STATS` dict растёт бесконечно — записи никогда не удаляются после завершения боя. При длительной работе сервис будет потреблять всё больше памяти.
**Решение:** Очищать записи для (battle_id, pid) при завершении боя, или использовать TTL-cache (например `cachetools.TTLCache`).

### A-029-1. GET /users/all exposes hashed_password and email to unauthenticated users
**Сервис:** user-service
**Файл:** `services/user-service/main.py` (endpoint `GET /users/all`, line ~296)
**Описание:** `GET /users/all` returns raw ORM objects without a `response_model`, meaning all User fields including `hashed_password` and `email` are sent in the API response. The endpoint requires no authentication, so anyone can retrieve all user emails and password hashes.
**Решение:** Add `response_model` with a safe schema (exclude `hashed_password`, `email`) or add explicit field selection in the query.

### 7. Баг: shield нельзя экипировать через API
**Сервис:** inventory-service
**Файл:** `services/inventory-service/app/crud.py:98-107`
**Описание:** Функция `find_equipment_slot_for_item()` не включает `shield` в словарь `fixed`, хотя слот `shield` существует в `EquipmentSlot` и на фронтенде. При попытке экипировать щит, бэкенд ищет fast_slot (как для consumable), вместо слота `shield`. Функция `is_item_compatible_with_slot()` корректно включает shield, но она не используется в `find_equipment_slot_for_item`.
**Решение:** Добавить `'shield': 'shield'` в словарь `fixed` в `find_equipment_slot_for_item()`.

---

## MEDIUM

### 10. photo-service: bare except и отсутствие валидации файлов
**Сервис:** photo-service
**Файл:** `services/photo-service/crud.py` (main.py уже исправлен на `except Exception`)
**Описание:** В `crud.py` используются `except:` без типа исключения (10 мест — ловит SystemExit, KeyboardInterrupt). Нет валидации MIME-type загружаемых файлов — принимается любой файл.
**Решение:** Использовать `except Exception:` в crud.py, добавить проверку content-type и расширения файла.

### 11. Celery подавляет ошибки при записи логов боёв
**Сервис:** battle-service
**Файл:** `services/battle-service/app/tasks.py:29`
**Описание:** `contextlib.suppress(Exception)` маскирует любые ошибки записи в MongoDB/Redis. Логи боёв могут теряться без каких-либо следов.
**Решение:** Заменить на try/except с логированием ошибки.

### 13. Опечатки в названиях полей БД
**Сервис:** character-attributes-service
**Файл:** `services/character-attributes-service/app/models.py`
**Описание:** `res_catting` (вероятно `res_cutting`), `res_watering` (вероятно `res_water`), `res_sainting` (вероятно `res_holy`). Эти же названия продублированы в inventory-service (модификаторы предметов) и battle-service (расчёт урона).
**Решение:** Миграция БД для переименования полей + обновление кода во всех сервисах.

### 14. Синтаксическая ошибка в redis_state.py
**Сервис:** battle-service
**Файл:** `services/battle-service/app/redis_state.py:91-92`
**Описание:** Пропущена закрывающая скобка в dict comprehension при инициализации state.
**Решение:** Исправить синтаксис.

### 15. Polling вместо WebSocket на BattlePage
**Сервис:** frontend
**Файл:** `src/components/pages/BattlePage/BattlePage.jsx`
**Описание:** BattlePage опрашивает `GET /battles/{id}/state` каждые 5 секунд. Redis Pub/Sub уже используется на бэкенде, но фронтенд его не слушает. Лишняя нагрузка и задержка до 5 сек.
**Решение:** Реализовать WebSocket или SSE для push-обновлений состояния боя.

### B-027-1. user-service: main.py connects to MySQL at import time, breaking tests in CI
**Service:** user-service
**File:** `services/user-service/main.py:29`, `services/user-service/database.py:7`
**Description:** `main.py:29` calls `models.Base.metadata.create_all(bind=engine)` at module import time. The `database.py` engine is hardcoded to `mysql+pymysql://...@mysql:3306/...`. In CI (no MySQL), importing `main.py` fails with `OperationalError: Can't connect to MySQL server`. The conftest overrides `get_db()` but cannot prevent the import-time connection.
**Solution:** Guard `create_all` behind `if __name__ == "__main__"` or use a FastAPI startup event, or make the engine lazy. Alternatively, use `DATABASE_URL` env var with a fallback.

### B-027-2. character-service: 2 test files use invalid `from conftest import`
**Service:** character-service
**Files:** `services/character-service/app/tests/test_admin_character_management.py:13`, `services/character-service/app/tests/test_admin_update_level_xp.py:17`
**Description:** Both files do `from conftest import _test_engine, _TestSessionLocal` which fails with `ModuleNotFoundError: No module named 'conftest'`. In pytest, conftest.py is auto-loaded but not importable as a module.
**Solution:** Use pytest fixtures instead of direct imports from conftest, or add `__init__.py` to make conftest importable.

### B-027-3. skills-service: tests hang indefinitely due to async engine at import
**Service:** skills-service
**File:** `services/skills-service/app/database.py:9`
**Description:** `database.py` creates `create_async_engine("mysql+aiomysql://...")` at import time. While the test files patch `database.engine`, the async engine creation to an unreachable MySQL host causes tests to hang indefinitely (connection timeout).
**Solution:** Make the engine creation lazy or configurable via env var.

### B-027-4. notification-service: conftest creates Pydantic model without required fields
**Service:** notification-service
**File:** `services/notification-service/app/tests/conftest.py:59`
**Description:** `_make_user()` calls `UserRead()` without `user_id` and `username` params, causing `pydantic.error_wrappers.ValidationError: 2 validation errors for UserRead`. This breaks 38 out of 42 tests.
**Solution:** Pass required fields: `UserRead(id=user_id, username=username, ...)`.

### B-027-5. locations-service: test_sql_injection_in_rule_id_delete fails
**Service:** locations-service
**File:** `services/locations-service/app/tests/test_rules.py::TestRulesSecurity::test_sql_injection_in_rule_id_delete`
**Description:** This security test fails. Likely the endpoint does not properly handle SQL injection in rule ID for delete operations.
**Solution:** Investigate and fix the endpoint's input validation.

### B-027-6. character-attributes-service: test_admin_endpoints.py fails to collect
**Service:** character-attributes-service
**File:** `services/character-attributes-service/app/tests/test_admin_endpoints.py:43`
**Description:** Importing `main.py` triggers `from rabbitmq_consumer import start_consumer` which does `import aio_pika`. While `aio_pika` is in requirements.txt, the module-level import chain causes collection errors in CI environments where the import triggers RabbitMQ connection attempts.
**Solution:** Lazy-import rabbitmq_consumer or mock it in conftest.

---

## LOW

### 17. Неиспользуемые таблицы и зависимости
**Описание:**
- `users_avatar_preview`, `users_avatar_character_preview` — создаются при регистрации, но не читаются
- `lightgbm`, `scikit-learn` в autobattle-service — не импортируются
- `credentials/gcs-credentials.json` в photo-service — не используется
**Решение:** Удалить неиспользуемый код и зависимости.

### 20. photo-service: delete_s3_file включает имя бакета в ключ
**Сервис:** photo-service
**Файл:** `services/photo-service/utils.py:124`
**Описание:** `"/".join(file_url.split("/")[3:])` для URL вида `https://host/bucket/subdir/file.webp` возвращает `bucket/subdir/file.webp` вместо `subdir/file.webp`. Т.к. `Bucket` передаётся отдельно в `delete_object()`, ключ включает имя бакета и удаление молча не находит файл.
**Решение:** Пропускать 4 сегмента вместо 3: `"/".join(file_url.split("/")[4:])`, или парсить URL корректно.

### 21. frontend: SubmitPage.tsx hardcoded user_id = 1
**Сервис:** frontend
**Файл:** `services/frontend/app-chaldea/src/components/CreateCharacterPage/SubmitPage/SubmitPage.tsx:88`
**Описание:** При загрузке превью аватара персонажа используется `const user_id = 1` вместо реального ID пользователя из Redux store.
**Решение:** Использовать `id` из `useSelector(state => state.user)`, который уже импортируется в компоненте.

### 22. user-service: legacy endpoint upload-avatar сохраняет файлы локально
**Сервис:** user-service
**Файл:** `services/user-service/main.py:184-199`
**Описание:** `POST /users/upload-avatar/` сохраняет файлы на локальную файловую систему (`/assets/avatars/`) вместо S3. Дублирует функционал photo-service. Фронтенд использует photo-service для загрузки аватаров.
**Решение:** Удалить legacy endpoint или перенаправить на photo-service.

### 19. Несогласованность типов participant_id в battle-service
**Сервис:** battle-service
**Описание:** participant_id хранится как string ключ в Redis dict, но используется как int в разных местах кода. Потенциальный `KeyError`.
**Решение:** Унифицировать: всегда приводить к string при работе с Redis state.

---

## GLOBAL TASKS (стратегические задачи)

Крупные задачи по улучшению проекта. Каждая может быть разбита на подзадачи.

### T1. Frontend: переход на Tailwind CSS
**Сервис:** frontend
**Статус:** TODO
**Описание:** Заменить текущий подход к стилям (SCSS/CSS-файлы, inline-стили) на Tailwind CSS. Цель — унифицировать стилизацию, избавиться от разрозненных CSS-файлов, ускорить вёрстку.
**Стратегия: органическая миграция.** Не переписывать всё разом. Вместо этого:
- **Новые компоненты/страницы** — сразу писать на Tailwind, без создания CSS/SCSS-файлов.
- **Изменение существующего компонента** — если задача затрагивает стили компонента, мигрировать весь компонент на Tailwind в том же PR. Удалить старый CSS/SCSS-файл после миграции.
- **Задача не касается стилей** — не трогать стили, оставить как есть.

Таким образом проект постепенно перейдёт на Tailwind без выделения отдельного спринта на миграцию.
**Первый шаг (обязательный перед любой работой по T1):**
- Установить и настроить Tailwind CSS + PostCSS в Vite-проекте
- Настроить `tailwind.config.js` с кастомной цветовой палеттой и шрифтами проекта
- Убедиться, что Tailwind и старые SCSS сосуществуют без конфликтов
**Правила:**
- Не смешивать миграцию стилей с изменениями логики/функциональности — если задача требует и то и другое, делать два коммита.
- Сохранять визуальную идентичность — внешний вид компонента не должен меняться при миграции.
- Перед удалением CSS/SCSS-файла убедиться, что он не импортируется в других компонентах.

### T2. Backend: добавить Alembic во все сервисы
**Сервисы:** все backend-сервисы
**Статус:** TODO
**Описание:** Сейчас Alembic есть только в части сервисов (character-service, character-attributes-service, skills-service, inventory-service), причём в некоторых из них он настроен, но не поддерживается актуально. В остальных (user-service, locations-service, notification-service, battle-service, photo-service) миграций нет — схема управляется вручную или через SQL-дампы (`docker/mysql/backups/`). Цель — единообразное управление схемой БД через Alembic во всех сервисах.
**Стратегия: органическое добавление.** Не делать за раз. Вместо этого:
- **Работа в сервисе без Alembic** — добавить Alembic в рамках текущей задачи: инициализировать, создать initial-миграцию по существующим моделям, добавить `alembic` в `requirements.txt`.
- **Изменение схемы БД в сервисе с Alembic** — создать миграцию через `alembic revision --autogenerate`.
- **Задача не затрагивает БД** — не трогать.
**Сервисы без Alembic (нужно добавить при первой работе с ними):**
- locations-service
- notification-service
- battle-service
- photo-service (особый случай — сначала создать SQLAlchemy-модели, сейчас raw PyMySQL)
- user-service (Alembic есть, но legacy — проверить и актуализировать)
**Правила:**
- Initial-миграция должна точно соответствовать текущей схеме — не менять таблицы, типы, constraints.
- Для async-сервисов (locations-service, battle-service) использовать async-конфигурацию Alembic (`run_async`).
- Не удалять SQL-бэкап из `docker/mysql/` — он останется как fallback.
- Добавление Alembic — отдельный коммит от основной задачи.

### T3. Frontend: переход с JavaScript на TypeScript (`.jsx` → `.tsx`)
**Сервис:** frontend
**Статус:** TODO
**Описание:** Сейчас весь фронтенд написан на JS (`.jsx`). Цель — постепенно перевести на TypeScript для типобезопасности, автодополнения и уменьшения runtime-ошибок.
**Стратегия: органическая миграция.** Не переписывать всё разом. Вместо этого:
- **Новые компоненты/файлы** — сразу писать на TypeScript (`.tsx` / `.ts`).
- **Изменение существующего файла** — если задача затрагивает логику компонента, мигрировать его на TypeScript в том же PR. Переименовать `.jsx` -> `.tsx` / `.js` -> `.ts`, добавить типы.
- **Задача не касается логики файла** — не трогать, оставить как есть.
**Первый шаг (обязательный перед любой работой по T3):**
- Убедиться, что `tsconfig.json` настроен в проекте (Vite поддерживает TS из коробки)
- Установить `typescript` и `@types/react`, `@types/react-dom` в devDependencies
- Настроить strict mode постепенно (начать с `"strict": false`, ужесточать позже)
- Убедиться, что `.tsx` и `.jsx` файлы сосуществуют без конфликтов
**Правила:**
- Миграция файла на TS — отдельный коммит от изменений логики.
- Не использовать `any` без явной причины. Если тип неизвестен — оставить `// TODO: type this` и использовать `unknown`.
- Для API-ответов создавать интерфейсы в отдельных файлах (`types/` или рядом с компонентом).
- Redux slices: типизировать state, action payloads, selectors.

### T4. Backend: органическое покрытие тестами (pytest)
**Сервисы:** все backend-сервисы
**Статус:** TODO
**Описание:** Сейчас тестов почти нет (тесты в character-service исправлены в FEAT-011). Цель — постепенно покрыть бекенд unit и integration тестами через pytest.
**Стратегия: органическое покрытие.** Не писать тесты для всего разом. Вместо этого:
- **Новая фича** → тесты обязательны для всех новых/изменённых эндпоинтов и CRUD-логики.
- **Изменение существующего кода** → покрыть тестами изменённую логику.
- **Код не менялся** → не трогать.
- **Фронтенд НЕ тестируем** — только backend Python-код.
**Правила:**
- Тесты размещаются в `services/<service>/app/tests/`.
- Фикстуры — в `conftest.py` (SQLite in-memory для тестов, override `get_db()`).
- Межсервисные HTTP-вызовы всегда мокать (`unittest.mock.patch`).
- Reviewer запускает `pytest` в затронутых сервисах как часть review-чеклиста.
- `pytest` добавлять в `requirements.txt` при первой работе с тестами в сервисе.

---

## Статистика

| Приоритет | Количество |
|-----------|-----------|
| CRITICAL | 1 |
| HIGH | 11 |
| MEDIUM | 6 |
| LOW | 4 |
| **Итого** | **22** |
