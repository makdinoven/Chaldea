import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import type { AdminSession } from '../../../api/dungeons';

const STATUS_LABELS: Record<string, string> = {
  forming: 'Формируется',
  active: 'Активна',
  completed: 'Завершена',
  escaped: 'Побег',
  wiped: 'Вайп',
};

const STATUS_COLORS: Record<string, string> = {
  forming: 'bg-site-blue/30 text-site-blue',
  active: 'bg-green-500/30 text-green-400',
  completed: 'bg-white/20 text-white',
  escaped: 'bg-gold/30 text-gold',
  wiped: 'bg-site-red/30 text-site-red',
};

const MEMBER_STATUS_COLORS: Record<string, string> = {
  alive: 'text-green-400',
  dead: 'text-site-red',
  disconnected: 'text-white/30',
};

const AdminDungeonSessions = () => {
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('');
  const [cleanupId, setCleanupId] = useState<number | null>(null);
  const [cleaning, setCleaning] = useState(false);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (filter) params.status = filter;
      const { data } = await axios.get<AdminSession[]>('/dungeons/admin/sessions', { params });
      setSessions(data);
    } catch {
      setError('Не удалось загрузить сессии');
      toast.error('Ошибка загрузки сессий');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleCleanup = async (sessionId: number) => {
    setCleaning(true);
    try {
      const { data } = await axios.delete(`/dungeons/admin/sessions/${sessionId}`);
      toast.success(data.message || 'Сессия завершена');
      setCleanupId(null);
      loadSessions();
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) && err.response?.data?.detail
        ? err.response.data.detail
        : 'Ошибка при завершении сессии';
      toast.error(msg);
    } finally {
      setCleaning(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Filter */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="flex gap-2 flex-wrap">
          {['', 'forming', 'active', 'completed', 'escaped', 'wiped'].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors duration-200 ${
                filter === s
                  ? 'bg-gold/30 text-gold'
                  : 'bg-white/10 text-white/50 hover:text-white hover:bg-white/20'
              }`}
            >
              {s ? STATUS_LABELS[s] || s : 'Активные'}
            </button>
          ))}
        </div>
        <button
          onClick={loadSessions}
          className="text-sm text-white/50 hover:text-site-blue transition-colors sm:ml-auto"
        >
          Обновить
        </button>
      </div>

      {error && <div className="text-site-red text-sm">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : sessions.length === 0 ? (
        <p className="text-center text-white/50 text-sm py-8">Сессий не найдено</p>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden sm:block gray-bg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">ID</th>
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Подземелье</th>
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Статус</th>
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Лидер</th>
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Участники</th>
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Начало</th>
                  <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Действия</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200">
                    <td className="px-4 py-3 text-sm text-white/70">#{s.id}</td>
                    <td className="px-4 py-3 text-sm text-white">
                      {s.dungeon_name || `Данж #${s.dungeon_id}`}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[s.status] || 'bg-white/20 text-white'}`}>
                        {STATUS_LABELS[s.status] || s.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-white/70">
                      Персонаж #{s.leader_character_id}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1.5">
                        {s.members.map((m) => (
                          <span
                            key={m.character_id}
                            className={`text-xs ${MEMBER_STATUS_COLORS[m.status] || 'text-white/50'}`}
                            title={`User #${m.user_id}, ${m.status}`}
                          >
                            #{m.character_id}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-white/50">
                      {formatDate(s.started_at || s.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {['forming', 'active'].includes(s.status) && (
                        <button
                          onClick={() => setCleanupId(s.id)}
                          className="text-sm text-site-red hover:text-white transition-colors duration-200"
                        >
                          Завершить
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="sm:hidden flex flex-col gap-3">
            {sessions.map((s) => (
              <div key={s.id} className="gray-bg rounded-card p-4 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <span className="text-white text-sm font-medium">
                    #{s.id} — {s.dungeon_name || `Данж #${s.dungeon_id}`}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STATUS_COLORS[s.status] || ''}`}>
                    {STATUS_LABELS[s.status] || s.status}
                  </span>
                </div>
                <div className="flex flex-wrap gap-3 text-xs text-white/50">
                  <span>Лидер: #{s.leader_character_id}</span>
                  <span>{formatDate(s.started_at || s.created_at)}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {s.members.map((m) => (
                    <span
                      key={m.character_id}
                      className={`text-xs px-2 py-0.5 rounded-full bg-white/10 ${MEMBER_STATUS_COLORS[m.status] || 'text-white/50'}`}
                    >
                      #{m.character_id} ({m.status})
                    </span>
                  ))}
                </div>
                {['forming', 'active'].includes(s.status) && (
                  <button
                    onClick={() => setCleanupId(s.id)}
                    className="text-sm text-site-red hover:text-white transition-colors self-start"
                  >
                    Принудительно завершить
                  </button>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* Cleanup confirmation modal */}
      {cleanupId !== null && (
        <div className="modal-overlay">
          <div className="modal-content gold-outline gold-outline-thick">
            <h2 className="gold-text text-2xl uppercase mb-4">Подтверждение</h2>
            <p className="text-white mb-6">
              Принудительно завершить сессию #{cleanupId}? Все участники будут освобождены, инвентарь удалён.
            </p>
            <div className="flex gap-4">
              <button
                className="btn-blue"
                onClick={() => handleCleanup(cleanupId)}
                disabled={cleaning}
              >
                {cleaning ? 'Завершение...' : 'Завершить'}
              </button>
              <button
                className="btn-line"
                onClick={() => setCleanupId(null)}
                disabled={cleaning}
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

export default AdminDungeonSessions;
