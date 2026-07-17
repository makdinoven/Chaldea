// FEAT-151 — shared profile-tab primitive: big gold value + tiny label tile
// (Battles 4-tile stats row and similar).

interface StatTileProps {
  value: string | number;
  label: string;
  className?: string;
}

const StatTile = ({ value, label, className = '' }: StatTileProps) => {
  return (
    <div
      className={`gold-outline relative rounded-card bg-site-bg flex flex-col items-center gap-1 py-4 px-2 ${className}`}
    >
      <span className="gold-text text-2xl font-medium tabular-nums">{value}</span>
      <span className="text-[10px] uppercase tracking-[0.06em] text-white/50 text-center">
        {label}
      </span>
    </div>
  );
};

export default StatTile;
