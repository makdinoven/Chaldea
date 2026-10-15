import { useEffect, useId, useRef, useState } from "react";

export type VialKind = "hp" | "mana" | "energy";

// Liquid colours, deep and low-lit like everything else on the table: the surface
// catching a little candlelight, a near-black bottom, and the faint glow through the glass.
const LIQUID = {
  hp: { top: "#b4473a", bottom: "#2e0604", glow: "rgba(170,40,25,0.3)" },
  mana: { top: "#4f7eae", bottom: "#081530", glow: "rgba(50,100,170,0.3)" },
  energy: { top: "#c49a48", bottom: "#3a2205", glow: "rgba(190,140,50,0.28)" },
} as const;

// "+N" beside an orb that just filled, in the liquid's colour.
const GAIN_TEXT = {
  hp: "text-[#e8a090]",
  mana: "text-[#a8c8e8]",
  energy: "text-[#e8d29a]",
} as const;
// How long the fill flare and its "+N" stay up.
const GAIN_MS = 1300;

// Orb geometry in viewBox units: a glass sphere seen face-on.
const VIEW_W = 40;
const VIEW_H = 40;
const BODY_TOP = 2;
const BODY_BOTTOM = 38;
const BODY_PATH = "M20 2 A18 18 0 1 1 20 38 A18 18 0 1 1 20 2 Z";
// One wave period; the surface path spans two so it can slide one period and loop.
const WAVE_PERIOD = 20;
const WAVE_PATH = (() => {
  const amp = 1.4;
  let d = `M0 0`;
  for (let x = 0; x < VIEW_W + WAVE_PERIOD * 2; x += WAVE_PERIOD) {
    d += ` q${WAVE_PERIOD / 4} ${-amp} ${WAVE_PERIOD / 2} 0 t${WAVE_PERIOD / 2} 0`;
  }
  return `${d} V${VIEW_H} H0 Z`;
})();

interface VialProps {
  kind: VialKind;
  value: number;
  max: number;
  title: string;
  className: string;
}

/** A glass orb of the resource's liquid; it drains as the resource is spent. */
const Vial = ({ kind, value, max, title, className }: VialProps) => {
  const id = useId().replace(/:/g, "");
  const colors = LIQUID[kind];
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const level = BODY_BOTTOM - ratio * (BODY_BOTTOM - BODY_TOP + 1.5);

  // Filling up (a heal, restored mana / energy) flares the orb and floats "+N"
  // beside it; spending only lowers the liquid.
  const previous = useRef(value);
  const [gain, setGain] = useState<{ id: number; amount: number } | null>(null);
  useEffect(() => {
    const amount = Math.round(value - previous.current);
    previous.current = value;
    if (amount < 1) return;
    const next = { id: performance.now(), amount };
    setGain(next);
    const t = window.setTimeout(
      () => setGain((g) => (g?.id === next.id ? null : g)),
      GAIN_MS,
    );
    return () => window.clearTimeout(t);
  }, [value]);

  return (
    <div title={title} className={`relative ${className}`}>
      {gain && (
        <>
          <span
            key={`flare-${gain.id}`}
            className="pointer-events-none absolute inset-0 animate-vial-fill rounded-full"
            style={{ boxShadow: `0 0 14px 3px ${colors.glow}` }}
          />
          {/* HP already gets its big "+N" on the card; the orbs of mana / energy get theirs here. */}
          {kind !== "hp" && (
            <span
              key={`gain-${gain.id}`}
              className={`pointer-events-none absolute right-full top-1/2 mr-0.5 animate-gain-float whitespace-nowrap text-[11px] font-extrabold tabular-nums [-webkit-text-stroke:2px_rgba(0,0,0,0.85)] [paint-order:stroke_fill] sm:text-xs ${GAIN_TEXT[kind]}`}
            >
              +{gain.amount}
            </span>
          )}
        </>
      )}
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="h-full w-full overflow-visible"
        style={{
          filter: `drop-shadow(0 2px 3px rgba(0,0,0,0.9)) drop-shadow(0 0 4px ${ratio > 0 ? colors.glow : "transparent"})`,
        }}
      >
        <defs>
          <clipPath id={`${id}-body`}>
            <path d={BODY_PATH} />
          </clipPath>
          <linearGradient id={`${id}-liquid`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colors.top} />
            <stop offset="100%" stopColor={colors.bottom} />
          </linearGradient>
          <radialGradient id={`${id}-glass`} cx="35%" cy="55%" r="65%">
            <stop offset="0%" stopColor="rgba(255,240,210,0.04)" />
            <stop offset="100%" stopColor="rgba(8,6,4,0.75)" />
          </radialGradient>
        </defs>

        {/* Dark glass, then the liquid inside it */}
        <path d={BODY_PATH} fill={`url(#${id}-glass)`} />
        <g clipPath={`url(#${id}-body)`}>
          <g
            className="transition-transform duration-700 ease-out"
            style={{ transform: `translateY(${level}px)` }}
          >
            <g className="animate-liquid-wave">
              <path d={WAVE_PATH} fill={`url(#${id}-liquid)`} />
            </g>
          </g>
          {ratio > 0.15 && (
            <>
              <circle
                cx="14"
                cy={BODY_BOTTOM - 5}
                r="1.1"
                fill="rgba(255,240,215,0.4)"
                className="animate-vial-bubble"
              />
              <circle
                cx="25"
                cy={BODY_BOTTOM - 4}
                r="0.8"
                fill="rgba(255,240,215,0.35)"
                className="animate-vial-bubble [animation-delay:1.3s]"
              />
            </>
          )}
        </g>

        {/* A brass band round the glass like the card's gilding, a candlelit shine
            across the upper left, a glint low on the right */}
        <path
          d={BODY_PATH}
          fill="none"
          stroke="rgba(184,145,63,0.85)"
          strokeWidth="1.3"
        />
        <path
          d="M8 15 A13 13 0 0 1 16 7"
          fill="none"
          stroke="rgba(255,236,200,0.4)"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <circle cx="30" cy="29" r="1" fill="rgba(255,236,200,0.25)" />

        <text
          x={VIEW_W / 2}
          y="24"
          textAnchor="middle"
          className="fill-[#efe3c4] font-extrabold tabular-nums [paint-order:stroke_fill]"
          stroke="rgba(0,0,0,0.9)"
          strokeWidth="3"
          strokeLinejoin="round"
          fontSize={value >= 1000 ? 10 : 12}
        >
          {Math.max(0, Math.round(value))}
        </text>
      </svg>
    </div>
  );
};

export default Vial;
