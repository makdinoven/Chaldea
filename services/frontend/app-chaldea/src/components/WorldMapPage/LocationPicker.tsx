import { useEffect, useMemo, useRef, useState } from 'react';
import type { GraphLocation } from '../../api/worldGraph';

interface LocationPickerProps {
  locations: GraphLocation[];
  regionNames: Map<number, string>;
  value: number | null;
  onChange: (id: number | null) => void;
  placeholder: string;
  accentColor: string;
}

const MAX_RESULTS = 40;

const LocationPicker = ({
  locations,
  regionNames,
  value,
  onChange,
  placeholder,
  accentColor,
}: LocationPickerProps) => {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const selected = useMemo(
    () => locations.find((l) => l.id === value) ?? null,
    [locations, value],
  );

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return locations.slice(0, MAX_RESULTS);
    const matches: GraphLocation[] = [];
    for (const location of locations) {
      if (location.name.toLowerCase().includes(needle)) {
        matches.push(location);
        if (matches.length >= MAX_RESULTS) break;
      }
    }
    return matches;
  }, [locations, query]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  const commit = (location: GraphLocation) => {
    onChange(location.id);
    setQuery('');
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setOpen(true);
      setHighlight((h) => Math.min(h + 1, results.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const target = results[highlight];
      if (target) commit(target);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={containerRef} className="relative flex-1 min-w-0">
      <div
        className="flex items-center gap-2 rounded-lg border bg-black/40 px-2.5 py-1.5"
        style={{ borderColor: `${accentColor}66` }}
      >
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: accentColor }}
          aria-hidden
        />
        <input
          type="text"
          className="min-w-0 flex-1 bg-transparent text-[13px] text-white placeholder-white/35 outline-none"
          placeholder={selected ? selected.name : placeholder}
          value={open ? query : selected?.name ?? ''}
          onFocus={() => {
            setOpen(true);
            setQuery('');
            setHighlight(0);
          }}
          onChange={(event) => {
            setQuery(event.target.value);
            setHighlight(0);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
        />
        {selected && (
          <button
            type="button"
            aria-label="Очистить точку"
            className="shrink-0 text-white/40 transition-colors hover:text-site-red"
            onClick={() => {
              onChange(null);
              setQuery('');
            }}
          >
            ✕
          </button>
        )}
      </div>

      {open && (
        <ul
          className="gold-scrollbar absolute z-30 mt-1 max-h-64 w-full overflow-y-auto rounded-lg
                     border border-gold-dark/50 bg-[#0d0e15] py-1 shadow-dropdown"
        >
          {results.length === 0 && (
            <li className="px-3 py-2 text-[12px] text-white/40">Ничего не найдено</li>
          )}
          {results.map((location, index) => (
            <li key={location.id}>
              <button
                type="button"
                className={`flex w-full flex-col items-start px-3 py-1.5 text-left transition-colors ${
                  index === highlight ? 'bg-gold-dark/25' : 'hover:bg-white/5'
                }`}
                onMouseEnter={() => setHighlight(index)}
                onClick={() => commit(location)}
              >
                <span className="w-full truncate text-[13px] text-white/90">{location.name}</span>
                <span className="w-full truncate text-[10px] text-white/40">
                  {regionNames.get(location.region_id) ?? '—'} · ур. {location.recommended_level}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default LocationPicker;
