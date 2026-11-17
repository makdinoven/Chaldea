interface DockedShipsProps {
  ships: { id: number; name: string }[];
}

/**
 * FEAT-213 — «У причала: «X»» in a port: every ship standing here, for everyone. The way aboard is the Captain
 * (among the NPCs of the location); the passage to the deck appears only for a pass holder.
 */
const DockedShips = ({ ships }: DockedShipsProps) => {
  if (ships.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-card bg-site-bg backdrop-blur-sm border border-white/10 px-3 sm:px-4 py-2.5 min-w-0">
      <span className="text-white/60 text-xs sm:text-sm shrink-0 flex items-center gap-1.5">
        <span aria-hidden>⚓</span>У причала:
      </span>
      {ships.map((s) => (
        <span
          key={s.id}
          className="px-2.5 py-0.5 rounded-full border border-gold/40 bg-gold/[0.06] text-gold text-xs sm:text-sm break-words max-w-full"
        >
          «{s.name}»
        </span>
      ))}
      <span className="text-white/40 text-xs basis-full sm:basis-auto">
        На борт пускает капитан — поговорите с ним.
      </span>
    </div>
  );
};

export default DockedShips;
