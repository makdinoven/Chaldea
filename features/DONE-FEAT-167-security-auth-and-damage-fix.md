# FEAT-167: Закрыть открытые эндпоинты (предметы, характеристики) и двойной учёт урона оружия

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-18 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-167-slug.md` → `DONE-FEAT-167-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Три предсуществующие проблемы, найденные по ходу FEAT-164/165 и подтверждённые пользователем на локалке. Все три нужно закрыть до следующего пуша на прод (прод — живой альфа-тест с игроками).

1. **Уязвимость: выдача любого предмета любому персонажу без авторизации.** `POST /inventory/{character_id}/items` (inventory-service) доступен через gateway без токена: запрос без авторизации доходит до обработчика. Любой клиент может положить в инвентарь любого персонажа любой предмет в любом количестве.
2. **Уязвимость: изменяющие эндпоинты character-attributes-service открыты через gateway без авторизации.** `POST /{id}/apply_modifiers`, `POST /{id}/recover`, `PUT /{id}/active_experience`, `PUT /{id}/passive_experience`, `POST /{id}/consume_stamina`, `POST /{id}/refund_stamina`. Можно снаружи вылечить любого персонажа, выдать статы, начислить опыт, обнулить выносливость. Вызываются только другими сервисами.
3. **Баг: урон оружия считается дважды.** Пользователь проверил на локалке (персонаж «Арлекино»): без меча 25 урона, меч даёт +10 силы и +10 урона, с мечом становится 55 вместо 45. Причина по `docs/ISSUES.md`: `build_modifiers_dict` (inventory-service) кладёт `damage_modifier` оружия в атрибут `damage`, а `battle_engine` (battle-service) прибавляет `weapon["damage_modifier"]` ещё раз.

### Бизнес-правила

> **Обновлено 2026-09-18 по решению пользователя (после анализа).** Первоначальное правило «считать урон оружия один раз через общую характеристику `damage`» заменено на модель трёх значений урона: урон оружия НЕ вливается в общую характеристику, а учитывается отдельно по слоту. Причина: иначе навыки «без оружия» перестают быть безоружными, а основная и дополнительная рука становятся численно одинаковыми (см. §2.6, вопросы 1–2).

- **Урон оружия не входит в общую характеристику `damage`.** Характеристика `damage` = «база»: всё неоружейное — статы, броня, украшения, перки, заточка и камни на неоружейных предметах, баффы/еда. Ровно то, что попадает в `damage` сегодня, минус модификаторы урона оружия.
- **В игре три значения урона, все три видны в профиле:**
  - «Основной урон» = база + оружие в основной руке (`main_weapon`);
  - «Дополнительный урон» = база + оружие в дополнительной руке (`additional_weapons`);
  - «Урон без оружия» = только база.
- **`weapon_slot` навыка выбирает, какое из трёх значений применяется:** `no_weapon` → урон без оружия (безоружные навыки по-прежнему игнорируют оружие), `main_weapon` → основной, `additional_weapons` → дополнительный. Тип урона (`damage_type` / `primary_damage_type`) работает как сегодня.
- **Урон оружия учитывается ровно один раз** — нигде нет двойного сложения (исходный баг). Числа в профиле обязаны совпадать с тем, что считает бой.
- Урон оружия считается по фактическому состоянию предмета: базовый модификатор + заточка + вставленные камни этого оружия. Сломанное оружие (прочность 0) даёт 0 урона — как сейчас не даёт и остальных бонусов.
- Правка не должна занижать урон вдвое где-либо ещё: проверить обычный бой, автобой, подземелья, мобов/NPC (у них снаряжение тоже бывает) и тесты battle-service.
- **Закрытые эндпоинты должны остаться рабочими для межсервисных вызовов.** Нельзя ломать существующие вызовы из inventory, dungeon, locations, character-service, battle-service и т.д.: все вызывающие обновить синхронно в этой же задаче.
- Для админских действий (если такие есть среди потребителей, например «выдать предмет» в админке) — проверка разрешения RBAC, а не открытый доступ.
- Ответы на неавторизованные запросы — 401/403 без утечки деталей.
- Ничего из этого не должно быть закрыто «только на уровне nginx», если эндпоинт может быть вызван снаружи: защита в самом сервисе (`verify_internal_token` / JWT / RBAC), nginx — дополнительный слой.

### UX / Пользовательский сценарий
1. Игрок надевает меч «+10 силы, +10 урона» — в профиле «Основной урон» растёт с 25 до 45, «Урон без оружия» становится 35 (сила выросла), «Дополнительный урон» = 35, пока вторая рука пуста. В бою удар этим мечом считает ровно 45.
2. Внешний запрос на выдачу предмета или изменение характеристик без токена получает 401/403.
3. Обычная игра (бои, подземелья, сбор, крафт, экипировка, отдых) работает как раньше.

### Edge Cases
- У уже экипированных персонажей в `character_attributes.damage` сейчас лежит урон надетого оружия — после смены модели это значение становится неверным, нужен одноразовый пересчёт (см. §3.4).
- Бои, идущие в момент деплоя (снапшот участников уже сделан).
- Мобы и NPC со снаряжением.
- Автобой (autobattle-service) использует battle-service — убедиться, что формула одна.

### Вопросы к пользователю (если есть)
- [x] Как чинить двойной урон → **три значения урона** (основной / дополнительный / без оружия), урон оружия отдельно от характеристики `damage`, учитывается один раз, все три видны в профиле
- [x] Навыки `no_weapon` (§2.10 в.1) → остаются безоружными: применяется «урон без оружия»
- [x] Основная vs дополнительная рука (§2.10 в.2) → реально разные значения, `weapon_slot` выбирает нужное
- [x] Разрешение для админской выдачи предмета (§2.10 в.3) → существующее `items:update`, новое разрешение и миграцию RBAC не делаем
- [x] Закрытие эндпоинтов → internal-токен в самих сервисах + nginx вторым слоем, GET-эндпоинты (восстановление FEAT-164) не трогаем
- [x] Когда → до следующего пуша на прод, одной задачей с двумя дырами
- [x] Заточка/камни на оружии → относятся к этому оружию (в `effective_damage`), а не в базу; на броне и украшениях — в базу
- [x] Право на админскую выдачу предметов → `items:update`, модератор без этого права кнопку видит, но получает понятный отказ (оставляем как есть)
- [x] Сломанное оружие → даёт 0 урона, и в профиле нужна пометка «оружие сломано» (всё едет одним деплоем)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline: current working tree (FEAT-166 profile redesign is uncommitted and under review — none of its files are touched by this analysis or needed by this feature, except one read-only note in §2.6 about `DerivedStatsSection.tsx`, which the redesign did **not** modify).

