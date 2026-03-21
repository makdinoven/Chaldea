import { useState } from 'react';
import { Player, NpcInLocation } from './types';
import { NPC_ROLE_LABELS } from '../../../constants/npc';
import NpcProfileModal from './NpcProfileModal';

interface PlayersSectionProps {
  players: Player[];
  npcs: NpcInLocation[];
}

const AvatarCard = ({ avatar, name, level }: { avatar: string | null; name: string; level?: number }) => (
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
  </div>
);

interface NpcCardProps {
  npc: NpcInLocation;
  onClick: () => void;
}

const NpcCard = ({ npc, onClick }: NpcCardProps) => {
  const roleLabel = npc.npc_role ? (NPC_ROLE_LABELS[npc.npc_role] || npc.npc_role) : null;

  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center gap-2 p-2 rounded-card hover:bg-white/5 transition-colors cursor-pointer bg-transparent border-0"
    >
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
      <span className="text-white text-xs sm:text-sm text-center truncate w-full">
        {npc.name}
      </span>
      {roleLabel && (
        <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-[10px] sm:text-xs font-medium">
          {roleLabel}
        </span>
      )}
    </button>
  );
};

const PlayersSection = ({ players, npcs }: PlayersSectionProps) => {
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
