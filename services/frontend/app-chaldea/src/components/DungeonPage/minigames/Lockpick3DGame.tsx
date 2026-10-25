import { useCallback } from 'react';
import { Canvas } from '@react-three/fiber';
import type { LockpickParams } from '../../../api/dungeons';
import type { LockOutcome } from './lockpick';
import { useLockpick } from './useLockpick';
import { OUTCOME_HOLD_MS } from './three/holds';
import LockScene, { CAMERA_Z } from './three/LockScene';

/*
  The lock in 3D (devices with graphics to spare; the 2D plate otherwise):
  the same game as LockpickGame — a press anywhere on the picture, the button,
  space or enter sets the pin rocking on the pick if its top is at the shear line.
*/

interface Lockpick3DGameProps {
  params: LockpickParams;
  offClass: boolean;
  onDone: (presses: number[], outcome: LockOutcome) => void;
  onPress?: (presses: number[]) => void;
}

const Lockpick3DGame = ({ params, offClass, onDone, onPress }: Lockpick3DGameProps) => {
  const held = useCallback(
    (presses: number[], outcome: LockOutcome) => {
      setTimeout(() => onDone(presses, outcome), OUTCOME_HOLD_MS);
    },
    [onDone],
  );
  const { started, lock, live, timeBar, begin, doPress } = useLockpick({ params, onDone: held, onPress });
  const left = params.strains + 1 - lock.strains;

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Отмычка покачивает штифт. Поддевайте, когда его верх войдёт в золотое свечение у линии среза, — касанием
        замка, кнопкой или пробелом. Промах натягивает отмычку.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Замки — ремесло плута. Вам он поддаётся хуже: окно уже, штифтов больше, отмычка хрупче.
        </p>
      )}

      <div
        className="relative w-full aspect-[16/10] rounded-card overflow-hidden border border-white/10 shadow-card cursor-pointer touch-manipulation"
        onPointerDown={(e) => {
          e.preventDefault();
          doPress();
        }}
      >
        <Canvas
          dpr={[1, 2]}
          camera={{ position: [0, 0.15, CAMERA_Z], fov: 32 }}
          gl={{ antialias: true, powerPreference: 'high-performance' }}
        >
          <LockScene params={params} live={live} />
        </Canvas>
        {/* Vignette: the candle's reach ends in dark */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_45%_40%,transparent_55%,rgba(0,0,0,0.6)_100%)]" />
        <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-1.5" aria-label={`Запас отмычки: ${left}`}>
          {Array.from({ length: params.strains + 1 }, (_, i) => (
            <span
              key={i}
              className={`w-2.5 h-2.5 rounded-full border border-black/40 ${i < left ? 'bg-site-blue shadow-[0_0_6px_rgba(118,166,189,0.9)]' : 'bg-white/15'}`}
            />
          ))}
        </div>
        <div className="pointer-events-none absolute right-3 top-3 text-white/70 text-xs tabular-nums">
          {lock.set} / {params.pins.length}
        </div>
      </div>

      <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div ref={timeBar} className="h-full bg-gold/70" style={{ width: '100%' }} />
      </div>

      {!started ? (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      ) : (
        <button
          type="button"
          onPointerDown={(e) => {
            e.preventDefault();
            doPress();
          }}
          disabled={!!lock.over}
          className="btn-blue text-base px-10 py-3 w-full sm:w-auto disabled:opacity-50 touch-manipulation"
        >
          Поддеть
        </button>
      )}
    </div>
  );
};

export default Lockpick3DGame;
