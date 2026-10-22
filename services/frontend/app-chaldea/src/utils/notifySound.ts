import { getClientPrefs } from './clientPrefs';
import { getCustomSoundBuffer, loadCustomSounds, MAX_SOUND_SECONDS } from './customSounds';

/*
  The site's few sounds, synthesised on the spot with the Web Audio API —
  no files to load. Kept short and quiet: a soft pluck for a message, a small
  bell for a notification, a low drum and horn for a battle starting. A sound
  the player uploaded for a kind (customSounds) plays instead.
*/

export type SoundKind = 'message' | 'notification' | 'battle';

/** The same sound twice in quick succession (a burst of events) plays once. */
const MIN_REPEAT_MS = 400;

let context: AudioContext | null = null;
const lastPlayed: Partial<Record<SoundKind, number>> = {};

const getContext = (): AudioContext | null => {
  if (context) return context;
  const Ctor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  try {
    context = new Ctor();
  } catch {
    return null;
  }
  return context;
};

// Browsers keep audio locked until the player has interacted with the page:
// open the context on the first click or key press so later sounds can play.
if (typeof window !== 'undefined') {
  const unlock = () => {
    const ctx = getContext();
    if (ctx && ctx.state === 'suspended') void ctx.resume().catch(() => {});
    window.removeEventListener('pointerdown', unlock);
    window.removeEventListener('keydown', unlock);
  };
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);
}

interface Tone {
  freq: number;
  /** Seconds after the sound starts. */
  at: number;
  duration: number;
  type?: OscillatorType;
  gain?: number;
  /** Frequency the tone glides to over its duration. */
  glideTo?: number;
}

const SOUNDS: Record<SoundKind, Tone[]> = {
  message: [
    { freq: 880, at: 0, duration: 0.18, type: 'sine', gain: 0.6 },
    { freq: 1318.5, at: 0.09, duration: 0.28, type: 'sine', gain: 0.5 },
  ],
  notification: [
    { freq: 1046.5, at: 0, duration: 0.9, type: 'sine', gain: 0.5 },
    { freq: 2093, at: 0, duration: 0.5, type: 'sine', gain: 0.15 },
    { freq: 1568, at: 0.12, duration: 0.8, type: 'sine', gain: 0.35 },
  ],
  battle: [
    { freq: 110, at: 0, duration: 0.35, type: 'sine', gain: 0.9, glideTo: 55 },
    { freq: 220, at: 0.18, duration: 0.45, type: 'triangle', gain: 0.35 },
    { freq: 330, at: 0.38, duration: 0.6, type: 'triangle', gain: 0.3 },
  ],
};

const playTones = (ctx: AudioContext, tones: Tone[], volume: number) => {
  const master = ctx.createGain();
  master.gain.value = volume * 0.35;
  master.connect(ctx.destination);
  const start = ctx.currentTime + 0.01;
  for (const tone of tones) {
    const osc = ctx.createOscillator();
    const env = ctx.createGain();
    const t0 = start + tone.at;
    const t1 = t0 + tone.duration;
    osc.type = tone.type ?? 'sine';
    osc.frequency.setValueAtTime(tone.freq, t0);
    if (tone.glideTo) osc.frequency.exponentialRampToValueAtTime(tone.glideTo, t1);
    // A quick attack and an exponential fade, like a struck string or bell.
    env.gain.setValueAtTime(0.0001, t0);
    env.gain.exponentialRampToValueAtTime(tone.gain ?? 0.5, t0 + 0.015);
    env.gain.exponentialRampToValueAtTime(0.0001, t1);
    osc.connect(env).connect(master);
    osc.start(t0);
    osc.stop(t1 + 0.05);
  }
};

/** Fade at the end of a cut-off custom sound, seconds. */
const CUSTOM_FADE_SECONDS = 0.3;

const playBuffer = (ctx: AudioContext, buffer: AudioBuffer, volume: number) => {
  const source = ctx.createBufferSource();
  const gain = ctx.createGain();
  source.buffer = buffer;
  const start = ctx.currentTime + 0.01;
  const length = Math.min(buffer.duration, MAX_SOUND_SECONDS);
  gain.gain.setValueAtTime(volume, start);
  if (buffer.duration > MAX_SOUND_SECONDS) {
    // Longer files are cut, fading out rather than stopping mid-note.
    gain.gain.setValueAtTime(volume, start + length - CUSTOM_FADE_SECONDS);
    gain.gain.linearRampToValueAtTime(0, start + length);
  }
  source.connect(gain).connect(ctx.destination);
  source.start(start, 0, length);
};

/** Plays a sound if this browser has sounds on. `force` previews it from the settings regardless. */
export const playSound = (kind: SoundKind, options: { force?: boolean; volume?: number } = {}) => {
  const prefs = getClientPrefs();
  if (!options.force && !prefs.soundEnabled) return;
  const volume = options.volume ?? prefs.soundVolume;
  if (volume <= 0) return;
  const now = Date.now();
  if (!options.force && now - (lastPlayed[kind] ?? 0) < MIN_REPEAT_MS) return;
  lastPlayed[kind] = now;

  const ctx = getContext();
  if (!ctx) return;
  const go = () => {
    try {
      const custom = getCustomSoundBuffer(kind);
      if (custom) playBuffer(ctx, custom, volume);
      else playTones(ctx, SOUNDS[kind], volume);
    } catch {
      // Sound is a nicety; never let it break event handling.
    }
  };
  const ready = ctx.state === 'suspended' ? ctx.resume() : Promise.resolve();
  void Promise.all([ready, loadCustomSounds()]).then(go).catch(() => {});
};
