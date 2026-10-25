import * as THREE from 'three';

/*
  Textures for the 3D minigames, painted on canvases (no image files): old
  door planks, forged iron with rust, brushed brass. Each is made once and
  shared by every game that wants it.
*/

const rng = (seed: number) => {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
};

const canvasTexture = (size: number, paint: (ctx: CanvasRenderingContext2D, rand: () => number) => void, seed = 1) => {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  paint(ctx, rng(seed));
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  return texture;
};

/** Specks of a colour scattered over the whole canvas. */
const speckle = (ctx: CanvasRenderingContext2D, rand: () => number, size: number, count: number, colour: string, max = 2) => {
  ctx.fillStyle = colour;
  for (let i = 0; i < count; i++) {
    const r = 0.3 + rand() * max;
    ctx.globalAlpha = 0.15 + rand() * 0.35;
    ctx.beginPath();
    ctx.arc(rand() * size, rand() * size, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
};

const cache = new Map<string, THREE.Texture>();
const once = (key: string, make: () => THREE.Texture) => {
  if (!cache.has(key)) cache.set(key, make());
  return cache.get(key)!;
};

/** Dark old planks running up and down, with grain, knots and gaps. */
export const doorPlanksTexture = () =>
  once('planks', () =>
    canvasTexture(
      512,
      (ctx, rand) => {
        const planks = 5;
        const w = 512 / planks;
        for (let p = 0; p < planks; p++) {
          const tone = 30 + rand() * 14;
          ctx.fillStyle = `rgb(${tone + 22}, ${tone + 8}, ${tone - 4})`;
          ctx.fillRect(p * w, 0, w, 512);
          // Grain: long wavy streaks.
          for (let g = 0; g < 26; g++) {
            const x0 = p * w + rand() * w;
            ctx.strokeStyle = rand() < 0.5 ? 'rgba(0,0,0,0.25)' : 'rgba(120,80,50,0.12)';
            ctx.lineWidth = 0.6 + rand() * 1.4;
            ctx.beginPath();
            ctx.moveTo(x0, 0);
            for (let y = 0; y <= 512; y += 32) ctx.lineTo(x0 + Math.sin(y * 0.02 + g) * (2 + rand() * 3), y);
            ctx.stroke();
          }
          // A knot or two.
          for (let k = 0; k < 1 + Math.floor(rand() * 2); k++) {
            const kx = p * w + w * (0.25 + rand() * 0.5);
            const ky = rand() * 512;
            for (let r = 9; r > 0; r -= 2) {
              ctx.strokeStyle = `rgba(20,10,4,${0.12 + (9 - r) * 0.04})`;
              ctx.lineWidth = 1.2;
              ctx.beginPath();
              ctx.ellipse(kx, ky, r * 0.7, r * 1.6, 0, 0, Math.PI * 2);
              ctx.stroke();
            }
          }
          // The gap to the next plank.
          ctx.fillStyle = 'rgba(0,0,0,0.85)';
          ctx.fillRect(p * w + w - 3, 0, 3, 512);
          ctx.fillStyle = 'rgba(255,220,180,0.05)';
          ctx.fillRect(p * w, 0, 2, 512);
        }
        speckle(ctx, rand, 512, 900, '#000', 1.6);
      },
      7,
    ),
  );

/** Forged iron: dark, hammered, with blooms of rust. */
export const ironTexture = () =>
  once('iron', () =>
    canvasTexture(
      256,
      (ctx, rand) => {
        ctx.fillStyle = '#3b3b40';
        ctx.fillRect(0, 0, 256, 256);
        // Hammer marks: soft light and dark dents.
        for (let i = 0; i < 160; i++) {
          const x = rand() * 256;
          const y = rand() * 256;
          const r = 4 + rand() * 12;
          const g = ctx.createRadialGradient(x, y, 0, x, y, r);
          const light = rand() < 0.5;
          g.addColorStop(0, light ? 'rgba(150,150,160,0.10)' : 'rgba(0,0,0,0.18)');
          g.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.fillStyle = g;
          ctx.fillRect(x - r, y - r, r * 2, r * 2);
        }
        // Rust blooms.
        for (let i = 0; i < 14; i++) {
          const x = rand() * 256;
          const y = rand() * 256;
          const r = 6 + rand() * 22;
          const g = ctx.createRadialGradient(x, y, 0, x, y, r);
          g.addColorStop(0, 'rgba(110,60,30,0.35)');
          g.addColorStop(0.6, 'rgba(80,44,22,0.15)');
          g.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.fillStyle = g;
          ctx.fillRect(x - r, y - r, r * 2, r * 2);
        }
        speckle(ctx, rand, 256, 600, '#140c08', 1.2);
        speckle(ctx, rand, 256, 200, '#a0a0aa', 0.8);
      },
      3,
    ),
  );

/** Brushed brass: warm, with fine streaks along its length. */
export const brassTexture = () =>
  once('brass', () =>
    canvasTexture(
      256,
      (ctx, rand) => {
        ctx.fillStyle = '#ad9562';
        ctx.fillRect(0, 0, 256, 256);
        for (let i = 0; i < 420; i++) {
          const y = rand() * 256;
          ctx.strokeStyle = rand() < 0.5 ? 'rgba(255,240,200,0.07)' : 'rgba(60,40,10,0.07)';
          ctx.lineWidth = 0.5 + rand();
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(256, y + (rand() - 0.5) * 4);
          ctx.stroke();
        }
        speckle(ctx, rand, 256, 120, '#3a2808', 1.5);
      },
      5,
    ),
  );

/** A soft round glow for additive sprites (sparks, the candle's halo). */
export const glowTexture = () =>
  once('glow', () =>
    canvasTexture(64, (ctx) => {
      const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
      g.addColorStop(0, 'rgba(255,255,255,1)');
      g.addColorStop(0.25, 'rgba(255,255,255,0.6)');
      g.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 64, 64);
    }),
  );

/** Grey granite: speckled, with a few hairline cracks. */
export const stoneTexture = () =>
  once('stone', () =>
    canvasTexture(
      256,
      (ctx, rand) => {
        ctx.fillStyle = '#6a6762';
        ctx.fillRect(0, 0, 256, 256);
        for (let i = 0; i < 90; i++) {
          const x = rand() * 256;
          const y = rand() * 256;
          const r = 6 + rand() * 26;
          const g = ctx.createRadialGradient(x, y, 0, x, y, r);
          const light = rand() < 0.5;
          g.addColorStop(0, light ? 'rgba(170,165,155,0.18)' : 'rgba(20,18,16,0.2)');
          g.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.fillStyle = g;
          ctx.fillRect(x - r, y - r, r * 2, r * 2);
        }
        speckle(ctx, rand, 256, 1400, '#1c1a18', 1.1);
        speckle(ctx, rand, 256, 600, '#b8b2a6', 0.9);
        ctx.strokeStyle = 'rgba(15,12,10,0.45)';
        ctx.lineWidth = 0.8;
        for (let c = 0; c < 4; c++) {
          let x = rand() * 256;
          let y = rand() * 256;
          ctx.beginPath();
          ctx.moveTo(x, y);
          for (let k = 0; k < 6; k++) {
            x += (rand() - 0.5) * 40;
            y += (rand() - 0.5) * 40;
            ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
      },
      11,
    ),
  );

/**
 * The nine runes of the illusory wall (Elder Futhark, all straight strokes),
 * as segments in a unit square, y down.
 */
const RUNE_STROKES: [number, number, number, number][][] = [
  // ᚠ fehu
  [[0.32, 0.08, 0.32, 0.92], [0.32, 0.38, 0.7, 0.12], [0.32, 0.62, 0.7, 0.36]],
  // ᚢ uruz
  [[0.3, 0.92, 0.3, 0.08], [0.3, 0.08, 0.7, 0.34], [0.7, 0.34, 0.7, 0.92]],
  // ᚦ thurisaz
  [[0.35, 0.08, 0.35, 0.92], [0.35, 0.3, 0.7, 0.5], [0.7, 0.5, 0.35, 0.7]],
  // ᚨ ansuz
  [[0.32, 0.08, 0.32, 0.92], [0.32, 0.1, 0.7, 0.32], [0.32, 0.36, 0.7, 0.58]],
  // ᚱ raido
  [[0.32, 0.08, 0.32, 0.92], [0.32, 0.08, 0.7, 0.28], [0.7, 0.28, 0.32, 0.5], [0.32, 0.5, 0.7, 0.92]],
  // ᚲ kaunan
  [[0.66, 0.16, 0.34, 0.42], [0.34, 0.42, 0.66, 0.68]],
  // ᚷ gebo
  [[0.25, 0.12, 0.75, 0.88], [0.75, 0.12, 0.25, 0.88]],
  // ᚹ wunjo
  [[0.32, 0.08, 0.32, 0.92], [0.32, 0.08, 0.7, 0.28], [0.7, 0.28, 0.32, 0.5]],
  // ᚺ hagalaz
  [[0.3, 0.08, 0.3, 0.92], [0.7, 0.08, 0.7, 0.92], [0.3, 0.34, 0.7, 0.6]],
];

const strokeRune = (ctx: CanvasRenderingContext2D, glyph: number, size: number, colour: string, width: number) => {
  ctx.strokeStyle = colour;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  for (const [x1, y1, x2, y2] of RUNE_STROKES[glyph % RUNE_STROKES.length]) {
    ctx.beginPath();
    ctx.moveTo(x1 * size, y1 * size);
    ctx.lineTo(x2 * size, y2 * size);
    ctx.stroke();
  }
};

/** A rune cut into stone: the groove for a bump map (dark in light) and its glow (light in dark). */
export const runeTextures = (glyph: number) => ({
  // The cut itself, on a clear ground: a soft dark rim, a darker groove, a pale lip catching the light.
  groove: once(`rune-groove-${glyph}`, () =>
    canvasTexture(128, (ctx) => {
      ctx.clearRect(0, 0, 128, 128);
      strokeRune(ctx, glyph, 128, 'rgba(20,16,14,0.45)', 15);
      ctx.save();
      ctx.translate(-1.5, -1.5);
      strokeRune(ctx, glyph, 128, 'rgba(230,220,200,0.35)', 9);
      ctx.restore();
      strokeRune(ctx, glyph, 128, 'rgba(12,10,9,0.95)', 8);
    }),
  ),
  glow: once(`rune-glow-${glyph}`, () =>
    canvasTexture(128, (ctx) => {
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, 128, 128);
      ctx.shadowColor = '#fff';
      ctx.shadowBlur = 10;
      strokeRune(ctx, glyph, 128, '#fff', 7);
    }),
  ),
});

/** A figure cut into stone and glowing (white on black, for an emissive map); "✦" for the find. */
export const markTexture = (mark: string) =>
  once(`mark-${mark}`, () =>
    canvasTexture(128, (ctx) => {
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, 128, 128);
      ctx.fillStyle = '#fff';
      ctx.shadowColor = '#fff';
      ctx.shadowBlur = 12;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.font = 'bold 84px Georgia, "Times New Roman", serif';
      ctx.fillText(mark, 64, 70);
    }),
  );

/** Scuff marks dragged one way: an arrow of scratches, white on black (for a glow), pointing up. */
export const tracesTexture = () =>
  once('traces', () =>
    canvasTexture(128, (ctx, rand) => {
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, 128, 128);
      ctx.strokeStyle = '#fff';
      ctx.lineCap = 'round';
      ctx.shadowColor = '#fff';
      ctx.shadowBlur = 6;
      // Long drag marks converging upwards.
      for (let i = 0; i < 5; i++) {
        const x = 44 + i * 10 + (rand() - 0.5) * 4;
        ctx.lineWidth = 2 + rand() * 2;
        ctx.globalAlpha = 0.6 + rand() * 0.4;
        ctx.beginPath();
        ctx.moveTo(x, 112);
        ctx.lineTo(64 + (x - 64) * 0.35, 30);
        ctx.stroke();
      }
      // The head of the arrow.
      ctx.globalAlpha = 1;
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.moveTo(38, 46);
      ctx.lineTo(64, 16);
      ctx.lineTo(90, 46);
      ctx.stroke();
    }, 13),
  );
