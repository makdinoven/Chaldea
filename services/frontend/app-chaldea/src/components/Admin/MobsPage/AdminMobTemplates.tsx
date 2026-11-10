import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import useDebounce from '../../../hooks/useDebounce';
import AdminPagination from '../AdminPagination/AdminPagination';
import ConfirmationModal from '../../ui/ConfirmationModal';
import {
  deleteMobTemplate,
  fetchMobTemplate,
  fetchMobTemplates,
  fillMobXp,
  setMobReady,
  type MobTemplateDetail,
  type MobTemplateListItem,
} from '../../../api/mobs';
import { apiErrorMessage } from '../../../api/errors';
import { usePanelUrlState } from '../ExpandableList/usePanelUrlState';
import { useDirtyGuard } from '../ExpandableList/useDirtyGuard';
import { useGeoFilter } from '../ExpandableList/useGeoFilter';
import { useReadyFilterUrlState } from '../ExpandableList/useReadyFilterUrlState';
import GeoFilterSelects from '../ExpandableList/GeoFilterSelects';
import ReadyFilterSelect from '../ExpandableList/ReadyFilterSelect';
import MobRow from './MobRow';
import MobExpandedPanel from './MobExpandedPanel';
import { availableMobTabs, isMobTabKey, type MobTabKey } from './mobTabKeys';

/* FEAT-210: mob templates as expandable plates; the open mob + tab live in `?mob=&tab=`,
   country / region / ready filters in `?country=&region=&ready=`. Search, tier and page are local. */

const PAGE_SIZE = 20;

const TIER_OPTIONS = [
  { value: '', label: 'Все типы' },
  { value: 'normal', label: 'Обычный' },
  { value: 'elite', label: 'Элитный' },
  { value: 'boss', label: 'Босс' },
] as const;

const readyFields = (r: {
  admin_ready?: boolean | null;
  admin_ready_at?: string | null;
  admin_ready_by?: string | null;
}) => ({
  admin_ready: !!r.admin_ready,
  admin_ready_at: r.admin_ready_at ?? null,
  admin_ready_by: r.admin_ready_by ?? null,
});

const detailToListItem = (d: MobTemplateDetail): MobTemplateListItem => ({
  id: d.id,
  name: d.name,
  tier: d.tier,
  level: d.level,
  avatar: d.avatar,
  xp_reward: d.xp_reward,
  gold_reward: d.gold_reward,
  respawn_enabled: d.respawn_enabled,
  respawn_seconds: d.respawn_seconds,
  spawn_count: d.spawn_locations?.length ?? 0,
  ...readyFields(d),
});

