# FEAT-137: Вложения-картинки в сообщения (Батч 4)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

Отправка изображений в личке. В поле ввода — кнопка скрепки/картинки: выбираешь файл, он
грузится в S3 (photo-service), показывается превью, отправляешь с подписью или без. В сообщении
картинка кликабельна (открывается в новой вкладке). В списке диалогов сообщение-картинка
показывается как «📷 Изображение».

---

## 2-5. Technical

**photo-service**:
- `main.py` — `POST /photo/upload_chat_image` (валидация MIME → webp → S3, возвращает `image_url`,
  без записи в БД). `tests/test_chat_image_upload.py` (200 + 401).

**notification-service**:
- `messenger_models.py` — `PrivateMessage.image_url` (String(500), nullable). Alembic `0010`
  (проверена против MySQL 8.0).
- `messenger_crud.create_message` — параметр `image_url`.
- `messenger_ws_handler.handle_messenger_send` — приём `image_url`, разрешён пустой текст при
  наличии картинки, `image_url` в `msg_data` (ответ + broadcast).
- `messenger_schemas.PrivateMessageResponse.image_url`; `get_messages` отдаёт `image_url`
  (скрыт у удалённых).

**Frontend**:
- `types/messenger.ts` — `image_url` в `PrivateMessage` и `WsPrivateMessageData`.
- `api/messengerApi.ts` — `uploadChatImage(file)`.
- `redux/slices/messengerSlice.ts` — `sendMessage` принимает `image_url` (оптимистично + в WS).
- `MessageInput` — кнопка вложения, загрузка с превью и спиннером, отправка картинки (с текстом
  или без).
- `MessengerPage`/`MessageArea` — проброс `imageUrl` в отправку.
- `MessageBubble` — рендер картинки (кликабельная), `ConversationItem` — «📷 Изображение» в превью.

**Tests**: notification `pytest tests/test_messenger.py` — 51 passed; photo — 6 passed
(chat image + group avatar); migration 0010 vs MySQL — OK; `npm run build` + `tsc` — OK.

## 7. Итог (RU)
Готов FEAT-137. Дальше Батч 4: FEAT-138 (поиск/@упоминания), FEAT-139 (web-push + бейдж),
FEAT-140 (виртуализация).
