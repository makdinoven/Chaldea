import { getClientPrefs } from './clientPrefs';
import { getAudioContext } from './notifySound';

/*
  Sounds of the dungeon table, synthesised like the site's other sounds (no
  files): a figurine's footfall, a door's creak, the stone rumble of a room
  rising, dice on the board, a chest, a trap, a rune circle. They follow the
  same switch and volume as the rest of the site's sounds.
*/

export type DungeonSound =
  | 'step'
  | 'door'
  | 'rise'
  | 'dice'
  | 'chest'
  | 'coins'
  | 'trap'
  | 'disarm'
  | 'teleport'
  | 'mark'
  | 'vote';

/** The same sound again within this many ms (several triggers at once) plays once. */
const MIN_REPEAT_MS: Record<DungeonSound, number> = {
  step: 90,
  door: 300,
  rise: 400,
  dice: 400,
  chest: 400,
  coins: 300,
  trap: 400,
  disarm: 400,
  teleport: 400,
  mark: 250,
  vote: 150,
};
const lastPlayed: Partial<Record<DungeonSound, number>> = {};

let noiseBuffer: AudioBuffer | null = null;
const noise = (ctx: AudioContext) => {
  if (noiseBuffer && noiseBuffer.sampleRate === ctx.sampleRate) return noiseBuffer;
  const length = ctx.sampleRate * 2;
  noiseBuffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = noiseBuffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
  return noiseBuffer;
};

/** A burst of filtered noise: footfalls, thuds, clicks, rumbles and whooshes. */
const burst = (
  ctx: AudioContext,
  out: AudioNode,
  at: number,
  duration: number,
  options: { type: BiquadFilterType; freq: number; freqTo?: number; q?: number; gain: number; attack?: number },
) => {
  const src = ctx.createBufferSource();
  src.buffer = noise(ctx);
  const filter = ctx.createBiquadFilter();
  filter.type = options.type;
  filter.frequency.setValueAtTime(options.freq, at);
  if (options.freqTo) filter.frequency.exponentialRampToValueAtTime(options.freqTo, at + duration);
  filter.Q.value = options.q ?? 1;
  const env = ctx.createGain();
  const attack = options.attack ?? 0.005;
  env.gain.setValueAtTime(0.0001, at);
  env.gain.exponentialRampToValueAtTime(options.gain, at + attack);
  env.gain.exponentialRampToValueAtTime(0.0001, at + duration);
  src.connect(filter).connect(env).connect(out);
  src.start(at, Math.random() * 1.5);
  src.stop(at + duration + 0.05);
};

/** A plain tone with a quick strike and a fade: bells, coins, metal. */
const ping = (ctx: AudioContext, out: AudioNode, at: number, freq: number, duration: number, gain: number, type: OscillatorType = 'sine') => {
  const osc = ctx.createOscillator();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, at);
  const env = ctx.createGain();
  env.gain.setValueAtTime(0.0001, at);
  env.gain.exponentialRampToValueAtTime(gain, at + 0.004);
  env.gain.exponentialRampToValueAtTime(0.0001, at + duration);
  osc.connect(env).connect(out);
  osc.start(at);
  osc.stop(at + duration + 0.05);
};

/** A wooden creak: a buzzing low tone whose pitch wavers, through a narrow band. */
const creak = (ctx: AudioContext, out: AudioNode, at: number, duration: number, gain: number) => {
  const osc = ctx.createOscillator();
  osc.type = 'sawtooth';
  osc.frequency.setValueAtTime(95, at);
  const steps = 8;
  for (let i = 1; i <= steps; i++) {
    osc.frequency.linearRampToValueAtTime(95 + Math.random() * 70 + i * 6, at + (duration * i) / steps);
  }
  const band = ctx.createBiquadFilter();
  band.type = 'bandpass';
  band.frequency.value = 900;
  band.Q.value = 4;
  const env = ctx.createGain();
  env.gain.setValueAtTime(0.0001, at);
  env.gain.exponentialRampToValueAtTime(gain, at + 0.06);
  env.gain.setValueAtTime(gain, at + duration * 0.7);
  env.gain.exponentialRampToValueAtTime(0.0001, at + duration);
  osc.connect(band).connect(env).connect(out);
  osc.start(at);
  osc.stop(at + duration + 0.05);
};

