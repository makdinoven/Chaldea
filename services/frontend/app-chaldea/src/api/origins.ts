import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * FEAT-154 — origin registry (`origin_countries`, owned by locations-service).
 *
 * The list is deliberately WIDER than the playable `Countries` (rule 9) and
 * never exposes `Countries.description` (rule 4) — it carries its own `summary`
 * and `skitaltsy_attitude`.
 */

/** Public card of one origin (`GET /locations/origins`). */
export interface OriginCountry {
  id: number;
  name: string;
  emblem_url: string | null;
  map_image_url: string | null;
  summary: string | null;
  skitaltsy_attitude: string | null;
  archive_slug: string | null;
  country_id: number | null;
  is_playable: boolean;
  sort_order: number;
}

/**
 * Admin card — the public fields plus the soft-delete flag.
 *
 * ⚠️ Note N5: `GET /locations/admin/origins` **includes soft-deleted rows by
 * default** (`include_inactive=true`), otherwise a hidden origin could never be
 * found and restored. The public `GET /locations/origins` excludes them.
 * There is no dedicated restore endpoint — restoring is `PUT { is_active: true }`.
 */
export interface OriginCountryAdmin extends OriginCountry {
  is_active: boolean;
}

/** Body of `POST /locations/admin/origins`. */
export interface OriginCountryCreatePayload {
  name: string;
  emblem_url?: string | null;
  map_image_url?: string | null;
  summary?: string | null;
  skitaltsy_attitude?: string | null;
  /** Must match `^[a-z0-9-]+$` — validated server-side. */
  archive_slug?: string | null;
  country_id?: number | null;
  is_playable?: boolean;
  is_active?: boolean;
  sort_order?: number;
}

/** Body of `PUT /locations/admin/origins/{id}` — every field optional. */
export type OriginCountryUpdatePayload = Partial<OriginCountryCreatePayload>;

/** Response of the soft `DELETE /locations/admin/origins/{id}`. */
export interface OriginDeleteResponse {
  id: number;
  is_active: boolean;
}

// ── Public ──────────────────────────────────────────────────────────────────

/** Active origins only. Used by the wizard's «Родина» step and admin pickers. */
export const fetchOrigins = async (): Promise<OriginCountry[]> => {
  try {
    const { data } = await axios.get<OriginCountry[]>('/locations/origins');
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить список происхождений.'));
  }
};

// ── Admin (`origins:*` permissions) ─────────────────────────────────────────

/** Admin listing. `includeInactive` defaults to `true` on the backend (N5). */
export const fetchOriginsAdmin = async (includeInactive = true): Promise<OriginCountryAdmin[]> => {
  try {
    const { data } = await axios.get<OriginCountryAdmin[]>('/locations/admin/origins', {
      params: { include_inactive: includeInactive },
    });
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить справочник происхождений.'));
  }
};

export const createOrigin = async (
  payload: OriginCountryCreatePayload,
): Promise<OriginCountryAdmin> => {
  try {
    const { data } = await axios.post<OriginCountryAdmin>('/locations/admin/origins', payload);
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось создать происхождение.'));
  }
};

export const updateOrigin = async (
  originId: number,
  payload: OriginCountryUpdatePayload,
): Promise<OriginCountryAdmin> => {
  try {
    const { data } = await axios.put<OriginCountryAdmin>(
      `/locations/admin/origins/${originId}`,
      payload,
    );
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось обновить происхождение.'));
  }
};

/** Soft delete — the row is hidden (`is_active = 0`), never erased. */
export const deleteOrigin = async (originId: number): Promise<OriginDeleteResponse> => {
  try {
    const { data } = await axios.delete<OriginDeleteResponse>(
      `/locations/admin/origins/${originId}`,
    );
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось скрыть происхождение.'));
  }
};

/** Restore a soft-deleted origin. There is no dedicated endpoint (N5). */
export const restoreOrigin = (originId: number): Promise<OriginCountryAdmin> =>
  updateOrigin(originId, { is_active: true });
