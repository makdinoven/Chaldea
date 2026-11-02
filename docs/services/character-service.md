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

### Лорное население и масштаб (FEAT-186, миграция `032_econ_population_scale`)

- `econ_regions.population` и `econ_region_templates.default_population` — **лорное** население (до
  `schemas.ECON_MAX_POPULATION` = 1 000 000 000; колонка INT). API возвращает его как есть.
- Расчёт идёт на **расчётном** населении = лорное / `population_scale` — параметр «Пересчёта» (`econ_sim_settings.params`,
  int, по умолчанию 100, границы 1..10 000; отсутствующий ключ = 100). Единственная точка — `econ_sim.sim_population(pop,
  params)` (масштаб < 1 считается 1, отрицательное население → 0, результат может быть дробным: 50 жителей при масштабе
  100 = 0.5). `simulate_region` масштабирует `RegionState.population` сам; `norm_stock` / `demand_tick` /
  `needs_cost_day` / `starting_purse` / `starting_goods` принимают уже расчётное население — в `economy_sim_crud`
  (`_recompute_norms`, «Заполнить») его передают через `sim_population`. Гранты страны делятся по лорным числам
  (пропорция от масштаба не зависит). Торговцы и банки население не читают — они масштабируются через кошелёк и нормы.
- Админские ответы: у региона `sim_population`, у шаблона `default_sim_population` (только чтение, округлено до 0.01).
- Свойство кода: лорное N при масштабе 100 считается бит-в-бит как старое население N/100 (тест
  `tests/test_econ_population_scale.py`).
- Миграция 032 трогает **только шаблоны** и только поля, ещё равные значениям 028: `default_population` ×100,
  названия «Столичный регион», «Портовый регион», …, «Пограничный регион», «Сельский регион», описания про регион,
  слово для фраз «Регион» (м. р.). `econ_regions.population` и история не меняются — на проде там уже лорные числа.
  Downgrade возвращает значения 028 там, где поле ещё равно значению 032.
- **«Привести к масштабу»** — опции «Заполнить регионы по шаблонам»: `return_purse_excess` / `return_treasury_excess`
  (по умолчанию `false`). Часть кошелька жителей / казны региона выше тех же целей заполнения (`starting_purse` от
  расчётного населения / `treasury_target` пробного шага) уходит обратно в эмиссию ногами `кошелёк → emission` /
  `казна → emission` той же операции `admin_emission` (новых op type нет, сумма мира = 0). Вместе с доливкой баланс
  встаёт ровно на цель; повторный клик ничего не двигает. Нормы пересчитываются под расчётное население всегда, запас =
  норма при `reset_stocks`. Ответ получил `returned`, `returned_purses`, `returned_treasuries`; гонка с другим
  списанием → 409 «Баланс региона изменился во время заполнения, повторите».
- С `return_purse_excess` сначала приводятся позиции **жителей в банке** региона (`econ_banks` FOR UPDATE до счетов,
  порядок 3.8; `econ_bank.resident_rescale`): цели — устойчивое состояние шага жителей при кошельке = цели заполнения
  (вклады `floor(P* × s / (1 − s))`, `s = bank_resident_deposit_share`; займы `floor(P* × bank_resident_loan_share)`;
  у выключенного банка 0/0). Излишек вкладов и излишек займов сначала зачитываются друг в друга (без денег), остаток —
  деньгами: вклады из всего баланса `bank` (банк не уходит в минус, недоплата остаётся долгом перед жителями и вернётся
  тиком), займы из кошелька (не ниже 0). Нетто — одна нога `bank ↔ purse` той же `admin_emission`; вклады игроков и
  `bank_deposits` не трогаются. Ответ: `resident_deposits_out`, `resident_loans_repaid`. Повторный клик — 0.
  Слово по умолчанию в коде (`econ_sim.food_label` / `prosperity_label` / `region_card`, карточка без шаблона) — «Регион».

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

## Banks (FEAT-184)

Один банк на регион (таблицы `econ_banks`, `bank_deposits`, `bank_loans`, миграция `031_econ_banks`). Деньги банка —
два счёта реестра с `ref_id = region_id`: `bank` (свои деньги банка: капитал, вклады жителей, погашения займов; из
него выдаются займы и платятся проценты) и `bank_deposits` (хранилище вкладов игроков = Σ `amount + interest_accrued`
открытых строк; никогда не идёт в займы → вклад игрока всегда снимаем). Чистая математика — `app/econ_bank.py`,
слой БД — `app/economy_bank_crud.py` (разделы: общие помощники → API игрока (B4) → тик (B5) → админка (B6)).
Параметры — 21 ключ `bank_*` в `econ_sim_settings.params` (`econ_tick.load_params`).

### Порядок блокировок (3.8, общий для всех потоков экономики)

`econ_regions → econ_region_goods → npc_shop_items (asc id) → econ_banks (asc region_id) → bank_deposits (asc id) →
bank_loans (asc id) → characters (asc id) → econ_accounts (asc id)`. Любое изменение строк/счетов банка X идёт под
`econ_banks(X) FOR UPDATE`. Потоки игрока `econ_regions` не блокируют.

| Поток игрока | Блокировки |
|---|---|
| вклад / снятие в X | `econ_banks(X)` → строка вклада (или новая) → `characters` → счета |
| перевод A→B / отправка игроку | `econ_banks{A, B}` asc → строки вкладов asc (новая строка получателя — последней) → `characters` (только при оплате из кошелька) → счета |
| займ в X / погашение в L | `econ_banks(X | L)` → строка займа → `characters` → счета |
| тик: проход банка X | `econ_banks(X)` → открытые вклады X → открытые займы X → счета (B, V, P региона X) |
| тик: взыскание займа L | `econ_banks` {L} ∪ банки вкладов должника asc → вклады должника → займ → `characters` → счета |
| тик: закрытие банка удалённого региона | `econ_banks(X)` → займы X → счета |
| удаление персонажа | `econ_banks` всех его вкладов/займов asc → вклады → займы → `characters` → счета |

### Банки в 6-часовом пересчёте (B5, контракт 3.7; `econ_tick.py` + раздел «Tick helpers» в `economy_bank_crud.py`)

После цикла регионов, каждый шаг — **в своей транзакции** (транзакция региона банковские таблицы не трогает):

1. **Закрытие банков удалённых регионов** (`_prepare_banks`): строка `econ_banks` без `Regions` → флаг выключен,
   вклады/займы жителей обнуляются, открытые займы → `written_off` (без денег), свои деньги банка `B(X) → W`
   операцией `treasury_closed` (ключ `bank_closed:r:<X>`, `apply_tax=False`; если позже в B(X) снова попали деньги —
   например, сгоревшие проценты досрочного закрытия — ключ `bank_closed:r:<X>:run<id>`), счёт `bank` деактивирован.
   Хранилище и строки вкладов остаются (перевод в другой банк / выплата при удалении персонажа).
2. **Проход банка** — банки с флагом, открытыми вкладами/займами или ненулевыми суммами жителей, по возрастанию
   региона; одна транзакция на банк: `econ_banks(X)` FOR UPDATE (пропуск, если `last_run_id` = этот запуск) → время
   берётся **после** блокировки → вклады → займы → `econ_bank.bank_step` (проценты, сроки, займы, жители, фактор
   ставки) → все строки записываются → одна операция `bank_tick` (ключ `bank_tick:<run>:b:<X>`, `apply_tax=False`,
   в metadata — счётчики) → `last_run_id`, `last_tick_at`, `accrued_at`, `last_stats` (+ `factor`, + `marks`). Банк
   включён для начислений, только если флаг стоит **и** регион существует; «жители» — только в симулируемом регионе
   (`econ_regions.template_code` и `population > 0`).
   **Прибыль в казну** (фикс 2026-11-01, `econ_bank.profit_to_treasury`): в каждом проходе (и у закрытого банка тоже)
   реализованный чистый процентный доход банка — `получено − выплачено`, где получено = проценты по займам жителей
   этого прохода + проценты/пени по займам игроков, реально погашенные или взысканные с прошлого прохода, а выплачено =
   проценты по вкладам игроков и жителей этого прохода + проценты по вкладам, выплаченные вне прохода (досчёт срочного
   вклада при снятии) — положительная часть × `bank_profit_to_treasury_share` (по умолчанию 1, диапазон 0…1), но не
   больше свободных денег (`lendable` — резерв жителей не трогается), уходит ногой `B(X) → T(X)` (`main`) в той же
   операции `bank_tick` (без налога стране). Счётчики `player_loan_income` и `profit_to_treasury` — в `last_stats`
   (админка «Банки» показывает их в «последнем пересчёте»). Убыток и не покрытый свободными деньгами остаток не
   переносятся. Доход по займам игроков считается по метке: Σ по всем займам банка `max(0, paid_total +
   collected_total − principal)` (сначала возвращается тело займа, потом засчитываются проценты); выплаты вне прохода —
   по метке Σ `interest_total` всех вкладов банка. Метки лежат в `last_stats.marks` (`loan_income`,
   `deposit_interest`); при первом проходе после выкладки метки нет → берётся текущее значение (накопленная раньше
   прибыль не выгребается — её можно вернуть кнопкой «Вернуть капитал в казну»). Известные упрощения: списанный займ
   прибыль не уменьшает (тело не вернулось → дохода просто нет); сгоревшие при досрочном закрытии срочного вклада
   проценты (`V → B`) в «получено» не засчитываются (консервативно).
