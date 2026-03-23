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

const serifFont = "'Georgia', 'Palatino Linotype', 'Palatino', serif";

/* ═══════════════════════════════════════════════
   SVG filters — inline so they're available to the whole book.
   - parchmentNoise: feTurbulence grain for paper texture
   - inkBleed: feGaussianBlur for slight ink spread effect
   ═══════════════════════════════════════════════ */
const SvgFilters = () => (
  <svg className="absolute w-0 h-0" aria-hidden="true">
    <defs>
      {/* Paper grain noise */}
      <filter id="parchmentNoise" x="0%" y="0%" width="100%" height="100%">
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.65"
          numOctaves="6"
          stitchTiles="stitch"
          result="noise"
        />
        <feColorMatrix
          type="saturate"
          values="0"
          in="noise"
          result="gray"
        />
        <feBlend in="SourceGraphic" in2="gray" mode="multiply" />
      </filter>

      {/* Coarser noise for leather */}
      <filter id="leatherGrain" x="0%" y="0%" width="100%" height="100%">
        <feTurbulence
          type="turbulence"
          baseFrequency="0.8"
          numOctaves="3"
          seed="2"
          stitchTiles="stitch"
          result="noise"
        />
        <feColorMatrix
          type="saturate"
          values="0"
          in="noise"
          result="gray"
        />
        <feBlend in="SourceGraphic" in2="gray" mode="soft-light" />
      </filter>

      {/* Ornament gradient */}
      <linearGradient id="ornGold" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stopColor="transparent" />
        <stop offset="25%" stopColor="#c9a84c" />
        <stop offset="50%" stopColor="#e8d48b" />
        <stop offset="75%" stopColor="#c9a84c" />
        <stop offset="100%" stopColor="transparent" />
      </linearGradient>

      {/* Ragged edge clip for pages */}
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

/* ── Decorative SVG ornament (more elaborate) ── */
const BookOrnament = ({ flip }: { flip?: boolean }) => (
  <svg
    viewBox="0 0 240 20"
    className={`w-40 sm:w-56 md:w-64 h-5 ${flip ? 'rotate-180' : ''}`}
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Center diamond */}
    <rect x="115" y="5" width="10" height="10" rx="1" transform="rotate(45 120 10)"
      stroke="url(#ornGold)" strokeWidth="0.8" fill="none" />
    <rect x="117" y="7" width="6" height="6" rx="0.5" transform="rotate(45 120 10)"
      fill="#c9a84c" fillOpacity="0.3" />
    {/* Left flourish */}
    <path d="M110 10 C100 10 95 6 85 6 C78 6 74 10 65 10 C58 10 54 7 45 7 C38 7 34 10 20 10 L0 10"
      stroke="url(#ornGold)" strokeWidth="0.8" strokeLinecap="round" opacity="0.5" />
    <path d="M110 10 C100 10 95 14 85 14 C78 14 74 10 65 10"
      stroke="url(#ornGold)" strokeWidth="0.6" strokeLinecap="round" opacity="0.3" />
    {/* Right flourish */}
    <path d="M130 10 C140 10 145 6 155 6 C162 6 166 10 175 10 C182 10 186 7 195 7 C202 7 206 10 220 10 L240 10"
      stroke="url(#ornGold)" strokeWidth="0.8" strokeLinecap="round" opacity="0.5" />
    <path d="M130 10 C140 10 145 14 155 14 C162 14 166 10 175 10"
      stroke="url(#ornGold)" strokeWidth="0.6" strokeLinecap="round" opacity="0.3" />
    {/* Small dots */}
    <circle cx="45" cy="10" r="1.2" fill="#c9a84c" fillOpacity="0.4" />
    <circle cx="195" cy="10" r="1.2" fill="#c9a84c" fillOpacity="0.4" />
  </svg>
);

