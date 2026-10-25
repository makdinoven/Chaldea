import type { DungeonTheme } from './dungeonThemes';

/*
  The walls and floors of each dungeon look, painted on canvases: one floor
  square and one wall section per look (plus where the lava glows, for the
  volcano). Plain canvas work with no three.js, so the admin form can show the
  same pictures as swatches.
*/

const S = 256;

type Ctx = CanvasRenderingContext2D;
type Rand = () => number;
type RGB = [number, number, number];

export interface ThemeCanvases {
  floor: HTMLCanvasElement;
  wall: HTMLCanvasElement;
  /** Where the floor and walls glow (black elsewhere), for looks that have it. */
  floorGlow?: HTMLCanvasElement;
  wallGlow?: HTMLCanvasElement;
}

const rng = (seed: number): Rand => () => {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const sheet = (fill: string): { canvas: HTMLCanvasElement; ctx: Ctx } => {
  const canvas = document.createElement('canvas');
  canvas.width = S;
  canvas.height = S;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  ctx.fillStyle = fill;
  ctx.fillRect(0, 0, S, S);
  return { canvas, ctx };
};

const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
const rgb = ([r, g, b]: RGB, a = 1) => (a >= 1 ? `rgb(${clamp(r)},${clamp(g)},${clamp(b)})` : `rgba(${clamp(r)},${clamp(g)},${clamp(b)},${a})`);
/** A colour near `base`, all channels moved together by up to ±spread/2. */
const near = (rand: Rand, base: RGB, spread: number): string => {
  const k = (rand() - 0.5) * spread;
  return rgb([base[0] + k, base[1] + k, base[2] + k]);
};

/** Light and dark flecks over a patch: worn, uneven stone. */
const mottle = (ctx: Ctx, rand: Rand, x: number, y: number, w: number, h: number, count: number, alpha = 0.07, size = 8) => {
  for (let i = 0; i < count; i++) {
    ctx.fillStyle = `rgba(${rand() > 0.5 ? '255,255,255' : '0,0,0'},${alpha * (0.5 + rand())})`;
    ctx.fillRect(x + rand() * w, y + rand() * h, 1 + rand() * size, 1 + rand() * size);
  }
};

/** A wandering crack from (x, y). */
const crackPath = (rand: Rand, x: number, y: number, steps: number, len: number): [number, number][] => {
  const pts: [number, number][] = [[x, y]];
  let a = rand() * Math.PI * 2;
  for (let s = 0; s < steps; s++) {
    a += (rand() - 0.5) * 1.4;
    x += Math.cos(a) * len * (0.6 + rand() * 0.6);
    y += Math.sin(a) * len * (0.6 + rand() * 0.6);
    pts.push([x, y]);
  }
  return pts;
};

const stroke = (ctx: Ctx, pts: [number, number][], color: string, width: number) => {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.stroke();
};

/** Courses of blocks in running bond, each block with a lit top edge and a shaded foot. */
const courses = (
  ctx: Ctx,
  rand: Rand,
  { rows, perRow, base, spread, gap, from = 0, to = S, each }: {
    rows: number;
    perRow: number;
    base: RGB;
    spread: number;
    gap: number;
    from?: number;
    to?: number;
    each?: (x: number, y: number, w: number, h: number) => void;
  },
) => {
  const h = (to - from) / rows;
  for (let row = 0; row < rows; row++) {
    let x = row % 2 ? -S / perRow / 2 : 0;
    const y = from + row * h;
    while (x < S) {
      const w = S / perRow + (rand() - 0.5) * (S / perRow) * 0.25;
      ctx.fillStyle = near(rand, base, spread);
      ctx.fillRect(x + gap, y + gap, w - gap * 2, h - gap * 2);
      ctx.fillStyle = 'rgba(255,255,255,0.08)';
      ctx.fillRect(x + gap, y + gap, w - gap * 2, Math.max(2, gap));
      ctx.fillStyle = 'rgba(0,0,0,0.25)';
      ctx.fillRect(x + gap, y + h - gap * 2, w - gap * 2, Math.max(2, gap));
      mottle(ctx, rand, x + gap, y + gap, w - gap * 2, h - gap * 2, 10, 0.06, 5);
      each?.(x + gap, y + gap, w - gap * 2, h - gap * 2);
      x += w;
    }
  }
};

/** A carved line: a dark groove with a lit lip under it. */
const carve = (ctx: Ctx, draw: () => void, width = 3) => {
  ctx.save();
  ctx.translate(1, 1.5);
  ctx.strokeStyle = 'rgba(255,240,205,0.28)';
  ctx.lineWidth = width;
  ctx.beginPath();
  draw();
  ctx.stroke();
  ctx.restore();
  ctx.strokeStyle = 'rgba(70,52,28,0.6)';
  ctx.lineWidth = width;
  ctx.beginPath();
  draw();
  ctx.stroke();
};

const blob = (ctx: Ctx, rand: Rand, cx: number, cy: number, r: number, corners = 9) => {
  ctx.beginPath();
  for (let i = 0; i <= corners; i++) {
    const a = (i / corners) * Math.PI * 2;
    const rr = r * (0.7 + rand() * 0.5);
    const x = cx + Math.cos(a) * rr;
    const y = cy + Math.sin(a) * rr;
    if (i) ctx.lineTo(x, y);
    else ctx.moveTo(x, y);
  }
  ctx.closePath();
};

// ---------------------------------------------------------------- the looks

const stone = (): ThemeCanvases => {
  const rand = rng(1301);
  const floor = sheet('#2b2a2c');
  const half = S / 2;
  for (let i = 0; i < 2; i++) {
    for (let j = 0; j < 2; j++) {
      floor.ctx.fillStyle = near(rand, [128, 128, 132], 34);
      floor.ctx.fillRect(i * half + 6, j * half + 6, half - 12, half - 12);
      mottle(floor.ctx, rand, i * half + 8, j * half + 8, half - 24, half - 24, 50, 0.07, 10);
    }
  }
  for (let c = 0; c < 3; c++) stroke(floor.ctx, crackPath(rand, rand() * S, rand() * S, 4, 22), 'rgba(20,20,22,0.7)', 2);
  const wall = sheet('#262528');
  courses(wall.ctx, rng(1409), { rows: 5, perRow: 3, base: [118, 118, 122], spread: 40, gap: 4 });
  return { floor: floor.canvas, wall: wall.canvas };
};

const temple = (): ThemeCanvases => {
  const rand = rng(2203);
  const floor = sheet('#7a6648');
  const f = floor.ctx;
  f.fillStyle = near(rand, [200, 174, 128], 16);
  f.fillRect(5, 5, S - 10, S - 10);
  mottle(f, rand, 8, 8, S - 16, S - 16, 120, 0.05, 9);
  carve(f, () => f.rect(26, 26, S - 52, S - 52));
  carve(f, () => f.rect(36, 36, S - 72, S - 72), 1.5);
  const c = S / 2;
  carve(f, () => f.arc(c, c, 44, 0, Math.PI * 2));
  carve(f, () => f.arc(c, c, 14, 0, Math.PI * 2), 2);
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    carve(f, () => f.ellipse(c + Math.cos(a) * 29, c + Math.sin(a) * 29, 12, 5, a, 0, Math.PI * 2), 2);
  }
  // corner marks
  [[26, 26], [S - 26, 26], [26, S - 26], [S - 26, S - 26]].forEach(([x, y]) =>
    carve(f, () => {
      f.moveTo(x - 8, y);
      f.lineTo(x, y - 8);
      f.lineTo(x + 8, y);
      f.lineTo(x, y + 8);
      f.closePath();
    }, 2),
  );
  stroke(f, crackPath(rand, rand() * S, rand() * S, 3, 18), 'rgba(90,70,40,0.5)', 1.5);

  const wall = sheet('#6e5c40');
  const w = wall.ctx;
  courses(w, rng(2207), { rows: 2, perRow: 2, base: [192, 166, 120], spread: 22, gap: 4, from: 0, to: S * 0.4 });
  courses(w, rng(2209), { rows: 2, perRow: 2, base: [192, 166, 120], spread: 22, gap: 4, from: S * 0.6, to: S });
  // the frieze: a band with a carved zigzag between two grooves
  w.fillStyle = 'rgb(176,150,104)';
  w.fillRect(0, S * 0.4 + 3, S, S * 0.2 - 6);
  mottle(w, rand, 0, S * 0.4, S, S * 0.2, 60, 0.05, 6);
  const top = S * 0.4 + 10;
  const bottom = S * 0.6 - 10;
  carve(w, () => {
    w.moveTo(0, top - 3);
    w.lineTo(S, top - 3);
  }, 2);
  carve(w, () => {
    w.moveTo(0, bottom + 3);
    w.lineTo(S, bottom + 3);
  }, 2);
  carve(w, () => {
    const step = S / 8;
    w.moveTo(0, bottom);
    for (let i = 0; i < 8; i++) {
      w.lineTo(i * step + step / 2, top);
      w.lineTo((i + 1) * step, bottom);
    }
  }, 2.5);
  return { floor: floor.canvas, wall: wall.canvas };
};

