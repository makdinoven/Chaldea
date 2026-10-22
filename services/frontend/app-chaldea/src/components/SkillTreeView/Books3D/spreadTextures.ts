import * as THREE from 'three';
import { STOCKS, drawSigil, mulberry32, paper, weatherPage, type BookBinding, type PaperStock } from './bookTextures';
import type { SpreadEdge, SpreadModel, SpreadNode } from './spreadLayout';

/*
  The tree inked onto the right-hand page of an open book. Drawn in spread
  coordinates (see spreadLayout) on a sheet as wide as both pages, then the
  right half is laid onto that page's own paper.

  How each part reads:
  - the path walked is laid in the class's own colour: branches and filled
    medallions in the warrior's crimson, the rogue's green, the mage's blue;
  - what can be taken now is inked firmly and ringed in the class's colour;
  - what is still ahead is a pale pencil sketch;
  - what the player closed off is smudged ink, struck through;
  - another class's book is plain ink throughout.
*/

/** One page, in canvas pixels. The page is 4:3 tall, as the book is. */
export const PAGE_W = 1024;
export const PAGE_H = 1365;
const SPREAD_W = PAGE_W * 2;

/** Medallion radii, in canvas pixels. */
const NODE_R = 38;
const LARGE_R = 47;

const PENCIL = 'rgba(70,70,70,0.55)';

/* DB class ids: 1=Warrior, 2=Rogue, 3=Mage — matching the class colours elsewhere */
export const CLASS_INK: Record<number, string> = {
  1: '#b3261e',
  2: '#1f7a50',
  3: '#2557a8',
};

/** The colours a walked path is laid in: the shadow and body of a filled medallion, its lit side, and the sheen round it. */
export interface PathInk {
  dark: string;
  mid: string;
  light: string;
  glow: string;
  /** The rune on a filled medallion, pale enough to read on it. */
  rune: string;
}

/** Each class lays its path in its own colour. */
export const CLASS_PATH: Record<number, PathInk> = {
  1: { dark: '#6e120d', mid: '#b3261e', light: '#e2705f', glow: 'rgba(214,72,52,0.75)', rune: '#fff1e6' },
  2: { dark: '#0d4a30', mid: '#1f7a50', light: '#62c08c', glow: 'rgba(72,186,122,0.7)', rune: '#effff4' },
  3: { dark: '#142f69', mid: '#2557a8', light: '#719de2', glow: 'rgba(92,142,238,0.75)', rune: '#eef4ff' },
};
/** Gold, for a class without a colour of its own. */
const GILT_PATH: PathInk = { dark: '#8a6508', mid: '#b8860b', light: '#e8c060', glow: 'rgba(232,192,96,0.8)', rune: '#3b2a0c' };
export const pathInk = (classId: number) => CLASS_PATH[classId] ?? GILT_PATH;
/** The path colours of whichever class writes in this ink. */
export const pathInkFor = (classInk: string) =>
  pathInk(Number(Object.keys(CLASS_INK).find((id) => CLASS_INK[Number(id)] === classInk)));

/** Elder Futhark, one per node, so every medallion carries a mark. */
const RUNES = 'ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ';

const px = (u: number) => ((u + 1) / 2) * SPREAD_W;
const py = (v: number) => (1 - v) * PAGE_H;

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

/** Radius of a node's medallion, in canvas pixels. */
export const nodeRadiusPx = (node: SpreadNode) => (node.large ? LARGE_R : NODE_R);
/** The spread's size in canvas pixels per unit of u and of v, for hit-testing. */
export const SPREAD_PX = { u: SPREAD_W / 2, v: PAGE_H } as const;

/** The curve of a branch: leaving its lower node upward and arriving at the upper one from below. */
/** How far short of a medallion's centre a branch stops: its rim, plus the outer ring an available node carries. */
const reach = (n: SpreadNode) => nodeRadiusPx(n) + (n.state === 'available' ? 10 : 3);

/**
 * The curve of a branch: leaving the top of its lower medallion and arriving
 * at the bottom of the upper one, never crossing into either — inside an
 * open pencil ring the line would show through.
 */
const branchPath = (ctx: CanvasRenderingContext2D, e: SpreadEdge) => {
  const x0 = px(e.from.u);
  const y0 = py(e.from.v) - reach(e.from);
  const x1 = px(e.to.u);
  const y1 = py(e.to.v) + reach(e.to);
  const lift = (y0 - y1) * 0.55;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.bezierCurveTo(x0, y0 - lift, x1, y1 + lift, x1, y1);
};

