import axios from 'axios';
import { apiErrorMessage } from './errors';
import type { StarterKitItem, StarterKitSkill, StarterKitResolvedFrom } from './starterKits';

/**
 * FEAT-154 — public per-character reads that feed the passport (rules 25-27).
 */

/**
 * The kit as recorded on the character.
 *
 * When it is a **snapshot** (`granted_kit_is_snapshot === true`) it is the
 * frozen record of what was actually issued at approval (rule 12d / D17) and
 * later admin edits never change it. When it is `false` the backend produced a
 * best-effort live re-resolve for a character created before this feature (D18)
 * — the UI may mark it as a reconstruction.
 *
 * Only ids, quantities and currency are frozen (D19); names, icons and rarity
 * are still resolved live through `fetchItemsBulk` / `fetchSkillsBulk`.
 */
export interface GrantedKit {
  class_id: number;
  origin_id: number;
  resolved_from: StarterKitResolvedFrom;
  items: StarterKitItem[];
  skills: StarterKitSkill[];
  currency_amount: number;
  /** Present only on a real snapshot. */
  granted_at?: string | null;
}

/** `GET /characters/{id}/public`. Also serves NPCs — see `is_npc` (note N13). */
export interface CharacterPublic {
  id: number;
  name: string;
  avatar: string | null;
  level: number | null;

  id_race: number | null;
  id_subrace: number | null;
  id_class: number | null;
  race_name: string | null;
  subrace_name: string | null;
  class_name: string | null;
  subrace_image: string | null;
  subrace_distinctive_features: string | null;

  sex: string | null;
  age: number | null;
  weight: string | null;
  height: string | null;

  appearance: string | null;
  biography: string | null;
  personality: string | null;
  background: string | null;

  origin_id: number | null;
  /** System registration date, set at approval. NULL for NPCs and old rows. */
  registered_at: string | null;
  skitaltsy_since_year: number | null;
  skitaltsy_since_segment: number | null;
  current_location_id: number | null;

  is_npc: boolean;
  user_id: number | null;
  username: string | null;

  granted_kit: GrantedKit | null;
  /** `true` = frozen record, `false` = live reconstruction (D18). */
  granted_kit_is_snapshot: boolean;

  /**
   * The ten base characteristics, read from character-attributes-service
   * (rule 27, N31). `null` when that service is unreachable — the passport
   * then simply renders without the stat block, it never fails.
   */
  stats: Record<string, number> | null;
}

/**
 * One row of `GET /characters/list`. The FEAT-154 keys are additive, so the
 * compact passport card renders with zero per-row requests (rule 26).
 */
export interface CharacterListItem {
  id: number;
  name: string;
  avatar: string | null;
  level: number;
  id_class: number;
  id_race: number;
  id_subrace: number;
  biography: string | null;
  personality: string | null;
  appearance: string | null;
  background: string | null;
  sex: string | null;
  age: number | null;
  is_npc: boolean;
  user_id: number | null;
  username: string | null;
  class_name: string | null;
  race_name: string | null;
  subrace_name: string | null;
  // FEAT-154 additive keys
  origin_id: number | null;
  registered_at: string | null;
  skitaltsy_since_year: number | null;
  skitaltsy_since_segment: number | null;
  height: string | null;
  weight: string | null;
  current_location_id: number | null;
  subrace_image: string | null;
}

export interface CharacterListResponse {
  items: CharacterListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CharacterListParams {
  q?: string;
  id_class?: number;
  id_race?: number;
  include_npcs?: boolean;
  page?: number;
  page_size?: number;
}

/** One character by id. **404** when it does not exist. */
export const fetchCharacterPublic = async (characterId: number): Promise<CharacterPublic> => {
  try {
    const { data } = await axios.get<CharacterPublic>(`/characters/${characterId}/public`);
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить персонажа.'));
  }
};

/** Paginated public list. */
export const fetchCharactersList = async (
  params: CharacterListParams = {},
): Promise<CharacterListResponse> => {
  try {
    const { data } = await axios.get<CharacterListResponse>('/characters/list', { params });
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить список персонажей.'));
  }
};

/** Megalink number derived from the character id (D11) — `СК-000501`. */
export const megalinkNumber = (characterId: number): string =>
  `СК-${String(characterId).padStart(6, '0')}`;
