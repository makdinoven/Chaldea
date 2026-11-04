import axios from 'axios';

/**
 * FEAT-198 — player side of the law (character-service `law_api.py`):
 * wanted per region, the guard encounter, jail, escape and bail.
 * Players never get raw wanted numbers — only the level, fine and term.
 * Admin endpoints live in `lawAdmin.ts`.
 * Timestamps are naive UTC — read them with `parseServerDate`.
 */

export type LawChoice = 'fine' | 'surrender' | 'flee' | 'fight';

export type LawChoiceResult =
  | 'fined'
  | 'jailed'
  | 'fled'
  | 'fight'
  | 'flee_failed_blocked'
  | 'guard_gone';

export interface LawEncounterOut {
  id: number;
  region_id: number;
  region_name: string | null;
  location_id: number;
  guard_name: string | null;
  guard_avatar: string | null;
  /** «Вне закона»: only surrender / fight */
  is_outlaw: boolean;
  /** the region has a jail (otherwise no «сдаться») */
  has_jail: boolean;
  level_name: string | null;
  fine: number;
  jail_hours: number;
  options: LawChoice[];
  /** null when «бежать» is not offered */
  flee_chance_pct: number | null;
  /** pending | fighting | … */
  status: string;
  battle_id: number | null;
  /** auto-surrender time when the player never answers */
  expires_at: string;
}

export interface LawJailOut {
  id: number;
  region_id: number;
  region_name: string | null;
  location_id: number;
  location_name: string | null;
  until: string;
  bail_price: number;
  /** null = may try now */
  can_escape_at: string | null;
  escape_chance_pct: number;
  escape_attempts: number;
}

export interface LawWantedOut {
  region_id: number;
  region_name: string | null;
  level_code: string;
  level_name: string;
  fine: number;
  jail_hours: number;
  decaying: boolean;
}

export interface LawStateOut {
  wanted: LawWantedOut[];
  encounter: LawEncounterOut | null;
  jail: LawJailOut | null;
}

export interface LawChoiceOut {
  result: LawChoiceResult;
  message: string;
  battle_id: number | null;
  jail: LawJailOut | null;
  encounter: LawEncounterOut | null;
}

export interface LawEscapeOut {
  success: boolean;
  message: string;
  jail: LawJailOut | null;
}

export interface LawSelfBailOut {
  message: string;
  jail: LawJailOut | null;
}

export interface LawPrisonerOut {
  character_id: number;
  name: string;
  avatar: string | null;
  region_name: string | null;
  location_name: string | null;
  until: string;
  bail_price: number;
}

export interface LawPrisonersPage {
  items: LawPrisonerOut[];
  total: number;
}

export interface LawBailOut {
  message: string;
  paid: number;
}

/** Backend limits of the prisoner search. */
export const LAW_PRISONERS_PAGE_MAX = 50;
export const LAW_QUERY_MAX = 50;

/** Idempotency key of one click (the backend validates a UUID). */
export const newLawRequestId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // RFC 4122 v4 fallback for old browsers.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    const v = c === 'x' ? r : (r % 4) + 8;
    return v.toString(16);
  });
};

export const fetchLawState = async (characterId: number): Promise<LawStateOut> => {
  const { data } = await axios.get<LawStateOut>(`/characters/${characterId}/law`);
  return data;
};

export const fetchLawEncounter = async (characterId: number): Promise<LawEncounterOut | null> => {
  const { data } = await axios.get<{ encounter: LawEncounterOut | null }>(
    `/characters/${characterId}/law/encounter`,
  );
  return data.encounter;
};

export const chooseLawOption = async (
  characterId: number,
  encounterId: number,
  choice: LawChoice,
): Promise<LawChoiceOut> => {
  const { data } = await axios.post<LawChoiceOut>(
    `/characters/${characterId}/law/encounter/${encounterId}/choice`,
    { choice, request_id: newLawRequestId() },
  );
  return data;
};

export const fetchLawJail = async (characterId: number): Promise<LawJailOut | null> => {
  const { data } = await axios.get<{ jail: LawJailOut | null }>(`/characters/${characterId}/law/jail`);
  return data.jail;
};

export const escapeFromJail = async (characterId: number): Promise<LawEscapeOut> => {
  const { data } = await axios.post<LawEscapeOut>(`/characters/${characterId}/law/jail/escape`, {
    request_id: newLawRequestId(),
  });
  return data;
};

export const selfBail = async (characterId: number): Promise<LawSelfBailOut> => {
  const { data } = await axios.post<LawSelfBailOut>(`/characters/${characterId}/law/jail/bail`, {
    request_id: newLawRequestId(),
  });
  return data;
};

export const fetchPrisoners = async (
  q: string,
  page: number,
  pageSize: number,
): Promise<LawPrisonersPage> => {
  const params: Record<string, string | number> = {
    page,
    page_size: Math.min(pageSize, LAW_PRISONERS_PAGE_MAX),
  };
  const query = q.trim().slice(0, LAW_QUERY_MAX);
  if (query) params.q = query;
  const { data } = await axios.get<LawPrisonersPage>('/characters/law/prisoners', { params });
  return data;
};

export const payBail = async (
  payerCharacterId: number,
  bankerNpcId: number,
  prisonerCharacterId: number,
): Promise<LawBailOut> => {
  const { data } = await axios.post<LawBailOut>('/characters/law/bail', {
    payer_character_id: payerCharacterId,
    banker_npc_id: bankerNpcId,
    prisoner_character_id: prisonerCharacterId,
    request_id: newLawRequestId(),
  });
  return data;
};

/** «4 ч» / «3 д» / «7 д» — a jail term in hours as a short phrase. */
export const jailTermText = (hours: number): string => {
  if (hours >= 24 && hours % 24 === 0) return `${hours / 24} д`;
  if (hours > 24) return `${Math.floor(hours / 24)} д ${hours % 24} ч`;
  return `${hours} ч`;
};
