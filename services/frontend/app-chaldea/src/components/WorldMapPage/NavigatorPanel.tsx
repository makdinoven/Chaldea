import type { GraphLocation } from '../../api/worldGraph';
import type { RouteMode, RouteResult } from './graphUtils';
import LocationPicker from './LocationPicker';
import { ROUTE_COLOR } from './theme';

interface NavigatorPanelProps {
  locations: GraphLocation[];
  locationById: Map<number, GraphLocation>;
  regionNames: Map<number, string>;
  waypoints: Array<number | null>;
  onWaypointsChange: (next: Array<number | null>) => void;
  activeSlot: number | null;
  onActiveSlotChange: (slot: number | null) => void;
  mode: RouteMode;
  onModeChange: (mode: RouteMode) => void;
  route: RouteResult | null;
  onFocusLocation: (id: number) => void;
}

/** Russian plural: 1 локация, 2–4 локации, 5+ локаций. */
const pluralLocations = (count: number): string => {
  const mod100 = count % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'локаций';
  switch (count % 10) {
    case 1: return 'локация';
    case 2:
    case 3:
    case 4: return 'локации';
    default: return 'локаций';
  }
};

const slotColor = (index: number, total: number) => {
  if (index === 0) return '#5fb98f';
  if (index === total - 1) return '#f37753';
  return ROUTE_COLOR;
};

const slotLabel = (index: number, total: number) => {
  if (index === 0) return 'A — откуда';
  if (index === total - 1) return 'B — куда';
  return `Точка ${index + 1}`;
};

