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
} from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { selectGameTimeAdmin } from '../../redux/slices/gameTimeSlice';
import {
  fetchGameTimeAdmin,
  updateGameTimeAdminThunk,
} from '../../redux/actions/gameTimeActions';
import { SEGMENT_LABELS, YEAR_SEGMENTS } from '../../utils/gameTime';

const SEGMENT_ICON_MAP: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
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

  // Change epoch state
  const [epochInput, setEpochInput] = useState('');

  useEffect(() => {
    dispatch(fetchGameTimeAdmin());
  }, [dispatch]);

  // Sync epoch input when admin data arrives
  useEffect(() => {
    if (admin.epoch) {
      // Convert ISO string to datetime-local format (YYYY-MM-DDTHH:mm)
      const dt = new Date(admin.epoch);
      const local = dt.getFullYear().toString().padStart(4, '0')
        + '-' + (dt.getMonth() + 1).toString().padStart(2, '0')
        + '-' + dt.getDate().toString().padStart(2, '0')
        + 'T' + dt.getHours().toString().padStart(2, '0')
        + ':' + dt.getMinutes().toString().padStart(2, '0');
      setEpochInput(local);
    }
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
    try {
      await dispatch(
        updateGameTimeAdminThunk({ epoch: new Date(epochInput).toISOString() }),
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
                  Epoch: {admin.epoch ? new Date(admin.epoch).toLocaleDateString('ru-RU') : '—'}
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
