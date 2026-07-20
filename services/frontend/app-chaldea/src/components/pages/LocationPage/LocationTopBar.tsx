import { Link } from 'react-router-dom';
import { LocationData } from './types';

interface LocationTopBarProps {
  location: LocationData;
  isFavorited: boolean;
  onToggleFavorite: () => void;
  onBack: () => void;
}

/**
 * A breadcrumb segment. `to === null` renders as plain text — used both for
 * the district (no route) and defensively when a name arrives without its id,
 * so a missing id can never produce a dead link.
 */
type Crumb = { label: string; to: string | null };

/**
 * Top bar of the location page: back button, breadcrumb
 * (Country / Region / District / Location — segments with no data are hidden)
 * and the labeled favorite toggle (A8).
 *
 * Breadcrumb navigation (FEAT-153 §3.8): the country and region segments link
 * into `WorldPage` via the pre-existing `world/country/:countryId` and
 * `world/region/:regionId` routes (`App.tsx:120-121`). The district segment is
 * plain text — no district route exists and creating one was declined as out of
 * scope. The current location is plain text because you are already there.
 */
const LocationTopBar = ({
  location,
  isFavorited,
  onToggleFavorite,
  onBack,
}: LocationTopBarProps) => {
  const crumbs: Crumb[] = [
    location.country_name
      ? {
          label: location.country_name,
          to: location.country_id ? `/world/country/${location.country_id}` : null,
        }
      : null,
    location.region_name
      ? {
          label: location.region_name,
          to: location.region_id ? `/world/region/${location.region_id}` : null,
        }
      : null,
    location.district_name ? { label: location.district_name, to: null } : null,
  ].filter((c): c is Crumb => c !== null);

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

        {/* Breadcrumb — ancestors link into WorldPage, missing segments hidden.
            The row wraps instead of truncating so every link stays tappable. */}
        <nav
          aria-label="Расположение локации"
          className="flex items-center gap-2 min-w-0 flex-wrap text-xs tracking-[0.04em]"
        >
          {crumbs.map((crumb, index) => (
            <span
              key={`${index}-${crumb.label}`}
              className="flex items-center gap-2 min-w-0"
            >
              {crumb.to ? (
                <Link
                  to={crumb.to}
                  className="site-link text-white/70 hover:text-site-blue truncate max-w-[110px] transition-colors duration-200 ease-site"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span className="text-white/55 truncate max-w-[110px]">{crumb.label}</span>
              )}
              <span className="text-white/25 shrink-0">/</span>
            </span>
          ))}
          <span className="text-gold font-medium shrink-0">{location.name}</span>
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