3. **Взыскание** — займы `active|overdue` с `due_at <= now`, по возрастанию id; одна транзакция на займ: долг
   доначисляется до «сейчас», затем `econ_bank.plan_collection` (вклады до востребования → срочные (сначала
   начисленные проценты) → кошелёк, не больше, чем есть) → операция `loan_collect` (ключ `loan_collect:<run>:l:<id>`:
   `V(Y) → B(L)` по каждому банку вкладов + `C → B(L)`); долг 0 → займ `closed`. Повтор того же запуска — no-op по ключу.

Сбой банка/займа откатывает только его (лог: регион/займ + класс ошибки), остальное идёт дальше; начисление по
времени — на следующем запуске ничего не теряется. Нет таблиц (тик раньше миграции 031) — проходы пропускаются с
предупреждением. `RunSummary` (ответ «Пересчитать сейчас»): `banks_processed`, `bank_ops_posted`, `bank_failures`,
`bank_failed_region_ids`, `bank_interest_paid` (проценты игрокам и жителям), `loans_overdue`, `loans_collected`,
`collected_amount`, `banks_closed`. Ошибки банков пишутся в `econ_tick_runs.error` с префиксом
`BANK_ERROR_PREFIX` («банки — ошибка в регионах: …»); в списке запусков (`economy_sim_crud._run_dict`) выводятся
`bank_ops_posted` и `loans_collected` (по ключам операций) и `bank_failures` (из текста ошибки). На статус запуска
сбои банков не влияют (как у торговцев).

**Снятие созревшего срочного вклада до тика:** `withdraw` доплачивает проценты последнего неполного периода
`[accrued_at, matures_at)` (`matured_term_interest`: только включённый банк, только из свободных денег `lendable`)
ногой `B(X) → V(X)` `interest` в той же операции `bank_withdraw`.

**Удаление персонажа** (`crud.post_character_deletion`, до блокировки персонажа): открытые вклады →
`V(Y) → T(Y)` (`W`, если региона Y нет) в той же операции `character_deleted`, что и кошелёк (налог 10 % — как с
кошелька), строки закрыты; открытый займ → `written_off` (убыток банка, без денег). У НПС банковских строк нет — шаг
пропускается.
| админ: флаг / капитал / списание долга | `econ_banks(X)` (вставляется, если нет) → строка займа → счета |
| «Заполнить регионы» с `open_banks` | строки `econ_regions` → `econ_banks` asc → счета (проводки заливки и капитала) |

### API игрока (B4, контракт 3.9; роутер `economy_api.py`, префикс `/characters/economy/bank`)

| Метод и путь | Тело / query | Ответ |
|---|---|---|
| `GET /npc/{npc_id}?character_id=` | — | `BankView` (без гейта; долг займа — проекция на «сейчас», не сохраняется) |
| `POST /npc/{npc_id}/deposit` | `BankDepositIn {character_id, kind: demand\|term, term_days (term: 7/14/28; demand: null), amount, request_id?}` | `BankActionOut {message, operation_id, wallet, view}` |
| `POST /npc/{npc_id}/withdraw` | `BankWithdrawIn {character_id, deposit_id, amount? (до востребования — обязателен; срочный — весь вклад), request_id?}` | `BankActionOut` |
| `POST /npc/{npc_id}/transfer` | `BankTransferIn {character_id, deposit_id, to_region_id, amount, request_id?}` — свой вклад до востребования → свой вклад в другом банке | `BankActionOut` |
| `POST /npc/{npc_id}/send` | `BankSendIn {character_id, source: wallet\|deposit, deposit_id (только для deposit), recipient_name, to_region_id, amount, request_id?}` | `BankActionOut` |
| `POST /npc/{npc_id}/loan` | `BankLoanIn {character_id, amount, term_days: 7/14/28, request_id?}` | `BankActionOut` |
| `POST /npc/{npc_id}/repay` | `BankRepayIn {character_id, amount, request_id?}` (у любого банкира, даже если банк выключен) | `BankActionOut` |
| `GET /summary?character_id=` | — | `BankSummary` (владелец или `economy:read`; без банкира) |
| `GET /regions` | — | публичный список включённых банков `[{region_id, name, country_name}]` |

**Проверки банкира — в фиксированном порядке:** 1) JWT → персонаж существует (404) и принадлежит пользователю (403),
не НПС (403); 2) НПС существует, `is_npc`, `npc_role = 'banker'` (иначе 404 «Банкир не найден»), не мёртв (409);
3) блокировка активности (только POST, 409 с текстом `activity_lock`); 4) персонаж в локации банкира (400);
5) гейт FEAT-145 (только POST): `locations_client.check_npc_gate` → `GET /locations/internal/action-gate`
(`action_type=npc_dialogue`, `target_ref=npc_id`, `X-Internal-Token`, 5 с), `false` → 403, сбой/не-200 → 503
(fail-closed); вызывается **без открытой транзакции** (чтение шагов 1–4 откатывается до HTTP); 6) регион банкира
(`econ_ledger.resolve_location`, нет → 409). POST-обработчики — `async def`, синхронная работа с БД идёт в threadpool;
шаги 1–4 и 6 повторяются внутри транзакции операции.

**Проводки:** вклад `C → V(X)` (`bank_deposit`); снятие `V(X) → C`, досрочное закрытие срочного — ещё
`V(X) → B(X)` нога `interest` (сгоревшие проценты) (`bank_withdraw`); перевод `V(A) → V(B)` + комиссия
`V(A) → T(X)` нога `commission` (налог 10 % в страну добавляет реестр) (`bank_transfer`); отправка игроку — то же из
кошелька `C → V(B)` / `C → T(X)` или со своего вклада (из одного хранилища в то же — только комиссия, двигаются
строки); займ `B(X) → C` (`loan_issue`); погашение `C → B(L)` (`loan_repay`). X — регион банкира, L — банк займа.
Комиссия = `max(fee_min, ceil(amount × fee_rate))`, берётся **сверх** суммы из источника.

**Правила:** минимальная сумма `bank_min_amount` (кроме снятия/погашения всего остатка); новый вклад до
востребования начинает с `interest_base = 0` (процент — со следующего периода), пополнение не меняет
`interest_base`, снятие — `interest_base = min(base, amount)`; срочный — ставка `term_rate × factor` фиксируется при
открытии, не больше 10 открытых срочных вкладов на персонажа; срочный после `matures_at` отдаётся с процентами
(даже если тик ещё не превратил его во вклад до востребования); займ — не больше `loan_cap(level)` и свободных денег
банка (`lendable`: баланс `bank` минус резерв под вклады жителей), один открытый займ на персонажа
(`uq_bank_loans_active`), просроченный займ → «Должник», новые не выдаются; при погашении долг сначала
доначисляется до текущей минуты. Получатель перевода — имя персонажа-игрока (`is_npc = 0`; сравнение по collation колонки — без учёта регистра и ё): нет → 404,
несколько → 409, сам себе → 400; вклады получателя в ответе не раскрываются.

**Идемпотентность:** `request_id` (`^[A-Za-z0-9-]{8,64}$`) → ключ реестра `bank:<dep|wd|tr|send|loan|repay>:c<id>:<request_id>`;
повтор → 409 «Операция уже выполнена» (проверка до бизнес-проверок и ещё раз после блокировки банка; гонку ловит
уникальный ключ реестра). Конфликт уникальных ключей БД → 409 «Не удалось выполнить операцию, попробуйте ещё раз».
Суммы — строгие целые 1…1e9 (float/строка/bool → 422). Логи — только id и суммы.

### Таблицы (миграция `031_econ_banks`)

| Таблица | Ключ | Назначение |
|---|---|---|
| `econ_banks` | `region_id` (без FK на `Regions`) | флаг «Банк есть» `is_enabled`, фактор ставки вкладов `deposit_rate_factor`, вклады/займы жителей числами (`resident_deposits`, `resident_loans` + carry), часы жителей `accrued_at`, `capital_seeded_at` (стартовый капитал уже взят), `last_run_id` / `last_tick_at` / `last_stats` (JSON, ключи `econ_bank.STAT_KEYS`) |
| `bank_deposits` | `id`; FK `region_id → econ_banks`; `uq (region_id, demand_owner_id)` — один открытый вклад до востребования на банк | вклады игроков: `kind` demand/term, `status` open/closed, `amount`, `interest_base` (минимальный остаток периода), `interest_accrued` (только срочный), `rate_day` (срочный — фикс.), `term_days`, `matures_at`, `accrued_at` |
| `bank_loans` | `id`; FK `region_id → econ_banks`; `uq (active_character_id)` — один открытый займ на персонажа | `status` active/overdue/closed/written_off, `principal`, `debt` (с процентами и пенями), итоги (`interest_total`, `penalty_total`, `paid_total`, `collected_total`, `written_off`), ставки фикс. при выдаче, `due_at`, `accrued_at`, `closed_by_user_id` + `note` (списание админом) |

### Админ-API (B6, контракт 3.10; префикс `/characters/admin/economy`)

Чтение — `economy:read`, изменения — `economy:settings` (новых прав нет). Ответы — обычные словари.

