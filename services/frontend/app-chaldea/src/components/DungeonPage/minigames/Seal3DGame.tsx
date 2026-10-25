import { useState } from 'react';
import type { ChallengeStep, SealParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';
import { CraftStage } from './three/craftKit';
import SealScene, { SEAL_CAMERA, type SealEnd } from './three/SealScene';

/*
  The magic seal in 3D (graphics to spare; SealGame otherwise): trace the
  sigil from the lit crystal, touching at each step the one true crystal among
  those that resonate. Which is true only the server knows.
*/

interface Seal3DGameProps {
  params: SealParams;
  offClass: boolean;
  onStep: (move: { index: number }) => Promise<ChallengeStep | null>;
}

const Seal3DGame = ({ params, offClass, onStep }: Seal3DGameProps) => {
  const [path, setPath] = useState<number[]>([params.start]);
  const [pulsing, setPulsing] = useState<number[]>(params.pulsing);
  const [offsets, setOffsets] = useState<number[]>(params.offsets ?? []);
  const [sparked, setSparked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [end, setEnd] = useState<SealEnd>(null);

  const touch = async (node: number) => {
    if (busy || end || !pulsing.includes(node)) return;
    setBusy(true);
    const step = await onStep({ index: node });
    setBusy(false);
    if (!step) return;
    if (step.safe) {
      playDungeonSound('disarm');
      setPath((p) => [...p, node]);
    } else {
      playDungeonSound('trap');
      setSparked((s) => [...s, node]);
    }
    setPulsing(step.pulsing ?? []);
    setOffsets(step.offsets ?? []);
    if (step.result) setEnd(step.result.passed ? 'open' : 'broke');
  };

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Проведите знак печати от светящегося кристалла. Круг бьётся в ритме — волна бежит к кольцу. Из отозвавшихся
        кристаллов знак продолжает тот, что вспыхивает ровно в такт с кругом; ложные сбиваются с ритма.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Печати — ремесло мага. Ложных отзвуков у вас больше, сбиваются они едва заметно, и первая же искра сорвёт печать.
        </p>
      )}
      <CraftStage
        camera={SEAL_CAMERA}
        hud={
          <div className="absolute left-3 top-3 flex gap-4 text-xs">
            <span className="text-white/70 tabular-nums">
              знак {path.length - 1} / {params.steps}
            </span>
            <span className={sparked.length ? 'text-site-red' : 'text-white/50'}>
              искр {sparked.length}/{params.mistakes}
            </span>
          </div>
        }
      >
        <SealScene
          nodes={params.nodes}
          beatMs={params.beat_ms}
          path={path}
          pulsing={pulsing}
          offsets={offsets}
          sparked={sparked}
          end={end}
          onTouch={(n) => void touch(n)}
        />
      </CraftStage>
    </div>
  );
};

export default Seal3DGame;
