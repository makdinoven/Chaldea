import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { TreeNodeInTreeResponse, NodeVisualState } from './types';

interface PlayerNodeData extends TreeNodeInTreeResponse {
  visualState: NodeVisualState;
  classId: number;
}

/* ========== Rune symbols by level_ring ========== */
const runesByRing: Record<number, string[]> = {
  1:  ['ᚨ', 'ᚠ', 'ᚢ'],
  5:  ['ᚦ', 'ᚱ', 'ᚲ', 'ᚷ', 'ᚹ'],
  10: ['ᚺ', 'ᚾ', 'ᛁ', 'ᛃ', 'ᛇ'],
  15: ['ᛈ', 'ᛉ', 'ᛊ', 'ᛏ', 'ᛒ'],
  20: ['ᛖ', 'ᛗ', 'ᛚ', 'ᛜ', 'ᛞ'],
  25: ['ᛟ', 'ᛝ', 'ᛠ', 'ᛡ', 'ᛢ', 'ᛣ'],
  30: ['ᛤ', 'ᛥ', 'ᛦ', 'ᛧ', 'ᛨ', 'ᛩ', 'ᛪ'],
  35: ['᛫', 'ᚨ', 'ᚠ'],
  40: ['ᚢ', 'ᚦ', 'ᚱ'],
  45: ['ᚲ', 'ᚷ', 'ᚹ'],
  50: ['ᚺ', 'ᚾ', 'ᛁ'],
};

const getRune = (levelRing: number, sortOrder: number): string => {
  const runes = runesByRing[levelRing] ?? runesByRing[1];
  return runes[sortOrder % runes.length];
};

/* ========== Class color schemes ========== */
interface ClassColors {
  chosen: { border: string; fill: string; glow: string; rune: string; badge: string };
  available: { border: string; fill: string; glow: string; rune: string };
  locked: { border: string; fill: string; rune: string };
  blocked: { border: string; fill: string; rune: string };
}

/* DB class IDs: 1=Warrior, 2=Rogue, 3=Mage */
const classColors: Record<number, ClassColors> = {
  // Warrior — red/amber
  1: {
    chosen:    { border: '#f87171', fill: 'rgba(248,113,113,0.15)', glow: '0 0 16px rgba(248,113,113,0.6), inset 0 0 12px rgba(248,113,113,0.15)', rune: '#fca5a5', badge: 'rgba(248,113,113,0.25)' },
    available: { border: '#f8717180', fill: 'rgba(248,113,113,0.06)', glow: '0 0 10px rgba(248,113,113,0.3)', rune: '#f8717199' },
    locked:    { border: 'rgba(255,255,255,0.12)', fill: 'rgba(255,255,255,0.03)', rune: 'rgba(255,255,255,0.15)' },
    blocked:   { border: 'rgba(239,68,68,0.2)', fill: 'rgba(239,68,68,0.04)', rune: 'rgba(239,68,68,0.15)' },
  },
  // Rogue — green/emerald
  2: {
    chosen:    { border: '#34d399', fill: 'rgba(52,211,153,0.15)', glow: '0 0 16px rgba(52,211,153,0.6), inset 0 0 12px rgba(52,211,153,0.15)', rune: '#6ee7b7', badge: 'rgba(52,211,153,0.25)' },
    available: { border: '#34d39980', fill: 'rgba(52,211,153,0.06)', glow: '0 0 10px rgba(52,211,153,0.3)', rune: '#34d39999' },
    locked:    { border: 'rgba(255,255,255,0.12)', fill: 'rgba(255,255,255,0.03)', rune: 'rgba(255,255,255,0.15)' },
    blocked:   { border: 'rgba(239,68,68,0.2)', fill: 'rgba(239,68,68,0.04)', rune: 'rgba(239,68,68,0.15)' },
  },
  // Mage — blue/cyan
  3: {
    chosen:    { border: '#38bdf8', fill: 'rgba(56,189,248,0.15)', glow: '0 0 16px rgba(56,189,248,0.6), inset 0 0 12px rgba(56,189,248,0.15)', rune: '#7dd3fc', badge: 'rgba(56,189,248,0.25)' },
    available: { border: '#38bdf880', fill: 'rgba(56,189,248,0.06)', glow: '0 0 10px rgba(56,189,248,0.3)', rune: '#38bdf899' },
    locked:    { border: 'rgba(255,255,255,0.12)', fill: 'rgba(255,255,255,0.03)', rune: 'rgba(255,255,255,0.15)' },
    blocked:   { border: 'rgba(239,68,68,0.2)', fill: 'rgba(239,68,68,0.04)', rune: 'rgba(239,68,68,0.15)' },
  },
};

const defaultColors = classColors[1];

/* ========== Hexagon SVG clip path (used inline) ========== */
const HEX_POINTS = '50,0 93.3,25 93.3,75 50,100 6.7,75 6.7,25';

