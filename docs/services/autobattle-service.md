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
| POST | `/register` | Зарегистрировать участника для автобоя (JWT + проверка владения) |
| POST | `/internal/register` | Служебный двойник для battle-service: поставить моба/НПС под управление ИИ. Требует `X-Internal-Token` (FEAT-170), проверки владения нет |
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
4. Выбор предмета: максимизация `value(slot)` (`strategy.py`, `_pick_best`)

#### Оценка предмета из быстрого слота (FEAT-168)

Раньше слот оценивался только по восстановлению ресурсов, поэтому боевое зелье, яд или свиток урона стоили ровно 0 и автобой не брал их никогда. Сейчас к прежним слагаемым добавлены боевые (все веса — именованные константы в начале `strategy.py`):

| Слагаемое | Формула | Вес |
|---|---|---|
| Восстановление | `need_hp * health_recovery` и т.д., где `need = max(0, порог − доля ресурса)`: нужда растёт по мере того, как ресурс заканчивается (пороги hp 70 %, mana/energy 60 %) | — |
| Запас | `quantity` | `QUANTITY_WEIGHT = 0.01` |
| Строки урона (свитки) | `Σ amount` (поле `chance` у строк урона предмета боевой сервис намеренно не бросает — урон применяется всегда, отыгрываются только уклонение и сопротивления) | `DAMAGE_WEIGHT = 0.6` |
| Эффекты на себя/союзника | `Σ abs(magnitude) * max(1, duration)` | `BUFF_WEIGHT = 0.15` |
| Эффекты на врага | `Σ abs(magnitude) * max(1, duration)` | `DEBUFF_WEIGHT = 0.12` |
| Яд на оружие | `coating_bonus_damage * coating_turns` | `COATING_WEIGHT = 0.2` |
| Очищение (строка `Cleanse`) | фикс. ценность, только если на участнике есть снимаемый эффект | `CLEANSE_WEIGHT = 2.0` |

Особые правила:
- **Яд при уже нанесённом яде** (`runtime.participants[pid].weapon_coating` непустой) — весь слот стоит `0`: боевой сервис отклонит нанесение (`item_rejected`), а предмет за ход всего один, и ход по предмету был бы потрачен впустую.
- **Очищение** засчитывается, только если среди `runtime.active_effects[pid]` есть эффект, подходящий под селектор строки (`attribute_key`: `debuff` / `periodic_damage` / `control_partial` / `stat_down` / `all` / имя эффекта). Полный контроль (Stun, Poison:paralysis) не снимается ничем и не учитывается. Вся логика селекторов — **упрощённое зеркало** `battle-service/app/buffs.py`, источник истины — боевой сервис: автобою нужен только ответ «есть ли смысл брать очищение». В частности `stat_down` повторяет `buffs._is_stat_down`: сложные эффекты (ArmorBreak, Freeze, Electrify, Daze, Wet, Curse) движок раскрывает по модулю силы и они считаются ухудшением при любом знаке magnitude, Holy — никогда; у остальных смотрится знак magnitude. При правках `buffs.py` зеркало нужно сверять.
- **Совместимость:** все новые поля слота и состояния читаются через `.get(..., default)`. Бой, начатый до деплоя (снапшот быстрых слотов без `effects` / `damage_entries` / `consumable_action`), оценивается ровно как раньше — только по восстановлению и запасу.
- **Нужда в ресурсах считалась наоборот** (`ratio − порог`) — автобой лечился на полном HP и не лечился на 20 %. Исправлено в FEAT-168 (задача #5a); формула теперь `порог − ratio`, зафиксирована тестами `tests/test_strategy_items.py::TestLegacyRecoveryRegression`.
- `hp_pots_left` / `mana_pots_left` в `build_features` (`main.py`) не менялись — эти фичи про запас лечения, а не про боевые эффекты.

### 3. Триггер
- Redis Pub/Sub -> получает `participant_id` в канале `battle:{id}:your_turn`
- Если participant_id в ALLOWED -> автоматический ход
- HTTP -> battle-service: `POST /battles/{id}/action`

## Коммуникация

### HTTP (исходящие)
- `battle-service:8010` -> GET `/battles/internal/{id}/state` (состояние боя)
- `battle-service:8010` -> POST `/battles/internal/{id}/action` (отправка действия)

**FEAT-169 (на упреждение):** оба вызова отправляют `X-Internal-Token`
(`clients.internal_token_headers()`, читает `INTERNAL_SERVICE_TOKEN` из окружения
в момент вызова). Сами маршруты `/battles/internal/*` пока токен **не проверяют** —
заголовок сегодня инертен. Смысл: когда этот префикс будут закрывать, автобой
не умрёт молча (оба вызова best-effort по своей природе — ошибка гасит автоход).
Если переменной нет в окружении, уходит пустое значение — поведение ровно такое же,
как сегодня без заголовка. Переменную в оба compose-файла добавляет DevSecOps.

**FEAT-170 (волна 1):** оба заголовка перепроверены — `clients.py:27` (`get_battle_state`)
и `clients.py:38` (`post_battle_action`) действительно шлют `X-Internal-Token`, правок не
потребовалось. Дополнительно в `app/auth_http.py` добавлен канонический
`verify_internal_token` (пусто в env → 503, нет/чужой заголовок → 401, тексты по-русски).
С волной 2 `/battles/internal/*` закрыт токеном, так что эти заголовки больше не инертны —
без них автобой перестал бы ходить.

**FEAT-170 (волна 2, задача T11):** `POST /autobattle/internal/register` закрыт
`dependencies=[Depends(verify_internal_token)]`. У этого маршрута, в отличие от публичного
двойника, **нет проверки владения персонажем** — он ставит под управление ИИ любого
участника, поэтому доступ без общего токена недопустим. Единственный вызывающий —
battle-service при создании PvE-боя (`main.py:801`), заголовок он шлёт с волны 1.
Публичный `POST /autobattle/register` (JWT + проверка владения) не затрагивается.

### Redis Pub/Sub (входящие)
- `battle:*:your_turn` -> триггер автохода

## FEAT-125: перк-система

- `Strategy.rating: Dict[int, Tuple[int, int]]` теперь ключуется по `skill_id` (раньше — `rank_id`). Прежняя история лайков/дизлайков дропается на cutover.
- Payload `/battles/{id}/action` формируется с `{attack_skill_id, defense_skill_id, support_skill_id}` (раньше `*_rank_id`).
- `_filter_available` читает `skill_id` (с fallback на `id`) из snapshot rows; battle-service `skills_client.character_skills` денормализует `skill_id` в `id` alias для совместимости.

## Известные проблемы

1. **Memory leak** - `LAST_STATS` растёт бесконечно, нет очистки после завершения боя
2. **Неиспользуемые зависимости** - lightgbm, scikit-learn, celery, pymongo, sqlalchemy в requirements но не используются
3. **Race conditions** - `ALLOWED`, `PID_BATTLE` модифицируются из HTTP и async Redis reader без блокировок
4. **httpx клиент не пулится** - создаётся заново на каждый запрос
5. **Mode не персистентен** - сбрасывается в "balance" при перезапуске
6. **Предполагает 1v1** - логика выбора врага: `order[(index + 1) % len]`
