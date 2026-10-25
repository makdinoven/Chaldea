import type { SessionMember } from '../../api/dungeons';
import type { MemberBusy } from '../DungeonBoard3D/boardTypes';
import PartyFrames from './PartyFrames';

interface DungeonPartyPanelProps {
  members: SessionMember[];
  /** Shows "N/max" when given. */
  maxSize?: number;
  currentCharacterId: number | null;
  /** Figurine colour per character on the 3D table. */
  colors?: Map<number, string>;
  /** Who is in a minigame right now, and which. */
  busy?: Map<number, MemberBusy>;
}

const DungeonPartyPanel = ({ members, maxSize, currentCharacterId, colors, busy }: DungeonPartyPanelProps) => (
  <div className="bg-black/40 rounded-card p-4 backdrop-blur-sm">
    <div className="flex items-center justify-between mb-3">
      <h3 className="gold-text text-lg font-medium uppercase">Группа</h3>
      <span className="text-white/60 text-sm">{maxSize ? `${members.length}/${maxSize}` : members.length}</span>
    </div>
    <PartyFrames members={members} currentCharacterId={currentCharacterId} colors={colors} busy={busy} />
  </div>
);

export default DungeonPartyPanel;
