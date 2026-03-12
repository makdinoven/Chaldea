# photo-service

**Порт:** 8001
**Технологии:** FastAPI, PyMySQL (raw SQL), boto3 (S3), Pillow (обработка изображений)
**Путь:** `/home/dudka/chaldea/services/photo-service/`

## Назначение

Загрузка, обработка и хранение изображений для всех сущностей системы: аватары пользователей и персонажей, карты, изображения локаций, навыков, предметов.

## Структура файлов

```
photo-service/
├── main.py          # FastAPI app, 13 эндпоинтов (251 строка)
├── crud.py          # SQL-операции через PyMySQL DictCursor (207 строк)
├── utils.py         # S3, конвертация изображений (131 строка)
├── requirements.txt
├── credentials/     # GCS credentials (не используется)
└── media/maps/      # Локальные файлы (legacy?)
```

## API Endpoints (13 штук)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/photo/change_user_avatar_photo` | Загрузить/обновить аватар пользователя |
| DELETE | `/photo/delete_user_avatar_photo` | Удалить аватар пользователя |
| POST | `/photo/change_character_avatar_photo` | Загрузить аватар персонажа |
| POST | `/photo/character_avatar_preview` | Превью аватара персонажа |
| POST | `/photo/user_avatar_preview` | Превью аватара пользователя |
| POST | `/photo/change_country_map` | Карта страны |
| POST | `/photo/change_region_map` | Карта региона |
| POST | `/photo/change_region_image` | Изображение региона |
| POST | `/photo/change_district_image` | Изображение района |
| POST | `/photo/change_location_image` | Изображение локации |
| POST | `/photo/change_skill_image` | Изображение навыка |
| POST | `/photo/change_skill_rank_image` | Изображение ранга навыка |
| POST | `/photo/change_item_image` | Изображение предмета |

## Обработка изображений

1. Приём файла (UploadFile)
2. Валидация: файл не пустой, max 15MB
3. Конвертация в **WebP** (quality=80, method=6, lossless=False)
4. Генерация уникального имени: `{prefix}_{entity_id}_{uuid.hex}.webp`
5. Загрузка в S3 с MD5 checksum
6. Обновление URL в MySQL
7. Возврат URL

## S3 Storage

- **Endpoint:** `https://s3.twcstorage.ru`
- **Region:** `ru-1`
- **ACL:** public-read
- **Cache-Control:** max-age=31536000 (1 год)
- **Подкаталоги:** `user_avatars/`, `character_avatars/`, `maps/`, `locations/`, `skills/`, `skill_ranks/`, `items/`, `character_preview/`, `user_preview/`

## Обновляемые таблицы (raw SQL)

| Таблица | Поле | Сущность |
|---------|------|----------|
| users | avatar | Аватар пользователя |
| users_avatar_preview | avatar | Превью аватара |
| characters | avatar | Аватар персонажа |
| users_avatar_character_preview | avatar | Превью персонажа |
| Countries | map_image_url | Карта страны |
| Regions | map_image_url, image_url | Карта/изображение региона |
| Districts | image_url | Изображение района |
| Locations | image_url | Изображение локации |
| skills | skill_image | Изображение навыка |
| skill_ranks | rank_image | Изображение ранга |
| items | image | Изображение предмета |

## Особенности

- **Использует raw SQL** через PyMySQL DictCursor (не SQLAlchemy ORM)
- **Нет аутентификации** - user_id передаётся как form parameter
- **env-файл** для S3-credentials
- **GCS credentials** в `/credentials/gcs-credentials.json` - не используются (legacy)

## Известные проблемы

1. **Нет аутентификации** - любой может загрузить аватар любого пользователя
2. **Bare except** clauses - ловит все исключения включая SystemExit
3. **Захардкоженный CORS origin** - `http://4452515-co41851.twc1.net`
4. **Нет валидации типа файла** - принимает любой файл (только PIL проверит при открытии)
5. **Fragile S3 URL parsing** - `"/".join(file_url.split("/")[3:])` предполагает конкретную структуру URL
6. **Комментарий-опечатка** - эндпоинт для items описан как "для ранга навыка"
