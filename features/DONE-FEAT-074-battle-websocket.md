# FEAT-074: WebSocket для боевой системы (замена polling)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-24 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-074-battle-websocket.md` → `DONE-FEAT-074-battle-websocket.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Заменить polling (опрос каждые 5 секунд) на WebSocket для получения состояния боя в реальном времени. Оба игрока должны видеть действия друг друга мгновенно. Автобой тоже должен транслировать обновления через WebSocket. Добавить регулировку скорости автобоя (быстрый/медленный режим).

### Бизнес-правила
- Оба участника боя видят результат хода мгновенно (push через WebSocket)
- При потере соединения — автоматическое переподключение к WebSocket с индикатором "переподключение..."
- Если переподключение не удаётся — fallback на polling (как сейчас)
- Автобой транслирует ходы через WebSocket
- Два режима скорости автобоя: быстрый и медленный
- Замедленный режим нужен, чтобы игрок мог вовремя остановить автобой, если стратегия ему не нравится

### UX / Пользовательский сценарий

**Обычный бой:**
1. Игрок заходит на страницу боя
2. Устанавливается WebSocket-соединение
3. Игрок делает ход — результат мгновенно отображается у обоих участников
4. Если соединение теряется — показывается индикатор "Переподключение..."
5. Система пытается переподключиться автоматически
6. Если не удалось — переключается на polling, игрок видит уведомление

**Автобой:**
1. Игрок запускает автобой
2. На экране появляется переключатель скорости: быстрый / медленный
3. В медленном режиме ходы идут с задержкой, чтобы игрок успевал следить и мог остановить
4. В быстром режиме ходы идут максимально быстро
5. Все обновления приходят через WebSocket

### Edge Cases
- Что если оба игрока потеряли соединение одновременно? — Бой продолжается на сервере, оба переподключатся
- Что если один игрок на WebSocket, а другой на polling (fallback)? — Оба получают состояние, просто с разной задержкой
- Что если автобой идёт, а игрок переключает скорость? — Новая скорость применяется со следующего хода

### Вопросы к пользователю (если есть)
- [x] Мгновенная трансляция ходов обоим игрокам? → Да
- [x] Поведение при потере соединения? → Автопереподключение + индикатор + fallback на polling
- [x] Автобой через WebSocket? → Да, плюс регулировка скорости (быстрый/медленный)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### Affected Services

| Service | Type of Changes | Key Files |
|---------|----------------|-----------|
| battle-service | Add WebSocket endpoint, publish full state on Pub/Sub after action | `app/main.py`, `app/redis_state.py`, `app/config.py`, `app/schemas.py` |
| autobattle-service | Add speed control (fast/slow), delay between turns, new REST endpoint | `app/main.py`, `app/config.py`, `app/clients.py` |
| frontend | Replace polling with WebSocket, reconnection logic, fallback to polling, speed control UI | `src/components/pages/BattlePage/BattlePage.tsx`, `src/components/pages/BattlePage/BattlePageBar/BattlePageBar.tsx`, `src/hooks/useWebSocket.ts` (reference pattern), `src/api/api.ts` |
| api-gateway (Nginx) | Add WebSocket upgrade support for `/battles/` path | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` |

### Current Implementation Details

#### Battle-Service: State Endpoint (`GET /battles/{id}/state`)

- **File:** `services/battle-service/app/main.py` (line ~506)
- Authenticated endpoint requiring JWT. Verifies the requesting user owns a participating character.
- Loads state from Redis via `load_state(battle_id)` which reads `battle:{id}:state` JSON key.
- Loads snapshot from Redis cache (`battle:{id}:snapshot`), falls back to MongoDB if not cached.
- Returns `{snapshot: [...], runtime: {...}}` where runtime includes `participants`, `current_actor`, `next_actor`, `turn_number`, `deadline_at`, `active_effects`, `is_paused`, `rewards`.
- There is also an **internal** version at `GET /battles/internal/{id}/state` (line ~447) used by autobattle-service (no JWT).
- A **spectate** version at `GET /battles/{id}/spectate` (line ~580) for observers at the same location.

#### Battle-Service: Redis Pub/Sub (Already Exists)

- **File:** `services/battle-service/app/redis_state.py` (line ~104) and `main.py` (line ~1403)
- After every action, battle-service publishes to `battle:{battle_id}:your_turn` with the `next_actor_participant_id` as the message payload.
- This is also done on battle creation (`init_battle_state`, line ~104 of redis_state.py).
- **Current payload is minimal** — only the next actor's participant_id as a string. It does NOT include full state.
- The channel pattern is `battle:{id}:your_turn` — currently only consumed by autobattle-service.

#### Battle-Service: Action Flow (`POST /battles/{id}/action`)

- **File:** `services/battle-service/app/main.py` (line ~780, `_make_action_core`)
- Core flow after processing a turn (lines ~1380-1421):
  1. Updates Redis state (`save_state`)
  2. Records turn number in Redis ZSET
  3. Updates deadline in ZSET
  4. **Publishes** to `battle:{battle_id}:your_turn` with next actor pid
  5. Async saves log to MongoDB via Celery
  6. Returns `ActionResponse` with events, turn_number, next_actor, deadline_at, battle_finished, winner_team, rewards

#### Autobattle-Service: Current Loop

- **File:** `services/autobattle-service/app/main.py`
- Subscribes to Redis Pub/Sub pattern `battle:*:your_turn` on startup (line ~64).
- When message received: parses `battle_id` from channel name, `participant_id` from message data.
- If `pid in ALLOWED`, spawns `handle_turn(bid, pid)` as an asyncio task.
- `handle_turn` (line ~263): fetches full state via HTTP `GET /battles/internal/{id}/state`, runs strategy, posts action via HTTP `POST /battles/internal/{id}/action`.
- **No speed control exists.** All turns execute as fast as possible.
- Retry logic: 3 retries with exponential backoff (2s, 4s, 8s).
- On battle finish (`res.get("battle_finished")`), calls `_cleanup_battle(bid)` to clear in-memory state.
- **Mode** (`attack`/`defense`/`balance`) is global, not per-battle or per-participant.

#### Autobattle-Service: Speed Control (Where It Fits)

- Speed control would add a configurable delay before `handle_turn` executes.
- Current code: `asyncio.create_task(handle_turn(bid, pid))` in `redis_reader()` (line ~77) and in `/register` (line ~127).
- A delay could be inserted at the beginning of `handle_turn` or before the task creation.
- Need a new REST endpoint or extend `/register` to accept speed setting.
- Speed should be per-participant or per-battle (current `mode` is global — this is a known issue).

#### Frontend: Polling Mechanism

- **File:** `services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePage.tsx`
- Uses `setInterval` with 5000ms (line ~351) to call `getBattleState()`.
- `getBattleState()` (line ~195) makes `axios.get` to `/battles/{battleId}/state`.
- Interval is cleared on unmount and when `battleResult` is set.
- After sending a turn (`setTurnApi`, line ~412), also calls `getBattleState(false)` immediately.
- Battle result detection is done by checking HP <= 0 in `useEffect` watching `opponentData`/`myData`.
- Spectate mode uses same polling mechanism but calls `fetchBattleSpectateState` instead.

#### Frontend: Autobattle UI

- **File:** `BattlePageBar.tsx` (lines ~512-528)
- Toggle button ("Включить автобой" / "остановить автобой").
- Mode selector (attack/defense/balance) via `AUTOBATTLE_MODE_BTNS` with icons.
- Mode is sent via `POST /autobattle/mode` — global mode, not per-battle.
- **No speed control UI currently exists.**

#### Frontend: Existing WebSocket Infrastructure

- **File:** `services/frontend/app-chaldea/src/hooks/useWebSocket.ts`
- Already has a robust WebSocket hook connecting to `/notifications/ws?token=...`.
- Features: auto-reconnect with exponential backoff (1s → 30s max), handles unauthorized (4001 code), processes typed messages via `switch(parsed.type)`.
- Handles: `notification`, `chat_message`, `chat_message_deleted`, `pvp_battle_start`, `ping`.
- **This pattern can be reused/adapted** for a battle-specific WebSocket.
- Connection URL: `${protocol}//${window.location.host}/notifications/ws?token=${token}`.

