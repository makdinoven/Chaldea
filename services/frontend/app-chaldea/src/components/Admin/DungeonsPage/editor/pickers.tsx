import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import useDebounce from '../../../../hooks/useDebounce';
import { searchLocations } from '../../../../api/startingPoints';

/*
  Pickers for the dungeon admin: an item, a mob or a location is found by its
  name or its id and shown by name — no more typing bare ids.
*/

interface Option {
  id: number;
  label: string;
  /** A second line: level and tier, the location's region… */
  sub?: string;
}

type Kind = 'item' | 'mob' | 'location';

const TIER_LABELS: Record<string, string> = { normal: 'обычный', elite: 'элитный', boss: 'босс' };
const SEARCH_LIMIT = 20;
const BULK_MAX = 100;

// Names already looked up, for every picker on the page.
const known: Record<Kind, Map<number, Option>> = { item: new Map(), mob: new Map(), location: new Map() };
const remember = (kind: Kind, options: Option[]) => options.forEach((o) => known[kind].set(o.id, o));

interface ItemCard {
  id: number;
  name: string;
  item_type?: string;
  item_rarity?: string;
  rarity?: string;
}
interface MobRow {
  id: number;
  name: string;
  level: number;
  tier: string;
}

const itemOption = (i: ItemCard): Option => ({ id: i.id, label: i.name, sub: `#${i.id}` });
const mobOption = (m: MobRow): Option => ({
  id: m.id,
  label: m.name,
  sub: `#${m.id} · ур. ${m.level} · ${TIER_LABELS[m.tier] ?? m.tier}`,
});

const isId = (q: string) => /^\d+$/.test(q.trim());

const search: Record<Kind, (q: string) => Promise<Option[]>> = {
  item: async (q) => {
    const byName = axios
      .get('/inventory/items', { params: { q, page: 1, page_size: SEARCH_LIMIT } })
      .then(({ data }) => ((Array.isArray(data) ? data : data.items ?? []) as ItemCard[]).map(itemOption));
    const byId = isId(q)
      ? axios.get<ItemCard>(`/inventory/items/${q.trim()}`).then(({ data }) => [itemOption(data)]).catch(() => [])
      : Promise.resolve([] as Option[]);
    const [ids, names] = await Promise.all([byId, byName]);
    return [...ids, ...names.filter((o) => !ids.some((i) => i.id === o.id))];
  },
  mob: async (q) => {
    const byName = axios
      .get('/characters/admin/mob-templates', { params: { q, page: 1, page_size: SEARCH_LIMIT } })
      .then(({ data }) => ((data.items ?? []) as MobRow[]).map(mobOption));
    const byId = isId(q)
      ? axios.get<MobRow>(`/characters/admin/mob-templates/${q.trim()}`).then(({ data }) => [mobOption(data)]).catch(() => [])
      : Promise.resolve([] as Option[]);
    const [ids, names] = await Promise.all([byId, byName]);
    return [...ids, ...names.filter((o) => !ids.some((i) => i.id === o.id))];
  },
  location: async (q) =>
    (await searchLocations(q, SEARCH_LIMIT)).map((l) => ({
      id: l.id,
      label: l.name,
      sub: [`#${l.id}`, l.district_name, l.region_name, l.country_name].filter(Boolean).join(' · '),
    })),
};

/** Names for ids picked earlier (saved configs come with ids only). */
const lookup: Record<Kind, (ids: number[]) => Promise<Option[]>> = {
  item: async (ids) => {
    const out: Option[] = [];
    for (let i = 0; i < ids.length; i += BULK_MAX) {
      const { data } = await axios.get<ItemCard[]>('/inventory/items/bulk', {
        params: { ids: ids.slice(i, i + BULK_MAX).join(',') },
      });
      out.push(...data.map(itemOption));
    }
    return out;
  },
  mob: async (ids) =>
    (await Promise.all(
      ids.map((id) => axios.get<MobRow>(`/characters/admin/mob-templates/${id}`).then(({ data }) => mobOption(data)).catch(() => null)),
    )).filter((o): o is Option => o !== null),
  location: async (ids) =>
    (await Promise.all(ids.map((id) => search.location(String(id)).catch(() => [] as Option[])))).flat()
      .filter((o) => ids.includes(o.id)),
};

