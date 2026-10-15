import { useEffect, useRef, useState } from "react";
import { pluralizeTurn } from "../battleEffects";
import type { IconType } from "react-icons";
import {
  GiBiceps,
  GiBlast,
  GiBleedingWound,
  GiBoltSpellCast,
  GiBrain,
  GiBrokenAxe,
  GiBrokenShield,
  GiCheckedShield,
  GiCrackedShield,
  GiCrosshair,
  GiCursedStar,
  GiFalling,
  GiFireShield,
  GiFlame,
  GiHealing,
  GiHeartBeats,
  GiHeartPlus,
  GiHolySymbol,
  GiIceShield,
  GiKnockout,
  GiLightningArc,
  GiLightningShield,
  GiMagicPotion,
  GiMagicShield,
  GiMagicSwirl,
  GiPoison,
  GiPoisonBottle,
  GiRunningNinja,
  GiRuneStone,
  GiSnowflake1,
  GiSpiralBloom,
  GiSprint,
  GiSwordsPower,
  GiTornado,
  GiWaterDrop,
  GiWingfoot,
} from "react-icons/gi";
import type { ArenaEffect, EffectIcon } from "./arenaTypes";
import type { DotFx } from "./DotEffects";

const MAX_RUNES = 4;

// Game Icons (game-icons.net, CC BY 3.0 — credited in the site footer).
const ICONS: Record<EffectIcon, IconType> = {
  bleeding: GiBleedingWound,
  burn: GiFlame,
  poison: GiPoisonBottle,
  paralysis: GiPoison,
  stun: GiKnockout,
  knockdown: GiFalling,
  windburn: GiTornado,
  armorbreak: GiCrackedShield,
  freeze: GiSnowflake1,
  electrify: GiLightningArc,
  wet: GiWaterDrop,
  holy: GiHolySymbol,
  curse: GiCursedStar,
  daze: GiSpiralBloom,
  magicImpact: GiMagicSwirl,
  cleanse: GiHealing,
  critChance: GiCrosshair,
  critDamage: GiBlast,
  dodge: GiWingfoot,
  hp: GiHeartPlus,
  mana: GiMagicPotion,
  energy: GiBoltSpellCast,
  stamina: GiSprint,
  strength: GiBiceps,
  agility: GiRunningNinja,
  intelligence: GiBrain,
  endurance: GiHeartBeats,
  damage: GiSwordsPower,
  buff: GiSwordsPower,
  debuff: GiBrokenAxe,
  resist: GiCheckedShield,
  resistDown: GiBrokenShield,
  resistFire: GiFireShield,
  resistIce: GiIceShield,
  resistLightning: GiLightningShield,
  resistMagic: GiMagicShield,
  rune: GiRuneStone,
};

export const RuneIcon = ({ icon, className }: { icon: EffectIcon; className: string }) => {
  const Icon = ICONS[icon];
  return <Icon className={className} aria-hidden />;
};
const NEW_EFFECT_FLASH_MS = 1500;

const RUNE_STYLE = {
  // Enamel on a brass rim, dimmed to the table's candlelight.
  good: "bg-[radial-gradient(circle_at_35%_30%,#8fb488_0%,#2c5233_55%,#0a1a0d_100%)] ring-[#a8894a]",
  bad: "bg-[radial-gradient(circle_at_35%_30%,#c98a74_0%,#6e2216_55%,#1e0604_100%)] ring-[#a8894a]",
} as const;

interface EffectRunesProps {
  effects: ArenaEffect[];
  /** A damage-over-time tick right now: the runes of the effects behind it flare. */
  flare: DotFx | null;
}

/**
 * A column of rune stones down the card's right edge, one per active effect, with
 * the turns left on each. Hover (desktop) or tap (touch) opens a panel describing
 * every effect; a freshly applied effect pulses once, and a ticking one flares.
 */
