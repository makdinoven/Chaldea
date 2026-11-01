/**
 * Client mirror of subclass-passive cost modifiers (FEAT-189).
 *
 * The Caster's «Чистая энергия» makes every skill 10% cheaper in mana. The
 * battle-service charges `passives.mana_cost` = `(raw * (100 - 10) + 50) // 100`
 * (integer round-half-up) — see `services/battle-service/app/passives.py`
 * (`CASTER_MANA_DISCOUNT_PCT`). Keep the key, the percent and the formula in sync,
 * otherwise a skill card would show a price (or block a skill) the server disagrees with.
 *
 * Reference table: 0→0, 1→1, 5→5, 10→9, 15→14, 25→23.
 */

export const CASTER_PASSIVE_KEY = "caster_pure_energy";
export const CASTER_MANA_DISCOUNT_PCT = 10;
/** Player-facing note next to a discounted mana price. */
export const CASTER_MANA_DISCOUNT_NOTE = `−${CASTER_MANA_DISCOUNT_PCT}% Чистая энергия`;

/** Mana a skill actually costs the owner of `passiveKey` (the raw cost for everyone else). */
export const effectiveManaCost = (cost: number, passiveKey?: string | null): number => {
  if (passiveKey !== CASTER_PASSIVE_KEY) return cost;
  const raw = Math.max(0, Math.trunc(Number(cost) || 0));
  return Math.floor((raw * (100 - CASTER_MANA_DISCOUNT_PCT) + 50) / 100);
};

/**
 * FEAT-190 — the Necromancer's «Плата кровью»: a mana shortfall is paid with HP,
 * 1 mana = 1.5 HP, rounded up, and at least 1 HP must remain. Mirror of
 * `passives.blood_price` in `services/battle-service/app/passives.py`
 * (`BLOOD_HP_PER_MANA`, `BLOOD_MIN_HP_LEFT`). The server re-checks at payment;
 * this only decides what a card shows and whether it is clickable.
 *
 * Reference table (cost, mana, hp → hpCost, payable):
 *   (10, 0, 16 → 15, ✓)  (10, 0, 15.9 → 15, ✗)  (3, 2, 10 → 2, ✓)
 *   (1, 0, 2 → 2, ✗)     (1, 0, 3 → 2, ✓)        (5, 5, 1 → 0, ✓)
 */
export const NECROMANCER_PASSIVE_KEY = "necromancer_blood_price";
export const BLOOD_HP_PER_MANA = 1.5;
export const BLOOD_MIN_HP_LEFT = 1;
/** Player-facing rule, for cards that do not know the current bars. */
export const BLOOD_PRICE_NOTE = "нехватку маны можно доплатить здоровьем: 1 маны = 1,5 HP";

const num = (v: unknown): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

/** HP the owner of `passiveKey` pays on top when `cost` (already effective) exceeds `mana`; 0 otherwise. */
export const bloodPriceHp = (cost: number, mana: number, passiveKey?: string | null): number => {
  if (passiveKey !== NECROMANCER_PASSIVE_KEY) return 0;
  const shortfall = num(cost) - num(mana);
  if (shortfall <= 0) return 0;
  return Math.ceil(shortfall * BLOOD_HP_PER_MANA);
};

/** Whether a mana `cost` (already effective) can be paid — with HP for the Necromancer. */
export const canPayMana = (
  cost: number,
  mana: number,
  hp: number,
  passiveKey?: string | null,
): boolean => {
  if (num(cost) <= num(mana)) return true;
  if (passiveKey !== NECROMANCER_PASSIVE_KEY) return false;
  return num(hp) - bloodPriceHp(cost, mana, passiveKey) >= BLOOD_MIN_HP_LEFT;
};

/** Live bars a skill is paid from. */
export interface PayerBars {
  mana: number;
  energy: number;
  hp: number;
}

/** What one skill card costs the viewer right now (FEAT-189 discount + FEAT-190 blood price). */
export interface SkillPayment {
  /** Mana actually charged (Caster discount applied). */
  mana: number;
  /** HP the Necromancer pays on top; 0 for everyone else / when mana suffices. */
  hpCost: number;
  shortMana: boolean;
  shortEnergy: boolean;
  short: boolean;
  /** Russian hint for a card that cannot be paid; empty when payable. */
  shortText: string;
}

/**
 * Affordability of one skill for the owner of `passiveKey`. `rawMana` is the
 * resolved (level-adjusted) price; without `bars` nothing is ever short.
 */
export const skillPayment = (
  rawMana: number,
  energy: number,
  bars: PayerBars | null | undefined,
  passiveKey?: string | null,
): SkillPayment => {
  const mana = effectiveManaCost(rawMana, passiveKey);
  if (!bars) {
    return { mana, hpCost: 0, shortMana: false, shortEnergy: false, short: false, shortText: "" };
  }
  const necro = passiveKey === NECROMANCER_PASSIVE_KEY;
  const shortMana = !canPayMana(mana, bars.mana, bars.hp, passiveKey);
  const shortEnergy = num(energy) > num(bars.energy);
  const hpCost = shortMana ? 0 : bloodPriceHp(mana, bars.mana, passiveKey);
  const manaWord = necro ? "маны и здоровья" : "маны";
  const shortText = shortMana && shortEnergy
    ? `Не хватает ${necro ? "маны, здоровья" : "маны"} и энергии`
    : shortMana
      ? `Не хватает ${manaWord}`
      : shortEnergy
        ? "Не хватает энергии"
        : "";
  return { mana, hpCost, shortMana, shortEnergy, short: shortMana || shortEnergy, shortText };
};
