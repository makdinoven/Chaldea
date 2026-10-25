import type { StarsParams } from '../../../api/dungeons';
import { starsLayout } from './intel';
import { useStars } from './useIntelGames';

/*
  Reading a portal or an event ("Созвездие"): rings of a star chart, geared
  together — turning a ring turns the next one too. Bring every ring to its
  golden mark and the constellation is whole.
*/

const SIZE = 240;

interface StarsGameProps {
  params: StarsParams;
  offClass: boolean;
  onDone: (turns: number[], outcome: 'open' | 'time') => void;
  onPress?: (turns: number[]) => void;
}

const StarsGame = ({ params, offClass, onDone, onPress }: StarsGameProps) => {
  const { playing, offsets, outcome, timeBar, begin, turn } = useStars({ params, onDone, onPress });
  const layout = starsLayout(params);
  const radius = (r: number) => 34 + r * (80 / params.rings);
  const whole = outcome === 'open';

  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Кольца звёздной карты сцеплены: поворот кольца двигает и следующее. Сведите каждое к золотой отметке — созвездие
        соберётся.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">Знаки — ремесло мага. Колец у вас больше, а времени меньше.</p>
      )}
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-60 h-60 rounded-full bg-gradient-to-b from-[#16142a] to-[#08070f] border border-white/10">
        <line x1={SIZE / 2} y1={6} x2={SIZE / 2} y2={22} stroke="#d6b46a" strokeWidth={3} />
        {layout.map((stars, r) => {
          const rr = radius(r);
          const angle = (offsets[r] / params.steps) * 360;
          return (
            <g
              key={r}
              transform={`rotate(${angle} ${SIZE / 2} ${SIZE / 2})`}
              onClick={() => turn(r)}
              className={playing ? 'cursor-pointer' : undefined}
              style={{ transition: 'transform 0.15s ease-out' }}
            >
              <circle cx={SIZE / 2} cy={SIZE / 2} r={rr} fill="none" stroke="rgba(160,150,255,0.25)" strokeWidth={14} />
              <circle cx={SIZE / 2} cy={SIZE / 2} r={rr} fill="none" stroke={whole ? '#d6b46a' : 'rgba(200,190,255,0.5)'} strokeWidth={1} />
              {/* the ring's mark: at the top when the ring is home */}
              <circle cx={SIZE / 2} cy={SIZE / 2 - rr} r={3.5} fill="#d6b46a" />
              {stars.map((s, k) => (
                <circle
                  key={k}
                  cx={SIZE / 2 + Math.sin(s.angle) * rr}
                  cy={SIZE / 2 - Math.cos(s.angle) * rr}
                  r={1.6 * s.size}
                  fill="#e8e2ff"
                />
              ))}
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap justify-center gap-2">
        {offsets.map((_, r) => (
          <button
            key={r}
            type="button"
            disabled={!playing}
            onClick={() => turn(r)}
            className="btn-line text-xs px-3 py-1.5 disabled:opacity-40"
          >
            Кольцо {r + 1} ↻
          </button>
        ))}
      </div>
      <div className="w-full max-w-xs h-1.5 rounded-full bg-white/10 overflow-hidden">
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

export default StarsGame;