const drawBranch = (ctx: CanvasRenderingContext2D, e: SpreadEdge, stock: PaperStock, path: PathInk) => {
  ctx.save();
  ctx.lineCap = 'round';
  switch (e.kind) {
    case 'walked':
      ctx.shadowColor = path.glow;
      ctx.shadowBlur = 14;
      ctx.strokeStyle = path.mid;
      ctx.lineWidth = 9;
      branchPath(ctx, e);
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = path.light;
      ctx.lineWidth = 3;
      branchPath(ctx, e);
      ctx.stroke();
      break;
    case 'open':
    case 'plain':
      ctx.strokeStyle = stock.ink;
      ctx.lineWidth = e.kind === 'open' ? 5 : 3.5;
      branchPath(ctx, e);
      ctx.stroke();
      break;
    case 'locked':
      // Pencil: a light line drawn twice, a hair apart, as a sketch is.
      ctx.strokeStyle = PENCIL;
      ctx.lineWidth = 2;
      branchPath(ctx, e);
      ctx.stroke();
      ctx.translate(1.5, -1);
      ctx.lineWidth = 1;
      branchPath(ctx, e);
      ctx.stroke();
      break;
    case 'dead':
      ctx.strokeStyle = stock.faintInk;
      ctx.shadowColor = stock.faintInk;
      ctx.shadowBlur = 10;
      ctx.lineWidth = 4;
      branchPath(ctx, e);
      ctx.stroke();
      break;
  }
  ctx.restore();
};

const circle = (ctx: CanvasRenderingContext2D, x: number, y: number, r: number) => {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
};

const drawNode = (
  ctx: CanvasRenderingContext2D,
  n: SpreadNode,
  stock: PaperStock,
  classInk: string,
  path: PathInk,
  foreign: boolean,
  labelRow: 0 | 1 = 0,
) => {
  const at = { x: px(n.u), y: py(n.v) };
  const { x, y } = at;
  const r = nodeRadiusPx(n);
  const rune = RUNES[n.id % RUNES.length];
  const runePx = Math.round(r * 0.95);
  ctx.save();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = `bold ${runePx}px serif`;

  const state = foreign ? 'plain' : n.state;
  switch (state) {
    case 'chosen': {
      ctx.shadowColor = path.glow;
      ctx.shadowBlur = 22;
      const fill = ctx.createRadialGradient(x - r * 0.3, y - r * 0.3, 2, x, y, r);
      fill.addColorStop(0, path.light);
      fill.addColorStop(0.55, path.mid);
      fill.addColorStop(1, path.dark);
      ctx.fillStyle = fill;
      circle(ctx, x, y, r);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = stock.ink;
      ctx.lineWidth = 4;
      ctx.stroke();
      circle(ctx, x, y, r * 0.78);
      ctx.strokeStyle = path.rune;
      ctx.globalAlpha = 0.55;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = path.rune;
      ctx.fillText(rune, x, y + 2);
      break;
    }
    case 'available': {
      circle(ctx, x, y, r);
      ctx.fillStyle = 'rgba(255,250,235,0.55)';
      ctx.fill();
      ctx.strokeStyle = stock.ink;
      ctx.lineWidth = 4.5;
      ctx.stroke();
      circle(ctx, x, y, r + 7);
      ctx.strokeStyle = classInk;
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.fillStyle = classInk;
      ctx.fillText(rune, x, y + 2);
      break;
    }
    case 'locked': {
      ctx.strokeStyle = PENCIL;
      ctx.lineWidth = 2;
      circle(ctx, x, y, r);
      ctx.stroke();
      circle(ctx, x + 1.5, y - 1, r - 1);
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = PENCIL;
      ctx.fillText(rune, x, y + 2);
      break;
    }
    case 'blocked':
    case 'unreachable': {
      // Ink that ran: a blurred, faded medallion, then struck through.
      ctx.shadowColor = stock.faintInk;
      ctx.shadowBlur = 14;
      circle(ctx, x, y, r);
      ctx.fillStyle = 'rgba(80,70,60,0.12)';
      ctx.fill();
      ctx.strokeStyle = stock.faintInk;
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.fillStyle = stock.faintInk;
      ctx.fillText(rune, x, y + 2);
      ctx.shadowBlur = 0;
      ctx.strokeStyle = stock.ink;
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(x - r * 0.85, y - r * 0.85);
      ctx.lineTo(x + r * 0.85, y + r * 0.85);
      ctx.moveTo(x + r * 0.85, y - r * 0.85);
      ctx.lineTo(x - r * 0.85, y + r * 0.85);
      ctx.stroke();
      break;
    }
    default: {
      // Another class's book: plain ink.
      circle(ctx, x, y, r);
      ctx.fillStyle = 'rgba(255,250,235,0.3)';
      ctx.fill();
      ctx.strokeStyle = stock.ink;
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.fillStyle = stock.ink;
      ctx.fillText(rune, x, y + 2);
    }
  }

  if (n.large) {
    // Subclass picks: a second ring, and the name lettered above.
    circle(ctx, x, y, r - 9);
    ctx.strokeStyle = state === 'locked' ? PENCIL : stock.ink;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.font = 'bold 24px serif';
    ctx.fillStyle = state === 'chosen' ? path.mid : state === 'locked' ? PENCIL : stock.ink;
    // Neighbours sit closer than their names are long, so the names take turns
    // on two rows.
    ctx.fillText(n.node.name.toUpperCase(), x, y - r - (labelRow === 0 ? 18 : 46));
  }
  ctx.restore();
};

