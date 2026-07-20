# Chaldea - Known Issues & Tech Debt

Файл с известными проблемами, багами и техническим долгом. Приоритеты: CRITICAL / HIGH / MEDIUM / LOW.

---

## DONE / Learning notes

### Баг: некорректный рендер пути между локациями при рисовании от большего id к меньшему DONE
**Сервис:** frontend (`AdminPathEditor`) + locations-service
**Файл:** `services/frontend/app-chaldea/src/components/AdminPathEditor/AdminPathEditorPage.tsx` (`handleDrawClick`)
**Описание:** При создании пути между локациями (`createNeighborWithPath`) фронтенд отправлял `locationId`/`neighbor_id` в том порядке, в котором пользователь кликал, а `path_data` — в порядке рисования. Backend (`locations-service/app/crud.py::add_neighbor`) хранит обе строки `LocationNeighbor` (forward + reverse) с одинаковым `path_data`. На чтении (`crud.py` ~428) region endpoint нормализует ребро к `(min_id, max_id)` и дедуплицирует по `seen_edges`: какая из двух строк будет оставлена — зависит от порядка итерации по БД. Если оставалась строка, где `location_id > neighbor_id`, код разворачивал `path_data`; иначе — нет. В результате, когда пользователь рисовал от локации с бóльшим id к локации с меньшим id, `path_data` мог остаться в исходном (обратном относительно `min→max`) порядке, и в `RegionMapEditor.tsx` (~строка 897) полилиния `[from, ...path_data, to]` рендерилась с «прыжками».
**Исправление:** В `handleDrawClick` перед dispatch `createNeighborWithPath` канонизируем направление: всегда отправляем `locationId = min(drawStartId, locId)`, `neighbor_id = max(...)`, и если рисование шло от большего id — реверсируем `drawWaypoints`. Благодаря этому обе строки в БД хранятся в порядке `min→max`, и существующая логика reverse при чтении работает консистентно в обоих направлениях. Аналогичный приём уже был применён в ветке «arrow → location» того же файла.
**Альтернатива (не реализована):** то же самое можно было сделать в backend `add_neighbor` (нормализовать порядок + reverse при swap), но чтобы минимизировать blast radius, правка сделана только на фронтенде.

### Alembic revision IDs должны быть ≤32 символов DONE (FEAT-123 hotfix)
**Сервис:** все сервисы с Alembic
**Описание:** Дефолтная ширина колонки `version_num` в таблицах `alembic_version_*` — VARCHAR(32). Если revision id длиннее, `alembic upgrade head` падает на финальном UPDATE: `(1406, "Data too long for column 'version_num' at row 1")`, контейнер не стартует (fail-fast).
**Случай:** В FEAT-123 миграция character-service имела id `015_add_teleport_links_and_cooldown` (35 символов) → переименована в `015_teleport_cooldown` (21).
**Правило:** Все новые revision id — ≤32 символов. Желательно ≤24, чтобы оставить запас. Формат: `NNN_short_slug`.

---

## CRITICAL

### 27. JWT-секрет — публично известный fallback `your-secret-key` (вероятно, и на prod)
**Сервис:** user-service (docker/env)
**Файлы:** `docker-compose.yml:227` (`JWT_SECRET_KEY: ${JWT_SECRET_KEY:-your-secret-key}`), `.env` (ключ отсутствует), prod `.env` на VPS (fallofgods.top)
**Обнаружено:** FEAT-150 (Codebase Analyst, 2026-07-17). По решению пользователя — исправляется отдельной задачей, не в рамках FEAT-150.
**Описание:** `auth.py` берёт секрет из `JWT_SECRET_KEY`, но ни локальный, ни (по всем признакам) prod `.env` его не задают — используется дефолт `your-secret-key`, прописанный прямо в публичном репозитории. HS256-подпись с известным секретом означает, что **любой может изготовить валидный JWT с ролью admin** и пройти авторизацию во всех 12 сервисах (они валидируют токены через `GET /users/me` user-service). Это полная компрометация аутентификации.
**Решение:**
1. Сгенерировать криптостойкий секрет (например, `openssl rand -hex 32`) и прописать `JWT_SECRET_KEY` в prod `.env` на VPS.
2. Добавить `JWT_SECRET_KEY` в `.env.example` с маскированным значением-заглушкой.
3. Рассмотреть удаление fallback-значения из `docker-compose.yml` (fail-fast без секрета) — как минимум для prod-конфигурации.
**Цена:** смена секрета инвалидирует все выданные токены → однократный принудительный re-logout всех пользователей (после FEAT-150 достаточно одного повторного входа; refresh-токены со старой подписью тоже перестанут работать). Скоординировать с деплоем.

