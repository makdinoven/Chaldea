import { useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchStartingPoints, type StartingPoint } from '../../../api/startingPoints';

/**
 * FEAT-154 (task #18) — «точка первого назначения» (rules 19-20).
 *
 * The picker only ever shows the curated list from
 * `GET /locations/starting-points`; the full 2287-location catalogue is never
 * exposed here — that is the whole point of the `is_starting` flag.
 *
 * The list may legitimately be empty until an administrator flags locations. In
 * that case the step says so plainly instead of pretending to offer a choice:
 * approval falls back to the first curated point, and if none exists at all the
 * moderator is warned server-side (§3.6).
 *
 * FEAT-155 — with an origin chosen on step 2, the list is the same list: the
 * points an administrator recommended for that origin simply come first and are
 * introduced (rules 2-3). The **first** recommended point is presented as the
 * character's homeland (rule 13) — there is no field saying so, the position in
 * the curated order is what says it. Without recommendations nothing above
 * appears at all (rule 4), and every point stays selectable either way.
 */

interface StartingPointPickerProps {
  selectedId: number | null;
  onSelect: (point: StartingPoint | null) => void;
  /** The origin picked on step «Родина». `null` → the plain FEAT-154 list. */
  originId?: number | null;
}

const StartingPointPicker = ({ selectedId, onSelect, originId = null }: StartingPointPickerProps) => {
  const [points, setPoints] = useState<StartingPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const notifiedRef = useRef<string | null>(null);

  const load = async (forOriginId: number | null) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchStartingPoints(forOriginId);
      setPoints(data);
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'Не удалось загрузить список стартовых точек.';
      setError(message);
      // The failure must reach the player, not only the console.
      if (notifiedRef.current !== message) {
        notifiedRef.current = message;
        toast.error(message);
      }
    } finally {
      setLoading(false);
    }
  };

  // Re-read when the player goes back and changes his origin: the annotations
  // and the order belong to that origin, not to the session.
  useEffect(() => {
    void load(originId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [originId]);

  const selected = points.find((point) => point.id === selectedId) ?? null;

  /**
   * The backend already sorts recommended points first, so «recommended» and
   * «the rest» are a prefix and a suffix — no re-sorting here, which is also
   * what keeps the curated order (and therefore the homeland) intact.
   */
  const recommended = useMemo(
    () => points.filter((point) => point.is_recommended),
    [points],
  );
  const others = useMemo(
    () => points.filter((point) => !point.is_recommended),
    [points],
  );

  if (loading && points.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-8 h-8 border-4 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (error && points.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-8">
        <p className="text-site-red text-sm text-center">{error}</p>
        <button type="button" className="btn-line w-auto px-5" onClick={() => void load(originId)}>
          Повторить
        </button>
      </div>
    );
  }

  if (points.length === 0) {
    return (
      <p className="text-white/60 text-sm py-6">
        Координатор ещё не утвердил список точек назначения. Заявку можно отправить и так —
        место вам назначат при одобрении.
      </p>
    );
  }

  const renderPoint = (point: StartingPoint, isHomeland: boolean) => {
    const isSelected = point.id === selectedId;
    const place = [point.district_name, point.region_name, point.country_name]
      .filter(Boolean)
      .join(' · ');

    return (
      <button
        key={point.id}
        type="button"
        aria-pressed={isSelected}
        onClick={() => onSelect(isSelected ? null : point)}
        className={`flex flex-col gap-2 p-3 rounded-card text-left transition-colors duration-200 ease-site
          ${isSelected ? 'gold-outline bg-white/[0.06]' : 'hover:bg-white/5'}`}
      >
        {point.image_url && (
          <img src={point.image_url} alt="" className="w-full h-24 object-cover rounded-card" />
        )}
        <span className="flex flex-wrap items-center gap-2">
          <span
            className={`text-sm sm:text-base font-medium ${isSelected ? 'gold-text' : 'text-white'}`}
          >
            {point.name}
          </span>
          {isHomeland && (
            <span className="text-[11px] px-2 py-0.5 rounded-full border border-gold/50 text-gold">
              Ваша родина
            </span>
          )}
        </span>
        {place && <span className="text-white/40 text-[11px] leading-snug">{place}</span>}
      </button>
    );
  };

  const gridClass = 'grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3';

  return (
    <div className="flex flex-col gap-4">
      {/*
        Rule 4 — with no recommendations the step is exactly what it was: one
        plain grid, no heading, no empty block, nothing marked.
      */}
      {recommended.length === 0 ? (
        <div className={gridClass}>{others.map((point) => renderPoint(point, false))}</div>
      ) : (
        <>
          <section className="flex flex-col gap-3">
            <h4 className="gold-text text-base sm:text-lg font-semibold">Родные края</h4>
            <p className="field-hint max-w-[720px]">
              {recommended.length > 1
                ? 'Первая — место, где вы выросли; остальные здесь хорошо знают ваших земляков. Это подсказка: сойти на берег вы вправе где угодно.'
                : 'Место, где вы выросли. Это подсказка: сойти на берег вы вправе где угодно.'}
            </p>
            <div className={gridClass}>
              {recommended.map((point, index) => renderPoint(point, index === 0))}
            </div>
          </section>

          {others.length > 0 && (
            <section className="flex flex-col gap-3 mt-2">
              <h4 className="text-white/70 text-base sm:text-lg font-semibold">Остальной мир</h4>
              <div className={gridClass}>{others.map((point) => renderPoint(point, false))}</div>
            </section>
          )}
        </>
      )}

      {selected?.starting_blurb && (
        <p className="text-white/70 text-sm leading-relaxed whitespace-pre-wrap">
          {selected.starting_blurb}
        </p>
      )}
    </div>
  );
};

export default StartingPointPicker;
