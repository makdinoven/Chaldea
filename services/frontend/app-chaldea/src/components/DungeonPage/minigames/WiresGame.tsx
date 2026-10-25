import { useState } from 'react';
import type { ChallengeStep, WiresParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';

/*
  Disarming a trap ("Тяги"): a row of rods, some of them taut. A slack rod cut
  shows how many of its neighbours are taut; cut every slack one. Which are
  taut only the server knows — every cut is asked of it.
*/

/** A rod's state as the player knows it: uncut, cut (with its taut neighbours), or found taut. */
export type RodState = { cut: true; near: number } | { taut: true } | undefined;

interface WiresGameProps {
  params: WiresParams;
  offClass: boolean;
  onStep: (move: { index: number }) => Promise<ChallengeStep | null>;
}

export const useWires = (params: WiresParams, onStep: WiresGameProps['onStep']) => {
  const [rods, setRods] = useState<Map<number, RodState>>(
    () => new Map(params.shown.map(([i, near]) => [i, { cut: true as const, near }])),
  );
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const slips = [...rods.values()].filter((r) => r && 'taut' in r).length;

  const cut = async (index: number) => {
    if (busy || over || rods.has(index)) return;
    setBusy(true);
    const step = await onStep({ index });
    setBusy(false);
    if (!step || step.safe == null) return;
    setRods((prev) => new Map(prev).set(index, step.safe ? { cut: true, near: step.near ?? 0 } : { taut: true }));
    playDungeonSound(step.safe ? 'disarm' : 'trap');
    if (step.result) setOver(true);
  };
  return { rods, busy, over, slips, cut };
};

/** How the rods are read, spelled out: players found the one-line rule too terse. */
export const WiresRules = ({ mistakes, narrow }: { mistakes: number; narrow?: boolean }) => (
  <div className={`text-white/70 text-sm ${narrow ? 'max-w-sm' : 'max-w-md'} w-full flex flex-col gap-1.5`}>
    <p className="text-center">
      Перережьте все свободные тяги, не задев натянутых — это спуск ловушки.
    </p>
    <ul className="list-disc pl-5 text-xs text-white/60 flex flex-col gap-0.5">
      <li>
        Число над перерезанной тягой — сколько натянутых среди двух её соседок, слева и справа.
      </li>
      <li>«0» — обе соседки свободны, режьте смело. «2» — обе натянуты, их не трогать.</li>
      <li>Одна тяга уже перерезана — начните рассуждать от её числа.</li>
      <li>
        {mistakes > 0
          ? `Задеть натянутую можно ${mistakes === 1 ? 'один раз' : `${mistakes} раза`}, дальше ловушка сработает.`
          : 'Задеть натянутую нельзя ни разу — ловушка сработает сразу.'}
      </li>
    </ul>
    <details className="text-xs text-white/55">
      <summary className="cursor-pointer text-white/70 hover:text-gold">Пример</summary>
      <p className="mt-1">
        Над тягой 4 стоит «1» — натянута 3 или 5. Режем крайнюю 7: «0», значит 6 свободна. Режем 6: «1» — раз 7
        свободна, натянута 5. Тогда по числу у 4 тяга 3 свободна; режем 3: «1» — натянута 2. Остаётся 1, она свободна.
      </p>
    </details>
  </div>
);

const WiresGame = ({ params, offClass, onStep }: WiresGameProps) => {
  const { rods, busy, over, slips, cut } = useWires(params, onStep);
  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <WiresRules mistakes={params.mistakes} narrow />
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Ловушки — ремесло плута. Тяг у вас больше, подсказок меньше, ошибиться нельзя.
        </p>
      )}
      <div className="flex gap-1.5 sm:gap-2 p-3 rounded-card bg-gradient-to-b from-[#2e2a26] to-[#141210] border border-white/10">
        {Array.from({ length: params.wires }, (_, i) => {
          const r = rods.get(i);
          const cutDone = r && 'cut' in r;
          const taut = r && 'taut' in r;
          return (
            <button
              key={i}
              type="button"
              disabled={busy || over || !!r}
              onClick={() => void cut(i)}
              className="relative w-7 sm:w-9 h-36 flex flex-col items-center justify-between touch-manipulation group"
              aria-label={`Тяга ${i + 1}`}
            >
              <span className="w-3 h-3 rounded-full bg-[#8a8a92]" />
              <span
                className={`flex-1 w-[3px] my-0.5 ${
                  taut ? 'bg-site-red' : cutDone ? 'bg-gradient-to-b from-[#b08a4a] via-transparent to-[#b08a4a]' : 'bg-[#b08a4a] group-enabled:group-hover:bg-gold'
                }`}
              />
              <span
                className={`w-6 h-6 rounded border text-xs flex items-center justify-center tabular-nums ${
                  cutDone ? 'border-gold/60 text-gold' : taut ? 'border-site-red text-site-red' : 'border-white/15 text-transparent'
                }`}
              >
                {cutDone ? (r as { near: number }).near : taut ? '!' : '·'}
              </span>
            </button>
          );
        })}
      </div>
      <p className="text-white/60 text-xs">
        Натянутых: {params.taut} · ошибок {slips}/{params.mistakes}
      </p>
    </div>
  );
};

export default WiresGame;
