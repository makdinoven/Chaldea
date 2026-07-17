import { useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
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
  isCharacterHere?: boolean;
  // FEAT-145 v2: NPC ids the player may interact with (npc_dialogue gate posts).
  // Staff bypass the gate entirely.
  talkableNpcIds?: number[];
  npcGateStaff?: boolean;
}

type WhoTab = 'players' | 'npcs';

const getRarityColorClass = (rarity?: string): string => {
  switch (rarity) {
    case 'common': return 'text-rarity-common';
    case 'rare': return 'text-rarity-rare';
    case 'legendary': return 'text-rarity-legendary';
    default: return 'text-site-blue';
  }
};

const AvatarCard = ({ avatar, name, level, title, titleRarity, actionsSlot }: { avatar: string | null; name: string; level?: number; title?: string; titleRarity?: string; actionsSlot?: ReactNode }) => (
  <div className="flex flex-col items-center gap-2 p-2 rounded-card hover:bg-white/5 transition-colors duration-200">
    {title ? (
      <span className={`text-[10px] sm:text-xs text-center leading-tight break-words w-full ${getRarityColorClass(titleRarity)}`}>
        {title}
      </span>
    ) : (
      <span className="text-[10px] sm:text-xs text-transparent select-none">&nbsp;</span>
    )}
    <div className="gold-outline relative w-[4.5rem] h-[4.5rem] sm:w-20 sm:h-20 rounded-full overflow-hidden bg-black/40 shrink-0">
      {avatar ? (
        <img src={avatar} alt={name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-white/20">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
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
  isCharacterHere?: boolean;
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

const NpcCard = ({ npc, onClick, currentCharacterId, isCharacterHere = false }: NpcCardProps) => {
  const roleLabel = npc.npc_role ? (NPC_ROLE_LABELS[npc.npc_role] || npc.npc_role) : null;
  const roleIcon = npc.npc_role ? (NPC_ROLE_ICONS[npc.npc_role] || null) : null;

  return (
    <div className="flex flex-col items-center gap-2 p-2 rounded-card hover:bg-white/5 transition-colors duration-200">
      <button
        onClick={onClick}
        className="flex flex-col items-center gap-2 cursor-pointer bg-transparent border-0 w-full"
      >
        <div className="relative">
          <div className="gold-outline relative w-[4.5rem] h-[4.5rem] sm:w-20 sm:h-20 rounded-full overflow-hidden bg-black/40 shrink-0">
            {npc.avatar ? (
              <img src={npc.avatar} alt={npc.name} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-white/20">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
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
      {currentCharacterId != null && isCharacterHere && (
        <NpcAttackButton
          npcId={npc.id}
          npcName={npc.name}
          currentCharacterId={currentCharacterId}
        />
      )}
    </div>
  );
};

/**
 * «Кто здесь» — single card with Игроки/НПС tabs (FEAT-152 §3.5 mock style).
 * Deliberately NOT dimmed while in battle (decision A10): the lists and
 * profiles stay browsable, only the actions themselves are gated elsewhere.
 */
const PlayersSection = ({ players, npcs, currentUserId, currentCharacterId, currentCharacterLevel = 0, locationId, locationMarkerType = 'safe', isCharacterHere = false, talkableNpcIds = [], npcGateStaff = false }: PlayersSectionProps) => {
  const [selectedNpcId, setSelectedNpcId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<WhoTab>('players');

  const tabs: { key: WhoTab; label: string; count: number }[] = [
    { key: 'players', label: 'Игроки', count: players.length },
    { key: 'npcs', label: 'НПС', count: npcs.length },
  ];

  return (
    <>
      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card overflow-hidden flex flex-col">
        {/* Header: icon + title + tab switcher */}
        <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3 border-b border-white/[0.07] flex-wrap">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-gold shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
          </svg>
          <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">
            Кто здесь
          </h2>
          <div className="ml-auto flex gap-1 p-[3px] rounded-full bg-black/35 border border-white/10">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`chip-outline ${activeTab === tab.key ? 'chip-outline-active' : ''} rounded-full px-3 py-1 text-[11px] font-medium flex items-center gap-1.5`}
              >
                {tab.label}
                <span className={`text-[9px] font-bold px-1.5 py-px rounded-full ${
                  activeTab === tab.key ? 'bg-black/30' : 'bg-white/10'
                }`}>
                  {tab.count}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        {activeTab === 'players' ? (
          players.length === 0 ? (
            <p className="text-white/50 text-sm p-4 sm:p-5">Здесь пока никого нет</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 sm:gap-2 p-3 sm:p-4 max-h-[320px] lg:max-h-[400px] overflow-y-auto gold-scrollbar">
              {players.map((player) => (
                <AvatarCard
                  key={player.id}
                  avatar={player.avatar}
                  name={player.name}
                  level={player.level}
                  title={player.character_title}
                  titleRarity={player.character_title_rarity}
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
                        isCharacterHere={isCharacterHere}
                      />
                    ) : undefined
                  }
                />
              ))}
            </div>
          )
        ) : npcs.length === 0 ? (
          <p className="text-white/50 text-sm p-4 sm:p-5">НПС отсутствуют на этой локации</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 sm:gap-2 p-3 sm:p-4 max-h-[320px] lg:max-h-[400px] overflow-y-auto gold-scrollbar">
            {npcs.map((npc) => (
              <NpcCard
                key={npc.id}
                npc={npc}
                onClick={() => {
                  // FEAT-145 v2: interacting needs an npc_dialogue post naming THIS npc.
                  if (isCharacterHere && !npcGateStaff && !talkableNpcIds.includes(npc.id)) {
                    toast.error('Нужен пост «Диалог с НПС» с этим персонажем');
                    return;
                  }
                  setSelectedNpcId(npc.id);
                }}
                currentCharacterId={currentCharacterId}
                isCharacterHere={isCharacterHere}
              />
            ))}
          </div>
        )}
      </section>

      {selectedNpcId !== null && (
        <NpcProfileModal
          npcId={selectedNpcId}
          onClose={() => setSelectedNpcId(null)}
          isCharacterHere={isCharacterHere}
        />
      )}
    </>
  );
};

export default PlayersSection;
