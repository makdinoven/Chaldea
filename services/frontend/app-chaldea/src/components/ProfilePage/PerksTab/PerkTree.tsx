import React, { useMemo } from 'react';
import { motion } from 'motion/react';
import { isPerkActive } from '../../../types/perks';
import type { CharacterPerk } from '../../../types/perks';
import PerkNode, { HEX_SIZE } from './PerkNode';
import perksBackdrop from '../../../assets/perksWheelBackdrop.png';

/* ── Backdrop ── */

/**
 * The artwork is a wheel of five equal sectors, centred in its own square file
 * and painted on the same bearings the tree uses: red straight up (-90°), then
 * gold (-18°), blue (+54°), green (+126°) and purple (-162°) — measured off the
 * picture at -89.5°, -21.5°, +50°, +125° and -162°, so within a few degrees of
 * the ideal 72° star, and no rotation of the picture improves on that, so it is
 * drawn square-on.
 *
 * The layout is measured off it rather than the other way round: the tiers fill
 * each 72° wedge between the picture's central disc and its rim rings (see
 * `TREE_HALF` and the band constants below).
 *
 * So it is drawn inside the SVG rather than behind the panel, anchored on the
 * tree's own centre and measured in the tree's own units. The viewBox then
 * scales art and nodes together, and the two cannot drift apart however the
 * panel is sized — which is what went wrong when it was a CSS background: it
 * was centred on the panel, and the panel's centre is not the tree's.
 */
/** Panel backing behind the constellation and the mobile list. */
const PerkBackdrop = () => (
  <div className="absolute inset-0 overflow-hidden rounded-card">
    <div
      className="absolute inset-0"
      style={{
        background:
          'radial-gradient(ellipse at 50% 45%, rgba(20,18,44,0.95) 0%, rgba(8,8,24,0.98) 55%, rgba(4,4,16,1) 100%)',
      }}
    />
  </div>
);

/* ── Config ── */

interface PerkTreeProps {
  perks: CharacterPerk[];
  onSelectPerk: (perk: CharacterPerk) => void;
}

const CATEGORY_CONFIG: Record<string, { label: string; color: string }> = {
  combat:      { label: 'Бой',           color: 'rgba(248,113,113,0.7)' },
  trade:       { label: 'Торговля',      color: 'rgba(240,217,92,0.7)' },
  exploration: { label: 'Исследование',  color: 'rgba(118,166,189,0.7)' },
  progression: { label: 'Прогрессия',    color: 'rgba(136,179,50,0.7)' },
  usage:       { label: 'Использование', color: 'rgba(184,117,189,0.7)' },
};

const CATEGORY_ORDER = ['combat', 'trade', 'exploration', 'progression', 'usage'];

/**
 * Where each branch points, in degrees, 0 = right and growing clockwise:
 * `index * 72 - 90`, red straight up and the rest following clockwise, which is
 * what the backdrop is painted on.
 *
 * They used to be measured off the older, hand-painted rosette, whose lobes
 * were uneven, and that left each fan a few degrees off its sector once the
 * even five-sector wheel replaced it — trade and exploration by 7-8°, enough to
 * read as crooked. An even star is the whole point now: every fan sits in the
 * middle of its own sector.
 */
const BRANCH_BEARING: Record<string, number> = {
  combat: -90,          // красный, вверх
  trade: -18,           // золотой, вправо-вверх
  exploration: 54,      // синий, вправо-вниз
  progression: 126,     // зелёный, влево-вниз
  usage: -162,          // фиолетовый, влево-вверх
};

/**
 * How far the backdrop is nudged to bring its composition onto the hub, as a
 * fraction of its rendered size. Positive moves the picture right and down.
 *
 * Aligned on the ring around the central disc, because that is the feature the
 * eye compares with the hub hexagon sitting inside it. A least-squares circle
 * through it lands at (625.5, 605.8) with r=96.9 in the 1254px file (residual
 * 1.0px), that is 1.0px left and 20.7px above the middle of the image, so the
 * picture is pushed back by exactly that.
 *
 * The picture is not concentric with itself — its rim ring fits at (624.8,
 * 620.3), 14.4px below the disc — so aligning the disc leaves the rim about 9px
 * low in the frame, where a decorative circle against the edge is far less
 * noticeable than a hub sitting off-centre in its disc. Rim-based alignment is
 * what put the hub 2.5px right of the disc before.
 */
