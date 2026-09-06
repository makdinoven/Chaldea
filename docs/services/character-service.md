# character-service

**Порт:** 8005
**Технологии:** FastAPI, SQLAlchemy (sync), PyMySQL, httpx, aio_pika (не используется)
**Путь:** `/home/dudka/chaldea/services/character-service/`

## Назначение

Управление персонажами: создание (через заявки на модерацию), профили, уровни, титулы, расы/подрасы/классы.

## Структура файлов

```
character-service/app/
├── main.py               # FastAPI app, все эндпоинты
├── models.py             # SQLAlchemy модели (8 моделей)
├── schemas.py            # Pydantic схемы
├── crud.py               # CRUD и бизнес-логика
├── presets.py            # МЁРТВЫЙ КОД: реальный источник статов — колонка subraces.stat_preset
├── locations_client.py   # HTTP-клиент к locations-service (FEAT-154), всё graceful
├── config.py             # Настройки из env
├── database.py           # Подключение к БД
├── producer.py           # Публикация в RabbitMQ (уведомления)
├── rabbitmq_consumer.py  # ЗАКОММЕНТИРОВАН (в main.py не импортируется)
├── alembic/              # Миграции, version_table = alembic_version_character
├── tests/                # Pytest тесты
└── requirements.txt
```

## API Endpoints

⚠️ Ниже перечислены не все эндпоинты сервиса — только игровое ядро. Административные блоки (NPC, mob-templates, mob-packs, active-mobs, бестиарий, телепорты, логи) в этот документ не вынесены; источник истины — `app/main.py`.

### Валидация заявки (FEAT-154)

Общий валидатор используется и в `POST /requests/`, и в `PUT /requests/{id}`. Порядок: **владение (403) -> Pydantic (422) -> домен (400)** — он нагружен смыслом, тест на 403 при чужом `user_id` проверяет именно его.

- Существование `id_race`, `id_class`, `id_subrace` **и** принадлежность подрасы выбранной расе
- `name` — 1..20 символов после `strip()`; валидатор **записывает очищенное имя обратно** в payload, иначе `"   " + 20 символов` прошло бы проверку и упало на `String(20)` с MySQL 1406
- `appearance` непустой, `age` в 1..100000, `sex` из `male`/`female`/`genderless`
- `skitaltsy_since_segment` в 0..7; `skitaltsy_since_year` не позже текущего игрового года и не раньше рождения персонажа — **обе границы пропускаются**, если locations-service не ответил
- Лимит 5 персонажей: `users_character` (таблица user-service, при ошибке запроса — пропуск, как в claim) **плюс** свои заявки `creation` в статусе `pending`
- `origin_id` — только `> 0`; существование межсервисно **не проверяется**
- Рост вне диапазона подрасы и нехарактерная для подрасы страна **не блокируют** ничего — это подсказки на клиенте, решение принимает модератор


### Заявки на создание персонажа
| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/characters/requests/` | игрок | Создать заявку. Порядок проверок: владение (403) -> Pydantic (422) -> доменная валидация (400). Проверяет существование расы/подрасы/класса, принадлежность подрасы расе, лимит 5 персонажей, стаж и стартовую точку |
| POST | `/characters/requests/claim` | игрок | Заявка на присвоение существующего персонажа (NPC) |
| GET | `/characters/requests/my` | игрок | Свои заявки со статусом и причиной отказа. **Объявлен ДО `/requests/{request_id}`**, иначе `my` парсится как int |
| PUT | `/characters/requests/{id}` | владелец | Отредактировать и переотправить отклонённую заявку. `status` -> `pending`, `rejection_reason` очищается. 403 не владелец · 404 нет заявки · 409 статус не `rejected` |
| POST | `/characters/requests/{id}/approve` | `characters:approve` | Одобрить заявку (полный workflow, см. ниже) |
| POST | `/characters/requests/{id}/reject` | `characters:approve` | Отклонить заявку. Тело `{"reason": "..."}` необязательно, ≤1000 символов (иначе **400** с русским текстом, не 422). Отклонить можно только `pending` — иначе **409**. Публикует уведомление игроку |
| GET | `/characters/moderation-requests` | админ | Все заявки на модерации (без пагинации) |

### Управление персонажами
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/characters/{id}/full_profile` | Полный профиль с уровнем, атрибутами, титулом |
| GET | `/characters/{id}/profile` | Профиль с данными пользователя |
| GET | `/characters/{id}/short_info` | Краткая инфо (имя, аватар, локация) |
| GET | `/characters/{id}/race_info` | Раса, подраса, класс, уровень |
| GET | `/characters/list` | Список всех персонажей |
| DELETE | `/characters/{id}` | Удалить персонажа |
| PUT | `/characters/{id}/deduct_points` | Списать stat points |

