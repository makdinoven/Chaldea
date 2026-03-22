import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchActiveMobs,
  deleteActiveMob,
  spawnMob,
  setActiveMobsPage,
  setActiveMobsFilters,
  resetActiveMobsFilters,
  selectActiveMobs,
  selectActiveMobsTotal,
  selectActiveMobsPage,
  selectActiveMobsPageSize,
  selectActiveMobsLoading,
  selectActiveMobsError,
  selectActiveMobsFilters,
  selectMobsSaving,
} from '../../../redux/slices/mobsSlice';
import type { MobTemplateListItem } from '../../../api/mobs';

interface LocationOption {
  id: number;
  name: string;
}

const STATUS_LABELS: Record<string, string> = {
  alive: 'Жив',
  in_battle: 'В бою',
  dead: 'Мёртв',
};

const STATUS_COLORS: Record<string, string> = {
  alive: 'bg-green-500/30 text-green-300',
  in_battle: 'bg-yellow-500/30 text-yellow-300',
  dead: 'bg-white/10 text-white/40',
};

const TIER_COLORS: Record<string, string> = {
  normal: 'bg-white/20 text-white',
  elite: 'bg-purple-500/30 text-purple-300',
  boss: 'bg-site-red/30 text-site-red',
};

const TIER_LABELS: Record<string, string> = {
  normal: 'Обычный',
  elite: 'Элитный',
  boss: 'Босс',
};

