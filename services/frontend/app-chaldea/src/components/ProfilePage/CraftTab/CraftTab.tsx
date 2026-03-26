import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchProfessions,
  fetchCharacterProfession,
  chooseProfession,
  changeProfession,
  fetchRecipes,
  craftItem,
  clearCraftResult,
  selectProfessions,
  selectProfessionsLoading,
  selectProfessionsError,
  selectCharacterProfession,
  selectCharacterProfessionLoading,
  selectCharacterProfessionError,
  selectRecipes,
  selectRecipesLoading,
  selectRecipesError,
  selectCraftLoading,
} from '../../../redux/slices/craftingSlice';
import type { Recipe, CraftResult } from '../../../types/professions';
import ProfessionSelect from './ProfessionSelect';
import ProfessionInfo from './ProfessionInfo';
import RecipeList from './RecipeList';
import CraftConfirmModal from './CraftConfirmModal';
import SharpeningSection from './SharpeningSection';
import EssenceExtractionSection from './EssenceExtractionSection';
import TransmutationSection from './TransmutationSection';
import GemSocketSection from './GemSocketSection';
import RuneSocketSection from './RuneSocketSection';
import SmeltingSection from './SmeltingSection';
import ActiveBuffIndicator from './ActiveBuffIndicator';

interface CraftTabProps {
  characterId: number;
}

