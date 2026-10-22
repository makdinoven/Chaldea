import * as THREE from 'three';

/*
  Covers, page edges and pages, all drawn on canvas like the rest of the 3D
  scenes: nothing is sampled from the cross-origin bucket.
*/

export const mulberry32 = (seed: number) => () => {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const makeCanvas = (width: number, height: number) => {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  return { canvas, ctx };
};

const toTexture = (canvas: HTMLCanvasElement) => {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
};

/** What a class's book is bound in. */
export interface BookBinding {
  /** Leather, hex. */
  leather: string;
  /** Tooling and lettering on the cover, hex. */
  foil: string;
  /** Corner pieces and clasp, hex. */
  metal: string;
  /** Which emblem is tooled on the cover. */
  sigil: 'warrior' | 'rogue' | 'mage';
}

/* DB class ids: 1=Warrior, 2=Rogue, 3=Mage */
export const BINDINGS: Record<number, BookBinding> = {
  // Oxblood under tarnished brass lettering.
  1: { leather: '#5a1913', foil: '#a98552', metal: '#7d7f84', sigil: 'warrior' },
  // Pale, rubbed tan leather, the name pressed blind into it: nothing that glints.
  2: { leather: '#7f5c3c', foil: '#3a2516', metal: '#a7adb2', sigil: 'rogue' },
  // Midnight blue under old gold.
  3: { leather: '#15204a', foil: '#cfa96c', metal: '#c99a55', sigil: 'mage' },
};
export const DEFAULT_BINDING = BINDINGS[1];

/** Grain and wear on leather: tiny pores, creases and rubbed patches. */
const leatherGrain = (ctx: CanvasRenderingContext2D, w: number, h: number, rand: () => number) => {
  for (let i = 0; i < 9000; i++) {
    ctx.fillStyle = rand() > 0.5 ? `rgba(255,255,255,${0.012 + rand() * 0.03})` : `rgba(0,0,0,${0.05 + rand() * 0.1})`;
    ctx.fillRect(rand() * w, rand() * h, 1 + rand() * 2, 1 + rand() * 2);
  }
  for (let i = 0; i < 40; i++) {
    ctx.strokeStyle = `rgba(0,0,0,${0.08 + rand() * 0.12})`;
    ctx.lineWidth = 0.6 + rand() * 1.2;
    ctx.beginPath();
    const x = rand() * w;
    const y = rand() * h;
    ctx.moveTo(x, y);
    ctx.quadraticCurveTo(x + (rand() - 0.5) * 80, y + (rand() - 0.5) * 80, x + (rand() - 0.5) * 140, y + (rand() - 0.5) * 140);
    ctx.stroke();
  }
  // Edges rubbed lighter by handling
  const rub = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.3, w / 2, h / 2, Math.max(w, h) * 0.75);
  rub.addColorStop(0, 'rgba(0,0,0,0)');
  rub.addColorStop(1, 'rgba(255,230,200,0.08)');
  ctx.fillStyle = rub;
  ctx.fillRect(0, 0, w, h);
};

/**
 * Years of hard use: creases with a pale lip, patches rubbed pale, stains with
 * a darker rim, and edges darkened by hands and rubbed through at the very
 * rim. `amount` scales how much of it there is.
 */