---

## HIGH

### Баг: таймер кулдауна перемещения никогда не отображается — `/users/me` не отдаёт `travel_cooldown_until`
**Сервис:** user-service (+ frontend consumer)
**Файлы:**
- `services/user-service/schemas.py` (класс `CharacterShort`, ~строка 66) — поле `travel_cooldown_until` отсутствует в схеме
- `services/user-service/main.py:154` — значение собирается в dict, но затем срезается response_model
- `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx:59-90` — UI-таймер читает `character.travel_cooldown_until`, который никогда не приходит
**Описание:** `MeResponse.character` типизирован как `CharacterShort`, в котором нет поля `travel_cooldown_until`. Pydantic отфильтровывает поле из ответа `/users/me`, хотя main.py его подставляет (и frontend-тип `userSlice.ts` его ожидает). В результате блок «Перемещение будет доступно через N мин M сек» на странице локации никогда не показывается, кулдаун виден только как ошибка при попытке перемещения. Баг существовал до FEAT-152 (обнаружен Reviewer при live-проверке FEAT-152, 2026-07-17). Фикс: добавить `travel_cooldown_until: Optional[datetime/str] = None` в `CharacterShort`.
**Приоритет:** HIGH (нерабочая пользовательская функция)

### ~~Баг: locations-service миграция 004 падает на свежей БД (отсутствует таблица `permissions`)~~ DONE (2026-04-08)
~~**Сервис:** locations-service~~
~~**Файлы:** `services/locations-service/app/alembic/versions/004_game_time_config.py`~~
**Исправлено:** В `upgrade()` добавлен defensive guard — блок `INSERT INTO permissions / role_permissions` выполняется только если `inspector.get_table_names()` содержит `permissions`, `roles` и `role_permissions`. Схема (`game_time_config`) создаётся безусловно. `INSERT` заменён на `INSERT IGNORE` для идемпотентности. На prod no-op (таблицы существуют), фикс улучшает только dev/CI/disaster-recovery bootstrap. Проверено: `docker compose up -d locations-service` — миграции проходят 003 -> 028, uvicorn стартует, `curl http://localhost/characters/races` = 200 `[]`.

### Баг: маркеры на карте мира съезжают при нестандартной ширине окна DONE
**Сервис:** frontend
**Файлы:**
- `services/frontend/app-chaldea/src/components/WorldPage/InteractiveMap/InteractiveMap.tsx`
- `services/frontend/app-chaldea/src/components/AdminLocationsPage/FloatingRouteEditor.tsx`
**Описание:** Контейнер карты мира имел `min-h-[300px] md:min-h-[500px]` и `w-full`, то есть его соотношение сторон зависело от ширины окна. Внутри лежал `<img class="w-full h-full object-cover">`, который кропает картинку под контейнер. Все маркеры (clickable zones, локации, плавающие структуры, стрелки) позиционируются в `% left/top` относительно контейнера — поэтому при изменении aspect ratio контейнера они «уезжали» относительно фич карты. Стало особенно заметно при тестировании плавающих структур (FEAT-123).
**Исправление:** Контейнер теперь блокирует aspect ratio под натуральные размеры загруженной картинки (`onLoad` -> `setAspectRatio(`${naturalWidth} / ${naturalHeight}`)`), `min-h-*` убран. `object-cover` остаётся, но теперь идентичен `object-contain`, потому что контейнер совпадает с картинкой по пропорциям. Все существующие маркеры с `% left/top` автоматически выравниваются на любых ширинах окна (от 360px до 1920px+). Аналогичная правка применена к редактору маршрутов, чтобы клики `getBoundingClientRect` тоже маппились в правильные координаты картинки.



### ~~3. Баг: бой не завершается при HP <= 0~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** Добавлена проверка HP<=0 после применения урона. При обнаружении — battle.status='finished' в MySQL, Redis state expire 5 мин, winner_team в ActionResponse. Повторные action на finished battle возвращают 400.~~

### ~~4. Баг: кулдаун навыков не обновляется в dict~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** `remaining -= 1` заменено на `new_val = remaining - 1` с записью `cd_map[rank_id] = new_val`.~~

### ~~5. Баг: дублирование enemy_effects в бою~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** Удалён дублирующий блок apply_new_effects для enemy в секции ATTACK.~~

