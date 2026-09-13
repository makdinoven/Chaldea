/**
 * REST client for the RP post drafts feature (FEAT-156), endpoints D1–D6.
 *
 * Mirrors the API contract in section 3.3 of the feature file. Auth is
 * supplied by the global axios request interceptor in `axiosSetup.ts` — no
 * explicit `Authorization` header is set here. Errors are propagated to
 * callers (the `usePostDraft` hook / `DraftsPanel`), which must surface a
 * Russian-language message to the user (see CLAUDE.md "Frontend Error
 * Display" mandate).
 */
import axios from 'axios';
import type {
  PostDraftListItem,
  PostDraftRead,
  PostDraftSave,
} from '../types/postDrafts';

/** D1 — history of the character's texts, ≤10, ordered `updated_at DESC`. */
export const listDrafts = async (
  characterId: number,
): Promise<PostDraftListItem[]> => {
  const { data } = await axios.get<PostDraftListItem[]>('/locations/drafts', {
    params: { character_id: characterId },
  });
  return data;
};

/** D2 — one draft by id, including its full `content`. */
export const getDraftById = async (
  draftId: number,
): Promise<PostDraftRead> => {
  const { data } = await axios.get<PostDraftRead>(
    `/locations/drafts/${draftId}`,
  );
  return data;
};

/** D3 — the live draft of (character, location); `null` when there is none. */
export const getActiveDraft = async (
  locationId: number,
  characterId: number,
): Promise<PostDraftRead | null> => {
  const { data } = await axios.get<PostDraftRead | null>(
    `/locations/${locationId}/draft`,
    { params: { character_id: characterId } },
  );
  return data ?? null;
};

/**
 * D4 — autosave upsert of the live draft. Returns `null` when the content
 * was empty and the server therefore deleted the row.
 */
export const saveDraft = async (
  locationId: number,
  body: PostDraftSave,
): Promise<PostDraftRead | null> => {
  const { data } = await axios.put<PostDraftRead | null>(
    `/locations/${locationId}/draft`,
    body,
  );
  return data ?? null;
};

/**
 * D5 — free the live draft slot of (character, location). Idempotent.
 *
 * @param keepInHistory `false` (default) — «Очистить черновик»: the row is
 *   hard-deleted, exactly as before. `true` — «Отмена»: the live slot is freed
 *   but the text is retired into the history (`active = NULL`, `sent_at` stays
 *   `NULL`), so the player can pull it back from the «Черновики» tab and the
 *   next post written in this location starts a fresh row instead of
 *   overwriting it (section 3.13).
 */
export const deleteActiveDraft = async (
  locationId: number,
  characterId: number,
  keepInHistory: boolean = false,
): Promise<void> => {
  await axios.delete(`/locations/${locationId}/draft`, {
    params: { character_id: characterId, keep_in_history: keepInHistory },
  });
};

/** D6 — delete one history row by id. */
export const deleteDraftById = async (draftId: number): Promise<void> => {
  await axios.delete(`/locations/drafts/${draftId}`);
};
