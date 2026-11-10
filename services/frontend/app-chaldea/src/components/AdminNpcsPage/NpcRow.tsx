import type { ReactNode, Ref } from 'react';
import { NPC_ROLE_LABELS } from '../../constants/npc';
import ExpandableRow from '../Admin/ExpandableList/ExpandableRow';
import { toReadyMark } from '../Admin/ExpandableList/readyMark';

/* FEAT-208: compact clickable NPC plate (over the shared ExpandableRow); the expanded panel renders under it. */

export interface NpcListItem {
  id: number;
  name: string;
  avatar: string | null;
  level: number;
  npc_role: string | null;
  location_name: string | null;
  location_id: number | null;
  npc_status: string | null;
  /** FEAT-209 admin «Готов» flag (+ who / when, UTC-naive) */
  npc_ready: boolean;
  npc_ready_at: string | null;
  npc_ready_by: string | null;
}

interface NpcRowProps {
  /** null = the «Новый НПС» plate of the create panel */
  npc: NpcListItem | null;
  open: boolean;
  onToggle: () => void;
  /** Small caption over the plate, e.g. «Открыт по ссылке» */
  badge?: string;
  rowRef?: Ref<HTMLDivElement>;
  /** The expanded panel (rendered only while open) */
  children?: ReactNode;
}

const GRID_CLASS = 'sm:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)_minmax(0,1.4fr)_auto_auto]';

const Avatar = ({ npc }: { npc: NpcListItem | null }) =>
  npc?.avatar ? (
    <img src={npc.avatar} alt={npc.name} className="w-10 h-10 sm:w-11 sm:h-11 rounded-full object-cover shrink-0" />
  ) : (
    <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-full bg-white/[0.05] flex items-center justify-center text-white/30 text-xs shrink-0">
      {npc ? 'НПС' : '+'}
    </div>
  );

const StatusChip = ({ status }: { status: string | null }) =>
  status === 'dead' ? (
    <span className="px-2 py-0.5 rounded-full bg-site-red/20 text-site-red text-xs whitespace-nowrap">Мёртв</span>
  ) : (
    <span className="px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-xs whitespace-nowrap">Жив</span>
  );

const NpcCells = ({ npc }: { npc: NpcListItem }) => (
  <>
    {/* Role */}
    <div className="flex flex-wrap items-center gap-2 min-w-0 pl-[52px] sm:pl-0">
      {npc.npc_role && (
        <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-xs font-medium truncate">
          {NPC_ROLE_LABELS[npc.npc_role] || npc.npc_role}
        </span>
      )}
      {/* Status (mobile, next to the role) */}
      <span className="sm:hidden">
        <StatusChip status={npc.npc_status} />
      </span>
    </div>

    {/* Location */}
    <span className="text-white/60 text-xs sm:text-sm truncate pl-[52px] sm:pl-0">
      {npc.location_name ?? (npc.location_id != null ? `Локация #${npc.location_id}` : '—')}
    </span>

    {/* Status (desktop) */}
    <span className="hidden sm:block">
      <StatusChip status={npc.npc_status} />
    </span>
  </>
);

const NpcRow = ({ npc, open, onToggle, badge, rowRef, children }: NpcRowProps) => (
  <ExpandableRow
    open={open}
    onToggle={onToggle}
    avatar={<Avatar npc={npc} />}
    title={npc ? npc.name : 'Новый НПС'}
    subtitle={npc ? `#${npc.id} · ${npc.level} ур.` : undefined}
    ready={npc ? toReadyMark(npc.npc_ready, npc.npc_ready_at, npc.npc_ready_by) : null}
    cells={npc ? <NpcCells npc={npc} /> : undefined}
    gridClassName={GRID_CLASS}
    badge={badge}
    rowRef={rowRef}
  >
    {children}
  </ExpandableRow>
);

export default NpcRow;
