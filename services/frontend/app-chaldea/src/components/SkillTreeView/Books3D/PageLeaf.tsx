import { useEffect, useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { noRaycast } from './bookParts';
import { pageBow } from './pageBlock';

/*
  A single leaf turning over on the spine. Lying on the right it shows its
  front — the page that was there — and as it rises and falls to the left it
  shows its back, the page that will be read there. It bends as it goes: the
  edge by the spine leads and the free edge trails, as a real page does.
*/

/** Strips across the leaf, spine to fore-edge; enough for a smooth curl. */
const SEGMENTS = 40;
/** How far the free edge lags behind the spine at the height of the turn, radians. */
const CURL = 1.0;
/** Height above the hinge the leaf travels at, clear of the pages under it. */
const LIFT = 0.012;

interface PageLeafProps {
  width: number;
  depth: number;
  hingeY: number;
  /**
   * How far over the leaf is, linear in time: 0 lying on the right, 1 lying on
   * the left. The book swaps the pages under the leaf on exactly this value,
   * so the leaf shows for exactly as long as 0 < turn < 1 — on any other
   * threshold a frame of the wrong page shows through.
   */
  turn: MutableRefObject<number>;
  front: THREE.Texture;
  back: THREE.Texture;
  /**
   * For a leaf in a riffle of several: whether the riffle is under way. The
   * leaf then shows for the whole of it, lying on whichever side it is on,
   * instead of only while it is itself in the air.
   */
  shown?: MutableRefObject<boolean>;
  /** Extra height for a leaf in a riffle, so leaves lying on one another don't fight. */
  stack?: MutableRefObject<number>;
}

const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

const PageLeaf = ({ width, depth, hingeY, turn, front, back, shown, stack }: PageLeafProps) => {
  // Two meshes on one set of positions: the front drawn from above, the back
  // from below with its picture flipped across, so it reads right once over.
  const { frontGeometry, backGeometry, positions } = useMemo(() => {
    const n = SEGMENTS + 1;
    const positions = new Float32Array(n * 2 * 3);
    const uvFront: number[] = [];
    const uvBack: number[] = [];
    const index: number[] = [];
    for (let i = 0; i < n; i++) {
      const s = i / SEGMENTS;
      uvFront.push(s, 1, s, 0);
      uvBack.push(1 - s, 1, 1 - s, 0);
      if (i > 0) {
        const a = (i - 1) * 2;
        index.push(a, a + 1, a + 2, a + 2, a + 1, a + 3);
      }
    }
    const attr = new THREE.BufferAttribute(positions, 3);
    const make = (uv: number[]) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', attr);
      g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
      g.setIndex(index);
      return g;
    };
    return { frontGeometry: make(uvFront), backGeometry: make(uvBack), positions };
  }, []);
  useEffect(
    () => () => {
      frontGeometry.dispose();
      backGeometry.dispose();
    },
    [frontGeometry, backGeometry],
  );

  const materials = useMemo(
    () => ({
      front: new THREE.MeshStandardMaterial({ map: front, roughness: 0.92, side: THREE.FrontSide }),
      back: new THREE.MeshStandardMaterial({ map: back, roughness: 0.92, side: THREE.BackSide }),
    }),
    [front, back],
  );
  useEffect(
    () => () => {
      materials.front.dispose();
      materials.back.dispose();
    },
    [materials],
  );

  const group = useRef<THREE.Group>(null);
  const last = useRef(-1);
  const lastStack = useRef(0);

  useFrame(() => {
    const raw = turn.current;
    const g = group.current;
    if (!g) return;
    g.visible = shown ? shown.current : raw > 0 && raw < 1;
    const t = easeInOut(raw);
    const extra = stack?.current ?? 0;
    if (!g.visible || (t === last.current && extra === lastStack.current)) return;
    last.current = t;
    lastStack.current = extra;

    // Walk out from the spine, each strip turned a little less than the one
    // before it, so the leaf curls with its free edge trailing.
    const theta = t * Math.PI;
    const curl = CURL * Math.sin(theta);
    // Lying down it takes the bow of the pages it lies on; in the air, none.
    const rest = Math.pow(1 - Math.sin(theta), 3);
    let x = 0;
    let y = 0;
    const step = width / SEGMENTS;
    for (let i = 0; i <= SEGMENTS; i++) {
      const s = i / SEGMENTS;
      if (i > 0) {
        const a = theta - curl * s;
        x += Math.cos(a) * step;
        y += Math.sin(a) * step;
      }
      // Never below the page it is passing over: as it starts to rise (or
      // settles) its own bow fades faster than it lifts, and near the spine,
      // where the pages hump, it would dip into them and let them show through.
      const surface = pageBow(Math.min(1, Math.abs(x) / width));
      const py = hingeY + LIFT + extra + Math.max(y + rest * pageBow(s), surface);
      for (let row = 0; row < 2; row++) {
        const k = (i * 2 + row) * 3;
        positions[k] = x;
        positions[k + 1] = py;
        positions[k + 2] = row === 0 ? -depth / 2 : depth / 2;
      }
    }
    frontGeometry.attributes.position.needsUpdate = true;
    frontGeometry.computeVertexNormals();
    backGeometry.computeVertexNormals();
    frontGeometry.computeBoundingSphere();
    backGeometry.computeBoundingSphere();
  });

  return (
    <group ref={group} visible={false}>
      <mesh geometry={frontGeometry} material={materials.front} raycast={noRaycast} castShadow />
      <mesh geometry={backGeometry} material={materials.back} raycast={noRaycast} />
    </group>
  );
};

export default PageLeaf;
