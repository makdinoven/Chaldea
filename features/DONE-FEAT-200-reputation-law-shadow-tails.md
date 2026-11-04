# FEAT-200: Хвосты после репутации, закона и тени

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-04 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Пачка мелких доработок и багов, найденных при ревью FEAT-197/198/199 (пользователь поручил вести этапы до конца; хвосты — этап 2 плана). Только целевые правки, без рефакторинга.

### Список (что делаем)
1. **Бой с NPC без здоровья** (ISSUES «Нападение» на воскрешённого NPC с нулевым здоровьем…): при оживлении NPC (`update_npc_status` → alive, снятие нокаута, выход стражника из нокаута) поднимать здоровье до максимума; и на сервере боя не создавать бой против NPC с `current_health <= 0` (409 «Этот персонаж сейчас недоступен для боя»). Закрыть запись в ISSUES.
2. **Карточка персонажа в админке по прямой ссылке** (ISSUES): `/admin/characters/:id` должна грузить персонажа по id, а не искать в первой странице списка. Закрыть запись в ISSUES.
3. **Список товаров у NPC с порогом репутации**: личный список товаров (`GET .../shop?character_id=`) тоже закрывать порогом NPC (403 «Нужна репутация: …»), как покупку/продажу.
4. **Формулировка журнала**: выбитый (не убитый) стражник пишется в журнал репутации как «Убит NPC» — для нокаута стражника писать «Стражник повержен» (или аналогично); проверить тексты журнала.
5. **Окно авто-решения vs «драться»**: авто-сдача/авто-штраф планировщиком не должна срабатывать по встрече, которая уже в статусе «бой» (или игрок только что выбрал «драться») — условный UPDATE по статусу pending.
6. **«Розыск снят» при нулевом розыске**: при снятии розыска по краю, где его нет, отвечать «Розыска нет» и не писать лишнюю запись в журнал.
7. **Лимит победителей 50**: `killer_character_ids` > 50 даёт 422 и NPC не умирает — убрать падение: обрезать/принимать список больше (например до 200) без 422, NPC умирает всегда.
8. **Ключ славы**: `fame:rep:{idem_key}` обрезается до 191 символа — для длинных ключей использовать хеш (например sha1) хвоста, чтобы разные события не слипались.
9. **Вызовы после коммита задания**: `_apply_quest_reputation` / `_apply_quest_fame` ловят только `httpx.HTTPError` — любое другое исключение после коммита даёт 500 при уже выполненном задании; ловить все исключения (с логом).

### Бизнес-правила
- Поведение игры не меняется, кроме исправлений выше.

---

## 4. Tasks

| # | Description | Agent | Status | Depends On |
|---|---|---|---|---|
| 1 | Backend fixes 1, 3–9 (character-service, battle-service, locations-service) | Backend Developer | DONE | — |
| 2 | Frontend fix 2 (admin character card by id) | Frontend Developer | DONE | — |
| 3 | QA: tests for every fix | QA Test | DONE | 1, 2 |
| 4 | Review + live verification | Reviewer | DONE | 3 |

---

## 5. Review Log

### Review #1 — 2026-11-04
**Result:** PASS

Scope: FEAT-200 fixes 1-9 + deploy-readiness of the whole uncommitted tree (FEAT-198 + FEAT-199 + FEAT-200).

