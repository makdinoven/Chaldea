import type { PaperStock } from './bookTextures';
import { BLOOD, box, link, picture, wrap } from './nodePageInk';
import { pathInkFor } from './spreadTextures';
import { skillActionKey, type SkillPageAction, type SkillPageModel, type SkillPagePerk } from './skillPageModel';

/*
  A skill's spread, written in ink on transparent page-sized sheets: its card
  on the left-hand page, its perks on the right. Like a node's page, controls
  are drawn — ruled boxes, underlined words, wax seals — and come back as
  regions for the book to hit-test clicks against.
*/

export interface SkillRegion {
  action: SkillPageAction;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Text columns: the left page's gutter is on its right, the right page's on its left. */
const CARD = { left: 100, right: 910 } as const;
const PERKS = { left: 130, right: 930 } as const;

const ink = (ctx: CanvasRenderingContext2D, font: string, colour: string) => {
  ctx.font = font;
  ctx.fillStyle = colour;
};

/** The loading and failure states, shared by both pages. */
const pending = (ctx: CanvasRenderingContext2D, width: number, height: number, model: SkillPageModel, stock: PaperStock) => {
  ctx.textAlign = 'center';
  ink(ctx, 'italic 38px serif', stock.faintInk);
  ctx.fillText(model.error ? 'Чернила расплылись…' : 'Чернила ещё сохнут…', width / 2, height / 2);
  ctx.textAlign = 'left';
};

/** Left-hand page: the skill's picture, name, level, numbers and what can be done with it. */
export const drawSkillCard = (
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  model: SkillPageModel,
  stock: PaperStock,
  classInk: string,
  hovered: string | null,
): SkillRegion[] => {
  const regions: SkillRegion[] = [];
  const isHovered = (a: SkillPageAction) => hovered === skillActionKey(a);
  const { left, right } = CARD;
  const column = right - left;
  ctx.textBaseline = 'alphabetic';
  ctx.textAlign = 'left';

  const back: SkillPageAction = { kind: 'back' };
  ctx.font = 'italic 34px serif';
  const bw = link(ctx, '← К древу', left, 100, stock.ink, isHovered(back));
  regions.push({ action: back, x: left - 10, y: 60, w: bw + 20, h: 60 });

  if (!model.title) {
    pending(ctx, width, height, model, stock);
    if (model.error) {
      const retry: SkillPageAction = { kind: 'retry' };
      ctx.font = 'italic 34px serif';
      const rw = link(ctx, 'Попробовать снова', width / 2 - 140, height / 2 + 70, classInk, isHovered(retry));
      regions.push({ action: retry, x: width / 2 - 150, y: height / 2 + 30, w: rw + 20, h: 60 });
    }
    return regions;
  }

  // Picture, name and level
  picture(ctx, model.image, left + 86, 250, 86, stock.ink);
  const tx = left + 200;
  let y = 225;
  ink(ctx, 'bold 56px serif', stock.ink);
  for (const line of wrap(ctx, model.title.toUpperCase(), right - tx)) {
    ctx.fillText(line, tx, y);
    y += 62;
  }
  ink(ctx, 'italic 30px serif', stock.faintInk);
  ctx.fillText('Уровень', tx, y + 4);
  const lx = tx + ctx.measureText('Уровень').width + 30;
  for (let i = 0; i < model.maxLevel; i++) {
    // Each level reached is a circle filled with ink.
    ctx.beginPath();
    ctx.arc(lx + i * 46, y - 6, 16, 0, Math.PI * 2);
    ctx.strokeStyle = stock.ink;
    ctx.lineWidth = 2.5;
    ctx.stroke();
    if (i < model.level) {
      ctx.fillStyle = classInk;
      ctx.fill();
    }
  }
  y += 50;
  if (model.freePerkPoints > 0) {
    ink(ctx, 'italic bold 30px serif', classInk);
    ctx.fillText(`Свободных очков перка: ${model.freePerkPoints} — выберите перк справа`, left, y + 20);
    y += 50;
  }
  y = Math.max(y, 380);

  if (model.description) {
    ink(ctx, 'italic 31px serif', stock.ink);
    for (const line of wrap(ctx, model.description, column)) {
      ctx.fillText(line, left, y);
      y += 42;
    }
    y += 18;
  }

  // Numbers: the skill's base, and what it comes to with its level and perks
  ink(ctx, 'italic 26px serif', stock.faintInk);
  ctx.fillText('база', left + 420, y);
  ctx.fillText('итог', left + 560, y);
  y += 44;
  for (const s of model.stats) {
    ink(ctx, 'italic 32px serif', stock.ink);
    ctx.fillText(s.label, left, y);
    ink(ctx, '32px serif', stock.faintInk);
    ctx.fillText(String(s.base), left + 420, y);
    ctx.fillText('→', left + 490, y);
    ink(ctx, 'bold 32px serif', s.total !== s.base ? classInk : stock.ink);
    ctx.fillText(String(s.total), left + 560, y);
    y += 44;
  }
  y += 10;
  for (const e of model.effects) {
    ink(ctx, 'italic 30px serif', e.tone === 'damage' ? BLOOD : classInk);
    for (const line of wrap(ctx, e.text, column)) {
      ctx.fillText(line, left, y);
      y += 40;
    }
  }

  // What can be done: upgrade, and reset — or, while asking, the question.
  const foot = height - 290;
  if (model.confirmingReset) {
    ink(ctx, 'italic 31px serif', BLOOD);
    let qy = foot;
    for (const line of wrap(
      ctx,
      'Сбросить навык? Потраченный на улучшения опыт не вернётся, а следующий сброс откроется только через 24 часа.',
      column,
    )) {
      ctx.fillText(line, left, qy);
      qy += 42;
    }
    const yes: SkillPageAction = { kind: 'confirmReset' };
    const no: SkillPageAction = { kind: 'cancelReset' };
    const half = (column - 30) / 2;
    ctx.font = 'bold 34px serif';
    box(ctx, 'ДА, СБРОСИТЬ', left, qy + 10, half, 84, BLOOD, isHovered(yes), false);
    box(ctx, 'ОТМЕНА', left + half + 30, qy + 10, half, 84, stock.ink, isHovered(no), false);
    regions.push({ action: yes, x: left, y: qy + 10, w: half, h: 84 });
    regions.push({ action: no, x: left + half + 30, y: qy + 10, w: half, h: 84 });
  } else {
    const upgrade: SkillPageAction = { kind: 'upgrade' };
    ctx.font = 'bold 38px serif';
    box(
      ctx,
      model.upgrade.label.toUpperCase(),
      left,
      foot,
      column,
      96,
      model.upgrade.enabled ? classInk : stock.faintInk,
      model.upgrade.enabled && isHovered(upgrade),
      model.upgrade.busy,
    );
    if (model.upgrade.enabled) regions.push({ action: upgrade, x: left, y: foot, w: column, h: 96 });

    const reset: SkillPageAction = { kind: 'reset' };
    ctx.font = 'italic 32px serif';
    if (model.reset.enabled) {
      const rw = link(ctx, model.reset.label, left, foot + 170, BLOOD, isHovered(reset));
      regions.push({ action: reset, x: left - 10, y: foot + 130, w: rw + 20, h: 60 });
    } else {
      ink(ctx, 'italic 32px serif', stock.faintInk);
      ctx.fillText(model.reset.label, left, foot + 170);
    }
  }
  return regions;
};

/** A wax seal pressed onto the page beside a chosen perk. */
const waxSeal = (ctx: CanvasRenderingContext2D, x: number, y: number, r: number, wax: string) => {
  ctx.save();
  // An uneven blob of wax...
  ctx.beginPath();
  for (let i = 0; i <= 20; i++) {
    const a = (i / 20) * Math.PI * 2;
    const rr = r * (1 + 0.08 * Math.sin(a * 5 + x));
    if (i === 0) ctx.moveTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
    else ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
  }
  const g = ctx.createRadialGradient(x - r * 0.3, y - r * 0.3, 2, x, y, r * 1.1);
  g.addColorStop(0, '#ffffff');
  g.addColorStop(0.08, wax);
  g.addColorStop(1, 'rgba(0,0,0,0.85)');
  ctx.fillStyle = wax;
  ctx.fill();
  ctx.globalCompositeOperation = 'multiply';
  ctx.fillStyle = g;
  ctx.fill();
  ctx.globalCompositeOperation = 'source-over';
  // ...with a ring and a star pressed into it.
  ctx.strokeStyle = 'rgba(255,255,255,0.35)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(x, y, r * 0.68, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  for (let i = 0; i <= 10; i++) {
    const a = (i / 10) * Math.PI * 2 - Math.PI / 2;
    const rr = i % 2 === 0 ? r * 0.5 : r * 0.2;
    if (i === 0) ctx.moveTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
    else ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
  }
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.fill();
  ctx.restore();
};