const cave = (): ThemeCanvases => {
  const rand = rng(3301);
  const floor = sheet('#463e36');
  const f = floor.ctx;
  for (let i = 0; i < 6; i++) {
    const g = f.createRadialGradient(rand() * S, rand() * S, 0, rand() * S, rand() * S, 90);
    g.addColorStop(0, `rgba(${rand() > 0.5 ? '120,108,92' : '30,26,22'},0.35)`);
    g.addColorStop(1, 'rgba(0,0,0,0)');
    f.fillStyle = g;
    f.fillRect(0, 0, S, S);
  }
  mottle(f, rand, 0, 0, S, S, 300, 0.08, 4);
  for (let i = 0; i < 150; i++) {
    const x = rand() * S;
    const y = rand() * S;
    const r = 2 + rand() * (rand() > 0.85 ? 12 : 5);
    f.fillStyle = 'rgba(15,12,10,0.55)';
    blob(f, rand, x + 1.5, y + 2, r, 7);
    f.fill();
    f.fillStyle = near(rand, [104, 96, 86], 50);
    blob(f, rand, x, y, r, 7);
    f.fill();
  }

  const wall = sheet('#2a241f');
  const w = wall.ctx;
  for (let i = 0; i < 34; i++) {
    const x = rand() * S;
    const y = rand() * S;
    const r = 24 + rand() * 34;
    for (const [dx, dy] of [[0, 0], [S, 0], [-S, 0], [0, S], [0, -S]]) {
      if (x + dx < -r || x + dx > S + r || y + dy < -r || y + dy > S + r) continue;
      const shade = near(rand, [98, 88, 76], 44);
      w.fillStyle = shade;
      blob(w, rng(i * 31 + 7), x + dx, y + dy, r, 7);
      w.fill();
      w.strokeStyle = 'rgba(18,14,10,0.85)';
      w.lineWidth = 3;
      w.stroke();
    }
  }
  mottle(w, rand, 0, 0, S, S, 220, 0.08, 5);
  for (let c = 0; c < 5; c++) stroke(w, crackPath(rand, rand() * S, rand() * S, 5, 20), 'rgba(10,8,6,0.8)', 2.5);
  return { floor: floor.canvas, wall: wall.canvas };
};

