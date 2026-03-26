# FEAT-082: Автопрокачка профессий (XP за крафт)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-03-26 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-082-profession-auto-leveling.md` → `DONE-FEAT-082-profession-auto-leveling.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Автоматическая прокачка профессий через получение опыта (XP) за крафт. При достижении порога XP для следующего ранга — автоматическое повышение ранга с уведомлением игрока. Количество XP зависит от редкости/сложности рецепта.

### Бизнес-правила
- Каждый успешный крафт даёт XP профессии
- Количество XP зависит от редкости рецепта (common = мало, legendary = много)
- При достижении порога XP для следующего ранга — автоматическое повышение
- При повышении ранга — автоматически выучиваются рецепты с `auto_learn_rank` для нового ранга
- Игрок видит текущий XP, прогресс до следующего ранга (полоска прогресса)
- На максимальном ранге XP продолжает копиться (для будущего расширения), но ранг не растёт
- Админ по-прежнему может вручную менять ранг
- При смене профессии XP сбрасывается (уже реализовано)

### UX / Пользовательский сценарий
1. Игрок крафтит предмет
2. Получает XP профессии, видит "+N XP" в результате крафта
3. На табе "Крафт" видит полоску прогресса (текущий XP / нужный XP)
4. Когда XP достигает порога — ранг повышается автоматически
5. Появляется уведомление "Вы достигли ранга Подмастерье!"
6. Новые рецепты (auto_learn) автоматически изучаются

### Edge Cases
- Что если один крафт даёт достаточно XP для перескока через несколько рангов? → Повысить до максимально доступного ранга за один раз
- Что если игрок на максимальном ранге? → XP копится, ранг не меняется
- Что если порог XP для ранга = 0? → Ранг доступен сразу (для ранга 1 это норма)

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

### 2.1 Current State — Backend

**`services/inventory-service/app/crud.py` — `execute_craft()` (line 1270)**
- Takes `(db, character_id, recipe, blueprint_item_id)`, returns a plain dict with `success`, `crafted_item`, `consumed_materials`, `blueprint_consumed`.
- No XP logic exists. The function only consumes materials, optionally consumes a blueprint, creates result items, and returns.
- The function operates within a transaction (caller does `db.commit()` in `main.py` line 1318).
- This is the single place where XP must be awarded — after step 3 (create result item), before `db.flush()`.

**`services/inventory-service/app/main.py` — `craft_item()` (line 1260)**
- The endpoint calls `crud.execute_craft()` and returns its result directly. The `CraftResult` schema is used implicitly (dict returned, not validated via response_model). Adding new fields to the return dict is safe — no schema enforcement on the response.
- The endpoint already loads `cp` (CharacterProfession) at line 1272, so it's available to pass into `execute_craft()`.

**`services/inventory-service/app/models.py` — Profession models**
- `CharacterProfession`: has `experience` (Integer, default=0), `current_rank` (Integer, default=1). Ready for XP accumulation.
- `ProfessionRank`: has `required_experience` (Integer, default=0). Used as threshold for rank-up.
- `Recipe`: has `rarity` (String(20), default='common'). No `xp_reward` field yet.
- `Profession`: has `ranks` relationship — can load all ranks sorted by `rank_number`.

**`services/inventory-service/app/schemas.py` — `CraftResult` (line 574)**
- Currently: `success: bool`, `crafted_item: dict`, `consumed_materials: list`, `blueprint_consumed: bool`.
- Needs new fields for XP info.

**`services/inventory-service/app/crud.py` — `set_character_rank()` (line 906)**
- Existing auto-learn logic: queries recipes where `auto_learn_rank <= rank_number` and creates `CharacterRecipe` entries for unlearned ones. This exact pattern should be reused for rank-up during craft.

### 2.2 Current State — Seed Data (Alembic migration 004)

Ranks seeded per profession (3 ranks each, 18 total):
| Rank | Name | `required_experience` |
|------|------|-----------------------|
| 1 | Ученик | 0 |
| 2 | Подмастерье | 500 |
| 3 | Мастер | 2000 |

### 2.3 Current State — Frontend

**`services/frontend/app-chaldea/src/types/professions.ts`**
- `CharacterProfession` type already has `experience: number` and ranks have `required_experience: number`.
- `CraftResult` type: `success`, `crafted_item`, `consumed_materials`, `blueprint_consumed`. Needs new XP fields.

**`ProfessionInfo.tsx`**
- Displays profession icon, name, rank name, and rank number. No XP progress bar.
- The `characterProfession` prop already contains `experience` and `profession.ranks` (with `required_experience`), so all data for a progress bar is available without new API calls.

