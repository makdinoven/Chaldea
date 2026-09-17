// FEAT-166: shared portaled ModalShell; opened from the character tab's item
// context menu (props/exports unchanged).
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
  selectSharpenError,
} from '../../../redux/slices/craftingSlice';
import { fetchInventory, fetchEquipment } from '../../../redux/slices/profileSlice';
import type { SharpenStatInfo, SharpenWhetstoneInfo, SharpenResult } from '../../../types/professions';
import {
  MAX_ENHANCEMENT_POINTS as MAX_POINTS,
  SHARPEN_GROUP_BY_ITEM_TYPE,
  WHETSTONE_GROUP_LABELS,
  WHETSTONE_GROUP_TARGETS,
} from '../../../constants/professions';
import ModalShell from '../shared/ModalShell';
import GoldIconFrame from '../shared/GoldIconFrame';
import SectionHeader from '../shared/SectionHeader';
import ProgressBar from '../shared/ProgressBar';
import LoadingState from '../shared/LoadingState';
import ErrorState from '../shared/ErrorState';

export interface SharpenableItemRef {
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
  const sharpenError = useAppSelector(selectSharpenError);

  const [selectedStat, setSelectedStat] = useState<string | null>(null);
  const [selectedWhetstone, setSelectedWhetstone] = useState<number | null>(null);
  const [lastResult, setLastResult] = useState<{
    success: boolean;
    statName: string;
    oldValue: number;
    newValue: number;
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
      const data = result.payload as SharpenResult;

      setLastResult({
        success: data.success,
        statName: data.stat_display_name,
        oldValue: data.old_value,
        newValue: data.new_value,
      });

      if (data.success) {
        toast.success(`Заточка успешна! ${data.stat_display_name} +1`);
      } else {
        toast.error('Неудача! Камень потрачен');
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

  const group = sharpenInfo?.sharpen_group ?? SHARPEN_GROUP_BY_ITEM_TYPE[item.itemType];
  const stoneLabel = group ? WHETSTONE_GROUP_LABELS[group] : 'Камень заточки';
  const stoneTargets = group ? WHETSTONE_GROUP_TARGETS[group] : '';

  const canSharpen = Boolean(
    selectedStat &&
    selectedWhetstone &&
    selectedStatInfo?.can_sharpen &&
    !sharpenLoading &&
    !infoLoading,
  );

  return (
    <ModalShell
      open
      onClose={onClose}
      title={item.name}
      size="md"
      footer={!infoLoading && sharpenInfo ? (
        <>
          <button type="button" onClick={onClose} className="btn-line w-full sm:w-auto">
            Закрыть
          </button>
          <button
            type="button"
            onClick={handleSharpen}
            disabled={!canSharpen}
            className={`btn-blue w-full sm:w-auto ${!canSharpen ? 'opacity-40 cursor-not-allowed' : ''}`}
          >
            {sharpenLoading ? (
              <span className="flex items-center justify-center gap-2">
                <LoadingState size="xs" />
                Заточка...
              </span>
            ) : selectedStatInfo ? (
              `Заточить ${selectedStatInfo.name}${selectedWhInfo ? ` (${selectedWhInfo.success_chance}%)` : ''}`
            ) : (
              'Выберите стат'
            )}
          </button>
        </>
      ) : undefined}
    >
      {/* Item identity + sharpening budget */}
      <div className="flex items-center gap-3 mb-4 min-w-0">
        <GoldIconFrame
          size={56}
          shape="circle"
          src={item.image}
          alt={item.name}
          fallback={<span className="text-white/30 text-xl">?</span>}
        />
        <div className="flex-1 min-w-0">
          <p className="text-white/60 text-sm">
            {pointsSpent}/{MAX_POINTS} поинтов потрачено
          </p>
          <p className="text-white/50 text-xs break-words">
            Нужен: <span className="text-gold">{stoneLabel}</span>
            {stoneTargets && ` (${stoneTargets})`}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <ProgressBar value={pointsSpent} max={MAX_POINTS} variant="gold" className="mb-5" />

      {infoLoading ? (
        <LoadingState size="sm" className="!py-10" />
      ) : sharpenInfo ? (
        <>
          {/* Stats list */}
          <div className="space-y-1 mb-5">
            <SectionHeader title="Статы для заточки" className="mb-2" />
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
                    <span className="text-white/40 text-xs uppercase">Новые характеристики (1 очко)</span>
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
            <SectionHeader title={stoneLabel} className="mb-2" />
            {sharpenInfo.whetstones.length === 0 ? (
              <p className="text-site-red text-sm">Нет подходящих камней. Нужен «{stoneLabel}»</p>
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
                className={`text-center py-2 px-3 rounded-card mb-4 text-sm font-medium border ${
                  lastResult.success
                    ? 'bg-stat-energy/10 text-stat-energy border-stat-energy/30'
                    : 'bg-site-red/10 text-site-red border-site-red/30'
                }`}
              >
                {lastResult.success
                  ? `${lastResult.statName}: +${lastResult.oldValue} → +${lastResult.newValue}`
                  : 'Неудача! Камень потрачен'}
              </motion.div>
            )}
          </AnimatePresence>

          {pointsRemaining <= 0 && (
            <p className="text-site-red text-xs text-center">
              Бюджет заточки исчерпан ({MAX_POINTS}/{MAX_POINTS})
            </p>
          )}
        </>
      ) : (
        <ErrorState
          message={sharpenError ?? 'Не удалось загрузить информацию о заточке'}
          className="!py-6"
        />
      )}
    </ModalShell>
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
      type="button"
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
      type="button"
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
      <span className="truncate max-w-[120px] sm:max-w-[160px]">{whetstone.name}</span>
      <span className="text-xs text-white/50">x{whetstone.quantity}</span>
      <span className={`text-xs font-medium ${isSelected ? 'text-gold-light' : 'text-site-blue'}`}>
        {whetstone.success_chance}%
      </span>
    </button>
  );
};

export default SharpeningModal;
