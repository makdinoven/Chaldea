import { useEffect, useMemo } from 'react';
import type { ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';
import { createRibbonGeometry, type BookFrame } from './bookParts';

/*
  A silk ribbon marking the subclass chapter of a class's book: it comes out
  between the pages at the head and trails over the table, the chapter's name
  embroidered down it in gold. Touching it turns the book to the chapter, or
  back.
*/

/** Width of the ribbon across, world units. */
const WIDTH = 0.3;
/** How far along the right-hand page, from the spine, it comes out. */
const ALONG = 0.72;
/** Height a ribbon lying on the table floats above it. */
const LIFT = 0.012;

const TEX_W = 128;
const TEX_H = 1024;

/** Silk in the class's colour, a forked end, and the name stitched along it. Canvas top is the free end. */
const createRibbonTexture = (colour: string, label: string) => {
  const canvas = document.createElement('canvas');
  canvas.width = TEX_W;
  canvas.height = TEX_H;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');

  // The swallowtail: everything outside it stays transparent.
  ctx.beginPath();
  ctx.moveTo(0, TEX_H);
  ctx.lineTo(0, 0);
  ctx.lineTo(TEX_W / 2, 70);
  ctx.lineTo(TEX_W, 0);
  ctx.lineTo(TEX_W, TEX_H);
  ctx.closePath();
  ctx.fillStyle = colour;
  ctx.fill();
  ctx.save();
  ctx.clip();
  // Sheen across the silk, and fine threads along it.
  const sheen = ctx.createLinearGradient(0, 0, TEX_W, 0);
  sheen.addColorStop(0, 'rgba(0,0,0,0.35)');
  sheen.addColorStop(0.45, 'rgba(255,255,255,0.18)');
  sheen.addColorStop(1, 'rgba(0,0,0,0.4)');
  ctx.fillStyle = sheen;
  ctx.fillRect(0, 0, TEX_W, TEX_H);
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  for (let x = 4; x < TEX_W; x += 6) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, TEX_H);
    ctx.stroke();
  }
  // Gold edging
  ctx.strokeStyle = '#d9ab55';
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(10, TEX_H);
  ctx.lineTo(10, 40);
  ctx.moveTo(TEX_W - 10, TEX_H);
  ctx.lineTo(TEX_W - 10, 40);
  ctx.stroke();
  ctx.restore();

  // The name, stitched to read from the book outward, toward the free end:
  // the part nearest the book lies under the pages' edge.
  ctx.save();
  ctx.translate(TEX_W / 2 + 14, TEX_H * 0.33);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.font = 'bold 54px serif';
  ctx.fillStyle = 'rgba(0,0,0,0.5)';
  ctx.fillText(label.toUpperCase(), 2, 3);
  ctx.fillStyle = '#f0cf7a';
  ctx.fillText(label.toUpperCase(), 0, 0);
  ctx.restore();

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
};

interface ChapterRibbonProps {
  frame: BookFrame;
  colour: string;
  label: string;
  onToggle: () => void;
}

const ChapterRibbon = ({ frame, colour, label, onToggle }: ChapterRibbonProps) => {
  const { hingeY, pageWidth, pageDepth } = frame;
  const head = -pageDepth / 2;
  const x = pageWidth * ALONG;

  const geometry = useMemo(() => {
    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(x, hingeY - 0.03, head + 0.1),
      new THREE.Vector3(x, hingeY - 0.03, head - 0.02),
      new THREE.Vector3(x + 0.02, hingeY * 0.5, head - 0.18),
      new THREE.Vector3(x + 0.06, LIFT, head - 0.5),
      new THREE.Vector3(x + 0.18, LIFT, head - 1.55),
    ]);
    // Kept above the table where the smoothed curve would dip into it.
    const points = curve.getPoints(40).map((p) => p.setY(Math.max(p.y, LIFT)));
    return createRibbonGeometry(points, WIDTH);
  }, [x, hingeY, head]);
  useEffect(() => () => geometry.dispose(), [geometry]);

  const texture = useMemo(() => createRibbonTexture(colour, label), [colour, label]);
  useEffect(() => () => texture.dispose(), [texture]);

  return (
    <mesh
      geometry={geometry}
      castShadow
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation();
        if (e.delta <= 8) onToggle();
      }}
      onPointerOver={(e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation();
        document.body.style.cursor = 'pointer';
      }}
      onPointerOut={() => {
        document.body.style.cursor = '';
      }}
    >
      <meshStandardMaterial map={texture} roughness={0.45} metalness={0.15} side={THREE.DoubleSide} alphaTest={0.5} />
    </mesh>
  );
};

export default ChapterRibbon;