| Метод и путь | Тело | Ответ |
|---|---|---|
| `GET /banks` | — | `{items: [BankAdminItem], totals: {banks, enabled, own_funds, player_deposits, resident_deposits, player_loans_debt, resident_loans, debtors}}` — только регионы со строкой `econ_banks` |
| `GET /banks/debtors` (объявлен до `/banks/{region_id}`) | — | список `{loan_id, character_id, character_name, region_id, region_name, debt, principal, due_at, overdue_days, penalty_total}` — открытые займы после `due_at` с долгом, долг по убыванию |
| `GET /banks/{region_id}` | — | `{item, deposits (открытые, 500 новейших), loans (открытые)}` — поля игрока + `character_id`, `character_name` (+ `status` у вкладов); 404 «Банк не найден» (редактор региона читает флаг отсюда) |
| `PUT /banks/{region_id}` | `BankFlagIn {is_enabled, seed_capital = true}` | `BankAdminItem`; 404 «Регион не найден»; создаёт строку (`accrued_at = now`); первое включение с `seed_capital` и `capital_seeded_at IS NULL` → `bank_capital` `T(X) → B(X)` на `min(bank_start_capital, max(0, казна − econ_regions.treasury_target))` (только излишек казны над её резервом; фикс 2026-11-01 — раньше брал всю казну, и жалованье падало до 0), ключ `bank_capital:r:<X>:seed`, `capital_seeded_at = now` даже при 0 (повторное включение капитал не берёт) |
| `POST /banks/{region_id}/capital` | `BankCapitalIn {direction: in\|out, amount 1…1e9, comment 3…500}` | `{operation_id, bank_balance, treasury_balance}`; `in` больше положительной казны → 400 «В казне региона только N»; `out` больше `lendable` (резерв жителей остаётся) → 400 «Банк может вернуть не больше N»; нет строки банка → 404; без налога; ключ `bank_capital:r:<X>:p<последняя проводка B(X)>:<dir>:<amount>` |
| `POST /banks/loans/{loan_id}/write-off` | `BankWriteOffIn {comment}` | `BankLoanOut`; долг доначисляется до «сейчас», затем `written_off += debt`, `debt = 0`, `status = written_off`, `active_character_id = NULL`, `closed_by_user_id`, `note`; денег не двигает (убыток банка), снимает «Должник»; закрытый → 409 «Займ уже закрыт», нет → 404 |

`BankAdminItem`: `region_id, region_name, country_name, enabled` (строка включена и регион существует), `simulated`,
`bankers` (**список** `{npc_id, name}` живых НПС с ролью `banker`, чья локация разрешается в регион), `own_funds`
(баланс `bank`), `vault` (баланс `bank_deposits`), `deposits_sum` (Σ открытых строк), `vault_ok`, `deposits_count`,
`term_count`, `resident_deposits`, `resident_loans`, `reserve`, `lendable`, `loans_count`, `loans_debt` и
`overdue_count` (по долгу, спроецированному на «сейчас»), `rate_factor`, `demand_rate_day`, `term_rates
[{term_days, rate_day}]`, `capital_seeded_at`, `last_tick_at`, `last_stats` (`{}` до первого прохода).

**Интеграция с экономикой:** `GET /regions` (и деталь региона) — `bank_enabled`; публичная карточка региона —
`has_bank` в обеих формах (включая `participating: false`); `POST /regions/fill` — `open_banks` (по умолчанию `true`):
регионам с шаблоном `capital` / `port` (`BANK_TEMPLATE_CODES`) и жителями после заполнения включает банк и один раз
берёт стартовый капитал **после** пополнения казны, ответ `+ banks_opened` (регионы, чей банк включила именно эта
заливка); строки `econ_banks` блокируются до проводок заливки (порядок 3.8). Сводка — `totals.banks`,
`totals.bank_deposits`, `invariant.bank_deposits_expected` (Σ открытых строк) / `bank_deposits_actual` (Σ хранилищ),
расхождение роняет `ok`; счета `bank` / `bank_deposits` — региональные (имя из `Regions`, операции с `region_id`), в
«системные счета» сводки не попадают, ручная корректировка их запрещена (`ADJUST_FORBIDDEN_KINDS`), эмиссия в них
невозможна.

## Region events (FEAT-187)

Временные модификаторы регионов — кризисы (засуха, чума, потоп…) и благоприятные события (урожайный год, ярмарка…).
Всё живёт в character-service: таблицы и сид — миграция `033_econ_region_events`, чистая математика —
`app/econ_events.py`, проход событий в тике — `app/econ_tick.py`, БД-помощники и админ-логика —
`app/economy_events_crud.py`, маршруты — `app/economy_api.py`. Подробности решения — `features/FEAT-187-*.md` §3.

### Таблицы (миграция `033_econ_region_events`)

- `econ_event_templates` — шаблоны, которые заводит админ: `code` (неизменяемый slug, на него ссылаются цепочки),
  `name`, `icon` (белый список `EVENT_ICONS`), `kind` good/bad, `player_text` (≤ 500, видят игроки), `admin_note`,
  `trigger_kind` random / low_stability (бунт) / manual (только руками), `weight`, `duration_min_days` /
  `duration_max_days`, `scope` region / neighbours / country / world, `spread_chance` (за жизнь события),
  `region_templates` и `seasons` (JSON, пусто = любые), `effects` (JSON, ≤ 12), `chains` (`[{code, chance}]`),
  `is_enabled`. Сид — 14 стартовых шаблонов (`EVENT_TEMPLATES` в миграции).
- `econ_region_events` — **один экземпляр события в одном регионе: и активное состояние, и вечная история**. Снимок
  шаблона на момент старта (`template_code, name, icon, kind, player_text, trigger_kind, effects, chains,
  spread_chance`) + `region_name` / `country_id`; `origin` random / manual / spread / chain / riot, `parent_event_id`
  (источник распространения/цепочки), `root_event_id` (первый экземпляр многорегионного старта), `generation`;
  `status` active / ended / cancelled, `started_at`, `ends_at`, `ended_at`; `origin_key` UNIQUE (идемпотентность
  бросков и ручного `request_id`), `active_key` UNIQUE (`r<region>:<code>` пока активно — один активный экземпляр
  шаблона в регионе); итоги разовых эффектов: `applied_at`, `applied_run_id`, `population_before/after`, `outcome`
  (`{stock_lost: {group: units}, treasury_expense, operation_id}`); аудит: `started_by_user_id`,
  `cancelled_by_user_id`, `cancel_comment`. Нет FK на `Regions` / `econ_regions` / `econ_tick_runs` (история
  переживает их), `template_id` → SET NULL при удалении шаблона.
- `econ_regions.low_stability_since` — «часы бунта» (ставит/сбрасывает тик).

### Эффекты (3.4)

| type | поля | когда | рычаг |
|---|---|---|---|
| `production` / `consumption` | groups, mult 0…5 | каждый шаг | копия производства / потребления группы × m |
| `labor` («больные жители») | mult 0…1.5 | каждый шаг | производство всех групп × m |
| `price` | groups, mult 0.2…5 | каждый шаг | `price_mult × m` в пределах `price_min…price_max` |
| `tax_income` | mult 0…5 | каждый шаг | налог × m |
| `stability` / `prosperity` | delta −10…10 | каждый шаг | ± к показателю |
| `merchants_halt` | — | каждый шаг | торговцы не докупают |
| `bank_panic` / `loan_boom` | — / mult 1…5 | проход банков | жители забирают вклады / больше займов |
| `stock_loss` | groups, share 0…0.9 | один раз | запасы × (1 − share) |
| `treasury_expense` | share 0…0.9 | один раз | операция `region_event` казна → кошелёк жителей, без налога, ключ `region_event:e<id>` |
| `population` | pct −0.5…0.5 | один раз | лорное население × (1 + pct), не ниже масштаба |

Несколько событий складываются (произведения множителей, суммы дельт) и обрезаются параметрами
`event_mult_min/max`, `event_delta_max`. Без активных событий `simulate_region(mods=None)` считает побитово как раньше.
Разовые эффекты применяются **один раз** в транзакции региона первого пересчёта (авто или ручного) после старта.

### Тик (3.6)

Проход событий после подготовки торговцев, до цикла регионов, best effort (ошибка → `события — ошибка: …` в
`econ_tick_runs.error`, регионы всё равно считаются): окончание по часам в **каждом** прогоне; броски (бунт →
случайное → цепочки → распространение) — **только в плановых слотах** и при `events_enabled = 1`, RNG от
`слот:регион:цель`, ключи `auto:<slot>:r<R>`, `riot:…`, `chain:…`, `spread:…`. Сезон — `GET /locations/game-time`
(3 с; сбой → только шаблоны без сезона). Соседи — `region_transition_arrows` в обе стороны, иначе регионы той же
страны. Параметры (`/admin/economy/sim`): `events_enabled, event_rate_per_season, event_season_days, event_max_active,
event_mult_min, event_mult_max, event_delta_max, event_spread_max_depth, event_riot_stability, event_riot_after_days`.

**Порядок блокировок (3.6.1, заменяет FEAT-184 3.8):** `econ_regions → econ_region_goods → econ_region_events (asc id)
→ npc_shop_items (asc id) → econ_banks (asc region_id) → bank_deposits → bank_loans → characters → econ_accounts`.
Проход событий и админ-потоки трогают только строки событий (вставки / UPDATE / `FOR UPDATE` одной строки при отмене).

### API (B4, контракт 3.7; префикс `/characters`)

Чтение — `economy:read`, изменения — `economy:settings` (новых прав нет). 401 без токена, 403 без права.

