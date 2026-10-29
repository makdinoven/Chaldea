# FEAT-185: Гайд по настройке экономики в админке

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-10-29 |
| **Author** | PM (Orchestrator) |
| **Priority** | MEDIUM |

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Пользователь (админ) базово понимает экономику, но ему тяжело разобраться, как правильно настроить раздел
«Экономика» в админке (этапы 1–4: книга счетов, живые регионы, торговцы, банки). Нужен подробный гайд прямо в
разделе админки. Только фронтенд и тексты, сервер не трогаем.

### Бизнес-правила (согласовано с пользователем 2026-10-29, «Да, делай»)
1. **Новая вкладка «Как настроить» — первая в разделе «Экономика»:**
   - живой чек-лист запуска: шаги по порядку, у каждого — статус из данных, которые админка уже получает
     (например «Шаблоны назначены: 3 из 13 регионов», «Кассы торговцев пополнены: 5 из 12», «Банков открыто: 2»,
     «Банкиров нет — назначь роль НПС»), и кнопка перехода в нужную вкладку;
   - «Как устроена экономика» простыми словами: откуда берутся и куда уходят марки, что такое казна (региона и
     страны), кошелёк жителей, касса торговца, банк (свои деньги и хранилище вкладов), эмиссия; что происходит
     каждые 6 часов; схема движения денег;
   - «Что делать, если…»: голод в регионе, пустая казна, торговцу нечем платить, банк не платит проценты, сводка
     пишет «не сходится», инфляция/дефляция — короткие рецепты.
2. **Подсказки у каждого параметра** (≈50 во вкладке «Пересчёт» и в редакторе региона, плюс настройки валюты и
   банка региона): значок «?» → что делает, что будет, если поднять/опустить, безопасный диапазон; для дневных
   ставок — перевод в месяц.
3. **На остальных вкладках** — короткая строка «что здесь» со ссылкой на нужный раздел гайда.

### UX
Админ открывает «Экономика» → видит «Как настроить» → идёт по чек-листу сверху вниз, жмёт кнопки перехода;
в «Пересчёте» наводит/нажимает «?» у непонятного параметра и читает объяснение.

### Edge Cases
- Нет прав `economy:settings` — чек-лист показывает статусы, кнопки действий ведут на вкладки (сами действия там
  уже скрыты правами).
- Данные не загрузились — ошибка по-русски, остальной гайд читается.
- Мобильный 360px: «?» открывается тапом (не только hover).

---

## 2–3. Analysis / Architecture
Frontend-only, текстовая фича; анализ и архитектура — в задачах ниже (PM). Источник фактов для текстов:
`docs/services/character-service.md` (экономика, Living regions, NPC merchants, Banks), `docs/services/locations-service.md`
(«Торговцы НПС»), `features/FEAT-181-world-economy.md`, `features/DONE-FEAT-182…`, `DONE-FEAT-183…`, `DONE-FEAT-184…`,
код вкладок `services/frontend/app-chaldea/src/components/Admin/EconomyPage/*`. Тексты обязаны совпадать с реальным
поведением кода (числа по умолчанию, границы — из `econ_sim.py` / схем).

## 4. Tasks

| # | Description | Agent | Status | Depends On |
|---|-------------|-------|--------|------------|
| F1 | Вкладка «Как настроить» (чек-лист, «Как устроена», «Что делать, если…») + строки «что здесь» на вкладках, кроме «Пересчёт» и редактора региона | Frontend Developer | DONE | — |
| F2 | Компонент подсказки «?» + подсказки у всех параметров «Пересчёт», редактора региона, банка региона, настроек валюты; строка «что здесь» в «Пересчёт» | Frontend Developer | DONE | — |
| R1 | Ревью: сверка текстов с кодом, правила фронтенда, живая проверка | Reviewer | DONE | F1, F2 |

## 5. Review Log

### Review #1 — 2026-10-29
**Result:** PASS (after reviewer text fixes; open items below are non-blocking suggestions)

Scope: FEAT-185 files only (EconomyGuide.tsx, GuideLink.tsx, guideSections.ts, ParamHint.tsx, paramHints.ts,
EconomyPage.tsx, hint wiring in EconomyTick / RegionEconomyEditor / RegionBankPanel / EconomySettings /
EconomyGoodsGroups / EconomyTemplates, CommonComponents/InfoTooltip.tsx). FEAT-183/184 diffs not reviewed.

