import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { TreeNodeInTreeResponse, NodeVisualState } from './types';
import { playerNodeSize } from './nodeSizes';

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
interface StateColors {
  border: string;
  fill: string;
  /** CSS drop-shadow value, applied to the whole disc. */
  glow: string;
  rune: string;
  badge: string;
}

interface ClassColors {
  chosen: StateColors;
  available: StateColors;
  locked: StateColors;
  blocked: StateColors;
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
 * The nodes sit on a painted, busy backdrop, so every state has to hold its own
 * against it: full-strength borders, a lit rune, and a glow that separates the
 * disc from whatever is behind it. The opaque core drawn under the fill (see
 * CORE_FILL) is what stops the art bleeding through and washing the node out.
 *
 * Every state keeps the class hue, so an untaken node still says whose branch
 * it is. "blocked" stays red on purpose: that is a rule, not a class.
 */
const buildClassColors = ({ base, light, rgb }: { base: string; light: string; rgb: string }): ClassColors => ({
  chosen: {
    border: light,
    fill: `rgba(${rgb},0.38)`,
    glow: `drop-shadow(0 0 10px rgba(${rgb},0.95)) drop-shadow(0 0 22px rgba(${rgb},0.55))`,
    rune: '#ffffff',
    badge: `rgba(${rgb},0.35)`,
  },
  available: {
    border: base,
    fill: `rgba(${rgb},0.26)`,
    glow: `drop-shadow(0 0 8px rgba(${rgb},0.8)) drop-shadow(0 0 18px rgba(${rgb},0.4))`,
    rune: light,
    badge: `rgba(${rgb},0.3)`,
  },
  locked: {
    border: `rgba(${rgb},0.9)`,
    fill: `rgba(${rgb},0.16)`,
    glow: `drop-shadow(0 0 6px rgba(${rgb},0.5))`,
    rune: light,
    badge: `rgba(${rgb},0.25)`,
  },
  blocked: {
    border: 'rgba(239,68,68,0.75)',
    fill: 'rgba(239,68,68,0.14)',
    glow: 'drop-shadow(0 0 5px rgba(239,68,68,0.4))',
    rune: 'rgba(252,165,165,0.75)',
    badge: 'rgba(239,68,68,0.25)',
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

/* ========== Node shape ==========
   Drawn on a 0..100 viewBox and scaled to the node's size, so the stroke
   weights below read the same whatever that size is. */
const OUTER_RADIUS = 48;
const INNER_RADIUS = 37;

/** Opaque core, so the painted backdrop never shows through a node. */
const CORE_FILL = 'rgba(9,9,16,0.9)';

/* ========== Component ========== */
const PlayerNodeComponent = ({ data, selected }: NodeProps) => {
  const d = data as PlayerNodeData;
  const skillsCount = d.skills?.length ?? 0;
  const state = d.visualState ?? 'locked';
  const nodeType = d.node_type ?? 'regular';
  // Roots are drawn like any other node — see NODE_SIZE_LARGE for why.
  const isLarge = nodeType === 'subclass_choice';
  const isForeign = d.foreign ?? false;
  const isAdmin = d.adminView ?? false;
  const handleStyle = isAdmin ? ADMIN_HANDLE_STYLE : CENTRED_HANDLE_STYLE;
  // Foreign nodes stay clickable: the panel they open is read-only, and being
  // able to inspect another class's branches is the whole point of showing them.
  const isClickable = isForeign || state === 'available' || state === 'chosen';
  const colors = classColors[d.classId] ?? defaultColors;
  const stateColors = colors[state];

  const size = playerNodeSize(nodeType);
  const rune = getRune(d.level_ring, d.sort_order ?? 0);
  const runeSize = isLarge ? 'text-[28px]' : 'text-[19px]';

  // The admin is editing, not playing: nothing there is dimmed or pulsing.
  // Otherwise another class's node is always fainter than anything in the
  // player's own sector — a locked node of your own class still outranks it.
  // Nodes stay at full strength: they have to read against the painted wheel.
  // Only another class's nodes step back, and only enough to rank below yours.
  const opacity = isAdmin ? 1 : isForeign ? 0.65 : state === 'blocked' ? 0.5 : 1;
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

      {/* Disc */}
      <svg
        viewBox="0 0 100 100"
        className="absolute inset-0 w-full h-full"
        style={{ filter: stateColors.glow }}
      >
        {/* Opaque core first, so the art behind cannot wash the node out */}
        <circle cx={50} cy={50} r={OUTER_RADIUS} fill={CORE_FILL} stroke="none" />

        {/* Main ring */}
        <circle
          cx={50}
          cy={50}
          r={OUTER_RADIUS}
          fill={stateColors.fill}
          stroke={stateColors.border}
          strokeWidth={state === 'chosen' ? 4 : state === 'available' ? 3.5 : 2.5}
        />

        {/* Inner ring (decorative) */}
        {isLarge && (
          <circle
            cx={50}
            cy={50}
            r={INNER_RADIUS}
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
          textShadow: '0 0 6px rgba(0,0,0,0.9)',
        }}
      >
        {rune}
      </span>

      {/* Level badge — large nodes always, every node while editing */}
      {(isLarge || isAdmin) && (
        <span
          className="absolute -top-1 -right-1 z-10 text-[9px] font-medium rounded-full w-[18px] h-[18px] flex items-center justify-center border"
          style={{
            background: '#0e0e1a',
            borderColor: stateColors.border,
            color: stateColors.rune,
          }}
        >
          {d.level_ring}
        </span>
      )}

      {/* Skills count badge */}
      {skillsCount > 0 && (
        <span
          className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 z-10 text-[8px] font-bold rounded-full px-1.5 min-w-[16px] text-center leading-[15px]"
          style={{
            background: '#0e0e1a',
            color: stateColors.rune,
            border: `1px solid ${stateColors.border}`,
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
          className="absolute -bottom-[18px] left-1/2 -translate-x-1/2 z-10 whitespace-nowrap select-none text-[10px] font-bold uppercase tracking-[0.15em]"
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
          className="absolute inset-[-5px] rounded-full border-2 border-site-blue/60 pointer-events-none"
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
