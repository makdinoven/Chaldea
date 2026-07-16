import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchDungeons,
  deleteDungeon,
  selectDungeons,
  selectDungeonsLoading,
  selectDungeonsError,
} from '../../../redux/slices/dungeonAdminSlice';

const STABILITY_LABELS: Record<string, string> = {
  static: 'Статичный',
  unstable: 'Нестабильный',
  chaotic: 'Хаотичный',
};

const STABILITY_COLORS: Record<string, string> = {
  static: 'bg-white/20 text-white',
  unstable: 'bg-gold/30 text-gold',
  chaotic: 'bg-site-red/30 text-site-red',
};

const DANGER_LABELS: Record<string, string> = {
  safe: 'Безопасный',
  deadly: 'Смертельный',
};

const DANGER_COLORS: Record<string, string> = {
  safe: 'bg-white/20 text-white',
  deadly: 'bg-site-red/30 text-site-red',
};

const AdminDungeonList = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const dungeons = useAppSelector(selectDungeons);
  const loading = useAppSelector(selectDungeonsLoading);
  const error = useAppSelector(selectDungeonsError);

  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  const loadDungeons = useCallback(() => {
    dispatch(fetchDungeons());
  }, [dispatch]);

  useEffect(() => {
    loadDungeons();
  }, [loadDungeons]);

  const handleDelete = async (id: number) => {
    await dispatch(deleteDungeon(id));
    setDeleteConfirmId(null);
  };

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-6">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Управление подземельями
      </h1>

      {/* Actions */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4">
        <button
          className="btn-line !text-base !px-6 !py-2"
          onClick={() => navigate('/admin/dungeons/sessions')}
        >
          Активные сессии
        </button>
        <button
          className="btn-blue !text-base !px-6 !py-2 sm:ml-auto"
          onClick={() => navigate('/admin/dungeons/create')}
        >
          Создать подземелье
        </button>
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
            <div className="hidden sm:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Название</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Стабильность</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Опасность</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Локация ID</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Активно</th>
                    <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {dungeons.map((dungeon) => (
                    <tr key={dungeon.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200">
                      <td className="px-4 py-3 text-sm text-white">{dungeon.name}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STABILITY_COLORS[dungeon.stability_type] || ''}`}>
                          {STABILITY_LABELS[dungeon.stability_type] || dungeon.stability_type}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${DANGER_COLORS[dungeon.danger_level] || ''}`}>
                          {DANGER_LABELS[dungeon.danger_level] || dungeon.danger_level}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-white/70">{dungeon.location_id}</td>
                      <td className="px-4 py-3 text-sm">
                        <span className={dungeon.is_active ? 'text-green-400' : 'text-white/30'}>
                          {dungeon.is_active ? 'Да' : 'Нет'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col items-end gap-1.5">
                          <button
                            onClick={() => navigate(`/admin/dungeons/${dungeon.id}`)}
                            className="text-sm text-gold hover:text-white transition-colors duration-200"
                          >
                            Комнаты и коридоры
                          </button>
                          <button
                            onClick={() => navigate(`/admin/dungeons/${dungeon.id}/edit`)}
                            className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                          >
                            Редактировать
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(dungeon.id)}
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
              {dungeons.map((dungeon) => (
                <div key={dungeon.id} className="bg-white/[0.03] rounded-card p-4 flex flex-col gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex flex-col gap-1 min-w-0">
                      <span className="text-white text-sm font-medium truncate">
                        {dungeon.name}
                      </span>
                      <span className="text-white/50 text-xs">Локация: {dungeon.location_id}</span>
                    </div>
                    <div className="flex flex-col items-end gap-1 ml-auto shrink-0">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STABILITY_COLORS[dungeon.stability_type] || ''}`}>
                        {STABILITY_LABELS[dungeon.stability_type] || dungeon.stability_type}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${DANGER_COLORS[dungeon.danger_level] || ''}`}>
                        {DANGER_LABELS[dungeon.danger_level] || dungeon.danger_level}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-4 text-xs text-white/50">
                    <span>{dungeon.is_active ? 'Активно' : 'Неактивно'}</span>
                  </div>
                  <div className="flex gap-3 flex-wrap">
                    <button
                      onClick={() => navigate(`/admin/dungeons/${dungeon.id}`)}
                      className="text-sm text-gold hover:text-white transition-colors"
                    >
                      Комнаты и коридоры
                    </button>
                    <button
                      onClick={() => navigate(`/admin/dungeons/${dungeon.id}/edit`)}
                      className="text-sm text-white hover:text-site-blue transition-colors"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => setDeleteConfirmId(dungeon.id)}
                      className="text-sm text-site-red hover:text-white transition-colors"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {dungeons.length === 0 && (
              <p className="text-center text-white/50 text-sm py-8">Подземелья не найдены</p>
            )}
          </>
        )}
      </div>

      {/* Delete confirmation modal */}
      {deleteConfirmId !== null && (
        <div className="modal-overlay">
          <div className="modal-content gold-outline gold-outline-thick">
            <h2 className="gold-text text-2xl uppercase mb-4">Подтверждение</h2>
            <p className="text-white mb-6">
              Удалить подземелье? Все комнаты и коридоры будут удалены. Это действие нельзя отменить.
            </p>
            <div className="flex gap-4">
              <button
                className="btn-blue"
                onClick={() => handleDelete(deleteConfirmId)}
              >
                Удалить
              </button>
              <button
                className="btn-line"
                onClick={() => setDeleteConfirmId(null)}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDungeonList;
