# Chaldea - Architecture Overview

## What is Chaldea?

Chaldea - это браузерная RPG-игра с микросервисной архитектурой. Игроки создают персонажей, исследуют мир, прокачивают навыки, экипируют предметы и сражаются друг с другом в пошаговых PvP-боях.

## Tech Stack

| Компонент | Технология |
|-----------|-----------|
| **Backend** | Python 3, FastAPI (все 10 сервисов) |
| **Frontend** | React 18 + Vite + Redux Toolkit |
| **Основная БД** | MySQL 8.0 (единая для всех сервисов) |
| **Документная БД** | MongoDB 6.0 (логи боёв, снапшоты) |
| **Кэш/Стейт** | Redis 7 (состояние боёв, Pub/Sub) |
| **Очереди** | RabbitMQ (уведомления, Celery broker) |
| **Фоновые задачи** | Celery (worker + beat) |
| **API Gateway** | Nginx |
| **Хранилище файлов** | S3-совместимое (s3.twcstorage.ru) |
| **Оркестрация** | Docker Compose (single instance) |

## Service Map

```
                          +-----------+
                          |   Nginx   |
                          | (port 80) |
                          +-----+-----+
                                |
        +-----------+-----------+-----------+-----------+
        |           |           |           |           |
   +----+----+ +----+----+ +----+----+ +----+----+ +----+----+
   |Frontend | |  User   | | Battle  | |AutoBattle| |  Photo  |
   | :5555   | | :8000   | | :8010   | | :8011    | | :8001   |
   +---------+ +----+----+ +----+----+ +----+----+ +----+----+
                    |           |           |           |
        +-----------+-----------+-----------+-----------+
        |           |           |           |
   +----+----+ +----+----+ +----+----+ +----+----+
   |Character| |Char Attrs| | Skills | |Inventory|
   | :8005   | | :8002    | | :8003  | | :8004   |
   +---------+ +----------+ +--------+ +---------+
        |
   +----+----+ +----+----+
   |Locations| |Notific. |
   | :8006   | | :8007   |
   +---------+ +---------+

   Infrastructure:
   [MySQL :3306] [MongoDB :27017] [Redis :6379] [RabbitMQ :5672]
   [Adminer :8081] [MongoExpress :8082] [RedisInsight :5540]
```

## API Gateway Routes (Nginx)

| Path | Service | Port |
|------|---------|------|
| `/users/` | user-service | 8000 |
| `/photo/` | photo-service | 8001 |
| `/attributes/` | character-attributes-service | 8002 |
| `/skills/` | skills-service | 8003 |
| `/inventory/` | inventory-service | 8004 |
| `/characters/` | character-service | 8005 |
| `/locations/` | locations-service | 8006 |
| `/notifications/` | notification-service | 8007 |
| `/battles/` | battle-service | 8010 |
| `/media/` | Static files | - |
| `/` (catch-all) | frontend (Vite dev) | 5555 |

Специальная настройка для `/notifications/` - streaming (SSE), без буферизации, таймаут 3600s.

## Database Architecture

**Единая MySQL-база `mydatabase`** - все сервисы подключаются к одной БД, но работают со своими таблицами:

### Таблицы по сервисам

| Сервис | Таблицы |
|--------|---------|
| user-service | `users`, `users_character`, `users_avatar_preview`, `users_avatar_character_preview` |
| character-service | `characters`, `character_requests`, `races`, `subraces`, `classes`, `starter_kits`, `titles`, `character_titles`, `level_thresholds` |
| character-attributes-service | `character_attributes` |
| skills-service | `skills`, `skill_ranks`, `skill_rank_damages`, `skill_rank_effects`, `character_skills` |
| inventory-service | `items`, `character_inventory`, `equipment_slots`, `gathering_skills`, `gathering_skill_ranks`, `character_gathering_skills` (FEAT-128) |
| locations-service | `Countries`, `Regions`, `Districts`, `Locations`, `LocationNeighbors`, `posts`, `gathering_nodes`, `gathering_sessions` (FEAT-128), `origin_countries` (FEAT-154), `post_drafts` (FEAT-156), `post_gate_requests` (FEAT-159) |
| notification-service | `notifications` |
| battle-service | `battles`, `battle_participants`, `battle_turns` |

