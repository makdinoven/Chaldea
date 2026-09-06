import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * FEAT-154 — character-request flow (character-service) plus the pre-character
 * avatar upload (photo-service).
 */

export type CharacterRequestStatus = 'pending' | 'approved' | 'rejected';
export type CharacterRequestType = 'creation' | 'claim';
export type CharacterSex = 'male' | 'female' | 'genderless';

/** Public class registry — replaces the old mock `INITIAL_CLASSES` (rule 12). */
export interface GameClass {
  id_class: number;
  name: string;
  description: string | null;
}

/**
 * Body of `POST /characters/requests/`.
 *
 * `avatar` is `Optional[str] = None` on the backend (D5) — an upload failure
 * must never block submission. The literal `avatar: 'string'` is gone for good.
 */
export interface CharacterRequestPayload {
  name: string;
  id_race: number;
  id_subrace: number;
  id_class: number;
  appearance: string;
  biography?: string | null;
  personality?: string | null;
  background?: string | null;
  sex?: string | null;
  age?: number | null;
  weight?: string | null;
  height?: string | null;
  user_id: number;
  avatar?: string | null;
  origin_id?: number | null;
  start_location_id?: number | null;
  /**
   * In-game year of «в Скитальцах с». ⚠️ Never hardcode a year anywhere —
   * the current one comes from `computed.year` of `GET /locations/game-time`.
   */
  skitaltsy_since_year?: number | null;
  /** Segment index 0..7 into `YEAR_SEGMENTS`. */
  skitaltsy_since_segment?: number | null;
}

/** Body of `PUT /characters/requests/{id}` — the same, without a required owner. */
export type CharacterRequestUpdatePayload = Omit<CharacterRequestPayload, 'user_id'> & {
  user_id?: number | null;
};

/** Response of `POST /characters/requests/`. */
export interface CharacterRequestCreated extends CharacterRequestUpdatePayload {
  id: number;
  status: CharacterRequestStatus;
  created_at: string | null;
  request_type: CharacterRequestType | null;
  character_id: number | null;
  rejection_reason: string | null;
}

/**
 * One row of `GET /characters/requests/my`, and the response of
 * `PUT /characters/requests/{id}`. Enriched with resolved reference names so
 * the «мои заявки» page renders with zero extra requests.
 */
export interface MyCharacterRequest {
  id: number;
  status: CharacterRequestStatus;
  request_type: CharacterRequestType | null;
  created_at: string | null;
  rejection_reason: string | null;

  name: string | null;
  id_race: number | null;
  id_subrace: number | null;
  id_class: number | null;
  race_name: string | null;
  subrace_name: string | null;
  class_name: string | null;

  avatar: string | null;
  origin_id: number | null;
  start_location_id: number | null;

  biography: string | null;
  personality: string | null;
  appearance: string | null;
  background: string | null;

  sex: string | null;
  age: number | null;
  weight: string | null;
  height: string | null;

  skitaltsy_since_year: number | null;
  skitaltsy_since_segment: number | null;
  character_id: number | null;
}

/** Response of `POST /characters/requests/{id}/approve`. */
export interface ApproveRequestResponse {
  message: string;
  current_location_id: number | null;
  /** Russian warning when the start-location fallback chain had to degrade. */
  location_warning: string | null;
}

export interface RejectRequestResponse {
  message: string;
}

/** Response of `POST /photo/upload_character_request_avatar`. */
export interface AvatarUploadResponse {
  avatar_url: string;
}

// ── Public ──────────────────────────────────────────────────────────────────

export const fetchClasses = async (): Promise<GameClass[]> => {
  try {
    const { data } = await axios.get<GameClass[]>('/characters/classes');
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить список классов.'));
  }
};

// ── Player (auth) ───────────────────────────────────────────────────────────

/**
 * Submits a creation request.
 * **403** `user_id` mismatch · **400** domain validation (Russian message)
 * · **422** schema · **500** DB.
 */
export const createCharacterRequest = async (
  payload: CharacterRequestPayload,
): Promise<CharacterRequestCreated> => {
  try {
    const { data } = await axios.post<CharacterRequestCreated>('/characters/requests/', payload);
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось отправить заявку. Попробуйте позже.'));
  }
};

