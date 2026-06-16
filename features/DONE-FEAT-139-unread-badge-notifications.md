# FEAT-139: Бейдж непрочитанных + desktop-уведомления (Батч 4)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (RU)

- **Бейдж непрочитанных в заголовке вкладки**: `(3) Chaldea`, обновляется в реальном времени.
- **Desktop-уведомления** о новом личном сообщении, когда вкладка свёрнута/не в фокусе
  (Notification API, запрос разрешения у залогиненного пользователя).

> Полноценный web-push (доставка при **закрытой** вкладке) требует service worker + VAPID-ключей
> (секрет в env) — вынесено отдельной задачей. Текущая версия покрывает «вкладка открыта, но в фоне».

---

## 2-5. Technical (frontend-only)

- `components/App/Layout/Layout.tsx` — для залогиненных: загрузка `fetchUnreadCount`, запрос
  `Notification.requestPermission()`; эффект, пишущий `(N) <title>` в `document.title` по
  `selectTotalUnread` (живо обновляется через `receivePrivateMessage`).
- `hooks/useWebSocket.ts` — на `private_message`, если `document.hidden` и разрешение выдано,
  показывает `new Notification(sender, { body })` (best-effort, в try/catch).

## Verification
- `npm run build` + `tsc` — OK. Без бэкенда и миграций.

## 7. Итог (RU)
Готов FEAT-139 (бейдж + уведомления в фоне). Полный web-push при закрытой вкладке — отдельная
задача (нужны VAPID-ключи). Дальше — FEAT-140 (виртуализация).
