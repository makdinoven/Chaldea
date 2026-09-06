import { useMemo } from 'react';
import { motion } from 'motion/react';
import {
  computeDerivedStats,
  formatDerivedValue,
  PASSPORT_DERIVED_ROWS,
  PASSPORT_STAT_LABELS,
  POINTS_PER_LEVEL,
  PRESET_TOTAL_POINTS,
  PASSPORT_STAT_ORDER,
} from '../../CommonComponents/CharacterPassport';
import type { StatPreset } from '../types';

/**
 * FEAT-154 (task #17) — rules 5-7.
 *
 * Turns a subrace stat preset into something a player can actually reason
 * about: what every point does, what it adds up to (HP, mana, dodge, crit,
 * initiative), a one-word archetype, and how the preset compares with the
 * average across every subrace in the game.
 *
 * ⚠️ The derived values come from `computeDerivedStats` of the passport module
 * (task #16) — the ONLY copy of the backend formulas on the frontend. Computing
 * them here again would let this panel and the passport print different numbers
 * for the same character.
 */

/** What one point of each stat actually does. Mirrors
 *  `character-attributes-service/app/crud.py::compute_derived_stats`. */
const STAT_EFFECTS: Record<string, string> = {
  strength: 'Урон воина. +0.1% ко всем физическим сопротивлениям за очко и вклад в инициативу.',
  agility: 'Урон плута. +0.1% к уклонению за очко и наибольший вклад в инициативу.',
  intelligence: 'Урон мага. +0.1% ко всем магическим сопротивлениям за очко и вклад в инициативу.',
  endurance: '+0.2% к сопротивлению эффектам за очко — яды, ожоги, проклятия держатся хуже.',
  health: '+10 к запасу здоровья за очко.',
  mana: '+10 к запасу маны за очко.',
  energy: '+5 к запасу энергии за очко.',
  stamina: '+5 к запасу выносливости за очко.',
  charisma: 'Пока не участвует в боевых расчётах — задел под социальные проверки.',
  luck: '+0.1% к шансу крита, к уклонению и к сопротивлению эффектам за очко.',
};

/** Core stats that define the build's shape (resources only amplify it). */
const CORE_STATS = ['strength', 'agility', 'intelligence', 'endurance'] as const;
type CoreStat = (typeof CORE_STATS)[number];

const ARCHETYPE_NAME: Record<CoreStat, string> = {
  strength: 'Таран',
  agility: 'Клинок в тени',
  intelligence: 'Толкователь',
  endurance: 'Стена',
};

const ARCHETYPE_LEAD: Record<CoreStat, string> = {
  strength: 'Ломает строй и держит удар в лоб.',
  agility: 'Бьёт первым и уходит из-под ответа.',
  intelligence: 'Решает бой знанием, а не силой руки.',
  endurance: 'Переживает то, от чего другие ломаются.',
};

const ARCHETYPE_SUPPORT: Record<CoreStat, string> = {
  strength: 'Во второй руке — грубая сила.',
  agility: 'Подстрахован скоростью.',
  intelligence: 'Подкреплён холодным расчётом.',
  endurance: 'Опирается на запас прочности.',
};

/** Delta below which a stat counts as «на уровне среднего». */
const NOTABLE_DELTA = 1;

interface StatExplainerProps {
  statPreset: StatPreset | null;
  subraceName: string;
  /** Every preset in the game — the baseline for the comparison (rule 7). */
  allPresets: StatPreset[];
}

