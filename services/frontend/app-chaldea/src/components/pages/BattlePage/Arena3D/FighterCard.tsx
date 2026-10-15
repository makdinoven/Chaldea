import { useState } from "react";
import type { ArenaFighter, DotKind } from "./arenaTypes";
import DotEffects, { DOT_GLOW, DOT_LABELS, DOT_LABEL_STYLE, DOT_NUMBER_STYLE, type DotFx } from "./DotEffects";
import EffectRunes from "./EffectRunes";
import ControlEffects from "./ControlEffects";
import HitMarks from "./HitMarks";
import type { StrikeStyle } from "./strikeStyles";
import Auras, { auraKindsOf, frameFinishOf, portraitFilterOf } from "./Auras";
import CastEffects, { HealSparkles, type CastFx } from "./CastEffects";
import Vial from "./Vial";

export interface FloatingNumber {
  id: number;
  /** HP change; 0 for a word-only pop. */
  value: number;
  spawnedAt: number;
  critical?: boolean;
  /** Shown instead of a number — a blow that never landed, or control kicking in. */
  word?: string;
  /** Smaller line under the word (the skill types a block cut). */
  sub?: string;
  /** Colour of a word: steel for a dodge / miss, gold stun, green paralysis, red block. */
  tone?: WordTone;
  /** Set when the HP was lost to damage-over-time rather than a blow: its families. */
  dots?: DotKind[];
}

export type { DotFx };

export type WordTone = "evade" | "absorb" | "stun" | "paralysis" | "block";

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

// Numbers struck in metal: gradient fill, dark rim, a glow of the right colour.
const DAMAGE_NUMBER_STYLE =
  "bg-[linear-gradient(180deg,#ffe2c4_0%,#ff6a3d_45%,#8f1106_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(30,4,2,0.95)] [filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(255,80,40,0.55))]";
const HEAL_NUMBER_STYLE =
  "bg-[linear-gradient(180deg,#ecffe6_0%,#5be08a_45%,#14532d_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(4,24,10,0.95)] [filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(80,230,140,0.5))]";

// A crit is struck in gold and slams in harder. The glow sits on the wrapper; the
// gradient only on the number, so the caption above keeps its own bright gold.
const CRIT_GLOW = "[filter:drop-shadow(0_3px_3px_rgba(0,0,0,0.95))_drop-shadow(0_0_18px_rgba(255,190,60,0.8))]";
const CRIT_NUMBER_STYLE =
  "bg-[linear-gradient(180deg,#fffbe6_0%,#ffd75a_40%,#c4741a_75%,#5a2a04_100%)] bg-clip-text text-transparent [-webkit-text-stroke:2px_rgba(40,18,2,0.95)]";
const CRIT_CAPTION_STYLE = "text-[#ffe9a8] [-webkit-text-stroke:1px_rgba(40,18,2,0.9)]";
// Dodges and misses: pale steel capitals, no blood in it. A thick outline painted under
// the fill keeps them readable over bright portraits (a thin one eats the serifs).
// Control words share the evasion words' build — capitals over a thick dark outline —
// in their own colour.
const CONTROL_WORD_STYLE: Record<Exclude<WordTone, "evade">, string> = {
  // A blow soaked up by resistances: cold steel with a blue sheen, like a shield.
  absorb:
    "uppercase tracking-[0.12em] text-[#cfe0f5] [paint-order:stroke_fill] [-webkit-text-stroke:3px_rgba(8,14,26,0.9)] [filter:drop-shadow(0_2px_2px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(110,160,230,0.75))]",
  stun: "uppercase tracking-[0.12em] text-[#ffe08a] [paint-order:stroke_fill] [-webkit-text-stroke:3px_rgba(30,18,2,0.9)] [filter:drop-shadow(0_2px_2px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(255,200,80,0.75))]",
  paralysis:
    "uppercase tracking-[0.12em] text-[#c8ff9a] [paint-order:stroke_fill] [-webkit-text-stroke:3px_rgba(8,26,4,0.9)] [filter:drop-shadow(0_2px_2px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(130,240,80,0.7))]",
  block:
    "uppercase tracking-[0.12em] text-[#ffb4a2] [paint-order:stroke_fill] [-webkit-text-stroke:3px_rgba(40,4,2,0.9)] [filter:drop-shadow(0_2px_2px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(243,90,60,0.7))]",
};
const EVASION_WORD_STYLE =
  "uppercase tracking-[0.12em] text-[#eef5fc] [paint-order:stroke_fill] [-webkit-text-stroke:3px_rgba(10,16,24,0.9)] [filter:drop-shadow(0_2px_2px_rgba(0,0,0,0.95))_drop-shadow(0_0_12px_rgba(140,190,240,0.75))]";

