import { useCallback, useRef } from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  selectBestiaryEntries,
  selectBestiaryTotal,
  selectBestiaryKilledCount,
  selectCurrentSpreadIndex,
  selectCurrentEntry,
  nextSpread,
  prevSpread,
} from '../../redux/slices/bestiarySlice';
import GrimoireSpread from './GrimoireSpread';
import GrimoireNavigation from './GrimoireNavigation';
import { MagicParticles, ArcaneGlow, CoverRunes, CoverEmblem } from './GrimoireMagic';

/*
 * Font constants for the grimoire:
 * - titleFont: MedievalSharp — for the book title and section headings
 * - scriptFont: Marck Script — for handwritten body text (quill pen feel)
 * - statFont: Cormorant Garamond — for stats, numbers, elegant serif text
 */
export const titleFont = "'MedievalSharp', 'Georgia', serif";
export const scriptFont = "'Marck Script', 'Georgia', cursive";
export const statFont = "'Cormorant Garamond', 'Georgia', serif";

/* ═══════════════════════════════════════════════
   SVG definitions: clip paths, gradients
   ═══════════════════════════════════════════════ */
const SvgDefs = () => (
  <svg className="absolute w-0 h-0" aria-hidden="true">
    <defs>
      <linearGradient id="ornGold" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stopColor="transparent" />
        <stop offset="25%" stopColor="#8b6914" />
        <stop offset="50%" stopColor="#c9a84c" />
        <stop offset="75%" stopColor="#8b6914" />
        <stop offset="100%" stopColor="transparent" />
      </linearGradient>

      <clipPath id="raggedLeft" clipPathUnits="objectBoundingBox">
        <path d="M0,0 L0.98,0 C0.985,0.05 0.99,0.08 0.985,0.12 C0.98,0.16 0.995,0.2 0.99,0.25
                 C0.985,0.3 0.992,0.35 0.987,0.4 C0.982,0.45 0.993,0.5 0.988,0.55
                 C0.983,0.6 0.99,0.65 0.986,0.7 C0.982,0.75 0.994,0.8 0.989,0.85
                 C0.984,0.9 0.991,0.95 0.987,1 L0,1 Z" />
      </clipPath>
      <clipPath id="raggedRight" clipPathUnits="objectBoundingBox">
        <path d="M0.02,0 L1,0 L1,1 L0.013,1
                 C0.018,0.95 0.009,0.9 0.014,0.85 C0.019,0.8 0.006,0.75 0.011,0.7
                 C0.016,0.65 0.008,0.6 0.013,0.55 C0.018,0.5 0.007,0.45 0.012,0.4
                 C0.017,0.35 0.01,0.3 0.015,0.25 C0.02,0.2 0.005,0.15 0.01,0.1
                 C0.015,0.05 0.008,0.02 0.02,0 Z" />
      </clipPath>
    </defs>
  </svg>
);

/* ── Decorative SVG ornament ── */
const BookOrnament = ({ flip }: { flip?: boolean }) => (
  <svg
    viewBox="0 0 240 20"
    className={`w-40 sm:w-56 md:w-64 h-5 ${flip ? 'rotate-180' : ''}`}
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <rect x="115" y="5" width="10" height="10" rx="1" transform="rotate(45 120 10)"
      stroke="url(#ornGold)" strokeWidth="0.8" fill="none" />
    <rect x="117" y="7" width="6" height="6" rx="0.5" transform="rotate(45 120 10)"
      fill="#8b6914" fillOpacity="0.3" />
    <path d="M110 10 C100 10 95 6 85 6 C78 6 74 10 65 10 C58 10 54 7 45 7 C38 7 34 10 20 10 L0 10"
      stroke="url(#ornGold)" strokeWidth="0.8" strokeLinecap="round" opacity="0.6" />
    <path d="M130 10 C140 10 145 6 155 6 C162 6 166 10 175 10 C182 10 186 7 195 7 C202 7 206 10 220 10 L240 10"
      stroke="url(#ornGold)" strokeWidth="0.8" strokeLinecap="round" opacity="0.6" />
    <circle cx="45" cy="10" r="1.2" fill="#8b6914" fillOpacity="0.5" />
    <circle cx="195" cy="10" r="1.2" fill="#8b6914" fillOpacity="0.5" />
  </svg>
);

