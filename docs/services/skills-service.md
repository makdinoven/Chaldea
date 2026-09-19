# skills-service

**Порт:** 8003
**Технологии:** FastAPI (async), SQLAlchemy (async, aiomysql), httpx
**Путь:** `/home/dudka/chaldea/services/skills-service/`

## Назначение

Управление навыками, перками навыков (FEAT-125), деревьями классов. CRUD для базового урона/эффектов навыков и для перков. Назначение навыков персонажам, прокачка уровня (0..4), выбор перков, сброс с 24-часовым cooldown.

## FEAT-125 — система перков (актуальная модель)

С FEAT-125 ранги навыков (`SkillRank`) полностью удалены. Вместо ветвящегося DAG ранги заменены на плоский **пул перков**:

- Навык покупается на **уровне 0** с базовыми статами (`Skill.cost_energy/cost_mana/cooldown/level_requirement` + `skill_base_damage[]` + `skill_base_effects[]`).
- Игрок может прокачать его до уровня 4 (`upgrade_cost = floor(skill.purchase_cost / 2)` за каждое улучшение, списывается из active_experience).
- Каждое улучшение даёт 1 свободное очко перка. Игрок выбирает один перк из пула навыка. Один перк нельзя взять дважды.
- Финальные статы навыка = база + Σ дельт всех выбранных перков (cooldown floored at 0; level_requirement фиксирован базой).
- Сброс: уровень → 0, выбранные перки удаляются, опыт **не возвращается**, 24h cooldown на повторный сброс этого навыка.
- Минимум 4 перка в пуле (валидация на DELETE).
- `delta_level_requirement` поля **нет** — character-level gate не меняется.
- Resolver `GET /skills/{id}/resolved?character_id=...` — единственный авторитативный источник финальных статов; принимает либо JWT владельца / админа, либо `INTERNAL_SERVICE_TOKEN` от battle-service.
- **Required env var:** `INTERNAL_SERVICE_TOKEN` — общий секрет для service-to-service авторизации (FEAT-125). В dev есть дефолт в `docker-compose.yml`. В prod читается строго из `.env` на VPS — должен быть выставлен до FEAT-125 cutover.

## Структура файлов

```
skills-service/app/
├── main.py               # FastAPI app, все эндпоинты
├── models.py             # 5 SQLAlchemy моделей
├── schemas.py            # Pydantic схемы
├── crud.py               # CRUD-операции
├── config.py             # Настройки
├── database.py           # Async SQLAlchemy
├── auth_http.py          # JWT через user-service, internal-токен, get_optional_user (FEAT-171)
├── visibility.py         # FEAT-171: асинхронный can_view_private / require_private_access
├── rabbitmq_consumer.py  # ЗАКОММЕНТИРОВАН
└── requirements.txt
```

## API Endpoints (FEAT-125)

### Admin: Skills
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/skills/admin/skills/` | Создать навык |
| GET | `/skills/admin/skills/` | Все навыки |
| GET | `/skills/admin/skills/{id}` | Навык по ID |
| PUT | `/skills/admin/skills/{id}` | Обновить навык |
| DELETE | `/skills/admin/skills/{id}` | Удалить навык |

### Admin: Skill Perks (NEW)
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/skills/admin/skills/{skill_id}/perks` | Создать перк |
| GET  | `/skills/admin/skills/{skill_id}/perks` | Список перков навыка |
| GET  | `/skills/admin/skill_perks/{perk_id}` | Получить перк |
| PUT  | `/skills/admin/skill_perks/{perk_id}` | Обновить перк (replace damage/effects) |
| DELETE | `/skills/admin/skill_perks/{perk_id}` | Удалить перк (409 если пул < 4) |

### Admin: Skill Base Damage / Effects (NEW)
| Метод | Путь | Описание |
|-------|------|----------|
| POST/PUT/DELETE | `/skills/admin/skills/{skill_id}/base_damage[/{id}]` | Базовый урон навыка |
| POST/PUT/DELETE | `/skills/admin/skills/{skill_id}/base_effects[/{id}]` | Базовые эффекты навыка |

