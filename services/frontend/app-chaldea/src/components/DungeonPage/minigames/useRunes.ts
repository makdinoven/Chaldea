import { useCallback, useEffect, useRef, useState } from 'react';
import type { RunesParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';

/*
  Playing the illusory wall, however it is drawn: the runes flash in order,
  then the mage touches them back; a wrong one counts as a mistake (a mage is
  forgiven one). Rules as the server has them (challenges.py runes_verdict).
*/

/** The pause between two flashes. */
export const RUNE_GAP_MS = 220;
const FLASH_SHOWN_MS = 250;

export type RunePhase = 'ready' | 'showing' | 'input' | 'over';
export type RuneOutcome = 'open' | 'broke' | 'short' | 'time';

interface Options {
  params: RunesParams;
  onDone: (inputs: number[], outcome: RuneOutcome) => void;
  onPress?: (inputs: number[]) => void;
  /** A wrong rune: the picture shakes. */
  onWrong?: () => void;
}

export const useRunes = ({ params, onDone, onPress, onWrong }: Options) => {
  const [phase, setPhase] = useState<RunePhase>('ready');
  const [lit, setLit] = useState<number | null>(null);
  const [step, setStep] = useState(0);
  const [mistakes, setMistakes] = useState(0);
  const [flash, setFlash] = useState<{ glyph: number; good: boolean } | null>(null);
  const [outcome, setOutcome] = useState<RuneOutcome | null>(null);
  const inputs = useRef<number[]>([]);
  const done = useRef(false);
  const timeBar = useRef<HTMLDivElement>(null);

  const finish = useCallback(
    (how: RuneOutcome) => {
      if (done.current) return;
      done.current = true;
      setPhase('over');
      setOutcome(how);
      onDone(inputs.current, how);
    },
    [onDone],
  );

  // Show the order, then hand over to the mage.
  useEffect(() => {
    if (phase !== 'showing') return;
    const timers: ReturnType<typeof setTimeout>[] = [];
    params.sequence.forEach((g, i) => {
      const at = i * (params.flash_ms + RUNE_GAP_MS);
      timers.push(setTimeout(() => setLit(g), at));
      timers.push(setTimeout(() => setLit(null), at + params.flash_ms));
    });
    timers.push(setTimeout(() => setPhase('input'), params.sequence.length * (params.flash_ms + RUNE_GAP_MS)));
    return () => timers.forEach(clearTimeout);
  }, [phase, params]);

  // The time to answer runs from the end of the showing.
  useEffect(() => {
    if (phase !== 'input') return;
    const start = performance.now();
    let frame = 0;
    const tick = () => {
      const t = performance.now() - start;
      if (timeBar.current) timeBar.current.style.width = `${Math.max(0, 100 - (t / params.time_limit_ms) * 100)}%`;
      if (t >= params.time_limit_ms) {
        finish('time');
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [phase, params, finish]);

  const touch = useCallback(
    (glyph: number) => {
      if (phase !== 'input' || done.current) return;
      inputs.current.push(glyph);
      onPress?.([...inputs.current]);
      if (glyph === params.sequence[step]) {
        setFlash({ glyph, good: true });
        playDungeonSound('disarm');
        const next = step + 1;
        setStep(next);
        if (next === params.sequence.length) finish('open');
      } else {
        setFlash({ glyph, good: false });
        playDungeonSound('vote');
        onWrong?.();
        const m = mistakes + 1;
        setMistakes(m);
        if (m > params.mistakes) finish('broke');
      }
      setTimeout(() => setFlash(null), FLASH_SHOWN_MS);
    },
    [phase, params, step, mistakes, finish, onPress, onWrong],
  );

  const begin = useCallback(() => setPhase('showing'), []);

  return { phase, lit, step, mistakes, flash, outcome, timeBar, begin, touch };
};
