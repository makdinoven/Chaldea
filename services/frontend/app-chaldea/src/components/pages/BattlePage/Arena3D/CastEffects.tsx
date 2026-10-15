/** An effect landing on a card; `id` restarts the show for each new cast. */
export interface CastFx {
  id: number;
  /** Every new effect helps the fighter (buff) — otherwise it is a debuff. */
  positive: boolean;
  /** Cast on themselves: rings rise from the card instead of a seal closing on it. */
  self: boolean;
}

const TONE = {
  buff: {
    ring: "border-[#7ef0a6] shadow-[0_0_14px_rgba(110,232,154,0.9),inset_0_0_10px_rgba(110,232,154,0.6)]",
    flash: "bg-[radial-gradient(ellipse_at_50%_50%,rgba(130,240,170,0.55),transparent_70%)]",
  },
  debuff: {
    ring: "border-[#ef6aa8] shadow-[0_0_14px_rgba(209,75,143,0.9),inset_0_0_10px_rgba(209,75,143,0.6)]",
    flash: "bg-[radial-gradient(ellipse_at_50%_50%,rgba(209,75,143,0.55),transparent_70%)]",
  },
} as const;

/** Rings of light rising from the foot of the card: a buff on oneself. */
const RisingRings = ({ tone }: { tone: (typeof TONE)[keyof typeof TONE] }) => (
  <>
    {["0s", "0.25s", "0.5s"].map((delay) => (
      <span
        key={delay}
        className={`pointer-events-none absolute inset-x-[-10%] bottom-[2%] z-[6] h-[22%] animate-cast-rise rounded-[50%] border-2 opacity-0 ${tone.ring}`}
        style={{ animationDelay: delay }}
      />
    ))}
    <div className={`pointer-events-none absolute inset-[5px] z-[2] animate-fx-fade rounded-[9px] opacity-0 mix-blend-screen ${tone.flash}`} />
  </>
);

/** A ring closing in on the card like a seal pressed into wax: an effect cast onto it. */
const Seal = ({ tone }: { tone: (typeof TONE)[keyof typeof TONE] }) => (
  <>
    <span className={`pointer-events-none absolute -inset-3 z-[6] animate-cast-seal rounded-[20px] border-2 opacity-0 ${tone.ring}`} />
    <div className={`pointer-events-none absolute inset-[5px] z-[2] animate-fx-fade rounded-[9px] opacity-0 mix-blend-screen ${tone.flash}`} />
  </>
);

const HEAL_SPARKS = [
  { left: "14%", delay: "0s", size: 9 },
  { left: "30%", delay: "0.25s", size: 7 },
  { left: "46%", delay: "0.1s", size: 11 },
  { left: "62%", delay: "0.35s", size: 8 },
  { left: "78%", delay: "0.15s", size: 10 },
  { left: "38%", delay: "0.5s", size: 6 },
];

/** Green glints shaped like little crosses drifting up the portrait: HP restored. */
export const HealSparkles = () => (
  <div className="pointer-events-none absolute inset-[5px] z-[3] overflow-hidden rounded-[9px]">
    <div className="absolute inset-0 animate-fx-fade bg-[radial-gradient(ellipse_at_50%_90%,rgba(110,232,154,0.5),transparent_70%)] opacity-0 mix-blend-screen" />
    {HEAL_SPARKS.map((sp) => (
      <svg
        key={sp.left}
        viewBox="-5 -5 10 10"
        className="absolute bottom-1 animate-heal-rise opacity-0"
        style={{ left: sp.left, width: sp.size, height: sp.size, maxWidth: "none", animationDelay: sp.delay, filter: "drop-shadow(0 0 3px rgba(110,232,154,0.95))" }}
      >
        <path d="M-1.4 -5 H1.4 V-1.4 H5 V1.4 H1.4 V5 H-1.4 V1.4 H-5 V-1.4 H-1.4 Z" fill="#c8ffd8" />
      </svg>
    ))}
  </div>
);

const CastEffects = ({ fx }: { fx: CastFx }) => {
  const tone = TONE[fx.positive ? "buff" : "debuff"];
  return fx.self ? <RisingRings key={fx.id} tone={tone} /> : <Seal key={fx.id} tone={tone} />;
};

export default CastEffects;