**MongoDB** (`mydatabase`):
- `battle_logs` - логи ходов боёв
- `battle_snapshots` - снапшоты персонажей на момент начала боя

**Redis**:
- `battle:{id}:state` - текущее состояние боя (JSON)
- `battle:{id}:snapshot` - кэш снапшота
- `battle:{id}:turns` - ZSET номеров ходов
- `battle:deadlines` - ZSET дедлайнов всех боёв
- Pub/Sub: `battle:{id}:your_turn` - оповещение о ходе

## Time & Timezones

**Инвариант: все контейнеры работают в UTC. Переменная `TZ` не задана нигде и задаваться не должна.**

Проверяется так (должно не выводить ничего):

```bash
grep -nE "^[[:space:]]*-?[[:space:]]*TZ[=:]" docker-compose.yml docker-compose.prod.yml
```

(Простой `grep -n "TZ"` теперь находит сами предупреждающие комментарии в обоих compose-файлах —
поэтому проверять надо именно присваивание переменной.)

Почему это важно, а не просто «принято»:

- Колонки `created_at` / `updated_at` / `deadline_at` — это MySQL `DATETIME`/`TIMESTAMP`, у них
  **нет часового пояса**. Значение в них правильное только потому, что и `NOW()` в MySQL, и
  `datetime.utcnow()` в Python дают UTC.
- Pydantic v1 сериализует наивный `datetime` без смещения: клиент получает
  `"2026-03-23T10:23:58"` — строку, по которой невозможно понять пояс.
- Поэтому клиент (`services/frontend/app-chaldea/src/utils/serverDate.ts`) по договорённости
  трактует строку без смещения как **UTC**. Строку со смещением (`Z`, `+03:00`) он разбирает как
  есть и повторно не сдвигает.

**Что сломается, если кто-нибудь задаст `TZ` любому сервису.** MySQL и Python начнут писать в те
же колонки местное время, но метка уедет клиенту всё так же без смещения — и клиент всё так же
прочитает её как UTC. Каждая дата в игре сместится на величину пояса: возраст постов и лента
локации, онлайн-статус игроков, кулдауны сбора и перемещения, таймер хода в бою, игровой
календарь. **Ни исключения, ни ошибки в логах, ни падения теста** — цифры просто станут неверными,
и обнаружит это только игрок. Хуже того, сместятся только новые записи: база окажется смесью
UTC и местного времени без признака, где что.

Это же относится к `ENV TZ` в Dockerfile, монтированию `/etc/localtime` и `default-time-zone`
в конфиге MySQL.

**Как сделать правильно, если пояс всё-таки понадобится.** Сначала бэкенд должен начать отдавать
смещение явно (FEAT-161 Stage 2 — бэкенд эмитит UTC-offset во всех сервисах, включая ~22 места с
ручным `.isoformat()`), и только после этого `TZ` перестанет быть опасным. Клиентский парсер
написан терпимым к смещению заранее, ровно ради этого перехода.

Отдельно: **игровой календарь — это не часовые пояса.** Игровое время (196 реальных дней = 1
игровой год) считается в `locations-service` как разность двух наивных UTC-меток. Пояс на него не
влияет и влиять не должен.

## Inter-Service Communication

### HTTP (синхронно)

