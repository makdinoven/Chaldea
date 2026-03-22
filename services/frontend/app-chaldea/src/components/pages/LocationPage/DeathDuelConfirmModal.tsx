import { useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { sendPvpInvitation } from '../../../api/pvp';

interface DeathDuelConfirmModalProps {
  targetName: string;
  targetLevel: number;
  targetCharacterId: number;
  currentCharacterId: number;
  onClose: () => void;
  onSuccess: () => void;
}

const CONFIRMATION_WORD = 'ПОДТВЕРЖДАЮ';

const DeathDuelConfirmModal = ({
  targetName,
  targetLevel,
  targetCharacterId,
  currentCharacterId,
  onClose,
  onSuccess,
}: DeathDuelConfirmModalProps) => {
  const [confirmText, setConfirmText] = useState('');
  const [loading, setLoading] = useState(false);

  const isConfirmed = confirmText.trim() === CONFIRMATION_WORD;

  const handleConfirm = async () => {
    if (!isConfirmed) return;
    setLoading(true);
    try {
      await sendPvpInvitation(currentCharacterId, targetCharacterId, 'pvp_death');
      toast.success('Вызов на смертельный бой отправлен!');
      onSuccess();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось отправить вызов на смертельный бой';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick max-w-sm w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="gold-text text-lg sm:text-xl font-medium uppercase mb-4">
          Смертельный бой
        </h3>

        {/* Warning */}
        <div className="bg-site-red/10 border border-site-red/30 rounded-card p-3 sm:p-4 mb-4">
          <p className="text-site-red text-sm sm:text-base font-medium text-center">
            ВНИМАНИЕ! Проигравший в этом бою потеряет своего персонажа навсегда!
          </p>
        </div>

        {/* Target info */}
        <div className="flex flex-col gap-3 mb-4">
          <p className="text-white text-sm">
            Вы собираетесь вызвать на{' '}
            <span className="text-site-red font-medium">смертельный бой</span>{' '}
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
        </div>

        {/* Confirmation input */}
        <div className="flex flex-col gap-2 mb-6">
          <label className="text-white/60 text-xs">
            Для подтверждения введите <span className="text-white font-medium">{CONFIRMATION_WORD}</span>
          </label>
          <input
            type="text"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={CONFIRMATION_WORD}
            className="input-underline text-sm"
            disabled={loading}
            autoComplete="off"
          />
        </div>

        {/* Buttons */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="btn-line text-xs sm:text-sm px-4 py-1.5"
          >
            Отмена
          </button>
          <button
            onClick={handleConfirm}
            disabled={!isConfirmed || loading}
            className="btn-blue text-xs sm:text-sm px-4 py-1.5 disabled:opacity-50"
          >
            {loading ? 'Отправка...' : 'Подтвердить'}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default DeathDuelConfirmModal;
