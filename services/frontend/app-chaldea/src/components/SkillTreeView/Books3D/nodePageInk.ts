import type { PaperStock } from './bookTextures';
import { pathInkFor } from './spreadTextures';
import { actionKey, type NodePageAction, type NodePageModel, type NodePageTone } from './nodePageModel';

/*
  A node's page, written in ink on a transparent sheet the size of a book page;
  the book lays it over its own paper. Controls are drawn like everything else
  on the page — a ruled box, an underlined word — and their places come back as
  regions, so the book can tell which one a click on the paper landed on.
*/

export interface InkRegion {
  action: NodePageAction;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Where the text column runs on a left-hand page: the fore-edge on the left, the gutter on the right. */
const LEFT = 100;
const RIGHT = 910;
const COLUMN = RIGHT - LEFT;

export const BLOOD = '#7a1a12';

/** A taken node is written in the colour its class lays its path in, as on the tree. */
const toneColour = (tone: NodePageTone, stock: PaperStock, classInk: string) =>
  tone === 'chosen'
    ? pathInkFor(classInk).dark
    : tone === 'available'
      ? classInk
      : tone === 'blocked'
        ? BLOOD
        : stock.faintInk;

export const wrap = (ctx: CanvasRenderingContext2D, text: string, width: number) => {
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > width && line) {
      lines.push(line);
      line = word;
    } else line = next;
  }
  if (line) lines.push(line);
  return lines;
};

/* Skill pictures live on the media proxy; they are fetched once and kept. */
const pictures = new Map<string, HTMLImageElement | 'loading' | 'failed'>();

/** Starts loading a picture if it isn't already; calls back when it arrives. */
export const loadPicture = (url: string | null, onLoad: () => void) => {
  if (!url || pictures.has(url)) return;
  pictures.set(url, 'loading');
  const img = new Image();
  img.onload = () => {
    pictures.set(url, img);
    onLoad();
  };
  img.onerror = () => pictures.set(url, 'failed');
  img.src = url;
};

/** Starts loading any skill pictures the page needs; calls back as each arrives. */
export const loadPictures = (model: NodePageModel, onLoad: () => void) => {
  for (const s of model.skills) loadPicture(s.image, onLoad);
};

/** A word that acts when touched: underlined, darker under the pointer. */
export const link = (
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  colour: string,
  hovered: boolean,
) => {
  ctx.fillStyle = colour;
  ctx.fillText(text, x, y);
  const w = ctx.measureText(text).width;
  ctx.strokeStyle = colour;
  ctx.lineWidth = hovered ? 3 : 1.5;
  ctx.beginPath();
  ctx.moveTo(x, y + 8);
  ctx.lineTo(x + w, y + 8);
  ctx.stroke();
  return w;
};

/** A ruled box with a label: the page's buttons. */
export const box = (
  ctx: CanvasRenderingContext2D,
  label: string,
  x: number,
  y: number,
  w: number,
  h: number,
  colour: string,
  hovered: boolean,
  busy: boolean,
) => {
  ctx.save();
  ctx.globalAlpha = busy ? 0.45 : 1;
  if (hovered && !busy) {
    ctx.fillStyle = colour;
    ctx.globalAlpha = 0.1;
    ctx.fillRect(x, y, w, h);
    ctx.globalAlpha = 1;
  }
  ctx.strokeStyle = colour;
  ctx.lineWidth = hovered ? 4 : 3;
  ctx.strokeRect(x, y, w, h);
  // A second, finer rule just inside, as on an engraved plate.
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 6, y + 6, w - 12, h - 12);
  ctx.fillStyle = colour;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x + w / 2, y + h / 2 + 2);
  ctx.restore();
};

/** A skill's picture in a ringed medallion, faded to sepia so it sits in the ink; a star if there is none. */
export const picture = (ctx: CanvasRenderingContext2D, url: string | null, cx: number, cy: number, r: number, ink: string) => {
  const img = url ? pictures.get(url) : undefined;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  if (img instanceof HTMLImageElement) {
    ctx.save();
    ctx.clip();
    ctx.filter = 'sepia(0.7) contrast(0.9) brightness(0.95)';
    ctx.globalAlpha = 0.85;
    ctx.drawImage(img, cx - r, cy - r, r * 2, r * 2);
    ctx.restore();
  } else {
    ctx.fillStyle = ink;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `${r}px serif`;
    ctx.globalAlpha = 0.5;
    ctx.fillText('★', cx, cy + 2);
    ctx.globalAlpha = 1;
  }
  ctx.strokeStyle = ink;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
};

/**
 * Writes the page and returns where each control ended up.
 * `hovered` is the actionKey of the control under the pointer, if any.
 */