| Метод и путь | Тело / запрос | Ответ и отказы |
|---|---|---|
| `GET /admin/economy/events/templates` | — | `List[EventTemplateOut]` (kind, name) + `active_count` |
| `POST /admin/economy/events/templates` | `EventTemplateIn` | 201 `EventTemplateOut`; 409 «Шаблон с кодом «{code}» уже есть»; 400 «Неизвестная группа товаров: {code}» / «Неизвестный шаблон региона: {code}» / «Цепочка ссылается на неизвестное событие: {code}» / «Событие не может вызывать само себя»; 422 — границы 3.8 (лишнее / недостающее поле эффекта, иконка, сезон, длительность…) с русским `msg` |
| `PUT /admin/economy/events/templates/{id}` | `EventTemplateUpdate` (всё, кроме `code`; `code` в теле игнорируется) | `EventTemplateOut`; 404 «Шаблон события не найден»; те же 400. Идущие экземпляры сохраняют снимок |
| `DELETE /admin/economy/events/templates/{id}` | — | 204; 404; 409 «На это событие ссылаются цепочки: «…»»; у экземпляров `template_id = NULL` |
| `GET /admin/economy/events/active?region_id=` | — | `List[RegionEventOut]` (status active, `ends_at > now`, по `ends_at`) |
| `POST /admin/economy/events/start` | `EventStartIn {template_id, region_id, scope?, duration_days? 0…365, request_id? [A-Za-z0-9-]{8,64}}` | `{started: [RegionEventOut], skipped: [{region_id, region_name, reason (русский текст)}]}`; 404 шаблон / «Регион не найден»; 409 «Регион не участвует в пересчёте — у него нет шаблона или населения»; ничего не запущено → 409 с первой причиной («В регионе уже идёт «…» — отмените его или дождитесь конца»); тот же `request_id` → 409 «Событие уже запущено». Выключенные шаблоны и любой триггер запускаются; `event_max_active` не действует; разовые эффекты — при следующем пересчёте |
| `POST /admin/economy/events/{id}/cancel` | `EventCancelIn {comment 3…500}` | `RegionEventOut` (cancelled, `ended_at = now`, `active_key = NULL`); 404 «Событие не найдено»; 409 «Событие уже закончилось». Разовые итоги не откатываются |
| `GET /admin/economy/events/history` | `region_id, template_code, kind, status, origin, date_from, date_to (YYYY-MM-DD, по started_at), page, page_size ≤ 200` | `{items, total, page, page_size}` (новые сначала); 422 на плохой запрос; 400 «Дата начала периода позже даты конца» |
| `GET /economy/regions/{id}/card` (публичный) | — | `+ events: [{code, name, icon, kind, text, started_at, ends_at}]` в **обеих** формах (`[]` для неучаствующих); без чисел эффектов |
| `GET /admin/economy/regions` | — | у элемента `+ active_events: [{name, icon, kind}]` |
| `GET /admin/economy/sim`, `POST …/sim/run` | — | счётчики `events_ended, events_started, events_spread, events_chained, riots_started, events_applied, event_expense_ops, events_failed`; у ручного прогона — из `RunSummary`, в списке прогонов — **выведены** из экземпляров (`run_id` / `applied_run_id` / `outcome.operation_id`; `events_ended` — окончания между стартом предыдущего прогона и этого, приблизительно; `events_failed` — части текста ошибки) |

### Контракт для будущей газеты (3.1.2)

Читать `econ_region_events` напрямую: `SELECT … ORDER BY started_at`. Строки **никогда не удаляются** (`purge_old` их
не трогает), содержат снимки имени региона и шаблона — переименование/удаление региона или шаблона историю не ломает.
Поля для текста: `region_name, name, icon, kind, player_text, origin, started_at, ends_at, ended_at, status,
cancel_comment` (только для админов), итоги — `population_before/after`, `outcome`. Объём ≈ 1 строка на регион за
49 дней. Публичного читателя истории пока нет — его добавит фича газеты.

## Mint and season quota (FEAT-191)

Этап 5а экономики: два штатных источника новых марок — **монетный двор** (один на страну, в столице) и **квота
сезона**. Деньги — только проводки книги счетов со счёта `emission`. Модули: чистый `app/econ_mint.py` (календарь,
расчёт двора, деление квоты), БД — `app/economy_mint_crud.py`, проходы тика — `econ_tick._quota_pass` / `_mint_pass`,
роутер — `app/economy_api.py`.

### Операции книги (econ_core, копии ×4)

| op_type | Ноги | Ключ идемпотентности |
|---|---|---|
| `mint_court` | `emission → country_treasury(страна)`, `region_id` = столица | `mint_court:<run_id>:c<country_id>` |
| `mint_player` | `emission → character` | `mint:<character_id>:<request_id>` |
| `season_quota` | `emission → region_treasury(R)` по всем участвующим регионам (одна операция) | `season_quota:p<period_index>` |

Все три — в `OP_TYPES`, `SOURCE_OP_TYPES` и `MINT_OP_TYPES`, **не** требуют комментария, `apply_tax=False`.
`mint_player` засчитывается заданиям БП «заработай марки» (battle-pass не исключает его).

### «Сезон» (3.3)

Сезон + праздник после него = 49 реальных дней, 4 периода в год. character-service **читает `game_time_config`
напрямую** (таблица locations-service, только чтение, одна строка); формула `compute_game_time`:
`elapsed = max(0, floor((now − epoch)/86400) + offset_days)`, `index = elapsed // 49` (абсолютный, монотонный),
`year = index // 4 + 1`, `season = spring|summer|autumn|winter`, `starts_at = epoch + (index·49 − offset_days) дней`,
`ends_at = starts_at + 49 дней`. Раскладка календаря продублирована в `econ_mint.YEAR_SEGMENTS` — держать в синхроне с
`locations-service/app/crud.py` и `frontend/src/utils/gameTime.ts`. Нет строки/таблицы календаря → квота пропускается,
двор и монетчики закрыты («календарь мира недоступен»). Правка календаря назад повторно использует счётчик и ключ квоты
(второй квоты нет); вперёд — пропущенные сезоны не наверстываются.

### Таблицы (миграция `034_econ_mint`, без FK)

- `econ_mints` — по стране: `country_id` PK, `capital_region_id` (NULL = авто), `season_limit` (NULL = параметр
  `mint_season_limit`), `is_enabled` (по умолчанию 1), `updated_at`, `updated_by`. Нет строки = всё по умолчанию.
- `econ_mint_items` — руда, которую принимает монетчик: `item_id` PK, `marks_per_item`, `is_enabled`, `updated_*`.
- `econ_mint_seasons` — общий лимит страны за сезон (двор + игроки), блокируемый счётчик: PK `(country_id,
  period_index)`, `minted_court`, `minted_players`, `ore_units_court`, `ore_units_players`, `created_at`, `updated_at`.
  Строка создаётся `ensure_season_row` в **своей короткой транзакции** (никогда под другими блокировками); не чистится.

Новые параметры пересчёта (JSON `econ_sim_settings.params`, без миграции): `quota_season_amount` (0, 0…1e9),
`mint_season_limit` (0, 0…1e9), `mint_court_marks_per_unit` (8.0, 0.01…10 000), `mint_court_threshold_pct`
(100.0, 0…1000). Значения 0 = всё выключено до настройки админом.

### Столица и «двор работает» (3.4)

Столица: `econ_mints.capital_region_id`, если регион существует и принадлежит стране (`manual`); иначе единственный
регион страны с шаблоном `capital` (`auto`); 0 или ≥ 2 таких → столицы нет (`none`). Устаревшая ручная столица
игнорируется (`override_stale` в админке). Двор работает, когда есть столица, `is_enabled`, столица участвует
(`template_code` и `population > 0`), у неё есть строка `econ_region_goods('ore_metal')`, лимит > 0 и календарь
доступен. Причины закрытия: «у страны не выбрана столица», «двор выключен», «столица не участвует в экономике»,
«в столице не ведётся запас руды и металла», «лимит не задан», «календарь мира недоступен».

### Тик (3.6 / 3.7)

- **Квота** — перед циклом регионов, своя транзакция: `quota_season_amount > 0` и календарь есть → если операции с
  ключом `season_quota:p<index>` ещё нет — одна операция `emission → казны` участвующих регионов (`SQL_PARTICIPATING`),
  деление по населению методом наибольших остатков (сумма ровно равна квоте, ничьи → меньший id). Сбой → `квота —
  ошибка` в `econ_tick_runs.error`, повтор в следующем прогоне. Работает и в ручных прогонах (ключ сезона).
- **Двор** — после цикла регионов, до банков, транзакция на страну: `econ_regions(столица) → econ_region_goods(столица,
  ore_metal) → econ_mint_seasons(страна, сезон)` FOR UPDATE → `excess = max(0, stock − norm·threshold/100)`,
  `marks = min(floor(excess·rate), остаток лимита)`, `units = min(excess, ceil_3(marks/rate))` → `stock −= units`,
  счётчик += → `mint_court`. Сбой страны → `чеканка — ошибка в странах: …`, остальные идут. Марки попадают в регионы
  через гранты страны **следующего** прогона (план грантов фиксируется при захвате прогона).
- `RunSummary`: `quota_amount, quota_failed, mint_court_ops, mint_court_marks, mint_failures, mint_failed_country_ids`.

### Порядок блокировок (3.12, заменяет FEAT-187 3.6.1)

`econ_regions → econ_region_goods → econ_region_events (asc id) → econ_mint_seasons → npc_shop_items (asc id) →
econ_banks (asc region_id) → bank_deposits (asc id) → bank_loans (asc id) → character_inventory (asc id) →
characters (asc id) → econ_accounts (asc id)`. Транзакция региона не трогает `econ_mint_seasons` /
`character_inventory`. Двор: `econ_regions → econ_region_goods → econ_mint_seasons → econ_accounts`. Игрок:
`econ_regions → econ_region_goods → econ_mint_seasons → character_inventory → characters → econ_accounts`. Квота:
только `econ_accounts`.

### Монетчик — API игрока (3.8; роль НПС `minter`)

