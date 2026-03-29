import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { SpellError } from '../../../api/spellcheck';

interface SpellCheckPanelProps {
  errors: SpellError[];
  loading: boolean;
  checked: boolean;
  onApplySuggestion: (errorIndex: number, suggestion: string) => void;
  onDismissError: (errorIndex: number) => void;
}

const SpellCheckPanel = ({
  errors,
  loading,
  checked,
  onApplySuggestion,
  onDismissError,
}: SpellCheckPanelProps) => {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 px-4 text-sm text-white/70">
        <svg
          className="animate-spin h-4 w-4 text-site-blue flex-shrink-0"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        Проверяю правописание...
      </div>
    );
  }

  if (!checked) return null;

  if (errors.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: -5 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="py-2 px-4 text-sm text-stat-energy"
      >
        Ошибок не найдено
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="flex flex-col gap-1 py-2"
    >
      <span className="px-4 text-xs text-white/50 mb-1">
        Найдено ошибок: {errors.length}
      </span>
      <div className="flex flex-col gap-1 max-h-[200px] overflow-y-auto gold-scrollbar px-2">
        {errors.map((error, index) => {
          const hasSuggestions = error.suggestions.length > 0;
          const hasAlternatives = error.suggestions.length > 1;

          return (
            <div
              key={`${error.word}-${error.pos}-${index}`}
              className="relative flex flex-col gap-1 px-2 py-1.5 rounded
                         hover:bg-white/[0.05] transition-colors"
            >
              <div className="flex flex-wrap items-center gap-2">
                {/* Click on the word auto-applies first suggestion */}
                <button
                  type="button"
                  onClick={() => {
                    if (hasSuggestions) {
                      onApplySuggestion(index, error.suggestions[0]);
                      setExpandedIndex(null);
                    }
                  }}
                  className={`font-medium text-sm transition-colors ${
                    hasSuggestions
                      ? 'text-site-red cursor-pointer hover:underline'
                      : 'text-site-red/60 cursor-default'
                  }`}
                  title={hasSuggestions ? `Исправить на «${error.suggestions[0]}»` : 'Нет вариантов'}
                >
                  {error.word}
                </button>

                {hasSuggestions && (
                  <span className="text-xs text-white/40 hidden sm:inline">
                    → {error.suggestions[0]}
                  </span>
                )}

                {/* Expand chevron for alternative suggestions */}
                {hasAlternatives && (
                  <button
                    type="button"
                    onClick={() => setExpandedIndex(expandedIndex === index ? null : index)}
                    className="text-xs text-white/30 hover:text-white/60 transition-colors"
                    title="Другие варианты"
                  >
                    <svg
                      className={`w-3.5 h-3.5 transition-transform ${
                        expandedIndex === index ? 'rotate-180' : ''
                      }`}
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => onDismissError(index)}
                  className="text-xs text-white/40 hover:text-white/70 transition-colors ml-auto"
                >
                  Пропустить
                </button>
              </div>

              {/* Alternative suggestions (excluding the first, which is auto-applied on click) */}
              <AnimatePresence>
                {expandedIndex === index && hasAlternatives && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.15 }}
                    className="flex flex-wrap gap-1.5 pl-2 overflow-hidden"
                  >
                    {error.suggestions.slice(1).map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        className="text-xs px-2 py-0.5 rounded bg-white/[0.07] text-white/70
                                   hover:bg-white/[0.15] hover:text-white transition-colors"
                        onClick={() => {
                          onApplySuggestion(index, suggestion);
                          setExpandedIndex(null);
                        }}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
};

export default SpellCheckPanel;
