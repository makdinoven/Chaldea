import { motion, AnimatePresence } from 'motion/react';
import type { Recipe } from '../../../types/professions';

interface CraftConfirmModalProps {
  recipe: Recipe;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

const CraftConfirmModal = ({ recipe, onConfirm, onCancel, loading }: CraftConfirmModalProps) => {
  const isBlueprint = recipe.source === 'blueprint';

  return (
    <AnimatePresence>
      <div className="modal-overlay" onClick={onCancel}>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="modal-content gold-outline gold-outline-thick max-w-md w-full mx-4"
          onClick={(e) => e.stopPropagation()}
        >
          <h2 className="gold-text text-xl font-medium uppercase mb-4">
            Подтверждение крафта
          </h2>

          {/* Result item */}
          <div className="flex items-center gap-3 mb-4 p-3 rounded-card bg-white/[0.05]">
            {recipe.result_item?.image ? (
              <img
                src={recipe.result_item.image}
                alt={recipe.result_item?.name ?? recipe.name}
                className="w-12 h-12 rounded-lg object-cover"
              />
            ) : (
              <div className="w-12 h-12 rounded-lg bg-white/10 flex items-center justify-center">
                <span className="text-white/30 text-lg">?</span>
              </div>
            )}
            <div>
              <p className="text-white font-medium">{recipe.result_item?.name ?? recipe.name}</p>
              {recipe.result_quantity > 1 && (
                <p className="text-white/50 text-sm">x{recipe.result_quantity}</p>
              )}
              <p className="text-white/30 text-xs capitalize">{recipe.result_item?.item_rarity ?? recipe.rarity}</p>
            </div>
          </div>

          {/* Consumed materials */}
          <div className="mb-4">
            <p className="text-white/70 text-sm mb-2">Будет потрачено:</p>
            <div className="space-y-1.5">
              {(recipe.ingredients ?? []).map((ing) => (
                <div
                  key={ing.item_id}
                  className="flex items-center justify-between text-sm px-2 py-1 rounded bg-white/[0.03]"
                >
                  <div className="flex items-center gap-2">
                    {ing.item_image ? (
                      <img
                        src={ing.item_image}
                        alt={ing.item_name}
                        className="w-6 h-6 rounded object-cover"
                      />
                    ) : (
                      <div className="w-6 h-6 rounded bg-white/10" />
                    )}
                    <span className="text-white">{ing.item_name}</span>
                  </div>
                  <span className={ing.available >= ing.quantity ? 'text-green-400' : 'text-site-red'}>
                    {ing.quantity} шт.
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Blueprint warning */}
          {isBlueprint && (
            <div className="mb-4 p-2.5 rounded-lg bg-site-red/10 border border-site-red/30">
              <p className="text-site-red text-sm">
                Чертёж будет использован и исчезнет из инвентаря.
              </p>
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-3">
            <button
              onClick={onConfirm}
              disabled={loading}
              className="btn-blue flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Создание...
                </span>
              ) : (
                'Подтвердить'
              )}
            </button>
            <button
              onClick={onCancel}
              disabled={loading}
              className="btn-line flex-1"
            >
              Отмена
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default CraftConfirmModal;
