# FEAT-134: Список диалогов как в Telegram (всплытие + закрепление)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

Идея пользователя. Две вещи:

- **Живой порядок (как в ТГ).** Раньше диалог всплывал наверх только после перезагрузки.
  Теперь при новом сообщении (входящем или своём) диалог поднимается наверх своего блока
  на клиенте, без перезагрузки.
- **Закрепление диалогов.** Можно закрепить диалог — он держится над незакреплёнными.
  Закрепление персональное (на участнике), синхронизируется между вкладками по WS.

---

## 2-5. Technical

**Backend** (`notification-service`):
- `messenger_models.py` — `ConversationParticipant.pinned_at` (DateTime, nullable, per-user).
- Alembic `0007_add_participant_pinned_at.py` — add column. Проверена против MySQL 8.0
  (цепочка 0001→0007 применяется чисто, fail-fast при старте контейнера).
- `messenger_crud.py` — `set_conversation_pin()`; `list_conversations()` теперь джойнит
  participant текущего юзера и сортирует `pinned first` (ключ `pinned_at IS NOT NULL DESC`,
  одинаково на MySQL и SQLite) → `pinned_at DESC` → активность. Каждый item несёт `is_pinned`.
- `messenger_schemas.py` — `ConversationListItem.is_pinned`.
- `messenger_routes.py` — `PUT/DELETE /conversations/{id}/pin` (проверка участия), WS-событие
  `conversation_pin_changed` тому же юзеру для синка вкладок.

**Frontend**:
- `types/messenger.ts` — `is_pinned` в `ConversationListItem`, `WsConversationPinChangedData`.
- `api/messengerApi.ts` — `pinConversation` / `unpinConversation`.
- `redux/slices/messengerSlice.ts` — `bumpConversationToTop` (живой порядок в
  `receivePrivateMessage` / `receiveOwnSentMessage`), `applyPinState`, `pinConversation` thunk,
  `receiveConversationPinChanged` reducer.
- `hooks/useWebSocket.ts` — обработка `conversation_pin_changed`.
- `MessengerPage` / `ConversationList` / `ConversationItem` — проброс `onTogglePin`, индикатор
  закрепления (значок) и hover-кнопка pin/unpin.

**Tests** (`tests/test_messenger.py::TestPinning`): pin/unpin, попадание `is_pinned` в список,
сортировка pinned-first, 404 на несуществующий, 403 для не-участника. 40 messenger-тестов зелёные.

## Verification
- `pytest tests/test_messenger.py` — 40 passed.
- Alembic `upgrade head` против MySQL 8.0 — OK, колонка создана.
- `npm run build` — OK (единственная tsc-ошибка `params ?? {}` предсуществующая, не из этой правки).

## 7. Итог (RU)
Готов FEAT-134. Осталось по плану: FEAT-135 (аватар группы), FEAT-132 (presence + оптимистичная
отправка), затем реакции/вложения/поиск/web-push/виртуализация.