const AdminMobTemplates = () => {
  const [mobs, setMobs] = useState<MobTemplateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [listLoaded, setListLoaded] = useState(false);
  const [search, setSearch] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const debouncedSearch = useDebounce(search);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const {
    target: openTarget,
    tab: urlTab,
    rawTarget: rawMob,
    open: openMob,
    setTab,
    close,
    normalize,
  } = usePanelUrlState('mob', isMobTabKey, 'general');
  const [pinned, setPinned] = useState<MobTemplateListItem | null>(null);
  const { onDirtyChange: handleDirtyChange, guard, pendingLeave, confirmLeave, cancelLeave, resetDirty } =
    useDirtyGuard(openTarget !== null);
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [readyPending, setReadyPending] = useState(false);
  const openRowRef = useRef<HTMLDivElement>(null);

  /* ── Country / region / ready filters (URL) ── */

  const resetPage = useCallback(() => setPage(1), []);
  const { countryId, regionId, settled: filtersSettled, selectProps: geoSelectProps } = useGeoFilter({
    onChanged: resetPage,
  });
  const { ready: readyFilter, setReady } = useReadyFilterUrlState();

  // Requested only once the URL filters are validated (no request for a value about to be reset)
  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchMobTemplates({
        q: debouncedSearch || undefined,
        tier: tierFilter || undefined,
        country_id: countryId,
        region_id: regionId,
        ready: readyFilter,
        page,
        page_size: PAGE_SIZE,
      });
      setMobs(data.items.map((r) => ({ ...r, spawn_count: r.spawn_count ?? 0, ...readyFields(r) })));
      setTotal(data.total ?? 0);
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось загрузить список мобов'));
    } finally {
      setLoading(false);
      setListLoaded(true);
    }
  }, [debouncedSearch, tierFilter, countryId, regionId, readyFilter, page]);

  useEffect(() => {
    if (filtersSettled) fetchList();
  }, [fetchList, filtersSettled]);

  /* ── Open mob resolution ── */

  const openId = typeof openTarget === 'number' ? openTarget : null;
  const inList = openId !== null ? mobs.find((m) => m.id === openId) ?? null : null;
  const pinnedItem = openId !== null && !inList && pinned?.id === openId ? pinned : null;
  const openItem = inList ?? pinnedItem;
  const isNew = openTarget === 'new';

  const fetchPinned = useCallback(async (id: number): Promise<boolean> => {
    try {
      const detail = await fetchMobTemplate(id);
      setPinned(detailToListItem(detail));
      return true;
    } catch (err) {
      const notFound = axios.isAxiosError(err) && err.response?.status === 404;
      toast.error(notFound ? 'Моб не найден' : apiErrorMessage(err, 'Не удалось загрузить данные моба'));
      return false;
    }
  }, []);

  // Deep link / mob that left the current page → load it as a pinned plate
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

  const tabs = availableMobTabs(isNew);
  const activeTab: MobTabKey = urlTab && tabs.includes(urlTab) ? urlTab : 'general';

  // URL normalisation (replace): garbage `mob`, invalid / unavailable tab
  useEffect(() => {
    if (rawMob !== null && openTarget === null) {
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
  }, [rawMob, openTarget, isNew, urlTab, activeTab, openItem, normalize]);

  /* ── Actions ── */

  const toggleRow = (id: number) => {
    if (openId === id) guard(close);
    else guard(() => openMob(id));
  };

  const refreshAfterChange = (id: number) => {
    if (pinnedItem?.id === id) fetchPinned(id);
    fetchList();
  };

  const handleSaved = (id: number, created: boolean) => {
    if (created) normalize(id, 'general');
    refreshAfterChange(id);
  };

  const handleDelete = async () => {
    const id = deleteTarget;
    setDeleteTarget(null);
    if (id === null) return;
    try {
      await deleteMobTemplate(id);
      toast.success('Шаблон моба удалён');
      setMobs((prev) => prev.filter((m) => m.id !== id));
      setPinned((prev) => (prev?.id === id ? null : prev));
      resetDirty();
      if (openId === id) normalize(null);
      fetchList();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось удалить шаблон моба'));
    }
  };

  const handleToggleReady = async (item: MobTemplateListItem) => {
    setReadyPending(true);
    try {
      const res = await setMobReady(item.id, !item.admin_ready);
      const patchRow = (m: MobTemplateListItem): MobTemplateListItem =>
        m.id === res.id ? { ...m, ...readyFields(res) } : m;
      setMobs((prev) => prev.map(patchRow));
      setPinned((prev) => (prev ? patchRow(prev) : prev));
      toast.success(res.admin_ready ? 'Отмечено: готов' : 'Отметка «Готов» снята');
      // The mob may leave the filtered set — it then stays open as a pinned plate
      if (readyFilter !== null) fetchList();
    } catch (err) {
      toast.error(`Не удалось изменить отметку «Готов»: ${apiErrorMessage(err, 'ошибка сервера')}`);
    } finally {
      setReadyPending(false);
    }
  };

  // Mobs left with 0 XP get the default for their level and tier; hand-set values stay.
  const [filling, setFilling] = useState(false);
  const handleFillXp = async () => {
    setFilling(true);
    try {
      const { count } = await fillMobXp(true);
      if (count === 0) {
        toast('У всех мобов опыт уже заполнен');
        return;
      }
      if (!window.confirm(
        `Заполнить опыт ${count} мобам, у которых он сейчас 0?\n` +
        'Обычный — 20 + 6 × уровень, элитный ×3, босс ×10. Заданный вручную опыт не меняется.',
      )) return;
      const done = await fillMobXp(false);
      toast.success(`Опыт заполнен: ${done.count}`);
      fetchList();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось заполнить опыт мобов'));
    } finally {
      setFilling(false);
    }
  };

  /* ── Render ── */

  const renderPanel = (item: MobTemplateListItem | null) => (
    <MobExpandedPanel
      key="panel"
      mob={item}
      tabs={tabs}
      activeTab={activeTab}
      onTabSelect={(t) => guard(() => setTab(t))}
      onSaved={handleSaved}
      onCancel={() => guard(close)}
      onDirtyChange={handleDirtyChange}
      onDeleteRequest={() => item && setDeleteTarget(item.id)}
      onToggleReady={() => item && handleToggleReady(item)}
      readyPending={readyPending}
      onChanged={refreshAfterChange}
      scrollTargetRef={openRowRef}
    />
  );

  const showPinnedLoader = openId !== null && !openItem;

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-6">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">
        Управление мобами
      </h1>

      {/* Search + filters + actions */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-3 sm:gap-4">
        <input
          className="input-underline flex-1 sm:min-w-[200px] sm:max-w-[320px]"
          placeholder="Поиск по имени..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
        <select
          className="input-underline sm:max-w-[200px]"
          aria-label="Тип моба"
          value={tierFilter}
          onChange={(e) => { setTierFilter(e.target.value); setPage(1); }}
        >
          {TIER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-site-dark text-white">
              {opt.label}
            </option>
          ))}
        </select>
        <GeoFilterSelects {...geoSelectProps} />
        <ReadyFilterSelect
          value={readyFilter}
          onChange={(value) => {
            setReady(value);
            setPage(1);
          }}
        />
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:ml-auto">
          <button
            className="btn-line !w-auto !text-base !px-5 !py-2 disabled:opacity-40"
            onClick={() => void handleFillXp()}
            disabled={filling}
            title="Опыт по формуле всем мобам, у которых он 0: обычный 20 + 6 × уровень, элитный ×3, босс ×10"
          >
            {filling ? 'Заполнение...' : 'Заполнить опыт по формуле'}
          </button>
          <button className="btn-blue !text-base !px-6 !py-2" onClick={() => guard(() => openMob('new'))}>
            Создать моба
          </button>
        </div>
      </div>

      {/* Mob list */}
      <div className="gray-bg">
        <div className="flex flex-col gap-1 p-2 sm:p-3">
          {/* Pinned: create panel / mob opened by link or off the current page */}
          {isNew && (
            <MobRow mob={null} open onToggle={() => guard(close)} rowRef={openRowRef}>
              {renderPanel(null)}
            </MobRow>
          )}
          {pinnedItem && (
            <MobRow
              key={`pinned-${pinnedItem.id}`}
              mob={pinnedItem}
              open
              onToggle={() => toggleRow(pinnedItem.id)}
              badge="Открыт по ссылке"
              rowRef={openRowRef}
            >
              {renderPanel(pinnedItem)}
            </MobRow>
          )}
          {showPinnedLoader && (
            <div className="flex items-center gap-2 px-4 py-3 text-white/50 text-sm">
              <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
              Загрузка моба...
            </div>
          )}

          {loading && mobs.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
            </div>
          ) : (
            <div className={`flex flex-col gap-1 transition-opacity duration-200 ${loading ? 'opacity-60' : ''}`}>
              {mobs.map((mob) => {
                const isOpen = openId === mob.id;
                return (
                  <MobRow
                    key={mob.id}
                    mob={mob}
                    open={isOpen}
                    onToggle={() => toggleRow(mob.id)}
                    rowRef={isOpen ? openRowRef : undefined}
                  >
                    {isOpen && renderPanel(mob)}
                  </MobRow>
                );
              })}
              {!loading && mobs.length === 0 && (
                <p className="text-center text-white/50 text-sm py-8">Шаблоны мобов не найдены</p>
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
        title="Удаление моба"
        message="Удалить шаблон моба? Это действие нельзя отменить."
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};

export default AdminMobTemplates;
