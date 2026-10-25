import { makeCanvas, makeRectCanvas, mulberry32, toTexture } from '../pages/BattlePage/Arena3D/textures';

/*
  Canvas textures for the dungeon's dressing: cracks, moss, liquids, vines,
  grass, cobwebs, seepage stains and floor litter. All drawn on transparent
  canvases, so a decal is just a quad laid over the stone.
*/

const SIZE = 256;

type Point = [number, number];

/** A wandering line from (x, y): the points of one crack branch. */
const wander = (rand: () => number, x: number, y: number, angle: number, length: number): Point[] => {
  const steps = 5 + Math.floor(rand() * 4);
  const step = length / steps;
  const points: Point[] = [[x, y]];
  let a = angle;
  for (let s = 0; s < steps; s++) {
    a += (rand() - 0.5) * 0.9;
    x += Math.cos(a) * step;
    y += Math.sin(a) * step;
    points.push([x, y]);
  }
  return points;
};

/** A tapering polyline: thick where it starts, a hairline where it ends. */
const taper = (ctx: CanvasRenderingContext2D, points: Point[], width: number) => {
  for (let i = 1; i < points.length; i++) {
    ctx.lineWidth = Math.max(0.6, width * (1 - (i - 1) / points.length));
    ctx.beginPath();
    ctx.moveTo(points[i - 1][0], points[i - 1][1]);
    ctx.lineTo(points[i][0], points[i][1]);
    ctx.stroke();
  }
};

/**
 * Branching cracks from the middle. Dark fissures with a pale lip — or, `glowing`,
 * white seams with a halo, to be tinted into embers or magic.
 */
export const createCrackTexture = (seed: number, glowing = false) => {
  const rand = mulberry32(seed);
  const { canvas, ctx } = makeCanvas(SIZE);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  const branches: { points: Point[]; width: number }[] = [];
  const grow = (x: number, y: number, angle: number, length: number, width: number, depth: number) => {
    const points = wander(rand, x, y, angle, length);
    branches.push({ points, width });
    if (depth <= 0) return;
    for (let i = 2; i < points.length - 1; i++) {
      if (rand() < 0.35) {
        const side = rand() > 0.5 ? 1 : -1;
        grow(points[i][0], points[i][1], angle + side * (0.6 + rand() * 0.6), length * 0.45, width * 0.6, depth - 1);
      }
    }
  };
  const arms = 2 + Math.floor(rand() * 2);
  for (let i = 0; i < arms; i++) {
    const angle = (i / arms) * Math.PI * 2 + rand() * 0.8;
    grow(SIZE / 2, SIZE / 2, angle, 70 + rand() * 40, glowing ? 5 : 6, 2);
  }
  if (glowing) {
    ctx.shadowColor = 'rgba(255,255,255,1)';
    ctx.shadowBlur = 10;
    ctx.strokeStyle = 'rgba(255,255,255,0.95)';
    branches.forEach((b) => taper(ctx, b.points, b.width));
  } else {
    ctx.strokeStyle = 'rgba(215,208,196,0.35)';
    branches.forEach((b) => taper(ctx, b.points.map(([x, y]) => [x + 1.5, y + 1.5]), b.width + 2));
    ctx.strokeStyle = 'rgba(8,7,9,0.95)';
    branches.forEach((b) => taper(ctx, b.points, b.width));
  }
  return toTexture(canvas);
};

/** A soft patch of moss: overlapping clumps, darker in the middle, specks of light green. */
export const createMossTexture = (seed: number) => {
  const rand = mulberry32(seed);
  const { canvas, ctx } = makeCanvas(SIZE);
  const c = SIZE / 2;
  for (let i = 0; i < 260; i++) {
    const a = rand() * Math.PI * 2;
    const d = Math.pow(rand(), 0.7) * 100;
    const x = c + Math.cos(a) * d;
    const y = c + Math.sin(a) * d * 0.8;
    const r = (5 + rand() * 13) * (1 - d / 130);
    const hue = 80 + rand() * 40;
    const light = 16 + rand() * 18;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `hsla(${hue},45%,${light}%,${0.55 + rand() * 0.35})`);
    g.addColorStop(1, `hsla(${hue},45%,${light}%,0)`);
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  for (let i = 0; i < 90; i++) {
    const a = rand() * Math.PI * 2;
    const d = Math.pow(rand(), 0.8) * 80;
    ctx.fillStyle = `hsla(${85 + rand() * 25},60%,${40 + rand() * 15}%,0.7)`;
    ctx.fillRect(c + Math.cos(a) * d, c + Math.sin(a) * d * 0.8, 1.5, 1.5);
  }
  return toTexture(canvas);
};