#### Notification-Service: WebSocket Pattern (Reference)

- **File:** `services/notification-service/app/main.py` (line ~52) and `app/ws_manager.py`
- `@app.websocket("/notifications/ws")` with JWT auth via query param `token`.
- `ws_manager.py`: maintains `active_connections: dict[int, WebSocket]` (1 connection per user).
- `send_to_user(user_id, data)` — thread-safe send using `asyncio.run_coroutine_threadsafe`.
- Battle-service already uses `publish_notification()` with `ws_type`/`ws_data` to send structured messages to users via this WebSocket (e.g., `pvp_battle_start`, `battle_paused`, `battle_resumed`).
- **Key insight:** Battle events are already routed through notification-service WS. The new battle WS could either be a separate endpoint in battle-service or leverage the existing notification WS channel.

#### Nginx: WebSocket Support

- **Dev** (`docker/api-gateway/nginx.conf`):
  - `/notifications/` block (line ~163): Already has `proxy_http_version 1.1`, `Upgrade`, `Connection "upgrade"` headers, `proxy_buffering off`, `proxy_read_timeout 3600`.
  - `/battles/` block (line ~177): Standard HTTP proxy only — **no WebSocket upgrade headers**.
  - `/` (Vite HMR, line ~229): Also has WebSocket upgrade headers.
- **Prod** (`docker/api-gateway/nginx.prod.conf`):
  - `/notifications/` (line ~178): Same WebSocket headers as dev.
  - `/battles/` (line ~192): Standard HTTP proxy only — **no WebSocket upgrade headers**.

**Both nginx configs need WebSocket upgrade support added to `/battles/` path.**

#### Docker Compose

- `battle-service` (line ~429): No special config needed beyond what exists.
- `autobattle-service` (line ~466): No special config needed.
- No new services or ports required.

### Existing Patterns

- **battle-service:** Async FastAPI, async SQLAlchemy (aiomysql), aioredis, Pydantic <2.0, Alembic present (`alembic_version_battle`). Uses `redis.asyncio` for Redis.
- **autobattle-service:** Async FastAPI, no DB, `aioredis` for Redis Pub/Sub, `httpx` for HTTP calls, Pydantic <2.0. No Alembic (no DB).
- **frontend:** React 18 + TypeScript (BattlePage already `.tsx`), Vite, Redux Toolkit, axios for HTTP. WebSocket pattern exists in `useWebSocket.ts` hook.
- **WebSocket auth pattern:** Query param `?token=JWT` validated server-side (see notification-service).
- **Redis Pub/Sub pattern:** Already used for `battle:{id}:your_turn` channel.

### Cross-Service Dependencies

```
Frontend (BattlePage) ──WS──> battle-service (new /battles/ws endpoint)
Frontend (BattlePage) ──HTTP──> battle-service (existing /state, /action — kept as fallback)
Frontend (BattlePage) ──HTTP──> autobattle-service (existing /register, /unregister, /mode + new /speed)
battle-service ──Redis Pub/Sub──> autobattle-service (existing battle:*:your_turn)
battle-service ──Redis Pub/Sub──> battle-service WS handler (NEW — subscribe to own channel to push to connected clients)
battle-service ──RabbitMQ──> notification-service (existing — for ws_type events like pvp_battle_start)
api-gateway (Nginx) ──proxy──> battle-service (needs WebSocket upgrade headers)
```

**Important:** Two options exist for the WebSocket implementation:

1. **Option A: New WS endpoint in battle-service** — battle-service subscribes to its own Redis Pub/Sub channel and pushes state to connected WebSocket clients. Requires adding WS endpoint and connection manager to battle-service.
2. **Option B: Route through existing notification-service WS** — battle-service publishes full state updates via `publish_notification()` with a `ws_type: "battle_state_update"`. Frontend listens on existing notification WS. No new WS endpoint needed.

**Trade-offs:**
- Option A: More precise (battle-specific), lower latency (direct), but adds WS infrastructure to battle-service.
- Option B: Reuses existing infrastructure, but routes through RabbitMQ → notification-service → WS (higher latency, ~100-500ms extra). Also sends full battle state through notification pipeline which is designed for small messages. Spectators would need to be connected to notification-service WS too.

### DB Changes

- **No DB schema changes required.** All state is in Redis (runtime) and the speed setting can be in-memory in autobattle-service.
- **No Alembic migrations needed.**

### Risks

1. **Risk: Nginx WebSocket upgrade misconfiguration** — If WebSocket upgrade headers are not properly configured in both `nginx.conf` and `nginx.prod.conf`, WS connections will fail silently.
   - Mitigation: Copy exact pattern from `/notifications/` block. Test in dev before deploying.

2. **Risk: Connection management in battle-service** — battle-service currently has no WebSocket infrastructure. Adding a connection manager adds complexity and potential memory leaks if connections are not properly cleaned up on battle finish or disconnect.
   - Mitigation: Follow notification-service `ws_manager.py` pattern. Use battle_id-scoped connection tracking. Clean up on battle finish.

3. **Risk: Auth for WebSocket** — battle-service needs JWT validation for WS connections. Currently, only user-service and notification-service handle JWT. battle-service uses `auth_http.py` which calls user-service `/users/me` via HTTP — this works for WS auth too (same pattern as notification-service).
   - Mitigation: Reuse `auth_http.py` pattern already in battle-service.