Порядок проверок как у банкира: 1 JWT + владелец + персонаж игрока (403) → 2 НПС существует, `is_npc`, роль `minter`
(404 «Монетчик не найден»), не мёртв (409) → 3 блокировка активности (POST) → 4 та же локация (400) → 5 FEAT-145
(POST, fail-closed, 403 / 503) → 6 локация → регион → страна; у страны есть столица, и это не регион монетчика → 409
«Монетный двор есть только в столице страны — этот монетчик ему не служит»; двор не работает → 409 «Монетный двор
закрыт: {причина}» (GET отдаёт вид с `working=false`).

| Метод и путь | Тело / запрос | Ответ и отказы |
|---|---|---|
| `GET /characters/economy/mint/npc/{npc_id}?character_id=` | — | `MintView` (сезон, лимит, отчеканено двором/игроками, остаток, принимаемая руда с `have` и `max_by_limit`, кошелёк) |
| `POST /characters/economy/mint/npc/{npc_id}/mint` | `MintIn {character_id, item_id, quantity 1…10000, request_id [A-Za-z0-9-]{8,64}}` | `MintActionOut {message, operation_id, marks, quantity, requested, partial, wallet, view}` — `quantity`/`marks` = реально принятые штуки и выплата; при нехватке лимита принимается `floor(остаток / marks_per_item)` шт., `partial=true`, сообщение «Принято N из M шт. — лимит сезона исчерпан, остальная руда осталась у вас. Отчеканено …»; иначе «Отчеканено …: руда × N»; 400 «Монетный двор не принимает этот предмет» / «Не хватает: …» (проверка по **запрошенному** количеству); 409 «Монетный двор исчерпал лимит до dd.mm.yyyy» (не влезает ни одной штуки) / «Операция уже выполнена» |

Поток (одна транзакция, роутер коммитит): `ensure_season_row` (своя транзакция) → блокировки → проверка ключа →
предмет включён и его действующая группа `ore_metal` → лимит: `accepted = min(quantity, floor(остаток /
marks_per_item))`, 0 → 409 (частичный приём, решение пользователя 2026-11-01; раньше запрос отклонялся целиком) →
**руда списывается прямо из `character_inventory`** (в сумке должно быть всё **запрошенное** количество, списывается
только `accepted`; только обычные стопки: `enhancement_points_spent = 0`, без камней, без прочности; строки
`FOR UPDATE` по id; DELETE или `quantity − q`) → `stock += accepted × units_per_item` → счётчик `+= accepted ×
marks_per_item` → `mint_player` последним шагом (в metadata `quantity` = принято, `requested` = запрошено). Любой
отказ откатывает всё — руда не теряется; повтор с тем же `request_id` → 409 «Операция уже выполнена».

**Межсервисная запись:** character-service пишет в таблицу inventory-service `character_inventory` напрямую (тот же
принятый приём, что `locations-service houses._take_materials`). Если inventory-service заведёт производные кэши
сумки — поток чеканки должен их обновлять.

### Админ-API (3.10; префикс `/characters/admin/economy`)

| Метод и путь | Права | Описание |
|---|---|---|
| `GET /mint` | `economy:read` | `MintAdminOut`: текущий сезон, параметры, по каждой стране — столица (auto/manual/none, кандидаты, устаревшая ручная), работает ли и почему нет, лимит (свой/по умолчанию), отчеканено двором/игроками, остаток (0, если двор закрыт — как у игрока), запас руды столицы и норма, монетчики (`in_capital`) |
| `PUT /mint/countries/{country_id}` | `economy:settings` + `economy:emit` | `MintCountryIn {capital_region_id\|null, season_limit 0…1e9\|null, is_enabled}` (все ключи обязательны); 404 «Страна не найдена»; 400 «Регион не принадлежит этой стране» |
| `GET /mint/items` | `economy:read` | `List[MintItemOut]` с `effective_group` и `valid` |
| `PUT /mint/items/{item_id}` | `economy:settings` + `economy:emit` | `MintItemIn {marks_per_item 1…1e6, is_enabled}`; 404 «Предмет не найден»; 400 «Чеканить можно только руду и металл (группа «Руда и металл»)» |
| `DELETE /mint/items/{item_id}` | `economy:settings` + `economy:emit` | 204; 404 |
| `GET /mint/quotas?limit=20` | `economy:read` | `List[QuotaOut]` — история операций `season_quota`, новые сначала |
| `PUT /sim` (существующий) | `economy:settings` | изменение `quota_season_amount`, `mint_season_limit` или `mint_court_marks_per_unit` без `economy:emit` → 403 «Нужно право на эмиссию» |

Публичная карточка региона `GET /characters/economy/regions/{id}/card` получила `has_mint` в обеих формах (регион —
действующая столица и двор работает).


## NPC caravans (FEAT-192)

Этап 5б экономики: караваны НПС возят товары из регионов с излишком (запас выше нормы) в регионы с нехваткой и тем
выравнивают запасы и цены. Модули: чистый `app/econ_caravan.py` (маршрут, подбор, цена/пошлина, пересчёт при
отправке), БД — `app/economy_caravan_crud.py`, проход тика — `econ_tick._caravan_pass`, роутер — `app/economy_api.py`.

### Правила

- **Маршруты:** внутри страны — между любыми участвующими регионами всегда, без пошлины, в пути
  `caravan_travel_domestic` пересчётов (1); между странами — только если пара стран разрешена в `econ_trade_pairs`
  (по умолчанию запрещено), в пути `caravan_travel_foreign` (2), пошлина `duty_pct` пары. Граф соседства не нужен,
  только `Regions.country_id`.
- **Подбор (3.5, детерминирован):** группы — сначала продовольствие, затем по коду; продавец отдаёт не больше
  `caravan_surplus_share` (25 %) излишка над нормой и всегда остаётся не ниже нормы; покупатель получает не больше, чем
  нужно до нормы, **с учётом уже едущего** (`inbound`); покупатели — самые нуждающиеся первыми
  (`(stock + inbound) / norm`), продавцы — ближние и дешёвые первыми (`travel_runs`, цена, id). Сигнал —
  `stock / norm_stock` (ценовые модификаторы событий отправку не вызывают). `norm_stock = 0` → группа пропускается.
  Не больше `caravan_max_per_run` отправок за пересчёт, сделки дешевле `caravan_min_value` не отправляются.
- **Цена:** `unit_price = base_price × price_mult продавца` (4 знака), `value = floor(units × unit_price)`,
  `duty = floor(value × duty_pct / 100)` — платит покупатель **сверху**, продавец получает полный `value`.
- **Кто платит:** кошелёк жителей покупателя — до `caravan_purse_share` (25 %) кошелька за пересчёт на все группы;
  **продовольствие** доплачивает казна региона-покупателя — до `caravan_treasury_food_share` (50 %) её положительного
  остатка. Не хватает денег → объём уменьшается до оплачиваемого.
- **«Набег» / «Бунт»** (эффект `merchants_halt` активного события) — регион не **вывозит**; ввозить может; караваны в
  пути едут дальше.
- Руда, привезённая в столицу, чеканится двором в этом же прогоне (так задумано).

### Деньги: счёт «Караваны в пути» (3.4)

Новый одиночный счёт `caravan_escrow` («Караваны в пути»): не уходит в минус, не источник денег, не облагается.

| op_type | Ноги | Ключ |
|---|---|---|
| `caravan_dispatch` | `population_purse(покупатель) → caravan_escrow` + (только еда) `region_treasury(покупатель) → caravan_escrow` | `caravan:c<id>:pay` |
| `caravan_delivery` | `caravan_escrow → population_purse(продавец)` = value; `caravan_escrow → country_treasury(страна покупателя)` = duty | `caravan:c<id>:done` |
| `caravan_cancel` | `caravan_escrow → кошелёк / казна покупателя` = ровно то, что было заплачено | `caravan:c<id>:back` |

Все три — в `OP_TYPES` и `CARAVAN_OP_TYPES` (не в `SOURCE_OP_TYPES`, без комментария), проводятся с
`apply_tax=False` (налог страны на них не начисляется — переводы с/на `caravan_escrow` под правило налога не попадают).
Получатель удалён: кошелёк / казна удалённого региона → казна его страны (`from_country_id` / `to_country_id` строки),
удалённая страна → Казна Скитальцев. **Подинвариант** (сводка): баланс `caravan_escrow` = Σ `paid_purse +
paid_treasury` караванов `in_transit`; `totals.caravan_escrow`, `invariant.caravan_escrow_expected / _actual`, входит
в `invariant.ok`. Счёт нельзя корректировать (`ADJUST_FORBIDDEN_KINDS`).

### Таблицы (миграция `035_econ_caravans`, без FK, без ENUM)

- `econ_trade_pairs` — разрешение торговли пары стран, симметричное: PK `(country_a, country_b)`, `country_a <
  country_b` (нормализует приложение), `is_enabled` (0), `duty_pct` DECIMAL(5,2) (10.00), `updated_at`, `updated_by`.
  Нет строки = торговля запрещена.
- `econ_caravans` — караван: `dispatch_run_id`, `from/to_region_id`, `from/to_country_id`, `group_code`, `units`
  DECIMAL(16,3), `unit_price` DECIMAL(14,4), `value`, `duty`, `duty_pct`, `paid_purse`, `paid_treasury`,
  `travel_runs`, `runs_left`, `last_run_id`, `status` (`in_transit | delivered | cancelled`), `cancel_reason`
  (`destination_left | destination_deleted`), `goods_returned`, `dispatch_op_id`, `finish_op_id`, `created_at`,
  `finished_at`, `finished_run_id`. UNIQUE `(dispatch_run_id, from_region_id, to_region_id, group_code)` — маркер
  идемпотентности отправки. Строки **хранятся** (история для будущей газеты), `purge_old` их не трогает; индекс
  `finished_at` — на случай будущей чистки.
