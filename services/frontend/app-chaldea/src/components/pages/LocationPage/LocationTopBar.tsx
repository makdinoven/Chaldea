import { LocationData } from './types';

interface LocationTopBarProps {
  location: LocationData;
  isFavorited: boolean;
  onToggleFavorite: () => void;
  onBack: () => void;
}

/**
 * Top bar of the location page (FEAT-152): back button, plain-text
 * breadcrumb (Country / Region / District / Location — segments with no
 * data are hidden) and the labeled favorite toggle (A8).
 * Breadcrumb segments are intentionally NOT links — the app has no client
 * routes for countries/regions/districts (§3.1).
 */
const LocationTopBar = ({
  location,
  isFavorited,
  onToggleFavorite,
  onBack,
}: LocationTopBarProps) => {
  const parentSegments = [
    location.country_name,
    location.region_name,
    location.district_name,
  ].filter((s): s is string => Boolean(s));

  return (
    <div className="flex items-center justify-between gap-3 sm:gap-4 flex-wrap">
      <div className="flex items-center gap-3 sm:gap-4 min-w-0">
        {/* Back button */}
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 shrink-0 px-3.5 py-2 rounded-card bg-site-bg border border-white/10 text-white/70 hover:text-white hover:border-gold-dark/60 text-sm transition-all duration-200 ease-site"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 18l-6-6 6-6" />
          </svg>
          Назад
        </button>

        {/* Breadcrumb — plain text, missing segments hidden */}
        <nav
          aria-label="Расположение локации"
          className="flex items-center gap-2 min-w-0 text-xs tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis"
        >
          {parentSegments.map((segment) => (
            <span key={segment} className="flex items-center gap-2 min-w-0">
              <span className="text-white/55 truncate">{segment}</span>
              <span className="text-white/25">/</span>
            </span>
          ))}
          <span className="text-gold font-medium truncate">{location.name}</span>
        </nav>
      </div>

      {/* Favorite — labeled button (A8) */}
      <button
        type="button"
        onClick={onToggleFavorite}
        aria-label={isFavorited ? 'Убрать из избранного' : 'Добавить в избранное'}
        title={isFavorited ? 'Убрать из избранного' : 'Добавить в избранное'}
        className={`flex items-center gap-2 shrink-0 px-3.5 py-2 rounded-card bg-site-bg border text-sm transition-all duration-200 ease-site ${
          isFavorited
            ? 'border-gold-dark/70 text-gold'
            : 'border-white/10 text-white/70 hover:text-gold hover:border-gold-dark/60'
        }`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-4 h-4 shrink-0"
          viewBox="0 0 24 24"
          fill={isFavorited ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
          />
        </svg>
        <span>{isFavorited ? 'В избранном' : 'В избранное'}</span>
      </button>
    </div>
  );
};

export default LocationTopBar;
