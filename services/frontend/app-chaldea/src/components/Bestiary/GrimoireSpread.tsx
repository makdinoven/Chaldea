import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import type { BestiaryEntry } from '../../api/bestiary';
import GrimoirePageAvatar from './GrimoirePageAvatar';
import GrimoirePageInfo from './GrimoirePageInfo';
import { MagicThreads, ArcaneCircle } from './GrimoireMagic';

const serifFont = "'Georgia', 'Palatino Linotype', 'Palatino', serif";

interface GrimoireSpreadProps {
  entry: BestiaryEntry;
  direction: number;
}

/* ── Decorative overlays ── */
const WaterStain = ({ className }: { className: string }) => (
  <div
    className={`absolute pointer-events-none rounded-full ${className}`}
    style={{
      background:
        'radial-gradient(ellipse, transparent 40%, rgba(80,60,25,0.04) 50%, rgba(80,60,25,0.06) 55%, transparent 65%)',
    }}
  />
);

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

const PageOverlays = ({ side }: { side: 'left' | 'right' }) => (
  <>
    <div
      className="absolute inset-0 pointer-events-none z-[2]"
      style={{
        background: side === 'left'
          ? 'linear-gradient(110deg, rgba(200,180,120,0.03) 0%, transparent 40%, rgba(0,0,0,0.08) 100%)'
          : 'linear-gradient(250deg, rgba(0,0,0,0.1) 0%, transparent 30%, rgba(200,180,120,0.02) 100%)',
      }}
    />
    <div
      className="absolute inset-0 pointer-events-none opacity-[0.025] z-[2]"
      style={{
        backgroundImage:
          'repeating-linear-gradient(to bottom, transparent 0px, transparent 26px, rgba(160,120,60,1) 26px, rgba(160,120,60,1) 27px)',
      }}
    />
    {side === 'left' ? (
      <>
        <WaterStain className="w-28 h-28 -top-4 -right-2 opacity-80" />
        <WornLine className="w-40 top-[15%] left-[10%]" angle={-3} />
      </>
    ) : (
      <>
        <WaterStain className="w-20 h-20 bottom-[10%] right-[5%] opacity-70" />
        <WornLine className="w-32 top-[80%] right-[8%]" angle={1} />
      </>
    )}
  </>
);

/* ── Parchment texture for the back of a turning page ── */
const ParchmentBack = () => (
  <div
    className="absolute inset-0"
    style={{
      background:
        'linear-gradient(170deg, #dfd0b8 0%, #d5c5a8 30%, #e0d2ba 60%, #d8c8b0 100%)',
    }}
  >
    <div
      className="absolute inset-0 opacity-15 mix-blend-multiply pointer-events-none"
      style={{ backgroundImage: 'url(/textures/paper.png)', backgroundRepeat: 'repeat' }}
    />
    <div
      className="absolute inset-0 pointer-events-none"
      style={{ boxShadow: 'inset 0 0 40px rgba(140,110,60,0.25)' }}
    />
    <div
      className="absolute inset-0 opacity-10 mix-blend-multiply pointer-events-none"
      style={{ backgroundImage: 'url(/textures/old-wall.png)', backgroundRepeat: 'repeat' }}
    />
  </div>
);

/* ═══════════════════════════════════════════════════
   3D Page Turn — only ONE half flips, the other stays.

   Forward (→): RIGHT page flips left around the spine.
     The new content is underneath. Left page stays.
   Backward (←): LEFT page flips right around the spine.
     The new content is underneath. Right page stays.
   ═══════════════════════════════════════════════════ */

const TURN_DURATION = 0.7;