- Откат: `DROP TABLE econ_caravans, econ_trade_pairs`. Перед откатом с караванами в пути поставить `caravans_enabled =
  0` и дождаться, пока все доедут, иначе их деньги останутся на «Караваны в пути».

Параметры пересчёта (JSON `econ_sim_settings.params`, без миграции, правятся `PUT /admin/economy/sim`):
`caravans_enabled` (1, 0…1; 0 = новых не отправлять, едущие доезжают), `caravan_surplus_share` (0.25, 0…1),
`caravan_purse_share` (0.25, 0…1), `caravan_treasury_food_share` (0.5, 0…1), `caravan_travel_domestic` (1, 1…8),
`caravan_travel_foreign` (2, 1…8), `caravan_min_value` (10, 1…1e6), `caravan_max_per_run` (200, 1…5000).

### Тик (3.2 / 3.7 / 3.8)

Проход `_caravan_pass` — **после квоты, до цикла регионов**, в плановых и ручных прогонах; сначала **прибытия**, потом
**отправки** (шаг регионов уже считает цены и потребление по запасу после караванов).
- **Прибытия:** каждый караван `in_transit` (кроме отправленных / продвинутых этим же прогоном) — своя транзакция.
  `runs_left > 1` → только `runs_left −= 1`, `last_run_id = run` (блокируется только строка каравана). Иначе —
  завершение: блокировки `econ_regions` обоих концов по возрастанию → их `econ_region_goods` → строка каравана; если
  какой-то из регионов уже прошёл этот прогон (возобновлённый прогон) → `runs_left = 0`, завершится в следующем.
  Назначение участвует (есть `Regions`, шаблон и население, строка товара) → **доставка**: `stock += units`,
  `caravan_delivery`. Иначе → **отмена**: товар возвращается в регион-отправитель (если у него есть `Regions` и строка
  товара; оба региона исчезли → товар списывается, `goods_returned = 0`, WARNING в лог), деньги — `caravan_cancel`.
  Запрет пары или «Набег»/«Бунт» едущий караван не останавливают.
- **Отправки:** снимок (участвующие регионы со страной, ещё не прошедшие этот прогон; товары; кошельки и казны;
  `inbound`; разрешённые пары; `merchants_halt` из `active_map` прохода событий) → `plan_caravans` → на каждый план
  своя транзакция: `econ_regions` обоих по возрастанию (оба участвуют и ещё не прошли прогон) → строка товара продавца
  → перепроверка маршрута (пошлина берётся текущая) → счета покупателя и `caravan_escrow` блокируются по возрастанию id
  → `clamp_dispatch` (не больше плана, продавец не ниже нормы, кошелёк/казна не больше плана и остатка) → INSERT
  `econ_caravans` (UNIQUE → «уже отправлен») → `stock −= units` → `caravan_dispatch`.
- Сбой одного каравана откатывает только его; в `econ_tick_runs.error` — `караваны — ошибка: <число>`. Сбой снимка →
  в этом прогоне отправок нет (прибытия идут). `RunSummary`: `caravans_dispatched, caravans_delivered,
  caravans_cancelled, caravans_failed, caravan_value`.

### Порядок блокировок (3.9, заменяет FEAT-191 3.12)

`econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) → econ_region_events (asc id) →
econ_caravans (asc id) → econ_mint_seasons → npc_shop_items (asc id) → econ_banks (asc region_id) → bank_deposits
(asc id) → bank_loans (asc id) → character_inventory (asc id) → characters (asc id) → econ_accounts (asc id)`.
Отправка: `econ_regions ×2 → econ_region_goods(продавец) → [INSERT econ_caravans] → econ_accounts`; завершение:
`econ_regions ×≤2 → econ_region_goods ×≤2 → econ_caravans → econ_accounts`; продвижение — только `econ_caravans`.
Это первая транзакция, блокирующая **два** региона, — только по возрастанию id. `econ_trade_pairs` не блокируется.

### Админ-API (3.11; префикс `/characters/admin/economy`)

| Метод и путь | Права | Описание |
|---|---|---|
| `GET /caravans/overview` | `economy:read` | `CaravanOverviewOut`: 8 параметров, `escrow {balance, expected, ok}`, `in_transit {count, value, duty}`, `last_run {run_id, dispatched, delivered, cancelled}` (последний завершённый прогон, null — прогонов нет), `countries [{country_id, name, participating_regions}]` (по имени), `pairs` — все неупорядоченные пары стран (`a < b`), нет строки → `is_enabled=false, duty_pct=10.0` |
| `PUT /caravans/pairs` | `economy:settings` | `TradePairIn {country_a ≥1, country_b ≥1, is_enabled, duty_pct 0…100}` → `TradePairOut`; пара нормализуется, `duty_pct` округляется до 2 знаков; 400 «Страна не может торговать сама с собой», 404 «Страна не найдена», 422 — границы. Действует на **новые** отправки (едущие хранят свою пошлину) |
| `GET /caravans?status=in_transit\|delivered\|cancelled\|all&region_id=&group_code=&limit=50&offset=0` | `economy:read` | `CaravanListOut {total, items}` новые сначала; `region_id` — отправитель **или** получатель; неизвестная группа → 400 «Неизвестная группа товаров»; `limit 1…200`; имена регионов / стран — LEFT JOIN (удалён → null) |

`GET /admin/economy/summary` — новые поля `totals.caravan_escrow`, `invariant.caravan_escrow_expected / _actual`.

### Карточка региона (3.12)

`GET /characters/economy/regions/{id}/card` — поле `caravans {incoming: [...], outgoing: [...]}` в обеих формах
(скрытая — пустые списки). Строка: `group_code, group_name, region_id, region_name, country_name (только чужая
страна), foreign, in_transit`. Источник — караваны региона в пути или доставленные за последние 24 ч
(`CARD_RECENT_HOURS`), без отменённых; одна строка на (группа, другой регион), «в пути» важнее; сначала в пути, затем
по порядку групп; не больше 6 (`CARD_MAX_LINES`) в списке; другой регион удалён → строка выпадает. **Без количеств,
цен и денег.**

## Guild orders (FEAT-193)

Этап 5в экономики: регион с нехваткой группы товаров выставляет заказ в «Гильдии торговцев»; игрок приносит любые
предметы этой группы к НПС с ролью `guild` в этом регионе и сразу получает марки из кошелька жителей (за еду —
доплата из казны) и немного опыта. Новых денег заказы не создают. Модули: чистый `app/econ_guild.py` (план заказов,
цена, приём, опыт), БД — `app/economy_guild_crud.py`, шаг тика — `econ_tick._process_region` (SAVEPOINT в конце) +
`econ_tick._guild_sweep`, роутер — `app/economy_api.py`.

### Пересчёт заказов (3.2 / 3.3)
- Внутри транзакции региона: открытые строки `econ_guild_orders` региона блокируются сразу после строк событий;
  **в самом конце шага** (после торговцев, перед строкой истории) SAVEPOINT считает бюджет и заказы по **итоговому**
  запасу, норме, `price_mult` и караванам в пути к региону (`econ_caravans in_transit`, вычитаются — решение 6).
- Бюджет на пересчёт (на строке `econ_regions`, не копится): `guild_budget = floor(max(0, кошелёк) ×
  guild_purse_share)`, `guild_food_budget = floor(max(0, казна) × guild_treasury_food_share)`.
- Заказ открыт ⇔ `guild_enabled = 1`, норма > 0, `запас + в пути < норма × guild_open_threshold_pct %`, объём
  `floor3(норма − запас − в пути)` (до **полной** нормы) × базовая цена × `price_mult` ≥ `guild_min_order_value` и
  есть бюджет (для еды — бюджет + еда-бюджет). Каждый пересчёт: открытая строка обновляется (`units_total =
  units_left` = новый объём, снимок `price_mult` / `markup_pct`, счётчики сданного копятся), новая — INSERT, лишняя —
  `closed` (`no_shortage | no_money | disabled`). Выполненная (`filled`) не переоткрывается — при сохранении нехватки
  открывается **новая** строка (история хранится).
- Сбой шага гильдии откатывает только SAVEPOINT (заказы и бюджет — прежние), регион всё равно проходит;
  `econ_tick_runs.error` — `гильдия — ошибка в регионах: <id>`. Повтор торговцев другим исполнителем
  (`DuplicateOperation`) пропускает и шаг гильдии. `RunSummary`: `guild_opened, guild_refreshed, guild_closed,
  guild_failures, guild_failed_region_ids, guild_sweep_failed`.
- **Уборка** `_guild_sweep` (после цикла регионов, до чеканки; одна короткая транзакция): регионы, вышедшие из
  экономики, — бюджеты в 0, их открытые заказы — `closed / region_left`; строки `econ_guild_xp_days` старше 7 дней
  удаляются. Ошибка — `гильдия — ошибка закрытия заказов`.
- Нет миграции 036 → шаг и уборка пропускаются.

### Цена за штуку (3.5, правка PM)
`offer = floor(item_base × price_mult(снимок заказа) × (1 + markup_pct(снимок)/100))`; если предмет продаёт какой-то
торговец региона — `offer = min(offer, floor(самая дешёвая цена продажи × 0,5))` (`econ_core.ask_discount_floor`);
`unit_price = max(лучшая цена скупки торговцами региона, offer)`; `≤ 0` → отказ. `item_base` — `items.price`, при 0 —
базовая цена группы. «Торговцы региона» — НПС с активными строками `npc_shop_items`, не мёртвые, чьё место
резолвится в регион (живые **и** legacy, например в подземелье региона, с множителем 1). Строка продажи — как в окне
магазина (`origin='player'` — только пока есть на складе, admin — и при 0). Формулы — общие `econ_core.shop_row_prices
/ shop_row_bid / merchant_buys_groups / effective_shop_stock` (те же, что у магазина locations-service). Чтение без
блокировок.

