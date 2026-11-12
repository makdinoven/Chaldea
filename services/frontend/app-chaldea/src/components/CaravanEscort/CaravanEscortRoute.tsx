import type { EscortRoutePoint } from '../../types/caravanEscort';

interface CaravanEscortRouteProps {
  route: EscortRoutePoint[];
  routeIndex: number;
}

/** FEAT-212 — the caravan's whole route as a vertical list; the current stop is highlighted. */
const CaravanEscortRoute = ({ route, routeIndex }: CaravanEscortRouteProps) => {
  if (route.length === 0) return <p className="text-white/40 text-xs">Маршрут неизвестен.</p>;
  return (
    <ol className="flex flex-col max-h-[240px] overflow-y-auto gold-scrollbar pr-1">
      {route.map((p, i) => {
        const current = p.index === routeIndex;
        const passed = p.index < routeIndex;
        const last = i === route.length - 1;
        return (
          <li key={`${p.index}-${p.location_id}`} className="flex items-stretch gap-2.5 min-w-0">
            <div className="flex flex-col items-center shrink-0 w-3">
              <span
                className={`mt-1.5 w-2.5 h-2.5 rounded-full shrink-0 ${
                  current ? 'bg-gold shadow-[0_0_6px_rgba(240,217,92,0.8)]' : passed ? 'bg-white/25' : 'border border-white/40'
                }`}
                aria-hidden
              />
              {!last && <span className={`flex-1 w-px ${passed ? 'bg-white/20' : 'bg-white/10'}`} aria-hidden />}
            </div>
            <span
              className={`pb-2 text-sm break-words min-w-0 ${
                current ? 'text-gold font-medium' : passed ? 'text-white/35' : 'text-white/75'
              }`}
            >
              {p.name ?? `Локация #${p.location_id}`}
              {current && <span className="text-white/50 text-xs font-normal"> — вы здесь</span>}
              {i === 0 && !current && <span className="text-white/35 text-xs"> · отправление</span>}
              {last && !current && <span className="text-white/35 text-xs"> · назначение</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
};

export default CaravanEscortRoute;
