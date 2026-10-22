import * as THREE from 'three';
import { megalinkNumber } from '../../../api/charactersPublic';
import {
  DASH,
  SEX_LABELS,
  formatLineage,
  formatRegisteredAt,
  formatTenure,
} from '../../CommonComponents/CharacterPassport/passportText';
import type { PassportData } from '../../CommonComponents/CharacterPassport/types';
import { mulberry32 } from './bookTextures';
import { scrawl } from './spreadTextures';

/*
  The player's Скиталец passport as a sheet of paper: the Citadel's registry
  form, filled in. Laid out like the passport sheet — portrait and name at the
  head, the rows under it — but as a printed and inked document: ruled lines,
  a red registry stamp, the registrar's hand at the foot, and a space left
  for the wax seal set on it (CharacterDossier).
*/

export const DOSSIER_PX = { w: 1024, h: 1356 } as const;
/** Where the wax seal sits on the sheet, canvas pixels. */
export const DOSSIER_SEAL_AT = { x: 860, y: 1222 } as const;

const SERIF = '"Cormorant Garamond", Georgia, serif';
const INK = '#2f2416';
const FAINT = 'rgba(47,36,22,0.55)';
const STAMP_RED = 'rgba(150,32,28,0.55)';

/** The faces the sheet is written in, loaded before it is drawn. */
export const loadDossierFonts = () =>
  Promise.all(
    ['bold 56px', 'italic 32px', '32px', 'bold 26px'].map((f) =>
      document.fonts.load(`${f} "Cormorant Garamond"`).catch(() => []),
    ),
  );

