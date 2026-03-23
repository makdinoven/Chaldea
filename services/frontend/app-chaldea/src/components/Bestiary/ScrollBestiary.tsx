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
  RollerGlow,
  ScrollEnergyLines,
  ParchmentWatermarks,
} from './GrimoireMagic';

const titleFont = "'MedievalSharp', 'Georgia', serif";
const scriptFont = "'Marck Script', 'Georgia', cursive";
const statFont = "'Cormorant Garamond', 'Georgia', serif";

/* ── Tier styling ── */
const TIER_STYLE: Record<string, { label: string; color: string; glow: string }> = {
  normal: { label: 'Обычный', color: '#5a4a2a', glow: 'none' },
  elite: { label: 'Элитный', color: '#6a3a8a', glow: '0 0 8px rgba(106,58,138,0.3)' },
  boss: { label: 'Босс', color: '#8b2020', glow: '0 0 8px rgba(139,32,32,0.3)' },
};

/* ── Scroll roller (top/bottom) ── */
const ScrollRoller = () => (
  <div className="relative h-6 sm:h-8 mx-2 sm:mx-4 z-10">
    {/* Magical glow on roller */}
    <RollerGlow />
    {/* Wood bar */}
    <div
      className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-4 sm:h-5 rounded-full"
      style={{
        background: 'linear-gradient(180deg, #8b7350 0%, #6b5030 30%, #4a3520 60%, #6b5030 90%, #8b7350 100%)',
        boxShadow: '0 2px 6px rgba(60,30,10,0.4), inset 0 1px 0 rgba(255,255,255,0.1)',
      }}
    />
    {/* End knobs */}
    {['left', 'right'].map((side) => (
      <div
        key={side}
        className="absolute top-1/2 -translate-y-1/2 w-6 h-6 sm:w-8 sm:h-8 rounded-full"
        style={{
          [side]: '-4px',
          background: 'radial-gradient(circle at 35% 35%, #a08050, #6b4a2a 60%, #4a3018)',
          boxShadow: '0 2px 4px rgba(0,0,0,0.4), inset 0 1px 2px rgba(255,255,255,0.15)',
          border: '1px solid rgba(139,105,20,0.3)',
        }}
      />
    ))}
  </div>
);

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