const ice = (): ThemeCanvases => {
  const rand = rng(4401);
  const floor = sheet('#a8cde4');
  const f = floor.ctx;
  const g = f.createLinearGradient(0, 0, S, S);
  g.addColorStop(0, 'rgba(255,255,255,0.25)');
  g.addColorStop(0.5, 'rgba(120,170,210,0.15)');
  g.addColorStop(1, 'rgba(255,255,255,0.2)');
  f.fillStyle = g;
  f.fillRect(0, 0, S, S);
  for (let i = 0; i < 7; i++) {
    const pts = crackPath(rand, rand() * S, rand() * S, 6, 26);
    stroke(f, pts, 'rgba(60,110,150,0.55)', 3);
    stroke(f, pts, 'rgba(255,255,255,0.85)', 1.2);
  }
  for (let i = 0; i < 260; i++) {
    f.fillStyle = `rgba(255,255,255,${0.2 + rand() * 0.5})`;
    f.fillRect(rand() * S, rand() * S, 1 + rand() * 2, 1 + rand() * 2);
  }
  for (let i = 0; i < 4; i++) {
    f.strokeStyle = 'rgba(255,255,255,0.18)';
    f.lineWidth = 6 + rand() * 8;
    const x = rand() * S;
    f.beginPath();
    f.moveTo(x, 0);
    f.lineTo(x + 70, S);
    f.stroke();
  }

  const wall = sheet('#e4f4ff');
  const w = wall.ctx;
  courses(w, rng(4409), {
    rows: 4,
    perRow: 2,
    base: [138, 184, 214],
    spread: 24,
    gap: 3,
    each: (x, y, bw, bh) => {
      const grad = w.createLinearGradient(0, y, 0, y + bh);
      grad.addColorStop(0, 'rgba(255,255,255,0.35)');
      grad.addColorStop(1, 'rgba(40,90,140,0.25)');
      w.fillStyle = grad;
      w.fillRect(x, y, bw, bh);
      for (let k = 0; k < 4; k++) {
        w.strokeStyle = 'rgba(255,255,255,0.22)';
        w.lineWidth = 1;
        const sx = x + rand() * bw;
        w.beginPath();
        w.moveTo(sx, y + 3);
        w.lineTo(sx + (rand() - 0.5) * 10, y + bh - 3);
        w.stroke();
      }
      for (let k = 0; k < 5; k++) {
        w.strokeStyle = 'rgba(255,255,255,0.45)';
        w.beginPath();
        w.arc(x + rand() * bw, y + rand() * bh, 1 + rand() * 2.5, 0, Math.PI * 2);
        w.stroke();
      }
    },
  });
  return { floor: floor.canvas, wall: wall.canvas };
};

