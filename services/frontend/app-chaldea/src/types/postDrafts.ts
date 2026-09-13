/**
 * Type definitions for the RP post drafts feature (FEAT-156).
 *
 * All shapes mirror the API contract in section 3.3 of the feature file
 * exactly, including the `snake_case` field names the locations-service
 * actually returns — do not camelCase them. Timestamps are ISO-8601 strings
 * as serialised by FastAPI/Pydantic v1.
 */

/** Request body of D4 `PUT /locations/{location_id}/draft`. */
export interface PostDraftSave {
  character_id: number;
  content: string;
}

/** Full draft row — returned by D2, D3 and D4. */
export interface PostDraftRead {
  id: number;
  character_id: number;
  location_id: number;
  content: string;
  /** `sent_at IS NOT NULL` — the text became a real post. */
  is_sent: boolean;
  /** `active == 1` — the live draft of its (character, location) pair. */
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * History row — returned by D1. Deliberately carries no `content`;
 * the full text is fetched per item via D2.
 */
export interface PostDraftListItem {
  id: number;
  location_id: number;
  location_name: string | null;
  /** Plain text, first 180 chars, ellipsised server-side. */
  preview: string;
  /** Plain-text length of the stored content. */
  char_count: number;
  is_sent: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
