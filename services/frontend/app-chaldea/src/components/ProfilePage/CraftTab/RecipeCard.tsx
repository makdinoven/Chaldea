// FEAT-151 — recipe card per mock 1011-1037: 52px round icon with rarity ring,
// name + qty, rarity label, source badge (Чертёж/Выучен), description,
// «Материалы» have/need list and the craft button (disabled style when short).
import { motion } from 'motion/react';
import type { Recipe } from '../../../types/professions';

// Ring color around the 52px round icon (design-system rarity tokens only;
// divine/demonic map to the closest existing tokens)
const RARITY_RING: Record<string, string> = {
  common: 'bg-white/25',
  rare: 'bg-rarity-rare',
  epic: 'bg-rarity-epic',
  mythical: 'bg-rarity-mythical',
  legendary: 'bg-gradient-to-b from-gold-light to-gold-dark',
  divine: 'bg-gradient-to-b from-gold-light to-gold-dark',
  demonic: 'bg-rarity-mythical',
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
  const ringClass = RARITY_RING[recipe.rarity] ?? 'bg-white/25';
  const rarityTextClass = RARITY_TEXT[recipe.rarity] ?? 'text-white/60';
  const rarityLabel = RARITY_LABEL[recipe.rarity] ?? recipe.rarity;

  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
      className="relative rounded-card bg-black/30 border border-gold/[0.16] shadow-card flex flex-col gap-3 p-4 transition-colors duration-200 ease-site hover:border-gold/40"
    >
      {/* Header: 52px round icon with rarity ring + name/qty/rarity + source badge */}
      <div className="flex items-start gap-3">
        <div className={`w-[52px] h-[52px] shrink-0 rounded-full p-[2px] ${ringClass}`}>
          <div className="w-full h-full rounded-full bg-site-dark flex items-center justify-center overflow-hidden">
            {recipe.result_item?.image ? (
              <img
                src={recipe.result_item.image}
                alt={recipe.result_item?.name ?? recipe.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-white/30 text-base">?</span>
            )}
          </div>
        </div>
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
        {/* Source badge */}
        <span
          className={`shrink-0 text-[9.5px] font-medium uppercase tracking-[0.04em] px-2 py-0.5 rounded ${
            recipe.source === 'blueprint'
              ? 'bg-gold/15 text-gold'
              : 'bg-site-blue/15 text-site-blue'
          }`}
        >
          {recipe.source === 'blueprint' ? 'Чертёж' : 'Выучен'}
        </span>
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
    </motion.div>
  );
};

export default RecipeCard;