/** A pool of liquid: a white irregular shape with a brighter rim, tinted by its material. */
export const createPuddleTexture = (seed: number) => {
  const rand = mulberry32(seed);
  const { canvas, ctx } = makeCanvas(SIZE);
  const c = SIZE / 2;
  const blobs = Array.from({ length: 7 + Math.floor(rand() * 4) }, () => {
    const a = rand() * Math.PI * 2;
    const d = rand() * 45;
    return { x: c + Math.cos(a) * d, y: c + Math.sin(a) * d * 0.75, r: 28 + rand() * 30 };
  });
  // The rim first, a touch wider: a lighter meniscus round the edge.
  ctx.fillStyle = 'rgba(255,255,255,1)';
  blobs.forEach((b) => {
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r + 2, 0, Math.PI * 2);
    ctx.fill();
  });
  // The pool itself a shade darker than its rim, with a soft gleam across it.
  ctx.globalCompositeOperation = 'destination-out';
  ctx.fillStyle = 'rgba(0,0,0,0.3)';
  blobs.forEach((b) => {
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r - 3, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.globalCompositeOperation = 'source-atop';
  const gleam = ctx.createLinearGradient(c - 60, c - 40, c + 40, c + 30);
  gleam.addColorStop(0, 'rgba(255,255,255,0)');
  gleam.addColorStop(0.45, 'rgba(255,255,255,0.9)');
  gleam.addColorStop(0.55, 'rgba(255,255,255,0.9)');
  gleam.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = gleam;
  ctx.fillRect(0, c - 30, SIZE, 18);
  ctx.globalCompositeOperation = 'source-over';
  // Stray droplets.
  for (let i = 0; i < 8; i++) {
    const a = rand() * Math.PI * 2;
    const d = 85 + rand() * 30;
    ctx.fillStyle = 'rgba(200,200,200,0.95)';
    ctx.beginPath();
    ctx.arc(c + Math.cos(a) * d, c + Math.sin(a) * d * 0.75, 2 + rand() * 5, 0, Math.PI * 2);
    ctx.fill();
  }
  return toTexture(canvas);
};

/** A splash: a pool with streaks and droplets flung out from it (blood, mostly). */
export const createSplatterTexture = (seed: number) => {
  const rand = mulberry32(seed);
  const { canvas, ctx } = makeCanvas(SIZE);
  const c = SIZE / 2;
  ctx.fillStyle = 'rgba(255,255,255,1)';
  for (let i = 0; i < 6; i++) {
    ctx.beginPath();
    ctx.arc(c + (rand() - 0.5) * 40, c + (rand() - 0.5) * 30, 18 + rand() * 18, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.strokeStyle = 'rgba(255,255,255,1)';
  ctx.lineCap = 'round';
  for (let i = 0; i < 12; i++) {
    const a = rand() * Math.PI * 2;
    const len = 40 + rand() * 70;
    ctx.lineWidth = 2 + rand() * 4;
    ctx.beginPath();
    ctx.moveTo(c + Math.cos(a) * 20, c + Math.sin(a) * 20);
    ctx.lineTo(c + Math.cos(a) * len, c + Math.sin(a) * len);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(c + Math.cos(a) * (len + 6), c + Math.sin(a) * (len + 6), 2 + rand() * 4, 0, Math.PI * 2);
    ctx.fill();
  }
  return toTexture(canvas);
};

/** A circle of runes, white, to glow in a portal's colour. */
export const createRuneCircleTexture = () => {
  const rand = mulberry32(77);
  const { canvas, ctx } = makeCanvas(SIZE);
  const c = SIZE / 2;
  ctx.strokeStyle = 'rgba(255,255,255,0.95)';
  ctx.shadowColor = 'rgba(255,255,255,1)';
  ctx.shadowBlur = 6;
  ctx.lineWidth = 3;
  [118, 92].forEach((r) => {
    ctx.beginPath();
    ctx.arc(c, c, r, 0, Math.PI * 2);
    ctx.stroke();
  });
  ctx.lineWidth = 2.2;
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2;
    ctx.save();
    ctx.translate(c + Math.cos(a) * 105, c + Math.sin(a) * 105);
    ctx.rotate(a + Math.PI / 2);
    // A made-up glyph: a stroke or two and a dot.
    ctx.beginPath();
    ctx.moveTo(-5, -6);
    ctx.lineTo(rand() * 8 - 4, 6);
    if (rand() > 0.4) {
      ctx.moveTo(5, -6);
      ctx.lineTo(-2 + rand() * 6, 2);
    }
    ctx.stroke();
    if (rand() > 0.5) {
      ctx.beginPath();
      ctx.arc(0, -9, 1.6, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
  }
  return toTexture(canvas);
};

/** Hanging vines: a few leafy strands of different lengths falling from the top edge. */
export const createVineTexture = (seed: number) => {
  const rand = mulberry32(seed);
  const { canvas, ctx } = makeRectCanvas(96, 256);
  const strands = 3 + Math.floor(rand() * 2);
  for (let s = 0; s < strands; s++) {
    const x0 = 12 + rand() * 72;
    const length = 110 + rand() * 140;
    const phase = rand() * 6;
    const xAt = (y: number) => x0 + Math.sin(y / 22 + phase) * 6;
    ctx.strokeStyle = `hsl(${95 + rand() * 20},35%,${14 + rand() * 8}%)`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(xAt(0), 0);
    for (let y = 4; y <= length; y += 4) ctx.lineTo(xAt(y), y);
    ctx.stroke();
    for (let y = 6; y < length; y += 7 + rand() * 6) {
      const side = Math.floor(y / 9) % 2 ? 1 : -1;
      const size = 4 + rand() * 4 * (1 - y / 400);
      ctx.save();
      ctx.translate(xAt(y), y);
      ctx.rotate(side * (0.6 + rand() * 0.5));
      ctx.fillStyle = `hsl(${90 + rand() * 35},${40 + rand() * 20}%,${20 + rand() * 18}%)`;
      ctx.beginPath();
      ctx.ellipse(side * size, 0, size, size * 0.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }
  return toTexture(canvas);
};

/** A tuft of grass blades rising from the bottom middle. */
export const createGrassTexture = (seed: number) => {
  const rand = mulberry32(seed);
  const { canvas, ctx } = makeRectCanvas(128, 128);
  ctx.lineCap = 'round';
  for (let i = 0; i < 22; i++) {
    const x = 64 + (rand() - 0.5) * 50;
    const lean = (rand() - 0.5) * 60;
    const top = 20 + rand() * 60;
    ctx.strokeStyle = `hsl(${70 + rand() * 40},${35 + rand() * 25}%,${22 + rand() * 20}%)`;
    ctx.lineWidth = 2 + rand() * 2;
    ctx.beginPath();
    ctx.moveTo(x, 128);
    ctx.quadraticCurveTo(x + lean * 0.3, (128 + top) / 2, x + lean, top);
    ctx.stroke();
  }
  return toTexture(canvas);
};

/** A cobweb strung from the top edge: spokes and sagging rings of thread. */
export const createWebTexture = () => {
  const rand = mulberry32(53);
  const { canvas, ctx } = makeCanvas(SIZE);
  const cx = SIZE / 2;
  const cy = 6;
  const spokes = 9;
  const angles = Array.from({ length: spokes }, (_, i) => 0.1 + (i / (spokes - 1)) * (Math.PI - 0.2));
  const radius = angles.map(() => 170 + rand() * 70);
  ctx.strokeStyle = 'rgba(235,235,240,0.75)';
  ctx.lineWidth = 1.1;
  angles.forEach((a, i) => {
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(a) * radius[i], cy + Math.sin(a) * radius[i]);
    ctx.stroke();
  });
  for (let ring = 1; ring <= 7; ring++) {
    const t = ring / 8;
    ctx.beginPath();
    angles.forEach((a, i) => {
      const r = radius[i] * t;
      const x = cx + Math.cos(a) * r;
      const y = cy + Math.sin(a) * r;
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        // Each thread sags a little between the spokes.
        const mid = (a + angles[i - 1]) / 2;
        const sag = r * 0.88;
        ctx.quadraticCurveTo(cx + Math.cos(mid) * sag, cy + Math.sin(mid) * sag, x, y);
      }
    });
    ctx.stroke();
  }
  return toTexture(canvas);
};

/** Seepage down a wall: dark wet streaks from the top with green slime where they start. */
export const createStainTexture = (seed: number) => {
  const rand = mulberry32(seed);
  const { canvas, ctx } = makeRectCanvas(128, 256);
  for (let i = 0; i < 9; i++) {
    const x = 10 + rand() * 108;
    const w = 4 + rand() * 12;
    const length = 80 + rand() * 170;
    const g = ctx.createLinearGradient(0, 0, 0, length);
    g.addColorStop(0, 'rgba(14,18,14,0.6)');
    g.addColorStop(1, 'rgba(14,18,14,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(x - w / 2, 0);
    ctx.lineTo(x + w / 2, 0);
    ctx.quadraticCurveTo(x + w / 3, length * 0.7, x, length);
    ctx.quadraticCurveTo(x - w / 3, length * 0.7, x - w / 2, 0);
    ctx.fill();
  }
  const top = ctx.createLinearGradient(0, 0, 0, 40);
  top.addColorStop(0, 'rgba(60,90,30,0.7)');
  top.addColorStop(1, 'rgba(60,90,30,0)');
  ctx.fillStyle = top;
  ctx.fillRect(0, 0, 128, 40);
  return toTexture(canvas);
};

/** Litter on the floor: pebbles, twigs, straw and dry leaves. */
export const createDebrisTexture = (seed: number) => {
  const rand = mulberry32(seed);
  const { canvas, ctx } = makeCanvas(SIZE);
  const spot = () => {
    const a = rand() * Math.PI * 2;
    const d = Math.pow(rand(), 0.6) * 110;
    return [SIZE / 2 + Math.cos(a) * d, SIZE / 2 + Math.sin(a) * d] as Point;
  };
  for (let i = 0; i < 26; i++) {
    const [x, y] = spot();
    const r = 2 + rand() * 6;
    const v = 70 + rand() * 60;
    ctx.fillStyle = `rgb(${v},${v - 4},${v - 8})`;
    ctx.beginPath();
    ctx.ellipse(x, y, r, r * (0.6 + rand() * 0.4), rand() * 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.18)';
    ctx.beginPath();
    ctx.arc(x - r * 0.3, y - r * 0.3, r * 0.4, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.lineCap = 'round';
  for (let i = 0; i < 18; i++) {
    const [x, y] = spot();
    const a = rand() * Math.PI;
    const len = 8 + rand() * 22;
    ctx.strokeStyle = rand() > 0.5 ? `hsl(45,${40 + rand() * 20}%,${45 + rand() * 15}%)` : `hsl(25,35%,${18 + rand() * 12}%)`;
    ctx.lineWidth = 1 + rand() * 1.5;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    ctx.stroke();
  }
  for (let i = 0; i < 10; i++) {
    const [x, y] = spot();
    ctx.fillStyle = `hsl(${20 + rand() * 25},${45 + rand() * 20}%,${22 + rand() * 15}%)`;
    ctx.beginPath();
    ctx.ellipse(x, y, 5 + rand() * 3, 2.5, rand() * 3, 0, Math.PI * 2);
    ctx.fill();
  }
  return toTexture(canvas);
};

/** A portal's vortex: four arms winding in to a bright eye, fading at the rim. White, to be tinted. */
export const createSwirlTexture = () => {
  const { canvas, ctx } = makeCanvas(SIZE);
  const c = SIZE / 2;
  const eye = ctx.createRadialGradient(c, c, 0, c, c, c);
  eye.addColorStop(0, 'rgba(255,255,255,0.9)');
  eye.addColorStop(0.25, 'rgba(255,255,255,0.35)');
  eye.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = eye;
  ctx.fillRect(0, 0, SIZE, SIZE);
  const STEPS = 140;
  for (let arm = 0; arm < 4; arm++) {
    for (let i = 0; i < STEPS; i++) {
      const t = i / STEPS;
      const r = t * c * 0.95;
      const a = (arm * Math.PI) / 2 + t * Math.PI * 3.2;
      ctx.fillStyle = `rgba(255,255,255,${0.75 * (1 - t)})`;
      ctx.beginPath();
      ctx.arc(c + Math.cos(a) * r, c + Math.sin(a) * r, 2 + t * 9, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  return toTexture(canvas);
};