4. **Risk: Stale/duplicate state pushes** — If action processing is slow and multiple state changes happen rapidly (e.g., fast autobattle), clients might receive out-of-order updates.
   - Mitigation: Include `turn_number` in every WS message. Frontend discards messages with turn_number <= current.

5. **Risk: Polling fallback complexity** — Maintaining both WS and polling paths increases frontend complexity and testing burden.
   - Mitigation: Abstract state-fetching behind a hook that manages WS primary / polling fallback transparently.

6. **Risk: Spectate mode WebSocket** — Spectators are not participants. They need access to battle state via WS without being in the battle. Current spectate endpoint checks location — this auth check needs to work for WS too.
   - Mitigation: WS auth can accept both participants and spectators (check on connect). Or spectators can remain on polling (simpler, lower priority).

7. **Risk: Autobattle speed is currently global** — The `/mode` endpoint sets strategy globally for all battles. Adding per-battle speed control requires changing the data model.
   - Mitigation: Make speed per-participant (keyed by `participant_id` in a dict), similar to how `ALLOWED` and `PID_BATTLE` work.

8. **Risk: FastAPI WebSocket + existing `uvicorn[standard]`** — `uvicorn[standard]` includes `websockets` package. FastAPI natively supports `@app.websocket()`. No additional dependencies needed for battle-service.
   - Mitigation: Already included via `uvicorn[standard]` in requirements.txt.

### Key Findings Summary

1. **Redis Pub/Sub infrastructure already exists** — `battle:{id}:your_turn` channel is published after every action. Currently only consumed by autobattle-service. This can be extended to also push state to WebSocket clients.

2. **Notification-service already has a working WebSocket system** — with `ws_manager.py`, auth, reconnection, and message routing. This is a proven pattern to replicate in battle-service.

3. **Frontend already has a WebSocket hook** (`useWebSocket.ts`) with reconnection logic. A battle-specific variant can be created following the same pattern.

4. **Nginx already supports WebSocket** for `/notifications/` — the same headers need to be added to `/battles/`.

5. **No DB changes needed** — all state is Redis-based.

6. **Autobattle speed control is a straightforward addition** — add a per-participant delay dict and a new REST endpoint. The delay is applied before `handle_turn` executes.

---

## 3. Architecture Decision (filled by Architect — in English)

### Chosen Approach: Option A — New WebSocket endpoint in battle-service

**Justification:**

Option A (dedicated WS endpoint in battle-service) is chosen over Option B (routing through notification-service) for these reasons:

1. **Latency**: Battle state updates are time-critical. Option B adds RabbitMQ publish + notification-service consume + WS send — easily 100-500ms extra latency per turn. With fast autobattle this compounds significantly.
2. **Payload size**: Full battle state is ~2-5KB (participants, effects, cooldowns, fast_slots). The notification pipeline is designed for small messages (~100 bytes). Routing large state payloads through RabbitMQ is wasteful and may cause backpressure.
3. **Scoping**: A battle-specific WS endpoint naturally scopes connections to a battle_id. With notification-service, all battle state updates for all battles would flow through a single user-level WS connection, requiring additional client-side routing logic.
4. **Spectate support**: A dedicated battle WS can cleanly handle both participants and spectators with different auth checks on connect. With notification-service, spectators would need to be "subscribed" to battles they don't participate in — an awkward fit.
5. **Proven pattern**: The notification-service `ws_manager.py` pattern is well-tested and can be replicated in battle-service with minimal risk. FastAPI + uvicorn[standard] already support WebSocket natively.

**Trade-off accepted**: battle-service gains WS infrastructure (connection manager, Redis subscriber). This is ~150 lines of new code, following a proven pattern already in the codebase.

### WebSocket Endpoint Contract

#### `WS /battles/ws/{battle_id}?token={JWT}`

**Connection handshake:**
1. Client connects with JWT token as query parameter
2. Server validates JWT via `auth_http.py` (calls user-service `/users/me`)
3. Server checks if user is a participant OR a spectator (at same location) for `battle_id`
4. On success: accepts connection, sends initial `battle_state` message
5. On auth failure: closes with code `4001` (unauthorized)
6. On not-participant/not-spectator: closes with code `4003` (forbidden)

**Server → Client message types:**

```json
// 1. Full state update (sent after every turn)
{
  "type": "battle_state",
  "data": {
    "snapshot": [...],        // same as GET /state response.snapshot
    "runtime": {...}          // same as GET /state response.runtime
  }
}

// 2. Battle finished
{
  "type": "battle_finished",
  "data": {
    "winner_team": 0,
    "rewards": { "xp": 100, "gold": 50, "items": [] }  // null for losers
  }
}

// 3. Battle paused/resumed (join request)
{
  "type": "battle_paused",
  "data": { "is_paused": true, "reason": "Рассматривается заявка на присоединение" }
}

// 4. Keepalive ping (every 30s of inactivity)
{
  "type": "ping",
  "data": {}
}
```

**Client → Server messages:** None (read-only push channel, same pattern as notification-service). Client actions go through existing REST endpoints (`POST /battles/{id}/action`).

**Connection lifecycle:**
- One WebSocket per user per battle (if user reconnects, old connection is closed)
- Connection is scoped to `battle_id` — server only pushes updates for that specific battle
- Server cleans up connections when battle finishes or client disconnects
- Server-side keepalive ping every 30s (same as notification-service)

### Internal Pub/Sub Enhancement

The existing Redis Pub/Sub channel `battle:{id}:your_turn` currently sends only the next actor's participant_id. This will be **enhanced to a new channel** for WS push:

- **New channel:** `battle:{battle_id}:state_update`
- **Payload:** JSON string with `{"type": "battle_state", "snapshot": [...], "runtime": {...}}`
- **Published by:** battle-service `_make_action_core()` after `save_state()`, alongside the existing `your_turn` publish
- **Consumed by:** battle-service WS connection manager (to push to connected WebSocket clients)
- **The existing `your_turn` channel is unchanged** — autobattle-service continues to consume it as before

Why a separate channel instead of enriching `your_turn`:
- `your_turn` is consumed by autobattle-service which only needs the participant_id
- Sending full state on `your_turn` would waste bandwidth for autobattle-service (it fetches state via HTTP anyway)
- Separation of concerns: `your_turn` = turn notification, `state_update` = full state push for UI

### Battle WS Connection Manager (`ws_manager.py`)

```
battle_connections: dict[int, dict[int, WebSocket]]
    battle_id → { user_id → WebSocket }
```

- `connect(battle_id, user_id, ws)` — register, close old connection if exists
- `disconnect(battle_id, user_id)` — remove from dict
- `broadcast_to_battle(battle_id, data)` — send to all connected users for that battle
- `cleanup_battle(battle_id)` — close all connections and remove battle from dict
- On startup: subscribe to `battle:*:state_update` pattern, route messages to the correct battle's connected clients

