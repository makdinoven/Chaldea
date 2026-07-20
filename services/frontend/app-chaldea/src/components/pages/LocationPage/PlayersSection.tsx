import { useMemo, useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
import { Player, NpcInLocation } from './types';
import type { PartyOnLocation } from '../../../api/squads';
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
  // FEAT-153 §3.5: squads present on this location. The fetch is owned by
  // LocationPage so the players↔squads join happens in one place.
  parties: PartyOnLocation[];
  partiesError: string | null;
  onRetryParties: () => void;
}

type WhoTab = 'players' | 'npcs';

/** A player as rendered inside a group frame. */
interface GroupMember extends Player {
  isLeader: boolean;
}

/** One frame in the Игроки tab: a squad, or the trailing «Вне отряда» frame. */
interface PlayerGroup {
  id: string;
  name: string;
  isSquad: boolean;
  members: GroupMember[];
}

/**
 * FEAT-153 §3.5: join `players` (from /client/details) with `parties`
 * (from party-service) client-side. Squads keep server order; every player not
 * claimed by a squad falls into the trailing «Вне отряда» frame, so the total
 * number of avatars always equals `players.length` with no duplicates.
 */
const buildPlayerGroups = (players: Player[], parties: PartyOnLocation[]): PlayerGroup[] => {
  const byId = new Map(players.map((p) => [p.id, p]));
  const claimed = new Set<number>();

  const groups: PlayerGroup[] = parties
    .map((party) => {
      const members = party.members.reduce<GroupMember[]>((acc, member) => {
        const player = byId.get(member.character_id);
        // Defensive: a squad member who is not in `players` cannot normally
        // happen (the endpoint returns co-located members only) — skip, never crash.
        if (player && !claimed.has(player.id)) {
          claimed.add(player.id);
          acc.push({ ...player, isLeader: member.is_leader });
        }
        return acc;
      }, []);
      return { id: `squad-${party.id}`, name: party.name, isSquad: true, members };
    })
    .filter((group) => group.members.length > 0);

  const solo = players
    .filter((player) => !claimed.has(player.id))
    .map((player) => ({ ...player, isLeader: false }));

  if (solo.length > 0) {
    groups.push({ id: 'solo', name: 'Вне отряда', isSquad: false, members: solo });
  }

  return groups;
};

const SquadIcon = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
  </svg>
);

const LeaderCrown = () => (
  <span
    title="Лидер отряда"
    className="absolute top-0.5 right-2 z-10 text-gold pointer-events-none drop-shadow-[0_1px_2px_rgba(0,0,0,0.6)]"
  >
    <svg xmlns="http://www.w3.org/2000/svg" className="w-[15px] h-[15px]" viewBox="0 0 24 24" fill="currentColor">
      <path d="M5 16L3 5l5.5 5L12 4l3.5 6L21 5l-2 11H5zm0 3h14v2H5v-2z" />
    </svg>
  </span>
);

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
 *
 * FEAT-153 §3.5: squads are NOT a third tab. The tab strip stays two tabs and
 * the Игроки tab body is a vertical list of group frames — one per co-located
 * squad, plus a trailing «Вне отряда» frame. Squads arrive as props; the fetch
 * lives in LocationPage (which also supplies the retry handler).
 */
const PlayersSection = ({ players, npcs, currentUserId, currentCharacterId, currentCharacterLevel = 0, locationId, locationMarkerType = 'safe', isCharacterHere = false, talkableNpcIds = [], npcGateStaff = false, parties, partiesError, onRetryParties }: PlayersSectionProps) => {
  const [selectedNpcId, setSelectedNpcId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<WhoTab>('players');

  const playerGroups = useMemo(() => buildPlayerGroups(players, parties), [players, parties]);

  // The tab pill keeps the TOTAL player count, not a per-group count.
  const tabs: { key: WhoTab; label: string; count: number }[] = [
    { key: 'players', label: 'Игроки', count: players.length },
    { key: 'npcs', label: 'НПС', count: npcs.length },
  ];

  return (
    <>
      {/* FEAT-153 §3.6: fixed 460px row-3 box from `sm` up; below it the height
          is natural and the tab body caps at 320px. Empty states render INSIDE
          the flex body so an empty block keeps its box instead of collapsing. */}
      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card overflow-hidden h-auto sm:h-[460px] flex flex-col">
        {/* Header: icon + title + tab switcher */}
        <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3 border-b border-white/[0.07] flex-wrap shrink-0">
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
          <div className="flex-1 min-h-0 max-h-[320px] sm:max-h-none overflow-y-auto gold-scrollbar flex flex-col gap-3 p-3 sm:p-4">
            {/* Squads failed to load — visible inline (CLAUDE.md: no silent failures).
                Rendered ABOVE the frames; players still render below it. */}
            {partiesError && (
              <div className="shrink-0 flex flex-wrap items-center gap-2 rounded-card border border-site-red/30 bg-site-red/[0.06] p-3">
                <p className="text-site-red text-sm min-w-0 flex-1">{partiesError}</p>
                <button
                  type="button"
                  onClick={onRetryParties}
                  className="btn-blue text-xs px-3 py-1.5 shrink-0"
                >
                  Повторить
                </button>
              </div>
            )}

            {players.length === 0 ? (
              <div className="flex-1 min-h-0 flex items-center justify-center p-5 text-center text-white/50 text-sm">
                Здесь пока никого нет
              </div>
            ) : (
              playerGroups.map((group) => (
                <div
                  key={group.id}
                  className={`shrink-0 rounded-card overflow-hidden border ${
                    group.isSquad ? 'border-gold-dark/25 bg-gold/[0.04]' : 'border-transparent bg-transparent'
                  }`}
                >
                  <div
                    className={`flex items-center gap-2 px-3 py-2 border-b ${
                      group.isSquad ? 'border-gold-dark/15' : 'border-white/[0.07]'
                    }`}
                  >
                    {group.isSquad && <SquadIcon className="w-3.5 h-3.5 text-gold shrink-0" />}
                    <span
                      className={`text-[11.5px] font-medium tracking-[0.04em] truncate ${
                        group.isSquad ? 'text-gold' : 'text-white/50'
                      }`}
                    >
                      {group.name}
                    </span>
                    <span className="ml-auto shrink-0 bg-white/10 text-white/60 text-[9.5px] font-bold px-[7px] py-px rounded-full">
                      {group.members.length}
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 p-3">
                    {group.members.map((player) => (
                      <div key={player.id} className="relative">
                        {player.isLeader && <LeaderCrown />}
                        <AvatarCard
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
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        ) : npcs.length === 0 ? (
          <div className="flex-1 min-h-0 flex items-center justify-center p-5 text-center text-white/50 text-sm">
            НПС отсутствуют на этой локации
          </div>
        ) : (
          <div className="flex-1 min-h-0 max-h-[320px] sm:max-h-none overflow-y-auto gold-scrollbar grid grid-cols-2 sm:grid-cols-3 content-start items-start gap-1.5 sm:gap-2 p-3 sm:p-4">
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