/** The level of each row, lettered small in both outer margins. */
const drawLevelMarks = (ctx: CanvasRenderingContext2D, model: SpreadModel, stock: PaperStock) => {
  ctx.save();
  ctx.font = 'italic 24px serif';
  ctx.fillStyle = stock.faintInk;
  ctx.textBaseline = 'middle';
  for (const { level, v } of model.levels) {
    const y = py(v);
    ctx.textAlign = 'right';
    ctx.fillText(`${level} ур.`, SPREAD_W - 30, y);
  }
  ctx.restore();
};

const drawHeadings = (ctx: CanvasRenderingContext2D, title: string, stock: PaperStock) => {
  ctx.save();
  ctx.fillStyle = stock.ink;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = 'bold 40px serif';
  ctx.fillText(`Древо пути: ${title}`, PAGE_W * 1.5, 64);
  ctx.strokeStyle = stock.ink;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(PAGE_W * 1.5 - 170, 100);
  ctx.lineTo(PAGE_W * 1.5 + 170, 100);
  ctx.stroke();
  ctx.restore();
};

/**
 * The opening words of each class's book, set on its left-hand page until a
 * node is opened there. Setting-neutral: no world names, only what every
 * Скиталец knows — the УР scale and the Цитадель.
 */
const INTROS: Record<BookBinding['sigil'], string[]> = {
  warrior: [
    'Эта книга — неотъемлемая часть пути каждого воителя. Её страницы не пишут пером: их выбивают сталью, а чернилами служат пот и кровь.',
    'С каждым новым УР в ней проступает строка, но какой она станет, решаешь лишь ты. Выбранная тропа ведёт дальше; отвергнутая сгорает навсегда.',
  ],
  rogue: [
    'Такую книгу не найти в библиотеках Цитадели — её передают из рук в руки, тихо и без лишних вопросов.',
    'Здесь записаны тропы тех, кто побеждает раньше, чем противник поймёт, что бой начался. Читай внимательно: выбрав одну дорогу, другую уже не вернёшь.',
  ],
  mage: [
    'Эта книга помнит больше, чем написано на её страницах. Каждый, кто открывает её, оставляет в ней свой след — и каждый след меняет книгу.',
    'С ростом УР её узор становится сложнее, а выбор — необратимее. Не спеши: слово, однажды вписанное в древо, назад не стереть.',
  ],
};

/** Breaks text into lines no wider than maxWidth at the current font. */
const wrapLines = (ctx: CanvasRenderingContext2D, text: string, maxWidth: number) => {
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
};

/** A specimen of each way a node can be written, for the key at the foot of the intro. */
const LEGEND: { state: SpreadNode['state']; label: string }[] = [
  { state: 'chosen', label: 'Пройденный путь' },
  { state: 'available', label: 'Можно выбрать сейчас' },
  { state: 'locked', label: 'Откроется с ростом УР' },
  { state: 'blocked', label: 'Путь закрыт выбором' },
];

/** The bare left-hand page — its paper and the marks of use — that its writing is laid over. */
export const createLeftPaperCanvas = (binding: BookBinding) => {
  const stock = STOCKS[binding.sigil];
  const { canvas, ctx } = makeCanvas(PAGE_W, PAGE_H);
  paper(ctx, PAGE_W, PAGE_H, 'right', 21, stock);
  weatherPage(ctx, PAGE_W, PAGE_H, binding.sigil, 'right', 21);
  return canvas;
};