### Player / Public
| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/skills/{skill_id}` | public | Навык + полный пул перков (`SkillWithPerksRead`) |
| GET | `/skills/{skill_id}/resolved?character_id=...` | JWT (owner/admin) или `INTERNAL_SERVICE_TOKEN` | Server-authoritative финальные статы (`ResolvedSkillRead`) |
| GET | `/skills/characters/{cid}/skills` | `allow_jwt_or_service_token` + `can_view_private` (FEAT-171, S1) | Список навыков персонажа в новой плоской форме |
| POST | `/skills/characters/{cid}/skills/{sid}/upgrade` | JWT owner | Поднять уровень (cost = floor(purchase_cost/2)) |
| POST | `/skills/characters/{cid}/skills/{sid}/perks/{perk_id}` | JWT owner | Выбрать перк |
| POST | `/skills/characters/{cid}/skills/{sid}/reset` | JWT owner | Сброс (24h cooldown, нет возврата опыта) |

### Admin: Character Skills
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/skills/admin/character_skills/` | Назначить навык на уровне (admin form) |
| PUT  | `/skills/admin/character_skills/{cs_id}` | `{skill_id, level}` |
| DELETE | `/skills/admin/character_skills/{cs_id}` | Убрать навык |
| DELETE | `/skills/admin/character_skills/by_character/{cid}` | Bulk delete |

### Прочее
- `POST /skills/assign_multiple` — body `{character_id, skills:[{skill_id}]}` (без `rank_number`). **FEAT-169:** маршрут разложен на два, тело общее (`_assign_multiple_core`):
  - `POST /skills/internal/assign_multiple` — `Depends(verify_internal_token)`, для character-service (выдача пресетов при одобрении заявки). Пустой `INTERNAL_SERVICE_TOKEN` → 503, чужой/отсутствующий заголовок `X-Internal-Token` → 401.
  - `POST /skills/assign_multiple` — `require_permission("skills:create")`, для админского редактора НПС (`NpcStatsEditor.tsx`): он раздаёт навыки чужому персонажу, поэтому проверка владения здесь невозможна. Разрешение уже существует (то же, что у `POST /skills/admin/character_skills/`) — новой строки в `permissions` не заводили.
- `POST /skills/` (legacy «Basic Attack») — **FEAT-169:** `Depends(verify_internal_token)`. `character_id` приходит в теле, поэтому открытый маршрут позволял навесить навык любому персонажу. Единственный вызывающий — character-service `crud.send_skills_request`.
- Class-tree эндпоинты (FEAT-056/057) без изменений; `purchase_skill` теперь вставляет CharacterSkill(skill_id, level=0); 409 "Навык уже есть" если уже куплен.
- Удалены: `/skills/admin/skill_ranks/*`, `/skills/admin/damages/*`, `/skills/admin/effects/*`, `/skills/skill_ranks/{id}`, `/skills/character_skills/upgrade` (старая форма), `/skills/admin/skills/{id}/full_tree`, `/skills/skills/{id}/full_tree`.

## Видимость приватных данных персонажа (FEAT-171)

`app/visibility.py` — **асинхронный** близнец общего предиката из FEAT-171 §3.1 (ещё три
синхронные копии живут в character-service, character-attributes-service и inventory-service;
согласованность держится параметризованным тестом-матрицей, а не общим пакетом):

- `await can_view_private(db, character_id, user)` — 404 «Персонаж не найден», если персонажа нет
  (проверяется ПЕРВОЙ); `user_id IS NULL` (НПС/моб) → `True`; владелец → `True`;
  admin/moderator с разрешением `characters:read` → `True`; иначе `False`.
- `await require_private_access(...)` — жёсткая обёртка, 403 «Эти данные доступны только
  владельцу персонажа».

`auth_http.get_optional_user` (+ `OAUTH2_SCHEME_OPTIONAL`) возвращает `None` вместо 401.
Синхронная `def` — FastAPI уводит её в threadpool, event loop не блокируется.

`main.require_character_skills_access(db, character_id, viewer)` — готовый предикат для
`GET /skills/characters/{cid}/skills`: `viewer is None` означает вызов по сервисному токену
(`allow_jwt_or_service_token`, battle-service уже его шлёт) и пропускается всегда, реальный
пользователь проверяется через `can_view_private`.

**Pass B — гейт стоит.** `GET /skills/characters/{cid}/skills` объявляет
`viewer=Depends(allow_jwt_or_service_token)` и первым делом зовёт
`require_character_skills_access`. Матрица ответов:

| Кто | Ответ |
|-----|-------|
| сервис с общим токеном в позиции Bearer (battle-service) | 200, вызывающих менять не пришлось |
| владелец персонажа | 200 |
| admin/moderator с `characters:read` | 200 |
| NPC/моб (`user_id IS NULL`) | 200 для любого вошедшего |
| чужой игрок | 403 «Эти данные доступны только владельцу персонажа» |
| гость (токена нет совсем) | 401 — зависимость требует Bearer |
| несуществующий персонаж | 404 «Персонаж не найден» (проверяется до владения) |

