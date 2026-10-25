import { useCallback, useEffect, useRef, useState } from 'react';
import type { GateParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';
import { advanceGate, freshGate, GATE_MIN_TOGGLE_GAP_MS, type GateOutcome, type GateState } from './warrior';

/*
  Holding up a gate, however it is drawn: the grip (button, space), the gate
  played tick by tick exactly as the server replays it (challenges.py
  gate_verdict). The newest state is always in `live`; `gate` mirrors it in
  React state when the picture is drawn by React.
*/

interface Options {
  params: GateParams;
  onDone: (toggles: number[], outcome: GateOutcome) => void;
  onPress?: (toggles: number[]) => void;
  /** Keep `gate` in state every frame (a 2D picture); a 3D picture reads `live` itself. */
  trackState?: boolean;
}

export const useGate = ({ params, onDone, onPress, trackState = true }: Options) => {
  const [playing, setPlaying] = useState(false);
  const [gate, setGate] = useState<GateState>(freshGate);
  const [pressed, setPressed] = useState(false);
  const [outcome, setOutcome] = useState<GateOutcome | null>(null);
  const toggles = useRef<number[]>([]);
  const live = useRef<GateState>(freshGate());
  const started = useRef(0);
  const done = useRef(false);
  /** Bars drawn straight from the loop when React state is not kept. */
  const holdBar = useRef<HTMLDivElement>(null);
  const timeBar = useRef<HTMLDivElement>(null);

  const finish = useCallback(
    (how: GateOutcome) => {
      if (done.current) return;
      done.current = true;
      setPlaying(false);
      setOutcome(how);
      playDungeonSound(how === 'open' ? 'disarm' : 'trap');
      onDone(toggles.current, how);
    },
    [onDone],
  );

  /** Press or release: taken in from the next tick not yet played, as the server will. */
  const grip = useCallback(
    (hold: boolean) => {
      setPressed(hold);
      if (!playing || done.current || hold === (toggles.current.length % 2 === 1)) return;
      const last = toggles.current[toggles.current.length - 1] ?? -Infinity;
      const t = Math.max(Math.ceil(performance.now() - started.current), live.current.t, last + GATE_MIN_TOGGLE_GAP_MS);
      toggles.current.push(t);
      onPress?.([...toggles.current]);
    },
    [playing, onPress],
  );

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const next = advanceGate(params, live.current, toggles.current, performance.now() - started.current);
      live.current = next;
      if (trackState) setGate(next);
      if (holdBar.current) holdBar.current.style.height = `${Math.min(100, (next.held / params.hold_ms) * 100)}%`;
      if (timeBar.current) timeBar.current.style.width = `${Math.max(0, 1 - next.t / params.time_limit_ms) * 100}%`;
      if (next.over) {
        finish(next.over);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, params, finish, trackState]);

  useEffect(() => {
    if (!playing) return;
    const down = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.repeat) return;
      e.preventDefault();
      grip(true);
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return;
      e.preventDefault();
      grip(false);
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, [playing, grip]);

  const begin = useCallback(() => {
    started.current = performance.now();
    setPlaying(true);
  }, []);

  return { playing, gate, pressed, outcome, live, holdBar, timeBar, begin, grip };
};
