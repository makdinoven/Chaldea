# locations-service

**Порт:** 8006
**Технологии:** FastAPI (async), SQLAlchemy (async, aiomysql), httpx
**Путь:** `/home/dudka/chaldea/services/locations-service/`

## Назначение

Игровой мир: страны, регионы, районы, локации. Граф локаций (соседи с cost перемещения). Перемещение персонажей. Посты/чат в локациях. Черновики ролевых постов (FEAT-156).

**Аутентификация:** вопреки CLAUDE.md п.10.7, сервис **проверяет JWT сам** — `app/auth_http.py:24` `get_current_user_via_http` валидирует Bearer-токен запросом к `user-service GET /users/me`. Зависимость стоит напрямую на 26 маршрутах и ещё на 59 через `require_permission(...)` (`auth_http.py:73`), который строится поверх неё. Владелец персонажа сверяется отдельной функцией `verify_character_ownership` (`main.py:114`).

## Структура файлов

```
locations-service/app/
├── main.py        # FastAPI app, все роуты
├── models.py      # 6 SQLAlchemy моделей
├── schemas.py     # Pydantic схемы (обширные)
├── crud.py        # Бизнес-логика
├── config.py      # Настройки
└── database.py    # Async SQLAlchemy
```

## API Endpoints (~25 штук)

### Lookup (для выпадающих списков)
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/locations/lookup` | id+name всех локаций |
| GET | `/districts/lookup` | id+name всех районов |
| GET | `/countries/lookup` | id+name всех стран |

### Countries
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/countries/create` | Создать страну |
| PUT | `/countries/{id}/update` | Обновить страну |
| GET | `/countries/list` | Список стран |
| GET | `/countries/{id}/details` | Страна с регионами |

### Regions
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/regions/create` | Создать регион |
| PUT | `/regions/{id}/update` | Обновить регион |
| GET | `/regions/{id}/details` | Регион с полной иерархией |
| DELETE | `/regions/{id}/delete` | Каскадное удаление |

### Districts
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/districts` | Создать район |
| PUT | `/districts/{id}/update` | Обновить район |
| GET | `/districts/{id}/details` | Район с локациями |
| GET | `/districts/{id}/locations` | Локации района |
| DELETE | `/districts/{id}/delete` | Каскадное удаление |

### Locations
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/` | Создать локацию |
| PUT | `/locations/{id}/update` | Обновить локацию |
| GET | `/locations/{id}/details` | Локация с соседями и потомками |
| GET | `/locations/{id}/children` | Дочерние локации |
| DELETE | `/locations/{id}/delete` | Рекурсивное каскадное удаление |

### Neighbors (граф)
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/{id}/neighbors/` | Создать двустороннюю связь |
| GET | `/locations/{id}/neighbors/` | Соседи локации |
| DELETE | `/locations/{id}/neighbors/{neighbor_id}` | Удалить связь |
| POST | `/locations/{id}/neighbors/update` | Заменить всех соседей |

