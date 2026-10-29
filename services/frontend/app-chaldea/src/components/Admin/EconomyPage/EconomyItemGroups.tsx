import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { ChevronLeft, ChevronRight, RefreshCw, X } from 'lucide-react';
import { fetchEconomyGoodsGroups, fetchEconomyItemGroups, putEconomyItemGroups } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import useDebounce from '../../../hooks/useDebounce';
import { useCurrency } from '../../../hooks/useCurrency';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import { ITEM_TYPES, ITEM_TYPE_LABELS, RARITY_LABELS, RARITY_TEXT_COLORS, shownRarity } from '../../../constants/items';
import type { EconGoodsGroup, EconItemGroupRow, EconItemGroupsParams, EconItemGroupsUpdate } from '../../../types/economy';

const PAGE_SIZE = 50;
/** Backend limit of one bulk `PUT /admin/economy/item-groups` (feature file 3.7). */
const MAX_BULK = 500;
const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_MAX = 100;
/** Select value meaning «back to the auto group» (`group_code: null`). */
const AUTO_GROUP = '__auto__';

type SourceFilter = '' | 'auto' | 'manual';
type OffMarketFilter = '' | 'yes' | 'no';

const isManual = (r: EconItemGroupRow) => r.override_group !== null || r.override_off_market !== null;

