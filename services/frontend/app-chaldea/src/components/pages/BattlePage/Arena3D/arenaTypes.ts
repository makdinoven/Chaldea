export type FighterSide = "ally" | "enemy";

export interface ArenaEffect {
  /** Stable per effect instance, so a newly applied one can be told apart. */
  key: string;
  label: string;
  detail: string;
  positive: boolean;
  duration: number;
}

export type FighterSelection = "target" | "ally" | null;

export interface ArenaFighter {
  participantId: number;
  name: string;
  avatar: string | null;
  side: FighterSide;
  hp: number;
  maxHp: number;
  mana: number;
  maxMana: number;
  energy: number;
  maxEnergy: number;
  effects: ArenaEffect[];
  isActing: boolean;
  isDead: boolean;
  isSelf: boolean;
  selection: FighterSelection;
  selectable: boolean;
}

export interface ArenaAim {
  from: number;
  to: number;
  kind: "attack" | "ally";
}

export interface ArenaSceneProps {
  fighters: ArenaFighter[];
  onSelect: (fighter: ArenaFighter) => void;
  aims: ArenaAim[];
  /** Absolute epoch ms when the current turn expires; null when unknown. */
  turnDeadline: number | null;
  turnPaused: boolean;
  /** Same-origin URL of the location art painted into the board, if any. */
  boardArtUrl: string | null;
  /** performance.now() of the latest critical hit; the dice of fate roll on each new value. */
  critRollAt: number | null;
  /** Completed turns of this battle; each one is notched into the table. */
  turnNumber: number;
}

// Mirrors battle-service TURN_TIMEOUT_HOURS (default 24) — only drives the rune-circle timer.
export const TURN_DURATION_MS = 24 * 60 * 60 * 1000;
