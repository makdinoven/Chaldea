# dungeon-service

Порт **8013**, путь `services/dungeon-service/app/`. FastAPI + **async** SQLAlchemy (aiomysql),
Redis (кэш состояния забега), WebSocket. Alembic: `alembic_version_dungeon`, auto-migration при
старте контейнера. Один uvicorn-воркер (на этом держится реестр WebSocket и фоновый свипер).

Подземелья: граф комнат и коридоров, который проходит один игрок или отряд. Правила этапа 1
«Данжи 2.0» (FEAT-175) согласованы с пользователем — см. `features/FEAT-175-dungeons-2.md`.

## Файлы

| Файл | Что внутри |
|---|---|
| `main.py` | Роуты (админка, игрок, internal, WebSocket), фоновый свипер |
| `gameplay.py` | Вся игровая логика: вход, перемещение, комнаты, бои, концовки, свипер |
| `crud.py` | Админский CRUD + валидация графа |
| `schemas.py` | Pydantic v1; `validate_room_config` / `validate_grid_size` общие для create и update |
| `session_state.py` | Redis-ключи забега (кэш, восстанавливается из БД) |
| `http_clients.py` | Вызовы соседей (все с `X-Internal-Token`) |
| `ws_manager.py` | Реестр WebSocket `session_id -> {user_id -> ws}` |

## Таблицы

| Таблица | Назначение |
|---|---|
| `dungeons` | Подземелье: локация, откат (`cooldown_hours`), множители, ядро маны, `search_loot` (случайные находки при обыске, миграция 007) |
| `dungeon_rooms` | Комнаты: тип, `room_config` (JSON), позиция на карте, **`grid_w`/`grid_d`** (размер в клетках для 3D-диорамы, 2..8, NULL = дефолт фронта) |
| `dungeon_corridors` | Коридоры: стоимость выносливости, засада, ловушка, **`lock_config`** (запертая дверь) |
| `dungeon_sessions` | Забег. Статус `active/completed/escaped/wiped` (`forming` — только старые записи). `current_room_id`, `active_battle_id`, `last_activity_at`, `cooldown_until`, `finished_at`, `finalized_at`, `keys_found` (найденные ключи), `unlocked_corridor_ids` (открытые в забеге двери) |
| `dungeon_session_members` | Участники (`alive/dead`). В ответах `members[]` дополнены из профиля и атрибутов: `avatar`, `level`, `class_id` (миниатюра на столе), полосы ресурсов |
| `dungeon_session_inventory` | Общий инвентарь забега |
| `dungeon_room_state` | Состояние комнаты в забеге: `is_cleared`, `loot_collected`, выбор события, `extra_data` (отдых, склад торговца, ядро маны) |
| `dungeon_room_visits` | Туман войны (по персонажу, переживает забеги) |

Миграции: `001` initial, `002` позиции, `003` ручки коридоров, `004` жизненный цикл сессии +
`grid_w`/`grid_d` (старые сессии помечаются завершёнными, осиротевшие `forming` → `escaped`), `005` замки и ключи, `006` этажи.

## Жизненный цикл забега

```
вход (соло / отряд) ──> active ──сундук босса──> completed ──finalize──> закрыт
                          │ └──побег / 24 ч бездействия──> escaped ──finalize──> закрыт
                          └──все погибли──> wiped (закрыт сразу)
```

* **Одна группа на подземелье.** Пока есть `active`-сессия, вход → `409 «В подземелье уже находится другая группа»`.
* **Откат общий** и ставится **только при открытии сундука босса** (`cooldown_until` в БД + Redis-ключ).
  Побег и вайп отката не дают. Проверка: Redis, затем БД (восстанавливает Redis-ключ).
* **Вход атомарный** (`gameplay.start_run`): сначала все проверки (владелец, локация, блокировки,
  отряд, вход, откат), затем блокировка строки `dungeons` и повторная проверка занятости, вставка
  сессии, блокировка персонажей в character-service (всё или ничего), списание поста-намерения
  «Данж» (последним — необратимо). Любая ошибка откатывает БД и снимает блокировки: ни висящих
  `forming`, ни маркеров в Redis.
* **Блокировка персонажей** (`characters.dungeon_session_id`) ставится на входе. Побег снимает её
  сразу, вайп превращает в «без сознания 1 ч», прохождение — сразу при открытии сундука босса
  (дележ добычи идёт уже без блокировки; `finalize` снимает её ещё раз на случай сбоя).
  Пройденный забег в `my-session` отдаётся как `pending_loot_session_id`, а не `session_id`.
