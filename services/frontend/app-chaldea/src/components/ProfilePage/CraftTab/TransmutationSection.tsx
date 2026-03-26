import { useEffect, useCallback } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchTransmuteInfo,
  transmuteItem,
  fetchCharacterProfession,
  selectTransmuteInfo,
  selectTransmuteInfoLoading,
  selectTransmuteLoading,
  selectTransmuteError,
} from '../../../redux/slices/craftingSlice';
import type { TransmuteItemInfo, TransmuteResult } from '../../../types/professions';

interface TransmutationSectionProps {
  characterId: number;
}

const RARITY_LABELS: Record<string, string> = {
  common: 'Обычный',
  rare: 'Редкий',
  epic: 'Эпический',
  legendary: 'Легендарный',
  mythical: 'Мифический',
};

const rarityTextColor = (rarity: string) => {
  switch (rarity) {
    case 'common': return 'text-rarity-common';
    case 'rare': return 'text-rarity-rare';
    case 'epic': return 'text-rarity-epic';
    case 'legendary': return 'text-rarity-legendary';
    case 'mythical': return 'text-rarity-mythical';
    default: return 'text-white';
  }
};

const TransmutationSection = ({ characterId }: TransmutationSectionProps) => {
  const dispatch = useAppDispatch();

  const transmuteInfo = useAppSelector(selectTransmuteInfo);
  const transmuteInfoLoading = useAppSelector(selectTransmuteInfoLoading);
  const transmuteLoading = useAppSelector(selectTransmuteLoading);
  const transmuteError = useAppSelector(selectTransmuteError);

  useEffect(() => {
    dispatch(fetchTransmuteInfo(characterId));
  }, [dispatch, characterId]);

  useEffect(() => {
    if (transmuteError) toast.error(transmuteError);
  }, [transmuteError]);

  const handleTransmute = useCallback(
    async (item: TransmuteItemInfo) => {
      const result = await dispatch(
        transmuteItem({ characterId, inventoryItemId: item.inventory_item_id }),
      );

      if (result.meta.requestStatus === 'fulfilled') {
        const payload = result.payload as TransmuteResult;

        toast.success(
          `Трансмутация успешна! Получен: ${payload.result_item_name}`,
          { duration: 4000 },
        );

        if (payload.xp_earned > 0) {
          toast.success(`+${payload.xp_earned} XP`, { duration: 3000 });
        }

        if (payload.rank_up && payload.new_rank_name) {
          toast.success(`Повышение ранга: ${payload.new_rank_name}!`, { duration: 5000 });
        }

        // Refresh data
        dispatch(fetchTransmuteInfo(characterId));
        dispatch(fetchCharacterProfession(characterId));
      } else {
        const err = result.payload as string | undefined;
        toast.error(err ?? 'Не удалось трансмутировать ресурс');
      }
    },
    [dispatch, characterId],
  );

  const items = transmuteInfo?.items ?? [];

  return (
    <div className="space-y-3">
      <div>
        <h3 className="gold-text text-lg font-medium uppercase">Трансмутация</h3>
        <p className="text-white/60 text-sm mt-1">
          Преобразуйте 5 ресурсов одной редкости в 1 ресурс следующей редкости.
        </p>
      </div>

      {transmuteInfoLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-white/40 text-sm py-4 text-center">
          Нет ресурсов для трансмутации
        </p>
      ) : (
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3"
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.04 } } }}
        >
          {items.map((item) => (
            <motion.div
              key={item.inventory_item_id}
              variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}
              className="flex flex-col gap-2 p-3 rounded-card bg-white/[0.04] border border-white/10"
            >
              {/* Item info row */}
              <div className="flex items-center gap-2">
                {/* Source item */}
                <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
                  <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full overflow-hidden bg-white/[0.05] flex items-center justify-center flex-shrink-0">
                    {item.image ? (
                      <img src={item.image} alt={item.name} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-white/30 text-xl">?</span>
                    )}
                  </div>
                  <span className="text-white text-xs text-center leading-tight line-clamp-2">
                    {item.name}
                  </span>
                  <span className="text-white/50 text-xs">x{item.quantity}</span>
                  <span className={`text-xs font-medium ${rarityTextColor(item.item_rarity)}`}>
                    {RARITY_LABELS[item.item_rarity] ?? item.item_rarity}
                  </span>
                </div>

                {/* Arrow with conversion info */}
                <div className="flex flex-col items-center gap-0.5 flex-shrink-0">
                  <span className="text-white/50 text-[10px]">{item.required_quantity}x</span>
                  <span className="text-gold text-lg">&rarr;</span>
                  <span className="text-white/50 text-[10px]">1x</span>
                </div>

                {/* Result */}
                <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
                  <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full overflow-hidden bg-white/[0.05] flex items-center justify-center flex-shrink-0">
                    <span className={`text-xl ${rarityTextColor(item.next_rarity)}`}>&#9733;</span>
                  </div>
                  <span className={`text-xs font-medium text-center ${rarityTextColor(item.next_rarity)}`}>
                    {RARITY_LABELS[item.next_rarity] ?? item.next_rarity}
                  </span>
                </div>
              </div>

              {/* Button */}
              <div className="flex items-center justify-between mt-1">
                <span className="text-white/60 text-xs">
                  {item.can_transmute
                    ? 'Готово к трансмутации'
                    : `Нужно ${item.required_quantity} шт.`}
                </span>
                <button
                  onClick={() => handleTransmute(item)}
                  disabled={!item.can_transmute || transmuteLoading}
                  className="btn-blue text-xs px-3 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {transmuteLoading ? 'Трансмутация...' : 'Трансмутировать'}
                </button>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
};

export default TransmutationSection;
