# FEAT-136: Реакции на сообщения (Батч 4)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

Эмодзи-реакции на сообщения лички (👍 ❤️ 😂 😮 😢 🔥). Тапаешь по сообщению → быстрый набор
реакций; под сообщением — чипы с эмодзи и счётчиком, своя реакция подсвечена. Реал-тайм по WS.

---

## 2-5. Technical

**notification-service**:
- `messenger_models.py` — `MessageReaction` (message_id FK CASCADE, user_id, emoji, unique
  (message,user,emoji)). Alembic `0009_add_message_reactions.py` (проверена против MySQL 8.0).
- `messenger_crud.py` — `toggle_reaction` (add/remove), `get_reactions_summary` (батч по странице).
- `messenger_schemas.py` — `ReactionSummary`, `PrivateMessageResponse.reactions`.
- `messenger_routes.py` — реакции прикладываются к сообщениям в `get_messages` (батч-запрос).
- `messenger_ws_handler.py` — `handle_messenger_react`: проверка участия, toggle, broadcast
  события `message_reaction` всем участникам (включая автора). `main.py` — экшн `messenger_react`.

**Frontend**:
- `types/messenger.ts` — `ReactionSummary`, `PrivateMessage.reactions`, `WsMessageReactionData`.
- `redux/slices/messengerSlice.ts` — `sendReaction` thunk, `receiveReaction` reducer
  (инкремент/декремент по emoji, `reacted_by_me` через is_self).
- `hooks/useWebSocket.ts` — обработка `message_reaction` (is_self = user_id === currentUserId via ref).
- `MessengerPage`/`MessageArea` — проброс `onReact`.
- `MessageBubble` — чипы реакций (подсветка своей) + быстрый набор в экшн-баре.

**Tests** (`tests/test_messenger.py::TestReactions`): toggle add/remove + summary, broadcast всем
участникам, не-участник без эффекта. 49 messenger-тестов зелёные.

## Verification
- `pytest tests/test_messenger.py` — 49 passed; migration 0009 vs MySQL 8.0 — OK.
- `npm run build` + `tsc` — OK.

## 7. Итог (RU)
Готов FEAT-136. Дальше Батч 4: FEAT-137 (вложения-картинки), FEAT-138 (поиск/@упоминания),
FEAT-139 (web-push + бейдж), FEAT-140 (виртуализация).