const GrimoireSpread = ({ entry, direction }: GrimoireSpreadProps) => {
  const [mobileSubPage, setMobileSubPage] = useState(0);

  // Track turning state
  const [isTurning, setIsTurning] = useState(false);
  const [turnDir, setTurnDir] = useState(0);
  const [turnKey, setTurnKey] = useState(0);
  const prevEntryIdRef = useRef(entry.id);

  // Detect entry change → trigger page turn animation
  useEffect(() => {
    if (entry.id !== prevEntryIdRef.current && direction !== 0) {
      setTurnDir(direction);
      setTurnKey((k) => k + 1);
      setIsTurning(true);
      prevEntryIdRef.current = entry.id;

      // Auto-clear after animation
      const timer = setTimeout(() => {
        setIsTurning(false);
      }, TURN_DURATION * 1000);
      return () => clearTimeout(timer);
    }
    prevEntryIdRef.current = entry.id;
  }, [entry.id, direction]);

  return (
    <div className="w-full">
      {/* ══ Desktop: two-page spread ══ */}
      <div className="hidden md:block" style={{ perspective: '2000px' }}>
        <div className="relative min-h-[450px] lg:min-h-[520px]">

          {/* ── Base layer: always shows CURRENT (new) content ── */}
          <div className="grid grid-cols-2 min-h-[450px] lg:min-h-[520px]">
            {/* Left page */}
            <div className="relative pr-4" style={{ clipPath: 'url(#raggedLeft)' }}>
              <PageOverlays side="left" />
              <MagicThreads side="left" />
              {/* Faint arcane circle watermark behind avatar */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[1] opacity-[0.06]">
                <ArcaneCircle size={280} />
              </div>
              <GrimoirePageAvatar entry={entry} />
            </div>
            {/* Right page */}
            <div className="relative pl-4" style={{ clipPath: 'url(#raggedRight)' }}>
              <PageOverlays side="right" />
              <MagicThreads side="right" />
              <GrimoirePageInfo entry={entry} />
            </div>
          </div>

          {/* ── Turning page overlay — only covers ONE half ── */}
          <AnimatePresence>
            {isTurning && (
              <>
                {/* The flipping page front (parchment covering old content) */}
                <motion.div
                  key={`flip-front-${turnKey}`}
                  className="absolute top-0 bottom-0 overflow-hidden z-[5]"
                  style={{
                    width: '50%',
                    /* Forward: right page flips. Backward: left page flips */
                    left: turnDir > 0 ? '50%' : 0,
                    right: turnDir > 0 ? 0 : undefined,
                    transformOrigin: turnDir > 0 ? 'left center' : 'right center',
                    transformStyle: 'preserve-3d',
                  }}
                  initial={{ rotateY: 0 }}
                  animate={{ rotateY: turnDir > 0 ? -180 : 180 }}
                  exit={{ rotateY: turnDir > 0 ? -180 : 180 }}
                  transition={{
                    duration: TURN_DURATION,
                    ease: [0.3, 0.1, 0.2, 1],
                  }}
                >
                  {/* Front face — parchment (what you see before it flips) */}
                  <div
                    className="absolute inset-0"
                    style={{ backfaceVisibility: 'hidden' }}
                  >
                    <ParchmentBack />
                  </div>

                  {/* Back face — also parchment (what you see after it flips) */}
                  <div
                    className="absolute inset-0"
                    style={{
                      backfaceVisibility: 'hidden',
                      transform: 'rotateY(180deg)',
                    }}
                  >
                    <ParchmentBack />
                  </div>
                </motion.div>

                {/* Shadow that follows the turning page */}
                <motion.div
                  key={`flip-shadow-${turnKey}`}
                  className="absolute top-0 bottom-0 z-[4] pointer-events-none"
                  style={{
                    width: '15%',
                  }}
                  initial={{
                    left: turnDir > 0 ? '50%' : '35%',
                    opacity: 0.4,
                  }}
                  animate={{
                    left: turnDir > 0 ? '35%' : '50%',
                    opacity: 0,
                  }}
                  transition={{
                    duration: TURN_DURATION,
                    ease: [0.3, 0.1, 0.2, 1],
                  }}
                >
                  <div
                    className="w-full h-full"
                    style={{
                      background: turnDir > 0
                        ? 'linear-gradient(to left, rgba(0,0,0,0.35), transparent)'
                        : 'linear-gradient(to right, rgba(0,0,0,0.35), transparent)',
                    }}
                  />
                </motion.div>
              </>
            )}
          </AnimatePresence>
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

        <AnimatePresence mode="wait" custom={direction}>
          <motion.div
            key={`${entry.id}-${mobileSubPage}`}
            initial={{ opacity: 0, x: direction > 0 ? 60 : -60 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: direction > 0 ? -60 : 60 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className="relative"
          >
            <WaterStain className="w-16 h-16 top-[20%] right-[5%] opacity-60" />
            {mobileSubPage === 0 ? (
              <GrimoirePageAvatar entry={entry} />
            ) : (
              <GrimoirePageInfo entry={entry} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
};

export default GrimoireSpread;
