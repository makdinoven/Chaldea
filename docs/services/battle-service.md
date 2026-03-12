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

## Хранение данных

### MySQL (постоянное)
- **battles** - id, status (pending/in_progress/finished/forfeit), timestamps
- **battle_participants** - battle_id, character_id, team
- **battle_turns** - battle_id, actor_id, turn_number, attack/defense/support_rank_id, item_id, deadline

### MongoDB (логи)
- **battle_logs** - battle_id, turn_number, events[], timestamp
- **battle_snapshots** - battle_id, participants[] (полные данные на начало боя)

### Redis (runtime state)
- `battle:{id}:state` - JSON: participants (hp/mana/energy/stamina/cooldowns/active_effects), turn_order, turn_number, next_actor (TTL: 48h)
- `battle:{id}:snapshot` - кэш снапшота из MongoDB (TTL: 24h)
- `battle:{id}:turns` - ZSET номеров ходов
- `battle:deadlines` - ZSET дедлайнов: `{battle_id}:{participant_id}` -> unix_timestamp
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
1. base_attack = attacker_damage + weapon_damage_modifier
2. damage_type -> определить тип (или взять с оружия если "all")
3. raw_damage = base_attack + skill_damage_amount
4. raw_damage *= (1 + percent_buffs / 100)
5. Roll dodge -> если попал, урон = 0
6. Roll hit_chance -> если промах, урон = 0
7. Roll crit -> если крит, raw_damage *= crit_multiplier
8. final = raw_damage * (1 - resists / 100)
```

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

## Известные проблемы

1. **Нет проверки HP <= 0** - бой не завершается автоматически при смерти участника
2. **Дублирование логики** - enemy_effects применяются дважды (copy-paste ошибка)
3. **Синтаксическая ошибка** в redis_state.py (пропущена скобка в dict comprehension)
4. **Кулдаун не обновляется** в battle_engine.py - `remaining -= 1` не записывает обратно в dict
5. **Несогласованность типов** - participant_id хранится как string в Redis, но используется как int
6. **Нет атомарности** - Redis state + MySQL write не в одной транзакции
7. **Celery подавляет ошибки** - `contextlib.suppress(Exception)` маскирует сбои записи логов
8. **Нет retry-логики** для HTTP-вызовов (таймаут 5 сек, крэш при 4xx/5xx)
