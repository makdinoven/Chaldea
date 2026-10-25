import type { ShadowParams, StarsParams } from '../../../api/dungeons';

/*
  The scouting and reading games' rules, as the server has them
  (dungeon-service challenges.py shadow_* and stars_*): the browser plays them
  to draw the game, the server replays what was done to settle it.
*/

// --- scouting: the shadows ---

export const SHADOW_TICK_MS = 25;
export const SHADOW_MIN_GAP_MS = 80;

/** A lamp is lit for the first `duty` of each of its cycles. */
export const shadowLit = (lamp: ShadowParams['lamps'][number], t: number) => {
  if (!lamp) return false;
  const cycle = (((t / 1000) * lamp.freq + lamp.phase) % 1 + 1) % 1;
  return cycle < lamp.duty;
};

export type ShadowOutcome = 'open' | 'broke' | 'time' | 'short';

export interface ShadowState {
  /** The next tick to play, ms from the start. */
  t: number;
  /** 0 — the start, cells + 1 — the far end. */
  pos: number;
  next: number;
  over: ShadowOutcome | null;
}

export const freshShadow = (): ShadowState => ({ t: 0, pos: 0, next: 0, over: null });

/** Plays the ticks up to `untilMs` with the steps so far. */
export const advanceShadow = (params: ShadowParams, state: ShadowState, steps: number[], untilMs: number): ShadowState => {
  const s = { ...state };
  while (!s.over && s.t <= untilMs) {
    if (s.t >= params.time_limit_ms) {
      s.over = 'time';
      break;
    }
    while (s.next < steps.length && steps[s.next] <= s.t) {
      s.pos += 1;
      s.next += 1;
      if (s.pos > params.cells) {
        s.over = 'open';
        break;
      }
    }
    if (s.over) break;
    if (s.pos >= 1 && s.pos <= params.cells && shadowLit(params.lamps[s.pos - 1], s.t)) {
      s.over = 'broke';
      break;
    }
    s.t += SHADOW_TICK_MS;
  }
  return s;
};

// --- reading: the star chart ---

/** Turn a ring one step: it and the next ring move together. */
export const starsTurn = (offsets: number[], ring: number, steps: number) =>
  offsets.map((o, r) => (r === ring || r === ring + 1 ? (o + 1) % steps : o));

export const starsWhole = (offsets: number[]) => offsets.every((o) => o === 0);

/** The rings' stars, laid out from the chart's seed (the same on every screen). */
export const starsLayout = (params: StarsParams) => {
  let s = params.seed || 1;
  const rand = () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
  return Array.from({ length: params.rings }, () =>
    Array.from({ length: 3 + Math.floor(rand() * 2) }, () => ({ angle: rand() * Math.PI * 2, size: 0.6 + rand() * 0.6 })),
  );
};
