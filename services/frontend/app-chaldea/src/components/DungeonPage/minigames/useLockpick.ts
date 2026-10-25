import { useCallback, useEffect, useRef, useState } from 'react';
import type { LockpickParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';
import { freshLock, MIN_PRESS_GAP_MS, press, type LockOutcome, type LockState } from './lockpick';

/*
  Playing the lock, whichever way it is drawn (the 2D plate or the 3D lock):
  the clock, the presses, the time running out. What happened last is kept in
  `live` for a picture redrawn every frame (the pins, the sparks).
*/

export interface LockLive {
  started: boolean;
  /** performance.now() at the start. */
  startAt: number;
  lock: LockState;
  /** When (performance.now()) the last strain, set pin and press happened — for the effects. */
  strainAt: number;
  setAt: number;
  pressAt: number;
}

interface Options {
  params: LockpickParams;
  onDone: (presses: number[], outcome: LockOutcome) => void;
  onPress?: (presses: number[]) => void;
  /** A strain shakes the picture: the 2D plate jolts. */
  onStrain?: () => void;
}

export const useLockpick = ({ params, onDone, onPress, onStrain }: Options) => {
  const [started, setStarted] = useState(false);
  const [lock, setLock] = useState<LockState>(freshLock);
  const live = useRef<LockLive>({
    started: false,
    startAt: 0,
    lock: freshLock(),
    strainAt: -Infinity,
    setAt: -Infinity,
    pressAt: -Infinity,
  });
  const presses = useRef<number[]>([]);
  const doneRef = useRef(false);
  const timeBar = useRef<HTMLDivElement>(null);

  const update = useCallback((next: LockState) => {
    live.current.lock = next;
    setLock(next);
  }, []);

  const finish = useCallback(
    (state: LockState) => {
      if (doneRef.current || !state.over) return;
      doneRef.current = true;
      onDone(presses.current, state.over);
    },
    [onDone],
  );

  // The running time (and the time running out), straight to the DOM each frame.
  useEffect(() => {
    if (!started) return;
    let frame = 0;
    const tick = () => {
      const t = performance.now() - live.current.startAt;
      const state = live.current.lock;
      if (!state.over && t > params.time_limit_ms) {
        const timedOut: LockState = { ...state, over: 'time' };
        update(timedOut);
        finish(timedOut);
        return;
      }
      if (timeBar.current) timeBar.current.style.width = `${Math.max(0, 100 - (t / params.time_limit_ms) * 100)}%`;
      if (!state.over) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [started, params, finish, update]);

  const doPress = useCallback(() => {
    const state = live.current.lock;
    if (!live.current.started || state.over) return;
    const now = performance.now();
    const t = Math.round(now - live.current.startAt);
    const last = presses.current[presses.current.length - 1];
    if (last !== undefined && t - last < MIN_PRESS_GAP_MS) return;
    presses.current.push(t);
    onPress?.([...presses.current]);
    live.current.pressAt = now;
    const next = press(params, state, t);
    update(next);
    if (next.set > state.set) {
      live.current.setAt = now;
      playDungeonSound('disarm');
    } else if (next.strains > state.strains) {
      live.current.strainAt = now;
      playDungeonSound('vote');
      onStrain?.();
    }
    finish(next);
  }, [params, finish, onPress, onStrain, update]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== 'Space' && e.code !== 'Enter') return;
      e.preventDefault();
      doPress();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [doPress]);

  const begin = useCallback(() => {
    live.current.startAt = performance.now();
    live.current.started = true;
    setStarted(true);
  }, []);

  return { started, lock, live, timeBar, begin, doPress };
};