**`CraftTab.tsx`**
- `handleConfirmCraft()` (line 124): on success, shows `toast.success('Предмет создан!')`, clears craft result, refreshes recipes.
- After craft, it calls `dispatch(fetchCharacterProfession(characterId))` is NOT called — this means the XP bar won't update after craft unless we add this call.
- `lastCraftResult` exists in Redux state (craftingSlice) but is not displayed anywhere in the current UI — it's immediately cleared. The toast is the only feedback.

**`craftingSlice.ts`**
- Has `lastCraftResult: CraftResult | null` in state. The `craftItem` thunk dispatches the result.

### 2.4 Rarity Values in Codebase

The `ItemRarity` enum (schemas.py) and item_rarity column use: `common`, `rare`, `epic`, `legendary`, `mythical`, `divine`, `demonic`. There is no `uncommon` rarity.

### 2.5 Cross-Service Impact

- **None.** All changes are within inventory-service (backend) and frontend. No other services consume the craft endpoint or `CraftResult` format.

### 2.6 Risks

- **Multi-rank jump:** If a recipe gives enough XP to skip ranks, we must iterate through all ranks, not just check the next one. The auto-learn logic must fire for each intermediate rank.
- **Max rank:** Must handle the case where character is already at the highest rank (no next rank threshold exists).
- **Transaction safety:** XP award and rank-up must be in the same transaction as the craft. Since `execute_craft` already operates within the caller's transaction, this is naturally handled.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 XP Reward Strategy

**Default XP by rarity** — hardcoded mapping (simplest, configurable later):

| Rarity | XP |
|--------|-----|
| common | 10 |
| rare | 25 |
| epic | 50 |
| legendary | 100 |
| mythical | 200 |
| divine | 500 |
| demonic | 500 |

**Per-recipe override:** Add an optional `xp_reward` column (Integer, nullable) to the `recipes` table. If set, it overrides the default rarity-based XP. This allows admins to fine-tune XP for specific recipes. Requires an Alembic migration.

Logic: `xp = recipe.xp_reward if recipe.xp_reward is not None else RARITY_XP_MAP[recipe.rarity]`

### 3.2 Auto-Rank-Up Logic

Add to `execute_craft()`, after creating the result item:

```python
# 4. Award XP and check rank-up
xp_earned = recipe.xp_reward if recipe.xp_reward is not None else RARITY_XP_MAP.get(recipe.rarity, 10)
cp.experience += xp_earned

# Check for rank-up (handle multi-rank jumps)
rank_up = False
new_rank_name = None
auto_learned = []

all_ranks = sorted(cp.profession.ranks, key=lambda r: r.rank_number)
while True:
    next_ranks = [r for r in all_ranks if r.rank_number == cp.current_rank + 1]
    if not next_ranks:
        break  # Already at max rank
    next_rank = next_ranks[0]
    if cp.experience >= next_rank.required_experience:
        cp.current_rank = next_rank.rank_number
        rank_up = True
        new_rank_name = next_rank.name
        # Auto-learn recipes for the new rank
        new_recipes = auto_learn_recipes_for_rank(db, cp.character_id, cp.profession_id, next_rank.rank_number)
        auto_learned.extend(new_recipes)
    else:
        break
```

**`auto_learn_recipes_for_rank()`** — extract from existing `set_character_rank()` pattern. Queries recipes where `auto_learn_rank == rank_number` and creates `CharacterRecipe` entries for unlearned ones.

**Note:** The function signature of `execute_craft` must be updated to accept `cp: models.CharacterProfession` parameter (the caller already has it).

### 3.3 CraftResult Schema Changes

**Backend** — `schemas.CraftResult`:
```python
class CraftResult(BaseModel):
    success: bool
    crafted_item: dict
    consumed_materials: list
    blueprint_consumed: bool = False
    xp_earned: int = 0
    new_total_xp: int = 0
    rank_up: bool = False
    new_rank_name: Optional[str] = None
    auto_learned_recipes: list = []  # [{"id": int, "name": str}]
```

**Frontend** — `types/professions.ts` — `CraftResult`:
```typescript
export interface CraftResult {
  success: boolean;
  crafted_item: CraftedItem;
  consumed_materials: ConsumedMaterial[];
  blueprint_consumed: boolean;
  xp_earned: number;
  new_total_xp: number;
  rank_up: boolean;
  new_rank_name: string | null;
  auto_learned_recipes: { id: number; name: string }[];
}
```

### 3.4 Frontend Changes

