import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import type { BestiaryEntry } from '../../api/bestiary';
import GrimoirePageAvatar from './GrimoirePageAvatar';
import GrimoirePageInfo from './GrimoirePageInfo';

const serifFont = "'Georgia', 'Palatino Linotype', 'Palatino', serif";

interface GrimoireSpreadProps {
  entry: BestiaryEntry;
  direction: number;
}

/* Page-turn animation — slight 3D rotation for realism */
const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 200 : -200,
    opacity: 0,
    rotateY: direction > 0 ? -8 : 8,
    scale: 0.97,
  }),
  center: {
    x: 0,
    opacity: 1,
    rotateY: 0,
    scale: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? -200 : 200,
    opacity: 0,
    rotateY: direction > 0 ? 8 : -8,
    scale: 0.97,
  }),
};

/* ── Water / coffee stain ring decoration ── */
const WaterStain = ({ className }: { className: string }) => (
  <div
    className={`absolute pointer-events-none rounded-full ${className}`}
    style={{
      background:
        'radial-gradient(ellipse, transparent 40%, rgba(80,60,25,0.04) 50%, rgba(80,60,25,0.06) 55%, transparent 65%)',
    }}
  />
);

/* ── Scratches / worn lines ── */
const WornLine = ({ className, angle }: { className: string; angle: number }) => (
  <div
    className={`absolute pointer-events-none ${className}`}
    style={{
      background: 'linear-gradient(90deg, transparent, rgba(200,180,120,0.03), transparent)',
      transform: `rotate(${angle}deg)`,
      height: '1px',
    }}
  />
);

const GrimoireSpread = ({ entry, direction }: GrimoireSpreadProps) => {
  const [mobileSubPage, setMobileSubPage] = useState(0);

  return (
    <AnimatePresence mode="wait" custom={direction}>
      <motion.div
        key={entry.id}
        custom={direction}
        variants={slideVariants}
        initial="enter"
        animate="center"
        exit="exit"
        transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
        className="w-full"
        style={{ transformStyle: 'preserve-3d' }}
      >
        {/* ══ Desktop: two-page spread ══ */}
        <div className="hidden md:grid md:grid-cols-2 min-h-[450px] lg:min-h-[520px]">

          {/* ── Left page ── */}
          <div
            className="relative pr-4"
            style={{ clipPath: 'url(#raggedLeft)' }}
          >
            {/* Page lighting — lighter from left (lamp effect) */}
            <div
              className="absolute inset-0 pointer-events-none z-[2]"
              style={{
                background:
                  'linear-gradient(110deg, rgba(200,180,120,0.03) 0%, transparent 40%, rgba(0,0,0,0.08) 100%)',
              }}
            />

            {/* Subtle horizontal ruled lines (like old paper) */}
            <div
              className="absolute inset-0 pointer-events-none opacity-[0.025] z-[2]"
              style={{
                backgroundImage:
                  'repeating-linear-gradient(to bottom, transparent 0px, transparent 26px, rgba(160,120,60,1) 26px, rgba(160,120,60,1) 27px)',
              }}
            />

            {/* Water stain / ring marks */}
            <WaterStain className="w-28 h-28 -top-4 -right-2 opacity-80" />
            <WornLine className="w-40 top-[15%] left-[10%]" angle={-3} />
            <WornLine className="w-24 top-[65%] left-[5%]" angle={2} />

            <GrimoirePageAvatar entry={entry} />
          </div>

          {/* ── Right page ── */}
          <div
            className="relative pl-4"
            style={{ clipPath: 'url(#raggedRight)' }}
          >
            {/* Page lighting — darker towards right edge (shadow from binding) */}
            <div
              className="absolute inset-0 pointer-events-none z-[2]"
              style={{
                background:
                  'linear-gradient(250deg, rgba(0,0,0,0.1) 0%, transparent 30%, rgba(200,180,120,0.02) 100%)',
              }}
            />

            {/* Ruled lines */}
            <div
              className="absolute inset-0 pointer-events-none opacity-[0.025] z-[2]"
              style={{
                backgroundImage:
                  'repeating-linear-gradient(to bottom, transparent 0px, transparent 26px, rgba(160,120,60,1) 26px, rgba(160,120,60,1) 27px)',
              }}
            />

            {/* Stains on right page */}
            <WaterStain className="w-20 h-20 bottom-[10%] right-[5%] opacity-70" />
            <WornLine className="w-32 top-[80%] right-[8%]" angle={1} />

            <GrimoirePageInfo entry={entry} />
          </div>
        </div>

        {/* ══ Mobile: single page with tabs ══ */}
        <div className="block md:hidden min-h-[350px]">
          <div className="flex mb-3 gap-1">
            <button
              onClick={() => setMobileSubPage(0)}
              className={`flex-1 py-2 text-xs sm:text-sm tracking-[0.15em] uppercase transition-colors duration-200 rounded-t-card ${
                mobileSubPage === 0
                  ? 'text-amber-200 bg-amber-900/20 border-b border-gold/30'
                  : 'text-amber-200/30 hover:text-amber-200/50'
              }`}
              style={{ fontFamily: serifFont }}
            >
              Портрет
            </button>
            <button
              onClick={() => setMobileSubPage(1)}
              className={`flex-1 py-2 text-xs sm:text-sm tracking-[0.15em] uppercase transition-colors duration-200 rounded-t-card ${
                mobileSubPage === 1
                  ? 'text-amber-200 bg-amber-900/20 border-b border-gold/30'
                  : 'text-amber-200/30 hover:text-amber-200/50'
              }`}
              style={{ fontFamily: serifFont }}
            >
              Сведения
            </button>
          </div>

          <div className="relative">
            <WaterStain className="w-16 h-16 top-[20%] right-[5%] opacity-60" />

            {mobileSubPage === 0 ? (
              <GrimoirePageAvatar entry={entry} />
            ) : (
              <GrimoirePageInfo entry={entry} />
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

export default GrimoireSpread;
