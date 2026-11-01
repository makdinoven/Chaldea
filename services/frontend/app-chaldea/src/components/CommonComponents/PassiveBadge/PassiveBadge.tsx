import { useMemo } from 'react';
import { Sparkles } from 'lucide-react';
import { useTooltip } from '../InfoTooltip';

/*
  A subclass passive (FEAT-188): a small round gold badge; hover (mouse),
  keyboard focus or a tap (touch) opens a popover with the passive's name and
  description. A passive that has no effect in battle yet says so.

  Shared by the profile, the skill tree and the battle cards. The popover is
  portaled to <body> with fixed positioning (useTooltip), so panels with
  overflow-hidden and 3D drei <Html> layers don't clip it; it closes on
  Escape, a tap outside, or when the mouse leaves, and stays inside a 360px
  viewport.
*/

/** What the badge needs of a passive — the registry entry and the battle snapshot both fit. */
export interface PassiveBadgeData {
  name: string;
  description: string;
  /** false — described, but no effect in battle yet. Absent counts as working. */
  implemented?: boolean;
}

/** Shown under a passive that is registered but has no effect in battle yet. */
export const PASSIVE_NOT_ACTIVE_NOTE = 'пока не действует в бою';

interface PassiveInfoProps {
  passive: PassiveBadgeData;
  className?: string;
}

/** The passive's text: «Пассивка: <name>», its description and, if inactive, the muted note. */
export const PassiveInfo = ({ passive, className = '' }: PassiveInfoProps) => (
  <div className={`flex flex-col gap-1 text-left normal-case ${className}`}>
    <span className="text-xs font-medium uppercase tracking-[0.06em]">
      <span className="text-white/50">Пассивка: </span>
      <span className="gold-text">{passive.name}</span>
    </span>
    <span className="text-white/85 text-xs leading-relaxed whitespace-normal">{passive.description}</span>
    {passive.implemented === false && (
      <span className="text-white/45 text-[11px] italic">{PASSIVE_NOT_ACTIVE_NOTE}</span>
    )}
  </div>
);

const SIZES = {
  sm: { box: 'w-5 h-5', icon: 11 },
  md: { box: 'w-7 h-7', icon: 15 },
} as const;

interface PassiveBadgeProps {
  passive: PassiveBadgeData;
  size?: keyof typeof SIZES;
  /** Also write the passive's name beside the badge (a chip, for roomier places). */
  showName?: boolean;
  className?: string;
  /** Stacking order of the popover when the badge sits in a high layer (e.g. 3D labels). */
  tooltipZIndex?: number;
}

const PassiveBadge = ({ passive, size = 'sm', showName = false, className = '', tooltipZIndex }: PassiveBadgeProps) => {
  const { name, description, implemented } = passive;
  // Stable across re-renders: callers build `passive` inline, the popover only cares about its fields.
  const content = useMemo(
    () => <PassiveInfo passive={{ name, description, implemented }} />,
    [name, description, implemented],
  );
  const { open, setOpen, anchorRef, id, bubble, pointerHandlers, onFocus, toggleByClick } = useTooltip(content, {
    zIndex: tooltipZIndex,
  });
  const { box, icon } = SIZES[size];
  const inactive = passive.implemented === false;

  return (
    <button
      type="button"
      ref={(el) => {
        anchorRef.current = el;
      }}
      aria-label={`Пассивка: ${passive.name}`}
      aria-expanded={open}
      aria-describedby={open ? id : undefined}
      className={`group inline-flex items-center gap-1.5 min-w-0 shrink-0 rounded-full cursor-help focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold/60 ${className}`}
      {...pointerHandlers}
      onFocus={onFocus}
      onBlur={() => setOpen(false)}
      onClick={(e) => {
        // The badge may sit on a clickable card (a battle target): the tap is for the popover only.
        e.stopPropagation();
        toggleByClick();
      }}
    >
      <span
        className={`${box} shrink-0 rounded-full p-[1.5px] bg-gradient-to-b from-gold-light to-gold-dark shadow-[0_0_8px_rgba(240,217,92,0.3)] ${inactive ? 'opacity-60' : ''}`}
      >
        <span className="w-full h-full rounded-full bg-site-dark flex items-center justify-center">
          <Sparkles size={icon} strokeWidth={1.8} className="text-gold" />
        </span>
      </span>
      {showName && (
        <span className="text-xs font-medium text-white/85 group-hover:text-site-blue transition-colors duration-200 ease-site truncate">
          {passive.name}
        </span>
      )}
      {bubble}
    </button>
  );
};

export default PassiveBadge;
