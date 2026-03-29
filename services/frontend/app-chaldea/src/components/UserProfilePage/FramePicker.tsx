import { useEffect } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchMyFrames,
  equipFrame,
  selectMyFrames,
  selectActiveFrameSlug,
  selectCosmeticsLoading,
  selectCosmeticsError,
  clearCosmeticsError,
} from '../../redux/slices/cosmeticsSlice';
import type { UserCosmeticItem, CosmeticRarity } from '../../types/cosmetics';
import AvatarWithFrame from '../common/AvatarWithFrame';

interface FramePickerProps {
  avatarUrl: string | null;
}

const RARITY_CONFIG: Record<CosmeticRarity, { label: string; color: string }> = {
  common: { label: 'Обычная', color: 'bg-white/60 text-black' },
  rare: { label: 'Редкая', color: 'bg-rarity-rare text-white' },
  epic: { label: 'Эпическая', color: 'bg-rarity-epic text-white' },
  legendary: { label: 'Легендарная', color: 'bg-rarity-legendary text-black' },
};

const FramePicker = ({ avatarUrl }: FramePickerProps) => {
  const dispatch = useAppDispatch();
  const myFrames = useAppSelector(selectMyFrames);
  const activeSlug = useAppSelector(selectActiveFrameSlug);
  const loading = useAppSelector(selectCosmeticsLoading);
  const error = useAppSelector(selectCosmeticsError);

  useEffect(() => {
    dispatch(fetchMyFrames());
  }, [dispatch]);

  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearCosmeticsError());
    }
  }, [error, dispatch]);

  const handleSelect = (slug: string | null) => {
    if (slug === activeSlug) return;
    dispatch(equipFrame(slug));
  };

  const isActive = (slug: string | null) =>
    slug === activeSlug || (slug === null && activeSlug === null);

  return (
    <div>
      <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
        Рамка аватара
      </h3>

      {loading && myFrames.length === 0 && (
        <p className="text-white/40 text-sm">Загрузка...</p>
      )}

      {!loading && myFrames.length === 0 && (
        <p className="text-white/40 text-sm">
          Нет доступных рамок. Получите их в батл пассе!
        </p>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {/* No frame option */}
        <button
          type="button"
          onClick={() => handleSelect(null)}
          disabled={loading}
          className={`flex flex-col items-center gap-2 p-3 rounded-card transition-all duration-200 ease-site relative ${
            isActive(null)
              ? 'gold-outline gold-outline-thick bg-white/10'
              : 'bg-white/[0.03] hover:bg-white/[0.06] border border-white/10'
          } ${loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
        >
          <AvatarWithFrame
            avatarUrl={avatarUrl}
            frameSlug={null}
            pixelSize={56}
            rounded="full"
          />
          <span className="text-white text-xs">Без рамки</span>
        </button>

        {/* Unlocked frames */}
        {myFrames.map((frame: UserCosmeticItem) => {
          const rarity = RARITY_CONFIG[frame.rarity];
          return (
            <button
              key={frame.slug}
              type="button"
              onClick={() => handleSelect(frame.slug)}
              disabled={loading}
              className={`flex flex-col items-center gap-2 p-3 rounded-card transition-all duration-200 ease-site relative ${
                isActive(frame.slug)
                  ? 'gold-outline gold-outline-thick bg-white/10'
                  : 'bg-white/[0.03] hover:bg-white/[0.06] border border-white/10'
              } ${loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
            >
              {/* Rarity badge */}
              <span
                className={`absolute top-1 right-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full leading-none ${rarity.color}`}
              >
                {rarity.label}
              </span>

              <AvatarWithFrame
                avatarUrl={avatarUrl}
                frameSlug={frame.slug}
                pixelSize={56}
                rounded="full"
              />
              <span className="text-white text-xs text-center leading-tight mt-1">
                {frame.name}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default FramePicker;
