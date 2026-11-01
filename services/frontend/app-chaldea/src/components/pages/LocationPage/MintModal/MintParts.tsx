/** FEAT-191 — small pieces shared by the player mint modal and the admin «Монетный двор» tab. */

/** «Монетный двор закрыт: у страны не выбрана столица» — the backend may send a short reason or a full sentence. */
export const mintClosedText = (reason: string | null | undefined): string => {
  const r = (reason ?? '').trim();
  if (!r) return 'Монетный двор закрыт';
  if (r.toLowerCase().startsWith('монетный двор')) return r;
  return `Монетный двор закрыт: ${r}`;
};

const PERCENT = 100;

const share = (part: number, total: number): number =>
  total > 0 ? Math.min(PERCENT, Math.max(0, (part / total) * PERCENT)) : 0;

interface MintLimitBarProps {
  limit: number;
  court: number;
  players: number;
  remaining: number;
  /** Formats an amount of money (currency word forms). */
  format: (n: number) => string;
}

/** Season limit of a country: minted by the court (gold) and by players (blue), what is left. */
export const MintLimitBar = ({ limit, court, players, remaining, format }: MintLimitBarProps) => {
  const courtPct = share(court, limit);
  const playersPct = Math.min(PERCENT - courtPct, share(players, limit));
  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      <div
        className="relative h-2 w-full rounded-full bg-white/10 overflow-hidden flex"
        role="img"
        aria-label={`Отчеканено ${format(court + players)} из ${format(limit)}`}
      >
        <div className="h-full bg-gold/80" style={{ width: `${courtPct}%` }} />
        <div className="h-full bg-site-blue/80" style={{ width: `${playersPct}%` }} />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] sm:text-xs">
        <span className="text-white/60">
          <span className="inline-block w-2 h-2 rounded-full bg-gold/80 mr-1 align-middle" aria-hidden />
          двор: <span className="text-white">{format(court)}</span>
        </span>
        <span className="text-white/60">
          <span className="inline-block w-2 h-2 rounded-full bg-site-blue/80 mr-1 align-middle" aria-hidden />
          игроки: <span className="text-white">{format(players)}</span>
        </span>
        <span className="text-white/60 sm:ml-auto">
          осталось: <span className="text-gold">{format(Math.max(0, remaining))}</span> из {format(limit)}
        </span>
      </div>
    </div>
  );
};
