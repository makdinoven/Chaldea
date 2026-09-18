# FEAT-168: Боевые эффекты зелий и свитков, книги опыта

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-09-19 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-168-slug.md` → `DONE-FEAT-168-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Этап 3 (последний) ребаланса профессий. Этап 1 — DONE-FEAT-164 (восстановление в покое, сытость от еды), этап 2 — DONE-FEAT-165 (переработка, камни заточки, подкатегории, Мистик). Сейчас расходники умеют почти ничего: у предметов есть восстановление здоровья/энергии/маны/выносливости и ровно один вид временного баффа (+% к опыту, книги). Из-за этого зелья алхимика, свитки и книги Мистика — пустые профессии по содержанию.

Цель: дать расходникам настоящие эффекты, чтобы алхимик и Мистик стали нужны в бою и в прокачке.

### Бизнес-правила

**Зелья (алхимик) — боевые, используются в бою из быстрых слотов пояса:**
- Мгновенное восстановление здоровья/маны/энергии/выносливости — уже есть, сохранить.
- **Боевые зелья на N ходов:** временные бонусы к характеристикам (сила, ловкость, урон, уклонение и т.п.). Действуют только в текущем бою.
- **Яды:** наносятся на оружие, параметры (прибавка к урону, длительность и т.д.) настраиваются у предмета. Пока действует нанесённый яд, новый нанести нельзя.
- **Противоядия/очищение:** что именно снимают, настраивается у предмета; полный контроль с пропуском хода не снимается никогда.
- Использование предмета не тратит ход, но **за ход можно применить только один предмет** из быстрых слотов.

**Свитки (Мистик):**
- Одноразовое заклинание в бою из быстрых слотов: урон, щит, лечение.
- Свиток телепорта — **вне этого этапа**, отдельной задачей (механики телепорта по свитку в игре нет).
- Свиток опознания — уже есть в игре, сохранить.

**Книги (Мистик):**
- Книга опыта персонажа — **нужно добавить** (сегодняшний `xp_bonus` ускоряет опыт профессии, а не персонажа).
- Книга опыта профессии — уже работает, сохранить. Книга опыта сбора — добавить. Тип баффа задаётся у предмета в админке.

**Общее:**
- Все эффекты настраиваются админом у предмета, без правок кода под каждый предмет.
- Максимальная редкость расходников — легендарная (правило из FEAT-164).
- Эффекты должны работать и в обычном бою, и в автобое, и в подземельях — везде, где идёт бой.
- Пояс = быстрые слоты; в бой игрок берёт то, что положил в пояс.
- Ошибки игроку — по-русски, без тихих отказов.

### UX / Пользовательский сценарий
1. Алхимик варит зелье силы, кладёт в пояс, в бою использует — на 3 хода +5 силы, в журнале боя видно применение и окончание эффекта.
2. Игрок наносит яд на оружие, противник получает урон несколько ходов.
3. Мистик создаёт свиток огня, применяет в бою — разовый урон.
4. Игрок читает книгу опыта профессии — быстрее качает кузнеца.

### Edge Cases
- Эффект длиннее боя — заканчивается вместе с боем.
- Повторное использование того же зелья — обновление или запрет (решить).
- Смерть носителя эффекта, выход из боя, автобой без участия игрока.
- Яд на оружии при смене оружия.
- Эффекты и снапшот участников боя.

### Вопросы к пользователю (если есть)
- [x] Тратит ли предмет ход → нет, и зелья, и свитки применяются бесплатно; свитки балансируются слабой силой эффекта
- [x] Повторное применение → **у навыков эффекты накладываются независимо** (кровоток 2 хода по 5 и кровоток 3 хода по 10 тикают отдельно). **У предметов** повторное применение того же предмета обновляет его собственный эффект (длительность = max, сила = новая), не складывая
- [x] Лимит за бой → **один предмет из быстрых слотов за ход** (общий лимит на зелья, свитки, яды). Отдельного лимита на бой нет. Баг «стопка расходуется целиком» починить
- [x] Яды → тонкая настройка в админке у предмета (сколько урона добавляет к оружию, сколько ходов действует и т.д.). Нанесение — такое же использование предмета, один за ход. **Пока действует старый яд, новый нанести нельзя**
- [x] Очищение → тонкая настройка в админке (что именно снимает). **Полный контроль с пропуском хода снять нельзя никогда** — это правило движка, а не настройка предмета
- [x] Свитки урона → считаются по обычной боевой формуле (криты, сопротивления, уклонение)
- [x] Книги/свитки опыта → **гибкая настройка в админке**: у предмета указывается, какой опыт ускорять и на сколько. Источники: бои/PvE, отыгрыш (посты), задания, титулы, боевой пропуск, профессия, сбор. В одном предмете можно комбинировать несколько
- [x] Свиток телепорта → выносим отдельной задачей, в этот этап не входит; свиток опознания уже реализован

---

## 2. Analysis Report (Codebase Analyst)

Baseline: clean tree at `f50284f`. All line numbers below are from that commit.

### 2.0 Headline finding

**The in-battle effect engine this feature needs already exists and is complete.** FEAT-143/146 built a
turn-scoped effect system in `battle-service/app/buffs.py` that covers stat buffs, percent damage/resist
buffs, periodic damage (DoT), control effects, ownership-based duration ticking, proc chance vs. luck /
endurance, and multi-target application. Skills feed it; **items do not**. A consumable today carries
exactly four numbers (`health/mana/energy/stamina_recovery`) and one out-of-battle buff
(`buff_type`/`buff_value`/`buff_duration_minutes`, and the only `buff_type` the backend understands is
`xp_bonus`).

So the work is mostly **plumbing item data into an engine that is already there**, not building an engine.
The genuinely new mechanics are: weapon poisons (a persistent coating), cleanse/antidote (effect removal),
and any XP book that is not profession XP.

---

### 2.1 Affected Services

| Service | Type of change | Key files |
|---|---|---|
| inventory-service | new item-effect tables + admin CRUD; expose effects on item read and on the fast-slot payload; new `buff_type` values; gathering-XP multiplier hook | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py`, `app/alembic/versions/0NN_…` |
| battle-service | feed item effect/damage rows into the existing engine at the item step; poison coating; cleanse; per-battle item limits if wanted; log events | `app/main.py:2581-2645`, `app/buffs.py`, `app/inventory_client.py:91-129`, `app/redis_state.py:199-219`, `app/tests/test_item_usage.py` |
| autobattle-service | teach the item picker that effect items have value (today value == recovery only) | `app/strategy.py:157-174`, `app/main.py:254-255` |
| frontend | battle log lines for new events; item tooltip shows effects; admin item form gets an effect editor + new buff types | `pages/BattlePage/BattlePageBar.tsx`, `pages/BattlePage/SkillPicker/SkillPicker.tsx`, `pages/BattlePage/battleEffects.ts`, `ItemsAdminPage/ItemForm.tsx`, `ItemsAdminPage/itemFormRules.ts`, `ProfilePage/CraftTab/ActiveBuffIndicator.tsx` |
| character-service | only if a **character-XP** book is in scope: `add_rewards_to_character` is the single write point | `app/crud.py:2136-2185` |
| dungeon-service | **no changes.** It only creates a battle via `POST /battles/` and polls `/battles/internal/{id}/state` (`app/gameplay.py:1197-1318`, `app/http_clients.py:317-388`). Item effects work there for free. |
| party-service / battle-pass-service | no changes |

---

### 2.2 Battle engine & turn flow (battle-service)

**One turn = one POST** `/{battle_id}/action` → `_make_action_core` (`main.py:2190-3051`). A single request
carries **all four** actions at once:
`SkillSelection = {attack_skill_id, defense_skill_id, support_skill_id, item_id}` (`schemas.py:22-29`)
plus `target_id` and `ally_target_id` (`schemas.py:32-41`).

Order inside a turn:
1. `decrement_cooldowns` (`main.py:2242`, impl `battle_engine.py:189`)
2. skill ownership + cooldown validation (`main.py:2250-2270`)
3. **control check** `evaluate_control` (`main.py:2297`, impl `buffs.py:94`) — Stun / Poison:paralysis null every
   action **including `item_id`** (`main.py:2304`); Knockdown / Windburn null one skill type
4. first-cycle one-skill-type limit (`main.py:2329-2341`, impl `buffs.py:117`)
5. target resolution (`main.py:2359-2399`)
6. **support** effects (`main.py:2412-2494`) → 7. **defense** effects (`:2499-2579`) →
   8. **item** (`:2584-2644`) → 9. **attack** effects + damage (`:2651-2830`)
10. durability rolls (`:2835-2860`), skill costs `_pay_skill_costs` (`:2875`), cooldowns (`:2882-2893`)
11. `tick_periodic_effects` for the actor's own effects (`:2906`) → `decrement_durations` (`:2920`)
12. death check (`:2927-2944`), turn row in MySQL `write_turn` (`:2952`), Redis state save (`:3004`),
    WS `state_update` publish (`:3023-3035`), Mongo log via Celery `save_log.delay` (`:3040`).

**Participant state** lives in Redis only (`redis_state.py`, key `battle:{id}:state`, TTL 48 h,
`STATE_TTL_HOURS`). Shape at `redis_state.py:199-219`: per participant `hp/mana/energy/stamina` + `max_*`,
`team`, `character_id`, `cooldowns`, `fast_slots`, `equipment_durability`, `total_damage_*`. Effects live
in a sibling map `state["active_effects"][str(pid)]` (`redis_state.py:198`). MySQL holds only the battle
row and turn rows; MongoDB holds the per-turn event log (write-only, via Celery, exceptions suppressed).

**Effect record shape** (what `apply_new_effects` stores, `buffs.py:30-35, 72-77`):
`{name, attribute, magnitude, duration, owner_id, fresh}`. It is built from a raw row shaped exactly like
skills-service `SkillPerkEffect`: `{target_side, effect_name, chance, duration, magnitude, attribute_key}`
(`skills-service/app/models.py:123-137`). **This is the contract an item effect must mimic — nothing more.**

What `buffs.py` already does:
- `apply_new_effects(state, pid, rows, is_enemy, owner_pid)` `:38` — instant hp/mana/energy/stamina clamped
  to max; everything else appended to `active_effects` with `fresh=True` so it does not tick on the cast turn
- `tick_periodic_effects(state, pid)` `:132` — DoT (`bleeding`, `burn`, `poison` with
  `attribute_key="periodic_damage"`), emits `effect_tick` events
- `decrement_durations(state, pid)` `:172` — ticks only effects **owned** by the acting participant, so a
  debuff on an enemy decays on the caster's turn
- `evaluate_control(effects)` `:94` — Stun / Poison-paralysis / Knockdown / Windburn
- `_expand_complex_effect(name, magnitude)` `:216` — ArmorBreak / Freeze / Electrify / Daze / Wet / Holy /
  Curse expanded onto engine channels; `aggregate_modifiers` `:238`; `build_percent_damage_buffs` `:256`;
  `build_percent_resist_buffs` `:269`
- proc chance: `_filter_effects_by_chance` (`main.py:172`) — `chance + luck*0.1 − endurance*0.2`

**`docs/ISSUES.md` "DoT-эффекты и контроли не работают" is STALE** — that was fixed by FEAT-143 (see the
entry, updated during this analysis). DoT and controls work today.

**Does using an item cost a turn?** No, and it is not even a separate action: `item_id` rides along with up
to three skills in the same request, is free, has no cooldown and no per-battle cap. `first_cycle` explicitly
exempts items (`main.py:2330` comment). The only thing that blocks an item is a full-skip control
(`main.py:2304`).

**Frontend battle page** (all `.tsx`, Tailwind, **no redux slice** — state is component-local):
`pages/BattlePage/BattlePage.tsx` (draft state `:160-165`, POST body `:573-625`),
`BattlePageBar/BattlePageBar.tsx` (4 round slots `:699-745`, log `:918-929`),
`SkillPicker/SkillPicker.tsx` (fast-slot list `:196-231`, recovery text `:142-149`),
`CharacterSide/CharacterSide.tsx:40-73` + `EffectCircle` (active-effect bubbles over the portrait),
`battleEffects.ts` (`describeEffect` `:81-165`, `evaluateControl`, families `:27-29`).
The battle log formatter is a single function `formatBattleEvent` (`BattlePageBar.tsx:462-656`) handling
`skill_use`, `apply_effects`, `item_use`, `participant_timed_out`, `participant_defeated`, `control_skip`,
`control_block`, `effect_tick`, `damage`, `resource_spend`. **Unhandled → prints the raw English event name**
(fallback `:644-655`, `helpers/commonConstants.js:29-34`), which already happens for `item_broken`.

---

### 2.3 Skills system — what the item effects can reuse verbatim

Damage: `battle_engine.compute_damage_with_rolls` (`battle_engine.py:91-170`).
`final = (main_class_attr + attr.damage + weapon.effective_damage + entry.amount) × (1+buff%) × crit × (1−resist%)`,
with `weapon_slot ∈ {main_weapon, additional_weapons, no_weapon}` (`main.py:2806-2810`), dodge rolled once
per target (`main.py:2762-2783`), AoE via `resolve_aoe_targets` (`main.py:102`).
A damage **scroll** maps onto this with zero new math: one `damage_entry` row with
`weapon_slot="no_weapon"` and a `damage_type`, run through the same function. Same for a heal scroll
(instant `hp` effect) and a shield scroll (a `Resist:`/`percent_resist_*` effect with a duration).

Stat buffs: any key present in `GET /attributes/{id}` works as `attribute_key`, because
`aggregate_modifiers` → `apply_flat_modifiers` (`battle_engine.py:173`) just adds deltas onto the attribute
dict. Available keys: `strength, agility, intelligence, endurance, luck, charisma, damage, dodge,
critical_hit_chance, critical_damage, hp/mana/energy/stamina` (instant) —
`character-attributes-service/app/models.py:31-47`.

Admin vocabulary that already exists and could be reused for items (`AdminSkillsPage/skillConstants.ts`):
`DAMAGE_TYPES` :155-169, `WEAPON_SLOTS` :171-177, `STAT_MODIFIERS` :179-186,
`POISON_SUBTYPE_OPTIONS` :202-207, `COMPLEX_EFFECTS` :209-336 (14 effects), target sides in
`SkillEffectSections.tsx:94-137`. The whole skill effect editor is `AdminSkillsPage/SkillEffectSections.tsx`
(906 lines, 5 sections) — a good template for an item effect editor.

**Conclusion: combat potions, poisons (as effect payloads), damage/heal/shield scrolls need NO new battle
math.** They need a data channel from `items` into `apply_new_effects` / `compute_damage_with_rolls`.

---

### 2.4 Consumables today

**`items` columns** (`inventory-service/app/models.py:19+`): `item_type` enum includes `consumable` and
`scroll` (`:28-32`); `item_rarity` (`:36-38`) — `mythical/divine/demonic` are equipment-only
(`schemas.py:37-51`), so consumables already cap at **legendary**, matching the FEAT-164 rule;
`health/energy/mana/stamina_recovery` (`:149-152`); `buff_type`/`buff_value`/`buff_duration_minutes`
(`:76-78`); `is_food` (`:81`); `identify_level` (`:59`); flat stat modifiers `:120-166`.

**`active_buffs`** (`models.py:368-380`, migration `012_add_time_buffs.py`): one row per
`(character_id, buff_type)` (unique constraint), columns `buff_type / value / expires_at /
source_item_name`. `apply_buff` (`crud.py:1983`) is an **upsert that replaces** — re-reading a book resets
duration, never stacks. Expiry is **lazy** (`get_active_buff` `crud.py:1968`, `get_active_buffs` `:2019`) —
no cron. Nothing reads it except `get_xp_multiplier` (`crud.py:2035`); it never touches character stats.

**Ways to use an item today**

| Path | Where | In battle? |
|---|---|---|
| `POST /inventory/{cid}/use_item` | `main.py:1099-1146` | **not blocked** — the only "use" endpoint without `check_not_in_battle` (bug, see §2.8) |
| `POST /inventory/{cid}/use-buff-item` | `main.py:3110-3177` | blocked (`:3119`) |
| `POST /inventory/{cid}/eat-food` | `main.py:3197-3284` | blocked (`:3210`) |
| turn field `skills.item_id` | `battle-service/main.py:2584-2644` | **this is the only in-battle path** |

**In-battle item path in detail** (`battle-service/main.py:2584-2644`): match `item_id` against the cached
`participant["fast_slots"]`; best-effort `consume_item` (failure is logged, the effect still applies —
deliberate, `tests/test_item_usage.py:452`); apply recovery **from the cached slot fields**; `pop` the slot;
emit `item_use`. Food is refused server-side at `inventory/main.py:1555-1558`.

**Fast slots (belt).** `GET /inventory/characters/{cid}/fast_slots` (`inventory/main.py:1161-1214`) returns
`{slot_type, item_id, quantity, name, image}` — **no effect data**. battle-service re-fetches each item and
mixes in only the four non-zero recovery keys (`inventory_client.py:91-129`), then snapshots the result into
Redis at battle start (`main.py:214, 241`; `redis_state.py:211`). `quantity` is the total in inventory, not
per slot. Equipment changes are blocked in battle (`inventory/main.py:819, 1007`), so the belt is frozen for
the fight — which also means **the weapon cannot be swapped mid-battle** (removes one of the brief's edge
cases).

**FEAT-164 satiety** is the other temporary-modifier model, and it is *not* the right one to copy for combat
potions: `character_satiety` (`character-attributes-service/models.py:88-110`) is **one row per character**
(unique on `character_id`), writes flat deltas straight into the base stat columns via
`crud._apply_modifiers_internal`, and reverses them exactly once at expiry inside `regen.settle_regen`
(`regen.py:245-318`, expiry branch `:306-316`). It is out-of-battle, single-slot and lazily settled. Combat
effects belong in the Redis `active_effects` map instead.

---

### 2.5 Autobattle & dungeons

**dungeon-service:** creates a normal battle (`gameplay.py:1197-1318` room, `:1321+` corridor) and polls
`get_battle_state` (`http_clients.py:365-388`); party members act through the normal battle endpoints.
**Nothing to change** — whatever works in a battle works in a dungeon.

**autobattle-service:** stateless, listens on the Redis `your_turn` channel, builds a feature vector and
posts to `/battles/internal/{id}/action`. Item choice is `strategy._pick_best` (`strategy.py:157-174`):

```python
def value(slot):
    v  = need_hp   * slot.get("health_recovery", 0)
    v += need_mana * slot.get("mana_recovery",   0)
    v += need_energy * slot.get("energy_recovery", 0)
    v += 0.01 * slot.get("quantity", 0)
```
`item_id` is set only `if value(best) > 0` (`:172-173`). A buff potion, a poison or a damage scroll scores
**0** and will therefore **never** be used by autobattle. `main.py:254-255` likewise counts only
`health_recovery`/`mana_recovery` for the `hp_pots_left` feature. This is the single real parity gap.
The strategy already reads `runtime.active_effects` for its features (`main.py:232-238`), so it has the
data it needs.

---

### 2.6 XP buffs — the brief and the code disagree

`xp_bonus` has **exactly one** effect in the whole codebase: `award_profession_xp` (`crud.py:1435-1440`)
multiplies profession XP by `get_xp_multiplier`. Reached only from `execute_craft` (`crud.py:1890`) and
`refine_items` (`crud.py:2258`).

| XP kind | Table / column | Where it is added | Multiplier hook today |
|---|---|---|---|
| **Profession XP** | `character_professions.experience` (`models.py:348`) | `crud.award_profession_xp` `crud.py:1435` | **yes — this IS the existing book** |
| **Gathering XP** | `character_gathering_skills.experience` (`models.py:501-516`) | `crud.award_gathering` `crud.py:4089-4093`, endpoint `main.py:1648`, caller `locations-service/crud.py:6237-6259` | none — but same service, same session ⇒ **cheap** |
| **Character XP** | `character_attributes.passive_experience` | `character-service/crud.py:2136`, XP write `:2158-2173`; battle rewards `battle-service/main.py:284-326` → `character-service/main.py:3452`; also RP posts, quests, titles, battle-pass | none — and the buff table lives in **another service** ⇒ **expensive** (needs a new internal endpoint, e.g. `GET /inventory/internal/{cid}/xp-multiplier`, plus a call from `add_rewards_to_character`) |
| `active_experience` (skill points) | `character_attributes.active_experience` | `character-attributes-service/crud.py:136-153` | none |

So the brief's line «Книга опыта (+% к опыту персонажа) — уже есть» is inaccurate: **today's book is a
profession-XP book.** Requirement "книги опыта профессии — добавить" is therefore already shipped, while
"книга опыта персонажа" (which the brief assumes exists) is the one that is missing and is the most
expensive of the three.

Admin surface for books is tiny: `BUFF_TYPE_OPTIONS` has exactly one entry
(`ItemsAdminPage/itemFormRules.ts:135-137`), labels one entry (`CraftTab/ActiveBuffIndicator.tsx:14-16`),
the buff section shows only for `item_type === "consumable" && !is_food`
(`itemFormRules.ts:176`, form at `ItemForm.tsx:577-608`). `buff_type` is a free `String(50)` with **no
backend validation**, so new types cost one line each. The success message is hardcoded `"+N% XP"`
regardless of type (`inventory/main.py:3168`).

**Teleport scroll:** no mechanic exists. Teleporting today is an NPC service —
`character-service/crud.py:3147-3179` (`TELEPORT_ROLE`, `teleport_links` table, `characters.last_teleport_at`
cooldown, migration `015_teleport_cooldown`). An item-driven teleport is a genuinely new feature in
character-service + locations-service, unrelated to the battle work.
**Identification scroll:** already fully implemented (`items.identify_level` `models.py:59`,
`inventory/main.py:3044-3103`, frontend `InventoryTab/ItemContextMenu.tsx`, `ItemCell.tsx:43-48`). Nothing to do.

---

### 2.7 DB changes (proposal-level — Architect decides)

The shape that costs the least is a mirror of the skills tables, so battle-service can pass item rows
straight into `apply_new_effects` / `compute_damage_with_rolls` without translation:

- new `item_effects` — mirror of `skill_perk_effects` (`skills-service/models.py:123-137`):
  `item_id FK→items(id) ON DELETE CASCADE, target_side, effect_name, chance, duration, magnitude,
  attribute_key, description`
- new `item_damage_entries` — mirror of `skill_perk_damage` (`skills-service/models.py:103-120`):
  `item_id, damage_type, amount, chance, target_side, weapon_slot, aoe_*`
- likely a small discriminator on `items` for *how* the item is used (instant / coating-on-weapon /
  cleanse), unless that is inferred from `target_side`
- no schema change needed for new `buff_type` values (free string)
- inventory-service has Alembic (`alembic_version_inventory`, auto-migration in the Dockerfile); head at
  baseline is around `021_add_item_is_food` + the FEAT-165 series — Architect must check `alembic heads`
  before numbering.

Redis state is JSON and additive-friendly: new keys in `participant` (e.g. a poison coating, per-battle
item counters) default-absent for battles started before the deploy.

---

### 2.8 Risks

| Risk | Mitigation |
|---|---|
| **In-flight battles during deploy.** Redis state lives up to 48 h (`redis_state.py:26`) and `fast_slots` were snapshotted at battle start **without** effect data. After deploy, running battles have effect-less slots. | Every new field must be read with `.get(..., default)`; an item with no effect rows behaves exactly as today. Never require a new key to exist. Same rule the codebase already follows for `owner_id`/`fresh` (`buffs.py:193`, `:198`) and `dropped_out` (`schemas.py:290-320`). |
| **Effects stack without limit.** `apply_new_effects` always appends (`buffs.py:77`) and `aggregate_modifiers` sums (`buffs.py:238`). Drinking the same potion three turns in a row triples the bonus today. | This is the "повторное применение" question in §1 — it needs a decision *and* new code in `buffs.py` either way (refresh or reject); doing nothing means stacking. |
| **Autobattle would ignore every new item** (`strategy.py:169-173`). | Must be in scope, not a follow-up — otherwise autobattle players simply never drink buff potions. |
| **Unknown log events print raw English** (`BattlePageBar.tsx:644-655`). Already happening for `item_broken`. | Every new event type needs a branch in `formatBattleEvent` in the same PR. |
| **Mongo log is fire-and-forget** (`tasks.py`, `contextlib.suppress`), so the battle log is not a source of truth for effect state. | Keep all effect state in Redis; the log is display only. |
| **Test coverage of the engine is thin where it matters.** `tests/test_item_usage.py` **mocks out `buffs` entirely** (`:34-45`), so item + effect interaction is currently untestable there; `buffs.py` has no dedicated unit-test module (only `test_dodge_and_freshness.py` touches freshness). | New QA tasks must cover `buffs.py` directly (unit level) **and** the item branch of `_make_action_core` with the real `buffs` module. |
| **Cross-service contract.** Adding effects to `GET /inventory/items/{id}` changes a payload read by battle-service, photo-service (mirror models) and the frontend. Additive fields only. | Additive; no field removals or renames. |
| **`items` enum/table locks.** Any ENUM change on `items` locks the table; FEAT-165 hit this (see `DONE-FEAT-165` §risks). | Prefer new child tables over new ENUM values on `items`. |
| **Security.** `use_item` has no in-battle guard (§2.9 #3) and the in-battle item path trusts the Redis-cached slot rather than the inventory row (`main.py:2603-2611`). Adding real combat power to items raises the value of both holes. | Decide deliberately: keep "best effort" (a lost potion on a failed consume) or make consumption authoritative before applying the effect. |
| **Migration/rollback.** New child tables are drop-safe; no data backfill is needed (existing consumables simply have zero effect rows). | Down-migration = drop tables. |

---

### 2.9 Bugs found during analysis (added to `docs/ISSUES.md`)

1. **`docs/ISSUES.md` "DoT-эффекты и контроли не работают в боёвке" is stale** — fixed by FEAT-143
   (`buffs.py:94, 132, 216`; `main.py:2297, 2906`). Entry marked DONE.
2. **`item_broken` is not rendered in the battle log** — backend emits it (`battle-service/main.py:2849, 2860`),
   the frontend has no branch and no translation key, so the player sees the literal string `item_broken`.
3. **`POST /inventory/{cid}/use_item` has no `check_not_in_battle`** — the only "use" endpoint without it
   (`inventory/main.py:1099-1107`; compare `:3119`, `:3210`, and 9 other guarded endpoints).
4. **A fast slot is dropped after one use regardless of `quantity`** (`battle-service/main.py:2632`) — a
   stack of 5 potions in the belt yields exactly one use per battle. Possibly intentional ("одноразовое"),
   but it collides directly with the §1 question "сколько зелий за бой".
5. **`use-buff-item` always answers `"+N% XP"`** (`inventory/main.py:3168`) regardless of `buff_type` — will
   be wrong the moment a second buff type exists.
6. **`item_use` log line ignores `recovery.stamina`** (`BattlePageBar.tsx:514-530`), although the picker does
   show stamina (`SkillPicker.tsx:142-149`) and the engine applies it.

---

### 2.10 Questions for the user (refinement of §1, annotated with cost)

- **Тратит ли предмет ход?** Today it is free *and* stacks with all three skills in one request
  (`schemas.py:22-29`). Keeping it free = **zero work**. Making it cost the turn = one validation in
  `_make_action_core` + slot-locking in `BattlePageBar.tsx:699-745` — cheap, but it is a balance decision,
  not a technical one.
- **Лимит зелий за бой / кулдаун?** There is no counter today, and bug #4 above accidentally imposes
  "one use per belt slot per battle". A real counter is a new key in the participant state — cheap. Worth
  asking together with #4: should a stack of 5 potions give 5 uses?
- **Повторное применение того же эффекта?** Today it **stacks without limit** (`buffs.py:77`,
  `buffs.py:238`). All three answers (stack / refresh / reject) cost roughly the same small change; the
  user must pick.
- **Яды — на сколько ходов, урон фиксированный или от характеристик?** Both are cheap: a fixed-damage
  poison is an `effect_name="Poison"` row with `attribute_key="periodic_damage"` (already supported end to
  end, `buffs.py:91`); a stat-scaled poison would need a new formula. **Extra question the code raises:**
  does applying poison to a weapon cost a turn, does it survive the fight (weapon stays coated afterwards),
  and how many hits does one application cover? Weapons cannot be swapped in battle
  (`inventory/main.py:819`), so the brief's "яд при смене оружия" edge case only matters out of combat.
- **Свитки в бою — формула навыка или фикс?** Reusing `compute_damage_with_rolls` with
  `weapon_slot="no_weapon"` is free and gives crits, resists and dodge for nothing. A flat
  "ignores-everything" number is *more* work, not less. Recommend the skill formula unless the user wants
  scrolls to bypass resistances deliberately.
- **Книги опыта — какие именно?** The code says today's book is a **profession**-XP book, not a
  character-XP book (§2.6). So: (a) gathering-XP book — cheap, same service; (b) character-XP book —
  expensive, needs a cross-service multiplier lookup in `character-service`; (c) if a character-XP book is
  added, should it also apply to RP-post XP, quest XP and title XP, or only to battle XP?
- **Свиток телепорта** — no mechanic exists at all (§2.6). It is a separate feature in
  character-service/locations-service, not an extension of the battle work. Recommend splitting it out.
- **Очищение/противоядие** — what exactly does it remove: all debuffs, only DoTs, only controls, or N
  effects? The engine has no removal function yet (`buffs.py` only appends and decrements); adding one is
  ~15 lines, but the selection rule is a game-design answer.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Guiding principle

The analyst's headline finding is accepted: **no new battle math is built**. Items get two child tables whose
row shape is byte-for-byte the one `buffs.apply_new_effects` and `battle_engine.compute_damage_with_rolls`
already consume (`skill_perk_effects` / `skill_perk_damage`). Everything else is plumbing: expose the rows,
snapshot them into the fast-slot payload, feed them in at the existing item step, and render the resulting
events.

Three mechanics are genuinely new and are designed below: **weapon coating (poison)**, **effect removal
(cleanse)** and **XP-book types beyond profession XP**.

**Compatibility contract (applies to every task, non-negotiable):**

1. Battle state lives in Redis for up to 48 h and `fast_slots` were snapshotted at battle start **without**
   effect data. Every new key in the participant state, in a fast-slot dict and in an effect record is read
   with `.get(key, <default>)`. No code path may assume a new key exists.
2. An item with **zero** effect rows, `consumable_action` NULL and no coating columns must behave **exactly**
   as today (recovery only). This is the regression test QA must write first.
3. All payload changes are **additive** — no field is renamed or removed (`GET /inventory/items/{id}` is read
   by battle-service, photo-service mirror models and the frontend).

---

### 3.1 DB changes (inventory-service, one Alembic revision)

Revision `024_item_battle_effects` (down_revision = current head — Backend Dev runs `alembic heads` first;
at baseline that is `023_weapon_damage_backfill`). `version_table = alembic_version_inventory`, auto-migration
on container start as usual.

```sql
-- 1. Effect rows — mirror of skill_perk_effects (skills-service/app/models.py:123-137)
CREATE TABLE item_effects (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    item_id       INT          NOT NULL,
    target_side   VARCHAR(10)  NOT NULL DEFAULT 'self',   -- self | enemy | ally | all_allies
    effect_name   VARCHAR(50)  NOT NULL,
    description   TEXT         NULL,
    chance        INT          NOT NULL DEFAULT 100,
    duration      INT          NOT NULL DEFAULT 1,
    magnitude     FLOAT        NOT NULL DEFAULT 0,
    attribute_key VARCHAR(50)  NULL,
    CONSTRAINT fk_item_effects_item FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    INDEX ix_item_effects_item_id (item_id)
);

