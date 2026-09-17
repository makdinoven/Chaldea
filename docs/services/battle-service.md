# battle-service

**Порт:** 8010
**Технологии:** FastAPI (async), SQLAlchemy (async, aiomysql), Motor (MongoDB async), aioredis, Celery, httpx
**Путь:** `/home/dudka/chaldea/services/battle-service/`

## Назначение

Пошаговая боевая система. Создание боёв, управление ходами, расчёт урона, эффекты, кулдауны. Самый сложный сервис в системе.

## Структура файлов

```
battle-service/app/
├── main.py              # FastAPI app, 5 роутов, основная боевая логика
├── models.py            # SQLAlchemy модели (Battle, BattleParticipant, BattleTurn)
├── schemas.py           # Pydantic схемы
├── battle_engine.py     # Расчёт урона, кулдауны, модификаторы
├── buffs.py             # Система эффектов (баффы/дебаффы)
├── config.py            # Настройки
├── database.py          # Async SQLAlchemy engine
├── crud.py              # CRUD-операции
├── redis_state.py       # Redis state management
├── mongo_client.py      # Motor AsyncIO connection (singleton)
├── mongo_helpers.py     # Сохранение/загрузка снапшотов
├── character_client.py  # HTTP клиент к character-service
├── inventory_client.py  # HTTP клиент к inventory-service
├── skills_client.py     # HTTP клиент к skills-service
├── tasks.py             # Celery задача save_log
└── requirements.txt
```

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/battles/` | Создать бой (список участников с командами) |
| GET | `/battles/{battle_id}/state` | Текущее состояние боя + снапшот |
| POST | `/battles/{battle_id}/action` | Выполнить ход (атака/защита/поддержка + предмет) |
| GET | `/battles/{battle_id}/logs` | Логи всех ходов |
| GET | `/battles/{battle_id}/logs/{turn_number}` | Логи конкретного хода |
| POST | `/battles/admin/{battle_id}/force-finish` | Принудительно завершить бой (`battles:manage`) |
| POST | `/battles/admin/{battle_id}/freeze` | Заморозить бой с причиной (`battles:manage`, FEAT-163) |
| POST | `/battles/admin/{battle_id}/unfreeze` | Разморозить бой (`battles:manage`, FEAT-163) |

## Хранение данных

### MySQL (постоянное)
- **battles** - id, status (pending/in_progress/finished/forfeit), is_paused, `pause_reason`, `paused_by_admin`, timestamps
- **battle_participants** - battle_id, character_id, team, `dropped_out_at`, `joined_at` (FEAT-164, миграция `007_participant_joined_at`; ставится при создании боя и при одобрении заявки на вступление, NULL у старых строк)
- **battle_turns** - battle_id, actor_id, turn_number, attack/defense/support_rank_id, item_id, deadline

### MongoDB (логи)
- **battle_logs** - battle_id, turn_number, events[], timestamp
- **battle_snapshots** - battle_id, participants[] (полные данные на начало боя)

### Redis (runtime state)
- `battle:{id}:state` - JSON: participants (hp/mana/energy/stamina/cooldowns/active_effects), turn_order, turn_number, next_actor (TTL: 48h)
- `battle:{id}:snapshot` - кэш снапшота из MongoDB (TTL: 24h)
- `battle:{id}:turns` - ZSET номеров ходов
- `battle:deadlines` - ZSET дедлайнов: `{battle_id}:{participant_id}` -> unix_timestamp. **Читается свипером** (FEAT-163), держит не более одной записи на бой
- `battle:deadline_sweeper:lock` - аренда свипера (advisory, `main.py:4962`)
- `battle:{id}:timeout:lock` - мьютекс обработки таймаута конкретного боя (TTL 60 с)
- Pub/Sub `battle:{id}:your_turn` - оповещение о следующем ходе

## Поток боя

### Создание боя (POST `/`)
1. Для каждого участника: HTTP -> attributes, character, skills, inventory
2. Собрать полный снапшот (характеристики, навыки, быстрые слоты, экипировка)
3. Сохранить снапшот в MongoDB
4. Закэшировать снапшот в Redis
5. Инициализировать state в Redis (hp, mana, energy, stamina, cooldowns={}, effects={})
6. Создать записи в MySQL (battle + participants)
7. Вернуть battle_id, next_actor, deadline

### Выполнение хода (POST `/{id}/action`)
1. Загрузить state из Redis
2. Проверить очерёдность хода
3. Уменьшить длительность эффектов и кулдаунов
4. Валидировать владение навыками
5. Обработать SUPPORT-навык (эффекты на себя и врага)
6. Обработать DEFENSE-навык (эффекты на себя и врага)
7. Использовать предмет из быстрого слота (восстановление ресурсов)
8. Обработать ATTACK-навык + расчёт урона
9. Списать ресурсы (mana, energy) за использованные навыки
10. Установить кулдауны
11. Записать ход в MySQL
12. Обновить state в Redis
13. Pub/Sub -> оповестить следующего игрока
14. Celery task -> сохранить лог хода в MongoDB

### Формула урона (compute_damage_with_rolls)
```
1. base = главная характеристика класса (CLASS_MAIN_ATTRIBUTE[class_id])
          + attrs["damage"]                    # база: перки, броня, украшения, баффы/еда
          + weapon["effective_damage"]         # урон оружия выбранного слота (0, если слот пуст)
