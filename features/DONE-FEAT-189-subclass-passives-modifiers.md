# FEAT-189: Пассивки подклассов — волна 1 (на существующих механиках боя)

## Meta

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Created** | 2026-10-31 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-189-slug.md` → `DONE-FEAT-189-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание
Продолжение FEAT-188 (`features/DONE-FEAT-188-subclass-passives-foundation.md`): фундамент
готов — подкласс персонажа, загрузка `passive_key` в бой, реестр пассивок, значок в UI,
живая «Ярость» Берсерка. Теперь включаем пассивки, которые ложатся на **существующие**
механики боя (проценты урона, сопротивления, крит, уклонение, шансы эффектов, длительности,
мана, AoE/доп. урон). Источник истины по названиям и цифрам — `docs/SUBCLASS-PASSIVES.md`.

Пассивки этой волны (13 подклассов):

**Воин**
- **Инквизитор — Печать ереси.** Каждое попадание по врагу, который в этом бою применял
  магию: −3% к его сопротивлению магии, до 5 стаков (−15%), до конца боя. Минус работает и
  для союзников Инквизитора.
- **Сейбер — Охотник на чудовищ + Несгибаемость.** По мобам +15% урона; каждое убийство в
  данже — +2% урона до конца забега, максимум +10%. В PvP: каждый пропущенный удар — +2% ко
  всем сопротивлениям, максимум 3 стака (+6%).
- **Гладиатор — Арена.** За каждого врага сверх числа союзников: +8% урона и +4%
  сопротивлений, максимум 3. Если не в меньшинстве: +3% урона за каждый свой ход, максимум +15%.
- **Агент — Слабое место.** При крите: +20 п.п. к шансу наложить эффекты навыка; для
  оглушения/паралича — только +10 п.п.

**Плут**
- **Лансер — Пригвоздить.** Каждое попадание крадёт у цели 2% уклонения и 2 п.п. крита
  себе, до 5 стаков (±10), до конца боя; ниже нуля значения цели не уходят.
- **Механик — Шрапнель.** С шансом 30% удар задевает ещё одного случайного врага на 40%
  урона (свой бросок уклонения). Если других врагов нет: с шансом 30% — +35% урона той же цели.
- **Арчер — Первая кровь.** Первый удар по каждой цели в бою — гарантированный крит с +50% к
  крит. урону.
- **Ассасин — Из тени + Добивание.** После успешного уклонения следующая атака —
  гарантированный крит с +25% к крит. урону. По целям ниже 30% HP — +20% урона.
- **Фокусник — Обман (часть 1).** С шансом 10% атака по Фокуснику не проходит. Его дебафы
  держатся на 1 ход дольше (кроме оглушения/паралича). Перенаправление атаки в союзника
  атакующего — в FEAT-190 (пока атака просто не проходит).
- **Монах — Гармония.** +10 п.п. к шансу наложить контроль (оглушение/паралич — +5). Первый
  контроль на Монаха в бою не срабатывает.

**Маг**
- **Саламандр — Разгорание.** Каждый огненный удар подряд по одной цели — +6% урона, до 5
  стаков (+30%); сброс при смене цели или не-огненной атаке. Его ожоги — на 1 ход дольше.
- **Кастер — Чистая энергия.** Чистый магический урон (тип `magic`, не стихии) игнорирует
  25% сопротивления цели. Все навыки на 10% дешевле по мане.
- **Искромаг — Цепная молния.** Урон электричеством или ветром с шансом 25% перескакивает на
  другого врага на 50%. Если других врагов нет: с шансом 25% — повторный удар по той же цели на 40%.

### Бизнес-правила
- Цифры — константы в `battle-service/app/passives.py` (как «Ярость»), описания — в реестре
  skills-service; после включения пассивки ставится `implemented=True`, пометка «пока не
  действует в бою» пропадает сама.
- Длительность оглушения/паралича пассивки не увеличивают никогда.
- Решения PM по неоднозначностям (можно пересмотреть):
  - «Применял магию» (Инквизитор) = в этом бою использовал навык с не-физическим уроном
    (magic, fire, ice, watering, electricity, sainting, wind, damning).
  - «Режим дуэли» (Механик, Искромаг) = нет другого живого врага для перескока. **Режим
    определяется в момент каждого удара, а не на старте боя** (подтверждено пользователем):
    если бой начался 1×1, а потом вступил ещё один враг — перескок сразу начинает работать;
    если остался один враг — снова дуэльный вариант.
  - Гладиатор: бонус «Арены», если врагов больше, чем союзников (включая себя); иначе — разгон
    за ходы. Проверяется в момент удара по текущему числу живых. **Работает везде — и в PvP, и в
    боях с мобами (стаи)** (подтверждено пользователем).
  - Контроль (Монах) = оглушение, паралич, сбивание с ног, порыв ветра.
  - Стаки Сейбера за убийства живут в рамках забега в данж (между боями забега); вне данжа их нет.
- Пассивки фиксируются на старте боя, старые бои без ключей не падают.
- В логе боя видно, когда сработала пассивка (как «· Ярость +N%»).

### UX / Пользовательский сценарий
1. Игрок видит значок пассивки (уже есть из FEAT-188); у пассивок этой волны пропадает пометка
   «пока не действует в бою».
2. В бою срабатывания пассивок видны в логе (крит «Первой крови», стаки, перескок и т.д.).

### Edge Cases
- Цель умерла от основного удара — перескок Шрапнели/Цепной молнии идёт только по живым.
- Перескок не перескакивает повторно и не триггерит другие пассивки по цепочке бесконечно.
- Украсть больше, чем есть у цели, нельзя.
- Старые бои/состояния без новых полей — не падают.

### Вопросы к пользователю
- [x] Делать все оставшиеся пассивки → Да («делай дальше всё»), разбито на FEAT-189 и FEAT-190.
- [x] Сейбер, «мобы» → любые NPC-противники (`is_npc`).
- [x] Сейбер, «Несгибаемость» → во всех боях против игроков (тренировочные, смертельные, нападения без согласия).
- [x] Сейбер, убийства → считается и добивающий удар, и смерть от его периодических эффектов; бонус растёт сразу в том же бою.
- [x] Инквизитор → −3% ко ВСЕМ не-физическим сопротивлениям (магия и все стихии/святость/проклятье), а не только к `magic`.
- [x] Попадание → любой удар, от которого не уклонились и который не промахнулся, даже если сопротивления срезали урон до 0.
- [x] Шрапнель / Цепная молния → проверка один раз за атаку (не за каждую строку урона и не за каждую цель AoE).
- [x] Свитки/предметы → считаются наравне с навыками (магия для Инквизитора, «Первая кровь», «Из тени», «Обман» и т.д.), как у «Ярости».
- [x] Гладиатор → ход, пропущенный из-за оглушения/паралича, в разгон не засчитывается.
- [x] Кастер → скидка на ману видна и на карточках навыков (не блокировать навык, доступный со скидкой).

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

Line numbers refer to the current (uncommitted, post-FEAT-188) working tree.

### Affected Services
| Service | Type of change | Files |
|---|---|---|
| battle-service | all 13 passives: hooks in the action pipeline, per-battle passive state, log fields | `app/passives.py` (numbers + pure math), `app/main.py` (`_make_action_core`, `_filter_effects_by_chance`, `_pay_skill_costs`, `build_participant_info`/`_participant_payload`, maybe `_notify_dungeon_battle_end`), `app/redis_state.py` (only if new keys are seeded at init; `.get` defaults also work), `app/schemas.py` (only if `DungeonBattleCreate` is extended) |
| skills-service | flip `implemented=True` for 13 keys; Trickster description (redirect is FEAT-190) | `app/subclasses.py` |
| dungeon-service | only if Saber run-stacks are owned by the run (see §Dungeon) | `app/gameplay.py` (`_start_battle` ~1690-1740, `process_battle_callback` 1812), `app/http_clients.py:370`, `app/schemas.py:1315`, `app/models.py` (`DungeonSession`) |
| frontend | log rendering of new event kinds; optional Caster mana discount in skill cost UI | `BattlePageBar/useBattleBar.tsx` (`PASSIVE_LOG_NAMES` :116, `BattleEvent` :122, damage branch :685-744), `Arena3D/hud/ArenaHud.tsx:68-88` (hit/dodge/crit animation from damage events), optionally `Arena3D/hud/SkillHand.tsx:194-197`, `SkillPicker/SkillPicker.tsx:268` |
| autobattle-service | none required (see §autobattle) | — |
| DB / nginx / compose | none, unless Saber stacks are persisted in `dungeon_sessions` (Alembic in dungeon-service) | — |

