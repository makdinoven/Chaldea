import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * FEAT-154 — curated starting locations (rules 18-20, locations-service).
 *
 * Only locations flagged `is_starting = 1` are ever published here; the full
 * 2287-location catalogue is deliberately not exposed to the wizard.
 *
 * ⚠️ Note N6: `is_starting` / `starting_blurb` are accepted in location
 * create/update bodies and returned by `GET /locations/{id}/details`, but they
 * are NOT part of the generic location response schemas. An admin form must
 * read the current values from `/details`.
 */
export interface StartingPoint {
  id: number;
  name: string;
  image_url: string | null;
  starting_blurb: string | null;
  district_name: string | null;
  region_name: string | null;
  country_name: string | null;
  sort_order: number;
  /**
   * FEAT-155 — the point is recommended for the origin passed as `?origin_id=`.
   * A hint, never a filter (rule 2): the list stays complete either way, and
   * without `origin_id` this is always `false`.
   */
  is_recommended: boolean;
}

/**
 * The whole curated list. May legitimately be empty until content is seeded.
 *
 * With `originId` the list is still complete — recommended points simply come
 * first, in the order an administrator curated (rule 3).
 */
export const fetchStartingPoints = async (
  originId?: number | null,
): Promise<StartingPoint[]> => {
  try {
    const { data } = await axios.get<StartingPoint[]>('/locations/starting-points', {
      params: originId ? { origin_id: originId } : undefined,
    });
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить список стартовых точек.'));
  }
};

/**
 * One starting point. Answers **404** both when the location does not exist and
 * when it exists but is not flagged as a starting point.
 */
export const fetchStartingPoint = async (locationId: number): Promise<StartingPoint> => {
  try {
    const { data } = await axios.get<StartingPoint>(`/locations/starting-points/${locationId}`);
    return data;
  } catch (error) {
    throw new Error(
      apiErrorMessage(error, 'Выбранная точка не входит в список стартовых.'),
    );
  }
};

// ── FEAT-155 — admin: recommended starting points of one origin ─────────────

/**
 * One hit of `GET /locations/admin/location-search`.
 *
 * The breadcrumbs are not decoration (rule 6): the catalogue holds a dozen
 * locations literally named «Ворота», and without «район · регион · страна»
 * the admin cannot tell which one he is about to attach.
 */
export interface LocationSearchResult {
  id: number;
  name: string;
  image_url: string | null;
  district_name: string | null;
  region_name: string | null;
  country_name: string | null;
  /** Already a starting point. If `false`, attaching it makes it one (rule 7). */
  is_starting: boolean;
}

/** Search a location by name without walking the five-level tree (rule 6). */
export const searchLocations = async (
  query: string,
  limit = 20,
): Promise<LocationSearchResult[]> => {
  try {
    const { data } = await axios.get<LocationSearchResult[]>(
      '/locations/admin/location-search',
      { params: { q: query, limit } },
    );
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось выполнить поиск локаций.'));
  }
};

/** The recommended set of one origin, in the curated order (`origins:read`). */
export const fetchOriginStartingPoints = async (
  originId: number,
): Promise<StartingPoint[]> => {
  try {
    const { data } = await axios.get<StartingPoint[]>(
      `/locations/admin/origins/${originId}/starting-points`,
    );
    return data ?? [];
  } catch (error) {
    throw new Error(
      apiErrorMessage(error, 'Не удалось загрузить рекомендованные точки происхождения.'),
    );
  }
};

/**
 * Replaces the whole set; **the array order becomes the set's order**, and the
 * first element is what the wizard presents as the character's homeland
 * (rule 13). This is what the reorder controls call.
 */
export const setOriginStartingPoints = async (
  originId: number,
  locationIds: number[],
): Promise<StartingPoint[]> => {
  try {
    const { data } = await axios.put<StartingPoint[]>(
      `/locations/admin/origins/${originId}/starting-points`,
      { location_ids: locationIds },
    );
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось сохранить порядок точек.'));
  }
};

/** Appends one point. Idempotent, and promotes the location to starting (rule 7). */
export const addOriginStartingPoint = async (
  originId: number,
  locationId: number,
): Promise<StartingPoint[]> => {
  try {
    const { data } = await axios.post<StartingPoint[]>(
      `/locations/admin/origins/${originId}/starting-points/${locationId}`,
    );
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось добавить точку в набор.'));
  }
};

/** Removes one link. The location keeps its `is_starting` flag (rule 8). */
export const removeOriginStartingPoint = async (
  originId: number,
  locationId: number,
): Promise<StartingPoint[]> => {
  try {
    const { data } = await axios.delete<StartingPoint[]>(
      `/locations/admin/origins/${originId}/starting-points/${locationId}`,
    );
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось убрать точку из набора.'));
  }
};
