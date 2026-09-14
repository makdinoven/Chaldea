/**
 * FEAT-161 — the single place where a timestamp coming from the backend is
 * turned into a `Date`.
 *
 * ## Why this module exists
 *
 * FastAPI/Pydantic v1 serialises the naive MySQL `TIMESTAMP` / `datetime.utcnow()`
 * values **without a zone designator** (`"2026-03-23T10:23:58"`). `new Date(...)`
 * reads such a string as *local* time, so every relative time in the game was
 * wrong by exactly the player's UTC offset — at UTC+3 a three-hour-old post read
 * as «только что».
 *
 * ## Contract
 *
 * - A string that already carries an offset (`Z`, `+HH:MM`, `+HHMM`, `-HH:MM`) is
 *   parsed **as-is** and never shifted again. This is not hypothetical:
 *   `battle-service` emits `deadline_at` with `+03:00` on one path and naive on
 *   another, so a blind «append Z» would corrupt the turn timer.
 * - A string with **no** offset is treated as **UTC**.
 * - Rendering always goes through the browser's own locale conversion, so the
 *   player's timezone and DST are handled by the platform. No manual offset
 *   arithmetic lives here or should live at any call site.
 * - These functions are **total**: `null`, `undefined`, `''` and malformed input
 *   never throw and never leak an `Invalid Date` to a renderer.
 *
 * ## Assumption this rests on (verified, not guessed)
 *
 * Naive == UTC. All app containers and MySQL run in UTC and **no `TZ`
 * environment variable is set in `docker-compose.yml` or
 * `docker-compose.prod.yml`** (`NOW() == UTC_TIMESTAMP()`). If a `TZ` var is
 * ever added to a container, naive timestamps stop being UTC and this module —
 * and every timestamp in the UI — silently becomes wrong again.
 *
 * ## Forward compatibility
 *
 * When the backend eventually emits explicit UTC offsets everywhere (Stage 2),
 * this module degrades to a pass-through and **no call site has to change**.
 */

/**
 * Anchored to the end of the string on purpose: an unanchored `[Z+]` would
 * match the `-` inside the date part of e.g. `2026-03-23`.
 */
const OFFSET_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/** `2026-03-23 10:23:58` — MySQL-ish, space instead of `T`. */
const SPACE_SEPARATED_RE = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/;

const MS_PER_MINUTE = 60_000;
const MS_PER_HOUR = 3_600_000;
const MS_PER_DAY = 86_400_000;

/** Beyond this age a relative label is replaced by an absolute date. */
const RELATIVE_WINDOW_DAYS = 7;
/** Older than this, the absolute `short` fallback also spells out the year. */
const SHOW_YEAR_AFTER_DAYS = 365;

/** Placeholder rendered when a timestamp is missing or unparseable. */
export const EMPTY_DATE_PLACEHOLDER = '—';

/**
 * Parse a server timestamp into a `Date`, or `null` when it is absent or
 * unparseable. Never throws.
 */
export const parseServerDate = (raw: string | null | undefined): Date | null => {
  if (!raw || typeof raw !== 'string') return null;

  const normalized = raw.replace(SPACE_SEPARATED_RE, '$1T$2');
  const iso = OFFSET_SUFFIX_RE.test(normalized) ? normalized : `${normalized}Z`;
  const ms = Date.parse(iso);

  return Number.isFinite(ms) ? new Date(ms) : null;
};

/**
 * Epoch milliseconds for a server timestamp, or `0` when absent/unparseable.
 * `0` is a deliberately harmless value for "older than anything".
 */
export const serverDateMs = (raw: string | null | undefined): number => {
  const date = parseServerDate(raw);
  return date ? date.getTime() : 0;
};

/* ── Relative time ─────────────────────────────────────────────────────── */

/**
 * Wording of the units. The three styles are the ones that already existed in
 * the five hand-rolled copies this module replaced; each call site keeps the
 * exact strings it showed before.
 *
 * - `short`   — «5 мин. назад», «3 ч. назад», «2 дн. назад»
 * - `compact` — «5 мин», «3 ч», «2 д» (messenger list, no room for more)
 * - `long`    — «5 минут назад», «3 часа назад», «2 дня назад»
 */
export type RelativeTimeStyle = 'short' | 'compact' | 'long';

/**
 * Absolute format used once the relative window is exceeded.
 *
 * - `short`   — «23 мар.» (plus the year when older than a year)
 * - `numeric` — «23.03»
 * - `long`    — «23 мар» / «23 мар 2025»
 * - `none`    — never falls back; keeps counting in hours indefinitely
 */
export type RelativeTimeFallback = 'short' | 'numeric' | 'long' | 'none';

