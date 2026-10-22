import * as THREE from 'three';
import { mulberry32 } from './bookTextures';
import { scrawl } from './spreadTextures';

/*
  The chart spread over the table of fates, under all the books: the world's
  own map, washed onto parchment. Until it arrives (or if it never does) the
  lands are drawn from a seed instead — coasts, mountains, forests, rivers —
  under rhumb lines from a compass rose. Either way the sheet is then aged:
  folded, stained, and spotted with ink and wax where the inkwells and candles
  have stood on it.
*/

/** Largest texture side drawn, so phones that cap textures at 4096 still take it. */
const MAX_TEXTURE = 4096;
/** Canvas pixels per world unit, when the cap allows. */
const PX_PER_UNIT = 110;
/** Spacing of the elevation samples coasts are traced through, canvas pixels. */
const CELL = 8;
/** Elevation where land rises out of the sea. */
const SEA_LEVEL = 0.5;

const PARCHMENT = '#d3b98c';
const INK = 'rgba(62,38,18,0.88)';
const FAINT = 'rgba(62,38,18,0.42)';
const FADED_RED = 'rgba(150,52,30,0.32)';

/** A point on the map in world units, from its centre: [x, z]. */
export type MapPoint = [number, number];

/** What has been set down on the map and left its mark. */
export interface MapMarks {
  /** Compass roses; on a drawn map each throws its rhumb lines across the sea. */
  roses: MapPoint[];
  /** Where inkwells stand: a ring, a blot and spatters. */
  inkSpots: MapPoint[];
  /** Where candles stand: drips of wax. */
  waxSpots: MapPoint[];
}

/** Smooth fractal value noise, the same for the same seed. */
const makeNoise = (seed: number) => {
  const rand = mulberry32(seed);
  const SIZE = 256;
  const table = Float32Array.from({ length: SIZE * SIZE }, rand);
  const at = (x: number, y: number) => table[(((y % SIZE) + SIZE) % SIZE) * SIZE + (((x % SIZE) + SIZE) % SIZE)];
  const smooth = (t: number) => t * t * (3 - 2 * t);
  const noise = (x: number, y: number) => {
    const xi = Math.floor(x);
    const yi = Math.floor(y);
    const fx = smooth(x - xi);
    const fy = smooth(y - yi);
    const a = at(xi, yi);
    const b = at(xi + 1, yi);
    const c = at(xi, yi + 1);
    const d = at(xi + 1, yi + 1);
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
  };
  return (x: number, y: number, octaves = 5) => {
    let sum = 0;
    let amp = 0.5;
    let freq = 1;
    let norm = 0;
    for (let o = 0; o < octaves; o++) {
      sum += noise(x * freq + o * 17.3, y * freq + o * 31.7) * amp;
      norm += amp;
      amp *= 0.5;
      freq *= 2.03;
    }
    return sum / norm;
  };
};

/**
 * Lines where a sampled field crosses a level, by marching squares. The field
 * is sampled every CELL pixels, gw samples to a row.
 */
const traceContour = (ctx: CanvasRenderingContext2D, field: Float32Array, gw: number, gh: number, level: number) => {
  const lerp = (p: number, q: number) => (level - p) / (q - p);
  ctx.beginPath();
  for (let j = 0; j < gh - 1; j++) {
    for (let i = 0; i < gw - 1; i++) {
      const a = field[j * gw + i];
      const b = field[j * gw + i + 1];
      const c = field[(j + 1) * gw + i + 1];
      const d = field[(j + 1) * gw + i];
      const idx = (a > level ? 8 : 0) | (b > level ? 4 : 0) | (c > level ? 2 : 0) | (d > level ? 1 : 0);
      if (idx === 0 || idx === 15) continue;
      const x = i * CELL;
      const y = j * CELL;
      const top: [number, number] = [x + CELL * lerp(a, b), y];
      const right: [number, number] = [x + CELL, y + CELL * lerp(b, c)];
      const bottom: [number, number] = [x + CELL * lerp(d, c), y + CELL];
      const left: [number, number] = [x, y + CELL * lerp(a, d)];
      const seg = (p: [number, number], q: [number, number]) => {
        ctx.moveTo(p[0], p[1]);
        ctx.lineTo(q[0], q[1]);
      };
      switch (idx) {
        case 1: case 14: seg(left, bottom); break;
        case 2: case 13: seg(bottom, right); break;
        case 3: case 12: seg(left, right); break;
        case 4: case 11: seg(top, right); break;
        case 6: case 9: seg(top, bottom); break;
        case 7: case 8: seg(left, top); break;
        case 5: seg(top, right); seg(left, bottom); break;
        case 10: seg(left, top); seg(bottom, right); break;
      }
    }
  }
  ctx.stroke();
};

