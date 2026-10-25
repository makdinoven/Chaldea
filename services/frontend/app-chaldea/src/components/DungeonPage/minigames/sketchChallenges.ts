import type {
  ChallengeKind,
  ChallengeResult,
  ChallengeStart,
  ChallengeStep,
  GateParams,
  LockpickParams,
  RunesParams,
  ShadowParams,
  ShieldParams,
  StarsParams,
} from '../../../api/dungeons';
import { freshLock, press } from './lockpick';
import { advanceGate, freshGate, shieldParried } from './warrior';
import { advanceShadow, freshShadow, starsTurn, starsWhole } from './intel';

/*
  The challenges played offline, for the board sketch: made-up games settled
  in the browser by the server's rules (challenges.py), so they can be tried
  without a run. The real ones always come from and go back to the server.
*/

/** What the server would keep to itself: the lever's stone, the bearing stones. */
export interface SketchSecret {
  target?: [number, number];
  /** The seal: the sigil's nodes, how far along, the nodes resonating now. */
  sigil?: { path: number[]; at: number; mistakes: number; pulsing: number[] };
  bearing?: boolean[];
  pressed: number;
  pulled: number[];
  collapses: number;
}

const MESSAGES: Record<ChallengeKind, Record<string, string>> = {
  lockpick: {
    open: 'Замок вскрыт — дверь открыта!',
    broke: 'Отмычка сломалась — замок не поддался.',
    time: 'Не успели — замок так и не поддался.',
    short: 'Бросили возиться с замком.',
  },
  illusion: {
    open: 'Иллюзия рассеяна — за ней тайный проход!',
    broke: 'Руны сбились — иллюзия держится.',
    time: 'Не успели — иллюзия держится.',
    short: 'Отступили от иллюзорной стены.',
  },
  mechanism: {
    open: 'Скрытый рычаг найден — в стене открылся проход!',
    broke: 'Механизм так и не нашёлся.',
    short: 'Бросили поиски механизма.',
  },
  rubble: {
    open: 'Завал разобран — путь свободен!',
    broke: 'Завал обрушился!',
    short: 'Бросили разбирать завал.',
  },
  shield: {},
  seal: {
    open: 'Знак проведён до конца — печать рассыпается искрами!',
    broke: 'Печать бьёт в ответ!',
    short: 'Отступили от печати.',
  },
  search: {
    open: 'Тайник найден!',
    broke: 'Тайника не нашлось.',
    short: 'Бросили обыск.',
  },
  watch: {},
  scout: {
    open: 'Путь разведан: впереди сокровищница, в коридоре ловушка.',
    broke: 'Вас заметили в коридоре!',
    time: 'Не успели — пришлось вернуться.',
    short: 'Вернулись, не дойдя.',
  },
  disarm: { open: 'Ловушка обезврежена!', broke: 'Ловушка сработала!', short: 'Бросили возиться с ловушкой.' },
  insight: { open: 'Знаки прочитаны!', time: 'Знаки так и не сложились.', short: 'Отступили от знаков.' },
  gate: {
    open: 'Решётка поднята и подпёрта — путь открыт!',
    broke: 'Решётка срывается вниз!',
    time: 'Не хватило сил — решётка опускается.',
    short: 'Отпустили решётку.',
  },
};

const MECH_COLS = 5;
const MECH_ROWS = 4;
const RUBBLE_STONES = 9;
const RUBBLE_BEARING = 3;

const pick = (n: number) => Math.floor(Math.random() * n);

