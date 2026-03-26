import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import type { CharacterProfession, Profession } from '../../../types/professions';

interface ProfessionInfoProps {
  characterProfession: CharacterProfession;
  professions: Profession[];
  loading: boolean;
  onChangeProfession: (professionId: number) => void;
}

const ProfessionInfo = ({
  characterProfession,
  professions,
  loading,
  onChangeProfession,
}: ProfessionInfoProps) => {
  const [showChangeModal, setShowChangeModal] = useState(false);
  const [selectedNewId, setSelectedNewId] = useState<number | null>(null);

  const prof = characterProfession?.profession;

  if (!prof) {
    return null;
  }

  const otherProfessions = professions.filter(
    (p) => p.is_active && p.id !== prof.id,
  );

  // XP progress calculations
  const currentXp = characterProfession.experience;
  const sortedRanks = [...(prof.ranks || [])].sort(
    (a, b) => a.rank_number - b.rank_number,
  );
  const nextRank = sortedRanks.find(
    (r) => r.rank_number === characterProfession.current_rank + 1,
  );
  const isMaxRank = !nextRank;
  const xpThreshold = nextRank?.required_experience ?? 0;
  const progressPercent = isMaxRank
    ? 100
    : xpThreshold > 0
      ? Math.min(100, Math.round((currentXp / xpThreshold) * 100))
      : 100;

  const handleConfirmChange = () => {
    if (selectedNewId !== null) {
      onChangeProfession(selectedNewId);
      setShowChangeModal(false);
      setSelectedNewId(null);
    }
  };

  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4 mb-4">
      {/* Profession icon + info */}
      <div className="flex items-center gap-3">
        {prof.icon ? (
          <img
            src={prof.icon}
            alt={prof.name}
            className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg object-cover"
          />
        ) : (
          <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-white/10 flex items-center justify-center">
            <span className="text-gold text-lg">{prof.name.charAt(0)}</span>
          </div>
        )}
        <div>
          <h3 className="gold-text text-base sm:text-lg font-medium">{prof.name}</h3>
          <p className="text-white/50 text-xs sm:text-sm">
            {characterProfession.rank_name} (ранг {characterProfession.current_rank})
          </p>
        </div>
      </div>

      {/* XP Progress bar */}
      <div className="flex-1 min-w-0 w-full sm:w-auto">
        <div className="w-full max-w-xs">
          <div className="h-2 rounded-full bg-white/10 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ease-out ${
                isMaxRank
                  ? 'bg-gradient-to-r from-gold-dark via-gold to-gold-light'
                  : 'bg-gradient-to-r from-gold-dark to-gold'
              }`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <p className="text-white/40 text-xs mt-1">
            {isMaxRank ? (
              <>Макс. ранг &middot; {currentXp} XP</>
            ) : (
              <>{currentXp} / {xpThreshold} XP</>
            )}
          </p>
        </div>
      </div>

      {/* Change profession button */}
      <button
        onClick={() => setShowChangeModal(true)}
        className="text-xs sm:text-sm text-white/40 hover:text-site-blue transition-colors sm:ml-auto shrink-0"
      >
        Сменить профессию
      </button>

      {/* Change confirmation modal */}
      <AnimatePresence>
        {showChangeModal && (
          <div className="modal-overlay" onClick={() => { setShowChangeModal(false); setSelectedNewId(null); }}>
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
              <div className="mb-4 p-2.5 rounded-lg bg-site-red/10 border border-site-red/30">
                <p className="text-site-red text-sm">
                  Прогресс будет потерян, выученные рецепты сохранятся. Продолжить?
                </p>
              </div>

              {/* Profession selector */}
              <div className="space-y-2 mb-5 max-h-60 overflow-y-auto gold-scrollbar">
                {otherProfessions.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setSelectedNewId(p.id)}
                    className={`w-full flex items-center gap-3 p-2.5 rounded-lg text-left transition-all duration-200 ${
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
                <button
                  onClick={() => { setShowChangeModal(false); setSelectedNewId(null); }}
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

export default ProfessionInfo;
