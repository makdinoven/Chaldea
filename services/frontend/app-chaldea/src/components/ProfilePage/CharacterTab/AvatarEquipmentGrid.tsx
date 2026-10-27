import { useState } from 'react';
import { useAppSelector, useAppDispatch } from '../../../redux/store';
import {
  selectProfile,
  selectAvatarUploading,
  selectEquipmentSlots,
  uploadCharacterAvatar,
} from '../../../redux/slices/profileSlice';
import type { EquipmentSlotData } from '../../../redux/slices/profileSlice';
import EquipmentSlot from '../EquipmentPanel/EquipmentSlot';
import AvatarEditor from '../../CommonComponents/AvatarEditor/AvatarEditor';

/**
 * Equipment diamond (FEAT-149 mock): portrait center, slots around —
 * head top-center; left column: main_weapon, body, ring, belt;
 * right column: additional_weapons, cloak, necklace, bracelet.
 * The 'shield' slot no longer exists (shields equip into additional_weapons).
 * Mobile (<lg): compressed 46px slots, max-w-[320px] centered.
 */
const AvatarEquipmentGrid = () => {
  const dispatch = useAppDispatch();
  const profile = useAppSelector(selectProfile);
  const avatarUploading = useAppSelector(selectAvatarUploading);
  const equipmentSlots = useAppSelector(selectEquipmentSlots);
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const raceInfo = useAppSelector((state) => state.profile.raceInfo);
  const [avatarEditor, setAvatarEditor] = useState(false);

  const getSlot = (slotType: string): EquipmentSlotData =>
    equipmentSlots.find((s) => s.slot_type === slotType) ?? {
      character_id: 0,
      slot_type: slotType,
      item_id: null,
      is_enabled: true,
      item: null,
    };

  return (
    <div className="w-full max-w-[320px] lg:max-w-none mx-auto">
      {avatarEditor && raceInfo?.id && userId && (
        <AvatarEditor
          title="Аватар персонажа"
          currentUrl={profile?.avatar}
          onClose={() => setAvatarEditor(false)}
          onUpload={(file, crop) =>
            dispatch(uploadCharacterAvatar({ characterId: raceInfo.id, userId, file, crop })).unwrap()}
          onReframe={(crop) =>
            dispatch(uploadCharacterAvatar({ characterId: raceInfo.id, userId, file: null, crop })).unwrap()}
        />
      )}

      {/* Diamond grid: 5 columns, portrait spans center cols 2-4 / rows 2-4 */}
      <div className="grid grid-cols-[46px_46px_1fr_46px_46px] lg:grid-cols-[60px_60px_1fr_60px_60px] gap-[9px] place-items-center">
        {/* Row 1: head top-center */}
        <div className="col-start-3 row-start-1">
          <EquipmentSlot slot={getSlot('head')} size="small" />
        </div>

        {/* Portrait — center, spans rows 2-4 */}
        <div className="col-start-2 col-span-3 row-start-2 row-span-3 w-full self-stretch flex items-center px-1 lg:px-2">
          <div
            className="gold-outline relative rounded-card w-full max-w-[236px] mx-auto aspect-square overflow-hidden bg-black/30 cursor-pointer group"
            onClick={() => setAvatarEditor(true)}
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

        {/* Row 2: main weapon left / additional weapons right */}
        <div className="col-start-1 row-start-2">
          <EquipmentSlot slot={getSlot('main_weapon')} size="small" />
        </div>
        <div className="col-start-5 row-start-2">
          <EquipmentSlot slot={getSlot('additional_weapons')} size="small" />
        </div>

        {/* Row 3: body left / cloak right */}
        <div className="col-start-1 row-start-3">
          <EquipmentSlot slot={getSlot('body')} size="small" />
        </div>
        <div className="col-start-5 row-start-3">
          <EquipmentSlot slot={getSlot('cloak')} size="small" />
        </div>

        {/* Row 4: ring left / necklace right */}
        <div className="col-start-1 row-start-4">
          <EquipmentSlot slot={getSlot('ring')} size="small" />
        </div>
        <div className="col-start-5 row-start-4">
          <EquipmentSlot slot={getSlot('necklace')} size="small" />
        </div>

        {/* Row 5: belt left / bracelet right */}
        <div className="col-start-1 row-start-5">
          <EquipmentSlot slot={getSlot('belt')} size="small" />
        </div>
        <div className="col-start-5 row-start-5">
          <EquipmentSlot slot={getSlot('bracelet')} size="small" />
        </div>
      </div>
    </div>
  );
};

export default AvatarEquipmentGrid;
