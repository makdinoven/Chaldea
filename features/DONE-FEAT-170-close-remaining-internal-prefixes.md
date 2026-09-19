# FEAT-170: Закрыть оставшиеся internal-префиксы (bat­tles, dungeons, battle-pass, locations, users/diamonds)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-19 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-170-slug.md` → `DONE-FEAT-170-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Завершение работы, начатой в DONE-FEAT-167 и DONE-FEAT-169. Те задачи закрыли выдачу предметов и навыков, изменяющие эндпоинты характеристик, пояс, начисление наград, отрядный бонус, накрутку статистики и активности, а также убрали публичные значения секретов. Остались internal-префиксы, которые держатся **только на правиле nginx**: `/battles/internal/*`, `/dungeons/internal/*`, `/battle-pass/internal/*`, оставшиеся `/locations/internal/*` и `/locations/quests/internal/*`, `/users/internal/*` (включая алмазы и косметику), `/autobattle/internal/register`.

Актуальный перечень и вызывающие — в записи «Долг: оставшиеся internal-префиксы …» в `docs/ISSUES.md` (сужена после FEAT-169).

Снаружи они закрыты gateway'ем, порты сервисов на проде наружу не открыты — поэтому это долг, а не авария. Но защита должна быть в самом сервисе: ошибка в ingress или доступ внутрь сети контейнеров открывает начисление алмазов, изменение состояния боя, выдачу косметики и прочее.

### Бизнес-правила
- На каждый оставшийся internal-маршрут — `Depends(verify_internal_token)` по образцу FEAT-167/169: пустой токен → 503, отсутствующий или чужой → 401, тексты по-русски. nginx остаётся вторым слоем.
- **Начинать с вызывающих, а не с маршрутов.** Известная ловушка: `dungeon-service/app/http_clients.py:377` опрашивает `GET /battles/internal/{id}/state` **без заголовка**, тогда как autobattle-service для этого же маршрута уже подготовлен. Если закрыть маршрут раньше, подземелья сломаются молча. Сначала заголовки у всех вызывающих, потом проверки на маршрутах.
- Особое внимание `/users/internal/*diamonds*` и косметике: это валюта и покупки, самый весомый остаток.
- Все вызывающие обновить синхронно; там, где вызов «отправил и забыл» (ошибка проглатывается), тест обязан проверять сам факт отправки заголовка, а не «ничего не упало».
- Ничего не должно тихо деградировать: бой, автобой, подземелья, боевой пропуск, задания, сбор, покупки за алмазы, косметика.
- Если какой-то маршрут на самом деле вызывается с фронтенда — его нельзя просто закрыть токеном, нужен отдельный игровой путь (как было с поясом в FEAT-169). Проверить каждый.

### UX / Пользовательский сценарий
1. Игрок играет как обычно: бой, автобой, подземелье, боевой пропуск, задания, покупки — ничего не сломалось.
2. Ни один internal-маршрут не отвечает на запрос без токена, даже если запрос пришёл изнутри сети контейнеров.

### Edge Cases
- Бои и подземелья, идущие в момент деплоя (их опрашивают по внутренним маршрутам).
- Автобой: он уже шлёт заголовок, но переменная у него появилась только в FEAT-169 — проверить, что она реально доезжает.
- Маршруты, которые вызываются из нескольких сервисов с разной готовностью.
- Celery-задачи и фоновые процессы, если они ходят по этим маршрутам.

### Вопросы к пользователю (если есть)
- [x] Делаем сейчас, после FEAT-169 → да
- [ ] Что-то из этих маршрутов должно остаться доступным игроку (а не только сервисам)? → выяснить по коду, спросить при находке

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline: clean tree at `15e522b` (FEAT-164..169 shipped to prod). The route inventory below was
**rebuilt from source with an AST sweep over every `@app`/`@router` decorator in `services/`**, not
copied from `docs/ISSUES.md` — that list is a 2026-09-14 snapshot and is both stale and incomplete
(it misses `GET /locations/quests/internal/completed-count` and the read-only
`GET /locations/internal/action-gate`, and still names routes FEAT-169 already closed). Every claim
below carries `file:line`.

### 2.0. Reuse, do not reinvent

| Piece | Canonical location |
|---|---|
| Fail-closed incoming `verify_internal_token` (empty env → 503, missing/wrong → 401, Russian `detail`) | `character-service/app/auth_http.py:81`; copies in char-attrs `auth_http.py:81`, inventory `auth_http.py:69`, skills `auth_http.py:87`, user-service `auth.py:104`, locations `main.py:3743`, party `internal_auth.py:23` |
| Outgoing `_internal_token_headers()` | battle `main.py:65`, battle `inventory_client.py:10`, dungeon `http_clients.py:26`, battle-pass `crud.py:25`, inventory `main.py:28`, locations `main.py:3734` + `crud.py:26`, char-attrs `main.py:30`, autobattle `clients.py:13`, party `internal_auth.py:41` |
| Internal twin split (when a browser also calls the route) | `inventory-service/app/main.py:467` vs `:481`; `:1328` vs the player `fast_slots` |
| Leaf module to dodge an import cycle | `party-service/app/internal_auth.py` (FEAT-169 M1) |
| nginx second layer | `location /…/internal/ { return 403; }` |

**No frontend change is expected this time.** A full sweep of `services/frontend/app-chaldea/src`
(`.ts`/`.tsx`/`.js`/`.jsx`) finds **zero** requests to any `*/internal/*` path — the only hits are
`InternalAxiosRequestConfig`, `internal_district_id` and prose in comments. The browser's
look-alikes go to **public twins that already exist and are JWT-gated**:
`GET /battles/{id}/state` (`battle-service/app/main.py:1443`), `POST /battles/{id}/action` (`:3505`),
`GET /locations/action-gate/status` (`LocationPage.tsx:388`), and
`POST /autobattle/{register,unregister,speed,mode}` (`autobattle-service/app/main.py:102, :156, :170, :94`
— all `Depends(get_current_user_via_http)`, `/register` additionally verifies character ownership at
`:104-116`). So, unlike FEAT-169's belt, **no player path needs carving out** — subject to the
Architect re-confirming the "dead" routes in §2.6.

---

### 2.1. Complete route inventory

37 routes live under an `internal` path segment. **20 are already gated** (FEAT-162/167/169).
**17 are gated by nginx only** — that is this feature's exact scope. Severity assumes an attacker
inside the compose network, or an ingress mistake.

#### Still open (17) — the scope

| # | Route | file:line | What it does | Severity |
|---|---|---|---|---|
| 1 | `POST /users/internal/{uid}/diamonds/add` | `user-service/main.py:1708` | mints premium currency, unbounded (only `amount > 0`) | **CRITICAL** — currency |
| 2 | `POST /users/internal/{uid}/diamonds/spend` | `user-service/main.py:1729` | burns premium currency | **CRITICAL** — currency; **no caller today** |
| 3 | `POST /users/internal/{uid}/cosmetics/unlock` | `user-service/main.py:2153` | grants frames / chat backgrounds | **HIGH** — purchasable goods |
| 4 | `POST /battles/internal/{bid}/action` | `battle-service/app/main.py:1432` | `_make_action_core(..., skip_ownership=True)` — **acts as any participant in any battle** | **CRITICAL** — battle-state mutation, ownership deliberately bypassed |
| 5 | `GET /battles/internal/{bid}/state` | `battle-service/app/main.py:1377` | full state: every participant's HP/mana/cooldowns/belt/**rewards** | **HIGH** — full info leak on any live battle |
| 6 | `POST /battles/internal/party/leave-on-move` | `battle-service/app/main.py:6368` | removes a character from a pre-battle party (leader ⇒ disband) | MEDIUM — griefing |
| 7 | `POST /dungeons/internal/battle-callback` | `dungeon-service/app/main.py:746` | marks a room cleared, applies casualties, advances the session | **HIGH** — dungeon-state mutation; **no caller today** |
| 8 | `GET /dungeons/internal/character-session/{cid}` | `dungeon-service/app/main.py:730` | is this character in a dungeon | LOW; **no caller today** |
| 9 | `POST /autobattle/internal/register` | `autobattle-service/app/main.py:136` | registers a participant into the AI driver **with no ownership check** (the public twin at `:102` has one) | **HIGH** — drives another player's turns |
| 10 | `POST /battle-pass/internal/track-event` | `battle-pass-service/app/main.py:295` | credits battle-pass progress (location visits) | MEDIUM — progression ⇒ rewards |
| 11 | `POST /locations/quests/internal/auto-progress` | `locations-service/app/main.py:3195` | advances any objective of any character's quest; completion pays out | **HIGH** — rewards |
| 12 | `POST /locations/internal/action-gate/consume` | `locations-service/app/main.py:3698` | burns a limited combat/pvp/dungeon action gate | MEDIUM — can drain a player's attempts |
| 13 | `GET /locations/internal/action-gate` | `locations-service/app/main.py:3685` | reads gate state | LOW; **no caller today** |
| 14 | `POST /locations/internal/gathering-status` | `locations-service/app/main.py:3674` | which of these characters are gathering | LOW (read) |
| 15 | `GET /locations/quests/internal/check-completed` | `locations-service/app/main.py:3150` | has character completed quest X | LOW (read) |
| 16 | `GET /locations/quests/internal/completed-count` | `locations-service/app/main.py:3172` | completed-quest count | LOW (read); **no caller today** |
| 17 | `GET /users/internal/{uid}/diamonds` | `user-service/main.py:1696` | reads a diamond balance | LOW (read); **no caller today** |

#### Already gated — touch nothing

`character-service/app/main.py` all 14 under `/characters/internal/` (`:1053, :1299, :1871, :2111,
:3157, :3478, :3537, :3556, :3580, :3619, :3643, :3700, :3775, :3969`); char-attrs `:438, :462, :1430`;
inventory `:467, :753, :1328, :1690, :1767, :1796, :1821, :1855, :3774`; locations `:3762, :3810, :3845`;
party `:129, :181`; skills `:604`; user-service `main.py:1658`.

---

### 2.2. Caller matrix — one row per call site, each hit read individually

**FEAT-169's design matrix was wrong twice**, so this one was produced mechanically: every literal
path fragment grepped across `*.py`, `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.sh`, `*.sql`, `*.yml` in
`services/`, `docker/` and the repo root, then every hit opened. **18 call sites in 6 services.**

| Target route | Caller | file:line | Header today? | Helper in that module? | Error handling |
|---|---|---|---|---|---|
| `/autobattle/internal/register` | battle-service, PvE battle creation | `battle-service/app/main.py:799` | **no** | yes, `main.py:65` | **swallowed** — non-200 → `logger.warning`, `RequestError` → `logger.error`, wrapped in a second `except Exception` |
| `/battles/internal/{id}/state` | autobattle `get_battle_state` | `autobattle-service/app/clients.py:27` | **yes** (FEAT-169, pre-emptive) | yes, `clients.py:13` | raises |
| `/battles/internal/{id}/state` | **dungeon-service polling loop** | `dungeon-service/app/http_clients.py:377` | **no** ← the §1 trap, confirmed | yes, `http_clients.py:26` (used at `:404`, not here) | **raises** 502/503 → the dungeon run aborts loudly |
| `/battles/internal/{id}/action` | autobattle `post_battle_action` | `autobattle-service/app/clients.py:38` | **yes** | yes | raises |
| `/battles/internal/party/leave-on-move` | locations, `move` | `locations-service/app/main.py:1372` | **no** | yes, `main.py:3734` | **swallowed** (`except Exception: pass`) |
| `/battles/internal/party/leave-on-move` | locations, quick-move | `locations-service/app/main.py:1588` | **no** | yes | **swallowed** (`except Exception: pass`) |
| `/battles/internal/party/leave-on-move` | locations, registration move | `locations-service/app/main.py:3894` | **no** | yes | **swallowed** (`logger.warning`, `party_pruned=False`) |
| `/battle-pass/internal/track-event` | locations, `move` | `locations-service/app/main.py:1355` | **no** | yes | **swallowed** (`except Exception: pass`) |
| `/battle-pass/internal/track-event` | locations, `move_and_post` | `locations-service/app/main.py:1619` | **no** | yes | **swallowed** (`except Exception: pass`) |
| `/locations/quests/internal/auto-progress` | battle-service, per defeated enemy | `battle-service/app/main.py:696` (POST at `:725`) | **no** | yes | **swallowed** (`logger.warning`) |
| `/locations/quests/internal/auto-progress` | inventory, gather/collect | `inventory-service/app/main.py:454` | **no** | yes, `main.py:28` | **swallowed** (`logger.warning`) |
| `/locations/quests/internal/check-completed` | char-attrs perk evaluator | `character-attributes-service/app/perk_evaluator.py:85` | **no** | **no — and importing `main`'s helper is a cycle** (§2.4) | **swallowed** (`logger.warning`, returns `False` ⇒ perks silently stop unlocking) |
| `/locations/internal/action-gate/consume` | battle-service combat gate | `battle-service/app/main.py:902` | **no** | yes | **swallowed** → returns `False` ⇒ **attack refused** (fails closed, player-visible) |
| `/locations/internal/action-gate/consume` | battle-service PvP gate | `battle-service/app/main.py:1239` | **no** | yes | **swallowed** → `False` ⇒ PvP refused |
| `/locations/internal/action-gate/consume` | dungeon entry gate | `dungeon-service/app/http_clients.py:81` | **no** | yes, `:26` | **swallowed** → `False` ⇒ **dungeon entry refused** |
| `/locations/internal/gathering-status` | battle-service party start | `battle-service/app/main.py:1025` | **no** | yes | **swallowed** → empty set ⇒ gatherers get pulled into fights |
| `/locations/internal/gathering-status` | battle-service party start (2nd flow) | `battle-service/app/main.py:1192` | **no** | yes | **swallowed**, same |
| `/locations/internal/gathering-status` | battle-service `_drop_busy` | `battle-service/app/main.py:3731` | **no** | yes | **swallowed**, same |
| `/users/internal/{uid}/diamonds/add` | battle-pass `_deliver_diamonds` | `battle-pass-service/app/crud.py:580` | **no** | yes, `crud.py:25` | **re-raises** — a claim would 500 |
| `/users/internal/{uid}/cosmetics/unlock` | battle-pass `_deliver_cosmetic` | `battle-pass-service/app/crud.py:594` | **no** | yes, `crud.py:25` | **re-raises** |

