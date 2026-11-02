# FEAT-195: Софт- и хард-кап характеристик

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-02 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Сейчас прокачка характеристик выше 100 ничем не ограничена — каждая единица даёт полный эффект. Вводим убывающую отдачу: до 100 — полный эффект, от 100 до 200 — половина, выше 200 — четверть.

### Бизнес-правила
- **Кап:** эффективное значение стата `eff(x)`:
  - `x ≤ 100` → `x`;
  - `100 < x ≤ 200` → `100 + (x − 100) × 0.5`;
  - `x > 200` → `150 + (x − 200) × 0.25`.
  Пример: 250 → 162.5; 530 → 232.5. Само число стата (что видно в профиле) не меняется — режется только то, что оно даёт.
- **Считается от суммы всего:** вложенные очки + снаряжение (включая заточку/камни) + еда/сытость + перки + баффы в бою. Кап применяется к итоговой сумме, а не к каждому источнику отдельно.
- **Все статы:** сила, ловкость, интеллект, живучесть (endurance), удача, харизма, и очки ресурсов — здоровье, мана, энергия, выносливость (stamina).
- **Везде, где стат во что-то превращается:** производные (сопротивления, уклонение, шанс крита, сопротивление эффектам, максимум здоровья/маны/энергии/выносливости), урон от основного стата в бою, инициатива (очерёдность ходов), бонус удачи к попаданию/эффектам, скидка харизмы, проверки статов в подземельях, баффы, меняющие статы в бою.
- **Исправление 1:** сила/ловкость/интеллект/живучесть/удача со снаряжения теперь тоже дают производные (сопротивления, уклонение, крит), как уже дают вложенные очки и перки.
- **Исправление 2:** удача учитывается в шансе крита один раз (сейчас — дважды: в сохранённом крите и ещё раз в бою).
- **Харизма:** скидка у торговцев = `eff(харизма) × 0.1 %` (было 0.2 % за единицу с потолком 50 % при 250). Потолок 50 % как защитный оставить (недостижим на практике). 530 харизмы → 23.25 %.
- Уже прокачанные персонажи на проде с статами выше 100 ослабнут — это нормально (до беты).

### UX / Пользовательский сценарий
1. Игрок вкладывает очки в силу выше 100 — число силы растёт как раньше, но прирост сопротивлений/урона за единицу вдвое меньше; выше 200 — вчетверо.
2. В профиле производные значения (сопротивления, уклонение, крит, макс. здоровье, урон, инициатива) показываются уже с учётом капа.
3. Подсказки/объяснения статов в профиле и при создании персонажа упоминают кап (до 100 — полностью, 100–200 — 50 %, выше 200 — 25 %).

### Edge Cases
- Бафф/проклятие в бою переводит стат через порог 100 или 200 — прирост считается как `eff(итог) − eff(до)`.
- Снятие предмета / истечение еды / отзыв перка — производные пересчитываются так, чтобы не осталось «хвостов» (снятие ровно отменяет надевание).
- Отрицательные модификаторы (стат ниже 0) — `eff` для x ≤ 100 линеен, отрицательные значения не ломаются.
- Существующие персонажи на проде — производные должны быть пересчитаны один раз при выкатке (миграция/скрипт), с учётом снаряжения.

### Вопросы к пользователю (если есть)
- [x] Что считать → всё вместе (очки + шмот + еда + перки + баффы)
- [x] Какие статы → все, включая ресурсы
- [x] Где резать → везде
- [x] Ослабление текущих персонажей → нормально
- [x] Статы со шмота в производные → исправить
- [x] Удача в крите дважды → один раз
- [x] Харизма → 0.1 % за эффективную единицу, 530 → 23.25 %

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Pre-analysis by PM-launched Explore agent (2026-11-02). Architect must verify line numbers.

### Derived stats stored in DB (character-attributes-service) — accumulated as deltas
- Constants `character-attributes-service/app/constants.py`: STAT_BONUS_PER_POINT = 0.1; endurance mult 0.2; health ×10, mana ×10, energy ×5, stamina ×5.
- `compute_derived_stats` `crud.py:18-70`: max_health = 100 + health*10, max_mana = 75 + mana*10, max_energy = 50 + energy*5, max_stamina = 100 + stamina*5; dodge = 5 + (agility+luck)*0.1; crit = 20 + luck*0.1; crit_dmg = 125; res_physical/catting/crushing/piercing = strength*0.1; 8 magic res = intelligence*0.1; res_effects = endurance*0.2 + luck*0.1. Used by creation (`crud.py:73`), `recalculate_attributes` (`crud.py:191`, `main.py:1303`), admin `recalculate_all` (`main.py:1393`) — **resets item bonuses** (not gear-aware).
- Upgrade endpoint `main.py:646-770`: `+= points*b` deltas (resource multipliers hardcoded ~739-755).
- `_apply_modifiers_internal` `crud.py:539-634` (perks grant/revoke `crud.py:813/839`, admin perk edits `main.py:230/237/277`, `perk_evaluator.py:329/443/451`; `regen.py:373` satiety and `main.py:605` with `propagate_derived=False`).
- HTTP `POST /{id}/apply_modifiers` `main.py:847-1015` (all equipment): resources `max += Δ*mult`; primary stats raw only — **no derived propagation** (bug → fix 1).

### Item bonus flow
- `inventory-service/app/crud.py:638 build_modifiers_dict` → `inventory-service/app/main.py:1028 apply_modifiers_in_attributes_service`; call sites: equip 389/1355, unequip 742/1316/1462, sharpening 3145, gems 3431/3528.

### Use-time formulas (raw total stat)
- Damage `battle-service/app/battle_engine.py:146-150`: base = main_attr + damage + weapon; main attr by class (1 str, 2 agi, 3 int, line 96).
- Luck: `luck*0.1` to hit (`battle_engine.py:168-180`) and crit (line 186, double count → fix 2), effect-proc chance `battle-service/app/main.py:2772` used at 211/3571.
- Dodge roll uses stored dodge (`battle-service/app/main.py:3046`, `battle_engine.py:174`).
- Initiative `battle-service/app/redis_state.py:155-165`: agility + (strength+intelligence)*0.75, used `main.py:441`.
- Battle buffs `battle-service/app/buffs.py:466-512` re-derive primary-stat changes with the same constants (luck not included).
- Charisma `locations-service/app/econ_core.py:865` (byte-identical copies in character/inventory/dungeon `econ_core.py`, checked by `scripts/check_econ_copies.sh`; contract tests `tests/econ_contract_cases.py`): `min(charisma*0.2, 50)%`; used `locations-service/app/main.py:2767/2820/2914`, guild payout cap (FEAT-193).
- Dungeon checks `dungeon-service/app/gameplay.py:1635` (raw stat vs difficulty), minigames `dungeon-service/app/challenges.py:125-160`.
- skills-service, autobattle-service, passives.py — no stat scaling.

