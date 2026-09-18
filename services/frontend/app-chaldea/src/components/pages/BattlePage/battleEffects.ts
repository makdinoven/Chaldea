// Shared, human-readable descriptions of battle effects (FEAT-143).
// Works uniformly on the normalized effect shape used both by
// `active_effects[pid]` (EffectCircle) and by the `apply_effects` log events
// (backend normalizes them before emitting): { name, attribute, magnitude, duration }.

import {
  COMPLEX_EFFECTS,
  DAMAGE_TYPES,
  STAT_MODIFIERS,
  PRIMARY_ATTR_OPTIONS,
} from "../../AdminSkillsPage/skillConstants";

export interface EffectLike {
  name?: string;
  attribute?: string;
  magnitude?: number;
  duration?: number;
}

export interface EffectDescription {
  label: string;
  detail: string;
  positive: boolean;
}

// Complex-effect families (lowercase names), mirroring the battle-service
// expansion so the tooltip shows the right unit per effect.
const PERIODIC_DAMAGE = ["bleeding", "burn"];
const PERCENT_MODIFIERS = ["armorbreak", "freeze", "electrify", "daze", "wet"];
const CONTROL_EFFECTS = ["stun", "knockdown", "windburn"];

export const pluralizeTurn = (count: number): string => {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} ход`;
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100))
    return `${count} хода`;
  return `${count} ходов`;
};

// Mirror of the battle-service `evaluate_control`: given a participant's active
// effects, report whether they lose the whole turn and which skill types are
// blocked. Used to warn the player on their own turn (FEAT-143 group B).
export const evaluateControl = (
  effects: EffectLike[] | undefined,
): { fullSkip: string | null; blocked: string[] } => {
  let fullSkip: string | null = null;
  const blocked = new Set<string>();
  for (const e of effects ?? []) {
    const name = (e.name ?? "").toLowerCase();
    const attr = (e.attribute ?? "").toLowerCase();
    if (name === "stun") fullSkip = fullSkip ?? "Stun";
    else if (name === "poison" && attr === "paralysis")
      fullSkip = fullSkip ?? "Poison";
    else if (
      (name === "knockdown" || name === "windburn") &&
      ["attack", "defense", "support"].includes(attr)
    )
      blocked.add(attr);
  }
  return { fullSkip, blocked: [...blocked] };
};

export const damageLabel = (value: string): string =>
  DAMAGE_TYPES.find((d) => d.value === value)?.label ?? value;

/**
 * FEAT-168 — cleanse rows (`effect_name === "Cleanse"`). `attribute_key` says
 * what the item removes; the engine never removes a full skip-turn control
 * (Stun / Poison-паралич), whatever the selector says.
 */
export const CLEANSE_EFFECT_NAME = "Cleanse";

export const CLEANSE_SELECTORS: { value: string; label: string }[] = [
  { value: "debuff", label: "чужие эффекты" },
  { value: "periodic_damage", label: "периодический урон" },
  { value: "control_partial", label: "частичный контроль" },
  { value: "stat_down", label: "ослабление характеристик" },
  { value: "all", label: "все эффекты" },
];

export const CLEANSE_HINT =
  "Полный контроль с пропуском хода (оглушение, паралич) не снимается никогда — это правило боя, а не настройка предмета.";

/** Selector -> Russian. An effect name (e.g. `Bleeding`) falls back to its own label. */
export const cleanseSelectorLabel = (key: string | null | undefined): string => {
  if (!key) return CLEANSE_SELECTORS[0].label;
  const known = CLEANSE_SELECTORS.find((s) => s.value === key);
  if (known) return known.label;
  const complex = COMPLEX_EFFECTS.find((c) => c.value === key);
  if (complex) return complex.label.toLowerCase();
  return key;
};

const complexOption = (name: string) =>
  COMPLEX_EFFECTS.find((c) => c.value === name);

const statLabel = (key: string): string =>
  STAT_MODIFIERS.find((m) => m.key === key)?.label.replace("(%)", "").trim() ??
  PRIMARY_ATTR_OPTIONS.find((a) => a.value === key)?.label ??
  key;

/**
 * Turn a raw effect into a readable Russian label + detail.
 * `label` names the effect, `detail` carries duration and magnitude with the
 * right unit (percent for buffs/resists, HP/turn for periodic effects, ± for
 * stat modifiers). `positive` is true for beneficial effects.
 */
export const describeEffect = (e: EffectLike): EffectDescription => {
  const name = e.name ?? "";
  const attr = e.attribute ?? "";
  const mag = e.magnitude ?? 0;
  const dur = e.duration ?? 0;
  const turns = dur ? pluralizeTurn(dur) : "";
  const join = (parts: string[]) => parts.filter(Boolean).join(", ");

  // Damage buff — percent_damage[_type] or "Buff: type"
  if (
    attr === "percent_damage" ||
    attr.startsWith("percent_damage_") ||
    /^buff\s*:/i.test(name)
  ) {
    const type =
      attr === "percent_damage"
        ? "all"
        : attr.startsWith("percent_damage_")
          ? attr.slice("percent_damage_".length)
          : name.replace(/^buff\s*:\s*/i, "").toLowerCase();
    const dt = type === "all" ? "" : damageLabel(type);
    return {
      label: `Изменение урона${dt ? ` (${dt})` : ""}`,
      detail: join([turns, mag ? `${mag}%` : ""]),
      positive: mag >= 0,
    };
  }

  // Resist — percent_resist[_type] or "Resist: type"
  if (
    attr === "percent_resist" ||
    attr.startsWith("percent_resist_") ||
    /^resist\s*:/i.test(name)
  ) {
    const type =
      attr === "percent_resist"
        ? "all"
        : attr.startsWith("percent_resist_")
          ? attr.slice("percent_resist_".length)
          : name.replace(/^resist\s*:\s*/i, "").toLowerCase();
    const dt = type === "all" ? "" : damageLabel(type);
    const magPart = mag ? `${mag}%${mag < 0 ? " (уязвимость)" : ""}` : "";
    return {
      label: `Изменение защиты${dt ? ` (${dt})` : ""}`,
      detail: join([turns, magPart]),
      positive: mag >= 0,
    };
  }

  // Cleanse (FEAT-168) — an item that strips effects. `attribute` is the
  // selector, `magnitude` the cap (0 / empty = all matching).
  if (name === CLEANSE_EFFECT_NAME) {
    const limit = mag > 0 ? `не более ${Math.round(mag)}` : "";
    return {
      label: `Очищение: ${cleanseSelectorLabel(attr)}`,
      detail: join([limit]),
      positive: true,
    };
  }

  // Complex effect — Bleeding, Burn, ArmorBreak, Holy, Stun, ... The magnitude
  // unit depends on the effect family (mirrors the backend expansion).
  const complex = complexOption(name);
  if (complex) {
    const key = name.toLowerCase();
    const isPeriodic =
      PERIODIC_DAMAGE.includes(key) ||
      (key === "poison" && attr === "periodic_damage");
    const isPercentMod = PERCENT_MODIFIERS.includes(key);
    const isControl = CONTROL_EFFECTS.includes(key);

    let magPart = "";
    let positive = false;
    if (isPeriodic) {
      magPart = mag ? `−${Math.abs(mag)} HP/ход` : "";
    } else if (isPercentMod) {
      magPart = mag ? `${Math.abs(mag)}%` : "";
    } else if (isControl) {
      magPart = ""; // control effects carry no magnitude, only a duration
    } else {
      // Attribute modifiers (Holy / Curse / MagicImpact / Poison subtypes).
      magPart = mag ? `${mag > 0 ? "+" : ""}${mag}` : "";
      positive = key === "holy" || mag > 0;
    }
    return { label: complex.label, detail: join([turns, magPart]), positive };
  }

  // Stat modifier — attribute holds the stat key.
  const key = attr || name;
  const sign = mag > 0 ? "+" : "";
  return {
    label: statLabel(key),
    detail: join([turns, mag ? `${sign}${mag}` : ""]),
    positive: mag >= 0,
  };
};
