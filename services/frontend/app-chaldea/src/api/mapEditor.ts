import axios from 'axios';
import { BASE_URL } from './api';
import type { MarkerType } from './worldGraph';

/** Full editable state of a location, as returned by /locations/{id}/details. */
export interface LocationDetails {
  id: number;
  name: string;
  type: 'location' | 'subdistrict';
  parent_id: number | null;
  description: string;
  image_url: string | null;
  recommended_level: number;
  quick_travel_marker: boolean;
  no_quick_move: boolean;
  district_id: number | null;
  region_id: number | null;
  marker_type: MarkerType;
  map_icon_url: string | null;
  neighbors: Array<{ neighbor_id: number; energy_cost: number }>;
}

export interface LocationFormValues {
  name: string;
  description: string;
  recommended_level: number;
  marker_type: MarkerType;
  quick_travel_marker: boolean;
  no_quick_move: boolean;
  district_id: number | null;
  region_id: number | null;
}

export const fetchLocationDetails = async (locationId: number): Promise<LocationDetails> => {
  const { data } = await axios.get<LocationDetails>(`${BASE_URL}/locations/${locationId}/details`);
  return data;
};

/**
 * The backend applies PATCH semantics (exclude_unset), so only the keys sent
 * here are written. A location must stay attached to either a district or a
 * region, so both are always sent together.
 */
export const updateLocation = async (
  locationId: number,
  values: LocationFormValues,
): Promise<void> => {
  await axios.put(`${BASE_URL}/locations/${locationId}/update`, values);
};

export const uploadLocationImage = async (locationId: number, file: File): Promise<string> => {
  const form = new FormData();
  form.append('file', file);
  form.append('location_id', String(locationId));
  const { data } = await axios.post<{ image_url: string }>(
    `${BASE_URL}/photo/change_location_image`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data.image_url;
};

/**
 * Creates a link in both directions. Also acts as an upsert on the backend,
 * but prefer `updateNeighborCost` for existing links — this call clears any
 * drawn waypoints when path_data is omitted.
 */
export const createNeighbor = async (
  fromId: number,
  toId: number,
  energyCost = 1,
): Promise<void> => {
  await axios.post(`${BASE_URL}/locations/${fromId}/neighbors/`, {
    neighbor_id: toId,
    energy_cost: energyCost,
  });
};

/** Changes only the stamina cost, preserving path_data on both rows. */
export const updateNeighborCost = async (
  fromId: number,
  toId: number,
  energyCost: number,
): Promise<void> => {
  await axios.patch(`${BASE_URL}/locations/neighbors/${fromId}/${toId}/cost`, {
    energy_cost: energyCost,
  });
};

export const deleteNeighbor = async (fromId: number, toId: number): Promise<void> => {
  await axios.delete(`${BASE_URL}/locations/${fromId}/neighbors/${toId}`);
};

/** Turns an axios failure into a message that can be shown to the user. */
export const editorErrorMessage = (error: unknown, fallback: string): string => {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 403) return 'Недостаточно прав для этого действия.';
    if (error.response?.status === 401) return 'Сессия истекла — войдите заново.';
    if (error.response?.status === 404) return 'Объект не найден — возможно, он уже удалён.';
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
    if (!error.response) return 'Нет связи с сервером.';
  }
  return fallback;
};