### Frontend (display mirrors)
- `CommonComponents/CharacterPassport/derived.ts:31-68` (dodge, crit, initiative), `ProfilePage/StatsTab/damage.ts`, `CreateCharacterPage/StepBlood/StatExplainer.tsx:31-40`, `ProfilePage/StatsTab/DerivedStatsSection.tsx`.

### Realistic max
- +10 stat points per level (`character-service/app/crud.py:1342`), start presets up to 40 → ~530 in one stat at level 50.

### Risks
- Delta accumulation makes capped derived stats path-dependent; needs a single source of truth (full gear-aware recompute from totals, or derive at read time).
- Cap function duplicated across services (Python + TS) — must be identical; consider a shared copy checked like econ_core.
- Prod data: one-time recompute for all characters.

### Architect verification (2026-11-02) — corrections and additions
Pointers above verified against the code; deltas worth knowing:
- **Food has the same bug as gear.** `apply_satiety` (`character-attributes-service/app/main.py:605`) and satiety expiry (`regen.py:373`) call `_apply_modifiers_internal(..., propagate_derived=False)` — food primary stats also never reach derived stats. They are the only `propagate_derived=False` callers.
- `_apply_modifiers_internal` is `crud.py:539-634`, derived propagation block `crud.py:610-631`; the HTTP `apply_modifiers` (`main.py:847-1015`) is a hand-copied twin of the same logic without that block.
- `compute_derived_stats` (`crud.py:18-70`) also **zeroes `damage`** (line 70) — so `/{id}/recalculate` (`main.py:1303`) and `/admin/recalculate_all` (`main.py:1393`) wipe item/perk/food damage as well as item resist/dodge/crit bonuses. `/{id}/recalculate` is called by the admin Mob/NPC stat editors (`frontend .../Admin/MobsPage/MobStatsEditor.tsx:142`, `AdminNpcsPage/NpcStatsEditor.tsx:320`) right after an admin `PUT /attributes/admin/{id}` (`main.py:1240`, raw absolute overwrite, no derived logic).
- Upgrade endpoint: derived block `main.py:700-760`; resource multipliers hardcoded 10/5/10/5 at 727-745.
- Column types (`models.py`): `max_*`, `current_*`, primaries, `damage`, `critical_damage` are `Integer`; `dodge`, `critical_hit_chance`, `res_*`, `vul_*` are `Float`.
- Battle: luck block is inside `compute_damage_with_rolls` (`battle_engine.py:166-186`): `luck_bonus = attacker_attr.luck*0.1` added to the hit roll (178) and the crit roll (186). `attacker_attr` there is the *buffed* copy; the effect-proc bonus at `battle-service/app/main.py:2772` uses the *unbuffed* `base_attacker_attributes`. `aggregate_modifiers` (`buffs.py:475-512`) propagates derived via `_DERIVED_PER_POINT` (`buffs.py:467-472`, linear, luck absent); it has no access to base values. Call sites: `main.py:2887, 2901, 3067, 3080, 3641, 3902, 3943`, `buffs.py:634` (`_is_stat_down`, sign only). Initiative `redis_state.py:155-166`, snapshot at `main.py:441`.
- Lancer passive (`passives.py:868-908`) steals dodge/crit (already derived values) — no cap involvement.
- Charisma constants `econ_core.py:734-735`, function `865-875`; contract rows `tests/econ_contract_cases.py:1042-1051` (×4 copies). `MAX_CHARISMA_DISCOUNT` also drives `market_bid` / `ask_discount_floor` (bid cap, FEAT-193 guild cap `character-service/app/econ_guild.py:161`) — these stay unchanged.
- Dungeon: `perform_stat_check` `dungeon-service/app/gameplay.py:1610-1641` and `_challenger` `gameplay.py:3223-3236` both read `cumulative_stats.get(stat, attrs.get(stat))` — the cap must apply only when the value is a primary attribute, never to a cumulative counter.
- Not conversions (out of scope, stay raw): perk/title attribute conditions (`character-service/app/crud.py:3295, 3464`, `character-attributes-service/app/crud.py` perk progress), equipment level/class requirements.
- Inventory has no "sum of everything a character wears" endpoint; `_worn_modifiers` (`inventory-service/app/main.py:351-368`) is the per-item pattern (slot sharpening + gems + durability + slot_type). `/inventory/internal/` is already blocked externally in both nginx configs.
- Extra frontend mirror: `Admin/MobsPage/AdminMobTemplateForm.tsx:102-138` (`computeDerivedStats` preview, also stale `damage: mainAttr`). Profile initiative is computed inline in `DerivedStatsSection.tsx:67` with tooltip at line 113. `StatExplainer.tsx:30-41` holds the per-point texts (charisma text is outdated: "не участвует").
- No other service writes primary attributes (`UPDATE character_attributes` elsewhere touches only `current_*`/experience).

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.1 The cap function (one definition, byte-identical copies)

```python
# stat_caps.py — canonical: services/character-attributes-service/app/stat_caps.py
SOFT_CAP = 100          # full effect up to here
HARD_CAP = 200          # half effect between SOFT_CAP and HARD_CAP
SOFT_RATE = 0.5
HARD_RATE = 0.25        # quarter effect above HARD_CAP

def effective_stat(value) -> float:
    """eff(x): x<=100 -> x; 100<x<=200 -> 100+(x-100)*0.5; x>200 -> 150+(x-200)*0.25.
    None/non-numeric -> 0.0. Negative values are linear (x)."""

def effective_delta(old, new) -> float:
    """eff(new) - eff(old) — what a change of a stat from old to new is worth."""
```
- Continuous, monotonic, piecewise-linear; eff(0)=0, eff(100)=100, eff(150)=125, eff(200)=150, eff(250)=162.5, eff(530)=232.5, eff(-10)=-10.
- For any integer stat, eff(x) is a multiple of 0.25 → exactly representable in binary floats; `m*eff(x)` for m ∈ {5, 10} is exact too.
- **Copies (byte-identical, sha256-checked):** `character-attributes-service/app/stat_caps.py` (canonical), `battle-service/app/stat_caps.py`, `dungeon-service/app/stat_caps.py`. `scripts/check_econ_copies.sh` gets a new `check_group "stat_caps" ...` (already run by CI, `ci.yml:124`). No shared package (repo convention, same as econ_core).
- **Charisma** lives in `econ_core.py` (4 byte-identical copies, Decimal maths). It gets its own Decimal implementation of the same piecewise function (`_effective_stat_dec`, same thresholds as constants) — econ_core stays self-contained (inventory/character services have no `stat_caps.py` and do not need one). Parity with `stat_caps.py` is pinned by the contract table: the charisma rows encode eff at every breakpoint, so both implementations are tested against the same numbers.
- **Frontend**: `src/utils/statCaps.ts` exports `effectiveStat(value: number): number` and the constants; a header comment points to the canonical Python file. Single TS copy used by every display helper.

