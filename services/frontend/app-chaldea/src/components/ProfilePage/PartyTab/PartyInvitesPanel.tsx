// FEAT-151 — incoming party invites panel (mock composition, design-system
// styles). Accept/decline flows preserved from FEAT-144.
import { CheckCircle, Swords } from 'lucide-react';
import type { IncomingInvite } from '../../../api/squads';
import PanelShell from '../PanelShell';
import EmptyState from '../shared/EmptyState';

interface PartyInvitesPanelProps {
  invites: IncomingInvite[];
  busy: boolean;
  onRespond: (partyId: number, accept: boolean) => void;
}

const PartyInvitesPanel = ({ invites, busy, onRespond }: PartyInvitesPanelProps) => {
  return (
    <PanelShell
      title="Приглашения"
      headerExtra={
        invites.length > 0 ? (
          <span className="font-mono tabular-nums text-xs font-medium text-site-red bg-site-red/[0.14] border border-site-red/30 rounded-full px-2.5 py-0.5">
            {invites.length}
          </span>
        ) : undefined
      }
      bodyClassName="flex flex-col gap-3 p-4 lg:p-5"
    >
      {invites.length === 0 ? (
        <EmptyState
          icon={<CheckCircle size={32} strokeWidth={1.4} className="text-white/20" />}
          message="Нет активных приглашений"
          className="py-10"
        />
      ) : (
        invites.map((inv) => (
          <div
            key={inv.party_id}
            className="flex flex-col gap-3 rounded-card bg-white/[0.03] border border-white/[0.08] p-4"
          >
            <div className="flex items-center gap-3">
              <div className="w-[42px] h-[42px] shrink-0 rounded-[10px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
                <div className="w-full h-full rounded-lg bg-site-dark flex items-center justify-center overflow-hidden">
                  {inv.party_avatar ? (
                    <img
                      src={inv.party_avatar}
                      alt={inv.party_name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <Swords size={18} strokeWidth={1.6} className="text-gold" />
                  )}
                </div>
              </div>
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
                className="flex-1 py-2 rounded-[9px] text-xs font-medium uppercase tracking-[0.04em] text-stat-energy bg-stat-energy/[0.14] border border-stat-energy/50 cursor-pointer hover:bg-stat-energy/[0.24] transition-colors duration-200 ease-site disabled:opacity-50"
              >
                Принять
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onRespond(inv.party_id, false)}
                className="px-4 py-2 rounded-[9px] text-xs font-medium uppercase tracking-[0.04em] text-white/60 border border-white/15 cursor-pointer hover:text-site-red hover:border-site-red transition-colors duration-200 ease-site disabled:opacity-50"
              >
                Отклонить
              </button>
            </div>
          </div>
        ))
      )}
    </PanelShell>
  );
};

export default PartyInvitesPanel;
