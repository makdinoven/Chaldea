import { useEffect, useState, useCallback, type ReactNode } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import { GATE_LABEL, GATE_STYLE } from '../pages/LocationPage/gateConstants';
import { formatServerDateTime } from '../../utils/serverDate';
/**
 * Posts are stored as TipTap **HTML**, so the moderation queues have to render
 * them as markup — a moderator judging a report must see the post exactly as
 * the players saw it, not the tags mixed into the words.
 *
 * The content is player-written, which makes this the one place stored XSS
 * would land on an admin's screen. It goes through the shared post policy in
 * `utils/sanitizePostHtml.ts` — the same function the public renderer
 * (`pages/LocationPage/PostCard.tsx`) uses, so the two can never drift apart.
 * **Never loosen it and never bypass it.**
 */
import { sanitizePostHtml } from '../../utils/sanitizePostHtml';
import { useAppSelector } from '../../redux/store';
import { selectPermissions } from '../../redux/slices/userSlice';
import { hasPermission } from '../../utils/permissions';
import PostVersionHistoryModal from '../pages/LocationPage/PostVersionHistoryModal';

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
  /**
   * Deletion requests and reports carry a reason; gate requests do not
   * (`PostGateRequestRead` has no such field), hence optional.
   */
  reason?: string | null;
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

/** One gate the player asks to add retroactively. Mirrors the `gates` JSON. */
interface RequestedGate {
  action_type: string;
  targets?: (number | null)[] | null;
}

/**
 * One target of a requested gate, resolved server-side to a real name and a
 * current state (`crud._resolve_gate_targets`, FEAT-159 section 3.9).
 *
 * Resolution is **enrichment, never validation**: a target that could not be
 * found comes back with `name: null` and `state: "цель не найдена"` instead of
 * the request being auto-rejected. The admin must see that uncertainty — it is
 * the whole reason a human reviews this queue.
 */
interface ResolvedTarget {
  /** `null` when the gate was filed without a target at all. */
  id: number | null;
  /** `null` when the lookup found nothing — render the id and the state. */
  name: string | null;
  state: string;
}

/**
 * Mirrors the backend `PostGateRequestRead` (locations-service
 * `app/schemas.py`), verified against the live `/openapi.json`. Same card
 * fields as the other two queues plus the gate payload.
 */
interface GateRequest extends ModerationItem {
  /** The character the gate would be granted to. */
  character_id: number;
  /** The location the gate would be granted on. */
  location_id: number;
  gates: RequestedGate[];
  post_edited_at: string | null;
  post_location_name: string | null;
  /** `{action_type: [...]}` — empty when enrichment could not run at all. */
  targets_resolved: Record<string, ResolvedTarget[]>;
}

type TabType = 'deletions' | 'reports' | 'gates';

/**
 * `pvp` exists server-side (`crud.GATED_POST_TYPES`) but is not offered in the
 * post editor, so `GATE_LABEL` has no entry for it. The moderation queue can
 * receive any gate type, so it needs the full table plus a loud fallback for
 * anything added later on the backend alone.
 */
const GATE_REQUEST_LABEL: Record<string, string> = {
  ...GATE_LABEL,
  pvp: 'Нападение на игрока',
};

const gateLabel = (actionType: string): string =>
  GATE_REQUEST_LABEL[actionType] ?? `Намерение «${actionType}»`;

