import axios from 'axios';
import { BASE_URL } from './api';
import type {
  CustomsInspectRequest,
  CustomsInspectResponse,
  CustomsJob,
  CustomsJobWrap,
  CustomsOfficerView,
  CustomsResignResponse,
} from '../types/customs';

/**
 * FEAT-216 — customs officer job and caravan inspection (character-service, feature file 3.7 C1–C5).
 *
 * A 403 here is a game rule (no «Диалог с НПС» post, wanted, reputation, not your character), not missing rights —
 * the caller shows the server's own text, so the global 403 toast is skipped.
 */

const CHARACTERS = `${BASE_URL}/characters`;
const QUIET_403 = { skipForbiddenToast: true };

/** C1 — the «Таможенник» window: the post's country, the character's own service, whether he may enlist. */
export const fetchCustomsOfficer = async (npcId: number, characterId: number): Promise<CustomsOfficerView> => {
  const { data } = await axios.get<CustomsOfficerView>(`${CHARACTERS}/customs/officer/${npcId}`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

/** C2 — enlist as a customs officer of the post's country. */
export const enlistCustoms = async (npcId: number, characterId: number): Promise<CustomsJob | null> => {
  const { data } = await axios.post<CustomsJobWrap>(
    `${CHARACTERS}/customs/officer/${npcId}/enlist`,
    { character_id: characterId },
    QUIET_403,
  );
  return data?.job ?? null;
};

/** C3 — leave the customs service. */
export const resignCustoms = async (characterId: number): Promise<CustomsResignResponse> => {
  const { data } = await axios.post<CustomsResignResponse>(
    `${CHARACTERS}/customs/resign`,
    { character_id: characterId },
    QUIET_403,
  );
  return data;
};

/** C4 — the character's own customs service (`null` when none). */
export const fetchCustomsJob = async (characterId: number): Promise<CustomsJob | null> => {
  const { data } = await axios.get<CustomsJobWrap>(`${CHARACTERS}/customs/job`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data?.job ?? null;
};

/** C5 — «Досмотреть» the caravan the officer was alerted about (solo or with the squad); answers with the battle. */
export const inspectCaravan = async (
  caravanId: number,
  body: CustomsInspectRequest,
): Promise<CustomsInspectResponse> => {
  const { data } = await axios.post<CustomsInspectResponse>(
    `${CHARACTERS}/caravans/${caravanId}/inspect`,
    body,
    QUIET_403,
  );
  return data;
};
