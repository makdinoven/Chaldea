import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchCustomsAdmin, putCustomsBans } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import type { CustomsAdmin, CustomsCountry, CustomsGroup } from '../../../types/economy';

/*
  FEAT-216 — «Таможня» (A1/A2): per country, the goods groups legal trade may not
  bring in (chips, saved per country) and the read-only list of its customs posts
  (posts are set with the «Таможня» checkbox in the location editor).
*/

/** Backend cap of banned groups per country (`customs_core.MAX_BANNED_GROUPS`). */
const BANS_MAX = 64;

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

const countryName = (c: CustomsCountry) => c.name ?? `Страна #${c.country_id}`;

interface CountryRowProps {
  country: CustomsCountry;
  groups: CustomsGroup[];
  canEdit: boolean;
  onSaved: (c: CustomsCountry) => void;
}

const CountryRow = ({ country, groups, canEdit, onSaved }: CountryRowProps) => {
  const [draft, setDraft] = useState<string[]>(country.banned_groups);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraft(country.banned_groups), [country.banned_groups]);

  const dirty = !sameSet(draft, country.banned_groups);
  const groupName = (code: string) => groups.find((g) => g.code === code)?.name ?? code;
  // Codes the server knows but the groups list lost (e.g. a deleted group) stay visible so they can be removed.
  const unknown = draft.filter((code) => !groups.some((g) => g.code === code));

  const toggle = (code: string) => {
    setError(null);
    setDraft((list) => {
      if (list.includes(code)) return list.filter((x) => x !== code);
      if (list.length >= BANS_MAX) {
        toast.error(`Не больше ${BANS_MAX} запрещённых групп`);
        return list;
      }
      return [...list, code];
    });
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const saved = await putCustomsBans(country.country_id, draft);
      toast.success(
        saved.banned_groups.length
          ? `«${countryName(saved)}»: запрещено групп — ${saved.banned_groups.length}`
          : `«${countryName(saved)}»: запретов нет`,
      );
      onSaved(saved);
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось сохранить запреты страны');
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className="flex flex-col gap-3 rounded-card border border-white/10 bg-white/[0.03] p-3 min-w-0">
      <div className="flex flex-wrap items-center gap-2 min-w-0">
        <span className="text-white text-sm font-medium break-words">{countryName(country)}</span>
        <span className={`text-xs ${country.banned_groups.length ? 'text-site-red' : 'text-white/40'}`}>
          {country.banned_groups.length ? `запрещено: ${country.banned_groups.length}` : 'запретов нет'}
        </span>
      </div>

      <div className="flex flex-col gap-1 min-w-0">
        <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">Посты</span>
        {country.posts.length === 0 ? (
          <p className="text-white/40 text-xs">Постов нет — законные караваны идут без досмотра.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {country.posts.map((p) => (
              <li
                key={p.location_id}
                className="rounded-full border border-gold/30 bg-gold/[0.06] px-2.5 py-0.5 text-[11px] text-gold break-words"
              >
                {p.is_port && <span aria-label="порт">⚓ </span>}
                {p.name ?? `Локация #${p.location_id}`}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-col gap-1 min-w-0">
        <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">Запрещённые группы товаров</span>
        {groups.length === 0 && unknown.length === 0 ? (
          <p className="text-white/40 text-xs">Групп товаров нет.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {[...groups.map((g) => g.code), ...unknown].map((code) => {
              const on = draft.includes(code);
              return (
                <button
                  key={code}
                  type="button"
                  aria-pressed={on}
                  disabled={!canEdit || saving}
                  onClick={() => toggle(code)}
                  className={`rounded-full border px-3 py-1 text-xs transition-colors duration-200 ease-site disabled:cursor-default ${
                    on
                      ? 'border-site-red/60 bg-site-red/15 text-site-red'
                      : 'border-white/15 text-white/60 enabled:hover:border-white/40 enabled:hover:text-white'
                  }`}
                >
                  {on && '⛔ '}
                  {groupName(code)}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {canEdit && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-blue !px-5 !py-1.5 !text-sm"
            disabled={!dirty || saving}
            onClick={() => void save()}
          >
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
          {dirty && !saving && (
            <button
              type="button"
              className="text-sm text-white/50 hover:text-white transition-colors duration-200"
              onClick={() => {
                setDraft(country.banned_groups);
                setError(null);
              }}
            >
              Отменить изменения
            </button>
          )}
        </div>
      )}
      {error && <p className="text-site-red text-xs sm:text-sm">{error}</p>}
    </li>
  );
};

const CustomsBansCard = ({ canEdit }: { canEdit: boolean }) => {
  const [data, setData] = useState<CustomsAdmin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const load = useCallback(() => {
    fetchCustomsAdmin()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить таможню');
        setError(msg);
        toast.error(msg);
      });
  }, []);

  useEffect(load, [load]);

  const replace = (c: CustomsCountry) =>
    setData((prev) =>
      prev
        ? { ...prev, countries: prev.countries.map((x) => (x.country_id === c.country_id ? { ...x, ...c } : x)) }
        : prev,
    );

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    const list = q ? data.countries.filter((c) => countryName(c).toLowerCase().includes(q)) : data.countries;
    return [...list].sort((a, b) => countryName(a).localeCompare(countryName(b), 'ru'));
  }, [data, query]);

  return (
    <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
      <div className="flex flex-col gap-1">
        <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Таможня</h2>
        <p className="text-white/50 text-sm">
          Запрещённые группы товаров не ввозятся законной торговлей в страну — часть таких сделок уходит
          контрабандистам. Посты ставятся галочкой «Таможня» в редакторе локаций; нет поста — нет досмотра.
        </p>
      </div>

      {error && !data ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !text-sm" onClick={load}>
            Повторить
          </button>
        </div>
      ) : !data ? (
        <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      ) : data.countries.length === 0 ? (
        <p className="text-white/40 text-sm">Стран нет.</p>
      ) : (
        <>
          {data.countries.length > 3 && (
            <input
              type="search"
              className="input-underline w-full sm:max-w-[320px]"
              placeholder="Поиск по названию страны"
              maxLength={100}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
          {filtered.length === 0 ? (
            <p className="text-white/40 text-sm">Ничего не найдено.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {filtered.map((c) => (
                <CountryRow key={c.country_id} country={c} groups={data.groups} canEdit={canEdit} onSaved={replace} />
              ))}
            </ul>
          )}
        </>
      )}
      {!canEdit && <p className="field-hint">Менять запреты может администратор с правом «economy:settings».</p>}
    </section>
  );
};

export default CustomsBansCard;