/** Where a chapter's way back is written on its first page, and the patch of paper that answers to it. */
const INTRO_BACK_AT = { x: 100, y: 100 } as const;
export const INTRO_BACK_REGION = { x: 80, y: 55, w: 360, h: 70 } as const;

/** The bare right-hand page — its paper and the marks of use — that its writing is laid over. */
export const createRightPaperCanvas = (binding: BookBinding) => {
  const stock = STOCKS[binding.sigil];
  const { canvas, ctx } = makeCanvas(PAGE_W, PAGE_H);
  paper(ctx, PAGE_W, PAGE_H, 'left', 34, stock);
  weatherPage(ctx, PAGE_W, PAGE_H, binding.sigil, 'left', 34);
  return canvas;
};

/** A run of cramped cursive that never quite resolves into letters, along a line from x0 to x1. */
export const scrawl = (ctx: CanvasRenderingContext2D, rand: () => number, x0: number, x1: number, y: number) => {
  let x = x0;
  ctx.beginPath();
  while (x < x1) {
    const end = Math.min(x1, x + 40 + rand() * 110);
    ctx.moveTo(x, y);
    let up = true;
    while (x < end) {
      const step = 5 + rand() * 7;
      // Now and then a tall stroke above or below the line, as letters have.
      const reach = rand() < 0.12 ? 22 + rand() * 12 : 6 + rand() * 7;
      ctx.quadraticCurveTo(x + step / 2, y + (up ? -reach : reach * 0.5), x + step, y + (rand() - 0.5) * 3);
      x += step;
      up = !up;
    }
    x += 14 + rand() * 12;
  }
  ctx.stroke();
};

/**
 * One of the leaves between the class's chapter and the subclass's: notes no
 * one can read any more — faded lines of hand, a struck-out passage, a margin
 * sketch, a blot. Each seed fills its leaf differently.
 */