### Локации
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/characters/by_location?location_id=X` | Персонажи в локации |
| PUT | `/characters/{id}/update_location` | Обновить текущую локацию |

### Титулы
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/characters/titles/` | Создать титул |
| GET | `/characters/titles/` | Все титулы |
| GET | `/characters/{id}/titles` | Титулы персонажа |
| POST | `/characters/{id}/titles/{title_id}` | Назначить титул |
| POST | `/characters/{id}/current-title/{title_id}` | Установить текущий титул |

### Метаданные и справочники
| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/characters/metadata` | публично | Все расы, подрасы с атрибутами |
| GET | `/characters/races` | публично | Расы с подрасами. На каждой подрасе, помимо `stat_preset`/`image`: `distinctive_features`, `height_min`, `height_max`, `typical_origin_ids` (FEAT-154) |
| GET | `/characters/classes` | публично | Список классов (`id_class`, `name`, `description`). Заменил фиктивный `INITIAL_CLASSES` на фронтенде |
| GET | `/characters/{id}/public` | публично | Данные одного персонажа для «паспорта». Путь с суффиксом `/public`, чтобы не конфликтовать с `/list`, `/races`, `/classes`, `/metadata`, `/starter-kits` |

### Стартовые наборы (FEAT-154)
| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/characters/starter-kits` | публично | Без параметров — **только наборы классов по умолчанию** (`origin_id = 0`), то есть ровно тот набор строк, что был до фичи. `?include_origins=true` — все строки |
| GET | `/characters/starter-kits/resolve?class_id=&origin_id=` | публично | Разрешённый набор для пары. Возвращает `resolved_from` = `exact` \| `class_default` \| `none`. 404, если класса нет |
| PUT | `/characters/starter-kits/{class_id}` | `characters:update` | Записать набор класса по умолчанию (`origin_id = 0`). Контракт не менялся |
| PUT | `/characters/starter-kits/{class_id}/origins/{origin_id}` | `characters:update` | Создать/обновить набор для пары. 400 при `origin_id = 0` — дефолт пишется только эндпоинтом выше |
| DELETE | `/characters/starter-kits/{class_id}/origins/{origin_id}` | `characters:update` | Убрать переопределение, пара снова падает на дефолт класса. 404, если переопределения нет |
| GET | `/characters/starter-kits/coverage` | `characters:update` | Матрица заполненности (класс × происхождение) для контент-чеклиста. Не публичный: показывает состояние наполнения |

## Таблицы БД

- **characters** - персонажи (name, race, subrace, class, level, stat_points, avatar, current_location_id, currency_balance, is_npc, npc_role/npc_status, travel_cooldown_until)
- **character_requests** - заявки (status: pending/approved/rejected)
- **races** / **subraces** - расы и подрасы. ⚠️ Локальный сид (`docker/mysql/init/01-seed-data.sql`) содержит **отброшенный сеттинг** (7 рас, 16 подрас, мир «Ло-Ка»). Актуальные данные — только на проде: 10 рас, ~35 подрас, мир Каркарис. Разработка ведётся на дампе прод-базы
- **classes** (3) - Воин, Ловкач, Маг
- **starter_kits** - стартовые наборы, ключ — **пара** (`class_id`, `origin_id`), см. ниже
- **titles** - титулы
- **character_titles** - many-to-many персонаж<->титул
- **level_thresholds** - таблица опыт->уровень

### Колонки, добавленные FEAT-154

Все колонки **nullable и без бэкфилла** — старый образ сервиса работает на новой схеме, откат безопасен в обе стороны.

