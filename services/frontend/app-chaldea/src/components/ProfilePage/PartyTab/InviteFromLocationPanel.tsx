// FEAT-151 — leader-only «Пригласить с локации» panel (mock composition,
// design-system styles). Players come from getPlayersOnLocation (FEAT-144).
// FEAT-166 — toolbar (location) + scroll area, ProfileCard rows, GoldIconFrame.
import { MapPin, Plus, UserPlus, Users } from 'lucide-react';
import type { PlayerOnLocation } from '../../../api/squads';
import PanelShell from '../PanelShell';
import EmptyState from '../shared/EmptyState';
import PanelCounter from '../shared/PanelCounter';
import PanelToolbar from '../shared/PanelToolbar';
import PanelScrollArea from '../shared/PanelScrollArea';
import ProfileCard from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';

interface InviteFromLocationPanelProps {
  /** Name of the viewer's current location (null when unknown) */
  locationName: string | null;
  /** Whether the viewer's character is on a location at all */
  hasLocation: boolean;
  players: PlayerOnLocation[];
  busy: boolean;
  onInvite: (characterId: number) => void;
  /** Extra classes for the PanelShell (height from PartyTab) */
  className?: string;
}

const InviteFromLocationPanel = ({
  locationName,
  hasLocation,
  players,
  busy,
  onInvite,
  className = '',
}: InviteFromLocationPanelProps) => {
  return (
    <PanelShell
      title="Пригласить с локации"
      icon={<UserPlus size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      headerExtra={
        hasLocation && players.length > 0 ? (
          <PanelCounter>{players.length}</PanelCounter>
        ) : undefined
      }
      className={className}
      bodyClassName="flex-1 min-h-0 flex flex-col"
    >
      {hasLocation ? (
        <>
          <PanelToolbar>
            <div className="flex items-center gap-1.5 min-w-0 text-xs text-site-blue">
              <MapPin size={13} strokeWidth={2} className="shrink-0" />
              <span className="truncate">{locationName ?? 'Ваша локация'}</span>
            </div>
          </PanelToolbar>

          <PanelScrollArea className="flex flex-col gap-3.5">
            {players.length === 0 ? (
              <EmptyState
                icon={<Users size={30} strokeWidth={1.4} className="text-white/20" />}
                message="Нет доступных игроков на вашей локации"
                className="py-8"
              />
            ) : (
              <div className="flex flex-col gap-2.5">
                {players.map((p) => (
                  <ProfileCard key={p.id} className="flex items-center gap-3 p-3">
                    <GoldIconFrame
                      size={40}
                      shape="circle"
                      src={p.avatar}
                      alt={p.name}
                      fallback={<Users size={17} strokeWidth={1.5} className="text-white/40" />}
                    />
                    <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                      <span className="text-white text-[13px] font-medium truncate">{p.name}</span>
                      {p.level != null && (
                        <span className="text-[11px] text-white/50">Ур. {p.level}</span>
                      )}
                    </div>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onInvite(p.id)}
                      className="flex items-center gap-1.5 shrink-0 min-h-[36px] px-3.5 py-2 rounded-[9px] border border-gold/40 bg-gold/10 text-gold text-[11px] font-medium uppercase tracking-[0.04em] cursor-pointer hover:bg-gold/20 transition-colors duration-200 ease-site disabled:opacity-50"
                    >
                      <Plus size={13} strokeWidth={2.2} className="shrink-0" />
                      Позвать
                    </button>
                  </ProfileCard>
                ))}
              </div>
            )}

            <span className="text-[11px] text-white/35 leading-relaxed">
              Приглашать можно только игроков, находящихся на вашей текущей локации.
            </span>
          </PanelScrollArea>
        </>
      ) : (
        <p className="p-4 lg:p-5 text-sm text-white/40">Вы не находитесь в локации.</p>
      )}
    </PanelShell>
  );
};

export default InviteFromLocationPanel;
