import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import type { Profession } from '../../../types/professions';

interface ProfessionSelectProps {
  professions: Profession[];
  loading: boolean;
  onSelect: (professionId: number) => void;
}

const ProfessionSelect = ({ professions, loading, onSelect }: ProfessionSelectProps) => {
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const confirmProfession = professions.find((p) => p.id === confirmId);

  const handleConfirm = () => {
    if (confirmId !== null) {
      onSelect(confirmId);
      setConfirmId(null);
    }
  };

  return (
    <div>
      <h3 className="gold-text text-lg font-medium uppercase mb-1">
        Выберите профессию
      </h3>
      <p className="text-white/50 text-sm mb-4">
        Профессия определяет, какие предметы вы сможете создавать. Выбрать можно только одну.
      </p>

      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.06 } },
        }}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4"
      >
        {[...professions]
          .filter((p) => p.is_active)
          .sort((a, b) => a.sort_order - b.sort_order)
          .map((prof) => (
            <motion.div
              key={prof.id}
              variants={{
                hidden: { opacity: 0, y: 10 },
                visible: { opacity: 1, y: 0 },
              }}
              className="rounded-card p-4 bg-black/40 border border-white/10 flex flex-col gap-2 hover:border-white/20 transition-all duration-200"
            >
              {/* Icon + name */}
              <div className="flex items-center gap-3">
                {prof.icon ? (
                  <img
                    src={prof.icon}
                    alt={prof.name}
                    className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg object-cover"
                  />
                ) : (
                  <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-white/10 flex items-center justify-center">
                    <span className="text-gold text-lg">
                      {prof.name.charAt(0)}
                    </span>
                  </div>
                )}
                <h4 className="gold-text text-base sm:text-lg font-medium">
                  {prof.name}
                </h4>
              </div>

              {/* Description */}
              {prof.description && (
                <p className="text-white/50 text-xs sm:text-sm leading-relaxed line-clamp-3">
                  {prof.description}
                </p>
              )}

              {/* Ranks preview */}
              {Array.isArray(prof.ranks) && prof.ranks.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {[...prof.ranks]
                    .sort((a, b) => a.rank_number - b.rank_number)
                    .map((rank) => (
                      <span
                        key={rank.id}
                        className="text-[10px] sm:text-xs text-white/30 px-1.5 py-0.5 rounded bg-white/[0.05]"
                      >
                        {rank.name}
                      </span>
                    ))}
                </div>
              )}

              {/* Select button */}
              <button
                onClick={() => setConfirmId(prof.id)}
                disabled={loading}
                className="mt-auto w-full py-2 rounded-lg text-sm font-medium bg-site-blue/20 text-site-blue hover:bg-site-blue/30 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Выбрать
              </button>
            </motion.div>
          ))}
      </motion.div>

      {/* Confirmation modal */}
      <AnimatePresence>
        {confirmProfession && (
          <div className="modal-overlay" onClick={() => setConfirmId(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-sm w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-xl font-medium uppercase mb-3">
                Подтверждение
              </h2>
              <p className="text-white mb-5">
                Вы уверены, что хотите выбрать профессию{' '}
                <span className="text-gold font-medium">{confirmProfession.name}</span>?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handleConfirm}
                  disabled={loading}
                  className="btn-blue flex-1 disabled:opacity-50"
                >
                  {loading ? 'Выбор...' : 'Подтвердить'}
                </button>
                <button
                  onClick={() => setConfirmId(null)}
                  className="btn-line flex-1"
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ProfessionSelect;