| Таблица | Колонка | Назначение |
|---------|---------|-----------|
| `character_requests` | `origin_id INT NULL` | Происхождение. Указывает на `origin_countries.id` в **locations-service**, FK нет (граница владения) |
| | `start_location_id BIGINT NULL` | Выбранная игроком стартовая точка |
| | `skitaltsy_since_year INT NULL` | Внутримировой стаж: игровой год вступления в Скитальцы |
| | `skitaltsy_since_segment TINYINT NULL` | Сегмент года (0..7) |
| | `rejection_reason TEXT NULL` | Причина отказа модератора |
| `characters` | `origin_id INT NULL` | Копируется из заявки при одобрении |
| | `registered_at TIMESTAMP NULL` | **Системная** дата регистрации, ставится при одобрении. Отличается от внутримирового стажа. NULL у NPC и у всех персонажей, созданных до фичи |
| | `skitaltsy_since_year` / `skitaltsy_since_segment` | Копируются из заявки |
| | `granted_kit JSON NULL` | Замороженный слепок выданного набора, см. ниже |
| `subraces` | `distinctive_features TEXT NULL` | Отличительные особенности облика. Если пусто — паспорт/мастер показывают обычное `description` |
| | `height_min INT NULL` / `height_max INT NULL` | Характерный диапазон роста. Проверяется **только на клиенте**, мягкое предупреждение, отправку не блокирует |
| | `typical_origin_ids JSON NULL` | Массив `origin_countries.id` — характерные для подрасы страны. Нехарактерный выбор разрешён и лишь помечается как редкий |
| `starter_kits` | `origin_id INT NOT NULL DEFAULT 0` | `0` = набор класса по умолчанию |

**Миграции:** `019_char_registration` (колонки заявки/персонажа/подрасы), `020_starter_kit_origin` (`starter_kits.origin_id`, `characters.granted_kit`, пересборка уникального ключа).

⚠️ **Порядок DDL в миграции 020 обязателен именно такой:** сначала создаётся парный `UNIQUE (class_id, origin_id)`, и только потом дропается старый одноколоночный уникальный индекс по `class_id`. Обратный порядок падает на MySQL с `(1553, "Cannot drop index 'class_id': needed in a foreign key constraint")` — FK `class_id -> classes.id_class` требует индекса по колонке, а в парном ключе `class_id` стоит слева и берёт эту роль на себя. `downgrade()` зеркалит порядок. Откат **лоссовый**: он удаляет все переопределения (`DELETE FROM starter_kits WHERE origin_id <> 0`) и все слепки `granted_kit`.

## Стартовые наборы: пара (класс × происхождение) — FEAT-154

Набор зависит не только от класса, но и от происхождения: воин из Шинзо и воин из Мидденгерда получают разную экипировку.

**Единственная точка разрешения — `crud.resolve_starter_kit(db, class_id, origin_id)`.** Никто не дублирует цепочку у себя:

```
1) точная пара (class_id, origin_id) -> resolved_from = "exact"
2) иначе набор класса по умолчанию (class_id, 0) -> resolved_from = "class_default"
3) иначе пустой набор -> resolved_from = "none"
```

Шаг 3 воспроизводит поведение до фичи: класс без строки в `starter_kits` просто не даёт ничего. Запрос с `origin_id = 0` считается `"exact"`, а не `"class_default"` — ни на что не откатывались.

Почему `origin_id = 0`, а не NULL: MySQL считает NULL-ы различными внутри UNIQUE-индекса, поэтому с nullable-колонкой в `starter_kits` можно было бы завести два конкурирующих дефолта для одного класса и получить недетерминированное разрешение. `origin_countries.id` — AUTO_INCREMENT и нуля не выдаёт.

### Заморозка выданного набора (`granted_kit`, правило 12d)

| Кто | Что использует |
|-----|----------------|
| Мастер создания, шаг «Путь» | резолвер — выдавать ещё нечего |
| Одобрение заявки | резолвер **ровно один раз**: один и тот же результат идёт и на выдачу, и в слепок |
| Паспорт | слепок `characters.granted_kit` |
| Паспорт, если `granted_kit IS NULL` | резолвер как запасной путь |

Паспорт — лорная запись «тебе это выдали при вступлении», а не живое отображение шаблона. Поэтому последующее редактирование набора в админке **не меняет** паспорта уже созданных персонажей. Так как выдача и слепок берутся из одного вызова резолвера, разойтись они не могут по построению.

Слепок хранит **только идентификаторы**: `{class_id, origin_id, resolved_from, items:[{item_id, quantity}], skills:[{skill_id}], currency_amount, granted_at}`. Названия, иконки и редкость по-прежнему резолвятся живыми запросами — переименованный предмет остаётся тем же предметом.

