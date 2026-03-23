import { useState, type ReactNode } from 'react';
import { Player, NpcInLocation } from './types';
import { NPC_ROLE_LABELS, NPC_ROLE_ICONS } from '../../../constants/npc';
import useNpcAttack from '../../../hooks/useNpcAttack';
import NpcProfileModal from './NpcProfileModal';
import PlayerActionsMenu from './PlayerActionsMenu';

interface PlayersSectionProps {
  players: Player[];
  npcs: NpcInLocation[];
  currentUserId?: number | null;
  currentCharacterId?: number | null;
  currentCharacterLevel?: number;
  locationId: number;
  locationMarkerType?: string;
}

const AvatarCard = ({ avatar, name, level, actionsSlot }: { avatar: string | null; name: string; level?: number; actionsSlot?: ReactNode }) => (
  <div className="flex flex-col items-center gap-2 p-2 rounded-card hover:bg-white/5 transition-colors">
    <div className="gold-outline relative w-20 h-20 sm:w-24 sm:h-24 rounded-full overflow-hidden bg-black/40 shrink-0">
      {avatar ? (
        <img src={avatar} alt={name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-white/20">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      )}
    </div>
    <span className="text-white text-xs sm:text-sm text-center truncate w-full">
      {name}
    </span>
    {level !== undefined && (
      <span className="gold-text text-[10px] sm:text-xs font-medium">
        LVL {level}
      </span>
    )}
    {actionsSlot}
  </div>
);

interface NpcCardProps {
  npc: NpcInLocation;
  onClick: () => void;
  currentCharacterId?: number | null;
}

const NpcAttackButton = ({ npcId, npcName, currentCharacterId }: { npcId: number; npcName: string; currentCharacterId: number }) => {
  const { attacking, handleAttack } = useNpcAttack({
    npcId,
    npcName,
    currentCharacterId,
  });

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        handleAttack();
      }}
      disabled={attacking}
      className="
        text-site-red text-[10px] sm:text-xs font-medium uppercase tracking-wide
        hover:text-white transition-colors duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
        flex items-center gap-1
      "
    >
      {attacking ? (
        <div className="w-3 h-3 border-2 border-site-red/30 border-t-site-red rounded-full animate-spin" />
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      )}
      {attacking ? 'Атака...' : 'Напасть'}
    </button>
  );
};

const NpcCard = ({ npc, onClick, currentCharacterId }: NpcCardProps) => {
  const roleLabel = npc.npc_role ? (NPC_ROLE_LABELS[npc.npc_role] || npc.npc_role) : null;
  const roleIcon = npc.npc_role ? (NPC_ROLE_ICONS[npc.npc_role] || null) : null;

  return (
    <div className="flex flex-col items-center gap-2 p-2 rounded-card hover:bg-white/5 transition-colors">
      <button
        onClick={onClick}
        className="flex flex-col items-center gap-2 cursor-pointer bg-transparent border-0 w-full"
      >
        <div className="relative">
          <div className="gold-outline relative w-20 h-20 sm:w-24 sm:h-24 rounded-full overflow-hidden bg-black/40 shrink-0">
            {npc.avatar ? (
              <img src={npc.avatar} alt={npc.name} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-white/20">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
            )}
          </div>
          {roleIcon && (
            <span className="absolute -bottom-1 -right-1 w-7 h-7 sm:w-8 sm:h-8 flex items-center justify-center rounded-full bg-black/80 border border-gold-dark/50 text-sm sm:text-base leading-none">
              {roleIcon}
            </span>
          )}
        </div>
        <span className="text-white text-xs sm:text-sm text-center truncate w-full">
          {npc.name}
        </span>
        {roleLabel && (
          <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-[10px] sm:text-xs font-medium">
            {roleLabel}
          </span>
        )}
      </button>
      {currentCharacterId != null && (
        <NpcAttackButton
          npcId={npc.id}
          npcName={npc.name}
          currentCharacterId={currentCharacterId}
        />
      )}
    </div>
  );
};

const PlayersSection = ({ players, npcs, currentUserId, currentCharacterId, currentCharacterLevel = 0, locationId, locationMarkerType = 'safe' }: PlayersSectionProps) => {
  const [selectedNpcId, setSelectedNpcId] = useState<number | null>(null);

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
        {/* Left: Players */}
        <section className="bg-black/50 rounded-card p-4 sm:p-6 flex flex-col gap-4">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
            Игроки в локации
          </h2>
          {players.length === 0 ? (
            <p className="text-white/50 text-sm">На локации никого нет</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4">
              {players.map((player) => (
                <AvatarCard
                  key={player.id}
                  avatar={player.avatar}
                  name={player.name}
                  level={player.level}
                  actionsSlot={
                    currentCharacterId != null &&
                    currentUserId != null &&
                    player.user_id !== currentUserId ? (
                      <PlayerActionsMenu
                        targetCharacterId={player.id}
                        targetUserId={player.user_id}
                        targetName={player.name}
                        targetLevel={player.level}
                        currentCharacterId={currentCharacterId}
                        currentCharacterLevel={currentCharacterLevel}
                        locationId={locationId}
                        locationMarkerType={locationMarkerType}
                      />
                    ) : undefined
                  }
                />
              ))}
            </div>
          )}
        </section>

        {/* Right: NPCs */}
        <section className="bg-black/50 rounded-card p-4 sm:p-6 flex flex-col gap-4">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
            НПС на локации
          </h2>
          {npcs.length === 0 ? (
            <p className="text-white/50 text-sm">НПС отсутствуют на этой локации</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4">
              {npcs.map((npc) => (
                <NpcCard
                  key={npc.id}
                  npc={npc}
                  onClick={() => setSelectedNpcId(npc.id)}
                  currentCharacterId={currentCharacterId}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      {selectedNpcId !== null && (
        <NpcProfileModal
          npcId={selectedNpcId}
          onClose={() => setSelectedNpcId(null)}
        />
      )}
    </>
  );
};

export default PlayersSection;
