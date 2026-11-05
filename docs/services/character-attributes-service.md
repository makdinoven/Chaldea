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
| POST | `/attributes/` | Создать атрибуты для персонажа. FEAT-196: необязательные `level`, `id_class` в теле (не хранятся в строке атрибутов, только для прибавки ресурсов за уровень; не переданы → читаются из `characters`, нет строки → без прибавки) |
| GET | `/attributes/{character_id}` | Получить все атрибуты. **FEAT-171 (A1): приватно** — владелец, админ/модератор с `characters:read`, NPC |
| GET | `/attributes/{character_id}/passive_experience` | Пассивный опыт. **FEAT-171 (A4): приватно** |
| POST | `/attributes/{character_id}/upgrade` | Прокачать статы (тратит stat points). Тело `StatsUpgradeRequest`: 10 статов + `stealth` (FEAT-201), каждое поле `Field(0, ge=0)` — отрицательное значение → 422 |
| POST | `/attributes/{character_id}/apply_modifiers` | **internal** (FEAT-167): применить модификаторы (экипировка/баффы); FEAT-195: основные статы со снаряжения тоже двигают производные |
| POST | `/attributes/{character_id}/recalculate` | Админ (`characters:update`): абсолютный пересчёт производных с учётом снаряжения/перков/еды (FEAT-195). Инвентарь недоступен → 502 «Не удалось получить снаряжение персонажа» |
| POST | `/attributes/admin/recalculate_all` | Админ (`characters:update`): то же для всех персонажей батчами по 100 → `{"detail", "count", "skipped": [id...]}` (FEAT-195) |
| POST | `/attributes/{character_id}/recover` | **internal** (FEAT-167): восстановить ресурсы (health/mana/energy/stamina) |
| PUT | `/attributes/{character_id}/active_experience` | **internal** (FEAT-167): изменить активный опыт |
| PUT | `/attributes/{character_id}/passive_experience` | **internal** (FEAT-167): изменить пассивный опыт |
| POST | `/attributes/{character_id}/consume_stamina` | **internal** (FEAT-167): потратить стамину (с блокировкой строки) |
| POST | `/attributes/{character_id}/refund_stamina` | **internal** (FEAT-167): вернуть стамину (FEAT-128) |
| GET | `/attributes/{character_id}/rest-status` | FEAT-164: состояние восстановления в покое и активная сытость. **FEAT-171 (A5): приватно** |
| POST | `/attributes/internal/{character_id}/satiety` | FEAT-164, internal: применить сытость (вызывает inventory-service `/eat-food`). **FEAT-169: `X-Internal-Token`** |
| POST | `/attributes/internal/settle-regen` | FEAT-164, internal: досчитать восстановление для списка персонажей (до 50 id). **FEAT-169: `X-Internal-Token`** |
| POST | `/attributes/internal/{character_id}/reconcile-perks` | FEAT-143, internal: пересчёт активности перков. **FEAT-169: `X-Internal-Token`** |
| GET | `/attributes/internal/{character_id}` | **FEAT-171 (A1i):** двойник `GET /attributes/{character_id}` для межсервисных вызовов (общий хелпер `_build_full_attributes`, тело идентично). `X-Internal-Token`, fail-closed. Вызывающие — battle-service, character-service, locations-service, skills-service |
| POST | `/attributes/internal/{character_id}/sync-level` | **FEAT-196**, internal (`X-Internal-Token`), без тела: перечитать `level`/`id_class` из `characters` и выставить максимумы ресурсов (см. «Рост ресурсов за уровень»). 404 «Атрибуты персонажа не найдены», 500 «Не удалось обновить ресурсы персонажа». Ответ `{character_id, level, id_class, max_health, max_mana, max_energy, max_stamina}`. Вызывающий — character-service |
| GET | `/attributes/internal/{character_id}/passive_experience` | **FEAT-171 (A4i):** двойник `GET /attributes/{character_id}/passive_experience` (общий хелпер `_build_passive_experience`). `X-Internal-Token`. Вызывающий — character-service (`full_profile`) |

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
- **На игровых GET'ах нет `verify_internal_token`:** `GET /attributes/{id}` и
  `GET /attributes/{id}/rest-status` доигрывают восстановление FEAT-164, и
  соседние сервисы читают их двойники, а не эти пути. Не тронуты
  `POST /{id}/upgrade` (JWT) и `/attributes/admin/*` (RBAC).
