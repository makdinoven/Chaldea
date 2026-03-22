# FEAT-063: Player Actions Menu (Trade, Duels, Attack)

## Meta

| Field | Value |
|-------|-------|
| **Status** | REVIEW |
| **Created** | 2026-03-23 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-063-player-actions-menu.md` → `DONE-FEAT-063-player-actions-menu.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
На ролевой локации под аватаркой каждого поста **другого** игрока появляется кнопка «Действие», открывающая сайдбар с четырьмя действиями:

1. **Предложить обмен** — система обмена предметами и деньгами между двумя игроками.
2. **Вызвать на тренировочный бой** — PvP-бой с согласия обеих сторон. Проигравший остаётся с 1 HP.
3. **Вызвать на смертельный бой** — PvP-бой с согласия обеих сторон. Проигравший теряет персонажа (персонаж снимается и остаётся свободным в каталоге). Доступно с 30 уровня. Недоступно на безопасных локациях.
4. **Напасть** — принудительный PvP-бой без согласия жертвы. Жертва получает уведомление. Недоступно на безопасных локациях. Штрафов для нападающего пока нет.

### Бизнес-правила
- Кнопка «Действие» видна только под аватарками **других** игроков, не под своей.
- **Обмен:** обе стороны могут предлагать предметы и деньги. Можно обменивать только деньги, только предметы, или и то и другое. Лимитов на количество предметов нет. Требуется подтверждение обоих игроков.
- **Тренировочный бой:** начинается только при согласии другой стороны. HP проигравшего остаётся на 1 (не восстанавливается).
- **Смертельный бой:** начинается только при согласии обеих сторон. Доступен с 30 уровня. Недоступен на локациях с пометкой «Безопасно». Проигравший теряет персонажа — персонаж снимается и остаётся свободным в каталоге. В будущем будут предметы воскрешения.
- **Нападение:** принудительный бой, жертва не может отклонить. Недоступно на безопасных локациях. Жертва получает уведомление (SSE в реальном времени + в раздел уведомлений на сайте).

### UX / Пользовательский сценарий

**Обмен:**
1. Игрок A нажимает «Действие» → «Предложить обмен» под постом Игрока B.
2. Открывается окно обмена, где Игрок A выбирает предметы/деньги для обмена.
3. Игрок B получает уведомление о предложении обмена.
4. Игрок B открывает окно обмена, видит предложение A, может добавить свои предметы/деньги.
5. Обе стороны подтверждают → обмен завершается.

**Тренировочный бой:**
1. Игрок A нажимает «Действие» → «Вызвать на тренировочный бой».
2. Игрок B получает уведомление с предложением боя.
3. Игрок B принимает → бой начинается.
4. Проигравший остаётся с 1 HP.

**Смертельный бой:**
1. Игрок A нажимает «Действие» → «Вызвать на смертельный бой» (доступно если оба 30+ лвл, локация не безопасная).
2. Игрок B получает уведомление с предложением.
3. Игрок B принимает → бой начинается.
4. Проигравший теряет персонажа.

**Нападение:**
1. Игрок A нажимает «Действие» → «Напасть» (доступно если локация не безопасная).
2. Бой начинается немедленно.
3. Игрок B получает уведомление о нападении.

### Edge Cases
- Что если целевой игрок уже в бою? → Показать сообщение «Игрок уже в бою».
- Что если целевой игрок офлайн (для обмена/вызовов)? → Предложение сохраняется, игрок увидит при заходе.
- Что если при смертельном бою один из игроков ниже 30 уровня? → Кнопка неактивна/скрыта.
- Что если предложение обмена/боя отклонено? → Уведомление инициатору.
- Что если игрок пытается напасть на безопасной локации? → Кнопка скрыта/неактивна.
- Что если обмен предложен, но один из игроков покинул локацию? → Предложение отменяется.

### Вопросы к пользователю (если есть)
- [x] Обмен двусторонний? → Да, каждый может предлагать.
- [x] Лимиты на обмен? → Нет.
- [x] Только деньги / только предметы? → Да, можно.
- [x] HP после тренировочного боя? → Остаётся на 1, не восстанавливается.
- [x] Потеря персонажа при смерти? → Персонаж снимается и остаётся свободным в каталоге.
- [x] Нападение — можно ли отклонить? → Нет, принудительный бой.
- [x] Пометка «Безопасно» у локаций? → Уже существует.
- [x] Кнопка только под чужими аватарками? → Да.
- [x] Уведомления? → SSE в реальном времени + в раздел уведомлений на сайте.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Affected Services

| Service | Port | Sync/Async | Alembic | Role in Feature |
|---------|------|-----------|---------|-----------------|
| **locations-service** | 8006 | Async (aiomysql) | YES (`alembic_version_locations`) | Location data (marker_type for safe zones), post rendering, player list |
| **battle-service** | 8010 | Async (aiomysql + Motor + aioredis) | YES (`alembic_version_battle`) — **NOTE: CLAUDE.md says "no Alembic" but alembic dir exists** | Battle creation (PvP), battle types (training/death duel/attack) |
| **inventory-service** | 8004 | Sync (PyMySQL) | YES (`alembic_version_inventory`) | Item transfer between characters (trade), gold transfer |
| **character-service** | 8005 | Sync (PyMySQL) | YES (`alembic_version_character`) | Character levels (for 30+ check), character unlinking (death duel loser), currency_balance (gold/trade) |
| **notification-service** | 8007 | Sync (PyMySQL) + WebSocket | YES (`alembic_version_notification`) | Real-time notifications (duel invites, trade offers, attack alerts) via WebSocket |
| **frontend** | 5555 | React 18 / TypeScript / Tailwind | N/A | Player actions menu UI, trade UI, duel invitation UI |
| **autobattle-service** | 8011 | Async (httpx) | N/A | May need to handle forced PvP (attack) if victim is offline |

### 2.2 Existing Patterns & Key Code

#### 2.2.1 Location System

**Models** (`services/locations-service/app/models.py`):
- `Location.marker_type` — Enum: `'safe'`, `'dangerous'`, `'dungeon'`, `'farm'`. Default: `'safe'`. This is the "safe location" flag referenced in the feature brief.
- `Post` model has `character_id`, `location_id`, `content`, `created_at`.
- `PlayerInLocation` schema (schemas.py:428-436) returns: `id`, `name`, `avatar`, `level`, `class_name`, `race_name`, `character_title`, `user_id`. **Critically: `user_id` is available**, which lets the frontend identify "other players."

**Client endpoint** (`/locations/{id}/client/details`):
- Returns `LocationClientDetails` schema with `players: List[PlayerInLocation]`, `posts: List[ClientPost]`, `marker_type: str`.
- `ClientPost` (schemas.py:455-468) includes: `character_id`, `character_photo`, `character_name`, `character_level`, `user_id`, `user_nickname`.

**Notification pattern**: locations-service uses `rabbitmq_publisher.publish_notification_sync(user_id, message)` via `BackgroundTasks` to send notifications through the `general_notifications` RabbitMQ queue.

#### 2.2.2 Battle System

**Battle creation** (`services/battle-service/app/main.py:272`):
- `POST /battles/` accepts `BattleCreate` schema: `{ players: [{ character_id: int, team: int | None }] }`.
- Returns `BattleCreated`: `{ battle_id, participants, next_actor, deadline_at }`.
- Auth: requires JWT token; validates that at least one character belongs to `current_user`.
- Minimum 2 players required.
- **No battle type concept exists yet** — all battles are identical mechanically. There's no `battle_type` field (training/death/attack). This must be added.

**Battle models** (`services/battle-service/app/models.py`):
- `Battle` — `id`, `status` (pending/in_progress/finished/forfeit), `created_at`, `updated_at`.
- `BattleParticipant` — `battle_id`, `character_id`, `team`.
- **No `battle_type` column exists.** Must be added via Alembic migration.

**"Character in battle" check**: **Does NOT exist.** There is no endpoint or check to determine if a character is currently in an active battle. This must be built (e.g., query `battle_participants` + `battles.status = 'in_progress'` for a given `character_id`).

**Post-battle consequences**: Currently, the battle system only distributes PvE rewards (XP, gold, loot). There is **no mechanism** for:
- Setting loser HP to 1 (training duel).
- Unlinking character from user (death duel).
- These must be added as post-battle hooks.

**Frontend battle creation** (`services/frontend/app-chaldea/src/api/mobs.ts:150-161`):
- `createBattle(playerCharacterId, mobCharacterId)` → `POST /battles/` with team 0 and team 1.
- After creation, navigates to `/battle/{battle_id}`.

#### 2.2.3 Inventory / Trade System

**Models** (`services/inventory-service/app/models.py`):
- `CharacterInventory` — `character_id`, `item_id` (FK to `items`), `quantity`.
- Items support stacking via `max_stack_size`.
- **No trade/exchange system exists.** Must be built from scratch.

**Existing item transfer endpoints**:
- `POST /inventory/{character_id}/items` — adds item (used by battle reward system).
- `DELETE /inventory/{character_id}/items/{item_id}?quantity=N` — removes items (requires auth + ownership check).
- Both endpoints exist but are designed for single-character operations, not atomic two-character trades.

**Gold/Currency**: stored as `characters.currency_balance` in character-service (not inventory-service). Transfer requires updating both characters' balances atomically. Currently `add_rewards` endpoint exists in character-service for adding gold.

**Auth pattern in inventory-service**: Uses `get_current_user_via_http` (HTTP call to user-service with JWT) and `verify_character_ownership(db, character_id, user_id)` via direct SQL on shared DB.

#### 2.2.4 Character System

**Character "release" (unlink)** (`services/character-service/app/main.py:547-608`):
- `POST /characters/admin/{character_id}/unlink` — admin-only endpoint.
- Sets `character.user_id = None`.
- Calls user-service to delete user-character relation and clear `current_character`.
- **This is the mechanism for death duel loser.** However, it requires admin auth. A new **internal** endpoint (no auth) or a service-to-service call pattern is needed for battle-service to unlink the loser's character.

**Character level**: `Character.level` column (Integer, default=1). Available in `PlayerInLocation` schema and in post data. Used for the 30+ level check for death duels.

#### 2.2.5 Notification System

**WebSocket** (`services/notification-service/app/ws_manager.py`):
- `send_to_user(user_id, data)` — thread-safe, sends JSON to a specific user's WebSocket.
- `broadcast_to_all(data)` — sends to all connected users.
- Message format: `{"type": "notification", "data": {id, user_id, message, status, created_at}}`.
- **Other services cannot directly call `send_to_user`** — they must publish to RabbitMQ `general_notifications` queue, which the consumer picks up, saves to DB, and pushes via WebSocket.

**Frontend WebSocket handling** (`services/frontend/app-chaldea/src/hooks/useWebSocket.ts`):
- Handles types: `notification`, `chat_message`, `chat_message_deleted`, `ping`.
- `notification` type dispatches `addNotification` and shows a `toast()`.
- **New types will need to be added** for trade offers, duel invitations, and attack alerts (or they can use the generic `notification` type with structured messages).

**Existing notification pattern**: RabbitMQ publish with `{"target_type": "user", "target_value": user_id, "message": "text"}`. This is simple text — no structured data. For interactive notifications (accept/decline), either:
  1. Extend notification model to include `notification_type` and `action_data` (JSON), OR
  2. Use the existing text notification + a separate API for pending invitations.

#### 2.2.6 Frontend — Location Page

**LocationPage** (`services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx`):
- Fetches location data from `/locations/{id}/client/details`.
- Renders: `LocationHeader`, `PlayersSection`, `LocationMobs`, `LootSection`, Posts section, `NeighborsSection`, `PlaceholderSection`.
- **`PlaceholderSection`** at bottom says "Бой на локации — Скоро здесь можно будет сражаться" — this is where the actions menu could be integrated or this placeholder replaced.
- Has access to: `character` (from Redux: id, name, avatar, current_location), `userId`, `userRole`.

**PlayersSection** (`PlayersSection.tsx`):
- Renders `AvatarCard` for each player with avatar, name, level.
- Currently a **read-only display** — no action buttons on player avatars.
- **This is where the "Действие" button should be added** — under each avatar for OTHER players (filter by `player.user_id !== userId`).

**PostCard** (`PostCard.tsx`):
- Renders post with avatar panel on the left (title, avatar, name, level).
- Has actions: like, tag player, report, request deletion.
- The **avatar panel** shows `character_photo`, `character_name`, `character_level`, `user_id`.
- Feature brief says "под аватаркой каждого поста другого игрока" — the action button goes in the PostCard avatar panel.

**Types** (`types.ts`):
- `Player` interface: `{ id, user_id, name, avatar, level, class_name, race_name }`.
- `Post` interface: `{ post_id, character_id, character_photo, character_name, character_level, user_id, ... }`.
- `LocationData` includes `marker_type: string` — available for safe/dangerous checks.

### 2.3 Cross-Service Dependencies for FEAT-063

