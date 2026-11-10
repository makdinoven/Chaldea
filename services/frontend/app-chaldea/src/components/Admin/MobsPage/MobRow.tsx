import type { ReactNode, Ref } from 'react';
import ExpandableRow from '../ExpandableList/ExpandableRow';
import { adminReadyMark } from '../ExpandableList/readyMark';
import type { MobTemplateListItem } from '../../../api/mobs';
import { TIER_COLORS, TIER_LABELS } from './mobTabKeys';

/* FEAT-210: compact clickable mob-template plate (over the shared ExpandableRow); the panel renders under it. */

interface MobRowProps {
  /** null = the «Новый моб» plate of the create panel */
  mob: MobTemplateListItem | null;
  open: boolean;
  onToggle: () => void;
  /** Small caption over the plate, e.g. «Открыт по ссылке» */
  badge?: string;
  rowRef?: Ref<HTMLDivElement>;
  /** The expanded panel (rendered only while open) */
  children?: ReactNode;
}

const GRID_CLASS = 'sm:grid-cols-[minmax(0,2.4fr)_minmax(0,1fr)_minmax(0,1fr)_auto]';

const Avatar = ({ mob }: { mob: MobTemplateListItem | null }) =>
  mob?.avatar ? (
    <img src={mob.avatar} alt={mob.name} className="w-10 h-10 sm:w-11 sm:h-11 rounded-full object-cover shrink-0" />
  ) : (
    <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-full bg-white/[0.05] flex items-center justify-center text-white/30 text-xs shrink-0">
      {mob ? 'Моб' : '+'}
    </div>
  );

const TierChip = ({ tier }: { tier: string }) => (
  <span className={`px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${TIER_COLORS[tier] || 'bg-white/10 text-white/70'}`}>
    {TIER_LABELS[tier] || tier}
  </span>
);

const SpawnCount = ({ count }: { count: number }) => (
  <span className={`text-xs sm:text-sm whitespace-nowrap ${count > 0 ? 'text-white/60' : 'text-white/30'}`}>
    Спавнов: {count}
  </span>
);

const MobCells = ({ mob }: { mob: MobTemplateListItem }) => (
  <>
    {/* Tier (+ spawn count on mobile) */}
    <div className="flex flex-wrap items-center gap-3 min-w-0 pl-[52px] sm:pl-0">
      <TierChip tier={mob.tier} />
      <span className="sm:hidden">
        <SpawnCount count={mob.spawn_count ?? 0} />
      </span>
    </div>

    {/* Spawn count (desktop) */}
    <span className="hidden sm:block">
      <SpawnCount count={mob.spawn_count ?? 0} />
    </span>
  </>
);

const MobRow = ({ mob, open, onToggle, badge, rowRef, children }: MobRowProps) => (
  <ExpandableRow
    open={open}
    onToggle={onToggle}
    avatar={<Avatar mob={mob} />}
    title={mob ? mob.name : 'Новый моб'}
    subtitle={mob ? `#${mob.id} · ${mob.level} ур.` : undefined}
    ready={mob ? adminReadyMark(mob) : null}
    cells={mob ? <MobCells mob={mob} /> : undefined}
    gridClassName={GRID_CLASS}
    badge={badge}
    rowRef={rowRef}
  >
    {children}
  </ExpandableRow>
);

export default MobRow;