const volcano = (): ThemeCanvases => {
  // The cracks are drawn twice from the same plan: dark rock with a hot core, and the glow alone.
  const plan = (seed: number, count: number, steps: number, len: number) => {
    const rand = rng(seed);
    return Array.from({ length: count }, () => crackPath(rand, rand() * S, rand() * S, steps, len));
  };
  const floorCracks = plan(5501, 6, 7, 24);
  const wallVeins = plan(5507, 2, 4, 18);

  const rand = rng(5503);
  const floor = sheet('#1d1918');
  const f = floor.ctx;
  mottle(f, rand, 0, 0, S, S, 320, 0.08, 6);
  for (let i = 0; i < 30; i++) {
    f.fillStyle = 'rgba(0,0,0,0.35)';
    blob(f, rand, rand() * S, rand() * S, 8 + rand() * 18, 6);
    f.fill();
  }
  floorCracks.forEach((pts) => {
    stroke(f, pts, '#0a0707', 6);
    stroke(f, pts, '#ff7a2a', 2);
  });
  const wall = sheet('#141010');
  const w = wall.ctx;
  courses(w, rng(5509), { rows: 4, perRow: 3, base: [46, 40, 38], spread: 16, gap: 4 });
  wallVeins.forEach((pts) => {
    stroke(w, pts, '#0a0707', 4);
    stroke(w, pts, '#ff7a2a', 1.5);
  });

  const glow = (cracks: [number, number][][], width: number) => {
    const g = sheet('#000000');
    g.ctx.shadowColor = '#ff6a1a';
    g.ctx.shadowBlur = 10;
    cracks.forEach((pts) => stroke(g.ctx, pts, '#ff8a3a', width));
    return g.canvas;
  };
  return { floor: floor.canvas, wall: wall.canvas, floorGlow: glow(floorCracks, 3), wallGlow: glow(wallVeins, 2) };
};