* **Вайп:** добыча забега теряется, участники без сознания `WIPE_KNOCKOUT_SECONDS = 3600` и
  возвращаются на локацию подземелья (character-service `knockout`). Если оглушение не удалось —
  блокировка всё равно снимается.
* **Побег:** каждая стопка теряется с шансом 50 %, забег завершён, подземелье свободно, остаток
  можно разделить (фаза `distributing_loot`) и закрыть `finalize`.
* **Брошенный забег:** 24 ч без действий (`last_activity_at`) → как побег; остаток добычи уходит
  лидеру, сессия закрывается. Свипер раз в 5 минут + ленивая проверка при входе/чтении состояния.
  Брошенный дележ (completed/escaped без finalize) тоже закрывается через 24 ч (остаток — лидеру).
* **Лидер пропал:** если лидер бездействует ≥10 минут и не подключён к WebSocket, лидерство
  переходит к участнику, который совершает действие (`leader_changed`).

## Бои

* Создаются через `POST /battles/internal/dungeon` (battle-service, internal token, без JWT),
  бой помечен `dungeon_session_id`. Участники забега освобождены от блокировки только для этого боя.
* Мобы спавнятся `POST /characters/internal/spawn-dungeon-mobs` со `stat_multiplier = dungeon.mob_multiplier`
  (масштабирует все числовые базовые характеристики шаблона). `spawn_type='dungeon'`: их нет в списке
  мобов локации, они не возрождаются, после боя удаляются (`despawn-dungeon-mobs`).
* Боевая комната: бой стартует **до** того, как группа войдёт. Не стартовал — ошибка, выносливость
  не списана, группа на месте, ход можно повторить. Комната без мобов → `409`.
* Засада в коридоре: при неудачном старте боя выносливость не списывается. Победа → группа
  продолжает путь в целевую комнату (если она боевая — сразу новый бой).
* Итог боя приходит **колбэком** `POST /dungeons/internal/battle-callback`; запасной путь — опрос
  `GET /state` (Redis-состояние боя, затем `GET /battles/internal/{id}/result`) и свипер.
  Обработка ровно один раз: под блокировкой строки сессии `active_battle_id` должен совпасть и
  тут же обнуляется; повтор → `{"status": "ignored"}`.
* Прерванный бой (админ / брошен) → фаза `battle_pending`: действие `start_battle` повторяет бой,
  отступать можно только в уже исследованные комнаты.

## Комнаты

| Тип | Поведение |
|---|---|
| `battle` / `boss` | Бой при входе (см. выше). Босс: один бросок ядра маны; сундук завершает забег |
| `treasure` | `open_chest` (`loot_table`, шанс × `loot_multiplier`), один раз |
| `trap` | При первом входе проверка характеристики (`stat_check`, `difficulty` × `difficulty_modifier`), урон `fail_damage` (по умолчанию 20) |
| `event` | `event_choice`: `reward` (предметы + золото лидеру), `damage`, `heal` (`heal_percent`, совместимость с `heal_amount`), `teleport` (только в комнату этого подземелья), `battle` (мобы из исхода), `nothing` |
| `rest` | `start_rest` → `complete_rest` (лечение `heal_percent`), `revive_member` (`revive_gold_cost`) |
| `merchant` | `merchant_buy` (склад на сессию) |
| `teleport` | `portal`: `blue` (по умолчанию) или `red`. **Синий** — при входе ничего не происходит, группа стоит в комнате и может идти дальше; действие `use_portal` переносит в `target_room_id` того же подземелья, многоразово (неверная цель — 400). **Красный** — ловушка: при входе проверка `stat_check` (по умолчанию `intelligence`) против `difficulty` (по умолчанию 10). Успех — портал раскрыт (`is_cleared`), больше не срабатывает. Провал — перенос в случайную комнату из `target_room_ids` с её эффектами (бой и т.п.), портал остаётся живым. Игрокам видны `portal`, у синего `target_room_id`, у красного только `portal_result`; цели красного не раскрываются |
| `fork` / `deadend` | Без действий |

Ловушки и уроны событий **не убивают**: HP не опускается ниже 1 (смерть — только в бою).
Урон ловушки в коридоре (`trap_config`, по умолчанию 15) тоже наносится.

**Ядро маны:** после победы над боссом один бросок `mana_core_chance`. Успех открывает путь в
комнату ядра **только для этого забега** (граф не меняется). Из комнаты босса — `enter_mana_core`,
в комнате ядра — `search_mana_core` (без второго броска): кристалл `mana_core_item_id` в общий
инвентарь, **подземелье деактивируется** (`is_active=false`), группа возвращается к сундуку босса.
Если в комнату ядра можно пройти обычным коридором, бросок делается при поиске.

