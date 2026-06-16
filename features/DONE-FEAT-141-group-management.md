# FEAT-141: Управление групповой конфой

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

В групповом чате можно: посмотреть всех участников, **создателю** — добавлять и исключать
участников и менять аватар группы. Права привязаны к создателю (`created_by`), без отдельной
системы ролей (миграция не нужна).

> Делегирование прав (создатель назначает «админов») — отдельная задача (нужна колонка роли).

---

## 2-5. Technical

**notification-service** (без миграции):
- `messenger_schemas` — `GroupParticipant`, `GroupParticipantsResponse`.
- `messenger_routes`:
  - `GET /conversations/{id}/participants` — полный список с профилями и `is_creator` (участник).
  - `POST .../participants` (добавить) — **только создатель**; новым участникам шлётся
    `conversation_created` (группа появляется в их списке).
  - `DELETE .../participants/{user_id}` (исключить) — **только создатель**; нельзя исключить
    создателя; исключённому шлётся `conversation_removed`.

**photo-service**:
- mirror `Conversation.created_by`; `change_group_avatar` / `delete_group_avatar` — **только
  создатель**.

**Frontend**:
- `types`/`api` — `GroupParticipant(s)`, `getGroupParticipants`, `removeParticipant`,
  `WsConversationRemovedData`.
- `messengerSlice` — `removeConversation` reducer; `hooks/useWebSocket` — `conversation_removed`
  (дроп беседы + тост «Вас исключили»).
- `GroupParticipantsModal` (new) — список участников (бейдж «создатель»); для создателя: смена
  аватара, добавление (поиск пользователей), исключение.
- `MessageArea` — кнопка «участники» (иконка) в шапке группы + рендер модалки.

**Tests**: notification `tests/test_messenger.py::TestGroupManagement` — список, add создателем,
add не-создателем 403, kick создателем, нельзя исключить создателя, kick не-создателем 403
(61 messenger-тест зелёный). photo — 4 (аватар создателем / 403 не-создателю).

## Verification
- notification 61 passed; photo 4 passed; `npm run build` + `tsc` — OK. Без миграций.

## 7. Итог (RU)
Готов FEAT-141 (управление группой создателем). Делегирование ролей (админы) — кандидат на
отдельную задачу.
