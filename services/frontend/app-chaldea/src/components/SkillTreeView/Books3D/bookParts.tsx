import { createContext, useContext, useMemo, useRef, useEffect, type MutableRefObject, type ReactNode } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { BookBinding } from './bookTextures';

/*
  What every book is built from, shared by the common frame in Book and the
  dressing each class adds on top of it.
*/

/** Width of one page, world units. */
export const PAGE_WIDTH = 3;

/** How a class's book is proportioned. */
export interface BookForm {
  /** Thickness of each board. */
  cover: number;
  /** How far the boards stand proud of the pages. */
  overhang: number;
  /** Height of each half of the page block. */
  halfBlock: number;
  /** Page edges gilded instead of plain paper. */
  gilded: boolean;
}

/* DB class ids: 1=Warrior, 2=Rogue, 3=Mage */
export const FORMS: Record<number, BookForm> = {
  // Heavy wooden boards under the leather, set well proud of a fat block.
  1: { cover: 0.17, overhang: 0.14, halfBlock: 0.26, gilded: false },
  // A soft journal: thin limp leather hugging the pages.
  2: { cover: 0.045, overhang: 0.05, halfBlock: 0.2, gilded: false },
  // A slim, fine volume with gilt edges.
  3: { cover: 0.06, overhang: 0.08, halfBlock: 0.18, gilded: true },
};
export const DEFAULT_FORM = FORMS[1];


/** The book's measurements, worked out from its form. */
export interface BookFrame {
  pageWidth: number;
  pageDepth: number;
  cover: number;
  halfBlock: number;
  boardWidth: number;
  boardDepth: number;
  /** Where the spine hinge sits: the top of the lower half of the pages. */
  hingeY: number;
  /** Height of the closed book from the table to the top of its front board. */
  closedHeight: number;
}

export const frameOf = (form: BookForm, pageDepth: number): BookFrame => {
  const hingeY = form.cover + form.halfBlock;
  return {
    pageWidth: PAGE_WIDTH,
    pageDepth,
    cover: form.cover,
    halfBlock: form.halfBlock,
    boardWidth: PAGE_WIDTH + form.overhang,
    boardDepth: pageDepth + form.overhang * 2,
    hingeY,
    closedHeight: hingeY * 2,
  };
};

/** Widest any open book gets, for framing the camera. */
export const MAX_OVERHANG = Math.max(...Object.values(FORMS).map((f) => f.overhang));

/** How far through opening the book is: the fastening first, then the cover. */
export interface BookProgress {
  /** 0 fastened .. 1 undone. */
  fastening: number;
  /** 0 shut .. 1 lying open. */
  cover: number;
}

/** What each piece of class dressing is handed. */
export interface DressingProps {
  frame: BookFrame;
  binding: BookBinding;
  progress: MutableRefObject<BookProgress>;
  /** The book's own leather, so straps and flaps match the binding. */
  leather: THREE.Material;
}

/**
 * For glows, motes and other effects that should never catch the pointer —
 * left raycastable, they sit in front of the nodes and swallow their clicks.
 */
export const noRaycast = () => null;

/** Disposes owned three.js resources when they change or the component goes. */
export const useDisposable = <T extends { dispose: () => void }>(make: () => T, deps: unknown[]): T => {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const value = useMemo(make, deps);
  useEffect(() => () => value.dispose(), [value]);
  return value;
};

interface FoldingStrapProps {
  /**
   * Where the strap is fixed: on the table at the outer face of the strap,
   * against the fore-edge — one strap thickness out from the boards.
   */
  anchor: [number, number, number];
  /** Height it climbs up the fore-edge: the closed book plus its own thickness. */
  height: number;
  /** How far it reaches back across the front board. */
  reach: number;
  /** Across the strap, along the spine. */
  width: number;
  thickness: number;
  material: THREE.Material;
  progress: MutableRefObject<BookProgress>;
  /** Fittings on the free end, placed from the tip of the strap, lying on the board. */
  children?: ReactNode;
}

/**
 * Reflections for metal only. A whole-scene environment map lit the leather,
 * the paper and the table as well and washed out the candlelight, so the map
 * is handed to the metal materials alone.
 */
export const MetalEnvContext = createContext<THREE.Texture | null>(null);

/** Applies the metal reflections to a material, once they exist. */
export const useMetalEnv = (material: THREE.MeshStandardMaterial) => {
  const env = useContext(MetalEnvContext);
  useEffect(() => {
    material.envMap = env;
    material.needsUpdate = true;
  }, [material, env]);
};

/** A plain metal material that picks up the metal reflections. */
export const useMetal = (color: string, roughness: number, metalness = 0.85) => {
  const material = useDisposable(() => new THREE.MeshStandardMaterial({ color, roughness, metalness }), [color, roughness, metalness]);
  useMetalEnv(material);
  return material;
};

/**
 * A strap, flap or hasp fixed to the back board that climbs the fore-edge and
 * reaches back across the front board. Undone, it unfolds at both bends and
 * lies out flat on the table.
 */
export const FoldingStrap = ({ anchor, height, reach, width, thickness, material, progress, children }: FoldingStrapProps) => {
  const rise = useRef<THREE.Group>(null);
  const flap = useRef<THREE.Group>(null);
  useFrame(() => {
    const k = progress.current.fastening;
    // Both bends straighten together: the riser drops outward onto the table,
    // and the end over the board swings round to carry on from it.
    if (rise.current) rise.current.rotation.z = (-k * Math.PI) / 2;
    if (flap.current) flap.current.rotation.z = (-k * Math.PI) / 2;
  });
  // Both pivots sit on the strap's outer corners, so once unfolded every part
  // of it lies on top of the table rather than sinking into it.
  return (
    <group ref={rise} position={anchor}>
      <mesh position={[-thickness / 2, height / 2, 0]} material={material} castShadow>
        <boxGeometry args={[thickness, height, width]} />
      </mesh>
      <group ref={flap} position={[0, height, 0]}>
        <mesh position={[-reach / 2, -thickness / 2, 0]} material={material} castShadow>
          <boxGeometry args={[reach, thickness, width]} />
        </mesh>
        <group position={[-reach, 0, 0]}>{children}</group>
      </group>
    </group>
  );
};

/**
 * A flat strip along a path, a fixed width across it, lying sideways along x:
 * bookmark ribbons, laces. Its face looks up wherever the path runs flat.
 */
export const createRibbonGeometry = (points: THREE.Vector3[], width: number) => {
  const positions: number[] = [];
  const uvs: number[] = [];
  const index: number[] = [];
  points.forEach((p, i) => {
    positions.push(p.x - width / 2, p.y, p.z, p.x + width / 2, p.y, p.z);
    const v = i / (points.length - 1);
    uvs.push(0, v, 1, v);
    if (i > 0) {
      const a = (i - 1) * 2;
      index.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(index);
  geometry.computeVertexNormals();
  return geometry;
};

/** A dome-headed rivet, sitting on a surface at the given point. */
export const Rivet = ({ position, radius = 0.045, material }: { position: [number, number, number]; radius?: number; material: THREE.Material }) => (
  <mesh position={position} scale={[1, 0.55, 1]} material={material}>
    <sphereGeometry args={[radius, 10, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
  </mesh>
);
