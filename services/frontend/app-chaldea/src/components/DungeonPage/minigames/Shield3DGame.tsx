import type { ShieldParams } from '../../../api/dungeons';
import { useShield } from './useShield';
import { CraftStage, useHeldDone } from './three/craftKit';
import ShieldScene, { SHIELD_CAMERA } from './three/ShieldScene';

/*
  The party shield in 3D (graphics to spare; ShieldGame otherwise): turn the
  shield to meet each arrow — the buttons or the arrow keys.
*/

const SIDES = [
  { label: 'Слева', arrow: '←' },
  { label: 'Сверху', arrow: '↑' },
  { label: 'Справа', arrow: '→' },
];

interface Shield3DGameProps {
  params: ShieldParams;
  offClass: boolean;
  onDone: (presses: number[], outcome: 'open') => void;
  onPress?: (presses: number[]) => void;
}

const Shield3DGame = ({ params, offClass, onDone, onPress }: Shield3DGameProps) => {
  const held = useHeldDone(onDone);
  const { phase, side, flash, parried, startedAt, begin, turn } = useShield({
    params,
    onDone: held,
    onPress,
    trackNow: false,
  });

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Из темноты летят стрелы — слева, сверху и справа. Поверните щит навстречу каждой, пока не долетела. Чем больше
        отобьёте, тем крепче щит прикроет отряд на следующем переходе.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Щит — ремесло воина. Вам стрел достанется больше, а заметите вы их позже.
        </p>
      )}
      <CraftStage
        camera={SHIELD_CAMERA}
        hud={
          <span className="absolute left-3 top-3 text-white/70 text-xs tabular-nums">
            отбито {parried} из {params.blows.length}
          </span>
        }
      >
        <ShieldScene params={params} phase={phase} side={side} flash={flash} startedAt={startedAt} />
      </CraftStage>

      <div className="grid grid-cols-3 gap-2 w-full max-w-xs">
        {SIDES.map((s, i) => (
          <button
            key={i}
            type="button"
            disabled={phase !== 'playing'}
            onPointerDown={(e) => {
              e.preventDefault();
              turn(i);
            }}
            className={`py-3 rounded-card border text-sm touch-manipulation transition-colors duration-150 ease-site ${
              side === i && phase === 'playing'
                ? 'border-gold/70 bg-gold/15 text-white'
                : 'border-white/15 bg-black/40 text-white/70 enabled:hover:border-white/40'
            } disabled:opacity-50`}
          >
            <span className="block text-lg leading-none">{s.arrow}</span>
            <span className="text-[11px]">{s.label}</span>
          </button>
        ))}
      </div>

      {phase === 'ready' ? (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      ) : (
        <p className="text-white/50 text-xs h-5">{phase === 'playing' ? 'Стрелки ← ↑ → или кнопки.' : ''}</p>
      )}
    </div>
  );
};

export default Shield3DGame;
