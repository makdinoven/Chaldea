import { useState } from 'react';
import type { ChallengeStep, RubbleParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';
import { CraftStage } from './three/craftKit';
import RubbleScene, { CRACK_WORDS, RUBBLE_CAMERA, type RubbleEnd } from './three/RubbleScene';

/*
  The cave-in in 3D (graphics to spare; RubbleGame otherwise): pull stones
  out until the way is clear; deep cracks mark the ones holding the pile up.
  Every pull is asked of the server.
*/

interface Rubble3DGameProps {
  params: RubbleParams;
  offClass: boolean;
  onStep: (move: { index: number }) => Promise<ChallengeStep | null>;
}

const Rubble3DGame = ({ params, offClass, onStep }: Rubble3DGameProps) => {
  const [pulled, setPulled] = useState<Map<number, boolean>>(new Map());
  const [busy, setBusy] = useState(false);
  const [end, setEnd] = useState<RubbleEnd>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const cleared = [...pulled.values()].filter(Boolean).length;
  const collapses = [...pulled.values()].filter((safe) => !safe).length;

  const pull = async (index: number) => {
    if (busy || end || pulled.has(index)) return;
    setBusy(true);
    const step = await onStep({ index });
    setBusy(false);
    if (!step || step.safe == null) return;
    setPulled((prev) => new Map(prev).set(index, step.safe as boolean));
    setHovered(null);
    playDungeonSound(step.safe ? 'disarm' : 'trap');
    if (step.result) setEnd(step.result.passed ? 'open' : 'broke');
  };

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Вынимайте камни, пока не расчистите проход. Глубокие трещины и раскол — у камней, что держат завал (обычно), а
        держат его чаще нижние. Вынете такой — завал осыплется, подпорка выдержит раз.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Завалы — дело воина. Трещины вам говорят меньше, а подпорок нет.
        </p>
      )}
      <CraftStage
        camera={RUBBLE_CAMERA}
        hud={
          <>
            <div className="absolute left-3 top-3 flex gap-4 text-xs text-white/70">
              <span>
                Расчищено: <span className="text-white tabular-nums">{cleared}</span> / {params.to_clear}
              </span>
              <span>
                Подпорок: <span className="text-white tabular-nums">{Math.max(0, params.braces - collapses)}</span>
              </span>
            </div>
            {hovered !== null && (
              <span className="absolute left-1/2 bottom-3 -translate-x-1/2 rounded-card bg-black/70 px-3 py-1 text-xs text-white">
                {CRACK_WORDS[params.cracks[hovered]] ?? ''}
              </span>
            )}
          </>
        }
      >
        <RubbleScene params={params} pulled={pulled} end={end} onPull={(i) => void pull(i)} onHover={setHovered} />
      </CraftStage>
    </div>
  );
};

export default Rubble3DGame;