**15 of the 18 call sites swallow their error.** A forgotten header therefore degrades silently in
almost every case: quest progress stops, battle-pass progress stops, perks stop unlocking, gatherers
get dragged into battles, mobs stop being driven by the AI. Per §1, QA must assert **the header
itself** on the real client function (`call.kwargs["headers"]["X-Internal-Token"]`), never "nothing
blew up". The three that do not swallow (dungeon polling, the two battle-pass deliveries) fail
loudly and are the deploy-window risk in §2.7.

**Callers outside `services/`: none.** No script, seed, SQL file, compose file or CI step calls an
internal route.

**Celery: not a caller.** `battle-service/app/tasks.py` has exactly one task (`save_log`, `:11`) and
it only writes to Mongo; no `beat_schedule` is defined anywhere, so `celery-beat` schedules nothing.
See §2.5 for the (harmless) env gap.

---

### 2.3. Services needing new machinery

| Service | Incoming `verify_internal_token`? | Outgoing helper? | Action |
|---|---|---|---|
| user-service | **yes** (`auth.py:104`, already used at `main.py:1662`) | n/a | add the dep to routes #1, #2, #3, #17 — one line each |
| locations-service | **yes** (`main.py:3743`) but **defined below the routes to gate** | yes (`main.py:3734`, `crud.py:26`) | hoist the definition above line 3150 (§2.4) |
| battle-service | **no** | yes (`main.py:65`) | add `verify_internal_token` to `app/auth_http.py` (leaf module: imports only `os/requests/httpx/fastapi/pydantic`, no cycle) |
| dungeon-service | **no** | yes (`http_clients.py:26`) | same, `app/auth_http.py` |
| battle-pass-service | **no** | yes (`crud.py:25`) | same, `app/auth_http.py`; its `config.Settings` has **no** `INTERNAL_SERVICE_TOKEN` field — read `os.environ` at call time, as `crud.py:25` already does |
| autobattle-service | **no** | yes (`clients.py:13`) | same, `app/auth_http.py` |
| char-attrs `perk_evaluator.py` | n/a | **no** | build headers locally from `config.settings.INTERNAL_SERVICE_TOKEN` (`config.py:19`) — do **not** import from `main` |

### 2.4. Import traps (FEAT-169 hit two; there are two here)

1. **locations-service definition order.** `verify_internal_token` is defined at `main.py:3743`, but
   routes #11–#16 live at `:3150`–`:3698`. `Depends(...)` in a signature default (or in
   `dependencies=[...]`) is evaluated **at import time**, so gating them where they stand raises
   `NameError` at container start — the service would not boot. FEAT-169 already hit this and worked
   around it by moving the *route* down (`main.py:3139` NOTE, `docs/ISSUES.md:197`). Six routes
   cannot all be relocated; the clean fix is to hoist `INTERNAL_SERVICE_TOKEN` +
   `_internal_token_headers` + `verify_internal_token` to the top of `main.py`, or into a leaf
   `internal_auth.py` (the party-service M1 shape). **Caution:** locations' helper reads a
   module-level constant captured at import (`main.py:3729`), and
   `locations-service/app/tests/test_internal_auth.py` / `test_internal_headers.py` monkeypatch
   `main.INTERNAL_SERVICE_TOKEN` — the name must stay reachable as `main.INTERNAL_SERVICE_TOKEN`.
2. **char-attrs `perk_evaluator.py`.** `main.py` imports `perk_evaluator` **lazily**
   (`main.py:342, :694, :1410, :1446`, plus `crud.py:729`, `regen.py:336`) precisely because a
   top-level import would cycle. `from main import _internal_token_headers` re-creates that cycle.
   Build the header from `config.settings` in place.

No other cycle risk: every other target module already imports its service's `config` / `auth_http`.

### 2.5. Does `INTERNAL_SERVICE_TOKEN` actually reach every service?

Verified by parsing both compose files block by block.

- **dev `docker-compose.yml`** — present for 13 services: `celery-worker:135`, `user-service:256`,
  `character-attributes-service:316`, `skills-service:343`, `inventory-service:371`,
  `character-service:403`, `locations-service:434`, `notification-service:461`, `battle-service:500`,
  `autobattle-service:532`, `battle-pass-service:563`, `dungeon-service:595`, `party-service:626` —
  all with the deliberate dev fallback `${INTERNAL_SERVICE_TOKEN:-dev-internal-token-change-me}`.
- **prod `docker-compose.prod.yml`** — the same 13 (`:106, :120, :134, :143, :156, :177, :193, :208,
  :233, :248, :267, :283, :297`), all in the strict `${INTERNAL_SERVICE_TOKEN:?…}` form from
  FEAT-169. Environment blocks **merge** with the base file (proven empirically in FEAT-169), so
  nothing is lost.
- **Every service this feature touches already has the variable in both files** — battle,
  dungeon, battle-pass, autobattle, locations, user, char-attrs, inventory. **No compose change is
  required.** `.env.example:40` documents the variable and `:37` the prod `:?` behaviour.
- Two benign gaps: **`celery-beat` has it in neither file** (no `beat_schedule`, no HTTP calls) and
  **photo-service has it in neither** (calls no internal route). Worth one comment line, not a
  change — but a future beat task hitting an internal route would 401 silently.

### 2.6. Routes with no caller at all — a decision is needed

Six of the seventeen are called from **nowhere** in the repo (no service, no frontend, no test, no
script): #2 `diamonds/spend`, #17 `GET diamonds`, #7 `dungeons/internal/battle-callback`,
#8 `dungeons/internal/character-session`, #13 `GET /locations/internal/action-gate`,
#16 `/locations/quests/internal/completed-count`. Two are weighty: `diamonds/spend` moves currency,
and `battle-callback` mutates dungeon session state — its own docstring calls it a "backup to
polling", and the polling path (`http_clients.py:377`) is the one actually in use.

FEAT-169's precedent for exactly this situation (`POST /locations/quests/progress/update`) was
**"close, do not delete"**, which is the safe default here too. See §2.8 for the PM question.

### 2.7. Risks

