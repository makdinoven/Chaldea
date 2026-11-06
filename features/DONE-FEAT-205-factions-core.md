# FEAT-205: Фракции — этап 1 (ядро)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-05 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Лорные фракции (ордена, гильдии, храмы, тёмные гильдии), которые создаёт админ. Игрок может состоять в любом числе фракций, если сама фракция не ограничивает. Внутри фракции — своя шкала очков и лестница званий с условиями и наградами. Вступление завязано на уже существующие системы: региональная репутация (FEAT-197), слава/дурная слава (FEAT-199), уровень, класс, раса, квесты. Это первый из трёх этапов:
- **Этап 1 (эта фича)** — ядро: фракции, вступление, очки, звания, враждебность, тайные фракции, исключение, квесты фракции, вкладка в профиле, каталог.
- Этап 2 (потом, НЕ делаем) — экономика фракций: казна в общей книге (ledger), условные NPC-участники, шаблоны, тик 6 ч, пожертвования, награды марками из казны (с долгом при пустой казне), интендант.
- Этап 3 (потом, НЕ делаем) — закрытые локации/данжи фракций, пассивки на высоких званиях, очки за убийство врагов фракции, членство как преступление в крае.

Игровые гильдии/кланы, создаваемые игроками, — ОТДЕЛЬНАЯ будущая система, к фракциям не относится.

### Бизнес-правила
**Фракция (создаёт админ):** название, описание, герб (картинка), штаб (локация, опционально), руководитель(и) — NPC (опционально, для квестов), флаги и ограничения:
- лимит участников (пусто = без лимита);
- «только по приглашению» — вступление через заявку, которую одобряет админ в админке;
- «тайная» — членство видит только сам игрок (и админ); в чужом профиле фракция не показывается, в каталоге фракция видна, но список участников/их число — нет (решит архитектор, не раскрывать членов);
- активна / скрыта из каталога (черновик).

**Условия вступления** — набор блоков, все должны выполняться (И):
- репутация в крае X не ниже уровня Y (уровни FEAT-197);
- слава не меньше N / дурная слава не меньше N (FEAT-199); при желании также «не больше N» (например, паладинам дурная слава ≤ 20);
- уровень персонажа от N;
- класс / подкласс / раса из списка;
- выполнен квест X (вступительное испытание);
- «не состоит во фракции X».
Игрок видит условия в каталоге с отметкой выполнено/не выполнено.

**Враждебность:** админ задаёт пары враждебных фракций.
- Очки, полученные у фракции, отнимают 50 % от полученного у каждой враждебной ей фракции, где игрок состоит (процент — настройка, по умолчанию 50).
- Пару можно отметить «непримиримой» — состоять в обеих нельзя (вступление во вторую запрещено).

**Очки фракции:** у каждого участника — шкала очков в этой фракции (не ниже 0). Источники в этапе 1: награда квеста «очки фракции X» (может быть и отрицательной) + ручное начисление админом. Очки копятся только пока игрок состоит во фракции.

**Звания:** упорядоченная лестница внутри фракции (первое звание даётся при вступлении). Условия звания (все И): очки фракции от N, уровень от N, выполнен квест X (квест выдаёт руководитель фракции). Повышение **автоматическое**, как только все условия выполнены (проверка при начислении очков, при завершении квеста, при повышении уровня; за раз можно пройти несколько званий). Понижения званий нет (только исключение).

**Награды за звание** (выдаются один раз при первом получении звания — повторное вступление не даёт их снова): предметы (с количеством), опыт, титул (строка, отображается в профиле во вкладке), дом, участок под дом. Награды марками — этап 2 (из казны фракции), в этапе 1 НЕ делаем. Что такое «дом» и «участок» в награде — определяет аналитик по текущей системе домов (вариант PM: дом = готовый дом/право на дом в заданной локации; участок = право построить дом в заданной локации). Если механика не ложится — вопрос вернуть PM.

**Выход и исключение:**
- Выход добровольный в любой момент. Повторное вступление в ту же фракцию — не раньше чем через 7 дней, 50 % очков сгорает (звание пересчитывается от оставшихся очков при повторном вступлении; награды за уже полученные звания второй раз не выдаются).
- Если участник перестал соответствовать условиям вступления (например, выросла дурная слава, стал состоять в непримиримой фракции не может по правилам, упала репутация в крае) — предупреждение (уведомление + отметка во вкладке), через 3 дня, если не исправил, — исключение (с теми же последствиями, что выход). Проверка — периодическая (например, в существующем фоновом проходе) и/или при изменении репутации/славы.
- Админ может исключить вручную.
- Все сроки — настройки (по умолчанию 3 дня / 7 дней / 50 %).

**Квесты фракции:** в редакторе квеста — принадлежность фракции; квест доступен только участникам этой фракции и (опционально) начиная с звания N; новый тип награды «очки фракции X». Вступительный квест (условие вступления) должен быть доступен НЕ-участникам.

### UX / Пользовательский сценарий
1. Игрок открывает каталог фракций — видит активные фракции, описание, герб, условия вступления с отметками, кнопку «Вступить» (или «Подать заявку» для фракций по приглашению).
2. Вступает — получает первое звание (+ его награды), запись в журнале, уведомление.
3. В профиле персонажа — вкладка «Фракции»: все фракции игрока, звание, титул, очки, прогресс до следующего звания (условия с отметками), предупреждение об исключении (с обратным отсчётом), кнопка «Покинуть» (с подтверждением, где сказано про 7 дней и сгорание 50 %), журнал фракций (вступил, звание, очки, предупреждение, исключён, вышел). В чужом профиле — только нетайные фракции и звания, без журнала.
4. Выполняет квесты фракции → очки → автоматическое повышение → награда + уведомление.
5. Админ: раздел «Фракции» — CRUD фракций, званий (с условиями и наградами), условий вступления, враждебных пар, заявки на вступление (одобрить/отклонить), участники (начислить очки, исключить), настройки сроков.

### Edge Cases
- Лимит участников достигнут → «Во фракции нет мест».
- Заявка во фракцию по приглашению, пока заявка висит — повторная заявка запрещена; при одобрении условия перепроверяются.
- Игрок вышел и вернулся — награды за звания не дублируются.
- Очки после штрафа враждебности не уходят ниже 0.
- Удаление фракции админом / удаление звания с участниками — решит архитектор (вариант: только деактивация).
- NPC не могут состоять во фракциях.
- Все сроки показывать обратным отсчётом («осталось 2 д 5 ч»), не «до ЧЧ:ММ» (требование пользователя).

### Вопросы к пользователю (если есть)
- [x] Фракции только лорные (админ), игровые гильдии — отдельно → Да
- [x] Шкала очков фракции → Да
- [x] Враждебность и тайные фракции → Сразу, в этапе 1
- [x] Источник очков → квесты фракции (+ в этапе 2 пополнение казны)
- [x] Повышение → автоматическое; условие может быть «выполнить квест у руководителя»
- [x] Награды за звания → + опыт, дома, участки под дома
- [x] «По приглашению» → заявка, одобряет админ
- [x] Враждебность → −50 % от полученных очков у враждебной; «непримиримые» пары — нельзя состоять в обеих
- [x] Сроки → 3 дня до исключения, 7 дней до повторного вступления, 50 % очков сгорает
- [x] Марки за звание при пустой казне → в долг (этап 2)

**Решения по вопросам аналитика (пользователь: «Как предлагаешь», 2026-11-05):**
- [x] Слава/дурная слава в условиях → по СТУПЕНЯМ (tier), не по числам — скрытые числа не раскрываются.
- [x] Титул за звание → настоящий титул из существующей системы Титулов (`titles` / `character_titles` / `grant_title`), не текстовая строка.
- [x] Дом / участок за звание → ПРАВО (ваучер) на бесплатный готовый дом (`kind=ready`) / пустой участок (`kind=empty`) в заданной локации; игрок сам выбирает любое свободное место нужного типа там. Нет свободного места → право ждёт. Сезонный налог такие дома платят как обычные.
- [x] Квесты «только для членов» → у не-членов показываются закрытыми с причиной «Только для членов фракции X» (и «Нужно звание …»); квесты ТАЙНЫХ фракций у не-членов скрыты полностью.
- [x] Очки фракции в награде квеста → список пар (фракция, ±очки).
- [x] Квесты-условия вступления/званий → только НЕповторяемые (редактор не даёт выбрать повторяемый, бэкенд валидирует).
- [x] Каталог фракций → ссылка в шапке рядом с разделами мира + кнопка «Все фракции» во вкладке профиля.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

All paths are relative to `services/`. Line numbers are as of commit 34e0d0d.

### Affected Services

| Service | Type of changes | Files |
|---------|-----------------|-------|
| character-service (owner) | new tables + migration 045, faction core/crud/api modules, notify, scheduler hook, level-up hook, public/private endpoints, internal endpoints for locations-service | `app/models.py`, new `app/faction_*.py` (following `reputation_*`/`shadow_*` split), `app/schemas.py`, `app/main.py` (include_router ~4758-4762), `app/econ_scheduler.py`, `app/crud.py` (`check_and_update_level`), `app/alembic/versions/045_*.py` |
| locations-service | quest columns (faction, min rank, faction points reward), member-only gate on quest list/accept, post-commit call «faction points / quest completed» | `app/models.py:492` (Quest), `app/schemas.py:1271-1330`, `app/crud.py:5167-5450`, `app/main.py:3367-3712`, new read module like `app/fame_read.py`, migration `058_*` |
| user-service | RBAC permissions `factions:*` (migration 0034) + test section | `alembic/versions/0034_*.py`, `tests/test_rbac_permissions.py` |
| inventory-service | no changes expected (existing internal grant endpoint) | `app/main.py:644` |
| photo-service | only if a dedicated emblem endpoint is chosen (mirror model) | `main.py` |
| frontend | profile tab «Фракции», public passport block, catalog page, admin section, quest editor fields, NPC quest modal lock reason | see §2 / §7 below |

### 1. Where factions live — existing reputation/law/renown stack (character-service)

**Pattern of the service:** sync SQLAlchemy, Pydantic v1, Alembic head `044_guard_patrols` (`app/alembic/versions/044_guard_patrols.py:21`; chain 038 reputation → 039 law → 040 shadow_renown → 041..044). Each subsystem = `*_core.py` (pure rules, constants, dataclasses) + `*_crud.py` (DB) + `*_api.py` (router, prefix `/characters`, included in `main.py:4757-4761` **before** the main router so static `/admin/...`, `/internal/...` paths win over `/{character_id}/...`) + `*_notify.py`. API wrappers `_read/_write` (`shadow_api.py:58-85`) commit once, map `IntegrityError`→409, `SQLAlchemyError`→500 with Russian messages.

**Tables (models.py):**
- `character_reputation` (1112): value per (character, region), `decay_at`; UNIQUE(character_id, region_id); FK→characters ON DELETE CASCADE.
- `reputation_log` (1131): journal, `event_key` + UNIQUE(event_key, region_id) = idempotency; `tier_before/after`, `actor_user_id`, `reason`.
- `reputation_settings` (1160, single row id=1), `reputation_tiers` (1174, 8 fixed codes `reputation_core.TIER_CODES` = outlaw..legend, `reputation_core.py:24`, `min_value` editable), `reputation_actions`, `reputation_npc_role_weights`.
- `character_renown` (1521): `fame`, `infamy` per character (no row = 0/0); `renown_tiers` (1533, 5 codes per scale: `shadow_core.py:39-40` FAME_CODES nameless..legend, INFAMY_CODES none..dreaded); `renown_log` (1550, UNIQUE event_key).
- law: `character_wanted`, `law_settings` (with `pass_last_run_at` claim column), `law_log` etc. (1210-1466).

**How tiers/levels are read:**
- Region reputation: `reputation_crud.effective(db, cid, region_id)` (179) applies lazy decay; `tier_of` (192); `gate_failure(db, cid, region_id, min_code)` (198) returns «Нужна репутация: X» or None; `rc.meets(value, code, tiers)`; `rc.tier_rank`.
- Fame/infamy: `renown_crud.renown_of(db, cid) -> (fame, infamy)` (55), `fame_tier_of` (64), `sc.renown_tier_for`.
- **Visibility rule (important):** players never see fame/infamy numbers. `renown_crud.player_renown` (188) returns tier names only; infamy is shown to the owner only as «слухи» tier (`rumors`); public passport shows only fame tier name (`main.py:2710`). Region reputation player view: `reputation_crud.player_view` (592).
- Level/class/race: `characters.level`, `id_class`, `id_race`, `id_subrace`, `is_npc` (models.py:38-112).

