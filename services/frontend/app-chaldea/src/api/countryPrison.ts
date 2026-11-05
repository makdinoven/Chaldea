import axios from 'axios';

/**
 * FEAT-202 — the country prison (тюрьма страны) in the locations admin.
 * `GET /locations/countries/{id}/districts` needs `locations:update`; the prison itself is saved
 * through the regular country update (`prison_district_id`, `null` clears it).
 */
export interface CountryDistrict {
  id: number;
  name: string;
  region_id: number;
  region_name: string;
  parent_district_id: number | null;
  /** Locations in the district subtree (sub-districts and nested locations included). */
  location_count: number;
  entrance_location_id: number | null;
}

/** Every district of every region of the country, ordered by region, parent first. */
export const fetchCountryDistricts = async (countryId: number): Promise<CountryDistrict[]> => {
  const { data } = await axios.get<CountryDistrict[]>(`/locations/countries/${countryId}/districts`);
  return data;
};
