import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
  RECOMMENDED_LEVEL_MAX,
  RECOMMENDED_LEVEL_MIN,
  fetchRecommendedLevel,
  type RecommendedLevelInfo,
  type RecommendedLevelTarget,
} from '../../../api/recommendedLevel';

interface RecommendedLevelFieldsProps {
  targetType: RecommendedLevelTarget;
  /** Undefined for an entity that is not created yet */
  targetId?: number;
  min: string;
  max: string;
  onChange: (min: string, max: string) => void;
}

const inputClass =
  'w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none';

const formatAuto = (info: RecommendedLevelInfo | null): string => {
  if (!info || (info.auto_min == null && info.auto_max == null)) return 'нет локаций';
  return info.auto_min === info.auto_max ? `${info.auto_min}` : `${info.auto_min}–${info.auto_max}`;
};

/** Admin override of a country/region recommended level; empty inputs = computed from locations */
const RecommendedLevelFields = ({ targetType, targetId, min, max, onChange }: RecommendedLevelFieldsProps) => {
  const [info, setInfo] = useState<RecommendedLevelInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const touched = useRef(false);

  useEffect(() => {
    if (!targetId) return;
    let cancelled = false;
    setLoading(true);
    fetchRecommendedLevel(targetType, targetId)
      .then((data) => {
        if (cancelled) return;
        setInfo(data);
        // Prefill the stored override unless the admin already started typing
        if (!touched.current) {
          onChange(data.manual_min?.toString() ?? '', data.manual_max?.toString() ?? '');
        }
      })
      .catch(() => {
        if (!cancelled) toast.error('Не удалось загрузить рекомендуемый уровень');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // onChange is a fresh closure each render; loading once per entity is intended
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetType, targetId]);

  const change = (nextMin: string, nextMax: string) => {
    touched.current = true;
    onChange(nextMin, nextMax);
  };

  return (
    <div className="mb-6">
      <label className="block mb-2 text-[#8ab3d5] font-medium">РЕКОМЕНДУЕМЫЙ УРОВЕНЬ:</label>
      <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-gray-400">от</span>
          <input
            type="number"
            min={RECOMMENDED_LEVEL_MIN}
            max={RECOMMENDED_LEVEL_MAX}
            step={1}
            value={min}
            placeholder="авто"
            onChange={(e) => change(e.target.value, max)}
            className={inputClass}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-gray-400">до</span>
          <input
            type="number"
            min={RECOMMENDED_LEVEL_MIN}
            max={RECOMMENDED_LEVEL_MAX}
            step={1}
            value={max}
            placeholder="авто"
            onChange={(e) => change(min, e.target.value)}
            className={inputClass}
          />
        </label>
      </div>
      <p className="text-xs text-gray-400 mt-2">
        {targetId
          ? loading
            ? 'Считаем по локациям…'
            : `Автоматически: ${formatAuto(info)}. Пустое поле — значение считается по локациям.`
          : 'Пустое поле — значение считается по локациям.'}
      </p>
    </div>
  );
};

export default RecommendedLevelFields;
