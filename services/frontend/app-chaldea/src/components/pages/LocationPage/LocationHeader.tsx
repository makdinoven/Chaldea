import { ReactNode } from 'react';
import { LocationData, MarkerType } from './types';
import { hasRecommendedLevel } from '../../../utils/recommendedLevel';

interface LocationHeaderProps {
  location: LocationData;
  /** Right-hand inset panel of the hero body (FEAT-153 §3.2 — «Соседние локации»). */
  aside?: ReactNode;
}

const MARKER_LABELS: Record<MarkerType, string> = {
  safe: 'Безопасная',
  dangerous: 'Опасная',
  dungeon: 'Подземелье',
  farm: 'Фарм',
};

const MARKER_COLORS: Record<MarkerType, string> = {
  safe: 'bg-green-600/80 text-green-100 border-green-300/40',
  dangerous: 'bg-red-600/80 text-red-100 border-red-300/40',
  dungeon: 'bg-purple-600/80 text-purple-100 border-purple-300/40',
  farm: 'bg-orange-500/80 text-orange-100 border-orange-300/40',
};

/**
 * Head panel of the location page: marker + level badges, title, description
 * and the meta row (players here / posts / region — A6). Favorite toggle and
 * «Скрыть интерфейс» live in LocationTopBar (A8).
 *
 * A translucent panel like every other block on the page. It used to carry the
 * location art as well, but the same art is already the page background, and
 * two copies of one picture at two different sizes clashed.
 *
 * FEAT-153 §3.2: from `lg` the body is a flex row — free text on the left, the
 * optional `aside` panel («Соседние локации») as a full-body-height column on
 * the right. The card is as tall as its text, up to 400px; a longer neighbour
 * list scrolls inside it. Below `lg` the body stacks.
 */
const LocationHeader = ({ location, aside }: LocationHeaderProps) => {
  const markerType = (location.marker_type || 'safe') as MarkerType;
  const markerLabel = MARKER_LABELS[markerType] ?? markerType;
  const markerColor =
    MARKER_COLORS[markerType] ?? 'bg-white/20 text-white border-white/20';

  const playersCount = location.players.length;
  const postsCount = location.posts.length;

  return (
    <section className="relative h-auto lg:max-h-[400px] rounded-card overflow-hidden bg-site-bg backdrop-blur-sm border border-gold-dark/20 shadow-card flex flex-col">
      {/* Badges — top left */}
      <div className="absolute top-4 left-4 sm:top-5 sm:left-6 flex items-center gap-2.5 flex-wrap">
        <span
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[11px] font-medium uppercase tracking-[0.06em] shadow-card ${markerColor}`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-3.5 h-3.5 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4m0 4h.01"
            />
          </svg>
          {markerLabel}
        </span>
        {hasRecommendedLevel(location.recommended_level) && (
          <span className="px-3 py-1.5 rounded-full bg-site-bg border border-gold-dark/60 text-gold text-[11px] font-medium tracking-[0.06em]">
            {location.recommended_level}+ LVL
          </span>
        )}
      </div>

      {/* Body — free text (left) + optional inset panel (right) */}
      <div className="relative flex-1 min-h-0 flex flex-col lg:flex-row gap-4 lg:gap-6 px-4 pb-5 pt-16 sm:px-8 sm:pb-7">
        <div className="flex-1 min-w-0 flex flex-col gap-2.5 sm:gap-3">
          <h1
            className="text-white text-3xl sm:text-5xl font-medium uppercase leading-tight"
            style={{ textShadow: '0 6px 26px rgba(0,0,0,.8)' }}
          >
            {location.name}
          </h1>

          {location.description && (
            <p
              className="max-w-2xl text-white/80 text-sm sm:text-[15px] font-light leading-relaxed break-words"
              style={{ textShadow: '0 2px 10px rgba(0,0,0,.8)' }}
            >
              {location.description}
            </p>
          )}

          {/* Meta row (A6) */}
          <div className="flex items-center gap-4 sm:gap-6 mt-1 flex-wrap text-xs sm:text-[12.5px] text-white/75">
            <span className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-stat-energy shadow-[0_0_8px_#88B332] animate-pulse" />
              <b className="text-white font-medium">{playersCount}</b>
              {' '}игроков сейчас здесь
            </span>
            <span className="flex items-center gap-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-4 h-4 text-site-blue shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
                />
              </svg>
              <b className="text-white font-medium">{postsCount}</b>
              {' '}постов
            </span>
            {location.region_name && (
              <span className="flex items-center gap-2">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4 text-gold shrink-0"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"
                  />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                Регион{' '}
                <b className="text-white font-medium">{location.region_name}</b>
              </span>
            )}
          </div>
        </div>

        {aside}
      </div>
    </section>
  );
};

export default LocationHeader;
