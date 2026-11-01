# FEAT-190: Пассивки подклассов — волна 2 (новые боевые механики)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-11-01 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-190-slug.md` → `DONE-FEAT-190-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Последняя волна пассивок подклассов. Фундамент — FEAT-188 (`features/DONE-FEAT-188-*.md`),
волна 1 — FEAT-189 (`features/DONE-FEAT-189-*.md`): 14 из 21 пассивок работают, вся логика —
хуки в `battle-service/app/passives.py`. Здесь — пассивки, которым нужны **новые механики боя**
(щит, вампиризм, отражение, оплата навыка здоровьем, бафы союзникам, удар по своим).
Источник истины по названиям и цифрам — `docs/SUBCLASS-PASSIVES.md`.

**Новые механики движка**
- **Щит** — поглощает урон до того, как он снимет HP.
- **Вампиризм** — лечение от нанесённого урона.
- **Отражение** — часть полученного урона возвращается атакующему.
- **Оплата навыка здоровьем** — нехватку маны можно доплатить HP.
- **Баф союзника от пассивки** — пассивка накладывает эффект на союзника.
- **Удар по своим** — единственное исключение: «Обман» Фокусника.

**Пассивки (7 + доделка двух)**
- **Паладин — Священный обет.** Один раз за бой при падении HP ниже 30%: щит на 20% макс. HP +
  снятие одного снимаемого негативного эффекта (оглушение/паралич не снимаются ничем).
- **Хранитель — Возмездие.** 15% полученного урона (после сопротивлений) возвращается
  атакующему. Отражённый урон не критует, от него не уклониться, он сам не отражается.
- **Бард — Ритм.** Каждый свой ход — стак «Вдохновения» себе и союзникам: +3% урона, максимум 4
  (+12%). Бард пал — стаки исчезают. Если союзников нет — только себе: +5%, максимум 3 (+15%).
- **Некромант — Плата кровью.** Нехватку маны на навык доплачивает здоровьем: 1 маны = 1.5 HP.
  Убить себя нельзя — если HP не хватает, ход срывается, как при нехватке маны. За убийство в
  бою — +10% макс. HP.
- **Эфириад — Шёпот духов («умные духи»).** Каждый свой ход духи выбирают по приоритету:
  (1) союзник ниже 50% HP (самый побитый) → +8% сопротивлений; (2) иначе враг без дебафа духов
  (тот, по кому бил Эфириад) → −8% сопротивлений; (3) иначе союзник → +8% урона. Эффект 2 хода.
  Если союзников нет, «союзник» = сам Эфириад.
- **Ауромант — Прилив.** Лечение сверх максимума HP становится щитом, до 20% макс. HP цели, на
  3 хода. Без союзников — от собственного лечения.
- **Жрец — Вера.** 10% нанесённого урона лечит Жреца, святым уроном — 15%.
- **Берсерк — доделка «Ярости».** Ниже 25% HP — вампиризм 15% от нанесённого урона.
- **Фокусник — доделка «Обмана».** В групповом бою «обманутая» атака уходит в случайного
  союзника атакующего с 50% урона (если такого нет — атака просто не проходит, как сейчас).

### Бизнес-правила
- Цифры — константы в `passives.py`, описания — в реестре skills-service; после включения —
  `implemented=True` для всех 21 (Берсерк и Фокусник — обновить описания).
- Режимы «есть союзники / нет союзников» определяются в момент срабатывания (как в FEAT-189).
- Длительность оглушения/паралича пассивки не увеличивают.
- Участники без пассивок — поведение в точности прежнее.
- Решения PM по неоднозначностям (можно пересмотреть):
  - Щиты от разных источников складываются; каждый живёт своё время (Паладина — до конца боя
    или пока не пробит; Ауроманта — 3 хода). Щит не лечится и не превышает свой предел.
  - Паладин снимает самый свежий снимаемый негативный эффект.
  - Вампиризм и «Вера» лечат только до максимума HP; лечение от урона по щиту не считается
    (только урон, реально снятый с HP цели). Отражённый урон вампиризм не даёт.
  - Отражение Хранителя считается от урона после сопротивлений, включая урон, поглощённый щитом
    Хранителя. Отражение — обычный урон: может убить атакующего.
  - Удар по своим от «Обмана» не триггерит пассивки атакующего (как доп. удары в FEAT-189).
  - (по итогам анализа) Щиты поглощают ЛЮБОЙ урон, включая периодический (кровотечение, ожог,
    яд) и урон от эффектов. Вампиризм, «Вера» и отражение — только от прямых ударов (навык,
    свиток/предмет, осколок/перескок), не от периодического урона.
  - Вампиризм и отражение работают и на доп. удары (осколок Механика, перескок Искромага).
  - Щит Ауроманта убывает в ходы Ауроманта (как все эффекты, которые он накладывает).
  - Некромант «+10% макс. HP за убийство» = **лечение** на 10% от максимального HP (не выше
    максимума), максимальное HP не растёт.
  - «Прилив» Ауроманта считает любое его лечение: навыки, лечение по времени, предметы/зелья.
  - Перенаправленный «Обманом» удар по союзнику атакующего: без броска уклонения и без любых
    пассивок (ни атакующего, ни цели — в т.ч. без отражения Хранителя); щит цели поглощает.
  - Атакующий, убитый отражением посреди AoE-атаки, дальше не бьёт.
  - Эфириад выбирает действие в конце своего действия (когда уже известно, по кому он бил).
  - Некромант: карточка навыка не блокируется, если маны + HP/1.5 хватает (с запасом в 1 HP);
    окончательная проверка — при оплате, ошибка по-русски. Автобой Некроманта здоровьем не платит.
  - «Ярость» по-прежнему считается один раз на атаку (по HP в её начале).
  - Лечение/баф, которые наносит пассивка, показываются в логе.

### UX / Пользовательский сценарий
1. Пометка «пока не действует в бою» пропадает у всех пассивок.
2. В бою видны щиты (значение щита у участника) и срабатывания в логе: «Священный обет»,
   «Возмездие −N», «Вера +N HP», «Плата кровью −N HP», «Вдохновение ×N», «Шёпот духов» и т.д.

### Edge Cases
- Два Хранителя бьют друг друга — отражение не отражается.
- Хранитель отражает урон атакующему со щитом — щит атакующего поглощает отражение.
- Некромант с 1 HP и без маны — ход срывается с понятной русской ошибкой.
- Паладин получает смертельный удар с 40% HP сразу до 0 — обет не срабатывает: он срабатывает,
  только если после удара HP > 0 и < 30%.
- Старые бои без новых полей не падают.

### Вопросы к пользователю
- [x] Делать оставшиеся пассивки → да («делай дальше всё»).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Scope: **battle-service** (`passives.py`, `main.py`, optionally `buffs.py` kwargs), **skills-service**
(`app/subclasses.py` registry: `implemented=True` for the 7 + description updates for Berserk/Trickster),
**frontend** (log lines, shield display, Necromancer affordability, runtime max HP), **autobattle-service**
(optional). No DB / Alembic / nginx / compose / permissions. Line numbers = current uncommitted tree.

### 2.1 HP model and every place HP goes down

State: `battle_state["participants"][str(pid)]` has `hp` (float, may go **negative** — `_strike` does not clamp),
`max_hp` (+ `mana/max_mana`, …), seeded by `_participant_payload` (`main.py:412-449`) → `redis_state.init_battle_state`
(`redis_state.py:169`, keys ~214-232). Runtime payloads sent to clients copy `hp`/`max_hp` explicitly — internal
state `main.py:~1729`, `GET /{id}/state` `~1838`, spectate `~1932`, WS `~6001`, admin `~5069`, preview `~2059`
(a new `shield` field must be added to each, `.get` default 0).

HP loss sites (exhaustive):
| # | Source | Where | Notes |
|---|--------|-------|-------|
| A | Skill strike, scroll (item damage rows), Mechanic/Sparkmage extra hits | `_strike` **`main.py:3050`** `target_state["hp"] -= dealt` | Single choke point for all *direct* damage. Unclamped. `total_damage_dealt/received` updated right after (3052-3056). Attacker = `actor_pid` (event `source`). |
| B | Enemy-side instant resource rows (`StatModifier hp`, effect damage) | `buffs.apply_new_effects` → `_change_resource` (`buffs.py:150-155`, 208-212, clamp 0..max) | Called via `_land_enemy_effects` (`main.py:2909`). |
| C | DoT bleed/burn/periodic poison | `buffs.tick_periodic_effects` `buffs.py:296-301` (clamp at 0) | Called at step 9.4a `main.py:3932`; ticks only effects **owned by the actor**. |
| D | HP-over-time negative doses | `buffs._tick_resource` `buffs.py:314-335` | same call. |
| E | Timeout drop-out | `main.py:6246` `pdata["hp"] = 0` | not damage — shields/vow must ignore. |

**Shield placement.** No shield/absorb concept exists anywhere (grep `shield` → only frontend `WordTone "absorb"` in
`FighterCard.tsx:31`, a word-pop tone). The single place for direct damage is `_strike` between the
`dealt` computation and line 3050. B/C/D live in `buffs.py`, which ~30 suites `MagicMock` (FEAT-189 D1). Options:
(1) shields absorb only A + reflected damage (simplest; DoT bypasses shield — needs PM/Architect OK);
(2) add an optional `absorb_fn=None` kwarg to `apply_new_effects` / `tick_periodic_effects` / `_tick_resource`
(default → byte-identical) with the absorb logic itself in `passives.py`; mocks accept extra kwargs, real-buffs
harness (`REAL_BUFFS` in `test_subclass_passives.py`) can test it. Post-hoc refund in main.py is **not** viable:
DoT clamps HP at 0, so the "lost" amount is wrong when shield > remaining HP. Recommend (2) if DoT must hit shields.

Shield storage: recommend `passive_state["shields"] = [{"key", "amount", "cap", "turns_left"|None, "owner"}]`
(old states → absent → 0), absorb oldest/shortest first, `passives.shield_total(p)` for payloads/logs. Alternative —
a real `active_effects` row (would show as an effect circle and tick by owner automatically) is risky: cleanse
selector `all` would strip it, `aggregate_modifiers` would sum a junk `shield` key, and absorb mutates magnitude.
Expiry of Auromancer's 3 turns: decide whose turns (owner = Auromancer, like effects — `decrement_durations` at
`main.py:~3947`; or the shielded target's). A `passives.tick_shields(state, actor_pid)` next to 9.4 mirrors effects.

### 2.2 Healing today (Auromancer overheal, lifesteal cap)

| Heal source | Where | Overheal observable? |
|---|---|---|
| Skill rows `hp` positive, sides self/ally/all_allies (support `main.py:3144-3190`, defense `3212-3260`, attack 9.0/9.0c/9.0d `3628-3680`), item non-enemy rows (`main.py:3437`) | `apply_new_effects` → `_change_resource` clamps to `max_hp`, returns real change but `apply_new_effects` returns `None` | Only by main.py pre/post compare: `overheal = Σ positive hp magnitudes of rows − (hp_after − hp_before)` per target. Rows with duration>1 land the first dose now. |
| Item `health_recovery` | `main.py:3338-3342` `min(old+delta, mx)` | Yes, explicit (`old+delta-mx`). |
| HoT doses | `buffs._tick_resource` (positive `change`), event `resource_tick` with **real** amount only | Needs intended magnitude: pre-scan actor-owned non-fresh `hp>0` rows per target before 9.4a, compare with summed `resource_tick` amounts per target (pure, in passives) — or the `absorb_fn`-style kwarg returning overflow. |

No generic heal helper exists; lifesteal/«Вера» heals should be a passives helper `heal(p, amount) -> applied`
(clamp to `max_hp`, never heal `hp <= 0`). Cap at max HP everywhere (PM decision: lifesteal overflow is NOT
Auromancer shield — tide only for heals **cast by the Auromancer**). Open: do potions (`health_recovery`) /
item heal rows used by the Auromancer count? Do HoT doses count?

### 2.3 Durations, ally effects, passive-sourced buffs (Etheriad, Bard)

- Effects live in `battle_state["active_effects"][str(pid)]` (list of normalized rows with `owner_id`, `fresh`,
  optional `source`). Duration ticks **only at the end of the owner's turn** (`buffs.decrement_durations`
  `buffs.py:337`, step 9.4 `main.py:~3947`); fresh rows skip their first tick. ⚠ Rows owned by a **dead**
  participant never tick again (no turns) → they live forever → Bard's stacks/Etheriad's effects must be removed
  explicitly on death.
- Ally targeting: `ally_target_pid` (`main.py:~2838`, `request.ally_target_id`, fallback self), `alive_allies`
  incl. self (`~2846`). Ally rows → `apply_new_effects(state, pid, rows, owner_pid=actor)` directly (no roll).