const PLAYERS: Record<DungeonSound, (ctx: AudioContext, out: AudioNode, t: number) => void> = {
  step: (ctx, out, t) => burst(ctx, out, t, 0.07, { type: 'lowpass', freq: 380 + Math.random() * 120, gain: 0.55 }),
  door: (ctx, out, t) => {
    creak(ctx, out, t, 0.6, 0.22);
    burst(ctx, out, t + 0.62, 0.18, { type: 'lowpass', freq: 220, gain: 0.7 });
  },
  rise: (ctx, out, t) => {
    burst(ctx, out, t, 1.5, { type: 'lowpass', freq: 90, freqTo: 160, gain: 0.85, attack: 0.35 });
    burst(ctx, out, t + 0.2, 1.1, { type: 'bandpass', freq: 500, q: 0.8, gain: 0.08, attack: 0.3 });
  },
  dice: (ctx, out, t) => {
    // Two dice: a first knock each, then smaller bounces closing in.
    let at = t;
    let gap = 0.13;
    let gain = 0.55;
    for (let i = 0; i < 7; i++) {
      burst(ctx, out, at, 0.04, { type: 'bandpass', freq: 1800 + Math.random() * 1400, q: 3, gain });
      if (i < 2) burst(ctx, out, at + 0.03, 0.04, { type: 'bandpass', freq: 1500 + Math.random() * 1200, q: 3, gain: gain * 0.8 });
      at += gap;
      gap *= 0.72;
      gain *= 0.72;
    }
  },
  chest: (ctx, out, t) => {
    creak(ctx, out, t, 0.45, 0.18);
    PLAYERS.coins(ctx, out, t + 0.42);
  },
  coins: (ctx, out, t) => {
    for (let i = 0; i < 6; i++) {
      ping(ctx, out, t + i * 0.06 + Math.random() * 0.03, 2400 + Math.random() * 1800, 0.18, 0.12);
    }
  },
  trap: (ctx, out, t) => {
    burst(ctx, out, t, 0.12, { type: 'highpass', freq: 2500, gain: 0.35 });
    ping(ctx, out, t, 523, 0.7, 0.25, 'triangle');
    ping(ctx, out, t, 1347, 0.5, 0.12);
    ping(ctx, out, t + 0.01, 2210, 0.35, 0.06);
  },
  disarm: (ctx, out, t) => {
    burst(ctx, out, t, 0.03, { type: 'bandpass', freq: 3000, q: 4, gain: 0.4 });
    burst(ctx, out, t + 0.09, 0.03, { type: 'bandpass', freq: 2400, q: 4, gain: 0.3 });
  },
  teleport: (ctx, out, t) => {
    burst(ctx, out, t, 1.0, { type: 'bandpass', freq: 300, freqTo: 3200, q: 2, gain: 0.35, attack: 0.4 });
    ping(ctx, out, t + 0.7, 880, 0.6, 0.1);
    ping(ctx, out, t + 0.75, 1320, 0.5, 0.07);
  },
  // A squadmate's mark on the table: two soft bell notes.
  mark: (ctx, out, t) => {
    ping(ctx, out, t, 988, 0.45, 0.14);
    ping(ctx, out, t + 0.12, 1319, 0.5, 0.11);
  },
  // A say on the way on: a wooden knock.
  vote: (ctx, out, t) => {
    burst(ctx, out, t, 0.05, { type: 'bandpass', freq: 900, q: 3, gain: 0.45 });
  },
};

/** Plays a dungeon sound if this browser has sounds on. */
export const playDungeonSound = (sound: DungeonSound, delayMs = 0) => {
  const prefs = getClientPrefs();
  if (!prefs.soundEnabled || prefs.soundVolume <= 0) return;
  const now = Date.now();
  if (now - (lastPlayed[sound] ?? 0) < MIN_REPEAT_MS[sound]) return;
  lastPlayed[sound] = now;
  const ctx = getAudioContext();
  if (!ctx) return;
  const go = () => {
    try {
      const master = ctx.createGain();
      master.gain.value = prefs.soundVolume * 0.5;
      master.connect(ctx.destination);
      PLAYERS[sound](ctx, master, ctx.currentTime + 0.01 + delayMs / 1000);
    } catch {
      // Sound is a nicety; never let it break the board.
    }
  };
  if (ctx.state === 'suspended') void ctx.resume().then(go).catch(() => {});
  else go();
};