/** The names of these ids; unknown ones read "#id" until (or unless) they are found. */
const useNames = (kind: Kind, ids: number[]): ((id: number) => Option) => {
  const [, setTick] = useState(0);
  const key = ids.join(',');
  useEffect(() => {
    const missing = [...new Set(ids)].filter((id) => id > 0 && !known[kind].has(id));
    if (!missing.length) return;
    let alive = true;
    lookup[kind](missing)
      .then((found) => {
        remember(kind, found);
        // An id nobody has: remembered as such, so it is not asked for again.
        missing.filter((id) => !known[kind].has(id)).forEach((id) =>
          known[kind].set(id, { id, label: `#${id}`, sub: 'не найден' }));
        if (alive) setTick((t) => t + 1);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, key]);
  return (id: number) => known[kind].get(id) ?? { id, label: `#${id}` };
};

const PLACEHOLDERS: Record<Kind, string> = {
  item: 'Предмет: название или id',
  mob: 'Моб: название или id',
  location: 'Локация: название или id',
};

/** A search box with a list of what it found; picking one hands its id over. */
const SearchBox = ({ kind, onPick, autoFocus }: { kind: Kind; onPick: (o: Option) => void; autoFocus?: boolean }) => {
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 300) as string;
  const [results, setResults] = useState<Option[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = debounced.trim();
    if (!q) {
      setResults([]);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    search[kind](q)
      .then((found) => {
        if (!alive) return;
        remember(kind, found);
        setResults(found);
      })
      .catch(() => alive && setError('Не удалось выполнить поиск'))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [debounced, kind]);

  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, []);

  return (
    <div ref={box} className="relative w-full min-w-0">
      <input
        className="input-underline !text-sm w-full"
        placeholder={PLACEHOLDERS[kind]}
        value={query}
        autoFocus={autoFocus}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
      />
      {open && query.trim() && (
        <div className="dropdown-menu absolute left-0 top-full mt-1 z-50 min-w-full w-max max-w-[min(18rem,80vw)] max-h-60 overflow-y-auto gold-scrollbar">
          {loading && <div className="px-3 py-2 text-xs text-white/50">Поиск...</div>}
          {error && <div className="px-3 py-2 text-xs text-site-red">{error}</div>}
          {!loading && !error && results.length === 0 && debounced.trim() === query.trim() && (
            <div className="px-3 py-2 text-xs text-white/50">Ничего не найдено</div>
          )}
          {!loading &&
            results.map((o) => (
              <button
                key={o.id}
                type="button"
                className="dropdown-item w-full text-left flex flex-col !py-1.5"
                onClick={() => {
                  onPick(o);
                  setQuery('');
                  setResults([]);
                  setOpen(false);
                }}
              >
                <span className="text-sm text-white truncate">{o.label}</span>
                {o.sub && <span className="text-[10px] text-white/45 truncate">{o.sub}</span>}
              </button>
            ))}
        </div>
      )}
    </div>
  );
};

const Chip = ({ option, onRemove }: { option: Option; onRemove: () => void }) => (
  <span className="inline-flex items-center gap-1 max-w-full rounded-full bg-white/10 pl-2.5 pr-1 py-0.5 text-xs text-white">
    <span className="truncate" title={option.sub ? `${option.label} — ${option.sub}` : option.label}>
      {option.label}
    </span>
    {option.label !== `#${option.id}` && <span className="text-white/40 shrink-0">#{option.id}</span>}
    <button
      type="button"
      onClick={onRemove}
      className="shrink-0 w-4 h-4 leading-none rounded-full text-white/60 hover:text-site-red"
      aria-label="Убрать"
    >
      ×
    </button>
  </span>
);

/** One thing (an item, a mob, a location), or none. */
export const EntityPicker = ({
  kind,
  value,
  onChange,
}: {
  kind: Kind;
  value: number | null | undefined;
  onChange: (id: number | null) => void;
}) => {
  const name = useNames(kind, value ? [value] : []);
  if (value) {
    const o = name(value);
    return (
      <div className="flex flex-col gap-0.5 min-w-0">
        <div>
          <Chip option={o} onRemove={() => onChange(null)} />
        </div>
        {o.sub && o.sub !== `#${o.id}` && <span className="text-[10px] text-white/40 truncate">{o.sub}</span>}
      </div>
    );
  }
  return <SearchBox kind={kind} onPick={(o) => onChange(o.id)} />;
};

/** A list of ids picked by name. `repeats`: the same mob may stand twice in a pack. */
export const EntityListPicker = ({
  kind,
  ids,
  onChange,
  repeats = false,
}: {
  kind: Kind;
  ids: number[];
  onChange: (ids: number[]) => void;
  repeats?: boolean;
}) => {
  const name = useNames(kind, ids);
  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      {ids.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {ids.map((id, idx) => (
            <Chip key={`${id}-${idx}`} option={name(id)} onRemove={() => onChange(ids.filter((_, i) => i !== idx))} />
          ))}
        </div>
      )}
      <SearchBox
        kind={kind}
        onPick={(o) => {
          if (!repeats && ids.includes(o.id)) return;
          onChange([...ids, o.id]);
        }}
      />
    </div>
  );
};