### 2.1. Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| inventory-service | add `verify_internal_token` helper; gate `POST /inventory/{cid}/items`; add an admin-gated variant for the admin UI | `app/auth_http.py`, `app/main.py:368` |
| character-attributes-service | add `verify_internal_token` helper; gate 6 mutating endpoints | `app/auth_http.py` (new dep), `app/main.py:723,886,925,959,992,1044` |
| battle-service | send `X-Internal-Token` on the inventory item-grant call; **remove the duplicate weapon damage term** | `app/main.py:356`, `app/battle_engine.py:156-157` (+ dead twin at `:85-86`) |
| battle-pass-service | send `X-Internal-Token`; needs the env var (missing!) | `app/crud.py:534`, `app/config.py` |
| dungeon-service | send `X-Internal-Token` on 3 calls | `app/http_clients.py:183,214,248` |
| locations-service | send `X-Internal-Token` on 6 calls (today they forward the *player's* Authorization or nothing) | `app/main.py:1340,1600,2184,2739,3040`, `app/crud.py:7196,7582` |
| skills-service | send `X-Internal-Token` on the XP deduction | `app/main.py:700-709` |
| party-service | send `X-Internal-Token` on 2 XP calls + the settle-regen call; needs the env var (missing!) | `app/main.py:52,66`, `app/crud.py:22`, `app/config.py` |
| character-service | send auth on the level→XP sync call (see §2.3 note) | `app/main.py:747-760` |
| frontend | admin "issue item" must hit the admin-gated route; damage display must drop the duplicate term | `src/api/items.ts:128`, `src/api/adminCharacters.ts:159`, `src/components/ProfilePage/StatsTab/DerivedStatsSection.tsx:58`, `src/components/ProfilePage/CharacterTab/IndicatorsPanel.tsx:33-34` |
| DevSecOps (compose) | `INTERNAL_SERVICE_TOKEN` for party-service and battle-pass-service | `docker-compose.yml`, `docker-compose.prod.yml` |
| nginx (optional 2nd layer) | `/attributes/` and `/inventory/` currently proxy everything | `docker/api-gateway/nginx.conf:193-228`, `nginx.prod.conf:212-244` |

No DB schema change and no Alembic migration are needed for any of the three items (see §2.7).

### 2.2. Hole #1 — `POST /inventory/{character_id}/items`

**Handler:** `services/inventory-service/app/main.py:368` `add_item_to_inventory(character_id, item_data, db)`. Zero auth dependencies, no ownership check, no quantity ceiling beyond `max_stack_size` splitting. Confirmed unreachable-by-accident only: nginx proxies `/inventory/` wholesale (`nginx.conf:221`, `nginx.prod.conf:237`).

**Auth machinery already in this service** — `services/inventory-service/app/auth_http.py`:
- `get_current_user_via_http` (`:24`) — validates JWT via `GET {AUTH_SERVICE_URL}/users/me`
- `get_admin_user` (`:46`) — admin **or** moderator
- `require_permission("module:action")` (`:57`) — granular, reads `user.permissions`
- **No `verify_internal_token`.** It only has the *outgoing* helper `_internal_token_headers()` at `main.py:28-33`.

Neighbouring endpoints for comparison: `GET /{cid}/items` (`:324`) open; `DELETE /{cid}/items/{iid}` (`:414`) uses `get_current_user_via_http` + `verify_character_ownership`; item-catalog admin routes use `require_permission("items:create"/"items:update"/...)`; `/inventory/internal/*` (`:687, 1497, 1575, 1604, 3461`) have **no** service-side check at all, only the nginx `return 403` (`nginx.conf:217`).

**Every caller (full repo sweep, incl. raw URLs):**

| # | Caller | file:line | Kind | Sends today |
|---|--------|-----------|------|-------------|
| 1 | battle-service — PvE loot drop to winner | `battle-service/app/main.py:356` | internal | nothing |
| 2 | battle-pass-service — `_deliver_item` (season reward) | `battle-pass-service/app/crud.py:534` | internal | nothing |
| 3 | dungeon-service — `add_item_to_character` | `dungeon-service/app/http_clients.py:248` | internal | nothing |
| 4 | locations-service — location loot pickup | `locations-service/app/main.py:2184` | internal | forwards **player** `Authorization` |
| 5 | locations-service — NPC shop purchase | `locations-service/app/main.py:2739` | internal | forwards **player** `Authorization` |
| 6 | locations-service — quest reward item | `locations-service/app/main.py:3040` | internal | forwards **player** `Authorization` |
| 7 | Admin UI — Items admin "Выдать предмет" | `src/api/items.ts:128` `issueItem` → `components/ItemsAdminPage/IssueItemModal.tsx:60` | admin UI | player/admin JWT (axios interceptor) |
| 8 | Admin UI — Characters admin, inventory tab | `src/api/adminCharacters.ts:159` `addInventoryItem` → `redux/slices/adminCharactersSlice.ts:256` | admin UI | player/admin JWT |

**No player-facing caller exists.** Gathering awards do *not* go through this route — they use the dedicated `POST /inventory/internal/characters/{cid}/gathering/award` (`locations-service/app/crud.py:6256` → `inventory-service/app/main.py:1604`). Crafting writes inventory in-process.

So the route has exactly two audiences: 5 internal services and 2 admin UI screens. It can be split cleanly: internal route behind `verify_internal_token`, admin route behind `require_permission("items:update")` (or a new `items:grant`). Note the 3 locations-service calls forward a *player* token today — after the change they must send the internal header instead; the player's ownership is already validated upstream in locations-service before the call.

### 2.3. Hole #2 — the six character-attributes-service endpoints

All six are on `router = APIRouter(prefix="/attributes")` with **no** dependency of any kind:

| Endpoint | file:line | Callers (file:line) | Sends today |
|---|---|---|---|
| `POST /{id}/apply_modifiers` | `main.py:723` | **only** inventory-service `main.py:707` `apply_modifiers_in_attributes_service`, used from 12 sites (`:501, 864, 901, 1006, 2577, 2858, 2951, 3349, 3506, 3700, 3702, 3738` — equip/unequip, gems, sharpening, durability-zero, NPC equip) | nothing |
| `POST /{id}/recover` | `main.py:886` | inventory-service `main.py:749` (`use_item` recovery); dungeon-service `http_clients.py:214` `recover_character` | nothing |
| `PUT /{id}/active_experience` | `main.py:925` | skills-service `main.py:700` `deduct_active_experience`; party-service `main.py:52` `_charge_active_xp` | nothing |
| `PUT /{id}/passive_experience` | `main.py:959` | party-service `main.py:66` `_award_passive_xp` | nothing |
| `POST /{id}/consume_stamina` | `main.py:992` | locations-service `main.py:1340` (travel), `main.py:1600`, `crud.py:7196` (gathering); dungeon-service `http_clients.py:183` | nothing |
| `POST /{id}/refund_stamina` | `main.py:1044` | locations-service `crud.py:7582` (used at `:7708, :7776`) | nothing |

**No frontend caller for any of the six** (verified by sweeping `.ts`/`.tsx`). The only attributes mutation the UI performs is `POST /attributes/admin/{id}/grant_active_xp` (`adminCharacters.ts:136`), which is already `require_permission("characters:update")` (`main.py:1165-1170`), plus `POST /{id}/upgrade` which uses `get_current_user_via_http` (`main.py:523-528`). So all six can become internal-only without any UI work.

**Internal-endpoint protection in this service:** there is **none**. `POST /internal/settle-regen` (`:422`), `POST /internal/{id}/satiety` (`:439`) and `POST /internal/{id}/reconcile-perks` (`:1365`) rely solely on the nginx `location /attributes/internal/ { return 403; }` (`nginx.conf:193`, `nginx.prod.conf:212`). The service has **no** `verify_internal_token`; it only has the *outgoing* helper `main.py:24-26` and the `INTERNAL_SERVICE_TOKEN` setting at `config.py:19`. `auth_http.py` here exports only `get_current_user_via_http` / `get_admin_user` / `require_permission` / `UserRead` (`main.py:15`).

**nginx today:** `/attributes/internal/` → 403; `/attributes/` → plain proxy_pass, no auth (`nginx.conf:193-205`, `nginx.prod.conf:212-224`). Same shape for `/inventory/` (`nginx.conf:217-228`, `nginx.prod.conf:233-244`). Per §1 the fix must live in the service; nginx is at most an extra layer.

**FEAT-164 interaction — important, and it does *not* block the fix.** Regen catch-up now runs inside the **GET** paths: `GET /attributes/{id}` (`main.py:341-351` → `regen.settle_character`) and `GET /attributes/{id}/rest-status` (`main.py:372`). Those are **reads** and are **not** in the list of six — they must stay reachable, because they are consumed by battle-service (`battle_engine.py:27` `fetch_full_attributes`, called live on every attack), skills-service (`main.py:738-745` `get_active_experience`), character-service (`main.py:1379, 1926, 2844`) and the player profile UI. **Recommendation: do not gate the GETs.** Consequences:
- party-service's settle call targets `POST /attributes/internal/settle-regen` (`party-service/app/crud.py:22`) — a *different* route from the six, already nginx-blocked, already tokenless. Leaving it as-is keeps party working; if the Architect decides to also gate `/internal/*` in this service, party-service **must** get `INTERNAL_SERVICE_TOKEN` first (it has none — see §2.5).
- battle start (`battle-service/app/main.py:196` `build_participant_info` → `fetch_full_attributes`) and mid-battle attribute reads are GET-only → untouched.
- Food/satiety (`inventory-service/app/main.py:3184` → `/attributes/internal/{id}/satiety`) is also outside the six.

**Pre-existing side finding (do not fix here, see §2.8):** `character-service/app/main.py:755` PUTs `/attributes/admin/{character_id}` to sync `passive_experience` on a level change. That route is `require_permission("characters:update")` (`main.py:1083-1088`) and character-service sends **no** Authorization header — so this sync is silently failing today (the call site logs a warning and continues, `main.py:766-772`).

### 2.4. Existing internal-auth machinery (the pattern to copy)

Two equivalent implementations exist; they behave identically:
- `services/character-service/app/auth_http.py:78-95` — module-level `INTERNAL_SERVICE_TOKEN = os.environ.get(...)`, `verify_internal_token(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"))`; **fail-closed**: empty env → always reject (503), missing/mismatched header → 401. Used via `Depends(verify_internal_token)` on all 14 `/characters/internal/*` routes.
- `services/locations-service/app/main.py:3692-3718` — same, inline in `main.py`; used at `:3756, :3791`.
- skills-service has a different flavour: `app/auth_http.py:58-68` accepts the internal token *as a Bearer token* in place of a user (returns `None` for the user) — do **not** copy that shape for these endpoints.

There is **no** shared package — each service has its own copy. inventory-service and character-attributes-service each need their own `verify_internal_token` added (put it in their `auth_http.py`; char-attrs already imports from there at `main.py:15`).

**Outgoing side** — helpers already exist and only need to be *passed* to the relevant calls: `inventory-service/app/main.py:28`, `character-attributes-service/app/main.py:24`, `dungeon-service/app/http_clients.py:26`, `battle-service/app/main.py:65`, `locations-service/app/crud.py:24-27` and `main.py:3696-3701`, `character-service/app/locations_client.py:175`. battle-pass-service and party-service have **no** helper and **no** setting.

**Known debt (ISSUES.md HIGH):** `INTERNAL_SERVICE_TOKEN` has the publicly-known fallback `dev-internal-token-change-me` in both compose files. After this feature that token becomes the *only* application-layer guard for another ~12 routes, which raises the stakes of that entry. Worth escalating in the same push (prod `.env` value + `.env.example` stub), but it is a separate ISSUES item, not part of this feature's code.

### 2.5. Blocker: missing `INTERNAL_SERVICE_TOKEN` for two callers

`INTERNAL_SERVICE_TOKEN` is currently injected for: celery-worker, character-attributes-service, skills-service, inventory-service, character-service, locations-service, battle-service, dungeon-service (`docker-compose.yml:135,311,338,366,398,429,493,585`).

**Not injected anywhere (neither dev nor prod): `party-service` (`docker-compose.yml:607-618`, `docker-compose.prod.yml:261`) and `battle-pass-service` (`docker-compose.yml:537`, `docker-compose.prod.yml:174`).** Both are callers of endpoints this feature is closing (party → `active_experience`/`passive_experience`; battle-pass → `POST /inventory/{cid}/items`). Without the env var they would start sending an empty header and get 401 → **silent loss of party XP and of battle-pass item rewards**. Adding the var to both compose files is a hard prerequisite of this feature.

`docker-compose.prod.yml` overrides `environment:` for skills, character, locations, battle-pass, notification, battle, autobattle, dungeon, party, celery-worker. Both files use map syntax, so Compose merges the maps per key and the base value should carry — but DevSecOps should confirm with `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` for character-attributes-service, inventory-service and locations-service rather than assume it (an ISSUES note from FEAT-162 claims prod did *not* inherit for dungeon-service).

### 2.6. Bug #3 — the weapon damage double-count

**How `damage` reaches the battle:**
1. `character_attributes` has a single `damage` column (`character-attributes-service/app/models.py:44`). There is **no** `damage_modifier` column on the attributes table (the §1 brief's wording is a shorthand) — `damage_modifier` is a column on `items`.
2. `compute_derived_stats` (`char-attrs/app/crud.py:39-65`) **seeds** `attr.damage = <class main attribute>` (`:63`; `CLASS_MAIN_ATTRIBUTE` 1=strength/2=agility/3=intelligence), or `0` when the class is unknown. This runs on attribute creation (`:104`), on `/{id}/recalculate` and on `/admin/recalculate_all` — **not** on every equip.
3. Equipping writes flat deltas: `inventory-service/app/crud.py:533` `build_modifiers_dict` puts the item's `damage_modifier` into the `"damage"` key at **`crud.py:571`**, and the dict is POSTed to `/attributes/{id}/apply_modifiers` via `inventory-service/app/main.py:707`. Unequip sends the same dict negated.
4. On the receiving side `apply_modifiers` → `_apply_modifiers_internal` (`char-attrs/app/crud.py:536`) adds `"damage"` as a plain additive key (`simple_keys`, `:586-588`). A `strength` delta propagates to resists/dodge (`:607-630`) but **does not** touch `damage`.
   → **`attr.damage` = (main attribute as of the last recalculate) + Σ(all equipped items' `damage_modifier`) + perk/sharpening/gem damage bonuses.** Weapon damage is already in there, exactly once.
5. Battle: `battle-service/app/main.py:2796` is the single live call site. Attributes are fetched **live** per attack (`main.py:2270-2276` `attrs()` → `battle_engine.py:27` `fetch_full_attributes`) and weapons **live** (`main.py:2278` `fetch_weapons` → `battle_engine.py:34-58`, which reads `/inventory/{cid}/equipment` then `/inventory/items/{item_id}` for `main_weapon` / `additional_weapons`). `weapon["damage_modifier"]` is therefore the **base item template** value, not the sharpened/socketed one.
6. `battle_engine.py:154-157`:
   ```
   base_stat    = attacker_attr[CLASS_MAIN_ATTRIBUTE[class_id]]
   damage_bonus = attacker_attr["damage"]          # already contains the weapon
   weapon_mod   = weapon["damage_modifier"]        # ← counted a second time
   base = max(0, base_stat + damage_bonus + weapon_mod)
   ```

**Arithmetic check against the user's report** (Арлекино, sword +10 str / +10 dmg, class whose main attribute recalculated to a `damage` seed of 0 — i.e. `attr.damage` holds only flat bonuses): unarmed `base = 25 + 0 = 25`; armed `base = 35 + 10 + 10 = 55`; correct value `35 + 10 = 45`. Matches the observed 25 / 55 / expected-45 exactly.

**The line that must change: `services/battle-service/app/battle_engine.py:156-157`** — drop `weapon_mod` from the sum. The `weapon` argument must be **kept**, because `:158-159` still uses `weapon["primary_damage_type"]` to resolve `damage_type == "all"`, and `log["base"]` is still emitted.

**The dead twin:** `battle_engine.py:85-86` in `compute_single_damage_entry` has the same duplicate (`base_attack_value = attacker_attr["damage"]` then `+= weapon_item["damage_modifier"]`). That function is **not imported by `main.py`** (`main.py:45` imports only `compute_damage_with_rolls` and friends) and has no other caller — dead code. Fix it identically or delete it; leaving it is a trap for the next reader.

**Everywhere else weapon damage could be added — all clear:**
- **Mobs / NPCs:** NPC gear is equipped through `inventory-service/app/main.py:3682` (`POST /inventory/admin/npc/{cid}/equip`) which calls `apply_modifiers_in_attributes_service` (`:3700-3702`). So NPC weapon damage is in `attr.damage` too, and mobs go through the *same* `compute_damage_with_rolls`. The fix applies symmetrically — no separate NPC path.
- **autobattle-service:** does **no** damage math (only skill selection / feature scoring, `app/main.py:223-237`); it drives battle-service's attack endpoint. Parity is automatic — one formula.
- **dungeon-service:** its damage is flat trap/event config (`app/gameplay.py:1921, 2571`), unrelated to weapons. Dungeon combat itself is battle-service.
- **skills / perks:** skill `damage_entries[].amount` is added separately at `battle_engine.py:161` and never involves the weapon; perk damage bonuses flow through `apply_modifiers` (`perk_evaluator.py:305, 408, 416`) into `attr.damage` — counted once.
- **Sharpening / gems / refine:** all go through `apply_modifiers` (`inventory-service/app/main.py:2577, 2858, 2951, 3349`) into `attr.damage`. Since the battle only ever re-added the **base template** `damage_modifier`, those bonuses were *never* double-counted — only the base weapon value was, and only that duplicate disappears.
- **Broken equipment:** `build_modifiers_dict` returns `{}` for a 0-durability item (`crud.py:543-545`) and durability-zero strips modifiers (`main.py:3506`), so a broken weapon contributes nothing to `attr.damage`. **Today** the battle still re-adds its raw `damage_modifier` via `fetch_weapons` (which does not read durability) — so the fix incidentally *also* fixes broken weapons still dealing their bonus damage. Worth a test.

**Same triple-sum in the UI:** `services/frontend/app-chaldea/src/components/ProfilePage/StatsTab/DerivedStatsSection.tsx:58` computes `mainAttrValue + damageBonus + mainWeaponDamageModifier`, fed by `CharacterTab/IndicatorsPanel.tsx:33-34` (`equipment.find(slot_type==='main_weapon')?.item?.damage_modifier`). Neither file is touched by the FEAT-166 redesign. To satisfy §1's "profile shows the final number and battle matches", line 58 must drop the third term; the `mainWeaponDamageModifier` prop and the `IndicatorsPanel` lookup then become dead and should go with it. (The user reported 45 in the profile, which this code would render as 55 — the Reviewer should check live whether the weapon's `damage_modifier` actually arrives in the equipment payload, since `?.item?.damage_modifier ?? 0` silently yields 0 when the nested `item` is partial. Either way the correct end state is the two-term sum.)

**Semantic consequences of counting once — needs a product decision (see §2.9):** with `weapon_mod` gone from the formula,
- `weapon_slot: "no_weapon"` damage entries (`battle-service/app/main.py:2799-2804`) stop meaning "unarmed": the equipped weapon's damage still counts, because it lives in the attribute. Unarmed skills get stronger relative to today.
- a `main_weapon` entry and an `additional_weapons` entry become **numerically identical** (both weapons' modifiers are in `attr.damage` regardless of slot). `weapon_slot` would then only select the `primary_damage_type`.

### 2.7. DB changes / migration / backfill

**None needed.**
- No schema change for any of the three items.
- No backfill for the damage bug: `attr.damage` is **already correct** (weapon counted once). Only the runtime formula over-counted, and that value is never persisted. Nothing stored is wrong.
- In-flight battles: safe. Attributes and weapons are re-fetched **live** on every attack (`main.py:2276, 2278`); the `attributes` blob in `build_participant_info` (`main.py:196-243`) is a display snapshot only. A battle in progress at deploy time simply deals correct damage from the next turn on. No Redis/Mongo state carries the formula.
- Per-service Alembic already exists everywhere touched; none of the three fixes needs a revision. No new RBAC permission is required if the admin item-grant reuses `items:update` — if the Architect prefers a new `items:grant`, that **does** need an Alembic revision in user-service **plus** an explicit seed block in `test_rbac_permissions.py::TestAdminAutoPermissions` (CLAUDE.md §10.13: new permissions are not covered automatically).

### 2.8. Tests that encode the current (buggy / open) behaviour

**Damage — battle-service (assert the triple sum; every one must be re-baselined):**
- `app/tests/test_class_damage_luck.py` — `test_class_damage_with_weapon` (`:292-310`, `assert log["base"] == 45`, `final == 50.0`); `test_no_weapon_is_attribute_only` (`:312-338`, asserts `40.0` / `25.0` and `with_weapon - no_weapon == 15.0` — this test *codifies* the duplicate and its premise is what §2.6 changes); group-2 cases at `:207, 226, 245, 264, 283` and `:352, 390, 415, 445`.
- `app/tests/test_weapon_slot.py` — the file's whole premise (`:8-12`: "weapon_mod from main_weapon / from additional_weapons"); assertions at `:393-395` (base 30), `:413-415` (22), `:435-441` (25), `:458-461` (15), `:514-541` (25/20), `:550-569` (25), `:578-595` (15). After the fix, main vs additional slots produce the same number — the *value* tests collapse and should be rewritten around `primary_damage_type` selection instead.
- `app/tests/test_dodge_and_freshness.py:36` holds a reference to the real `compute_damage_with_rolls` — check its numeric expectations.
- Mock-based suites are unaffected (they patch `main.compute_damage_with_rolls`): `test_admin_battles`, `test_battle_fixes`, `test_battle_history`, `test_battle_preview`, `test_endpoint_auth`, `test_item_usage`, `test_join_requests`, `test_npc_death`, `test_pve_rewards`, `test_pvp_*`, `test_rewards_in_state`, `test_spectate`.
- **New tests wanted:** profile-formula parity (attribute-only base), broken-weapon contributes nothing, NPC-with-weapon parity.

**Open access — inventory-service:**
- `app/tests/test_add_item_to_inventory.py` — ~13 unauthenticated `client.post("/inventory/{n}/items")` calls (`:44, 62, 78, 101, 125, 152, 174, 175, 189, 200, 222, 252, 276`). All need the new header (or the new route path). Mechanical, no assertion changes.
- `app/tests/test_endpoint_auth.py` — documents only `I3: DELETE /inventory/{cid}/items/{iid}` (`:5, 137-172`); **has no case for the POST**, which is why the hole survived. Add no-header → 401/503, wrong-header → 401, admin-without-permission → 403, good-header → 201.
- Indirect: `test_admin_auth.py`, `test_gathering.py`, `test_item_conversions_admin.py`, `test_item_rarity_rules.py`, `test_item_type_rules.py`, `test_resource_subcategory_rules.py`, `test_trade.py`, `test_trade_atomicity.py` all touch `/items` paths — re-run and patch fixtures that seed inventory through the HTTP route.

**Open access — character-attributes-service and its callers:**
- char-attrs: `app/tests/test_refund_stamina.py`, `test_passive_experience.py`, `test_perks.py`, `test_regen.py` call the six endpoints in-process → add the header.
- Caller-side: locations `test_gathering_ingredient.py`, `test_post_xp.py`, `test_bp_tracking.py`; dungeon `test_gameplay.py`; skills `test_character_skill_upgrade.py`, `test_player_tree_endpoints.py`. Follow the FEAT-162 precedent (pin the module constant, add `headers=`, change no assertions).
- **Coverage gap to close:** neither party-service nor battle-pass-service has any test asserting the outgoing header — and those are exactly the two services missing the env var (§2.5). `docs/ISSUES.md` already records the same class of gap from FEAT-162 (`test_pvp_death_duel.py` rewrites httpx in-test and would not catch a missing header). QA should assert the header on the *real* client function, not a re-implementation.

### 2.9. Risks

| Risk | Mitigation |
|---|---|
| **Missing env var breaks party XP and battle-pass rewards silently** (§2.5) — both callers log-and-continue on failure (`party-service/app/main.py:57-58,70-71`; `battle-pass-service/app/crud.py:539`) | Add `INTERNAL_SERVICE_TOKEN` to both services in **both** compose files *in the same commit*; QA asserts the header; Reviewer verifies live that a party XP tick and a BP item reward still land |
| **Fail-closed helper + unset env = 503 for every internal call.** `verify_internal_token` rejects when the env var is empty | The fallback in compose means dev works; prod must have the var. Verify with `docker compose config` before the push (§2.5) |
| 3 locations-service calls currently forward the **player's** token; swapping to the internal header changes who the callee trusts | Ownership is already validated in locations-service before each call (loot ownership `main.py:2178-2180`, currency check `:2733`, quest ownership). No behaviour change for players |
| **Gating a GET would break battle start / skills XP / the profile** | Do **not** touch `GET /attributes/{id}` or `/rest-status` — they are not in the six, and FEAT-164 put regen catch-up inside them (§2.3) |
| Admin UI stops working if the route becomes internal-only | Two audiences → two routes (or one route accepting internal-token **or** `require_permission`). Both admin call sites (`items.ts:128`, `adminCharacters.ts:159`) must be repointed and their error paths must surface a Russian message |
| In-flight battles at deploy | No risk: attributes/weapons are fetched live per attack; snapshot is display-only (§2.7) |
| autobattle divergence | None: autobattle does no damage math, it drives battle-service (§2.6) |
| Balance shift: `no_weapon` entries and off-hand entries change meaning (§2.6) | Product decision — see the question below |
| Perceived nerf for players mid-alpha: everyone's effective damage drops by their weapon's base `damage_modifier` | Expected and intended per §1; worth a short in-game note. No data migration |
| `INTERNAL_SERVICE_TOKEN` public fallback becomes load-bearing for ~12 more routes | Escalate the existing ISSUES.md HIGH entry: real secret in prod `.env` + `.env.example` stub, same push |

### 2.10. Questions needing a non-technical (product) decision

1. **`weapon_slot: "no_weapon"` skills** (§2.6): after counting weapon damage once via the attribute, an "unarmed" skill can no longer exclude the equipped weapon's damage — the attribute carries it. Accept that (unarmed skills get stronger), or should the engine subtract the weapon's base `damage_modifier` for `no_weapon` entries to preserve the current intent?
2. **`main_weapon` vs `additional_weapons` damage entries** become numerically identical (both weapons are in the attribute) and `weapon_slot` would only pick the damage *type*. Is that acceptable, or should off-hand damage be modelled separately later?
3. **Admin "issue item" permission**: reuse the existing `items:update`, or introduce a dedicated `items:grant` (extra Alembic revision in user-service + an explicit RBAC test seed)?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0. Scope, principles, shipping constraint

Three independent problems, one deploy. They are independent in code but **must ship together**: the item-grant route changes path for internal callers (§3.3.1) and the damage model changes the meaning of `character_attributes.damage` (§3.1) — a partial deploy leaves either silent 401s or wrong damage.

Guiding decisions:
1. **One owner per number.** Weapon damage is owned by inventory-service (it owns `equipment_slots`, sharpening, gems, durability). Everyone else *reads* it; nobody re-derives it from `items.damage_modifier` any more.
2. **Derived on read, nothing new stored.** No column is added to `character_attributes`, no schema migration. The three damage values are computed where they are consumed, from two inputs: base `damage` (char-attrs) + per-slot effective weapon damage (inventory).
3. **Auth in the service, nginx as a second layer** (§1). Fail-closed internal-token pattern copied verbatim from `character-service/app/auth_http.py:78-95`.
4. **No new RBAC permission, no user-service Alembic revision** (user decision): the admin item-grant reuses `items:update`.

---

### 3.1. Damage model — three values

#### 3.1.1. Definitions

```
base            = <class main attribute> + character_attributes.damage
                  (damage = perks + armour/jewellery + their sharpening/gems + buffs/food)
weapon_dmg(slot) = effective damage of the item equipped in `slot`
                  = items.damage_modifier
                  + 1 × enhancement_bonuses["damage_modifier"]      (sharpening, +1 per point)
                  + Σ socketed gems' damage_modifier
                  = 0.0 if the item is broken (max_durability > 0 and current_durability <= 0)
                  = 0.0 if the slot is empty

Основной урон        = base + weapon_dmg("main_weapon")
Дополнительный урон  = base + weapon_dmg("additional_weapons")
Урон без оружия      = base
```

Interpretation note (flagged to PM in §3.9): **sharpening and gems on the weapon itself belong to that weapon**, not to `base`. Otherwise sharpening a sword would raise unarmed and off-hand damage too. Sharpening/gems on armour and jewellery stay in `base`, exactly as today.

#### 3.1.2. inventory-service — stop folding weapon damage into `damage`

`crud.build_modifiers_dict()` keeps its current shape and gains one parameter:

```python
WEAPON_SLOTS = ("main_weapon", "additional_weapons")

def build_modifiers_dict(item_obj, negative=False, enhancement_bonuses=None,
                         gem_items=None, current_durability=None, max_durability=0,
                         slot_type: str | None = None) -> dict:
    ...
    # last step, after sharpening + gems are folded in, before the `negative` flip:
    if slot_type in WEAPON_SLOTS:
        mods.pop("damage", None)
    ...
```

To guarantee the two computations can never drift, the damage arithmetic lives in **one** new helper that `build_modifiers_dict` and the equipment response both call:

```python
def compute_item_damage(item_obj, enhancement_bonuses=None, gem_items=None,
                        current_durability=None, max_durability=0) -> float
```

It returns exactly the number `build_modifiers_dict` would have put in `mods["damage"]` (0.0 when broken / no damage). **Anti-drift requirement: `build_modifiers_dict` must obtain its `damage` value from `compute_item_damage`, not from a second copy of the arithmetic.**

`slot_type=` must be passed at **every** site that applies modifiers for an *equipped* item — otherwise weapon damage silently keeps leaking into `damage` (this is exactly the FEAT-162-class silent-failure pattern, so the Reviewer checks the list):

| # | Site | Slot source |
|---|---|---|
| 1 | `main.py:496` `_revalidate_equipment` removal | `slot.slot_type` |
| 2 | `main.py:862` equip — auto-return of the replaced item | `slot.slot_type` |
| 3 | `main.py:899` equip — new item | `slot.slot_type` |
| 4 | `main.py:1004` unequip | `slot.slot_type` |
| 5 | `main.py:2577` sharpening delta (`is_equipped`) | equipped row's `slot_type` — skip the `damage` key for weapon slots |
| 6 | `main.py:2858` gem socket (`is_equipped`, manual dict) | same — drop `damage` from `gem_only_mods` |
| 7 | `main.py:2951` gem unsocket (`is_equipped`, manual dict) | same — drop `damage` from `gem_neg_mods` |
| 8 | `main.py:3349` repair of a broken equipped item | equipped row's `slot_type` |
| 9 | `main.py:3506` durability-zero break | `entry.slot_type` / `slot.slot_type` |
| 10 | `crud.py:361, 373` `admin_equip_npc_item` | `slot_type` argument |
| 11 | `crud.py:408` `admin_unequip_npc_item` | `slot_type` argument |

Not changed: `main.py:3175` (food payload — display/consumable, no slot) and `use_item` recovery. Food damage buffs stay in `base`, as decided.

Result: **`character_attributes.damage` becomes base-only.** No schema change; the stored value's *meaning* changes, which is why §3.4 backfills it.

#### 3.1.3. inventory-service — expose effective weapon damage

`GET /inventory/{character_id}/equipment` gains one **additive, read-only** field per slot: `effective_damage: float` (0.0 for non-weapon/empty/broken). It is computed in `crud` from the slot row (`item`, `enhancement_bonuses`, `socketed_gems`, `current_durability`) via `compute_item_damage`.

Why this endpoint and not a new one: battle-service's `fetch_weapons` **already** calls it, and the frontend already keeps it in `profileSlice.equipment`. Both consumers get the number with zero extra HTTP calls, and it stays a single source of truth. The endpoint is a GET already reachable without auth — the new field exposes no more than the item template it already returns.

#### 3.1.4. battle-service — one formula, weapon counted once

`battle_engine.fetch_weapons()` attaches the slot's number to the weapon dict it returns:

```python
result[slot_type] = {**item_resp.json(), "effective_damage": float(slot.get("effective_damage") or 0.0)}
```

`compute_damage_with_rolls()`:

```python
base_stat    = attacker_attr.get(main_attr_key, 0)     # class main attribute
damage_bonus = attacker_attr.get("damage", 0)          # base — no weapon inside any more
weapon_dmg   = float(weapon.get("effective_damage") or 0.0) if weapon else 0.0
base = max(0, base_stat + damage_bonus + weapon_dmg)
```

- The duplicate `weapon["damage_modifier"]` term is **gone**; the template field is no longer read for damage anywhere in battle-service.
- `weapon` is still passed and still resolves `damage_type == "all"` via `weapon["primary_damage_type"]` — unchanged.
- `weapon_slot` selection at `main.py:2799-2805` stays as it is: `no_weapon` → `weapon=None` → `weapon_dmg = 0.0` → unarmed value; `main_weapon` / `additional_weapons` → that slot's weapon. An unknown slot keeps resolving to unarmed. This now genuinely produces three different numbers.
- **Broken weapon (durability 0):** `effective_damage = 0.0`, but the weapon object is still returned, so it still occupies the slot and still provides `primary_damage_type`. So a broken sword deals base damage of the "unarmed" size while keeping its damage type — consistent with `build_modifiers_dict` returning `{}` for broken items, and it removes today's bug where a broken weapon still added its `damage_modifier` in battle.
- **Dead twin `compute_single_damage_entry` (`battle_engine.py:72-121`): delete it.** It is imported by nobody (`main.py:45` imports only `compute_damage_with_rolls`, `fetch_weapons`, `fetch_main_weapon`, `apply_flat_modifiers`, `roll_*`), and leaving a second, wrong damage formula in the file is the trap that produced this bug. If any test imports it, the test goes with it.
- `fetch_main_weapon` (`:61`) is a thin wrapper — keep, it is used elsewhere in `main.py`.
- `build_participant_info` (`main.py:196-243`) keeps its display-only attribute snapshot; no three-value fields added there (battle UI does not show damage). Out of scope.

#### 3.1.5. Where each value is computed (and why nowhere else)

| Value | Computed in | Inputs |
|---|---|---|
| `base` (stored) | char-attrs `character_attributes.damage`, accumulated by `apply_modifiers` | inventory/perks/buffs deltas, weapon damage now excluded at the source |
| `weapon_dmg(slot)` | **inventory-service** `crud.compute_item_damage`, surfaced as `effective_damage` on the equipment response | slot row |
| Battle base per damage entry | battle-service `battle_engine.compute_damage_with_rolls` | live GET attributes + live GET equipment |
| The three profile numbers | **frontend** `StatsTab/DerivedStatsSection.tsx` via one shared helper | `attributes` + `equipment[].effective_damage` from `profileSlice` |

**Deliberately rejected:** returning the three values from `GET /attributes/{id}`. That would make character-attributes-service call inventory-service, creating a cycle (`inventory → char-attrs → inventory`) on the hottest read in the game (battle-service fetches attributes on every attack, FEAT-164 regen also runs there). The cost is that the formula `base = main_attr + damage` exists in two places (engine + frontend) — as it already does today; QA task #11/#13 pins them to the same numbers.

---

### 3.2. API contracts

#### 3.2.1. `GET /inventory/{character_id}/equipment` — additive field (no auth change)

**Response `200`** (`List[EquipmentSlot]`), new field marked `NEW`:
```json
[
  {
    "id": 12, "character_id": 7, "slot_type": "main_weapon", "item_id": 331,
    "is_enabled": true, "enhancement_points_spent": 3,
    "enhancement_bonuses": "{\"damage_modifier\": 2}",
    "socketed_gems": "[404, null]", "current_durability": 57,
    "effective_damage": 17.0,
    "item": { "...": "unchanged" }
  }
]
```
`effective_damage: float = 0.0` (Pydantic v1, `EquipmentSlotBase`). Backward compatible: existing consumers ignore it. Because the handler must enrich ORM rows, `crud.get_equipment_slots()` gains a sibling that returns dicts (ORM fields + `effective_damage`); `response_model` stays `List[schemas.EquipmentSlot]`.

Consumers to keep working: battle-service `fetch_weapons`, frontend `profileSlice`, admin `fetchCharacterEquipment`, `AdminNpcsPage/NpcEquipmentEditor`, `NpcStatsEditor`.

#### 3.2.2. `POST /inventory/internal/characters/{character_id}/items` — NEW (internal only)

Same request/response as today's open route, so callers only change URL + header.

**Request:** `{ "item_id": int, "quantity": int }` (existing schema, unchanged)
**Headers:** `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>` (required)
**Responses:** `200/201` as today · `401` `{"detail":"Invalid internal token"}` (missing/wrong header) · `404` item/character not found · `503` when `INTERNAL_SERVICE_TOKEN` is unset in the service (fail-closed) · `422` validation.

Placed under the existing `/inventory/internal/` prefix, which nginx already answers with `403` for external traffic (`nginx.conf:217`, `nginx.prod.conf:233`) — the second layer comes for free, no nginx edit needed for this route.

#### 3.2.3. `POST /inventory/{character_id}/items` — becomes admin-gated (path kept)

`main.py:368` `add_item_to_inventory` gains `current_user = Depends(require_permission("items:update"))`.

**Responses:** `200/201` as today · `401` no/invalid JWT · `403` authenticated but lacking `items:update` · rest unchanged.

Why keep the path for admins: both admin call sites (`api/items.ts:128 issueItem`, `api/adminCharacters.ts:159 addInventoryItem`) already send the JWT through the axios interceptor, so **no frontend API change is needed** — only error surfacing (§3.5.2). Anonymous external calls, the actual hole, now get 401.

*Accepted risk:* a Moderator/Editor who can open the Characters-admin inventory tab but lacks `items:update` loses that button. Admin is unaffected (all permissions automatically). Reviewer must check `role_permissions` for the roles that use those two screens — see §3.9 Q2.

#### 3.2.4. The six character-attributes endpoints — contracts unchanged, header required

`POST /attributes/{id}/apply_modifiers`, `POST /{id}/recover`, `PUT /{id}/active_experience`, `PUT /{id}/passive_experience`, `POST /{id}/consume_stamina`, `POST /{id}/refund_stamina` each gain `Depends(verify_internal_token)`. Paths, request bodies and success responses are untouched.

**New responses:** `401` `{"detail":"Invalid internal token"}` · `503` `{"detail":"Internal service token is not configured"}` (env empty → fail closed).

**Explicitly NOT gated** (FEAT-164 depends on them): `GET /attributes/{id}`, `GET /attributes/{id}/rest-status`, and every other GET. Also untouched: `POST /{id}/upgrade` (JWT), `/attributes/admin/*` (RBAC), `/attributes/internal/*` (nginx-blocked today; gating those is a separate task — see §3.8).

#### 3.2.5. Caller changes (the complete list — Backend task #4)

| Caller | file:line | Change |
|---|---|---|
| battle-service — PvE loot | `battle-service/app/main.py:356` | new internal path + `X-Internal-Token` (helper exists `main.py:65`) |
| battle-pass-service — `_deliver_item` | `battle-pass-service/app/crud.py:534` | new internal path + header; **add** a `_internal_token_headers()` helper |
| dungeon-service — `add_item_to_character` | `dungeon-service/app/http_clients.py:248` | new internal path + header (helper `:26`) |
| locations-service — loot / shop / quest reward | `main.py:2184, 2739, 3040` | new internal path + internal header **instead of** forwarding the player's `Authorization` |
| dungeon-service — `recover_character`, stamina | `http_clients.py:214, 183` | add header |
| locations-service — stamina consume / refund | `main.py:1340, 1600`, `crud.py:7196, 7582` | add header (helpers `crud.py:24-27`, `main.py:3696-3701`) |
| inventory-service — `apply_modifiers_in_attributes_service` | `inventory-service/app/main.py:707` | add header (helper `main.py:28`) — covers all 12 call sites |
| inventory-service — `use_item` recovery | `main.py:749` | add header |
| skills-service — XP deduction | `skills-service/app/main.py:700-709` | add header |
| party-service — `_charge_active_xp`, `_award_passive_xp` | `party-service/app/main.py:52, 66` | add header; **add** a `_internal_token_headers()` helper |

Pattern for the two services without a helper: copy `inventory-service/app/main.py:28-33` — read `os.environ.get("INTERNAL_SERVICE_TOKEN", "")` **at call time** (so tests can set it), not through `config.Settings`. No `config.py` change in party-service / battle-pass-service.

**character-service `main.py:747-760` is out of scope** (§3.8): it calls `/attributes/admin/{id}` — an RBAC route, not one of the six — and is already silently failing today (tracked in ISSUES.md). Nothing in this feature makes it worse.

---

### 3.3. Security considerations

| Question | Answer |
|---|---|
| Authentication | `POST /inventory/internal/characters/{cid}/items` + the six char-attrs endpoints → `X-Internal-Token` (service-to-service only, no player-facing caller exists). `POST /inventory/{cid}/items` → JWT + `items:update`. Damage changes touch no auth. |
| Fail-closed | `verify_internal_token` rejects with `503` when `INTERNAL_SERVICE_TOKEN` is empty and `401` on missing/mismatched header — never "allow if unset". Copied from `character-service/app/auth_http.py:78-95`. **Do not** copy skills-service's Bearer-flavoured variant (`auth_http.py:58-68`). |
| Authorization | Internal routes: token equality only (no per-character ownership — ownership is validated upstream by the calling service, e.g. locations-service checks loot/currency/quest ownership before the call). Admin route: `items:update`; character ownership intentionally not required (it is an admin grant). |
| Input validation | Unchanged schemas; `quantity` bounds and `max_stack_size` splitting stay as today. No new user input. |
| Error messages | Exactly `{"detail": "Invalid internal token"}` / `{"detail": "Internal service token is not configured"}` — no echo of the received header, no hints about which services hold the token. |
| Rate limiting | None added: internal routes are unreachable from outside (nginx 403) and the admin route is behind RBAC. Nginx `limit_req` on `/inventory/` is out of scope. |
| Second layer (nginx, both files) | Add, **before** the generic `location /attributes/`, a regex block returning 403 for the six mutating paths: `location ~ ^/attributes/[0-9]+/(apply_modifiers\|recover\|consume_stamina\|refund_stamina\|active_experience\|passive_experience)$ { return 403; }`. Regex locations win over prefix locations in nginx, and the existing `/attributes/` block is a plain prefix (not `^~`), so ordering is safe. Verified: no frontend code calls any of the six (§2.3), so a hard 403 breaks nothing. `/inventory/internal/` and `/attributes/internal/` 403 blocks already exist — keep. |
| Leftover debt | `INTERNAL_SERVICE_TOKEN`'s public fallback `dev-internal-token-change-me` becomes load-bearing for ~12 more routes. Not code in this feature; DevSecOps escalates the existing ISSUES.md HIGH entry (real secret in prod `.env`) — task #10. |

---

### 3.4. DB changes and one-off backfill

**Schema: none.** No new column, no new table, no RBAC permission, no user-service revision.

**Data: one backfill is required.** Today `character_attributes.damage` includes the effective damage of every equipped weapon. After §3.1.2 it must be base-only, and equip/unequip deltas will no longer cancel that historical amount (unequipping a weapon will subtract nothing, leaving the old weapon damage stuck in `base` forever). So the stored value **is** wrong the moment the new code starts.

**Where:** a **data-only Alembic revision in inventory-service** (`services/inventory-service/app/alembic/versions/`). inventory-service is the only service that can compute the number (it owns `equipment_slots`, sharpening JSON, gems, durability) and it already auto-migrates on container start, so the fix lands in the same deploy, before any traffic.

**Upgrade:**
```sql
-- conceptually, per equipment slot; executed in Python inside the revision
SELECT es.character_id, es.item_id, es.slot_type, es.enhancement_bonuses,
       es.socketed_gems, es.current_durability,
       i.damage_modifier, i.max_durability
FROM equipment_slots es
JOIN items i ON i.id = es.item_id
WHERE es.slot_type IN ('main_weapon', 'additional_weapons') AND es.item_id IS NOT NULL;
-- d = damage_modifier + 1 * enhancement_bonuses['damage_modifier'] + Σ gem.damage_modifier
--     (d = 0 when max_durability > 0 AND current_durability <= 0)
UPDATE character_attributes SET damage = GREATEST(0, damage - :d) WHERE character_id = :cid;
```
Requirements for the revision:
- Same arithmetic as `compute_item_damage`. The revision must **inline** the formula (migrations must not import app code that can change later), and QA task #14 asserts the migration and the helper agree on a fixture.
- `GREATEST(0, ...)` clamp plus a `logger.warning` naming any `character_id` that would have gone negative (data anomaly, not silent).
- Idempotent by construction: Alembic runs a revision once (`alembic_version_inventory`). It must **not** be re-runnable by hand.
- Cross-ownership note: this revision writes a table owned by char-attrs. Acceptable (single shared DB, no schema change, no ordering dependency on char-attrs' own revisions), and called out in the revision docstring.

**Downgrade:** recompute the same `d` per slot and `UPDATE character_attributes SET damage = damage + :d`. Exact as long as equipment did not change in between; the docstring must say so. Operational safety net: run `backup.sh` before the deploy (prod is a live alpha) — the rollback of record is the DB dump, the downgrade is the convenience path.

**In-flight battles:** unaffected — attributes and equipment are re-fetched live per attack; the participant snapshot is display-only (§2.7).

---

### 3.5. Frontend

#### 3.5.1. The three damage values in the profile

Style: FEAT-166 panel language — `PanelShell` → «Показатели» → the «В бою» section of `StatsTab/DerivedStatsSection.tsx`, existing card markup (`rounded-card`, `bg-gold/5 border-gold/20` for highlighted, `bg-white/[0.03] border-white/[0.07]` otherwise, `font-mono` values, `title` tooltip with the full name). No new SCSS; Tailwind only; no `React.FC`; TypeScript.

- `IndicatorsPanel.tsx:33-34`: drop `mainWeaponDamageModifier` and the `?.item?.damage_modifier` lookup. Pass the equipment slots instead: `<DerivedStatsSection attributes={attributes} classId={classId} equipment={equipment} />`.
- `DerivedStatsSection.tsx`: replace `getDisplayDamage()` with one helper producing all three values from `attributes` + `equipment`:
  ```ts
  const weaponDamage = (slotType: 'main_weapon' | 'additional_weapons') =>
    Number(equipment.find((s) => s.slot_type === slotType)?.effective_damage ?? 0);
  const base = mainAttrValue + Number(attributes.damage ?? 0);
  // damage_main = base + weaponDamage('main_weapon')
  // damage_additional = base + weaponDamage('additional_weapons')
  // damage_unarmed = base
  ```
  Put the helper in a small exported function (e.g. `src/components/ProfilePage/StatsTab/damage.ts`) so future consumers (battle UI, admin) reuse it instead of re-summing.
- Cards, in this order, inside the existing `grid grid-cols-2 gap-2`:

| Label (card) | `title` tooltip | Style |
|---|---|---|
| «Осн. урон» | `Основной урон — база + оружие в основной руке` | highlighted, `col-span-2` |
| «Доп. урон» | `Дополнительный урон — база + оружие в дополнительной руке` | normal |
| «Без оружия» | `Урон без оружия — только характеристики, перки и снаряжение без оружия` | normal |

  Then `initiative`, `dodge`, `critical_hit_chance`, `critical_damage` as today. All three damage cards are always visible (an empty hand simply equals the unarmed value) — the player must be able to compare them.
- Responsiveness (360px+): the grid is already `grid-cols-2`; short labels + `truncate` + `shrink-0` values keep it inside the viewport. The full-width main-damage card must not force a horizontal scroll.
- Types: `EquipmentSlotData` in `redux/slices/profileSlice.ts:77-88` gains `effective_damage?: number` (optional — synthetic empty-slot placeholders omit it). `components/Admin/CharactersPage/types.ts:190` `EquipmentSlot` gains the same optional field.

#### 3.5.2. Admin item grant — error surfacing only

No API-path change (§3.2.3). Both flows must show a Russian message on `401/403/5xx` instead of failing silently:
- `components/ItemsAdminPage/IssueItemModal.tsx:60` — on error show e.g. «Не удалось выдать предмет: недостаточно прав (требуется items:update)» for 403, «Ошибка выдачи предмета: <detail>» otherwise.
- `redux/slices/adminCharactersSlice.ts:256` (`addInventoryItem`) — `rejectWithValue` with a Russian message, rendered by the inventory tab.
If those components' styles are touched, CLAUDE.md §10.8/§10.12 apply (Tailwind + responsive migration for the touched component).

---

### 3.6. Data flow

**Equip a sword (damage split at the source)**
```
Player → Frontend POST /inventory/{cid}/equip
  inventory-service: slot.item_id = sword
    build_modifiers_dict(sword, slot_type="main_weapon")   → {"strength": +10}   (damage dropped)
    POST /attributes/{cid}/apply_modifiers  + X-Internal-Token
      char-attrs: damage unchanged, strength +10 → resists/dodge recomputed
  Frontend GET /attributes/{cid} → base
  Frontend GET /inventory/{cid}/equipment → effective_damage = 10 (sword, sharpened/gemmed/broken aware)
  Profile: Осн. урон = 35 + 0 + 10 = 45 | Доп. урон = 35 | Без оружия = 35
```

**Attack in battle (one formula, weapon once)**
```
Frontend/autobattle → battle-service POST /battle/{id}/attack
  battle-service GET /attributes/{attacker}            (live, FEAT-164 regen settles here)
  battle-service GET /inventory/{attacker}/equipment   (live) → effective_damage per slot
                 GET /inventory/items/{id}             (live) → primary_damage_type
  for each damage_entry:
      weapon = None if weapon_slot == "no_weapon" else weapons[weapon_slot]
      base   = main_attr + attrs.damage + (weapon.effective_damage or 0)
  → 45 for the main-hand entry, 35 for a no_weapon entry
```

**Internal grant of an item**
```
battle-service / battle-pass / dungeon / locations
  → POST /inventory/internal/characters/{cid}/items  (X-Internal-Token)
     nginx: /inventory/internal/ → 403 for anything coming from outside
     inventory-service: Depends(verify_internal_token) → 401 / 503 when wrong or unconfigured

Admin UI → POST /inventory/{cid}/items  (Bearer JWT)
     inventory-service: require_permission("items:update") → 401 / 403
```

---

### 3.7. Cross-service contract check (cross-service-validator)

| Caller | Callee | Endpoint | Status | Note |
|---|---|---|---|---|
| battle-service | inventory | `GET /inventory/{cid}/equipment` | OK | additive `effective_damage`, consumed in `fetch_weapons` |
| battle-service | inventory | `POST /inventory/internal/characters/{cid}/items` | CHANGED | path + header; old path would 403/401 |
| battle-pass, dungeon, locations ×3 | inventory | same | CHANGED | path + header; **battle-pass needs the env var** |
| Admin UI ×2 | inventory | `POST /inventory/{cid}/items` | OK | path kept, JWT already sent; now 403 without `items:update` |
| inventory, dungeon, locations, skills, party | char-attrs | the six mutating endpoints | CHANGED | header only; **party needs the env var** |
| battle, skills, character, frontend | char-attrs | `GET /attributes/{id}`, `/rest-status` | OK | untouched by design (FEAT-164) |
| party | char-attrs | `POST /attributes/internal/settle-regen` | OK | different route, left as-is (§3.8) |
| character-service | char-attrs | `PUT /attributes/admin/{id}` | PRE-BROKEN | already failing (ISSUES.md), out of scope |
| inventory | char-attrs | `POST /attributes/internal/{id}/satiety` | OK | outside the six |
| autobattle | battle | attack endpoints | OK | no damage math of its own → parity automatic |
| frontend | inventory/char-attrs | `equipment`, `attributes` | CHANGED | new optional TS field; three-value display |

Types: `effective_damage` is `float` (Pydantic v1 `float = 0.0`) ↔ `effective_damage?: number`. No Pydantic v2 syntax anywhere.

---

### 3.8. Deliberately out of scope (follow-ups, keep in ISSUES.md)

1. `character-service/app/main.py:747-760` — level→XP sync via the RBAC route `/attributes/admin/{id}` without auth; silently failing today. Needs a service-account decision; separate feature.
2. Gating `/attributes/internal/*` and `/inventory/internal/*` with `verify_internal_token` in the service (today nginx-only). Would require party-service's settle-regen call to send the header — safe once task #9 lands, but it is a bigger sweep; file as a follow-up.
3. `compute_derived_stats` (char-attrs `crud.py:60-65`) reseeds `damage` from the class main attribute and wipes accumulated item/perk bonuses on `/recalculate` and `/admin/recalculate_all`; the engine then adds the main attribute again. Pre-existing; not touched here. Backend Dev must **log it in `docs/ISSUES.md`** (task #12) — after this feature a recalculate no longer restores weapon damage either (it never should, but the wipe of perk/armour bonuses is real).
4. Real `INTERNAL_SERVICE_TOKEN` secret in prod `.env` + `.env.example` stub (existing HIGH entry — escalate, DevSecOps task #10).
5. Rate limiting on `/inventory/`.

---

### 3.9. Questions for PM → user (non-blocking; defaults chosen)

1. **Sharpening/gems on the weapon itself.** Decided as: they belong to that weapon (so «Урон без оружия» and the off-hand value do not grow when you sharpen the main weapon). §1 wording listed "sharpening, gems" under base — this is the narrow reading. Confirm.
2. **Moderator access to the admin grant.** Reusing `items:update` may remove the "add item" button from the Characters-admin inventory tab for a Moderator who has `characters:update` but not `items:update`. Admin is unaffected. OK, or should that screen accept `characters:update` as well?
3. **Broken weapon** (durability 0) now contributes 0 damage but still sets the damage type — so «Основной урон» equals «Урон без оружия» while the weapon is broken. Confirm that reads correctly in the profile (no separate "оружие сломано" marker is planned in this feature).


### 3.10. Addendum — tasks #17/#18: two more pre-existing holes of the same class

Filed by the Reviewer at review #1 as pre-existing findings, approved by the user for this same
push (prod is a live alpha, so the gateway must not go out with them open). They are the same class
as §3.3 and are closed the same way: **the guard lives in the service** (`verify_internal_token`,
already present in both services after tasks #2/#3), with nginx as a second layer.

#### 3.10.1. The two holes

| # | Route | Symptom before | Damage |
|---|---|---|---|
| 17 | `POST /attributes/cumulative_stats/increment` | anonymous POST through the gateway answered **200 «Stats updated»** | pumps `pve_kills` / `pvp_wins` / `total_damage_dealt` / win streaks for any character **and returns `newly_unlocked_perks`** — free perk unlocks from outside |
| 17 | `POST /attributes/` (create attributes row) | anonymous POST reached the handler (**422** on the body schema, not 401) | attribute rows for arbitrary `character_id` |
| 18 | `POST /inventory/` (create inventory + default equipment slots) | same — **422**, not 401 | inventory rows and equipment slots for arbitrary `character_id` |

`/attributes/cumulative_stats/increment` sits **outside** the `/attributes/internal/` prefix, which
is why the existing nginx `return 403` never covered it, and its own docstring already called it
internal. The two creation routes are `POST /` on each service's router, so the generic
`/attributes/` and `/inventory/` proxy blocks passed them straight through.

#### 3.10.2. Caller sweep (the whole repo, before any change)

| Route | Callers | Sends today | Decision |
|---|---|---|---|
| `POST /attributes/cumulative_stats/increment` | battle-service `main.py:486` (`_track_cumulative_stats`, battle end); locations-service `main.py:42` (posts, travel, NPC shop, quests — 7 call sites through **one** helper); inventory-service `main.py:759` (crafting / gathering counters); skills-service `main.py:524` (`skills_used` on skill upgrade) | nothing | `verify_internal_token` |
| `POST /attributes/` | character-service only: `crud.send_attributes_request` (`crud.py:1001` — character creation **hard-fail**, and admin NPC creation), `crud._sync_send_attributes_request` (`crud.py:1578` — mob spawn) | nothing | `verify_internal_token` |
| `POST /inventory/` | character-service only: `crud.send_inventory_request` (`crud.py:950` — starter kit at character creation) | nothing | `verify_internal_token` |

**No frontend caller for any of the three** (swept `.ts`/`.tsx`: `client.ts` and `professions.ts`
use `baseURL: "/inventory"` but never `post("/")`; `perks.ts` uses `baseURL: "/attributes"` and
posts only to `/admin/perks*`). **No seed or admin script** calls them. So all three are pure
service-to-service and no player or admin route needs JWT/RBAC here — unlike task #2, this needs no
route split.

#### 3.10.3. Decisions

1. **`verify_internal_token` on all three**, not JWT and not RBAC: there is no player-facing or
   admin-facing caller, so any user credential on these routes would be strictly weaker than the
   service token. Same fail-closed helper, same Russian wording («Недействительный internal token»
   / «Internal service token не настроен»).
2. **Character creation is the blast radius.** `POST /attributes/` is a *hard-fail* step of the
   approval flow (`character-service/app/main.py:505` rolls the character back on a falsy answer),
   so the header had to land in the same change. `POST /inventory/` (starter kit) and the mob-spawn
   attributes call are log-and-continue, i.e. failures there would be **silent** — the
   `docs/ISSUES.md` "тихие отказы" pattern. Hence the caller-side header tests in §3.10.5.
3. **character-service gets its own `_internal_token_headers()`** in `crud.py`, lazily importing
   `auth_http` and reading `INTERNAL_SERVICE_TOKEN` at call time — copied from
   `character-service/app/locations_client.py:169-173`, so tests can pin the module attribute.
   `character-service` already receives the env var in both compose files, so no compose change is
   needed for #17/#18 (unlike tasks #9/#10).
4. **No new config, no schema change, no migration, no RBAC permission.**

#### 3.10.4. nginx second layer

Three **exact-match** (`location = …`) blocks in both `nginx.conf` and `nginx.prod.conf`, each with
`limit_except GET HEAD { deny all; }`, placed before the generic prefix blocks:

```
location = /attributes/cumulative_stats/increment
location = /attributes/
location = /inventory/
```

Exact-match locations win over every prefix and regex location, so declaration order is not load
bearing, and — critically — they match **only** those three URIs. The `/attributes/` and
`/inventory/` prefixes serve dozens of live routes (`/inventory/items`, `/inventory/{id}/equip`,
`/inventory/trade/*`, `/inventory/auction/*`, `/attributes/{id}`, `/attributes/{id}/upgrade`,
`/attributes/admin/*`), so a *prefix* or *regex* block here would have taken the game down; an
exact match cannot. `limit_except GET HEAD` keeps the FEAT-167 shape: reads are never blocked
(`GET /attributes/{id}/cumulative_stats` is a different URI and is used by the profile).

FastAPI's `redirect_slashes` means `POST /attributes` (no trailing slash) would 307 to
`/attributes/`, but `/attributes` matches neither `location /attributes/` nor the exact block, so it
never reaches the service through the gateway at all — and the service-side gate covers it anyway.

#### 3.10.5. Tests

Same shape as tasks #12/#13:

- **Auth matrix per route** — no header / wrong header / empty header value / player Bearer token →
  401; empty `INTERNAL_SERVICE_TOKEN` env → 503 and never 200; correct header → the call really
  works and really writes. Every rejection is asserted **against the DB** (no row created, no
  counter moved), so a guard that rejects *after* writing still fails. Plus a route-table sweep per
  service so the gate cannot be quietly removed.
- **Caller-side header guards** on the **real** client functions (not re-implementations), because
  three of the seven call sites swallow their errors: battle-service `_track_cumulative_stats`,
  inventory-service `_track_cumulative_stats`, locations-service `_track_cumulative_stats`,
  skills-service (source sweep — the call is inline in the handler), and all three character-service
  creation helpers.
- `POST /attributes/` also gets an explicit **"auth runs before schema validation"** case, because
  the reported symptom of the hole was a 422: a malformed anonymous body must now be a 401.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Everything ships in one deploy.** Parallel waves:
- **Wave A (parallel):** #1, #3, #7, #9, #10 — no dependencies between them.
- **Wave B:** #2 (after #1, same service/files), #4 (after #2+#3), #5 (after #1), #6 (after #1), #8 (after #1).
- **Wave C:** QA #11–#14. **Wave D:** #15 docs, #16 review.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **Damage split in inventory-service.** Add `crud.compute_item_damage(...)` (template `damage_modifier` + sharpening ×1 + gems, `0.0` if broken) and make `build_modifiers_dict` take its `damage` value from it. Add `slot_type: str \| None = None` to `build_modifiers_dict` and drop the `damage` key for `main_weapon`/`additional_weapons`. Pass `slot_type` at **all 11 apply sites** of §3.1.2 (incl. the two manual gem dicts and the sharpening delta). Add `effective_damage: float = 0.0` to `schemas.EquipmentSlotBase` and enrich `GET /inventory/{cid}/equipment` with it (§3.2.1). | Backend Developer | DONE | `inventory-service/app/crud.py`, `app/main.py`, `app/schemas.py` | — | `py_compile` OK; equipping a weapon no longer changes `character_attributes.damage`; `effective_damage` correct for plain / sharpened / gemmed / broken / empty slots; armour & jewellery `damage_modifier` still lands in `damage`; existing suites re-run |
| 2 | **inventory-service auth.** Add fail-closed `verify_internal_token` to `app/auth_http.py` (copy of `character-service/app/auth_http.py:78-95`). Add `POST /inventory/internal/characters/{cid}/items` with `Depends(verify_internal_token)` reusing the existing handler logic; put `require_permission("items:update")` on the existing `POST /inventory/{cid}/items` (`main.py:368`). Russian `detail` messages, no header echo (§3.3). | Backend Developer | DONE | `inventory-service/app/auth_http.py`, `app/main.py` | #1 | `py_compile` OK; internal route: no header → 503/401, wrong → 401, right → 201; admin route: anon → 401, authed w/o permission → 403, admin → 201; no code path left that grants items unauthenticated |
| 3 | **char-attrs auth.** Add fail-closed `verify_internal_token` to `character-attributes-service/app/auth_http.py`, export it, and add `Depends(verify_internal_token)` to the six mutating endpoints (`main.py:723, 886, 925, 959, 992, 1044`). **Do not touch any GET** (FEAT-164 regen) nor `/upgrade`, `/admin/*`, `/internal/*`. | Backend Developer | DONE | `character-attributes-service/app/auth_http.py`, `app/main.py` | — | `py_compile` OK; the six return 401 without header / 503 with empty env / 200 with header; `GET /attributes/{id}` and `/rest-status` unchanged |
| 4 | **All callers send the internal header** per the table in §3.2.5: repoint the 5 item-grant callers to the new internal path; add `X-Internal-Token` to the char-attrs calls in inventory, locations (6), dungeon (2), skills (1), party (2); add a call-time `_internal_token_headers()` helper to party-service and battle-pass-service (no `config.py` change). locations-service stops forwarding the player's `Authorization` on the 3 grant calls. character-service is **not** touched. | Backend Developer | DONE | `battle-service/app/main.py`, `battle-pass-service/app/crud.py`, `dungeon-service/app/http_clients.py`, `locations-service/app/main.py`+`crud.py`, `skills-service/app/main.py`, `party-service/app/main.py`, `inventory-service/app/main.py` | #2, #3 | `py_compile` OK on every file; grep shows no remaining call to the old grant path or to the six endpoints without a header; each helper reads the env at call time |
| 5 | **battle-service: weapon counted once.** `fetch_weapons` attaches `effective_damage` from the equipment slot; `compute_damage_with_rolls` uses it instead of `weapon["damage_modifier"]`; `weapon` still resolves `damage_type=="all"`. Delete the dead `compute_single_damage_entry`. Keep `weapon_slot` selection (`main.py:2799-2805`) as-is. | Backend Developer | DONE | `battle-service/app/battle_engine.py` (`app/main.py` не понадобился — выбор слота уже корректен) | #1 | `py_compile` OK; the Арлекино case yields 45 (main hand) / 35 (no_weapon); off-hand uses the off-hand weapon only; no `damage_modifier` read remains in battle-service; broken weapon adds 0 but keeps its damage type |
| 6 | **Backfill migration** (§3.4): data-only Alembic revision in inventory-service subtracting each equipped weapon's effective damage from `character_attributes.damage`, with `GREATEST(0, …)` clamp + warning log for anomalies, inlined arithmetic, and a downgrade that adds it back. Docstring states the cross-service write and the rollback caveat. | Backend Developer | DONE | `inventory-service/app/alembic/versions/<new>.py` | #1 | `alembic upgrade head` then `downgrade -1` round-trips on a seeded DB; after upgrade, unequipping a weapon leaves `damage` at the pre-equip value; no negative `damage` |
| 7 | **Frontend: three damage values** (§3.5.1) in the FEAT-166 panel style — `effective_damage?: number` on both `EquipmentSlot` types, shared `damage.ts` helper, three cards («Осн. урон» highlighted `col-span-2`, «Доп. урон», «Без оружия») with full Russian `title` tooltips; remove the `mainWeaponDamageModifier` prop and the `item.damage_modifier` lookup. Tailwind only, no `React.FC`, 360px-safe. | Frontend Developer | DONE | `ProfilePage/StatsTab/DerivedStatsSection.tsx`, `ProfilePage/StatsTab/damage.ts` (new), `ProfilePage/CharacterTab/IndicatorsPanel.tsx`, `redux/slices/profileSlice.ts`, `components/Admin/CharactersPage/types.ts` | #1 | `npx tsc --noEmit` and `npm run build` pass; three values shown; main-hand number equals what battle logs as `base`; no horizontal scroll at 360px; no SCSS added |
| 8 | **Frontend: admin grant error surfacing** (§3.5.2) — 401/403/5xx from `POST /inventory/{cid}/items` shown to the admin in Russian in both flows; no silent failures. API paths unchanged. | Frontend Developer | DONE | `components/ItemsAdminPage/IssueItemModal.tsx`, `redux/slices/adminCharactersSlice.ts` | #1 | `tsc --noEmit` + `npm run build` pass; a 403 renders a Russian message in the modal and in the characters-admin inventory tab |
| 9 | **Compose: `INTERNAL_SERVICE_TOKEN` for party-service and battle-pass-service** in **both** `docker-compose.yml` and `docker-compose.prod.yml`; then verify the merged config for party, battle-pass, char-attrs, inventory and locations with `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`. | DevSecOps | DONE | `docker-compose.yml`, `docker-compose.prod.yml` | — | Both services show the var in dev **and** merged prod config; output pasted into the feature log |
| 10 | **Nginx second layer** (§3.3): regex `403` block for the six `/attributes/{id}/…` mutating paths, placed before the generic `location /attributes/`, in **both** `nginx.conf` and `nginx.prod.conf`; confirm the existing `/inventory/internal/` and `/attributes/internal/` 403 blocks still match the new internal grant path. Escalate the `INTERNAL_SERVICE_TOKEN` fallback entry in `docs/ISSUES.md` (real secret in prod `.env` + `.env.example` stub). | DevSecOps | DONE (ISSUES.md escalation left to task #15 — see log) | `docker/api-gateway/nginx.conf`, `nginx.prod.conf`, `docs/ISSUES.md` | — | `nginx -t` passes; external `POST /attributes/1/recover` → 403, `POST /inventory/internal/characters/1/items` → 403; `GET /attributes/1` and `/rest-status` still 200 |
| 11 | **QA: damage math.** Re-baseline `test_class_damage_luck.py` and rewrite `test_weapon_slot.py` around the three values; new cases: main-hand = base + main weapon, off-hand = base + off-hand weapon (**different numbers**), `no_weapon` = base only, weapon damage counted exactly once (attribute never contains it), broken weapon contributes 0 but keeps its damage type, sharpened/gemmed weapon uses the effective value, NPC-with-weapon parity, profile-formula parity (`base = main_attr + attrs.damage`). Check `test_dodge_and_freshness.py:36`. Remove tests of the deleted `compute_single_damage_entry`. | QA Test | DONE | `battle-service/app/tests/test_weapon_damage_once.py` (new, 17 тестов), `inventory-service/app/tests/test_weapon_damage.py` (new, 29 тестов — заточка/камни/сломанное + `effective_damage`); `test_class_damage_luck.py` / `test_weapon_slot.py` / `test_dodge_and_freshness.py` уже перебазированы Backend Dev'ом, проверены и не менялись | #5 | `pytest` green in battle-service; a test fails if the duplicate term is reintroduced or if `weapon_slot` stops differentiating the hands |
| 12 | **QA: auth for every newly gated route.** inventory: the **missing POST case** in `test_endpoint_auth.py` (no header → 503/401, wrong → 401, authed w/o `items:update` → 403, admin → 201) plus the internal route; char-attrs: all six × (no header / wrong header / good header) and **fail-closed with an empty `INTERNAL_SERVICE_TOKEN` env**; fix the ~13 unauthenticated posts in `test_add_item_to_inventory.py` and the fixtures in the indirect suites (`test_admin_auth`, `test_gathering`, `test_item_*`, `test_resource_subcategory_rules`, `test_trade*`). | QA Test | DONE | `inventory-service/app/tests/test_endpoint_auth.py` (+13 кейсов: internal-роут и админский), `character-attributes-service/app/tests/test_internal_auth.py` (new, 57 тестов); `test_add_item_to_inventory.py` и косвенные сюиты уже переведены Backend Dev'ом — перепроверены полным прогоном | #2, #3 | `pytest` green in both services; every newly gated route has a no-header, wrong-header, good-header case; an empty token env yields 503, never 200 |
| 13 | **QA: caller-side headers.** Assert `X-Internal-Token` on the **real** client functions (not re-implementations) for party-service (`_charge_active_xp`, `_award_passive_xp`) and battle-pass-service (`_deliver_item`) — these two had zero coverage — and patch the caller suites: locations (`test_gathering_ingredient`, `test_post_xp`, `test_bp_tracking`), dungeon (`test_gameplay`), skills (`test_character_skill_upgrade`, `test_player_tree_endpoints`), battle-service loot drop. Follow the FEAT-162 precedent (pin the module constant, add `headers=`, assertions unchanged). | QA Test | DONE | `party-service/app/tests/test_internal_headers.py` (new, 8), `battle-pass-service/app/tests/test_internal_headers.py` (new, 5), `dungeon-service/app/tests/test_internal_headers.py` (new, 6), `skills-service/app/tests/test_internal_headers.py` (new, 5), `locations-service/app/tests/test_internal_headers.py` (new, 9), `inventory-service/app/tests/test_outgoing_internal_headers.py` (new, 8), `battle-service/app/tests/test_pve_rewards.py` (+2 на лут) | #4 | `pytest` green in all touched services; a test fails if any caller drops the header or hits the old grant path |
| 14 | **QA: backfill migration.** Seed a character with base damage + a sharpened/gemmed main weapon + an off-hand + a broken weapon; run `alembic upgrade head`; assert `damage` equals the base-only value and that the migration's arithmetic matches `crud.compute_item_damage`; assert `downgrade` restores the original; assert no negative values. | QA Test | DONE | `inventory-service/app/tests/test_weapon_damage_backfill.py` (new, 26 тестов) | #6 | `pytest` green; migration and helper agree on every fixture |
| 15 | **Docs:** update `docs/services/inventory-service.md`, `character-attributes-service.md`, `battle-service.md` (three damage values, `effective_damage`, new internal route, gated endpoints) and `docs/ISSUES.md` — mark the double-count and the two open-endpoint entries as fixed/removed, add the `compute_derived_stats` recalculate-wipe finding (§3.8.3). | Backend Developer | DONE (PM) | `docs/services/*.md`, `docs/ISSUES.md` | #5, #6 | ISSUES.md has no stale entry for anything fixed here; new finding recorded with service/file/priority |
| 16 | **Review** — full checklist + **live verification**: unauthenticated `POST /inventory/1/items` and `POST /attributes/1/recover` rejected; equip/unequip, gathering, crafting, rest, party XP tick, battle-pass item reward, dungeon run and a PvP attack all still work; profile's «Осн. урон» equals the battle log's `base`; console clean. | Reviewer | TODO | all | #1–#15 | `py_compile`, `pytest` (all touched services), `tsc --noEmit`, `npm run build` results recorded + live checks passed; §3.9 questions answered or logged |
| 17 | **Close `POST /attributes/cumulative_stats/increment` and `POST /attributes/`** (§3.10). Add `Depends(verify_internal_token)` to both (helper already added by task #3). Update all four increment callers to send `X-Internal-Token` (battle, locations, inventory, skills — each has a `_internal_token_headers()` helper already) and both character-service creation callers (`crud.send_attributes_request`, `crud._sync_send_attributes_request`), adding a lazy `_internal_token_headers()` to `character-service/app/crud.py` in the `locations_client` style. **Do not touch any GET**, `/attributes/{id}/cumulative_stats` included. | Backend Developer | DONE | `character-attributes-service/app/main.py`, `battle-service/app/main.py`, `locations-service/app/main.py`, `inventory-service/app/main.py`, `skills-service/app/main.py`, `character-service/app/crud.py` | #3 | `py_compile` OK; both routes: no/wrong/empty header → 401, empty env → 503, correct header → 200; `GET /attributes/{id}` and `/attributes/{id}/cumulative_stats` unchanged; character creation, mob spawn and battle-end stat tracking still work |
| 18 | **Close `POST /inventory/`** (§3.10) with `Depends(verify_internal_token)` (helper already added by task #2); its only caller, `character-service/app/crud.py:send_inventory_request` (starter kit), sends the header. **Do not touch any other `/inventory/` route.** | Backend Developer | DONE | `inventory-service/app/main.py`, `character-service/app/crud.py` | #2, #17 | `py_compile` OK; no/wrong/empty header → 401, empty env → 503, correct header → 200 with the equipment slots created; starter kit still granted at character creation |
| 19 | **nginx second layer for #17/#18** (§3.10.4): three **exact-match** `location = …` blocks (`/attributes/cumulative_stats/increment`, `/attributes/`, `/inventory/`) with `limit_except GET HEAD { deny all; }` in **both** `nginx.conf` and `nginx.prod.conf`. Exact match only — a prefix or regex block on `/attributes/` or `/inventory/` would break the game. | Backend Developer (DevSecOps scope, done in the same change) | DONE | `docker/api-gateway/nginx.conf`, `nginx.prod.conf` | #17, #18 | `nginx -t` passes on both; through a throwaway gateway on the real network the three POSTs → 403 while `/attributes/{id}`, `/attributes/{id}/rest-status`, `/attributes/{id}/cumulative_stats`, `/attributes/{id}/passive_experience`, `/inventory/items`, `/inventory/{id}/equipment` (GET) and `/inventory/{id}/items`, `/inventory/trade/propose`, `/attributes/{id}/upgrade`, `/attributes/{id}/recalculate` (POST) are untouched |
| 20 | **QA for #17/#18** (§3.10.5): auth matrix per route (no header / wrong / empty value / player JWT → 401; empty `INTERNAL_SERVICE_TOKEN` → 503, never 200; correct header → really works) with every rejection asserted against the DB, route-table sweeps, «auth before schema validation» for `POST /attributes/`, and caller-side header guards on the **real** client functions of all seven call sites. Also fix the `_capture_post` stubs in `battle-service/app/tests/test_cumulative_stats.py`, which do not accept the new `headers=` kwarg (review #2 finding #1). | QA Test / Backend Developer | DONE | `character-attributes-service/app/tests/test_internal_auth.py`, `…/test_cumulative_stats.py`, `…/test_title_evaluation_trigger.py`, `inventory-service/app/tests/test_endpoint_auth.py`, `…/test_outgoing_internal_headers.py`, `battle-service/app/tests/test_cumulative_stats.py`, `locations-service/app/tests/test_internal_headers.py`, `skills-service/app/tests/test_internal_headers.py`, `character-service/app/tests/test_internal_headers.py` (new) | #17, #18 | full `pytest` green in all six touched services; a test fails if any gate is removed or any caller drops the header |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-18

**Result:** FAIL — documentation only. **No code defect was found.** Every automated check and
every live check passed; the two blocking items are both stale entries in `docs/ISSUES.md`,
i.e. the not-yet-finished task #15. Nothing in the implementation needs to change.

#### Automated Check Results

| Check | Result | Detail |
|---|---|---|
| `py_compile` (35 changed/new `.py`) | **PASS** | `python:3.10` container, whole repo mounted, 0 failures |
| `pytest` inventory-service | **PASS** | 1017 passed |
| `pytest` battle-service | **PASS** | 535 passed |
| `pytest` character-attributes-service | **PASS** | 408 passed, 2 skipped, 1 xpassed |
| `pytest` locations-service | **PASS** | 1204 passed |
| `pytest` skills-service | **PASS** | 218 passed |
| `pytest` dungeon-service | **PASS** | 132 passed |
| `pytest` party-service | **PASS** | 47 passed |
| `pytest` battle-pass-service | **PASS** | 112 passed |
| `pytest` autobattle-service | **PASS** | 78 passed (parity guard) |
| `npx tsc --noEmit` | **PASS** | exit 0 |
| `npm run build` | **PASS** | exit 0, built in 2m08s |
| `docker compose config` (dev) | **PASS** | exit 0 |
| `docker compose -f … -f docker-compose.prod.yml config` | **PASS** | `INTERNAL_SERVICE_TOKEN` present for 10 services in the **merged prod** config, including the two that were missing: **party-service** and **battle-pass-service** (§2.5 blocker closed) |
| `nginx -t` | **PASS** | implicitly — `docker compose up --build -d api-gateway` started cleanly and serves |

All pytest runs used a throwaway `python:3.10` container with the whole repo mounted, the CI
`pytest-args` per service and `CI=true`. Totals are at or above the numbers QA reported, so no
regression slipped in after their run.

#### Damage model — code verification

- **All 11 modifier-application sites pass `slot_type`** (§3.1.2 checklist, verified by grep):
  `main.py:525, 896, 933, 1038, 3387, 3544` (slot-object sites) and `crud.py:365, 377, 412`
  (NPC equip ×2 / unequip). The three hand-built dicts drop the key explicitly instead:
  sharpening `main.py:2607-2610`, gem insert `main.py:2892-2895`, gem extract `main.py:2988-2991`.
  The only `build_modifiers_dict` call left without `slot_type` is `main.py:3219` (the food
  payload) — correct by design: food has no slot and its damage buff belongs in `base`.
- **No path can leak weapon damage back into `character_attributes.damage`.**
  `build_modifiers_dict` now *derives* the `damage` key from `compute_item_damage` in the `else`
  branch and `pop`s it for `WEAPON_SLOTS`, so a weapon slot cannot produce a `damage` key at all,
  no matter what the item template, sharpening or gems hold. `apply_modifiers` in char-attrs is
  the single writer and it is reached only through `apply_modifiers_in_attributes_service`.
- **Anti-drift holds.** `compute_item_damage` is the only arithmetic: `build_modifiers_dict`,
  `get_equipment_slots_with_damage` (→ `effective_damage`) and therefore the battle engine and the
  profile all read the same number.
- **Sharpening increment matches.** `damage_modifier` is in `MAIN_STAT_FIELDS` (`crud.py:138`) →
  `+1` per point, which is exactly `compute_item_damage`'s `× 1`. No divergence.
- **Nothing else reads the raw `damage_modifier` for damage.** battle-service: the string survives
  only inside one comment (`battle_engine.py:57`); QA's guard strips comments before asserting, so
  the test is honest. No other backend service reads the field. The remaining frontend hits are
  per-item stat lists (`ItemDetailModal`, `itemFormRules`, `NpcEquipmentEditor`), not character
  totals — `IndicatorsPanel`'s lookup and the `mainWeaponDamageModifier` prop are gone.
- Dead `compute_single_damage_entry` deleted; QA pins both its absence and that exactly one
  `attacker_attr.get("damage"` formula remains.

#### Migration 023 — safety on prod-like data

The local `fogdatabase` **is a prod dump**, so this is a prod-shaped check: 697 characters,
750 `character_attributes` rows, **12** filled weapon slots. `alembic_version_inventory` =
`023_weapon_damage_backfill`, chain `022_profession_rework → 023` with no branch.

- **Arithmetic matches `compute_item_damage` exactly.** Both are pure integer sums here:
  `items.damage_modifier` and `character_attributes.damage` are `Integer` columns and sharpening
  counts are integers, so the migration's `int(...)` and the helper's `float(...)` cannot diverge
  on any real row. Broken-weapon rule is identical
  (`max_durability > 0 and current_durability is not None and <= 0`).
- Spot-checks against the analyst's report line up: character 12 (staff 500 + 1 sharpening point)
  `520 → 15`; character 278 (dagger 18) `118 → 100`.
- `damage < 0` rows after upgrade: **0**. Clamp + `logger.warning` present for anomalies; skipped
  characters without an attributes row are warned, not silently dropped; malformed sharpening JSON
  is caught. Downgrade is the symmetric `+d`. Cross-service write and the rollback caveat are in
  the docstring.

#### nginx layer — live, through the rebuilt gateway

`docker compose up --build -d api-gateway` was run first (the running container had the old baked
config), and party-service / battle-pass-service were recreated to pick up the new env var.

| Request (anonymous, via gateway) | Result |
|---|---|
| `POST /attributes/706/recover`, `/apply_modifiers`, `/consume_stamina`, `/refund_stamina` | **403** |
| `PUT /attributes/706/active_experience`, `/passive_experience` | **403** |
| `GET /attributes/706` | **200** |
| `GET /attributes/706/rest-status` | **200** |
| `GET /attributes/706/passive_experience` | **200** (the `limit_except GET HEAD` trick works — a naive `return 403` would have broken this reader) |
| `POST /attributes/internal/settle-regen` | **403** (unchanged) |
| `PUT /attributes/admin/706` | **401** (unchanged, reaches RBAC) |
| `POST /attributes/706/upgrade` | **401** (unchanged, reaches JWT) |
| `POST /inventory/internal/characters/706/items` | **403** (the new internal route inherits the existing block — no nginx edit needed) |
| `POST /inventory/706/items` | **401** (the hole is closed) |
| `POST /attributes/abc/recover` | 401 — regex does not match, request reaches the service and the token dep refuses it (defence in depth proven) |
| `POST /attributes/706/recover/extra` | 404 — regex does not over-match |

The regex block wins over `location /attributes/`: no `^~` prefix exists and no earlier regex
location matches `/attributes/`. dev and prod blocks are byte-identical.

Service-layer (bypassing nginx, direct to the container): all six answer **401
`{"detail":"Недействительный internal token"}`** with no header and with a wrong header, and
**200** with the right one. Same for the new inventory internal route (401 → 404 for an unknown
item id with a valid token). No header value is echoed anywhere.

#### Live Verification Results

Character **706 «Арлекино»** (class 1, strength 20, `damage` 5 → unarmed 25) with **item 4
«Экскалибур» (+10 strength, +10 damage)** — the exact case from the bug report.

| # | Check | Result |
|---|---|---|
| a | Profile shows «Осн. урон» / «Доп. урон» / «Без оружия» at 1440 and 360 | **PASS** — 45 / 35 / 35; «Осн. урон» highlighted and `col-span-2`; horizontal overflow **0 px** at both widths; «Осн. урон» − «Без оружия» = 10 = the slot's `effective_damage` |
| b | Real battle attack | **PASS** — `POST /battles/{id}/action` logged `"base": 45.0`, `"final": 45.0`. Identical to the profile, **not** the old 55 |
| b2 | Same after sharpening the weapon's damage (+1) | **PASS** — `effective_damage` 10 → 11, `character_attributes.damage` stayed **5** (no leak), battle logged `"base": 46.0`. Confirms the user's decision that sharpening belongs to the weapon |
| c | Broken weapon (durability 0) | **PASS** — `effective_damage` → 0.0, battle logged `"base": 35.0`, profile showed 35 / 35 / 35 with the «⚠ Оружие сломано» badge on «Осн. урон», legible and inside the viewport at 360 px |
| d | Equip / unequip drift | **PASS** — 3 full cycles: `damage` stayed **5** every time, `strength` 20 ⇄ 30. Equipping no longer moves `damage` at all |
| e | Admin item grant | **PASS** — admin **200**; moderator **200** (the `moderator` role *does* hold `items:update` in `role_permissions`, so the button keeps working for them); `editor` (only `items:read`) **403 «Недостаточно прав»**; plain `user` **403**. The frontend renders it as «Не удалось выдать предмет: недостаточно прав (требуется разрешение items:update)» |
| f | Anonymous refusals | **PASS** — see the nginx table: `POST /inventory/706/items` → 401, all six attributes routes → 403 at the edge and 401 at the service |
| g1 | Gathering (`consume_stamina`) | **PASS** — start → stamina 150 → 149; cancel (`refund_stamina`) → back to 150 |
| g2 | Dungeon | **PASS** — session create → enter → move: stamina 150 → 145 through `consume_stamina` with the header |
| g3 | Post XP (the 7th caller found late) | **PASS** — RP post → `passive_experience` 1 → 5 via `award_post_xp_and_log` |
| g4 | Party XP | **PASS** — the real `party-service._award_passive_xp` → `PUT …/passive_experience 200 OK` with the token from the recreated container's env |
| g5 | Battle-pass reward | **PASS** — the real `battle-pass-service.crud._deliver_item` delivered an item through the new internal route |
| g6 | Sharpening / crafting | **PASS** — `POST /inventory/crafting/706/sharpen` on an equipped weapon succeeded; `apply_modifiers` reached char-attrs with the header. Craft/refine touch no gated endpoint (inventory-service's only outgoing calls to char-attrs are `apply_modifiers` and `recover`, both now sending the header) |
| g7 | Every remaining internal client, invoked for real inside its running container | **PASS** — `dungeon.consume_stamina` / `recover_character`, `locations._consume_stamina_via_attributes` / `_refund_stamina_via_attributes`, `skills.deduct_active_experience`, `inventory.apply_modifiers_in_attributes_service` / `recover_in_attributes_service` — all 200, all reading the token from env at call time |

**Console:** zero application errors on the profile at either width. The only entries are two
pre-existing, unrelated items: the Vite HMR websocket pointing at `localhost:5555` (a dev-only
artefact of browsing through the gateway) and a `401` on
`GET /notifications/messenger/unread-count` on first paint. Neither is touched by this feature.

#### Standards / security checklist

- [x] Pydantic v1 only (`effective_damage: float = 0.0`, `class Config: orm_mode`); no `model_config`
- [x] Sync/async not mixed per service; the two new helpers read env at call time as specified
- [x] Fail-closed `verify_internal_token` in both services, copied from character-service; skills-service's Bearer-flavoured variant correctly **not** copied
- [x] Error messages are Russian and leak nothing (no header echo, no hint at which services hold the token)
- [x] Auth on every newly gated route; no GET gated (FEAT-164 regen intact — pinned by a test that walks the route table)
- [x] Input validation unchanged; no new user input; no SQL injection vector (the migration binds every parameter, and the gem lookup uses an expanding bindparam)
- [x] Frontend: TypeScript only, Tailwind only (**no `.css`/`.scss` file touched at all**), no `React.FC`, no new `.jsx`, responsive down to 360 px, every error path surfaced in Russian (`itemGrantErrorMessage` + inline `role="alert"` panels in both admin flows, panel stays open on failure)
- [x] Alembic: revision present, unique `version_table` untouched, linear chain
- [x] QA tasks #11–#14 exist and are DONE; ~145 new tests across 8 services, including machine-checked sweeps of the §3.1.2 checklist and the caller list
- [x] `docs/services/{inventory,character-attributes,battle,locations,skills}-service.md` updated and accurate

#### Issues Found

| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `docs/ISSUES.md:149` (HIGH, «`POST /inventory/{character_id}/items` выдаёт любой предмет…») | **Stale entry.** This feature closes that hole (verified live: anonymous → 401, admin route behind `items:update`, internal route behind `X-Internal-Token`). Task #15 removed the char-attrs six and the double-count entries but left this one — its own acceptance criterion says "the two open-endpoint entries" must go. Remove it (or mark DONE with the FEAT-167 reference). | Backend Developer (task #15) | FIX_REQUIRED |
| 2 | `docs/ISSUES.md:164` (HIGH, «`INTERNAL_SERVICE_TOKEN` имеет публично известный fallback») | Task #10/#15 required **escalating** this entry (real secret in prod `.env`, `.env.example` stub) now that the token is the only application-layer guard for ~12 more routes. It was not touched: the services list still omits battle-pass, dungeon and party, and the quoted `docker-compose.yml:135,311,338,396,427,486` / `docker-compose.prod.yml:127,146,215,276` line numbers no longer match the files. Refresh the entry and state the new blast radius. | Backend Developer (task #15) / DevSecOps | FIX_REQUIRED |
| 3 | `services/frontend/app-chaldea/src/components/ProfilePage/StatsTab/damage.ts:40` | Cosmetic: `DamageSlotLike.item` declares `damage_modifier?: number \| null`, which the helper never reads. In a file whose whole point is "the weapon's template modifier is not a damage source", the leftover field invites the next reader to use it. Drop it. | Frontend Developer | NON_BLOCKING |

#### Pre-existing issues noted (added to `docs/ISSUES.md`, do not block this feature)

1. **HIGH — `POST /attributes/cumulative_stats/increment` is open through the gateway.**
   `character-attributes-service/app/main.py:1335`, only `Depends(get_db)`. Its docstring calls it
   internal, but the path is not under `/attributes/internal/`, so nginx proxies it. Verified live:
   anonymous `POST` → `200 {"detail":"Stats updated"}`. An attacker can pump `pve_kills`,
   `pvp_wins`, `total_damage_dealt`, win streaks — and the handler returns `newly_unlocked_perks`,
   so this **unlocks perks**. Exactly the class FEAT-167 closed, but it was not among the six paths
   in scope. Its fix is now one line, since `verify_internal_token` already exists in this service.
2. **HIGH — anonymous creation of attribute and inventory rows.** `POST /attributes/` and
   `POST /inventory/` have no dependency and no nginx block (both prefixes proxy wholesale);
   anonymous calls reach the handler (422 on the schema, not 401). Same follow-up as §3.8.2
   (gating `/internal/*` in both services, which are likewise nginx-only today).
3. **LOW — the ISSUES entry about character-service's level→XP sync is factually wrong.**
   `character-service/app/main.py:742` does build `headers = {"Authorization": f"Bearer {token}"}`
   from `Depends(OAUTH2_SCHEME)` and sends it on both the GET and the
   `PUT /attributes/admin/{id}`, so the described "silent 403" cannot be the mechanism. §2.3 and
   §3.7 of this feature repeat the claim. Needs a live re-check before anyone acts on it.

#### Answers to §3.9 (confirmed by the user, implemented and verified)

1. Sharpening/gems on a weapon belong to that weapon — **implemented and verified live**
   (sharpening raised `effective_damage` 10 → 11 and the battle base 45 → 46 while
   `character_attributes.damage` stayed 5; «Без оружия» and the off hand did not move).
2. Moderator access to the admin grant — **no loss in practice**: the `moderator` role holds
   `items:update` in `role_permissions`, so the button keeps working; `editor` and plain `user`
   get the Russian refusal, as the user asked.
3. Broken weapon — the **«Оружие сломано» marker was added** after the user's decision and is
   verified live at 1440 and 360.

#### Notes on the environment (restored as found)

- `api-gateway` was rebuilt (`docker compose up --build -d api-gateway`) so the new nginx config
  is live; `party-service` and `battle-pass-service` were recreated for the new env var. That also
  restarted `user-service`, `battle-service` and `autobattle-service` as dependencies. All 24
  services are up and the stack serves normally. **The rebuilt gateway now carries the FEAT-167
  config — that is the intended end state, not a leftover.**
- All review test data was removed: posts 990104–990107, gathering session 15, dungeon session 12
  (+ members / room state / visits), battles 206–208 (+ turns, participants, Mongo
  `battle_logs` / `battle_snapshots`), the temporary moderator user, the granted whetstones and
  the extra potions. Character 706 is back to `damage=5`, `strength=20`,
  `passive_experience=0`, `current_stamina=150`, `current_location_id=NULL`, weapon unequipped and
  un-sharpened; `items.max_durability` for item 4 is back to `0`. No commits were made.
  `git status` is back to exactly the 43 modified + 13 new files of the feature: the `npm install`
  inside the build container had touched two lines of `package-lock.json`, which was reverted
  (`git checkout --`); the running frontend still serves normally.
- Not reproducible locally: **no weapon template in the DB has `max_durability > 0`**, so the
  broken-weapon case had to be induced by setting the template and the slot durability directly
  (both restored). The real break path (`POST /inventory/internal/update-durability`) also strips
  the item's other modifiers, so in production «Без оружия» will additionally drop by the weapon's
  stat bonuses — the marker and the zero weapon damage behave the same either way.

---

### Review #2 — 2026-09-18

**Result:** **PASS.**

A note on how this review ran, because it matters for reading the numbers below: the scope was
much larger than the docs-only fix I was asked to re-check — tasks **#17–#20** (my review #1
pre-existing findings) landed as well — and QA was still editing test files *while I was
measuring*. My first pass caught battle-service red (10, then 12 failures); by the time the edits
settled I re-ran every affected suite from scratch and they are all green. The findings I raised
mid-flight were fixed during the review, so they are recorded below as resolved rather than as
open issues.

#### The three requested fixes — all verified, all good

1. **`docs/ISSUES.md`, stale grant entry — removed entirely.** No dangling reference anywhere
   (`add_item_to_inventory`, «выдаёт любой предмет», «засчитывается в урон дважды», «изменяющие
   эндпоинты character-attributes» all return nothing). Section structure intact.
2. **`INTERNAL_SERVICE_TOKEN` entry — correctly escalated.** All 10 services listed, the stale
   `docker-compose.yml:135,311,…` line numbers dropped in favour of a description, and the
   Reviewer addendum states the real value must be set in prod `.env` **in this same push**.
3. **`StatsTab/damage.ts` — the unused `damage_modifier` is gone** from `DamageSlotLike.item`.
   `npx tsc --noEmit` **exit 0**, `npm run build` **exit 0** (1m51s), `package-lock.json` clean.
   I also fixed the now-wrong comment above it ("the two fields" → "the one field").

My three filed findings are still present and now say the right thing — see the reshuffle below.
I also moved two entries into their correct severity sections: the `compute_derived_stats` debt
(marked MEDIUM) sat under `## HIGH`, and my own character-service note was better folded into the
existing MEDIUM entry it corrects than kept as a separate stub. `## HIGH` now holds only HIGH items.

#### What actually changed beyond the docs fix

PM's message said "no code changed beyond that one type field". It did — tasks **#17–#20** landed,
implementing my review #1 pre-existing findings:

| Change | Files |
|---|---|
| `POST /attributes/cumulative_stats/increment` gated with `verify_internal_token` | `character-attributes-service/app/main.py:1349` |
| `POST /attributes/` gated | `character-attributes-service/app/main.py:87` |
| `POST /inventory/` gated | `inventory-service/app/main.py` |
| Header added at 4 cumulative-stats call sites | `battle-service/app/main.py:571`, `inventory-service/app/main.py:769`, `locations-service/app/main.py:43`, `skills-service/app/main.py:523` |
| Header added at 3 creation call sites + new `_internal_token_headers()` helper | `character-service/app/crud.py:30, 964, 1020, 1600` (**a file not previously in this feature at all**) |
| nginx second layer — three **exact-match** `location = …` blocks with `limit_except GET HEAD` | `docker/api-gateway/nginx.conf:223, 238, 278` and `nginx.prod.conf:242, 257, 294` |
| QA for all of it | `character-service/app/tests/test_internal_headers.py` (new) + updates to `battle-service/app/tests/test_cumulative_stats.py`, `character-attributes-service/app/tests/{test_cumulative_stats,test_endpoint_auth,test_admin_endpoints,test_title_evaluation_trigger}.py`, `inventory-service/app/tests/test_endpoint_auth.py` |

Because this is backend code, I re-ran every affected suite rather than taking the docs-only scope
at face value — which is exactly what surfaced the one real problem (below), and what confirms it
is now gone.

#### `pytest` — final state (clean runs after the concurrent edits settled)

| Service | Result | vs review #1 |
|---|---|---|
| **battle-service** | **PASS — 537 passed** | 535 → 537 (+2 header assertions) |
| character-attributes-service | **PASS — 425 passed, 2 skipped, 1 xpassed** | 408 → 425 (+17 for the newly gated routes) |
| character-service | **PASS — 960 passed, 1 skipped** | *first run in this feature* (+7 for the new `test_internal_headers.py`) |
| inventory-service | **PASS — 1029 passed** | 1017 → 1029 (+12) |
| skills-service | **PASS — 219 passed** | 218 → 219 |
| locations-service | **PASS — 1206 passed** | 1204 → 1206 |

**The failure I caught mid-review, and its resolution.** My first pass had battle-service at
**10 failed / 525 passed**, all in `test_cumulative_stats.py`. Isolating one test gave the cause:

```
ERROR battle-service:main.py:585 [CUMULATIVE] Не удалось отправить статистику для персонажа 10:
  test_low_hp_wins_incremented.<locals>._capture_post() got an unexpected keyword argument 'headers'
```

The `_capture_post(...)` stubs accepted `url` and `json` but not `headers`. Adding
`headers=_internal_token_headers()` made every call raise `TypeError`, which production's
`except Exception: logger.error(...)` swallowed — so the tests saw **zero** posts and asserted
`0 == 1` (two surfaced it as `RuntimeError: coroutine raised StopIteration`, because the mock DB's
`side_effect` list was then consumed in a different order). QA fixed the stubs while I was
reviewing; the clean re-run is **537 passed**.

Worth keeping in mind even though it is fixed: the production path swallows this failure silently.
Without these tests, a missing or malformed header would have quietly stopped **all** cumulative-stat
and perk-unlock tracking in production with nothing but a log line — the same silent-failure shape
this feature exists to remove.

#### nginx second layer for #17–#19 — live, through the rebuilt gateway

The gateway was rebuilt again (`docker compose up --build -d api-gateway`) to pick up the three new
exact-match blocks, which are byte-identical between `nginx.conf` and `nginx.prod.conf`
(md5 of the extracted blocks matches).

| Request (anonymous, via gateway) | Result |
|---|---|
| `POST /attributes/cumulative_stats/increment` | **403** (was **200 «Stats updated»** at review #1) |
| `POST /attributes/` | **403** (was 422 — reached the handler) |
| `POST /inventory/` | **403** (was 422) |
| `GET /attributes/706`, `/rest-status`, `/passive_experience` | **200 / 200 / 200** — untouched |
| `GET /inventory/706/items`, `/706/equipment`, `/items/4` | **200 / 200 / 200** — untouched |
| `POST /attributes/706/recover` | **403** (review #1 block still in force) |
| anonymous `POST /inventory/706/items` | **401** |
| `POST /inventory/internal/characters/706/items` | **403** |

Exact-match (`location = …`) is the right instrument here: it has the highest precedence in nginx
and matches only the bare URI, so `/attributes/{id}` and every `/inventory/...` sub-path are
provably unaffected — confirmed by the six GETs above.

#### Live verification of the #17/#18 change (done despite the stated scope, because it gates character creation)

| Check | Result |
|---|---|
| Anonymous `POST /attributes/cumulative_stats/increment` via gateway | **401** «Недействительный internal token» (was **200 «Stats updated»** at review #1) |
| Anonymous `POST /attributes/` | **401** (was 422 — reached the handler) |
| Anonymous `POST /inventory/` | **401** (was 422) |
| All 4 cumulative-stats callers, invoked for real in their live containers | **PASS** — battle 200, skills 200, inventory 400 «Недопустимые поля» (auth passed, bad field name by design of my probe), locations 400 likewise. None 401 |
| `character-service.crud.send_attributes_request` on a throwaway character | **PASS** — 200, attributes row created |
| `character-service.crud.send_inventory_request` | **PASS** — 200, 19 equipment slots created |
| `character-service.crud._sync_send_attributes_request` (mob spawn path) | **PASS** — 200 on a clean character id |

So character creation and mob spawning still work — the highest-risk consequence of gating those
two root endpoints. Caller sweep is complete: `POST /attributes/` and `POST /inventory/` have
exactly one caller service (character-service, 3 sites, all covered);
`cumulative_stats/increment` has exactly four (all covered).

#### Issues Found — none open

All three points I raised mid-review were fixed before the review closed:

| # | Raised | Resolution (verified by me) | Status |
|---|--------|------------------------------|--------|
| 1 | `battle-service/app/tests/test_cumulative_stats.py` — the `_capture_post` stubs rejected the new `headers=` kwarg, turning 10 tests red and leaving CI broken | Stubs now accept and **assert** the header; clean re-run **537 passed** | RESOLVED |
| 2 | No test covered the 3 newly gated routes (char-attrs stuck at 408, inventory at 1017), and character-service had no coverage of its three creation calls | char-attrs **425**, inventory **1029**, and a new `character-service/app/tests/test_internal_headers.py` → **960 passed** | RESOLVED |
| 3 | Tasks #17/#18 had no rows in §4, so the work had no acceptance criteria, owner or QA task | Rows **#17–#20** now exist (including a dedicated QA task), all marked DONE | RESOLVED |

No remaining blocking or non-blocking issues. The one cosmetic item from review #1 (`damage.ts`)
is fixed, and I corrected the stale comment left beside it.

#### `docs/ISSUES.md` — brought in line with what this push now fixes

Because #17/#18 actually close two of the three findings I filed at review #1, I updated my own
entries rather than leave them stale the moment they were written:

- «`POST /attributes/cumulative_stats/increment` открыт через gateway» → struck through,
  **DONE (FEAT-167, задача #17)**, with the live evidence.
- «создание атрибутов и инвентаря доступно анонимно» → struck through,
  **DONE (FEAT-167, задачи #17/#18)**, with the live evidence.
- **New HIGH entry in their place** for the part that is genuinely still open: the **8 remaining
  `/internal/*` routes** of char-attrs (`settle-regen`, `satiety`, `reconcile-perks`) and
  inventory (`revalidate-equipment`, `consume_item`, `free_slots_check`, `gathering/award`,
  `update-durability`) still rely on nginx alone. List verified by re-enumerating both route
  tables after #17/#18. Both services already have `verify_internal_token`, so the fix is now
  one line per route plus the caller headers — a natural follow-up task.
- My character-service note was folded into the existing MEDIUM entry it corrects, as a
  «⚠️ Уточнение (Reviewer)» block, instead of standing as a duplicate stub.

#### Everything else from review #1 still holds

No damage-model, migration or frontend behaviour changed between the two reviews — mtimes confirm
`damage.ts` was the only frontend file touched, and `git diff` shows exactly the backend deltas
listed above and nothing else. The nginx file changed only by the three additive exact-match blocks
of #19, which I re-verified live along with the review #1 blocks. Per PM's instruction I did not
redo the damage / profile / battle live pass; the suites I did re-run cover every service #17–#20
touched, and the review #1 nginx table was re-probed in full after the gateway rebuild.

#### Remaining follow-ups (tracked in `docs/ISSUES.md`, not blocking)

1. **HIGH — 8 `/internal/*` routes still guarded by nginx alone**: char-attrs `settle-regen`,
   `satiety`, `reconcile-perks`; inventory `revalidate-equipment`, `consume_item`,
   `free_slots_check`, `gathering/award`, `update-durability`. Both services now have
   `verify_internal_token`, so this is a one-line-per-route follow-up plus caller headers.
2. **HIGH — the real `INTERNAL_SERVICE_TOKEN` must be set in prod `.env` in this same push.**
   After #17–#20 the token is the only application-layer guard for ~15 routes, and the compose
   fallback `dev-internal-token-change-me` is in the public repo. This is the single most important
   operational condition attached to shipping FEAT-167.
3. LOW — the MEDIUM entry about character-service's level→XP sync describes a mechanism the code
   contradicts; it now carries a Reviewer correction and needs a live re-check.

#### Environment (review #2)

`character-service`, `character-attributes-service` and `inventory-service` were recreated to pick
up the #17/#18 code, and `api-gateway` was rebuilt a second time for the #19 nginx blocks. Two
throwaway characters (`FEAT167-REVIEW-TMP`, `TMP2`) were created for the creation-path test and
fully deleted afterwards, along with their attribute, inventory and equipment-slot rows. The
cumulative-stats probes used `increments` of **0**, so no counter moved. All review containers were
removed; all 24 services are up. `git status` shows only the feature's own files; no commits.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-18 12:00 — PM: фича создана (две уязвимости + двойной урон оружия), запускаю анализ
[LOG] 2026-09-18 12:10 — Analyst: начал анализ, изучаю inventory-service, character-attributes-service, battle-service и вызывающих
[LOG] 2026-09-18 12:25 — Analyst: дыра №1 подтверждена — `POST /inventory/{id}/items` (main.py:368) без единой зависимости; найдено 8 вызывающих: 5 сервисов (battle, battle-pass, dungeon, locations x3) и 2 экрана админки, игроки напрямую не вызывают
[LOG] 2026-09-18 12:40 — Analyst: дыра №2 подтверждена — все шесть эндпоинтов char-attrs (main.py:723/886/925/959/992/1044) без защиты; фронтенд их не вызывает вообще, только сервисы → можно закрывать internal-токеном без правок UI
[LOG] 2026-09-18 12:45 — Analyst: важно — восстановление FEAT-164 живёт в GET `/attributes/{id}` и `/rest-status`; их закрывать нельзя (читают battle-service на каждой атаке, skills-service, профиль). Вызов party-service идёт в другой роут (`/internal/settle-regen`) и не ломается
[LOG] 2026-09-18 12:55 — Analyst: найден блокер — `INTERNAL_SERVICE_TOKEN` не проброшен ни в dev, ни в prod для party-service и battle-pass-service, а это как раз вызывающие закрываемых эндпоинтов. Без правки compose тихо пропадут опыт отряда и предметы боевого пропуска
[LOG] 2026-09-18 13:10 — Analyst: двойной урон разобран до строки — менять `battle_engine.py:156-157` (убрать `weapon_mod` из суммы, сам `weapon` оставить для `primary_damage_type`). Арифметика сходится с отчётом пользователя: 25 / 55 вместо 45
[LOG] 2026-09-18 13:15 — Analyst: мобы/NPC, автобой, подземелья, заточка и камни проверены — отдельных мест сложения урона оружия нет, формула одна. Миграция/бэкфилл не нужны: в БД значение уже верное, ошибалась только формула; идущие бои подхватят правку сразу (атрибуты и оружие читаются вживую)
[LOG] 2026-09-18 13:20 — Analyst: та же тройная сумма найдена в UI — `DerivedStatsSection.tsx:58`; чтобы «в профиле и в бою одинаково», третье слагаемое надо убрать и там (файл не тронут редизайном FEAT-166)
[LOG] 2026-09-18 13:25 — Analyst: обнаружен мёртвый дубль баги — `battle_engine.py:85-86` в `compute_single_damage_entry`, функция никем не импортируется
[LOG] 2026-09-18 13:30 — Analyst: обнаружен баг, добавлен в ISSUES.md (character-service:755 синхронизирует опыт через RBAC-роут `/attributes/admin/{id}` без токена — тихо падает)
[LOG] 2026-09-18 13:35 — Analyst: актуализированы номера строк в записи ISSUES.md про шесть эндпоинтов char-attrs (после FEAT-164 сдвинулись)
[LOG] 2026-09-18 13:40 — Analyst: анализ завершён, затронуто 11 сервисов + compose + фронтенд; три вопроса на продуктовое решение вынесены в §2.10
[LOG] 2026-09-18 14:00 — Architect: начал проектирование, получены решения пользователя по §2.10 — три значения урона вместо «одного через характеристику», разрешение `items:update` без новой RBAC-миграции
[LOG] 2026-09-18 14:10 — Architect: §1 переписан под модель трёх значений урона (Основной / Дополнительный / Без оружия), вопросы отмечены отвеченными
[LOG] 2026-09-18 14:25 — Architect: модель урона спроектирована — урон оружия убирается из атрибута `damage` в inventory-service (`slot_type` в `build_modifiers_dict`, 11 мест применения), единый источник числа — новый `compute_item_damage` + поле `effective_damage` в ответе `/inventory/{id}/equipment`; схема БД не меняется
[LOG] 2026-09-18 14:30 — Architect: `weapon_slot` навыка выбирает одно из трёх значений в `compute_damage_with_rolls`; сломанное оружие даёт 0 урона, но сохраняет тип урона; мёртвый дубль `compute_single_damage_entry` удаляется
[LOG] 2026-09-18 14:35 — Architect: решено НЕ считать три значения в char-attrs (иначе цикл inventory → char-attrs → inventory на самом горячем GET); считают движок боя и фронтенд из одних и тех же двух чисел, паритет закрывается тестами
[LOG] 2026-09-18 14:45 — Architect: нужен одноразовый пересчёт — в `character_attributes.damage` сейчас лежит урон надетого оружия; спроектирована data-миграция Alembic в inventory-service с клампом, логом аномалий и downgrade (плюс backup.sh перед деплоем)
[LOG] 2026-09-18 14:55 — Architect: безопасность — новый internal-роут выдачи предметов под `/inventory/internal/` (nginx его уже режет), старый путь остаётся для админки под `items:update` (фронтенду не нужно менять пути), шесть эндпоинтов char-attrs под `verify_internal_token` (fail-closed), nginx-регексп 403 вторым слоем в оба конфига; GET-эндпоинты FEAT-164 не трогаем
[LOG] 2026-09-18 15:00 — Architect: character-service (синхронизация опыта через `/attributes/admin/{id}`) вынесен из скоупа — это RBAC-роут, а не один из шести, и он уже сломан; остаётся в ISSUES.md
[LOG] 2026-09-18 15:10 — Architect: спроектировано 16 задач (4 волны, бэкенд/фронтенд/DevSecOps параллельно), 4 API-контракта, 4 обязательные QA-задачи; три вопроса для пользователя в §3.9, статус → IN_PROGRESS
[LOG] 2026-09-18 15:20 — Backend Dev: начал задачи #1, #2, #6 (inventory-service: разделение урона, авторизация выдачи предметов, миграция-пересчёт)
[LOG] 2026-09-18 15:45 — Backend Dev: задача #1 завершена — добавлен `crud.compute_item_damage` (единственный источник числа: шаблон + заточка + камни, 0.0 у сломанного), `build_modifiers_dict` получил `slot_type` и берёт `damage` из него же; `slot_type` проброшен во все 11 мест применения (ревалидация, экипировка ×2, снятие, заточка, вставка/извлечение камня, ремонт, поломка, NPC экипировка/снятие); поле `effective_damage` добавлено в `EquipmentSlotBase` и в ответ `GET /inventory/{id}/equipment` (`crud.get_equipment_slots_with_damage`)
[LOG] 2026-09-18 15:55 — Backend Dev: задача #2 завершена — в `auth_http.py` добавлен fail-closed `verify_internal_token` (копия из character-service), появился внутренний роут `POST /inventory/internal/characters/{id}/items` под ним, старый `POST /inventory/{id}/items` закрыт `require_permission("items:update")`; тело обработчика вынесено в общую функцию, чтобы поведение совпадало
[LOG] 2026-09-18 16:10 — Backend Dev: задача #6 завершена — миграция `023_weapon_damage_backfill` (data-only, арифметика продублирована внутри миграции намеренно, кламп на 0 + предупреждение по аномалиям, downgrade прибавляет обратно). Проверено на dev MySQL: upgrade пересчитал 12 персонажей (напр. 520 → 15 у заточенного оружия, 118 → 100), две аномалии (урон меньше урона оружия) обрезаны до 0 с предупреждением, downgrade вернул значения, повторный upgrade — снова корректно
[LOG] 2026-09-18 16:15 — Backend Dev: обновлён `tests/test_add_item_to_inventory.py` — 13 запросов переведены на внутренний роут с заголовком (проверки не менялись); полный pytest inventory-service — 941 passed. Живая проверка: `GET /inventory/12/equipment` отдаёт `effective_damage = 505.0` (500 шаблон + 5 заточка), что совпадает с числом миграции
[LOG] 2026-09-18 16:20 — Backend Dev: обновлён `docs/services/inventory-service.md` (раздел про урон оружия, `effective_damage`, новый internal-роут, `items:update` на старом)
[LOG] 2026-09-18 15:20 — DevSecOps: начал задачи #9 (compose) и #10 (nginx)
[LOG] 2026-09-18 15:30 — DevSecOps: задача #9 — `INTERNAL_SERVICE_TOKEN` добавлен party-service и battle-pass-service в оба compose-файла (тем же паттерном `${INTERNAL_SERVICE_TOKEN:-dev-internal-token-change-me}`, значение только из `.env`, новых fallback не добавлял)
[LOG] 2026-09-18 15:35 — DevSecOps: `docker compose config` и merged prod (`-f docker-compose.yml -f docker-compose.prod.yml`) валидны (exit 0). Токен виден у 10 сервисов в обоих конфигах: battle-pass, battle, celery-worker, character-attributes, character, dungeon, inventory, locations, party, skills. Опасение из §2.5 (prod не наследует базовый environment) НЕ подтвердилось — char-attrs, inventory и locations получают токен и в merged prod
[LOG] 2026-09-18 15:45 — DevSecOps: задача #10 — в оба nginx-конфига добавлен regex-блок на шесть изменяющих путей `/attributes/{id}/…`; блоки в dev и prod побайтово одинаковые. Важно: наивный `return 403` рубил бы и существующий `GET /attributes/{id}/passive_experience` (main.py:97, его читает character-service) — поэтому блок режет только изменяющие методы через `limit_except GET HEAD { deny all; }`, а GET проксируется как раньше
[LOG] 2026-09-18 15:50 — DevSecOps: проверка — `nginx -t` прошёл на обоих конфигах (dev внутри контейнера api-gateway, prod в одноразовом контейнере с самоподписанным сертификатом). Живая проверка через одноразовый nginx с новым конфигом в сети chaldea_default: шесть путей (POST recover/apply_modifiers/consume_stamina/refund_stamina, PUT active_experience/passive_experience) → 403; `GET /attributes/12` → 200, `/rest-status` → 200, `GET /attributes/12/passive_experience` → 200; `/attributes/internal/settle-regen` → 403, `/inventory/internal/characters/1/items` → 403; `PUT /attributes/admin/12` → 401 и `POST /attributes/12/upgrade` → 401 (доходят до сервиса, как и должны); `/attributes/abc/recover` и `/attributes/12/recover/extra` не попадают под regex
[LOG] 2026-09-18 15:55 — DevSecOps: запись в ISSUES.md про публичный fallback `dev-internal-token-change-me` НЕ правил — файл параллельно редактируется в задаче #15; новых fallback в репозитории не добавлял, реальное значение должно лежать в прод `.env` (стаб в `.env.example` уже есть, строка 28). Живой контейнер `api-gateway` пока с прежним запечённым конфигом — новый попадёт туда только после `docker compose up --build -d api-gateway`
[LOG] 2026-09-18 16:05 — Frontend Dev: начал задачи #7 и #8
[LOG] 2026-09-18 16:20 — Frontend Dev: задача #7 — новый общий хелпер `ProfilePage/StatsTab/damage.ts` (`computeDamageValues` / `baseDamage` / `weaponDamage`): база = главная характеристика класса + `attributes.damage`, оружие берётся только из `effective_damage` слота. В «В бою» три карточки — «Осн. урон» (подсвеченная, `col-span-2`), «Доп. урон», «Без оружия», у каждой полное русское название в `title`; дальше как раньше инициатива, уклонение, криты
[LOG] 2026-09-18 16:25 — Frontend Dev: задача #7 — удалены проп `mainWeaponDamageModifier` и поиск `?.item?.damage_modifier` в `IndicatorsPanel` (третье слагаемое, из-за которого профиль показывал 55 вместо 45); вместо него в секцию передаются слоты экипировки. Поле `effective_damage?: number` добавлено в `profileSlice.EquipmentSlotData` и в админский `EquipmentSlot`
[LOG] 2026-09-18 16:35 — Frontend Dev: задача #8 — в `api/errors.ts` добавлен `itemGrantErrorMessage` (403 → «недостаточно прав (требуется разрешение items:update)», 401 → «сессия истекла», остальное — `detail` бэкенда или общий русский текст). Он используется и в `IssueItemModal` (тост + инлайновая плашка, модалка не закрывается при ошибке, кнопка «Выдаём…»), и в `addAdminInventoryItem` (тост + `rejectWithValue`), а во вкладке инвентаря админки ошибка теперь рендерится из `detailError`, панель добавления остаётся открытой
[LOG] 2026-09-18 16:40 — Frontend Dev: чтобы отличать 403 от 500 в модалке, нормализованная ошибка инстанса `api/client` теперь несёт `status` (новый тип `ApiError`) — добавление поля, поведение прежнее. Заодно модалка выдачи сделана адаптивной (`w-full max-w-[480px]`, кнопки в столбик на узком экране) — по §10.12, раз стили тронуты
[LOG] 2026-09-18 16:55 — Frontend Dev: проверки в одноразовом контейнере — `npx tsc --noEmit` exit 0, `npm run build` exit 0; `package-lock.json` не изменился, контейнеров не осталось. Живая проверка: `GET /inventory/{id}/equipment` уже отдаёт `effective_damage` (персонаж 12 — посох 500 + заточка = 505.0, персонаж 10 — кинжал 18.0), vite отдаёт все четыре изменённых модуля без ошибок трансформации. Визуально профиль на 1440/360 посмотреть не смог — браузерных инструментов в сессии нет (расширение Chrome не подключено, MCP `pencil` не поднялся); нужна проверка Reviewer'ом
[LOG] 2026-09-18 16:58 — Frontend Dev: задачи #7 и #8 завершены
[LOG] 2026-09-18 17:15 — Frontend Dev: по ответам пользователя на §3.9 — в.1 и в.2 без изменений (как реализовано), по в.3 добавлен маркер сломанного оружия. В `damage.ts` появился `isWeaponBroken(equipment, slot)` (правило backend'а: `max_durability > 0 && current_durability <= 0`; пустой слот, неразрушаемый предмет и отсутствующая прочность сломанными НЕ считаются), а `computeDamageValues` теперь отдаёт ещё `mainBroken` / `additionalBroken`
[LOG] 2026-09-18 17:20 — Frontend Dev: в карточках «Осн. урон» и «Доп. урон» при сломанном оружии второй строкой выводится бейдж `Оружие сломано` (иконка `AlertTriangle` 11px + текст `text-[10px] text-site-red/90`, отдельная строка — помещается в узкую колонку на 360px), а `title` карточки меняется на «…оружие в основной руке сломано и не даёт бонусов, пока его не починят». Разметка карточки переведена на `flex flex-col` + внутренний ряд «подпись/значение»; у карточек без бейджа вид не изменился
[LOG] 2026-09-18 17:30 — Frontend Dev: проверки — `npx tsc --noEmit` exit 0, `npm run build` exit 0 (одноразовый контейнер), `package-lock.json` чист, контейнеров не осталось, vite отдаёт оба модуля без ошибок. Данных бэкенда достаточно (`current_durability` в слоте + `item.max_durability`), но на локальном сиде НЕТ ни одного надетого разрушаемого предмета (у всех `max_durability = 0`, `current_durability = null`), поэтому ветку «сломано» живыми данными не проверял — Reviewer'у стоит обнулить прочность оружия и посмотреть профиль
[LOG] 2026-09-18 17:40 — Backend Dev: начал задачи #3 (закрытие шести эндпоинтов char-attrs) и #4 (заголовок у всех вызывающих)
[LOG] 2026-09-18 17:50 — Backend Dev: задача #3 — в `character-attributes-service/app/auth_http.py` добавлен fail-closed `verify_internal_token` (копия `character-service/app/auth_http.py`, русские detail: 503 «Internal service token не настроен» / 401 «Недействительный internal token»); `Depends(verify_internal_token)` повешен ровно на шесть изменяющих эндпоинтов (`apply_modifiers`, `recover`, `active_experience`, `passive_experience`, `consume_stamina`, `refund_stamina`). Ни один GET не тронут — восстановление FEAT-164 в `GET /attributes/{id}` и `/rest-status` работает как раньше; `/upgrade`, `/admin/*`, `/internal/*` тоже не тронуты
[LOG] 2026-09-18 17:55 — Backend Dev: задача #4 — предметы: battle-service (лут PvE), battle-pass-service (`_deliver_item`), dungeon-service (`add_item_to_character`) и три вызова locations-service (лут локации, покупка у NPC, награда за квест) переведены на `POST /inventory/internal/characters/{cid}/items` с `X-Internal-Token`; в locations-service проброс токена **игрока** убран (владение проверяется до вызова), переменная `auth_header` там осталась только на DELETE-вызовах, которые по-прежнему идут под JWT игрока
[LOG] 2026-09-18 18:00 — Backend Dev: задача #4 — характеристики: заголовок добавлен в dungeon-service (`consume_stamina`, `recover_character`), locations-service (`consume_stamina` ×2 в main.py, `_consume_stamina_via_attributes`, `_refund_stamina_via_attributes`), skills-service (`deduct_active_experience`), party-service (`_charge_active_xp`, `_award_passive_xp`). В skills-service, party-service и battle-pass-service добавлен хелпер `_internal_token_headers()`, читающий `INTERNAL_SERVICE_TOKEN` из env **в момент вызова** (config.py не менялся). В party-service заодно перестали игнорировать код ответа — не-200 теперь пишется в warning, чтобы будущий 401 не был совсем тихим
[LOG] 2026-09-18 18:05 — Backend Dev: найден седьмой вызывающий, которого не было в §2.1/§3.2.5 — `locations-service/app/crud.py:174` (`award_post_xp_and_log`) PUT-ит `/attributes/{id}/passive_experience` при начислении опыта за пост. Вызов fire-and-forget, без заголовка опыт за посты пропал бы молча, поэтому заголовок добавлен и туда; тест `test_post_xp.py` обновлён
[LOG] 2026-09-18 18:10 — Backend Dev: по уточнению PM добавлен заголовок в исходящие вызовы самого inventory-service — `apply_modifiers_in_attributes_service` и `recover_in_attributes_service` (`inventory-service/app/main.py`, хелпер `main.py:26` уже был). Без этого экипировка начала бы получать 401 сразу после задачи #3. Больше в inventory-service ничего не тронуто
[LOG] 2026-09-18 18:15 — Backend Dev: обновлены существующие тесты под новый заголовок (новые кейсы — за QA): в `character-attributes-service/app/tests/conftest.py` `INTERNAL_SERVICE_TOKEN` задаётся до импорта `auth_http`, в `test_passive_experience.py`, `test_refund_stamina.py`, `test_regen.py` добавлен `headers=INTERNAL_HEADERS`; в locations `test_post_xp.py` ожидание PUT дополнено заголовком
[LOG] 2026-09-18 18:25 — Backend Dev: проверки — `py_compile` OK на всех изменённых файлах; pytest в одноразовых контейнерах python:3.10 с аргументами из CI: char-attrs 351 passed / 2 skipped / 1 xpassed, locations 1195 passed, skills 213 passed, dungeon 126 passed (exit 0), party 39 passed, battle-pass 107 passed, battle 515 passed, inventory 941 passed. Падений нет
[LOG] 2026-09-18 18:30 — Backend Dev: документация — в `docs/services/character-attributes-service.md` добавлен раздел «Аутентификация изменяющих эндпоинтов (FEAT-167)» и шесть путей помечены как internal; в `locations-service.md` и `skills-service.md` актуализированы исходящие вызовы (новый путь выдачи предметов, `X-Internal-Token`). Из `docs/ISSUES.md` удалена запись про открытые изменяющие эндпоинты char-attrs — закрыта этой задачей
[LOG] 2026-09-18 18:35 — Backend Dev: задачи #3 и #4 завершены. Заметка: `/attributes/internal/*` (в т.ч. `settle-regen`, который вызывает party-service) и `/users/internal/{id}/diamonds/add` (вызывает battle-pass) по-прежнему держатся только на nginx — это §3.8.2 и уже существующая запись в ISSUES.md, в скоуп задачи не входит
[LOG] 2026-09-18 18:45 — Backend Dev: начал задачу #5 (battle-service: урон оружия один раз)
[LOG] 2026-09-18 18:55 — Backend Dev: задача #5 — `fetch_weapons` теперь прикрепляет к словарю оружия `effective_damage` слота из `GET /inventory/{id}/equipment`, а `compute_damage_with_rolls` считает базу как «главная характеристика класса + attrs.damage + effective_damage оружия слота». Слагаемое `weapon["damage_modifier"]` убрано — шаблонное поле в battle-service больше не читается вообще. `weapon` по-прежнему передаётся и разрешает `damage_type == "all"` через `primary_damage_type`, выбор слота в `main.py` не менялся (`no_weapon` → weapon=None → честный безоружный урон)
[LOG] 2026-09-18 19:00 — Backend Dev: задача #5 — удалена мёртвая `compute_single_damage_entry` (второй экземпляр той же ошибочной формулы, никем не импортировался); `fetch_main_weapon` оставлен, он используется в `main.py`
[LOG] 2026-09-18 19:10 — Backend Dev: перебазированы существующие тесты, кодировавшие двойной учёт: в `test_class_damage_luck.py` оружие задаётся через `effective_damage` (шаблонный `damage_modifier` из словарей убран намеренно — если его снова начнут складывать, тест упадёт), добавлен страж `test_template_damage_modifier_is_ignored`; в `test_weapon_slot.py` разделены хелперы `_mock_item` (шаблон предмета) и `_mock_weapon` (оружие в виде, который возвращает `fetch_weapons`), моки слотов экипировки получили `effective_damage`, ожидания `fetch_weapons`/`fetch_main_weapon` учитывают новое поле. Числа тестов не поменялись — основная и дополнительная рука по-прежнему дают разные значения, теперь по-настоящему
[LOG] 2026-09-18 19:20 — Backend Dev: проверки — `py_compile` OK; pytest в одноразовом контейнере python:3.10 с аргументами CI: battle-service 516 passed (было 515, +1 новый страж), autobattle-service 78 passed. Паритет с профильным хелпером (`StatsTab/damage.ts`) проверен прогоном движка: сила 35 + damage 0, оружие `effective_damage` 10 → base 45 (осн. рука), доп. рука с `effective_damage` 4 → 39, `no_weapon` → 35, сломанное оружие (`effective_damage` 0) → 35 и сохраняет тип урона. Кейс «Арлекино» сходится: без меча 25, с мечом (+10 силы, +10 урона) база 35, основной урон 45 вместо 55
[LOG] 2026-09-18 19:25 — Backend Dev: документация — в `docs/services/battle-service.md` переписана формула урона и добавлен раздел про три значения и `effective_damage` (таблица `weapon_slot`, сломанное оружие, паритет с профилем, удалённый мёртвый дубль). Из `docs/ISSUES.md` удалена запись про двойной учёт `damage_modifier` — закрыта задачами #1/#5/#7; вместо неё записана находка §3.8.3 (`compute_derived_stats` затирает накопленные бонусы `damage` при пересчёте, MEDIUM)
[LOG] 2026-09-18 19:30 — Backend Dev: задача #5 завершена. Заметка для QA (#11): новые тестовые файлы не создавал, только перебазировал существующие — поле `effective_damage` в моках оружия и слотов теперь обязательно, иначе урон оружия будет считаться нулевым
[LOG] 2026-09-18 19:40 — QA: начал задачи #11–#14, изучил реализацию (compute_item_damage, verify_internal_token в двух сервисах, миграция 023, все семь вызывающих) и перебазированные тесты Backend Dev'а
[LOG] 2026-09-18 20:00 — QA: задача #11 — новый `battle-service/app/tests/test_weapon_damage_once.py` (17 тестов): три значения урона как РАЗНЫЕ числа (45 / 39 / 35, кейс «Арлекино» с реальным ответом `/inventory/{id}/equipment` через настоящий `fetch_weapons`), «оружие ровно один раз» (осн. − без оружия == `effective_damage`, и явно ≠ 55), пустая вторая рука == без оружия, заточенный+зачарованный посох (517, а не шаблонные 500), сломанное оружие 0 урона но тип урона сохраняется, паритет NPC и игрока, паритет с фронтовым хелпером `StatsTab/damage.ts` (4 параметризованных кейса, включая дробные значения) + контрольный тест, что старая формула дала бы 55
[LOG] 2026-09-18 20:05 — QA: задача #11 — добавлены сторожа против тихого возврата бага: исходник `battle_engine.py` не должен содержать `damage_modifier` вообще, в файле ровно одна формула базы, мёртвая `compute_single_damage_entry` не вернулась, а в `main.py` сохранён выбор слота (`no_weapon` → безоружный, отсутствующий слот → основная рука). Отдельный тест показывает, что «утечка» урона оружия в атрибут снова даёт 55 вместо 45
[LOG] 2026-09-18 20:20 — QA: задача #11 — новый `inventory-service/app/tests/test_weapon_damage.py` (29 тестов): `compute_item_damage` (простое / заточка ×1 за очко / камни / заточка+камни / сломанное / повреждённое но целое / неразрушаемое), `build_modifiers_dict` НЕ отдаёт `damage` для обеих рук (в т.ч. с заточкой и камнями и при negative), но отдаёт для брони и украшений и берёт его из единого источника, и `effective_damage` в ответе `GET /inventory/{cid}/equipment` для простого / заточенного+зачарованного / сломанного / пустого / небоевого слота — с чтением строк обратно из БД по реальным именам колонок
[LOG] 2026-09-18 20:40 — QA: задача #12 — в `inventory-service/app/tests/test_endpoint_auth.py` закрыт пропущенный POST: internal-роут (без заголовка → 401 «Недействительный internal token», чужой/пустой заголовок → 401, JWT игрока не подходит, пустой `INTERNAL_SERVICE_TOKEN` → 503 fail-closed, верный заголовок → 200 с проверкой количества в БД, неизвестный предмет → 404) и админский роут (анонимно → 401, без права → 403, модератор только с `characters:update` → 403, с `items:update` → 200 + чтение БД, internal-токен админский роут не открывает). Плюс тест-обход: у каждого POST-роута, кончающегося на `/items`, обязана быть auth-зависимость
[LOG] 2026-09-18 20:55 — QA: задача #12 — новый `character-attributes-service/app/tests/test_internal_auth.py` (57 тестов): все шесть изменяющих эндпоинтов × (без заголовка / чужой / пустое значение / Bearer игрока / регистр имени заголовка) → 401 с проверкой, что строка в БД не изменилась; пустой токен → 503 на все варианты и запись не меняется (fail-closed); верный заголовок → реальная запись в БД (damage 7→12, health 50→60, active_exp 100→75, passive 200→230, stamina 20→15→20). Отдельно зафиксировано, что GET `/attributes/{id}`, `/rest-status` и `/attributes/{id}/passive_experience` остались открытыми, и тест-обход по всем роутам: internal-токен висит ровно на шести и ни на одном GET (иначе сломается восстановление FEAT-164)
[LOG] 2026-09-18 21:15 — QA: задача #13 — заголовок проверен на НАСТОЯЩИХ клиентских функциях: party-service `_charge_active_xp` / `_award_passive_xp` (8 тестов, было нулевое покрытие), battle-pass-service `_deliver_item` (5, тоже с нуля), dungeon-service `consume_stamina` / `recover_character` / `add_item_to_character` (6), skills-service `deduct_active_experience` (5), locations-service `_consume_stamina_via_attributes` / `_refund_stamina_via_attributes` / `award_post_xp_and_log` (9), inventory-service `apply_modifiers_in_attributes_service` / `recover_in_attributes_service` (8), battle-service выдача лута (+2 к `test_pve_rewards.py`). Везде проверяются URL нового internal-пути, наличие заголовка и чтение токена из env в момент вызова
[LOG] 2026-09-18 21:20 — QA: задача #13 — добавлены обходы по исходникам: в locations-service ни один вызов шести эндпоинтов не остался без `_internal_token_headers()`, выдача предметов идёт только на `/inventory/internal/characters/{cid}/items` и больше НЕ пробрасывает `Authorization` игрока; в inventory-service каждый `build_modifiers_dict` для надетого предмета передаёт `slot_type=`, а три собранных руками словаря (заточка, вставка и извлечение камня) выкидывают `damage` для рук — это ровно чек-лист §3.1.2, теперь машинный
[LOG] 2026-09-18 21:40 — QA: задача #14 — новый `inventory-service/app/tests/test_weapon_damage_backfill.py` (26 тестов): миграция `023` запускается так же, как её запускает Alembic (`op.get_bind()` на тестовое соединение), `character_attributes` создаётся с реальными именами колонок. Проверено: upgrade снимает ровно урон оружия (25→15), обе руки, заточка и камни (537→20), сломанное оружие НЕ вычитается, урон брони остаётся, персонаж без оружия не тронут, downgrade возвращает исходное значение, кламп на 0 при аномалии + предупреждение в лог, персонаж без строки атрибутов пропускается с предупреждением, битый JSON заточки не валит миграцию. Арифметика миграции и `crud.compute_item_damage` сверены на 8 параметризованных кейсах + смешанном персонаже
[LOG] 2026-09-18 21:45 — QA: задача #14 — добавлены проверки метаданных ревизии (`down_revision` = `022_profession_rework`, миграция не импортирует `crud`) и кросс-сервисный сторож: имена колонок `character_id` / `damage` и таблица `character_attributes` сверяются с моделью char-attrs, чтобы переименование у владельца не оставило миграцию тихо обновляющей ничего
[LOG] 2026-09-18 22:10 — QA: полные прогоны в одноразовых контейнерах (весь репозиторий смонтирован, аргументы из CI, `CI=true`): inventory 1017 passed (было 941), char-attrs 408 passed / 2 skipped / 1 xpassed (было 351), battle 535 passed (было 516), locations 1204 passed (было 1195), skills 218 passed (было 213), dungeon 132 passed (было 126), party 47 passed (было 39), battle-pass 112 passed (было 107), autobattle 78 passed. Падений нет, exit 0 везде; продакшн-код не менялся
[LOG] 2026-09-18 22:15 — QA: баги не найдены — все четыре QA-задачи прошли без правок продакшн-кода. Наблюдение для Reviewer (не баг): `POST /attributes/{id}/recover` принимает dict без схемы и реагирует только на ключи `*_recovery`; payload вида `{"health": 10}` молча ничего не делает (все реальные вызывающие ключи передают правильно). Задачи #11–#14 завершены
[LOG] 2026-09-18 22:20 — Reviewer: начал проверку, статус → REVIEW; поднял полные прогоны pytest по девяти затронутым сервисам и tsc/build фронтенда в одноразовых контейнерах
[LOG] 2026-09-18 22:30 — Reviewer: автопроверки зелёные — `py_compile` на 35 файлах, pytest: inventory 1017, battle 535, char-attrs 408/2 skip/1 xpass, locations 1204, skills 218, dungeon 132, party 47, battle-pass 112, autobattle 78; `npx tsc --noEmit` и `npm run build` exit 0; `docker compose config` и merged prod валидны, `INTERNAL_SERVICE_TOKEN` виден у 10 сервисов в prod, включая party и battle-pass (блокер §2.5 закрыт)
[LOG] 2026-09-18 22:35 — Reviewer: чек-лист §3.1.2 проверен по коду — `slot_type` передаётся во всех 11 местах, три собранных руками словаря выкидывают `damage` для рук, без `slot_type` остался только payload еды (так и задумано). Утечки урона оружия в `character_attributes.damage` нет ни одним путём: у слота оружия ключ `damage` вообще не может появиться
[LOG] 2026-09-18 22:40 — Reviewer: миграция 023 проверена на локальной БД (это дамп прода: 697 персонажей, 750 строк атрибутов, 12 надетых оружий) — арифметика совпадает с `compute_item_damage` побитово (оба поля `Integer`, расхождения float/int невозможны), `alembic_version_inventory = 023`, цепочка 022 → 023 без ветвлений, отрицательных `damage` нет, кламп и предупреждения на месте
[LOG] 2026-09-18 22:45 — Reviewer: пересобрал `api-gateway` (в контейнере был старый запечённый конфиг) и пересоздал party/battle-pass под новую переменную. Nginx-слой: шесть изменяющих путей → 403, `GET /attributes/{id}`, `/rest-status` и `GET /attributes/{id}/passive_experience` → 200 (приём `limit_except GET HEAD` работает, наивный `return 403` сломал бы третий), `/attributes/internal/*` и `/attributes/admin/*` без изменений, `/inventory/internal/characters/{id}/items` → 403, анонимный `POST /inventory/{id}/items` → 401
[LOG] 2026-09-18 22:50 — Reviewer: живая проверка урона на «Арлекино» (706) с Экскалибуром — профиль 45 / 35 / 35 на 1440 и 360 без горизонтальной прокрутки, реальная атака в бою пишет `base: 45.0` (не 55), после заточки `effective_damage` 10 → 11 и бой пишет 46.0, при этом `character_attributes.damage` остался 5. Сломанное оружие: `effective_damage` 0, бой 35.0, в профиле бейдж «Оружие сломано». Три цикла надеть/снять — дрейфа нет
[LOG] 2026-09-18 22:55 — Reviewer: геймплей после закрытия эндпоинтов — сбор (150→149) и отмена сбора (возврат до 150), подземелье (вход + переход, 150→145), опыт за пост (пассивный 1→5, седьмой вызывающий работает), опыт отряда и предмет боевого пропуска через настоящие клиентские функции в живых контейнерах, заточка надетого оружия. Все internal-клиенты семи сервисов вызваны вживую — везде 200, токен читается из env в момент вызова
[LOG] 2026-09-18 23:00 — Reviewer: админская выдача — админ 200, модератор 200 (у роли `moderator` право `items:update` реально есть, кнопка не пропадает), `editor` и обычный игрок 403 «Недостаточно прав» с русским текстом в модалке и во вкладке инвентаря
[LOG] 2026-09-18 23:05 — Reviewer: обнаружены предсуществующие баги того же класса, добавлены в ISSUES.md — `POST /attributes/cumulative_stats/increment` открыт снаружи (анонимно 200, накручивает кумулятивные статы и ОТКРЫВАЕТ перки), `POST /attributes/` и `POST /inventory/` доступны анонимно; плюс запись про синхронизацию опыта character-service оказалась неверной (токен там как раз отправляется). В скоуп FEAT-167 не входят
[LOG] 2026-09-18 23:10 — Reviewer: тестовые данные убраны (посты, сессия сбора, сессия подземелья, бои 206–208 + логи Mongo, временный пользователь, выданные камни и зелья), персонаж 706 возвращён в исходное состояние, коммитов не делал
[LOG] 2026-09-18 23:15 — Reviewer: проверка завершена, результат FAIL — по коду замечаний нет ни одного, блокируют только две устаревшие записи в `docs/ISSUES.md` (незакрытая задача #15): не удалена запись про дыру в выдаче предметов, которую эта фича закрыла, и не актуализирована запись про fallback `INTERNAL_SERVICE_TOKEN`. Третье замечание косметическое (лишнее поле в `damage.ts:40`)
[LOG] 2026-09-18 23:10 — PM: ревью #1 FAIL только по докам; убрал закрытую запись про выдачу предметов из ISSUES.md, дополнил запись про INTERNAL_SERVICE_TOKEN, убрал неиспользуемое поле в damage.ts (tsc OK)
[LOG] 2026-09-18 23:40 — Reviewer: начал ревью #2. Три заявленные правки подтверждены: устаревшая запись про выдачу предметов удалена без висячих ссылок, запись про `INTERNAL_SERVICE_TOKEN` расширена до 10 сервисов и требует задать настоящее значение в прод `.env` тем же пушем, лишнее поле из `damage.ts` убрано (заодно поправил комментарий «две поля» → «одно»). `npx tsc --noEmit` и `npm run build` — exit 0, `package-lock.json` чист
[LOG] 2026-09-18 23:45 — Reviewer: правок оказалось больше, чем «одно поле типа» — приехали задачи #17/#18 (мои находки из ревью #1): закрыты `POST /attributes/cumulative_stats/increment`, `POST /attributes/` и `POST /inventory/`, заголовок добавлен четырём вызывающим кумулятивной статистики и трём вызовам character-service (файла `character-service/app/crud.py` раньше в фиче вообще не было). Ни новых тестов, ни строк в таблице задач — поэтому перепрогнал затронутые сервисы вместо того, чтобы поверить в «только документация»
[LOG] 2026-09-18 23:50 — Reviewer: **pytest battle-service красный — 10 упавших** (было 535 passed). Причина найдена запуском одного теста: заглушки `_capture_post` в `test_cumulative_stats.py` не принимают новый `headers=`, вызов падает с `TypeError`, продакшн-код глушит его `except Exception`, и тесты видят ноль отправок. Заодно это показывает, что путь кумулятивной статистики молча проглатывает сбои
[LOG] 2026-09-18 23:55 — Reviewer: остальные сервисы зелёные — character-service 953 (прогнан впервые за всю фичу), char-attrs 408, inventory 1017, skills 219, locations 1206. Счётчики char-attrs и inventory не изменились, то есть на тот момент три новых закрытых роута не были покрыты ни одним тестом
[LOG] 2026-09-19 00:00 — Reviewer: живая проверка #17/#18 — анонимно все три роута теперь 401 (раньше `cumulative_stats` отдавал 200 «Stats updated»); все четыре вызывающих статистики и все три вызова создания персонажа/моба из character-service проходят авторизацию и создают строки. Создание персонажа не сломано
[LOG] 2026-09-19 00:05 — Reviewer: ISSUES.md приведён в соответствие — две мои записи из ревью #1 закрыты этим же пушем и помечены DONE, вместо них заведена реально открытая часть (восемь `/internal/*` роутов char-attrs и inventory держатся только на nginx), запись про character-service сложена в существующую MEDIUM-запись как уточнение, всё разложено по секциям по приоритету
[LOG] 2026-09-19 00:20 — Reviewer: QA правила тесты параллельно с проверкой — дождался, пока правки устоятся, и перепрогнал начисто. Всё зелёное: **battle-service 537** (было 10 упавших), char-attrs 425 (+17), character-service 960 (+7, новый `test_internal_headers.py`), inventory 1029 (+12), skills 219, locations 1206. Задачи #17–#20 появились в таблице
[LOG] 2026-09-19 00:25 — Reviewer: пересобрал `api-gateway` ещё раз под задачу #19 — три точных `location = …` блока режут анонимные `POST /attributes/cumulative_stats/increment`, `POST /attributes/` и `POST /inventory/` (403), при этом `GET /attributes/{id}`, `/rest-status`, `/passive_experience`, `/inventory/{id}/items`, `/inventory/{id}/equipment` и `/inventory/items/{id}` отвечают 200 — регрессий нет, блоки в dev и prod побайтово одинаковые
[LOG] 2026-09-19 00:30 — Reviewer: ревью #2 завершено, результат **PASS**. Открытых замечаний нет; все три поднятых по ходу пункта закрыты до конца ревью. Главное условие на деплой остаётся организационным: настоящее значение `INTERNAL_SERVICE_TOKEN` обязано попасть в прод `.env` тем же пушем — после #17–#20 на нём держится единственный прикладной слой примерно для 15 маршрутов
[LOG] 2026-09-19 00:20 — Backend Dev: начал задачи #17/#18 (две предсуществующие дыры того же класса, найденные Reviewer'ом в ревью #1 и одобренные пользователем к закрытию тем же пушем). Перед правкой прогнал полный свип вызывающих по всему репозиторию: `POST /attributes/cumulative_stats/increment` — ровно четыре вызывающих (battle `main.py:486`, locations `main.py:42` на семь call-сайтов через один хелпер, inventory `main.py:759`, skills `main.py:524`), `POST /attributes/` и `POST /inventory/` — ровно один вызывающий, character-service (`crud.send_attributes_request` — создание персонажа хард-фейлом и админский NPC, `crud._sync_send_attributes_request` — спавн моба, `crud.send_inventory_request` — стартовый набор). Ни одного вызова с фронта, ни одного из скриптов/сидов, ни одного in-process теста на эти роуты
[LOG] 2026-09-19 00:25 — Backend Dev: задача #17 завершена — `Depends(verify_internal_token)` на `POST /attributes/cumulative_stats/increment` и `POST /attributes/`, заголовок добавлен четырём вызывающим статистики и трём вызовам character-service. В `character-service/app/crud.py` добавлен ленивый `_internal_token_headers()` по образцу `locations_client.py` (читает константу в момент вызова, чтобы тесты могли её подменить). GET-роуты не тронуты, `/attributes/{id}/cumulative_stats` остался открытым
[LOG] 2026-09-19 00:28 — Backend Dev: задача #18 завершена — `Depends(verify_internal_token)` на `POST /inventory/`; единственный вызывающий (стартовый набор) шлёт заголовок. Остальные ~40 роутов `/inventory/` не тронуты
[LOG] 2026-09-19 00:35 — Backend Dev: задача #19 (nginx) — три **точных** блока `location = …` с `limit_except GET HEAD` в обоих конфигах. Именно точное совпадение, а не префикс и не регулярка: под `/attributes/` и `/inventory/` живут десятки боевых роутов, неверный шаблон уронил бы игру. Оба конфига прошли `nginx -t` (прод — с самоподписанным сертификатом-заглушкой, иначе падает только на отсутствующем Let's Encrypt)
[LOG] 2026-09-19 00:45 — Backend Dev: маршрутизация проверена на одноразовом gateway-контейнере в той же docker-сети (работающий api-gateway не трогал): три POST'а → 403, при этом `GET /attributes/{id}`, `/rest-status`, `/{id}/cumulative_stats`, `/{id}/passive_experience`, `/inventory/items`, `/inventory/{id}/equipment` → 200, а `POST /inventory/{id}/items`, `/inventory/trade/propose`, `/attributes/{id}/upgrade`, `/attributes/{id}/recalculate` → 401 (то есть доходят до сервиса). Блоки FEAT-167 (шесть изменяющих + оба `/internal/`) по-прежнему 403
[LOG] 2026-09-19 00:55 — Backend Dev: задача #20 — тесты. Матрица авторизации на каждый роут (без заголовка / неверный / пустое значение / player JWT → 401; пустой `INTERNAL_SERVICE_TOKEN` → 503 и никогда 200; верный → реально работает и реально пишет), каждый отказ сверяется с БД, плюс свипы по таблице роутов. Для `POST /attributes/` отдельный кейс «авторизация раньше валидации схемы» — исходный симптом дыры был именно 422. Caller-side проверки заголовка на **настоящих** клиентских функциях всех семи call-сайтов, включая три в character-service, у которого покрытия этих вызовов не было вообще
[LOG] 2026-09-19 00:58 — Backend Dev: починил замечание #1 ревью #2 — заглушки `_capture_post` в `battle-service/app/tests/test_cumulative_stats.py` не принимали новый `headers=`; добавлен `**kwargs`, ассерты не менялись. Изолировал причину так же, как Reviewer: падение глушится продакшн-кодом `except Exception`, поэтому тесты видели ноль отправок
[LOG] 2026-09-19 01:10 — Backend Dev: проверки. `py_compile` по всем изменённым файлам. Полный pytest по шести затронутым сервисам в Docker (весь репозиторий смонтирован, аргументы из ci.yml, `CI=true`): character-attributes-service 425 passed / 2 skipped / 1 xpassed, inventory-service 1029 passed, battle-service 537 passed, locations-service 1206 passed, skills-service 219 passed, character-service 960 passed / 1 skipped. Красный battle-service из ревью #2 закрыт, счётчики char-attrs, inventory и character-service выросли — замечание #2 ревью #2 тоже закрыто
[LOG] 2026-09-19 01:15 — Backend Dev: живая проверка на поднятом стеке. Анонимно (в обход gateway, прямо в сервис) все три роута → 401 «Недействительный internal token», с неверным токеном → 401; с верным токеном → 200 у всех трёх. Все три клиентские функции character-service вызваны в живом контейнере — 200, строки атрибутов, инвентаря и слотов экипировки создаются, то есть создание персонажа и спавн моба не сломаны. Тестовые строки (`character_id` 999997–999999) удалены из БД
[LOG] 2026-09-19 01:20 — Backend Dev: задачи #17–#20 завершены, изменено 17 файлов. Замечание #3 ревью #2 закрыто — в §4 добавлены строки #17/#18 (+#19 nginx, +#20 QA), в §3 добавлен §3.10 с решениями, свипом вызывающих и обоснованием точных nginx-блоков. `docs/ISSUES.md` уже приведён в порядок Reviewer'ом в ревью #2 — обе записи помечены DONE, я их не дублировал; актуализированы `docs/services/character-attributes-service.md`, `inventory-service.md`, `battle-service.md`, `locations-service.md`, `skills-service.md`, `character-service.md`. Коммитов не делал
[LOG] 2026-09-19 01:30 — PM: ревью #2 PASS, задачи #17-#20 закрыты, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Урон оружия считается один раз.** Модификатор урона оружия больше не вливается в характеристику: он считается по надетому предмету (шаблон + заточка и камни этого оружия, 0 у сломанного) и отдаётся как `effective_damage` в уже существующем ответе экипировки. Формула боя: главная характеристика класса + `damage` + `effective_damage` оружия слота.
- **Три значения урона в профиле:** «Осн. урон», «Доп. урон», «Без оружия» — руки теперь действительно различаются, безоружные навыки не получают урон оружия. У сломанного оружия — пометка «Оружие сломано». Цифры профиля совпадают с боем (проверено вживую: 45 / 35 / 35, база боя 45 вместо 55).
- **Разовая миграция** `023_weapon_damage_backfill` вычитает урон надетого оружия из `character_attributes.damage` (кламп на 0 с предупреждением в логе, рабочий откат).
- **Закрыты дыры:** выдача предметов (`POST /inventory/{cid}/items` → `items:update`, новый внутренний маршрут для сервисов), шесть изменяющих эндпоинтов характеристик, накрутка накопительной статистики с бесплатной выдачей перков (`cumulative_stats/increment`), анонимные `POST /attributes/` и `POST /inventory/`. Везде fail-closed внутренний токен, русские тексты ошибок, плюс запрет в nginx вторым слоем (только для изменяющих методов — чтение осталось рабочим).
- **Обновлены все вызывающие сервисы** (battle, battle-pass, dungeon, locations, skills, party, inventory, character), `INTERNAL_SERVICE_TOKEN` добавлен party-service и battle-pass-service в оба compose-файла.
- Тесты: ~200 новых, все сервисы зелёные (инвентарь 1029, характеристики 425, персонажи 960, бои 537, локации 1206, навыки 219, подземелья 132, отряды 47, боевой пропуск 112, автобой 78).

### Что изменилось от первоначального плана
- Вместо «урон один раз через характеристику» по решению пользователя сделаны три отдельных значения урона.
- Добавлена пометка «Оружие сломано».
- По ходу ревью найдены и закрыты ещё две предсуществующие дыры (задачи #17–#20).
- Найден седьмой вызывающий, которого не было в плане: начисление опыта за пост в locations-service (без токена опыт молча пропадал бы).

### Оставшиеся риски / follow-up задачи
- **Перед пушем на прод обязательно задать настоящий `INTERNAL_SERVICE_TOKEN` в `.env`** — после этой задачи на нём держится защита ~15 маршрутов, а в репозитории лежит публично известный fallback.
- Перед деплоем снять бэкап базы: в задаче есть миграция, которая правит данные.
- В ISSUES.md остаётся HIGH: 8 маршрутов `/internal/*` у характеристик и инвентаря по-прежнему держатся только на nginx.
- MEDIUM: `compute_derived_stats` затирает накопленные бонусы `damage` при пересчёте (предсуществующее).