### Запертые двери и ключи

`dungeon_corridors.lock_config = {key, pickable=true, difficulty=12, stat_check="agility", pick_cost=2}`.
Ключи — фиксированный набор (`schemas.DUNGEON_KEYS`: copper, silver, gold, bone, obsidian, crimson), живут
только внутри забега (`dungeon_sessions.keys_found`), не предметы. Ключ выдают: сундук сокровищницы
(`room_config.key_reward`), победа в боевой комнате (`key_reward`), исход события `key` (`outcome_data.key`);
событие `key_found` по WS. Ход через запертый коридор без ключа — `409` без списания выносливости; с ключом
дверь открывается до конца забега (`unlocked_corridor_ids`), ключ не тратится и подходит ко всем дверям своего
цвета. `POST /sessions/{id}/pick-lock` (лидер, фаза исследования) — взлом: каждый живой платит `pick_cost`
выносливости, проверка `stat_check` против `difficulty`; успех открывает дверь. `exits`, `explored_corridors`,
`seen_doors` отдают `lock_key`/`locked` (+ `lock_pickable` у выходов), состояние — `keys`. `validate` ругается
на ключ, который нигде не выдаётся (ошибка, если взлом запрещён).
Замок висит со стороны `from_room`: из `to_room` дверь отпирается засовом без ключа (и тоже остаётся
открытой до конца забега), выход там `locked=false`. Подъёмник — не дверь, ему ключ/рычаг нужен с обеих сторон.
`validate` предупреждает, если из комнаты, куда переносят порталы, события или провал, не выйти без ключа/рычага.

Пройденные комнаты в состоянии (`explored_rooms`) несут `used`: сундук сокровищницы открыт или привал
использован — 3D-стол показывает их отработанными (открытый пустой сундук, костёр догорел), как и `is_cleared`.

### Решение отряда (FEAT-176)
`POST /dungeons/sessions/{id}/vote {character_id, corridor_id?, portal?}` — живой участник говорит, куда идти из
текущей комнаты (дверь, синий портал или ничего — «как решит лидер»). Голос хранится в Redis
(`dungeon:session:{id}:vote:{character_id}` = `room_id|choice`) и действует только в этой комнате. Состояние отдаёт
`votes` и `waiting_for`; `move` и `use_portal` лидера — `409`, пока `waiting_for` не пуст (одиночный забег не ждёт,
павшие не голосуют). `POST /dungeons/sessions/{id}/ping {character_id, kind, room_id?, corridor_id?}` — метка на столе
для отряда, только рассылка по WS, не чаще раза в секунду на участника (`429`).

### Классовые испытания (FEAT-176)
`POST /dungeons/sessions/{id}/challenges {character_id, kind, corridor_id, mode}` — живой участник берётся за
испытание (`lockpick` — запертая взламываемая дверь из текущей комнаты; тайники, щит и решётка — ниже; фаза исследования). Выносливость
`pick_cost` платит он сам. `mode="roll"` — бросок: его характеристика ±5 против сложности (×`difficulty_modifier`),
не своего класса −6 — итог сразу в `result`. `mode="game"` — мини-игра: сервер выдаёт `challenge_id` и `params`
(штифты: частота, фаза, центр и полуширина окна; запас промахов; лимит времени), хранит их в Redis; браузер
присылает `POST .../challenges/finish {character_id, challenge_id, presses[]}` (мс от начала), сервер переигрывает
нажатия по тем же правилам (`challenges.py`, зеркало — `minigames/lockpick.ts`) и проверяет правдоподобие (не чаще
80 мс, не больше нажатий, чем позволяет игра, не дальше прошедшего времени). Ловкость расширяет окно; не плут — окно
×0.6, +1 штифт, меньше запас промахов. Над одной дверью одновременно работает один участник (`409`).
`/pick-lock` оставлен как бросок того, кто взламывает.