### 3.2 Single source of truth for stored derived stats — decision: option (b) "delta of eff", enforced by one helper

Options considered:
- (a) store derived = flat + f(eff(total)) with a full gear/perk/food-aware recompute after every change — needs an inventory HTTP round-trip on every perk grant, food, upgrade, regen expiry; the flat part is not stored anywhere, so it must be re-collected from 3 sources each time. Heavy, couples hot paths to inventory availability.
- (c) derive at read time — every reader (battle snapshot, autobattle, dungeon, frontend, admin) would need to know the flat part separately; requires splitting every derived column into "flat" + "derived" (schema change in a shared table). Largest diff.
- **(b) chosen.** Invariant per derived field *d*: `stored_d = BASE_d + flat_d + Σ k·eff(P_total)` where `P_total` is the stored primary column (which already contains points + gear + sharpening/gems + perks + food). Every change of a primary stat from `old` to `new` adds `k·(eff(new) − eff(old))` to its derived fields; flat derived modifiers (item `res_fire +5`, perk `dodge +2`) are added as-is. Because eff is a function of the total, the sum of deltas telescopes: `Σ k·(eff(P_i+1) − eff(P_i)) = k·(eff(P_final) − eff(P_start))` — **path-independent**. Equip then unequip (with or without anything in between) returns exactly to the eff of the remaining total; worked example: str 80, equip +50 (→130: +3.5), upgrade +20 (→150: +1.0), unequip −50 (→100: −2.5) ⇒ net +2.0 = 0.1·(eff(100) − eff(80)). Order inside one modifiers dict is irrelevant (each primary is handled from its own old/new, flats are additive).
- **Resources** (`max_health/mana/energy/stamina`, Integer columns, no flat part exists — no item/perk key writes `max_*`): `max_R = BASE_R + floor(m_R · eff(R))`. Applied as a delta `floor(m·eff(new)) − floor(m·eff(old))` (telescopes exactly over integers), `current_R` moves by the same delta and is clamped to `[0, max_R]` — identical to today's behaviour below 100.
- Float derived fields keep accumulating (as today) — no rounding of the stored value; tests compare with `pytest.approx`.

**Mapping (unchanged coefficients, now through eff):**
| Primary | Derived |
|---|---|
| strength | 4 physical resists `+0.1·eff` |
| intelligence | 8 magical resists `+0.1·eff` |
| agility | dodge `+0.1·eff` |
| endurance | res_effects `+0.2·eff` |
| luck | dodge `+0.1·eff`, critical_hit_chance `+0.1·eff`, res_effects `+0.1·eff` |
| health / mana | max `+10·eff` (floor) |
| energy / stamina | max `+5·eff` (floor) |
| charisma | merchant discount `0.1 %·eff` (econ_core, not stored) |

**One code path.** New pure function in `character-attributes-service/app/crud.py`:
```python
def apply_attribute_modifiers(attr, modifiers: dict) -> None:
    """Adds `modifiers` to an already-locked CharacterAttributes row.
    Resources: value += Δ (clamped >= 0), max/current via floor(m*eff) delta.
    Primaries: value += Δ, derived += k*effective_delta(old, new).
    Everything else in the whitelist: plain add. No commit/flush."""
```
It replaces the three hand-written copies: the upgrade endpoint (`main.py:700-760` → builds a dict from `StatsUpgradeRequest` and calls the helper), `_apply_modifiers_internal` (keeps its signature minus `propagate_derived`; lock + helper + flush) and the HTTP `apply_modifiers` (lock + settle + helper). **Derived propagation is now unconditional**: gear (fix 1) and food (satiety apply/expiry) propagate exactly like points and perks. The `propagate_derived` parameter is removed (its only users were the two satiety calls; migration 006 does not use it).
`compute_derived_stats` (creation of a fresh row — no gear/perks/food yet) uses `effective_stat` for all formulas.

Not changed: admin `PUT /attributes/admin/{id}` stays an absolute raw overwrite (admin may set any field, including derived); the admin UIs already follow it with `/recalculate`, which becomes gear-aware (3.3) and therefore restores consistency.

### 3.3 Gear-aware rebuild (used once on prod, and by the existing recalculate endpoints)

New `crud.rebuild_derived_stats(db, attr, equipment_mods: dict) -> None` (absolute, idempotent):
1. Caller has locked the row and called `regen.settle_regen` first (expired food is already removed).
2. `flat = equipment_mods + Σ build_perk_modifiers_dict(perk) for every row of character_perks + (active satiety.modifiers or {})`, restricted to derived keys (`res_*` 13, `dodge`, `critical_hit_chance`).
3. Set: physical resists = `flat_f + 0.1·eff(strength)`; magical = `flat_f + 0.1·eff(intelligence)`; `dodge = 5 + flat + 0.1·eff(agility) + 0.1·eff(luck)`; `critical_hit_chance = 20 + flat + 0.1·eff(luck)`; `res_effects = flat + 0.2·eff(endurance) + 0.1·eff(luck)`; `max_R = BASE_R + floor(m·eff(R))`, `current_R = min(current_R, max_R)` (no top-up).
4. **Untouched:** all 10 primary columns (they are already totals), `damage`, `critical_damage`, all `vul_*`, experience, regen fields. (Fixes the "recalculate wipes item damage/resists" bug.)

