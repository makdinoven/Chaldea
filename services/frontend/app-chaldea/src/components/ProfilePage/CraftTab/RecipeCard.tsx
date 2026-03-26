import { motion } from 'motion/react';
import type { Recipe } from '../../../types/professions';

const RARITY_BORDER: Record<string, string> = {
  common: 'border-white/10',
  rare: 'border-site-blue/40',
  epic: 'border-[#B875BD]/40',
  mythical: 'border-site-red/40',
  legendary: 'border-gold/40',
  divine: 'border-[#FFD700]/60',
  demonic: 'border-[#8B0000]/50',
};

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
  rare: 'text-site-blue',
  epic: 'text-[#B875BD]',
  mythical: 'text-site-red',
  legendary: 'text-gold',
  divine: 'text-[#FFD700]',
  demonic: 'text-[#8B0000]',
};

interface RecipeCardProps {
  recipe: Recipe;
  onCraft: (recipe: Recipe) => void;
}

const RecipeCard = ({ recipe, onCraft }: RecipeCardProps) => {
  const borderClass = RARITY_BORDER[recipe.rarity] ?? 'border-white/10';
  const rarityTextClass = RARITY_TEXT[recipe.rarity] ?? 'text-white/60';
  const rarityLabel = RARITY_LABEL[recipe.rarity] ?? recipe.rarity;

  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
      className={`rounded-card p-3 sm:p-4 bg-black/60 border ${borderClass} flex flex-col gap-2.5 transition-all duration-200 hover:bg-black/70`}
    >
      {/* Header: result item + source badge */}
      <div className="flex items-start gap-3">
        {recipe.result_item?.image ? (
          <img
            src={recipe.result_item.image}
            alt={recipe.result_item?.name ?? recipe.name}
            className="w-11 h-11 sm:w-12 sm:h-12 rounded-lg object-cover shrink-0"
          />
        ) : (
          <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-lg bg-white/10 flex items-center justify-center shrink-0">
            <span className="text-white/30 text-base">?</span>
          </div>
        )}
        <div className="flex-1 min-w-0">
          <h4 className="text-white font-medium text-sm sm:text-base leading-tight truncate">
            {recipe.name}
          </h4>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className={`text-[10px] sm:text-xs ${rarityTextClass}`}>
              {rarityLabel}
            </span>
            {recipe.result_quantity > 1 && (
              <span className="text-white/30 text-[10px] sm:text-xs">
                x{recipe.result_quantity}
              </span>
            )}
          </div>
        </div>
        {/* Source badge */}
        <span
          className={`shrink-0 text-[9px] sm:text-[10px] font-medium uppercase px-1.5 py-0.5 rounded ${
            recipe.source === 'blueprint'
              ? 'bg-gold/20 text-gold'
              : 'bg-site-blue/20 text-site-blue'
          }`}
        >
          {recipe.source === 'blueprint' ? 'Чертёж' : 'Выучен'}
        </span>
      </div>

      {/* Description */}
      {recipe.description && (
        <p className="text-white/40 text-xs leading-snug line-clamp-2">
          {recipe.description}
        </p>
      )}

      {/* Ingredients */}
      <div className="space-y-1">
        <p className="text-white/50 text-[10px] sm:text-xs uppercase tracking-wide">Материалы</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
          {(recipe.ingredients ?? []).map((ing) => {
            const hasEnough = ing.available >= ing.quantity;
            return (
              <div
                key={ing.item_id}
                className="flex items-center gap-1.5 text-xs"
              >
                {ing.item_image ? (
                  <img
                    src={ing.item_image}
                    alt={ing.item_name}
                    className="w-5 h-5 rounded object-cover shrink-0"
                  />
                ) : (
                  <div className="w-5 h-5 rounded bg-white/10 shrink-0" />
                )}
                <span className="text-white/70 truncate">{ing.item_name}</span>
                <span className={`ml-auto shrink-0 font-medium ${hasEnough ? 'text-green-400' : 'text-site-red'}`}>
                  {ing.available}/{ing.quantity}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Craft button */}
      <button
        onClick={() => onCraft(recipe)}
        disabled={!recipe.can_craft}
        className={`mt-auto w-full py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
          recipe.can_craft
            ? 'bg-site-blue/20 text-site-blue hover:bg-site-blue/30'
            : 'bg-white/5 text-white/25 cursor-not-allowed'
        }`}
      >
        Создать
      </button>
    </motion.div>
  );
};

export default RecipeCard;