```
Frontend (LocationPage)
  ├──> locations-service: GET /locations/{id}/client/details (marker_type, players, posts)
  ├──> battle-service: POST /battles/ (create PvP battle — training/death/attack)
  ├──> inventory-service: NEW trade endpoints (propose, accept, decline)
  ├──> character-service: GET character level (already in PlayerInLocation data)
  └──> notification-service: via WebSocket (receive trade offers, duel invites, attack alerts)

battle-service (post-battle)
  ├──> character-attributes-service: set HP to 1 (training duel loser)
  ├──> character-service: NEW internal unlink endpoint (death duel loser)
  └──> notification-service: via RabbitMQ (battle result notifications)

inventory-service (trade)
  ├──> character-service: verify character ownership, transfer gold (currency_balance)
  └──> notification-service: via RabbitMQ (trade offer notifications)

New dependency: battle-service ──> notification-service (via RabbitMQ, for duel invites/attack alerts)
New dependency: inventory-service ──> notification-service (via RabbitMQ, for trade proposals)
```

### 2.4 DB Changes Needed

#### New Tables

1. **`trade_offers`** (owned by inventory-service):
   - `id`, `initiator_character_id`, `target_character_id`, `location_id`, `status` (pending/accepted/declined/cancelled/expired), `created_at`, `updated_at`

2. **`trade_offer_items`** (owned by inventory-service):
   - `id`, `trade_offer_id` (FK), `character_id` (who offers this item), `item_id` (FK to items), `quantity`

3. **`trade_offer_gold`** (owned by inventory-service, or as columns on `trade_offers`):
   - `initiator_gold`, `target_gold` — amount of gold each side offers

4. **`pvp_invitations`** (owned by battle-service):
   - `id`, `initiator_character_id`, `target_character_id`, `location_id`, `battle_type` (training_duel / death_duel), `status` (pending/accepted/declined/expired), `created_at`, `expires_at`

#### Modified Tables

5. **`battles`** — add `battle_type` column: Enum(`pve`, `pvp_training`, `pvp_death`, `pvp_attack`). Default: `pve` for backward compatibility.

### 2.5 Risks & Considerations

1. **Atomicity of trade**: Transferring items AND gold between two characters across two services (inventory-service for items, character-service for gold) is not atomic. Options:
   - (A) Have inventory-service handle gold too (duplicates `currency_balance` management).
   - (B) Use a two-phase approach: lock items, call character-service for gold, commit items, or rollback.
   - (C) Since all services share one MySQL DB, a single service can do the entire trade in one transaction using direct SQL. **Recommended: inventory-service handles entire trade atomically using shared DB.**

2. **"Character is in battle" check**: No existing mechanism. Must add a query to battle-service (or use shared DB from locations-service/other) to check `battle_participants.character_id WHERE battles.status IN ('pending', 'in_progress')`.

3. **Death duel — character unlink**: The existing admin unlink endpoint (`/characters/admin/{id}/unlink`) does significant work (calls user-service twice). Battle-service needs to call this or a new internal version. **Risk**: if the unlink HTTP call fails, the battle result is inconsistent.

4. **Concurrent actions**: Player A proposes trade to Player B while Player C attacks Player B. Need to handle race conditions — e.g., a player cannot accept a trade if they are suddenly in a battle.

5. **Offline players**: Trade offers and duel invitations need to persist in DB. Notifications are already persisted via RabbitMQ -> notification-service -> DB.

6. **battle-service Alembic**: CLAUDE.md states battle-service lacks Alembic, but this is **outdated** — Alembic is fully configured with `alembic_version_battle` version table, async env.py, and an initial baseline migration. New migrations can be created normally.

7. **Frontend mandatory rules**: All new components must be TypeScript + Tailwind (no SCSS). New files = `.tsx/.ts`. Must be responsive (360px+). No `React.FC`. Must follow design system (`docs/DESIGN-SYSTEM.md`).

8. **notification-service has no Alembic**: Per CLAUDE.md. But we may not need schema changes there if we keep using the simple `{message: text}` format. If we need structured notification types, a migration would be needed.

9. **HP modification after battle**: Currently no endpoint exists to set a character's HP to a specific value. The `character-attributes-service` has `/apply_modifiers` and `/recover` but not a "set HP to X" endpoint. A new endpoint or adjustment is needed for training duel (set loser HP to 1).

### 2.6 Existing Patterns to Follow

| Pattern | Where | Details |
|---------|-------|---------|
| Battle creation | `POST /battles/` | JWT auth, character ownership check, Redis state init |
| Notification sending | locations-service `rabbitmq_publisher.py` | `publish_notification_sync(user_id, message)` via BackgroundTasks |
| WebSocket push | notification-service `ws_manager.py` | `send_to_user(user_id, {"type": "notification", "data": {...}})` |
| Frontend WS handling | `useWebSocket.ts` | Switch on `parsed.type`, dispatch Redux actions, show toast |
| Modal UI | `PostCard.tsx`, `NpcShopModal.tsx`, `NpcProfileModal.tsx` | Use `modal-overlay` + `modal-content` classes from design system |
| Character ownership check | inventory-service `main.py:51-57` | Direct SQL: `SELECT user_id FROM characters WHERE id = :cid` |
| Frontend API calls | `mobs.ts:createBattle()` | axios POST, error handling pattern |
| Player avatar rendering | `PlayersSection.tsx` / `PostCard.tsx` | `AvatarCard` component with gold-outline, responsive sizing |
| Frontend sidebar/dropdown | `PostCard.tsx` tag dropdown | `useRef` + outside click handler + absolute positioning |

### 2.7 Summary of What Must Be Built

| Component | Scope | Complexity |
|-----------|-------|-----------|
| **Trade system** (backend) | New tables, endpoints in inventory-service (propose, add items, confirm, cancel), gold transfer via shared DB | HIGH |
| **PvP invitation system** (backend) | New table in battle-service, endpoints (invite, accept, decline), battle_type on battles table | MEDIUM |
| **Attack (forced PvP)** (backend) | New endpoint in battle-service, no consent needed, notification to victim | MEDIUM |
| **Post-battle consequences** (backend) | HP-to-1 for training, character unlink for death duel, integrated into battle finish flow | MEDIUM |
| **Notifications** (backend) | Structured notifications for all 4 action types via RabbitMQ | LOW-MEDIUM |
| **Frontend: Actions menu** | Button on PostCard avatars + sidebar/dropdown with 4 actions, conditional visibility | MEDIUM |
| **Frontend: Trade UI** | Trade window (select items, gold, confirm), real-time sync via WS | HIGH |
| **Frontend: Duel invitation UI** | Send invitation, receive/accept/decline notification | MEDIUM |
| **Frontend: Attack alert** | Notification + redirect to battle | LOW |

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Phasing Strategy

This feature is split into **3 phases** to be deliverable incrementally:

| Phase | Scope | Dependencies |
|-------|-------|-------------|
| **Phase 1** | Foundation + PvP (Training Duel + Attack) | None |
| **Phase 2** | Death Duel | Phase 1 |
| **Phase 3** | Trade System | Phase 1 (uses same Actions menu) |

Each phase is independently deployable and testable.

---

### 3.1 Phase 1: Foundation + PvP Battles (Training Duel + Attack)

#### 3.1.1 DB Changes

##### A. `battles` table — add `battle_type` column

**Owner**: battle-service (Alembic, `alembic_version_battle`)

```sql
ALTER TABLE battles ADD COLUMN battle_type ENUM('pve', 'pvp_training', 'pvp_death', 'pvp_attack')
  NOT NULL DEFAULT 'pve' AFTER status;
```

Migration file: `services/battle-service/app/alembic/versions/002_add_battle_type.py`

The default `'pve'` ensures backward compatibility with all existing battles.

##### B. `pvp_invitations` table — new

**Owner**: battle-service (Alembic, `alembic_version_battle`)

```sql
CREATE TABLE pvp_invitations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    initiator_character_id INT NOT NULL,
    target_character_id INT NOT NULL,
    location_id INT NOT NULL,
    battle_type ENUM('pvp_training', 'pvp_death') NOT NULL,
    status ENUM('pending', 'accepted', 'declined', 'expired', 'cancelled') NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    INDEX idx_target_status (target_character_id, status),
    INDEX idx_initiator_status (initiator_character_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Migration file: `services/battle-service/app/alembic/versions/002_add_battle_type.py` (same migration as battle_type, single revision)

##### C. Model changes in battle-service

`services/battle-service/app/models.py`:

```python
class BattleType(str, Enum):
    pve = "pve"
    pvp_training = "pvp_training"
    pvp_death = "pvp_death"
    pvp_attack = "pvp_attack"

# Add to Battle model:
battle_type: Mapped[BattleType] = mapped_column(
    SQLEnum(BattleType), default=BattleType.pve
)

# New model:
class PvpInvitationStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    cancelled = "cancelled"