`equipment_mods` comes from a new inventory endpoint (contract below). Usage:
- `POST /attributes/{id}/recalculate` (admin, `characters:update`) → one-id inventory call → rebuild. Inventory unreachable/non-200 → **502 "Не удалось получить снаряжение персонажа"**, nothing written.
- `POST /attributes/admin/recalculate_all` (admin, `characters:update`) → batches of 100 character_ids → one inventory call per batch → rebuild + commit per batch. A batch whose inventory call fails is skipped (not written) and reported. Response: `{"detail": str, "count": int, "skipped": [int]}` (count = rebuilt rows; `detail` kept for backward compatibility).
- **Prod rollout:** after deploy, PM calls `POST /attributes/admin/recalculate_all` once with an admin JWT (or via the VPS helper). Until it runs, the new eff-delta logic merely preserves each character's existing offset (no new drift is created); the rebuild is absolute, so whatever drift exists (gear/food never propagated, old recalculates that wiped item bonuses, pre-cap linear values) is erased in one pass. Idempotent — safe to re-run. Pre-beta: characters with stats > 100 lose effect, as approved.
- Why not an Alembic data migration: the rebuild needs inventory's `build_modifiers_dict` (sharpening, gems, durability, slot_type rules) — re-implementing that in SQL would be a second copy of the item maths, and calling inventory over HTTP from a migration at container start would fail-fast the service whenever inventory boots later.

### 3.4 Battle-service
- `battle_engine.compute_damage_with_rolls`: `base_stat = effective_stat(attacker_attr[main_attr])` (attacker_attr already contains buffs and passive deltas → cap is on the sum, as required). Hit roll: `chance + luck_proc_bonus(attacker_attr)`.
- **Luck double count (fix 2): drop the battle-time luck term from the crit roll**; crit = stored `critical_hit_chance` (+ buff deltas). Justification: the stored crit already contains `0.1·eff(luck)` from points, gear, perks and food and is exactly what the profile shows — dropping the battle-side term makes profile = battle without any read-time recomputation, and battle buffs to luck keep a crit effect because luck now propagates in `aggregate_modifiers` (below). The opposite choice would require removing luck from the stored crit, a schema-semantic change visible in every client.
- New helper in `battle_engine.py`: `LUCK_PROC_PER_POINT = 0.1`; `luck_proc_bonus(attrs) = LUCK_PROC_PER_POINT * effective_stat(attrs.get("luck", 0))`. Used for the hit roll and for `attacker_luck_bonus` at `main.py:2772`, which now reads the attacker's **buffed** luck (`apply_flat_modifiers(base, aggregate_modifiers(attacker_effects, base))`) — consistent with the hit roll.
- `buffs.aggregate_modifiers(effects, base_attributes: Optional[dict] = None)`: `_DERIVED_PER_POINT` gains `"luck": {"dodge": 0.1, "critical_hit_chance": 0.1, "res_effects": 0.1}`; when `base_attributes` is given, each derived contribution is `per_point · effective_delta(base[p], base[p] + Δp)`; when `None` (only `_is_stat_down`, which needs signs) the old linear per-point delta is used (sign-identical, since eff is monotonic). All 7 `main.py` call sites pass the base attrs they already hold.
- `redis_state.compute_initiative`: `eff(agility)·1.0 + (eff(strength) + eff(intelligence))·0.75`. Tie-break by raw agility unchanged.

### 3.5 Economy (charisma)
`econ_core.py` (4 copies): `CHARISMA_DISCOUNT_PER_POINT = Decimal("0.1")` (per **effective** point); `charisma_discount_pct(c) = min(eff_dec(c) * 0.1, 50)`, guards for None/bool/garbage/≤0 unchanged. `MAX_CHARISMA_DISCOUNT = 0.5` kept as the safety ceiling (reached only at eff=500, i.e. charisma 1600), so `market_bid`, `ask_discount_floor`, the FEAT-193 guild payout cap and `discounted_ask` clamp are numerically unchanged and still consistent (max discount ≤ 50 % ⇒ resale never profitable). Contract rows updated: 0→0, 3→0.3, 30→3, 100→10, 150→12.5, 200→15, 250→16.25, 530→23.25, 100000→50, garbage/None/negative→0. No caller changes (locations `main.py:2767/2820/2914` already pass raw charisma).

### 3.6 Dungeon-service
`perform_stat_check` and `_challenger`: if the stat name is one of the 10 primary attributes **and** it is not present in `cumulative_stats`, value = `floor(effective_stat(raw))`; cumulative counters stay raw. The returned/displayed `best_value` / `rolled` is the effective number (what was actually compared). Minigame parameters (`roll`, `lockpick_params`, `runes_params`, `mechanism_params`, `shield_params`) receive the effective value — no change inside `challenges.py`.

### 3.7 Frontend
- `src/utils/statCaps.ts` — `effectiveStat`, `STAT_SOFT_CAP`, `STAT_HARD_CAP`, plus `STAT_CAP_NOTE` (Russian: «Убывающая отдача: до 100 — полный эффект, от 100 до 200 — половина, выше 200 — четверть. Считается от суммы очков, снаряжения, еды, перков и баффов.»).
- `CharacterPassport/derived.ts` — all formulas through `effectiveStat` (max resources use `Math.floor(m·eff)`), initiative too.
- `ProfilePage/StatsTab/damage.ts` — `baseDamage = effectiveStat(mainAttr) + damage`.
- `ProfilePage/StatsTab/DerivedStatsSection.tsx` — initiative via `effectiveStat` (ideally reuse the passport helper), tooltip mentions the cap.
- `CreateCharacterPage/StepBlood/StatExplainer.tsx` — `STAT_EFFECTS` texts get the cap note; charisma text → «Скидка у торговцев: 0.1% за очко (с учётом убывающей отдачи).»
- `Admin/MobsPage/AdminMobTemplateForm.tsx` — preview formulas through `effectiveStat`; drop the stale `damage: mainAttr` (damage is a pure bonus since FEAT-167 → 0).
- Profile stat-upgrade area (`PrimaryStatsSection.tsx` or `StatDistributionPanel.tsx`) — one small hint line with `STAT_CAP_NOTE` (or `title` tooltip on the section header). Styling rules: these are Tailwind components already (FEAT-149) — if any touched component still imports SCSS, migrate it; mobile 360px+; no `React.FC`.
- No new API / Redux changes: stored values come from the backend already capped.

### API Contracts

#### `POST /inventory/internal/equipment-modifiers` (new, inventory-service)
**Auth:** `X-Internal-Token` (`verify_internal_token`); `/inventory/internal/` is blocked externally by both nginx configs — no nginx change.
**Request:**
```json
{ "character_ids": [12, 13] }
```
Validation: list of positive ints, 1..500 items, duplicates ignored → 422 otherwise.
**Response 200:**
```json
{ "modifiers": { "12": { "strength": 15, "res_fire": 4.0, "dodge": 1.5 }, "13": {} } }
```
Every requested id is present (empty dict = nothing equipped). Per character: sum over all `equipment_slots` with an item of `crud.build_modifiers_dict(item, enhancement_bonuses=get_enhancement_bonuses(slot), gem_items=..., current_durability=slot.current_durability, max_durability=item.max_durability, slot_type=slot.slot_type)` — exactly what equip applied (same as `_worn_modifiers`). Read-only.

