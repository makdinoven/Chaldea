import { useState } from "react";
import type { ArenaFighter } from "./arenaTypes";
import EffectRunes from "./EffectRunes";

export interface FloatingNumber {
  id: number;
  value: number;
}

const SELECTION_BADGE = {
  target: { text: "Цель", className: "bg-site-red" },
  ally: { text: "Поддержка", className: "bg-emerald-500" },
} as const;

// Outer glow by state, stacked on the card's own drop shadow.
const STATE_GLOW = {
  acting: "shadow-[0_0_26px_rgba(240,217,92,0.75),0_12px_24px_rgba(0,0,0,0.8)]",
  target: "shadow-[0_0_24px_rgba(243,119,83,0.75),0_12px_24px_rgba(0,0,0,0.8)]",
  ally: "shadow-[0_0_24px_rgba(52,211,153,0.7),0_12px_24px_rgba(0,0,0,0.8)]",
  idle: "shadow-[0_12px_24px_rgba(0,0,0,0.8)]",
} as const;

const GEM = {
  hp: "bg-[radial-gradient(circle_at_35%_30%,#ff9d80_0%,#c4321d_55%,#4f0b05_100%)]",
  mana: "bg-[radial-gradient(circle_at_35%_30%,#a8d8f0_0%,#2f6f9e_55%,#0b2236_100%)]",
  energy: "bg-[radial-gradient(circle_at_35%_30%,#fff2a8_0%,#c49a2c_55%,#4a3507_100%)]",
} as const;

const Gem = ({
  kind,
  value,
  title,
  className,
}: {
  kind: keyof typeof GEM;
  value: number;
  title: string;
  className: string;
}) => (
  <span
    title={title}
    className={`absolute z-10 flex items-center justify-center rounded-full font-extrabold tabular-nums leading-none text-white ring-2 ring-[#d8b866] shadow-[0_3px_6px_rgba(0,0,0,0.85),inset_0_-2px_4px_rgba(0,0,0,0.5)] [text-shadow:0_1px_2px_#000] ${GEM[kind]} ${className}`}
  >
    {Math.max(0, Math.round(value))}
  </span>
);

// Numbers struck in metal: gradient fill, dark rim, a glow of the right colour.
const DAMAGE_NUMBER_STYLE =
  "bg-[linear-gradient(180deg,#ffe2c4_0%,#ff6a3d_45%,#8f1106_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(30,4,2,0.95)] [filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(255,80,40,0.55))]";
const HEAL_NUMBER_STYLE =
  "bg-[linear-gradient(180deg,#ecffe6_0%,#5be08a_45%,#14532d_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(4,24,10,0.95)] [filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(80,230,140,0.5))]";

const CORNER_STUD = "absolute z-[1] h-2 w-2 rotate-45 bg-[#e8cc7a] shadow-[0_0_0_1px_#3a2810]";

interface FighterCardProps {
  fighter: ArenaFighter;
  hit: boolean;
  numbers: FloatingNumber[];
  onSelect: () => void;
}