### ~~6. Memory leak в autobattle-service~~ Частично исправлен (FEAT-071)
~~**Сервис:** autobattle-service~~
~~**Описание:** `LAST_STATS` dict растёт бесконечно — записи никогда не удаляются после завершения боя.~~
**Частично исправлено:** `_cleanup_battle()` добавлена, но cleanup LAST_STATS не работает корректно из-за бага #22 (несовпадение ключей).

### Баг: DoT-эффекты и контроли не работают в боёвке
**Сервис:** battle-service
**Файлы:**
- `services/battle-service/app/buffs.py` (строки 5-35 `_normalize_effect`, 38-61 `apply_new_effects`, 64-75 `decrement_durations`)
- `services/battle-service/app/main.py:1068`
**Описание:** Все 14 сложных эффектов из `COMPLEX_EFFECTS` (Bleeding, Burn, Poison, ArmorBreak, Stun, Knockdown, Daze, MagicImpact, Freeze, Wet, Electrify, Windburn, Holy, Curse) молча игнорируются боевым движком. `_normalize_effect` распознаёт только префиксы `Buff:` / `Resist:` и StatModifier — всё остальное проваливается в else-ветку и превращается в произвольный атрибут (`bleeding`, `burn`, ...). Эти атрибуты не входят в `inst_attrs = {hp,mana,energy,stamina}`, поэтому `apply_new_effects` не применяет мгновенный урон. На последующих ходах единственный per-turn вызов — `decrement_durations()` — только уменьшает `duration`, но никогда не читает `magnitude` и не вычитает HP. DoT-эффекты сохраняются в state, тикают по длительности, но не наносят урона. Аналогично сломан контроль: `next_actor` в `main.py` не консультируется с `active_effects` для пропуска хода оглушённых целей.
**Impact:** DoT-навыки (кровотечение, ожог, яд) бесполезны в бою. Контролей фактически нет. Замечено пользователем во время тестирования FEAT-125, но баг существовал и до FEAT-125 — это не регресс, а латентный баг боевого движка.
**Решение:** Добавить функцию `tick_dot_effects(state)` в `buffs.py`, вызвать её перед `decrement_durations()` в `main.py:1068`. Контроли — отдельная задача (модификация `next_actor` с чтением `active_effects` для пропуска хода при Stun/Freeze/Knockdown).

### 22. Баг: несовпадение ключей LAST_STATS и HISTORY в autobattle-service
**Сервис:** autobattle-service
**Файл:** `services/autobattle-service/app/main.py`
**Описание:** `build_features()` (строка 189, 227) использует ключ `(turn_number, pid)` для LAST_STATS и HISTORY, но `handle_turn()` (строка 300) записывает в HISTORY с ключом `(bid, pid)`. `_cleanup_battle()` (строки 254-257) ищет записи по `k[0] == bid`, но LAST_STATS хранит `(turn_number, pid)` — очистка не сработает если turn_number != bid. HISTORY имеет смешанные ключи.
**Решение:** Привести все ключи к единому формату `(bid, pid)` в build_features и handle_turn.

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

### 30. N+1 HTTP-запросов в BattlesSection при каждом polling-цикле
**Сервис:** frontend (+ нагрузка на battle-service)
**Файл:** `services/frontend/app-chaldea/src/components/pages/LocationPage/BattlesSection.tsx:49-69, 71-97`
**Описание:** После каждой загрузки списка боёв `checkExistingRequests()` последовательно вызывает `fetchJoinRequests(battle.id)` для КАЖДОГО боя в локации. При polling каждые 10 секунд это даёт N дополнительных запросов к battle-service каждые 10 с на каждого зрителя страницы локации. При 10 активных боях и 20 игроках на странице — 200 запросов / 10 с. Запросы выполняются последовательно (`for ... await`), что дополнительно растягивает цикл.
**Решение:** Отдавать признак «моя заявка подана» batch-эндпоинтом battle-service (например, поле `has_my_request` прямо в `/battles/by-location/{id}`), либо запрашивать заявки только для развёрнутой секции и параллельно (`Promise.all`).

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

### ~~15. Polling вместо WebSocket на BattlePage~~ DONE (FEAT-074)
~~**Сервис:** frontend~~
~~**Исправлено в FEAT-074:** Polling заменён на WebSocket (`/battles/ws/{battle_id}`). Оба игрока получают обновления мгновенно. Авто-переподключение с exponential backoff, fallback на polling при неудаче. Автобой тоже через WebSocket + управление скоростью (быстрый/медленный режим).~~

