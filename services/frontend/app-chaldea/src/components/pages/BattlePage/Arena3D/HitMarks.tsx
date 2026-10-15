import type { StrikeStyle } from "./strikeStyles";

// Tint laid over the portrait for a moment as the blow lands, by its look.
const TINT: Record<StrikeStyle, string> = {
  slash: "bg-site-red mix-blend-multiply",
  pierce: "bg-site-red mix-blend-multiply",
  crush: "bg-site-red mix-blend-multiply",
  bolt: "bg-site-red mix-blend-multiply",
  fire: "bg-[radial-gradient(ellipse_at_50%_60%,rgba(255,150,40,0.9),rgba(160,20,0,0.6))] mix-blend-screen",
  ice: "bg-[rgba(170,225,255,0.55)] mix-blend-screen shadow-[inset_0_0_22px_8px_rgba(225,246,255,0.95)]",
  lightning: "bg-[rgba(200,230,255,0.85)] mix-blend-screen",
  water: "bg-[rgba(60,130,230,0.55)] mix-blend-screen",
  wind: "bg-[rgba(190,245,220,0.35)] mix-blend-screen",
  arcane: "bg-[radial-gradient(circle,rgba(190,110,255,0.85),rgba(80,20,150,0.4))] mix-blend-screen",
  holy: "bg-[radial-gradient(circle,rgba(255,240,180,0.95),rgba(255,200,80,0.35))] mix-blend-screen",
  curse: "bg-[radial-gradient(circle,rgba(160,10,50,0.75),rgba(20,0,10,0.8))] mix-blend-multiply",
};

const SLASH = (
  // A blade's slash wiping across the portrait
  <span className="pointer-events-none absolute left-[-20%] top-1/2 h-[3px] w-[140%] origin-left -rotate-[32deg] animate-slash bg-[linear-gradient(90deg,transparent,#fff6e0_35%,#ff6a4d_65%,transparent)] shadow-[0_0_10px_rgba(255,120,80,0.9)]" />
);

/** A thrust: a short streak driving in from the side and a bright puncture where it stops. */
const Pierce = () => (
  <>
    <span className="pointer-events-none absolute left-[-30%] top-[46%] h-[2px] w-[85%] origin-left animate-thrust bg-[linear-gradient(90deg,transparent,#ffffff_70%,#ffd0b0)] shadow-[0_0_8px_rgba(255,220,190,0.95)]" />
    <span className="pointer-events-none absolute left-[55%] top-[46%] h-5 w-5 -translate-x-1/2 -translate-y-1/2 animate-fx-fade rounded-full bg-[radial-gradient(circle,#ffffff,rgba(255,90,60,0.7)_45%,transparent_70%)] opacity-0" />
  </>
);

/** A crushing blow: cracks spidering out from where it landed. */
const Crush = () => (
  <svg viewBox="0 0 100 133" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full animate-fx-fade opacity-0" style={{ maxWidth: "none" }}>
    <g fill="none" stroke="rgba(255,240,215,0.95)" strokeWidth="1.4" strokeLinejoin="bevel" style={{ filter: "drop-shadow(0 0 2px rgba(0,0,0,0.9))" }}>
      <path d="M50 62 L38 48 L30 50 L18 36" />
      <path d="M50 62 L64 50 L70 38 L84 30" />
      <path d="M50 62 L46 80 L52 94 L47 110" />
      <path d="M50 62 L70 72 L78 86" />
      <path d="M50 62 L30 70 L22 84" />
    </g>
  </svg>
);

/** Lightning: a zigzag flicking across the portrait as it flashes white. */
const Zap = () => (
  <svg viewBox="0 0 100 133" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full animate-flicker" style={{ maxWidth: "none" }}>
    <path d="M58 0 L40 46 L56 52 L34 100 L46 104 L30 133" fill="none" stroke="#ffffff" strokeWidth="2.4" style={{ filter: "drop-shadow(0 0 4px #7fc8ff)" }} />
  </svg>
);

/** Wind: streaks of air raking sideways across the portrait. */
const Gust = () => (
  <>
    {["30%", "52%", "70%"].map((top, i) => (
      <span
        key={top}
        className="pointer-events-none absolute left-[-30%] h-[2px] w-[70%] animate-thrust rounded-full bg-[linear-gradient(90deg,transparent,rgba(235,255,245,0.95),transparent)]"
        style={{ top, animationDelay: `${i * 0.08}s` }}
      />
    ))}
  </>
);

const MARK: Partial<Record<StrikeStyle, () => JSX.Element>> = {
  pierce: Pierce,
  crush: Crush,
  lightning: Zap,
  wind: Gust,
};

/**
 * What a landed blow leaves on the portrait for a moment: a tint of its element and,
 * for the ones with a shape of their own, that shape — a slash, a thrust, cracks, a
 * bolt of lightning, a gust. Missiles that burst (fire, ice, magic) get the tint alone.
 */
const HitMarks = ({ hit, style }: { hit: boolean; style: StrikeStyle | null }) => {
  const look = style ?? "slash";
  const Mark = MARK[look];
  const slashed = look === "slash" || look === "bolt";
  return (
    <>
      <div
        className={`pointer-events-none absolute inset-0 transition-opacity duration-500 ${TINT[look]} ${
          hit ? (slashed ? "opacity-45" : "opacity-70") : "opacity-0"
        }`}
      />
      {hit && (slashed ? SLASH : Mark ? <Mark /> : null)}
    </>
  );
};

export default HitMarks;
