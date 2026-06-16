# FEAT-135: Аватар группового чата

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

Идея пользователя. При создании группового чата можно **выбрать аватар** (загрузка файла через
photo-service → S3). Аватар показывается в панели диалогов (и далее в списке у всех участников
при загрузке списка). Загрузка — стандартным паттерном photo-service (Form + UploadFile → webp → S3).

---

## 2-5. Technical

**notification-service**:
- `messenger_models.py` — `Conversation.avatar` (String(500), nullable).
- Alembic `0008_add_conversation_avatar.py` — проверена против MySQL 8.0 (цепочка 0001→0008).
- `messenger_schemas.py` — `avatar` в `ConversationResponse` и `ConversationListItem`.
- `messenger_crud.py` — `avatar` в элементах `list_conversations`.
- `messenger_routes.py` — `avatar` в ответах create и в WS-событии `conversation_created`.

**photo-service**:
- `models.py` — mirror-модели `Conversation`, `ConversationParticipant`.
- `crud.py` — `is_conversation_participant`, `get_conversation_type`,
  `update_conversation_avatar`, `get_conversation_avatar`.
- `main.py` — `POST /photo/change_group_avatar` (участник + только group → webp → S3 →
  запись avatar) и `DELETE /photo/delete_group_avatar`.
- `tests/test_group_avatar_upload.py` — 200/403/400/401 (4 теста).

**Frontend**:
- `types/messenger.ts` — `avatar` в `Conversation`, `ConversationListItem`, `WsConversationCreatedData`.
- `api/messengerApi.ts` — `uploadGroupAvatar(conversationId, file)`.
- `redux/slices/messengerSlice.ts` — `setConversationAvatar` reducer, `avatar` в создаваемых элементах.
- `NewConversationModal` — пикер аватара (превью) для группы; `onCreate` отдаёт файл.
- `MessengerPage` — после создания группы грузит аватар и проставляет URL.
- `ConversationItem` — для группы показывает `conversation.avatar`.

## Verification
- notification: `pytest tests/test_messenger.py` — 46 passed; migration 0008 vs MySQL 8.0 — OK.
- photo: `pytest tests/test_group_avatar_upload.py` — 4 passed.
- `npm run build` + `tsc` — OK (только предсуществующая ошибка `params ?? {}`).

## 7. Итог (RU)
Готов FEAT-135. Аватар задаётся при создании группы, виден в списке диалогов. Реал-тайм
рассылки смены аватара остальным участникам нет (видят при загрузке списка) — кандидат на
доработку. Дальше — Батч 4: реакции, вложения-картинки в сообщения, поиск/@упоминания,
web-push, виртуализация.