- **Двойники закрыты `verify_internal_token`:** GET `/attributes/internal/{id}`
  и GET `/attributes/internal/{id}/passive_experience` — чтобы соседние сервисы
  не потеряли данные после того, как FEAT-171 Pass B закрыл игровые GET'ы.

### Дополнение (FEAT-169) — три `/attributes/internal/*`

`POST /internal/settle-regen`, `POST /internal/{id}/satiety` и
`POST /internal/{id}/reconcile-perks` держались только на правиле nginx.
Теперь на каждом висит тот же `verify_internal_token` с той же fail-closed
семантикой (пустой токен → 503, чужой/отсутствующий → 401, русский `detail`).

Вызывающие (все посылают заголовок): party-service `crud.settle_regen`
(settle-regen), inventory-service (`/eat-food` → satiety; equip/unequip →
reconcile-perks, sync и async), character-service (reconcile-perks).

**Внутрипроцессные вызовы `reconcile_perks` не затронуты** — это прямые
вызовы Python-функции из `GET /{id}/perks`, из апгрейда и из `regen.py`,
они не проходят через HTTP-зависимость.

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

`GET /attributes/{character_id}/cumulative_stats` — чтение профиля; FEAT-167
его не трогал, **FEAT-171 (A3) закрыл его гейтом видимости** (там суммы
заработанного и потраченного золота).

Nginx вторым слоем: точные блоки `location = /attributes/cumulative_stats/increment`
и `location = /attributes/` с `limit_except GET HEAD` в обоих конфигах. Именно
точное совпадение — под префиксом `/attributes/` живут все игровые роуты.

## Приватность чтений (FEAT-171, Pass B)

Пять игровых GET'ов закрыты «жёстким гейтом» (стиль B из §3.2 фичи):

| Путь | Что закрывает |
|------|---------------|
| `GET /attributes/{id}` | ресурсы, урон, уклонение, крит, 13 сопротивлений + 13 уязвимостей, активный и пассивный опыт |
| `GET /attributes/{id}/perks` | дерево перков и прогресс по нему |
| `GET /attributes/{id}/cumulative_stats` | счётчики, включая заработанное/потраченное золото |
| `GET /attributes/{id}/passive_experience` | пассивный опыт |
| `GET /attributes/{id}/rest-status` | состояние восстановления и сытости |

Механика одна на все пять: `Depends(get_optional_user)` (JWT необязателен,
невалидный токен даёт `None`, а не 401) + `visibility.require_private_access`
из `app/visibility.py` — копии §3.1 фичи, побайтово совпадающей с
character-service, inventory-service и (в async-варианте) skills-service.

Порядок проверок важен: **сначала существование персонажа**, и только потом
владение, иначе 403/404 работали бы как оракул.

- персонажа нет → `404 «Персонаж не найден»`;
- `characters.user_id IS NULL` (NPC/моб) → доступ **разрешён всем** (Q6: у NPC
  нет приватного слоя, на этом держатся бестиарий и модалка NPC);
- владелец → разрешено;
- `role in ("admin", "moderator")` **и** `characters:read` в разрешениях →
  разрешено. Отдельно проверено: админская синхронизация уровня в
  character-service (`app/main.py`, ветка `if "level" in update_data`) читает
  `/attributes/{id}/passive_experience`, **пробрасывая JWT администратора**, —
  этот путь под гейтом проходит;
- остальные (гость, чужой игрок) → `403 «Эти данные доступны только владельцу
  персонажа»`.

Межсервисные вызывающие сюда не ходят — у них двойники `/attributes/internal/*`
(Pass A). Админские `/attributes/admin/*` не тронуты.

**Известное, намеренно не чинится здесь (§3.4 D8):** `GET /attributes/{id}/perks`
**пишет в БД** (`reconcile_perks` внутри GET). Гейт только сужает круг тех, кто
может это запустить; превращение маршрута в read-only — отдельная задача из
`docs/ISSUES.md`.

## Восстановление в покое и сытость (FEAT-164)

Логика — `app/regen.py`, константы — `app/constants.py` (`REGEN_PERCENT_PER_HOUR`, `SATIETY_DURATION_HOURS`, `SATIETY_REGEN_BONUS_BY_RARITY`).