### Игрок у «Гильдии торговцев» (3.6 / 3.6a)
Роль НПС `guild`. Проверки — как у банкира / монетчика: JWT + свой персонаж игрока (403) → НПС есть / роль / жив
(404 / 409) → блокировка активности (POST, 409) → та же локация (400) → гейт FEAT-145 (POST, fail-closed 403/503) →
регион участвует и `guild_enabled = 1` (POST 409 «Гильдия не принимает заказы: …»; окно отвечает `working=false`).
Не принимаются: без группы / вне рынка (свиток, рецепт, легендарное+, админ-override) 400; квестовые
(`quest_objectives collect|deliver`) 400; нет открытого заказа группы 409; цена ≤ 0 400. Только обычные стопки.

Сдача — одна транзакция (роутер коммитит): `econ_regions` FOR UPDATE → повтор `guild:{character}:{request_id}` (409
«Операция уже выполнена») → правила → `econ_region_goods(группа)` → открытая строка заказа по `open_key` → цена →
деньги (`min(бюджет, баланс)`, без блокировки счетов) → `accept`: целые штуки, пока заказу что-то нужно (последняя
может перекрыть), не больше денег; 0 → 409 «У жителей сейчас нет денег…» → строка дня опыта FOR UPDATE → списание
из `character_inventory` (проверка «не хватает» — по запрошенному числу) → `stock += штуки × units_per_item`, заказ
уменьшается (0 → `filled`), бюджеты уменьшаются → проводка `guild_order` (последний денежный шаг; `InsufficientFunds`
→ 409 «Деньги жителей изменились…») → `character_attributes.passive_experience += опыт` → COMMIT → проверка уровня.
Частичный приём — 200 с `partial=true` и причиной. Опыт: `floor(марки × 0,1)` (0,05 — если предмет продаёт торговец
региона), дневной лимит `guild_xp_daily_cap` базового опыта на персонажа за UTC-сутки (`econ_guild_xp_days`), книга
опыта квестов (`XP_SOURCE_QUEST`) умножает после лимита; множитель берётся по HTTP **до** транзакции (fail-open 1.0).
Нет строки `character_attributes` → опыт 0, сдача проходит. Всё — в одной транзакции с проводкой (повтор / сбой
откатывает и опыт).

Кросс-владение: character-service пишет `character_inventory` (inventory-service) и
`character_attributes.passive_experience` (character-attributes-service) напрямую SQL — прецеденты чеканки и
`add_rewards_to_character`.

### Книга счетов
| Тип | Ноги | Ключ |
|---|---|---|
| `guild_order` | `population_purse(R) → character` + (только еда) `region_treasury(R) → character`, `LEG_MAIN`, `apply_tax=False` | `guild:{character_id}:{request_id}` |

`econ_core.GUILD_OP_TYPES` ⊂ `OP_TYPES`, не источник, без комментария. Метаданные: `order_id, npc_id, item_id,
item_name, group, quantity, requested, unit_price, units, price_mult, markup_pct, best_bid, cheapest_ask, paid_purse,
paid_treasury, xp_base, xp, xp_rate, xp_multiplier`. battle-pass считает её «заработанным золотом».

### Таблицы (миграция `036_econ_guild_orders`, без FK, без ENUM, перезапускаемая)
- `econ_guild_orders` — одно «открытие» заказа: `region_id, group_code, open_key` (`r<регион>:<группа>` пока
  открыт, иначе NULL; UNIQUE → не больше одного открытого заказа на пару), `status open|filled|closed`,
  `close_reason filled|no_shortage|no_money|disabled|region_left`, `units_total / units_left / units_filled`,
  `price_mult, markup_pct` (снимок), `pieces, paid_total, paid_treasury, hand_ins`, `opened/last/closed_run_id`,
  `opened_at, updated_at, closed_at`.
- `econ_guild_xp_days (character_id, day)` PK, `xp` — базовый опыт гильдии за UTC-день.
- `econ_regions.guild_budget`, `guild_food_budget` BIGINT NOT NULL DEFAULT 0.
- Откат: удалить две колонки и обе таблицы (проводки и выданный опыт остаются).

### Параметры (`econ_sim_settings.params`, `PUT /admin/economy/sim`, право `economy:settings`)
`guild_enabled` (1, 0…1), `guild_markup_pct` (20, 0…200), `guild_open_threshold_pct` (80, 1…100),
`guild_min_order_value` (50, 1…1e6), `guild_purse_share` (0.25, 0…1), `guild_treasury_food_share` (0.25, 0…1),
`guild_xp_per_mark` (0.1, 0…10), `guild_xp_per_mark_merchant_items` (0.05, 0…10), `guild_xp_daily_cap` (200, 0…1e6;
0 = без опыта). Наценка и множитель цены берутся из снимка заказа — изменение наценки действует со следующего пересчёта.

### Порядок блокировок (3.7, заменяет FEAT-192 3.9)
`econ_regions (asc region_id) → econ_region_goods (asc region_id, group_code) → econ_region_events (asc id) →
econ_caravans (asc id) → econ_guild_orders (asc id) → econ_guild_xp_days → econ_mint_seasons → npc_shop_items (asc id)
→ econ_banks (asc region_id) → bank_deposits (asc id) → bank_loans (asc id) → character_inventory (asc id) → characters
(asc id) → econ_accounts (asc id) → character_attributes`. Шаг региона: `… → события → заказы → npc_shop_items →
characters → econ_accounts` (бюджет — на уже заблокированной строке региона). Сдача: `econ_regions →
econ_region_goods(группа) → econ_guild_orders → econ_guild_xp_days → character_inventory → characters → econ_accounts →
character_attributes`; `npc_shop_items` / `characters` торговцев читаются без блокировок. INSERT заказов — только под
блокировкой `econ_regions` региона; строка дня опыта создаётся в отдельной короткой транзакции.

### API (префикс `/characters`)
| Метод и путь | Доступ | Описание |
|---|---|---|
| `GET /economy/guild/npc/{npc_id}?character_id=` | JWT, свой персонаж | `GuildView {npc_id, npc_name, region_id (null — нет региона), region_name, working, closed_reason, markup_pct, orders[{order_id, group_code, group_name, is_food, units_total, units_left, filled_pct, payable}], offers[{item_id, name, image, group_code, order_id, have, unit_price, units_per_item, max_accept, capped_by_merchants, xp_rate}], refused[{item_id, name, image, group_code, have, reason}], xp{per_mark, per_mark_merchant_items, daily_cap, left_today, multiplier}, wallet}`; без чисел бюджета |
| `POST /economy/guild/npc/{npc_id}/hand-in` | JWT + гейт | `GuildHandInIn {character_id ≥1, item_id ≥1, quantity 1…10000, request_id [A-Za-z0-9-]{8,64}}` → `GuildActionOut {message, operation_id, quantity, requested, partial, unit_price, total, xp, xp_capped, wallet, view}`; `message` уже содержит «и N опыта» |
| `GET /admin/economy/guild?status=open/filled/closed/all&region_id=&group_code=&limit=50&offset=0` | `economy:read` | `GuildAdminOut {params (9), totals {open, units_left_value, paid_last_7d, hand_ins_last_7d, xp_last_7d}, regions [{region_id, region_name, guild_budget, guild_food_budget, open_orders, masters [{npc_id, name, npc_status, location_name}]}], total, items [...]}`; `status=closed` — закрытые **и** выполненные; неизвестная группа → 400; `limit 1…200` |
| `GET /economy/regions/{id}/card` | публично | новое поле `guild_wants [{group_code, group_name}]` (обе формы; только при живом НПС гильдии в регионе, открытый заказ с остатком и бюджетом; до 12; без чисел) |

## Social classes and the wealth norm (FEAT-194)

У каждого участвующего региона — доли трёх классов жителей: бедные / зажиточные / богатые (сумма 1). Состав влияет на
спрос, налог, стабильность и покупательную способность, задаёт **норму богатства** (нормальные деньги жителей) и
медленно дрейфует сам. Деньги не сжигаются: излишок сверх нормы остывает налогом с накоплений в казну. Модули: чистый
`app/econ_classes.py` (формулы), класс-путь в `econ_sim.simulate_region`, тик — `econ_tick`, API — `economy_sim_crud`.

### Нормировка и выключатель
- Регион «с классами» ⇔ `classes_enabled = 1` **и** три колонки долей не NULL. Иначе вся математика — прежняя,
  инструкция в инструкцию (`wealth_norm` = `starting_purse` = `purse_start_days` дней нужд по базовым ценам).
- Все классовые множители нормированы на **долю шаблона по умолчанию** (`econ_region_templates.class_*`): регион с
  долями шаблона считает множитель ровно 1.0 → выкатка не двигает спрос, нормы, цены и подоходный налог. Правка долей
  шаблона перебалансирует все его регионы; правка долей одного региона двигает только его спрос.

### Формулы (раздел 3 фичи)
- **Спрос** (3.3): у группы товаров веса на душу `class_demand_poor/_middling/_rich`; `w_kg = s_k c_kg / Σ base_j c_jg`,
  `F_g = Σ s_k c_kg / Σ base_j c_jg` (ровно 1.0 на шаблонной смеси; нулевой знаменатель → 1). Спрос группы, норма
  запаса (часть домохозяйств) — ×`F_g`; часть класса `D_kg = D_g × w_kg / F_g`.