const AdminActiveMobs = () => {
  const dispatch = useAppDispatch();
  const mobs = useAppSelector(selectActiveMobs);
  const total = useAppSelector(selectActiveMobsTotal);
  const page = useAppSelector(selectActiveMobsPage);
  const pageSize = useAppSelector(selectActiveMobsPageSize);
  const loading = useAppSelector(selectActiveMobsLoading);
  const error = useAppSelector(selectActiveMobsError);
  const filters = useAppSelector(selectActiveMobsFilters);
  const saving = useAppSelector(selectMobsSaving);

  // Spawn form state
  const [spawnFormOpen, setSpawnFormOpen] = useState(false);
  const [spawnTemplateId, setSpawnTemplateId] = useState<number | ''>('');
  const [spawnLocationId, setSpawnLocationId] = useState<number | ''>('');

  // Lookup data
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [templates, setTemplates] = useState<MobTemplateListItem[]>([]);

  const loadMobs = useCallback(() => {
    dispatch(fetchActiveMobs());
  }, [dispatch]);

  useEffect(() => {
    loadMobs();
  }, [loadMobs, page, filters]);

  useEffect(() => {
    // Fetch locations for filter/spawn
    axios.get<LocationOption[]>('/locations/locations/lookup')
      .then((res) => setLocations(res.data))
      .catch(() => {});

    // Fetch templates for filter/spawn
    axios.get('/characters/admin/mob-templates', { params: { page_size: 100 } })
      .then((res) => {
        const data = res.data;
        setTemplates(data.items ?? []);
      })
      .catch(() => {});
  }, []);

  const handleDelete = async (id: number) => {
    if (!window.confirm('Удалить активного моба?')) return;
    await dispatch(deleteActiveMob(id));
    loadMobs();
  };

  const handleSpawn = async () => {
    if (!spawnTemplateId || !spawnLocationId) {
      toast.error('Выберите шаблон и локацию');
      return;
    }
    try {
      await dispatch(spawnMob({
        mobTemplateId: Number(spawnTemplateId),
        locationId: Number(spawnLocationId),
      })).unwrap();
      setSpawnFormOpen(false);
      setSpawnTemplateId('');
      setSpawnLocationId('');
      loadMobs();
    } catch {
      // Error already shown by thunk
    }
  };

  const handleFilterChange = (
    field: 'locationId' | 'status' | 'templateId',
    value: string,
  ) => {
    if (field === 'locationId' || field === 'templateId') {
      dispatch(setActiveMobsFilters({
        [field]: value === '' ? null : Number(value),
      }));
    } else {
      dispatch(setActiveMobsFilters({ [field]: value }));
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString('ru-RU');
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Активные мобы
      </h1>

      {/* Filters + Manual spawn */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4">
          <select
            className="input-underline max-w-[200px]"
            value={filters.status}
            onChange={(e) => handleFilterChange('status', e.target.value)}
          >
            <option value="" className="bg-site-dark text-white">Все статусы</option>
            <option value="alive" className="bg-site-dark text-white">Жив</option>
            <option value="in_battle" className="bg-site-dark text-white">В бою</option>
            <option value="dead" className="bg-site-dark text-white">Мёртв</option>
          </select>

          <select
            className="input-underline max-w-[200px]"
            value={filters.locationId ?? ''}
            onChange={(e) => handleFilterChange('locationId', e.target.value)}
          >
            <option value="" className="bg-site-dark text-white">Все локации</option>
            {locations.map((loc) => (
              <option key={loc.id} value={loc.id} className="bg-site-dark text-white">
                {loc.name}
              </option>
            ))}
          </select>

          <select
            className="input-underline max-w-[200px]"
            value={filters.templateId ?? ''}
            onChange={(e) => handleFilterChange('templateId', e.target.value)}
          >
            <option value="" className="bg-site-dark text-white">Все шаблоны</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id} className="bg-site-dark text-white">
                {t.name}
              </option>
            ))}
          </select>

          <button
            onClick={() => dispatch(resetActiveMobsFilters())}
            className="text-sm text-white/50 hover:text-white transition-colors"
          >
            Сбросить
          </button>

          <button
            className="btn-blue !text-base !px-6 !py-2 sm:ml-auto"
            onClick={() => setSpawnFormOpen(!spawnFormOpen)}
          >
            Разместить моба
          </button>
        </div>

        {/* Spawn form */}
        {spawnFormOpen && (
          <div className="gray-bg p-4 flex flex-col sm:flex-row items-stretch sm:items-end gap-3 sm:gap-4">
            <label className="flex flex-col gap-1 flex-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Шаблон моба</span>
              <select
                className="input-underline"
                value={spawnTemplateId}
                onChange={(e) => setSpawnTemplateId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="" className="bg-site-dark text-white">Выберите шаблон...</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id} className="bg-site-dark text-white">
                    {t.name} (LVL {t.level})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 flex-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Локация</span>
              <select
                className="input-underline"
                value={spawnLocationId}
                onChange={(e) => setSpawnLocationId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="" className="bg-site-dark text-white">Выберите локацию...</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id} className="bg-site-dark text-white">
                    {loc.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={handleSpawn}
              disabled={saving || !spawnTemplateId || !spawnLocationId}
              className="btn-blue !text-base !px-6 !py-2 disabled:opacity-50"
            >
              {saving ? 'Размещение...' : 'Разместить'}
            </button>
            <button
              onClick={() => setSpawnFormOpen(false)}
              className="btn-line !w-auto !px-6"
            >
              Отмена
            </button>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="text-site-red text-sm">{error}</div>
      )}

      {/* Table */}
      <div className="gray-bg overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">ID</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Имя</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Тип</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Локация</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Статус</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Тип спавна</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Размещён</th>
                    <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {mobs.map((mob) => (
                    <tr key={mob.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200">
                      <td className="px-4 py-3 text-sm text-white/70">{mob.id}</td>
                      <td className="px-4 py-3 text-sm text-white">{mob.name || mob.template_name || `Моб #${mob.id}`}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${TIER_COLORS[mob.tier] || ''}`}>
                          {TIER_LABELS[mob.tier] || mob.tier}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-white/70">
                        {mob.location_name || `#${mob.location_id}`}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[mob.status] || ''}`}>
                          {STATUS_LABELS[mob.status] || mob.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-white/50">
                        {mob.spawn_type === 'manual' ? 'Ручной' : 'Случайный'}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/50">
                        {formatDate(mob.spawned_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleDelete(mob.id)}
                          className="text-sm text-site-red hover:text-white transition-colors duration-200"
                        >
                          Удалить
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden flex flex-col gap-3 p-3">
              {mobs.map((mob) => (
                <div key={mob.id} className="bg-white/[0.03] rounded-card p-4 flex flex-col gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-white text-sm font-medium">
                      {mob.name || mob.template_name || `Моб #${mob.id}`}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${TIER_COLORS[mob.tier] || ''}`}>
                      {TIER_LABELS[mob.tier] || mob.tier}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STATUS_COLORS[mob.status] || ''}`}>
                      {STATUS_LABELS[mob.status] || mob.status}
                    </span>
                  </div>
                  <div className="text-white/50 text-xs flex gap-3 flex-wrap">
                    <span>Локация: {mob.location_name || `#${mob.location_id}`}</span>
                    <span>{mob.spawn_type === 'manual' ? 'Ручной' : 'Случайный'}</span>
                  </div>
                  <div className="text-white/40 text-xs">
                    Размещён: {formatDate(mob.spawned_at)}
                  </div>
                  <button
                    onClick={() => handleDelete(mob.id)}
                    className="text-sm text-site-red hover:text-white transition-colors self-start"
                  >
                    Удалить
                  </button>
                </div>
              ))}
            </div>

            {mobs.length === 0 && (
              <p className="text-center text-white/50 text-sm py-8">Активные мобы не найдены</p>
            )}
          </>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-3">
          <button
            disabled={page <= 1}
            onClick={() => dispatch(setActiveMobsPage(page - 1))}
            className="text-sm text-white hover:text-site-blue transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Назад
          </button>
          <span className="text-sm text-white/50">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => dispatch(setActiveMobsPage(page + 1))}
            className="text-sm text-white hover:text-site-blue transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Вперёд
          </button>
        </div>
      )}
    </div>
  );
};

export default AdminActiveMobs;