#### Code review (FEAT-200)
- Fix 1: `_restore_revived_npc` (best effort, `current_* = max_*`) is called on admin `dead -> alive` and on internal `npc-status alive`; battle-service `_ensure_npc_available` adds a `current_health <= 0` check (409, same text) after the dead/KO check, only for `is_npc` rows; a missing attributes row passes. Guard KO expiry is healed by the law pass (`_guard_recovery`). OK.
- Fix 2: `GET /characters/admin/{character_id:int}` (characters:read, `is_npc == False`, 404 otherwise). Route shadowing checked: the `:int` converter matches digits only, so `/admin/list`, `/admin/npcs`, `/admin/titles`, `/admin/levels/...`, `/admin/mob-*` and the routers included earlier (economy/reputation/law/shadow) are unaffected; live: list/npcs/titles 200, new route 200 / 404 (unknown or NPC) / 401 (anonymous). Frontend: one request, 404 -> «Персонаж не найден» on the page, other errors via `apiErrorMessage` + toast, no infinite spinner, no React.FC, Tailwind tokens.
- Fix 3: personal shop (`character_id` given) runs `require_private_access` then `require_npc_tier` (403 «Нужна репутация: …»); public window unchanged; `NpcShopModal` already maps 403 to the refusal panel.
- Fix 4: `npc_kill_reason` -> «Повержен стражник «…» (#id)» for the guard role.
- Fix 5: `auto_resolve` passes `statuses=(pending,)` into `send_to_jail` / `_forced_fine_commit`, both re-check the status under `FOR UPDATE` locks of character + encounter. OK.
- Fix 6: region without wanted -> no journal row, «Розыска нет»; all-regions path writes nothing when empty.
- Fix 7: validator dedups and caps at 200 (`NPC_KILLER_IDS_MAX`), no 422.
- Fix 8: `fame_rep_key` sha1 for keys over the column limit; short keys unchanged (nothing of FEAT-199 is on prod yet, so no key-format migration concern).
- Fix 9: broad `except Exception` with `logger.exception`, returns False; quest stays completed.
- Security: new endpoint behind `require_permission("characters:read")`; no raw SQL with user input; error texts in Russian, no internals leaked.

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (inside `frontend` container; the host node_modules lacks `react-icons`, environment only)
- [x] `npm run build` (vite build) — PASS (inside `frontend` container)
- [x] `py_compile` — PASS (100 changed/new .py files)
- [x] `pytest` — PASS: character 8220 passed / 1 skipped; locations 2757 passed (`--asyncio-mode=auto`); battle 1859 passed (`--asyncio-mode=auto`); inventory 2383 passed; user-service 776 passed; dungeon `test_econ_contract.py` + `test_feat175_entry.py` 453 passed with `--timeout=30 --timeout-method=signal` (18 s total, no slow tests)
- [x] `sh scripts/check_econ_copies.sh` — PASS (all shared copies identical)
- [x] `docker compose config` — PASS (dev and dev+prod)
- [x] Alembic single head per service: character `040_shadow_renown`, locations `056_quest_fame`, inventory `034_item_mask`, battle `009_battle_law_encounter`, user `0033`; no missing down_revisions, all ids <= 32 chars. New migrations (char 039/040, loc 055/056, inv 034, battle 009) only create tables/columns/indexes and seed static settings/tier rows with `WHERE NOT EXISTS` — no dependency on dev-only data.
- [x] Live verification — PASS

#### Live Verification Results
- `/admin/characters/764` by direct URL (id outside the first list page): card renders, zero console errors. `/admin/characters/641` (an NPC id): «Персонаж не найден» shown, no spinner.
- `GET /locations/npcs/33/shop?character_id=764` with NPC 33 temporarily gated at `legend`: 403 «Нужна репутация: Легенда края»; public `GET /locations/npcs/33/shop`: 200.
- NPC 641 alive with 0 HP: `POST /battles/` -> 409 «Этот персонаж сейчас недоступен для боя» (no battle created). Then dead + 0 HP, admin `PUT /characters/admin/npcs/641 {"npc_status":"alive"}` -> 200, HP 210/210, mana 90/90; `_ensure_npc_available(641)` passes (attackable).
- Local data restored (NPC 33 gate NULL; NPC 641 dead with its original 200/75/100/150 resources); no battles created.

#### Notes / risks (non-blocking)
- Local (prod-dump) data has merchant «Петя» (#33) alive with `current_health = 0`, plus 76 orphan mob characters with 0 HP (no `active_mobs` rows, so unreachable). After deploy such NPCs answer 409 instead of starting a broken battle; `_restore_revived_npc` only fires on dead -> alive, so an alive NPC with 0 HP stays unattackable until an admin toggles dead -> alive (or a one-off `UPDATE ... SET current_health = max_health` for alive non-mob NPCs). Optional follow-up.
- CI time budget: character-service suite grows from 7646 to 8220 tests (last CI step 4m09s against a 6 min step timeout). The 557 new FEAT-198/199/200 tests run in 46 s locally (~0.08 s each), so the expected CI step is ~4.5 min — within the limit but with a thinner margin.
- Deploy: 59 untracked files (new modules, migrations, tests, frontend files) must be `git add`-ed with the commits — e.g. `law_*.py`, `shadow_*.py`, `renown_crud.py`, `battle_client.py`, `character-service/app/stat_caps.py`, all six new migrations.

#### Small fix applied by Reviewer
- `docs/ISSUES.md`: the duplicate LOW entry «Нападение» на NPC с нулевым здоровьем… was still open — marked DONE (FEAT-200).

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-04 — PM: фича создана из хвостов ревью FEAT-197/198/199; запускаю разработку
[LOG] 2026-11-04 — Backend Dev: задача #1 —
  п.1: оживление NPC (internal npc-status → alive и админское npc_status dead → alive) поднимает current_* до max_* (main._restore_revived_npc); battle-service _ensure_npc_available даёт 409 при current_health <= 0; запись в ISSUES закрыта (DONE);
  п.3: личная витрина GET .../shop?character_id= закрыта гейтом NPC (403 «Нужна репутация: …»);
  п.4: причина в журнале репутации для стражника — «Повержен стражник «…» (#id)» вместо «Убит NPC»;
  п.5: авторазрешение (авто-сдача/авто-штраф) под блокировкой проходит только по встрече в статусе pending;
  п.6: снятие розыска в крае без розыска — ответ «Розыска нет», запись в журнал не пишется (и для «всех краёв» пустой маркер больше не пишется);
  п.7: killer_character_ids без лимита 50 — дубли убираются, берутся первые 200, без 422;
  п.8: ключ славы fame:rep:… при длине > 191 — sha1 вместо обрезки (reputation_crud.fame_rep_key);
  п.9: _apply_quest_reputation/_apply_quest_fame ловят любые исключения (logger.exception), 500 после коммита больше нет;
  обновлены docs/services (character, battle, locations) и ISSUES.md; два теста поправлены под намеренно изменённое поведение (test_law_admin — текст «Розыска нет»; test_reputation_npc_kill — убрана проверка 422 на 59 id); полные прогоны: character 8178 passed, battle 1840 passed, locations 2738 passed
[LOG] 2026-11-04 — Backend Dev: доп. к п.2 — новый эндпоинт GET /characters/admin/{id} (characters:read, форма строки админ-списка, NPC/неизвестный → 404, конвертер :int не перекрывает /admin/list и др.); fetchAdminCharacterById на фронте теперь делает один запрос к нему (404 → null, остальное — ошибка страницы); тесты 200/404/403 в test_admin_character_management.py; tsc и build чистые
[LOG] 2026-11-04 — Frontend Dev: задача 2 готова — карточка /admin/characters/:id грузит персонажа по id (имя через short_info, затем точное совпадение id в /characters/admin/list?q=имя с перебором страниц; отдельного GET /admin/{id} в character-service нет). Ошибки и «Персонаж не найден» видны на странице, а не бесконечный спиннер. tsc и build проходят
[LOG] 2026-11-04 — QA: задача 3 — тесты на все правки бэкенда: character-service новый test_feat200_tails.py (38: оживление NPC внутренним и админским путём поднимает ресурсы до максимума, падение лечения не мешает оживлению; журнал «Повержен стражник»; авторазрешение пропускает встречу в «бою» (тюрьма и штраф), pending по-прежнему решается; «Розыска нет» без записи в журнал; >50 и дубли убийц — дедуп, первые 200, NPC умирает; fame_rep_key — sha1 для длинных ключей, без склеек); battle-service +9 в test_law_guard_battle.py (409 при current_health <= 0, без строки атрибутов — проходит); locations-service +7 в test_reputation_trade.py (гейт NPC на личной витрине, публичная без гейта), +4 в test_reputation_gates.py и +5 в test_quest_fame.py (любое исключение после коммита — лог, False, задание выполнено). Полные прогоны: character 8220 passed, battle 1849 passed, locations 2754 passed. Багов не найдено
[LOG] 2026-11-04 21:00 — Reviewer: начал проверку FEAT-200 и готовности к выкатке всего рабочего дерева
[LOG] 2026-11-04 21:33 — Reviewer: проверка завершена, результат PASS. Все 9 правок верны; маршрут /characters/admin/{id:int} ничего не перекрывает. Полные прогоны: character 8220, locations 2757, battle 1859, inventory 2383, user 776, данжи (econ + feat175) 453 — всё зелёное; tsc и сборка чистые, копии econ совпадают, compose валиден, у каждого сервиса одна голова Alembic, миграции не зависят от локальных данных. Вживую: карточка по прямой ссылке открывается, личная витрина закрытого NPC — 403, оживлённый NPC с полным здоровьем, бой с NPC без здоровья — 409; локальные данные возвращены. Закрыл дубль записи в ISSUES.md. Готово к выкатке FEAT-198+199+200 (не забыть git add для 59 новых файлов)
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

**Статус: DONE (2026-11-04), ревью PASS.** Исправлены все 9 хвостов: оживлённый NPC получает полное здоровье, бой против NPC без здоровья не создаётся; карточка персонажа в админке открывается по прямой ссылке (новый `GET /characters/admin/{id}`); личный список товаров закрыт порогом NPC; «Повержен стражник» в журнале; авто-решение стражи не трогает начатый бой; «Розыска нет»; до 200 победителей без 422; длинные ключи славы хешируются; ошибки после выполнения задания не дают 500.
Риск: NPC, которые сейчас живы с 0 HP (на проде вероятно есть, напр. «Петя»), после деплоя недоступны для боя (409), пока админ не переключит их «мёртв → жив».
