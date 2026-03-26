import { useState, useMemo } from 'react';
import { motion } from 'motion/react';
import type { Recipe } from '../../../types/professions';
import RecipeCard from './RecipeCard';

interface RecipeListProps {
  recipes: Recipe[];
  loading: boolean;
  error: string | null;
  onCraft: (recipe: Recipe) => void;
}

const RecipeList = ({ recipes, loading, error, onCraft }: RecipeListProps) => {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return recipes;
    const q = search.trim().toLowerCase();
    return recipes.filter(
      (r) =>
        r.name?.toLowerCase().includes(q) ||
        r.result_item?.name?.toLowerCase().includes(q) ||
        r.ingredients?.some((i) => i.item_name?.toLowerCase().includes(q)),
    );
  }, [recipes, search]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-8 text-center">
        <p className="text-site-red text-sm">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Search */}
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск рецептов..."
        className="input-underline w-full max-w-sm"
      />

      {/* Recipes grid */}
      {filtered.length === 0 ? (
        <p className="text-white/40 text-sm py-6 text-center">
          {recipes.length === 0 ? 'Нет доступных рецептов' : 'Ничего не найдено'}
        </p>
      ) : (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.04 } },
          }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
        >
          {filtered.map((recipe) => (
            <RecipeCard key={recipe.id} recipe={recipe} onCraft={onCraft} />
          ))}
        </motion.div>
      )}
    </div>
  );
};

export default RecipeList;
