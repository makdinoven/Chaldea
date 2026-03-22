import { motion, AnimatePresence } from 'motion/react';
import type { BattleRewards } from '../../../api/mobs';

interface BattleRewardsModalProps {
  rewards: BattleRewards;
  visible: boolean;
  onClose: () => void;
}

const BattleRewardsModal = ({ rewards, visible, onClose }: BattleRewardsModalProps) => {
  return (
    <AnimatePresence>
      {visible && (
        <div className="modal-overlay" onClick={onClose}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="modal-content gold-outline gold-outline-thick max-w-md w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Victory title */}
            <h2 className="gold-text text-3xl sm:text-4xl font-medium uppercase text-center mb-6">
              Победа!
            </h2>

            {/* Rewards list */}
            <div className="flex flex-col gap-4 mb-6">
              {/* XP */}
              {rewards.xp > 0 && (
                <div className="flex items-center gap-3 p-3 rounded-card bg-white/5">
                  <div className="w-10 h-10 rounded-full bg-site-blue/20 flex items-center justify-center shrink-0">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="w-5 h-5 text-site-blue"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                      />
                    </svg>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-white/60 text-xs uppercase tracking-wider">
                      Опыт
                    </span>
                    <span className="text-white text-lg font-medium">
                      +{rewards.xp}
                    </span>
                  </div>
                </div>
              )}

              {/* Gold */}
              {rewards.gold > 0 && (
                <div className="flex items-center gap-3 p-3 rounded-card bg-white/5">
                  <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center shrink-0">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="w-5 h-5 text-gold"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-white/60 text-xs uppercase tracking-wider">
                      Золото
                    </span>
                    <span className="text-gold text-lg font-medium">
                      +{rewards.gold}
                    </span>
                  </div>
                </div>
              )}

              {/* Items */}
              {rewards.items.length > 0 && (
                <div className="flex flex-col gap-2">
                  <span className="text-white/60 text-xs uppercase tracking-wider px-1">
                    Предметы
                  </span>
                  {rewards.items.map((item, index) => (
                    <div
                      key={`${item.item_id}-${index}`}
                      className="flex items-center gap-3 p-3 rounded-card bg-white/5"
                    >
                      <div className="w-10 h-10 rounded-full bg-purple-500/20 flex items-center justify-center shrink-0">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="w-5 h-5 text-purple-300"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                          />
                        </svg>
                      </div>
                      <div className="flex flex-col flex-1 min-w-0">
                        <span className="text-white text-sm font-medium truncate">
                          {item.item_name ?? `Предмет #${item.item_id}`}
                        </span>
                        <span className="text-white/50 text-xs">
                          x{item.quantity}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Fallback: no rewards */}
              {rewards.xp === 0 && rewards.gold === 0 && rewards.items.length === 0 && (
                <p className="text-white/50 text-sm text-center">
                  Нет наград за этот бой
                </p>
              )}
            </div>

            {/* Close button */}
            <button
              onClick={onClose}
              className="btn-blue w-full text-base py-3"
            >
              Закрыть
            </button>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default BattleRewardsModal;
