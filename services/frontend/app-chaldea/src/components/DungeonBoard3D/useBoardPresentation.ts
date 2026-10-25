import { useEffect, useReducer, useRef } from 'react';
import type { CorridorEvent, RoomEvent } from '../../api/dungeons';
import type { CorridorScene, DiceThrow } from './DungeonBoardScene';

/*
  Plays a move the server has already decided, step by step on the board: on a
  trapped corridor the party walks to its middle, the gods' dice tumble and the
  trap springs (or is caught) before it walks on; a rune
  circle holds the party for a moment before throwing it to its target, a trap
  room's check is thrown once the party is in. Nothing here decides anything —
  the dice only show the server's `passed`.
*/

/** What the board needs from a move: the leader's own response or a squadmate's `room_entered`. */
export interface BoardMoveEvent {
  corridor_event: CorridorEvent | null;
  room_event: RoomEvent | null;
  /** Where the party ended up, when the event says. */
  new_room_id: number | null;
  /** performance.now() when the event arrived: a later one is played, an older one never again. */
  at: number;
}

const DICE_SETTLE_MS = 1200;
/** Time for the figurines to walk from the room to the middle of a corridor. */
const WALK_IN_MS = 1600;
/** The trap springing (or caught) before the party walks on. */
const TRAP_SHOW_MS = 1100;
const TELEPORT_DELAY_MS = 1100;
/** Time for the figurines to walk into a room before its trap is thrown for. */
const HOP_MS = 2400;
/** Dice stay on the table a little after they settle, then are taken away. */
const DICE_LINGER_MS = 3500;
const MAX_TELEPORT_CHAIN = 5;

interface Plan {
  /** Where the party is shown from each moment on; null = where the server says it is; `stop` = halfway down a corridor. */
  steps: { at: number; roomId: number | null; stop?: { from: number; to: number } }[];
  /** The corridor's trap springing in the middle of the way. */
  trap: { at: number; passed: boolean } | null;
  /** Rooms kept face down until the party gets there. */
  veil: Map<number, number>;
  dice: DiceThrow[];
  /** The party has arrived and the last dice have settled. */
  settled: number;
  /** The dice are taken off the table. */
  end: number;
}

/** Two dice whose total shows the check's outcome: 7 and up passed, 6 and below failed. */
const diceShowing = (passed: boolean): [number, number] => {
  const pairs: [number, number][] = [];
  for (let a = 1; a <= 6; a++) {
    for (let b = 1; b <= 6; b++) {
      if (a + b >= 7 === passed) pairs.push([a, b]);
    }
  }
  return pairs[Math.floor(Math.random() * pairs.length)];
};

const makePlan = (
  event: BoardMoveEvent,
  fromRoomId: number | null,
  revealedBefore: Set<number>,
  now: number,
): Plan | null => {
  const ce = event.corridor_event;
  const corridorPassed = ce?.type === 'trap' && ce.stat_check && typeof ce.passed === 'boolean' ? ce.passed : null;

  // Rooms the party was thrown from; a red portal rolls (and fails) before it throws.
  const origins: { roomId: number; rolled: boolean }[] = [];
  let ev: RoomEvent | null | undefined = event.room_event;
  for (let depth = 0; ev?.type === 'teleported' && depth < MAX_TELEPORT_CHAIN; depth++) {
    if (typeof ev.teleported_from === 'number') origins.push({ roomId: ev.teleported_from, rolled: !!ev.red_portal });
    ev = ev.followup;
  }
  const roomPassed =
    (ev?.type === 'trap_triggered' || ev?.type === 'portal_spotted') && ev.stat_check && typeof ev.passed === 'boolean'
      ? ev.passed
      : null;
  if (corridorPassed === null && origins.length === 0 && roomPassed === null) return null;

  const steps: Plan['steps'] = [];
  const veil = new Map<number, number>();
  const dice: DiceThrow[] = [];
  const hideUntil = (roomId: number | null, at: number) => {
    if (roomId !== null && !revealedBefore.has(roomId)) veil.set(roomId, at);
  };

  let t = now;
  let trap: Plan['trap'] = null;
  if (corridorPassed !== null) {
    // Halfway down the corridor the dice decide, and the trap springs or is caught; then the party walks on.
    const corridorTo = origins[0]?.roomId ?? event.new_room_id;
    if (fromRoomId !== null) {
      steps.push(
        corridorTo !== null
          ? { at: t, roomId: fromRoomId, stop: { from: fromRoomId, to: corridorTo } }
          : { at: t, roomId: fromRoomId },
      );
    }
    t += corridorTo !== null ? WALK_IN_MS : 0;
    dice.push({ values: diceShowing(corridorPassed), at: t });
    t += DICE_SETTLE_MS;
    trap = { at: t, passed: corridorPassed };
    t += TRAP_SHOW_MS;
  }
  origins.forEach(({ roomId, rolled }) => {
    steps.push({ at: t, roomId });
    hideUntil(roomId, t);
    if (rolled) {
      // In the red portal: the dice come up short, then it pulls the party away.
      t += HOP_MS;
      dice.push({ values: diceShowing(false), at: t });
      t += DICE_SETTLE_MS;
    }
    t += TELEPORT_DELAY_MS;
  });
  steps.push({ at: t, roomId: null });
  hideUntil(event.new_room_id, t);
  if (roomPassed !== null) {
    t += HOP_MS;
    dice.push({ values: diceShowing(roomPassed), at: t });
    t += DICE_SETTLE_MS;
  }
  const lastThrow = dice.length > 0 ? dice[dice.length - 1].at + DICE_LINGER_MS : 0;
  return { steps, trap, veil, dice, settled: t, end: Math.max(t, lastThrow) };
};