### Посты
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/posts/` | Создать пост в локации |
| GET | `/locations/{id}/posts/` | Посты в локации (newest first) |
| PUT | `/locations/posts/{post_id}` | Редактировать текст своего поста (FEAT-159, см. ниже) |

### Редактирование поста (FEAT-159, Phase A)

`PUT /locations/posts/{post_id}` (`main.py:988`, логика — `crud.edit_post`, `crud.py:1167`). Аутентификация: `Depends(get_current_user_via_http)`. Правится **только текст**: тело — `schemas.PostEditRequest` (`schemas.py:351`) с единственным полем `content`. Ни `post_type`, ни `targets`, ни `gates` эндпоинт не принимает — легаси-форма одиночного гейта на новом пути не поддерживается сознательно, чтобы не появился второй, иначе валидируемый способ объявлять намерения.

Ответ — `schemas.PostEditResponse` (`schemas.py:362`): `id, content, length, created_at, edited_at, edited_by_admin`. `length` считается по сырому (с HTML) содержимому, как и в `get_post_details`; проверки длины — по тексту после `strip_html_tags`.

#### Кто и когда может править

Порядок ветвлений в `crud.edit_post` — часть контракта:

1. **Роль `admin`** — обходит **оба** ограничения (час и «после поста уже написали) **безусловно**, в том числе на **своих собственных** постах. Ветка проверяется **первой** (решение пользователя от 2026-09-13). Проверяется буквально `current_user.role == "admin"`; `get_admin_user` **не** используется намеренно — он пускает и модераторов, а модератор на чужом посту получает 403.
2. **Автор поста** (не админ) — правит, только если после его поста в локации никто не писал и только в течение `POST_EDIT_WINDOW_HOURS = 1` (`crud.py:1164`) с момента **публикации**.
3. Кто угодно ещё — 403.

Обход админом касается **только этих двух ограничений**, а не проверок содержимого: минимальная длина и бюджет символов применяются к админу ровно так же.

| Код | Условие | `detail` |
|-----|---------|----------|
| 200 | успешно | — |
| 400 | текст короче `MIN_POST_LENGTH` | `Минимальная длина поста — 300 символов (сейчас: N)` |
| 400 | текст короче бюджета гейтов поста | `Для всех действий этого поста нужно минимум N символов (сейчас: M)` |
| 403 | не админ и не автор | `Вы можете редактировать только свои посты` |
| 403 | час истёк (путь автора) | `Редактировать пост можно в течение часа после публикации` |
| 403 | после поста уже написали (путь автора) | `После этого поста уже написали — редактирование недоступно` |
| 404 | поста нет (или его удалили между UPDATE и перечитыванием) | `Пост не найден` |

#### Два ограничения и то, как они проверяются

Оба перепроверяются **на сервере, в момент сохранения, в той же транзакции**, что и `UPDATE`, под `SELECT ... FOR UPDATE` на строке поста. Клиентская проверка — только удобство.

- **«После поста уже написали» — по `id >`, а не по `created_at >`.** `posts.id` — монотонный автоинкремент и упорядочивает ленту ровно так же, как `get_posts_by_location` (`ORDER BY id DESC`), поэтому два поста с одинаковой посекундной `TIMESTAMP` не проскочат.
- **Час считается MySQL против `NOW()`**, а не в Python: `created_at > NOW() - INTERVAL :hours HOUR` вычисляется прямо в том же `SELECT`, что читает пост. `posts.created_at` — наивный MySQL `TIMESTAMP`, записанный серверным `NOW()`; сравнение его с `datetime.now(timezone.utc)` — классический баг naive/aware и сдвинуло бы окно на смещение контейнера. Окно всегда измеряется от `created_at` и **никогда** не смотрит на `edited_at`, поэтому повторные правки его не продлевают.
- **Опыт не пересчитывается** и фоновая задача начисления не ставится: XP выдан при публикации, иначе «дописывай текст» стало бы способом фарма.
- **Принятая остаточная гонка:** `FOR UPDATE` берётся на строку поста, а не на локацию. Блокировка локации сериализовала бы всё написание постов там ради проверки, которую читает только этот эндпоинт. Остаётся окно в миллисекунды: правка может лечь сразу после чужого ответа. Последствие косметическое, это осознанный размен (задокументирован в докстринге `crud.edit_post`).

#### Бюджет символов при редактировании

Гейты покупаются длиной текста (`GATE_SYMBOL_COST`, `crud.py:25-27`: `combat` — 200 за цель, остальные — 500; пол — `MIN_POST_LENGTH`). Правка **не может** сократить пост ниже той длины, которую уже стоят его гейты.

- `crud.gate_list_for_post` (`crud.py:1128`) читает **все** строки `action_gates` этого поста — статуса `open`, `consumed` **и** `expired`, без фильтра по статусу. Это принципиально: гейты истекают при выходе персонажа из локации, поэтому счёт только `open` означал бы «купи пять гейтов, выйди и вернись — и тот же текст снова свободен». Пост эти гейты купил, бюджет остаётся потраченным.
- `crud.merge_gate_lists(*gate_lists)` (`crud.py:55`) — **чистая** функция: группирует по `action_type` и **объединяет** множества целей (`None` как цель сохраняется отдельным элементом). Объединение, а не конкатенация: `required_symbols_for_gates` берёт `cost * max(1, len(targets))`, и цель, названная дважды, была бы посчитана дважды.
- `crud.required_symbols_for_gates` (`crud.py:92`) переиспользуется без изменений, так что сервер и клиентское зеркало (`gateConstants.ts`) не могут разойтись.
- Проверка идёт **после** проверки `MIN_POST_LENGTH` и применяется **и к админам**. У поста без гейтов работает только минимальная длина — со своей формулировкой ошибки.

`merge_gate_lists` принимает **произвольное число списков** намеренно: Phase B (T8) добавит к нему список гейтов из ожидающих заявок и список запрашиваемых сейчас, **расширив** этот код, а не заменив его. В Phase A передаётся ровно один список — гейты, которые пост уже имеет.

#### «Изменено»

Две новые nullable-колонки в `posts` (миграция `038_post_edit_columns`, модель — `models.py:173,176`):

- `edited_at TIMESTAMP NULL DEFAULT NULL` — когда пост правили в последний раз. `NULL` = не правили ни разу.
- `edited_by_user_id INT NULL DEFAULT NULL` — кто правил. **Только аудит, клиенту не отдаётся никогда.**

**Почему не generic `updated_at ... ON UPDATE CURRENT_TIMESTAMP`:** такой столбец срабатывал бы на **любую** будущую запись в строку — бэкфилл, админский скрипт, добавленная позже колонка — и пометил бы «изменено» всю таблицу. Эти две колонки пишет ровно один путь кода (`crud.edit_post`) и значат они ровно одно. Откат миграции — `DROP COLUMN`, теряется только сама пометка.

`schemas.ClientPost` (`schemas.py:549`) получил два аддитивных поля, которые наследует и `LatestPostResponse`:

- `edited_at: Optional[datetime] = None`;
- `edited_by_admin: bool = False` — **производное, не хранится**. Считается в `crud.get_post_details` (`crud.py:2024-2036`) как «`edited_at` не пуст **и** `edited_by_user_id` не пуст **и** `user_id` автора не пуст **и** они не равны». `user_id` автора берётся из уже запрашиваемого профиля character-service, то есть лишних запросов нет. **Если вызов профиля упал**, `profile_data["user_id"]` = `None`, флаг = `False`, и UI показывает обычное «изменено»: сбой никогда не обвиняет админа ложно. По той же причине админ, правящий **свой** пост, даёт `false` — он и есть автор.

`PostResponse` (сырая ORM-форма из `GET /{location_id}/posts/`) намеренно не тронут.

#### Rate limit

`PUT /locations/posts/{id}` ограничен на Nginx в обоих конфигах: `limit_req_zone ... zone=post_edit_limit:10m rate=20r/m` (`nginx.conf:49`, `nginx.prod.conf:51`) и `limit_req zone=post_edit_limit burst=10 nodelay; limit_req_status 429` в regex-локации `~ ^/locations/posts/[0-9]+$` (`nginx.conf:289`, `nginx.prod.conf:304`). Ключ — `$binary_remote_addr` (на IP). Паттерн строго на числовой id без хвоста, поэтому `/posts/{id}/like`, `/unlike`, `/request-deletion`, `/report`, а также литеральные `/posts/as-npc`, `/posts/latest`, `/posts/character-stats` под лимит **не** попадают. Тело 429 отдаёт Nginx как HTML — у фронтенда для этого статуса отдельная ветка с русским сообщением.

> Заявки на ретро-добавленные гейты (`post_gate_requests`, раздел модерации) — **Phase B, ещё не реализовано**. В коде их нет.

### Черновики ролевых постов (FEAT-156)

Черновик привязан к паре **персонаж + локация**. Автосохранение с фронтенда (debounce), восстановление при возврате в локацию, история из последних 10 текстов персонажа — как недописанных, так и уже отправленных.

Маршруты `/locations/drafts...` объявлены в `main.py:376-496` **до** параметрических `/{location_id}/...` — иначе FastAPI сопоставил бы `/locations/drafts` с одностегментным параметром. Порядок объявления здесь часть контракта, а не стиль.

#### Player-facing (JWT + `verify_character_ownership`)
| # | Метод | Путь | Описание |
|---|-------|------|----------|
| D1 | GET | `/locations/drafts?character_id={id}` | История текстов персонажа: ≤10 `PostDraftListItem`, `updated_at DESC`. **Без `content`** — только `preview` (первые 180 символов чистого текста с многоточием), `char_count`, `location_name`, флаги `is_sent` / `is_active` |
| D2 | GET | `/locations/drafts/{draft_id}` | Один черновик целиком (`PostDraftRead`, вместе с текстом). 404 «Черновик не найден» |
| D3 | GET | `/locations/{location_id}/draft?character_id={id}` | Живой черновик персонажа в локации либо `null` |
| D4 | PUT | `/locations/{location_id}/draft` | Автосохранение (upsert). Тело `PostDraftSave` = `{character_id, content}`. Возвращает `null`, если текст был пуст и живая строка удалена — пустые черновики не хранятся. 400 «Черновик слишком длинный — максимум 100000 символов». Rate-limit 60 r/min, burst 20 (Nginx, regex-локация `~ ^/locations/[0-9]+/draft$`) |
| D5 | DELETE | `/locations/{location_id}/draft?character_id={id}` | Кнопка «Очистить черновик». 204, идемпотентно |
| D6 | DELETE | `/locations/drafts/{draft_id}` | Удалить строку из истории. 204. 404 «Черновик не найден» |

Для маршрутов, адресованных строкой (**D2, D6**), строка читается **первой**, и владелец проверяется по `row.character_id`, а не по `character_id` из запроса — чужой черновик отдаёт 403, а не содержимое.

#### Служебный (`require_permission("locations:delete")`)
| # | Метод | Путь | Описание |
|---|-------|------|----------|
| D7 | DELETE | `/locations/admin/drafts/by_character/{character_id}` | Очистка черновиков удаляемого персонажа. Возвращает `{"detail": "All post drafts deleted", "count": N}`, идемпотентно (`count: 0`, когда чистить нечего). Вызывается **character-service** из `delete_character` |

D7 намеренно **не** проверяет владельца: строка персонажа в этот момент уже уничтожается, и `verify_character_ownership` отдала бы 404. Доступ по RBAC — токен вызывающего пробрасывается character-service'ом, то есть чистить черновики может тот, кому позволено удалить персонажа. Разрешение `locations:delete` уже существовало, новой RBAC-миграции не потребовалось. Удаляются **только** `post_drafts`: посты персонажа остаются, они часть общего отыгрыша локации.

#### Архивация при отправке поста
Отдельного эндпоинта нет. `move_and_post` сразу после успешного `crud.create_post` зовёт `crud.archive_draft_on_post` (`main.py:1215-1224`) — живая строка получает `active = NULL`, `sent_at = now` и текст отправленного поста. Вызов обёрнут в `try/except` + `logger.warning` по образцу соседнего `create_action_gates`: бухгалтерия черновиков не имеет права уронить пост, который база уже приняла.

#### Константы (`crud.py:31-36`)
`MAX_DRAFTS_PER_CHARACTER = 10`, `MAX_DRAFT_LENGTH = 100_000`, `DRAFT_PREVIEW_LENGTH = 180`.

### Клиентские / Admin
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/locations/admin/data` | Вся иерархия для админ-панели |
| GET | `/locations/{id}/client/details` | Данные локации для клиента (соседи, игроки, посты, **gathering_nodes** с lazy-restore + lazy-finalize) |
| POST | `/locations/{id}/move_and_post` | Перемещение + создание поста |