- **Скорость:** 5% от максимума в час реального времени для здоровья, маны, энергии и выносливости; не выше максимума.
- **Лениво, без фоновых задач:** `settle_regen(db, attr)` вызывается под блокировкой строки (`with_for_update`) во всех путях чтения/записи: `GET /{id}`, `GET /{id}/rest-status`, `recover`, `apply_modifiers`, `consume_stamina`, `refund_stamina`, `upgrade`, `PUT /admin/{id}`, `internal/{id}/reconcile-perks`, `internal/{id}/satiety`, `internal/settle-regen`. Ответ `GET /{id}` не изменился (новые колонки не отдаются).
- **Учёт времени:** `character_attributes.regen_anchor_at` — момент последнего пересчёта (NULL = часы ещё не запущены; первый пересчёт запускает их без ретро-лечения). `regen_carry_*` — дробный остаток на ресурс, поэтому частые чтения не «съедают» восстановление.
- **Занятость (восстановление не идёт):** из общей БД берутся интервалы — бой (`battle_participants.joined_at`/`battles.created_at` … `dropped_out_at` или «сейчас» для активного боя), подземелье (только `dungeon_sessions.status='active'`, `started_at` … `finished_at`; лобби `forming` = покой), сбор (`gathering_sessions.started_at` … `finished_at`/`complete_at`). Время покоя = окно минус объединение интервалов. `now`/начало окна передаются bind-параметрами. Ошибка чтения интервалов логируется (ERROR), восстановление не начисляется, якорь не сдвигается.
- **Конец боя:** battle-service при синхронизации ресурсов ставит `regen_anchor_at = UTC_TIMESTAMP()`.
- **Мобы/NPC** (`characters.is_npc = 1`) и персонажи без строки в `characters` пропускаются.
- **Сытость** — таблица `character_satiety` (одна строка на персонажа, `UNIQUE(character_id)`): `item_id`, `source_item_name`, `rarity`, `regen_bonus`, `modifiers` (JSON), `started_at`, `expires_at` (24 ч, naive UTC). Бонус к восстановлению по редкости: обычная +50%, редкая +100%, эпическая +150%, легендарная +200%. Пока сытость активна, новая еда → 409 «Вы уже наелись». Модификаторы еды добавляются в базовые колонки как у экипировки (FEAT-195: с производными бонусами, через `apply_attribute_modifiers`) и вычитаются при первом пересчёте после `expires_at` (строка удаляется в той же транзакции), затем выполняется reconcile перков. Если сытость закончилась посреди окна, до `expires_at` считается с бонусом, после — без.
- **Святилище дома** (FEAT-180 6б): благословение `regen` из `house_buffs` (locations-service; `source='shrine'`,
  `kind='regen'`) умножает покой на (1 + value) до своего `expires_at` — так же, как окно сытости (`regen.
  get_shrine_regen`, в `_effective_hours` складывается с сытостью и сном). locations-service досчитывает реген
  перед каждой молитвой, поэтому окно от якоря до конца благословения целиком «благословлённое». Нет таблицы —
  без бонуса. `rest-status` учитывает его в `regen_percent_per_hour` и отдаёт `shrine_regen_bonus` (доля) и
  `shrine_regen_until`.

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
Тело: `{item_id, source_item_name, rarity, modifiers: {...}, recovery: {health_recovery, mana_recovery, energy_recovery, stamina_recovery}, duration_hours}`. `duration_hours` (FEAT-180 6а, необязательно, 1..72, по умолчанию 24) — сколько держится сытость: inventory-service присылает больше, если под рукой кухня дома; вне диапазона → 422. Ответ 201 `{satiety, stats_changed}`. Ошибки: 400 «Недопустимая редкость еды» / недопустимые модификаторы / отрицательное восстановление; 404; 409 «Вы уже наелись». Одна транзакция: блокировка → пересчёт → проверка → модификаторы → мгновенное восстановление → запись сытости.

### `POST /attributes/internal/settle-regen`
Тело `{"character_ids": [1, 2]}` (1..50 уникальных) → `{"settled": [...], "missing": [...]}`; каждый id в своей короткой транзакции. Вызывается party-service перед чтением ресурсов участников.

