/**
 * ToolSelectionModal (FEAT-128, task #21).
 *
 * Shown when the user clicks "Добыть" on a gathering node. Loads the
 * player's tools whose `tool_category` matches the node's category and:
 *
 *  - exactly one tool      → pre-selected, single confirm screen
 *  - multiple tools        → radio-style picker, "Подтвердить" enabled when
 *                            any tool is selected
 *  - zero tools            → the explicit spec warning ("без инструмента
 *                            сбор будет в 2 раза дольше и без бонусов")
 *
 * Errors from the tools fetch are rendered inline in Russian per
 * CLAUDE.md "Frontend Error Display" rule.
 *
 * Tailwind only, no React.FC, mobile responsive (360px+).
 */
import { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import {
  loadGatheringTools,
  selectToolsByCategory,
  selectGatheringIsLoadingTools,
  selectGatheringError,
  clearGatheringError,
} from '../../../../redux/slices/gatheringSlice';
import type { GatheringTool, GatheringCategory, ToolCategory } from '../../../../types/gathering';
import type { ToolSelectionModalProps } from './gatheringSection.types';

const NODE_CATEGORY_TO_TOOL: Record<GatheringCategory, ToolCategory> = {
  ore: 'pickaxe',
  herb: 'sickle',
  wood: 'axe',
};

const TOOL_CATEGORY_LABELS: Record<ToolCategory, string> = {
  pickaxe: 'Кирка',
  sickle: 'Серп',
  axe: 'Топор',
};

const fmtPct = (value: number): string => {
  if (!value) return '';
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}%` : `${rounded.toFixed(1)}%`;
};

const ToolBonuses = ({ tool }: { tool: GatheringTool }) => {
  const parts: string[] = [];
  if (tool.gather_double_chance_bonus > 0) parts.push(`Шанс дубля +${fmtPct(tool.gather_double_chance_bonus)}`);
  if (tool.gather_speed_bonus_pct > 0) parts.push(`Скорость +${fmtPct(tool.gather_speed_bonus_pct)}`);
  if (tool.gather_stamina_bonus_pct > 0) parts.push(`Стамина −${fmtPct(tool.gather_stamina_bonus_pct)}`);
  if (parts.length === 0) {
    return (
      <span className="text-white/40 text-xs">Без бонусов</span>
    );
  }
  return (
    <span className="text-site-blue text-xs">{parts.join(' · ')}</span>
  );
};

const ToolRow = ({
  tool,
  selected,
  onSelect,
}: {
  tool: GatheringTool;
  selected: boolean;
  onSelect: () => void;
}) => {
  const durabilityLabel =
    tool.current_durability === null
      ? `${tool.max_durability}/${tool.max_durability}`
      : `${tool.current_durability}/${tool.max_durability}`;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex items-start gap-3 p-3 rounded-card border text-left transition-colors w-full ${
        selected
          ? 'border-gold bg-gold/10'
          : 'border-white/10 bg-white/5 hover:border-white/30'
      }`}
    >
      <div className="gold-outline relative w-12 h-12 rounded-card overflow-hidden bg-black/40 shrink-0">
        {tool.image ? (
          <img src={tool.image} alt={tool.name} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-white/20 text-lg">
            ?
          </div>
        )}
      </div>
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span className="text-white text-sm font-medium truncate">
          {tool.name}
        </span>
        <span className="text-white/50 text-xs">
          Прочность: <span className="text-white/80">{durabilityLabel}</span>
        </span>
        <ToolBonuses tool={tool} />
      </div>
      <span
        className={`shrink-0 mt-1 w-4 h-4 rounded-full border ${
          selected ? 'border-gold bg-gold' : 'border-white/40'
        }`}
        aria-hidden="true"
      />
    </button>
  );
};

