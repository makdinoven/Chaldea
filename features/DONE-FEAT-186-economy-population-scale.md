# FEAT-186: Экономика — лорное население в масштабе 1:100, «регионы» вместо «городов», сокращённые числа

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-10-29 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Население регионов в лоре — от 100 000 до 4 000 000. Экономика (FEAT-182..184) настроена на десятки тысяч жителей,
и всё в регионе (потребление, производство, кошелёк жителей, налоги, торговля жителей, вклады/займы жителей)
масштабируется линейно от населения. Если вписать настоящие числа, денег в мире станет на два порядка больше и
игроки станут незаметны. Плюс: всё в игре называется регионами, а фразы карточки и шаблоны говорят «город»,
«край», «крепость», «округа».

### Бизнес-правила (согласовано с пользователем 2026-10-29: «Делай как рекомендуешь, 1 к 100»)
1. **Население в БД и в админке — лорное** (настоящее, например 4 000 000). Игрок видит лорное.
2. **Расчёт берёт население в масштабе:** расчётное = лорное / `population_scale`. Новый параметр «Пересчёта»
   `population_scale`, по умолчанию **100** (4 000 000 → 40 000; 100 000 → 1 000). Применяется везде, где расчёт
   использует население (потребление/производство/нормы запасов/кошелёк/резервы/гранты по населению/торговля
   жителей с торговцами/вклады и займы жителей в банке — всё, что сейчас читает `population`).
3. **Существующие данные сохраняют поведение:** миграция умножает текущее население регионов и население по
   умолчанию у шаблонов на 100 (столица 25 000 → 2 500 000 и т.д.), чтобы расчёт дал те же суммы.
4. **Везде «Регион»:** слово для фраз карточки у всех шаблонов — «Регион» (м. р.): «Регион сыт», «Скромный регион».
   Шаблоны переименовываются: Столица → Столичный регион, Портовый → Портовый регион, Шахтёрский → Шахтёрский регион,
   Аграрный → Аграрный регион, Лесной → Лесной регион, Магический → Магический регион, Пограничная крепость →
   Пограничный регион, Сельская округа → Сельский регион; описания — про регион, не про город/край. На проде
   меняются только шаблоны, которые админ ещё не трогал (значения совпадают со старыми по умолчанию). Код по
   умолчанию («Город») → «Регион».
5. **Сокращённые числа:** население выводится коротко: 4 000 000 → «4.0 м», 4 500 000 → «4.5 м», 120 000 →
   «120 к», 12 500 → «12.5 к», меньше 1000 — как есть (точное число — в подсказке/title). Так же коротко — большие
   суммы в админских сводках экономики (кошельки жителей, казны, запасы и т.п. от 100 000), точное значение — в
   подсказке. Деньги игрока (кошелёк, лавка, банк игрока, шапка) — точными, как сейчас. Поля ввода — точное число,
   рядом короткое превью.
6. Гайд «Как настроить» и подсказки «?» обновить: лорное население, масштаб, новые названия, новые числа.

### Edge Cases
- Население меньше масштаба (например 50 при масштабе 100) → расчётное < 1: регион живёт как крошечный (дробное
  население допустимо в формулах или минимум — решает разработчик, без деления на ноль).
- Смена `population_scale` админом сразу меняет масштаб всей экономики со следующего пересчёта — в подсказке
  предупредить.
- Население 0 = регион не в пересчёте (как сейчас).

---

## 4. Tasks

| # | Description | Agent | Status | Depends On |
|---|-------------|-------|--------|------------|
| B1 | character-service: `population_scale` param (default 100, bounds), scaled population everywhere the sim/merchants/banks read it, migration 032 (×100 populations + template renames/noun «Регион» only where untouched), code defaults «Регион», tests, docs | Backend Developer | DONE | — |
| F1 | frontend: compact number formatter util + population everywhere (admin regions/templates/editor/card), big admin economy sums compact with exact in title, `population_scale` param + hint, guide/hints texts update | Frontend Developer | DONE | — |
| Q1 | tests: scaling equivalence (lore N with scale 100 == old N/100), migration, renames | QA Test | DONE | B1 |
| R1 | review + live check | Reviewer | DONE | B1, F1, Q1 |

## 5. Review Log

### Review #1 — 2026-10-29
**Result:** PASS (with small reviewer fixes)

