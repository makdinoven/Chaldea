import { useRef } from 'react';
import toast from 'react-hot-toast';
import { useAppSelector, useAppDispatch } from '../../../redux/store';
import {
  selectProfile,
  selectAvatarUploading,
  selectEquipmentSlots,
  uploadCharacterAvatar,
} from '../../../redux/slices/profileSlice';
import type { EquipmentSlotData } from '../../../redux/slices/profileSlice';
import EquipmentSlot from '../EquipmentPanel/EquipmentSlot';

const MAX_FILE_SIZE = 15 * 1024 * 1024; // 15 MB

const AvatarEquipmentGrid = () => {
  const dispatch = useAppDispatch();
  const profile = useAppSelector(selectProfile);
  const avatarUploading = useAppSelector(selectAvatarUploading);
  const equipmentSlots = useAppSelector(selectEquipmentSlots);
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const raceInfo = useAppSelector((state) => state.profile.raceInfo);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const getSlot = (slotType: string): EquipmentSlotData =>
    equipmentSlots.find((s) => s.slot_type === slotType) ?? {
      character_id: 0,
      slot_type: slotType,
      item_id: null,
      is_enabled: true,
      item: null,
    };

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
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

  return (
    <div className="flex flex-col items-center">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* CSS Grid: equipment slots surrounding avatar */}
      <div
        className="grid gap-1 lg:gap-1.5 place-items-center"
        style={{
          gridTemplateColumns: 'auto auto 1fr auto auto',
          gridTemplateRows: 'auto auto auto auto auto',
        }}
      >
        {/* Row 1: head in center */}
        <div className="col-start-3 row-start-1 flex justify-center">
          <EquipmentSlot slot={getSlot('head')} size="small" />
        </div>

        {/* Row 2: main_weapon left, avatar center-start, additional_weapons right */}
        <div className="col-start-1 row-start-2 flex items-center">
          <EquipmentSlot slot={getSlot('main_weapon')} size="small" />
        </div>
        <div
          className="col-start-2 col-span-3 row-start-2 row-span-3 flex items-center justify-center px-2 lg:px-4"
        >
          {/* Avatar */}
          <div
            className="gold-outline relative rounded-card w-[140px] h-[180px] lg:w-[180px] lg:h-[220px] overflow-hidden bg-black/30 cursor-pointer group shrink-0"
            onClick={handleAvatarClick}
          >
            {profile?.avatar ? (
              <img
                src={profile.avatar}
                alt={profile.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-white/20">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-16 h-16 lg:w-20 lg:h-20"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                  />
                </svg>
              </div>
            )}

            {!avatarUploading && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
                <span className="text-white text-sm font-medium text-center px-2">
                  Изменить фото
                </span>
              </div>
            )}

            {avatarUploading && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
              </div>
            )}
          </div>
        </div>
        <div className="col-start-5 row-start-2 flex items-center">
          <EquipmentSlot slot={getSlot('additional_weapons')} size="small" />
        </div>

        {/* Row 3: shield left, body right */}
        <div className="col-start-1 row-start-3 flex items-center">
          <EquipmentSlot slot={getSlot('shield')} size="small" />
        </div>
        <div className="col-start-5 row-start-3 flex items-center">
          <EquipmentSlot slot={getSlot('body')} size="small" />
        </div>

        {/* Row 4: ring left, cloak right */}
        <div className="col-start-1 row-start-4 flex items-center">
          <EquipmentSlot slot={getSlot('ring')} size="small" />
        </div>
        <div className="col-start-5 row-start-4 flex items-center">
          <EquipmentSlot slot={getSlot('cloak')} size="small" />
        </div>

        {/* Row 5: necklace left, belt center, bracelet right */}
        <div className="col-start-1 row-start-5 flex justify-center">
          <EquipmentSlot slot={getSlot('necklace')} size="small" />
        </div>
        <div className="col-start-3 row-start-5 flex justify-center">
          <EquipmentSlot slot={getSlot('belt')} size="small" />
        </div>
        <div className="col-start-5 row-start-5 flex justify-center">
          <EquipmentSlot slot={getSlot('bracelet')} size="small" />
        </div>
      </div>
    </div>
  );
};

export default AvatarEquipmentGrid;
