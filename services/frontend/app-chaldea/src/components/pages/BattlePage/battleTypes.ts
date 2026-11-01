import type { BattleRewards } from "../../../api/mobs";
import type { EffectLike } from "./battleEffects";
import type { SubclassPassive } from "../../../api/subclasses";

/** A participant's subclass in the battle snapshot (FEAT-188); name is null for a key unknown to the registry. */
export interface ParticipantSubclass {
  key: string;
  name: string | null;
}

/**
 * Subclass-passive fields of a battle snapshot entry (FEAT-188). Optional:
 * mobs, characters without a subclass and battles started before the feature
 * have them null / absent.
 */
export interface ParticipantPassiveFields {
  subclass?: ParticipantSubclass | null;
  passive?: SubclassPassive | null;
}

export interface ResourceEntry {
  current: number;
  max: number;
}

export interface ResourceBlock {
  health?: ResourceEntry;
  mana?: ResourceEntry;
  stamina?: ResourceEntry;
  energy?: ResourceEntry;
}

export interface ParticipantSnapshot extends ParticipantPassiveFields {
  participant_id: number;
  character_id: number;
  name: string;
  avatar: string | null;
  skills: unknown;
  attributes: Record<string, number>;
}

export interface RuntimeState {
  participants: Record<
    number,
    {
      hp: number;
      mana: number;
      stamina: number;
      energy: number;
      fast_slots: unknown;
      team: number;
      /** FEAT-190 — total passive shield; absent in older states. */
      shield?: number;
    }
  >;
  current_actor: number;
  next_actor: number;
  turn_number: number;
  turn_order: number[];
  total_turns: number;
  first_actor: number;
  deadline_at: string;
  is_paused?: boolean;
  paused_reason?: string | null;
  rewards?: BattleRewards | null;
  active_effects?: Record<number, EffectLike[]>;
  first_cycle?: boolean;
}

export interface CharacterData {
  character_id?: number;
  participant_id?: number;
  name?: string;
  avatar?: string | null;
  skills?: unknown;
  attributes?: Record<string, number>;
  items?: unknown;
  resources?: ResourceBlock[];
  title?: string;
  /** FEAT-188 — the subclass passive shown as a badge on the card. */
  passive?: SubclassPassive | null;
  /** FEAT-190 — total passive shield from the runtime (0 when none / old states). */
  shield?: number;
}

export interface TurnInfo {
  currentCharacterParticipant: {
    id: number;
    characterName: string;
  };
  turn_number: number;
  isOpponentTurn: boolean;
  endsAt: number;
}

export interface SkillSlot {
  id?: number;
  item_id?: number;
  [key: string]: unknown;
}

export interface TurnDataState {
  [key: string]: SkillSlot | null;
}

export interface BattleResultState {
  winner: string;
  isLose: boolean;
}

export interface ActionResponseData {
  ok: boolean;
  turn_number: number;
  next_actor: number;
  deadline_at: string;
  events: unknown[];
  battle_finished?: boolean;
  winner_team?: number;
  rewards?: BattleRewards;
}
