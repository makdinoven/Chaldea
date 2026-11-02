/**
 * FEAT-195 — soft/hard cap of primary stats (diminishing returns).
 *
 * MIRRORS the canonical backend implementation
 * `services/character-attributes-service/app/stat_caps.py` (byte-identical
 * copies in battle-service and dungeon-service). Every display helper on the
 * frontend that turns a stat into something (resists, dodge, crit, resource
 * pools, damage, initiative) must go through `effectiveStat` — never re-derive
 * the thresholds locally.
 *
 *   x <= 100        -> x                       (negative values are linear too)
 *   100 < x <= 200  -> 100 + (x - 100) * 0.5
 *   x > 200         -> 150 + (x - 200) * 0.25
 *
 * The stat number itself (what the profile shows) is never capped — only what
 * it gives. The cap applies to the total: points + gear + food + perks + buffs.
 */

/** Full effect up to this value. */
export const STAT_SOFT_CAP = 100;
/** Half effect between the soft and the hard cap, quarter effect above. */
export const STAT_HARD_CAP = 200;
export const STAT_SOFT_RATE = 0.5;
export const STAT_HARD_RATE = 0.25;

/** eff(x) at the hard cap: 100 + 100 * 0.5 = 150. */
const EFF_AT_HARD_CAP = STAT_SOFT_CAP + (STAT_HARD_CAP - STAT_SOFT_CAP) * STAT_SOFT_RATE;

/** Effective value of a stat total. Non-numeric / non-finite input → 0. */
export const effectiveStat = (value: unknown): number => {
  const x = typeof value === 'number' ? value : Number(value ?? 0);
  if (!Number.isFinite(x)) return 0;
  if (x <= STAT_SOFT_CAP) return x;
  if (x <= STAT_HARD_CAP) return STAT_SOFT_CAP + (x - STAT_SOFT_CAP) * STAT_SOFT_RATE;
  return EFF_AT_HARD_CAP + (x - STAT_HARD_CAP) * STAT_HARD_RATE;
};

/** What a change of a stat from `oldValue` to `newValue` is worth: eff(new) − eff(old). */
export const effectiveDelta = (oldValue: unknown, newValue: unknown): number =>
  effectiveStat(newValue) - effectiveStat(oldValue);

/** Player-facing explanation of the cap (Russian UI text). */
export const STAT_CAP_NOTE =
  'Каждое очко до 100 работает в полную силу, от 100 до 200 — вдвое слабее, выше 200 — вчетверо слабее. ' +
  'Считается от суммы: очки, снаряжение, еда, перки и баффы.';

/** Short form for tooltips next to a single formula. */
export const STAT_CAP_SHORT = 'до 100 — полностью, 100–200 — вдвое слабее, выше 200 — вчетверо слабее';