export const createLeafCanvas = (binding: BookBinding, side: 'left' | 'right', seed: number) => {
  const canvas = side === 'left' ? createLeftPaperCanvas(binding) : createRightPaperCanvas(binding);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  const stock = STOCKS[binding.sigil];
  const rand = mulberry32(seed * 7919 + 13);
  // More room on the gutter's side.
  const left = side === 'left' ? 110 : 170;
  const right = PAGE_W - (side === 'left' ? 170 : 110);

  ctx.save();
  ctx.strokeStyle = stock.faintInk;
  ctx.fillStyle = stock.faintInk;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // Where the sketch goes: top or bottom, and the writing keeps clear of it.
  const sketchTop = rand() < 0.5;
  const sketchY = sketchTop ? 300 : PAGE_H - 330;
  const struck = Math.floor(rand() * 14);
  let y = sketchTop ? 560 : 150;
  const last = sketchTop ? PAGE_H - 140 : PAGE_H - 560;
  for (let line = 0; y < last; line++) {
    // Paragraphs: an indent to start, a short last line, a gap.
    const paraEnd = rand() < 0.16;
    const x0 = left + (line === 0 || rand() < 0.1 ? 50 : 0);
    const x1 = paraEnd ? left + (right - left) * (0.3 + rand() * 0.4) : right - rand() * 30;
    ctx.globalAlpha = 0.45 + rand() * 0.35;
    ctx.lineWidth = 1.4 + rand() * 0.6;
    scrawl(ctx, rand, x0, x1, y);
    if (line === struck || line === struck + 1) {
      ctx.globalAlpha = 0.6;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x0 - 6, y - 8);
      ctx.bezierCurveTo(x0 + (x1 - x0) * 0.3, y - 2, x0 + (x1 - x0) * 0.7, y - 14, x1 + 6, y - 6);
      ctx.stroke();
    }
    y += paraEnd ? 74 : 46;
  }

  // The margin sketch.
  const cx = left + (right - left) * (0.3 + rand() * 0.4);
  ctx.globalAlpha = 0.55;
  ctx.lineWidth = 2;
  const kind = Math.floor(rand() * 3);
  if (kind === 0) {
    // A ward circle: rings, spokes and marks round its rim.
    ctx.beginPath();
    ctx.arc(cx, sketchY, 110, 0, Math.PI * 2);
    ctx.arc(cx, sketchY, 80, 0, Math.PI * 2);
    ctx.stroke();
    const points = 5 + Math.floor(rand() * 3);
    ctx.beginPath();
    for (let i = 0; i <= points; i++) {
      const a = (i * 2 * Math.PI * 2) / points - Math.PI / 2;
      const px2 = cx + Math.cos(a) * 80;
      const py2 = sketchY + Math.sin(a) * 80;
      if (i === 0) ctx.moveTo(px2, py2);
      else ctx.lineTo(px2, py2);
    }
    ctx.stroke();
    ctx.font = '24px serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2;
      ctx.fillText(RUNES[Math.floor(rand() * RUNES.length)], cx + Math.cos(a) * 95, sketchY + Math.sin(a) * 95);
    }
  } else if (kind === 1) {
    // A path drafted and abandoned: medallions joined by branches, one crossed out.
    const nodes = [
      [0, 90],
      [-70, 10],
      [70, 10],
      [-40, -80],
      [40, -80],
    ];
    const rim = 20;
    ctx.beginPath();
    [[0, 1], [0, 2], [1, 3], [2, 4], [1, 4]].forEach(([a, b]) => {
      // Branches stop at the medallions' rims, as on the tree itself.
      const [ax, ay] = nodes[a];
      const [bx, by] = nodes[b];
      const len = Math.hypot(bx - ax, by - ay);
      const ux = (bx - ax) / len;
      const uy = (by - ay) / len;
      ctx.moveTo(cx + ax + ux * rim, sketchY + ay + uy * rim);
      ctx.lineTo(cx + bx - ux * rim, sketchY + by - uy * rim);
    });
    ctx.stroke();
    nodes.forEach(([dx, dy]) => {
      ctx.beginPath();
      ctx.arc(cx + dx, sketchY + dy, rim, 0, Math.PI * 2);
      ctx.stroke();
    });
    const [dx, dy] = nodes[3 + Math.floor(rand() * 2)];
    ctx.beginPath();
    ctx.moveTo(cx + dx - 26, sketchY + dy - 26);
    ctx.lineTo(cx + dx + 26, sketchY + dy + 26);
    ctx.moveTo(cx + dx + 26, sketchY + dy - 26);
    ctx.lineTo(cx + dx - 26, sketchY + dy + 26);
    ctx.stroke();
  } else {
    // A hand's tally of something: rows of marks, bundled in fives, and a ringed note.
    for (let row = 0; row < 3; row++) {
      const n = 3 + Math.floor(rand() * 12);
      for (let i = 0; i < n; i++) {
        const group = Math.floor(i / 5);
        const x = cx - 130 + group * 70 + (i % 5) * 11;
        const yy = sketchY - 60 + row * 55;
        ctx.beginPath();
        if (i % 5 === 4) {
          ctx.moveTo(x - 50, yy + 14);
          ctx.lineTo(x + 4, yy - 14);
        } else {
          ctx.moveTo(x, yy - 18);
          ctx.lineTo(x + 2, yy + 18);
        }
        ctx.stroke();
      }
    }
    ctx.beginPath();
    ctx.ellipse(cx + 150, sketchY + 80, 70, 30, -0.1, 0, Math.PI * 2);
    ctx.stroke();
    scrawl(ctx, rand, cx + 100, cx + 200, sketchY + 86);
  }

  // A blot where the pen rested too long.
  if (rand() < 0.6) {
    const bx = left + rand() * (right - left);
    const by = 150 + rand() * (PAGE_H - 300);
    ctx.globalAlpha = 0.18 + rand() * 0.12;
    ctx.beginPath();
    ctx.arc(bx, by, 7 + rand() * 9, 0, Math.PI * 2);
    ctx.fill();
    for (let i = 0; i < 4; i++) {
      ctx.beginPath();
      ctx.arc(bx + (rand() - 0.5) * 50, by + (rand() - 0.5) * 50, 1.5 + rand() * 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
  return canvas;
};

/** A transparent sheet the size of a page, to write ink on. */
export const createInkCanvas = () => makeCanvas(PAGE_W, PAGE_H);

/**
 * The book's opening page, in ink only: its emblem, a few words on what the
 * book is, and a key to how the tree opposite is written.
 */
export const createIntroInkCanvas = (
  binding: BookBinding,
  title: string,
  classId: number,
  foreign: boolean,
  /** Words of the book's own, in place of its class's opening; a subclass book brings its tree's description. */
  paragraphs?: string[],
  /** A way back written in the corner, for a chapter's first page (see INTRO_BACK_REGION). */
  backLink?: string,
) => {
  const stock = STOCKS[binding.sigil];
  const classInk = CLASS_INK[classId] ?? stock.ink;
  const { canvas, ctx } = makeCanvas(PAGE_W, PAGE_H);
  const cx = PAGE_W * 0.47;

  if (backLink) {
    const { x, y } = INTRO_BACK_AT;
    ctx.font = 'italic 34px serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = stock.ink;
    ctx.fillText(backLink, x, y);
    ctx.strokeStyle = stock.ink;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x, y + 8);
    ctx.lineTo(x + ctx.measureText(backLink).width, y + 8);
    ctx.stroke();
  }

  ctx.strokeStyle = stock.ink;
  ctx.lineWidth = 5;
  ctx.lineCap = 'round';
  drawSigil(ctx, binding.sigil, cx, 210, 110);
  ctx.stroke();

  ctx.fillStyle = stock.ink;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = 'bold 54px serif';
  ctx.fillText(`Книга: ${title}`, cx, 395);
  ctx.strokeStyle = stock.ink;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx - 200, 440);
  ctx.lineTo(cx + 200, 440);
  ctx.stroke();

  // Body text, set like a book: italic, justified to a column.
  ctx.font = 'italic 31px serif';
  ctx.textAlign = 'left';
  let y = 500;
  for (const paragraph of paragraphs ?? INTROS[binding.sigil]) {
    for (const line of wrapLines(ctx, paragraph, 700)) {
      ctx.fillText(line, cx - 350, y);
      y += 42;
    }
    y += 22;
  }

  // The key
  y = Math.max(y + 10, 1000);
  ctx.textAlign = 'center';
  ctx.font = 'bold 26px serif';
  ctx.fillText(foreign ? 'Это книга другого класса — её можно только читать.' : 'Как читать древо', cx, y);
  if (!foreign) {
    ctx.font = 'italic 24px serif';
    ctx.textAlign = 'left';
    LEGEND.forEach(({ state, label }, i) => {
      const col = i % 2;
      const row = Math.floor(i / 2);
      const sx = cx - 330 + col * 370;
      const sy = y + 70 + row * 90;
      // A specimen node, drawn at a third of the spread's scale, centred on (sx, sy).
      const specimen: SpreadNode = {
        id: 3 + i * 5,
        node: { name: '' } as SpreadNode['node'],
        u: (sx / PAGE_W) - 1,
        v: 1 - sy / PAGE_H,
        state,
        large: false,
      };
      drawNode(ctx, specimen, stock, classInk, pathInk(classId), false);
      ctx.fillStyle = stock.ink;
      ctx.fillText(label, sx + 60, sy);
    });
    ctx.textAlign = 'center';
    ctx.font = 'italic 26px serif';
    ctx.fillStyle = stock.faintInk;
    ctx.fillText('Коснитесь узла древа, чтобы прочесть его страницу.', cx, y + 270);
  }
  return canvas;
};