const EffectRunes = ({ effects, flare }: EffectRunesProps) => {
  const [open, setOpen] = useState(false);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    const keys = new Set(effects.map((e) => e.key));
    if (seen.current === null) {
      // Effects already on the card when the page opens aren't news.
      seen.current = keys;
      return;
    }
    const added = [...keys].filter((k) => !seen.current?.has(k));
    seen.current = keys;
    if (added.length === 0) return;
    setFresh(new Set(added));
    const t = window.setTimeout(() => setFresh(new Set()), NEW_EFFECT_FLASH_MS);
    return () => window.clearTimeout(t);
  }, [effects]);

  useEffect(() => {
    if (effects.length === 0) setOpen(false);
  }, [effects.length]);

  if (effects.length === 0) return null;

  const shown = effects.slice(0, MAX_RUNES);
  const extra = effects.length - shown.length;

  return (
    <div
      className="group/effects absolute -right-3 top-3 z-20 flex flex-col items-center gap-1 sm:-right-3.5"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onClick={(e) => {
        // Tapping the runes must not also pick the card as a target.
        e.stopPropagation();
        setOpen((v) => !v);
      }}
    >
      {shown.map((effect) => (
        <span
          key={effect.key}
          className={`relative flex h-7 w-7 cursor-help items-center justify-center rounded-full text-[#efe3c4] ring-2 shadow-[0_2px_5px_rgba(0,0,0,0.85),inset_0_-2px_3px_rgba(0,0,0,0.45)] sm:h-8 sm:w-8 ${
            RUNE_STYLE[effect.positive ? "good" : "bad"]
          }`}
        >
          {fresh.has(effect.key) && (
            <span
              className={`absolute inset-0 animate-ping rounded-full ${
                effect.positive ? "bg-emerald-300/35" : "bg-site-red/35"
              }`}
            />
          )}
          {flare && effect.dot && flare.kinds.includes(effect.dot) && (
            <span
              key={flare.id}
              className="pointer-events-none absolute -inset-2 animate-rune-flare rounded-full bg-[radial-gradient(circle,rgba(255,214,150,0.95)_0%,rgba(255,90,40,0.55)_45%,rgba(255,60,20,0)_70%)]"
            />
          )}
          <RuneIcon icon={effect.icon} className="relative h-[68%] w-[68%] drop-shadow-[0_1px_1px_rgba(0,0,0,0.9)]" />
          {/* Turns left, as a small plate on the stone's corner */}
          <span className="absolute -bottom-1 -right-1.5 flex h-3.5 min-w-[14px] items-center justify-center rounded-full bg-[#120e0a] px-0.5 text-[9px] font-bold leading-none text-gold-light ring-1 ring-[#c9a24e] tabular-nums">
            {effect.duration > 0 ? effect.duration : "∞"}
          </span>
        </span>
      ))}
      {extra > 0 && (
        <span className="rounded-full bg-black/80 px-1.5 text-[9px] font-semibold text-gold-light ring-1 ring-gold/50">
          +{extra}
        </span>
      )}

      {open && (
        <div
          className="absolute left-full top-0 ml-2 w-[200px] animate-fade-in rounded-card border border-gold-dark/50 bg-[linear-gradient(180deg,rgba(34,26,19,0.97),rgba(12,11,10,0.98))] p-2.5 text-left shadow-[0_10px_24px_rgba(0,0,0,0.75)] sm:w-[230px]"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="gold-text mb-1.5 text-[10px] font-medium uppercase tracking-[0.18em]">Эффекты</p>
          <ul className="flex flex-col gap-1.5">
            {effects.map((effect) => (
              <li key={effect.key} className="flex items-start gap-2">
                <RuneIcon
                  icon={effect.icon}
                  className={`mt-0.5 h-4 w-4 shrink-0 ${effect.positive ? "text-emerald-400" : "text-site-red"}`}
                />
                <div className="min-w-0">
                  <p className={`text-xs font-medium leading-tight ${effect.positive ? "text-emerald-200" : "text-[#ffb4a2]"}`}>
                    {effect.label}
                  </p>
                  {effect.detail && <p className="text-[11px] leading-tight text-white/60">{effect.detail}</p>}
                  {effect.duration > 0 && !effect.detail.includes("ход") && (
                    <p className="text-[11px] leading-tight text-white/45">ещё {pluralizeTurn(effect.duration)}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default EffectRunes;
