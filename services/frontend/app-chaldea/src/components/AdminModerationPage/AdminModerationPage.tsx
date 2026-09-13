import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';

/**
 * Flat shape returned by the moderation queues. Mirrors the backend
 * `PostDeletionRequestRead` / `PostReportRead` (locations-service
 * `app/schemas.py`) field-for-field — snake_case, no nested `post` object.
 *
 * `post_id` is nullable since migration 037: deleting a post no longer
 * cascades the moderation row away, so a decided row survives its post
 * (FEAT-158). When the post row is gone, every `post_*` field comes back
 * `null` at once.
 */
interface ModerationItem {
  id: number;
  /** `null` when the post has already been deleted. */
  post_id: number | null;
  /** The account that asked for the action — a user, not a character. */
  user_id: number;
  reason: string | null;
  status: string;
  created_at: string;
  reviewed_at: string | null;
  post_content: string | null;
  post_character_id: number | null;
  post_location_id: number | null;
  /** `null` if the post is gone OR the character name could not be resolved. */
  post_character_name: string | null;
  post_created_at: string | null;
  /** `null` if the username could not be resolved. */
  requester_username: string | null;
}

type DeletionRequest = ModerationItem;
type Report = ModerationItem;

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

/**
 * The post row is gone (deleted, or orphaned by an earlier decision).
 * Distinct from "the post exists but its author name did not resolve".
 */
const isPostMissing = (item: ModerationItem): boolean =>
  item.post_id === null || item.post_content === null;

/** Post author. A resolved-to-null name still means the post exists. */
const postAuthorLabel = (item: ModerationItem): string => {
  if (item.post_character_name) return item.post_character_name;
  if (item.post_character_id !== null) return `Персонаж #${item.post_character_id}`;
  return 'Неизвестный персонаж';
};

/** Who filed the request/report — always a user account. */
const requesterLabel = (item: ModerationItem): string =>
  item.requester_username ?? `Пользователь #${item.user_id}`;

const errorMessage = (error: unknown, fallback: string): string => {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if (status === 401) return 'Сессия истекла. Войдите заново.';
    if (status === 403) return 'Недостаточно прав для раздела модерации';
    if (status === 404) return 'Заявка не найдена — возможно, её уже рассмотрели.';
    if (status && status >= 500) return 'Сервер модерации недоступен. Попробуйте позже.';
    if (!error.response) return 'Нет связи с сервером. Проверьте подключение.';
  }
  return fallback;
};

interface ModerationCardProps {
  item: ModerationItem;
  /** «Запросил» for deletion requests, «Пожаловался» for reports. */
  requesterCaption: string;
  approveLabel: string;
  rejectLabel: string;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}

