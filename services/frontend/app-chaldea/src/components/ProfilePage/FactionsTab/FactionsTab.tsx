// FEAT-205 — «Фракции» profile tab: the character's factions (rank, points, next rank with ✓/✗,
// warning countdown, leave with the cooldown / burn spelled out), applications, former factions,
// and the faction journal. Private data (owner / staff); the public part is the passport block.
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { Flag } from 'lucide-react';
import {
  FACTION_APPLICATION_STATUS_LABEL,
  cancelFactionApplication,
  fetchMyFactions,
  leaveFaction,
  type FactionApplicationBrief,
  type FactionMembership,
  type FactionPrivateView,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { formatRelativeTime } from '../../../utils/serverDate';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import EmptyState from '../shared/EmptyState';
import ErrorState from '../shared/ErrorState';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';
import ProfileCard from '../shared/ProfileCard';
import SectionHeader from '../shared/SectionHeader';
import FactionMembershipCard, { FormerMembershipRow } from './FactionMembershipCard';
import FactionHistory from './FactionHistory';
import LeaveFactionDialog from './LeaveFactionDialog';
import DonateFactionDialog from './DonateFactionDialog';
import { ModifierList } from './FactionPassives';

interface FactionsTabProps {
  characterId: number;
}

const TAB_MOTION = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: 'easeOut' as const },
};

const ApplicationRow = ({
  app,
  busy,
  onCancel,
}: {
  app: FactionApplicationBrief;
  busy: boolean;
  onCancel: (app: FactionApplicationBrief) => void;
}) => (
  <ProfileCard className="p-3 flex flex-col gap-1" variant={app.status === 'rejected' ? 'danger' : 'default'}>
    <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
      <span className="text-white text-sm break-words min-w-0">{app.faction_name ?? 'Фракция'}</span>
      <span
        className={`text-xs ${
          app.status === 'pending' ? 'text-gold-light' : app.status === 'approved' ? 'text-stat-energy' : 'text-site-red'
        }`}
      >
        {FACTION_APPLICATION_STATUS_LABEL[app.status] ?? app.status}
      </span>
    </div>
    {app.reject_reason && <p className="text-white/60 text-xs break-words">Причина: {app.reject_reason}</p>}
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-white/35 text-[11px]">
        {app.created_at ? `подана ${formatRelativeTime(app.created_at, { style: 'long', yesterday: true })}` : ''}
      </span>
      {app.status === 'pending' && (
        <button
          type="button"
          disabled={busy}
          onClick={() => onCancel(app)}
          className="text-xs text-white/50 hover:text-site-red transition-colors duration-200 ease-site disabled:opacity-50"
        >
          Отозвать
        </button>
      )}
    </div>
  </ProfileCard>
);

const FactionsTab = ({ characterId }: FactionsTabProps) => {
  const [view, setView] = useState<FactionPrivateView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [leaving, setLeaving] = useState<FactionMembership | null>(null);
  const [donating, setDonating] = useState<FactionMembership | null>(null);
  const [busy, setBusy] = useState(false);
  const [showFormer, setShowFormer] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setView(await fetchMyFactions(characterId));
    } catch (err) {
      setError(apiErrorMessage(err, 'Не удалось загрузить фракции'));
    } finally {
      setLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = () => {
    void load();
    setHistoryKey((k) => k + 1);
  };

  const confirmLeave = async () => {
    if (!leaving) return;
    setBusy(true);
    try {
      const res = await leaveFaction(characterId, leaving.faction.id);
      toast.success(`Вы покинули фракцию «${leaving.faction.name}». Осталось очков: ${res.points_after}`);
      setLeaving(null);
      refresh();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось покинуть фракцию'));
    } finally {
      setBusy(false);
    }
  };

  const cancelApplication = async (app: FactionApplicationBrief) => {
    setBusy(true);
    try {
      await cancelFactionApplication(characterId, app.id);
      toast.success('Заявка отозвана');
      refresh();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось отозвать заявку'));
    } finally {
      setBusy(false);
    }
  };

  const active = view?.memberships.filter((m) => m.status === 'active') ?? [];
  const former = view?.memberships.filter((m) => m.status !== 'active') ?? [];
  const applications = view?.applications ?? [];

  const allLink = (
    <Link to="/factions" className="btn-line !text-xs !py-1 !px-3 whitespace-nowrap">
      Все фракции
    </Link>
  );

  return (
    <motion.div {...TAB_MOTION} className="flex flex-col lg:flex-row gap-4 lg:gap-6">
      <PanelShell
        title="Фракции"
        icon={<Flag size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
        headerExtra={
          <span className="flex items-center gap-2">
            {view && active.length > 0 && <PanelCounter>{active.length}</PanelCounter>}
            {allLink}
          </span>
        }
        className={`lg:flex-1 ${PANEL_DESKTOP_HEIGHT_CLASS}`}
      >
        {loading && !view ? (
          <LoadingState />
        ) : error && !view ? (
          <ErrorState message={error} onRetry={() => void load()} />
        ) : (
          <div className="flex flex-col gap-5">
            {error && <p className="text-site-red text-xs">{error}</p>}

            {active.length === 0 ? (
              <EmptyState
                icon={<Flag size={32} strokeWidth={1.5} className="text-white/20" />}
                message="Вы пока не состоите ни в одной фракции"
                hint="Ордена, гильдии и храмы мира принимают тех, кто подходит под их условия."
                action={
                  <Link to="/factions" className="btn-blue !text-sm">
                    Открыть каталог фракций
                  </Link>
                }
              />
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                {active.map((m) => (
                  <FactionMembershipCard key={m.membership_id} membership={m} onLeave={setLeaving} onDonate={setDonating} />
                ))}
              </div>
            )}

            {/* FEAT-207: all faction passives together (only worth showing with several factions) */}
            {active.filter((m) => (m.passives ?? []).length > 0).length > 1 &&
              Object.keys(view?.passive_total ?? {}).length > 0 && (
              <ProfileCard className="p-3 flex flex-col gap-1.5">
                <p className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Все пассивки фракций в бою</p>
                <ModifierList modifiers={view?.passive_total ?? {}} />
              </ProfileCard>
            )}

            {applications.length > 0 && (
              <div className="flex flex-col gap-2">
                <SectionHeader title="Заявки" />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {applications.map((a) => (
                    <ApplicationRow key={a.id} app={a} busy={busy} onCancel={(x) => void cancelApplication(x)} />
                  ))}
                </div>
              </div>
            )}

            {former.length > 0 && (
              <div className="flex flex-col gap-2">
                <SectionHeader
                  title="Бывшие фракции"
                  extra={
                    <button
                      type="button"
                      className="text-xs text-white/50 hover:text-site-blue transition-colors duration-200 ease-site"
                      onClick={() => setShowFormer((v) => !v)}
                    >
                      {showFormer ? 'Скрыть' : `Показать (${former.length})`}
                    </button>
                  }
                />
                {showFormer && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {former.map((m) => (
                      <FormerMembershipRow key={m.membership_id} membership={m} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </PanelShell>

      <FactionHistory characterId={characterId} reloadKey={historyKey} />

      <LeaveFactionDialog
        membership={leaving}
        settings={view?.settings ?? null}
        busy={busy}
        onCancel={() => setLeaving(null)}
        onConfirm={() => void confirmLeave()}
      />

      <DonateFactionDialog
        characterId={characterId}
        membership={donating}
        onClose={() => setDonating(null)}
        onDone={refresh}
      />
    </motion.div>
  );
};

export default FactionsTab;
