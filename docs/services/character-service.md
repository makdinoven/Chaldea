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
├── economy_api.py        # FEAT-181: роутер API экономики (публичная валюта + /admin/economy/*)
├── economy_crud.py       # FEAT-181: сводка, счета, журнал, эмиссия/корректировка, настройки
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

**Уровни (2026-10-25).** `level_thresholds.required_experience` — опыт ВСЕГО для уровня (со 2-го); подъём уровня
(`crud.check_and_update_level`) сравнивает с ним суммарный пассивный опыт, несколько уровней за раз. Админка
«Уровни и опыт» (`/admin/levels`): `GET/PUT /characters/admin/levels/thresholds` (`characters:read` / `characters:update`),
PUT заменяет таблицу целиком (уровни подряд со 2-го, опыт строго растёт). Набранные уровни не отнимаются; игрокам, у
кого опыт ниже порога их уровня, он подтягивается до порога (`crud.raise_xp_to_level_thresholds`, пишет в
`character_attributes`). Полоска профиля (`main.level_progress`): набрано в уровне (не меньше 0) / шаг уровня,
`exp_to_next_level` — осталось, `max_level` — выше таблицы.

**Награды мобов (2026-10-25).** Мобы дают только опыт: `gold_reward` в `mob_templates` остаётся, но battle-service его
больше не выплачивает, а из админки поле убрано. `POST /characters/admin/mob-templates/fill-xp[?dry_run=true]`
(`mobs:manage`) ставит опыт по формуле шаблонам, у которых он 0: обычный 20 + 6 × уровень, элитный ×3, босс ×10
(`crud.default_mob_xp`); заданный вручную опыт не трогается.

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
| GET | `/characters/{id}/full_profile` | Полный профиль с уровнем, атрибутами, титулом. **FEAT-171 (C1, optional-auth):** владелец, админ/модератор с `characters:read` и NPC получают прежнее тело; любой другой зритель — `PublicProfileResponse` (`id`, `name`, `level`, `active_title`, `active_title_rarity`, `avatar`). Ключей `currency_balance`, `stat_points`, `level_progress`, `attributes` в его ответе **нет** (именно отсутствуют, а не null). Несуществующий персонаж → 404 |
| GET | `/characters/{id}/profile` | Профиль с данными пользователя; `character_class_id` (1 воин, 2 плут, 3 маг) — для миниатюр на 3D-столе данжа |
| GET | `/characters/{id}/short_info` | Краткая инфо (имя, аватар, локация). **FEAT-171 (C4, D7):** `currency_balance` убран **безусловно, для всех** — маршрут читают сервис-в-сервис, поэтому optional-auth тут не годится. Баланс отдаёт только двойник `/characters/internal/{id}/short_info` |
| GET | `/characters/{id}/race_info` | Раса, подраса, класс, уровень |
| GET | `/characters/list` | Список всех персонажей |
| DELETE | `/characters/{id}` | Удалить персонажа. **FEAT-181 C8:** весь баланс уходит проводкой `character_deleted` в казну его локации (иначе «Казна Скитальцев»), счёт персонажа помечается неактивным — в той же транзакции, что и удаление строки. То же делает `DELETE /characters/admin/npcs/{id}` |
| PUT | `/characters/internal/{id}/deduct_points` | Списать stat points (internal, `X-Internal-Token`) |
| GET | `/characters/internal/{id}/full_profile` | **FEAT-171 (C1i):** двойник `GET /characters/{id}/full_profile` для межсервисных вызовов. Тело общее с публичным маршрутом (общий хелпер `_build_full_profile`), но остаётся полным после того, как Pass B утончит публичный ответ. Требует `X-Internal-Token` (пустой env → 503, неверный заголовок → 401), nginx отдаёт 403 снаружи. Вызывающий — character-attributes-service (`perk_evaluator`, `/upgrade`) |
| GET | `/characters/internal/{id}/short_info` | **FEAT-171 (C4i):** двойник `GET /characters/{id}/short_info`, **всегда с `currency_balance`** — именно он питает `/users/me` и счётчик золота в шапке, когда Pass B уберёт баланс из публичного тела. Та же защита `X-Internal-Token`. Вызывающие — user-service (`_fetch_character_short`) и locations-service |

### Журнал и история постов (FEAT-095, приватность — FEAT-171)
| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/characters/{id}/logs` | владелец / админ-модератор с `characters:read` / NPC | Журнал событий персонажа. **FEAT-171 (C8, Q4a):** в описаниях и `metadata` лежат лут, золото и опыт, поэтому маршрут закрыт жёстко: чужой и гость → **403** «Эти данные доступны только владельцу персонажа», несуществующий персонаж → **404** «Персонаж не найден» (проверка существования идёт раньше проверки владения, чтобы 403 vs 404 не работал оракулом) |
| GET | `/characters/{id}/post-history` | публично (optional-auth) | История отыгрышных постов. **FEAT-171 (C7, Q4b):** сами посты публичны, но `xp_earned` отдаётся только владельцу, админу/модератору и на NPC — у чужого этого ключа в элементах списка нет (`schemas.PublicPostHistoryItem`). Несуществующий персонаж → 404 |

### Локации
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/characters/by_location?location_id=X` | Персонажи в локации |
| PUT | `/characters/internal/{id}/update_location` | Обновить текущую локацию (internal, `X-Internal-Token`, nginx 403 снаружи) |
| POST | `/characters/admin/{id}/move` | Перенос персонажа в произвольную локацию (админ, `characters:teleport`). Гасит намерения и заявки в покидаемой локации, отменяет сбор ресурсов, сбрасывает кулдаун перехода, пишет `admin_teleport` в `character_logs`. Отказ 409, если персонаж в бою или в подземелье; та же локация — no-op без записей |

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
| GET | `/characters/{id}/public` | публично (optional-auth) | Данные одного персонажа для «паспорта». Путь с суффиксом `/public`, чтобы не конфликтовать с `/list`, `/races`, `/classes`, `/metadata`, `/starter-kits`. **FEAT-171 (C3):** `granted_kit` и `granted_kit_is_snapshot` остаются публичными, а `starting_attributes` и `starting_attributes_is_snapshot` отдаются только владельцу, админу/модератору с `characters:read` и на NPC — у чужого этих ключей в JSON нет (`schemas.CharacterPublicStrangerResponse`) |

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
| | `starting_attributes JSON NULL` | Замороженный слепок стартовых характеристик (пресет подрасы на момент одобрения), см. ниже |
| `subraces` | `distinctive_features TEXT NULL` | Отличительные особенности облика. Если пусто — паспорт/мастер показывают обычное `description` |
| | `height_min INT NULL` / `height_max INT NULL` | Характерный диапазон роста. Проверяется **только на клиенте**, мягкое предупреждение, отправку не блокирует |
| | `typical_origin_ids JSON NULL` | Массив `origin_countries.id` — характерные для подрасы страны. Нехарактерный выбор разрешён и лишь помечается как редкий |
| `starter_kits` | `origin_id INT NOT NULL DEFAULT 0` | `0` = набор класса по умолчанию |

**Миграции:** `019_char_registration` (колонки заявки/персонажа/подрасы), `020_starter_kit_origin` (`starter_kits.origin_id`, `characters.granted_kit`, пересборка уникального ключа), `021_starting_attributes` (`characters.starting_attributes`, чисто аддитивная, откат дропает колонку).

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

### Заморозка стартовых характеристик (`starting_attributes`) — FEAT-155

Тот же принцип, что и у набора, и по той же причине.

| Кто | Что использует |
|-----|----------------|
| Мастер создания | пресет подрасы — начислять ещё нечего |
| Одобрение заявки | `crud.generate_attributes_for_subrace` **ровно один раз**: один результат идёт и в character-attributes-service, и в слепок |
| Паспорт | слепок `characters.starting_attributes` |
| Паспорт, если слепка нет | `subraces.stat_preset` как реконструкция, `starting_attributes_is_snapshot: false` |

**`GET /characters/{id}/public` не ходит в character-attributes-service и не отдаёт текущие статы.** До FEAT-155 отдавал: блок «Оценка при вступлении» показывал актуальный билд персонажа, из-за чего подпись «Всего распределено: N из 100 очков подрасы» врала (N > 100 после вложенных очков), а чужая анкета раскрывала распределение очков игрока. Утечка закрыта в источнике — из ответа API просто нечего взять. Уровень (`level`) остаётся публичным: спойлером было распределение, а не УР.

**Бэкфилла нет** (по образцу D18). NULL означает «персонаж создан до фичи», и паспорт реконструирует пресет его подрасы, честно помечая это подписью «Запись восстановлена по пресету подрасы». Пресет известен и по смыслу равен стартовым характеристикам, поэтому реконструкция не выдумывает данные; но выдавать её за оригинал нельзя. Если у подрасы нет и пресета — `starting_attributes: null`, и блок не рисуется вовсе. Текущие статы не показываются ни при каком раскладе.

