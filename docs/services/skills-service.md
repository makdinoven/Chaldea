# skills-service

**Порт:** 8003
**Технологии:** FastAPI (async), SQLAlchemy (async, aiomysql), httpx
**Путь:** `/home/dudka/chaldea/services/skills-service/`

## Назначение

Управление навыками, рангами навыков, деревьями навыков. CRUD для урона и эффектов навыков. Назначение навыков персонажам.

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

## API Endpoints (22 штуки)

### Admin: Skills
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/skills/admin/skills/` | Создать навык |
| GET | `/skills/admin/skills/` | Все навыки |
| GET | `/skills/admin/skills/{id}` | Навык по ID |
| PUT | `/skills/admin/skills/{id}` | Обновить навык |
| DELETE | `/skills/admin/skills/{id}` | Удалить навык |

### Admin: Skill Ranks
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/skills/admin/skill_ranks/` | Создать ранг |
| GET | `/skills/admin/skill_ranks/{id}` | Ранг по ID |
| PUT | `/skills/admin/skill_ranks/{id}` | Обновить ранг |
| DELETE | `/skills/admin/skill_ranks/{id}` | Удалить ранг |

### Admin: Damage & Effects
| Метод | Путь | Описание |
|-------|------|----------|
| POST/GET/PUT/DELETE | `/skills/admin/damages/...` | CRUD для записей урона |
| POST/GET/PUT/DELETE | `/skills/admin/effects/...` | CRUD для эффектов |

### Skill Trees
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/skills/admin/skills/{id}/full_tree` | Полное дерево навыка |
| PUT | `/skills/admin/skills/{id}/full_tree` | Обновить дерево (с temp ID mapping) |

### Character Skills
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/skills/characters/{id}/skills` | Навыки персонажа (с вложенными данными) |
| POST | `/skills/admin/character_skills/` | Назначить навык персонажу |
| DELETE | `/skills/admin/character_skills/{id}` | Убрать навык |
| POST | `/skills/character_skills/upgrade` | Прокачать/изучить навык |
| POST | `/skills/assign_multiple` | Массовое назначение навыков |

## Таблицы БД

### skills
- id, name (unique), skill_type, description, class/race/subrace_limitations, min_level, purchase_cost, skill_image

### skill_ranks
- id, skill_id (FK), rank_name, rank_number, left_child_id (FK self), right_child_id (FK self)
- cost_energy, cost_mana, cooldown, level_requirement, upgrade_cost
- class/race/subrace_limitations, rank_description, rank_image

### skill_rank_damages
- id, skill_rank_id (FK), damage_type, amount (float), weapon_slot, target_side, chance (0-100)

### skill_rank_effects
- id, skill_rank_id (FK), target_side, effect_name, chance, duration, magnitude (float), attribute_key

### character_skills
- id, character_id (int, не FK), skill_rank_id (FK)

## Дерево навыков

Бинарное дерево через `left_child_id` и `right_child_id` в SkillRank:
- Ранги образуют дерево прогрессии
- При прокачке: проверка конфликтов (если у родителя 2+ детей, они конфликтуют друг с другом)
- Full tree update поддерживает temporary ID (prefix "temp-") для новых рангов

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
