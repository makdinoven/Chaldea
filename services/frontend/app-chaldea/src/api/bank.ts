import axios from 'axios';
import { BASE_URL } from './api';
import type {
  BankActionResult,
  BankDepositRequest,
  BankLoanRequest,
  BankRegion,
  BankRepayRequest,
  BankSendRequest,
  BankSummary,
  BankTransferRequest,
  BankView,
  BankWithdrawRequest,
} from '../types/bank';

/**
 * FEAT-184 — player bank API (character-service, contract 3.9).
 *
 * A 403 here is a game rule (no «Диалог с НПС» post, not your character), not missing
 * rights: the caller toasts the server's own text, so the global 403 toast is skipped.
 */

const BANK = `${BASE_URL}/characters/economy/bank`;
const QUIET_403 = { skipForbiddenToast: true };

const npcPath = (npcId: number) => `${BANK}/npc/${npcId}`;

export const getBankView = async (npcId: number, characterId: number): Promise<BankView> => {
  const { data } = await axios.get<BankView>(npcPath(npcId), {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

const post = async <B>(npcId: number, action: string, body: B): Promise<BankActionResult> => {
  const { data } = await axios.post<BankActionResult>(`${npcPath(npcId)}/${action}`, body, QUIET_403);
  return data;
};

export const bankDeposit = (npcId: number, body: BankDepositRequest) => post(npcId, 'deposit', body);
export const bankWithdraw = (npcId: number, body: BankWithdrawRequest) => post(npcId, 'withdraw', body);
export const bankTransfer = (npcId: number, body: BankTransferRequest) => post(npcId, 'transfer', body);
export const bankSend = (npcId: number, body: BankSendRequest) => post(npcId, 'send', body);
export const bankLoan = (npcId: number, body: BankLoanRequest) => post(npcId, 'loan', body);
export const bankRepay = (npcId: number, body: BankRepayRequest) => post(npcId, 'repay', body);

/** All own deposits and the loan, any bank (profile summary). */
export const getBankSummary = async (characterId: number): Promise<BankSummary> => {
  const { data } = await axios.get<BankSummary>(`${BANK}/summary`, {
    params: { character_id: characterId },
    ...QUIET_403,
  });
  return data;
};

/** Enabled banks — transfer destinations (public). */
export const getBankRegions = async (): Promise<BankRegion[]> => {
  const { data } = await axios.get<BankRegion[]>(`${BANK}/regions`);
  return data;
};