/* ── Single mob entry in the list ── */
const MobListEntry = ({ entry, onClick }: { entry: BestiaryEntry; onClick: () => void }) => {
  const tier = TIER_STYLE[entry.tier] ?? TIER_STYLE.normal;
  const isEliteOrBoss = entry.tier === 'elite' || entry.tier === 'boss';
  const isHidden = !entry.killed && isEliteOrBoss;

  return (
    <motion.button
      onClick={onClick}
      className="w-full flex items-center gap-3 sm:gap-4 px-3 sm:px-5 py-3 sm:py-4 text-left
                 rounded-sm transition-all duration-200 group"
      style={{
        background: 'transparent',
      }}
      whileHover={{
        background: 'rgba(139,105,20,0.06)',
        x: 4,
      }}
      whileTap={{ scale: 0.99 }}
    >
      {/* Avatar thumbnail */}
      <div
        className="w-12 h-12 sm:w-14 sm:h-14 rounded-sm shrink-0 overflow-hidden relative"
        style={{
          border: `1.5px solid ${tier.color}40`,
          boxShadow: entry.killed ? tier.glow : 'none',
        }}
      >
        {entry.avatar ? (
          <img
            src={entry.avatar}
            alt={entry.name}
            className="w-full h-full object-cover"
            style={{
              filter: isHidden
                ? 'brightness(0.3) saturate(0) blur(1px)'
                : 'sepia(0.15) contrast(1.05)',
            }}
          />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{ background: 'rgba(180,160,120,0.2)' }}
          >
            <span style={{ fontFamily: titleFont, color: 'rgba(120,90,40,0.2)', fontSize: '20px' }}>?</span>
          </div>
        )}
        {/* Kill indicator dot */}
        {entry.killed && (
          <div
            className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full"
            style={{ background: '#4a8a3a', boxShadow: '0 0 4px rgba(74,138,58,0.5)' }}
          />
        )}
      </div>

      {/* Name and tier */}
      <div className="flex-1 min-w-0">
        <div
          className="text-base sm:text-lg truncate group-hover:text-amber-900 transition-colors"
          style={{
            fontFamily: titleFont,
            color: isHidden ? '#9a8a70' : '#3a2810',
          }}
        >
          {entry.name}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span
            className="text-[10px] sm:text-xs uppercase tracking-wider"
            style={{ fontFamily: statFont, color: tier.color }}
          >
            {tier.label}
          </span>
          <span className="text-[10px]" style={{ color: '#b0a080' }}>&#x2022;</span>
          <span
            className="text-[10px] sm:text-xs"
            style={{ fontFamily: scriptFont, color: '#8a7050' }}
          >
            Ур. {entry.level}
          </span>
        </div>
      </div>

      {/* Arrow indicator */}
      <svg
        className="w-4 h-4 sm:w-5 sm:h-5 shrink-0 opacity-30 group-hover:opacity-60 transition-opacity"
        style={{ color: '#8b6914' }}
        fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
      </svg>
    </motion.button>
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

  const handleSelectMob = (id: number) => dispatch(selectMob(id));
  const handleBack = () => dispatch(clearSelectedMob());

  return (
    <div className="max-w-2xl mx-auto w-full px-2 sm:px-4">

      {/* ══ Top roller ══ */}
      <ScrollRoller />

      {/* ══ Parchment body ══ */}
      <div
        className="relative mx-2 sm:mx-4 -mt-2 -mb-2"
        style={{
          background:
            'linear-gradient(180deg, #d8c8a8 0%, #e4d8c2 3%, #e8dcc8 10%, #e4d8c2 50%, #e0d4be 90%, #e4d8c2 97%, #d8c8a8 100%)',
          boxShadow:
            '4px 0 12px rgba(100,70,30,0.15), -4px 0 12px rgba(100,70,30,0.15), inset 3px 0 8px rgba(100,70,30,0.1), inset -3px 0 8px rgba(100,70,30,0.1)',
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
        {/* Curl shadow on sides */}
        <div
          className="absolute top-0 bottom-0 left-0 w-6 pointer-events-none"
          style={{ background: 'linear-gradient(to right, rgba(140,110,60,0.2), transparent)' }}
        />
        <div
          className="absolute top-0 bottom-0 right-0 w-6 pointer-events-none"
          style={{ background: 'linear-gradient(to left, rgba(140,110,60,0.2), transparent)' }}
        />

        {/* ── Magical effects ── */}
        <MagicParticles />
        <ScrollMarginRunes />
        <ScrollEnergyLines />
        <ParchmentWatermarks />

        {/* ── Content ── */}
        <div className="relative z-[1] px-4 sm:px-8 py-6 sm:py-8">

          {/*
            Ink soak animation:
            - Exit: content blurs + fades to parchment color (ink absorbing into paper)
            - Enter: content appears from blur (ink bleeding through from behind)
          */}
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
                key="list"
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
                <div className="flex justify-center gap-4 mb-2 pb-2">
                  <span className="text-xs" style={{ fontFamily: statFont, color: '#8a7050' }}>
                    Записей: {total}
                  </span>
                  <span style={{ color: '#c0b090' }}>&#x2022;</span>
                  <span className="text-xs" style={{ fontFamily: statFont, color: '#8a7050' }}>
                    Изучено: {killedCount}
                  </span>
                </div>

                {/* Mob list */}
                <div className="flex flex-col">
                  {entries.map((entry, i) => (
                    <div key={entry.id}>
                      {i > 0 && (
                        <div className="mx-4 h-px" style={{ background: 'rgba(139,105,20,0.1)' }} />
                      )}
                      <MobListEntry
                        entry={entry}
                        onClick={() => handleSelectMob(entry.id)}
                      />
                    </div>
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
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* ══ Bottom roller ══ */}
      <ScrollRoller />
    </div>
  );
};

export default ScrollBestiary;
