import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import { fetchCountryOptions, fetchCountryRegionOptions, type GeoOption } from '../../../api/adminGeo';
import { parsePositiveId, useSearchParamsPatch } from './urlParams';
import type { GeoFilterSelectsProps } from './GeoFilterSelects';

/**
 * FEAT-209/210 — «Страна → Регион» list filter in `?country=<id>&region=<id>` (replace, other params kept).
 *
 * Loads the country options once and the region options of the selected country, then validates
 * the URL: garbage / unknown / foreign ids are removed silently (a region without a country is
 * dropped too). Options that failed to load keep the URL value (Russian toast shown).
 *
 * - `countryId` / `regionId` — validated-to-parse values to send to the backend
 * - `settled` — URL values are validated: request the list only when true (no request for a value
 *   that is about to be reset)
 * - `selectProps` — spread into `<GeoFilterSelects {...selectProps} />`
 * - `onChanged` — called when the filter changes (user pick or silent reset): reset the page to 1
 */

const COUNTRY_PARAM = 'country';
const REGION_PARAM = 'region';
const LOAD_ERROR = 'Не удалось загрузить список стран/регионов';

interface RegionOptionsState {
  countryId: number;
  list: GeoOption[];
  /** Options failed to load — the URL value is kept as is (backend returns an empty set if foreign). */
  failed: boolean;
}

export const useGeoFilter = ({ onChanged }: { onChanged?: () => void } = {}) => {
  const [searchParams] = useSearchParams();
  const patch = useSearchParamsPatch();
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;

  const rawCountry = searchParams.get(COUNTRY_PARAM);
  const rawRegion = searchParams.get(REGION_PARAM);
  const parsedCountry = parsePositiveId(rawCountry);
  const parsedRegion = parsePositiveId(rawRegion);
  const countryId = parsedCountry;
  // A region without a country is meaningless — treat it as absent (and drop it below).
  const regionId = parsedCountry !== null ? parsedRegion : null;

  // Garbage params → removed silently
  useEffect(() => {
    const changes: Record<string, null> = {};
    if (rawCountry !== null && parsedCountry === null) changes[COUNTRY_PARAM] = null;
    if (rawRegion !== null && (parsedRegion === null || parsedCountry === null)) changes[REGION_PARAM] = null;
    if (Object.keys(changes).length > 0) patch(changes, true);
  }, [rawCountry, rawRegion, parsedCountry, parsedRegion, patch]);

  const setCountry = useCallback(
    (id: number | null) => patch({ [COUNTRY_PARAM]: id === null ? null : String(id), [REGION_PARAM]: null }, true),
    [patch],
  );
  const setRegion = useCallback(
    (id: number | null) => patch({ [REGION_PARAM]: id === null ? null : String(id) }, true),
    [patch],
  );

  const [countries, setCountries] = useState<GeoOption[] | null>(null);
  const [countriesFailed, setCountriesFailed] = useState(false);
  const [regionOptions, setRegionOptions] = useState<RegionOptionsState | null>(null);

  useEffect(() => {
    fetchCountryOptions()
      .then(setCountries)
      .catch(() => {
        toast.error(LOAD_ERROR);
        setCountriesFailed(true);
        setCountries([]);
      });
  }, []);

  useEffect(() => {
    if (countryId === null) {
      setRegionOptions(null);
      return;
    }
    let cancelled = false;
    fetchCountryRegionOptions(countryId)
      .then((list) => {
        if (!cancelled) setRegionOptions({ countryId, list, failed: false });
      })
      .catch((err) => {
        if (cancelled) return;
        if (axios.isAxiosError(err) && err.response?.status === 404) {
          // Unknown country in the URL — reset the filter silently
          setCountry(null);
          return;
        }
        toast.error(LOAD_ERROR);
        setRegionOptions({ countryId, list: [], failed: true });
      });
    return () => {
      cancelled = true;
    };
  }, [countryId, setCountry]);

  const countryValid =
    countryId === null || countriesFailed || (countries?.some((c) => c.id === countryId) ?? false);
  const regionsLoaded = countryId === null || regionOptions?.countryId === countryId;
  const regionValid =
    regionId === null ||
    (regionOptions?.countryId === countryId &&
      (regionOptions.failed || regionOptions.list.some((r) => r.id === regionId)));

  // Foreign / unknown ids in the URL → reset silently
  useEffect(() => {
    if (countries === null) return;
    if (!countryValid) {
      setCountry(null);
      onChangedRef.current?.();
      return;
    }
    if (regionsLoaded && !regionValid) {
      setRegion(null);
      onChangedRef.current?.();
    }
  }, [countries, countryValid, regionsLoaded, regionValid, setCountry, setRegion]);

  const settled = countries !== null && countryValid && regionsLoaded && regionValid;

  const selectProps: GeoFilterSelectsProps = {
    countryId,
    regionId,
    countries,
    regions: countryId !== null && regionOptions?.countryId === countryId ? regionOptions.list : null,
    onCountryChange: (id) => {
      setCountry(id);
      onChangedRef.current?.();
    },
    onRegionChange: (id) => {
      setRegion(id);
      onChangedRef.current?.();
    },
  };

  return { countryId, regionId, settled, selectProps, setCountry, setRegion };
};