#### Fact check (vs econ_sim.py, econ_merchant.py, econ_bank.py, econ_core.py, econ_tick.py, economy_*crud.py, schemas.py, migration 028)
Verified correct: all 59 sim-param defaults/bounds in EconomyTick.tsx = SimParams / ECON_SIM_PARAM_BOUNDS; templates
(population, tax), 12 groups, chains (weapons 3 ore, potions 2 herbs), food 300/1000, 7 days, base 2 → Capital norm
52 500, 15 000/day; price curve (×1.55 / ×0.65 / ×0.5 at 3×, clamp 0.5–3, spoil above 3 norms); production
(stability <60, hunger −50 %, price response +30 %); tax/wage/reserve formula (1/8 release, 7 days of tax); stability
(85, −100/−15/−2 per pp over 12 %/−10, up 0.08 / down 0.25); per-day conversions (68 %, 28 %, 19 %); merchant rules
(bid cap 50 %, charisma 50 %, wholesale ½, cash target 2×, cap 3×, purse 5 %); bank rates/terms/caps (750 at lvl 1,
3 000 at lvl 10), debt cap 2× principal, collection order, reserve 20 %, cover 1.25, floor 0.2; schedule UTC 00/06/12/18,
no catch-up, banks after regions; fill/fund need settings+emit; settings TTL 60 s; country tax 0–50 %; field ranges.

Inaccuracies found and **fixed by reviewer** (text only):
| # | File | Was | Correct |
|---|------|-----|---------|
| 1 | EconomyGuide.tsx step 3 | implied assigning a template sets population/tax | first assignment copies goods only; population via field or fill «Население из шаблона»; tax via «Применить шаблон» (`update_region`, `apply_template`) |
| 2 | EconomyGuide.tsx step 4 | fill «копирует товары» | it re-copies template goods, resetting manual production edits (`fill_regions` → `_apply_template_goods` always); added the «Население из шаблона» checkbox (default off — regions with 0 are skipped); template is «Портовый», not «Порт» |
| 3 | EconomyGuide.tsx step 6 | capital always taken | only with the seed-capital checkbox (`seed_capital`) |
| 4 | EconomyGuide.tsx «Банки» | «нет свободных денег — проценты не начисляются» | short → paid pro rata, rest forfeited (`prorata` in `bank_step`) |
| 5 | EconomyGuide.tsx recipe «Голод» | fill as a fix for a raised region production | fill resets production to the template — warned |
| 6 | paramHints.ts prosp_w_liq | «при сумме ≈1 все регионы богатые, роскошь до ×1,5» | the B4 problem had sum 0.85 too; cause = liq weight with 7-day full purse — reworded |
| 7 | paramHints.ts bank_transfer_fee_min | «0 — маленький перевод бесплатен» | fee = max(min, ceil(amount×rate)) → ≥1 whenever rate>0 |
| 8 | paramHints.ts bank_start_capital | checkbox «Взять стартовый капитал» | real labels «Взять стартовый капитал из казны» / «Стартовый капитал из казны» |
| 9 | paramHints.ts region_population def | «из шаблона» | 0 for a new region; template value only via fill + checkbox |
| 10 | paramHints.ts region_tax def | «из шаблона» | 10 % for a new region; template rate via «Применить шаблон» |
| 11 | paramHints.ts region_template | «смена шаблона товары не меняет» | first assignment to a region without goods copies them |
| 12 | paramHints.ts template_production | copied on assignment / apply | also by «Заполнить регионы по шаблонам» |
| 13 | paramHints.ts group_norm_days def | «сырьё 14» | magic materials (raw) = 21 |
| 14 | EconomyPage.tsx templates intro | region gets population/tax on assignment | goods on assignment, tax by apply, population by fill checkbox |

#### Checklist statuses vs API (live, local DB)
Templated 5/27, simulated 5, purses 5/5, treasury ≥ reserve 1/5 (region 10: 1112 ≥ 1064), merchants 3 / living 2 /
funded 2/2 (npc 429 = dungeon), banks open 2, bankers 0 in both → «Банкиров нет в 2», last run 5/5 done — all match
`/regions`, `/merchants`, `/banks`, `/sim`.