const CraftTab = ({ characterId }: CraftTabProps) => {
  const dispatch = useAppDispatch();

  const professions = useAppSelector(selectProfessions);
  const professionsLoading = useAppSelector(selectProfessionsLoading);
  const professionsError = useAppSelector(selectProfessionsError);

  const characterProfession = useAppSelector(selectCharacterProfession);
  const charProfLoading = useAppSelector(selectCharacterProfessionLoading);
  const charProfError = useAppSelector(selectCharacterProfessionError);

  const recipes = useAppSelector(selectRecipes);
  const recipesLoading = useAppSelector(selectRecipesLoading);
  const recipesError = useAppSelector(selectRecipesError);

  const craftLoading = useAppSelector(selectCraftLoading);

  const [craftRecipe, setCraftRecipe] = useState<Recipe | null>(null);
  // Use state (not ref) so the transition from "not fetched" to "fetched"
  // triggers a proper re-render and avoids any race with Redux loading flags.
  const [hasFetched, setHasFetched] = useState(false);

  // Load professions and character profession on mount
  useEffect(() => {
    setHasFetched(true);
    dispatch(fetchProfessions());
    dispatch(fetchCharacterProfession(characterId));
  }, [dispatch, characterId]);

  // Load recipes when character has a profession
  useEffect(() => {
    if (characterProfession) {
      dispatch(fetchRecipes({ characterId }));
    }
  }, [dispatch, characterId, characterProfession]);

  // Show errors as toasts
  useEffect(() => {
    if (professionsError) toast.error(professionsError);
  }, [professionsError]);

  useEffect(() => {
    // 404 for no profession is expected — don't show as error
    if (charProfError && !charProfError.includes('404') && !charProfError.toLowerCase().includes('not found') && !charProfError.toLowerCase().includes('нет профессии') && !charProfError.toLowerCase().includes('no profession')) {
      toast.error(charProfError);
    }
  }, [charProfError]);

  useEffect(() => {
    if (recipesError) toast.error(recipesError);
  }, [recipesError]);

  // Handle profession selection
  const handleSelectProfession = useCallback(
    async (professionId: number) => {
      const result = await dispatch(chooseProfession({ characterId, professionId }));
      if (result.meta.requestStatus === 'fulfilled') {
        toast.success('Профессия выбрана!');
        dispatch(fetchCharacterProfession(characterId));
      } else {
        const err = result.payload as string | undefined;
        toast.error(err ?? 'Не удалось выбрать профессию');
      }
    },
    [dispatch, characterId],
  );

  // Handle profession change
  const handleChangeProfession = useCallback(
    async (professionId: number) => {
      const result = await dispatch(changeProfession({ characterId, professionId }));
      if (result.meta.requestStatus === 'fulfilled') {
        toast.success('Профессия изменена');
        dispatch(fetchCharacterProfession(characterId));
      } else {
        const err = result.payload as string | undefined;
        toast.error(err ?? 'Не удалось сменить профессию');
      }
    },
    [dispatch, characterId],
  );

  // Handle crafting
  const handleCraft = useCallback(
    (recipe: Recipe) => {
      setCraftRecipe(recipe);
    },
    [],
  );

  const handleConfirmCraft = useCallback(
    async () => {
      if (!craftRecipe) return;

      const result = await dispatch(
        craftItem({
          characterId,
          recipeId: craftRecipe.id,
          blueprintItemId: craftRecipe.blueprint_item_id,
        }),
      );

      if (result.meta.requestStatus === 'fulfilled') {
        const craftResult = result.payload as CraftResult;
        const xpText = craftResult.xp_earned > 0 ? ` +${craftResult.xp_earned} XP` : '';
        toast.success(`Предмет создан!${xpText}`);

        if (craftResult.rank_up && craftResult.new_rank_name) {
          toast.success(`Повышение ранга: ${craftResult.new_rank_name}!`, { duration: 5000 });
        }

        if (craftResult.auto_learned_recipes?.length > 0) {
          const names = craftResult.auto_learned_recipes.map((r) => r.name).join(', ');
          toast.success(`Новые рецепты изучены: ${names}`, { duration: 4000 });
        }

        setCraftRecipe(null);
        dispatch(clearCraftResult());
        // Refresh recipes to update material counts and newly learned recipes
        dispatch(fetchRecipes({ characterId }));
        // Refresh profession to update XP bar
        dispatch(fetchCharacterProfession(characterId));
      } else {
        const err = result.payload as string | undefined;
        toast.error(err ?? 'Не удалось создать предмет');
      }
    },
    [dispatch, characterId, craftRecipe],
  );

  // Show spinner until initial data fetch cycle completes.
  // hasFetched starts false so the very first render shows a spinner
  // instead of briefly flashing empty content before useEffect runs.
  const isInitialLoading = !hasFetched || professionsLoading || charProfLoading;

  if (isInitialLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Determine if character has a profession
  const hasProfession = characterProfession !== null;
  // Defensive: ensure professions is always an array
  const safeProfs = Array.isArray(professions) ? professions : [];
  const safeRecipes = Array.isArray(recipes) ? recipes : [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="space-y-4 rounded-card border border-white/10 bg-black/50 p-3 sm:p-4"
    >
      {!hasProfession ? (
        <ProfessionSelect
          professions={safeProfs}
          loading={charProfLoading}
          onSelect={handleSelectProfession}
        />
      ) : (
        <>
          <ProfessionInfo
            characterProfession={characterProfession}
            professions={safeProfs}
            loading={charProfLoading}
            onChangeProfession={handleChangeProfession}
          />
          <ActiveBuffIndicator characterId={characterId} />
          {characterProfession.profession.slug === 'blacksmith' && (
            <SharpeningSection characterId={characterId} />
          )}
          {characterProfession.profession.slug === 'alchemist' && (
            <>
              <EssenceExtractionSection characterId={characterId} />
              <TransmutationSection characterId={characterId} />
            </>
          )}
          {characterProfession.profession.slug === 'jeweler' && (
            <>
              <GemSocketSection characterId={characterId} />
              <SmeltingSection characterId={characterId} />
            </>
          )}
          {characterProfession.profession.slug === 'enchanter' && (
            <RuneSocketSection characterId={characterId} />
          )}
          <RecipeList
            recipes={safeRecipes}
            loading={recipesLoading}
            error={recipesError}
            onCraft={handleCraft}
          />
        </>
      )}

      {/* Craft confirmation modal */}
      {craftRecipe && (
        <CraftConfirmModal
          recipe={craftRecipe}
          onConfirm={handleConfirmCraft}
          onCancel={() => setCraftRecipe(null)}
          loading={craftLoading}
        />
      )}
    </motion.div>
  );
};

export default CraftTab;
