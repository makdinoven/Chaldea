import { useState } from 'react';
import { motion, useAnimationControls } from 'motion/react';
import type { ChallengeStep, SealParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';

/*
  The magic seal: nodes on a ring, the sigil starting at the lit one. At each
  step a few nodes resonate — one of them is the sigil's true next node; touch
  it to draw the line on. A wrong one sparks and falls silent (a mage is
  forgiven a spark). Which node is true only the server knows: every touch is
  asked of it.
*/

const SIZE = 220;
const RADIUS = 86;
const NODE_R = 13;
const SPARK = '#ff6b6b';
const LINE = '#b07aff';

const spot = (i: number, n: number) => {
  const a = (i / n) * Math.PI * 2 - Math.PI / 2;
  return { x: SIZE / 2 + Math.cos(a) * RADIUS, y: SIZE / 2 + Math.sin(a) * RADIUS };
};

interface SealGameProps {
  params: SealParams;
  offClass: boolean;
  /** Touches a node; the server's answer, or null if the request failed. */
  onStep: (move: { index: number }) => Promise<ChallengeStep | null>;
}

const SealGame = ({ params, offClass, onStep }: SealGameProps) => {
  const [path, setPath] = useState<number[]>([params.start]);
  const [pulsing, setPulsing] = useState<number[]>(params.pulsing);
  const [offsets, setOffsets] = useState<number[]>(params.offsets ?? []);
  const [sparked, setSparked] = useState<number | null>(null);
  const [mistakes, setMistakes] = useState(0);
  const [busy, setBusy] = useState(false);
  const ring = useAnimationControls();

  const touch = async (node: number) => {
    if (busy || !pulsing.includes(node)) return;
    setBusy(true);
    const step = await onStep({ index: node });
    setBusy(false);
    if (!step) return;
    if (step.safe) {
      playDungeonSound('disarm');
      setPath((p) => [...p, node]);
      setSparked(null);
    } else {
      playDungeonSound('trap');
      setSparked(node);
      setMistakes((m) => m + 1);
      void ring.start({ x: [0, -6, 6, -4, 4, 0], transition: { duration: 0.3 } });
    }
    setPulsing(step.pulsing ?? []);
    setOffsets(step.offsets ?? []);
  };

  const nodes = Array.from({ length: params.nodes }, (_, i) => i);
  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Проведите знак печати от светящегося узла. Круг бьётся в ритме; из отозвавшихся узлов знак продолжает тот, что
        вспыхивает ровно в такт с кругом. Ошибка высекает искру.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Печати — ремесло мага. Ложных отзвуков у вас больше, сбиваются они едва заметно, и первая же искра сорвёт печать.
        </p>
      )}

      <motion.svg
        animate={ring}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="w-56 h-56 sm:w-64 sm:h-64 rounded-full bg-gradient-to-b from-[#221d2c] to-[#110e16] border border-white/15 shadow-card"
      >
        <circle cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={2} />
        {/* The beat: a wave runs out to the ring, which flares as it lands */}
        <circle cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} fill="none" stroke={LINE} strokeWidth={2} opacity={0}>
          <animate attributeName="r" values={`0;0;${RADIUS}`} keyTimes="0;0.5;1" dur={`${params.beat_ms}ms`} repeatCount="indefinite" />
          <animate attributeName="opacity" values="0;0;0.7" keyTimes="0;0.5;1" dur={`${params.beat_ms}ms`} repeatCount="indefinite" />
        </circle>
        {path.slice(1).map((n, i) => {
          const a = spot(path[i], params.nodes);
          const b = spot(n, params.nodes);
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={LINE}
              strokeWidth={3}
              strokeLinecap="round"
              style={{ filter: `drop-shadow(0 0 4px ${LINE})` }}
            />
          );
        })}
        {nodes.map((n) => {
          const { x, y } = spot(n, params.nodes);
          const onPath = path.includes(n);
          const resonates = pulsing.includes(n);
          const head = n === path[path.length - 1];
          return (
            <g
              key={n}
              onClick={() => void touch(n)}
              className={resonates && !busy ? 'cursor-pointer' : undefined}
              style={{ touchAction: 'manipulation' }}
            >
              {resonates && (
                // Pulses once a beat, on its offset from it (begins are on the page's clock, so all share the beat).
                <circle cx={x} cy={y} r={NODE_R + 2} fill="none" stroke={LINE} strokeWidth={3} opacity={0.15}>
                  <animate
                    attributeName="r"
                    values={`${NODE_R + 9};${NODE_R + 2};${NODE_R + 2};${NODE_R + 9}`}
                    keyTimes="0;0.12;0.88;1"
                    dur={`${params.beat_ms}ms`}
                    begin={`${Math.round((offsets[pulsing.indexOf(n)] ?? 0) * params.beat_ms)}ms`}
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="opacity"
                    values="1;0.12;0.12;1"
                    keyTimes="0;0.12;0.88;1"
                    dur={`${params.beat_ms}ms`}
                    begin={`${Math.round((offsets[pulsing.indexOf(n)] ?? 0) * params.beat_ms)}ms`}
                    repeatCount="indefinite"
                  />
                </circle>
              )}
              <circle
                cx={x}
                cy={y}
                r={NODE_R}
                fill={sparked === n ? SPARK : onPath ? LINE : '#2b2533'}
                stroke={head ? '#f0e0ff' : resonates ? LINE : 'rgba(255,255,255,0.2)'}
                strokeWidth={head ? 3 : 1.5}
              />
            </g>
          );
        })}
      </motion.svg>

      <div className="flex items-center gap-4 text-xs">
        <span className="text-white/60 tabular-nums">
          знак {path.length - 1} / {params.steps}
        </span>
        <span className={mistakes ? 'text-site-red' : 'text-white/40'}>
          искр {mistakes}/{params.mistakes}
        </span>
      </div>
    </div>
  );
};

export default SealGame;