/** The right-hand page of an open book with its class tree inked on it. */
export const createTreePageTexture = (model: SpreadModel, binding: BookBinding, title: string) => {
  const stock = STOCKS[binding.sigil];
  const classInk = CLASS_INK[model.classId] ?? stock.ink;

  const { canvas: ink, ctx } = makeCanvas(SPREAD_W, PAGE_H);
  drawHeadings(ctx, title, stock);
  drawLevelMarks(ctx, model, stock);
  // Dead and pencil first, so live ink and the walked path lie over them where they cross.
  const path = pathInk(model.classId);
  const order = { dead: 0, locked: 1, plain: 2, open: 3, walked: 4 } as const;
  [...model.edges].sort((a, b) => order[a.kind] - order[b.kind]).forEach((e) => drawBranch(ctx, e, stock, path));
  // Subclass names alternate rows along their level, left to right.
  const topRow = model.nodes.filter((n) => n.large).sort((a, b) => a.u - b.u);
  model.nodes.forEach((n) =>
    drawNode(ctx, n, stock, classInk, path, model.foreign, (Math.max(0, topRow.indexOf(n)) % 2) as 0 | 1),
  );

  const { canvas, ctx: pageCtx } = makeCanvas(PAGE_W, PAGE_H);
  paper(pageCtx, PAGE_W, PAGE_H, 'left', 34, stock);
  weatherPage(pageCtx, PAGE_W, PAGE_H, binding.sigil, 'left', 34);
  pageCtx.drawImage(ink, PAGE_W, 0, PAGE_W, PAGE_H, 0, 0, PAGE_W, PAGE_H);
  return toTexture(canvas);
};
