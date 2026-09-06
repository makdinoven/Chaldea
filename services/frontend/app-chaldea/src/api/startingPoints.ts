import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * FEAT-154 — curated starting locations (rules 18-20, locations-service).
 *
 * Only locations flagged `is_starting = 1` are ever published here; the full
 * 2260-location catalogue is deliberately not exposed to the wizard.
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
}

/** The whole curated list. May legitimately be empty until content is seeded. */
export const fetchStartingPoints = async (): Promise<StartingPoint[]> => {
  try {
    const { data } = await axios.get<StartingPoint[]>('/locations/starting-points');
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
