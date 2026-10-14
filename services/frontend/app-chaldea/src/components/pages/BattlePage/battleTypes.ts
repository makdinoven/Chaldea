import type { BattleRewards } from "../../../api/mobs";
import type { EffectLike } from "./battleEffects";

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

export interface ParticipantSnapshot {
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
