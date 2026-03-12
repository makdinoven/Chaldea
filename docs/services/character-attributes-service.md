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
| POST | `/attributes/` | Создать атрибуты для персонажа |
| GET | `/attributes/{character_id}` | Получить все атрибуты |
| GET | `/attributes/{character_id}/passive_experience` | Пассивный опыт |
| POST | `/attributes/{character_id}/upgrade` | Прокачать статы (тратит stat points) |
| POST | `/attributes/{character_id}/apply_modifiers` | Применить модификаторы (экипировка/баффы) |
| POST | `/attributes/{character_id}/recover` | Восстановить ресурсы (health/mana/energy/stamina) |
| PUT | `/attributes/{character_id}/active_experience` | Изменить активный опыт |
| POST | `/attributes/{character_id}/consume_stamina` | Потратить стамину |

## Модель CharacterAttributes

### Ресурсы (current + max)
- `health` (base 100, +10 за point)
- `mana` (base 75, +10 за point)
- `energy` (base 50, +5 за point)
- `stamina` (base 50, +5 за point)

### Прокачиваемые статы
- `strength` -> +0.1 к res_physical
- `agility` -> +0.1 к dodge
- `intelligence` -> +0.1 к res_magic
- `endurance` -> +0.1 к res_effects
- `luck` -> +0.1 к critical_hit_chance и dodge
- `charisma` -> (без автоматического бонуса)

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

## Система прокачки (upgrade)

1. HTTP -> character-service: получить stat_points персонажа
2. Проверить достаточно ли points
3. Применить множители за каждый вложенный point
4. HTTP -> character-service: списать stat_points
5. Используется `with_for_update()` для блокировки строки (race condition protection)

## Коммуникация

### HTTP (исходящие)
- `character-service:8005` -> GET `/characters/{id}/full_profile` (stat points)
- `character-service:8005` -> PUT `/characters/{id}/deduct_points` (списание points)

### RabbitMQ
Полностью закомментирован.

## Известные проблемы

1. **Опечатки в названиях полей** - `res_catting` (вероятно `res_cutting`), `res_watering` (вероятно `res_water`), `res_sainting` (вероятно `res_holy`)
2. **Нет валидации в apply_modifiers** - принимает произвольный dict, может установить отрицательные значения
3. **Нет constraints в БД** - current_* поля могут стать отрицательными
4. **Float precision** - сопротивления используют Float без явного округления
5. **Неиспользуемые URL** - INVENTORY_SERVICE_URL, SKILLS_SERVICE_URL, USER_SERVICE_URL определены, но не используются
