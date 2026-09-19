# FEAT-169: Закрыть оставшиеся открытые эндпоинты и fail-fast по секретам

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-19 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-169-slug.md` → `DONE-FEAT-169-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Продолжение DONE-FEAT-167, которая закрыла выдачу предметов, шесть изменяющих эндпоинтов характеристик, накрутку накопительной статистики и анонимные создающие запросы. Остались ещё три группы открытых мест (все зафиксированы в `docs/ISSUES.md`) плюс долг по секретам.

Прод — живой альфа-тест с игроками. 2026-09-19 на проде уже заменены `INTERNAL_SERVICE_TOKEN` (64 hex) и `JWT_SECRET_KEY` (был публично известный дефолт `your-secret-key`).

### Бизнес-правила

**1. `GET /inventory/characters/{id}/fast_slots` — чтение чужого пояса без авторизации.**
- Сейчас единственная зависимость — `Depends(get_db)`. Кто угодно может прочитать пояс любого персонажа, а после FEAT-168 ответ содержит ещё и эффекты предметов, яды и настройки — это разведка перед боем.
- Сложность: этот же маршрут server-to-server вызывает battle-service (`inventory_client.py`) без токена. Нужно развести игрока и сервис: игроку — JWT + проверка владения, сервису — внутренний маршрут с `verify_internal_token`.
- В тестах уже есть `test_fast_slots_requires_auth` (xfail) — он должен позеленеть.

**2. `POST /characters/{id}/add_rewards` и `POST /party/internal/xp-bonus` — без проверки на уровне сервиса.**
- Первый закрыт только правилом nginx, второй — префиксом `/internal/`. Через них можно начислять опыт и золото.
- Вызывающие: battle-service, battle-pass-service (через `xp_source`), party-service. Все обновить синхронно.

**3. Восемь `/internal/*` маршрутов держатся только на nginx** (`docs/ISSUES.md`): у character-attributes-service — `settle-regen`, `satiety`, `reconcile-perks`; у inventory-service — `revalidate-equipment`, `consume_item`, `free_slots_check`, `gathering/award`, `update-durability`.
- Навесить `verify_internal_token` (механизм уже есть в обоих сервисах) и обновить вызывающих, включая party-service (`settle-regen`).

**4. Долг по секретам (fail-fast).**
- Убрать публичный fallback `JWT_SECRET_KEY: ${JWT_SECRET_KEY:-your-secret-key}` из compose — без секрета сервис должен падать, а не подниматься с известным значением. То же рассмотреть для `INTERNAL_SERVICE_TOKEN` (`dev-internal-token-change-me`) хотя бы в prod-конфигурации.
- Добавить `JWT_SECRET_KEY` в `.env.example` с маскированной заглушкой.
- Dev-окружение не должно сломаться: разработчику нужен понятный способ задать значения (описать в docs и `.env.example`).

**Общее:**
- Ничего из этого нельзя закрывать «только на уровне nginx» — защита в самом сервисе, nginx вторым слоем.
- Все текущие игровые сценарии должны продолжать работать: бой (старт, ход, награды), подземелья, сбор, крафт, экипировка, отдых/сытость, отряды, боевой пропуск, титулы, задания.
- Ответы без авторизации — 401/403, без утечки деталей; тексты по-русски.
- Fail-closed: пустой внутренний токен → 503, чужой/отсутствующий → 401 (как в FEAT-167).

### UX / Пользовательский сценарий
1. Игрок играет как обычно: бой, сбор, крафт, подземелье, отряд — ничего не сломалось.
2. Посторонний не может прочитать чужой пояс, начислить себе опыт или золото, дёрнуть служебные маршруты.

### Edge Cases
- Бои, идущие в момент деплоя (battle-service читает пояс на старте боя и по ходу).
- Автобой и подземелья, которые ходят теми же маршрутами.
- Прод поднимется без `JWT_SECRET_KEY`/`INTERNAL_SERVICE_TOKEN` → по новым правилам упадёт: убедиться, что на проде оба уже заданы (проверено 2026-09-19), и описать это в инструкции деплоя.
- Локальная разработка без `.env`.

### Вопросы к пользователю (если есть)
- [x] Делаем одной задачей все три группы + долг по секретам → **да**
- [x] Fail-fast для `INTERNAL_SERVICE_TOKEN` тоже в prod-конфиге, или только для JWT? → **fallback убираем только из `docker-compose.prod.yml`**; в dev-файле fallback остаётся, чтобы локалка поднималась «из коробки». `JWT_SECRET_KEY` — fallback убираем везде (сервис и так падает сам на импорте; бесполезный `KeyError` заменить на понятный `RuntimeError`).
- [x] Брать ли в эту фичу пять новых открытых изменяющих маршрутов из §2.6 A? → **да, берём все пять**: `POST /skills/assign_multiple`, `POST /skills/`, `POST /locations/quests/progress/update`, `POST /locations/npcs/{id}/dialogue/{node}/choose`, `POST /users/{uid}/activity/increment`. Для каждого решение принимается **по его вызывающим** (internal-токен / JWT+владение / admin-RBAC), а не одним правилом на всех.
- [x] `GET /party/internal/active-members` — закрывать в этом же проходе? → **да**, закрываем вместе с `xp-bonus` (весь префикс `/party/internal/` становится закрытым).
- [x] Группа анонимных **чтений** (чужой инвентарь/экипировка/атрибуты, история чата, `GET /attributes/{id}/perks`) → **вне scope**: нужно продуктовое решение, что должно остаться публичным (часть страниц открыта гостям). Остаётся в `docs/ISSUES.md` как follow-up. Отдельно выносится `GET /attributes/{id}/perks`, который **пишет в БД на чтение** — это баг независимо от продуктового решения.
- [x] `INTERNAL_SERVICE_TOKEN` для autobattle-service → **добавить в оба compose-файла сейчас**, на упреждение (сервис ходит в `/battles/internal/*` без токена и переменной у него нет вовсе).
- [ ] Новое, требует ответа: `POST /locations/quests/progress/update` **не вызывается ниоткуда** (ни один сервис, ни фронтенд, ни тест). Закрываем как internal-маршрут — или удаляем совсем? По умолчанию архитектор выбрал «закрыть, не удалять».

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline: clean tree at `2f08496` (FEAT-164..168 shipped). Everything below is verified by reading the
files at that commit; every claim carries `file:line`.

### 2.0. Reuse, do not reinvent — the FEAT-167 pattern

FEAT-167 solved exactly this class of problem. Its machinery is already in the repo and must be reused:

| Piece | Canonical location | Already present in |
|---|---|---|
| Fail-closed incoming check `verify_internal_token` | `character-service/app/auth_http.py:78-95` | char-attrs `auth_http.py:81`, inventory `auth_http.py:69`, locations `main.py:3750`, skills (different flavour, do **not** copy) |
| Outgoing header helper `_internal_token_headers()` | `character-service/app/crud.py:40` | inventory `main.py:33`, char-attrs `main.py:32`, locations `crud.py:28` + `main.py:3743`, battle `main.py:73`, dungeon `http_clients.py:32`, skills `main.py:37`, party `main.py:53`, battle-pass `crud.py:32` |
| "internal twin route" split | `inventory-service/app/main.py:467` (`POST /inventory/internal/characters/{cid}/items`) + `:481` player/admin variant, sharing `_add_item_to_inventory_core` | — |
| nginx second layer | `limit_except GET HEAD { deny all; }` (`nginx.conf:205,223,238,278`) and `return 403` on `/…/internal/` | both configs |

**Semantics to keep identical:** empty `INTERNAL_SERVICE_TOKEN` → 503; missing/wrong header → 401;
Russian `detail`. Note `verify_internal_token` reads a **module-level** constant captured at import
(`INTERNAL_SERVICE_TOKEN = os.environ.get(...)`), so tests must `monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", …)`,
not only `setenv` — the FEAT-162/167 test precedent.

Every service that already has a helper reads `os.environ` **at call time**, so adding `headers=` to a
call site is a one-line change with no import-order hazard.

---

### 2.1. Affected services

| Service | Change | Files |
|---|---|---|
| inventory-service | split `fast_slots` into player+internal; gate 5 `/internal/*` routes | `app/main.py:1252` (+ new internal twin), `:753, :1644, :1721, :1750, :3721` |
| character-attributes-service | gate 3 `/internal/*` routes | `app/main.py:438, :455, :1419` |
| character-service | gate `POST /characters/{cid}/add_rewards` | `app/main.py:3498` |
| party-service | gate `POST /party/internal/xp-bonus` (+ `GET /party/internal/active-members`, see §2.6); add `verify_internal_token` (service has none) | `app/auth_http.py` (new dep), `app/main.py:129, :176`, `app/crud.py:22` (outgoing) |
| battle-service | send the header on 5 calls | `app/inventory_client.py:23, :83, :118`, `app/main.py:425, :442` |
| battle-pass-service | send the header on `add_rewards` | `app/crud.py:538` |
| dungeon-service | send the header on `add_rewards` | `app/http_clients.py:404` |
| locations-service | send the header on 3 calls | `app/crud.py:286` (xp-bonus), `:6381` (gathering/award), `:7374` (free_slots_check) |
| skills-service | send the header on `revalidate-equipment` | `app/main.py:734` |
| frontend | `fast_slots` stays on the player route (already sends JWT) — no change expected; confirm the 401 path shows a Russian message | `src/redux/slices/profileSlice.ts:485` |
| DevSecOps / compose | drop the `JWT_SECRET_KEY` fallback; decide on the `INTERNAL_SERVICE_TOKEN` fallback; local `.env` | `docker-compose.yml:248`, all `INTERNAL_SERVICE_TOKEN` lines, `docker-compose.prod.yml`, `.env.example` |
| nginx (2nd layer, optional) | `add_rewards` rule already exists; `fast_slots` cannot be method-gated (it is a GET) | `docker/api-gateway/nginx.conf:137`, `nginx.prod.conf:158` |

**No DB change, no Alembic revision, no new RBAC permission** is required by any item in §1.

---

### 2.2. Group 1 — `GET /inventory/characters/{cid}/fast_slots`

**Handler:** `services/inventory-service/app/main.py:1252-1256` — `get_fast_slots(character_id, db=Depends(get_db))`.
Single dependency is the DB session. (ISSUES.md cites `main.py:1186-1193` — stale line numbers after FEAT-168;
the route is now at `:1252`.)

**Every caller in the repo — there are exactly two:**

| # | Caller | file:line | Sends today | Audience |
|---|---|---|---|---|
| 1 | battle-service `inventory_client.get_fast_slots` | `battle-service/app/inventory_client.py:118` | nothing (bare `httpx.AsyncClient().get`) | service |
| 2 | frontend `fetchFastSlots` thunk | `frontend/app-chaldea/src/redux/slices/profileSlice.ts:485` | player JWT via the axios interceptor | player |

Caller #1 is reached from exactly one place: `battle-service/app/main.py:317` (`slots = await get_fast_slots(char_id)`),
inside battle start — the belt is **snapshotted into Redis battle state** at start, not re-read per turn.
So a 401 here does not break an in-flight battle, it breaks the *start* of a new one.

Caller #2 is dispatched from 6 sites in `profileSlice.ts` (`:531, :558, :586, :612, :748, :826`) — all
composite "reload my profile" thunks that already take `characterId` of the **own** character.
No admin screen reads fast slots (the admin battle page reads `fast_slots` off the battle state blob,
`Admin/BattlesPage/AdminBattlesPage.tsx:60`, not from inventory-service).

**What a split touches:**
- new `GET /inventory/internal/characters/{cid}/fast_slots` with `Depends(verify_internal_token)` (already
  imported at `inventory-service/app/main.py:21`), sharing the existing body via a `_get_fast_slots_core` extraction —
  the exact shape FEAT-167 used for `items` (`main.py:467` vs `:481`);
- the player route keeps its path and gains `Depends(get_current_user_via_http)` + ownership.
  **Ownership helper check needed:** `verify_character_ownership` is used at `inventory-service/app/main.py` for
  `DELETE /{cid}/items/{iid}` — the Architect should reuse that same helper, not write a new one;
- battle-service `inventory_client.py:118` repoints to the internal path and gains
  `headers={"X-Internal-Token": …}`. battle-service already has the helper at `main.py:73`, but
  `inventory_client.py` has **no** helper of its own (it reads only `config.settings`) — it needs one
  (three call sites in that file: `:23`, `:83`, `:118`);
- `nginx` needs the new `/inventory/internal/…` path to keep returning 403 — it already does, the
  prefix rule `nginx.conf:290` / `nginx.prod.conf:306` covers it with no edit.

**Existing xfail test:** `services/inventory-service/app/tests/test_fast_slots_payload.py:248-261`
(`TestFastSlotsAuth::test_fast_slots_requires_auth`, `xfail(strict=False)`) asserts `401/403` for an
anonymous read of character 2's belt. Removing the marker is part of the task. The rest of that file
(`test_effect_rows_reach_the_fast_slot_payload` etc.) calls the route anonymously and must be moved to
the internal route or given a token.

**Other test files hitting `fast_slots` in-process:** inventory `test_equip_locking.py`,
`test_npc_equipment.py`, `test_item_out_schemas_serve_stored_rows.py`. battle-service and
autobattle-service files mention `fast_slots` only as a *state key*, not as an HTTP path — they mock
`inventory_client`, so they are unaffected except any that assert the URL.

---

### 2.3. Group 2 — `add_rewards` and `xp-bonus`

**`POST /characters/{cid}/add_rewards`** — `character-service/app/main.py:3498-3503`, docstring literally
says *"Internal endpoint (no auth)"*. Only protection is the nginx regex
`location ~ ^/characters/\d+/add_rewards$ { return 403; }` (`nginx.conf:137`, `nginx.prod.conf:158`) — one layer.

| Caller | file:line | Sends today |
|---|---|---|
| battle-service, PvE victory | `battle-service/app/main.py:425` | nothing |
| battle-pass-service `_deliver_gold_xp` | `battle-pass-service/app/crud.py:538` | nothing (helper exists at `crud.py:32`, unused here) |
| dungeon-service `add_gold` | `dungeon-service/app/http_clients.py:404` | nothing (helper exists at `http_clients.py:32`, unused here) |

**No frontend caller** (full `.ts`/`.tsx` sweep). No admin UI grants XP/gold through this route — the
admin paths are `POST /attributes/admin/{cid}/grant_active_xp` and the character admin editor, both RBAC-gated.

**`POST /party/internal/xp-bonus`** — `party-service/app/main.py:129-130`, `Depends(get_db)` only.
Protection: `location /party/internal/ { return 403; }` (`nginx.conf:488`, `nginx.prod.conf:503`).

| Caller | file:line | Sends today |
|---|---|---|
| battle-service, combat XP | `battle-service/app/main.py:442` | nothing |
| **locations-service, post XP** | `locations-service/app/crud.py:286` | nothing — **the §1 brief does not list this caller; it is the third one and must be updated too** |

battle-pass-service does **not** call `xp-bonus` (it reaches party XP indirectly, via `add_rewards`).

**party-service has no `verify_internal_token`** — `party-service/app/auth_http.py` exports only
`get_current_user_via_http` (`:24`) and `get_admin_user` (`:43`). The fail-closed helper must be added
there (copy of `character-service/app/auth_http.py:78-95`). party-service *does* already have the
outgoing helper (`main.py:53`) and the env var (`docker-compose.yml:617`, `docker-compose.prod.yml:271`).

**Tests to update:** `character-service/app/tests/` — `test_add_rewards.py` (~10 anonymous posts),
`test_gold_transactions.py` (5), `test_xp_books.py` (~15), `test_xp_paths_real_session.py` (8),
`test_xp_multiplier_call_shape.py`; `party-service/app/tests/test_party.py:194`;
caller-side header assertions: `battle-pass-service/app/tests/test_xp_source.py:49`,
`battle-service/app/tests/test_pve_rewards.py:216-235`, `locations-service/app/tests/test_post_xp.py:253`.
All mechanical (add `headers=`), no assertion semantics change — the FEAT-162/167 precedent.

---

### 2.4. Group 3 — the eight `/internal/*` routes

All eight confirmed: handler has **no** auth dependency, only `Depends(get_db)`.