**Тайные проходы.** Коридор с `passage_config.secret = {kind, difficulty=12, cost=2, fail_damage=10, hint}` —
`kind`: `mechanism` (плут, ловкость), `illusion` (маг, интеллект), `rubble` (воин, сила). Пока не открыт в этом забеге
(`unlocked_corridor_ids`), его нет среди выходов из `from_room`, на карте (`explored_corridors`, `seen_doors`), в ходе и
голосовании; изнутри тайной комнаты путь назад виден. `current_room.secrets[]` = `{corridor_id, kind, hint}` (подсказка
по умолчанию — своя у каждого вида). Испытание того же вида на этот коридор (`/challenges`, `kind=<вид>`) открывает
проход. Иллюзия — руны (последовательность в `params`, ответ — `presses` с номерами рун в `/finish`). Механизм и завал
играются по ходам: `POST .../challenges/step {challenge_id, x, y}` / `{index}` — где рычаг и какие камни несущие,
знает только сервер; ответ `distance` / `safe`, последний ход несёт `result`. `/finish` для них — отказ. Несущие камни завала выбираются с весом по ряду груды (снизу вверх 4-3-2: веса 3/2/1), трещины 0–3 намекают на них с честностью 0.8 + 0.01 × навык (0.55–0.95, чужому классу −0.2). Обвал завала
(и проваленный бросок силы) наносит разбирающему `fail_damage`.

**Щит отряда** (`kind="shield"`, без `corridor_id`; воин, сила; сложность 12, стамина 2). Мини-игра «Стойка»:
`params.blows[] = {at_ms, side}` (0 слева, 1 сверху, 2 справа), `warn_ms` — за сколько до удара он виден; повороты
щита приходят в `/finish` как `ms * 4 + side`, сервер считает отбитые удары не позже прошедшего времени. Блок
`block` = доля отбитых (бросок: 0.8 / 0.3). Щит хранится в Redis (`dungeon_shield:{session_id}` =
`{character_id, room_id, block}`) и действует, пока отряд в этой комнате и держащий жив; состояние отдаёт
`shield = {character_id, block}`. Второй щит в той же комнате — `409`. На ближайшем ходе (`move`) щит встречает
проваленную ловушку коридора или комнаты-ловушки — урон получает только держащий, `ceil(урон × (1 − 0.75 × block))`
— и первый удар засады; после хода щит опускается. **Первый удар засады** (`AMBUSH_STRIKE_DAMAGE = 10`) наносится
перед боем всем живым без щита (или ослабленным — держащему), не убивает (HP ≥ 1); не удалось начать бой —
здоровье возвращается вместе со стаминой. Пока идёт засадный бой, состояние отдаёт `ambush = {corridor_id, from_room_id, to_room_id}` (Redis `pending_corridor_id`) — 3D-стол ставит отряд посреди коридора, врагов впереди.

**Решётка / плита** — коридор с `passage_config.gate = {look: grate|slab, difficulty=12, cost=2, fail_damage=10}`
(не вместе с `secret`; с замком лучше не совмещать — у них общий `unlocked_corridor_ids`). Пока не подпёрта, ход по
коридору с любой стороны — `409`, выход отдаёт `gate = look`. Испытание `kind="gate"` (воин, сила): мини-игра
«Удержать» — тиками по 50 мс решётка тянется вниз (`surges` — рывки сильнее), нажатие поднимает; нужно продержать её
в `zone` суммарно `hold_ms`; упала до пола — рухнула. `/finish` получает моменты нажатий и отпусканий по очереди,
сервер переигрывает тики до прошедшего времени (`gate_verdict`, зеркало — `minigames/warrior.ts`). Успех открывает
коридор до конца забега; провал (и проваленный бросок) — держащему `fail_damage`.

**Магическая печать** — коридор с `passage_config.seal = {difficulty=12, cost=2, fail_damage=12}` (не вместе с
`secret` и `gate`; общий `unlocked_corridor_ids` с замком). Пока не снята, ход с любой стороны — `409`, выход отдаёт
`sealed: true`. Испытание `kind="seal"` (маг, интеллект) играется по ходам: `params = {nodes: 8, start, steps,
mistakes, pulsing}`; путь знака (звезда: соседние по кругу узлы подряд не идут) знает только сервер. `step {index}` —
узел из `pulsing`; ответ `safe` (верный ли), новые `pulsing` и `offsets`; неверный узел выбывает, искр сверх `mistakes` — провал
(магу прощается одна, при навыке ≥10 — две; чужому классу — ноль и больше ложных узлов). Провал бьёт снимающего. Ритм: круг бьётся раз в `beat_ms` (1400 мс); `offsets[i]` — сдвиг пульса узла `pulsing[i]` от такта в долях такта: у верного 0, у ложных ±0.22 + 0.008 × навык (0.07–0.38), чужому классу ×0.55.

