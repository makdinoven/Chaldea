import type { GateParams } from '../../../api/dungeons';
import type { GateOutcome } from './warrior';
import { useGate } from './useGate';
import { CraftStage, useHeldDone } from './three/craftKit';
import GateScene, { GATE_CAMERA } from './three/GateScene';

/*
  Holding up a gate in 3D (graphics to spare; GateGame otherwise): hold the
  button or space to heave it up, let go to let it sink; keep its foot between
  the gold notches until the bar fills.
*/

interface Gate3DGameProps {
  params: GateParams;
  offClass: boolean;
  onDone: (toggles: number[], outcome: GateOutcome) => void;
  onPress?: (toggles: number[]) => void;
}

const Gate3DGame = ({ params, offClass, onDone, onPress }: Gate3DGameProps) => {
  const held = useHeldDone(onDone);
  const { playing, pressed, outcome, live, holdBar, timeBar, begin, grip } = useGate({
    params,
    onDone: held,
    onPress,
    trackState: false,
  });
  const what = params.look === 'slab' ? 'плиту' : 'решётку';

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Держите кнопку (или пробел), чтобы поднимать {what}, отпустите — опускается. Удерживайте её низ между
        золотыми насечками, пока не заполнится шкала, и её подопрут. Опустится до пола — рухнет.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Держать тяжести — ремесло воина. Полоса у вас уже, а держать дольше.
        </p>
      )}
      <CraftStage
        camera={GATE_CAMERA}
        hud={
          <div className="absolute right-3 top-3 bottom-3 w-2.5 rounded-full bg-white/10 overflow-hidden flex flex-col justify-end">
            <div ref={holdBar} className="w-full bg-gold/80" style={{ height: '0%' }} />
          </div>
        }
      >
        <GateScene params={params} live={live} pressed={pressed} outcome={outcome} />
      </CraftStage>
      <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div ref={timeBar} className="h-full bg-white/40" style={{ width: '100%' }} />
      </div>

      {playing ? (
        <button
          type="button"
          onPointerDown={(e) => {
            e.preventDefault();
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
            grip(true);
          }}
          onPointerUp={() => grip(false)}
          onPointerCancel={() => grip(false)}
          onContextMenu={(e) => e.preventDefault()}
          className={`w-full sm:w-56 py-4 rounded-card border text-sm font-medium touch-none transition-colors duration-75 ${
            pressed ? 'border-gold bg-gold/25 text-white' : 'border-white/25 bg-black/50 text-white/80'
          }`}
        >
          {pressed ? 'Держу!' : 'Держать'}
        </button>
      ) : outcome ? (
        <p className="text-white/50 text-xs h-5" />
      ) : (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      )}
    </div>
  );
};

export default Gate3DGame;
