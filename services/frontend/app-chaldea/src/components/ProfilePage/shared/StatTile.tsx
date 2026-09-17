// FEAT-151 — shared profile-tab primitive: big gold value + tiny label tile
// (Battles 4-tile stats row and similar).
// FEAT-166: flat ProfileCard surface — the tile now sits inside a PanelShell.

interface StatTileProps {
  value: string | number;
  label: string;
  className?: string;
}

const StatTile = ({ value, label, className = '' }: StatTileProps) => {
  return (
    <div
      className={`relative rounded-card border border-white/10 bg-white/[0.03] flex flex-col items-center gap-1 py-4 px-2 ${className}`}
    >
      <span className="gold-text text-2xl font-medium tabular-nums">{value}</span>
      <span className="text-[10px] uppercase tracking-[0.06em] text-white/50 text-center">
        {label}
      </span>
    </div>
  );
};

export default StatTile;
