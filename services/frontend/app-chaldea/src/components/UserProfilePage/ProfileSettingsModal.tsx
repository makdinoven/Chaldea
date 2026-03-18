import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X } from 'react-feather';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  updateProfileSettings,
  updateUsername,
  uploadProfileBackground,
  deleteProfileBackground,
  selectSettingsUpdating,
  type UserProfile,
} from '../../redux/slices/userProfileSlice';
import ColorPicker from '../common/ColorPicker';
import AvatarFramePreview from './AvatarFramePreview';
import type { AvatarFrame } from './AvatarFramePreview';
import BackgroundPositionPicker from './BackgroundPositionPicker';

export const AVATAR_FRAMES = [
  { id: 'gold', label: 'Золотая', borderStyle: '3px solid #f0d95c', shadow: '0 0 12px rgba(240, 217, 92, 0.4)' },
  { id: 'silver', label: 'Серебряная', borderStyle: '3px solid #c0c0c0', shadow: '0 0 12px rgba(192, 192, 192, 0.4)' },
  { id: 'fire', label: 'Огненная', borderStyle: '3px solid #ff6347', shadow: '0 0 15px rgba(255, 99, 71, 0.5)' },
] as const;

const NO_FRAME: AvatarFrame = { id: 'none', label: 'Нет рамки', borderStyle: 'none', shadow: 'none' };

const MAX_FILE_SIZE = 15 * 1024 * 1024;
const MAX_STATUS_LENGTH = 100;

interface ProfileSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  profile: UserProfile;
}

