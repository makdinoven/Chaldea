import type { LockPin, LockpickParams } from '../../../api/dungeons';

/*
  The lock's rules, as the server has them (dungeon-service challenges.py):
  the browser plays them to draw the game, the server replays the presses to
  settle it — the two must agree.
*/

/** Where a pin's tip is, from -1 (down) to 1 (up), `sinceMs` after it woke. */
export const pinHeight = (pin: LockPin, sinceMs: number) =>
  Math.sin(2 * Math.PI * pin.freq * (sinceMs / 1000) + pin.phase);

/** A press counts if the pin was in the window then or this long before: the eye sees it, the hand follows. */
export const PRESS_GRACE_MS = 70;

const inWindowAt = (pin: LockPin, sinceMs: number) => Math.abs(pinHeight(pin, sinceMs) - pin.center) <= pin.width;

/** The pin's tip is in the shear window now, or was a moment ago (PRESS_GRACE_MS). */
export const inWindow = (pin: LockPin, sinceMs: number) =>
  inWindowAt(pin, sinceMs) || (sinceMs - PRESS_GRACE_MS >= 0 && inWindowAt(pin, sinceMs - PRESS_GRACE_MS));

export type LockOutcome = 'open' | 'broke' | 'time' | 'short';

export interface LockState {
  /** Pins set so far (the next one is active). */
  set: number;
  /** When the active pin woke, ms from the start. */
  wokeAt: number;
  strains: number;
  over: LockOutcome | null;
}

export const freshLock = (): LockState => ({ set: 0, wokeAt: 0, strains: 0, over: null });

/** One press at `t` ms from the start: the lock as it stands after it. */
export const press = (params: LockpickParams, state: LockState, t: number): LockState => {
  if (state.over) return state;
  if (t > params.time_limit_ms) return { ...state, over: 'time' };
  const pin = params.pins[state.set];
  if (inWindow(pin, t - state.wokeAt)) {
    const set = state.set + 1;
    return { ...state, set, wokeAt: t, over: set === params.pins.length ? 'open' : null };
  }
  const strains = state.strains + 1;
  return { ...state, strains, over: strains > params.strains ? 'broke' : null };
};

/** Presses closer together than this are not counted (the server would refuse them). */
export const MIN_PRESS_GAP_MS = 80;
