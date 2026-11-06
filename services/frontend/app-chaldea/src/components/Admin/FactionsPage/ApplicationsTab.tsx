import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { XCircle } from 'lucide-react';
import {
  FACTION_APPLICATION_STATUS_LABEL,
  FACTION_LIMITS,
  adminApproveApplication,
  adminListApplications,
  adminRejectApplication,
  type FactionApplicationAdmin,
  type FactionApplicationStatus,
  type FactionPage,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { formatServerDateTime } from '../../../utils/serverDate';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { RequirementRow } from '../../ProfilePage/FactionsTab/FactionMembershipCard';
import { FIELD, LABEL, OPTION, useFactionOptions } from './adminShared';

const PAGE_SIZE = 20;
const STATUSES: (FactionApplicationStatus | 'all')[] = ['pending', 'approved', 'rejected', 'cancelled', 'all'];

export const Pager = ({ page, total, pageSize, onPage }: { page: number; total: number; pageSize: number; onPage: (p: number) => void }) => {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-3 text-sm">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className="text-white/70 hover:text-site-blue disabled:opacity-30">
        ← Назад
      </button>
      <span className="text-white/50 font-mono tabular-nums">
        {page} / {pages}
      </span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)} className="text-white/70 hover:text-site-blue disabled:opacity-30">
        Вперёд →
      </button>
    </div>
  );
};

/** Applications to invite-only factions: approve (conditions are re-checked) or reject with a reason. */
const ApplicationsTab = ({ canManage }: { canManage: boolean }) => {
  const { factions } = useFactionOptions();
  const [status, setStatus] = useState<FactionApplicationStatus | 'all'>('pending');
  const [factionId, setFactionId] = useState<number | ''>('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<FactionPage<FactionApplicationAdmin> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState<FactionApplicationAdmin | null>(null);
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await adminListApplications({ status, faction_id: factionId || null, page, page_size: PAGE_SIZE }));
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить заявки'));
    }
  }, [status, factionId, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const approve = async (app: FactionApplicationAdmin) => {
    setBusy(true);
    try {
      await adminApproveApplication(app.id);
      toast.success(`${app.character.name ?? 'Персонаж'} принят во фракцию «${app.faction.name ?? ''}»`);
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось одобрить заявку'), { duration: 6000 });
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!rejecting) return;
    if (reason.length > FACTION_LIMITS.reasonMax) {
      toast.error(`Причина: до ${FACTION_LIMITS.reasonMax} символов`);
      return;
    }
    setBusy(true);
    try {
      await adminRejectApplication(rejecting.id, reason.trim() || null);
      toast.success('Заявка отклонена');
      setRejecting(null);
      setReason('');
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось отклонить заявку'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <label className="flex flex-col gap-1 sm:w-56">
          <span className={LABEL}>Статус</span>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as FactionApplicationStatus | 'all');
              setPage(1);
            }}
            className={FIELD}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s} className={OPTION}>
                {s === 'all' ? 'Все' : FACTION_APPLICATION_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 sm:w-72">
          <span className={LABEL}>Фракция</span>
          <select
            value={factionId}
            onChange={(e) => {
              setFactionId(e.target.value ? Number(e.target.value) : '');
              setPage(1);
            }}
            className={FIELD}
          >
            <option value="" className={OPTION}>Все фракции</option>
            {factions.map((f) => (
              <option key={f.id} value={f.id} className={OPTION}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="text-site-red text-sm">{error}</p>}
      {!data && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {data?.items.length === 0 && <p className="text-white/50 text-sm">Заявок нет.</p>}

      <div className="flex flex-col gap-3">
        {data?.items.map((app) => (
          <div key={app.id} className="flex flex-col gap-3 bg-white/[0.03] border border-white/[0.06] rounded-card p-3 sm:p-4">
            <div className="flex flex-col sm:flex-row sm:items-start gap-2 sm:gap-4">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <span className="w-10 h-10 rounded-full overflow-hidden bg-black/40 shrink-0">
                  {app.character.avatar && <img src={app.character.avatar} alt="" className="w-full h-full object-cover" />}
                </span>
                <div className="min-w-0">
                  <Link to={`/admin/characters/${app.character.id}`} className="site-link text-sm break-words">
                    {app.character.name ?? `#${app.character.id}`}
                  </Link>
                  <p className="text-white/50 text-xs">
                    ур. {app.character.level ?? '—'}
                    {app.character.class_name ? ` · ${app.character.class_name}` : ''} → <span className="text-gold">{app.faction.name}</span>
                  </p>
                </div>
              </div>
              <div className="text-xs text-white/45 sm:text-right shrink-0">
                <p className={app.status === 'pending' ? 'text-gold-light' : app.status === 'approved' ? 'text-stat-energy' : 'text-white/60'}>
                  {FACTION_APPLICATION_STATUS_LABEL[app.status]}
                </p>
                <p>{formatServerDateTime(app.created_at)}</p>
              </div>
            </div>
            {app.message && <p className="text-white/80 text-sm whitespace-pre-wrap break-words border-l-2 border-gold/30 pl-3">{app.message}</p>}
            {app.reject_reason && <p className="text-white/60 text-xs break-words">Причина отказа: {app.reject_reason}</p>}
            {app.conditions.length > 0 && (
              <ul className="flex flex-col gap-1">
                {app.conditions.map((c, i) => (
                  <RequirementRow key={`${c.type}-${i}`} met={c.met} text={c.text} />
                ))}
              </ul>
            )}
            {canManage && app.status === 'pending' && (
              <div className="flex flex-col sm:flex-row gap-2">
                <button type="button" disabled={busy} onClick={() => void approve(app)} className="btn-blue !w-full sm:!w-auto !text-sm !px-5 !py-1.5 disabled:opacity-50">
                  Одобрить
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setReason('');
                    setRejecting(app);
                  }}
                  className="btn-line !w-full sm:!w-auto !text-sm !px-5 !py-1.5 disabled:opacity-50"
                >
                  Отклонить
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
      {data && <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} />}

      <ModalShell
        open={rejecting !== null}
        onClose={() => setRejecting(null)}
        title="Отклонить заявку"
        icon={<XCircle size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
        size="sm"
        dismissible={!busy}
        footer={
          <>
            <button type="button" className="btn-line w-full sm:w-auto" onClick={() => setRejecting(null)} disabled={busy}>
              Отмена
            </button>
            <button type="button" className="btn-blue w-full sm:w-auto disabled:opacity-50" onClick={() => void reject()} disabled={busy}>
              Отклонить
            </button>
          </>
        }
      >
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Причина (увидит игрок, необязательно)</span>
          <textarea value={reason} maxLength={FACTION_LIMITS.reasonMax} onChange={(e) => setReason(e.target.value)} rows={3} className="textarea-bordered text-sm" />
        </label>
      </ModalShell>
    </div>
  );
};

export default ApplicationsTab;