const ART_NUDGE_X = 0.0008;
const ART_NUDGE_Y = 0.0165;

/**
 * The wheel's rim sits at 0.930 of the file's half-size, so drawn edge to edge
 * it would leave a black ring inside the frame. Scaling by 1/0.930 puts the
 * painted rim on the frame instead, and carries the coloured band out to the
 * outermost ring of nodes (0.85 of the radius) with the gold rim rings still
 * inside the circle.
 */
const ART_SCALE = 1.0757;

const RARITY_LABELS: Record<string, string> = {
  common: 'Обычный',
  rare: 'Редкий',
  legendary: 'Легендарный',
};

const RARITY_BORDER: Record<string, string> = {
  common: 'border-white/20',
  rare: 'border-purple-400/40',
  legendary: 'border-gold/40',
};

const RARITY_BG: Record<string, string> = {
  common: '',
  rare: 'bg-purple-400/5',
  legendary: 'bg-gold/5',
};

function hexPoints(cx: number, cy: number, size: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 2;
    pts.push(`${cx + size * Math.cos(angle)},${cy + size * Math.sin(angle)}`);
  }
  return pts.join(' ');
}

/* ── Constellation layout v3: arcs that fill the painted wedge ── */

/**
 * The frame is fixed, not fitted to the data: `half` is a constant, so the
 * wheel behind the tree and the tree itself always share one scale. It keeps
 * the viewBox this tab has had since the art was aligned (1132.8 units across
 * the circle's 760px), which is what makes the two line up.
 */
const TREE_HALF = 566.4;

/**
 * Where the art's own rings sit, as fractions of `TREE_HALF`, measured on the
 * rendered wheel: the gold ring around the central disc at 0.172 (65px of the
 * 380px radius) and the innermost of the rim rings at 0.876 (333px). Nodes live
 * between the two, so the hub disc stays clear and nothing runs into the rim.
 */
const ART_DISC_FRACTION = 0.172;
const ART_RING_FRACTION = 0.876;

/**
 * Clearance from a hexagon's corner to the art's rings and to a sector edge, in
 * the tree's units — about 13px and 15px on the rendered 760px circle, which is
 * enough for the painted gold boundary ray to read as a gap rather than a line
 * through the hexagons.
 */
const ART_CLEARANCE = 20;
const BOUNDARY_CLEARANCE = 22;

/** Radial band the tiers are spread across. */
const BAND_INNER = ART_DISC_FRACTION * TREE_HALF + HEX_SIZE + ART_CLEARANCE;
const BAND_OUTER = ART_RING_FRACTION * TREE_HALF - HEX_SIZE - ART_CLEARANCE;

/** Hexagons touch flat to flat at 2·inradius; this keeps a visible gap. */
const MIN_NODE_SPACING = HEX_SIZE * 2.3;

/** More tiers than this leaves the arcs too thin to read as rings. */
const MAX_TIERS = 7;

interface NodePos {
  perk: CharacterPerk;
  x: number;
  y: number;
  category: string;
}

/** Half the angle a tier may use at this radius, in degrees. */
function tierHalfSpan(radius: number, sectorHalfDeg: number): number {
  const blocked = Math.asin(Math.min(1, (HEX_SIZE + BOUNDARY_CLEARANCE) / radius));
  return Math.max(0, sectorHalfDeg - (blocked * 180) / Math.PI);
}

/** Tier radii, evenly spread across the band. */
function tierRadii(tiers: number): number[] {
  if (tiers <= 1) return [BAND_INNER];
  return Array.from(
    { length: tiers },
    (_, i) => BAND_INNER + ((BAND_OUTER - BAND_INNER) * i) / (tiers - 1),
  );
}