const paper = (ctx: CanvasRenderingContext2D, w: number, h: number, rand: () => number) => {
  ctx.fillStyle = '#eee2c6';
  ctx.fillRect(0, 0, w, h);
  for (let i = 0; i < 26; i++) {
    const x = rand() * w;
    const y = rand() * h;
    const r = 40 + rand() * 180;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, rand() < 0.6 ? 'rgba(150,110,55,0.08)' : 'rgba(255,250,235,0.12)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  ctx.fillStyle = 'rgba(140,90,40,0.18)';
  for (let i = 0; i < 140; i++) {
    ctx.beginPath();
    ctx.arc(rand() * w, rand() * h, 0.6 + rand() * 2, 0, Math.PI * 2);
    ctx.fill();
  }
  // Folded in three to be carried, and opened out again.
  for (const y of [h / 3, (h * 2) / 3]) {
    ctx.fillStyle = 'rgba(255,252,240,0.35)';
    ctx.fillRect(0, y - 2, w, 3);
    ctx.fillStyle = 'rgba(90,60,25,0.18)';
    ctx.fillRect(0, y + 1, w, 1.5);
  }
  const band = 60;
  const edges: [number, number, number, number][] = [
    [0, 0, band, 0],
    [w, 0, w - band, 0],
    [0, 0, 0, band],
    [0, h, 0, h - band],
  ];
  edges.forEach(([x0, y0, x1, y1]) => {
    const g = ctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, 'rgba(110,70,30,0.35)');
    g.addColorStop(1, 'rgba(110,70,30,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  });
};

/** Text that must fit a width: shrunk until it does. */
const fitText = (ctx: CanvasRenderingContext2D, text: string, weight: string, size: number, maxWidth: number) => {
  let px = size;
  ctx.font = `${weight} ${px}px ${SERIF}`;
  while (px > 18 && ctx.measureText(text).width > maxWidth) {
    px -= 2;
    ctx.font = `${weight} ${px}px ${SERIF}`;
  }
  return px;
};

/** The portrait in its frame: the picture cut to fill it, or the name's first letter. */
const drawPortrait = (
  ctx: CanvasRenderingContext2D,
  picture: HTMLImageElement | null,
  name: string,
  x: number,
  y: number,
  w: number,
  h: number,
) => {
  ctx.fillStyle = '#d8c7a2';
  ctx.fillRect(x, y, w, h);
  if (picture) {
    const scale = Math.max(w / picture.naturalWidth, h / picture.naturalHeight);
    const sw = w / scale;
    const sh = h / scale;
    ctx.save();
    // Printed onto the paper: a little faded and warmed.
    ctx.filter = 'sepia(0.25) saturate(0.85) contrast(0.95)';
    ctx.drawImage(picture, (picture.naturalWidth - sw) / 2, (picture.naturalHeight - sh) / 2, sw, sh, x, y, w, h);
    ctx.restore();
  } else {
    ctx.fillStyle = FAINT;
    ctx.font = `bold 160px ${SERIF}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(name.charAt(0).toUpperCase(), x + w / 2, y + h / 2);
  }
  ctx.strokeStyle = INK;
  ctx.lineWidth = 3;
  ctx.strokeRect(x - 6, y - 6, w + 12, h + 12);
  ctx.lineWidth = 1.2;
  ctx.strokeRect(x - 13, y - 13, w + 26, h + 26);
  // Paper corners holding it in.
  ctx.fillStyle = 'rgba(60,45,25,0.85)';
  for (const [cx, cy, sx, sy] of [
    [x, y, 1, 1],
    [x + w, y, -1, 1],
    [x, y + h, 1, -1],
    [x + w, y + h, -1, -1],
  ] as const) {
    ctx.beginPath();
    ctx.moveTo(cx - sx * 4, cy - sy * 4);
    ctx.lineTo(cx + sx * 40, cy - sy * 4);
    ctx.lineTo(cx - sx * 4, cy + sy * 40);
    ctx.closePath();
    ctx.fill();
  }
};

/** A red registry stamp, struck at an angle and not quite evenly. */
const drawStamp = (ctx: CanvasRenderingContext2D, x: number, y: number, rand: () => number) => {
  const face = document.createElement('canvas');
  face.width = 420;
  face.height = 150;
  const f = face.getContext('2d');
  if (!f) return;
  f.strokeStyle = STAMP_RED;
  f.fillStyle = STAMP_RED;
  f.lineWidth = 6;
  f.strokeRect(8, 8, 404, 134);
  f.lineWidth = 2;
  f.strokeRect(20, 20, 380, 110);
  f.font = `bold 38px ${SERIF}`;
  f.textAlign = 'center';
  f.textBaseline = 'middle';
  f.fillText('ЗАРЕГИСТРИРОВАН', 210, 66);
  f.font = `bold 24px ${SERIF}`;
  f.fillText('РЕЕСТР ЦИТАДЕЛИ', 210, 108);
  // The ink took unevenly.
  f.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < 220; i++) {
    f.fillStyle = `rgba(0,0,0,${0.3 + rand() * 0.7})`;
    f.beginPath();
    f.arc(rand() * 420, rand() * 150, 1 + rand() * 4, 0, Math.PI * 2);
    f.fill();
  }
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(-0.16);
  ctx.drawImage(face, -210, -75);
  ctx.restore();
};

/**
 * Draws the passport onto a sheet. `picture` is the portrait, already loaded
 * from a same-origin address, or null for the name's first letter.
 */
export const createDossierTexture = (data: PassportData, currentGameYear: number | null, picture: HTMLImageElement | null) => {
  const { w: W, h: H } = DOSSIER_PX;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  const rand = mulberry32((data.characterId ?? 1) * 131);
  paper(ctx, W, H, rand);

  // Head of the form.
  ctx.fillStyle = FAINT;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.font = `bold 26px ${SERIF}`;
  ctx.letterSpacing = '6px';
  ctx.fillText('РЕЕСТР ЦИТАДЕЛИ', W / 2, 78);
  ctx.letterSpacing = '0px';
  ctx.fillStyle = INK;
  ctx.font = `bold 58px ${SERIF}`;
  ctx.fillText('Паспорт Скитальца', W / 2, 140);
  ctx.strokeStyle = INK;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(W * 0.2, 166);
  ctx.lineTo(W * 0.8, 166);
  ctx.moveTo(W * 0.3, 174);
  ctx.lineTo(W * 0.7, 174);
  ctx.stroke();

  // Portrait, and beside it who this is.
  const portrait = { x: 80, y: 220, w: 300, h: 380 };
  drawPortrait(ctx, picture, data.name, portrait.x, portrait.y, portrait.w, portrait.h);
  const colX = 440;
  const colW = W - colX - 70;
  ctx.textAlign = 'left';
  ctx.fillStyle = INK;
  const namePx = fitText(ctx, data.name, 'bold', 64, colW);
  ctx.fillText(data.name, colX, 270 + (64 - namePx) / 2);
  ctx.fillStyle = FAINT;
  fitText(ctx, formatLineage(data), 'italic', 34, colW);
  ctx.fillText(formatLineage(data), colX, 322);

  // УР, boxed, as the badge on the sheet is.
  const level = `УР ${data.level ?? 1}`;
  ctx.font = `bold 34px ${SERIF}`;
  const lw = ctx.measureText(level).width + 36;
  ctx.strokeStyle = INK;
  ctx.lineWidth = 2;
  ctx.strokeRect(colX, 360, lw, 52);
  ctx.fillStyle = INK;
  ctx.fillText(level, colX + 18, 398);
  if (data.className) {
    ctx.font = `italic 32px ${SERIF}`;
    ctx.fillText(data.className, colX + lw + 24, 398);
  }

  const megalink = typeof data.characterId === 'number' && data.characterId > 0 ? megalinkNumber(data.characterId) : DASH;
  ctx.fillStyle = FAINT;
  ctx.font = `bold 24px ${SERIF}`;
  ctx.letterSpacing = '3px';
  ctx.fillText('МЕГАЛИНК', colX, 470);
  ctx.letterSpacing = '0px';
  ctx.fillStyle = INK;
  ctx.font = `bold 44px ${SERIF}`;
  ctx.letterSpacing = '4px';
  ctx.fillText(megalink, colX, 520);
  ctx.letterSpacing = '0px';

  // Struck over the right of the form, between the Megalink and the rows.
  drawStamp(ctx, W - 270, 612, rand);

  // The rows, label left and value right on a dotted ruling.
  const rows: [string, string][] = [
    ['Раса', data.raceName ?? DASH],
    ['Подраса', data.subraceName ?? DASH],
    ['Родина', data.origin?.name ?? DASH],
    ['Путь', data.className ?? DASH],
    ['Пол', data.sex ? SEX_LABELS[data.sex] ?? data.sex : DASH],
    ['Возраст', data.age != null ? String(data.age) : DASH],
    ['Рост', data.height ?? DASH],
    ['Вес', data.weight ?? DASH],
    ['Дата регистрации', formatRegisteredAt(data.registeredAt)],
    ['В Скитальцах с', formatTenure(data, currentGameYear)],
  ];
  const left = 80;
  const right = W - 80;
  let y = 700;
  rows.forEach(([label, value]) => {
    ctx.textAlign = 'left';
    ctx.fillStyle = FAINT;
    ctx.font = `bold 24px ${SERIF}`;
    ctx.letterSpacing = '2px';
    ctx.fillText(label.toUpperCase(), left, y);
    ctx.letterSpacing = '0px';
    const labelEnd = left + ctx.measureText(label.toUpperCase()).width + label.length * 2 + 16;
    ctx.textAlign = 'right';
    ctx.fillStyle = INK;
    fitText(ctx, value, '', 32, right - labelEnd - 10);
    ctx.fillText(value, right, y);
    ctx.strokeStyle = 'rgba(47,36,22,0.3)';
    ctx.setLineDash([3, 6]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(left, y + 14);
    ctx.lineTo(right, y + 14);
    ctx.stroke();
    ctx.setLineDash([]);
    y += 50;
  });

  // The registrar's hand at the foot, the seal beside it.
  ctx.textAlign = 'left';
  ctx.fillStyle = FAINT;
  ctx.font = `italic 26px ${SERIF}`;
  ctx.fillText('Подпись регистратора', left, 1270);
  ctx.strokeStyle = 'rgba(30,26,60,0.85)';
  ctx.lineWidth = 2.4;
  ctx.lineCap = 'round';
  scrawl(ctx, rand, left + 10, left + 330, 1236);
  ctx.beginPath();
  ctx.moveTo(left, 1246);
  ctx.quadraticCurveTo(left + 200, 1256, left + 380, 1238);
  ctx.stroke();

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 16;
  return texture;
};

/** The wax seal's face: «СК» pressed into it. */
export const createSealFaceTexture = () => {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  const g = ctx.createRadialGradient(100, 90, 10, 128, 128, 128);
  g.addColorStop(0, '#a52a2a');
  g.addColorStop(0.5, '#8b1a1a');
  g.addColorStop(1, '#5e0e0e');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 256);
  ctx.strokeStyle = 'rgba(40,0,0,0.6)';
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.arc(128, 128, 92, 0, Math.PI * 2);
  ctx.stroke();
  ctx.font = `bold 92px "MedievalSharp", ${SERIF}`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(40,0,0,0.65)';
  ctx.fillText('СК', 131, 133);
  ctx.fillStyle = '#e8b8a0';
  ctx.globalAlpha = 0.55;
  ctx.fillText('СК', 128, 129);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
};
