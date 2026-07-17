// FEAT-151 — CraftTab no-profession screen (§3.4.3, user decision — the mock
// has no such screen): gold-framed PanelShell with a heading and 4 profession
// cards (gold icon frame, name, short description, «Выбрать»).
// The confirmation modal flow is preserved from the previous version.
import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Hammer } from 'lucide-react';
import type { Profession } from '../../../types/professions';
import PanelShell from '../PanelShell';

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
    <PanelShell
      title="Выбор профессии"
      icon={<Hammer size={16} strokeWidth={1.8} className="text-gold shrink-0" />}
    >
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
        className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5"
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
              className="relative rounded-card bg-black/30 border border-gold/[0.16] shadow-card flex flex-col gap-3 p-4 transition-colors duration-200 ease-site hover:border-gold/40"
            >
              {/* Icon frame + name */}
              <div className="flex items-center gap-3">
                <div className="w-[54px] h-[54px] shrink-0 rounded-[13px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
                  <div className="w-full h-full rounded-[11px] bg-site-dark flex items-center justify-center overflow-hidden">
                    {prof.icon ? (
                      <img src={prof.icon} alt={prof.name} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-gold text-lg">{prof.name.charAt(0)}</span>
                    )}
                  </div>
                </div>
                <h4 className="text-white text-[15px] font-medium leading-tight">
                  {prof.name}
                </h4>
              </div>

              {/* Description */}
              {prof.description && (
                <p className="text-white/50 text-xs leading-relaxed line-clamp-3">
                  {prof.description}
                </p>
              )}

              {/* Select button */}
              <button
                type="button"
                onClick={() => setConfirmId(prof.id)}
                disabled={loading}
                className="mt-auto w-full py-2.5 rounded-[10px] text-xs font-medium uppercase tracking-[0.04em] bg-site-blue/20 text-site-blue hover:bg-site-blue/30 transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed"
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
    </PanelShell>
  );
};

export default ProfessionSelect;