/** A compass rose: rings, ticks and an eight-pointed star, north marked. */
const drawRose = (ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) => {
  ctx.save();
  ctx.strokeStyle = INK;
  ctx.fillStyle = INK;
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.86, 0, Math.PI * 2);
  ctx.stroke();
  for (let i = 0; i < 32; i++) {
    const a = (i / 32) * Math.PI * 2;
    const inner = i % 4 === 0 ? r * 0.78 : r * 0.86;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner);
    ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    ctx.stroke();
  }
  // Short points under the long ones; each point half filled, half bare.
  for (const long of [false, true]) {
    for (let k = long ? 0 : 1; k < 8; k += 2) {
      const a = (k * Math.PI) / 4 - Math.PI / 2;
      const len = long ? r * 1.08 : r * 0.62;
      const w = r * 0.15;
      const tip = [cx + Math.cos(a) * len, cy + Math.sin(a) * len];
      const l = [cx + Math.cos(a - Math.PI / 2) * w, cy + Math.sin(a - Math.PI / 2) * w];
      const rt = [cx + Math.cos(a + Math.PI / 2) * w, cy + Math.sin(a + Math.PI / 2) * w];
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(tip[0], tip[1]);
      ctx.lineTo(l[0], l[1]);
      ctx.closePath();
      ctx.fillStyle = INK;
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(tip[0], tip[1]);
      ctx.lineTo(rt[0], rt[1]);
      ctx.closePath();
      ctx.fillStyle = PARCHMENT;
      ctx.fill();
      ctx.stroke();
    }
  }
  ctx.font = `bold ${Math.round(r * 0.3)}px serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = INK;
  ctx.fillText('С', cx, cy - r * 1.14);
  ctx.restore();
};

/** A peak, its far slope hatched in shadow. */
const drawMountain = (ctx: CanvasRenderingContext2D, x: number, y: number, s: number, rand: () => number) => {
  const peakX = x + (rand() - 0.5) * s * 0.4;
  const peakY = y - s * (1.1 + rand() * 0.4);
  ctx.beginPath();
  ctx.moveTo(x - s, y);
  ctx.quadraticCurveTo(x - s * 0.45, y - s * 0.6, peakX, peakY);
  ctx.quadraticCurveTo(x + s * 0.45, y - s * 0.55, x + s, y);
  ctx.stroke();
  ctx.beginPath();
  for (let i = 1; i <= 3; i++) {
    const t = i / 4;
    const sx = peakX + (x + s - peakX) * t;
    const sy = peakY + (y - peakY) * t;
    ctx.moveTo(sx, sy);
    ctx.lineTo(sx - s * 0.18, sy + (y - sy) * 0.8);
  }
  ctx.stroke();
};

/** Ink pooled where an inkwell stood: a ring from its foot, a blot, spatters and a wiped pen. */
const drawInkSpot = (ctx: CanvasRenderingContext2D, x: number, y: number, scale: number, rand: () => number) => {
  ctx.save();
  ctx.strokeStyle = 'rgba(25,15,8,0.28)';
  ctx.lineWidth = 0.05 * scale;
  ctx.beginPath();
  ctx.arc(x + 0.25 * scale, y - 0.1 * scale, 0.5 * scale, 0.4, Math.PI * 1.7);
  ctx.stroke();
  ctx.fillStyle = 'rgba(18,10,6,0.72)';
  const bx = x - 0.75 * scale;
  const by = y + 0.45 * scale;
  for (let i = 0; i < 7; i++) {
    ctx.beginPath();
    ctx.arc(bx + (rand() - 0.5) * 0.25 * scale, by + (rand() - 0.5) * 0.18 * scale, (0.06 + rand() * 0.08) * scale, 0, Math.PI * 2);
    ctx.fill();
  }
  for (let i = 0; i < 14; i++) {
    const a = rand() * Math.PI * 2;
    const d = (0.25 + rand() * 0.5) * scale;
    ctx.beginPath();
    ctx.arc(bx + Math.cos(a) * d, by + Math.sin(a) * d * 0.7, (0.008 + rand() * 0.02) * scale, 0, Math.PI * 2);
    ctx.fill();
  }
  // Where the pen was wiped clean.
  ctx.strokeStyle = 'rgba(18,10,6,0.4)';
  ctx.lineCap = 'round';
  for (let i = 0; i < 3; i++) {
    ctx.lineWidth = (0.02 + rand() * 0.02) * scale;
    ctx.beginPath();
    const sy = y + (0.75 + i * 0.07) * scale;
    ctx.moveTo(x - 0.2 * scale, sy);
    ctx.quadraticCurveTo(x + 0.15 * scale, sy - 0.08 * scale, x + (0.45 + rand() * 0.2) * scale, sy + 0.02 * scale);
    ctx.stroke();
  }
  ctx.restore();
};

/** Wax dripped round a candle's foot. */
const drawWaxSpot = (ctx: CanvasRenderingContext2D, x: number, y: number, scale: number, rand: () => number) => {
  ctx.save();
  for (let i = 0; i < 10; i++) {
    const a = rand() * Math.PI * 2;
    const d = (0.55 + rand() * 0.6) * scale;
    const r = (0.025 + rand() * 0.06) * scale;
    const dx = x + Math.cos(a) * d;
    const dy = y + Math.sin(a) * d;
    ctx.fillStyle = 'rgba(242,232,204,0.85)';
    ctx.strokeStyle = 'rgba(140,115,70,0.45)';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.ellipse(dx, dy, r, r * (0.7 + rand() * 0.3), rand() * Math.PI, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
  ctx.restore();
};

/** Margin left round the world's map inside the sheet, and how far its edges fade into the parchment, canvas pixels. */
const PICTURE_INSET = 40;
const PICTURE_FADE = 90;

/**
 * The world's own map on the parchment: its middle cut to the sheet's shape,
 * toned toward sepia and laid on as though washed into the paper, its edges
 * fading out into the sheet.
 */
const drawPicture = (ctx: CanvasRenderingContext2D, picture: HTMLImageElement, cw: number, ch: number) => {
  const w = cw - PICTURE_INSET * 2;
  const h = ch - PICTURE_INSET * 2;
  const pw = picture.naturalWidth;
  const ph = picture.naturalHeight;
  let sw = pw;
  let sh = pw / (w / h);
  if (sh > ph) {
    sh = ph;
    sw = ph * (w / h);
  }

  const layer = document.createElement('canvas');
  layer.width = w;
  layer.height = h;
  const lctx = layer.getContext('2d');
  const mask = document.createElement('canvas');
  mask.width = w;
  mask.height = h;
  const mctx = mask.getContext('2d');
  if (!lctx || !mctx) throw new Error('2D canvas context unavailable');
  // Browsers without canvas filters lay it on in its own colours; the multiply below still ties it to the paper.
  lctx.filter = 'sepia(0.5) saturate(0.75) contrast(0.95) brightness(1.35)';
  lctx.drawImage(picture, (pw - sw) / 2, (ph - sh) / 2, sw, sh, 0, 0, w, h);
  lctx.filter = 'none';

  mctx.fillStyle = '#000';
  mctx.fillRect(0, 0, w, h);
  mctx.globalCompositeOperation = 'destination-out';
  const edges: [number, number, number, number][] = [
    [0, 0, PICTURE_FADE, 0],
    [w, 0, w - PICTURE_FADE, 0],
    [0, 0, 0, PICTURE_FADE],
    [0, h, 0, h - PICTURE_FADE],
  ];
  edges.forEach(([x0, y0, x1, y1]) => {
    const g = mctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, 'rgba(0,0,0,1)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    mctx.fillStyle = g;
    mctx.fillRect(0, 0, w, h);
  });
  lctx.globalCompositeOperation = 'destination-in';
  lctx.drawImage(mask, 0, 0);

  ctx.save();
  ctx.globalCompositeOperation = 'multiply';
  ctx.globalAlpha = 0.85;
  ctx.drawImage(layer, PICTURE_INSET, PICTURE_INSET);
  ctx.restore();
};

export const createWorldMapTexture = (
  width: number,
  depth: number,
  marks: MapMarks,
  /** The world's own map; without it the lands are drawn from the seed. */
  picture: HTMLImageElement | null = null,
  seed = 7,
) => {
  const scale = Math.min(PX_PER_UNIT, MAX_TEXTURE / width);
  const cw = Math.round(width * scale);
  const ch = Math.round(depth * scale);
  const toPx = ([x, z]: MapPoint) => [(x + width / 2) * scale, (z + depth / 2) * scale] as const;

  const canvas = document.createElement('canvas');
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  const rand = mulberry32(seed);
  const height = makeNoise(seed);
  const moisture = makeNoise(seed + 101);
  /** Features about 2.6 to the map's height. */
  const freq = 2.6 / ch;
  const elev = (px: number, py: number) => {
    let e = height(px * freq, py * freq);
    // The known lands thin out into open sea toward the map's edges.
    const edge = Math.min(px, cw - px, py, ch - py) / (ch * 0.2);
    if (edge < 1) e -= (1 - Math.max(0, edge)) ** 2 * 0.16;
    return e;
  };

  // Parchment: a warm sheet, mottled.
  ctx.fillStyle = PARCHMENT;
  ctx.fillRect(0, 0, cw, ch);
  for (let i = 0; i < 40; i++) {
    const x = rand() * cw;
    const y = rand() * ch;
    const r = 60 + rand() * 260;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    const dark = rand() < 0.6;
    g.addColorStop(0, dark ? 'rgba(120,80,35,0.1)' : 'rgba(255,240,205,0.12)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }

  if (picture) drawPicture(ctx, picture, cw, ch);
  else {
    // Elevation, sampled for the coasts and the land's tint.
    const gw = Math.ceil(cw / CELL) + 1;
    const gh = Math.ceil(ch / CELL) + 1;
    const field = new Float32Array(gw * gh);
    for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) field[j * gw + i] = elev(i * CELL, j * CELL);

    const mask = document.createElement('canvas');
    mask.width = gw;
    mask.height = gh;
    const mctx = mask.getContext('2d');
    if (!mctx) throw new Error('2D canvas context unavailable');
    const img = mctx.createImageData(gw, gh);
    for (let k = 0; k < field.length; k++) {
      const a = THREE.MathUtils.clamp((field[k] - SEA_LEVEL) / 0.012 + 0.5, 0, 1);
      img.data.set([120, 86, 46, Math.round(a * 255)], k * 4);
    }
    mctx.putImageData(img, 0, 0);
    const drawMask = (target: CanvasRenderingContext2D) =>
      target.drawImage(mask, -CELL / 2, -CELL / 2, gw * CELL, gh * CELL);

    // Rhumb lines from every rose, across the sea only.
    const rhumb = document.createElement('canvas');
    rhumb.width = cw;
    rhumb.height = ch;
    const rctx = rhumb.getContext('2d');
    if (!rctx) throw new Error('2D canvas context unavailable');
    rctx.lineWidth = 1.1;
    marks.roses.forEach((p) => {
      const [x, y] = toPx(p);
      for (let i = 0; i < 16; i++) {
        const a = (i / 16) * Math.PI * 2;
        rctx.strokeStyle = i % 2 === 0 ? FAINT : FADED_RED;
        rctx.beginPath();
        rctx.moveTo(x, y);
        rctx.lineTo(x + Math.cos(a) * cw, y + Math.sin(a) * cw);
        rctx.stroke();
      }
    });
    rctx.globalCompositeOperation = 'destination-out';
    drawMask(rctx);
    ctx.drawImage(rhumb, 0, 0);

    // The land, tinted; the coast traced, with ripples standing off it into the sea.
    ctx.save();
    ctx.globalAlpha = 0.28;
    drawMask(ctx);
    ctx.restore();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = FAINT;
    [0.022, 0.044, 0.07].forEach((d, i) => {
      ctx.globalAlpha = 0.8 - i * 0.22;
      ctx.lineWidth = 1.1;
      traceContour(ctx, field, gw, gh, SEA_LEVEL - d);
    });
    ctx.globalAlpha = 1;
    ctx.strokeStyle = INK;
    ctx.lineWidth = 2.6;
    traceContour(ctx, field, gw, gh, SEA_LEVEL);

    // Mountains on the heights, forests in the damp lowlands.
    const mountains: { x: number; y: number; s: number }[] = [];
    for (let y = 20; y < ch - 20; y += 40) {
      for (let x = 20; x < cw - 20; x += 40) {
        const px = x + (rand() - 0.5) * 22;
        const py = y + (rand() - 0.5) * 22;
        const e = elev(px, py);
        if (e > SEA_LEVEL + 0.13 && rand() < 0.6) mountains.push({ x: px, y: py, s: THREE.MathUtils.clamp(10 + (e - SEA_LEVEL - 0.12) * 160, 10, 22) });
      }
    }
    ctx.strokeStyle = INK;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let y = 12; y < ch - 12; y += 16) {
      for (let x = 12; x < cw - 12; x += 16) {
        const px = x + (rand() - 0.5) * 12;
        const py = y + (rand() - 0.5) * 12;
        const e = elev(px, py);
        if (e < SEA_LEVEL + 0.025 || e > SEA_LEVEL + 0.085 || moisture(px * freq * 1.5, py * freq * 1.5) < 0.53) continue;
        const r = 3.5 + rand() * 2.2;
        ctx.moveTo(px + r, py - r - 2);
        ctx.arc(px, py - r - 2, r, 0, Math.PI * 2);
        ctx.moveTo(px, py - 2);
        ctx.lineTo(px, py + 2);
      }
    }
    ctx.globalAlpha = 0.7;
    ctx.stroke();
    ctx.globalAlpha = 1;

    // Rivers run down from the heights to the sea.
    ctx.strokeStyle = INK;
    ctx.lineWidth = 1.7;
    const sources = [...mountains].sort(() => rand() - 0.5).slice(0, Math.round(cw / 300));
    sources.forEach((m) => {
      let x = m.x;
      let y = m.y + 3;
      let dx = 0;
      let dy = 1;
      const path: [number, number][] = [[x, y]];
      for (let step = 0; step < 400; step++) {
        if (elev(x, y) < SEA_LEVEL - 0.01 || x < 0 || y < 0 || x > cw || y > ch) break;
        const gx = elev(x + 4, y) - elev(x - 4, y);
        const gy = elev(x, y + 4) - elev(x, y - 4);
        const len = Math.hypot(gx, gy) || 1;
        dx = dx * 0.75 - (gx / len) * 0.25 + (rand() - 0.5) * 0.35;
        dy = dy * 0.75 - (gy / len) * 0.25 + (rand() - 0.5) * 0.35;
        const n = Math.hypot(dx, dy) || 1;
        dx /= n;
        dy /= n;
        x += dx * 6;
        y += dy * 6;
        path.push([x, y]);
      }
      if (path.length < 10) return;
      ctx.beginPath();
      path.forEach(([px, py], i) => (i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)));
      ctx.stroke();
    });

    mountains.sort((a, b) => a.y - b.y).forEach((m) => drawMountain(ctx, m.x, m.y, m.s, rand));

    // Wavelets out at sea.
    ctx.strokeStyle = FAINT;
    ctx.lineWidth = 1.2;
    for (let i = 0; i < cw / 40; i++) {
      const x = rand() * cw;
      const y = rand() * ch;
      if (elev(x, y) > SEA_LEVEL - 0.08) continue;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.quadraticCurveTo(x + 6, y - 6, x + 12, y);
      ctx.quadraticCurveTo(x + 18, y - 6, x + 24, y);
      ctx.stroke();
    }

    // Names of places, long since faded past reading.
    ctx.strokeStyle = INK;
    for (let i = 0; i < cw / 160; i++) {
      const x = 60 + rand() * (cw - 260);
      const y = 60 + rand() * (ch - 120);
      if (elev(x, y) < SEA_LEVEL + 0.03) continue;
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(0.5, 0.5);
      ctx.globalAlpha = 0.55 + rand() * 0.3;
      ctx.lineWidth = 2.4;
      scrawl(ctx, rand, 0, 120 + rand() * 160, 0);
      ctx.restore();
    }
  }

  marks.roses.forEach((p) => {
    const [x, y] = toPx(p);
    drawRose(ctx, x, y, 0.75 * scale);
  });

  // Border: two rules, the band between them marked off in degrees.
  ctx.strokeStyle = INK;
  ctx.fillStyle = INK;
  const outer = 22;
  const inner = 34;
  ctx.lineWidth = 3;
  ctx.strokeRect(outer, outer, cw - outer * 2, ch - outer * 2);
  ctx.lineWidth = 1.2;
  ctx.strokeRect(inner, inner, cw - inner * 2, ch - inner * 2);
  const step = 0.5 * scale;
  for (let x = inner, k = 0; x < cw - inner; x += step, k++) {
    if (k % 2) continue;
    const w = Math.min(step, cw - inner - x);
    ctx.fillRect(x, outer, w, inner - outer);
    ctx.fillRect(x, ch - inner, w, inner - outer);
  }
  for (let y = inner, k = 0; y < ch - inner; y += step, k++) {
    if (k % 2) continue;
    const h = Math.min(step, ch - inner - y);
    ctx.fillRect(outer, y, inner - outer, h);
    ctx.fillRect(cw - inner, y, inner - outer, h);
  }

  // What stands on it: ink and wax.
  marks.inkSpots.forEach((p) => {
    const [x, y] = toPx(p);
    drawInkSpot(ctx, x, y, scale, rand);
  });
  marks.waxSpots.forEach((p) => {
    const [x, y] = toPx(p);
    drawWaxSpot(ctx, x, y, scale, rand);
  });

  // Age: folds, stains, foxing, and edges darkened by hands.
  for (let k = 1; k < 6; k++) {
    const x = (cw * k) / 6;
    ctx.fillStyle = 'rgba(255,245,215,0.18)';
    ctx.fillRect(x - 2, 0, 3, ch);
    ctx.fillStyle = 'rgba(70,45,20,0.16)';
    ctx.fillRect(x + 1, 0, 1.5, ch);
  }
  ctx.fillStyle = 'rgba(255,245,215,0.18)';
  ctx.fillRect(0, ch / 2 - 2, cw, 3);
  ctx.fillStyle = 'rgba(70,45,20,0.16)';
  ctx.fillRect(0, ch / 2 + 1, cw, 1.5);
  for (let i = 0; i < cw / 200; i++) {
    const x = rand() * cw;
    const y = rand() * ch;
    const r = 30 + rand() * 90;
    const g = ctx.createRadialGradient(x, y, r * 0.6, x, y, r);
    g.addColorStop(0, 'rgba(140,95,40,0.05)');
    g.addColorStop(0.85, 'rgba(110,70,30,0.14)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = 'rgba(120,70,30,0.22)';
  for (let i = 0; i < cw / 6; i++) {
    ctx.beginPath();
    ctx.arc(rand() * cw, rand() * ch, 0.6 + rand() * 2.2, 0, Math.PI * 2);
    ctx.fill();
  }
  const edgeBand = 90;
  const edges: [number, number, number, number][] = [
    [0, 0, edgeBand, 0],
    [cw, 0, cw - edgeBand, 0],
    [0, 0, 0, edgeBand],
    [0, ch, 0, ch - edgeBand],
  ];
  edges.forEach(([x0, y0, x1, y1]) => {
    const g = ctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, 'rgba(70,40,15,0.45)');
    g.addColorStop(1, 'rgba(70,40,15,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, cw, ch);
  });

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
};

/** The back of the sheet, seen where its ends are rolled up. */
export const createMapBackTexture = () => {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  const rand = mulberry32(3);
  ctx.fillStyle = '#c4a878';
  ctx.fillRect(0, 0, 256, 256);
  // Turns of the roll, darker where the sheet wraps under itself.
  for (let y = 0; y < 256; y += 3) {
    ctx.fillStyle = `rgba(80,50,20,${0.04 + rand() * 0.08})`;
    ctx.fillRect(0, y, 256, 1 + rand() * 1.5);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
};