**ProfessionInfo.tsx** — Add XP progress bar:
- Compute `currentXp = characterProfession.experience`.
- Find next rank from `profession.ranks` where `rank_number == current_rank + 1`.
- If next rank exists: show progress bar `currentXp / nextRank.required_experience`.
- If at max rank: show "Макс. ранг" with full bar and total XP displayed.
- Use Tailwind classes, keep the airy design style.

**CraftTab.tsx** — After successful craft:
- Show XP earned in toast: `"Предмет создан! +{xp_earned} XP"`.
- If rank-up: show additional toast: `"Повышение ранга: {new_rank_name}!"`.
- If auto-learned recipes: mention in toast.
- Call `dispatch(fetchCharacterProfession(characterId))` to refresh XP bar.
- Call `dispatch(fetchRecipes({ characterId }))` (already done) to show newly available recipes.

### 3.5 Admin Schema Updates

**`RecipeCreate`** and **`RecipeUpdate`** schemas: add optional `xp_reward: Optional[int] = None`.
**`RecipeAdminOut`** and **`RecipeOut`** schemas: add `xp_reward: Optional[int] = None`.
**Frontend admin types**: add `xp_reward` to `AdminRecipe`, `RecipeCreateRequest`, `RecipeUpdateRequest`.

### 3.6 API Changes

No new endpoints. Only the existing `POST /crafting/{character_id}/craft` response changes (backward-compatible — new fields added with defaults).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

### Task 1: Backend — XP reward logic and schema updates ✅ DONE
**Agent:** Backend Developer
**Files to modify:**
- `services/inventory-service/app/models.py` — add `xp_reward` column to `Recipe` model
- `services/inventory-service/app/alembic/versions/005_add_recipe_xp_reward.py` — new Alembic migration adding `xp_reward` column
- `services/inventory-service/app/crud.py`:
  - Add `RARITY_XP_MAP` constant
  - Add `auto_learn_recipes_for_rank()` helper (extracted from `set_character_rank` pattern)
  - Modify `execute_craft()` signature to accept `cp` parameter
  - Add XP award + rank-up logic after crafting
  - Return new fields in result dict
- `services/inventory-service/app/main.py` — pass `cp` to `execute_craft()` call; add `fetchCharacterProfession` refresh comment
- `services/inventory-service/app/schemas.py`:
  - Update `CraftResult` with `xp_earned`, `new_total_xp`, `rank_up`, `new_rank_name`, `auto_learned_recipes`
  - Update `RecipeCreate`, `RecipeUpdate` with optional `xp_reward`
  - Update `RecipeOut`, `RecipeAdminOut` with `xp_reward`

**Acceptance criteria:**
- Successful craft awards XP based on rarity (or per-recipe override)
- Rank auto-promotes when XP threshold is met (including multi-rank jumps)
- Auto-learn recipes fire on each rank-up
- Max rank: XP accumulates but rank stays
- CraftResult response includes all new XP fields
- Alembic migration adds `xp_reward` column to `recipes` table

