import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { TreeNodeInTreeResponse, NodeVisualState } from './types';

interface PlayerNodeData extends TreeNodeInTreeResponse {
  visualState: NodeVisualState;
  classId: number;
}

/* ---------- Class color themes ---------- */
// Warrior = red, Rogue = green, Mage = blue
interface ClassTheme {
  chosenRing: string;
  chosenFill: string;
  chosenGlow: string;
  chosenDot: string;
  chosenText: string;
  chosenBadge: string;
  availableRing: string;
  availableFill: string;
  availableGlow: string;
  availableDot: string;
  availableText: string;
}

const classThemes: Record<number, ClassTheme> = {
  // Warrior — red
  1: {
    chosenRing: 'ring-red-400',
    chosenFill: 'bg-red-400/30',
    chosenGlow: 'shadow-[0_0_12px_rgba(248,113,113,0.7)]',
    chosenDot: 'bg-red-400',
    chosenText: 'text-red-300',
    chosenBadge: 'bg-red-400/25 text-red-300',
    availableRing: 'ring-red-300/60 animate-pulse',
    availableFill: 'bg-red-400/10',
    availableGlow: 'shadow-[0_0_10px_rgba(248,113,113,0.35)]',
    availableDot: 'bg-red-300/70',
    availableText: 'text-red-300/80',
  },
  // Mage — blue
  2: {
    chosenRing: 'ring-sky-400',
    chosenFill: 'bg-sky-400/30',
    chosenGlow: 'shadow-[0_0_12px_rgba(56,189,248,0.7)]',
    chosenDot: 'bg-sky-400',
    chosenText: 'text-sky-300',
    chosenBadge: 'bg-sky-400/25 text-sky-300',
    availableRing: 'ring-sky-300/60 animate-pulse',
    availableFill: 'bg-sky-400/10',
    availableGlow: 'shadow-[0_0_10px_rgba(56,189,248,0.35)]',
    availableDot: 'bg-sky-300/70',
    availableText: 'text-sky-300/80',
  },
  // Rogue — green
  3: {
    chosenRing: 'ring-emerald-400',
    chosenFill: 'bg-emerald-400/30',
    chosenGlow: 'shadow-[0_0_12px_rgba(52,211,153,0.7)]',
    chosenDot: 'bg-emerald-400',
    chosenText: 'text-emerald-300',
    chosenBadge: 'bg-emerald-400/25 text-emerald-300',
    availableRing: 'ring-emerald-300/60 animate-pulse',
    availableFill: 'bg-emerald-400/10',
    availableGlow: 'shadow-[0_0_10px_rgba(52,211,153,0.35)]',
    availableDot: 'bg-emerald-300/70',
    availableText: 'text-emerald-300/80',
  },
};

const defaultTheme = classThemes[1];

/* ---------- size by node_type ---------- */
const sizeMap: Record<string, { outer: string }> = {
  root: { outer: 'w-[70px] h-[70px]' },
  subclass_choice: { outer: 'w-[60px] h-[60px]' },
  regular: { outer: 'w-[36px] h-[36px]' },
};

const PlayerNodeComponent = ({ data, selected }: NodeProps) => {
  const d = data as PlayerNodeData;
  const skillsCount = d.skills?.length ?? 0;
  const state = d.visualState ?? 'locked';
  const nodeType = d.node_type ?? 'regular';
  const size = sizeMap[nodeType] ?? sizeMap.regular;
  const isLarge = nodeType === 'root' || nodeType === 'subclass_choice';
  const isClickable = state === 'available' || state === 'chosen';
  const theme = classThemes[d.classId] ?? defaultTheme;

  // Build style based on state + class theme
  let ring = '';
  let fill = '';
  let glow = '';
  let opacity = 'opacity-100';

  if (state === 'chosen') {
    ring = `ring-2 ${theme.chosenRing}`;
    fill = theme.chosenFill;
    glow = theme.chosenGlow;
  } else if (state === 'available') {
    ring = `ring-2 ${theme.availableRing}`;
    fill = theme.availableFill;
    glow = theme.availableGlow;
  } else if (state === 'locked') {
    ring = 'ring-1 ring-white/15';
    fill = 'bg-white/5';
    opacity = 'opacity-40';
  } else {
    ring = 'ring-1 ring-site-red/25';
    fill = 'bg-site-red/5';
    opacity = 'opacity-30';
  }

  const label = isLarge
    ? (d.name ?? '').slice(0, 3).toUpperCase()
    : undefined;

  return (
    <div
      className={`
        relative flex items-center justify-center
        rounded-full
        ${size.outer}
        ${ring} ${fill} ${glow} ${opacity}
        transition-all duration-200 ease-site
        ${isClickable ? 'cursor-pointer hover:brightness-125' : 'cursor-default'}
        ${selected ? 'ring-site-blue ring-offset-1 ring-offset-transparent' : ''}
      `}
      title={
        state === 'locked'
          ? `Требуется уровень ${d.level_ring}`
          : state === 'blocked'
            ? 'Альтернативная ветка выбрана'
            : d.name
      }
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-[3px] !h-[3px] !bg-transparent !border-0 !-top-px"
      />

      {/* Inner dot for regular nodes */}
      {!isLarge && (
        <span
          className={`block rounded-full ${
            state === 'chosen' ? `w-[14px] h-[14px] ${theme.chosenDot}` :
            state === 'available' ? `w-[10px] h-[10px] ${theme.availableDot}` :
            state === 'locked' ? 'w-[8px] h-[8px] bg-white/20' :
            'w-[8px] h-[8px] bg-site-red/20'
          }`}
        />
      )}

      {/* Label for large nodes */}
      {isLarge && label && (
        <span
          className={`text-[11px] font-medium tracking-wider select-none ${
            state === 'chosen' ? theme.chosenText :
            state === 'available' ? theme.availableText :
            state === 'locked' ? 'text-white/40' :
            'text-site-red/40'
          }`}
        >
          {label}
        </span>
      )}

      {/* Level ring badge (large nodes only) */}
      {isLarge && (
        <span
          className={`
            absolute -top-1.5 -right-1.5
            bg-[#1a1a2e] text-[9px] font-medium rounded-full
            w-[18px] h-[18px] flex items-center justify-center
            border border-white/15
            ${state === 'chosen' ? theme.chosenText : 'text-white/60'}
          `}
        >
          {d.level_ring}
        </span>
      )}

      {/* Skills count badge */}
      {skillsCount > 0 && (
        <span
          className={`
            absolute -bottom-1 left-1/2 -translate-x-1/2
            text-[8px] font-medium rounded-full
            px-1 min-w-[14px] text-center leading-[14px]
            ${state === 'chosen' ? theme.chosenBadge : 'bg-site-blue/25 text-site-blue'}
          `}
        >
          {skillsCount}
        </span>
      )}

      {/* Blocked X (large only) */}
      {state === 'blocked' && isLarge && (
        <span className="absolute top-0.5 left-0.5 text-site-red/50 text-[9px] font-bold">
          &#10005;
        </span>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-[3px] !h-[3px] !bg-transparent !border-0 !-bottom-px"
      />
    </div>
  );
};

export default memo(PlayerNodeComponent);
