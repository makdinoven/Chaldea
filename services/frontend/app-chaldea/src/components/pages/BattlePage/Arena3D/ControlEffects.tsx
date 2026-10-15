import type { CSSProperties } from "react";
import type { BlockedSkill, ControlSkip, FighterControl } from "./arenaTypes";

export const BLOCKED_LABELS: Record<BlockedSkill, { badge: string; word: string }> = {
  attack: { badge: "Без атаки", word: "атака" },
  defense: { badge: "Без защиты", word: "защита" },
  support: { badge: "Без поддержки", word: "поддержка" },
};

export const SKIP_LABELS: Record<ControlSkip, string> = {
  Stun: "Оглушён",
  Poison: "Паралич",
};

// What circles a fighter who will lose the turn: stars for a stun, poison sparks for paralysis.
const HALO = {
  Stun: { color: "#ffe08a", glow: "rgba(255,210,90,0.9)", tint: "bg-[rgba(12,12,30,0.42)]" },
  Poison: { color: "#a8ff70", glow: "rgba(130,240,80,0.9)", tint: "bg-[rgba(25,70,10,0.45)]" },
} as const;
const ORBITERS = [0, 72, 144, 216, 288];
// One lap, and the ellipse's half-axes (the card is 104px wide, 132px from sm).
const ORBIT_MS = 2200;
const ORBIT_RX = "44px";
const ORBIT_RY = "9px";

const Star = ({ color, glow }: { color: string; glow: string }) => (
  <svg
    viewBox="-5 -5 10 10"
    // Explicit size: the orbit's anchor is 0px wide and preflight caps svg at max-width: 100%.
    style={{ width: 14, height: 14, maxWidth: "none", filter: `drop-shadow(0 0 3px ${glow})` }}
  >
    <path d="M0 -5 L1.3 -1.3 L5 0 L1.3 1.3 L0 5 L-1.3 1.3 L-5 0 L-1.3 -1.3 Z" fill={color} />
  </svg>
);

const Spark = ({ color, glow }: { color: string; glow: string }) => (
  <span className="block rounded-full" style={{ width: 6, height: 6, background: color, boxShadow: `0 0 5px ${glow}` }} />
);

/**
 * A ring of stars (stun) or poison sparks (paralysis) circling above the card,
 * seen at an angle: the orbit is a flattened circle. Plus a dimmed portrait.
 */
const SkipHalo = ({ skip }: { skip: ControlSkip }) => {
  const halo = HALO[skip];
  const Orbiter = skip === "Stun" ? Star : Spark;
  return (
    <>
      <div className={`pointer-events-none absolute inset-[5px] z-[2] rounded-[9px] ${halo.tint}`} />
      {/* Each orbiter rides an ellipse around the card's top edge: one animation swings
          it across, a nested one up and down a quarter-turn behind — together a circle
          seen from the side, without squashing the stars themselves. */}
      <div className="pointer-events-none absolute left-1/2 top-1 z-20 h-0 w-0">
        {ORBITERS.map((angle) => {
          const phase = { animationDelay: `${-(angle / 360) * ORBIT_MS}ms` };
          return (
            <span
              key={angle}
              className="absolute animate-orbit-x"
              style={{ ...phase, "--rx": ORBIT_RX } as CSSProperties}
            >
              <span
                className="block -translate-x-1/2 -translate-y-1/2 animate-orbit-y"
                style={{
                  animationDelay: `${-(angle / 360) * ORBIT_MS - ORBIT_MS / 4}ms`,
                  "--ry": ORBIT_RY,
                } as CSSProperties}
              >
                <Orbiter color={halo.color} glow={halo.glow} />
              </span>
            </span>
          );
        })}
      </div>
    </>
  );
};

/** Plates on the card naming each skill type Knockdown / Windburn takes away. */
const BlockedBadges = ({ blocked }: { blocked: BlockedSkill[] }) => (
  <div className="pointer-events-none absolute left-1.5 top-5 z-20 flex flex-col items-start gap-0.5">
    {blocked.map((type) => (
      <span
        key={type}
        className="flex items-center gap-1 rounded-sm bg-black/80 px-1.5 py-0.5 text-[8px] font-semibold uppercase leading-none tracking-wide text-[#ffb4a2] ring-1 ring-site-red/60 shadow-[0_2px_4px_rgba(0,0,0,0.8)] sm:text-[9px]"
      >
        <svg viewBox="0 0 12 6" className="h-1.5 w-3" aria-hidden>
          <ellipse cx="3.2" cy="3" rx="2.6" ry="2" fill="none" stroke="#c9c2b8" strokeWidth="1.1" />
          <ellipse cx="8.8" cy="3" rx="2.6" ry="2" fill="none" stroke="#8a847c" strokeWidth="1.1" />
        </svg>
        {BLOCKED_LABELS[type].badge}
      </span>
    ))}
  </div>
);

/** Everything a fighter's control effects show on the card while they last. */
const ControlEffects = ({ control }: { control: FighterControl }) => (
  <>
    {control.skip && <SkipHalo skip={control.skip} />}
    {!control.skip && control.blocked.length > 0 && <BlockedBadges blocked={control.blocked} />}
  </>
);

export default ControlEffects;
