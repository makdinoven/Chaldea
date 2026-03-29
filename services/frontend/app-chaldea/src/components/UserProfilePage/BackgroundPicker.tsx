import { useEffect } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchMyBackgrounds,
  equipBackground,
  selectMyBackgrounds,
  selectActiveBackgroundSlug,
  selectCosmeticsLoading,
  selectCosmeticsError,
  clearCosmeticsError,
} from '../../redux/slices/cosmeticsSlice';
import type { UserCosmeticBackgroundItem, CosmeticRarity } from '../../types/cosmetics';
import MessageBackground from '../common/MessageBackground';

const RARITY_CONFIG: Record<CosmeticRarity, { label: string; color: string }> = {
  common: { label: 'Обычная', color: 'bg-white/60 text-black' },
  rare: { label: 'Редкая', color: 'bg-rarity-rare text-white' },
  epic: { label: 'Эпическая', color: 'bg-rarity-epic text-white' },
  legendary: { label: 'Легендарная', color: 'bg-rarity-legendary text-black' },
};

const BackgroundPicker = () => {
  const dispatch = useAppDispatch();
  const myBackgrounds = useAppSelector(selectMyBackgrounds);
  const activeSlug = useAppSelector(selectActiveBackgroundSlug);
  const loading = useAppSelector(selectCosmeticsLoading);
  const error = useAppSelector(selectCosmeticsError);

  useEffect(() => {
    dispatch(fetchMyBackgrounds());
  }, [dispatch]);

  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearCosmeticsError());
    }
  }, [error, dispatch]);

  const handleSelect = (slug: string | null) => {
    if (slug === activeSlug) return;
    dispatch(equipBackground(slug));
  };

  const isActive = (slug: string | null) =>
    slug === activeSlug || (slug === null && activeSlug === null);

  return (
    <div>
      <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
        Подложка сообщений
      </h3>

      {loading && myBackgrounds.length === 0 && (
        <p className="text-white/40 text-sm">Загрузка...</p>
      )}

      {!loading && myBackgrounds.length === 0 && (
        <p className="text-white/40 text-sm">
          Нет доступных подложек. Получите их в батл пассе!
        </p>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {/* Default / no background option */}
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
          {/* Sample message bubble with no background */}
          <div className="w-full rounded-lg bg-white/[0.06] border border-white/[0.08] px-3 py-2 min-h-[48px] flex items-center">
            <span className="text-white/60 text-xs">Пример сообщения</span>
          </div>
          <span className="text-white text-xs">Стандартная</span>
        </button>

        {/* Unlocked backgrounds */}
        {myBackgrounds.map((bg: UserCosmeticBackgroundItem) => {
          const rarity = RARITY_CONFIG[bg.rarity];
          return (
            <button
              key={bg.slug}
              type="button"
              onClick={() => handleSelect(bg.slug)}
              disabled={loading}
              className={`flex flex-col items-center gap-2 p-3 rounded-card transition-all duration-200 ease-site relative ${
                isActive(bg.slug)
                  ? 'gold-outline gold-outline-thick bg-white/10'
                  : 'bg-white/[0.03] hover:bg-white/[0.06] border border-white/10'
              } ${loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
            >
              {/* Rarity badge */}
              <span
                className={`absolute top-1 right-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full leading-none z-10 ${rarity.color}`}
              >
                {rarity.label}
              </span>

              {/* Sample message bubble with this background */}
              <MessageBackground
                backgroundSlug={bg.slug}
                className="w-full rounded-lg border border-white/[0.08] px-3 py-2 min-h-[48px] flex items-center"
              >
                <span className="text-white/60 text-xs">Пример сообщения</span>
              </MessageBackground>

              <span className="text-white text-xs text-center leading-tight mt-1">
                {bg.name}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default BackgroundPicker;