| # | Route | Handler | Caller(s) | Caller has outgoing helper? | Sends today |
|---|---|---|---|---|---|
| 1 | `POST /attributes/internal/settle-regen` | `char-attrs/main.py:438` | party-service `crud.py:22` | party has one in `main.py:53`, **but `crud.py` does not import it** | nothing |
| 2 | `POST /attributes/internal/{cid}/satiety` | `char-attrs/main.py:455` | inventory `main.py:3443` (eat-food) | yes, `inventory/main.py:33` | nothing |
| 3 | `POST /attributes/internal/{cid}/reconcile-perks` | `char-attrs/main.py:1419` | inventory `main.py:844-870` (`_reconcile_perks` sync **and** `_reconcile_perks_async`); character-service `main.py:1963` | inventory yes; char-svc yes (`crud.py:40`) | nothing on any of the 3 sites |
| 4 | `POST /inventory/internal/characters/{cid}/revalidate-equipment` | `inventory/main.py:753` | skills-service `main.py:734` | yes, `skills/main.py:37` | nothing |
| 5 | `POST /inventory/internal/characters/{cid}/consume_item` | `inventory/main.py:1644` | battle-service `inventory_client.py:23` | **no helper in that module** | nothing |
| 6 | `POST /inventory/internal/characters/{cid}/free_slots_check` | `inventory/main.py:1721` | locations `crud.py:7374` | yes, `locations/crud.py:28` | nothing |
| 7 | `POST /inventory/internal/characters/{cid}/gathering/award` | `inventory/main.py:1750` | locations `crud.py:6381` | yes | nothing |
| 8 | `POST /inventory/internal/update-durability` | `inventory/main.py:3721` | battle-service `inventory_client.py:83` | **no helper in that module** | nothing |

**None of the eight is called from the frontend** (verified by sweeping `.ts`/`.tsx` for each path).
So all eight can become internal-only with no UI work — unlike FEAT-167's item-grant, no split is needed here.

**Two more `/internal/*` routes in inventory-service that ISSUES.md does not list because they are newer
(FEAT-168) — and they are already protected:** `GET /inventory/internal/characters/{cid}/xp-multiplier`
(`main.py:1773`, `verify_internal_token` at `:1781`) and `…/xp-multipliers` (`:1807`, dep at `:1815`).
Good news: the list is genuinely eight, not ten.

**Two behaviours to preserve:**
- #3 `reconcile-perks` is also invoked **in-process** at `char-attrs/main.py:345` (on `GET /{cid}/perks`)
  and `:686` (after upgrade) and from `regen.py:341` — those are direct function calls, unaffected.
- #1 `settle-regen` is called from party-service with a 2s timeout and is **best-effort**
  (`crud.py:31-34` logs a WARNING and continues). A missing header would therefore degrade silently —
  exactly the project's silent-failure pattern. Same for #7 `gathering/award` (`locations/crud.py:6396`),
  #6 `free_slots_check` (fails *closed* — returns `False` → the player is told the bag is full),
  #3 reconcile-perks (warning only), #4 revalidate-equipment (error log only), #8 update-durability
  (best-effort). **Only #2 satiety and #5 consume_item surface an error to the player.**
  → QA must assert the header on the real client function of each of the eight, not on a re-implementation.

**Tests touching these routes:** char-attrs `test_satiety.py`, `test_regen.py`; party `test_settle_before_read.py`;
inventory `test_food_satiety.py`, `test_consume_item.py`, `test_gathering.py`, `test_equipment_rules.py`;
locations `test_gathering.py`, `test_gathering_ingredient.py`; skills `test_player_tree_endpoints.py`;
battle `test_item_usage.py`, `test_item_effects.py`. No test file currently exercises `update-durability`
or `reconcile-perks` over HTTP — a coverage gap worth closing while here.

---

### 2.5. Secrets fail-fast

**`JWT_SECRET_KEY`**
- Declared only for user-service: `docker-compose.yml:248` — `JWT_SECRET_KEY: ${JWT_SECRET_KEY:-your-secret-key}`.
  **Not declared at all in `docker-compose.prod.yml`** (user-service is not overridden there, so prod inherits
  this exact line, fallback included).
- Read at `services/user-service/auth.py:13` — `SECRET_KEY = os.environ["JWT_SECRET_KEY"]`, i.e.
  **import time, `KeyError` if absent**. `main.py:17` re-exports it. No other service reads it
  (notification-service validates through user-service `GET /users/me`).
- **So the service-side is already fail-fast**; removing the compose fallback is sufficient and the
  container will crash-loop on a bare `KeyError` traceback. Worth replacing with an explicit
  `raise RuntimeError("JWT_SECRET_KEY is not set")` so the log says what is wrong.
- **`.env.example` already contains `JWT_SECRET_KEY=change-me-jwt-secret-at-least-32-chars`** (line 21).
  §1 item 4 bullet 2 and the corresponding ISSUES.md step are therefore **already done** — the remaining
  work is only the compose fallback. (I have marked that step stale in ISSUES.md.)

**`INTERNAL_SERVICE_TOKEN`**
- `${INTERNAL_SERVICE_TOKEN:-dev-internal-token-change-me}` for 10 services in `docker-compose.yml`
  (`:135 celery-worker, :311 char-attrs, :338 skills, :366 inventory, :398 character, :429 locations,
  :493 battle, :554 battle-pass, :586 dungeon, :617 party`) and for 7 in `docker-compose.prod.yml`
  (`:127 skills, :147 character, :183 battle-pass, :222 battle, :255 dungeon, :271 party, :285 celery-worker`).
  The other three (char-attrs, inventory, locations) are not overridden in prod and inherit the base map.
- **Never declared for: user-service, photo-service, notification-service, autobattle-service.**
  autobattle matters — see §2.6.
- Read **at import time** into a module constant in the *incoming* checks
  (`character-service/auth_http.py:78`, `char-attrs:78`, `inventory:66`, `locations/main.py:3734`,
  `skills/auth_http.py:58`) and **at call time** in every *outgoing* helper
  (`os.environ.get(...)` or `settings.INTERNAL_SERVICE_TOKEN`).
- **Today with the var missing:** incoming checks fail closed → every gated internal call gets 503;
  ungated ones still work. Outgoing helpers send an empty header.
- `.env.example:28` already has a stub.
- **Local dev would break if the fallbacks are removed:** the repo's local `.env` contains
  **neither** `JWT_SECRET_KEY` nor `INTERNAL_SERVICE_TOKEN` (verified — it has only MySQL/PMA/S3 keys).
  Removing the fallbacks without also adding both keys to the developer's `.env` means user-service
  crash-loops and every internal call 503s. Whatever the Architect decides, the task must include
  a documented dev step (README/`docs/` + `.env.example` note) and the user must add both to the local `.env`.
- **No test depends on either fallback:** a repo-wide grep for the literals `your-secret-key` and
  `dev-internal-token-change-me` hits only the two compose files. Tests monkeypatch
  `auth_http.INTERNAL_SERVICE_TOKEN` / set env explicitly, and CI runs pytest directly (not through compose),
  so CI is unaffected by removing either fallback.
- **CI check:** `.github/workflows/ci.yml` runs pytest per service without compose, so no CI job reads these
  variables; the deploy job runs `docker compose up --build -d` on the VPS, where both are set in prod `.env`
  (confirmed by the user 2026-09-19). Risk is the *local* developer, not CI.

---

### 2.6. Anything else still open (systematic sweep, NOT in scope — report only)

Method: parsed every `@router.<verb>` in all 13 services and flagged handlers whose signature/decorator
contains none of `get_current_user_via_http` / `get_admin_user` / `require_permission` / `verify_internal_token`,
then cross-checked against both nginx configs.

**A. Publicly routable and mutating — new findings, worth their own feature:**

| Severity | Route | Handler | Why it matters |
|---|---|---|---|
| HIGH | `POST /skills/assign_multiple` | `skills-service/app/main.py:567` | `character_id` comes from the body; grants any skill id to any character. nginx proxies `/skills/` wholesale (`nginx.conf:264`). |
| HIGH | `POST /skills/` (legacy) | `skills-service/app/main.py:75` | creates/attaches "Basic Attack" for an arbitrary `character_id` from the body. |
| MEDIUM | `POST /locations/quests/progress/update` | `locations-service/app/main.py:3133` | advances any character's quest objective by an arbitrary increment; quest completion pays rewards. |
| MEDIUM | `POST /locations/npcs/{npc_id}/dialogue/{node_id}/choose` | `locations-service/app/main.py:2488` | dialogue choice for a body-supplied character; dialogue nodes can hand out quests. |
| MEDIUM | `POST /users/{user_id}/activity/increment` | `user-service/main.py:1656` | docstring says "internal, no auth required"; **not** under `/users/internal/`, so nginx does not block it — anyone can inflate anyone's activity points. Exactly the shape of the FEAT-167 `cumulative_stats/increment` hole. |