#### Code review
- Equivalence: every population use in the sim goes through `econ_sim.sim_population` (simulate_region, `_recompute_norms`, fill `starting_purse`, `_region_item` / `_template_dict` display). Remaining raw-population reads are only `> 0` participation checks and `country_grants` (proportional split, scale-independent). Lore N at scale 100 == old N/100 (exact float when N is a multiple of 100); scale floored at 1, population 0 -> not simulated, fractional sim population allowed.
- Migration 032: only templates, field-by-field and only where the 028 value is still present; downgrade symmetric; revision id 25 chars; plain UPDATEs (MySQL-safe). `econ_regions` / history untouched (matches the prod facts).
- Fill rescale: `econ_bank.resident_rescale` sets excess deposits off against excess loans, pays the rest within the bank balance / purse (never negative), targets = steady state of the residents' step; all legs in one `admin_emission` operation (bank<->purse, purse/treasury->emission), so the world sum stays 0; `econ_banks` locked before any account (FEAT-184 order) for every target region when `return_purse_excess`; player vault/deposits untouched; idempotent; `InsufficientFunds` -> Russian 409.
- RBAC unchanged (fill requires `economy:settings` + `economy:emit`), Pydantic v1 (`StrictBool`, `Optional[int]`), bounds `population_scale` 1..10000 int.
- Frontend: TS, Tailwind, no React.FC; compact rule verified (4 000 000 -> «4.0 м», 4 500 000 -> «4.5 м», 120 000 -> «120 к», 12 500 -> «12.5 к», <1000 exact, 999 960 -> «1.0 м»), exact value in `title`; player-facing money components not touched (still exact).

#### Fixes made by Reviewer
| # | File | Fix |
|---|------|-----|
| 1 | `src/types/economy.ts`, `EconomyRegions.tsx` | Fill response fields `resident_deposits_out` / `resident_loans_repaid` were not typed nor shown — added to `EconFillResult`, to the result line («Банк: вклады жителей возвращены в кошелёк …, займы жителей погашены …») and to the toast |
| 2 | `EconomyRegions.tsx` | «Вернуть излишек кошелька жителей» hint now says the residents' bank positions are rescaled first (player deposits untouched) |
| 3 | `EconomyGuide.tsx` | Recipe «Перешли на масштаб населения» step 3 mentions the bank rescale |
| 4 | `paramHints.ts` | `population_scale` hint listed «доля дотации страны» as scale-dependent — corrected (grants split by lore population, independent of the scale) |

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (only the known EffectRunes noise filtered)
- [x] `vite build` — PASS
- [x] `py_compile` (econ_sim, econ_bank, economy_api, economy_sim_crud, schemas, migration 032, tests) — PASS
- [x] `pytest` character-service in Docker — PASS, exit 0: 3017 passed, 1 skipped
- [x] `scripts/check_econ_copies.sh` — PASS
- [x] `docker compose config` — PASS

#### Live Verification Results (local MySQL prod rehearsal)
- Migration 032 downgrade -> upgrade -> downgrade -> upgrade: templates switch 028 <-> 032 values cleanly.
- Regions set to 4 000 000 / 1 500 000 / 120 000, `population_scale` = 1, purses inflated (capital 13.66 м emission, as on prod), 8 manual ticks with aged bank clock -> capital purse 9.2 м, treasury 3.1 м, resident deposits 2.22 м / loans 0.90 м.
- Scale 100, «Заполнить» via admin UI (Chrome) with «Запасы — к норме» + both return flags: purses = metadata targets exactly (capital 283 808), treasuries = reserve targets, food norm 8 400 000 -> 84 000 (÷100), resident deposits 70 952 / loans 28 380 = targets (P*·0.2/0.8, P*·0.1), bank 71 245 >= 0, player vault 593 unchanged; returned 15.1 м, bank 2.2 м / 875 к shown in the result; summary invariant ok, ledger_sum 0 («Сходится»).
- Second fill (API, same flags): 0 operations, all amounts 0. Manual tick afterwards: hunger 0 everywhere, bank positions stay at targets, ledger_sum 0.
- UI: compact population/money with exact hover («4.0 м => 4 000 000 жит. · в расчёте 40 000», «284 к марок => 283 808 марок»), «Пересчёт» shows «Масштаб населения, 1 к N» with hint, guide recipe present, no horizontal overflow at 360px on Регионы/Шаблоны/Банки/Сводка/Как настроить/Пересчёт, zero console errors.
- Local data changed: regions 9/14/10 populations restored (2 500 000 / 600 000 / 250 000); balances, resident bank positions, stocks of the 5 simulated local regions are now the post-rehearsal state (plus emission ops 261–263 and fill ops 322–326); `population_scale` back to 100.