/* ── Corner clasp ornament (more detailed) ── */
const CornerClasp = ({ position }: { position: 'tl' | 'tr' | 'bl' | 'br' }) => {
  const rotations = { tl: '', tr: 'scale(-1,1)', bl: 'scale(1,-1)', br: 'scale(-1,-1)' };
  const positions = {
    tl: 'top-1 left-1',
    tr: 'top-1 right-1',
    bl: 'bottom-1 left-1',
    br: 'bottom-1 right-1',
  };
  return (
    <svg
      viewBox="0 0 32 32"
      className={`absolute ${positions[position]} w-8 h-8 sm:w-10 sm:h-10`}
      style={{ transform: rotations[position] }}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M2 2 L14 2 C14 2 12 4 12 6 L12 8" stroke="#c9a84c" strokeWidth="1.2" strokeOpacity="0.5" strokeLinecap="round" />
      <path d="M2 2 L2 14 C2 14 4 12 6 12 L8 12" stroke="#c9a84c" strokeWidth="1.2" strokeOpacity="0.5" strokeLinecap="round" />
      <circle cx="2" cy="2" r="1.5" fill="#c9a84c" fillOpacity="0.4" />
      <path d="M6 6 L4 8 M6 6 L8 4" stroke="#c9a84c" strokeWidth="0.6" strokeOpacity="0.3" />
    </svg>
  );
};