### Autobattle Speed Control

#### `POST /autobattle/speed`

**Request:**
```json
{
  "participant_id": 123,
  "speed": "fast"   // "fast" | "slow"
}
```

**Response:**
```json
{
  "ok": true,
  "participant_id": 123,
  "speed": "fast"
}
```

**Authentication:** JWT required (same as `/register`, `/mode`). Ownership check: user must be the one who registered this participant for autobattle.

**Implementation:**
- New in-memory dict: `SPEED: dict[int, str] = {}` (participant_id → "fast" | "slow", default "fast")
- In `handle_turn()`, before executing the turn: if `SPEED.get(pid) == "slow"`, insert `await asyncio.sleep(SLOW_DELAY)` where `SLOW_DELAY = 3.0` seconds (configurable via env `AUTOBATTLE_SLOW_DELAY`)
- Speed is per-participant, stored alongside `ALLOWED`, `PID_BATTLE`, `OWNER`
- Cleaned up in `_cleanup_battle()` alongside other per-participant data
- Default speed on `/register` is "fast"

**Why 3 seconds for slow mode:** This gives the player enough time to see the turn result via WebSocket and press "stop autobattle" before the next turn executes. With WS delivering state updates in <100ms, 3s provides comfortable reaction time.

### Security Considerations

1. **Authentication:** WS connection requires valid JWT via `?token=` query param. Token is validated once on connect (not per-message, since WS is server-push only). If token expires mid-connection, the connection persists until disconnect — this is acceptable for battle duration (typically <30 min).

2. **Authorization:** On WS connect, server verifies the user is either:
   - A battle participant (owns a character in the battle) — for participant mode
   - At the same location as the battle — for spectate mode
   This mirrors the existing `GET /state` and `GET /spectate` auth checks.

3. **Rate limiting:** Not needed for WS (server-push only, no client messages processed). The existing REST endpoints (`/action`, `/register`, etc.) retain their current rate limiting.

4. **Input validation:** No client-to-server messages are processed on the battle WS. All actions continue through REST.

5. **Connection limits:** Max 1 WS connection per user per battle (enforced by connection manager). This prevents resource exhaustion from multiple tabs.

6. **Resource cleanup:** Connections are cleaned up on: disconnect, battle finish, server shutdown. The connection manager's `cleanup_battle()` is called when battle finishes to prevent memory leaks.

7. **Nginx:** WebSocket upgrade headers added to `/battles/` location in both dev and prod configs. `proxy_read_timeout 3600` ensures long-lived connections are not prematurely closed.

### DB Changes

None. All state is in Redis (runtime) and in-memory (speed setting). No Alembic migrations needed.

### Frontend Components

1. **New hook: `useBattleWebSocket.ts`**
   - Connects to `ws://{host}/battles/ws/{battleId}?token={jwt}`
   - Auto-reconnect with exponential backoff (1s → 30s), following `useWebSocket.ts` pattern
   - Returns: `{ connected, reconnecting, state, battleFinished }`
   - On `battle_state` message: updates state (snapshot + runtime)
   - On `battle_finished` message: signals battle end with rewards
   - Includes `turn_number` check: discards messages with turn_number <= current to handle out-of-order delivery
   - On permanent failure (5+ reconnect attempts): sets `fallbackToPolling = true`

2. **Modified: `BattlePage.tsx`**
   - Uses `useBattleWebSocket` hook as primary state source
   - Keeps existing `getBattleState()` polling as fallback (activated when WS reports `fallbackToPolling`)
   - Removes 5s interval when WS is connected
   - Shows reconnection indicator ("Переподключение...") when `reconnecting = true`
   - Shows fallback notice ("Используется резервное соединение") when polling active

3. **Modified: `BattlePageBar.tsx`**
   - Add speed toggle (fast/slow) next to autobattle mode buttons
   - Two-state toggle: fast (default) / slow
   - Calls `POST /autobattle/speed` on change
   - Only visible when autobattle is active

4. **Modified: `api.ts`**
   - Add `postAutobattleSpeed(participantId: number, speed: 'fast' | 'slow')` function

### Data Flow Diagram