const ProfileSettingsModal = ({ isOpen, onClose, profile }: ProfileSettingsModalProps) => {
  const dispatch = useAppDispatch();
  const settingsUpdating = useAppSelector(selectSettingsUpdating);

  const [bgColor, setBgColor] = useState(profile.profile_bg_color ?? '');
  const [nicknameColor, setNicknameColor] = useState(profile.nickname_color ?? '');
  const [avatarFrame, setAvatarFrame] = useState(profile.avatar_frame ?? 'none');
  const [effectColor, setEffectColor] = useState(profile.avatar_effect_color ?? '');
  const [statusText, setStatusText] = useState(profile.status_text ?? '');
  const [bgPosition, setBgPosition] = useState(profile.profile_bg_position ?? '50% 50%');
  const [newUsername, setNewUsername] = useState(profile.username);
  const [usernameError, setUsernameError] = useState<string | null>(null);

  const bgFileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setBgColor(profile.profile_bg_color ?? '');
      setNicknameColor(profile.nickname_color ?? '');
      setAvatarFrame(profile.avatar_frame ?? 'none');
      setEffectColor(profile.avatar_effect_color ?? '');
      setStatusText(profile.status_text ?? '');
      setBgPosition(profile.profile_bg_position ?? '50% 50%');
      setNewUsername(profile.username);
      setUsernameError(null);
    }
  }, [isOpen, profile]);

  const handleSave = async () => {
    try {
      await dispatch(
        updateProfileSettings({
          userId: profile.id,
          settings: {
            profile_bg_color: bgColor || null,
            nickname_color: nicknameColor || null,
            avatar_frame: avatarFrame === 'none' ? null : avatarFrame,
            avatar_effect_color: effectColor || null,
            status_text: statusText || null,
            profile_bg_position: profile.profile_bg_image ? bgPosition : null,
          },
        }),
      ).unwrap();
      toast.success('Настройки сохранены');
      onClose();
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось сохранить настройки');
    }
  };

  const handleUsernameChange = async () => {
    const trimmed = newUsername.trim();
    if (!trimmed) {
      setUsernameError('Никнейм не может быть пустым');
      return;
    }
    if (trimmed === profile.username) {
      setUsernameError('Никнейм не изменился');
      return;
    }
    setUsernameError(null);
    try {
      await dispatch(updateUsername({ userId: profile.id, username: trimmed })).unwrap();
      toast.success('Никнейм изменён');
    } catch (err) {
      const errorMsg = typeof err === 'string' ? err : 'Не удалось изменить никнейм';
      setUsernameError(errorMsg);
      toast.error(errorMsg);
    }
  };

  const handleBgUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    if (file.size > MAX_FILE_SIZE) {
      toast.error('Файл слишком большой. Максимальный размер: 15 МБ');
      return;
    }

    try {
      await dispatch(uploadProfileBackground({ userId: profile.id, file })).unwrap();
      toast.success('Фон профиля обновлён');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось загрузить фон');
    }
  };

  const handleBgDelete = async () => {
    try {
      await dispatch(deleteProfileBackground(profile.id)).unwrap();
      toast.success('Фон профиля удалён');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось удалить фон');
    }
  };

  const selectedFrame: AvatarFrame =
    AVATAR_FRAMES.find((f) => f.id === avatarFrame) ?? NO_FRAME;

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="modal-overlay" onClick={onClose}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="modal-content gold-outline gold-outline-thick relative w-full max-w-[520px] max-h-[85vh] overflow-y-auto gold-scrollbar"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <h2 className="gold-text text-2xl font-medium uppercase">Настройки профиля</h2>
              <button
                onClick={onClose}
                className="text-white/50 hover:text-white transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <div className="flex flex-col gap-6">
              {/* Section: Background color */}
              <div>
                <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                  Цвет подложки
                </h3>
                <ColorPicker color={bgColor || '#232329'} onChange={setBgColor} />
                <button
                  type="button"
                  onClick={() => setBgColor('')}
                  className="mt-2 text-white/40 text-xs hover:text-site-blue transition-colors"
                >
                  Сбросить
                </button>
              </div>

              {/* Section: Background image */}
              <div>
                <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                  Фон профиля
                </h3>
                <input
                  ref={bgFileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleBgUpload}
                />
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => bgFileInputRef.current?.click()}
                    className="btn-blue text-sm"
                    disabled={settingsUpdating}
                  >
                    Загрузить фон
                  </button>
                  {profile.profile_bg_image && (
                    <button
                      type="button"
                      onClick={handleBgDelete}
                      className="text-site-red text-sm hover:text-white transition-colors"
                      disabled={settingsUpdating}
                    >
                      Удалить фон
                    </button>
                  )}
                </div>
                {profile.profile_bg_image && (
                  <div className="mt-3">
                    <BackgroundPositionPicker
                      imageUrl={profile.profile_bg_image}
                      position={bgPosition}
                      onChange={setBgPosition}
                    />
                  </div>
                )}
              </div>

              {/* Section: Username */}
              <div>
                <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                  Никнейм
                </h3>
                <div className="flex items-end gap-3">
                  <div className="flex-1">
                    <input
                      type="text"
                      value={newUsername}
                      onChange={(e) => {
                        setNewUsername(e.target.value);
                        setUsernameError(null);
                      }}
                      className="input-underline w-full"
                      placeholder="Новый никнейм"
                      maxLength={32}
                    />
                    {usernameError && (
                      <p className="text-site-red text-xs mt-1">{usernameError}</p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleUsernameChange}
                    className="btn-line text-sm whitespace-nowrap"
                    disabled={settingsUpdating}
                  >
                    Изменить
                  </button>
                </div>
              </div>

              {/* Section: Nickname color */}
              <div>
                <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                  Цвет никнейма
                </h3>
                <ColorPicker color={nicknameColor || '#f0d95c'} onChange={setNicknameColor} />
                <button
                  type="button"
                  onClick={() => setNicknameColor('')}
                  className="mt-2 text-white/40 text-xs hover:text-site-blue transition-colors"
                >
                  Сбросить
                </button>
              </div>

              {/* Section: Avatar frame */}
              <div>
                <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                  Рамка аватарки
                </h3>
                <div className="flex flex-wrap gap-4">
                  {/* No frame option */}
                  <button
                    type="button"
                    onClick={() => setAvatarFrame('none')}
                    className={`flex flex-col items-center gap-2 p-2 rounded-card transition-all ${
                      avatarFrame === 'none'
                        ? 'bg-white/10'
                        : 'hover:bg-white/5'
                    }`}
                  >
                    <AvatarFramePreview avatarUrl={profile.avatar} frame={NO_FRAME} />
                    <span className="text-white text-xs">Нет рамки</span>
                  </button>
                  {AVATAR_FRAMES.map((frame) => (
                    <button
                      key={frame.id}
                      type="button"
                      onClick={() => setAvatarFrame(frame.id)}
                      className={`flex flex-col items-center gap-2 p-2 rounded-card transition-all ${
                        avatarFrame === frame.id
                          ? 'bg-white/10'
                          : 'hover:bg-white/5'
                      }`}
                    >
                      <AvatarFramePreview avatarUrl={profile.avatar} frame={frame} />
                      <span className="text-white text-xs">{frame.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Section: Avatar effect color */}
              <div>
                <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                  Эффект аватарки
                </h3>
                <ColorPicker color={effectColor || '#f0d95c'} onChange={setEffectColor} />
                <button
                  type="button"
                  onClick={() => setEffectColor('')}
                  className="mt-2 text-white/40 text-xs hover:text-site-blue transition-colors"
                >
                  Сбросить
                </button>
              </div>

              {/* Section: Status text */}
              <div>
                <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                  Статус
                </h3>
                <input
                  type="text"
                  value={statusText}
                  onChange={(e) => {
                    if (e.target.value.length <= MAX_STATUS_LENGTH) {
                      setStatusText(e.target.value);
                    }
                  }}
                  className="input-underline w-full"
                  placeholder="Введите статус / девиз"
                  maxLength={MAX_STATUS_LENGTH}
                />
                <p className="text-white/30 text-xs mt-1 text-right">
                  {statusText.length}/{MAX_STATUS_LENGTH}
                </p>
              </div>

              {/* Save button */}
              <button
                type="button"
                onClick={handleSave}
                className="btn-blue w-full"
                disabled={settingsUpdating}
              >
                {settingsUpdating ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default ProfileSettingsModal;
