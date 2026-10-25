import type { ChallengeStep, WiresParams } from '../../../api/dungeons';
import { WiresRules, useWires } from './WiresGame';
import { CraftStage } from './three/craftKit';
import WiresScene, { WIRES_CAMERA } from './three/WiresScene';

/* Disarming in 3D (graphics to spare; WiresGame otherwise): cut every slack rod, leave the taut ones. */

interface Wires3DGameProps {
  params: WiresParams;
  offClass: boolean;
  onStep: (move: { index: number }) => Promise<ChallengeStep | null>;
}

const Wires3DGame = ({ params, offClass, onStep }: Wires3DGameProps) => {
  const { rods, over, slips, cut } = useWires(params, onStep);
  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <WiresRules mistakes={params.mistakes} />
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Ловушки — ремесло плута. Тяг у вас больше, подсказок меньше, ошибиться нельзя.
        </p>
      )}
      <CraftStage
        camera={WIRES_CAMERA}
        hud={
          <span className="absolute left-3 top-3 text-white/70 text-xs">
            Натянутых: {params.taut} · ошибок {slips}/{params.mistakes}
          </span>
        }
      >
        <WiresScene params={params} rods={rods} over={over} onCut={(i) => void cut(i)} />
      </CraftStage>
    </div>
  );
};

export default Wires3DGame;
