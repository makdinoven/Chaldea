import { useState } from 'react';
import type { ChallengeStep, SearchParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';

/*
  Searching a room: its floor in tiles. Under each tile looked at there are
  traces — scuffs, a dragged mark — pointing one of eight ways, mostly towards
  a stash if there is one. Find it before the looks run out. Where the stash
  lies only the server knows; every look is asked of it.
*/

/** Eight ways, clockwise from up. */
const ARROWS = ['↑', '↗', '→', '↘', '↓', '↙', '←', '↖'];

interface SearchGameProps {
  params: SearchParams;
  offClass: boolean;
  /** Looks under a tile; the server's answer, or null if the request failed. */
  onStep: (move: { x: number; y: number }) => Promise<ChallengeStep | null>;
}

const SearchGame = ({ params, offClass, onStep }: SearchGameProps) => {
  // A tile looked under: the way its traces point, or null where the stash was.
  const [looks, setLooks] = useState<Map<string, number | null>>(new Map());
  const [busy, setBusy] = useState(false);
  const left = params.probes - looks.size;

  const look = async (x: number, y: number) => {
    const key = `${x},${y}`;
    if (busy || looks.has(key) || left <= 0) return;
    setBusy(true);
    const step = await onStep({ x, y });
    setBusy(false);
    if (!step) return;
    const found = step.way == null;
    playDungeonSound(found ? 'chest' : 'step');
    setLooks((prev) => new Map(prev).set(key, found ? null : (step.way as number)));
  };

  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Осмотрите плиты пола. Под каждой — следы, которые указывают, куда тянуть дальше. Если в комнате есть тайник,
        следы чаще всего ведут к нему. Найдите его, пока не кончились попытки.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Обыск — ремесло плута. Попыток у вас меньше, а следы чаще путают.
        </p>
      )}

      <div
        className="grid gap-1 sm:gap-1.5 rounded-card border border-white/15 bg-gradient-to-b from-[#3b352d] to-[#1f1b16] p-2.5 sm:p-3 shadow-card"
        style={{ gridTemplateColumns: `repeat(${params.cols}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: params.rows }, (_, y) =>
          Array.from({ length: params.cols }, (_, x) => {
            const key = `${x},${y}`;
            const seen = looks.has(key);
            const way = looks.get(key);
            return (
              <button
                key={key}
                type="button"
                disabled={busy || seen || left <= 0}
                onClick={() => void look(x, y)}
                className={`w-10 h-10 sm:w-12 sm:h-12 rounded border text-lg font-medium transition-colors duration-150 ease-site touch-manipulation ${
                  seen
                    ? way === null
                      ? 'bg-gold/60 border-gold text-black'
                      : 'bg-black/50 border-white/15 text-gold'
                    : 'bg-[#6b6155] border-[#857a6c]/60 enabled:hover:bg-[#7a6f62] disabled:opacity-80'
                }`}
              >
                {seen ? (way === null ? '✦' : ARROWS[way as number]) : ''}
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

export default SearchGame;