2. damage_type -> определить тип (или взять с оружия если "all")
3. raw_damage = base + skill_damage_amount
4. raw_damage *= (1 + percent_buffs / 100)
5. Roll dodge -> если попал, урон = 0
6. Roll hit_chance -> если промах, урон = 0
7. Roll crit -> если крит, raw_damage *= crit_multiplier
8. final = raw_damage * (1 - resists / 100)
```

### Три значения урона и `effective_damage` (FEAT-167)

Урон оружия **не входит** в характеристику `damage` — она хранит только «базу»
(характеристики, перки, броня и украшения с их заточкой и камнями, баффы, еда).
Урон конкретного оружия считает **inventory-service** и отдаёт его полем
`effective_damage` в `GET /inventory/{character_id}/equipment`
(шаблонный `damage_modifier` + заточка + вставленные камни этого оружия; `0.0`,
если предмет сломан — `max_durability > 0` и `current_durability <= 0`).

`fetch_weapons()` (`battle_engine.py`) прикрепляет `effective_damage` слота к
словарю оружия, а `compute_damage_with_rolls` берёт урон оружия **только** из
этого поля. Шаблонный `items.damage_modifier` в battle-service больше не читается
— именно его повторное сложение давало двойной урон (25 без меча / 55 с мечом
вместо 45).

`weapon_slot` элемента `damage_entries` выбирает, какое из трёх значений считается
(`main.py`, выбор оружия перед вызовом движка):

| `weapon_slot` | `weapon` | Базовый урон |
|---|---|---|
| `no_weapon` | `None` | главная характеристика + `damage` (честный безоружный урон) |
| `main_weapon` (и любой неизвестный слот → `main_weapon`) | оружие основной руки | база + `effective_damage` основного |
| `additional_weapons` | оружие доп. руки | база + `effective_damage` дополнительного |

Следствия:
- значения основной и дополнительной руки реально различаются — урон каждого
  оружия учитывается ровно один раз и только в своём слоте;
- сломанное оружие даёт 0 урона, но остаётся в слоте и по-прежнему определяет
  `primary_damage_type` для `damage_type == "all"`;
- профиль игрока считает те же три числа тем же способом
  (`frontend/src/components/ProfilePage/StatsTab/damage.ts`), поэтому «Осн. урон»
  в профиле обязан совпадать с `base` в логе боя;
- autobattle-service своей математики урона не имеет — он вызывает эти же
  эндпоинты, паритет формулы автоматический.

Мёртвая функция `compute_single_damage_entry` (второй, ошибочный экземпляр той же
формулы) удалена в FEAT-167 — новую логику урона добавлять только в
`compute_damage_with_rolls`.

## Система эффектов

- Эффекты имеют: name, magnitude, duration, target_side (self/enemy)
- **Instant**: здоровье/мана/энергия/стамина - применяются сразу (clamped to max)
- **Buff**: хранятся в `active_effects[pid]`, влияют на damage/resist модификаторы
- Duration уменьшается каждый ход, удаляется при 0

## Celery задача

- `save_log(battle_id, turn_number, events)` - сохраняет лог хода в MongoDB
- Broker: RabbitMQ
- Backend: Redis
- **Подавляет исключения** через `contextlib.suppress(Exception)`

## Коммуникация (HTTP, исходящие)

| Сервис | Endpoint | Назначение |
|--------|----------|-----------|
| character-attributes:8002 | GET `/attributes/{id}` | Боевые характеристики |
| character:8005 | GET `/characters/{id}/profile` | Имя, аватар |
| skills:8003 | GET `/skills/admin/skill_ranks/{id}` | Данные навыка |
| skills:8003 | GET `/skills/characters/{id}/skills` | Навыки персонажа |
| inventory:8004 | GET `/inventory/{id}/equipment` | Экипировка |
| inventory:8004 | GET `/inventory/items/{id}` | Данные предмета |
| inventory:8004 | GET `/inventory/{id}/fast_slots` | Быстрые слоты |
| character-attributes:8002 | POST `/attributes/cumulative_stats/increment` | Кумулятивная статистика по итогам боя (`_track_cumulative_stats`). **FEAT-167 задача #17: роут стал internal-only** — обязателен `X-Internal-Token` (`main._internal_token_headers()`, читает env в момент вызова). Вызов fire-and-forget: ошибка логируется и глотается, поэтому потеря заголовка молча остановила бы учёт побед, убийств и разблокировку перков — покрыто тестами в `tests/test_cumulative_stats.py` |

## FEAT-125: перк-система (контракт с skills-service)

- Внешние поля действия: `SkillSelection = {attack_skill_id, defense_skill_id, support_skill_id, item_id}`. Поля `*_rank_id` удалены.
- `skills_client.py` общается с новым контрактом skills-service:
  - `get_resolved_skill(skill_id, character_id)` → `GET /skills/{skill_id}/resolved?character_id=...`
  - `character_has_skill(character_id, skill_id)` / `character_skills(character_id)` → `GET /skills/characters/{character_id}/skills`
- Все межсервисные запросы в skills-service идут с `Authorization: Bearer ${INTERNAL_SERVICE_TOKEN}` (env var, DevSecOps FEAT-125 task #20).
- **Required env var:** `INTERNAL_SERVICE_TOKEN` — используется battle-service и celery-worker при вызове skills-service resolver. В dev есть дефолт `dev-internal-token-change-me` в `docker-compose.yml`. В prod читается строго из `.env` на VPS (без дефолта) — должен быть выставлен до FEAT-125 cutover-деплоя. Для первого cutover-деплоя раскомментировать `BATTLE_RESET_ON_BOOT: "1"` в `docker-compose.prod.yml` (one-shot сброс `battle:*` Redis-ключей rank-эры).
- Redis-кулдауны (`participants[*].cooldowns`) теперь ключуются по `str(skill_id)` вместо rank_id. Одноразовый flush при первом старте — startup hook `feat125_flush_battle_state`, gated by `BATTLE_RESET_ON_BOOT=1`.
- `models.BattleTurn` хранит Python-атрибуты `attack_skill_id/defense_skill_id/support_skill_id`, но столбцы MySQL остались с именем `*_rank_id` (миграции нет — это лог).

## FEAT-163: таймаут хода, выбывание и админская заморозка

До этой фичи дедлайн хода писался **в три места** (Redis-state, ZSET `battle:deadlines`,
`battle_turns.deadline_at`) и **не читался на истечение ни одним из них**. Бой ушедшего игрока
оставался `in_progress` навсегда и блокировал **обоих** участников: перемещение, сбор ресурсов,
ролевые посты, двенадцать операций инвентаря и любой новый бой. Свипер — это тот самый
недостающий читатель.

### Свипер: один фоновый цикл, три задачи за тик

Запускается из `@app.on_event("startup")` → `startup_deadline_sweeper` (`main.py:5400-5408`),
который создаёт `asyncio.create_task(_deadline_sweeper_loop())`. Это тот же приём, что уже
использует WS-подписчик (`main.py:4937-4941`). Не Celery beat: celery-worker не имеет реквизитов
БД (`DB_HOST`/`DB_DATABASE`/`DB_USERNAME`/`DB_PASSWORD` ему в compose не заданы), а вся боевая
логика асинхронная.

- `_deadline_sweeper_loop` (`main.py:5379`) — «неумирающий» цикл: тело тика обёрнуто в
  `try/except`, любое исключение логируется, цикл продолжается. Свипер, который тихо умер,
  воспроизводит ту же ошибку, которую чинит.
- `_deadline_sweeper_tick` (`main.py:5362`) — один тик; собственная сессия `AsyncSessionLocal()`
  на тик.

**Три задачи за тик:**

1. **Проход по просроченным дедлайнам** — `_sweep_due_deadlines` (`main.py:5225`):
   `ZRANGEBYSCORE battle:deadlines -inf <now> LIMIT 0 50` (`SWEEPER_BATCH_LIMIT = 50`,
   `main.py:4964`) → на каждую запись `handle_expired_turn`. Неразбираемая запись просто
   удаляется (`_parse_deadline_member`, `main.py:4974`) — испорченный элемент не должен убивать
   цикл. Если обработчик упал, запись возвращается в ZSET с исходным score, чтобы следующий тик
   повторил.
2. **Keep-alive замороженных боёв** — `_keep_alive_frozen_battles` (`main.py:5285`).
3. **Сверка с MySQL** — `_reconcile_stale_battles` (`main.py:5310`), раз в
   `BATTLE_TIMEOUT_RECONCILE_EVERY` тиков (по умолчанию каждый 60-й ≈ раз в час).

**Аренда (advisory).** `_acquire_sweeper_lease` (`main.py:5351`) делает
`SET battle:deadline_sweeper:lock <instance_id> NX EX <2 × interval>` (`SWEEPER_LEASE_KEY`,
`main.py:4962`) и умеет продлевать собственную аренду. Аренда **не несущая**: корректность на ней
не держится — её обеспечивает атомарный `ZREM`-захват (см. ниже). Аренда лишь избавляет от
дублирующих чтений Redis/MySQL, если у battle-service когда-нибудь появится вторая реплика
(сегодня невозможно: `container_name: battle-service` в обоих compose-файлах).

**Выключатель.** `BATTLE_TIMEOUT_SWEEPER_ENABLED=0` → startup-хук выходит сразу, без деплоя кода.

### Почему выбывание выражено как поражение — ключевой приём

**Это главное архитектурное решение фичи, и без него код читается неправильно.**

`handle_expired_turn` (`main.py:5056`) не пишет собственной концовки боя. Просрочившему
проставляется `hp = 0`, `defeated = True`, `dropped_out = True` — то есть **выбывание выражается
как обычное поражение** — а дальше вызывается та же пост-ходовая резолюция, которую выполняет
смертельный удар:

```
teams_alive = {team участника, у кого hp > 0}
if len(teams_alive) <= 1:  -> _finalize_battle(..., by_timeout=True)   # main.py:1785
else:                      -> ход переходит дальше по turn_order, минуя мёртвых
```

Из-за этого **оба бизнес-правила выполняются без единой ветки «если 1×1 / если командный»**:

- **1×1** — жива только команда противника → `_finalize_battle` проводит штатное завершение
  (награды, история, синхронизация ресурсов и прочности, кумулятивная статистика, Mongo-лог,
  WS `battle_finished`, уборка ZSET, статус `finished`) → блокировка снимается **обоим**.
- **Командный бой** — живы несколько команд → бой продолжается, союзники не наказаны;
  блокировка самого выбывшего снимается через `dropped_out_at`.
- **Выбыл последний в команде** — у команды нет `hp > 0`, она выпадает из `teams_alive`;
  если осталась одна команда, бой завершается её победой. Отдельного кода на это нет.

**Будущему читателю:** соблазн добавить явные ветки «1×1 против командного» означает, что этот
приём не был замечен. Параллельной концовки здесь нет и быть не должно.

`BattleStatus.forfeit` намеренно **не** используется — см. запись в `docs/ISSUES.md`: в командном
бою бой вообще не «сдан», уходит один участник, поэтому значение перечисления — неверная
гранулярность. Статус остаётся `finished`, факт выбывания живёт в
`battle_participants.dropped_out_at` и в Mongo-событии `participant_timed_out`.

### Три слоя идемпотентности — и почему ни один не используется в одиночку

1. **Атомарный захват.** `ZREM` возвращает число реально удалённых элементов; продолжает только
   тот вызов, который получил `1` (`main.py:5244`). Из любого числа параллельных проходов ровно
   один владеет записью. Это первичная гарантия, и она не требует блокировок.
2. **Мьютекс на бой.** `SET battle:{id}:timeout:lock <uuid> NX EX 60`
   (`TIMEOUT_LOCK_TTL_SECONDS`, `main.py:4966`) сериализует обработчик против другого прохода
   свипера. **Это сужение, а не гарантия:** путь обычного хода игрока этот замок не берёт, так
   что гонка «свипер против легитимного хода» им не закрывается.
3. **Предусловия, перечитанные внутри обработчика** (`main.py:5069-5109`). Именно они закрывают
   дыру слоя 2. Дроп отменяется, если: боя нет; `status != in_progress`; `state["paused"]` или
   `battle.is_paused`; `next_actor != participant_id` (игрок уже сходил); дедлайн в состоянии
   **не** в прошлом (состояние авторитетнее score в ZSET — так выглядит перевзведённый дедлайн);
   участник уже `dropped_out` или `hp <= 0`.
   Плюс сама запись в MySQL идемпотентна:
   `UPDATE battle_participants SET dropped_out_at = UTC_TIMESTAMP() WHERE id = :pid AND dropped_out_at IS NULL`.

Сравнения времени идут только через `parse_deadline` (`redis_state.py:74`) и `utc_now()`
(`redis_state.py:62`) — никогда через `datetime.utcnow()` напрямую: в живом состоянии
сосуществуют формы со смещением `+03:00` и наивный UTC (наследие FEAT-161).

### `AND is_paused = 0` в SELECT сверки — не косметика

`_reconcile_stale_battles` (`main.py:5310`) ищет бои, у которых **вообще нет записи в ZSET**
(например, бой был на паузе, когда истёк ключ состояния) — свипер по ZSET к ним структурно слеп.
Это же и ретро-починка уже зависших на проде боёв.

```sql
SELECT id FROM battles
 WHERE status = 'in_progress'
   AND is_paused = 0
   AND updated_at < UTC_TIMESTAMP() - INTERVAL :ttl HOUR
