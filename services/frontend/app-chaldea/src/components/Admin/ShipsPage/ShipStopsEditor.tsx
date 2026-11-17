import { useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Route, Trash2, X } from 'lucide-react';
import { previewSeaLegs, seaAdminError, SEA_LIMITS } from '../../../api/seaAdmin';
import type { SeaLeg, SeaPort, SeaStopInput, SeaZone } from '../../../types/seaAdmin';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';

const PREVIEW_DEBOUNCE_MS = 400;

interface ShipStopsEditorProps {
  stops: SeaStopInput[];
  onChange: (stops: SeaStopInput[]) => void;
  isLoop: boolean;
  zoneMinutes: number;
  ports: SeaPort[];
  zones: SeaZone[];
  /** The route is locked (ship at sea / no rights) */
  disabled?: boolean;
  disabledReason?: string;
  /** Latest legs preview (null while loading / unavailable) */
  onLegsChange?: (legs: SeaLeg[] | null) => void;
}

/** Key of the leg starting at stop `i` ("a>b"), or null when there is no such leg. */
const legKeys = (stops: SeaStopInput[], isLoop: boolean): (string | null)[] =>
  stops.map((s, i) => {
    const j = i + 1 < stops.length ? i + 1 : isLoop && stops.length > 1 ? 0 : -1;
    return j < 0 ? null : `${s.port_location_id}>${stops[j].port_location_id}`;
  });

/** Keeps a manual path only on the legs whose ports did not change (reorder/insert/remove). */
const carryOverrides = (prev: SeaStopInput[], next: SeaStopInput[], isLoop: boolean): SeaStopInput[] => {
  const kept = new Map<string, number[]>();
  legKeys(prev, isLoop).forEach((k, i) => {
    const path = prev[i].path_override;
    if (k && path && path.length) kept.set(k, path);
  });
  const keys = legKeys(next, isLoop);
  return next.map((s, i) => ({ ...s, path_override: (keys[i] && kept.get(keys[i] as string)) || null }));
};

const zoneLabel = (zone: SeaZone | undefined, id: number): string =>
  zone ? `${zone.name}${zone.region_name ? ` (${zone.region_name})` : ''}` : `#${id}`;

const portLabel = (port: SeaPort): string => {
  const place = [port.region_name, port.country_name].filter(Boolean).join(', ');
  const zone = port.port_sea_zone_name ? ` → ${port.port_sea_zone_name}` : ' — нет выхода в море';
  return `${port.name}${place ? ` (${place})` : ''}${zone}`;
};

// ---------------------------------------------------------------------------------------------------------------------
// manual zone chain
// ---------------------------------------------------------------------------------------------------------------------

interface OverrideEditorProps {
  startZone: number;
  goalZone: number;
  initial: number[];
  zonesById: Map<number, SeaZone>;
  onApply: (path: number[]) => void;
  onCancel: () => void;
}

