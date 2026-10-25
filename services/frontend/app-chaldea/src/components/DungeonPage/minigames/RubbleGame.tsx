import { useState } from 'react';
import { motion, useAnimationControls } from 'motion/react';
import type { ChallengeStep, RubbleParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';

/*
  The cave-in: a pile of stones, some of them holding the rest up. Deep cracks
  hint at a bearing stone — mostly truly. The warrior pulls stones out until
  the way is clear; pulling a bearing one brings the pile down (a brace holds
  once). Which stones bear only the server knows — every pull is asked of it.
*/

/** The pile from the top: three rows narrowing upwards. */
const ROWS = [[0, 1, 2, 3], [4, 5, 6], [7, 8]];
const CRACK_MARKS = ['', '╱', '╱╲', '╳╱'];
const CRACK_WORDS = ['Цел', 'Трещина', 'Глубокая трещина', 'Раскол — держит вес?'];

interface RubbleGameProps {
  params: RubbleParams;
  offClass: boolean;
  /** Pulls a stone; the server's answer, or null if the request failed. */
  onStep: (move: { index: number }) => Promise<ChallengeStep | null>;
}

const RubbleGame = ({ params, offClass, onStep }: RubbleGameProps) => {
  const [pulled, setPulled] = useState<Map<number, boolean>>(new Map());
  const [busy, setBusy] = useState(false);
  const pile = useAnimationControls();
  const cleared = [...pulled.values()].filter(Boolean).length;
  const collapses = [...pulled.values()].filter((safe) => !safe).length;

  const pull = async (index: number) => {
    if (busy || pulled.has(index)) return;
    setBusy(true);
    const step = await onStep({ index });
    setBusy(false);
    if (!step || step.safe == null) return;
    setPulled((prev) => new Map(prev).set(index, step.safe as boolean));
    if (step.safe) playDungeonSound('disarm');
    else {
      playDungeonSound('trap');
      void pile.start({ y: [0, 6, -3, 2, 0], transition: { duration: 0.4 } });
    }
  };

  const rows = ROWS.map((row) => row.filter((i) => i < params.cracks.length));
  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Вынимайте камни, пока не расчистите проход. Глубокие трещины — у камней, что держат завал (обычно), а держат его
        чаще нижние. Вынете такой — завал осыпется.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Завалы — дело воина. Трещины вам говорят меньше, а подпорок нет.
        </p>
      )}

      <motion.div
        animate={pile}
        className="flex flex-col-reverse items-center gap-1.5 rounded-card border border-white/15 bg-gradient-to-b from-[#2a2624] to-[#151312] p-3 sm:p-4 shadow-card"
      >
        {rows.map((row, r) => (
          <div key={r} className="flex gap-1.5">
            {row.map((i) => {
              const state = pulled.get(i);
              return (
                <button
                  key={i}
                  type="button"
                  disabled={busy || state !== undefined}
                  onClick={() => void pull(i)}
                  className={`w-14 h-11 sm:w-16 sm:h-12 rounded-[10px] border text-sm tracking-tighter transition-colors duration-150 ease-site touch-manipulation ${
                    state === true
                      ? 'border-dashed border-white/10 bg-transparent text-transparent'
                      : state === false
                        ? 'bg-site-red/40 border-site-red text-white'
                        : 'bg-[#6a686c] border-[#8a868a]/60 text-black/70 enabled:hover:bg-[#7a787c]'
                  }`}
                  aria-label={`Камень ${i + 1}: ${CRACK_WORDS[params.cracks[i]]}`}
                  title={CRACK_WORDS[params.cracks[i]]}
                >
                  {state === undefined ? CRACK_MARKS[params.cracks[i]] : state === false ? 'обвал' : ''}
                </button>
              );
            })}
          </div>
        ))}
      </motion.div>

      <div className="flex gap-4 text-xs text-white/60">
        <span>
          Расчищено: <span className="text-white tabular-nums">{cleared}</span> / {params.to_clear}
        </span>
        <span>
          Подпорок: <span className="text-white tabular-nums">{Math.max(0, params.braces - collapses)}</span>
        </span>
      </div>
    </div>
  );
};

export default RubbleGame;
