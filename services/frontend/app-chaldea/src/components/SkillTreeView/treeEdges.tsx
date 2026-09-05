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

/**
 * Beyond this angular span the quadratic stops approximating a circular arc and
 * starts bulging outward — at 60° the midpoint overshoots the true arc by about
 * 1%, at 140° by 63%. Wider links are drawn straight instead.
 */
const MAX_CURVE_SPAN = (60 * Math.PI) / 180;

/**
 * Path for a link that follows the wheel rather than cutting across it.
 *
 * The wheel is centred on the flow origin, so a link's two ends are simply two
 * polar points. A quadratic Bézier whose control point sits on the bisecting
 * ray at radius `meanRadius / cos(halfSpan)` hugs the circle through both ends;
 * for a purely radial link the span is zero and it degenerates to the straight
 * line, which is what a link between rings should be.
 */
const arcPath = (sourceX: number, sourceY: number, targetX: number, targetY: number): string => {
  const r1 = Math.hypot(sourceX, sourceY);
  const r2 = Math.hypot(targetX, targetY);
  if (r1 < 1 || r2 < 1) return `M ${sourceX},${sourceY} L ${targetX},${targetY}`;

  const a1 = Math.atan2(sourceY, sourceX);
  const a2 = Math.atan2(targetY, targetX);
  // Shortest way round, so a link never bows the long way about the wheel.
  let span = a2 - a1;
  while (span > Math.PI) span -= 2 * Math.PI;
  while (span < -Math.PI) span += 2 * Math.PI;

  if (Math.abs(span) > MAX_CURVE_SPAN) {
    return `M ${sourceX},${sourceY} L ${targetX},${targetY}`;
  }

  const midAngle = a1 + span / 2;
  const controlRadius = ((r1 + r2) / 2) / Math.cos(span / 2);
  const cx = Math.cos(midAngle) * controlRadius;
  const cy = Math.sin(midAngle) * controlRadius;
  return `M ${sourceX},${sourceY} Q ${cx},${cy} ${targetX},${targetY}`;
};

/** A link inside one class tree, coloured by how far the player has walked it. */
export const GradientEdge = memo(({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps) => {
  // On the wheel, links bow along the rings instead of cutting the middle out
  // of it. Elsewhere — the single-class view — there is no centre to bow
  // around, so they stay straight. (Orthogonal routing was worse than either:
  // it turned every diagonal into a staircase.)
  const curved = (data?.curved ?? false) as boolean;
  const [straightPath] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  const edgePath = curved ? arcPath(sourceX, sourceY, targetX, targetY) : straightPath;

  const gradientId = `gradient-${id}`;
  const colors = (data?.colors ?? defaultGradient.faint) as [string, string];
  const strokeWidth = (data?.strokeWidth ?? 1.5) as number;
  const glowing = (data?.glowing ?? false) as boolean;
  const opacity = (data?.opacity ?? 1) as number;

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
        style={{ stroke: `url(#${gradientId})`, strokeWidth, opacity }}
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
