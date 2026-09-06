import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import toast from 'react-hot-toast';
import {
  addOriginStartingPoint,
  fetchOriginStartingPoints,
  removeOriginStartingPoint,
  searchLocations,
  setOriginStartingPoints,
  type LocationSearchResult,
  type StartingPoint,
} from '../../../api/startingPoints';

/**
 * FEAT-155 (rules 5-7, 13) — the recommended starting points of one origin.
 *
 * This screen exists because the only other way to mark a starting point is the
 * location form at the bottom of a five-level tree (область → страна → регион →
 * район → локация), and that form cannot express «this point belongs to that
 * country» at all. Here the admin searches the whole 2287-location catalogue by
 * name (rule 6) and assembles the set in one place.
 *
 * **Order carries meaning.** The first point of the set is what the wizard
 * presents to the player as his homeland (rule 13); there is no separate
 * «home» flag. Hence the explicit move controls — composition alone is not
 * enough.
 *
 * Writes go through the endpoint that matches the intent: `POST` appends,
 * `DELETE` unlinks, and only a reorder needs the whole-set `PUT`. Each one
 * answers with the resulting set, so the panel never has to guess.
 */

interface OriginStartingPointsProps {
  originId: number;
  originName: string;
  /** `origins:update` — without it the panel is read-only (`origins:read`). */
  canUpdate: boolean;
  onClose: () => void;
}

/** Long enough that typing «Ворота» is one request, short enough to feel live. */
const SEARCH_DEBOUNCE_MS = 350;
const SEARCH_LIMIT = 20;
const MIN_QUERY_LENGTH = 2;

const errorText = (error: unknown, fallback: string): string =>
  error instanceof Error && error.message ? error.message : fallback;

const breadcrumbs = (point: {
  district_name: string | null;
  region_name: string | null;
  country_name: string | null;
}): string =>
  [point.district_name, point.region_name, point.country_name].filter(Boolean).join(' · ');