const ToolSelectionModal = ({
  node,
  inventoryId,
  characterId: _characterId, // eslint-disable-line @typescript-eslint/no-unused-vars
  onClose,
  onConfirm,
  submitting = false,
}: ToolSelectionModalProps) => {
  const dispatch = useAppDispatch();
  const toolCategory = NODE_CATEGORY_TO_TOOL[node.category];
  const tools = useAppSelector(selectToolsByCategory(toolCategory));
  const isLoading = useAppSelector(selectGatheringIsLoadingTools);
  const error = useAppSelector(selectGatheringError);

  const [selectedToolId, setSelectedToolId] = useState<number | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  // Load tools on open. We always re-fetch to guarantee the durability and
  // ownership are fresh (player may have repaired/dropped tools elsewhere).
  useEffect(() => {
    let cancelled = false;
    void dispatch(loadGatheringTools({ inventoryId, category: toolCategory }))
      .finally(() => {
        if (!cancelled) setHasFetched(true);
      });
    return () => {
      cancelled = true;
    };
    // We intentionally only re-run when modal opens for a new (inv, cat) pair.
  }, [dispatch, inventoryId, toolCategory]);

  // Auto-select when exactly one usable tool is available
  const usableTools = useMemo(
    () =>
      tools.filter(
        (t) => (t.current_durability ?? t.max_durability) > 0,
      ),
    [tools],
  );

  useEffect(() => {
    if (!hasFetched) return;
    if (usableTools.length === 1) {
      setSelectedToolId(usableTools[0].id);
    }
  }, [hasFetched, usableTools]);

  const handleClose = (): void => {
    if (submitting) return;
    dispatch(clearGatheringError());
    onClose();
  };

  const handleConfirm = async (toolInventoryItemId: number | null): Promise<void> => {
    await onConfirm(toolInventoryItemId);
  };

  const showLoading = isLoading && !hasFetched;
  const noTools = hasFetched && usableTools.length === 0;
  const oneTool = hasFetched && usableTools.length === 1;
  const manyTools = hasFetched && usableTools.length > 1;

  return (
    <div
      className="modal-overlay"
      onClick={handleClose}
      role="dialog"
      aria-modal="true"
      aria-label="Выбор инструмента"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick max-w-md w-full mx-4 max-h-[85vh] overflow-y-auto gold-scrollbar"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="gold-text text-lg sm:text-xl font-medium uppercase mb-2">
          Выбор инструмента
        </h3>
        <p className="text-white/70 text-xs sm:text-sm mb-4">
          {`Категория: ${TOOL_CATEGORY_LABELS[toolCategory]}`}
        </p>

        {showLoading && (
          <div className="flex items-center justify-center py-6">
            <div className="w-6 h-6 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        )}

        {error && !showLoading && (
          <div role="alert" className="text-red-400 text-sm mb-3 break-words">
            {error}
          </div>
        )}

        {noTools && (
          <div className="flex flex-col gap-3">
            <p className="text-white text-sm leading-relaxed">
              У вас нет подходящих инструментов. Без инструмента сбор будет
              в 2 раза дольше и без бонусов. Продолжить?
            </p>
            <div className="flex flex-col sm:flex-row gap-2">
              <button
                type="button"
                onClick={() => handleConfirm(null)}
                disabled={submitting}
                className="btn-blue text-sm flex-1 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? 'Запуск…' : 'Продолжить без инструмента'}
              </button>
              <button
                type="button"
                onClick={handleClose}
                disabled={submitting}
                className="btn-line text-sm flex-1 py-2 disabled:opacity-50"
              >
                Отмена
              </button>
            </div>
          </div>
        )}

        {oneTool && (
          <div className="flex flex-col gap-3">
            <p className="text-white text-sm">
              {`Использовать «${usableTools[0].name}»?`}
            </p>
            <ToolRow
              tool={usableTools[0]}
              selected
              onSelect={() => setSelectedToolId(usableTools[0].id)}
            />
            <div className="flex flex-col sm:flex-row gap-2">
              <button
                type="button"
                onClick={() => handleConfirm(usableTools[0].id)}
                disabled={submitting}
                className="btn-blue text-sm flex-1 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? 'Запуск…' : 'Подтвердить'}
              </button>
              <button
                type="button"
                onClick={handleClose}
                disabled={submitting}
                className="btn-line text-sm flex-1 py-2 disabled:opacity-50"
              >
                Отмена
              </button>
            </div>
          </div>
        )}

        {manyTools && (
          <div className="flex flex-col gap-3">
            <p className="text-white/70 text-xs sm:text-sm">
              Выберите инструмент для сбора:
            </p>
            <div className="flex flex-col gap-2 max-h-[50vh] overflow-y-auto gold-scrollbar pr-1">
              {usableTools.map((tool) => (
                <ToolRow
                  key={tool.id}
                  tool={tool}
                  selected={selectedToolId === tool.id}
                  onSelect={() => setSelectedToolId(tool.id)}
                />
              ))}
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <button
                type="button"
                onClick={() => selectedToolId && handleConfirm(selectedToolId)}
                disabled={submitting || selectedToolId === null}
                className="btn-blue text-sm flex-1 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? 'Запуск…' : 'Подтвердить'}
              </button>
              <button
                type="button"
                onClick={handleClose}
                disabled={submitting}
                className="btn-line text-sm flex-1 py-2 disabled:opacity-50"
              >
                Отмена
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
};

export default ToolSelectionModal;
