# FEAT-201: Стат «Скрытность»

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-04 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-000-slug.md` → `DONE-FEAT-000-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Пользователь: сейчас «обнаружение» при преступлении — по сути проки от местности (база места − 0.1×(ловкость+удача) − подкласс − маска). Нужен отдельный полноценный стат «Скрытность», который влияет на шанс быть замеченным. Продолжение FEAT-199 «Тень» (на проде 331e4b9).

### Решения пользователя (2026-11-04)
1. Скрытность — **прокачиваемый стат** (очки при повышении уровня, как остальные), плюс снаряжение/еда/бафы/подклассы.
2. **Бегство от стражи и побег из тюрьмы** переводятся на скрытность.
3. Противовеса (внимательность стражи/NPC) **пока нет** — скрытность просто снижает шанс обнаружения. Пример пользователя: «в поселении шанс заметить преступление 100 %, у тебя стат скрытности даёт 50 %, следовательно шанс прока будет 50 %».
4. В бою скрытность **ничего не даёт** (не трогаем).

### Бизнес-правила (значения по умолчанию PM, всё редактируемо в админке; формулу пользователь может поправить)
- **Скрытность** — 11-й первичный стат персонажа (рядом с ловкостью, удачей, харизмой), подчиняется капу FEAT-195 (до 100 — полностью, 100–200 ×0.5, >200 ×0.25) от суммы очки+шмот+еда+перки+баффы.
- **Снижение шанса** = 0.5 % за эффективную единицу скрытности, потолок 90 %.
- **Шанс заметить** = база места × (1 − снижение скрытности) × множители (слава, размер группы), границы 5–95 % (или пересмотреть с учётом базы 100 %). Мультипликативно: при базе 40 % и скрытности 50 % → 20 %.
- **Базы места:** поселение (safe) 100 %, ферма 70 %, опасная 40 %, данж 25 %.
- Ловкость и удача **больше не участвуют** в броске свидетелей. Подклассы Ассасин / Фокусник / Агент — вместо плоского бонуса к шансу получают прибавку к стату скрытности (через существующий механизм модификаторов/пассивок).
- **Маска** — только анонимность («заметили, но не узнали»); плоский −10 к шансу убирается; маска как предмет может давать скрытность обычным модификатором предмета.
- **Решение пользователя (2026-11-04):** у головных уборов в админке — галочка **«Скрывает личность»** (это существующий флаг `items.is_mask` из FEAT-199; переименовать подпись в ItemForm и везде в UI с «Маска (скрывает лицо при преступлениях)» на «Скрывает личность»; в карточке предмета — пометка «Скрывает личность»). Никакой отдельной механики маски сверх анонимности.
- **Бегство от стражи** — по скрытности и ловкости поровну; **побег из тюрьмы** — по скрытности.
- **Раскрытие нераскрытых дел** — шанс снижается скрытностью преступника (на момент преступления — снимок).
- Группа: шанс по наименее скрытному участнику (как сейчас — «самый заметный»), + бонус за размер.
- Без противовеса у стражи; в бою стат ничего не делает.

### Решения пользователя по вопросам аналитика (2026-11-04) — «как предлагаешь»
1. Очки за уровень — без изменений (10), скрытность конкурирует с остальными; сброса статов не делаем.
2. Бонус подклассов — **вариант A**: прибавка к скрытности считается в момент броска (character-service, по `subclass_of()`), числа в админке: Ассасин +30, Фокусник +30, Агент +20 (очки стата, добавляются ДО капа). Действует на свидетелей, бегство и побег.
3. Шанс может доходить до **100 %** (верхний предел 100, нижний 5 % остаётся); слава и размер группы — **множители** (не прибавки).
4. Расы — все начинают с 0 скрытности; пресеты рас не меняем (админ настроит сам). Валидатор пресета суммы=100 — переписать на root_validator (баг аналитика).
5. Заточка и самоцветы — да, скрытность качается как остальные статы.
6. Раскрытие дела — снимок снижения скрытности применяется 1:1 к шансу раскрытия.
7. Профиль — рядом со статом показывать «−X % к шансу быть замеченным» (нужен эндпоинт/поле от character-service с текущими настройками).
8. Проверки данжей — не трогаем (отдельная задача).

### UX
- Новый стат в распределении очков, в профиле, в карточках предметов/еды/баффов (модификатор «Скрытность»), в админке предметов/еды/перков.
- Руководство «Навыки и характеристики» и «Репутация, закон и тень» — обновить после выкатки.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Baseline: prod 331e4b9 (FEAT-199 shadow). Latest migrations: attributes `008_add_regen_and_satiety`, inventory `034_item_mask`, character `040_shadow_renown`. All paths below are relative to `services/`.

### 2.0 Key facts that shape the design

1. **`character_attributes` primaries are stored TOTALS** (points + gear + perks + food). Every source goes through `crud.apply_attribute_modifiers` (`character-attributes-service/app/crud.py:117`). It loops over `constants.PRIMARY_ATTRIBUTE_KEYS` (`constants.py:71`) and moves derived fields only for keys in `PRIMARY_DERIVED_EFFECTS` (`constants.py:60`). Charisma is the precedent: it is in `PRIMARY_ATTRIBUTE_KEYS` and absent from `PRIMARY_DERIVED_EFFECTS`. **Add stealth the same way: a primary with no derived fields.** Then the following all work with no extra code:
   - stat upgrade;
   - equipment: equip, unequip, sharpen, gems, durability;
   - perk flat bonuses;
   - food: satiety modifiers and their expiry reversal (`regen.negate_modifiers`).

   `rebuild_derived_stats` (`crud.py:185`) doesn't touch primaries, so `/recalculate` stays correct.
2. **The cap needs no code change.** `stat_caps.effective_stat` is generic and has no stat list. The 4 byte-identical copies (attributes, battle, dungeon, character) and `frontend/src/utils/statCaps.ts` stay as they are. character-service already applies the cap in `law_crud._effective` (`law_crud.py:169`).
3. **Battle-time buffs never reach the shadow code.** Shadow and law read the stored row by raw SQL (`law_crud.attributes_of`, `law_crud.py:160`). Battle buffs live only in Redis. Out of combat, "buffs" today means **food (satiety) and perks**. No other persistent timed stat buff exists.
4. **Subclass passives work only in battle** (`battle-service/app/passives.py`). They are loaded at battle start from skills-service `GET /skills/internal/characters/{id}/subclass`. Nothing gives a persistent stat for a subclass, and skills-service never calls the attributes `apply_modifiers`:
   - subclass choice: `skills-service/app/main.py:1032`;
   - tree reset keeps the subclass: `main.py:1105-1123`.

   See 2.6 for the options.
5. **No MySQL ENUM or JSON schema lists stat names.** These are all free JSON/TEXT:
   - `perks.bonuses` and `perks.conditions`;
   - `character_satiety.modifiers`;
   - `subraces.stat_preset` and `characters.starting_attributes`;
   - mob `base_attributes`;
   - `items.enhancement_bonuses`;
   - dungeon `trap_config.stat_check`;
   - title conditions.

   The only DDL needed is **plain `ADD COLUMN ... DEFAULT 0`**: `character_attributes.stealth`, `items.stealth_modifier`, and the character-service settings and snapshot columns. The `items` ENUM-lock gotcha doesn't apply here. Adding an `INT DEFAULT 0` column is instant in MySQL 8, the same as `034_item_mask`.

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| character-attributes-service | new column + every primary-stat list | **Model and migration:** `app/models.py:30-40` (add `stealth = Column(Integer, default=0)`); new migration `009_add_stealth` (`ADD COLUMN stealth INT NOT NULL DEFAULT 0`).<br>**Constants:** `app/constants.py:71` `PRIMARY_ATTRIBUTE_KEYS` (+`stealth`, NOT in `PRIMARY_DERIVED_EFFECTS`).<br>**Schemas:** `app/schemas.py:6-16` `CharacterAttributesBase` (**default must be `Field(0)`**: the base gives charisma/luck a default of 1, and the create path from character-service/RabbitMQ relies on these defaults when a preset lacks the key); `:95` `StatsUpgradeRequest`; `:161` `AdminAttributeUpdate`.<br>**crud:** `app/crud.py:230-241` `create_character_attributes` (pass `stealth=`); `:449-460` `VALID_FLAT_BONUS_KEYS` (perk flat bonus); `:719-728` perk-progress `attr_fields`.<br>**main:** `app/main.py:669-680` `total_needed`; `:714-725` upgrade modifiers dict; `:741-776` `updated_attributes` response.<br>**No change:** `rabbitmq_consumer.py` uses the schema; `perk_evaluator.py:158` reads attributes generically. |
| inventory-service | new item modifier column | **Model and migration:** `app/models.py:161-162` (+`stealth_modifier`); new migration `035_item_stealth_modifier`.<br>**crud:** `app/crud.py:139-143` `MAIN_STAT_FIELDS`. This list also drives sharpening (`main.py:3014/3127/3194`), `ALL_MODIFIER_FIELDS` (`crud.py:201`) and the display names. Whether stealth can be sharpened is Q5. `:155-160` `STAT_DISPLAY_NAMES` (+`'Скрытность'`). `:660-680` `build_modifiers_dict` (`mods["stealth"]`); it feeds equip, `/internal/equipment-modifiers` (`main.py:991`) and eat-food (`main.py:3852`).<br>**Schemas:** `app/schemas.py:182-193` `GATHERING_TOOL_FORBIDDEN_STAT_FIELDS`; `:630-641` `ItemBase`; `:1005-1014` (second item schema). |
| character-service | shadow/law rewiring + settings + snapshot + presets | **shadow_core:** `app/shadow_core.py`: `ShadowSettings` :78-110, `subclass_pct` :210, `member_chance` :219, `group_chance` :232, `reveal_chance` :242, `validate` :335+ labels.<br>**shadow_crud:** `app/shadow_crud.py:250-260` (reads `effective_attributes_of`; switch to effective stealth); `:396-405` `roll_reveal` (apply the per-crime stealth snapshot); `:265-298` (write the snapshot on deferred rows); `:546-615` settings out/update.<br>**law:** `app/law_crud.py:160-188` (`attributes_of`, `effective_attributes_of`, `flee_chance`, `escape_chance`); `app/law_core.py:148-155` (settings); `:329` `chance(base, per_point, lo, hi, agility, luck)`. The signature and docstring change: flee = stealth + agility, escape = stealth only.<br>**Models:** `app/models.py:1238-1245` (LawSettings); `:1270-1297` (LawCrime + snapshot column); `:1395-1420` (ShadowSettings).<br>**Schemas:** `app/schemas.py:3824-3833`, `:4022-4035` (settings in/out).<br>**Migration:** new `041_stealth`.<br>**Presets:** `app/schemas.py:619-650` `STAT_PRESET_KEYS` / `StatPreset`. **The sum-to-100 validator is attached to `luck` as the "last key" and sums `STAT_PRESET_KEYS[:-1]`. Appending `stealth` breaks it, so move it to a `root_validator`.** `app/crud.py:627-630` `PASSPORT_STAT_KEYS` (and the docstring "Десять"); `:1105-1117` fallback preset. `app/presets.py` is dead code (`main.py:348`); leave it. |
| frontend | new stat everywhere stats are listed | see "Frontend inventory" below |
| dungeon-service (optional) | only if stealth should feed dungeon checks | `app/gameplay.py:1615-1618` `PRIMARY_ATTRIBUTES` (so that `stat_check: "stealth"` uses eff); `app/generator.py:47` `CHECK_STATS`; `app/challenges.py:71-82` `KIND_STAT` (scout/search could lean on stealth). Outside the brief's scope, see Q8. |
| battle-service | **none** | Snapshots read the attributes dict by key, so an extra `stealth` key is ignored. `buffs.py:438/470` `_PRIMARY_ATTRS` / `_DERIVED_PER_POINT` and `battle_engine` stay as they are (brief rule 4). |
| skills-service / autobattle / locations / others | none | skills-service changes only if Q2 option B is chosen. |