**Тёмные комнаты** — `room_config.dark = true` у любой комнаты. Пока в ней не горит свет (`current_room.dark`,
`dark_room` — всегда), выходы отдаются как неизученные (`to_room_name = "???"`), ловушка комнаты при входе и ловушка
коридора при выходе из неё бьют ×1.5, обыск невозможен (`409`). `POST /dungeons/sessions/{id}/light {character_id}` —
любой живой: маг — заклинание (стамина 1, `room_state.extra_data.lit = "spell"`, до конца забега), остальные — факел
(стамина 3, Redis `dungeon_torch:{session_id}` = комната, гаснет при любом переходе). WS `room_lit`. На карте
`explored_rooms[].dark` — комната осталась без магического света.

**Обыск** — `kind="search"` (плут, ловкость; стамина 2; без `corridor_id`), раз на комнату за забег
(`extra_data.searched`), не в темноте. Тайник — `room_config.stash = {items: [{item_id, quantity, chance}],
difficulty=12}`. Мини-игра по ходам: поле 6×4, `step {x, y}` → `way` (куда указывают следы, 0 — вверх, по часовой
восьмыми) или находка (`way = null`, `result`); следы честны с вероятностью от навыка, без тайника — случайны.
Бросок: успех — тайник найден (если есть). Любой обыск с шансом 5% даёт одну вещь из `dungeons.search_loot`.
`result.loot` — найденное; кладётся в общий инвентарь, WS `loot_added`.

**Дозор и ночная вылазка.** Комната отдыха: `room_config.ambush_chance` (0..1) и `ambush_mob_ids`. Во время привала
(фаза `resting`) любой живой встаёт в дозор — `kind="watch"`, только `mode="roll"` (сила, стамина 1), один дозорный
(`current_room.watch = {character_id, passed}`). На `complete_rest` с шансом вылазки: бдительный дозорный — тревога,
отдых засчитан; задремавший — первый удар (10) по нему, иначе по всем; бой с `ambush_mob_ids`, отдых сгорает без
лечения (WS `rest_completed` с `raided`). Бой не начался — урон возвращается, отдых идёт как обычно.

Состояние отдаёт `extents = [{floor, min_col, max_col, min_row, max_row}]` — габариты каждого этажа в клетках
редактора (180 px) по всем комнатам, известным и нет (только рамка): 3D-стол кладёт под весь этаж скальное основание
сразу, и оно не растёт по мере открытия.

### Чат и журнал забега (FEAT-176)
`POST /dungeons/sessions/{id}/chat {character_id, text}` — реплика участника (до 300 символов, не чаще раза в секунду —
`429`); `GET /dungeons/sessions/{id}/chat?character_id=` — лента забега, старые сначала. Лента в Redis
(`dungeon_chat:{session_id}`, последние 200 строк, на время забега). Строка — `{id, at, kind: say|log, text, tone:
info|good|bad, character_id, name}`; новая рассылается по WS `chat_message`. Журнал (`chat.py`) слушает каждую рассылку
`ws_manager` (`ws_manager.listeners`) и превращает события в строки: переход («Отряд идёт из «A» в «B»» — пишется в
начале хода, до событий коридора), ловушки с уроном по каждому, засады с первым ударом, бои, кто чем занят, итоги
испытаний, привал, добыча. `party_vote` теперь несёт `character_id` голосовавшего (реплика над фигуркой).

**Разведка, обезвреживание, распознавание (FEAT-176).**
- `kind="scout"` (плут, ловкость; стамина 2; коридор из текущей комнаты, ещё не разведанный). Мини-игра «Тени»:
  `params = {cells, lamps[{freq, phase, duty}|null], time_limit_ms}`, тиками по 25 мс; `/finish` — моменты шагов,
  стоять или войти в клетку под горящим фонарём — провал (`shadow_verdict`, зеркало `minigames/intel.ts`). Успех:
  выход отдаёт `scout = {room_type, room_name, mob_count, trap, ambush, disarmed}`. Провал: разведчику 8 урона,
  коридор «настороже» — на следующем проходе шанс засады +0.3 (если в нём есть мобы засады).
- `kind="disarm"` (плут; только если разведка нашла ловушку): «Тяги» по ходам, `step {index}` → `safe`, `near`
  (сколько натянутых рядом); перерезать все свободные — ловушка коридора снята до конца забега; провал — 12 урона.
- `kind="insight"` (маг, интеллект; без `corridor_id`; комната события до выбора или синего портала). «Созвездие»:
  `params = {rings, steps, offsets, time_limit_ms, seed}`, `/finish` — индексы повёрнутых колец (кольцо r двигает r и
  r+1), успех — все на 0. Итог в `room_state.extra_data.insight`: событие отдаёт `choice_hints`, портал — `portal_to`.
