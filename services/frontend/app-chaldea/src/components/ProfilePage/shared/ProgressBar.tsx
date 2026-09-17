// FEAT-166 — shared profile-tab primitive: progress bar on top of the DS
// `.stat-bar` (profession XP, gathering, titles, perks, quest objectives).
// `MiniStatBar` stays the compact HP/MP variant.
import type { ReactNode } from 'react';

export type ProgressBarVariant = 'gold' | 'neutral' | 'hp' | 'mana' | 'energy' | 'epic';

interface ProgressBarProps {
  value: number;
  max: number;
  variant?: ProgressBarVariant;
  /** `md` = DS 9px bar with white border, `sm` = thin 6px bar with a softer border */
  size?: 'sm' | 'md';
  /** Caption above the bar (left) */
  label?: ReactNode;
  /** Show `value/max` above the bar (right) */
  showValues?: boolean;
  className?: string;
}

const FILL_CLASSES: Record<ProgressBarVariant, string> = {
  gold: 'bg-gradient-to-r from-gold-dark to-gold-light',
  // Neutral progress that must not read as a reward/achievement (locked conditions).
  neutral: 'bg-white/60',
  hp: 'stat-bar-hp',
  mana: 'stat-bar-mana',
  energy: 'stat-bar-energy',
  epic: 'bg-rarity-epic',
};

const ProgressBar = ({
  value,
  max,
  variant = 'gold',
  size = 'md',
  label,
  showValues = false,
  className = '',
}: ProgressBarProps) => {
  const percent = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const hasCaption = (label !== undefined && label !== null) || showValues;

  return (
    <div className={`flex flex-col gap-1 min-w-0 ${className}`}>
      {hasCaption && (
        <div className="flex items-center justify-between gap-2 min-w-0">
          {label !== undefined && label !== null && (
            <div className="min-w-0 text-xs text-white/60">{label}</div>
          )}
          {showValues && (
            <span className="ml-auto text-[10px] font-mono tabular-nums text-white/50 shrink-0">
              {value}/{max}
            </span>
          )}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        className={`stat-bar ${size === 'sm' ? 'h-1.5 border-white/40' : ''}`}
      >
        <div
          className={`stat-bar-fill ${FILL_CLASSES[variant]}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
};

export default ProgressBar;
