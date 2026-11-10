import { useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';
import { NPC_ROLES } from '../../constants/npc';
import AdminPagination from '../Admin/AdminPagination/AdminPagination';
import ConfirmationModal from '../ui/ConfirmationModal';
import NpcRow, { type NpcListItem } from './NpcRow';
import NpcExpandedPanel from './NpcExpandedPanel';
import type { RaceWithSubraces } from './NpcGeneralForm';
import { availableTabs, isNpcTabKey, type NpcTabKey } from './npcTabKeys';
import { setNpcReady } from '../../api/npcAdmin';
import { usePanelUrlState } from '../Admin/ExpandableList/usePanelUrlState';
import { useDirtyGuard } from '../Admin/ExpandableList/useDirtyGuard';
import { useGeoFilter } from '../Admin/ExpandableList/useGeoFilter';
import { useReadyFilterUrlState } from '../Admin/ExpandableList/useReadyFilterUrlState';
import GeoFilterSelects from '../Admin/ExpandableList/GeoFilterSelects';
import ReadyFilterSelect from '../Admin/ExpandableList/ReadyFilterSelect';

/* FEAT-208: NPC list as expandable plates; the open NPC + tab live in `?npc=&tab=`.
   FEAT-209: country / region / ready filters live in `?country=&region=&ready=`. */

interface NpcDetailResponse {
  id: number;
  name: string;
  avatar: string | null;
  level: number;
  npc_role: string | null;
  npc_status: string | null;
  current_location_id: number | null;
  npc_ready?: boolean;
  npc_ready_at?: string | null;
  npc_ready_by?: string | null;
}

/** A row of GET /characters/admin/npcs (location_name is filled by the list endpoint). */
interface NpcApiItem extends NpcDetailResponse {
  location_name?: string | null;
}

const PAGE_SIZE = 20;

const readyFields = (d: Pick<NpcDetailResponse, 'npc_ready' | 'npc_ready_at' | 'npc_ready_by'>) => ({
  npc_ready: !!d.npc_ready,
  npc_ready_at: d.npc_ready_at ?? null,
  npc_ready_by: d.npc_ready_by ?? null,
});

const errorDetail = (err: unknown): string | null => {
  if (!axios.isAxiosError(err)) return null;
  const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' && detail.trim() ? detail : null;
};

const detailToListItem = (d: NpcDetailResponse): NpcListItem => ({
  id: d.id,
  name: d.name,
  avatar: d.avatar,
  level: d.level,
  npc_role: d.npc_role,
  npc_status: d.npc_status,
  location_id: d.current_location_id,
  // The detail endpoint has no location name — the plate shows «Локация #id».
  location_name: null,
  ...readyFields(d),
});

/* ── Component ── */

const AdminNpcsPage = () => {
  const [npcs, setNpcs] = useState<NpcListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [listLoaded, setListLoaded] = useState(false);
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const debouncedQuery = useDebounce(query);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [racesData, setRacesData] = useState<RaceWithSubraces[]>([]);

  const {
    target: openTarget,
    tab: urlTab,
    rawTarget: rawNpc,
    open: openNpc,
    setTab,
    close,
    normalize,
  } = usePanelUrlState('npc', isNpcTabKey, 'general');
  const [pinned, setPinned] = useState<NpcListItem | null>(null);
  const { onDirtyChange: handleDirtyChange, guard, pendingLeave, confirmLeave, cancelLeave, resetDirty } =
    useDirtyGuard(openTarget !== null);
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [resurrecting, setResurrecting] = useState(false);
  const openRowRef = useRef<HTMLDivElement>(null);
  const [readyPending, setReadyPending] = useState(false);

  /* ── Country / region / ready filters (URL) ── */

  const resetPage = useCallback(() => setPage(1), []);
  const { countryId, regionId, settled: filtersSettled, selectProps: geoSelectProps } = useGeoFilter({
    onChanged: resetPage,
  });
  const { ready: readyFilter, setReady } = useReadyFilterUrlState();

  // The list is requested only once the URL filters are validated (no request / toast for a reset filter)
  const fetchNpcs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (debouncedQuery) params.q = debouncedQuery;
      if (roleFilter) params.npc_role = roleFilter;
      if (statusFilter) params.npc_status = statusFilter;
      if (countryId !== null) params.country_id = String(countryId);
      if (regionId !== null) params.region_id = String(regionId);
      if (readyFilter !== null) params.ready = readyFilter ? '1' : '0';
      params.page = String(page);
      params.page_size = String(PAGE_SIZE);
      const res = await axios.get(`${BASE_URL}/characters/admin/npcs`, { params });
      const data = res.data;
      const rows: NpcApiItem[] = Array.isArray(data) ? data : (data.items ?? []);
      setNpcs(
        rows.map((r) => ({
          ...r,
          location_id: r.current_location_id,
          location_name: r.location_name ?? null,
          ...readyFields(r),
        })),
      );
      setTotal(data.total ?? 0);
    } catch {
      toast.error('Не удалось загрузить список НПС');
    } finally {
      setLoading(false);
      setListLoaded(true);
    }
  }, [debouncedQuery, roleFilter, statusFilter, countryId, regionId, readyFilter, page]);

  useEffect(() => {
    if (filtersSettled) fetchNpcs();
  }, [fetchNpcs, filtersSettled]);

  // Races with subraces — shared by the «Основное» form and the stats editor
  useEffect(() => {
    axios
      .get<RaceWithSubraces[]>(`${BASE_URL}/characters/races`)
      .then((res) => setRacesData(res.data))
      .catch(() => toast.error('Не удалось загрузить список рас и подрас'));
  }, []);

  /* ── Open NPC resolution ── */

  const openId = typeof openTarget === 'number' ? openTarget : null;
  const inList = openId !== null ? npcs.find((n) => n.id === openId) ?? null : null;
  const pinnedItem = openId !== null && !inList && pinned?.id === openId ? pinned : null;
  const openItem = inList ?? pinnedItem;
  const isNew = openTarget === 'new';

  const fetchPinned = useCallback(async (id: number): Promise<boolean> => {
    try {
      const res = await axios.get<NpcDetailResponse>(`${BASE_URL}/characters/admin/npcs/${id}`);
      setPinned(detailToListItem(res.data));
      return true;
    } catch (err) {
      const notFound = axios.isAxiosError(err) && err.response?.status === 404;
      toast.error(notFound ? 'НПС не найден' : 'Не удалось загрузить данные НПС');
      return false;
    }
  }, []);

  // Deep link / NPC that left the current page → load it as a pinned plate
  const needPinned = openId !== null && listLoaded && !inList && pinned?.id !== openId;
  useEffect(() => {
    if (!needPinned || openId === null) return;
    let cancelled = false;
    fetchPinned(openId).then((ok) => {
      if (!ok && !cancelled) normalize(null);
    });
    return () => {
      cancelled = true;
    };
  }, [needPinned, openId, fetchPinned, normalize]);

  const tabs = availableTabs(openItem?.npc_role ?? null, isNew);
  const activeTab: NpcTabKey = urlTab && tabs.includes(urlTab) ? urlTab : 'general';

  // URL normalisation (replace): garbage `npc`, invalid / unavailable tab
  useEffect(() => {
    if (rawNpc !== null && openTarget === null) {
      normalize(null);
      return;
    }
    if (isNew && urlTab !== 'general') {
      normalize('new', 'general');
      return;
    }
    if (openItem && urlTab !== activeTab) {
      normalize(openItem.id, activeTab);
    }
  }, [rawNpc, openTarget, isNew, urlTab, activeTab, openItem, normalize]);

  /* ── Actions ── */

  const toggleRow = (id: number) => {
    if (openId === id) guard(close);
    else guard(() => openNpc(id));
  };

  const handleSaved = (id: number, created: boolean) => {
    if (created) {
      normalize(id, 'general');
    } else if (pinnedItem?.id === id) {
      fetchPinned(id);
    }
    fetchNpcs();
  };

  const handleDelete = async () => {
    const id = deleteTarget;
    setDeleteTarget(null);
    if (id === null) return;
    try {
      await axios.delete(`${BASE_URL}/characters/admin/npcs/${id}`);
      toast.success('НПС удалён');
      setNpcs((prev) => prev.filter((n) => n.id !== id));
      setPinned((prev) => (prev?.id === id ? null : prev));
      resetDirty();
      if (openId === id) normalize(null);
      fetchNpcs();
    } catch {
      toast.error('Не удалось удалить НПС');
    }
  };

  const handleResurrect = async (id: number) => {
    setResurrecting(true);
    try {
      await axios.put(`${BASE_URL}/characters/admin/npcs/${id}`, { npc_status: 'alive' });
      toast.success('НПС воскрешён');
      if (pinnedItem?.id === id) fetchPinned(id);
      fetchNpcs();
    } catch {
      toast.error('Не удалось воскресить НПС');
    } finally {
      setResurrecting(false);
    }
  };

  const handleToggleReady = async (item: NpcListItem) => {
    setReadyPending(true);
    try {
      const res = await setNpcReady(item.id, !item.npc_ready);
      const patchRow = (n: NpcListItem): NpcListItem => (n.id === res.id ? { ...n, ...readyFields(res) } : n);
      setNpcs((prev) => prev.map(patchRow));
      setPinned((prev) => (prev ? patchRow(prev) : prev));
      toast.success(res.npc_ready ? 'НПС отмечен готовым' : 'Отметка «Готов» снята');
      // The NPC may leave the filtered set — it then stays open as a pinned plate
      if (readyFilter !== null) fetchNpcs();
    } catch (err) {
      const detail = errorDetail(err);
      toast.error(`Не удалось изменить отметку «Готов»${detail ? `: ${detail}` : ''}`);
    } finally {
      setReadyPending(false);
    }
  };

  /* ── Render ── */

  const renderPanel = (item: NpcListItem | null) => (
    <NpcExpandedPanel
      key="panel"
      npc={item}
      tabs={tabs}
      activeTab={activeTab}
      onTabSelect={(t) => guard(() => setTab(t))}
      racesData={racesData}
      onSaved={handleSaved}
      onCancel={() => guard(close)}
      onDirtyChange={handleDirtyChange}
      onDeleteRequest={() => item && setDeleteTarget(item.id)}
      onResurrect={() => item && handleResurrect(item.id)}
      resurrecting={resurrecting}
      onToggleReady={() => item && handleToggleReady(item)}
      readyPending={readyPending}
      scrollTargetRef={openRowRef}
    />
  );

  const showPinnedLoader = openId !== null && !openItem;

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-6">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">
        Управление НПС
      </h1>

      {/* Search + Filter + Create */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-3 sm:gap-4">
        <input
          className="input-underline flex-1 sm:min-w-[200px] sm:max-w-[320px]"
          placeholder="Поиск по имени..."
          value={query}
          onChange={(e) => { setQuery(e.target.value); setPage(1); }}
        />
        <select
          className="input-underline sm:max-w-[200px]"
          value={roleFilter}
          onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }}
        >
          <option value="" className="bg-site-dark text-white">Все роли</option>
          {NPC_ROLES.map((r) => (
            <option key={r.value} value={r.value} className="bg-site-dark text-white">
              {r.label}
            </option>
          ))}
        </select>
        <select
          className="input-underline sm:max-w-[200px]"
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
        >
          <option value="" className="bg-site-dark text-white">Все статусы</option>
          <option value="alive" className="bg-site-dark text-white">Жив</option>
          <option value="dead" className="bg-site-dark text-white">Мёртв</option>
        </select>
        <GeoFilterSelects {...geoSelectProps} />
        <ReadyFilterSelect
          value={readyFilter}
          onChange={(value) => {
            setReady(value);
            setPage(1);
          }}
        />
        <button
          className="btn-blue !text-base !px-6 !py-2 sm:ml-auto"
          onClick={() => guard(() => openNpc('new'))}
        >
          Создать НПС
        </button>
      </div>

      {/* NPC list */}
      <div className="gray-bg">
        <div className="flex flex-col gap-1 p-2 sm:p-3">
          {/* Pinned: create panel / NPC opened by link or off the current page */}
          {isNew && (
            <NpcRow npc={null} open onToggle={() => guard(close)} rowRef={openRowRef}>
              {renderPanel(null)}
            </NpcRow>
          )}
          {pinnedItem && (
            <NpcRow
              key={`pinned-${pinnedItem.id}`}
              npc={pinnedItem}
              open
              onToggle={() => toggleRow(pinnedItem.id)}
              badge="Открыт по ссылке"
              rowRef={openRowRef}
            >
              {renderPanel(pinnedItem)}
            </NpcRow>
          )}
          {showPinnedLoader && (
            <div className="flex items-center gap-2 px-4 py-3 text-white/50 text-sm">
              <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
              Загрузка НПС...
            </div>
          )}

          {loading && npcs.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
            </div>
          ) : (
            <div className={`flex flex-col gap-1 transition-opacity duration-200 ${loading ? 'opacity-60' : ''}`}>
              {npcs.map((npc) => {
                const isOpen = openId === npc.id;
                return (
                  <NpcRow
                    key={npc.id}
                    npc={npc}
                    open={isOpen}
                    onToggle={() => toggleRow(npc.id)}
                    rowRef={isOpen ? openRowRef : undefined}
                  >
                    {isOpen && renderPanel(npc)}
                  </NpcRow>
                );
              })}
              {!loading && npcs.length === 0 && (
                <p className="text-center text-white/50 text-sm py-8">НПС не найдены</p>
              )}
            </div>
          )}
        </div>

        {/* Pagination */}
        <AdminPagination
          page={page}
          totalPages={Math.max(1, Math.ceil(total / PAGE_SIZE))}
          onPageChange={(p) => setPage(p)}
          total={total}
          pageSize={PAGE_SIZE}
          className="px-4 py-3 border-t border-white/10"
        />
      </div>

      <ConfirmationModal
        isOpen={pendingLeave}
        title="Несохранённые изменения"
        message="Есть несохранённые изменения. Уйти без сохранения?"
        onConfirm={confirmLeave}
        onCancel={cancelLeave}
      />

      <ConfirmationModal
        isOpen={deleteTarget !== null}
        title="Удаление НПС"
        message="Удалить НПС? Это действие нельзя отменить."
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};

export default AdminNpcsPage;