**Reputation journal tab:** player endpoints `GET /characters/{id}/reputation` and `/reputation/history` (`reputation_api.py:209-232`) guarded by `visibility.require_private_access` (owner, or admin/moderator with `characters:read`; `visibility.py:32-75`). History = paginated `reputation_log` with human text (`reputation_crud._history_text` 614, `player_history` 633). Separate generic `character_logs` (`models.py:397`, `crud.create_character_log` 3628) feeds the «Логи персонажа» tab.

**Periodic pass:** `econ_scheduler.py` — daemon thread started on startup (`main.py:4767-4772`) when env `ECON_TICK_ENABLED` (default `1` in both compose files: `docker-compose.yml:407`, `docker-compose.prod.yml:158`), every 60 s; never under pytest. `run_scheduled_once` (≈line 80) runs `run_reputation_decay` → `run_law_pass` → econ tick (only if DB toggle on). Each sub-pass has **its own throttle** via a conditional UPDATE claim on a settings row (`reputation_decay.claim_run` 32, hourly; `law_pass.claim_run` 49, 55 s) and processes in batches, every item its own transaction, failures logged and skipped. A faction pass («expel if conditions no longer met», «expire warnings», «7-day cooldown» is lazy) fits as a 4th `run_faction_pass(factory)` wrapper in the same function, with its own claim column on a `faction_settings` row — exactly the decay/law pattern. The econ 6h tick is economy-only and should NOT host it.

**Change hooks (for «check on reputation/fame change»):** reputation changes go through `reputation_crud.apply_reputation` (368) from many callers (quests, guild, kills, caravans, crimes, admin, decay); fame/infamy through `renown_crud.add_renown/add_fame/add_infamy` (113-158). Both are deep inside other transactions; hooking expulsion there means touching many flows. The periodic pass alone satisfies «warning → 3 days → expel» (precision = pass interval).

**Admin APIs + RBAC pattern:** admin routes use `Depends(require_permission("module:action"))` from `auth_http.py` (e.g. `shadow_api.py:93-160`; titles `main.py:1256-1370` use `titles:read/create/update/delete`). Permissions are inserted by **user-service** Alembic migrations (head `0033`, `user-service/alembic/versions/0033_reputation_permissions.py`: idempotent SELECT-then-INSERT, moderator role_id=3 grants, admin automatic). Per CLAUDE.md §10.13 a new module needs its own seed section in `user-service/tests/test_rbac_permissions.py` (see reputation section 1442-1510: `_seed_*_permissions`, fixture, class `Test*Permissions` that also reads the migration file). New module name proposal: `factions` (`read`, `manage`, `settings`?) — Architect decides.

**Notifications:** `law_notify.py` / `reputation_notify.py` — sync pika publish to `general_notifications` after commit (category `system`/`progress`, `ws_type`), best-effort, swallowed errors; from async routes wrapped in `run_in_threadpool`. Tests stub `_send` (`tests/conftest.py:244` autouse `stub_law_notify_send`; `reputation_world.py` replaces `reputation_notify._send`). Countdown text helper: `activity_lock.format_remaining` (`activity_lock.py:100`, «3 д 4 ч»), `law_notify.remaining`.

### 2. Character profile tabs (frontend)

- Tab registry: `frontend/app-chaldea/src/components/ProfilePage/ProfileTabs.tsx:6-19` (static `TABS` array, «Репутация» = key `reputation`). Switch in `ProfilePage.tsx:68-115`; ReputationTab wrapped in `ErrorBoundary`.
- Component: `components/ProfilePage/ReputationTab/ReputationTab.tsx` (uses `PanelShell`, `shared/*` EmptyState/ErrorState/LoadingState/SectionHeader/ProfileCard, `CommonComponents/RemainingText`, `api/errors.apiErrorMessage`). API modules: `api/reputation.ts`, `api/renown.ts`, `api/law.ts` (plain axios functions + TS interfaces).
- **Own vs foreign:** `ProfilePage` (`/profile`, App.tsx:410) shows ONLY the current user's active character (`state.user.character`). There is no foreign ProfilePage. Foreign characters are seen via the **CharacterPassport** (`components/CommonComponents/CharacterPassport/*`, fed by `GET /characters/{id}/public`, `api/charactersPublic.ts`; used from `/characters/list` and `/user-profile/:userId`). Precedent for public data: FEAT-199 added `fame_tier_name` to `/public` (`character-service/app/main.py:2685-2712`, passport `CharacterPassport.tsx:361`). So «в чужом профиле — нетайные фракции и звания» = a new block in the passport + either extra fields in `/public` or a public `GET /characters/{id}/factions/public`.
- Admin character card: `components/Admin/CharactersPage/AdminCharacterDetailPage.tsx:22-40,157` (tabs incl. `reputation`, permission-gated) — natural place for admin «начислить очки / исключить» per character.

### 3. Quests (owned by locations-service, async SQLAlchemy)

- Model `Quest` (`locations-service/app/models.py:492-514`): `npc_id` (quest giver = NPC character), `quest_type` ('standard' / 'repeatable'), `min_level`, `reward_currency`, `reward_exp`, `reward_items` JSON `[{item_id, quantity}]`, `reputation_reward`, `min_reputation_tier` (FEAT-197), `min_fame_tier`, `fame_reward` (FEAT-199, migration `056_quest_fame.py` — plain columns, no ENUM). `QuestObjective` (517), `CharacterQuest` (531, UNIQUE(character_id, quest_id), status active/completed), progress (549).
- Schemas `QuestCreate/Update/Read` (`schemas.py:1271-1330`) with validators for tier codes.
- Admin CRUD `POST/GET/PUT/DELETE /locations/admin/quests` (`main.py:3367-3436`) guarded by `get_admin_user` (admin+moderator), not a permission. Editor UI: `frontend/.../components/AdminNpcsPage/QuestEditor.tsx` (807 lines; fame fields at 42-45, 233-234, 361-389, 563-590 — follow it for faction fields).
- **Gating:** list `crud.get_available_quests_for_npc` (5318-5402): filters `min_level` in SQL, then gated quests stay in the list with `locked_reason` (reputation then fame, via `reputation_read.quest_gates` / `fame_read.quest_fame_gates`). Accept `crud.accept_quest` (5405-5450) re-checks and raises 403 (`reputation_read.GATE_STATUS`). Player UI: `components/pages/LocationPage/NpcQuestsModal.tsx` renders `locked_reason`. Cross-service read pattern = `app/fame_read.py` (raw parameterised SQL on character-service tables in the shared DB, read only when some quest needs it). A `faction_read.py` reading the membership table is the matching pattern for «only members from rank N». Note: «members only» quests probably should be **hidden** for non-members rather than shown locked (to keep secret factions secret) — Architect/PM decide.
- **Completion and payout** `POST /locations/quests/{id}/complete` (`main.py:3575-3712`): conditional status flip (`crud.complete_quest_record`), gold via ledger (`pay_character`, idem key `quest_reward:cq:{cq_id}`), XP via `crud.add_experience` (5830: direct UPDATE of `character_attributes`, **no level-up check**), commit; then after commit: items via inventory internal endpoint (not idempotent, no retry), reputation `_apply_quest_reputation` (3487) and fame `_apply_quest_fame` (3534) — HTTP POST to character-service internal endpoints with idempotency key, one retry, never fail the completion. Then `_auto_progress_quest(... "complete_quest" ...)` for chains.
  - Character-service side of fame: `POST /characters/internal/fame/apply` (`shadow_api.py:162-188`, `verify_internal_token`, `FameApplyIn`, log UNIQUE event_key → duplicate-safe).
  - **Faction points reward + rank re-check hook** fits as a third post-commit call `_apply_quest_faction(...)` → new `POST /characters/internal/factions/quest-completed` (or `/points/apply`) with key `faction:quest:cq:{cq_id}`; character-service applies points (with hostile-faction penalty), re-checks ranks (quest-condition ranks too), grants rank rewards, notifies. Must be sent even when points = 0 if the quest is a rank/entry condition (so re-check happens) — or the rank check reads `character_quests` lazily.
- **«Quest X completed» condition:** `character_quests.status='completed'` (precedent: internal `GET /locations/quests/internal/check-completed`, `main.py:3744`). character-service can read `character_quests` by raw SQL (shared DB; it already reads Locations/Regions this way). Caveat: for `repeatable` quests `accept_quest` **deletes** the completed row on re-accept (`crud.py:5447-5453`) → a repeatable quest as a condition can "un-complete". Recommend: condition quests must be non-repeatable, or record completions in a faction-owned table.
- Entry-trial quest = an ordinary (non-faction-gated) quest referenced by the faction's entry condition; nothing special needed except not marking it members-only.
- Rank-N quest from the leader: just a quest with `npc_id` = leader NPC + faction + min rank. No enforcement that the giver is the leader is needed.

### 4. Rank rewards