export const makeSketchChallenge = (kind: ChallengeKind): { start: ChallengeStart; secret: SketchSecret } => {
  const secret: SketchSecret = { pressed: 0, pulled: [], collapses: 0 };
  let params: ChallengeStart['params'];
  if (kind === 'lockpick') {
    params = {
      pins: Array.from({ length: 4 }, () => ({
        freq: 0.4 + Math.random() * 0.3,
        phase: Math.random() * Math.PI * 2,
        center: Math.random() - 0.5,
        width: 0.3,
      })),
      strains: 2,
      time_limit_ms: 16000,
    };
  } else if (kind === 'illusion') {
    const sequence: number[] = [];
    while (sequence.length < 5) {
      const g = pick(9);
      if (sequence[sequence.length - 1] !== g) sequence.push(g);
    }
    params = { glyphs: 9, sequence, flash_ms: 700, mistakes: 1, time_limit_ms: 15500 };
  } else if (kind === 'shield') {
    const blows: ShieldParams['blows'] = [];
    let at = 1500;
    for (let i = 0; i < 6; i += 1) {
      blows.push({ at_ms: at, side: pick(3) });
      at += 900 + pick(600);
    }
    params = { blows, warn_ms: 800, start_side: 1, time_limit_ms: blows[blows.length - 1].at_ms + 800 };
  } else if (kind === 'gate') {
    const surges = Array.from({ length: 3 }, () => ({
      at_ms: 1000 + pick(9000),
      dur_ms: 400 + pick(400),
      force: 1.2 + Math.round(Math.random() * 60) / 100,
    })).sort((a, b) => a.at_ms - b.at_ms);
    params = { zone: [0.57, 0.79], hold_ms: 3500, surges, time_limit_ms: 11000, look: Math.random() < 0.5 ? 'grate' : 'slab' };
  } else if (kind === 'seal') {
    const path = [pick(8)];
    while (path.length < 5) {
      const free = [...Array(8).keys()].filter(
        (n) => !path.includes(n) && ![1, 7].includes((((n - path[path.length - 1]) % 8) + 8) % 8),
      );
      if (!free.length) break;
      path.push(free[pick(free.length)]);
    }
    secret.sigil = { path, at: 0, mistakes: 0, pulsing: [] };
    const pulsing = sealPulsing(secret.sigil, []);
    params = { nodes: 8, start: path[0], steps: path.length - 1, mistakes: 1, beat_ms: 1400, pulsing, offsets: sealOffsets(secret.sigil) };
  } else if (kind === 'scout') {
    const lamps = Array.from({ length: 8 }, (_, i) =>
      i % 3 === 2 ? null : { freq: 0.35 + Math.random() * 0.3, phase: Math.random(), duty: 0.42 },
    );
    params = { cells: 8, lamps, time_limit_ms: 4000 + 2200 * 8 };
  } else if (kind === 'disarm') {
    const taut = Array(7).fill(false) as boolean[];
    while (taut.filter(Boolean).length < 2) taut[pick(7)] = true;
    secret.bearing = taut;
    const safe = taut.map((t, i) => (t ? -1 : i)).filter((i) => i >= 0);
    const hint = safe[pick(safe.length)];
    const near = (i: number) => [i - 1, i + 1].filter((j) => j >= 0 && j < 7 && taut[j]).length;
    params = { wires: 7, taut: 2, mistakes: 1, shown: [[hint, near(hint)]] };
    secret.pulled = [hint];
  } else if (kind === 'insight') {
    params = { rings: 3, steps: 8, offsets: [1 + pick(7), 1 + pick(7), 1 + pick(7)], time_limit_ms: 32000, seed: 1 + pick(99999) };
  } else if (kind === 'search') {
    secret.target = [pick(6), pick(4)];
    params = { cols: 6, rows: 4, probes: 4 };
  } else if (kind === 'mechanism') {
    secret.target = [pick(MECH_COLS), pick(MECH_ROWS)];
    params = { cols: MECH_COLS, rows: MECH_ROWS, probes: 5 };
  } else {
    const bearing = Array(RUBBLE_STONES).fill(false) as boolean[];
    // The lower rows bear more often (weights 3, 2, 1 for the bottom, middle and top rows).
    const weightOf = (i: number) => (i < 4 ? 3 : i < 7 ? 2 : 1);
    while (bearing.filter(Boolean).length < RUBBLE_BEARING) {
      const free = [...Array(RUBBLE_STONES).keys()].filter((i) => !bearing[i]);
      let roll = Math.random() * free.reduce((sum, i) => sum + weightOf(i), 0);
      const chosen = free.find((i) => (roll -= weightOf(i)) <= 0) ?? free[free.length - 1];
      bearing[chosen] = true;
    }
    secret.bearing = bearing;
    // Mostly honest cracks, as for a decent warrior.
    const cracks = bearing.map((b) => ((Math.random() < 0.8 ? b : !b) ? 2 + pick(2) : pick(2)));
    params = { cracks, to_clear: 4, braces: 1 };
  }
  return {
    start: { kind, off_class: false, stamina_consumed: 0, challenge_id: `sketch-${Date.now()}`, params },
    secret,
  };
};