#### `POST /attributes/{character_id}/recalculate` (changed behaviour, same contract)
Now gear/perk/food-aware (3.3). New error: 502 `{"detail": "Не удалось получить снаряжение персонажа"}` when inventory fails. 404 unchanged.

#### `POST /attributes/admin/recalculate_all` (changed behaviour)
Response `{"detail": "Recalculated N characters", "count": N, "skipped": [character_id, ...]}` (field `skipped` added).

#### `POST /attributes/{id}/upgrade`, `POST /attributes/{id}/apply_modifiers`, satiety, perks — contracts unchanged; only the derived arithmetic changes.

### Security Considerations
- New inventory endpoint: internal-token only, nginx-blocked, read-only, bounded list (≤500) — no user input reaches SQL except ints via ORM.
- Recalculate endpoints: unchanged auth (`require_permission("characters:update")`), no new permissions needed. No rate limiting beyond existing (admin-only).
- No secrets, no new env vars (`INVENTORY_SERVICE_URL` default already in attributes `config.py:10`; `INTERNAL_SERVICE_TOKEN` already set).

### DB Changes
None (no schema change, no Alembic migration). Data re-baseline via `recalculate_all` after deploy (3.3). Rollback: revert code and run `recalculate_all` again (old linear formula) — note the old recalculate is not gear-aware, so a rollback would leave item bonuses stripped until re-equip; acceptable pre-beta.

### Cross-service checks
- Battle reads stored `dodge`/`critical_hit_chance`/`res_*`/`max_*` — values just change magnitude, types unchanged. autobattle, skills-service: no stat scaling (verified).
- `character-service` presets/creation go through `POST /attributes/` → `compute_derived_stats` → capped (starting presets ≤ 40, so no visible change at creation).
- Perk/title attribute *conditions* and equipment requirements compare raw stats (the number on the profile) — intentionally unchanged.

### Data Flow Diagram
```
Equip/unequip/sharpen/gem/durability break:
  Frontend → nginx → inventory-service → POST attributes/{id}/apply_modifiers (internal)
           → crud.apply_attribute_modifiers: primary += Δ; derived += k*(eff(new)-eff(old)); flats += v → MySQL
Upgrade:   Frontend → attributes /{id}/upgrade → character-service deduct_points → apply_attribute_modifiers
Perk / food / food expiry: attributes-internal → _apply_modifiers_internal → apply_attribute_modifiers
Rebuild:   Admin → attributes /admin/recalculate_all → inventory /internal/equipment-modifiers (batch 100)
           + character_perks + character_satiety → rebuild_derived_stats (absolute) → MySQL
Battle:    battle-service reads stored attrs → damage eff(main), hit +0.1*eff(luck), crit = stored, initiative eff
Shop:      locations-service → econ_core.charisma_discount_pct(eff(charisma)*0.1%)
Dungeon:   dungeon-service → eff(primary) for checks/minigames
```

---