### Frontend inventory (`services/frontend/app-chaldea/src/`)

The lists are hand-written, so each needs `stealth` / `stealth_modifier` + the label «Скрытность»:
- **Profile / stat distribution:**
  - `components/ProfilePage/constants.ts`: `STAT_LABELS` (:112), `PRIMARY_STATS` (:201), `MAIN_STATS` (:218, the tiered bar in `StatsTab/PrimaryStatsSection.tsx:58`), `UPGRADEABLE_STATS` (:231, used by `StatsTab/StatDistributionPanel.tsx:98`; the panel is list-driven, but `attributes[stat]` is typed).
  - `redux/slices/profileSlice.ts`: `CharacterAttributes` (:179-187), `UpgradeStatsPayload` (:239), the item `*_modifier` type (:29-37).
  - Optional: show the stat's effect ("−X % к шансу быть замеченным") in `StatsTab/DerivedStatsSection.tsx`. The per-point value is admin-editable in the DB, so don't hardcode it on the frontend (Q7).
- **Item / food tooltips:**
  - `ProfilePage/InventoryTab/ItemDetailModal.tsx`: `MODIFIER_FIELDS` (:23) + `MODIFIER_TO_STAT` (:76).
  - `Auction/AuctionListingDetail.tsx:160` strips `_modifier` and uses `STAT_LABELS`, so it needs no change.
  - `ProfilePage/CraftTab/GemSocketModal.tsx:57` `MODIFIER_LABELS`.
  - Optional: `AdminNpcsPage/NpcEquipmentEditor.tsx:210` (hand-written lines), `NpcStatsEditor.tsx:33-37/80/116`.
- **Admin forms:**
  - `ItemsAdminPage/itemFormRules.ts:142-150`. Items **and** food share this form.
  - `Admin/PerksPage/PerkForm.tsx:91` (condition attribute) + `:133` (flat bonus).
  - `Admin/CharactersPage/tabs/AttributesTab.tsx:53` + `types.ts:100-103,163-171`.
  - `Admin/TitlesPage/TitleForm.tsx:55-61` (title attribute condition). The backend side, `character-service/app/crud.py:3361/3521`, is generic.
  - `Admin/AdminRaces/StatPresetEditor.tsx:3-26` + `redux/slices/racesSlice.ts:9-16`, only if subraces get stealth (Q4).
  - Optional, since mobs never commit crimes: `Admin/MobsPage/MobStatsEditor.tsx:28/61/67`, `AdminMobTemplateForm.tsx:29`.
  - `Admin/DungeonsPage/editor/PropertyPanel.tsx:81-88`, only with Q8.
- **Creation / passport:**
  - `CreateCharacterPage/StepBlood/StatExplainer.tsx:35-46` `STAT_EFFECTS` (add a line).
  - `CommonComponents/CharacterPassport/types.ts:37-48` `PASSPORT_STAT_ORDER`, and the labels in `derived.ts:130-140`.
- **Perks/titles in the profile:** `ProfilePage/PerksTab/PerkDetailModal.tsx:49-52,102-105`, `TitlesTab/TitleCard.tsx:55-58`.
- **Shadow/law admin:**
  - `api/shadowAdmin.ts:48-52`.
  - `Admin/ReputationPage/ShadowSettingsTab.tsx:76-80`. The hints still say "ловкости + удачи", the subclass fields change from "% к шансу" to "очки скрытности", and the mask field goes away.
  - `api/lawAdmin.ts:34-38`.
  - `Admin/ReputationPage/LawSettingsTab.tsx:74,83` (hints say "ловкости + удачи").