## Workflow создания персонажа (approve)

Распределённая неатомарная транзакция: один `db.commit()` в конце, вокруг него вызовы пяти сервисов. Критические шаги (атрибуты, привязка к пользователю) при провале откатывают транзакцию; остальные — graceful.

1. Заявка существует и в статусе `pending` (иначе 404 / 400), лимит персонажей не превышен (лимит настраивается переменной `MAX_CHARACTERS_PER_USER`; по умолчанию `0` = без ограничений, и проверка пропускается)
2. **Разрешить стартовый набор** — `crud.resolve_starter_kit(db, id_class, origin_id or 0)`, **ровно один вызов**. Результат идёт и на выдачу, и в слепок `granted_kit`. Тот же вызов делал мастер создания, поэтому выдаётся ровно то, что игроку показали
2.5. **Сгенерировать атрибуты по подрасе** — `crud.generate_attributes_for_subrace`, из колонки **`subraces.stat_preset`** (не из `presets.py`, он мёртв); при отсутствии пресета — все по 10 с warning. **Ровно один вызов**: результат идёт и в слепок `starting_attributes` (шаг 3), и в character-attributes-service (шаг 7)
3. Создать `Character` (`flush`) — с `currency_balance = 0` (золото набора — проводкой на шаге 11.5), `registered_at = utcnow()`, `origin_id` и `skitaltsy_since_*` из заявки, `granted_kit` = слепок набора, `starting_attributes` = слепок пресета. `avatar` берётся из заявки, при её отсутствии — `subraces.image`, затем `''`
4. *(шага 4 больше нет — генерация атрибутов поднята в 2.5, чтобы слепок и начисление шли из одного результата)*
5. HTTP -> **inventory-service**: создать инвентарь с предметами набора *(graceful)*
6. HTTP -> **skills-service**: назначить навыки набора + подрасовый `SUBRACE_SKILL_ID = 7` *(graceful)*
7. HTTP -> **character-attributes-service**: создать атрибуты *(критично — при провале rollback + 500)*
8. Обновить `character.id_attributes` (`flush`)
9. **Разрешить стартовую локацию** — цепочка ниже *(graceful)*
10. Статус заявки -> `approved` (`flush`)
11. HTTP -> **user-service**: создать связь user-character *(критично — при провале rollback + 500)*
11.5. **FEAT-181 C1:** `crud.post_starter_kit` — проводка `starter_kit` из казны региона стартовой локации (шаг 9; без локации — «Казна Скитальцев») персонажу, ключ `starter_kit:c:<id>`. Последний шаг перед коммитом, после всех HTTP-вызовов
12. `db.commit()` — единый коммит шагов 3, 8, 9, 10, 11.5
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

### Книги опыта (FEAT-168 #6)

Два места записи опыта персонажа в этом сервисе умножают начисление на активную книгу опыта из inventory-service:

| Функция | Источник опыта (`buff_type`) |
|---|---|
| `crud.add_rewards_to_character(..., xp_source=XP_SOURCE_BATTLE)` | `character_xp_battle_bonus` по умолчанию; боевой пропуск шлёт `character_xp_pass_bonus` в теле `POST /characters/{cid}/add_rewards` (поле `xp_source`, валидируется по `crud.CHARACTER_XP_SOURCES`) |
| `crud._grant_title_xp` | `character_xp_title_bonus` — **только пассивный опыт**, активный (очки навыков) книгами не ускоряется |

Запрос множителя — `GET {INVENTORY_SERVICE_URL}internal/characters/{cid}/xp-multiplier` с `X-Internal-Token`, таймаут 5 с, в двух вариантах: `crud.get_character_xp_multiplier` (блокирующий, **только для обработчиков-`def`**) и `crud.get_character_xp_multiplier_async` (httpx.AsyncClient, для `async def`). **Fail-open, но не молча:** любая ошибка, таймаут, неизвестный источник, NaN/бесконечность или множитель < 1.0 дают 1.0 — опыт не теряется из-за недоступного inventory-service, — и провал пишется в лог уровнем **error** с id персонажа, источником опыта и затраченным временем. Кому нужно отличить «книги нет» от «спросить не вышло», есть `crud.lookup_character_xp_multiplier[_async]`: они возвращают `XpMultiplierLookup(multiplier, ok, reason, elapsed_ms)`, а `get_character_xp_multiplier[_async]` — тонкие обёртки над ними, возвращающие только число. Округление `int(xp * множитель)`, как у опыта профессии.