/** A heavy gilded card: portrait, name plate, and its resources set in gems. */
const FighterCard = ({ fighter, hit, numbers, onSelect }: FighterCardProps) => {
  const [avatarFailed, setAvatarFailed] = useState(false);
  const showAvatar = Boolean(fighter.avatar) && !avatarFailed;
  const badge = fighter.selection ? SELECTION_BADGE[fighter.selection] : null;
  const glow = fighter.isDead
    ? STATE_GLOW.idle
    : fighter.isActing
      ? STATE_GLOW.acting
      : fighter.selection
        ? STATE_GLOW[fighter.selection]
        : STATE_GLOW.idle;
  const hpPct = fighter.maxHp > 0 ? Math.max(0, Math.min(100, (fighter.hp / fighter.maxHp) * 100)) : 0;

  return (
    <div
      onClick={fighter.selectable ? onSelect : undefined}
      className={`relative w-[104px] select-none pb-4 transition-all duration-500 ease-out sm:w-[132px] ${
        fighter.selectable ? "cursor-pointer hover:-translate-y-1" : ""
      } ${fighter.isDead ? "translate-y-3 rotate-[7deg] opacity-50 grayscale" : ""}`}
    >
      {!badge && fighter.isSelf && (
        <span className="absolute -top-3 left-1/2 z-20 -translate-x-1/2 rounded-full border border-gold/60 bg-[#1a140c] px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-gold-light shadow-[0_2px_6px_rgba(0,0,0,0.7)] sm:text-[10px]">
          Вы
        </span>
      )}
      {badge && (
        <span
          className={`absolute -top-3 left-1/2 z-20 -translate-x-1/2 whitespace-nowrap rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white shadow-[0_2px_6px_rgba(0,0,0,0.7)] sm:text-[10px] ${badge.className}`}
        >
          {badge.text}
        </span>
      )}

      <div className="relative">
        {/* Thickness: the card's edge showing beneath it */}
        <div className="absolute inset-0 translate-y-[7px] rounded-[14px] bg-[linear-gradient(180deg,#3d2a11,#0f0905)]" />
        <div className="absolute inset-0 translate-y-[3.5px] rounded-[14px] bg-[#6a4b1d]" />

        {/* Gilded frame */}
        <div
          className={`relative rounded-[14px] bg-[linear-gradient(145deg,#f6e3a1_0%,#b8913f_28%,#6e5320_52%,#d8b866_78%,#7a5c24_100%)] p-[3px] transition-shadow duration-300 ${glow}`}
        >
          <span className={`${CORNER_STUD} -left-1 -top-1`} />
          <span className={`${CORNER_STUD} -right-1 -top-1`} />
          <span className={`${CORNER_STUD} -bottom-1 -left-1`} />
          <span className={`${CORNER_STUD} -bottom-1 -right-1`} />

          <div className="rounded-[11px] bg-[#120e0a] p-[2px]">
            <div className="relative aspect-[3/4] overflow-hidden rounded-[9px] bg-site-dark">
              {showAvatar ? (
                <img
                  src={fighter.avatar ?? undefined}
                  alt={fighter.name}
                  draggable={false}
                  onError={() => setAvatarFailed(true)}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-4xl font-medium text-white/35">
                  {fighter.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_14px_rgba(0,0,0,0.85)]" />
              <div
                className={`pointer-events-none absolute inset-0 bg-site-red mix-blend-multiply transition-opacity duration-500 ${
                  hit ? "opacity-45" : "opacity-0"
                }`}
              />
              {/* A blade's slash wiping across the portrait */}
              {hit && (
                <span className="pointer-events-none absolute left-[-20%] top-1/2 h-[3px] w-[140%] origin-left -rotate-[32deg] animate-slash bg-[linear-gradient(90deg,transparent,#fff6e0_35%,#ff6a4d_65%,transparent)] shadow-[0_0_10px_rgba(255,120,80,0.9)]" />
              )}
            </div>
          </div>
        </div>

        <EffectRunes effects={fighter.effects} />

        {/* Name plate across the lower edge */}
        <div className="absolute inset-x-[-14px] bottom-[-12px] z-[5] rounded-md border border-[#b8913f] bg-[linear-gradient(180deg,#2a1f14,#120d08)] pb-1 pl-5 pr-7 pt-0.5 sm:pl-6 sm:pr-9 shadow-[0_4px_8px_rgba(0,0,0,0.8)]">
          <p
            title={fighter.name}
            className={`truncate text-center text-[10px] font-semibold uppercase leading-tight tracking-wide sm:text-[11px] ${
              fighter.isActing ? "gold-text" : "text-[#efe3c4]"
            }`}
          >
            {fighter.name}
          </p>
          <div className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-black/70">
            <div
              className="h-full rounded-full bg-gradient-to-r from-red-700 to-site-red transition-[width] duration-700 ease-out"
              style={{ width: `${hpPct}%` }}
            />
          </div>
        </div>

        <Gem
          kind="energy"
          value={fighter.energy}
          title={`Энергия: ${Math.round(fighter.energy)} / ${fighter.maxEnergy}`}
          className="-left-2.5 -top-2.5 h-6 w-6 text-[10px] sm:h-7 sm:w-7 sm:text-[11px]"
        />
        <Gem
          kind="mana"
          value={fighter.mana}
          title={`Мана: ${Math.round(fighter.mana)} / ${fighter.maxMana}`}
          className="-bottom-5 -left-3 h-7 w-7 text-[11px] sm:h-8 sm:w-8 sm:text-xs"
        />
        <Gem
          kind="hp"
          value={fighter.hp}
          title={`Здоровье: ${Math.round(fighter.hp)} / ${fighter.maxHp}`}
          className="-bottom-6 -right-3.5 h-9 w-9 text-xs sm:h-11 sm:w-11 sm:text-sm"
        />
      </div>

      {numbers.map((n) => (
        <span
          key={n.id}
          className={`pointer-events-none absolute left-1/2 top-[22%] z-30 animate-damage-pop whitespace-nowrap font-serif text-6xl font-semibold leading-none lining-nums tabular-nums sm:text-7xl ${
            n.value < 0 ? DAMAGE_NUMBER_STYLE : HEAL_NUMBER_STYLE
          }`}
        >
          {n.value > 0 ? `+${n.value}` : `\u2212${Math.abs(n.value)}`}
        </span>
      ))}
    </div>
  );
};

export default FighterCard;
