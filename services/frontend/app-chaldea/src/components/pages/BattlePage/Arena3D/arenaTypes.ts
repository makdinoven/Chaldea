import type { DotKind as EffectDotKind } from "../battleEffects";

/** Damage-over-time families on the arena: the effect ones plus a plain "HP −"
 * stat modifier with a duration, which drains rather than bleeds. */
export type DotKind = EffectDotKind | "drain";
export type FighterSide = "ally" | "enemy";

export interface ArenaEffect {
  /** Stable per effect instance, so a newly applied one can be told apart. */
  key: string;
  label: string;
  detail: string;
  positive: boolean;
  duration: number;
  /** Damage-over-time family, so its rune can flare when it ticks. */
  dot: DotKind | null;
  /** Lingering state this effect paints on the card, if any. */
  aura: AuraKind | null;
  /** Picture on its rune. */
  icon: EffectIcon;
}

export type FighterSelection = "target" | "ally" | null;

/** Which picture an effect's rune carries (drawn from Game Icons in EffectRunes.tsx). */
export type EffectIcon =
  | "bleeding" | "burn" | "poison" | "paralysis" | "stun" | "knockdown" | "windburn"
  | "armorbreak" | "freeze" | "electrify" | "wet" | "holy" | "curse" | "daze"
  | "magicImpact" | "cleanse"
  | "critChance" | "critDamage" | "dodge" | "hp" | "mana" | "energy" | "stamina"
  | "strength" | "agility" | "intelligence" | "endurance" | "damage"
  | "buff" | "debuff"
  | "resist" | "resistDown" | "resistFire" | "resistIce" | "resistLightning" | "resistMagic"
  | "rune";

const COMPLEX_ICONS: Record<string, EffectIcon> = {
  bleeding: "bleeding",
  burn: "burn",
  stun: "stun",
  knockdown: "knockdown",
  windburn: "windburn",
  armorbreak: "armorbreak",
  freeze: "freeze",
  electrify: "electrify",
  wet: "wet",
  holy: "holy",
  curse: "curse",
  daze: "daze",
  magicimpact: "magicImpact",
  cleanse: "cleanse",
};

const STAT_ICONS: Record<string, EffectIcon> = {
  critical_hit_chance: "critChance",
  crit_chance: "critChance",
  critical_damage: "critDamage",
  crit_damage: "critDamage",
  dodge: "dodge",
  dodge_chance: "dodge",
  hp: "hp",
  mana: "mana",
  energy: "energy",
  stamina: "stamina",
  strength: "strength",
  agility: "agility",
  intelligence: "intelligence",
  endurance: "endurance",
  damage: "damage",
};

// Resist icons for the elements that have a shield of their own.
const RESIST_ICONS: Record<string, EffectIcon> = {
  fire: "resistFire",
  ice: "resistIce",
  electricity: "resistLightning",
  magic: "resistMagic",
};

/** The rune picture for an effect, from its name, attribute and sign. */
export const effectIconOf = (e: { name?: string; attribute?: string; magnitude?: number }): EffectIcon => {
  const name = (e.name ?? "").toLowerCase();
  const attr = (e.attribute ?? "").toLowerCase();
  const down = (e.magnitude ?? 0) < 0;
  if (name === "poison") return attr === "paralysis" ? "paralysis" : "poison";
  if (COMPLEX_ICONS[name]) return COMPLEX_ICONS[name];
  if (name.startsWith("buff:") || attr.startsWith("percent_damage")) return down ? "debuff" : "buff";
  if (name.startsWith("resist:") || attr.startsWith("percent_resist") || attr.startsWith("res_")) {
    if (down) return "resistDown";
    const element = attr.replace(/^(percent_resist_|res_)/, "");
    return RESIST_ICONS[element] ?? "resist";
  }
  return STAT_ICONS[attr] ?? "rune";
};

/** Lingering states painted on a card for as long as they last (see Auras.tsx). */
export type AuraKind = "holy" | "curse" | "armorbreak" | "freeze" | "electrify" | "wet";