- **Battle UI needs no change** (stealth isn't a battle stat): `pages/BattlePage/battleEffects.ts:160-175`, `Arena3D/*`, `AdminSkillsPage/skillConstants.ts`.
- The frontend rules apply. These are logic/style edits in existing `.tsx` files (already TS). Touching any `.jsx` or SCSS file triggers the T1/T3 migration rule.

### Existing Patterns
- **attributes-service:** sync SQLAlchemy, Pydantic v1, Alembic `alembic_version_char_attrs` (auto-migrate on start). All stat changes go through `apply_attribute_modifiers` (FEAT-195 telescoping deltas).
- **inventory-service:** sync, Alembic `alembic_version_inventory`. `build_modifiers_dict` is the single item→modifier mapper.
- **character-service:** sync, Alembic `alembic_version_character`.
  - Shadow/law modules are split into a pure core (`*_core.py`: Decimal math, dataclass settings with `SETTINGS_FIELDS` → `SQL_SELECT_SETTINGS`) and crud (raw SQL over other services' tables).
  - Settings live in a singleton row `id=1`, editable in the admin panel and validated in `*_core.validate`.
  - Migrations 039/040 use idempotent `_has_column` guards + raw `ALTER TABLE`.
- **Auth is unchanged:**
  - player upgrade: JWT + ownership;
  - `apply_modifiers`: `X-Internal-Token`;
  - shadow/law settings: the existing RBAC permissions. **No new permission rows are needed.**

### Cross-Service Dependencies
```
frontend ──> attributes POST /attributes/{id}/upgrade (body gains "stealth")
character-service ──HTTP──> attributes POST /attributes/ (create; preset dict, stealth defaults to 0)
inventory-service ──HTTP──> attributes POST /attributes/{id}/apply_modifiers ({"stealth": n} from items/food)
inventory-service ──HTTP──> attributes POST /attributes/internal/{id}/satiety (modifiers incl. stealth)
attributes /recalculate ──HTTP──> inventory POST /internal/equipment-modifiers (stealth ignored by rebuild: primaries untouched)
character-service (shadow/law) ──SQL──> character_attributes.stealth (+agility for flee), equipment_slots+items.is_mask, skills tree tables (subclass_of)
```
Deploy order: attributes migration 009 must run before character-service reads `stealth`. Both go out in the same compose deploy, but there can still be a window. `law_crud.attributes_of` should tolerate a missing column (WARNING + 0, like `shadow_crud._missing_mask_column`). Otherwise every NPC kill and every flee returns 500 during the deploy-skew window.

### DB Changes
- **`character_attributes`:** `ADD COLUMN stealth INT NOT NULL DEFAULT 0` (attributes 009). Existing prod rows get 0.
- **`items`:** `ADD COLUMN stealth_modifier INT NULL DEFAULT 0` (inventory 035). This matches the other `*_modifier` columns, which are nullable with default 0.
- **`shadow_settings`** (character 041):
  - Add `witness_stealth_reduction_per_point_pct` (DECIMAL(6,3), 0.500) and `witness_stealth_reduction_max_pct` (DECIMAL(5,2), 90.00).
  - Add subclass stealth points `stealth_agent` / `stealth_assassin` / `stealth_trickster` (INT, or DECIMAL if fractions are wanted).
  - Drop or zero `witness_agent_pct` / `witness_assassin_pct` / `witness_trickster_pct` / `witness_mask_pct` / `witness_stealth_per_point_pct`.
  - **`server_default` only affects new rows.** The migration must run `UPDATE shadow_settings SET witness_base_safe_pct=100, witness_base_farm_pct=70, witness_base_dangerous_pct=40, witness_base_dungeon_pct=25 WHERE id=1` and change the `ShadowSettings` dataclass defaults to match. DECIMAL(5,2) holds 100.00.
- **`law_settings`:** flee and escape keep their `*_base/_per_point/_min/_max` columns; only the meaning changes (flee = stealth + agility, escape = stealth). Escape goes from 2 stats to 1, so `escape_per_point_pct` likely needs re-tuning (UPDATE the row). The hint texts change too. No column rename is needed.
- **`law_crimes`:** add a snapshot column for the reveal, e.g. `stealth_reduction_pct DECIMAL(5,2) NULL`: the attacker's reduction at the time of the crime. NULL (old rows) is treated as 0. The VARCHAR `status` column is untouched.
- No new tables. No ENUM changes.

### Shadow rewiring (exact points)
- **`shadow_core.member_chance` (:219):**
  - Today (additive): `base − (eff_agi + eff_luck) × 0.1 − subclass_pct − mask_pct`, plus fame if unmasked.
  - New: `reduction = min(max_pct, eff_stealth × per_point)`, `chance = base × (1 − reduction/100)`, then the fame/group multipliers (Q3), then clamp.
  - The mask no longer subtracts anything; it only keeps anonymity. `masked` still selects the `CRIME_MASKED` status and suppresses fame.
- **`shadow_core.subclass_pct` (:210):** replaced by subclass stealth points (option A in 2.6), or removed (option B).
- **`shadow_crud.npc_kill_consequences` (:250-260):**
  - Replace `law_crud.effective_attributes_of` with a new `effective_stealth_of(db, cid, subclass_key, s)`: raw `stealth` + subclass bonus → `stat_caps.effective_stat`.
  - When creating deferred rows (:265-298, `register_crime` kwargs, around `law_crud.py:394`), persist each member's reduction into `law_crimes.stealth_reduction_pct`.
- **`shadow_core.reveal_chance` (:242) + `shadow_crud.roll_reveal` (:405):** multiply by `(1 − crime.stealth_reduction_pct/100)`, and/or apply a separate reveal factor (Q6).
- **`law_crud.flee_chance` / `escape_chance` (:179-188) + `law_core.chance` (:329):** flee `= base + (eff_stealth + eff_agility) × per_point`, escape `= base + eff_stealth × per_point`. Whether the subclass bonus counts here too is part of Q2.
- **`shadow_core.validate` (:335):** new labels and bounds (reduction max ≤ 100, per-point ≤ 10).
- **Tests:**
  - `character-service/app/tests/law_world.py:50-55` and `reputation_world.py:51` create a **SQLite `character_attributes` table with only `agility, luck`**. `shadow_world.py:70-77` has `set_attributes(agi, luck)`. Both need a `stealth` column/helper.
  - A missing column here repeats the known "silent failure" pattern: `law_crud.attributes_of` would raise in tests, and in prod that error must not be swallowed.
  - Existing assertions will change in `test_shadow_core.py`, `test_shadow_kill.py`, `test_shadow_reveal.py` and `test_law_core.py` (flee/escape numbers).

### 2.6 Subclass +stealth: options
- **A. Read-time bonus in character-service (recommended).** `subclass_of()` already runs per member (`shadow_crud.py:72`). Add admin settings `stealth_assassin/trickster/agent` (points), added to the raw stealth before `eff()`.
  - Pros: one service, no cross-service writes, editable, no drift.
  - Cons: the profile's stealth number won't include the bonus unless the frontend asks character-service (Q7).
- **B. Persistent modifier.** skills-service calls attributes `apply_modifiers({"stealth": n})` on subclass choice and on admin progress changes/deletions.
  - Pros: shows in the profile automatically and counts toward the cap like gear.
  - Cons:
    - a new cross-service write path;
    - idempotency and reversal: today `reset_tree` keeps the subclass, but an admin delete doesn't;
    - existing subclass holders on prod need a backfill;
    - the setting can't be changed without a recompute.
- **C. Perks.** An auto perk with a flat `stealth` bonus and a condition on the subclass. `VALID_CONDITION_TYPES` (`crud.py:463`) has no `subclass` type, so perk_evaluator would need a new condition type. More work than A.

### Risks
- **Many hand-written stat lists** (~10 backend, ~20 frontend). Mitigation:
  - grep for `charisma` / `luck_modifier`, which hits every list;
  - add a test asserting that `StatsUpgradeRequest` fields == `PRIMARY_ATTRIBUTE_KEYS ∪ RESOURCE_STATS`;
  - add a test asserting that every inventory `MAIN_STAT_FIELDS` entry has a mapping in `build_modifiers_dict`.
- **`StatPreset` validator ordering bug** (see above). Appending `stealth` silently double-counts luck and breaks saving races in the admin panel.
- **The schema default-1 trap.** `CharacterAttributesBase` gives charisma/luck a default of `1`. Copying that for stealth would give every new character 1 point for free.
- **Prod balance jump.** After deploy:
  - stealth is 0 for everyone;
  - agility and luck no longer count;
  - the settlement base becomes 100 (clamped to `witness_max_pct` 95);
  - the mask's −10 is gone.

  So almost every crime in a settlement is witnessed until players invest points or gear. That's acceptable pre-beta (per memory), but the user should know (Q1).
- **Flee/escape regression.** Characters built on agility/luck lose flee and escape chance overnight (escape → stealth only). The base values may need retuning.
- **Deploy skew.** character-service may read `stealth` before attributes migration 009 has run. Guard it like `_missing_mask_column` (WARNING + 0, never silent).
- **No backfill for items.** No worn item can have stealth before deploy (the new column defaults to 0). Option B, if chosen, needs a backfill of existing subclass holders.
- **Sharpening/gems/identification** automatically include everything in `MAIN_STAT_FIELDS`. That's fine if wanted; otherwise exclude stealth explicitly.
- **Copies.** No `stat_caps` / `econ_core` copy changes; `scripts/check_econ_copies.sh` is unaffected.
- **Docs to update:**
  - `docs/services/character-attributes-service.md` (~:215, stat effects);
  - `inventory-service.md` (item columns);
  - `character-service.md` (shadow/law formulas);
  - `docs/SUBCLASS-PASSIVES.md` (note the out-of-battle stealth bonus);
  - the in-game guides «Навыки и характеристики» and «Репутация, закон и тень» are DB content (PM updates them after deploy).

### Open questions (user decisions)
1. **Points per level.** Keep 10 points per level (`character-service/app/crud.py:1395`) and let stealth compete with the other 10 stats? Or give stealth a separate allowance? Do existing characters get a one-time compensation or a stat reset? No respec mechanism exists.
2. **Subclass bonus mechanism.** Option A (a read-time setting, not shown in the profile total) or option B (a real stat via modifiers, shown everywhere)? What numbers per subclass (e.g. Ассасин/Фокусник +30, Агент +20)? Does the bonus also apply to flee/escape?
3. **Formula details.**
   - Fame tier (`renown_tiers.witness_pct`, today +0..15 pp additive) and group size (+10 pp per extra member): keep them additive after the multiplication, or turn them into true multipliers (e.g. ×1.10 per extra member)?
   - Clamp 5–95 vs a base of 100: should a settlement with 0 stealth stay at 95 or reach 100?
4. **Starting stealth / subraces.** Start everyone at 0, or put stealth into some subrace presets? Presets must sum to 100, so another stat would go down. Stealth is also new in the passport.
5. **Sharpening/gems.** Can stealth be sharpened or socketed (whetstones, gems) like the other main stats?
6. **Reveal.** Should the snapshot reduction apply 1:1 to the daily reveal chance (`reveal × (1 − reduction)`), or with its own factor?
7. **Profile display of the effect.** Should the profile show "−X % к шансу быть замеченным"? That needs the admin-editable per-point/max values from character-service, via a small public endpoint or added to `GET /characters/{id}/renown`.
8. **Dungeons.** Should stealth be a dungeon `stat_check` / scout challenge stat? This isn't in the brief; I suggest a follow-up.
9. **Mask.** Are there mask items on prod already (`items.is_mask = 1`), and should they get a `stealth_modifier` value as part of this feature?

---

## 3. Architecture Decision (filled by Architect — in English)

Baseline: prod `331e4b9` (FEAT-199). Latest migrations: attributes `008_add_regen_and_satiety`, inventory `034_item_mask`, character `040_shadow_renown`. All paths are relative to `services/`. The user decisions in §1 (incl. «Решения пользователя по вопросам аналитика») are FINAL and are implemented exactly as written below.

### 3.0 Summary of key decisions

| # | Decision | Why |
|---|---|---|
| D1 | **`stealth` is the 11th primary stat, stored in `character_attributes` as a TOTAL**, like charisma: it is in `PRIMARY_ATTRIBUTE_KEYS` and NOT in `PRIMARY_DERIVED_EFFECTS` (it has no derived fields). Upgrades, gear (equip/unequip/sharpen/gems/durability), perk flat bonuses and food (satiety + expiry reversal) then work through the existing `apply_attribute_modifiers` with no extra code. | §2.0 fact 1. |
| D2 | **Default 0 everywhere** (`Field(0)` in the schema, `server_default 0` in the DB). Do NOT copy charisma/luck's schema default of 1. | Otherwise every new character gets 1 free point. |
| D3 | **Item modifier `items.stealth_modifier`** is added to `MAIN_STAT_FIELDS`, so it can be sharpened and socketed like the other main stats (user decision 5), and it is mapped in `build_modifiers_dict`. | §2 inventory row. |
| D4 | **Subclass bonus = read-time stat points in character-service (option A).** Defaults: Ассасин +30, Фокусник +30, Агент +20. The bonus is added to the raw stealth **before** the cap, and it applies to witnesses, flee and escape. It is NOT written into `character_attributes`. | User decision 2. |
| D5 | **Witness chance is multiplicative** (formulas in §3.3): base × (1 − stealth reduction) × fame multiplier, then the group multiplier, then clamp to 5..**100**. Agility, luck, the flat subclass % and the flat mask % are removed from the roll. | User decision 3 + brief. |
| D6 | **The mask = anonymity only.** The existing `items.is_mask` flag is unchanged in the DB; the UI label becomes «Скрывает личность». A masked member still has their fame ignored and still produces a `masked` crime. The `witness_mask_pct` setting is dropped. | Brief. |
| D7 | **Reveal** chance × (1 − the attacker's stealth reduction, snapshotted on the crime row at crime time, 1:1). | User decision 6. |
| D8 | **Flee** = stealth + agility, equal weight. **Escape** = stealth only. Both use effective (capped) values. The `law_settings` columns are unchanged (`escape_per_point_pct` is re-tuned, see Q2 below). | Brief. |
| D9 | **Deploy-skew guard:** if `character_attributes.stealth` is missing (attributes migration 009 not applied yet), log a WARNING and treat stealth as 0. Any other DB error re-raises. This mirrors the `wears_mask` pattern. | §2 risk; memory «тихие отказы». |
| D10 | **Profile effect line** «−X % к шансу быть замеченным» comes from a new private character-service read `GET /characters/{id}/stealth`. It returns the computed reduction, including the subclass bonus and the cap. The per-point value is never hardcoded on the frontend. | User decision 7. |
| D11 | **Subrace presets** gain an optional `stealth` key (default 0; existing presets are unchanged). The sum-to-100 validator moves to a `root_validator`. The passport shows 11 stats. | User decision 4 + analyst bug. |
| D12 | **Out of scope:** battle (stealth gives nothing in combat), dungeon checks (user decision 8), mob/NPC stat editors, skills-service, autobattle, and the `stat_caps` / `econ_core` copies (no change, so `check_econ_copies.sh` is unaffected). | Brief, §2. |

### 3.1 DB changes

#### character-attributes-service — Alembic `009_add_stealth` (down_revision `008_add_regen_and_satiety`)
```sql
ALTER TABLE character_attributes ADD COLUMN stealth INT NOT NULL DEFAULT 0;   -- instant in MySQL 8; existing rows = 0
```
- Guard the migration with `_has_column` (the 039/040 idempotent pattern).
- Rollback: `DROP COLUMN stealth`.
- ORM: `stealth = Column(Integer, default=0, nullable=False)  # Скрытность`.

#### inventory-service — Alembic `035_item_stealth_modifier` (down_revision `034_item_mask`; id is 25 chars, within the 32 limit)
```sql
ALTER TABLE items ADD COLUMN stealth_modifier INT NULL DEFAULT 0;   -- same shape as the other *_modifier columns; no ENUM touched
```
- Rollback: drop the column.
- ORM: `stealth_modifier = Column(Integer, default=0)`.

#### character-service — Alembic `041_stealth` (down_revision `040_shadow_renown`)
```sql
-- 1. new shadow settings (singleton row id = 1)
ALTER TABLE shadow_settings
  ADD COLUMN stealth_pct_per_point      DECIMAL(6,3) NOT NULL DEFAULT 0.500,  -- % of the chance removed per EFFECTIVE stealth point
  ADD COLUMN stealth_max_reduction_pct  DECIMAL(5,2) NOT NULL DEFAULT 90.00,  -- ceiling of the reduction
  ADD COLUMN stealth_assassin_points    INT NOT NULL DEFAULT 30,              -- rogue_assassin «Ассасин», stat points before the cap
  ADD COLUMN stealth_trickster_points   INT NOT NULL DEFAULT 30,              -- rogue_trickster «Фокусник»
  ADD COLUMN stealth_agent_points       INT NOT NULL DEFAULT 20;              -- warrior_agent «Агент»

-- 2. remove the FEAT-199 additive knobs that no longer exist in the formula
ALTER TABLE shadow_settings
  DROP COLUMN witness_stealth_per_point_pct,
  DROP COLUMN witness_agent_pct,
  DROP COLUMN witness_assassin_pct,
  DROP COLUMN witness_trickster_pct,
  DROP COLUMN witness_mask_pct;

-- 3. new location bases + upper bound 100 (server_default only affects new rows, so UPDATE the existing row)
ALTER TABLE shadow_settings
  MODIFY witness_base_safe_pct      DECIMAL(5,2) NOT NULL DEFAULT 100.00,
  MODIFY witness_base_farm_pct      DECIMAL(5,2) NOT NULL DEFAULT 70.00,
  MODIFY witness_base_dangerous_pct DECIMAL(5,2) NOT NULL DEFAULT 40.00,
  MODIFY witness_base_dungeon_pct   DECIMAL(5,2) NOT NULL DEFAULT 25.00,
  MODIFY witness_max_pct            DECIMAL(5,2) NOT NULL DEFAULT 100.00;
UPDATE shadow_settings SET witness_base_safe_pct = 100, witness_base_farm_pct = 70, witness_base_dangerous_pct = 40,
                           witness_base_dungeon_pct = 25, witness_max_pct = 100 WHERE id = 1;

-- 4. per-crime snapshot for the reveal
ALTER TABLE law_crimes ADD COLUMN stealth_reduction_pct DECIMAL(5,2) NULL;   -- NULL (old / forced rows) = 0

-- 5. escape is now 1 stat instead of 2: double the per-point value only if it is still the shipped default
ALTER TABLE law_settings MODIFY escape_per_point_pct DECIMAL(6,3) NOT NULL DEFAULT 0.300;
UPDATE law_settings SET escape_per_point_pct = 0.300 WHERE id = 1 AND escape_per_point_pct = 0.150;
```
- Developer note: keep the exact existing column type of `law_settings.escape_per_point_pct` in the `MODIFY` (check `039_law`; only the default changes).
- `witness_base_default_pct` (unknown location / no marker) stays at 50.
- No FK, no index, and no ENUM change. `law_crimes.status` stays VARCHAR.
- Every step is guarded (`_has_column` / `_column_default` checks) so a re-run is a no-op.
- **Rollback (`downgrade`):**
  - re-add the 5 dropped columns with their FEAT-199 defaults (0.100 / 10 / 15 / 15 / 10; old custom values are lost, which is acceptable pre-beta);
  - drop the 5 new columns;
  - restore the bases 70/45/25/15 and max 95 (row and defaults);
  - drop `law_crimes.stealth_reduction_pct`;
  - set `escape_per_point_pct` back to 0.150 where it is 0.300.
- ORM updates:
  - `models.ShadowSettings`: drop the 5 columns, add the 5 new ones, and change the defaults.
  - `models.LawCrime.stealth_reduction_pct = Column(Numeric(5, 2), nullable=True)`.
  - `models.LawSettings.escape_per_point_pct`: default 0.3.

### 3.2 Primary-stat lists (every hand-written list gains `stealth`)

**character-attributes-service**
- `constants.py:71` `PRIMARY_ATTRIBUTE_KEYS += ("stealth",)`. **Not** in `PRIMARY_DERIVED_EFFECTS`.
- `schemas.py`:
  - `CharacterAttributesBase`: `stealth: Optional[int] = Field(0, ge=0, description="Скрытность")`. **Default 0, not 1.**
  - `StatsUpgradeRequest`: `stealth: Optional[int] = 0` (non-negative like the others).
  - `AdminAttributeUpdate`: `stealth: Optional[int] = None`.
  - Every response schema that lists primaries (grep `charisma`).
- `crud.py`:
  - `create_character_attributes`: `stealth=attributes.stealth or 0`.
  - `VALID_FLAT_BONUS_KEYS` (:449) `+ "stealth"`.
  - perk-progress `attr_fields` (:719) `+ "stealth"`.
- `main.py` upgrade endpoint:
  - `total_needed` sum (:669) includes `stealth`;
  - the modifiers dict (:714) includes `"stealth": upgrade_request.stealth`;
  - the `updated_attributes` response (:741) includes `"stealth": attr.stealth`.
- Admin attribute update path: `stealth` is accepted and written like charisma.
- No change: `rabbitmq_consumer.py` (it uses the schema), `perk_evaluator.py` (generic), `rebuild_derived_stats` (primaries untouched), `stat_caps.py`.
- **Points per level are unchanged (10).** No respec.

**inventory-service**
- `crud.py:139` `MAIN_STAT_FIELDS += 'stealth_modifier'`. This automatically covers sharpening, gems, `ALL_MODIFIER_FIELDS` and identification.
- `STAT_DISPLAY_NAMES['stealth_modifier'] = 'Скрытность'`.
- `build_modifiers_dict`: `if item_obj.stealth_modifier: mods["stealth"] = item_obj.stealth_modifier`. This feeds equip/unequip, `/internal/equipment-modifiers` and eat-food (satiety).
- `schemas.py`: `GATHERING_TOOL_FORBIDDEN_STAT_FIELDS += "stealth_modifier"`; `ItemBase` (:630) and the second item schema (:1005) get `stealth_modifier: Optional[int] = None`. Grep `luck_modifier` in the service; every hit gets a `stealth_modifier` sibling.
- Mask validator message (`schemas.py:887`): «Скрывать личность может только головной убор». The flag name `is_mask` stays.

**character-service (presets / passport)**
- `schemas.py:617` `STAT_PRESET_KEYS` gains `"stealth"` (last).
- `StatPreset.stealth: int = 0`.
- The per-field non-negative validator stays.
- **Replace** `@validator("luck", always=True) preset_sum_must_be_100` with a `@root_validator(skip_on_failure=True)` that sums `values.get(k, 0)` over all `STAT_PRESET_KEYS`. It keeps the same Russian error, «Сумма пресета должна быть равна 100, получено {total}».
- `crud.py:627` `PASSPORT_STAT_KEYS` gains `"stealth"`; the comment/docstring changes «Десять» → «Одиннадцать».
- Fallback preset (:1105) gets `"stealth": 0`; the sum stays 100.
- `presets.py` is dead code; leave it.

### 3.3 Shadow / law maths (character-service; pure parts in `shadow_core.py` / `law_core.py`)

**Settings value object `shadow_core.ShadowSettings`:**
- Remove `witness_stealth_per_point_pct`, `witness_agent_pct`, `witness_assassin_pct`, `witness_trickster_pct` and `witness_mask_pct`.
- Add `stealth_pct_per_point: Decimal = 0.5`, `stealth_max_reduction_pct: Decimal = 90`, `stealth_assassin_points: int = 30`, `stealth_trickster_points: int = 30` and `stealth_agent_points: int = 20` (the 3 subclass fields go into `INT_FIELDS`).
- New defaults: bases 100/70/40/25, `witness_max_pct = 100`.
- `SETTINGS_FIELDS` / `SQL_SELECT_SETTINGS` follow automatically.

**Pure functions (`shadow_core`):**
```
SUBCLASS_LABELS = {rogue_assassin: "Ассасин", rogue_trickster: "Фокусник", warrior_agent: "Агент"}

subclass_stealth_points(subclass_key, s) -> int            # replaces subclass_pct; 0 for none / other subclasses
effective_stealth(raw_stealth, subclass_points) -> Decimal  # stat_caps.effective_stat(max(0, raw) + points), q2
stealth_reduction_pct(eff_stealth, s) -> Decimal            # min(max_reduction, max(0, eff) × pct_per_point), q2
member_chance(base, reduction_pct, masked, fame_witness_pct) -> Decimal      # unclamped
    = base × (1 − reduction/100) × (masked ? 1 : 1 + fame_witness_pct/100)
group_chance(member_chances, n_players, s) -> Decimal
    = q2(clamp(max(member_chances) × (1 + group_per_extra_pct/100 × (n − 1)), witness_min_pct, witness_max_pct))
    # empty list -> clamp(base_default) as today
reveal_chance(effective_suspicion, masked, s, stealth_reduction_pct=0) -> Decimal
    = q2(clamp((reveal_base + susp × per_susp) × (masked ? factor/100 : 1) × (1 − snapshot/100), reveal_min, reveal_max))
```
- `shadow_core` may import the pure `stat_caps` module (no I/O).
- The fame tier `renown_tiers.witness_pct` keeps its column. Its meaning changes from «+N п.п.» to **«+N % multiplier»**, and its bounds 0..50 stay.
- `witness_group_per_extra_pct` likewise becomes «+N % multiplier per extra attacker» (linear: 2 players ×1.10, 3 players ×1.20 with the default 10).

**`law_core.chance`:** generalise to `chance(base, per_point, lo, hi, *points)`, which computes `clamp(base + Σ max(0, p) × per_point, lo, hi)`. Integer and two-arg callers give identical results. Update the docstring.

**`shadow_core.validate`:**
- Drop the removed labels.
- Add the new rules:
  - `stealth_pct_per_point` 0..`MAX_PER_POINT` (10) → «Снижение за очко скрытности: от 0 до 10»;
  - `stealth_max_reduction_pct` 0..100 → «Предел снижения скрытностью: от 0 до 100 %»;
  - subclass points 0..`MAX_SUBCLASS_STEALTH` = 500 → «Скрытность подкласса «Ассасин»: от 0 до 500».
- The existing rules stay: bases 0..100, `witness_max_pct` ≤ 100, and min ≤ max.
- Fame tier label: «Узнаваемость ступени славы (множитель): от 0 до 50 %».

**Worked numbers (QA expectations; all settings are defaults; fame «Безвестный» = 0):**

| Case | Result |
|---|---|
| Settlement 100, stealth 0, alone | 100.00 (clamp max 100) |
| Settlement, raw stealth 100 | eff 100 → reduction 50 → **50.00** |
| Dangerous 40, raw 100 | **20.00** |
| Ассасин, raw 0, settlement | eff 30 → red 15 → **85.00** |
| Ассасин, raw 100, settlement | 130 → eff 115 → red 57.50 → **42.50** |
| Raw 400, settlement | eff 200 → red min(90, 100) = 90 → **10.00** |
| Raw 400, dungeon 25 | 2.50 → clamp **5.00** |
| Dangerous, raw 0, fame «Легенда» (15) | 40 × 1.15 = **46.00** |
| Same, masked | **40.00** (masked fame ignored) |
| Group of 2, member chances 50 and 20 | 50 × 1.10 = **55.00** |
| Reveal: susp 50 (15 + 20 = 35), snapshot 50 | **17.50** |
| Reveal: same, masked | 35 × 0.5 × 0.5 = **8.75** |
| Reveal: snapshot NULL | 35.00 (unchanged from today) |
| Flee (base 20, 0.25/pt): stealth 40, agility 60 | 20 + 100 × 0.25 = **45.00** |
| Escape (base 5, 0.30/pt): stealth 100 | **35.00** |
| Escape: Ассасин, raw 0 | eff 30 → **14.00** |

**DB readers (`law_crud.py`).** `law_crud` already imports `renown_crud`, so there is no cycle.
- **Move** `subclass_of(db, cid)` from `shadow_crud` to `law_crud`, and keep `shadow_crud.subclass_of = law_crud.subclass_of` as an alias for existing tests and callers.
- `stealth_agility_of(db, cid) -> (int stealth, int agility)`: `SELECT stealth, agility FROM character_attributes WHERE character_id = :c`, run inside `db.begin_nested()`. It returns (0, 0) when there is no row.
  - **Only** a `DBAPIError` whose message mentions `stealth` together with "unknown column" or "no such column" leads to `logger.warning("character_attributes.stealth is missing (attributes migration 009 not applied?) — treating stealth as 0")`, then a fallback `SELECT agility` that returns `(0, agility)`.
  - Anything else re-raises (the `_missing_mask_column` pattern).
- `StealthInfo` dataclass: `raw: int, subclass_key: Optional[str], subclass_points: int, effective: Decimal, reduction_pct: Decimal, eff_agility: Decimal`.
- `stealth_info(db, cid, shadow_settings=None) -> StealthInfo`. It loads `renown_crud.load_shadow_settings` when not given, then calls `stealth_agility_of`, `subclass_of`, `sc.subclass_stealth_points`, `sc.effective_stealth`, `sc.stealth_reduction_pct` and `_effective(agility)`.
- `flee_chance` = `lc.chance(flee_base, flee_per_point, lo, hi, info.effective, info.eff_agility)`.
- `escape_chance` = `lc.chance(escape_base, escape_per_point, lo, hi, info.effective)`.
- Remove `attributes_of` / `effective_attributes_of` once grep shows no other user (luck is no longer read anywhere in law/shadow).

**Orchestrator (`shadow_crud.npc_kill_consequences`):**
- **Non-forced path, per player:**
  - `info = law_crud.stealth_info(db, cid, s)`, `masked = wears_mask(...)`;
  - `chance_i = sc.member_chance(base, info.reduction_pct, masked, fame_witness_pct(...))`;
  - keep `info.reduction_pct` on `_Member`.
- Then `group_chance` and one roll, as today.
- Each `register_crime(...)` call (immediate and deferred) passes the new kwarg `stealth_reduction_pct=member.reduction_pct`.
- **Forced path** (guard encounter or switch off) passes `None`.
- `law_crud.record_crime` / `register_crime` gain the optional kwarg `stealth_reduction_pct=None` and store it. Jail escape and other callers are unchanged and store NULL.

**Reveal (`shadow_crud.roll_reveal`):** `sc.reveal_chance(susp, bool(crime.masked), s, crime.stealth_reduction_pct or 0)`. Staff reveal is unaffected (no roll).

**Staff read models:** `shadow_crud` crimes list (:435) and `law_crud.admin_character` crimes (:1139) gain `stealth_reduction_pct: Optional[float]`. The matching Pydantic out-schemas (`ShadowCrimeOut`, the law admin crime schema) gain `stealth_reduction_pct: Optional[float] = None`. These are staff-only.

**Settings schemas (`schemas.py:4021` `ShadowSettingsFields`):** mirror the dataclass (remove 5 fields, add 5). The response and body shapes are otherwise unchanged. `update_settings` is generic (iterates `SETTINGS_FIELDS`), so it needs no code change beyond the schema.

### 3.4 API contracts

**New — `GET /characters/{character_id}/stealth`** (character-service, `shadow_api.py`, next to `/{character_id}/renown`)
- Auth: `visibility.require_private_access` (owner, or staff with `characters:read`), the same as `/renown`. 404 unknown character, 403 stranger.
- 200 → `schemas.StealthPlayerOut`:
```json
{
  "stealth": 40,
  "subclass_bonus": 30,
  "subclass_name": "Ассасин",
  "effective": 70.0,
  "reduction_pct": 35.0,
  "pct_per_point": 0.5,
  "max_reduction_pct": 90.0
}
```
- Field notes:
  - `stealth` is the stored total (points + gear + food + perks), the same number the profile shows;
  - `subclass_bonus` is 0 and `subclass_name` is null without a stealth subclass;
  - `effective` = eff(stealth + bonus).
- NPC character: the same shape (harmless). Deploy-skew: stealth 0 with the WARNING.
- Read-only; no rate limit needed (the same class as `/renown`). No body. The path id is typed `int`.

**Changed (additive / semantic only):**
- `POST /attributes/{id}/upgrade` (attributes): the body accepts `stealth` (optional, ≥ 0, default 0). The response's `updated_attributes` includes `stealth`.
- `GET /attributes/{id}` and the admin attribute endpoints: the payload includes `stealth`.
- `POST /attributes/` (create from character-service/RabbitMQ): optional `stealth`, default 0.
- Inventory item create/update/read: optional `stealth_modifier`.
- `GET/PUT /characters/admin/shadow/settings`: the settings field set changes (5 removed, 5 added). This is a breaking change for the admin frontend only, and it ships in the same deploy.
- Staff crime lists: `+stealth_reduction_pct`.
- Encounter/jail player payloads (`flee_chance_pct`, `escape_chance_pct`): same fields, new maths.
- Subrace admin create/update: `stat_preset` accepts `stealth`.

**Unchanged:** battle-service, autobattle, dungeon-service, skills-service, locations-service, `PUT /characters/internal/npc-status/{id}`, nginx.

### 3.5 Security
- The new endpoint is private (owner/staff). It reveals only the caller's own derived number plus the public-to-owner settings (per-point, max). It does not expose crime rows, chances, rolls or base location values.
- No new permissions. Shadow settings keep `reputation:settings` / `reputation:read`; attribute admin keeps its existing guards; upgrade keeps JWT + ownership. The RBAC test is unchanged.
- Input validation:
  - upgrade `stealth ≥ 0` and counted in `total_needed` against free points (no free stat);
  - item `stealth_modifier` is an int like its siblings;
  - settings bounds per §3.3;
  - preset non-negative and sum = 100 (root validator).
- SQL: only parameterised `text()`. The deploy-skew fallback catches only the specific missing-column error and logs it; nothing else is swallowed.
- Randomness stays server-only (`law_crud.rng()`). Chance and roll are stored on the crime row; the reduction snapshot is stored too.

### 3.6 Frontend (all `.tsx`/`.ts`; Tailwind + design system; 360 px+; no `React.FC`; every API error shown in Russian)

Label everywhere: **«Скрытность»**. Item modifier key: `stealth_modifier`. Stat key: `stealth`.

**Player side**
- `ProfilePage/constants.ts`: `STAT_LABELS.stealth`, `PRIMARY_STATS`, `MAIN_STATS` (tiered bar), `UPGRADEABLE_STATS`.
- `redux/slices/profileSlice.ts`: `CharacterAttributes.stealth`, `UpgradeStatsPayload.stealth`, item `stealth_modifier`.
- `StatsTab/StatDistributionPanel.tsx`: verify it is list-driven and the typing compiles.
- `StatsTab/PrimaryStatsSection.tsx` (or `DerivedStatsSection.tsx`; the developer picks the place that reads best next to the stealth row): a muted line **«−X % к шансу быть замеченным»** from `getStealth(characterId)`.
  - With a subclass bonus, append «(вкл. +30 от подкласса «Ассасин»)».
  - Tooltip: «Шанс заметить преступление = база места × (1 − снижение) … Предел — {max_reduction_pct} %» plus `STAT_CAP_SHORT`.
  - Fetch only for the viewer's own character (the same ownership condition the ReputationTab uses for `/renown`). Refetch when `attributes.stealth` changes.
  - On error, show an inline Russian message «Не удалось загрузить влияние скрытности».
- `api/shadow.ts`: `getStealth(characterId): Promise<StealthInfo>` + the interface.
- `ProfilePage/InventoryTab/ItemDetailModal.tsx`:
  - `MODIFIER_FIELDS` + `MODIFIER_TO_STAT` (`stealth_modifier → stealth`);
  - when `item.is_mask`, a small badge **«Скрывает личность»** (design-system tokens; muted).
- `ProfilePage/CraftTab/GemSocketModal.tsx` `MODIFIER_LABELS`.
- `ProfilePage/PerksTab/PerkDetailModal.tsx` and `TitlesTab/TitleCard.tsx`: attribute label maps.
- `CreateCharacterPage/StepBlood/StatExplainer.tsx` `STAT_EFFECTS`: «Скрытность — снижает шанс, что преступление заметят; помогает сбежать от стражи и из тюрьмы. В бою не действует».
- `CommonComponents/CharacterPassport/types.ts` `PASSPORT_STAT_ORDER` + labels in `derived.ts`.
- `CommonComponents/ItemTypeLine.tsx`: «Маска» → **«Скрывает личность»**.

**Admin side**
- `ItemsAdminPage/itemFormRules.ts` (items and food share it): add `stealth_modifier` to the modifier field list.
- `ItemsAdminPage/ItemForm.tsx`:
  - legend «Маска» → «Личность»;
  - checkbox label **«Скрывает личность»**;
  - `MASK_HINT` → «Свидетели видят преступника, но не узнают его: дело не приписывается персонажу сразу, слава не учитывается. Скрытность предмет даёт только через модификатор «Скрытность»»;
  - head-only behaviour unchanged.
- `Admin/PerksPage/PerkForm.tsx`: condition attribute + flat bonus option `stealth`.
- `Admin/CharactersPage/tabs/AttributesTab.tsx` + `types.ts`: the `stealth` field.
- `Admin/TitlesPage/TitleForm.tsx`: condition attribute `stealth`.
- `Admin/AdminRaces/StatPresetEditor.tsx` + `redux/slices/racesSlice.ts`: `stealth` (default 0). The sum-to-100 indicator includes it.
- `api/shadowAdmin.ts` + `Admin/ReputationPage/ShadowSettingsTab.tsx` («Свидетели» group):
  - remove the 5 old fields;
  - add «Снижение за очко скрытности, %» (hint «Шанс × (1 − скрытность × значение / 100); скрытность — эффективная, после капа»);
  - add «Предел снижения, %»;
  - add «Скрытность подкласса «Ассасин» / «Фокусник» / «Агент»» (int, «очки скрытности, добавляются до капа; действуют на свидетелей, бегство и побег»);
  - base hints mention «множится на (1 − снижение скрытности)»;
  - group: «+N % к шансу за каждого участника после первого (множитель)»;
  - max ≤ 100;
  - fame tier column header/hint «Узнаваемость, % (множитель)»;
  - remove any «ловкости + удачи» text.
- `api/lawAdmin.ts` + `Admin/ReputationPage/LawSettingsTab.tsx`:
  - flee hint «Прибавка за каждое эффективное очко скрытности + ловкости»;
  - escape hint «Прибавка за каждое эффективное очко скрытности»;
  - subclass bonus note.
- `Admin/ReputationPage/UnresolvedCrimesTab.tsx` and `Admin/CharactersPage/tabs/LawPanel.tsx`: show `stealth_reduction_pct` («Скрытность: −X %», «—» for null).
- **Not touched:** battle UI, mob/NPC editors, dungeon editor, `AuctionListingDetail` (generic), `statCaps.ts`.

### 3.7 Data flow
```
Upgrade:  Profile → POST /attributes/{id}/upgrade {stealth:n} → attributes TX: apply_attribute_modifiers(+stealth) → character_attributes.stealth
Gear/food: inventory equip/eat → build_modifiers_dict {"stealth": m} → POST /attributes/{id}/apply_modifiers | /internal/{id}/satiety → stealth ±m
Crime:    battle-service → PUT /characters/internal/npc-status/{npc} → shadow_crud.npc_kill_consequences
            per player: SQL character_attributes.stealth(+agility) ─┐ (missing column → WARNING, 0)
                        SQL tree tables → subclass points ──────────┼→ eff → reduction → member chance (× fame unless masked)
                        SQL equipment_slots+items.is_mask ──────────┘
            group = max × (1 + extra%) → clamp 5..100 → one roll → register_crime(..., stealth_reduction_pct snapshot)
Reveal:   law_pass._reveal_crimes → roll_reveal: reveal_chance(susp, masked) × (1 − snapshot)
Flee/escape: law_flows → law_crud.flee_chance / escape_chance → stealth_info (+subclass, caps)
Profile:  ProfilePage → GET /characters/{id}/stealth (owner) → {reduction_pct, subclass_bonus, ...}
```

### 3.8 Rollout
- All three migrations auto-run at container start in the same compose deploy.
- Skew window: if character-service serves a kill or a flee before attributes `009` runs, it uses stealth = 0 with a WARNING. Inventory `035` is independent: until it runs, nobody has a stealth item.
- Balance jump at deploy (accepted pre-beta):
  - everyone has stealth 0 (plus the subclass bonus);
  - the settlement base is 100 %, so almost every settlement crime is witnessed until players invest;
  - flee/escape lose agility/luck builds (escape per point doubled if it is still the default).
- Kill switch is unchanged (`witness_enabled`).
- **Post-deploy (PM):**
  - update the Технобук guide articles «Навыки и характеристики» (id 10) and «Репутация, закон и тень» (id 16) on prod;
  - optionally give existing mask items a `stealth_modifier` in the admin.

### 3.9 Tests impact
- `tests/law_world.py:51` and `tests/reputation_world.py:51`: the SQLite `character_attributes` gets `stealth INTEGER DEFAULT 0` (keep `luck`, since other code may read it).
- `shadow_world.set_attrs(f, cid, agility=0, luck=0, stealth=0)`.
- Add a test that **drops/omits the column** to prove the WARNING fallback (it must not break silently: assert the log record + stealth 0), and that other DB errors re-raise.
- Recompute assertions in `test_shadow_core.py`, `test_shadow_kill.py`, `test_shadow_reveal.py`, `test_law_core.py` and the flee/escape tests per the §3.3 table. Old tests that set agility/luck to lower the witness chance must switch to stealth.
- attributes-service: test fixtures that create `character_attributes` via the ORM pick up the column automatically. Raw SQL fixtures (if any) need the column.

### 3.10 Open business questions (defaults applied — do not block)
- **Q1 — Fame/group as multipliers:** the existing numbers are reused as percentages (legend ×1.15, +10 % per extra member). Alternative: bigger multipliers (e.g. ×1.25 per member).
- **Q2 — Escape re-tune:** `escape_per_point_pct` 0.15 → 0.30 (only if untouched), so a stealth-only build escapes about as well as an agility+luck build did. Flee is unchanged (it still sums 2 stats).
- **Q3 — Unclassified location base (`witness_base_default_pct`)** stays at 50. Locations default to `safe` anyway, so this applies only to a missing location.
- **Q4 — Notification text** «Свидетели видели лишь неизвестного в маске» is kept. Alternative: «…неизвестного, скрывшего лицо».
- **Q5 — Profile line for other players' profiles:** not shown (the endpoint is private). Only the owner sees the «−X %» line.
- **Q6 — The subclass bonus is not added to the profile stat number.** It is shown only in the «−X %» line as «вкл. +30 от подкласса». Alternative: show «40 (+30)» next to the stat.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**All developer tasks: NO commits, NO pushes, NO `git add` (the user commits once at the end).** Backend: `python -m py_compile` on every modified file + the service's test suite inside its container. Frontend: `npx tsc --noEmit` and `npm run build` inside the frontend container. User-facing text in Russian.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|---|---|---|---|---|---|
| 1 | **character-attributes-service stealth stat** per §3.1/§3.2: migration `009_add_stealth`; model column; `PRIMARY_ATTRIBUTE_KEYS` (NOT `PRIMARY_DERIVED_EFFECTS`); schemas (`Field(0)` default, upgrade, admin update, responses); `create_character_attributes`; `VALID_FLAT_BONUS_KEYS`; perk-progress `attr_fields`; upgrade endpoint `total_needed` / modifiers / response; admin update path. Grep `charisma` across the service to catch every list. No commits/pushes/`git add`. | Backend Developer | DONE | `character-attributes-service/app/alembic/versions/009_add_stealth.py`, `app/models.py`, `app/constants.py`, `app/schemas.py`, `app/crud.py`, `app/main.py` | — | Migration up/down clean on MySQL; a new character gets stealth 0 (not 1); upgrading `stealth` consumes free points and raises the stored total; equip/food/perk `{"stealth": n}` changes it and the reversal restores it; `/recalculate` leaves stealth untouched; py_compile + service tests pass. |
| 2 | **inventory-service stealth modifier** per §3.1/§3.2: migration `035_item_stealth_modifier`; model; `MAIN_STAT_FIELDS` (sharpening/gems included), `STAT_DISPLAY_NAMES`, `build_modifiers_dict`; schemas (`ItemBase`, second item schema, `GATHERING_TOOL_FORBIDDEN_STAT_FIELDS`); mask validator text «Скрывать личность может только головной убор». Grep `luck_modifier`. No commits/pushes/`git add`. | Backend Developer | DONE | `inventory-service/app/alembic/versions/035_item_stealth_modifier.py`, `app/models.py`, `app/crud.py`, `app/schemas.py` | — | Up/down clean; item create/update/read round-trip `stealth_modifier`; equip sends `{"stealth": n}`; food with stealth goes into satiety modifiers; a whetstone/gem can target stealth; a gathering tool with stealth is rejected; py_compile + service tests pass. |
| 3 | **character-service shadow/law rewrite** per §3.1 (migration `041_stealth` incl. the UPDATEs, the guarded steps and the downgrade) and §3.3: ORM (`ShadowSettings`, `LawCrime.stealth_reduction_pct`, `LawSettings` default); `shadow_core` (settings fields/defaults, `SUBCLASS_LABELS`, `subclass_stealth_points`, `effective_stealth`, `stealth_reduction_pct`, new `member_chance` / `group_chance` / `reveal_chance`, validate); `law_core.chance(*points)`; `law_crud` (`subclass_of` moved + alias, `stealth_agility_of` with the missing-column WARNING fallback, `stealth_info`, new flee/escape, `record_crime`/`register_crime` kwarg, `admin_character` field; remove `attributes_of`/`effective_attributes_of` if unused); `shadow_crud` (orchestrator snapshot, `roll_reveal`, crimes list field); settings + crime schemas. No commits/pushes/`git add`. | Backend Developer | DONE | `character-service/app/alembic/versions/041_stealth.py`, `app/models.py`, `app/shadow_core.py`, `app/law_core.py`, `app/law_crud.py`, `app/shadow_crud.py`, `app/schemas.py` | — | Every number in the §3.3 table reproduces; chance reaches 100 and is never below 5; agility/luck no longer affect witnesses; a masked member gets no fame multiplier and creates a `masked` crime with no flat bonus; the snapshot is stored on rolled rows and NULL on forced rows/escape; reveal uses the snapshot; a missing `stealth` column → WARNING + 0, other errors raise; the migration is idempotent and the downgrade restores FEAT-199 columns/values; py_compile passes. |
| 4 | **character-service endpoint + presets/passport** per §3.2/§3.4: `GET /characters/{id}/stealth` (`StealthPlayerOut`, `require_private_access`); `STAT_PRESET_KEYS` + `StatPreset.stealth` + **root_validator** for the sum; `PASSPORT_STAT_KEYS` (11, comment); fallback preset `stealth: 0`. No commits/pushes/`git add`. | Backend Developer | DONE | `app/shadow_api.py`, `app/schemas.py`, `app/crud.py` | 3 | Owner/staff 200 with the documented shape (subclass bonus and cap applied); stranger 403; unknown 404; a preset with stealth 10 and the rest 90 is accepted, sum ≠ 100 is rejected with the same Russian text, and luck is no longer double counted; the passport lists stealth; py_compile passes. |
| 5 | **Frontend player side** per §3.6: profile constants/slice types, stat distribution, the «−X % к шансу быть замеченным» line via `api/shadow.ts` `getStealth` (owner only, refetch on change, Russian error), ItemDetailModal modifier + «Скрывает личность» badge, GemSocketModal, PerkDetailModal, TitleCard, StatExplainer, passport order/labels, ItemTypeLine label. No commits/pushes/`git add`. | Frontend Developer | DONE | `src/components/ProfilePage/constants.ts`, `src/redux/slices/profileSlice.ts`, `ProfilePage/StatsTab/PrimaryStatsSection.tsx` / `DerivedStatsSection.tsx` / `StatDistributionPanel.tsx`, `src/api/shadow.ts`, `ProfilePage/InventoryTab/ItemDetailModal.tsx`, `ProfilePage/CraftTab/GemSocketModal.tsx`, `ProfilePage/PerksTab/PerkDetailModal.tsx`, `ProfilePage/TitlesTab/TitleCard.tsx`, `CreateCharacterPage/StepBlood/StatExplainer.tsx`, `CommonComponents/CharacterPassport/types.ts`, `CommonComponents/CharacterPassport/derived.ts`, `CommonComponents/ItemTypeLine.tsx` | 1, 2, 4 (contracts) | Stealth is shown and upgradable; the effect line matches the endpoint; item/food/gem cards show «Скрытность»; mask items show «Скрывает личность»; no `React.FC`; 360 px layout OK; tsc + build pass. |
| 6 | **Frontend admin** per §3.6: itemFormRules + ItemForm («Скрывает личность», new hint), PerkForm, AttributesTab + types, TitleForm, StatPresetEditor + racesSlice, ShadowSettingsTab + `shadowAdmin.ts` (new fields/hints, removed fields, multiplier wording), LawSettingsTab + `lawAdmin.ts` hints, UnresolvedCrimesTab + LawPanel `stealth_reduction_pct`. No commits/pushes/`git add`. | Frontend Developer | DONE | `ItemsAdminPage/itemFormRules.ts`, `ItemsAdminPage/ItemForm.tsx`, `Admin/PerksPage/PerkForm.tsx`, `Admin/CharactersPage/tabs/AttributesTab.tsx`, `Admin/CharactersPage/types.ts`, `Admin/TitlesPage/TitleForm.tsx`, `Admin/AdminRaces/StatPresetEditor.tsx`, `redux/slices/racesSlice.ts`, `src/api/shadowAdmin.ts`, `src/api/lawAdmin.ts`, `Admin/ReputationPage/ShadowSettingsTab.tsx`, `Admin/ReputationPage/LawSettingsTab.tsx`, `Admin/ReputationPage/UnresolvedCrimesTab.tsx`, `Admin/CharactersPage/tabs/LawPanel.tsx` | 1–4 (contracts) | Shadow settings load/save with the new field set (no 422); no «ловкости + удачи» text left in admin; items/food/perks/titles/presets accept stealth; tsc + build pass. |
| 7 | **QA attributes + inventory:** upgrade with stealth (points consumed, total, response); create default 0 (schema + DB); apply_modifiers/satiety/expiry reversal with stealth; perk flat bonus `stealth`; `/recalculate` keeps stealth; guard test `StatsUpgradeRequest` fields ⊇ `PRIMARY_ATTRIBUTE_KEYS`; inventory `build_modifiers_dict` maps every `MAIN_STAT_FIELDS` entry (guard test), equip/eat payload contains stealth, sharpen/gem on stealth, gathering-tool rejection, mask validator text; negative/SQL-injection-ish inputs rejected. | QA Test | DONE | `character-attributes-service/app/tests/test_stealth_stat.py`, `inventory-service/app/tests/test_item_stealth.py` | 1, 2 | All new + existing tests pass in both containers. |
| 8 | **QA character-service:** `shadow_core` units for every §3.3 row (clamp 5/100, cap, subclass before cap, max reduction, fame multiplier, masked fame ignored, group multiplier, reveal × snapshot incl. NULL); `law_core.chance(*points)` back-compat; flee/escape numbers incl. subclass; orchestrator stores the snapshot (rolled) / NULL (forced, escape); reveal uses it; **missing-column fallback** (WARNING asserted, stealth 0) and other errors re-raise; settings validation (new bounds, removed fields rejected/ignored, max 100); `GET /{id}/stealth` owner/staff/stranger/404; StatPreset root_validator (stealth counted, luck not double counted, the same error text); passport keys; update fixtures (`law_world`, `reputation_world`, `shadow_world.set_attrs`) and recompute existing FEAT-198/199 assertions. | QA Test | DONE | `character-service/app/tests/test_stealth_*.py`, `tests/law_world.py`, `tests/reputation_world.py`, `tests/shadow_world.py`, existing `test_shadow_*.py`, `test_law_*.py`, preset tests | 3, 4 | The full character-service suite passes in the container. |
| 9 | **Docs:** `docs/services/character-attributes-service.md` (stealth stat, no derived fields), `inventory-service.md` (`stealth_modifier`), `character-service.md` (new formulas, settings, snapshot, `/stealth` endpoint, presets), `docs/SUBCLASS-PASSIVES.md` (out-of-battle stealth points for Ассасин/Фокусник/Агент), `docs/ARCHITECTURE.md` (columns), `docs/ISSUES.md` (nothing stale). No commits/pushes/`git add`. | Backend Developer | DONE | `docs/…` | 1–4 | Docs match the implemented formulas and contracts. |
| 10 | **Final review:** code vs §3; cross-service contracts (attributes ↔ inventory ↔ character ↔ battle unaffected); grep that no hand-written primary-stat list (backend + frontend) is missing stealth; py_compile + all three backend suites; tsc + build. **Live verification on localhost** (Chrome allowed): distribute points into «Скрытность» → profile total + «−X %» line; equip an item / eat food with a stealth modifier → stat changes and reverts on unequip/expiry; admin: create an item with «Скрывает личность» + stealth, save Shadow/Law settings; kill an NPC via «Нападение» in a settlement with stealth 0 → witnessed (100 %); raise stealth → crime row `witness_chance_pct` matches the formula and `stealth_reduction_pct` stored; guard encounter flee/jail escape chances show the new values; subrace preset with stealth saves; zero console errors. | Reviewer | DONE | — | 1–9 | PASS only with automated results + live verification recorded in §5. |
| 11 | **Post-deploy (PM, after the user pushes):** update the Технобук articles «Навыки и характеристики» (id 10) and «Репутация, закон и тень» (id 16) on prod with the new stat, formulas, subclass bonuses and «Скрывает личность»; tell the user about the balance jump (§3.8). | PM | TODO | prod DB content | deploy | Both articles describe stealth correctly. |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-04
**Result:** PASS

#### Correctness vs §1 / §3
- Witness maths (`shadow_core.member_chance` / `group_chance`): `base × (1 − reduction/100) × (1 + fame/100)`, where fame is skipped for a masked member. The group takes max(member) × (1 + per_extra/100 × (n − 1)) and clamps to 5..100. Agility, luck, the flat subclass % and the flat mask % are gone from the roll. OK.
- `stealth_reduction_pct = min(max_reduction (90), eff × 0.5)`. `effective_stealth` adds the subclass points to the raw stealth **before** `stat_caps.effective_stat`. OK.
- Subclass points (Ассасин 30 / Фокусник 30 / Агент 20) apply to witnesses, flee and escape through `law_crud.stealth_info`. OK.
- The mask means anonymity only: it still produces the `masked` status and suppresses fame, with no flat bonus. OK.
- Flee = `chance(base, pp, lo, hi, eff_stealth, eff_agility)`; escape = `chance(..., eff_stealth)`. `law_core.chance(*points)` stays back-compatible. OK.
- Reveal = clamp(… × (1 − snapshot/100)). The snapshot is stored on rolled rows (immediate + deferred) and is NULL on the forced path and on escape. `roll_reveal` passes `crime.stealth_reduction_pct or 0`. OK.
- Deploy-skew guard (`law_crud.stealth_agility_of`): the read runs in a `begin_nested()` savepoint. Only a `DBAPIError` whose message mentions `stealth` together with unknown/no such column leads to a WARNING and a fallback `SELECT 0, agility`. Every other error re-raises. A test covers it. OK.
- Upgrade: all 11 `StatsUpgradeRequest` fields are `Field(0, ge=0)`, `stealth` counts in `total_needed`, and the schema default is 0 (not 1). OK.
- Presets: the `root_validator` sums every key once and keeps the same Russian error. The passport has 11 keys. OK.

#### Cross-service contracts
- attributes `character_attributes.stealth` (009) is read by character-service raw SQL `SELECT stealth, agility`. The column name and type match.
- inventory `build_modifiers_dict` → `{"stealth": n}` → attributes `apply_attribute_modifiers` (`stealth` ∈ `PRIMARY_ATTRIBUTE_KEYS`, ∉ `PRIMARY_DERIVED_EFFECTS`). Verified live: equipping raised the stored stealth from 10 to 30.
- battle, dungeon, autobattle, skills and locations are unaffected. Battle reads attributes by key, and an extra key is ignored. The battle (1859) and dungeon econ/entry suites pass.
- A grep of the hand-written stat lists shows `stealth` / `stealth_modifier` everywhere in scope. The only lists without it are mob/NPC/dungeon/bestiary/battle UI, all out of scope per D12.

#### Migrations
- Single head per service: attributes `009_add_stealth` ← 008, inventory `035_item_stealth_modifier` ← 034, character `041_stealth` ← 040. Ids ≤ 32 chars.
- All three have guarded upgrade and downgrade, and none touches an ENUM.
- The local DB is at all three heads. The shadow row is 100/70/40/25/max 100 and escape is 0.300.

#### Security
- `GET /characters/{id}/stealth` uses `require_private_access`. Live results: owner/admin 200, no token 401, unknown id 404.
- No new permissions are added. SQL is parameterised; the DDL in migrations uses constants only.
- Frontend errors are shown in Russian, with retry, in `StealthEffectLine`.

#### Frontend rules
- No `React.FC`, no `any`, no SCSS/JSX touched. Tailwind and design tokens are used throughout.
- The new line is a muted `text-xs break-words` paragraph, fine at 360 px.
- **ItemDetailModal badge decision:** accepted the `ItemTypeLine` segment instead of a separate badge. Live, the card reads «ШЛЕМ • СКРЫВАЕТ ЛИЧНОСТЬ • ОБЫЧНЫЙ • УР. 0» in site-blue, and the same line covers the auction. A second badge would only duplicate it.

#### Automated Check Results
- [x] `python -m py_compile` (all changed .py) — PASS
- [x] `npx tsc --noEmit` (frontend container) — PASS (0 errors). On the host, tsc fails only on the pre-existing missing `react-icons` in host node_modules, which is unrelated.
- [x] `vite build` (frontend container, temp outDir) — PASS
- [x] pytest character-attributes-service — 975 passed, 2 skipped, 1 xpassed
- [x] pytest inventory-service — 2448 passed
- [x] pytest character-service — 8308 passed, 1 skipped
- [x] pytest battle-service — 1859 passed
- [x] pytest user-service (in its container) — 771 passed, 5 skipped
- [x] pytest dungeon-service econ (3 files) + `test_feat175_entry` — exit 0, all dots
- [x] pytest locations-service — 2757 passed
- [x] `sh scripts/check_econ_copies.sh` — all copies identical
- [x] `docker compose config` — PASS
- [x] Live verification (Chrome, http://localhost, admin, char 763) — PASS

#### Live Verification Results
- `/profile`:
  - shows «Скрытность 0 / −0 % к шансу быть замеченным», with a tooltip that gives the formula, 0.5 %/pt, the 90 % ceiling and the cap note;
  - after spending 10 points through the distribution panel (+ ×10 → Сохранить), the DB shows stealth 10 and stat_points 0, and the UI shows «10 / −5 %».
- `/admin/items`:
  - the head form shows the fieldset «Личность», the checkbox «Скрывает личность», the new hint, and the «Скрытность» modifier;
  - created item 1151 (head, is_mask = 1, stealth_modifier = 20), then gave and equipped it on 763;
  - attributes stealth went 10 → 30, `/stealth` → reduction 15, and the profile line shows «−15 %»;
  - the item modal reads «Скрытность +20».
- `/admin/reputation` → «Тень и слава»:
  - the new fields are present and the old ones are gone;
  - changed «Скрытность подкласса «Агент»» to 25 → PUT 200, and the DB is updated.
- Crime: internal `PUT /characters/internal/npc-status/33` (merchant at location 197, `dangerous`, base 40) with killer 763 (stealth 30, mask, fame 0) produced:
  - `witness_chance_pct` 34.00 = 40 × (1 − 0.15), which matches the formula;
  - roll 12.36, status `masked`, `stealth_reduction_pct` 15.00.
- «Нераскрытые дела» shows «Скрытность снизила шанс на 15 %».
- Flee/escape for 763, computed live in the container:
  - `StealthInfo(raw 30, subclass mage_salamander → 0 pts, eff 30, red 15, eff_agi 20)`;
  - flee 32.50 = 20 + (30 + 20) × 0.25;
  - escape 14.00 = 5 + 30 × 0.30.
- Console: zero errors on `/profile` and the admin reputation pages. API calls returned 200; the only 401 was the deliberate no-token probe.
- The local DB was restored from a pre-review mysqldump afterwards. The test item, crime, stat points and settings change were all rolled back, and NPC 33 is alive again.

#### Small fixes made by the reviewer
- `docs/ISSUES.md`: the negative-upgrade entry now says that all 11 fields have `ge=0`. Before, it said the other fields were untouched.
- This file: the unclosed §6 code fence is closed.

#### Issues Found
None blocking.

#### Notes / residual risks (non-blocking)
- Balance jump at deploy (per §3.8, accepted pre-beta): settlement base 100 % and stealth 0 for everyone, so almost every settlement crime is witnessed. Characters that relied on agility or luck lose flee/escape chance.
- During the deploy-skew window, character-service logs a WARNING on every flee or kill until attributes 009 runs. That is expected.
- The CI user-service job installs only `requirements.txt`. That is pre-existing; locally it was run inside the service container.

---

## 6. Logging (filled by all agents — in Russian)

Running log of progress updates. Each agent writes brief Russian entries here.

```
[LOG] 2026-11-04 — PM: фича создана по решениям пользователя (стат прокачиваемый, бегство/побег на скрытность, без противовеса, в бою не трогаем); запускаю анализ
[LOG] 2026-11-04 — Codebase Analyst: анализ готов (§2). Скрытность добавляется как «харизма без производных»: колонка в character_attributes и items, расширение списков статов (~10 мест в бэкенде, ~20 во фронте), переделка формул тени и закона в character-service. ENUM нет; бой, копии stat_caps и автобой не меняются. Найдены ловушки: валидатор суммы пресета подрасы привязан к «удаче», у схемы дефолт 1. Пассивки подклассов работают только в бою, поэтому бонус скрытности подклассам нужно решить отдельно (варианты A/B/C). Вынесено 9 вопросов пользователю.
[LOG] 2026-11-04 — PM: пользователь принял все предложения по 8 вопросам аналитика; запускаю архитектора
[LOG] 2026-11-04 22:45 — Architect: спроектировано 11 задач (4 бэкенд, 2 фронтенд, 2 QA, документация, ревью, пост-деплой статьи PM), 1 новый эндпоинт GET /characters/{id}/stealth, 3 миграции (attributes 009, inventory 035, character 041). Формула свидетелей мультипликативная (база × (1 − снижение) × слава × группа, 5..100), подклассы — очки скрытности до капа, маска = только анонимность, снимок снижения на деле для раскрытия, бегство = скрытность + ловкость, побег = скрытность. Статус IN_PROGRESS
[LOG] 2026-11-04 — Backend Developer: задачи 3–4 готовы (character-service). Миграция 041_stealth (новые поля скрытности в shadow_settings, удалены 5 старых ручек, базы 100/70/40/25 и максимум 100, law_crimes.stealth_reduction_pct, побег 0.15→0.30 только если не трогали) — upgrade/downgrade/upgrade и повторный прогон на локальном MySQL чистые. Формула свидетелей мультипликативная, подклассы — очки скрытности до капа, маска — только анонимность, снимок снижения на деле и в раскрытии; бегство = скрытность + ловкость, побег = скрытность. Защита от рассинхрона деплоя: нет колонки stealth → WARNING и 0, прочие ошибки падают. Новый эндпоинт GET /characters/{id}/stealth. Пресет подрасы: ключ stealth + root_validator суммы; паспорт — 11 статов. Фикстуры и ожидания старых тестов пересчитаны, добавлены тесты на fallback и эндпоинт
[LOG] 2026-11-04 — QA Test: задачи 7–8 готовы. Новые тесты: attributes test_stealth_stat.py (47: дефолт 0 при создании, прокачка списывает очки и не двигает производные, отрицательные/инъекции 422, перк-условие и плоский бонус на скрытность, еда с откатом по истечении, админ PUT, recalculate не трогает, миграция 009 вверх/вниз/повтор), inventory test_item_stealth.py (65: списки и guard-тест build_modifiers_dict по всем полям, заточка/камни/сломанный предмет, создание-обновление-чтение, инструмент сбора со скрытностью отклонён, надеть/снять шлёт ±stealth, equipment-modifiers, еда, заточка надетого, текст валидатора маски, миграция 035), character-service test_stealth_feat201.py (51: числа §3.3 для побега/бегства и всех подклассов, /stealth с капом и чужими подклассами, настройки тени — новые поля, границы 400, старые ручки игнорируются, 422 без новых полей; миграция 041 на эмуляции MySQL — правило побега 0.15→0.30, повтор без изменений, откат; root_validator пресета, паспорт 11 ключей). Багов в коде не найдено.
[LOG] 2026-11-04 — Backend Developer: задача 9 (документация) готова. character-attributes-service.md — стат «Скрытность» без производных, миграция 009, дефолт 0, запрет отрицательных значений в прокачке; inventory-service.md — stealth_modifier (миграция 035, заточка/камни/еда), подпись «Скрывает личность», маска только анонимность; character-service.md — миграция 041, мультипликативная формула свидетелей с примерами, новые настройки и валидация, снимок stealth_reduction_pct и раскрытие, бегство/побег на скрытности, защита от рассинхрона деплоя, GET /characters/{id}/stealth, root_validator пресета и 11 ключей паспорта; SUBCLASS-PASSIVES.md — очки скрытности Ассасин/Фокусник/Агент вне боя; ARCHITECTURE.md — колонки и описание потока тени. ISSUES.md — устаревших записей нет
[LOG] 2026-11-04 — Frontend Developer: задача 6 готова (админка). «Скрытность» добавлена в модификаторы предметов/еды, перки (условие и плоский бонус), атрибуты персонажа, условия титулов, пресет подрасы (по умолчанию 0, входит в сумму 100). Галочка у головных уборов — «Скрывает личность», подсказка переписана. Тень: убраны 5 старых полей, добавлены снижение за очко, предел снижения и очки скрытности подклассов; подсказки про множители, «ловкости + удачи» больше нигде нет. Закон: подсказки бегства/побега про скрытность. В списках дел — «Скрытность снизила шанс на X %». tsc и build в контейнере проходят
[LOG] 2026-11-04 — Frontend Developer: задача 5 готова (сторона игрока). «Скрытность» добавлена в STAT_LABELS/PRIMARY_STATS/MAIN_STATS/UPGRADEABLE_STATS (полоска в «Характеристиках» и распределение очков), типы profileSlice (stealth, stealth_modifier, is_mask), модификаторы в карточке предмета, самоцветы, перки, титулы, объяснение крови при создании и паспорт (11 статов). Новый api/shadow.ts getStealth: под строкой скрытности в профиле — «−X % к шансу быть замеченным» (+ «вкл. +N от подкласса «…»» при бонусе), подсказка с формулой и пределом, перезапрос при изменении стата, ошибка на русском с кнопкой «Повторить»; профиль всегда свой, так что запрос только для владельца. Метка «Маска» в строке типа предмета заменена: тип остаётся «Головной убор», добавлен сегмент «Скрывает личность» (виден в карточке предмета и на аукционе — отдельный бейдж не дублировал). tsc и build в контейнере проходят; /characters/{id}/stealth живой (401 без токена)
[LOG] 2026-11-04 23:25 — Reviewer: начал проверку (задача 10): код против §1/§3, контракты между сервисами, миграции, безопасность, правила фронтенда
[LOG] 2026-11-04 23:55 — Reviewer: автоматические проверки зелёные: py_compile, tsc и сборка в контейнере, pytest — атрибуты 975, инвентарь 2448, персонажи 8308, локации 2757, бой 1859, пользователи 771, данжи (экономика + вход) ок; копии econ одинаковые, docker compose config ок
[LOG] 2026-11-04 23:55 — Reviewer: живая проверка на localhost: строка «−X % к шансу быть замеченным» в профиле, распределение 10 очков в скрытность (−5 %), предмет «Скрывает личность» со скрытностью +20 надет (30 → −15 %), настройки тени сохраняются, убийство НПС в опасной локации дало шанс 34 % = 40 × 0.85 и снимок 15 %, бегство 32.5 % и побег 14 % по формуле; ошибок в консоли нет; локальная БД восстановлена из дампа
[LOG] 2026-11-04 23:55 — Reviewer: поправил формулировку записи про отрицательную прокачку в ISSUES.md (ge=0 теперь на всех 11 полях) и закрыл блок кода в §6; бейдж в карточке предмета заменён сегментом ItemTypeLine — принято
[LOG] 2026-11-04 23:55 — Reviewer: проверка завершена, результат PASS
```

**Статус: DONE (2026-11-04), ревью PASS.** Новый 11-й стат «Скрытность» (прокачка очками, снаряжение/заточка/самоцветы, еда, перки, пресеты рас); шанс быть замеченным = база места (100/70/40/25) × (1 − 0.5 %/ед., потолок 90 %) × слава × группа, 5–100 %; Ассасин/Фокусник +30, Агент +20 очков до капа; бегство = скрытность + ловкость, побег = скрытность; маска — только «Скрывает личность»; в профиле «−X % к шансу быть замеченным». Попутно закрыта дыра с отрицательными значениями при прокачке статов.
Осталось (PM, после деплоя): обновить статьи Технобука id 10 и id 16; сообщить о балансе (у всех скрытность 0 → в поселениях почти всегда замечают).
