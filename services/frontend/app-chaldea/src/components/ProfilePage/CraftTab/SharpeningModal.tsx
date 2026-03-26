import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchSharpenInfo,
  sharpenItem,
  clearSharpenInfo,
  selectSharpenInfo,
  selectSharpenInfoLoading,
  selectSharpenLoading,
  fetchCharacterProfession,
} from '../../../redux/slices/craftingSlice';
import { fetchInventory, fetchEquipment } from '../../../redux/slices/profileSlice';
import type { SharpenStatInfo, SharpenWhetstoneInfo } from '../../../types/professions';

const MAX_POINTS = 15;

interface SharpenableItemRef {
  rowId: number;
  itemId: number;
  name: string;
  image: string | null;
  itemType: string;
  itemRarity: string;
  pointsSpent: number;
  source: 'inventory' | 'equipment';
}

interface SharpeningModalProps {
  characterId: number;
  item: SharpenableItemRef;
  onClose: () => void;
}

const SharpeningModal = ({ characterId, item, onClose }: SharpeningModalProps) => {
  const dispatch = useAppDispatch();
  const sharpenInfo = useAppSelector(selectSharpenInfo);
  const infoLoading = useAppSelector(selectSharpenInfoLoading);
  const sharpenLoading = useAppSelector(selectSharpenLoading);

  const [selectedStat, setSelectedStat] = useState<string | null>(null);
  const [selectedWhetstone, setSelectedWhetstone] = useState<number | null>(null);
  const [lastResult, setLastResult] = useState<{
    success: boolean;
    statName: string;
    oldValue: number;
    newValue: number;
    xpEarned: number;
  } | null>(null);

  // Load sharpen info on open
  useEffect(() => {
    dispatch(fetchSharpenInfo({
      characterId,
      itemRowId: item.rowId,
      source: item.source,
    }));
    return () => {
      dispatch(clearSharpenInfo());
    };
  }, [dispatch, characterId, item.rowId, item.source]);

  // Auto-select first available whetstone
  useEffect(() => {
    if (sharpenInfo?.whetstones.length && selectedWhetstone === null) {
      setSelectedWhetstone(sharpenInfo.whetstones[0].inventory_item_id);
    }
  }, [sharpenInfo, selectedWhetstone]);

  const handleSharpen = useCallback(async () => {
    if (!selectedStat || !selectedWhetstone) return;

    const result = await dispatch(sharpenItem({
      characterId,
      payload: {
        inventory_item_id: item.rowId,
        whetstone_item_id: selectedWhetstone,
        stat_field: selectedStat,
        source: item.source,
      },
    }));

    if (result.meta.requestStatus === 'fulfilled') {
      const data = result.payload as {
        success: boolean;
        stat_display_name: string;
        old_value: number;
        new_value: number;
        xp_earned: number;
        rank_up: boolean;
        new_rank_name: string | null;
      };

      setLastResult({
        success: data.success,
        statName: data.stat_display_name,
        oldValue: data.old_value,
        newValue: data.new_value,
        xpEarned: data.xp_earned,
      });

      if (data.success) {
        toast.success(`Заточка успешна! ${data.stat_display_name} +1`);
      } else {
        toast.error('Неудача! Камень потрачен');
      }

      if (data.rank_up && data.new_rank_name) {
        toast.success(`Повышение ранга: ${data.new_rank_name}!`, { duration: 5000 });
        dispatch(fetchCharacterProfession(characterId));
      }

      // Refresh sharpen info and inventory
      dispatch(fetchSharpenInfo({
        characterId,
        itemRowId: item.rowId,
        source: item.source,
      }));
      dispatch(fetchInventory(characterId));
      if (item.source === 'equipment') {
        dispatch(fetchEquipment(characterId));
      }

      // Reset whetstone selection if it might have been consumed
      setSelectedWhetstone(null);
    } else {
      const err = result.payload as string | undefined;
      toast.error(err ?? 'Не удалось заточить предмет');
    }
  }, [dispatch, characterId, item, selectedStat, selectedWhetstone]);

  const pointsSpent = sharpenInfo?.points_spent ?? item.pointsSpent;
  const pointsRemaining = sharpenInfo ? sharpenInfo.points_remaining : (MAX_POINTS - item.pointsSpent);

  const selectedStatInfo = sharpenInfo?.stats.find((s) => s.field === selectedStat);
  const selectedWhInfo = sharpenInfo?.whetstones.find((w) => w.inventory_item_id === selectedWhetstone);

  const canSharpen = Boolean(
    selectedStat &&
    selectedWhetstone &&
    selectedStatInfo?.can_sharpen &&
    !sharpenLoading &&
    !infoLoading,
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-14 h-14 rounded-full overflow-hidden bg-white/[0.05] flex-shrink-0 flex items-center justify-center">
            {item.image ? (
              <img src={item.image} alt={item.name} className="w-full h-full object-cover" />
            ) : (
              <span className="text-white/30 text-xl">?</span>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="gold-text text-xl font-medium uppercase truncate">{item.name}</h2>
            <p className="text-white/60 text-sm">
              {pointsSpent}/{MAX_POINTS} поинтов потрачено
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-white/50 hover:text-white transition-colors text-xl leading-none p-1"
          >
            &times;
          </button>
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 bg-white/[0.08] rounded-full mb-5 overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-gold-dark to-gold-light"
            initial={{ width: 0 }}
            animate={{ width: `${(pointsSpent / MAX_POINTS) * 100}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          />
        </div>

        {infoLoading ? (
          <div className="flex items-center justify-center py-10">
            <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
          </div>
        ) : sharpenInfo ? (
          <>
            {/* Stats list */}
            <div className="space-y-1 mb-5">
              <h3 className="text-white text-sm font-medium uppercase tracking-wide mb-2">Статы для заточки</h3>
              <div className="space-y-1 max-h-[240px] overflow-y-auto gold-scrollbar pr-1">
                {sharpenInfo.stats
                  .filter((stat) => stat.is_existing || stat.sharpened_count > 0)
                  .map((stat) => (
                    <StatRow
                      key={stat.field}
                      stat={stat}
                      isSelected={selectedStat === stat.field}
                      onSelect={() => setSelectedStat(stat.field)}
                    />
                  ))}

                {/* Non-existing stats (new stats that can be added) */}
                {sharpenInfo.stats.some((s) => !s.is_existing && s.sharpened_count === 0) && (
                  <>
                    <div className="border-t border-white/[0.06] my-2 pt-2">
                      <span className="text-white/40 text-xs uppercase">Новые статы (2 поинта)</span>
                    </div>
                    {sharpenInfo.stats
                      .filter((stat) => !stat.is_existing && stat.sharpened_count === 0)
                      .map((stat) => (
                        <StatRow
                          key={stat.field}
                          stat={stat}
                          isSelected={selectedStat === stat.field}
                          onSelect={() => setSelectedStat(stat.field)}
                        />
                      ))}
                  </>
                )}
              </div>
            </div>

            {/* Whetstone selector */}
            <div className="mb-5">
              <h3 className="text-white text-sm font-medium uppercase tracking-wide mb-2">Точильный камень</h3>
              {sharpenInfo.whetstones.length === 0 ? (
                <p className="text-site-red text-sm">Нет точильных камней в инвентаре</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {sharpenInfo.whetstones.map((ws) => (
                    <WhetstoneButton
                      key={ws.inventory_item_id}
                      whetstone={ws}
                      isSelected={selectedWhetstone === ws.inventory_item_id}
                      onSelect={() => setSelectedWhetstone(ws.inventory_item_id)}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Result flash */}
            <AnimatePresence>
              {lastResult && (
                <motion.div
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -5 }}
                  className={`text-center py-2 px-3 rounded-card mb-4 text-sm font-medium ${
                    lastResult.success
                      ? 'bg-green-900/30 text-green-300 border border-green-500/30'
                      : 'bg-red-900/30 text-site-red border border-site-red/30'
                  }`}
                >
                  {lastResult.success
                    ? `${lastResult.statName}: +${lastResult.oldValue} → +${lastResult.newValue} | +${lastResult.xpEarned} XP`
                    : `Неудача! Камень потрачен | +${lastResult.xpEarned} XP`}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Sharpen button */}
            <div className="flex flex-col sm:flex-row gap-2">
              <button
                onClick={handleSharpen}
                disabled={!canSharpen}
                className={`
                  btn-blue flex-1 text-sm py-2.5
                  ${!canSharpen ? 'opacity-40 cursor-not-allowed' : ''}
                `}
              >
                {sharpenLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Заточка...
                  </span>
                ) : selectedStatInfo ? (
                  `Заточить ${selectedStatInfo.name}${selectedWhInfo ? ` (${selectedWhInfo.success_chance}%)` : ''}`
                ) : (
                  'Выберите стат'
                )}
              </button>
              <button onClick={onClose} className="btn-line text-sm py-2.5 sm:w-auto">
                Закрыть
              </button>
            </div>

            {pointsRemaining <= 0 && (
              <p className="text-site-red text-xs text-center mt-3">
                Бюджет заточки исчерпан ({MAX_POINTS}/{MAX_POINTS})
              </p>
            )}
          </>
        ) : (
          <p className="text-site-red text-sm text-center py-4">
            Не удалось загрузить информацию о заточке
          </p>
        )}
      </motion.div>
    </div>
  );
};

/* ── Sub-components ── */

interface StatRowProps {
  stat: SharpenStatInfo;
  isSelected: boolean;
  onSelect: () => void;
}

const StatRow = ({ stat, isSelected, onSelect }: StatRowProps) => {
  const isMaxed = stat.sharpened_count >= stat.max;

  return (
    <button
      onClick={onSelect}
      disabled={!stat.can_sharpen}
      className={`
        w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-left
        transition-all duration-200 ease-site
        ${isSelected ? 'bg-gold/[0.12] border border-gold/30' : 'bg-white/[0.03] border border-transparent hover:bg-white/[0.06]'}
        ${!stat.can_sharpen ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
      `}
    >
      <span className="text-white text-sm flex-1 min-w-0 truncate">{stat.name}</span>
      <span className={`text-xs font-medium ${isMaxed ? 'text-site-red' : 'text-gold'}`}>
        +{stat.sharpened_count}/{stat.max}
      </span>
      <span className={`text-[10px] px-1.5 py-0.5 rounded ${stat.is_existing ? 'bg-white/[0.08] text-white/60' : 'bg-site-blue/20 text-site-blue'}`}>
        {stat.point_cost}п
      </span>
    </button>
  );
};

interface WhetstoneButtonProps {
  whetstone: SharpenWhetstoneInfo;
  isSelected: boolean;
  onSelect: () => void;
}

const WhetstoneButton = ({ whetstone, isSelected, onSelect }: WhetstoneButtonProps) => {
  return (
    <button
      onClick={onSelect}
      className={`
        flex items-center gap-2 px-3 py-2 rounded-card text-sm
        transition-all duration-200 ease-site cursor-pointer
        ${isSelected
          ? 'bg-gold/[0.12] border border-gold/30 text-gold'
          : 'bg-white/[0.04] border border-white/10 text-white hover:bg-white/[0.08]'
        }
      `}
    >
      <span className="truncate max-w-[140px]">{whetstone.name}</span>
      <span className="text-xs text-white/50">x{whetstone.quantity}</span>
      <span className={`text-xs font-medium ${isSelected ? 'text-gold-light' : 'text-site-blue'}`}>
        {whetstone.success_chance}%
      </span>
    </button>
  );
};

export default SharpeningModal;
