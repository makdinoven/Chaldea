# Chaldea - Known Issues & Tech Debt

Файл с известными проблемами, багами и техническим долгом. Приоритеты: CRITICAL / HIGH / MEDIUM / LOW.

---

## HIGH

### ~~3. Баг: бой не завершается при HP <= 0~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** Добавлена проверка HP<=0 после применения урона. При обнаружении — battle.status='finished' в MySQL, Redis state expire 5 мин, winner_team в ActionResponse. Повторные action на finished battle возвращают 400.~~

### ~~4. Баг: кулдаун навыков не обновляется в dict~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** `remaining -= 1` заменено на `new_val = remaining - 1` с записью `cd_map[rank_id] = new_val`.~~

### ~~5. Баг: дублирование enemy_effects в бою~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** Удалён дублирующий блок apply_new_effects для enemy в секции ATTACK.~~

### 6. Memory leak в autobattle-service
**Сервис:** autobattle-service
**Файл:** `services/autobattle-service/app/main.py`
**Описание:** `LAST_STATS` dict растёт бесконечно — записи никогда не удаляются после завершения боя. При длительной работе сервис будет потреблять всё больше памяти.
**Решение:** Очищать записи для (battle_id, pid) при завершении боя, или использовать TTL-cache (например `cachetools.TTLCache`).

### ~~7. Баг: shield нельзя экипировать через API~~ DONE (FEAT-041)
~~**Сервис:** inventory-service~~
~~**Исправлено в FEAT-041:** добавлен `'shield'` во все ENUM-определения (models, schemas, crud) + Alembic-миграция + data backfill для существующих персонажей.~~

### ~~20. GIF-анимация теряется при загрузке аватарки/фона профиля~~ DONE (FEAT-044)
~~**Сервис:** photo-service~~
~~**Исправлено в FEAT-044:** `convert_to_webp` теперь определяет анимированные GIF (`image.format == 'GIF'` + `is_animated`) и сохраняет их как GIF с `save_all=True`, сохраняя все кадры и анимацию. Статические изображения по-прежнему конвертируются в WebP. S3 получает корректный `ContentType` (`image/gif` или `image/webp`).~~

---

## MEDIUM

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

---

## LOW

### 17. Неиспользуемые зависимости
**Описание:**
- `lightgbm`, `scikit-learn` в autobattle-service — не импортируются
- `credentials/gcs-credentials.json` в photo-service — не используется
**Решение:** Удалить неиспользуемый код и зависимости.

### ~~21. Schema/ORM mismatch: loot_table vs loot_entries in MobTemplateDetailResponse~~ DONE (FEAT-059, Review)
~~**Сервис:** character-service~~
~~**Исправлено в FEAT-059 Review:** Renamed schema field `loot_table` to `loot_entries` in `MobTemplateDetailResponse` and updated frontend TypeScript interface to match.~~

### ~~22. Баг: вражеские эффекты лечат вместо нанесения урона~~ DONE
~~**Сервис:** battle-service~~
~~**Файл:** `services/battle-service/app/buffs.py`~~
~~**Описание:** `apply_new_effects` для enemy-эффектов с положительной magnitude на HP/mana/energy/stamina прибавляла значение (лечила врага) вместо вычитания.~~
~~**Исправлено:** Добавлен параметр `is_enemy` — при `True` положительная magnitude инвертируется для мгновенных атрибутов.~~

### ~~23. Баг: _normalize_effect падает при effect_name без двоеточия~~ DONE
~~**Сервис:** battle-service~~
~~**Файл:** `services/battle-service/app/buffs.py`~~
~~**Описание:** `kind, tail = name.split(":", 1)` падал с `ValueError` если effect_name не содержал `:` (например "Bleeding").~~
~~**Исправлено:** Проверка `len(parts)` перед распаковкой.~~

