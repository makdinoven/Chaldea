import { memo } from 'react';
import { BaseEdge, getStraightPath, type EdgeProps } from 'reactflow';

/**
 * Edge rendering shared by the player skill wheel and the admin wheel editor,
 * so both draw the same picture.
 */

/**
 * Map class_id -> edge gradients (DB: 1=Warrior, 2=Rogue, 3=Mage).
 *
 * Three tiers: `bright` when both ends are taken, `dim` when one is, `faint`
 * for untouched branches. Untouched links used to be the same neutral white for
 * every class, which left the combined wheel looking like one grey web.
 */
export const classGradientColors: Record<
  number,
  { bright: [string, string]; dim: [string, string]; faint: [string, string] }
> = {
  1: {
    bright: ['#fbbf24', '#ef4444'],  // Warrior — gold → red
    dim: ['rgba(251,191,36,0.3)', 'rgba(239,68,68,0.2)'],
    faint: ['rgba(248,113,113,0.4)', 'rgba(248,113,113,0.22)'],
  },
  2: {
    bright: ['#fbbf24', '#34d399'],  // Rogue — gold → green
    dim: ['rgba(251,191,36,0.3)', 'rgba(52,211,153,0.2)'],
    faint: ['rgba(52,211,153,0.4)', 'rgba(52,211,153,0.22)'],
  },
  3: {
    bright: ['#a78bfa', '#38bdf8'],  // Mage — purple → blue
    dim: ['rgba(167,139,250,0.3)', 'rgba(56,189,248,0.2)'],
    faint: ['rgba(56,189,248,0.4)', 'rgba(56,189,248,0.22)'],
  },
};

export const defaultGradient = classGradientColors[1];

/** A link inside one class tree, coloured by how far the player has walked it. */
export const GradientEdge = memo(({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps) => {
  // Straight, centre-to-centre. Orthogonal routing turned the rotated sectors
  // of the combined wheel into staircases.
  const [edgePath] = getStraightPath({ sourceX, sourceY, targetX, targetY });

  const gradientId = `gradient-${id}`;
  const colors = (data?.colors ?? defaultGradient.faint) as [string, string];
  const strokeWidth = (data?.strokeWidth ?? 1.5) as number;
  const glowing = (data?.glowing ?? false) as boolean;

  return (
    <>
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={colors[0]} />
          <stop offset="100%" stopColor={colors[1]} />
        </linearGradient>
      </defs>
      {/* Glow layer */}
      {glowing && (
        <BaseEdge
          id={`${id}-glow`}
          path={edgePath}
          style={{
            stroke: `url(#${gradientId})`,
            strokeWidth: strokeWidth + 4,
            opacity: 0.3,
            filter: 'blur(3px)',
          }}
        />
      )}
      {/* Main line */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{ stroke: `url(#${gradientId})`, strokeWidth }}
      />
    </>
  );
});

/**
 * Link between two class sectors of the combined wheel. Purely scenic — a
 * character can only ever choose nodes in its own class tree, so these are
 * drawn as severed, dashed lines rather than as a walkable path.
 */
export const BridgeEdge = memo(({ id, sourceX, sourceY, targetX, targetY }: EdgeProps) => {
  const [edgePath] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  return (
    <BaseEdge
      id={id}
      path={edgePath}
      style={{
        stroke: 'rgba(255,255,255,0.14)',
        strokeWidth: 1.5,
        strokeDasharray: '2 10',
      }}
    />
  );
});
