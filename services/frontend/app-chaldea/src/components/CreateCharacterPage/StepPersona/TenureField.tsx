import { SEGMENT_LABELS, YEAR_SEGMENTS } from '../../../utils/gameTime';

/**
 * FEAT-154 (task #18) — «в Скитальцах с» (rules 22-24, §3.5).
 *
 * Two dates exist in this feature and they are not the same thing: the system
 * registration date is stamped at approval, while this one is in-world and is
 * the player's own claim. **It grants nothing.** A new Скиталец is УР 1 no
 * matter what is entered here — the field is pure roleplay, and how believable
 * it is, is the moderator's call.
 *
 * ⚠️ **No year is ever hardcoded.** The upper bound is `currentGameYear`, which
 * comes from `computed.year` of `GET /locations/game-time` at runtime. Moving
 * the game clock must require zero changes to this file.
 */

interface TenureFieldProps {
  year: number | null;
  /** Index 0..7 into `YEAR_SEGMENTS`, or `null` for «год целиком». */
  segment: number | null;
  onChange: (year: number | null, segment: number | null) => void;
  /** From `selectCurrentGameYear`. `null` until the clock has answered. */
  currentGameYear: number | null;
  /** Character age from the persona form — the lower bound of the tenure. */
  age: number | null;
  /**
   * `selectGameTimeError` — set when `fetchGameTime` failed. Without it a dead
   * clock is indistinguishable from a slow one and the hint would promise a
   * year that never arrives.
   */
  gameTimeError?: string | null;
}

/**
 * The two bounds of rule 23, mirroring the authoritative backend check.
 * Exported so the «Контракт» step can block a signature on the same rule
 * instead of re-deriving it. Returns `null` when the value is acceptable.
 */
export const validateTenure = (
  year: number | null,
  segment: number | null,
  currentGameYear: number | null,
  age: number | null,
): string | null => {
  if (year === null) return null;
  if (!Number.isInteger(year) || year <= 0) {
    return 'Год вступления указан некорректно.';
  }
  if (segment !== null && (segment < 0 || segment >= YEAR_SEGMENTS.length)) {
    return 'Выбран несуществующий отрезок года.';
  }
  // Both bounds depend on the live clock. If it has not answered yet, the
  // backend still enforces them — the form simply does not pre-judge.
  if (currentGameYear === null) return null;
  if (year > currentGameYear) {
    return 'Нельзя вступить в Скитальцы позже текущей игровой даты.';
  }
  if (age !== null && currentGameYear - year > age) {
    return 'Указанный стаж больше возраста персонажа.';
  }
  return null;
};

const TenureField = ({
  year,
  segment,
  onChange,
  currentGameYear,
  age,
  gameTimeError = null,
}: TenureFieldProps) => {
  const error = validateTenure(year, segment, currentGameYear, age);

  const handleYear = (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) {
      onChange(null, null);
      return;
    }
    const parsed = Number(trimmed);
    onChange(Number.isFinite(parsed) ? Math.trunc(parsed) : null, segment);
  };

  const handleSegment = (raw: string) => {
    onChange(year, raw === '' ? null : Number(raw));
  };

  return (
    <fieldset className="flex flex-col gap-2 w-full">
      <legend className="text-white text-sm sm:text-base mb-1">В Скитальцах с</legend>

      <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,120px)_minmax(0,1fr)] gap-3 sm:gap-4">
        <input
          type="number"
          inputMode="numeric"
          className="input-underline"
          placeholder="Год"
          aria-label="Игровой год вступления в Скитальцы"
          value={year ?? ''}
          onChange={(event) => handleYear(event.target.value)}
        />
        <select
          className="input-underline"
          aria-label="Отрезок года"
          value={segment ?? ''}
          onChange={(event) => handleSegment(event.target.value)}
          disabled={year === null}
        >
          <option value="" className="bg-site-dark text-white">
            Отрезок года — не важен
          </option>
          {YEAR_SEGMENTS.map((item, index) => (
            <option key={item.name} value={index} className="bg-site-dark text-white">
              {SEGMENT_LABELS[item.name] ?? item.name}
            </option>
          ))}
        </select>
      </div>

      {error ? (
        <p className="text-site-red text-xs">{error}</p>
      ) : (
        <>
          {/*
            A failed clock is not a slow clock. Saying «ещё отвечают» forever
            hides a real failure, so the load error is shown instead. It does
            not block: character-service checks both bounds of rule 23 anyway
            and returns its own Russian message.
          */}
          {currentGameYear === null && gameTimeError ? (
            <p className="text-site-red text-[13px] sm:text-sm leading-snug">
              Игровые часы недоступны — текущий игровой год не загрузился, поэтому проверить
              дату здесь нельзя. Поле можно оставить пустым или заполнить: дату проверит сервер
              при отправке заявки.
            </p>
          ) : null}
          <p className="field-hint">
            {currentGameYear !== null
              ? `Сейчас идёт ${currentGameYear} год. `
              : gameTimeError
                ? ''
                : 'Игровые часы ещё отвечают. '}
            Поле необязательно и не даёт никаких преимуществ: любой новичок получает УР 1.
            Это только отыгрыш — достоверность оценит Координатор.
          </p>
        </>
      )}
    </fieldset>
  );
};

export default TenureField;