-- 2. Damage rows — mirror of skill_perk_damage (skills-service/app/models.py:103-120)
CREATE TABLE item_damage_entries (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    item_id         INT          NOT NULL,
    damage_type     VARCHAR(50)  NOT NULL,
    amount          FLOAT        NOT NULL DEFAULT 0,
    description     TEXT         NULL,
    weapon_slot     VARCHAR(20)  NOT NULL DEFAULT 'no_weapon',  -- scrolls default to unarmed math
    target_side     VARCHAR(10)  NOT NULL DEFAULT 'enemy',
    chance          INT          NOT NULL DEFAULT 100,
    aoe_shape       VARCHAR(12)  NOT NULL DEFAULT 'single',
    aoe_falloff     INT          NOT NULL DEFAULT 50,
    aoe_max_targets INT          NOT NULL DEFAULT 3,
    CONSTRAINT fk_item_damage_item FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    INDEX ix_item_damage_entries_item_id (item_id)
);

-- 3. Three nullable columns on items (VARCHAR, NOT an ENUM — FEAT-165 hit ENUM table locks;
--    nullable trailing columns are INSTANT DDL on MySQL 8)
ALTER TABLE items
    ADD COLUMN consumable_action    VARCHAR(20) NULL,   -- NULL/'instant' | 'weapon_coating' | 'cleanse'
    ADD COLUMN coating_turns        INT         NULL,
    ADD COLUMN coating_bonus_damage FLOAT       NULL;
```

**Rollback:** `DROP TABLE item_damage_entries; DROP TABLE item_effects;` +
`ALTER TABLE items DROP COLUMN consumable_action, DROP COLUMN coating_turns, DROP COLUMN coating_bonus_damage;`.
No data backfill in either direction — existing consumables simply have zero effect rows, so a downgrade
loses only data created by this feature. `downgrade()` must be written and must be reversible on a live DB.

**No change to `active_buffs`** — new `buff_type` values are plain strings in the existing table.

---

### 3.2 How each consumable kind maps onto the schema

| Kind | `consumable_action` | Rows |
|---|---|---|
| Recovery potion (today) | NULL | none — the four `*_recovery` columns, unchanged |
| Combat buff potion | NULL | `item_effects`, `target_side='self'`, `attribute_key='strength'`, `magnitude=5`, `duration=3` |
| Debuff potion / thrown flask | NULL | `item_effects`, `target_side='enemy'` |
| Damage scroll | NULL | `item_damage_entries`, `target_side='enemy'`, `weapon_slot='no_weapon'`, `damage_type='fire'` |
| Heal scroll | NULL | `item_effects`, `target_side='self'` or `'ally'`, `attribute_key='hp'` (instant, clamped to max) |
| Shield scroll | NULL | `item_effects`, `effect_name='Resist:all'` (or `percent_resist_*` via `attribute_key`), `duration=N` |
| **Poison (weapon coating)** | `'weapon_coating'` | `coating_turns`, `coating_bonus_damage`, plus optional `item_effects` with `target_side='enemy'` (e.g. `effect_name='Poison'`, `attribute_key='periodic_damage'`) that are inflicted on every weapon hit while the coating lasts |
| **Antidote / cleanse** | `'cleanse'` | `item_effects` rows with `effect_name='Cleanse'`, `target_side='self'`/`'ally'`, `attribute_key` = what to remove, `magnitude` = how many (0 = all matching) |
| XP book | NULL | no rows — `buff_type` / `buff_value` / `buff_duration_minutes`, unchanged |

`attribute_key` vocabulary for a `Cleanse` row (admin-selectable, this is the whole "what does it remove"
configuration):

| `attribute_key` | Removes |
|---|---|
| `debuff` | every effect on the target owned by **someone else** (the standard antidote) |
| `periodic_damage` | DoTs only (`bleeding`, `burn`, periodic `poison`) |
| `control_partial` | `Knockdown` / `Windburn` (partial controls) |
| `stat_down` | effects whose aggregated contribution is negative (stat/resist debuffs) |
| `all` | every removable effect, including the target's own buffs |
| any effect name, e.g. `Bleeding` | exactly that effect |

**Engine rule, not an item setting:** a **full skip-turn control is never removable.** `Stun`, and `Poison`
with `attribute_key='paralysis'` (the two things `buffs.evaluate_control` returns as `full_skip`) are filtered
out of every removal regardless of the configured `attribute_key`, including `all`. This lives in `buffs.py`,
not in the item row, so no admin configuration can ever bypass it.

---

### 3.3 API contracts

#### 3.3.1 New Pydantic schemas (inventory-service, **Pydantic v1 syntax**, `class Config: orm_mode = True`)

```python
class ItemEffectIn(BaseModel):
    target_side: str = "self"          # self | enemy | ally | all_allies
    effect_name: str                   # 1..50 chars
    description: Optional[str] = None
    chance: int = 100                  # 0..100
    duration: int = 1                  # 0..100
    magnitude: float = 0.0             # -10000..10000
    attribute_key: Optional[str] = None

class ItemEffectOut(ItemEffectIn):
    id: int
    class Config: orm_mode = True

class ItemDamageIn(BaseModel):
    damage_type: str                   # from DAMAGE_TYPES
    amount: float = 0.0                # -10000..10000
    description: Optional[str] = None
    weapon_slot: str = "no_weapon"     # main_weapon | additional_weapons | no_weapon
    target_side: str = "enemy"
    chance: int = 100                  # 0..100
    aoe_shape: str = "single"
    aoe_falloff: int = 50              # 0..100
    aoe_max_targets: int = 3           # 1..10

class ItemDamageOut(ItemDamageIn):
    id: int
    class Config: orm_mode = True
