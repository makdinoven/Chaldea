// FEAT-151 — recipe card per mock 1011-1037: round result icon,
// name + qty, rarity label, description,
// «Материалы» have/need list and the craft button (disabled style when short).
// FEAT-166: flat ProfileCard (dimmed when it cannot be crafted) + 48px gold frame.
import type { Recipe } from '../../../types/professions';
import { MotionProfileCard } from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';

const RARITY_LABEL: Record<string, string> = {
  common: 'Обычный',
  rare: 'Редкий',
  epic: 'Эпический',
  mythical: 'Мифический',
  legendary: 'Легендарный',
  divine: 'Божественный',
  demonic: 'Демонический',
};

const RARITY_TEXT: Record<string, string> = {
  common: 'text-white/60',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  mythical: 'text-rarity-mythical',
  legendary: 'text-rarity-legendary',
  divine: 'text-rarity-legendary',
  demonic: 'text-rarity-mythical',
};

interface RecipeCardProps {
  recipe: Recipe;
  onCraft: (recipe: Recipe) => void;
}

const RecipeCard = ({ recipe, onCraft }: RecipeCardProps) => {
  const rarityTextClass = RARITY_TEXT[recipe.rarity] ?? 'text-white/60';
  const rarityLabel = RARITY_LABEL[recipe.rarity] ?? recipe.rarity;

  return (
    <MotionProfileCard
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
      locked={!recipe.can_craft}
      className="flex flex-col gap-3 p-3.5 min-w-0"
    >
      {/* Header: 48px round icon + name/qty/rarity */}
      <div className="flex items-start gap-3">
        <GoldIconFrame
          size={48}
          shape="circle"
          src={recipe.result_item?.image}
          alt={recipe.result_item?.name ?? recipe.name}
          fallback={<span className="text-white/30 text-base">?</span>}
        />
        <div className="flex flex-col gap-1 flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-white text-[15px] font-medium leading-tight truncate">
              {recipe.name}
            </span>
            {recipe.result_quantity > 1 && (
              <span className="font-mono tabular-nums text-[11px] text-white/50 shrink-0">
                x{recipe.result_quantity}
              </span>
            )}
          </div>
          <span className={`text-[11px] font-medium uppercase tracking-[0.04em] ${rarityTextClass}`}>
            {rarityLabel}
          </span>
        </div>
      </div>

      {/* Description */}
      {recipe.description && (
        <p className="text-xs leading-relaxed text-white/50 line-clamp-2">
          {recipe.description}
        </p>
      )}

      {/* Ingredients: have/need */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] uppercase tracking-[0.08em] text-white/40">
          Материалы
        </span>
        {(recipe.ingredients ?? []).map((ing) => {
          const hasEnough = ing.available >= ing.quantity;
          return (
            <div key={ing.item_id} className="flex items-center gap-2.5">
              <span className="w-[26px] h-[26px] shrink-0 flex items-center justify-center rounded-[7px] bg-white/5 border border-white/10 overflow-hidden">
                {ing.item_image ? (
                  <img
                    src={ing.item_image}
                    alt={ing.item_name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="text-white/20 text-[10px]">?</span>
                )}
              </span>
              <span className="flex-1 text-[12.5px] text-white/70 min-w-0 truncate">
                {ing.item_name}
              </span>
              <span
                className={`font-mono tabular-nums text-[12.5px] font-medium shrink-0 ${
                  hasEnough ? 'text-stat-energy' : 'text-site-red'
                }`}
              >
                {ing.available}/{ing.quantity}
              </span>
            </div>
          );
        })}
      </div>

      {/* Craft button */}
      <button
        type="button"
        onClick={() => onCraft(recipe)}
        disabled={!recipe.can_craft}
        className={`mt-auto w-full py-2.5 rounded-[10px] text-xs font-medium uppercase tracking-[0.04em] transition-colors duration-200 ease-site ${
          recipe.can_craft
            ? 'bg-site-blue/20 text-site-blue hover:bg-site-blue/30 cursor-pointer'
            : 'bg-white/5 text-white/25 border border-white/10 cursor-not-allowed'
        }`}
      >
        Создать
      </button>
    </MotionProfileCard>
  );
};

export default RecipeCard;
