import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { ownerKey, SQUARE, type DioramaLayout } from './dioramaLayout';
import type { BoardDungeon } from './boardTypes';

/*
  Fog of war on the cloth: everything the party hasn't opened up lies in
  shadow, and the built rooms and corridors stand in soft pools of light. The
  board's edges fade into the same dusk, so the known dungeon reads as an
  island on the table.
*/

/** Canvas pixels per world unit, and the largest side the mask may take. */
const PX_PER_UNIT = 40;
const MAX_SIDE = 2048;
/** How dark the unknown is, and how far light spills round a built square. */
const SHADE = 0.5;
const LIGHT_RADIUS = SQUARE * 3;

interface BoardFogProps {
  dungeon: BoardDungeon;
  layout: DioramaLayout;
  revealed: Set<number>;
  width: number;
  depth: number;
  /** Height of the board's surface: the fog lies just on it, under the miniature. */
  y: number;
  /** The middle of the area it covers (the layout's centre unless given). */
  center?: [number, number];
}

const BoardFog = ({ dungeon, layout, revealed, width, depth, y, center: given }: BoardFogProps) => {
  const center = given ?? layout.center;
  // Redrawn only when what is built changes.
  const builtKey = useMemo(() => [...revealed].sort((a, b) => a - b).join(','), [revealed]);

  const textures = useMemo(() => {
    const scale = Math.min(PX_PER_UNIT, MAX_SIDE / Math.max(width, depth));
    const w = Math.max(16, Math.round(width * scale));
    const h = Math.max(16, Math.round(depth * scale));
    const left = center[0] - width / 2;
    const top = center[1] - depth / 2;
    const r = LIGHT_RADIUS * scale;

    // Every built square, in canvas pixels.
    const lit: [number, number][] = [];
    const add = (key: string) =>
      layout.pieces.get(key)?.floor.forEach((f) => lit.push([(f.x - left) * scale, (f.z - top) * scale]));
    dungeon.rooms.filter((room) => revealed.has(room.id)).forEach((room) => add(ownerKey({ kind: 'room', id: room.id })));
    dungeon.corridors
      .filter((c) => revealed.has(c.from) || revealed.has(c.to))
      .forEach((c) => add(ownerKey({ kind: 'corridor', key: `${Math.min(c.from, c.to)}-${Math.max(c.from, c.to)}` })));

    const draw = (paint: (ctx: CanvasRenderingContext2D) => void) => {
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;
      paint(ctx);
      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      return tex;
    };
    const pool = (ctx: CanvasRenderingContext2D, x: number, y: number, stops: [number, string][]) => {
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      stops.forEach(([at, colour]) => g.addColorStop(at, colour));
      ctx.fillStyle = g;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    };

    // Dusk over everything, cleared round what is built.
    const shade = draw((ctx) => {
      ctx.fillStyle = `rgba(0, 0, 0, ${SHADE})`;
      ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = 'destination-out';
      lit.forEach(([x, y]) =>
        pool(ctx, x, y, [
          [0, 'rgba(0,0,0,0.35)'],
          [0.5, 'rgba(0,0,0,0.18)'],
          [1, 'rgba(0,0,0,0)'],
        ]),
      );
    });
    // Warm light pooled on the cloth under the built part.
    const warmth = draw((ctx) => {
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = 'lighter';
      lit.forEach(([x, y]) =>
        pool(ctx, x, y, [
          [0, 'rgba(255,190,120,0.09)'],
          [1, 'rgba(255,190,120,0)'],
        ]),
      );
    });
    return { shade, warmth };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, builtKey, width, depth, center[0], center[1]]);
  useEffect(
    () => () => {
      textures.shade?.dispose();
      textures.warmth?.dispose();
    },
    [textures],
  );

  return (
    <group position={[center[0], y, center[1]]} rotation={[-Math.PI / 2, 0, 0]}>
      {textures.warmth && (
        <mesh renderOrder={1}>
          <planeGeometry args={[width, depth]} />
          <meshBasicMaterial
            map={textures.warmth}
            transparent
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </mesh>
      )}
      {textures.shade && (
        <mesh renderOrder={1} position={[0, 0, 0.001]}>
          <planeGeometry args={[width, depth]} />
          <meshBasicMaterial map={textures.shade} transparent depthWrite={false} toneMapped={false} />
        </mesh>
      )}
    </group>
  );
};

export default BoardFog;