**Бэкфилла нет.** `granted_kit IS NULL` означает «персонаж создан до фичи»; `GET /characters/{id}/public` в этом случае резолвит набор на лету и отдаёт `granted_kit_is_snapshot: false`, чтобы клиент мог показать реконструкцию как реконструкцию. Бэкфилл из сегодняшнего дефолта класса **сфабриковал** бы запись о выдаче, которой не было.

## Workflow создания персонажа (approve)

Распределённая неатомарная транзакция: один `db.commit()` в конце, вокруг него вызовы пяти сервисов. Критические шаги (атрибуты, привязка к пользователю) при провале откатывают транзакцию; остальные — graceful.

1. Заявка существует и в статусе `pending` (иначе 404 / 400), лимит персонажей не превышен (лимит настраивается переменной `MAX_CHARACTERS_PER_USER`; по умолчанию `0` = без ограничений, и проверка пропускается)
2. **Разрешить стартовый набор** — `crud.resolve_starter_kit(db, id_class, origin_id or 0)`, **ровно один вызов**. Результат идёт и на выдачу, и в слепок `granted_kit`. Тот же вызов делал мастер создания, поэтому выдаётся ровно то, что игроку показали
3. Создать `Character` (`flush`) — с `currency_balance` из набора, `registered_at = utcnow()`, `origin_id` и `skitaltsy_since_*` из заявки, `granted_kit` = слепок. `avatar` берётся из заявки, при её отсутствии — `subraces.image`, затем `''`
4. Сгенерировать атрибуты по подрасе — из колонки **`subraces.stat_preset`** (не из `presets.py`, он мёртв); при отсутствии пресета — все по 10 с warning
5. HTTP -> **inventory-service**: создать инвентарь с предметами набора *(graceful)*
6. HTTP -> **skills-service**: назначить навыки набора + подрасовый `SUBRACE_SKILL_ID = 7` *(graceful)*
7. HTTP -> **character-attributes-service**: создать атрибуты *(критично — при провале rollback + 500)*
8. Обновить `character.id_attributes` (`flush`)
9. **Разрешить стартовую локацию** — цепочка ниже *(graceful)*
10. Статус заявки -> `approved` (`flush`)
11. HTTP -> **user-service**: создать связь user-character *(критично — при провале rollback + 500)*
12. `db.commit()` — единый коммит шагов 3, 8, 9, 10
13. RabbitMQ: уведомление игроку *(не блокирует)*

Ответ, помимо `message`, содержит `current_location_id` и `location_warning`.

⚠️ Шаги 5-7 дублируются публикацией в RabbitMQ теми же данными. Консьюмеры реально работают и идемпотентны, но узкая гонка остаётся — см. `docs/ISSUES.md`.

### Разрешение стартовой локации (FEAT-154 §3.6)

**При подаче заявки** — мягко: `GET /locations/starting-points/{id}`; 404 -> 400 «Выбранная точка не входит в список стартовых», сбой транспорта -> заявка принимается, пишется лог.

**При одобрении** — цепочка, каждый шаг graceful, исключений не бросает и транзакцию не откатывает:

| Шаг | Условие | `current_location_id` | `location_warning` |
|-----|---------|------------------------|--------------------|
| 1 | Игрок выбрал точку, locations-service подтвердил | выбранная | `null` |
| 2a | Игрок выбрал точку, но подтвердить её не удалось (404 или сервис не ответил) | первая точка курируемого списка | «Выбранная стартовая точка недоступна, назначена точка по умолчанию.» |
| 2b | **Игрок ничего не выбирал**, назначена точка по умолчанию | первая точка курируемого списка | `null` (лог уровня INFO) |
| 3 | Курируемый список пуст или locations-service недоступен | `NULL` | «Стартовая локация не назначена — обратитесь к администратору.» |

`location_warning` — канал **деградации**, а не журнал: он непустой только тогда, когда результат хуже запрошенного. Назначить курируемый дефолт заявке, в которой точка не выбиралась, — штатное поведение, поэтому шаг 2b молчит (иначе модератор читает про «недоступную» точку там, где ничего не выбиралось и ничего не ломалось). Информация при этом не теряется: у вызывающего есть и `start_location_id` заявки, и `current_location_id` в ответе.

Шаг 3 безопасен: `move_and_post` в locations-service трактует `current_location_id IS NULL` как «можно переместиться куда угодно бесплатно», поэтому персонаж не застревает. Именно поэтому вызов классифицирован как graceful, а не критический: NULL-локацию модератор поправит, а наполовину одобренную заявку — нет.

### Заявки на присвоение (`claim`)

