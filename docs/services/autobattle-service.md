# autobattle-service

**Порт:** 8011 (Docker) / 8020 (внутренний)
**Технологии:** FastAPI (async), aioredis, httpx
**Путь:** `/home/dudka/chaldea/services/autobattle-service/`

## Назначение

AI-автобой. Автоматическое принятие решений за игрока в бою на основе эвристического алгоритма. Подписывается на Redis Pub/Sub для мгновенной реакции на ход.

## Структура файлов

```
autobattle-service/app/
├── main.py        # FastAPI app, Redis listener, обработчик ходов, построение фичей (230 строк)
├── strategy.py    # Класс Strategy: выбор действий, веса, Wilson score (148 строк)
├── clients.py     # HTTP-обёртки для battle-service API (23 строки)
├── config.py      # Pydantic Settings
├── tasks.py       # Пустой файл
└── requirements.txt
```

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Статус сервиса (mode, allowed participants, redis status) |
| POST | `/mode` | Установить стратегию: "attack" / "defense" / "balance" |
| POST | `/register` | Зарегистрировать участника для автобоя |
| POST | `/unregister` | Снять участника с автобоя |

## Хранение данных

**Без собственной БД.** Всё в оперативной памяти:
- `ALLOWED: set` - participant_id на автобое
- `PID_BATTLE: dict` - participant_id -> battle_id
- `LAST_STATS: dict` - (turn, pid) -> {hp, mana, energy, stamina}
- `HISTORY: defaultdict(deque)` - (battle_id, pid) -> последние 12 ходов DPS

**Redis Pub/Sub:**
- Слушает pattern `battle:*:your_turn`
- При получении сообщения -> автоматический ход

## Алгоритм принятия решений

### 1. Feature Vector (build_features)
- **Ресурсы:** hp_ratio, mana_ratio, energy_ratio, stamina_ratio (0-1)
- **Дельты:** изменения ресурсов с прошлого хода
- **Боевые:** attack_ready_cnt (навыки без кулдауна), buff/debuff counts
- **Моментум:** dps_last3_avg (средний DPS за 3 хода)
- **Предметы:** hp_pots_left, mana_pots_left
- **Предсказание:** enemy_lethal_in (через сколько ходов убьём врага при текущем DPS)
- **Шум:** rand_uniform (рандомизация)

### 2. Выбор действий (strategy.select_actions)
1. Фильтрация доступных навыков (проверка кулдаунов и ресурсов)
2. Расчёт весов для каждого навыка:
   - Base weight: 1.0
   - Mode bonus: attack (+0.5 атака), defense (+0.5 защита), balance (+0.2 всё)
   - HP-based bonus: низкое HP -> больше вес support/defense
   - Wilson score: пользовательский фидбек (лайки/дизлайки)
   - Noise: +-0.05 рандом
3. Выбор лучшего навыка каждого типа (attack, defense, support)
4. Выбор предмета: максимизация value = (need_hp * recovery) при hp < 70% или mana < 60%

### 3. Триггер
- Redis Pub/Sub -> получает `participant_id` в канале `battle:{id}:your_turn`
- Если participant_id в ALLOWED -> автоматический ход
- HTTP -> battle-service: `POST /battles/{id}/action`

## Коммуникация

### HTTP (исходящие)
- `battle-service:8010` -> GET `/battles/{id}/state` (состояние боя)
- `battle-service:8010` -> POST `/battles/{id}/action` (отправка действия)

### Redis Pub/Sub (входящие)
- `battle:*:your_turn` -> триггер автохода

## Известные проблемы

1. **Memory leak** - `LAST_STATS` растёт бесконечно, нет очистки после завершения боя
2. **Неиспользуемые зависимости** - lightgbm, scikit-learn, celery, pymongo, sqlalchemy в requirements но не используются
3. **Race conditions** - `ALLOWED`, `PID_BATTLE` модифицируются из HTTP и async Redis reader без блокировок
4. **httpx клиент не пулится** - создаётся заново на каждый запрос
5. **Mode не персистентен** - сбрасывается в "balance" при перезапуске
6. **Предполагает 1v1** - логика выбора врага: `order[(index + 1) % len]`