## 4. Tasks (filled by Architect, updated by PM — in English)

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | Create `stat_caps.py` (3.1: constants, `effective_stat`, `effective_delta`) in character-attributes-service and copy byte-for-byte to battle-service and dungeon-service; add `check_group "stat_caps"` to the copy-check script (update its final error hint to name the canonical file). | Backend Developer | DONE | `services/character-attributes-service/app/stat_caps.py`, `services/battle-service/app/stat_caps.py`, `services/dungeon-service/app/stat_caps.py`, `scripts/check_econ_copies.sh` | — | `sh scripts/check_econ_copies.sh` passes; py_compile passes; eff values match 3.1 examples. |
| 2 | character-attributes-service: add `crud.apply_attribute_modifiers(attr, modifiers)` (3.2) and route the upgrade endpoint, `_apply_modifiers_internal` and HTTP `apply_modifiers` through it; remove `propagate_derived` (satiety apply + expiry now propagate); `compute_derived_stats` uses eff; add constants for the luck→dodge/crit/res_effects coefficient if missing (no magic numbers, drop the hardcoded 10/5/10/5 in upgrade). | Backend Developer | DONE | `app/crud.py`, `app/main.py`, `app/regen.py`, `app/constants.py` | #1 | Gear primary stats now move resists/dodge/crit; equip→unequip returns all fields to the starting values across 100/200 thresholds; responses/contracts unchanged; py_compile passes; existing tests updated where they asserted the old linear/no-propagation behaviour. |
| 3 | inventory-service: new internal endpoint `POST /inventory/internal/equipment-modifiers` (contract in §3) + Pydantic v1 request/response schemas; sum `build_modifiers_dict` per equipped slot exactly like `_worn_modifiers`. | Backend Developer | DONE | `services/inventory-service/app/main.py`, `services/inventory-service/app/schemas.py` (and `crud.py` if a helper is extracted) | — | 401/403 without internal token; 422 on empty/>500/non-int list; every requested id returned; broken items contribute nothing; sharpening and gems included; py_compile passes. |
| 4 | character-attributes-service: `crud.rebuild_derived_stats(db, attr, equipment_mods)` (3.3) + inventory client call; rewrite `/{id}/recalculate` and `/admin/recalculate_all` to use it (batches of 100, `skipped` in response, 502 on single-id inventory failure). `damage`, `critical_damage`, `vul_*`, primaries untouched. Remove/replace the old non-gear-aware `crud.recalculate_attributes`. | Backend Developer | DONE | `app/crud.py`, `app/main.py`, `app/schemas.py` (if response model added) | #2, #3 | Rebuild of a character with gear + perk + food gives the same derived values as building it up incrementally via `apply_attribute_modifiers`; running it twice changes nothing; inventory down → nothing written; py_compile passes. |
| 5 | battle-service: `stat_caps` in `compute_damage_with_rolls` (main attr), `luck_proc_bonus` helper (hit roll + `attacker_luck_bonus` from buffed luck at `main.py:2772`), drop luck from the crit roll, `aggregate_modifiers(effects, base_attributes=None)` with eff deltas and luck in `_DERIVED_PER_POINT`, pass base attrs at all `main.py` call sites, `compute_initiative` via eff. Update the stale docstrings/comments. | Backend Developer | DONE | `services/battle-service/app/battle_engine.py`, `buffs.py`, `redis_state.py`, `main.py` | #1 | Main attr 250 → base 162.5; crit roll uses stored crit only; luck 250 → +16.25 pp hit; a +50 strength buff at 180 adds 0.1·(eff(230)−eff(180)) = 1.25 to each phys resist; initiative of agi 300 = 175; py_compile passes; existing battle tests updated. |
| 6 | Economy: charisma via eff in `econ_core.py` (3.5) — edit the canonical character-service copy, copy byte-for-byte to the other 3; update `econ_contract_cases.py` charisma rows (canonical + 3 copies); update docstrings ("0.1 % per effective point"). | Backend Developer | DONE | `services/{character,inventory,locations,dungeon}-service/app/econ_core.py`, `services/{character,inventory,locations,dungeon}-service/app/tests/econ_contract_cases.py` | — | 530 → 23.25, 250 → 16.25, 100000 → 50; `MAX_CHARISMA_DISCOUNT`, `market_bid`, `ask_discount_floor` unchanged; check script passes; econ contract tests green in all 4 services. |
| 7 | dungeon-service: eff for primary-attribute stat checks and challenge stats (3.6), cumulative counters untouched. | Backend Developer | DONE | `services/dungeon-service/app/gameplay.py` | #1 | Strength 250 vs difficulty 170 fails (eff 162); cumulative stat check unchanged; py_compile passes. |
| 8 | Docs: describe the cap, the eff-delta invariant, gear/food propagation, rebuild endpoint and the luck change. Remove/mark DONE any ISSUES.md entries this feature fixes (gear stats without derived, recalculate wiping item bonuses, luck counted twice — if listed). | Backend Developer | DONE | `docs/services/character-attributes-service.md`, `docs/services/battle-service.md`, `docs/services/inventory-service.md`, `docs/services/dungeon-service.md`, `docs/services/locations-service.md`, `docs/ISSUES.md` | #2–#7 | Docs match the code; no stale ISSUES entries. |
| 9 | Frontend: `src/utils/statCaps.ts` + apply in `derived.ts`, `damage.ts`, `DerivedStatsSection.tsx` (initiative + tooltip), `StatExplainer.tsx` (texts incl. cap and new charisma text), `AdminMobTemplateForm.tsx` preview, cap hint near stat upgrade (§3.7). Russian texts, Tailwind only, 360px+, no `React.FC`. | Frontend Developer | DONE | `src/utils/statCaps.ts`, `src/components/CommonComponents/CharacterPassport/derived.ts`, `src/components/ProfilePage/StatsTab/damage.ts`, `src/components/ProfilePage/StatsTab/DerivedStatsSection.tsx`, `src/components/CreateCharacterPage/StepBlood/StatExplainer.tsx`, `src/components/Admin/MobsPage/AdminMobTemplateForm.tsx`, `src/components/ProfilePage/StatsTab/PrimaryStatsSection.tsx` or `StatDistributionPanel.tsx` | — (formulas fixed by this spec) | `npx tsc --noEmit` and `npm run build` pass (inside the container); profile numbers for a char with str 250 show base damage 162.5+bonus and initiative via eff; texts mention the cap. |
| 10 | QA (character-attributes-service): `test_stat_caps.py` — eff at 0, 100, 101, 150, 200, 201, 250, 530, −10, None; `effective_delta` symmetry. Upgrade across 100 and 200 (str 95 +10, 195 +10, resources incl. floor for energy/stamina at 101/201); `apply_modifiers` HTTP with gear strength/agility/int/end/luck propagates; equip/unequip reversibility across thresholds incl. interleaved upgrade (worked example in 3.2); perk grant/revoke across threshold; satiety apply/expiry propagate and fully revert; rebuild == incremental build; rebuild idempotent; rebuild keeps damage/crit_damage/vul_*; rebuild 502 / batch `skipped` with mocked inventory. Update old tests that pinned linear / non-propagating behaviour. | QA Test | DONE | `services/character-attributes-service/app/tests/test_stat_caps.py` (new), `test_upgrade_formulas.py`, `test_stats_formulas.py`, `test_recalculate.py`, `test_satiety.py`, `test_perks.py` | #2, #4 | pytest green in the container; fixtures use the real schema (see memory: silent-failure pattern — assert on actual column values). |
| 11 | QA (inventory-service): tests for `POST /inventory/internal/equipment-modifiers` — auth, validation, sum across slots, sharpening + gems, broken item, character without gear, weapon slot drops `damage`. | QA Test | DONE | `services/inventory-service/app/tests/test_equipment_modifiers_internal.py` (new) | #3 | pytest green. |
| 12 | QA (battle-service): damage base with main attr 80/150/250 (+buff crossing 200); crit roll no longer includes luck (patch `random`); hit roll +0.1·eff(luck); `attacker_luck_bonus` uses buffed luck; `aggregate_modifiers` with base attrs across thresholds and luck propagation; `_is_stat_down` still works without base; initiative via eff; `stat_caps.py` copy identical (sha256) to canonical. | QA Test | DONE | `services/battle-service/app/tests/test_stat_caps_battle.py` (new) + updates to existing luck/initiative tests | #5 | pytest green. |
| 13 | QA (economy + dungeon): econ contract cases green in all 4 services (charisma 530 → 23.25); guild payout cap / `market_bid` unchanged at the extremes; dungeon stat check and `_challenger` use eff for primaries and raw for cumulative counters; `check_econ_copies.sh` passes. | QA Test | DONE | `services/dungeon-service/app/tests/test_stat_caps_dungeon.py` (new), existing econ/guild tests (no edit expected beyond contract cases) | #6, #7 | pytest green in character, inventory, locations, dungeon services. |
| 14 | Review: full checklist, py_compile/tsc/build, pytest in all touched services, copy-check script, live check (profile of a char with stats > 100, equip/unequip an item with strength and verify resists move and return, run `recalculate_all` locally and confirm `skipped` empty, one battle turn without errors). Confirm no commit/push by agents. | Reviewer | DONE | all | #1–#13 | Checklist passed; live verification recorded in section 5. |

**Post-deploy (PM):** after the user pushes and prod is up, call `POST /attributes/admin/recalculate_all` once (admin JWT) and confirm `skipped` is empty; re-run for any skipped ids.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-02 — Result: **PASS**