const Badge = ({ tone, children, title }: { tone: 'gold' | 'blue' | 'red' | 'green' | 'muted'; children: string; title?: string }) => {
  const cls = {
    gold: 'border-gold/50 bg-gold/10 text-gold',
    blue: 'border-site-blue/50 bg-site-blue/10 text-site-blue',
    red: 'border-site-red/50 bg-site-red/10 text-site-red',
    green: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy',
    muted: 'border-white/20 text-white/50',
  }[tone];
  return (
    <span title={title} className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap ${cls}`}>
      {children}
    </span>
  );
};

const FieldLabel = ({ htmlFor, children }: { htmlFor: string; children: string }) => (
  <label htmlFor={htmlFor} className="text-white/60 text-xs uppercase tracking-[0.06em]">
    {children}
  </label>
);

/** «Предметы» (FEAT-182): which goods group each item belongs to, overrides and the off-market mark. */
const EconomyItemGroups = () => {
  const canEdit = hasPermission(useAppSelector(selectPermissions), 'economy:settings');
  const { format } = useCurrency();

  const [groups, setGroups] = useState<EconGoodsGroup[]>([]);
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, SEARCH_DEBOUNCE_MS) as string;
  const [itemType, setItemType] = useState('');
  const [group, setGroup] = useState('');
  const [source, setSource] = useState<SourceFilter>('');
  const [offMarket, setOffMarket] = useState<OffMarketFilter>('');
  const [page, setPage] = useState(1);

  const [rows, setRows] = useState<EconItemGroupRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  /** Selection survives paging and filtering so the admin can collect items from several pages. */
  const [selected, setSelected] = useState<Map<number, EconItemGroupRow>>(new Map());
  const [bulkGroup, setBulkGroup] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchEconomyGoodsGroups()
      .then((list) => {
        if (!cancelled) setGroups([...list].sort((a, b) => a.sort_order - b.sort_order));
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить группы товаров'));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Any filter change starts from the first page.
  useEffect(() => setPage(1), [debouncedQuery, itemType, group, source, offMarket]);

  useEffect(() => {
    let cancelled = false;
    const params: EconItemGroupsParams = {
      q: debouncedQuery.trim() || undefined,
      item_type: itemType || undefined,
      group: group || undefined,
      source: source || undefined,
      off_market: offMarket === '' ? undefined : offMarket === 'yes',
      page,
      page_size: PAGE_SIZE,
    };
    setLoading(true);
    fetchEconomyItemGroups(params)
      .then((res) => {
        if (cancelled) return;
        setRows(res.items);
        setTotal(res.total);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить предметы');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, itemType, group, source, offMarket, page, reloadKey]);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  const groupNames = useMemo(() => Object.fromEntries(groups.map((g) => [g.code, g.name])), [groups]);
  const groupName = (code: string | null) => (code ? groupNames[code] ?? code : null);

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageRows = rows ?? [];
  const allOnPageSelected = pageRows.length > 0 && pageRows.every((r) => selected.has(r.item_id));
  const selectedCount = selected.size;
  const tooMany = selectedCount > MAX_BULK;

  const toggleRow = (r: EconItemGroupRow) =>
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(r.item_id)) next.delete(r.item_id);
      else next.set(r.item_id, r);
      return next;
    });

  const togglePage = () =>
    setSelected((prev) => {
      const next = new Map(prev);
      if (allOnPageSelected) pageRows.forEach((r) => next.delete(r.item_id));
      else pageRows.forEach((r) => next.set(r.item_id, r));
      return next;
    });

  const applyBulk = async (patch: Omit<EconItemGroupsUpdate, 'item_ids'>, success: string) => {
    if (selectedCount === 0 || tooMany) return;
    setBusy(true);
    try {
      const res = await putEconomyItemGroups({ item_ids: [...selected.keys()], ...patch });
      toast.success(`${success}: ${res.updated}`);
      setSelected(new Map());
      setBulkGroup('');
      reload();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось изменить группы предметов'));
    } finally {
      setBusy(false);
    }
  };

  const assignGroup = () => {
    if (!bulkGroup) return;
    const code = bulkGroup === AUTO_GROUP ? null : bulkGroup;
    applyBulk({ group_code: code }, code ? `Группа «${groupName(code)}» назначена предметам` : 'Группа возвращена к авто');
  };

  const resetFilters = () => {
    setQuery('');
    setItemType('');
    setGroup('');
    setSource('');
    setOffMarket('');
  };
  const filtersSet = query || itemType || group || source || offMarket;

  const badges = (r: EconItemGroupRow) => (
    <>
      {isManual(r) ? (
        <Badge tone="blue" title="Группа или отметка рынка заданы вручную">вручную</Badge>
      ) : (
        <Badge tone="muted" title="Группа определена автоматически по типу предмета">авто</Badge>
      )}
      {r.off_market && <Badge tone="red" title="Не продаётся у торговцев, цена фиксированная">вне рынка</Badge>}
      {r.in_quests && (
        <Badge tone="gold" title="Предмет нужен в заданиях (собрать / доставить) — возможно, его стоит убрать с рынка">
          в заданиях
        </Badge>
      )}
    </>
  );

  const groupCell = (r: EconItemGroupRow) => {
    const name = groupName(r.group);
    const autoDiffers = r.override_group !== null && r.override_group !== r.auto_group;
    return (
      <span className="flex flex-col min-w-0">
        {name ? <span className="text-white/90 break-words">{name}</span> : <span className="text-site-red">без группы</span>}
        {autoDiffers && <span className="text-white/40 text-xs break-words">авто: {groupName(r.auto_group) ?? 'нет'}</span>}
      </span>
    );
  };

  const typeLine = (r: EconItemGroupRow) => {
    const rarity = shownRarity(r.item_type, r.item_rarity);
    return (
      <span className="text-xs text-white/50 break-words">
        {ITEM_TYPE_LABELS[r.item_type] ?? r.item_type}
        {rarity && (
          <>
            {' · '}
            <span className={RARITY_TEXT_COLORS[rarity] ?? ''}>{RARITY_LABELS[rarity] ?? rarity}</span>
          </>
        )}
        {r.is_food && ' · еда'}
      </span>
    );
  };

  const thumb = (r: EconItemGroupRow) =>
    r.image ? (
      <img src={r.image} alt="" loading="lazy" className="w-9 h-9 rounded object-cover shrink-0 bg-white/5" />
    ) : (
      <span className="w-9 h-9 rounded shrink-0 bg-white/5" aria-hidden="true" />
    );

  const checkbox = (r: EconItemGroupRow) => (
    <input
      type="checkbox"
      aria-label={`Выбрать «${r.name}»`}
      checked={selected.has(r.item_id)}
      onChange={() => toggleRow(r)}
      onClick={(e) => e.stopPropagation()}
      className="w-4 h-4 shrink-0 accent-gold cursor-pointer"
    />
  );

  return (
    <div className="flex flex-col gap-5">
      <p className="text-white/50 text-sm max-w-3xl">
        Группа предмета определяет его рыночную цену в регионе. Обычно она выводится из типа предмета («авто»);
        здесь можно назначить её вручную или убрать предмет с рынка — например, квестовые предметы (отметка
        «в заданиях» подсказывает, какие предметы нужны в заданиях).
      </p>
      {!canEdit && <p className="field-hint">Только просмотр: менять группы предметов может администратор с правом «economy:settings».</p>}

      {/* Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))_auto] gap-4 items-end">
        <div className="flex flex-col gap-1 min-w-0">
          <FieldLabel htmlFor="econ-items-q">Поиск</FieldLabel>
          <input
            id="econ-items-q"
            type="text"
            className="input-underline w-full"
            placeholder="Название предмета..."
            value={query}
            maxLength={SEARCH_MAX}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <FieldLabel htmlFor="econ-items-type">Тип</FieldLabel>
          <select id="econ-items-type" className="input-underline w-full" value={itemType} onChange={(e) => setItemType(e.target.value)}>
            <option value="" className="bg-site-dark text-white">Все типы</option>
            {ITEM_TYPES.map((t) => (
              <option key={t} value={t} className="bg-site-dark text-white">
                {ITEM_TYPE_LABELS[t] ?? t}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <FieldLabel htmlFor="econ-items-group">Группа</FieldLabel>
          <select id="econ-items-group" className="input-underline w-full" value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="" className="bg-site-dark text-white">Все группы</option>
            <option value="none" className="bg-site-dark text-white">Без группы</option>
            {groups.map((g) => (
              <option key={g.code} value={g.code} className="bg-site-dark text-white">
                {g.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <FieldLabel htmlFor="econ-items-source">Источник</FieldLabel>
          <select
            id="econ-items-source"
            className="input-underline w-full"
            value={source}
            onChange={(e) => setSource(e.target.value as SourceFilter)}
          >
            <option value="" className="bg-site-dark text-white">Любой</option>
            <option value="auto" className="bg-site-dark text-white">Авто</option>
            <option value="manual" className="bg-site-dark text-white">Вручную</option>
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <FieldLabel htmlFor="econ-items-market">Рынок</FieldLabel>
          <select
            id="econ-items-market"
            className="input-underline w-full"
            value={offMarket}
            onChange={(e) => setOffMarket(e.target.value as OffMarketFilter)}
          >
            <option value="" className="bg-site-dark text-white">Все</option>
            <option value="no" className="bg-site-dark text-white">На рынке</option>
            <option value="yes" className="bg-site-dark text-white">Вне рынка</option>
          </select>
        </div>
        <div className="flex items-center gap-3 sm:col-span-2 lg:col-span-1 pb-1">
          {filtersSet && (
            <button type="button" onClick={resetFilters} className="text-sm text-white/60 hover:text-white transition-colors duration-200 ease-site">
              Сбросить
            </button>
          )}
          <button
            type="button"
            onClick={reload}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
        </div>
      </div>

      {/* Bulk bar: pinned to the bottom of the viewport so it never shifts the list under the cursor */}
      {canEdit && selectedCount > 0 && (
        <div className="fixed bottom-3 left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-4xl max-h-[60vh] overflow-y-auto z-30 rounded-card border border-gold/30 bg-site-dark/95 backdrop-blur-sm p-3 sm:p-4 flex flex-col gap-3 shadow-card">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="text-white">
              Выбрано: <span className="text-gold">{selectedCount}</span>
            </span>
            <button
              type="button"
              onClick={() => setSelected(new Map())}
              className="inline-flex items-center gap-1 text-white/60 hover:text-white transition-colors duration-200 ease-site"
            >
              <X size={14} />
              Снять выбор
            </button>
            {tooMany && <span className="text-site-red text-xs">За раз можно изменить не больше {MAX_BULK} предметов</span>}
          </div>
          <div className="flex flex-col lg:flex-row lg:items-end gap-3">
            <div className="flex flex-col sm:flex-row sm:items-end gap-3 min-w-0">
              <div className="flex flex-col gap-1 min-w-0 sm:w-56">
                <FieldLabel htmlFor="econ-items-bulk-group">Группа</FieldLabel>
                <select
                  id="econ-items-bulk-group"
                  className="input-underline w-full"
                  value={bulkGroup}
                  onChange={(e) => setBulkGroup(e.target.value)}
                >
                  <option value="" className="bg-site-dark text-white">— выберите —</option>
                  <option value={AUTO_GROUP} className="bg-site-dark text-white">Авто (по типу предмета)</option>
                  {groups.map((g) => (
                    <option key={g.code} value={g.code} className="bg-site-dark text-white">
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
                disabled={!bulkGroup || busy || tooMany}
                onClick={assignGroup}
              >
                Назначить группу
              </button>
            </div>
            <div className="flex flex-wrap gap-2 lg:ml-auto">
              <button
                type="button"
                className="btn-line !text-xs !py-2 !px-4"
                disabled={busy || tooMany}
                onClick={() => applyBulk({ off_market: true }, 'Убрано с рынка')}
              >
                Убрать с рынка
              </button>
              <button
                type="button"
                className="btn-line !text-xs !py-2 !px-4"
                disabled={busy || tooMany}
                onClick={() => applyBulk({ off_market: false }, 'Возвращено на рынок')}
              >
                Вернуть на рынок
              </button>
              <button
                type="button"
                className="btn-line !text-xs !py-2 !px-4"
                disabled={busy || tooMany}
                title="Удалить ручные настройки: группа и рынок снова по авто-правилу"
                onClick={() => applyBulk({ reset: true }, 'Сброшено к авто')}
              >
                Сбросить к авто
              </button>
            </div>
          </div>
        </div>
      )}

      {error && !rows && <p className="text-site-red text-sm">{error}</p>}
      {!rows && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {rows && rows.length === 0 && <p className="text-white/40 text-sm italic">Предметов не найдено.</p>}

      {rows && rows.length > 0 && (
        <div className={`flex flex-col gap-3 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {canEdit && (
            <label className="flex items-center gap-2 text-sm text-white/70 cursor-pointer select-none self-start">
              <input type="checkbox" checked={allOnPageSelected} onChange={togglePage} className="w-4 h-4 shrink-0 accent-gold" />
              Выбрать все на странице
            </label>
          )}

          {/* Table — lg and up */}
          <div className="hidden lg:block bg-site-bg rounded-card border border-white/[0.07] px-4 py-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                  {canEdit && <th className="py-2 pr-3 font-normal w-8" />}
                  <th className="py-2 pr-3 font-normal">Предмет</th>
                  <th className="py-2 pr-3 font-normal">Группа</th>
                  <th className="py-2 pr-3 font-normal text-right">Цена</th>
                  <th className="py-2 font-normal">Отметки</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.item_id}
                    onClick={canEdit ? () => toggleRow(r) : undefined}
                    className={`border-b border-white/[0.07] last:border-b-0 transition-colors duration-200 ease-site ${
                      canEdit ? 'cursor-pointer hover:bg-white/[0.04]' : ''
                    } ${selected.has(r.item_id) ? 'bg-gold/[0.06]' : ''}`}
                  >
                    {canEdit && <td className="py-2 pr-3">{checkbox(r)}</td>}
                    <td className="py-2 pr-3">
                      <span className="flex items-center gap-3 min-w-0">
                        {thumb(r)}
                        <span className="flex flex-col min-w-0">
                          <span className="text-white break-words">{r.name}</span>
                          {typeLine(r)}
                        </span>
                      </span>
                    </td>
                    <td className="py-2 pr-3">{groupCell(r)}</td>
                    <td className="py-2 pr-3 text-right text-white/80 whitespace-nowrap">
                      {r.price > 0 ? format(r.price) : <span className="text-white/30">—</span>}
                    </td>
                    <td className="py-2">
                      <span className="flex flex-wrap gap-1.5">{badges(r)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Cards — below lg */}
          <ul className="lg:hidden grid grid-cols-1 md:grid-cols-2 gap-3">
            {rows.map((r) => {
              const isSel = selected.has(r.item_id);
              const body = (
                <>
                  <span className="flex items-start gap-3 min-w-0">
                    {canEdit && <span className="pt-2.5">{checkbox(r)}</span>}
                    {thumb(r)}
                    <span className="flex-1 flex flex-col min-w-0">
                      <span className="text-white text-sm break-words">{r.name}</span>
                      {typeLine(r)}
                    </span>
                    <span className="text-white/80 text-xs whitespace-nowrap pt-0.5">{r.price > 0 ? format(r.price) : '—'}</span>
                  </span>
                  <span className="text-sm">{groupCell(r)}</span>
                  <span className="flex flex-wrap gap-1.5">{badges(r)}</span>
                </>
              );
              const cls = `w-full text-left bg-site-bg rounded-card border p-3 flex flex-col gap-2 transition-colors duration-200 ease-site ${
                isSel ? 'border-gold/50' : 'border-white/[0.07]'
              }`;
              return (
                <li key={r.item_id}>
                  {canEdit ? (
                    <div role="button" tabIndex={0} onClick={() => toggleRow(r)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          toggleRow(r);
                        }
                      }}
                      className={`${cls} cursor-pointer hover:border-gold/40`}
                    >
                      {body}
                    </div>
                  ) : (
                    <div className={cls}>{body}</div>
                  )}
                </li>
              );
            })}
          </ul>

          {/* Pagination */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <span className="text-white/50">
              Всего: {total.toLocaleString('ru-RU')}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="Предыдущая страница"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="p-1.5 text-white/60 hover:text-gold disabled:opacity-30 transition-colors duration-200 ease-site"
              >
                <ChevronLeft size={18} />
              </button>
              <span className="text-white/70">
                {page} из {pages}
              </span>
              <button
                type="button"
                aria-label="Следующая страница"
                disabled={page >= pages || loading}
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                className="p-1.5 text-white/60 hover:text-gold disabled:opacity-30 transition-colors duration-200 ease-site"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Room below the list so the pinned bulk bar does not cover the last rows */}
      {canEdit && selectedCount > 0 && <div aria-hidden className="h-56 sm:h-40 lg:h-32" />}
    </div>
  );
};

export default EconomyItemGroups;
