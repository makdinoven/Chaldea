// FEAT-151 — CraftTab profession rail (mock 941-952): all professions as
// horizontal chips. The active one is gold-highlighted; the rest are dimmed.
// Clicking a non-active profession opens the existing change-profession modal
// (with its progress-loss warning), preselecting the clicked profession.
import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import type { CharacterProfession, Profession } from '../../../types/professions';

interface ProfessionRailProps {
  /** All professions from craftingSlice (filtered to is_active inside) */
  professions: Profession[];
  characterProfession: CharacterProfession;
  /** True while the change request is in flight */
  loading: boolean;
  onChangeProfession: (professionId: number) => void;
}

const ProfessionRail = ({
  professions,
  characterProfession,
  loading,
  onChangeProfession,
}: ProfessionRailProps) => {
  const [showChangeModal, setShowChangeModal] = useState(false);
  const [selectedNewId, setSelectedNewId] = useState<number | null>(null);

  const activeId = characterProfession.profession.id;
  const rail = [...professions]
    .filter((p) => p.is_active)
    .sort((a, b) => a.sort_order - b.sort_order);
  const otherProfessions = rail.filter((p) => p.id !== activeId);

  const openChangeModal = (professionId: number) => {
    setSelectedNewId(professionId);
    setShowChangeModal(true);
  };

  const closeModal = () => {
    setShowChangeModal(false);
    setSelectedNewId(null);
  };

  const handleConfirmChange = () => {
    if (selectedNewId !== null) {
      onChangeProfession(selectedNewId);
      closeModal();
    }
  };

  return (
    <>
      {/* Horizontal chip rail — scrolls on narrow screens */}
      <div className="flex gap-2 overflow-x-auto gold-scrollbar pb-1">
        {rail.map((prof) => {
          const isActive = prof.id === activeId;
          return (
            <button
              key={prof.id}
              type="button"
              onClick={() => {
                if (!isActive) openChangeModal(prof.id);
              }}
              className={`chip-outline flex items-center gap-2.5 shrink-0 px-4 py-2 rounded-card whitespace-nowrap transition-all duration-200 ease-site ${
                isActive
                  ? 'chip-outline-active cursor-default'
                  : 'opacity-50 hover:opacity-80 cursor-pointer'
              }`}
            >
              {prof.icon ? (
                <img
                  src={prof.icon}
                  alt={prof.name}
                  className="w-[26px] h-[26px] rounded-md object-cover shrink-0"
                />
              ) : (
                <span className="w-[26px] h-[26px] rounded-md bg-white/10 flex items-center justify-center shrink-0">
                  <span className="text-gold text-xs">{prof.name.charAt(0)}</span>
                </span>
              )}
              <span className="flex flex-col items-start gap-px">
                <span
                  className={`text-[13px] font-medium leading-tight ${
                    isActive ? 'text-gold' : 'text-white'
                  }`}
                >
                  {prof.name}
                </span>
                <span className="font-mono tabular-nums text-[9.5px] text-white/45 leading-tight">
                  {isActive
                    ? `Ранг ${characterProfession.current_rank} · ${characterProfession.rank_name}`
                    : 'Не изучена'}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {/* Change-profession confirmation modal (existing flow, progress-loss warning) */}
      <AnimatePresence>
        {showChangeModal && (
          <div className="modal-overlay" onClick={closeModal}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-md w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-xl font-medium uppercase mb-3">
                Сменить профессию
              </h2>

              {/* Warning */}
              <div className="mb-4 p-2.5 rounded-card bg-site-red/10 border border-site-red/30">
                <p className="text-site-red text-sm">
                  Прогресс будет потерян, выученные рецепты сохранятся. Продолжить?
                </p>
              </div>

              {/* Profession selector */}
              <div className="space-y-2 mb-5 max-h-60 overflow-y-auto gold-scrollbar">
                {otherProfessions.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setSelectedNewId(p.id)}
                    className={`w-full flex items-center gap-3 p-2.5 rounded-card text-left transition-all duration-200 ease-site ${
                      selectedNewId === p.id
                        ? 'bg-site-blue/20 border border-site-blue/40'
                        : 'bg-white/[0.03] border border-transparent hover:bg-white/[0.06]'
                    }`}
                  >
                    {p.icon ? (
                      <img src={p.icon} alt={p.name} className="w-8 h-8 rounded object-cover" />
                    ) : (
                      <div className="w-8 h-8 rounded bg-white/10 flex items-center justify-center">
                        <span className="text-gold text-sm">{p.name.charAt(0)}</span>
                      </div>
                    )}
                    <div>
                      <p className="text-white text-sm font-medium">{p.name}</p>
                      {p.description && (
                        <p className="text-white/40 text-xs line-clamp-1">{p.description}</p>
                      )}
                    </div>
                  </button>
                ))}
              </div>

              {/* Buttons */}
              <div className="flex gap-3">
                <button
                  onClick={handleConfirmChange}
                  disabled={loading || selectedNewId === null}
                  className="btn-blue flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Смена...' : 'Сменить'}
                </button>
                <button onClick={closeModal} className="btn-line flex-1">
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
};

export default ProfessionRail;