/** Which lingering state an effect paints on the card, by its name. */
export const auraKindOf = (name?: string | null): AuraKind | null => {
  switch ((name ?? "").toLowerCase()) {
    case "holy":
      return "holy";
    case "curse":
      return "curse";
    case "armorbreak":
      return "armorbreak";
    case "freeze":
      return "freeze";
    case "electrify":
      return "electrify";
    case "wet":
      return "wet";
    default:
      return null;
  }
};


export type ControlSkip = "Stun" | "Poison";
export type BlockedSkill = "attack" | "defense" | "support";

/** Control effects on a fighter right now (mirror of battle-service evaluate_control). */
export interface FighterControl {
  /** The whole next turn is lost: Stun, or Poison-paralysis. */
  skip: ControlSkip | null;
  /** Skill types Knockdown / Windburn block on the next turn. */
  blocked: BlockedSkill[];
}

export interface ArenaFighter {
  participantId: number;
  name: string;
  avatar: string | null;
  side: FighterSide;
  hp: number;
  maxHp: number;
  mana: number;
  maxMana: number;
  energy: number;
  maxEnergy: number;
  effects: ArenaEffect[];
  control: FighterControl;
  isActing: boolean;
  isDead: boolean;
  isSelf: boolean;
  selection: FighterSelection;
  selectable: boolean;
}

export interface ArenaAim {
  from: number;
  to: number;
  kind: "attack" | "ally";
}

export type EvasionKind = "dodge" | "miss" | "absorb";

/** What the newest turn's log says beyond HP: crits and blows that never landed. */
export interface TurnOutcome {
  /** Turn number the log belongs to — matched against the HP change it explains. */
  turn: number;
  /** performance.now() when the log arrived; each new outcome replays once. */
  at: number;
  /** Participants a direct blow landed on (damage > 0, not dodged / missed). */
  hits: number[];
  /** Damage type of the first blow that hurt each of them — picks how the blow looks. */
  hitTypes: Record<number, string>;
  /** Damage-over-time ticks this turn. */
  ticks: { target: number; kind: DotKind; amount: number }[];
  /** Control that fired this turn: a lost turn, or skill types cut from the action. */
  controls: ({ who: number; kind: "skip"; control: ControlSkip } | { who: number; kind: "block"; skill: BlockedSkill })[];
  /** Participants who took a critical hit. */
  crits: number[];
  /** Blows that did no harm: `dodge` — the target stepped aside; `miss` — the attacker
   * failed the hit roll; `absorb` — it landed, but resistances took all of it. */
  evasions: { source: number; target: number; kind: EvasionKind; damageType?: string }[];
}

export interface Evade {
  kind: EvasionKind;
  /** performance.now() when the card reacts (steps aside / shows the word). */
  at: number;
  /** Unit direction of the sidestep on the board (x, z). */
  away: [number, number];
}

/** A damage-over-time tick landing on a fighter: its families and total HP lost. */
export interface DotHit {
  kinds: DotKind[];
  amount: number;
  /** performance.now() when the tick's HP drop is released to the card. */
  at: number;
}

export interface ArenaSceneProps {
  fighters: ArenaFighter[];
  onSelect: (fighter: ArenaFighter) => void;
  aims: ArenaAim[];
  /** Absolute epoch ms when the current turn expires; null when unknown. */
  turnDeadline: number | null;
  turnPaused: boolean;
  /** Same-origin URL of the location art painted into the board, if any. */
  boardArtUrl: string | null;
  /** The newest turn's crits and evasions, from its log; null until a new turn is seen. */
  outcome: TurnOutcome | null;
  /** Completed turns of this battle; each one is notched into the table. */
  turnNumber: number;
}

// Mirrors battle-service TURN_TIMEOUT_HOURS (default 24) — only drives the rune-circle timer.
export const TURN_DURATION_MS = 24 * 60 * 60 * 1000;
