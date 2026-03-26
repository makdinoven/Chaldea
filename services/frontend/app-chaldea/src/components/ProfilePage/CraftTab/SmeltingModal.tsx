import { useEffect, useCallback, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchSmeltInfo,
  smeltItem,
  clearSmeltInfo,
  selectSmeltInfo,
  selectSmeltInfoLoading,
  selectSmeltLoading,
  fetchCharacterProfession,
} from '../../../redux/slices/craftingSlice';
import { fetchInventory } from '../../../redux/slices/profileSlice';
import type { SmeltResult } from '../../../types/gems';

interface SmeltableItemRef {
  rowId: number;
  itemId: number;
  name: string;
  image: string | null;
  itemType: string;
  itemRarity: string;
  hasGems: boolean;
  gemCount: number;
}

interface SmeltingModalProps {
  characterId: number;
  item: SmeltableItemRef;
  onClose: () => void;
}

const SmeltingModal = ({ characterId, item, onClose }: SmeltingModalProps) => {
  const dispatch = useAppDispatch();
  const smeltInfo = useAppSelector(selectSmeltInfo);
  const infoLoading = useAppSelector(selectSmeltInfoLoading);
  const smeltLoading = useAppSelector(selectSmeltLoading);
  const [confirmStep, setConfirmStep] = useState(false);

  // Fetch smelt info on open
  useEffect(() => {
    dispatch(fetchSmeltInfo({ characterId, itemRowId: item.rowId }));
    return () => {
      dispatch(clearSmeltInfo());
    };
  }, [dispatch, characterId, item.rowId]);

  const handleSmelt = useCallback(async () => {
    if (!confirmStep) {
      setConfirmStep(true);
      return;
    }

    const result = await dispatch(smeltItem({
      characterId,
      payload: { inventory_item_id: item.rowId },
    }));

    if (result.meta.requestStatus === 'fulfilled') {
      const data = result.payload as SmeltResult;
      const materialsText = data.materials_returned
        .map((m) => `${m.name} x${m.quantity}`)
        .join(', ');
      toast.success(`Переплавка завершена! Получено: ${materialsText}`);

      if (data.xp_earned > 0) {
        toast.success(`+${data.xp_earned} XP`, { duration: 3000 });
      }
      if (data.rank_up && data.new_rank_name) {
        toast.success(`Повышение ранга: ${data.new_rank_name}!`, { duration: 5000 });
        dispatch(fetchCharacterProfession(characterId));
      }
      if (data.gems_destroyed > 0) {
        toast.error(`${data.gems_destroyed} камн. уничтожено`, { duration: 3000 });
      }

      dispatch(fetchInventory(characterId));
      onClose();
    } else {
      const err = result.payload as string | undefined;
      toast.error(err ?? 'Не удалось переплавить предмет');
      setConfirmStep(false);
    }
  }, [dispatch, characterId, item, confirmStep, onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar"
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
            <p className="text-white/60 text-sm">Переплавка</p>
          </div>
          <button
            onClick={onClose}
            className="text-white/50 hover:text-white transition-colors text-xl leading-none p-1"
          >
            &times;
          </button>
        </div>

        {infoLoading ? (
          <div className="flex items-center justify-center py-10">
            <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
          </div>
        ) : smeltInfo ? (
          <>
            {/* Materials to receive */}
            <div className="mb-4">
              <h3 className="text-white text-sm font-medium uppercase tracking-wide mb-2">
                Вы получите
              </h3>
              {smeltInfo.ingredients.length === 0 ? (
                <p className="text-white/40 text-sm">Нет материалов</p>
              ) : (
                <div className="space-y-1.5">
                  {smeltInfo.ingredients.map((ing) => (
                    <div
                      key={ing.item_id}
                      className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-white/[0.04]"
                    >
                      <div className="w-8 h-8 rounded-full overflow-hidden bg-white/[0.05] flex-shrink-0 flex items-center justify-center">
                        {ing.image ? (
                          <img src={ing.image} alt={ing.name} className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-white/30 text-sm">?</span>
                        )}
                      </div>
                      <span className="text-white text-sm flex-1 min-w-0 truncate">{ing.name}</span>
                      <span className="text-gold text-sm font-medium">x{ing.quantity}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Gem warning */}
            {smeltInfo.has_gems && (
              <div className="bg-site-red/10 border border-site-red/30 rounded-lg p-3 mb-4">
                <p className="text-site-red text-sm text-center font-medium">
                  &#9888; Камни в слотах будут уничтожены!
                </p>
                <p className="text-site-red/70 text-xs text-center mt-1">
                  {smeltInfo.gem_count} камн. будет потеряно. Извлеките их перед переплавкой.
                </p>
              </div>
            )}

            {!smeltInfo.has_recipe && (
              <div className="bg-white/[0.04] border border-white/10 rounded-lg p-2 mb-4">
                <p className="text-white/50 text-xs text-center">
                  Этот предмет не был создан по рецепту. Будет получен ювелирный лом.
                </p>
              </div>
            )}

            {/* Confirm step */}
            {confirmStep && (
              <div className="bg-gold/[0.08] border border-gold/20 rounded-lg p-3 mb-4">
                <p className="text-gold text-sm text-center font-medium">
                  Вы уверены? Предмет будет уничтожен безвозвратно.
                </p>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex flex-col sm:flex-row gap-2">
              <button
                onClick={handleSmelt}
                disabled={smeltLoading}
                className={`btn-blue flex-1 text-sm py-2.5 ${smeltLoading ? 'opacity-40 cursor-not-allowed' : ''}`}
              >
                {smeltLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Переплавка...
                  </span>
                ) : confirmStep ? (
                  'Подтвердить переплавку'
                ) : (
                  'Переплавить'
                )}
              </button>
              <button
                onClick={confirmStep ? () => setConfirmStep(false) : onClose}
                className="btn-line text-sm py-2.5 sm:w-auto"
              >
                {confirmStep ? 'Назад' : 'Закрыть'}
              </button>
            </div>
          </>
        ) : (
          <p className="text-site-red text-sm text-center py-4">
            Не удалось загрузить информацию о переплавке
          </p>
        )}
      </motion.div>
    </div>
  );
};

export default SmeltingModal;