**B. Unauthenticated reads (reconnaissance / privacy, same class as `fast_slots`):**
`GET /inventory/{cid}/items` (`inventory/main.py:361`), `GET /inventory/{cid}/equipment` (`:766`),
`GET /attributes/{cid}` (`char-attrs/main.py:357`), `GET /attributes/{cid}/perks` (`:332`, and it
*writes* — it runs `reconcile_perks` as a self-heal at `:339-345`), `GET /characters/{cid}/full_profile`
(`character-service/main.py:1911`), `GET /users/all` (`user-service/main.py:702`),
`GET /notifications/chat/messages` (`notification-service/app/chat_routes.py:153` — reads any chat
channel's history with no token, while `DELETE` on the same router is `require_permission("chat:delete")`).
Severity LOW–MEDIUM each; they belong in one follow-up sweep, not in FEAT-169.

**C. `/internal/*` still relying on nginx only, outside §1's eight:**
`GET /party/internal/active-members` (`party-service/app/main.py:176`; callers: battle `main.py:988, :1168, :3709`,
dungeon `http_clients.py:63`, locations `crud.py:7119`) — since party-service gets `verify_internal_token`
anyway for `xp-bonus`, adding it here is nearly free and closes the whole prefix;
`GET/POST /battles/internal/{id}/state|action` (`battle/main.py:1373, :1428`),
`POST /battles/internal/party/leave-on-move` (`:6363`),
`POST /battle-pass/internal/track-event` (`battle-pass/main.py:295`),
`GET /dungeons/internal/character-session/{cid}` + `POST /dungeons/internal/battle-callback`
(`dungeon/main.py:730, :746`),
`GET|POST /locations/internal/gathering-status|action-gate|action-gate/consume` (`locations/main.py:3677, :3688, :3701`),
`GET|POST /locations/quests/internal/check-completed|completed-count|auto-progress` (`:3153, :3175, :3198`),
`GET|POST /users/internal/{uid}/diamonds|diamonds/add|diamonds/spend|cosmetics/unlock`
(`user-service/main.py:1687, :1699, :1720, :2144` — **currency mutation**, the weightiest of this set).

**D. Blocker for any future gating of `/battles/internal/*`:** autobattle-service calls
`battle-service` internal routes with no header (`autobattle-service/app/clients.py:15, :23`) and has
**no `INTERNAL_SERVICE_TOKEN` in either compose file**. If FEAT-169 (or a follow-up) touches those routes,
autobattle needs the env var + a helper first, or auto-battle dies silently.

**E. RBAC routes — genuinely protected (checked, per §1's question).** In char-attrs every
`/attributes/admin/*` handler carries `require_permission(...)`: perks CRUD `main.py:120, 140, 158, 212, 254, 309`,
`PUT /admin/{cid}` `:1132` (`characters:update`), `POST /admin/{cid}/grant_active_xp` `:1214`,
`POST /admin/recalculate_all` `:1285`, plus `POST /{cid}/recalculate` `:1195` and `DELETE /{cid}` `:1259`.
Route-ordering was checked for shadowing: `/admin/perks*` is declared above `/{character_id}` (`:332/:357`),
and `/admin/recalculate_all` cannot be captured by `/{character_id}/recalculate` (different literal).
**No admin route is reachable unauthenticated.** Same result for inventory's item-catalog admin routes
and notification's chat moderation. The RBAC layer is not part of this problem.

---

### 2.7. DB / migrations

**None.** No schema change, no Alembic revision, no backfill, no new `permissions` row (and therefore no
`test_rbac_permissions.py::TestAdminAutoPermissions` seed needed, CLAUDE.md §10.13). No Redis or Mongo
state encodes any of this.

---

### 2.8. Risks

| Risk | Detail | Mitigation |
|---|---|---|
| **In-flight battles at deploy** | `fast_slots` is read **once**, at battle start (`battle/main.py:317`), and snapshotted into Redis (TTL 48h). `consume_item` (`main.py:2740`) and `update-durability` are called **mid-battle and post-battle**. If battle-service is restarted before inventory-service, or ships without the header, a running battle loses item usage and durability writes — both are best-effort/warn-only paths. | Ship inventory-service gating and battle-service headers in the **same** image build; deploy order does not matter if both change together, because compose recreates all. Reviewer should start a battle, use a belt item, and finish it live. |
| **Silent degradation instead of failure** | 6 of the 8 internal routes' callers swallow errors with a WARNING (§2.4). A forgotten header = party XP, gathering awards, perk reconcile, durability and equipment revalidation quietly stop. This repeats the project's known silent-failure pattern (4 prior occurrences). | QA asserts `X-Internal-Token` on the **real** client function for each of the 11 call sites; Reviewer verifies live: gather a node, eat food, level up, change subclass, finish a battle, party XP tick. |
| **Third `xp-bonus` caller missed** | §1 names battle/battle-pass/party; the actual third caller is **locations-service `crud.py:286`** (post XP). Missing it kills the party bonus for forum posts. | Listed in §2.3; must be in the task list. |
| **`inventory_client.py` has no token helper** | battle-service's helper lives in `main.py:73`; `inventory_client.py` imports only `config`. Three call sites there (`:23, :83, :118`). | Add a local helper in `inventory_client.py` (do not import from `main` — circular). |
| **party-service has no `verify_internal_token`** | Only `get_current_user_via_http` / `get_admin_user` exist. | Copy `character-service/app/auth_http.py:78-95` verbatim. |
| **party-service `crud.py` cannot reach the helper in `main.py`** | `settle_regen` lives in `crud.py:19`; the helper is in `main.py:53` — importing `main` from `crud` is circular. | Move/duplicate the helper into `crud.py` or a small `internal_auth.py`. |
| **Dev environment breaks on fallback removal** | Local `.env` has neither secret (§2.5). | Same commit must update `.env.example` guidance and `docs/`; the user must add both keys to their local `.env` before the next `docker compose up`. Ask before removing the `INTERNAL_SERVICE_TOKEN` fallback from the **dev** file. |
| **Prod deploy with fail-fast** | Both secrets confirmed present in prod `.env` on 2026-09-19. But the CI deploy does `down` before a parallel build on a 3.8 GB box (known issue) — a crash-loop on a missing secret compounds that. | Verify with `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` that `JWT_SECRET_KEY` resolves non-empty on the VPS **before** pushing. |
| **Autobattle / dungeon paths** | Autobattle drives battle-service's internal routes with no token (§2.6 D) — not touched by §1's list, so **no regression from this feature**; dungeon-service calls `add_rewards`, `consume_stamina`, `recover` and already has a helper. | Keep `/battles/internal/*` out of scope this round; note the prerequisite for later. |
| **Test fixtures needing the header** | ~20 test files across 8 services (§2.2–2.4), all mechanical. | Follow the FEAT-162 precedent: pin the module constant + add `headers=`, change no assertion. |
| **`fast_slots` player route and NPC/mob belts** | `inventory/tests/test_npc_equipment.py` reads fast slots for NPC characters, which have no owning user. | The internal twin covers it; ownership check must not be applied to the internal route. |

---

### 2.9. Questions needing a non-technical (user) decision

1. **Dev fallback for `INTERNAL_SERVICE_TOKEN`:** remove it from `docker-compose.prod.yml` only (dev keeps
   working out of the box) or from both files (stricter, but every developer must put the key in `.env`
   before the next `up`)? §1 leaves this open.
2. **`JWT_SECRET_KEY` in dev:** removing the fallback means user-service will not start until the key is in
   the local `.env`. Confirm that is acceptable, and that you will add both keys locally in the same session.
3. **Scope creep, your call:** the sweep found five *new* unauthenticated mutating routes (§2.6 A) —
   `POST /skills/assign_multiple`, `POST /skills/`, `POST /locations/quests/progress/update`,
   `POST /locations/npcs/{id}/dialogue/{node}/choose`, `POST /users/{uid}/activity/increment`.
   The first two let anyone grant skills to any character, which is at least as bad as the belt leak.
   Fold them into FEAT-169, or open FEAT-170? (They are recorded in `docs/ISSUES.md` either way.)
4. **`GET /party/internal/active-members`** is the only route left on the `/party/internal/` prefix after
   `xp-bonus`. Close it in the same pass (nearly free) or leave it for the general internal sweep?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0. Guiding rule — one question per route, not one answer for all

Every route in scope is classified by **who actually calls it** (§2 caller tables, extended by two
targeted sweeps during design). Three gate shapes exist in the codebase; we reuse them unchanged:

| Gate | Dependency | Semantics | When it applies |
|---|---|---|---|
| **I — internal** | `Depends(verify_internal_token)` | empty `INTERNAL_SERVICE_TOKEN` → **503**; missing/wrong header → **401**; Russian `detail` | every caller is another container |
| **P — player** | `Depends(get_current_user_via_http)` + `verify_character_ownership(...)` | 401 no/bad JWT; 404 unknown character; 403 someone else's character | the caller is the browser, acting on its own character |
| **A — admin** | `Depends(require_permission("<module>:<action>"))` | 401 no JWT; 403 missing permission | the caller is an admin screen acting on a character it does not own (NPCs) |

Where a route genuinely has **both** a service caller and a browser caller, we do **not** weaken the
gate to the weakest common denominator — we split the route into an **internal twin** (gate I, under
the service's `/internal/` prefix) and a **player/admin route** (gate P or A) sharing one `_core`
function. This is the FEAT-167 `POST /inventory/internal/characters/{cid}/items` vs `:481` pattern
(`inventory-service/app/main.py:467`/`:481`), and it is the only new API surface this feature adds.

**No new schemas, no request/response shape changes, no DB change, no Alembic revision, no new
`permissions` row** (so no `test_rbac_permissions.py::TestAdminAutoPermissions` seed — CLAUDE.md §10.13).
Every new route returns exactly what its existing sibling returns. Pydantic v1 syntax throughout;
each service keeps its own sync/async flavour.

---

### 3.1. The decision table — every route, its gate, and why

#### Group 1 — `fast_slots` (split)

| Route | Gate | Rationale |
|---|---|---|
| `GET /inventory/internal/characters/{cid}/fast_slots` **(new)** | **I** | battle-service reads the belt once at battle start (`battle/main.py:317`) and snapshots it into Redis; NPC/mob characters have no owning user, so gate P is impossible here |
| `GET /inventory/characters/{cid}/fast_slots` (existing path) | **P** | the only browser caller is `profileSlice.fetchFastSlots` (`profileSlice.ts:485`), dispatched from 6 "reload my own profile" thunks; no admin screen reads it |

#### Group 2 — reward grants

| Route | Gate | Rationale |
|---|---|---|
| `POST /characters/{cid}/add_rewards` | **I** | three callers, all containers (battle, battle-pass, dungeon); zero frontend callers; admin XP/gold grants go through separate RBAC routes |
| `POST /party/internal/xp-bonus` | **I** | three callers, all containers (battle, locations, party itself) |
| `GET /party/internal/active-members` | **I** | callers: battle `main.py:988, :1168, :3709`, dungeon `http_clients.py:63`, locations `crud.py:7119`. Closing it makes the whole `/party/internal/` prefix gated |

#### Group 3 — the eight nginx-only internal routes → all gate **I**, no split

`POST /attributes/internal/settle-regen`, `POST /attributes/internal/{cid}/satiety`,
`POST /attributes/internal/{cid}/reconcile-perks`,
`POST /inventory/internal/characters/{cid}/revalidate-equipment`,
`…/consume_item`, `…/free_slots_check`, `…/gathering/award`, `POST /inventory/internal/update-durability`.
None is called from the frontend (§2.4), so no twin is needed. The in-process calls to
`reconcile_perks` (`char-attrs/main.py:345`, `:686`, `regen.py:341`) are direct Python calls and are
untouched by an HTTP dependency.

#### Group 4 — the five newly found mutating holes (PM: in scope; decided per caller)

| Route | Gate | Caller evidence → why this gate |
|---|---|---|
| `POST /skills/internal/assign_multiple` **(new twin)** | **I** | character-service `crud.py:1547` (`send_skills_presets_request`, character approval step 6, `main.py:493`) |
| `POST /skills/assign_multiple` (existing path) | **A** — `require_permission("skills:create")` | the browser caller is the **admin** NPC editor `AdminNpcsPage/NpcStatsEditor.tsx:249`, which assigns skills to an **NPC** — a character the admin does not own, so gate P would break it. `skills:create` is the permission already used by the sibling `POST /skills/admin/character_skills/` (`skills/main.py:312`), so **no new permission row** |
| `POST /skills/` (legacy "Basic Attack") | **I** | only caller is character-service `crud.py:1156` (`send_skills_request`), which has **no production call site** — tests only. No frontend caller. Gate I is the zero-risk choice; see the open question in §1 about deleting it instead |
| `POST /locations/quests/internal/progress/update` **(moved)** | **I** | **zero callers anywhere** — no service, no frontend, no test. Moving it under the already-403'd `/locations/quests/internal/` prefix costs nothing and needs no caller update. The live sibling that services really use is `POST /quests/internal/auto-progress` (`locations/main.py:3198`) |
| `POST /locations/npcs/{npc_id}/dialogue/{node_id}/choose` | **P (JWT only)** | the only caller is the **player** screen `NpcDialogueModal.tsx:74`, which already sends the JWT via the global axios interceptor. **Ownership is deliberately not added**: the request body (`DialogueChooseRequest = {option_id}`) carries no `character_id` at all, and the handler is pure dialogue-tree navigation — it grants nothing (quests are granted by the separate `POST /locations/quests/{id}/accept`, `NpcDialogueModal.tsx:101`). Adding `character_id` to force an ownership check would be a breaking contract change plus a frontend change, for no additional protection. Authentication alone removes the anonymous-access hole |
| `POST /users/internal/{uid}/activity/increment` **(moved)** | **I** | only caller is notification-service `chat_routes.py:138` (fire-and-forget after a chat message). Moving it under `/users/internal/` puts it behind the existing nginx `return 403` (`nginx.conf:118`) **and** the new token check |

**Note on the `activity/increment` move:** `points` is currently unvalidated (negatives accepted).
Add `points: int = Field(1, ge=1, le=100)` (Pydantic v1) while the route is being touched — cheap
input validation on a now-internal mutation.

---

### 3.2. New / changed API contracts

Only four routes are new or move. Everything else gains a dependency and keeps its contract byte-for-byte.

#### `GET /inventory/internal/characters/{character_id}/fast_slots` — NEW
- **Auth:** `Depends(verify_internal_token)` (gate I). **No ownership check** — mobs/NPCs have `user_id IS NULL`.
- **Response:** identical to the existing player route — `List[schemas.FastSlot]` (FEAT-168 payload: recovery fields, `consumable_action`, `coating_*`, `effects`, `damage_entries`).
- **Implementation:** extract the current body of `get_fast_slots` (`inventory/main.py:1252`) into
  `_get_fast_slots_core(db, character_id) -> List[schemas.FastSlot]`; both routes call it. Shape copied
  from `_add_item_to_inventory_core` (FEAT-167).
- **Errors:** 503 token unset · 401 missing/wrong header.

#### `GET /inventory/characters/{character_id}/fast_slots` — CHANGED (gate P)
- **Auth:** `current_user = Depends(get_current_user_via_http)`, then
  `verify_character_ownership(db, character_id, current_user.id)` (`inventory/main.py:68` — reuse, do not rewrite).
- **Response:** unchanged. **Errors:** 401 · 404 «Персонаж не найден» · 403 «Вы можете управлять только своими персонажами».

#### `POST /skills/internal/assign_multiple` — NEW
- **Auth:** gate I. **Request:** `schemas.MultipleSkillsAssignRequest` (unchanged). **Response:** `{"assigned": [...]}` (unchanged).
- **Implementation:** extract `_assign_multiple_core(db, data)`; the public `/skills/assign_multiple` keeps
  the same body behind `require_permission("skills:create")`.

#### `POST /locations/quests/internal/progress/update` — MOVED (was `POST /locations/quests/progress/update`)
- **Auth:** gate I. Request/response unchanged. The old path is **removed**, not aliased — it has no callers.

#### `POST /users/internal/{user_id}/activity/increment` — MOVED (was `POST /users/{user_id}/activity/increment`)
- **Auth:** gate I (user-service gets `verify_internal_token` for the first time).
- **Request:** `{"points": int}` — now `Field(1, ge=1, le=100)`. **Response:** `{"activity_points": int}` (unchanged).
- The old path is **removed**. FastAPI route-order note: `/users/internal/{uid}/activity/increment` (4 segments)
  cannot be shadowed by `/users/{user_id}/activity/increment` (3 segments) — no ordering hazard, and the
  existing `/users/internal/{uid}/diamonds*` routes prove the prefix resolves.

---

### 3.3. Missing machinery — what must be built before the gates can be hung

The analyst found four holes. All four are "add a small module / helper", none is a redesign.

| # | Gap | Decision |
|---|---|---|
| M1 | **party-service has no `verify_internal_token`** (`party/auth_http.py` exports only `get_current_user_via_http`, `get_admin_user`; it does not even import `Header`) | Create **`services/party-service/app/internal_auth.py`** holding **both** directions: `INTERNAL_SERVICE_TOKEN` module constant + `verify_internal_token(...)` (verbatim copy of `character-service/app/auth_http.py:78-95`) **and** `internal_token_headers()` (env read at call time). Putting both in a new leaf module — imported by `main.py` *and* `crud.py` — is what breaks the circular import in M2. `main.py:47`'s existing `_internal_token_headers` is re-pointed at it so there is one source of truth in the service |
| M2 | **`party/crud.py` cannot reach the helper in `party/main.py:47`** (importing `main` from `crud` is circular); `settle_regen` (`crud.py:19-34`) posts to `internal/settle-regen` with no headers | `crud.py` imports `internal_auth` (leaf module, imports only `os`/`fastapi`) — no cycle |
| M3 | **`battle-service/app/inventory_client.py` has no token helper** (imports only `httpx` and `config`); battle-service's helper lives in `main.py:65` and importing `main` from it is circular | Add a module-local `_internal_token_headers()` to `inventory_client.py` reading `os.environ.get("INTERNAL_SERVICE_TOKEN", "")` at call time. **Do not import from `main`.** Apply it to the two `/internal/` calls (`consume_item` `:23`, `update_durability` `:83`) and to the re-pointed `get_fast_slots` (`:118`). `get_item` (`:11`) and `get_equipment_durability` (`:45`) hit public GETs and stay as they are |
| M4 | **user-service has no internal-token machinery at all** (no `INTERNAL_SERVICE_TOKEN`, no `X-Internal-Token` anywhere in the service) | Add `verify_internal_token` to **`services/user-service/auth.py`** (the service has no `auth_http.py`; it is the auth service itself), same fail-closed body. This also makes the later `/users/internal/*diamonds*` sweep nearly free — but those routes stay **out of scope** here |
| M5 | **skills-service has `INTERNAL_SERVICE_TOKEN` but no `verify_internal_token`** — only `allow_jwt_or_service_token` (`skills/auth_http.py:61`), which compares the token as a **Bearer**, a different mechanism | Add the standard `verify_internal_token` to `skills/auth_http.py`. **Do not reuse or extend `allow_jwt_or_service_token`** — mixing the two would make one secret valid in two header positions |
| M6 | **notification-service has no `INTERNAL_SERVICE_TOKEN`** and calls user-service with no header | Add the env var (§3.6) and a module-local `internal_token_headers()` in `chat_routes.py` |

---

### 3.4. Caller update matrix — every call site that must start sending `X-Internal-Token`

This is the table the review hangs on. 19 call sites across 10 services.

| # | Caller service | File:line | Target route | Change | Error handling today |
|---|---|---|---|---|---|
| 1 | battle-service | `inventory_client.py:23` | `…/consume_item` | header | returns `{"status":"error"}` → **surfaced to player** |
| 2 | battle-service | `inventory_client.py:83` | `…/update-durability` | header | `raise_for_status`, caller swallows → **silent** |
| 3 | battle-service | `inventory_client.py:118` | `fast_slots` | **re-point to `/inventory/internal/…`** + header | `raise_for_status` → battle start fails loudly |
| 4 | battle-service | `main.py:425` | `add_rewards` | header | best-effort |
| 5 | battle-service | `main.py:442` | `party/internal/xp-bonus` | header | best-effort → **silent** |
| 6 | battle-pass-service | `crud.py:538` | `add_rewards` | header (helper exists `crud.py:25`, unused here) | warning → **silent** |
| 7 | dungeon-service | `http_clients.py:404` | `add_rewards` | header (helper exists `http_clients.py:26`) | warning → **silent** |
| 8 | locations-service | `crud.py:286` | `party/internal/xp-bonus` | header | warning → **silent** (post XP; the caller §1 forgot) |
| 9 | locations-service | `crud.py:6381` | `…/gathering/award` | header | warning → **silent** (lost gathering rewards) |
| 10 | locations-service | `crud.py:7374` | `…/free_slots_check` | header | fails **closed** → player told "bag is full" |
| 11 | skills-service | `main.py:734` | `…/revalidate-equipment` | header (helper `main.py:31`) | error log → **silent** |
| 12 | inventory-service | `main.py:3443` | `…/{cid}/satiety` | header (helper `main.py:28`) | surfaced to player |
| 13 | inventory-service | `main.py:844` | `…/reconcile-perks` (sync) | header | warning → **silent** |
| 14 | inventory-service | `main.py:~870` | `…/reconcile-perks` (async) | header | warning → **silent** |
| 15 | character-service | `main.py:1963` | `…/reconcile-perks` | header (helper `crud.py:31`) | warning → **silent** |
| 16 | character-service | `crud.py:1547` | `skills/assign_multiple` | **re-point to `/skills/internal/assign_multiple`** + header | logs + returns `None` → **silent** (character created with no skills!) |
| 17 | character-service | `crud.py:1156` | `POST /skills/` | header (dead helper — keep it correct) | logs → silent |
| 18 | party-service | `crud.py:26` | `…/settle-regen` | header via new `internal_auth` | warning → **silent** |
| 19 | notification-service | `chat_routes.py:138` | activity increment | **re-point to `/users/internal/…`** + header | bare `except: pass` → **fully silent** |

**Silent-failure risk (CLAUDE.md §10 / ISSUES "тихие отказы", 4 prior occurrences).** 12 of these 19
swallow the error. A forgotten header would not raise anything: party XP, forum-post XP, gathering
rewards, perk reconciliation, durability writes, equipment revalidation and chat activity points would
just quietly stop, and **a test that only asserts "nothing raised" would still pass**.
→ **QA must assert the header on the real client function** (patch the transport, inspect
`call.kwargs["headers"]["X-Internal-Token"]`), never on a re-implementation of the call. This is a
FAIL condition for the Reviewer, not a nice-to-have.

---

### 3.5. Security considerations

- **Authentication.** Per-route, per §3.1. No route keeps `Depends(get_db)` as its only dependency after this feature.
- **Fail-closed everywhere.** Empty `INTERNAL_SERVICE_TOKEN` → 503, never "allow". Identical to FEAT-162/167;
  do not invent a "dev bypass".
- **Authorization.** Ownership via each service's existing `verify_character_ownership`
  (`inventory/main.py:68`, `locations/main.py:119`, `skills/main.py:53`) — reuse, do not write a new one.
  Admin access via the existing `skills:create` permission — no new permission, no RBAC migration.
- **Input validation.** Only one addition: `points: int = Field(1, ge=1, le=100)` on the activity route.
  Everything else keeps its current schema.
- **Error messages.** Russian, no internals leaked. Reuse the exact strings already in the repo:
  «Internal service token не настроен» (503), «Недействительный internal token» (401),
  «Персонаж не найден» (404), «Вы можете управлять только своими персонажами» (403), «Недостаточно прав» (403).
- **Rate limiting.** Not added. All gated routes become either container-only or authenticated; the
  existing nginx `limit_req` zones stay as they are.
- **Defence in depth.** nginx is the **second** layer, never the only one (§3.7).
- **Token in logs.** `X-Internal-Token` must never be logged; no call site currently logs headers — keep it that way.

---

### 3.6. Secrets — fail-fast, and the dev/prod split

#### `JWT_SECRET_KEY`
- `services/user-service/auth.py:13` is `os.environ["JWT_SECRET_KEY"]` — already fail-fast, but it dies
  with a bare `KeyError` traceback, and **an empty-string value would sail straight through**
  (the key is present, just blank). Replace with an explicit, truthiness-checking guard that raises
  `RuntimeError("JWT_SECRET_KEY is not set — user-service refuses to start with an unset or empty JWT secret")`.
- Remove the fallback in `docker-compose.yml:248`: `JWT_SECRET_KEY: ${JWT_SECRET_KEY}`.
  `docker-compose.prod.yml` declares no `JWT_SECRET_KEY` at all and its user-service block (`:97-101`)
  overrides only `command`/`volumes`/`ports`, so prod inherits this same line — one edit covers both.
- Deliberately **not** using Compose's `${JWT_SECRET_KEY:?err}` form here: that makes `docker compose config`,
  `ps` and `down` fail for the whole stack, which is worse ergonomics than one container crash-looping
  with a one-line, unambiguous reason in `docker logs user-service`.
- `.env.example:20` already has the stub — that ISSUES step is done.

#### `INTERNAL_SERVICE_TOKEN` (PM decision: prod only)
- **`docker-compose.yml` (dev): keep `${INTERNAL_SERVICE_TOKEN:-dev-internal-token-change-me}`** on every
  consumer, so a fresh clone still comes up.
- **`docker-compose.prod.yml`: declare `INTERNAL_SERVICE_TOKEN: ${INTERNAL_SERVICE_TOKEN:?INTERNAL_SERVICE_TOKEN is required in production}`
  for *every* consumer.** Here the "whole stack refuses to start" behaviour is exactly what we want,
  and the prod deploy is scripted.
- **⚠️ The trap DevSecOps must not fall into.** Four consumers (character-attributes-service,
  inventory-service, locations-service, user-service) get the var **only from the base file** today.
  Overriding the other services in prod alone would leave those four running prod with the public
  `dev-internal-token-change-me`. So the prod file must carry the `:?` line for **all** consumers.
- **Compose merge semantics are load-bearing here and must be verified, not assumed.** The prod file
  already uses the `!reset []` extension for `volumes`/`ports`, which exists precisely because mappings
  and sequences **merge** by default — so adding one key to a prod `environment:` block should merge,
  not replace. **Do not take that on trust.** Acceptance is empirical:
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` must show (a) every service
  keeping its full pre-existing environment, and (b) **zero** occurrences of the literal
  `dev-internal-token-change-me` in the merged prod config. If merging turns out to replace, the whole
  base `environment:` map must be restated in that prod block.

#### New consumers of `INTERNAL_SERVICE_TOKEN` (three services that have never had it)
| Service | Why it needs it now | Files |
|---|---|---|
| **user-service** | now *receives* a gated internal route (`activity/increment`) — without the var its own check 503s | both compose files |
| **notification-service** | now *sends* the header to user-service | both compose files |
| **autobattle-service** | future-proofing (PM decision): it drives `/battles/internal/{id}/state\|action` (`clients.py:15,:23`) with no token and has no var anywhere. Add the var **and** the header helper now, while those routes are still ungated, so the eventual `/battles/internal/*` sweep cannot kill auto-battle silently | both compose files + `app/clients.py` |

Sending a header to a route that does not check it yet is harmless — this is the cheapest possible
way to retire the ISSUES blocker entry.

#### `.env.example`
Already has both keys. Two fixes while we are there: the `INTERNAL_SERVICE_TOKEN` comment block
(lines 22-27) is stale — it still says "used by battle-service/celery-worker when calling skills-service
`GET /skills/{id}/resolved`" (FEAT-125), whereas 13 services now consume it; and `JWT_SECRET_KEY` needs
a note that user-service will refuse to start without it. Generation hint for both: `openssl rand -hex 32`.

#### Dev-environment note (must be in the PR description and in `docs/`)
Removing the `JWT_SECRET_KEY` fallback means **the local `.env` must gain `JWT_SECRET_KEY` before the
next `docker compose up`**, or user-service crash-loops. The local `.env` currently has neither secret
(§2.5). PM has said they will add real values locally. `INTERNAL_SERVICE_TOKEN` stays optional in dev
thanks to the retained fallback. CI is unaffected — it runs pytest directly, never through compose.

---

### 3.7. nginx — the second layer

nginx is never the only protection, but every newly-gated path should also be unreachable from outside.

| Config change | Both `nginx.conf` and `nginx.prod.conf` |
|---|---|
| **`location /skills/internal/ { return 403; }`** — NEW | `/skills/` is the **only** service family with no internal deny rule (verified in both configs). Must be declared **above** `location /skills/` |
| **`location = /skills/ { limit_except GET HEAD { deny all; } }`** — NEW | blocks the legacy `POST /skills/` from outside, exact-match so no `/skills/...` sub-path is affected. Copy of the `location = /inventory/` rule (`nginx.conf:278`, `nginx.prod.conf:294`) |
| `/inventory/internal/`, `/users/internal/`, `/locations/quests/internal/`, `/party/internal/`, `/attributes/internal/`, `~ ^/characters/\d+/add_rewards$` | **already present** — the new `fast_slots` twin, the moved quest-progress route and the moved activity route land under prefixes that are already 403'd. **No edit needed**, but the Reviewer must confirm each new path resolves to 403 through the gateway |
| `GET /inventory/characters/{cid}/fast_slots` | **cannot** be method-gated (it is a GET the browser legitimately makes) — the service-side JWT + ownership check is the whole protection. This is exactly why gate P, not "nginx only", is required |

---

### 3.8. Data flow after the change

```
PLAYER belt read
  browser ──JWT──> nginx /inventory/ ──> inventory-service
                                          get_current_user_via_http → user-service /users/me
                                          verify_character_ownership(db, cid, user.id)
                                          _get_fast_slots_core → MySQL

BATTLE start
  battle-service inventory_client.get_fast_slots
     ──X-Internal-Token──> inventory-service GET /inventory/internal/characters/{cid}/fast_slots
                             verify_internal_token → _get_fast_slots_core → MySQL
     → snapshot into Redis battle state (TTL 48h)

BATTLE mid/post
  battle-service ──X-Internal-Token──> /inventory/internal/.../consume_item
                 ──X-Internal-Token──> /inventory/internal/update-durability
                 ──X-Internal-Token──> /characters/{cid}/add_rewards
                 ──X-Internal-Token──> /party/internal/xp-bonus

CHARACTER approval
  character-service ──X-Internal-Token──> skills POST /skills/internal/assign_multiple

ADMIN NPC editor
  browser ──JWT(admin)──> nginx /skills/ ──> POST /skills/assign_multiple
                                             require_permission("skills:create")

CHAT message
  browser ──JWT──> notification-service /notifications/chat/messages
                     └─X-Internal-Token──> user-service POST /users/internal/{uid}/activity/increment
```

---

### 3.9. Deploy ordering and rollback

- **battle-service and inventory-service must ship in the same image build.** `consume_item` and
  `update-durability` are called **mid-battle and post-battle**. If inventory-service came up gated
  while battle-service still ran the old image, every in-flight battle would silently lose item usage
  and durability writes (both best-effort paths, §3.4 #1/#2). The same argument applies pairwise to
  character-service↔skills-service and notification-service↔user-service, where the **path itself**
  changes — an old caller would get a hard 404.
- Mitigation: this is **one commit, one `docker compose up --build -d`**, which recreates everything.
  The CI deploy already does `down` first (a full-stack window, not a partial one), so there is no
  mixed-version period — at the cost of the known "CI deploy кладёт прод" issue.
- **Prod pre-flight, before pushing to `main`:** on the VPS run
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -E "JWT_SECRET_KEY|INTERNAL_SERVICE_TOKEN"`
  and confirm both resolve to real values and that `dev-internal-token-change-me` and `your-secret-key`
  appear **nowhere**. Both secrets were confirmed present in prod `.env` on 2026-09-19.
- **Rollback:** pure code + compose revert (`git revert`, rebuild). No schema change, no data migration,
  nothing to undo in MySQL/Redis/Mongo. Redis battle snapshots taken before the deploy remain valid —
  the belt is already in the state blob.

---

### 3.10. Explicitly out of scope (recorded in `docs/ISSUES.md`, not fixed here)

1. **The anonymous-READ group** — `GET /inventory/{cid}/items`, `/inventory/{cid}/equipment`,
   `GET /attributes/{cid}`, `GET /attributes/{cid}/perks`, `GET /characters/{cid}/full_profile`,
   `GET /users/all`, `GET /notifications/chat/messages`. PM decision: needs a **product** call on what
   stays public (some pages are open to guests). The existing ISSUES entry stays and must be kept accurate.
2. **`GET /attributes/{cid}/perks` writes on read** (`char-attrs/main.py:332`, self-heal `reconcile_perks`
   at `:339-345`). PM decision: **flag this separately** — it is a bug whatever the product decision is.
   An anonymous GET triggers a DB write *and* a full perk evaluation, which per ISSUES ("оценка перков
   тянет весь `/full_profile`") transitively calls character-service and inventory-service. That makes an
   unauthenticated endpoint an amplification vector, independent of whether perks should be public.
   → must become its **own** ISSUES entry, not a clause inside the reads entry.
3. **`/battles/internal/*`, `/dungeons/internal/*`, `/battle-pass/internal/track-event`,
   `/locations/internal/*`, `/locations/quests/internal/*`, `/users/internal/*diamonds*|cosmetics`** —
   the remaining nginx-only internal routes. After this feature the `/users/internal/` and
   `/party/internal/` prefixes have the machinery in place, so the follow-up sweep gets cheaper.
   Note `POST /quests/internal/auto-progress` (`locations/main.py:3198`, called by battle and inventory)
   is in this group.
4. **Deleting the two dead routes** (`POST /skills/`'s dead helper, the zero-caller quest-progress route)
   — gated, not deleted; see the open question in §1.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Waves: **A** (infra, no code deps) ‖ **B** (nine backend services, fully parallel — the new paths are
frozen by §3.2, so no service waits on another) → **C** (QA, five parallel groups) → **D** (frontend
verification, bookkeeping) → **E** (review).

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Secrets fail-fast + env wiring.** Drop the `JWT_SECRET_KEY` fallback (`${JWT_SECRET_KEY}`); replace `os.environ["JWT_SECRET_KEY"]` with a guard raising `RuntimeError` on missing **or empty**. In `docker-compose.prod.yml` set `INTERNAL_SERVICE_TOKEN: ${INTERNAL_SERVICE_TOKEN:?…}` for **every** consumer incl. the four that only inherit it from the base file; keep the dev fallback in `docker-compose.yml`. Add `INTERNAL_SERVICE_TOKEN` to **user-service, notification-service, autobattle-service** in **both** files. Refresh the stale `.env.example` comment block and add a "user-service will not start without it" note to `JWT_SECRET_KEY`. Document the local-`.env` step in `docs/`. | DevSecOps | DONE (`services/user-service/auth.py` — Backend Dev task #9; `docs/ARCHITECTURE.md` deploy note written on the review-fix pass) | `docker-compose.yml`, `docker-compose.prod.yml`, `.env.example`, `docs/ARCHITECTURE.md` | — | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` succeeds with the vars set, every service keeps its **full** prior environment, and the merged prod config contains **zero** occurrences of `dev-internal-token-change-me` / `your-secret-key`; with `JWT_SECRET_KEY` unset user-service logs the RuntimeError message and exits |
| 2 | **nginx second layer.** Add `location /skills/internal/ { return 403; }` (above `location /skills/`) and `location = /skills/ { limit_except GET HEAD { deny all; } }` to **both** configs. Verify the already-existing deny rules cover the three moved/new paths. | DevSecOps | DONE | `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | — | `nginx -t` passes on both; `/skills/internal/…` → 403, `POST /skills/` → 403, `GET /skills/...` sub-paths unaffected |
| 3 | **inventory-service.** Extract `_get_fast_slots_core`; add the internal twin `GET /inventory/internal/characters/{cid}/fast_slots` (gate I); put gate P (`get_current_user_via_http` + existing `verify_character_ownership`, `main.py:68`) on the player route. Add `Depends(verify_internal_token)` to the 5 internal routes (`:753, :1644, :1721, :1750, :3721`). Send `X-Internal-Token` on the 3 outgoing calls (`:3443` satiety, `:844`/`~:870` reconcile-perks) using the existing helper `main.py:28`. | Backend Developer | DONE | `services/inventory-service/app/main.py` | — | `python -m py_compile` OK; anonymous GET of the player route → 401; internal twin without header → 401, with empty token → 503 |
| 4 | **character-attributes-service.** `Depends(verify_internal_token)` on `settle-regen` (`:438`), `{cid}/satiety` (`:455`), `{cid}/reconcile-perks` (`:1419`). Do **not** touch the in-process `reconcile_perks` calls at `:345`, `:686`, `regen.py:341`. | Backend Developer | DONE | `services/character-attributes-service/app/main.py` | — | py_compile OK; all three return 401 without header, 503 on empty token; rest/satiety/perk flows unchanged in-process |
| 5 | **character-service.** Gate `POST /characters/{cid}/add_rewards` (`:3498`) with `verify_internal_token`; drop the misleading "no auth" docstring. Send the header on `reconcile-perks` (`main.py:1963`), on `skills assign_multiple` (`crud.py:1547` — **re-point to `/skills/internal/assign_multiple`**) and on the legacy `POST /skills/` helper (`crud.py:1156`), all via `_internal_token_headers()` (`crud.py:31`). | Backend Developer | DONE | `services/character-service/app/main.py`, `app/crud.py` | — | py_compile OK; anonymous `add_rewards` → 401; approval flow still grants preset skills (test-level) |
| 6 | **party-service.** Create `app/internal_auth.py` with `verify_internal_token` **and** `internal_token_headers()` (M1). Gate `POST /party/internal/xp-bonus` (`:129`) and `GET /party/internal/active-members` (`:176`). Re-point `main.py:47` at the new module. Send the header from `crud.settle_regen` (`crud.py:26`) via `internal_auth` — **not** by importing `main` (circular). | Backend Developer | DONE | `services/party-service/app/internal_auth.py` (new), `app/main.py`, `app/crud.py` | — | py_compile OK; no circular import (`python -c "import crud"` works); both routes 401 without header, 503 on empty token — **DONE.** `internal_auth.py` создан (обе стороны токена), `main._internal_token_headers` — тонкий алиас на него (имя сохранено: на него завязан source-sweep в `test_internal_headers.py`). `xp-bonus` и `active-members` под `verify_internal_token`; `crud.settle_regen` шлёт заголовок через `internal_auth` (циклического импорта нет: `python -c 'import crud'` OK). py_compile OK; pytest 47 passed |
| 7 | **skills-service.** Add the standard `verify_internal_token` to `auth_http.py` (**do not** extend `allow_jwt_or_service_token`). Extract `_assign_multiple_core`; add `POST /skills/internal/assign_multiple` (gate I); put `require_permission("skills:create")` on `POST /skills/assign_multiple` (`:567`). Gate legacy `POST /skills/` (`:75`) with `verify_internal_token`. Send the header on `revalidate-equipment` (`main.py:734`). | Backend Developer | DONE | `services/skills-service/app/auth_http.py`, `app/main.py` | — | py_compile OK; anonymous POST to either public route → 401; admin JWT → 200; internal twin behaves per gate I |
| 8 | **locations-service.** Move `POST /quests/progress/update` (`:3133`) to `POST /quests/internal/progress/update` + `verify_internal_token` (`main.py:3746`); old path removed. Add `get_current_user_via_http` to `POST /npcs/{npc_id}/dialogue/{node_id}/choose` (`:2488`) — **JWT only, no ownership, no schema change**. Send the header on 3 outgoing calls: `crud.py:286` (xp-bonus), `:6381` (gathering/award), `:7374` (free_slots_check) via `crud.py:26`. | Backend Developer | DONE | `services/locations-service/app/main.py`, `app/crud.py` | — | py_compile OK; anonymous dialogue choose → 401, authenticated → unchanged response; old quest-progress path → 404; gathering/post-XP flows keep working — **DONE.** Маршрут прогресса квеста перенесён и объявлен **ниже** определения `verify_internal_token` (`main.py`) — декоратор выполняется на импорте, выше по файлу зависимости ещё нет; старый путь удалён, вызывающих у него не было. Диалог НПС — JWT без проверки владения, как в §3.1. Заголовок добавлен на **четыре** исходящих вызова, а не три: **§3.4 пропустила `GET /party/internal/active-members` (`crud.py:7119`)** — маршрут закрывается задачей #6, вызов best-effort и вернул бы пустой набор молча. Сделан сплошной свип locations по всем закрываемым в FEAT-169 маршрутам — других пропусков нет. py_compile OK; pytest 1250 passed |
| 9 | **user-service.** Add `verify_internal_token` to `auth.py` (M4). Move `POST /{user_id}/activity/increment` (`main.py:1656`) to `POST /internal/{user_id}/activity/increment` with gate I; old path removed. Add `points: int = Field(1, ge=1, le=100)`. | Backend Developer | DONE | `services/user-service/main.py`, `services/user-service/auth.py` | — | py_compile OK; old path → 404; new path 401 without header, 503 on empty token; `points=0`/`-5` → 422 |
| 10 | **battle-service.** Add a module-local `_internal_token_headers()` to `inventory_client.py` (M3 — **do not** import from `main`). Send the header on `consume_item` (`:23`) and `update_durability` (`:83`); re-point `get_fast_slots` (`:118`) to `/inventory/internal/characters/{cid}/fast_slots` + header. Leave `get_item` (`:11`) and `get_equipment_durability` (`:45`) alone (public GETs). Send the header on `add_rewards` (`main.py:425`) and `xp-bonus` (`:442`) via `main.py:65`. | Backend Developer | DONE | `services/battle-service/app/inventory_client.py`, `app/main.py` | — | py_compile OK; no circular import; a live battle start/turn/finish exercises all four calls |
| 11 | **notification-service.** Add a module-local `internal_token_headers()`; re-point the activity call (`chat_routes.py:138`) to `/users/internal/{uid}/activity/increment` and send the header. Keep it fire-and-forget but log a WARNING instead of `except: pass`, so a future breakage is visible. | Backend Developer | DONE | `services/notification-service/app/chat_routes.py` | — | py_compile OK; sending a chat message still increments activity points — **DONE.** Добавлен `chat_routes.internal_token_headers()` (env на момент вызова), вызов переведён на `/users/internal/{uid}/activity/increment` с заголовком, `except: pass` заменён на `logger.warning` (и по статусу ответа, и по исключению). py_compile OK; pytest 236 passed. Переменная `INTERNAL_SERVICE_TOKEN` для notification-service — за задачей #1 (DevSecOps) |
| 12 | **battle-pass-service + dungeon-service.** Send `X-Internal-Token` on `add_rewards`: `battle-pass/app/crud.py:538` (helper `crud.py:25`) and `dungeon/app/http_clients.py:404` (helper `http_clients.py:26`). No other change. | Backend Developer | DONE | `services/battle-pass-service/app/crud.py`, `services/dungeon-service/app/http_clients.py` | — | py_compile OK; both calls carry the header |
| 13 | **autobattle-service (future-proofing).** Add an `internal_token_headers()` helper to `app/clients.py` and send it on `get_battle_state` (`:15`) and `post_battle_action` (`:23`). Routes are not gated yet — the header is inert today and prevents a silent death when `/battles/internal/*` is swept. | Backend Developer | DONE | `services/autobattle-service/app/clients.py` | #1 (env var) | py_compile OK; auto-battle still runs end-to-end |
| 14 | **QA — inventory-service.** Auth matrix (no header / wrong / **empty token → 503** / correct → 200) for all 5 internal routes **and** the new `fast_slots` twin. Player `fast_slots`: anonymous → 401, other player's character → 403, own → 200 — and **remove the `xfail` from `TestFastSlotsAuth::test_fast_slots_requires_auth`**. Move/adapt the anonymous calls in `test_fast_slots_payload.py`, `test_equip_locking.py`, `test_npc_equipment.py`, `test_item_out_schemas_serve_stored_rows.py`. **Close the coverage gap: `update-durability` has no HTTP test at all — write one.** Assert the outgoing header on the real satiety/reconcile-perks client code. | QA Test | DONE | `services/inventory-service/app/tests/*` | #3 | pytest green; the xfail marker is gone and the test passes on its own merit — **DONE.** Новые `test_internal_auth.py` (59) и `test_update_durability.py` (19), расширены `test_outgoing_internal_headers.py` и `test_food_satiety.py`. Матрица на 6 маршрутов gate I + двойник пояса; игровой пояс: аноним 401 / чужой 403 / неизвестный 404 / свой 200, ответы игрового и internal маршрутов совпадают байт-в-байт (сплит `_core` не должен разойтись), internal-токен игровой маршрут НЕ открывает. Закрыт пробел по `update-durability` (было ноль HTTP-тестов). Исходящие — значение заголовка на реальных `_reconcile_perks` / `_reconcile_perks_async` / satiety + два негативных контроля, доказывающих, что «ничего не упало» ничего не ловит. AST-свип по `main.py` проверен мутацией. pytest 1389 passed (+88) |
| 15 | **QA — character-attributes-service + character-service.** Auth matrix on the 3 attribute internal routes; **`reconcile-perks` has no HTTP test — write one.** Auth matrix on `add_rewards`; update `test_add_rewards.py`, `test_gold_transactions.py`, `test_xp_books.py`, `test_xp_paths_real_session.py`, `test_xp_multiplier_call_shape.py`. Caller-side: assert the header on the real `crud.send_skills_presets_request` / `send_skills_request` and on the reconcile-perks call, **including the new `/skills/internal/` URL**. | QA Test | DONE | `services/character-attributes-service/app/tests/*`, `services/character-service/app/tests/*` | #4, #5 | pytest green in both services; header assertions read `call.kwargs["headers"]` — **DONE.** char-attrs: новый `test_internal_auth_feat169.py` (40) — матрица на три маршрута, каждый отказ сверяется со снимком БД из 7 полей; **закрыт пробел по `reconcile-perks`** (выдача перка и бонуса, отзыв, идемпотентность), внутрипроцессные вызовы закреплены как негатированные. character-service: матрица на `add_rewards` (10) с проверкой тройного реестра (золото, пассивный опыт, строка `gold_transactions`); исходящие — заголовок и **новый URL `/skills/internal/assign_multiple`** на реальной `crud.send_skills_presets_request`, заголовок на `send_skills_request` и на reconcile-perks через реальный обработчик `full_profile`. Мутационная проверка: откат трёх правок → 9 падений. pytest 465 passed / 2 skipped / 1 xpassed (+40) и 1076 passed / 1 skipped (+22) |
| 16 | **QA — party-service + locations-service.** Auth matrix on `xp-bonus` and `active-members`; update `test_party.py:194`, `test_settle_before_read.py`. Caller-side header on the **real** `crud.settle_regen`. locations: auth matrix on the moved quest-progress route; dialogue choose 401/200; caller-side header on the **real** xp-bonus / gathering-award / free-slots-check functions (`test_post_xp.py:253`, `test_gathering*.py`). | QA Test | DONE | `services/party-service/app/tests/*`, `services/locations-service/app/tests/*` | #6, #8 | pytest green; `settle_regen` test fails if the header is dropped (verify by temporarily removing it) — **DONE.** Новые `test_internal_auth.py` в обоих сервисах (21 + 21). party: матрица на `xp-bonus` и `active-members`, отказ не начисляет опыт и не отдаёт состав отряда, свип «весь префикс `/party/internal/` закрыт»; заголовок на реальной `crud.settle_regen` (значение, URL, тело, таймаут, чтение токена в момент вызова, все чанки >50 id). locations: матрица на перенесённый `quests/internal/progress/update`, **старый путь отдаёт 404** (и анонимно, и с валидным токеном, и отсутствует в таблице маршрутов); диалог НПС — 401 анонимно, ответ авторизованного не изменился, отсутствие проверки владения закреплено намеренно (тест + предупреждение «прочти прежде чем чинить»); заголовок на **четырёх** реальных исходящих, включая пропущенный в §3.4 `active-members`. Мутационная проверка выполнена в обоих сервисах (5 и 2 падения). pytest 68 passed (+21) и 1275 passed (+25) |
| 17 | **QA — skills-service + user-service + notification-service.** skills: auth matrix on `POST /skills/internal/assign_multiple` and legacy `POST /skills/`; 401/403/200 matrix on `POST /skills/assign_multiple` (anonymous / plain player / `skills:create` holder); caller-side header on `revalidate-equipment` (`test_internal_headers.py`). user-service: auth matrix on the moved activity route + `points` validation + old path 404. notification: assert the chat send calls the **new** path **with** the header (this call is currently unmocked and is the cause of the flaky rate-limit test, ISSUES ~:227 — mock it while here). | QA Test | DONE | `services/skills-service/app/tests/*`, `services/user-service/tests/*`, `services/notification-service/app/tests/*` | #7, #9, #11 | pytest green in all three; the flaky chat rate-limit test no longer depends on a live user-service — **DONE.** skills: новый `test_internal_auth.py` (34) — матрица gate I на `internal/assign_multiple` и legacy `POST /skills/`, матрица gate A на публичном `assign_multiple` (аноним 401 / обычный игрок 403 / держатель `skills:create` 200) через реальный `require_permission`, паритет двойника и публичного пути, и **два механизма токена разведены**: сервисный секрет в позиции Bearer не открывает `verify_internal_token`, а `X-Internal-Token` не открывает `allow_jwt_or_service_token`. user-service: матрица на перенесённый маршрут, старый путь 404, валидация `points` (0/-5/-1/101/1000 → 422, 1/2/100 → 200, без поля → 1), отказ не двигает баланс; `test_jwt_secret.py` усилен — сообщение RuntimeError проверяется по тексту, плюс страж, что `os.environ[...]` не вернулся. notification: новый `test_chat_activity_increment.py` (12) — новый путь + значение заголовка, WARNING вместо `except: pass` на не-200 и на исключении; **флапающий тест rate limiting починен** (autouse-мок в `conftest.py`, `test_chat.py` 1.14 с вместо ~4 с на отправку), запись в `docs/ISSUES.md` помечена DONE. pytest 253 (+34), 550 (+26), 248 (+12) |
| 18 | **QA — battle-service + battle-pass + dungeon + autobattle.** Caller-side header assertions on the **real** client functions: `inventory_client.consume_item`, `.update_durability`, `.get_fast_slots` (also asserting the `/inventory/internal/…` URL), `battle/main.py` add_rewards + xp-bonus, `battle-pass/crud.py:538`, `dungeon/http_clients.py:404`, `autobattle/clients.py` both calls. Update any test asserting the old `fast_slots` URL. | QA Test | DONE | `services/battle-service/app/tests/*`, `services/battle-pass-service/app/tests/*`, `services/dungeon-service/app/tests/*`, `services/autobattle-service/app/tests/*` | #10, #12, #13 | pytest green in all four; every assertion inspects the header, not just "no exception" — **DONE.** Новые `test_internal_headers.py` в battle (17) и autobattle (7), расширены battle-pass (+5) и dungeon (+3). Проверяется значение заголовка на реальных функциях: `inventory_client.consume_item` / `.update_durability` / `.get_fast_slots` (с утверждением **нового** URL `/inventory/internal/...` и отдельным тестом, что старого игрового пути там нет), `main._distribute_pve_rewards` (add_rewards + xp-bonus), `main._party_active_members_data`, `crud._deliver_gold_xp`, `http_clients.add_gold` / `get_party_active_members`, `clients.get_battle_state` / `post_battle_action`. Публичные `get_item`, `get_equipment_durability`, `get_character_owner` закреплены как маршруты БЕЗ заголовка. Мутационная проверка на трёх файлах — тесты краснеют. **Найдена и исправлена слабость в шаблоне свипа** (окно в 900 символов перетекало в соседнюю функцию и видело её хелпер — свип оставался зелёным при потерянном заголовке); все четыре свипа теперь режут окно по первой пустой строке. pytest 727 (+21), 124 (+5), 135 (exit 0, +3), 133 (+7) |
| 19 | **Frontend — verification, change only if broken.** No code change is expected: the global axios interceptor (`api/axiosSetup.ts:53`) already attaches the JWT to `profileSlice.fetchFastSlots` (`:485`) and to `NpcStatsEditor` (`:249`) and `NpcDialogueModal` (`:74`). Confirm a 401/403 on each of these three surfaces a **Russian** message (toast or `rejectValue`) and never fails silently. Fix only what is actually silent — if a component's styles are touched, CLAUDE.md §10.8/§10.12 (Tailwind + mobile) apply. | Frontend Developer | DONE | `services/frontend/app-chaldea/src/redux/slices/profileSlice.ts`, `components/AdminNpcsPage/NpcStatsEditor.tsx`, `components/pages/LocationPage/NpcDialogueModal.tsx` | #3, #7, #8 | `npx tsc --noEmit` and `npm run build` both pass; each of the three paths shows a Russian error on 401/403 | — **DONE (verified by Reviewer, no code change needed).** `npx tsc --noEmit` и `npm run build` зелёные; все три поверхности уже показывают русскую ошибку и ничего не проглатывают: `profileSlice.fetchFastSlots` (`:487` → `rejectValue`, укладывается в `state.error` на `:992`), `NpcStatsEditor.handleSaveSkills` (`:266-273`, toast с `detail` от сервера) и `NpcDialogueModal.handleChooseOption` (`:85`, toast «Ошибка при выборе ответа»). Правок не потребовалось.
| 20 | **ISSUES.md bookkeeping.** Mark DONE/remove the entries this feature closes (fast_slots, the eight internal routes, add_rewards/xp-bonus, the skills holes, activity/increment, the locations quest+dialogue holes, the autobattle token blocker, the `JWT_SECRET_KEY`/`INTERNAL_SERVICE_TOKEN` compose debt). **Keep** the anonymous-READ entry as an open follow-up, and **split `GET /attributes/{cid}/perks` out of it into its own entry** — an anonymous GET that writes to the DB and fans out to two other services is a bug regardless of the product decision on public reads. Add a follow-up entry for the remaining nginx-only internal prefixes (§3.10.3). | DevSecOps | DONE | `docs/ISSUES.md` | #1–#13 | No stale entry for anything fixed here; the perks write-on-read has its own entry with priority and file:line |
| 21 | **Review.** Re-run `py_compile` for every touched service, `pytest` per service, `npx tsc --noEmit`, `npm run build`, `nginx -t`. **Live verification (mandatory):** log in, open the profile belt, start and finish a battle using a belt item, gather a node, eat food, level up a character in a party (party XP tick), open an NPC dialogue, save NPC skills in the admin editor, send a chat message. Then verify from outside the gateway that every closed route returns 401/403 and none returns 200. Verify the merged prod compose config has no default secrets. **FAIL the review if any caller-side test asserts only "no exception raised" instead of the header value.** | Reviewer | DONE | all | #1–#20 | All automated checks green **and** every live scenario works with zero console/5xx errors; auth matrix verified through the gateway | — **DONE.** Ревью #1 (код, безопасность, автопроверки, живой прогон, мутационная проверка 26 вызовов) и ревью #2 (документация) — см. §5.

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-19
**Result:** FAIL — **code, security and runtime behaviour all PASS; two non-code deliverables of the
feature (tasks #20 and the documentation half of #1) are simply not done.** Nothing found in the
implementation itself requires a change.

---

#### Automated Check Results
- `py_compile` — **PASS** (all 56 modified/added `.py` files, run in a clean `python:3.10-slim`)
- `pytest` — **PASS**, all 13 services, run in their own containers with the repo mounted and the
  CI arguments from `.github/workflows/ci.yml`:
  user 545+5s · character 1076+1s · skills 253 · inventory 1388+1s · char-attrs 457+10s+1xp ·
  locations 1275 · notification 248 · battle 723+4s · autobattle 133 · battle-pass 124 ·
  dungeon exit 0 · party 68.
  *Note:* char-attrs needs `INTERNAL_SERVICE_TOKEN=test-internal-token` in the container, see
  pre-existing issue P-2 below; skills/character/inventory/… need `--asyncio-mode=auto` (CI passes it).
- `npx tsc --noEmit` — **PASS** (exit 0, frontend container)
- `npm run build` — **PASS** (exit 0, `✓ built in 32.13s`)
- `nginx -t` — **PASS** on **both** configs (run on the compose network so upstreams resolve;
  `nginx.prod.conf` tested with a throwaway self-signed cert for the letsencrypt path)
- `docker compose config` — **PASS**, see the secrets section below
- Live verification — **PASS**, see below

---

#### 1. The five hand-rebuilt files (QA warning: two QA agents ran `git checkout --`)

`party-service/app/crud.py`, `character-service/app/crud.py`, `battle-service/app/inventory_client.py`,
`battle-pass-service/app/crud.py`, `autobattle-service/app/clients.py` were re-read **diff by diff**
against §3.3/§3.4, and then **mutation-tested individually** (see §2). All five are correct and complete:

| File | Expected | Present |
|---|---|---|
| `party-service/app/crud.py:10,:28` | import `internal_auth.internal_token_headers`, header on `settle_regen` | yes — and the import is the leaf module, no cycle (`python -c "import crud"` OK) |
| `character-service/app/crud.py:1156,:1555` | header on legacy `POST /skills/`; header **and** re-point to `internal/assign_multiple` | yes — both; the URL change is the easiest thing to lose in a hand-rebuild and it is there |
| `battle-service/app/inventory_client.py:8,:37,:98,:138` | module-local `_internal_token_headers()` (no import from `main`), header on `consume_item` / `update-durability`, header **and** `/inventory/internal/…` on `get_fast_slots`; `get_item` / `get_equipment_durability` untouched | yes — all four, and the two public GETs are correctly left bare |
| `battle-pass-service/app/crud.py:548` | header on `add_rewards` | yes |
| `autobattle-service/app/clients.py:13,:29,:40` | `internal_token_headers()` + header on both `/battles/internal/*` calls | yes |

**No missing or subtly-wrong change in any of the five.** Verified again at runtime (§4).

---

#### 2. Are the header guards real? Independent sweep + mutation testing

**(a) My own repo-wide caller sweep**, per gated route, over `.py`/`.ts`/`.tsx` (not trusting §3.4 or
QA's sweep). Grepped each route fragment — `fast_slots`, `revalidate-equipment`, `consume_item`,
`free_slots_check`, `gathering/award`, `update-durability`, `settle-regen`, `satiety`,
`reconcile-perks`, `add_rewards`, `xp-bonus`, `active-members`, `assign_multiple`,
`progress/update`, `activity/increment` — and read every hit.
**Result: 26 real call sites; every single one sends the header, and the four re-pointed URLs are all
re-pointed.** No caller left on an old path. The §3.4 matrix was indeed incomplete (`active-members`
had five unlisted callers) but the developers had already found and fixed all five
(battle `main.py:990/:1171/:3713`, dungeon `http_clients.py:69`, locations `crud.py:7122`).
The only frontend caller of a changed contract is `NpcStatsEditor.tsx:249` → `/skills/assign_multiple`,
which is exactly the route that kept its path under RBAC. No frontend call site needs changing.

**(b) Mutation testing — 26 mutations, each run against that service's full suite, file restored by
byte-exact copy afterwards (never `git checkout`).** For every one of the 26 call sites I removed the
`headers=` argument (or reverted the URL) and re-ran the suite:

> **26 / 26 CAUGHT.** There is **no toothless guard**: every call site is pinned by at least one
> behavioural test that patches the transport and reads `call.kwargs["headers"]["X-Internal-Token"]`,
> not merely "nothing raised".

QA's observation about the FEAT-167 sweep template is accurate as a *code-quality* point — the
fixed-window sweeps still present in `party/tests/test_internal_headers.py:149` (±400),
`locations/…:175` (−200/+700), `character-service/…:308,:342` (±400/±500),
`battle-pass/…:189` (−300/+500) and `skills/…:208` (+400) can in principle see a neighbouring
function's helper. **But it does not matter here**, because in every one of those services the
same call is *also* covered by a real behavioural test, and the mutation run proves it: e.g. dropping
the header on `locations crud._check_inventory_has_free_slot` reddens
`TestInventoryGatheringCallsCarryTheToken::test_free_slots_check_sends_the_token`, not the sweep.
`inventory/tests/test_outgoing_internal_headers.py:137` uses proper paren-matching and is the best of
the family — worth making the template. Logged as a low-priority follow-up, **not** a blocker.

---

#### 3. Fail-closed behaviour, moved paths, and the two token mechanisms — verified live

Through the **gateway**, anonymously (must never be 200):

| Route | Result |
|---|---|
| `GET /inventory/characters/{id}/fast_slots` | **401** (service-side; nginx cannot method-gate a GET, as designed) |
| `GET /inventory/internal/…/fast_slots`, `…/consume_item`, `…/free_slots_check`, `…/gathering/award`, `/inventory/internal/update-durability`, `…/revalidate-equipment` | **403** (nginx) |
| `/attributes/internal/settle-regen` · `…/{id}/satiety` · `…/{id}/reconcile-perks` | **403** |
| `POST /characters/{id}/add_rewards` | **403** |
| `POST /party/internal/xp-bonus` · `GET /party/internal/active-members` | **403** |
| `POST /skills/internal/assign_multiple` | **403** (new nginx rule) |
| `POST /skills/` | **403** (new `limit_except GET HEAD`) |
| `POST /skills/assign_multiple` | **401** |
| `POST /locations/quests/internal/progress/update` | **403** |
| `POST /users/internal/{id}/activity/increment` | **403** |
| `POST /locations/npcs/{id}/dialogue/{node}/choose` | **401** |
| **old** `POST /locations/quests/progress/update` | **404** ✔ moved, not aliased |
| **old** `POST /users/{id}/activity/increment` | **404** ✔ moved, not aliased |

`GET /skills/…` sub-paths are untouched by the new exact-match rule: `/skills/1` → 200,
`/skills/admin/skills/` → 200 (admin JWT), `/skills/1/resolved` → 401 as before, `GET /skills/` → 405
(the route has no GET — it is proxied, not denied, which is the point of `limit_except`).

**Direct to each service** (gateway bypassed):
- player `fast_slots`: own → **200**, another player's character → **403 «Вы можете управлять только своими персонажами»**, unknown id → **404 «Персонаж не найден»**, anonymous → **401**, and a valid `X-Internal-Token` does **not** open the player route → **401**.
- internal twin: no header / wrong header / player JWT → **401 «Недействительный internal token»**; NPC with `user_id IS NULL` → **200** (ownership correctly absent).
- **twin parity: byte-identical response bodies** (1573 bytes, `==`) between the player route and the internal twin for the same character — the `_core` split has not drifted.
- **empty `INTERNAL_SERVICE_TOKEN` → 503 «Internal service token не настроен»** confirmed in **all seven** services that host a gate: party (`internal_auth`), skills (`auth_http`), user (`auth`), inventory, char-attrs, character (`auth_http`), locations (`main`).
- **skills' two mechanisms cannot substitute for each other** (live): internal route + `X-Internal-Token` → 200, internal route + the same secret in the **Bearer** position → **401**; the Bearer route (`/skills/1/resolved`) + `X-Internal-Token` only → **401**. `allow_jwt_or_service_token` was correctly left untouched.
- **empty JWT secret is rejected**: both `JWT_SECRET_KEY=` (empty) and unset raise
  `RuntimeError: JWT_SECRET_KEY не задан или пуст …` at import. This is the case the old
  `os.environ["JWT_SECRET_KEY"]` would have sailed through, since compose expands an unset
  variable to an empty string.

---

#### 4. Live Verification Results

**Stack recreated with the new `.env` (`docker compose up -d --force-recreate`), plus
`--build api-gateway`** — note the gateway config is baked into the image, so a plain recreate keeps
the old `nginx.conf`; a deploy does `up --build`, so prod is fine, but it is worth knowing.
All 13 token consumers confirmed to carry the real `INTERNAL_SERVICE_TOKEN` inside the container,
and user-service the real `JWT_SECRET_KEY` (login works, so the new secret is live).

Every FEAT-169-gated call was driven through its **real client function** against the **live**
services, and confirmed in the callee's access log:

| Scenario | Evidence |
|---|---|
| **Full battle** (create → 15 turns → win) | `POST /battles/` 201 → both belts fetched via `GET /inventory/internal/characters/{706,641}/fast_slots` **200**; the belt snapshot contains the potion |
| **Belt item used in battle** | `POST /inventory/internal/characters/706/consume_item` **200**; quantity 3 → **2** in the live state and in the browser |
| **Durability write** | `inventory_client.update_durability` → **200** `{"status":"ok"}` (the test character wears nothing durable, so the battle itself had no entries) |
| **PvE rewards** | `POST /characters/706/add_rewards` **200** |
| **Party XP tick** | `POST /party/internal/xp-bonus` **200** |
| **Co-located squad lookup** | `active-members` **200** from locations (`_party_active_member_ids`) *and* dungeon (`get_party_active_members`) |
| **Title grant** | `POST /characters/internal/evaluate-titles` **200** after the win |
| **Gathering award** | `crud._award_via_inventory` → item granted, +1 mining XP, `gathering/award` **200** |
| **Crafting / free-slot check** | `crud._check_inventory_has_free_slot` → **True** (fails *closed*, so a lost header would have said "bag full") |
| **Rest / passive regen** | `party crud.settle_regen` → `settle-regen` **200**, no WARNING |
| **Satiety (eat food)** | `satiety` reached with the header → **400 «Недопустимая редкость еды»** i.e. business validation, auth passed. *The local DB has no `is_food` items at all, so a full eat-food click-through was impossible — flagged as a data gap, not a code gap.* |
| **Level-up perk reconciliation** | `reconcile-perks` **200** from inventory (sync **and** async helpers) and from character-service's real helper |
| **Subclass equipment revalidation** | `skills main.revalidate_character_equipment` → `revalidate-equipment` **200** |
| **Quest progress (moved route)** | `quests/internal/progress/update` reached with the header → **404 «Прогресс квеста не найден»** (business), old path **404 not found** |
| **Chat message → activity increment** | sent from the **browser**; `POST /users/internal/4/activity/increment` **200**, `activity_points` 57 → 58. `points=0` / `points=-5` → **422** |
| **Character approval → skills assignment** | `crud.send_skills_presets_request` → `POST /skills/internal/assign_multiple` **200**; legacy `crud.send_skills_request` → `POST /skills/` **409 «Навык уже есть»** (business, auth passed) |
| **Admin NPC skill editing** | full matrix through the gateway: anonymous **401**, plain player **403 «Недостаточно прав»**, `skills:create` holder **200** |
| **Auto-battle** | `clients.get_battle_state` reaches `/battles/internal/…` with the (currently inert) header — 404 for a non-existent battle, i.e. routed, not rejected |
| **Dungeon gold award** | `http_clients.add_gold` → `add_rewards` **200** |

**Browser** (Playwright, Chromium): login → `/home` → `/profile` → `/admin/npcs`.
- Profile renders **«БЫСТРЫЕ СЛОТЫ»** with the potion and its post-battle quantity — the JWT + ownership player route works end-to-end in the UI.
- Chat message sent successfully from the UI.
- **Console errors: NONE** and **no 4xx/5xx** on any of those pages, apart from the dev-only Vite HMR
  websocket noise (`ws://localhost:5555`, dev server only, not present in prod).
- Screenshots: `scratchpad/feat169/` (`20-profile-belt.png`, `21-admin-npcs.png`, `11-chat.png`).

**Log sweep across all services for the whole session:** every `401`/`403`/`503` on a gated route
traces back to one of my own negative probes. **Zero unexpected auth failures** — i.e. no caller is
silently degraded. Neither secret appears anywhere in any container log.

**Test data cleaned, characters restored:** battles 218/219 (MySQL rows, Redis keys, 17 Mongo docs),
the probe potion and gathering drop, `fast_slot_1`, mining XP → 0/0, character 706's location → NULL
and its attributes back to 250/250 health-15, the two perks the test victory unlocked, mob 641 back to
200 HP, `activity_points` back to 57, the probe user, the test chat message. Working tree verified
byte-identical to the pre-review state (60 files / +2183 / −230); the incidental
`package-lock.json` churn from the container's `npm install` was reverted. **No commits made.**

---

#### 5. Secrets, compose and nginx

- Merged prod config (`-f docker-compose.yml -f docker-compose.prod.yml config`): **zero** occurrences of
  `dev-internal-token-change-me` and `your-secret-key`; `INTERNAL_SERVICE_TOKEN` declared for **13**
  consumers, including the four that previously only inherited it.
- **Compose merge verified empirically, service by service** (not by reasoning): for every service the
  merged prod `environment` is a **superset** of the dev one — `LOST=[]` everywhere. The only services
  that lose keys are `mongo-express` / `redis-insight`, which prod disables on purpose.
- With an empty `.env`: the prod config **fails** with
  `required variable INTERNAL_SERVICE_TOKEN is missing a value: INTERNAL_SERVICE_TOKEN is required in production`,
  while the dev config still resolves (13 fallbacks) — exactly the PM's dev/prod split.
- `nginx -t` green on **both** files; routing behaviour verified live against the running gateway.
- `.env.example` comment block rewritten and accurate.
- `X-Internal-Token` is never logged anywhere (source grep + log grep).

---

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `docs/ISSUES.md:136, :145, :154, :164, :172, :180, :196` | **Task #20 was never done.** Seven entries this feature actually closes are still written as open: the `fast_slots` leak, the eight nginx-only internal routes, the `INTERNAL_SERVICE_TOKEN` compose-fallback debt, the two skills holes, `activity/increment`, the two locations holes, and the autobattle token blocker. Mark each DONE (FEAT-169) per CLAUDE.md §11 "Bug Tracking". | DevSecOps | FIX_REQUIRED |
| 2 | `docs/ISSUES.md:374` | Same task: the umbrella entry «большинство внутренних эндпоинтов защищены только nginx» is now stale — after this feature `/party/internal/` is fully closed and `/users/internal/` has the machinery. It must be narrowed to the remaining prefixes listed in §3.10.3. | DevSecOps | FIX_REQUIRED |
| 3 | `docs/ISSUES.md` (entry at `:188`, the anonymous-reads group) | Same task: `GET /attributes/{cid}/perks` (`char-attrs/main.py:332`, self-heal write at `:339-345`) was **not** split into its own entry, although §3.10.2 and task #20's acceptance criterion require it — an anonymous GET that writes to the DB and fans out to two other services is a bug independent of the product decision on public reads. | DevSecOps | FIX_REQUIRED |
| 4 | `docs/ARCHITECTURE.md` | Task #1's documentation half is explicitly marked "not written". The deploy/dev note is required by the task: local `.env` must now carry `JWT_SECRET_KEY` or user-service crash-loops, and prod refuses to start without `INTERNAL_SERVICE_TOKEN`. | DevSecOps | FIX_REQUIRED |
| 5 | Task #19 row in §4 | Bookkeeping only: the frontend task is still `TODO`, but the verification it asks for is **done and green** — `tsc` and `build` both pass, and all three surfaces already surface a Russian message (`profileSlice.ts:487` → `state.error` at `:992`, `NpcStatsEditor.tsx:266-273` toast, `NpcDialogueModal.tsx:85` toast). No code change was needed. Flip to DONE. | PM | FIX_REQUIRED |

**Nothing in the implementation needs to change.** Issues 1–4 are documentation deliverables of this
feature; issue 5 is a status flip.

---

#### Pre-existing issues noted (not caused by this feature, do not block it)

- **P-1 — `docs/ISSUES.md` candidate.** `services/character-attributes-service/app/tests/conftest.py:30`
  uses `os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")` while
  `test_passive_experience.py:110`, `test_refund_stamina.py` and `test_regen.py` hard-code the literal
  `"test-internal-token"`. Whenever the environment already defines the variable — which is true inside
  **every service container** — the seed value differs and **16 FEAT-167 tests fail with 401**.
  Green on CI (no such env var) and green with `-e INTERNAL_SERVICE_TOKEN=test-internal-token`, so it is
  a test-environment trap, not a product bug — but it makes "run the suite in Docker" misleading.
  FEAT-167 legacy; FEAT-169's new char-attrs test file does **not** repeat the mistake.
- **P-2.** `dungeon-service`'s pytest prints no summary line at all (only progress dots), so its runs can
  only be judged by exit code. Worth a look when someone is next in that service's `conftest.py`.
- **P-3.** The fixed-window source-sweep template (§2b) should be replaced by the paren-matching version
  in `inventory-service/app/tests/test_outgoing_internal_headers.py:137` wherever it is still used.
  Harmless today because every call site has a behavioural test as well.
- **P-4.** The local dev DB contains **no** `is_food` items, so the eat-food player flow cannot be
  exercised locally end-to-end. Test-data gap.

---

### Review #2 — 2026-09-20 (docs-only re-check of the five fix items)
**Result:** **PASS — feature complete.**

Scope: documentation only. Confirmed first that **no service code moved in this pass** — the per-file
`git diff --stat` for every `services/**`, `docker-compose*.yml`, `nginx*.conf` and `.env.example`
entry is byte-for-byte identical to Review #1 (e.g. `inventory-service/app/main.py` still `97 +++---`,
`skills-service/app/main.py` still `67 ++---`, `user-service/auth.py` still `50 ++--`). The only
changed files since my last look are `docs/ISSUES.md`, the new `docs/ARCHITECTURE.md` section and
this feature file. No re-run of the suites or the live pass was needed, and none was done.

| # (Review #1) | Verified |
|---|---|
| 1 | **Done.** All seven entries struck through as `DONE (FEAT-169, задачи #N)` in the FEAT-167 style, each with an «Исправлено (FEAT-169)» evidence block. I spot-checked four blocks against the shipped code — `fast_slots` (`:137`), the eight internal routes (`:147`), skills (`:171`) and `activity/increment` (`:181`) — and every claim matches what I verified live in Review #1: the `_core` split, the internal twin without an ownership check, the re-pointed `inventory_client.py`, the new leaf module `party-service/app/internal_auth.py` and why it exists, the `except: pass` → `logger.warning` swap, the `Field(1, ge=1, le=100)` validation, and the nginx routing results. Entry 27's leftover step 3 is closed with the correct reasoning: compose expands an unset variable to an **empty string**, so `os.environ[...]` would have let a blank secret through — that is exactly the case I confirmed live raises `RuntimeError`. |
| 2 | **Done and better than asked.** The umbrella entry is renamed to name the prefixes that actually remain and carries a route → `file:line` → callers table; `/users/internal/*diamonds|cosmetics` is correctly called out as the weightiest (currency mutation) with a note that FEAT-169 already laid the machinery. **The dungeon trap is real and I verified it independently:** `services/dungeon-service/app/http_clients.py:377` polls `GET /battles/internal/{id}/state` with **no** header while autobattle is future-proofed — confirmed by reading the function. It is written into *both* that entry and the autobattle entry, with "fix dungeon's header first" as step one of any future gating task. That is a genuine find of this pass, not bookkeeping, and it is correctly out of FEAT-169's scope. |
| 3 | **Done.** `GET /attributes/{cid}/perks` is now its own MEDIUM entry (`:209`) with the write-on-read and amplification argument, correct `file:line` (`char-attrs/main.py:332`, self-heal at `:339-345`), and an explicit paragraph on why it is separable from the product decision. The anonymous-reads entry (`:200`) keeps its open status and cross-references it. |
| 4 | **Done.** `docs/ARCHITECTURE.md` gained «Секреты и fail-fast»: the empty-string subtlety, the crash-loop consequence for local dev, the deliberate decision *not* to use `${JWT_SECRET_KEY:?}`, the dev/prod split for `INTERNAL_SERVICE_TOKEN`, the warning that the prod `:?` form takes down `config`/`ps`/`down` too (which I confirmed empirically in Review #1), and the pre-flight grep. The stale Authentication bullet claiming the key is hardcoded as `"your-secret-key"` is corrected. |
| 5 | **Done.** Task #19 flipped to DONE with the verification evidence; task #21 flipped to DONE. |

**My four Review #1 entries survived** intact (`ISSUES.md:674`, `:682`, `:689`, `:698`).

**The notification rate-limit entry — removal justified, with a correction.** It was not in fact
removed: it is struck through as `DONE (FEAT-169 #17)` at `ISSUES.md:255`, and the *other* half of the
old entry — the blocking `requests.post(..., timeout=3)` still sitting in the chat hot path — was
correctly split off and **left open** at `:248`. That split is right: the flakiness is genuinely fixed
(autouse `mock_activity_increment` fixture in `notification-service/app/tests/conftest.py` patches
`chat_routes.requests.post`, so no chat test touches the network), while the latency debt is still
true in the shipped code and still needs `BackgroundTasks`.

**One cosmetic inaccuracy, not worth a fix round** (noting it so nobody trusts it later): the
`fast_slots` evidence block says the anonymous calls in `test_equip_locking.py` and
`test_npc_equipment.py` were moved to the internal route. Neither file ever calls the route over HTTP
— they only touch fast slots at ORM level, which is why neither was modified. The claim is inherited
from §2.2's slightly over-broad list; the substantive part (xfail removed, `test_fast_slots_payload.py`
and `test_item_out_schemas_serve_stored_rows.py` converted) is accurate. There is also a leftover
sentence fragment in the anonymous-reads entry at `:205` («Данные эти чтения не портят»).

**Feature is complete.** Nothing outstanding.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-19 20:00 — PM: фича создана (остатки открытых эндпоинтов + fail-fast по секретам), запускаю анализ
[LOG] 2026-09-19 20:10 — Analyst: начал анализ, поднял паттерны FEAT-167 (fail-closed verify_internal_token, internal-двойники маршрутов, обновление всех вызывающих)
[LOG] 2026-09-19 20:25 — Analyst: fast_slots — ровно два вызывающих: battle-service (inventory_client.py:118, без токена, читает пояс один раз на старте боя) и фронтенд (profileSlice.ts:485, JWT есть). Раскладывается на игровой + internal без правок UI
[LOG] 2026-09-19 20:35 — Analyst: add_rewards — три вызывающих (battle, battle-pass, dungeon), из UI не вызывается; xp-bonus — три, а не два: третий это locations-service (crud.py:286, опыт за посты), в брифе его нет
[LOG] 2026-09-19 20:45 — Analyst: восемь internal-маршрутов подтверждены, ни один не зовётся с фронтенда; два новых (xp-multiplier/xp-multipliers) уже закрыты FEAT-168. У party-service нет verify_internal_token, у battle-service inventory_client.py нет хелпера заголовка
[LOG] 2026-09-19 20:55 — Analyst: секреты — JWT_SECRET_KEY уже читается через os.environ[...] (падает сам), в .env.example заглушка уже есть; локальный .env не содержит ни одного из двух ключей — снятие fallback ломает локалку. На fallback'и не завязан ни один тест, CI не через compose
[LOG] 2026-09-19 21:05 — Analyst: обнаружены пять новых открытых изменяющих маршрутов (skills/assign_multiple, skills/, quests/progress/update, npc dialogue choose, users activity/increment) — добавлены в ISSUES.md, в текущую фичу не берутся без решения пользователя
[LOG] 2026-09-19 21:10 — Analyst: шаг «добавить JWT_SECRET_KEY в .env.example» уже выполнен — отметил в ISSUES.md как неактуальный
[LOG] 2026-09-19 21:15 — Analyst: анализ завершён — затронуто 9 backend-сервисов + compose; схема БД и Alembic не нужны
[LOG] 2026-09-19 21:30 — Architect: начал проектирование, взял решения PM (пять новых дыр в scope, active-members закрываем, секреты — JWT везде, internal-токен только в prod)
[LOG] 2026-09-19 21:45 — Architect: по каждой из пяти новых дыр решение принято по её вызывающим, а не одним правилом. assign_multiple зовут двое — character-service (создание персонажа) и админский редактор НПС, поэтому раскладываем: internal-двойник + require_permission("skills:create") на публичном пути (новое разрешение не нужно, такое уже есть)
[LOG] 2026-09-19 21:50 — Architect: legacy POST /skills/ — вызывающий в character-service есть, но в проде не вызывается ни разу (только тесты) → закрываем internal-токеном. POST /locations/quests/progress/update — вызывающих нет вообще → переносим под /quests/internal/ (nginx его уже режет), риска ноль
[LOG] 2026-09-19 21:55 — Architect: выбор в диалоге НПС — только игровой экран, в теле запроса вообще нет character_id, и сам обработчик ничего не выдаёт (квест берётся отдельной ручкой) → ставим JWT без проверки владения; добавлять character_id ради проверки = ломать контракт и править фронт без выигрыша
[LOG] 2026-09-19 22:00 — Architect: activity/increment переносим под /users/internal/ — у user-service вообще нет механизма internal-токена, добавляем; заодно единственный вызывающий (notification-service) не имеет ни переменной, ни заголовка — это третий сервис, которому нужен INTERNAL_SERVICE_TOKEN, помимо autobattle
[LOG] 2026-09-19 22:10 — Architect: собрана матрица вызывающих — 19 мест в 10 сервисах, 12 из них проглатывают ошибку. Требование к QA: проверять сам заголовок на реальной клиентской функции, а не «ничего не упало»
[LOG] 2026-09-19 22:20 — Architect: ловушка по секретам — четыре сервиса (char-attrs, inventory, locations, user-service) получают INTERNAL_SERVICE_TOKEN только из базового compose, поэтому fail-fast в prod-файле нужно прописать всем потребителям, иначе они поедут на публичном дефолте. Приёмка — `docker compose config` без единого вхождения дефолтных значений
[LOG] 2026-09-19 22:30 — Architect: спроектирована 21 задача (2 DevSecOps + 11 backend, идущих параллельно, 5 QA-групп, фронт-проверка, уборка ISSUES.md, ревью), 5 новых/перенесённых маршрутов; миграции и новые разрешения не нужны. Статус → IN_PROGRESS
[LOG] 2026-09-19 23:05 — Backend Dev: начал задачи #10, #12, #13 (battle, battle-pass, dungeon, autobattle)
[LOG] 2026-09-19 23:20 — Backend Dev: battle-service — в inventory_client.py добавлен модуль-локальный _internal_token_headers() (импорт из main циклический), заголовок на consume_item и update-durability, get_fast_slots переведён на /inventory/internal/characters/{id}/fast_slots; в main.py заголовок на add_rewards и party/internal/xp-bonus
[LOG] 2026-09-19 23:25 — Backend Dev: найден пробел в матрице §3.4 — три вызова /party/internal/active-members из battle-service (main.py:988, :1168, :3709) и один из dungeon-service (http_clients.py:63) в матрице не перечислены, хотя §3.1 закрывает этот маршрут. Заголовок добавлен на все четыре, иначе групповой PvE/PvP и подземелья молча остались бы без отряда
[LOG] 2026-09-19 23:30 — Backend Dev: battle-pass (crud.py add_rewards) и dungeon (http_clients.py add_gold) шлют X-Internal-Token через существующие хелперы; в dungeon tests/test_internal_headers.py расширен список GATED (/add_rewards, /party/internal/active-members)
[LOG] 2026-09-19 23:35 — Backend Dev: autobattle — добавлен clients.internal_token_headers(), заголовок на /battles/internal/{id}/state и /action. Маршруты пока токен не проверяют, заголовок инертен; переменной у сервиса ещё нет — уходит пустое значение, поведение как раньше
[LOG] 2026-09-19 23:45 — Backend Dev: задачи #10, #12, #13 завершены — py_compile OK, pytest в Docker: battle 706 passed / 4 skipped, battle-pass 119 passed, dungeon exit 0 (132), autobattle 126 passed. Обновлены docs/services/battle-service.md и autobattle-service.md
[LOG] 2026-09-19 23:10 — Backend Dev: задачи #6, #8, #11 (party / locations / notification) — начал
[LOG] 2026-09-19 23:25 — Backend Dev: party-service — создан app/internal_auth.py (verify_internal_token + internal_token_headers в одном leaf-модуле), закрыт весь префикс /party/internal/, crud.settle_regen шлёт заголовок; циклического импорта нет
[LOG] 2026-09-19 23:40 — Backend Dev: locations-service — маршрут прогресса квеста пришлось объявить ниже verify_internal_token (декоратор выполняется на импорте, иначе NameError); выбор в диалоге НПС — JWT без проверки владения по §3.1
[LOG] 2026-09-19 23:45 — Backend Dev: пробел в §3.4 — у GET /party/internal/active-members не было ни одной строки вызывающих, а locations-service зовёт его в crud.py:7119 (best-effort, вернул бы пустой отряд молча). Заголовок добавлен; сплошной свип locations по всем закрываемым маршрутам других пропусков не нашёл
[LOG] 2026-09-19 23:55 — Backend Dev: notification-service — добавлен локальный internal_token_headers(), вызов переведён на /users/internal/{uid}/activity/increment, except: pass заменён на logger.warning
[LOG] 2026-09-20 00:05 — Backend Dev: проверки в Docker — py_compile по всем изменённым файлам OK; pytest: party 47 passed, locations 1250 passed, notification 236 passed. Обновлены docs/services/locations-service.md и notification-service.md (у party-service файла документации нет, дизайн его не требует)
[LOG] 2026-09-20 00:10 — DevSecOps: начал задачи 1 и 2 (compose, .env.example, nginx); код сервисов не трогаю — параллельно работают backend-разработчики
[LOG] 2026-09-20 00:20 — DevSecOps: JWT_SECRET_KEY переведён на строгую форму ${JWT_SECRET_KEY} — литерал your-secret-key больше не встречается в репозитории ни разу
[LOG] 2026-09-20 00:30 — DevSecOps: в docker-compose.prod.yml строгая форма ${INTERNAL_SERVICE_TOKEN:?...} проставлена ВСЕМ 13 потребителям, включая четыре (char-attrs, inventory, locations, user-service), которые получали переменную только из базового файла — иначе они уехали бы в прод на публичном dev-токене
[LOG] 2026-09-20 00:35 — DevSecOps: INTERNAL_SERVICE_TOKEN добавлен в оба compose-файла для user-service, notification-service и autobattle-service (раньше переменной у них не было вовсе)
[LOG] 2026-09-20 00:45 — DevSecOps: приёмка эмпирическая, не «по рассуждению». Слияние конфигов проверено: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` — посервисный diff окружения до/после даёт ровно три добавленных ключа и ни одной потери (environment в prod-файле действительно мержится, а не заменяет базовый). С обоими секретами в .env — ноль вхождений dev-internal-token-change-me и your-secret-key; с пустым .env prod-конфиг падает с «required variable INTERNAL_SERVICE_TOKEN is missing a value», а dev-конфиг поднимается с fallback'ом, как и задумано
[LOG] 2026-09-20 00:55 — DevSecOps: nginx — в обоих конфигах добавлены `location /skills/internal/ { return 403; }` и `location = /skills/ { limit_except GET HEAD }`. `nginx -t` зелёный на обоих. Маршрутизация проверена живьём (nginx во временном контейнере + заглушки апстримов): POST /skills/ → 403, GET/HEAD /skills/ → 200, /skills/internal/... → 403, при этом /skills/1, /skills/1/resolved, /skills/assign_multiple, /skills/admin/... и DELETE /skills/character_skills/... не задеты. Новые/перенесённые пути (inventory/internal/.../fast_slots, users/internal/.../activity/increment, locations/quests/internal/..., party/internal/*, characters/{id}/add_rewards) уже отдают 403 существующими правилами — в обоих конфигах результат идентичен
[LOG] 2026-09-20 01:00 — DevSecOps: задачи 1 и 2 закрыты. Осознанно НЕ трогал: services/user-service/auth.py (это задача backend-разработчика №9) и заметку о деплое в docs/ARCHITECTURE.md; docs/ISSUES.md (задача 20) сейчас правится параллельно, вернусь к ней отдельно
[LOG] 2026-09-19 22:45 — Backend Dev: задачи #5/#7/#9 — character-service: add_rewards закрыт verify_internal_token, исходящие вызовы reconcile-perks и обоих маршрутов навыков получили X-Internal-Token
[LOG] 2026-09-19 22:55 — Backend Dev: skills-service — добавлен стандартный header-based verify_internal_token в auth_http.py (allow_jwt_or_service_token НЕ трогал: один секрет в двух позициях заголовка недопустим); assign_multiple разложен на internal-двойника и публичный путь под require_permission("skills:create"), новых разрешений не требуется; legacy POST /skills/ закрыт internal-токеном
[LOG] 2026-09-19 23:05 — Backend Dev: user-service — механизма internal-токена не было вовсе, добавил verify_internal_token в auth.py; activity/increment переехал на /users/internal/{uid}/activity/increment, старый путь удалён (404), points теперь Field(1, ge=1, le=100)
[LOG] 2026-09-19 23:15 — Backend Dev: обновил существующие тесты character-service (add_rewards теперь с заголовком в 4 файлах, стаб httpx принимает headers); py_compile и полный pytest в Docker зелёные: character 1054 passed, skills 219 passed, user 518 passed
[LOG] 2026-09-20 01:10 — Backend Dev: по просьбе PM закрыл сервисную половину задачи #1 — services/user-service/auth.py: вместо голого KeyError теперь RuntimeError по-русски с подсказкой `openssl rand -hex 32`, и проверяется пустая строка (в compose незаданная переменная разворачивается в JWT_SECRET_KEY= , то есть ключ «есть»). Обновил test_jwt_secret.py (ожидание RuntimeError) и добавил тест на пустую строку; user-service: 519 passed, 5 skipped
[LOG] 2026-09-19 23:20 — Backend Dev: внимание другим разработчикам — notification-service (задача #11) обязан перейти на POST /users/internal/{uid}/activity/increment, иначе 404; старый путь удалён
[LOG] 2026-09-19 23:10 — Backend Dev (inventory/char-attrs): задачи #3 и #4 — пояс разложен на игровой (JWT + verify_character_ownership) и internal-двойник GET /inventory/internal/characters/{cid}/fast_slots через общий _get_fast_slots_core
[LOG] 2026-09-19 23:15 — Backend Dev (inventory/char-attrs): verify_internal_token навешан на 5 маршрутов inventory (revalidate-equipment, consume_item, free_slots_check, gathering/award, update-durability) и 3 маршрута char-attrs (settle-regen, satiety, reconcile-perks); внутрипроцессные вызовы reconcile_perks не тронуты
[LOG] 2026-09-19 23:20 — Backend Dev (inventory/char-attrs): исходящие вызовы inventory (satiety, reconcile-perks sync и async) теперь шлют X-Internal-Token через существующий _internal_token_headers()
[LOG] 2026-09-19 23:35 — Backend Dev (inventory/char-attrs): обновлены существующие тесты (6 файлов inventory + test_satiety.py), снят xfail с test_fast_slots_requires_auth; pytest в Docker с примонтированным репозиторием: inventory 1301 passed, char-attrs 425 passed / 2 skipped (1 xpass — предсуществующий баг роутинга /attributes/admin/perks). py_compile OK, docs обоих сервисов обновлены
[LOG] 2026-09-20 01:20 — QA: начал задачи #14–#18, пять групп параллельно. До написания тестов сделал собственный сплошной свип вызывающих по всем закрываемым маршрутам (13 сервисов + фронтенд, `.py`/`.ts`/`.tsx`)
[LOG] 2026-09-20 01:25 — QA: свип подтвердил — ни одного вызывающего без заголовка и ни одного застрявшего на старом пути. Пробел §3.4 по `GET /party/internal/active-members` (пять вызывающих, ни одного в матрице) подтверждён независимо: battle `main.py:990, :1171, :3713`, dungeon `http_clients.py:63`, locations `crud.py:7122` — все уже исправлены разработчиками
[LOG] 2026-09-20 02:10 — QA: inventory — 59 тестов матрицы на 6 маршрутов gate I + двойник пояса, игровой пояс 401/403/404/200, xfail снят и тест проходит по существу; закрыт пробел по `update-durability` (19 тестов, раньше ноль HTTP-покрытия)
[LOG] 2026-09-20 02:20 — QA: char-attrs — закрыт второй пробел из §2.4: у `reconcile-perks` не было ни одного HTTP-теста. Добавлены реальные сценарии выдачи и отзыва перка вместе с бонусом; каждый отказ сверяется со снимком БД, чтобы страж, который пишет до 401, не проскочил
[LOG] 2026-09-20 02:35 — QA: по требованию §3.4 все проверки исходящих сделаны на реальных клиентских функциях со значением заголовка (`call.kwargs["headers"]["X-Internal-Token"]`), плюс два негативных контроля: при подменённом хелпере вызов всё равно происходит — то есть тест на «ничего не упало» такую потерю не увидит
[LOG] 2026-09-20 02:50 — QA: найдена слабость в самом шаблоне свипа, унаследованном из FEAT-167: фиксированное окно в 900 символов перетекает в следующую функцию и видит её хелпер, поэтому свип остаётся зелёным при потерянном заголовке. Во всех новых свипах окно режется по первой пустой строке; исправлено по факту демонстрации на autobattle
[LOG] 2026-09-20 02:55 — QA: мутационные проверки (удалить заголовок → тест краснеет → файл восстановлен) выполнены на party `crud.settle_regen`, locations `_check_inventory_has_free_slot`, character-service (три правки сразу, 9 падений), battle `get_fast_slots`, battle-pass `_deliver_gold_xp`, autobattle `post_battle_action`
[LOG] 2026-09-20 03:00 — QA: попутно починен флапающий `test_chat.py::TestRateLimiting` (ISSUES ~:224) — незамоканный исходящий вызов из `send_message` съедал двухсекундное окно лимита; добавлен autouse-мок, время `test_chat.py` упало с ~4 с на отправку до 1.14 с на весь файл, запись в ISSUES.md помечена DONE
[LOG] 2026-09-20 03:15 — QA: задачи #14–#18 закрыты. Добавлено ~304 теста. Полные прогоны в Docker с аргументами из ci.yml, CI=true, репозиторий примонтирован — все 12 затронутых сервисов зелёные: inventory 1389, character 1076, locations 1275, battle 727, user 550, char-attrs 465/2 skipped/1 xpassed, skills 253, notification 248, autobattle 133, dungeon 135 (exit 0), battle-pass 124, party 68. Продакшен-код не менялся, багов не найдено
[LOG] 2026-09-20 03:20 — QA: предупреждение ревьюеру — два QA-агента в ходе мутационных проверок восстановили файлы через `git checkout`, что стирало НЕзакоммиченные правки разработчиков; файлы восстановлены вручную и сверены. Диффы `services/party-service/app/crud.py`, `services/character-service/app/crud.py`, `services/battle-service/app/inventory_client.py`, `services/battle-pass-service/app/crud.py`, `services/autobattle-service/app/clients.py` перепроверены мной отдельно и соответствуют задуманному FEAT-169 один в один
[LOG] 2026-09-20 04:00 — Reviewer: начал проверку, статус → REVIEW. Два фокуса по просьбе PM: пять файлов, восстановленных вручную после `git checkout`, и подозрение на беззубые свипы
[LOG] 2026-09-20 04:20 — Reviewer: сделал собственный сплошной свип по каждому закрываемому маршруту (не доверяя ни §3.4, ни свипу QA) — 26 реальных вызывающих, все шлют заголовок, все четыре переехавших URL переписаны. Пропуск §3.4 по `active-members` (пять вызывающих) разработчики уже закрыли
[LOG] 2026-09-20 04:45 — Reviewer: пять восстановленных вручную файлов сверены построчно с §3.3/§3.4 — расхождений нет; самое «теряемое» место (новый URL `internal/assign_multiple` в character-service) на месте
[LOG] 2026-09-20 05:30 — Reviewer: мутационная проверка всех 26 вызовов (убрать заголовок/вернуть старый URL → прогнать сюиту сервиса → восстановить файл побайтово, НЕ через git checkout). **26 из 26 краснеют.** Беззубых стражей нет: у каждого вызова есть поведенческий тест на значение заголовка, а не «ничего не упало». Замечание QA про фиксированное окно верно как долг по качеству тестов, но ни один вызов на нём одном не держится
[LOG] 2026-09-20 05:50 — Reviewer: автоматические проверки зелёные — py_compile 56 файлов, pytest во всех 13 сервисах с аргументами из ci.yml, tsc --noEmit, npm run build, nginx -t на обоих конфигах, слияние prod-конфига (посервисный diff окружения: ни одной потери, ноль дефолтных секретов, с пустым .env prod падает, dev поднимается)
[LOG] 2026-09-20 06:10 — Reviewer: стек пересоздан с реальными секретами (+ пересборка api-gateway: конфиг nginx запечён в образ, обычный recreate его не подхватывает). Матрица через шлюз: все закрытые маршруты 401/403, оба старых пути 404, GET-подпути /skills/ не задеты. Пустой internal-токен → 503 во всех семи сервисах; пустой JWT_SECRET_KEY → RuntimeError; два механизма токена в skills не подменяют друг друга
[LOG] 2026-09-20 06:40 — Reviewer: живые сценарии — полный бой с применением предмета пояса (3→2), награды PvE, опыт отряда, титулы, сбор, проверка свободных слотов, отдых/регенерация, сытость, реконсайл перков, ревалидация экипировки, прогресс квеста, сообщение в чат с начислением активности, выдача пресетов навыков, админский редактор навыков НПС (401/403/200), автобой, золото подземелья. Все внутренние вызовы 200; в логах за всю сессию нет ни одного неожиданного 401/403/503 — тихих отказов нет. Пояс виден в браузере, ошибок в консоли нет
[LOG] 2026-09-20 06:55 — Reviewer: тестовые данные убраны, персонажи восстановлены (бои, Redis, Mongo, инвентарь, перки, здоровье, локация, очки активности, пробный пользователь, сообщение в чате). Рабочее дерево побайтово как до ревью, коммитов нет
[LOG] 2026-09-20 07:00 — Reviewer: проверка завершена, результат FAIL — **не по коду**. Код, безопасность и поведение в рантайме в порядке; не выполнены задача #20 (ISSUES.md: семь закрытых записей всё ещё открыты, общая запись устарела, `GET /attributes/{id}/perks` не вынесён отдельной записью) и документационная половина задачи #1 (заметка о деплое в ARCHITECTURE.md). Задача #19 фактически выполнена — нужен только перевод статуса
[LOG] 2026-09-20 07:05 — Reviewer: попутно найдены предсуществующие проблемы (в ISSUES.md отдельными записями): conftest char-attrs использует setdefault, а три теста FEAT-167 зашивают литерал токена → 16 падений при запуске внутри любого контейнера; dungeon-service не печатает итоговую строку pytest; шаблон свипа с фиксированным окном; в локальной БД нет ни одного предмета-еды
[LOG] 2026-09-20 07:20 — DevSecOps: взял правки по ревью — задача 20 (ISSUES.md) и документационная половина задачи 1; код сервисов по-прежнему не трогаю
[LOG] 2026-09-20 07:35 — DevSecOps: семь записей помечены DONE (FEAT-169) в стиле FEAT-167, с доказательствами, а не просто вычеркнуты: дыра с fast_slots, восемь internal-маршрутов, долг по fallback'у internal-токена, две дыры в skills, activity/increment, две дыры locations, блокер autobattle. В записи 27 (JWT) закрыт остававшийся пункт 3 — с отметкой, что пустая строка теперь тоже считается отсутствующим ключом
[LOG] 2026-09-20 07:45 — DevSecOps: зонтичная запись про «большинство внутренних эндпоинтов защищены только nginx» была уже неправдой — большинство как раз закрыто. Переписал заголовок и добавил таблицу реального остатка по §3.10.3; самое весомое там — четыре маршрута мутации алмазов в user-service
[LOG] 2026-09-20 07:50 — DevSecOps: в той же записи зафиксирована ловушка для следующего захода — `GET /battles/internal/{id}/state` опрашивают двое, и заголовок шлёт только autobattle; dungeon-service (`http_clients.py:377`) не шлёт (проверил код), так что гейтить battles/internal нельзя, не обновив сперва его, иначе опрос боя в подземелье отвалится молча
[LOG] 2026-09-20 07:55 — DevSecOps: `GET /attributes/{cid}/perks` вынесен в собственную запись — запись в БД на GET плюс транзитивные вызовы двух сервисов на анонимной ручке; в записи явно сказано, почему это баг независимо от продуктового решения о публичности чтений (та запись остаётся открытой и помечена как сознательно оставленная)
[LOG] 2026-09-20 08:05 — DevSecOps: в docs/ARCHITECTURE.md добавлен раздел «Секреты и fail-fast»: локальный .env обязан содержать JWT_SECRET_KEY (пустая строка = отсутствует, compose подставляет именно её), прод без INTERNAL_SERVICE_TOKEN не поднимается вовсе — строгая форма `:?` роняет config/ps/down/up для всего стека, а не один контейнер; добавлена команда пре-флайта перед пушем в main. Заодно поправил устаревшую строку в разделе Authentication, где ключ всё ещё описан как захардкоженный `your-secret-key`
[LOG] 2026-09-20 08:10 — DevSecOps: правки по ревью закрыты, задачи 1 и 20 — DONE. Коммитов не делал
[LOG] 2026-09-20 09:30 — Reviewer: ревью #2 (только документация). Кода в этом проходе никто не трогал — построчная сверка `git diff --stat` по всем service/compose/nginx файлам совпадает с ревью #1. Все пять пунктов закрыты: семь записей ISSUES.md вычеркнуты с блоками «Исправлено» (четыре сверил с кодом — совпадают с тем, что я проверял живьём), общая запись сужена до реально оставшихся префиксов с таблицей «маршрут → файл → вызывающие», `GET /attributes/{id}/perks` вынесен отдельной записью, в ARCHITECTURE.md появился раздел «Секреты и fail-fast» и исправлен устаревший пункт про захардкоженный ключ. Мои четыре записи на месте
[LOG] 2026-09-20 09:40 — Reviewer: ловушка с dungeon-service подтверждена независимо — `app/http_clients.py:377` опрашивает `/battles/internal/{id}/state` без заголовка, тогда как autobattle заголовок шлёт. Находка настоящая и описана в обеих записях; в scope FEAT-169 она справедливо не входит
[LOG] 2026-09-20 09:45 — Reviewer: запись про флапающий rate limiting не удалена, а вычеркнута как DONE, при этом вторая половина (блокирующий вызов в горячем пути чата) корректно оставлена открытой — разделение обоснованно, autouse-мок в conftest реальный
[LOG] 2026-09-20 09:50 — Reviewer: задачи #19 и #21 переведены в DONE. Ревью #2 — PASS, фича закрыта. Мелочь без правки: в блоке про fast_slots упомянуты два тестовых файла, которых правка не касалась (HTTP-вызова маршрута там нет)
[LOG] 2026-09-19 09:30 — PM: ревью #2 PASS, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Пояс больше не читается анонимно:** игровой маршрут требует вход и проверяет, что персонаж твой; для сервисов заведён отдельный внутренний маршрут (мобам и NPC владелец не нужен).
- **Закрыты восемь внутренних маршрутов** характеристик и инвентаря, начисление наград, отрядный бонус и список участников отряда — всё по внутреннему токену, nginx вторым слоем.
- **Выдача навыков разделена:** сервису — внутренний маршрут, админке NPC — проверка права `skills:create`. Новых разрешений не заводили.
- **Накрутка активности** переехала под внутренний префикс, старый адрес отдаёт 404; заодно запрещены нулевые и отрицательные значения (раньше можно было списать активность в минус).
- **Обновление прогресса задания** переехало под внутренний префикс; выбор реплики у NPC требует входа (без проверки владения — в запросе нет персонажа, и сам обработчик ничего не выдаёт).
- **Секреты fail-fast:** публичные значения по умолчанию убраны; user-service не стартует без `JWT_SECRET_KEY` (пустая строка считается отсутствием), прод не поднимается без `INTERNAL_SERVICE_TOKEN` ни для одного из 13 сервисов. Автобою переменную добавили заранее.
- **Обновлены 26 мест вызова** в десяти сервисах; все проверены «от противного» — убирали заголовок и убеждались, что тест падает. 26 из 26 пойманы.
- Около 300 новых тестов, все 13 сервисов зелёные.

### Что изменилось от первоначального плана
- В задачу добавлены пять дыр, найденных при разборе, включая две серьёзные с выдачей навыков.
- Список вызывающих в плане оказался неполным: у списка участников отряда было пять вызывающих и ни одного в таблице. Нашли независимыми проверками.
- Анонимное чтение чужих данных сознательно оставлено на потом: нужно решать, что вообще публично.

### Найдено попутно (в ISSUES.md)
- Подземелья опрашивают состояние боя без токена, а автобой уже подготовлен: если закрыть этот маршрут, подземелья молча сломаются. Записано дважды, чтобы не пропустили.
- `GET /attributes/{id}/perks` пишет в базу на чтение и анонимно дёргает два сервиса — выделено в отдельную запись.
- 16 тестов сервиса характеристик падают при запуске внутри контейнера (в CI зелено).
- Шаблон теста-«сторожа» из прошлой задачи мог пропускать потерю заголовка; новые сторожа исправлены.
- Плавающий тест чата починен: причина была в незамоканном вызове активности.

### Оставшиеся риски / follow-up задачи
- **Перед пушем:** на проде должны быть оба секрета (проверены 2026-09-19). Без `INTERNAL_SERVICE_TOKEN` прод-конфиг не выполнится вообще, включая `down`.
- Остальные внутренние префиксы (бои, подземелья, боевой пропуск, локации, алмазы) — следующий заход, начинать с заголовка в подземельях.
- Анонимное чтение чужих данных — отдельная задача с продуктовым решением.
