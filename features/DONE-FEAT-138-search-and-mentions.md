# FEAT-138: Поиск по сообщениям + @упоминания (Батч 4)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

- **Поиск по сообщениям** в открытом диалоге: иконка-лупа в шапке → строка поиска → выпадающий
  список совпадений (автор, сниппет, дата). Бэкенд-поиск (LIKE), без перехода к сообщению (v1).
- **@упоминания**: `@username` подсвечивается в сообщениях; упомянутый участник получает
  уведомление (тост + запись в колокольчик).

---

## 2-5. Technical

**notification-service** (без миграции):
- `messenger_crud.search_messages` (LIKE по content, не удалённые, newest-first).
- `messenger_routes` — `GET /conversations/{id}/search?q=` (проверка участия, enrich автора).
- `messenger_ws_handler` — на отправке парсит `@username` (regex), и для упомянутых участников
  (по их username из профиля) шлёт WS-событие `messenger_mention`.

**Frontend**:
- `api/messengerApi.ts` — `searchMessages`.
- `MessageArea` — тоггл поиска в шапке, дебаунс-запрос (350мс), выпадающая панель результатов.
- `MessageBubble` — рендер `@username` с подсветкой (`renderContent`).
- `hooks/useWebSocket.ts` — `messenger_mention` → тост «X упомянул вас» + уведомление.

**Tests** (`tests/test_messenger.py`): поиск находит совпадение + 403 не-участнику; упоминание
шлёт событие нужному участнику, без @ — не шлёт. 55 messenger-тестов зелёные.

## Verification
- `pytest tests/test_messenger.py` — 55 passed; `npm run build` + `tsc` — OK.

## 7. Итог (RU)
Готов FEAT-138. Поиск без jump-to-message (кандидат на доработку). Дальше Батч 4: FEAT-139
(web-push + бейдж), FEAT-140 (виртуализация).