const NavigatorPanel = ({
  locations,
  locationById,
  regionNames,
  waypoints,
  onWaypointsChange,
  activeSlot,
  onActiveSlotChange,
  mode,
  onModeChange,
  route,
  onFocusLocation,
}: NavigatorPanelProps) => {
  const hasAnyPoint = waypoints.some((id) => id !== null);

  const setSlot = (index: number, id: number | null) => {
    const next = [...waypoints];
    next[index] = id;
    onWaypointsChange(next);
  };

  const addSlot = () => {
    // Insert before the final destination so B stays the endpoint.
    const next = [...waypoints];
    next.splice(Math.max(next.length - 1, 1), 0, null);
    onWaypointsChange(next);
  };

  const removeSlot = (index: number) => {
    if (waypoints.length <= 2) return;
    onWaypointsChange(waypoints.filter((_, i) => i !== index));
    onActiveSlotChange(null);
  };

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h2 className="gold-text text-[15px] font-semibold">Навигатор</h2>
        <p className="mt-0.5 text-[11px] leading-snug text-white/45">
          Выберите точки или кликните по локации на карте, чтобы заполнить активное поле.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        {waypoints.map((value, index) => (
          <div
            key={`slot-${index}`}
            className={`flex items-center gap-2 rounded-lg p-1 transition-colors ${
              activeSlot === index ? 'bg-gold-dark/20 ring-1 ring-gold-dark/60' : ''
            }`}
            onClick={() => onActiveSlotChange(index)}
            role="presentation"
          >
            <span
              className="w-[74px] shrink-0 text-[10px] uppercase tracking-wide text-white/45"
            >
              {slotLabel(index, waypoints.length)}
            </span>
            <LocationPicker
              locations={locations}
              regionNames={regionNames}
              value={value}
              onChange={(id) => setSlot(index, id)}
              placeholder="Название локации…"
              accentColor={slotColor(index, waypoints.length)}
            />
            {waypoints.length > 2 && (
              <button
                type="button"
                aria-label="Удалить точку маршрута"
                className="shrink-0 rounded px-1 text-white/35 transition-colors hover:text-site-red"
                onClick={(event) => {
                  event.stopPropagation();
                  removeSlot(index);
                }}
              >
                −
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-line text-[12px]" onClick={addSlot}>
          + Промежуточная точка
        </button>
        <button
          type="button"
          disabled={!hasAnyPoint}
          className="rounded-lg border border-site-red/40 px-2.5 py-1 text-[12px] text-site-red
                     transition-colors hover:bg-site-red/15 disabled:cursor-not-allowed
                     disabled:border-white/10 disabled:text-white/25 disabled:hover:bg-transparent"
          onClick={() => {
            onWaypointsChange([null, null]);
            onActiveSlotChange(0);
          }}
        >
          Очистить маршрут
        </button>
      </div>

      <div>
        <span className="mb-1 block text-[10px] uppercase tracking-wide text-white/45">
          Оптимизировать по
        </span>
        <div className="flex overflow-hidden rounded-lg border border-gold-dark/40">
          {(['energy', 'steps'] as RouteMode[]).map((option) => (
            <button
              key={option}
              type="button"
              className={`flex-1 px-3 py-1.5 text-[12px] transition-colors ${
                mode === option
                  ? 'bg-gold-dark/35 text-gold-light'
                  : 'text-white/50 hover:bg-white/5'
              }`}
              onClick={() => onModeChange(option)}
            >
              {option === 'energy' ? 'Энергии' : 'Числу шагов'}
            </button>
          ))}
        </div>
      </div>

      {route && <RouteSummary route={route} locationById={locationById} onFocusLocation={onFocusLocation} />}
    </div>
  );
};

interface RouteSummaryProps {
  route: RouteResult;
  locationById: Map<number, GraphLocation>;
  onFocusLocation: (id: number) => void;
}

const RouteSummary = ({ route, locationById, onFocusLocation }: RouteSummaryProps) => {
  const nameOf = (id: number) => locationById.get(id)?.name ?? `#${id}`;

  return (
    <div className="gradient-line-border rounded-lg bg-black/35 p-3">
      {route.complete ? (
        <div className="flex items-center gap-4">
          <div>
            <div className="gold-text text-[20px] font-bold leading-none">{route.energy}</div>
            <div className="text-[10px] uppercase tracking-wide text-white/45">энергии</div>
          </div>
          <div className="h-8 w-px bg-white/10" />
          <div>
            <div className="text-[20px] font-bold leading-none text-site-blue">{route.steps}</div>
            <div className="text-[10px] uppercase tracking-wide text-white/45">переходов</div>
          </div>
        </div>
      ) : (
        <p className="text-[12px] leading-snug text-site-red">
          Маршрут не существует — часть точек находится в несвязанных частях мира.
        </p>
      )}

      <div className="mt-3 flex flex-col gap-2">
        {route.legs.map((leg, index) => (
          <div key={`leg-${index}`} className="text-[11px]">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-white/70">
                {nameOf(leg.from)} → {nameOf(leg.to)}
              </span>
              <span className={leg.reachable ? 'shrink-0 text-white/45' : 'shrink-0 text-site-red'}>
                {leg.reachable ? `${leg.energy} эн. / ${leg.steps} ш.` : 'нет пути'}
              </span>
            </div>
          </div>
        ))}
      </div>

      {route.complete && route.nodes.length > 1 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[11px] text-white/45 transition-colors hover:text-gold">
            Показать все {route.nodes.length} {pluralLocations(route.nodes.length)} маршрута
          </summary>
          <ol className="gold-scrollbar mt-2 max-h-56 overflow-y-auto pr-1">
            {route.nodes.map((id, index) => (
              <li key={`${id}-${index}`}>
                <button
                  type="button"
                  className="flex w-full items-baseline gap-2 rounded px-1 py-0.5 text-left
                             transition-colors hover:bg-white/5"
                  onClick={() => onFocusLocation(id)}
                >
                  <span className="w-6 shrink-0 text-right text-[10px] text-white/30">
                    {index + 1}
                  </span>
                  <span className="truncate text-[11px] text-white/70">{nameOf(id)}</span>
                </button>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
};

export default NavigatorPanel;