const skull = (ctx: Ctx, x: number, y: number, r: number) => {
  ctx.fillStyle = '#cfc3a2';
  ctx.beginPath();
  ctx.arc(x, y, r, Math.PI * 0.9, Math.PI * 2.1);
  ctx.lineTo(x + r * 0.6, y + r * 1.0);
  ctx.lineTo(x - r * 0.6, y + r * 1.0);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = 'rgba(60,50,35,0.35)';
  ctx.fillRect(x - r * 0.6, y + r * 0.7, r * 1.2, r * 0.3);
  ctx.fillStyle = '#1a1612';
  ctx.beginPath();
  ctx.arc(x - r * 0.38, y + r * 0.05, r * 0.27, 0, Math.PI * 2);
  ctx.arc(x + r * 0.38, y + r * 0.05, r * 0.27, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(x, y + r * 0.3);
  ctx.lineTo(x - r * 0.12, y + r * 0.55);
  ctx.lineTo(x + r * 0.12, y + r * 0.55);
  ctx.closePath();
  ctx.fill();
};

const moss = (ctx: Ctx, rand: Rand, count: number, yFrom: number, yTo: number) => {
  for (let i = 0; i < count; i++) {
    ctx.fillStyle = `rgba(${60 + rand() * 30},${95 + rand() * 40},${40 + rand() * 20},${0.25 + rand() * 0.35})`;
    blob(ctx, rand, rand() * S, yFrom + rand() * (yTo - yFrom), 3 + rand() * 9, 7);
    ctx.fill();
  }
};

const catacombs = (): ThemeCanvases => {
  const rand = rng(6601);
  const wall = sheet('#1c1a17');
  const w = wall.ctx;
  courses(w, rng(6603), { rows: 8, perRow: 4, base: [80, 72, 62], spread: 24, gap: 2.5 });
  [S * 0.27, S * 0.73].forEach((cx) => {
    const nw = 64;
    const top = S * 0.3;
    const nh = 70;
    w.fillStyle = '#0d0b09';
    w.beginPath();
    w.moveTo(cx - nw / 2, top + nh);
    w.lineTo(cx - nw / 2, top + nw / 2);
    w.arc(cx, top + nw / 2, nw / 2, Math.PI, 0);
    w.lineTo(cx + nw / 2, top + nh);
    w.closePath();
    w.fill();
    w.strokeStyle = 'rgba(150,135,110,0.35)';
    w.lineWidth = 3;
    w.stroke();
    // bones under the skull
    w.strokeStyle = '#b8ac8c';
    w.lineWidth = 4;
    w.lineCap = 'round';
    w.beginPath();
    w.moveTo(cx - 20, top + nh - 6);
    w.lineTo(cx + 20, top + nh - 16);
    w.moveTo(cx - 20, top + nh - 16);
    w.lineTo(cx + 20, top + nh - 6);
    w.stroke();
    skull(w, cx, top + nh * 0.45, 14);
  });
  moss(w, rand, 70, S * 0.6, S);
  moss(w, rand, 18, 0, S * 0.6);

  const floor = sheet('#24301e');
  const f = floor.ctx;
  const n = 3;
  const cell = S / n;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const jx = (rand() - 0.5) * 8;
      const jy = (rand() - 0.5) * 8;
      f.fillStyle = near(rand, [70, 66, 58], 22);
      f.fillRect(i * cell + 4 + jx, j * cell + 4 + jy, cell - 8, cell - 8);
      mottle(f, rand, i * cell + 6, j * cell + 6, cell - 12, cell - 12, 30, 0.07, 6);
    }
  }
  moss(f, rand, 40, 0, S);
  for (let i = 0; i < 6; i++) {
    const x = 20 + rand() * (S - 40);
    const y = 20 + rand() * (S - 40);
    const a = rand() * Math.PI;
    const l = 10 + rand() * 14;
    f.strokeStyle = '#bfb393';
    f.lineWidth = 3;
    f.lineCap = 'round';
    f.beginPath();
    f.moveTo(x - Math.cos(a) * l, y - Math.sin(a) * l);
    f.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l);
    f.stroke();
    f.fillStyle = '#bfb393';
    [-1, 1].forEach((s) => {
      f.beginPath();
      f.arc(x + s * Math.cos(a) * l, y + s * Math.sin(a) * l, 3, 0, Math.PI * 2);
      f.fill();
    });
  }
  return { floor: floor.canvas, wall: wall.canvas };
};