## 6. Logging
```
[LOG] 2026-10-29 — PM: фича создана по решению пользователя («Делай как рекомендуешь, 1 к 100» + сокращённые числа)
[LOG] 2026-10-29 — Frontend Dev: F1 готово — utils/compactNumber.ts (4.0 м / 12.5 к / 120 к), CompactValue.tsx (BigMoney, Population), население коротко в «Регионах», «Шаблонах», редакторе (превью у поля), большие суммы админки коротко с точным в title; параметр «Масштаб населения» в «Пересчёте» с подсказкой; гайд и подсказки — лорное население, 1 к 100, новые названия шаблонов. tsc и build проходят
[LOG] 2026-10-29 — Frontend Dev: доработка F1 — в «Заполнить регионы по шаблонам» две галочки возврата излишка (кошелёк жителей / казна) в эмиссию, возвращённые суммы в итоге и тосте; предел населения в полях 1 000 000 000; в гайде рецепт «Перешли на масштаб населения (регионы раздуты)». tsc и build проходят
[LOG] 2026-10-29 — Backend Developer: B1 готово — параметр population_scale (100, 1..10000) и econ_sim.sim_population, расчёт везде на лорное/масштаб; миграция 032 (население ×100, шаблоны → «… регион», слово «Регион» только где не правили); в API sim_population / default_sim_population; лимит населения 1 млрд; тесты эквивалентности ×100 (бит-в-бит), границ, миграции; набор character-service зелёный, миграция туда-обратно на MySQL и ручной пересчёт прошли
[LOG] 2026-10-29 — Backend Developer: B1 поправлено по данным прода — миграция 032 больше не трогает население регионов и историю (там уже лорные числа), ×100 только у шаблонов с населением 028; в «Заполнить» добавлены return_purse_excess / return_treasury_excess («Привести к масштабу»: излишек кошелька/казны выше цели → эмиссия операцией admin_emission, повторный клик = 0); тесты, документация, миграция туда-обратно и заполнение + пересчёт на MySQL прошли
[LOG] 2026-10-29 — Backend Developer: исправлен баг QA (вклады/займы жителей в банке не приводились к масштабу) — при return_purse_excess «Заполнить» сначала приводит позиции жителей в банке к целям (зачёт вкладов против займов, остаток деньгами, банк не в минус, вклады игроков не трогаются), xfail снят, добавлены тесты краёв; полный набор character-service зелёный
[LOG] 2026-10-29 — QA Test: Q1 готово — тесты бэкенда разработчика просмотрены, добавлено: прод-сценарий (регионы 120 000…4 000 000, несколько пересчётов при масштабе 1 → масштаб 100 → «Заполнить» с reset_stocks и обоими флагами возврата: кошелёк/казна на цели, нормы ÷100, сумма мира 0, повторный клик = 0, 4 пересчёта без голода и минусов), возврат без пополнения, смена масштаба на лету, null/границы масштаба, население 1/50/99 при масштабе 100, StrictBool флагов (422), RBAC «Заполнить» с флагами, фразы карточки «Регион сыт», банки и торговцы в лорных регионах. Найден баг (xfail strict): «Привести к масштабу» не трогает вклады/займы жителей в банке (econ_banks.resident_*) — после перехода с масштаба 1 жители за несколько периодов выливают ×100-вклады обратно в кошелёк (кошелёк 4.25× цели через 4 периода). Набор character-service: 3011 passed, 1 xfailed
[LOG] 2026-10-29 — Reviewer: проверка завершена, результат PASS — эквивалентность ×100, миграция 032 туда-обратно, репетиция прода на локальной MySQL (раздутые кошельки/казны/банк → «Заполнить» с возвратом → цели, сумма мира 0, повторный клик = 0, пересчёт стабилен); добавил вывод возвращённых вкладов/погашенных займов жителей в итог заполнения, поправил подсказки и гайд
```

## 7. Completion Summary

**Сделано (2026-10-29):** население в БД и админке — лорное; расчёт берёт его в масштабе `population_scale`
(по умолчанию 100) через единый `econ_sim.sim_population`. Миграция 032 меняет только нетронутые шаблоны (население
×100, «… регион», слово «Регион»); население регионов на проде не трогается — оно уже лорное. «Заполнить регионы по
шаблонам» пересчитывает нормы под масштаб и умеет вернуть излишек кошелька жителей (с приведением их вкладов/займов
в банке) и казны в эмиссию одной проводкой. Фронт: сокращённые числа («4.0 м», «120 к») для населения и больших
админских сумм, точное — в подсказке; параметр масштаба, две галочки возврата, рецепт в гайде. Тесты character 3017,
ревью PASS с репетицией прод-сценария на локальной MySQL.

**После выкатки на прод:** «Экономика → Регионы → Заполнить регионы по шаблонам» с «Запасы — к норме» и обеими
галочками возврата излишков (один раз; повторно ничего не двигает).
