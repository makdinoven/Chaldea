import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  selectBestiaryEntries,
  selectBestiaryTotal,
  selectBestiaryKilledCount,
  selectSelectedMobId,
  selectSelectedMob,
  selectMob,
  clearSelectedMob,
} from '../../redux/slices/bestiarySlice';
import type { BestiaryEntry } from '../../api/bestiary';
import ScrollMobDetail from './ScrollMobDetail';
import {
  MagicParticles,
  ScrollMarginRunes,
  ScrollEnergyLines,
  ParchmentWatermarks,
} from './GrimoireMagic';

const titleFont = "'MedievalSharp', 'Georgia', serif";
const scriptFont = "'Marck Script', 'Georgia', cursive";
const statFont = "'Cormorant Garamond', 'Georgia', serif";

const MOBS_PER_PAGE = 16;
const MAX_FAVORITES = 4;
const FAVORITES_KEY = 'bestiary_favorites';

/* ── Tier styling ── */
const TIER_STYLE: Record<string, { label: string; color: string; glow: string }> = {
  normal: { label: 'Обычный', color: '#5a4a2a', glow: 'none' },
  elite: { label: 'Элитный', color: '#6a3a8a', glow: '0 0 8px rgba(106,58,138,0.3)' },
  boss: { label: 'Босс', color: '#8b2020', glow: '0 0 8px rgba(139,32,32,0.3)' },
};

/* ── Favorites helpers (localStorage) ── */
const loadFavorites = (): number[] => {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((v: unknown) => typeof v === 'number') : [];
  } catch {
    return [];
  }
};

const saveFavorites = (ids: number[]) => {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(ids));
};

/* ── Ornamental divider ── */
const ScrollDivider = () => (
  <div className="flex items-center gap-2 py-3 px-4">
    <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, transparent, rgba(139,105,20,0.3))' }} />
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="4" y="4" width="8" height="8" rx="1" transform="rotate(45 8 8)"
        stroke="#8b6914" strokeWidth="0.8" strokeOpacity="0.4" />
    </svg>
    <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, rgba(139,105,20,0.3), transparent)' }} />
  </div>
);

