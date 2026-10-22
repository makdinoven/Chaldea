import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { noRaycast, useDisposable, useMetal } from './bookParts';
import { mulberry32 } from './bookTextures';
import { inkClock, quillPose, type QuillStroke } from './quillStroke';

/*
  The inkwell beside each book, with a quill standing in it, in the manner of
  its class: a soldier's squat iron well and a grey goose quill; a rogue's
  glazed clay pot of green-black ink and a crow's feather; a mage's glass
  bottle of ink that glows, and a white quill tipped with blue.
*/

/** Overall size of the well and its quill. */
const INKWELL_SCALE = 1.3;
/** How far the quill leans out of the well, radians: away from the book, and back. */
const QUILL_LEAN = { out: -0.38, back: -0.55 } as const;
const QUILL_LENGTH = 1.45;
/** How the quill is held to write: leaning off to the right and away, out of the reader's way. */
const WRITING_LEAN = new THREE.Euler(-0.35, 0.15, -0.6);
/** The nib: the foot of the bare quill, in the quill's own frame. */
const NIB = new THREE.Vector3(0, -0.05, 0);
/** How high over the node the quill hovers before coming down, and how high it arcs in flight, world units. */
const HOVER_HEIGHT = 0.4;
const ARC_HEIGHT = 0.7;
const QUILL_WIDTH = 0.44;

interface InkwellStyle {
  /** Outline turned on the lathe: base to lip, then down inside to the ink. */
  profile: [number, number][];
  /** Facets round: few for cast iron, many for glass and clay. */
  segments: number;
  /** Height of the ink inside, and the radius of its surface. */
  ink: { y: number; r: number; colour: string; glow?: string };
  feather: { base: string; band: string; tip: string };
}

/* DB class ids: 1=Warrior, 2=Rogue, 3=Mage */
const STYLES: Record<number, InkwellStyle> = {
  1: {
    profile: [
      [0, 0], [0.36, 0], [0.38, 0.04], [0.38, 0.2], [0.3, 0.28], [0.15, 0.32],
      [0.12, 0.38], [0.15, 0.4], [0.15, 0.43], [0.1, 0.43], [0.1, 0.36], [0, 0.36],
    ],
    segments: 8,
    ink: { y: 0.37, r: 0.1, colour: '#0d0906' },
    feather: { base: '#8f897d', band: '#4b453c', tip: '#2e2a25' },
  },
  2: {
    profile: [
      [0, 0], [0.26, 0], [0.32, 0.06], [0.34, 0.16], [0.3, 0.26], [0.16, 0.33],
      [0.12, 0.36], [0.13, 0.4], [0.09, 0.4], [0.09, 0.33], [0, 0.33],
    ],
    segments: 24,
    ink: { y: 0.34, r: 0.09, colour: '#0c1a0e' },
    feather: { base: '#17171b', band: '#2c3a33', tip: '#0a0a0c' },
  },
  3: {
    profile: [
      [0, 0], [0.3, 0], [0.3, 0.03], [0.22, 0.12], [0.26, 0.22], [0.12, 0.34],
      [0.1, 0.44], [0.12, 0.46], [0.08, 0.46], [0.08, 0.4], [0, 0.4],
    ],
    segments: 32,
    ink: { y: 0.41, r: 0.08, colour: '#2d5cff', glow: '#3d7bff' },
    feather: { base: '#f3f1ff', band: '#c9dcff', tip: '#7fa8ff' },
  },
};

/** One side of a flight feather, barb by barb; canvas top is the tip. */
const createFeatherTexture = (feather: InkwellStyle['feather'], seed: number) => {
  const W = 128;
  const H = 512;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  const rand = mulberry32(seed);
  const cx = W * 0.56;
  /** Half-width of the vane down its length, t from tip (0) to quill (1). */
  const half = (t: number) => Math.sin(Math.PI * Math.min(1, t * 1.15)) ** 0.55;
  ctx.lineCap = 'round';
  let gap = 0;
  for (let y = 6; y < H * 0.86; y += 2.2) {
    const t = y / H;
    // Now and then the vane parts, as real feathers do.
    if (gap > 0) {
      gap--;
      continue;
    }
    if (rand() < 0.015) gap = 2 + Math.floor(rand() * 3);
    const band = Math.sin(t * 34) > 0.55;
    const colour = t < 0.12 ? feather.tip : band ? feather.band : feather.base;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 1.6;
    const lw = half(t) * cx * 0.95;
    const rw = half(t) * (W - cx) * 0.9;
    ctx.beginPath();
    ctx.moveTo(cx, y);
    ctx.quadraticCurveTo(cx - lw * 0.5, y - lw * 0.15, cx - lw, y - lw * 0.42);
    ctx.moveTo(cx, y);
    ctx.quadraticCurveTo(cx + rw * 0.5, y - rw * 0.15, cx + rw, y - rw * 0.42);
    ctx.stroke();
  }
  // Down near the quill: loose wisps.
  ctx.strokeStyle = feather.base;
  ctx.lineWidth = 1;
  for (let i = 0; i < 40; i++) {
    const y = H * (0.8 + rand() * 0.1);
    const a = (rand() - 0.5) * 2.4;
    ctx.beginPath();
    ctx.moveTo(cx, y);
    ctx.lineTo(cx + Math.sin(a) * 30, y - Math.cos(a) * 18);
    ctx.stroke();
  }
  // The rachis down the middle.
  ctx.strokeStyle = '#e8e0cc';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(cx, 4);
  ctx.lineTo(cx, H);
  ctx.stroke();

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
};