/**
 * Split `count` nodes between tiers in proportion to how long each tier's arc
 * is, so an outer tier — with more room — carries more of them and the wedge
 * fills out instead of bunching at the narrow end. Largest remainder, so the
 * counts add up exactly.
 */
function allocate(count: number, radii: number[], sectorHalfDeg: number): number[] {
  const arcs = radii.map((r) => r * ((2 * tierHalfSpan(r, sectorHalfDeg) * Math.PI) / 180));
  const total = arcs.reduce((sum, a) => sum + a, 0) || 1;
  const exact = arcs.map((a) => (count * a) / total);
  const counts = exact.map((x) => Math.floor(x));
  const short = count - counts.reduce((sum, c) => sum + c, 0);
  [...counts.keys()]
    .sort((a, b) => exact[b] - counts[b] - (exact[a] - counts[a]))
    .slice(0, short)
    .forEach((i) => {
      counts[i] += 1;
    });
  return counts;
}

/** Angles within one tier, evenly spread across its usable arc. */
function tierAngles(count: number, radius: number, sectorHalfDeg: number): number[] {
  if (count <= 0) return [];
  if (count === 1) return [0];
  const span = 2 * tierHalfSpan(radius, sectorHalfDeg);
  return Array.from({ length: count }, (_, i) => -span / 2 + (span * i) / (count - 1));
}

/**
 * How many tiers to use. Every option that keeps the hexagons apart is legal,
 * so the pick is the one whose radial step is closest to its angular step: that
 * is what reads as an even constellation rather than rows or columns.
 */
function chooseTiers(count: number, sectorHalfDeg: number): number {
  let best = 1;
  let bestScore = Number.POSITIVE_INFINITY;
  for (let tiers = 1; tiers <= Math.min(MAX_TIERS, count); tiers++) {
    const radii = tierRadii(tiers);
    const counts = allocate(count, radii, sectorHalfDeg);
    const gaps: number[] = [];
    let fits = true;
    radii.forEach((r, i) => {
      if (counts[i] <= 1) return;
      const arc = r * ((2 * tierHalfSpan(r, sectorHalfDeg) * Math.PI) / 180);
      const gap = arc / (counts[i] - 1);
      if (gap < MIN_NODE_SPACING) fits = false;
      gaps.push(gap);
    });
    if (!fits) continue;
    const radialGap = tiers > 1 ? radii[1] - radii[0] : 0;
    const meanGap = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length : radialGap;
    const score = Math.abs(radialGap - meanGap);
    if (score < bestScore - 1e-9) {
      bestScore = score;
      best = tiers;
    }
  }
  return best;
}

/**
 * Place every branch's perks as arcs inside its own painted wedge.
 *
 * Tier order follows the order the perks arrive in, so the first ones stay
 * nearest the hub and depth still reads outwards. The data carries no tier or
 * prerequisite field (no `has_perk` conditions in it either), so that order is
 * the only depth there is to honour, and no connecting lines are drawn.
 */
function computePositions(
  /** Every category, in a fixed order — including the ones with no perks. */
  categories: Array<[string, CharacterPerk[]]>,
  center: number,
): NodePos[] {
  const positions: NodePos[] = [];
  // Sectors are counted over every category, not just the populated ones, so a
  // branch keeps its bearing when another empties out. The backdrop is painted
  // against these bearings; if they shifted with the data it could never line
  // up.
  const catCount = categories.length || 1;
  const sectorHalfDeg = 180 / catCount;

  categories.forEach(([cat, catPerks], catIdx) => {
    if (catPerks.length === 0) return;
    // The painted sector's bearing where there is one; an even share otherwise,
    // so an unknown category still gets a place rather than piling up at 0.
    const bearingDeg = BRANCH_BEARING[cat] ?? catIdx * sectorHalfDeg * 2 - 90;

    const tiers = chooseTiers(catPerks.length, sectorHalfDeg);
    const radii = tierRadii(tiers);
    const counts = allocate(catPerks.length, radii, sectorHalfDeg);

    let taken = 0;
    radii.forEach((radius, tierIdx) => {
      const tierPerks = catPerks.slice(taken, taken + counts[tierIdx]);
      taken += counts[tierIdx];
      tierAngles(tierPerks.length, radius, sectorHalfDeg).forEach((offsetDeg, nodeIdx) => {
        const angle = ((bearingDeg + offsetDeg) * Math.PI) / 180;
        positions.push({
          perk: tierPerks[nodeIdx],
          x: center + radius * Math.cos(angle),
          y: center + radius * Math.sin(angle),
          category: cat,
        });
      });
    });
  });

  return positions;
}

