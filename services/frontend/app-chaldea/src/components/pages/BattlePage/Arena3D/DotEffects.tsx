import type { CSSProperties } from "react";
import type { DotKind } from "./arenaTypes";

/** A damage-over-time tick playing on a card; `id` restarts the show on each tick. */
export interface DotFx {
  id: number;
  kinds: DotKind[];
}

export const DOT_LABELS: Record<DotKind, string> = {
  bleeding: "Кровотечение",
  burn: "Горение",
  poison: "Яд",
  drain: "Иссушение",
};

// Tick numbers: smaller than a blow, each family in its own metal, with its name under it.
export const DOT_NUMBER_STYLE: Record<DotKind, string> = {
  bleeding:
    "bg-[linear-gradient(180deg,#ffd6d6_0%,#e0182e_45%,#4a0008_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(30,0,4,0.95)]",
  burn: "bg-[linear-gradient(180deg,#fff3c0_0%,#ff9a1e_45%,#8a2a00_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(40,12,0,0.95)]",
  poison:
    "bg-[linear-gradient(180deg,#efffd8_0%,#74d63c_45%,#1d4a06_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(6,24,2,0.95)]",
  drain:
    "bg-[linear-gradient(180deg,#f1e2ff_0%,#a463e8_45%,#2e0b52_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(16,4,30,0.95)]",
};
export const DOT_GLOW: Record<DotKind, string> = {
  bleeding: "[filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(220,20,50,0.6))]",
  burn: "[filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_14px_rgba(255,140,30,0.7))]",
  poison: "[filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(120,230,60,0.6))]",
  drain: "[filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(160,90,240,0.6))]",
};
export const DOT_LABEL_STYLE: Record<DotKind, string> = {
  bleeding: "text-[#ffb8bf]",
  burn: "text-[#ffd99a]",
  poison: "text-[#ccf7a8]",
  drain: "text-[#dcc4ff]",
};

// The portrait sits inside the gilded frame (3px) and its dark mat (2px).
const PORTRAIT = "pointer-events-none absolute inset-[5px] overflow-hidden rounded-[9px]";

const DRIPS = [
  { left: "14%", width: 3, length: "38%", delay: "0s" },
  { left: "33%", width: 5, length: "62%", delay: "0.15s" },
  { left: "57%", width: 4, length: "48%", delay: "0.05s" },
  { left: "79%", width: 3, length: "30%", delay: "0.25s" },
];
const DROPS = [
  { left: "30%", delay: "0.45s" },
  { left: "58%", delay: "0.7s" },
  { left: "44%", delay: "1s" },
];

/** Blood runs down the portrait and drips off the card's edge onto the board. */
const Bleeding = () => (
  <>
    <div className={PORTRAIT}>
      <div className="absolute inset-0 animate-fx-fade bg-[rgba(120,0,16,0.5)] opacity-0 mix-blend-multiply" />
      {DRIPS.map((d) => (
        <span
          key={d.left}
          className="absolute top-0 h-0 animate-blood-drip rounded-b-full bg-[linear-gradient(180deg,#4a0008,#b3101f_70%,#e8384a)]"
          style={{ left: d.left, width: d.width, animationDelay: d.delay, "--drip": d.length } as CSSProperties}
        />
      ))}
    </div>
    {DROPS.map((d) => (
      <span
        key={d.left}
        className="pointer-events-none absolute bottom-0 z-[4] h-2 w-1.5 animate-drop-fall rounded-full bg-[#b3001a] opacity-0 shadow-[0_0_3px_rgba(0,0,0,0.8)]"
        style={{ left: d.left, animationDelay: d.delay }}
      />
    ))}
  </>
);

