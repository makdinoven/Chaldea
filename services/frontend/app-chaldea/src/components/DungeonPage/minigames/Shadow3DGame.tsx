import type { ShadowParams } from '../../../api/dungeons';
import type { ShadowOutcome } from './intel';
import { useShadow } from './useIntelGames';
import { CraftStage, useHeldDone } from './three/craftKit';
import ShadowScene, { SHADOW_CAMERA } from './three/ShadowScene';

/* Scouting in 3D (graphics to spare; ShadowGame otherwise): step through the corridor only into the dark. */

interface Shadow3DGameProps {
  params: ShadowParams;
  offClass: boolean;
  onDone: (steps: number[], outcome: ShadowOutcome) => void;
  onPress?: (steps: number[]) => void;
}

const Shadow3DGame = ({ params, offClass, onDone, onPress }: Shadow3DGameProps) => {
  const held = useHeldDone(onDone);
  const { playing, outcome, live, timeBar, begin, step } = useShadow({ params, onDone: held, onPress });
  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Проберитесь по коридору: шаг — касанием, кнопкой, пробелом или →. Входите только в тень и не стойте там, где вот-вот
        вспыхнет фонарь.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Разведка — ремесло плута. Фонари горят у вас дольше, а коридор длиннее.
        </p>
      )}
      <CraftStage camera={SHADOW_CAMERA} onPress={playing ? step : undefined}>
        <ShadowScene params={params} live={live} outcome={outcome} />
      </CraftStage>
      <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
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

export default Shadow3DGame;