/* ── Corner clasp ── */
const CornerClasp = ({ position }: { position: 'tl' | 'tr' | 'bl' | 'br' }) => {
  const rotations = { tl: '', tr: 'scale(-1,1)', bl: 'scale(1,-1)', br: 'scale(-1,-1)' };
  const positions = { tl: 'top-1 left-1', tr: 'top-1 right-1', bl: 'bottom-1 left-1', br: 'bottom-1 right-1' };
  return (
    <svg
      viewBox="0 0 32 32"
      className={`absolute ${positions[position]} w-8 h-8 sm:w-10 sm:h-10`}
      style={{ transform: rotations[position] }}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M2 2 L14 2 C14 2 12 4 12 6 L12 8" stroke="#8b6914" strokeWidth="1.2" strokeOpacity="0.6" strokeLinecap="round" />
      <path d="M2 2 L2 14 C2 14 4 12 6 12 L8 12" stroke="#8b6914" strokeWidth="1.2" strokeOpacity="0.6" strokeLinecap="round" />
      <circle cx="2" cy="2" r="1.5" fill="#8b6914" fillOpacity="0.5" />
    </svg>
  );
};

/* ── Age spots on pages ── */
const AgeSpot = ({ className }: { className: string }) => (
  <div
    className={`absolute pointer-events-none ${className}`}
    style={{
      background: 'radial-gradient(ellipse, rgba(160,130,80,0.12) 0%, rgba(140,110,60,0.06) 40%, transparent 70%)',
      borderRadius: '50% 40% 60% 45% / 55% 45% 50% 40%',
    }}
  />
);

