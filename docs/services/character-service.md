# character-service

**Порт:** 8005
**Технологии:** FastAPI, SQLAlchemy (sync), PyMySQL, httpx, aio_pika (не используется)
**Путь:** `/home/dudka/chaldea/services/character-service/`

## Назначение

Управление персонажами: создание (через заявки на модерацию), профили, уровни, титулы, расы/подрасы/классы.

## Структура файлов

```
character-service/app/
├── main.py               # FastAPI app, все эндпоинты
├── models.py             # SQLAlchemy модели (8 моделей)
├── schemas.py            # Pydantic схемы
├── crud.py               # CRUD и бизнес-логика
├── presets.py             # Пресеты: SUBRACE_ATTRIBUTES, CLASS_ITEMS, CLASS_SKILLS, SUBRACE_SKILLS
├── config.py             # Настройки из env
├── database.py           # Подключение к БД
├── rabbitmq_consumer.py  # ЗАКОММЕНТИРОВАН
├── tests/                # Pytest тесты (с ошибками в путях)
└── requirements.txt
```

## API Endpoints (20 штук)

### Заявки на создание персонажа
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/characters/requests/` | Создать заявку на персонажа |
| POST | `/characters/requests/{id}/approve` | Одобрить заявку (запускает полный workflow) |
| POST | `/characters/requests/{id}/reject` | Отклонить заявку |
| GET | `/characters/moderation-requests` | Все заявки на модерации |

### Управление персонажами
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/characters/{id}/full_profile` | Полный профиль с уровнем, атрибутами, титулом |
| GET | `/characters/{id}/profile` | Профиль с данными пользователя |
| GET | `/characters/{id}/short_info` | Краткая инфо (имя, аватар, локация) |
| GET | `/characters/{id}/race_info` | Раса, подраса, класс, уровень |
| GET | `/characters/list` | Список всех персонажей |
| DELETE | `/characters/{id}` | Удалить персонажа |
| PUT | `/characters/{id}/deduct_points` | Списать stat points |

### Локации
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/characters/by_location?location_id=X` | Персонажи в локации |
| PUT | `/characters/{id}/update_location` | Обновить текущую локацию |

### Титулы
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/characters/titles/` | Создать титул |
| GET | `/characters/titles/` | Все титулы |
| GET | `/characters/{id}/titles` | Титулы персонажа |
| POST | `/characters/{id}/titles/{title_id}` | Назначить титул |
| POST | `/characters/{id}/current-title/{title_id}` | Установить текущий титул |

### Метаданные
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/characters/metadata` | Все расы, подрасы с атрибутами |

## Таблицы БД

- **characters** - персонажи (name, race, subrace, class, level, stat_points, avatar, current_location_id, currency_balance)
- **character_requests** - заявки (status: pending/approved/rejected)
- **races** (7 рас) - Человек, Эльф, Драконид, Дворф, Демон, Бистмен, Урук
- **subraces** (16 подрас) - по 2-3 на расу
- **classes** (3) - Воин, Ловкач, Маг
- **titles** - титулы
- **character_titles** - many-to-many персонаж<->титул
- **level_thresholds** - таблица опыт->уровень

## Workflow создания персонажа (approve)

1. Создать запись `Character` из данных заявки
2. Сгенерировать атрибуты по подрасе (из `SUBRACE_ATTRIBUTES`)
3. Определить стартовую экипировку по классу (из `CLASS_ITEMS`)
4. HTTP -> **inventory-service**: создать инвентарь с предметами
5. Определить навыки: 3 по классу + 1 по подрасе (из `CLASS_SKILLS`, `SUBRACE_SKILLS`)
6. HTTP -> **skills-service**: назначить навыки
7. HTTP -> **character-attributes-service**: создать атрибуты
8. Обновить character.id_attributes
9. Статус заявки -> "approved"
10. HTTP -> **user-service**: создать связь user-character, установить current_character

## Система уровней

- `LevelThreshold` - таблица `level_number` -> `required_experience`
- При получении профиля: проверка `passive_experience` >= threshold -> level up
- **+10 stat points** за каждый уровень
- Опыт списывается при повышении уровня

## Коммуникация

### HTTP (исходящие)
- `inventory-service:8004` - POST `/` (создание инвентаря)
- `skills-service:8003` - POST `/assign_multiple` (назначение навыков)
- `character-attributes-service:8002` - POST `/`, GET `/{id}`, GET `/{id}/passive_experience`
- `user-service:8000` - POST `/users/user_characters/`, PUT `/users/{id}/update_character`, GET `/users/{id}`

### RabbitMQ
Полностью закомментирован. Ранее планировались очереди: `character_request_queue`, `character_inventory_queue`, `character_skills_queue`, `character_attributes_queue`

## Известные проблемы

1. **RabbitMQ отключён** - весь код закомментирован, aio_pika в зависимостях
2. **Тесты с неправильными путями** - `/character/requests/` вместо `/characters/requests/`
3. **Опыт не сохраняется** - `check_and_update_level()` уменьшает passive_experience локально, но не сохраняет в attributes-service
4. **Неиспользуемый код** - `send_equipment_slots_request()` ссылается на несуществующий EQUIPMENT_SERVICE_URL
5. **Нет аутентификации** на эндпоинтах