const plank = (ctx: Ctx, rand: Rand, x: number, y: number, w: number, h: number, base: RGB) => {
  ctx.fillStyle = near(rand, base, 24);
  ctx.fillRect(x, y, w, h);
  const along = w > h;
  for (let k = 0; k < 6; k++) {
    ctx.strokeStyle = `rgba(30,18,8,${0.2 + rand() * 0.25})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (along) {
      const gy = y + 2 + rand() * (h - 4);
      ctx.moveTo(x, gy);
      ctx.bezierCurveTo(x + w * 0.3, gy + (rand() - 0.5) * 4, x + w * 0.7, gy + (rand() - 0.5) * 4, x + w, gy);
    } else {
      const gx = x + 2 + rand() * (w - 4);
      ctx.moveTo(gx, y);
      ctx.bezierCurveTo(gx + (rand() - 0.5) * 4, y + h * 0.3, gx + (rand() - 0.5) * 4, y + h * 0.7, gx, y + h);
    }
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(255,230,190,0.08)';
  if (along) ctx.fillRect(x, y, w, 2);
  else ctx.fillRect(x, y, 2, h);
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  if (along) ctx.fillRect(x, y + h - 2, w, 2);
  else ctx.fillRect(x + w - 2, y, 2, h);
};

const mine = (): ThemeCanvases => {
  const rand = rng(7701);
  const wall = sheet('#4e3c2c');
  const w = wall.ctx;
  mottle(w, rand, 0, 0, S, S, 260, 0.1, 6);
  for (let i = 0; i < 60; i++) {
    w.fillStyle = near(rand, [110, 96, 80], 40);
    blob(w, rand, rand() * S, rand() * S, 2 + rand() * 6, 6);
    w.fill();
  }
  // the lagging: boards held against the rock
  for (let i = 0; i < 4; i++) plank(w, rand, 0, 54 + i * 30, S, 26, [112, 80, 48]);
  // the post at the end of the section, and its cap
  plank(w, rand, 8, 0, 34, S, [96, 66, 38]);
  plank(w, rand, 0, 18, S, 22, [90, 62, 36]);
  w.fillStyle = '#1c1612';
  [[25, 29], [25, 80], [25, 170]].forEach(([x, y]) => {
    w.beginPath();
    w.arc(x, y, 2.5, 0, Math.PI * 2);
    w.fill();
  });

  const floor = sheet('#5e4a36');
  const f = floor.ctx;
  for (let i = 0; i < 5; i++) {
    const g = f.createRadialGradient(rand() * S, rand() * S, 0, rand() * S, rand() * S, 100);
    g.addColorStop(0, `rgba(${rand() > 0.5 ? '130,108,80' : '40,30,20'},0.35)`);
    g.addColorStop(1, 'rgba(0,0,0,0)');
    f.fillStyle = g;
    f.fillRect(0, 0, S, S);
  }
  mottle(f, rand, 0, 0, S, S, 380, 0.09, 3);
  for (let i = 0; i < 80; i++) {
    f.fillStyle = near(rand, [120, 108, 92], 50);
    f.beginPath();
    f.arc(rand() * S, rand() * S, 1 + rand() * 3, 0, Math.PI * 2);
    f.fill();
  }
  plank(f, rand, 0, S * 0.42, S, 38, [92, 64, 38]);
  return { floor: floor.canvas, wall: wall.canvas };
};

const sewer = (): ThemeCanvases => {
  const rand = rng(8801);
  const wall = sheet('#2a2420');
  const w = wall.ctx;
  courses(w, rng(8803), { rows: 9, perRow: 4, base: [118, 70, 54], spread: 26, gap: 2.5 });
  const slime = w.createLinearGradient(0, S * 0.62, 0, S);
  slime.addColorStop(0, 'rgba(70,100,40,0)');
  slime.addColorStop(0.3, 'rgba(70,100,40,0.55)');
  slime.addColorStop(1, 'rgba(40,60,24,0.85)');
  w.fillStyle = slime;
  w.fillRect(0, S * 0.62, S, S * 0.38);
  for (let i = 0; i < 16; i++) {
    const x = rand() * S;
    const len = 30 + rand() * 120;
    const g = w.createLinearGradient(0, 0, 0, len);
    g.addColorStop(0, 'rgba(40,50,28,0.5)');
    g.addColorStop(1, 'rgba(40,50,28,0)');
    w.fillStyle = g;
    w.fillRect(x, 0, 2 + rand() * 5, len);
  }
  moss(w, rand, 30, S * 0.55, S);

  const floor = sheet('#1e2618');
  const f = floor.ctx;
  const n = 4;
  const cell = S / n;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      f.fillStyle = near(rand, [82, 80, 68], 22);
      f.fillRect(i * cell + 3, j * cell + 3, cell - 6, cell - 6);
      mottle(f, rand, i * cell + 4, j * cell + 4, cell - 8, cell - 8, 14, 0.07, 5);
    }
  }
  for (let i = 0; i < 3; i++) {
    const x = 30 + rand() * (S - 60);
    const y = 30 + rand() * (S - 60);
    const r = 16 + rand() * 22;
    f.fillStyle = 'rgba(48,66,40,0.75)';
    blob(f, rand, x, y, r, 10);
    f.fill();
    f.strokeStyle = 'rgba(210,230,190,0.35)';
    f.lineWidth = 2;
    f.beginPath();
    f.arc(x - r * 0.2, y - r * 0.2, r * 0.5, Math.PI * 1.1, Math.PI * 1.6);
    f.stroke();
  }
  moss(f, rand, 30, 0, S);
  return { floor: floor.canvas, wall: wall.canvas };
};

const PAINTERS: Record<DungeonTheme, () => ThemeCanvases> = { stone, temple, cave, ice, volcano, catacombs, mine, sewer };

export const paintTheme = (theme: DungeonTheme): ThemeCanvases => PAINTERS[theme]();

const swatches = new Map<DungeonTheme, string>();
/** A small picture of a look for the admin form: a wall section over a floor square. */
export const themeSwatch = (theme: DungeonTheme): string => {
  const cached = swatches.get(theme);
  if (cached) return cached;
  const { floor, wall } = paintTheme(theme);
  const out = document.createElement('canvas');
  out.width = 160;
  out.height = 120;
  const ctx = out.getContext('2d');
  if (!ctx) return '';
  ctx.drawImage(wall, 0, 0, S, S, 0, 0, 80, 60);
  ctx.drawImage(wall, 0, 0, S, S, 80, 0, 80, 60);
  ctx.drawImage(floor, 0, 0, S, S, 0, 60, 80, 60);
  ctx.drawImage(floor, 0, 0, S, S, 80, 60, 80, 60);
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.fillRect(0, 58, 160, 4);
  const url = out.toDataURL('image/png');
  swatches.set(theme, url);
  return url;
};
