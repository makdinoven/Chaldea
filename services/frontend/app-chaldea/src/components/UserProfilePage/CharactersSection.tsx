import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { User } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  loadUserCharacters,
  selectUserCharacters,
  selectCharactersLoading,
  selectUserProfile,
  UserCharacterItem,
} from '../../redux/slices/userProfileSlice';
import { buildColorEffectStyle } from './ProfileSettingsModal';
import { formatServerDate } from '../../utils/serverDate';

/** Mapping race IDs to Tailwind ring colors */
const RACE_BORDER_COLORS: Record<number, string> = {
  1: 'ring-blue-400',       // Люди — blue
  2: 'ring-emerald-400',    // Эльфы — emerald
  3: 'ring-red-500',        // Орки — red
  4: 'ring-amber-400',      // Дварфы — amber
  5: 'ring-purple-400',     // Тифлинги — purple
  6: 'ring-cyan-400',       // Полуэльфы — cyan
  7: 'ring-orange-400',     // Полуорки — orange
  8: 'ring-pink-400',       // Гномы — pink
  9: 'ring-indigo-400',     // Полурослики — indigo
  10: 'ring-teal-400',      // Драконорождённые — teal
};

const DEFAULT_RING_COLOR = 'ring-white/30';

const getRingColor = (raceId: number | null | undefined): string => {
  if (raceId == null) return DEFAULT_RING_COLOR;
  return RACE_BORDER_COLORS[raceId] ?? DEFAULT_RING_COLOR;
};

const getRarityColorClass = (rarity?: string | null): string => {
  switch (rarity) {
    case 'common': return 'text-rarity-common';
    case 'rare': return 'text-rarity-rare';
    case 'legendary': return 'text-rarity-legendary';
    default: return 'text-site-blue';
  }
};

/** Truncate class name if too long for the badge */
const formatClassName = (name: string): string => {
  if (name.length <= 6) return name;
  return name.slice(0, 5) + '.';
};

interface CharactersSectionProps {
  profileUserId: number;
}

interface CharacterCardProps {
  char: UserCharacterItem;
  /**
   * `true` only when this card is the viewer's OWN active character — the only
   * case where `/profile` actually shows this character.
   */
  isOwnActive: boolean;
}

const CharacterCard = ({ char, isOwnActive }: CharacterCardProps) => {
  const ringColor = getRingColor(char.id_race);

  const content = (
    <>
      {/* Avatar container with badges */}
      <div className="relative">
        {/* Class badge — top-right */}
        {char.class_name && (
          <div className="absolute -top-1 -right-1 z-20 px-1.5 py-0.5 rounded-full bg-black/70 backdrop-blur-sm text-[10px] font-medium text-white/90 leading-tight whitespace-nowrap max-w-[60px] truncate">
            {formatClassName(char.class_name)}
          </div>
        )}

        {/* Avatar circle */}
        <div
          className={`
            w-[100px] h-[100px]
            sm:w-[120px] sm:h-[120px]
            rounded-full relative overflow-hidden
            bg-black/30 flex items-center justify-center
            ring-2 ${ringColor}
            group-hover:shadow-hover transition-shadow
          `}
        >
          {char.avatar ? (
            <img
              src={char.avatar}
              alt={char.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <User size={40} className="text-white/20" />
          )}
        </div>

        {/* Level badge — bottom-right */}
        {char.level != null && (
          <div className="absolute -bottom-1 -right-1 z-20 w-7 h-7 rounded-full bg-black/80 border border-white/20 flex items-center justify-center">
            <span className="text-xs font-bold gold-text leading-none">
              {char.level}
            </span>
          </div>
        )}
      </div>

      {/* Character info */}
      <div className="flex flex-col items-center gap-0.5 text-center">
        <span className="text-white text-sm font-medium group-hover:text-site-blue transition-colors">
          {char.name}
        </span>
        {char.active_title && (
          <span className={`text-[10px] sm:text-xs ${getRarityColorClass(char.active_title_rarity)}`}>
            {char.active_title}
          </span>
        )}
        {char.race_name && (
          <span className="text-white/50 text-xs">
            {char.race_name}
            {char.subrace_name ? ` (${char.subrace_name})` : ''}
          </span>
        )}
        <span className="text-white/40 text-xs">
          {char.rp_posts_count} {char.rp_posts_count === 1 ? 'пост' : 'постов'}
        </span>
        <span className="text-white/30 text-xs">
          {char.last_rp_post_date
            ? formatServerDate(char.last_rp_post_date, {})
            : 'Нет данных'}
        </span>
      </div>
    </>
  );

  // TODO(FEAT-172): link to /character/:id once the public profile page exists.
  // Until then only the viewer's own active character has a page to open —
  // every other card stays non-interactive instead of silently opening
  // the viewer's own profile.
  if (isOwnActive) {
    return (
      <Link to="/profile" className="flex flex-col items-center gap-2 group">
        {content}
      </Link>
    );
  }

  return <div className="flex flex-col items-center gap-2">{content}</div>;
};

const CharactersSection = ({ profileUserId }: CharactersSectionProps) => {
  const dispatch = useAppDispatch();
  const characters = useAppSelector(selectUserCharacters);
  const loading = useAppSelector(selectCharactersLoading);
  const profile = useAppSelector(selectUserProfile);
  const ownCharacterId = useAppSelector((state) => state.user.character?.id ?? null);

  const postColor = profile?.post_color ?? '';
  const containerStyle = useMemo(() => {
    if (!postColor) return undefined;
    const style = buildColorEffectStyle(postColor, 'post_color', profile?.profile_style_settings);
    return { backgroundColor: style.backgroundColor } as React.CSSProperties;
  }, [postColor, profile?.profile_style_settings]);

  useEffect(() => {
    dispatch(loadUserCharacters(profileUserId));
  }, [dispatch, profileUserId]);

  if (loading) {
    return (
      <div className={postColor ? 'rounded-card p-5' : 'gray-bg p-5'} style={containerStyle}>
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (characters.length === 0) {
    return (
      <div className={postColor ? 'rounded-card p-5' : 'gray-bg p-5'} style={containerStyle}>
        <div className="flex items-center justify-center py-12">
          <p className="text-white/40 text-sm">У пользователя нет персонажей</p>
        </div>
      </div>
    );
  }

  return (
    <div className={postColor ? 'rounded-card p-5' : 'gray-bg p-5'} style={containerStyle}>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
        {characters.map((char) => (
          <CharacterCard
            key={char.id}
            char={char}
            isOwnActive={ownCharacterId != null && char.id === ownCharacterId}
          />
        ))}
      </div>
    </div>
  );
};

export default CharactersSection;