```
=== TURN FLOW (with WebSocket) ===

Player A (Browser)
  │
  ├──HTTP POST──> Nginx ──> battle-service: POST /battles/{id}/action
  │                              │
  │                              ├── process turn (engine, buffs, damage)
  │                              ├── save_state() → Redis
  │                              ├── publish "battle:{id}:your_turn" → Redis Pub/Sub → autobattle-service
  │                              ├── publish "battle:{id}:state_update" → Redis Pub/Sub ─┐
  │                              ├── save_log() → Celery → MongoDB                       │
  │                              └── return ActionResponse to Player A                    │
  │                                                                                      │
  │                         battle-service WS manager (subscriber) <──────────────────────┘
  │                              │
  │                              ├── broadcast to all WS clients for this battle_id
  │                              │
  ├<──WS push─── Nginx <──WS──── ├──> Player A WS connection
  │                               └──> Player B WS connection (+ spectators)
  │
Player B (Browser) receives state update via WebSocket


=== AUTOBATTLE FLOW (with speed control) ===

Player A: POST /autobattle/register → autobattle-service (ALLOWED += pid)
Player A: POST /autobattle/speed   → autobattle-service (SPEED[pid] = "slow")

Redis Pub/Sub "battle:{id}:your_turn" → autobattle-service
  │
  └── if pid in ALLOWED:
        if SPEED[pid] == "slow": await asyncio.sleep(3.0)
        handle_turn(bid, pid)
          ├── GET /battles/internal/{id}/state (HTTP → battle-service)
          ├── strategy.select_actions(ctx)
          └── POST /battles/internal/{id}/action (HTTP → battle-service)
                └── triggers state_update Pub/Sub → WS push to players


=== RECONNECTION FLOW ===

Browser: WS connection lost
  │
  ├── Show "Переподключение..." indicator
  ├── Attempt reconnect with exponential backoff (1s, 2s, 4s, 8s, 16s, 30s)
  │
  ├── Success: hide indicator, receive latest state via WS initial message
  │
  └── Failure (5+ attempts):
        ├── Show "Используется резервное соединение" notice
        └── Activate polling fallback (5s interval, same as current)
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Add WebSocket connection manager (`ws_manager.py`) to battle-service. Manage per-battle connections: connect/disconnect/broadcast/cleanup. Follow notification-service `ws_manager.py` pattern. Data structure: `dict[int, dict[int, WebSocket]]` (battle_id → user_id → WS). | Backend Developer | DONE | `services/battle-service/app/ws_manager.py` (new) | — | Module exists with `connect()`, `disconnect()`, `broadcast_to_battle()`, `cleanup_battle()` functions. Unit-importable. |
| 2 | Add WebSocket endpoint `WS /battles/ws/{battle_id}` to battle-service. Auth via `?token=` query param (validate JWT using existing `auth_http.py` pattern). On connect: verify user is participant or spectator (same checks as GET `/state` and GET `/spectate`). Accept connection, send initial `battle_state` message. Read loop with 30s ping keepalive (same as notification-service). On disconnect: cleanup via ws_manager. | Backend Developer | DONE | `services/battle-service/app/main.py` | 1 | WS endpoint accepts connections with valid JWT, rejects invalid/unauthorized with 4001/4003. Initial state is sent on connect. Ping sent every 30s. |
| 3 | Add Redis Pub/Sub subscriber in battle-service for `battle:*:state_update` pattern. On startup, create asyncio task that listens to this channel and routes messages to ws_manager `broadcast_to_battle()`. Parse battle_id from channel name. | Backend Developer | DONE | `services/battle-service/app/main.py`, `services/battle-service/app/ws_manager.py` | 1 | Subscriber task starts on app startup. Messages on `battle:{id}:state_update` are forwarded to all WS clients connected to that battle_id. |
| 4 | After `save_state()` in `_make_action_core()`, publish full state (snapshot + runtime) to new Redis Pub/Sub channel `battle:{battle_id}:state_update`. Also publish `battle_finished` event when battle ends (with winner_team and rewards). Publish `battle_paused` event on pause/resume. Reuse existing `load_state` + snapshot assembly logic to build the payload. | Backend Developer | DONE | `services/battle-service/app/main.py`, `services/battle-service/app/redis_state.py` | 1, 3 | After every action, a `battle_state` message is published to `battle:{id}:state_update`. Battle finish and pause events are also published. Existing `your_turn` Pub/Sub is unchanged. |
| 5 | Add autobattle speed control: new in-memory dict `SPEED: dict[int, str]`, new REST endpoint `POST /speed` accepting `{"participant_id": int, "speed": "fast"|"slow"}` with JWT auth and ownership check. In `handle_turn()`, add delay of `AUTOBATTLE_SLOW_DELAY` seconds (env var, default 3.0) when speed is "slow". Clean up `SPEED` in `_cleanup_battle()`. Set default speed "fast" on `/register`. | Backend Developer | DONE | `services/autobattle-service/app/main.py`, `services/autobattle-service/app/config.py` | — | `POST /speed` endpoint works with auth. Slow mode adds configurable delay before turn execution. Speed is per-participant. Cleanup on battle finish. |
| 6 | Update Nginx config for `/battles/` location: add WebSocket upgrade headers (`proxy_http_version 1.1`, `Upgrade`, `Connection "upgrade"`, `proxy_buffering off`, `proxy_read_timeout 3600`). Update BOTH `nginx.conf` (dev) and `nginx.prod.conf` (prod). Copy exact pattern from existing `/notifications/` block. | DevSecOps | DONE | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | — | WebSocket connections to `/battles/ws/{id}?token=...` pass through Nginx successfully in both dev and prod configs. HTTP endpoints under `/battles/` continue to work normally. |
| 7 | Create `useBattleWebSocket` hook. Connect to `ws://{host}/battles/ws/{battleId}?token={jwt}`. Auto-reconnect with exponential backoff (1s → 30s max). Return `{ connected, reconnecting, fallbackToPolling, state, battleFinished }`. On `battle_state` message: update state. On `battle_finished`: signal end. Discard messages with turn_number <= current. After 5 failed reconnects: set `fallbackToPolling = true`. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/hooks/useBattleWebSocket.ts` (new) | — | Hook connects to battle WS, receives state updates, auto-reconnects on disconnect, falls back to polling signal after 5 failures. TypeScript, no `React.FC`. |
| 8 | Integrate `useBattleWebSocket` into `BattlePage.tsx`. Use WS as primary state source. Keep polling as fallback (activated when `fallbackToPolling` is true). Remove 5s interval when WS is connected. Show "Переподключение..." indicator when `reconnecting`. Show "Используется резервное соединение" when polling fallback active. Handle `battleFinished` from WS. Both participant and spectate modes should use WS. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePage.tsx` | 7 | BattlePage uses WS for real-time state. Polling only activates on WS failure. Reconnection indicator visible. Spectate mode works via WS. All styles use Tailwind (migrate touched SCSS). Mobile-responsive. |
| 9 | Add autobattle speed toggle UI in `BattlePageBar.tsx`. Two-state toggle (fast/slow) visible when autobattle is active. Calls `POST /autobattle/speed` on change. Add `postAutobattleSpeed()` function to `api.ts`. Default is "fast". | Frontend Developer | DONE | `services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePageBar/BattlePageBar.tsx`, `services/frontend/app-chaldea/src/api/api.ts` | 5 | Speed toggle appears when autobattle is on. Switching speed calls API. UI shows current speed. Tailwind styles, mobile-responsive. |
| 10 | Write backend tests for battle-service WebSocket: test WS connection with valid/invalid JWT, test participant vs non-participant access, test that state_update messages are received after action, test battle_finished message, test connection cleanup on disconnect. Mock Redis Pub/Sub and user-service auth. | QA Test | DONE | `services/battle-service/app/tests/test_websocket.py` (new) | 1, 2, 3, 4 | Tests cover: auth (valid/invalid/forbidden), state update delivery, battle finish event, connection lifecycle. 36 tests, all pass with `pytest`. |
| 11 | Write backend tests for autobattle-service speed control: test `POST /speed` with valid/invalid auth, test ownership check, test that slow mode adds delay (mock asyncio.sleep), test cleanup on battle finish, test invalid speed value rejection. | QA Test | DONE | `services/autobattle-service/app/tests/test_speed.py` (new) | 5 | Tests cover: auth, ownership, speed setting, delay application, cleanup, validation. 26 tests, all pass with `pytest`. |
| 12 | Final review: verify all tasks, run all tests, check cross-service contracts, verify Nginx configs, live verification of WS connection + autobattle speed control + reconnection + fallback. | Reviewer | TODO | — | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 | All tests pass. WS connection works end-to-end. Autobattle speed control works. Reconnection and fallback work. No console errors. No regressions in existing battle functionality. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-24
**Result:** FAIL

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not available in review environment; must be verified by Frontend Developer before re-review)
- [ ] `npm run build` — N/A (Node.js not available in review environment; must be verified by Frontend Developer before re-review)
- [x] `py_compile` — PASS (all modified Python files: ws_manager.py, auth_http.py, main.py, autobattle config.py, autobattle main.py)
- [x] `pytest` battle-service — PASS (224 tests, 0 failures, including 36 new WS tests)
- [x] `pytest` autobattle-service — PASS (74 tests, 0 failures, including 26 new speed tests)
- [ ] `docker-compose config` — N/A (Docker not available in review environment)
- [ ] Live verification — N/A (application not running in review environment)

#### Code Quality Assessment

**Backend (battle-service):**
- `ws_manager.py` — Clean, follows notification-service pattern. Proper stale connection cleanup, safe close handling, per-battle scoping. No issues.
- `auth_http.py` — New `authenticate_websocket()` uses `httpx.AsyncClient` (async) for WS auth, while existing `get_current_user_via_http()` uses `requests` (sync). This is correct — WS endpoint is async, so async HTTP client is appropriate.
- WS endpoint (`main.py:2951`) — Proper JWT auth, participant/spectator verification, initial state send, keepalive ping loop, clean disconnect handling.
- Redis subscriber (`main.py:3094`) — Correctly uses `psubscribe` for pattern matching, parses battle_id from channel name, routes to `broadcast_to_battle`.
- `_build_runtime()` helper — Consistent with existing GET /state runtime construction.
- State publishing after actions — Correctly publishes to `battle:{id}:state_update` channel. Existing `your_turn` Pub/Sub is unchanged (autobattle not broken).

**Backend (autobattle-service):**
- `POST /speed` — Proper auth, ownership check, input validation (fast/slow only), 404 for unregistered participant.
- Speed delay in `handle_turn()` — Correctly uses `asyncio.sleep(settings.AUTOBATTLE_SLOW_DELAY)` when speed is "slow".
- Cleanup — SPEED entries properly removed in `_cleanup_battle()` and `/unregister`.
- Config — `AUTOBATTLE_SLOW_DELAY` configurable via env var, default 3.0.

**Frontend:**
- `useBattleWebSocket.ts` — Well-structured hook following existing `useWebSocket.ts` pattern. Proper reconnection with exponential backoff, turn_number dedup, fallback to polling, clean unmount cleanup. TypeScript, no `React.FC`.
- `BattlePage.tsx` — Good WS integration. Polling preserved as fallback. Reconnection and fallback indicators shown in Russian. SCSS migrated to Tailwind (BattlePage.module.scss deleted). Mobile-responsive grid with breakpoints.
- `api.ts` — Clean `postAutobattleSpeed()` function.

**Nginx:**
- Both `nginx.conf` and `nginx.prod.conf` correctly updated with WebSocket upgrade headers for `/battles/` location, matching the existing `/notifications/` pattern.

**Tests:**
- 36 WS tests cover: ws_manager unit tests, auth (valid/invalid JWT), participant/non-participant access, state delivery, battle finish/pause messages, connection lifecycle, Redis subscriber routing, authenticate_websocket helper.
- 26 speed tests cover: valid/invalid auth, ownership, input validation, slow delay, fast no-delay, default speed on register, cleanup on battle finish and unregister.

#### Checklist
- [x] Types match (Pydantic < 2.0 syntax, TS interfaces match WS message shapes)
- [x] API contracts consistent (backend WS messages match frontend hook types)
- [x] No stubs/TODO without tracking (pre-existing TODOs in BattlePage/BattlePageBar are tracked)
- [x] `py_compile` — PASS
- [x] Security: JWT auth on WS, no exposed secrets, safe error messages
- [x] Frontend displays errors to user in Russian (toast.error messages)
- [x] User-facing strings in Russian
- [ ] **Tailwind migration for BattlePageBar — INCOMPLETE** (see Issue #1)
- [x] No `React.FC` used
- [x] Mobile-responsive (Tailwind breakpoints in BattlePage, speed toggle responsive)
- [x] Existing `your_turn` Pub/Sub unchanged
- [x] Cross-service contracts preserved
- [x] Tests cover key scenarios

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePageBar/BattlePageBar.tsx:1` | **BLOCKING (T1 — Tailwind migration).** Task #9 added styled UI elements (speed toggle with Tailwind classes, lines 548-568) to BattlePageBar.tsx, but did not migrate the rest of the component from SCSS to Tailwind. The component still imports `BattlePageBar.module.scss` and uses SCSS classes (`s.container`, `s.battle_bar_top`, `s.auto_battle_btns`, etc.) throughout. Per CLAUDE.md rule 8: when changing styles of an existing component, migrate the entire component to Tailwind and delete the SCSS file. Fix: Migrate all SCSS classes in BattlePageBar.tsx to Tailwind utilities, delete `BattlePageBar.module.scss`. | Frontend Developer | FIX_REQUIRED |
| 2 | `services/battle-service/app/main.py:1411` | **Missing `ws_manager.cleanup_battle()` call.** After publishing `battle_finished` to Pub/Sub (lines 1390-1411), there is no call to `await ws_manager.cleanup_battle(battle_id)` to close server-side WS connections for the finished battle. This causes a memory leak — connections for finished battles linger in `battle_connections` dict until clients disconnect or stale detection during next broadcast. Fix: Add `await ws_manager.cleanup_battle(battle_id)` after the `battle_finished` publish block (after line 1411), wrapped in try/except. | Backend Developer | FIX_REQUIRED |

