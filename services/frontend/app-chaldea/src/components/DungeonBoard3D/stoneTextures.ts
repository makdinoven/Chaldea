import { makeCanvas, mulberry32, toTexture } from '../pages/BattlePage/Arena3D/textures';

/*
  Painted-resin stone for the miniature: grey flagstones for the floor and
  rough courses of blocks for the walls, drawn on canvases like every other
  texture on the table.
*/

const SIZE = 128;

const stoneShade = (rand: () => number, base: number, spread: number) => {
  const v = Math.round(base + (rand() - 0.5) * spread);
  return `rgb(${v},${v},${Math.min(255, v + 4)})`;
};

/** One floor square: four worn flagstones with dark grout and a few cracks. */
export const createFlagstoneTexture = () => {
  const rand = mulberry32(1301);
  const { canvas, ctx } = makeCanvas(SIZE);
  ctx.fillStyle = '#2b2a2c';
  ctx.fillRect(0, 0, SIZE, SIZE);
  const half = SIZE / 2;
  for (let i = 0; i < 2; i++) {
    for (let j = 0; j < 2; j++) {
      ctx.fillStyle = stoneShade(rand, 128, 34);
      ctx.fillRect(i * half + 3, j * half + 3, half - 6, half - 6);
      // Mottling inside each slab.
      for (let k = 0; k < 40; k++) {
        ctx.fillStyle = `rgba(${rand() > 0.5 ? '255,255,255' : '0,0,0'},${0.04 + rand() * 0.06})`;
        ctx.fillRect(i * half + 4 + rand() * (half - 12), j * half + 4 + rand() * (half - 12), 2 + rand() * 6, 2 + rand() * 6);
      }
    }
  }
  ctx.strokeStyle = 'rgba(20,20,22,0.7)';
  ctx.lineWidth = 1.2;
  for (let c = 0; c < 3; c++) {
    let x = rand() * SIZE;
    let y = rand() * SIZE;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let s = 0; s < 4; s++) {
      x += (rand() - 0.5) * 22;
      y += (rand() - 0.5) * 22;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  return toTexture(canvas);
};

/** A wall section: staggered courses of rough-cut blocks with deep mortar lines. */
export const createWallBlockTexture = () => {
  const rand = mulberry32(1409);
  const { canvas, ctx } = makeCanvas(SIZE);
  ctx.fillStyle = '#262528';
  ctx.fillRect(0, 0, SIZE, SIZE);
  const courses = 5;
  const h = SIZE / courses;
  for (let row = 0; row < courses; row++) {
    let x = row % 2 ? -SIZE / 6 : 0;
    while (x < SIZE) {
      const w = SIZE / 3 + (rand() - 0.5) * 14;
      ctx.fillStyle = stoneShade(rand, 118, 40);
      ctx.fillRect(x + 2, row * h + 2, w - 4, h - 4);
      // Light top edge and dark bottom edge: chiselled faces catching the light.
      ctx.fillStyle = 'rgba(255,255,255,0.08)';
      ctx.fillRect(x + 2, row * h + 2, w - 4, 2);
      ctx.fillStyle = 'rgba(0,0,0,0.25)';
      ctx.fillRect(x + 2, row * h + h - 4, w - 4, 2);
      x += w;
    }
  }
  return toTexture(canvas);
};
