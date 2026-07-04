# FEAT-143: Групповые бои — выбор цели, отображение команд, party-лобби

## Meta

| Field | Value |
|-------|-------|
| **Status** | IN_PROGRESS |
| **Created** | 2026-07-04 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-143-slug.md` → `DONE-FEAT-143-slug.md`

> **Примечание.** Файл заведён задним числом. Основная реализация уже закоммичена
> в `main` (см. раздел «Что уже сделано»), но фича работает нестабильно
> («криво») и не была доведена до REVIEW. Этот файл нужен, чтобы вернуть работу
> в трекинг, зафиксировать известные баги и довести групповые бои до рабочего
> состояния — как пререквизит для опор боевого движка под пассивки подклассов
> (см. `docs/SUBCLASS-PASSIVES.md`).

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Расширяем боёвку с формата «1 на 1» до **групповых боёв**: две команды, у каждого
участника — своя сторона, ход идёт по кругу со скипом мёртвых, победа считается
по команде (жива хотя бы одна сторона). Игрок должен **выбирать конкретную цель**
из вражеской команды, а не бить «следующего по кругу». NPC (autobattle) тоже
выбирают цель. До боя группа собирается через **party-лобби** на странице локации
(приглашения, ожидание, старт).

Это первая из опор боевого движка, нужных для пассивок подклассов. Порядок опор
(из `docs/SUBCLASS-PASSIVES.md`): **таргетинг → загрузка пассивок в бой → таргет
союзника → контроль → мультицель**. Данная фича закрывает таргетинг + групповую
инфраструктуру (команды в состоянии боя, party-лобби), на которую опираются
остальные опоры.

### Бизнес-правила
- Бой имеет две команды (стороны). Участник принадлежит одной стороне.
- Победа/поражение считаются **по команде**, а не по одному персонажу.
- Мёртвые участники пропускаются в очереди ходов.
- Атакующий выбирает цель из живых противников; при отсутствии выбора —
  поведение по умолчанию (нужно зафиксировать, см. Edge Cases).
- Группа собирается до боя в party-лобби; смена локации = выход из пре-боевой пати.

### UX / Пользовательский сценарий
1. На странице локации игрок открывает party-лобби, приглашает союзников.
2. Приглашённые видят панель входящих приглашений, принимают.
3. Стартует групповой бой; на `BattlePage` показаны обе команды (раскладка).
4. В свой ход игрок выбирает цель из вражеской команды и применяет навык/атаку.
5. Бой идёт до победы одной из команд.

### Edge Cases
- Что если у выбранной цели не осталось HP к моменту хода? → цель невалидна.
- Что если игрок не выбрал цель? → default target.
- Что если участник вышел/дисконнект в бою?
- Что если все члены party покинули лобби до старта?
- Что если игрок сменил локацию, находясь в пати? → выход из пати (реализовано).

### Вопросы к пользователю (если есть)
- [ ] Точный список «криво работает» симптомов → Ответ: _(заполнить)_

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

> TODO: заполнить после диагностики. Ниже — карта уже затронутого кода
> (реконструирована из git-истории коммитов, а не из свежего анализа).

### Affected Services
| Service | Type of Changes | Files |
|---------|----------------|-------|
| battle-service | targeting, team win, dead-skip, party lobby backend, state | `app/main.py`, `app/models.py`, `app/schemas.py`, `app/config.py`, `app/alembic/versions/005_add_battle_parties.py` |
| autobattle-service | NPC target selection | `app/main.py`, `app/strategy.py` |
| locations-service | leave pre-battle party on location change | `app/main.py`, `app/config.py` |
| frontend | team layout + target selection UI, party lobby UI | `components/pages/BattlePage/BattlePage.tsx`, `BattlePage/BattlePageBar/BattlePageBar.tsx`, `components/pages/LocationPage/PartyLobbyModal.tsx`, `PendingPartyInvitesPanel.tsx`, `BattlesSection.tsx`, `LocationPage.tsx`, `api/party.ts`, `hooks/useWebSocket.ts` |

### Cross-Service Dependencies
```
frontend ──HTTP──> battle-service (party lobby, battle state, actions)
frontend ──WS────> battle-service / notification (party + battle events)
autobattle-service ──> battle-service (NPC turns, target selection)
locations-service ──> battle-service (leave party on location change)
```

### DB Changes
- New tables: battle parties (миграция `005_add_battle_parties.py`, battle-service).
- Migrations: Alembic — да, уже настроен в battle-service? **Проверить** (по CLAUDE.md
  battle-service числился «без Alembic»; миграция 005 существует — уточнить статус).

### Risks
- Групповые бои закоммичены без FEAT-файла и без прохождения Reviewer.
- Нет зафиксированного списка багов — симптомы «криво» надо воспроизвести.
- battle-service — async (aiomysql + Motor + aioredis); состояние боя в Redis.
- Изменение формата `/state` уже ломало победу на старте (fix `96de746`) — регресс-риск.

---

## 3. Architecture Decision (filled by Architect — in English)

> Уже реализовано; раздел заполнить/актуализировать при доводке. Ключевые контракты:
> состояние боя `/state` теперь содержит команды (team), экшены принимают target,
> party-лобби эндпоинты в battle-service.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 0 | Reconstruct current state + reproduce & list bugs («криво») | Codebase Analyst | TODO | battle/autobattle/frontend | — | Bug list confirmed in §6 |
| 1 | Fix confirmed group-battle bugs (targeting / team display / turn flow) | Backend + Frontend Dev | TODO | tbd | #0 | Group battle runs clean end-to-end |
| 2 | Tests for group battle flow (targeting, team win, dead-skip) | QA Test | TODO | `services/battle-service/app/tests/*`, `services/autobattle-service/app/tests/*` | #1 | pytest pass |
| 3 | Review + live verification | Reviewer | TODO | all | #1, #2 | Checklist passed, live OK |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

_(pending)_

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-07-04 — PM: заведён FEAT-файл задним числом. Реализация групповых боёв
      (таргетинг, раскладка команд, party-лобби, NPC target) уже в main —
      коммиты 1296d07, e17c2dd, fc3a7ba, a67b39f, 2d3cfd5, 60a1151, fix 96de746.
      Фича работает нестабильно, не проходила Reviewer. Статус IN_PROGRESS.
      Следующий шаг — зафиксировать конкретные баги «криво» и починить.
[LOG] 2026-07-04 — Backend Dev: гибридная очередь ходов реализована и покрыта
      тестами (301 passed). См. раздел «Очередь ходов».
[LOG] 2026-07-04 — Frontend Dev: UX-пакет из 5 пунктов выполнен (выносливость,
      наглядность хода + очередь-аватарки, фикс истории, читаемый лог, пейсинг).
      Backend: событие skill_use. vite build OK, 0 новых tsc-ошибок, 301 passed.
      Требуется визуальная приёмка вживую.
[LOG] 2026-07-04 — Frontend/Backend Dev: правки по замечаниям к скрину img_143:
      (1) подложка карточки — min-h контейнеру инвентаря, кнопки секций больше не
      торчат; (2) эффекты на участнике — EffectCircle мигрирован на .tsx, читаемые
      русские описания (кровотечение «2 хода, −20 HP/ход» вместо англ. «Изменение
      уронаBleeding 20%»); (3) лог — событие apply_effects теперь несёт
      нормализованные эффекты (backend), модификатор описывается по существу.
      Общий helper describeEffect (battleEffects.ts). Build OK, 0 новых tsc-ошибок,
      301 passed.
[LOG] 2026-07-04 — Backend Dev: правки боевой логики по замечаниям (img_144/145):
      (A) уклонение теперь один бросок на ВСЮ атаку, а не на каждый damage_entry —
      больше нет «уклонился» рядом с прошедшим ударом (battle_engine apply_dodge,
      бросок в main); (B) свеженаложенный эффект НЕ тикает на ходу наложения
      (buffs fresh-флаг) — длительность в активных эффектах совпадает с логом.
      Новые тесты test_dodge_and_freshness.py (6), обновлены 12 mock-сетапов
      (roll_dodge=False). Весь набор: 307 passed.
      ВАЖНО: сложные эффекты (Кровотечение/Ожог/Яд) сейчас НЕ наносят периодический
      урон — только висят и тикают (см. docs/SUBCLASS-PASSIVES.md, опора «контроль/
      сложные эффекты»). Тултип показывает «−20 HP/ход», но урона нет. Нужна отдельная
      задача на реализацию периодического урона, если требуется.
[LOG] 2026-07-04 — Backend/Frontend Dev: реализован ПЕРИОДИЧЕСКИЙ УРОН (DoT) для
      сложных эффектов — Кровотечение / Ожог / Яд(периодический). buffs.tick_periodic_effects
      тикает на ходу владельца эффекта (перед декрементом, свежие пропускаются),
      наносит magnitude HP цели, шлёт событие effect_tick; смерть от DoT ловится
      проверкой гибели. Фронт рендерит «<цель> Кровотечение −20». Тесты +5
      (TestPeriodicDamage). Весь набор: 312 passed. Build OK, 0 новых tsc-ошибок.
      Ещё не реализованы: сложные модификаторы (ArmorBreak, Freeze, Daze, Wet,
      Electrify, MagicImpact, Holy, Curse) и КОНТРОЛЬ (Stun, Knockdown, Windburn,
      Poison-паралич) — следующий этап.
[LOG] 2026-07-04 — Backend/Frontend Dev: реализована ГРУППА A (модификаторы) —
      buffs.aggregate_modifiers раскрывает сложные эффекты в движковые каналы:
      ArmorBreak/Freeze/Electrify → −резисты, Daze/Wet → −исходящий урон,
      Holy/Curse → ±первичные атрибуты. MagicImpact уже работал через attribute_key.
      Тултип (battleEffects.ts) показывает верную единицу (%/HP-ход/±/контроль).
      +9 тестов (TestComplexModifiers).
[LOG] 2026-07-04 — Backend/Frontend Dev: реализована ГРУППА B (контроль) —
      buffs.evaluate_control + энфорс в обработчике действия: Stun/Poison-паралич
      обнуляют весь ход (событие control_skip), Knockdown/Windburn блокируют тип
      навыка (control_block). Фронт: лог-события + баннер «Оглушение — ход
      пропущен», блокировка слотов, кнопка «Пропустить ход». +7 тестов
      (TestControlEffects). Обновлено 18 mock-сетапов (evaluate_control по умолчанию).
      Итого backend 328 passed, build OK, 0 новых tsc-ошибок.
      СЛОЖНЫЕ ЭФФЕКТЫ РЕАЛИЗОВАНЫ ПОЛНОСТЬЮ (DoT + модификаторы + контроль).
      Осталось из опор движка: загрузка пассивок персонажа в бой, таргет союзника
      (саппорт), ловкость→инициатива — см. docs/SUBCLASS-PASSIVES.md.
[LOG] 2026-07-04 — Backend/Frontend Dev: ИНИЦИАТИВА + ПЕРВЫЙ КРУГ.
      Очередь: инициатор всегда первый, дальше по инициативе (без чередования
      команд). Инициатива = ловкость×1.0 + (сила+инт)×0.75 (выносливость не в счёт).
      `build_hybrid_turn_order` переписан, `compute_initiative` в redis_state.
      Первый круг (до 2-го хода инициатора): только 1 тип навыка/ход
      (first_cycle_limit_skills), предметы свободны; фронт блокирует слоты + баннер.
      first_cycle проброшен в runtime. Строка «Инициатива» добавлена в профиль
      (DerivedStatsSection). Тесты обновлены под инициативу + TestFirstCycleLimit.
      Backend 334 passed, build OK, 0 новых tsc-ошибок. Опора «ловкость→инициатива»
      ЗАКРЫТА.
```

### Что уже сделано (в main, до заведения файла)

| Commit | Слой | Описание |
|--------|------|----------|
| `1296d07` | battle-service | phase 1 — таргетинг, победа по команде, скип мёртвых (+ `test_battle_fixes.py`) |
| `e17c2dd` | frontend | phase 2 — раскладка команд + выбор цели (`BattlePage.tsx` переписан) |
| `fc3a7ba` | autobattle-service | phase 3 — выбор цели для NPC (+ `test_strategy.py`) |
| `a67b39f` | battle-service | backend party-лобби (миграция `005_add_battle_parties`, модели, схемы) |
| `2d3cfd5` | locations-service | выход из пре-боевой пати при смене локации |
| `60a1151` | frontend | UI party-лобби (`PartyLobbyModal`, `PendingPartyInvitesPanel`, `api/party.ts`) |
| `96de746` | fix | групповой бой ложно «выигрывался» на старте (в `/state` не было team) |

### Уточнение от пользователя (2026-07-04)

Критических багов нет — групповые бои работают. Реальная проблема — **UX/визуал**:
неинтуитивно для рядового игрока. Собран отдельный список из 5 задач по улучшению
(выносливость в бою, хайлайт «чей ход» + очередь-аватарки, авто-прыжок истории,
читаемость лога, замедление смены ходов). См. раздел ниже.

### Очередь ходов — решение и реализация (DONE)

**Решение (гибрид, зафиксировано пользователем):**
- инициатор всегда ходит первым;
- команды **чередуются**, начиная с команды инициатора;
- внутри команды порядок — по **убыванию ловкости** (`agility`), ничьи → порядок
  добавления;
- очередь **считается один раз на старте** и не пересчитывается (бафы статов не
  влияют); мёртвый просто пропускает ход.

**Реализация (battle-service):**
- `redis_state.build_hybrid_turn_order()` — чистая функция построения очереди.
- `init_battle_state()` пишет `turn_order` через неё (единый источник истины).
- Продвижение хода (`main.py`, обработчик `action`) переведено с `participants.keys()`
  на `turn_order` — устранён потенциальный рассинхрон между реальным ходом и превью
  «кто следующий» (`next_pid_after` уже читал `turn_order`).
- `agility` добавлена в `participants_payload` во всех 3 путях создания боя (public
  create / PvP-invite / party-start).
- Тесты: `tests/test_redis_state.py::TestBuildHybridTurnOrder` (7 кейсов) — весь набор
  battle-service **301 passed**.
- Существующие бои в Redis не мигрируются (порядок фиксируется на старте) — новый
  порядок применяется только к новым боям.

### UX-пакет из 5 пунктов — DONE (2026-07-04)

1. **Выносливость убрана из боя** — `BattlePage.tsx` `getResources` больше не кладёт
   `stamina`; в карточках остаются HP / мана / энергия.
2. **Наглядность хода:**
   - таймер вынесен в отдельный блок сверху (`BattlePageBar.tsx`);
   - под именем текущего ходящего — **живая очередь аватарок** (`turnQueue`,
     строится из `turn_order` + `current_actor`, скип мёртвых, обновляется в
     реальном времени);
   - карточки участников в блоке: **полузолотистый** у того, чей сейчас ход,
     тёмный у остальных (`BattlePage.tsx`, обе команды).
3. **История ходов больше не «шакалит»** — авто-прыжок на последний ход отключён,
   пока пользователь читает старый ход (`followLatestRef`); кнопка «К последнему».
   В кругляшах истории — **аватар ходившего** + номер хода бейджем.
4. **Читаемый лог** (`formatBattleEvent`):
   - типы урона — **иконки** (эмодзи `DAMAGE_TYPE_ICONS`) с подписью на hover;
   - «попал» больше не пишется; показываются только промахи, причём два разных:
     `уклонился` (dodge врага) и `промахнулся` (низкий шанс навыка);
   - **выводятся использованные навыки** — backend шлёт событие `skill_use`
     (`who`, `skill_id`, `kind`), фронт резолвит имя навыка из снапшота;
   - убраны формульные поля (base_attack / after_buffs / resist_pct и т.п.),
     остался компактный `источник → цель  <иконка> −N  крит`.
5. **Пейсинг ходов** — быстрые последовательные апдейты состояния разносятся во
   времени (`enqueueState`/`drainStates` в `BattlePage.tsx`, мин. зазор 1100мс):
   первый/idle-апдейт применяется сразу, всплеск ходов (напр. авто-моб) —
   по одному, чтобы движение ходов было видно.

**Backend:** `main.py` — событие `skill_use` в начале обработки хода.
**Проверка:** `vite build` — OK; `tsc --noEmit` — 0 новых ошибок (baseline HEAD
имел те же 7 предсуществующих ошибок по `.jsx`-пропсам); battle-service **301 passed**.
**Осталось:** визуальная приёмка вживую (изменения преимущественно визуальные —
нужен взгляд пользователя на реальном бою).

---

## 7. Completion Summary (filled by PM on close — in Russian)

_(pending)_
