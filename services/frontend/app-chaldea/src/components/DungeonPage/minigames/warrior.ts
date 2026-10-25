import type { GateParams, ShieldParams } from '../../../api/dungeons';

/*
  The warrior's games, as the server has them (dungeon-service challenges.py):
  the browser plays them to draw the game, the server replays what was done
  to settle it — the two must agree.
*/

// --- the party shield ---

/** A turn of the shield is sent as ms * SHIELD_CODE + side. */
export const SHIELD_CODE = 4;
/** Turns closer together than this are not counted (the server would refuse them). */
export const SHIELD_MIN_GAP_MS = 60;

/** Blows turned aside: the shield faced each when it landed. */
export const shieldParried = (params: ShieldParams, presses: number[], untilMs: number) => {
  let parried = 0;
  for (const blow of params.blows) {
    if (blow.at_ms > untilMs) break;
    let side = params.start_side;
    for (const p of presses) {
      if (Math.floor(p / SHIELD_CODE) > blow.at_ms) break;
      side = p % SHIELD_CODE;
    }
    if (side === blow.side) parried += 1;
  }
  return parried;
};

// --- the gate ---

export const GATE_TICK_MS = 50;
export const GATE_START = 0.45;
export const GATE_SLAM = 0.05;
const GATE_GRAVITY = 0.9;
const GATE_PUSH = 2.0;
const GATE_DAMPING = 0.9;
/** Presses and releases closer together than this are pushed apart (the server would refuse them). */
export const GATE_MIN_TOGGLE_GAP_MS = 30;

/** One tick of the gate: its new height (0 down … 1 up) and speed. */
export const gateStep = (params: GateParams, level: number, speed: number, holding: boolean, t: number) => {
  let surge = 0;
  for (const s of params.surges) if (s.at_ms <= t && t < s.at_ms + s.dur_ms) surge += s.force;
  const accel = (holding ? GATE_PUSH : 0) - GATE_GRAVITY - surge;
  const dt = GATE_TICK_MS / 1000;
  let v = (speed + accel * dt) * GATE_DAMPING;
  let h = level + v * dt;
  if (h >= 1) {
    h = 1;
    v = 0;
  }
  return { level: h, speed: v };
};

export type GateOutcome = 'open' | 'broke' | 'time' | 'short';

export interface GateState {
  /** The next tick to play, ms from the start. */
  t: number;
  level: number;
  speed: number;
  held: number;
  holding: boolean;
  /** How many of the presses and releases have been taken in. */
  next: number;
  over: GateOutcome | null;
}

export const freshGate = (): GateState => ({
  t: 0,
  level: GATE_START,
  speed: 0,
  held: 0,
  holding: false,
  next: 0,
  over: null,
});

/** Plays the ticks up to `untilMs` with the grip so far (ms of each press and release, in turn). */
export const advanceGate = (params: GateParams, state: GateState, toggles: number[], untilMs: number): GateState => {
  const s = { ...state };
  const [lo, hi] = params.zone;
  while (!s.over && s.t <= untilMs) {
    if (s.t >= params.time_limit_ms) {
      s.over = 'time';
      break;
    }
    while (s.next < toggles.length && toggles[s.next] <= s.t) {
      s.holding = !s.holding;
      s.next += 1;
    }
    const step = gateStep(params, s.level, s.speed, s.holding, s.t);
    s.level = step.level;
    s.speed = step.speed;
    if (s.level >= lo && s.level <= hi) {
      s.held += GATE_TICK_MS;
      if (s.held >= params.hold_ms) s.over = 'open';
    }
    if (!s.over && s.level <= GATE_SLAM) s.over = 'broke';
    s.t += GATE_TICK_MS;
  }
  return s;
};