```
и затем, только если ключа `battle:{id}:state` в Redis **нет**, — abandon-finish.

**Неочевидная причина `AND is_paused = 0`:** пауза **не обновляет `updated_at`**. `pause_battle`
пишет сырой SQL (`main.py:1629-1635`), который не запускает ORM-овский `onupdate` на
`models.py:68-72`, а у самой колонки нет MySQL-ного `ON UPDATE CURRENT_TIMESTAMP`. Значит
замороженный неделю назад бой подходит под **все** условия по возрасту, а его ключ состояния к
тому времени истёк. Без этой строки проход, задуманный как спасение брошенных боёв, **уничтожал
бы легитимные заморозки**. Проверка сделана на MySQL, поэтому продолжает работать и после
исчезновения Redis-состояния — то есть ровно тогда, когда она нужна.

### Keep-alive замороженных боёв — зачем он вообще нужен

`battle:{id}:state` живёт `BATTLE_STATE_TTL_HOURS` = 48 ч (`redis_state.py:26-27`), а заморозка
рассчитана на **дни**. Если ключ истекает посреди заморозки, разморозка делает бесполезное:
`resume_battle_if_ready` оборачивает весь блок восстановления в `if state:` (`main.py:1720`), так
что она снимает `is_paused`, **не взводит дедлайн**, **не добавляет запись в ZSET** — и при этом
**рапортует об успехе**. На выходе бой, в который нельзя играть и которого не видит свипер. То
есть фича заморозки тихо переставала бы работать после 48 часов — единственного срока, ради
которого ею и пользуются.

Поэтому каждый тик: `SELECT id FROM battles WHERE status = 'in_progress' AND is_paused = 1` →
`EXPIRE battle:{id}:state <STATE_TTL>` (`main.py:5285-5308`). Один индексированный запрос плюс N
`EXPIRE` — цена ничтожна, новой фоновой задачи не требуется.

### Админская заморозка / разморозка

Переиспользует существующую машинерию паузы, параллельного пути resume нет.

- `pause_battle(db, battle_id, reason, by_admin=False)` (`main.py:1617`) — пишет
  `is_paused` / `pause_reason` / `paused_by_admin` в MySQL, зеркалит `pause_reason` и
  `remaining_deadline_seconds` в Redis-состояние, **ZREM-ит все записи боя из `battle:deadlines`**
  (таймер действительно останавливается и свипер боя не видит) и шлёт WS `battle_paused`.
- `resume_battle_if_ready` (`main.py:1674`) первым делом читает `paused_by_admin` и возвращает
  `False`, пока флаг стоит (`main.py:1684-1694`). Иначе одобрение/отклонение заявки на
  присоединение (`main.py:4498`, `:4562`) тихо снимало бы админскую заморозку.
- **`POST /battles/admin/{battle_id}/freeze`** (`main.py:4136`, `require_permission("battles:manage")`).
  Тело: `AdminFreezeRequest {reason?}` (`schemas.py:254`). Причина проходит
  `_validate_pause_reason` (`main.py:4092`): trim, отказ на управляющих символах, максимум
  255 символов (`PAUSE_REASON_MAX_LENGTH`, `main.py:1614`), пусто → «Бой заморожен
  администратором» (`main.py:1613`). `404` «Бой не найден», `400` «Бой уже завершён».
  Заморозка боя, уже стоящего на паузе из-за заявки, разрешена — она «повышает» паузу до
  админской и заменяет причину. Участников (кроме NPC) уведомляет `_notify_participants`
  (`main.py:4110`).
- **`POST /battles/admin/{battle_id}/unfreeze`** (`main.py:4171`). Снимает `paused_by_admin`,
  затем вызывает `resume_battle_if_ready`. **Восстанавливается ОСТАВШЕЕСЯ время, а не свежие
  24 часа** — `deadline_at = now + remaining_deadline_seconds` из существующего пути resume. Если
  заявка на присоединение всё ещё висит, бой честно остаётся на паузе с причиной заявки и ответом
  «Бой остаётся на паузе: рассматривается заявка на присоединение». `400` «Бой не приостановлен»,
  если бой не на паузе.
- Причина рендерится из **четырёх** мест: `main.py:1349`, `:1434`, `pause_battle` (`:1617`) и
  `_build_runtime` (`main.py:4859`, `state.get("pause_reason") or JOIN_REQUEST_PAUSE_REASON`).

### Новые колонки и миграция

Миграция `006_dropout_admin_freeze`
(`services/battle-service/app/alembic/versions/006_add_dropout_and_admin_freeze.py`,
`down_revision = '005_battle_parties'`, `version_table = alembic_version_battle`, применяется
автоматически при старте контейнера). Все три колонки — одной ревизией, один деплой-window;
`downgrade` удаляет все три. Индексов нет, бэкфила нет.

| Таблица | Колонка | Тип | Модель |
|---|---|---|---|
| `battle_participants` | `dropped_out_at` | `DATETIME NULL` | `models.py:102-104` |
| `battles` | `pause_reason` | `VARCHAR(255) NULL` | `models.py:60-62` |
| `battles` | `paused_by_admin` | `TINYINT(1) NOT NULL DEFAULT 0` | `models.py:65-67` |

Схемы: `dropped_out: bool = False` в состоянии участника (`schemas.py:323`), заполняется в
`_build_runtime` (`main.py:4886`). Поле аддитивное, для autobattle-service инертно.

### Снятие блокировки: `AND bp.dropped_out_at IS NULL` в четырёх сервисах

В бою 1×1 блокировка снимается сама (статус становится `finished`). В **командном** бою бой
остаётся `in_progress`, поэтому выбывший остался бы заблокированным — это чинило бы симптом, а не
причину. Поэтому все четыре предиката активного боя получили `AND bp.dropped_out_at IS NULL`.
**Все четыре названы здесь намеренно: следующее изменение этой колонки упрётся в ту же стену.**

| Сервис | Файл:строка | Функция | Что разблокирует |
|---|---|---|---|
| locations-service | `app/main.py:129-142` | `check_not_in_battle` | перемещение, сбор ресурсов, ролевые посты |
| character-service | `app/main.py:809-820` | `_is_in_battle` | проверки на стороне персонажа |
| inventory-service | `app/crud.py:781-793` | `is_character_in_battle` | двенадцать операций инвентаря |
| battle-service | `app/crud.py:79-96` | `get_active_battle_for_character` | новый бой / заявка / принятие приглашения |

**Порядок деплоя (принятый риск, LOW):** колонку создаёт `alembic upgrade head` battle-service при
старте, а остальные три сервиса читают её по запросу пользователя. При общем
`docker compose up --build -d` есть окно в несколько секунд, когда запрос инвентаря/перемещения
может получить `Unknown column 'bp.dropped_out_at'` → 500. Транзиентно, лечится повтором. При
ручном деплое поднимать battle-service первым.

### Истекшее состояние Redis при живой строке `in_progress`

`_abandon_finish_battle` (`main.py:5030`): честно наградить победой после 48 часов тишины
нечем — HP, команды, эффекты и порядок ходов уже стёрты. Бой завершается через
`_force_finish_battle` (`main.py:3965`): статус `finished`, без победителя, без наград и
PvP-последствий, `dropped_out_at` всем участникам, **все записи ZSET удалены (участники
перечисляются из MySQL, не из Redis)**, все уведомлены. Это же чинит старый путь админского
force-finish (`main.py:4059`), который раньше молча оставлял записи в ZSET для боёв с истекшим
состоянием.

### Что видят игроки

| Кому | Канал | Текст | `ws_type` |
|---|---|---|---|
| Выбывшему | уведомление | «Вы не сделали ход за отведённое время и выбыли из боя.» | `battle_timeout_dropout` |
| Остальным в бою | уведомление | «{Имя} не успел сделать ход и выбыл из боя.» | `battle_participant_dropped` |
| Всем (abandon-finish) | уведомление | «Бой завершён: истёк срок ожидания хода.» | `battle_force_finished` |
| Всем (заморозка) | уведомление + баннер | причина от админа либо «Бой заморожен администратором» | `battle_frozen` |
| Лог боя (Mongo) | `save_log.delay` | событие `participant_timed_out` | — |

NPC исключаются (`c.is_npc = 0`) во всех запросах уведомлений.

### Переменные окружения (обе compose-файла)

| Переменная | Default | Читается | Назначение |
|---|---|---|---|
| `TURN_TIMEOUT_HOURS` | `24` | `config.py:11` | Время на ход. **Остаётся 24** — это одни реальные сутки: игрок должен успеть поспать и отработать день. Теперь меняется без правки кода |
| `BATTLE_STATE_TTL_HOURS` | `48` | `redis_state.py:26` | TTL ключа `battle:{id}:state`; он же порог возраста для сверки |
| `BATTLE_TIMEOUT_SWEEPER_ENABLED` | `1` | `config.py:14` | Выключатель свипера |
| `BATTLE_TIMEOUT_SWEEP_INTERVAL_SECONDS` | `60` | `config.py:15-17` | Период тика |
| `BATTLE_TIMEOUT_RECONCILE_EVERY` | `60` | `config.py:18` | Раз в сколько тиков запускать сверку с MySQL |

Прописаны в `docker-compose.yml:487-491` и `docker-compose.prod.yml:214-218`. Новых Python-пакетов
фича не добавляет. Новых RBAC-разрешений тоже: оба админских эндпоинта используют существующее
`battles:manage`.

## FEAT-164: восстановление в покое

- Все три синхронизации ресурсов в `character_attributes` (обычное завершение боя, HP=1 проигравшему в `pvp_training`, force-finish/таймаут) дополнительно ставят `regen_anchor_at = UTC_TIMESTAMP()` — время боя не засчитывается как покой. Если колонки ещё нет (миграция character-attributes-service не применена), выполняется старый UPDATE без якоря с WARNING в логе (`_execute_with_anchor_fallback`).
- `battle_participants.joined_at` — начало «занятого» интервала участника для character-attributes-service (для поздно вступивших — свой момент входа).
- Старт боя не менялся: `build_participant_info` → `GET /attributes/{id}` досчитывает восстановление до `joined_at`.

## Известные проблемы

1. **Нет проверки HP <= 0** - бой не завершается автоматически при смерти участника
2. **Дублирование логики** - enemy_effects применяются дважды (copy-paste ошибка)
3. **Синтаксическая ошибка** в redis_state.py (пропущена скобка в dict comprehension)
4. **Кулдаун не обновляется** в battle_engine.py - `remaining -= 1` не записывает обратно в dict
5. **Несогласованность типов** - participant_id хранится как string в Redis, но используется как int
6. **Нет атомарности** - Redis state + MySQL write не в одной транзакции
7. **Celery подавляет ошибки** - `contextlib.suppress(Exception)` маскирует сбои записи логов
8. **Нет retry-логики** для HTTP-вызовов (таймаут 5 сек, крэш при 4xx/5xx)