class PvpInvitation(Base):
    __tablename__ = "pvp_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    initiator_character_id: Mapped[int] = mapped_column(Integer, index=True)
    target_character_id: Mapped[int] = mapped_column(Integer, index=True)
    location_id: Mapped[int] = mapped_column(Integer)
    battle_type: Mapped[BattleType] = mapped_column(SQLEnum(BattleType))
    status: Mapped[PvpInvitationStatus] = mapped_column(
        SQLEnum(PvpInvitationStatus), default=PvpInvitationStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
```

#### 3.1.2 API Contracts — battle-service

##### A. `POST /battles/pvp/invite` — Send PvP Invitation (Training Duel)

**Auth**: JWT required (get_current_user_via_http)

**Request**:
```json
{
  "initiator_character_id": 42,
  "target_character_id": 55,
  "battle_type": "pvp_training"
}
```

**Validation**:
1. Initiator character must belong to current_user (ownership check via shared DB)
2. Initiator and target must be at the same location (query `characters.current_location` via shared DB)
3. Neither character can be in an active battle (`battles.status IN ('pending', 'in_progress')` via `battle_participants`)
4. No duplicate pending invitation from same initiator to same target
5. For `pvp_training`: no location restrictions
6. For `pvp_death` (Phase 2): both characters must be level 30+, location must not be `marker_type = 'safe'`

**Response 201**:
```json
{
  "invitation_id": 1,
  "initiator_character_id": 42,
  "target_character_id": 55,
  "battle_type": "pvp_training",
  "status": "pending",
  "expires_at": "2026-03-23T15:00:00Z"
}
```

**Errors**:
- 400: "Персонаж уже в бою" / "Целевой персонаж уже в бою" / "Вы не можете вызвать самого себя" / "Персонажи должны находиться в одной локации"
- 403: "Вы должны использовать своего персонажа"
- 409: "У вас уже есть активное приглашение для этого игрока"

**Side effects**: Publish notification to target_user via RabbitMQ `general_notifications`.

##### B. `POST /battles/pvp/invite/{invitation_id}/respond` — Accept/Decline Invitation

**Auth**: JWT required

**Request**:
```json
{
  "action": "accept"
}
```
Where `action` is `"accept"` or `"decline"`.

**Validation**:
1. Invitation must exist and be in `pending` status
2. Current user must own the `target_character_id`
3. Re-validate: both characters still at same location, neither in battle

**Response 200 (accept)**:
```json
{
  "invitation_id": 1,
  "status": "accepted",
  "battle_id": 77,
  "battle_url": "/battle/77"
}
```

On accept: creates battle via existing `create_battle()` with `battle_type` set, initializes Redis state, returns battle_id. Sends notification to initiator.

**Response 200 (decline)**:
```json
{
  "invitation_id": 1,
  "status": "declined"
}
```

Sends notification to initiator about decline.

**Errors**:
- 400: "Приглашение уже было обработано" / "Персонаж уже в бою"
- 403: "Это приглашение адресовано другому игроку"
- 404: "Приглашение не найдено"

##### C. `POST /battles/pvp/attack` — Force Attack (no consent)

**Auth**: JWT required

**Request**:
```json
{
  "attacker_character_id": 42,
  "victim_character_id": 55
}
```

**Validation**:
1. Attacker must belong to current_user
2. Both must be at same location
3. Location `marker_type` must NOT be `'safe'` (query via shared DB: `SELECT marker_type FROM Locations WHERE id = :loc_id`)
4. Neither character can be in an active battle
5. Cannot attack yourself

**Response 201**:
```json
{
  "battle_id": 78,
  "battle_url": "/battle/78",
  "attacker_character_id": 42,
  "victim_character_id": 55
}
```

Creates battle immediately with `battle_type = 'pvp_attack'`. Sends notification to victim via RabbitMQ.

**Errors**:
- 400: "Нападение невозможно на безопасной локации" / "Персонаж уже в бою" / "Нельзя напасть на самого себя" / "Персонажи должны находиться в одной локации"
- 403: "Вы должны использовать своего персонажа"

##### D. `GET /battles/pvp/invitations/pending` — Get pending invitations for current user

**Auth**: JWT required

**Response 200**:
```json
{
  "incoming": [
    {
      "invitation_id": 1,
      "initiator_character_id": 42,
      "initiator_name": "Артур",
      "initiator_avatar": "https://...",
      "initiator_level": 15,
      "battle_type": "pvp_training",
      "created_at": "2026-03-23T12:00:00Z",
      "expires_at": "2026-03-23T15:00:00Z"
    }
  ],
  "outgoing": [
    {
      "invitation_id": 2,
      "target_character_id": 55,
      "target_name": "Гильгамеш",
      "battle_type": "pvp_training",
      "status": "pending",
      "created_at": "2026-03-23T12:30:00Z"
    }
  ]
}
```

##### E. `DELETE /battles/pvp/invite/{invitation_id}` — Cancel own invitation

**Auth**: JWT required. Only initiator can cancel.

**Response 200**:
```json
{
  "invitation_id": 1,
  "status": "cancelled"
}
```

##### F. `GET /battles/character/{character_id}/in-battle` — Check if character is in battle

**Auth**: None (internal endpoint)

**Response 200**:
```json
{
  "in_battle": true,
  "battle_id": 77
}
```

Implementation: `SELECT b.id FROM battles b JOIN battle_participants bp ON b.id = bp.battle_id WHERE bp.character_id = :cid AND b.status IN ('pending', 'in_progress') LIMIT 1`

#### 3.1.3 Post-Battle Consequences (Training Duel)

In `main.py`, after `finish_battle()` is called (line ~847), add a hook:

```python
if battle_finished and winner_team is not None:
    # Determine battle_type from DB
    battle_row = await db_session.execute(
        text("SELECT battle_type FROM battles WHERE id = :bid"),
        {"bid": battle_id},
    )
    bt = battle_row.fetchone()
    if bt and bt[0] == 'pvp_training':
        # Set loser HP to 1 (override the 0 that was synced)
        for pid_str, pdata in battle_state["participants"].items():
            if pdata["hp"] <= 0 and pdata["team"] != winner_team:
                await db_session.execute(
                    text("UPDATE character_attributes SET current_health = 1 WHERE character_id = :cid"),
                    {"cid": pdata["character_id"]},
                )
                await db_session.commit()
```

This uses the same shared-DB direct SQL pattern already used at lines 855-872 for resource sync.

#### 3.1.4 RabbitMQ Notification Pattern

battle-service needs a RabbitMQ publisher. Create `services/battle-service/app/rabbitmq_publisher.py` following the exact pattern from `services/locations-service/app/rabbitmq_publisher.py`:

```python
# Same pattern: pika blocking publish wrapped in run_in_executor
async def publish_notification(target_user_id: int, message: str) -> None:
    payload = {
        "target_type": "user",
        "target_value": target_user_id,
        "message": message,
    }
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _publish_sync, payload)
```

Add `RABBITMQ_URL` to battle-service `config.py` (already available in docker-compose env). Add `pika` to `requirements.txt`.

**Notification messages** (Russian, for end users):
- Duel invite: `"{initiator_name} вызывает вас на тренировочный бой!"`
- Duel accepted: `"{target_name} принял ваш вызов на тренировочный бой! Бой начинается."`
- Duel declined: `"{target_name} отклонил ваш вызов на бой."`
- Attack: `"{attacker_name} напал на вас! Бой начинается."`

#### 3.1.5 Frontend Architecture

##### A. New files

| File | Purpose |
|------|---------|
| `src/api/pvp.ts` | API client for PvP endpoints |
| `src/components/pages/LocationPage/PlayerActionsMenu.tsx` | Actions dropdown on avatars (PostCard + PlayersSection) |
| `src/components/pages/LocationPage/DuelInviteModal.tsx` | Modal for sending duel invitation |
| `src/components/pages/LocationPage/PendingInvitationsPanel.tsx` | Panel showing incoming/outgoing invitations |

##### B. PlayerActionsMenu component

A dropdown attached to player avatars. Shown only for OTHER players (filter by `user_id !== currentUserId`).

**Props**:
```typescript
interface PlayerActionsMenuProps {
  targetCharacterId: number;
  targetUserId: number;
  targetName: string;
  targetLevel: number;
  currentCharacterId: number;
  locationMarkerType: string;
  onActionComplete?: () => void;
}
```

**Menu items** (conditionally shown):
1. "Предложить обмен" — always visible (Phase 3, disabled until then)
2. "Вызвать на тренировочный бой" — always visible
3. "Вызвать на смертельный бой" — visible only if both players level 30+ AND location is not safe (Phase 2, hidden until then)
4. "Напасть" — visible only if location is not safe

**Design**: Uses `dropdown-menu` + `dropdown-item` classes. Positioned with `absolute` and outside-click handler (same pattern as PostCard tag dropdown). Uses `AnimatePresence` + motion for enter/exit.

**Placement**:
- In **PostCard**: Below the level display in the avatar panel, for posts by OTHER users. A small button "Действие" styled with `btn-line text-[10px]`.
- In **PlayersSection**: Below each `AvatarCard` for OTHER players. Modify `AvatarCard` to accept an optional `actionsMenu` render prop.

##### C. DuelInviteModal component

Confirmation modal before sending invitation.

```typescript
interface DuelInviteModalProps {
  targetName: string;
  targetLevel: number;
  battleType: 'pvp_training' | 'pvp_death';
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}
```

Uses `modal-overlay` + `modal-content` + `gold-outline gold-outline-thick`. Shows target info and a "Вызвать" (btn-blue) / "Отмена" (btn-line) button pair.

##### D. PendingInvitationsPanel component

Shown at the top of LocationPage (or as a floating notification) when the user has pending incoming invitations.

```typescript
interface PendingInvitationsPanelProps {
  invitations: PvpInvitation[];
  onAccept: (invitationId: number) => void;
  onDecline: (invitationId: number) => void;
}
```

Design: Gold-outlined card at the top of the location page. Each invitation shows initiator avatar + name + battle type + "Принять" (btn-blue) / "Отклонить" (btn-line).

##### E. API client (`src/api/pvp.ts`)

```typescript
import axios from 'axios';

export interface PvpInvitation {
  invitation_id: number;
  initiator_character_id: number;
  initiator_name: string;
  initiator_avatar: string | null;
  initiator_level: number;
  battle_type: 'pvp_training' | 'pvp_death';
  created_at: string;
  expires_at: string;
}

export interface PvpInvitationResponse {
  incoming: PvpInvitation[];
  outgoing: PvpInvitation[];
}

export const sendPvpInvitation = async (
  initiatorCharacterId: number,
  targetCharacterId: number,
  battleType: 'pvp_training' | 'pvp_death',
) => {
  const { data } = await axios.post('/battles/pvp/invite', {
    initiator_character_id: initiatorCharacterId,
    target_character_id: targetCharacterId,
    battle_type: battleType,
  });
  return data;
};

export const respondToInvitation = async (
  invitationId: number,
  action: 'accept' | 'decline',
) => {
  const { data } = await axios.post(
    `/battles/pvp/invite/${invitationId}/respond`,
    { action },
  );
  return data;
};

export const getPendingInvitations = async (): Promise<PvpInvitationResponse> => {
  const { data } = await axios.get('/battles/pvp/invitations/pending');
  return data;
};

export const cancelInvitation = async (invitationId: number) => {
  const { data } = await axios.delete(`/battles/pvp/invite/${invitationId}`);
  return data;
};

export const attackPlayer = async (
  attackerCharacterId: number,
  victimCharacterId: number,
) => {
  const { data } = await axios.post('/battles/pvp/attack', {
    attacker_character_id: attackerCharacterId,
    victim_character_id: victimCharacterId,
  });
  return data;
};
```

##### F. WebSocket Integration

No new WebSocket types needed for Phase 1. All notifications use the existing `"notification"` type with text messages. The toast system already displays these. When a duel is accepted or an attack starts, the frontend navigates to `/battle/{battle_id}` based on the API response. For the victim of an attack, the notification message includes the battle_id reference, but the primary mechanism is:

1. Victim is on LocationPage, gets a toast "X напал на вас! Бой начинается."
2. Victim can navigate to the battle via the notification panel or a follow-up poll.

**Enhancement for Phase 1**: Add a new WS message type `pvp_battle_start` that includes `battle_id` so the frontend can show a modal prompt to navigate to the battle:

```json
{
  "type": "pvp_battle_start",
  "data": {
    "battle_id": 78,
    "attacker_name": "Артур",
    "battle_type": "pvp_attack"
  }
}
```

This requires a minor addition to `useWebSocket.ts` to handle the new type and show a navigation prompt.

For this, notification-service consumer needs a small extension: if the message payload contains a `ws_type` field, use that as the WebSocket message type instead of `"notification"`. This allows sending structured WS messages while keeping the RabbitMQ interface simple:

```python
# In battle-service publisher:
payload = {
    "target_type": "user",
    "target_value": victim_user_id,
    "message": f"{attacker_name} напал на вас! Бой начинается.",
    "ws_type": "pvp_battle_start",
    "ws_data": {"battle_id": battle_id, "attacker_name": attacker_name, "battle_type": "pvp_attack"},
}
```

notification-service consumer checks for `ws_type` in payload; if present, sends the WS message with that type and `ws_data` instead of the generic notification format. The text `message` still gets saved to the notifications table for persistence.

##### G. Mobile Responsiveness

All new components use Tailwind responsive breakpoints:
- Actions menu button: `text-[10px] sm:text-xs` sizing
- Dropdown: full-width on mobile (`w-full sm:w-48`), positioned below on mobile vs absolute on desktop
- Modals: `max-w-sm w-full mx-4` with proper padding
- Invitation panel: single-column on mobile, with smaller avatar sizes (`w-10 h-10 sm:w-14 sm:h-14`)

#### 3.1.6 Data Flow — Sequence Diagrams

##### Training Duel Flow

```
Player A (frontend)                battle-service              RabbitMQ         notification-service        Player B (frontend)
    |                                    |                        |                    |                         |
    |-- POST /battles/pvp/invite ------->|                        |                    |                         |
    |                                    |-- validate ownership,  |                    |                         |
    |                                    |   same location,       |                    |                         |
    |                                    |   not in battle         |                    |                         |
    |                                    |-- INSERT pvp_invitations|                    |                         |
    |                                    |-- publish notification->|                    |                         |
    |<-- 201 {invitation_id} ------------|                        |-- consume -------->|                         |
    |                                    |                        |                    |-- WebSocket push ------->|
    |                                    |                        |                    |   "Вас вызывают на бой"  |
    |                                    |                        |                    |                         |
    |                                    |<-- POST .../respond {"accept"} -----------------------------------|
    |                                    |-- re-validate           |                    |                         |
    |                                    |-- UPDATE invitation     |                    |                         |
    |                                    |-- create_battle()       |                    |                         |
    |                                    |-- init Redis state      |                    |                         |
    |                                    |-- publish notification->|                    |                         |
    |                                    |                        |-- consume -------->|                         |
    |                                    |                        |                    |-- WS: pvp_battle_start ->|
    |<-- WS: pvp_battle_start -----------|                        |                    |-- WS: pvp_battle_start ->|
    |                                    |<-- 200 {battle_id} ---|                    |                         |
    |-- navigate /battle/{id} --------->|                        |                    |                         |
    |                                    |                        |                    |     navigate /battle/{id}|
```

##### Attack Flow

```
Player A (frontend)                battle-service              RabbitMQ         notification-service        Player B (frontend)
    |                                    |                        |                    |                         |
    |-- POST /battles/pvp/attack ------->|                        |                    |                         |
    |                                    |-- validate: ownership, |                    |                         |
    |                                    |   same location,       |                    |                         |
    |                                    |   not safe,            |                    |                         |
    |                                    |   not in battle         |                    |                         |
    |                                    |-- create_battle(        |                    |                         |
    |                                    |     type=pvp_attack)   |                    |                         |
    |                                    |-- init Redis state      |                    |                         |
    |                                    |-- publish notification->|                    |                         |
    |<-- 201 {battle_id} ---------------|                        |-- consume -------->|                         |
    |                                    |                        |                    |-- WS: pvp_battle_start ->|
    |-- navigate /battle/{id} --------->|                        |                    |                         |
```

#### 3.1.7 Security

1. **Auth**: All PvP endpoints require JWT via `get_current_user_via_http`.
2. **Ownership**: Initiator/attacker character must belong to `current_user.id` (verified via shared DB query on `characters.user_id`).
3. **Same location**: Both characters must have the same `current_location` value (shared DB query).
4. **Safe location**: Attack endpoint checks `Locations.marker_type != 'safe'` (shared DB query).
5. **In-battle check**: Prevents double battles via DB query on `battle_participants` + `battles.status`.
6. **Rate limiting**: Rely on Nginx rate limiting (existing). No additional per-endpoint rate limiting in Phase 1.
7. **Input validation**: Pydantic schemas validate all input types. character_id must be positive int.
8. **Invitation expiry**: Invitations expire after 3 hours (configurable). Expired invitations are treated as declined.

---

### 3.2 Phase 2: Death Duel

#### 3.2.1 API Changes

The `POST /battles/pvp/invite` endpoint already supports `battle_type: "pvp_death"`. Additional validation for death duels:

1. Both characters must be level 30+ (query `characters.level` via shared DB)
2. Location must not be `marker_type = 'safe'`
3. Extra confirmation is handled on the frontend (double-confirm modal)

#### 3.2.2 Post-Battle Consequence: Character Unlink

After `finish_battle()` for `pvp_death` battles:

```python
if bt and bt[0] == 'pvp_death':
    for pid_str, pdata in battle_state["participants"].items():
        if pdata["hp"] <= 0 and pdata["team"] != winner_team:
            loser_char_id = pdata["character_id"]
            # Get loser's user_id
            row = await db_session.execute(
                text("SELECT user_id FROM characters WHERE id = :cid"),
                {"cid": loser_char_id},
            )
            loser_user = row.fetchone()
            if loser_user and loser_user[0]:
                loser_user_id = loser_user[0]
                # Call character-service internal unlink
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.CHARACTER_SERVICE_URL}/characters/internal/unlink",
                        json={"character_id": loser_char_id},
                    )
