// FEAT-151 — leader-only «Пригласить с локации» panel (mock composition,
// design-system styles). Players come from getPlayersOnLocation (FEAT-144).
import { MapPin, Plus, UserPlus, Users } from 'lucide-react';
import type { PlayerOnLocation } from '../../../api/squads';
import PanelShell from '../PanelShell';
import EmptyState from '../shared/EmptyState';

interface InviteFromLocationPanelProps {
  /** Name of the viewer's current location (null when unknown) */
  locationName: string | null;
  /** Whether the viewer's character is on a location at all */
  hasLocation: boolean;
  players: PlayerOnLocation[];
  busy: boolean;
  onInvite: (characterId: number) => void;
}

const InviteFromLocationPanel = ({
  locationName,
  hasLocation,
  players,
  busy,
  onInvite,
}: InviteFromLocationPanelProps) => {
  return (
    <PanelShell
      title="Пригласить с локации"
      icon={<UserPlus size={16} strokeWidth={1.8} className="text-gold shrink-0" />}
      bodyClassName="flex flex-col gap-3.5 p-4 lg:p-5"
    >
      {hasLocation ? (
        <>
          <div className="flex items-center gap-1.5 text-xs text-site-blue">
            <MapPin size={13} strokeWidth={2} className="shrink-0" />
            <span className="truncate">{locationName ?? 'Ваша локация'}</span>
          </div>

          {players.length === 0 ? (
            <EmptyState
              icon={<Users size={30} strokeWidth={1.4} className="text-white/20" />}
              message="Нет доступных игроков на вашей локации"
              className="py-8"
            />
          ) : (
            <div className="flex flex-col gap-2.5">
              {players.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center gap-3 rounded-card bg-white/[0.03] border border-white/[0.08] p-3"
                >
                  <div className="w-10 h-10 shrink-0 rounded-full bg-white/10 flex items-center justify-center overflow-hidden">
                    {p.avatar ? (
                      <img src={p.avatar} alt={p.name} className="w-full h-full object-cover" />
                    ) : (
                      <Users size={17} strokeWidth={1.5} className="text-white/40" />
                    )}
                  </div>
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
                    className="flex items-center gap-1.5 shrink-0 px-3.5 py-2 rounded-[9px] border border-gold/40 bg-gold/10 text-gold text-[11px] font-medium uppercase tracking-[0.04em] cursor-pointer hover:bg-gold/20 transition-colors duration-200 ease-site disabled:opacity-50"
                  >
                    <Plus size={13} strokeWidth={2.2} className="shrink-0" />
                    Позвать
                  </button>
                </div>
              ))}
            </div>
          )}

          <span className="text-[11px] text-white/35 leading-relaxed">
            Приглашать можно только игроков, находящихся на вашей текущей локации.
          </span>
        </>
      ) : (
        <p className="text-sm text-white/40">Вы не находитесь в локации.</p>
      )}
    </PanelShell>
  );
};

export default InviteFromLocationPanel;
