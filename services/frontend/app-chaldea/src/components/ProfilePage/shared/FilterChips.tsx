// FEAT-151 — shared profile-tab primitive: generic pill-chip filter row.
// Used by Skills (type filter), Quests (type filter), Battles (type + result),
// Titles (Все/Полученные/Закрытые), Party toggle.

export interface FilterChipItem {
  key: string;
  label: string;
  /** Tailwind bg-class for the colored dot, e.g. 'bg-stat-hp' */
  dot?: string;
  /** Optional dimmed counter rendered after the label */
  count?: number;
}

interface FilterChipsProps {
  items: FilterChipItem[];
  /** Key of the active chip */
  active: string;
  onChange: (key: string) => void;
  className?: string;
}

const FilterChips = ({ items, active, onChange, className = '' }: FilterChipsProps) => {
  return (
    <div className={`flex gap-2 overflow-x-auto gold-scrollbar pb-1 ${className}`}>
      {items.map((item) => {
        const isActive = item.key === active;
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => onChange(item.key)}
            className={`chip-outline flex items-center gap-2 shrink-0 rounded-full px-4 py-2 text-xs font-medium whitespace-nowrap cursor-pointer ${
              isActive ? 'chip-outline-active' : ''
            }`}
          >
            {item.dot && <span className={`w-2 h-2 rounded-full ${item.dot}`} />}
            {item.label}
            {item.count !== undefined && (
              <span
                className={`font-mono tabular-nums ${isActive ? 'text-gold-light/70' : 'text-white/40'}`}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};

export default FilterChips;