const FLAMES = [
  { left: "2%", height: 30, delay: "0s" },
  { left: "20%", height: 42, delay: "0.12s" },
  { left: "39%", height: 52, delay: "0.04s" },
  { left: "58%", height: 40, delay: "0.18s" },
  { left: "76%", height: 32, delay: "0.08s" },
];
const SPARKS = [
  { left: "12%", dx: "-8px", delay: "0.1s" },
  { left: "28%", dx: "6px", delay: "0.35s" },
  { left: "45%", dx: "-4px", delay: "0.2s" },
  { left: "60%", dx: "10px", delay: "0.5s" },
  { left: "74%", dx: "-6px", delay: "0.3s" },
  { left: "88%", dx: "5px", delay: "0.6s" },
];

/** Flames lick up the lower edge of the card, throwing sparks. */
const Burn = () => (
  <>
    <div className={PORTRAIT}>
      <div className="absolute inset-0 animate-fx-fade bg-[radial-gradient(ellipse_at_50%_100%,rgba(255,140,30,0.75),transparent_65%)] opacity-0 mix-blend-screen" />
    </div>
    {FLAMES.map((f) => (
      <span
        key={f.left}
        className="pointer-events-none absolute bottom-2 z-[4] w-[24%] origin-bottom scale-y-0 animate-flame-lick rounded-[50%_50%_45%_45%/65%_65%_35%_35%] bg-[radial-gradient(ellipse_at_50%_85%,#fff6c0_0%,#ffc23a_30%,#ff6a14_60%,rgba(255,60,0,0)_75%)] opacity-0 mix-blend-screen"
        style={{ left: f.left, height: f.height, animationDelay: f.delay }}
      />
    ))}
    {SPARKS.map((sp) => (
      <span
        key={sp.left}
        className="pointer-events-none absolute bottom-4 z-[6] h-1 w-1 animate-spark-rise rounded-full bg-[#ffd27a] opacity-0 shadow-[0_0_4px_#ff9a2a]"
        style={{ left: sp.left, animationDelay: sp.delay, "--dx": sp.dx } as CSSProperties}
      />
    ))}
  </>
);

const BUBBLES = [
  { left: "12%", size: 8, delay: "0s" },
  { left: "27%", size: 12, delay: "0.3s" },
  { left: "44%", size: 7, delay: "0.15s" },
  { left: "58%", size: 10, delay: "0.45s" },
  { left: "72%", size: 6, delay: "0.1s" },
  { left: "84%", size: 9, delay: "0.35s" },
];

/** A sickly green haze rises through the portrait, full of bubbles. */
const Poison = () => (
  <div className={PORTRAIT}>
    <div className="absolute inset-0 animate-fx-fade bg-[rgba(50,120,20,0.4)] opacity-0 mix-blend-multiply" />
    <div className="absolute inset-0 animate-fx-fade bg-[radial-gradient(ellipse_at_50%_95%,rgba(130,235,70,0.6),transparent_70%)] opacity-0 mix-blend-screen" />
    {BUBBLES.map((b) => (
      <span
        key={b.left}
        className="absolute bottom-1 animate-poison-bubble rounded-full border border-[#c8ff9a]/80 bg-[#7be04a]/25 opacity-0"
        style={{ left: b.left, width: b.size, height: b.size, animationDelay: b.delay }}
      />
    ))}
  </div>
);

/** Life seeps out of the portrait: it greys and a violet shadow closes in from the edges. */
const Drain = () => (
  <div className={PORTRAIT}>
    <div className="absolute inset-0 animate-fx-fade bg-[rgba(40,10,70,0.45)] opacity-0 mix-blend-multiply" />
    <div className="absolute inset-0 animate-fx-fade bg-[radial-gradient(ellipse_at_50%_50%,transparent_35%,rgba(150,80,230,0.6)_100%)] opacity-0 mix-blend-screen" />
  </div>
);

const FX = { bleeding: Bleeding, burn: Burn, poison: Poison, drain: Drain } as const;

/** Plays every damage-over-time family that ticked on this card. */
const DotEffects = ({ fx }: { fx: DotFx }) => (
  <>
    {fx.kinds.map((kind) => {
      const Effect = FX[kind];
      return <Effect key={`${fx.id}-${kind}`} />;
    })}
  </>
);

export default DotEffects;
