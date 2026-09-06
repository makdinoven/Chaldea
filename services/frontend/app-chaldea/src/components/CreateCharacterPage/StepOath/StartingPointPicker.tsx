import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchStartingPoints, type StartingPoint } from '../../../api/startingPoints';

/**
 * FEAT-154 (task #18) — «точка первого назначения» (rules 19-20).
 *
 * The picker only ever shows the curated list from
 * `GET /locations/starting-points`; the full 2260-location catalogue is never
 * exposed here — that is the whole point of the `is_starting` flag.
 *
 * The list may legitimately be empty until an administrator flags locations. In
 * that case the step says so plainly instead of pretending to offer a choice:
 * approval falls back to the first curated point, and if none exists at all the
 * moderator is warned server-side (§3.6).
 */

interface StartingPointPickerProps {
  selectedId: number | null;
  onSelect: (point: StartingPoint | null) => void;
}

const StartingPointPicker = ({ selectedId, onSelect }: StartingPointPickerProps) => {
  const [points, setPoints] = useState<StartingPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const notifiedRef = useRef<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchStartingPoints();
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

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = points.find((point) => point.id === selectedId) ?? null;

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
        <button type="button" className="btn-line w-auto px-5" onClick={() => void load()}>
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

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {points.map((point) => {
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
                <img
                  src={point.image_url}
                  alt=""
                  className="w-full h-24 object-cover rounded-card"
                />
              )}
              <span
                className={`text-sm sm:text-base font-medium ${
                  isSelected ? 'gold-text' : 'text-white'
                }`}
              >
                {point.name}
              </span>
              {place && <span className="text-white/40 text-[11px] leading-snug">{place}</span>}
            </button>
          );
        })}
      </div>

      {selected?.starting_blurb && (
        <p className="text-white/70 text-sm leading-relaxed whitespace-pre-wrap">
          {selected.starting_blurb}
        </p>
      )}
    </div>
  );
};

export default StartingPointPicker;