#### Spec compliance
- eff(x) piecewise (100 full / 100–200 ×0.5 / >200 ×0.25) on the stored TOTAL column (points+gear+sharpening/gems+perks+food) and on buffed battle attrs — verified in `stat_caps.py` (3 byte-identical copies), `econ_core` Decimal twin, `statCaps.ts`.
- All conversions covered: stored derived (resists, dodge, crit, res_effects, 4 resource maxes), battle damage main attr, hit-roll luck, effect-proc luck (now buffed luck), initiative, battle buffs (`aggregate_modifiers` with base attrs + luck now propagates), charisma 0.1 %/eff point with 50 % ceiling, dungeon checks/challenges (cumulative counters raw).
- Fix 1 (gear/food primaries feed derived): one helper `crud.apply_attribute_modifiers` for upgrade, HTTP apply_modifiers, perks, food apply/expiry; `propagate_derived` removed.
- Fix 2 (luck once in crit): battle crit roll uses stored crit only.
- Delta-of-eff telescopes, path-independent. Resources use floor(m·eff) deltas (integer-exact).
- `rebuild_derived_stats`: absolute, flats = equipment + held perks + active satiety; primaries, damage, critical_damage, vul_* untouched; current_* only clamped down. Held `character_perks` always have their flats applied (grant/revoke/admin edit/delete all go through the helper), so including every held perk is correct.
- Inventory endpoint mirrors `_worn_modifiers` exactly (sharpening, gems, durability, slot_type); fast slots included, consistent with equip which applies mods for every slot.

#### Cross-service
- `POST /inventory/internal/equipment-modifiers`: internal token (401 without), 422 on empty, 403 from nginx externally (checked live). attributes → inventory URL/headers correct; failure → `None` → 502 single / `skipped` batch.
- Frontend callers of `/recalculate`: `NpcStatsEditor.tsx` shows a toast on any error; `MobStatsEditor.tsx` showed a generic toast — **fixed by reviewer** to show the backend `detail` (so the new 502 text is visible). No frontend caller of `/admin/recalculate_all` (admin/PM tool only) — `skipped` needs no UI.
- character-service `send_recalculate_request` treats non-200 as None (logged) — unchanged behaviour.

#### Code standards / frontend rules
- Pydantic v1 (`validator`, `StrictInt`), sync attrs service stays sync. No magic numbers (constants added). No secrets.
- Frontend: TS only, no `React.FC`, Tailwind/design-system classes (`field-hint`, `gold-text`), Russian text, no new SCSS. 360px: no horizontal overflow on `/profile` (iframe check, scrollWidth == clientWidth).
- Docs: 5 service docs updated; stale ISSUES entry (recalculate wipes damage) removed.

#### Automated Check Results
- [x] `npx tsc --noEmit` (frontend container) — PASS (host node_modules lack `react-icons`, unrelated/pre-existing)
- [x] `vite build` (frontend container) — PASS
- [x] `py_compile` on all 38 modified/new Python files — PASS
- [x] `pytest` — PASS: character-attributes 771 passed; inventory 2185; battle 1705; character-service 7331; locations 2267; dungeon all passed (exit 0)
- [x] `bash scripts/check_econ_copies.sh` — PASS (econ_core, contract cases, ledger, stat_caps)
- [x] `docker compose config` — PASS
- [x] Live verification — PASS

#### Live Verification Results (localhost only)
- Char 706 (weapon +10 str, str 30): `/recalculate` → res_physical 2.0 → 3.0 (gear now propagates), damage 20 / crit_damage / vul untouched; second call identical (idempotent).
- Internal `apply_modifiers` on 706: +80 str/+100 hp → str 110, res_physical 10.5 (=0.1·eff 105), max_health 1275 (health 135 → eff 117.5); +120 str → 230, res_physical 15.75; revert −200/−100 → every field back exactly to the post-rebuild values.
- Inventory paused → `/recalculate` 502 «Не удалось получить снаряжение персонажа», nothing written.
- `/admin/recalculate_all` → `{"count": 843, "skipped": []}` in 4.1 s; re-run identical. Spot checks: char 18 (agi 206, luck 110) dodge 30.65, crit 30.5, res_effects 21.5, max_health 1275 — match formulas; char 188 (all stats >340) dodge 42.7 correct.
- Profile `/profile` (Ашари, mage, int 110, damage bonus 1000): основной урон 1105 (=eff 105 + 1000), инициатива 113.8 (=20 + (20+105)·0.75), маг. сопротивления 10.5 %, HP 1300; tooltips/hint carry the cap text; console errors: NONE.
- Not done live: a real battle turn and a points upgrade across 100 (no free points on test chars) — both covered by unit/integration tests (battle 57 new tests, upgrade threshold tests).

#### Issues found
| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| 1 | LOW | `frontend/.../Admin/MobsPage/MobStatsEditor.tsx` | recalculate error toast ignored backend `detail` (new 502 message invisible) | FIXED by reviewer |