const formatDate = (dateStr: string | null | undefined): string =>
  formatServerDateTime(dateStr, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

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

/**
 * The Russian `detail` the server sends for the *business* outcomes of a gate
 * review — 400 «Заявка уже рассмотрена» and the three 409s of FEAT-159 T9
 * («Пост удалён…», «Персонаж покинул локацию…», «Текст поста больше не
 * оплачивает эти действия…»). These are not failures of the request, they are
 * the world having moved between the request and the review, and the server's
 * wording says exactly what moved — so it must reach the admin verbatim.
 *
 * Deliberately limited to 400/409: 401/403/404/5xx keep `errorMessage`'s
 * wording, which is Russian, whereas FastAPI's own details there are not
 * (e.g. «Not authenticated»).
 */
const serverDetail = (error: unknown): string | null => {
  if (!axios.isAxiosError(error)) return null;
  const status = error.response?.status;
  if (status !== 400 && status !== 409) return null;
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' && detail.trim() ? detail : null;
};

/** A decided/stale row must disappear from the queue, so the list is refetched. */
const isStaleQueueError = (error: unknown): boolean => {
  if (!axios.isAxiosError(error)) return false;
  const status = error.response?.status;
  return status === 400 || status === 404 || status === 409;
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
  /**
   * Show the post in full instead of clamping it to three lines. Gate requests
   * need it: the admin's decision *is* a judgement of the text — whether it
   * really voices the intent being asked for — and a clamped preview would
   * hide the part that decides it.
   */
  showFullPost?: boolean;
  /** Queue-specific detail rendered between the reason and the actions. */
  extra?: ReactNode;
}

const ModerationCard = ({
  item,
  requesterCaption,
  approveLabel,
  rejectLabel,
  busy,
  onApprove,
  onReject,
  showFullPost = false,
  extra,
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
          /* Rendered as HTML (sanitised — see `sanitizePostHtml`) and styled
             like the public post body: `prose-rules` + gold quote rule. Bold
             and italic deliberately carry no colour of their own (FEAT-157),
             so an author's own colour is shown, not overridden. */
          <div
            className={`text-white/[0.88] text-sm bg-black/30 rounded p-2 whitespace-pre-wrap break-words prose-rules
              [&_blockquote]:border-l-2 [&_blockquote]:border-gold/50 [&_blockquote]:pl-3.5 [&_blockquote]:my-2 [&_blockquote]:italic [&_blockquote]:text-white/75
              [&_em]:italic [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 ${
                showFullPost ? 'max-h-64 overflow-y-auto gold-scrollbar' : 'line-clamp-3'
              }`}
            dangerouslySetInnerHTML={{ __html: sanitizePostHtml(item.post_content ?? '') }}
          />
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

      {/* Queue-specific detail (gate requests: the intents being asked for) */}
      {extra}

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

/** A target the backend could not resolve to a real entity. */
const isUnresolved = (target: ResolvedTarget): boolean => target.name === null;

interface GateRequestDetailsProps {
  item: GateRequest;
  /**
   * FEAT-160 (T9): opens the post's edit history. `undefined` when the viewer
   * does not hold `posts:history` — the link is then never rendered.
   */
  onShowHistory?: (postId: number) => void;
}

/**
 * The part of a gate-request card an admin actually decides on: which intents
 * are being asked for, and what each named target really is right now.
 *
 * FEAT-159 section 3.9 ruled that target resolution **shows, never blocks** —
 * there is no reliable way to know when a target entered a location, so a
 * human judges. That makes the failure case load-bearing: an unresolved target
 * is rendered loudly («цель не найдена»), never as a silent blank, because the
 * uncertainty is exactly what the admin is here to weigh.
 */
const GateRequestDetails = ({ item, onShowHistory }: GateRequestDetailsProps) => {
  // The payload may list the same action_type more than once; merge so each
  // intent is shown once, the way the server charges for it.
  const actionTypes: string[] = [];
  const rawTargets: Record<string, (number | null)[]> = {};
  for (const gate of item.gates ?? []) {
    const type = gate.action_type;
    if (!actionTypes.includes(type)) actionTypes.push(type);
    rawTargets[type] = [...(rawTargets[type] ?? []), ...(gate.targets ?? [])];
  }

  return (
    <div className="flex flex-col gap-2 border-t border-white/10 pt-3">
      {/* Where the gate would be granted, and whether the post was edited */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap gap-1 sm:gap-3 text-xs">
        <span className="text-white/40 break-words">
          Локация:{' '}
          <span className="text-white/70">
            {item.post_location_name ?? `#${item.location_id}`}
          </span>
        </span>
        {item.post_edited_at && (
          <span className="text-white/40 break-words">
            Пост изменён:{' '}
            <span className="text-white/70">{formatDate(item.post_edited_at)}</span>
            {/* FEAT-160 (T9): this line is exactly where an admin needs to know
                WHAT changed — the queue has been stating that a post was edited
                and offering no way to look. The post row must still exist
                (`post_id !== null`), since the history cascades away with it. */}
            {onShowHistory && item.post_id !== null && (
              <>
                {' · '}
                <button
                  type="button"
                  onClick={() => onShowHistory(item.post_id as number)}
                  className="text-site-blue hover:text-white transition-colors duration-200 ease-site break-words"
                >
                  Показать историю правок
                </button>
              </>
            )}
          </span>
        )}
      </div>

      <p className="text-white/40 text-xs">Запрошенные намерения:</p>

      {actionTypes.length === 0 ? (
        <p className="text-site-red text-xs">
          В заявке не указано ни одного намерения
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {actionTypes.map((type) => {
            const style = GATE_STYLE[type];
            const resolved = item.targets_resolved?.[type];
            // No enrichment for this intent at all (the lookup itself failed) —
            // fall back to the bare ids rather than showing nothing.
            const targets: ResolvedTarget[] =
              resolved && resolved.length > 0
                ? resolved
                : (rawTargets[type] ?? []).map((id) => ({
                    id: id ?? null,
                    name: null,
                    state: id === null ? 'цель не указана' : 'не удалось определить цель',
                  }));

            return (
              <div
                key={type}
                className="flex flex-col gap-1.5 bg-black/30 rounded p-2"
              >
                <span
                  className={`inline-flex items-center gap-1.5 text-xs font-medium self-start px-2 py-1 rounded border ${
                    style?.activeCls ?? 'border-white/20 text-white/70'
                  }`}
                >
                  {style?.icon && <span aria-hidden="true">{style.icon}</span>}
                  {gateLabel(type)}
                </span>

                {targets.length === 0 ? (
                  <span className="text-site-red text-xs">Цели не указаны</span>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {targets.map((target, index) => (
                      <li
                        key={`${type}-${target.id ?? 'none'}-${index}`}
                        className="flex flex-col sm:flex-row sm:items-baseline sm:gap-2 text-xs break-words"
                      >
                        <span
                          className={
                            isUnresolved(target) ? 'text-site-red' : 'text-white'
                          }
                        >
                          {target.name ??
                            (target.id === null ? 'Цель не указана' : `Цель #${target.id}`)}
                        </span>
                        <span
                          className={
                            isUnresolved(target) ? 'text-site-red/70' : 'text-white/40'
                          }
                        >
                          {target.state}
                          {target.name !== null && target.id !== null && ` · #${target.id}`}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const AdminModerationPage = () => {
  /**
   * FEAT-160 (T9): the history link is gated on the `posts:history`
   * PERMISSION, not on a role. The permission is granted to no role
   * (user-service migration 0029): admins hold it implicitly, moderators — who
   * are the usual inhabitants of this queue — do not, and the user can delegate
   * it to one named person through `user_permissions` with no deploy. A
   * `role === 'admin'` check would hide the link from exactly that person while
   * the server answered them 200.
   */
  const permissions = useAppSelector(selectPermissions);
  const canViewPostHistory = hasPermission(permissions, 'posts:history');
  /** Post whose history modal is open (null = closed). */
  const [historyPostId, setHistoryPostId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('deletions');
  const [deletionRequests, setDeletionRequests] = useState<DeletionRequest[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [gateRequests, setGateRequests] = useState<GateRequest[]>([]);
  const [loadingDeletions, setLoadingDeletions] = useState(false);
  const [loadingReports, setLoadingReports] = useState(false);
  const [loadingGates, setLoadingGates] = useState(false);
  const [deletionsError, setDeletionsError] = useState<string | null>(null);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [gatesError, setGatesError] = useState<string | null>(null);
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

  const fetchGateRequests = useCallback(async () => {
    setLoadingGates(true);
    try {
      const res = await axios.get<GateRequest[]>(
        `${BASE_URL}/locations/admin/moderation/gate-requests`
      );
      setGateRequests(res.data);
      setGatesError(null);
    } catch (error) {
      const message = errorMessage(error, 'Не удалось загрузить заявки на намерения');
      setGateRequests([]);
      setGatesError(message);
      toast.error(message);
    } finally {
      setLoadingGates(false);
    }
  }, []);

  useEffect(() => {
    fetchDeletionRequests();
    fetchReports();
    fetchGateRequests();
  }, [fetchDeletionRequests, fetchReports, fetchGateRequests]);

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

  /**
   * Approve or reject a retro-added gate (FEAT-159, T9).
   *
   * Approval re-checks the world server-side and can legitimately refuse with a
   * 409 — the post was deleted, the character left the location, or the text was
   * shortened below what the gates cost. Those are outcomes, not bugs, so the
   * server's own Russian `detail` is shown verbatim and the queue is refetched:
   * the row's fate has already changed and a stale card must not stay clickable.
   */
  const handleGateAction = async (id: number, action: 'approve' | 'reject') => {
    setActionLoading(id);
    try {
      await axios.put(
        `${BASE_URL}/locations/admin/moderation/gate-requests/${id}/review`,
        { action }
      );
      toast.success(
        action === 'approve'
          ? 'Заявка одобрена, намерение активно'
          : 'Заявка отклонена, намерение не выдано'
      );
      await fetchGateRequests();
    } catch (error) {
      toast.error(
        serverDetail(error) ?? errorMessage(error, 'Не удалось рассмотреть заявку')
      );
      if (isStaleQueueError(error)) await fetchGateRequests();
    } finally {
      setActionLoading(null);
    }
  };

  const tabs: { key: TabType; label: string; count: number }[] = [
    { key: 'deletions', label: 'Запросы на удаление', count: deletionRequests.length },
    { key: 'reports', label: 'Жалобы', count: reports.length },
    { key: 'gates', label: 'Заявки на намерения', count: gateRequests.length },
  ];

  const isLoading =
    activeTab === 'deletions'
      ? loadingDeletions
      : activeTab === 'reports'
        ? loadingReports
        : loadingGates;
  const activeError =
    activeTab === 'deletions'
      ? deletionsError
      : activeTab === 'reports'
        ? reportsError
        : gatesError;
  const retryActiveTab =
    activeTab === 'deletions'
      ? fetchDeletionRequests
      : activeTab === 'reports'
        ? fetchReports
        : fetchGateRequests;

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

      {/* Gate Requests Tab — retro-added intents awaiting a human decision */}
      {activeTab === 'gates' && !loadingGates && !gatesError && (
        <div className="flex flex-col gap-3">
          {gateRequests.length === 0 ? (
            <p className="text-white/50 text-sm py-8 text-center">
              Нет заявок на намерения
            </p>
          ) : (
            gateRequests.map((req) => (
              <ModerationCard
                key={req.id}
                item={req}
                requesterCaption="Запросил"
                approveLabel="Одобрить"
                rejectLabel="Отклонить"
                busy={actionLoading === req.id}
                showFullPost
                extra={
                  <GateRequestDetails
                    item={req}
                    onShowHistory={canViewPostHistory ? setHistoryPostId : undefined}
                  />
                }
                onApprove={() => handleGateAction(req.id, 'approve')}
                onReject={() => handleGateAction(req.id, 'reject')}
              />
            ))
          )}
        </div>
      )}

      {/* FEAT-160: the same self-contained modal the location feed opens — it
          takes a post id and fetches its own history, so nothing is duplicated. */}
      {historyPostId !== null && (
        <PostVersionHistoryModal
          postId={historyPostId}
          onClose={() => setHistoryPostId(null)}
        />
      )}
    </div>
  );
};

export default AdminModerationPage;
