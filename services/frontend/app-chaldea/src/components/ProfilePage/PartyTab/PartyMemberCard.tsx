// FEAT-151 — party member card per Claude Design mock (composition only,
// styles from the project design system). Class chip instead of the mock's
// role chip (user decision); HP/MP bars hidden when enrichment is null.
import { Crown, Users } from 'lucide-react';
import type { PartyMember } from '../../../api/squads';
import MiniStatBar from '../shared/MiniStatBar';

interface PartyMemberCardProps {
  member: PartyMember;
  /** Current location id of the viewer's own character (online-dot logic, FEAT-144) */
  ownLocationId: number | null;
}

const PartyMemberCard = ({ member, ownLocationId }: PartyMemberCardProps) => {
  const invited = member.status === 'invited';
  const sameLocation =
    member.current_location_id != null && member.current_location_id === ownLocationId;

  return (
    <div
      className={`relative rounded-card bg-black/30 border border-gold/[0.16] shadow-card flex gap-3.5 p-4 ${
        invited ? 'opacity-60' : ''
      }`}
    >
      {/* 54px round avatar in gold-gradient frame, Crown badge for the leader */}
      <div className="relative w-[54px] h-[54px] shrink-0 rounded-full p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
        <div className="w-full h-full rounded-full bg-site-dark flex items-center justify-center overflow-hidden">
          {member.avatar ? (
            <img
              src={member.avatar}
              alt={member.name ?? ''}
              className="w-full h-full object-cover"
            />
          ) : (
            <Users size={22} strokeWidth={1.5} className="text-white/40" />
          )}
        </div>
        {member.is_leader && (
          <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-gold">
            <Crown size={15} strokeWidth={2} />
          </span>
        )}
      </div>

      <div className="flex flex-col gap-1.5 flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-white text-sm font-medium truncate">
            {member.name ?? `#${member.character_id}`}
          </span>
          {/* Class chip — hidden when enrichment is null */}
          {member.class_name != null && (
            <span className="shrink-0 text-[10px] font-medium uppercase tracking-[0.05em] px-2 py-0.5 rounded text-site-blue bg-site-blue/10">
              {member.class_name}
            </span>
          )}
        </div>

        {member.level != null && (
          <span className="text-xs text-white/60">Ур. {member.level}</span>
        )}

        {invited ? (
          <span className="w-fit text-[10px] font-medium uppercase tracking-[0.05em] px-2 py-0.5 rounded-full border border-white/20 text-white/50">
            Приглашён
          </span>
        ) : (
          <>
            {/* MiniStatBar renders nothing when values are null — never «0/0» */}
            <MiniStatBar
              variant="hp"
              label="HP"
              current={member.current_health}
              max={member.max_health}
            />
            <MiniStatBar
              variant="mana"
              label="MP"
              current={member.current_mana}
              max={member.max_mana}
            />
          </>
        )}

        {/* Online dot: green when on the viewer's location, red otherwise */}
        <div className="flex items-center gap-1.5 mt-0.5">
          <span
            className={`w-[7px] h-[7px] rounded-full shrink-0 ${
              sameLocation ? 'bg-stat-energy' : 'bg-site-red/70'
            }`}
          />
          <span className="text-[11px] text-white/50">
            {sameLocation ? 'На вашей локации' : 'На другой локации'}
          </span>
        </div>
      </div>
    </div>
  );
};

export default PartyMemberCard;