### Добыча ресурсов (FEAT-128)

#### Player-facing
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/{location_id}/gathering-nodes/{node_id}/start` | Начать добычу. Списывает стамину полностью, создаёт сессию, авто-постит «{name} начинает добычу: {ресурс}». Rate-limit 10 req/min, burst 5 (Nginx) |
| POST | `/locations/{location_id}/gathering-nodes/{node_id}/cancel` | Ручная отмена. Возвращает `ceil(stamina_paid/2)` стамины |
| GET | `/locations/characters/{character_id}/active_gathering` | Polling-эндпоинт для активной сессии. Lazy-finalize при `complete_at <= NOW()`, в этом ответе вернёт `last_finished_session` с deltами |

#### Admin (require_permission `gathering:<action>`)
| Метод | Путь | Permission |
|-------|------|-----------|
| GET | `/locations/admin/locations/{location_id}/gathering-nodes` | `gathering:read` |
| POST | `/locations/admin/locations/{location_id}/gathering-nodes` | `gathering:create` |
| PUT | `/locations/admin/gathering-nodes/{node_id}` | `gathering:update` |
| DELETE | `/locations/admin/gathering-nodes/{node_id}` | `gathering:delete` (cascade на sessions) |
| POST | `/locations/admin/gathering-nodes/{node_id}/restore` | `gathering:update` (мгновенный refill) |

#### Internal (Header `X-Internal-Token: ${INTERNAL_SERVICE_TOKEN}`)
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/internal/cancel-gathering` | Вызывается battle-service из `pvp_attack` ДО создания боя. Отмечает status=`interrupted_by_battle`, рефанд стамины |