- **Reuse for passives**: build rows `{"effect_name": "Вдохновение", "attribute_key": "percent_damage",
  "magnitude": n, "duration": d}` (StatModifier path in `_normalize_effect` `buffs.py:21-55` → attribute
  `percent_damage` → `aggregate_modifiers` → `build_percent_damage_buffs()["all"]`, i.e. picked up by both attack
  `~3693` and item `~3471` paths with zero new hooks). Resists: `attribute_key` `percent_resist_all` (negative
  magnitude for Etheriad's enemy debuff). Pass `source=("passive", key)` → `_effect_identity` (`buffs.py:84`)
  makes re-application **refresh in place** (duration = max, magnitude = new) — exactly Bard's growing stack
  (set magnitude = stacks × pct) and Etheriad's non-stacking 2-turn effect. The call must live in **main.py**
  (passives must not import buffs): passives returns `[(target_pid, rows)]`, main.py applies + logs `apply_effects`
  with `passives` contribution. Displayed automatically as effect circles (2D/3D).
- Stack count storage: Bard `passive_state["bard_stacks"]` (+ mode); removal on Bard death: a pure
  `passives.on_deaths(state, pids)` filtering `active_effects` rows with `source == "passive:bard_rhythm"` and
  `owner_id == bard` — call at step 9.5 (`main.py:3966-3976`, newly defeated) **and** the drop-out path
  (`main.py:6246`).
- Etheriad «по кому бил»: record hit targets in `record_strike`/`finish_attack` (e.g. `passive_state["spirit_hits"]`),
  "enemy without spirit debuff" = no `active_effects` row with `source == "passive:etheriad_spirit_whisper"`.
  "Most beaten ally <50%" from `participants_map` (`hp/max_hp`). Hook timing to decide: H1 (`main.py:2777`,
  turn start; stunned turns?) vs end of action before 9.4a (includes this turn's hits). Mode (allies/no allies)
  via `_alive_sides` (`passives.py:300`).
- ⚠ Cleanse selector `debuff` = `owner_id != list_pid` (`buffs.py:582`) → an ally-cast buff (Bard/Etheriad, and
  already today ally skill buffs) counts as a "debuff" for antidotes. Pre-existing semantics.

### 2.4 Cleanse for Paladin

`buffs.remove_effects(state, pid, selector, limit)` (`buffs.py:597`), used by item cleanse rows (`main.py:3408`).
Unremovable = `is_unremovable` (Stun, Poison+paralysis via `evaluate_control`, `buffs.py:550`). It removes the
**oldest** matches; list order = application order, so "most recent" = last matching element. Since passives may not
import buffs, Paladin needs its own pure pick: last row in `active_effects[pid]` that is negative (recommend
team-based: `owner` on an enemy team, or `passives.control_kind == "soft"` / periodic / negative magnitude) and not
hard control (`passives.control_kind(row) == "hard"`, `passives.py:343`). Log as `effects_removed`-like event or
`passive_proc` with `removed`.

Vow trigger: after every HP loss of a Paladin (`_strike`, reflect, DoT if shields cover DoT): `0 < hp < 30% max_hp`
and `not passive_state["vow_used"]` → shield 20% `max_hp` + cleanse one. Must be checked **per hit** (so the shield
protects against the remaining entries / extra hit of the same action), not once at 9.5.

### 2.5 Mana / Necromancer HP payment

- `_pay_skill_costs` `main.py:625-662`: sums ranks (mana via H12 `passives.mana_cost`), checks
  `pstate[res] < value` → `HTTPException(400, "Недостаточно маны: нужно X, есть Y")` (`main.py:646-650`),
  then deducts. Called **after resolution** at `main.py:3898` (after attack 9.x and durability 9.1, before 9.4a
  DoT/9.5). An exception there aborts the request: `save_state` (`main.py:~4062`) never runs, so the Redis state is
  untouched — "ход срывается" = this 400. ⚠ Pre-existing: side effects before it are NOT rolled back
  (`consume_item` HTTP to inventory `main.py:~3315`, i.e. a scroll can be burnt in inventory by a failed turn).
- Necromancer: in `_pay_skill_costs`, after H12, if `mana < cost`: `shortfall = cost − mana`, `hp_cost =
  ceil(shortfall × 1.5)` (rounding to decide); require `hp − hp_cost > 0` (strictly, "can't kill yourself") else
  400 with a Russian message (mana + HP); mana → 0, hp −= hp_cost; add `hp_paid` to `spend` / `resource_spend`
  event + contribution. HP checked at **end of turn**, i.e. after reflect damage taken this turn — a Guardian's
  reflect can turn an affordable turn into a 400 (whole turn void). Option: pre-validate at turn start too; or
  accept. HP payment must bypass shields (self-payment, not damage) and must not trigger Paladin/kill logic.
- Frontend blocks the card when short of mana: `SkillHand.tsx:198-201` (`short` → disabled + "Не хватает маны"),
  `SkillPicker.tsx:278` (number only). Needs a Necromancer branch in `utils/passiveCosts.ts`
  (e.g. `manaShortfallHpCost`) mirroring the backend formula; card shows the HP surcharge instead of blocking.
- **autobattle** (`autobattle-service/app/strategy.py:234-242` `enough()`) filters skills by raw `cost_mana <=
  mana`. Players can enable autobattle (frontend toggle), so a Necromancer on autobattle simply never pays with HP
  (safe, no 400). It also ignores the Caster discount. Optional improvement, not required; if done, it must not
  pick HP-paid skills that would self-kill.

### 2.6 Kills (Necromancer +10% max HP)

Step 9.5 `main.py:3962-3999`: `_newly_defeated` → `_victims` (enemy team only) → `passives.on_kills`
(`passives.py:1252`, Saber-only today, returns `(events, saber_stacks)`). Extend `on_kills` with a Necromancer
branch (+10% `max_hp` per kill; base for % — original or current max — and whether current HP also rises: decide).
Friendly-fire victims are already excluded (team filter). ⚠ End-of-battle sync `_sync_final_resources`
(`main.py:2305-2318`) writes `hp` into `character_attributes.current_health`; with a raised `max_hp` the HP can
exceed the real `max_health` → store `base_max_hp` and clamp at sync. ⚠ Frontend shows max HP from the
**snapshot** (`BattlePage.tsx:281-283` `snapshot.attributes.max_health`; 3D `BattlePage.tsx:~767`
`c.attributes?.max_health`) → must prefer runtime `max_hp` (already in the runtime payloads).

### 2.7 Reflect (Guardian), lifesteal (Berserk/Priest), redirect (Trickster) — all in `_strike`

`_strike` (`main.py:3002-3085`) knows target, attacker (`actor_pid`), `dealt` after resists/mult, `log["damage_type"]`
(resolved type; holy = `"sainting"`), `extra_plan` (extra hit), `actx` (None for non-enemy item rows). Proposed
order inside `_strike` (new kwarg e.g. `friendly=False` to switch attacker passives off):
1. `dealt` (engine) → 2. target shield absorb → `hp_loss` → `hp -= hp_loss`; `hp_removed = min(hp_loss,
max(0, hp_before))` (overkill not counted for lifesteal) → 3. Paladin vow check on target → 4. lifesteal
(Berserk if attacker `hp < 25% max` at that moment; Priest 10% / 15% if `damage_type == "sainting"`) from
`hp_removed`, capped at max, never on a dead attacker → 5. Guardian reflect `15% × dealt` (incl. part absorbed by
the Guardian's shield, per PM) applied to the attacker via a non-`_strike` path (no crit/dodge/resists, no
recursion → Guardian-vs-Guardian safe), attacker's own shield absorbs, then vow check on attacker. Order 4↔5
matters (reflect first could kill the attacker before lifesteal heals) — Architect to fix it.
- `total_damage_dealt/received` currently use `dealt_int` incl. what a shield would absorb — decide.
- Rage is computed once per attack (`main.py:3693-3699`, comment "HP атакующего внутри одной атаки не меняется") —
  no longer true with reflect/lifesteal; acceptable (document) or recompute.
- An attacker killed by reflect mid-AoE keeps striking (loop has no attacker-alive check) — decide whether to stop.
- Open: reflect/lifesteal on DoT ticks and effect-damage (B/C/D)? on extra hits (D13 says extra hits don't trigger
  on-hit passives; lifesteal is "dealt damage")? on scrolls (yes by D4 analogy)?
- Reflected/lifesteal log: `damage` event with `reflected: true` (source = Guardian, target = attacker) is animated
  by 3D automatically (`ArenaHud.tsx:68` reacts to every `damage`); lifesteal as `passive_proc` `heal` or
  contribution on the damage event.

**Trickster redirect.** Seam: `_finish_target_ctx` `main.py:2943-2969` already calls
`passives.deceit_redirect_target(battle_state, actor_pid, pid)` and discards the result (`passives.py:842`,
returns None). Fill: candidates = alive teammates of the attacker **excluding the attacker** (`_alive_sides`
allies minus self), `pick()` (rolls only because the target is a Trickster → D2 holds); none → None (old
behaviour). Store `ctx["redirect_pid"]`. Ctx is cached per (attack, target) (`_atk_ctx` `~3740`, `_item_ctx`
`~3497`), so every entry of the deceived attack goes to the same ally. Deceived consumers: skill loop
`main.py:~3812-3817`, item loop `~3528-3533`, extra hit `_finish_passive_attack` `~3121-3127` (decide whether
extra hits redirect). Strike the ally via `_strike(ally, dmg, mult × 0.5, ally_ctx, actx=None, …)` BUT:
`percent_damage_buffs` already contains the attack-level passive pct (`main.py:3713-3714` `_actx["pct"]`, item
`3491-3492`) and rage (`3698`, `3476`) → pass a copy without them, `rage_pct=0`, no H3/H8/H9, no lifesteal; ally
ctx via `_build_target_ctx(ally)` (defender-side passives of the ally apply; it rolls a dodge for the ally — decide;
`roll_deceit` is already skipped for same-team targets, `main.py:2958`). Guardian ally reflecting onto its own
teammate — decide (suggest no). Event: `damage` with `deceived_redirect`/`friendly_fire: true` + trickster pid.
Ally killed → `participant_defeated`, not a kill (team filter at 9.5). The deceit miss event stays as is.

### 2.8 Frontend

- Log: `BattlePageBar/useBattleBar.tsx` — `formatBattleEvent` (`:499`), contribution kinds switch (`:526-538`),
  `passive_proc` switch (`:628-700`), `PASSIVE_LOG_NAMES` (`:116`), `BattleEvent` type (`~:216`). Used by 2D bar
  (`BattlePageBar.tsx:279`) and 3D Chronicle (`Chronicle.tsx:85`). Add: `absorbed`/shield on damage, `reflected`,
  redirect, `hp_paid` on `resource_spend`, new `passive_proc` kinds (shield gain, vow, heal, inspiration stacks,
  spirit whisper, max HP gain). Unknown kinds already render as nothing.
- 2D: `CharacterSide.tsx` (TSX) renders `PlayerCard.jsx` (+`.module.scss`) and `CharacterResourcesList.jsx`
  (+scss) — **do not touch JSX/SCSS**; a shield chip can be an absolutely-positioned overlay in `CharacterSide.tsx`
  next to the existing passive badge (`CharacterSide.tsx:83-90`), data from `getResources`/`characterData`
  (`BattlePage.tsx:275-317`).
- 3D: `FighterCard.tsx` HP orb `:258-263` (`fighter.hp/maxHp`), `ArenaFighter` in `arenaTypes.ts`, built in
  `BattlePage.tsx:~755-790` → add `shield` (and runtime `max_hp`). Shield could be a ring/second value on the HP
  orb or a small badge; `WordTone "absorb"` (`FighterCard.tsx:31,64`) already exists for a float-pop.
- Runtime type `RuntimeState` in `BattlePage.tsx:~60-75` gains `shield?`, `max_hp`.
- Mana: `utils/passiveCosts.ts` (Necromancer HP surcharge mirror), `SkillHand.tsx:198-216`,
  `SkillPicker.tsx:278`, `InventoryItem.tsx:106`, profile `ResolvedSkillCard.tsx:173` / `SkillsTab.tsx:260`.

### 2.9 skills-service

`services/skills-service/app/subclasses.py`: set `implemented=True` for `paladin_sacred_vow` (:69),
`guardian_retribution` (:99), `bard_rhythm` (:217), `necromancer_blood_price` (:262),
`etheriad_spirit_whisper` (:276), `auromancer_tide` (:334), `priest_faith` (:348); update Berserk (:129, add
lifesteal <25%) and Trickster (:232, return the redirect sentence). Battle mirror `IMPLEMENTED_PASSIVES`
(`passives.py:68`) + `PASSIVE_*` keys; contract test compares the two.

### 2.10 Tests to extend

battle-service: `test_passives_wave1.py` (pure hooks), `test_passives_wave1_integration.py` (real
`_make_action_core` + REAL buffs harness from `test_subclass_passives.py`), `test_subclass_passives.py`
(registry/contract), and suites that pin runtime payload shapes (`test_join_requests.py`,
`test_pvp_attack.py`, `test_pvp_invitations.py` already touched by FEAT-189). The FEAT-189 docstring asserts
"the 7 registry passives that are NOT implemented do nothing" — that regression test must be inverted.
New: shield absorb (direct, reflect, DoT if chosen), vow one-shot incl. 40%→0 no-trigger, reflect no-recursion
(Guardian vs Guardian), reflect into attacker's shield, lifesteal caps / no heal from shield-absorbed part /
no heal from reflect, Necromancer 1 HP + 0 mana → 400 and state unsaved, kill → max HP, Bard stacks + death
cleanup, Etheriad priority, Auromancer overheal→shield cap + 3-turn expiry, redirect (ally exists / none / no
attacker passives), old states without new keys. skills-service registry tests for `implemented`.

### 2.11 Risks

| Risk | Note |
|---|---|
| Logic in `buffs` becomes a MagicMock in ~30 suites | Keep logic in `passives.py`; buffs only gets optional pass-through kwargs (default = identical). |
| Order shield / reflect / lifesteal / vow inside `_strike` | Must be fixed explicitly; double counting (lifesteal from absorbed part, reflect of reflect, vow twice). |
| Effects owned by dead Bard/Etheriad never expire | Explicit removal on death (9.5 + drop-out path). |
| Necromancer turn void by late 400 after reflect; non-rolled-back side effects | Pre-existing for mana; document or pre-check. |
| `max_hp` growth leaks into `character_attributes.current_health` | Clamp at `_sync_final_resources`. |
| Frontend shows snapshot max HP | Switch to runtime `max_hp`. |
| Rage / Berserk lifesteal threshold computed at different moments | Rage once per attack; lifesteal per hit — document. |
| Old Redis states | `.get` everywhere; `shields`/`bard_stacks`/etc. absent → neutral. |
| autobattle unaware of HP payment / Caster discount | Conservative, never errors; optional enhancement. |
| Cleanse `debuff` selector is owner-based | Ally buffs from passives removable by antidotes; Paladin needs its own negative-effect definition. |

---

## 3. Architecture Decision (filled by Architect — in English)

Builds on FEAT-189 §3 (D1–D19 stay in force). Line numbers = current uncommitted tree, indicative only.

### 3.0 Summary of decisions

| # | Question | Decision |
|---|----------|----------|
| E1 | Where does the logic live? | Same as D1/D2: **every rule, number, roll and state mutation in `passives.py`** (new hooks H14–H25, §3.2). `passives` still imports neither `buffs` nor `battle_engine`. `main.py` only calls hooks at fixed points. Rolls (`pick` only — no new chance rolls) happen only for an owner of the passive. |
| E2 | `buffs.py` | Gets exactly **two optional keyword hooks**, defaults `None` → byte-identical behaviour: `absorb_fn` and `overheal_fn` on `apply_new_effects`, `tick_periodic_effects` and (pass-through) `_tick_resource`. No logic in buffs beyond calling them (§3.3). `main.py` always passes both closures; the closures are no-ops for passive-less battles, so results are identical; the ~30 suites that `MagicMock` buffs accept extra kwargs (verified: no suite asserts the exact call kwargs of these functions). |
| E3 | Shield storage | On the **shielded** participant: `passive_state["shields"] = [{"key", "owner", "amount", "cap", "turns_left", "fresh"}]` (list, additive, old states → absent → 0). `key` = source passive (`paladin_sacred_vow` / `auromancer_tide`), `owner` = pid whose passive created it, `amount` float > 0, `cap` = its ceiling, `turns_left` = int (tide) or `None` (Paladin: until broken / end of battle), `fresh` = skip the first owner-turn tick. Not an `active_effects` row (cleanse `all` would strip it, `aggregate_modifiers` would sum it, absorb mutates it) — the analyst's recommendation is adopted. |
| E4 | Absorb order / stacking | Shields from different sources **stack** (separate entries). Absorb consumes **timed entries first, shortest `turns_left` first, then permanent ones** (use what would vanish anyway first); ties → list order. Empty entries are removed. A shield is never "healed" (vow is once per battle); a tide entry from the same Auromancer on the same target is **topped up** by new overheal up to its cap and its `turns_left` reset to 3 (one entry per (target, Auromancer)). |
| E5 | What shields absorb | **Any HP loss that is damage**: direct strikes (`_strike`, incl. extra hits, scrolls, redirected blows), Guardian reflect, enemy instant HP rows (`apply_new_effects`), DoT (bleed/burn/periodic poison) and negative HP doses (`_tick_resource`). **Not**: Necromancer HP payment (self-payment), timeout drop-out (`hp = 0` is not damage). |
| E6 | Shield expiry | Paladin: `turns_left=None` → until broken or battle end. Auromancer: `turns_left=3`, ticks at the **end of the Auromancer's own turn** (`passives.tick_shields(state, actor_pid)` right after `decrement_durations` at 9.4), `fresh` skips the creation turn — identical clock to effects he casts. Shields owned by a participant who dies/drops out are removed (§E14) — they would otherwise never tick. |
| E7 | Order inside `_strike` (fixed) | ① engine `dealt` (+mult, unchanged) → ② **target shield absorb** (`absorbed`, `remaining`) → ③ **HP loss** `hp -= remaining`; `hp_removed = min(remaining, max(0, hp_before))` (overkill never counts) → ④ **Paladin vow** check on the target (`0 < hp < 30%`, once) → ⑤ **lifesteal / «Вера»** of the attacker from `hp_removed` → ⑥ **Guardian reflect** to the attacker from `taken = absorbed + hp_removed`. |
| E8 | Lifesteal vs reflect | **Lifesteal first, reflect second.** Justification: (a) the drain is part of the blow itself, the reflect is the defender's *reaction* to it — causal order; (b) deterministic and favourable to read: a Berserk at 5 HP who hits a Guardian heals, then eats the reflect (otherwise the reflect would kill him before the heal and lifesteal would be skipped as "attacker dead", making «Ярость»-lifesteal useless against exactly the tank it is meant to outlast); (c) Berserk's `<25%` threshold is read **before** the heal of this hit, so the order doesn't change whether lifesteal applies. Reflect never triggers lifesteal (PM). |
| E9 | Reflect mechanics | `R = taken × 15%` (`taken` = after resists, incl. what the Guardian's shield absorbed, **excluding overkill**). Applied by `passives.retaliate` — **not** through `_strike`/engine: no crit, no dodge, no resists, no deceit, no H3/H8, never reflected again (Guardian vs Guardian safe by construction: `retaliate` is never called from the reflect path), never lifesteals. The attacker's shields absorb it, then HP loss (can go ≤ 0 = can kill), then the attacker's Paladin vow check. Fires on every enemy-side strike including extra hits and scrolls; **not** on redirected blows, DoT, effect damage. Fires even if the hit killed the Guardian. Stats: `R` (rounded int) added to Guardian `total_damage_dealt` and attacker `total_damage_received`. |
| E10 | Dead attacker | After every strike (skill loop, item loop, extra hit) main checks the actor: `hp <= 0` → **no further strikes** in this action (AoE loop breaks, extra hit skipped, attack-skill damage loop at step 9 skipped if the actor died in the item step). Non-strike steps (effects already rolled, H9 stacks, costs, DoT tick, 9.5) run as before. Actor death is resolved in 9.5 like any other (`participant_defeated`; not a kill — own team). |
| E11 | Lifesteal | Per strike with `actx is not None` (enemy-side attack: skill, scroll, extra hit) and not redirected. Attacker must be alive. Berserk: attacker `hp < 25% max_hp` at that moment → 15% of `hp_removed`; Priest: 10%, 15% if the strike's resolved `damage_type == "sainting"`. Heal via `passives.heal` (clamped to `max_hp`, never heals `hp ≤ 0`, never creates a shield). Not from DoT/effect damage, not from reflect, not from the absorbed part. «Ярость» damage bonus stays computed **once per attack** (FEAT-188 comment updated: HP can now change inside an attack via reflect/lifesteal — accepted, documented). |
| E12 | Paladin vow | Trigger after **every** HP-loss site where the Paladin can be hit: inside `_strike` (step ④, not on redirected blows), inside `retaliate` (attacker side), after `_land_enemy_effects`, after the non-enemy effect wrapper, after the DoT tick (sweep over participants whose HP went down). Condition `0 < hp < 30% × max_hp` and `not vow_used` → `vow_used = True`, shield `20% × max_hp` (`turns_left=None`), and **cleanse one**: pure pick in passives — the **last** row in `active_effects[paladin]` that is *negative* = `owner_id` belongs to a participant of **another team** (rows without `owner_id`/old rows → treated as own → not negative) and `control_kind(row) != "hard"` (Stun / Poison-paralysis never removed). Removed by `pop` from that list (passives mutates state as before). 40% → 0 in one hit: HP not > 0 → no vow. |
| E13 | Necromancer | `_pay_skill_costs` (final check at payment, PM). After H12 sums the mana cost: if the actor is a Necromancer and `mana < cost` → `passives.blood_price(participant, cost)` → `shortfall = cost − mana`, `hp_cost = ceil(shortfall × 1.5)`; affordable iff `hp − hp_cost ≥ 1`; else **400** `"Недостаточно маны: нужно X, есть Y. Доплатить здоровьем нельзя: нужно Z HP, есть W (должно остаться хотя бы 1)"`. Paid: `mana = 0` (actual mana spent goes to `spend["mana"]`), `hp −= hp_cost`, `spend["hp_paid"] = hp_cost`. HP payment bypasses shields, triggers nothing (no vow/rage/kill). Energy/stamina checks unchanged, all checks before any deduction. Edge: actor already dead at payment time (killed by reflect) → surcharge waived (mana → 0, `hp_paid` absent) — a dead man doesn't pay and the death is not "undone" by a 400. Reflect can make a planned surcharge unaffordable → 400, whole turn void (state unsaved) — consistent with "final check at payment", documented. Kill → `on_kills`: per victim, if Necro alive: heal `10% × max_hp` (capped, `max_hp` unchanged → no sync issue). Autobattle unchanged. |
| E14 | Deaths / drop-out cleanup | `passives.on_deaths(state, pids) -> events`: for every dead pid — remove `active_effects` rows whose `source` is `passive:bard_rhythm` / `passive:etheriad_spirit_whisper` and `owner_id` = that pid (on everyone); remove shields owned by that pid (on everyone) and all shields **on** that pid; Bard → `inspiration_end` proc. Called at 9.5 with `_newly_defeated` and in `handle_expired_turn` after `pdata["defeated"] = True` (drop-out). |
| E15 | Passive-sourced effects (Bard, Etheriad) | Rows are ordinary StatModifier rows (`effect_name`, `attribute_key`, `magnitude`, `duration`) applied by **main.py** with `apply_new_effects(state, target, rows, owner_pid=actor, source=("passive", key))` → `_effect_identity` refreshes in place (duration = max, magnitude = new). They work through existing channels (`percent_damage` → `build_percent_damage_buffs["all"]`, `percent_resist_all` → resists `"all"`) with zero new damage hooks, and show as effect circles. Passive hook `end_of_action` returns `[(target_pid, rows)]` + events; it is called **after `resource_spend`, before 9.4a** (so a payment 400 voids them too; fresh rows skip the creation-turn tick). Not called when the actor is dead. |
| E16 | Bard | Counter `passive_state["bard_stacks"]`. Every own action: mode decided **now** — *group* if ≥1 living teammate other than the Bard (+3%/stack, cap 4) else *solo* (+5%/stack, cap 3). Non-control-skipped turn → `stacks = min(cap, stacks + 1)`; control-skipped turn → no new stack, rows refreshed (so the stack doesn't decay while stunned). On mode change stacks are clamped to the new cap. Rows `Вдохновение` (`percent_damage`, `magnitude = stacks × pct`, duration 2) to the Bard + every living teammate (group) / the Bard only (solo). Duration 2 + refresh every Bard turn = permanent while the Bard acts; explicit removal on death (E14). Solo→group switch leaves no stale rows (same identity, refreshed). Log: `inspiration` proc. |
| E17 | Etheriad | At end of every **non-skipped** own action. "Allies" = living teammates **excluding** the Etheriad; none → `[etheriad]`. Priority: (1) allies with `hp/max_hp < 50%` → lowest ratio (tie → lowest pid) gets `Шёпот духов: стойкость` (`percent_resist_all +8`); (2) else enemies **landed** by the Etheriad in this action (skill + scroll + extra hit targets, collected by main from `passives.landed_targets(actx)` + extra-hit target), alive, without a `passive:etheriad_spirit_whisper` debuff row → `pick()` → `Шёпот духов: уязвимость` (`percent_resist_all −8`, `is_enemy=True`, no chance roll, no Monk/Trickster adjustments — not control); (3) else `pick(allies)` → `Шёпот духов: сила` (`percent_damage +8`). Duration 2 (fresh → active through his next 2 turns). Log: `spirit_whisper` proc. |
| E18 | Auromancer «Прилив» | One pure hook `passives.on_heal(state, healer_pid, target_pid, intended, applied) -> events`: healer must own `auromancer_tide`, target alive; `overflow = intended − applied > 0` → tide shield on target (E4, cap `20% × target max_hp`, 3 turns, fresh). Measurement per path: **(a) skill / item HP rows** (self, ally, all_allies, item non-enemy, incl. the first dose of a HoT) → `apply_new_effects(..., overheal_fn)` calls `overheal_fn(pid, intended=dose magnitude, applied=real change, owner_id)` for every positive HP dose; **(b) HoT doses** at 9.4a → `_tick_resource` calls `overheal_fn` for positive HP doses **before** its `if not change: return None` (full-HP target = whole dose overflows); **(c) potions** (`health_recovery`) → main calls `on_heal(actor, actor, delta, new − old)` right after the existing clamp. Lifesteal/«Вера»/kill heals never create tide (their owners can't be Auromancers). |
| E19 | Trickster redirect | `_finish_target_ctx(pid, tattrs, resists, allow_redirect=True)`: when deceived → `ctx["redirect_pid"] = passives.deceit_redirect_target(state, actor_pid, pid)` = `pick(living teammates of the attacker excluding the attacker)` (only rolls for a Trickster target; empty → `None` = old behaviour, attack just fails). Extra hits pass `allow_redirect=False` (no pick consumed, deceived extra hit = miss as today). Consumers (skill loop, item enemy loop): deceit miss event logged once as today, then **each entry aimed at the Trickster** strikes `redirect_pid` via `_strike(..., redirect_from=trickster_pid)` with: `mult × 0.5`, a **plain ctx** for the ally (attrs + effect mods + resists from effects/attributes; no H4/H5, no dodge roll, no deceit), attacker attrs **without** H5, damage buffs **without** rage/H2 pct (effects-only `build_percent_damage_buffs`), `actx=None` (no H3/H8/H9/H10), no vow/lifesteal/reflect; the ally's shields absorb. Ally killed → 9.5 `participant_defeated`, not a kill (team filter). |
| E20 | Runtime `shield` field | `shield: int` = `passives.shield_total(p)` (rounded sum, 0 for old states) added to **every** runtime participant payload: `get_state_internal` (~1739), `get_state` (~1847), `spectate_battle` (~1940), `get_battle_preview` (~2059), `admin_get_battle_state` (~5073), `_build_runtime` (~6009, WS). Additive; autobattle ignores it. Runtime `max_hp` does not change in this feature (Necro kill = heal) → frontend keeps the snapshot max HP. |
| E21 | Stats | `_strike` keeps counting `dealt_int` (incl. absorbed) into `total_damage_dealt/received` (unchanged); DoT keeps counting only HP actually lost (buffs unchanged). Reflect counts as in E9. Lifesteal/heals are not counted. |
| E22 | DB / nginx / compose / permissions / Redis keys | None. New `passive_state` keys only (`shields`, `vow_used`, `bard_stacks`, `bard_mode`). |

### 3.1 `passives.py` — new constants

```
PASSIVE_PALADIN="paladin_sacred_vow"  PASSIVE_GUARDIAN="guardian_retribution"  PASSIVE_BARD="bard_rhythm"
PASSIVE_NECROMANCER="necromancer_blood_price"  PASSIVE_ETHERIAD="etheriad_spirit_whisper"
PASSIVE_AUROMANCER="auromancer_tide"  PASSIVE_PRIEST="priest_faith"
IMPLEMENTED_PASSIVES = all 21 keys

PALADIN:    VOW_HP_PCT=30, VOW_SHIELD_PCT=20
GUARDIAN:   RETRIBUTION_PCT=15
BERSERK:    RAGE_LIFESTEAL_HP_PCT=25, RAGE_LIFESTEAL_PCT=15
PRIEST:     FAITH_LIFESTEAL_PCT=10, FAITH_HOLY_LIFESTEAL_PCT=15, HOLY_TYPE="sainting"
BARD:       INSPIRATION_PCT=3, INSPIRATION_MAX_STACKS=4, INSPIRATION_SOLO_PCT=5,
            INSPIRATION_SOLO_MAX_STACKS=3, INSPIRATION_DURATION=2, INSPIRATION_EFFECT_NAME="Вдохновение"
NECROMANCER:BLOOD_HP_PER_MANA=1.5, BLOOD_MIN_HP_LEFT=1, NECRO_KILL_HEAL_PCT=10
ETHERIAD:   SPIRIT_ALLY_HP_PCT=50, SPIRIT_RESIST_PCT=8, SPIRIT_DAMAGE_PCT=8, SPIRIT_DURATION=2,
            SPIRIT_WARD_NAME="Шёпот духов: стойкость", SPIRIT_CURSE_NAME="Шёпот духов: уязвимость",
            SPIRIT_MIGHT_NAME="Шёпот духов: сила"
AUROMANCER: TIDE_CAP_PCT=20, TIDE_TURNS=3
TRICKSTER:  REDIRECT_MULT=0.5
SOURCE_BARD="passive:bard_rhythm", SOURCE_ETHERIAD="passive:etheriad_spirit_whisper"  (= buffs.normalize_source(("passive", key)) — local string, no import)
Kinds (contribution): KIND_LIFESTEAL="lifesteal", KIND_REFLECT="reflect", KIND_REDIRECT="redirect", KIND_BLOOD_PRICE="blood_price"
Kinds (passive_proc): PROC_VOW="vow", PROC_TIDE="tide", PROC_SHIELD_ABSORB="shield_absorb", PROC_KILL_HEAL="kill_heal",
            PROC_INSPIRATION="inspiration", PROC_INSPIRATION_END="inspiration_end", PROC_SPIRIT_WHISPER="spirit_whisper"
```
Module docstring: wave 2 added, new `passive_state` keys listed, "change a constant → update the registry description" kept.

### 3.2 `passives.py` — new hook API (names binding for tests; internals free)

All tolerant of old states / garbage (neutral result, never raise). "Alive" = existing `_is_alive`.

| # | Hook | Called from | Behaviour |
|---|------|-------------|-----------|
| H14 | `shield_total(participant) -> int` | all runtime payload builders, event fields | `round(Σ amount)` of `passive_state["shields"]`, 0 if absent |
| H15 | `absorb(state, pid, amount) -> (remaining: float, absorbed: float)` | `_strike`, `retaliate`, main's `absorb_fn` closure | E4 order, mutates/removes entries; `amount ≤ 0` or no shields → `(amount, 0)` |
| H16 | `add_shield(state, pid, key, owner, amount, cap, turns_left) -> float gained` | internal (vow, tide) | E4 top-up rule; returns amount actually added (cap-limited) |
| H17 | `tick_shields(state, actor_pid) -> None` | right after `decrement_durations` (9.4) | timed shields with `owner == actor`: `fresh` → clear flag; else `turns_left −= 1`, drop at 0 |
| H18 | `check_vow(state, pid) -> list[event]`; `snapshot_hp(state) -> {pid: hp}`; `check_vows(state, before) -> list[event]` (pids whose hp < before) | `_strike` ④, `retaliate`, both effect wrappers, after the DoT tick | E12 |
| H19 | `lifesteal(state, attacker_pid, hp_removed, damage_type) -> Optional[contribution]` | `_strike` ⑤ | E11; contribution `{key, kind:"lifesteal", value: healed int, owner: attacker}`; None if nothing healed |
| H20 | `retaliate(state, guardian_pid, attacker_pid, taken, damage_type) -> list[event]` | `_strike` ⑥ | E9; returns `[reflect damage event, *vow events of attacker]`, `[]` if target not Guardian / same team / R ≤ 0 |
| H21 | `heal(participant, amount) -> float applied` | internal (lifesteal, kill heal) | clamp to `max_hp`, no-op on `hp ≤ 0` |
| H22 | `on_heal(state, healer_pid, target_pid, intended, applied) -> list[event]` | main's `overheal_fn` closure; potion path | E18 |
| H23 | `blood_price(participant, mana_cost) -> Optional[dict]` | `_pay_skill_costs` | None unless Necromancer with `mana < cost`; else `{"hp_cost": int, "mana_paid": mana, "affordable": bool, "waived": bool}` (E13) |
| H24 | `end_of_action(state, actor_pid, skipped: bool, landed_pids: list) -> (applications: list[(target_pid, rows, source_tuple, is_enemy)], events)` | after `resource_spend`, before 9.4a | Bard E16, Etheriad E17; others → `([], [])` |
| H25 | `on_deaths(state, pids) -> list[event]` | 9.5, `handle_expired_turn` | E14 |
| H6 | `deceit_redirect_target(state, attacker_pid, trickster_pid) -> Optional[int]` (filled) + `redirect_contribution(trickster_pid)` | `_finish_target_ctx` | E19 |
| H13 | `on_kills` (extended, same signature/return) | 9.5 | + Necromancer kill heal → `kill_heal` proc per victim |

### 3.3 `buffs.py` — optional hooks only

```python
def apply_new_effects(state, pid, raw_effect_rows, is_enemy=False, owner_pid=None, source=None,
                      absorb_fn=None, overheal_fn=None) -> None
def tick_periodic_effects(state, participant_id=None, absorb_fn=None, overheal_fn=None) -> List[Dict]
def _tick_resource(state, pid, eff, owner, absorb_fn=None, overheal_fn=None) -> Dict | None
```
- `absorb_fn(pid: int, amount: float) -> float remaining` — called for every **HP decrease** before it hits the bar: in `apply_new_effects` resource branch when `attribute == "hp"` and the (post-inversion) dose is negative → the bar changes by `−remaining`, while the **stored** per-dose `eff["magnitude"]` for later doses stays the original (un-absorbed) value; in `tick_periodic_effects` → `amount = absorb_fn(pid, amount)` before `new_hp` (event `amount` = HP actually lost, as today); in `_tick_resource` for negative HP doses.
- `overheal_fn(pid: int, intended: float, applied: float, owner_id: int) -> None` — called for every **positive HP dose** in `apply_new_effects` (after `_change_resource`) and `_tick_resource` (before the `if not change` early return).
- With both `None` the code path is unchanged (no extra branches executed besides `if absorb_fn` checks). Docstrings explain why the logic lives in passives (mocked module).

### 3.4 `main.py` integration

Module level:
1. **`_pay_skill_costs`** (E13): after the H12 loop and before the generic check, `bp = passives.blood_price(pstate, spend["mana"])`; `bp` not None → skip the mana check for this actor, 400 (Russian, E13) if not `affordable`; deduct energy/stamina as before, `mana → 0`, `hp −= hp_cost` (unless waived), `spend["mana"] = mana_paid`, `spend["hp_paid"] = hp_cost` (only when > 0). Others: unchanged code path. In `_make_action_core` the `resource_spend` event gets `passives: [contribution(necromancer_blood_price, "blood_price", hp_paid, actor)]` when `hp_paid` (merged with the Caster list logic).
2. **Six runtime payload builders** (E20): `"shield": passives.shield_total(<participant>)`.
3. **`handle_expired_turn`**: after the drop, `turn_events.extend(passives.on_deaths(state, [participant_id]))` (list built after the drop — append there).

Inside `_make_action_core` (single writer):
4. Closures next to the FEAT-189 helpers: `_absorb_fn(pid, amount)` → `passives.absorb`, records `(pid, absorbed)` into a local `_pending_absorbs`; `_flush_absorbs()` → one `passive_proc shield_absorb` per pid (who = holder, value = absorbed int, shield = left) appended to `turn_events`; `_overheal_fn(pid, intended, applied, owner)` → `turn_events.extend(passives.on_heal(...))`.
5. **`_apply_effects(target_pid, rows, **kw)`** wrapper for **all non-enemy** `apply_new_effects` sites in `_make_action_core` (support/defense/attack self, ally, all_allies; item non-enemy rows): passes `absorb_fn`/`overheal_fn`, then `_flush_absorbs()` + vow check on the target (`check_vows` with the pre-call HP snapshot). **`_land_enemy_effects`** gets the same kwargs + flush + vow check. Callers otherwise unchanged (events identical when no passives).
6. **Potion** (`health_recovery`): after the clamp, `turn_events.extend(passives.on_heal(state, actor, actor, delta, new − old))` (health only).
7. **`_finish_target_ctx(..., allow_redirect=True)`** (E19) stores `redirect_pid`; `_build_target_ctx(pid, allow_redirect=True)` passes it; extra hit uses `False`. New `_plain_ctx(pid)` for the redirect target (attrs+effect mods, `build_percent_resist_buffs(mods, attrs)`, `dodged=False`, `deceived=False`, `contributions=[]`).
8. **`_strike`**: new kwarg `redirect_from: int | None = None`; return value becomes **`(dealt_int, event, post_events)`** (caller appends `event` then `post_events`). Order E7. Event additions (only when non-zero/true): `absorbed`, `shield_left`, lifesteal contribution, `redirected: True` + `deceived_by` + redirect contribution (redirect events carry **no** rage/attack/defender contributions and no FEAT-188 `passive_key`).
9. **Skill loop / item enemy loop**: deceived ctx with `redirect_pid` (alive) → after the (once-per-target) miss event, `_strike(redirect_pid, dmg, tmult × REDIRECT_MULT, _plain_ctx cached per attack, None, <effects-only buffs>, <attrs without H5>, weapon, extra, 0, None, slot, redirect_from=target)`. The skill path keeps `percent_damage_buffs_base = build_percent_damage_buffs(attacker_buff_modifiers)` copy **before** rage/H2 pct and the attrs before `_actor_attrs`; item path likewise. After every `_strike` → `if actor hp <= 0: stop` (E10). Step 9 damage loop not entered if the actor is already dead.
10. **`_finish_passive_attack`**: extra hit skipped if actor dead; uses the new `_strike` return; collect the extra-hit target into the landed list when it lands.
11. **After `resource_spend`**: if actor alive → `apps, evs = passives.end_of_action(state, actor, bool(_full_skip), landed)` where `landed` = union of `passives.landed_targets(actx)` of the item and skill attacks (+ landed extra-hit target); for each application `apply_new_effects(state, target, rows, is_enemy=…, owner_pid=actor, source=source)`; `turn_events.extend(evs)`.
12. **9.4a**: `before = passives.snapshot_hp(state)`; `tick_periodic_effects(state, actor, absorb_fn=_absorb_fn, overheal_fn=_overheal_fn)`; `_flush_absorbs()`; `turn_events.extend(passives.check_vows(state, before))` (after the periodic events).
13. **9.4**: `passives.tick_shields(state, actor)` right after `decrement_durations`.
14. **9.5**: `turn_events.extend(passives.on_deaths(state, _newly_defeated))` after the defeat events; `on_kills` call unchanged (Necro branch inside).
15. FEAT-188 rage comment updated (HP may change inside an attack now; rage still once per attack).

### 3.5 Log contract (exact field names for the frontend)

Damage event (additive optional keys):
```json
{"event":"damage","source":3,"target":7,"final":120.0, "...":"engine log",
 "absorbed":40, "shield_left":10,
 "passives":[{"key":"priest_faith","kind":"lifesteal","value":12,"owner":3},
             {"key":"berserker_rage","kind":"lifesteal","value":18,"owner":3}]}
```
Reflect (one per reflected strike, right after the strike's event and the target's vow event):
```json
{"event":"damage","source":7,"target":3,"final":18.0,"damage_type":"physical","reflected":true,
 "absorbed":0,
 "passives":[{"key":"guardian_retribution","kind":"reflect","value":18,"owner":7}]}
```
(`final` = R rounded to 2; `absorbed`/`shield_left` as on any damage event; no `critical`, no `dodged`.)
Redirect:
```json
{"event":"damage","source":3,"target":5,"final":30.0,"...":"engine log","redirected":true,"deceived_by":7,
 "passives":[{"key":"trickster_deceit","kind":"redirect","value":50,"owner":7}]}
```
(preceded by the existing deceit miss event on the Trickster.)
`resource_spend`: `"hp_paid": 15` + `passives:[{"key":"necromancer_blood_price","kind":"blood_price","value":15,"owner":3}]`.
`passive_proc` (shape `{event, who, key, kind, target?, value?, stacks?, effects?, shield?, mode?, targets?}`):
| kind | who | fields |
|---|---|---|
| `vow` | Paladin | `value` = shield gained, `shield` = total after, `effects` = [removed effect name] (absent if nothing removed) |
| `tide` | Auromancer | `target`, `value` = shield gained, `shield` = target total after |
| `shield_absorb` | shield holder | `value` = absorbed (DoT / effect damage only; strikes use `absorbed`), `shield` = left |
| `kill_heal` | Necromancer | `target` = victim, `value` = HP healed |
| `inspiration` | Bard | `stacks`, `value` = % per target now, `mode` = `"group"`/`"solo"`, `targets` = [pids] |
| `inspiration_end` | Bard | `targets` = [pids whose rows were removed] |
| `spirit_whisper` | Etheriad | `target`, `mode` = `"ward"`/`"curse"`/`"might"`, `value` = signed % (8 / −8 / 8) |
Unknown kinds still render as nothing. All values are ints except `final`.

### 3.6 Frontend

- **`utils/passiveCosts.ts`**: `NECROMANCER_PASSIVE_KEY`, `BLOOD_HP_PER_MANA = 1.5`, `BLOOD_MIN_HP_LEFT = 1` (comment: mirror of `passives.py`), `bloodPriceHp(cost, mana, passiveKey): number` = Necro && cost > mana ? `Math.ceil((cost − mana) * 1.5)` : 0, `canPayMana(cost, mana, hp, passiveKey): boolean` = `cost <= mana || (Necro && hp − bloodPriceHp(...) >= 1)`. Table (cost, mana, hp → hpCost, ok): (10,0,16 → 15, ✓), (10,0,15.9 → 15, ✗), (3,2,10 → 2, ✓), (1,0,2 → 2, ✗), (1,0,3 → 2, ✓), (5,5,1 → 0, ✓).
- **Cards**: `Arena3D/hud/SkillHand.tsx` (affordability + cost gem shows `+N HP` when surcharge > 0, not blocked when payable), `SkillPicker/SkillPicker.tsx` (same rule for the 2D picker), any other battle-page mana check (`InventoryItem.tsx` if it checks skill mana). The acting player's `hp` from runtime, passive from the snapshot.
- **Shield 2D**: `CharacterSide/CharacterSide.tsx` absolutely-positioned overlay chip next to the passive badge («Щит N», hidden when 0); data from runtime `shield` via `characterData` (add `shield?: number` to the TS types in `battleTypes.ts`/`BattlePage.tsx` `RuntimeState`). **Do not touch `PlayerCard.jsx`, `CharacterResourcesList.jsx` or any SCSS.** Tailwind + design-system tokens, 360px.
- **Shield 3D**: `arenaTypes.ts` `ArenaFighter.shield: number`, filled in `BattlePage.tsx` (~755-790), `FighterCard.tsx` HP orb shows the shield (ring/second value, hidden when 0); `WordTone "absorb"` may pop on `absorbed`.
- **Log** (`BattlePageBar/useBattleBar.tsx`, covers 2D bar + 3D Chronicle): `BattleEvent` gains `absorbed?`, `shield_left?`, `reflected?`, `redirected?`, `deceived_by?`, `hp_paid?`, `shield?`, `mode?`, `targets?`; `PASSIVE_LOG_NAMES` for the 7 new keys; contribution kinds `lifesteal` («· Вера +N HP» / «· Ярость: вампиризм +N HP» — label by key), `reflect`, `redirect`, `blood_price`; damage line suffix «(щит поглотил N)»; reflect line «<Хранитель> — Возмездие: <атакующий> −N»; redirect line «удар ушёл в <союзник> (Обман <Фокусник>) −N»; `resource_spend` «Плата кровью −N HP»; procs `vow` «Священный обет: щит N, снято: X», `tide` «Прилив: щит <цель> +N», `shield_absorb` «щит <кто> поглотил N», `kill_heal` «Плата кровью +N HP», `inspiration` «Вдохновение ×N (+X% урона)», `inspiration_end` «Вдохновение угасло», `spirit_whisper` by mode. Old logs unchanged.
- `ArenaHud.tsx`: reflect/redirect are plain `damage` events (animate automatically) — verify, no change expected.
- Rules: DESIGN-SYSTEM, TS only, Tailwind only, no `React.FC`, Russian strings, errors visible, `tsc --noEmit` + `npm run build` in Docker.

### 3.7 skills-service

`app/subclasses.py`: `implemented=True` for `paladin_sacred_vow`, `guardian_retribution`, `bard_rhythm`, `necromancer_blood_price`, `etheriad_spirit_whisper`, `auromancer_tide`, `priest_faith` (all 21 now). Descriptions: **Berserk** + «Ниже 25% здоровья — вампиризм: 15% нанесённого урона лечит Берсерка.»; **Trickster** returns the redirect: «…атака по Фокуснику не проходит; в групповом бою она уходит в случайного союзника атакующего с 50% урона.»; **Necromancer** last sentence → «За убийство в бою — лечение на 10% макс. здоровья.» (PM decision: heal, not max HP growth). Others already match §3.1. Same schema, no API change.

### 3.8 Security

No new endpoints or client inputs (target ids validated as before; `redirect_pid` is chosen server-side). New 400 message contains only the actor's own numbers. No secrets/PII in logs. Rate limits unchanged.

### 3.9 Cross-service validation

- Runtime payloads: additive `shield` field in 6 builders; autobattle-service reads `/internal/.../state` by explicit keys → unaffected; frontend tolerant (`?? 0`).
- skills-service registry: same schema, flags only → frontend badge.
- `buffs` signatures: optional kwargs only; mocked suites unaffected.
- Log: additive keys/kinds; `save_log` stores dicts as-is.
- autobattle: Necromancer on autobattle never pays HP (its `enough()` filter stays raw mana) — safe, documented.

### 3.10 Risks & mitigations

| Risk | Mitigation |
|---|---|
| Logic slipping into mocked `buffs` | E2: buffs only calls callbacks; QA tests the callbacks through the REAL buffs harness + guard test (passives imports neither module). |
| Double counting (lifesteal from shield part, reflect of reflect, vow twice) | E7 order, `retaliate` never recurses, `vow_used` flag; QA pins each. |
| Eternal effects/shields of dead owners | E14 `on_deaths` at 9.5 + drop-out; QA. |
| Late Necromancer 400 after reflect | Documented (PM: final check at payment); dead-actor waiver; QA. |
| `_strike` return-shape change missed at a call site | Single writer for `main.py`; 3 call sites (skill, item, extra) listed; full suite. |
| Stored dose magnitude corrupted by absorb | E2/§3.3 explicit rule; QA HoT/DoT with partial absorb over 2 doses. |
| Frontend/backend blood formula drift | Same integer rule + shared table in both files' comments; QA backend table; frontend dev checks the same table. |
| Old in-flight Redis states | `.get`/`_ps_read` everywhere; QA old-state attack with a Guardian/Paladin key but no `passive_state`. |

### 3.11 Rollback

Code-only. Reverting leaves unused `passive_state` keys and effect rows with `source="passive:…"` in live states (old code treats them as normal effects that expire by owner turns; Bard rows of a dead Bard would linger until battle end — acceptable pre-beta). Flip the 7 `implemented` flags back if only battle code is reverted.

### 3.12 Open questions for PM (non-blocking — defaults above are implemented unless PM says otherwise)

- **Q1 (Bard, stunned turn):** default — no new stack, existing stacks refreshed (don't decay).
- **Q2 (Etheriad, stunned turn):** default — spirits are silent on a control-skipped turn.
- **Q3 (Etheriad «союзник»):** default — teammates **excluding** the Etheriad when any are alive; the Etheriad himself only when alone. Target choice in (2)/(3) is random among candidates.
- **Q4 (Auromancer died):** default — his tide shields vanish with him (no one left to tick them).
- **Q5 (Redirected blow on an ally Paladin):** default — no vow from that blow (PM: "no passives of the target"); a later hit triggers it normally.
- **Q6 (Guardian killed by the hit):** default — reflect still fires (base excludes overkill).
- **Q7 (Necromancer killed by reflect before paying):** default — HP surcharge waived (turn stands, he is dead).


---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Parallelism.** Wave A (no file overlap): Tasks 1, 2, 4. Task 3 (the only `main.py` writer) after Task 2. QA 5 after 2; QA 6 after 3; QA 7 after 1. Frontend (Task 4) codes against the §3.5 contract; its live check needs Task 3. Reviewer last. **No agent runs `git commit`, `git stash` or `git push`** (the user commits once at the end). All checks run inside Docker containers (no node/python toolchain on the host).

### Task 1 — skills-service: all 21 implemented, description updates
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/skills-service/app/subclasses.py`, `docs/services/skills-service.md` |
| **Depends On** | — |
| **Description** | Per §3.7: `implemented=True` for the 7 keys; Berserk (lifesteal <25%), Trickster (redirect sentence back), Necromancer (kill = heal 10% max HP) descriptions; re-check the other 4 new descriptions quote §3.1 numbers. Module docstring / service doc: all 21 live. Do NOT edit tests (Task 7). |
| **Acceptance Criteria** | `python -m py_compile` passes in the container; `GET /skills/subclasses` → every passive `implemented=true`. |

### Task 2 — battle-service: `passives.py` wave-2 hooks + `buffs.py` optional kwargs
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/battle-service/app/passives.py`, `services/battle-service/app/buffs.py` (only the 3 signatures of §3.3) |
| **Depends On** | — |
| **Description** | §3.1 constants, `IMPLEMENTED_PASSIVES` = 21, hooks H14–H25 + filled H6 + extended H13 exactly per §3.0 (E3–E19) and §3.2, event/contribution builders per §3.5. Rules: no import of `buffs`/`battle_engine`; only `pick` rolls, only for owners; never raise on old/garbage state; `heal` clamps to max and skips dead; `absorb` order E4; `retaliate` never recurses and runs the attacker's vow; Paladin cleanse pick = last enemy-owned non-hard-control row; Bard/Etheriad return raw StatModifier rows + source tuples (main applies them). `buffs.py`: `absorb_fn`/`overheal_fn` kwargs per §3.3 with `None` defaults = byte-identical; stored per-dose magnitude never altered by absorb; `overheal_fn` before `_tick_resource`'s early return. Update both module docstrings. No `main.py` edits. |
| **Acceptance Criteria** | `py_compile` passes. Existing `test_passives_wave1.py`, `test_subclass_passives.py` (except the 7-unimplemented contract test Task 6 rewrites), `test_item_effects.py` and all buffs-based suites stay green. `passives` imports neither `buffs` nor `battle_engine`. |

### Task 3 — battle-service: `main.py` wiring + payloads + docs
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/battle-service/app/main.py` (`_pay_skill_costs`, the 6 runtime builders, `handle_expired_turn`, `_make_action_core`), `docs/services/battle-service.md`, `docs/SUBCLASS-PASSIVES.md`, `docs/ISSUES.md` (only if new issues found) |
| **Depends On** | 2 |
| **Description** | §3.4 steps 1–15: Necromancer payment + `hp_paid` + `blood_price` contribution; `shield` in all 6 payload builders; drop-out `on_deaths`; `_absorb_fn`/`_flush_absorbs`/`_overheal_fn` closures; `_apply_effects` wrapper over every non-enemy `apply_new_effects` site + same kwargs/flush/vow in `_land_enemy_effects`; potion `on_heal`; `allow_redirect` + `_plain_ctx`; `_strike` order E7 with `redirect_from` and 3-tuple return at all 3 call sites; redirect strikes in the skill and item loops (effects-only buffs, attrs without H5); dead-actor stop (E10); `end_of_action` after `resource_spend`; DoT tick with callbacks + vow sweep; `tick_shields` after `decrement_durations`; `on_deaths` at 9.5; rage comment. No random calls for passives in main.py. Docs: battle-service.md (hooks H14–H25, `passive_state` keys, shield model, `_strike` order, log contract §3.5, `shield` payload field); SUBCLASS-PASSIVES.md: opory 2/3/5 ✅, plan steps 4/5 ✅ (wave 2 = FEAT-190), all 21 ✅; ISSUES.md: note the pre-existing "ally buff counts as debuff for antidotes" if not listed. |
| **Acceptance Criteria** | `py_compile` passes. Full battle-service suite green (excluding contract tests Task 6 rewrites). Battle without passive owners → events identical to before. Manual smoke in the container: one action per new passive owner resolves without exception; `GET /battles/{id}/state` shows `shield`. |

### Task 4 — frontend: shields, log lines, Necromancer cost
| Field | Value |
|---|---|
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `src/utils/passiveCosts.ts`, `src/components/pages/BattlePage/Arena3D/hud/SkillHand.tsx`, `src/components/pages/BattlePage/SkillPicker/SkillPicker.tsx`, `src/components/pages/BattlePage/CharacterSide/CharacterSide.tsx`, `src/components/pages/BattlePage/Arena3D/FighterCard.tsx`, `src/components/pages/BattlePage/Arena3D/arenaTypes.ts`, `src/components/pages/BattlePage/BattlePage.tsx`, `src/components/pages/BattlePage/battleTypes.ts`, `src/components/pages/BattlePage/BattlePageBar/useBattleBar.tsx`; verify `Arena3D/hud/ArenaHud.tsx` |
| **Depends On** | — (contract §3.5 fixed; live check after Task 3) |
| **Description** | Per §3.6: blood-price util with the exact table; 2D/3D skill cards show `+N HP` and don't block a payable skill, block an unpayable one with a Russian hint («Не хватает маны и здоровья»); `shield` from runtime into 2D overlay chip (CharacterSide only — NOT `PlayerCard.jsx`/`CharacterResourcesList.jsx`/SCSS) and the 3D HP orb; all new event fields/kinds rendered in `formatBattleEvent`; old logs unchanged; unknown kinds render nothing. |
| **Acceptance Criteria** | Read `docs/DESIGN-SYSTEM.md` first. No `React.FC`, no SCSS, no `.jsx` logic, Tailwind + tokens, 360px OK. `npx tsc --noEmit` + `npm run build` pass in Docker. Blood table from §3.6 verified. |

### Task 5 — QA: `passives.py` wave-2 unit tests
| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | new `services/battle-service/app/tests/test_passives_wave2.py` |
| **Depends On** | 2 |
| **Description** | Pure tests with the real module, `pick` patched both ways. **Shields**: stacking, absorb order (timed shortest first, then permanent), partial/total absorb, empty entries removed, `shield_total` rounding, old state → 0; tide top-up to cap, turns reset, `tick_shields` (fresh skip, only owner's turn, drop at 0); `add_shield` cap. **Vow**: 31%→29% triggers once, second time not; 40%→0 no trigger; shield 20% max; cleanse picks the **last** enemy-owned row, never Stun/Poison-paralysis, own buffs/old rows untouched, nothing to remove → shield only. **Lifesteal**: Berserk only below 25% (24.9 yes / 25 no), 15%; Priest 10% / `sainting` 15%; capped at max HP; dead attacker → none; returns None when healed 0. **Retaliate**: 15% of `taken` incl. absorbed part, excluding overkill; attacker shield absorbs; can kill; no recursion (Guardian vs Guardian → exactly one reflect event); same team → nothing; attacker-Paladin vow event. **Blood price**: table (cost, mana, hp → hp_cost, affordable): (10,0,16→15 ✓), (10,0,15.9 ✗), (3,2,10→2 ✓), (1,0,2 ✗), non-Necro → None, enough mana → None, dead → waived. **on_kills**: Necro heal 10% per victim, capped, dead Necro nothing, Saber unchanged. **on_heal**: overflow → tide only for Auromancer healer, cap 20% target max, dead target nothing. **end_of_action**: Bard group (+3, cap 4, rows to self+allies), solo (+5, cap 3), group→solo clamp, skipped turn refresh without stack; Etheriad priority 1/2/3 incl. tie-break, enemy already cursed skipped, no allies → self, skipped → nothing. **on_deaths**: Bard/Etheriad rows and shields of the dead owner removed everywhere, others untouched, `inspiration_end`. **Redirect**: Trickster target only, candidates exclude attacker and dead allies, none → None. **buffs kwargs (REAL buffs)**: defaults byte-identical (same state/events with and without `None`); DoT absorbed fully/partially; HoT overheal reported incl. full-HP early-return case; stored dose magnitude unchanged after partial absorb over 2 doses. Guards: passives imports neither module; no roll for non-owners; garbage values never raise. |
| **Acceptance Criteria** | All pass in the container; each passive ≥1 positive and ≥1 negative case; no flaky results over 20 runs. |

### Task 6 — QA: integration through `_make_action_core` + payloads + contract tests
| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE (1 bug found: `GET /preview` drops `shield` — `BattlePreviewParticipant` lacks the field; failing repro `test_passives_wave2_integration.py::TestShieldInRuntimePayloads::test_preview_response_reaches_the_client_with_the_shield`). **Fixed** (Backend Dev, post-QA): `shield: int = 0` added to `BattlePreviewParticipant`; dead-attacker leftover fixed per PM rule (step 9 runs only for a living actor — no 9.0–9.0e rows / damage / H2; weapon-coating effects, Agent re-roll and item weapon-coating also guarded by `_actor_alive()`; costs/cooldowns still charged) — test renamed to `TestDeadAttackerLeftover::test_dead_attacker_lands_no_attack_effects`; redirected blows no longer carry `aoe_falloff` (only genuine AoE falloff is tagged). Suite: 1654 passed, 0 failed. |
| **Files** | new `services/battle-service/app/tests/test_passives_wave2_integration.py`; update `test_subclass_passives.py` (:301-315), `test_passives_wave1_integration.py` (:19-20, :375-395 — the "7 not implemented do nothing" tests are inverted/removed); extend `test_join_requests.py` / `test_pvp_attack.py` / `test_pvp_invitations.py` only where they pin runtime payload shapes |
| **Depends On** | 3 |
| **Description** | Through the real `/battles/{id}/action` harness (REAL buffs, real engine, forced `pick`/`roll_pct`): (a) contract: registry `implemented` set == `IMPLEMENTED_PASSIVES` == 21. (b) `_strike` order: shield absorbs before HP, event `absorbed`/`shield_left`; Paladin vow mid-AoE protects against the next entry; lifesteal from `hp_removed` only (no heal from absorbed part), then reflect; Berserk at low HP hitting a Guardian heals then takes the reflect; reflect kills the attacker mid-AoE → remaining targets untouched, no extra hit, `participant_defeated` for the attacker, not a kill; reflect into attacker shield; Guardian vs Guardian single reflect; extra hit (Mechanic splash) lifesteals/reflects; scroll lifesteals. (c) DoT/effect damage absorbed by shields + `shield_absorb` proc, no lifesteal/reflect from DoT, vow from DoT. (d) Necromancer: payable with HP (`hp_paid`, contribution, mana 0), 1 HP + 0 mana → 400 Russian and Redis state unchanged, kill heal at 9.5. (e) Bard stacks across turns, group/solo, removal on Bard death and on drop-out (`handle_expired_turn`); Etheriad priorities end-to-end; damage buffs from the rows actually raise damage. (f) Auromancer overheal → shield for skill heal, HoT tick and potion; cap; expiry after 3 Auromancer turns; vanishes on his death. (g) Redirect: ally takes 50% with no dodge/passives (no attacker contributions, no ally reflect even if Guardian, no vow), ally shield absorbs; no ally → old miss only; extra hit never redirects. (h) `shield` present in all 6 runtime builders. (i) Old-state attack (no `passive_state`, Guardian/Paladin keys) resolves. (j) Regression: battle with no passive owners → identical events. |
| **Acceptance Criteria** | Full battle-service suite green in the container; no test passes via a swallowed exception; new files stable over 20 runs. |

### Task 7 — QA: skills-service registry tests
| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | `services/skills-service/app/tests/test_character_subclass_internal.py` (:16, :85-110, :402-410) |
| **Depends On** | 1 |
| **Description** | All 21 implemented (no not-implemented set); Berserk description mentions lifesteal below 25%; Trickster mentions the redirect to the attacker's ally at 50%; Necromancer says heal 10%. |
| **Acceptance Criteria** | skills-service suite green in the container. |

### Task 8 — Review
| Field | Value |
|---|---|
| **Agent** | Reviewer |
| **Status** | DONE (Review #1 — PASS) |
| **Files** | all of the above |
| **Depends On** | 1, 2, 3, 4, 5, 6, 7 |
| **Description** | Per `agents/reviewer.md`: E1–E22 honoured (logic and rolls only in `passives.py`; buffs kwargs default-identical; `_strike` order E7/E8; no reflect recursion; shields absorb DoT; vow once; cleanse never hard control; dead-owner cleanup at 9.5 and drop-out; `shield` in all 6 builders; `.get` on new keys), frontend rules (TS, Tailwind, no `React.FC`, design system, Russian, 360px, no JSX/SCSS edits), docs + ISSUES. Re-run `py_compile`, both pytest suites, `tsc --noEmit`, `npm run build` inside Docker. **Live** (local test creds / dungeon polygon memory): group battle with a Guardian and a Paladin vs a hard hitter — shield chip in 2D and on the 3D HP orb, «Священный обет» and «Возмездие» lines in the 2D log and 3D Chronicle, reflect animates; Priest/Berserk lifesteal lines; Necromancer card shows `+N HP` and the turn pays HP (`Плата кровью`); Bard «Вдохновение» circles on allies, gone after the Bard dies; Etheriad line; Auromancer overheal → shield; Trickster redirect hits the attacker's ally; badges no longer show «пока не действует в бою»; zero console errors. |
| **Acceptance Criteria** | All checks green, live verification recorded; PASS/FAIL in §5. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-11-01 — **PASS**

#### Scope reviewed
FEAT-190 only (FEAT-188/189 already PASSed): battle-service `passives.py` (wave-2 section H14–H25, H6, H13 Necro branch,
`land_hit`), `buffs.py` (3 optional kwargs), `main.py` (`_pay_skill_costs`, 6 runtime builders, `handle_expired_turn`,
`_make_action_core` closures/wrappers, `_strike`, skill/item loops, `_finish_passive_attack`, end-of-action, 9.4a/9.4/9.5),
`schemas.py` (`BattlePreviewParticipant.shield`); skills-service `subclasses.py`; frontend `passiveCosts.ts`, `SkillPicker.tsx`,
`SkillHand.tsx`, `ResolvedSkillCard.tsx`, `InventoryItem.tsx`, `CharacterSide.tsx`, `FighterCard.tsx`, `arenaTypes.ts`,
`battleTypes.ts`, `BattlePage.tsx`, `useBattleBar.tsx`; the new/extended test files; docs.

#### Code review vs §1 / §3
| Item | Verdict |
|---|---|
| `_strike` order (E7/E8) | OK — `passives.land_hit`: shield absorb → `hp -= remaining` (unclamped, same number object when nothing absorbed) → `hp_removed` excludes overkill → target vow → lifesteal → reflect from `absorbed + hp_removed`. `direct = actx is not None and redirect_from is None`, so redirected blows / non-enemy item rows get shields only. |
| Shields everywhere incl. DoT (E5) | OK — strikes (`land_hit`), reflect (`retaliate` → `absorb`), enemy instant HP rows and non-enemy rows (`_apply_with_passives` passes `absorb_fn`), DoT ticks and negative HP doses (`tick_periodic_effects` / `_tick_resource`). Necro HP payment and drop-out `hp = 0` bypass shields. Absorb order timed-shortest → permanent; a dead holder never absorbs; `on_deaths` clears shields on / owned by the dead. |
| Vow (E12) | OK — `0 < hp < 30%`, `vow_used` once, 20% permanent shield, cleanse = last row owned by another team and not hard control; checked after strikes, reflect (attacker side), both effect wrappers and the DoT sweep. |
| Lifesteal / «Вера» (E11) | OK — only direct enemy strikes incl. extra hits/scrolls, from `hp_removed` only, Berserk threshold read before the heal, Priest 15% on `sainting`, `heal` clamps to max and skips the dead; reflect never lifesteals. |
| Reflect (E9) | OK — `retaliate` never re-enters `land_hit` (no recursion by construction), same team / self excluded, dead attacker skipped, can kill, attacker vow, stats `round(R)` on both sides; fires even if the Guardian died (Q6). |
| Necromancer (E13) | OK — `blood_price` after H12, before any deduction; `ceil(shortfall × 1.5)` with `hp − cost ≥ 1`; Russian 400 with both numbers; waived when already dead (Q7); `hp_paid` + `blood_price` contribution; kill heal 10% max at 9.5 (max HP unchanged). Frontend `bloodPriceHp` / `canPayMana` mirror the formula and the §3.6 table. |
| Bard / Etheriad (E14–E17) | OK — rows applied by main with a `("passive", key)` source (refresh in place), after `resource_spend` and only for a living actor; Bard group/solo decided per action, clamp on mode change, skipped turn refreshes; Etheriad ward → curse (landed, uncursed) → might, silent when skipped; `on_deaths` at 9.5 and in `handle_expired_turn` removes Bard/Etheriad rows and shields of the dead + `inspiration_end`. |
| Auromancer tide (E18) | OK — `overheal_fn` on every positive HP dose in `apply_new_effects` (all non-enemy apply sites go through `_apply_effects`) and in `_tick_resource` before the early return; potion path calls `on_heal` after the clamp; one entry per (target, Auromancer), cap 20% of the target's max, 3 owner turns via `tick_shields` right after `decrement_durations`. |
| Trickster redirect (E19) | OK — `deceit_redirect_target` picks among living attacker teammates (excl. attacker / Trickster), rolls only for a Trickster target; extra hits pass `allow_redirect=False`; skill and item loops strike the ally with ×0.5, `_plain_ctx` (no H4/H5/dodge/deceit), effects-only buffs copied before rage/H2, attrs without H5, `actx=None`; no `aoe_falloff` tag; coating not applied to redirect targets. |
| Dead attacker (E10) + dev's extra guards | OK — `_actor_alive()` before every strike in both loops, before the extra hit, before step 9 entirely, before weapon-coating effects, the Agent re-roll and the item weapon coating; costs/cooldowns still charged. H9 (`finish_attack`, on-hit stacks, `main.py:3247`) still runs after the attacker's death — **acceptable**: it only records consequences of hits that already landed (no new damage, rolls or effects on others), consistent with E10 "non-strike steps run as before". |
| `buffs` kwargs default | OK — with `absorb_fn` / `overheal_fn` = None the executed path is the old one (`delta = magnitude`; the previously discarded `_change_resource` result is only stored). |
| Passive-less behaviour | OK — `absorb` / `land_hit` return the caller's own number objects, no procs, `on_heal` returns `[]` for non-Auromancers; pinned by the "no passive owners → identical events" regression tests; pre-existing suites unchanged and green. |
| Old Redis states | OK — `_ps_read` / `.get` everywhere, `shield_total` 0 for absent keys, `pstate` lazy; tested with states lacking `passive_state`. |
| Log contract | OK — backend fields/kinds match §3.5 and `useBattleBar.tsx` renders every one (`absorbed`, `shield_left`, `reflected`, `redirected` / `deceived_by`, `hp_paid`, contributions `lifesteal` / `reflect` / `redirect` / `blood_price`, procs `vow` / `tide` / `shield_absorb` / `kill_heal` / `inspiration` / `inspiration_end` / `spirit_whisper`); unknown kinds render nothing. `shield` in all 6 runtime payloads + preview schema. |
| skills-service | OK — all 21 `implemented=True`; Berserk / Trickster / Necromancer descriptions per §3.7 (also live: `GET /skills/subclasses` → 21, 0 not implemented). |
| Frontend rules | OK — touched files are `.tsx` / `.ts`, Tailwind + tokens (`site-blue`, `stat-hp`, `site-red`, `gold-text`), no `React.FC`, no `.jsx` / SCSS edits, Russian strings, chips absolutely positioned (no layout shift). |
| 2D SkillPicker now blocks unaffordable skills for all classes | **Acceptable.** It matches the 3D hand (blocking since FEAT-189), the server rejects the same action with a 400 anyway, and the reason is shown on the row («Не хватает маны / энергии», Necro «…маны и здоровья»). Caveat (LOW, same semantics as 3D): the per-card check uses the current bars only, so a combo where a same-turn support skill restores the mana for the attack is blocked client-side; rare, no change needed now. |

#### Automated Check Results
- [x] `py_compile` — battle-service `main.py`, `passives.py`, `buffs.py`, `schemas.py`, `battle_engine.py`, `redis_state.py`, `skills_client.py`; skills-service `subclasses.py`, `crud.py`, `main.py`, `schemas.py` — PASS
- [x] battle-service pytest (python:3.10-slim, `--asyncio-mode=auto`) — PASS, **1654 passed**
- [x] skills-service pytest (`--asyncio-mode=auto`) — PASS, **396 passed**
- [x] `npx tsc --noEmit` (frontend container) — PASS
- [x] `vite build` to /tmp (cleaned up) — PASS (only the usual chunk-size warning)
- [x] `docker compose config` — PASS
- [x] Live verification — PASS (below)

#### Live Verification Results (localhost only; battle-service + skills-service restarted, nginx reloaded)
Setup (all restored, see §6): `tree_nodes` 28 → `mage_necromancer`, 50 → `rogue_bard`; progress 105 (Ашари 763) → node 28,
106 (Аэлис 761) → 86 Guardian, later 84 Paladin; new row 108 (Годрик 764 → node 50). HP / mana / cooldowns / `passive_key`
edited only inside the Redis state of the test battles (763 switched to `priest_faith` in battle 320 for the lifesteal check).
Battles 319 (763 Necro + 764 Bard vs 761 Guardian), 320 (763 vs 761 Paladin), 321 (same, for the 390 px check) — 319/320
ended by kills, 321 admin force-finished.
1. **Shield 2D + 3D, absorb line** — 320: a 1099 hit → «Аэлис Священный обет — щит 2000» right after the damage line; next
   hit `absorbed:1374, shield_left:626` → 2D log «Ашари → Аэлис −1374 крит (щит поглотил 1374)», 2D chip «Щит 626» under the
   passive badge, 3D HP-orb seal «626», 3D Chronicle the same line. Last hit «(щит поглотил 626)» → shield gone. PASS.
2. **Guardian** — 319: «Аэлис — Возмездие: Ашари −165» (1099 × 15%), «… Годрик −5»; a reflect (−248) killed the 10-HP
   Necromancer mid-action → surcharge waived (no `hp_paid`), `participant_defeated`, battle over. PASS.
3. **Priest «Вера»** — 320: `lifesteal` 110 on a 1099 hit, log «· Вера +110 HP»; the fully absorbed hit gave no lifesteal
   (correct: nothing removed from HP). PASS.
4. **Necromancer** — 2D picker with mana 5: «Энергетический луч» 15 → «+15 HP», not blocked; cast → mana 0, HP 827.23 →
   812.23, log «Расход: 5 маны · Плата кровью −15 HP». With HP 10 / mana 0 the row is greyed «Не хватает маны и здоровья»
   and the API answers 400 «Недостаточно маны: нужно 15, есть 0. Доплатить здоровьем нельзя: нужно 23 HP, есть 10 (должно
   остаться хотя бы 1)». Kill → `kill_heal` 150, Chronicle «Ашари Плата кровью +150 HP за убийство Аэлис». PASS.
5. **Bard** (real group battle 319) — `inspiration` stacks 1 → 2, mode group, targets [Bard, Ашари], `buff_pct 3.0` on the
   next Bard hit; 2D log «Годрик Ритм — Вдохновение ×2 (+6% урона)»; Bard killed → «Годрик Ритм — Вдохновение угасло»
   (`inspiration_end` targets [727, 728]). PASS.
6. **Profile / skill tree** — no «пока не действует в бою» on `/profile` (badge «Плата кровью») or `/skill-tree`. PASS.
7. **390×844 iframe** (battle 321, 2D) — the «Щит 901» chip fits inside the card corner, «(щит поглотил 1099)» wraps inside
   the log panel. PASS. (The two 2D participant cards overlapping at 390 px is pre-existing layout — no class changes in
   `BattlePage.tsx`; general T5 item.)
Console: zero errors. Network: no app 4xx/5xx — only my deliberate 400 probe on battle 320.
Not exercised live (covered by `test_passives_wave2_integration.py`): Etheriad, Auromancer tide, Trickster redirect.

#### Non-blocking notes (no re-review needed)
1. LOW — `services/battle-service/app/main.py:3196`: a redirected «Обман» blow is added to the attacker's
   `total_damage_dealt` (damage to his own ally). Harmless today; if cumulative stats ever reward damage dealt, skip it when
   `redirect_from` is set. Backend Developer, optional.
2. LOW — `SkillPicker.tsx:243` / `SkillHand.tsx` per-card affordability ignores same-turn mana restoration (see table). Optional.
3. Pre-existing, not FEAT-190: the generic fallback renders `battle_finished` as an unnamed «совершает действие» line in the
   2D log and the Chronicle (`useBattleBar.tsx:~1240`).


---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-11-01 — PM: фича создана (волна 2 пассивок, новые механики), запускаю анализ
[LOG] 2026-11-01 — Codebase Analyst: анализ завершён — точки HP-урона (_strike + DoT/эффекты в buffs), лечения, длительностей, оплаты маны, убийств, «Обмана» и фронта описаны в §2; щитов в движке нет, нужны решения по DoT/порядку щит-отражение-вампиризм
[LOG] 2026-11-01 — Architect: спроектировано (§3 E1–E22, хуки H14–H25, контракт лога), 8 задач; щиты в passive_state, в buffs только необязательные absorb_fn/overheal_fn; порядок в _strike: щит → HP → обет → вампиризм → отражение; 7 вопросов к PM необязательные (значения по умолчанию заданы)
[LOG] 2026-11-01 — Backend Developer: задача 1 готова — в реестре skills-service все 21 пассивка implemented=True; описания: Берсерк (+вампиризм 15% ниже 25% HP), Фокусник (перенаправление в союзника атакующего 50%), Некромант (за убийство лечение 10% макс. HP), Паладин/Бард/Эфириад/Ауромант сверены с §1/§3; обновлены докстринг и docs/services/skills-service.md; py_compile OK
[LOG] 2026-11-01 — QA Test: задача 7 готова — тесты реестра skills-service: все 21 пассивка implemented (не-реализованных нет), тест «у Берсерка нет вампиризма» перевёрнут (вампиризм 15% ниже 25%), Фокусник — перенаправление в союзника атакующего 50%, новые проверки описаний Некроманта (лечение 10%, не рост макс. HP), Паладина (самый свежий эффект), «Если союзников нет» у Барда/Эфириада/Ауроманта и цифр волны 2; весь набор skills-service в контейнере — 396 passed
[LOG] 2026-11-01 — Frontend Developer: задача 4 готова — щит на карточке 2D (плашка «Щит N» в CharacterSide) и на сфере HP в 3D; в логе (2D и Хроника 3D) поглощение щитом, «Возмездие», удар через «Обман» в союзника, вампиризм «Веры»/«Ярости», «Плата кровью» в расходе и за убийство, «Священный обет», «Прилив», «Вдохновение», «Шёпот духов»; Некромант: карточки 2D/3D, полная карточка навыка и подсказка слота показывают «+N HP», неоплатный навык блокируется («Не хватает маны и здоровья»); таблица формулы сверена; tsc и vite build проходят
[LOG] 2026-11-01 — Backend Developer: задача 2 готова — passives.py: 7 новых ключей, IMPLEMENTED_PASSIVES = 21, константы §3.1; хуки щитов (shield_total/absorb/add_shield/tick_shields, порядок: срочные короче → вечные), heal, on_heal («Прилив»), check_vow/snapshot_hp/check_vows (обет + снятие последнего вражеского некритичного эффекта), lifesteal (Берсерк <25% / «Вера» 10–15%), retaliate (без рекурсии, щит атакующего, обет атакующего), land_hit — фиксированный порядок E7 для _strike (щит → HP → обет → вампиризм → отражение), blood_price/blood_hp_cost, end_of_action (Бард, Эфириад), on_deaths, заполнен deceit_redirect_target + redirect_contribution, on_kills с лечением Некроманта; buffs.py: необязательные absorb_fn/overheal_fn (по умолчанию поведение прежнее). py_compile OK; набор battle-service: 1333 passed, 5 failed — все 5 закрепляют старое «7 пассивок не реализованы» / «seam возвращает None» (переписывает задача 6)
[LOG] 2026-11-01 — QA Test: задача 5 готова — новый tests/test_passives_wave2.py (239 тестов, настоящие passives и buffs под приватными именами, main не импортируется): щиты (сумма/округление, порядок поглощения срочные→вечные, мёртвый держатель, пополнение до потолка, сброс ходов, тик только в ход владельца, Ауромант 3 хода, Паладин вечный), обет (0<HP<30%, один раз, 20%, снятие последнего вражеского эффекта, оглушение/паралич никогда), вампиризм (Берсерк <25% 15%, Жрец 10/15%, только снятое с HP, потолок), отражение (15% от поглощённого+снятого, без оверкилла, щит атакующего, может убить, обет атакующего, без рекурсии), land_hit (порядок E7, direct=False), «Прилив», «Плата кровью» (таблица §3.6, мёртвый — без оплаты), лечение Некроманта за убийство, Бард/Эфириад (приоритеты, соло/группа, оглушённый ход), on_deaths, перенаправление «Обмана», колбэки buffs absorb_fn/overheal_fn (по умолчанию побайтово то же, доза не уменьшается щитом, overheal до раннего выхода), нейтральные участники без бросков и без passive_state, мусор не роняет. Мутационная проверка: 8/8 мутантов пойманы. Весь набор battle-service: 1572 passed, 5 failed — те же 5 закреплений FEAT-189 (задача 6); новый файл 10 прогонов подряд — стабильно. Багов в коде не найдено
[LOG] 2026-11-01 — Backend Developer: задача 3 готова — main.py: «Плата кровью» в _pay_skill_costs (оплата HP, hp_paid + вклад blood_price в resource_spend, русская 400, мёртвому доплата не нужна); поле shield во всех 6 runtime-билдерах; _strike через passives.land_hit (щит → HP → обет → вампиризм → отражение), возвращает (урон, событие, post_events) во всех 3 местах; absorbed/shield_left на ударе; замыкания _absorb_fn/_overheal_fn во всех наложениях эффектов (обёртки _apply_effects и _land_enemy_effects с проверкой обета) и в тике DoT, процы shield_absorb/tide/vow выводятся после своего события; зелье → «Прилив»; «Обман» бьёт союзника атакующего 50% (чистый контекст, без уклонения и пассивок, баффы без «Ярости»/H2, доп. удары не перенаправляются); убитый отражением атакующий больше не бьёт; end_of_action (Бард/Эфириад) после resource_spend; tick_shields после decrement_durations; on_deaths на 9.5 и при выбывании по таймауту; комментарий «Ярости» обновлён. Документы: battle-service.md (раздел FEAT-190), SUBCLASS-PASSIVES.md (все опоры и 21 пассивка ✅), ISSUES.md (союзный баф снимается антидотом как дебаф). py_compile OK; набор battle-service 1572 passed, 5 failed (те же закрепления FEAT-189, задача 6); смоук всех новых пассивок через реальный /action — без ошибок; battle-service перезапущен и стартует
[LOG] 2026-11-01 — QA Test: задача 6 готова — переписаны 5 закреплений FEAT-189 (21 реализована = реестр skills-service; «Обман» возвращает живого союзника атакующего; класс «7 не реализованы» заменён проверкой «не реализованных нет»; заодно priest_faith убран из теста «неизвестный ключ инертен»). Новый tests/test_passives_wave2_integration.py (76 тестов через настоящий /action): щиты на ударах, свитках, строках предметов, доп. ударах, DoT и дозах HP; поле shield во всех 6 выдачах + WS-публикация; обет Паладина (удар, DoT, урон эффектом, 40%→0, один раз, снятие свежего вражеского эффекта); «Прилив» (навык, союзник с потолком, HoT, зелье, 3 его хода, гибель Ауроманта); «Возмездие» (щит атакующего, свой щит, двое Хранителей, смерть посреди AoE без доп. удара, доп. удар, DoT нет, оверкилл); вампиризм до отражения (Берсерк с 5 HP выживает), «Вера» 10/15%; «Плата кровью» (hp_paid, граница 1 HP, русская 400 без сохранения, мёртвый не платит, лечение за убийство); Бард (стаки, соло/группа, урон растёт, снятие при смерти и при выбывании по таймауту); Эфириад (проклятие ударенного врага, стойкость, сила, оглушение); «Обман» (×0.5, без уклонения и пассивок, щит союзника, без союзника — промах, доп. удары не перенаправляются, свиток, союзник убит — не убийство); порядок отложенных процов; бой без пассивок побайтово как прежде. Мутационная проверка: 12/12 мутантов пойманы. Найден баг: GET /battles/{id}/preview теряет shield — в схеме BattlePreviewParticipant нет поля (тест падает, ждёт фикса). Остаток от разработчика: убитый отражением в шаге свитка всё ещё накладывает эффекты атакующего навыка — задокументировано тестом, считаю багом (низкий/средний), решение за PM
[LOG] 2026-11-01 — Backend Developer: баг QA исправлен — в схеме BattlePreviewParticipant добавлено поле shield (int, по умолчанию 0), GET /battles/{id}/preview теперь отдаёт щит; тест-репро проходит
[LOG] 2026-11-01 — Backend Developer: по решению PM убитый отражением больше ничего не делает — шаг 9 (атакующий навык) выполняется только для живого: ни эффектов 9.0–9.0e, ни урона, ни H2; также для мёртвого не накладываются эффекты яда с оружия, перебросы Агента и яд на оружие из предмета; стоимость и кулдауны списываются как прежде. Тест TestDeadAttackerLeftover перевёрнут (test_dead_attacker_lands_no_attack_effects); бой без пассивок не затронут
[LOG] 2026-11-01 — Backend Developer: косметика — у перенаправленного «Обманом» удара больше нет поля aoe_falloff (×0.5 — не затухание AoE), добавлена проверка в тест; docs/services/battle-service.md обновлён. py_compile OK; весь набор battle-service в контейнере — 1654 passed, 0 failed
[LOG] 2026-11-01 — Reviewer: Review #1 — автопроверки: py_compile OK, battle-service 1654 passed, skills-service 396 passed, tsc --noEmit и vite build OK, docker compose config OK
[LOG] 2026-11-01 — Reviewer: живая проверка на localhost (бои 319–321): «Священный обет — щит 2000», «(щит поглотил N)» в логе, плашка «Щит N» в 2D и печать на сфере HP в 3D; «Возмездие −165»; «Вера +110 HP»; Некромант — «+15 HP» на карточке, «Плата кровью −15 HP», русская 400 при нехватке HP, «+150 HP за убийство»; Бард «Вдохновение ×2 (+6% урона)» и «Вдохновение угасло» после гибели; на профиле и в древе нет «пока не действует»; 390 px — плашка и лог помещаются; ошибок в консоли нет
[LOG] 2026-11-01 — Reviewer: тестовые правки откатаны — subclass_key узлов 28 и 50 снова NULL, прогресс 105 (763) снова узел 25, 106 (761) снова узел 88, строка 108 (764) удалена, HP/мана/энергия/выносливость 761/763/764 возвращены, current_character пользователя 4 = 763; бои 319–321 завершены
[LOG] 2026-11-01 — Reviewer: Review #1 — PASS (некритично: удар, перенаправленный «Обманом», идёт в статистику нанесённого урона атакующего; блокировка карточек в 2D по текущим полоскам — как в 3D). Задача 8 DONE, статус REVIEW
[LOG] 2026-11-01 — PM: два некритичных замечания ревью добавлены в ISSUES.md (LOW), фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Все 21 пассивка подклассов работают. Новые механики боя: щит (поглощает любой урон, включая периодический), вампиризм, отражение, оплата навыка здоровьем, бафы союзникам от пассивок, удар по своим от «Обмана».
- Пассивки волны 2: Паладин «Священный обет», Хранитель «Возмездие», Бард «Ритм», Некромант «Плата кровью», Эфириад «Шёпот духов» (умные духи), Ауромант «Прилив», Жрец «Вера»; доделаны вампиризм «Ярости» и перенаправление «Обмана».
- Фиксированный порядок удара: урон → щит → HP → обет → вампиризм → отражение (`passives.land_hit`). Атакующий, погибший от отражения, дальше ничего не делает.
- `buffs.py` получил необязательные `absorb_fn`/`overheal_fn` (по умолчанию — прежнее поведение); поле `shield` во всех 6 выдачах состояния боя и в предпросмотре.
- Фронт: щит в 2D (плашка) и 3D (печать на сфере HP), все новые строки лога, доплата HP Некроманта на карточках навыков.
- Тесты: battle-service 1654 passed, skills-service 396 passed; мутационные проверки (12 из 12 и 8 из 8) пойманы.

### Что изменилось от первоначального плана
- По итогам анализа PM уточнил правила (подтверждено пользователем): щит поглощает и периодический урон; вампиризм/отражение — только от прямых ударов; «+10% HP» Некроманта — лечение, а не рост максимума; удар по своим без уклонения и без пассивок.
- QA нашёл 2 бага (предпросмотр без щита; мёртвый атакующий накладывал эффекты) — исправлены до ревью. Ревью #1 — PASS.
- 2D-выбор навыков теперь, как и 3D, блокирует навыки, на которые не хватает маны/энергии (для всех классов).

### Оставшиеся риски / follow-up задачи
- LOW в ISSUES.md: урон «Обмана» по союзнику идёт в статистику атакующего; карточки навыков не учитывают ману, восстановленную в том же ходу; антидот снимает бафы союзников как дебафы.
- Эфириад, «Прилив» Ауроманта и перенаправление «Обмана» вживую не прогонялись — покрыты интеграционными тестами.
