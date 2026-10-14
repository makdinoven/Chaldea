import { useEffect, useRef, useState } from "react";
import { pluralizeTurn } from "../battleEffects";
import type { ArenaEffect } from "./arenaTypes";

const MAX_RUNES = 4;
const NEW_EFFECT_FLASH_MS = 1500;

const RUNE_STYLE = {
  good: "bg-[radial-gradient(circle_at_35%_30%,#d9f7c4_0%,#3f8f4a_55%,#0f2e16_100%)] ring-[#c9b46a]",
  bad: "bg-[radial-gradient(circle_at_35%_30%,#ffc2a8_0%,#b0301c_55%,#3a0806_100%)] ring-[#c9915a]",
} as const;

interface EffectRunesProps {
  effects: ArenaEffect[];
}

/**
 * A column of rune stones down the card's right edge, one per active effect, with
 * the turns left on each. Hover (desktop) or tap (touch) opens a panel describing
 * every effect; a freshly applied effect pulses once.
 */
const EffectRunes = ({ effects }: EffectRunesProps) => {
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
          className={`relative flex h-6 w-6 cursor-help items-center justify-center rounded-full text-[10px] font-bold leading-none text-white ring-2 shadow-[0_2px_5px_rgba(0,0,0,0.85),inset_0_-2px_3px_rgba(0,0,0,0.45)] [text-shadow:0_1px_2px_#000] sm:h-7 sm:w-7 sm:text-[11px] ${
            RUNE_STYLE[effect.positive ? "good" : "bad"]
          }`}
        >
          {fresh.has(effect.key) && (
            <span
              className={`absolute inset-0 animate-ping rounded-full ${
                effect.positive ? "bg-emerald-300/70" : "bg-site-red/70"
              }`}
            />
          )}
          <span className="relative">{effect.duration > 0 ? effect.duration : "∞"}</span>
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
                <span
                  className={`mt-1 h-2 w-2 shrink-0 rotate-45 ${effect.positive ? "bg-emerald-400" : "bg-site-red"}`}
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