const OverrideEditor = ({ startZone, goalZone, initial, zonesById, onApply, onCancel }: OverrideEditorProps) => {
  const [chain, setChain] = useState<number[]>(
    initial.length && initial[0] === startZone ? initial : [startZone],
  );
  const last = chain[chain.length - 1];
  const options = (zonesById.get(last)?.neighbor_ids ?? [])
    .filter((id) => zonesById.has(id) && id !== chain[chain.length - 2])
    .sort((a, b) => (zonesById.get(a)?.name ?? '').localeCompare(zonesById.get(b)?.name ?? '', 'ru'));
  const done = last === goalZone;

  return (
    <div className="flex flex-col gap-3 rounded-card border border-white/10 bg-black/20 p-3">
      <p className="text-white/60 text-xs">
        Цепочка соседних морских зон от выхода в море первого порта до выхода второго. Каждая следующая зона —
        только из соседей предыдущей. Обратный участок (туда-обратно) идёт по этой же цепочке задом наперёд.
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        {chain.map((id, i) => (
          <span key={`${id}-${i}`} className="flex items-center gap-1">
            {i > 0 && <span className="text-white/30 text-xs">→</span>}
            <span
              className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs ${
                id === goalZone && i === chain.length - 1 ? 'bg-gold/[0.12] text-gold' : 'bg-white/[0.07] text-white/85'
              }`}
            >
              {zoneLabel(zonesById.get(id), id)}
              {i > 0 && i === chain.length - 1 && (
                <button
                  type="button"
                  aria-label="Убрать зону"
                  onClick={() => setChain((c) => c.slice(0, -1))}
                  className="text-white/50 hover:text-site-red transition-colors"
                >
                  <X size={12} />
                </button>
              )}
            </span>
          </span>
        ))}
      </div>
      {!done && (
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Следующая зона</span>
          {options.length ? (
            <select
              value=""
              onChange={(e) => e.target.value && setChain((c) => [...c, Number(e.target.value)])}
              className={FIELD}
            >
              <option value="">— выберите соседнюю зону —</option>
              {options.map((id) => (
                <option key={id} value={id}>
                  {zoneLabel(zonesById.get(id), id)}
                  {id === goalZone ? ' — цель' : ''}
                </option>
              ))}
            </select>
          ) : (
            <span className="text-site-red text-xs">У этой зоны нет других соседей — уберите её и выберите другую.</span>
          )}
        </label>
      )}
      <p className={`text-xs ${done ? 'text-stat-energy' : 'text-white/50'}`}>
        {done
          ? `Путь готов: ${chain.length} ${chain.length === 1 ? 'зона' : 'зон(ы)'}`
          : `Цель: ${zoneLabel(zonesById.get(goalZone), goalZone)}`}
      </p>
      <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
        <button type="button" onClick={onCancel} className="btn-line w-full sm:w-auto">
          Отмена
        </button>
        <button type="button" disabled={!done} onClick={() => onApply(chain)} className="btn-blue w-full sm:w-auto">
          Применить путь
        </button>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------------------------------------------------
// stops + legs
// ---------------------------------------------------------------------------------------------------------------------

const ShipStopsEditor = ({
  stops,
  onChange,
  isLoop,
  zoneMinutes,
  ports,
  zones,
  disabled = false,
  disabledReason,
  onLegsChange,
}: ShipStopsEditorProps) => {
  const [adding, setAdding] = useState('');
  const [legs, setLegs] = useState<SeaLeg[] | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [editingLeg, setEditingLeg] = useState<number | null>(null);

  const portsById = useMemo(() => new Map(ports.map((p) => [p.id, p])), [ports]);
  const zonesById = useMemo(() => new Map(zones.map((z) => [z.id, z])), [zones]);
  const sortedPorts = useMemo(
    () => [...ports].sort((a, b) => (a.country_name ?? '').localeCompare(b.country_name ?? '', 'ru') || a.name.localeCompare(b.name, 'ru')),
    [ports],
  );

  const previewKey = JSON.stringify({ stops, isLoop, zoneMinutes });

  useEffect(() => {
    if (stops.length < 2) {
      setLegs(null);
      setPreviewError(null);
      onLegsChange?.(null);
      return undefined;
    }
    let cancelled = false;
    setPreviewLoading(true);
    const timer = window.setTimeout(() => {
      previewSeaLegs({ stops, is_loop: isLoop, zone_minutes: zoneMinutes >= 1 ? zoneMinutes : null })
        .then((rows) => {
          if (cancelled) return;
          setLegs(rows);
          setPreviewError(null);
          onLegsChange?.(rows);
        })
        .catch((e) => {
          if (cancelled) return;
          setLegs(null);
          setPreviewError(seaAdminError(e, 'Не удалось проложить путь между портами'));
          onLegsChange?.(null);
        })
        .finally(() => {
          if (!cancelled) setPreviewLoading(false);
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // previewKey captures stops / isLoop / zoneMinutes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey]);

  const commit = (next: SeaStopInput[]) => {
    setEditingLeg(null);
    onChange(carryOverrides(stops, next, isLoop));
  };

  const move = (i: number, delta: number) => {
    const j = i + delta;
    if (j < 0 || j >= stops.length) return;
    const next = [...stops];
    [next[i], next[j]] = [next[j], next[i]];
    commit(next);
  };

  const remove = (i: number) => commit(stops.filter((_, k) => k !== i));

  const add = () => {
    const id = Number(adding);
    if (!id) return;
    commit([...stops, { port_location_id: id, path_override: null }]);
    setAdding('');
  };

  const setOverride = (legIndex: number, path: number[] | null) => {
    setEditingLeg(null);
    onChange(stops.map((s, i) => (i === legIndex ? { ...s, path_override: path && path.length ? path : null } : s)));
  };

  const maxStops = SEA_LIMITS.stops[1];
  const lastPortId = stops.length ? stops[stops.length - 1].port_location_id : null;

  return (
    <div className="flex flex-col gap-4">
      {disabled && disabledReason && <p className="text-white/50 text-xs italic">{disabledReason}</p>}

      {/* stops */}
      <ol className="flex flex-col gap-2">
        {stops.map((stop, i) => {
          const port = portsById.get(stop.port_location_id);
          return (
            <li
              key={`${stop.port_location_id}-${i}`}
              className="flex items-center gap-2 sm:gap-3 rounded-card border border-white/[0.07] bg-white/[0.03] px-3 py-2"
            >
              <span className="w-6 h-6 shrink-0 rounded-full bg-gold/[0.12] text-gold text-xs flex items-center justify-center">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1 flex flex-col">
                <span className="text-white text-sm truncate">{port?.name ?? `Локация #${stop.port_location_id}`}</span>
                <span className={`text-xs truncate ${port?.port_sea_zone_id ? 'text-white/40' : 'text-site-red'}`}>
                  {port
                    ? port.port_sea_zone_name
                      ? `Выход в море: ${port.port_sea_zone_name}`
                      : 'У порта не задан выход в море'
                    : 'Не порт — уберите из маршрута'}
                </span>
              </div>
              {!disabled && (
                <div className="flex items-center shrink-0">
                  <button
                    type="button"
                    aria-label="Выше"
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                    className="w-8 h-8 flex items-center justify-center text-white/50 hover:text-site-blue disabled:opacity-30 transition-colors"
                  >
                    <ArrowUp size={15} />
                  </button>
                  <button
                    type="button"
                    aria-label="Ниже"
                    disabled={i === stops.length - 1}
                    onClick={() => move(i, 1)}
                    className="w-8 h-8 flex items-center justify-center text-white/50 hover:text-site-blue disabled:opacity-30 transition-colors"
                  >
                    <ArrowDown size={15} />
                  </button>
                  <button
                    type="button"
                    aria-label="Убрать остановку"
                    onClick={() => remove(i)}
                    className="w-8 h-8 flex items-center justify-center text-white/50 hover:text-site-red transition-colors"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {stops.length === 0 && <p className="text-white/40 text-sm italic">Добавьте хотя бы два порта.</p>}

      {!disabled && stops.length < maxStops && (
        <div className="flex flex-col sm:flex-row gap-2">
          <select value={adding} onChange={(e) => setAdding(e.target.value)} className={`${FIELD} sm:flex-1 min-w-0`}>
            <option value="">— добавить порт —</option>
            {sortedPorts.map((p) => (
              <option key={p.id} value={p.id} disabled={p.id === lastPortId}>
                {portLabel(p)}
              </option>
            ))}
          </select>
          <button type="button" disabled={!adding} onClick={add} className="btn-blue w-full sm:w-auto shrink-0">
            Добавить
          </button>
        </div>
      )}
      {!disabled && ports.length === 0 && (
        <p className="text-white/50 text-xs">
          Портов пока нет — отметьте локацию как порт и задайте ей выход в море в редакторе локаций.
        </p>
      )}

      {/* legs preview */}
      {stops.length >= 2 && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Route size={15} className="text-gold shrink-0" />
            <span className={LABEL}>Участки пути {isLoop ? '(по кругу)' : '(туда-обратно)'}</span>
            {previewLoading && <span className="text-white/40 text-xs">считаем…</span>}
          </div>
          {previewError && <p className="text-site-red text-sm">{previewError}</p>}
          {legs?.map((leg) => {
            const fromPort = portsById.get(leg.from?.id ?? 0);
            const toPort = portsById.get(leg.to?.id ?? 0);
            const startZone = fromPort?.port_sea_zone_id ?? null;
            const goalZone = toPort?.port_sea_zone_id ?? null;
            const override = stops[leg.index]?.path_override ?? null;
            return (
              <div
                key={leg.index}
                className={`flex flex-col gap-2 rounded-card border px-3 py-2.5 ${
                  leg.ok ? 'border-white/[0.07] bg-white/[0.02]' : 'border-site-red/40 bg-site-red/[0.05]'
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
                  <span className="text-white text-sm min-w-0 break-words">
                    {leg.index + 1}. {leg.from?.name ?? '—'} → {leg.to?.name ?? '—'}
                  </span>
                  <span className="text-white/50 text-xs sm:ml-auto shrink-0">
                    {leg.zones.length ? `${leg.zones.length} зон(ы)` : ''}
                    {leg.minutes != null ? ` · ≈${leg.minutes} мин` : ''}
                    {leg.override ? ' · ручной путь' : leg.zones.length ? ' · кратчайший' : ''}
                  </span>
                </div>
                {leg.zones.length > 0 && (
                  <p className="text-white/60 text-xs break-words">{leg.zones.map((z) => z.name ?? `#${z.id}`).join(' → ')}</p>
                )}
                {leg.problem_text && <p className="text-site-red text-xs">{leg.problem_text}</p>}
                {!disabled && startZone && goalZone && editingLeg !== leg.index && (
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    <button type="button" onClick={() => setEditingLeg(leg.index)} className="site-link text-xs">
                      {override ? 'Изменить ручной путь' : 'Задать путь вручную'}
                    </button>
                    {override && (
                      <button type="button" onClick={() => setOverride(leg.index, null)} className="site-link text-xs">
                        Вернуть кратчайший
                      </button>
                    )}
                  </div>
                )}
                {editingLeg === leg.index && startZone && goalZone && (
                  <OverrideEditor
                    startZone={startZone}
                    goalZone={goalZone}
                    initial={override ?? leg.zones.map((z) => z.id)}
                    zonesById={zonesById}
                    onApply={(path) => setOverride(leg.index, path)}
                    onCancel={() => setEditingLeg(null)}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ShipStopsEditor;