| Risk | Detail | Mitigation |
|---|---|---|
| **In-flight dungeons at deploy** | `dungeon-service/app/http_clients.py:377` polls `GET /battles/internal/{id}/state` in the gameplay loop and **raises** 502/503. If battle-service redeploys with the gate before dungeon-service has the header, every running dungeon run aborts with a user-visible error. | Callers ship first; deploy is one `docker compose up --build -d` over the whole stack, so the window is seconds — but ordering still matters if a build fails halfway. |
| **In-flight battles at deploy** | autobattle already sends the header (FEAT-169) and the browser uses the public twins, so player turns survive. `battle-service/app/main.py:799` (autobattle register) is swallowed — a missed header means **mobs stop taking turns** with only a WARNING. Most likely silent breakage in the whole feature. | Explicit header test on the register call; live check that a PvE mob acts after deploy. |
| **Silent degradation (15/18 sites)** | Quest progress, battle-pass progress, perk unlocking, gathering exclusion all fail to WARNING-and-continue. | Assert the header on the real client function; per-service source sweep (below). |
| **Fails-closed griefing** | The three `action-gate/consume` callers return `False` on error ⇒ **attack, PvP and dungeon entry are refused**. A missed header here is loud and blocks core gameplay. | Header + live smoke: attack a mob, start PvP, enter a dungeon. |
| **Battle-pass claim 500** | `crud.py:580/:594` re-raise. If the reward is marked claimed *before* delivery, a 401 could burn a reward. | Architect to confirm ordering inside `claim_reward`; not to be changed here, but must not regress. |
| **locations `NameError` at start** | §2.4 trap 1 — a wrong edit takes locations-service down entirely on boot. | `py_compile` is not enough; import the module (or run the service's tests, which import `main`). |
| **Toothless sweeps** | Existing source sweeps use an **allowlist** of gated prefixes (`dungeon .../test_internal_headers.py:210`, `battle-pass .../test_internal_headers.py:222`, `autobattle .../test_internal_headers.py:205`) — a new internal target not on the list passes silently. Two carry explicit FEAT-170 to-do markers that **must** be honoured: `inventory-service/app/tests/test_outgoing_internal_headers.py:506` (`_KNOWN_UNGATED_TARGETS = ("/locations/quests/internal/auto-progress",)`) and `battle-pass-service/app/tests/test_internal_headers.py:215` ("…when that sweep happens, add them here"). | Invert the sweeps: *any* URL containing `/internal/` must carry the header, plus a `checked >= N` floor as at `inventory .../test_outgoing_internal_headers.py:601`. Widen the scanned files beyond `main.py`/`crud.py` to `http_clients.py`, `perk_evaluator.py`, `clients.py`, `inventory_client.py`. |
| **nginx** | Not a risk: **all seven prefixes are already blocked in both configs** — `nginx.conf:118, 133, 250, 266, 311, 404, 408, 446, 464, 478, 491, 509` and `nginx.prod.conf:141, 154, 269, 283, 327, 419, 423, 461, 479, 493, 506, 524`. | No nginx edit needed. |
| **DB / Alembic / RBAC** | None. No schema change, no new permission, no migration. | — |

### 2.8. Test coverage — gaps and tests that will need the header

**Tests that call a to-be-gated route in-process and will 401 after the change:**
- `battle-service/app/tests/test_rewards_in_state.py:215, :236, :249` — `client.get("/battles/internal/1/state")`
- `user-service/tests/test_diamonds.py:42, :50, :244, :258` — `GET /users/internal/{id}/diamonds`
- `user-service/tests/test_cosmetics.py:658, :687, :709, :715, :735, :753, :863` — `POST /users/internal/{id}/cosmetics/unlock`
- `autobattle-service/app/tests/test_speed.py:567` — `POST /internal/register`
- Fixture precedent: `user-service/tests/test_activity_increment_internal.py` (FEAT-169); note `:195`,
  a sweep asserting the route lives under `/users/internal/`.

**Caller-side tests that assert a URL and must now also assert the header:**
`locations-service/app/tests/test_bp_tracking.py:244-245` (track-event),
`battle-pass-service/app/tests/test_cosmetic_rewards.py:368` (cosmetics URL),
`battle-service/app/tests/test_pve_rewards.py:600` (autobattle register call).

**Routes with no HTTP test at all today** (worst gaps — a 401 regression would be invisible):
`/battles/internal/{id}/action`, `/battles/internal/party/leave-on-move`,
`/battle-pass/internal/track-event`, both `/dungeons/internal/*`, all three
`/locations/internal/{gathering-status, action-gate, action-gate/consume}`, both
`/locations/quests/internal/{check-completed, completed-count}`,
`/locations/quests/internal/auto-progress`, `/users/internal/{uid}/diamonds/add`,
`/users/internal/{uid}/diamonds/spend`.

**Caller-side header tests that do not exist yet:** of the 18 call sites only 2 are covered
(`autobattle-service/app/tests/test_internal_headers.py:101, :121`). The other 16 need one, and the
15 swallowing sites need the header asserted on the real client function.

**Monkeypatch shape:** where the token is a module-level constant (locations `main.py:3729`,
char-attrs via `settings`), tests must `monkeypatch.setattr(module, "INTERNAL_SERVICE_TOKEN", …)`,
not only `setenv` — the FEAT-162/167 precedent. Where the helper reads `os.environ` at call time
(battle, inventory, battle-pass, dungeon, autobattle), `setenv` suffices.

**Per-service route sweep worth adding** (precedent:
`character-attributes-service/app/tests/test_internal_auth_feat169.py:567`): walk `app.routes` and
assert that **every** route whose path contains `/internal/` carries `verify_internal_token`. That
is the only check that stays true for routes nobody has written yet.

### 2.9. Recommended order of work (callers before routes — §1's rule)

1. **Helpers first:** char-attrs `perk_evaluator` local header builder; new `verify_internal_token`
   in `auth_http.py` of battle, dungeon, battle-pass, autobattle; the locations hoist (§2.4).
2. **All 18 caller call sites** gain `headers=_internal_token_headers()`. Harmless while the routes
   are still open — an ignored header.
3. **Gate the 17 routes**, lowest blast radius first: locations reads → locations mutators →
   battle-pass → dungeon → autobattle → battle → user-service (diamonds/cosmetics last, they are the
   ones whose caller re-raises).
4. **Tests:** fix the 15 in-process tests, add caller-side header tests, invert the source sweeps,
   add the per-service route sweep.
5. **No compose change, no nginx change, no migration.**

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1. Goal and non-goals

**Goal.** Every one of the 17 routes listed in §2.1 gains `Depends(verify_internal_token)`, and every
one of the 18 call sites in §2.2 sends `X-Internal-Token`. After this feature **no route whose path
contains an `internal` segment answers a request without the shared token**, in any of the 13
services. nginx stays as the outer layer; the service becomes the inner one.

**Non-goals — do not do these:**

- **No new endpoint, no changed request/response body, no changed success status code.** This feature
  adds a dependency and a header; the successful behaviour of all 17 routes is byte-identical.
- **No frontend change.** §2.0 proved the browser calls zero `*/internal/*` paths and every
  look-alike has a JWT-gated public twin. If a developer finds a frontend caller, **stop and ask PM**
  — that would be a FEAT-169-belt situation needing a separate player path, not a silent workaround.
- **No route deletion** (§3.9).
- **No compose change, no nginx change, no DB/Alembic migration, no RBAC permission.** §2.5 and §2.7
  verified all four. `INTERNAL_SERVICE_TOKEN` is already in both compose files for all 13 services
  that need it; all seven prefixes are already `return 403` in `nginx.conf` **and**
  `nginx.prod.conf`; no table, column or `permissions` row is involved. **Anyone who opens
  `docker-compose*.yml`, `nginx*.conf`, an Alembic `versions/` file or a `permissions` seed in this
  feature is off-spec.** The only permitted exception is a comment.

### 3.2. Canonical machinery — copy it exactly, do not redesign it

**Incoming guard.** The single source of truth is `character-service/app/auth_http.py:71-95`. Every
new copy must be character-for-character equivalent in behaviour:

```
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")

def verify_internal_token(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> None:
    if not INTERNAL_SERVICE_TOKEN:
        raise HTTPException(503, detail="Internal service token не настроен")
    if not x_internal_token or x_internal_token != INTERNAL_SERVICE_TOKEN:
        raise HTTPException(401, detail="Недействительный internal token")
```

Contract, identical for all 17 routes:

| Condition | Status | `detail` (Russian, exactly this string) |
|---|---|---|
| `INTERNAL_SERVICE_TOKEN` env empty/unset | `503` | `Internal service token не настроен` |
| header absent | `401` | `Недействительный internal token` |
| header present but not equal | `401` | `Недействительный internal token` |
| header equal | route runs unchanged | — |

Fail-closed is deliberate: a missing config must never *disable* the check. The token is compared
with `!=` (the existing precedent) and is **never logged, never echoed in a `detail`, never returned
in a body**.

**Attachment style.** Use `dependencies=[Depends(verify_internal_token)]` in the decorator, not a
signature parameter — it keeps the handler signature (and therefore the response model and every
existing in-process test's call shape) untouched. This is the shape already used at
`locations-service/app/main.py:3760` and `character-service/app/main.py`.

**Outgoing helper.** Each caller module already has `_internal_token_headers()` except the two listed
in §3.6/§2.3. Reuse it; do not add a second one in a module that has one. The call-time env read
(`os.environ.get(...)` inside the function) is the required shape for battle, dungeon, battle-pass,
inventory and autobattle; locations and char-attrs read a module-level constant/`settings` so that
their existing monkeypatch-based tests keep working (§3.5, §3.6).

### 3.3. Per-service machinery placement

| Service | Guard lives in | New file? | Note |
|---|---|---|---|
| user-service | `app/auth.py:104` (exists, already used at `main.py:1662`) | no | import it in `main.py` if not already |
| locations-service | `app/main.py` — **hoisted** (§3.5) | no | must stay reachable as `main.INTERNAL_SERVICE_TOKEN` |
| battle-service | `app/auth_http.py` (leaf: `os`, `requests`, `httpx`, `fastapi`, `pydantic` only) | no | append the block |
| dungeon-service | `app/auth_http.py` (same leaf shape, verified) | no | append |
| battle-pass-service | `app/auth_http.py` | no | `config.Settings` has **no** `INTERNAL_SERVICE_TOKEN` field — read `os.environ` directly, as `crud.py:25` already does. **Do not add the field to `Settings`** (it would change the strict-env behaviour of the whole service). |
| autobattle-service | `app/auth_http.py` | no | append |
| char-attrs `perk_evaluator.py` | n/a (caller only) | no | §3.6 |

Placing the guard in `auth_http.py` for the four services that lack it is the FEAT-169 M1 shape
(`party-service/app/internal_auth.py`): a leaf module imported by `main.py`, so no cycle can form.

### 3.4. Order of work — a hard constraint, not a preference

The analyst's order (§2.9) is binding and is encoded as task dependencies in §4:

```
helpers  →  all 18 caller headers  →  gate the 17 routes  →  tests
```

Adding a header to a caller while the route is still open is a **no-op**: FastAPI ignores an
unknown header. Gating a route before its caller sends the header is **an outage**. Therefore every
route-gating task in §4 declares, as an explicit `Depends On`, the caller task(s) that feed that
route — the mapping is in §3.8.

This ordering matters more than usual here because **15 of the 18 call sites swallow their error**
(§2.2): a missed header does not raise, it degrades. And the three that do *not* swallow
(`action-gate/consume` ×3) **fail closed** — a missed header there refuses attacks, refuses PvP and
refuses dungeon entry, with the player seeing only "not allowed".

### 3.5. Import trap 1 — locations-service must not `NameError` at boot

`INTERNAL_SERVICE_TOKEN` (`main.py:3729`), `_internal_token_headers` (`:3734`) and
`verify_internal_token` (`:3743`) are defined **below** routes #11–#16 (`:3150`–`:3698`). A
`Depends(verify_internal_token)` inside a decorator is evaluated **at import time**, so gating those
six routes where they stand raises `NameError` and the container never starts. FEAT-169 dodged this
by relocating a single route (`main.py:3139` NOTE); six routes cannot all be relocated.

**Decision: hoist, do not relocate routes.** Move the whole three-item block — the constant and both
functions, verbatim, together with its explanatory comment — to the top of
`services/locations-service/app/main.py`, immediately after the imports and the `logger` /
`OAUTH2_SCHEME_OPTIONAL` lines (i.e. before `_track_cumulative_stats` at `:32`). Nothing else moves.

Constraints on the hoist:

1. The names must remain module attributes of `main`: `locations-service/app/tests/test_internal_auth.py`
   and `test_internal_headers.py` do `monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", …)`.
   Hoisting inside the same module preserves this; **moving the block into a new `internal_auth.py`
   does not** and would break those tests. Keep it in `main.py`.
2. `_internal_token_headers` is already *called* from above its current definition
   (`_track_cumulative_stats`, `:43`) — that works because calls resolve at runtime. Hoisting keeps
   that correct and additionally makes the decorators resolvable.
3. Leave a one-line comment at the old location explaining that the block was hoisted for FEAT-170
   so the next reader does not move it back.
4. Verification is **not** `py_compile` — that cannot catch a decorator-time `NameError` ordering
   problem in the way that matters. The task is done only when `main.py` **imports** cleanly
   (running locations-service's own test suite does this, since its tests import `main`).

### 3.6. Import trap 2 — char-attrs `perk_evaluator.py`

`main.py` imports `perk_evaluator` **lazily** (`main.py:342, :694, :1410, :1446`, `crud.py:729`,
`regen.py:336`) specifically because a top-level import cycles. Therefore
`from main import _internal_token_headers` is forbidden.

**Decision:** build the header inside `perk_evaluator.py` from `config.settings`:

```
from config import settings          # already imported lazily inside the fetch helpers
headers = {"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN}
```

`config.py:19` already declares `INTERNAL_SERVICE_TOKEN: str = ""`, and `config` is a leaf (it
imports only `pydantic`), so no cycle. Add a small local `_internal_token_headers()` in
`perk_evaluator.py` for readability and use it at `:85` (`_fetch_quest_completed`). Because the value
comes from a `settings` object captured at import, QA must monkeypatch
`perk_evaluator.settings.INTERNAL_SERVICE_TOKEN` (or the local helper), not only `setenv`.

Note `_fetch_quest_completed` currently calls `httpx.get(url, params=…, timeout=5.0)` — add
`headers=` to that same call; do not restructure the function.

### 3.7. The 18 caller call sites

One mechanical change each: add `headers=_internal_token_headers()` to the existing request call.
**No other edit in these functions** — no retry, no error-handling change, no logging change. The
swallow-vs-raise behaviour stays exactly as it is today; changing it is a separate feature.

| Service (task) | file:line | Target |
|---|---|---|
| battle (T1) | `main.py:799` | `/autobattle/internal/register` |
| battle (T1) | `main.py:725` (url built `:696`) | `/locations/quests/internal/auto-progress` |
| battle (T1) | `main.py:902`, `:1239` | `/locations/internal/action-gate/consume` ×2 |
| battle (T1) | `main.py:1025`, `:1192`, `:3731` | `/locations/internal/gathering-status` ×3 |
| dungeon (T2) | `http_clients.py:377` | `/battles/internal/{id}/state` ← the §1 trap |
| dungeon (T2) | `http_clients.py:81` | `/locations/internal/action-gate/consume` |
| battle-pass (T3) | `crud.py:580`, `:594` | diamonds/add, cosmetics/unlock |
| locations (T5) | `main.py:1372`, `:1588`, `:3894` | `/battles/internal/party/leave-on-move` ×3 |
| locations (T5) | `main.py:1355`, `:1619` | `/battle-pass/internal/track-event` ×2 |
| char-attrs (T6) | `perk_evaluator.py:85` | `/locations/quests/internal/check-completed` |
| inventory (T7) | `main.py:454` | `/locations/quests/internal/auto-progress` |
| autobattle | `clients.py:27`, `:38` | already correct (FEAT-169) — **verify only, no edit** |

`dungeon-service/app/http_clients.py:367 get_battle_state` is the single client function behind
**two** call paths (`gameplay.py:955`, the in-run polling loop, and `main.py:777`) — fixing it once
covers both.

### 3.8. Route gating: blast radius and the caller-task each route waits on

Gated lowest blast radius first. Each gating task may start only once the caller tasks in the right
column are DONE.

| Order | Route(s) | Gating task | Waits on |
|---|---|---|---|
| 1 | locations reads #13 #14 #15 #16 then mutators #11 #12 | T8 | T1, T2, T6, T7 |
| 2 | `/battle-pass/internal/track-event` #10 | T9 | T5 |
| 3 | `/dungeons/internal/*` #7 #8 | T10 | T2 (helper only — no callers exist) |
| 4 | `/autobattle/internal/register` #9 | T11 | T1, T4 |
| 5 | `/battles/internal/*` #4 #5 #6 | T12 | T1, T2, T5 |
| 6 | `/users/internal/*` #1 #2 #3 #17 | T13 | T3 |

user-service goes last on purpose: its two live callers (`battle-pass crud.py:580/:594`) are the only
callers in the system that **re-raise**, so a mistake there is a user-visible 500 on a reward claim.

### 3.9. Six routes with no caller — close, do not delete

#2 `diamonds/spend`, #17 `GET diamonds`, #7 `dungeons/internal/battle-callback`,
#8 `dungeons/internal/character-session`, #13 `GET /locations/internal/action-gate`,
#16 `/locations/quests/internal/completed-count`.

**Decision (PM, consistent with FEAT-169's `POST /locations/quests/progress/update`): gate them,
leave them in place.** Deleting a route is a behaviour change with no security benefit once it is
token-gated, and `battle-callback`'s own docstring calls it a documented backup to the polling path.
Whether `battle-callback` / `character-session` are planned or leftover does not change this
feature's work — either way they are closed now; a later decision to delete them is a separate,
cheap change.

### 3.10. Deploy-safety analysis — what a player mid-run actually sees

CI runs `docker compose down` then `up --build -d` over the **whole stack**. There is therefore **no
mixed-version window**: it is impossible for a gated battle-service to be live while an
un-headered dungeon-service is also live. That removes the §2.7 ordering risk *at deploy time* —
but the callers-before-routes order in §3.4 still stands, because it is also the order that keeps
each intermediate commit shippable if the build fails halfway and only part of the stack comes back.

What **does** survive the restart is state: MySQL rows, Redis battle state, Mongo logs, dungeon
sessions. What does **not** survive is anything in process memory. Per subsystem:

| Subsystem | Survives `down`/`up`? | What the player sees | Caused by this feature? |
|---|---|---|---|
| PvP / PvE battle | **yes** — Redis + MySQL | Reload the page; the battle is still there, still their turn. Public twins `GET /battles/{id}/state`, `POST /battles/{id}/action` are JWT-gated and untouched. | no |
| **Autobattle driver** | **no** — `ALLOWED`, `PID_BATTLE`, `SPEED`, `OWNER` are **in-process dicts** (`autobattle-service/app/main.py:119-126`), not Redis | A mob or auto-played character stops taking turns after any restart until re-registered. **This is pre-existing behaviour on every deploy, not a FEAT-170 regression** — but it makes post-deploy "is the mob acting?" a weak signal, so live verification must create a **new** PvE battle rather than judging an old one. Flag for `docs/ISSUES.md` (§3.14). | no |
| Dungeon run | **yes** — session rows + `session_state` | The run resumes; the polling loop (`gameplay.py:955` → `http_clients.py:377`) restarts and re-polls the battle. After this feature it carries the header, so it resumes cleanly. If the header were missed it would raise 502/503 and abort the run loudly — this is the single loudest failure mode in the feature. | only if T2 is wrong |
| Battle-pass progress | **yes** — DB | Nothing visible. `track-event` is fire-and-forget from locations; a lost event costs one location visit credit. | no |
| Quest auto-progress | **yes** — DB | Nothing visible; a lost event costs one objective tick. | no |
| Diamond / cosmetic claim | **yes** — DB | See §3.11 — a failed claim is retryable, nothing is burned. | no |
| Celery | n/a | `tasks.py:11 save_log` writes Mongo only; no `beat_schedule` exists, so `celery-beat` runs nothing. No internal HTTP call anywhere in Celery. | no |

**Conclusion:** the only player-visible deploy risk introduced by this feature is a missed header on
`dungeon-service/app/http_clients.py:377` (aborted dungeon run) or on one of the three
`action-gate/consume` sites (attack / PvP / dungeon entry refused). Both are covered by mandatory
live verification in T16.

### 3.11. `battle-pass-service/app/crud.py claim_reward` — verified, no defect

Read at `crud.py:618-695`. The order is:

1. validate season status, level reached, premium track (`:630-640`)
2. look up the level, **check `BpUserReward` for an existing claim** (`:653-662`) → `error_conflict`
3. look up the reward row (`:664-673`)
4. **`await deliver_reward(reward, character_id, user_id)`** (`:676`)
5. **then** `db.add(BpUserReward(...))` + `await db.commit()` (`:678-687`)

Delivery happens **before** the claim row is written, and the claim row is the only "already claimed"
marker. `_deliver_diamonds` / `_deliver_cosmetic` re-raise on failure, which propagates out of
`claim_reward` before step 5, so **a 401 during rollout cannot burn a reward** — the claim simply
fails (HTTP 500 to the player, Russian error surfaced by the existing handler) and the same reward
can be claimed again afterwards. **No defect, nothing to fix here.**

Two things that follow, and that T3/T13 must preserve:

- **Do not "improve" this by marking the claim first.** The current order is the safe one.
- `deliver_reward` (`:512`) dispatches to exactly one delivery per reward type, so there is no
  partial-delivery double-grant on retry either.

### 3.12. Test strategy

The inherited tests are not adequate for this feature and the design requires them to be changed,
not merely extended.

**(a) Fix the 15 in-process calls that will start 401ing.** `battle-service .../test_rewards_in_state.py:215, :236, :249`;
`user-service tests/test_diamonds.py:42, :50, :244, :258`; `user-service tests/test_cosmetics.py:658, :687, :709, :715, :735, :753, :863`;
`autobattle .../test_speed.py:567`. Follow `user-service/tests/test_activity_increment_internal.py`
(FEAT-169): set the token and pass the header in the test client call. **Do not** weaken a route to
make a test pass.

**(b) Each of the 17 routes gets a three-case HTTP test** — no header → 401, wrong header → 401,
correct header → the route's normal success. 13 of the 17 have **no HTTP test at all** today, so
these are new. Where the guard reads a module-level constant (locations, and the four new
`auth_http` copies), monkeypatch the module attribute, not only the env var
(`monkeypatch.setattr(module, "INTERNAL_SERVICE_TOKEN", …)`) — the FEAT-162/167 precedent. Add the
503-on-empty-token case at least once per service.

**(c) Caller-side header assertions — on the header, never on "nothing blew up".** Only 2 of the 18
call sites are covered today (`autobattle .../test_internal_headers.py:101, :121`). The remaining 16
each need a test that patches the HTTP client and asserts
`call.kwargs["headers"]["X-Internal-Token"] == <token>`. For the 15 swallowing sites this is the
**only** observable difference — the precedent negative test at
`inventory .../test_outgoing_internal_headers.py:480-487` states this explicitly. Three existing
tests already assert the URL and must now also assert the header:
`locations .../test_bp_tracking.py:244-245`, `battle-pass .../test_cosmetic_rewards.py:368`,
`battle .../test_pve_rewards.py:600`.

**(d) Invert the source sweeps — they are allowlist-based and toothless today.** Required changes:

- `inventory-service/app/tests/test_outgoing_internal_headers.py:506` — delete
  `_KNOWN_UNGATED_TARGETS = ("/locations/quests/internal/auto-progress",)` and its skip branch. That
  marker exists precisely for this feature.
- `battle-pass-service/app/tests/test_internal_headers.py:215-224` — replace the `GATED` allowlist
  (and the docstring exempting diamonds/cosmetics) with the inverted rule; the docstring literally
  says "when that sweep happens, add them here".
- `dungeon .../test_internal_headers.py:210`, `autobattle .../test_internal_headers.py:205` — same
  inversion.
- **The rule after inversion, in every service:** *any* `httpx`/`client`/`requests` call whose
  resolved URL contains `/internal/` **must** pass `headers=`. No allowlist, no exemption list.
- Keep and raise the `checked >= N` floor (precedent
  `inventory .../test_outgoing_internal_headers.py:601`) so a URL refactor cannot silently empty the
  sweep.
- **Widen the scanned files** beyond `main.py`/`crud.py` to every module that makes outgoing calls:
  `http_clients.py` (dungeon), `perk_evaluator.py` (char-attrs), `clients.py` (autobattle),
  `inventory_client.py`, `character_client.py`, `skills_client.py` (battle).

**(e) Per-service `app.routes` sweep — the check that survives us.** Precedent:
`character-attributes-service/app/tests/test_internal_auth_feat169.py:567`. In **every** service
touched here, walk `app.routes` and assert that every route whose `path` contains `/internal/`
carries `verify_internal_token` among its dependencies. This is the only test that stays true for
routes nobody has written yet, and it is what stops FEAT-171 from existing.

**(f) Do not add integration tests that require a live stack.** Cross-service behaviour is covered by
mocked clients; the live check is the Reviewer's job (T16).

### 3.13. Security review of the change itself

| Question | Answer |
|---|---|
| Authentication | Shared-secret header on all 17 routes; nginx `403` stays as the outer layer. Unchanged for public twins (JWT). |
| Authorization | Unchanged. Note #4 `POST /battles/internal/{bid}/action` keeps `skip_ownership=True` **by design** — that is why it must never be reachable without the token; and #9 `autobattle/internal/register` keeps no ownership check, its public twin at `:102` has one. |
| Input validation | Unchanged — no body or param is touched. |
| Rate limiting | Not added. These routes are unreachable from outside nginx and are now token-gated; a rate limit would throttle legitimate service-to-service traffic (e.g. the dungeon polling loop). Out of scope. |
| Secret handling | The token is never logged, never in a `detail`, never in a response body, never in a test fixture committed as a real value. Tests use an obvious dummy. |
| Error messages | Fixed Russian strings from §3.2; they leak nothing about why the token failed. |

### 3.14. Follow-ups discovered, not fixed here

- **Autobattle registration is in-process memory** (`autobattle-service/app/main.py:119-126`): every
  deploy or crash silently stops AI-driven turns for battles already in flight until a re-register.
  Unrelated to this feature, pre-existing. Per CLAUDE.md §11 Bug Tracking, the developer who touches
  autobattle (T4/T11) adds this to `docs/ISSUES.md` (priority MEDIUM, service autobattle-service)
  and does **not** fix it here.
- `celery-beat` and photo-service have no `INTERNAL_SERVICE_TOKEN` in either compose file. Harmless
  today (neither calls an internal route). **No change** — a one-line comment in the feature log is
  enough; a future beat task hitting an internal route would 401 silently.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Ordering law (§3.4): helpers → all 18 caller headers → gate the 17 routes → tests.** The
`Depends On` column encodes it. T1–T7 may all run **in parallel** (different services, no shared
file). T8–T13 may run in parallel **with each other** once their own dependencies are DONE.

### Wave 1 — helpers + caller headers (parallel)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | battle-service: add the canonical `verify_internal_token` + `INTERNAL_SERVICE_TOKEN` to `auth_http.py` (§3.2). Add `headers=_internal_token_headers()` (existing helper, `main.py:65`) to all **7** outgoing call sites: `:799`, `:725`, `:902`, `:1239`, `:1025`, `:1192`, `:3731`. **Do not gate any route in this task.** No change to error handling or logging. | Backend Developer | DONE | `services/battle-service/app/auth_http.py`, `services/battle-service/app/main.py` | — | `py_compile` passes on both files; `auth_http.py` imports cleanly; all 7 calls pass `headers=`; existing battle-service tests still pass |
| 2 | dungeon-service: add `verify_internal_token` to `auth_http.py`. Add `headers=_internal_token_headers()` (`http_clients.py:26`) to `http_clients.py:377` (**the §1 trap — the battle-state poll**) and `:81` (action-gate consume). No route gating. | Backend Developer | DONE | `services/dungeon-service/app/auth_http.py`, `services/dungeon-service/app/http_clients.py` | — | `py_compile` passes; both calls pass `headers=`; note in the PR that `:377` serves both `gameplay.py:955` and `main.py:777` |
| 3 | battle-pass-service: add `verify_internal_token` to `auth_http.py`, reading `os.environ` — **do not add a field to `config.Settings`** (§3.3). Add `headers=_internal_token_headers()` (`crud.py:25`) to `crud.py:580` (`_deliver_diamonds`) and `:594` (`_deliver_cosmetic`). **Leave `claim_reward`'s deliver-then-record order exactly as it is** (§3.11). | Backend Developer | DONE | `services/battle-pass-service/app/auth_http.py`, `services/battle-pass-service/app/crud.py` | — | `py_compile` passes; both deliveries pass `headers=`; `claim_reward` diff is empty |
| 4 | autobattle-service: add `verify_internal_token` to `auth_http.py`. **Verify only** (no edit) that `clients.py:27` and `:38` already send the header. Add the autobattle in-memory-registration finding to `docs/ISSUES.md` (§3.14, MEDIUM) — do not fix it. | Backend Developer | DONE | `services/autobattle-service/app/auth_http.py`, `docs/ISSUES.md` | — | `py_compile` passes; report confirms the two existing headers; ISSUES.md entry added |
| 5 | locations-service: **hoist** `INTERNAL_SERVICE_TOKEN` + `_internal_token_headers` + `verify_internal_token` from `main.py:3729-3757` to the top of `main.py` (after imports / `logger`, before `_track_cumulative_stats`), verbatim, keeping them as `main.*` module attributes (§3.5). Leave a one-line breadcrumb at the old location. Then add `headers=_internal_token_headers()` to `main.py:1372`, `:1588`, `:3894` (leave-on-move) and `:1355`, `:1619` (track-event). No route gating. | Backend Developer | DONE | `services/locations-service/app/main.py` | — | **`main.py` imports without `NameError`** (run locations-service's test suite, which imports `main` — `py_compile` alone is NOT acceptance); `test_internal_auth.py` and `test_internal_headers.py` still pass unchanged; all 5 calls pass `headers=` |
| 6 | char-attrs: add a local `_internal_token_headers()` in `perk_evaluator.py` built from `config.settings.INTERNAL_SERVICE_TOKEN` (§3.6) and use it at `:85`. **Never `from main import …`** — that is the documented cycle. Do not restructure `_fetch_quest_completed`. | Backend Developer | DONE | `services/character-attributes-service/app/perk_evaluator.py` | — | `py_compile` passes; module imports standalone (no cycle); the `httpx.get` at `:85` passes `headers=` |
| 7 | inventory-service: add `headers=_internal_token_headers()` (`main.py:28`) to `main.py:454` (gather/collect → quest auto-progress). | Backend Developer | DONE | `services/inventory-service/app/main.py` | — | `py_compile` passes; the call passes `headers=` |

### Wave 2 — gate the 17 routes (lowest blast radius first)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 8 | locations-service: add `dependencies=[Depends(verify_internal_token)]` to the **6** routes — reads first (`:3685` action-gate, `:3674` gathering-status, `:3150` check-completed, `:3172` completed-count), then mutators (`:3195` quests auto-progress, `:3698` action-gate/consume). Handler signatures and responses unchanged. | Backend Developer | DONE | `services/locations-service/app/main.py` | 1, 2, 5, 6, 7 | Service imports and starts; each of the 6 routes returns 401 without the header and its normal 200 with it |
| 9 | battle-pass-service: gate `POST /battle-pass/internal/track-event` (`main.py:295`) with the new `auth_http.verify_internal_token`. | Backend Developer | DONE | `services/battle-pass-service/app/main.py` | 3, 5 | Route 401s without the header, works with it |
| 10 | dungeon-service: gate `POST /dungeons/internal/battle-callback` (`main.py:746`) and `GET /dungeons/internal/character-session/{cid}` (`:730`). **Close, do not delete** (§3.9) — keep both routes and their behaviour. | Backend Developer | DONE | `services/dungeon-service/app/main.py` | 2 | Both routes 401 without the header; neither is removed |
| 11 | autobattle-service: gate `POST /autobattle/internal/register` (`main.py:136`). Leave the public `/register` (`:102`, JWT + ownership) untouched. | Backend Developer | DONE | `services/autobattle-service/app/main.py` | 1, 4 | Internal route 401s without the header; public `/register` behaviour unchanged |
| 12 | battle-service: gate `GET /battles/internal/{bid}/state` (`main.py:1377`), `POST /battles/internal/{bid}/action` (`:1432`, keeps `skip_ownership=True`), `POST /battles/internal/party/leave-on-move` (`:6368`). Public twins `GET /battles/{id}/state` (`:1443`) and `POST /battles/{id}/action` (`:3505`) untouched. | Backend Developer | DONE | `services/battle-service/app/main.py` | 1, 2, 5 | All three 401 without the header; public twins still serve the browser |
| 13 | user-service: gate `POST /users/internal/{uid}/diamonds/add` (`main.py:1708`), `POST .../diamonds/spend` (`:1729`), `POST .../cosmetics/unlock` (`:2153`), `GET .../diamonds` (`:1696`) using the existing `auth.py:104` guard. **Close, do not delete** the three with no caller. | Backend Developer | DONE | `services/user-service/main.py` | 3 | All four 401 without the header; a battle-pass diamond/cosmetic claim still succeeds end-to-end with the header |

### Wave 3 — QA (mandatory)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 14 | **Route-side tests.** For each of the 17 routes: no-header → 401, wrong header → 401, correct header → normal success; plus at least one empty-token → 503 case per service (§3.12 b). Fix the 15 in-process calls that will now 401 (§3.12 a: `battle .../test_rewards_in_state.py:215,236,249`; `user-service tests/test_diamonds.py:42,50,244,258`; `tests/test_cosmetics.py:658,687,709,715,735,753,863`; `autobattle .../test_speed.py:567`). Monkeypatch the module attribute, not only the env var, where the guard captures a constant. | QA Test | DONE | `services/{battle,dungeon,battle-pass,autobattle,locations}-service/app/tests/*`, `services/user-service/tests/*` | 8, 9, 10, 11, 12, 13 | Every one of the 17 routes has all three cases; full suite green in each touched service; no route was weakened to make a test pass |
| 15 | **Caller-side + sweep tests.** (i) A header assertion for each of the 16 uncovered call sites, asserting `call.kwargs["headers"]["X-Internal-Token"]` on the real client function — never "nothing raised" (§3.12 c). (ii) Add the header assertion to `locations .../test_bp_tracking.py:244-245`, `battle-pass .../test_cosmetic_rewards.py:368`, `battle .../test_pve_rewards.py:600`. (iii) **Invert the source sweeps**: remove `_KNOWN_UNGATED_TARGETS` at `inventory .../test_outgoing_internal_headers.py:506` and the `GATED` allowlist at `battle-pass .../test_internal_headers.py:215`; same for dungeon `:210` and autobattle `:205`. Rule: any resolved URL containing `/internal/` must pass `headers=`; keep/raise the `checked >= N` floor; widen scanned files to `http_clients.py`, `perk_evaluator.py`, `clients.py`, `inventory_client.py`, `character_client.py`, `skills_client.py` (§3.12 d). (iv) Per-service `app.routes` sweep asserting every `/internal/` route carries `verify_internal_token` (§3.12 e). | QA Test | DONE | test dirs of battle, dungeon, battle-pass, autobattle, locations, inventory, char-attrs, user-service | 1–7, 8–13 | All 18 call sites covered by a header assertion; both FEAT-170 to-do markers gone; each sweep proven to go red when a header is deleted (state this in the report); route sweep present in every touched service |

### Wave 4 — Review

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 16 | **DONE — PASS (see section 5).** Final review. Re-run `py_compile` on every modified file **and** import-check locations `main.py` (§3.5). Re-run every touched service's suite. Confirm: 17/17 routes gated, 18/18 callers send the header, no compose / nginx / Alembic / RBAC / frontend file touched (§3.1), `claim_reward` ordering unchanged (§3.11), `_KNOWN_UNGATED_TARGETS` and the battle-pass allowlist are gone. **Live verification is mandatory** — with the stack up: attack a mob, start a PvP fight, enter a dungeon (the three fail-closed `action-gate/consume` paths), complete a **newly created** PvE battle and confirm the mob takes turns (not an old battle — see §3.10 autobattle note), claim a battle-pass diamond reward, and confirm zero 401/500 in the logs of battle, dungeon, locations, battle-pass, user-service. A review without both the automated results and the live check is invalid. | Reviewer | DONE | — | 14, 15 | All of the above confirmed in writing in section 5; FAIL if any internal route is still open or any caller still headerless |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-19
**Result:** PASS

Nothing in this review was taken from the agents' reports. Every claim below was re-derived
independently: the route inventory and the caller inventory from my own AST sweeps over `services/`,
the gate behaviour from live HTTP probes inside the compose network, and the sweeps' teeth from my
own red-proofs on throwaway copies of the source.

#### Scope compliance (§3.1)

`git status` touches **only** `services/**` and `docs/**` plus this feature file. No
`docker-compose*.yml`, no `nginx*.conf`, no Alembic `versions/`, no `permissions` seed, no frontend
file. `grep` over `services/frontend/app-chaldea/src` for `internal/` returns **zero** hits, so §2.0's
"no frontend change" holds. `battle-pass-service/app/crud.py`'s `claim_reward` has an **empty diff** —
the deliver-then-record order of §3.11 is intact; the only change in that file is the two
`headers=` arguments.

One unrelated file (`services/frontend/app-chaldea/package-lock.json`) was dirtied by the
container's own `npm install` during the stack recreate — two `devOptional` → `dev` flips, nothing to
do with this feature. Restored, working tree left exactly as found.

#### 1. Are all 17 routes actually gated? — verified two independent ways

**(a) AST sweep, whole repo.** Every `@app`/`@router` decorator in `services/` (tests excluded) whose
path has an `internal` **path segment**: **50 routes, 0 ungated.** The 17 in §2.1 are all present and
carry `dependencies=[Depends(verify_internal_token)]`; the 20 pre-existing ones are untouched; the
remaining 13 are FEAT-162/167/169's. Separately checked that no `APIRouter(prefix=…)` contains
`internal`, so no route can hide an internal segment behind a prefix — the 50 are the complete set.

**(b) Live HTTP, from inside the compose network**, three variants per route
(no header / wrong header / correct header):

| Target | no header | wrong header | correct header |
|---|---|---|---|
| all 17 routes | **401** `Недействительный internal token` | **401** same | route's normal behaviour |

`POST /battles/internal/{id}/action` and `POST /battle-pass/internal/track-event` answered **401 with
a deliberately malformed body** and only reached **422** once the header was right — i.e. the guard
rejects **before** body parsing, let alone before any read or write. The Russian `detail` strings match
§3.2 exactly.

**Public twins still serve players** (all exercised as a real logged-in user, not probed):
`GET /battles/{id}/state` and `POST /battles/{id}/action` drove two full battles;
`GET /locations/action-gate/status` returned `{"combat":[759]}` / `{"dungeon":[1]}` / `{"pvp":[27]}`;
`POST /autobattle/register`'s JWT+ownership path is untouched in the diff.

#### 2. My own caller sweep — no header missing, and nothing on an old path

An independent AST sweep of every `httpx`/`requests`/`client` call in `services/` (tests excluded),
resolving f-strings and one level of local variable assignment, found **every** call site whose URL
contains an `internal` segment. **All of them pass `headers=`; zero offenders.** This covers more than
§3.7's 18: it also re-confirms the FEAT-162/167/169 sites. A follow-up plain-text `grep` for
`internal` across all non-test Python found no call the AST pass had missed, and no caller still on a
pre-FEAT-168/169 path.

Two caller sites build the header inline instead of calling the module helper —
`battle-service/app/main.py:2134` and `:4140`. **Both are pre-existing** (`:4140` dates to commit
`90096f3`, FEAT-128), untouched by this feature, and neither is a hole: see §5 "QA's three flagged
items" below.

#### 3. The locations hoist really holds

`py_compile` was **not** accepted as evidence (§3.5 constraint 4). `python -c "import main"` was run
inside the live container for **locations, battle, dungeon, battle-pass, autobattle, user and
inventory** — all `IMPORT_OK` — plus `import perk_evaluator` standalone in char-attrs, which proves
the §3.6 cycle is still avoided. The hoisted block keeps `INTERNAL_SERVICE_TOKEN`,
`_internal_token_headers` and `verify_internal_token` as `main.*` attributes, the old location carries
the "do not move it back" breadcrumb, and locations-service's suite (1354 tests, including the
`monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", …)` tests that were **not** edited) is green.
Nothing else regressed from the hoist.

#### 4. The inverted sweeps have teeth — proven red by me, not by the report

Two sweeps were re-proved from scratch. The service tree was **copied to a scratch directory** and the
header deleted there, so the real working tree was never touched (no `git checkout`, per the FEAT-169
incident):

- **inventory** — removing `headers=` from `main.py:455` turned
  `TestEveryInternalCallSiteSendsHeaders::test_no_internal_call_is_missing_headers` red, naming
  `main.py:455` in the failure, **plus** the two per-call tests (`KeyError: 'headers'`). 3 failed.
- **battle-pass** — removing `headers=` from `_deliver_diamonds` turned
  `TestEveryGatedCallCarriesTheHeader::test_no_internal_call_is_missing_headers` red, naming
  `crud.py:583`, plus both `TestDeliverDiamonds` tests. 3 failed.

**QA's two caveats check out, and neither hides a gap:**

- Matching on `internal/` rather than `/internal/` is strictly **broader**, not narrower — it is the
  only way to catch inventory's `f"{ATTRIBUTES_SERVICE_URL}internal/…"` (the setting already ends in a
  slash). It cannot exempt anything.
- "Decorator expressions had to be skipped" is achieved by requiring the call's receiver to be one of
  `httpx` / `client` / `requests`. `@router.post(...)` / `@app.get(...)` have receiver `router` / `app`,
  so they are excluded structurally rather than by an allowlist. My own sweep hit the same false
  positives and confirmed all 50 of them are decorators.

All four FEAT-170 markers are gone (`_KNOWN_UNGATED_TARGETS`, and the `GATED` allowlists in
battle-pass, dungeon and autobattle); the only surviving mentions are guard-tests asserting those
names must never come back, and one explanatory comment.

#### 5. QA's three flagged items — my judgement

1. **`battle-service/app/tests/test_rewards_in_state.py:124`** — `auth_http.INTERNAL_SERVICE_TOKEN`
   assigned at module import with no `monkeypatch` and no restore, so it leaks to every other module
   in the same process. **Not a blocker, does not have to be fixed now.** The leak sets a *non-empty*
   token, so the failure mode is loud and order-dependent (a test expecting the empty-token `503`
   would get `401` and fail), never a silent pass; the full suite is green at 759. Logged in
   `docs/ISSUES.md` (LOW) so it is not forgotten.
2. **`battle-service/app/main.py:4140`** — `headers={"X-Internal-Token": tok} if tok else {}`.
   **Not a fail-open hole.** This is a *caller*, not a guard: with an empty token it sends no header
   and the receiving route (`/locations/internal/cancel-gathering`) answers `401`, or `503` if its own
   env is empty. Either way the request is refused — the `{}` branch can only make the call fail, never
   succeed. It is pre-existing (FEAT-128, `90096f3`), outside this feature's diff, and the path was
   exercised live during the PvP attack: `POST /locations/internal/cancel-gathering → 200 OK`. Style
   inconsistency only.
3. **char-attrs' weaker route sweep** — `test_internal_auth_feat169.py:566` is correct in substance
   (it walks the flattened `route.dependant.dependencies`, so nested deps count, and char-attrs' paths
   really are `/attributes/internal/…`). Its only weakness is the missing `checked >= N` floor the six
   new sweeps have. Logged in `docs/ISSUES.md` (LOW). Not a blocker.

#### Automated Check Results

- [x] `npx tsc --noEmit` — **N/A** (no frontend file touched, verified via `git status`)
- [x] `npm run build` — **N/A** (same)
- [x] `py_compile` on every modified production file — **PASS** (8 services, all exit 0)
- [x] **Module import** of `main` in 7 services + `perk_evaluator` standalone — **PASS** (§3.5/§3.6)
- [x] `pytest` — **PASS**, every touched service, run in its own container with CI args:
      battle **759 passed / 4 skipped** · locations **1354 passed** · inventory **1395 passed / 1 skipped** ·
      user **581 passed / 5 skipped** · autobattle **151 passed** · battle-pass **147 passed** ·
      dungeon **155 passed** · char-attrs **see note**
- [x] `docker-compose config` (dev **and** dev+prod overlay) — **PASS**
- [x] Live verification — **PASS** (below)

**char-attrs note — a pre-existing failure, not a regression.** In the dev container 22 tests in
`test_passive_experience.py` / `test_refund_stamina.py` / `test_regen.py::TestEndpointWiring` fail with
`401` (or `503` on an empty token): they call gated `/attributes/internal/*` routes without sending the
header, and are green in CI only because CI has no `INTERNAL_SERVICE_TOKEN` at all. I ran the **same
tests at clean `15e522b`** in a throwaway container with the token set: **identical 22 failures**. So
FEAT-167/169 introduced this, not FEAT-170 (which touches only `perk_evaluator.py` in that service).
With no token in the environment — CI's condition — both HEAD and the working tree give the same
6 "needs the whole repository" environment failures and nothing else. Logged in `docs/ISSUES.md` (LOW).

**One more environment trap, worth recording:** the first battle-service run failed on
`test_the_sweep_has_no_exemption_list` with `OSError: could not get source code`. Cause: stale
`__pycache__` left in the working tree by QA's runs with the repo mounted at `/repo`, so the `.pyc`
carried a `co_filename` that does not exist in the service container and `inspect.getsource` could not
read it. After `find /app -name __pycache__ -delete` the suite is **759 passed**. Not a code defect —
but it is why a green report is not the same as a green run.

#### Live Verification Results

Stack fully recreated (`docker compose up -d --force-recreate`, all 24 containers). Because uvicorn
`--reload` has silently missed edits on this stack before, I confirmed the containers actually run the
new code rather than assuming it: every one of the 17 routes answered `401` to an un-headered request
**through the live network**, which is only possible with the new code loaded.

Played as a real logged-in player (`chaldea@admin.com`, character 761 «Аэлис»), not by curling
endpoints:

| Flow | Internal call it drives | Live result |
|---|---|---|
| Move 196→197 (`quick_move`) | `POST /battles/internal/party/leave-on-move` | **200 OK** from locations (172.18.0.13) |
| Same move | `POST /battle-pass/internal/track-event` | **200 OK** from locations |
| Combat intent post → `POST /battles/mob-attack` | `POST /locations/internal/action-gate/consume` (**fails closed**) | **200 OK**, battle 220 created |
| Battle 220 fought to the end via the public twins | `POST /battles/internal/220/action`, `GET /battles/internal/220/state` from autobattle (172.18.0.21) | **200 OK** repeatedly; **the mob took every turn** (my HP 150 → −15). Battle reached `status=finished`. This was a **freshly created** battle, per §3.10 |
| PvP intent post → `POST /battles/pvp/attack` on character 27 | `POST /locations/internal/action-gate/consume` (pvp, **fails closed**) | **200 OK**, battle 222 created; also `POST /locations/internal/cancel-gathering` **200 OK** |
| Dungeon intent post → create session → `enter` | `POST /locations/internal/action-gate/consume` (dungeon, **fails closed**) from dungeon-service (172.18.0.12) | **200 OK**, session 13 entered |
| Dungeon: 7 room moves, corridor ambush → battle 221 | `GET /battles/internal/221/state` from **dungeon-service** — the §1 trap, the loudest failure mode | **200 OK**; the polling loop drove the fight and resolved the session to `wiped`. Zero errors in dungeon-service |
| Gathering: intent post → start node 1 → completion | `POST /inventory/internal/.../free_slots_check`, `.../gathering/award` | **200 OK** each; 5× «Эссенция огня» actually awarded |
| Item collected → quest auto-progress | `POST /locations/quests/internal/auto-progress` from **inventory** (172.18.0.8) | **200 OK** |
| Same route from **battle-service**, invoked through the real `main._internal_token_headers()` | `POST /locations/quests/internal/auto-progress`, `POST /locations/internal/gathering-status`, `POST /autobattle/internal/register` | **200 / 200 / 422-after-guard**; helper header verified to equal the env token (64 chars) |
| char-attrs perk evaluator, real `perk_evaluator._fetch_quest_completed` | `GET /locations/quests/internal/check-completed` | **200 OK** `{"completed": false}` — the new local helper (§3.6) works |
| **Battle-pass claim → diamonds** (caller **re-raises**) | `POST /users/internal/4/diamonds/add` | **200 OK**; balance **0 → 5** in the DB |
| **Battle-pass claim → cosmetic** (caller **re-raises**) | `POST /users/internal/4/cosmetics/unlock` | **200 OK**; frame row actually created |

**Log sweep for 401/403/503 across all 13 services** (battle, locations, user, dungeon, battle-pass,
autobattle, inventory, char-attrs, character, party, skills, notification, celery): **no unexplained
rejection.** Every 401/403 traces to one of three known sources, each checked by timestamp:

- my own three-variant probes at `10:38:21` (deliberate no-header / wrong-header requests);
- one `POST /battles/mob-attack → 403` — my first attack attempt before opening the combat gate, i.e.
  the game rule working;
- `GET /users/me → 401` from notification-service (172.18.0.23), an SSE reconnect with a stale JWT.
  Pre-existing, a JWT route, unrelated to this feature.

The `auto-progress` 401s from battle-service at `10:39`/`10:41` were chased down rather than assumed:
they fall inside the in-container pytest window, not any gameplay, and the **real** production helper
returns `200` (row above). No internal call from any service degraded silently.

Two non-blocking runtime observations, neither caused by this feature: one
`ERROR [CUMULATIVE] Не удалось отправить статистику для персонажа 761` — a `ReadTimeout` on the
5-second fire-and-forget to char-attrs at the end of a battle, **not** a 401; and
`GET /characters/internal/mob-reward-data/761 → 404`, the expected answer for a non-mob character.

#### Test data cleaned up

All of it restored, verified by re-query: character 761 back at location 1183 and healed to full,
character 214 back to `NULL`, battle-pass progress back to level 1 / 50 xp, the temporarily repointed
`bp_rewards` row 7 back to `xp/100/NULL`, both claim rows deleted, `users.diamonds` back to 0, the
battle-pass frame unlock deleted, the gathered items and the node bank (55) restored, all 4 action
gates deleted, the 6 test posts, dungeon session 13 and gathering session 16 deleted, and
autobattle-service restarted to drop the two in-memory probe registrations. Character 27 (another
player's) was verified **unchanged** — battle 222 was force-finished before a turn was taken. The
three finished battle rows (220, 221, 222) are left as ordinary game history; deleting them would
reach into `battle_history`/`mob_kills` for no benefit. **No commits were made.**

#### Pre-existing issues noted (added to `docs/ISSUES.md`, all LOW, none blocking)

| # | File | Description |
|---|------|-------------|
| 1 | `char-attrs/app/tests/{test_passive_experience,test_refund_stamina,test_regen}.py` | 22 tests call gated `/attributes/internal/*` with no header; green only because CI has no `INTERNAL_SERVICE_TOKEN`. Proven identical at `15e522b` — FEAT-167/169, not this feature |
| 2 | `char-attrs/app/tests/test_internal_auth_feat169.py:566` | Route sweep has no `checked >= N` floor, unlike the six added here |
| 3 | `battle-service/app/tests/test_rewards_in_state.py:124` | Module-level token assignment without `monkeypatch`/restore; leaks across modules in one process |

#### Verdict

17/17 routes gated and rejecting before any read or write; 18/18 callers (and in fact every internal
call site in the repo) sending the header; the locations hoist imports cleanly; the sweeps are
genuinely toothy; no player path broken — attack, PvP, dungeon entry, dungeon room moves, autobattle,
quest auto-progress, gathering, battle-pass diamond and cosmetic claims all verified live end to end.
**PASS.**

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-19 10:00 — PM: фича создана (остаток internal-префиксов), запускаю анализ
[LOG] 2026-09-19 10:05 — Analyst: начал анализ, перечень маршрутов собираю заново AST-обходом декораторов, а не из ISSUES.md
[LOG] 2026-09-19 10:35 — Analyst: найдено 37 маршрутов с сегментом internal, из них 17 держатся только на nginx; список ISSUES.md оказался устаревшим и неполным (нет completed-count и GET action-gate)
[LOG] 2026-09-19 10:50 — Analyst: собрана матрица вызывающих — 18 точек вызова в 6 сервисах; 15 из 18 проглатывают ошибку, то есть забытый заголовок даст тихую деградацию
[LOG] 2026-09-19 10:55 — Analyst: ловушка из §1 подтверждена — dungeon-service/app/http_clients.py:377 ходит в /battles/internal/{id}/state без заголовка и при ошибке падает громко (502/503), подземелье прервётся
[LOG] 2026-09-19 11:05 — Analyst: фронтенд не вызывает ни одного internal-маршрута — игровые пути-двойники уже есть и закрыты JWT, отдельный игровой путь не нужен
[LOG] 2026-09-19 11:15 — Analyst: найдены две ловушки импорта — в locations-service verify_internal_token объявлен ниже шести закрываемых маршрутов (NameError на старте), в char-attrs perk_evaluator импорт хелпера из main даст цикл
[LOG] 2026-09-19 11:25 — Analyst: INTERNAL_SERVICE_TOKEN доезжает до всех 13 сервисов в обоих compose-файлах; правки не нужны. Пробелы только у celery-beat и photo-service, оба безвредны (HTTP-вызовов нет)
[LOG] 2026-09-19 11:35 — Analyst: шесть маршрутов не вызываются ниоткуда (spend/GET diamonds, оба dungeons/internal, GET action-gate, completed-count) — нужен ответ пользователя: закрыть или удалить
[LOG] 2026-09-19 11:45 — Analyst: анализ завершён, раздел 2 заполнен; затронуто 8 сервисов, 17 маршрутов, 18 точек вызова
[LOG] 2026-09-19 12:00 — Architect: начал проектирование, статус IN_PROGRESS
[LOG] 2026-09-19 12:10 — Architect: порядок работ зафиксирован жёстко — хелперы → 18 заголовков у вызывающих → закрытие 17 маршрутов → тесты; зависимость «вызывающие раньше маршрутов» прописана в колонке Depends On
[LOG] 2026-09-19 12:15 — Architect: ловушка locations решена подъёмом блока (константа + оба хелпера + verify_internal_token) в начало main.py — имена остаются доступны как main.INTERNAL_SERVICE_TOKEN, существующие monkeypatch-тесты не ломаются; приёмка задачи — импорт модуля, а не py_compile
[LOG] 2026-09-19 12:20 — Architect: для perk_evaluator заголовок строится из config.settings — импорт хелпера из main запрещён (цикл); четырём сервисам (battle, dungeon, battle-pass, autobattle) guard кладём в готовый листовой auth_http.py, battle-pass читает os.environ, поле в Settings не добавляем
[LOG] 2026-09-19 12:30 — Architect: проверил battle-pass crud.py claim_reward — награда выдаётся ДО записи BpUserReward (:676 против :678), значит 401 при выкатке не сжигает награду, дефекта нет; в задаче T3 явно запрещено менять этот порядок
[LOG] 2026-09-19 12:40 — Architect: разбор безопасности выкатки — CI делает down/up целиком, смешанных версий не бывает; бой, подземелье, боевой пропуск переживают рестарт (Redis/БД), а регистрации автобоя лежат в памяти процесса и теряются на любом деплое (это не регрессия фичи, но живую проверку надо делать на НОВОМ бою) — вынесено в ISSUES.md отдельной задачей T4
[LOG] 2026-09-19 12:50 — Architect: стратегия тестов — три кейса на каждый из 17 маршрутов, проверка самого заголовка на 16 непокрытых точках вызова, инверсия свипов (снять _KNOWN_UNGATED_TARGETS и allowlist battle-pass, оба помечены как TODO FEAT-170) и свип по app.routes в каждом сервисе
[LOG] 2026-09-19 12:55 — Architect: спроектировано 16 задач (7 параллельных в первой волне, 6 на закрытие маршрутов, 2 QA, 1 ревью); новых API-контрактов нет — меняется только требование заголовка; compose, nginx, БД, Alembic и RBAC не трогаем, это записано в раздел 3 явным запретом
[LOG] 2026-09-19 13:10 — Backend Dev: начал задачи #6 и #7 (char-attrs perk_evaluator, inventory main.py), только заголовки у вызывающих, маршруты не трогаю
[LOG] 2026-09-19 13:25 — Backend Dev: задача #6 завершена — в perk_evaluator.py добавлен локальный _internal_token_headers() из config.settings (импорт хелпера из main запрещён, цикл), заголовок добавлен в httpx.get на /locations/quests/internal/check-completed
[LOG] 2026-09-19 13:30 — Backend Dev: задача #7 завершена — httpx.post на /locations/quests/internal/auto-progress (inventory main.py, событие collect) теперь шлёт headers=_internal_token_headers()
[LOG] 2026-09-19 13:45 — Backend Dev: проверки — py_compile обоих файлов, реальный импорт perk_evaluator (хелпер вернул токен), полные наборы тестов в Docker: char-attrs 465 passed / 2 skipped / 1 xpassed, inventory 1389 passed; docs/services обоих сервисов обновлены
[LOG] 2026-09-19 13:10 — Backend Dev: начал задачу #5 (locations-service, волна 1 — подъём блока и заголовки у вызывающих)
[LOG] 2026-09-19 13:25 — Backend Dev: блок INTERNAL_SERVICE_TOKEN + _internal_token_headers + verify_internal_token перенесён из main.py:3731-3759 в начало файла (после OAUTH2_SCHEME_OPTIONAL, перед _track_cumulative_stats), тела функций не менялись; на старом месте оставлена хлебная крошка с объяснением, почему не двигать обратно
[LOG] 2026-09-19 13:30 — Backend Dev: добавлен headers=_internal_token_headers() в 5 вызовов — leave-on-move (перемещение, быстрое перемещение, character-left-location) и track-event (перемещение, move_and_post); обработка ошибок и логирование не тронуты
[LOG] 2026-09-19 13:40 — Backend Dev: проверка — `python -c "import main"` внутри контейнера locations-service проходит без NameError; полный pytest (--asyncio-mode=auto, CI=true) в контейнере: 1275 passed, тесты с monkeypatch main.INTERNAL_SERVICE_TOKEN не правились и зелёные
[LOG] 2026-09-19 13:45 — Backend Dev: задача #5 завершена, изменено 2 файла (main.py, docs/services/locations-service.md); маршруты не закрывал — это волна 2 (задача #8)
[LOG] 2026-09-19 13:10 — Backend Dev: задача 1 — в battle-service/app/auth_http.py добавлен канонический verify_internal_token (пусто в env → 503, нет/чужой → 401, тексты по-русски); к маршрутам НЕ привязан, это волна 2
[LOG] 2026-09-19 13:20 — Backend Dev: задача 1 — заголовок X-Internal-Token добавлен во все 7 исходящих вызовов battle-service (auto-progress :727, autobattle register :801, action-gate/consume combat :912 и pvp, gathering-status ×3); обработка ошибок и логирование не тронуты
[LOG] 2026-09-19 13:25 — Backend Dev: задача 4 — autobattle/app/auth_http.py получил тот же verify_internal_token; вызовы clients.py:27 и :38 перепроверены — заголовок действительно шлют, правок не потребовалось
[LOG] 2026-09-19 13:30 — Backend Dev: задача 4 — в docs/ISSUES.md добавлена запись MEDIUM про регистрации автобоя в памяти процесса (теряются на каждом деплое), как и предписано §3.14 — не чиню
[LOG] 2026-09-19 13:45 — Backend Dev: проверки в Docker — py_compile по изменённым файлам, реальный импорт обоих auth_http (декоратор/порядок импорта ловится только импортом), полный pytest: battle-service 727 passed, autobattle-service 133 passed
[LOG] 2026-09-19 13:50 — Backend Dev: обновлены docs/services/battle-service.md (4 новые строки в таблице исходящих вызовов + раздел про волну 1) и docs/services/autobattle-service.md
[LOG] 2026-09-19 14:00 — Backend Dev: задача 2 — в dungeon-service/app/auth_http.py добавлен канонический verify_internal_token (пусто в env → 503, нет/чужой → 401); к маршрутам не привязан, это волна 2
[LOG] 2026-09-19 14:05 — Backend Dev: задача 2 — заголовок X-Internal-Token добавлен в оба исходящих вызова http_clients.py: consume_dungeon_gate (:81, action-gate/consume, ошибку глотает и отказывает во входе) и get_battle_state (:377 — та самая ловушка §1, она падает громко 502/503; одна функция обслуживает оба пути — gameplay.py:955 и main.py:777)
[LOG] 2026-09-19 14:15 — Backend Dev: задача 3 — battle-pass-service/app/auth_http.py получил verify_internal_token, читающий os.environ; поле в config.Settings НЕ добавлял (§3.3). Заголовок добавлен в _deliver_diamonds (crud.py:580) и _deliver_cosmetic (:594); порядок claim_reward (выдача до записи BpUserReward) не тронут — диффа там нет
[LOG] 2026-09-19 14:25 — Backend Dev: тесты на сам заголовок, а не на «ничего не упало» — 2 новых в dungeon (gate consume + опрос состояния боя) и 2 новых класса в battle-pass (алмазы, косметика: значение заголовка, чтение токена на каждом вызове, проброс 401); в свипы добавлены /locations/internal/, /battles/internal/ (dungeon) и /users/internal/ (battle-pass — снят TODO FEAT-170 из FEAT-169)
[LOG] 2026-09-19 14:35 — Backend Dev: проверки в Docker (CI=true, аргументы как в CI) — py_compile + реальный импорт обоих auth_http, dungeon-service 137 passed, battle-pass-service 130 passed; отдельно проверил, что тест на опрос состояния боя краснеет, если убрать заголовок
[LOG] 2026-09-19 14:40 — Backend Dev: docs/services/ для dungeon-service и battle-pass-service не существует — обновлять нечего
[LOG] 2026-09-19 15:00 — Backend Dev: начал задачу #13 (user-service, волна 2 — алмазы и косметика, закрываются последними: их вызывающий в battle-pass пробрасывает ошибку наружу)
[LOG] 2026-09-19 15:10 — Backend Dev: задача #13 — четыре маршрута закрыты существующим auth.verify_internal_token через dependencies=[Depends(...)] в декораторе (сигнатуры обработчиков и тела ответов не тронуты): GET /users/internal/{uid}/diamonds, POST .../diamonds/add, POST .../diamonds/spend, POST .../cosmetics/unlock. Маршруты без вызывающих закрыты, но не удалены (§3.9)
[LOG] 2026-09-19 15:20 — Backend Dev: задача #13 — поправлены существующие in-process тесты, которые теперь получали бы 401: tests/test_diamonds.py (27 вызовов клиента, не 4 — закрыты и POST-маршруты тоже) и tests/test_cosmetics.py (7 вызовов unlock); в обоих файлах добавлена autouse-фикстура с monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", ...) по образцу test_activity_increment_internal.py
[LOG] 2026-09-19 15:30 — Backend Dev: проверки в Docker (chaldea-user-service, репозиторий смонтирован, CI=true, аргументы как в CI) — py_compile трёх изменённых файлов, реальный импорт main (IMPORT_OK), полный pytest: 550 passed; отдельно свипом по app.routes подтверждено, что все 5 маршрутов /users/internal/ несут verify_internal_token (BAD: [])
[LOG] 2026-09-19 15:35 — Backend Dev: задача #13 завершена, изменено 4 файла (main.py, два файла тестов, docs/services/user-service.md); маршрутов не удалял, тела ответов и коды успеха не менял
[LOG] 2026-09-19 15:00 — Backend Dev: начал задачу #8 (locations-service, волна 2 — закрытие шести маршрутов). Перед правкой перепроверил всех вызывающих по коду: 8 точек вызова (battle-service ×6, dungeon-service ×1, inventory ×1, char-attrs ×1) действительно шлют X-Internal-Token после волны 1
[LOG] 2026-09-19 15:10 — Backend Dev: задача #8 — dependencies=[Depends(verify_internal_token)] добавлен шести маршрутам: сначала чтения (quests/internal/check-completed, quests/internal/completed-count, internal/gathering-status, internal/action-gate), затем мутаторы (quests/internal/auto-progress, internal/action-gate/consume). Сигнатуры обработчиков, response_model и тела ответов не менялись — добавлены только зависимость и пояснения в docstring
[LOG] 2026-09-19 15:15 — Backend Dev: особое внимание action-gate/consume — вызывающие падают ЗАКРЫТО (отказ в атаке, PvP и входе в подземелье). Отдельно перечитал battle-service main.py:905/:1245 и dungeon-service http_clients.py:84 — заголовок на месте во всех трёх
[LOG] 2026-09-19 15:25 — Backend Dev: проверка — `python -c "import main"` в контейнере проходит без NameError (py_compile тут недостаточен), свип по app.routes показал 9 из 9 internal-маршрутов с verify_internal_token, непокрытых нет; полный pytest (--asyncio-mode=auto, CI=true) в Docker: 1275 passed — ровно столько же, сколько после волны 1
[LOG] 2026-09-19 15:30 — Backend Dev: существующих тестов, вызывающих эти шесть маршрутов внутри процесса, в locations-service нет (§2.8 это и предсказывал) — править было нечего. Задача #8 завершена, изменено 2 файла (main.py, docs/services/locations-service.md)
[LOG] 2026-09-19 15:00 — Backend Dev: начал задачи 11 и 12 (волна 2) — закрытие /autobattle/internal/register и всего префикса /battles/internal/
[LOG] 2026-09-19 15:10 — Backend Dev: задача 12 — на трёх маршрутах battle-service добавлен dependencies=[Depends(verify_internal_token)]: GET /internal/{battle_id}/state, POST /internal/{battle_id}/action (skip_ownership=True сохранён — именно поэтому маршрут и нельзя держать открытым) и POST /internal/party/leave-on-move; сигнатуры обработчиков, тела и коды ответов не менялись
[LOG] 2026-09-19 15:15 — Backend Dev: задача 11 — POST /autobattle/internal/register закрыт тем же guard'ом; публичный POST /autobattle/register (JWT + проверка владения) не тронут
[LOG] 2026-09-19 15:20 — Backend Dev: поправлены тесты, которые теперь получали бы 401 — battle-service/tests/test_rewards_in_state.py (3 вызова /battles/internal/1|999/state) и autobattle/tests/test_speed.py (internal register); в обоих файлах выставлен auth_http.INTERNAL_SERVICE_TOKEN (модульный атрибут, а не только env) и добавлен заголовок
[LOG] 2026-09-19 15:30 — Backend Dev: проверки в Docker (CI=true, аргументы как в CI) — py_compile по изменённым файлам, реальный импорт main и auth_http обоих сервисов, полный pytest: battle-service 723 passed / 4 skipped, autobattle-service 133 passed
[LOG] 2026-09-19 15:35 — Backend Dev: живая проверка контракта через TestClient — все четыре маршрута: без заголовка 401, чужой 401, верный 200, пустой токен в env 503; публичные двойники GET /battles/{id}/state и POST /battles/{id}/action по-прежнему требуют JWT и не требуют internal-токена
[LOG] 2026-09-19 15:40 — Backend Dev: задачи 11 и 12 завершены; обновлены docs/services/battle-service.md (раздел FEAT-170 — таблица трёх закрытых маршрутов) и docs/services/autobattle-service.md (волна 2 + строка про /internal/register в таблице эндпоинтов)
[LOG] 2026-09-19 15:45 — Backend Dev: начал задачи #9 и #10 (волна 2) — закрытие internal-маршрутов dungeon-service и battle-pass-service; вызывающие из волны 1 перепроверены, оба вызова locations на track-event уже шлют headers=_internal_token_headers()
[LOG] 2026-09-19 15:55 — Backend Dev: задача #10 — GET /dungeons/internal/character-session/{cid} и POST /dungeons/internal/battle-callback закрыты через dependencies=[Depends(verify_internal_token)] из auth_http; маршруты и их поведение сохранены (закрываем, не удаляем, §3.9), сигнатуры обработчиков не тронуты
[LOG] 2026-09-19 16:00 — Backend Dev: задача #9 — POST /battle-pass/internal/track-event закрыт тем же guard'ом из auth_http (токен читается из os.environ, поле в config.Settings не добавлялось); claim_reward не тронут, диффа в crud.py нет
[LOG] 2026-09-19 16:10 — Backend Dev: проверки в Docker (весь репозиторий примонтирован, CI=true, аргументы как в CI) — py_compile + реальный импорт main и auth_http обоих сервисов, полный pytest: dungeon-service 137 passed (exit 0), battle-pass-service 130 passed; существующих тестов, которые теперь получали бы 401, в этих двух сервисах нет — править было нечего
[LOG] 2026-09-19 16:15 — Backend Dev: живая проверка контракта через TestClient — все три маршрута: без заголовка 401 «Недействительный internal token», чужой 401, пустой токен в env 503 «Internal service token не настроен», верный заголовок проходит guard и доходит до валидации тела; обход app.routes подтверждает verify_internal_token у всех маршрутов с сегментом /internal/ в обоих сервисах
[LOG] 2026-09-19 16:20 — Backend Dev: задачи #9 и #10 завершены, изменено 2 файла (dungeon main.py, battle-pass main.py); docs/services/ для dungeon-service и battle-pass-service по-прежнему не существует — обновлять нечего, новый файл не создавал
[LOG] 2026-09-19 16:30 — QA: начал задачи #14 и #15, работа разбита по восьми сервисам; производственный код не трогаю, каждая правка — только в тестах
[LOG] 2026-09-19 17:10 — QA: задача #14 — матрица авторизации написана для всех 17 маршрутов (нет заголовка → 401, чужой → 401, пустой INTERNAL_SERVICE_TOKEN → 503, верный → штатное поведение), русские detail проверяются дословно; 13 из 17 маршрутов до этого не имели HTTP-теста вообще
[LOG] 2026-09-19 17:15 — QA: на каждом отказе (401/503) дополнительно проверяется, что состояние НЕ изменилось — баланс алмазов и косметика, прогресс заданий, счётчик action-gate, сессия подземелья, реестры автобоя в памяти, вызовы crud/db не происходят. Guard, который отвечает 401 уже после записи, такие тесты роняют
[LOG] 2026-09-19 17:20 — QA: везде используется monkeypatch.setattr(<модуль>, "INTERNAL_SERVICE_TOKEN", ...) — только setenv не работает, токен захватывается в модульную константу при импорте (locations → main, battle/autobattle/dungeon/battle-pass → auth_http, user-service → auth)
[LOG] 2026-09-19 17:30 — QA: задача #14 — ручной обход app.routes, который разработчики гоняли «на коленке», закреплён как тест в шести сервисах: каждый маршрут с сегментом /internal/ обязан нести verify_internal_token в ПЛОСКОМ списке зависимостей (учитываются и вложенные), с порогом >= N, чтобы рефакторинг не опустошил проверку. В char-attrs такой тест уже был (test_internal_auth_feat169.py:565) — не дублировал
[LOG] 2026-09-19 17:45 — QA: задача #15 — закрыты все 16 непокрытых точек вызова; проверяется сам факт отправки заголовка на РЕАЛЬНОЙ функции клиента (call.kwargs["headers"]["X-Internal-Token"]) плюс разрешённый URL, а не «ничего не упало» — 15 из 18 вызывающих ошибку глотают. Усилены три старых теста: locations test_bp_tracking, battle-pass test_cosmetic_rewards, battle test_pve_rewards
[LOG] 2026-09-19 17:55 — QA: задача #15 — свипы инвертированы, а не расширены: сняты все четыре маркера FEAT-170 (_KNOWN_UNGATED_TARGETS в inventory, allowlist GATED в battle-pass, dungeon и autobattle). Правило теперь одно — любой вызов с разрешённым URL, содержащим internal/, обязан передавать headers=; добавлены пороги checked >= N и guard-тест, который краснеет при попытке вернуть любой список исключений
[LOG] 2026-09-19 18:00 — QA: область сканирования свипов расширена с main.py/crud.py на http_clients.py, gameplay.py, perk_evaluator.py, regen.py, clients.py, strategy.py, tasks.py, inventory_client.py, character_client.py, skills_client.py; сверка идёт по «internal/», а не «/internal/» — inventory строит два URL без ведущего слэша, и строгий фильтр их молча терял
[LOG] 2026-09-19 18:10 — QA: каждый свип доказан «в красном» — из рабочего кода временно убирался headers=, тест падал, файл восстанавливался обратной правкой (git checkout НЕ использовался ни разу: в FEAT-169 два агента так стёрли незакоммиченную работу разработчиков). Контрольные точки: battle main.py:3755, locations track-event, inventory main.py:454, dungeon http_clients.py:384, autobattle clients.py:28, char-attrs perk_evaluator.py:98, battle-pass crud.py diamonds/add
[LOG] 2026-09-19 18:20 — QA: полные наборы в Docker (весь репозиторий примонтирован, CI=true, аргументы как в ci.yml) — battle 763, locations 1354, inventory 1396, user 586, char-attrs 478 (+2 skipped, 1 xpassed), autobattle 151, battle-pass 147, dungeon 155; всё зелёное, добавлено ~230 тестов
[LOG] 2026-09-19 18:25 — QA: производственный код не менялся — git diff --stat по всем рабочим файлам совпадает с состоянием до начала задачи; багов в рабочем коде не найдено: все 17 guard'ов отвергают запрос ДО чтения и записи, битое тело без заголовка даёт 401, а не 422
[LOG] 2026-09-19 18:30 — QA: замечание по гигиене тестов (не баг) — battle-service/app/tests/test_rewards_in_state.py:124 присваивает auth_http.INTERNAL_SERVICE_TOKEN обычным присваиванием на импорте модуля, без monkeypatch и без восстановления; новые тесты от этого не зависят, но значение протекает на остальные модули в том же процессе
[LOG] 2026-09-19 18:35 — QA: задачи #14 и #15 завершены, передаю на ревью (#16)
[LOG] 2026-09-19 19:00 — Reviewer: начал проверку (задача #16), статус REVIEW. Отчётам агентов не доверяю — перечень маршрутов и вызывающих пересобираю своими AST-свипами, поведение гейтов проверяю живыми запросами
[LOG] 2026-09-19 19:10 — Reviewer: свип по всем декораторам маршрутов в services/ — 50 маршрутов с сегментом internal, незакрытых 0. Отдельно проверил, что ни у одного APIRouter в prefix нет internal, значит список полный и спрятать маршрут за префиксом нельзя
[LOG] 2026-09-19 19:15 — Reviewer: свой свип вызывающих (f-строки и одноуровневые переменные раскрываются) — ни одного вызова на internal-маршрут без headers=, ни одного на старом пути. Контрольный текстовый grep по всем не-тестовым .py ничего сверх не нашёл; фронтенд internal-путей не зовёт вообще
[LOG] 2026-09-19 19:25 — Reviewer: стек пересоздан целиком (up -d --force-recreate). Живая проверка всех 17 маршрутов по трём вариантам: без заголовка 401, чужой 401, верный — штатное поведение, тексты по-русски дословно как в §3.2. Битое тело без заголовка даёт 401, а 422 только с верным заголовком — значит guard отвергает ДО разбора тела, тем более до чтения и записи. Это же доказывает, что контейнеры крутят новый код, а не старый из-за --reload
[LOG] 2026-09-19 19:35 — Reviewer: py_compile по всем изменённым файлам зелёный, но приёмка §3.5 — именно импорт: `python -c "import main"` в семи контейнерах и отдельный импорт perk_evaluator в char-attrs проходят без NameError и без цикла. Подъём блока в locations держится, старые monkeypatch-тесты не правились и зелёные
[LOG] 2026-09-19 19:45 — Reviewer: свипы проверил на «красноту» сам, на КОПИЯХ дерева в scratch (git checkout не трогал — в FEAT-169 так стёрли работу): убрал headers= у inventory main.py:455 и у battle-pass _deliver_diamonds — оба свипа покраснели с указанием файла и строки, плюс покраснели поштучные тесты. Оговорки QA проверил: правило «internal/» ШИРЕ, чем «/internal/», исключить ничего не может, а декораторы отсекаются требованием получателя httpx/client/requests, а не списком исключений — дыры ни там, ни там нет
[LOG] 2026-09-19 19:55 — Reviewer: три замечания QA разобрал. Присваивание токена в test_rewards_in_state.py:124 — чинить сейчас НЕ обязательно: утечка ставит непустой токен, режим отказа шумный и зависит от порядка сбора, набор зелёный (759). Инлайновый словарь battle main.py:4140 с фоллбэком {} — НЕ дыра: это вызывающий, а не guard, с пустым токеном маршрут всё равно ответит 401/503; запись предсуществующая (FEAT-128, 90096f3) и живьём даёт 200. Свип char-attrs по сути верный, слабость только в отсутствии порога. Все три занесены в ISSUES.md как LOW
[LOG] 2026-09-19 20:10 — Reviewer: наборы тестов прогнаны в контейнерах с аргументами CI — battle 759, locations 1354, inventory 1395, user 581, autobattle 151, battle-pass 147, dungeon 155, всё зелёное. Первый прогон battle падал на OSError «could not get source code» — виноват не код, а протухший __pycache__ от прогонов QA с репозиторием в /repo: в .pyc стоит несуществующий в контейнере путь. После очистки кэша 759 passed
[LOG] 2026-09-19 20:20 — Reviewer: 22 падения в char-attrs — НЕ регрессия. Те же тесты на чистом 15e522b в отдельном контейнере с выставленным INTERNAL_SERVICE_TOKEN падают ровно так же (22). Они зелёные в CI только потому, что там переменной нет вовсе. Занесено в ISSUES.md (LOW), FEAT-170 в этом сервисе трогала только perk_evaluator.py
[LOG] 2026-09-19 20:40 — Reviewer: живая проверка игрой, а не curl'ом. Перемещение (leave-on-move и track-event — 200), боевой пост и нападение на моба (action-gate/consume, падает ЗАКРЫТО — 200, бой 220), бой доведён до конца публичными двойниками, и моб ходил КАЖДЫЙ ход на СВЕЖЕМ бою (autobattle register доехал); PvP-нападение (второй закрытый гейт — 200, бой 222) плюс cancel-gathering 200; вход в подземелье (третий закрытый гейт — 200) и семь переходов по комнатам с засадой — dungeon-service опрашивал GET /battles/internal/221/state и получал 200, то есть ловушка §1 закрыта живьём
[LOG] 2026-09-19 20:50 — Reviewer: сбор ресурса доведён до выдачи (free_slots_check и gathering/award — 200, 5 предметов реально начислены), автопрогресс заданий 200 и из inventory, и из battle-service (вызвал настоящий main._internal_token_headers(), заголовок совпадает с env), check-completed из perk_evaluator 200 — новый локальный хелпер §3.6 работает
[LOG] 2026-09-19 20:55 — Reviewer: самое весомое — оба вызывающих, которые пробрасывают ошибку наружу: выдача алмазов боевого пропуска POST /users/internal/4/diamonds/add 200, баланс реально 0 → 5; выдача косметики POST /users/internal/4/cosmetics/unlock 200, рамка реально разблокирована
[LOG] 2026-09-19 21:00 — Reviewer: свип логов всех сервисов на 401/403/503 — необъяснённых нет. Все находки разложены по времени: мои же пробы без заголовка, один 403 на нападение до открытия гейта (правило игры), и 401 на GET /users/me от notification-service с протухшим JWT (предсуществующее, маршрут не internal). 401 на auto-progress в 10:39/10:41 попали в окно прогона pytest внутри контейнеров, а настоящий вызов из кода даёт 200
[LOG] 2026-09-19 21:10 — Reviewer: тестовые данные убраны и проверены перезапросом — персонажи 761 и 214 возвращены на свои места и вылечены, прогресс боевого пропуска и строка награды восстановлены, алмазы снова 0, рамка и предметы удалены, банк узла возвращён, гейты, посты, сессия подземелья и сбора удалены, autobattle перезапущен ради очистки памяти. Чужой персонаж 27 не пострадал. Коммитов не делал
[LOG] 2026-09-19 21:15 — Reviewer: проверка завершена, результат PASS. 17 из 17 маршрутов закрыты и отвергают до чтения и записи, 18 из 18 вызывающих шлют заголовок, ни один игровой путь не сломан. compose, nginx, Alembic, RBAC и фронтенд не тронуты, диффа в claim_reward нет
[LOG] 2026-09-19 22:05 — QA: взял три LOW-замечания Reviewer'а из раздела 5. Правки только в тестах, рабочий код не трогал.
[LOG] 2026-09-19 22:15 — QA: главное — char-attrs. В test_passive_experience.py, test_refund_stamina.py и test_regen.py добавлена autouse-фикстура `monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", INTERNAL_TOKEN)` по образцу test_internal_auth_feat169.py. Причина именно такая, как описано: conftest ставит переменную через `setdefault`, а auth_http ловит её в константу на импорте, поэтому внутри любого контейнера побеждал настоящий токен и запросы получали 401. Проверено, что фикстура несущая: со старыми версиями этих трёх файлов и выставленным INTERNAL_SERVICE_TOKEN падало 16 тестов (`assert 401 == 200`), с новыми — ноль.
[LOG] 2026-09-19 22:20 — QA: в test_internal_auth_feat169.py:566 добавлен порог `checked >= 3` с русским пояснением — форма та же, что у шести свипов FEAT-170. В battle-service test_rewards_in_state.py присваивание токена на уровне модуля заменено на autouse-фикстуру с monkeypatch, утечка на соседние модули закрыта.
[LOG] 2026-09-19 22:45 — QA: прогоны в Docker (весь репозиторий смонтирован в /repo, аргументы CI, CI=true), __pycache__ очищался перед каждым запуском из-за ловушки OSError «could not get source code». char-attrs: без INTERNAL_SERVICE_TOKEN — 478 passed, 2 skipped, 1 xpassed; с выставленным токеном — те же 478 passed, 2 skipped, 1 xpassed. battle-service: без токена — 763 passed; с токеном — 763 passed. Набор больше не зелёный «по недоразумению».
[LOG] 2026-09-19 22:50 — QA: из ISSUES.md удалены три записи Reviewer'а, а также четвёртая — «Хрупкость теста: 16 тестов char-attrs падают при запуске внутри любого контейнера сервиса» (FEAT-169): у неё та же причина и те же файлы, и она закрыта этой же фикстурой.
[LOG] 2026-09-19 17:40 — PM: ревью PASS, гигиена тестов поправлена, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Закрыты **все 17 оставшихся внутренних маршрутов**: локации (6), бои (3), подземелья (2), автобой (1), боевой пропуск (1), алмазы и косметика (4). Теперь ни один не отвечает без токена, даже изнутри сети контейнеров. nginx остался вторым слоем.
- Самые весомые: действие в бою по внутреннему маршруту (ходил за любого участника любого боя), чтение состояния боя (отдавало чужие пояса и награды), начисление и списание алмазов, выдача косметики.
- Работа шла в два захода: **сначала заголовки у всех 18 вызывающих, потом закрытие маршрутов.** Иначе сломались бы подземелья: они опрашивают бой, и делали это без токена.
- В четырёх сервисах появилась проверка токена (бои, подземелья, боевой пропуск, автобой), в характеристиках — свой сборщик заголовков, в локациях проверка поднята в начало файла, иначе сервис не запустился бы.
- Около 230 новых тестов; проверки «любой внутренний вызов обязан слать заголовок» заменили старые списки-исключения, из-за которых проверка проходила не по делу.

### Что изменилось от первоначального плана
- Перечень маршрутов пересобран по коду: в документации было 16, на деле 37 с внутренним префиксом, из них 17 открытых, и вызывающие были указаны неверно почти везде.
- Число тестовых правок в пользователях оказалось 34 вместо 11 — разработчик проверил по коду, а не по плану.
- Маршруты без вызывающих закрыты, но не удалены.

### Найдено попутно
- Регистрации автобоя хранятся в памяти процесса: любая выкатка уже молча останавливает ходы мобов в текущих боях (записано в ISSUES.md, не чинили).
- 16 тестов характеристик были зелёными «по недоразумению» — в CI нет внутреннего токена, а внутри контейнера они падали. Починено.
- Устаревший кэш Python может показать ложное падение проверки — учтено.

### Оставшиеся риски / follow-up задачи
- Анонимное чтение чужих данных (инвентарь, экипировка, характеристики, чат) — нужно продуктовое решение, что публично.
- `GET /attributes/{id}/perks` пишет в базу при чтении.
- Перед пушем на проде должны быть оба секрета — проверено 2026-09-19.