const ModerationCard = ({
  item,
  requesterCaption,
  approveLabel,
  rejectLabel,
  busy,
  onApprove,
  onReject,
}: ModerationCardProps) => {
  const postMissing = isPostMissing(item);

  return (
    <div className="bg-black/40 rounded-card p-3 sm:p-4 flex flex-col gap-3">
      {/* Post preview */}
      <div className="flex flex-col gap-1">
        {/* The author line is hidden entirely when there is no post left. */}
        {!postMissing && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white/40 text-xs">Пост от</span>
            <span className="text-white text-xs font-medium break-words">
              {postAuthorLabel(item)}
            </span>
            {item.post_created_at && (
              <span className="text-white/30 text-xs">
                {formatDate(item.post_created_at)}
              </span>
            )}
          </div>
        )}
        {postMissing ? (
          <p className="text-white/40 text-sm italic bg-black/30 rounded p-2">
            Пост уже удалён
          </p>
        ) : (
          <p className="text-white/70 text-sm bg-black/30 rounded p-2 line-clamp-3 whitespace-pre-wrap break-words">
            {item.post_content}
          </p>
        )}
      </div>

      {/* Requester info — a user account, not a character */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 text-xs">
        <span className="text-white/40 break-words">
          {requesterCaption}: <span className="text-site-blue">{requesterLabel(item)}</span>
        </span>
        <span className="text-white/30">{formatDate(item.created_at)}</span>
      </div>

      {/* Reason */}
      {item.reason && (
        <div className="text-xs">
          <span className="text-white/40">Причина: </span>
          <span className="text-white/70 break-words">{item.reason}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2 mt-1">
        <button
          onClick={onApprove}
          disabled={busy}
          className="btn-blue text-xs px-4 py-1.5 disabled:opacity-50"
        >
          {busy ? '...' : approveLabel}
        </button>
        <button
          onClick={onReject}
          disabled={busy}
          className="btn-line text-xs px-4 py-1.5 disabled:opacity-50"
        >
          {rejectLabel}
        </button>
      </div>
    </div>
  );
};

const AdminModerationPage = () => {
  const [activeTab, setActiveTab] = useState<TabType>('deletions');
  const [deletionRequests, setDeletionRequests] = useState<DeletionRequest[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [loadingDeletions, setLoadingDeletions] = useState(false);
  const [loadingReports, setLoadingReports] = useState(false);
  const [deletionsError, setDeletionsError] = useState<string | null>(null);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const fetchDeletionRequests = useCallback(async () => {
    setLoadingDeletions(true);
    try {
      const res = await axios.get<DeletionRequest[]>(
        `${BASE_URL}/locations/admin/moderation/deletion-requests`
      );
      setDeletionRequests(res.data);
      setDeletionsError(null);
    } catch (error) {
      const message = errorMessage(error, 'Не удалось загрузить запросы на удаление');
      setDeletionRequests([]);
      setDeletionsError(message);
      toast.error(message);
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
      setReportsError(null);
    } catch (error) {
      const message = errorMessage(error, 'Не удалось загрузить жалобы');
      setReports([]);
      setReportsError(message);
      toast.error(message);
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
      toast.success(action === 'approve' ? 'Запрос одобрен, пост удалён' : 'Запрос отклонён');
      await fetchDeletionRequests();
    } catch (error) {
      toast.error(errorMessage(error, 'Не удалось выполнить действие'));
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
      toast.success(action === 'resolve' ? 'Жалоба решена, пост удалён' : 'Жалоба отклонена');
      await fetchReports();
    } catch (error) {
      toast.error(errorMessage(error, 'Не удалось выполнить действие'));
    } finally {
      setActionLoading(null);
    }
  };

  const tabs: { key: TabType; label: string; count: number }[] = [
    { key: 'deletions', label: 'Запросы на удаление', count: deletionRequests.length },
    { key: 'reports', label: 'Жалобы', count: reports.length },
  ];

  const isLoading = activeTab === 'deletions' ? loadingDeletions : loadingReports;
  const activeError = activeTab === 'deletions' ? deletionsError : reportsError;
  const retryActiveTab =
    activeTab === 'deletions' ? fetchDeletionRequests : fetchReports;

  return (
    <div className="w-full max-w-container mx-auto">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em] mb-6 sm:mb-8">
        Модерация постов
      </h1>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-white/10 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 sm:px-4 py-2.5 text-xs sm:text-sm font-medium transition-colors relative whitespace-nowrap ${
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

      {/* Fetch error — never leave a failed load looking like an empty queue */}
      {!isLoading && activeError && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 bg-black/40 rounded-card p-3 sm:p-4 mb-4">
          <p className="text-site-red text-sm break-words">{activeError}</p>
          <button
            onClick={retryActiveTab}
            className="btn-line text-xs px-4 py-1.5 self-start sm:self-auto sm:ml-auto"
          >
            Повторить
          </button>
        </div>
      )}

      {/* Deletion Requests Tab */}
      {activeTab === 'deletions' && !loadingDeletions && !deletionsError && (
        <div className="flex flex-col gap-3">
          {deletionRequests.length === 0 ? (
            <p className="text-white/50 text-sm py-8 text-center">
              Нет запросов на удаление
            </p>
          ) : (
            deletionRequests.map((req) => (
              <ModerationCard
                key={req.id}
                item={req}
                requesterCaption="Запросил"
                approveLabel="Одобрить"
                rejectLabel="Отклонить"
                busy={actionLoading === req.id}
                onApprove={() => handleDeletionAction(req.id, 'approve')}
                onReject={() => handleDeletionAction(req.id, 'reject')}
              />
            ))
          )}
        </div>
      )}

      {/* Reports Tab */}
      {activeTab === 'reports' && !loadingReports && !reportsError && (
        <div className="flex flex-col gap-3">
          {reports.length === 0 ? (
            <p className="text-white/50 text-sm py-8 text-center">
              Нет жалоб
            </p>
          ) : (
            reports.map((report) => (
              <ModerationCard
                key={report.id}
                item={report}
                requesterCaption="Пожаловался"
                approveLabel="Решено"
                rejectLabel="Отклонить"
                busy={actionLoading === report.id}
                onApprove={() => handleReportAction(report.id, 'resolve')}
                onReject={() => handleReportAction(report.id, 'dismiss')}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default AdminModerationPage;