**Откат миграции 008:** перед `downgrade` снять активные бонусы: `UPDATE character_satiety SET expires_at = UTC_TIMESTAMP();`, затем `POST /attributes/internal/settle-regen` для всех `character_id` из таблицы.

## Скрытность (FEAT-201, миграция 009)

- **Миграция `009_add_stealth`** (revises `008_add_regen_and_satiety`): `character_attributes.stealth INT NOT NULL
  DEFAULT 0`; существующие строки получают 0; идемпотентна (`_has_column`). Downgrade — `DROP COLUMN stealth`.
- 11-й первичный стат, хранится как **сумма** (очки + снаряжение + еда + перки), как остальные первичные. Через
  `apply_attribute_modifiers` автоматически работают прокачка, экипировка (заточка, камни, прочность), плоские бонусы
  перков (`VALID_FLAT_BONUS_KEYS`), сытость и её истечение. `rebuild_derived_stats` первичные не трогает, поэтому
  `/recalculate` скрытность не меняет. Кап FEAT-195 применяется при чтении (в character-service).
- Схемы: `CharacterAttributesBase.stealth = Field(0, ge=0)` — **дефолт 0, а не 1** (как у `charisma`/`luck`), чтобы
  новый персонаж не получал бесплатное очко; `create_character_attributes` пишет `stealth or 0`; `AdminAttributeUpdate.stealth`;
  ответ `/upgrade` (`updated_attributes`) содержит `stealth`; `stealth` есть в `attr_fields` прогресса перков.
- Бонус подклассов (Ассасин / Фокусник / Агент) сюда **не записывается** — его добавляет character-service в момент броска.

## Модель CharacterAttributes

Все коэффициенты ниже — за **эффективную** единицу стата `eff(x)` (FEAT-195, см. раздел «Убывающая отдача статов»).

### Ресурсы (current + max)
- `health` (base 100, +10 за point) — `max = 100 + floor(10·eff(health)) + level·rate`
- `mana` (base 75, +10 за point) — `max = 75 + floor(10·eff(mana)) + level·rate`
- `energy` (base 50, +5 за point) — `max = 50 + floor(5·eff(energy)) + level·rate`
- `stamina` (base 100, +5 за point) — `max = 100 + floor(5·eff(stamina)) + level·rate`

`level·rate` — прибавка за уровень по классу (FEAT-196, раздел ниже).

### Прокачиваемые статы
- `strength` -> +0.1 ко всем 4 физическим сопротивлениям
- `agility` -> +0.1 к dodge
- `intelligence` -> +0.1 ко всем 8 магическим сопротивлениям
- `endurance` -> +0.2 к res_effects
- `luck` -> +0.1 к critical_hit_chance, dodge и res_effects
- `charisma` -> скидка у торговцев 0.1 % за эффективную единицу (считается в `econ_core.charisma_discount_pct`, не хранится)
- `stealth` (FEAT-201, «Скрытность») -> **производных полей нет** (в `PRIMARY_ATTRIBUTE_KEYS`, но не в `PRIMARY_DERIVED_EFFECTS`, как харизма). Снижает шанс, что преступление заметят, и даёт шанс бегства от стражи / побега из тюрьмы — считает character-service по своим настройкам (`shadow_settings`, см. `docs/services/character-service.md`, раздел «Shadow»). В бою ничего не даёт

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

## Убывающая отдача статов (FEAT-195)

`app/stat_caps.py` (каноническая копия; байт-в-байт копии в battle-service, dungeon-service и character-service (FEAT-199),
сверяет `scripts/check_econ_copies.sh`): `eff(x) = x` до 100, `100 + (x−100)·0.5` до 200,
`150 + (x−200)·0.25` выше (250 → 162.5, 530 → 232.5; отрицательные — линейно). Число стата
в профиле не меняется — режется только то, во что оно превращается. Кап берётся от **суммы**
всех источников (очки + снаряжение с заточкой/камнями + еда + перки).