- Хранение: Redis `dungeon_intel:{session_id}` = `{scouted, alerted, disarmed}`. `scouted` — по ключу
  `"{corridor_id}>{room_id}"`: разведка смотрит в одну сторону (с другого конца коридора впереди другая комната);
  ловушка и её обезвреживание принадлежат коридору — найденную с любого конца можно обезвредить с любого.
- «Тяги»: подсказки раздаются уже перерезанными (входят в `hidden.cut`). Бросить игру, не задев натянутую, — без урона.

**Кто в мини-игре (FEAT-176).** `members[].busy` в состоянии — вид игры, которую участник сейчас играет (из
`dungeon:session:{sid}:challenge:{cid}`); брошенная игра перестаёт показываться через `time_limit_ms` + 10 с
(без часов — через 3 мин). Фронт держит его свежим по WS `challenge_started` / `challenge_finished` и рисует
значок над фигуркой и строку в рамке отряда; `challenge_started` несёт `busy_ms` — когда снять значок, если о конце игры так и не сообщат. Броски кубика не показываются — они решаются сразу.

**Бой забега в БД (FEAT-176, миграция 009).** `dungeon_sessions.battle_mob_ids`, `pending_target_room_id`,
`pending_corridor_id` — мобы боя и (для засады в коридоре) куда шёл отряд; источник истины — БД, Redis — зеркало,
`ensure_redis_state` восстанавливает их. Проигрыш без прерывания = все живые участники побеждены (вайп).
Передача лидерства AFK-лидера: БД — в транзакции действия, Redis и `leader_changed` — `after_commit()` (выбрасываются,
если транзакция не закоммичена).

**Оформление 3D-стола (FEAT-176).** `dungeons.theme` (VARCHAR(32), по умолчанию `stone`) — стены, пол и свет:
`stone`, `temple`, `cave`, `ice`, `volcano`, `catacombs`, `mine`, `sewer` (`schemas.DUNGEON_THEMES`);
`dungeons.floor_themes` (JSON) — `{"2": "volcano"}`, своё оформление этажа, остальные берут `theme`. Пустой объект
хранится как NULL. Оба поля отдаются в админских ответах и в состоянии забега (`theme`, `floor_themes`). Миграция 008.
Текстуры рисуются на фронте (`DungeonBoard3D/themePaint.ts`, настройки света — `dungeonThemes.ts`); 2D-карта не меняется.

### Этажи

`dungeon_rooms.floor` (1 — верхний). Коридор `passage_type`: `corridor` (внутри этажа), `stairs` (двусторонняя),
`drop` (только вниз, `is_bidirectional` всегда false), `lift` (двусторонний, обычно заперт). Лестница, провал и
подъёмник соединяют только соседние этажи — это проверяют create/update коридора и `validate`. Провал со
`passage_config.hidden` — ловушка: группа оказывается в его комнате (любым путём) → проверка `stat_check`
(по умолчанию intelligence) против `difficulty` (12); успех — `drop_spotted`, провал становится обычным выходом;
неудача — урон `fail_damage` (15) и падение этажом ниже (`room_event` `teleported` с `fell: true`). Найденный
провал (любым исходом) больше не срабатывает (`unlocked_corridor_ids`); до этого его нет в выходах и на карте.
Замок может открываться рычагом: `lock_config.lever`, рычаг — `room_config.lever_corridor_id` в любой комнате,
действие `pull_lever` (один раз за забег). Глубина: `dungeons.floor_mob_step` / `floor_loot_step` /
`floor_flee_step` — прибавка за каждый этаж ниже первого к силе мобов, шансам добычи из сундуков и шансу
потерять стопку при побеге (не выше 95%). Состояние отдаёт `floors`, `current_room.floor`, у выходов `passage` и
`to_floor`.

Действия с гонками (сундук, выбор события, торговец, воскрешение, дележ, finalize) берут
блокировку строки сессии/состояния комнаты; повтор получает `409`, золото не списывается дважды.
Внешние эффекты (золото, HP) — после коммита.

## API