const weatherLeather = (ctx: CanvasRenderingContext2D, w: number, h: number, rand: () => number, amount: number) => {
  ctx.save();
  ctx.lineCap = 'round';
  for (let i = 0; i < 12 * amount; i++) {
    let x = rand() * w;
    let y = rand() * h;
    const a = rand() * Math.PI;
    const steps = 4 + Math.floor(rand() * 5);
    const pts: [number, number][] = [[x, y]];
    for (let k = 0; k < steps; k++) {
      x += Math.cos(a) * 18 + (rand() - 0.5) * 14;
      y += Math.sin(a) * 18 + (rand() - 0.5) * 14;
      pts.push([x, y]);
    }
    for (const [dx, dy, colour, width] of [
      [0, 0, `rgba(0,0,0,${0.18 + rand() * 0.15})`, 2.2],
      [1.5, 1.5, `rgba(255,232,205,${0.06 + rand() * 0.06})`, 1.4],
    ] as const) {
      ctx.strokeStyle = colour;
      ctx.lineWidth = width;
      ctx.beginPath();
      pts.forEach(([px, py], k) => (k ? ctx.lineTo(px + dx, py + dy) : ctx.moveTo(px + dx, py + dy)));
      ctx.stroke();
    }
  }
  // Rubbed pale, mostly toward the edges where it is held.
  for (let i = 0; i < 60 * amount; i++) {
    const edge = rand() < 0.7;
    const x = edge ? (rand() < 0.5 ? rand() * 70 : w - rand() * 70) : rand() * w;
    const y = edge && rand() < 0.5 ? (rand() < 0.5 ? rand() * 70 : h - rand() * 70) : rand() * h;
    ctx.fillStyle = `rgba(255,225,190,${0.03 + rand() * 0.07})`;
    ctx.beginPath();
    ctx.ellipse(x, y, 4 + rand() * 22, 3 + rand() * 12, rand() * Math.PI, 0, Math.PI * 2);
    ctx.fill();
  }
  for (let i = 0; i < 5 * amount; i++) {
    const x = rand() * w;
    const y = rand() * h;
    const r = 25 + rand() * 70;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `rgba(15,8,4,${0.08 + rand() * 0.1})`);
    g.addColorStop(0.85, `rgba(15,8,4,${0.12 + rand() * 0.1})`);
    g.addColorStop(1, 'rgba(15,8,4,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  // Edges: darkened by hands, then rubbed through at the very rim.
  const band = 46;
  const edges: [number, number, number, number][] = [
    [0, 0, band, 0],
    [w, 0, w - band, 0],
    [0, 0, 0, band],
    [0, h, 0, h - band],
  ];
  edges.forEach(([x0, y0, x1, y1]) => {
    const g = ctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, 'rgba(255,225,190,0.14)');
    g.addColorStop(0.12, `rgba(10,5,2,${0.3 * Math.min(1, amount)})`);
    g.addColorStop(1, 'rgba(10,5,2,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  });
  ctx.restore();
};

/** A line pressed into the leather and filled with foil: dark bed, bright face. */
const tooled = (ctx: CanvasRenderingContext2D, foil: string, draw: () => void, width: number) => {
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.strokeStyle = 'rgba(0,0,0,0.6)';
  ctx.lineWidth = width + 3;
  ctx.translate(1.5, 2);
  draw();
  ctx.stroke();
  ctx.translate(-1.5, -2);
  ctx.strokeStyle = foil;
  ctx.lineWidth = width;
  draw();
  ctx.stroke();
  ctx.restore();
};

/** The emblem of each class, drawn as paths around (0,0) at unit size ~1. */
const SIGILS: Record<BookBinding['sigil'], (ctx: CanvasRenderingContext2D) => void> = {
  // A sword point-down over a round shield.
  warrior: (ctx) => {
    ctx.beginPath();
    ctx.arc(0, 0.05, 0.62, 0, Math.PI * 2);
    ctx.moveTo(0, -0.95);
    ctx.lineTo(0, 0.95);
    ctx.moveTo(-0.32, -0.55);
    ctx.lineTo(0.32, -0.55);
    ctx.moveTo(-0.09, 0.8);
    ctx.lineTo(0, 0.98);
    ctx.lineTo(0.09, 0.8);
  },
  // A dagger across a crescent moon.
  rogue: (ctx) => {
    ctx.beginPath();
    ctx.arc(0, 0, 0.72, Math.PI * 0.35, Math.PI * 1.65);
    ctx.arc(0.28, 0, 0.56, Math.PI * 1.55, Math.PI * 0.45, true);
    ctx.moveTo(-0.55, 0.75);
    ctx.lineTo(0.7, -0.8);
    ctx.moveTo(-0.62, 0.4);
    ctx.lineTo(-0.2, 0.75);
  },
  // An eight-pointed star in a ring, with an eye at its heart.
  mage: (ctx) => {
    ctx.beginPath();
    ctx.arc(0, 0, 0.82, 0, Math.PI * 2);
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2 - Math.PI / 2;
      const b = a + Math.PI / 8;
      const r = i % 2 === 0 ? 0.78 : 0.55;
      ctx.moveTo(Math.cos(a) * r, Math.sin(a) * r);
      ctx.lineTo(Math.cos(b) * 0.25, Math.sin(b) * 0.25);
    }
    ctx.moveTo(-0.24, 0);
    ctx.quadraticCurveTo(0, -0.16, 0.24, 0);
    ctx.quadraticCurveTo(0, 0.16, -0.24, 0);
  },
};

export const drawSigil = (ctx: CanvasRenderingContext2D, sigil: BookBinding['sigil'], cx: number, cy: number, size: number) => {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(size, size);
  SIGILS[sigil](ctx);
  ctx.restore();
};

const COVER_W = 768;
const COVER_H = 1024;

/** What each class's book is called on its cover. */
const COVER_TITLES: Record<BookBinding['sigil'], string> = {
  warrior: 'Warrior',
  rogue: 'Rogue',
  mage: 'Mage',
};

/**
 * The title in the leather, pressed and filled: a dark bed under its face, the
 * face worn away in specks where thumbs have rubbed it.
 */
const stampTitle = (ctx: CanvasRenderingContext2D, title: string, x: number, y: number, px: number, fill: string) => {
  const text = title.toUpperCase();
  ctx.font = `bold ${px}px serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.letterSpacing = `${Math.round(px * 0.12)}px`;
  ctx.fillStyle = 'rgba(0,0,0,0.55)';
  ctx.fillText(text, x + 2, y + 3);

  const face = document.createElement('canvas');
  face.width = ctx.canvas.width;
  face.height = ctx.canvas.height;
  const fctx = face.getContext('2d');
  if (!fctx) return;
  fctx.font = ctx.font;
  fctx.textAlign = 'center';
  fctx.textBaseline = 'middle';
  fctx.letterSpacing = ctx.letterSpacing;
  fctx.fillStyle = fill;
  fctx.fillText(text, x, y);
  fctx.globalCompositeOperation = 'destination-out';
  const rand = mulberry32(text.length * 97);
  const half = (fctx.measureText(text).width / 2) * 1.1;
  for (let i = 0; i < 160; i++) {
    fctx.fillStyle = `rgba(0,0,0,${0.35 + rand() * 0.6})`;
    fctx.beginPath();
    fctx.ellipse(x + (rand() - 0.5) * half * 2, y + (rand() - 0.5) * px, 1 + rand() * 4, 1 + rand() * 2.5, rand() * Math.PI, 0, Math.PI * 2);
    fctx.fill();
  }
  ctx.drawImage(face, 0, 0);
  ctx.letterSpacing = '0px';
};

/**
 * Warrior: leather stretched over heavy boards and beaten about — scuffs,
 * scorches and old cuts. No tooling to speak of; the ironwork on top is the
 * decoration, and the name is stamped low beneath the boss.
 */
const drawWarriorCover = (ctx: CanvasRenderingContext2D, w: number, h: number, binding: BookBinding, title: string) => {
  const rand = mulberry32(101);
  for (let i = 0; i < 14; i++) {
    const x = rand() * w;
    const y = rand() * h;
    const r = 30 + rand() * 90;
    const scorch = ctx.createRadialGradient(x, y, 0, x, y, r);
    scorch.addColorStop(0, `rgba(10,4,2,${0.25 + rand() * 0.25})`);
    scorch.addColorStop(1, 'rgba(10,4,2,0)');
    ctx.fillStyle = scorch;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  for (let i = 0; i < 26; i++) {
    const x = rand() * w;
    const y = rand() * h;
    const len = 30 + rand() * 120;
    const a = rand() * Math.PI;
    ctx.strokeStyle = 'rgba(0,0,0,0.5)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(255,200,170,0.12)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + 1, y + 2);
    ctx.lineTo(x + Math.cos(a) * len + 1, y + Math.sin(a) * len + 2);
    ctx.stroke();
  }
  // Low on the board, between the boss and the lower band, clear of the iron.
  stampTitle(ctx, title, w * 0.55, h * 0.665, 60, binding.foil);
};

/**
 * Rogue: soft leather, saddle-stitched round the edge, the emblem blind-pressed
 * rather than gilt. The fore-edge third is left plain — the wrap flap lies there.
 */
const drawRogueCover = (ctx: CanvasRenderingContext2D, w: number, h: number, binding: BookBinding, title: string) => {
  const stitch = (inset: number) => {
    ctx.setLineDash([16, 10]);
    ctx.lineCap = 'round';
    ctx.strokeStyle = 'rgba(0,0,0,0.3)';
    ctx.lineWidth = 6;
    ctx.strokeRect(inset + 1, inset + 2, w - inset * 2, h - inset * 2);
    ctx.strokeStyle = '#3d2919';
    ctx.lineWidth = 3.5;
    ctx.strokeRect(inset, inset, w - inset * 2, h - inset * 2);
    ctx.setLineDash([]);
  };
  stitch(26);
  stitch(48);
  const cx = w * 0.36;
  ctx.strokeStyle = 'rgba(0,0,0,0.55)';
  ctx.lineWidth = 7;
  ctx.lineCap = 'round';
  drawSigil(ctx, binding.sigil, cx, h * 0.38, 120);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 2;
  drawSigil(ctx, binding.sigil, cx - 1, h * 0.38 - 2, 120);
  ctx.stroke();
  // Below the dagger laid across the board.
  stampTitle(ctx, title, cx, h * 0.8, 58, binding.foil);
};

/**
 * Mage: fine leather tooled all over in gold — a double frame, flourishes in
 * the corners, a ring of small stars, the emblem at the centre where the
 * crystal is set, and the name below.
 */
const drawMageCover = (ctx: CanvasRenderingContext2D, w: number, h: number, binding: BookBinding, title: string) => {
  const frame = (inset: number) => () => {
    ctx.beginPath();
    ctx.rect(inset, inset, w - inset * 2, h - inset * 2);
  };
  tooled(ctx, binding.foil, frame(40), 3);
  tooled(ctx, binding.foil, frame(56), 1.5);
  for (const [x, y, sx, sy] of [
    [56, 56, 1, 1],
    [w - 56, 56, -1, 1],
    [56, h - 56, 1, -1],
    [w - 56, h - 56, -1, -1],
  ] as const) {
    tooled(
      ctx,
      binding.foil,
      () => {
        ctx.beginPath();
        ctx.moveTo(x + sx * 8, y + sy * 110);
        ctx.bezierCurveTo(x + sx * 8, y + sy * 40, x + sx * 40, y + sy * 8, x + sx * 110, y + sy * 8);
        ctx.moveTo(x + sx * 24, y + sy * 80);
        ctx.quadraticCurveTo(x + sx * 30, y + sy * 30, x + sx * 80, y + sy * 24);
        ctx.moveTo(x + sx * 40, y + sy * 40);
        ctx.arc(x + sx * 40, y + sy * 40, 7, 0, Math.PI * 2);
      },
      1.8,
    );
  }
  const cy = h * 0.44;
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2;
    const x = w / 2 + Math.cos(a) * 250;
    const y = cy + Math.sin(a) * 250;
    tooled(
      ctx,
      binding.foil,
      () => {
        ctx.beginPath();
        ctx.moveTo(x - 7, y);
        ctx.lineTo(x + 7, y);
        ctx.moveTo(x, y - 7);
        ctx.lineTo(x, y + 7);
      },
      i % 2 === 0 ? 2 : 1,
    );
  }
  tooled(ctx, binding.foil, () => drawSigil(ctx, binding.sigil, w / 2, cy, 190), 3.5);
  tooled(
    ctx,
    binding.foil,
    () => {
      ctx.beginPath();
      ctx.moveTo(w * 0.3, h * 0.77);
      ctx.lineTo(w * 0.7, h * 0.77);
    },
    1.5,
  );
  stampTitle(ctx, title, w / 2, h * 0.84, 66, binding.foil);
};

const COVER_STYLES: Record<BookBinding['sigil'], typeof drawMageCover> = {
  warrior: drawWarriorCover,
  rogue: drawRogueCover,
  mage: drawMageCover,
};

/** How hard each book has been used: the soldier's hardest, the mage's most cared for. */
const WEAR: Record<BookBinding['sigil'], number> = { warrior: 1.6, rogue: 1.3, mage: 0.8 };

/** The front cover, in the manner of its class. Canvas x runs spine -> fore-edge, top is the head. */
export const createCoverTexture = (binding: BookBinding, title: string) => {
  const w = COVER_W;
  const h = COVER_H;
  const rand = mulberry32(binding.sigil.length * 31 + 5);
  const { canvas, ctx } = makeCanvas(w, h);
  ctx.fillStyle = binding.leather;
  ctx.fillRect(0, 0, w, h);
  leatherGrain(ctx, w, h, rand);
  weatherLeather(ctx, w, h, rand, WEAR[binding.sigil]);
  COVER_STYLES[binding.sigil](ctx, w, h, binding, COVER_TITLES[binding.sigil] ?? title);
  return toTexture(canvas);
};

/** Elder Futhark, for the mage's seal. */
const GLYPHS = 'ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ';
/** The mage's seal: concentric rings with a band of runes, white for tinting. */
export const createSealTexture = () => {
  const size = 512;
  const c = size / 2;
  const { canvas, ctx } = makeCanvas(size, size);
  ctx.strokeStyle = '#ffffff';
  ctx.shadowColor = 'rgba(255,255,255,0.8)';
  ctx.shadowBlur = 10;
  for (const [r, lw] of [
    [c * 0.95, 4],
    [c * 0.8, 2],
    [c * 0.6, 3],
    [c * 0.3, 2],
  ] as const) {
    ctx.lineWidth = lw;
    ctx.beginPath();
    ctx.arc(c, c, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 34px serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const count = 18;
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2;
    ctx.save();
    ctx.translate(c + Math.cos(a) * c * 0.875, c + Math.sin(a) * c * 0.875);
    ctx.rotate(a + Math.PI / 2);
    ctx.fillText(GLYPHS[(i * 7) % GLYPHS.length], 0, 0);
    ctx.restore();
  }
  // A six-pointed star between the inner rings
  ctx.lineWidth = 2.5;
  for (let t = 0; t < 2; t++) {
    ctx.beginPath();
    for (let i = 0; i <= 3; i++) {
      const a = (i / 3) * Math.PI * 2 + (t * Math.PI) / 3 - Math.PI / 2;
      const x = c + Math.cos(a) * c * 0.58;
      const y = c + Math.sin(a) * c * 0.58;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  return toTexture(canvas);
};

/** Plain leather for the other faces of a cover. */
export const createLeatherTexture = (binding: BookBinding) => {
  const { canvas, ctx } = makeCanvas(256, 256);
  ctx.fillStyle = binding.leather;
  ctx.fillRect(0, 0, 256, 256);
  leatherGrain(ctx, 256, 256, mulberry32(77));
  weatherLeather(ctx, 256, 256, mulberry32(78), WEAR[binding.sigil] * 0.4);
  return toTexture(canvas);
};

/** The block of pages seen edge-on: fine cream lines, darker toward the covers. */
export const createPageEdgeTexture = (sigil: BookBinding['sigil']) => {
  const { canvas, ctx } = makeCanvas(64, 256);
  const rand = mulberry32(13);
  ctx.fillStyle = STOCKS[sigil].edgeColour;
  ctx.fillRect(0, 0, 64, 256);
  for (let y = 0; y < 256; y += 2) {
    ctx.fillStyle = `rgba(90,60,25,${0.08 + rand() * 0.18})`;
    ctx.fillRect(0, y, 64, 1);
  }
  const age = ctx.createLinearGradient(0, 0, 0, 256);
  age.addColorStop(0, 'rgba(70,45,15,0.35)');
  age.addColorStop(0.5, 'rgba(70,45,15,0)');
  age.addColorStop(1, 'rgba(70,45,15,0.35)');
  ctx.fillStyle = age;
  ctx.fillRect(0, 0, 64, 256);
  // Soot on the warrior's, spills on the rogue's.
  if (sigil === 'warrior') {
    for (let i = 0; i < 10; i++) {
      ctx.fillStyle = `rgba(30,16,6,${0.1 + rand() * 0.15})`;
      ctx.fillRect(rand() * 64, rand() * 256, 8 + rand() * 24, 10 + rand() * 40);
    }
  }
  if (sigil === 'rogue') {
    for (let i = 0; i < 6; i++) {
      ctx.fillStyle = rand() > 0.5 ? 'rgba(100,25,18,0.25)' : 'rgba(100,120,35,0.18)';
      ctx.beginPath();
      ctx.arc(rand() * 64, rand() * 256, 4 + rand() * 10, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  return toTexture(canvas);
};

const PAGE_W = 768;
const PAGE_H = 1024;

/** Aged paper: warm, foxed, darker at the edges and in the gutter. */
/** What a class's pages are made of and written in. */
export interface PaperStock {
  /** Middle of the page, and its darker edges. */
  centre: string;
  edge: string;
  /** Foxing and age spots, as an rgb triple. */
  foxing: string;
  /** Shadow in the gutter, as an rgb triple. */
  gutter: string;
  /** Text and drawing. */
  ink: string;
  /** Lighter ink, for asides. */
  faintInk: string;
  /** What gives the sheet its character. */
  texture: 'fibres' | 'creases' | 'watermark';
  /** Colour of the paper edges seen on the block. */
  edgeColour: string;
}

export const STOCKS: Record<BookBinding['sigil'], PaperStock> = {
  // Thick, coarse, tanned parchment, browned by smoke and handling.
  warrior: {
    centre: '#d2b98c',
    edge: '#8d6c42',
    foxing: '90,55,20',
    gutter: '55,30,8',
    ink: 'rgba(52,26,10,0.92)',
    faintInk: 'rgba(52,26,10,0.5)',
    texture: 'fibres',
    edgeColour: '#bfa47a',
  },
  // Cheap grey-green paper, thin and much folded, written in faded ink.
  rogue: {
    centre: '#d4d0b8',
    edge: '#8c8a70',
    foxing: '80,85,55',
    gutter: '35,38,25',
    ink: 'rgba(38,40,34,0.85)',
    faintInk: 'rgba(38,40,34,0.45)',
    texture: 'creases',
    edgeColour: '#c4c0a6',
  },
  // Fine pale vellum, barely aged, with a watermark in the sheet; indigo ink.
  mage: {
    centre: '#f1e9d6',
    edge: '#cbbd98',
    foxing: '150,130,90',
    gutter: '60,55,80',
    ink: 'rgba(30,32,78,0.9)',
    faintInk: 'rgba(30,32,78,0.45)',
    texture: 'watermark',
    edgeColour: '#e8dcc0',
  },
};

/** Long fibres caught in coarse parchment. */
const fibres = (ctx: CanvasRenderingContext2D, w: number, h: number, rand: () => number) => {
  for (let i = 0; i < 260; i++) {
    const x = rand() * w;
    const y = rand() * h;
    const len = 8 + rand() * 30;
    const a = rand() * Math.PI;
    ctx.strokeStyle = rand() > 0.5 ? 'rgba(90,60,25,0.16)' : 'rgba(255,240,210,0.12)';
    ctx.lineWidth = 0.8 + rand();
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.quadraticCurveTo(x + Math.cos(a) * len * 0.5 + (rand() - 0.5) * 6, y + Math.sin(a) * len * 0.5, x + Math.cos(a) * len, y + Math.sin(a) * len);
    ctx.stroke();
  }
};

/** Fold lines of a sheet that has been folded small and opened again. */
const creases = (ctx: CanvasRenderingContext2D, w: number, h: number, rand: () => number) => {
  const fold = (x0: number, y0: number, x1: number, y1: number) => {
    ctx.strokeStyle = 'rgba(40,40,25,0.16)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(255,255,240,0.18)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x0 + 2, y0 + 2);
    ctx.lineTo(x1 + 2, y1 + 2);
    ctx.stroke();
  };
  fold(0, h * (0.32 + rand() * 0.04), w, h * (0.33 + rand() * 0.04));
  fold(0, h * (0.66 + rand() * 0.04), w, h * (0.65 + rand() * 0.04));
  fold(w * (0.5 + (rand() - 0.5) * 0.04), 0, w * (0.5 + (rand() - 0.5) * 0.04), h);
};

/** A faint star-and-circle watermark, seen in the sheet rather than on it. */
const watermark = (ctx: CanvasRenderingContext2D, w: number, h: number) => {
  const cx = w / 2;
  const cy = h * 0.55;
  ctx.strokeStyle = 'rgba(255,255,255,0.1)';
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.arc(cx, cy, 170, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  for (let i = 0; i <= 10; i++) {
    const a = (i / 10) * Math.PI * 2 - Math.PI / 2;
    const r = i % 2 === 0 ? 150 : 62;
    const x = cx + Math.cos(a) * r;
    const y = cy + Math.sin(a) * r;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  // Chain lines of laid paper
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 2;
  for (let x = 40; x < w; x += 64) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
};

/** A sheet of the class's paper: its tone, its age, its texture, and the shadow of the gutter. */
export const paper = (ctx: CanvasRenderingContext2D, w: number, h: number, gutter: 'left' | 'right', seed: number, stock: PaperStock) => {
  const rand = mulberry32(seed);
  const base = ctx.createRadialGradient(w / 2, h / 2, 40, w / 2, h / 2, w * 0.85);
  base.addColorStop(0, stock.centre);
  base.addColorStop(1, stock.edge);
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, w, h);
  if (stock.texture === 'fibres') fibres(ctx, w, h, rand);
  if (stock.texture === 'creases') creases(ctx, w, h, rand);
  if (stock.texture === 'watermark') watermark(ctx, w, h);
  for (let i = 0; i < 60; i++) {
    const r = 4 + rand() * 26;
    const x = rand() * w;
    const y = rand() * h;
    const fox = ctx.createRadialGradient(x, y, 0, x, y, r);
    fox.addColorStop(0, `rgba(${stock.foxing},${0.04 + rand() * 0.08})`);
    fox.addColorStop(1, `rgba(${stock.foxing},0)`);
    ctx.fillStyle = fox;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  // Shadow where the page curves into the binding
  const gx = gutter === 'left' ? 0 : w;
  const shade = ctx.createLinearGradient(gx, 0, gutter === 'left' ? 120 : w - 120, 0);
  shade.addColorStop(0, `rgba(${stock.gutter},0.45)`);
  shade.addColorStop(1, `rgba(${stock.gutter},0)`);
  ctx.fillStyle = shade;
  ctx.fillRect(0, 0, w, h);
};


/** A ragged closed outline round a centre, for burns and stains. */
const raggedBlob = (ctx: CanvasRenderingContext2D, x: number, y: number, r: number, rand: () => number, jag = 0.35) => {
  const points = 28;
  ctx.beginPath();
  for (let i = 0; i <= points; i++) {
    const a = (i / points) * Math.PI * 2;
    const rr = r * (1 - jag / 2 + rand() * jag);
    const px = x + Math.cos(a) * rr;
    const py = y + Math.sin(a) * rr;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
};

/**
 * Warrior: the outer corners charred where the book has been near a fire — a
 * black burnt edge, a brown scorch round it and a last thin line of ember.
 */
const burnCorners = (ctx: CanvasRenderingContext2D, w: number, h: number, gutter: 'left' | 'right', rand: () => number) => {
  const outerX = gutter === 'left' ? w : 0;
  for (const y of [0, h]) {
    const r = 60 + rand() * 35;
    // A wide brown scorch fading into the paper...
    const scorch = ctx.createRadialGradient(outerX, y, r * 0.5, outerX, y, r * 2.1);
    scorch.addColorStop(0, 'rgba(90,48,16,0.38)');
    scorch.addColorStop(0.5, 'rgba(110,62,22,0.14)');
    scorch.addColorStop(1, 'rgba(110,62,22,0)');
    ctx.fillStyle = scorch;
    ctx.fillRect(0, 0, w, h);
    // ...the charred paper itself, a wavering edge built up from overlapping
    // burns rather than one hard cut...
    for (let i = 0; i < 6; i++) {
      const a = (i / 5) * (Math.PI / 2);
      const d = r * (0.35 + rand() * 0.45);
      const bx = outerX + Math.cos(a) * d * (outerX === 0 ? 1 : -1) * 0.9;
      const by = y + Math.sin(a) * d * (y === 0 ? 1 : -1) * 0.9;
      const br = r * (0.35 + rand() * 0.3);
      const burn = ctx.createRadialGradient(bx, by, 0, bx, by, br);
      burn.addColorStop(0, 'rgba(40,20,8,0.55)');
      burn.addColorStop(0.6, 'rgba(50,26,10,0.35)');
      burn.addColorStop(1, 'rgba(40,20,8,0)');
      ctx.fillStyle = burn;
      ctx.fillRect(bx - br, by - br, br * 2, br * 2);
    }
    const core = ctx.createRadialGradient(outerX, y, 0, outerX, y, r * 0.75);
    core.addColorStop(0, 'rgba(22,11,5,0.75)');
    core.addColorStop(1, 'rgba(10,6,3,0)');
    ctx.fillStyle = core;
    ctx.fillRect(0, 0, w, h);
    // ...and a last broken line of ember along it.
    ctx.strokeStyle = 'rgba(200,100,30,0.18)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i <= 24; i++) {
      const a = (i / 24) * (Math.PI / 2);
      const rr = r * (0.82 + rand() * 0.22);
      const px = outerX + Math.cos(a) * rr * (outerX === 0 ? 1 : -1);
      const py = y + Math.sin(a) * rr * (y === 0 ? 1 : -1);
      if (i === 0 || rand() < 0.2) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
  }
  // Soot smudges along the fore-edge
  for (let i = 0; i < 4; i++) {
    const y = rand() * h;
    const r = 20 + rand() * 40;
    const smudge = ctx.createRadialGradient(outerX, y, 0, outerX, y, r);
    smudge.addColorStop(0, 'rgba(40,22,8,0.18)');
    smudge.addColorStop(1, 'rgba(25,12,4,0)');
    ctx.fillStyle = smudge;
    ctx.fillRect(outerX - r, y - r, r * 2, r * 2);
  }
};

/** A spatter of blood: a main drop and its satellites, dried dark. */
const bloodSpatter = (ctx: CanvasRenderingContext2D, x: number, y: number, size: number, rand: () => number) => {
  raggedBlob(ctx, x, y, size, rand, 0.3);
  ctx.fillStyle = 'rgba(110,30,20,0.32)';
  ctx.fill();
  raggedBlob(ctx, x, y, size * 0.6, rand, 0.3);
  ctx.fillStyle = 'rgba(80,20,14,0.2)';
  ctx.fill();
  const a = rand() * Math.PI * 2;
  for (let i = 0; i < 5; i++) {
    const d = size * (1.3 + rand() * 2.2);
    const spread = a + (rand() - 0.5) * 1.4;
    ctx.beginPath();
    ctx.arc(x + Math.cos(spread) * d, y + Math.sin(spread) * d, 2 + rand() * size * 0.2, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(105,28,18,0.3)';
    ctx.fill();
  }
};

/** A poison stain: a sickly green-yellow tide mark with a darker rim where it dried. */
const poisonStain = (ctx: CanvasRenderingContext2D, x: number, y: number, size: number, rand: () => number) => {
  raggedBlob(ctx, x, y, size, rand, 0.45);
  const fill = ctx.createRadialGradient(x, y, 0, x, y, size);
  fill.addColorStop(0, 'rgba(110,130,40,0.06)');
  fill.addColorStop(0.75, 'rgba(95,115,35,0.12)');
  fill.addColorStop(1, 'rgba(70,85,25,0.22)');
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = 'rgba(70,80,25,0.22)';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // Runs where it dripped down the page
  for (let i = 0; i < 2; i++) {
    const dx = x + (rand() - 0.5) * size;
    const len = size * (0.6 + rand());
    const run = ctx.createLinearGradient(dx, y, dx, y + size + len);
    run.addColorStop(0, 'rgba(90,110,30,0.12)');
    run.addColorStop(1, 'rgba(90,110,30,0)');
    ctx.fillStyle = run;
    ctx.fillRect(dx - 1.5, y, 3, size + len);
  }
};

/** Rogue: dried blood and the stains of something poisonous spilled across the page. */
const stainPage = (ctx: CanvasRenderingContext2D, w: number, h: number, rand: () => number) => {
  poisonStain(ctx, w * (0.15 + rand() * 0.7), h * (0.2 + rand() * 0.7), 45 + rand() * 40, rand);
  for (let i = 0; i < 2; i++) bloodSpatter(ctx, w * (0.1 + rand() * 0.8), h * (0.1 + rand() * 0.8), 6 + rand() * 8, rand);
  // A bloody thumbprint near the fore-edge, where the page was turned
  const tx = w * (0.75 + rand() * 0.15);
  const ty = h * (0.75 + rand() * 0.15);
  ctx.strokeStyle = 'rgba(110,35,25,0.14)';
  ctx.lineWidth = 1.5;
  for (let r = 6; r < 34; r += 5) {
    ctx.beginPath();
    ctx.ellipse(tx, ty, r, r * 1.3, 0.4, 0, Math.PI * 2);
    ctx.stroke();
  }
};

/** Leaves each class's mark on a page: burns for the warrior, blood and poison for the rogue. */
export const weatherPage = (
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  sigil: BookBinding['sigil'],
  gutter: 'left' | 'right',
  seed: number,
) => {
  const rand = mulberry32(seed);
  if (sigil === 'warrior') burnCorners(ctx, w, h, gutter, rand);
  if (sigil === 'rogue') stainPage(ctx, w, h, rand);
};


/** A thin inked rule with a diamond at its middle. */
const ornamentRule = (ctx: CanvasRenderingContext2D, cx: number, y: number, half: number, ink: string) => {
  ctx.strokeStyle = ink;
  ctx.fillStyle = ink;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(cx - half, y);
  ctx.lineTo(cx - 14, y);
  ctx.moveTo(cx + 14, y);
  ctx.lineTo(cx + half, y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(cx, y - 9);
  ctx.lineTo(cx + 9, y);
  ctx.lineTo(cx, y + 9);
  ctx.lineTo(cx - 9, y);
  ctx.closePath();
  ctx.fill();
};

/**
 * The opening spread, until the tree is drawn into it: a title page on the
 * left with the class emblem, and on the right the heading of the chapter the
 * tree will fill.
 */
export const createTitlePageTexture = (binding: BookBinding, title: string) => {
  const w = PAGE_W;
  const h = PAGE_H;
  const { canvas, ctx } = makeCanvas(w, h);
  const stock = STOCKS[binding.sigil];
  paper(ctx, w, h, 'right', 21, stock);
  weatherPage(ctx, w, h, binding.sigil, 'right', 21);

  // The path is built under drawSigil's scale but stroked after it, in page pixels.
  ctx.strokeStyle = stock.ink;
  ctx.lineWidth = 5;
  ctx.lineCap = 'round';
  drawSigil(ctx, binding.sigil, w / 2, h * 0.36, 150);
  ctx.stroke();

  ornamentRule(ctx, w / 2, h * 0.58, 200, stock.ink);
  ctx.fillStyle = stock.ink;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = 'bold 64px serif';
  ctx.fillText(`Книга: ${title}`, w / 2, h * 0.66);
  ornamentRule(ctx, w / 2, h * 0.74, 200, stock.ink);
  return toTexture(canvas);
};

export const createChapterPageTexture = (binding: BookBinding) => {
  const w = PAGE_W;
  const h = PAGE_H;
  const { canvas, ctx } = makeCanvas(w, h);
  const stock = STOCKS[binding.sigil];
  paper(ctx, w, h, 'left', 34, stock);
  weatherPage(ctx, w, h, binding.sigil, 'left', 34);
  ctx.fillStyle = stock.ink;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = 'bold 54px serif';
  ctx.fillText('Древо пути', w / 2, h * 0.14);
  ornamentRule(ctx, w / 2, h * 0.2, 160, stock.ink);
  ctx.font = 'italic 34px serif';
  ctx.fillStyle = stock.faintInk;
  ctx.fillText('Страницы ещё ждут чернил…', w / 2, h * 0.5);
  return toTexture(canvas);
};

/** Ratio of a page's height to its width, matching the page textures. */
export const PAGE_ASPECT = PAGE_H / PAGE_W;