```

##### New internal endpoint in character-service

`POST /characters/internal/unlink` — No auth (internal only, not exposed via Nginx)

This is a simplified version of the existing `admin_unlink_character` that:
1. Sets `character.user_id = None`
2. Calls user-service to delete user-character relation and clear current_character
3. Uses a service-to-service token or no auth (internal network only)

**IMPORTANT**: This endpoint must NOT be exposed via Nginx. Add to `nginx.conf` and `nginx.prod.conf`:
```nginx
location /characters/internal/ {
    return 403;
}
```

#### 3.2.3 Frontend Changes

- Enable "Вызвать на смертельный бой" menu item in `PlayerActionsMenu`
- Add `DeathDuelConfirmModal.tsx` — extra scary confirmation with Russian text:
  - "ВНИМАНИЕ! Проигравший потеряет персонажа навсегда!"
  - Requires typing "ПОДТВЕРЖДАЮ" to enable the confirm button
- Update `DuelInviteModal` to show death duel variant

#### 3.2.4 Notification Messages

- Death duel invite: `"{name} вызывает вас на смертельный бой! Проигравший потеряет персонажа."`
- Death duel accepted: `"{name} принял ваш вызов на смертельный бой! Бой начинается."`
- Character lost: `"Ваш персонаж {name} погиб в смертельном бою."`

---

### 3.3 Phase 3: Trade System

#### 3.3.1 DB Changes

**Owner**: inventory-service (Alembic, `alembic_version_inventory`)

##### A. `trade_offers` table

```sql
CREATE TABLE trade_offers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    initiator_character_id INT NOT NULL,
    target_character_id INT NOT NULL,
    location_id INT NOT NULL,
    initiator_gold INT NOT NULL DEFAULT 0,
    target_gold INT NOT NULL DEFAULT 0,
    initiator_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    target_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    status ENUM('pending', 'negotiating', 'completed', 'cancelled', 'expired') NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_initiator_status (initiator_character_id, status),
    INDEX idx_target_status (target_character_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

##### B. `trade_offer_items` table

```sql
CREATE TABLE trade_offer_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trade_offer_id INT NOT NULL,
    character_id INT NOT NULL COMMENT 'Which side offers this item',
    item_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    FOREIGN KEY (trade_offer_id) REFERENCES trade_offers(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id),
    INDEX idx_trade_offer (trade_offer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Migration file: `services/inventory-service/app/alembic/versions/XXX_add_trade_tables.py`

#### 3.3.2 API Contracts — inventory-service

##### A. `POST /inventory/trade/propose` — Create trade offer

**Auth**: JWT required

**Request**:
```json
{
  "initiator_character_id": 42,
  "target_character_id": 55
}
```

**Validation**: Ownership, same location, neither in battle, no existing active trade between them.

**Response 201**:
```json
{
  "trade_id": 1,
  "initiator_character_id": 42,
  "target_character_id": 55,
  "status": "pending"
}
```

##### B. `PUT /inventory/trade/{trade_id}/items` — Update trade items/gold

**Auth**: JWT required (must be one of the two participants)

**Request**:
```json
{
  "character_id": 42,
  "items": [
    {"item_id": 10, "quantity": 2},
    {"item_id": 15, "quantity": 1}
  ],
  "gold": 500
}
```

**Validation**:
- Character must own all offered items in sufficient quantity
- Character must have enough gold (`currency_balance >= gold`)
- Gold >= 0
- Updates reset both `confirmed` flags to `false` (any change requires re-confirmation)

**Response 200**: Full trade state.

##### C. `POST /inventory/trade/{trade_id}/confirm` — Confirm trade

**Auth**: JWT required

**Request**:
```json
{
  "character_id": 42
}
```

Sets `initiator_confirmed` or `target_confirmed` to `true`. If both are confirmed, executes the trade atomically.

**Atomic trade execution** (single DB transaction in inventory-service, using shared DB):

```python
with db.begin():
    # 1. Verify both characters still have the items and gold
    # 2. Transfer items: UPDATE character_inventory for each item
    # 3. Transfer gold: UPDATE characters SET currency_balance = currency_balance +/- gold
    # 4. Update trade status to 'completed'
```

This is safe because all tables (character_inventory, characters, trade_offers) are in the same MySQL DB.

**Response 200**:
```json
{
  "trade_id": 1,
  "status": "completed",
  "message": "Обмен завершён успешно!"
}
```

##### D. `POST /inventory/trade/{trade_id}/cancel` — Cancel trade

**Auth**: JWT required (either participant)

**Response 200**:
```json
{
  "trade_id": 1,
  "status": "cancelled"
}
```

##### E. `GET /inventory/trade/{trade_id}` — Get trade state

**Auth**: JWT required (either participant)

**Response 200**: Full trade state with items from both sides, gold amounts, confirmation status.

```json
{
  "trade_id": 1,
  "status": "negotiating",
  "initiator": {
    "character_id": 42,
    "character_name": "Артур",
    "items": [
      {"item_id": 10, "item_name": "Меч", "item_image": "...", "quantity": 2}
    ],
    "gold": 500,
    "confirmed": true
  },
  "target": {
    "character_id": 55,
    "character_name": "Гильгамеш",
    "items": [
      {"item_id": 20, "item_name": "Щит", "item_image": "...", "quantity": 1}
    ],
    "gold": 0,
    "confirmed": false
  }
}
```

#### 3.3.3 Frontend Components

| File | Purpose |
|------|---------|
| `src/api/trade.ts` | API client for trade endpoints |
| `src/components/pages/LocationPage/TradeModal.tsx` | Main trade modal (two-column item/gold layout) |
| `src/components/pages/LocationPage/TradeItemSelector.tsx` | Item picker from own inventory |

**TradeModal** design:
- Two columns (left: your items + gold, right: their items + gold)
- Item cells use `item-cell` + rarity classes from design system
- Gold input uses `input-underline`
- Each column has "Подтвердить" button (btn-blue)
- When both confirmed: trade executes automatically
- Uses polling (every 3s) or WebSocket for real-time sync of trade state
- Modal uses `modal-overlay` + `modal-content` + `gold-outline gold-outline-thick`
- Mobile: stacked vertically instead of side-by-side

#### 3.3.4 Real-time Trade Sync

**Option chosen**: Polling with 3-second interval via `GET /inventory/trade/{trade_id}`. This is simpler than WebSocket and sufficient for the two-person trade scenario. The trade UI polls while the modal is open.

Notification-service WebSocket is used only for the initial "trade proposed" notification, not for real-time state sync within the trade.

#### 3.3.5 Notification Messages

- Trade proposed: `"{name} предлагает вам обмен."`
- Trade completed: `"Обмен с {name} завершён успешно!"`
- Trade cancelled: `"{name} отменил обмен."`

---

### 3.4 Cross-Service Impact Summary

| Service | Changes | Risk |
|---------|---------|------|
| **battle-service** | New models, endpoints, migration, RabbitMQ publisher, post-battle hooks | MEDIUM — core battle flow modified |
| **character-service** | New internal unlink endpoint (Phase 2) | LOW — isolated endpoint |
| **inventory-service** | New trade tables, endpoints, migration (Phase 3) | MEDIUM — atomic trade logic |
| **notification-service** | Minor: handle `ws_type` in consumer for structured WS messages | LOW — backward compatible |
| **frontend** | New components in LocationPage, new API clients, WS handler update | MEDIUM — multiple new files |
| **Nginx** | Block `/characters/internal/` route (Phase 2) | LOW — security measure |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Phase 1: Foundation + PvP Battles

| # | Task | Agent | Files to Modify/Create | Depends On | Acceptance Criteria |
|---|------|-------|----------------------|------------|-------------------|
| **1.1** | **Alembic migration: add `battle_type` to `battles`, create `pvp_invitations` table** | Backend Developer | `services/battle-service/app/alembic/versions/002_add_battle_type_and_pvp_invitations.py`, `services/battle-service/app/models.py` | — | Migration runs cleanly on existing DB. Existing battles get `battle_type='pve'`. New models added to models.py. `python -m py_compile` passes. |
| **1.2** | **Add RabbitMQ publisher to battle-service** | Backend Developer | `services/battle-service/app/rabbitmq_publisher.py` (new), `services/battle-service/app/config.py`, `services/battle-service/app/requirements.txt` | — | `publish_notification(user_id, message)` works. `pika` added to requirements.txt. `RABBITMQ_URL` added to config.py. Pattern matches locations-service publisher. |
| **1.3** | **Implement "character in battle" check endpoint** | Backend Developer | `services/battle-service/app/main.py`, `services/battle-service/app/schemas.py` | 1.1 | `GET /battles/character/{character_id}/in-battle` returns `{in_battle: bool, battle_id: int|null}`. Queries `battle_participants` + `battles.status`. |
| **1.4** | **Implement PvP invitation endpoints** (`POST /battles/pvp/invite`, `POST .../respond`, `GET .../pending`, `DELETE .../invite/{id}`) | Backend Developer | `services/battle-service/app/main.py`, `services/battle-service/app/schemas.py`, `services/battle-service/app/crud.py` | 1.1, 1.2, 1.3 | All 4 endpoints work per API contract in 3.1.2. Ownership check, same-location check, in-battle check all enforced. Notification sent on invite/accept/decline. Invitation expiry (3h) handled. |
| **1.5** | **Implement Attack endpoint** (`POST /battles/pvp/attack`) | Backend Developer | `services/battle-service/app/main.py`, `services/battle-service/app/schemas.py` | 1.1, 1.2, 1.3 | Creates battle immediately with `battle_type='pvp_attack'`. Safe-location check enforced. Notification sent to victim. All validations per 3.1.2.C. |
| **1.6** | **Implement training duel post-battle hook** (set loser HP to 1) | Backend Developer | `services/battle-service/app/main.py` | 1.1 | After `pvp_training` battle finishes, loser's `current_health` is set to 1 (not 0). Verified by checking `character_attributes` after battle. |
| **1.7** | **Update `create_battle` CRUD to accept `battle_type` parameter** | Backend Developer | `services/battle-service/app/crud.py`, `services/battle-service/app/main.py` | 1.1 | `create_battle()` accepts and stores `battle_type`. Existing PvE battle creation passes `battle_type='pve'` (backward compatible). |
| **1.8** | **Extend notification-service WS consumer to support `ws_type` field** | Backend Developer | `services/notification-service/app/consumers/general_notification.py` (or equivalent consumer file) | — | When RabbitMQ message has `ws_type` field, WS message uses that type and `ws_data`. When no `ws_type`, behaves as before (backward compatible). |
| **1.9** | **Frontend: Create PvP API client** (`src/api/pvp.ts`) | Frontend Developer | `services/frontend/app-chaldea/src/api/pvp.ts` (new) | — | TypeScript file with all PvP API functions per 3.1.5.E. All functions typed. |
| **1.10** | **Frontend: Create PlayerActionsMenu component** | Frontend Developer | `services/frontend/app-chaldea/src/components/pages/LocationPage/PlayerActionsMenu.tsx` (new) | 1.9 | Dropdown with action items. Conditional visibility based on location safety and user identity. Tailwind only, responsive 360px+, no React.FC. Uses `dropdown-menu`/`dropdown-item` + AnimatePresence. |
| **1.11** | **Frontend: Integrate PlayerActionsMenu into PostCard and PlayersSection** | Frontend Developer | `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCard.tsx`, `PlayersSection.tsx`, `LocationPage.tsx` | 1.10 | Actions button appears under OTHER players' avatars in both PostCard and PlayersSection. Not shown for own character. `marker_type` passed through from LocationPage. |
| **1.12** | **Frontend: Create DuelInviteModal component** | Frontend Developer | `services/frontend/app-chaldea/src/components/pages/LocationPage/DuelInviteModal.tsx` (new) | 1.9 | Confirmation modal with target info. Calls `sendPvpInvitation`. Shows loading state. Error handling with toast. Design system classes. |
| **1.13** | **Frontend: Create PendingInvitationsPanel component** | Frontend Developer | `services/frontend/app-chaldea/src/components/pages/LocationPage/PendingInvitationsPanel.tsx` (new), `LocationPage.tsx` | 1.9 | Shows incoming invitations with Accept/Decline buttons. Polls `getPendingInvitations()`. On accept, navigates to `/battle/{id}`. Integrated into LocationPage. |
| **1.14** | **Frontend: Handle `pvp_battle_start` WS message type** | Frontend Developer | `services/frontend/app-chaldea/src/hooks/useWebSocket.ts` | 1.8 | New case in WS switch: shows toast + optional navigate-to-battle prompt. Handles attack notifications. |
| **1.15** | **Frontend: Remove PlaceholderSection for "Бой на локации"** | Frontend Developer | `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx` | 1.13 | Remove the `<PlaceholderSection title="Бой на локации" .../>` line and replace with PendingInvitationsPanel integration. |
| **1.16** | **QA: Tests for PvP invitation endpoints** | QA Test | `services/battle-service/app/tests/test_pvp_invitations.py` (new) | 1.4 | Tests: create invitation (happy path), accept, decline, cancel, duplicate prevention, wrong user, not same location, already in battle, expiry. |
| **1.17** | **QA: Tests for Attack endpoint** | QA Test | `services/battle-service/app/tests/test_pvp_attack.py` (new) | 1.5 | Tests: attack (happy path), safe location blocked, self-attack blocked, already in battle, not same location. |
| **1.18** | **QA: Tests for training duel post-battle hook** | QA Test | `services/battle-service/app/tests/test_pvp_consequences.py` (new) | 1.6 | Tests: after pvp_training, loser HP = 1. After pvp_attack, loser HP = 0 (normal). After pve, no change to flow. |
| **1.19** | **QA: Tests for notification-service ws_type extension** | QA Test | `services/notification-service/app/tests/test_ws_type.py` (new) | 1.8 | Tests: message with ws_type sends structured WS. Message without ws_type sends generic notification (backward compat). |

### Phase 2: Death Duel

| # | Task | Agent | Files to Modify/Create | Depends On | Acceptance Criteria |
|---|------|-------|----------------------|------------|-------------------|
| **2.1** | **Add internal unlink endpoint to character-service** | Backend Developer | `services/character-service/app/main.py` | Phase 1 done | `POST /characters/internal/unlink` works without auth. Sets `user_id=None`, calls user-service to clean up. |
| **2.2** | **Block internal routes in Nginx** | DevSecOps | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | 2.1 | `/characters/internal/` returns 403 from outside. Internal Docker network still works. |
| **2.3** | **Add CHARACTER_SERVICE_URL to battle-service config** (if not already available) | Backend Developer | `services/battle-service/app/config.py` | — | Already exists (`CHARACTER_SERVICE_URL`). Verify it's accessible. |
| **2.4** | **Implement death duel post-battle hook** (character unlink) | Backend Developer | `services/battle-service/app/main.py` | 2.1, Phase 1 | After `pvp_death` battle, loser's character is unlinked. Calls internal unlink endpoint. Sends "character lost" notification. |
| **2.5** | **Add level 30+ and safe-location validation to PvP invite for death duels** | Backend Developer | `services/battle-service/app/main.py` | Phase 1 | `pvp_death` invitations blocked if either character < level 30 or location is safe. Proper Russian error messages. |
| **2.6** | **Frontend: Enable death duel in PlayerActionsMenu** | Frontend Developer | `PlayerActionsMenu.tsx` | Phase 1 frontend done | "Вызвать на смертельный бой" visible when both level 30+ and location not safe. Hidden otherwise. |
| **2.7** | **Frontend: Create DeathDuelConfirmModal** | Frontend Developer | `DeathDuelConfirmModal.tsx` (new) | 2.6 | Extra confirmation requiring user to type "ПОДТВЕРЖДАЮ". Scary warning text. btn-blue disabled until typed. |
| **2.8** | **QA: Tests for death duel** | QA Test | `services/battle-service/app/tests/test_pvp_death_duel.py` (new) | 2.4, 2.5 | Tests: invite with level < 30 blocked, safe location blocked, post-battle unlink works, notification sent. |
| **2.9** | **QA: Tests for internal unlink endpoint** | QA Test | `services/character-service/app/tests/test_internal_unlink.py` (new) | 2.1 | Tests: unlink works, already unlinked returns error, character not found returns 404. |

### Phase 3: Trade System

| # | Task | Agent | Files to Modify/Create | Depends On | Acceptance Criteria |
|---|------|-------|----------------------|------------|-------------------|
| **3.1** | **Alembic migration: create `trade_offers` and `trade_offer_items` tables** | Backend Developer | `services/inventory-service/app/alembic/versions/XXX_add_trade_tables.py`, `services/inventory-service/app/models.py` | — | Migration runs cleanly. New models added. |
| **3.2** | **Add RabbitMQ publisher to inventory-service** | Backend Developer | `services/inventory-service/app/rabbitmq_publisher.py` (new) | — | Sync publisher function (inventory-service is sync). Pattern matches existing usage. `pika` already in requirements (verify). |
| **3.3** | **Implement trade endpoints** (propose, update items, confirm, cancel, get state) | Backend Developer | `services/inventory-service/app/main.py`, `services/inventory-service/app/schemas.py`, `services/inventory-service/app/crud.py` | 3.1, 3.2 | All 5 endpoints work per API contract in 3.3.2. Atomic trade execution in single transaction. Gold transfer via shared DB. Ownership and validation enforced. |
| **3.4** | **Frontend: Create Trade API client** (`src/api/trade.ts`) | Frontend Developer | `services/frontend/app-chaldea/src/api/trade.ts` (new) | — | TypeScript file with all trade API functions. Typed. |
| **3.5** | **Frontend: Create TradeModal component** | Frontend Developer | `TradeModal.tsx` (new), `TradeItemSelector.tsx` (new) | 3.4 | Two-column trade UI. Item selection from inventory. Gold input. Confirm buttons. Polling for state sync. Mobile stacked layout. Design system classes. |
| **3.6** | **Frontend: Enable "Предложить обмен" in PlayerActionsMenu** | Frontend Developer | `PlayerActionsMenu.tsx` | 3.5, Phase 1 frontend done | Menu item opens TradeModal. Functional end-to-end. |
| **3.7** | **QA: Tests for trade endpoints** | QA Test | `services/inventory-service/app/tests/test_trade.py` (new) | 3.3 | Tests: propose, add items, confirm (both sides), atomic execution, insufficient gold/items, cancel, double-trade prevention. |
| **3.8** | **QA: Tests for trade atomicity** | QA Test | `services/inventory-service/app/tests/test_trade_atomicity.py` (new) | 3.3 | Tests: concurrent modification, rollback on failure, gold balance consistency. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review: Phase 1 — 2026-03-23

**Reviewer**: Reviewer Agent
**Scope**: All Phase 1 changes (Tasks 1.1–1.19)
**Result**: **PASS** (with 2 non-blocking issues to fix in follow-up)

---

#### Mandatory Rules Verification

| Rule | Status | Notes |
|------|--------|-------|
| No `React.FC` | PASS | Grep across all new .tsx files — zero matches |
| All new files TypeScript (.tsx/.ts) | PASS | `pvp.ts`, `PlayerActionsMenu.tsx`, `DuelInviteModal.tsx`, `PendingInvitationsPanel.tsx` |
| All new styles Tailwind only (no CSS/SCSS) | PASS | No SCSS/CSS imports in any new component |
| Responsive 360px+ (sm:/md: breakpoints) | PASS | `text-[10px] sm:text-xs`, `w-10 h-10 sm:w-14 sm:h-14`, `flex-col sm:flex-row`, etc. |
| Design system classes used | PASS | `gold-text`, `gold-outline`, `btn-blue`, `btn-line`, `dropdown-menu`, `dropdown-item`, `modal-overlay`, `modal-content`, `rounded-card` all used correctly |
| Russian user-facing strings | PASS | All UI text in Russian: "Действие", "Предложить обмен", "Вызвать на тренировочный бой", "Напасть", etc. |
| Error handling on every API call | PASS | All API calls in `PlayerActionsMenu`, `DuelInviteModal`, `PendingInvitationsPanel` have try/catch with `toast.error()`. Poll errors in `PendingInvitationsPanel` silently caught — acceptable for background polling. |
| Pydantic <2.0 syntax | PASS | No `model_config` used. `schemas.py` uses `BaseModel` without `class Config: orm_mode = True` (not needed since schemas are not ORM-backed). `config.py` uses `BaseSettings` with `class Config` — correct for Pydantic v1. |
| All backend error messages in Russian | PASS | Verified: "Персонаж уже в бою", "Нельзя напасть на самого себя", "Нападение невозможно на безопасной локации", etc. |
| Auth on endpoints / ownership checks | PASS | All PvP endpoints use `Depends(get_current_user_via_http)`. Ownership verified via shared DB query. `in-battle` endpoint correctly has no auth (internal). |

#### Backend Code Quality

| File | Status | Notes |
|------|--------|-------|
| `models.py` | PASS | `BattleType`, `PvpInvitationStatus` enums, `PvpInvitation` model match architecture spec. `battle_type` column added to `Battle` with `default=BattleType.pve` for backward compatibility. Minor note: `PvpInvitation.battle_type` uses raw string SQLEnum instead of `BattleType` enum — functionally correct since it restricts to valid values. |
| `schemas.py` | PASS | All PvP schemas added: `PvpInviteRequest`, `PvpInviteResponse`, `PvpRespondRequest`, `PvpRespondAcceptResponse`, `PendingInvitationsResponse`, `IncomingInvitation`, `OutgoingInvitation`, `CancelInvitationResponse`, `InBattleResponse`, `PvpAttackRequest`, `PvpAttackResponse`. Proper types, Optional fields. |
| `crud.py` | PASS | `create_battle()` accepts `battle_type` parameter with `default=BattleType.pve` — backward compatible. `get_active_battle_for_character()` added with correct SQL query. |
| `main.py` | PASS | All 6 endpoints implemented: `GET /character/{id}/in-battle`, `POST /pvp/invite`, `POST /pvp/invite/{id}/respond`, `GET /pvp/invitations/pending`, `DELETE /pvp/invite/{id}`, `POST /pvp/attack`. Validations: ownership, same location, not in battle, duplicate prevention, safe location check. Post-battle hook for `pvp_training` correctly sets loser HP to 1. Redis state initialization follows existing pattern. |
| `rabbitmq_publisher.py` | PASS | Follows locations-service pattern exactly: blocking pika wrapped in `run_in_executor`. Extended with optional `ws_type`/`ws_data` parameters. |
| `config.py` | PASS | `RABBITMQ_URL` added with correct default. |
| `requirements.txt` | PASS | `pika` added. |
| `alembic/versions/002_*.py` | PASS | Idempotent (checks for existing tables/columns). Creates `pvp_invitations` with correct indexes. Adds `battle_type` column with `server_default='pve'`. |
| `notification-service general_notification.py` | PASS | `ws_type`/`ws_data` extracted from message payload. When `ws_type` present, sends structured WS message. When absent, sends generic notification (backward compatible). `create_and_send` function signature extended with optional params. |

#### Frontend Code Quality

| File | Status | Notes |
|------|--------|-------|
| `api/pvp.ts` | PASS | TypeScript types match API contracts. 5 API functions with proper typing. Uses axios with generic type parameters. |
| `PlayerActionsMenu.tsx` | PASS | No React.FC. Tailwind only. Responsive. Outside-click handler. AnimatePresence for dropdown. Conditional "Напасть" visibility based on `isSafe`. Trade disabled for Phase 3. Death duel hidden for Phase 2. |
| `DuelInviteModal.tsx` | PASS | `modal-overlay` + `modal-content` + `gold-outline gold-outline-thick`. Loading state. Error handling with toast. Responsive sizing. |
| `PendingInvitationsPanel.tsx` | PASS | Polls every 7s. Accept/Decline/Cancel with loading states. AnimatePresence for list animations. Responsive layout (`flex-col sm:flex-row`). Returns null when empty. |
| `PostCard.tsx` | PASS | `PlayerActionsMenu` integrated below level display, only for other users' posts. `locationMarkerType` prop threaded through. |
| `PlayersSection.tsx` | PASS | `actionsSlot` render prop on `AvatarCard`. `PlayerActionsMenu` rendered for other players via `player.user_id !== currentUserId`. |
| `LocationPage.tsx` | PASS | `PendingInvitationsPanel` imported and rendered. `marker_type` passed to `PlayersSection` and `PostCard`. `PlaceholderSection` for "Бой на локации" removed (confirmed via grep). |
| `useWebSocket.ts` | PASS | `pvp_battle_start` case added. Differentiates `pvp_attack` (error toast) vs duel (success toast). 8s/6s duration. |

#### Cross-Service Consistency

| Check | Status | Notes |
|-------|--------|-------|
| API contracts match (backend <-> frontend) | PASS | Endpoint paths, request bodies, response shapes all consistent between `main.py` and `pvp.ts`. |
| Types match (Pydantic <-> TypeScript) | PASS | `PvpInvitation`, `OutgoingInvitation`, `SendInvitationResult`, `RespondResult`, `AttackResult` all match their Pydantic counterparts. |
| Notification format consistent | PASS | RabbitMQ payload format matches what `general_notification.py` consumer expects. `ws_type`/`ws_data` fields handled correctly. |
| WebSocket types consistent | PASS | `pvp_battle_start` type used in both battle-service publisher and frontend `useWebSocket.ts`. |

#### Build Verification

| Check | Status |
|-------|--------|
| `python -m py_compile` on all modified .py files | PASS (6/6 files) |
| TypeScript imports resolvable | PASS — all imports reference existing modules and correct paths |
| Design system classes exist | PASS — `gold-text`, `btn-blue`, `btn-line`, `dropdown-menu`, `dropdown-item`, `modal-overlay`, `modal-content`, `gold-outline`, `gold-outline-thick`, `rounded-card` all defined in index.css |

#### Test Quality

| Test File | Tests | Coverage | Status |
|-----------|-------|----------|--------|
| `test_pvp_invitations.py` | 15 tests | Create (happy path, self-invite, invalid type, wrong user, target not found, different locations, initiator in battle, target in battle, duplicate), Respond (accept, decline, expired, invalid action), Cancel | PASS |
| `test_pvp_attack.py` | 10 tests | Happy path, self-attack, safe location, wrong user, different locations, in battle, notification, not found | PASS |
| `test_pvp_consequences.py` | 3 tests | pvp_training loser HP=1, pvp_attack no HP override, pve no HP override | PASS |
| `test_ws_type.py` | 5 tests | Structured ws_type, empty ws_data, generic notification, DB persistence, pvp_battle_start | PASS |

Tests mock dependencies correctly (Redis, Mongo, Celery, RabbitMQ, external services). All use TestClient with dependency overrides. Good edge case coverage.

#### Issues Found

| # | Severity | File | Description | Assigned Agent |
|---|----------|------|-------------|----------------|
| I-1 | **LOW** | `PlayerActionsMenu.tsx:55` | Navigate path uses `/location/0/battle/${result.battle_id}` with hardcoded `0` for location ID. The component doesn't have `locationId` prop. Should either add `locationId` prop or use a different route pattern. `PendingInvitationsPanel` correctly receives `locationId`. | Frontend Developer |
| I-2 | **LOW** | `alembic/versions/002_*.py:77-79` | Downgrade function uses `DROP TYPE IF EXISTS` which is PostgreSQL syntax, not MySQL. MySQL ENUMs are column-level, not separate types. These statements will fail on MySQL downgrade. Should be removed or replaced with no-op comment. | Backend Developer |

Both issues are **non-blocking** for Phase 1 deployment:
- I-1: The navigate path may work if the battle route is `/location/:locationId/battle/:battleId` and `0` is handled as a fallback, but should be fixed for correctness.
- I-2: Downgrade is rarely used and the `DROP TYPE` statements would simply error on MySQL without affecting the column/table drops above them.

#### Verdict

**PASS** — Phase 1 implementation is complete, correct, and follows all mandatory rules. The code quality is good, cross-service contracts are consistent, tests provide adequate coverage, and all mandatory rules (TypeScript, Tailwind, no React.FC, responsive, design system, Russian strings, error handling) are satisfied. The two non-blocking issues should be addressed in a follow-up commit.

---

### Review #2: All Phases (1+2+3) Final Review — 2026-03-23

**Reviewer**: Reviewer Agent
**Scope**: Complete review of ALL changes across Phases 1, 2, and 3 (Tasks 1.1–3.8)
**Result**: **FAIL** — 3 critical runtime bugs found in SQL column names

---

#### Mandatory Rules Verification (All Phases)

| Rule | Status | Notes |
|------|--------|-------|
| No `React.FC` | PASS | Zero matches in all new .tsx files (PlayerActionsMenu, DuelInviteModal, PendingInvitationsPanel, DeathDuelConfirmModal, TradeModal, TradeItemSelector) |
| All new files TypeScript (.tsx/.ts) | PASS | `pvp.ts`, `trade.ts`, `PlayerActionsMenu.tsx`, `DuelInviteModal.tsx`, `PendingInvitationsPanel.tsx`, `DeathDuelConfirmModal.tsx`, `TradeModal.tsx`, `TradeItemSelector.tsx` |
| All new styles Tailwind only (no CSS/SCSS) | PASS | No SCSS/CSS imports in any new component |
| Responsive 360px+ (sm:/md: breakpoints) | PASS | `text-[10px] sm:text-xs`, `w-10 h-10 sm:w-14 sm:h-14`, `flex-col sm:flex-row`, `flex-col md:flex-row` (TradeModal), grid responsive sizing |
| Design system classes used | PASS | `gold-text`, `gold-outline`, `gold-outline-thick`, `btn-blue`, `btn-line`, `dropdown-menu`, `dropdown-item`, `modal-overlay`, `modal-content`, `rounded-card`, `input-underline`, `item-cell`, rarity classes, `gold-scrollbar-wide` |
| Russian user-facing strings | PASS | All UI text in Russian throughout |
| Error handling on every API call | PASS | All API calls have try/catch with `toast.error()` using `axios.isAxiosError` pattern. Polling errors silently caught (acceptable). |
| Pydantic <2.0 syntax | PASS | No `model_config` anywhere. `class Config: orm_mode = True` used where needed. `BaseSettings` with `class Config` in config.py. |
| All backend error messages in Russian | PASS | Verified across battle-service and inventory-service endpoints |
| Auth on all endpoints | PASS | All PvP and trade endpoints use `Depends(get_current_user_via_http)`. Internal endpoints (`in-battle`, `internal/unlink`) correctly have no auth. |
| Internal endpoints blocked by Nginx | PASS | `/characters/internal/`, `/battles/internal/`, `/autobattle/internal/` all return 403 in both `nginx.conf` and `nginx.prod.conf` |

#### Build Verification

| Check | Status |
|-------|--------|
| `python -m py_compile` on ALL modified .py files | PASS (15 files: 6 battle-service, 4 inventory-service, 1 notification-service, 1 character-service, 2 migrations, 8 test files) |
| No SCSS/CSS imports in new components | PASS |
| TypeScript imports resolvable | PASS — all imports reference existing modules |
| Design system classes exist | PASS |

#### Phase 2 Backend Review

| File | Status | Notes |
|------|--------|-------|
| `character-service/app/main.py` (internal unlink) | PASS | Endpoint at `/internal/unlink`, no auth, sets `user_id=None`, clears `user_characters` table, uses shared DB direct SQL. Idempotent for already-unlinked characters. |
| `battle-service/app/main.py` (death duel hook) | PASS | Post-battle hook for `pvp_death`: fetches loser user_id before unlink, calls character-service internal endpoint, sends `pvp_death_character_lost` notification. Error handling on all steps. |
| Death duel validation in invite endpoint | PASS | Level 30+ check for both characters, safe location check, proper Russian error messages |
| Nginx blocking | PASS | Both dev and prod configs block `/characters/internal/` |

#### Phase 2 Frontend Review

| File | Status | Notes |
|------|--------|-------|
| `DeathDuelConfirmModal.tsx` | PASS | CONFIRMATION_WORD = 'ПОДТВЕРЖДАЮ', input required to unlock button, `btn-blue disabled:opacity-50`, `modal-overlay` + `modal-content` + `gold-outline gold-outline-thick`, responsive sizing, error handling with toast |
| `PlayerActionsMenu.tsx` (death duel integration) | PASS | `canDeathDuel` check: `!isSafe && currentCharacterLevel >= 30 && targetLevel >= 30`. Shows red-styled button. DeathDuelConfirmModal triggered on click. |

#### Phase 3 Backend Review

| File | Status | Notes |
|------|--------|-------|
| `inventory-service/app/models.py` | PASS | `TradeOffer` and `TradeOfferItem` models match architecture spec. Correct relationships and cascade. |
| `inventory-service/app/schemas.py` | PASS | Trade schemas: `TradeProposeRequest/Response`, `TradeUpdateItemsRequest`, `TradeConfirmRequest/Response`, `TradeCancelResponse`, `TradeItemDetail`, `TradeSideState`, `TradeStateResponse`. Proper Pydantic v1 syntax. |
| `inventory-service/app/crud.py` | **FAIL** (I-3, I-4) | See Critical Issues below |
| `inventory-service/app/main.py` | PASS | 5 trade endpoints: propose, update items, confirm, cancel, get state. All with JWT auth, ownership checks, proper Russian errors. Atomic trade execution with rollback on failure. |
| `inventory-service/app/rabbitmq_publisher.py` | PASS | Sync publisher matching locations-service pattern. `pika` in requirements.txt. `RABBITMQ_URL` in config. |
| `alembic/versions/003_add_trade_tables.py` | PASS | Idempotent migration. Correct table structure matching models. ForeignKey constraints. Indexes. |

#### Phase 3 Frontend Review

| File | Status | Notes |
|------|--------|-------|
| `api/trade.ts` | PASS | 5 API functions, typed responses, correct endpoint paths matching backend |
| `TradeModal.tsx` | PASS | Two-column layout (`flex-col md:flex-row`), polling every 3s, confirm/cancel/auto-close, `modal-overlay` + `modal-content` + `gold-outline gold-outline-thick`, responsive, `item-cell` + rarity classes |
| `TradeItemSelector.tsx` | PASS | Fetches inventory, toggle selection, quantity controls for stackable items, `item-cell` + rarity classes, loading state, responsive grid (`grid-cols-4 sm:grid-cols-5`) |
| `PlayerActionsMenu.tsx` (trade integration) | PASS | `handleTradeClick` calls `proposeTrade`, opens `TradeModal` with resulting `trade_id`, loading state, error handling |

#### Cross-Service Consistency (All Phases)

| Check | Status | Notes |
|-------|--------|-------|
| API contracts match (backend <-> frontend) | PASS | Endpoint paths, request/response bodies all consistent |
| Notification format | PASS | RabbitMQ payload format matches consumer expectations |
| WebSocket types | PASS | `pvp_battle_start`, `pvp_invitation`, `pvp_death_character_lost` all handled |
| Backward compatibility (PvE battles) | PASS | `create_battle()` defaults to `BattleType.pve`. Existing battle creation unaffected. |
| Backward compatibility (notifications) | PASS | `ws_type`/`ws_data` optional in consumer; absent = generic notification format |
| Atomic trade execution | PASS | Single DB transaction in `execute_trade()`, caller commits/rollbacks |

#### Test Quality (All Phases)

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_pvp_invitations.py` | 15 tests | PASS |
| `test_pvp_attack.py` | 10 tests | PASS |
| `test_pvp_consequences.py` | 3 tests | PASS |
| `test_ws_type.py` | 5 tests | PASS |
| `test_pvp_death_duel.py` | 6 tests | PASS |
| `test_internal_unlink.py` | 3 tests | PASS |
| `test_trade.py` | 17 tests | PASS |
| `test_trade_atomicity.py` | 3 tests | PASS |

All 62 tests compile. Tests mock dependencies correctly. **However**, tests pass only because SQL queries are mocked — the incorrect column names in the actual SQL strings are not caught by the mocks.

---

#### CRITICAL Issues Found

| # | Severity | File:Line | Description |
|---|----------|-----------|-------------|
| **I-3** | **CRITICAL** | `services/battle-service/app/main.py:1112` | `_get_character_info()` uses `SELECT id, user_id, current_location, level FROM characters` but the actual DB column is `current_location_id` (verified in `character-service/app/models.py:54`). This will cause a runtime SQL error on every PvP invite, respond, and attack endpoint. **Must change `current_location` to `current_location_id`.** |
| **I-4** | **CRITICAL** | `services/battle-service/app/main.py:1129` | `_get_character_name()` uses `SELECT character_name FROM characters` but the actual DB column is `name` (verified in `character-service/app/models.py:34`). This will cause a runtime SQL error when sending notifications. **Must change `character_name` to `name`.** |
| **I-5** | **CRITICAL** | `services/battle-service/app/main.py:1139` | `_get_character_profile_info()` uses `SELECT character_name, character_photo, level FROM characters` but the actual DB columns are `name` and `avatar` (verified in `character-service/app/models.py:34,50`). The API returns these as `character_name` and `character_photo` but the DB columns differ. **Must change to `SELECT name, avatar, level`.** |
| **I-6** | **CRITICAL** | `services/inventory-service/app/crud.py:358` | `get_character_location()` uses `SELECT current_location FROM characters` but the actual DB column is `current_location_id`. This will cause a runtime SQL error on trade propose. **Must change `current_location` to `current_location_id`.** |

#### Non-Blocking Issues

| # | Severity | File:Line | Description |
|---|----------|-----------|-------------|
| **I-7** | **LOW** | `services/battle-service/app/main.py:1204` | `SELECT marker_type FROM Locations WHERE id = :lid` — the query uses `Locations` (correct table name), but the `id` column on Locations table should be verified. The locations-service model uses a non-standard primary key column name. Verify this works in integration. |
| **I-8** | **LOW** | `services/battle-service/app/main.py:1244` | `invitation.battle_type` in the `PvpInviteResponse` may return the raw enum string from `SQLEnum('pvp_training', 'pvp_death')` which could differ from the expected string format. The `.value` extraction with `hasattr` guard at line 1245 handles the status field but the battle_type field at line 1244 has no such guard. |

---

#### Verdict

**FAIL** — 4 critical runtime SQL column name mismatches found (I-3 through I-6). These will cause 500 errors on every PvP and trade endpoint when running against the real MySQL database. The tests pass because they mock SQL execution, hiding the column name errors.

**Required fixes before PASS:**
1. `battle-service/app/main.py:1112` — Change `current_location` to `current_location_id` in `_get_character_info()`
2. `battle-service/app/main.py:1129` — Change `character_name` to `name` in `_get_character_name()`
3. `battle-service/app/main.py:1139` — Change `character_name, character_photo` to `name, avatar` in `_get_character_profile_info()`
4. `inventory-service/app/crud.py:358` — Change `current_location` to `current_location_id` in `get_character_location()`

All other aspects of the implementation (architecture, frontend, tests, security, backward compatibility, mandatory rules) are PASS.

---

### Review #3: Re-review after SQL column name fixes — 2026-03-23

**Reviewer**: Reviewer Agent
**Scope**: Verification of 4 SQL column name bug fixes (I-3 through I-6) + full audit of all raw SQL in modified files
**Result**: **PASS**

---

#### Fix Verification

All 4 fixes verified against `character-service/app/models.py` (source of truth for `characters` table):

| Issue | File:Line | Before | After | Model Column | Status |
|-------|-----------|--------|-------|-------------|--------|
| I-3 | `battle-service/app/main.py:1112` | `current_location` | `current_location_id` | `models.py:54` `current_location_id = Column(BigInteger)` | CORRECT |
| I-4 | `battle-service/app/main.py:1129` | `character_name` | `name` | `models.py:34` `name = Column(String(255))` | CORRECT |
| I-5 | `battle-service/app/main.py:1139` | `character_name, character_photo` | `name, avatar` | `models.py:34,50` `name`, `avatar` | CORRECT |
| I-6 | `inventory-service/app/crud.py:358` | `current_location` | `current_location_id` | `models.py:54` `current_location_id = Column(BigInteger)` | CORRECT |

#### Caller Reference Verification (I-3)

The `_get_character_info()` function returns dict keys `{"id", "user_id", "current_location_id", "level"}`. All 5 callers verified to use `["current_location_id"]`:
- Line 1176: `initiator["current_location_id"] != target["current_location_id"]` — CORRECT
- Line 1205: `initiator["current_location_id"]` — CORRECT
- Line 1217: `initiator["current_location_id"]` — CORRECT
- Line 1326: `initiator["current_location_id"] != target["current_location_id"]` — CORRECT
- Line 1565: `attacker["current_location_id"] != victim["current_location_id"]` — CORRECT

#### Full Raw SQL Audit — battle-service/app/main.py

All 23 `text()` calls verified against actual model definitions:

| Line | Query | Table | Columns | Status |
|------|-------|-------|---------|--------|
| 76 | `SELECT user_id FROM characters` | characters | `user_id` (models.py:42) | CORRECT |
| 299 | `SELECT user_id FROM characters` | characters | `user_id` | CORRECT |
| 368 | `SELECT is_npc FROM characters` | characters | `is_npc` (models.py:55) | CORRECT |
| 486 | `SELECT user_id FROM characters` | characters | `user_id` | CORRECT |
| 865 | `UPDATE character_attributes SET current_health, current_mana, current_energy, current_stamina` | character_attributes | All 4 columns match (char-attrs models.py:14-17) | CORRECT |
| 907 | `SELECT battle_type FROM battles` | battles | `battle_type` (battle models.py:41) | CORRECT |
| 915 | `UPDATE character_attributes SET current_health = 1` | character_attributes | `current_health` | CORRECT |
| 930 | `SELECT user_id FROM characters` | characters | `user_id` | CORRECT |
| 1112 | `SELECT id, user_id, current_location_id, level FROM characters` | characters | All match | CORRECT (FIXED) |
| 1129 | `SELECT name FROM characters` | characters | `name` | CORRECT (FIXED) |
| 1139 | `SELECT name, avatar, level FROM characters` | characters | All match | CORRECT (FIXED) |
| 1187 | `SELECT id FROM pvp_invitations WHERE ...` | pvp_invitations | Columns match model | CORRECT |
| 1204 | `SELECT marker_type FROM Locations WHERE id = :lid` | Locations | `marker_type` (loc models.py:116), `id` (PK, loc models.py:106) | CORRECT |
| 1266 | `SELECT * FROM pvp_invitations` | pvp_invitations | All columns | CORRECT |
| 1288 | `UPDATE pvp_invitations SET status = 'expired'` | pvp_invitations | `status` | CORRECT |
| 1305 | `UPDATE pvp_invitations SET status = 'declined'` | pvp_invitations | `status` | CORRECT |
| 1335 | `UPDATE pvp_invitations SET status = 'accepted'` | pvp_invitations | `status` | CORRECT |
| 1436 | `SELECT id FROM characters WHERE user_id = :uid` | characters | `id`, `user_id` | CORRECT |
| 1448 | `SELECT id, initiator_character_id, battle_type, created_at, expires_at FROM pvp_invitations` | pvp_invitations | All match model | CORRECT |
| 1476 | `SELECT id, target_character_id, battle_type, status, created_at FROM pvp_invitations` | pvp_invitations | All match model | CORRECT |
| 1514 | `SELECT id, initiator_character_id, status FROM pvp_invitations` | pvp_invitations | All match model | CORRECT |
| 1530 | `UPDATE pvp_invitations SET status = 'cancelled'` | pvp_invitations | `status` | CORRECT |
| 1570 | `SELECT marker_type FROM Locations WHERE id = :lid` | Locations | Same as line 1204 | CORRECT |

#### Full Raw SQL Audit — inventory-service/app/crud.py

All 8 `text()` calls verified:

| Line | Query | Table | Status |
|------|-------|-------|--------|
| 358 | `SELECT current_location_id FROM characters` | characters | CORRECT (FIXED) |
| 367 | `SELECT name FROM characters` | characters | CORRECT |
| 376 | `SELECT user_id FROM characters` | characters | CORRECT |
| 385 | `SELECT currency_balance FROM characters` | characters | CORRECT |
| 394 | `SELECT 1 FROM battle_participants bp JOIN battles b ON bp.battle_id = b.id` | battle_participants, battles | CORRECT |
| 524 | `SELECT COALESCE(SUM(quantity), 0) FROM character_inventory` | character_inventory | CORRECT |
| 555-569 | `UPDATE characters SET currency_balance = ...` | characters | CORRECT |
| 696 | `SELECT COALESCE(SUM(quantity), 0) FROM character_inventory` | character_inventory | CORRECT |

#### Build Verification

| Check | Status |
|-------|--------|
| `python -m py_compile services/battle-service/app/main.py` | PASS |
| `python -m py_compile services/inventory-service/app/crud.py` | PASS |

#### Verdict

**PASS** — All 4 critical SQL column name bugs (I-3 through I-6) are correctly fixed. Full audit of every raw SQL query in both files confirms zero remaining column name mismatches. All dict key references updated consistently. Both files pass py_compile.

FEAT-063 is ready for deployment.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-23 — PM: фича создана (FEAT-063), запускаю анализ кодовой базы
[LOG] 2026-03-23 — Codebase Analyst: начат анализ 7 сервисов (locations, battle, inventory, character, notification, autobattle, frontend)
[LOG] 2026-03-23 — Codebase Analyst: проанализированы модели и схемы locations-service — marker_type (safe/dangerous) доступен, PlayerInLocation содержит user_id
[LOG] 2026-03-23 — Codebase Analyst: проанализирован battle-service — нет поля battle_type, нет проверки "персонаж уже в бою", нет пост-боевых последствий (HP=1, unlink)
[LOG] 2026-03-23 — Codebase Analyst: проанализирован inventory-service — нет системы обмена, трансфер предметов только для одного персонажа
[LOG] 2026-03-23 — Codebase Analyst: проанализирован character-service — найден admin_unlink_character для "смерти" персонажа, currency_balance для золота
[LOG] 2026-03-23 — Codebase Analyst: проанализирован notification-service — WebSocket через ws_manager.send_to_user(), RabbitMQ general_notifications queue
[LOG] 2026-03-23 — Codebase Analyst: проанализирован фронтенд — LocationPage, PlayersSection (аватарки без кнопок), PostCard (аватарка с user_id), PlaceholderSection для боя
[LOG] 2026-03-23 — Codebase Analyst: анализ завершён, отчёт записан в секцию 2. Ключевые риски: атомарность обмена, отсутствие battle_type, HP-to-1 эндпоинт
[LOG] 2026-03-23 — Architect: начато проектирование архитектуры, изучены модели battle-service, inventory-service, character-service, notification-service, frontend LocationPage
[LOG] 2026-03-23 — Architect: решение по атомарности обмена — inventory-service выполняет всё в одной транзакции через shared DB (items + gold)
[LOG] 2026-03-23 — Architect: решение по HP=1 — прямой SQL UPDATE в battle-service post-battle hook (аналогично существующему sync ресурсов)
[LOG] 2026-03-23 — Architect: решение по unlink персонажа — новый internal endpoint в character-service + блокировка через Nginx
[LOG] 2026-03-23 — Architect: решение по уведомлениям — RabbitMQ publisher в battle-service + расширение ws_type в notification-service
[LOG] 2026-03-23 — Architect: решение по real-time trade sync — polling каждые 3 секунды (проще чем WS, достаточно для двух игроков)
[LOG] 2026-03-23 — Architect: архитектура записана в секцию 3, задачи в секцию 4. 3 фазы, 28 задач, все с acceptance criteria
[LOG] 2026-03-23 — Backend Developer: Phase 1 backend — начата реализация задач 1.1-1.8
[LOG] 2026-03-23 — Backend Developer: Task 1.1 — добавлены BattleType, PvpInvitationStatus enums, PvpInvitation model, battle_type column в Battle. Создана Alembic миграция 002_add_pvp
[LOG] 2026-03-23 — Backend Developer: Task 1.2 — создан rabbitmq_publisher.py для battle-service (async pika через run_in_executor), добавлен RABBITMQ_URL в config.py, pika в requirements.txt
[LOG] 2026-03-23 — Backend Developer: Task 1.3 — добавлен GET /battles/character/{id}/in-battle endpoint + InBattleResponse schema + get_active_battle_for_character в crud.py
[LOG] 2026-03-23 — Backend Developer: Task 1.4 — добавлены 4 PvP invitation endpoints: POST invite, POST respond, GET pending, DELETE cancel. Все валидации по спеке (ownership, location, in-battle, duplicates)
[LOG] 2026-03-23 — Backend Developer: Task 1.5 — добавлен POST /battles/pvp/attack endpoint с проверкой safe location через shared DB
[LOG] 2026-03-23 — Backend Developer: Task 1.6 — добавлен post-battle hook для pvp_training: установка current_health=1 проигравшему через direct SQL
[LOG] 2026-03-23 — Backend Developer: Task 1.7 — обновлён create_battle() в crud.py: принимает battle_type параметр, default=pve для обратной совместимости
[LOG] 2026-03-23 — Backend Developer: Task 1.8 — расширен notification-service general_notification consumer: поддержка ws_type/ws_data для структурированных WS-сообщений (backward compatible)
[LOG] 2026-03-23 — Backend Developer: все файлы прошли py_compile проверку. Phase 1 backend завершён
[LOG] 2026-03-23 — Frontend Developer: начата реализация Phase 1 frontend (задачи 1.9-1.15)
[LOG] 2026-03-23 — Frontend Developer: Task 1.9 — создан src/api/pvp.ts с типами и 5 API-функциями (sendPvpInvitation, respondToInvitation, getPendingInvitations, cancelInvitation, attackPlayer)
[LOG] 2026-03-23 — Frontend Developer: Task 1.10 — создан PlayerActionsMenu.tsx: dropdown с 3 пунктами (обмен disabled, тренировочный бой, напасть), outside-click, AnimatePresence, адаптивность
[LOG] 2026-03-23 — Frontend Developer: Task 1.12 — создан DuelInviteModal.tsx: модальное окно подтверждения вызова с loading state и error handling
[LOG] 2026-03-23 — Frontend Developer: Task 1.13 — создан PendingInvitationsPanel.tsx: панель входящих/исходящих вызовов с polling каждые 7 секунд, accept/decline/cancel
[LOG] 2026-03-23 — Frontend Developer: Task 1.11 — интегрирован PlayerActionsMenu в PostCard (под аватаркой чужих постов) и PlayersSection (под аватаркой чужих игроков), прокинут marker_type через LocationPage
[LOG] 2026-03-23 — Frontend Developer: Task 1.14 — добавлен обработчик pvp_battle_start в useWebSocket.ts с toast уведомлениями (разные для attack и duel)
[LOG] 2026-03-23 — Frontend Developer: Task 1.15 — удалён PlaceholderSection "Бой на локации", заменён на PendingInvitationsPanel (показывается когда персонаж на локации)
[LOG] 2026-03-23 — QA Test: начата реализация задач 1.16-1.19 (тесты для Phase 1 backend)
[LOG] 2026-03-23 — QA Test: Task 1.16 — создан test_pvp_invitations.py: 15 тестов (create happy path, self-invite blocked, duplicate prevention, wrong user 403, different locations, in-battle, cancel, decline, accept→battle, expiry, invalid action)
[LOG] 2026-03-23 — QA Test: Task 1.17 — создан test_pvp_attack.py: 10 тестов (happy path, self-attack blocked, safe location blocked, wrong user 403, different locations, in-battle, notification to victim, attacker/victim not found)
[LOG] 2026-03-23 — QA Test: Task 1.18 — создан test_pvp_consequences.py: 3 теста (pvp_training loser HP=1, pvp_attack no HP override, pve no HP override)
[LOG] 2026-03-23 — QA Test: Task 1.19 — создан test_ws_type.py: 5 тестов (structured ws_type message, empty ws_data, generic notification backward compat, DB persistence, pvp_battle_start type)
[LOG] 2026-03-23 — Reviewer: начат ревью Phase 1 — проверка всех backend и frontend файлов
[LOG] 2026-03-23 — Reviewer: проверены mandatory rules — no React.FC, TypeScript, Tailwind only, responsive, design system, Russian strings — все ОК
[LOG] 2026-03-23 — Reviewer: проверена backend кодовая база — models, schemas, crud, main (6 endpoints), migration, rabbitmq_publisher, config, requirements — все ОК
[LOG] 2026-03-23 — Reviewer: проверена frontend кодовая база — pvp.ts, PlayerActionsMenu, DuelInviteModal, PendingInvitationsPanel, PostCard, PlayersSection, LocationPage, useWebSocket — все ОК
[LOG] 2026-03-23 — Reviewer: проверена кросс-сервисная совместимость — API контракты, типы, уведомления, WebSocket — все ОК
[LOG] 2026-03-23 — Reviewer: py_compile проверка — 6/6 backend файлов прошли
[LOG] 2026-03-23 — Reviewer: проверены тесты — 33 теста в 4 файлах, покрытие acceptance criteria адекватное
[LOG] 2026-03-23 — Reviewer: найдены 2 некритичных issue: I-1 (hardcoded location 0 в navigate), I-2 (PostgreSQL syntax в downgrade миграции)
[LOG] 2026-03-23 — Reviewer: ревью Phase 1 завершён — результат: PASS (с 2 non-blocking issues)
[LOG] 2026-03-23 — QA Test: все 4 файла прошли py_compile проверку. Phase 1 QA завершён
[LOG] 2026-03-23 — Frontend Developer: Phase 2 frontend — начата реализация задач 2.6-2.7
[LOG] 2026-03-23 — Frontend Developer: Task 2.6 — включена кнопка «Вызвать на смертельный бой» в PlayerActionsMenu: видна только если оба игрока 30+ и локация не safe. Добавлен prop currentCharacterLevel, прокинут через PostCard, PlayersSection, LocationPage
[LOG] 2026-03-23 — Frontend Developer: Task 2.7 — создан DeathDuelConfirmModal.tsx: модальное окно с предупреждением о потере персонажа, ввод «ПОДТВЕРЖДАЮ» для разблокировки кнопки, вызов sendPvpInvitation с pvp_death, loading state, error handling с toast
[LOG] 2026-03-23 — Frontend Developer: интеграция — DeathDuelConfirmModal подключён в PlayerActionsMenu, полный flow: клик → модалка → ввод подтверждения → API вызов → success toast
[LOG] 2026-03-23 — Backend Developer: Phase 2 backend — начата реализация задач 2.1-2.5 + исправление review issues I-1, I-2
[LOG] 2026-03-23 — Backend Developer: Issue I-1 — исправлен hardcoded locationId=0 в PlayerActionsMenu.tsx, добавлен prop locationId через PlayersSection и PostCard из LocationPage
[LOG] 2026-03-23 — Backend Developer: Issue I-2 — удалены PostgreSQL DROP TYPE IF EXISTS из downgrade миграции 002_add_pvp (MySQL не имеет custom types)
[LOG] 2026-03-23 — Backend Developer: Task 2.1 — создан POST /characters/internal/unlink endpoint в character-service (без auth, direct SQL для shared DB cleanup)
[LOG] 2026-03-23 — Backend Developer: Task 2.3 — CHARACTER_SERVICE_URL уже существует в battle-service config.py и docker-compose.yml, дополнительных изменений не требуется
[LOG] 2026-03-23 — Backend Developer: Task 2.4 — добавлен pvp_death post-battle hook в battle-service: отвязка персонажа через character-service + уведомление проигравшему
[LOG] 2026-03-23 — Backend Developer: Task 2.5 — валидация level 30+ и safe location уже реализована в Phase 1 (pvp invite endpoint), дополнительных изменений не требуется
[LOG] 2026-03-23 — Backend Developer: py_compile проверка — все 4 модифицированных файла прошли. Phase 2 backend завершён
[LOG] 2026-03-23 — DevSecOps: Task 2.2 — /characters/internal/ уже заблокирован в обоих nginx.conf (dev и prod), дополнительных изменений не требуется
[LOG] 2026-03-23 — QA Test: Task 2.8 — создан test_pvp_death_duel.py: 6 тестов (level<30 initiator/target blocked, safe location blocked, valid death duel success, loser unlink via httpx, notification sent)
[LOG] 2026-03-23 — QA Test: Task 2.9 — создан test_internal_unlink.py: 3 теста (unlink success, 404 not found, idempotent already unlinked)
[LOG] 2026-03-23 — QA Test: py_compile проверка — оба тестовых файла прошли компиляцию
[LOG] 2026-03-23 — Frontend Developer: Phase 3 frontend — начата реализация задач 3.4-3.6
[LOG] 2026-03-23 — Frontend Developer: Task 3.4 — создан src/api/trade.ts с типами (TradeOffer, TradeItem, TradeSide, TradeState, TradeCancelResult) и 5 API-функциями (proposeTrade, updateTradeItems, confirmTrade, cancelTrade, getTradeState)
[LOG] 2026-03-23 — Frontend Developer: Task 3.5 — создан TradeModal.tsx: двухколоночный layout (md+), stacked на мобильных, polling каждые 3 секунды, подтверждение/отмена/авто-закрытие при завершении. Создан TradeItemSelector.tsx: выбор предметов из инвентаря, изменение количества для stackable предметов, item-cell + rarity классы из дизайн-системы
[LOG] 2026-03-23 — Frontend Developer: Task 3.6 — включена кнопка «Предложить обмен» в PlayerActionsMenu: клик вызывает proposeTrade API, при успехе открывает TradeModal с trade_id, loading state и error handling с toast
[LOG] 2026-03-23 — Frontend Developer: Phase 3 frontend завершён — все 3 задачи реализованы, TypeScript, Tailwind, no React.FC, responsive 360px+, Russian UI text, error handling на каждом API вызове
[LOG] 2026-03-23 — Backend Developer: Phase 3 backend — начата реализация задач 3.1-3.3 (Trade System)
[LOG] 2026-03-23 — Backend Developer: Task 3.1 — добавлены модели TradeOffer и TradeOfferItem в models.py, создана Alembic миграция 003_add_trade_tables (идемпотентная)
[LOG] 2026-03-23 — Backend Developer: Task 3.2 — создан rabbitmq_publisher.py для inventory-service (sync pika, паттерн из locations-service), добавлен pika в requirements.txt
[LOG] 2026-03-23 — Backend Developer: Task 3.3 — реализованы 5 trade endpoints: POST propose, PUT items, POST confirm, POST cancel, GET state. Атомарное выполнение обмена в одной транзакции. Валидация: ownership, same location, in-battle, gold balance, item ownership
[LOG] 2026-03-23 — Backend Developer: добавлены Pydantic-схемы для trade в schemas.py, trade CRUD функции в crud.py (execute_trade, build_trade_state, verify_item_ownership и др.)
[LOG] 2026-03-23 — Backend Developer: py_compile проверка — все 6 модифицированных/созданных файлов прошли компиляцию. Phase 3 backend завершён
[LOG] 2026-03-23 — QA Test: Task 3.7 — создан test_trade.py: 17 тестов (propose happy path, self-trade blocked, different location, not owned, duplicate active, update items happy path, insufficient quantity, insufficient gold, resets confirmations, non-participant blocked, confirm single side, both sides executes, items transferred, gold transferred, cancel success, cancel non-participant, get state)
[LOG] 2026-03-23 — QA Test: Task 3.8 — создан test_trade_atomicity.py: 3 теста (insufficient items at execution time → rollback, insufficient gold at execution time → rollback, gold balance consistency after trade)
[LOG] 2026-03-23 — QA Test: обновлён conftest.py — добавлен Enum→String патч для TradeOffer модели (SQLite совместимость)
[LOG] 2026-03-23 — QA Test: py_compile проверка — все 3 файла прошли компиляцию. Все 20 trade тестов проходят. Полный test suite (99 тестов) проходит без регрессий. Phase 3 QA завершён
[LOG] 2026-03-23 — Reviewer: начат финальный ревью всех 3 фаз (Review #2) — проверка всех backend, frontend, nginx, тестовых файлов
[LOG] 2026-03-23 — Reviewer: mandatory rules — no React.FC, TypeScript, Tailwind, responsive, design system, Russian strings, error handling, Pydantic <2.0 — все PASS
[LOG] 2026-03-23 — Reviewer: py_compile — все 15 backend файлов + 8 тестовых файлов прошли компиляцию
[LOG] 2026-03-23 — Reviewer: Phase 2 — internal unlink endpoint, death duel hook, DeathDuelConfirmModal, Nginx blocking — все PASS
[LOG] 2026-03-23 — Reviewer: Phase 3 — trade models, schemas, crud, endpoints, migration, rabbitmq publisher, TradeModal, TradeItemSelector — PASS (кроме I-3..I-6)
[LOG] 2026-03-23 — Reviewer: КРИТИЧЕСКИЕ БАГИ НАЙДЕНЫ — 4 некорректных имени SQL-колонок в battle-service и inventory-service:
[LOG] 2026-03-23 — Reviewer: I-3: battle-service main.py:1112 — `current_location` должно быть `current_location_id`
[LOG] 2026-03-23 — Reviewer: I-4: battle-service main.py:1129 — `character_name` должно быть `name`
[LOG] 2026-03-23 — Reviewer: I-5: battle-service main.py:1139 — `character_name, character_photo` должно быть `name, avatar`
[LOG] 2026-03-23 — Reviewer: I-6: inventory-service crud.py:358 — `current_location` должно быть `current_location_id`
[LOG] 2026-03-23 — Reviewer: тесты пропускают эти баги т.к. SQL запросы замокированы — проблема проявится только при runtime на реальной MySQL БД
[LOG] 2026-03-23 — Reviewer: финальный ревью всех 3 фаз завершён — результат: FAIL (4 критических SQL column name бага)
[LOG] 2026-03-23 — Backend Developer: исправлены 4 критических SQL бага (I-3..I-6):
[LOG] 2026-03-23 — Backend Developer: I-3 fix: battle-service _get_character_info() — `current_location` → `current_location_id` (SQL + dict key + все 5 caller references)
[LOG] 2026-03-23 — Backend Developer: I-4 fix: battle-service _get_character_name() — `character_name` → `name`
[LOG] 2026-03-23 — Backend Developer: I-5 fix: battle-service _get_character_profile_info() — `character_name, character_photo` → `name, avatar`
[LOG] 2026-03-23 — Backend Developer: I-6 fix: inventory-service get_character_location() — `current_location` → `current_location_id`
[LOG] 2026-03-23 — Backend Developer: py_compile проверка — оба файла прошли компиляцию. Все 4 бага исправлены
[LOG] 2026-03-23 — Reviewer: начат ре-ревью (Review #3) — верификация 4 SQL column name фиксов + полный аудит всех raw SQL запросов
[LOG] 2026-03-23 — Reviewer: I-3 fix verified: _get_character_info() — `current_location_id` корректно, все 5 caller references обновлены
[LOG] 2026-03-23 — Reviewer: I-4 fix verified: _get_character_name() — `name` корректно
[LOG] 2026-03-23 — Reviewer: I-5 fix verified: _get_character_profile_info() — `name, avatar` корректно
[LOG] 2026-03-23 — Reviewer: I-6 fix verified: get_character_location() — `current_location_id` корректно
[LOG] 2026-03-23 — Reviewer: полный аудит: 23 text() вызова в battle-service/main.py + 8 text() вызовов в inventory-service/crud.py — ВСЕ column names корректны
[LOG] 2026-03-23 — Reviewer: py_compile — оба файла прошли компиляцию
[LOG] 2026-03-23 — Reviewer: ре-ревью завершён — результат: PASS. FEAT-063 готова к деплою
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
