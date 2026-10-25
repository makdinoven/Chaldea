import type { RunesParams } from '../../../api/dungeons';
import { useRunes, type RuneOutcome } from './useRunes';
import { CraftStage, useHeldDone } from './three/craftKit';
import RuneScene, { RUNE_CAMERA } from './three/RuneScene';

/*
  The illusory wall in 3D (graphics to spare; RuneGame otherwise): the same
  game — remember the order the runes flare in, touch the stones back in it.
*/

interface Rune3DGameProps {
  params: RunesParams;
  offClass: boolean;
  onDone: (inputs: number[], outcome: RuneOutcome) => void;
  onPress?: (inputs: number[]) => void;
}

const Rune3DGame = ({ params, offClass, onDone, onPress }: Rune3DGameProps) => {
  const held = useHeldDone(onDone);
  const { phase, lit, step, mistakes, flash, outcome, timeBar, begin, touch } = useRunes({ params, onDone: held, onPress });

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Запомните, в каком порядке вспыхнут руны на камнях, и коснитесь камней в том же порядке — иллюзия рассеется.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Иллюзии — ремесло мага. Вам рун достанется больше, а ошибиться нельзя.
        </p>
      )}

      <CraftStage
        camera={RUNE_CAMERA}
        hud={
          <>
            <span className="absolute left-3 top-3 text-white/70 text-xs tabular-nums">
              {step} / {params.sequence.length}
            </span>
            {params.mistakes > 0 && (
              <span className={`absolute right-3 top-3 text-xs ${mistakes ? 'text-site-red' : 'text-white/50'}`}>
                ошибок {mistakes}/{params.mistakes}
              </span>
            )}
          </>
        }
      >
        <RuneScene params={params} phase={phase} lit={lit} flash={flash} outcome={outcome} onTouch={touch} />
      </CraftStage>

      <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div ref={timeBar} className="h-full bg-[#b07aff]/80" style={{ width: '100%' }} />
      </div>

      {phase === 'ready' ? (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      ) : (
        <p className="text-white/50 text-xs h-5">
          {phase === 'showing' ? 'Смотрите на руны…' : phase === 'input' ? 'Ваш черёд: коснитесь камней.' : ''}
        </p>
      )}
    </div>
  );
};

export default Rune3DGame;
