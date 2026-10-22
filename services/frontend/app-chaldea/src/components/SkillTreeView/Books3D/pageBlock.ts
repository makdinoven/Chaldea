import * as THREE from 'three';

/*
  Half of a book's pages as one slab whose top face is the page. Flat while the
  book is shut; as it opens the page bows the way a real one does: it dives
  into the binding at the gutter, rises in a hump just off it, and runs gently
  down to the fore-edge.

  Built in its own frame: gutter at x = 0, fore-edge at x = width, the back of
  the slab at y = 0 and the page on top, head of the page at -z. Group 0 is the
  page, group 1 the edges of the paper.
*/

/** Strips across the page; spaced finer near the gutter, where the bend is sharpest. */
const SEGMENTS = 40;
/** How strongly the strips crowd toward the gutter. */
const GUTTER_CROWDING = 1.7;

/** The bow of an open page, in world units above the flat slab, by share of the width. */
const DIP = 0.15;
const HUMP = 0.2;
const RISE = 13;
const FALL = 0.12;
/** Height of a fully bowed page above the flat slab, at a share u of the way from gutter to fore-edge. */
export const pageBow = (u: number) => {
  const k = Math.exp(-u * RISE);
  return HUMP * (1 - k) - DIP * k - FALL * u;
};

export interface PageBlockShape {
  width: number;
  depth: number;
  /** Thickness of the slab where the page lies flat. */
  height: number;
  /**
   * The page is seen from the other side of the slab (the half that turns over
   * on the spine): its picture is flipped across so it reads right once turned.
   */
  mirrored: boolean;
}

/** Vertices per strip line on the page face and on each wall. */
const ROWS = 2;

/**
 * Fills in every vertex for a given bend, 0 (flat) .. 1 (fully bowed).
 *
 * Layout: page face, back face, head wall, tail wall — each (SEGMENTS + 1) × 2
 * vertices — then the fore-edge and gutter walls, four vertices each.
 */
const writePositions = (positions: Float32Array, xs: number[], shape: PageBlockShape, bend: number) => {
  const { width, depth, height } = shape;
  const half = depth / 2;
  const top = xs.map((x) => height + bend * pageBow(x / width));
  let p = 0;
  const put = (x: number, y: number, z: number) => {
    positions[p++] = x;
    positions[p++] = y;
    positions[p++] = z;
  };
  // Page face, back face
  xs.forEach((x, i) => {
    put(x, top[i], -half);
    put(x, top[i], half);
  });
  xs.forEach((x) => {
    put(x, 0, -half);
    put(x, 0, half);
  });
  // Head (far) and tail (near) walls: bottom and top of each strip line
  for (const z of [-half, half]) {
    xs.forEach((x, i) => {
      put(x, 0, z);
      put(x, top[i], z);
    });
  }
  // Fore-edge and gutter walls
  const last = xs.length - 1;
  for (const [x, t] of [
    [xs[last], top[last]],
    [xs[0], top[0]],
  ]) {
    put(x, 0, -half);
    put(x, 0, half);
    put(x, t, -half);
    put(x, t, half);
  }
};

export const createPageBlockGeometry = (shape: PageBlockShape) => {
  const { width, mirrored } = shape;
  const xs = Array.from({ length: SEGMENTS + 1 }, (_, i) => width * Math.pow(i / SEGMENTS, GUTTER_CROWDING));
  const n = xs.length;
  const vertexCount = n * ROWS * 4 + 8;

  const positions = new Float32Array(vertexCount * 3);
  writePositions(positions, xs, shape, 0);

  // UVs. The page carries its picture, head at the top of the texture. The
  // paper edges run the edge texture's lines along the slab, one per sheet.
  const uvs: number[] = [];
  xs.forEach((x) => {
    const u = mirrored ? 1 - x / width : x / width;
    uvs.push(u, 1, u, 0);
  });
  xs.forEach((x) => uvs.push(x / width, 0, x / width, 1));
  for (let w = 0; w < 2; w++) xs.forEach((x) => uvs.push(x / width, 0, x / width, 1));
  for (let w = 0; w < 2; w++) uvs.push(0, 0, 1, 0, 0, 1, 1, 1);

  const index: number[] = [];
  const faceStart = 0;
  const backStart = n * ROWS;
  const headStart = n * ROWS * 2;
  const tailStart = n * ROWS * 3;
  const foreStart = n * ROWS * 4;
  const gutterStart = foreStart + 4;

  // Page face, facing up
  for (let i = 0; i < n - 1; i++) {
    const a = faceStart + i * 2;
    index.push(a, a + 1, a + 2, a + 2, a + 1, a + 3);
  }
  const pageCount = index.length;
  // Back face, facing down
  for (let i = 0; i < n - 1; i++) {
    const a = backStart + i * 2;
    index.push(a, a + 2, a + 1, a + 2, a + 3, a + 1);
  }
  // Head wall faces -z, tail wall faces +z
  for (let i = 0; i < n - 1; i++) {
    const h = headStart + i * 2;
    index.push(h, h + 1, h + 2, h + 2, h + 1, h + 3);
    const t = tailStart + i * 2;
    index.push(t, t + 2, t + 1, t + 2, t + 3, t + 1);
  }
  // Fore-edge faces +x, gutter faces -x
  index.push(foreStart, foreStart + 2, foreStart + 1, foreStart + 1, foreStart + 2, foreStart + 3);
  index.push(gutterStart, gutterStart + 1, gutterStart + 2, gutterStart + 1, gutterStart + 3, gutterStart + 2);

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(index);
  geometry.addGroup(0, pageCount, 0);
  geometry.addGroup(pageCount, index.length - pageCount, 1);
  geometry.computeVertexNormals();

  let lastBend = 0;
  /** Bows the page to the given bend; does nothing when it hasn't changed. */
  const setBend = (bend: number) => {
    if (Math.abs(bend - lastBend) < 1e-4) return;
    lastBend = bend;
    writePositions(positions, xs, shape, bend);
    geometry.attributes.position.needsUpdate = true;
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();
  };

  return { geometry, setBend };
};
