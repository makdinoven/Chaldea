// FEAT-151/166 — «Рецепты» panel of the Craft tab: PanelShell with the
// filtered count in the header, the search in a fixed toolbar and the card
// grid in the scroll area (internal scroll on lg+ only).
import { useState, useMemo } from 'react';
import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { BookOpen, Hammer } from 'lucide-react';
import type { Recipe } from '../../../types/professions';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import PanelCounter from '../shared/PanelCounter';
import PanelToolbar from '../shared/PanelToolbar';
import PanelScrollArea from '../shared/PanelScrollArea';
import EmptyState from '../shared/EmptyState';
import ErrorState from '../shared/ErrorState';
import LoadingState from '../shared/LoadingState';
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

  const isReady = !loading && !error;

  let content: ReactNode;
  if (loading) {
    content = <LoadingState />;
  } else if (error) {
    content = <ErrorState message={error} />;
  } else if (filtered.length === 0) {
    content = (
      <EmptyState
        icon={<Hammer size={32} strokeWidth={1.5} className="text-white/20" />}
        message={recipes.length === 0 ? 'Нет доступных рецептов' : 'Ничего не найдено'}
      />
    );
  } else {
    content = (
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.04 } },
        }}
        className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-3.5"
      >
        {filtered.map((recipe) => (
          <RecipeCard key={recipe.id} recipe={recipe} onCraft={onCraft} />
        ))}
      </motion.div>
    );
  }

  return (
    <PanelShell
      title="Рецепты"
      icon={<BookOpen size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      headerExtra={isReady ? <PanelCounter>{filtered.length}</PanelCounter> : undefined}
      className={PANEL_DESKTOP_HEIGHT_CLASS}
      bodyClassName="flex-1 min-h-0 flex flex-col"
    >
      {isReady && (
        <PanelToolbar>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск рецептов..."
            className="input-underline w-full sm:max-w-sm"
          />
        </PanelToolbar>
      )}
      <PanelScrollArea className={isReady ? '' : '!pt-4'}>{content}</PanelScrollArea>
    </PanelShell>
  );
};

export default RecipeList;