**Инвариант хранения.** Производное поле = `BASE + плоские бонусы + Σ k·eff(итоговый стат)`.
Единственный путь изменения — `crud.apply_attribute_modifiers(attr, modifiers)`: основной
стат `+= Δ`, его производные `+= k·(eff(new) − eff(old))`, ресурсы `max/current +=
floor(m·eff(new)) − floor(m·eff(old))`, остальные ключи — простое сложение. Через него идут
прокачка (`/upgrade`), снаряжение (`/apply_modifiers`), перки (`_apply_modifiers_internal`)
и еда (наедание и истечение). Дельты телескопируются, поэтому снятие предмета ровно отменяет
надевание при любых промежуточных изменениях. Параметра `propagate_derived` больше нет —
снаряжение и еда теперь тоже дают производные (раньше давали только очки и перки).

**Пересчёт с нуля.** `crud.rebuild_derived_stats(db, attr, equipment_mods)` — абсолютная,
идемпотентная сборка: плоские бонусы = надетое (`POST /inventory/internal/equipment-modifiers`)
+ все перки + активная еда; сопротивления/уклонение/крит/res_effects и `max_*` выставляются по
формуле, `current_*` только урезается до максимума. Не трогает основные статы, `damage`,
`critical_damage`, `vul_*` (старый пересчёт обнулял урон и бонусы предметов — исправлено).
`compute_derived_stats` используется только при создании строки (нет снаряжения/перков/еды).

**Выкатка на прод:** один раз вызвать `POST /attributes/admin/recalculate_all` (JWT админа) и
проверить, что `skipped` пустой; повторный запуск безопасен.

## Рост ресурсов за уровень (FEAT-196)

`max_R = BASE_R + floor(m_R·eff(R)) + level·rate(class, R)` — слагаемое за уровень **вне** `eff`
(это не стат, кап FEAT-195 его не режет). Уровень 1 уже даёт прибавку. Подкласс не влияет.

| Класс (`id_class`) | здоровье | мана | энергия | выносливость |
|---|---|---|---|---|
| 1 Воин | **15** | 10 | 10 | 10 |
| 2 Плут | 10 | 10 | **15** | 10 |
| 3 Маг | 10 | **15** | 10 | 10 |

Константы — `constants.py` (`MAIN_RESOURCE_PER_LEVEL`, `OTHER_RESOURCE_PER_LEVEL`,
`CLASS_MAIN_RESOURCE`, `LEVEL_RESOURCE_GROWTH`), зеркало на фронте —
`src/utils/resourceGrowth.ts`. `crud.level_resource_bonus(resource, class_id, level)`:
неизвестный/`None` класс или уровень `None`/`< 1` → 0, без ошибки.

Где применяется:
- **Создание** (`POST /attributes/`): уровень и класс из тела (строка `characters` у вызывающего
  ещё только `flush()`-нута и не видна), иначе `SELECT level, id_class FROM characters`, иначе без
  прибавки. Текущие = максимум.
- **Смена уровня/класса** — `POST /attributes/internal/{id}/sync-level` (`crud.sync_level_resources`):
  блокировка строки → досчёт восстановления по старому максимуму → `get_level_and_class` →
  абсолютная цель `T`. Рост максимума двигает текущее на ту же разницу (как вложение очков,
  без доп. долечивания), падение (админ понизил уровень) — обрезает текущее до `T`.
  Идемпотентен, без хранимого «применённого уровня», без миграций.
- **Пересчёт** (`rebuild_derived_stats`: `/recalculate`, `/admin/recalculate_all`) читает
  уровень и класс из `characters` — абсолютно; ошибка SQL не глотается (батч → `skipped`).
- **`apply_attribute_modifiers`** не менялся: постоянное слагаемое сокращается в дельте.
- **Мобы и NPC** — те же строки `characters`/`character_attributes`; множитель данжа
  (`mob_multiplier`) масштабирует только базовые статы, не уровень.

**Выкатка:** тот же единственный `recalculate_all` из FEAT-195 начисляет прибавку всем
игрокам, NPC и мобам задним числом (текущие не доливаются — их наполнит восстановление).
Откат: вернуть код и снова `recalculate_all`.

## Система прокачки (upgrade)

1. HTTP -> character-service: получить stat_points персонажа
2. Проверить достаточно ли points (`total_needed` — сумма всех 11 полей запроса, включая `stealth`; 0 → 400 «No stats to upgrade»). Все поля `StatsUpgradeRequest` — `Field(0, ge=0)` (FEAT-201): отрицательное значение → 422; раньше `{"strength": -20, "agility": 21}` списывало 1 очко и переносило 20 очков между статами (тест `test_upgrade_negative_points.py`)
3. Применить вложенные очки через `crud.apply_attribute_modifiers` (FEAT-195: с убывающей отдачей)
4. HTTP -> character-service: списать stat_points
5. Используется `with_for_update()` для блокировки строки (race condition protection)