const GrimoireBook = () => {
  const dispatch = useAppDispatch();
  const entries = useAppSelector(selectBestiaryEntries);
  const total = useAppSelector(selectBestiaryTotal);
  const killedCount = useAppSelector(selectBestiaryKilledCount);
  const currentIndex = useAppSelector(selectCurrentSpreadIndex);
  const currentEntry = useAppSelector(selectCurrentEntry);

  const directionRef = useRef(0);

  const handlePrev = useCallback(() => {
    directionRef.current = -1;
    dispatch(prevSpread());
  }, [dispatch]);

  const handleNext = useCallback(() => {
    directionRef.current = 1;
    dispatch(nextSpread());
  }, [dispatch]);

  if (!currentEntry || entries.length === 0) {
    return null;
  }

  return (
    <div className="max-w-5xl mx-auto w-full px-2 sm:px-4" style={{ perspective: '1200px' }}>
      <SvgDefs />

      {/* ══════ LEATHER COVER ══════ */}
      <div
        className="relative rounded-xl"
        style={{
          transform: 'rotateX(1deg)',
          transformOrigin: 'center bottom',
          boxShadow:
            '0 12px 50px rgba(80,50,20,0.4), 0 4px 20px rgba(60,30,10,0.3), inset 0 1px 0 rgba(201,168,76,0.15)',
        }}
      >
        {/* Arcane glow */}
        <ArcaneGlow />

        {/* Leather base — warm dark brown */}
        <div
          className="absolute inset-0 rounded-xl"
          style={{
            background:
              'radial-gradient(ellipse at 30% 20%, #6b4a2a 0%, #4a3018 40%, #3a2210 70%, #2a1808 100%)',
          }}
        />

        {/* Leather texture */}
        <div
          className="absolute inset-0 rounded-xl opacity-30 pointer-events-none mix-blend-overlay"
          style={{ backgroundImage: 'url(/textures/leather.png)', backgroundRepeat: 'repeat' }}
        />

        {/* Emboss lines */}
        <div className="absolute inset-3 rounded-lg pointer-events-none border border-amber-600/20" />
        <div className="absolute inset-5 rounded-md pointer-events-none border border-amber-600/10" />

        {/* Corner clasps */}
        <CornerClasp position="tl" />
        <CornerClasp position="tr" />
        <CornerClasp position="bl" />
        <CornerClasp position="br" />

        {/* Magical effects */}
        <CoverRunes />
        <CoverEmblem />
        <MagicParticles />

        {/* ── Inner content ── */}
        <div className="relative p-4 sm:p-6 md:p-8">

          {/* Title */}
          <div className="flex items-center justify-between mb-1 sm:mb-2">
            <h1
              className="text-xl sm:text-2xl md:text-3xl tracking-wide"
              style={{
                fontFamily: titleFont,
                color: '#c9a84c',
                textShadow: '0 1px 3px rgba(0,0,0,0.6), 0 0 12px rgba(201,168,76,0.3)',
              }}
            >
              Гримуар охотника
            </h1>
            <span
              className="text-amber-300/40 text-[10px] sm:text-xs tracking-wider"
              style={{ fontFamily: statFont, fontStyle: 'italic' }}
            >
              Изучено: {killedCount} / {total}
            </span>
          </div>

          {/* Top ornament */}
          <div className="flex justify-center mb-3 sm:mb-4">
            <BookOrnament />
          </div>

          {/* ══════ PARCHMENT PAGES AREA ══════ */}
          <div
            className="relative rounded-sm overflow-hidden"
            style={{
              boxShadow:
                'inset 0 2px 8px rgba(100,70,30,0.3), inset 0 -2px 6px rgba(100,70,30,0.2), 0 1px 0 rgba(201,168,76,0.1)',
            }}
          >
            {/* — Light parchment base — */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                background:
                  'linear-gradient(170deg, #e8dcc8 0%, #dfd0b8 20%, #e4d8c2 40%, #d8cab0 60%, #e0d4be 80%, #e8dcc8 100%)',
              }}
            />

            {/* — Paper texture overlay — */}
            <div
              className="absolute inset-0 pointer-events-none opacity-15 mix-blend-multiply"
              style={{ backgroundImage: 'url(/textures/paper.png)', backgroundRepeat: 'repeat' }}
            />

            {/* — Aged stain overlay — */}
            <div
              className="absolute inset-0 pointer-events-none opacity-20 mix-blend-multiply"
              style={{ backgroundImage: 'url(/textures/old-wall.png)', backgroundRepeat: 'repeat' }}
            />

            {/* — Age spots — */}
            <AgeSpot className="w-24 h-20 top-[10%] left-[5%]" />
            <AgeSpot className="w-32 h-24 top-[60%] right-[8%]" />
            <AgeSpot className="w-20 h-28 top-[30%] right-[45%]" />
            <AgeSpot className="w-28 h-20 top-[5%] right-[25%]" />

            {/* — Edge darkening / vignette (soft) — */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                boxShadow:
                  'inset 0 0 40px rgba(140,110,60,0.25), inset 0 0 80px rgba(120,90,40,0.1)',
              }}
            />

            {/* — Book spine / center gutter — */}
            <div className="hidden md:block absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-8 z-10 pointer-events-none">
              <div
                className="w-full h-full"
                style={{
                  background:
                    'linear-gradient(90deg, transparent 0%, rgba(120,90,40,0.2) 20%, rgba(100,70,30,0.4) 45%, rgba(90,60,25,0.5) 50%, rgba(100,70,30,0.4) 55%, rgba(120,90,40,0.2) 80%, transparent 100%)',
                }}
              />
              {/* Stitching */}
              <div
                className="absolute top-6 bottom-6 left-1/2 -translate-x-1/2 w-px"
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(to bottom, rgba(139,105,20,0.4) 0px, rgba(139,105,20,0.4) 6px, transparent 6px, transparent 14px)',
                }}
              />
            </div>

            {/* — Page curl (bottom-right) — */}
            <div
              className="hidden md:block absolute bottom-0 right-0 w-10 h-10 z-10 pointer-events-none"
              style={{
                background: 'linear-gradient(315deg, rgba(190,170,130,0.9) 0%, rgba(210,190,150,0.5) 30%, transparent 60%)',
                borderTopLeftRadius: '8px',
                boxShadow: '-1px -1px 3px rgba(100,70,30,0.2)',
              }}
            />

            {/* ── Spread content ── */}
            <div className="relative z-[1]">
              <GrimoireSpread
                entry={currentEntry}
                direction={directionRef.current}
              />
            </div>
          </div>

          {/* Bottom ornament */}
          <div className="flex justify-center mt-3 sm:mt-4">
            <BookOrnament flip />
          </div>

          {/* Kill status */}
          <div className="flex justify-center mt-2">
            {currentEntry.killed ? (
              <span
                className="text-green-300/60 text-[10px] sm:text-xs flex items-center gap-1.5 tracking-wider"
                style={{ fontFamily: scriptFont }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                Запись изучена
              </span>
            ) : (
              <span
                className="text-amber-300/30 text-[10px] sm:text-xs flex items-center gap-1.5 tracking-wider"
                style={{ fontFamily: scriptFont }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                Запись не изучена
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Navigation */}
      <GrimoireNavigation
        currentIndex={currentIndex}
        total={entries.length}
        onPrev={handlePrev}
        onNext={handleNext}
      />
    </div>
  );
};

export default GrimoireBook;
