import { motion, useAnimationControls } from 'motion/react';
import type { RunesParams } from '../../../api/dungeons';
import { useRunes, type RuneOutcome } from './useRunes';

/*
  The illusory wall: nine runes on the stone light up one after another; the
  mage touches them back in the same order. A wrong rune shakes the wall (a
  mage is forgiven one); the shown order fades from memory as time runs.
  Rules as the server has them (challenges.py runes_verdict).
*/

export const RUNES = ['ᚠ', 'ᚢ', 'ᚦ', 'ᚨ', 'ᚱ', 'ᚲ', 'ᚷ', 'ᚹ', 'ᚺ'];

interface RuneGameProps {
  params: RunesParams;
  offClass: boolean;
  onDone: (inputs: number[], outcome: RuneOutcome) => void;
  onPress?: (inputs: number[]) => void;
}

const RuneGame = ({ params, offClass, onDone, onPress }: RuneGameProps) => {
  const wall = useAnimationControls();
  const { phase, lit, step, mistakes, flash, timeBar, begin, touch } = useRunes({
    params,
    onDone,
    onPress,
    onWrong: () => void wall.start({ x: [0, -6, 6, -4, 4, 0], transition: { duration: 0.3 } }),
  });

  return (
    <div className="flex flex-col items-center gap-4 select-none">
      <p className="text-white/70 text-sm text-center max-w-sm">
        Запомните, в каком порядке вспыхнут руны, и коснитесь их в том же порядке — иллюзия рассеется.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-sm">
          Иллюзии — ремесло мага. Вам рун достанется больше, а ошибиться нельзя.
        </p>
      )}

      <motion.div
        animate={wall}
        className="grid grid-cols-3 gap-2 sm:gap-3 rounded-card border border-white/15 bg-gradient-to-b from-[#2e2a36] to-[#18161e] p-3 sm:p-4 shadow-card"
      >
        {RUNES.slice(0, params.glyphs).map((rune, g) => {
          const shown = lit === g;
          const answered = flash?.glyph === g;
          return (
            <button
              key={g}
              type="button"
              disabled={phase !== 'input'}
              onClick={() => touch(g)}
              className={`w-14 h-14 sm:w-16 sm:h-16 rounded-card border text-2xl sm:text-3xl transition-colors duration-150 ease-site touch-manipulation ${
                shown
                  ? 'bg-[#b07aff]/40 border-[#d8b8ff] text-white shadow-[0_0_18px_rgba(176,122,255,0.8)]'
                  : answered
                    ? flash?.good
                      ? 'bg-site-blue/30 border-site-blue text-white'
                      : 'bg-site-red/30 border-site-red text-white'
                    : 'bg-black/50 border-white/10 text-white/50 enabled:hover:text-white enabled:hover:border-white/30'
              }`}
            >
              {rune}
            </button>
          );
        })}
      </motion.div>

      <div className="w-full max-w-xs flex items-center gap-3">
        <span className="text-white/60 text-xs tabular-nums">
          {step} / {params.sequence.length}
        </span>
        <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
          <div ref={timeBar} className="h-full bg-[#b07aff]/80" style={{ width: '100%' }} />
        </div>
        {params.mistakes > 0 && (
          <span className={`text-xs ${mistakes ? 'text-site-red' : 'text-white/40'}`}>
            ошибок {mistakes}/{params.mistakes}
          </span>
        )}
      </div>

      {phase === 'ready' ? (
        <button type="button" onClick={begin} className="btn-blue text-sm px-8 py-2.5 w-full sm:w-auto">
          Начать
        </button>
      ) : (
        <p className="text-white/50 text-xs h-5">
          {phase === 'showing' ? 'Смотрите на руны…' : phase === 'input' ? 'Ваш черёд.' : ''}
        </p>
      )}
    </div>
  );
};

export default RuneGame;