const resultOf = (kind: ChallengeKind, outcome: string): ChallengeResult => ({
  passed: outcome === 'open',
  kind,
  outcome,
  message: MESSAGES[kind][outcome] ?? MESSAGES[kind].short,
  corridor_id: null,
  character_id: 0,
});

/** A one-go game over: settle it as the server would. */
export const settleSketch = (start: ChallengeStart, presses: number[], ended?: string): ChallengeResult => {
  if (start.kind === 'shield') {
    const params = start.params as ShieldParams;
    const parried = shieldParried(params, presses, Infinity);
    const block = parried / params.blows.length;
    return {
      passed: block >= 0.5,
      kind: 'shield',
      outcome: 'open',
      message: parried
        ? `Щит поднят: отбито ${parried} из ${params.blows.length}. Удар слабее на ${Math.round(75 * block)}%.`
        : 'Ни один удар не отбит — щит не поднят.',
      corridor_id: null,
      character_id: 0,
      block,
    };
  }
  if (start.kind === 'scout') {
    const end = advanceShadow(start.params as ShadowParams, freshShadow(), presses, Infinity);
    return resultOf('scout', end.over ?? (ended === 'time' ? 'time' : 'short'));
  }
  if (start.kind === 'insight') {
    const params = start.params as StarsParams;
    let offsets = [...params.offsets];
    for (const r of presses) {
      offsets = starsTurn(offsets, r, params.steps);
      if (starsWhole(offsets)) return resultOf('insight', 'open');
    }
    return resultOf('insight', ended === 'time' ? 'time' : 'short');
  }
  if (start.kind === 'gate') {
    const end = advanceGate(start.params as GateParams, freshGate(), presses, Infinity);
    return resultOf('gate', end.over ?? (ended === 'time' ? 'time' : 'short'));
  }
  if (start.kind === 'lockpick') {
    const params = start.params as LockpickParams;
    const end = presses.reduce((state, t) => press(params, state, t), freshLock());
    return resultOf('lockpick', end.over ?? (ended === 'time' ? 'time' : 'short'));
  }
  if (start.kind === 'illusion') {
    const params = start.params as RunesParams;
    let step = 0;
    let mistakes = 0;
    for (const g of presses) {
      if (g === params.sequence[step]) {
        step += 1;
        if (step === params.sequence.length) return resultOf('illusion', 'open');
      } else if (++mistakes > params.mistakes) return resultOf('illusion', 'broke');
    }
    return resultOf('illusion', ended === 'time' ? 'time' : 'short');
  }
  return resultOf(start.kind, 'short');
};

/** The true next node of the sigil among one false one. */
function sealPulsing(sigil: NonNullable<SketchSecret['sigil']>, ruledOut: number[]) {
  const correct = sigil.path[sigil.at + 1];
  const free = [...Array(8).keys()].filter(
    (n) => !sigil.path.slice(0, sigil.at + 1).includes(n) && n !== correct && !ruledOut.includes(n),
  );
  const decoy = free.length ? [free[Math.floor(Math.random() * free.length)]] : [];
  sigil.pulsing = [correct, ...decoy].sort((a, b) => a - b);
  return sigil.pulsing;
}

