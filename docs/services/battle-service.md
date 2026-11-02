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
| GET | `/battles/battles/{battle_id}/logs` | Логи всех ходов. **FEAT-171 (фикс по ревью #2):** требует JWT + `battle_visibility.require_battle_log_access` |
| GET | `/battles/battles/{battle_id}/logs/{turn_number}` | Логи конкретного хода. Тот же гейт |
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
- `battle:{id}:state` - JSON: participants (hp/mana/energy/stamina/cooldowns/fast_slots/weapon_coating/passive_key/is_npc/passive_state), active_effects, turn_order, turn_number, next_actor, dungeon_session_id (TTL: 48h)
- `battle:passive:saber_run:{dungeon_session_id}:{character_id}` - int, стаки Сейбера за забег (FEAT-189, TTL 14 дней)
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
7. Использовать предмет из быстрого слота (восстановление, боевые эффекты, урон, яд на оружие — FEAT-168)
8. Обработать ATTACK-навык + расчёт урона
9. Списать ресурсы (mana, energy) за использованные навыки
10. Установить кулдауны
11. Записать ход в MySQL
12. Обновить state в Redis
13. Pub/Sub -> оповестить следующего игрока
14. Celery task -> сохранить лог хода в MongoDB

### Формула урона (compute_damage_with_rolls)
```
1. base = eff(главная характеристика класса)   # CLASS_MAIN_ATTRIBUTE[class_id], FEAT-195
          + attrs["damage"]                    # база: перки, броня, украшения, баффы/еда
          + weapon["effective_damage"]         # урон оружия выбранного слота (0, если слот пуст)
2. damage_type -> определить тип (или взять с оружия если "all")
3. raw_damage = base + skill_damage_amount
4. raw_damage *= (1 + percent_buffs / 100)
5. Roll dodge -> если попал, урон = 0
6. Roll hit_chance + 0.1·eff(luck) -> если промах, урон = 0
7. Roll crit (сохранённый critical_hit_chance + баффы, без второй удачи) -> raw_damage *= crit_multiplier
8. final = raw_damage * (1 - resists / 100)
```

### Убывающая отдача статов (FEAT-195)

`app/stat_caps.py` — байт-в-байт копия канонического
`character-attributes-service/app/stat_caps.py` (сверяет `scripts/check_econ_copies.sh`):
`eff(x) = x` до 100, `100 + (x−100)·0.5` до 200, `150 + (x−200)·0.25` выше.
Кап считается от суммы: `attacker_attr` уже содержит баффы и пассивки.

- **Урон:** `base_stat = eff(основной атрибут)` (250 → 162.5).
- **Удача:** `battle_engine.luck_proc_bonus(attrs) = 0.1·eff(luck)` — к броску попадания;
  к шансу эффектов (`attacker_luck_bonus` в `main.py`) — та же формула от **баффнутой** удачи
  (константа `LUCK_PROC_PER_POINT` продублирована в `main.py`: тесты подменяют `battle_engine`
  моком). В бросок крита удача больше не добавляется — она уже есть в сохранённом
  `critical_hit_chance` (раньше считалась дважды).
- **Баффы статов:** `buffs.aggregate_modifiers(effects, base_attributes=None)` — производные
  (сопротивления, уклонение, крит, res_effects) от изменения основного стата считаются как
  `k·(eff(base+Δ) − eff(base))`; удача теперь тоже тянет dodge / critical_hit_chance / res_effects
  по 0.1. Без `base_attributes` (только `_is_stat_down`, нужен знак) — линейно.
- **Инициатива:** `redis_state.compute_initiative = eff(agi)·1.0 + (eff(str) + eff(int))·0.75`;
  тай-брейк по сырой ловкости не изменился.

### Три значения урона и `effective_damage` (FEAT-167)

Урон оружия **не входит** в характеристику `damage` — она хранит только «базу»
(характеристики, перки, броня и украшения с их заточкой и камнями, баффы, еда).
Урон конкретного оружия считает **inventory-service** и отдаёт его полем
`effective_damage` в `GET /inventory/internal/characters/{character_id}/equipment`
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

Актуализировано FEAT-168 (Codebase Analyst, 2026-09-18) — раздел отставал от FEAT-143/146.

Исходная строка эффекта (та же форма, что у `skill_perk_effects` в skills-service):
`{target_side, effect_name, chance, duration, magnitude, attribute_key}`. `target_side` —
`self` / `enemy` / `ally` / `all_allies` / `all_enemies`. Шанс срабатывания фильтруется в
`main._filter_effects_by_chance` (`chance + 0.1·eff(удача атакующего с баффами) − живучесть цели×0.2`, FEAT-195).

- **Instant**: `hp` / `mana` / `energy` / `stamina` — применяются сразу, clamp 0..max
  (`buffs.apply_new_effects`). Для врага положительная magnitude инвертируется в урон.
- **Модификаторы**: хранятся в `state["active_effects"][pid]` как
  `{name, attribute, magnitude, duration, owner_id, fresh}`; `aggregate_modifiers` складывает их
  в движковые каналы (`percent_damage_*`, `percent_resist_*`, плоские атрибуты).
- **Сложные эффекты** (`buffs._expand_complex_effect`): ArmorBreak, Freeze, Electrify, Daze, Wet,
  Holy, Curse раскрываются в те же каналы.
- **Периодический урон (DoT)**: `buffs.tick_periodic_effects` — Bleeding, Burn и Poison с
  `attribute_key="periodic_damage"`; событие `effect_tick`.
- **Контроли**: `buffs.evaluate_control` — Stun и Poison:paralysis обнуляют весь ход (включая
  предмет), Knockdown и Windburn блокируют один тип навыка; события `control_skip` / `control_block`.
- **Тик длительности**: по ВЛАДЕЛЬЦУ (`owner_id`), а не по носителю — дебафф на враге убывает в конце
  хода кастера. Свеженаложенный эффект (`fresh`) не тикает в ход применения. Удаляется при duration == 0.
- **Накопление vs обновление** (FEAT-168) — зависит от ИСТОЧНИКА эффекта
  (`apply_new_effects(..., source=("item", item_id))`, по умолчанию `source=None`):
  - **Навыки** (`source=None`) — накапливаются: каждое применение добавляет отдельную запись со своей
    длительностью и силой, записи тикают независимо. Кровотечение на 2 хода по 5 и кровотечение на
    3 хода по 10 идут параллельно.
  - **Предметы** (`source=("item", id)`) — не накапливаются: повторное применение ТОГО ЖЕ предмета
    обновляет его собственную запись на месте — `duration = max(старая, новая)`, `magnitude = новая`.
    Ключ обновления — `(source, имя, нормализованный attribute, owner_id)`, поэтому эффект другого
    предмета или навыка с тем же именем не затрагивается.
  - Флаг `fresh` ставится только у по-настоящему новой записи; у уже активного эффекта он не трогается —
    иначе эффект пропустил бы один тик (подновлённый яд переставал бы наносить урон на ход).
  - `source` хранится в записи эффекта строкой `"item:42"` (состояние сериализуется в JSON, кортеж после
    round-trip стал бы списком). Нормализация — `buffs.normalize_source(source)`.
- **Снятие эффектов** (FEAT-168, `buffs.remove_effects(state, pid, *, selector, limit=0)`):
  селекторы `debuff` (всё, что повесил участник **из команды противника**; бафы союзников —
  «Вдохновение», «Шёпот духов», навыки ally — не снимаются; владелец не найден в `participants` →
  по-старому считается дебафом), `periodic_damage`, `control_partial`
  (Knockdown / Windburn), `stat_down` (отрицательный вклад в модификаторы), `all`, либо имя
  конкретного эффекта (`Bleeding`). Пустой селектор = `debuff`. `limit = 0` — снять все подходящие,
  иначе снимаются первые N (самые старые). Возвращает снятые записи для события `effects_removed`.
  **Полный контроль с пропуском хода (Stun, Poison с атрибутом `paralysis`) не снимается никогда**,
  в том числе селектором `all` — это правило движка (`buffs.is_unremovable`, список берётся из
  `evaluate_control`), его нельзя обойти настройкой предмета.
- **Совместимость со старым состоянием**: записи из Redis, созданные до FEAT-143/168 (без `owner_id`
  и `fresh`), обрабатываются как принадлежащие участнику, в чьём списке лежат.

### Расходники в бою (FEAT-168)

Предмет применяется полем `skills.item_id` того же POST-а, что и навыки: ход он не тратит, но за
ход можно применить ровно один предмет — второго канала нет по конструкции. Полный контроль
(Stun / Poison:paralysis) обнуляет и предмет.

Вся боевая настройка предмета едет в снапшоте быстрых слотов (`inventory_client.get_fast_slots`,
снимается на старте боя): `*_recovery`, `consumable_action`, `coating_turns`,
`coating_bonus_damage`, `effects`, `damage_entries`. Строки эффектов и урона имеют ту же форму,
что у навыков, поэтому идут в тот же движок без перевода. **Каждое из этих полей читается через
`.get(..., default)`**: бой, начатый до FEAT-168, их не содержит, и предмет без боевой настройки
проходит ровно прежний путь (только восстановление).

Порядок внутри шага 8 (`main.py`, секция 8):

1. Слот ищется по `item_id` в `fast_slots`; не нашли — предупреждение в лог, шаг пропускается.
2. `consumable_action` (`instant` по умолчанию | `weapon_coating` | `cleanse`).
3. **Яд при действующем яде** — событие `item_rejected` (`reason: "coating_active"`), предмет НЕ
   расходуется, остальной ход отыгрывается полностью. Отказ 400 стоил бы игроку хода.
4. `consume_item` в inventory-service — best-effort, как и раньше: ошибка логируется и не мешает.
5. Восстановление здоровья/маны/энергии/выносливости из закэшированного слота, clamp по максимумам.
6. Строки `effects`: бросок шанса той же формулой, что у навыков; `Cleanse` снимает эффекты
   (`buffs.remove_effects`, селектор в `attribute_key`, число в `magnitude`, 0 = все), остальные
   накладываются на `self` / `ally` / `all_allies` / `enemy` c `source=("item", item_id)` —
   повторное применение того же предмета обновляет свою запись, а не копит их.
7. Строки `damage_entries`: `resolve_aoe_targets` + та же `compute_damage_with_rolls`, что у атаки
   (криты, сопротивления, уклонение один раз на цель), `weapon=None` при `weapon_slot="no_weapon"`.
   Поле `chance` у строк урона **не бросается** — намеренно, ровно как в шаге атаки для урона
   навыков: попадание решают уклонение и сопротивления. Админка поле шанса у строк урона не
   показывает, чтобы не обещать несуществующий бросок.
8. `weapon_coating` — яд записывается в состояние участника (см. ниже).
9. Расход стопки: `quantity − 1`, слот уходит из пояса только на нуле. `quantity` есть и у слотов,
   снятых до FEAT-168, поэтому бои, начатые до деплоя, тоже получают все применения стопки; дефолт
   `1` нужен только для мусорного значения (нет ключа / None / 0 / не число) — такой слот тратится
   за одно применение.

### Яд на оружии (weapon_coating)

Поле участника в Redis, по умолчанию отсутствующее:

```json
"weapon_coating": {"item_id": 91, "name": "Яд гадюки", "bonus_damage": 12.0,
                   "turns_left": 4, "effects": [ …строки item_effects с target_side=enemy… ]}
```

- `bonus_damage` прибавляется к `amount` КАЖДОЙ строки урона, бьющей оружием
  (`weapon_slot != "no_weapon"`), ДО формулы — значит проходит через баффы, крит и сопротивления.
- `effects` вешаются на тех, кто реально получил урон отравленным оружием, по одному разу за ход,
  с обычным броском шанса (удача атакующего против стойкости цели). «Строка отравлена» определяется
  наличием яда и слотом оружия, а **не** величиной прибавки: яд с `coating_bonus_damage = 0` —
  нормальная настройка (вся сила в периодическом уроне) и обязан вешать свои эффекты.
- `turns_left` убывает в конце хода владельца, рядом с `decrement_durations`; на нуле яд снимается
  и пишется `weapon_coating_expired`.
- Живёт только в состоянии боя, поэтому кончается вместе с боем. Оружие в бою не меняется.
- Отдаётся клиенту в `runtime.participants[pid].weapon_coating` (схема
  `BattleRuntimeParticipant.weapon_coating`, необязательное поле, `None` для старых боёв).

### События журнала боя от предметов

| Событие | Ключи |
|---|---|
| `item_use` | `who, item_id, item_name, recovery{health,mana,energy,stamina}, action, effects[], removed[], damage, quantity_left` |
| `item_rejected` | `who, item_id, item_name, reason ("coating_active"), active_coating, turns_left` |
| `apply_effects` (от предмета) | `who, kind: "item", item_id, item_name, effects[]` |
| `damage` (от предмета) | обычные поля + `source_kind: "item"`, `item_id`, `item_name` |
| `effects_removed` | `who, target, source, item_id, item_name, removed[]` (снятые записи эффектов) |
| `weapon_coating_applied` | `who, item_id, item_name, turns, bonus_damage` |
| `weapon_coating_expired` | `who, item_id, item_name` |

## Celery задача

- `save_log(battle_id, turn_number, events)` - сохраняет лог хода в MongoDB
- Broker: RabbitMQ
- Backend: Redis
- **Подавляет исключения** через `contextlib.suppress(Exception)`

## Уведомления (RabbitMQ `general_notifications`)

`rabbitmq_publisher.publish_notification(..., category="battle")` — каждое сообщение несёт `category` для настроек уведомлений в notification-service. Бой — `battle` (обязательная, не отключается); события боевых групп `party_left`, `party_disbanded`, `party_invitation`, `party_response`, `party_kicked` передают `category=CATEGORY_PARTY` (`party`). `party_started` остаётся `battle`.

## Коммуникация (HTTP, исходящие)

| Сервис | Endpoint | Назначение |
|--------|----------|-----------|
| character-attributes:8002 | GET `/attributes/internal/{id}` | Боевые характеристики. **FEAT-171:** игровой `/attributes/{id}` уходит под гейт владельца, бой читает внутренний двойник с `X-Internal-Token` (`battle_engine._internal_token_headers()`). У мобов и НПС владельца нет, проверка владения для них невозможна |
| character:8005 | GET `/characters/{id}/profile` | Имя, аватар |
| skills:8003 | GET `/skills/internal/characters/{id}/subclass` | **FEAT-188:** подкласс и пассивка участника на старте боя (`skills_client.get_character_subclass`). Заголовок **`X-Internal-Token`** (`skills_client._internal_headers()`), а не Bearer — `/skills/internal/*` закрыты `verify_internal_token`, Bearer там даёт 401. Таймаут `SUBCLASS_LOOKUP_TIMEOUT_S = 3.0`. Ошибка мягкая: `logger.error`, участник без пассивки, бой стартует |
| skills:8003 | GET `/skills/admin/skill_ranks/{id}` | Данные навыка |
| skills:8003 | GET `/skills/characters/{id}/skills` | Навыки персонажа |
| inventory:8004 | GET `/inventory/internal/characters/{id}/equipment` | Экипировка (полное тело: `effective_damage`, заточка, вставки, прочность, включая `fast_slot_*`). **FEAT-171:** игровой `/inventory/{id}/equipment` уходит под гейт владельца, бой читает внутренний двойник с `X-Internal-Token`. Два вызывающих: `battle_engine.fetch_weapons` и `inventory_client.get_equipment_durability` |
| inventory:8004 | GET `/inventory/internal/items/{id}` | Данные предмета (полный шаблон). **FEAT-171:** публичный `/inventory/items/{id}` стал тонкой карточкой (id, name, description, image_url, rarity, type) без цифр, поэтому бой читает внутренний двойник с `X-Internal-Token`. Вызывающие: `battle_engine.fetch_weapons`, `inventory_client.get_item`, `skills_client.get_item` |
| inventory:8004 | GET `/inventory/internal/characters/{id}/fast_slots` | Быстрые слоты (пояс) — снимок на старте боя. **FEAT-169:** игровой путь `/inventory/characters/{id}/fast_slots` закрыт JWT + проверкой владения, поэтому бой ходит во внутренний двойник с `X-Internal-Token`. Проверка владения для internal-двойника не применяется — у мобов и НПС нет владельца. Заголовок даёт `inventory_client._internal_token_headers()` (модуль-локальный: импорт из `main` был бы циклическим) |
| inventory:8004 | POST `/inventory/internal/characters/{id}/consume_item` | Трата предмета пояса в бою. **FEAT-169:** обязателен `X-Internal-Token`; ошибка возвращается игроку |
| inventory:8004 | POST `/inventory/internal/update-durability` | Запись прочности после боя. **FEAT-169:** обязателен `X-Internal-Token`; вызов best-effort — без заголовка прочность молча перестала бы сохраняться |
| character:8005 | POST `/characters/{id}/add_rewards` | Опыт и золото победителям PvE. **FEAT-169:** роут стал internal-only, обязателен `X-Internal-Token` (`main._internal_token_headers()`); ошибка только логируется |
| party:8014 | POST `/party/internal/xp-bonus` | Отрядный бонус опыта за бой. **FEAT-169:** обязателен `X-Internal-Token`; ошибка глотается в WARNING |
| party:8014 | GET `/party/internal/active-members` | Состав отряда в локации (групповой PvE/PvP). **FEAT-169:** весь префикс `/party/internal/` закрыт токеном, заголовок обязателен на всех трёх вызовах (`main.py`) |
| character-attributes:8002 | POST `/attributes/cumulative_stats/increment` | Кумулятивная статистика по итогам боя (`_track_cumulative_stats`). **FEAT-167 задача #17: роут стал internal-only** — обязателен `X-Internal-Token` (`main._internal_token_headers()`, читает env в момент вызова). Вызов fire-and-forget: ошибка логируется и глотается, поэтому потеря заголовка молча остановила бы учёт побед, убийств и разблокировку перков — покрыто тестами в `tests/test_cumulative_stats.py` |
| autobattle:8011 | POST `/autobattle/internal/register` | Постановка моба/НПС под управление ИИ при создании PvE-боя (`main.py:801`). **FEAT-170 (волна 1):** вызов отправляет `X-Internal-Token` (`main._internal_token_headers()`). Ошибка глотается в WARNING — без заголовка мобы просто перестали бы ходить, поэтому заголовок проверяется тестом на самом вызове |
| locations:8006 | POST `/locations/quests/internal/auto-progress` | Продвижение целей заданий за побеждённых врагов (`main.py:727`). **FEAT-170 (волна 1):** обязателен `X-Internal-Token`; ошибка глотается в WARNING |
| locations:8006 | POST `/locations/internal/action-gate/consume` | Трата лимита действия: PvE-атака (`_consume_combat_gate`) и PvP (`_consume_pvp_gate`). **FEAT-170 (волна 1):** обязателен `X-Internal-Token`. Обработка ошибки fail-closed — при сбое возвращается `False` и атака/PvP запрещаются, то есть потеря заголовка видна игроку сразу |
| locations:8006 | POST `/locations/internal/gathering-status` | Кто из соотрядцев занят сбором — 3 вызова (`main.py:1029`, `:1197`, `_filter_available`). **FEAT-170 (волна 1):** обязателен `X-Internal-Token`; ошибка глотается, и без заголовка сборщиков молча затягивало бы в бой |

### FEAT-170: internal-токен

`app/auth_http.py` получил канонический `verify_internal_token` (`INTERNAL_SERVICE_TOKEN`
читается из env на импорте; пусто → 503 «Internal service token не настроен», нет или
чужой заголовок → 401 «Недействительный internal token»). Модуль листовой, поэтому цикла
импорта с `main.py` нет.

**Волна 1.** Все 7 исходящих вызовов battle-service во внутренние маршруты соседей теперь
передают `headers=_internal_token_headers()` (`main.py:65`, читает env в момент вызова).

**Волна 2 (задача T12).** Весь префикс `/battles/internal/` закрыт токеном —
`dependencies=[Depends(verify_internal_token)]` на трёх маршрутах:

| Маршрут | Почему это важно |
|---------|------------------|
| `GET /battles/internal/{id}/state` | Полное состояние боя: HP/мана/кулдауны каждого участника, пояс (`fast_slots`) и награды. Вызывают autobattle-service (`clients.py:27`) и опрос из dungeon-service (`http_clients.py:377`) |
| `POST /battles/internal/{id}/action` | `_make_action_core(..., skip_ownership=True)` — ход **за любого участника любого боя**. Обход проверки владения сделан намеренно (мобами ходит ИИ), именно поэтому маршрут не должен быть доступен без токена. Вызывает autobattle-service (`clients.py:38`) |
| `POST /battles/internal/party/leave-on-move` | Удаление персонажа из формирующегося отряда при смене локации (лидер ⇒ роспуск). Вызывает locations-service (3 точки) |

Публичные двойники **не затронуты**: `GET /battles/{id}/state` и `POST /battles/{id}/action`
по-прежнему закрыты JWT и проверкой владения — именно ими пользуется браузер. nginx
(`location /battles/internal/ { return 403; }`) остаётся внешним слоем, токен — внутренним.

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
- Старт боя не менялся: `build_participant_info` → `GET /attributes/internal/{id}` (FEAT-171) досчитывает восстановление до `joined_at`.

## FEAT-171 (фикс по ревью): кто может читать логи боя

`app/battle_visibility.py` — `can_view_battle_logs` / `require_battle_log_access`.
До фикса `GET /battles/battles/{battle_id}/logs` и `.../logs/{turn_number}` не имели
**ни одной** зависимости и проходили через gateway, так что гость перебором
последовательных `battle_id` читал `{"event":"pve_rewards","xp":30,"gold":5}` и
`{"event":"skill_use","skill_id":9003}` — опыт, деньги и навыки, то есть ровно то, что
FEAT-171 объявила приватным.

Правило (сначала 404, потом 403 — как во всей фиче):

| Зритель | Результат |
|---|---|
| гость (без токена) | 401 |
| участник боя (владеет персонажем в `battle_participants`) | 200, в том числе для завершённого боя |
| наблюдатель: бой активен и у зрителя есть персонаж в `battles.location_id` | 200 |
| тот же наблюдатель, но бой завершён | 403 |
| админ/модератор **с** правом `characters:read` | 200 |
| модератор **без** этого права | 403 |
| чужой игрок | 403 |
| несуществующий `battle_id` | 404 «Бой не найден» |

Ветка наблюдателя — **дословно** правило `GET /battles/{battle_id}/spectate`: панель
логов живёт на той же странице, что и состояние боя, которое наблюдатель уже читает.
Сузить гейт логов, не сузив `/spectate`, значило бы сломать панель, не закрыв при этом
более богатую утечку (открытая запись в `docs/ISSUES.md` про снапшот наблюдателя:
`build_participant_info` отдаёт `attributes`, `skills`, `fast_slots`). Это **отдельный
путь кода**, продуктовое решение по нему не принято; когда его сузят — сужать оба
правила вместе.

Фронтенд не менялся: `BattlePageBar.tsx` ходит через дефолтный инстанс axios, которому
`api/axiosSetup.ts` уже добавляет Bearer-токен.

## Известные проблемы

1. **Нет проверки HP <= 0** - бой не завершается автоматически при смерти участника
2. **Дублирование логики** - enemy_effects применяются дважды (copy-paste ошибка)
3. **Синтаксическая ошибка** в redis_state.py (пропущена скобка в dict comprehension)
4. **Кулдаун не обновляется** в battle_engine.py - `remaining -= 1` не записывает обратно в dict
5. **Несогласованность типов** - participant_id хранится как string в Redis, но используется как int
6. **Нет атомарности** - Redis state + MySQL write не в одной транзакции
7. **Celery подавляет ошибки** - `contextlib.suppress(Exception)` маскирует сбои записи логов
8. **Нет retry-логики** для HTTP-вызовов (таймаут 5 сек, крэш при 4xx/5xx)

### Сопротивления и уязвимости (2026-10-16)

Защита от типа урона = `res_<тип> − vul_<тип>` из атрибутов бойца (`buffs.net_resist`, внутри
`build_percent_resist_buffs`) плюс боевые `percent_resist*`. Ниже нуля — урон проходит сильнее.
Шанс наложения эффекта уменьшается на `res_effects − vul_effects` (отрицательный итог его повышает).
До этого колонки `vul_*` суммировались со снаряжения в атрибуты, но в бою не читались вовсе.


## Подземелья и блокировка активности (FEAT-175)

* `battles.dungeon_session_id` (миграция `008_dungeon_session_id`) помечает бои подземелья.
* `POST /battles/internal/dungeon` (X-Internal-Token) `{dungeon_session_id, players:[{character_id, team}]}` —
  создание боя подземелья: команда 1 должна быть заблокирована именно в этом забеге (единственное
  исключение из блокировки), команда 2 — мобы. Ответ — `BattleCreated`.
* Конец такого боя (`_finalize_battle` и `_force_finish_battle`) шлёт в dungeon-service
  `POST /dungeons/internal/battle-callback` `{battle_id, session_id, winner_team, defeated_characters, aborted}`
  (фоновая задача, 3 попытки при 5xx/сетевой ошибке; промах подстрахован опросом).
* `GET /battles/internal/{id}/result` (X-Internal-Token) — итог после истечения Redis-состояния:
  `{status, winner_team, aborted, dungeon_session_id}` (победитель — по `battle_history`).
* `_ensure_not_activity_locked` отказывает (409) во всех путях создания боя, PvP-вызовах/нападениях,
  лобби, заявках на вступление и их одобрении; заблокированные соотрядцы тихо исключаются из
  групповых атак (`_filter_available`, party mob/pack attack).

Формулировки отказа одинаковы во всех сервисах (`activity_lock.lock_message`):
«Персонаж находится в подземелье» / «Персонаж без сознания до HH:MM МСК» (для второго
участника — «Цель …», «Целевой персонаж …», «Другой участник обмена …»). Код ответа — **409**.
Колонки `characters.dungeon_session_id` / `characters.unconscious_until` пишет только
character-service; остальные сервисы читают их из общей БД (как блокировку боя). В тестах
сервисов с таблицами-зеркалами `characters` conftest по умолчанию подменяет чтение на
«не заблокирован»; настоящий запрос проверяют тесты с маркером `real_activity_lock`.

## FEAT-188: пассивки подклассов

**Загрузка.** `build_participant_info` (общая для всех 4 мест сборки боя: `_assemble_battle`,
принятие PvP-вызова, PvP-нападение, одобрение вступления в идущий бой) шестым мягким вызовом
спрашивает skills-service `GET /skills/internal/characters/{id}/subclass`. Результат —
два ключа в записи снимка (`battle_snapshots` / `battle:{id}:snapshot`):
`subclass: {key, name} | null` и `passive: {key, name, description, implemented} | null`.
Снимок уже отдаётся всеми runtime-эндпоинтами и WS как есть — правок в пяти билдерах не нужно.
`is_npc: true` → у моба ни подкласса, ни пассивки. skills-service недоступен / 401 / таймаут →
`logger.error`, оба ключа `null`, бой стартует.

**Состояние.** Payload участника собирает один хелпер `_participant_payload(snap, participant_objs)`
(раньше три копии), он добавляет `passive_key` (из `_passive_key_of(snap)`);
`redis_state.init_battle_state` копирует `p.get("passive_key")`. Путь вступления в бой кладёт
`passive_key` в рукописный dict участника. Пассивка фиксируется на старте и в бою не меняется.
Бои, начатые до деплоя: ключа нет → пассивки нет (всё читается через `.get`).

**Цифры и математика** — `app/passives.py` (чистый модуль): `PASSIVE_BERSERKER_RAGE`,
`RAGE_HP_STEP_PCT = 10`, `RAGE_PCT_PER_STEP = 4`, `RAGE_MAX_STEPS = 9`, `rage_bonus_pct(hp, max_hp)`,
`passive_damage_bonus(participant_state) -> (pct, key)` (таблица диспетчеризации). Название и
описание пассивки — в реестре skills-service `subclasses.py`; меняешь константу — правь описание.

**«Ярость» Берсерка** (единственная живая пассивка): +4% к урону за каждые полные 10% потерянного
HP, максимум +36%. `max_hp` нет/0 → 0; HP зажимается в `[0, max_hp]`. Бонус добавляется в
`percent_buffs["all"]` атакующего в `_make_action_core` в двух местах — урон навыка (после
`build_percent_damage_buffs(attacker_buff_modifiers)`) и урон предмета (после `_item_pct_damage`);
считается один раз за атаку по текущему HP. `compute_damage_with_rolls` не менялся. Периодический
урон (DoT) пассивку не получает. Вампиризм ниже 25% HP — FEAT-190 (см. ниже).

**Журнал.** Каждое не-уклонённое событие `damage` от навыка или предмета при бонусе > 0 несёт
`passive_key` и `passive_pct`; `buff_pct` уже включает эту долю. События уклонения не меняются.

## FEAT-189: пассивки подклассов — волна 1

Включены 13 пассивок на существующих механиках боя (Инквизитор, Сейбер, Гладиатор, Агент,
Лансер, Механик, Арчер, Ассасин, Фокусник ч.1, Монах, Саламандр, Кастер, Искромаг) + «Ярость»
из FEAT-188. `passives.IMPLEMENTED_PASSIVES` — зеркало флага `implemented` реестра skills-service.

**Где живёт логика.** Вся математика, состояние и **все случайные броски пассивок** — в
`app/passives.py` (гейты `roll_pct` / `pick` на собственном `_rng`; бросок делается только у
владельца пассивки, поэтому случайность остальных боёв не меняется). `passives` не импортирует
`buffs` / `battle_engine` (их подменяют `MagicMock` в ~30 наборах тестов). `main.py` вызывает только
хуки H0–H13.

**Точки подключения** (`_make_action_core`, блок «5.1» общих хелперов):
| Хелпер / место | Хуки | Что делает |
|---|---|---|
| сразу после `evaluate_control` | H1 `on_turn_start` | счётчик своих ходов Гладиатора (ход, сорванный оглушением/параличом, не считается) |
| `_roll_enemy_effects` | H11a | бросок шанса вражеских строк актёра; `_filter_effects_by_chance(bonus_pp_fn=, failed_out=)` — Монах +10/+5 п.п., сбор проваленных строк для Агента |
| `_land_enemy_effects` | H11c → H11d | единая обёртка над **всеми 8** местами наложения вражеских эффектов (support/defense/attack enemy и all_enemies, вражеские строки предмета, яд на оружии): +1 ход (Фокусник — все кроме жёсткого контроля и мгновенных ресурсов; Саламандр — только Burn), затем Монах сбрасывает первый контроль (`passive_proc control_immune`) |
| `_build_target_ctx` / `_finish_target_ctx` | H5, H4, H6 | контекст цели на атаку: кража Лансера (статы цели не ниже 0) → дельты сопротивлений защитника (стаки ереси −3×n на все не-физические, Гладиатор +4×перевес, Сейбер PvP +2×n) на копии словаря → бросок уклонения → «Обман» Фокусника 10% (только если не уклонился и цель — враг). FEAT-190: при «Обмане» `deceit_redirect_target` выбирает союзника атакующего (`ctx["redirect_pid"]`), см. ниже |
| `_strike` | H3, H8 | один бросок урона по одной цели — общий для цикла навыка, цикла предмета и доп. ударов: процент по цели (копия `percent_buffs`), `force_crit` / `crit_damage_bonus` / `resist_ignore` в `compute_damage_with_rolls` (передаются только если не по умолчанию), HP/статистика, `record_strike` |
| `_finish_passive_attack` | H9, H11b, H10, H7 | после цикла урона: стаки за попадания (ересь, Лансер, Сейбер-PvP, Саламандр, «первая кровь» израсходована) → пере-бросок Агента для проваленных до урона строк по целям с критом (`passive_proc weak_spot`) → один доп. удар Механика/Искромага (свежий контекст цели: своё уклонение/обман, без H3 и без on-hit, только по живой цели) |
| атака навыка / урон предмета | H2 `begin_attack` | открывает атаку; `actx["pct"]` (Гладиатор, Сейбер-убийства) добавляется **один раз** в `percent_damage_buffs["all"]`; «Ярость» идёт прежним путём FEAT-188 |
| реальное уклонение (навык, предмет, доп. удар) | H7 `on_dodged` | Ассасин: «Из тени» готов (`passive_proc shadow_ready`); на «Обман» не срабатывает |
| `_pay_skill_costs` | H12 `mana_cost` | Кастер −10% маны за ранг, `(raw×90+50)//100`, до проверки «хватает ли»; в `spend` ключ `mana_discount` (только у Кастера) |
| шаг 9.5 | H13 `on_kills` | все новые погибшие враги актёра — его убийства (прямой урон, свитки, доп. удары и DoT его эффектов); Сейбер в данже +2%/убийство (макс. 10%), сразу в этом же бою |

Яд на оружии бросается после урона — Агенту бонус +20/+10 п.п. добавляется прямо в этот бросок
по целям, получившим от него крит.

**Состояние** (Redis, все ключи читаются через `.get`): у участника `is_npc`, `passive_state`
(`used_magic`, `heresy_stacks`, `saber_kills`, `saber_pvp`, `own_turns`, `lancer_stacks`,
`lancer_gain`, `stolen`, `first_blood_done`, `shadow_ready`, `control_immunity_used`,
`kindling_target`, `kindling_stacks`); у боя `dungeon_session_id`. Старые бои без ключей — все
хуки нейтральны. Стаки Сейбера за забег: ключ
`battle:passive:saber_run:{dungeon_session_id}:{character_id}` (TTL 14 дней, обновляется при
записи), читается при сборке боя/вступлении, пишется после каждого убийства Сейбера
(`redis_state.set_saber_run_stacks`, мягкий отказ).

**Журнал** (все поля опциональны; бой без пассивок даёт прежние события байт-в-байт):
- `damage`: `passives: [{key, kind, value?, owner?}]` — вклады атакующего и защитника, kind ∈
  `damage_pct`, `resist_pct`, `forced_crit`, `resist_ignore`, `extra_hit`, `deceit`; от движка —
  `forced_crit`, `resist_ignored_pct`; доп. удар — `extra_hit: splash|chain|echo`, `extra_mult`.
  «Ярость» по-прежнему пишет `passive_key`/`passive_pct` и попадает в `passives`, только когда в
  списке есть что-то ещё (лог только с «Яростью» = формат FEAT-188).
- «Обман»: `{"event":"damage", ..., "dodged":true, "final":0, "deceived":true,
  "passives":[{"key":"trickster_deceit","kind":"deceit","owner":t}]}` — 3D анимирует как уклонение.
- `apply_effects`: `passives` с `duration_plus` (Фокусник/Саламандр); `effects` — уже с +1 ходом.
- `resource_spend`: `mana_discount` и `passives: [{kind:"mana_discount", value}]`.
- `passive_proc`: `{who, key, kind, target?, value?, stacks?, effects?, stolen?}`, kind ∈
  `heresy_stack`, `pin`, `saber_kill`, `saber_resolve`, `shadow_ready`, `control_immune`, `weak_spot`.

## FEAT-190: пассивки подклассов — волна 2 (новые механики)

Включены оставшиеся 7 пассивок (Паладин, Хранитель, Бард, Некромант, Эфириад, Ауромант, Жрец) и
доделаны две (вампиризм «Ярости» Берсерка, перенаправление «Обмана» Фокусника) — все 21 живые,
`passives.IMPLEMENTED_PASSIVES` = 21. Правила FEAT-189 в силе: логика, числа и броски (`pick`) —
только в `passives.py`, `passives` не импортирует `buffs` / `battle_engine`.

**`buffs.py`** получил два необязательных колбэка (по умолчанию `None` → поведение байт-в-байт
прежнее): `absorb_fn(pid, amount) -> remaining` (щиты съедают снятие HP) и
`overheal_fn(pid, intended, applied, owner)` (каждая положительная доза HP) в
`apply_new_effects`, `tick_periodic_effects`, `_tick_resource`. `main.py` всегда передаёт оба
замыкания; в бою без пассивок они ничего не меняют.

**Хуки** (H14–H25 + заполненный H6 + расширенный H13):
| Хук | Где вызывается | Что делает |
|---|---|---|
| H14 `shield_total(p)` | все 6 runtime-билдеров, поля событий | сумма щитов участника (int, 0 у старых боёв) |
| H15 `absorb(state, pid, amount)` | `land_hit`, `retaliate`, замыкание `_absorb_fn` | щиты поглощают урон: сначала срочные (меньше ходов — раньше), потом вечные |
| H16 `add_shield` | обет, «Прилив» | новый щит / доливка «Прилива» того же Ауроманта до потолка, ходы → 3 |
| H17 `tick_shields(state, actor)` | 9.4, сразу после `decrement_durations` | срочные щиты, наложенные актёром, теряют ход (свежий пропускает первый тик) |
| H18 `check_vow` / `snapshot_hp` / `check_vows` | `land_hit` ④, `retaliate`, обёртки эффектов, после DoT | «Священный обет»: `0 < HP < 30%`, раз за бой — щит 20% макс. HP + снятие последнего вражеского эффекта (кроме оглушения/паралича) |
| H19 `lifesteal` | `land_hit` ⑤ | Берсерк ниже 25% HP — 15%, Жрец — 10% (святым `sainting` — 15%) от реально снятого HP |
| H20 `retaliate` | `land_hit` ⑥ | «Возмездие»: 15% полученного (щит + HP, без overkill) атакующему, без движка, без рекурсии |
| H21 `heal` | вампиризм, лечение за убийство | лечение с потолком `max_hp`, мёртвых не лечит |
| H22 `on_heal` | `_overheal_fn`, зелья (`health_recovery`) | «Прилив»: переизбыток лечения Ауроманта → щит цели (≤ 20% её макс. HP, 3 его хода) |
| H23 `blood_price` | `_pay_skill_costs` | «Плата кровью»: нехватка маны × 1.5 HP (вверх), после оплаты должно остаться ≥ 1 HP, иначе 400 |
| H24 `end_of_action` | после `resource_spend`, до 9.4a, только живой актёр | Бард «Вдохновение», Эфириад «Шёпот духов» — строки StatModifier, `main` накладывает их `apply_new_effects(..., owner_pid=actor, source=("passive", key))` |
| H25 `on_deaths` | 9.5 (`_newly_defeated`), `handle_expired_turn` | у мёртвых/выбывших снимаются их эффекты Барда/Эфириада и щиты (свои и наложенные), `inspiration_end` |
| H6 `deceit_redirect_target` | `_finish_target_ctx(allow_redirect=True)` | «Обман» → случайный живой союзник атакующего (`ctx["redirect_pid"]`), нет такого → атака просто не проходит |
| H13 `on_kills` | 9.5 | + Некромант: за каждое убийство лечение 10% макс. HP (`kill_heal`) |

**Порядок внутри `_strike` (E7)** — через `passives.land_hit` вместо `hp -= dealt`:
урон движка → ② щит цели → ③ HP (`hp_removed` без overkill) → ④ обет цели → ⑤ вампиризм
атакующего → ⑥ отражение Хранителя (→ щит атакующего → его HP → обет атакующего). `_strike`
возвращает `(dealt_int, event, post_events)`; вызывающий добавляет `event`, затем `post_events`.
`total_damage_dealt/received` по-прежнему считают `dealt_int` (включая поглощённое щитом);
исключение — перенаправленный «Обманом» удар: он идёт в `total_damage_received` союзника, но **не**
в `total_damage_dealt` атакующего (удар по своим — не урон по врагу).
Перенаправленный удар и удар не по врагу (`actx is None`) — `direct=False`: только щит и HP.
**Атакующий, убитый отражением**, дальше не бьёт (`_actor_alive()`): цикл AoE навыка/свитка
прерывается, доп. удар пропускается. Убит в шаге свитка — шаг 9 (атакующий навык) пропускается
целиком: ни урона, ни строк эффектов 9.0–9.0e, ни H2. Убит посреди атаки — не накладываются эффекты яда
с оружия и перебросы Агента; убит уроном своего же предмета — яд на оружие не наносится. Стоимость и кулдауны выбранных навыков списываются
как обычно (действие совершено); `end_of_action` — только для живого.

**Щиты** — не эффект, а `passive_state["shields"] = [{key, owner, amount, cap, turns_left, fresh}]`
у защищаемого. Поглощают любой урон: удары, отражение, мгновенный урон эффектов, DoT, отрицательные
дозы HP. Не трогают оплату HP Некромантом и выбывание по таймауту. Паладин — до конца боя или пока
не пробит; Ауромант — 3 его хода.

**Обёртки эффектов.** Все места наложения в `_make_action_core` идут через `_apply_with_passives`
(`_land_enemy_effects` — вражеские; `_apply_effects` — self/ally/all_allies/строки предмета не по
врагу): колбэки + проверка обета по снимку HP. Procs `shield_absorb` / `tide` / `vow`, возникшие
при наложении, **откладываются** и выгружаются (`_flush_absorbs`) при следующем вызове хелпера /
`_strike`, перед `resource_spend` и после тика DoT — поэтому в журнале они идут после своего
`apply_effects`. На шаге 9.4a: `snapshot_hp` → `tick_periodic_effects(..., absorb_fn, overheal_fn)`
→ periodic-события → `_flush_absorbs` → `check_vows`.

**«Обман» (E19).** Каждая строка урона, направленная в обманувшего Фокусника, после события
промаха бьёт `redirect_pid` с `× 0.5`: «чистый» контекст союзника (`_plain_ctx` — атрибуты и
сопротивления от эффектов, без уклонения, без H4/H5), атрибуты атакующего без кражи Лансера, процент
урона только от эффектов (снимок до «Ярости» и H2), `actx=None`, без вампиризма/отражения/обета.
Доп. удары не перенаправляются (`allow_redirect=False`).

**Некромант.** `_pay_skill_costs`: при `mana < cost` вся мана уходит, остаток — HP
(`spend["hp_paid"]`), щиты не участвуют, ничего не триггерит. Не хватает HP → 400
«Недостаточно маны: нужно X, есть Y. Доплатить здоровьем нельзя: нужно Z HP, есть W (должно
остаться хотя бы 1)» — ход срывается целиком (состояние не сохраняется). Уже мёртвый (отражение) —
доплата не берётся. Автобой здоровьем не платит.

**Runtime.** Поле `shield` (int) во всех 6 билдерах: `get_state_internal`, `get_state`,
`spectate_battle`, `get_battle_preview`, `admin_get_battle_state`, `_build_runtime` (WS).
Для `GET /battles/{id}/preview` поле объявлено в схеме `BattlePreviewParticipant` (`shield: int = 0`),
иначе Pydantic его отбрасывает.
Новые ключи `passive_state`: `shields`, `vow_used`, `bard_stacks`, `bard_mode`.

**Журнал** (новые поля опциональны):
- `damage`: `absorbed`, `shield_left` (только если щит что-то поглотил); `passives` + `lifesteal`
  (`{key: priest_faith|berserker_rage, kind: "lifesteal", value, owner}`).
- отражение: `{"event":"damage","source":хранитель,"target":атакующий,"final":R,"reflected":true,
  "absorbed":n,"passives":[{"key":"guardian_retribution","kind":"reflect","value":R,"owner":хранитель}]}`.
- перенаправление: `damage` с `redirected: true`, `deceived_by: фокусник`,
  `passives: [{"key":"trickster_deceit","kind":"redirect","value":50,"owner":фокусник}]` (после промаха по Фокуснику);
  `aoe_falloff` у перенаправленного удара не пишется (×0.5 — не затухание AoE).
- `resource_spend`: `hp_paid` + `passives: [{kind:"blood_price", value}]` (вместе с `mana_discount` Кастера, если есть).
- `passive_proc` kind: `vow` (`value`, `shield`, `effects?`), `tide` (`target`, `value`, `shield`),
  `shield_absorb` (`value`, `shield`; только эффекты/DoT), `kill_heal` (`target`, `value`),
  `inspiration` (`stacks`, `value`, `mode` group/solo, `targets`), `inspiration_end` (`targets`),
  `spirit_whisper` (`target`, `mode` ward/curse/might, `value` ±8).
