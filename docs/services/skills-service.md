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
| GET | `/skills/characters/{cid}/skills` | — | Список навыков персонажа в новой плоской форме |
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
- `POST /skills/assign_multiple` — body `{character_id, skills:[{skill_id}]}` (без `rank_number`).
- Class-tree эндпоинты (FEAT-056/057) без изменений; `purchase_skill` теперь вставляет CharacterSkill(skill_id, level=0); 409 "Навык уже есть" если уже куплен.
- Удалены: `/skills/admin/skill_ranks/*`, `/skills/admin/damages/*`, `/skills/admin/effects/*`, `/skills/skill_ranks/{id}`, `/skills/character_skills/upgrade` (старая форма), `/skills/admin/skills/{id}/full_tree`, `/skills/skills/{id}/full_tree`.

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
- Определены URL для character-service и attributes-service, но **не используются активно**

### RabbitMQ
Полностью закомментирован.

## Известные проблемы

1. **Нет аутентификации** - admin/* эндпоинты доступны всем
2. **Нет валидации ограничений** - class/race/subrace limitations хранятся, но не проверяются при назначении
3. **Level requirements не проверяются** при upgrade
4. **Стоимость навыков не списывается** - TODO в коде
5. **character_id не FK** - soft reference, возможны orphaned records
6. **RabbitMQ закомментирован** - aio_pika в зависимостях
