/**
 * How a blow looks, by its damage type. A blade gives a lunge and a slash on the
 * card; elements fly as their own missile and burst in their own colours.
 */
export type StrikeStyle =
  | "slash"
  | "pierce"
  | "crush"
  | "fire"
  | "ice"
  | "lightning"
  | "water"
  | "wind"
  | "arcane"
  | "holy"
  | "curse"
  | "bolt";

/** Damage types as battle-service logs them (`damage_type`) → the look of the blow. */
const BY_DAMAGE_TYPE: Record<string, StrikeStyle> = {
  physical: "slash",
  catting: "slash",
  piercing: "pierce",
  crushing: "crush",
  fire: "fire",
  ice: "ice",
  electricity: "lightning",
  watering: "water",
  wind: "wind",
  magic: "arcane",
  sainting: "holy",
  damning: "curse",
};

export const strikeStyleOf = (damageType?: string | null): StrikeStyle =>
  (damageType && BY_DAMAGE_TYPE[damageType]) || "bolt";

/** Blades have no missile: the attacker lunges and the blow lands at the lunge's peak. */
export const isMelee = (style: StrikeStyle) => style === "slash" || style === "pierce" || style === "crush";

// How long each kind of blow takes to land, in ms. A lunge peaks well before a
// thrown missile arrives; lightning charges for a beat, then strikes at once.
export const STRIKE_MS: Record<StrikeStyle, number> = {
  slash: 380,
  pierce: 340,
  crush: 440,
  fire: 850,
  ice: 700,
  lightning: 620,
  water: 820,
  wind: 760,
  arcane: 850,
  holy: 850,
  curse: 900,
  bolt: 850,
};

export interface StrikePalette {
  /** Missile core and its glow. */
  core: string;
  glow: string;
  /** Impact sparks: hot when shed, then warm, then cold as they die on the board. */
  hot: string;
  warm: string;
  cold: string;
  /** Flash of light at the impact. */
  light: string;
}

export const PALETTE: Record<Exclude<StrikeStyle, "bolt">, StrikePalette> = {
  // Steel on steel: white-hot sparks cooling to grey.
  slash: { core: "#ffffff", glow: "#d8dde6", hot: "#fffbe8", warm: "#ffd27a", cold: "#3a3a40", light: "#ffe7b0" },
  pierce: { core: "#ffffff", glow: "#d8dde6", hot: "#fffbe8", warm: "#ffd27a", cold: "#3a3a40", light: "#ffe7b0" },
  crush: { core: "#ffffff", glow: "#c9b79a", hot: "#fff1d0", warm: "#c99a5a", cold: "#2e241a", light: "#ffcf8a" },
  fire: { core: "#fff4c2", glow: "#ff6a14", hot: "#ffe1a0", warm: "#ff6a1a", cold: "#4a0e04", light: "#ff7a2a" },
  ice: { core: "#ffffff", glow: "#8fe0ff", hot: "#ffffff", warm: "#9fe4ff", cold: "#1a3c5a", light: "#9fe4ff" },
  lightning: { core: "#ffffff", glow: "#7fc8ff", hot: "#ffffff", warm: "#9fd6ff", cold: "#1a2a5a", light: "#a8dcff" },
  water: { core: "#e6f6ff", glow: "#3f8fe6", hot: "#d8efff", warm: "#4fa0ff", cold: "#0d2a52", light: "#5fb0ff" },
  wind: { core: "#f2fff8", glow: "#9fe8c8", hot: "#ffffff", warm: "#b8f0d8", cold: "#2a4a3e", light: "#c8f8e4" },
  arcane: { core: "#f6e8ff", glow: "#a24dff", hot: "#f0d8ff", warm: "#b066ff", cold: "#2a0e4a", light: "#b880ff" },
  holy: { core: "#fffbe6", glow: "#ffd75a", hot: "#ffffff", warm: "#ffe08a", cold: "#5a4410", light: "#ffe7a0" },
  curse: { core: "#ff9ab0", glow: "#8a1030", hot: "#ff7a90", warm: "#a0103a", cold: "#1a0208", light: "#c0204a" },
};

/** The bolt of old: coloured by the attacker's side. */
export const sidePalette = (side: string): StrikePalette => ({
  core: "#fff6d8",
  glow: side,
  hot: "#ffe1a0",
  warm: "#ff6a1a",
  cold: "#4a0e04",
  light: side,
});
