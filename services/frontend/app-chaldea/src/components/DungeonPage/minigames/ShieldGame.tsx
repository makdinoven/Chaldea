import { useCallback } from 'react';
import { motion, useAnimationControls } from 'motion/react';
import type { ShieldParams } from '../../../api/dungeons';
import { useShield } from './useShield';

/*
  The party shield ("Стойка"): blows come from the left, from above, from the
  right. Each is shown flying in a moment before it lands; turn the shield to
  meet it — buttons, or the arrow keys. How many are turned aside is how firmly
  the shield is held until the party moves on.
  Rules as the server has them (challenges.py shield_verdict).
*/

/** Left, above, right: the lane's direction from the centre (x, y on a unit square). */
const SIDES = [
  { label: 'Слева', arrow: '←', dx: -1, dy: 0 },
  { label: 'Сверху', arrow: '↑', dx: 0, dy: -1 },
  { label: 'Справа', arrow: '→', dx: 1, dy: 0 },
];
/** How far out (share of the arena's half) a blow is first seen. */
const LANE_START = 0.95;
const LANE_END = 0.3;
const FLASH_MS = 350;

interface ShieldGameProps {
  params: ShieldParams;
  offClass: boolean;
  onDone: (presses: number[], outcome: 'open') => void;
  onPress?: (presses: number[]) => void;
}

const ShieldGame = ({ params, offClass, onDone, onPress }: ShieldGameProps) => {
  const arena = useAnimationControls();
  const onHit = useCallback(() => void arena.start({ x: [0, -7, 7, -4, 4, 0], transition: { duration: 0.3 } }), [arena]);
  const { phase, side, now, flash, parried, begin, turn } = useShield({ params, onDone, onPress, onHit });

  // Blows in flight: shown from warn_ms before they land.
  const flying = params.blows.filter((b) => b.at_ms - params.warn_ms <= now && now < b.at_ms);
  const flashOn = flash && performance.now() - flash.at < FLASH_MS;

  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Удары летят слева, сверху и справа. Поверните щит навстречу каждому, пока он не долетел. Чем больше отобьёте,
        тем крепче щит прикроет отряд на следующем переходе.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Щит — ремесло воина. Вам ударов достанется больше, а заметите вы их позже.
        </p>
      )}

      <motion.div
        animate={arena}
        className="relative w-56 h-44 sm:w-64 sm:h-48 rounded-card border border-white/15 bg-gradient-to-b from-[#2a2622] to-[#141210] shadow-card overflow-hidden"
      >
        {/* The lanes */}
        {SIDES.map((s, i) => (
          <div
            key={i}
            className="absolute bg-white/5"
            style={
              s.dy
                ? { left: '50%', top: 0, width: 6, height: '62%', transform: 'translateX(-50%)' }
                : { top: '62%', [s.dx < 0 ? 'left' : 'right']: 0, height: 6, width: '50%', transform: 'translateY(-50%)' }
            }
          />
        ))}
        {/* Blows in flight */}
        {flying.map((b) => {
          const s = SIDES[b.side];
          const k = LANE_START - (LANE_START - LANE_END) * (1 - (b.at_ms - now) / params.warn_ms);
          return (
            <div
              key={b.at_ms}
              className="absolute w-5 h-5 -ml-2.5 -mt-2.5 rounded-full bg-site-red shadow-[0_0_14px_rgba(255,80,80,0.9)]"
              style={{ left: `${50 + s.dx * k * 50}%`, top: `${62 + s.dy * k * 62}%` }}
            />
          );
        })}
        {/* The warrior and the shield */}
        <div className="absolute left-1/2 top-[62%] -translate-x-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-[#d9cdb4] border-2 border-[#8a7d66]" />
        <div
          className={`absolute left-1/2 top-[62%] w-16 h-16 -ml-8 -mt-8 rounded-full transition-transform duration-75 ${
            flashOn ? (flash.good ? 'drop-shadow-[0_0_10px_rgba(118,166,189,1)]' : 'drop-shadow-[0_0_10px_rgba(255,80,80,1)]') : ''
          }`}
          style={{
            border: '5px solid transparent',
            borderTopColor: flashOn && !flash.good ? '#ff6b6b' : '#c8a96a',
            transform: `rotate(${(side - 1) * 90}deg)`,
          }}
        />
        {flashOn && (
          <p
            className={`absolute left-0 right-0 bottom-2 text-center text-xs font-medium ${flash.good ? 'text-site-blue' : 'text-site-red'}`}
          >
            {flash.good ? 'Отбито!' : 'Удар прошёл!'}
          </p>
        )}
      </motion.div>

      <div className="grid grid-cols-3 gap-2 w-full max-w-xs">
        {SIDES.map((s, i) => (
          <button
            key={i}
            type="button"
            disabled={phase !== 'playing'}
            onPointerDown={(e) => {
              e.preventDefault();
              turn(i);
            }}
            className={`py-3 rounded-card border text-sm touch-manipulation transition-colors duration-150 ease-site ${
              side === i && phase === 'playing'
                ? 'border-gold/70 bg-gold/15 text-white'
                : 'border-white/15 bg-black/40 text-white/70 enabled:hover:border-white/40'
            } disabled:opacity-50`}
          >
            <span className="block text-lg leading-none">{s.arrow}</span>
            <span className="text-[11px]">{s.label}</span>
          </button>
        ))}
      </div>

      <div className="w-full max-w-xs flex items-center gap-3">
        <span className="text-white/60 text-xs tabular-nums whitespace-nowrap">
          отбито {parried} из {params.blows.length}
        </span>
        <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full bg-gold/80"
            style={{ width: `${Math.max(0, 100 - (Math.min(now, params.time_limit_ms) / params.time_limit_ms) * 100)}%` }}
          />
        </div>
      </div>

      {phase === 'ready' ? (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      ) : (
        <p className="text-white/50 text-xs h-5 text-center">
          {phase === 'playing' ? 'Стрелки ← ↑ → или кнопки.' : ''}
        </p>
      )}
    </div>
  );
};

export default ShieldGame;