**Правило порядка (ревью #2, #3 и #4).** Множитель запрашивает **обработчик**, а не функция начисления, и передаёт вниз параметром `xp_multiplier`; `None` везде значит «книги нет» — начисляется базовый опыт. Ограничения, каждое оплачено отдельным инцидентом:

1. Сессия БД не должна ждать соседний сервис с открытой транзакцией (инцидент 2026-09-04 с QueuePool, см. `docs/ISSUES.md`).
2. **Освобождать соединение откатом чужой сессии нельзя.** `rollback()` протухает загруженные объекты независимо от `expire_on_commit`, и вызывающий падает на следующем чтении своего объекта (в async-сессии — `MissingGreenlet`).
3. **В `async def` нельзя ходить блокирующим клиентом** — 5 секунд таймаута останавливают весь event loop. Для таких обработчиков есть `crud.get_character_xp_multiplier_async` (httpx.AsyncClient); блокирующий `crud.get_character_xp_multiplier` — только для обработчиков-`def`, которые FastAPI уводит в threadpool. Ядро у них общее, поэтому белый список источников, fail-open и зажим NaN/бесконечности одинаковы.
4. **Из колбэков, которые нам шлёт inventory-service, обратно в inventory-service ходить нельзя на каждый вызов** — получается круг: инвентарь ждёт нас, держа свою транзакцию, мы ждём инвентарь. Поэтому автовыдача титулов спрашивает множитель только тогда, когда титул реально открылся (см. ниже).

**Автовыдача титулов — один помощник на все пути.** `main._evaluate_titles_with_book(db, character_id)` делает три шага: `crud.find_unlockable_titles` (только чтение, сети не касается) → множитель книги, **только если титул открылся и у него есть пассивный опыт** (`crud.title_reward_needs_the_book`) → `crud.grant_unlocked_titles` (одна транзакция, сетевых вызовов внутри нет). `crud.evaluate_titles` остался синхронной обёрткой над этими двумя половинами. Итог: надевание предмета, при котором ничего не открылось, в inventory-service не ходит вовсе, а титул, который открылся, получает книгу.

Где именно берётся множитель:

| Путь | Обработчик | Как берётся |
|---|---|---|
| `POST /{cid}/add_rewards` (бои, боевой пропуск) | `def` | блокирующий вызов до любой работы с БД, только если `xp > 0` |
| `POST /admin/titles/grant` | `def` | блокирующий вызов до любой работы с БД — поэтому проверка «титул уже есть» и вставка остаются в одной транзакции |
| `PUT /admin/{cid}` (смена уровня) | `async def` | через `_evaluate_titles_with_book` — только если титул открылся |
| `GET /{cid}/full_profile` | `async def` | **дважды лениво**: сама автовыдача запускается лишь при реальном повышении уровня, и уже внутри неё множитель берётся только при открытии титула. Обычное чтение профиля запросов не делает |
| `POST /internal/evaluate-titles` (зовут inventory и char-attrs) | `async def` | через `_evaluate_titles_with_book` — на обычном надевании предмета обращений нет |
| `GET /{cid}/titles` | `async def` | то же самое — горячее чтение платит за запрос только в тот редкий раз, когда титул открылся |

**Осознанный размен.** На ленивых ветках множитель запрашивается уже при открытой транзакции (выше были SELECT-ы), то есть соединение БД удерживается на время запроса — до 5 с. Ветки редкие (открытие титула, сдача квеста с наградой опытом), и это дешевле безусловного запроса на каждом чтении. **Чинить это откатом сессии нельзя** — откат протухает загруженные объекты и ломает вызывающего (см. запись про battle-pass в `docs/ISSUES.md`); если удержание понадобится убрать, начисление выносят за пределы транзакции.

Функции начисления (`add_rewards_to_character`, `grant_title`, `evaluate_titles`, `_grant_title_xp`) в сеть не ходят никогда — это зафиксировано тестом по AST в `tests/test_xp_multiplier_call_shape.py`. `_grant_title_xp` принимает `xp_multiplier` обязательным keyword-аргументом, чтобы его нельзя было молча забыть. Вставка титула вдобавок защищена от гонки: `flush()` обёрнут в `try/except IntegrityError` (первичный ключ `character_titles`), при проигранной гонке идёт откат и ответ `(True, "already_has")` — то же, что при обычном повторе, а не 500. Опыт за титул в этом случае не начисляется: `flush` падает до награды.

## Коммуникация

### HTTP (исходящие)
- `inventory-service:8004` - POST `/inventory/` (создание инвентаря + слотов экипировки, стартовый набор — `crud.send_inventory_request`). **FEAT-167 задача #18: роут стал internal-only**, вызов обязан слать `X-Internal-Token` (хелпер `crud._internal_token_headers()`, читает `auth_http.INTERNAL_SERVICE_TOKEN` в момент вызова). Вызов log-and-continue, поэтому потеря заголовка была бы молчаливой — покрыт `tests/test_internal_headers.py`
- `skills-service:8003` - POST `/skills/internal/assign_multiple` (назначение навыков; FEAT-169: публичный `/skills/assign_multiple` ушёл под `require_permission("skills:create")` для админского редактора НПС, сервисный вызов — на internal-двойника с заголовком `X-Internal-Token`), POST `/skills/` (legacy «Basic Attack», тоже закрыт internal-токеном)
- `character-attributes-service:8002` - POST `/attributes/` (создание строки атрибутов: `crud.send_attributes_request` — одобрение заявки, **хард-фейл с откатом персонажа**, и создание NPC из админки; `crud._sync_send_attributes_request` — спавн моба), GET `/{id}`, GET `/{id}/passive_experience`. **FEAT-167 задача #17: `POST /attributes/` стал internal-only** — оба вызова шлют `X-Internal-Token` через `crud._internal_token_headers()`. **FEAT-171 (Pass A):** чтения из `full_profile` переехали на internal-двойники — GET `/attributes/internal/{id}` (A1i) и GET `/attributes/internal/{id}/passive_experience` (A4i), оба с `X-Internal-Token`
- `user-service:8000` - POST `/users/user_characters/`, PUT `/users/{id}/update_character`, GET `/users/{id}`, GET `/users/me` (auth во всех защищённых эндпоинтах)
- `locations-service:8006` — **новая зависимость, появилась в FEAT-154** (`LOCATIONS_SERVICE_URL`, дефолт `http://locations-service:8006`). Клиент — `app/locations_client.py`, таймаут 5 с, три чтения:
  - GET `/locations/starting-points/{id}` — проверка выбранной стартовой точки при подаче и при одобрении заявки
  - GET `/locations/starting-points` — курируемый список, первый элемент = точка по умолчанию
  - GET `/locations/game-time` — текущий игровой год из блока `computed.year` для проверки стажа

  **Все три graceful.** Клиент возвращает `None`, если сервис не смог ответить, и вызывающая сторона пропускает проверку. Недоступность locations-service никогда не блокирует подачу и не проваливает одобрение. Календарь здесь **не реализуется повторно** — игровой год всегда читается в рантайме, никаких захардкоженных годов в коде, валидации, фикстурах и сидах.

### RabbitMQ
Консьюмер (`rabbitmq_consumer.py`) закомментирован и в `main.py` не импортируется — входящих сообщений сервис не читает. **Продюсер (`producer.py`) работает**: одобрение и отклонение заявки (и получение титула) публикуют уведомление игроку в очередь `general_notifications` с `category: "progress"`; одобрение дополнительно дублирует полезную нагрузку по инвентарю/навыкам/атрибутам (см. предупреждение в workflow выше).

## FEAT-125: mob_template_skills теперь по skill_id

- Таблица `mob_template_skills` после Alembic `016_repoint_mob_template_skills` хранит `skill_id` (FK → `skills.id`, ON DELETE CASCADE) вместо `skill_rank_id`. UNIQUE переимённован на `(mob_template_id, skill_id)`.
- Бэкфилл колонки делает skills-service `003_perk_system`, character-service 016 только дропает старое и промоутит NOT NULL (+ 30-секундный short-poll, чтобы выдержать Compose race).
- `crud.send_skills_presets_request` теперь шлёт в skills-service `{character_id, skills:[{skill_id}]}` без `rank_number`.
- FEAT-169: `send_skills_presets_request` и `send_skills_request` шлют `X-Internal-Token` через `crud._internal_token_headers()`; оба вызывающих проглатывают ошибку, поэтому потеря заголовка была бы молчаливой (персонаж создался бы без навыков).
- `schemas.MobSkillResponse.skill_id`, `MobSkillsUpdate.skill_ids`, `BestiarySkillEntry.skill_id`.

## Известные проблемы

1. **RabbitMQ-консьюмер отключён** - код закомментирован, aio_pika остаётся в зависимостях. Продюсер при этом используется
2. **Опыт не сохраняется** - `check_and_update_level()` уменьшает passive_experience локально, но не сохраняет в attributes-service
3. **Неиспользуемый код** - `send_equipment_slots_request()` ссылается на несуществующий `EQUIPMENT_SERVICE_URL` (в `config.py` его нет; тест маскирует это, подставляя атрибут в `settings`)
4. **`presets.py` — мёртвый код.** Реальный источник статов подрасы — колонка `subraces.stat_preset`
5. **Аутентификация частичная.** Заявки, админские и модераторские эндпоинты защищены (`get_current_user_via_http`, `require_permission`). Все публично маршрутизируемые незащищённые write-эндпоинты закрыты в FEAT-162: `update_location`, `set_travel_cooldown`, `deduct_points` и `POST .../logs` перенесены под `/characters/internal/` (nginx 403) + `verify_internal_token`. FEAT-169 закрыл последнюю дыру этого класса: `POST /characters/{cid}/add_rewards` теперь тоже требует `Depends(verify_internal_token)` (пустой `INTERNAL_SERVICE_TOKEN` → 503, чужой/отсутствующий заголовок → 401), nginx остался вторым слоем. Вызывающие — battle-service, battle-pass-service, dungeon-service — шлют `X-Internal-Token`
6. **`character_requests.name` — `String(20)`, `characters.name` — `String(255)`.** Заявка на присвоение NPC с длинным именем не проходит round-trip
7. **Одобрение неатомарно** - 13 шагов по пяти сервисам под одним коммитом; дублирующие публикации в RabbitMQ оставляют узкую гонку двойной выдачи

Полный список с приоритетами — в `docs/ISSUES.md`.


## Блокировка активности (FEAT-175)

Источник истины — две nullable-колонки `characters` (миграция `023_activity_lock`):
`dungeon_session_id` (персонаж в забеге) и `unconscious_until` (наивный UTC; прошедшее время = свободен,
фоновая очистка не нужна). Логика — `app/activity_lock.py`.

| Метод | Путь | Описание |
|---|---|---|
| GET | `/characters/internal/{id}/activity-lock` | `{"locked", "reason": "dungeon"|"unconscious"|null, "until", "dungeon_session_id"}` |
| POST | `/characters/internal/activity-lock/dungeon` `{character_ids, session_id}` | Блокировка всех или никого (`SELECT … FOR UPDATE` по возрастанию id); 409 `{character_id, message, activity_lock}` если кто-то без сознания или в другом забеге; повтор для той же сессии — no-op |
| POST | `/characters/internal/activity-lock/dungeon/clear` `{character_ids, session_id}` | Снимает только блокировку этой сессии |
| POST | `/characters/internal/activity-lock/knockout` `{character_ids, seconds, session_id?, return_location_id?}` | Вайп: «без сознания» до now+seconds, снимает блокировку подземелья, возвращает на локацию |
| POST | `/characters/internal/despawn-dungeon-mobs` `{character_ids}` | Удаляет `active_mobs` с `spawn_type='dungeon'` (строки персонажей-мобов остаются скрытыми) |

`GET /characters/{id}/profile` и оба `short_info` отдают объект `activity_lock` (его же получает
`/users/me` → `character.activity_lock`). Мастер Телепорта отказывает заблокированному персонажу (409).

Мобы подземелий: `spawn-dungeon-mobs` принимает `stat_multiplier` (= `dungeons.mob_multiplier`,
масштабирует числовые базовые характеристики шаблона, положительные не опускаются ниже 1);
`spawn_type='dungeon'` не попадают в `get_mobs_at_location`, не получают `respawn_at` и не
возрождаются. Миграция 023 удалила утёкших мобов подземелий (кроме тех, что в бою).

Формулировки отказа одинаковы во всех сервисах (`activity_lock.lock_message`):
«Персонаж находится в подземелье» / «Персонаж без сознания до HH:MM МСК» (для второго
участника — «Цель …», «Целевой персонаж …», «Другой участник обмена …»). Код ответа — **409**.
Колонки `characters.dungeon_session_id` / `characters.unconscious_until` пишет только
character-service; остальные сервисы читают их из общей БД (как блокировку боя). В тестах
сервисов с таблицами-зеркалами `characters` conftest по умолчанию подменяет чтение на
«не заблокирован»; настоящий запрос проверяют тесты с маркером `real_activity_lock`.

## Сон в доме (FEAT-180, миграция 024)

`characters.asleep_since` (DATETIME, naive UTC), `sleep_regen_factor` (FLOAT), `sleep_house_room_id`
(BIGINT, `house_rooms.id` без FK). Пишет и очищает locations-service (сон в спальне дома / пробуждение).
Пока `asleep_since` задан, персонаж заблокирован: `activity_lock` отдаёт причину `asleep` («Персонаж спит —
сначала нужно проснуться»); без сознания и подземелье важнее сна. Колонку читают копии `activity_lock` в
battle-, inventory- и locations-service.

## Чтение в библиотеке и свиток возвращения (FEAT-180 этап 6б, миграция 025)

`characters.reading_since` (DATETIME, naive UTC) и `reading_house_room_id` (BIGINT, `house_rooms.id` без FK) —
пишет и очищает locations-service (библиотека дома). Пока `reading_since` задан, `activity_lock` отдаёт
причину `reading` («Персонаж читает — сначала нужно закончить чтение»); сон, без сознания и подземелье
важнее. Колонку читают копии `activity_lock` в battle-, inventory- и locations-service.

`POST /characters/internal/{character_id}/home-teleport {location_id}` (X-Internal-Token; nginx закрывает
`/characters/internal/`) — inventory-service, когда прочитан свиток возвращения домой. Те же шаги, что у
`admin/{id}/move` (общий `_prepare_move`): бой / подземелье → 409, отмена добычи (`reason=home_teleport`),
гашение намерений в покидаемой локации (502 при сбое — никто не перенесён), затем `crud.apply_admin_move` с
`event_type="home_teleport"` (сброс кулдауна перехода, запись в журнал без полей админа). Дополнительно: та же
локация → 400 «Персонаж уже в этой локации», иная блокировка активности (сон, чтение) → 409, нет локации → 404.
Ответ `{character_id, from_location_id, location_id, location_name, gathering_cancelled}`. Тесты:
`tests/test_home_teleport_internal.py`.

## Присутствие в доме (FEAT-180 этап 7, миграция 026)

`characters.house_room_id` (BIGINT NULL, индекс `ix_characters_house_room_id`, без FK) — комната дома
(locations-service `house_rooms.id`), где стоит персонаж. Пишет locations-service (вход/переход/выход);
character-service **обнуляет при каждой смене локации**: `PUT /characters/internal/{id}/update_location` (если
локация действительно другая — обычный переход и быстрое перемещение через locations-service), перенос Мастера
телепортов (`crud.execute_teleport`), админский перенос и свиток (`crud.apply_admin_move`), нокаут подземелья с
возвратом в другую локацию (`/internal/activity-lock/knockout`). Свиток возвращения:
`POST /characters/internal/{id}/home-teleport {location_id, house_room_id?}` — `house_room_id` (круг возвращения,
который выбрал inventory-service) ставится в той же транзакции, что и перенос; без поля персонаж просто в локации.
Комната считается только пока её дом стоит в текущей локации, поэтому пропущенная очистка безопасна.

`GET /characters/by_location` — у игрока `in_house: {house_id, house_name} | null` (персонаж внутри дома этой
локации; комната не раскрывается; таблицы домов читаются сырым SQL, без них — null). Откат миграции снимает индекс
и колонку. Тесты: `tests/test_house_presence.py`.
- `GET /characters/internal/{id}/short_info` отдаёт `current_house {house_id, house_name, room_id, room_name}` (или null) — комната дома, где стоит персонаж (правило то же: дом в его локации). Публичный `short_info` этого поля не содержит. user-service передаёт его только в `/users/me` — для ссылки «вернуться в дом» в шапке.

## Economy ledger (FEAT-181 этап 1, миграция 027)

Двойная запись золота мира. Таблицы живут в character-service (миграция `027_world_economy`), но в них пишут
четыре сервиса — каждый в **своей** транзакции через локальный помощник над одним контрактом.

### Таблицы

- `characters.currency_balance` — теперь `BIGINT NOT NULL DEFAULT 0`; это баланс счёта `character`.
- `econ_settings` (одна строка `id=1`) — формы названия валюты (`currency_name/genitive/one/few/many/short`) и
  `country_tax_rate` (доля налога регион → страна, по умолчанию 0.1).
- `econ_accounts` (`kind`, `ref_id`, уникальная пара) — счета: `character` (баланс в `characters`, колонка `balance`
  не используется), `region_treasury` / `country_treasury` (ref = `Regions.id` / `Countries.id`), одиночки
  `world_treasury` («Казна Скитальцев»), `auction_escrow` («Ставки аукциона»), `auction_storage` («Хранилище аукциона»),
  `emission`, `adjustment`. В минус могут уходить казны и источники; персонажи, эскроу и хранилище — нет.
  Счета создаются лениво при первой проводке; `is_active=0` после удаления владельца (строка остаётся).
- `econ_operations` — заголовок бизнес-события (`op_type`, уникальный `idempotency_key`, `location_id`, `region_id`,
  `actor_user_id`, `source_service`, `comment`, `metadata` JSON). Только добавление.
- `econ_postings` — ноги «откуда → куда» (`amount > 0`, `leg_type`: `main | refund | commission | tax`). Только
  добавление; отмена — новая операция.

Инвариант мира: `Σ characters.currency_balance + Σ econ_accounts.balance (kind <> 'character') = 0`. Деньги
появляются только проводками из `emission` (genesis, админская эмиссия) и `adjustment` (админская корректировка).
Подинварианты: счёт `auction_escrow` = Σ активных ставок (`auction_listings.current_bid`, status `active`, есть
ставящий), `auction_storage` = Σ `auction_storage.gold_amount`, у каждого персонажа баланс = Σ входящих − Σ исходящих
проводок (детектор обхода помощника).

Genesis (в миграции, идемпотентно по `idempotency_key='genesis'`): одиночные счета, казна на каждый регион и страну,
счёт на каждого персонажа с ненулевым балансом (игроки **и** НПС), одна операция `genesis`: `emission → персонаж`,
`emission → auction_escrow`, `emission → auction_storage`. Казны стартуют с 0 — начальную эмиссию делает админ.

### Файлы контракта

| Файл | Что | Копии |
|------|-----|-------|
| `app/econ_core.py` | Чистый контракт: виды счетов, типы операций/ног, `AccountRef`, `Leg`, `PostingResult`, валидация, ноги налога, неттинг, порядок применения, все SQL, `plural_ru`, `format_currency`, `CurrencyForms`, исключения, кэш настроек | побайтно в inventory-, locations-, dungeon-service (CI `econ-contract-copies`) |
| `app/econ_ledger.py` | Sync-исполнитель (SQLAlchemy `Session`) + ORM-страж баланса | побайтно в inventory-service; async-канон — locations-service (копия в dungeon-service) |
| `app/tests/econ_contract_cases.py` | Общие сценарии + SQLite DDL; каждый сервис гоняет их через свой исполнитель | побайтно во всех четырёх |

Канон — character-service: правки делаются здесь и копируются дословно.

### API помощника (`econ_ledger`, async-вариант — те же имена с `await`)

```python
from econ_ledger import AccountRef, Leg, post_operation, treasury_for_location, lock_characters
# AccountRef.character(id) / region(id) / country(id) / world() / escrow() / storage() / emission() / adjustment()
# Leg(src, dst, amount, leg_type="main")          # amount: int >= 0, ноги с 0 отбрасываются

post_operation(session, *, op_type, legs, source_service, location_id=None, region_id=None,
               actor_user_id=None, comment=None, metadata=None, idempotency_key=None,
               apply_tax=True) -> PostingResult    # (operation_id | None, {character_id: new_balance})
resolve_location(session, location_id) -> (region_id | None, country_id | None)
treasury_for_location(session, location_id | None) -> AccountRef   # казна региона, иначе world_treasury
lock_characters(session, character_ids) -> {id: balance}            # SELECT … FOR UPDATE по возрастанию id
get_currency_forms(session) -> CurrencyForms                        # кэш 60 с, при ошибке — DEFAULT_FORMS
get_economy_settings(session) -> EconomySettings(forms, country_tax_rate)
invalidate_settings_cache()                                         # после PUT настроек
get_or_create_account(session, ref) -> account_id
deactivate_account(session, ref)                                    # удаление персонажа / региона / страны
allow_direct_balance_write(session)                                 # контекст: отключить страж (фикстуры, ремонт)
install_balance_guard(model_cls, attr="currency_balance", strict=True)
# econ_core: plural_ru(n, one, few, many), format_currency(n, forms, short=False), DEFAULT_FORMS,
#   EconomyError, InsufficientFunds(account, needed), DuplicateOperation(operation_id)
```

Алгоритм `post_operation`: валидация (до любого SQL) → ноги налога `регион → страна` для каждого поступления в казну
региона от `character` / `auction_escrow` / `auction_storage` (`floor(amount × country_tax_rate)`, `leg_type='tax'`) →
`session.flush()` → вставка операции (с ключом — сначала SELECT, затем INSERT в SAVEPOINT; дубликат →
`DuplicateOperation`, ничего не двигалось) → get-or-create счетов → неттинг по счёту и применение в порядке:
персонажи по возрастанию id (условное списание `… WHERE currency_balance >= :d`, иначе `InsufficientFunds`), затем
`econ_accounts` по возрастанию id (`allow_negative = 1 OR balance + :delta >= 0`) → вставка всех ног (без неттинга) →
чтение новых балансов и `expire` ORM-копий `currency_balance`. Если все ноги нулевые — ничего не пишется,
`operation_id=None`. В SQLite (тесты) SAVEPOINT не используется.

### Правила для вызывающих

- Никто не меняет `characters.currency_balance` и `econ_accounts.balance` иначе как через `post_operation`. Новый
  персонаж вставляется с 0, стартовый баланс — проводкой после `flush`.
- Порядок блокировок: свои бизнес-строки (лот, обмен, дом, квест, сессия данжа) → `characters` по возрастанию id →
  `econ_accounts` по возрастанию id. Помощник вызывается последним шагом перед `commit`; транзакция не держится
  открытой через HTTP-вызов.
- **Помощник никогда не делает commit/rollback.** Вызывающий коммитит вместе с бизнес-строками или откатывает при
  исключении (`InsufficientFunds` → понятная русская ошибка «Недостаточно {forms.genitive}»).
- Всегда передавать `location_id`, если он известен; плательщика/получателя-казну выбирать через
  `treasury_for_location()`. Локация без региона → `world_treasury`.
- Ключи идемпотентности: `<op_type>:<бизнес-id>`, например `quest_reward:cq:123`, `battle_pass_reward:claim:55`,
  `dungeon_reward:s:7:r:3`.
- Админские операции (`admin_emission`, `admin_adjust`) — с обязательным `comment`, `actor_user_id` и `apply_tax=False`.
  Только `genesis` / `admin_emission` / `admin_adjust` могут трогать счета `emission` / `adjustment`.
- `gold_transactions` заморожена: новых записей не делать (удаление таблицы — позже).

### Страж ORM

`models.py` ставит `before_flush`-слушатель (`econ_ledger.install_balance_guard(Character)`): изменение
`currency_balance` у **существующего** персонажа через ORM — обход журнала. С FEAT-181 B2
`BALANCE_GUARD_STRICT = True`: такой `flush` бросает `EconomyError`. Фикстуры тестов (и разовые скрипты починки),
которым нужно выставить баланс через ORM, оборачивают запись в `allow_direct_balance_write(session)`. Вставка новых
строк не проверяется — новые персонажи/НПС создаются с 0, деньги приходят проводкой.

В тестах SQLite `conftest.py` при каждом `create_all()` создаёт переносимые копии `Countries`/`Regions`/`Districts`/
`Locations` (DDL из `tests/econ_contract_cases.py`), чтобы выбор казны по локации работал в любом тесте.

### Писатели золота в character-service (FEAT-181 B2)

Все в `crud.py`, секция «Economy writers», `source_service = "character-service"`. В `gold_transactions` сервис больше
не пишет (функция `log_gold_transaction` удалена).

| # | Где | Операция | Проводка |
|---|-----|----------|----------|
| C1 | одобрение заявки → `post_starter_kit` | `starter_kit`, ключ `starter_kit:c:<id>` | казна стартовой локации → персонаж |
| C2 | `POST /characters/{id}/add_rewards` → `add_rewards_to_character` | `gold_op_type` | `payer="world"` → «Казна Скитальцев»; `payer="location"` → казна `location_id`, иначе текущей локации персонажа, иначе «Казна Скитальцев» |
| C3 | `POST /characters/internal/deduct-gold` | `op_type` (по умолчанию `dungeon_expense`) | персонаж → казна `location_id` / текущей локации / мира (+ налог стране) |
| C4 | телепорт (`execute_teleport`) | `teleport` | персонаж → казна локации НПС-источника (+ налог); строка персонажа уже под `FOR UPDATE` |
| C5 | `PUT /characters/admin/{id}` → `admin_set_balance` | `admin_adjust`, комментарий «Правка в карточке персонажа» | дельта под `lock_characters`: `adjustment → персонаж` или `персонаж → adjustment`, без налога |
| C6 | `POST`/`PUT /characters/admin/npcs[/{id}]` → `admin_set_balance` | `admin_adjust`, «Правка золота НПС» | как C5; НПС вставляется с 0 |
| C8 | `DELETE /characters/{id}`, `DELETE /characters/admin/npcs/{id}`, `crud.delete_character` → `post_character_deletion` | `character_deleted`, ключ `character_deleted:c:<id>` | весь баланс → казна локации (+ налог), счёт неактивен |

Изменённые внутренние контракты (обратно совместимы — новые поля необязательны, старые клиенты работают как раньше):
- `POST /characters/{id}/add_rewards`: запрос `+ gold_op_type` (`battle_reward` по умолчанию | `battle_pass_reward` |
  `dungeon_reward`), `+ location_id`, `+ payer` (`location` по умолчанию | `world`), `+ idempotency_key` (1–128). Ответ
  `+ duplicate`. Повтор ключа → 200 `duplicate=true`, **ни опыта, ни золота** (`new_xp = null`). Ключ записывается
  только вместе с операцией, т.е. защищает награды с `gold > 0`; награда только опытом идемпотентной не является.
- `POST /characters/internal/deduct-gold`: запрос `+ location_id`, `+ op_type` (только траты игрока: `dungeon_expense`,
  `teleport`, `npc_shop_buy`, `house_purchase`, `house_build`, `house_tax`), `+ idempotency_key`. Ответ `+ duplicate`.
  Нехватка → 400 «Недостаточно {genitive} (имеется N …, нужно M …)» с формами валюты из `econ_settings`.
- `PUT /characters/admin/{id}`: форма та же; **изменённый** `currency_balance` дополнительно требует `economy:adjust`
  (иначе 403 «Недостаточно прав для изменения баланса»), неизменённый игнорируется (карточка шлёт его всегда).
  Отрицательный → 400 «Баланс не может быть отрицательным». То же для создания/правки НПС с ненулевым/изменённым золотом.
- Сообщение телепорта о нехватке денег — «Недостаточно {genitive}» из настроек валюты.

### API экономики (FEAT-181 B3)

Роутер `app/economy_api.py` (логика в `app/economy_crud.py`, схемы — секция FEAT-181 в конце `schemas.py`). Подключён
в `main.py` **перед** основным роутером, поэтому статические пути не перехватываются маршрутами `/characters/{character_id}/…`.
Nginx: покрыто существующим `location /characters/` (dev и prod), правок не нужно. Эндпоинты — обычные `def`
(синхронная сессия в threadpool); собственный `economy_api.get_db` читает `database.SessionLocal` в момент вызова
(в тестах переопределяется через `app.dependency_overrides[economy_api.get_db]`).

| Метод и путь | Право | Что делает |
|---|---|---|
| `GET /characters/economy/currency` | публичный | формы названия валюты (кеш 60 с, при сбое — значения по умолчанию) |
| `GET /characters/admin/economy/summary` | `economy:read` | итоги (выпущено/на руках/игроки/НПС/эскроу/хранилище/казны), инвариант (сумма мира = 0, эскроу и хранилище = суммам аукциона, до 50 персонажей с расхождением баланса и журнала), дерево страна → регионы, системные счета, ставка налога. Перед расчётом создаёт недостающие счета казн существующих регионов/стран, чтобы на любую казну можно было сделать эмиссию. Регионы без известной страны — в группе «Без страны» (`account_id = null`) |
| `GET /characters/admin/economy/accounts?kind=&q=&page=&page_size=` | `economy:read` | счета: несимвольные из `econ_accounts` + все персонажи (баланс из `characters`); `q` — поиск по имени (LIKE с экранированием, ≤ 100 символов); персонажам без счёта на текущей странице счёт создаётся; `page_size ≤ 100` |
| `GET /characters/admin/economy/operations?account_id=&character_id=&op_type=&region_id=&date_from=&date_to=&page=&page_size=` | `economy:read` | журнал, `id DESC`, у каждой операции её проводки с именами счетов; `date_to` включительно |
| `POST /characters/admin/economy/emission` | `economy:emit` | `{account_id, amount 1…10^12, comment 3–500}` → `admin_emission` из `emission` в казну региона/страны/Казну Скитальцев, без налога |
| `POST /characters/admin/economy/adjust` | `economy:adjust` | `{account_id, delta ≠ 0, модуль ≤ 10^12, comment}` → `admin_adjust` через счёт `adjustment`; запрещены `emission`, `adjustment`, `auction_escrow`, `auction_storage`; уход в минус неотрицательного счёта → 400 «Недостаточно средств на счёте» |
| `GET` / `PUT /characters/admin/economy/settings` | `economy:read` / `economy:settings` | формы валюты (1–50 символов, сокращение 1–20, обрезка пробелов, `<` `>` и управляющие символы запрещены → 422) и `country_tax_rate` 0…0.5; PUT сбрасывает кеш настроек этого процесса, остальные сервисы подхватят за 60 с |

Ответы эмиссии/корректировки: `{operation_id, account_id, balance}`. Ошибки — по-русски: 404 «Счёт не найден»,
400 «Счёт закрыт» (неактивный счёт), «Эмиссия возможна только в казну…», «Этот счёт нельзя корректировать»,
«Неизвестный тип счёта/операции»; SQL и трассировки наружу не уходят. Каждое действие админа — операция журнала с
`actor_user_id` и обязательным комментарием.

### Контракт этапа 2: кошелёк жителей и пересчёт региона (FEAT-182 B1)

- Новый вид счёта `population_purse` («Кошелёк жителей», `AccountRef.purse(region_id)`, ref = `Regions.id`, имя-снимок
  из `Regions`). **Не уходит в минус** (не в `NEGATIVE_ALLOWED_KINDS`). Входит в `TAX_SOURCE_KINDS`: поступление
  `кошелёк → казна региона` облагается налогом стране, как платёж игрока. Закрытие кошелька в казну страны
  (`treasury_closed`) налогом не облагается.
- Новый тип операции `region_tick` («Пересчёт региона»): ноги кошелёк ↔ казна региона ↔ казна страны за один шаг
  симуляции; источники `emission`/`adjustment` трогать не может. Ключ `region_tick:<run_id>:r:<region_id>`.
- `econ_core.GOODS_GROUPS` — 12 кодов групп товаров; `auto_item_group(item_type, resource_subcategory, is_food,
  item_rarity) -> (group | None, off_market)` — правило автогруппы (FEAT-182 3.6); `OFF_MARKET_ITEM_TYPES`
  (`scroll`, `recipe`), `OFF_MARKET_RARITIES` (легендарная и выше). Сценарии — `ITEM_GROUP_CASES` в
  `tests/econ_contract_cases.py`.
- Админ-API: эмиссия разрешена и в кошелёк жителей (операция помечается `region_id`); корректировка кошелька тоже
  разрешена (минус → 400). Сводка: `totals.population_purses` (уже входит в `held`, инвариант не меняется), у узла
  региона в дереве — `purse_account_id`, `purse_balance` (`null`, если кошелька нет); кошельки не попадают в
  `system_accounts`. Счета и журнал показывают кошелёк с текущим названием региона. Журнал:
  `GET …/operations?exclude_op_type=<op_type>` (из `OP_TYPES`, иначе 400) — скрыть операции одного типа
  (фронтенд скрывает `region_tick` по умолчанию).

### Контракт этапа 3: торговцы НПС (FEAT-183 B1)

Всё в `econ_core` (4 побайтных копии); это **единственный** способ, которым locations-service (лавка игрока) и
character-service (тик, вкладка «Торговцы») считают цену торговца. Полное описание торговцев и порядок блокировок —
в разделе «NPC merchants (FEAT-183)» (задача B6).

- Тип операции `merchant_trade` («Торговля с жителями», ключ `merchant_trade:<run>:r:<region>`, источники трогать
  нельзя). Тип ноги `trade_tax` («Налог с выручки», `NPC → казна региона`) — передаётся вызывающим (есть и в
  `LEG_TYPES`, и в `CALLER_LEG_TYPES`); как поступление `character → region` сам облагается 10 % в казну страны.
  Сгенерированная нога `tax` по-прежнему не передаётся.
- Константы: `MAX_CHARISMA_DISCOUNT = 0.5`, `DEFAULT_MERCHANT_BID_SHARE = 0.5`, `DEFAULT_RESTOCK_TARGET = 10`,
  `PRICE_LEVEL_LOW_MULT = 0.85` / `PRICE_LEVEL_HIGH_MULT = 1.2`, `SHOP_ORIGIN_ADMIN|PLAYER`,
  `MERCHANT_LEGACY_REASONS` = `not_npc, dead, no_location, dungeon, no_region, not_simulated`.
- Чистые функции (Decimal, игрок платит `ceil`, получает `floor`):
  `effective_item_group(item_type, subcategory, is_food, rarity, override_group=None, override_off_market=None)`
  (переопределение поверх автоправила, **нет группы ⇒ вне рынка**), `item_base_price(items_price, group_base)`,
  `market_mult(living, group, off_market, mults)`, `price_level(mult)`, `market_ask(base_ask, mult)`,
  `market_bid(base_bid, mult, ask)` (≤ `floor(ask × 0.5)` — перепродажа тому же торговцу не выгодна даже при
  максимальной харизме; 0 = «не покупает»), `wholesale_price(base_ask, mult, share)`, `charisma_discount_pct(cha)`,
  `discounted_ask(ask, pct)`, `units_per_item(base, group_base)`, `trade_tax(amount, rate)`, `default_bid(base, share)`,
  `merchant_bid_share(params_json)`, `merchant_status(npc_row, region_row) -> (living, reason)`.
- SQL: `SQL_NPC_PLACE` → `merchant_status`; `SQL_RESOLVE_LOCATION` → `SQL_REGION_ECON` (заголовок региона:
  шаблон, население, налог); `SQL_REGION_MARKET` + `region_goods_from_rows` (`{group: price_mult}`, `{group: base}`);
  `sql_item_market(ph)` + `item_market_from_row` → `ItemMarket(item_id, name, image, price, group, off_market)`;
  `SQL_SIM_PARAMS`; `sql_lock_shop_rows(ph, for_update, by="npc_id"|"id")`, `sql_shop_row_by_item(for_update)`
  (колонки `SHOP_ROW_COLUMNS`), `SQL_SHOP_STOCK_TAKE` (условное списание, `rowcount 0` = не хватает; `NULL` не
  списывается), `SQL_SHOP_STOCK_ADD`, `SQL_SHOP_STOCK_SET`.
- `GET …/item-groups` считает и `auto_*`, и итоговые поля через `effective_item_group`: предмет без группы теперь
  `off_market = true` (раньше `false`).
- Сценарии в `tests/econ_contract_cases.py`: ноги торговца в `CASES` (покупка с `trade_tax`, нехватка кассы НПС,
  разворот покупки, запасной возврат из казны, `merchant_trade` с идемпотентностью), `expected_leg_counts`;
  `PRICING_CASES`, `EFFECTIVE_GROUP_CASES`, `MERCHANT_STATUS_CASES`, `BID_CAP_GRID`; отдельный SQLite-мир торговцев
  (`MERCHANT_SQLITE_DDL`, `MERCHANT_QUERY_CASES`, `MERCHANT_STATUS_SQL_CASES`, `MERCHANT_STOCK_STEPS`) — все
  четыре `tests/test_econ_contract.py` их гоняют.

## Economy simulation (FEAT-182)

### Пересчёт регионов: тик (`app/econ_tick.py`) и планировщик (`app/econ_scheduler.py`) — B5

Один прогон (`econ_tick_runs`) = один шаг симуляции всех участвующих регионов (`econ_regions.template_code IS NOT
NULL`, `population > 0`, строка `Regions` существует). Регион без шаблона не участвует. Математика — чистый модуль
`econ_sim.py`; тик только читает строки, вызывает `simulate_region` и проводит деньги.

- **Слот:** `slot = floor(unix_time / 21600)` (UTC 00/06/12/18). Авто-прогон делает `INSERT econ_tick_runs(slot)`;
  `UNIQUE(slot)` → второй вызов в том же слоте (другой процесс, перезапуск `--reload`) — no-op (`run_tick` вернёт
  `None`). **Пропущенные слоты не догоняются**: берётся только текущий.
- **Доигрывание:** прогон в статусе `running` с `heartbeat_at` старше 10 минут подхватывается следующим авто-вызовом
  того же слота (условный `UPDATE … WHERE heartbeat_at < stale` — ровно один процесс). Уже сделанные регионы
  (`econ_regions.last_run_id = run.id`) пропускаются. Зависшие ручные прогоны и прогоны прошлых слотов закрываются
  как `partial`/`failed` с ошибкой «прерван…».
- **План грантов:** при захвате в `grant_plan` пишется `{region_id: grant}` для **всех** участвующих регионов (0 тоже —
  это и список регионов прогона): 25 % (`country_grant_share`) положительного баланса казны страны делится между её
  регионами пропорционально населению (`econ_sim.country_grants`). При доигрывании используется тот же план.
- **Регион = одна транзакция:** `econ_regions` FOR UPDATE → `econ_region_goods` FOR UPDATE → балансы кошелька/казны
  (чтение без блокировки) → `simulate_region` → UPDATE строк → `post_operation(op_type='region_tick')` с ногами
  `кошелёк → казна` (налог; +10 % `казна → страна` добавляет реестр), `страна → казна` (грант),
  `казна → кошелёк` (жалованье); `idempotency_key = region_tick:<run_id>:r:<region_id>`, `region_id`, metadata
  `{run_id, tax, grant, wages, income, hunger}` → строка `econ_region_history` → COMMIT. Порядок блокировок:
  бизнес-строки → `econ_accounts` по возрастанию id (внутри `post_operation`); с FEAT-183 между ними — строки лавок
  и `characters` торговцев региона (см. «NPC merchants (FEAT-183)»). Все ноги
  нулевые → операции нет (регион всё равно посчитан). `DuplicateOperation` = регион уже проведён параллельным
  исполнителем → считается сделанным. Любая другая ошибка → откат региона, `regions_failed += 1`, лог с id региона и
  классом ошибки, остальные регионы идут дальше; итог `done` / `partial` / `failed`, `error` = список регионов.
- **Застревание:** пустой кошелёк + нет гранта + нет излишка казны → нет налога и жалованья, жители не покупают —
  тик пишет WARNING «region … is stuck».
- **Уборка:** перед шагом удаляются `econ_regions` (+ товары) регионов, которых больше нет в `Regions`; после —
  история старше `history_retention_days` (60) и прогоны старше 500 последних.
- **Ручной пересчёт** («Пересчитать сейчас», B6): настоящий дополнительный шаг, `slot = NULL`, `trigger_kind =
  'manual'`, `actor_user_id`; расписание не сдвигает. Захват сериализуется `SELECT … FOR UPDATE` строки
  `econ_sim_settings`; если жив любой прогон (heartbeat свежее 10 минут) — `RunInProgress` (→ 409).

**Публичные функции `econ_tick`:**

| Функция | Назначение |
|---|---|
| `run_tick(session_factory=None, *, trigger='auto'\|'manual', actor_user_id=None, now=None, clock=None) -> RunSummary \| None` | прогон; `None` — авто-слот уже сделан/занят живым процессом; `now` фиксирует часы (тесты) |
| `run_manual(actor_user_id, session_factory=None) -> RunSummary` | ручной шаг; бросает `RunInProgress(run_id)` |
| `RunSummary.to_dict()` | `{run_id, trigger, slot, status, resumed, regions_total, regions_done, regions_failed, operations_posted, failed_region_ids, merchants_processed, merchant_items_sold, merchant_items_restocked, merchant_ops_posted, merchant_failures, merchant_failed_region_ids, shop_rows_purged, started_at, finished_at}` (поля торговцев — FEAT-183) |
| `slot_of(now=None)`, `slot_start(slot)` | номер слота / его начало (UTC) — для «следующий пересчёт в …» |
| `load_params(db)`, `load_groups(db)`, `is_tick_enabled(db)` | параметры `econ_sim_settings`, группы с цепочками, DB-рубильник |
| `region_state(row)`, `good_state(row)`, `account_balance(db, ref)` | строки ORM → датаклассы `econ_sim`, баланс счёта (0, если счёта нет) |
| `participating_regions(db)`, `build_grant_plan(db, params)`, `purge_orphans(db)` | список участников, план грантов, уборка (без коммита) |

Сессии `run_tick` открывает сам из `session_factory` (по умолчанию `database.SessionLocal`) и коммитит их сам;
сессию запроса ему передавать не нужно.

**Планировщик:** `start_scheduler()` вызывается из `@app.on_event("startup")` в `main.py`. Поток-демон стартует,
только если env `ECON_TICK_ENABLED` ∈ `1/true/yes/on` (по умолчанию выключено; в обоих compose-файлах `1`) и процесс
не pytest; один поток на процесс (модульный guard). Первая проверка через 30 с, затем каждые
`ECON_TICK_POLL_SECONDS` (по умолчанию 60, минимум 5). Каждая итерация читает `econ_sim_settings.tick_enabled`
(выключено → ничего) и вызывает `run_tick(trigger='auto')`; исключения ловятся и логируются, поток не умирает.
Ручной пересчёт работает независимо от обоих рубильников. `stop_scheduler()` / `is_running()` — для тестов.

### API живых регионов (`app/economy_api.py` + `app/economy_sim_crud.py`) — B6

Контракт — раздел 3.7 файла `features/FEAT-182-economy-living-regions.md`. Все пути под nginx `location /characters/`.
Права: GET — `economy:read`, запись — `economy:settings`, «Заполнить» — `economy:settings` **и** `economy:emit`
(`require_all_permissions`). Ошибки валидации — 422 с русским `msg`, бизнес-ошибки — 400/404 с русским `detail`.
Текстовые поля (названия, описание, слово поселения) обрезаются, `<`, `>` и управляющие символы отклоняются.

| Метод и путь | Что делает |
|---|---|
| `GET /characters/economy/regions/{id}/card` | **публичный**, без токена: `econ_sim.region_card` + `region_id, participating, updated_at` (= `last_tick_at`). Неизвестный регион / без шаблона / население 0 → `{region_id, participating: false}`. Чисел денег и запасов нет |
| `GET /characters/admin/economy/regions` | `{items}` — все `Regions` (LEFT JOIN `econ_regions`), кошелёк/казна из `econ_accounts`, `simulated` |
| `GET …/regions/{id}` | элемент + `goods` (12 строк в порядке групп); 404 «Регион не найден» |
| `PUT …/regions/{id}` | создаёт/обновляет строку; новая строка (или без товаров) с шаблоном получает товары шаблона, запас = норма; смена шаблона товары **не** перезаписывает; `goods` — частичный список (stock необязателен); норма пересчитывается |
| `POST …/regions/{id}/apply-template` | `{reset_stocks=true}` — товары и налог из шаблона, население сохраняется; запас = норма, цена ×1 при `reset_stocks`; 400, если шаблона нет |
| `POST …/regions/fill` | см. ниже |
| `GET …/regions/{id}/history?limit=1..200 (40)` | `{items}` новые сверху, `goods = {code: {stock, price_mult, produced, consumed}}` |
| `GET …/goods-groups`, `PUT …/goods-groups/{code}` | `{items}` / одна группа; цепочка: нельзя сам себе, циклы → 400 «Цепочка производства замыкается в круг» |
| `GET …/templates`, `PUT …/templates/{code}` | `{items}` / один шаблон с `goods`; переданные строки товаров upsert-ятся |
| `GET …/item-groups` | `q` (LIKE с экранированием `!`), `item_type` (enum items), `group` (код или `none`), `source` (`auto`/`manual`), `off_market`, `page`, `page_size ≤ 100`. `q`/`item_type` фильтруются в SQL, остальное — после автоправила в Python (каталог предметов маленький); группа и «вне рынка» — `econ_core.effective_item_group` (нет группы ⇒ вне рынка, FEAT-183). `in_quests` — есть `quest_objectives` `collect`/`deliver` с `target_id = item.id` |
| `PUT …/item-groups` | `{item_ids ≤ 500, group_code?, off_market?, reset?}`: отсутствующее поле не меняется, `null` — назад к авто, `reset` удаляет переопределения (нельзя вместе с полями); строка, где оба поля `null`, удаляется; несуществующие id пропускаются; ответ `{updated}` |
| `GET …/sim`, `PUT …/sim` | состояние (`tick_enabled`, `env_enabled`, `params`, `current_slot_start`, `next_slot_at`, `running`, `runs` — 20 последних); PUT сливает переданные параметры с сохранёнными, границы — `schemas.ECON_SIM_PARAM_BOUNDS`, плюс `price_min < price_max`, `prod_price_min < prod_price_max` |
| `POST …/sim/run` | «Пересчитать сейчас»: `econ_tick.run_manual`, ждёт окончания; ответ `RunSummary` с `id`/`trigger_kind`; 409 «Пересчёт уже идёт, попробуйте позже» |

**«Заполнить регионы по шаблонам»** (`fill_regions`): тело `{region_ids?, population_from_template=false,
reset_stocks=true, fund_purses=true, treasury_to_reserve=true, comment 3..500}`. Без `region_ids` — все регионы с
шаблоном; явно указанный регион без шаблона → 400. Первым запросом блокируются строки `econ_regions` (FOR UPDATE), затем
для каждого региона: население из шаблона (только если 0), товары шаблона, запас = норма; регион с населением 0
пропускается (`skipped_no_population`). Деньги — **доливка** через эмиссию: кошелёк до `econ_sim.starting_purse`,
казна (`treasury_to_reserve`) до резерва жалованья (`treasury_target` пробного шага `simulate_region` от заполненного
состояния; он же пишется в `econ_regions.treasury_target`). Без доливки казны жалованье равно 0, пока казна не
наберёт 7-дневный резерв налогами (~неделя), и кошельки после заполнения только тают. Сумма = `max(0, цель − баланс)`,
повторный клик эмитирует 0. **Одна операция `admin_emission` на регион** (с `region_id` — журнал фильтруется по
региону), ключ `econ_fill:r:<region>:p<id последней проводки кошелька>:t<…казны>` — два одновременных одинаковых
запроса получают один ключ, второй отбрасывается (`DuplicateOperation` → регион пропущен). Ответ:
`{regions, operation_id (последняя), operation_ids, emitted, emitted_purses, emitted_treasuries, skipped_no_population}`.

## NPC merchants (FEAT-183)

Торговец НПС — персонаж с `is_npc = 1` и активными строками `npc_shop_items` (таблица locations-service, миграция
`053_npc_shop_market`). Касса = `characters.currency_balance` НПС (счёт вида `character`, в минус уйти не может —
условное списание реестра). Отдельных таблиц торговцев в character-service нет; все настройки — 9 ключей
`merchant_*` в `econ_sim_settings.params` (`econ_sim.SimParams`, границы `schemas.ECON_SIM_PARAM_BOUNDS`).

### Контракт чтения этапа 3 (обязателен для обоих сервисов)

Цена торговца считается **только** через `econ_core` (раздел «Контракт этапа 3» выше) — locations-service (лавка
игрока, `crud.merchant_market`) и character-service (тик, вкладка «Торговцы») используют одни и те же SQL и функции:

1. **Живой или «обычный» (legacy):** `SQL_NPC_PLACE(:id)` → `SQL_RESOLVE_LOCATION(current_location_id)` → регион →
   `SQL_REGION_ECON(:region_id)` → `merchant_status(npc_row, region_row)`. Живой = НПС жив, есть локация, она не
   `dungeon`, относится к региону, регион симулируется (`template_code IS NOT NULL AND population > 0`). Иначе
   причина: `not_npc | dead | no_location | dungeon | no_region | not_simulated`. Статус считается на каждом запросе
   (переезд НПС / выключение региона действуют сразу).
2. **Группа предмета:** `sql_item_market(ids)` + `item_market_from_row` → `effective_item_group` (переопределение
   `econ_item_groups` поверх автоправила; **нет группы ⇒ вне рынка**).
3. **Множитель:** `SQL_REGION_MARKET(:region_id)` + `region_goods_from_rows` → `market_mult(living, group, off_market,
   mults)` — `price_mult` группы региона для живого торговца и рыночного предмета, иначе 1.
4. **Цены:** `ask = market_ask(buy_price, mult)`; игрок платит `discounted_ask(ask, charisma_discount_pct(cha))`;
   `bid = market_bid(sell_price или default_bid(item_base_price(items.price, group_base), merchant_bid_share), mult,
   ask)` (≤ `floor(ask × 0.5)`, 0 = не покупает); опт (докупка из региона) `wholesale_price(buy_price, mult,
   merchant_wholesale_share)`; единицы региона на предмет `units_per_item(buy_price, group_base)`; налог с выручки
   `trade_tax(amount, econ_regions.tax_rate)`.
5. **Склад:** `stock NULL` = безлимит **только** у legacy; у живого `NULL` = 0. Строки `origin='player'` — скуплено у
   игроков, только перепродаются (`restock_target = 0`).

### Единый порядок блокировок (3.5; заменяет FEAT-181/182 для этих потоков)

`econ_regions → econ_region_goods → npc_shop_items (по возрастанию id) → characters (по возрастанию id) →
econ_accounts (по возрастанию id)`. Тик региона: регион → товары → строки лавок его живых торговцев → их `characters`
(всё это **до** проводки `region_tick`, чтобы не держать счета в ожидании строк) → счета. Покупка/продажа игрока:
строка лавки → `characters` игрока и НПС → счета; регионы игрок не блокирует (цены и ставку налога читает без
блокировок — снимок последнего тика). «Пополнить кассы»: `characters` → счета.

### Шаг торговцев в тике (`app/econ_tick.py`, B6; математика — чистый `app/econ_merchant.py`, B5)

- **Начало прогона** (`_prepare_merchants`, best effort — сбой логируется, регионы тикают без торговцев):
  удаляются строки лавок удалённых НПС (`npc_id` нет в `characters`) → `RunSummary.shop_rows_purged`; строится карта
  `{region_id: [npc_id]}` живых торговцев (НПС с активными строками → `merchant_place` → `merchant_status`).
- **В транзакции региона** после блокировки товаров: `lock_merchants` — строки лавок этих НПС FOR UPDATE, затем
  `lock_characters` (касса), повторная проверка статуса (НПС, переехавший после построения карты, выпадает с INFO).
  Сбой чтения → торговцы региона пропущены, `merchant_failures += 1`, регион идёт дальше.
- **После проводки `region_tick`**, внутри `session.begin_nested()` (SAVEPOINT; перед ним `flush`, это же открывает
  транзакцию pysqlite в тестах): кошелёк после налога/жалованья → `econ_merchant.merchant_step` → `UPDATE stock`
  изменённых активных строк (`NULL` живого торговца становится числом) → `DELETE` строк `origin='player'` с остатком
  ≤ 0 → запас групп `econ_region_goods.stock += delta` (не ниже 0) → **одна** операция `merchant_trade` на регион:
  ноги на каждого торговца `кошелёк → НПС` (покупки жителей), `НПС → казна` (`trade_tax`, +10 % `казна → страна`
  добавляет реестр), `НПС → кошелёк` (докупка), `НПС → кошелёк` (содержание сверх 3× нормы кассы); ключ
  `merchant_trade:<run_id>:r:<region_id>`; metadata `{run_id, sold_value, tax, purse_budget, merchants: {"<npc_id>":
  {sold_items, sold_value, tax, restock_items, restock_value, upkeep}}}`. Все ноги нулевые → операции нет.
- **Ошибка в шаге** → откат SAVEPOINT (строки лавок, запасы, деньги — как до шага), ERROR в лог с id региона и
  классом ошибки, `merchant_failures += 1`, `merchant_failed_region_ids`; регион **коммитится**. В
  `econ_tick_runs.error` дописывается `торговцы — ошибка в регионах: <ids>` (статус прогона остаётся `done`).
  Строка `econ_region_history` пишется после шага (запасы и кошелёк уже с учётом торговцев).
- **Идемпотентность:** наследуется от региона (`last_run_id` + ключ `region_tick`); повтор того же прогона — регион
  `already`, `merchant_trade` второй раз не проводится (и ключ уникален).
- Строки торговцев legacy и неактивные строки не трогаются; строки «вне рынка» живого торговца не докупаются и не
  продаются жителям (остаток ведёт админ).

`RunSummary` (ответ «Пересчитать сейчас»): `merchants_processed`, `merchant_items_sold`, `merchant_items_restocked`,
`merchant_ops_posted`, `merchant_failures`, `merchant_failed_region_ids`, `shop_rows_purged`. В `GET …/sim` у каждого
прогона (`runs[]`, `running`) — вычисляемые `merchant_ops_posted` (операции `merchant_trade:<id>:r:%`) и
`merchant_failures` (разбор `error`; миграции у `econ_tick_runs` нет).

### API торговцев (`app/economy_api.py` + `app/economy_merchants_crud.py`)

| Метод и путь | Права | Что делает |
|---|---|---|
| `GET /characters/admin/economy/merchants?region_id=&living=` | `economy:read` | все НПС со строками лавок (включая неактивные строки и legacy) |
| `POST /characters/admin/economy/merchants/fund` | `economy:settings` **и** `economy:emit` | «Пополнить кассы торговцев» |

Ответ списка: `{items: [{npc_id, name, location_id, region_id, region_name, living, reason, tax_rate, cash,
cash_target, rows: [{row_id, item_id, item_name, group, off_market, origin, is_active, base_buy, base_sell, ask, bid,
market, stock, restock_target}], stock_value, last_trade}], totals: {merchants, living, cash}}`. `ask`/`bid` — текущие
цены (без харизмы); `stock` у живого — число (`NULL` → 0), у legacy `null` = безлимит; `cash_target` =
`econ_merchant.cash_target` (живые; у legacy 0); `stock_value` = Σ остаток × ask по активным строкам; `last_trade` —
из последних 10 операций `merchant_trade` региона, где есть этот НПС: `{operation_id, run_id, at, sold_items,
sold_value, tax, restock_items, restock_value, upkeep}` или `null`. Удалённый НПС до чистки тиком — `name: null`,
`reason: not_npc`.

Пополнение: тело `{region_ids?: [int] ≤ 500, npc_ids?: [int] ≤ 500, comment 3..500}` (без фильтров — все живые).
Блокирует `characters` живых торговцев (по возрастанию), сумма `max(0, cash_target − касса)` новыми деньгами;
**одна операция `admin_emission` на регион** (`эмиссия → НПС`, `apply_tax=False`, `region_id`, комментарий и
`actor_user_id`, metadata `{merchant_fund: true, targets}`), ключ
`merchant_fund:r:<region>:m<id последней проводки по счетам этих НПС>:h<crc32 набора НПС>` — повторный клик
эмитирует 0, два одновременных одинаковых — второй `DuplicateOperation` → регион пропущен. Ответ `{merchants (живых
рассмотрено), funded, operation_ids, emitted, skipped: [{npc_id, reason}]}`; причины пропуска: `at_target` (касса уже
≥ нормы), `no_target` (нет рыночных админских строк — норма 0), а для явно перечисленных `npc_ids` ещё
`not_merchant` (нет активных строк), `region_filtered` и причины legacy (`dungeon`, `not_simulated`, …). Отдельная
правка денег одного НПС — как раньше, в карточке НПС (`economy:adjust`).