### Регистрация персонажа: стартовые точки и происхождение (FEAT-154)

Маршруты живут в **отдельном роутере** `registration_router` с тем же префиксом `/locations`, который подключается **первым** — иначе литеральные пути `/starting-points` и `/origins` проиграли бы параметрическим маршрутам основного роутера.

#### Публичные
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/locations/starting-points` | Курируемый список стартовых точек (`is_starting = 1`), отсортирован по `sort_order`. Полный каталог из 2260 локаций через этот контракт не публикуется. Поля: `id`, `name`, `image_url`, `starting_blurb`, `district_name`, `region_name`, `country_name`, `sort_order` |
| GET | `/locations/starting-points/{location_id}` | Проверочный запрос character-service при подаче и одобрении заявки. **404**, если локации нет **или** она не помечена как стартовая |
| GET | `/locations/origins` | Справочник происхождения без мягко удалённых записей. Поля: `id`, `name`, `emblem_url`, `map_image_url`, `summary`, `skitaltsy_attitude`, `archive_slug`, `sort_order` |

Справочник происхождения **шире** списка играбельных стран на карте (в него входят Железный Пояс, Эльфийские Сады, Республика Белый Клин) и **никогда не читает `Countries.description`** — описания стран в `Countries` являются админскими заглушками и игроку не показываются. Лорные тексты справочник несёт сам (`summary`, `skitaltsy_attitude`) и ссылкой на статью Архива (`archive_slug`).

#### Admin (`require_permission("origins:<action>")`)
| Метод | Путь | Permission |
|-------|------|-----------|
| GET | `/locations/admin/origins` | `origins:read` — возвращает `OriginCountryAdminRead` (публичные поля + `is_active`) и по умолчанию **включает мягко удалённые** (`include_inactive=true`), иначе скрытую запись нельзя было бы найти и вернуть |
| POST | `/locations/admin/origins` | `origins:create` |
| PUT | `/locations/admin/origins/{id}` | `origins:update` — восстановление скрытой записи делается здесь через `is_active: true`, отдельного restore-эндпоинта нет |
| DELETE | `/locations/admin/origins/{id}` | `origins:delete` — **мягкое удаление** (`is_active = 0`), возвращает `{id, is_active}`. Жёсткое потребовало бы проверки ссылок на `characters.origin_id` / `character_requests.origin_id` в чужом сервисе |

Разрешения `origins:*` заводятся миграцией **user-service `0026`**; до её применения админские маршруты отвечают 403 даже администратору.

#### Изменённые контракты
- **Создание/обновление локации** принимает два дополнительных поля: `is_starting: bool` (по умолчанию `false`) и `starting_blurb: Optional[str]` (≤2000 символов). Новое разрешение не заводилось — действует существующий модуль `locations:*`. ⚠️ В **response**-схемы локации эти поля намеренно не добавлены (это ломало 8 тестов, мокающих объект локации, а возврат жёсткого `false`/`null` дезинформировал бы); текущие значения админская форма читает из `GET /locations/{id}/details`.
- **`GET /locations/game-time`** (публичный) дополнен блоком `computed: {year, segment_name, segment_type, week, is_transition}` — тем самым, что уже отдавался админскому варианту. Существующие ключи не тронуты, `frontend/src/utils/gameTime.ts` продолжает считать время сам. Блок нужен character-service, чтобы проверять внутримировой стаж, **не реализуя календарь третий раз**.

## Иерархия мира

```
Country -> Region -> District -> Location
                                    ├── Location (child, type: subdistrict)
                                    └── Location (child)