/* ── Ink stain decorative element ── */
const InkStain = ({ className }: { className: string }) => (
  <div
    className={`absolute pointer-events-none ${className}`}
    style={{
      background: 'radial-gradient(ellipse, rgba(80,60,30,0.08) 0%, rgba(60,40,15,0.04) 40%, transparent 70%)',
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
      <SvgFilters />

      {/* ══════ OUTER BOOK — 3D leather cover ══════ */}
      <div
        className="relative rounded-xl"
        style={{
          transform: 'rotateX(1deg)',
          transformOrigin: 'center bottom',
          boxShadow:
            '0 12px 50px rgba(0,0,0,0.8), 0 4px 20px rgba(0,0,0,0.6), inset 0 1px 0 rgba(201,168,76,0.12), 0 -2px 0 rgba(40,25,10,1)',
        }}
      >
        {/* Leather base */}
        <div
          className="absolute inset-0 rounded-xl"
          style={{
            background:
              'radial-gradient(ellipse at 25% 15%, #4a3020 0%, #2c1a0e 40%, #1a0f08 70%, #0f0805 100%)',
          }}
        />

        {/* Leather grain texture via SVG filter */}
        <div
          className="absolute inset-0 rounded-xl opacity-30 pointer-events-none"
          style={{ filter: 'url(#leatherGrain)' }}
        />

        {/* Leather tooling / emboss lines */}
        <div
          className="absolute inset-3 rounded-lg pointer-events-none border border-gold/15"
          style={{
            boxShadow: 'inset 0 0 0 1px rgba(201,168,76,0.05)',
          }}
        />
        <div
          className="absolute inset-5 rounded-md pointer-events-none border border-gold/8"
        />

        {/* Corner clasps */}
        <CornerClasp position="tl" />
        <CornerClasp position="tr" />
        <CornerClasp position="bl" />
        <CornerClasp position="br" />

        {/* ── Inner content ── */}
        <div className="relative p-4 sm:p-6 md:p-8">

          {/* Title / Header */}
          <div className="flex items-center justify-between mb-1 sm:mb-2">
            <h1
              className="text-xl sm:text-2xl md:text-3xl font-bold uppercase tracking-[0.15em]"
              style={{
                fontFamily: serifFont,
                background: 'linear-gradient(180deg, #f0e0a0 0%, #d4b050 40%, #a07830 80%, #806020 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.8))',
              }}
            >
              Гримуар охотника
            </h1>
            <span
              className="text-amber-300/30 text-[10px] sm:text-xs tracking-wider italic"
              style={{ fontFamily: serifFont }}
            >
              Изучено: {killedCount} / {total}
            </span>
          </div>

          {/* Top ornament */}
          <div className="flex justify-center mb-3 sm:mb-4">
            <BookOrnament />
          </div>

          {/* ══════ PAGES AREA ══════ */}
          <div
            className="relative rounded-sm overflow-hidden"
            style={{
              boxShadow:
                'inset 0 3px 12px rgba(0,0,0,0.6), inset 0 -2px 8px rgba(0,0,0,0.4), 0 1px 0 rgba(201,168,76,0.08)',
            }}
          >
            {/* — Parchment base color — */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                background:
                  'linear-gradient(170deg, #32291e 0%, #28211a 20%, #2e2518 40%, #251e15 60%, #2b2319 80%, #32291e 100%)',
              }}
            />

            {/* — Paper grain via SVG feTurbulence — */}
            <div
              className="absolute inset-0 pointer-events-none opacity-20"
              style={{ filter: 'url(#parchmentNoise)' }}
            />

            {/* — Foxing / age spots scattered across the page — */}
            <InkStain className="w-24 h-20 top-[10%] left-[5%]" />
            <InkStain className="w-32 h-24 top-[60%] right-[8%]" />
            <InkStain className="w-20 h-28 top-[30%] right-[45%]" />
            <InkStain className="w-16 h-16 bottom-[5%] left-[20%]" />
            <InkStain className="w-28 h-20 top-[5%] right-[25%]" />

            {/* — Burn / scorch marks on edges — */}
            <div
              className="absolute top-0 left-0 w-full h-3 pointer-events-none"
              style={{
                background:
                  'linear-gradient(to bottom, rgba(60,40,15,0.3) 0%, transparent 100%)',
              }}
            />
            <div
              className="absolute bottom-0 left-0 w-full h-3 pointer-events-none"
              style={{
                background:
                  'linear-gradient(to top, rgba(60,40,15,0.3) 0%, transparent 100%)',
              }}
            />

            {/* — Deep vignette for worn edges — */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                boxShadow:
                  'inset 0 0 50px rgba(0,0,0,0.5), inset 0 0 100px rgba(0,0,0,0.25), inset 0 0 150px rgba(0,0,0,0.1)',
              }}
            />

            {/* — Book spine / center gutter (desktop only) — */}
            <div className="hidden md:block absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-8 z-10 pointer-events-none">
              {/* Spine shadow / valley */}
              <div
                className="w-full h-full"
                style={{
                  background:
                    'linear-gradient(90deg, transparent 0%, rgba(0,0,0,0.4) 20%, rgba(0,0,0,0.7) 45%, rgba(0,0,0,0.8) 50%, rgba(0,0,0,0.7) 55%, rgba(0,0,0,0.4) 80%, transparent 100%)',
                }}
              />
              {/* Stitching thread */}
              <div
                className="absolute top-6 bottom-6 left-1/2 -translate-x-1/2 w-px"
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(to bottom, rgba(201,168,76,0.35) 0px, rgba(201,168,76,0.35) 6px, transparent 6px, transparent 14px)',
                }}
              />
              {/* Stitch holes */}
              <div
                className="absolute top-6 bottom-6 left-1/2 -translate-x-[3px] w-[5px]"
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(to bottom, transparent 0px, transparent 5px, rgba(201,168,76,0.15) 5px, rgba(201,168,76,0.15) 7px, transparent 7px, transparent 14px)',
                }}
              />
            </div>

            {/* — Page curl effect (bottom-right corner) — */}
            <div
              className="hidden md:block absolute bottom-0 right-0 w-12 h-12 z-10 pointer-events-none"
              style={{
                background:
                  'linear-gradient(315deg, rgba(50,40,25,0.9) 0%, rgba(40,32,20,0.6) 30%, transparent 60%)',
                borderTopLeftRadius: '8px',
              }}
            />
            <div
              className="hidden md:block absolute bottom-[2px] right-[2px] w-8 h-8 z-10 pointer-events-none"
              style={{
                background:
                  'linear-gradient(315deg, rgba(70,55,30,0.5) 0%, transparent 50%)',
                borderTopLeftRadius: '12px',
                boxShadow: '-2px -2px 4px rgba(0,0,0,0.3)',
              }}
            />

            {/* ── Actual spread content ── */}
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
                className="text-green-400/50 text-[10px] sm:text-xs flex items-center gap-1.5 italic tracking-wider"
                style={{ fontFamily: serifFont }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                Запись изучена
              </span>
            ) : (
              <span
                className="text-amber-300/20 text-[10px] sm:text-xs flex items-center gap-1.5 italic tracking-wider"
                style={{ fontFamily: serifFont }}
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
