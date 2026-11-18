import { Fragment } from 'react';
import type { EscortRoutePoint } from '../../types/caravanEscort';

interface CaravanEscortRouteProps {
  route: EscortRoutePoint[];
  routeIndex: number;
  /** FEAT-215: index of the boarding port — the sea leg goes from it to the next point. */
  seaSplitIndex?: number | null;
  /** FEAT-215: the caravan is in a ship's hold (the sea leg is the current position). */
  aboard?: boolean;
  shipName?: string | null;
}

/** FEAT-212 — the caravan's whole route as a vertical list; the current stop is highlighted. */
const CaravanEscortRoute = ({ route, routeIndex, seaSplitIndex = null, aboard = false, shipName = null }: CaravanEscortRouteProps) => {
  if (route.length === 0) return <p className="text-white/40 text-xs">Маршрут неизвестен.</p>;
  return (
    <ol className="flex flex-col max-h-[240px] overflow-y-auto gold-scrollbar pr-1">
      {route.map((p, i) => {
        const current = !aboard && p.index === routeIndex;
        const passed = p.index < routeIndex || (aboard && p.index === routeIndex);
        const last = i === route.length - 1;
        const seaAfter = seaSplitIndex !== null && p.index === seaSplitIndex && !last;
        return (
          <Fragment key={`${p.index}-${p.location_id}`}>
          <li className="flex items-stretch gap-2.5 min-w-0">
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
              {seaAfter && <span className="text-white/35 text-xs"> · погрузка на корабль</span>}
            </span>
          </li>
          {seaAfter && (
            <li className="flex items-stretch gap-2.5 min-w-0">
              <div className="flex flex-col items-center shrink-0 w-3">
                <span className="text-[11px] leading-none mt-1" aria-hidden>
                  ⚓
                </span>
                <span className="flex-1 w-px bg-site-blue/30" aria-hidden />
              </div>
              <span className={`pb-2 text-sm break-words min-w-0 ${aboard ? 'text-site-blue font-medium' : 'text-site-blue/70'}`}>
                Море{shipName ? ` — корабль «${shipName}»` : ''}
                {aboard && <span className="text-white/50 text-xs font-normal"> — вы здесь</span>}
              </span>
            </li>
          )}
          </Fragment>
        );
      })}
    </ol>
  );
};

export default CaravanEscortRoute;