/** Faint blue light the glowing ink throws on the table round the bottle, slowly breathing. */
const InkGlow = ({ seed }: { seed: number }) => {
  const texture = useDisposable(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('2D canvas context unavailable');
    const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(0.4, 'rgba(255,255,255,0.35)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(canvas);
  }, []);
  const material = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }) => {
    if (material.current) material.current.opacity = 0.22 + Math.sin(clock.elapsedTime * 0.8 + seed) * 0.06;
  });
  return (
    <mesh raycast={noRaycast} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]}>
      <planeGeometry args={[1.4, 1.4]} />
      <meshBasicMaterial
        ref={material}
        map={texture}
        color="#4f7dff"
        transparent
        opacity={0.22}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </mesh>
  );
};

interface InkwellProps {
  classId: number;
  position: [number, number, number];
  seed: number;
  /** A node to write: the quill leaves the well for it and comes back. */
  stroke?: QuillStroke | null;
}

const Inkwell = ({ classId, position, seed, stroke = null }: InkwellProps) => {
  const style = STYLES[classId] ?? STYLES[1];
  const glass = classId === 3;
  const iron = useMetal('#55565b', 0.5);
  const body = useDisposable(
    () =>
      glass
        ? new THREE.MeshStandardMaterial({
            color: '#bcd4ff',
            roughness: 0.08,
            metalness: 0.1,
            transparent: true,
            opacity: 0.3,
            depthWrite: false,
            // Outside only: the inner walls caught the light as stray rings and flecks.
            side: THREE.FrontSide,
          })
        : new THREE.MeshStandardMaterial({ color: '#2b1c13', roughness: 0.28, metalness: 0.05 }),
    [glass],
  );
  const profile = useMemo(() => style.profile.map(([r, h]) => new THREE.Vector2(r, h)), [style]);
  const feather = useDisposable(() => createFeatherTexture(style.feather, seed), [style, seed]);
  const vane = useDisposable(() => {
    const g = new THREE.PlaneGeometry(QUILL_WIDTH, QUILL_LENGTH, 1, 12);
    // A gentle curve along its length, as a feather has.
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const t = pos.getY(i) / QUILL_LENGTH + 0.5;
      pos.setZ(i, -t * t * 0.14);
    }
    g.computeVertexNormals();
    return g;
  }, []);

  const neck = style.profile[style.profile.length - 4][1];
  // Where the quill rests in the well, and how it lies there; and how it is held to write.
  const rest = useMemo(
    () => ({
      position: new THREE.Vector3(0, neck - 0.12, 0),
      turn: new THREE.Quaternion().setFromEuler(new THREE.Euler(QUILL_LEAN.back, 0.15, QUILL_LEAN.out)),
      writing: new THREE.Quaternion().setFromEuler(WRITING_LEAN),
    }),
    [neck],
  );

  // A draft from the candles stirs the quill at rest; a node taken sends it
  // to the page to write it (see quillPose for its flight).
  const quill = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    const g = quill.current;
    if (!g) return;
    const pose = quillPose(stroke ? inkClock() - stroke.at : -1);
    if (!stroke || pose.reach === 0) {
      const t = clock.elapsedTime + seed * 3.1;
      g.position.copy(rest.position);
      g.quaternion.copy(rest.turn);
      g.rotateZ(Math.sin(t * 0.9) * 0.012 + Math.sin(t * 2.3) * 0.005);
      return;
    }
    // Everything here is in the well's own frame: world less its place, over its size.
    const turn = rest.turn.clone().slerp(rest.writing, pose.reach);
    const nib = new THREE.Vector3(...stroke.point)
      .sub(new THREE.Vector3(...position))
      .add(pose.scribble)
      .divideScalar(INKWELL_SCALE);
    const down = nib.sub(NIB.clone().applyQuaternion(rest.writing));
    down.y += ((pose.hover * HOVER_HEIGHT) + pose.arc * ARC_HEIGHT) / INKWELL_SCALE;
    g.position.copy(rest.position).lerp(down, pose.reach);
    g.quaternion.copy(turn);
  });

  return (
    <group position={position} scale={INKWELL_SCALE}>
      <mesh material={classId === 1 ? iron : body} raycast={noRaycast} castShadow>
        <latheGeometry args={[profile, style.segments]} />
      </mesh>
      {/* The ink inside: a pool at the neck, and in glass the whole bottle full */}
      <mesh raycast={noRaycast} position={[0, style.ink.y, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[style.ink.r, 20]} />
        <meshStandardMaterial
          color={style.ink.colour}
          roughness={0.05}
          metalness={0.2}
          emissive={style.ink.glow ?? '#000000'}
          emissiveIntensity={style.ink.glow ? 0.6 : 0}
        />
      </mesh>
      {glass && (
        <>
          {/* The ink filling the belly, kept wholly inside the glass */}
          <mesh raycast={noRaycast} position={[0, 0.15, 0]} scale={[1, 0.8, 1]}>
            <sphereGeometry args={[0.16, 20, 14]} />
            <meshStandardMaterial color="#1c3cb0" emissive="#3d7bff" emissiveIntensity={0.8} roughness={0.2} />
          </mesh>
          <InkGlow seed={seed} />
        </>
      )}
      <group ref={quill}>
        {/* The bare quill, down into the ink */}
        <mesh raycast={noRaycast} position={[0, 0.2, 0]}>
          <cylinderGeometry args={[0.012, 0.008, 0.5, 8]} />
          <meshStandardMaterial color="#e6dcc4" roughness={0.4} />
        </mesh>
        <mesh raycast={noRaycast} geometry={vane} position={[0, 0.38 + QUILL_LENGTH / 2, 0]} castShadow>
          <meshStandardMaterial map={feather} alphaTest={0.35} side={THREE.DoubleSide} roughness={0.75} transparent />
        </mesh>
      </group>
    </group>
  );
};

export default Inkwell;