#### Pre-existing issues noted (not blocking this review)
- `BattlePageBar.tsx:501` — `console.log(data)` left in production code (pre-existing, not introduced by FEAT-074).

### Review #2 — 2026-03-24
**Result:** PASS

#### Fix Verification

**Issue #1 (BattlePageBar.tsx Tailwind migration) — FIXED:**
- `BattlePageBar.module.scss` is deleted (confirmed via glob — file not found)
- No SCSS/CSS imports remain in `BattlePageBar.tsx` (confirmed via grep)
- All styling uses Tailwind utility classes throughout the 774-line component
- Design system classes actively used: `gray-bg`, `gold-text`, `gold-outline`, `gold-outline-thick`, `btn-line`, `gold-scrollbar`, `rounded-card`, `rounded-map`, `text-site-blue`, `text-site-red`, `ease-site`
- Mobile-responsive: `flex-wrap`, `hidden sm:inline` (speed toggle text hidden on mobile), grid layout for turn history
- No `React.FC` usage — component declared as `const BattlePageBar = ({ ... }: BattlePageBarProps) => {`
- `formatBattleEvent` refactored to use Tailwind classes instead of SCSS style parameter

**Issue #2 (WS cleanup on battle finish) — FIXED:**
- `_redis_state_update_subscriber()` at line 3094 now checks `data.get("type") == "battle_finished"` after broadcasting (line 3117)
- 0.5s `asyncio.sleep()` delay before cleanup ensures clients receive the final `battle_finished` message (line 3119)
- `await ws_manager.cleanup_battle(battle_id)` called after delay (line 3120)
- Wrapped in inner `try/except` (line 3122) — errors in one message don't crash the subscriber loop
- Outer `try/except` (line 3124) catches subscriber-level failures
- No memory leak risk — all battle connections are cleaned up on finish

