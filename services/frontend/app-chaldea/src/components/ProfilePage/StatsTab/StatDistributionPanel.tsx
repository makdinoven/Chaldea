import { useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../../redux/store';
import {
  upgradeStats,
  CharacterAttributes,
  UpgradeStatsPayload,
} from '../../../redux/slices/profileSlice';
import { UPGRADEABLE_STATS, STAT_LABELS } from '../constants';

interface StatDistributionPanelProps {
  characterId: number;
  statPoints: number;
  attributes: CharacterAttributes;
}

type PendingChanges = Record<string, number>;

const StatDistributionPanel = ({
  characterId,
  statPoints,
  attributes,
}: StatDistributionPanelProps) => {
  const dispatch = useAppDispatch();
  const [pending, setPending] = useState<PendingChanges>({});
  const [saving, setSaving] = useState(false);

  const totalPending = Object.values(pending).reduce((sum, v) => sum + v, 0);
  const remaining = statPoints - totalPending;

  const handleIncrement = useCallback(
    (stat: string) => {
      if (remaining <= 0) return;
      setPending((prev) => ({
        ...prev,
        [stat]: (prev[stat] ?? 0) + 1,
      }));
    },
    [remaining],
  );

  const handleDecrement = useCallback((stat: string) => {
    setPending((prev) => {
      const current = prev[stat] ?? 0;
      if (current <= 0) return prev;
      const updated = { ...prev, [stat]: current - 1 };
      if (updated[stat] === 0) delete updated[stat];
      return updated;
    });
  }, []);

  const handleSave = async () => {
    if (totalPending <= 0) return;
    setSaving(true);
    try {
      const stats: UpgradeStatsPayload = {};
      for (const [key, value] of Object.entries(pending)) {
        if (value > 0) {
          (stats as Record<string, number>)[key] = value;
        }
      }
      await dispatch(upgradeStats({ characterId, stats })).unwrap();
      setPending({});
      toast.success('Характеристики успешно улучшены!');
    } catch (err) {
      const message =
        typeof err === 'string' ? err : 'Не удалось распределить очки';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  if (statPoints <= 0 && totalPending <= 0) {
    return null;
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <h3 className="gold-text text-xl font-medium uppercase">
          Распределение очков
        </h3>
        <span className="text-site-blue text-sm font-medium">
          Нераспределённые очки: {remaining}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
        {UPGRADEABLE_STATS.map((stat) => {
          const currentValue = attributes[stat] ?? 0;
          const pendingValue = pending[stat] ?? 0;

          return (
            <div
              key={stat}
              className="flex items-center justify-between gap-2 py-1.5"
            >
              <span className="text-white text-sm font-medium flex-1 min-w-0 truncate">
                {STAT_LABELS[stat]}
              </span>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-white/70 text-sm font-mono w-8 text-right">
                  {currentValue}
                </span>
                {pendingValue > 0 && (
                  <span className="text-site-blue text-sm font-mono">
                    +{pendingValue}
                  </span>
                )}
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => handleDecrement(stat)}
                    disabled={pendingValue <= 0 || saving}
                    className="w-7 h-7 flex items-center justify-center rounded-md
                      border border-white/20 text-white/70 text-sm font-medium
                      hover:border-site-blue hover:text-site-blue
                      disabled:opacity-30 disabled:cursor-not-allowed
                      transition-colors duration-200"
                  >
                    -
                  </button>
                  <button
                    type="button"
                    onClick={() => handleIncrement(stat)}
                    disabled={remaining <= 0 || saving}
                    className="w-7 h-7 flex items-center justify-center rounded-md
                      border border-white/20 text-white/70 text-sm font-medium
                      hover:border-site-blue hover:text-site-blue
                      disabled:opacity-30 disabled:cursor-not-allowed
                      transition-colors duration-200"
                  >
                    +
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={handleSave}
          disabled={totalPending <= 0 || saving}
          className="btn-blue text-base px-8 py-2.5 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      </div>
    </div>
  );
};

export default StatDistributionPanel;
