import { useCallback, useEffect, useRef, useState } from 'react';
import type { ShadowParams, StarsParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';
import {
  advanceShadow,
  freshShadow,
  SHADOW_MIN_GAP_MS,
  starsTurn,
  starsWhole,
  type ShadowOutcome,
  type ShadowState,
} from './intel';

/*
  Playing the scouting and reading games, however they are drawn: the clock,
  the moves, the end. The newest state is in `live` for a 3D picture.
*/

// --- scouting: step through the shadows ---

export const useShadow = ({
  params,
  onDone,
  onPress,
}: {
  params: ShadowParams;
  onDone: (steps: number[], outcome: ShadowOutcome) => void;
  onPress?: (steps: number[]) => void;
}) => {
  const [playing, setPlaying] = useState(false);
  const [shadow, setShadow] = useState<ShadowState>(freshShadow);
  const [outcome, setOutcome] = useState<ShadowOutcome | null>(null);
  const live = useRef<ShadowState>(freshShadow());
  const steps = useRef<number[]>([]);
  const started = useRef(0);
  const done = useRef(false);
  const timeBar = useRef<HTMLDivElement>(null);

  const finish = useCallback(
    (how: ShadowOutcome) => {
      if (done.current) return;
      done.current = true;
      setPlaying(false);
      setOutcome(how);
      playDungeonSound(how === 'open' ? 'disarm' : 'trap');
      onDone(steps.current, how);
    },
    [onDone],
  );

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const now = performance.now() - started.current;
      const next = advanceShadow(params, live.current, steps.current, now);
      live.current = next;
      setShadow(next);
      if (timeBar.current) timeBar.current.style.width = `${Math.max(0, 1 - now / params.time_limit_ms) * 100}%`;
      if (next.over) {
        finish(next.over);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, params, finish]);

  /** One step forward: taken in from the next tick not yet played, as the server will. */
  const step = useCallback(() => {
    if (!playing || done.current) return;
    const last = steps.current[steps.current.length - 1] ?? -Infinity;
    const t = Math.max(Math.ceil(performance.now() - started.current), live.current.t, last + SHADOW_MIN_GAP_MS);
    if (steps.current.length > params.cells) return;
    steps.current.push(t);
    playDungeonSound('step');
    onPress?.([...steps.current]);
  }, [playing, params.cells, onPress]);

  useEffect(() => {
    if (!playing) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.code !== 'Space' && e.code !== 'ArrowRight' && e.code !== 'Enter') || e.repeat) return;
      e.preventDefault();
      step();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [playing, step]);

  const begin = useCallback(() => {
    started.current = performance.now();
    setPlaying(true);
  }, []);

  return { playing, shadow, outcome, live, started, timeBar, begin, step };
};

// --- reading: turn the geared rings ---

export const useStars = ({
  params,
  onDone,
  onPress,
}: {
  params: StarsParams;
  onDone: (turns: number[], outcome: 'open' | 'time') => void;
  onPress?: (turns: number[]) => void;
}) => {
  const [playing, setPlaying] = useState(false);
  const [offsets, setOffsets] = useState<number[]>(params.offsets);
  const [outcome, setOutcome] = useState<'open' | 'time' | null>(null);
  const turns = useRef<number[]>([]);
  const lastTurn = useRef(-Infinity);
  const done = useRef(false);
  const timeBar = useRef<HTMLDivElement>(null);

  const finish = useCallback(
    (how: 'open' | 'time') => {
      if (done.current) return;
      done.current = true;
      setPlaying(false);
      setOutcome(how);
      playDungeonSound(how === 'open' ? 'disarm' : 'trap');
      onDone(turns.current, how);
    },
    [onDone],
  );

  useEffect(() => {
    if (!playing) return;
    const start = performance.now();
    let frame = 0;
    const tick = () => {
      const t = performance.now() - start;
      if (timeBar.current) timeBar.current.style.width = `${Math.max(0, 1 - t / params.time_limit_ms) * 100}%`;
      if (t >= params.time_limit_ms) {
        finish('time');
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, params.time_limit_ms, finish]);

  const turn = useCallback(
    (ring: number) => {
      if (!playing || done.current) return;
      const now = performance.now();
      if (now - lastTurn.current < 60) return;
      lastTurn.current = now;
      turns.current.push(ring);
      onPress?.([...turns.current]);
      playDungeonSound('step');
      setOffsets((prev) => {
        const next = starsTurn(prev, ring, params.steps);
        if (starsWhole(next)) setTimeout(() => finish('open'), 0);
        return next;
      });
    },
    [playing, params.steps, onPress, finish],
  );

  const begin = useCallback(() => setPlaying(true), []);

  return { playing, offsets, outcome, timeBar, begin, turn };
};
