import * as THREE from 'three';
import { makeCanvas, mulberry32, speckle, toTexture } from '../pages/BattlePage/Arena3D/textures';

/*
  Small canvas textures for the dungeon miniature: the reach ring, door planks,
  chalk and mist. Everything is drawn on a canvas, like the arena's textures,
  so nothing remote is sampled by WebGL.
*/

/** A soft ring of light under the tiles the party can walk to. */
export const createReachRingTexture = () => {
  const { canvas, ctx } = makeCanvas(128);
  const g = ctx.createRadialGradient(64, 64, 34, 64, 64, 62);
  g.addColorStop(0, 'rgba(255,220,140,0)');
  g.addColorStop(0.7, 'rgba(255,220,140,0.85)');
  g.addColorStop(1, 'rgba(255,220,140,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  return toTexture(canvas);
};

/** Oak planks for the dungeon doors: four boards, grain, dark seams. */
export const createDoorWoodTexture = () => {
  const rand = mulberry32(4242);
  const { canvas, ctx } = makeCanvas(128);
  const boards = 4;
  const w = 128 / boards;
  for (let b = 0; b < boards; b++) {
    const shade = 70 + Math.floor(rand() * 26);
    ctx.fillStyle = `rgb(${shade + 26}, ${shade}, ${Math.floor(shade * 0.62)})`;
    ctx.fillRect(b * w, 0, w, 128);
    for (let i = 0; i < 9; i++) {
      ctx.strokeStyle = `rgba(30, 16, 6, ${0.18 + rand() * 0.22})`;
      ctx.lineWidth = 0.6 + rand();
      const x = b * w + 3 + rand() * (w - 6);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.bezierCurveTo(x + rand() * 4 - 2, 40, x + rand() * 4 - 2, 88, x + rand() * 3 - 1.5, 128);
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(15, 8, 3, 0.85)';
    ctx.fillRect(b * w, 0, 1.5, 128);
  }
  speckle(ctx, 128, rand, 160);
  return toTexture(canvas);
};

/** A chalk stroke, repeated along the outline of a room the map already knows. */
export const createChalkTexture = () => {
  const rand = mulberry32(77);
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 16;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  for (let i = 0; i < 900; i++) {
    const x = rand() * 256;
    const y = 8 + (rand() + rand() + rand() - 1.5) * 4;
    ctx.fillStyle = `rgba(240, 236, 222, ${0.25 + rand() * 0.6})`;
    ctx.fillRect(x, y, 1 + rand() * 3, 1 + rand() * 1.5);
  }
  const tex = toTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  return tex;
};

/** A ragged wisp of mist: many soft blots under one round fall-off. */
export const createMistTexture = () => {
  const rand = mulberry32(1313);
  const { canvas, ctx } = makeCanvas(128);
  for (let i = 0; i < 46; i++) {
    const a = rand() * Math.PI * 2;
    const d = Math.sqrt(rand()) * 40;
    const x = 64 + Math.cos(a) * d;
    const y = 64 + Math.sin(a) * d;
    const r = 10 + rand() * 22;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `rgba(255,255,255,${0.12 + rand() * 0.14})`);
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
  }
  // Soften the edge so a wisp never ends in a hard circle.
  ctx.globalCompositeOperation = 'destination-in';
  const edge = ctx.createRadialGradient(64, 64, 20, 64, 64, 64);
  edge.addColorStop(0, 'rgba(0,0,0,1)');
  edge.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = edge;
  ctx.fillRect(0, 0, 128, 128);
  return toTexture(canvas);
};

export const disposeAll = (textures: THREE.Texture[]) => textures.forEach((t) => t.dispose());