### Action pipeline map (`battle-service/app/main.py::_make_action_core`, 2571-3796)
| Step | Where | Notes for passives |
|---|---|---|
| Battle row | 2583 `battle_record = await get_battle(...)` | `battle_record.battle_type` ∈ `pve / pvp_training / pvp_death / pvp_attack` (models.py:20). **Not in Redis state.** `get_battle` is patched to return `None` in the action-test harness → must be `None`-safe. |
| Turn owner | 2614 `battle_state["next_actor"]`; advance 3726-3747 over `turn_order` (skip dead) | No per-participant "own turn" counter exists; `turn_number` is global. A counter must be added (e.g. incremented once per `_make_action_core` call for the actor). Control-skipped turns also pass through `_make_action_core` (2681) — decide whether they count. Timeouts drop out (`participant_timed_out` 5941), not a turn. |
| Attacker stats | 2663 `base_attacker_attributes`; 3408 `attacker_attributes = apply_flat_modifiers(base, buff_mods)` | `critical_hit_chance`, `critical_damage` (×/100; default 125 ⇒ ×1.25), `dodge`, `luck` come from char-attrs `/attributes/internal/{id}` + flat effect mods (aliases `crit_chance`/`dodge_chance`/`crit_damage`, buffs.py:10). A copy of `attacker_attributes` with extra crit chance/crit damage changes the roll **without touching `compute_damage_with_rolls`**. |
| Control at turn start | 2678 `evaluate_control(active_effects[actor])` (buffs.py:229) | Stun / Poison+`paralysis` → whole action nulled (`control_skip`); Knockdown/Windburn with attribute `attack/defense/support` → that skill nulled (`control_block`). Enforcement only reads `active_effects` ⇒ blocking a control **at application** is enough for Monk. |
| Targets | 2742 `alive_enemies` (computed once per action), 2754 `defender_pid`, 2774 `alive_allies` | Gladiator counts come from these lists. They are not refreshed after kills inside the action. |
| Effect chance | `_filter_effects_by_chance(effects, luck_bonus, res_effects)` 181-207: `chance + luck*0.1 − target res_effects`, `roll_chance` per effect | Call sites: support enemy 2823, support all-enemies 2872, defense 2909/2957, item rows 3090, attack enemy **3329**, attack all-enemies 3380, weapon coating 3531. No per-effect bonus hook today → needs an optional param (e.g. per-row bonus callable / `bonus_pp`) or a wrapper. Raw rows here are DB rows (`effect_name`, `attribute_key`), not normalized; Knockdown/Windburn may carry `attribute_key="random"` (resolved only inside `apply_new_effects` 162-164) — `evaluate_control` would NOT classify such a raw row as control. Classify control by name (`stun`, `knockdown`, `windburn`, `poison`+`paralysis`). |
| Effect application | `apply_new_effects(state, pid, rows, is_enemy, owner_pid, source)` buffs.py:109 | `is_enemy=True` call sites: 2830, 2879, 2916, 2964, 3123 (items, `is_enemy_side`), **3336** (attack), 3387, 3538 (coating). Duration is read from the row (`duration`); +1 turn for Trickster/Salamander = bump `row["duration"]` before the call. Resource rows (hp/mana… with duration) are *doses* (161) — +1 means one extra dose. Effects tick on the **caster's** turn (`decrement_durations` 337, `fresh` flag skips the cast turn). |
| **Order inside the attack** | 9.0 self effects 3311 → **9.0b enemy effects applied BEFORE damage 3325-3343** → 9.0c-e ally/all → damage | Consequence: attack debuffs land **regardless of dodge** and **before crit is known**. Agent («при крите +20 п.п.») cannot ride the current roll — needs either a post-damage second roll for effects that failed, or moving effect application after damage (behaviour change for "resist-down affects this same hit"). Architect decision. |
| Attacker % damage | 3395-3406 `percent_damage_buffs = build_percent_damage_buffs(...)`, FEAT-188 rage added to `"all"` | Per-attack dict. Per-target bonuses (Saber vs mob, Assassin execute <30%, Gladiator, Salamander stacks vs this target, Mechanic duel +35%) need a **per-target copy** inside the target loop — no signature change. |
| Defender resists | primary 3412-3422 `build_percent_resist_buffs(mods, attrs)`; secondary targets `_ctx_for` 3437-3449; item path `_item_ctx_for` 3162-3176 | Dict `{type: pct, "all": pct}`; `resist_pct = all + type` inside the engine (battle_engine.py:182). Inquisitor (−3%/stack to target's magic resist), Gladiator/Saber (+% all resists on the passive owner when defending) = adjust the per-target dict copy → no signature change. 3 builders must get the same helper. |
| Dodge | rolled **once per target per attack** in the ctx (`roll_dodge(attrs["dodge"])` 3432 / 3447 / 3174), cached; `apply_dodge=False` passed to engine; one `dodged` event per target (3477-3484) | Lancer's dodge theft = subtract from `_tattrs["dodge"]` before `roll_dodge` (floor 0). Trickster «Обман» 10% = an extra roll in the same ctx builder (store e.g. `deceived`), emitted like a dodge but with its own marker. Assassin "after a successful dodge" = set a flag on the dodger where `_ctx["dodged"]` is true (both skill and item paths). |
| Damage roll | `compute_damage_with_rolls` battle_engine.py:112-191: base → `*(1+buff_pct)` → (dodge skipped) → hit roll `damage_entry["chance"] + luck` → crit roll `critical_hit_chance + luck`, `raw *= critical_damage/100` → resist → `max(0, …)` | Called per damage_entry × AoE target: skill 3485, item 3208. Log: `damage_type` (resolved; `"all"` → weapon primary type / physical), `base, entry, buff_pct, after_buffs, hit_chance_failed, critical, crit_mul, resist_pct, final`. |
| AoE | `resolve_aoe_targets(shape, primary, alive_enemies, falloff=50, max)` 111-141: `single/splash/cleave/all/random_n`; secondaries take `falloff%` (post-multiplied `dealt *= _tmult`, 3501-3503, log `aoe_falloff`) | Mechanic/Sparkmage extra hit can reuse the post-multiply pattern (another `compute_damage_with_rolls` call with `_tmult=0.4/0.5`) and `random.sample`-style target pick. |
| HP / kills | HP subtracted 3504 (skill), 3225 (item); DoT `tick_periodic_effects` 3631 (buffs.py:267, `source=eff_owner`); deaths marked 3665-3672 `participant_defeated` (**no killer recorded**) | Saber kill attribution needs the killer: compare hp before/after in the damage loops (and DoT ticks by `eff_owner` if DoT kills count). |
| Mana cost | `_pay_skill_costs` 583-609, called 3600 **after** damage; sums `cost_mana` of attack/defense/support ranks; logged as `resource_spend` 3620 | Caster −10% = scale `spend["mana"]` there (rounding rule needed — costs are ints). |
| Log | `turn_events` list (2672); returned in `ActionResponse`, WS publish 3763-3780, Celery `save_log.delay` 3785 → Mongo | Any dict keys pass through. |
| State save | `save_state(battle_id, battle_state)` 3749 (whole JSON, TTL 48h); finish path `_finalize_battle` 3703 | New per-participant keys persist automatically; no schema. |

### Which hooks need `compute_damage_with_rolls` changes
| Need | Without signature change | Needs new optional param |
|---|---|---|
| +% damage per attack / per target | yes — `percent_buffs` (per-target copy) | — |
| Extra crit chance (Lancer) | yes — `attacker_attr["critical_hit_chance"]` copy | — |
| Extra crit damage (Archer +50, Assassin +25) | yes — `attacker_attr["critical_damage"]` copy (+50 ⇒ ×1.75 from ×1.25) | — |
| Forced crit (Archer, Assassin) | only by hack (`critical_hit_chance` ≥ 100 − luck) | cleaner: `force_crit: bool = False` (log `forced_crit`) |
| Resist modifiers (Inquisitor, Gladiator, Saber) | yes — `percent_resists` copy | — |
| Caster ignores 25% of `magic` resist | possible (pre-scale positive `magic` + `"all"` parts of the dict copy when the entry type is `magic`; `"all"`-type entries resolve inside the engine) | cleaner: `resist_ignore_pct` / type-aware |
| Know whether the hit crit / landed | yes — returned `log["critical"]`, `log["hit_chance_failed"]`, `final` | — |
Note: the engine's own `roll_crit`/`roll_chance` are module-level in `battle_engine`; tests patch them via `patch.object(battle_engine, ...)`.

### Per-passive hook map
| Passive | Hook point(s) | Rides on | Per-battle state |
|---|---|---|---|
| Инквизитор `inquisitor_heresy_seal` | (a) mark caster as "used magic": attack-skill path 3466 when any `dmg["damage_type"]` (or resolved `log["damage_type"]`) ∉ physical set — `buffs._PHYSICAL_TYPES` (`physical, catting, crushing, piercing`) — and item scrolls 3182 if they count; (b) on Inquisitor's landed hit (not dodged, not `hit_chance_failed`) on a marked target → +1 stack on target; (c) every attacker's resist builders (3420/3446/3173) subtract `3×stacks` from target's `magic` resist | per-target resist dict | target: `used_magic: bool`, `heresy_stacks: int` (shared — benefits Inquisitor's allies) |
| Сейбер `saber_monster_hunter` | (a) +15% per target if target is a mob (per-target `percent_buffs` copy); (b) kill → +2% (cap 10) for the rest of the run; (c) PvP: Saber takes a landed hit → +2% all resists (cap 3) in its defender resist dict | per-target % buff; defender resist | target `is_npc`/mob flag (not in state today); Saber `saber_kill_stacks` (seeded at start from run), `saber_pvp_stacks` |
| Гладиатор `gladiator_arena` | at attack: `surplus = min(3, len(alive_enemies) − len(alive_allies))`; if >0 → +8%×surplus damage; when defending → +4%×surplus resists (defender's view: its own enemies vs allies); else ramp +3% per own turn (cap 15) | `percent_buffs["all"]`; defender resist dict | `own_turns` counter (new) |
| Агент `agent_weak_spot` | effect rolls for attack effects vs a target that took a crit: +20 pp (+10 for stun/paralysis) | `_filter_effects_by_chance` | none; **blocked by 9.0b ordering** (effects before damage) |
| Лансер `lancer_pin` | after landed hit: steal `min(2, target_dodge_now)` dodge and +2 pp crit, stacks ≤5; target ctx dodge (3432/3447/3174) minus stolen; attacker crit chance (3408 copy) plus stolen | flat attr copies | Lancer `lancer_stacks`, target `dodge_stolen` (sum, possibly per-thief); "below zero" needs target's current dodge at steal time (`_ctx["attrs"]["dodge"]`) |
| Механик `mechanic_shrapnel` | after a landed hit in the damage loop: 30% → extra `compute_damage_with_rolls` on a random other **alive** enemy at ×0.4 with its own dodge roll; no other enemy → 30% +35% on the same hit (per-target buff before the call) | AoE post-multiply pattern | none (per-attack guard flag against chaining) |
| Арчер `archer_first_blood` | per target, first hit in battle: forced crit + `critical_damage`+50 | attacker attr copy / `force_crit` | Archer `first_blood_done: [pid…]` |
| Ассасин `assassin_from_shadow` | (a) set `shadow_ready` on the Assassin when it dodges (ctx `dodged` for target=Assassin, skill + item paths); (b) Assassin's next attack: forced crit + `critical_damage`+25, consume flag; (c) target `hp < 30% max_hp` → +20% per target | per-target buffs, attr copy | `shadow_ready: bool` |
| Фокусник `trickster_deceit` (part 1) | (a) 10% "attack doesn't pass" — extra roll in ctx builders (3432/3447/3174) when target is the Trickster; (b) enemy-side effects he applies get `duration+1` except stun / poison-paralysis — at `is_enemy=True` call sites (list above) when `owner_pid` is the Trickster | ctx dodge cache; row duration | none |
| Монах `monk_harmony` | (a) +10 pp to control rows (+5 stun/paralysis) in `_filter_effects_by_chance` when the caster is Monk; (b) first control landing on Monk is dropped at `is_enemy=True` call sites (or one wrapper) + event | chance filter; apply sites | Monk `control_immunity_used: bool` |
| Саламандр `salamander_kindling` | per hit: if `log["damage_type"]=="fire"` and target == last fire target → stacks+1 (cap 5), +6%/stack; non-fire attack or other target → reset; Burn rows (`effect_name` "Burn") he applies `duration+1` | per-target % buff; row duration | `kindling_target`, `kindling_stacks` |
| Кастер `caster_pure_energy` | (a) `magic`-type entries: scale target's positive magic resist ×0.75; (b) `_pay_skill_costs` mana ×0.9 | resist dict / engine param; spend | none |
| Искромаг `sparkmage_chain_lightning` | per landed `electricity`/`wind` hit: 25% → extra hit ×0.5 on another alive enemy; no other enemy → 25% repeat hit ×0.4 on the same target | same as Mechanic | per-attack chain guard |

### Detection data available at action time
- **Mob / NPC:** Redis participant state has **no `is_npc`**. Sources: `characters.is_npc` (raw SQL; used at 871, 639), `npc_role` (`'mob'` vs other NPCs, 2437), `active_mobs` (650). `build_participant_info` already receives `is_npc` from the skills endpoint (357-358) but drops it. Cheapest: carry `is_npc` into the snapshot/payload/state at start (one place, `_participant_payload` 393 + join dict ~5237). Ambiguity: do non-mob NPCs (`npc_role != 'mob'`) count as «мобы» for Saber?
- **PvP:** only `battles.battle_type` (DB row, already loaded at 2583). Note `_track_cumulative_stats` (626) treats only `pvp_training/pvp_death` as PvP — `pvp_attack` is excluded there; Saber's «В PvP» needs an explicit rule (all three `pvp_*`? or "attacker is a player"?).
- **Damage types:** `skills.damage_type` is a free `String(50)` (skills-service models.py:50/111). Engine-known set `RESISTED_DAMAGE_TYPES` (buffs.py:470): physical, catting, crushing, piercing, magic, fire, ice, watering, electricity, wind, sainting, damning; plus `"all"` = weapon `primary_damage_type` (resolved inside the engine → use `log["damage_type"]` after the call). PM's "magic" set = everything not in `_PHYSICAL_TYPES`. Attack skill rows are in `attack_rank["damage_entries"]` (resolved skill, fetched at 3308).

### Dungeon (Saber run stacks)
- Battles in a run are **sequential** (`DungeonSession.active_battle_id`, one at a time). dungeon-service `_start_battle` (gameplay.py ~1690-1740) spawns mobs → `http_clients.create_dungeon_battle` (http_clients.py:370) → battle-service `POST /battles/internal/dungeon` (main.py:1484-1536, body `DungeonBattleCreate{dungeon_session_id, players}`, schemas.py:17) → `_assemble_battle(..., dungeon_session_id=)` (831).
- battle-service persists `battles.dungeon_session_id` (models.py:75) and reads it at the end (`_get_dungeon_session_id` 1539). End callback: `_notify_dungeon_battle_end` 1569 → `POST /dungeons/internal/battle-callback` payload `{battle_id, session_id, winner_team, defeated_characters, aborted}` → `gameplay.process_battle_callback` 1812 → `complete_battle` (exactly-once guard on `active_battle_id`). Fallback: dungeon polls `GET /battles/internal/{id}/result` (1594).
- Storage options for the per-run counter (Architect): (1) **battle-service-only**: Redis key per `(dungeon_session_id, character_id)` (both services share `redis://redis:6379/0`), read in `_assemble_battle` when `dungeon_session_id` is set, written after each Saber kill; TTL ≥ dungeon session TTL; no cross-service contract change. (2) **dungeon-owned**: extend `DungeonBattleCreate` with per-character stacks and the callback with per-character kills; persist in `DungeonSession` (new JSON column → Alembic in dungeon-service) or its Redis `session_state`. Option 2 survives Redis loss but touches 2 services + migration.
- Mid-battle: should a kill raise the bonus immediately in the same battle? (brief implies yes — "до конца забега").

### autobattle-service
- No damage/crit/resist prediction; `strategy._filter_available` (strategy.py:217-242) filters by raw `cost_mana` from the snapshot; `main.py:393` only sums `final` of returned damage events. Passives cannot desync it. Caster's discount is ignored there (a skill affordable only with the discount is skipped — conservative, harmless; mobs have no passive anyway).

### Frontend
- `formatBattleEvent` (useBattleBar.tsx:443): damage branch 685-744 — `dodged` / `hit_chance_failed` / hit line with `крит` badge and FEAT-188 «· <name> +N%» from `passive_pct` (name from snapshot `passive.name`, fallback `PASSIVE_LOG_NAMES` :116 → «пассивка»). One passive segment per event; a hit may now carry the attacker's passive **and** a defender-side one (Saber/Gladiator resists, Inquisitor stacks) → the event shape for multiple contributions is an Architect decision (e.g. list of `{key, kind, value}`).
- New kinds needing rendering: forced crit (Archer/Assassin), extra hit from Shrapnel / Chain lightning (damage event with a marker so it isn't read as an AoE splash), stack changes (Inquisitor/Lancer/Saber/Salamander/Gladiator), Monk's resisted control, Trickster's «Обман» miss, mana discount (`resource_spend`).
- 3D `ArenaHud.tsx:68-88` derives animations from damage events: `dodged`/`hit_chance_failed` → evasion, `final>0` → hit, `critical` → crit. Emitting «Обман» as `dodged: true` + marker animates correctly with zero 3D changes; extra hits as ordinary damage events animate as hits.
- Skill cost UI (`SkillHand.tsx:194-197` greys out when `cost_mana > mana`; `SkillPicker.tsx:268` shows the number) uses raw cost → Caster sees full price and may be blocked client-side from a skill that is affordable after −10%. Needs a decision (show discounted cost via snapshot `passive.key`, or accept).

### Tests
- Extend `app/tests/test_subclass_passives.py`: its harness (`_run_turn` 822-877) drives the real `/battles/1/action` with REAL buffs (`REAL_BUFFS`), real `compute_damage_with_rolls` (via `_DamageSpy`), `main.roll_dodge`/`main.roll_chance` patched in `main`, `battle_engine.roll_crit`/`roll_chance` patched on the module, `get_battle` → `None`. Fixtures `_state`, `_participant`, `_damage_row`, `ATTACK_SKILL`, `SCROLL` are reusable; for AoE/splash a 3-participant `_state` variant is needed.
- **Must update** contract tests: `test_subclass_passives.py:309-315` asserts `implemented == set(passives._DAMAGE_PASSIVES) == {berserker_rage}` and :301-307 asserts the other 20 keys give `(0, None)` from `passive_damage_bonus`; skills-service `tests/test_character_subclass_internal.py:372-375` asserts only `berserker_rage` is implemented. The "implemented ⇔ has effect" check needs a new registry of implemented keys in `passives.py` (most new passives are not damage-dispatch).
- Other suites to keep green: `test_class_damage_luck.py` (engine unit tests — any `compute_damage_with_rolls` param must be optional), `test_weapon_damage_once.py`, `test_item_usage.py`, `test_item_effects.py`, `test_dodge_and_freshness.py`, `test_buffs.py`, `test_redis_state.py`, `test_join_requests.py`, `test_pvp_*`. 30 suites replace `buffs` (and others `battle_engine`) with `MagicMock` in `sys.modules` at collection → **new helpers imported into `main` from `buffs` or `battle_engine` become MagicMocks there** (a truthy MagicMock roll = "always procs"). `passives` is never mocked and imports nothing mocked — keep new logic and its random rolls in `passives.py` (own `random`, or a roll function passed in), not in `buffs`/`battle_engine`.
- dungeon-service tests only if option (2) is chosen.

### Existing Patterns
- battle-service: async, Redis JSON state, `.get(key, default)` for every post-deploy key (precedents `dropped_out`, `weapon_coating`, `passive_key`); constants in `passives.py`, descriptions in skills-service registry (cross-referenced docstrings); log fields are free-form dict keys.
- Passive identity fixed at start (`passive_key` in state, `passive` in snapshot); mobs/NPCs have `passive=None`.

### Cross-Service Dependencies
- No new HTTP calls required for 12 of 13 passives. Saber run stacks: either none (shared Redis, option 1) or `DungeonBattleCreate` + `BattleCallbackRequest` extension (option 2).
- skills-service registry `implemented` flags are read by the frontend badge (`api/subclasses.ts`) — flipping them is the visible "now active" switch.

### DB Changes
- None for battle-service (Redis only). Option 2 for Saber: new JSON column on `dungeon_sessions` (dungeon-service Alembic) or Redis `session_state` only.

### Risks
- **Effect-before-damage ordering (9.0b)** → Agent cannot know the crit; changing the order changes existing semantics (debuffs currently affect the same hit and land even on a dodge) → Mitigation: Architect picks post-damage bonus roll vs reorder; test both "dodged" and "crit" cases.
- **Randomness in tests**: new procs (Mechanic 30%, Sparkmage 25%, Trickster 10%) plus existing `main.roll_chance` patched to `True` in harnesses → passive procs must use a separately patchable roll (in `passives.py`), and tests pin both outcomes. `resolve_aoe_targets` and splash target choice use `random.sample`/`choice` → seed or patch.
- **Mocked modules**: helpers placed in `buffs`/`battle_engine` silently become MagicMocks in ~30 suites (see Tests) — the project's recurring "silent failure" pattern.
- **Splash recursion / passive chaining**: extra hits must not trigger Shrapnel/Chain again, nor (by decision) First blood / Lancer / Inquisitor stacks; target must be alive at that moment (`alive_enemies` is stale within an action; skill loop doesn't check `hp>0` — see new LOW issue in `docs/ISSUES.md`).
- **Dodge cache semantics**: one dodge roll per target per attack (3428-3449); Shrapnel's "own dodge roll" on a target already in the cache must decide reuse vs re-roll; Lancer's steal must apply before the roll for the *next* attack, not retroactively.
- **Control enforcement path**: blocking Monk's first control at application keeps `evaluate_control` untouched, but there are 8 `is_enemy=True` application sites → one wrapper is safer than 8 edits. Raw rows with `attribute_key="random"` (Knockdown/Windburn) are not recognized by `evaluate_control` before application.
- **Duration +1** must never apply to Stun / Poison-paralysis (brief rule) — resource-dose rows also get one extra dose.
- **Multiple passives on one hit** (attacker + defender + Inquisitor stacks from an ally) → log shape must carry several contributions; FEAT-188 frontend shows only one `passive_pct`.
- **Kill attribution** missing (`participant_defeated` has no killer; DoT kills attributed to `eff_owner`) → Saber needs explicit tracking.
- **Old states**: all new keys via `.get`; join path dict (~5237) is hand-written — missing keys default.
- **Caster discount vs client affordability check** (frontend uses raw cost).
- **Ambiguities for PM**: Saber "мобы" = any `is_npc` or `npc_role='mob'` only; "PvP" = which battle types (incl. `pvp_attack`?); Saber kill = own killing blow only? DoT kills? applies within the same battle? Inquisitor −3% to `magic` only or to all non-physical resists? "Попадание" = landed (not dodged/missed) incl. 0 after resists? Shrapnel / Chain per attack or per damage entry/AoE target? Do item scrolls count for Inquisitor's "магия", Archer's first hit, Assassin's next attack? Gladiator: does a control-skipped turn count as "свой ход"? Trickster's 10% — also vs AoE secondary hits and scrolls?

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Summary of decisions

| # | Question | Decision |
|---|----------|----------|
| D1 | Where does passive logic live? | **All of it in `battle-service/app/passives.py`** (constants, pure math, per-battle passive state, every passive random roll). `main.py` only calls a small set of hooks (§3.2) at fixed pipeline points. `passives.py` imports nothing from `buffs` / `battle_engine` (both are `MagicMock`ed in ~30 suites) — it keeps its own copies of the few constant sets it needs (physical types, resource attrs, control names) with a comment pointing at the originals. |
| D2 | Randomness | `passives.py` owns a module RNG: `_rng = random.Random()`, and exactly two gates: `roll_pct(pct) -> bool` and `pick(seq)`. Every passive chance goes through them (module-global lookup, so `patch.object(passives, "roll_pct", ...)` / `passives._rng.seed(n)` make tests deterministic). **A passive roll is consumed only when the participant actually owns that passive** → randomness of every other battle and of every existing test is untouched. `main.py` never rolls for passives. |
| D3 | `compute_damage_with_rolls` | Gets 3 optional kwargs with behaviour-preserving defaults: `force_crit: bool = False`, `crit_damage_bonus: float = 0` (added to `critical_damage` before `/100`), `resist_ignore: Optional[Dict[str, float]] = None` (fraction 0..1 by **resolved** damage type, applied only to a **positive** `resist_pct`). Forced crit still requires the hit roll to land; when forced, the crit roll is not consumed and `log["forced_crit"] = True`; when ignore applies, `log["resist_ignored_pct"]` = points ignored. Needed because `"all"` entries resolve their type (weapon primary type) inside the engine. |
| D4 | Hit / "попадание" unit | **One hit = one (attack, target) pair with ≥1 landed damage roll** (not dodged, not deceived, not `hit_chance_failed`; `final` may be 0 after resists). On-hit passives (Inquisitor, Lancer, Saber PvP stack, Salamander) fire **once per attack per target**, regardless of how many damage entries the skill has. "Attack" = the attack-skill step or a damaging item (scroll) use — items count like skills (user answer). |
| D5 | Agent vs effect order | **Existing order is kept** (enemy effects at 9.0b/9.0e and item step 5 are rolled/applied before damage, also on dodge). After damage, for each target that took a crit from the Agent in that attack, every enemy-side effect row of that attack that **failed** its roll for that target gets **one conditional re-roll** with chance `q = bonus / (100 − p) × 100` (clamped to 100), where `p` is the clamped effective chance of the failed roll and `bonus` = 20 pp (10 pp for stun / poison-paralysis). Overall chance becomes exactly `min(100, p + bonus)`. Rows landing by the re-roll go through the same landing wrapper (Monk immunity, duration rules). Coating rows are rolled after damage already → they simply get the bonus pp directly when the hit target was critted. Non-Agents: zero change (no extra roll, no reorder). |
| D6 | Control classification | By **name**, tolerant of raw (`effect_name` / `attribute_key`) and normalized (`name` / `attribute`) rows: **hard** = `stun`, `poison` + `paralysis`; **soft** = `knockdown`, `windburn` (any attribute incl. `"random"`). `passives.control_kind(row) -> None / "hard" / "soft"`. |
| D7 | Monk immunity | One landing wrapper `_land_enemy_effects` in `_make_action_core` replaces the 8 `is_enemy=True` application sites (§3.3). It calls `passives.filter_incoming_control(target, rows)` → the **first** control row that passed its roll on a Monk in this battle is dropped (flag `control_immunity_used`), a `passive_proc` `control_immune` event is emitted; other rows of the same batch land. Enforcement (`evaluate_control`) is untouched. |
| D8 | Duration +1 | Same wrapper calls `passives.adjust_outgoing_enemy_rows(owner, rows)` **before** Monk filtering/applying, on row copies: Trickster → every enemy-side row with `duration ≥ 1`, except hard control and except instant resource rows (`hp/mana/energy/stamina` with `duration ≤ 1` — bumping those would turn an instant hit into a DoT); Salamander → only rows named `Burn`. Never stun / paralysis. |
| D9 | `is_npc` / PvP | Participant state gets `is_npc: bool`. Source of truth: `_assemble_battle` (has `db`) fills `snap["is_npc"]` from `characters.is_npc` **before** building payloads (the existing per-participant `SELECT is_npc` used for autobattle registration is moved up and its result reused — one query, no behaviour change); `build_participant_info` also returns `is_npc` from the subclass lookup (fallback for the PvP/join paths, all players). **Saber «мобы»** = target `is_npc is True`; **Saber PvP «Несгибаемость»** = Saber takes a hit from an attacker with `is_npc is False` (covers pvp_training / pvp_death / pvp_attack, user answer, without needing `battle_type` in Redis). Old states (key absent) → neither rule fires. |
| D10 | Per-battle passive state | One namespaced dict per participant: `participants[pid]["passive_state"]` (created lazily via `passives.pstate(p)`, `.get` everywhere; old states → `{}`). Keys in §3.4. Battle-level: `state["dungeon_session_id"]` (new optional `init_battle_state` param, `None` otherwise). |
| D11 | Kill attribution | Every HP loss inside `_make_action_core` is caused by the acting participant (direct hits, scrolls, extra hits, and DoT/dose ticks — `tick_periodic_effects` only ticks effects **owned** by the actor). So in step 9.5, every **newly defeated enemy of the actor** is the actor's kill → `passives.on_kills(state, actor_pid, victims)`. No per-hit tracking, DoT kills included (user answer). Timeouts (`participant_timed_out`) are not kills. |
| D12 | Saber run stacks storage | **Option 1 — battle-service Redis key**, no migration, no dungeon-service change: `battle:passive:saber_run:{dungeon_session_id}:{character_id}` → int, TTL `SABER_RUN_STACKS_TTL_S = 14 days` refreshed on each write. Seeded into `passive_state["saber_kills"]` in `_assemble_battle` (and the join path) when the battle has a `dungeon_session_id`; written (soft-fail) after each Saber kill; bonus rises immediately in the same battle. Session ids are unique per run → a new run starts at 0 naturally. Option 2 (dungeon-owned) rejected: 2 services + contract + Alembic for a value that is cosmetic if lost (pre-beta, Redis loss = stacks reset, logged). |
| D13 | Splash / chain (Mechanic, Sparkmage) | Decided **once per attack after the attack's damage loop**, at that moment (mode is per hit, not per battle — user answer). Candidates = enemies with `hp > 0` **now**, excluding the attack's primary target. Mechanic: needs ≥1 landed hit in the attack; candidates → 30% → `splash` ×0.4 on `pick(candidates)`; no candidates → **duel mode is decided at attack begin** (no other living enemy): 30% → +35% damage on the primary for this attack. Sparkmage: needs ≥1 landed `electricity`/`wind` roll; candidates → 25% → `chain` ×0.5; no candidates and primary alive → 25% → `echo` ×0.4 on the same target. Extra hit = the **trigger entry** (first landed entry / first landed electricity-wind entry) re-run through `compute_damage_with_rolls` with the attacker's attack-level buffs only, the target's own resists (incl. defender-side passives), a **fresh** dodge roll (+ Trickster deceit), normal crit roll, then `× mult`. Extra hits **never** trigger on-hit passives, other extra hits, Agent re-rolls, coating or first blood (no recursion), but their kills count (D11). |
| D14 | Gladiator | Counted at hit time from `participants_map` (`hp > 0`): attacker side at attack begin `surplus = clamp(enemies − allies_incl_self, 0, 3)` → `+8×surplus%` damage; else ramp `+3% × own_turns` (cap 15). Defender side (target ctx) `+4×surplus` to `"all"` resists from the defender's own perspective. `own_turns` increments at the start of each Gladiator action that is **not** `control_skip` (stun/paralysis-skipped turns don't count — user answer), so the first own attack has +3%. Works in any battle type. |
| D15 | Lancer | Literal reading of the registry text «крадёт у цели 2% уклонения и 2 п.п. шанса крита себе»: on each hit the Lancer takes **both** `dodge` and `critical_hit_chance` from the target (target −, Lancer +), `min(2, target's current value)` per stat (never below 0), up to 5 successful steals per Lancer (±10). The stat list is a constant `LANCER_STOLEN_STATS` — if PM says "dodge from target, crit only to self" it is a one-constant change (see Q1). Applied via `passives.stat_deltas(state, pid)` to every attr copy used in an attack (attacker attrs in skill + item paths, every target ctx), floor 0. Steal happens in `finish_attack` → affects the **next** attacks, never retroactively. |
| D16 | Caster | Resist ignore via D3 `resist_ignore={"magic": 0.25}` (resolved type `magic` only, positive resist only). Mana: `passives.mana_cost(participant, raw)` per rank inside `_pay_skill_costs`, integer round-half-up `(raw × (100 − 10) + 50) // 100`, applied **before** the affordability check. Frontend mirrors the exact formula (§3.6). autobattle ignores it (mobs have no passive) — no change there. |
| D17 | Log shape | Damage events (and `apply_effects` / `resource_spend` where relevant) get an optional list **`passives: [{key, kind, value?, owner?}]`** collecting attacker- and defender-side contributions. FEAT-188 `passive_key` / `passive_pct` are **still emitted for rage** exactly as today. New event type `passive_proc` for things that are not a number on a hit (stacks, immunity, shadow, Agent bonus). Frontend: `passives` present → render the list; absent → FEAT-188 fallback. |
| D18 | Trickster redirect seam | Deceit is rolled in the target-ctx builder (after the dodge roll, only if not dodged). `passives.deceit_redirect_target(state, attacker_pid, trickster_pid) -> Optional[int]` exists and returns `None` in FEAT-189; FEAT-190 fills it (redirect into attacker's ally at 50%). The skills-service description drops the redirect sentence until then. |
| D19 | DB / nginx / compose / permissions | None. No new endpoint. |

### 3.1 `passives.py` — constants

All numbers as named constants next to their passive (docstring cross-ref to `skills-service/app/subclasses.py` — "change a constant → update the description"):

```
INQUISITOR: HERESY_RESIST_PER_STACK=3, HERESY_MAX_STACKS=5
SABER:      SABER_NPC_DAMAGE_PCT=15, SABER_KILL_PCT=2, SABER_KILL_MAX_PCT=10,
            SABER_PVP_RESIST_PCT=2, SABER_PVP_MAX_STACKS=3, SABER_RUN_STACKS_TTL_S=14*24*3600
GLADIATOR:  ARENA_DAMAGE_PCT=8, ARENA_RESIST_PCT=4, ARENA_MAX_SURPLUS=3,
            RAMP_PCT_PER_TURN=3, RAMP_MAX_PCT=15
AGENT:      WEAK_SPOT_BONUS_PP=20, WEAK_SPOT_HARD_CONTROL_BONUS_PP=10
LANCER:     PIN_STEAL=2, PIN_MAX_STACKS=5, LANCER_STOLEN_STATS=("dodge","critical_hit_chance")
MECHANIC:   SHRAPNEL_CHANCE=30, SHRAPNEL_MULT=0.4, SHRAPNEL_DUEL_PCT=35
ARCHER:     FIRST_BLOOD_CRIT_BONUS=50
ASSASSIN:   SHADOW_CRIT_BONUS=25, EXECUTE_HP_PCT=30, EXECUTE_DAMAGE_PCT=20
TRICKSTER:  DECEIT_CHANCE=10, DEBUFF_EXTRA_TURNS=1
MONK:       HARMONY_CONTROL_BONUS_PP=10, HARMONY_HARD_CONTROL_BONUS_PP=5
SALAMANDER: KINDLING_PCT=6, KINDLING_MAX_STACKS=5, BURN_EXTRA_TURNS=1
CASTER:     PURE_ENERGY_RESIST_IGNORE=0.25, CASTER_MANA_DISCOUNT_PCT=10
SPARKMAGE:  CHAIN_CHANCE=25, CHAIN_MULT=0.5, ECHO_CHANCE=25, ECHO_MULT=0.4
```
Plus `PASSIVE_*` key constants for all 14, and `IMPLEMENTED_PASSIVES: FrozenSet[str]` = rage + the 13 (the battle-side mirror of the registry `implemented` flag; the contract test compares the two).

Type sets (own copies, see D1): `PHYSICAL_TYPES = {"physical","catting","crushing","piercing"}`; `NON_PHYSICAL_TYPES = {"magic","fire","ice","watering","electricity","wind","sainting","damning"}`; "used magic" = any resolved entry type not in `PHYSICAL_TYPES`.

### 3.2 `passives.py` — hook API (main.py calls only these)

Names are binding for tests; internals free. All hooks: unknown/None `passive_key`, missing keys, old states → no-op / neutral result. Contribution = `{"key": str, "kind": str, "value": number (optional), "owner": pid (optional)}`.

| # | Hook | Called from | Covers |
|---|------|-------------|--------|
| H0 | `roll_pct(pct)`, `pick(seq)`, `pstate(participant)`, `control_kind(row)`, `resolve_entry_type(dmg, weapons)` | internal + main | gates/helpers |
| H1 | `on_turn_start(state, actor_pid, skipped: bool) -> None` | right after `evaluate_control` | Gladiator `own_turns` |
| H2 | `begin_attack(state, attacker_pid, primary_pid, entry_types: list[str], source_kind: "skill"/"item") -> AttackCtx` | skill attack step and item damage step, before the damage loop | Inquisitor "used magic" mark (any attacker); attacker-level pct + contributions (Gladiator arena/ramp, Saber kill stacks); Assassin shadow → force crit for the whole attack (flag consumed here); Mechanic duel roll; Salamander current stacks / reset |
| H3 | `target_damage_mods(actx, state, target_pid, dmg_type, is_primary) -> TargetMods` | per damage roll (inside `_strike`, not for extra hits) | Saber vs NPC; Assassin execute (<30% HP now); Salamander (+6×stacks to `fire`, kindling target only); Mechanic duel +35% (primary); Archer first blood (target not yet first-blooded → `force_crit` + 50); Assassin shadow (`force_crit` + 25); Caster `resist_ignore`. Returns `{pct_by_type, force_crit, crit_damage_bonus, resist_ignore, contributions}` |
| H4 | `defender_resist_mods(state, defender_pid, attacker_pid) -> (delta_by_type, contributions)` | target-ctx builder (copy of resists dict) | Inquisitor stacks (−3×n on each NON_PHYSICAL type — works for every attacker, i.e. allies too), Gladiator defender (+4×surplus `all`), Saber PvP stacks (+2×n `all`) |
| H5 | `stat_deltas(state, pid) -> dict`, `apply_stat_deltas(attrs, deltas) -> dict` (copy, stolen stats floored at 0) | every attacker attrs copy + target-ctx builder | Lancer |
| H6 | `roll_deceit(state, target_pid) -> bool`; `deceit_redirect_target(state, attacker_pid, trickster_pid) -> None` | target-ctx builder (if not dodged) | Trickster 10%; FEAT-190 seam |
| H7 | `on_dodged(state, dodger_pid) -> list[event]` | wherever a ctx `dodged` is consumed (skill, item, extra hit) — not on deceit | Assassin `shadow_ready` |
| H8 | `record_strike(actx, target_pid, dmg, log, is_extra)` | after each `compute_damage_with_rolls` | landed / crit per target, trigger entries, Archer first-blood consumption (on a landed forced crit) |
| H9 | `finish_attack(actx, state) -> list[event]` | after the damage loop (before extra hit) | Inquisitor +1 stack on marked hit targets (cap 5); Lancer steal; Saber PvP stack for each Saber hit by a non-NPC attacker (+1 per attack, cap 3); Salamander stack update/reset |
| H10 | `plan_extra_hit(actx, state) -> Optional[{target_pid, entry, mult, kind}]` | after H9 | Mechanic splash / Sparkmage chain / echo (D13) |
| H11a | `effect_chance_bonus_pp(caster, row) -> float` | `_filter_effects_by_chance(bonus_pp_fn=…)` for enemy rows | Monk +10 / +5 |
| H11b | `weak_spot_reroll(caster, row, failed_chance) -> bool`, `weak_spot_bonus_pp(caster, row) -> float` | post-damage re-roll; coating roll on critted targets | Agent (D5) |
| H11c | `adjust_outgoing_enemy_rows(caster, rows) -> (rows_copy, contributions)` | `_land_enemy_effects` | Trickster / Salamander +1 turn (D8) |
| H11d | `filter_incoming_control(target, rows, target_pid) -> (kept, events)` | `_land_enemy_effects` | Monk immunity (D7) |
| H12 | `mana_cost(participant, raw_cost: int) -> int` | `_pay_skill_costs` | Caster |
| H13 | `on_kills(state, killer_pid, victim_pids) -> (events, saber_stacks_to_persist: Optional[int])` | step 9.5 | Saber run stacks (only if `state.get("dungeon_session_id")`) |
| — | `passive_damage_bonus(p)` (FEAT-188) | unchanged | rage only |

`AttackCtx` is a plain dict/dataclass local to one attack (never saved). Rule: a hook rolls (`roll_pct`/`pick`) only for a participant owning that passive.

### 3.3 `main.py` integration (`_make_action_core`)

Scoped de-duplication (like FEAT-188's `_participant_payload`), so a passive cannot be wired into one path and forgotten in another. Behaviour for participants without passives must stay byte-identical (existing suites are the proof).

1. **`_filter_effects_by_chance`**: two optional kwargs `bonus_pp_fn: Optional[Callable[[dict], float]] = None` (added to `actual_chance` before clamping) and `failed_out: Optional[list] = None` (appends `(row, actual_chance)` for rows that failed). Defaults → current behaviour.
2. **Closures** defined once after `_res_effects_now`:
   - `_roll_enemy_effects(rows, target_pid, failed_out=None)` = `_filter_effects_by_chance(rows, attacker_luck_bonus, await _res_effects_now(target_pid), bonus_pp_fn=<Monk H11a for the actor>, failed_out=failed_out)`.
   - `_land_enemy_effects(target_pid, rows, source=None) -> applied_rows` = H11c (owner = actor) → H11d (target) → `apply_new_effects(..., is_enemy=True, owner_pid=actor, source=source)`; appends H11d events to `turn_events`; returns the rows actually applied (callers log those; empty → no `apply_effects` event).
   - Replace **all 8** enemy sites: support enemy (~2823/2830), support all-enemies (~2872/2879), defense enemy (~2909/2916), defense all-enemies (~2957/2964), item enemy rows (~3090/3123, only when `is_enemy_side`; ally/self/cleanse rows untouched), attack enemy (~3329/3336), attack all-enemies (~3380/3387), coating (~3531/3538, with `bonus_pp_fn` also adding H11b for critted targets).
3. **Target ctx builder** `_build_target_ctx(pid, attacker_pid) -> {"attrs","resists","dodged","deceived"}`: `apply_flat_modifiers(attrs, mods)` → H5 → `build_percent_resist_buffs` → copy + H4 deltas (contributions stored in ctx) → `roll_dodge` → if not dodged H6. Used for the skill primary seed, `_ctx_for`, `_item_ctx_for` (each path keeps its own per-attack cache). Attacker attrs in both paths also get H5.
4. **`_strike(target_pid, dmg, mult, ctx, actx, pct_buffs, attacker_attrs, weapon, event_extra, extra_kind=None) -> (dealt, event)`**: H3 (skipped for extra hits) → per-target copy of `pct_buffs` + `pct_by_type` → `compute_damage_with_rolls(..., force_crit, crit_damage_bonus, resist_ignore)` → `× mult` (existing falloff pattern) → HP / damage stats (as today) → H8 → event with `passives` (attack-level + target + ctx defender contributions), FEAT-188 `passive_key/passive_pct` for rage as today, `extra_hit`/`extra_mult` when `extra_kind`. Used by the skill loop, the item loop and extra hits. The dodge/deceit branch stays in the callers (one event per target per attack; deceit event per D17; H7 on a real dodge). The item loop keeps its existing `hp <= 0` skip; the skill loop keeps current behaviour (the known LOW issue about AoE on dead targets is **not** fixed here).
5. **Attack flow** (skill path and item damage path): resolve entry types (H0) → H2 → loop with `_strike` → H9 → Agent re-roll: for each critted target (from `actx`), for the rows that failed at 9.0b (primary) / 9.0e (that enemy) / item step 5 (primary) — collected via `failed_out` — H11b → `_land_enemy_effects` → `passive_proc weak_spot` event with the effects → H10 → if planned, one `_strike(extra_kind=...)` with a fresh `_build_target_ctx` (dodge/deceit/H7 apply; alive check right before). Items with no damage rows are not attacks (no H2).
6. **H1** right after `evaluate_control` (`skipped = bool(_full_skip)`).
7. **`_pay_skill_costs`**: mana per rank through H12; `spend` gets `mana_discount` (int, only when > 0) and `resource_spend` event gets `passives: [{key: caster_pure_energy, kind: mana_discount, value}]`.
8. **Step 9.5**: collect newly-defeated pids with `team != actor team` → H13 → events into `turn_events`; if stacks returned → `await redis_state.set_saber_run_stacks(session_id, character_id, stacks)` (soft-fail, `logger.error`).

### 3.4 State plumbing

- **Participant state** (Redis): `is_npc: bool`, `passive_state: dict` (seeded `{}` or `{"saber_kills": n}`). `passive_state` keys (all optional): `used_magic` (any participant), `heresy_stacks` (target), `saber_kills`, `saber_pvp`, `own_turns`, `lancer_stacks`, `lancer_gain: {stat: amt}`, `stolen: {stat: amt}` (target), `first_blood_done: [pid]`, `shadow_ready`, `control_immunity_used`, `kindling_target`, `kindling_stacks`.
- `build_participant_info` → return dict gains `is_npc` (`bool(sub_info.get("is_npc"))`, `False` on failure).
- `_participant_payload` → `"is_npc": bool(snap.get("is_npc"))`, `"passive_state": snap.get("passive_state") or {}` (the latter set by `_assemble_battle` for the Saber seed; snapshot itself never stores `passive_state` — strip/keep it out of the Mongo snapshot).
- `_assemble_battle(... dungeon_session_id)`: move the `SELECT is_npc` up, set `snap["is_npc"]`; Saber seed via `redis_state.get_saber_run_stacks(session_id, character_id)` (soft-fail → 0); pass `dungeon_session_id` to `init_battle_state`; autobattle registration reuses the flags.
- `redis_state.init_battle_state(..., dungeon_session_id=None)`: state `"dungeon_session_id"`; participant dict copies `p.get("is_npc")` and `dict(p.get("passive_state") or {})`.
- `redis_state`: `get_saber_run_stacks(session_id, character_id) -> int`, `set_saber_run_stacks(session_id, character_id, stacks)` (SET with TTL from `passives.SABER_RUN_STACKS_TTL_S`; key constant `KEY_SABER_RUN_STACKS`).
- Join (`admin_approve_join_request` dict ~5237): `is_npc`, `passive_state` (Saber seed if `state.get("dungeon_session_id")`).
- PvP invitation / PvP attack paths: covered by `_participant_payload` (is_npc from snapshot, no seed — no dungeon).

### 3.5 Log contract

Damage event (optional new keys):
```json
{"event":"damage","source":3,"target":7, "...engine log...": "...",
 "forced_crit": true, "resist_ignored_pct": 7.5,
 "passives":[{"key":"archer_first_blood","kind":"forced_crit","value":50,"owner":3},
             {"key":"inquisitor_heresy_seal","kind":"resist_pct","value":-9},
             {"key":"gladiator_arena","kind":"resist_pct","value":8,"owner":7}],
 "passive_key":"berserker_rage","passive_pct":12,
 "extra_hit":"splash","extra_mult":0.4}
```
`kind` ∈ `damage_pct` (value %), `resist_pct` (signed points on this hit), `forced_crit` (value = crit dmg bonus %), `resist_ignore` (value %), `extra_hit` (value = mult×100), `deceit`, `duration_plus` (on `apply_effects`), `mana_discount` (on `resource_spend`). Rage also appears in `passives` (`damage_pct`) **and** keeps FEAT-188 `passive_key/passive_pct`.
Deceit: `{"event":"damage","source":a,"target":t,"dodged":true,"final":0,"deceived":true,"passives":[{"key":"trickster_deceit","kind":"deceit","owner":t}]}` (3D animates it as a dodge without changes).
`passive_proc`: `{"event":"passive_proc","who":owner,"key":…, "kind":…, "target"?, "value"?, "stacks"?, "effects"?, "stolen"?}` with kinds `heresy_stack`, `pin`, `saber_kill`, `saber_resolve`, `shadow_ready`, `control_immune`, `weak_spot`. Unknown kinds must render as nothing (forward compat), never crash.

### 3.6 Frontend

- `BattlePageBar/useBattleBar.tsx`: `BattleEvent` gains `passives?: PassiveContribution[]`, `forced_crit?`, `resist_ignored_pct?`, `extra_hit?`, `extra_mult?`, `deceived?`, `stacks?`, `stolen?`, `value?`, `key?`, `mana_discount?`. `PASSIVE_LOG_NAMES` gets all 14 keys (Russian names from the registry). Damage line: render every contribution (owner's snapshot `passive.name` → fallback map → «пассивка»): e.g. «· Первая кровь: крит +50%», «· Печать ереси: сопр. −9%», «· Арена +16%»; extra-hit lines get a prefix («осколок» / «перескок» / «повтор»); deceit → «<цель> обманул <атакующий>» (not «уклонился»); `passive_proc` lines (stack gained, immunity, «Из тени готов», «Слабое место: <эффекты>», Saber kill stacks); `resource_spend` shows the discount if present. Old logs (no `passives`) → FEAT-188 rendering. Covers 2D bar and 3D Chronicle.
- Caster mana: new `src/utils/passiveCosts.ts` — `CASTER_PASSIVE_KEY`, `CASTER_MANA_DISCOUNT_PCT = 10` (comment: mirror of `battle-service/app/passives.py`), `effectiveManaCost(cost: number, passiveKey?: string | null): number` = `Math.floor((cost * (100 - pct) + 50) / 100)` for the Caster, else `cost`. Used by `Arena3D/hud/SkillHand.tsx` (affordability + shown number) and `SkillPicker/SkillPicker.tsx` (shown number + any affordability check), plus any other client-side mana check the dev finds in the battle page. The acting player's passive key comes from their snapshot entry (`passive?.key`). No styling changes required (numbers only); if a style is touched, the Tailwind/mobile rules apply.
- `Arena3D/hud/ArenaHud.tsx`: no change expected (deceit = `dodged`, extra hits = ordinary damage); verify it ignores `passive_proc`.
- Rules: `docs/DESIGN-SYSTEM.md`, no `React.FC`, TS only, Russian text, `tsc --noEmit` + `npm run build` in Docker.

### 3.7 skills-service

`app/subclasses.py`: `implemented=True` for the 13 keys. Description fixes to match the decided behaviour: Inquisitor «…снижает все его не-физические сопротивления (магия, стихии, святость, проклятие) на 3%…»; Trickster drops the redirect sentence (returns in FEAT-190), keeps 10% + debuffs +1 turn. Other 11 descriptions already match the constants. Docstring cross-ref to `passives.py` stays.

### 3.8 Security

No new endpoints, no new inputs from clients (target ids are already validated in `_make_action_core`). New Redis key is internal (battle-service only), integer value, TTL-bounded. No secrets/PII in new log fields. Rate limiting unchanged.

### 3.9 Cross-service validation

- skills-service `implemented` flags → frontend badge only (additive semantics, same schema).
- Redis state: additive keys (`is_npc`, `passive_state`, `dungeon_session_id`); every reader uses `.get`. autobattle reads `snapshot`/`state` explicit keys → unaffected; it ignores the Caster discount (mobs only, harmless).
- `compute_damage_with_rolls`: optional kwargs only → engine unit tests and mocked suites unaffected.
- Log events: additive keys/new event type; `save_log` stores dicts as-is; frontend tolerant of unknown kinds.
- dungeon-service: **no change** (D12).

### 3.10 Risks & mitigations

| Risk | Mitigation |
|---|---|
| Helpers placed in `buffs`/`battle_engine` become MagicMocks in ~30 suites (silent failure pattern) | All new logic in `passives.py`; QA asserts with the REAL modules (existing `test_subclass_passives.py` harness) and adds a guard test that `passives` imports neither module. |
| Non-determinism / existing tests consuming new rolls | D2: rolls only for owners; tests patch `passives.roll_pct` / `pick` both ways (proc / no proc). |
| main.py hotspot, two paths diverging | Single writer at a time (task order §4); `_strike` / `_build_target_ctx` / `_land_enemy_effects` shared by all paths. |
| Splash recursion / chain triggering | `is_extra` short-circuits H3/H8-on-hit/H9/H10; QA test: at most one extra hit per attack, none from an extra hit. |
| Monk immunity bypass via `attribute_key="random"` | name-based `control_kind`; QA test with a raw Knockdown `random` row. |
| Duration +1 on stun/paralysis | explicit exclusion + QA tests for Trickster and Salamander with Stun/Poison-paralysis rows. |
| Old in-flight battles | `.get` everywhere; QA runs an attack on a state without `is_npc`/`passive_state`/`dungeon_session_id`. |
| Saber stacks lost on Redis flush | Acceptable pre-beta; soft-fail + log. |
| Frontend/backend mana formula drift | Same integer formula, both files cross-reference; QA backend table + frontend dev unit check of the same table (5→5, 10→9, 15→14, 25→23, 1→1, 0→0). |

### 3.11 Rollback
Code-only. Reverting leaves unused `is_npc` / `passive_state` / `dungeon_session_id` in live Redis states (ignored by old code) and Saber keys that expire within 14 days. Flip the 13 `implemented` flags back if only battle-side code is reverted.

### 3.12 Open questions for PM (non-blocking — defaults above are implemented unless PM says otherwise)
- **Q1 (Lancer):** registry text «крадёт у цели 2% уклонения и 2 п.п. шанса крита себе». Default = target loses **both** dodge and crit, Lancer gains both. Alternative reading (target loses only dodge, Lancer gains only crit) = change `LANCER_STOLEN_STATS` handling in one place.
- **Q2 (Assassin):** «следующая атака» — default: the shadow is consumed by the next attack (skill attack or damaging scroll) whatever its outcome, and every damage roll of that attack is a forced crit.
- **Q3 (Caster rounding):** round-half-up (cost 5 → 5, 15 → 14). Alternative: always round down (5 → 4).

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Parallelism.** Wave A (start at once, no file overlap): Tasks 1, 2, 3, 5. Task 4 (main.py pipeline) needs 2 + 3 — `main.py` has a single writer at a time (Task 3 → Task 4). QA 6 after 2; QA 7 after 3 + 4; QA 8 after 1. Reviewer last. **No agent runs `git commit`, `git stash` or `git push`** (the user commits once at the end). All checks run inside Docker containers (no node/python toolchain on the host).

### Task 1 — skills-service: flip `implemented`, description fixes
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/skills-service/app/subclasses.py`, `docs/services/skills-service.md` |
| **Depends On** | — |
| **Description** | Per §3.7: `implemented=True` for the 13 keys (`inquisitor_heresy_seal`, `saber_monster_hunter`, `gladiator_arena`, `agent_weak_spot`, `lancer_pin`, `mechanic_shrapnel`, `archer_first_blood`, `assassin_from_shadow`, `trickster_deceit`, `monk_harmony`, `salamander_kindling`, `caster_pure_energy`, `sparkmage_chain_lightning`). Inquisitor description → all non-physical resists; Trickster description without the redirect sentence (FEAT-190). Re-check the other 11 descriptions quote the §3.1 constants. Update module docstring / service doc (14 passives live). Do NOT edit tests (Task 8). |
| **Acceptance Criteria** | `python -m py_compile` passes in the container. `GET /skills/subclasses` shows `implemented=true` for exactly 14 keys (rage + 13). |

### Task 2 — battle-service: `passives.py` hook module + engine kwargs
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/battle-service/app/passives.py`, `services/battle-service/app/battle_engine.py` (only `compute_damage_with_rolls`) |
| **Depends On** | — |
| **Description** | Implement §3.1 constants and the full §3.2 hook API (H0–H13) as pure functions over the state dicts, incl. `IMPLEMENTED_PASSIVES`, `pstate`, `control_kind`, `resolve_entry_type`, the RNG gates `roll_pct`/`pick` (module `_rng`), contributions and `passive_proc` event builders (§3.5). Rules: no import of `buffs`/`battle_engine`; rolls only for owners of the passive; every input tolerant of missing keys / old states; stolen stats never below 0; stacks capped; extra hits never re-trigger. Keep `rage_bonus_pct` / `passive_damage_bonus` behaviour. Engine: add `force_crit`, `crit_damage_bonus`, `resist_ignore` kwargs per D3 with defaults preserving current behaviour and log keys `forced_crit` / `resist_ignored_pct`. Update module docstrings (cross-ref to skills-service registry). No `main.py` edits. |
| **Acceptance Criteria** | `py_compile` passes. Existing `test_class_damage_luck.py`, `test_weapon_damage_once.py`, `test_subclass_passives.py` (except the 2 contract tests Task 7 rewrites) stay green. `passives` imports neither `buffs` nor `battle_engine`. |

### Task 3 — battle-service: state plumbing (is_npc, passive_state, dungeon id, Saber run key)
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/battle-service/app/main.py` (only `build_participant_info`, `_participant_payload`, `_assemble_battle`, join dict in `admin_approve_join_request`), `services/battle-service/app/redis_state.py` |
| **Depends On** | — (may run parallel with Task 2; imports `passives.SABER_RUN_STACKS_TTL_S` / `PASSIVE_SABER…` — if Task 2 isn't merged yet, coordinate by adding just those two constants first) |
| **Description** | Per §3.4 / D9 / D12: `is_npc` in snapshot + payload + Redis participant state (DB truth in `_assemble_battle` by moving the existing `SELECT is_npc` before payload building and reusing it for autobattle registration); `passive_state` seeded `{}` / Saber `{"saber_kills": n}` from the Redis run key when `dungeon_session_id` is set (also in the join path); `init_battle_state(..., dungeon_session_id=None)` stores `dungeon_session_id`, copies `is_npc` and `passive_state` with `.get`; `redis_state.get_saber_run_stacks` / `set_saber_run_stacks` (soft-fail, TTL). `passive_state` must not end up in the Mongo snapshot. |
| **Acceptance Criteria** | `py_compile` passes. Existing suites green (`test_redis_state.py`, `test_join_requests.py`, `test_pvp_*`, `test_pack_attack.py`, `test_npc_death.py`, `test_subclass_passives.py`). New states contain `is_npc`, `passive_state`, `dungeon_session_id` in all 4 construction paths; battle start works with Redis key absent or Redis read failing. |

### Task 4 — battle-service: action-pipeline wiring of the 13 passives + docs
| Field | Value |
|---|---|
| **Agent** | Backend Developer |
| **Status** | DONE |
| **Files** | `services/battle-service/app/main.py` (`_filter_effects_by_chance`, `_pay_skill_costs`, `_make_action_core`), `docs/services/battle-service.md`, `docs/SUBCLASS-PASSIVES.md`, `docs/ISSUES.md` (only if new issues found) |
| **Depends On** | 2, 3 |
| **Description** | Per §3.3 (steps 1–8) and §3.5: `_filter_effects_by_chance` kwargs; closures `_roll_enemy_effects` / `_land_enemy_effects` replacing all 8 enemy sites; `_build_target_ctx` (H5, H4, dodge, deceit) for skill primary, `_ctx_for`, `_item_ctx_for`; `_strike` shared by skill loop, item loop and extra hits; attack flow H2 → strikes → H9 → Agent re-roll (failed rows via `failed_out`) → H10 extra hit; H1 after `evaluate_control`; H7 on real dodges (skill, item, extra); H12 in `_pay_skill_costs` with `mana_discount`; step 9.5 kill attribution → H13 + `set_saber_run_stacks`. Emit `passives` lists, deceit events, `passive_proc` events; keep FEAT-188 `passive_key/passive_pct` for rage. No random calls for passives in main.py. Docs: battle-service.md (hook points, state keys, log contract §3.5, Saber Redis key); SUBCLASS-PASSIVES.md (opora 4 splash ✅, plan step 5 — wave 1 ✅ for the 13 incl. Trickster part 1, redirect → FEAT-190). |
| **Acceptance Criteria** | `py_compile` passes. Full battle-service suite green (excluding the two FEAT-188 contract tests Task 7 rewrites). A battle without passives produces byte-identical events vs before (existing suites). Manual smoke in the container: an attack with each passive owner resolves without exception. |

### Task 5 — frontend: passive log rendering + Caster mana cost
| Field | Value |
|---|---|
| **Agent** | Frontend Developer |
| **Status** | DONE |
| **Files** | `src/components/pages/BattlePage/BattlePageBar/useBattleBar.tsx`, new `src/utils/passiveCosts.ts`, `src/components/pages/BattlePage/Arena3D/hud/SkillHand.tsx`, `src/components/pages/BattlePage/SkillPicker/SkillPicker.tsx`, any other battle-page client mana check found; verify `Arena3D/hud/ArenaHud.tsx` |
| **Depends On** | — (contract §3.5 fixed; live check needs Task 4) |
| **Description** | Per §3.6: event types, `PASSIVE_LOG_NAMES` for 14 keys, rendering of all `passives` contributions, extra hits, deceit, `passive_proc` kinds, mana discount; old logs fall back to FEAT-188 rendering; unknown kinds render nothing. `effectiveManaCost` util with the exact integer formula; skill cards show the discounted cost for a Caster and don't block a skill affordable with the discount. |
| **Acceptance Criteria** | Read `docs/DESIGN-SYSTEM.md` first. No `React.FC`, no new SCSS, no `.jsx` logic. `npx tsc --noEmit` + `npm run build` pass in Docker. Formula table: 0→0, 1→1, 5→5, 10→9, 15→14, 25→23. 3D deceit animates as a dodge; no console errors on `passive_proc`. 360px OK if any layout touched. |

### Task 6 — QA: `passives.py` unit tests (all 13 + engine kwargs)
| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | new `services/battle-service/app/tests/test_passives_wave1.py` (engine kwargs tests live there too, not in `test_class_damage_luck.py`) |
| **Depends On** | 2 |
| **Description** | Pure tests with the real module, rolls forced via `patch.object(passives, "roll_pct"/"pick")` in both directions. Per passive: **Inquisitor** — mark on non-physical (incl. `all` resolved to a magic weapon), no mark on physical; stack only on marked target, cap 5, −3×n on every NON_PHYSICAL type, physical untouched, applies for any attacker. **Saber** — +15 only vs `is_npc True`, none vs `None`/False; kill stacks only with `dungeon_session_id`, +2/kill cap 10, returned for persistence; PvP stack only from `is_npc False` attacker, +1 per attack, cap 3. **Gladiator** — surplus 0/1/3/5→cap 3, damage and defender resist; ramp +3/turn cap 15; skipped turn not counted. **Agent** — re-roll chance math (p=0 → 20, p=50 → 40%-conditional = total 70, p=95 → capped 100), hard control +10, non-crit → no re-roll, non-Agent → no roll consumed. **Lancer** — steal both stats, partial steal when target has <2, never below 0, cap 5 stacks. **Mechanic** — splash only with landed hit, only alive non-primary candidates, duel +35 decided at begin, no extra from extra. **Archer** — first landed hit per target forced crit +50, dodge doesn't consume it, second target also gets it. **Assassin** — shadow on dodge only (not deceit), consumed by next attack, execute <30% (29.9 yes, 30 no). **Trickster** — deceit 10% gate, redirect seam returns None, +1 duration except stun/poison-paralysis and instant resource rows. **Monk** — +10 soft / +5 hard; first control only blocked, raw Knockdown `attribute_key="random"` counts, second control lands. **Salamander** — stacks on consecutive fire hits same target, reset on other target / non-fire, cap 5, Burn +1 turn only. **Caster** — `resist_ignore` only for `magic`, only positive resist; mana formula table (§3.10). **Sparkmage** — only electricity/wind, chain 50% with candidates, echo 40% when none and primary alive, nothing when primary dead and no others. Engine: defaults unchanged; `force_crit` without hit = miss; `crit_damage_bonus` 50 → ×1.75 at default 125; vulnerability (negative resist) not reduced. Guard: `passives` doesn't import `buffs`/`battle_engine`; rolls not consumed for participants without the passive; old-state dicts (no `passive_state`/`is_npc`) → neutral. Security-ish: garbage values (None, strings, negative stacks) don't raise. |
| **Acceptance Criteria** | All tests pass in the container; each passive has ≥1 positive and ≥1 negative case; both proc outcomes pinned for every chance passive. |

### Task 7 — QA: integration through `_make_action_core` + state plumbing + FEAT-188 contract tests
| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | `services/battle-service/app/tests/test_subclass_passives.py` (update :301-315 + extend harness), new `app/tests/test_passives_wave1_integration.py`, extend `test_redis_state.py`, `test_join_requests.py` |
| **Depends On** | 3, 4 |
| **Description** | (a) Rewrite FEAT-188 contract tests: `implemented` registry set == `passives.IMPLEMENTED_PASSIVES` (14); "other passives have no damage bonus" restricted to the 7 not-implemented keys. (b) Through the real `/battles/{id}/action` harness (REAL buffs, real engine via `_DamageSpy`, 3-participant `_state` variant for splash/Gladiator/Inquisitor-ally): per passive one end-to-end case asserting HP and log (`passives` entries, `forced_crit`, `extra_hit`, deceit event with `dodged+deceived`, `passive_proc` kinds, `mana_discount`) — incl. edge cases from §1: splash target died from main hit / only primary alive → duel variant; mid-battle joiner enables splash; splash doesn't chain; Inquisitor ally benefits; Saber kill by DoT tick credited, kill stack raises damage in the same battle and is written to the Redis key; Saber seed read in `_assemble_battle` with `dungeon_session_id`; Gladiator stun-skipped turn not counted; Monk immunity via each kind of site (attack, support, item, coating); Agent re-roll lands a failed effect on crit, nothing on non-crit, primary effects still applied on dodge as before; Trickster/Salamander durations; Caster can afford a skill only with discount, insufficient otherwise → 400 Russian message; scrolls count (Inquisitor mark, Archer, Assassin). (c) Old-state attack: no `is_npc`/`passive_state`/`dungeon_session_id` → resolves, no passive keys. (d) Plumbing: `is_npc`/`passive_state`/`dungeon_session_id` in `init_battle_state`, all 4 construction paths, join; `passive_state` absent from the Mongo snapshot; Redis key helpers TTL + soft-fail. (e) Regression: a battle with no passive owners produces identical events to the pre-feature expectation (existing suites green). |
| **Acceptance Criteria** | Full battle-service suite green in the container; no test passes only via a swallowed exception; rolls pinned (no flaky tests over 20 repeated runs of the new files). |

### Task 8 — QA: skills-service registry tests
| Field | Value |
|---|---|
| **Agent** | QA Test |
| **Status** | DONE |
| **Files** | `services/skills-service/app/tests/test_character_subclass_internal.py` (:372-375) |
| **Depends On** | 1 |
| **Description** | Replace "only berserker_rage implemented" with the exact 14-key set; assert Inquisitor description mentions non-physical resists and Trickster description has no redirect sentence; Berserk unchanged. |
| **Acceptance Criteria** | skills-service suite green in the container. |

### Task 9 — Review
| Field | Value |
|---|---|
| **Agent** | Reviewer |
| **Status** | DONE (Review #1 FAIL → Review #2 PASS, see §5) |
| **Files** | all of the above |
| **Depends On** | 1, 2, 3, 4, 5, 6, 7, 8 |
| **Description** | Review per `agents/reviewer.md`: decisions D1–D19 honoured (all rolls/logic in `passives.py`, no `buffs`/`battle_engine` imports there, single landing wrapper over all 8 sites, `_strike` used by all damage paths, no recursion, `.get` on new keys, stun/paralysis durations never bumped, FEAT-188 keys kept), frontend rules (TS, Tailwind, no `React.FC`, design system, Russian, 360px), docs + ISSUES updated. Re-run `py_compile`, both pytest suites, `tsc --noEmit`, `npm run build` (inside Docker). **Live:** local battles (test creds / dungeon test run memory) with characters of several subclasses — verify in 2D log and 3D Chronicle: Archer first-blood crit line, Mechanic/Sparkmage extra hit vs 2+ mobs and duel variant vs 1, Trickster deceit animates as dodge, Monk immunity line, Inquisitor stacks, Caster discounted cost on skill cards and in `resource_spend`, Saber kill stacks carried to the next dungeon battle; badges no longer show «пока не действует в бою» for the 13; zero console errors. |
| **Acceptance Criteria** | All checks green, live verification recorded; PASS/FAIL in §5. |

---

## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-10-31 — **FAIL** (2 small fixes, everything else verified)

#### Scope reviewed
FEAT-189 diff only (FEAT-188 parts already PASSed): battle-service `passives.py` (new), `main.py`
(`_filter_effects_by_chance`, `_pay_skill_costs`, `build_participant_info`/`_participant_payload`/`_assemble_battle`/join
dict, `_make_action_core` helpers `_roll_enemy_effects`/`_land_enemy_effects`/`_finish_target_ctx`/`_build_target_ctx`/
`_strike`/`_finish_passive_attack`, step 9.5), `battle_engine.py` (3 kwargs), `redis_state.py`; skills-service
`subclasses.py`; frontend `useBattleBar.tsx`, `utils/passiveCosts.ts`, `SkillPicker.tsx`, `SkillHand.tsx` and the
scope addition (Caster discount in the full card / slot tooltip / profile: `ResolvedSkillCard.tsx`, `SkillsTab.tsx`,
`InventoryItem.tsx`, `ActionBar.tsx`, `SlotMedallion.tsx`, `BattlePageBar.tsx`, `ItemSkillCircle.tsx`); tests; docs.

#### Correctness vs §1 / `docs/SUBCLASS-PASSIVES.md` (code review)
| Passive | Verdict |
|---|---|
| Inquisitor | OK — mark on any non-physical resolved entry (scrolls too), +1 stack per attack per landed marked target, cap 5, −3×n on all 8 NON_PHYSICAL types for every attacker (allies benefit), physical untouched; log contribution now filtered by resolved type. |
| Saber | OK — +15% vs `is_npc is True`; kill stacks only with `dungeon_session_id`, +2/kill cap 10, immediate, DoT kills via D11, Redis key TTL 14 d soft-fail; PvP stack only from `is_npc is False` attacker, once per attack, cap 3. |
| Gladiator | OK — surplus counted at hit time from alive teams (`dropped_out` excluded), +8%/+4% ×min(3); ramp +3%/own non-skipped turn cap 15; works in every battle type. |
| Agent | OK — D5 conditional re-roll gives exactly min(100, p+bonus); +10 for hard control; coating gets the pp directly on critted targets; non-Agents consume no roll. |
| Lancer | OK — steals min(2, current) of dodge and crit (target never below 0), cap 5 stacks, affects next attacks only; stolen crit also applies when the victim attacks (H5 on attacker attrs). |
| Mechanic / Sparkmage | OK — decided once per attack after the loop; candidates = alive enemies ≠ primary *now*; fresh dodge/deceit roll; `is_extra` short-circuits H3/H8/H9/H10 (no recursion, no first blood/Agent/coating); echo only if primary alive; duel +35% decided at attack begin. |
| Archer | OK — forced crit +50 (×1.75) per target until its first landed hit; dodge does not consume it. |
| Assassin | OK — shadow only on a real dodge (not deceit), consumed by the next attack (Q2), execute strictly < 30%. |
| Trickster | OK — 10% deceit rolled only if not dodged and only vs enemies; redirect seam returns None; +1 turn on enemy rows except stun / poison-paralysis and instant resource rows. |
| Monk | OK — +10/+5 pp on control rows; first control (name-based, incl. raw `attribute_key="random"`) dropped once per battle through the single landing wrapper covering all 8 sites. |
| Salamander | OK — stacks on consecutive landed fire hits on the same primary, reset on other target / no fire entry, cap 5; only `Burn` rows +1 turn. |
| Caster | Mechanics OK (25% of a *positive* magic resist, mana −10% round-half-up before the affordability check). **Log bug — see Issue 1.** |

Other checks: stun/paralysis durations are never bumped (only Trickster/Salamander touch `duration`, both exclude hard control);
participants without a passive go through the same calls with the same objects (helpers return the original lists/dicts when
no contribution) — confirmed by the unchanged pre-existing suites; FEAT-188 `passive_key`/`passive_pct` still emitted for rage;
old Redis states safe (`.get` everywhere, `_ps_read` never creates keys, `pstate` lazy); `passives.py` imports neither `buffs`
nor `battle_engine`; every passive roll goes through `passives.roll_pct`/`pick`; skills registry `implemented` set (14) ==
`passives.IMPLEMENTED_PASSIVES` (also confirmed live via `GET /skills/subclasses`: 14 implemented, 7 not). Backend↔frontend log
contract matches §3.5 (`passives[]`, `forced_crit`, `resist_ignored_pct`, `extra_hit`/`extra_mult`, `deceived`, `passive_proc`
kinds, `mana_discount`); unknown kinds render nothing. Frontend: TSX only, Tailwind only, no `React.FC`, no new SCSS/JSX,
Russian strings, registry error shown via toast. No new endpoints / DB changes / secrets. Pydantic v1 untouched.

Minor, non-blocking note: `begin_attack` runs even for an attack skill with no damage entries, so such a skill would consume
the Assassin's shadow and reset Salamander kindling (`main.py`, `_actx = passives.begin_attack(...)` in the attack step).
Practically all attack skills have damage rows; leave as is or guard with `if _attack_entries`.
**FIXED (Backend Dev, 2026-10-31):** the skill path now calls `begin_attack` (and `_finish_passive_attack`) only when the
attack skill has damage rows, mirroring the item path (`_actx = None` otherwise). Tests: Assassin shadow and Salamander
stacks survive a debuff-only attack skill and are used by the next real hit.

#### Automated Check Results
- [x] `python -m py_compile` (main.py, passives.py, battle_engine.py, redis_state.py, skills_client.py, skills-service subclasses/crud/main/schemas, 3 new test files) — PASS
- [x] battle-service pytest (python:3.10-slim, `--asyncio-mode=auto`) — PASS, **1328 passed**
- [x] skills-service pytest — PASS, **386 passed**
- [x] `npx tsc --noEmit` (frontend container) — PASS, run twice (before and after the Caster-card scope addition)
- [x] `vite build` to /tmp (cleaned up) — PASS, run twice
- [x] `docker compose config` — PASS
- [x] Live verification — done (results below); 2 issues found

#### Live Verification Results (localhost only; battle-service + skills-service restarted first)
Test setup (all restored afterwards, see §6): temporary `tree_nodes.subclass_key` on local mage/rogue nodes 24/45/46/47/49 and
`character_tree_progress` rows for 763/764/761 to get Caster / Mechanic / Archer / Lancer / Trickster / Paladin / Inquisitor;
battles created with `POST /battles/` (310–315) and driven via the action API + UI; all force-finished via
`POST /battles/admin/{id}/force-finish`.
1. **Caster** (battle 310/314, Ашари 763): 2D picker shows 14 for «Энергетический луч» (raw 15); with mana set to exactly 14
   the skill is selectable and cast — `resource_spend {mana:14, mana_discount:1}`, mana 14→0; log «Расход … · Чистая энергия −1
   маны». 3D hand card shows 14 and is not greyed. Full skill card (2D info button, 3D hand info button, profile «Навыки»
   card) shows «~~15~~ 14 маны (−10% Чистая энергия)» — PASS. Profile list chip shows the discounted base cost (27 of 30) — OK
   (the base-vs-resolved mismatch in the list is pre-existing → ISSUES.md LOW).
2. **Mechanic** (battle 310, Годрик vs 2 mobs): splash after a few attacks — `extra_hit:"splash", extra_mult:0.4` on the other
   mob, 2D line «↳ осколок Годрик → Иттан-момэн −17 крит · Шрапнель: 40% урона» — PASS.
3. **Trickster** (battle 313/315, Аэлис → Годрик): deceit event `dodged:true, deceived:true` + contribution; 2D «Годрик обманул
   Аэлис · Обман», 3D Chronicle shows the same line; 3D animation = dodge by construction (`ArenaHud.tsx:69` keys on `dodged`) —
   the live animation itself was not captured on screen (finished before the screenshot) — PASS.
4. **Archer** (battle 311): first hit on each of 2 targets `forced_crit:true, crit_mul:1.75` with contribution; second hit on the
   same target normal ×1.25; 2D «· Первая кровь: крит +50%» — PASS.
5. **passive_proc** — Lancer (battle 312): dodged attack → no pin; landed hit → `pin {stolen:{dodge:2, critical_hit_chance:2},
   stacks:1}`, 2D «Годрик Пригвоздить крадёт у Иттан-момэн 2% уклонения, 2 п.п. шанса крита (стаков: 1)» — PASS.
6. **Badges**: profile passive badge of Аэлис as Paladin shows «пока не действует в бою»; as Inquisitor it does not — PASS
   (registry API: exactly the 14 implemented). Skill-tree page could not be screenshotted (renderer timed out in the
   automation tab), checked via the profile badge instead.
7. **390×844 iframe** of the 2D battle page: log lines wrap inside the panel, no overflow from the new segments — PASS
   (the page-level ~12 px horizontal scroll at 390 px is pre-existing layout, not touched by this feature).
Console: zero errors throughout. Network: no 4xx/5xx from the app (only my own deliberate API probes: 403 «Сейчас не ваш ход»
and 400 «Недостаточно энергии» while scripting turns).

#### Issues Found
| # | Severity | File:line | Role | Problem / fix |
|---|---|---|---|---|
| 1 | MEDIUM (misleading log, same class as the Inquisitor fix) | `services/battle-service/app/passives.py:683-688` (contribution added for every `magic` roll) + `services/battle-service/app/main.py:3073` (`_strike` copies it unconditionally) | Backend Developer (+ QA test) | Live battle 310: target with magic *vulnerability* (`resist_pct: -6.8`, no `resist_ignored_pct` in the log) still gets `{"key":"caster_pure_energy","kind":"resist_ignore","value":25}` → log shows «· Чистая энергия: пробивает 25% сопр.» on hits where nothing was ignored (also for 0 resist). Fix: in `_strike`, keep the Caster `resist_ignore` contribution only when the engine log has `resist_ignored_pct > 0` (ideally put that number of points in `value`, frontend already renders «пробивает N% сопр.» — or keep 25 but only on actual ignores). Add an integration test: vulnerable/zero magic resist → no contribution; positive resist → contribution. **FIXED (Backend Dev, 2026-10-31):** new `passives.attacker_contribs_for_log(contribs, log)` drops the Caster `resist_ignore` contribution unless the engine log has `resist_ignored_pct > 0`; `_strike` filters `tmods["contributions"]` through it (next to `defender_contribs_for_type`). Value stays 25 (share of the resist). Tests: 3 integration (−6.8 / 0 / +8 magic resist) + 5 unit. |
| 2 | MEDIUM (scope-addition item not working) | `services/frontend/app-chaldea/src/components/pages/BattlePage/CharacterSide/CharacterInventory/InventoryItem/InventoryItem.tsx:233-242`; slot value set at `useBattleBar.tsx:1107` | Frontend Developer | The selected-slot tooltip (2D `ItemSkillCircle`, 3D `SlotMedallion`) never renders «Затрата маны» for skills: the slot holds the flat snapshot `BattleSkill` row, which has no top-level `cost_mana` (only the BASE `skill.cost_mana`), so the new discounted line is dead code — live the tooltip shows only name + «Тип: Навык атаки» for Caster and non-Caster alike. Either show the RESOLVED cost there (the resolved rank is already loaded by the picker/hand — note `skill.cost_mana` is the base 30, not the level-15 15, so do not use it) with the same strike-through format, or drop the tooltip part and say so in §6. Not misleading today, but the scope item as claimed is not delivered. **Status: FIXED (Frontend Dev)** — on selection the 2D `SkillPicker` and 3D `SkillHand` now put the resolved rank's `cost_mana` (same `/skills/{id}/resolved` value the cards show) on the slot object, so `InventoryItem` renders «Затрата маны» with the existing Caster strike-through; non-Casters see the resolved cost plain; items unchanged; the action payload still sends only ids. tsc + vite build OK. |

Pre-existing, not FEAT-189 (logged): profile «Навыки» list chips show base cost while the card shows the resolved cost → `docs/ISSUES.md` (LOW).

### Review #2 — 2026-11-01 — **PASS**

Scope: the three Review #1 fixes only (everything else passed in Review #1).

#### Code review of the fixes
| # | Fix | Verdict |
|---|---|---|
| 1 | `passives.attacker_contribs_for_log` (`passives.py:758-774`) + `_strike` (`main.py:3072-3074`) | OK — drops only the Caster `resist_ignore` contribution and only when the engine log has no `resist_ignored_pct > 0` (the engine sets it only on a positive resist, `battle_engine.py:203`); all other contributions pass through; damage math untouched. |
| 2 | `SkillPicker.tsx:243-249`, `Arena3D/hud/SkillHand.tsx:482-484` put `resolved?.cost_mana` on the slot; `InventoryItem.tsx:106-108, 233-242` renders it | OK — the turn payload is built in `BattlePage.tsx:650-655` from ids only (verified live: request body `{"participant_id":719,"target_id":720,"ally_target_id":null,"skills":{"attack_skill_id":58,…,"item_id":null}}`); a missing resolved rank gives `cost_mana: undefined` → `!!item.cost_mana` is false → the line is hidden; items unchanged (no `cost_mana`). `passiveKey` reaches `InventoryItem` from `ItemSkillCircle.tsx:81` and `SlotMedallion.tsx:89`. |
| 3 | `main.py:3716-3725` (`_actx = … if _attack_entries else None`) and `main.py:3848-3853` | OK — mirrors the item path; `_finish_passive_attack` is skipped with it; the rage/`percent_damage_buffs` add is guarded by `_actx is not None`. |

#### Automated Check Results
- [x] `py_compile` — battle-service `main.py`, `passives.py`, `battle_engine.py`, `redis_state.py`, `skills_client.py`, `tests/test_passives*.py`; skills-service `subclasses.py` — PASS
- [x] battle-service pytest (python:3.10-slim, `--asyncio-mode=auto`) — PASS, **1338 passed**
- [x] skills-service pytest — PASS, **386 passed**
- [x] `npx tsc --noEmit` (frontend container) — PASS
- [x] `vite build` to /tmp (cleaned up) — PASS

#### Live Verification Results (localhost only; battle-service restarted, nginx reloaded)
Setup (restored afterwards, see §6): `tree_nodes.subclass_key='mage_caster'` on node 24 and progress row 105 (Ашари 763)
moved 25→24; magic resist of mobs 999942 / 999944 / 999945 temporarily −10 / 0 / +20. Battles 316 (non-Caster, Ашари as
Salamander), 317 (Caster vs the three mobs), 318 (Caster, 3D) — all finished (316/317 by kills, 318 via admin force-finish).
- (a) **Caster log.** «Энергетический луч» applies −8% magic resist first, so the effective resists were −18 / −8 / +9.
  Battle 317 turn 1 (target −18): 3 damage events, no `passives`, no `resist_ignored_pct`; 2D log has no «Чистая энергия:
  пробивает…» line, only «Расход: 14 маны · Чистая энергия −1 маны». Turn 8 (target −8): same, no line. Turn 4 (target +9):
  `resist_ignored_pct: 3` + `{"key":"caster_pure_energy","kind":"resist_ignore","value":25}` on each of the 3 hits, 2D log
  shows «· Чистая энергия: пробивает 25% сопр.» under each hit — PASS. (A literal 0 resist could not be hit live because of the
  skill's own debuff; covered by the new integration test.)
- (b) **Slot tooltip.** Non-Caster: 2D picker 15, tooltip «Затрата маны:15»; 3D (slot cleared and re-played from the hand)
  «Затрата маны:15». Caster: 2D picker 14, tooltip `Затрата маны: ~~15~~ 14 (−10% Чистая энергия)`; 3D hand card 14, medallion
  tooltip the same strike-through + note — PASS.
- (c) Console: zero errors. Network: no app 4xx/5xx during play; only my own probes (400 «Навык на перезарядке», 400 «Бой уже
  завершён» on force-finishing 316 after it ended by kill) and the expected 404 of `/battles/318/state` when reopening a
  force-finished battle.

#### Non-blocking notes (no re-review needed)
1. `InventoryItem.tsx:234-235` — for a non-Caster the line renders as «Затрата маны:15» (no space): the `<li>` is a flex
   container, and the label and the number are one anonymous flex item, so the 5 px gap does not apply (before this fix it
   was «Затрата маны: 15»). One-character fix: `Затрата маны:{" "}` — Frontend Developer, whenever convenient.
2. Pre-existing: `TooltipPortal` centres the tooltip with no viewport clamp, so on the left-edge 3D medallions the slot tooltip
   is cut off by the window edge (Caster −36 px: first letters of «Тип:» / «Затрата маны» hidden; smaller for others) →
   `docs/ISSUES.md` (LOW).

**Result: PASS** — T9 DONE; Status stays REVIEW for PM to close.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-10-31 — PM: фича создана (волна 1 пассивок), запускаю анализ
[LOG] 2026-10-31 — Analyst: анализ завершён — точки подключения всех 13 пассивок в battle-service, хранение стаков, данж-счётчик Сейбера (2 варианта), фронтенд-лог, тесты; главные риски — эффекты атаки до урона (Агент), моки buffs/battle_engine в тестах, атрибуция убийств
[LOG] 2026-10-31 — Analyst: обнаружен баг (AoE-навык бьёт по уже мёртвой цели следующими строками урона), добавлен в ISSUES.md (LOW)
[LOG] 2026-10-31 22:19 — Architect: спроектировано — все пассивки и броски в passives.py (14 хуков), общие обёртки в main.py (наложение эффектов, цель, удар), стаки Сейбера в Redis без миграции; 9 задач (5 разработка, 3 QA, ревью), новых API нет; 3 некритичных вопроса к PM (Лансер, Ассасин, округление маны)
[LOG] 2026-10-31 — Backend Dev: T1 готова — в реестре skills-service включены 13 пассивок (implemented=True, всего 14 с «Яростью»); Инквизитор — все не-физические сопротивления, у Фокусника убрано перенаправление (FEAT-190), у Гладиатора/Механика/Искромага «в дуэли» заменено на «не в меньшинстве» / «если других врагов нет»; обновлён docs/services/skills-service.md; py_compile OK
[LOG] 2026-10-31 — QA: T8 готова — тест реестра skills-service теперь ждёт ровно 14 включённых пассивок (Ярость + 13 волны 1) и 7 невключённых; добавлены проверки описаний (Инквизитор — все не-физические сопротивления, Фокусник без перенаправления, Гладиатор/Механик/Искромаг без «дуэли», Ярость без изменений); набор skills-service: 386 passed (было 379)
[LOG] 2026-10-31 — Frontend Dev: T5 готова — лог боя (2D-панель и 3D-хроника) показывает список `passives` (урон, сопротивления, гарантированный крит, пробитие, доп. удары «осколок/перескок/повтор», +1 ход эффекта, скидка маны), «Обман» Фокусника («X обманул Y»), события `passive_proc` (стаки Печати ереси, Пригвоздить, Охотник на чудовищ, Несгибаемость, Из тени, Гармония, Слабое место; неизвестные — молча); старые логи FEAT-188 рисуются как раньше. Новый utils/passiveCosts.ts (формула (raw*90+50)//100, таблица 0/1/5/10/15/25 → 0/1/5/9/14/23 проверена), скидка Кастера на карточках навыков в 2D-выборе и 3D-руке (и цена, и «не хватает маны»). tsc --noEmit и vite build в контейнере — OK
[LOG] 2026-10-31 — Backend Dev: T2 готова — passives.py: константы 13 пассивок, IMPLEMENTED_PASSIVES (14), хуки H0–H13 (roll_pct/pick — единственные источники случайности, броски только у владельцев пассивки, buffs/battle_engine не импортируются, старые состояния нейтральны); «Ярость» без изменений. В compute_damage_with_rolls добавлены force_crit / crit_damage_bonus / resist_ignore (по умолчанию поведение и лог прежние). Для T4: H8 record_strike принимает target_attrs (текущие уклонение/крит цели для кражи Лансера); actx["pct"] не включает «Ярость» (она остаётся на пути FEAT-188); H11c принимает caster_pid. py_compile OK, battle-service: 982 passed, 1 failed — ожидаемый контрактный тест FEAT-188 (implemented == _DAMAGE_PASSIVES), его переписывает T7
[LOG] 2026-10-31 23:05 — Backend Dev: T3 готова — is_npc и passive_state у каждого участника (старт боя, PvP-пути, вступление по заявке), dungeon_session_id в состоянии боя; is_npc берётся из characters.is_npc (запрос перенесён выше, им же регистрируется автобой); стаки Сейбера читаются из Redis-ключа забега (get/set_saber_run_stacks, мягкий отказ, TTL 14 дней), в Mongo-снапшот passive_state не попадает; py_compile OK, тесты battle-service 982/983 (падает только контрактный тест FEAT-188 implemented-флагов — его переписывает T7)
[LOG] 2026-10-31 — QA: T6 готова — новый tests/test_passives_wave1.py (224 теста): все 13 пассивок волны 1 (позитивные и негативные случаи, капы стаков, оба исхода каждого шанса через патч roll_pct/pick), «Ярость» без изменений, нейтральные участники и старые состояния (без passive_state/is_npc/dungeon_session_id) — без бросков и без создания passive_state (единственное исключение по дизайну — метка used_magic у применившего магию), мусорные значения не роняют хуки; новые параметры compute_damage_with_rolls (force_crit, crit_damage_bonus, resist_ignore, умолчания = старое поведение). 10 повторных прогонов — стабильно; весь battle-service: 1206 passed, 1 failed — ожидаемый контрактный тест FEAT-188 (переписывает T7). Багов в passives.py не найдено
[LOG] 2026-10-31 23:55 — Backend Dev: T4 готова — пассивки подключены в _make_action_core через общие хелперы: _roll_enemy_effects/_land_enemy_effects (все 8 мест наложения вражеских эффектов: Монах +п.п. и иммунитет к первому контролю, +1 ход Фокусника/Саламандра), _build_target_ctx (кража Лансера, сопротивления защитника, уклонение, «Обман» Фокусника; шов FEAT-190 возвращает None), _strike — один на цикл навыка, цикл свитка и доп. удары (H3, force_crit/crit_damage_bonus/resist_ignore передаются только когда не по умолчанию), после урона — стаки (H9), пере-бросок Агента по проваленным эффектам при крите, доп. удар Механика/Искромага; H1 после контроля, реальное уклонение → «Из тени»; скидка маны Кастера в _pay_skill_costs (mana_discount + passives в resource_spend); шаг 9.5 — убийства актёра (включая DoT) → on_kills и запись стаков Сейбера в Redis. Лог: passives / deceived / extra_hit / passive_proc — поля совпадают с formatBattleEvent фронта, правок фронта не понадобилось. Бой без пассивок — те же вызовы и события («Ярость» в одиночку пишет лог в формате FEAT-188). Обновлены docs/services/battle-service.md (раздел FEAT-189, ключи Redis) и docs/SUBCLASS-PASSIVES.md (опора 4 ✅, план п.5 — волна 1 ✅, перенаправление Фокусника → FEAT-190). py_compile OK; battle-service 1206 passed, 1 failed — ожидаемый контрактный тест FEAT-188 (T7); смоук через настоящий эндпоинт действия для каждого владельца пассивки (13 + свиток, убийство Сейбера в данже, Агент, Кастер) — без исключений; battle-service перезапущен локально, стартует чисто
[LOG] 2026-10-31 — QA: T7 готова — контрактные тесты FEAT-188 переписаны: implemented в реестре skills-service == passives.IMPLEMENTED_PASSIVES (ровно 14 ключей), 7 невключённых пассивок без эффекта. Новый tests/test_passives_wave1_integration.py (108 тестов) — всё через настоящий POST /battles/{id}/action с реальными buffs, формулой урона и модулем passives: защита от регрессии (бой без пассивок — те же события и аргументы формулы, ни одного броска пассивок, без ключа passives; меняется только used_magic), 7 невключённых пассивок инертны во всём конвейере; Сейбер (+15% по NPC, убийство тиком DoT засчитано владельцу, стаки пишутся через set_saber_run_stacks и сразу дают +2% в том же бою, Несгибаемость, посев через _saber_seed и _assemble_battle); «Обман» (dodged+deceived, без «Из тени»), +1 ход у Фокусника/Саламандра (не оглушение/паралич, путь навыка и предмета); «Из тени» после настоящего уклонения; Шрапнель/Цепная молния (один раз за атаку, только живой другой враг, свой бросок уклонения, без рекурсии, вступивший в бой включает осколок, мёртвая цель — без повтора); Монах на всех 6 местах наложения (атака, атака по всем, поддержка, защита, предмет, яд на оружии); Агент (перебросок после крита, на яде — +20 п.п., без крита — ничего, на уклонении эффекты как раньше); Кастер (10 маны при 9, mana_discount в resource_spend, 400 «Недостаточно маны: нужно 9, есть 8», у остальных 3 ключа, пробитие 25% магии); Гладиатор (ход под оглушением не считается, арена в атаке и защите); Инквизитор (стаки, выгода союзника, свиток = магия); Лансер (кража видна в следующей атаке); Арчер; Redis-ключ Сейбера (TTL, мягкий отказ), init_battle_state. В test_join_requests.py — 3 теста вступления (is_npc, passive_state, посев Сейбера в данже). Весь battle-service: 1319 passed, 0 failed; 20 повторных прогонов новых файлов — стабильно; порядок файлов не влияет (6 падений в обратном порядке есть и без новых файлов — существующая зависимость от порядка в test_battle_fixes/test_redis_state/test_pvp_invitations)
[LOG] 2026-10-31 — QA: найден баг (LOW, лог): «Печать ереси» добавляет вклад resist_pct −3×n в passives КАЖДОГО удара по цели со стаками, в т.ч. физического, хотя физическое сопротивление не меняется — в логе «сопр. −6%» на ударе, где ничего не срезано (passives.defender_resist_mods, вклад без учёта типа урона). Тест в набор не добавлен, передан PM
[LOG] 2026-10-31 — Backend Dev: баг «Печати ереси» в логе исправлен — новый passives.defender_contribs_for_type: в _strike вклады сопротивлений защитника фильтруются по итоговому типу урона из лога (вклад Инквизитора остаётся только на нефизических типах; Гладиатор/Несгибаемость Сейбера действуют на «all» — без изменений; пробитие Кастера уже фильтровалось по magic). Расчёт урона не менялся. Тесты: 2 интеграционных (физический удар — без вклада, магический — вклад −6) и 7 юнит-тестов фильтра; battle-service 1328 passed, 0 failed
[LOG] 2026-10-31 — Frontend Dev: скидка Кастера и в карточке навыка — полная карточка (ResolvedSkillCard: в бою из 2D-выбора и 3D-руки, во вкладке «Навыки» профиля) и подсказка выбранного слота (InventoryItem, 2D-панель и 3D-медальоны) показывают зачёркнутую исходную ману, цену со скидкой и «(−10% Чистая энергия)»; ключ пассивки в бою — useBattleBar.myPassiveKey (свой снапшот), в профиле — equipmentRules.subclass_key + реестр подклассов (ошибка реестра — тостом); в списке навыков профиля мана тоже со скидкой. Остальным персонажам без изменений. tsc --noEmit и vite build в контейнере — OK
[LOG] 2026-10-31 23:50 — Reviewer: автоматические проверки — py_compile OK, battle-service 1328 passed, skills-service 386 passed, tsc и vite build OK (дважды, до и после доработки карточки Кастера), docker compose config OK
[LOG] 2026-10-31 23:50 — Reviewer: живая проверка на localhost (бои 310–315, все завершены через force-finish) — скидка Кастера в 2D/3D-руке, полной карточке и профиле, навык за 14 маны при 14 мане прошёл; Шрапнель «осколок», «Первая кровь» ×1.75, «Обман» в 2D и 3D-летописи, Пригвоздить (passive_proc), значки «пока не действует» только у невключённых, лог на 390 px — ошибок в консоли нет
[LOG] 2026-10-31 23:50 — Reviewer: тестовые правки в локальной БД откатаны — subclass_key узлов 24/45/46/47/49 снова NULL, прогресс 105 (763) снова узел 25, 106 (761) снова 88, временная строка 107 (764) удалена, current_character пользователя 4 снова 763, HP/мана/энергия 761/763/764 и мобов 999922/999942/999944–999948 возвращены
[LOG] 2026-10-31 23:50 — Reviewer: обнаружен баг (вне фичи: в списке навыков профиля базовая цена, в карточке — с учётом уровня), добавлен в ISSUES.md (LOW)
[LOG] 2026-10-31 23:50 — Reviewer: Review #1 — FAIL: (1) в логе «Чистая энергия: пробивает 25% сопр.» пишется и когда ничего не пробито (уязвимость/0 сопротивления) — Backend Dev + тест; (2) подсказка выбранного слота вообще не показывает ману навыка, поэтому скидка там не видна — Frontend Dev (показать цену ранга или убрать пункт)
[LOG] 2026-10-31 — Frontend Dev: замечание 2 ревью исправлено — при выборе навыка в 2D-списке и 3D-руке в слот кладётся цена маны ранга (та же, что на карточке, из /skills/{id}/resolved, не базовая), поэтому подсказка выбранного слота (2D-кружок и 3D-медальон) показывает «Затрата маны»; у Кастера — зачёркнутая цена, цена со скидкой и «(−10% Чистая энергия)», у остальных — просто цена ранга; предметы без изменений, в запрос хода по-прежнему уходят только id. tsc --noEmit и vite build в контейнере — OK
[LOG] 2026-11-01 — Backend Dev: замечание 1 ревью исправлено — «Чистая энергия: пробивает 25% сопр.» пишется в лог только если движок реально срезал сопротивление (resist_ignored_pct > 0): новый passives.attacker_contribs_for_log, фильтр в _strike рядом с фильтром Инквизитора; при уязвимости и нулевом сопротивлении вклада нет. Расчёт урона не менялся. Тесты: 3 интеграционных (−6.8 / 0 / +8 сопр. магии) и 5 юнит-тестов фильтра
[LOG] 2026-11-01 — Backend Dev: некритичное замечание ревью исправлено — навык атаки без строк урона (только дебафф) больше не открывает атаку для пассивок (begin_attack и добивка атаки не вызываются, как у предметов): «Из тени» Ассасина не тратится, стаки «Разгорания» Саламандра не сбрасываются. Тесты: 2 интеграционных (тень и стаки переживают такой навык и срабатывают на следующем ударе). py_compile OK, battle-service 1338 passed, 0 failed
[LOG] 2026-11-01 00:20 — Reviewer: Review #2 — автопроверки: py_compile OK, battle-service 1338 passed, skills-service 386 passed, tsc --noEmit и vite build OK
[LOG] 2026-11-01 00:20 — Reviewer: живая проверка на localhost (бои 316–318) — у Кастера по цели с отрицательным сопротивлением магии строки «Чистая энергия: пробивает…» нет, по цели с положительным — есть на каждом ударе; подсказка выбранного слота в 2D и 3D: у Кастера «15» зачёркнуто, 14 и «(−10% Чистая энергия)», у не-Кастера просто 15; в запрос хода уходят только id; ошибок в консоли нет
[LOG] 2026-11-01 00:20 — Reviewer: тестовые правки в локальной БД откатаны — subclass_key узла 24 снова NULL, прогресс 105 (763) снова узел 25, сопротивление магии мобов 999942/999944/999945 снова 1, HP/мана/энергия 763 и мобов 999922/999942/999944–999946 возвращены, current_character пользователя 4 = 763
[LOG] 2026-11-01 00:20 — Reviewer: обнаружен баг (вне фичи: подсказка у левого края 3D-HUD уезжает за экран, TooltipPortal без прижатия к границам), добавлен в ISSUES.md (LOW)
[LOG] 2026-11-01 00:20 — Reviewer: Review #2 — PASS (некритично: у не-Кастера в подсказке «Затрата маны:15» без пробела — можно поправить одним символом). T9 DONE, статус остаётся REVIEW
[LOG] 2026-11-01 — PM: пробел «Затрата маны: 15» поправлен (InventoryItem.tsx, tsc ок), фича закрыта
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано
- Включены 13 пассивок волны 1: Инквизитор, Сейбер, Гладиатор, Агент, Лансер, Механик, Арчер, Ассасин, Фокусник (без перенаправления), Монах, Саламандр, Кастер, Искромаг. Вместе с «Яростью» работают 14 из 21.
- Вся логика и все случайные броски пассивок — в `battle-service/app/passives.py` (хуки H0–H13); `main.py` только вызывает хуки. 8 мест наложения эффектов на врагов сведены в общий помощник, один удар по цели — общая функция `_strike`.
- `compute_damage_with_rolls` получил необязательные `force_crit`, `crit_damage_bonus`, `resist_ignore` (по умолчанию — прежнее поведение).
- В состоянии боя: `is_npc`, `passive_state`, `dungeon_session_id`; стаки Сейбера на забег — ключ Redis с TTL 14 дней.
- Лог боя: список `passives` у событий, события `passive_proc`, «Обман» как уклонение с пометкой; фронт показывает всё в 2D и 3D.
- Скидка Кастера на ману — на карточках навыков (2D/3D), в полной карточке, в подсказке слота и во вкладке навыков профиля.
- Тесты: battle-service 1338 passed (+355 за фичу), skills-service 386 passed.

### Что изменилось от первоначального плана
- Пользователь уточнил: режим перескока Механика/Искромага и «Арены» Гладиатора определяется в момент удара; Гладиатор работает и против мобов.
- Пользователь попросил показывать скидку Кастера и в карточке навыка.
- Ревью #1 нашло 2 бага (лишняя строка «Чистая энергия» в логе, пустая «Затрата маны» в подсказке слота) + навыки без урона сбрасывали «Из тени»/стаки Саламандра — исправлено, ревью #2 PASS.

### Оставшиеся риски / follow-up задачи
- FEAT-190: щит (Паладин, Ауромант), вампиризм (Берсерк, Жрец), отражение (Хранитель), оплата HP (Некромант), бафы союзников (Бард, Эфириад), перенаправление «Обмана» в союзника атакующего (Фокусник).
- В ISSUES.md (LOW): подсказка у левого края 3D-HUD обрезается; в списке навыков профиля базовая цена вместо цены по уровню; в навыке после смерти цели следующие строки урона бьют по мёртвой цели.
- Существующий порядок тестов: 6 старых тестов падают при обратном порядке запуска (не из этой фичи).
