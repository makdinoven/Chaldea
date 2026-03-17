import { useRef } from 'react';
import toast from 'react-hot-toast';
import { useAppSelector, useAppDispatch } from '../../../redux/store';
import {
  selectProfile,
  selectRaceInfo,
  selectAvatarUploading,
  uploadCharacterAvatar,
} from '../../../redux/slices/profileSlice';
import { RACE_NAMES, CLASS_NAMES } from '../constants';
import goldCoinsIcon from '../../../assets/icons/gold-coins.svg';

const MAX_FILE_SIZE = 15 * 1024 * 1024; // 15 MB

export default function CharacterCard() {
  const dispatch = useAppDispatch();
  const profile = useAppSelector(selectProfile);
  const raceInfo = useAppSelector(selectRaceInfo);
  const avatarUploading = useAppSelector(selectAvatarUploading);
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset input so the same file can be re-selected
    e.target.value = '';

    if (file.size > MAX_FILE_SIZE) {
      toast.error('Файл слишком большой. Максимальный размер: 15 МБ');
      return;
    }

    if (!raceInfo?.id || !userId) return;

    try {
      await dispatch(
        uploadCharacterAvatar({ characterId: raceInfo.id, userId, file }),
      ).unwrap();
      toast.success('Аватарка обновлена');
    } catch (err) {
      const message = typeof err === 'string' ? err : 'Не удалось загрузить аватарку';
      toast.error(message);
    }
  };

  if (!profile) {
    return (
      <div className="flex flex-col items-center gap-3 p-4">
        <div className="w-[180px] h-[220px] rounded-card bg-white/5 animate-pulse" />
        <div className="h-6 w-32 bg-white/5 rounded animate-pulse" />
      </div>
    );
  }

  const raceName = raceInfo ? (RACE_NAMES[raceInfo.id_race] ?? 'Неизвестная раса') : '—';
  const className = raceInfo ? (CLASS_NAMES[raceInfo.id_class] ?? 'Неизвестный класс') : '—';

  return (
    <div className="flex flex-col items-center gap-3 p-4">
      {/* Portrait / Avatar */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />
      <div
        className="gold-outline relative rounded-card w-[180px] h-[220px] overflow-hidden bg-black/30 cursor-pointer group"
        onClick={handleAvatarClick}
      >
        {profile.avatar ? (
          <img
            src={profile.avatar}
            alt={profile.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-white/20">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-20 h-20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
        )}

        {/* Hover overlay */}
        {!avatarUploading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
            <span className="text-white text-sm font-medium text-center px-2">
              Изменить фото
            </span>
          </div>
        )}

        {/* Loading spinner overlay */}
        {avatarUploading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60">
            <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* Name */}
      <h3 className="gold-text text-xl font-medium uppercase text-center">
        {profile.name}
      </h3>

      {/* Active Title */}
      {profile.active_title && (
        <span className="text-site-blue text-sm italic text-center">
          {profile.active_title}
        </span>
      )}

      {/* Race / Class */}
      <div className="flex items-center gap-2 text-sm text-white/80">
        <span>{raceName}</span>
        <span className="text-white/30">|</span>
        <span>{className}</span>
      </div>

      {/* Level + Progress Bar */}
      <div className="w-[210px] flex flex-col gap-[10px]">
        <div className="flex justify-between items-end">
          <span className="gold-text text-base font-medium uppercase">
            LVL {profile.level}
          </span>
          <span className="text-white text-sm font-medium uppercase text-right">
            {Math.round(profile.level_progress?.current_exp_in_level ?? 0)}
            /{Math.round(profile.level_progress?.exp_to_next_level ?? 0)}
          </span>
        </div>
        <div className="stat-bar">
          <div
            className="stat-bar-fill"
            style={{
              width: `${Math.min((profile.level_progress?.progress_fraction ?? 0) * 100, 100)}%`,
              background: 'linear-gradient(176.46deg, #FFF9B8 2.91%, #BCAB4C 237.31%)',
            }}
          />
        </div>
      </div>

      {/* Stat Points */}
      <div className="flex items-center gap-2">
        <span className="gold-text text-base font-medium uppercase">
          Очки прокачки
        </span>
        <div className="flex items-center gap-1">
          <div className="skill-point-dot" />
          <span className="text-site-blue text-sm font-medium">
            {profile.stat_points}
          </span>
        </div>
      </div>

      {/* Currency */}
      <div className="flex items-center gap-2 mt-1">
        <img src={goldCoinsIcon} alt="" className="w-5 h-5" />
        <span className="gold-text text-sm font-medium">
          {profile.currency_balance.toLocaleString('ru-RU')}
        </span>
      </div>
    </div>
  );
}