#### Remaining risks (prod rollout)
- Between deploy and the one-off `POST /attributes/admin/recalculate_all`, unequipping pre-existing gear / expiring pre-existing food subtracts derived values that were never added (temporary negative drift). The rebuild is absolute and erases it — run it right after deploy and check `skipped` is empty.
- `recalculate_all` holds row locks on 100 characters during one inventory call (≤15 s timeout) — fine for an admin one-off, avoid running during peak.
- Characters with stats > 100 get weaker on prod (approved, pre-beta). Rollback = revert + old recalculate (strips gear bonuses until re-equip).

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-02 — PM: фича создана, решения пользователя зафиксированы, предварительный анализ формул внесён в раздел 2; запускаю архитектора
[LOG] 2026-11-02 21:32 — Architect: начал проектирование, перепроверил анализ — дополнения в разделе 2 (еда тоже не даёт производных, пересчёт обнуляет бонусы шмота и урон, удача в бою берётся без баффов)
[LOG] 2026-11-02 21:55 — Architect: выбрана схема «дельта от eff» через один общий помощник + разовый пересчёт с учётом шмота/перков/еды через админ-эндпоинт; удача в крите — только в сохранённом крите
[LOG] 2026-11-02 21:55 — Architect: спроектировано 14 задач (8 бэкенд/доки, 1 фронт, 4 QA, 1 ревью), 1 новый внутренний API-контракт (inventory), 2 изменённых админских эндпоинта; миграций БД нет
[LOG] 2026-11-02 22:10 — Backend Dev: начал задачи #1–#8
[LOG] 2026-11-02 22:20 — Backend Dev: задача #1 завершена — stat_caps.py в атрибутах (канон), бою и данжах, группа stat_caps добавлена в scripts/check_econ_copies.sh
[LOG] 2026-11-02 22:25 — Backend Dev: задача #6 завершена — харизма 0.1 % за эффективную единицу в econ_core (4 копии), строки контрактной таблицы обновлены (530 → 23.25)
[LOG] 2026-11-02 22:35 — Backend Dev: задача #3 завершена — POST /inventory/internal/equipment-modifiers (схемы EquipmentModifiersRequest/Response), проверено вживую: 200 / 422 / 401
[LOG] 2026-11-02 22:50 — Backend Dev: задача #2 завершена — crud.apply_attribute_modifiers один для прокачки, снаряжения, перков и еды; propagate_derived удалён; шмот и еда теперь дают производные
[LOG] 2026-11-02 23:00 — Backend Dev: задача #4 завершена — crud.rebuild_derived_stats + переписаны /recalculate (502 без инвентаря) и /admin/recalculate_all (батчи по 100, skipped); старый recalculate_attributes удалён; баг «пересчёт стирает урон/бонусы шмота» исправлен, удалён из ISSUES.md
[LOG] 2026-11-02 23:15 — Backend Dev: задача #5 завершена — урон от eff(основного стата), удача в попадании 0.1·eff от баффнутой удачи, удача больше не идёт в крит второй раз, aggregate_modifiers с base_attributes и удачей, инициатива через eff
[LOG] 2026-11-02 23:20 — Backend Dev: задача #7 завершена — проверки статов и мини-игры в данжах сравнивают floor(eff) для основных атрибутов, счётчики cumulative_stats как есть
[LOG] 2026-11-02 23:35 — Backend Dev: задача #8 завершена — документация 5 сервисов обновлена
[LOG] 2026-11-02 23:35 — Backend Dev: поправлены старые тесты под новое поведение — атрибуты (пересчёт не трогает damage/crit_damage, еда двигает производные, кап для 10000, мок инвентаря в фикстурах пересчёта), бой (крит без удачи), локации и character-service (скидка харизмы, test_econ_merchant_pricing); в спецификации #5 пример «+50 силы на 180 = 1.25» неверен — правильно 1.75 (eff 230 − eff 180 = 17.5)
[LOG] 2026-11-02 22:10 — Frontend Dev: начал задачу #9
[LOG] 2026-11-02 22:40 — Frontend Dev: задача #9 завершена — utils/statCaps.ts (eff как на бэке), кап в паспорте/профиле (урон, инициатива, ресурсы, уклонение, крит), предпросмотре моба (урон-бонус теперь 0), тексты про убывающую отдачу и новую харизму; tsc и build в контейнере проходят
[LOG] 2026-11-02 22:25 — QA: начал тесты для задач #10–#13 (атрибуты, инвентарь, бой, экономика + данжи)
[LOG] 2026-11-02 23:55 — QA: #10 готово — test_stat_caps.py в атрибутах (105 тестов): eff на всех порогах, прокачка через 100/200 с floor ресурсов, шмот/перки/еда двигают производные и снимаются без хвостов (в т.ч. случайные последовательности), rebuild == пошаговая сборка, идемпотентен, не трогает урон/крит.урон/уязвимости, 502 и skipped в пересчёте, RBAC 403
[LOG] 2026-11-02 23:55 — QA: #11 готово — test_equipment_modifiers_internal.py (29 тестов): 401/503 без токена, 422 на мусор/инъекции/пустой/>500, сумма по слотам с заточкой и камнями, сломанный предмет, урон оружия в руке не идёт
[LOG] 2026-11-02 23:55 — QA: #12 готово — test_stat_caps_battle.py (57 тестов): урон от eff основного стата (в т.ч. бафф через 200), попадание +0.1·eff(удачи), крит без удачи, aggregate_modifiers с base (+50 силы на 180 = 1.75), инициатива, бонус удачи к эффектам в реальном ходе берётся от баффнутой удачи
[LOG] 2026-11-02 23:55 — QA: #13 готово — test_stat_caps_dungeon.py (57 тестов), test_econ_charisma_caps.py в character-service, +9 строк харизмы в econ_contract_cases (4 копии, check_econ_copies.sh проходит); тест «нет выгоды от перепродажи» теперь берёт настоящий потолок 50 % вместо харизмы 250
[LOG] 2026-11-02 23:55 — QA: полные прогоны в контейнерах зелёные — атрибуты 771, инвентарь 2185, бой 1705, character-service 7331, локации 2267, данжи — все прошли; багов в реализации не найдено
[LOG] 2026-11-03 00:40 — Reviewer: начал ревью — спецификация, кросс-сервисные контракты, копии, фронтенд-правила
[LOG] 2026-11-03 01:10 — Reviewer: py_compile, все pytest-наборы (6 сервисов), check_econ_copies, tsc и сборка фронта — всё зелёное
[LOG] 2026-11-03 01:30 — Reviewer: живая проверка на локалке — пересчёт с учётом шмота, идемпотентность, точный откат через пороги 100/200, 502 без инвентаря, recalculate_all 843 персонажа без пропусков, профиль без ошибок в консоли
[LOG] 2026-11-03 01:35 — Reviewer: мелкая правка — админка мобов теперь показывает текст ошибки пересчёта от бэкенда (MobStatsEditor.tsx)
[LOG] 2026-11-03 01:40 — Reviewer: ревью пройдено (PASS); на проде сразу после выкатки вызвать recalculate_all
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Убывающая отдача статов: до 100 — полностью, 100–200 — ×0.5, выше 200 — ×0.25; считается от суммы очков, снаряжения, еды, перков и баффов, для всех статов и ресурсов.
- Производные статы меняются на разницу эффективных значений — порядок не важен, снятие вещи точно отменяет надевание.
- Статы со снаряжения и еды теперь дают сопротивления/уклонение/крит; удача в крите — один раз (в сохранённом крите).
- Бой: урон от основного стата, инициатива, бонус удачи — через кап; баффы удачи дают уклонение/крит.
- Харизма: 0.1 % за эффективную единицу (530 → 23.25 %), потолок 50 % оставлен.
- Подземелья: проверки статов через кап.
- `/recalculate` и `/admin/recalculate_all` — полная пересборка с учётом шмота/перков/еды, не трогают урон/крит-урон/уязвимости; новый internal-эндпоинт inventory `equipment-modifiers`.
- Фронт: `statCaps.ts`, профиль, подсказки о капе, создание персонажа, админка мобов.
- Тесты: ~300 новых, все наборы зелёные; ревью PASS с живой проверкой.

### Оставшиеся риски / follow-up задачи
- После деплоя один раз вызвать `POST /attributes/admin/recalculate_all` на проде, проверить `skipped` пустой; не в пик.
- Обновить статью «Навыки и характеристики» в Технобуке (кап, харизма, удача).

```
[LOG] 2026-11-02 — PM: ревью PASS, фича закрыта
```
