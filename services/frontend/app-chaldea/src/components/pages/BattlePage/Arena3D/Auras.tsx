import type { ArenaEffect, AuraKind } from "./arenaTypes";

// The portrait sits inside the gilded frame (3px) and its dark mat (2px).
const PORTRAIT = "pointer-events-none absolute inset-[5px] overflow-hidden rounded-[9px]";

/** Every lingering state on the fighter, once each. */
export const auraKindsOf = (effects: ArenaEffect[]): AuraKind[] => [
  ...new Set(effects.flatMap((e) => (e.aura ? [e.aura] : []))),
];

// How each state grades the portrait itself: cold and drained, damp and dark, and so on.
const PORTRAIT_FILTER: Partial<Record<AuraKind, string>> = {
  freeze: "saturate(0.6) brightness(0.97)",
  wet: "brightness(0.86) contrast(1.06)",
  curse: "brightness(0.72) saturate(0.6)",
  holy: "brightness(1.06) sepia(0.18)",
};

/** CSS filter for the portrait under these states, or undefined for none. */
export const portraitFilterOf = (kinds: AuraKind[]) =>
  kinds.map((k) => PORTRAIT_FILTER[k]).filter(Boolean).join(" ") || undefined;

export const GILDED_FRAME = "bg-[linear-gradient(145deg,#f6e3a1_0%,#b8913f_28%,#6e5320_52%,#d8b866_78%,#7a5c24_100%)]";

// The frame's metal under a state, most telling first: rime silvering the gilding,
// tarnished and dull where the armour gave, dark and glossy when soaked.
const FRAME_FINISH: [AuraKind, string][] = [
  ["freeze", "bg-[linear-gradient(145deg,#eef6f8_0%,#a8bcc4_28%,#55666e_52%,#cbdade_78%,#5d6c72_100%)]"],
  ["armorbreak", "bg-[linear-gradient(145deg,#7c7364_0%,#4c4436_28%,#221e18_52%,#5c5444_78%,#2a2620_100%)]"],
  ["wet", "bg-[linear-gradient(145deg,#d9c27e_0%,#8a6a2a_28%,#3e2e12_52%,#b8964c_78%,#4e3a16_100%)]"],
];

/** The frame's gradient under these states. */
export const frameFinishOf = (kinds: AuraKind[]) =>
  FRAME_FINISH.find(([k]) => kinds.includes(k))?.[1] ?? GILDED_FRAME;

// A wash laid over the portrait, on top of its filter.
const WASH: Partial<Record<AuraKind, string>> = {
  // Cold blue creeping in, a breath of rime at the very edges.
  freeze: "bg-[#5f8fb8]/25 mix-blend-color shadow-[inset_0_0_10px_1px_rgba(200,228,248,0.3)]",
  // A damp sheen catching the light across it.
  wet: "bg-[linear-gradient(115deg,transparent_30%,rgba(200,225,255,0.12)_45%,transparent_60%)]",
  // Shadow closing in from the edges.
  curse: "bg-[radial-gradient(ellipse_at_50%_45%,transparent_40%,rgba(18,4,26,0.6)_100%)]",
  // Warm light from below.
  holy: "bg-[radial-gradient(ellipse_at_50%_100%,rgba(255,210,120,0.22),transparent_70%)] mix-blend-screen",
  // Now and then the portrait jolts white, as the charge runs through it.
  electrify: "animate-aura-jolt bg-[#cfe8ff] mix-blend-screen opacity-0",
};

/**
 * What the lingering states do to the card itself: only light and colour on the
 * portrait. Their substance — ice, flakes, puddles, smoke — is on the board (AuraBoard).
 */
const Auras = ({ kinds }: { kinds: AuraKind[] }) => (
  <>
    {kinds.map((kind) =>
      WASH[kind] ? <div key={kind} className={`${PORTRAIT} z-[2] ${WASH[kind]}`} /> : null,
    )}
  </>
);

export default Auras;