### ~~24. battle-service skills_client вызывает admin endpoint без авторизации~~ DONE
~~**Сервис:** battle-service~~
~~**Файл:** `services/battle-service/app/skills_client.py`~~
~~**Описание:** `get_rank()` и `character_ranks()` вызывали `/skills/admin/skill_ranks/{id}` (требует JWT), battle-service не отправлял токен → навыки не загружались в бою.~~
~~**Исправлено:** `character_ranks()` использует данные из публичного ответа `/skills/characters/{id}/skills`. `get_rank()` использует новый публичный endpoint `/skills/skill_ranks/{id}`.~~

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
**Статус:** IN PROGRESS (8/9 сервисов готовы)
**Описание:** Цель — единообразное управление схемой БД через Alembic во всех сервисах с автоматическим запуском миграций при старте контейнера.

**Сервисы с Alembic (DONE — auto-migration при старте):**
- user-service — `alembic_version_user` (sync)
- character-attributes-service — `alembic_version_char_attrs` (sync)
- skills-service — `alembic_version_skills` (async)
- locations-service — `alembic_version_locations` (async)
- character-service — `alembic_version_character` (sync)
- inventory-service — `alembic_version_inventory` (sync)
- photo-service — `alembic_version_photo` (sync, mirror models, no own migrations)
- battle-service — `alembic_version_battle` (async) — added in FEAT-059

**Сервисы без Alembic (нужно добавить при первой работе с ними):**
- notification-service

**Стратегия: органическое добавление.** Не делать за раз. Вместо этого:
- **Работа в сервисе без Alembic** — добавить Alembic в рамках текущей задачи: инициализировать, создать initial-миграцию по существующим моделям, добавить `alembic` в `requirements.txt`.
- **Изменение схемы БД в сервисе с Alembic** — создать миграцию через `alembic revision --autogenerate`.
- **Задача не затрагивает БД** — не трогать.
**Правила:**
- **При добавлении Alembic в сервис** — настроить автоматический запуск миграций при старте контейнера: в Dockerfile CMD добавить `alembic upgrade head && uvicorn ...` (fail-fast — если миграция падает, сервис не стартует).
- **Каждый сервис должен использовать уникальное имя `version_table`** в `env.py` (например `alembic_version_user`, `alembic_version_photo`) для избежания коллизий в общей БД.
- **`create_all()` удалить** при добавлении Alembic — схемой БД управляет только Alembic.
- Initial-миграция должна точно соответствовать текущей схеме — не менять таблицы, типы, constraints.
- Для async-сервисов (battle-service) использовать async-конфигурацию Alembic (`run_async`).
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

### T5. Frontend: адаптивность под мобильные устройства
**Сервис:** frontend
**Статус:** TODO
**Описание:** Сейчас почти ничего не адаптировано под мобильные устройства. Цель — постепенно сделать весь фронтенд рабочим на экранах 360px+.
**Стратегия: органическая адаптация.** Не переделывать всё разом. Вместо этого:
- **Новые компоненты/страницы** — сразу делать адаптивными.
- **Изменение стилей существующего компонента** — если задача затрагивает стили компонента, добавить адаптивность в том же PR.
- **Задача не касается стилей** — не трогать, оставить как есть.
**Правила:**
- Главное: всё должно помещаться и работать на экране 360px+. Контент не должен выходить за viewport.
- Навигация: должна быть доступна на мобильных (бургер-меню, сворачиваемые панели).
- Формы: поля ввода и кнопки удобны для touch.
- Изображения: масштабируются, не выходят за viewport.
- Таблицы: на мобильных либо горизонтальный скролл, либо переформатирование в карточки.
- Использовать Tailwind responsive breakpoints: `sm:`, `md:`, `lg:`, `xl:`.
- Не ломать десктопную версию при добавлении адаптивности.

---

## Статистика

| Приоритет | Количество |
|-----------|-----------|
| CRITICAL | 0 |
| HIGH | 4 |
| MEDIUM | 4 |
| LOW | 2 |
| **Итого** | **10** |