## Коммуникация

### HTTP (исходящие)
- `inventory-service:8004` -> POST `/inventory/internal/equipment-modifiers` (**FEAT-195**: сумма модификаторов надетого для `recalculate` / `recalculate_all`, заголовок `X-Internal-Token`; строка атрибутов заблокирована на время запроса)
- `character-service:8005` -> GET `/characters/{id}/full_profile` (stat points)
- `character-service:8005` -> PUT `/characters/internal/{id}/deduct_points` (списание points, заголовок `X-Internal-Token`)
- `character-service:8005` -> POST `/characters/internal/{id}/logs` (запись в журнал персонажа, заголовок `X-Internal-Token`)
- `character-service:8005` -> GET `/characters/internal/{id}/full_profile` (**FEAT-171**, C1i: уровень и баланс золота при разборе условий перков — `perk_evaluator._fetch_character_level` / `_fetch_gold_balance`, и проверка доступных stat points в `POST /{id}/upgrade`). Заголовок `X-Internal-Token`; в `perk_evaluator` — из локального `_internal_token_headers()`. Ошибка в `perk_evaluator` проглатывается (WARNING, в тексте лога теперь назван URL двойника), поэтому тест обязан проверять сам факт отправки заголовка
- `locations-service:8006` -> GET `/locations/quests/internal/check-completed` (проверка выполненного задания при разборе условий перков, `perk_evaluator._fetch_quest_completed`; FEAT-170: с `X-Internal-Token`). Заголовок строится **локальным** `perk_evaluator._internal_token_headers()` из `config.settings.INTERNAL_SERVICE_TOKEN` — импортировать хелпер из `main.py` нельзя, `main` подключает `perk_evaluator` лениво именно из-за цикла импорта. Ошибка вызова проглатывается (WARNING) и перк просто не открывается, поэтому тест обязан проверять сам факт отправки заголовка

### RabbitMQ
Полностью закомментирован.

## Известные проблемы

1. **Опечатки в названиях полей** - `res_catting` (вероятно `res_cutting`), `res_watering` (вероятно `res_water`), `res_sainting` (вероятно `res_holy`)
2. **Нет валидации в apply_modifiers** - принимает произвольный dict, может установить отрицательные значения
3. **Нет constraints в БД** - current_* поля могут стать отрицательными
4. **Float precision** - сопротивления используют Float без явного округления
5. **Неиспользуемые URL** - SKILLS_SERVICE_URL, USER_SERVICE_URL определены, но не используются (INVENTORY_SERVICE_URL используется пересчётом с FEAT-195)

### reconcile_perks: сначала решения, потом записи (2026-10-16)

Условия всех перков вычисляются до того, как пишется хоть одно переключение. Проверка золота
(и квестов) ходит в другие сервисы, а character-service отвечает, вызывая этот же сервис, — его
запрос пишет ту же строку `character_attributes`, которую блокирует переключение перка. Раньше
решение принималось внутри цикла записей: каждое надевание/снятие, переключавшее перк, висело
5 с до таймаута HTTP (на проде у персонажа с перком «Знания правят миром»), а проверка золота по
таймауту считалась «условие не выполнено». Следствие: перк, открытый другим перком в том же
пересчёте, включится на следующем пересчёте.

## Сон в доме (FEAT-180)

`regen.get_sleep` читает `characters.asleep_since` / `sleep_regen_factor` (колонки character-service,
пишет их locations-service). Часы отдыха после засыпания умножаются на множитель спальни (×2 / ×2.5 / ×3),
сытость складывается сверху, время боя/подземелья/добычи по-прежнему не считается (`_effective_hours`).
locations-service досчитывает восстановление (`/internal/settle-regen`) перед тем, как уложить персонажа и
перед пробуждением, поэтому весь отрезок от якоря (или от засыпания) — сон. `GET /{id}/rest-status`
отдаёт `asleep_since`, а `regen_percent_per_hour` уже включает множитель сна. Тесты:
`tests/test_house_sleep_regen.py`.