`GET /skills/class_trees/{tree}/progress/{cid}` был закрыт раньше и не тронут;
справочники навыков и подклассов остаются публичными.

## Таблицы БД (FEAT-125)

### skills
- id, name (unique), skill_type, description, class/race/subrace_limitations, min_level, purchase_cost, skill_image
- **NEW:** cost_energy, cost_mana, cooldown, level_requirement (бывшие поля rank-0)

### skill_base_damage (NEW)
- id, skill_id (FK CASCADE), damage_type, amount (Float), description, weapon_slot, target_side, chance

### skill_base_effects (NEW)
- id, skill_id (FK CASCADE), target_side, effect_name, description, chance, duration, magnitude (Float), attribute_key

### skill_perks (NEW)
- id, skill_id (FK CASCADE), name, description, perk_image, sort_order, created_at
- delta_cost_energy, delta_cost_mana, delta_cooldown (signed Int, nullable). **Нет delta_level_requirement.**

### skill_perk_damage / skill_perk_effects (NEW)
- Те же поля что у `skill_base_*`, но FK на `skill_perks.id`.

### character_skills (REBUILT)
- id, character_id (int, soft ref), **skill_id (FK skills.id CASCADE)**, **level TINYINT 0..4**, **reset_available_at DATETIME nullable**, created_at
- UNIQUE (character_id, skill_id). Колонка `skill_rank_id` удалена.

### character_skill_perks (NEW)
- id, character_skill_id (FK CASCADE), skill_perk_id (FK CASCADE), selected_at
- UNIQUE (character_skill_id, skill_perk_id) — гарантирует что один перк не выбран дважды.

### Удалённые таблицы
`skill_ranks`, `skill_rank_damage`, `skill_rank_effects` — удалены в Alembic 003.

## Резолвер навыков

`crud.resolve_character_skill(db, character_id, skill_id)` — server-authoritative. Возвращает dict с теми же полями `damage_entries[*]` / `effects[*]`, что и старый `SkillRankRead` (R1 byte-compat для battle-service):
- `cost_energy = max(0, base + Σ delta)`
- `cost_mana = max(0, base + Σ delta)`
- `cooldown = max(0, base + Σ delta)`
- `level_requirement` = base (фиксирован)
- `damage_entries`, `effects` — конкатенация base + всех выбранных перков (порядок: base, потом перки в порядке выбора).
- 404 — навык/персонаж не найден; 409 — у персонажа нет этого навыка.

## Типы урона

physical, catting, crushing, piercing, magic, fire, ice, watering, electricity, wind, sainting, damning

## Коммуникация

### HTTP (исходящие)
- `character-attributes-service:8002` -> GET `/attributes/internal/{id}` (баланс активного опыта; **FEAT-171: двойник A1i + `X-Internal-Token`** — публичный `GET /attributes/{id}` стал приватным, а у этого вызова нет пользователя в контексте), PUT `/attributes/{id}/active_experience` (списание за покупку/прокачку навыка; FEAT-167: обязателен заголовок `X-Internal-Token`, хелпер `main._internal_token_headers()` читает `INTERNAL_SERVICE_TOKEN` из env в момент вызова), POST `/attributes/cumulative_stats/increment` (счётчик `skills_used` при улучшении навыка; FEAT-167 задача #17: тот же заголовок. Вызов fire-and-forget, поэтому потеря заголовка была бы молчаливой — покрыт тестом `tests/test_internal_headers.py`)
- `character-service:8005` -> GET `/characters/{id}/race_info`
- `inventory-service:8004` -> POST `/inventory/internal/characters/{id}/revalidate-equipment` (FEAT-169: обязателен заголовок `X-Internal-Token`, хелпер `main._internal_token_headers()`; вызов только логирует ошибку, поэтому потеря заголовка была бы молчаливой)

### RabbitMQ
Полностью закомментирован.

## Известные проблемы

1. **Нет аутентификации** - admin/* эндпоинты доступны всем
2. **Нет валидации ограничений** - class/race/subrace limitations хранятся, но не проверяются при назначении
3. **Level requirements не проверяются** при upgrade
4. **Стоимость навыков не списывается** - TODO в коде
5. **character_id не FK** - soft reference, возможны orphaned records
6. **RabbitMQ закомментирован** - aio_pika в зависимостях
