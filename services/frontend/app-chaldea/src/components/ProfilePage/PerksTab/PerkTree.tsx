import React, { useMemo, useId } from 'react';
import { motion } from 'motion/react';
import type { CharacterPerk } from '../../../types/perks';
import PerkNode, { HEX_SIZE } from './PerkNode';

/* ── Starfield background ── */

const STAR_LAYERS = [
  { count: 80, size: 1, opacity: 0.6, duration: 4 },
  { count: 40, size: 1.5, opacity: 0.8, duration: 6 },
  { count: 15, size: 2, opacity: 1, duration: 8 },
] as const;

function generateStars(count: number, seed: number) {
  const stars: Array<{ x: number; y: number; delay: number }> = [];
  for (let i = 0; i < count; i++) {
    const a = Math.sin(i * 127.1 + seed * 311.7) * 43758.5453;
    const b = Math.sin(i * 269.5 + seed * 183.3) * 28935.3127;
    const c = Math.sin(i * 419.2 + seed * 77.9) * 17624.9871;
    stars.push({
      x: (a - Math.floor(a)) * 100,
      y: (b - Math.floor(b)) * 100,
      delay: (c - Math.floor(c)) * 10,
    });
  }
  return stars;
}

const StarfieldBg = () => {
  const id = useId();
  return (
    <div className="absolute inset-0 overflow-hidden rounded-card">
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at 30% 20%, rgba(25,20,60,0.95) 0%, rgba(8,8,24,0.98) 50%, rgba(4,4,16,1) 100%)',
        }}
      />
      <div
        className="absolute inset-0 opacity-30"
        style={{
          background:
            'radial-gradient(ellipse at 70% 60%, rgba(80,40,120,0.4) 0%, transparent 50%), ' +
            'radial-gradient(ellipse at 20% 80%, rgba(30,60,120,0.3) 0%, transparent 40%), ' +
            'radial-gradient(ellipse at 50% 30%, rgba(120,80,30,0.15) 0%, transparent 35%)',
        }}
      />
      {STAR_LAYERS.map((layer, li) => {
        const stars = generateStars(layer.count, li + 1);
        return stars.map((star, si) => (
          <div
            key={`${id}-${li}-${si}`}
            className="absolute rounded-full"
            style={{
              width: layer.size,
              height: layer.size,
              left: `${star.x}%`,
              top: `${star.y}%`,
              backgroundColor: `rgba(255, 255, 240, ${layer.opacity})`,
              animation: `perk-star-twinkle ${layer.duration}s ease-in-out ${star.delay}s infinite`,
            }}
          />
        ));
      })}
      <style>{`
        @keyframes perk-star-twinkle {
          0%, 100% { opacity: 0.2; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
};

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
  categories: Array<[string, CharacterPerk[]]>,
  center: number,
): NodePos[] {
  const positions: NodePos[] = [];
  const catCount = categories.length || 1;
  const sectorAngle = (2 * Math.PI) / catCount;

  categories.forEach(([cat, catPerks], catIdx) => {
    const sectorCenter = catIdx * sectorAngle - Math.PI / 2;

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

interface EdgeData {
  /** Trimmed line start (at hex border, not center) */
  x1: number; y1: number;
  /** Trimmed line end */
  x2: number; y2: number;
  cat: string;
  /** Visual state: 'both' = both unlocked, 'one' = one unlocked, 'none' = neither */
  state: 'both' | 'one' | 'none';
}

const CENTER_HEX_SIZE = 34; // center node hex radius

/**
 * Trim a line segment so it starts/ends at the hex border
 * (offset inward by `r` from each endpoint).
 */
function trimLine(
  ax: number, ay: number, bx: number, by: number,
  rA: number, rB: number,
): [number, number, number, number] {
  const dx = bx - ax;
  const dy = by - ay;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < rA + rB) return [ax, ay, bx, by]; // too short to trim
  const ux = dx / len;
  const uy = dy / len;
  return [ax + ux * rA, ay + uy * rA, bx - ux * rB, by - uy * rB];
}

/**
 * Build constellation edges connecting nodes within each category.
 * Lines are trimmed to hex borders and carry unlock state for styling.
 */
function computeEdges(
  categories: Array<[string, CharacterPerk[]]>,
  positions: NodePos[],
  center: number,
): EdgeData[] {
  const edges: EdgeData[] = [];
  const avoidR = HEX_SIZE + 2;

  for (const [cat] of categories) {
    const catNodes = positions.filter((p) => p.category === cat);
    if (catNodes.length === 0) continue;

    // Group by ring (distance from center)
    const byRing: NodePos[][] = [];
    const sorted = [...catNodes].sort((a, b) => {
      const da = Math.sqrt((a.x - center) ** 2 + (a.y - center) ** 2);
      const db = Math.sqrt((b.x - center) ** 2 + (b.y - center) ** 2);
      return da - db;
    });

    let currentRing: NodePos[] = [];
    let lastDist = 0;
    for (const node of sorted) {
      const d = Math.sqrt((node.x - center) ** 2 + (node.y - center) ** 2);
      if (currentRing.length > 0 && d - lastDist > RING_SPACING * 0.5) {
        byRing.push(currentRing);
        currentRing = [];
      }
      currentRing.push(node);
      lastDist = d;
    }
    if (currentRing.length > 0) byRing.push(currentRing);

    // Center → first ring (center always counts as "unlocked")
    for (const node of (byRing[0] ?? [])) {
      const [tx1, ty1, tx2, ty2] = trimLine(center, center, node.x, node.y, CENTER_HEX_SIZE, HEX_SIZE);
      const state = node.perk.is_unlocked ? 'both' : 'one';
      edges.push({ x1: tx1, y1: ty1, x2: tx2, y2: ty2, cat, state });
    }

    // Ring N → Ring N+1
    for (let r = 0; r < byRing.length - 1; r++) {
      const ringA = byRing[r];
      const ringB = byRing[r + 1];
      const connectedB = new Set<number>();

      const addEdge = (a: NodePos, b: NodePos) => {
        const [tx1, ty1, tx2, ty2] = trimLine(a.x, a.y, b.x, b.y, HEX_SIZE, HEX_SIZE);
        const aUn = a.perk.is_unlocked;
        const bUn = b.perk.is_unlocked;
        const state = aUn && bUn ? 'both' : (aUn || bUn ? 'one' : 'none');
        edges.push({ x1: tx1, y1: ty1, x2: tx2, y2: ty2, cat, state });
      };

      for (const a of ringA) {
        let bestIdx = 0;
        let bestDist = Infinity;
        ringB.forEach((b, idx) => {
          const d = Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
          if (d < bestDist) { bestDist = d; bestIdx = idx; }
        });
        const b = ringB[bestIdx];
        if (!lineHitsNode(a.x, a.y, b.x, b.y, positions, a, b, avoidR)) {
          addEdge(a, b);
          connectedB.add(bestIdx);
        }
      }

      // Orphaned ringB nodes
      ringB.forEach((b, idx) => {
        if (connectedB.has(idx)) return;
        let bestA = ringA[0];
        let bestDist = Infinity;
        for (const a of ringA) {
          const d = Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
          if (d < bestDist) { bestDist = d; bestA = a; }
        }
        addEdge(bestA, b);
      });
    }
  }

  return edges;
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

  const categories = useMemo(
    () => [...grouped.entries()].filter(([, items]) => items.length > 0),
    [grouped],
  );

  const CENTER = 350;

  const nodePositions = useMemo(
    () => computePositions(categories, CENTER),
    [categories],
  );

  const edges = useMemo(
    () => computeEdges(categories, nodePositions, CENTER),
    [categories, nodePositions],
  );

  const viewBox = useMemo(() => {
    const allX = [CENTER, ...nodePositions.map((p) => p.x)];
    const allY = [CENTER, ...nodePositions.map((p) => p.y)];
    const pad = 90;
    const minX = Math.min(...allX) - pad;
    const maxX = Math.max(...allX) + pad;
    const minY = Math.min(...allY) - pad;
    const maxY = Math.max(...allY) + pad;
    return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`;
  }, [nodePositions]);

  if (perks.length === 0) {
    return (
      <div className="relative rounded-card overflow-hidden p-8 text-center">
        <StarfieldBg />
        <p className="relative text-white/40 text-lg">Перки пока не добавлены</p>
      </div>
    );
  }

  return (
    <div className="relative rounded-card overflow-hidden">
      <StarfieldBg />
      <div className="relative z-10">
        {/* Desktop: SVG constellation */}
        <div className="hidden md:block py-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
            className="w-full flex justify-center"
          >
            <svg
              viewBox={viewBox}
              className="w-full max-w-[850px] h-auto"
              xmlns="http://www.w3.org/2000/svg"
            >
              {/* Edge gradient defs + blur filter */}
              <defs>
                <filter id="edge-blur" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" />
                </filter>
                {categories.map(([cat]) => {
                  const c = CATEGORY_CONFIG[cat]?.color ?? 'rgba(255,255,255,0.5)';
                  return (
                    <React.Fragment key={cat}>
                      <linearGradient id={`edge-bright-${cat}`} x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="rgba(240,217,92,0.9)" />
                        <stop offset="100%" stopColor={c.replace(/[\d.]+\)$/, '0.9)')} />
                      </linearGradient>
                      <linearGradient id={`edge-dim-${cat}`} x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="rgba(240,217,92,0.5)" />
                        <stop offset="100%" stopColor={c.replace(/[\d.]+\)$/, '0.45)')} />
                      </linearGradient>
                    </React.Fragment>
                  );
                })}
              </defs>

              {/* Center hexagon (drawn first — behind edges and nodes) */}
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

              {/* Edges (above center hex, behind perk nodes) */}
              {edges.map((e, i) => {
                const isBright = e.state === 'both';
                const isDim = e.state === 'one';
                const stroke = isBright
                  ? `url(#edge-bright-${e.cat})`
                  : isDim
                    ? `url(#edge-dim-${e.cat})`
                    : 'rgba(255,255,255,0.12)';
                const width = isBright ? 2.5 : isDim ? 1.5 : 1;

                // Nudge perfectly vertical/horizontal lines so SVG gradient
                // bounding box isn't degenerate (zero width/height kills gradient)
                let { x1, y1, x2, y2 } = e;
                if (x1 === x2) x2 += 0.1;
                if (y1 === y2) y2 += 0.1;

                return (
                  <g key={i}>
                    {/* Glow layer for bright edges */}
                    {isBright && (
                      <line
                        x1={x1} y1={y1} x2={x2} y2={y2}
                        stroke={stroke}
                        strokeWidth={width + 4}
                        opacity={0.25}
                        filter="url(#edge-blur)"
                      />
                    )}
                    {/* Main line */}
                    <line
                      x1={x1} y1={y1} x2={x2} y2={y2}
                      stroke={stroke}
                      strokeWidth={width}
                      strokeLinecap="round"
                    />
                  </g>
                );
              })}

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
          </motion.div>
        </div>

        {/* Mobile: flat list */}
        <div className="block md:hidden space-y-6 p-4">
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
                      const isLL = perk.rarity === 'legendary' && !perk.is_unlocked;
                      let prog = 0;
                      if (!perk.is_unlocked && perk.conditions.length > 0) {
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
                            ${perk.is_unlocked ? 'opacity-100' : 'opacity-60'} hover:opacity-100`}
                        >
                          <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 border
                              ${perk.rarity === 'legendary' ? 'border-gold/30' : perk.rarity === 'rare' ? 'border-purple-400/30' : 'border-white/15'}
                              ${perk.is_unlocked ? 'bg-white/10' : 'bg-white/5'}`}>
                              <span className={`text-sm ${perk.is_unlocked ? 'text-white' : 'text-white/30'}`}>
                                {isLL ? '?' : perk.name.slice(0, 2).toUpperCase()}
                              </span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className={`text-sm font-medium truncate ${perk.is_unlocked ? 'text-white' : 'text-white/50'}`}>
                                {isLL ? '???' : perk.name}
                              </p>
                              <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-[10px] text-white/30">{RARITY_LABELS[perk.rarity] ?? perk.rarity}</span>
                                {!perk.is_unlocked && prog > 0 && <span className="text-[10px] text-white/40">{prog}%</span>}
                              </div>
                            </div>
                            <div className="flex-shrink-0">
                              {perk.is_unlocked
                                ? <div className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                                : <div className="w-2.5 h-2.5 rounded-full bg-white/15" />}
                            </div>
                          </div>
                          {!perk.is_unlocked && prog > 0 && (
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
