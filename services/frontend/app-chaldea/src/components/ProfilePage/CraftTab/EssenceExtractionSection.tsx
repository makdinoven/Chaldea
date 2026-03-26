import { useEffect, useCallback } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchExtractInfo,
  extractEssence,
  fetchCharacterProfession,
  selectExtractInfo,
  selectExtractInfoLoading,
  selectExtractLoading,
  selectExtractError,
} from '../../../redux/slices/craftingSlice';
import type { CrystalInfo } from '../../../types/professions';

interface EssenceExtractionSectionProps {
  characterId: number;
}

const EssenceExtractionSection = ({ characterId }: EssenceExtractionSectionProps) => {
  const dispatch = useAppDispatch();

  const extractInfo = useAppSelector(selectExtractInfo);
  const extractInfoLoading = useAppSelector(selectExtractInfoLoading);
  const extractLoading = useAppSelector(selectExtractLoading);
  const extractError = useAppSelector(selectExtractError);

  useEffect(() => {
    dispatch(fetchExtractInfo(characterId));
  }, [dispatch, characterId]);

  useEffect(() => {
    if (extractError) toast.error(extractError);
  }, [extractError]);

  const handleExtract = useCallback(
    async (crystal: CrystalInfo) => {
      const result = await dispatch(
        extractEssence({ characterId, crystalItemId: crystal.inventory_item_id }),
      );

      if (result.meta.requestStatus === 'fulfilled') {
        const payload = result.payload as import('../../../types/professions').ExtractEssenceResult;

        if (payload.success) {
          toast.success(`Эссенция получена! ${payload.essence_name}`);
        } else {
          toast.error('Неудача! Кристалл потерян');
        }

        if (payload.xp_earned > 0) {
          toast.success(`+${payload.xp_earned} XP`, { duration: 3000 });
        }

        if (payload.rank_up && payload.new_rank_name) {
          toast.success(`Повышение ранга: ${payload.new_rank_name}!`, { duration: 5000 });
        }

        // Refresh data
        dispatch(fetchExtractInfo(characterId));
        dispatch(fetchCharacterProfession(characterId));
      } else {
        const err = result.payload as string | undefined;
        toast.error(err ?? 'Не удалось извлечь эссенцию');
      }
    },
    [dispatch, characterId],
  );

  const crystals = extractInfo?.crystals ?? [];

  return (
    <div className="space-y-3">
      <div>
        <h3 className="gold-text text-lg font-medium uppercase">Экстракция эссенций</h3>
        <p className="text-white/60 text-sm mt-1">
          Извлекайте магические эссенции из кристаллов. Кристалл расходуется при каждой попытке.
        </p>
      </div>

      {extractInfoLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
        </div>
      ) : crystals.length === 0 ? (
        <p className="text-white/40 text-sm py-4 text-center">
          Нет кристаллов для извлечения
        </p>
      ) : (
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3"
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.04 } } }}
        >
          {crystals.map((crystal) => (
            <motion.div
              key={crystal.inventory_item_id}
              variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}
              className="flex flex-col gap-2 p-3 rounded-card bg-white/[0.04] border border-white/10"
            >
              {/* Crystal -> Essence row */}
              <div className="flex items-center gap-2">
                {/* Crystal */}
                <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
                  <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full overflow-hidden bg-white/[0.05] flex items-center justify-center flex-shrink-0">
                    {crystal.image ? (
                      <img src={crystal.image} alt={crystal.name} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-white/30 text-xl">?</span>
                    )}
                  </div>
                  <span className="text-white text-xs text-center leading-tight line-clamp-2">
                    {crystal.name}
                  </span>
                  <span className="text-white/50 text-xs">x{crystal.quantity}</span>
                </div>

                {/* Arrow */}
                <span className="text-gold text-lg flex-shrink-0">&rarr;</span>

                {/* Essence */}
                <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
                  <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-full overflow-hidden bg-white/[0.05] flex items-center justify-center flex-shrink-0">
                    {crystal.essence_image ? (
                      <img src={crystal.essence_image} alt={crystal.essence_name} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-white/30 text-xl">?</span>
                    )}
                  </div>
                  <span className="text-white text-xs text-center leading-tight line-clamp-2">
                    {crystal.essence_name}
                  </span>
                </div>
              </div>

              {/* Chance + Button */}
              <div className="flex items-center justify-between mt-1">
                <span className="text-white/60 text-xs">
                  Шанс: <span className="text-gold font-medium">{crystal.success_chance}%</span>
                </span>
                <button
                  onClick={() => handleExtract(crystal)}
                  disabled={extractLoading}
                  className="btn-blue text-xs px-3 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {extractLoading ? 'Извлечение...' : 'Извлечь'}
                </button>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
};

export default EssenceExtractionSection;