- **Items:** `POST /inventory/internal/characters/{cid}/items {item_id, quantity}` (`inventory-service/app/main.py:644`, `X-Internal-Token`), same call as quest rewards. Not idempotent → reward grant must be recorded (e.g. `faction_rank_rewards` row / `rewards_granted_at`) before/after the call with a retry strategy; character-service currently has `crud._internal_token_headers()` and `settings.INVENTORY_SERVICE_URL` (`config.py:9`, base `.../inventory/`).
- **XP:** precedent `crud._grant_title_xp` (2971-3027): direct SQL UPDATE of `character_attributes.passive_experience`, then `check_and_update_level` (1372). XP-book multiplier is resolved by the caller before the transaction (FEAT-168 #6 rule — never HTTP inside an open transaction). `add_rewards_to_character` (2554) is the other path.
- **Level-up hook:** `crud.check_and_update_level` (1372-1412) is the single place where `level` grows (callers: `add_rewards` battle/dungeon/battle-pass `crud.py:2647`, title XP 3027, guild orders `economy_api.py:1062`, lazy re-check in `_build_full_profile`/check-level route `main.py:2086`, admin level change `main.py:870`). It commits and calls `notify_level_changed`. Quest XP from locations-service does NOT level up immediately — level-up happens lazily on the next full_profile load. Precedent of «on level-up re-evaluate»: `main.py:2091-2120` re-evaluates titles and perks when `character.level > old_level`. A rank re-check can hook inside `check_and_update_level`'s `leveled_up` branch (covers every caller) — beware of recursion (rank reward XP → level-up → rank re-check) and that it runs inside callers' flows (some async); notifications must stay post-commit.
- **Title:** an existing **Titles** system exists: `titles` (models.py:161: name UNIQUE, rarity, icon, conditions JSON, reward XP), `character_titles` (186), `characters.current_title_id`; `crud.grant_title` (3105, idempotent, logs «Получен титул»), profile tab «Титулы», admin `/admin/titles` (`titles:*` perms). The brief says «титул (строка, отображается во вкладке)». Two options: (a) a free string per rank shown only in the Factions tab; (b) rank reward references a `titles.id_title` granted via `grant_title` (then it appears in «Титулы» and can be set as the active title). → open question.
- **Houses (locations-service `app/houses.py`, docs `docs/services/locations-service.md` «Дома игроков» FEAT-180 stages 1-7):**
  - `house_plots` (models.py:1073): admin-created plot in a location (region, map point, `price`, grid plan, `kind` = `ready` (sold with template rooms `house_plot_rooms`) or `empty` (land only; owner builds rooms paying `house_build_costs` gold + materials + hours), `min_reputation_tier` gate).
  - `houses` (1151): **one house per plot** (`plot_id` UNIQUE), `owner_character_id`, `status` active/frozen/seized, seasonal tax (`tax_paid_through`, `house_settings`), heir, resale.
  - Getting a house today: only `POST /locations/houses/plots/{id}/buy {character_id}` (`houses.py:734-785`): must stand in the plot's location, not locked/in battle, reputation gate, plot free; creates `House` + copies template rooms + charges `plot.price` via ledger (`house_purchase`). No per-character house limit. No internal/admin "grant house" endpoint exists. Market resale `buy_listed_house` (2283).
  - **There is no separate "plot ownership" entity**: buying an `empty` plot already means "a house with no rooms" (a `houses` row). So concretely: reward «дом» = free ownership of a `ready` plot; reward «участок» = free ownership of an `empty` plot. Both produce a `houses` row, subject to the seasonal tax and seizure.
  - The core problem: a plot is a single unique object, but a rank reward is given to every member who reaches the rank. Options for Architect/PM: **(A)** rank reward = a "deed/right" (voucher) row `faction_house_rights(character, location_id, kind ready|empty)`; the player claims it on any free plot of that kind in that location (purchase with price 0), plots optionally reserved for a faction (`house_plots.faction_id`, `min_faction_rank`); **(B)** reward points to a concrete plot id — works only for unique ranks (e.g. the head), otherwise fails when taken; **(C)** auto-create a plot from a template per member (admin loses control of map placement). PM's variant (дом = готовый дом/право на дом в локации; участок = право построить в локации) maps cleanly to (A). Needs a new locations-service internal endpoint («claim free house») and probably a «Права на дом» UI on the house market/plot page. Tax on rewarded houses: should it be waived? → open question.

### 5. Notifications
Use a new `faction_notify.py` cloned from `reputation_notify.py` (`build_payloads`/`_send`/`publish_*`, category `progress` for rank-up/points, `system` for warning/expulsion), published after commit. Frontend shows `general_notifications` generically; no ws_type-specific handling needed unless the tab should refresh live.

### 6. Entry-condition data
- Level: `characters.level`; class `characters.id_class` (table `classes`); race `id_race` (`races`), subrace `id_subrace` (`subraces`); NPC flag `is_npc`.
- **Subclass:** not a column on characters. It is the `subclass_key` string of the chosen `subclass_choice` node: SQL `character_tree_progress JOIN tree_nodes WHERE node_type='subclass_choice'` (precedent `inventory-service/app/equipment_rules.py:124-145`); the subclass registry is hardcoded in `skills-service/app/subclasses.py` (`SubclassDef key/class_id/name`), public list `GET /skills/subclasses?class_id=` (`skills-service/app/main.py:418`), internal `GET /skills/internal/characters/{id}/subclass` (437).
- Region list/names: `reputation_crud.region_infos` (152) reads locations tables.

### 7. Admin panel + images (frontend)
- Admin hub: `components/Admin/AdminPage.tsx:14-51` — array of `{label, path, description, module}` filtered by `hasModuleAccess` (`utils/permissions.ts`); add «Фракции» with `module: 'factions'`.
- Route: `components/App/App.tsx:196-200` pattern `<ProtectedRoute requiredPermission="reputation:read">`. Admin page structure precedent: `components/Admin/ReputationPage/*` (tabbed page, `useReputationRefs.ts`, `ReputationTierSelect.tsx` — reusable for the region-tier condition editor; `useShadowRefs.useFameTierOptions` for fame tiers).
- Catalog page for players: new route (e.g. `/factions`); entry points: header user dropdown (`CommonComponents/Header/Header.tsx:56-64`), HomePage tiles (`HomePage.tsx:20-80`), or `CharactersHubPage`. PM/designer choice.
- Countdown UI: `CommonComponents/RemainingText.tsx`.
- **Emblem upload:** two existing patterns: (a) dedicated photo-service endpoint per entity with a mirror model and `require_permission("photos:upload")` (e.g. `/photo/change_origin_emblem`, `photo-service/main.py:911-943`) — requires a photo-service mirror model for the factions table; (b) generic upload `POST /photo/upload_episode_image` (photo-service `main.py:1101`) returning a URL that the owning service stores, frontend `components/pages/EpisodesPage/ImageField.tsx` (already reused by house plots `HousesAdminPage/PlotFormModal.tsx:239`; locations-service accepts only https URLs from `episode_images/`). (b) needs no photo-service change.
- Quest editor fields: `AdminNpcsPage/QuestEditor.tsx` (faction select, min rank select, faction points reward list).

### 8. Alembic heads and tests
- Heads verified in repo: character-service `044_guard_patrols`; locations-service `057_country_prison_district` (`down_revision 056_quest_fame`); inventory-service `035_item_stealth_modifier`; user-service `0033`. Next: character `045_*`, locations `058_*`, user `0034`. Memory note: revision ids ≤ 32 chars; FK indexes on MySQL; no ENUM churn.
- character-service tests: SQLite in-memory (`tests/conftest.py:27`), world fixtures as non-test modules — `tests/reputation_world.py`, `law_world.py`, `shadow_world.py` (raw DDL for foreign tables read by raw SQL, e.g. `SHADOW_DDL`; notifiers replaced by recorders). A `faction_world.py` should add DDL for `character_quests`, `character_tree_progress`/`tree_nodes`, `character_attributes`, `Regions` reads. Autouse stubs `stub_notify_level_changed`, `stub_law_notify_send` (conftest 231-250). locations-service: `tests/test_quest_fame.py`, `tests/reputation_sqlite.py`, `test_quest_complete_real_session.py` are the templates. Tests run inside containers (`docker compose exec <svc> pytest`); local containers lack `pytest-asyncio` — locations-service async tests use the existing sync-wrapper style there. CI runs pytest per service.
- Character deletion: new tables with FK → `characters.id` ON DELETE CASCADE (as `character_reputation`), see `tests/test_delete_character_cleanup.py`.

### Cross-Service Dependencies (new)
- locations-service → character-service: `POST /characters/internal/factions/...` after quest completion (X-Internal-Token, idempotency key per cq).
- locations-service reads faction membership tables (raw SQL, shared DB) for quest gating.
- character-service → inventory-service: item rewards (existing endpoint).
- character-service → locations-service: new internal «grant house right / claim» (if option A) — new endpoint.
- character-service reads `character_quests`, `character_tree_progress`/`tree_nodes`, `Regions` (raw SQL).
- notification-service via RabbitMQ `general_notifications` (existing).

### DB Changes (indicative — Architect designs)
- character-service 045: factions, faction ranks (+conditions, +rewards), entry conditions, hostile pairs, members (points, rank, joined_at, left_at/cooldown, warning_at), applications, faction log (UNIQUE event_key), rewards-granted ledger, faction settings (3 d / 7 d / 50 % / hostile %, pass claim column).
- locations-service 058: `quests.faction_id`, `quests.min_faction_rank_id`, faction points reward (int or JSON list); optionally `house_plots.faction_id/min_rank`.
- user-service 0034: `factions:*` permissions.

### Risks
- Secret factions leak via quest lists / catalog member counts / public endpoint / NPC quest lock reasons → hide members-only quests from non-members; never return members for secret factions.
- Non-idempotent item grants (inventory) → persist reward state per (character, rank) before calling; retry in the pass.
- Recursion/loop: rank reward XP → level-up → rank re-check → … → guard by «already granted» rows.
- `check_and_update_level` runs from sync and async paths and commits internally → the hook must be non-fatal, post-commit, and must not do HTTP on the event loop thread (see `notify_level_changed` threading note, crud.py:1324-1350).
- Quest XP does not level up immediately (lazy) → «rank on level-up» is delayed until the next profile load; acceptable or fix via the pass.
- Repeatable quests delete completion rows → condition quests must be non-repeatable.
- Hostile penalty applied only to factions where the player is a member; clamp at 0.
- Prod deploy: CI timeouts; scheduler runs in every character-service process — claim-row throttle mandatory.

### Open Questions for PM (to the user)
1. **Fame/infamy thresholds are hidden numbers.** Players see only tier names (fame) and «слухи» (infamy); the catalog must show conditions with ✓/✗. Should conditions be by **tier** (e.g. «слава не ниже "Известный"», «слухи не выше "Шепчутся"») like quests' `min_fame_tier`, or by raw numbers (which would reveal the hidden scale)?
2. **Title reward:** free text shown only in the Factions tab, or a real title from the existing «Титулы» system (appears in the Титулы tab, can be made the active title, can carry XP)?
3. **House/plot reward:** confirm option A — a "right" to a free house (ready) / free empty plot in a given location, claimed by the player on a free plot there (optionally plots reserved for the faction). Should rewarded houses pay the seasonal house tax like bought ones? What if no free plot exists?
4. Members-only faction quests for non-members: hide completely, or show locked («Только для членов фракции …»)? (For secret factions — hide.)
5. Quest faction-points reward: one faction per quest, or a list of (faction, points) pairs (e.g. +20 to one, −10 to a rival)?
6. Rank condition «quest X» and entry condition «quest X»: OK to require such quests to be non-repeatable?
7. Catalog entry point: header menu, home page tile, or the «Персонажи» hub?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Open questions for PM

No blocking questions — all product decisions are covered by §1. The defaults below are product-visible but were chosen
by the Architect; PM may confirm them with the user in the final report (changing any of them is a settings/one-line
change, not a redesign):

1. **Manual admin points do NOT trigger the hostility penalty** (admin adjusts exactly what they type; the penalty
   applies only to quest rewards). Negative quest rewards never trigger a penalty either (penalty = share of a *gain*).
2. **A house/plot voucher waives only the price.** All other plot rules still apply (stand in the location, not in
   battle/activity lock, plot free, the plot's own `min_reputation_tier` gate). Rewarded houses pay seasonal tax.
3. **Rank-reward XP ignores the XP book** (a rank reward is a fixed prize, not earned XP), `xp_multiplier=None`.
4. **Faction quests accepted while a member can still be completed after leaving**; their faction points are simply
   not credited (points accrue only to active members). Gold/XP/items of the quest are paid as usual.
5. **Rejected application → re-apply cooldown** = setting `reapply_cooldown_hours` (default 24).
6. **Hiding a faction (`is_active = false`)** only removes it from the catalog and blocks joins/applications; existing
   members keep it (tab shows «Фракция скрыта из каталога» only to admins; players just see it normally), points and
   ranks keep working. Hard delete is allowed only for a faction that never had members/applications.

### 3.1 Overview and ownership

| Concern | Owner | Notes |
|---|---|---|
| Factions, ranks, conditions, hostility, members, applications, journal, settings, reward grants/outbox | **character-service** (sync SQLAlchemy, migration `045_factions_core`) | new modules `faction_core.py` (pure rules), `faction_crud.py` (DB + flows), `faction_rewards.py` (outbox delivery), `faction_pass.py` (periodic pass), `faction_notify.py`, `faction_api.py` (router, prefix `/characters`, included in `main.py` next to `shadow_api`/`law_api` **before** the main router) |
| Quest fields (faction, min rank, faction-points list), quest gating, post-completion call, house vouchers + claim | **locations-service** (async, migration `058_quest_faction_vouchers`) | new `app/faction_read.py` (raw parameterised SQL on character-service tables, pattern `fame_read.py`), voucher code inside `app/houses.py` |
| Permissions `factions:*` | **user-service** (migration `0034`) | + explicit seed section in `tests/test_rbac_permissions.py` (CLAUDE.md §10.13) |
| Item rewards | inventory-service | **no change** — existing `POST /inventory/internal/characters/{cid}/items` |
| Emblem upload | photo-service | **no change** — generic `POST /photo/upload_episode_image` + `ImageField.tsx`; character-service stores the https URL |

No Nginx / Docker / env changes: all new paths are under existing `/characters/` and `/locations/` prefixes, the
scheduler already runs in character-service, internal token and `INVENTORY_SERVICE_URL` already exist. character-service
needs the locations base URL for the voucher call — reuse the existing `locations_client.py` / `settings` (Backend Dev
verifies; if no locations URL setting exists, add `LOCATIONS_SERVICE_URL` with a default in `config.py`, no compose change
needed since defaults point at the compose service name).

### 3.2 Data model — character-service migration `045_factions_core`

All FKs to `characters.id` are `ON DELETE CASCADE` (character deletion cleanup). FK columns get explicit indexes
(MySQL gotcha). No MySQL ENUMs — status/type columns are `VARCHAR` validated in code. Revision id ≤ 32 chars.

```sql
CREATE TABLE factions (
  id INT PK AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  description TEXT NULL,
  emblem_url VARCHAR(512) NULL,           -- https only, validated
  hq_location_id BIGINT NULL,             -- Locations.id (no FK, cross-service; validated by raw SELECT)
  leader_npc_ids JSON NULL,               -- [character_id of NPCs], validated is_npc=1, max 5
  member_limit INT NULL,                  -- NULL = unlimited, 1..100000
  is_invite_only BOOL NOT NULL DEFAULT 0,
  is_secret BOOL NOT NULL DEFAULT 0,
  is_active BOOL NOT NULL DEFAULT 0,      -- 0 = draft / hidden from catalog
  sort_order INT NOT NULL DEFAULT 0,
  created_at, updated_at
);

CREATE TABLE faction_ranks (
  id INT PK, faction_id INT NOT NULL FK→factions ON DELETE CASCADE (indexed),
  name VARCHAR(100) NOT NULL, description TEXT NULL,
  sort_order INT NOT NULL,                -- ladder position; lowest = entry rank (no conditions)
  min_points INT NOT NULL DEFAULT 0,      -- 0..10_000_000
  min_level INT NOT NULL DEFAULT 0,       -- 0..1000
  required_quest_id BIGINT NULL,          -- non-repeatable quest (validated)
  reward_xp INT NOT NULL DEFAULT 0,       -- 0..10_000_000 (passive XP)
  reward_title_id INT NULL,               -- titles.id_title (validated exists)
  reward_items JSON NULL,                 -- [{item_id, quantity}] max 10, qty 1..999
  reward_house_location_id BIGINT NULL,   -- voucher kind=ready in this location
  reward_plot_location_id BIGINT NULL,    -- voucher kind=empty in this location
  created_at
  INDEX (faction_id, sort_order)
);

CREATE TABLE faction_conditions (        -- entry conditions, AND-ed
  id INT PK, faction_id INT NOT NULL FK CASCADE (indexed),
  cond_type VARCHAR(30) NOT NULL,         -- see §3.4
  params JSON NOT NULL,
  sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE faction_hostilities (
  id INT PK,
  faction_a_id INT NOT NULL FK CASCADE, faction_b_id INT NOT NULL FK CASCADE,  -- stored with a_id < b_id
  irreconcilable BOOL NOT NULL DEFAULT 0,
  created_at,
  UNIQUE (faction_a_id, faction_b_id), INDEX (faction_b_id)
);

CREATE TABLE faction_members (           -- one row per (character, faction), survives leave/expel
  id INT PK,
  character_id INT NOT NULL FK→characters CASCADE,
  faction_id INT NOT NULL FK→factions CASCADE,
  status VARCHAR(10) NOT NULL,            -- active | left | expelled
  points INT NOT NULL DEFAULT 0,          -- >= 0 always
  rank_id INT NULL FK→faction_ranks ON DELETE SET NULL (indexed),
  joined_at DATETIME NOT NULL, left_at DATETIME NULL,
  rejoin_after DATETIME NULL,             -- cooldown end (left/expelled)
  warning_at DATETIME NULL,               -- set when entry conditions stopped being met
  warning_reasons JSON NULL,              -- [str] texts of unmet conditions (player-safe)
  UNIQUE (character_id, faction_id),
  INDEX (faction_id, status), INDEX (status, warning_at)
);

CREATE TABLE faction_applications (
  id INT PK,
  character_id INT NOT NULL FK CASCADE (indexed), faction_id INT NOT NULL FK CASCADE (indexed),
  status VARCHAR(10) NOT NULL,            -- pending | approved | rejected | cancelled
  message VARCHAR(500) NULL,
  pending_key VARCHAR(40) NULL UNIQUE,    -- "{character_id}:{faction_id}" while pending, NULL after decision
  reject_reason VARCHAR(500) NULL,
  decided_by_user_id INT NULL, decided_at DATETIME NULL, created_at
  INDEX (status, created_at)
);

CREATE TABLE faction_rank_grants (       -- rank reward ledger: once per (character, rank), forever
  id INT PK,
  character_id INT NOT NULL FK CASCADE, faction_id INT NOT NULL FK CASCADE (indexed),
  rank_id INT NOT NULL FK→faction_ranks (indexed; RESTRICT — ranks with grants cannot be deleted),
  granted_at DATETIME NOT NULL,
  UNIQUE (character_id, rank_id)
);

CREATE TABLE faction_reward_deliveries ( -- outbox, one row per reward component
  id INT PK,
  grant_id INT NOT NULL FK→faction_rank_grants CASCADE (indexed),
  character_id INT NOT NULL (indexed),
  kind VARCHAR(15) NOT NULL,              -- xp | title | item | voucher
  payload JSON NOT NULL,                  -- {xp} | {title_id} | {item_id, quantity} | {location_id, kind}
  status VARCHAR(10) NOT NULL,            -- pending | sending | done | failed
  attempts INT NOT NULL DEFAULT 0,
  next_attempt_at DATETIME NOT NULL,
  last_error VARCHAR(255) NULL, updated_at
  INDEX (status, next_attempt_at)
);

CREATE TABLE faction_log (               -- player journal + audit
  id BIGINT PK,
  character_id INT NOT NULL FK CASCADE, faction_id INT NOT NULL FK CASCADE,
  event_type VARCHAR(30) NOT NULL,        -- joined | left | expelled | rank_up | points | hostile_penalty |
                                          -- warning | warning_cleared | applied | application_approved |
                                          -- application_rejected | admin_points | reward_failed
  points_delta INT NULL, points_after INT NULL, rank_id INT NULL,
  event_key VARCHAR(120) NULL,            -- idempotency
  reason VARCHAR(500) NULL, actor_user_id INT NULL, created_at
  UNIQUE (event_key, faction_id), INDEX (character_id, id)
);

CREATE TABLE faction_settings (          -- single row id=1, seeded by the migration
  id INT PK,
  warning_days INT NOT NULL DEFAULT 3,            -- 0..60
  rejoin_cooldown_days INT NOT NULL DEFAULT 7,    -- 0..365
  leave_burn_pct INT NOT NULL DEFAULT 50,         -- 0..100
  hostile_penalty_pct INT NOT NULL DEFAULT 50,    -- 0..100
  reapply_cooldown_hours INT NOT NULL DEFAULT 24, -- 0..720
  pass_last_run_at DATETIME NULL                  -- throttle claim
);
```

Rollback: `downgrade()` drops the 9 tables in reverse FK order. Data loss on rollback is acceptable (pre-beta).

### 3.3 Data model — locations-service migration `058_quest_faction_vouchers`

```sql
ALTER TABLE quests
  ADD faction_id INT NULL,                 -- faction quest: members only
  ADD min_faction_rank_id INT NULL,        -- must belong to faction_id; requires faction_id
  ADD faction_points_rewards JSON NULL,    -- [{faction_id, points}] max 5, points -10000..10000, != 0, unique faction ids
  ADD INDEX ix_quests_faction (faction_id);

CREATE TABLE house_vouchers (
  id BIGINT PK,
  character_id INT NOT NULL (indexed),     -- no FK across services (pattern of quests.npc_id); cleaned by character deletion? see below
  location_id BIGINT NOT NULL FK→Locations ON DELETE CASCADE (indexed),
  kind VARCHAR(10) NOT NULL,               -- ready | empty  (matches house_plots.kind)
  source_key VARCHAR(120) NOT NULL UNIQUE, -- "faction:grant:{grant_id}:voucher:{kind}" — idempotency
  source_text VARCHAR(255) NULL,           -- «Награда за звание «Рыцарь» (Орден Зари)»
  status VARCHAR(10) NOT NULL DEFAULT 'unclaimed',  -- unclaimed | claimed
  claimed_house_id BIGINT NULL, claimed_at DATETIME NULL, created_at
);
```

No FK from `quests` to character-service tables (cross-service; validated at write time via `faction_read`). Orphaned
`house_vouchers` of deleted characters are harmless (claim requires owning the character); Backend Dev adds them to
the existing character-deletion cleanup in locations-service if such a cleanup hook exists, otherwise noted in ISSUES.

### 3.4 Rules (faction_core.py — pure functions, no DB)

**Entry condition types** (`cond_type` → `params`), validated by Pydantic in `schemas.FactionConditionIn` (v1 root
validator dispatching on `type`; unknown keys rejected; max 20 conditions per faction):

| type | params | met when | player-facing text (never numbers for fame/infamy) |
|---|---|---|---|
| `region_reputation` | `{region_id, min_tier}` (tier code from `reputation_core.TIER_CODES`) | `reputation_crud.effective` meets tier | «Репутация в крае «X»: не ниже «Y»» |
| `fame` | `{min_tier?, max_tier?}` (FAME_CODES, at least one, min ≤ max) | fame tier rank in range | «Слава: не ниже «Y»» / «не выше «Z»» |
| `infamy` | `{min_tier?, max_tier?}` (INFAMY_CODES) | infamy tier rank in range | «Слухи: не ниже/не выше «Y»» (tier names = the ones the owner already sees as «слухи») |
| `level` | `{min_level}` 1..1000 | `characters.level >= N` | «Уровень от N» |
| `class` | `{class_ids: [..]}` 1..20 | `id_class in` | «Класс: Воин или Маг» |
| `subclass` | `{subclass_keys: [..]}` 1..30, `^[a-z0-9_]{1,50}$` | chosen subclass node key in list (raw SQL `character_tree_progress JOIN tree_nodes node_type='subclass_choice'`) | «Подкласс: …» (names resolved by frontend from `/skills/subclasses`; backend returns keys + text with keys fallback) |
| `race` | `{race_ids: [..], subrace_ids?: [..]}` | race in list (and subrace in list if given) | «Раса: …» |
| `quest` | `{quest_id}` — must exist and be **non-repeatable** (raw `SELECT quest_type FROM quests`) | `character_quests.status='completed'` | «Выполнено задание «Title»» |
| `not_in_faction` | `{faction_id}` (≠ own) | no active membership there | «Не состоит во фракции «X»» — for a **secret** X the text is shown only if X itself is not secret; secret X → text «Не состоит в некоторых тайных организациях» |

Irreconcilable hostility is an implicit extra condition for both factions of the pair («Не состоит во фракции «X»»,
same secrecy rule). Each evaluation returns `[{type, text, met}]`; `evaluate_entry(...)` is used by catalog, join,
application approval, and the periodic pass.

**Ranks.** Ladder ordered by `sort_order`. The lowest rank is the entry rank: its conditions are ignored (UI hides the
fields). `compute_rank(member, ladder, level, completed_quests)` = walk upward from the current rank (or from the entry
rank on (re)join) while the next rank's conditions (points ≥ min_points, level ≥ min_level, quest completed if set) are
all met; stop at the first unmet. Ranks never go down while a member (no demotion). On rejoin the walk starts from the
entry rank with the remaining points → the rank is recomputed (may be lower than before).

**Points.** `apply_points(member, delta)` clamps at 0. Points change only for `status=active`. Hostility penalty on a
quest gain `G > 0` in faction A: for every faction B hostile to A (any pair, irreconcilable included) where the character
is active: `penalty = floor(G * hostile_penalty_pct / 100)`; B.points = max(0, B.points − penalty); logged as
`hostile_penalty` in B with the actual amount taken.

**Leave / expel.** `status → left|expelled`, `left_at = now`, `rejoin_after = now + rejoin_cooldown_days`,
`points = floor(points * (100 − leave_burn_pct) / 100)`, `warning_at/reasons = NULL`, rank kept in the row only for
history (rank shown as «бывш.»). Rejoin allowed when `now >= rejoin_after`; rejoin reuses the row (UNIQUE), status
active, rank recomputed. `faction_rank_grants` is never touched → rewards are not re-granted.

### 3.5 Flows (faction_crud.py)

All write flows run in one transaction (API `_write` wrapper commits once, same pattern as `shadow_api._read/_write`,
custom `FactionError(status, detail)`), return `notices` that the API publishes **after** commit via `faction_notify`,
and return `character_ids_to_deliver` for the outbox (§3.6).

- **join(character_id, faction_id)**: character exists, not NPC (403 «NPC не может вступать во фракции»); faction
  active (404 hidden); not invite-only (409 «Вступление только по заявке»); not already active (409); cooldown
  (409 «Повторное вступление возможно через 2 д 5 ч» via `activity_lock.format_remaining`); all entry conditions +
  irreconcilable (403 «Условия вступления не выполнены»); member limit — `SELECT ... FROM factions WHERE id FOR UPDATE`
  then count active (409 «Во фракции нет мест»). Insert/reactivate membership, compute rank (entry rank + possible
  climb), create grants + deliveries for every newly reached rank without a grant row, log `joined` + `rank_up`.
  A faction with no ranks: join still works with `rank_id = NULL` (UI shows «Без звания»).
- **apply(character_id, faction_id, message)**: invite-only faction, same pre-checks as join (conditions, limit,
  cooldown) so the player can't spam hopeless applications; `pending_key` UNIQUE → 409 «Заявка уже подана»;
  last rejection younger than `reapply_cooldown_hours` → 409 with countdown. Log `applied`.
- **cancel_application** (owner, pending only).
- **approve(application_id, admin)**: pending only (conditional UPDATE status pending→approved, `pending_key = NULL`;
  rowcount 0 → 409); re-check conditions/limit/cooldown/irreconcilable → on failure 409 with the unmet reasons, the
  application stays pending (admin may reject); then the join path (shared function). Notify.
- **reject(application_id, admin, reason)**: pending → rejected, notify.
- **leave(character_id, faction_id)** (owner) and **expel(membership_id, admin, reason)**: §3.4; log; notify on expel.
- **admin_points(membership_id, delta, reason)**: delta −100000..100000 (≠0), reason required 3..500; active only;
  no hostility penalty; rank re-check; log `admin_points` with `actor_user_id`.
- **quest_completed(character_id, quest_id, cq_id, rewards[])** (internal, idempotent): first
  `crud.check_and_update_level` from `character_attributes.passive_experience` (quest XP from locations-service is not
  levelled immediately — this closes the gap for faction members); then for each `{faction_id, points}`: skip if not
  active member; insert log with `event_key = faction:quest:cq:{cq_id}` (UNIQUE(event_key, faction_id) → duplicate =
  skip the whole entry, return `duplicate: true`); apply points; hostility penalty with key
  `faction:quest:cq:{cq_id}:hostile:{A}`; then rank re-check for **all** active memberships of the character (covers
  quest-condition ranks even when the quest gives no points).
- **recheck_ranks(character_id)**: used by points changes, quest completion, level-up hook; pure DB.

### 3.6 Rank rewards — grant ledger + outbox (faction_rewards.py)

Requirement: rewards exactly once per (character, rank), never re-granted after leave/rejoin, safe with a
non-idempotent inventory endpoint, no HTTP inside a transaction, no recursion.

1. **In the rank-up transaction** (DB-only): `INSERT faction_rank_grants (character, rank)` — UNIQUE guarantees one
   grant forever (IntegrityError on a race → that rank is already granted, skip). Same transaction inserts one
   `faction_reward_deliveries` row per component: `xp` (if reward_xp > 0), `title` (if reward_title_id), one `item` row
   per item entry, `voucher` rows for house (kind `ready`) / plot (kind `empty`). Status `pending`, `next_attempt_at = now`.
2. **After commit**, the caller triggers `faction_rewards.deliver_pending(character_id)`:
   - On an async route / event-loop thread → `run_in_threadpool` (API) or a daemon thread (level-up hook), same rule
     as `crud.notify_level_changed`. From sync code → inline.
   - Each row claimed by conditional `UPDATE ... SET status='sending', attempts=attempts+1 WHERE id=:id AND status='pending'`
     (rowcount 0 → someone else has it).
   - `xp`: one transaction: `UPDATE character_attributes SET passive_experience = passive_experience + :xp` +
     `UPDATE deliveries SET status='done'` → commit → `crud.check_and_update_level(...)` (post-commit). Exactly once.
     Implemented as a new small helper in crud (`add_passive_xp(db, cid, xp)` without the level check) — the
     `_grant_title_xp` pattern but without its mid-transaction commit.
   - `title`: `crud.grant_title(db, cid, title_id, xp_multiplier=None)` (idempotent by `character_titles`) + mark done,
     commit. Title XP (if the title has some) is granted by `grant_title` itself as today.
   - `item`: commit the `sending` claim **before** the HTTP call; `POST /inventory/internal/characters/{cid}/items`
     (timeout 5 s). 2xx → `done`. Connection refused / 4xx / 5xx response (definitely not applied — inventory's handler
     is a single transaction) → back to `pending`, `next_attempt_at = now + 2^attempts min`, failed after 5 attempts.
     **Timeout / read error (ambiguous)** → `failed` with `last_error='uncertain'` + log `reward_failed` — never
     auto-retried (no duplicates); admin sees it in the member view and can press «Повторить» (admin endpoint resets it
     to pending explicitly).
   - `voucher`: `POST /locations/houses/internal/vouchers` with `source_key = faction:grant:{grant_id}:voucher:{kind}`
     (idempotent by UNIQUE) → safe to retry on any error (exponential backoff, failed after 10 attempts).
   - Rows stuck in `sending` longer than 10 min: `xp`/`title`/`voucher` → back to pending (idempotent or transactional);
     `item` → `failed` uncertain (as above).
3. **Retries** are performed by the periodic pass (§3.8) for `pending` rows with `next_attempt_at <= now`.
4. **Recursion guard**: a `contextvars.ContextVar('faction_delivering')` is set inside `deliver_pending`. The level-up hook
   (§3.7) only *records* new grants when the flag is set and does not start another delivery; the outer
   `deliver_pending` loops "fetch pending → deliver" until nothing is pending (max 10 iterations, bounded anyway by the
   finite ladder + UNIQUE grants).
5. Rank-up notification lists the rewards («Новое звание «Рыцарь» во фракции «Орден Зари»: +500 опыта, титул «…»,
   предметы ×3, право на дом в «…»»). Delivery failures do not notify the player (admin view only).

### 3.7 Level-up hook

In `crud.check_and_update_level`, inside the `leveled_up` branch **after** `db.commit()` and `notify_level_changed`:
`faction_hooks.after_level_up(db, character_id)` wrapped in `try/except Exception: logger.exception` (never breaks the
caller). It:
- returns immediately if the character has no active memberships (one indexed SELECT — cheap for the many callers);
- runs `recheck_ranks` in the same session and commits (DB only — no HTTP on the event-loop thread);
- publishes notices and schedules `deliver_pending` with the threading rule of `notify_level_changed` (loop thread →
  daemon thread with its own `SessionLocal`; otherwise inline), **unless** the `faction_delivering` flag is set (then
  the outer delivery loop picks the new rows up).
Lazy levelling of quest XP is covered by `quest_completed` (§3.5) calling the level check first; other XP sources already
call `check_and_update_level`.

### 3.8 Periodic pass (faction_pass.py)

`econ_scheduler.run_scheduled_once` gets a 3rd independent call `run_faction_pass(factory)` (after `run_law_pass`, own
try/except, runs even when the economy toggle is off). Throttle `claim_run`: conditional
`UPDATE faction_settings SET pass_last_run_at = :now WHERE id=1 AND (pass_last_run_at IS NULL OR pass_last_run_at <= :cutoff)`,
`RUN_INTERVAL_SECONDS = 300`. Batches of 200, each item its own transaction, failures logged and skipped:
1. **Condition watch**: active members of active-or-hidden factions (keyset by membership id, round-robin cursor not
   needed — 200 per run ordered by `id > last` stored in memory is fine; simplest: all active members in batches per run,
   member count is small pre-beta). For each: evaluate entry conditions (incl. irreconcilable).
   - unmet & `warning_at IS NULL` → set `warning_at = now`, `warning_reasons` = unmet texts, log `warning`, notify
     «Вы перестали соответствовать условиям фракции «X»: … Исправьте в течение 3 д, иначе вас исключат».
   - met & `warning_at IS NOT NULL` → clear, log `warning_cleared`, notify.
   - unmet & `warning_at + warning_days <= now` → expel (same as §3.4, reason «Не соответствует условиям вступления»),
     log `expelled`, notify.
2. **Outbox retries** (§3.6) and stale `sending` rows.
Never runs under pytest automatically (scheduler rule); tests call `faction_pass.run_pass(factory, now=...)` directly.

### 3.9 Secrecy rules (enforced server-side)

- `GET /characters/{id}/factions/public` returns only memberships where `faction.is_secret = 0` and `status = active`.
- Catalog: secret factions are listed (if active) but `member_count` and `member_limit` are `null`; member lists are
  admin-only. A "no free places" error on join for a secret faction is acceptable (no counts revealed).
- `not_in_faction`/irreconcilable texts never name a secret faction to a player (§3.4).
- Journal/private tab only via `visibility.require_private_access` (owner or staff with `characters:read`).
- locations-service quest list: quests of a **secret** faction are removed from the list for non-members (not
  locked); accept → 404 «Задание не найдено» for non-members. Non-secret faction quests for non-members stay listed
  with `locked_reason = «Только для членов фракции «X»»`; members below `min_faction_rank` see «Нужно звание «Y» во
  фракции «X»». Accept re-checks → 403 with the same text.
- Notifications go only to the character's owner.

### 3.10 API contracts

Error format = FastAPI `{"detail": "<Russian text>"}`. All player endpoints require JWT
(`get_current_user_via_http`) and ownership of `character_id` (`_require_owner` pattern of `law_api.py`, 403 «Это не
ваш персонаж»), except the two public reads. Character IDs/faction IDs are path ints; bodies are Pydantic v1 with
`constr`/`conint` bounds as listed.

#### character-service — player

| Method & path | Auth | Request | Response (200) | Errors |
|---|---|---|---|---|
| `GET /characters/factions/catalog?character_id=` | JWT; `character_id` optional, must be own | — | `[{id, name, description, emblem_url, hq_location: {id,name}\|null, leaders: [{id,name,avatar}], is_invite_only, is_secret, member_count\|null, member_limit\|null, ranks: [{id,name,sort_order}], conditions: [{type,text,met\|null}], my: {status: none\|active\|left\|expelled\|pending, rank_name, rejoin_in_seconds\|null, application_id\|null, reapply_in_seconds\|null}\|null, can_join, join_block_reason\|null}]` — active factions only, ordered by sort_order | 403 not own |
| `GET /characters/factions/{faction_id}/public` | none | — | same item without `my`/`met` (for sharing a link) | 404 hidden/absent |
| `GET /characters/{cid}/factions` | private access | — | `{memberships: [{membership_id, faction: {id,name,emblem_url,is_secret}, status, points, rank: {id,name}\|null, rank_title: {id,name}\|null, next_rank: {id,name, conditions:[{type,text,met}]}\|null, warning: {reasons:[str], remaining_seconds}\|null, joined_at, rejoin_in_seconds\|null}], applications: [{id, faction_id, faction_name, status, created_at, reject_reason}]}` — active first, then left/expelled | 403/404 |
| `GET /characters/{cid}/factions/history?page=1&page_size=20` (≤50) | private access | — | `{items: [{id, faction_name, event_type, text, points_delta, points_after, created_at}], total, page, page_size}` | 403 |
| `GET /characters/{cid}/factions/public` | none | — | `[{faction_id, name, emblem_url, rank_name}]` non-secret active only | 404 character |
| `POST /characters/{cid}/factions/{fid}/join` | owner | — | `{membership_id, rank_name, notices_text}` | 403 NPC/conditions, 404, 409 invite-only/already/cooldown/limit/irreconcilable |
| `POST /characters/{cid}/factions/{fid}/apply` | owner | `{message: constr(max_length=500)\|null}` | `{application_id}` | 403, 404, 409 duplicate/cooldown/not invite-only |
| `DELETE /characters/{cid}/factions/applications/{aid}` | owner | — | `{ok: true}` | 404, 409 not pending |
| `POST /characters/{cid}/factions/{fid}/leave` | owner | — | `{points_after, rejoin_in_seconds}` | 404/409 not active |

#### character-service — admin (`/characters/admin/factions/...`, `require_permission`)

| Method & path | Permission | Notes |
|---|---|---|
| `GET /admin/factions` | factions:read | all factions incl. hidden, with member counts, rank/condition counts |
| `GET /admin/factions/{fid}` | factions:read | full: fields, ranks (all fields), conditions, hostilities |
| `POST /admin/factions` / `PUT /admin/factions/{fid}` | factions:edit | `FactionIn`: name 1..100 (unique → 409), description ≤ 5000, emblem_url https ≤ 512, hq_location_id exists, leader_npc_ids ≤ 5 existing NPCs, member_limit 1..100000\|null, flags, sort_order |
| `DELETE /admin/factions/{fid}` | factions:delete | 409 «Фракцию, в которой были участники, можно только скрыть» if any member/application/grant row |
| `POST /admin/factions/{fid}/ranks`, `PUT /admin/factions/ranks/{rid}`, `DELETE /admin/factions/ranks/{rid}` | factions:edit / factions:delete | `RankIn` with bounds §3.2; `required_quest_id` must be non-repeatable (422 «Условием может быть только неповторяемое задание»); title exists; items exist (raw `SELECT id FROM items`); voucher location ids exist. Delete → 409 if a member holds it or a grant exists |
| `PUT /admin/factions/{fid}/ranks/order` | factions:edit | `{rank_ids: [..]}` exact set of the faction's ranks → rewrites sort_order |
| `PUT /admin/factions/{fid}/conditions` | factions:edit | replaces the whole list `[{type, params}]` (≤ 20), validated per §3.4 |
| `GET/POST /admin/factions/hostilities`, `PUT/DELETE /admin/factions/hostilities/{hid}` | read / edit | `{faction_a_id, faction_b_id, irreconcilable}`; a≠b, normalised a<b; duplicate → 409. Creating an irreconcilable pair does not auto-expel — the periodic pass warns double members |
| `GET /admin/factions/applications?status=pending&faction_id=&page=` | factions:read | with character name/level/class, conditions with met flags |
| `POST /admin/factions/applications/{aid}/approve` / `.../reject {reason ≤ 500}` | factions:manage | §3.5 |
| `GET /admin/factions/{fid}/members?status=active&q=&page=` | factions:read | character id/name/level, points, rank, warning, joined_at |
| `GET /admin/factions/characters/{cid}` | factions:read | memberships + grants + deliveries (status, last_error) for the admin character card |
| `POST /admin/factions/members/{mid}/points` | factions:manage | `{delta: conint(-100000..100000) ≠ 0, reason: constr(3..500)}` |
| `POST /admin/factions/members/{mid}/expel` | factions:manage | `{reason: constr(3..500)}` |
| `POST /admin/factions/deliveries/{did}/retry` | factions:manage | only `failed` → pending; then deliver inline |
| `GET/PUT /admin/factions/settings` | factions:read / factions:settings | bounds §3.2 |

#### character-service — internal (`verify_internal_token`)

`POST /characters/internal/factions/quest-completed`
`{character_id:int, quest_id:int, cq_id:int, rewards:[{faction_id:int, points:conint(-10000..10000)}] (≤5)}` →
`{applied: [{faction_id, points_delta, points_after}], duplicate: bool, rank_ups: int}`. Idempotent (§3.5).
404 unknown character. Post-commit: notices + `deliver_pending` (via `run_in_threadpool`).

#### locations-service

| Method & path | Auth | Contract |
|---|---|---|
| Admin quest CRUD (existing `POST/PUT /locations/admin/quests`) | existing `get_admin_user` | + `faction_id\|null`, `min_faction_rank_id\|null` (requires faction_id, rank must belong to it), `faction_points_rewards: [{faction_id, points}]\|null` (≤5, points ≠ 0, −10000..10000, unique faction ids, factions exist). Validation via `faction_read` (422 Russian messages). Changing `quest_type` to `repeatable` or deleting a quest that is referenced by a faction entry condition or rank → 409 «Задание используется как условие фракции» |
| `QuestRead` / NPC quest list | existing | + the three fields; list gating per §3.9 |
| `POST /locations/houses/internal/vouchers` | `verify_internal_token` | `{character_id, location_id, kind: ready\|empty, source_key ≤120, source_text ≤255}` → `{voucher_id, duplicate}`; 404 unknown location |
| `GET /locations/houses/vouchers?character_id=` | JWT + own character | unclaimed + claimed vouchers `[{id, location: {id,name}, kind, source_text, status, claimed_house_id}]` |
| `POST /locations/houses/plots/{plot_id}/claim` | JWT + own character | `{character_id, voucher_id}`; same checks as `buy_house` (in location, not activity-locked, not in battle, plot reputation gate, plot free) + voucher own/unclaimed/`location_id == plot.location_id`/`kind == plot.kind` (409 «Право не подходит к этому участку»); voucher flip by conditional UPDATE `unclaimed → claimed` in the same transaction as the House (no ledger charge) → `{house_id}` |

Post-completion in `POST /locations/quests/{id}/complete`: new `_apply_quest_faction(...)` after `_apply_quest_fame`,
same style (post-commit, X-Internal-Token, timeout, one retry, never fails completion). Called when the quest has
`faction_points_rewards` **or** `faction_read.in_any_faction(character_id)` (on a read error → call anyway).

#### user-service migration `0034`

Permissions: `factions:read`, `factions:edit`, `factions:delete`, `factions:manage`, `factions:settings`.
Moderator (role_id=3): read, edit, manage. Editor: none. Admin: automatic. `downgrade` deletes the module rows
(pattern of 0033). `tests/test_rbac_permissions.py`: new section `_seed_faction_permissions` + fixture +
`TestFactionPermissions` (admin gets all 5, moderator gets 3 and not delete/settings, editor/user none, migration file
lists exactly these 5) — explicit seed per CLAUDE.md §10.13.

### 3.11 Security

- **Auth:** every player endpoint JWT + ownership; private tab via `visibility.require_private_access`; public endpoints
  return only non-secret data; admin endpoints `require_permission`; internal endpoints `verify_internal_token`.
- **Validation:** all bounds above; JSON params whitelisted per condition type; emblem only https; IDs referenced
  (locations, NPCs, titles, items, quests, ranks) verified to exist; free text length-capped; raw SQL parameterised only.
- **Rate limiting:** application-level — one pending application per (character, faction), re-apply cooldown, join
  cooldown, member limit row lock; join/leave are idempotent state transitions. No new Nginx zone (no expensive or
  amplifying player action; the existing gateway defaults apply).
- **Concurrency:** UNIQUE (character, faction), UNIQUE grants, UNIQUE event_key, conditional UPDATE claims for
  applications/deliveries/vouchers/pass throttle, `FOR UPDATE` on the faction row for the member limit.
- **No leaks:** hidden fame/infamy numbers never returned (tier names only), secret membership never exposed.
- Errors: Russian, no stack traces; 500 → generic «Не удалось выполнить действие».

### 3.12 Frontend

All new code TypeScript + Tailwind + design system classes (`gold-text`, `gray-bg`, `btn-blue`, `btn-line`,
`modal-overlay`, `modal-content`, …), no `React.FC`, mobile 360 px, every API error shown in Russian via
`apiErrorMessage` (toast or inline `ErrorState`), countdowns via `CommonComponents/RemainingText` («осталось 2 д 5 ч»).

- `src/api/factions.ts` — typed functions + interfaces for every character-service endpoint above; voucher functions in
  `src/api/houses.ts` (`getHouseVouchers`, `claimPlot`).
- **Profile tab «Фракции»** — `ProfileTabs.tsx` new key `factions`; `ProfilePage.tsx` switch (wrapped in
  `ErrorBoundary`); `components/ProfilePage/FactionsTab/FactionsTab.tsx` + subcomponents (`FactionMembershipCard`,
  `NextRankProgress`, `FactionWarningBanner`, `LeaveFactionDialog`, `FactionHistory`): membership cards (emblem, name,
  rank, rank title, points, next rank conditions with ✓/✗, warning banner with countdown, «Покинуть» with a confirm
  dialog that states the cooldown days and burn % from the response/settings text), pending applications with cancel,
  journal (paginated), button «Все фракции» → `/factions`. Former memberships shown collapsed with rejoin countdown.
- **Passport block** — `CharacterPassport` gets a «Фракции» section fed by `GET /characters/{id}/factions/public`
  (name + rank, emblem), hidden when empty; fetch failure shows a small inline error.
- **Catalog** — route `/factions` (`App.tsx`, auth-required like other player pages), `components/pages/FactionsPage/*`:
  grid of faction cards → expandable detail (description, leaders, HQ link, ranks, conditions with ✓/✗ for the active
  character, member count unless secret), button «Вступить» / «Подать заявку» (with optional message modal) /
  disabled reason / «Заявка на рассмотрении» / rejoin countdown. Header: `navData.ts` «ИГРОВОЙ МИР» → `{label:
  'Фракции', path: '/factions'}` (desktop mega-menu + mobile accordion share it).
- **Admin «Фракции»** — `AdminPage.tsx` entry `{label:'Фракции', path:'/admin/factions', module:'factions'}`; route with
  `ProtectedRoute requiredPermission="factions:read"`; `components/Admin/FactionsPage/*` tabs: «Фракции» (list +
  editor: fields, emblem via `ImageField`, HQ location select, leader NPC multi-select, flags), inside the editor —
  «Звания» (ordered list with up/down reorder, rank form: thresholds, quest select limited to non-repeatable quests,
  rewards: XP, title select, items list with quantity, house/plot location selects) and «Условия вступления» (typed
  block editor; reuse `ReputationTierSelect`, `useShadowRefs` fame tier options, infamy tier options, class/race lists,
  subclasses from `/skills/subclasses`); «Враждебность» (pairs + irreconcilable toggle); «Заявки» (pending first, approve /
  reject with reason, conditions with ✓/✗); «Участники» (per faction, search, points ± with reason, expel with reason);
  «Настройки» (5 numbers, `factions:settings`). Buttons hidden by `hasPermission`. `AdminCharacterDetailPage` tab
  «Фракции» (memberships, deliveries with «Повторить» for failed).
- **Quest editor** (`AdminNpcsPage/QuestEditor.tsx`): faction select, min rank select (ranks of the chosen faction),
  faction points reward list (faction + ±points, add/remove, ≤5). If this file's logic changes it is already `.tsx`.
- **House vouchers**: `MyHousesPage.tsx` section «Права на дом» (list, location, kind, source); `LocationPage/HousesSection.tsx`
  — on a free plot whose location/kind match an unclaimed voucher of the active character, a «Получить по праву»
  button next to «Купить» calling `claimPlot`. If these components still use SCSS for the touched parts, the touched
  component is migrated to Tailwind per CLAUDE.md §10.8.
- `NpcQuestsModal.tsx` needs no change (renders `locked_reason` generically) — verify only.

### 3.13 Data flow (quest → points → rank → rewards)

```
Player completes quest ─► locations POST /quests/{id}/complete
   commit (status, gold, XP) ─► items/rep/fame (existing) ─► _apply_quest_faction
        └─HTTP─► character POST /internal/factions/quest-completed (key faction:quest:cq:{id})
               tx: level check → points (+hostile penalty) → recheck ranks → grants + deliveries → commit
               post-commit: faction_notify (RabbitMQ general_notifications) ; deliver_pending (threadpool)
                    xp → tx(UPDATE character_attributes + done) → check_and_update_level → after_level_up (guarded)
                    title → grant_title
                    item → HTTP inventory internal (claim-before-call)
                    voucher → HTTP locations internal /houses/internal/vouchers (source_key)
Periodic (every 5 min, claim row): conditions watch → warning/clear/expel ; retry pending deliveries
```

### 3.14 Cross-service validation

- Existing contracts unchanged: quest fields are additive & nullable (old clients ignore them); `/public` untouched;
  `check_and_update_level` signature unchanged (hook is internal and non-fatal); inventory endpoint reused as-is;
  `buy_house` untouched (claim is a separate endpoint sharing helpers).
- Types: `faction_id`/`rank_id` INT in both services; `quest_id`/`cq_id` BIGINT on the locations side passed as int.
- Deploy order independent: locations `faction_read` only queries faction tables when needed and treats a missing table
  / SQL error as "no faction data" (log warning); character-service tolerates locations voucher endpoint 404 by retrying
  (backoff) until deployed.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Every agent: No commits, no pushes, no `git add`.** The user commits once at the end (push to main = prod deploy).
Backend devs run `python -m py_compile` on every modified file; frontend devs run `npx tsc --noEmit` and
`npm run build` inside the frontend container (no node on the host). Each agent writes a Russian `[LOG]` line in §6.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **character-service: schema + core rules + player/catalog flows.** Models and migration `045_factions_core` (§3.2, settings row seeded), `faction_core.py` (condition evaluation, rank walk, points/penalty/burn math, texts — §3.4), `faction_crud.py` player flows (catalog, private view, history, public view, join, apply, cancel, leave — §3.5), `faction_notify.py` (clone of `reputation_notify.py`), schemas, `faction_api.py` player routes (§3.10 player table) included in `main.py` before the main router. Grants + delivery rows are *created* here on rank-up (delivery itself is task 2 — expose a stub `faction_rewards.deliver_pending` hook point). No commits/pushes/git add. | Backend Developer | DONE | `services/character-service/app/models.py`, `app/alembic/versions/045_factions_core.py`, `app/faction_core.py`, `app/faction_crud.py`, `app/faction_notify.py`, `app/faction_api.py`, `app/schemas.py`, `app/main.py` | — | Migration upgrades/downgrades cleanly on MySQL (container); all player endpoints respond per §3.10; secret rules §3.9 hold; fame/infamy numbers never in responses; py_compile passes |
| 2 | **character-service: rewards outbox, quest hook, level-up hook, periodic pass.** `faction_rewards.py` (§3.6: claim, xp/title/item/voucher delivery, backoff, uncertain item handling, recursion ContextVar), `crud.add_passive_xp` helper, `faction_hooks.after_level_up` called from `crud.check_and_update_level` leveled_up branch (§3.7, non-fatal, threading rule), internal `POST /characters/internal/factions/quest-completed` (§3.5, idempotent), `faction_pass.py` + `econ_scheduler.run_faction_pass` (§3.8). Locations base URL setting if missing. No commits/pushes/git add. | Backend Developer | DONE | `app/faction_rewards.py`, `app/faction_hooks.py`, `app/faction_pass.py`, `app/faction_crud.py`, `app/faction_api.py`, `app/crud.py`, `app/econ_scheduler.py`, `app/config.py` (if needed) | 1 | Repeated quest-completed call with same cq_id changes nothing; a rank reached twice (leave/rejoin) never creates a second grant; item delivery never re-sent after an ambiguous error; level-up → rank re-check without recursion; pass warns/clears/expels on time and is throttled by the claim row; py_compile passes |
| 3 | **character-service: admin API.** All `/characters/admin/factions/...` routes of §3.10 with `require_permission` (factions:read/edit/delete/manage/settings): faction CRUD (delete guard), ranks CRUD + reorder (non-repeatable quest validation, reference existence checks), conditions replace, hostility CRUD, applications approve/reject (re-check), members list/points/expel, admin character view, delivery retry, settings. No commits/pushes/git add. | Backend Developer | DONE | `app/faction_crud.py` (or `app/faction_admin_crud.py`), `app/faction_api.py`, `app/schemas.py` | 1 (and 2 for retry/approve rank grants) | All admin routes reject callers without the permission (403); validation errors are 422/409 with Russian text; py_compile passes |
| 4 | **locations-service: quests + vouchers.** Migration `058_quest_faction_vouchers` (§3.3); `faction_read.py` (membership, faction names/secret flag, rank order, quest-reference check, in_any_faction — tolerant to missing tables); Quest model/schemas/admin CRUD validation (§3.10, incl. 409 when a referenced quest becomes repeatable/deleted); quest list gating + accept re-check (§3.9: secret → hidden/404, others locked reason / 403); `_apply_quest_faction` post-commit call; voucher internal create, player list, `plots/{id}/claim` (§3.10). No commits/pushes/git add. | Backend Developer | DONE | `services/locations-service/app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `app/houses.py`, `app/faction_read.py`, `app/alembic/versions/058_quest_faction_vouchers.py` | 1 (table names/columns) | Existing quest/house flows unchanged for quests without faction fields; secret faction quests invisible to non-members; claim creates a free house only with a matching voucher; py_compile passes |
| 5 | **user-service: permissions.** Migration `0034` adding `factions:read/edit/delete/manage/settings` (moderator: read/edit/manage; idempotent, pattern 0033) + explicit `_seed_faction_permissions` section and `TestFactionPermissions` in `tests/test_rbac_permissions.py` (CLAUDE.md §10.13). No commits/pushes/git add. | Backend Developer | DONE | `services/user-service/alembic/versions/0034_faction_permissions.py`, `services/user-service/tests/test_rbac_permissions.py` | — | Migration idempotent; RBAC test file passes in the container; py_compile passes |
| 6 | **Frontend: API layer + profile tab «Фракции» + passport block.** `api/factions.ts` (all types/functions §3.10), `ProfileTabs`/`ProfilePage` wiring, `FactionsTab/*` (§3.12), passport «Фракции» section. No commits/pushes/git add. | Frontend Developer | DONE | `src/api/factions.ts`, `src/components/ProfilePage/ProfileTabs.tsx`, `src/components/ProfilePage/ProfilePage.tsx`, `src/components/ProfilePage/FactionsTab/*`, `src/components/CommonComponents/CharacterPassport/*` | 1 | tsc + build pass; tab works at 360 px; leave confirm states cooldown/burn; warnings show countdown; errors shown in Russian |
| 7 | **Frontend: catalog page `/factions` + header link.** `components/pages/FactionsPage/*`, route in `App.tsx`, `navData.ts` link under «ИГРОВОЙ МИР», join / apply (message modal) / cancel / states (§3.12). No commits/pushes/git add. | Frontend Developer | DONE | `src/components/pages/FactionsPage/*`, `src/components/App/App.tsx`, `src/components/CommonComponents/Header/navData.ts` | 6 (api module) | tsc + build pass; conditions show ✓/✗; secret factions show no member count; mobile OK |
| 8 | **Frontend: admin section «Фракции» + admin character tab.** `components/Admin/FactionsPage/*` (tabs per §3.12), `AdminPage.tsx` entry, protected route, `AdminCharacterDetailPage` «Фракции» tab with delivery retry; permission-gated buttons. No commits/pushes/git add. | Frontend Developer | DONE | `src/components/Admin/FactionsPage/*`, `src/components/Admin/AdminPage.tsx`, `src/components/App/App.tsx`, `src/components/Admin/CharactersPage/AdminCharacterDetailPage.tsx`, `src/api/factions.ts` | 3, 6 | tsc + build pass; full CRUD flow works live; validation errors shown in Russian; mobile usable |
| 9 | **Frontend: quest editor fields + house vouchers UI.** `QuestEditor.tsx` faction/min rank/points-list fields; `api/houses.ts` voucher functions; «Права на дом» in `MyHousesPage.tsx`; «Получить по праву» on matching free plots in `LocationPage/HousesSection.tsx` (Tailwind migration of touched components if they still use SCSS). No commits/pushes/git add. | Frontend Developer | DONE | `src/components/AdminNpcsPage/QuestEditor.tsx`, `src/api/houses.ts`, `src/components/pages/HousesPage/MyHousesPage.tsx`, `src/components/pages/LocationPage/HousesSection.tsx` | 4, 6 | tsc + build pass; quest saves/loads faction fields; claim works live and shows errors |
| 10 | **QA: character-service tests.** `tests/faction_world.py` (DDL for `character_quests`, `quests`, `character_tree_progress`/`tree_nodes`, `character_attributes`, `Regions`/`Locations`, items/titles as needed; notifier recorders) + tests: each condition type incl. tier min/max and secret-name masking; join (NPC, limit, invite-only, cooldown, irreconcilable); apply/approve(re-check)/reject/reapply cooldown/duplicate pending; leave burn & rank recompute on rejoin & no re-granted rewards; quest-completed idempotency + hostility penalty floor 0 + non-member skip; multi-rank climb; outbox (xp exactly once, item ambiguous → failed not retried, voucher retry, mocked HTTP); level-up hook no recursion; pass warning→clear→expel timing + throttle; secrecy of public/catalog endpoints; admin permission 403s & validation 422/409; settings bounds; character deletion cascade. No commits/pushes/git add. | QA Test | DONE | `services/character-service/app/tests/faction_world.py`, `app/tests/test_factions_*.py`, `app/tests/test_delete_character_cleanup.py` (extend) | 1, 2, 3 | All new tests pass inside the container; full existing suite still green |
| 11 | **QA: locations-service + user-service tests.** Quest faction fields validation (rank of other faction, repeatable referenced quest 409, delete referenced 409), gating (non-member locked / secret hidden / rank lock / accept 403/404), `_apply_quest_faction` call conditions with mocked HTTP and that completion never fails on its error, voucher internal idempotency, claim (matching/mismatching kind/location, already claimed, plot taken, no gold charged); run RBAC test from task 5. Sync-wrapper style (no pytest-asyncio in containers). No commits/pushes/git add. | QA Test | DONE | `services/locations-service/app/tests/test_quest_factions.py`, `app/tests/test_house_vouchers.py` | 4, 5 | All new tests pass in the containers; existing suites green |
| 12 | **Review.** Full review vs §3 (security, secrecy, idempotency, CLAUDE.md frontend rules), py_compile/tsc/build re-run, pytest in the three services, live verification in Chrome on localhost (join, quest → rank-up → rewards, leave/rejoin, admin flows, passport, catalog, 360 px). No commits/pushes/git add. | Reviewer | TODO | — | 1–11 | PASS with automated + live results logged in §5 |

---

## 5. Review Log (filled by Reviewer — in English)

### QA findings (task #10/#11, 2026-11-06)

- **QA bug #1 (LOW, character-service `app/faction_rewards.py::_deliver_item`)** — violates §3.6 «no HTTP inside a
  transaction»: `db.rollback()` is called, then `inventory_url(delivery.character_id)` reads an *expired* ORM
  attribute, which lazy-loads it with a new SELECT and leaves a read transaction (and the pooled connection) open for
  the whole inventory call (up to 5 s). No row locks (plain consistent read), so impact is connection hold time only.
  Voucher path is fine (body built before the rollback). Fix: capture `character_id` (and the payload) before
  `db.rollback()`. Covered by `tests/test_factions_flows.py::TestRewards::test_no_transaction_is_open_during_the_http_call[item]`,
  currently `xfail(strict=True)` — remove the marker after the fix.
- Product code was NOT changed by QA.

### Review #1 — 2026-11-06
**Result:** FAIL (2 small backend fixes; everything else passes)

#### Automated Check Results
- [x] `py_compile` (all changed/new .py in character-, locations-, user-service) — PASS
- [x] `pytest` character-service (container, full suite) — PASS: 9276 passed, 1 skipped (QA bug #1 fix confirmed, xfail gone)
- [x] `pytest` locations-service (container, `--asyncio-mode=auto`; pytest-asyncio is now installed there) — PASS: 2926 passed, 4 skipped, 0 failed
- [x] `pytest` user-service (container) — PASS: 780 passed, 5 skipped
- [x] `npx tsc --noEmit` (frontend container) — PASS (0 errors)
- [x] `vite build` (frontend container) — PASS
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, localhost, admin / Ашари 763) — PASS

#### Live Verification Results
- Pages: `/factions` (cards, expand, secret faction without member count), `/profile` -> «Фракции» (2 memberships, rank, points, applications, journal), `/admin/factions` (list, editor, tabs Враждебность / Заявки / Участники / Настройки), `/admin/characters/763` -> «Фракции» (deliveries + journal).
- 360 px (iframe): `/factions`, `/admin/factions`, `/admin/characters/763` — no horizontal overflow.
- Console errors: NONE. character-service / locations-service logs: no 5xx, no tracebacks during the session.
- API: all player/admin/voucher endpoints 200; catalog without JWT 401; internal quest-completed and internal vouchers without token 403; secret faction has `member_count`/`member_limit` null in the catalog and `/factions/2/public`; `/characters/763/factions/public` omits the secret membership. Quest admin validation: foreign rank -> 422, points 0 -> 422 (Russian texts).

#### Checklist summary
- Contracts backend <-> frontend <-> tests consistent (dev deviations accepted: background delivery after quest-completed, `settings` block in the private view, `params` in catalog conditions).
- Pydantic v1, no `React.FC`, Tailwind + design-system classes, TS only, Russian errors via `apiErrorMessage`, countdowns via `RemainingText` («осталось …») — OK.
- Auth: JWT + ownership on player writes, `require_private_access` on private reads, `require_permission(factions:*)` on admin, `verify_internal_token` on internal — OK. RBAC migration 0034 + explicit test section — OK.
- Idempotency: `faction:quest:cq:{id}` UNIQUE(event_key, faction_id), hostile key per source faction, grants UNIQUE(character, rank) untouched by leave/rejoin, voucher `source_key` UNIQUE, delivery claim by conditional UPDATE, ambiguous item -> failed/uncertain — OK.
- No HTTP inside DB transactions (rollback before item/voucher calls; locations calls after its commit) — OK.
- Migrations 045 / 058 / 0034: ids <= 32 chars, VARCHAR not ENUM, FK columns indexed, guarded/idempotent — OK.
- Level-up hook non-fatal, collector ContextVar prevents nested delivery, loop-thread rule respected; faction pass has its own claim row (300 s) and per-member transactions — OK.
- Docs updated; nothing unrelated in the diff.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/locations-service/app/crud.py:5456-5458`, `app/schemas.py:1456-1458` (`QuestAvailableRead`) | Secrecy leak: the PLAYER NPC quest list returns raw `faction_id`, `min_faction_rank_id`, `faction_points_rewards`. A public quest (or a non-secret faction quest) that rewards/penalises a SECRET faction exposes that faction's id + points to every player; ids map to names via the catalog (secret factions are listed there). The frontend does not use these fields in `NpcQuestsModal`. Fix: drop the three fields from the player list / `QuestAvailableRead` (keep them in admin `QuestRead`), or at least filter out entries of secret factions where the character is not an active member. Add a test. | Backend Developer | FIXED |
| 2 | `services/character-service/app/faction_core.py:251-252` (+ `faction_crud.load_refs`) | Subclass condition text uses raw keys («Подкласс: warrior_paladin»). The frontend patches catalog texts, but the same text is persisted in `faction_members.warning_reasons`, the journal and warning notifications — players see English keys there. Decision on the frontend note: the backend SHOULD resolve names — in `load_refs` via `SELECT subclass_key, name FROM tree_nodes WHERE node_type='subclass_choice' AND subclass_key IN (...)` (names match the skills-service registry locally), fallback to the key. The frontend helper can stay as a fallback. Add a test. | Backend Developer | FIXED |
| 3 | `services/character-service/app/faction_crud.py:529-532` | Note only: the irreconcilable 409 names the other faction even when it is secret — acceptable, the player is an active member of it. | — | NOTE |

Pre-existing issues noted: none.

### Review #2 — 2026-11-06
**Result:** PASS

Both Review #1 issues are fixed and verified:
- #1 `locations-service/app/crud.py` (`get_available_quests_for_npc`) and `schemas.QuestAvailableRead` no longer return `faction_id` / `min_faction_rank_id` / `faction_points_rewards` (admin `QuestRead` keeps them; frontend only uses them in the admin `QuestEditor`). Live: `GET /locations/npcs/33/quests?character_id=763` → 200, no `faction` key in the body. Status: FIXED.
- #2 `faction_crud.subclass_names()` reads `tree_nodes` (`subclass_choice`), `load_refs` fills `refs.subclasses`, `faction_core.condition_text` falls back to the key. Live: a temporary subclass condition on faction 1 rendered «Подкласс: Паладин или Саламандр» in the catalog (condition removed afterwards, faction 1 restored to its 2 original conditions). Status: FIXED.
- The test helper change (`tests/reputation_world.py`: `tree_nodes.name` column) only affects test DDL.

#### Automated Check Results
- [x] `py_compile` (changed backend files + faction tests) — PASS
- [x] `pytest` character-service (container, full suite) — PASS: 9278 passed, 1 skipped
- [x] `pytest` locations-service (container, `--asyncio-mode=auto`) — PASS: 2929 passed, 4 skipped
- [x] `tsc` / `build` — N/A (no frontend change since Review #1, where both passed)
- [x] Live verification — PASS (see above)

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-05 — PM: фича создана по решениям пользователя (этап 1 фракций), запускаю анализ
[LOG] 2026-11-05 — Analyst: анализ завершён — ядро в character-service (045), квесты в locations-service (058), права в user-service (0034); отдельной сущности «участок» нет, награда «дом/участок» требует решения (право на бесплатный дом); 7 вопросов к пользователю
[LOG] 2026-11-05 — Architect: спроектировано — 9 таблиц в character-service (045), поля квестов + права на дом в locations-service (058), права factions:* (0034); награды через «очередь выдачи» (outbox) без дублей; 12 задач (5 бэкенд, 4 фронтенд, 2 QA, ревью); блокирующих вопросов нет, 6 решений по умолчанию вынесены в §3.0 на подтверждение
[LOG] 2026-11-05 — Backend Dev: задача #4 (locations-service) — миграция 058 (поля фракции у квестов + таблица house_vouchers), faction_read.py (чтение таблиц фракций SQL-ом, без таблиц — «нет данных», фракционные задания скрыты), валидация полей квеста и 409 для квестов-условий, гейт списка/принятия (тайные скрыты/404, остальные «Только для членов…»/403, звание), вызов quest-completed после сдачи, права на дом: внутреннее создание, список, получение участка по праву; документация сервиса обновлена
[LOG] 2026-11-05 — Backend Dev: задача #5 выполнена — миграция user-service 0034 (права factions:read/edit/delete/manage/settings; модератору read/edit/manage), раздел TestFactionPermissions в test_rbac_permissions.py; тесты user-service 780 passed, миграция применена локально
[LOG] 2026-11-05 — Backend Dev: задачи #1–#3 (character-service) выполнены — миграция 045 (10 таблиц, строка настроек), faction_core/crud/admin_crud/rewards/hooks/pass/notify/api, хук повышения уровня в check_and_update_level, проход фракций в планировщике, crud.add_passive_xp; все эндпоинты §3.10 (игрок, админ, внутренний quest-completed)
[LOG] 2026-11-05 — Backend Dev: отклонения от §3 — внутренний quest-completed выдаёт награды фоновой задачей после ответа (не держит locations-service); в GET /{cid}/factions добавлен блок settings (дни/процент для окна «Покинуть»); в условиях каталога добавлено поле params (у тайных фракций — null)
[LOG] 2026-11-06 — QA: задача #10 — тесты character-service: tests/faction_world.py + test_factions_core.py / test_factions_flows.py / test_factions_admin.py (286 тестов + 1 xfail): все типы условий (слава/слухи по ступеням), лимит, заявки/24 ч, непримиримые пары, −50 % враждебной, тайность, автоповышение, хук уровня без рекурсии, награды один раз, очередь выдачи, выход/исключение, проход (предупреждение → 3 дня), права 403, валидация, миграция 045, каскад удаления; полный набор 9275 passed
[LOG] 2026-11-06 — QA: задача #11 — тесты locations-service: test_quest_factions.py + test_house_vouchers.py (89 тестов, синхронные, через asyncio.run): гейт заданий, принятие 403/404, поля квеста и 409, вызов quest-completed, права на дом, миграция 058; новых падений нет (344 старых из-за pytest-asyncio — тот же набор); user-service: test_rbac_permissions 109 passed, весь сервис 780 passed
[LOG] 2026-11-06 — QA: найден баг #1 (LOW) — при выдаче предмета открыта транзакция БД во время HTTP-запроса в inventory (faction_rewards._deliver_item), записан в §5, тест помечен xfail(strict); код продукта не менялся
[LOG] 2026-11-06 — Frontend Dev: задачи #6–#9 выполнены — api/factions.ts; вкладка профиля «Фракции» (звание, очки, следующее звание с ✓/✗, предупреждение с обратным отсчётом, «Покинуть» с днями и % сгорания, заявки, бывшие фракции, журнал); блок «Фракции» в паспорте (только нетайные); каталог /factions + ссылка в шапке «ИГРОВОЙ МИР» (вступление, заявка с сообщением, отзыв, отсчёт до повторного вступления/заявки); админка /admin/factions (фракции, звания с порядком и наградами, условия вступления, враждебность, заявки, участники, настройки) и вкладка «Фракции» в карточке персонажа с повтором выдачи; поля фракции в редакторе квестов; «Права на дом» в «Мои дома» и «Получить по праву» на свободном участке
[LOG] 2026-11-06 — Frontend Dev: проверено — tsc и build в контейнере без ошибок; живая проверка в Chrome на localhost: создание фракции и званий, вступление, повышение до «Рыцаря» начислением очков, паспорт, заявка в тайную фракцию → одобрение, враждебная пара, квест с полями фракции сохраняется и загружается, право на дом выдано и получено (дом создан), 360 px без горизонтальной прокрутки, ошибок в консоли нет
[LOG] 2026-11-06 — Frontend Dev: замечание — в join_block_reason бэкенд пишет ключи подклассов (warrior_paladin), фронт подменяет их на названия; в локальной БД остались тестовые фракции «Тестовый Орден Зари»/«Тестовая Тень», квест 9116 и дом №3 Ашари
[LOG] 2026-11-06 — PM: QA bug #1 исправлен (faction_rewards._deliver_item: URL собирается до rollback), xfail снят, 287 тестов фракций проходят; запускаю ревью
[LOG] 2026-11-06 — Reviewer: проверка завершена, результат FAIL — тесты (character 9276, locations 2926, user 780), tsc/build, живая проверка в Chrome без ошибок; 2 правки бэкенда: (1) список заданий NPC отдаёт игрокам faction_points_rewards/faction_id — утечка тайных фракций; (2) названия подклассов вместо ключей в тексте условия (предупреждения, журнал, уведомления)
[LOG] 2026-11-06 — Backend Dev: правки ревью #1 — (1) из списка заданий NPC для игроков убраны faction_id / min_faction_rank_id / faction_points_rewards (в админском QuestRead остались, фронт их в списке не использовал), тест test_player_list_has_no_faction_fields; (2) названия подклассов берутся из tree_nodes (subclass_choice) в load_refs → текст условия «Подкласс: Паладин» (запасной вариант — ключ), тесты в test_factions_core/test_factions_flows; фронтовый помощник оставлен как запасной
```
[LOG] 2026-11-06 — Reviewer: ревью #2 — обе правки проверены (в списке заданий NPC нет полей фракций; условие подкласса показывает «Паладин»), тесты character 9278 / locations 2929 без падений, результат PASS

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Фракции (character-service, миграция 045): каталог, вступление по условиям (репутация края, ступени славы/дурной славы, уровень, класс/подкласс/раса, квест, «не во фракции X»), лимит мест, вступление по заявке с одобрением админом, тайные фракции, враждебность (−50 % очков, непримиримые пары), очки и звания с автоповышением, награды за звания (опыт, предметы, титул, право на дом/участок) — один раз навсегда, выход/исключение (3 д предупреждения, 7 д до повтора, сгорает 50 %), журнал, периодический проход.
- Квесты (locations-service, миграция 058): принадлежность фракции, минимальное звание, очки фракции в награде; права на дом/участок и бесплатное занятие места.
- Права админки `factions:*` (user-service, миграция 0034).
- Фронтенд: вкладка «Фракции» в профиле, блок в паспорте, каталог /factions, админка «Фракции», поля в редакторе квестов, права на дом в «Моих домах».
- ~380 новых тестов; ревью #1 FAIL (утечка тайной фракции через список квестов, ключи подклассов) → исправлено → ревью #2 PASS.

### Что изменилось от первоначального плана
- Награды марками — в этап 2 (казна фракции), как и договаривались.

### Оставшиеся риски / follow-up задачи
- Этап 2: казна фракций, условные участники, интендант, марки за звания (в долг при пустой казне).
- Этап 3: закрытые локации/данжи, пассивки, очки за убийство врагов фракции, членство как преступление.
- На проде фракций пока нет — их нужно создать в админке.
