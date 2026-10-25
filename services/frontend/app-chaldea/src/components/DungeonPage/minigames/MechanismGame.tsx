import { useState } from 'react';
import type { ChallengeStep, MechanismParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';

/*
  The hidden mechanism: a wall of stones, one of them hiding the lever. Each
  stone pressed tells how many steps away the lever is (across and up/down);
  the rogue has a few presses to find it. Where the lever is only the server
  knows — every press is asked of it.
*/

/** Warm when close, cold when far. */
const HEAT = ['bg-gold/70 text-black', 'bg-[#e08a4c]/60 text-white', 'bg-[#c9a24a]/35 text-white', 'bg-site-blue/25 text-white'];
const heatOf = (distance: number) => HEAT[Math.min(HEAT.length - 1, distance)];

interface MechanismGameProps {
  params: MechanismParams;
  offClass: boolean;
  /** Presses a stone; the server's answer, or null if the request failed. */
  onStep: (move: { x: number; y: number }) => Promise<ChallengeStep | null>;
}

const MechanismGame = ({ params, offClass, onStep }: MechanismGameProps) => {
  const [answers, setAnswers] = useState<Map<string, number>>(new Map());
  const [busy, setBusy] = useState(false);
  const left = params.probes - answers.size;

  const pressStone = async (x: number, y: number) => {
    const key = `${x},${y}`;
    if (busy || answers.has(key) || left <= 0) return;
    setBusy(true);
    const step = await onStep({ x, y });
    setBusy(false);
    if (!step || step.distance == null) return;
    playDungeonSound(step.distance === 0 ? 'disarm' : 'vote');
    setAnswers((prev) => new Map(prev).set(key, step.distance as number));
  };

  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        За одним из камней — рычаг. Нажмите на камень: на нём проступит, сколько шагов до рычага (по горизонтали и
        вертикали). Найдите его, пока не кончились попытки.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Механизмы — ремесло плута. У вас меньше попыток.
        </p>
      )}

      <div
        className="grid gap-1.5 sm:gap-2 rounded-card border border-white/15 bg-gradient-to-b from-[#3a3634] to-[#1e1b1a] p-3 sm:p-4 shadow-card"
        style={{ gridTemplateColumns: `repeat(${params.cols}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: params.rows }, (_, y) =>
          Array.from({ length: params.cols }, (_, x) => {
            const answer = answers.get(`${x},${y}`);
            return (
              <button
                key={`${x},${y}`}
                type="button"
                disabled={busy || answer !== undefined || left <= 0}
                onClick={() => void pressStone(x, y)}
                className={`w-11 h-9 sm:w-14 sm:h-11 rounded border text-sm font-medium tabular-nums transition-colors duration-150 ease-site touch-manipulation ${
                  answer !== undefined
                    ? `${heatOf(answer)} border-white/20`
                    : 'bg-[#6e6a66] border-[#8a8680]/60 text-transparent enabled:hover:bg-[#7e7a74] disabled:opacity-80'
                }`}
              >
                {answer !== undefined ? (answer === 0 ? '✦' : answer) : '·'}
              </button>
            );
          }),
        )}
      </div>

      <p className="text-white/60 text-xs">
        Попыток осталось: <span className="text-white tabular-nums">{left}</span>
      </p>
    </div>
  );
};

export default MechanismGame;