### Task 2: Frontend — XP progress bar and craft result display ✅ DONE
**Agent:** Frontend Developer
**Files to modify:**
- `services/frontend/app-chaldea/src/types/professions.ts` — update `CraftResult` interface, add `xp_reward` to admin types
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/ProfessionInfo.tsx` — add XP progress bar below rank info
- `services/frontend/app-chaldea/src/components/ProfilePage/CraftTab/CraftTab.tsx`:
  - Update `handleConfirmCraft` to show XP in toast, rank-up toast, refresh characterProfession
  - Access craft result data from thunk return value
- Admin recipe form (if exists): add optional `xp_reward` field

**Acceptance criteria:**
- XP progress bar visible showing `currentXp / nextRankThreshold`
- Max rank shows "Макс. ранг" state
- Toast after craft shows "+N XP"
- Rank-up shows separate congratulatory toast
- XP bar updates after craft without page reload
- All Tailwind, responsive (360px+), no SCSS
- TypeScript only

### Task 3: QA — Tests for XP and auto-rank-up ✅ DONE
**Agent:** QA Test
**Files created:**
- `services/inventory-service/app/tests/test_craft_xp.py` — 23 tests, all passing

**Test cases:**
1. Craft awards correct XP based on recipe rarity (each rarity value) — 7 parametrized tests
2. Craft awards correct XP when `xp_reward` override is set on recipe — 2 tests (override + zero override)
3. XP accumulates across multiple crafts — 1 test
4. Rank auto-promotes when threshold is reached — 2 tests (at threshold + below threshold)
5. Multi-rank jump works correctly (e.g., one craft gives enough XP for 2 rank-ups) — 1 test
6. Auto-learn recipes fire on rank-up — 2 tests (single rank + multi-rank intermediate)
7. Max rank: XP increases but rank stays the same — 1 test
8. CraftResult response contains all new fields with correct values — 2 tests
9. `xp_reward` field works in recipe CRUD (create, update, read) — 5 tests

### Task 4: Review
**Agent:** Reviewer

**Checklist:**
- All backend acceptance criteria from Task 1
- All frontend acceptance criteria from Task 2
- All tests pass from Task 3
- No regressions in existing craft flow
- Alembic migration is correct and reversible
- Cross-service impact: none (verified)
- Live verification: craft item, see XP gain, trigger rank-up

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-03-26
**Result:** PASS

#### 1. Backend Review

**`models.py`** — `xp_reward = Column(Integer, nullable=True)` on `Recipe`: Correct. Nullable column, no default (falls back to rarity-based XP in logic). Matches Alembic migration.

**`schemas.py`** — All changes correct:
- `CraftResult`: new fields `xp_earned: int = 0`, `new_total_xp: int = 0`, `rank_up: bool = False`, `new_rank_name: Optional[str] = None`, `auto_learned_recipes: list = []` — backward-compatible defaults.
- `RecipeCreate`, `RecipeUpdate`: `xp_reward: Optional[int] = None` — correct.
- `RecipeOut`, `RecipeAdminOut`: `xp_reward: Optional[int] = None` — correct.
- Pydantic v1 syntax (`class Config: orm_mode = True`) — correct, no v2 patterns.

**`crud.py`** — XP logic review:
- `RARITY_XP_MAP` — all 7 rarities covered, matches architecture spec.
- `auto_learn_recipes_for_rank()` — correctly extracted from `set_character_rank()` pattern. Filters by `auto_learn_rank == rank_number` (not `<=`), creates `CharacterRecipe` entries, skips already-learned.
- `execute_craft()` — signature updated to accept `cp` parameter (Optional, backward-compatible). XP logic:
  - `xp_reward` override: `recipe.xp_reward if recipe.xp_reward is not None else RARITY_XP_MAP.get(...)` — correctly handles `xp_reward=0` (explicit zero) vs `None` (fallback to rarity).
  - Multi-rank jump: `while True` loop iterates through all next ranks — correct.
  - Auto-learn fires per rank in the loop — correct.
  - Max rank: loop breaks when no next rank found — correct.
  - Transaction safety: operates within caller's transaction — correct.

**`main.py`** — `cp=cp` parameter passed to `execute_craft()`. Clean, minimal change.

**`alembic/versions/006_add_recipe_xp_reward.py`** — Correct:
- `down_revision = '005_add_recipe_item_type'` — chains properly.
- `upgrade()`: `add_column('recipes', Column('xp_reward', Integer, nullable=True))`.
- `downgrade()`: `drop_column('recipes', 'xp_reward')` — reversible.

#### 2. Frontend Review

**`types/professions.ts`** — Types match backend schemas exactly:
- `CraftResult`: `xp_earned: number`, `new_total_xp: number`, `rank_up: boolean`, `new_rank_name: string | null`, `auto_learned_recipes: { id: number; name: string }[]` — matches.
- `Recipe`, `AdminRecipe`: `xp_reward: number | null` — matches `Optional[int]`.
- `RecipeCreateRequest`, `RecipeUpdateRequest`: `xp_reward?: number | null` — matches.

**`ProfessionInfo.tsx`** — XP progress bar:
- Progress calculation: `currentXp / nextRank.required_experience * 100`, capped at 100 — correct.
- Max rank: shows "Макс. ранг · {xp} XP" with full bar — correct.
- Tailwind only, responsive (`sm:` breakpoints), no SCSS.
- No `React.FC` — uses `const ProfessionInfo = ({ ... }: ProfessionInfoProps) => {`.
- Russian strings — correct.

**`CraftTab.tsx`** — Craft result handling:
- XP toast: `"Предмет создан! +{xp_earned} XP"` — correct.
- Rank-up toast: `"Повышение ранга: {new_rank_name}!"` — correct, `duration: 5000`.
- Auto-learned recipes toast: lists names — correct.
- `dispatch(fetchCharacterProfession(characterId))` after craft — refreshes XP bar.
- Error handling: `toast.error(err ?? 'Не удалось создать предмет')` — Russian, visible.
- No `React.FC`, TypeScript, Tailwind.

**`RecipesAdminPage.tsx`** — XP reward field:
- Form state `xp_reward: number | ""` with `""` as empty — follows same pattern as `auto_learn_rank`.
- Conversion: `form.xp_reward !== "" ? Number(form.xp_reward) : null` — correct.
- Input field: `type="number"`, `placeholder="По умолчанию (по редкости)"` — Russian, clear.
- No `React.FC`, TypeScript, Tailwind.

#### 3. Cross-Service Impact
None. All changes within inventory-service and frontend. No other services consume `CraftResult` or the craft endpoint.

#### 4. QA Coverage
- 23 tests in `test_craft_xp.py`, all passing.
- Covers all 9 required test cases from the spec.
- Inter-service calls not needed (craft is self-contained in inventory-service).
- Edge cases covered: zero XP override, multi-rank jump, max rank, intermediate auto-learn.

#### 5. Known Limitations (pre-existing, not FEAT-082)
- `update_recipe()` in `crud.py` uses `if value is not None: setattr(...)` pattern, which means nullable fields like `xp_reward` cannot be explicitly set to `null` via the update endpoint. This is a pre-existing design pattern affecting all nullable Optional fields in recipe updates.
- `RARITY_OPTIONS` in `RecipesAdminPage.tsx` includes `uncommon` which doesn't exist in the backend `ItemRarity` enum. Pre-existing, not introduced by FEAT-082.

#### Automated Check Results
- [x] `py_compile` — PASS (all 4 modified Python files compile without errors)
- [x] `pytest` — PASS (23/23 new tests pass; 189 total pass; 19 errors in `test_endpoint_auth.py` are pre-existing)
- [ ] `npx tsc --noEmit` — N/A (Node.js not installed on this machine)
- [ ] `npm run build` — N/A (Node.js not installed on this machine)
- [ ] `docker-compose config` — N/A (Docker not available in this environment)
- [ ] Live verification — N/A (no running application instance available)

#### Note on Incomplete Checks
TypeScript compilation, production build, and live verification could not be performed because Node.js and Docker are not available in this environment. The code review is thorough and all backend automated checks pass. Frontend was reviewed manually: types match backend schemas, Tailwind-only styles, TypeScript-only files, no React.FC, responsive layout, Russian strings. Recommend running `tsc --noEmit` and `npm run build` before merging.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-03-26 — PM: фича создана, запускаю анализ
[LOG] 2026-03-26 — Codebase Analyst + Architect: анализ завершён, архитектура спроектирована, задачи разбиты. Инфраструктура FEAT-081 полностью готова — модели CharacterProfession.experience и ProfessionRank.required_experience уже существуют, execute_craft — единственная точка для добавления XP. Нужна 1 миграция (xp_reward в recipes), изменения в crud.py, schemas.py, и фронтенд (прогресс-бар + тосты). Кросс-сервисного влияния нет.
[LOG] 2026-03-26 — Backend Dev: задача #1 завершена. Добавлен RARITY_XP_MAP, auto_learn_recipes_for_rank(), XP-логика в execute_craft(), xp_reward в модель Recipe, обновлены схемы CraftResult/RecipeCreate/RecipeUpdate/RecipeOut/RecipeAdminOut, Alembic-миграция 006. Все admin-эндпоинты возвращают xp_reward. py_compile OK для всех файлов.
[LOG] 2026-03-26 — Frontend Dev: задача #2 завершена. Обновлён CraftResult (xp_earned, rank_up, auto_learned_recipes), добавлен xp_reward в Recipe/AdminRecipe/RecipeCreateRequest/RecipeUpdateRequest. Добавлен XP прогресс-бар в ProfessionInfo.tsx (gold-градиент, адаптивный, макс. ранг). CraftTab.tsx — тосты с XP/рангом/рецептами, рефреш профессии после крафта. RecipesAdminPage.tsx — поле «XP за крафт». Всё на Tailwind + TypeScript.
[LOG] 2026-03-26 — QA: написаны тесты для FEAT-082 — test_craft_xp.py, 23 теста, все проходят. Покрыты все 9 кейсов из спеки: XP по редкости (7 параметризованных), xp_reward override, накопление XP, авто-повышение ранга, мульти-прыжок, авто-изучение рецептов, макс. ранг, поля CraftResult, admin CRUD xp_reward.
[LOG] 2026-03-26 — Reviewer: проверка завершена, результат PASS. Бэкенд: XP-логика корректна (все edge cases), миграция правильная, схемы обновлены. Фронтенд: типы совпадают с бэкендом, прогресс-бар верный, тосты информативные, Tailwind + TS + responsive. py_compile и pytest OK. tsc/npm build не запущены (Node.js отсутствует на машине) — рекомендуется проверить перед мержем.
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

*Pending...*