#### Open (non-blocking, for a developer if desired)
- Step 4 is «Готово» while «Казна не ниже резерва» is 1 of 5 — tone ignores treasuries (they legitimately sit below
  reserve after a bank seed); consider `info`/`warn` when reserve count < simulated.
- Banks step «Без своих денег» uses `own_funds <= 0`; `lendable` (free money) is in the payload and is what really
  blocks interest/loans.
- `totals.debtors` counts overdue loans, labelled «Должников».
- Two intro lines while a region editor is open (tab + editor): acceptable — different scope (all regions vs one
  region, editor line points to the «?»); optional polish: hide the tab intro while the editor is open.

#### Automated Check Results
- [x] `npx tsc --noEmit` — PASS (clean, before and after fixes)
- [x] `vite build` — PASS (build=0)
- [ ] `py_compile` / `pytest` — N/A (frontend only)
- [x] Live verification (claude-in-chrome) — PASS

#### Live Verification Results
- Page: `http://localhost/admin/economy` as admin (local). «Как настроить» first and default; 8 steps with statuses.
- Step buttons switch tabs (e.g. «Открыть «Банки»»); TOC chips and «Если «Расхождение»» scroll to anchors; intro
  «Подробнее в гайде →» returns to the guide at its section.
- «?» hints: 59 on «Пересчёт», 46 in the region editor; mouse click opens, outside tap closes.
- 360 px (iframe): no horizontal overflow; touch tap toggles hints; bubbles at top/middle/bottom fields stay within
  the viewport (8 px edges). InfoTooltip change is backward compatible (default `icon='info'`; Houses users unaffected).
- Console: zero errors across all 12 tabs.
- Rules: TS only, Tailwind + design-system classes, no React.FC, Russian errors (per-source error lines in checklist).


## 6. Logging
```
[LOG] 2026-10-29 — PM: фича создана, пользователь одобрил план гайда («Да, делай»)
[LOG] 2026-10-29 — Frontend Developer: F1 готова — вкладка «Как настроить» (чек-лист из 8 шагов со статусами, «Как устроена экономика» со схемой денег, 6 рецептов), строки «что здесь» на 9 вкладках; ссылки в гайд для F2 — guideSections.ts (useOpenGuide) и GuideLink.tsx (GuideLink/GuideIntro); tsc и build чистые
[LOG] 2026-10-29 — Frontend Dev (F2): подсказки «?» у всех параметров «Пересчёт» (59), редактора и банка региона, настроек валюты, групп товаров и шаблонов; тексты в paramHints.ts, умолчания/границы «Пересчёта» берутся из определений параметров; у InfoTooltip добавлен значок «?» и удержание в пределах экрана по вертикали; строки «что здесь» в «Пересчёт», «Настройки» и редакторе региона со ссылкой в гайд. tsc чисто по моим файлам (ошибка в EconomyGuide.tsx — F1), build=0
[LOG] 2026-10-29 — Reviewer: проверка завершена, PASS; исправлено 14 неточностей в текстах гайда и подсказок (население/налог при назначении шаблона, «Заполнить» сбрасывает производство, проценты банка при нехватке, мин. комиссия и др.); tsc/build чистые, живая проверка в т.ч. на 360px, ошибок в консоли нет
```

## 7. Completion Summary

**Сделано (2026-10-29):** вкладка «Как настроить» (первая в «Экономике»): живой чек-лист из 8 шагов со статусами
из имеющихся API и кнопками перехода, «Как устроена экономика» со схемой движения марок, 6 рецептов «Что делать,
если…»; строки «что здесь» на всех вкладках; «?» у всех 59 параметров «Пересчёта», в редакторе региона, банке
региона, настройках валюты, товарах и шаблонах (тексты в `paramHints.ts`). Ревью PASS: ревьюер исправил 14 неточностей
в текстах, сверив их с кодом; PM довёл статусы чек-листа (шаг «Заполнить» готов только при казне на резерве во всех
регионах, банки проверяются по свободным деньгам, «Просроченных займов» вместо «Должников»). Только фронтенд.
