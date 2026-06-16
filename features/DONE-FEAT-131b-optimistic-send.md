# FEAT-131b: Оптимистичная отправка сообщений лички

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

Отложенный пункт из FEAT-131. Своё сообщение появляется в чате **мгновенно** (со статусом
«отправка…», приглушённое), а не после round-trip к серверу. Когда приходит подтверждение
`messenger_send_ok`, временное сообщение заменяется реальным на том же месте; при ошибке
(`messenger_error`) или невозможности отправить — убирается, показывается тост.

---

## 2-5. Technical

**Backend** (`notification-service`):
- `messenger_ws_handler.py` — `handle_messenger_send` стал тонкой обёрткой над
  `_handle_messenger_send_impl`, которая эхо-ит клиентский `temp_id` в `data` любого результата
  (ok или error). Копирует dict, не мутируя payload, уже отданный в broadcast.

**Frontend**:
- `types/messenger.ts` — `PrivateMessage.status?: 'sending' | 'sent'`.
- `redux/slices/messengerSlice.ts` — счётчик `nextOptimisticId()` (уникальные отрицательные id),
  `addOptimisticMessage` / `removeOptimisticMessage` reducers, `sendMessage` thunk добавляет
  оптимистичное сообщение и шлёт `temp_id`; `receiveOwnSentMessage` сверяет по `temp_id`
  (replace-in-place / drop, без дублей).
- `hooks/useWebSocket.ts` — `messenger_error` с `temp_id` убирает оптимистичное сообщение.
- `MessageBubble.tsx` — статус «отправка…», приглушение, без действий у неподтверждённого.

**Tests** (`tests/test_messenger.py::TestOptimisticTempId`): temp_id эхо-ится в ошибке;
без temp_id ответ не меняется. 46 messenger-тестов зелёные.

## Verification
- `pytest tests/test_messenger.py` — 46 passed.
- `npm run build` — OK (tsc: только предсуществующая ошибка `params ?? {}`).

## 7. Итог (RU)
Готова оптимистичная отправка. Осталось: FEAT-135 (аватар группы — нужен photo-service upload),
Батч 4 (реакции, вложения, поиск/@упоминания, web-push, виртуализация).

> Замечено (не в этой правке): своё новое сообщение не синкается в *другие свои вкладки*
> (messenger_send_ok идёт только на сокет-отправитель, а private_message-broadcast исключает
> отправителя целиком). Кандидат на отдельную мелкую задачу.
