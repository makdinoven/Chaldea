import { useEffect, useRef } from 'react';
import { motion, useAnimationControls } from 'motion/react';
import type { LockpickParams } from '../../../api/dungeons';
import { pinHeight, type LockOutcome } from './lockpick';
import { useLockpick } from './useLockpick';

/*
  The lock: pins in a row behind an iron plate. The active pin bobs; a press
  while its tip is inside the gold shear band sets it and wakes the next. A
  press outside strains the pick (the plate jolts); one strain too many and it
  breaks. Space, Enter, a tap on the lock or the button all press.
*/

/** A pin waiting its turn rests low in its channel. */
const RESTING = -0.85;

const tipTop = (y: number) => `${((1 - y) / 2) * 100}%`;

interface LockpickGameProps {
  params: LockpickParams;
  /** Not a rogue: shown a warning; the lock itself is already harder. */
  offClass: boolean;
  /** The game is over: every press (ms from the start) and how it ended. */
  onDone: (presses: number[], outcome: LockOutcome) => void;
  /** Every press so far, after each one (to give up with them if the window is closed). */
  onPress?: (presses: number[]) => void;
}

const LockpickGame = ({ params, offClass, onDone, onPress }: LockpickGameProps) => {
  const plate = useAnimationControls();
  const { started, lock, live, timeBar, begin, doPress } = useLockpick({
    params,
    onDone,
    onPress,
    onStrain: () => void plate.start({ x: [0, -6, 6, -4, 4, 0], transition: { duration: 0.3 } }),
  });
  const tips = useRef<(HTMLDivElement | null)[]>([]);

  // The bobbing pin, drawn straight to the DOM each frame.
  useEffect(() => {
    if (!started) return;
    let frame = 0;
    const draw = () => {
      const { lock: state, startAt } = live.current;
      if (state.over) return;
      const tip = tips.current[state.set];
      if (tip) tip.style.top = tipTop(pinHeight(params.pins[state.set], performance.now() - startAt - state.wokeAt));
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [started, params, live]);

  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Поймайте момент, когда штифт входит в золотую полосу, и поддевайте — кнопкой, касанием замка или пробелом.
        Промах натягивает отмычку.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Замки — ремесло плута. Вам он поддаётся хуже: полоса уже, штифтов больше, отмычка хрупче.
        </p>
      )}

      <motion.div
        animate={plate}
        onPointerDown={doPress}
        className="rounded-card border border-white/15 bg-gradient-to-b from-[#3a3634] to-[#1e1b1a] p-3 sm:p-4 flex gap-2 sm:gap-3 shadow-card cursor-pointer touch-manipulation"
      >
        {params.pins.map((pin, i) => {
          const isSet = i < lock.set;
          const isActive = started && !lock.over && i === lock.set;
          return (
            <div key={i} className="relative w-8 sm:w-10 h-40 sm:h-48 rounded bg-black/70 overflow-hidden">
              {/* The shear band */}
              <div
                className={`absolute inset-x-0 border-y ${isSet ? 'bg-gold/30 border-gold' : 'bg-gold/15 border-gold/50'}`}
                style={{ top: tipTop(pin.center + pin.width), height: `${pin.width * 100}%` }}
              />
              {/* The pin: a brass rod rising from the bottom to its tip */}
              <div
                ref={(el) => {
                  tips.current[i] = el;
                }}
                className={`absolute inset-x-[28%] bottom-0 rounded-t-sm ${
                  isSet ? 'bg-gold' : isActive ? 'bg-[#d8b46a]' : 'bg-[#6e5a3a]'
                }`}
                style={{ top: tipTop(isSet ? pin.center : RESTING) }}
              />
            </div>
          );
        })}
      </motion.div>

      <div className="w-full max-w-xs flex items-center gap-3">
        <div className="flex gap-1" aria-label={`Запас отмычки: ${params.strains + 1 - lock.strains}`}>
          {Array.from({ length: params.strains + 1 }, (_, i) => (
            <span
              key={i}
              className={`w-2.5 h-2.5 rounded-full ${i < params.strains + 1 - lock.strains ? 'bg-site-blue' : 'bg-white/15'}`}
            />
          ))}
        </div>
        <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
          <div ref={timeBar} className="h-full bg-gold/70" style={{ width: '100%' }} />
        </div>
      </div>

      {!started ? (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      ) : (
        <button
          type="button"
          onPointerDown={(e) => {
            e.preventDefault();
            doPress();
          }}
          disabled={!!lock.over}
          className="btn-blue text-base px-10 py-3 w-full sm:w-auto disabled:opacity-50 touch-manipulation"
        >
          Поддеть
        </button>
      )}
    </div>
  );
};

export default LockpickGame;