// Where the resource orbs sit, and where a damage-over-time number lands so it
// misses them (and, for an ally on a phone, the action bar under the board).
const ORB_PLACEMENT = {
  side: "right-full top-1/2 mr-0.5 -translate-y-1/2 flex-col",
  below: "left-1/2 top-full mt-4 -translate-x-1/2 flex-row",
  above: "left-1/2 bottom-full mb-5 -translate-x-1/2 flex-row",
} as const;
const DOT_POP_TOP = { side: "top-[104%]", below: "top-[150%]", above: "top-[62%]" } as const;

export type OrbRow = "below" | "above" | null;

const FloatingPop = ({ n, orbRow }: { n: FloatingNumber; orbRow: OrbRow }) => {
  const base =
    "pointer-events-none absolute left-1/2 z-30 whitespace-nowrap font-serif font-semibold leading-none lining-nums tabular-nums";
  if (n.dots?.length) {
    // Under the card, sinking like a drop — clear of a blow's number rising above it.
    // One number for the turn's total, then every effect behind it in its own colour.
    const [main] = n.dots;
    return (
      <span className={`${base} ${DOT_POP_TOP[orbRow ?? "side"]} flex animate-dot-pop flex-col items-center ${DOT_GLOW[main]}`}>
        <span className={`text-4xl sm:text-5xl ${DOT_NUMBER_STYLE[main]}`}>{`−${Math.abs(n.value)}`}</span>
        {n.dots.map((kind) => (
          <span
            key={kind}
            className={`mt-0.5 text-[10px] uppercase tracking-[0.18em] [-webkit-text-stroke:2px_rgba(0,0,0,0.85)] [paint-order:stroke_fill] sm:text-xs ${DOT_LABEL_STYLE[kind]}`}
          >
            {DOT_LABELS[kind]}
          </span>
        ))}
      </span>
    );
  }
  if (n.word) {
    const style = n.tone && n.tone !== "evade" ? CONTROL_WORD_STYLE[n.tone] : EVASION_WORD_STYLE;
    return (
      <span className={`${base} top-[22%] flex animate-damage-pop flex-col items-center ${style}`}>
        {/* "Заблокировано" / "Поглощено" run long — one size down so they fit the card. */}
        <span className={n.tone === "block" || n.tone === "absorb" ? "text-lg sm:text-2xl" : "text-2xl sm:text-3xl"}>
          {n.word}
        </span>
        {n.sub && <span className="mt-1 text-xs tracking-[0.18em] sm:text-sm">{n.sub}</span>}
      </span>
    );
  }
  if (n.critical) {
    return (
      <span className={`${base} top-[22%] flex animate-crit-pop flex-col items-center ${CRIT_GLOW}`}>
        <span className={`text-xl uppercase tracking-[0.2em] sm:text-2xl ${CRIT_CAPTION_STYLE}`}>Крит</span>
        <span className={`text-7xl sm:text-8xl ${CRIT_NUMBER_STYLE}`}>{`−${Math.abs(n.value)}`}</span>
      </span>
    );
  }
  return (
    <span
      className={`${base} top-[22%] animate-damage-pop text-6xl sm:text-7xl ${n.value < 0 ? DAMAGE_NUMBER_STYLE : HEAL_NUMBER_STYLE}`}
    >
      {n.value > 0 ? `+${n.value}` : `−${Math.abs(n.value)}`}
    </span>
  );
};

const VIAL_SIZE = "h-[34px] w-[34px] sm:h-[42px] sm:w-[42px]";

const CORNER_STUD = "absolute z-[1] h-2 w-2 rotate-45 bg-[#e8cc7a] shadow-[0_0_0_1px_#3a2810]";