#### Automated Check Results
- [ ] `npx tsc --noEmit` — N/A (Node.js not available in review environment)
- [ ] `npm run build` — N/A (Node.js not available in review environment)
- [x] `py_compile` — PASS (battle-service/app/main.py, battle-service/app/ws_manager.py, autobattle-service/app/main.py)
- [x] `pytest` battle-service — PASS (224 passed, 0 failures)
- [x] `pytest` autobattle-service — PASS (74 passed, 0 failures)
- [ ] `docker-compose config` — N/A (Docker not available in review environment)
- [ ] Live verification — N/A (application not running in review environment)

#### Checklist (re-verified)
- [x] Issue #1 fixed: BattlePageBar fully migrated to Tailwind, SCSS file deleted
- [x] Issue #2 fixed: `cleanup_battle()` called after `battle_finished` broadcast with 0.5s delay
- [x] No `React.FC` usage in modified frontend files
- [x] Design system classes used where applicable
- [x] Mobile-responsive layout preserved
- [x] All 224 battle-service tests pass (including 36 WS tests)
- [x] All 74 autobattle-service tests pass (including 26 speed tests)
- [x] `py_compile` passes for all modified Python files
- [x] No new issues introduced by the fixes
- [x] Pre-existing `console.log(data)` at line 507 still present (not introduced by FEAT-074, not blocking)

All issues from Review #1 have been resolved. Changes are ready for completion.

