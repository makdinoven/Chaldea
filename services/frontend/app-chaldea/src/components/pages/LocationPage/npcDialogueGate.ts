import axios from 'axios';

/**
 * FEAT-212 — NPC windows behind the FEAT-145 «Диалог с НПС» post (caravaneer, guild window).
 * The backend answers 403 «Нужен пост-намерение «Диалог с НПС» с этим персонажем» when no such post is open;
 * the modal shows that text and this hint on how to open the gate.
 */

export const NPC_DIALOGUE_HINT_CARAVANEER =
  'Напишите в локации пост с намерением «Диалог с НПС», указав караванщика, и откройте окно снова.';

export const NPC_DIALOGUE_HINT_GUILD =
  'Напишите в локации пост с намерением «Диалог с НПС», указав гильдию торговцев, и откройте окно снова.';

const HTTP_FORBIDDEN = 403;
const GATE_MARKER = 'Диалог с НПС';

/** True when the failure is the closed «Диалог с НПС» gate (not a reputation tier or ownership 403). */
export const isNpcDialogueGateError = (err: unknown): boolean => {
  if (!axios.isAxiosError(err) || err.response?.status !== HTTP_FORBIDDEN) return false;
  const detail: unknown = err.response.data?.detail;
  return typeof detail === 'string' && detail.includes(GATE_MARKER);
};