/* ── Component ── */

const PerkTree = ({ perks, onSelectPerk }: PerkTreeProps) => {
  const grouped = useMemo(() => {
    const map = new Map<string, CharacterPerk[]>();
    for (const cat of CATEGORY_ORDER) map.set(cat, []);
    for (const perk of perks) {
      const existing = map.get(perk.category);
      if (existing) existing.push(perk);
      else map.set(perk.category, [perk]);
    }
    for (const [, group] of map) group.sort((a, b) => a.sort_order - b.sort_order);
    return map;
  }, [perks]);

  /** Every category in its fixed order — this is what sets the bearings. */
  const allCategories = useMemo(() => [...grouped.entries()], [grouped]);

  /** Only the ones with perks — for the legend and the mobile list. */
  const categories = useMemo(
    () => allCategories.filter(([, items]) => items.length > 0),
    [allCategories],
  );

  const CENTER = 350;

  const nodePositions = useMemo(
    () => computePositions(allCategories, CENTER),
    [allCategories],
  );

  /*
    A square window centred on the hub, of a fixed size.

    Square and hub-centred on purpose: the frame is a circle and the artwork is
    square, so this is what makes all three agree. It no longer grows with the
    data either — the layout is measured off this window (see `TREE_HALF`), so
    the wheel behind the nodes keeps the same scale whatever the perk list does.
  */
  const half = TREE_HALF;

  const viewBox = `${CENTER - half} ${CENTER - half} ${half * 2} ${half * 2}`;



  if (perks.length === 0) {
    return (
      <div className="relative rounded-card overflow-hidden p-8 text-center">
        <PerkBackdrop />
        <p className="relative text-white/40 text-lg">Перки пока не добавлены</p>
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="relative z-10">
        {/* Desktop: SVG constellation, in a round frame like the skill wheel */}
        <div className="hidden md:block py-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
            className="w-full flex justify-center"
          >
            <div className="relative w-full max-w-[760px] aspect-square rounded-full overflow-hidden bg-[#04041a]">
              <svg
                viewBox={viewBox}
                className="absolute inset-0 w-full h-full"
                xmlns="http://www.w3.org/2000/svg"
              >
              {/* Square art in a square window, both centred on the hub, so
                  it lands where the branches are: scaled so the painted rim
                  meets the frame, then nudged onto the hub. Anything past the
                  window is clipped by the SVG viewport and the round frame. */}
              <image
                href={perksBackdrop}
                x={CENTER - half * ART_SCALE + ART_NUDGE_X * half * 2 * ART_SCALE}
                y={CENTER - half * ART_SCALE + ART_NUDGE_Y * half * 2 * ART_SCALE}
                width={half * 2 * ART_SCALE}
                height={half * 2 * ART_SCALE}
                preserveAspectRatio="xMidYMid slice"
              />
              {/* Just enough darkening for the nodes and labels to read over it */}
              <rect
                x={CENTER - half}
                y={CENTER - half}
                width={half * 2}
                height={half * 2}
                fill="rgba(4,4,16,0.3)"
              />

              {/* Center hexagon (drawn before the nodes, so they sit on top) */}
              <polygon
                points={hexPoints(CENTER, CENTER, 34)}
                fill="rgba(20,18,40,0.9)"
                stroke="rgba(240,217,92,0.4)"
                strokeWidth={2}
              />
              <polygon
                points={hexPoints(CENTER, CENTER, 22)}
                fill="none"
                stroke="rgba(240,217,92,0.15)"
                strokeWidth={0.8}
              />
              <text
                x={CENTER}
                y={CENTER}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={11}
                fontWeight={600}
                fill="rgba(255,249,184,0.9)"
                className="select-none uppercase"
                letterSpacing="0.06em"
                style={{ textShadow: '0 0 10px rgba(240,217,92,0.4)' }}
              >
                Перки
              </text>

              {/* Perk nodes */}
              {nodePositions.map(({ perk, x, y, category }) => (
                <PerkNode
                  key={perk.id}
                  perk={perk}
                  x={x}
                  y={y}
                  categoryColor={CATEGORY_CONFIG[category]?.color ?? 'rgba(255,255,255,0.5)'}
                  onSelect={onSelectPerk}
                />
              ))}

              </svg>
            </div>
          </motion.div>
        </div>

        {/* Mobile: flat list */}
        <div className="relative block md:hidden space-y-6 p-4 rounded-card overflow-hidden">
          <PerkBackdrop />
          <motion.div
            initial="hidden"
            animate="visible"
            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.05 } } }}
          >
            {categories.map(([cat, catPerks]) => {
              const config = CATEGORY_CONFIG[cat] ?? { label: cat, color: 'rgba(255,255,255,0.5)' };
              return (
                <motion.div
                  key={cat}
                  variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}
                  className="mb-5"
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className="h-px flex-1 bg-white/10" />
                    <span className="text-xs font-medium uppercase tracking-wider" style={{ color: config.color }}>
                      {config.label}
                    </span>
                    <div className="h-px flex-1 bg-white/10" />
                  </div>
                  <div className="space-y-2">
                    {catPerks.map((perk) => {
                      const active = isPerkActive(perk);
                      const isLL = perk.rarity === 'legendary' && !active;
                      let prog = 0;
                      if (!active && perk.conditions.length > 0) {
                        const ps = perk.conditions.map((c) => {
                          const entry = perk.progress?.[c.stat ?? c.type];
                          return entry ? Math.min(1, entry.current / entry.required) : 0;
                        });
                        prog = Math.round((ps.reduce((a, b) => a + b, 0) / ps.length) * 100);
                      }
                      return (
                        <button
                          key={perk.id}
                          onClick={() => onSelectPerk(perk)}
                          className={`w-full p-3 rounded-card border text-left transition-all duration-200 cursor-pointer
                            ${RARITY_BORDER[perk.rarity] ?? 'border-white/10'}
                            ${RARITY_BG[perk.rarity] ?? ''}
                            ${active ? 'opacity-100' : 'opacity-60'} hover:opacity-100`}
                        >
                          <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 border
                              ${perk.rarity === 'legendary' ? 'border-gold/30' : perk.rarity === 'rare' ? 'border-purple-400/30' : 'border-white/15'}
                              ${active ? 'bg-white/10' : 'bg-white/5'}`}>
                              <span className={`text-sm ${active ? 'text-white' : 'text-white/30'}`}>
                                {isLL ? '?' : perk.name.slice(0, 2).toUpperCase()}
                              </span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className={`text-sm font-medium truncate ${active ? 'text-white' : 'text-white/50'}`}>
                                {isLL ? '???' : perk.name}
                              </p>
                              <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-[10px] text-white/30">{RARITY_LABELS[perk.rarity] ?? perk.rarity}</span>
                                {!active && prog > 0 && <span className="text-[10px] text-white/40">{prog}%</span>}
                              </div>
                            </div>
                            <div className="flex-shrink-0">
                              {active
                                ? <div className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                                : <div className="w-2.5 h-2.5 rounded-full bg-white/15" />}
                            </div>
                          </div>
                          {!active && prog > 0 && (
                            <div className="mt-2 w-full h-1 rounded-full bg-white/10 overflow-hidden">
                              <div className="h-full rounded-full bg-site-blue/50 transition-all duration-300" style={{ width: `${prog}%` }} />
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      </div>
    </div>
  );
};

export default PerkTree;
