import {
  PASSPORT_DERIVED_ROWS,
  PASSPORT_STAT_LABELS,
  POINTS_PER_LEVEL,
  PRESET_TOTAL_POINTS,
  formatDerivedValue,
} from './derived';
import { PASSPORT_STAT_ORDER } from './types';
import type { DerivedStats, PassportStats } from './types';

/**
 * FEAT-154 — the stat preset and what it actually buys (rules 5-6).
 *
 * Renders nothing at all when the call site had no stats to give: an empty
 * table of zeroes would be a lie, and every field of `PassportData` is optional
 * by design.
 */
interface PassportStatBlockProps {
  stats?: PassportStats | null;
  derived?: DerivedStats | null;
}

const PassportStatBlock = ({ stats, derived }: PassportStatBlockProps) => {
  if (!stats) return null;

  const rows = PASSPORT_STAT_ORDER.filter((key) => typeof stats[key] === 'number');
  if (rows.length === 0) return null;

  const total = rows.reduce((sum, key) => sum + stats[key], 0);

  return (
    // `flex-1` + `mt-auto` on the closing note: the grid row already stretches
    // both ledger columns to a common height, so growing into the slack and
    // pushing the summary to the bottom edge makes «Информация о персонаже» and
    // this column finish level instead of leaving a ragged tail under the
    // shorter one. `flex-1`, not `h-full` — in the wizard the kit block is a
    // sibling below, and `h-full` would claim the whole column and overflow it.
    <section className="flex flex-1 flex-col">
      <h3 className="lore-heading text-lg sm:text-xl">Оценка при вступлении</h3>

      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {rows.map((key) => (
          <div key={key} className="passport-field">
            <dt className="passport-field-label">{PASSPORT_STAT_LABELS[key] ?? key}</dt>
            <dd className="passport-field-value ml-auto">{stats[key]}</dd>
          </div>
        ))}
      </dl>

      {derived ? (
        <>
          <div className="lore-divider my-4" />
          <h4 className="lore-heading text-base sm:text-lg">Стартовые показатели</h4>
          <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-2">
            {PASSPORT_DERIVED_ROWS.map((row) => (
              <div key={row.key} className="passport-field">
                <dt className="passport-field-label">{row.label}</dt>
                <dd className="passport-field-value ml-auto">
                  {formatDerivedValue(derived[row.key], row.isPercent)}
                </dd>
              </div>
            ))}
          </dl>
        </>
      ) : null}

      <p className="lore-body mt-auto pt-4 text-sm text-ink-muted">
        Всего распределено: {total} из {PRESET_TOTAL_POINTS} очков подрасы. Каждый новый УР
        добавляет ещё {POINTS_PER_LEVEL}.
      </p>
    </section>
  );
};

export default PassportStatBlock;
