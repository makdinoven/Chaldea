import type { OriginCountry } from '../../../api/origins';
import type { StarterKitCoverageClass } from '../../../api/starterKits';

/**
 * FEAT-154 (rules 12a-12c, task #32) — the seeding checklist made visible.
 *
 * Every (class × origin) pair is one of three things:
 *  - «Задан»      — an explicit override row exists for the pair;
 *  - «Наследует»  — no override, the pair falls back to the class default;
 *  - «Пусто»      — no override AND the class has no default either, so a
 *                   character of this pair would be granted nothing at all.
 *
 * Two renderings of the same data: a table from `sm:` up, and a per-class chip
 * list below it — a 3×8 grid does not fit a 360px screen as a table, and a
 * horizontally scrolling table is a bad checklist.
 */

export const kitKey = (classId: number, originId: number) => `${classId}:${originId}`;

export type CoverageState = 'override' | 'inherits' | 'empty';

interface CoverageMatrixProps {
  classes: StarterKitCoverageClass[];
  origins: OriginCountry[];
  /** Keys (`${classId}:${originId}`) of pairs that have their own row. */
  overrideKeys: Set<string>;
  /** Which origin each class card is currently editing, `classId -> originId`. */
  selectedByClass: Record<number, number>;
  onSelect: (classId: number, originId: number) => void;
}

const STATE_LABEL: Record<CoverageState, string> = {
  override: 'Задан',
  inherits: 'Наследует',
  empty: 'Пусто',
};

const STATE_CELL: Record<CoverageState, string> = {
  override: 'border-gold/60 bg-gold/15 text-gold',
  inherits: 'border-white/15 bg-white/[0.04] text-white/50',
  empty: 'border-site-red/50 bg-site-red/10 text-site-red',
};

const CoverageMatrix = ({
  classes,
  origins,
  overrideKeys,
  selectedByClass,
  onSelect,
}: CoverageMatrixProps) => {
  const stateOf = (klass: StarterKitCoverageClass, originId: number): CoverageState => {
    if (overrideKeys.has(kitKey(klass.id_class, originId))) return 'override';
    return klass.has_default ? 'inherits' : 'empty';
  };

  const isSelected = (classId: number, originId: number) =>
    selectedByClass[classId] === originId;

  const total = classes.length * origins.length;
  const filled = classes.reduce(
    (sum, klass) =>
      sum + origins.filter((o) => overrideKeys.has(kitKey(klass.id_class, o.id))).length,
    0,
  );
  const withoutDefault = classes.filter((klass) => !klass.has_default);

  if (classes.length === 0) {
    return null;
  }

  return (
    <section className="gray-bg p-4 sm:p-6 mb-8">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-2">
        <h2 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.06em]">
          Заполненность комбинаций
        </h2>
        {origins.length > 0 && (
          <span className="text-white/50 text-sm">
            Задано явно: {filled} из {total}
          </span>
        )}
      </div>

      <p className="text-white/50 text-sm mb-4">
        Незаданная пара не ломает игру — персонаж получит набор своего класса. Матрица показывает,
        где набор уже свой, а где всё ещё общий. Нажмите на ячейку, чтобы открыть её в редакторе
        ниже.
      </p>

      {origins.length === 0 ? (
        <p className="text-white/60 text-sm">
          Справочник происхождений пуст или не загрузился — второе измерение недоступно.
          Заполните его на странице «Происхождения».
        </p>
      ) : (
        <>
          {/* ── Table: sm and up ── */}
          <div className="hidden sm:block overflow-x-auto gold-scrollbar">
            <table className="min-w-full border-separate border-spacing-1 text-sm">
              <thead>
                <tr>
                  <th className="text-left text-white/40 font-normal px-2 py-1 whitespace-nowrap">
                    Класс / Происхождение
                  </th>
                  {origins.map((origin) => (
                    <th
                      key={origin.id}
                      className="text-white/60 font-normal px-2 py-1 align-bottom
                        text-xs max-w-[110px] break-words"
                    >
                      {origin.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {classes.map((klass) => (
                  <tr key={klass.id_class}>
                    <th className="text-left px-2 py-1 font-normal whitespace-nowrap">
                      <span className="text-white">{klass.name}</span>
                      {!klass.has_default && (
                        <span className="block text-site-red text-xs">нет набора класса</span>
                      )}
                    </th>
                    {origins.map((origin) => {
                      const state = stateOf(klass, origin.id);
                      return (
                        <td key={origin.id} className="p-0">
                          <button
                            type="button"
                            onClick={() => onSelect(klass.id_class, origin.id)}
                            title={`${klass.name} × ${origin.name} — ${STATE_LABEL[state]}`}
                            className={`w-full rounded-[10px] border px-2 py-2 text-xs
                              transition-colors duration-200 hover:brightness-125
                              ${STATE_CELL[state]} ${
                                isSelected(klass.id_class, origin.id)
                                  ? 'ring-1 ring-site-blue'
                                  : ''
                              }`}
                          >
                            {STATE_LABEL[state]}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ── Chips: below sm (360px-safe) ── */}
          <div className="sm:hidden flex flex-col gap-4">
            {classes.map((klass) => (
              <div key={klass.id_class}>
                <p className="text-white text-sm mb-2">
                  {klass.name}
                  {!klass.has_default && (
                    <span className="text-site-red text-xs"> · нет набора класса</span>
                  )}
                </p>
                <div className="flex flex-wrap gap-2">
                  {origins.map((origin) => {
                    const state = stateOf(klass, origin.id);
                    return (
                      <button
                        key={origin.id}
                        type="button"
                        onClick={() => onSelect(klass.id_class, origin.id)}
                        className={`rounded-full border px-3 py-1.5 text-xs max-w-full break-words
                          text-left transition-colors duration-200
                          ${STATE_CELL[state]} ${
                            isSelected(klass.id_class, origin.id) ? 'ring-1 ring-site-blue' : ''
                          }`}
                      >
                        {origin.name} · {STATE_LABEL[state]}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* ── Legend ── */}
          <div className="flex flex-wrap gap-x-4 gap-y-2 mt-4 text-xs">
            <span className="text-gold">■ Задан — у пары свой набор</span>
            <span className="text-white/50">■ Наследует — берётся набор класса</span>
            <span className="text-site-red">■ Пусто — набора нет вообще</span>
          </div>

          {withoutDefault.length > 0 && (
            <p className="text-site-red text-sm mt-3">
              Нет набора по умолчанию у классов: {withoutDefault.map((c) => c.name).join(', ')}.
              Заполните их первыми — иначе персонажи этих классов не получат ничего.
            </p>
          )}
        </>
      )}
    </section>
  );
};

export default CoverageMatrix;
