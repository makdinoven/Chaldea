import { useCallback, useEffect, useRef, useState } from 'react';
import type { ShieldParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';
import { SHIELD_CODE, SHIELD_MIN_GAP_MS, shieldParried } from './warrior';

/*
  Playing the party shield, however it is drawn: the clock, the turns of the
  shield (buttons, arrow keys), each blow landing — turned aside or not.
  Rules as the server has them (challenges.py shield_verdict).
*/

const KEYS: Record<string, number> = { ArrowLeft: 0, KeyA: 0, ArrowUp: 1, KeyW: 1, ArrowRight: 2, KeyD: 2 };

export type ShieldPhase = 'ready' | 'playing' | 'over';

/** A blow that has landed: where, whether the shield met it, when (performance.now()). */
export interface ShieldFlash {
  side: number;
  good: boolean;
  at: number;
}

interface Options {
  params: ShieldParams;
  onDone: (presses: number[], outcome: 'open') => void;
  onPress?: (presses: number[]) => void;
  /** A blow got through: the picture shakes. */
  onHit?: () => void;
  /** Keep `now` (ms since the start) in state for a picture drawn by React; a 3D picture reads `startedAt` itself. */
  trackNow?: boolean;
}

export const useShield = ({ params, onDone, onPress, onHit, trackNow = true }: Options) => {
  const [phase, setPhase] = useState<ShieldPhase>('ready');
  const [side, setSide] = useState(params.start_side);
  const [now, setNow] = useState(0);
  const [flash, setFlash] = useState<ShieldFlash | null>(null);
  const [parried, setParried] = useState(0);
  const presses = useRef<number[]>([]);
  /** performance.now() at the start. */
  const startedAt = useRef(0);
  const landed = useRef(0);
  const done = useRef(false);

  const finish = useCallback(() => {
    if (done.current) return;
    done.current = true;
    setPhase('over');
    onDone(presses.current, 'open');
  }, [onDone]);

  const turn = useCallback(
    (to: number) => {
      if (phase !== 'playing' || done.current) return;
      const t = Math.round(performance.now() - startedAt.current);
      const last = presses.current[presses.current.length - 1];
      if (last !== undefined && t - Math.floor(last / SHIELD_CODE) < SHIELD_MIN_GAP_MS) return;
      setSide(to);
      presses.current.push(t * SHIELD_CODE + to);
      onPress?.([...presses.current]);
    },
    [phase, onPress],
  );

  // The clock, and each blow as it lands.
  useEffect(() => {
    if (phase !== 'playing') return;
    let frame = 0;
    const tick = () => {
      const t = performance.now() - startedAt.current;
      if (trackNow) setNow(t);
      while (landed.current < params.blows.length && params.blows[landed.current].at_ms <= t) {
        const blow = params.blows[landed.current];
        landed.current += 1;
        // Counted with this blow and without it: did it meet the shield?
        const total = shieldParried(params, presses.current, blow.at_ms);
        const good = total > shieldParried(params, presses.current, blow.at_ms - 1);
        setParried(total);
        setFlash({ side: blow.side, good, at: performance.now() });
        playDungeonSound(good ? 'disarm' : 'trap');
        if (!good) onHit?.();
      }
      if (t >= params.time_limit_ms) {
        finish();
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [phase, params, finish, onHit, trackNow]);

  useEffect(() => {
    if (phase !== 'playing') return;
    const onKey = (e: KeyboardEvent) => {
      const to = KEYS[e.code];
      if (to === undefined || e.repeat) return;
      e.preventDefault();
      turn(to);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, turn]);

  const begin = useCallback(() => {
    startedAt.current = performance.now();
    setPhase('playing');
  }, []);

  return { phase, side, now, flash, parried, startedAt, begin, turn };
};