export interface BoardPresentation {
  /** The room the figurines stand in right now. */
  roomId: number | null;
  revealed: Set<number>;
  dice: DiceThrow | null;
  /** The party shown halfway down a corridor (a trapped stretch). */
  corridor: CorridorScene | null;
  /** A move is still being shown: the board takes no new orders and its outcome waits. */
  busy: boolean;
}

/**
 * The board's view of the run while moves are being shown. `enabled` = false
 * (the 2D map) skips the show and follows the server at once.
 */
export const useBoardPresentation = (
  event: BoardMoveEvent | null,
  actualRoomId: number | null,
  revealed: Set<number>,
  enabled: boolean,
): BoardPresentation => {
  // An event already there when the board appears (a reload) is not replayed.
  const handledAt = useRef(event ? event.at : -Infinity);
  const plan = useRef<Plan | null>(null);
  const shownRoom = useRef<number | null>(actualRoomId);
  const shownRevealed = useRef<Set<number>>(revealed);
  const [, rerender] = useReducer((n: number) => n + 1, 0);

  if (event && event.at > handledAt.current) {
    handledAt.current = event.at;
    plan.current = enabled ? makePlan(event, shownRoom.current, shownRevealed.current, performance.now()) : null;
  }

  const now = performance.now();
  if (plan.current && now >= plan.current.end) plan.current = null;
  const active = plan.current;

  let roomId = actualRoomId;
  let shown = revealed;
  let dice: DiceThrow | null = null;
  let corridor: CorridorScene | null = null;
  if (active) {
    const step = [...active.steps].reverse().find((s) => s.at <= now);
    if (step && step.roomId !== null) roomId = step.roomId;
    if (step?.stop) corridor = { ...step.stop, ambush: false, trap: active.trap };
    const hidden = [...active.veil].filter(([, at]) => at > now).map(([id]) => id);
    if (hidden.length > 0) {
      shown = new Set(revealed);
      hidden.forEach((id) => shown.delete(id));
    }
    dice = [...active.dice].reverse().find((d) => d.at <= now) ?? null;
  }

  // Wake up at every turn of the show.
  useEffect(() => {
    if (!active) return;
    const start = performance.now();
    const moments = [
      ...active.steps.map((s) => s.at),
      ...[...active.veil.values()],
      ...active.dice.map((d) => d.at),
      ...(active.trap ? [active.trap.at] : []),
      active.settled,
      active.end,
    ].filter((at) => at > start);
    const timers = [...new Set(moments)].map((at) => setTimeout(rerender, at - start + 5));
    return () => timers.forEach(clearTimeout);
  }, [active]);

  useEffect(() => {
    shownRoom.current = roomId;
    shownRevealed.current = shown;
  });

  return { roomId, revealed: shown, dice, corridor, busy: !!active && now < active.settled };
};
