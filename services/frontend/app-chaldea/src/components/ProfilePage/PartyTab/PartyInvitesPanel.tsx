// FEAT-151 — incoming party invites panel (mock composition, design-system
// styles). Accept/decline flows preserved from FEAT-144.
// FEAT-166 — PanelCounter / ProfileCard / GoldIconFrame alignment.
import { CheckCircle, Mail, Swords } from 'lucide-react';
import type { IncomingInvite } from '../../../api/squads';
import PanelShell from '../PanelShell';
import EmptyState from '../shared/EmptyState';
import PanelCounter from '../shared/PanelCounter';
import ProfileCard from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';

interface PartyInvitesPanelProps {
  invites: IncomingInvite[];
  busy: boolean;
  onRespond: (partyId: number, accept: boolean) => void;
  /** Extra classes for the PanelShell (height caps from PartyTab) */
  className?: string;
}

const PartyInvitesPanel = ({
  invites,
  busy,
  onRespond,
  className = '',
}: PartyInvitesPanelProps) => {
  return (
    <PanelShell
      title="Приглашения"
      icon={<Mail size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      headerExtra={
        invites.length > 0 ? <PanelCounter>{invites.length}</PanelCounter> : undefined
      }
      className={className}
      bodyClassName="flex-1 min-h-0 flex flex-col gap-3 p-4 lg:p-5 lg:overflow-y-auto gold-scrollbar-wide"
    >
      {invites.length === 0 ? (
        <EmptyState
          icon={<CheckCircle size={32} strokeWidth={1.4} className="text-white/20" />}
          message="Нет активных приглашений"
          className="py-10"
        />
      ) : (
        invites.map((inv) => (
          <ProfileCard key={inv.party_id} className="flex flex-col gap-3 p-4 shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              <GoldIconFrame
                size={42}
                shape="square"
                src={inv.party_avatar}
                alt={inv.party_name}
                fallback={<Swords size={18} strokeWidth={1.6} className="text-gold" />}
              />
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="text-white text-sm font-medium truncate">{inv.party_name}</span>
                <span className="text-[11px] text-white/50 truncate">
                  Лидер: {inv.leader_name ?? `#${inv.leader_character_id}`}
                </span>
              </div>
            </div>
            <div className="flex gap-2.5">
              <button
                type="button"
                disabled={busy}
                onClick={() => onRespond(inv.party_id, true)}
                className="flex-1 min-h-[36px] py-2 rounded-[9px] text-xs font-medium uppercase tracking-[0.04em] text-stat-energy bg-stat-energy/[0.14] border border-stat-energy/50 cursor-pointer hover:bg-stat-energy/[0.24] transition-colors duration-200 ease-site disabled:opacity-50"
              >
                Принять
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onRespond(inv.party_id, false)}
                className="min-h-[36px] px-4 py-2 rounded-[9px] text-xs font-medium uppercase tracking-[0.04em] text-white/60 border border-white/15 cursor-pointer hover:text-site-red hover:border-site-red transition-colors duration-200 ease-site disabled:opacity-50"
              >
                Отклонить
              </button>
            </div>
          </ProfileCard>
        ))
      )}
    </PanelShell>
  );
};

export default PartyInvitesPanel;
