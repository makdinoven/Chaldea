import axios from 'axios';
import { BASE_URL } from './api';
import type {
  CaravaneerView,
  EscortHireRequest,
  EscortJob,
  EscortJobWrap,
  EscortLeaveResponse,
  EscortMessage,
  EscortMessages,
} from '../types/caravanEscort';

/**
 * FEAT-212 — player caravan escorts (character-service, feature file 3.12 C1–C6).
 *
 * A 403 here is a game rule (no «Диалог с НПС» post, not wanted / reputation, not your character), not missing
 * rights — the caller shows the server's own text, so the global 403 toast is skipped.
 */

const CARAVANS = `${BASE_URL}/characters/caravans`;
const QUIET_403 = { skipForbiddenToast: true };

/** C1 — caravans preparing at the caravaneer's gate («есть места» / «мест нет» only). */
export const fetchCaravaneer = async (npcId: number, characterId: number): Promise<CaravaneerView> => {
  const { data } = await axios.get<CaravaneerView>(`${CARAVANS}/caravaneer/${npcId}`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

/** C2 — hire on as an escort; answers with the new job. */
export const hireEscort = async (caravanId: number, body: EscortHireRequest): Promise<EscortJob> => {
  const { data } = await axios.post<EscortJob>(`${CARAVANS}/${caravanId}/escort/hire`, body, QUIET_403);
  return data;
};

/** C3 — the character's own escort job (`null` when none). */
export const fetchEscortJob = async (characterId: number): Promise<EscortJob | null> => {
  const { data } = await axios.get<EscortJobWrap>(`${CARAVANS}/escort`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data?.escort ?? null;
};

/** C4 — «Сойти с каравана»: stays where the caravan is, no pay, no rejoin. */
export const leaveEscort = async (characterId: number): Promise<EscortLeaveResponse> => {
  const { data } = await axios.post<EscortLeaveResponse>(
    `${CARAVANS}/escort/leave`,
    { character_id: characterId },
    QUIET_403,
  );
  return data;
};

/** C5 — the caravan channel; `afterId = 0` → the latest 100, else the next 100 after it (oldest → newest). */
export const fetchEscortMessages = async (characterId: number, afterId = 0): Promise<EscortMessages> => {
  const { data } = await axios.get<EscortMessages>(`${CARAVANS}/escort/messages`, {
    params: { character_id: characterId, after_id: afterId },
    ...QUIET_403,
  });
  return data;
};

/** C6 — write to the caravan channel (1..500 chars, one message per 3 s). */
export const postEscortMessage = async (characterId: number, text: string): Promise<EscortMessage> => {
  const { data } = await axios.post<EscortMessage>(
    `${CARAVANS}/escort/messages`,
    { character_id: characterId, text },
    QUIET_403,
  );
  return data;
};
