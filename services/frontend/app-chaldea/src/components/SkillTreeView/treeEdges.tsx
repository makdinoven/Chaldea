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
  { bright: [string, string]; strong: [string, string]; dim: [string, string]; faint: [string, string] }
> = {
  1: {
    bright: ['#fbbf24', '#ef4444'],  // Warrior — gold → red
    strong: ['rgba(252,165,165,0.95)', 'rgba(248,113,113,0.7)'],
    dim: ['rgba(251,191,36,0.3)', 'rgba(239,68,68,0.2)'],
    faint: ['rgba(248,113,113,0.4)', 'rgba(248,113,113,0.22)'],
  },
  2: {
    bright: ['#fbbf24', '#34d399'],  // Rogue — gold → green
    strong: ['rgba(110,231,183,0.95)', 'rgba(52,211,153,0.7)'],
    dim: ['rgba(251,191,36,0.3)', 'rgba(52,211,153,0.2)'],
    faint: ['rgba(52,211,153,0.4)', 'rgba(52,211,153,0.22)'],
  },
  3: {
    bright: ['#a78bfa', '#38bdf8'],  // Mage — purple → blue
    strong: ['rgba(125,211,252,0.95)', 'rgba(56,189,248,0.7)'],
    dim: ['rgba(167,139,250,0.3)', 'rgba(56,189,248,0.2)'],
    faint: ['rgba(56,189,248,0.4)', 'rgba(56,189,248,0.22)'],
  },
};

export const defaultGradient = classGradientColors[1];

/**
 * Beyond this angular span the quadratic stops approximating a circular arc and
 * starts bulging outward — at 60° the midpoint overshoots the true arc by about
 * 1%, at 140° by 63%. Wider links fall back to the plain chord.
 */
const MAX_CURVE_SPAN = (60 * Math.PI) / 180;

/**
 * How far a link may wander off its true arc: a share of its own length, capped
 * in absolute pixels. Without the cap the long links along the outer rings swung
 * hundreds of pixels wide and the wheel turned to spaghetti.
 */
const MAX_WANDER = 0.3;
const MAX_WANDER_PX = 110;

/**
 * Ceiling on the circular bow itself, as a share of the link's length and in
 * absolute pixels. Following the ring exactly is right for a short link between
 * neighbours, but a long one that also spans a wide angle gets an arc that
 * swings hundreds of pixels off its chord and reads as a stray loop rather than
 * as a path between two nodes.
 */
const MAX_BOW = 0.35;
const MAX_BOW_PX = 180;

/**
 * A stable pair of numbers in -1..1 derived from a link's id.
 *
 * Stable matters: the bend has to be the same on every render, or the wheel
 * would writhe as React re-draws it. FNV-1a, then two slices of the hash.
 */
const wanderOf = (seed: string): [number, number] => {
  let hash = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  const first = ((hash & 0xffff) / 0xffff) * 2 - 1;
  const magnitude = ((hash >>> 16) & 0x7fff) / 0x7fff;
  // Half the links are given control points pushed the same way, which bows
  // them to one side; the other half get opposing ones, which draws them out
  // into a shallow S. Mixing the two is what makes the web look grown rather
  // than plotted.
  const snake = ((hash >>> 31) & 1) === 1;
  const second = snake
    ? -Math.sign(first || 1) * magnitude
    : Math.sign(first || 1) * magnitude;
  return [first, second];
};

/**
 * Path for a link on the wheel: an arc that follows the rings, bent by hand.
 *
 * The base curve is circular — the wheel is centred on the flow origin, so a
 * link's ends are two polar points, and a control point on the bisecting ray at
 * `meanRadius / cos(halfSpan)` hugs the circle through both of them. A purely
 * radial link has no span and reduces to the straight chord.
 *
 * That base is then raised to a cubic and its two control points are pushed
 * sideways by amounts drawn from the link's id, so no two links bow alike:
 * matching signs give a lopsided bow, opposing ones a soft S. This is what
 * keeps the wheel from looking like a technical drawing — and it is the only
 * bend radial links get, since their arc is a straight line.
 */
export const linkPath = (
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  seed: string,
): string => {
  const r1 = Math.hypot(sourceX, sourceY);
  const r2 = Math.hypot(targetX, targetY);

  // Control point of the circular arc, or the chord midpoint when there is none.
  let arcX = (sourceX + targetX) / 2;
  let arcY = (sourceY + targetY) / 2;
  if (r1 >= 1 && r2 >= 1) {
    const a1 = Math.atan2(sourceY, sourceX);
    const a2 = Math.atan2(targetY, targetX);
    let span = a2 - a1;
    while (span > Math.PI) span -= 2 * Math.PI;
    while (span < -Math.PI) span += 2 * Math.PI;
    if (Math.abs(span) <= MAX_CURVE_SPAN) {
      const midAngle = a1 + span / 2;
      const controlRadius = ((r1 + r2) / 2) / Math.cos(span / 2);
      arcX = Math.cos(midAngle) * controlRadius;
      arcY = Math.sin(midAngle) * controlRadius;
    }
  }

  // Rein the bow in towards the chord if the arc swings too wide.
  const midX = (sourceX + targetX) / 2;
  const midY = (sourceY + targetY) / 2;
  const bowX = arcX - midX;
  const bowY = arcY - midY;
  const bow = Math.hypot(bowX, bowY);
  const bowLimit = Math.min(Math.hypot(targetX - sourceX, targetY - sourceY) * MAX_BOW, MAX_BOW_PX);
  if (bow > bowLimit) {
    arcX = midX + (bowX / bow) * bowLimit;
    arcY = midY + (bowY / bow) * bowLimit;
  }

  // Quadratic -> cubic, which leaves the curve untouched.
  let c1x = sourceX + (2 / 3) * (arcX - sourceX);
  let c1y = sourceY + (2 / 3) * (arcY - sourceY);
  let c2x = targetX + (2 / 3) * (arcX - targetX);
  let c2y = targetY + (2 / 3) * (arcY - targetY);

  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const length = Math.hypot(dx, dy);
  if (length > 1) {
    const nx = -dy / length;
    const ny = dx / length;
    const [w1, w2] = wanderOf(seed);
    const wander = Math.min(length * MAX_WANDER, MAX_WANDER_PX);
    c1x += nx * wander * w1;
    c1y += ny * wander * w1;
    c2x += nx * wander * w2;
    c2y += ny * wander * w2;
  }

  return `M ${sourceX},${sourceY} C ${c1x},${c1y} ${c2x},${c2y} ${targetX},${targetY}`;
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
  const edgePath = curved
    ? linkPath(sourceX, sourceY, targetX, targetY, id)
    : straightPath;

  const gradientId = `gradient-${id}`;
  const colors = (data?.colors ?? defaultGradient.faint) as [string, string];
  const strokeWidth = (data?.strokeWidth ?? 1.5) as number;
  const glowing = (data?.glowing ?? false) as boolean;
  const opacity = (data?.opacity ?? 1) as number;
  // A dark casing under the line, so it stays readable where it crosses a
  // bright patch of the painted backdrop.
  const casing = (data?.casing ?? false) as boolean;

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
      {/* Dark casing */}
      {casing && (
        <BaseEdge
          id={`${id}-casing`}
          path={edgePath}
          style={{
            stroke: 'rgba(6,6,12,0.75)',
            strokeWidth: strokeWidth + 3,
            opacity,
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