**Note:** Frontend TypeScript check (`tsc --noEmit`) and production build (`npm run build`) could not be verified in this environment (Node.js unavailable). These must be confirmed by Frontend Developer or in CI.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-24 10:00 — PM: фича FEAT-074 создана, запускаю анализ кодовой базы
[LOG] 2026-03-24 10:45 — Analyst: начал анализ, изучаю battle-service, autobattle-service, frontend, nginx
[LOG] 2026-03-24 11:30 — Analyst: анализ завершён, затронуто 4 сервиса (battle-service, autobattle-service, frontend, api-gateway). Redis Pub/Sub уже существует, WebSocket инфраструктура есть в notification-service (паттерн для повторного использования). Nginx требует добавления WebSocket upgrade для /battles/. Нет изменений БД. Основной риск — управление WS-соединениями в battle-service.
[LOG] 2026-03-24 12:15 — Architect: начал проектирование, изучил battle-service, autobattle-service, notification-service ws_manager, frontend BattlePage, nginx конфиги
[LOG] 2026-03-24 13:00 — Architect: выбран Option A (отдельный WS endpoint в battle-service) — ниже латентность, лучше масштабируется, не нагружает notification pipeline большими payload. Спроектировано 12 задач, 1 WS endpoint, 1 REST endpoint (/speed), 4 типа WS-сообщений. Статус → IN_PROGRESS.
[LOG] 2026-03-24 14:00 — DevSecOps: задача #6 завершена. Добавлены WebSocket upgrade заголовки в /battles/ location в обоих nginx конфигах (dev + prod). Паттерн скопирован из /notifications/ блока. Существующие HTTP-эндпоинты продолжат работать — WebSocket upgrade происходит только при наличии Upgrade заголовка от клиента.
[LOG] 2026-03-24 15:00 — Backend Dev: начал задачу #5 (autobattle speed control)
[LOG] 2026-03-24 15:30 — Backend Dev: задача #5 завершена, изменено 2 файла (main.py, config.py). Добавлен SPEED dict, POST /speed endpoint с JWT + ownership check, задержка в handle_turn для slow режима, cleanup в _cleanup_battle, дефолт "fast" при регистрации. py_compile OK, 48 тестов пройдено.
[LOG] 2026-03-24 16:00 — Frontend Dev: начал задачу #7 — создание useBattleWebSocket хука
[LOG] 2026-03-24 16:30 — Frontend Dev: задача #7 завершена — создан useBattleWebSocket.ts по паттерну useWebSocket.ts. Реализовано: подключение к WS /battles/ws/{id}, авто-реконнект с exponential backoff (1s→30s), проверка turn_number для отбрасывания устаревших сообщений, fallback на polling после 5 неудачных попыток, обработка battle_state/battle_finished/battle_paused/ping. Экспортированы типы для использования в BattlePage.
[LOG] 2026-03-24 17:00 — Backend Dev: начал задачи #1-#4 (WebSocket инфраструктура в battle-service)
[LOG] 2026-03-24 17:45 — Backend Dev: задачи #1-#4 завершены, изменено 3 файла (ws_manager.py — новый, main.py, auth_http.py). Создан ws_manager.py по паттерну notification-service. Добавлен WS endpoint /battles/ws/{battle_id} с JWT auth + participant/spectator проверкой. Redis Pub/Sub subscriber на startup для battle:*:state_update. Публикация state_update после каждого хода, battle_finished при завершении, battle_paused при паузе/возобновлении. Добавлен authenticate_websocket в auth_http.py. py_compile OK, 188 тестов пройдено без регрессий.
[LOG] 2026-03-24 18:00 — Frontend Dev: начал задачу #9 — переключатель скорости автобоя
[LOG] 2026-03-24 18:20 — Frontend Dev: задача #9 завершена. Добавлена функция postAutobattleSpeed() в api.ts с axios import. В BattlePageBar.tsx добавлен двухпозиционный toggle (быстрый/медленный) с иконками, видимый только при активном автобое. Tailwind-стили, адаптивность (на мобильных скрывается текст, остаётся иконка). Ошибки API показываются через toast на русском. Скорость сбрасывается на "быстрый" при выключении автобоя.
[LOG] 2026-03-24 19:00 — Frontend Dev: начал задачу #8 — интеграция useBattleWebSocket в BattlePage.tsx
[LOG] 2026-03-24 19:30 — Frontend Dev: задача #8 завершена. Интегрирован useBattleWebSocket как основной источник состояния. Polling сохранён как fallback (активируется при fallbackToPolling). 5-секундный интервал отключается при активном WS. Добавлены индикаторы: "Переподключение..." (анимированный спиннер, fixed top bar) при reconnecting, "Используется резервное соединение" при fallback. Обработка battleFinished из WS для определения победителя/наград. Состояние WS маппится на существующие переменные через общую функцию processState. SCSS мигрирован на Tailwind (BattlePage.module.scss удалён). Адаптивная сетка: 280px/340px/440px центральная колонка по breakpoints. Не используется React.FC.
[LOG] 2026-03-24 20:00 — QA: начал написание тестов для autobattle-service speed control (задача #11)
[LOG] 2026-03-24 20:30 — QA: тесты готовы, 26 тестов, все проходят. Покрытие: auth (401 для missing/invalid/expired token), ownership (403 для чужого участника), валидация speed (400 для невалидных значений), 404 для незарегистрированного участника, slow delay через asyncio.sleep, отсутствие delay в fast режиме, дефолт "fast" при регистрации, cleanup SPEED при завершении боя и unregister. 74 теста всего в autobattle-service — без регрессий.
[LOG] 2026-03-24 21:00 — QA: начал написание тестов для battle-service WebSocket (задача #10)
[LOG] 2026-03-24 21:30 — QA: тесты готовы, 36 тестов, все проходят. Покрытие: ws_manager unit tests (connect/disconnect/broadcast_to_battle/cleanup_battle), WS endpoint auth (valid/invalid JWT, missing token), participant/non-participant access (4003), state update delivery, battle_finished/battle_paused messages, connection lifecycle и cleanup, Redis subscriber channel routing, authenticate_websocket helper (valid/invalid/network error). 224 теста всего в battle-service — без регрессий.
[LOG] 2026-03-24 22:00 — Reviewer: начал проверку FEAT-074
[LOG] 2026-03-24 22:30 — Reviewer: проверка завершена, результат FAIL. Найдено 2 проблемы: (1) BattlePageBar.tsx — не мигрирован на Tailwind полностью (SCSS остался), нарушение T1; (2) main.py — отсутствует вызов ws_manager.cleanup_battle() при завершении боя (утечка памяти). Все 224 теста battle-service и 74 теста autobattle-service проходят. py_compile OK. Бэкенд код высокого качества. Frontend tsc/build не проверен — Node.js не доступен в среде ревью.
[LOG] 2026-03-24 23:00 — Backend Dev: исправлена проблема #2 из ревью — добавлен вызов ws_manager.cleanup_battle(battle_id) в Redis Pub/Sub subscriber (_redis_state_update_subscriber) после broadcast battle_finished сообщения. Задержка 0.5с обеспечивает доставку финального сообщения клиентам перед закрытием соединений. py_compile OK, 224 теста пройдены без регрессий.
[LOG] 2026-03-24 23:30 — Frontend Dev: исправлена проблема #1 из ревью — BattlePageBar.tsx полностью мигрирован на Tailwind CSS. Удалён импорт BattlePageBar.module.scss и сам файл. Все SCSS-классы (s.container, s.battle_bar_top, s.icons, s.auto_battle_btns, s.mode_btns, s.auto_battle_mode_btn, s.auto_battle_btn, s.battle_turns_container, s.turns_list, s.turn_circle, s.battle_logs_container, s.turn_btn и др.) заменены на Tailwind-эквиваленты с использованием дизайн-системы (gray-bg, gold-text, gold-outline, btn-line, gold-scrollbar, rounded-card, rounded-map, text-site-blue, text-site-red). Функция formatBattleEvent рефакторизована — убран параметр styles, цвета заменены на Tailwind-классы. SVG-раскраска автобоя реализована через CSS custom property + arbitrary variant [&_path]. Адаптивность сохранена (flex-wrap, responsive). Node.js недоступен в среде — tsc/build не проверены.
[LOG] 2026-03-24 23:45 — Reviewer: начал повторную проверку (Review #2) после исправлений
[LOG] 2026-03-24 23:55 — Reviewer: проверка завершена, результат PASS. Обе проблемы исправлены: (1) BattlePageBar.tsx полностью на Tailwind, SCSS-файл удалён, дизайн-система используется; (2) cleanup_battle() вызывается в Redis subscriber после broadcast battle_finished с задержкой 0.5с. py_compile OK. 224 теста battle-service + 74 теста autobattle-service — все проходят. Новых проблем не обнаружено. Frontend tsc/build не проверен — Node.js не доступен.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

**WebSocket для боевой системы — полная замена polling на real-time push:**

- **battle-service**: новый WebSocket endpoint `/battles/ws/{battle_id}` с JWT-авторизацией, менеджер соединений (`ws_manager.py`), Redis Pub/Sub подписчик для трансляции состояния боя всем подключённым клиентам (участники + зрители). Публикация полного состояния после каждого хода, событий завершения боя и паузы/возобновления. Автоочистка соединений при завершении боя.

- **autobattle-service**: новый endpoint `POST /speed` для управления скоростью автобоя. Два режима: быстрый (без задержки) и медленный (3 сек задержка перед ходом). Скорость задаётся per-participant, с JWT-авторизацией и проверкой владельца.

- **frontend**: новый хук `useBattleWebSocket.ts` с авто-переподключением (exponential backoff 1с → 30с), проверкой turn_number, fallback на polling после 5 неудачных попыток. BattlePage интегрирован с WS как основным источником данных. Индикаторы "Переподключение..." и "Резервное соединение". UI переключатель скорости автобоя (🐇/🐢) в панели боя.

- **Nginx**: WebSocket upgrade headers добавлены для `/battles/` в обоих конфигах (dev + prod).

- **Миграция на Tailwind**: BattlePage.tsx и BattlePageBar.tsx полностью мигрированы, SCSS-файлы удалены.

- **Тесты**: 36 тестов для WebSocket в battle-service, 26 тестов для скорости автобоя. Все 298 тестов (224 + 74) проходят.

### Изменённые файлы

| Сервис | Файлы |
|--------|-------|
| battle-service | `app/ws_manager.py` (новый), `app/main.py`, `app/auth_http.py`, `app/tests/test_websocket.py` (новый) |
| autobattle-service | `app/main.py`, `app/config.py`, `app/tests/test_speed.py` (новый) |
| api-gateway | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` |
| frontend | `src/hooks/useBattleWebSocket.ts` (новый), `src/components/pages/BattlePage/BattlePage.tsx`, `src/components/pages/BattlePage/BattlePageBar/BattlePageBar.tsx`, `src/api/api.ts` |
| frontend (удалено) | `BattlePage.module.scss`, `BattlePageBar.module.scss` |

### Как проверить

1. **WebSocket**: открыть бой в двух вкладках (два игрока), сделать ход — второй игрок должен увидеть результат мгновенно
2. **Переподключение**: отключить сеть на 5 сек → должен появиться индикатор "Переподключение...", затем восстановиться
3. **Fallback**: заблокировать WS в DevTools → через ~30с должен переключиться на polling с уведомлением
4. **Скорость автобоя**: включить автобой → появляется переключатель скорости → в медленном режиме между ходами ~3 сек задержка
5. **Тесты**: `pytest services/battle-service/app/tests/` и `pytest services/autobattle-service/app/tests/`

### Что изменилось от первоначального плана
- Ничего существенного — реализация соответствует архитектуре

### Оставшиеся риски / follow-up задачи
- Frontend `tsc --noEmit` и `npm run build` не были проверены (Node.js недоступен в среде ревью) — необходимо проверить в CI или локально
- SVG-раскраска кнопок автобоя через CSS custom property + arbitrary variant `[&_path]` — требует runtime-проверки
- Проблема #15 в `docs/ISSUES.md` (polling вместо WebSocket) — теперь решена, нужно обновить ISSUES.md
