// FEAT-151 — shared profile-tab primitive: thin HP/MP bar with a small label
// and optional cur/max text (Party member cards, ActiveBattleCard rows).
// Renders nothing when values are null/undefined (never shows «0/0»).

interface MiniStatBarProps {
  variant: 'hp' | 'mana';
  /** Small colored label to the left of the bar, e.g. 'HP' / 'MP' */
  label?: string;
  current: number | null | undefined;
  max: number | null | undefined;
  /** Show `cur/max` text to the right of the bar (default true) */
  showValues?: boolean;
  className?: string;
}

const VARIANT_STYLES: Record<'hp' | 'mana', { fill: string; text: string }> = {
  hp: { fill: 'stat-bar-hp', text: 'text-stat-hp' },
  mana: { fill: 'stat-bar-mana', text: 'text-site-blue' },
};

const MiniStatBar = ({
  variant,
  label,
  current,
  max,
  showValues = true,
  className = '',
}: MiniStatBarProps) => {
  if (current === null || current === undefined || max === null || max === undefined) {
    return null;
  }
  const percent = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
  const { fill, text } = VARIANT_STYLES[variant];

  return (
    <div className={`flex items-center gap-2 min-w-0 ${className}`}>
      {label && (
        <span className={`text-[9px] font-medium uppercase shrink-0 ${text}`}>{label}</span>
      )}
      <div className="stat-bar h-1.5 flex-1 min-w-0">
        <div className={`stat-bar-fill ${fill}`} style={{ width: `${percent}%` }} />
      </div>
      {showValues && (
        <span className="text-[9px] font-medium text-white/50 font-mono tabular-nums shrink-0">
          {current}/{max}
        </span>
      )}
    </div>
  );
};

export default MiniStatBar;
