import type { StarsParams } from '../../../api/dungeons';
import { useStars } from './useIntelGames';
import { CraftStage, useHeldDone } from './three/craftKit';
import StarsScene, { STARS_CAMERA } from './three/StarsScene';

/* Reading in 3D (graphics to spare; StarsGame otherwise): bring every geared ring to the gold mark. */

interface Stars3DGameProps {
  params: StarsParams;
  offClass: boolean;
  onDone: (turns: number[], outcome: 'open' | 'time') => void;
  onPress?: (turns: number[]) => void;
}

const Stars3DGame = ({ params, offClass, onDone, onPress }: Stars3DGameProps) => {
  const held = useHeldDone(onDone);
  const { playing, offsets, outcome, timeBar, begin, turn } = useStars({ params, onDone: held, onPress });
  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Кольца звёздной карты сцеплены: поворот кольца двигает и следующее. Сведите отметку каждого кольца к золотой
        стрелке — созвездие соберётся.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">Знаки — ремесло мага. Колец у вас больше, а времени меньше.</p>
      )}
      <CraftStage camera={STARS_CAMERA}>
        <StarsScene params={params} offsets={offsets} playing={playing} whole={outcome === 'open'} onTurn={turn} />
      </CraftStage>
      <div className="flex flex-wrap justify-center gap-2">
        {offsets.map((_, r) => (
          <button key={r} type="button" disabled={!playing} onClick={() => turn(r)} className="btn-line text-xs px-3 py-1.5 disabled:opacity-40">
            Кольцо {r + 1} ↻
          </button>
        ))}
      </div>
      <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div ref={timeBar} className="h-full bg-[#b07aff]/80" style={{ width: '100%' }} />
      </div>
      {!playing && !outcome && (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      )}
    </div>
  );
};

export default Stars3DGame;