const OriginStartingPoints = ({
  originId,
  originName,
  canUpdate,
  onClose,
}: OriginStartingPointsProps) => {
  const [points, setPoints] = useState<StartingPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<LocationSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setPoints(await fetchOriginStartingPoints(originId));
    } catch (err) {
      const message = errorText(err, 'Не удалось загрузить рекомендованные точки.');
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [originId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Debounced search. A query shorter than two characters would return noise
  // from a 2287-row catalogue, so we simply do not ask.
  const searchSeq = useRef(0);
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([]);
      setSearchError(null);
      setSearching(false);
      setSearched(false);
      return;
    }

    const seq = ++searchSeq.current;
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchLocations(trimmed, SEARCH_LIMIT)
        .then((data) => {
          if (seq !== searchSeq.current) return;
          setResults(data);
          setSearchError(null);
        })
        .catch((err) => {
          if (seq !== searchSeq.current) return;
          // Inline, not a toast: the admin is typing, and a toast per keystroke
          // would bury the page.
          setResults([]);
          setSearchError(errorText(err, 'Не удалось выполнить поиск локаций.'));
        })
        .finally(() => {
          if (seq !== searchSeq.current) return;
          setSearching(false);
          setSearched(true);
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [query]);

  const chosenIds = useMemo(() => new Set(points.map((point) => point.id)), [points]);

  const handleAdd = async (location: LocationSearchResult) => {
    if (busy || chosenIds.has(location.id)) return;
    setBusy(true);
    try {
      setPoints(await addOriginStartingPoint(originId, location.id));
      toast.success(
        location.is_starting
          ? `«${location.name}» добавлена в набор`
          : `«${location.name}» добавлена в набор и стала стартовой точкой`,
      );
      // The hit is stale now — the location is a starting point either way.
      setResults((prev) =>
        prev.map((item) => (item.id === location.id ? { ...item, is_starting: true } : item)),
      );
    } catch (err) {
      toast.error(errorText(err, 'Не удалось добавить точку в набор.'));
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (point: StartingPoint) => {
    if (busy) return;
    setBusy(true);
    try {
      setPoints(await removeOriginStartingPoint(originId, point.id));
      toast.success(`«${point.name}» убрана из набора`);
    } catch (err) {
      toast.error(errorText(err, 'Не удалось убрать точку из набора.'));
    } finally {
      setBusy(false);
    }
  };

  /**
   * Moves one point by `delta` and persists the whole order (the `PUT` is the
   * only endpoint that can express order). Optimistic, because waiting out a
   * round trip on every arrow click makes reordering feel broken; on failure
   * the previous order is restored and the reason is shown.
   */
  const handleMove = async (index: number, delta: number) => {
    const target = index + delta;
    if (busy || target < 0 || target >= points.length) return;

    const previous = points;
    const reordered = [...points];
    const [moved] = reordered.splice(index, 1);
    reordered.splice(target, 0, moved);
    setPoints(reordered);

    setBusy(true);
    try {
      setPoints(
        await setOriginStartingPoints(
          originId,
          reordered.map((point) => point.id),
        ),
      );
    } catch (err) {
      setPoints(previous);
      toast.error(errorText(err, 'Не удалось сохранить порядок точек.'));
    } finally {
      setBusy(false);
    }
  };

  const handleOverlayClick = (event: React.MouseEvent) => {
    if (event.target === event.currentTarget) onClose();
  };

  // Portalled for the same reason as `OriginForm`: the admin page renders
  // inside an animated (transformed) wrapper, which would become the containing
  // block for `position: fixed` and trap this overlay under the site header.
  return createPortal(
    <div
      className="fixed inset-0 bg-black/85 z-[1000] overflow-y-auto py-6 px-3 sm:py-10 sm:px-5 flex items-start justify-center"
      onClick={handleOverlayClick}
    >
      <div className="modal-content gold-outline gold-outline-thick w-full max-w-3xl">
        <h2 className="gold-text text-lg sm:text-2xl uppercase mb-2 break-words">
          Стартовые точки: {originName}
        </h2>
        <p className="field-hint mb-5">
          Это подсказка для игрока, а не ограничение: выбрать он сможет любую точку. Первая
          точка набора подаётся как родина персонажа — порядок задаёте вы. Локация, ещё не
          отмеченная стартовой, становится ею при добавлении сюда.
        </p>

        {/* ── The curated set ─────────────────────────────────────────── */}
        {loading && <p className="text-white/60 text-sm py-4">Загрузка набора…</p>}

        {!loading && loadError && (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5 p-3 rounded border border-site-red/40 bg-site-red/10">
            <p className="text-site-red text-sm flex-1">{loadError}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="px-4 py-1.5 bg-white/10 text-white rounded text-sm transition-colors hover:bg-white/20"
            >
              Повторить
            </button>
          </div>
        )}

        {!loading && !loadError && points.length === 0 && (
          <p className="text-white/60 text-sm py-2 mb-4">
            Набор пуст. Игрок с этим происхождением увидит шаг «Присяга» без подсказок —
            ровно как раньше.
          </p>
        )}

        {points.length > 0 && (
          <ol className="flex flex-col gap-2 mb-6">
            {points.map((point, index) => (
              <li
                key={point.id}
                className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 p-3 rounded-card bg-white/[0.05]"
              >
                <span className="text-white/40 text-xs w-6 shrink-0">{index + 1}.</span>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-white text-sm sm:text-base font-medium break-words">
                      {point.name}
                    </span>
                    {index === 0 && (
                      <span className="text-xs px-2 py-0.5 rounded-full border border-gold/50 text-gold">
                        Родина
                      </span>
                    )}
                  </div>
                  {breadcrumbs(point) && (
                    <p className="text-white/40 text-[11px] leading-snug break-words">
                      {breadcrumbs(point)}
                    </p>
                  )}
                </div>

                {canUpdate && (
                  <div className="flex flex-wrap gap-2 sm:shrink-0">
                    <button
                      type="button"
                      onClick={() => void handleMove(index, -1)}
                      disabled={busy || index === 0}
                      aria-label={`Поднять «${point.name}» выше`}
                      title="Выше"
                      className="px-3 py-1.5 bg-white/10 text-white rounded text-sm transition-colors
                        hover:bg-white/20 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleMove(index, 1)}
                      disabled={busy || index === points.length - 1}
                      aria-label={`Опустить «${point.name}» ниже`}
                      title="Ниже"
                      className="px-3 py-1.5 bg-white/10 text-white rounded text-sm transition-colors
                        hover:bg-white/20 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleRemove(point)}
                      disabled={busy}
                      className="px-3 py-1.5 bg-site-red/20 text-site-red rounded text-sm transition-colors
                        hover:bg-site-red/30 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Убрать
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}

        {/* ── Search over the whole catalogue (rule 6) ─────────────────── */}
        {canUpdate && (
          <div className="flex flex-col gap-2">
            <label
              htmlFor="origin-location-search"
              className="block text-white/60 font-medium text-sm uppercase tracking-wide"
            >
              Добавить точку
            </label>
            <input
              id="origin-location-search"
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Название локации или её номер"
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-white
                transition-colors focus:border-site-blue/50 focus:outline-none"
            />

            {query.trim().length > 0 && query.trim().length < MIN_QUERY_LENGTH && (
              <p className="text-white/40 text-xs">Введите хотя бы два символа.</p>
            )}
            {searching && <p className="text-white/40 text-xs">Ищем…</p>}
            {searchError && <p className="text-site-red text-xs">{searchError}</p>}
            {!searching && !searchError && searched && results.length === 0 && (
              <p className="text-white/40 text-xs">Ничего не нашлось.</p>
            )}

            {results.length > 0 && (
              <ul className="flex flex-col gap-2 max-h-[320px] overflow-y-auto gold-scrollbar pr-1">
                {results.map((location) => {
                  const already = chosenIds.has(location.id);
                  return (
                    <li
                      key={location.id}
                      className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 p-3 rounded-card bg-white/[0.03]"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-white text-sm break-words">{location.name}</span>
                          <span className="text-white/30 text-[11px]">#{location.id}</span>
                          {!location.is_starting && (
                            <span className="text-xs px-2 py-0.5 rounded-full border border-white/20 text-white/60">
                              Станет стартовой
                            </span>
                          )}
                        </div>
                        {breadcrumbs(location) && (
                          <p className="text-white/40 text-[11px] leading-snug break-words">
                            {breadcrumbs(location)}
                          </p>
                        )}
                      </div>

                      <button
                        type="button"
                        onClick={() => void handleAdd(location)}
                        disabled={busy || already}
                        className="px-3 py-1.5 bg-green-600/20 text-white rounded text-sm transition-colors
                          hover:bg-green-600/30 disabled:opacity-40 disabled:cursor-not-allowed sm:shrink-0"
                      >
                        {already ? 'Уже в наборе' : 'Добавить'}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}

        {!canUpdate && (
          <p className="text-white/40 text-xs">
            Права «origins:update» у вас нет — набор доступен только для просмотра.
          </p>
        )}

        <div className="flex mt-6">
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-2 bg-white/10 text-white rounded font-medium transition-colors hover:bg-white/20"
          >
            Готово
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
};

export default OriginStartingPoints;