### Админка (`require_permission`)
| Метод | Путь | Право |
|---|---|---|
| GET | `/dungeons/admin/dungeons`, `/dungeons/admin/dungeons/{id}` | `dungeons:view` |
| POST | `/dungeons/admin/dungeons` | `dungeons:create` |
| PUT | `/dungeons/admin/dungeons/{id}` | `dungeons:edit` |
| DELETE | `/dungeons/admin/dungeons/{id}` (409, если внутри группа) | `dungeons:delete` |
| POST/PUT/DELETE | комнаты, коридоры, `rooms/positions` | `dungeons:edit` |
| POST | `/dungeons/admin/dungeons/{id}/validate` | `dungeons:view` |
| POST | `/dungeons/admin/dungeons/{id}/generate` (FEAT-177; 409 без `replace` при наличии комнат и если внутри группа) | `dungeons:edit` |
| GET | `/dungeons/admin/sessions` (по умолчанию — незакрытые) | `dungeons:view` |
| DELETE | `/dungeons/admin/sessions/{id}` (любой статус, снимает блокировки) | `dungeons:edit` |
| GET | `/dungeons/admin/dungeons/{id}/status` (откат после зачистки, группа внутри) | `dungeons:view` |
| DELETE | `/dungeons/admin/dungeons/{id}/cooldown` (восстановить сразу: Redis + `cooldown_until` в БД) | `dungeons:edit` |

Валидация: `location_id` должен существовать в `Locations`; `room_config` проверяется и при
обновлении (против итогового типа комнаты); цели телепорта (комната и исходы событий) — комнаты
того же подземелья; `grid_w`/`grid_d` — 2..8 (`422 «Размер комнаты должен быть от 2 до 8 клеток»`).
`validate` дополнительно ругается на боевые комнаты без мобов и телепорты в никуда. Комната ядра маны без коридоров
не считается недостижимой (в неё ведёт путь, открытый после босса).

**Генератор (FEAT-177, `generator.py`, тексты — `generator_texts.py`).** `generate` строит черновик: этажи
(1–5), комнат на этаже (4–20), уровень, размер группы, сложность (`easy`/`normal`/`hard`), оформление, ключи и
замки, тайники/испытания, свои списки мобов/боссов/предметов, `seed` (тот же seed — та же карта). Чистая функция
`generate(params, catalog)` → план; `crud.generate_dungeon` удаляет старые комнаты и коридоры, пишет новые и
выключает подземелье (`is_active=false`). Каталог мобов и предметов читается напрямую из `mob_templates` и `items`
(только чтение, как `Locations`). Гарантии: главный путь (вход → лестницы → босс) не заперт и не скрыт, на нём на
каждом этаже есть бой; замки и тайные ходы закрывают только ответвления (и, иногда, дверь босса); ключ лежит вне
закрытых ответвлений на этаже двери или выше; решётки и печати — только на необязательных ответвлениях без ключей
(отряду без воина/мага они не мешают); комнаты — соседние клетки сетки 180 px. Сложность проверок
`(8 + 3.5·уровень)·k`, урон `(8 + 2·уровень)·k`.

### Игрок (JWT)
| Метод | Путь | Ответ |
|---|---|---|
| GET | `/dungeons/at-location/{location_id}` | список + `is_on_cooldown`, `cooldown_remaining_seconds`, `is_occupied` |
| POST | `/dungeons/{id}/sessions` `{character_id}` | соло-вход, `SessionResponse` (уже `active`) |
| POST | `/dungeons/{id}/party-run` `{character_id}` | вход отрядом, `SessionStateResponse` (+ `skipped_members`) |
| POST | `/dungeons/sessions/{id}/enter` | устаревший второй шаг, просто возвращает состояние |
| GET | `/dungeons/sessions/{id}/state?character_id=` | `SessionStateResponse` |
| POST | `/dungeons/sessions/{id}/move` `{character_id, corridor_id}` | `MoveResponse` |
| POST | `/dungeons/sessions/{id}/interact` `{character_id, action, ...}` | `InteractResponse` |
| POST | `/dungeons/sessions/{id}/pick-lock` `{character_id, corridor_id}` | `PickLockResponse` |
| POST | `/dungeons/sessions/{id}/flee` | `FleeResponse` |
| POST | `/dungeons/sessions/{id}/give` `{character_id, target_character_id, item_id, quantity}` | FEAT-178: лидер во время забега отдаёт найденный расходник в походный рюкзак живого участника (inventory-service `backpack/add`); 409 — нет рюкзака/места, предмет остаётся у отряда |
| POST | `/dungeons/sessions/{id}/distribute-loot` | `DistributeLootResponse` (+ `failed`); получатели — только живые участники (иначе 400) |
| POST | `/dungeons/sessions/{id}/finalize` `{character_id, force}` | `FinalizeResponse` (+ `items_lost`) |
| GET | `/dungeons/my-session/{character_id}` | только свой персонаж (или admin/moderator): `{in_dungeon, session_id, pending_loot_session_id}` |

