# FEAT-132: Presence — «печатает…» и онлайн-статус

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

Presence для лички. Без БД и миграций (чистый WS/REST).

- **«Печатает…»** — пока собеседник набирает текст, под полем ввода видно «X печатает…».
  Сигнал эфемерный (ничего не пишется в БД), троттлится на клиенте (раз в 3с), на сервере
  релеится остальным участникам, авто-истечение на клиенте через 6с.
- **Онлайн-статус** — в шапке личного диалога видно «в сети / не в сети» собеседника
  (по наличию активного WS-соединения), опрос раз в 30с.

> Оптимистичная отправка (task FEAT-131 #7) — следующим шагом (нужен echo temp_id).

---

## 2-5. Technical

**Backend** (`notification-service`):
- `ws_manager.py` — `is_online(user_id)` по `active_connections`.
- `messenger_ws_handler.py` — `handle_messenger_typing()`: проверка участия, релей события
  `messenger_typing` остальным участникам, без записи в БД и без эха отправителю.
- `main.py` — ветка WS `messenger_typing` (to_thread, без ответа).
- `messenger_routes.py` — `GET /messenger/presence/{user_id}` → `{user_id, online}`.

**Frontend**:
- `types/messenger.ts` — `WsTypingData`, `PresenceResponse`.
- `api/messengerApi.ts` — `getPresence()`.
- `redux/slices/messengerSlice.ts` — `typingByConversation` state, `receiveTyping` / `pruneTyping`
  reducers, `sendTypingSignal` thunk, `selectTypingUsernames` selector (TTL 6с).
- `hooks/useWebSocket.ts` — обработка `messenger_typing`.
- `MessengerPage` — троттл-сигнал печати, интервал прунинга, проброс typing/onTyping.
- `MessageArea` — индикатор «печатает…», онлайн-статус в шапке (polling 30с).
- `MessageInput` — троттл `onTyping` (раз в 3с) на ввод.

**Tests** (`tests/test_messenger.py::TestTypingAndPresence`): релей только другим участникам,
не-участник без релея, presence online/offline. 44 messenger-теста зелёные.

## Verification
- `pytest tests/test_messenger.py` — 44 passed.
- `npm run build` — OK (tsc: только предсуществующая ошибка `params ?? {}`, не из этой правки).

## 7. Итог (RU)
Готов FEAT-132 (typing + online). Осталось: оптимистичная отправка, FEAT-135 (аватар группы —
нужен photo-service upload), Батч 4 (реакции, вложения, поиск/@упоминания, web-push, виртуализация).