Ветка `claim` в одобрении **намеренно** не ставит стартовую локацию, стартовый набор, `registered_at` и `granted_kit` — персонаж уже существует. Это решение пользователя, а не пробел.

## Система уровней

- `LevelThreshold` - таблица `level_number` -> `required_experience`
- При получении профиля: проверка `passive_experience` >= threshold -> level up
- **+10 stat points** за каждый уровень
- Опыт списывается при повышении уровня

## Коммуникация

### HTTP (исходящие)
- `inventory-service:8004` - POST `/` (создание инвентаря)
- `skills-service:8003` - POST `/assign_multiple` (назначение навыков)
- `character-attributes-service:8002` - POST `/`, GET `/{id}`, GET `/{id}/passive_experience`
- `user-service:8000` - POST `/users/user_characters/`, PUT `/users/{id}/update_character`, GET `/users/{id}`, GET `/users/me` (auth во всех защищённых эндпоинтах)
- `locations-service:8006` — **новая зависимость, появилась в FEAT-154** (`LOCATIONS_SERVICE_URL`, дефолт `http://locations-service:8006`). Клиент — `app/locations_client.py`, таймаут 5 с, три чтения:
  - GET `/locations/starting-points/{id}` — проверка выбранной стартовой точки при подаче и при одобрении заявки
  - GET `/locations/starting-points` — курируемый список, первый элемент = точка по умолчанию
  - GET `/locations/game-time` — текущий игровой год из блока `computed.year` для проверки стажа

  **Все три graceful.** Клиент возвращает `None`, если сервис не смог ответить, и вызывающая сторона пропускает проверку. Недоступность locations-service никогда не блокирует подачу и не проваливает одобрение. Календарь здесь **не реализуется повторно** — игровой год всегда читается в рантайме, никаких захардкоженных годов в коде, валидации, фикстурах и сидах.

### RabbitMQ
Консьюмер (`rabbitmq_consumer.py`) закомментирован и в `main.py` не импортируется — входящих сообщений сервис не читает. **Продюсер (`producer.py`) работает**: одобрение и отклонение заявки публикуют уведомление игроку в очередь `general_notifications`; одобрение дополнительно дублирует полезную нагрузку по инвентарю/навыкам/атрибутам (см. предупреждение в workflow выше).

## FEAT-125: mob_template_skills теперь по skill_id

- Таблица `mob_template_skills` после Alembic `016_repoint_mob_template_skills` хранит `skill_id` (FK → `skills.id`, ON DELETE CASCADE) вместо `skill_rank_id`. UNIQUE переимённован на `(mob_template_id, skill_id)`.
- Бэкфилл колонки делает skills-service `003_perk_system`, character-service 016 только дропает старое и промоутит NOT NULL (+ 30-секундный short-poll, чтобы выдержать Compose race).
- `crud.send_skills_presets_request` теперь шлёт в skills-service `{character_id, skills:[{skill_id}]}` без `rank_number`.
- `schemas.MobSkillResponse.skill_id`, `MobSkillsUpdate.skill_ids`, `BestiarySkillEntry.skill_id`.

## Известные проблемы

1. **RabbitMQ-консьюмер отключён** - код закомментирован, aio_pika остаётся в зависимостях. Продюсер при этом используется
2. **Опыт не сохраняется** - `check_and_update_level()` уменьшает passive_experience локально, но не сохраняет в attributes-service
3. **Неиспользуемый код** - `send_equipment_slots_request()` ссылается на несуществующий `EQUIPMENT_SERVICE_URL` (в `config.py` его нет; тест маскирует это, подставляя атрибут в `settings`)
4. **`presets.py` — мёртвый код.** Реальный источник статов подрасы — колонка `subraces.stat_preset`
5. **Аутентификация частичная.** Заявки, админские и модераторские эндпоинты защищены (`get_current_user_via_http`, `require_permission`), но `PUT /characters/{id}/deduct_points`, `PUT /characters/{id}/update_location` и `POST /characters/{id}/set_travel_cooldown` не имеют ни auth, ни проверки владения
6. **`character_requests.name` — `String(20)`, `characters.name` — `String(255)`.** Заявка на присвоение NPC с длинным именем не проходит round-trip
7. **Одобрение неатомарно** - 13 шагов по пяти сервисам под одним коммитом; дублирующие публикации в RabbitMQ оставляют узкую гонку двойной выдачи

Полный список с приоритетами — в `docs/ISSUES.md`.