Приглашения (`/invite`) и выход из формирующейся группы (`/leave`) удалены — группа = отряд.

Ошибки входа: `409` занято / уже в подземелье / без сознания, `403` откат / нет поста «Данж» /
чужой персонаж, `400` не на локации / не лидер отряда / неактивно, `404` нет подземелья.

### Internal (`X-Internal-Token`, nginx отдаёт 403 снаружи)
* `GET /dungeons/internal/character-session/{character_id}` — по БД.
* `POST /dungeons/internal/battle-callback` `{battle_id, session_id, winner_team, defeated_characters, aborted}`.

## WebSocket `/dungeons/ws/{session_id}?token=`

Только участники. Клиент шлёт `heartbeat`; сервер — `ping` каждые 30 с. Переподключение
регистрирует новый сокет и закрывает старый; уходящий обработчик удаляет только свой сокет.

| `type` | `data` |
|---|---|
| `session_status` | `status`, `phase`, `message`; при прохождении `cooldown_until`; при побеге `items_lost[]`, `items_remaining[]`, `reason`; при вайпе `knocked_out_until`, `location_id`; при закрытии `finalized: true` |
| `room_entered` | `room`, `corridor_event`, `room_event`, `stamina_consumed`, `teleported` |
| `battle_started` | `battle_id`, `room_id`, `room_name`, `corridor_id`, `mob_character_ids`, `mob_names` |
| `battle_ended` | `battle_id`, `party_won`, `aborted`, `casualties`, `boss_cleared`, `mana_core_revealed`, `room_event` |
| `member_status_changed` | `character_id`, `name`, `status` (= `new_status`) |
| `trap_triggered` | `passed`, `stat_check`, `difficulty`, `best_character`, `best_value`, `damage`, `damage_report`, `message` |
| `loot_added` | `items[{item_id,item_name,quantity}]`, `item_name` (через запятую), `source`, `message` |
| `event_result` | `outcome_type`, `message`, `loot_gained`, `damage_taken`, `effect_applied`, `teleported_to`, (`battle_id`, `mob_names`) |
| `rest_started` / `rest_completed` | параметры отдыха |
| `mana_core_revealed` / `mana_core_result` | комната ядра / `destroyed`, `loot`, `returned_to_room_id` |
| `leader_changed` | `new_leader_character_id`, `message` |
| `key_found` | `key`, `source`, `message` |
| `lock_picked` | `corridor_id`, `passed`, `message` |
| `lever_pulled` | `room_id`, `message` |
| `party_vote` | `room_id`, `votes[]` (`character_id`, `corridor_id`, `portal`), `waiting_for[]` |
| `party_ping` | `character_id`, `kind` (go/danger/look), `room_id`, `corridor_id` |
| `challenge_started` | `character_id`, `name`, `kind`, `corridor_id` |
| `challenge_finished` | `ChallengeResult`: `passed`, `kind`, `outcome`, `message`, `corridor_id`, `character_id`, `rolled`, `difficulty`, `block` (щит), `loot` (обыск) |
| `chat_message` | строка чата/журнала (`ChatEntry`) |
| `room_lit` | `character_id`, `name`, `how` (`spell`/`torch`), `room_id`, `message` |
| `loot_distributed` | `distributions`, `failed`, `remaining_count` |
| `item_given` | `target_character_id`, `target_name`, `item_id`, `item_name`, `quantity` (FEAT-178) |

## Фазы (`SessionStateResponse.phase`)

`exploring`, `resting`, `in_battle`, `battle_pending`, `distributing_loot`, `wiped`, `finished`.

## Межсервисные связи

* character-service: профиль (`character_name`, `activity_lock`), блокировки (`/internal/activity-lock/*`),
  спавн/удаление мобов, золото.
* character-attributes-service: атрибуты, выносливость, `recover` (лечение и урон отрицательным значением).
* inventory-service: выдача предметов, названия предметов.
* battle-service: `POST /battles/internal/dungeon`, `GET /battles/internal/{id}/state|result`; обратно — колбэк.
* party-service: состав отряда на локации. locations-service: пост-намерение «Данж».

## Тесты

`app/tests/`, pytest `--asyncio-mode=auto`. `dungeon_harness.py` гоняет **настоящий** `gameplay.py`
на SQLite с in-memory Redis и фейковыми соседями. `conftest.py` принудительно завершает процесс
(`os._exit`) после прогона из-за пулов aiomysql; `PYTEST_NO_FORCE_EXIT=1` оставляет отчёт
(процесс может не выйти сам — запускайте с `timeout`).