```
user-service ──> character-service (профиль персонажа)
               ──> locations-service (детали локации)

character-service ──> inventory-service (создание инвентаря)
                  ──> skills-service (назначение навыков)
                  ──> character-attributes-service (создание атрибутов)
                  ──> user-service (привязка персонажа к юзеру)
                  ──> locations-service (FEAT-154: проверка стартовой точки при подаче и
                      одобрении заявки, текущий игровой год из /locations/game-time;
                      FEAT-156: DELETE /locations/admin/drafts/by_character/{id} —
                      очистка черновиков постов при удалении персонажа, шаг 4.5 в
                      delete_character;
                      все ссылки graceful — недоступность сервиса не блокирует заявку
                      и не отменяет удаление персонажа)

locations-service ──> character-service (игроки в локации)
                  ──> character-attributes-service (стамина для перемещения, refund_stamina при cancel/battle-interrupt — FEAT-128)
                  ──> inventory-service (FEAT-128: gathering/award на finalize, free_slots_check на старте, gathering-skills на старте для расчёта бонусов)

inventory-service ──> character-attributes-service (модификаторы при экипировке)

battle-service ──> locations-service (FEAT-128: /internal/cancel-gathering при pvp_attack — отменяет добычу victim перед созданием боя)

battle-service ──> character-attributes-service (боевые характеристики)
               ──> character-service (профиль)
               ──> skills-service (данные навыков)
               ──> inventory-service (экипировка, предметы)

autobattle-service ──> battle-service (состояние боя, отправка действий)

notification-service ──> user-service (список юзеров для рассылки)
```

### RabbitMQ (асинхронно)

- `user_registration` queue: user-service -> notification-service (welcome-уведомление)
- `general_notifications` queue: notification-service -> notification-service consumer (рассылка)
- Celery broker: battle-service -> celery-worker (сохранение логов в MongoDB)

**Примечание:** RabbitMQ consumers в character-service, skills-service, inventory-service и character-attributes-service **закомментированы**. Изначально планировалась асинхронная коммуникация, но сервисы перешли на HTTP.

## CI/CD Pipeline

GitHub Actions (`.github/workflows/ci.yml`):

```
Push to main
    ↓
[Test] — parallel pytest for each backend service
    ↓ all pass
[Deploy] — SSH to VPS → git pull → docker compose up --build -d
```

### Environments

- **Dev** (`docker-compose.yml`): Vite dev server, hot reload, exposed ports, dev tools (Adminer, MongoExpress, RedisInsight)
- **Prod** (`docker-compose.yml` + `docker-compose.prod.yml`): static frontend build in Nginx, HTTPS (Let's Encrypt), no volume mounts, no exposed service ports, no dev tools

### Prod Server

- Domain: `fallofgods.top`
- VPS path: `~/rpgroll`
- SSL: Let's Encrypt via certbot container (auto-renewal every 12h)

## Authentication

- **JWT tokens** (HS256) с access (20h) и refresh (7d) токенами
- Секретный ключ **захардкожен** (`"your-secret-key"` в auth.py)
- Токены хранятся в `localStorage` на фронтенде
- Аутентификация реализована **только в user-service** и **notification-service** (через HTTP-вызов к user-service)
- Большинство эндпоинтов других сервисов **не защищены** аутентификацией

## Game Domain

### Основные игровые сущности

1. **Расы (7):** Человек, Эльф, Драконид, Дворф, Демон, Бистмен, Урук
2. **Подрасы (16):** По 2-3 подрасы на расу (Норды, Ост, Ориентал и т.д.)
3. **Классы (3):** Воин, Ловкач, Маг
4. **Создание персонажа:** Заявка -> модерация (approve/reject) -> создание персонажа с инвентарём, навыками и атрибутами
5. **Мир:** Countries -> Regions -> Districts -> Locations (граф соседей с стоимостью перемещения)
6. **Бои:** Пошаговые PvP с навыками (атака/защита/поддержка), предметами, эффектами, кулдаунами

### Character Progression

- Пассивный опыт -> уровни (по таблице LevelThreshold)
- 10 stat points за уровень
- Прокачка атрибутов: strength, agility, intelligence, endurance, health, mana, energy, stamina, charisma, luck
- Дерево навыков с рангами (бинарное ветвление)
- Экипировка с модификаторами (13 типов слотов + 10 быстрых слотов)
