import { useEffect, useMemo, useRef, useState } from 'react';
import type { WorldGraph } from '../../api/worldGraph';
import { COUNTRY_COLORS, MARKER_COLORS } from './theme';

export type SearchKind = 'location' | 'district' | 'region' | 'country';

export interface SearchHit {
  kind: SearchKind;
  id: number;
  name: string;
  context: string;
  color: string;
}

interface MapSearchProps {
  graph: WorldGraph;
  countryIndexOf: (countryId: number) => number;
  onSelect: (hit: SearchHit) => void;
}

const KIND_LABEL: Record<SearchKind, string> = {
  location: 'Локация',
  district: 'Район',
  region: 'Регион',
  country: 'Страна',
};

/** Kind order decides ranking when scores tie — big things first. */
const KIND_WEIGHT: Record<SearchKind, number> = {
  country: 0,
  region: 1,
  district: 2,
  location: 3,
};

const MAX_HITS = 30;

const MapSearch = ({ graph, countryIndexOf, onSelect }: MapSearchProps) => {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const index = useMemo<SearchHit[]>(() => {
    const regionName = new Map(graph.regions.map((r) => [r.id, r.name]));
    const countryName = new Map(graph.countries.map((c) => [c.id, c.name]));
    const regionCountry = new Map(graph.regions.map((r) => [r.id, r.country_id]));
    const districtName = new Map(graph.districts.map((d) => [d.id, d.name]));

    const hits: SearchHit[] = [];

    graph.countries.forEach((country) => {
      hits.push({
        kind: 'country',
        id: country.id,
        name: country.name,
        context: 'Страна',
        color: COUNTRY_COLORS[countryIndexOf(country.id) % COUNTRY_COLORS.length],
      });
    });

    graph.regions.forEach((region) => {
      hits.push({
        kind: 'region',
        id: region.id,
        name: region.name,
        context: countryName.get(region.country_id) ?? 'Регион',
        color: COUNTRY_COLORS[countryIndexOf(region.country_id) % COUNTRY_COLORS.length],
      });
    });

    graph.districts.forEach((district) => {
      const countryId = regionCountry.get(district.region_id);
      hits.push({
        kind: 'district',
        id: district.id,
        name: district.name,
        context: regionName.get(district.region_id) ?? 'Район',
        color: countryId === undefined
          ? '#7f8ea3'
          : COUNTRY_COLORS[countryIndexOf(countryId) % COUNTRY_COLORS.length],
      });
    });

    graph.locations.forEach((location) => {
      const district = location.district_id ? districtName.get(location.district_id) : null;
      hits.push({
        kind: 'location',
        id: location.id,
        name: location.name,
        context: district
          ? `${regionName.get(location.region_id) ?? '—'} · ${district}`
          : regionName.get(location.region_id) ?? '—',
        color: MARKER_COLORS[location.marker_type] ?? MARKER_COLORS.safe,
      });
    });

    return hits;
  }, [graph, countryIndexOf]);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle.length < 2) return [];
    const scored: Array<{ hit: SearchHit; score: number }> = [];
    for (const hit of index) {
      const name = hit.name.toLowerCase();
      const position = name.indexOf(needle);
      if (position === -1) continue;
      // Prefix matches beat mid-word ones; bigger entities break the tie.
      scored.push({ hit, score: position * 10 + KIND_WEIGHT[hit.kind] });
    }
    scored.sort((a, b) => a.score - b.score || a.hit.name.localeCompare(b.hit.name));
    return scored.slice(0, MAX_HITS).map((entry) => entry.hit);
  }, [index, query]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  const commit = (hit: SearchHit) => {
    onSelect(hit);
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlight((h) => Math.min(h + 1, results.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const hit = results[highlight];
      if (hit) commit(hit);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={containerRef} className="relative w-full">
      <div className="flex items-center gap-2 rounded-card border border-gold-dark/35 bg-[#0d0e15]/95 px-3 py-2">
        <span className="text-[13px] text-white/35" aria-hidden>⌕</span>
        <input
          type="text"
          className="min-w-0 flex-1 bg-transparent text-[13px] text-white placeholder-white/35 outline-none"
          placeholder="Поиск: локация, район, регион, страна…"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setHighlight(0);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
        />
        {query && (
          <button
            type="button"
            aria-label="Очистить поиск"
            className="text-white/40 transition-colors hover:text-site-red"
            onClick={() => {
              setQuery('');
              setOpen(false);
            }}
          >
            ✕
          </button>
        )}
      </div>

      {open && query.trim().length >= 2 && (
        <ul className="gold-scrollbar absolute z-40 mt-1 max-h-[320px] w-full overflow-y-auto rounded-card
                       border border-gold-dark/40 bg-[#0d0e15] py-1 shadow-dropdown">
          {results.length === 0 && (
            <li className="px-3 py-2 text-[12px] text-white/40">Ничего не найдено</li>
          )}
          {results.map((hit, position) => (
            <li key={`${hit.kind}-${hit.id}`}>
              <button
                type="button"
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors ${
                  position === highlight ? 'bg-gold-dark/25' : 'hover:bg-white/5'
                }`}
                onMouseEnter={() => setHighlight(position)}
                onClick={() => commit(hit)}
              >
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: hit.color }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] text-white/90">{hit.name}</span>
                  <span className="block truncate text-[10px] text-white/40">{hit.context}</span>
                </span>
                <span className="shrink-0 text-[9px] uppercase tracking-wide text-white/30">
                  {KIND_LABEL[hit.kind]}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default MapSearch;
