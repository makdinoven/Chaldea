# locations-service

**Порт:** 8006
**Технологии:** FastAPI (async), SQLAlchemy (async, aiomysql), httpx
**Путь:** `/home/dudka/chaldea/services/locations-service/`

## Назначение

Игровой мир: страны, регионы, районы, локации. Граф локаций (соседи с cost перемещения). Перемещение персонажей. Посты/чат в локациях.

## Структура файлов

```
locations-service/app/
├── main.py        # FastAPI app, все роуты
├── models.py      # 6 SQLAlchemy моделей
├── schemas.py     # Pydantic схемы (обширные)
├── crud.py        # Бизнес-логика
├── config.py      # Настройки
└── database.py    # Async SQLAlchemy
```

## API Endpoints (~25 штук)

### Lookup (для выпадающих списков)
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/locations/lookup` | id+name всех локаций |
| GET | `/districts/lookup` | id+name всех районов |
| GET | `/countries/lookup` | id+name всех стран |

### Countries
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/countries/create` | Создать страну |
| PUT | `/countries/{id}/update` | Обновить страну |
| GET | `/countries/list` | Список стран |
| GET | `/countries/{id}/details` | Страна с регионами |

### Regions
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/regions/create` | Создать регион |
| PUT | `/regions/{id}/update` | Обновить регион |
| GET | `/regions/{id}/details` | Регион с полной иерархией |
| DELETE | `/regions/{id}/delete` | Каскадное удаление |

### Districts
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/districts` | Создать район |
| PUT | `/districts/{id}/update` | Обновить район |
| GET | `/districts/{id}/details` | Район с локациями |
| GET | `/districts/{id}/locations` | Локации района |
| DELETE | `/districts/{id}/delete` | Каскадное удаление |

### Locations
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/` | Создать локацию |
| PUT | `/locations/{id}/update` | Обновить локацию |
| GET | `/locations/{id}/details` | Локация с соседями и потомками |
| GET | `/locations/{id}/children` | Дочерние локации |
| DELETE | `/locations/{id}/delete` | Рекурсивное каскадное удаление |

### Neighbors (граф)
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/{id}/neighbors/` | Создать двустороннюю связь |
| GET | `/locations/{id}/neighbors/` | Соседи локации |
| DELETE | `/locations/{id}/neighbors/{neighbor_id}` | Удалить связь |
| POST | `/locations/{id}/neighbors/update` | Заменить всех соседей |

### Посты
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/posts/` | Создать пост в локации |
| GET | `/locations/{id}/posts/` | Посты в локации (newest first) |

### Клиентские / Admin
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/locations/admin/data` | Вся иерархия для админ-панели |
| GET | `/locations/{id}/client/details` | Данные локации для клиента (соседи, игроки, посты, **gathering_nodes** с lazy-restore + lazy-finalize) |
| POST | `/locations/{id}/move_and_post` | Перемещение + создание поста |

### Добыча ресурсов (FEAT-128)

#### Player-facing
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/{location_id}/gathering-nodes/{node_id}/start` | Начать добычу. Списывает стамину полностью, создаёт сессию, авто-постит «{name} начинает добычу: {ресурс}». Rate-limit 10 req/min, burst 5 (Nginx) |
| POST | `/locations/{location_id}/gathering-nodes/{node_id}/cancel` | Ручная отмена. Возвращает `ceil(stamina_paid/2)` стамины |
| GET | `/locations/characters/{character_id}/active_gathering` | Polling-эндпоинт для активной сессии. Lazy-finalize при `complete_at <= NOW()`, в этом ответе вернёт `last_finished_session` с deltами |

#### Admin (require_permission `gathering:<action>`)
| Метод | Путь | Permission |
|-------|------|-----------|
| GET | `/locations/admin/locations/{location_id}/gathering-nodes` | `gathering:read` |
| POST | `/locations/admin/locations/{location_id}/gathering-nodes` | `gathering:create` |
| PUT | `/locations/admin/gathering-nodes/{node_id}` | `gathering:update` |
| DELETE | `/locations/admin/gathering-nodes/{node_id}` | `gathering:delete` (cascade на sessions) |
| POST | `/locations/admin/gathering-nodes/{node_id}/restore` | `gathering:update` (мгновенный refill) |

#### Internal (Header `X-Internal-Token: ${INTERNAL_SERVICE_TOKEN}`)
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/locations/internal/cancel-gathering` | Вызывается battle-service из `pvp_attack` ДО создания боя. Отмечает status=`interrupted_by_battle`, рефанд стамины |

