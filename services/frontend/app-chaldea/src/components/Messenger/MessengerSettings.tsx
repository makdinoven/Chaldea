import { useState, useEffect } from 'react';
import ModalShell from '../CommonComponents/ModalShell/ModalShell';
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
    <ModalShell
      open={isOpen}
      onClose={onClose}
      title="Настройки мессенджера"
      size="sm"
      footer={
        <button onClick={onClose} className="btn-line !text-sm w-full sm:w-auto">
          Закрыть
        </button>
      }
    >
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
            <div>
              <label className="text-white/50 text-xs uppercase tracking-wider mb-2 block">
                Заблокированные пользователи
              </label>

              {blocks.length === 0 ? (
                <p className="text-white/30 text-sm py-3">
                  Нет заблокированных пользователей
                </p>
              ) : (
                <div className="border border-white/10 rounded-card">
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

    </ModalShell>
  );
};

export default MessengerSettings;
