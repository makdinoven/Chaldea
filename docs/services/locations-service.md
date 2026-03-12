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
| GET | `/locations/{id}/client/details` | Данные локации для клиента (соседи, игроки, посты) |
| POST | `/locations/{id}/move_and_post` | Перемещение + создание поста |

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
- `character-service:8005` -> GET `/characters/{id}/profile`, GET `/characters/by_location`, PUT `/characters/{id}/update_location`
- `character-attributes-service:8002` -> GET `/attributes/{id}`, POST `/attributes/{id}/consume_stamina`

## Известные проблемы

1. **Нет валидации existence** destination_location_id в move_and_post
2. **update_location_neighbors** удаляет всех соседей перед созданием новых - не атомарно
3. **Нет валидации parent_id** при создании локации
4. **Молчаливые ошибки** - character-service failures возвращают пустые данные без warning
5. **CORS allow-all** в production
