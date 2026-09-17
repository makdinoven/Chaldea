// FEAT-165 — refine one kind of raw material: quantity picker + preview.
import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  refineItem,
  fetchRefineInfo,
  fetchRecipes,
  fetchCharacterProfession,
  selectRefineLoading,
} from '../../../redux/slices/craftingSlice';
import { fetchInventory } from '../../../redux/slices/profileSlice';
import type { RefineSource } from '../../../types/professions';
import { RARITY_TEXT_COLORS } from '../../../constants/items';

interface RefineModalProps {
  characterId: number;
  source: RefineSource;
  doubleChancePct: number | null;
  onClose: () => void;
}

interface ItemIconProps {
  image: string | null;
  name: string;
}

const ItemIcon = ({ image, name }: ItemIconProps) => (
  <div className="w-12 h-12 sm:w-14 sm:h-14 shrink-0 rounded-full overflow-hidden bg-white/[0.05] flex items-center justify-center">
    {image ? (
      <img src={image} alt={name} className="w-full h-full object-cover" />
    ) : (
      <span className="text-white/30 text-lg">?</span>
    )}
  </div>
);

const RefineModal = ({ characterId, source, doubleChancePct, onClose }: RefineModalProps) => {
  const dispatch = useAppDispatch();
  const loading = useAppSelector(selectRefineLoading);

  const step = Math.max(1, source.source_quantity);
  const maxUsable = source.max_batches * step;
  const [quantityText, setQuantityText] = useState(String(maxUsable > 0 ? maxUsable : step));

  const quantity = Number.parseInt(quantityText, 10);
  const validNumber = Number.isFinite(quantity) && quantity > 0;
  const batches = validNumber ? Math.floor(quantity / step) : 0;
  const consumed = batches * step;
  const leftover = validNumber ? quantity - consumed : 0;
  const produced = batches * source.result_quantity;

  const validationError = useMemo(() => {
    if (!validNumber) return 'Введите количество';
    if (quantity > source.owned_quantity) return `У вас только ${source.owned_quantity} шт.`;
    if (batches === 0) return `Нужно минимум ${step} шт. для переработки`;
    return null;
  }, [validNumber, quantity, source.owned_quantity, batches, step]);

  const handleConfirm = async () => {
    if (validationError || loading) return;
    const result = await dispatch(refineItem({
      characterId,
      sourceItemId: source.source_item_id,
      quantity,
    }));

    if (refineItem.fulfilled.match(result)) {
      const data = result.payload;
      const doubled = data.doubled_batches > 0 ? ` (удвоение ×${data.doubled_batches})` : '';
      toast.success(`Получено: ${data.result_item.name} ×${data.result_quantity}${doubled}`);
      if (data.xp_earned > 0) {
        toast.success(`+${data.xp_earned} опыта профессии`, { duration: 3000 });
      }
      if (data.rank_up && data.new_rank_name) {
        toast.success(`Повышение ранга: ${data.new_rank_name}!`, { duration: 5000 });
      }
      if (data.auto_learned_recipes?.length > 0) {
        const names = data.auto_learned_recipes.map((r) => r.name).join(', ');
        toast.success(`Новые рецепты изучены: ${names}`, { duration: 4000 });
      }
      dispatch(fetchRefineInfo(characterId));
      dispatch(fetchCharacterProfession(characterId));
      dispatch(fetchRecipes({ characterId }));
      dispatch(fetchInventory(characterId));
      onClose();
    } else {
      toast.error(result.payload ?? 'Не удалось переработать');
    }
  };

  return createPortal(
    <div className="modal-overlay" onClick={loading ? undefined : onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick max-w-[420px] w-full mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="gold-text text-lg sm:text-xl font-medium uppercase mb-4">Переработка</h2>

        {/* Source → result preview */}
        <div className="flex items-center justify-between gap-2 mb-4">
          <div className="flex flex-col items-center gap-1 flex-1 min-w-0 text-center">
            <ItemIcon image={source.image} name={source.name} />
            <span className={`text-xs leading-tight break-words ${RARITY_TEXT_COLORS[source.item_rarity] ?? 'text-white'}`}>
              {source.name}
            </span>
            <span className="text-[11px] text-white/50">×{step}</span>
          </div>
          <span className="text-gold text-xl shrink-0">→</span>
          <div className="flex flex-col items-center gap-1 flex-1 min-w-0 text-center">
            <ItemIcon image={source.result_item.image} name={source.result_item.name} />
            <span className={`text-xs leading-tight break-words ${RARITY_TEXT_COLORS[source.result_item.item_rarity] ?? 'text-white'}`}>
              {source.result_item.name}
            </span>
            <span className="text-[11px] text-white/50">×{source.result_quantity}</span>
          </div>
        </div>

        {/* Quantity */}
        <label className="block text-white/70 text-sm mb-1" htmlFor="refine-quantity">
          Количество сырья (есть {source.owned_quantity})
        </label>
        <div className="flex items-end gap-3 mb-3">
          <input
            id="refine-quantity"
            type="number"
            inputMode="numeric"
            min={step}
            max={source.owned_quantity}
            step={step}
            value={quantityText}
            onChange={(e) => setQuantityText(e.target.value)}
            className="input-underline flex-1 min-w-0"
          />
          <button
            type="button"
            onClick={() => setQuantityText(String(maxUsable > 0 ? maxUsable : step))}
            className="site-link text-sm shrink-0 pb-2"
          >
            Макс.
          </button>
        </div>

        {/* Summary */}
        <div className="space-y-1 mb-4 text-sm">
          {validationError ? (
            <p className="text-site-red">{validationError}</p>
          ) : (
            <>
              <p className="text-white/80">
                Будет израсходовано {consumed}, получите {produced}
                {doubleChancePct ? ` (шанс удвоения ${doubleChancePct}%)` : ''}
              </p>
              {leftover > 0 && (
                <p className="text-white/50 text-xs">
                  {leftover} шт. не кратно {step} и останется в инвентаре
                </p>
              )}
              <p className="text-white/50 text-xs">
                Базовый опыт профессии: +{batches * source.xp_per_batch} (без учёта баффов)
              </p>
            </>
          )}
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            type="button"
            onClick={handleConfirm}
            disabled={Boolean(validationError) || loading}
            className="btn-blue flex-1 text-base py-2.5 px-4 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Переработка...
              </span>
            ) : (
              'Переработать'
            )}
          </button>
          <button type="button" onClick={onClose} disabled={loading} className="btn-line sm:flex-1">
            Отмена
          </button>
        </div>
      </motion.div>
    </div>,
    document.body,
  );
};

export default RefineModal;