- **Норма богатства** (3.4): `Σ_k class_norm_days_k × (нужды класса k в день по базовым ценам)`; по умолчанию 3 / 7 / 21
  дня → столица ≈ 10 дней всех нужд, сельская округа ≈ 6. Пишется в `econ_regions.wealth_norm` каждым пересчётом,
  «Заполнить» и «Применить шаблон»; цель кошелька в «Заполнить» = норма.
- **Покупательная способность** (3.5): кошелёк делится между классами ∝ их частям нормы; `afford_k = деньги_k /
  (стоимость_k × afford_days)`; запас группы раздаётся богатые → зажиточные → бедные, поэтому дороговизна и нехватка бьют
  по бедным первыми. Голод по классам: потреблено / (норма еды × вес класса). Потребление денег не двигает (как раньше).
- **Налоги** (3.6): подоходный ×`Σ s_k t_k / Σ base_k t_k` (веса 0.3 / 1.0 / 2.0); **налог с накоплений** `floor(
  wealth_tax_rate × max(0, кошелёк после подоходного − норма))` (0.02 за пересчёт). Оба идут **одной ногой** `purse →
  region` операции `region_tick` (книга сама добавляет 10 % стране с суммы); новой операции и ключа нет, в metadata —
  `wealth_tax`. `treasury_target` и зарплаты считаются только от подоходного налога — налог с накоплений возвращается
  в кошелёк медленным выпуском излишка казны (`treasury_release_ticks`), а не в тот же пересчёт.
  `econ_regions.last_tax` — подоходный, `last_wealth_tax` — с накоплений.
- **Стабильность** (3.7): минус `class_stab_poor_w × max(0, бедные − порог)`, `class_stab_poor_hunger_w × бедные ×
  голод бедных`, `class_stab_rich_tax_w × богатые × max(0, ставка − class_stab_rich_free_tax)`; на шаблонных долях = 0.
- **Мобильность** (3.8): сигнал `mob_w_prosperity·(достаток−50)/50 + mob_w_money·clamp(r−1) +
  mob_w_stability·clamp((стаб−50)/50) − mob_w_hunger·clamp(голод/0.15)` (r = кошелёк / норма), мёртвая зона
  `mob_dead_zone`; вверх `mob_rate_up` (бедные → зажиточные, зажиточные → богатые ×`mob_rich_factor`), вниз
  `mob_rate_down`. Доли не выталкиваются за `class_share_min / class_share_max`; хранение — бедные / богатые с 6 знаками,
  зажиточные = 1 − бедные − богатые (сумма ровно 1). Сдвиг пересчёта (события + мобильность) — `class_dpoor / class_drich`.
- **Квота сезона** (3.9): нехватка региона `max(0, wealth_norm + treasury_target − кошелёк − казна)` (сохранённые
  колонки + текущие балансы, без блокировок). Квота делится только между регионами с нехваткой ∝ нехватке
  (`econ_mint.split_by_deficit`, наибольший остаток, каждому ≤ его нехватки), выдаётся `min(сумма, Σ нехваток)`, остаток
  не выдаётся. Никого ниже нормы → ничего не проводится, следующий пересчёт сезона проверяет снова (ключ
  `season_quota:p<период>` — единственный маркер). В metadata — `requested`, `deficits`.
- **Гранты страны** (3.10): `grant_deficit_share` (0.25) пула — регионам с нехваткой ∝ нехватке (не больше нехватки),
  остальное — по населению; никого ниже нормы → весь пул по населению.

### Событие `class_shift` (3.15)
Разовый эффект `{"type": "class_shift", "delta": d}`, d ∈ [−0.3, 0.3]: d > 0 — доля d бедных в зажиточные и
d × `mob_rich_factor` зажиточных в богатые; d < 0 — вниз. Применяется вместе с другими разовыми эффектами (один раз,
`applied_at`), только если у региона есть классы; `outcome.class_shift = {before: [p, m, r], after: [p, m, r]}`.
Миграция 037 дописала его в Бунт −0.03, Набег −0.02, Чума −0.02, Богатая жила +0.02, Ярмарка +0.01 и добавила плохое
событие «Разорение» (`ruin`: −0.06, доход казны ×0.85, достаток −1, стабильность −0.5, 5–10 дней, любой шаблон).

### Таблицы (миграция `037_econ_social_classes`, без FK, без ENUM, перезапускаемая)
- `econ_region_templates.class_poor / class_middling / class_rich` DECIMAL(6,4) (по умолчанию 0.45 / 0.45 / 0.10;
  сид: столица 35/45/20, порт 45/42/13, шахтёрский 55/37/8, аграрный 55/38/7, лесной 50/42/8, магический 30/50/20,
  крепость 45/48/7, сельская округа 60/35/5).
- `econ_regions.class_poor / class_middling / class_rich` DECIMAL(9,6) NULL (NULL = нет классов; заполнены из шаблона),
  `class_dpoor / class_drich` DECIMAL(9,6), `wealth_norm`, `last_wealth_tax` BIGINT.
- `econ_region_history.class_* / wealth_norm / wealth_tax` (NULL у старых строк).
- `econ_goods_groups.class_demand_poor / _middling / _rich` DECIMAL(6,3) (сид — таблица 3.3: еда 1/1/1.2 … украшения
  0.05/0.6/6).
- Откат: удалить колонки, убрать `class_shift` из эффектов шаблонов, удалить `ruin` (или выключить, если есть экземпляры).

### Параметры (`PUT /admin/economy/sim`, право `economy:settings`; без сид-миграции)
`classes_enabled` (1, 0…1), `class_norm_days_poor/_middling/_rich` (3 / 7 / 21, 0…365), `wealth_tax_rate` (0.02,
0…0.2), `class_tax_w_poor/_middling/_rich` (0.3 / 1 / 2, 0…5), `class_stab_poor_threshold` (0.6, 0…1),
`class_stab_poor_w` (40, 0…500), `class_stab_poor_hunger_w` (50, 0…500), `class_stab_rich_free_tax` (0.12, 0…1),
`class_stab_rich_tax_w` (100, 0…2000), `mob_rate_up` (0.001, 0…0.05), `mob_rate_down` (0.0015, 0…0.05),
`mob_rich_factor` (0.5, 0…1), `mob_dead_zone` (0.1, 0…0.9), `mob_w_prosperity / _money / _stability / _hunger`
(0.4 / 0.4 / 0.2 / 1, 0…5), `class_share_min` (0.02, 0…0.3) < `class_share_max` (0.9, 0.4…1) — иначе 400 «Нижняя
граница доли класса должна быть меньше верхней», `grant_deficit_share` (0.25, 0…1).

### API (префикс `/characters`)
| Метод и путь | Изменение |
|---|---|
| `GET /admin/economy/regions` | элемент + `class_poor, class_middling, class_rich` (float \| null), `class_base {poor, middling, rich} \| null` (доли шаблона), `class_dpoor, class_drich` (сдвиг последнего пересчёта), `wealth_norm`, `last_wealth_tax`, `money_vs_norm` (кошелёк / норма \| null) |
| `GET /admin/economy/regions/{id}` | + `classes`: `null` или `{classes: {poor\|middling\|rich: {share, base_share, norm_days, norm_per_resident, money_per_resident, needs_per_resident_day, afford}}, wealth_norm, money_norm, deficit, r}` (на одного жителя симуляции, нужды — по текущим ценам) |
| `PUT /admin/economy/regions/{id}` | необязательные `class_poor, class_middling, class_rich` (0…1, иначе 422): все три или ни одной (400 «Укажите все три доли»), сумма 1 ± 0.001 (400 «Сумма долей должна быть 100 %»); хранятся бедные / богатые с 6 знаками, зажиточные = остаток. Не переданы — сохраняются; строка без долей с шаблоном получает доли шаблона |
| `POST /admin/economy/regions/{id}/apply-template` | ещё сбрасывает доли к шаблону, обнуляет сдвиг, пересчитывает `wealth_norm` |
| `POST /admin/economy/regions/fill` | тело + `reset_classes` (bool, false); ответ + `classes_reset [region_id]` (сброшены к шаблону или получили доли впервые); цель кошелька = норма богатства |
| `GET /admin/economy/regions/{id}/history` | строки + `class_poor, class_middling, class_rich, wealth_norm, wealth_tax` (null у старых) |
| `GET/PUT /admin/economy/templates[/{code}]` | + `class_poor, class_middling, class_rich` (PUT: необязательны, все три или ни одной, хранятся с 4 знаками) |
| `GET/PUT /admin/economy/goods-groups[/{code}]` | + `class_demand_poor, class_demand_middling, class_demand_rich` (PUT: необязательны, 0…20, None — сохраняются) |
| `GET /economy/regions/{id}/card` | при классах (включены и доли есть): `classes {state: poor\|modest\|wealthy\|rich, label: «Скромный край, много бедняков», bar {poor, middling, rich: few\|some\|many}}`; `phrases[0]` = `classes.label`; `prosperity.label` — без прилагательного («Город процветает» / «живёт в достатке» / «живёт скромно» / «в упадке»), в фразы добавляется только «процветает» / «в упадке». Без классов карточка прежняя; чисел нет |

Пороги карточки: индекс = зажиточные × 0.5 + богатые; < 0.25 бедный, < 0.32 скромный, < 0.40 зажиточный, иначе
богатый. Хвост «, много бедняков» при бедных ≥ 0.5 (если не «бедный»), иначе «, много богачей» при богатых ≥ 0.18 (если
не «богатый»). Полоска: бедные / зажиточные few < 0.30 ≤ some < 0.50 ≤ many, богатые few < 0.08 ≤ some < 0.18 ≤ many.