/* ── Star icon for favorites ── */
const StarIcon = ({ filled, size = 16 }: { filled: boolean; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? '#c9a84c' : 'none'}
    stroke={filled ? '#8b6914' : '#8b6914'} strokeWidth={1.5}
    strokeLinecap="round" strokeLinejoin="round"
  >
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

/* ── Single mob entry in the grid ── */
const MobGridEntry = ({
  entry,
  onClick,
  isFavorite,
  onToggleFavorite,
}: {
  entry: BestiaryEntry;
  onClick: () => void;
  isFavorite: boolean;
  onToggleFavorite: (e: React.MouseEvent) => void;
}) => {
  const tier = TIER_STYLE[entry.tier] ?? TIER_STYLE.normal;
  const isHidden = !entry.killed;

  return (
    <motion.div
      className="flex items-center gap-2 sm:gap-3 px-2 sm:px-3 py-2 sm:py-2.5 rounded-sm
                 cursor-pointer group"
      style={{ background: 'rgba(139,105,20,0.04)' }}
      whileHover={{ background: 'rgba(139,105,20,0.1)', x: 2 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
    >
      {/* Avatar thumbnail */}
      <div
        className="w-10 h-10 sm:w-12 sm:h-12 rounded-sm shrink-0 overflow-hidden relative"
        style={{
          border: `1.5px solid ${tier.color}40`,
          boxShadow: entry.killed ? tier.glow : 'none',
        }}
      >
        {entry.avatar ? (
          <>
            <img
              src={entry.avatar}
              alt={entry.name}
              className="w-full h-full object-cover"
              style={{
                filter: isHidden
                  ? 'brightness(0.3) saturate(0) blur(2px)'
                  : 'sepia(0.15) contrast(1.05)',
              }}
            />
            {/* Question mark overlay for unstudied mobs */}
            {!entry.killed && (
              <div className="absolute inset-0 flex items-center justify-center">
                <span
                  className="text-lg sm:text-xl select-none"
                  style={{
                    fontFamily: titleFont,
                    color: 'rgba(200,180,140,0.8)',
                    textShadow: '0 1px 4px rgba(0,0,0,0.5)',
                  }}
                >
                  ?
                </span>
              </div>
            )}
          </>
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{ background: 'rgba(180,160,120,0.15)' }}
          >
            <span style={{ fontFamily: titleFont, color: 'rgba(120,90,40,0.2)', fontSize: '16px' }}>?</span>
          </div>
        )}
        {/* Kill indicator */}
        {entry.killed && (
          <div
            className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full"
            style={{ background: '#4a8a3a', boxShadow: '0 0 4px rgba(74,138,58,0.5)' }}
          />
        )}
      </div>

      {/* Name + tier + favorite */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1">
          <div
            className="text-xs sm:text-sm truncate group-hover:text-amber-900 transition-colors leading-tight"
            style={{
              fontFamily: titleFont,
              color: isHidden ? '#9a8a70' : '#3a2810',
            }}
          >
            {entry.name}
          </div>
          <button
            onClick={onToggleFavorite}
            className="shrink-0 p-0.5 opacity-40 hover:opacity-100 transition-opacity"
            title={isFavorite ? 'Убрать из избранного' : 'Добавить в избранное'}
          >
            <StarIcon filled={isFavorite} size={12} />
          </button>
        </div>
        <div className="flex items-center gap-1 mt-0.5">
          <span
            className="text-[9px] sm:text-[10px] uppercase tracking-wider"
            style={{ fontFamily: statFont, color: tier.color }}
          >
            {tier.label}
          </span>
          <span className="text-[8px]" style={{ color: '#b0a080' }}>&#x2022;</span>
          <span
            className="text-[9px] sm:text-[10px]"
            style={{ fontFamily: scriptFont, color: '#8a7050' }}
          >
            Ур. {entry.level}
          </span>
        </div>
      </div>
    </motion.div>
  );
};

/* ═══════════════════════════════════════════════
   Main Scroll Bestiary component
   ═══════════════════════════════════════════════ */
const ScrollBestiary = () => {
  const dispatch = useAppDispatch();
  const entries = useAppSelector(selectBestiaryEntries);
  const total = useAppSelector(selectBestiaryTotal);
  const killedCount = useAppSelector(selectBestiaryKilledCount);
  const selectedMobId = useAppSelector(selectSelectedMobId);
  const selectedMob = useAppSelector(selectSelectedMob);

  const [currentPage, setCurrentPage] = useState(1);
  const [favoriteIds, setFavoriteIds] = useState<number[]>(loadFavorites);
  const [searchQuery, setSearchQuery] = useState('');
  const [tierFilter, setTierFilter] = useState<string>('');

  const handleSelectMob = (id: number) => dispatch(selectMob(id));
  const handleBack = () => dispatch(clearSelectedMob());

  const toggleFavorite = useCallback((id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setFavoriteIds((prev) => {
      let next: number[];
      if (prev.includes(id)) {
        next = prev.filter((fid) => fid !== id);
      } else {
        if (prev.length >= MAX_FAVORITES) return prev;
        next = [...prev, id];
      }
      saveFavorites(next);
      return next;
    });
  }, []);

  // Filter entries by search + tier
  const filteredEntries = entries.filter((e) => {
    if (searchQuery && !e.name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    if (tierFilter && e.tier !== tierFilter) return false;
    return true;
  });

  // Pagination (on filtered results)
  const totalPages = Math.ceil(filteredEntries.length / MOBS_PER_PAGE);
  const startIdx = (currentPage - 1) * MOBS_PER_PAGE;
  const pageEntries = filteredEntries.slice(startIdx, startIdx + MOBS_PER_PAGE);

  // Reset page when filters change
  const handleSearch = (q: string) => {
    setSearchQuery(q);
    setCurrentPage(1);
  };
  const handleTierFilter = (t: string) => {
    setTierFilter((prev) => (prev === t ? '' : t));
    setCurrentPage(1);
  };

  // Favorites (only entries that still exist)
  const favoriteEntries = favoriteIds
    .map((id) => entries.find((e) => e.id === id))
    .filter((e): e is BestiaryEntry => !!e)
    .slice(0, MAX_FAVORITES);

  return (
    <div className="max-w-3xl mx-auto w-full px-2 sm:px-4">

      {/* ══ Parchment body (no rollers) ══ */}
      <div
        className="relative rounded-card overflow-hidden"
        style={{
          background:
            'linear-gradient(180deg, #d8c8a8 0%, #e4d8c2 3%, #e8dcc8 10%, #e4d8c2 50%, #e0d4be 90%, #e4d8c2 97%, #d8c8a8 100%)',
          boxShadow:
            '0 4px 20px rgba(100,70,30,0.2), inset 3px 0 8px rgba(100,70,30,0.1), inset -3px 0 8px rgba(100,70,30,0.1)',
        }}
      >
        {/* Paper texture */}
        <div
          className="absolute inset-0 pointer-events-none opacity-15 mix-blend-multiply"
          style={{ backgroundImage: 'url(/textures/paper.png)', backgroundRepeat: 'repeat' }}
        />
        {/* Aged spots */}
        <div
          className="absolute inset-0 pointer-events-none opacity-15 mix-blend-multiply"
          style={{ backgroundImage: 'url(/textures/old-wall.png)', backgroundRepeat: 'repeat' }}
        />
        {/* Edge vignette */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            boxShadow: 'inset 0 0 40px rgba(140,110,60,0.2), inset 0 0 80px rgba(120,90,40,0.08)',
          }}
        />

        {/* ── Magical effects ── */}
        <MagicParticles />
        <ScrollMarginRunes />
        <ScrollEnergyLines />
        <ParchmentWatermarks />

        {/* ── Content ── */}
        <div className="relative z-[1] px-4 sm:px-8 py-6 sm:py-8">

          <AnimatePresence mode="wait">
            {selectedMob ? (
              /* ── Detail view ── */
              <motion.div
                key={`detail-${selectedMob.id}`}
                initial={{ opacity: 0, filter: 'blur(8px) saturate(0) brightness(1.3)' }}
                animate={{ opacity: 1, filter: 'blur(0px) saturate(1) brightness(1)' }}
                exit={{ opacity: 0, filter: 'blur(6px) saturate(0) brightness(1.4)' }}
                transition={{
                  duration: 0.5,
                  ease: [0.4, 0, 0.2, 1],
                  opacity: { duration: 0.4 },
                }}
              >
                {/* Back button */}
                <button
                  onClick={handleBack}
                  className="flex items-center gap-1.5 mb-4 group"
                >
                  <svg className="w-4 h-4" style={{ color: '#8b6914' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                  </svg>
                  <span
                    className="text-sm group-hover:underline"
                    style={{ fontFamily: scriptFont, color: '#6a5030' }}
                  >
                    Назад к списку
                  </span>
                </button>

                <ScrollMobDetail entry={selectedMob} />
              </motion.div>
            ) : (
              /* ── List view ── */
              <motion.div
                key={`list-page-${currentPage}`}
                initial={{ opacity: 0, filter: 'blur(8px) saturate(0) brightness(1.3)' }}
                animate={{ opacity: 1, filter: 'blur(0px) saturate(1) brightness(1)' }}
                exit={{ opacity: 0, filter: 'blur(6px) saturate(0) brightness(1.4)' }}
                transition={{
                  duration: 0.5,
                  ease: [0.4, 0, 0.2, 1],
                  opacity: { duration: 0.4 },
                }}
              >
                {/* Lore intro */}
                <div className="text-center mb-6 sm:mb-8">
                  <h1
                    className="text-2xl sm:text-3xl md:text-4xl mb-3"
                    style={{
                      fontFamily: titleFont,
                      color: '#3a2810',
                      textShadow: '0 1px 2px rgba(100,70,30,0.15)',
                    }}
                  >
                    Свиток охотника
                  </h1>

                  <div className="flex items-center justify-center gap-2 mb-4">
                    <div className="w-12 h-px" style={{ background: 'linear-gradient(to right, transparent, rgba(139,105,20,0.4))' }} />
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <circle cx="6" cy="6" r="3" stroke="#8b6914" strokeWidth="0.6" strokeOpacity="0.4" />
                      <circle cx="6" cy="6" r="1" fill="#8b6914" fillOpacity="0.3" />
                    </svg>
                    <div className="w-12 h-px" style={{ background: 'linear-gradient(to right, rgba(139,105,20,0.4), transparent)' }} />
                  </div>

                  <p
                    className="text-sm sm:text-base leading-relaxed max-w-lg mx-auto mb-2"
                    style={{ fontFamily: scriptFont, color: '#4a3520' }}
                  >
                    Ты держишь в руках древний артефакт, пропитанный забытыми плетениями.
                    Чернила на этом свитке живут собственной жизнью — они проступают лишь тогда,
                    когда охотник сам познаёт природу зверя через кровь и сталь.
                  </p>
                  <p
                    className="text-xs sm:text-sm leading-relaxed max-w-md mx-auto"
                    style={{ fontFamily: scriptFont, color: '#7a6a4a' }}
                  >
                    Чем больше тварей падёт от твоей руки, тем больше тайн откроет свиток.
                    Ступай на путь охотника, скиталец.
                  </p>
                </div>

                <ScrollDivider />

                {/* Stats line */}
                <div className="flex justify-center gap-4 mb-4 pb-2">
                  <span className="text-xs" style={{ fontFamily: statFont, color: '#8a7050' }}>
                    Записей: {total}
                  </span>
                  <span style={{ color: '#c0b090' }}>&#x2022;</span>
                  <span className="text-xs" style={{ fontFamily: statFont, color: '#8a7050' }}>
                    Изучено: {killedCount}
                  </span>
                </div>

                {/* ── Search + Tier filter ── */}
                <div className="mb-4 space-y-3">
                  {/* Search */}
                  <div className="max-w-xs mx-auto">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => handleSearch(e.target.value)}
                      placeholder="Поиск по имени..."
                      className="w-full bg-white/30 border border-amber-800/15 rounded-sm px-3 py-1.5
                                 text-sm text-amber-900 placeholder:text-amber-700/40 outline-none
                                 focus:border-amber-700/40 transition-colors"
                      style={{ fontFamily: statFont }}
                    />
                  </div>

                  {/* Tier filter pills */}
                  <div className="flex justify-center gap-2">
                    {(['normal', 'elite', 'boss'] as const).map((t) => {
                      const ts = TIER_STYLE[t];
                      const active = tierFilter === t;
                      return (
                        <button
                          key={t}
                          onClick={() => handleTierFilter(t)}
                          className="px-2.5 py-1 rounded-sm text-[10px] sm:text-xs uppercase tracking-wider
                                     transition-all duration-200"
                          style={{
                            fontFamily: statFont,
                            color: active ? '#f5e6c8' : ts.color,
                            background: active ? `${ts.color}cc` : `${ts.color}10`,
                            border: `1px solid ${ts.color}${active ? '80' : '25'}`,
                          }}
                        >
                          {ts.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* ── Favorites section (page 1 only) ── */}
                {currentPage === 1 && favoriteEntries.length > 0 && (
                  <div className="mb-6">
                    <h2
                      className="text-center text-sm sm:text-base mb-3"
                      style={{ fontFamily: titleFont, color: '#6a5020' }}
                    >
                      <StarIcon filled size={14} /> Избранные
                    </h2>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 mb-2">
                      {favoriteEntries.map((entry) => (
                        <MobGridEntry
                          key={`fav-${entry.id}`}
                          entry={entry}
                          onClick={() => handleSelectMob(entry.id)}
                          isFavorite
                          onToggleFavorite={(e) => toggleFavorite(entry.id, e)}
                        />
                      ))}
                    </div>
                    <ScrollDivider />
                  </div>
                )}

                {/* ── Mob grid (2 columns, 8 per column = 16 per page) ── */}
                <div className="grid grid-cols-2 gap-2 sm:gap-3">
                  {pageEntries.map((entry) => (
                    <MobGridEntry
                      key={entry.id}
                      entry={entry}
                      onClick={() => handleSelectMob(entry.id)}
                      isFavorite={favoriteIds.includes(entry.id)}
                      onToggleFavorite={(e) => toggleFavorite(entry.id, e)}
                    />
                  ))}
                </div>

                {entries.length === 0 && (
                  <p
                    className="text-center py-8 text-sm"
                    style={{ fontFamily: scriptFont, color: '#9a8a70' }}
                  >
                    Свиток пуст — монстры ещё не ведомы этому миру
                  </p>
                )}

                {/* ── Pagination ── */}
                {totalPages > 1 && (
                  <div className="flex justify-center items-center gap-3 mt-6 pt-4">
                    <button
                      disabled={currentPage <= 1}
                      onClick={() => setCurrentPage((p) => p - 1)}
                      className="px-3 py-1.5 rounded-sm text-sm transition-colors
                                 disabled:opacity-30 disabled:pointer-events-none"
                      style={{
                        fontFamily: scriptFont,
                        color: '#6a5030',
                        background: 'rgba(139,105,20,0.08)',
                      }}
                    >
                      &larr; Назад
                    </button>
                    <span
                      className="text-xs"
                      style={{ fontFamily: statFont, color: '#8a7050' }}
                    >
                      {currentPage} / {totalPages}
                    </span>
                    <button
                      disabled={currentPage >= totalPages}
                      onClick={() => setCurrentPage((p) => p + 1)}
                      className="px-3 py-1.5 rounded-sm text-sm transition-colors
                                 disabled:opacity-30 disabled:pointer-events-none"
                      style={{
                        fontFamily: scriptFont,
                        color: '#6a5030',
                        background: 'rgba(139,105,20,0.08)',
                      }}
                    >
                      Вперёд &rarr;
                    </button>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default ScrollBestiary;
