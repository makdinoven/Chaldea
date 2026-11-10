import type { GeoOption } from '../../../api/adminGeo';

/**
 * FEAT-209/210 — the two «Страна» / «Регион» selects of a list filter row (a fragment, so they
 * flow in the parent's flex row). Feed it `useGeoFilter().selectProps`. Region is disabled
 * until a country is chosen; a URL value without a loaded option stays visible as «Страна #id».
 */
export interface GeoFilterSelectsProps {
  countryId: number | null;
  regionId: number | null;
  /** null while loading */
  countries: GeoOption[] | null;
  /** Regions of `countryId` (null while loading / no country) */
  regions: GeoOption[] | null;
  onCountryChange: (id: number | null) => void;
  onRegionChange: (id: number | null) => void;
  /** Width classes of each select (default `sm:max-w-[200px]`) */
  className?: string;
}

const OPTION_CLASS = 'bg-site-dark text-white';

const GeoFilterSelects = ({
  countryId,
  regionId,
  countries,
  regions,
  onCountryChange,
  onRegionChange,
  className = 'sm:max-w-[200px]',
}: GeoFilterSelectsProps) => (
  <>
    <select
      className={`input-underline ${className}`}
      aria-label="Страна"
      value={countryId ?? ''}
      onChange={(e) => onCountryChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="" className={OPTION_CLASS}>Все страны</option>
      {/* Keep a URL value visible while the options load / failed to load */}
      {countryId !== null && !(countries ?? []).some((c) => c.id === countryId) && (
        <option value={countryId} className={OPTION_CLASS}>Страна #{countryId}</option>
      )}
      {(countries ?? []).map((c) => (
        <option key={c.id} value={c.id} className={OPTION_CLASS}>
          {c.name}
        </option>
      ))}
    </select>
    <select
      className={`input-underline ${className} disabled:opacity-50 disabled:cursor-not-allowed`}
      aria-label="Регион"
      disabled={countryId === null}
      title={countryId === null ? 'Сначала выберите страну' : undefined}
      value={regionId ?? ''}
      onChange={(e) => onRegionChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="" className={OPTION_CLASS}>Все регионы</option>
      {regionId !== null && !(regions ?? []).some((r) => r.id === regionId) && (
        <option value={regionId} className={OPTION_CLASS}>Регион #{regionId}</option>
      )}
      {(regions ?? []).map((r) => (
        <option key={r.id} value={r.id} className={OPTION_CLASS}>
          {r.name}
        </option>
      ))}
    </select>
  </>
);

export default GeoFilterSelects;
