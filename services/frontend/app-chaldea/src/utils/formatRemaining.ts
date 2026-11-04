/**
 * FEAT-198 (A8) — the one format of a time limit shown to the player: a live
 * countdown «2 д 05:13:20» / «05:13:20» / «13:20», not an absolute «до HH:MM».
 *
 * Pair with `useCountdownTo` (hooks/useCountdown.ts), which re-renders every
 * second; server timestamps go through `parseServerDate` (naive = UTC).
 */

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_DAY = 86400;

const pad2 = (n: number): string => String(n).padStart(2, '0');

/** Seconds → «2 д 05:13:20», «05:13:20» (≥ 1 h) or «13:20». Negative counts as 0. */
export const formatRemaining = (totalSeconds: number): string => {
  const total = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(total / SECONDS_PER_DAY);
  const hours = Math.floor((total % SECONDS_PER_DAY) / SECONDS_PER_HOUR);
  const minutes = Math.floor((total % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  const seconds = total % SECONDS_PER_MINUTE;
  const clock = `${pad2(minutes)}:${pad2(seconds)}`;
  if (days > 0) return `${days} д ${pad2(hours)}:${clock}`;
  if (hours > 0) return `${pad2(hours)}:${clock}`;
  return clock;
};

/** «осталось 2 д 05:13:20». */
export const remainingText = (totalSeconds: number): string => `осталось ${formatRemaining(totalSeconds)}`;

/** Whole seconds from now until `target` (0 when absent or past). */
export const secondsUntil = (target: Date | null, nowMs: number = Date.now()): number =>
  target ? Math.max(0, Math.ceil((target.getTime() - nowMs) / 1000)) : 0;