const StatExplainer = ({ statPreset, subraceName, allPresets }: StatExplainerProps) => {
  const averages = useMemo<Record<string, number>>(() => {
    if (allPresets.length === 0) return {};
    const sums: Record<string, number> = {};
    allPresets.forEach((preset) => {
      PASSPORT_STAT_ORDER.forEach((key) => {
        sums[key] = (sums[key] ?? 0) + (Number(preset[key]) || 0);
      });
    });
    const result: Record<string, number> = {};
    PASSPORT_STAT_ORDER.forEach((key) => {
      result[key] = (sums[key] ?? 0) / allPresets.length;
    });
    return result;
  }, [allPresets]);

  /** `StatPreset` is a fixed-key interface; the passport helpers take an open
   *  record, so the preset is widened into one instead of being cast. */
  const statsRecord = useMemo<Record<string, number> | null>(() => {
    if (!statPreset) return null;
    const record: Record<string, number> = {};
    PASSPORT_STAT_ORDER.forEach((key) => {
      record[key] = Number(statPreset[key]) || 0;
    });
    return record;
  }, [statPreset]);

  const derived = useMemo(() => computeDerivedStats(statsRecord), [statsRecord]);

  const total = useMemo(
    () =>
      statPreset
        ? PASSPORT_STAT_ORDER.reduce((sum, key) => sum + (Number(statPreset[key]) || 0), 0)
        : 0,
    [statPreset],
  );

  const archetype = useMemo(() => {
    if (!statPreset || allPresets.length === 0) return null;

    const ranked = [...CORE_STATS]
      .map((key) => ({
        key,
        delta: (Number(statPreset[key]) || 0) - (averages[key] ?? 0),
        value: Number(statPreset[key]) || 0,
      }))
      .sort((a, b) => b.delta - a.delta || b.value - a.value);

    const [primary, secondary] = ranked;
    if (!primary || primary.delta < NOTABLE_DELTA) {
      return {
        name: 'Универсал',
        line: 'Ни одна из основ не выделяется — такой Скиталец гибок, но ничего не решает за счёт крови.',
      };
    }

    return {
      name: ARCHETYPE_NAME[primary.key],
      line: `${ARCHETYPE_LEAD[primary.key]} ${
        secondary && secondary.delta >= NOTABLE_DELTA ? ARCHETYPE_SUPPORT[secondary.key] : ''
      }`.trim(),
    };
  }, [statPreset, averages, allPresets.length]);

  const comparison = useMemo(() => {
    if (!statPreset || allPresets.length === 0) return null;
    const above: string[] = [];
    const below: string[] = [];
    PASSPORT_STAT_ORDER.forEach((key) => {
      const delta = (Number(statPreset[key]) || 0) - (averages[key] ?? 0);
      if (delta >= NOTABLE_DELTA) above.push(PASSPORT_STAT_LABELS[key] ?? key);
      else if (delta <= -NOTABLE_DELTA) below.push(PASSPORT_STAT_LABELS[key] ?? key);
    });
    return { above, below };
  }, [statPreset, averages, allPresets.length]);

  if (!statPreset) {
    return (
      <div className="gray-bg rounded-card p-4 sm:p-6">
        <p className="text-white/50 text-sm text-center">
          У этой подрасы ещё не задан набор характеристик.
        </p>
      </div>
    );
  }

  return (
    <motion.div
      key={subraceName}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="gray-bg rounded-card p-4 sm:p-6 flex flex-col gap-6"
    >
      <div className="flex flex-col gap-1">
        <h4 className="gold-text text-lg sm:text-xl font-medium uppercase">
          Что даёт кровь
        </h4>
        <p className="field-hint">
          Набор подрасы всегда стоит ровно {PRESET_TOTAL_POINTS} очков
          {total !== PRESET_TOTAL_POINTS ? ` (в этом наборе — ${total})` : ''}. На каждом
          уровне Скиталец получает ещё {POINTS_PER_LEVEL} очков и распределяет их сам, так
          что стартовый перекос со временем можно выправить.
        </p>
      </div>

      {/* Preset stats with per-point effect and the comparison delta (rules 6-7) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-3">
        {PASSPORT_STAT_ORDER.map((key) => {
          const value = Number(statPreset[key]) || 0;
          const delta = value - (averages[key] ?? 0);
          const notable = Math.abs(delta) >= NOTABLE_DELTA && allPresets.length > 0;

          return (
            <div key={key} className="flex flex-col gap-0.5 pb-2 border-b border-white/10">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-white text-sm font-medium">
                  {PASSPORT_STAT_LABELS[key] ?? key}
                </span>
                <span className="flex items-baseline gap-2 shrink-0">
                  <span className="text-gold text-sm font-medium">{value}</span>
                  {notable && (
                    <span
                      className={`text-[11px] ${delta > 0 ? 'text-stat-energy' : 'text-site-red'}`}
                      title="Сравнение со средним по всем подрасам"
                    >
                      {delta > 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}
                    </span>
                  )}
                </span>
              </div>
              <p className="text-white/45 text-[11px] sm:text-xs leading-snug">
                {STAT_EFFECTS[key]}
              </p>
            </div>
          );
        })}
      </div>

      {/* Derived values — computed by the passport module, never re-derived here */}
      <div className="flex flex-col gap-2">
        <h5 className="gold-text text-base font-medium uppercase">
          С чем выйдешь в первый бой
        </h5>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {PASSPORT_DERIVED_ROWS.map((row) => (
            <div
              key={row.key}
              className="flex flex-col items-center gap-0.5 py-2 px-1 rounded-card bg-white/[0.04]"
            >
              <span className="text-white/50 text-[11px] uppercase text-center leading-tight">
                {row.label}
              </span>
              <span className="text-gold text-sm font-medium">
                {formatDerivedValue(derived[row.key], row.isPercent)}
              </span>
            </div>
          ))}
        </div>
        <p className="field-hint">
          Значения посчитаны без экипировки и навыков — только кровь.
        </p>
      </div>

      {/* Verbal archetype + comparison summary (rule 7) */}
      {archetype && (
        <div className="flex flex-col gap-2 pt-4 border-t border-white/10">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-white/50 text-xs uppercase tracking-[0.08em]">Архетип</span>
            <span className="gold-text text-lg font-medium uppercase">{archetype.name}</span>
          </div>
          <p className="text-white text-sm leading-relaxed">{archetype.line}</p>

          {comparison && (comparison.above.length > 0 || comparison.below.length > 0) && (
            <p className="text-white/60 text-xs sm:text-sm leading-relaxed">
              {comparison.above.length > 0 && (
                <>
                  Выше среднего по подрасам:{' '}
                  <span className="text-stat-energy">{comparison.above.join(', ')}</span>.{' '}
                </>
              )}
              {comparison.below.length > 0 && (
                <>
                  Ниже среднего: <span className="text-site-red">{comparison.below.join(', ')}</span>.
                </>
              )}
            </p>
          )}
        </div>
      )}
    </motion.div>
  );
};

export default StatExplainer;