interface FighterCardProps {
  fighter: ArenaFighter;
  hit: boolean;
  /** How the blow that just landed looked — the mark it leaves follows it. */
  hitStyle: StrikeStyle | null;
  /** A damage-over-time tick playing on the card right now. */
  dotFx: DotFx | null;
  /** An effect just cast onto the card (seal / rising rings). */
  castFx: CastFx | null;
  /** Restarts the heal sparkles on each new heal; null when none is playing. */
  healFx: number | null;
  /** Phones: resource orbs in a row under / over the card instead of a column beside it. */
  orbRow: OrbRow;
  numbers: FloatingNumber[];
  onSelect: () => void;
}

/** A heavy gilded card: portrait, name plate, and its resources in glass orbs beside it. */
const FighterCard = ({ fighter, hit, hitStyle, dotFx, castFx, healFx, orbRow, numbers, onSelect }: FighterCardProps) => {
  const [avatarFailed, setAvatarFailed] = useState(false);
  const showAvatar = Boolean(fighter.avatar) && !avatarFailed;
  const badge = fighter.selection ? SELECTION_BADGE[fighter.selection] : null;
  const auras = fighter.isDead ? [] : auraKindsOf(fighter.effects);
  const glow = fighter.isDead
    ? STATE_GLOW.idle
    : fighter.isActing
      ? STATE_GLOW.acting
      : fighter.selection
        ? STATE_GLOW[fighter.selection]
        : STATE_GLOW.idle;

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

      <div className={`relative ${fighter.control.skip && !fighter.isDead ? "animate-daze-sway" : ""}`}>
        {/* Thickness: the card's edge showing beneath it */}
        <div className="absolute inset-0 translate-y-[7px] rounded-[14px] bg-[linear-gradient(180deg,#3d2a11,#0f0905)]" />
        <div className="absolute inset-0 translate-y-[3.5px] rounded-[14px] bg-[#6a4b1d]" />

        {/* Gilded frame */}
        <div
          className={`relative rounded-[14px] ${frameFinishOf(auras)} p-[3px] transition-shadow duration-300 ${glow}`}
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
                  style={{ filter: portraitFilterOf(auras) }}
                  className="h-full w-full object-cover transition-[filter] duration-700"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-4xl font-medium text-white/35">
                  {fighter.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_14px_rgba(0,0,0,0.85)]" />
              <HitMarks hit={hit} style={hitStyle} />
            </div>
          </div>
        </div>

        {dotFx && <DotEffects fx={dotFx} />}
        <Auras kinds={auras} />
        {!fighter.isDead && <ControlEffects control={fighter.control} />}
        {castFx && <CastEffects fx={castFx} />}
        {healFx !== null && <HealSparkles key={healFx} />}

        <EffectRunes effects={fighter.effects} flare={dotFx} />

        {/* Name plate across the lower edge */}
        <div className="absolute inset-x-[-10px] bottom-[-12px] z-[5] rounded-md border border-[#b8913f] bg-[linear-gradient(180deg,#2a1f14,#120d08)] px-2 py-1 shadow-[0_4px_8px_rgba(0,0,0,0.8)]">
          <p
            title={fighter.name}
            className={`truncate text-center text-[10px] font-semibold uppercase leading-tight tracking-wide sm:text-[11px] ${
              fighter.isActing ? "gold-text" : "text-[#efe3c4]"
            }`}
          >
            {fighter.name}
          </p>
        </div>

        {/* Resources: a column of glass orbs left of the card — or, on a phone's
            narrow board, a row facing the middle of the board (under an enemy,
            over an ally) so neighbours keep their room */}
        <div className={`absolute z-10 flex items-center gap-0.5 ${ORB_PLACEMENT[orbRow ?? "side"]}`}>
          <Vial
            kind="hp"
            value={fighter.hp}
            max={fighter.maxHp}
            title={`Здоровье: ${Math.round(fighter.hp)} / ${fighter.maxHp}`}
            className={VIAL_SIZE}
          />
          <Vial
            kind="mana"
            value={fighter.mana}
            max={fighter.maxMana}
            title={`Мана: ${Math.round(fighter.mana)} / ${fighter.maxMana}`}
            className={VIAL_SIZE}
          />
          <Vial
            kind="energy"
            value={fighter.energy}
            max={fighter.maxEnergy}
            title={`Энергия: ${Math.round(fighter.energy)} / ${fighter.maxEnergy}`}
            className={VIAL_SIZE}
          />
        </div>
      </div>

      {numbers.map((n) => (
        <FloatingPop key={n.id} n={n} orbRow={orbRow} />
      ))}
    </div>
  );
};

export default FighterCard;
