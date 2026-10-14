import * as THREE from "three";

// Avatars live on a cross-origin S3 bucket without CORS headers, so nothing in
// the scene samples remote images: every texture here is drawn on a canvas.

const mulberry32 = (seed: number) => () => {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const makeCanvas = (size: number) => {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas context unavailable");
  return { canvas, ctx };
};

const speckle = (
  ctx: CanvasRenderingContext2D,
  size: number,
  rand: () => number,
  count: number,
) => {
  for (let i = 0; i < count; i++) {
    const light = rand() > 0.5;
    ctx.fillStyle = light
      ? `rgba(255,240,220,${0.03 + rand() * 0.05})`
      : `rgba(0,0,0,${0.08 + rand() * 0.12})`;
    const r = 0.5 + rand() * 1.8;
    ctx.beginPath();
    ctx.arc(rand() * size, rand() * size, r, 0, Math.PI * 2);
    ctx.fill();
  }
};

const makeRectCanvas = (width: number, height: number) => {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas context unavailable");
  return { canvas, ctx };
};

const toTexture = (canvas: HTMLCanvasElement, srgb = true) => {
  const tex = new THREE.CanvasTexture(canvas);
  if (srgb) tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
};

/** Old dark-stained planks for the table the board lies on. */
export const createTableWoodTexture = () => {
  const rand = mulberry32(11);
  const size = 1024;
  const { canvas, ctx } = makeCanvas(size);
  const planks = 5;
  const plankH = size / planks;

  for (let p = 0; p < planks; p++) {
    const y0 = p * plankH;
    const tone = 30 + Math.floor(rand() * 10);
    ctx.fillStyle = `rgb(${tone + 12},${tone + 4},${tone - 6})`;
    ctx.fillRect(0, y0, size, plankH);

    // Grain: long wavy strokes, a few darker knots of tension.
    const phase = rand() * 100;
    for (let g = 0; g < 70; g++) {
      const gy = y0 + rand() * plankH;
      const amp = 2 + rand() * 6;
      const freq = 0.004 + rand() * 0.01;
      ctx.strokeStyle = rand() > 0.5 ? `rgba(0,0,0,${0.12 + rand() * 0.2})` : `rgba(120,80,40,${0.05 + rand() * 0.08})`;
      ctx.lineWidth = 0.6 + rand() * 1.6;
      ctx.beginPath();
      for (let x = 0; x <= size; x += 8) {
        const y = gy + Math.sin(x * freq + phase + g) * amp;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    for (let k = 0; k < 2; k++) {
      const kx = rand() * size;
      const ky = y0 + plankH * (0.3 + rand() * 0.4);
      const knot = ctx.createRadialGradient(kx, ky, 0, kx, ky, 18 + rand() * 14);
      knot.addColorStop(0, "rgba(0,0,0,0.55)");
      knot.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = knot;
      ctx.fillRect(kx - 40, ky - 40, 80, 80);
    }
    // Seam between planks
    ctx.fillStyle = "rgba(0,0,0,0.75)";
    ctx.fillRect(0, y0, size, 3);
  }
  speckle(ctx, size, rand, 4000);

  const tex = toTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
};

/**
 * The board of fates: a near-black field engraved with gold — a border, the line
 * between the two players' halves and a star chart of constellations (the fates
 * the gods are wagering on). The near half is tinted cold, the far half crimson.
 */
export const createBoardTexture = (
  worldWidth: number,
  worldDepth: number,
  /** The location's art, painted into the board as a dark underlayer. Must be same-origin. */
  art?: HTMLImageElement | null,
) => {
  const rand = mulberry32(23);
  const longSide = 1536;
  const aspect = worldWidth / worldDepth;
  const w = aspect >= 1 ? longSide : Math.round(longSide * aspect);
  const h = aspect >= 1 ? Math.round(longSide / aspect) : longSide;
  const { canvas, ctx } = makeRectCanvas(w, h);

  ctx.fillStyle = "#0d0c10";
  ctx.fillRect(0, 0, w, h);

  if (art && art.naturalWidth > 0) {
    // Cover-fit the location art, then sink it into the board: desaturate, darken, vignette.
    const scale = Math.max(w / art.naturalWidth, h / art.naturalHeight);
    const dw = art.naturalWidth * scale;
    const dh = art.naturalHeight * scale;
    ctx.drawImage(art, (w - dw) / 2, (h - dh) / 2, dw, dh);
    ctx.globalCompositeOperation = "saturation";
    ctx.fillStyle = "rgba(128,128,128,0.45)";
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(10,9,13,0.44)";
    ctx.fillRect(0, 0, w, h);
    const vignette = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.25, w / 2, h / 2, Math.max(w, h) * 0.7);
    vignette.addColorStop(0, "rgba(13,12,16,0)");
    vignette.addColorStop(1, "rgba(13,12,16,0.92)");
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, w, h);
  }

  // Players' halves: far (top of texture) crimson, near (bottom) cold blue.
  const far = ctx.createLinearGradient(0, 0, 0, h / 2);
  far.addColorStop(0, "rgba(120,24,20,0.35)");
  far.addColorStop(1, "rgba(120,24,20,0.04)");
  ctx.fillStyle = far;
  ctx.fillRect(0, 0, w, h / 2);
  const near = ctx.createLinearGradient(0, h, 0, h / 2);
  near.addColorStop(0, "rgba(40,80,130,0.35)");
  near.addColorStop(1, "rgba(40,80,130,0.04)");
  ctx.fillStyle = near;
  ctx.fillRect(0, h / 2, w, h / 2);

  // Leather-like mottling
  for (let i = 0; i < 260; i++) {
    const x = rand() * w;
    const y = rand() * h;
    const r = 20 + rand() * 80;
    const blot = ctx.createRadialGradient(x, y, 0, x, y, r);
    blot.addColorStop(0, `rgba(0,0,0,${0.08 + rand() * 0.12})`);
    blot.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = blot;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }

  const gold = (a: number) => `rgba(214,184,96,${a})`;

  // Star chart: scattered stars, some joined into constellations.
  for (let i = 0; i < 420; i++) {
    ctx.fillStyle = gold(0.15 + rand() * 0.35);
    ctx.beginPath();
    ctx.arc(rand() * w, rand() * h, 0.6 + rand() * 1.6, 0, Math.PI * 2);
    ctx.fill();
  }
  for (let c = 0; c < 9; c++) {
    let x = 120 + rand() * Math.max(1, w - 240);
    let y = 100 + rand() * (h - 200);
    ctx.strokeStyle = gold(0.28);
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(x, y);
    const points: [number, number][] = [[x, y]];
    for (let s = 0; s < 4 + Math.floor(rand() * 3); s++) {
      x += (rand() - 0.5) * 220;
      y += (rand() - 0.5) * 160;
      ctx.lineTo(x, y);
      points.push([x, y]);
    }
    ctx.stroke();
    points.forEach(([px, py]) => {
      ctx.fillStyle = gold(0.75);
      ctx.beginPath();
      ctx.arc(px, py, 3.2, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // Engraved double border with corner knots
  const inset = 34;
  ctx.strokeStyle = gold(0.8);
  ctx.lineWidth = 4;
  ctx.strokeRect(inset, inset, w - inset * 2, h - inset * 2);
  ctx.lineWidth = 1.5;
  ctx.strokeRect(inset + 14, inset + 14, w - (inset + 14) * 2, h - (inset + 14) * 2);
  for (const [cx, cy] of [[inset, inset], [w - inset, inset], [inset, h - inset], [w - inset, h - inset]]) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Math.PI / 4);
    ctx.fillStyle = gold(0.9);
    ctx.fillRect(-11, -11, 22, 22);
    ctx.fillStyle = "#0d0c10";
    ctx.fillRect(-5, -5, 10, 10);
    ctx.restore();
  }

  // Line dividing the two players' halves, broken by the rune circle in the middle.
  ctx.strokeStyle = gold(0.55);
  ctx.lineWidth = 2;
  ctx.setLineDash([18, 10]);
  ctx.beginPath();
  ctx.moveTo(inset + 14, h / 2);
  ctx.lineTo(w / 2 - h * 0.2, h / 2);
  ctx.moveTo(w / 2 + h * 0.2, h / 2);
  ctx.lineTo(w - inset - 14, h / 2);
  ctx.stroke();
  ctx.setLineDash([]);

  speckle(ctx, Math.max(w, h), rand, 6000);
  return toTexture(canvas);
};

const PIP_LAYOUT: Record<number, [number, number][]> = {
  1: [[0.5, 0.5]],
  2: [[0.27, 0.27], [0.73, 0.73]],
  3: [[0.27, 0.27], [0.5, 0.5], [0.73, 0.73]],
  4: [[0.27, 0.27], [0.73, 0.27], [0.27, 0.73], [0.73, 0.73]],
  5: [[0.27, 0.27], [0.73, 0.27], [0.5, 0.5], [0.27, 0.73], [0.73, 0.73]],
  6: [[0.27, 0.25], [0.73, 0.25], [0.27, 0.5], [0.73, 0.5], [0.27, 0.75], [0.73, 0.75]],
};

/** One face of an old bone die: yellowed ivory with dark carved pips. */
export const createDieFaceTexture = (value: number) => {
  const size = 128;
  const rand = mulberry32(100 + value);
  const { canvas, ctx } = makeCanvas(size);
  const base = ctx.createRadialGradient(size / 2, size / 2, 10, size / 2, size / 2, size * 0.75);
  base.addColorStop(0, "#efe2c2");
  base.addColorStop(1, "#b9a57a");
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, size, size);
  speckle(ctx, size, rand, 300);
  for (const [px, py] of PIP_LAYOUT[value]) {
    ctx.fillStyle = value === 6 ? "#5a0f0a" : "#1c120a";
    ctx.beginPath();
    ctx.arc(px * size, py * size, size * 0.085, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(255,240,210,0.35)";
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  return toTexture(canvas);
};

/** Struck face of a gold coin: rim, beaded ring and a crown-like sigil. */
export const createCoinFaceTexture = () => {
  const size = 128;
  const { canvas, ctx } = makeCanvas(size);
  const c = size / 2;
  const gold = ctx.createRadialGradient(c * 0.7, c * 0.7, 4, c, c, c);
  gold.addColorStop(0, "#fff0a8");
  gold.addColorStop(0.6, "#d6a93c");
  gold.addColorStop(1, "#8a6418");
  ctx.fillStyle = gold;
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = "rgba(90,60,10,0.8)";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(c, c, c * 0.86, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = "rgba(90,60,10,0.7)";
  for (let i = 0; i < 28; i++) {
    const a = (i / 28) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(c + Math.cos(a) * c * 0.74, c + Math.sin(a) * c * 0.74, 2.2, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(c - 22, c + 14);
  ctx.lineTo(c - 22, c - 10);
  ctx.lineTo(c - 8, c + 2);
  ctx.lineTo(c, c - 18);
  ctx.lineTo(c + 8, c + 2);
  ctx.lineTo(c + 22, c - 10);
  ctx.lineTo(c + 22, c + 14);
  ctx.closePath();
  ctx.stroke();
  return toTexture(canvas);
};

/** Back of a fate card: deep crimson field, gilt border and a central rune wheel. */
export const createCardBackTexture = () => {
  const w = 128;
  const h = 180;
  const rand = mulberry32(41);
  const { canvas, ctx } = makeRectCanvas(w, h);
  const field = ctx.createLinearGradient(0, 0, w, h);
  field.addColorStop(0, "#4a0f12");
  field.addColorStop(1, "#22070a");
  ctx.fillStyle = field;
  ctx.fillRect(0, 0, w, h);
  speckle(ctx, Math.max(w, h), rand, 400);
  ctx.strokeStyle = "#c9a24a";
  ctx.lineWidth = 4;
  ctx.strokeRect(6, 6, w - 12, h - 12);
  ctx.lineWidth = 1.5;
  ctx.strokeRect(13, 13, w - 26, h - 26);
  const cx = w / 2;
  const cy = h / 2;
  ctx.lineWidth = 2;
  for (const r of [34, 24]) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * 24, cy + Math.sin(a) * 24);
    ctx.lineTo(cx + Math.cos(a) * 34, cy + Math.sin(a) * 34);
    ctx.stroke();
  }
  ctx.fillStyle = "#c9a24a";
  ctx.beginPath();
  ctx.moveTo(cx, cy - 12);
  ctx.lineTo(cx + 8, cy);
  ctx.lineTo(cx, cy + 12);
  ctx.lineTo(cx - 8, cy);
  ctx.closePath();
  ctx.fill();
  return toTexture(canvas);
};

const RUNE_STROKES: [number, number, number, number][][] = [
  [[0.5, 0.15, 0.5, 0.85], [0.5, 0.35, 0.78, 0.18]],
  [[0.3, 0.15, 0.3, 0.85], [0.3, 0.15, 0.72, 0.5], [0.72, 0.5, 0.3, 0.85]],
  [[0.5, 0.15, 0.5, 0.85], [0.22, 0.4, 0.78, 0.4], [0.22, 0.62, 0.78, 0.62]],
  [[0.25, 0.85, 0.5, 0.15], [0.5, 0.15, 0.75, 0.85], [0.35, 0.55, 0.65, 0.55]],
];

/** A gold rune carved into a stone, on transparent ground (laid over the stone's top). */
export const createRuneGlyphTexture = (variant: number) => {
  const size = 64;
  const { canvas, ctx } = makeCanvas(size);
  ctx.strokeStyle = "rgba(240,205,110,0.95)";
  ctx.lineWidth = 5;
  ctx.lineCap = "round";
  for (const [x1, y1, x2, y2] of RUNE_STROKES[variant % RUNE_STROKES.length]) {
    ctx.beginPath();
    ctx.moveTo(x1 * size, y1 * size);
    ctx.lineTo(x2 * size, y2 * size);
    ctx.stroke();
  }
  return toTexture(canvas);
};

/** Pressed red wax: a seal ring with a sigil, darker in the recesses. */
export const createWaxSealTexture = () => {
  const size = 128;
  const { canvas, ctx } = makeCanvas(size);
  const c = size / 2;
  const wax = ctx.createRadialGradient(c * 0.8, c * 0.7, 5, c, c, c);
  wax.addColorStop(0, "#c8352a");
  wax.addColorStop(0.7, "#8e1a14");
  wax.addColorStop(1, "#4d0a07");
  ctx.fillStyle = wax;
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = "rgba(40,4,2,0.75)";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(c, c, c * 0.7, 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.moveTo(c, c - 26);
  ctx.lineTo(c, c + 26);
  ctx.moveTo(c - 20, c - 6);
  ctx.lineTo(c + 20, c - 6);
  ctx.moveTo(c - 14, c + 16);
  ctx.lineTo(c + 14, c + 16);
  ctx.stroke();
  return toTexture(canvas);
};

/** Aged parchment for a folded letter: warm stained paper with a fold line. */
export const createParchmentTexture = () => {
  const w = 192;
  const h = 128;
  const rand = mulberry32(57);
  const { canvas, ctx } = makeRectCanvas(w, h);
  const paper = ctx.createRadialGradient(w / 2, h / 2, 10, w / 2, h / 2, w * 0.7);
  paper.addColorStop(0, "#d9c497");
  paper.addColorStop(1, "#8e7448");
  ctx.fillStyle = paper;
  ctx.fillRect(0, 0, w, h);
  speckle(ctx, w, rand, 900);
  ctx.strokeStyle = "rgba(70,45,15,0.35)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, h / 2);
  ctx.lineTo(w, h / 2);
  ctx.stroke();
  ctx.strokeStyle = "rgba(40,25,10,0.35)";
  ctx.lineWidth = 1.2;
  for (let y = 18; y < h - 12; y += 10) {
    if (Math.abs(y - h / 2) < 6) continue;
    ctx.beginPath();
    ctx.moveTo(16, y);
    ctx.lineTo(w - 16 - rand() * 50, y);
    ctx.stroke();
  }
  return toTexture(canvas);
};

/** A quill feather: pale vane with a dark tip, on transparent ground. */
export const createFeatherTexture = () => {
  const w = 64;
  const h = 256;
  const { canvas, ctx } = makeRectCanvas(w, h);
  const cx = w / 2;
  for (let y = 20; y < h - 30; y += 3) {
    const t = (y - 20) / (h - 50);
    const half = Math.sin(Math.min(1, t * 1.15) * Math.PI) * (w * 0.42);
    const shade = Math.round(225 - t * 80);
    ctx.strokeStyle = `rgba(${shade},${shade - 8},${shade - 20},0.9)`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, y);
    ctx.lineTo(cx - half, y - 10);
    ctx.moveTo(cx, y);
    ctx.lineTo(cx + half, y - 10);
    ctx.stroke();
  }
  ctx.strokeStyle = "#3b2a18";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(cx, 8);
  ctx.lineTo(cx, h - 4);
  ctx.stroke();
  return toTexture(canvas);
};

// --- Worn brass ---

/**
 * Colour, bump and roughness maps for the board's brass rim after ages of play:
 * dark tarnish and green verdigris, bright spots rubbed by hands, scratches, dents
 * and a few deep nicks. Laid out along the length of a rim bar (u = along the bar).
 */
export const createWornBrassTextures = () => {
  const rand = mulberry32(91);
  const w = 1024;
  const h = 96;
  const color = makeRectCanvas(w, h);
  const bump = makeRectCanvas(w, h);
  const rough = makeRectCanvas(w, h);
  const c = color.ctx;
  const b = bump.ctx;
  const r = rough.ctx;

  c.fillStyle = "#8a6a2e";
  c.fillRect(0, 0, w, h);
  b.fillStyle = "#808080";
  b.fillRect(0, 0, w, h);
  r.fillStyle = "#6e6e6e";
  r.fillRect(0, 0, w, h);

  const blot = (ctx: CanvasRenderingContext2D, x: number, y: number, radius: number, colorStop: string) => {
    const g = ctx.createRadialGradient(x, y, 0, x, y, radius);
    g.addColorStop(0, colorStop);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  };

  // Tarnish everywhere, heaviest toward the ends (the corners of the board).
  for (let i = 0; i < 70; i++) {
    const x = rand() * w;
    const toEnd = Math.min(x, w - x) / (w / 2);
    blot(c, x, rand() * h, 20 + rand() * 60, `rgba(35,22,8,${0.12 + (1 - toEnd) * 0.3})`);
    blot(r, x, rand() * h, 30 + rand() * 50, "rgba(220,220,220,0.35)");
  }
  // Verdigris creeping out of the corners.
  for (const end of [0, w]) {
    for (let i = 0; i < 6; i++) {
      blot(c, end + (end ? -1 : 1) * rand() * 110, rand() * h, 14 + rand() * 26, "rgba(70,105,72,0.45)");
    }
  }
  // Bright metal where hands rest and slide along the rim.
  for (let i = 0; i < 14; i++) {
    const x = w * 0.1 + rand() * w * 0.8;
    blot(c, x, h * (0.3 + rand() * 0.4), 40 + rand() * 50, "rgba(255,226,140,0.38)");
    blot(r, x, h * 0.5, 50, "rgba(30,30,30,0.5)");
  }

  // Scratches: dark in colour and bump, glossier in roughness.
  for (let i = 0; i < 140; i++) {
    const x = rand() * w;
    const y = rand() * h;
    const a = (rand() - 0.5) * 0.6;
    const len = 10 + rand() * 70;
    const x2 = x + Math.cos(a) * len;
    const y2 = y + Math.sin(a) * len;
    for (const [ctx, style, lw] of [
      [c, `rgba(40,25,8,${0.25 + rand() * 0.3})`, 1],
      [b, "rgba(20,20,20,0.7)", 1.4],
      [r, "rgba(40,40,40,0.6)", 1],
    ] as [CanvasRenderingContext2D, string, number][]) {
      ctx.strokeStyle = style;
      ctx.lineWidth = lw;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }
  }

  // Dents: dark centre, light rim in the bump map.
  for (let i = 0; i < 10; i++) {
    const x = rand() * w;
    const y = h * (0.2 + rand() * 0.6);
    const rad = 6 + rand() * 12;
    blot(b, x, y, rad, "rgba(0,0,0,0.8)");
    b.strokeStyle = "rgba(255,255,255,0.35)";
    b.lineWidth = 2;
    b.beginPath();
    b.arc(x, y, rad, 0, Math.PI * 2);
    b.stroke();
    blot(c, x, y, rad, "rgba(30,18,6,0.35)");
  }

  // A few deep nicks across the bar, as if a blade came down on it.
  for (let i = 0; i < 4; i++) {
    const x = 120 + rand() * (w - 240);
    for (const [ctx, style, lw] of [
      [c, "rgba(25,14,4,0.85)", 3],
      [b, "rgba(0,0,0,1)", 5],
    ] as [CanvasRenderingContext2D, string, number][]) {
      ctx.strokeStyle = style;
      ctx.lineWidth = lw;
      ctx.beginPath();
      ctx.moveTo(x, h * 0.1);
      ctx.lineTo(x + 8, h * 0.9);
      ctx.stroke();
    }
  }

  speckle(c, w, rand, 1800);

  const map = toTexture(color.canvas);
  const bumpMap = toTexture(bump.canvas, false);
  const roughnessMap = toTexture(rough.canvas, false);
  return { map, bumpMap, roughnessMap };
};

// --- Table scars ---

export const SCARS_WORLD_WIDTH = 28;
export const SCARS_WORLD_DEPTH = 15;
const SCARS_PX_PER_UNIT = 64;

/** A carved groove: dark cut with a pale lifted edge on one side. */
const carve = (
  ctx: CanvasRenderingContext2D,
  points: [number, number][],
  width: number,
  depth = 0.75,
) => {
  const path = () => {
    ctx.beginPath();
    points.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
  };
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.save();
  ctx.translate(1.5, 1.5);
  ctx.strokeStyle = "rgba(255,225,170,0.16)";
  ctx.lineWidth = width;
  path();
  ctx.stroke();
  ctx.restore();
  ctx.strokeStyle = `rgba(8,4,2,${depth})`;
  ctx.lineWidth = width;
  path();
  ctx.stroke();
};

/**
 * Everything the gods' long games have left on the table, on a transparent layer the
 * size of the table area around the board. World x/z map to canvas x/y.
 */
export const createTableScarsTexture = () => {
  const rand = mulberry32(77);
  const w = SCARS_WORLD_WIDTH * SCARS_PX_PER_UNIT;
  const h = SCARS_WORLD_DEPTH * SCARS_PX_PER_UNIT;
  const { canvas, ctx } = makeRectCanvas(w, h);
  const X = (x: number) => (x + SCARS_WORLD_WIDTH / 2) * SCARS_PX_PER_UNIT;
  const Z = (z: number) => (z + SCARS_WORLD_DEPTH / 2) * SCARS_PX_PER_UNIT;
  const jag = (x1: number, z1: number, x2: number, z2: number, steps = 7, wobble = 0.05) =>
    Array.from({ length: steps + 1 }, (_, i): [number, number] => {
      const t = i / steps;
      return [
        X(x1 + (x2 - x1) * t + (rand() - 0.5) * wobble),
        Z(z1 + (z2 - z1) * t + (rand() - 0.5) * wobble),
      ];
    });

  // Rings left by cups and goblets over countless nights.
  for (const [x, z, r] of [[8.4, -2.0, 0.42], [9.7, -0.9, 0.38], [-10.2, 2.9, 0.4], [-11.4, -2.4, 0.36]]) {
    ctx.strokeStyle = "rgba(40,14,6,0.45)";
    ctx.lineWidth = 0.09 * SCARS_PX_PER_UNIT;
    ctx.beginPath();
    ctx.arc(X(x), Z(z), r * SCARS_PX_PER_UNIT, rand() * 2, rand() * 2 + Math.PI * 1.7);
    ctx.stroke();
  }

  // Scorch marks around the candle dishes.
  for (const [x, z] of [[-7.1, 3.9], [7.1, 3.9], [-7.1, -3.9], [7.1, -3.9]]) {
    const burn = ctx.createRadialGradient(X(x), Z(z), 0, X(x), Z(z), 1.3 * SCARS_PX_PER_UNIT);
    burn.addColorStop(0, "rgba(0,0,0,0.5)");
    burn.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = burn;
    ctx.fillRect(X(x) - 90, Z(z) - 90, 180, 180);
  }

  // Knife gouges: someone lost their temper — and the game.
  for (let i = 0; i < 9; i++) {
    const side = i % 2 ? 1 : -1;
    const x = side * (7.6 + rand() * 3.6);
    const z = -5 + rand() * 10;
    const a = rand() * Math.PI;
    const len = 0.6 + rand() * 1.2;
    carve(ctx, jag(x, z, x + Math.cos(a) * len, z + Math.sin(a) * len, 5, 0.04), 3 + rand() * 3);
  }

  // Four parallel claw marks raked across the right side of the table.
  for (let k = 0; k < 4; k++) {
    const pts: [number, number][] = [];
    for (let i = 0; i <= 12; i++) {
      const t = i / 12;
      pts.push([X(9.3 + t * 1.9 + k * 0.17), Z(-3.6 + t * 1.3 + Math.sin(t * Math.PI) * 0.25 + k * 0.05)]);
    }
    carve(ctx, pts, 5 - k * 0.6, 0.85);
  }

  // The gods' old score, in the lower right corner: one row of tallies per god, split by a line.
  const tally = (x0: number, z0: number, count: number) => {
    for (let i = 0; i < count; i++) {
      const group = Math.floor(i / 5);
      const inGroup = i % 5;
      const gx = x0 + group * 0.62;
      if (inGroup < 4) {
        const x = gx + inGroup * 0.11;
        carve(ctx, jag(x, z0, x + 0.02, z0 + 0.5, 3, 0.02), 3.5);
      } else {
        carve(ctx, jag(gx - 0.06, z0 + 0.4, gx + 0.42, z0 + 0.08, 3, 0.02), 3.5);
      }
    }
  };
  tally(9.7, 2.35, 23);
  carve(ctx, jag(9.5, 3.02, 12.8, 3.04, 6, 0.03), 4);
  tally(9.7, 3.22, 21);

  // A crude rune cut into the left of the table with a knife point.
  const rx = -9.6;
  const rz = -3.2;
  carve(ctx, jag(rx, rz - 0.6, rx, rz + 0.6, 4, 0.04), 4.5);
  carve(ctx, jag(rx, rz - 0.2, rx + 0.45, rz - 0.6, 3, 0.04), 4.5);
  carve(ctx, jag(rx, rz + 0.1, rx - 0.45, rz - 0.3, 3, 0.04), 4.5);
  ctx.strokeStyle = "rgba(8,4,2,0.6)";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(X(rx), Z(rz), 0.85 * SCARS_PX_PER_UNIT, 0, Math.PI * 2);
  ctx.stroke();

  // Fine surface scratches everywhere.
  for (let i = 0; i < 160; i++) {
    const x = -SCARS_WORLD_WIDTH / 2 + rand() * SCARS_WORLD_WIDTH;
    const z = -SCARS_WORLD_DEPTH / 2 + rand() * SCARS_WORLD_DEPTH;
    const a = rand() * Math.PI;
    const len = 0.15 + rand() * 0.5;
    ctx.strokeStyle = `rgba(8,4,2,${0.18 + rand() * 0.2})`;
    ctx.lineWidth = 1 + rand();
    ctx.beginPath();
    ctx.moveTo(X(x), Z(z));
    ctx.lineTo(X(x + Math.cos(a) * len), Z(z + Math.sin(a) * len));
    ctx.stroke();
  }

  return toTexture(canvas);
};

export const TALLY_WORLD_WIDTH = 2.6;
export const TALLY_WORLD_DEPTH = 1.1;
const TALLY_PX = 160;
const TALLY_PER_ROW = 25;

/**
 * Notches for the turns of this battle, cut in groups of five. With `onlyLast` the
 * texture holds just the newest notch (drawn bright) for the glow overlay.
 */
export const createTurnTallyTexture = (turns: number, onlyLast = false) => {
  const w = Math.round(TALLY_WORLD_WIDTH * TALLY_PX);
  const h = Math.round(TALLY_WORLD_DEPTH * TALLY_PX);
  const { canvas, ctx } = makeRectCanvas(w, h);
  const shown = Math.min(turns, TALLY_PER_ROW * 2);
  const notch = (i: number) => {
    const row = Math.floor(i / TALLY_PER_ROW);
    const k = i % TALLY_PER_ROW;
    const group = Math.floor(k / 5);
    const inGroup = k % 5;
    const gx = 18 + group * 78;
    const top = 14 + row * 84;
    if (inGroup < 4) {
      const x = gx + inGroup * 14;
      return [[x, top], [x + 2, top + 60]] as [number, number][];
    }
    return [[gx - 8, top + 50], [gx + 52, top + 10]] as [number, number][];
  };
  for (let i = 0; i < shown; i++) {
    if (onlyLast && i !== shown - 1) continue;
    if (onlyLast) {
      ctx.strokeStyle = "rgba(255,215,110,1)";
      ctx.lineWidth = 7;
      ctx.lineCap = "round";
      const [[x1, y1], [x2, y2]] = notch(i);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    } else {
      // Fresh cuts expose pale raw wood, unlike the old dark scars around them.
      const [[x1, y1], [x2, y2]] = notch(i);
      ctx.lineCap = "round";
      ctx.strokeStyle = "rgba(214,172,112,0.9)";
      ctx.lineWidth = 9;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
      ctx.strokeStyle = "rgba(45,22,8,0.75)";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }
  }
  return toTexture(canvas);
};

/** Split wood round a blade driven into the table: jagged dark cracks radiating out. */
export const createWoodSplitTexture = () => {
  const size = 256;
  const rand = mulberry32(131);
  const { canvas, ctx } = makeCanvas(size);
  const c = size / 2;
  const hole = ctx.createRadialGradient(c, c, 0, c, c, 26);
  hole.addColorStop(0, "rgba(0,0,0,0.85)");
  hole.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = hole;
  ctx.fillRect(0, 0, size, size);
  ctx.lineCap = "round";
  // The grain runs along x, so the wood splits mostly that way.
  const rays = [0, Math.PI, 0.35, Math.PI + 0.3, -0.4, Math.PI - 0.5, 1.5];
  rays.forEach((angle, i) => {
    let x = c;
    let y = c;
    const len = (i < 2 ? 110 : 45) + rand() * 20;
    ctx.strokeStyle = `rgba(10,5,2,${i < 2 ? 0.85 : 0.6})`;
    ctx.lineWidth = i < 2 ? 3 : 1.6;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let d = 0; d < len; d += 8) {
      const a = angle + (rand() - 0.5) * 0.5;
      x += Math.cos(a) * 8;
      y += Math.sin(a) * 8;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  });
  return toTexture(canvas);
};

/** Teardrop candle flame: white-hot core, amber body, fading tip — used as a sprite. */
export const createFlameTexture = () => {
  const w = 64;
  const h = 128;
  const { canvas, ctx } = makeRectCanvas(w, h);
  ctx.save();
  // Stretch a radial gradient vertically; its centre sits low so the tip tapers upward.
  ctx.translate(w / 2, h * 0.68);
  ctx.scale(1, 2.1);
  const body = ctx.createRadialGradient(0, 0, 0, 0, 0, w / 2);
  body.addColorStop(0, "rgba(255,252,235,1)");
  body.addColorStop(0.25, "rgba(255,220,140,0.95)");
  body.addColorStop(0.55, "rgba(255,150,50,0.55)");
  body.addColorStop(1, "rgba(255,90,20,0)");
  ctx.fillStyle = body;
  ctx.beginPath();
  ctx.arc(0, 0, w / 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  return toTexture(canvas);
};

/** Soft white spot fading to transparent — tinted for card glows and contact shadows. */
export const createSoftSpotTexture = () => {
  const { canvas, ctx } = makeCanvas(256);
  const spot = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
  spot.addColorStop(0, "rgba(255,255,255,1)");
  spot.addColorStop(0.45, "rgba(255,255,255,0.45)");
  spot.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = spot;
  ctx.fillRect(0, 0, 256, 256);
  return toTexture(canvas, false);
};

/** Thin golden rune circle, drawn once and laid flat in the arena centre. */
export const createRuneCircleTexture = () => {
  const size = 1024;
  const { canvas, ctx } = makeCanvas(size);
  const c = size / 2;
  ctx.strokeStyle = "rgba(240,217,92,0.9)";
  ctx.fillStyle = "rgba(240,217,92,0.9)";

  const ring = (radius: number, width: number) => {
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.arc(c, c, radius, 0, Math.PI * 2);
    ctx.stroke();
  };
  ring(c * 0.96, 6);
  ring(c * 0.86, 3);
  ring(c * 0.5, 3);

  // Runic glyph band between the outer rings.
  const glyphs = 36;
  ctx.lineWidth = 4;
  for (let i = 0; i < glyphs; i++) {
    const a = (i / glyphs) * Math.PI * 2;
    ctx.save();
    ctx.translate(c + Math.cos(a) * c * 0.91, c + Math.sin(a) * c * 0.91);
    ctx.rotate(a + Math.PI / 2);
    ctx.beginPath();
    const variant = i % 4;
    ctx.moveTo(0, -14);
    ctx.lineTo(0, 14);
    if (variant === 0) { ctx.moveTo(0, -4); ctx.lineTo(10, -14); }
    if (variant === 1) { ctx.moveTo(-9, 0); ctx.lineTo(9, 0); }
    if (variant === 2) { ctx.moveTo(0, 4); ctx.lineTo(-10, 14); ctx.moveTo(0, -4); ctx.lineTo(10, -14); }
    if (variant === 3) { ctx.moveTo(-8, -10); ctx.lineTo(8, 10); }
    ctx.stroke();
    ctx.restore();
  }

  // Two interlocked triangles — the hexagram at the heart of the circle.
  ctx.lineWidth = 3;
  for (const rot of [0, Math.PI]) {
    ctx.beginPath();
    for (let k = 0; k <= 3; k++) {
      const a = rot - Math.PI / 2 + (k / 3) * Math.PI * 2;
      const x = c + Math.cos(a) * c * 0.84;
      const y = c + Math.sin(a) * c * 0.84;
      if (k === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
};
