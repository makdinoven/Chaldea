import { useEffect, useState, useCallback } from 'react';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchMobTemplates,
  deleteMobTemplate,
  setSearch,
  setTierFilter,
  setPage,
  selectMobTemplates,
  selectMobTemplatesTotal,
  selectMobTemplatesPage,
  selectMobTemplatesPageSize,
  selectMobTemplatesSearch,
  selectMobTemplatesTierFilter,
  selectMobTemplatesListLoading,
  selectMobTemplatesListError,
} from '../../../redux/slices/mobsSlice';
import useDebounce from '../../../hooks/useDebounce';
import AdminMobTemplateForm from './AdminMobTemplateForm';
import AdminMobDetail from './AdminMobDetail';

const TIER_OPTIONS = [
  { value: '', label: 'Все типы' },
  { value: 'normal', label: 'Обычный' },
  { value: 'elite', label: 'Элитный' },
  { value: 'boss', label: 'Босс' },
] as const;

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

const AdminMobTemplates = () => {
  const dispatch = useAppDispatch();
  const templates = useAppSelector(selectMobTemplates);
  const total = useAppSelector(selectMobTemplatesTotal);
  const page = useAppSelector(selectMobTemplatesPage);
  const pageSize = useAppSelector(selectMobTemplatesPageSize);
  const search = useAppSelector(selectMobTemplatesSearch);
  const tierFilter = useAppSelector(selectMobTemplatesTierFilter);
  const loading = useAppSelector(selectMobTemplatesListLoading);
  const error = useAppSelector(selectMobTemplatesListError);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);

  const debouncedSearch = useDebounce(search);

  const loadTemplates = useCallback(() => {
    dispatch(fetchMobTemplates());
  }, [dispatch]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates, debouncedSearch, tierFilter, page]);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    dispatch(setSearch(e.target.value));
  };

  const handleTierChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    dispatch(setTierFilter(e.target.value));
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Удалить шаблон моба? Это действие нельзя отменить.')) return;
    dispatch(deleteMobTemplate(id));
  };

  const handleEdit = (id: number) => {
    setEditingId(id);
    setFormOpen(true);
  };

  const handleCreate = () => {
    setEditingId(null);
    setFormOpen(true);
  };

  const handleFormClose = () => {
    setFormOpen(false);
    setEditingId(null);
    loadTemplates();
  };

  const handleDetailOpen = (id: number) => {
    setDetailId(id);
  };

  const handleDetailClose = () => {
    setDetailId(null);
    loadTemplates();
  };

  const totalPages = Math.ceil(total / pageSize);

  // Show detail view
  if (detailId !== null) {
    return <AdminMobDetail templateId={detailId} onClose={handleDetailClose} />;
  }

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Управление мобами
      </h1>

      {/* Search + Filter + Create */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4">
        <input
          className="input-underline flex-1 max-w-[320px]"
          placeholder="Поиск по имени..."
          value={search}
          onChange={handleSearchChange}
        />
        <select
          className="input-underline max-w-[200px]"
          value={tierFilter}
          onChange={handleTierChange}
        >
          {TIER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-site-dark text-white">
              {opt.label}
            </option>
          ))}
        </select>
        <button className="btn-blue !text-base !px-6 !py-2 sm:ml-auto" onClick={handleCreate}>
          Создать моба
        </button>
      </div>

      {/* Form modal */}
      {formOpen && (
        <AdminMobTemplateForm
          editingId={editingId}
          onClose={handleFormClose}
        />
      )}

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
            <div className="hidden sm:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">ID</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Имя</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Тип</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Уровень</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Опыт</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Золото</th>
                    <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {templates.map((mob) => (
                    <tr key={mob.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200">
                      <td className="px-4 py-3 text-sm text-white/70">{mob.id}</td>
                      <td className="px-4 py-3 text-sm text-white">
                        <button
                          onClick={() => handleDetailOpen(mob.id)}
                          className="hover:text-site-blue transition-colors duration-200"
                        >
                          {mob.name}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${TIER_COLORS[mob.tier] || ''}`}>
                          {TIER_LABELS[mob.tier] || mob.tier}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-white/70">{mob.level}</td>
                      <td className="px-4 py-3 text-sm text-white/70">{mob.xp_reward}</td>
                      <td className="px-4 py-3 text-sm text-gold">{mob.gold_reward}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col items-end gap-1.5">
                          <button
                            onClick={() => handleDetailOpen(mob.id)}
                            className="text-sm text-site-blue hover:text-white transition-colors duration-200"
                          >
                            Подробнее
                          </button>
                          <button
                            onClick={() => handleEdit(mob.id)}
                            className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                          >
                            Редактировать
                          </button>
                          <button
                            onClick={() => handleDelete(mob.id)}
                            className="text-sm text-site-red hover:text-white transition-colors duration-200"
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="sm:hidden flex flex-col gap-3 p-3">
              {templates.map((mob) => (
                <div key={mob.id} className="bg-white/[0.03] rounded-card p-4 flex flex-col gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex flex-col gap-1 min-w-0">
                      <button
                        onClick={() => handleDetailOpen(mob.id)}
                        className="text-white text-sm font-medium truncate text-left hover:text-site-blue transition-colors"
                      >
                        {mob.name}
                      </button>
                      <span className="text-white/50 text-xs">LVL {mob.level}</span>
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ml-auto shrink-0 ${TIER_COLORS[mob.tier] || ''}`}>
                      {TIER_LABELS[mob.tier] || mob.tier}
                    </span>
                  </div>
                  <div className="flex gap-4 text-xs text-white/50">
                    <span>Опыт: {mob.xp_reward}</span>
                    <span className="text-gold">Золото: {mob.gold_reward}</span>
                  </div>
                  <div className="flex gap-3 flex-wrap">
                    <button
                      onClick={() => handleDetailOpen(mob.id)}
                      className="text-sm text-site-blue hover:text-white transition-colors"
                    >
                      Подробнее
                    </button>
                    <button
                      onClick={() => handleEdit(mob.id)}
                      className="text-sm text-white hover:text-site-blue transition-colors"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => handleDelete(mob.id)}
                      className="text-sm text-site-red hover:text-white transition-colors"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {templates.length === 0 && (
              <p className="text-center text-white/50 text-sm py-8">Шаблоны мобов не найдены</p>
            )}
          </>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-3">
          <button
            disabled={page <= 1}
            onClick={() => dispatch(setPage(page - 1))}
            className="text-sm text-white hover:text-site-blue transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Назад
          </button>
          <span className="text-sm text-white/50">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => dispatch(setPage(page + 1))}
            className="text-sm text-white hover:text-site-blue transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Вперёд
          </button>
        </div>
      )}
    </div>
  );
};

export default AdminMobTemplates;
