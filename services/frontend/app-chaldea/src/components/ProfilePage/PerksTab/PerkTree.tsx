import React, { useMemo } from 'react';
import { motion } from 'motion/react';
import { isPerkActive } from '../../../types/perks';
import type { CharacterPerk } from '../../../types/perks';
import PerkNode, { HEX_SIZE } from './PerkNode';
import perksBackdrop from '../../../assets/perksBackdrop.png';

/* ── Backdrop ── */

/**
 * The artwork is painted for this layout: its five coloured zones sit on the
 * same bearings as the tree's five branches. Measured against the tree's own
 * sector angles, the zones land within a degree or two — red -90.6° against
 * -90°, gold -18.5° against -18°, purple -162.2° against -162°, with green and
 * blue the loose ones at +6° and -10°.
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
 * Where each branch points, in degrees, 0 = right and growing clockwise.
 *
 * Not simply five even steps of 72°: these are the bearings of the painted
 * zones behind them, measured off the backdrop as the centroid of each zone's
 * colour. The artwork's lobes are hand-composed and sit a few degrees off a
 * perfect star — trade by -8.5°, exploration by -6.8°, the rest within three —
 * so an evenly spread tree left some perks over the edge of their own zone.
 * Aiming each branch at its zone instead is what puts them back inside it.
 *
 * These belong to this backdrop. Replace the picture and they must be measured
 * again, or dropped back to `index * 72 - 90`.
 */
const BRANCH_BEARING: Record<string, number> = {
  combat: -88.4,        // красный, вверх
  trade: -26.5,         // золотой, вправо-вверх
  exploration: 47.2,    // синий, вправо-вниз
  progression: 128.5,   // зелёный, влево-вниз
  usage: -155.3,        // фиолетовый, влево-вверх
};

/**
 * How far the backdrop is nudged to bring its composition onto the hub, as a
 * fraction of its own size. The artwork sits a little high in its file — the
 * measurements put it between half and one percent, depending on how you pick
 * the centre out of a hand-painted rosette — which showed up as the "Перки"
 * label sitting below the middle of the art. Positive moves the picture down.
 */
const ART_NUDGE_X = 0;
const ART_NUDGE_Y = 0.008;

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

/* ── Constellation layout v2: tiered rings within sectors ── */

const MIN_NODE_SPACING = HEX_SIZE * 2.8; // minimum px between node centers
const RING_SPACING = 65; // distance between concentric rings
const FIRST_RING = 90; // distance of first ring from center

interface NodePos {
  perk: CharacterPerk;
  x: number;
  y: number;
  category: string;
}

/**
 * Place perks in concentric rings within each category's sector.
 * Ring 1 (closest): up to 2 nodes
 * Ring 2: up to 3 nodes
 * Ring 3+: up to 4 nodes each
 * Nodes within a ring are spaced evenly across the sector angle.
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
  const sectorAngle = (2 * Math.PI) / catCount;

  categories.forEach(([cat, catPerks], catIdx) => {
    // The painted zone's bearing where there is one; an even share otherwise,
    // so an unknown category still gets a place rather than piling up at 0.
    const bearing = BRANCH_BEARING[cat];
    const sectorCenter =
      bearing === undefined
        ? catIdx * sectorAngle - Math.PI / 2
        : (bearing * Math.PI) / 180;

    // Distribute perks into rings
    const rings: CharacterPerk[][] = [];
    let remaining = [...catPerks];
    const capacities = [1, 2, 3, 3, 4, 4, 5, 5]; // nodes per ring

    for (let r = 0; remaining.length > 0; r++) {
      const cap = capacities[Math.min(r, capacities.length - 1)];
      rings.push(remaining.slice(0, cap));
      remaining = remaining.slice(cap);
    }

    rings.forEach((ringPerks, ringIdx) => {
      const dist = FIRST_RING + ringIdx * RING_SPACING;
      const count = ringPerks.length;

      // Angular spread: wider for outer rings, but stay within sector
      const maxSpread = Math.min(
        sectorAngle * 0.7,
        // Ensure min spacing: arc length >= MIN_NODE_SPACING * (count-1)
        count > 1 ? (MIN_NODE_SPACING * (count - 1)) / dist + 0.05 : 0,
      );

      ringPerks.forEach((perk, nodeIdx) => {
        let angle: number;
        if (count === 1) {
          angle = sectorCenter;
        } else {
          const t = nodeIdx / (count - 1) - 0.5; // -0.5..+0.5
          angle = sectorCenter + t * maxSpread;
        }

        positions.push({
          perk,
          x: center + dist * Math.cos(angle),
          y: center + dist * Math.sin(angle),
          category: cat,
        });
      });
    });
  });

  return positions;
}

 

function lineHitsNode(
  x1: number, y1: number, x2: number, y2: number,
  allNodes: NodePos[],
  skip1: NodePos, skip2: NodePos,
  radius: number,
): boolean {
  for (const node of allNodes) {
    if (node === skip1 || node === skip2) continue;
    const d = distToSegment(node.x, node.y, x1, y1, x2, y2);
    if (d < radius) return true;
  }
  return false;
}

function distToSegment(
  px: number, py: number,
  x1: number, y1: number, x2: number, y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq));
  return Math.sqrt((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2);
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
    A square window centred on the hub, wide enough for the furthest node.

    Square and hub-centred on purpose: the frame is a circle and the artwork is
    square, so this is what makes all three agree. A bounding box round the
    nodes would be neither — a five-sector fan reaches further down than up —
    and centring on it is exactly what used to push the picture off to one side.
  */
  const half = useMemo(() => {
    // Measured radially, not by how far a node strays along an axis. Taking
    // the larger of dx and dy let whichever branch happened to point straight
    // up set the size, so that branch ended up against the rim while the ones
    // pointing diagonally stopped well short of it. Radius treats every
    // bearing alike.
    const reach = nodePositions.reduce(
      (worst, p) => Math.max(worst, Math.hypot(p.x - CENTER, p.y - CENTER)),
      0,
    );
    // A margin that grows with the tree, with a floor for the small ones, so
    // the outermost nodes always sit about a sixth of the radius inside.
    return Math.max(reach * 1.18, reach + 70);
  }, [nodePositions]);

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
                  it lands where the branches are without any fitting to do */}
              <image
                href={perksBackdrop}
                x={CENTER - half + ART_NUDGE_X * half * 2}
                y={CENTER - half + ART_NUDGE_Y * half * 2}
                width={half * 2}
                height={half * 2}
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
