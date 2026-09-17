// FEAT-165 — «Переработка»: raw materials of the character's profession
// (ore → ingots, reagents → essences, ...). Renders nothing when the
// profession has no refining rule (backend returns can_refine=false).
import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchRefineInfo,
  clearRefineInfo,
  selectRefineInfo,
  selectRefineInfoLoading,
  selectRefineInfoError,
} from '../../../redux/slices/craftingSlice';
import type { RefineSource } from '../../../types/professions';
import { RARITY_TEXT_COLORS } from '../../../constants/items';
import { resourceSubcategoryLabel } from '../../../constants/professions';
import SectionHeader from '../shared/SectionHeader';
import { MotionProfileCard } from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';
import LoadingState from '../shared/LoadingState';
import ErrorState from '../shared/ErrorState';
import RefineModal from './RefineModal';

interface RefiningSectionProps {
  characterId: number;
  /** Refetch when the profession or its rank changes */
  professionId: number;
  currentRank: number;
}

const RefiningSection = ({ characterId, professionId, currentRank }: RefiningSectionProps) => {
  const dispatch = useAppDispatch();
  const info = useAppSelector(selectRefineInfo);
  const loading = useAppSelector(selectRefineInfoLoading);
  const error = useAppSelector(selectRefineInfoError);
  const [selected, setSelected] = useState<RefineSource | null>(null);

  useEffect(() => {
    dispatch(fetchRefineInfo(characterId));
  }, [dispatch, characterId, professionId, currentRank]);

  useEffect(() => () => {
    dispatch(clearRefineInfo());
  }, [dispatch]);

  if (!info) {
    if (loading) {
      return <LoadingState size="sm" />;
    }
    if (error) {
      return (
        <div className="flex flex-col gap-3">
          <SectionHeader title="Переработка" />
          <ErrorState
            message={error}
            onRetry={() => dispatch(fetchRefineInfo(characterId))}
            className="!py-6"
          />
        </div>
      );
    }
    return null;
  }

  if (!info.can_refine) return null;

  const sourceLabel = resourceSubcategoryLabel(info.source_subcategory);
  const resultLabel = resourceSubcategoryLabel(info.result_subcategory);
  const sources = Array.isArray(info.sources) ? info.sources : [];

  return (
    <div className="flex flex-col gap-3">
      <div className="space-y-1.5">
        <SectionHeader
          title="Переработка"
          extra={loading ? <LoadingState size="xs" /> : undefined}
        />
        <p className="text-xs text-white/50">
          {sourceLabel} → {resultLabel.toLowerCase()}
        </p>
        {info.double_chance_pct != null && (
          <p className="text-xs text-white/50">
            Шанс двойного результата: <span className="text-gold">{info.double_chance_pct}%</span>
          </p>
        )}
      </div>

      {error && <p className="text-site-red text-sm">{error}</p>}

      {sources.length === 0 ? (
        <p className="text-white/40 text-sm py-3 text-center">
          Нет сырья для переработки ({sourceLabel.toLowerCase()})
        </p>
      ) : (
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-2.5"
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.04 } } }}
        >
          {sources.map((src) => {
            const canRefine = src.max_batches > 0;
            return (
              <MotionProfileCard
                key={src.source_item_id}
                variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}
                className="flex flex-wrap items-center gap-3 p-3 min-w-0"
              >
                <GoldIconFrame
                  size={48}
                  shape="circle"
                  src={src.image}
                  alt={src.name}
                  fallback={<span className="text-white/30 text-lg">?</span>}
                />
                <div className="flex-1 min-w-[10rem] space-y-0.5">
                  <p className={`text-sm font-medium break-words ${RARITY_TEXT_COLORS[src.item_rarity] ?? 'text-white'}`}>
                    {src.name}
                  </p>
                  <p className="text-xs text-white/50">Есть: {src.owned_quantity}</p>
                  <p className="text-xs text-white/70 break-words">
                    {src.source_quantity} → {src.result_quantity}{' '}
                    <span className={RARITY_TEXT_COLORS[src.result_item.item_rarity] ?? 'text-white'}>
                      {src.result_item.name}
                    </span>
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelected(src)}
                  disabled={!canRefine}
                  title={canRefine ? undefined : `Нужно минимум ${src.source_quantity} шт.`}
                  className="btn-blue w-full sm:w-auto shrink-0 px-3 py-2 text-xs disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Переработать
                </button>
              </MotionProfileCard>
            );
          })}
        </motion.div>
      )}

      {selected && (
        <RefineModal
          characterId={characterId}
          source={selected}
          doubleChancePct={info.double_chance_pct}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
};

export default RefiningSection;
