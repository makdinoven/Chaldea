import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { TreeNodeInTreeResponse, NodeVisualState } from './types';

interface PlayerNodeData extends TreeNodeInTreeResponse {
  visualState: NodeVisualState;
  classId: number;
  /** Node belongs to another class's tree: readable, but never choosable. */
  foreign?: boolean;
  /**
   * Rendered inside the admin wheel editor: same look the players get, but
   * every node keeps its name and ring visible, nothing is dimmed, and the
   * connection handles are grabbable.
   */
  adminView?: boolean;
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

/* DB class IDs: 1=Warrior (red), 2=Rogue (emerald), 3=Mage (cyan) */
const CLASS_ACCENTS: Record<number, { base: string; light: string; rgb: string }> = {
  1: { base: '#f87171', light: '#fca5a5', rgb: '248,113,113' },
  2: { base: '#34d399', light: '#6ee7b7', rgb: '52,211,153' },
  3: { base: '#38bdf8', light: '#7dd3fc', rgb: '56,189,248' },
};

/**
 * Builds a node palette from one class accent.
 *
 * Every state keeps the class hue — an untaken node used to be the same grey
 * for all three classes, which made the combined wheel unreadable: you could
 * not tell whose branch you were looking at until something was chosen.
 * "blocked" stays red on purpose: that is a rule, not a class.
 */
const buildClassColors = ({ base, light, rgb }: { base: string; light: string; rgb: string }): ClassColors => ({
  chosen: {
    border: base,
    fill: `rgba(${rgb},0.15)`,
    glow: `0 0 16px rgba(${rgb},0.6), inset 0 0 12px rgba(${rgb},0.15)`,
    rune: light,
    badge: `rgba(${rgb},0.25)`,
  },
  available: {
    border: `${base}80`,
    fill: `rgba(${rgb},0.06)`,
    glow: `0 0 10px rgba(${rgb},0.3)`,
    rune: `${base}99`,
  },
  locked: {
    border: `rgba(${rgb},0.35)`,
    fill: `rgba(${rgb},0.05)`,
    rune: `rgba(${rgb},0.4)`,
  },
  blocked: {
    border: 'rgba(239,68,68,0.2)',
    fill: 'rgba(239,68,68,0.04)',
    rune: 'rgba(239,68,68,0.15)',
  },
});

const classColors: Record<number, ClassColors> = Object.fromEntries(
  Object.entries(CLASS_ACCENTS).map(([id, accent]) => [Number(id), buildClassColors(accent)]),
);

const defaultColors = classColors[1];

/**
 * Both handles sit dead centre of the hex, so the straight edges the player
 * view draws run centre-to-centre instead of hanging off the top and bottom
 * points. They stay invisible either way.
 */
const CENTRED_HANDLE_STYLE = {
  top: '50%',
  bottom: 'auto',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: 3,
  height: 3,
  minWidth: 0,
  minHeight: 0,
  background: 'transparent',
  border: 0,
} as const;

/**
 * While editing, the handle covers the whole node instead of being a dot at its
 * centre: a 12px target inside a 40px hex was near impossible to hit. Dragging
 * anywhere on a node now pulls a connection out of it, and dropping anywhere on
 * another node lands it — the canvas runs in ConnectionMode.Loose so either
 * handle accepts the drop. Clicks still reach the node underneath, so selecting
 * a node to edit it works as before.
 *
 * The anchor point ReactFlow draws edges from is the handle's centre, which is
 * the node's centre either way.
 */
const ADMIN_HANDLE_STYLE = {
  top: 0,
  left: 0,
  bottom: 'auto',
  transform: 'none',
  width: '100%',
  height: '100%',
  minWidth: 0,
  minHeight: 0,
  borderRadius: '50%',
  background: 'transparent',
  border: 0,
  zIndex: 5,
} as const;

/* ========== Hexagon SVG clip path (used inline) ========== */
const HEX_POINTS = '50,0 93.3,25 93.3,75 50,100 6.7,75 6.7,25';

/* ========== Component ========== */
const PlayerNodeComponent = ({ data, selected }: NodeProps) => {
  const d = data as PlayerNodeData;
  const skillsCount = d.skills?.length ?? 0;
  const state = d.visualState ?? 'locked';
  const nodeType = d.node_type ?? 'regular';
  const isLarge = nodeType === 'root' || nodeType === 'subclass_choice';
  const isForeign = d.foreign ?? false;
  const isAdmin = d.adminView ?? false;
  const handleStyle = isAdmin ? ADMIN_HANDLE_STYLE : CENTRED_HANDLE_STYLE;
  // Foreign nodes stay clickable: the panel they open is read-only, and being
  // able to inspect another class's branches is the whole point of showing them.
  const isClickable = isForeign || state === 'available' || state === 'chosen';
  const colors = classColors[d.classId] ?? defaultColors;
  const stateColors = colors[state];

  const size = isLarge ? 70 : 40;
  const rune = getRune(d.level_ring, d.sort_order ?? 0);
  const runeSize = isLarge ? 'text-[22px]' : 'text-[16px]';

  // The admin is editing, not playing: nothing there is dimmed or pulsing.
  // Otherwise another class's node is always fainter than anything in the
  // player's own sector — a locked node of your own class still outranks it.
  const opacity = isAdmin
    ? 1
    : isForeign ? 0.3 : state === 'locked' ? 0.5 : state === 'blocked' ? 0.3 : 1;
  // Nothing in another class's tree should pulse as if it were waiting to be taken.
  const animClass = !isForeign && !isAdmin && state === 'available' ? 'animate-pulse' : '';

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
        isForeign
          ? `${d.name} — дерево другого класса`
          : state === 'locked'
            ? `Требуется уровень ${d.level_ring}`
            : state === 'blocked'
              ? 'Альтернативная ветка выбрана'
              : d.name
      }
    >
      {/* Handles — both centred, see CENTRED_HANDLE_STYLE */}
      <Handle
        type="target"
        position={Position.Top}
        style={handleStyle}
        className={isAdmin ? '!cursor-crosshair' : undefined}
      />

      {/* Hexagon shape via SVG */}
      <svg
        viewBox="0 0 100 100"
        className="absolute inset-0 w-full h-full"
        style={{ filter: 'glow' in stateColors ? `drop-shadow(${stateColors.glow.split(',')[0]})` : undefined }}
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

      {/* Level badge — large nodes always, every node while editing */}
      {(isLarge || isAdmin) && (
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

      {/* Name label below — subclass picks always, every node while editing */}
      {(nodeType === 'subclass_choice' || isAdmin) && d.name && (
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

      <Handle
        type="source"
        position={Position.Bottom}
        style={handleStyle}
        className={isAdmin ? '!cursor-crosshair hover:!bg-gold/15' : undefined}
      />
    </div>
  );
};

export default memo(PlayerNodeComponent);
