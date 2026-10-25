/*
  The magic seal's beat: the circle flares once a beat, and each resonating
  node pulses at its own offset from it — the true one exactly in time.
*/

/** How sharp a pulse is (a share of the beat either side of its peak). */
const PULSE_WIDTH = 0.07;

/** Where in its beat a node is now: 0..1, 0 at the flare. */
export const beatPhase = (now: number, beatMs: number, offset = 0) => {
  const p = (now / beatMs - offset) % 1;
  return p < 0 ? p + 1 : p;
};

/** How bright a pulse is at this phase: 1 at the peak, falling fast to 0. */
export const pulseAt = (phase: number) => {
  const d = Math.min(phase, 1 - phase);
  return Math.exp(-(d * d) / (2 * PULSE_WIDTH * PULSE_WIDTH));
};
