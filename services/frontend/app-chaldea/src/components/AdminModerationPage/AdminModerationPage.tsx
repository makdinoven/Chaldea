import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';

interface PostPreview {
  post_id: number;
  content: string;
  character_name: string;
  character_id: number;
  created_at: string;
}

interface DeletionRequest {
  id: number;
  post_id: number;
  character_id: number;
  character_name: string;
  reason: string | null;
  status: string;
  created_at: string;
  post: PostPreview | null;
}

interface Report {
  id: number;
  post_id: number;
  reporter_character_id: number;
  reporter_character_name: string;
  reason: string | null;
  status: string;
  created_at: string;
  post: PostPreview | null;
}

type TabType = 'deletions' | 'reports';

const formatDate = (dateStr: string): string => {
  try {
    return new Date(dateStr).toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
};

const AdminModerationPage = () => {
  const [activeTab, setActiveTab] = useState<TabType>('deletions');
  const [deletionRequests, setDeletionRequests] = useState<DeletionRequest[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [loadingDeletions, setLoadingDeletions] = useState(false);
  const [loadingReports, setLoadingReports] = useState(false);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const fetchDeletionRequests = useCallback(async () => {
    setLoadingDeletions(true);
    try {
      const res = await axios.get<DeletionRequest[]>(
        `${BASE_URL}/locations/admin/moderation/deletion-requests`
      );
      setDeletionRequests(res.data);
    } catch {
      toast.error('Не удалось загрузить запросы на удаление');
    } finally {
      setLoadingDeletions(false);
    }
  }, []);

  const fetchReports = useCallback(async () => {
    setLoadingReports(true);
    try {
      const res = await axios.get<Report[]>(
        `${BASE_URL}/locations/admin/moderation/reports`
      );
      setReports(res.data);
    } catch {
      toast.error('Не удалось загрузить жалобы');
    } finally {
      setLoadingReports(false);
    }
  }, []);

  useEffect(() => {
    fetchDeletionRequests();
    fetchReports();
  }, [fetchDeletionRequests, fetchReports]);

  const handleDeletionAction = async (id: number, action: 'approve' | 'reject') => {
    setActionLoading(id);
    try {
      await axios.put(
        `${BASE_URL}/locations/admin/moderation/deletion-requests/${id}/review`,
        { action }
      );
      toast.success(action === 'approve' ? 'Пост удален' : 'Запрос отклонен');
      await fetchDeletionRequests();
    } catch {
      toast.error('Не удалось выполнить действие');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReportAction = async (id: number, action: 'resolve' | 'dismiss') => {
    setActionLoading(id);
    try {
      await axios.put(
        `${BASE_URL}/locations/admin/moderation/reports/${id}/review`,
        { action }
      );
      toast.success(action === 'resolve' ? 'Жалоба решена' : 'Жалоба отклонена');
      await fetchReports();
    } catch {
      toast.error('Не удалось выполнить действие');
    } finally {
      setActionLoading(null);
    }
  };

  const tabs: { key: TabType; label: string; count: number }[] = [
    { key: 'deletions', label: 'Запросы на удаление', count: deletionRequests.length },
    { key: 'reports', label: 'Жалобы', count: reports.length },
  ];

  const isLoading = activeTab === 'deletions' ? loadingDeletions : loadingReports;

  return (
    <div className="w-full max-w-[1240px] mx-auto">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em] mb-6 sm:mb-8">
        Модерация постов
      </h1>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-white/10">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors relative ${
              activeTab === tab.key
                ? 'text-gold'
                : 'text-white/50 hover:text-white/80'
            }`}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className="ml-2 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full bg-site-red/80 text-white text-[10px] px-1">
                {tab.count}
              </span>
            )}
            {activeTab === tab.key && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gold" />
            )}
          </button>
        ))}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <div className="w-8 h-8 border-4 border-white/20 border-t-gold rounded-full animate-spin" />
        </div>
      )}

      {/* Deletion Requests Tab */}
      {activeTab === 'deletions' && !loadingDeletions && (
        <div className="flex flex-col gap-3">
          {deletionRequests.length === 0 ? (
            <p className="text-white/50 text-sm py-8 text-center">
              Нет запросов на удаление
            </p>
          ) : (
            deletionRequests.map((req) => (
              <div
                key={req.id}
                className="bg-black/40 rounded-card p-4 flex flex-col gap-3"
              >
                {/* Post preview */}
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-white/40 text-xs">Пост от</span>
                    <span className="text-white text-xs font-medium">
                      {req.post?.character_name ?? 'Неизвестный'}
                    </span>
                    <span className="text-white/30 text-xs">
                      {req.post ? formatDate(req.post.created_at) : ''}
                    </span>
                  </div>
                  <p className="text-white/70 text-sm bg-black/30 rounded p-2 line-clamp-3 whitespace-pre-wrap break-words">
                    {req.post?.content ?? 'Пост удален'}
                  </p>
                </div>

                {/* Requester info */}
                <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 text-xs">
                  <span className="text-white/40">
                    Запросил: <span className="text-site-blue">{req.character_name}</span>
                  </span>
                  <span className="text-white/30">{formatDate(req.created_at)}</span>
                </div>

                {/* Reason */}
                {req.reason && (
                  <div className="text-xs">
                    <span className="text-white/40">Причина: </span>
                    <span className="text-white/70">{req.reason}</span>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 mt-1">
                  <button
                    onClick={() => handleDeletionAction(req.id, 'approve')}
                    disabled={actionLoading === req.id}
                    className="btn-blue text-xs px-4 py-1.5 disabled:opacity-50"
                  >
                    {actionLoading === req.id ? '...' : 'Одобрить'}
                  </button>
                  <button
                    onClick={() => handleDeletionAction(req.id, 'reject')}
                    disabled={actionLoading === req.id}
                    className="btn-line text-xs px-4 py-1.5 disabled:opacity-50"
                  >
                    Отклонить
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Reports Tab */}
      {activeTab === 'reports' && !loadingReports && (
        <div className="flex flex-col gap-3">
          {reports.length === 0 ? (
            <p className="text-white/50 text-sm py-8 text-center">
              Нет жалоб
            </p>
          ) : (
            reports.map((report) => (
              <div
                key={report.id}
                className="bg-black/40 rounded-card p-4 flex flex-col gap-3"
              >
                {/* Post preview */}
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-white/40 text-xs">Пост от</span>
                    <span className="text-white text-xs font-medium">
                      {report.post?.character_name ?? 'Неизвестный'}
                    </span>
                    <span className="text-white/30 text-xs">
                      {report.post ? formatDate(report.post.created_at) : ''}
                    </span>
                  </div>
                  <p className="text-white/70 text-sm bg-black/30 rounded p-2 line-clamp-3 whitespace-pre-wrap break-words">
                    {report.post?.content ?? 'Пост удален'}
                  </p>
                </div>

                {/* Reporter info */}
                <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 text-xs">
                  <span className="text-white/40">
                    Пожаловался: <span className="text-site-blue">{report.reporter_character_name}</span>
                  </span>
                  <span className="text-white/30">{formatDate(report.created_at)}</span>
                </div>

                {/* Reason */}
                {report.reason && (
                  <div className="text-xs">
                    <span className="text-white/40">Причина: </span>
                    <span className="text-white/70">{report.reason}</span>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 mt-1">
                  <button
                    onClick={() => handleReportAction(report.id, 'resolve')}
                    disabled={actionLoading === report.id}
                    className="btn-blue text-xs px-4 py-1.5 disabled:opacity-50"
                  >
                    {actionLoading === report.id ? '...' : 'Решено'}
                  </button>
                  <button
                    onClick={() => handleReportAction(report.id, 'dismiss')}
                    disabled={actionLoading === report.id}
                    className="btn-line text-xs px-4 py-1.5 disabled:opacity-50"
                  >
                    Отклонить
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default AdminModerationPage;