/* ========== Component ========== */
const PlayerNodeComponent = ({ data, selected }: NodeProps) => {
  const d = data as PlayerNodeData;
  const skillsCount = d.skills?.length ?? 0;
  const state = d.visualState ?? 'locked';
  const nodeType = d.node_type ?? 'regular';
  const isLarge = nodeType === 'root' || nodeType === 'subclass_choice';
  const isClickable = state === 'available' || state === 'chosen';
  const colors = classColors[d.classId] ?? defaultColors;
  const stateColors = colors[state];

  const size = isLarge ? 70 : 40;
  const rune = getRune(d.level_ring, d.sort_order ?? 0);
  const runeSize = isLarge ? 'text-[22px]' : 'text-[16px]';

  const opacity = state === 'locked' ? 0.4 : state === 'blocked' ? 0.3 : 1;
  const animClass = state === 'available' ? 'animate-pulse' : '';

  return (
    <div
      className={`
        relative flex items-center justify-center
        transition-all duration-300 ease-site
        ${isClickable ? 'cursor-pointer' : 'cursor-default'}
        ${animClass}
      `}
      style={{ width: size, height: size, opacity }}
      title={
        state === 'locked'
          ? `Требуется уровень ${d.level_ring}`
          : state === 'blocked'
            ? 'Альтернативная ветка выбрана'
            : d.name
      }
    >
      {/* Handle top */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-[3px] !h-[3px] !bg-transparent !border-0 !-top-px"
      />

      {/* Hexagon shape via SVG */}
      <svg
        viewBox="0 0 100 100"
        className="absolute inset-0 w-full h-full"
        style={{ filter: state === 'chosen' || state === 'available' ? `drop-shadow(${stateColors.glow.split(',')[0]})` : undefined }}
      >
        {/* Glow background for chosen */}
        {state === 'chosen' && (
          <polygon
            points={HEX_POINTS}
            fill={stateColors.fill}
            stroke="none"
          />
        )}

        {/* Main hexagon border */}
        <polygon
          points={HEX_POINTS}
          fill={stateColors.fill}
          stroke={stateColors.border}
          strokeWidth={state === 'chosen' ? 3 : state === 'available' ? 2.5 : 1.5}
        />

        {/* Inner hexagon line (decorative) */}
        {isLarge && (
          <polygon
            points="50,12 83,30 83,70 50,88 17,70 17,30"
            fill="none"
            stroke={stateColors.border}
            strokeWidth={0.8}
            opacity={0.3}
          />
        )}
      </svg>

      {/* Rune symbol */}
      <span
        className={`
          relative z-10 select-none font-bold leading-none
          ${runeSize}
          ${isClickable ? 'hover:brightness-150' : ''}
        `}
        style={{
          color: stateColors.rune,
          textShadow: state === 'chosen'
            ? `0 0 8px ${stateColors.rune}, 0 0 16px ${stateColors.rune}40`
            : undefined,
        }}
      >
        {rune}
      </span>

      {/* Level badge (large nodes only) */}
      {isLarge && (
        <span
          className="absolute -top-1.5 -right-1.5 z-10 text-[8px] font-medium rounded-full w-[16px] h-[16px] flex items-center justify-center border"
          style={{
            background: '#0e0e1a',
            borderColor: stateColors.border,
            color: state === 'chosen' ? stateColors.rune : 'rgba(255,255,255,0.5)',
          }}
        >
          {d.level_ring}
        </span>
      )}

      {/* Skills count badge */}
      {skillsCount > 0 && (
        <span
          className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 z-10 text-[7px] font-bold rounded-full px-1 min-w-[14px] text-center leading-[13px]"
          style={{
            background: state === 'chosen' ? (colors.chosen.badge) : 'rgba(100,130,255,0.2)',
            color: state === 'chosen' ? stateColors.rune : 'rgba(100,130,255,0.8)',
          }}
        >
          {skillsCount}
        </span>
      )}

      {/* Blocked X overlay */}
      {state === 'blocked' && (
        <span className="absolute inset-0 flex items-center justify-center z-10 text-red-500/40 text-lg font-bold">
          ✕
        </span>
      )}

      {/* Subclass name label below */}
      {nodeType === 'subclass_choice' && d.name && (
        <span
          className="absolute -bottom-5 left-1/2 -translate-x-1/2 z-10 whitespace-nowrap select-none text-[9px] font-bold uppercase tracking-[0.15em]"
          style={{
            color: state === 'chosen' ? stateColors.rune : 'rgba(255,255,255,0.35)',
            textShadow: state === 'chosen'
              ? `0 0 6px ${stateColors.rune}60`
              : undefined,
            fontFamily: 'serif',
          }}
        >
          {d.name}
        </span>
      )}

      {/* Selected ring */}
      {selected && (
        <div
          className="absolute inset-[-4px] rounded-full border-2 border-site-blue/60 pointer-events-none"
        />
      )}

      {/* Handle bottom */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-[3px] !h-[3px] !bg-transparent !border-0 !-bottom-px"
      />
    </div>
  );
};

export default memo(PlayerNodeComponent);