/** The true node pulses in time (0), the false ones off the beat by about a fifth of it. */
function sealOffsets(sigil: NonNullable<SketchSecret['sigil']>) {
  const correct = sigil.path[sigil.at + 1];
  return sigil.pulsing.map((n) => (n === correct ? 0 : (Math.random() < 0.5 ? -1 : 1) * (0.18 + Math.random() * 0.08)));
}

/** One move of a stepped game, answered as the server would. */
export const stepSketch = (
  start: ChallengeStart,
  secret: SketchSecret,
  move: { x?: number; y?: number; index?: number },
): ChallengeStep => {
  if (start.kind === 'mechanism' && secret.target && move.x !== undefined && move.y !== undefined) {
    const [tx, ty] = secret.target;
    const distance = Math.abs(move.x - tx) + Math.abs(move.y - ty);
    secret.pressed += 1;
    const probes = (start.params as { probes: number }).probes;
    const over = distance === 0 ? 'open' : secret.pressed >= probes ? 'broke' : null;
    return { kind: 'mechanism', distance, result: over ? resultOf('mechanism', over) : null };
  }
  if (start.kind === 'seal' && secret.sigil && move.index !== undefined) {
    const sigil = secret.sigil;
    const params = start.params as { steps: number; mistakes: number };
    if (move.index === sigil.path[sigil.at + 1]) {
      sigil.at += 1;
      if (sigil.at === params.steps) return { kind: 'seal', safe: true, result: resultOf('seal', 'open') };
      const pulsing = sealPulsing(sigil, []);
      return { kind: 'seal', safe: true, pulsing, offsets: sealOffsets(sigil) };
    }
    sigil.mistakes += 1;
    if (sigil.mistakes > params.mistakes) return { kind: 'seal', safe: false, result: resultOf('seal', 'broke') };
    const pulsing = sealPulsing(sigil, [move.index]);
    return { kind: 'seal', safe: false, pulsing, offsets: sealOffsets(sigil) };
  }
  if (start.kind === 'search' && secret.target && move.x !== undefined && move.y !== undefined) {
    const [tx, ty] = secret.target;
    secret.pressed += 1;
    if (move.x === tx && move.y === ty) return { kind: 'search', way: null, result: resultOf('search', 'open') };
    const way = Math.round(Math.atan2(tx - move.x, -(ty - move.y)) / (Math.PI / 4));
    const probes = (start.params as { probes: number }).probes;
    return {
      kind: 'search',
      way: ((way % 8) + 8) % 8,
      result: secret.pressed >= probes ? resultOf('search', 'broke') : null,
    };
  }
  if (start.kind === 'disarm' && secret.bearing && move.index !== undefined) {
    const taut = secret.bearing;
    secret.pulled.push(move.index);
    if (taut[move.index]) {
      secret.collapses += 1;
      return { kind: 'disarm', safe: false, result: secret.collapses > 1 ? resultOf('disarm', 'broke') : null };
    }
    const near = [move.index - 1, move.index + 1].filter((j) => j >= 0 && j < taut.length && taut[j]).length;
    const done = taut.every((t, i) => t || secret.pulled.includes(i));
    return { kind: 'disarm', safe: true, near, result: done ? resultOf('disarm', 'open') : null };
  }
  if (start.kind === 'rubble' && secret.bearing && move.index !== undefined) {
    secret.pulled.push(move.index);
    const params = start.params as { to_clear: number; braces: number };
    if (secret.bearing[move.index]) {
      secret.collapses += 1;
      const over = secret.collapses > params.braces;
      return { kind: 'rubble', safe: false, result: over ? resultOf('rubble', 'broke') : null };
    }
    const cleared = secret.pulled.filter((i) => !secret.bearing?.[i]).length;
    return { kind: 'rubble', safe: true, result: cleared >= params.to_clear ? resultOf('rubble', 'open') : null };
  }
  return { kind: start.kind };
};
