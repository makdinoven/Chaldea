# FEAT-131: Полиш UX мессенджера (пилюля новых, разделители, overscroll)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-06-16 |
| **Author** | Engineer (direct) |
| **Priority** | MEDIUM |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`

---

## 1. Feature Brief (RU)

### Описание
Фронтовый полиш личных сообщений (Батч 1 из плана по улучшению чата). Без бэкенда и миграций.

- **Пилюля «↓ N новых сообщений»** — когда читаешь историю и приходит новое сообщение, тебя больше не кидает вниз (по фиксу скролла из FEAT после WS-миграции), а внизу появляется кнопка-пилюля со счётчиком; клик — прыжок к последним.
- **Разделители по датам** — «Сегодня» / «Вчера» / «15 июня» между сообщениями разных дней.
- **Линия «непрочитанные сообщения»** — при открытии диалога показывает, откуда начинаются новые (снимок unread_count на момент открытия, до того как mark-read обнулит счётчик).
- **`overscroll-contain`** — упор скролла чата в крайнее сообщение больше не прокручивает всю страницу (scroll chaining). Тот же фикс применён к общему чат-виджету слева.

---

## 2-5. Technical

**Frontend only.** Files:
- `components/Messenger/MessageArea.tsx` — pill state (`newCount`), unread snapshot (`unreadSnapshot`),
  render list with date/unread separators (`renderItems` memo), `overscroll-contain` on the scroll
  container, relative wrapper anchoring the pill. Own outgoing messages always follow to the bottom;
  others' messages only follow when already near the bottom, otherwise they bump the pill counter.
- `components/Chat/ChatMessages.tsx` — `overscroll-contain` on the global chat scroll container.

No new dependencies. `ArrowDown` icon reused from `react-feather`.

## Verification
- `npm run build` (vite) — OK.
- `tsc --noEmit` — no errors in changed files.
- Deployed to prod via push to main (CI/CD).

## 7. Итог (RU)
Сделан Батч 1. Дальше по плану: Батч 2 — presence («печатает…», онлайн в шапке) + оптимистичная
отправка (нужен echo temp_id с бэка); Батч 3 — надёжность (мульти-таб в ws_manager, индикатор связи,
кулдаун rate-limit); Батч 4+ — реакции, вложения-картинки, поиск/@упоминания, web-push, виртуализация.