/** The caller's own requests. Scoped by token — another user's id cannot be named. */
export const fetchMyCharacterRequests = async (): Promise<MyCharacterRequest[]> => {
  try {
    const { data } = await axios.get<MyCharacterRequest[]>('/characters/requests/my');
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить ваши заявки.'));
  }
};

/**
 * Edits and resubmits a **rejected** request (rule 30): status returns to
 * `pending` and `rejection_reason` is cleared.
 * **403** not the owner · **404** not found · **409** status is not `rejected`
 * · **400** domain validation.
 */
export const updateCharacterRequest = async (
  requestId: number,
  payload: CharacterRequestUpdatePayload,
): Promise<MyCharacterRequest> => {
  try {
    const { data } = await axios.put<MyCharacterRequest>(
      `/characters/requests/${requestId}`,
      payload,
    );
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось сохранить заявку. Попробуйте позже.'));
  }
};

/**
 * Uploads an avatar **before** the character exists (D4). Writes no DB row and
 * returns a permanent S3 URL that the request then carries.
 * **413** over 15 MB · **400** invalid image · **401**.
 */
export const uploadCharacterRequestAvatar = async (file: File): Promise<AvatarUploadResponse> => {
  const form = new FormData();
  form.append('file', file);
  try {
    const { data } = await axios.post<AvatarUploadResponse>(
      '/photo/upload_character_request_avatar',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return data;
  } catch (error) {
    throw new Error(
      apiErrorMessage(error, 'Не удалось загрузить аватар. Заявку можно отправить и без него.'),
    );
  }
};

// ── Moderation (`characters:approve`) ───────────────────────────────────────

export const approveCharacterRequest = async (
  requestId: number,
): Promise<ApproveRequestResponse> => {
  try {
    const { data } = await axios.post<ApproveRequestResponse>(
      `/characters/requests/${requestId}/approve`,
    );
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось одобрить заявку.'));
  }
};

/**
 * Rejects a request with an optional reason (rule 28). The player receives a
 * notification carrying it.
 * **409** when the request is not `pending` (rule 30a) · **400** when the reason
 * is longer than 1000 characters (rule 30b — a Russian 400, not a bare 422).
 */
export const rejectCharacterRequest = async (
  requestId: number,
  reason?: string | null,
): Promise<RejectRequestResponse> => {
  try {
    const { data } = await axios.post<RejectRequestResponse>(
      `/characters/requests/${requestId}/reject`,
      { reason: reason ?? null },
    );
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось отклонить заявку.'));
  }
};

/** Max length of a rejection reason accepted by the backend (rule 30b). */
export const MAX_REJECTION_REASON_LENGTH = 1000;

// ── Character limit ─────────────────────────────────────────────────────────

/**
 * Response of `GET /characters/my-character-count`.
 *
 * `limit` is `null` when the account has **no** character cap: the backend
 * setting `MAX_CHARACTERS_PER_USER` is unset by default. Never compare a count
 * against this field directly (`count >= null` is a type-coercion accident, not
 * an intent) — use {@link isCharacterLimitReached}.
 */
export interface MyCharacterCount {
  count: number;
  /** `null` — no limit configured. A positive number — the cap. */
  limit: number | null;
}

/** No limit configured: nothing is blocked until the backend says otherwise. */
export const NO_CHARACTER_LIMIT: MyCharacterCount = { count: 0, limit: null };

/** The caller's own character count and the cap that applies to them, if any. */
export const fetchMyCharacterCount = async (): Promise<MyCharacterCount> => {
  try {
    const { data } = await axios.get<MyCharacterCount>('/characters/my-character-count');
    return { count: data?.count ?? 0, limit: data?.limit ?? null };
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось проверить лимит персонажей.'));
  }
};

/** `true` only when a cap exists AND it is reached. No cap → never blocked. */
export const isCharacterLimitReached = ({ count, limit }: MyCharacterCount): boolean =>
  limit !== null && count >= limit;
