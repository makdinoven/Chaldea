import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchBlocks,
  unblockUser,
  updateMessagePrivacy,
  selectBlocks,
} from '../../redux/slices/messengerSlice';
import type { MessagePrivacyValue } from '../../types/messenger';
import toast from 'react-hot-toast';

interface MessengerSettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

const PRIVACY_OPTIONS: { value: MessagePrivacyValue; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'friends', label: 'Только друзья' },
  { value: 'nobody', label: 'Никто' },
];

const MessengerSettings = ({ isOpen, onClose }: MessengerSettingsProps) => {
  const dispatch = useAppDispatch();
  const blocks = useAppSelector(selectBlocks);
  const [privacy, setPrivacy] = useState<MessagePrivacyValue>('all');
  const [saving, setSaving] = useState(false);

  // Load blocks when opened
  useEffect(() => {
    if (isOpen) {
      dispatch(fetchBlocks());
    }
  }, [isOpen, dispatch]);

  const handleSavePrivacy = async () => {
    setSaving(true);
    try {
      await dispatch(updateMessagePrivacy({ message_privacy: privacy })).unwrap();
      toast.success('Настройки сохранены');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось сохранить настройки');
    } finally {
      setSaving(false);
    }
  };

  const handleUnblock = async (blockedUserId: number) => {
    try {
      await dispatch(unblockUser(blockedUserId)).unwrap();
      toast.success('Пользователь разблокирован');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось разблокировать');
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="modal-overlay" onClick={onClose}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="modal-content gold-outline gold-outline-thick w-full max-w-md mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-xl font-medium uppercase mb-6">
              Настройки мессенджера
            </h2>

            {/* Privacy setting */}
            <div className="mb-6">
              <label className="text-white/50 text-xs uppercase tracking-wider mb-2 block">
                Кто может писать вам
              </label>
              <div className="flex flex-col gap-2">
                {PRIVACY_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setPrivacy(option.value)}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-card transition-colors duration-200 ease-site cursor-pointer ${
                      privacy === option.value
                        ? 'bg-site-blue/15 border border-site-blue/30'
                        : 'bg-white/[0.04] border border-white/10 hover:bg-white/[0.06]'
                    }`}
                  >
                    <div
                      className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                        privacy === option.value
                          ? 'border-site-blue'
                          : 'border-white/30'
                      }`}
                    >
                      {privacy === option.value && (
                        <div className="w-2 h-2 rounded-full bg-site-blue" />
                      )}
                    </div>
                    <span className="text-white text-sm">{option.label}</span>
                  </button>
                ))}
              </div>

              <button
                onClick={handleSavePrivacy}
                disabled={saving}
                className="btn-blue !px-4 !py-1.5 !text-sm mt-3 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>

            {/* Blocked users */}
            <div className="mb-4">
              <label className="text-white/50 text-xs uppercase tracking-wider mb-2 block">
                Заблокированные пользователи
              </label>

              {blocks.length === 0 ? (
                <p className="text-white/30 text-sm py-3">
                  Нет заблокированных пользователей
                </p>
              ) : (
                <div className="max-h-[200px] overflow-y-auto gold-scrollbar border border-white/10 rounded-card">
                  {blocks.map((block) => (
                    <div
                      key={block.id}
                      className="flex items-center justify-between px-3 py-2.5 border-b border-white/5 last:border-b-0"
                    >
                      <span className="text-white text-sm truncate">
                        {block.blocked_username || `Пользователь #${block.blocked_user_id}`}
                      </span>
                      <button
                        onClick={() => handleUnblock(block.blocked_user_id)}
                        className="text-site-red text-xs hover:text-site-red/80 transition-colors duration-200 ease-site cursor-pointer flex-shrink-0 ml-2"
                      >
                        Разблокировать
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Close button */}
            <div className="flex justify-end mt-4">
              <button
                onClick={onClose}
                className="btn-line !px-4 !py-1.5 !text-sm"
              >
                Закрыть
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default MessengerSettings;