```

`ItemBase` gains `consumable_action: Optional[str] = None`, `coating_turns: Optional[int] = None`,
`coating_bonus_damage: Optional[float] = None`.
`ItemCreate` gains `effects: List[ItemEffectIn] = []` and `damage_entries: List[ItemDamageIn] = []`
(**replace-all** semantics on update, same as the skills perk editor).
`Item`, `ItemDetailResponse` and the fast-slot response gain `effects: List[ItemEffectOut] = []` and
`damage_entries: List[ItemDamageOut] = []`. `ItemBulkResponse` is **not** changed (keeps list payloads small).

#### 3.3.2 Admin CRUD — **no new endpoints**

Effect rows ride inside the existing item payloads, exactly like `SkillPerkCreate.effects`:

- `POST /inventory/items` — `Depends(require_permission("items:create"))`, unchanged path/permission
- `PUT  /inventory/items/{item_id}` — `Depends(require_permission("items:update"))`; nested lists are
  delete-then-recreate inside the same transaction (mirror `skills-service` perk update)
- `GET  /inventory/items/{item_id}` — now returns `effects` / `damage_entries` / the three new columns
- `DELETE /inventory/items/{item_id}` — child rows go by `ON DELETE CASCADE`

**Consequence: no new rows in `permissions` / `role_permissions`, therefore no RBAC-test additions
(CLAUDE.md §10.13).** This is deliberate — the effect editor is part of the item editor.

#### 3.3.3 `GET /inventory/characters/{character_id}/fast_slots` (extended, additive)

```json
[
  {
    "slot_type": "fast_slot_1",
    "item_id": 42,
    "quantity": 5,
    "name": "Зелье силы",
    "image": "…",
    "health_recovery": 0, "mana_recovery": 0, "energy_recovery": 0, "stamina_recovery": 0,
    "consumable_action": null,
    "coating_turns": null,
    "coating_bonus_damage": null,
    "effects": [
      {"target_side": "self", "effect_name": "StatModifier", "attribute_key": "strength",
       "magnitude": 5.0, "duration": 3, "chance": 100}
    ],
    "damage_entries": []
  }
]
```

Auth unchanged (`get_current_user_via_http` + ownership check). Existing consumers that ignore the new keys
keep working.

#### 3.3.4 `GET /inventory/internal/characters/{character_id}/xp-multiplier` (new, internal)

```
Query: buff_type=character_xp_bonus   (default "xp_bonus")
Auth : Depends(verify_internal_token) — same guard as the other /inventory/internal/* routes
200  : {"character_id": 7, "buff_type": "character_xp_bonus", "multiplier": 1.25}
404  : character not found  → caller treats as 1.0
```

Called by character-service only. **Fail-open:** any exception/timeout on the caller side ⇒ multiplier 1.0 +
a warning log. XP must never be lost because the buff lookup failed.

#### 3.3.5 `POST /inventory/{character_id}/use-buff-item` (message fix, bug #5)

Response shape unchanged; `message` becomes type-aware:
`"Бафф активирован: +25% к опыту персонажа на 60 мин"` /
`"…к опыту профессии…"` / `"…к опыту сбора…"`, falling back to `"…к опыту…"` for an unknown type.

#### 3.3.6 battle-service — no new endpoints

`SkillSelection.item_id` (`schemas.py:22-29`) is unchanged and remains the only in-battle item channel.
The battle state returned by `GET /battles/{id}/state` and `/battles/internal/{id}/state` gains, per
participant, `weapon_coating` (nullable object, see §3.5) — additive, read with `.get()` everywhere.

---

### 3.4 Turn rules

**Free, one per turn.** Using an item costs no turn and no action slot — unchanged. The per-turn limit of
one item is already structural: a turn is one POST carrying one `item_id` field. Backend Dev must **not**
add a second item channel, and the frontend must keep exactly one item slot per round. Potions, scrolls and
poisons all flow through this one field, so they share the limit by construction.

**Bug fix (ISSUES #4): a stack is no longer consumed whole.** At the item step the cached slot's
`quantity` is decremented by 1; the slot is popped from `fast_slots` only when it reaches 0.
**Correction (review #1, issue 14):** slots snapshotted before this deploy *do* carry `quantity` — the
old `inventory_client.get_fast_slots` already wrote it — so in-flight battles get the full stack of uses
too. `int(slot.get("quantity", 1) or 1)` is kept as a defensive default for an unusable value (missing /
None / 0 / non-numeric), in which case the slot is spent in one use.

**Order inside the turn is unchanged:** support → defense → **item (step 8)** → attack. A buff potion
therefore buffs the same turn's attack, which is the expected player experience.

**Full-skip control still nullifies the item** (`main.py:2304`) — unchanged.

**Refresh, never stack.** `buffs.apply_new_effects` currently appends unconditionally (`buffs.py:77`), so the
same buff applied twice doubles. Per §1 it must **refresh**: when an effect with the same
`(name, attribute, owner_id)` already sits on the target, update it in place — `duration = max(old, new)`,
`magnitude = new`, `fresh = True` — instead of appending. **Note: this changes skill behaviour too**, because
skills go through the same function. That is intended (it is the stated rule and it closes the
unlimited-stacking hole), and it is called out here so Reviewer and QA treat it as a deliberate global change
rather than a regression.

---

### 3.5 Weapon coating (poison) — new state

Stored on the participant in the Redis state, **nullable and absent by default**:

```json
"weapon_coating": {
  "item_id": 91,
  "name": "Яд гадюки",
  "bonus_damage": 12.0,
  "turns_left": 4,
  "effects": [ {"target_side": "enemy", "effect_name": "Poison",
                "attribute_key": "periodic_damage", "magnitude": 6, "duration": 3, "chance": 100} ]
}
```

- **Applying** (item with `consumable_action='weapon_coating'`): if
  `part.get("weapon_coating")` is present with `turns_left > 0`, the application is **refused without
  failing the whole turn** — the item is not consumed, the player's skills still resolve, and a
  `item_rejected` event is appended with `reason: "coating_active"`. The frontend renders
  «На оружии уже нанесён яд — нанести новый нельзя, пока действует прежний.» and additionally disables the
  item in the picker when the state already shows a coating. (Rejecting the whole action with 400 would cost
  the player their turn — not acceptable.)
- **Effect on damage:** for every landed damage entry whose `weapon_slot != "no_weapon"`,
  `coating["bonus_damage"]` is added to `damage_entry["amount"]` before `compute_damage_with_rolls`, so the
  bonus passes through buffs, crit and resists like any other damage — the "normal damage formula" rule.
  The coating's own `item_effects` rows are applied to each target that actually took damage this turn
  (`apply_new_effects(..., is_enemy=True, owner_pid=attacker)`), once per target per turn.
- **Duration:** `turns_left` is decremented at step 11, next to `decrement_durations`, i.e. on the coating
  owner's own turn. At 0 the key is deleted and a `weapon_coating_expired` event is emitted.
- **Scope:** the coating lives in the battle state only, so it ends with the battle. Weapons cannot be swapped
  in battle (`inventory/main.py:819`), which removes the brief's "яд при смене оружия" edge case.
- Everything reads `part.get("weapon_coating")` ⇒ in-flight battles simply have no coating.

---

### 3.6 `buffs.py` — the three additions

```python
def apply_new_effects(state, pid, raw_effect_rows, is_enemy=False, owner_pid=None) -> None:
    # unchanged signature; internal change: refresh-in-place instead of append (§3.4)

def remove_effects(state, pid, *, selector: str, limit: int = 0) -> List[Dict]:
    """Remove effects from participant `pid` matching `selector`
    (debuff | periodic_damage | control_partial | stat_down | all | <effect name>).
    limit = 0 means "all matching". Returns the removed effect dicts for the battle log.
    NEVER removes a full-skip control: Stun, or Poison with attribute 'paralysis'
    — engine rule, not configurable by any item."""

def is_unremovable(eff: Dict) -> bool:
    """True for effects that grant a full skip (see evaluate_control)."""
```

**Addendum 2 (user correction, task #3 — supersedes the global refresh rule of §3.4):** the refresh rule
applies **only to item effects**, not to skill effects.

```python
def apply_new_effects(state, pid, raw_effect_rows, is_enemy=False,
                      owner_pid=None, source=None) -> None:
    # source: ("item", item_id) — or None (the default), which is how SKILLS call it
```

- **Skills (`source=None`, i.e. every existing call site — unchanged behaviour):** effects **stack** as
  before. Each application appends an independent record with its own duration and magnitude, and the
  records tick independently — a bleed for 2 turns at 5/turn and a bleed for 3 turns at 10/turn both run
  side by side.
- **Items (`source=("item", item_id)`):** re-using the **same item** refreshes **its own** record in place —
  `duration = max(old, new)`, `magnitude = new`. The merge key is
  `(source, effect name, normalized attribute, owner_id)`, so an identically named effect coming from
  another item or from a skill is never touched.
- `source` is normalized to the string `"item:42"` and stored on the effect record (`buffs.normalize_source`),
  because the state is JSON-serialized into Redis and a tuple would come back as a list. A tuple, a list, a
  ready string or None are all accepted. Records from before this change carry no `source` ⇒ they are never
  merged and never block a new application.

**Addendum 1 (Backend Dev, task #3):** on a **refresh** of an already active
effect, `fresh` is **not** set again — only `duration = max(old, new)` and `magnitude = new` are applied
(`owner_id` is re-stamped). `fresh` exists solely to skip the first tick on the turn an effect is cast;
re-setting it on a refresh would pause an already-running DoT for a turn (topping up a poison would cost
the player a tick of damage), which is an unintended balance side effect of the refresh rule. `fresh = True`
is therefore written only when the effect record is genuinely new.

`remove_effects` must tolerate legacy records without `owner_id` / `fresh` (`eff.get("owner_id", int(pid))`),
exactly like `decrement_durations` already does.

Coating helpers stay in `main.py` (they touch participant state, not the effect list) unless Backend Dev
prefers `buffs.py`; either is acceptable, but they must be unit-testable without Redis.

---

### 3.7 Item step in `_make_action_core` (battle-service `main.py:2581-2645`)

Rewritten as, in order:

1. Resolve the slot by `item_id` in `part.get("fast_slots", [])` — unchanged; miss ⇒ warn and skip.
2. `consumable_action = slot.get("consumable_action") or "instant"`.
3. If `weapon_coating` and a coating is already active ⇒ emit `item_rejected`, **return from the item step**
   (no consume, no quantity decrement).
4. Best-effort `consume_item` — unchanged semantics (a failure logs and does not block; keeps today's
   behaviour and `tests/test_item_usage.py:452`).
5. Apply the four recovery fields — unchanged.
6. `effects = slot.get("effects", [])`, filtered by `_filter_effects_by_chance` (`main.py:172`, the same
   luck/endurance proc roll skills use), then split:
   - `effect_name == "Cleanse"` ⇒ `remove_effects` on the resolved target (self / `ally_target_id`),
     emit `effects_removed` with the removed names; nothing is ever removed from a full-skip control.
   - `target_side == "self"` ⇒ `apply_new_effects(state, me, rows, owner_pid=me)`
   - `"ally"` ⇒ resolved `ally_target_id`, falling back to self
   - `"all_allies"` ⇒ every alive participant on the actor's team
   - `"enemy"` ⇒ resolved `target_id`, `is_enemy=True`, `owner_pid=me`
   Each application appends an `apply_effects` event with `"kind": "item"`.
7. `damage_entries = slot.get("damage_entries", [])` ⇒ for each row, `resolve_aoe_targets` + the **same**
   `compute_damage_with_rolls` call the attack step uses (dodge rolled once per target, crit, resists),
   `weapon=None` when `weapon_slot == "no_weapon"`. HP, `total_damage_dealt` / `total_damage_received` are
   updated like the attack step. Events: the existing `damage` event plus `"source_kind": "item"` and
   `"item_name"`.
8. `weapon_coating` ⇒ set `part["weapon_coating"]` from the slot (`coating_turns`, `coating_bonus_damage`,
   the item's `enemy` effect rows) and emit `weapon_coating_applied`.
9. Quantity/slot bookkeeping (§3.4) and the existing `item_use` event, now carrying `effects` /
   `damage` / `action` so the log can describe what happened, and including `stamina` in `recovery`
   (bug #6).

An item whose slot has none of the new keys reaches exactly steps 1, 4, 5, 9 ⇒ today's behaviour, bit for bit.

---

### 3.8 Autobattle item picker (`autobattle-service/app/strategy.py:157-174`)

`value(slot)` is extended so effect items stop scoring 0 (today they can never be chosen):

```
v  = need_hp * health_recovery + need_mana * mana_recovery + need_energy * energy_recovery      (as today)
v += 0.01 * quantity                                                                            (as today)
v += Σ over damage_entries:  amount * DMG_W                                    (DMG_W ≈ 0.6)
     (no `chance` factor — the engine never rolls chance on item damage rows, review #1 finding 9)
v += Σ over self/ally effects: |magnitude| * max(1, duration) * BUFF_W         (BUFF_W ≈ 0.15)
v += Σ over enemy effects:     |magnitude| * max(1, duration) * DEBUFF_W       (DEBUFF_W ≈ 0.12)
v += coating_bonus_damage * coating_turns * COAT_W  — only if the runtime participant has no
     active weapon_coating; otherwise this slot scores 0 (a refused application wastes the turn's item)
```

All weights are named module constants (no magic numbers, CLAUDE.md §6.3). A cleanse item scores
`CLEANSE_W` only when the runtime participant actually carries a removable debuff
(`ctx["runtime"]` already exposes `active_effects`, `main.py:232-238`).
`main.py:254-255` (`hp_pots_left` / `mana_pots_left`) stays as is — those features are about sustain only.
All slot reads use `.get(..., default)` so pre-deploy snapshots score exactly as today.

---

### 3.9 XP books

**Decision on `xp_bonus` semantics: keep it, do not migrate.** `xp_bonus` continues to mean **profession XP**
(its only current consumer is `award_profession_xp`, `crud.py:1435`). Renaming it would require a data
migration of live `active_buffs` rows and of existing item definitions for zero player-visible gain. Instead
two new sibling types are added:

| `buff_type` | Meaning | Consumer |
|---|---|---|
| `xp_bonus` | profession XP (**unchanged**, already shipped) | `crud.award_profession_xp` |
| `gathering_xp_bonus` | gathering-skill XP (**new**) | `crud.award_gathering` (same service, same session) |
| `character_xp_bonus` | character XP (**new**) | character-service `add_rewards_to_character` via §3.3.4 |

Work items:
- `crud.get_xp_multiplier(db, character_id, buff_type="xp_bonus")` — the parameter is added with the old
  value as default, so every existing call site keeps compiling and behaving identically.
- `crud.award_gathering` multiplies its `xp_award` by `get_xp_multiplier(db, cid, "gathering_xp_bonus")`,
  rounded the same way profession XP is.
- `ALLOWED_BUFF_TYPES = {"xp_bonus", "gathering_xp_bonus", "character_xp_bonus"}` validated in
  `ItemCreate` (a `root_validator`, Pydantic v1) — today `buff_type` is an unvalidated free string. All
  existing rows use `xp_bonus`, so nothing breaks.
- The admin UI exposes all three; labels are Russian («Опыт профессии», «Опыт сбора», «Опыт персонажа»).
- character-service calls the internal endpoint inside `add_rewards_to_character` (`crud.py:2136-2185`) —
  the single character-XP write point — and multiplies `xp` before the `UPDATE`. Fail-open on any error.
  **Scope note:** this covers every caller of `add_rewards_to_character` (battle rewards, mob rewards). RP-post
  XP, quest XP, title XP and battle-pass XP use other write paths and are **not** boosted in this feature —
  see the open question at the end of §3.12.

**Teleport scroll:** explicitly out of scope (separate future feature). **Identification scroll:** already
implemented, untouched.

---

### 3.9-bis XP books, flexible edition (Backend Dev addendum, task #6 — supersedes the narrow §3.9 book)

The user's decision (§1, «Книги/свитки опыта → гибкая настройка в админке») replaces the single
`character_xp_bonus` book of §3.9 with a per-item **list**: the admin picks *which* XP sources an item
accelerates and by how much, and may combine several in one item. §3.9 stays valid for everything it says
about `xp_bonus` and `gathering_xp_bonus`; only the character-XP part and the single-buff shape change.

#### A. Buff-type vocabulary (final, 8 values)

| `buff_type` | Meaning | Applied by | Russian label |
|---|---|---|---|
| `xp_bonus` | **profession XP — unchanged**, still the historic meaning | inventory `award_profession_xp` | «к опыту профессии» |
| `gathering_xp_bonus` | gathering-skill XP | inventory `award_gathering` | «к опыту сбора» |
| `character_xp_bonus` | **umbrella** — every character-XP source at once | see below | «ко всему опыту персонажа» |
| `character_xp_battle_bonus` | character XP from battles / PvE | character-service `add_rewards_to_character` | «к опыту персонажа за бои» |
| `character_xp_post_bonus` | character XP from roleplay posts | locations-service `award_post_xp_and_log` | «к опыту персонажа за отыгрыш» |
| `character_xp_quest_bonus` | character XP from quests | locations-service `add_experience` | «к опыту персонажа за задания» |
| `character_xp_title_bonus` | character XP from titles (passive XP only) | character-service `_grant_title_xp` | «к опыту персонажа за титулы» |
| `character_xp_pass_bonus` | character XP from the battle pass | battle-pass `_deliver_gold_xp` → `add_rewards_to_character` | «к опыту персонажа за боевой пропуск» |

`xp_bonus` is **not** renamed: live `active_buffs` rows and item definitions keep their meaning, so no data
migration and no behaviour change for the profession book that already shipped.

**Umbrella rule.** For a granular character source the values **add up**:
`multiplier = 1.0 + value(specific) + value(character_xp_bonus)`. A +25 % quest book worn together with a
+10 % all-character-XP book gives ×1.35. The folding happens **server-side in
`crud.get_xp_multiplier`** (`XP_BUFF_PARENTS`), so every caller asks for its own source only and can never
get the rule wrong. `xp_bonus` and `gathering_xp_bonus` have no parent — the umbrella is character XP only.

`active_experience` (skill points, incl. the active part of a title reward) is **not** accelerated by any
book; only `passive_experience` is.

#### B. Data model — one additive child table, migration `025_item_xp_buffs`

```sql
CREATE TABLE item_xp_buffs (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    item_id          INT         NOT NULL,     -- FK items(id) ON DELETE CASCADE
    buff_type        VARCHAR(50) NOT NULL,     -- one of the 8 above
    value            FLOAT       NOT NULL DEFAULT 0,   -- 0.25 = +25 %
    duration_minutes INT         NOT NULL DEFAULT 60,
    UNIQUE KEY uq_item_xp_buff_type (item_id, buff_type),
    INDEX ix_item_xp_buffs_item_id (item_id)
);
-- backfill: one row per item that already carried buff_type/buff_value/buff_duration_minutes
```

`items.buff_type / buff_value / buff_duration_minutes` are **kept and left filled** — no column is dropped
or rewritten, so a downgrade (`DROP TABLE item_xp_buffs`) is lossless for everything that existed before
this feature. **Precedence at runtime:** `item_xp_buffs` rows win; an item with no rows falls back to the
legacy triple (`crud.get_item_xp_buffs`). Saving a non-empty list through the admin clears the legacy
columns, so an item never has two sources of truth.

`active_buffs` is **unchanged** — the new types are plain strings in the existing table, one row per
`(character_id, buff_type)`, upsert-refresh as today. An item with three rows therefore produces three
independent `active_buffs` rows with independent expiry.

#### C. API contract

`ItemCreate` gains `xp_buffs: List[ItemXpBuffIn] = []` (replace-all on `PUT`, and only when the client
actually sends the key). `Item` / `ItemDetailResponse` gain `xp_buffs: List[ItemXpBuffOut] = []`.
No new endpoints for the admin, no new RBAC permissions — the rows ride inside the existing
`POST/PUT /inventory/items` under `items:create` / `items:update`, like `effects` and `damage_entries`.

Server-side validation (all messages Russian, 422 on failure):

| Rule | Message |
|---|---|
| `buff_type` ∈ the 8 values | «Недопустимый тип опыта» |
| `0 < value ≤ 10.0` | «Прибавка к опыту должна быть больше 0 и не больше 1000 %» |
| `1 ≤ duration_minutes ≤ 10080` (7 days) | «Длительность баффа опыта должна быть от 1 до 10080 минут» |
| no duplicate `buff_type` in one item | «Один тип опыта можно указать у предмета только один раз» |
| `item_type` ∈ {consumable, scroll} | «Ускорение опыта доступно только для расходников и свитков» |
| not `is_food` | «Еда не может ускорять опыт» |
| ≤ 8 rows | «Не больше 8 строк опыта у предмета» |

`POST /inventory/{cid}/use-buff-item` now applies **every** row (one `apply_buff` per type) in one
transaction. The response keeps its old single-buff fields (filled from the first row) for compatibility and
gains `buffs: [{buff_type, value, duration_minutes}]`; `message` lists every applied buff, e.g.
«Бафф активирован: +25% к опыту персонажа за задания на 60 мин, +10% к опыту профессии на 30 мин».

`GET /inventory/internal/characters/{cid}/xp-multiplier?buff_type=…` — **unchanged contract** (§3.3.4),
now accepting all 8 types and folding in the umbrella. Added sibling for callers that need several at once:

```
GET /inventory/internal/characters/{cid}/xp-multipliers?buff_types=a,b,c
Auth : Depends(verify_internal_token)
200  : {"character_id": 7, "multipliers": {"a": 1.25, "b": 1.1}}
400  : empty / unknown / too many types    404 : character not found
```

#### D. Award sites — where each multiplier is actually wired

The analyst's §2.6 note that «character XP is written in character-service» is only two-fifths true; the
write points are spread over three services:

| Source | Service · function | Multiplier call |
|---|---|---|
| battles / PvE | character-service `crud.add_rewards_to_character` (sync) | `apply_character_xp_buff(cid, xp, xp_source)`, default source = battle |
| battle pass | same helper, reached through `POST /characters/{cid}/add_rewards` | battle-pass-service now sends `xp_source: "character_xp_pass_bonus"` in the body |
| titles | character-service `crud._grant_title_xp` (sync) — passive part only | `apply_character_xp_buff(..., XP_SOURCE_TITLE)` |
| roleplay posts | locations-service `crud.award_post_xp_and_log` (async) | `await apply_character_xp_buff(..., XP_SOURCE_POST)`; the party +10 % bonus is still computed from the **base** XP so the book does not compound into it |
| quests | locations-service `crud.add_experience` (async), called from `POST /quests/{id}/complete` | `await apply_character_xp_buff(..., XP_SOURCE_QUEST)`; the endpoint now returns the **awarded** `reward_exp` |
| profession | inventory-service `award_profession_xp` | already shipped (task #2) |
| gathering | inventory-service `award_gathering` | already shipped (task #2) |

`AddRewardsRequest` gains `xp_source: str = "character_xp_battle_bonus"`, validated against the five
character sources («Недопустимый источник опыта»). battle-service and dungeon-service send nothing and keep
today's behaviour exactly — **battle-service is not touched by this task.**

**Fail-open, always.** Both helpers (`character-service/crud.get_character_xp_multiplier`,
`locations-service/crud.get_character_xp_multiplier`) return `1.0` and log a Russian warning on any error,
timeout (5 s) or unknown source, and clamp anything below 1.0 up to 1.0. XP is never lost because the buff
lookup failed. Rounding is `int(xp * multiplier)` — truncation, the same rule profession XP already uses.

#### E. What the admin form must offer (contract for the frontend)

Replace the single buff block (`ItemForm.tsx:577-608`, `BUFF_TYPE_OPTIONS` in `itemFormRules.ts`) with a
**repeatable list** «Ускорение опыта», shown for `item_type ∈ {consumable, scroll}` and `!is_food`:

- «Добавить строку» / «Удалить» per row; up to 8 rows; a type already used in another row is disabled in the
  select (the backend rejects duplicates).
- Per row: a `buff_type` select with the 8 Russian labels from table A (group the five character sources
  under a «Опыт персонажа» optgroup, with «ко всему опыту персонажа» as the umbrella); a percent input
  (UI shows 25, payload sends `value: 0.25`; > 0 and ≤ 1000 %); a duration input in minutes (1…10080).
- Client-side validation mirroring the table in §C, with those exact Russian messages; server errors are
  still displayed, never swallowed.
- On load: if `item.xp_buffs` is empty **and** the legacy `buff_type` is set, prefill one row from
  `buff_type` / `buff_value` / `buff_duration_minutes` (old items edited for the first time). On save, always
  send `xp_buffs` — the backend clears the legacy columns for you.
- `ActiveBuffIndicator` and the item tooltip must label all 8 types (labels in table A).

Tailwind only, no `React.FC`, responsive from 360 px, design-system classes — as everywhere else in §3.10.

---

### 3.10 Frontend

All new/changed files are `.tsx` / `.ts`, Tailwind only (no SCSS), no `React.FC`, responsive from 360 px,
every error surfaced to the player in Russian — CLAUDE.md §10.8/9/10/11/12 and `docs/DESIGN-SYSTEM.md`
(`gold-text`, `gray-bg`, `btn-blue`, `btn-line`, `modal-overlay`, `modal-content`, `input-underline`,
`text-site-blue`, `text-site-red`, `bg-site-bg`, `rounded-card`).

**A. Admin item effect editor** — new `components/ItemsAdminPage/ItemEffectSections.tsx`, modelled on
`AdminSkillsPage/SkillEffectSections.tsx` (906 lines, 5 sections) and reusing its vocabulary by importing
from `AdminSkillsPage/skillConstants.ts` (`DAMAGE_TYPES`, `WEAPON_SLOTS`, `STAT_MODIFIERS`,
`POISON_SUBTYPE_OPTIONS`, `COMPLEX_EFFECTS`) — **import, do not copy**, so the two editors can never drift.
Sections: (1) damage rows, (2) effect rows with the `TargetSideToggle`, (3) cleanse rows
(`effect_name='Cleanse'` + a selector dropdown + "сколько снимает", 0 = все), (4) coating block
(`consumable_action='weapon_coating'` + `coating_turns` + `coating_bonus_damage`). The whole editor is shown
only for `item_type ∈ {consumable, scroll}` and `!is_food`, next to the existing buff block
(`ItemForm.tsx:577-608`). `itemFormRules.ts`: `BUFF_TYPE_OPTIONS` grows from one entry to three; add the
effect-row defaults and client-side validation (chance 0..100, duration ≥ 0, coating turns ≥ 1).

**B. Battle log** — `BattlePageBar/BattlePageBar.tsx`, `formatBattleEvent` (`:462-656`). New/changed
branches, all Russian, no raw English may reach the player (the current fallback `:644-655` prints the event
name — that is the bug behind ISSUES #2):
`item_use` (now also mentions stamina — bug #6 — and what the item did), `item_rejected`
(«Нельзя применить „X": на оружии уже действует яд»), `weapon_coating_applied`
(«Наносит „Яд гадюки" на оружие (4 хода)»), `weapon_coating_expired`, `effects_removed`
(«Снимает эффекты: Кровотечение, Яд»), `item_broken` (**fixes ISSUES #2 in this PR**), and the `damage`
branch acknowledging `source_kind === "item"` («Свиток огня наносит 42 урона»). `apply_effects` with
`kind: "item"` reuses the existing branch.

**C. Item picker / tooltips in battle** — `SkillPicker/SkillPicker.tsx:142-231`: under each fast slot,
render a short Russian effect summary next to the existing recovery text (e.g. «+5 силы, 3 хода»,
«Урон: 40 (огонь)», «Яд на оружие, 4 хода»), show the remaining `quantity`, and disable a coating item
while `weapon_coating` is active with an explanatory tooltip. `battleEffects.ts` `describeEffect`
(`:81-165`) gets the new names (`Cleanse`, coating) so `CharacterSide`'s `EffectCircle` bubbles keep working.

**D. Inventory item tooltip** — `ProfilePage/InventoryTab/ItemDetailModal.tsx` (and `ItemCell`/
`ItemContextMenu` where the short description is built) render the item's `effects` / `damage_entries` /
coating in Russian, reusing the same describe helper so battle and inventory never disagree. Extract that
helper into a shared module rather than duplicating it.

**E. Buff labels** — `ProfilePage/CraftTab/ActiveBuffIndicator.tsx:14-16` gets labels for all three buff
types (today it labels only `xp_bonus`).

**TypeScript:** one shared interface set (`ItemEffect`, `ItemDamageEntry`, `FastSlot`, `WeaponCoating`) with
**every new field optional**, mirroring the `.get()` defaults on the backend, so a pre-deploy battle state
type-checks and renders.

---

### 3.11 Data flow

```
ADMIN
  Admin → ItemForm(+ItemEffectSections) → PUT /inventory/items/{id}  (items:update)
        → inventory-service → items + item_effects + item_damage_entries (replace-all in one tx)

BATTLE START
  battle-service → GET /inventory/characters/{cid}/fast_slots → slots + effects + damage + coating cfg
                 → snapshot into Redis  battle:{id}:state.participants[pid].fast_slots

TURN (one POST carries ≤1 item)
  Player/Autobattle → POST /battles/{id}/action {skills:{…, item_id}, target_id, ally_target_id}
    → _make_action_core step 8:
        control check → slot lookup → consume_item (best effort, inventory-service)
        → recovery → chance roll → Cleanse(remove_effects) / apply_new_effects (self|ally|team|enemy)
        → compute_damage_with_rolls for damage rows → set weapon_coating
        → quantity−1 (pop at 0) → events
    → step 9 attack: coating bonus_damage folded into weapon damage entries, coating effects onto hit targets
    → step 11 tick: tick_periodic_effects → decrement_durations → coating turns_left−1
    → Redis save (TTL 48h) → WS state_update → Celery save_log → MongoDB (display only)
  Frontend ← state_update → formatBattleEvent (Russian) + EffectCircle bubbles

XP BOOKS
  Player → POST /inventory/{cid}/use-buff-item → active_buffs upsert (refresh, never stack)
  Profession XP: inventory award_profession_xp × get_xp_multiplier(cid,"xp_bonus")              [existing]
  Gathering XP : inventory award_gathering    × get_xp_multiplier(cid,"gathering_xp_bonus")     [new, in-service]
  Character XP : character-service add_rewards_to_character
                   → GET /inventory/internal/characters/{cid}/xp-multiplier?buff_type=character_xp_bonus
                   → ×multiplier → UPDATE character_attributes.passive_experience   (fail-open = 1.0)
```

---

### 3.12 Security

| Surface | Decision |
|---|---|
| Admin item CRUD | Existing `require_permission("items:create"/"items:update")`. **No new permissions**, so no `permissions`/`role_permissions` migration and no RBAC-test additions. |
| Effect payload validation | Server-side, not just in the form: `chance` 0..100, `duration` 0..100, `magnitude`/`amount` −10000..10000, `aoe_falloff` 0..100, `aoe_max_targets` 1..10, `coating_turns` 1..50, `coating_bonus_damage` 0..10000, `target_side` ∈ {self,enemy,ally,all_allies}, `weapon_slot` ∈ {main_weapon,additional_weapons,no_weapon}, `damage_type` ∈ DAMAGE_TYPES, `effect_name`/`attribute_key` length-capped and character-restricted, **≤ 20 effect rows and ≤ 10 damage rows per item**. An admin must not be able to craft a one-shot or an infinite-duration item by accident, and no free-form string may reach the engine unchecked. |
| `buff_type` | Whitelisted (`ALLOWED_BUFF_TYPES`) — currently an unvalidated free string. |
| New internal endpoint | `Depends(verify_internal_token)`, like every other `/inventory/internal/*`. Never exposed through Nginx to the browser. |
| Player-facing endpoints | None added. `item_id` still comes from the server-side `fast_slots` snapshot, so a client cannot invent an item it does not own. |
| **ISSUES #3** | `POST /inventory/{cid}/use_item` gets the missing `check_not_in_battle` guard — with real combat power on items, out-of-band use during a fight becomes exploitable. Fixed in this feature and removed from `docs/ISSUES.md`. |
| Consume best-effort | Kept as today (a failed `consume_item` still applies the effect and is logged). Making consumption authoritative is a behaviour change outside this feature's brief; noted as a follow-up, not silently changed. |
| Rate limiting | No new limits — the item channel is inside the existing per-turn action, which is already deadline- and turn-order-bound. |
| Error messages | Russian, player-safe, no internals; nothing is swallowed silently (every refusal produces a log event the frontend renders). |

**Open question for PM/user (does not block the backend):** should the character-XP book also boost RP-post
XP, quest XP, title XP and battle-pass XP, or only the battle/mob rewards that go through
`add_rewards_to_character`? This design implements the latter.

---

## 4. Tasks (filled by Architect, updated by PM — in English)

Parallel groups: **A** = {#1, #2, #3} start together (different services/files); **B** = {#4} after #1+#3;
**C** = {#6, #7, #8} frontend, start immediately against the §3 contract; QA {#9…#12} after their backend task.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | inventory-service data layer: models `ItemEffect` / `ItemDamageEntry` + three `items` columns (§3.1); Alembic revision `024_item_battle_effects` with a working `downgrade()`; Pydantic v1 schemas §3.3.1 with all validation from §3.12; nested replace-all write in `create_item`/`update_item`; expose `effects`/`damage_entries`/coating on `GET /items/{id}`, `ItemDetailResponse` and `GET /characters/{cid}/fast_slots` (§3.3.3). `ItemBulkResponse` untouched. | Backend Developer | DONE | `inventory-service/app/models.py`, `schemas.py`, `crud.py`, `main.py`, `alembic/versions/024_item_battle_effects.py` | — | `alembic upgrade head` then `downgrade -1` both succeed on a live DB; creating an item with 2 effects + 1 damage row and re-reading it round-trips; an item with no rows returns `effects: []`; out-of-range chance/duration/magnitude → 422; `python -m py_compile` clean |
| 2 | XP books in inventory-service: `get_xp_multiplier(db, cid, buff_type="xp_bonus")`; `award_gathering` applies `gathering_xp_bonus`; `ALLOWED_BUFF_TYPES` whitelist; internal endpoint §3.3.4; type-aware `use-buff-item` message (ISSUES #5); add the missing `check_not_in_battle` to `POST /{cid}/use_item` (ISSUES #3) and drop both entries from `docs/ISSUES.md` | Backend Developer | DONE | `inventory-service/app/crud.py`, `main.py`, `schemas.py`, `docs/ISSUES.md` | — | profession XP unchanged with no buff and with `xp_bonus`; gathering XP scales with `gathering_xp_bonus`; internal endpoint 401 without the internal token; `use_item` in battle → 400 Russian message; `py_compile` clean |
| 3 | `buffs.py`: refresh-in-place instead of append in `apply_new_effects` (§3.4); `remove_effects(state, pid, selector, limit)` + `is_unremovable` (§3.6) with the hard rule that full-skip controls (Stun / Poison-paralysis) are never removed, including selector `all`; tolerate legacy records without `owner_id`/`fresh` | Backend Developer | DONE | `battle-service/app/buffs.py` | — | Pure-function module, no Redis/HTTP; same buff applied twice → one record with refreshed duration; `remove_effects(selector="all")` leaves a Stun in place; `py_compile` clean |
| 4 | battle-service item step rewrite (§3.7): action kinds, chance roll, cleanse, self/ally/team/enemy effects, damage rows through `compute_damage_with_rolls`, weapon coating apply/refuse/expire (§3.5), coating bonus damage + on-hit effects in the attack step, `quantity−1` stack fix (ISSUES #4, remove from `docs/ISSUES.md`), coating tick next to `decrement_durations`, `weapon_coating` in the participant state and in the state response, all new log events. Extend `inventory_client.get_fast_slots` to carry `effects`/`damage_entries`/`consumable_action`/coating fields. **Every new key read with `.get(..., default)`.** | Backend Developer | DONE (review #1 fixes applied) | `battle-service/app/main.py`, `inventory_client.py`, `schemas.py`, `tests/test_item_usage.py`, `docs/ISSUES.md` | #1, #3 | An item with no effect rows behaves exactly as before; a state dict snapshotted without the new keys survives a full turn; a stack of 5 gives 5 uses; a second coating is refused via `item_rejected` without failing the turn; `py_compile` clean |
| 5 | autobattle item picker (§3.8): named weight constants, values effect/damage/coating/cleanse items, skips a coating item while one is active, all reads defaulted | Backend Developer | DONE | `autobattle-service/app/strategy.py` | #1 | A buff potion / damage scroll / poison is now selectable; a recovery-only belt picks the same item as today; `py_compile` clean; review #1 follow-ups applied: item damage rows scored without the `chance` factor (the engine never rolls it) and `stat_down` mirrors `buffs._is_stat_down` |
| 5a | autobattle: fix the inverted resource need in `_pick_best` (`need = max(0, threshold - ratio)`) — the bot healed at full HP and never at 20 %; bug predates FEAT-168, approved by the user for this feature. Update the QA regression tests that pinned the old behaviour and drop the entry from `docs/ISSUES.md` | Backend Developer | DONE | `autobattle-service/app/strategy.py`, `app/tests/test_strategy_items.py`, `docs/ISSUES.md` | #5 | A heal wins over a buff at 20 % HP and loses at full HP; effect/coating/cleanse scoring unchanged; full autobattle pytest green |
| 6 | **Flexible XP books (§3.9-bis, replaces the narrow character-XP book).** inventory-service: `item_xp_buffs` child table + migration `025_item_xp_buffs` with backfill and a working `downgrade()`; 8 buff types with umbrella folding in `get_xp_multiplier`; `xp_buffs` on `ItemCreate`/`Item` with Russian validation; multi-buff `use-buff-item`; batch internal endpoint `/xp-multipliers`. Award sites: character-service `add_rewards_to_character` (battle, + `xp_source` from the battle pass) and `_grant_title_xp` (titles); locations-service `award_post_xp_and_log` (posts) and `add_experience` (quests); battle-pass-service sends its own `xp_source`. Fail-open to 1.0 everywhere. **battle-service untouched.** | Backend Developer | DONE | `inventory-service/app/{models,schemas,crud,main}.py`, `alembic/versions/025_item_xp_buffs.py`, `character-service/app/{crud,schemas,main}.py`, `locations-service/app/{crud,main}.py`, `battle-pass-service/app/crud.py` | #2 | migration up/down/up on a live DB incl. backfill; quest book 25 % + umbrella 10 % → ×1.35; profession XP untouched by character books; XP unchanged when inventory-service is down; legacy single-buff items still usable; `py_compile` + full pytest clean in all four services. **Review #2 fix (supersedes the review #1 attempt):** the multiplier is resolved at the *entry point* of each request — before any ORM object is loaded and before the transaction opens — and passed down as `xp_multiplier`. Nothing rolls back a session it does not own; `_release_db_connection` is deleted everywhere; `grant_title` is atomic again **and answers a lost duplicate race with `already_has` instead of a 500** (`IntegrityError` handled, no XP awarded); battle-pass reverted to the `xp_source` field only. **Review #3 fix:** an async helper for `async def` handlers (the blocking one is threadpool-only), the equip-triggered `evaluate-titles` and `GET /{id}/titles` look the book up **only when a title actually unlocks** (review #4) — zero callbacks on an equip that grants nothing, one lookup when it grants, and a lazy lookup on `full_profile` (only on a real level-up) and on quest completion (only when `reward_exp > 0`); crud award functions never look anything up |
| 7 | Admin item effect editor (§3.10 A): `ItemEffectSections.tsx` importing the vocabulary from `AdminSkillsPage/skillConstants.ts`, wired into `ItemForm`, `BUFF_TYPE_OPTIONS` → three types, client-side validation, Russian labels, responsive from 360 px, Tailwind + design-system classes, no `React.FC` | Frontend Developer | DONE | `components/ItemsAdminPage/ItemEffectSections.tsx` (new), `ItemForm.tsx`, `itemFormRules.ts` | — (contract §3.3) | An admin can create a buff potion, a damage scroll, a poison and an antidote without touching the DB; save → reload shows the same rows; `npx tsc --noEmit` and `npm run build` pass |
| 8 | Battle frontend (§3.10 B/C): all new events in `formatBattleEvent` in Russian incl. `item_broken` (ISSUES #2) and stamina in `item_use` (ISSUES #6); fast-slot effect summaries + quantity + coating-disabled state in `SkillPicker`; `describeEffect` knows the new names; shared optional-field TS interfaces | Frontend Developer | DONE | `components/pages/BattlePage/BattlePageBar/BattlePageBar.tsx`, `SkillPicker/SkillPicker.tsx`, `battleEffects.ts`, `CharacterSide/CharacterSide.tsx` | — (contract §3.7) | No raw English event name can reach the log; a pre-deploy state without the new keys still renders; `tsc --noEmit` + `npm run build` pass |
| 9 | Inventory item tooltip + buff labels (§3.10 D/E): item effects/damage/coating shown in Russian in `ItemDetailModal` (+ the short description surfaces) via one shared describe helper; `ActiveBuffIndicator` labels all three buff types | Frontend Developer | DONE | `components/ProfilePage/InventoryTab/ItemDetailModal.tsx`, `ItemCell.tsx`, `ItemContextMenu.tsx`, `components/ProfilePage/CraftTab/ActiveBuffIndicator.tsx` | — (contract §3.3) | A potion's tooltip shows its buff; an effect-less item's tooltip is unchanged; `tsc --noEmit` + `npm run build` pass |
| 10 | **New** unit tests for `buffs.py` — the module has none today: `_normalize_effect`, refresh-not-stack, `apply_new_effects` instant clamping and enemy inversion, ownership ticking, `tick_periodic_effects`, `evaluate_control`, `remove_effects` selectors, and the hard rule that Stun / Poison-paralysis survive `selector="all"`; legacy records without `owner_id`/`fresh` | QA Test | DONE | `battle-service/app/tests/test_buffs.py` (new) | #3 | ≥ 20 assertions covering every public function; pytest green |
| 11 | Battle item-usage tests **without mocking the effect engine** — today `test_item_usage.py:34-45` mocks `buffs` away. Add a suite that uses the real module: buff potion → effect in state and in the attack, damage scroll through the damage formula, cleanse (incl. an unremovable Stun), coating apply → bonus damage → refuse second → expire, stack of 5 → 5 uses, one item per turn, item nullified by a full-skip control, and **a battle state dict built without any of the new keys completing a turn** | QA Test | DONE | `battle-service/app/tests/test_item_effects.py` (new), `test_item_usage.py` | #4 | All scenarios asserted against real `buffs`; the legacy-state test fails if any new key is read without a default; pytest green |
| 12 | inventory + character + autobattle tests: nested effect CRUD round-trip and validation rejections, fast-slot payload shape, `get_xp_multiplier` per buff type, gathering XP with/without buff, internal xp-multiplier endpoint auth, `use_item` in-battle guard, type-aware buff message, character-service multiplier incl. fail-open, and the autobattle picker scoring. **Plus §3.9-bis (task #6):** `item_xp_buffs` round-trip and every validation message, the legacy single-buff fallback, multi-buff `use-buff-item`, umbrella folding (quest 25 % + umbrella 10 % = ×1.35) and the `/xp-multipliers` batch endpoint incl. auth; the five award sites in character-service (battle, title, `xp_source` from the battle pass) and locations-service (post, quest), each with the fail-open case | QA Test | DONE (+ ревью #2: закрыты две дыры — схемы чтения и опыт на настоящей сессии) | `inventory-service/app/tests/…`, `character-service/app/tests/…`, `locations-service/app/tests/…`, `battle-pass-service/app/tests/…`, `autobattle-service/app/tests/…` | #1, #2, #5, #6 | Each new/changed endpoint and CRUD path covered incl. one security case per surface; pytest green in all five services |
| 13 | Final review: contracts backend ↔ frontend ↔ tests, the §3.0 compatibility contract (grep every new key for a default), migration up **and** down on a live DB, Russian-only player strings, security checklist, `py_compile` / `tsc --noEmit` / `npm run build` / `pytest`, plus **live verification** — create an effect item in the admin UI, run a real battle using a buff potion, a damage scroll, a poison and an antidote, and confirm zero console/5xx errors | Reviewer | DONE | all | #1–#12 | Every checklist item evidenced with command output; live battle verified; `docs/ISSUES.md` no longer lists #2, #3, #4, #5, #6 |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

**No DevSecOps task:** no Docker, Nginx, env-var or new-dependency changes. The Alembic revisions run through
the existing auto-migration in the inventory-service Dockerfile.

**Frontend follow-up opened by task #6 (§3.9-bis E):** tasks #7 and #9 shipped the *single* buff select
(`BUFF_TYPE_OPTIONS`, three types). The admin form must now become a repeatable «Ускорение опыта» list over
the 8 types (contract in §3.9-bis E), and `ActiveBuffIndicator` / the item tooltip must label all 8. The
backend accepts both shapes meanwhile: a payload without `xp_buffs` leaves the rows untouched, and an item
with no rows still works off its legacy columns — so nothing is broken while the form catches up.

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-18
**Result:** FAIL

The feature is substantially well built: the compatibility contract, the cleanse hard rule, the
item-vs-skill stacking split, the coating lifecycle and the fail-open XP wiring all hold up under
inspection and in a live battle. Four defects block completion — one of them (#1) makes three of the
five buttons in the new admin editor unsaveable, and two (#2, #3) are silent failures of the exact
kind `docs/ISSUES.md` tracks as a recurring pattern.

#### Automated Check Results
- `npx tsc --noEmit` (in the `frontend` container) — **PASS** (zero output, no errors at all)
- `npm run build` — **PASS** (`built in 49.25s`)
- `py_compile` on all 25 modified/new Python files — **PASS**
- `pytest` in throwaway `python:3.10-slim` containers, whole repo mounted, CI args from `ci.yml`, `CI=true`:
  - battle-service — **707 passed**
  - inventory-service — **1226 passed, 1 xfailed** (the xfail is the known fast_slots auth gap)
  - character-service — **1003 passed, 1 skipped**
  - locations-service — **1232 passed**
  - battle-pass-service — **119 passed**
  - autobattle-service — **124 passed** (after the #5a need-formula fix; 122 before)
- `docker compose config` — **PASS**
- Migrations 024/025 up -> down -> up on the live dev MySQL — **PASS** (details below)
- Live verification (real battle + browser at 1440 px and 360 px) — **PASS for the flows that work**, see below

#### Migration verification (live dev DB, prod dump)
`alembic downgrade 024` -> `downgrade 023_weapon_damage_backfill` -> `upgrade head`, all clean.
After the 024 downgrade `item_effects`, `item_damage_entries` and the three `items` columns were
verifiably gone; after the re-upgrade they were back and the DB was left at `025_item_xp_buffs`.
The 025 backfill was exercised on purpose-built prod-like rows: an item with
`('xp_bonus', 0.25, 60)` backfilled correctly; one with `buff_duration_minutes = NULL` was correctly
skipped (it falls back to the legacy columns); but one with `buff_type = ''` and one with
`buff_value = 0` were backfilled verbatim — see issue #2. The local DB carries **zero** items with a
legacy `buff_type`, so the backfill is a no-op here; the risk is on prod.

#### Live Verification Results
Battles 210–215 (chars 761 vs 762), all driven through the real endpoints, state read from Redis:
- **Buff potion** — `apply_effects` + `item_use` (`quantity_left: 3`), effect stored with
  `source: "item:80"`; the +8 strength reached the **same turn's** item damage (`base: 18` = 10 + 8).
- **Refresh, not stack** — re-using the same potion left **one** record with a refreshed duration,
  never two.
- **Damage scroll** — `base 18 + entry 40 = final 58` through `compute_damage_with_rolls` with the
  crit/resist/dodge channels present, `source_kind: "item"`.
- **Poison coating** — applied (`weapon_coating_applied`, 4 turns -> `turns_left: 3` counting the
  current one), bonus folded into the weapon entry (`entry: 12`, 10 -> 22 final), the `Poison` row
  landed on the target that took damage, ticked 6 HP/turn (78 -> 72 -> 66) and expired with
  `weapon_coating_expired`.
- **Second coating refused** — `item_rejected` with `active_coating` and `turns_left`, the item was
  **not** consumed (quantity unchanged) and the rest of the turn still resolved.
- **Antidote** — removed both enemy-owned debuffs, left the character's own buff in place.
- **Stun is never removable** — with a Stun active the whole action including the item was nullified
  (`control_skip`), so no item can ever clear a full-skip control.
- **XP books** — `use-buff-item` applied all three rows in one call with the correct Russian summary;
  the internal multiplier endpoint returned **1.35** for `character_xp_quest_bonus` (0.25 + 0.10
  umbrella), 1.5 for gathering, **1.0** for `xp_bonus` (profession untouched by character books), and
  401 without the internal token. A real gathering award of `xp_to_add: 100` returned
  `xp_awarded: 150` — the book demonstrably multiplies the right source.
- **Autobattle** — with the new items in the belt the bot chose `item=82` (the poison coating), which
  scored 0 and was unreachable before this feature. After the #5a fix: at 20 % HP it chose the
  healing potion (`item=90`), at full HP it chose the coating instead — both directions correct.
- **Browser, 1440 px and 360 px** — battle page and admin item page render at both widths with **zero
  console errors and zero 4xx/5xx** attributable to this feature. The item picker shows Russian
  summaries and quantities: «ZZR-Зелье силы ×3 — Сила (3 хода, +8)», «ZZR-Свиток огня ×3 — Урон: 40
  (Огонь)», «ZZR-Яд гадюки ×3 — Яд на оружие, +12 к урону, 4 хода, считая текущий / Отравление
  (3 хода, −6 HP/ход), по врагу», «ZZR-Противоядие ×3 — Очищение: чужие эффекты». With a coating
  active the picker shows the banner «ZZR-Яд гадюки на оружии — осталось 3 хода» and disables the
  poison with «На оружии уже действует яд — новый нельзя нанести, пока прежний не выдохнется.»
  The admin item form renders the damage / effect / cleanse / coating sections and the
  «УСКОРЕНИЕ ОПЫТА» repeatable list, all in Russian, and round-trips every field.
  The only console error seen is a pre-existing 401 on `/notifications/messenger/unread-count`,
  unrelated to this feature (plus Vite HMR websocket noise from the headless container).

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 1 | `services/inventory-service/app/schemas.py:235` | **BLOCKER.** `AOE_SHAPES = {"single","line","cone","circle","all"}` matches neither the engine nor the admin UI. The engine's `resolve_aoe_targets` (`battle-service/app/main.py:102-132`) knows `single / splash / cleave / all / random_n`, and `ItemEffectSections.tsx:324-330` offers exactly those five. Verified live against the running service: `splash`, `cleave` and `random_n` -> **422 «Недопустимая форма области урона»**, so 3 of the 5 buttons in the new editor cannot be saved at all; `line`, `cone` and `circle` are accepted but unknown to the engine and silently degrade to single-target. Fix the backend set to `{"single","splash","cleave","all","random_n"}`. | Backend Developer | FIXED |
| 2 | `services/inventory-service/app/schemas.py:343` + `alembic/versions/025_item_xp_buffs.py:53-62` | **MAJOR.** `ItemXpBuffOut(ItemXpBuffIn)` inherits the request validators, so a stored row that fails them breaks the **response**. Migration 025 backfills any item whose three legacy columns are non-NULL, with no `buff_value > 0` filter and no buff-type whitelist — and `items.buff_type` was an unvalidated free string before this feature. Verified live: a row with `buff_type` outside the whitelist -> `GET /inventory/items/{id}` **500**; a row with a valid type and `value = 0` -> **500** as well. Invisible locally (dev DB has no legacy books) but reachable on prod the moment the migration runs. Needs both a non-validating output shape and a tightened backfill. | Backend Developer | FIXED |
| 3 | `services/battle-service/app/main.py:3168` | **MAJOR, silent failure.** `_coated_entry = bool(_coating_bonus) and _weapon_slot != "no_weapon"` gates the coating's on-hit effect rows on the *bonus damage* being non-zero. A DoT-only poison (`coating_bonus_damage = 0`, one `Poison`/`periodic_damage` row) is an explicitly valid admin config (`schemas.py:653` accepts 0). Verified live: such a coating applies, logs «наносит яд», ticks down, expires — and lands **no effect at all** on a target it hits. §3.5 conditions the application on targets that took damage, not on the bonus. Gate on `bool(_coating)` and keep only the `amount` top-up guarded by `_coating_bonus`. | Backend Developer | FIXED (review #1) — gate is now `_coating is not None and _weapon_slot != "no_weapon"`; the `amount` top-up alone stays behind `_coating_bonus`. Regression test `TestWeaponCoatingOnHit::test_zero_bonus_coating_still_applies_its_effects` verified to fail against the old gate. |
| 4 | `.../ItemsAdminPage/ItemEffectSections.tsx:622,634-640` + `itemFormRules.ts:277` | **MAJOR.** Switching «Как применяется» to «Нанесение на оружие (яд)» writes only `consumable_action`; `coating_turns` stays `null` while the input *displays* `1` (`value={coatingTurns ?? 1}`). `validateBattleConfig` then blocks the save with «Длительность яда на оружии — от 1 до 50 ходов» for a field the admin can see reading "1". Seed `coating_turns: 1` / `coating_bonus_damage: 0` when the action switches. | Frontend Developer | FIXED (Frontend Dev) |
| 5 | `services/inventory-service/app/crud.py:2420-2436` | MINOR. `replace_item_xp_buffs` clears the legacy `buff_type/buff_value/buff_duration_minutes` only when `rows` is non-empty, so an admin who deletes the prefilled row and saves gets the rows dropped but the legacy triple intact — `get_item_xp_buffs` then resurrects the old buff. Masked today only because the form also posts `buff_type: null`. | Backend Developer | FIXED |
| 6 | `services/inventory-service/app/main.py:147-151` | MINOR. `GET /inventory/items` eager-loads `effects` and `damage_entries` but not `xp_buffs`, which the response model now serialises — up to 500 extra queries per page, the exact N+1 the comment above it says it is avoiding. | Backend Developer | FIXED |
| 7 | `services/character-service/app/crud.py:2226` | MINOR. `apply_character_xp_buff` makes a blocking 5 s `httpx.get` after the transaction is open and before the gold/XP writes, so a slow inventory-service holds a MySQL transaction open per reward. Fail-open and correct style, but the lookup belongs before the transaction or on a shorter timeout. | Backend Developer | FIXED (review #1): every XP-book lookup now happens with the DB connection returned to the pool. New guarded helper `crud._release_db_connection(db)` — rolls back **only** when the session has no pending changes (`db.new/dirty/deleted`), so a caller's uncommitted work is never discarded — plus `crud.fetch_character_xp_multiplier(db, cid, source)` which releases and then calls. Wired at all four sites: `add_rewards_to_character` fetches as its **first** statement, before any query; `grant_title` fetches after its read checks and before the first write; `evaluate_titles` was split into a read/decide phase (collects `to_grant` with materialised reward fields) → one release + **one** multiplier fetch per call → a write phase, so a loop over N titles no longer makes N in-transaction HTTP calls; `_grant_title_xp` takes the resolved `xp_multiplier` as a parameter and only fetches itself when called directly. Same treatment in locations-service (`add_experience` releases before the lookup; the post path never had a session) and in battle-pass-service, where the **pre-existing** `deliver_reward` HTTP burst inside `claim_reward` now also releases first (`reward` is expunged beforehand — an expired ORM attribute would raise `MissingGreenlet` on an async session). Verified live: `db.in_transaction()` goes True → False around the lookup, and 100 XP with a 25 % book still lands as 125. |
| 8 | `services/autobattle-service/app/strategy.py` (`_matches_cleanse_selector`, `SELECTOR_STAT_DOWN`) | MINOR. Uses a raw `magnitude < 0` where `buffs._is_stat_down` (`buffs.py:419-429`) runs the value through `aggregate_modifiers`. Complex effects (`Curse`, `ArmorBreak`, ...) carry a positive magnitude that expands to negative channels, so the bot judges a `stat_down` antidote worthless against exactly those. | Backend Developer | FIXED (review #1): `_is_stat_down` added to `strategy.py` as an explicit, documented mirror of `buffs._is_stat_down` — complex effects expanded by `abs(magnitude)` (ArmorBreak, Freeze, Electrify, Daze, Wet, Curse) always count as a stat-down, Holy never does, everything else keeps the magnitude-sign rule. Source of truth named in the docstring and in `docs/services/autobattle-service.md`. |
| 9 | `services/inventory-service/app/schemas.py` (`ItemDamageIn.chance`) + `strategy.py` damage scoring | MINOR. Damage-row `chance` is validated, stored and used to weight the autobattle score, but the engine never rolls it (`main.py:2865-2963` has no `_filter_effects_by_chance` on `damage_entries`) — consistent with the skill attack step, and the admin form deliberately hides the field. Either drop it from the scoring or document it as dead. | Backend Developer | DECIDED (review #1): `chance` is **ignored for item damage rows**, deliberately and identically to the skill attack step — documented in `docs/services/battle-service.md` and in a comment at the item damage loop; the admin form already hides the field. The remaining touch-ups (a note in `ItemDamageIn.chance` and the autobattle scoring weight) belong to tasks #1/#5. **#5 done:** the `chance/100` factor was dropped from the autobattle damage term, so the picker's score matches what the engine actually does. |
| 10 | `.../ProfilePage/CraftTab/ActiveBuffIndicator.tsx:61` | MINOR. The badge keeps `whitespace-nowrap` while the label grew from `"XP"` to up to 30 characters («к опыту персонажа за боевой пропуск»); at 360 px it cannot wrap and overflows. CLAUDE.md §10.12. | Frontend Developer | FIX_REQUIRED |
| 11 | `.../ItemsAdminPage/itemFormRules.ts:389-391` | MINOR. `buildItemPayload` nulls the legacy buff triple unconditionally, including when `rules.buff` is false (e.g. an item flagged `is_food`, or a type switch), silently dropping a legacy buff on any save. | Frontend Developer | FIX_REQUIRED |
| 12 | `.../ItemsAdminPage/itemFormRules.ts:249-281` | MINOR. The battle-config client messages do not match the server wording («Слишком много эффектов: максимум 20» vs «Не больше 20 эффектов у предмета»). The XP-row messages *are* byte-exact — the same rule should hold here. | Frontend Developer | FIX_REQUIRED |
| 13 | `docs/services/frontend.md` | MINOR. Not updated for `ItemEffectSections.tsx`, `ItemXpBuffsEditor.tsx` and `utils/itemEffects.ts`. Every backend service doc was updated correctly. | Frontend Developer | FIX_REQUIRED |
| 14 | `services/battle-service/app/main.py:2985-2987` (comment) + `tests/test_item_usage.py::test_legacy_slot_without_quantity_is_removed` | NIT. The premise is false: the *old* `get_fast_slots` already wrote `"quantity": slot.get("quantity", 0)` unconditionally, so a pre-deploy snapshot always carries `quantity` (the inventory-wide total). The `int(slot.get("quantity", 1) or 1)` default is correct; the comment, §3.4's compatibility claim and that one test guard a shape that cannot occur. | Backend Developer | FIXED (review #1) — comment, §3.4 and `docs/services/battle-service.md` now state that pre-deploy slots do carry `quantity`; the test is renamed `test_slot_with_unusable_quantity_is_removed` and uses `quantity: 0`. |

#### Verified clean (no action needed)
- **§3.0 compatibility contract** — every new key on the Redis state, the fast-slot dicts and the effect
  records is read with `.get(..., default)`; the only bracket subscripts on new keys are writes. A
  battle state built without any new key completes a turn unchanged, and an item with zero effect rows
  takes exactly the old path (the only deliberate difference being the stack fix).
- **Item-vs-skill stacking** — `source=` is passed at exactly two call sites, both item-side; no skill
  call site gained one, so skill effects still stack independently (2-turn/5 and 3-turn/10 bleeds tick
  separately) while items refresh by item. `fresh` is correctly not re-set on a refresh.
- **Cleanse hard rule** — `remove_effects` filters `is_unremovable` first and unconditionally, ahead of
  the selector including `"all"`, and derives the full-skip set from `evaluate_control` itself.
- **Security** — new internal routes behind `verify_internal_token` (401 without it, and 403 from the
  browser through Nginx, both verified live); admin CRUD unchanged under `items:create` / `items:update`
  with no new RBAC rows; the only raw SQL is parameterised; `check_not_in_battle` added to
  `POST /{cid}/use_item`; all error messages Russian and internals-free.
- **XP award wiring** — fail-open to 1.0 with a Russian warning on any error/timeout, clamped to >= 1.0,
  truncated with `int()`; the locations-service party bonus is computed from the base XP; battle-service
  is untouched by the XP work.
- **CLAUDE.md frontend rules** — no `React.FC` anywhere, no new `.jsx`, no new SCSS/CSS, design-system
  classes and Tailwind tokens throughout, responsive from 360 px (one exception, issue #10), every API
  call surfaces a Russian error, no silently swallowed failures.
- **Battle log coverage** — all 17 backend event strings are handled; the fallback can no longer print a
  raw English event name (closes the `item_broken` entry).
- **`docs/ISSUES.md`** — all five entries this feature fixed are gone or struck through as DONE, each
  with a real fix in the code; both new QA findings are present and both claims verified true. (The LOW
  autobattle "need" entry was correctly removed once #5a fixed it.)
- **Task #5a (autobattle need formula)** — `need = max(0, threshold - ratio)` is the correct direction,
  applied consistently to hp/mana/energy with thresholds and FEAT-168 weights unchanged. The test edits
  are legitimate re-baselining, not cover: `TestWeightConstants` now pins **both** directions
  (`test_healing_in_a_crisis_outranks_a_stockpiled_buff` and `test_a_heal_at_full_hp_loses_to_a_buff`),
  `TestLegacyRecoveryRegression` pins the thresholds and an exact score with a sandwich, and the
  pre-deploy compatibility cases are retained. Confirmed live in both directions (see above).

#### Test data
All test items, inventory rows, belt entries, `active_buffs` and the gathering-skill row created during
verification were removed; battles 210–215 were force-finished; the admin's active character was
switched to 761 for the browser run and switched **back to 706**; character 706's belt was never
touched. No service was stopped or started; every throwaway container was removed. No commits.

---

### Review #2 — 2026-09-18
**Result:** FAIL

Every round-1 finding is genuinely fixed, and I re-verified the four blocking/major ones live rather
than on the diff. But the round-2 refactor that moved the XP-multiplier lookup out of the reward
transaction introduced a **new blocker** in locations-service that is worse than anything round 1
found: it 500s the quest-completion endpoint and leaves the quest replayable.

#### Automated Check Results
- `npx tsc --noEmit` — **PASS** (zero output)
- `npm run build` — **PASS** (`built in 33.52s`)
- `py_compile` on every modified/new Python file — **PASS**
- `pytest` in throwaway `python:3.10-slim` containers, repo mounted, CI args from `ci.yml`, `CI=true`:
  battle **710**, inventory **1238 + 1 xfail**, character **1003 + 1 skip**, locations **1232**,
  battle-pass **119**, autobattle **126** — all green, all up from round 1.
- Migration 024/025 down -> up re-run on the live dev DB — **PASS**

#### Round-1 findings — all verified fixed
| R1 # | Verification |
|---|---|
| 1 (BLOCKER, AoE) | Live against the running service: `single`/`splash`/`cleave`/`all`/`random_n` -> **201**, `line`/`cone`/`circle` -> **422**. Now matches `resolve_aoe_targets` exactly and the editor's five options are all saveable. |
| 2 (MAJOR, Out schemas + backfill) | Inserted deliberately corrupt rows into **all three** child tables (`buff_type='legacy_free_string'`, `value=-5`, `duration=99999`, `chance=999`, `duration=-7`, `damage_type='not_a_type'`, `weapon_slot='bogus_slot'`). `GET /inventory/items/{id}` -> **200** with every row echoed verbatim, list endpoint **200**. Previously 500. Backfill re-run on five prod-like legacy books: 3 migrated, **2 skipped** (unknown type, zero value) with the legacy columns left intact, **2 clamped** (999999 -> 10080, 0 -> 1), every decision logged in Russian. |
| 3 (MAJOR, coating gate) | Gate is now `_coating is not None and _weapon_slot != "no_weapon"` (`battle-service/app/main.py:3181`) with the bonus applied separately at `:3182`. Live: a coating with `coating_bonus_damage = 0` produced `damage … entry: 0.0` **and** `apply_effects … Poison` on the target, with the effect present in the Redis state. Previously nothing was applied. |
| 4 (MAJOR, coating turns) | `handleActionChange` (`ItemEffectSections.tsx:255-264`) now writes `coating_turns` / `coating_bonus_damage` into state on switch and clears them on switch-away. Admin form opened in the browser: the coating inputs read `4` / `0` from real state. |
| 5–13 | `replace_item_xp_buffs` clears legacy columns on an empty list (create path gated on the key); `xp_buffs` eager-loaded on the list endpoint; `stat_down` mirror aligned with `buffs._is_stat_down`; damage `chance` decided as never-rolled; `ActiveBuffIndicator` now `break-words` + `flex-wrap`; legacy columns only cleared when XP rows were edited; client validation strings verbatim-identical to the server's; `docs/services/frontend.md` updated. |
| 14 (NIT, quantity premise) | Corrected in the comment (`main.py:2989-2995`), in §3.4 and in the test (renamed to `test_slot_with_unusable_quantity_is_removed`, now using `quantity: 0`). |

#### Test re-baselining — legitimate, with one gap
Audited every changed/renamed test against its implementation. Nothing was weakened or deleted
without a meaningful replacement, and nothing asserts the old behaviour:
- The `stat_down` complex-effect test (`test_strategy_items.py:239-246`) uses `Curse` with a
  **positive** magnitude and fails under the old `magnitude < 0` rule.
- The `chance` tests were **inverted, not removed** (`test_damage_row_chance_is_ignored`), and the
  replacement discriminates: a 40-damage/25 %-chance row must now beat a 20-damage/100 % row.
- The coating regression test (`test_item_usage.py:737-752`) uses a **zero-bonus** coating and asserts
  the effect **is** applied — it genuinely fails against the old gate.
- The AoE tests assert both directions and round-trip the stored shape.
- The migration tests drive the real revision modules through a real `alembic.operations.Operations`
  and assert the skip/clamp/legacy-intact behaviour directly.

The gap: **no test anywhere asserts that a stored row with an invalid `buff_type` or `value = 0` can
be read without a 500** (issue #17 below). That was the round-1 fix with the widest blast radius and
it is currently guarded by nothing.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 15 | `services/locations-service/app/crud.py:5162` + `main.py:3050` | **BLOCKER, reproduced live.** `add_experience` starts with `await _release_db_connection(session)` -> `session.rollback()`, which **expires every loaded ORM object**. `complete_quest` loaded a `Quest` at `main.py:3031` and reads `quest.reward_items` at `:3050`, `quest.reward_currency` at `:3080` and both again in the response — on an expired instance bound to an `AsyncSession`, i.e. a lazy refresh outside greenlet context. Reproduced with the real session inside the container: `RAISED MissingGreenlet — greenlet_spawn has not been called`. Trigger: `reward_exp > 0` **and** `reward_currency == 0`; with gold the earlier `add_currency` commits, so the rollback is a no-op and nothing expires — which is exactly why a manual test on a gold-bearing quest passes. **Damage: the XP is already written and committed, then the request 500s before `complete_quest_record`, so the quest stays `active` and can be completed again for XP indefinitely.** Fix: materialise `reward_items`/`reward_currency` before calling `add_experience` (as battle-pass already does with `db.expunge(reward)`), or hoist the lookup into the endpoint before the quest is loaded. | Backend Developer | FIXED (review #2): the whole release-the-connection approach is gone — `_release_db_connection` is deleted from all three services and no code rolls back a session it does not own. `POST /quests/{id}/complete` now resolves the quest multiplier as its **first statement**, before `verify_character_ownership` and before the quest is loaded, and passes it to `add_experience(..., xp_multiplier=…)`, which no longer makes any network call. Regression test `TestAddExperienceKeepsCallerObjectsUsable` runs the exact trigger (`reward_exp > 0`, `reward_currency == 0`) against a **real in-memory aiosqlite AsyncSession with `expire_on_commit=False` (mirroring `database.async_session`) and reads `quest.reward_items` / `reward_currency` / `title` after the award; re-inserting the rollback makes it fail again with `MissingGreenlet`, which was verified. |
| 16 | `character-service/app/crud.py:103-113`, `locations-service/app/crud.py:211-221`, `battle-pass-service/app/crud.py:536-546` | **MAJOR.** `_release_db_connection` checks only `db.new / db.dirty / db.deleted`. It cannot see (a) an open transaction holding locks — no `in_transaction()` check, so a future caller after a `SELECT … FOR UPDATE` silently loses the lock; (b) **raw-SQL writes**, which is how this codebase writes almost everything (`session.execute(text("UPDATE …"))` never appears in `new/dirty/deleted`) — an uncommitted raw write would be rolled back while the helper returns `True`; (c) flushed-but-uncommitted ORM inserts (`grant_title` flushes at `crud.py:2783`, and `_grant_title_xp`'s `xp_multiplier=None` default invites exactly that call shape). Add `or db.in_transaction()` and document the raw-SQL limitation. | Backend Developer | FIXED (review #2) by removal, not by patching the guard: the helper is deleted from character-service, locations-service and battle-pass-service. The multiplier is resolved at the entry point of each request — before any ORM object is loaded and before the transaction is opened — and travels down as the `xp_multiplier` parameter, so no award function ever has to decide whether it is safe to end someone else's transaction. `TestMultiplyXp.test_no_in_transaction_lookup_helper_survives` fails if either helper comes back. |
| 17 | `services/inventory-service/app/tests/` | **MAJOR (QA).** The Out-schema decoupling (round-1 issue #2, the fix with the widest blast radius) has **no test**. All `models.ItemXpBuff(...)` inserts in the suite write valid rows; nothing inserts an invalid stored row and asserts `GET` still returns 200. Re-adding `class ItemXpBuffOut(ItemXpBuffIn)` would leave the whole suite green while every read of legacy data 500s. Add a raw-SQL insert of `buff_type="legacy_nonsense"` / `value=0` plus a `GET` assertion. | QA Test | FIX_REQUIRED |
| 18 | `services/character-service/app/crud.py:2777` (`grant_title`) | MAJOR. The duplicate check (`existing`, `:2760`) and the character check (`:2755`) now run in a **different transaction** from the INSERT (`:2783`), separated by an HTTP call of up to 5 s. `CharacterTitle` has a composite PK, so a concurrent duplicate now surfaces as an `IntegrityError`/500 instead of the intended `(True, "already_has")`. The race pre-existed; the window grew from ~0 to ~5 s. Hoist the multiplier fetch above the reads. | Backend Developer | FIXED (review #2): `grant_title` is back to its original single-transaction shape — the title/character/duplicate reads, the INSERT and `_grant_title_xp` run with nothing in between. The multiplier is resolved by `admin_grant_title` before any DB work and passed in; when it is omitted `grant_title` resolves it as its own first statement, still before the first query. Covered by `TestGrantTitleIsAtomic`: a second grant returns `(True, "already_has")`, XP is granted once, and `test_no_http_between_the_check_and_the_insert` asserts the HTTP call is the first event and never appears between the queries. **Follow-up (QA finding, same round):** the pre-existing part of the race — the SELECT-then-INSERT window itself — is now closed too: the INSERT's `flush()` is wrapped in `try/except IntegrityError` → `rollback()` → `(True, "already_has")`, so a lost race is answered idempotently instead of reaching `admin_grant_title`'s `except SQLAlchemyError` as a 500. No title XP is awarded on a lost race — the flush raises before `_grant_title_xp` is reached. `TestGrantTitleConcurrentDuplicate` is green and its `xfail` markers are removed; the MEDIUM entry is out of `docs/ISSUES.md`. |
| 19 | `services/locations-service/app/tests/test_xp_books.py:294-339` | MAJOR (QA). The guard tests pass `session = AsyncMock()`, whose `.new` is a truthy Mock, so the guard always returns `False` and **the rollback branch is never exercised by any test in the repo**; the endpoint tests mock `crud.add_experience` out entirely and use a `_FakeQuest` plain object that cannot expire. This is why #15 shipped green. A test with a real session, and an endpoint test with a real ORM `Quest`, would have caught it. | QA Test | FIX_REQUIRED |
| 20 | `character-service/app/crud.py:96`, `locations-service/app/crud.py:203` | MINOR. `float("nan") < 1.0` is False, so a malformed `{"multiplier": "NaN"}`/`Infinity` passes the clamp and `int(xp * nan)` then raises **outside** the try block — a 500 and the XP write never happens. This is the one path where XP *is* lost. Use `if not math.isfinite(multiplier) or multiplier < 1.0`. | Backend Developer | FIXED (review #2): exactly that guard in both services, with the reason in a comment. Covered by a parametrised test over `nan`/`inf`/`-inf` plus `test_nan_multiplier_still_awards_base_xp`, which asserts the award itself survives — this was the one path where XP could be lost. |
| 21 | `character-service/app/crud.py:2802-2804` | MINOR. After the release, `title.name` is read on an expired instance — sync session, so it silently re-SELECTs (and would raise `ObjectDeletedError` if the title vanished in the gap), despite the comment at `:2766-2768` claiming the rewards were materialised precisely to avoid that extra query. Comment and code disagree. | Backend Developer | FIXED (review #2): the materialised locals and the comment are gone with the rest of the round-2 restructure — `grant_title` reads `title.*` inside its single transaction again, so nothing is expired and no extra SELECT happens. |
| 22 | `battle-pass-service/app/crud.py:684-685` | NIT. `reward_type` / `reward_value` are assigned and never used — the return dict still reads them off the detached instance. Dead locals. | Backend Developer | FIXED (review #2): `claim_reward` is reverted to its pre-round-2 shape — the only remaining battle-pass change is the `xp_source` field in `_deliver_gold_xp`. The pre-existing «HTTP inside an open read transaction» in that function is recorded in `docs/ISSUES.md` (MEDIUM) instead, with an explicit warning not to fix it with a rollback. |
| 23 | `character-service/app/crud.py:124-128` | NIT. `apply_character_xp_buff` now has no caller in character-service — dead code left from the round-1 shape. | Backend Developer | FIXED (review #2): removed from character-service and replaced by the pure `crud.multiply_xp(xp, multiplier)`. locations-service keeps its own `apply_character_xp_buff` — there it has a real caller, the post path, which has no DB session at all. |
| 24 | `features/FEAT-168-…md:775` (§3.8) + `inventory-service/app/schemas.py:440` | NIT. §3.8 still specifies `v += Σ amount * chance/100 * DMG_W` although the `chance` factor was deliberately dropped, and `ItemDamageIn.chance` still carries no note that the engine never rolls it (round-1 issue #9 asked for one of the two). | Backend Developer | FIXED (review #2): both — the `chance/100` factor is out of the §3.8 formula, and `ItemDamageIn.chance` now carries a comment saying the engine never rolls it and why the field exists. |

#### Live Verification Results (round 2)
- AoE whitelist: all five engine shapes accepted, the three bogus ones rejected — verified against the
  running service.
- Corrupt stored rows: item with bad rows in all three child tables reads **200**, list **200**.
- Migration 025: 3 migrated / 2 skipped / 2 clamped on prod-like legacy books, legacy columns intact.
- DoT-only coating: `entry: 0.0` damage **and** `apply_effects … Poison` landed, effect in Redis state.
- XP with a book (umbrella 10 % + battle 25 % + quest 50 % + title 100 %): multipliers read back
  **1.35 / 1.60 / 2.10 / 1.10**; two real `add_rewards` calls moved `passive_experience`
  38 -> 173 -> 333, i.e. exactly `int(100 × 1.35)` then `int(100 × 1.60)` — the award path is correct
  after the transaction refactor.
- Admin form: coating fields carry real state values; no console errors beyond the pre-existing
  `/notifications/messenger/unread-count` 401.
- **Quest completion: 500.** See issue #15 — reproduced with a real `AsyncSession` inside
  locations-service, and the gold-bearing variant confirmed safe, pinning the trigger precisely.

#### Test data
The corrupt-row probe item, the five legacy-book probes, the DoT-only poison, the review book, the AoE
probes and the test quest were all deleted; belts unequipped; `active_buffs` cleared; character 761's
`passive_experience` restored to 38 and gold to 782; battle 216 force-finished; the admin's active
character is 706 as before. All throwaway containers removed. No commits.

---

### Review #3 — 2026-09-18
**Result:** FAIL

Everything from reviews #1 and #2 is closed, and I re-verified the round-2 blocker end-to-end through
the real endpoint rather than on the diff. Deleting the guard instead of patching it was the right
call, and the QA work this round is the strongest in the feature — both coverage gaps are
mutation-verified and reproduce to the number. What blocks the review is a **new class of issue
introduced by where the entry-point lookup was placed**: a blocking HTTP call inside `async` handlers,
a circular inventory→character→inventory call made while a transaction is open, and an unconditional
inventory-service round trip added to the two hottest read endpoints. All four are the same shape as
the 2026-09-04 pool-exhaustion incident this refactor exists to prevent, and all four should be fixable
together.

#### Automated Check Results
- `npx tsc --noEmit` — **PASS** · `npm run build` — **PASS** (`built in 28.57s`) · `py_compile` — **PASS**
- `docker compose config` — **PASS**
- `pytest` in throwaway `python:3.10-slim` containers, repo mounted, CI args, `CI=true` — all green and
  matching the reported counts exactly: inventory **1296 + 1 xfail**, locations **1245**,
  character **1030 + 1 skip**, battle **710**, battle-pass **119**, autobattle **126**.

#### Review #2 findings — all verified fixed
| R2 # | Verification |
|---|---|
| 15 (BLOCKER, quest) | **Fixed and verified through the real endpoint.** The XP-only quest (`reward_exp=10`, `reward_currency=0`) now returns **200** with `reward_exp: 15` (the book's ×1.5), the row is marked `completed` with a timestamp, `passive_experience` moved 38 → 53, and a replay is refused with **404 «Активный квест не найден»** — the replayable-quest exploit is gone. The gold-bearing variant also 200s (gold +5, XP +15). `complete_quest` resolves the multiplier as its first statement, before `get_quest_by_id`, and `add_experience` contains no `rollback()` at all. |
| 16 (MAJOR, guard) | **Removed, not patched** — the right call. `_release_db_connection` and `fetch_character_xp_multiplier` are gone from all three services; `test_xp_books.py:277-278` asserts `not hasattr(...)` for both, so they cannot come back silently. `battle-pass` is genuinely reverted (diff is 9 insertions confined to `_deliver_gold_xp`; `claim_reward` is byte-identical to HEAD) and its pre-existing HTTP-in-transaction is now an ISSUES entry that **explicitly warns against fixing it with a rollback**, citing this feature's review #2. Good knowledge capture. |
| 17 (MAJOR, QA) | **Closed, mutation-verified.** `test_item_out_schemas_serve_stored_rows.py` (58 tests) writes genuinely invalid rows via raw SQL — non-whitelisted `buff_type`/`target_side`/`aoe_shape`/`damage_type`, `chance` 500 and −20, `value` 0/−0.5, `duration` −3/999999 — and asserts all four read paths still serve them, with paired tests proving the same payloads still 422 on the way *in*. Re-adding the Out-schema inheritance turns the run into **55 failed / 12 passed**, matching the claim. |
| 18 (MAJOR, race) | **Fixed for real and verified live.** `try/except IntegrityError` → rollback → `(True, "already_has")`, no XP on the lost race. Six concurrent grants of the same title: **one** «Титул выдан», five «Персонаж уже имеет этот титул», **zero 500s**, exactly one `character_titles` row, XP awarded exactly once. |
| 19 (MAJOR, QA) | **Closed, mutation-verified.** `test_quest_complete_real_session.py` uses a real `AsyncSession` on aiosqlite with `expire_on_commit=False` and real ORM objects — no `AsyncMock`, no fake quest. Re-inserting the round-2 rollback produces **exactly 6 `MissingGreenlet` failures, all in `TestXpOnlyQuest`**, while the gold-bearing tests stay green — precisely the asymmetry that let the blocker ship. |
| 20–24 | NaN/inf now rejected before any arithmetic in **both** services (`math.isfinite` short-circuited ahead of `< 1.0`); dead `apply_character_xp_buff` and the battle-pass dead locals removed; the `title.name` comment/code mismatch resolved; §3.8's stale `chance/100` formula corrected. |

**The disputed race-test rewrite is legitimate.** The developer's argument is technically correct:
QA's original wrote the competing row from a `before_flush` hook, i.e. inside the same uncommitted
transaction, so on a single-connection SQLite engine the fix's own `rollback()` would have removed it
and "exactly one row survives" could never hold — that test would have been **red against a correct
fix**. The replacement commits the competing row first and blinds only the `CharacterTitle` dedup
query, which reproduces the losing request's real view, and it is strictly stronger: it asserts both
`(True, "already_has")` **and** that no XP was awarded. Mutation-killed twice — reverting the fix fails
both race tests with a real `UNIQUE constraint failed`, and awarding XP inside the handler fails the
no-double-XP test.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 25 | `character-service/app/crud.py:86`, called from `main.py:1288`, `:1817`, `:1889` (and `:669`) | **MAJOR.** `get_character_xp_multiplier` uses a **blocking** `httpx.get` with a 5 s timeout, and it is now called from `async def` handlers — `internal_evaluate_titles` (`main.py:1274`), `get_titles_for_character` (`:1811`), `get_full_profile` (`:1884`). A blocking call in an `async` endpoint stalls the event loop for **every** concurrent request on that worker, not just the caller. The service's only other sync-httpx helper is explicitly documented "for use in sync context", so this is new. Fix: make the helper `async` (these same endpoints already use `httpx.AsyncClient`) or wrap it in `run_in_threadpool`. | Backend Developer | FIXED (review #3): the helper is split in two. `get_character_xp_multiplier` stays blocking and is now documented «синхронный контекст только» — it is used exclusively from handlers declared with a plain `def` (`add_rewards`, `admin_grant_title`), which FastAPI runs in a threadpool. `get_character_xp_multiplier_async` (httpx.AsyncClient) is what every `async def` handler awaits. Both share `_xp_multiplier_url` / `_parse_xp_multiplier` / `_xp_multiplier_failed`, so the whitelist, fail-open, NaN/inf clamp and < 1.0 clamp cannot drift apart. `TestAsyncHelperExists` pins that the async variant is a coroutine function, uses `AsyncClient` and never touches `httpx.get`. |
| 26 | `inventory-service/app/main.py:1011`, `:1114` ↔ `character-service/app/main.py:1288` | **MAJOR, verified live.** inventory-service equip/unequip does a blocking `httpx.post` to `/characters/internal/evaluate-titles` **while its own DB transaction is open**; that endpoint now synchronously calls **back into inventory-service** for the multiplier. Measured: **one equip triggers 2 `xp-multiplier` calls back into inventory-service.** So an equip holds an inventory worker + DB connection while waiting on character-service, which waits on a second inventory worker + DB connection — the pool-exhaustion shape of the 2026-09-04 incident, moved one service over. Fix: let the internal evaluate-titles route pass `None` (= base XP, which `evaluate_titles` already handles), or make inventory fire that call after commit. | Backend Developer | FIXED (review #3): `internal/evaluate-titles` now passes `None` and makes **no call into inventory-service at all**, so the equip→titles→inventory loop is gone. The documented consequence: a title granted by that safety net awards **base** XP; the book applies where a title is granted deliberately (admin grant, level-up). `TestEquipCallbackMakesNoInventoryCall` asserts neither `httpx.get` nor `httpx.AsyncClient` is touched during a granting evaluate-titles call, and that the granted XP is the base amount. Verified the test fails if the lookup is put back. |
| 27 | `character-service/app/main.py:1889` (`full_profile`) | **MAJOR.** The multiplier lookup is **unconditional** on the game's hottest read endpoint, executed before the 404 check, to feed a branch (`if character.level > old_level` at `:1922`) that is taken almost never. Measured live: every `full_profile` GET now makes an extra inventory-service call. Fail-open means a degraded inventory-service does not break the profile, but it adds up to `XP_MULTIPLIER_TIMEOUT_SECONDS = 5.0` of latency to **every** profile load — a read path now has a hard latency coupling to inventory-service. | Backend Developer | FIXED (review #3): the lookup is **lazy** — it moved inside `if character.level > old_level`, so an ordinary profile read makes no inventory call at all, and the rare level-up path awaits the async helper. `test_full_profile_without_a_level_up_never_asks_inventory` installs a tripwire on the async helper and fails if it is called for nothing (verified against the old shape). |
| 28 | `character-service/app/main.py:1817` (`GET /{id}/titles`) | **MAJOR.** Same pattern, same class: unconditional extra inventory-service call on a read path. | Backend Developer | FIXED (review #3): `GET /{id}/titles` passes `None`, exactly like the internal callback — it is a hot read path and a grant there is a safety net, so it awards base XP rather than paying an inventory call on every request. Two tests assert no HTTP leaves the service, both when nothing is granted and when a title is. |
| 29 | `character-service/app/crud.py:2237-2238`, `:2755-2756` | MINOR. `add_rewards_to_character` and `grant_title` keep an **inline fallback** that fetches the multiplier when the caller passes none. No production caller reaches it today (all four `evaluate_titles` sites, `admin_grant_title` and the add_rewards handler pass it explicitly), but it is a footgun: a future caller with an open transaction silently re-introduces exactly the bug this refactor removed, and the docstrings encode an invariant nothing enforces. `evaluate_titles` already does the safe thing — `None` simply means base XP. Drop the two fallbacks and make `None` mean base XP everywhere. | Backend Developer | FIX_REQUIRED |
| 30 | `locations-service/app/main.py:3022` | MINOR. The quest multiplier is fetched even when `quest.reward_exp == 0` (the guard is at `:3053`). One wasted cross-service call per zero-XP quest completion. | Backend Developer | FIX_REQUIRED |
| 31 | `character-service/app/main.py:669-672` | NIT. The `if "level" in data.dict(exclude_unset=True)` guard is correct in principle, but the admin form sends the whole object, so in practice it likely fires on every admin save. Harmless (one call per admin action) — noting it so the guard is not mistaken for free. | Backend Developer | FIX_REQUIRED |
| 32 | `character-service/app/tests/test_xp_paths_real_session.py:30`; `inventory-service/app/tests/test_item_out_schemas_serve_stored_rows.py:335-336`; `locations-service/app/tests/test_xp_books.py:303-337` | NIT (QA). Unused `event` import left from the pre-rewrite race test; one assertion weakened by a tautological `or resp.status_code == 422` (the two equivalent checks elsewhere are strict); and the old `AsyncMock()`-session guards from issue #19 remain — they are harmless but must not be credited as coverage, since they provably cannot catch the rollback mutation. | QA Test | FIX_REQUIRED |

#### Live Verification Results (round 3)
- **XP-only quest** (the round-2 blocker): **200**, `reward_exp: 15`, row `completed`, XP 38 → 53,
  replay **404**. **Gold-bearing quest**: 200, gold +5, XP +15.
- **Title grant**: passive 68 → 108 (`20 × 2.0` from the title book), active +5 **unmultiplied**
  (books correctly do not accelerate skill points); second grant returns «Персонаж уже имеет этот
  титул» with no extra XP.
- **Concurrent grant race**: 6 parallel grants → 1 granted, 5 «уже имеет», 0 × 500, 1 row, XP once.
- **Battle reward with a book**: `passive_experience` 108 → 233, i.e. exactly `int(100 × 1.25)`.
- **Multiplier folding**: quest 1.50, title 2.00, battle 1.25 read back correctly from the internal
  endpoint; profession `xp_bonus` untouched at 1.0.
- **Equip**: 2 `xp-multiplier` callbacks into inventory-service per equip (issue #26).
- **`full_profile`**: median 105 ms solo, ~300 ms each under 6-way concurrency; the added
  inventory-service call is present on every request (issues #25/#27). A 6-way concurrency probe gave
  a 2.11× speedup rather than the 1.0× of full serialization, so the event-loop blocking is not
  conclusively demonstrated at this scale locally — issue #25 stands on the static evidence, which is
  unambiguous.

#### Test data
The two test quests, the two test titles (incl. the granted rows), the quest/title/battle XP books and
the equip probe were all deleted; belts unequipped; `active_buffs` cleared; character 761's
`passive_experience` restored to 38, `active_experience` to 0 and gold to 782; the admin's active
character is 706. All throwaway containers removed. No commits.

---

### Review #4 — 2026-09-18
**Result:** PASS

Findings 25–28 and both MINORs are fixed, and I verified each one live by measuring the actual
cross-service calls rather than reading the diff. The sync/async split is correct for every handler's
declaration, the equip→titles→inventory loop is gone, and the hot read paths make no inventory call at
all. Two items remain as **follow-ups, not blockers** — one is a product decision the user has already
been told about, the other a low-frequency trade-off that only needs to be written down.

#### Automated Check Results
- `npx tsc --noEmit` — **PASS** · `npm run build` — **PASS** · `py_compile` — **PASS** ·
  `docker compose config` — **PASS**
- `pytest` in throwaway `python:3.10-slim` containers, repo mounted, CI args, `CI=true`:
  character **1044 + 1 skip**, locations **1246**, inventory **1296 + 1 xfail**,
  battle-pass **119**, battle **710** — all green. (Counts match the report; I measured inventory as
  1296 passed + 1 xfailed with no skip, a trivial reporting difference.)

#### Sync/async split — correct at every call site
Matched each call against its handler's declaration:

| Handler | Declared | Variant used | Verdict |
|---|---|---|---|
| `admin_update_character` (`main.py:654`) | `async def` | `await …_async` (`:670`) | OK |
| `admin_grant_title` (`main.py:1220`) | plain `def` | blocking (`:1230`) | OK — threadpool |
| `get_full_profile` (`main.py:1892`) | `async def` | `await …_async` (`:1928`) | OK |
| `add_rewards` (`main.py:3484`) | plain `def` | blocking (`:3498`) | OK — threadpool |
| `complete_quest` (locations `main.py:3007`) | `async def` | `await` (helper is async there) | OK |

No blocking call from an `async def` anywhere — finding 25 is resolved. The whitelist, fail-open,
NaN/inf and `<1.0` clamps live in the shared `_parse_xp_multiplier` / `_xp_multiplier_failed` core, so
the two variants cannot drift; the only duplication is the two-line source whitelist check, which is
identical in both.

#### Live verification — measured, not assumed
**Note on method:** my first measurement still showed the old numbers. The running containers were
executing **stale code** — `main.py` was edited at 17:09 but the last uvicorn reload was at 16:51. I
restarted character-, locations- and inventory-service (all three were already running and were
returned to running) and re-measured. Everything below is from the restarted, current code.

| Path | Round 3 | Round 4 |
|---|---|---|
| Equip | **2** inventory callbacks | **0** |
| Unequip | 2 | **0** |
| `GET /full_profile` (no level-up) | 1 | **0** |
| `GET /{cid}/titles` | 1 | **0** |
| `PUT /admin/{cid}` with `level` | — | 2 (expected — the guard fires) |
| `PUT /admin/{cid}` without `level` | — | **0** |

The equip→evaluate-titles→inventory loop (finding 26) is measurably gone, and the two hot read paths
(27, 28) make no inventory call. Behaviour where the book **should** apply is intact:
- **Admin title grant**: `passive_experience` 1000 → **1040** = `20 × 2.0` (title book +100 %).
- **Battle reward**: unchanged from round 3, `int(100 × 1.25)`.
- **Quest with XP**: `reward_exp` reported as **15** (`10 × 1.5`), XP 1000 → 1015, row marked
  `completed`.
- **Quest with `reward_exp = 0`**: completes, gold awarded, and the lookup is skipped — the guard is
  `if quest.reward_exp > 0` at `locations/main.py:3046` (MINOR 30 fixed).
- Inline fallbacks are gone; `None` uniformly means "no book", pinned by an AST test
  (`test_xp_multiplier_call_shape.py:339 test_no_award_function_calls_the_blocking_helper`).

#### Test edits — legitimate
`test_admin_update_level_xp.py` replaced two `mock_instance.get.assert_called_once()` assertions with
`len(_passive_experience_gets(mock_instance)) == 1`, because the handler now makes a second GET (the
multiplier) through the same mocked client. That is strictly **more** precise than the original — it
now asserts *which* call was made, not merely how many. Not a weakening. The other three edited test
files were reviewed in earlier rounds. The new `test_xp_multiplier_call_shape.py` (14 tests) includes
the right tripwires, notably `test_no_http_when_a_title_is_granted`,
`test_full_profile_without_a_level_up_never_asks_inventory` and `test_granted_title_awards_base_xp`,
which pins the documented consequence rather than leaving it implicit.

#### Follow-ups (non-blocking)
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 33 | `locations-service/app/main.py:3051`, `character-service/app/main.py:1928` | **MINOR — trade-off to write down.** Both lazy lookups now run **after** the session has issued SELECTs, i.e. with a transaction open, so the handler holds a DB connection across a network call of up to 5 s. That is the 2026-09-04 shape — but only on rare branches (a real level-up, an XP-bearing quest completion) instead of every profile view, which is a good trade and clearly better than round 3. The comments at both sites explain why the session is *not* rolled back but do not acknowledge that the connection is held. Ask for the trade-off to be stated in the comment (and ideally in `docs/services/character-service.md` next to the existing table), so the next person does not "fix" it with a rollback — the exact trap the battle-pass ISSUES entry already warns about. | Backend Developer | FIXED (review #4): both comments now state the trade-off explicitly — the lookup runs with a transaction already open, the branch is rare, and the next person is told **not** to «fix» it with a rollback (the trap the battle-pass entry in `docs/ISSUES.md` warns about), but by moving the award out of the transaction. In character-service the note lives on `main._evaluate_titles_with_book`, which is now the single place all four automatic title paths go through. |
| 34 | `docs/services/character-service.md:262-263`; the buff label in the admin/item UI | **Product decision, already flagged to the user.** The engineer-facing documentation of "automatic title grants award base XP" is excellent — a per-handler table with the reason for each. What does not exist is a **player-facing** statement. A player who activates a title-XP book and then unlocks a title the usual way (automatically, via the equip / titles-listing safety nets) silently gets base XP, while the same title granted by an admin gives double; the buff is still labelled «к опыту персонажа за титулы» with no qualifier, so nothing lets the player tell which case they are in. Either qualify the label/tooltip, or resolve the multiplier lazily **inside** the grant branch of `evaluate_titles` (the pattern already used for `full_profile`) — that would restore the book everywhere and make the inventory callback as rare as an actual title unlock rather than per-equip. PM/user call, not a code defect. | Orchestrator (PM) | RESOLVED (review #4 follow-up 1): the book is no longer lost on automatic grants. `evaluate_titles` is split into `find_unlockable_titles` (read-only) + `grant_unlocked_titles`, and every automatic path goes through `main._evaluate_titles_with_book`, which looks the multiplier up **only when a title actually unlocked and carries passive XP**. So the product decision disappears: the book applies everywhere a title is granted, while an equip that unlocks nothing still makes zero callbacks. |

#### Test data
The two test titles (and their granted rows), the two test quests, the XP book and the equip probe
were deleted; belts unequipped; `active_buffs` cleared; character 761 restored to
`passive_experience = 38`, `active_experience = 0`, `level = 3`, `stat_points = 0`, gold 782; the
admin's active character is 706. All throwaway containers removed. character-, locations- and
inventory-service were restarted (to load the code under test) and are running. No commits.

---

### Review #5 — 2026-09-18
**Result:** FAIL

Follow-up #33 is done properly. Follow-up #34 is the right design and works on every path **except the
one it was written for**: on the equip/unequip path the book lookup deadlocks against inventory-service,
times out after 5 s and silently falls back to base XP. So the round-3 compromise is not removed — it
has been converted from an intentional, documented rule into an accidental, undocumented one that also
costs the player a 5-second stall. Round 4's state was strictly better.

#### Automated Check Results
- `pytest` in throwaway `python:3.10-slim` containers, repo mounted, CI args, `CI=true`:
  character **1046 + 1 skip**, locations **1246**, inventory **1296 + 1 xfail**, battle-pass **119** —
  all green, counts match the report.
- Containers restarted before every measurement; startup at 17:39 against a last edit at 17:28, so all
  live results below are from the current code.

#### Follow-up #33 — done
The trade-off is written at both sites (`locations/main.py` quest award and
`character/main.py:653 _evaluate_titles_with_book`): the lookup runs with a transaction open, the branch
is rare, the fix is **not** a rollback, and the battle-pass `docs/ISSUES.md` entry is named as the trap.
Exactly what was asked.

#### Follow-up #34 — right design, but broken on the equip path
The split is the shape I suggested and is clean: `find_unlockable_titles` (read-only) →
`title_reward_needs_the_book` → `grant_unlocked_titles` (one transaction, no network), behind one helper
used by all four automatic paths. The retained `evaluate_titles` wrapper is documented as
sync-convenience and makes no network call.

Measured live, and the contrast is decisive:

| Trigger | Lookups | XP awarded | Wall time |
|---|---|---|---|
| Equip / unequip, nothing unlocks | **0** | — | 241 ms |
| Unlock of a title with **no** passive reward (via equip) | **0** | active +3, correct | fast |
| Unlock of a passive-XP title **via `GET /{cid}/titles`** | **1, succeeded** | 3000 → **3200** = `100 × 2.0` ✔ | 80 ms |
| Unlock of a passive-XP title **via equip / unequip** | 1 attempted, **timed out** | 1000 → **1100** = base ✘ | **5429 ms** |

**Re-measured after the fix (Backend Dev, 2026-09-20).** The three fire-and-forget side calls in
`equip_item` / `unequip_item` are now awaited through `httpx.AsyncClient`, so the loop stays free:

| Scenario | Multiplier lookups | XP awarded | Wall clock |
|---|---|---|---|
| Equip that unlocks a passive-XP title (×2 book) | **1**, 200 OK | 0 → **2000** = 1000 × 2 ✔ | **432 ms** (was 5429) |
| Equip that unlocks nothing | **0** ✔ | — | **329 ms** |
| Unequip | 0 | — | 216 ms |

Measured on character 763 with a purpose-built title (`items_equipped >= 1`, `reward_passive_exp = 1000`)
and an active `character_xp_bonus = 1.0`. Two earlier runs showed ~5.4 s for *both* scenarios including the
one that unlocks nothing; that was a concurrent agent's test suite loading the shared dev stack (visible as
hundreds of `xp-multiplier` 401s for other characters in the same log window), not this code path. All test
data removed afterwards.

`character-service` logs the failure as
«Не удалось получить множитель опыта (character_xp_title_bonus) для персонажа 761: timed out —
начисляю без баффа». Fail-open then hides it: the player loses the book silently and waits 5 s.

**Cause — the round-3 circular call (finding 26) was never actually removed, only made rare.**
`inventory-service` runs a single uvicorn worker (no `--workers`), and `equip_item`
(`inventory-service/app/main.py:837`) and `unequip_item` (`:1026`) are `async def` handlers that make a
**blocking** `httpx.post` to `/characters/internal/evaluate-titles` (`:1010-1016`, timeout 5 s). That
blocking call stalls inventory-service's event loop. character-service then awaits a callback into
inventory-service for the multiplier — which that blocked event loop cannot serve — so the call times
out. Round 4 avoided this by never looking up on this path; round 5 reintroduces the lookup without
fixing the loop underneath it, so the loop now fires for real every time a passive-XP title unlocks
from an equip.

The dev's measurement («exactly 1 callback and XP 33 → 233») reproduces — but only through a path that
does not have inventory-service in the chain, which is exactly what my `GET /{cid}/titles` row above
shows. The in-process tripwire tests cannot see this either: they mock the HTTP boundary, so they
verify the *call shape* correctly and are not dishonest — they simply cannot observe a cross-service
event-loop deadlock. That is worth knowing about their coverage, not a criticism of them.

#### Issues Found
| # | File:line | Description | Assigned To | Status |
|---|-----------|-------------|-------------|--------|
| 35 | `inventory-service/app/main.py:1010-1016` (equip) and the same call in `unequip_item` (`:1026`) ↔ `character-service/app/main.py:653` | **BLOCKER (functional + latency), reproduced live.** A title with passive XP unlocked by equipping or unequipping awards **base XP instead of the book's**, and the request stalls **5.4 s**. Both handlers are `async def` yet call `httpx.post` **blocking**, freezing inventory-service's single-worker event loop while character-service awaits a multiplier callback into that same service. Fix the root cause rather than the symptom: make inventory-service's evaluate-titles call non-blocking (`httpx.AsyncClient` + `await`, or fire it after the response / as a background task) so its loop stays free. Then the book applies on every path and the 5 s stall disappears. If that is out of scope, revert this path to round 4's behaviour (no lookup on the internal route) — which was correct, documented, and fast — and keep #34 open. | Backend Developer | **FIXED** (root cause; see log 2026-09-20 12:xx) |
| 36 | `character-service/app/crud.py` (`get_character_xp_multiplier*`) | MINOR. Fail-open is right, but a *timeout* is currently indistinguishable from "no book" to everyone above it, which is what let this ship green. Consider logging the timeout case at `error` rather than `warning`, or returning a flag the caller can surface, so a systematically failing lookup is visible instead of silently degrading every award. | Backend Developer | FIXED (review #5): fail-open kept, fail-**silent** removed. Both services gained `lookup_character_xp_multiplier[_async]` returning an `XpMultiplierLookup(multiplier, ok, reason, elapsed_ms)`, so a caller can tell «no book» (`ok=True`, 1.0) from «the lookup failed» (`ok=False`, reason `request_failed` / `bad_payload` / `out_of_range` / `unknown_source`). Every failure is now logged at **error** level with the character id, the XP source and the elapsed milliseconds — the timeout that shipped green this round would have been loud. The existing `get_character_xp_multiplier[_async]` remain as thin float wrappers, so no call site or test changed. `TestFailedLookupIsVisible` in both services pins the level, the message contents and the flag; verified it goes red again if the failure path is made silent. |

#### Regression check — everything verified in round 4 still holds
- Equip / unequip with nothing to unlock: **0** lookups, 241 ms.
- `GET /full_profile` without a level-up: **0** lookups.
- `GET /{cid}/titles` with nothing to unlock: **0** lookups.
- Title unlock with no passive reward: **0** lookups, active XP +3 unmultiplied (correct — books never
  accelerate skill points).
- The sync/async split at every handler is unchanged and still correct.
- Quest, battle-reward and admin-grant paths were re-checked earlier in this round and are unaffected by
  the #34 refactor.

#### Test data
The five test titles (and their granted rows), the XP book and the equip probe were deleted; belts
unequipped; `active_buffs` cleared; character 761 restored to `passive_experience = 38`,
`active_experience = 0`, `level = 3`, `stat_points = 0`, gold 782; the admin's active character is 706.
All throwaway containers removed; character-, locations- and inventory-service were restarted to load
the code under test and are running. No commits.

---

### Review #6 — 2026-09-18
**Result:** PASS — feature closed

Both review #5 findings are fixed, and the fix for #35 went after the root cause rather than the one
call I named — which is the right instinct and turned up five more instances of the same bug. Verified
on a quiet stack, containers restarted first. Nothing from rounds 4–5 regressed.

#### Automated Check Results
- `npx tsc --noEmit` — **PASS** · `npm run build` — **PASS** · `py_compile` — **PASS** ·
  `docker compose config` — **PASS**
- `pytest` in throwaway `python:3.10-slim` containers, repo mounted, CI args, `CI=true`:
  character **1054 + 1 skip**, locations **1250**, inventory **1300 + 1 xfail**, battle-pass **119**,
  battle **710**, autobattle **126** — all green.

#### #35 — fixed at the root, verified independently
I ran my own AST audit of `inventory-service/app/main.py` rather than trusting the new test:
- blocking `httpx`/`requests` calls **directly** inside an `async def`: **0**;
- plain-`def` helpers that still contain a blocking call: 4 (`_add_item_to_inventory_core`,
  `_reconcile_perks`, `_track_cumulative_stats`, `eat_food`) — correct, they exist for the
  threadpooled plain-`def` handlers;
- `async def` handlers reaching any of those helpers: **none**.

The new detector in `test_outgoing_internal_headers.py:312` is honest — it walks the real `main.py`
AST, resolves the innermost enclosing function for each blocking call and fails if it is `async`, plus
a second test for the indirect sync-helper case. Same technique I used, same answer. Not a tautology.

Measured live on a quiet stack:

| Case | Round 5 | Round 6 |
|---|---|---|
| Equip unlocking a passive-XP title | 5429 ms, lookup **timed out**, base XP | **318 ms**, **1 lookup, succeeded**, XP 0 → **2000** = `1000 × 2.0` ✔ |
| Equip unlocking nothing | 241 ms, 0 lookups | 214–235 ms, 0 lookups |
| Unequip | — | 240–287 ms |
| `GET /full_profile` | 0 lookups | 65 ms, 0 lookups |
| `GET /{cid}/titles` | 0 lookups | 38 ms, 0 lookups |

The deadlock is gone and the book now applies on the equip path — the outcome follow-up #34 was
aiming for.

#### #36 — done
`XpMultiplierLookup(multiplier, ok, reason, elapsed_ms)` with `logger.error` carrying the character id,
the XP source, the elapsed ms and an explicit «бонус книги потерян». Fail-open is unchanged (still
1.0), and the wrappers kept every call site untouched. A systematically failing lookup is now visible
instead of silently degrading every award — which is exactly what let #35 ship green.

#### On the polluted-measurement claim
The storm was real: inventory-service logs carry **218** `401` responses on `xp-multiplier` for
character ids `1` and `99999` — synthetic ids, not mine (I used 761). So the dev's early numbers were
plausibly polluted.

It does **not** explain the round-5 finding, and I want that on the record so the diagnosis is not
mis-filed: in the same window, the *same* equip endpoint answered in 241 ms when nothing unlocked and
took 5429 ms only when a title unlocked, while `GET /{cid}/titles` unlocked a passive-XP title
successfully in 80 ms. A generic load storm would have slowed all three equally. The slow path tracked
the *unlock condition*, not the clock — and the fix that resolved it was removing six blocking calls
from `async def` handlers, which is the remedy for a deadlock, not for noisy neighbours. Both things
were true at once.

#### Regression pass — rounds 4–5 behaviour intact
- **Quest**, `reward_exp = 100` with a ×1.5 book → `reward_exp: 150`, marked `completed`;
  `reward_exp = 0` quest → 320 ms, gold awarded, **no lookup**.
- **Admin title grant** (passive 50, ×2 book) → +100, 89 ms.
- **Battle reward** → `new_xp` +125 = `int(100 × 1.25)`.
- **Hot read paths** → 0 lookups, 38–65 ms.
- **Real battle** (items re-created end to end): buff potion applied with `source: "item:119"`; damage
  scroll `base 18 + entry 40 = 58` through the normal formula; poison coating applied (`turns_left: 3`,
  `bonus_damage: 12`); a second poison correctly `item_rejected`; antidote consumed with no
  `effects_removed` because there was nothing removable — correct, not a regression.

#### Observation (no action needed)
The **first** request to each freshly restarted service takes ~5.4 s — I saw it once on `equip` and
once on `complete_quest`, and in both cases the immediately following identical requests ran in
214–278 ms and the XP multiplier had applied correctly, so it is a cold-start effect, not a timeout in
the feature. Worth knowing because it looks exactly like the #35 symptom and will show up on the first
request after every prod deploy. This is also the most likely source of a misleading one-shot
measurement — mine included, which is why every number above was taken at least twice.

#### `character-attributes-service/app/perk_evaluator.py:63` — ISSUES entry, not a fix here
Agreed with the dev's read, and I confirmed it: an AST audit of that service finds **0** blocking calls
inside `async def`, so `_fetch_gold_balance` is threadpooled and fail-open — no loop freeze, and out of
FEAT-168's scope. It still deserves a tracked entry, for two reasons beyond the blocking-call family:
it fetches an entire `/full_profile` to read one field (`currency_balance`), and `/full_profile` is now
a heavier endpoint that can itself trigger title evaluation and an inventory lookup — so a perk
evaluation can transitively reach inventory-service. Suggest a LOW/MEDIUM entry naming both, rather
than touching it in this feature.

#### Test data
The five test titles, four test quests, the XP book, the equip probe and the four battle items were
deleted; the battle was force-finished; belts unequipped; `active_buffs` cleared; character 761
restored to `passive_experience = 38`, `active_experience = 0`, `level = 3`, `stat_points = 0`,
gold 782; the admin's active character is 706; `item_effects` back to 0 rows. All throwaway containers
removed; character-, locations-, inventory- and character-attributes-service were restarted to load the
code under test and are running. No commits.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-19 12:00 — PM: фича создана (этап 3 из 3 ребаланса профессий), запускаю анализ
[LOG] 2026-09-19 12:05 — Analyst: начал анализ на базе f50284f — боевой движок, навыки, расходники, автобой, подземелья, опыт, админка
[LOG] 2026-09-19 12:35 — Analyst: главный вывод — движок эффектов в бою уже готов (buffs.py, FEAT-143/146), предметы в него просто не подключены; нужен канал данных, а не новая механика
[LOG] 2026-09-19 12:40 — Analyst: баг уже исправлен, запись «DoT-эффекты и контроли не работают» помечена DONE в ISSUES.md (сделано в FEAT-143)
[LOG] 2026-09-19 12:45 — Analyst: обнаружены баги, добавлены в ISSUES.md — событие item_broken не переводится в журнале боя; у /use_item нет проверки «не в бою»; быстрый слот удаляется целиком независимо от количества; сообщение use-buff-item всегда «+N% XP»
[LOG] 2026-09-19 12:50 — Analyst: расхождение с брифом — сегодняшняя «книга опыта» ускоряет ТОЛЬКО опыт профессии, опыт персонажа буфф не трогает; нужен ответ пользователя
[LOG] 2026-09-19 12:55 — Analyst: анализ завершён, раздел 2 заполнен; затронуто 4 сервиса + фронтенд (подземелья правок не требуют, автобой требует)
[LOG] 2026-09-19 13:10 — PM: пользователь ответил на вопросы анализа (раздел 1 обновлён), запускаю архитектора
[LOG] 2026-09-19 13:15 — Architect: начал проектирование — читаю движок эффектов, схему навыков, админку предметов
[LOG] 2026-09-19 13:40 — Architect: решение — предметам добавляются две дочерние таблицы (item_effects, item_damage_entries) с той же формой строк, что у навыков; новой боевой математики не пишем
[LOG] 2026-09-19 13:45 — Architect: яд на оружии — новое поле weapon_coating в состоянии участника (Redis), повторное нанесение отклоняется событием item_rejected без потери хода
[LOG] 2026-09-19 13:50 — Architect: очищение настраивается строкой Cleanse у предмета; полный контроль с пропуском хода не снимается никогда — правило движка в buffs.py
[LOG] 2026-09-19 13:55 — Architect: xp_bonus остаётся опытом профессии (миграции данных нет), добавляются gathering_xp_bonus и character_xp_bonus; опыт персонажа — через внутренний эндпоинт множителя
[LOG] 2026-09-19 14:00 — Architect: спроектировано 13 задач, 1 миграция (с откатом), 1 новый внутренний эндпоинт, 3 расширенных контракта; новых разрешений RBAC не требуется
[LOG] 2026-09-19 14:05 — Architect: обязательные QA-задачи — юнит-тесты buffs.py (их не было) и тесты боя без мока движка эффектов, включая бой со старым состоянием без новых полей
[LOG] 2026-09-19 14:10 — Architect: вопрос к пользователю — должна ли книга опыта персонажа ускорять опыт от отыгрыша/квестов/титулов или только боевые награды
[LOG] 2026-09-19 14:30 — Backend Dev: начал задачу #3 — buffs.py (обновление эффектов вместо накопления, снятие эффектов)
[LOG] 2026-09-19 14:45 — Backend Dev: apply_new_effects теперь обновляет запись с тем же (имя, атрибут, владелец): duration = max(старая, новая), magnitude = новая, fresh = True. ВАЖНО: правило общее, эффекты навыков тоже перестали складываться — осознанное изменение по §3.4
[LOG] 2026-09-19 14:50 — Backend Dev: добавлены remove_effects(state, pid, *, selector, limit=0) и is_unremovable(eff); селекторы debuff / periodic_damage / control_partial / stat_down / all / имя эффекта, limit=0 — снять все; пустой селектор = debuff
[LOG] 2026-09-19 14:55 — Backend Dev: полный контроль (Stun, Poison:paralysis) не снимается никаким очищением, включая selector="all"; список берётся из evaluate_control, чтобы правила не разъехались
[LOG] 2026-09-19 15:00 — Backend Dev: старые записи из Redis (без owner_id / fresh) читаются с дефолтами, поведение боёв, начатых до деплоя, не меняется
[LOG] 2026-09-19 15:10 — Backend Dev: проверки — py_compile чист, весь pytest battle-service в Docker: 533 passed, 4 skipped; правок в существующих тестах не потребовалось (накопление эффектов нигде не зафиксировано). Задача #3 завершена, обновлён docs/services/battle-service.md
[LOG] 2026-09-19 15:25 — Backend Dev: правка по замечанию PM — при обновлении уже активного эффекта флаг fresh больше не выставляется заново (иначе подновлённый яд пропускал бы тик урона); fresh ставится только по-настоящему новому эффекту. Отклонение от §3.4 зафиксировано addendum'ом в разделе 3, документация обновлена
[LOG] 2026-09-19 15:35 — Backend Dev: повторные проверки после правки — py_compile чист, весь pytest battle-service в Docker: 533 passed, 4 skipped
[LOG] 2026-09-19 15:40 — Backend Dev: начал задачи #1 и #2 — слой данных эффектов предметов и книги опыта в inventory-service
[LOG] 2026-09-19 16:00 — Backend Dev: модели ItemEffect / ItemDamageEntry (зеркала skill_perk_effects / skill_perk_damage) + три nullable-колонки у items (consumable_action, coating_turns, coating_bonus_damage) — VARCHAR, а не ENUM, чтобы не блокировать таблицу items
[LOG] 2026-09-19 16:15 — Backend Dev: схемы Pydantic v1 — ItemEffectIn/Out, ItemDamageIn/Out, вся валидация из §3.12 (белые списки цели/слота/типа урона, диапазоны, не больше 20 эффектов и 10 строк урона, боевые эффекты только у consumable/scroll и не у еды)
[LOG] 2026-09-19 16:25 — Backend Dev: вложенные списки едут внутри ItemCreate под существующими правами items:create / items:update, новых разрешений RBAC не добавлялось; на PUT замена целиком, но только если клиент прислал список
[LOG] 2026-09-19 16:35 — Backend Dev: GET /items/{id}, ItemDetailResponse и GET /characters/{cid}/fast_slots отдают effects / damage_entries / consumable_action / coating_*; в слот добавлены и четыре поля восстановления. Всё additive, ItemBulkResponse не тронут
[LOG] 2026-09-19 16:50 — Backend Dev: миграция 024_item_battle_effects (down_revision 023_weapon_damage_backfill); откат не удалял индексы отдельно — MySQL отказывается («needed in a foreign key constraint»), индексы уходят вместе с таблицами
[LOG] 2026-09-19 17:00 — Backend Dev: миграция проверена на dev-MySQL — upgrade → downgrade -1 → upgrade, база оставлена на head, таблицы и колонки на месте
[LOG] 2026-09-19 17:10 — Backend Dev: книги опыта — get_xp_multiplier(db, cid, buff_type="xp_bonus"), award_gathering умножает опыт сбора на gathering_xp_bonus, белый список ALLOWED_BUFF_TYPES, новый внутренний GET /inventory/internal/characters/{cid}/xp-multiplier под verify_internal_token
[LOG] 2026-09-19 17:15 — Backend Dev: баг исправлен, удалён из ISSUES.md — у POST /{cid}/use_item появилась проверка «не в бою»
[LOG] 2026-09-19 17:20 — Backend Dev: баг исправлен, удалён из ISSUES.md — сообщение use-buff-item собирается по словарю BUFF_TYPE_LABELS («к опыту профессии / сбора / персонажа»), а не хардкодом «XP»
[LOG] 2026-09-19 17:30 — Backend Dev: проверки — py_compile чист, весь pytest inventory-service в Docker: 1032 passed, 1 skipped. Дополнены существующие тесты: battle-lock для use_item (в бою 400, вне боя 200) и два случая по опыту сбора с баффом и без. Задачи #1 и #2 завершены, обновлён docs/services/inventory-service.md
[LOG] 2026-09-19 17:20 — Frontend Dev: начал задачи #7, #8, #9 — редактор эффектов в админке, журнал боя и быстрые слоты, подсказки в инвентаре
[LOG] 2026-09-19 17:35 — Frontend Dev: общий модуль utils/itemEffects.ts — один разбор боевой настройки предмета на русский для боя и инвентаря, чтобы описания нигде не разошлись; все поля необязательные, как и на бэкенде
[LOG] 2026-09-19 17:45 — Frontend Dev: describeEffect научился строкам Cleanse (что снимает, сколько), добавлены русские названия селекторов очищения и напоминание, что полный контроль не снимается
[LOG] 2026-09-19 18:05 — Frontend Dev: задача #7 — новый ItemEffectSections.tsx (урон, эффекты, очищение, яд на оружие), словарь импортируется из AdminSkillsPage/skillConstants, а не копируется; BUFF_TYPE_OPTIONS вырос до трёх типов опыта, добавлена проверка значений перед отправкой с русским сообщением
[LOG] 2026-09-19 18:20 — Frontend Dev: задача #8 — в журнал боя добавлены item_rejected, weapon_coating_applied, weapon_coating_expired, effects_removed, item_broken (баг ISSUES #2) и урон от предмета; в item_use появилась выносливость (баг ISSUES #6); запасной перевод больше никогда не печатает английское имя события
[LOG] 2026-09-19 18:30 — Frontend Dev: в списке быстрых слотов видно, что делает предмет, сколько его осталось и почему второй яд нельзя нанести — такой предмет отключён с пояснением
[LOG] 2026-09-19 18:40 — Frontend Dev: задача #9 — карточка предмета показывает блок «В бою», всплывающая подсказка ячейки — краткую сводку; ActiveBuffIndicator подписывает все три типа баффа опыта
[LOG] 2026-09-19 18:55 — Frontend Dev: проверки в одноразовом контейнере — npx tsc --noEmit чисто, npm run build успешно; package-lock.json не менялся, контейнеры не оставлены
[LOG] 2026-09-19 19:05 — Frontend Dev: живая проверка на поднятом стенде — созданы тестовые зелье (стат + очищение + урон) и яд (weapon_coating 4 хода, +12 урона), прочитаны обратно без потерь, некорректный яд отклонён 422; тестовые предметы удалены, дочерние строки ушли каскадом
[LOG] 2026-09-19 19:10 — Frontend Dev: задачи #7, #8, #9 завершены. Не проверено вживую: сам бой с применением предметов — задачи #4 (боевой шаг) ещё нет, события журнала и weapon_coating в состоянии участника отрисовываются по контракту §3.5/§3.7
[LOG] 2026-09-19 17:30 — PM: уточнения пользователя — эффекты навыков независимы (у предметов refresh), книги опыта настраиваются по источникам опыта
[LOG] 2026-09-19 19:20 — Backend Dev: правка #3 по уточнению пользователя — эффекты НАВЫКОВ снова накапливаются (каждое применение = отдельная запись со своей длительностью и силой, кровотечения 2х5 и 3х10 тикают параллельно), обновление оставлено только для ПРЕДМЕТОВ
[LOG] 2026-09-19 19:25 — Backend Dev: у apply_new_effects добавлен необязательный параметр source=("item", item_id); ключ обновления — (источник, имя, атрибут, владелец), эффекты без источника (навыки и старые записи из Redis) всегда добавляются новой записью; источник хранится строкой "item:42" ради JSON в Redis. Задокументировано в §3.6 (Addendum 2) и в docs/services/battle-service.md
[LOG] 2026-09-19 19:35 — Backend Dev: проверки — py_compile чист, pytest battle-service в Docker: 531 passed, 4 skipped, 2 падения в test_item_usage.py (старое ожидание «стопка расходуется целиком») — это задача #4 (правка main.py по ISSUES #4), к buffs.py отношения не имеет: эти тесты мокают buffs целиком
[LOG] 2026-09-19 19:40 — Backend Dev: начал задачу #4 — боевой шаг предмета, яд на оружии, очищение, события журнала
[LOG] 2026-09-19 19:50 — Backend Dev: inventory_client.get_fast_slots больше не дозапрашивает карточку каждого предмета — inventory-service отдаёт восстановление и боевую настройку прямо в ответе слотов; всё читается с дефолтами, старый ответ просто даст слот без эффектов
[LOG] 2026-09-19 20:10 — Backend Dev: шаг предмета переписан — эффекты предмета идут в тот же движок, что и эффекты навыков (свой бросок шанса по удаче/стойкости), строки урона считаются обычной боевой формулой с критами, сопротивлениями, уклонением и AoE, строка Cleanse снимает эффекты через remove_effects
[LOG] 2026-09-19 20:20 — Backend Dev: яд на оружии — новое поле weapon_coating у участника; прибавка к урону подмешивается в amount каждой строки урона оружием (значит, проходит через баффы, крит и сопротивления), эффекты яда вешаются на тех, кто реально получил урон, по разу за ход
[LOG] 2026-09-19 20:25 — Backend Dev: второй яд при действующем первом — событие item_rejected, предмет НЕ расходуется, остальной ход отыгрывается полностью (400 стоила бы игроку хода)
[LOG] 2026-09-19 20:30 — Backend Dev: длительность яда убывает рядом с decrement_durations, в конце хода владельца; на нуле яд снимается и пишется weapon_coating_expired
[LOG] 2026-09-19 20:35 — Backend Dev: баг исправлен, удалён из ISSUES.md — стопка расходуется по одной штуке, слот уходит из пояса только на нуле
[LOG] 2026-09-19 20:40 — Backend Dev: weapon_coating отдаётся клиенту во всех четырёх сборках runtime-состояния (обычное, внутреннее, зрительское, WS) и описан в схеме BattleRuntimeParticipant как необязательное поле
[LOG] 2026-09-19 20:50 — Backend Dev: проверки — py_compile чист, весь pytest battle-service в Docker: 539 passed. Обновлены два теста из test_item_usage.py, ожидавшие старого «слот удаляется целиком», и добавлены случаи «последняя штука освобождает слот» и «слот из старого состояния без quantity». Задача #4 завершена, обновлён docs/services/battle-service.md
[LOG] 2026-09-19 21:00 — Backend Dev: начал задачу #5 — оценка предметов в автобое (сегодня зелья, яды и свитки стоят 0 и никогда не берутся)
[LOG] 2026-09-19 21:15 — Backend Dev: value(slot) расширен — строки урона (DAMAGE_WEIGHT), эффекты на себя/союзника (BUFF_WEIGHT), эффекты на врага (DEBUFF_WEIGHT), яд на оружие (COATING_WEIGHT), очищение (CLEANSE_WEIGHT); все веса и пороги нужды — именованные константы
[LOG] 2026-09-19 21:20 — Backend Dev: яд при уже нанесённом яде обесценивает слот целиком (боевой сервис вернёт item_rejected, а предмет за ход только один — ход по предмету пропал бы зря); очищение считается ценным, только если на участнике реально есть снимаемый эффект, полный контроль не учитывается — логика селекторов зеркалит buffs.py
[LOG] 2026-09-19 21:25 — Backend Dev: weapon_coating и active_effects берутся из runtime через новый _actor_state(ctx); у _pick_best добавлен НЕОБЯЗАТЕЛЬНЫЙ четвёртый параметр, старые вызовы (и существующие тесты) работают без правок; все новые поля читаются с дефолтами — слот из состояния до деплоя оценивается ровно как раньше
[LOG] 2026-09-19 21:35 — Backend Dev: проверки — py_compile чист, весь pytest autobattle-service в Docker: 78 passed, правок в существующих тестах не потребовалось; ручная проверка оценки — свиток урона выигрывает у пустого слота, зелье баффа выбирается, яд при действующем яде даёт item_id=None, противоядие берётся только при наличии дебаффа. Задача #5 завершена, обновлён docs/services/autobattle-service.md
[LOG] 2026-09-19 19:30 — Backend Dev: начал задачу #6 — гибкие книги опыта; узкая задача «книга опыта персонажа» заменена, проект записан в раздел 3 как §3.9-bis
[LOG] 2026-09-19 19:40 — Backend Dev: найдены все точки начисления опыта персонажа — вопреки §2.6 они в трёх сервисах: бои и титулы в character-service, посты и задания в locations-service, боевой пропуск идёт через тот же add_rewards, что и бои
[LOG] 2026-09-19 19:50 — Backend Dev: модель — новая дочерняя таблица item_xp_buffs (тип опыта, прибавка, длительность), у предмета до 8 строк; старые колонки buff_type/buff_value/buff_duration_minutes оставлены и работают как запасной вариант, так что книги, созданные раньше, не ломаются
[LOG] 2026-09-19 19:55 — Backend Dev: восемь типов опыта — профессия (старый xp_bonus, смысл не менялся), сбор, «весь опыт персонажа» и пять источников по отдельности: бои, отыгрыш, задания, титулы, боевой пропуск. Общая книга и точечная складываются: 25 % за задания + 10 % на всё = ×1.35; сложение спрятано в get_xp_multiplier, чтобы вызывающие не могли ошибиться
[LOG] 2026-09-19 20:05 — Backend Dev: миграция 025_item_xp_buffs с переносом старых книг в новую таблицу; проверена на dev-MySQL upgrade → downgrade → upgrade, перенос строки проверен отдельно; откат ничего не теряет, старые колонки не трогались
[LOG] 2026-09-19 20:15 — Backend Dev: use-buff-item применяет все строки предмета сразу (по одному active_buffs на тип), сообщение перечисляет все баффы; старые поля ответа сохранены ради совместимости, добавлен список buffs
[LOG] 2026-09-19 20:25 — Backend Dev: множители подключены на местах начисления — бои и титулы (character-service), отыгрыш и задания (locations-service), боевой пропуск шлёт свой xp_source в add_rewards. battle-service не трогал. Везде fail-open: если inventory-service недоступен, опыт начисляется по базе с предупреждением в лог
[LOG] 2026-09-19 20:30 — Backend Dev: добавлен батч-эндпоинт GET /inventory/internal/characters/{cid}/xp-multipliers?buff_types=…; одиночный эндпоинт из §3.3.4 не менялся
[LOG] 2026-09-19 20:45 — Backend Dev: проверки — py_compile чист; полный pytest в Docker: inventory 1032 passed / 1 skipped, character 960 passed / 1 skipped, locations 1206 passed, battle-pass 112 passed; живая проверка множителей, валидации, отката миграции и fail-open. Задача #6 завершена
[LOG] 2026-09-19 20:50 — Backend Dev: фронтенду нужна доработка — вместо одного выбора типа баффа список строк «Ускорение опыта» на 8 типов (контракт в §3.9-bis E); бэкенд принимает обе формы, пока форма не переделана
[LOG] 2026-09-19 20:10 — Frontend Dev: сверил отрисовку журнала с настоящими событиями задачи #4 на живом бою — совпало почти всё; поправлено: у промаха по предмету теперь видно название предмета, effects_removed читает who/target/source (снимает с себя или с союзника) и объекты в removed, в item_rejected показываются название активного яда и сколько ходов осталось, в weapon_coating_applied — прибавка к урону, в item_use — остаток стопки
[LOG] 2026-09-19 20:20 — Frontend Dev: приведены к правде тексты — шанс у строк урона предмета не проверяется движком, поэтому поле «Шанс» убрано из раздела урона в админке и из описаний, вместо него пояснение; длительность яда подписана «ходов с ядом (вкл. текущий)», так как яд усиливает уже ту атаку, на которой нанесён
[LOG] 2026-09-19 20:30 — Frontend Dev: живая проверка на боевом стенде (бой 209, 761 против 762) — применены зелье, свиток, яд, повторный яд и противоядие; проверены все события и weapon_coating в состоянии участника; тестовые предметы, бой и состояние в Redis удалены
[LOG] 2026-09-19 20:50 — Frontend Dev: §3.9-bis — вместо одного баффа в админке список «Ускорение опыта» (до 8 строк, занятый тип недоступен в других строках, проценты в UI → доля в payload, минуты 1…10080); старый предмет с единственным баффом подставляется одной строкой, при сохранении старые колонки очищаются
[LOG] 2026-09-19 21:00 — Frontend Dev: все 8 видов опыта подписаны по-русски в одном общем месте — карточка предмета, подсказка ячейки и индикатор активных баффов берут подписи оттуда
[LOG] 2026-09-19 21:10 — Frontend Dev: живая проверка книг — предмет с тремя строками опыта сохранён и прочитан обратно, старые колонки очищены; все шесть серверных сообщений валидации совпали с моими клиентскими дословно; проверен и старый предмет без строк (подставляется одной строкой). Тестовые предметы удалены
[LOG] 2026-09-19 21:15 — Frontend Dev: повторные проверки — npx tsc --noEmit чисто, npm run build успешно; package-lock.json не менялся, контейнеры не оставлены
[LOG] 2026-09-19 21:40 — QA: начал задачи #10, #11, #12 — юнит-тесты buffs.py, бой с настоящим движком эффектов, тесты пяти сервисов
[LOG] 2026-09-19 21:55 — QA: задача #10 — первый в истории тестовый модуль для buffs.py: 117 тестов на нормализацию эффектов, источник, мгновенные значения, владение, тик DoT, контроли, сложные эффекты и снятие эффектов
[LOG] 2026-09-19 22:00 — QA: зафиксировано правило накопления — эффекты навыков независимы (кровоток 2х5 и 3х10 тикают отдельно), эффекты предмета обновляют свою запись (длительность = max, сила = новая), флаг fresh при обновлении НЕ выставляется заново, чужой предмет и навык с тем же именем не трогаются
[LOG] 2026-09-19 22:05 — QA: правило «полный контроль не снимается» проверено по всем селекторам (all, debuff, stun, control_partial, stat_down, periodic_damage, пустой) и для Stun, и для Poison:paralysis; отдельно проверено, что после очищения «всё» оглушение всё ещё пропускает ход
[LOG] 2026-09-19 22:20 — QA: задача #11 — новый модуль test_item_effects.py, 51 тест, движок эффектов НЕ мокается: buffs грузится приватным экземпляром прямо из файла (test_item_usage.py переписывает атрибуты модуля, из-за чего мокнутый evaluate_control сделал бы любое оглушение снимаемым)
[LOG] 2026-09-19 22:25 — QA: главный сторож от тихого отказа — зелье силы должно попасть в атрибуты атакующего ТОГО ЖЕ хода (шаг предмета идёт до атаки): тест падает, как только строки эффектов предмета перестанут доходить до движка
[LOG] 2026-09-19 22:30 — QA: яд на оружии проверен целиком — прибавка подмешивается в amount строки урона оружием (22 = 10 + 12) и не трогает строки без оружия, эффекты вешаются только на тех, кто реально получил урон, ход нанесения уже считается (4 хода → turns_left 3), на нуле пишется weapon_coating_expired
[LOG] 2026-09-19 22:35 — QA: второй яд при действующем первом — item_rejected с названием и остатком ходов, consume_item НЕ вызывается, слот остаётся с прежним количеством, при этом атака хода отыгрывается и урон проходит
[LOG] 2026-09-19 22:40 — QA: набор ключей события item_use сверен с тем, что читает журнал боя (BattlePageBar), включая выносливость в recovery и quantity_left; отдельно закреплено, что канал предмета за ход ровно один (поле item_id в SkillSelection)
[LOG] 2026-09-19 22:45 — QA: состояние боя «как до деплоя» (слот без quantity/effects/damage_entries/consumable_action, участник без weapon_coating, записи эффектов без owner_id/fresh/source) проходит полный ход без единого изменения поведения; отдельный тест сторожит, что фикстура действительно не содержит новых ключей
[LOG] 2026-09-19 22:50 — QA: весь pytest battle-service в Docker: 707 passed (было 539); проверено, что новые модули проходят и по одному, и в любом порядке с test_item_usage.py
[LOG] 2026-09-19 23:10 — QA: задача #12, inventory-service — 193 теста в пяти новых модулях: вложенный CRUD эффектов/урона с чтением обратно сырым SQL по настоящим именам колонок, все сообщения валидации §3.12 дословно, состав быстрых слотов, книги опыта, внутренние эндпоинты множителей и миграции 024/025 через настоящий Alembic Operations
[LOG] 2026-09-19 23:15 — QA: сложение общей и точечной книги проверено точно — 25 % за задания + 10 % на весь опыт персонажа = ×1.35; общая книга не трогает опыт профессии и сбора; предмет без строк item_xp_buffs работает по старым колонкам
[LOG] 2026-09-19 23:20 — QA: авторизация внутренних эндпоинтов — 401 без X-Internal-Token, 401 с чужим токеном, fail-closed 503 при пустом настроенном токене, 400 на пустой/неизвестный/слишком длинный список типов
[LOG] 2026-09-19 23:35 — QA: задача #12, места начисления опыта — 43 теста character-service (бои, титулы, боевой пропуск, валидация xp_source, fail-open), 26 locations-service (отыгрыш и задания, партийная надбавка считается от БАЗОВОГО опыта и не накручивается), 7 battle-pass-service (свой xp_source в теле запроса)
[LOG] 2026-09-19 23:40 — QA: в каждом из трёх сервисов есть тест, который падает, если вызывающий перестанет присылать источник опыта, и тест, который падает, если множитель перестанет доходить до записи в БД
[LOG] 2026-09-19 23:50 — QA: задача #12, автобой — 44 теста: свиток урона и зелье баффа обыгрывают пустой слот, яд стоит 0 при уже нанесённом яде, противоядие ценно только при наличии снимаемого эффекта (Stun и Poison:paralysis не считаются), старый пояс с одним лечением на низком HP выбирает тот же предмет, что и раньше
[LOG] 2026-09-19 23:55 — QA: обнаружен баг, добавлен в ISSUES.md (HIGH) — у GET /inventory/characters/{cid}/fast_slots вообще нет проверки доступа (inventory-service/app/main.py:1186-1193), хотя §3.3.3 утверждает обратное; после FEAT-168 в ответе ещё и вся боевая настройка предметов. Баг существовал до фичи; починка требует решения по вызову из battle-service (он ходит без токена). Задокументирован xfail-тестом, позеленеет сам после исправления
[LOG] 2026-09-19 23:58 — QA: обнаружен баг, добавлен в ISSUES.md (LOW) — автобой считает «нужду» в ресурсах наоборот (strategy.py:278-280): need_hp > 0 только при ВЫСОКОМ здоровье, поэтому лечение выбирается на полном HP, а не на низком. Баг был до FEAT-168 (задача #5 только вынесла пороги в константы); текущее поведение закреплено регрессионными тестами, чтобы правка была осознанной
[LOG] 2026-09-20 00:05 — QA: итог по прогонам в Docker (аргументы из ci.yml, CI=true, репозиторий примонтирован целиком) — battle 707 passed, inventory 1226 passed / 1 xfailed, character 1003 passed / 1 skipped, locations 1232 passed, battle-pass 119 passed, autobattle 122 passed. Всего добавлено 481 тест (+1 xfail на незакрытый баг доступа), продакшн-код не менялся. Задачи #10, #11, #12 завершены
[LOG] 2026-09-20 09:30 — QA: ревью #2 нашло две дыры в тестах, начал их закрывать; продакшн-код по опыту в это время переделывал разработчик, поэтому тесты писались по поведению, а не по внутренним функциям
[LOG] 2026-09-20 09:50 — QA: дыра 1 закрыта — 58 тестов на то, что чтение сохранённых строк никогда не падает. Заведомо неверные строки (тип опыта не из списка, value = 0, aoe_shape = 'circle', чужая цель, шанс 500, неизвестный тип урона) пишутся ПРЯМО В ТАБЛИЦУ сырым SQL, минуя API, и должны отдаваться как есть из GET /items/{id}, списка предметов, карточки предмета и быстрых слотов
[LOG] 2026-09-20 09:55 — QA: проверено мутацией — если вернуть наследование Out-схем от In-схем, падает 55 тестов из 58; парные тесты следят, чтобы вход при этом оставался строгим (те же строки по-прежнему получают 422 с русским сообщением)
[LOG] 2026-09-20 10:20 — QA: дыра 2 закрыта — 11 тестов на завершение квеста через НАСТОЯЩУЮ сессию (aiosqlite, настоящий crud, замокана только сеть). Каждый тест проверяет обе половины: опыт начислен И квест помечен выполненным
[LOG] 2026-09-20 10:25 — QA: проверено мутацией — при возврате прежнего поведения (освобождение соединения откатом внутри начисления опыта) падают ровно 6 тестов квеста без золота с MissingGreenlet, а квесты с золотом проходят: в точности та картина, из-за которой блокер проехал зелёным
[LOG] 2026-09-20 10:45 — QA: 16 тестов на пути опыта в character-service на настоящей сессии — награды за бой и боевой пропуск через реальный эндпоинт add_rewards (опыт, золото и ответ сверяются с БД), выдача титула (строка титула + пассивный опыт, активный не умножается), fail-open, неизвестный источник опыта, неизвестный персонаж — ничего не записывается
[LOG] 2026-09-20 10:55 — QA: обнаружен баг, добавлен в ISSUES.md (MEDIUM) — одновременная выдача одного титула даёт 500. Проверка «титул уже есть» это SELECT, за ним INSERT; второй запрос между ними ловит IntegrityError по первичному ключу, эндпоинт превращает его в «Внутренняя ошибка сервера» вместо идемпотентного «уже есть титул» (crud.py:2739-2790, main.py:1242-1245). Гонка воспроизведена детерминированно, тесты помечены xfail и позеленеют сами после починки
[LOG] 2026-09-20 11:10 — QA: прогоны после доработки (аргументы из ci.yml, CI=true, репозиторий примонтирован целиком) — inventory 1296 passed / 1 xfailed, locations 1245 passed, character 1028 passed / 1 skipped / 2 xfailed, battle 710 passed, battle-pass 119 passed, autobattle 126 passed. Продакшн-код не менялся, обе временные мутации откачены и сверены побайтово
[LOG] 2026-09-19 22:10 — Backend Dev: QA нашла баг (он был и до фичи) — нужда в ресурсах считалась наоборот: need_hp = max(0, hp_ratio − порог) больше нуля только при ПОЛНОМ здоровье и равен нулю при hp ≤ 70 %; автобой лечился на полном HP и не лечился на 20 %. Пользователь разрешил чинить внутри FEAT-168, добавлена строка #5a
[LOG] 2026-09-19 22:15 — Backend Dev: формула перевёрнута — need = max(0, порог − доля ресурса) для hp/маны/энергии; пороги (0.7 / 0.6 / 0.6) и веса боевых слагаемых не менялись, лечение на 20 % HP теперь заметно дороже баффа, на полном HP — ноль
[LOG] 2026-09-19 22:20 — Backend Dev: обновлены тесты QA, фиксировавшие ошибочное поведение (test_strategy_items.py): «на низком HP решает бонус за количество» → «побеждает большее лечение»; пример точного счёта переведён с ratio 0.9/1.0/1.0 на 0.5/0.2/0.2 (те же нужды 0.2/0.4/0.4 и та же сумма 16.03); «лечение выигрывает у баффа» перенесён с hp=1.0 на hp=0.2 и добавлен обратный случай — на полном HP лечение проигрывает баффу
[LOG] 2026-09-19 22:25 — Backend Dev: баг исправлен, запись удалена из ISSUES.md; проверки — py_compile чист, весь pytest autobattle-service в Docker: 124 passed
[LOG] 2026-09-20 00:20 — Reviewer: начал финальную проверку (задача #13), статус фичи переведён в REVIEW
[LOG] 2026-09-20 00:35 — Reviewer: автопроверки — py_compile по всем 25 файлам чисто, npx tsc --noEmit чисто, npm run build успешно, docker compose config ок
[LOG] 2026-09-20 00:55 — Reviewer: полный pytest в Docker (аргументы из ci.yml, CI=true, репозиторий примонтирован) — battle 707, inventory 1226 + 1 xfail, character 1003 + 1 skip, locations 1232, battle-pass 119, autobattle 124. Цифры сошлись с отчётом QA
[LOG] 2026-09-20 01:05 — Reviewer: миграции проверены на живой БД — 025 вниз, 024 вниз, обе вверх; таблицы и колонки исчезают и возвращаются, база оставлена на head
[LOG] 2026-09-20 01:10 — Reviewer: перенос старых книг проверен на подготовленных «как на проде» строках — нормальная книга переносится верно, книга без длительности пропускается (работает по старым колонкам), а книга с пустым типом и книга с нулевой прибавкой переносятся как есть — это и вылезло дальше как проблема №2
[LOG] 2026-09-20 01:30 — Reviewer: живой бой — зелье (эффект того же хода, обновление вместо накопления), свиток (обычная формула урона), яд (прибавка к урону, эффект на задетых, тик 6 HP/ход, истечение), второй яд отклонён без расхода предмета, противоядие сняло чужие эффекты и не тронуло своё, оглушение не снимается ничем
[LOG] 2026-09-20 01:40 — Reviewer: книги опыта вживую — множитель за задания 1.35 (25 % + 10 % общая), сбор 1.5, профессия 1.0 (общая книга её не трогает), без internal-токена 401; реальное начисление опыта сбора 100 → 150
[LOG] 2026-09-20 01:50 — Reviewer: автобой вживую берёт новые предметы (выбрал яд), после правки #5a на 20 % здоровья берёт лечение, на полном — яд; правки тестов — честная перебазировка, обе стороны зафиксированы
[LOG] 2026-09-20 02:05 — Reviewer: браузер на 1440 и 360 — список быстрых слотов с описаниями и остатком, блокировка второго яда с пояснением, форма предмета в админке со всеми разделами и списком «Ускорение опыта»; ошибок консоли и 5xx по фиче нет
[LOG] 2026-09-20 02:15 — Reviewer: НАЙДЕН БЛОКЕР — список форм области урона в inventory-service не совпадает ни с движком, ни с админкой: «Соседи», «Пробой» и «Случайные» сохранить нельзя (422), а line/cone/circle сохраняются, но движок их не знает и бьёт по одной цели
[LOG] 2026-09-20 02:20 — Reviewer: НАЙДЕНА КРУПНАЯ ПРОБЛЕМА — строка опыта, перенесённая миграцией 025 с нулевой прибавкой или с типом вне белого списка, роняет GET /inventory/items/{id} в 500 (схема ответа наследует проверки запроса). Локально не видно — старых книг в базе нет, на проде возможно
[LOG] 2026-09-20 02:25 — Reviewer: НАЙДЕН ТИХИЙ ОТКАЗ — яд с нулевой прибавкой к урону (допустимая настройка) наносится, пишется в журнал, тикает и истекает, но эффект не накладывается вообще; проверено вживую
[LOG] 2026-09-20 02:30 — Reviewer: тестовые данные убраны — предметы, инвентарь, пояса, баффы и навык сбора удалены, бои завершены, активный персонаж возвращён на 706; контейнеры не оставлены, коммитов нет
[LOG] 2026-09-20 02:35 — Reviewer: проверка завершена, результат FAIL — 1 блокер, 3 крупные, 10 мелких замечаний; раздел 5 заполнен
[LOG] 2026-09-19 22:10 — Frontend Dev: правки по ревью #1. Главное: при выборе «Нанесение на оружие (яд)» поля длительности и прибавки теперь реально записываются в состояние (1 и 0), а не только показываются — сохранение больше не отклоняется из-за поля, которое админ видит заполненным; при переключении обратно параметры яда очищаются
[LOG] 2026-09-19 22:20 — Frontend Dev: сообщения клиентских проверок боевой настройки приведены дословно к сообщениям inventory-service (шанс, длительность, сила эффекта, урон, затухание, число целей, длительность и прибавка яда, лимиты строк) — админ читает одну и ту же фразу независимо от того, кто поймал ошибку
[LOG] 2026-09-19 22:30 — Frontend Dev: индикатор активных баффов перестал ломать вёрстку на 360px — подписи стали длиннее из-за 8 видов опыта, поэтому плашка переносится по словам, таймер прижат вправо
[LOG] 2026-09-19 22:35 — Frontend Dev: старые колонки баффа очищаются только когда админ действительно оставил строки опыта — пустой список больше не стирает книгу у предмета, который форма не редактировала
[LOG] 2026-09-19 22:40 — Frontend Dev: формы АоЕ сверены — движок умеет single / splash / cleave / all / random_n, белый список inventory-service теперь тот же, редактор предлагает ровно их; правок не потребовалось
[LOG] 2026-09-19 22:45 — Frontend Dev: docs/services/frontend.md дополнен разделом про боевые эффекты расходников (общий модуль, журнал, быстрые слоты, админка, инвентарь)
[LOG] 2026-09-19 22:50 — Frontend Dev: проверки — npx tsc --noEmit чисто, npm run build успешно; вживую проверено, что предмет с новыми значениями по умолчанию (1 ход, 0 прибавки) сохраняется; тестовый предмет удалён
[LOG] 2026-09-20 09:10 — Backend Dev: правка по ревью #1 (замечание 3) — яд вешал свои эффекты только если у него была прибавка к урону; яд «весь в периодическом уроне» (coating_bonus_damage = 0) действовал вхолостую. Теперь строка считается отравленной по наличию яда и слоту оружия, а прибавка к урону осталась под своим условием
[LOG] 2026-09-20 09:15 — Backend Dev: добавлен тест TestWeaponCoatingOnHit — яд без прибавки к урону обязан вешать эффекты; проверено, что на старом коде тест падает, на исправленном проходит; заодно случаи «яд с прибавкой» и «яда нет»
[LOG] 2026-09-20 09:20 — Backend Dev: замечание 9 — шанс у строк урона предмета не бросается намеренно (так же, как у урона навыков в шаге атаки); записано в docs/services/battle-service.md и комментарием в коде, админка это поле и так не показывает
[LOG] 2026-09-20 09:25 — Backend Dev: замечание 14 — неверная посылка убрана: quantity есть и у слотов, снятых до FEAT-168, значит старые бои тоже получают всю стопку; дефолт остался защитой от мусорного значения, тест переименован и переписан на quantity = 0
[LOG] 2026-09-20 09:40 — Backend Dev: проверки после правок — py_compile чист, весь pytest battle-service в Docker (CI-аргументы, CI=true): 710 passed
[LOG] 2026-09-20 10:00 — Backend Dev: начал правки по ревью #1 в inventory-service — замечания 1 (блокер), 2, 5, 6
[LOG] 2026-09-20 10:10 — Backend Dev: замечание 1 исправлено — AOE_SHAPES приведён к тому, что реально умеет resolve_aoe_targets: single / splash / cleave / all / random_n. Фронтенд уже предлагал ровно эти пять, менять его не нужно; line / cone / circle теперь отклоняются, потому что движок их игнорирует и бьёт по одной цели
[LOG] 2026-09-20 10:20 — Backend Dev: добавлены тесты — все пять форм сохраняются, три несуществующие дают 422; фикстура _DAMAGE_A переведена с circle на splash
[LOG] 2026-09-20 10:35 — Backend Dev: замечание 2, первая половина — ItemXpBuffOut, ItemEffectOut и ItemDamageOut больше не наследуют схемы запроса. Валидация осталась только на записи: одна кривая строка в базе не должна превращать чтение в 500
[LOG] 2026-09-20 10:55 — Backend Dev: замечание 2, вторая половина — перенос старых книг в миграции 025 переписан с голого INSERT…SELECT на построчный: неизвестный/пустой тип и прибавка вне (0, 10] пропускаются, длительность вне 1..10080 обрезается, каждый случай пишется в лог с id предмета и причиной. Белый список в миграции инлайнен намеренно (правило из 023), тест сверяет его со schemas
[LOG] 2026-09-20 11:05 — Backend Dev: замечание 5 — присланный список xp_buffs теперь авторитетен даже пустым и всегда чистит устаревшую тройку. Чтобы не сломать старых клиентов, replace_item_xp_buffs вызывается только когда ключ реально прислан (в create_item тоже); QA-тест, закреплявший прежнее поведение, переписан, рядом добавлен тест на клиента без xp_buffs
[LOG] 2026-09-20 11:10 — Backend Dev: замечание 6 — в GET /inventory/items добавлен selectinload(xp_buffs), в комментарии зафиксировано правило «новая связь в schemas.Item — новая строка здесь»
[LOG] 2026-09-20 11:35 — Backend Dev: миграции проверены на dev-MySQL на подобранных «прод-подобных» строках: downgrade до 024, шесть легаси-книг (валидная, мусорный тип, пустой тип, нулевая прибавка, длительность 99999, длительность NULL), upgrade → перенесено 2, пропущено 3, обрезано 1, всё с предупреждениями в логе; затем down -1 → up ещё раз. Отдельно проверено, что GET /inventory/items/{id} отдаёт 200 на нарочно испорченных строках во всех трёх дочерних таблицах. Тестовые данные удалены, база оставлена на head, сервисы не останавливались
[LOG] 2026-09-20 11:45 — Backend Dev: проверки — py_compile чист, весь pytest inventory-service в Docker (CI-аргументы, CI=true): 1237 passed, 1 skipped, 1 xfailed. Обновлён docs/services/inventory-service.md
[LOG] 2026-09-19 23:10 — Backend Dev: правки по ревью #1 (замечания 8 и 9) — из оценки урона предмета убран множитель шанса: боевой сервис шанс у строк урона предмета не бросает, оценка теперь совпадает с реальностью; селектор stat_down вынесен в _is_stat_down и приведён к buffs._is_stat_down — сложные эффекты (ArmorBreak, Freeze, Electrify, Daze, Wet, Curse) раскрываются по модулю силы и считаются ухудшением при любом знаке, Holy — никогда. В коде и в docs/services/autobattle-service.md записано, что это зеркало, а источник истины — battle-service. Обновлены два теста на шанс (теперь фиксируют, что шанс игнорируется) и добавлены два случая на сложные эффекты; py_compile чист, весь pytest autobattle-service в Docker: 126 passed
[LOG] 2026-09-20 12:20 — Backend Dev: правка по ревью #1 (замечание 7) — ни один запрос множителя книги опыта больше не делается при открытой транзакции. Добавлен осторожный хелпер _release_db_connection: откат (и возврат соединения в пул) только если в сессии нет несохранённых изменений, чужую работу не теряем
[LOG] 2026-09-20 12:25 — Backend Dev: места вызова переставлены — add_rewards_to_character спрашивает множитель самой первой строкой, до любого обращения к БД; grant_title — после проверок и до первой записи; evaluate_titles разделён на «решить» и «записать», множитель запрашивается один раз на вызов, а не по разу на титул; _grant_title_xp теперь принимает готовый множитель
[LOG] 2026-09-20 12:30 — Backend Dev: тот же приём в locations-service (add_experience отпускает соединение перед запросом; у пути постов сессии БД нет вовсе) и в battle-pass-service, где HTTP-выдача наград висела в транзакции ещё до этой фичи — там reward заранее отцепляется от сессии, иначе протухшее поле в async-сессии упало бы с MissingGreenlet
[LOG] 2026-09-20 12:40 — Backend Dev: проверки — py_compile чист; весь pytest в Docker (CI-аргументы, CI=true): character 1003 passed / 1 skipped, locations 1232 passed, battle-pass 119 passed. Живая проверка: вокруг запроса множителя db.in_transaction() переходит True → False, начисление не изменилось (100 опыта с книгой 25 % = 125); тестовые данные в dev-базе восстановлены
[LOG] 2026-09-20 14:00 — Backend Dev: ревью #2 нашло блокер в моей же правке — освобождение соединения делалось откатом сессии, а откат протухает загруженные объекты; на квесте с опытом и без золота complete_quest падал с MissingGreenlet уже ПОСЛЕ записи опыта, квест оставался активным и его можно было сдавать за опыт повторно. Подход заменён целиком
[LOG] 2026-09-20 14:10 — Backend Dev: _release_db_connection удалён из всех трёх сервисов — чужую сессию не откатываем никогда. Множитель книги опыта теперь берётся на входе запроса (до загрузки объектов и до открытия транзакции) и передаётся параметром xp_multiplier в add_rewards_to_character, grant_title, evaluate_titles, add_experience
[LOG] 2026-09-20 14:15 — Backend Dev: grant_title снова целиком в одной транзакции — проверка «титул уже есть» и вставка больше не разделены сетевым вызовом, повторная выдача снова отвечает already_has, а не падает IntegrityError. evaluate_titles вернулся к исходному виду, множитель приходит от четырёх вызывающих обработчиков
[LOG] 2026-09-20 14:20 — Backend Dev: battle-pass откачен к прежнему виду, остался только xp_source; его давняя проблема (HTTP-выдача награды внутри открытой транзакции) записана в docs/ISSUES.md с пометкой «откатом сессии не чинить»
[LOG] 2026-09-20 14:25 — Backend Dev: NaN/inf больше не проходят проверку множителя (math.isfinite) — раньше int(xp * nan) падал вне try и опыт терялся; убраны мёртвый apply_character_xp_buff и мёртвые локальные переменные, поправлена устаревшая формула §3.8
[LOG] 2026-09-20 14:35 — Backend Dev: добавлены тесты на реальных путях — сдача квеста с наградой опытом и нулевым золотом на настоящей async-сессии (aiosqlite, expire_on_commit как в проде), гонка повторной выдачи титула, порядок «сначала множитель, потом БД» (проверяется db.in_transaction() в момент запроса) и NaN-случаи. Проверено, что тест на квест снова краснеет, если вернуть откат
[LOG] 2026-09-20 14:45 — Backend Dev: проверки — py_compile чист; весь pytest в Docker (CI-аргументы, CI=true): character 1028 passed / 1 skipped / 2 xfailed, locations 1245 passed, battle-pass 119 passed. Живая проверка на стенде: множители 1.25 и 1.5 приходят, начисление 100 → 125, неизвестный источник и NaN дают базовый опыт; данные dev-базы восстановлены
[LOG] 2026-09-20 15:20 — Backend Dev: починен баг от QA — при проигранной гонке выдачи титула вставка ловит IntegrityError, откатывается и отвечает «уже есть титул» вместо 500; опыт за титул при этом не начисляется вовсе, потому что flush падает раньше награды. Запись MEDIUM убрана из ISSUES.md
[LOG] 2026-09-20 15:30 — Backend Dev: тесты QA позеленели, маркеры xfail сняты. Симуляцию гонки пришлось поправить: конкурирующая строка вставлялась в хуке before_flush, то есть в нашу же транзакцию, и откат сносил её вместе с нашей — при одном соединении StaticPool «должна остаться ровно одна строка» так проверить нельзя. Теперь конкурирующая строка коммитится заранее (как это и делает выигравший запрос), а проверка «титул уже есть» ослепляется на один вызов — это ровно то состояние, которое видит проигравший. Проверено, что без исправления оба теста краснеют
[LOG] 2026-09-20 15:35 — Backend Dev: проверки — py_compile чист, весь pytest character-service в Docker (CI-аргументы, CI=true): 1030 passed, 1 skipped, xfail-ов не осталось
[LOG] 2026-09-20 16:30 — Backend Dev: ревью #3 — четыре замечания об одном: место запроса множителя. Запрос на входе обработчика оказался и блокирующим в async-коде, и лишним на горячих чтениях, и замыкал круг с инвентарём
[LOG] 2026-09-20 16:40 — Backend Dev: у помощника теперь два варианта — блокирующий (только для обработчиков-`def`, их FastAPI уводит в threadpool) и асинхронный на httpx.AsyncClient для `async def`. Общее ядро одно, поэтому белый список источников, fail-open и зажим NaN/бесконечности у них разъехаться не могут
[LOG] 2026-09-20 16:50 — Backend Dev: круг «надеть предмет → инвентарь зовёт нас → мы зовём инвентарь» разорван: внутренний роут evaluate-titles множитель больше не запрашивает вовсе. Осознанное следствие — титул, выданный этой подстраховкой, даёт базовый опыт; книга работает там, где титул выдают намеренно (админская выдача, повышение уровня)
[LOG] 2026-09-20 17:00 — Backend Dev: горячие чтения разгружены — в full_profile множитель спрашивается лениво, только в ветке реального повышения уровня, а GET /{id}/titles не спрашивает вовсе. Сдача квеста спрашивает только у квестов с опытом
[LOG] 2026-09-20 17:10 — Backend Dev: убраны запасные внутренние запросы в add_rewards_to_character и grant_title — None теперь везде значит «книги нет», и ни одна функция начисления в сеть не ходит
[LOG] 2026-09-20 17:25 — Backend Dev: новый тест-модуль test_xp_multiplier_call_shape.py фиксирует форму вызовов: асинхронность помощника, полное отсутствие HTTP при выдаче титула из инвентарного колбэка, отсутствие запросов на обоих путях чтения и запрет на запрос из функций начисления (проверка по AST). Убедился, что все три теста краснеют на старой форме
[LOG] 2026-09-20 17:35 — Backend Dev: проверки — py_compile чист; весь pytest в Docker (CI-аргументы, CI=true): character 1044 passed / 1 skipped, locations 1246 passed, inventory 1295 passed / 1 skipped / 1 xfailed, battle-pass 119 passed. Поправлены два теста админской смены уровня (теперь считают именно GET за passive_experience, а не все подряд) и тесты grant_title, опиравшиеся на убранный запасной запрос
[LOG] 2026-09-20 18:30 — Backend Dev: доработка по ревью #4 — книга опыта вернулась на автовыдачу титулов. evaluate_titles разделён на find_unlockable_titles (только чтение) и grant_unlocked_titles (только запись); между ними обработчик успевает спросить множитель
[LOG] 2026-09-20 18:40 — Backend Dev: все четыре автоматических пути титулов (колбэк инвентаря, список титулов, полный профиль, админская смена уровня) идут через один помощник _evaluate_titles_with_book: решение → множитель, только если титул реально открылся и у него есть пассивный опыт → запись. Надевание предмета, при котором ничего не открылось, в inventory-service не ходит вовсе
[LOG] 2026-09-20 18:45 — Backend Dev: записан осознанный размен — на ленивых ветках (сдача квеста, выдача титула) соединение БД удерживается на время запроса множителя. В комментариях прямо сказано: чинить это откатом сессии нельзя, только выносом начисления за транзакцию
[LOG] 2026-09-20 18:55 — Backend Dev: тесты-ловушки обновлены под новое, правильное поведение: «ничего не открылось → ноль обращений» осталось как было, а «титул открылся» теперь требует ровно один запрос множителя и применённую книгу; добавлены случаи «титул без пассивного опыта запроса не делает» и fail-open при недоступном inventory
[LOG] 2026-09-20 19:05 — Backend Dev: живые замеры на перезапущенных контейнерах (uvicorn --reload мог отдавать старый код) — выдача, при которой титул не открывается: 0 обращений к /xp-multiplier; выдача с открытием титула: ровно 1 обращение (buff_type=character_xp_title_bonus), опыт 33 → 233 при книге +100 % (100 × 2.0). Тестовый титул, строка выдачи, запись в журнале, опыт и бафф убраны
[LOG] 2026-09-20 19:10 — Backend Dev: проверки — py_compile чист; весь pytest в Docker (CI-аргументы, CI=true): character 1046 passed / 1 skipped, locations 1246 passed, inventory 1295 passed / 1 skipped / 1 xfailed
[LOG] 2026-09-20 20:10 — Backend Dev: правка по ревью #5 (замечание 36) — неудачный запрос множителя больше не выглядит как «книги нет». Добавлен lookup_character_xp_multiplier с результатом (множитель, ok, причина, миллисекунды); провал пишется уровнем error с id персонажа, источником опыта и затраченным временем. Поведение прежнее: опыт не теряется, множитель 1.0
[LOG] 2026-09-20 20:15 — Backend Dev: то же самое во втором сервисе — locations-service получил такой же lookup_character_xp_multiplier; старые get_character_xp_multiplier остались тонкими обёртками, возвращающими число, поэтому ни один вызывающий код не менялся
[LOG] 2026-09-20 20:25 — Backend Dev: новые тесты TestFailedLookupIsVisible в обоих сервисах проверяют уровень записи, наличие в ней id/источника/времени и флаг ok; отдельно убедился, что они краснеют, если вернуть тихую деградацию. Проверки — py_compile чист, весь pytest в Docker (CI-аргументы, CI=true): character 1054 passed / 1 skipped, locations 1250 passed
[LOG] 2026-09-20 03:00 — Reviewer: начал проверку №2 по исправлениям
[LOG] 2026-09-20 03:15 — Reviewer: автопроверки — py_compile чист, tsc чист, npm run build успешно; полный pytest в Docker: battle 710, inventory 1238 + 1 xfail, character 1003 + 1 skip, locations 1232, battle-pass 119, autobattle 126 — всё зелёное и больше, чем в прошлый раз
[LOG] 2026-09-20 03:25 — Reviewer: блокер с формами области урона закрыт — вживую single/splash/cleave/all/random_n сохраняются, line/cone/circle отбиваются 422; набор совпал с движком
[LOG] 2026-09-20 03:35 — Reviewer: чтение битых данных больше не падает — в три дочерние таблицы вручную вписаны заведомо негодные строки, карточка предмета и список отдают 200 и показывают их как есть
[LOG] 2026-09-20 03:40 — Reviewer: перенос старых книг перепроверен на пяти «как на проде» строках — 3 перенесены, 2 пропущены (неизвестный тип, нулевая прибавка) со старыми колонками нетронутыми, 2 длительности обрезаны; каждое решение записано в лог
[LOG] 2026-09-20 03:50 — Reviewer: тихий отказ с ядом закрыт — яд без прибавки к урону теперь вешает отравление на того, кого задело (урон при этом не меняется); проверено в живом бою
[LOG] 2026-09-20 03:55 — Reviewer: поле «ходов с ядом» теперь кладётся в состояние формы, а не только рисуется; в браузере значения читаются из настоящего состояния
[LOG] 2026-09-20 04:05 — Reviewer: книги опыта после переноса запроса множителя из транзакции считаются верно — множители 1.35 / 1.60 / 2.10 / 1.10, два реальных начисления дали 38 → 173 → 333, ровно по формуле
[LOG] 2026-09-20 04:15 — Reviewer: перебазировка тестов честная — тест на сложный эффект с положительной силой падает на старом правиле, тесты на шанс перевёрнуты, а не удалены, тест на яд без урона действительно ловит старую проверку, миграции проверяются настоящим Alembic
[LOG] 2026-09-20 04:30 — Reviewer: НАЙДЕН НОВЫЙ БЛОКЕР, внесён этой правкой — освобождение соединения в add_experience откатывает сессию и обесценивает уже загруженный объект квеста; следующее же обращение к его наградам падает MissingGreenlet. Воспроизведено с настоящей сессией внутри контейнера
[LOG] 2026-09-20 04:35 — Reviewer: условие блокера уточнено — бьёт только по квестам с опытом и БЕЗ золота (с золотом до этого идёт commit, и откат становится пустым). Опыт при этом уже начислен, а отметка о выполнении не ставится — квест остаётся активным и его можно сдавать повторно
[LOG] 2026-09-20 04:40 — Reviewer: сторож освобождения видит только изменения через ORM — открытую транзакцию с блокировками и сырые SQL-записи (а так пишет почти весь код) он не замечает и всё равно отвечает «безопасно»
[LOG] 2026-09-20 04:45 — Reviewer: пробел в тестах — ветка отката не проверяется нигде (у AsyncMock поле new истинно, сторож всегда возвращает False), и нет теста на чтение битой строки опыта; из-за этого блокер и проехал зелёным
[LOG] 2026-09-20 04:50 — Reviewer: тестовые данные убраны — предметы, квест, баффы, пояса; опыт и золото персонажа 761 возвращены к исходным, активный персонаж 706, контейнеры не оставлены, коммитов нет
[LOG] 2026-09-20 04:55 — Reviewer: проверка №2 завершена, результат FAIL — все замечания первого круга закрыты, но добавился блокер в выдаче наград за квест; раздел 5 дополнен
[LOG] 2026-09-20 05:30 — Reviewer: начал проверку №3
[LOG] 2026-09-20 05:40 — Reviewer: автопроверки — py_compile чист, tsc чист, сборка успешна, docker compose config ок; pytest в Docker: inventory 1296 + 1 xfail, locations 1245, character 1030 + 1 skip, battle 710, battle-pass 119, autobattle 126 — совпало с заявленным
[LOG] 2026-09-20 05:55 — Reviewer: блокер закрыт и проверен на настоящем эндпоинте — квест без золота отдаёт 200, опыт 38 → 53 (с книгой ×1.5), запись помечена completed, повторная сдача отбивается 404; квест с золотом тоже в порядке
[LOG] 2026-09-20 06:00 — Reviewer: подход выбран верный — сторож не залатали, а убрали; обе функции удалены из трёх сервисов, и тест падает, если они вернутся. Боевой пропуск честно откатан, а его давняя проблема вынесена в ISSUES с прямым предупреждением «не чинить откатом сессии»
[LOG] 2026-09-20 06:10 — Reviewer: гонка при выдаче титула проверена вживую — шесть одновременных выдач дали одну «Титул выдан», пять «уже имеет», ни одной 500-й, одна строка в базе и опыт ровно один раз
[LOG] 2026-09-20 06:20 — Reviewer: награды с книгой считаются верно — титул 20 × 2.0 (очки навыка книгой НЕ ускоряются, и это правильно), бой 100 × 1.25, квест 10 × 1.5
[LOG] 2026-09-20 06:35 — Reviewer: переписанный тест на гонку признан честным — исходный вариант вставлял конкурирующую строку в той же транзакции, и откат внутри исправления её бы снёс, то есть тест был бы красным на ПРАВИЛЬНОМ коде; новый проверяет и результат, и отсутствие лишнего опыта, и оба раза падает на подменённом коде
[LOG] 2026-09-20 06:45 — Reviewer: обе дыры в тестах закрыты по-настоящему — на возврате наследования схем ответа падает 55 тестов, на возврате отката — ровно 6 квестовых с MissingGreenlet; цифры сошлись с заявленными
[LOG] 2026-09-20 07:00 — Reviewer: НАЙДЕНА НОВАЯ ПРОБЛЕМА — запрос множителя делается блокирующим httpx внутри async-эндпоинтов; такой вызов на 5 секунд останавливает весь событийный цикл воркера, а не только свой запрос
[LOG] 2026-09-20 07:10 — Reviewer: НАЙДЕН КРУГОВОЙ ВЫЗОВ, проверено вживую — надевание предмета (с открытой транзакцией в inventory) дёргает character-service, а тот синхронно ходит обратно в inventory за множителем: на одно надевание пришлось 2 обращения назад. Это та же картина, что и в инциденте 2026-09-04, только сдвинутая на сервис
[LOG] 2026-09-20 07:20 — Reviewer: НАЙДЕНА НАГРУЗКА НА ЧТЕНИЕ — в full_profile и в списке титулов множитель запрашивается всегда, хотя нужен он там почти никогда; самый горячий эндпоинт игры теперь зависит от доступности inventory-service и при его тормозах ждёт до 5 секунд
[LOG] 2026-09-20 07:30 — Reviewer: тестовые данные убраны — квесты, титулы, книги и предмет для надевания удалены, опыт и золото персонажа 761 возвращены к исходным, активный персонаж 706; контейнеры не оставлены, коммитов нет
[LOG] 2026-09-20 07:35 — Reviewer: проверка №3 завершена, результат FAIL — всё из проверок №1 и №2 закрыто, но осталось четыре замечания одного класса про то, ГДЕ берётся множитель; раздел 5 дополнен
[LOG] 2026-09-20 08:10 — Reviewer: начал проверку №4
[LOG] 2026-09-20 08:20 — Reviewer: автопроверки — py_compile чист, tsc чист, сборка успешна, compose ок; pytest в Docker: character 1044 + 1 skip, locations 1246, inventory 1296 + 1 xfail, battle-pass 119, battle 710 — всё зелёное
[LOG] 2026-09-20 08:30 — Reviewer: разделение блокирующего и асинхронного вариантов проверено по каждому обработчику — где `async def`, там await асинхронного; где обычный `def`, там блокирующий (FastAPI уводит его в threadpool). Блокирующих вызовов из async-обработчиков не осталось
[LOG] 2026-09-20 08:40 — Reviewer: ВАЖНО по методике — первые замеры показали старые цифры, потому что в контейнерах крутился несвежий код (main.py правился в 17:09, последняя перезагрузка uvicorn — в 16:51). Перезапустил character/locations/inventory и перемерил; всё ниже — по текущему коду
[LOG] 2026-09-20 08:50 — Reviewer: круг разорван, проверено замером — надевание и снятие предмета теперь дают 0 обращений в inventory за множителем (в прошлый раз было 2), full_profile без повышения уровня — 0, список титулов — 0
[LOG] 2026-09-20 09:00 — Reviewer: запрос делается ровно там, где должен — админская смена уровня с полем level даёт обращения, без него ноль; квест без опыта множитель не спрашивает
[LOG] 2026-09-20 09:10 — Reviewer: книга работает там, где обещано — админская выдача титула 1000 → 1040 (20 × 2.0), квест с опытом 10 → 15, награда за бой 100 → 125; квест помечается выполненным
[LOG] 2026-09-20 09:20 — Reviewer: правки в существующем тесте признаны честными — счётчик GET-ов заменён на проверку конкретного вызова за passive_experience, потому что обработчик теперь делает ещё один GET через тот же мок; проверка стала точнее, а не слабее
[LOG] 2026-09-20 09:30 — Reviewer: замечание на будущее — оба «ленивых» запроса множителя идут уже при открытой транзакции (соединение держится на время сетевого вызова). Ветки редкие, это заметно лучше прошлого варианта, но компромисс стоит записать в комментарии, чтобы следующий не «починил» его откатом сессии
[LOG] 2026-09-20 09:40 — Reviewer: вопрос к PM — для инженеров правило «титул от автовыдачи даёт базовый опыт» расписано отлично, а для игрока нигде: бафф по-прежнему подписан «к опыту персонажа за титулы» без оговорок, и игрок не отличит случай, когда книга не сработала
[LOG] 2026-09-20 09:45 — Reviewer: тестовые данные убраны, персонаж 761 возвращён к исходным опыту, уровню, очкам и золоту; перезапущенные сервисы работают, контейнеры не оставлены, коммитов нет
[LOG] 2026-09-20 09:50 — Reviewer: проверка №4 завершена, результат PASS — замечания 25–28 и оба мелких закрыты и подтверждены замерами; осталось два необязательных пункта (запись компромисса и вопрос про подпись баффа)
[LOG] 2026-09-20 10:20 — Reviewer: начал короткую проверку №5; контейнеры перезапущены до замеров, в них точно текущий код
[LOG] 2026-09-20 10:30 — Reviewer: pytest в Docker — character 1046 + 1 skip, locations 1246, inventory 1296 + 1 xfail, battle-pass 119; всё зелёное, цифры совпали
[LOG] 2026-09-20 10:35 — Reviewer: пункт #33 закрыт — размен расписан в обоих местах, и прямо сказано, что чинить это откатом сессии нельзя, со ссылкой на запись про battle-pass
[LOG] 2026-09-20 10:45 — Reviewer: разделение «решить → спросить книгу только если титул открылся и даёт пассивный опыт → записать» сделано правильно и работает: титул без пассивной награды открывается за 0 обращений, а через GET /titles титул с опытом даёт ровно 1 обращение и книга применяется (3000 → 3200, то есть 100 × 2)
[LOG] 2026-09-20 10:55 — Reviewer: НАЙДЕН БЛОКЕР — но на пути «надеть/снять предмет» тот же титул даёт базовый опыт (1000 → 1100 вместо 1200) и запрос висит 5.4 секунды: запрос множителя уходит в таймаут
[LOG] 2026-09-20 11:00 — Reviewer: причина — круг из ревью #3 никуда не делся, его только сделали редким. inventory крутится в один воркер, а equip/unequip объявлены async и делают БЛОКИРУЮЩИЙ httpx.post в character-service; событийный цикл инвентаря встаёт, и обратный запрос за множителем обслужить некому — отсюда таймаут и тихий откат к базовому опыту
[LOG] 2026-09-20 11:05 — Reviewer: замер разработчика воспроизводится, но только на пути БЕЗ инвентаря в цепочке; тесты-сторожа этого тоже не видят — они мокают HTTP-границу, поэтому проверяют форму вызова верно, а межсервисную взаимоблокировку увидеть не могут
[LOG] 2026-09-20 11:10 — Reviewer: предложение — чинить корень: сделать вызов evaluate-titles из инвентаря неблокирующим (AsyncClient + await либо после ответа/фоном), тогда книга заработает на всех путях и уйдёт задержка в 5 с; если это вне объёма — вернуть поведение круга №4 (на внутреннем роуте множитель не спрашивать) и оставить #34 открытым
[LOG] 2026-09-20 11:15 — Reviewer: остальное из проверки №4 не сломалось — пустые надевания дают 0 обращений, профиль и список титулов без выдачи тоже 0, титул без пассивной награды 0, очки навыка книгой по-прежнему не ускоряются
[LOG] 2026-09-20 11:20 — Reviewer: тестовые данные убраны, персонаж 761 возвращён к исходному состоянию, контейнеры не оставлены, коммитов нет
[LOG] 2026-09-20 11:25 — Reviewer: проверка №5 завершена, результат FAIL — #33 закрыт, #34 сделан правильно по форме, но на пути надевания предмета книга теряется и запрос висит 5 секунд; состояние после круга №4 было лучше
[LOG] 2026-09-20 12:00 — Backend Dev: начал замечание #35 — блокирующий HTTP на event loop в inventory-service
[LOG] 2026-09-20 12:10 — Backend Dev: причина шире, чем один вызов. equip_item (async) звал блокирующим httpx ТРИ раза: evaluate-titles напрямую плюс _track_cumulative_stats и _reconcile_perks — оба обычные def с httpx.post внутри. unequip_item — два, _revalidate_equipment — один. То есть один воркер uvicorn мог стоять до 15 с на одном надевании
[LOG] 2026-09-20 12:25 — Backend Dev: у каждого «выстрелил и забыл» вызова теперь два варианта — синхронный для def-обработчиков (threadpool) и _async для async def; построение запроса общее, чтобы варианты не разъехались. equip_item, unequip_item и _revalidate_equipment переведены на await
[LOG] 2026-09-20 12:30 — Backend Dev: остальные блокирующие httpx в main.py проверены и оставлены как есть — _add_item_to_inventory_core, eat_food и синхронные варианты хелперов вызываются только из синхронных обработчиков, у них своя нить. Зависимость get_current_user_via_http тоже синхронная, тоже threadpool
[LOG] 2026-09-20 12:40 — Backend Dev: добавлены статические тесты TestNoBlockingHttpOnTheEventLoop — разбор main.py в AST: ни одного блокирующего клиентского вызова и ни одного синхронного хелпера внутри async def. Юнит-тесты мокают HTTP и саму взаимоблокировку увидеть не могут (ревьюер это отметил), поэтому проверяется форма кода. Плюс тест, что evaluate-titles ходит через AsyncClient и несёт internal-токен
[LOG] 2026-09-20 13:05 — Backend Dev: живая проверка после перезапуска контейнеров, персонаж 763, титул с наградой 1000 пассивного опыта и книга ×2: надевание, открывающее титул — 432 мс (было 5429), ровно один запрос множителя (200 OK), опыт 0 → 2000; надевание, ничего не открывающее — 329 мс и ноль обращений; снятие — 216 мс. Тестовые данные удалены, персонаж возвращён в исходное состояние
[LOG] 2026-09-20 13:10 — Backend Dev: первые два замера показывали ~5.4 с и на сценарии «ничего не открывается» — это грузил общий dev-стенд параллельно работающий агент (в том же окне лога сотни 401 на xp-multiplier по чужим персонажам), а не этот код; после повтора на спокойном стенде цифры выше
[LOG] 2026-09-20 13:20 — Backend Dev: проверки — py_compile чист, весь pytest inventory-service в Docker (CI-аргументы, CI=true): 1299 passed, 1 skipped, 1 xfailed. Обновлён docs/services/inventory-service.md — правило «никаких блокирующих HTTP в async def» с таблицей вариантов вызовов
[LOG] 2026-09-20 12:00 — Reviewer: начал закрывающую проверку №6; стенд предварительно проверен на тишину (посторонних запросов нет), контейнеры перезапущены
[LOG] 2026-09-20 12:10 — Reviewer: pytest в Docker — character 1054 + 1 skip, locations 1250, inventory 1300 + 1 xfail, battle-pass 119, battle 710, autobattle 126; tsc, сборка, py_compile и compose тоже чисты
[LOG] 2026-09-20 12:20 — Reviewer: блокирующие вызовы проверил своим разбором кода, а не только их тестом — внутри async-обработчиков inventory-service их нет ни напрямую, ни через синхронные помощники; сами помощники остались для обычных `def`, и это правильно
[LOG] 2026-09-20 12:25 — Reviewer: новый сторож честный — он разбирает настоящий main.py, ищет для каждого вызова ближайшую обрамляющую функцию и падает, если она async; отдельно ловит непрямой случай через синхронные помощники
[LOG] 2026-09-20 12:35 — Reviewer: БЛОКЕР ЗАКРЫТ — надевание предмета, открывающее титул с пассивным опытом: 318 мс (было 5429), ровно один успешный запрос множителя, опыт 0 → 2000 (книга ×2). Пустое надевание 214–235 мс и 0 запросов, снятие 240–287 мс
[LOG] 2026-09-20 12:40 — Reviewer: пункт #36 закрыт — провал запроса пишется уровнем error с персонажем, источником и временем, и прямо сказано, что бонус книги потерян; поведение fail-open не изменилось
[LOG] 2026-09-20 12:50 — Reviewer: про «грязные замеры» — шторм действительно был (218 ответов 401 по персонажам 1 и 99999, не моим), но находку из проверки №5 он не объясняет: в том же окне то же надевание отвечало за 241 мс, когда титул не открывался, и висело 5429 мс только когда открывался, а через GET /titles такой же титул выдавался за 80 мс. Медленным был не момент времени, а условие
[LOG] 2026-09-20 13:00 — Reviewer: регрессии нет — квест с опытом 100 → 150 и отметка «выполнен», квест без опыта без запроса множителя, админская выдача титула 50 × 2, награда за бой 100 × 1.25, горячие чтения по 0 запросов
[LOG] 2026-09-20 13:10 — Reviewer: боевые расходники перепроверены в живом бою — зелье вешает эффект, свиток считается обычной формулой (18 + 40 = 58), яд наносится на оружие, второй яд отклоняется, противоядие расходуется
[LOG] 2026-09-20 13:15 — Reviewer: наблюдение без последствий — первый запрос к только что перезапущенному сервису идёт ~5.4 с (видел на надевании и на квесте, повторные — 214–278 мс). Это разогрев, а не таймаут фичи, но выглядит он ровно как симптом блокера, поэтому все цифры выше снимались минимум дважды
[LOG] 2026-09-20 13:20 — Reviewer: по perk_evaluator согласен с разработчиком — блокирующих вызовов внутри async в character-attributes-service нет, правка вне объёма фичи; но запись в ISSUES заслуживает: он тянет весь full_profile ради одного поля, а full_profile теперь может сам дёрнуть выдачу титулов и инвентарь
[LOG] 2026-09-20 13:25 — Reviewer: тестовые данные убраны, персонаж 761 возвращён к исходному состоянию, контейнеры не оставлены, коммитов нет
[LOG] 2026-09-20 13:30 — Reviewer: проверка №6 завершена, результат PASS — фича закрыта
[LOG] 2026-09-19 23:50 — PM: ревью #6 PASS, фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- **Зелья в бою:** временные эффекты на несколько ходов через тот же движок, что и навыки (криты, сопротивления, уклонение). Повторное применение того же зелья обновляет длительность, не складывая бонус.
- **Свитки:** разовый урон по обычной боевой формуле, лечение и щиты. Шанс у строк урона не разыгрывается — попадание решают уклонение и сопротивления.
- **Яды:** наносятся на оружие, параметры настраиваются у предмета (прибавка к урону, длительность). Пока действует яд, новый нанести нельзя — предмет не тратится. Ядовитый эффект работает и без прибавки к урону.
- **Противоядия:** что снимать, настраивается у предмета; полный контроль с пропуском хода не снимается никогда.
- **Один предмет за ход**, применение бесплатно. Стопка расходуется по одной штуке (раньше тратилась целиком).
- **Эффекты навыков** накладываются независимо друг от друга (кровоток 2 хода по 5 и 3 хода по 10 тикают отдельно).
- **Книги опыта:** 8 видов (персонаж целиком, бои, посты, задания, титулы, боевой пропуск, профессия, сбор), комбинируются в одном предмете, общая складывается с частной.
- **Автобой** понимает новые предметы; попутно исправлено перепутанное условие лечения (бот пил зелье при полном здоровье и не пил при низком).
- **Админка:** редакторы эффектов, урона, яда, очищения и списка книг опыта; в инвентаре и в журнале боя всё подписано по-русски.
- Миграции 024 и 025 с откатом; 025 аккуратно переносит старые книги, пропуская битые записи.

### Что изменилось от первоначального плана
- Правило «обновлять, а не складывать» по решению пользователя оставлено только для предметов; навыки накладываются независимо.
- Книги опыта из трёх видов выросли до восьми с гибкой настройкой.
- Свиток телепорта вынесен в отдельную будущую задачу.

### Найдено и исправлено по ходу (всё предсуществующее)
- Надевание вещи блокировало весь сервис инвентаря: три блокирующих вызова в асинхронном обработчике, в худшем случае до 15 секунд. Теперь 0,3 секунды. Добавлен тест, который падает, если такой вызов вернут.
- Задание можно было сдать повторно и фармить опыт (появилось в ходе работы и было поймано ревью).
- Одновременная выдача одного титула давала ошибку 500 вместо «титул уже есть».
- Открытие предмета падало на нестандартных старых данных.
- Запросы множителя опыта убраны из транзакций и с горячих страниц; неудачный запрос теперь пишется в лог как ошибка, а не молча даёт базовый опыт.

### Оставшиеся риски / follow-up задачи
- Открытые эндпоинты: быстрые слоты пояса, начисление наград, отрядный бонус и 8 внутренних маршрутов — отдельной задачей (в ISSUES.md).
- MEDIUM: оценка перков тянет весь профиль ради одного поля.
- Первый запрос после деплоя занимает около 5 секунд (прогрев) и внешне похож на зависание — не пугаться.
- Игровые данные (зелья, свитки, яды, книги) админ заводит сам: код готов, предметов пока нет.
