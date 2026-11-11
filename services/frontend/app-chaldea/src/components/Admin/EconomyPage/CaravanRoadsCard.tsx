import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchCaravanRoads, putCaravanGate } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { searchLocations, type LocationSearchResult } from '../../../api/startingPoints';
import type { CaravanGateSource, CaravanNoRoadReason, CaravanRoadRegion, CaravanRoads } from '../../../types/economy';

/*
  FEAT-211 — «Дороги и ворота» (A6/A7): where every participating region's
  caravans start and end, the admin override, and the region pairs with no road.
*/

const SOURCE_LABEL: Record<CaravanGateSource, string> = {
  override: 'ворота заданы вручную',
  station: 'отделение стражи',
  none: 'нет ворот',
};

const NO_ROAD_LABEL: Record<CaravanNoRoadReason, string> = {
  no_gate: 'у края нет ворот',
  no_path: 'нет пути по связям локаций',
  too_long: 'путь длиннее предела',
};

const SEARCH_MIN = 2;
const SEARCH_LIMIT = 20;
const SEARCH_DELAY_MS = 300;
const NO_ROAD_PAGE = 30;

const regionLabel = (name: string | null, id: number) => name ?? `Край #${id}`;

/** Location search limited (client side) to the region; the server re-checks the region on save. */
const GatePicker = ({
  region,
  saving,
  onPick,
  onCancel,
}: {
  region: CaravanRoadRegion;
  saving: boolean;
  onPick: (loc: LocationSearchResult) => void;
  onCancel: () => void;
}) => {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<LocationSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = q.trim();
    if (query.length < SEARCH_MIN) {
      setHits([]);
      setError(null);
      return undefined;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setSearching(true);
      searchLocations(query, SEARCH_LIMIT)
        .then((res) => {
          if (cancelled) return;
          setHits(region.name ? res.filter((l) => l.region_name === region.name) : res);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!cancelled) setError(e instanceof Error ? e.message : 'Не удалось найти локации');
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, SEARCH_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [q, region.name]);

  return (
    <div className="flex flex-col gap-1.5 min-w-0 w-full">
      <div className="flex items-center gap-2">
        <input
          type="search"
          autoFocus
          className="input-underline !text-sm w-full min-w-0"
          placeholder="Локация этого края: название"
          maxLength={100}
          value={q}
          disabled={saving}
          onChange={(e) => setQ(e.target.value)}
        />
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="text-xs text-white/50 hover:text-white shrink-0 transition-colors duration-200"
        >
          Отмена
        </button>
      </div>
      {searching && <span className="text-white/40 text-xs">Поиск...</span>}
      {error && <span className="text-site-red text-xs">{error}</span>}
      {!searching && !error && q.trim().length >= SEARCH_MIN && hits.length === 0 && (
        <span className="text-white/40 text-xs">В этом крае ничего не найдено.</span>
      )}
      {hits.length > 0 && (
        <ul className="flex flex-col max-h-[200px] overflow-y-auto gold-scrollbar rounded-card border border-white/10">
          {hits.map((l) => (
            <li key={l.id}>
              <button
                type="button"
                disabled={saving}
                onClick={() => onPick(l)}
                className="w-full text-left px-3 py-1.5 text-sm text-white hover:bg-white/[0.06] disabled:opacity-50 transition-colors duration-200"
              >
                {l.name}
                <span className="text-white/40 text-xs"> · #{l.id}{l.district_name ? ` · ${l.district_name}` : ''}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const RegionRow = ({
  region,
  canEdit,
  onSaved,
}: {
  region: CaravanRoadRegion;
  canEdit: boolean;
  onSaved: (r: CaravanRoadRegion) => void;
}) => {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const name = regionLabel(region.name, region.region_id);

  const save = async (locationId: number | null) => {
    setSaving(true);
    setError(null);
    try {
      const saved = await putCaravanGate(region.region_id, locationId);
      toast.success(
        locationId === null
          ? `«${name}»: ворота сброшены`
          : `«${name}»: торговые ворота — ${saved.gate_location_name ?? `#${locationId}`}`,
      );
      setEditing(false);
      onSaved(saved);
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось сохранить торговые ворота');
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const sourceCls =
    region.gate_source === 'none'
      ? 'text-site-red'
      : region.gate_source === 'override'
        ? 'text-gold'
        : 'text-stat-energy';

  return (
    <li className="flex flex-col md:flex-row md:items-start gap-2 md:gap-4 rounded-card border border-white/10 bg-white/[0.03] p-3 min-w-0">
      <div className="flex flex-col min-w-0 md:w-[30%]">
        <span className="text-white text-sm font-medium break-words">{name}</span>
        {region.country_name && <span className="text-white/40 text-xs">{region.country_name}</span>}
      </div>
      <div className="flex flex-col gap-0.5 min-w-0 flex-1 text-xs">
        <span className="text-white/60 break-words">
          Ворота:{' '}
          <span className="text-white">
            {region.gate_location_name ?? (region.gate_location_id ? `#${region.gate_location_id}` : '—')}
          </span>{' '}
          <span className={sourceCls}>({SOURCE_LABEL[region.gate_source] ?? region.gate_source})</span>
        </span>
        <span className="text-white/40 break-words">
          Отделение стражи: {region.station_location_name ?? (region.station_location_id ? `#${region.station_location_id}` : 'не назначено')}
        </span>
        {error && <span className="text-site-red">{error}</span>}
      </div>
      {canEdit && (
        <div className="flex flex-col gap-1.5 min-w-0 md:w-[38%]">
          {editing ? (
            <GatePicker
              region={region}
              saving={saving}
              onPick={(l) => void save(l.id)}
              onCancel={() => setEditing(false)}
            />
          ) : (
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                className="text-sm text-site-blue hover:text-white transition-colors duration-200"
                onClick={() => setEditing(true)}
              >
                {region.gate_override_id ? 'Изменить ворота' : 'Задать ворота'}
              </button>
              {region.gate_override_id && (
                <button
                  type="button"
                  disabled={saving}
                  className="text-sm text-site-red hover:text-white disabled:opacity-50 transition-colors duration-200"
                  onClick={() => void save(null)}
                >
                  {saving ? 'Сброс...' : 'Сбросить на отделение стражи'}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
};

const CaravanRoadsCard = ({ canEdit, reloadKey }: { canEdit: boolean; reloadKey: number }) => {
  const [data, setData] = useState<CaravanRoads | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [shownNoRoad, setShownNoRoad] = useState(NO_ROAD_PAGE);

  const load = useCallback(() => {
    setLoading(true);
    fetchCaravanRoads()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить дороги караванов');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load, reloadKey]);

  const regions = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = [...(data?.regions ?? [])].sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'ru'));
    return q ? list.filter((r) => (r.name ?? '').toLowerCase().includes(q) || (r.country_name ?? '').toLowerCase().includes(q)) : list;
  }, [data, query]);

  // A new override changes the road list too — reload it after a save.
  const replaceRegion = () => load();

  return (
    <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
      <div className="flex flex-col gap-1">
        <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Дороги и ворота</h2>
        <p className="text-white/50 text-sm">
          Физический караван едет от торговых ворот края-продавца до ворот края-покупателя по связям локаций (без
          подземелий). По умолчанию ворота — отделение стражи края. Если дороги нет, караван остаётся абстрактным.
        </p>
      </div>

      {error && !data ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !text-sm" onClick={load}>
            Повторить
          </button>
        </div>
      ) : !data ? (
        <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      ) : (
        <div className={`flex flex-col gap-4 ${loading ? 'opacity-60' : ''}`}>
          <div className="flex flex-col gap-2">
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">
              Нет дороги ({data.no_road.length})
            </span>
            {data.no_road.length === 0 ? (
              <p className="text-stat-energy text-sm">Все пары торгующих краёв соединены дорогами.</p>
            ) : (
              <>
                <ul className="flex flex-col gap-1">
                  {data.no_road.slice(0, shownNoRoad).map((p) => (
                    <li
                      key={`${p.from_region_id}-${p.to_region_id}`}
                      className="text-xs text-white/70 rounded-card border border-site-red/20 bg-site-red/[0.04] px-3 py-1.5 break-words"
                    >
                      {regionLabel(p.from_name, p.from_region_id)} <span className="text-gold/70">↔</span>{' '}
                      {regionLabel(p.to_name, p.to_region_id)}:{' '}
                      <span className="text-site-red">{NO_ROAD_LABEL[p.reason] ?? p.reason}</span>
                    </li>
                  ))}
                </ul>
                {data.no_road.length > shownNoRoad && (
                  <button
                    type="button"
                    className="btn-line self-start !text-sm"
                    onClick={() => setShownNoRoad((n) => n + NO_ROAD_PAGE)}
                  >
                    Показать ещё ({data.no_road.length - shownNoRoad})
                  </button>
                )}
              </>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <span className="text-white/60 text-xs uppercase tracking-[0.06em] mr-auto">
                Края ({data.regions.length})
              </span>
              <input
                type="search"
                className="input-underline w-full sm:max-w-[280px]"
                placeholder="Поиск края или страны"
                maxLength={100}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            {regions.length === 0 ? (
              <p className="text-white/40 text-sm">Краёв нет.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {regions.map((r) => (
                  <RegionRow
                    key={`${r.region_id}-${r.gate_location_id ?? 0}-${r.gate_source}`}
                    region={r}
                    canEdit={canEdit}
                    onSaved={replaceRegion}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      {!canEdit && <p className="field-hint">Менять ворота может администратор с правом «economy:settings».</p>}
    </section>
  );
};

export default CaravanRoadsCard;