```

Локации связаны **графом соседей** (LocationNeighbors) с `energy_cost` за переход.

## Таблицы БД

- **Countries** - id, name, description, leader_id, map_image_url
- **Regions** - id, name, country_id (FK), description, map_image_url, image_url, entrance_location_id, x, y
- **Districts** - id, name, region_id (FK CASCADE), description, image_url, entrance_location_id, recommended_level, x, y
- **Locations** - id, name, district_id (FK CASCADE), type (location/subdistrict), image_url, recommended_level, quick_travel_marker, parent_id (FK self CASCADE), description, **is_starting** BOOLEAN NOT NULL DEFAULT 0 (+ индекс `ix_locations_is_starting`), **starting_blurb** TEXT NULL (FEAT-154)
- **origin_countries** (FEAT-154) - id, name (UNIQUE), summary, skitaltsy_attitude, emblem_url, map_image_url, archive_slug, is_active (мягкое удаление), sort_order; индекс `ix_origin_countries_active_sort (is_active, sort_order)`. `archive_slug` — **мягкая** ссылка на `archive_articles.slug` без FK: статьи это контент и могут переименовываться, «висячий» slug деградирует до «нет ссылки на лор», а не до ошибки
- **LocationNeighbors** - id, location_id (FK CASCADE), neighbor_id (FK CASCADE), energy_cost
- **posts** - id, character_id, location_id (FK CASCADE), content (`TEXT` — см. «Известные проблемы»), post_type (regular/gated, FEAT-145), created_at, **edited_at** TIMESTAMP NULL, **edited_by_user_id** INT NULL (FEAT-159, миграция `038_post_edit_columns`)
  - `edited_at` / `edited_by_user_id` пишет ровно один путь кода — `crud.edit_post`. `NULL` в `edited_at` = пост не редактировали. Generic `updated_at ... ON UPDATE CURRENT_TIMESTAMP` отвергнут намеренно: он срабатывал бы на любую будущую запись в строку и пометил бы «изменено» всю таблицу.
  - `edited_by_user_id` — **чисто аудит**, клиенту не отдаётся. Клиент получает только производный `edited_by_admin` (см. «Редактирование поста»).
- **post_drafts** (FEAT-156) - id, character_id (cross-service, **без FK**), location_id (FK `Locations.id` CASCADE), content **MEDIUMTEXT**, active TINYINT NULL, sent_at TIMESTAMP NULL, created_at, updated_at; `UNIQUE (character_id, location_id, active)` = `uq_post_drafts_active`, индекс `idx_post_drafts_char_updated (character_id, updated_at)`
  - `content` — `MEDIUMTEXT`, а не `TEXT`: кириллица в `utf8mb4` стоит 2 байта на символ плюс разметка TipTap, длинный ролевой пост упёрся бы в 64 КБ и молча обрезался.
  - `active` — намеренно **nullable-флаг**, а не boolean. MySQL не умеет частично уникальные индексы, но считает `NULL` различными внутри UNIQUE-ключа, поэтому `UNIQUE (character_id, location_id, active)` даёт ровно один живой черновик на пару «персонаж + локация» и не ограничивает число архивных строк. Код пишет только `1` или `NULL`, никогда `0`.
  - `sent_at IS NOT NULL` = текст стал настоящим постом. Архивная строка с `sent_at IS NULL` — черновик, вытесненный из живого слота, но ещё лежащий в истории.
  - `updated_at` проставляется явно в `crud` (`datetime.now(timezone.utc)`), без MySQL `ON UPDATE` — чтобы порядок вытеснения был детерминированным и тестируемым.
  - **Вытеснение:** после каждой вставки `evict_drafts` оставляет персонажу 10 самых свежих строк по `updated_at`, остальные удаляет. Вытеснить может и живой черновик другой локации — это корректно: он по определению самый давно не трогавшийся из десяти.
  - Удаление локации уносит её черновики каскадом; удаление персонажа — через D7 (FK на `characters` в этом сервисе нет ни у одной таблицы).
- **gathering_nodes** (FEAT-128) - id, location_id (FK Locations CASCADE), node_name, category enum(ore/herb/wood), result_item_id (cross-service, no FK), result_quantity_per_gather, stamina_per_gather, daily_bank_max, current_bank, allow_concurrent_gather, depleted_at, restore_at (= depleted_at+24h), is_enabled, created_at, updated_at
- **gathering_sessions** (FEAT-128) - id, node_id (FK gathering_nodes CASCADE), character_id, tool_inventory_item_id (nullable, no FK), tool_item_id, tool_durability_at_start, started_at, complete_at, effective_speed/double/stamina_bonus_pct (snapshot), stamina_paid, base_quantity, skill_slug, status enum(active/completed/cancelled/interrupted_by_battle/inventory_full), finished_at, result_quantity, xp_awarded, rank_up_to

## Перемещение (move_and_post)

1. HTTP -> character-service: получить текущую локацию персонажа
2. Валидация перемещения (null -> любая, та же -> бесплатно, иначе -> сосед?)
3. Найти energy_cost из LocationNeighbors
4. HTTP -> attributes-service: проверить стамину
5. Создать пост в целевой локации
5.1. Архивировать живой черновик локации (`archive_draft_on_post`, FEAT-156) — в `try/except`, сбой не роняет пост
6. HTTP -> character-service: обновить current_location
7. HTTP -> attributes-service: списать стамину

⚠️ Шаг 5 **коммитит пост до** шагов 6 и 7. Если они упадут (два пути с 500), пост уже записан, а персонаж остался в старой локации с несписанной стаминой — см. «Известные проблемы».

## Коммуникация

### HTTP (входящие, важные для межсервисных контрактов)
- `character-service:8005` -> GET `/locations/starting-points`, GET `/locations/starting-points/{id}`, GET `/locations/game-time` (FEAT-154). Со стороны character-service все три вызова graceful: недоступность locations-service не блокирует подачу заявки и не проваливает одобрение — персонаж просто остаётся без стартовой локации, а `move_and_post` трактует `current_location_id IS NULL` как «куда угодно бесплатно»
- `character-service:8005` -> DELETE `/locations/admin/drafts/by_character/{character_id}` (FEAT-156, эндпоинт D7). Шаг 4.5 внутри `delete_character` (`character-service/app/main.py:1209-1221`), под `require_permission("locations:delete")` с проброшенным Bearer-токеном вызывающего. Вызов graceful: `try/except` + `logger.warning`, недоступность locations-service **не отменяет** удаление персонажа

### HTTP (исходящие)
- `character-service:8005` -> GET `/characters/{id}/profile`, GET `/characters/by_location`, PUT `/characters/{id}/update_location`, GET `/characters/{id}/short_info` (для имени/аватара активных gatherers в client/details)
- `character-attributes-service:8002` -> GET `/attributes/{id}`, POST `/attributes/{id}/consume_stamina`, POST `/attributes/{id}/refund_stamina` (FEAT-128: 50% возврат при cancel/battle-interrupt)
- `inventory-service:8004` -> POST `/inventory/internal/characters/{cid}/free_slots_check` (preflight на старте), POST `/inventory/internal/characters/{cid}/gathering/award` (атомарный award на finalize: ресурс + XP + ранг + прочность инструмента), GET `/inventory/characters/{cid}/gathering-skills` (ранговые бонусы для расчёта effective_*)

### Lazy-finalize паттерн (FEAT-128)
- Сессии добычи завершаются «лениво» при доступе: `client/details` (по локации) и `active_gathering` (по персонажу) перед формированием ответа вызывают `finalize_due_sessions`, которая под `SELECT ... FOR UPDATE` обрабатывает все сессии с `status='active' AND complete_at <= NOW()`.
- Не требует Celery beat. Подобно `Character.travel_cooldown_until` — таймстемп проверяется на каждом запросе.

## Известные проблемы

1. **Нет валидации existence** destination_location_id в move_and_post
2. **update_location_neighbors** удаляет всех соседей перед созданием новых - не атомарно
3. **Нет валидации parent_id** при создании локации
4. **Молчаливые ошибки** - character-service failures возвращают пустые данные без warning
5. **CORS allow-all** в production
6. **`posts.content` — `TEXT`** (`app/models.py:165`), то есть 64 КБ. Кириллица в `utf8mb4` стоит 2 байта на символ плюс разметка TipTap — длинный ролевой пост может молча обрезаться. `post_drafts.content` сделан `MEDIUMTEXT` именно поэтому, `posts` оставлен как был (FEAT-156, вне области)
7. **`move_and_post` коммитит пост до обновления локации и списания стамины** (`app/main.py:1213` против `:1241` и `:1256`) — при 500 на любом из этих шагов пост остаётся, а переход не состоялся. Предсуществующее, тот же порядок в `quick_move` (`:1470` / `:1477`)