export interface RelativeTimeOptions {
  style?: RelativeTimeStyle;
  /** Defaults to the absolute format that matches `style`. */
  fallback?: RelativeTimeFallback;
  /** Render «вчера» instead of «1 день назад». */
  yesterday?: boolean;
  /** Returned for missing/unparseable input. Defaults to «—». */
  invalid?: string;
}

const NOW_LABEL: Record<RelativeTimeStyle, string> = {
  short: 'только что',
  compact: 'сейчас',
  long: 'только что',
};

const DEFAULT_FALLBACK: Record<RelativeTimeStyle, RelativeTimeFallback> = {
  short: 'short',
  compact: 'numeric',
  long: 'long',
};

const SHORT_MONTHS = [
  'янв', 'фев', 'мар', 'апр', 'май', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
];

/**
 * Plural forms carried over verbatim from the previous `LogsTab` /
 * `OnlineUsersPage` copies so no user-visible wording changes with this fix.
 */
const pluralMinutes = (n: number): string =>
  n === 1 ? 'минуту' : n < 5 ? 'минуты' : 'минут';

const pluralHours = (n: number): string =>
  n === 1 ? 'час' : n < 5 ? 'часа' : 'часов';

const pluralDays = (n: number): string => (n < 5 ? 'дня' : 'дней');

const formatUnit = (
  style: RelativeTimeStyle,
  value: number,
  unit: 'minute' | 'hour' | 'day',
): string => {
  if (style === 'compact') {
    if (unit === 'minute') return `${value} мин`;
    if (unit === 'hour') return `${value} ч`;
    return `${value} д`;
  }

  if (style === 'long') {
    if (unit === 'minute') return `${value} ${pluralMinutes(value)} назад`;
    if (unit === 'hour') return `${value} ${pluralHours(value)} назад`;
    return `${value} ${pluralDays(value)} назад`;
  }

  if (unit === 'minute') return `${value} мин. назад`;
  if (unit === 'hour') return `${value} ч. назад`;
  return `${value} дн. назад`;
};

const formatAbsoluteFallback = (
  date: Date,
  fallback: RelativeTimeFallback,
  diffDays: number,
): string => {
  if (fallback === 'numeric') {
    return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
  }

  if (fallback === 'long') {
    const label = `${date.getDate()} ${SHORT_MONTHS[date.getMonth()]}`;
    return date.getFullYear() === new Date().getFullYear()
      ? label
      : `${label} ${date.getFullYear()}`;
  }

  return date.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: diffDays > SHOW_YEAR_AFTER_DAYS ? 'numeric' : undefined,
  });
};

/**
 * Human-readable age of a server timestamp, in Russian, in the player's own
 * timezone. The canonical replacement for the five divergent local copies.
 */
export const formatRelativeTime = (
  raw: string | null | undefined,
  opts: RelativeTimeOptions = {},
): string => {
  const style = opts.style ?? 'short';
  const fallback = opts.fallback ?? DEFAULT_FALLBACK[style];
  const invalid = opts.invalid ?? EMPTY_DATE_PLACEHOLDER;

  const date = parseServerDate(raw);
  if (!date) return invalid;

  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.floor(diffMs / MS_PER_MINUTE);
  const diffHours = Math.floor(diffMs / MS_PER_HOUR);
  const diffDays = Math.floor(diffMs / MS_PER_DAY);

  if (diffMinutes < 1) return NOW_LABEL[style];
  if (diffMinutes < 60) return formatUnit(style, diffMinutes, 'minute');

  // `none` keeps counting hours forever instead of ever showing a date.
  if (fallback === 'none') return formatUnit(style, diffHours, 'hour');

  if (diffHours < 24) return formatUnit(style, diffHours, 'hour');
  if (diffDays === 1 && opts.yesterday) return 'вчера';
  if (diffDays < RELATIVE_WINDOW_DAYS) return formatUnit(style, diffDays, 'day');

  return formatAbsoluteFallback(date, fallback, diffDays);
};

/* ── Absolute time ─────────────────────────────────────────────────────── */

const DEFAULT_DATE_TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
};

/** Absolute date + time in the player's timezone, `ru-RU`. */
export const formatServerDateTime = (
  raw: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = DEFAULT_DATE_TIME_OPTIONS,
): string => {
  const date = parseServerDate(raw);
  return date ? date.toLocaleString('ru-RU', opts) : EMPTY_DATE_PLACEHOLDER;
};

/** Absolute date (no time) in the player's timezone, `ru-RU`. */
export const formatServerDate = (
  raw: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long', year: 'numeric' },
): string => {
  const date = parseServerDate(raw);
  return date ? date.toLocaleDateString('ru-RU', opts) : EMPTY_DATE_PLACEHOLDER;
};