const PERK_TOP = 270;
const PERK_FOOT_ROOM = 170;
const SEAL_R = 32;

/** How tall a perk's entry is once written, in canvas pixels. */
const entryHeight = (ctx: CanvasRenderingContext2D, perk: SkillPagePerk, textWidth: number) => {
  ctx.font = 'italic 26px serif';
  const desc = perk.description ? Math.min(2, wrap(ctx, perk.description, textWidth).length) : 0;
  const changes = perk.changes.length ? wrap(ctx, perk.changes.join(' · '), textWidth).length : 0;
  return 50 + (desc + changes) * 34 + 26;
};

/** Splits the perks into pages that each fit the right-hand page. */
const paginate = (ctx: CanvasRenderingContext2D, perks: SkillPagePerk[], height: number, textWidth: number) => {
  const pages: SkillPagePerk[][] = [[]];
  let y = PERK_TOP;
  for (const perk of perks) {
    const h = entryHeight(ctx, perk, textWidth);
    if (y + h > height - PERK_FOOT_ROOM && pages[pages.length - 1].length > 0) {
      pages.push([]);
      y = PERK_TOP;
    }
    pages[pages.length - 1].push(perk);
    y += h;
  }
  return pages;
};

/** Right-hand page: the skill's perks, chosen ones sealed in wax, and paging if they run over. */
export const drawPerks = (
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  model: SkillPageModel,
  stock: PaperStock,
  classInk: string,
  hovered: string | null,
): SkillRegion[] => {
  const regions: SkillRegion[] = [];
  const isHovered = (a: SkillPageAction) => hovered === skillActionKey(a);
  const { left, right } = PERKS;
  const textX = left + SEAL_R * 2 + 30;
  const textWidth = right - textX;
  ctx.textBaseline = 'alphabetic';
  ctx.textAlign = 'left';

  if (!model.title) {
    pending(ctx, width, height, model, stock);
    return regions;
  }

  ink(ctx, 'bold 44px serif', stock.ink);
  ctx.fillText(`ПЕРКИ (${model.perks.length})`, left, 150);
  if (model.perkNote) {
    ink(ctx, 'italic bold 30px serif', model.freePerkPoints > 0 ? classInk : stock.faintInk);
    ctx.fillText(model.perkNote, left, 200);
  }

  if (model.perks.length === 0) {
    ink(ctx, 'italic 32px serif', stock.faintInk);
    ctx.fillText('Перки этого навыка ещё не записаны.', left, PERK_TOP + 40);
    return regions;
  }

  const pages = paginate(ctx, model.perks, height, textWidth);
  const page = Math.min(model.perkPage, pages.length - 1);
  let y = PERK_TOP;
  for (const perk of pages[page]) {
    const top = y;
    const h = entryHeight(ctx, perk, textWidth);
    const pick: SkillPageAction = { kind: 'pick', perkId: perk.id };
    const hot = perk.state === 'available' && isHovered(pick);
    const sx = left + SEAL_R;
    const sy = top + 30;

    if (perk.state === 'selected') waxSeal(ctx, sx, sy, SEAL_R, classInk);
    else {
      ctx.beginPath();
      ctx.arc(sx, sy, SEAL_R, 0, Math.PI * 2);
      ctx.strokeStyle = perk.state === 'available' ? classInk : 'rgba(70,70,70,0.45)';
      ctx.lineWidth = perk.state === 'available' ? (hot ? 4.5 : 3) : 1.5;
      ctx.stroke();
      if (perk.state === 'available') {
        ctx.beginPath();
        ctx.arc(sx, sy, SEAL_R - 8, 0, Math.PI * 2);
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

    // A chosen perk is named in the colour its class lays its path in, as its seal is.
    const nameColour =
      perk.state === 'selected' ? pathInkFor(classInk).dark : perk.state === 'available' ? stock.ink : stock.faintInk;
    ink(ctx, `bold ${hot ? 36 : 34}px serif`, nameColour);
    ctx.fillText(perk.name, textX, top + 40);
    let ly = top + 40;
    if (perk.description) {
      ink(ctx, 'italic 26px serif', stock.faintInk);
      for (const line of wrap(ctx, perk.description, textWidth).slice(0, 2)) {
        ly += 34;
        ctx.fillText(line, textX, ly);
      }
    }
    if (perk.changes.length) {
      ink(ctx, 'italic 26px serif', perk.state === 'locked' ? stock.faintInk : classInk);
      for (const line of wrap(ctx, perk.changes.join(' · '), textWidth)) {
        ly += 34;
        ctx.fillText(line, textX, ly);
      }
    }
    if (perk.state === 'available') regions.push({ action: pick, x: left - 10, y: top - 6, w: right - left + 20, h: h - 14 });
    y += h;
  }

  if (pages.length > 1) {
    const ny = height - 100;
    ctx.font = 'italic 32px serif';
    if (page > 0) {
      const prev: SkillPageAction = { kind: 'perkPage', page: page - 1 };
      const pw = link(ctx, '← назад', left, ny, stock.ink, isHovered(prev));
      regions.push({ action: prev, x: left - 10, y: ny - 40, w: pw + 20, h: 60 });
    }
    ink(ctx, 'italic 28px serif', stock.faintInk);
    ctx.textAlign = 'center';
    ctx.fillText(`${page + 1} / ${pages.length}`, (left + right) / 2, ny);
    ctx.textAlign = 'left';
    if (page < pages.length - 1) {
      const next: SkillPageAction = { kind: 'perkPage', page: page + 1 };
      ctx.font = 'italic 32px serif';
      const label = 'далее →';
      const nw = ctx.measureText(label).width;
      link(ctx, label, right - nw, ny, stock.ink, isHovered(next));
      regions.push({ action: next, x: right - nw - 10, y: ny - 40, w: nw + 20, h: 60 });
    }
  }
  return regions;
};

/** The control at a point on a page, if any. */
export const skillRegionAt = (regions: SkillRegion[], x: number, y: number) =>
  regions.find((r) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) ?? null;