~~### 23. Баг: GET /attributes/admin/perks недоступен из-за конфликта роутов~~
~~**Сервис:** character-attributes-service~~
~~**Файл:** `services/character-attributes-service/app/main.py`~~
~~**Исправлено в FEAT-078:** Perks-роуты (GET /{character_id}/perks, GET/POST/PUT/DELETE /admin/perks/*) перенесены выше catch-all роута GET /{character_id}. FastAPI теперь матчит специфичные пути первыми.~~

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

### 25. Баг: dungeon-service тесты не запускаются (from conftest import)
**Сервис:** dungeon-service
**Файлы:** `services/dungeon-service/app/tests/test_admin_crud.py`, `services/dungeon-service/app/tests/test_room_positions.py`
**Описание:** Тесты используют `from conftest import _dungeon_payload, _room_payload` — это не работает, т.к. `tests/__init__.py` существует и conftest не доступен как обычный модуль. pytest обрабатывает conftest.py автоматически, но прямой import невозможен при наличии `__init__.py`. Затрагивает 2 из 5 тестовых файлов.
**Решение:** Удалить `__init__.py` из `tests/`, либо переименовать helper-функции в фикстуры, либо вынести `_dungeon_payload`/`_room_payload` в отдельный модуль `tests/helpers.py`.

### 19. Несогласованность типов participant_id в battle-service
**Сервис:** battle-service
**Описание:** participant_id хранится как string ключ в Redis dict, но используется как int в разных местах кода. Потенциальный `KeyError`.
**Решение:** Унифицировать: всегда приводить к string при работе с Redis state.

### 26. Неиспользуемые константы в ProfilePage/constants.ts (после FEAT-149)
**Сервис:** frontend
**Файл:** `services/frontend/app-chaldea/src/components/ProfilePage/constants.ts` (строки ~98, ~252)
**Описание:** После редизайна профиля (FEAT-149) константы `MIN_GRID_CELLS` (филлеры сетки инвентаря удалены) и `DERIVED_STATS` (DerivedStatsSection перешёл на собственные COMBAT_CARD_LABELS/RESIST_CHIPS) больше нигде не используются.
**Решение:** Удалить обе константы (безопасный dead-code cleanup, отдельным мелким коммитом).

### 28. Мёртвый код удаления accessToken в useNavigateTo.js
**Сервис:** frontend
**Файл:** `services/frontend/app-chaldea/src/hooks/useNavigateTo.js:9`
**Обнаружено:** FEAT-150 (Reviewer, 2026-07-17). Pre-existing, к фиче не относится.
**Описание:** Хук удаляет `accessToken` (но не `refreshToken`) при `navigateTo('/')`. Ни один текущий вызов не передаёт `'/'` (проверено grep), так что ветка — мёртвый код. Однако она нарушает инвариант FEAT-150 «токены удаляются только в `handleAuthFailure()` / `clearTokens()`»: будущий вызов `navigateTo('/')` создаст «полу-logout» (accessToken удалён, refreshToken жив → интерсептор воскресит сессию).
**Решение:** Удалить ветку `if (link === '/')` из хука (заодно мигрировать файл на TS при первой правке логики, правило T3).

### 29. После логина через форму хедер не показывает пользователя до перезагрузки
**Сервис:** frontend
**Файлы:** `services/frontend/app-chaldea/src/components/StartPage/AuthForm/AuthForm.tsx` (навигация после логина), `src/components/CommonComponents/Header/Header.tsx:29-35` (getMe пропускается на первом маунте)
**Обнаружено:** FEAT-150 (Reviewer, 2026-07-17). Pre-existing поведение, воспроизводится и на HEAD до фичи (проверено).
**Описание:** После успешного логина AuthForm делает SPA-переход на `/home` без dispatch(getMe()). Header монтируется заново и пропускает getMe на первом маунте (`isInitialMount`), App.tsx вызывает getMe только при старте приложения. В итоге сразу после логина хедер выглядит «разлогиненным» (нет аватара/меню) до следующей навигации или F5.
**Решение:** Диспатчить `getMe()` после успешного логина в AuthForm (или убрать пропуск первого маунта в Header).

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
| CRITICAL | 1 |
| HIGH | 4 |
| MEDIUM | 4 |
| LOW | 4 |
| **Итого** | **13** |
