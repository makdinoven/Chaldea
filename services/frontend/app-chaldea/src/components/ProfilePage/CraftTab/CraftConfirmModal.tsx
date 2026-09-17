// FEAT-166: craft confirmation on the shared portaled ModalShell.
import { Hammer } from 'lucide-react';
import type { Recipe } from '../../../types/professions';
import ModalShell from '../shared/ModalShell';
import ProfileCard from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';
import LoadingState from '../shared/LoadingState';

interface CraftConfirmModalProps {
  recipe: Recipe;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

const CraftConfirmModal = ({ recipe, onConfirm, onCancel, loading }: CraftConfirmModalProps) => {
  return (
    <ModalShell
      open
      onClose={onCancel}
      title="Подтверждение крафта"
      icon={<Hammer size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      size="sm"
      footer={
        <>
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="btn-line w-full sm:w-auto"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="btn-blue w-full sm:w-auto disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <LoadingState size="xs" />
                Создание...
              </span>
            ) : (
              'Подтвердить'
            )}
          </button>
        </>
      }
    >
      {/* Result item */}
      <ProfileCard className="flex items-center gap-3 mb-4 p-3 min-w-0">
        <GoldIconFrame
          size={48}
          src={recipe.result_item?.image}
          alt={recipe.result_item?.name ?? recipe.name}
          fallback={<span className="text-white/30 text-lg">?</span>}
        />
        <div className="min-w-0">
          <p className="text-white font-medium break-words">{recipe.result_item?.name ?? recipe.name}</p>
          {recipe.result_quantity > 1 && (
            <p className="text-white/50 text-sm">x{recipe.result_quantity}</p>
          )}
          <p className="text-white/30 text-xs capitalize">{recipe.result_item?.item_rarity ?? recipe.rarity}</p>
        </div>
      </ProfileCard>

      {/* Consumed materials */}
      <div>
        <p className="text-white/70 text-sm mb-2">Будет потрачено:</p>
        <div className="space-y-1.5">
          {(recipe.ingredients ?? []).map((ing) => (
            <div
              key={ing.item_id}
              className="flex items-center justify-between gap-3 text-sm px-2 py-1 rounded bg-white/[0.03]"
            >
              <div className="flex items-center gap-2 min-w-0">
                {ing.item_image ? (
                  <img
                    src={ing.item_image}
                    alt={ing.item_name}
                    className="w-6 h-6 rounded object-cover shrink-0"
                  />
                ) : (
                  <div className="w-6 h-6 rounded bg-white/10 shrink-0" />
                )}
                <span className="text-white break-words min-w-0">{ing.item_name}</span>
              </div>
              <span
                className={`shrink-0 ${ing.available >= ing.quantity ? 'text-stat-energy' : 'text-site-red'}`}
              >
                {ing.quantity} шт.
              </span>
            </div>
          ))}
        </div>
      </div>
    </ModalShell>
  );
};

export default CraftConfirmModal;
