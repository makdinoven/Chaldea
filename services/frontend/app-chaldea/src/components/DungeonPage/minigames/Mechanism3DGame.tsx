import { useState } from 'react';
import type { ChallengeStep, MechanismParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';
import { CraftStage } from './three/craftKit';
import MechanismScene, { MECHANISM_CAMERA } from './three/MechanismScene';

/*
  The hidden mechanism in 3D (graphics to spare; MechanismGame otherwise):
  press the wall's blocks, read how far the lever is, find it before the
  presses run out. Every press is asked of the server.
*/

interface Mechanism3DGameProps {
  params: MechanismParams;
  offClass: boolean;
  onStep: (move: { x: number; y: number }) => Promise<ChallengeStep | null>;
}

const Mechanism3DGame = ({ params, offClass, onStep }: Mechanism3DGameProps) => {
  const [answers, setAnswers] = useState<Map<string, number>>(new Map());
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const left = params.probes - answers.size;

  const press = async (x: number, y: number) => {
    const key = `${x},${y}`;
    if (busy || over || answers.has(key) || left <= 0) return;
    setBusy(true);
    const step = await onStep({ x, y });
    setBusy(false);
    if (!step || step.distance == null) return;
    playDungeonSound(step.distance === 0 ? 'disarm' : 'vote');
    setAnswers((prev) => new Map(prev).set(key, step.distance as number));
    if (step.result) setOver(true);
  };

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        За одним из камней — рычаг. Нажмите на камень: на нём проступит, сколько шагов до рычага (по горизонтали и
        вертикали). Тёплый свет — близко, холодный — далеко.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">Механизмы — ремесло плута. У вас меньше попыток.</p>
      )}
      <CraftStage
        camera={MECHANISM_CAMERA}
        hud={
          <span className="absolute left-3 top-3 text-white/70 text-xs">
            Попыток: <span className="text-white tabular-nums">{left}</span>
          </span>
        }
      >
        <MechanismScene params={params} answers={answers} over={over || left <= 0} onPress={(x, y) => void press(x, y)} />
      </CraftStage>
    </div>
  );
};

export default Mechanism3DGame;