export const drawNodePageInk = (
  ctx: CanvasRenderingContext2D,
  height: number,
  model: NodePageModel,
  stock: PaperStock,
  classInk: string,
  hovered: string | null,
): InkRegion[] => {
  const regions: InkRegion[] = [];
  const isHovered = (a: NodePageAction) => hovered === actionKey(a);
  ctx.textBaseline = 'alphabetic';
  ctx.textAlign = 'left';

  // Close mark, top corner by the gutter
  const close: NodePageAction = { kind: 'close' };
  ctx.font = `${isHovered(close) ? 'bold ' : ''}52px serif`;
  ctx.fillStyle = isHovered(close) ? stock.ink : stock.faintInk;
  ctx.fillText('✕', RIGHT - 20, 120);
  regions.push({ action: close, x: RIGHT - 40, y: 60, w: 90, h: 90 });

  // Title, wrapped if long
  let y = 175;
  ctx.fillStyle = stock.ink;
  ctx.font = 'bold 72px serif';
  for (const line of wrap(ctx, model.title.toUpperCase(), COLUMN - 80)) {
    ctx.fillText(line, LEFT, y);
    y += 80;
  }
  ctx.font = 'italic 34px serif';
  ctx.fillStyle = stock.faintInk;
  ctx.fillText(model.meta, LEFT, y - 14);
  y += 14;
  ctx.strokeStyle = stock.ink;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(LEFT, y);
  ctx.lineTo(LEFT + COLUMN * 0.6, y);
  ctx.stroke();
  y += 56;

  if (model.description) {
    ctx.font = 'italic 38px serif';
    ctx.fillStyle = stock.ink;
    for (const line of wrap(ctx, model.description, COLUMN)) {
      ctx.fillText(line, LEFT, y);
      y += 52;
    }
    y += 16;
  }

  // Status, set off like a marginal note
  ctx.font = 'italic bold 37px serif';
  ctx.fillStyle = toneColour(model.status.tone, stock, classInk);
  ctx.fillText(`— ${model.status.text} —`, LEFT, y);
  y += 40;

  if (model.action) {
    y += 20;
    const a: NodePageAction = { kind: model.action.kind };
    ctx.font = 'bold 44px serif';
    box(ctx, model.action.label.toUpperCase(), LEFT, y, COLUMN, 100, classInk, isHovered(a), model.action.busy);
    regions.push({ action: a, x: LEFT, y, w: COLUMN, h: 100 });
    y += 100 + 30;
  }

  if (model.skillsMode !== 'hidden' && model.skills.length > 0) {
    y += 34;
    ctx.font = 'bold 42px serif';
    ctx.fillStyle = stock.ink;
    ctx.fillText(`НАВЫКИ (${model.skills.length})`, LEFT, y);
    y += 26;

    for (const s of model.skills) {
      if (model.skillsMode === 'listed') {
        y += 52;
        ctx.font = '37px serif';
        ctx.fillStyle = stock.ink;
        ctx.fillText(`• ${s.name}`, LEFT + 10, y);
        continue;
      }
      const top = y + 18;
      picture(ctx, s.image, LEFT + 52, top + 56, 50, stock.ink);
      const tx = LEFT + 126;
      ctx.font = 'bold 40px serif';
      ctx.fillStyle = stock.ink;
      ctx.fillText(s.name, tx, top + 44);
      if (s.typeLabel) {
        const nameW = ctx.measureText(s.name).width;
        ctx.font = 'italic 28px serif';
        ctx.fillStyle = stock.faintInk;
        ctx.fillText(s.typeLabel.toLowerCase(), tx + nameW + 16, top + 44);
      }
      ctx.font = '30px serif';
      if (s.learned) {
        ctx.fillStyle = pathInkFor(classInk).dark;
        ctx.font = 'italic bold 35px serif';
        ctx.fillText('Изучено ✓', tx, top + 96);
        const upgrade: NodePageAction = { kind: 'upgrade', skillId: s.skillId };
        const ux = tx + ctx.measureText('Изучено ✓').width + 30;
        ctx.font = 'italic 35px serif';
        const uw = link(ctx, 'Улучшить', ux, top + 96, classInk, isHovered(upgrade));
        regions.push({ action: upgrade, x: ux - 10, y: top + 62, w: uw + 20, h: 50 });
      } else {
        const learn: NodePageAction = { kind: 'learn', skillId: s.skillId };
        ctx.font = 'bold 32px serif';
        box(ctx, s.busy ? 'ИЗУЧЕНИЕ…' : 'ИЗУЧИТЬ', tx, top + 64, 240, 58, classInk, isHovered(learn), s.busy);
        regions.push({ action: learn, x: tx, y: top + 64, w: 240, h: 58 });
      }
      y = top + 136;
    }
  }

  if (model.hint) {
    y += 40;
    ctx.font = 'italic 32px serif';
    ctx.fillStyle = stock.faintInk;
    for (const line of wrap(ctx, model.hint, COLUMN)) {
      ctx.fillText(line, LEFT, y);
      y += 44;
    }
  }

  if (model.canReset) {
    const reset: NodePageAction = { kind: 'reset' };
    ctx.font = 'italic 33px serif';
    const ry = height - 100;
    const rw = link(ctx, 'Сбросить прогресс', LEFT, ry, BLOOD, isHovered(reset));
    regions.push({ action: reset, x: LEFT - 10, y: ry - 38, w: rw + 20, h: 56 });
  }

  return regions;
};

/** The control at a point on the page, if any. */
export const regionAt = (regions: InkRegion[], x: number, y: number) =>
  regions.find((r) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) ?? null;
