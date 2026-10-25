import type { ShadowParams } from '../../../api/dungeons';
import { shadowLit, type ShadowOutcome } from './intel';
import { useShadow } from './useIntelGames';

/*
  Scouting a corridor ("Тени"): the corridor in cells, lanterns flaring over
  some of them. Step forward (the button, space or →) only into the dark — and
  don't stand where a lantern is about to flare. Played in ticks, exactly as
  the server replays it (challenges.py shadow_verdict).
*/

interface ShadowGameProps {
  params: ShadowParams;
  offClass: boolean;
  onDone: (steps: number[], outcome: ShadowOutcome) => void;
  onPress?: (steps: number[]) => void;
}

const ShadowGame = ({ params, offClass, onDone, onPress }: ShadowGameProps) => {
  const { playing, shadow, outcome, timeBar, begin, step } = useShadow({ params, onDone, onPress });
  const cells = Array.from({ length: params.cells + 2 }, (_, i) => i);

  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Проберитесь по коридору: шаг — кнопкой, пробелом или →. Входите только в тёмные клетки и не стойте там, где вот-вот
        вспыхнет фонарь.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Разведка — ремесло плута. Фонари горят у вас дольше, а коридор длиннее.
        </p>
      )}
      <div className="w-full overflow-x-auto">
        <div className="flex gap-1 mx-auto w-max p-2 rounded-card bg-gradient-to-b from-[#1e1b19] to-[#0e0c0b] border border-white/10">
          {cells.map((i) => {
            const lamp = i >= 1 && i <= params.cells ? params.lamps[i - 1] : null;
            const lit = lamp ? shadowLit(lamp, shadow.t) : false;
            const here = shadow.pos === i;
            return (
              <div
                key={i}
                className={`relative w-7 h-14 sm:w-8 sm:h-16 rounded border transition-colors duration-75 ${
                  i === 0 || i === params.cells + 1
                    ? 'bg-black/60 border-white/10'
                    : lit
                      ? 'bg-[#ffcf6a]/60 border-[#ffcf6a] shadow-[0_0_14px_rgba(255,207,106,0.7)]'
                      : lamp
                        ? 'bg-[#3a3024] border-[#6a5638]/60'
                        : 'bg-[#1a1714] border-white/5'
                }`}
              >
                {lamp && <span className="absolute -top-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-[#ffcf6a]" />}
                {here && (
                  <span
                    className={`absolute inset-x-1 bottom-1 h-6 rounded-t-full ${
                      outcome === 'broke' ? 'bg-site-red' : 'bg-[#8a7cb8]'
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
      <div className="w-full max-w-xs h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div ref={timeBar} className="h-full bg-gold/70" style={{ width: '100%' }} />
      </div>
      {playing ? (
        <button
          type="button"
          onPointerDown={(e) => {
            e.preventDefault();
            step();
          }}
          className="btn-blue text-base px-10 py-3 w-full sm:w-auto touch-manipulation"
        >
          Шаг
        </button>
      ) : outcome ? null : (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      )}
    </div>
  );
};

export default ShadowGame;
