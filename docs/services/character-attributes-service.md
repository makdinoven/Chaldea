# character-attributes-service

**Порт:** 8002
**Технологии:** FastAPI, SQLAlchemy (sync), PyMySQL, httpx
**Путь:** `/home/dudka/chaldea/services/character-attributes-service/`

## Назначение

Управление боевыми атрибутами персонажей: здоровье, мана, энергия, стамина, сила, ловкость, интеллект и т.д. Система прокачки через stat points. Модификаторы от экипировки.

## Структура файлов

```
character-attributes-service/app/
├── main.py               # FastAPI app, 8 эндпоинтов (440 строк)
├── models.py             # CharacterAttributes модель (77 строк)
├── schemas.py            # Pydantic схемы (116 строк)
├── crud.py               # 3 CRUD-функции
├── config.py             # Настройки
├── database.py           # SQLAlchemy подключение
├── rabbitmq_consumer.py  # ЗАКОММЕНТИРОВАН
└── requirements.txt
```

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/attributes/` | Создать атрибуты для персонажа |
| GET | `/attributes/{character_id}` | Получить все атрибуты |
| GET | `/attributes/{character_id}/passive_experience` | Пассивный опыт |
| POST | `/attributes/{character_id}/upgrade` | Прокачать статы (тратит stat points) |
| POST | `/attributes/{character_id}/apply_modifiers` | **internal** (FEAT-167): применить модификаторы (экипировка/баффы) |
| POST | `/attributes/{character_id}/recover` | **internal** (FEAT-167): восстановить ресурсы (health/mana/energy/stamina) |
| PUT | `/attributes/{character_id}/active_experience` | **internal** (FEAT-167): изменить активный опыт |
| PUT | `/attributes/{character_id}/passive_experience` | **internal** (FEAT-167): изменить пассивный опыт |
| POST | `/attributes/{character_id}/consume_stamina` | **internal** (FEAT-167): потратить стамину (с блокировкой строки) |
| POST | `/attributes/{character_id}/refund_stamina` | **internal** (FEAT-167): вернуть стамину (FEAT-128) |
| GET | `/attributes/{character_id}/rest-status` | FEAT-164: состояние восстановления в покое и активная сытость |
| POST | `/attributes/internal/{character_id}/satiety` | FEAT-164, internal: применить сытость (вызывает inventory-service `/eat-food`) |
| POST | `/attributes/internal/settle-regen` | FEAT-164, internal: досчитать восстановление для списка персонажей (до 50 id) |

## Аутентификация изменяющих эндпоинтов (FEAT-167)

Шесть изменяющих эндпоинтов доступны **только для межсервисных вызовов** и
закрыты зависимостью `verify_internal_token` (`app/auth_http.py`, копия
`character-service/app/auth_http.py`):

`POST /{id}/apply_modifiers`, `POST /{id}/recover`,
`PUT /{id}/active_experience`, `PUT /{id}/passive_experience`,
`POST /{id}/consume_stamina`, `POST /{id}/refund_stamina`.

- Требуется заголовок `X-Internal-Token` со значением `INTERNAL_SERVICE_TOKEN`.
- **Fail-closed:** пустой/не заданный `INTERNAL_SERVICE_TOKEN` в сервисе →
  `503 «Internal service token не настроен»` для любого запроса.
- Неверный или отсутствующий заголовок → `401 «Недействительный internal token»`
  (значение полученного заголовка не логируется и не возвращается).
- Nginx вторым слоем отдаёт `403` на эти шесть путей извне.
- **GET-эндпоинты не закрыты специально:** `GET /attributes/{id}` и
  `GET /attributes/{id}/rest-status` доигрывают восстановление FEAT-164 и
  читаются battle-service на каждой атаке, skills-service, character-service и
  профилем игрока. Так же не тронуты `POST /{id}/upgrade` (JWT),
  `/attributes/admin/*` (RBAC) и `/attributes/internal/*` (пока только nginx).

Вызывающие (все посылают заголовок): inventory-service (apply_modifiers,
recover), locations-service (consume/refund stamina, passive_experience),
dungeon-service (consume_stamina, recover), skills-service
(active_experience), party-service (active/passive_experience).

### Дополнение (FEAT-167, задача #17) — ещё два закрытых роута

Тем же пушем закрыты два предсуществующих отверстия того же класса, найденные
при ревью FEAT-167. Оба лежали **вне** префикса `/attributes/internal/`, поэтому
nginx их не резал, и ни одной зависимости в сервисе у них не было:

| Роут | Было | Стало |
|---|---|---|
| `POST /attributes/cumulative_stats/increment` | анонимный запрос через gateway → `200 «Stats updated»`; накручивал `pve_kills`, `pvp_wins`, `total_damage_dealt`, серии побед **и открывал перки** (в ответе `newly_unlocked_perks`) | `Depends(verify_internal_token)` |
| `POST /attributes/` (создание строки атрибутов) | анонимный запрос доходил до обработчика (`422` по схеме, а не `401`) | `Depends(verify_internal_token)` |

Поведение и тексты ошибок те же, что у шести роутов выше (401 / 503 fail-closed).

Вызывающие `cumulative_stats/increment` (все посылают заголовок):
battle-service (итоги боя), locations-service (посты, перемещение, лавка NPC,
квесты — семь мест через один хелпер `_track_cumulative_stats`),
inventory-service (крафт и сбор), skills-service (`skills_used` при улучшении
навыка). Вызывающий `POST /attributes/` — только character-service:
`crud.send_attributes_request` (создание персонажа — **хард-фейл**, и создание
NPC из админки) и `crud._sync_send_attributes_request` (спавн моба).

**Не тронут** `GET /attributes/{character_id}/cumulative_stats` — это чтение,
его использует профиль.

Nginx вторым слоем: точные блоки `location = /attributes/cumulative_stats/increment`
и `location = /attributes/` с `limit_except GET HEAD` в обоих конфигах. Именно
точное совпадение — под префиксом `/attributes/` живут все игровые роуты.

## Восстановление в покое и сытость (FEAT-164)

Логика — `app/regen.py`, константы — `app/constants.py` (`REGEN_PERCENT_PER_HOUR`, `SATIETY_DURATION_HOURS`, `SATIETY_REGEN_BONUS_BY_RARITY`).

- **Скорость:** 5% от максимума в час реального времени для здоровья, маны, энергии и выносливости; не выше максимума.
- **Лениво, без фоновых задач:** `settle_regen(db, attr)` вызывается под блокировкой строки (`with_for_update`) во всех путях чтения/записи: `GET /{id}`, `GET /{id}/rest-status`, `recover`, `apply_modifiers`, `consume_stamina`, `refund_stamina`, `upgrade`, `PUT /admin/{id}`, `internal/{id}/reconcile-perks`, `internal/{id}/satiety`, `internal/settle-regen`. Ответ `GET /{id}` не изменился (новые колонки не отдаются).
- **Учёт времени:** `character_attributes.regen_anchor_at` — момент последнего пересчёта (NULL = часы ещё не запущены; первый пересчёт запускает их без ретро-лечения). `regen_carry_*` — дробный остаток на ресурс, поэтому частые чтения не «съедают» восстановление.
- **Занятость (восстановление не идёт):** из общей БД берутся интервалы — бой (`battle_participants.joined_at`/`battles.created_at` … `dropped_out_at` или «сейчас» для активного боя), подземелье (только `dungeon_sessions.status='active'`, `started_at` … `finished_at`; лобби `forming` = покой), сбор (`gathering_sessions.started_at` … `finished_at`/`complete_at`). Время покоя = окно минус объединение интервалов. `now`/начало окна передаются bind-параметрами. Ошибка чтения интервалов логируется (ERROR), восстановление не начисляется, якорь не сдвигается.
- **Конец боя:** battle-service при синхронизации ресурсов ставит `regen_anchor_at = UTC_TIMESTAMP()`.
- **Мобы/NPC** (`characters.is_npc = 1`) и персонажи без строки в `characters` пропускаются.
- **Сытость** — таблица `character_satiety` (одна строка на персонажа, `UNIQUE(character_id)`): `item_id`, `source_item_name`, `rarity`, `regen_bonus`, `modifiers` (JSON), `started_at`, `expires_at` (24 ч, naive UTC). Бонус к восстановлению по редкости: обычная +50%, редкая +100%, эпическая +150%, легендарная +200%. Пока сытость активна, новая еда → 409 «Вы уже наелись». Модификаторы еды добавляются в базовые колонки как у экипировки (без производных бонусов) и вычитаются при первом пересчёте после `expires_at` (строка удаляется в той же транзакции), затем выполняется reconcile перков. Если сытость закончилась посреди окна, до `expires_at` считается с бонусом, после — без.

### `GET /attributes/{id}/rest-status`
```json
{"character_id": 12, "is_resting": true, "busy_reason": null,
 "base_regen_percent_per_hour": 5.0, "regen_percent_per_hour": 10.0,
 "satiety": {"item_id": 345, "source_item_name": "Жаркое из кабана", "rarity": "rare",
             "regen_bonus_percent": 100, "modifiers": {"strength": 2},
             "started_at": "...", "expires_at": "...", "remaining_seconds": 72000}}
```
`busy_reason`: `null | battle | dungeon | gathering`. NPC → `is_resting=false`, `satiety=null`. 404 «Атрибуты персонажа не найдены».

### `POST /attributes/internal/{id}/satiety`
Тело: `{item_id, source_item_name, rarity, modifiers: {...}, recovery: {health_recovery, mana_recovery, energy_recovery, stamina_recovery}}`. Ответ 201 `{satiety, stats_changed}`. Ошибки: 400 «Недопустимая редкость еды» / недопустимые модификаторы / отрицательное восстановление; 404; 409 «Вы уже наелись». Одна транзакция: блокировка → пересчёт → проверка → модификаторы → мгновенное восстановление → запись сытости.

### `POST /attributes/internal/settle-regen`
Тело `{"character_ids": [1, 2]}` (1..50 уникальных) → `{"settled": [...], "missing": [...]}`; каждый id в своей короткой транзакции. Вызывается party-service перед чтением ресурсов участников.

**Откат миграции 008:** перед `downgrade` снять активные бонусы: `UPDATE character_satiety SET expires_at = UTC_TIMESTAMP();`, затем `POST /attributes/internal/settle-regen` для всех `character_id` из таблицы.

## Модель CharacterAttributes

### Ресурсы (current + max)
- `health` (base 100, +10 за point)
- `mana` (base 75, +10 за point)
- `energy` (base 50, +5 за point)
- `stamina` (base 50, +5 за point)

### Прокачиваемые статы
- `strength` -> +0.1 к res_physical
- `agility` -> +0.1 к dodge
- `intelligence` -> +0.1 к res_magic
- `endurance` -> +0.1 к res_effects
- `luck` -> +0.1 к critical_hit_chance и dodge
- `charisma` -> (без автоматического бонуса)

### Боевые характеристики
- `damage`, `dodge` (base 5.0), `critical_hit_chance` (base 20.0), `critical_damage` (base 125)

### Сопротивления (13 типов, float)
- `res_effects`, `res_physical`, `res_catting`, `res_crushing`, `res_piercing`
- `res_magic`, `res_fire`, `res_ice`, `res_watering`, `res_electricity`
- `res_sainting`, `res_wind`, `res_damning`

### Уязвимости (13 типов, float)
- `vul_effects`, `vul_physical`, `vul_catting`, ... (аналогично сопротивлениям)

### Опыт
- `passive_experience`, `active_experience`

## Система прокачки (upgrade)

1. HTTP -> character-service: получить stat_points персонажа
2. Проверить достаточно ли points
3. Применить множители за каждый вложенный point
4. HTTP -> character-service: списать stat_points
5. Используется `with_for_update()` для блокировки строки (race condition protection)

## Коммуникация

### HTTP (исходящие)
- `character-service:8005` -> GET `/characters/{id}/full_profile` (stat points)
- `character-service:8005` -> PUT `/characters/internal/{id}/deduct_points` (списание points, заголовок `X-Internal-Token`)
- `character-service:8005` -> POST `/characters/internal/{id}/logs` (запись в журнал персонажа, заголовок `X-Internal-Token`)

### RabbitMQ
Полностью закомментирован.

## Известные проблемы

1. **Опечатки в названиях полей** - `res_catting` (вероятно `res_cutting`), `res_watering` (вероятно `res_water`), `res_sainting` (вероятно `res_holy`)
2. **Нет валидации в apply_modifiers** - принимает произвольный dict, может установить отрицательные значения
3. **Нет constraints в БД** - current_* поля могут стать отрицательными
4. **Float precision** - сопротивления используют Float без явного округления
5. **Неиспользуемые URL** - INVENTORY_SERVICE_URL, SKILLS_SERVICE_URL, USER_SERVICE_URL определены, но не используются
