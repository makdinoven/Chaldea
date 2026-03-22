import { useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { sendPvpInvitation } from '../../../api/pvp';

interface DuelInviteModalProps {
  targetName: string;
  targetLevel: number;
  battleType: 'pvp_training' | 'pvp_death';
  initiatorCharacterId: number;
  targetCharacterId: number;
  onComplete: () => void;
  onCancel: () => void;
}

const BATTLE_TYPE_LABELS: Record<string, string> = {
  pvp_training: 'тренировочный бой',
  pvp_death: 'смертельный бой',
};

const DuelInviteModal = ({
  targetName,
  targetLevel,
  battleType,
  initiatorCharacterId,
  targetCharacterId,
  onComplete,
  onCancel,
}: DuelInviteModalProps) => {
  const [loading, setLoading] = useState(false);

  const handleConfirm = async () => {
    setLoading(true);
    try {
      await sendPvpInvitation(initiatorCharacterId, targetCharacterId, battleType);
      toast.success(`Вызов на ${BATTLE_TYPE_LABELS[battleType]} отправлен!`);
      onComplete();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось отправить вызов на бой';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick max-w-sm w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="gold-text text-lg sm:text-xl font-medium uppercase mb-4">
          Вызов на бой
        </h3>

        <div className="flex flex-col gap-3 mb-6">
          <p className="text-white text-sm">
            Вы собираетесь вызвать на{' '}
            <span className="text-gold font-medium">
              {BATTLE_TYPE_LABELS[battleType]}
            </span>{' '}
            игрока:
          </p>

          <div className="flex items-center gap-3 bg-black/40 rounded-card p-3">
            <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-black/60 flex items-center justify-center text-white/20 shrink-0">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 sm:w-6 sm:h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-white text-sm font-medium truncate">{targetName}</span>
              <span className="gold-text text-xs">LVL {targetLevel}</span>
            </div>
          </div>

          {battleType === 'pvp_training' && (
            <p className="text-white/50 text-xs">
              Проигравший останется с 1 HP. Противник должен принять вызов.
            </p>
          )}
        </div>

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="btn-line text-xs sm:text-sm px-4 py-1.5"
          >
            Отмена
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="btn-blue text-xs sm:text-sm px-4 py-1.5 disabled:opacity-50"
          >
            {loading ? 'Отправка...' : 'Вызвать'}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default DuelInviteModal;
