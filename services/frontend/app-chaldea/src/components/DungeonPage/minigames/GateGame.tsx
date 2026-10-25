import type { GateParams } from '../../../api/dungeons';
import type { GateOutcome } from './warrior';
import { useGate } from './useGate';

/*
  Holding up a gate: a portcullis (or a slab) drags itself down, now and then
  harder. Holding the button (or space) heaves it up, letting go lets it sink.
  Keep it inside the golden band long enough and it is propped; let it reach
  the floor and it slams. The gate is played in fixed ticks, exactly as the
  server replays it (challenges.py gate_verdict).
*/

const BARS = 7;

interface GateGameProps {
  params: GateParams;
  offClass: boolean;
  onDone: (toggles: number[], outcome: GateOutcome) => void;
  onPress?: (toggles: number[]) => void;
}

const GateGame = ({ params, offClass, onDone, onPress }: GateGameProps) => {
  const { playing, gate, pressed, begin, grip } = useGate({ params, onDone, onPress });
  const slab = params.look === 'slab';
  const [lo, hi] = params.zone;

  const inZone = gate.level >= lo && gate.level <= hi;
  const surging = params.surges.some((s) => s.at_ms <= gate.t && gate.t < s.at_ms + s.dur_ms);
  const timeLeft = Math.max(0, 1 - gate.t / params.time_limit_ms);
  const what = slab ? 'плиту' : 'решётку';

  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Держите кнопку (или пробел), чтобы поднимать {what}, отпустите, чтобы она опускалась. Удержите её в золотой
        полосе, пока не заполнится шкала, и её подопрут. Опустится до пола — рухнет.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Держать тяжести — ремесло воина. Полоса у вас уже, а держать дольше.
        </p>
      )}

      <div className="flex items-stretch gap-3">
        {/* The doorway and the gate in it */}
        <div className="relative w-36 h-48 sm:w-40 sm:h-52 rounded-t-[40%] border-4 border-[#5a5248] bg-black/70 overflow-hidden shadow-card">
          <div
            className="absolute left-0 right-0 top-0"
            style={{ bottom: `${gate.level * 100}%` }}
          >
            {slab ? (
              <div className="absolute inset-0 bg-gradient-to-b from-[#6e665c] to-[#4a443d] border-b-4 border-[#3a352f]" />
            ) : (
              <div className="absolute inset-0 flex justify-around">
                {Array.from({ length: BARS }, (_, i) => (
                  <div key={i} className="w-1.5 h-full bg-gradient-to-r from-[#5c5852] via-[#9a948a] to-[#5c5852]" />
                ))}
                <div className="absolute left-0 right-0 bottom-0 h-1.5 bg-[#7c776e]" />
                <div className="absolute left-0 right-0 top-1/3 h-1 bg-[#6a655d]" />
              </div>
            )}
          </div>
          {/* The band to keep the gate's foot in, over the gate */}
          <div
            className={`absolute left-0 right-0 border-y transition-colors duration-150 ${
              inZone ? 'bg-gold/20 border-gold' : 'bg-gold/5 border-gold/60'
            }`}
            style={{ bottom: `${lo * 100}%`, height: `${(hi - lo) * 100}%` }}
          />
          {surging && playing && (
            <p className="absolute left-0 right-0 bottom-1 text-center text-site-red text-[11px] font-medium">
              Тянет вниз!
            </p>
          )}
        </div>
        {/* How long it has been held */}
        <div className="w-2.5 rounded-full bg-white/10 overflow-hidden flex flex-col justify-end">
          <div
            className="w-full bg-gold/80 transition-[height] duration-75"
            style={{ height: `${Math.min(100, (gate.held / params.hold_ms) * 100)}%` }}
          />
        </div>
      </div>

      <div className="w-full max-w-xs h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full bg-white/40" style={{ width: `${timeLeft * 100}%` }} />
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
      ) : gate.over ? (
        <p className="text-white/50 text-xs h-5" />
      ) : (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      )}
      <p className="text-white/40 text-[11px] tabular-nums h-4">
        {playing ? `${(gate.held / 1000).toFixed(1)} / ${(params.hold_ms / 1000).toFixed(1)} с` : ''}
      </p>
    </div>
  );
};

export default GateGame;
