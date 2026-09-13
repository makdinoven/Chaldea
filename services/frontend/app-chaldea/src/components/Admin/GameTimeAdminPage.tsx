import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  Droplet,
  Sun,
  Wind,
  CloudSnow,
  Zap,
  Award,
  Moon,
  Star,
  Icon as FeatherIcon,
} from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { selectGameTimeAdmin } from '../../redux/slices/gameTimeSlice';
import {
  fetchGameTimeAdmin,
  updateGameTimeAdminThunk,
} from '../../redux/actions/gameTimeActions';
import { SEGMENT_LABELS, YEAR_SEGMENTS } from '../../utils/gameTime';
import { formatServerDate, parseServerDate } from '../../utils/serverDate';

const pad = (value: number, length = 2): string => String(value).padStart(length, '0');

/**
 * FEAT-161: `<input type="datetime-local">` carries no zone, so it is filled
 * from — and read back into — the player's local wall clock. The epoch is
 * stored and returned by the backend as naive **UTC**, so both directions must
 * cross that boundary explicitly. Getting only one of them right is what used
 * to shift the stored epoch by the admin's UTC offset on every save.
 */
const toDateTimeLocalInput = (raw: string | null): string => {
  const date = parseServerDate(raw);
  if (!date) return '';
  return (
    `${pad(date.getFullYear(), 4)}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
};

/**
 * Serialise back in the exact shape the backend already emits: naive UTC, no
 * zone designator. Sending an offset-carrying string would make Pydantic build
 * an aware datetime, which `compute_game_time` (naive arithmetic) cannot mix.
 */
const toNaiveUtcIso = (date: Date): string =>
  `${pad(date.getUTCFullYear(), 4)}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`
  + `T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`;

const SEGMENT_ICON_MAP: Record<string, FeatherIcon> = {
  spring: Droplet,
  summer: Sun,
  autumn: Wind,
  winter: CloudSnow,
  beltane: Zap,
  lughnasad: Award,
  samhain: Moon,
  imbolc: Star,
};

const GameTimeAdminPage = () => {
  const dispatch = useAppDispatch();
  const admin = useAppSelector(selectGameTimeAdmin);

  // Shift time state
  const [shiftDays, setShiftDays] = useState(1);

  // Set specific date state
  const [targetYear, setTargetYear] = useState(1);
  const [targetSegment, setTargetSegment] = useState('spring');
  const [targetWeek, setTargetWeek] = useState(1);

  // Change epoch state. `loadedEpoch` keeps the raw string exactly as the API
  // returned it so an untouched Save can send it back byte-for-byte instead of
  // re-serialising it (which would silently drop sub-minute precision).
  const [epochInput, setEpochInput] = useState('');
  const [loadedEpoch, setLoadedEpoch] = useState<{ raw: string; input: string } | null>(null);

  useEffect(() => {
    dispatch(fetchGameTimeAdmin());
  }, [dispatch]);

  // Sync epoch input when admin data arrives
  useEffect(() => {
    if (!admin.epoch) return;
    const local = toDateTimeLocalInput(admin.epoch);
    setEpochInput(local);
    setLoadedEpoch({ raw: admin.epoch, input: local });
  }, [admin.epoch]);

  // Sync computed values into set-date form when admin data loads
  useEffect(() => {
    if (admin.computed) {
      setTargetYear(admin.computed.year);
      setTargetSegment(admin.computed.segment_name);
      if (admin.computed.week) {
        setTargetWeek(admin.computed.week);
      }
    }
  }, [admin.computed]);

  const isTransitionSegment = YEAR_SEGMENTS.some(
    (s) => s.name === targetSegment && s.type === 'transition',
  );

  const handleShift = async (direction: 1 | -1) => {
    const newOffset = admin.offsetDays + shiftDays * direction;
    try {
      await dispatch(updateGameTimeAdminThunk({ offset_days: newOffset })).unwrap();
      toast.success('Время обновлено');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось обновить время');
    }
  };

  const handleSetDate = async () => {
    try {
      await dispatch(
        updateGameTimeAdminThunk({
          target_year: targetYear,
          target_segment: targetSegment,
          target_week: isTransitionSegment ? undefined : targetWeek,
        }),
      ).unwrap();
      toast.success('Дата установлена');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось установить дату');
    }
  };

  const handleSaveEpoch = async () => {
    if (!epochInput) {
      toast.error('Укажите дату точки отсчёта');
      return;
    }
    // Untouched input → send back exactly what we were given, so an
    // open-and-save with no edit is a provably lossless round trip.
    let epoch: string;
    if (loadedEpoch && epochInput === loadedEpoch.input) {
      epoch = loadedEpoch.raw;
    } else {
      const parsed = new Date(epochInput);
      if (Number.isNaN(parsed.getTime())) {
        toast.error('Некорректная дата точки отсчёта');
        return;
      }
      epoch = toNaiveUtcIso(parsed);
    }
    try {
      await dispatch(
        updateGameTimeAdminThunk({ epoch }),
      ).unwrap();
      toast.success('Точка отсчёта обновлена');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось обновить точку отсчёта');
    }
  };

  // Computed display values
  const computed = admin.computed;
  const Icon = computed ? SEGMENT_ICON_MAP[computed.segment_name] : null;
  const segmentLabel = computed ? SEGMENT_LABELS[computed.segment_name] ?? computed.segment_name : '';
  const displayText = computed
    ? computed.is_transition
      ? `${segmentLabel} | ${computed.year}-й год`
      : `${segmentLabel}, ${computed.week}-я неделя, ${computed.year}-й год`
    : '';

  if (admin.loading && !admin.computed) {
    return (
      <div className="w-full max-w-[800px] mx-auto">
        <h1 className="gold-text text-3xl font-medium uppercase tracking-[0.06em] mb-8">
          Игровое время
        </h1>
        <div className="gray-bg rounded-card p-6 text-white/60">Загрузка...</div>
      </div>
    );
  }

  if (admin.error && !admin.computed) {
    return (
      <div className="w-full max-w-[800px] mx-auto">
        <h1 className="gold-text text-3xl font-medium uppercase tracking-[0.06em] mb-8">
          Игровое время
        </h1>
        <div className="gray-bg rounded-card p-6 text-site-red">{admin.error}</div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[800px] mx-auto">
      <h1 className="gold-text text-3xl font-medium uppercase tracking-[0.06em] mb-8">
        Игровое время
      </h1>

      <div className="flex flex-col gap-6">
        {/* Section 1: Current Time Display */}
        <section className="gray-bg rounded-card p-6">
          <h2 className="text-white text-lg font-medium uppercase tracking-[0.06em] mb-4">
            Текущее время
          </h2>
          {computed && (
            <div>
              <div className="flex items-center gap-3 mb-2">
                {Icon && <Icon size={24} className="text-gold" />}
                <span className="text-white text-xl font-medium">{displayText}</span>
              </div>
              <div className="text-white/60 text-sm flex flex-wrap gap-x-4 gap-y-1">
                <span>
                  Epoch: {formatServerDate(admin.epoch, {})}
                </span>
                <span>
                  Offset: {admin.offsetDays >= 0 ? '+' : ''}
                  {admin.offsetDays} дней
                </span>
              </div>
            </div>
          )}
        </section>

        {/* Section 2: Shift Time */}
        <section className="gray-bg rounded-card p-6">
          <h2 className="text-white text-lg font-medium uppercase tracking-[0.06em] mb-4">
            Сдвинуть время
          </h2>
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4">
            <label className="flex flex-col gap-1 flex-1 min-w-0 w-full sm:w-auto">
              <span className="text-white/80 text-sm">Количество дней</span>
              <input
                type="number"
                min={1}
                value={shiftDays}
                onChange={(e) => setShiftDays(Math.max(1, parseInt(e.target.value) || 1))}
                className="input-underline w-full"
              />
            </label>
            <div className="flex gap-3 w-full sm:w-auto">
              <button
                className="btn-blue flex-1 sm:flex-initial"
                disabled={admin.loading}
                onClick={() => handleShift(1)}
              >
                Вперёд
              </button>
              <button
                className="btn-blue flex-1 sm:flex-initial"
                disabled={admin.loading}
                onClick={() => handleShift(-1)}
              >
                Назад
              </button>
            </div>
          </div>
        </section>

        {/* Section 3: Set Specific Date */}
        <section className="gray-bg rounded-card p-6">
          <h2 className="text-white text-lg font-medium uppercase tracking-[0.06em] mb-4">
            Установить дату
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            <label className="flex flex-col gap-1">
              <span className="text-white/80 text-sm">Год</span>
              <input
                type="number"
                min={1}
                value={targetYear}
                onChange={(e) => setTargetYear(Math.max(1, parseInt(e.target.value) || 1))}
                className="input-underline w-full"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-white/80 text-sm">Сезон / переход</span>
              <select
                value={targetSegment}
                onChange={(e) => setTargetSegment(e.target.value)}
                className="input-underline w-full bg-transparent text-white"
              >
                {YEAR_SEGMENTS.map((seg) => (
                  <option key={seg.name} value={seg.name} className="bg-site-dark text-white">
                    {SEGMENT_LABELS[seg.name]}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-white/80 text-sm">Неделя</span>
              <input
                type="number"
                min={1}
                max={13}
                value={targetWeek}
                onChange={(e) =>
                  setTargetWeek(Math.min(13, Math.max(1, parseInt(e.target.value) || 1)))
                }
                disabled={isTransitionSegment}
                className="input-underline w-full disabled:opacity-40 disabled:cursor-not-allowed"
              />
            </label>
          </div>
          <button
            className="btn-blue"
            disabled={admin.loading}
            onClick={handleSetDate}
          >
            Установить
          </button>
        </section>

        {/* Section 4: Change Epoch */}
        <section className="gray-bg rounded-card p-6">
          <h2 className="text-white text-lg font-medium uppercase tracking-[0.06em] mb-4">
            Точка отсчёта
          </h2>
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4">
            <label className="flex flex-col gap-1 flex-1 min-w-0 w-full sm:w-auto">
              <span className="text-white/80 text-sm">Дата и время начала эпохи</span>
              <input
                type="datetime-local"
                value={epochInput}
                onChange={(e) => setEpochInput(e.target.value)}
                className="input-underline w-full"
              />
            </label>
            <button
              className="btn-blue w-full sm:w-auto"
              disabled={admin.loading}
              onClick={handleSaveEpoch}
            >
              Сохранить
            </button>
          </div>
        </section>
      </div>
    </div>
  );
};

export default GameTimeAdminPage;