## Иерархия мира

```
Country -> Region -> District -> Location
                                    ├── Location (child, type: subdistrict)
                                    └── Location (child)
```

Локации связаны **графом соседей** (LocationNeighbors) с `energy_cost` за переход.

## Таблицы БД

- **Countries** - id, name, description, leader_id, map_image_url
- **Regions** - id, name, country_id (FK), description, map_image_url, image_url, entrance_location_id, x, y
- **Districts** - id, name, region_id (FK CASCADE), description, image_url, entrance_location_id, recommended_level, x, y
- **Locations** - id, name, district_id (FK CASCADE), type (location/subdistrict), image_url, recommended_level, quick_travel_marker, parent_id (FK self CASCADE), description
- **LocationNeighbors** - id, location_id (FK CASCADE), neighbor_id (FK CASCADE), energy_cost
- **posts** - id, character_id, location_id (FK CASCADE), content, created_at
- **gathering_nodes** (FEAT-128) - id, location_id (FK Locations CASCADE), node_name, category enum(ore/herb/wood), result_item_id (cross-service, no FK), result_quantity_per_gather, stamina_per_gather, daily_bank_max, current_bank, allow_concurrent_gather, depleted_at, restore_at (= depleted_at+24h), is_enabled, created_at, updated_at
- **gathering_sessions** (FEAT-128) - id, node_id (FK gathering_nodes CASCADE), character_id, tool_inventory_item_id (nullable, no FK), tool_item_id, tool_durability_at_start, started_at, complete_at, effective_speed/double/stamina_bonus_pct (snapshot), stamina_paid, base_quantity, skill_slug, status enum(active/completed/cancelled/interrupted_by_battle/inventory_full), finished_at, result_quantity, xp_awarded, rank_up_to

## Перемещение (move_and_post)

1. HTTP -> character-service: получить текущую локацию персонажа
2. Валидация перемещения (null -> любая, та же -> бесплатно, иначе -> сосед?)
3. Найти energy_cost из LocationNeighbors
4. HTTP -> attributes-service: проверить стамину
5. Создать пост в целевой локации
6. HTTP -> character-service: обновить current_location
7. HTTP -> attributes-service: списать стамину

## Коммуникация

### HTTP (исходящие)
- `character-service:8005` -> GET `/characters/{id}/profile`, GET `/characters/by_location`, PUT `/characters/{id}/update_location`, GET `/characters/{id}/short_info` (для имени/аватара активных gatherers в client/details)
- `character-attributes-service:8002` -> GET `/attributes/{id}`, POST `/attributes/{id}/consume_stamina`, POST `/attributes/{id}/refund_stamina` (FEAT-128: 50% возврат при cancel/battle-interrupt)
- `inventory-service:8004` -> POST `/inventory/internal/characters/{cid}/free_slots_check` (preflight на старте), POST `/inventory/internal/characters/{cid}/gathering/award` (атомарный award на finalize: ресурс + XP + ранг + прочность инструмента), GET `/inventory/characters/{cid}/gathering-skills` (ранговые бонусы для расчёта effective_*)

### Lazy-finalize паттерн (FEAT-128)
- Сессии добычи завершаются «лениво» при доступе: `client/details` (по локации) и `active_gathering` (по персонажу) перед формированием ответа вызывают `finalize_due_sessions`, которая под `SELECT ... FOR UPDATE` обрабатывает все сессии с `status='active' AND complete_at <= NOW()`.
- Не требует Celery beat. Подобно `Character.travel_cooldown_until` — таймстемп проверяется на каждом запросе.

## Известные проблемы

1. **Нет валидации existence** destination_location_id в move_and_post
2. **update_location_neighbors** удаляет всех соседей перед созданием новых - не атомарно
3. **Нет валидации parent_id** при создании локации
4. **Молчаливые ошибки** - character-service failures возвращают пустые данные без warning
5. **CORS allow-all** в production
