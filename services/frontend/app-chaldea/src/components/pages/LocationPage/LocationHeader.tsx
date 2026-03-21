import { LocationData, MarkerType } from './types';

interface LocationHeaderProps {
  location: LocationData;
  isFavorited: boolean;
  onToggleFavorite: () => void;
}

const MARKER_LABELS: Record<MarkerType, string> = {
  safe: 'Безопасная',
  dangerous: 'Опасная',
  dungeon: 'Подземелье',
  farm: 'Фарм',
};

const MARKER_COLORS: Record<MarkerType, string> = {
  safe: 'bg-green-600/80 text-green-100',
  dangerous: 'bg-red-600/80 text-red-100',
  dungeon: 'bg-purple-600/80 text-purple-100',
  farm: 'bg-orange-500/80 text-orange-100',
};

const LocationHeader = ({ location, isFavorited, onToggleFavorite }: LocationHeaderProps) => {
  const markerType = (location.marker_type || 'safe') as MarkerType;
  const markerLabel = MARKER_LABELS[markerType] ?? markerType;
  const markerColor = MARKER_COLORS[markerType] ?? 'bg-white/20 text-white';

  return (
    <section className="flex flex-col items-center gap-4 sm:gap-6">
      {/* Location image */}
      <div
        className="gold-outline relative w-[120px] h-[120px] sm:w-[160px] sm:h-[160px] rounded-full overflow-hidden bg-black/40 shrink-0"
      >
        {location.image_url ? (
          <img
            src={location.image_url}
            alt={location.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-white/20">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 sm:w-16 sm:h-16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
        )}
      </div>

      {/* Name + Favorite */}
      <div className="flex items-center gap-2">
        <h1 className="gold-text text-xl sm:text-2xl font-medium uppercase text-center">
          {location.name}
        </h1>
        <button
          onClick={onToggleFavorite}
          className="shrink-0 p-1 transition-colors hover:scale-110 active:scale-95 transition-transform"
          aria-label={isFavorited ? 'Убрать из избранного' : 'Добавить в избранное'}
          title={isFavorited ? 'Убрать из избранного' : 'Добавить в избранное'}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className={`w-5 h-5 sm:w-6 sm:h-6 ${
              isFavorited ? 'text-gold' : 'text-white/40 hover:text-gold/70'
            }`}
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
        </button>
      </div>

      {/* Badges */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        {location.recommended_level > 0 && (
          <span className="gold-text text-sm font-medium px-3 py-1 rounded-full border border-gold-dark/50">
            {location.recommended_level}+ LVL
          </span>
        )}
        <span className={`text-xs font-medium px-3 py-1 rounded-full ${markerColor}`}>
          {markerLabel}
        </span>
      </div>

      {/* Description */}
      {location.description && (
        <p className="text-white/70 text-sm sm:text-base text-center max-w-2xl leading-relaxed">
          {location.description}
        </p>
      )}
    </section>
  );
};

export default LocationHeader;
