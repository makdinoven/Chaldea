import axios from 'axios';

/**
 * Country / region options for admin list filters (FEAT-209, shared since FEAT-210).
 * Public locations-service endpoints; used by `useGeoFilter` in `components/Admin/ExpandableList`.
 */

export interface GeoOption {
  id: number;
  name: string;
}

const byName = (a: GeoOption, b: GeoOption) => a.name.localeCompare(b.name, 'ru');

/** All countries (hidden included), sorted by name. */
export const fetchCountryOptions = async (): Promise<GeoOption[]> => {
  const { data } = await axios.get<GeoOption[]>('/locations/countries/lookup');
  return data.map((c) => ({ id: c.id, name: c.name })).sort(byName);
};

/** Regions of one country, sorted by name. 404 for an unknown country (caller handles). */
export const fetchCountryRegionOptions = async (countryId: number): Promise<GeoOption[]> => {
  const { data } = await axios.get<{ regions?: GeoOption[] }>(`/locations/countries/${countryId}/details`);
  return (data.regions ?? []).map((r) => ({ id: r.id, name: r.name })).sort(byName);
};
