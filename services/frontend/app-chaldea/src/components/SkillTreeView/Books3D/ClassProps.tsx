import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Sparkles } from '@react-three/drei';
import * as THREE from 'three';
import { noRaycast, useDisposable, useMetal, useMetalEnv } from './bookParts';
import { mulberry32 } from './bookTextures';
import { scrawl } from './spreadTextures';

/*
  What each class has left lying round its book on the table: a soldier's
  notched blade, battered shield and a pint of ale; a rogue's poison, coins, dice and
  picks; a mage's crystal ball, star chart and a cluster of glowing crystals.

  Everything is placed from the book's spine, in the free table round the open
  spread: clear of its pages, of the candles off the far left corner and the
  inkwell off the far right, and of whatever a book's fastening lays out on
  the table to its right as it opens: the rogue's wide flap covers that side
  whole, the warrior's two hasps leave a band free between them. None of it
  takes clicks.
*/

type Spot = [number, number, number];

const makeCanvas = (width: number, height: number) => {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');
  return { canvas, ctx };
};

const canvasTexture = (canvas: HTMLCanvasElement) => {
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
};

/* ===================== Warrior ===================== */

/**
 * Worn steel: fine scratches running one way, grime, a few rust freckles, and
 * the honed edges brighter where `edges` asks for them (rows at the top and
 * bottom of the canvas).
 */
const createWornSteelTexture = (seed: number, base: string, edges: boolean) => {
  const W = 512;
  const H = 128;
  const { canvas, ctx } = makeCanvas(W, H);
  const rand = mulberry32(seed);
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, W, H);
  // Grime settled in patches.
  for (let i = 0; i < 18; i++) {
    const x = rand() * W;
    const y = rand() * H;
    const r = 10 + rand() * 40;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `rgba(30,24,18,${0.15 + rand() * 0.2})`);
    g.addColorStop(1, 'rgba(30,24,18,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  // Scratches, nearly all along the length.
  for (let i = 0; i < 260; i++) {
    const x = rand() * W;
    const y = rand() * H;
    const len = 10 + rand() * 90;
    const a = (rand() - 0.5) * 0.12 + (rand() < 0.08 ? (rand() - 0.5) * 2 : 0);
    ctx.strokeStyle = rand() < 0.6 ? `rgba(230,232,240,${0.08 + rand() * 0.15})` : `rgba(20,20,24,${0.1 + rand() * 0.15})`;
    ctx.lineWidth = 0.6 + rand() * 0.8;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    ctx.stroke();
  }
  // Rust freckles, on a blade mostly along its edges.
  for (let i = 0; i < 26; i++) {
    const x = rand() * W;
    const y = edges ? (rand() < 0.5 ? rand() * 18 : H - rand() * 18) : rand() * H;
    ctx.fillStyle = `rgba(${120 + rand() * 40},${55 + rand() * 25},20,${0.25 + rand() * 0.35})`;
    ctx.beginPath();
    ctx.arc(x, y, 1 + rand() * 4, 0, Math.PI * 2);
    ctx.fill();
  }
  if (edges) {
    // The honed edges, bright and narrow.
    for (const y of [0, H - 7]) {
      const g = ctx.createLinearGradient(0, y, 0, y + 7);
      g.addColorStop(y === 0 ? 0 : 1, 'rgba(235,238,245,0.55)');
      g.addColorStop(y === 0 ? 1 : 0, 'rgba(235,238,245,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, y, W, 7);
    }
  }
  const texture = canvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  return texture;
};

/** Leather thong wound slantwise round a grip. */
const createGripTexture = () => {
  const { canvas, ctx } = makeCanvas(128, 128);
  ctx.fillStyle = '#3a2416';
  ctx.fillRect(0, 0, 128, 128);
  for (let i = -128; i < 256; i += 16) {
    ctx.strokeStyle = 'rgba(12,6,2,0.75)';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i + 128 * 0.45, 128);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(140,95,60,0.35)';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(i + 7, 0);
    ctx.lineTo(i + 7 + 128 * 0.45, 128);
    ctx.stroke();
  }
  const texture = canvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(2, 1);
  return texture;
};

const BLADE = { length: 2.4, halfWidth: 0.125, ridge: 0.032, edge: 0.004, stations: 48 } as const;

/**
 * A blade with a ridge down its middle — two bevelled faces meeting in a crisp
 * line — lying flat on the table, tip toward +x. Its edges are bitten in
 * places, each side on its own.
 */
const createBladeGeometry = () => {
  const rand = mulberry32(17);
  const n = BLADE.stations;
  const positions: number[] = [];
  const uvs: number[] = [];
  const index: number[] = [];
  const left: number[] = [];
  const right: number[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    // Straight, narrowing a little, then drawn to a point over the last fifth.
    let w = BLADE.halfWidth * (1 - 0.18 * t);
    if (t > 0.8) w *= Math.pow(1 - (t - 0.8) / 0.2, 0.75);
    const bite = () => (i > 2 && i < n * 0.8 && rand() < 0.16 ? 0.025 + rand() * 0.035 : 0);
    left.push(Math.max(0.002, w - bite()));
    right.push(Math.max(0.002, w - bite()));
  }
  // Two faces, each its own strip, so the ridge stays sharp.
  for (const side of [-1, 1]) {
    const start = positions.length / 3;
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      const x = BLADE.length * t;
      const w = side < 0 ? left[i] : right[i];
      const ridge = BLADE.edge + BLADE.ridge * (t > 0.8 ? 1 - (t - 0.8) / 0.2 : 1);
      positions.push(x, BLADE.edge, side * w, x, ridge, 0);
      uvs.push(t, side < 0 ? 0 : 1, t, 0.5);
    }
    for (let i = 0; i < n; i++) {
      const a = start + i * 2;
      // Wound so both faces look up.
      if (side < 0) index.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
      else index.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(index);
  geometry.computeVertexNormals();
  return geometry;
};

/** A crossguard bowed a little toward the blade. */
const createGuardGeometry = () => {
  const curve = new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(0.06, 0.045, -0.36),
    new THREE.Vector3(-0.04, 0.045, 0),
    new THREE.Vector3(0.06, 0.045, 0.36),
  );
  return new THREE.TubeGeometry(curve, 24, 0.032, 8, false);
};

/** A wheel pommel, turned on the lathe: its axis across the sword. */
const POMMEL_PROFILE: [number, number][] = [
  [0, -0.045], [0.07, -0.045], [0.095, -0.025], [0.1, 0], [0.095, 0.025], [0.07, 0.045], [0, 0.045],
];

/** A soldier's sword, notched and worn from use, dropped on the table. */
const NotchedSword = ({ position, yaw }: { position: Spot; yaw: number }) => {
  const bladeTexture = useDisposable(() => createWornSteelTexture(17, '#8d9096', true), []);
  const ironTexture = useDisposable(() => createWornSteelTexture(23, '#5a5b60', false), []);
  const gripTexture = useDisposable(createGripTexture, []);
  const steel = useDisposable(
    () => new THREE.MeshStandardMaterial({ map: bladeTexture, roughness: 0.42, metalness: 0.88 }),
    [bladeTexture],
  );
  const iron = useDisposable(
    () => new THREE.MeshStandardMaterial({ map: ironTexture, roughness: 0.55, metalness: 0.8 }),
    [ironTexture],
  );
  useMetalEnv(steel);
  useMetalEnv(iron);
  const blade = useDisposable(createBladeGeometry, []);
  const guard = useDisposable(createGuardGeometry, []);
  const pommel = useMemo(() => POMMEL_PROFILE.map(([r, h]) => new THREE.Vector2(r, h)), []);
  return (
    <group position={position} rotation={[0, yaw, 0]}>
      <mesh geometry={blade} material={steel} castShadow />
      <mesh geometry={guard} material={iron} castShadow />
      {[-0.36, 0.36].map((z) => (
        <mesh key={z} position={[0.06, 0.045, z]} material={iron}>
          <sphereGeometry args={[0.045, 12, 8]} />
        </mesh>
      ))}
      <mesh position={[-0.25, 0.045, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.04, 0.044, 0.4, 14]} />
        <meshStandardMaterial map={gripTexture} roughness={0.85} />
      </mesh>
      <mesh position={[-0.5, 0.075, 0]} rotation={[Math.PI / 2, 0, 0]} material={iron} castShadow>
        <latheGeometry args={[pommel, 20]} />
      </mesh>
    </group>
  );
};

/** A heater shield's outline, top edge straight, sides running down to a point; shield units, top at +y. */
const SHIELD = { width: 1.1, top: 0.55, shoulder: 0.05, point: -0.8, thickness: 0.06, bulge: 0.05 } as const;
const SHIELD_HEIGHT = SHIELD.top - SHIELD.point;

const shieldOutline = () => {
  const half = SHIELD.width / 2;
  const shape = new THREE.Shape();
  shape.moveTo(-half, SHIELD.top);
  shape.lineTo(half, SHIELD.top);
  shape.lineTo(half, SHIELD.shoulder);
  shape.quadraticCurveTo(half, -0.45, 0, SHIELD.point);
  shape.quadraticCurveTo(-half, -0.45, -half, SHIELD.shoulder);
  shape.closePath();
  return shape;
};

/** How far the face swells up across its width, at a point x from the middle. */
const shieldBulge = (x: number) => SHIELD.bulge * (1 - (x / (SHIELD.width / 2)) ** 2);

/**
 * The arms painted on the face: an oxblood field, a gold chevron and three
 * pale towers — then years of it being used as a shield: paint chipped to the
 * wood, scratches, a deep gash, grime at the rim. Canvas top is the shield's top.
 */
const createArmsTexture = () => {
  const W = 512;
  const H = Math.round((W * SHIELD_HEIGHT) / SHIELD.width);
  const { canvas, ctx } = makeCanvas(W, H);
  const rand = mulberry32(61);
  const px = (x: number) => (x / SHIELD.width + 0.5) * W;
  const py = (y: number) => ((SHIELD.top - y) / SHIELD_HEIGHT) * H;

  // Wood under the paint, seen where it has chipped.
  const WOOD = '#6a4a2c';
  ctx.fillStyle = '#6e1a14';
  ctx.fillRect(0, 0, W, H);
  for (let i = 0; i < 4000; i++) {
    ctx.fillStyle = `rgba(${rand() < 0.5 ? '0,0,0' : '255,210,190'},${0.02 + rand() * 0.04})`;
    ctx.fillRect(rand() * W, rand() * H, 1 + rand() * 3, 1 + rand() * 3);
  }

  // The chevron, rising from the lower flanks to a peak above the middle.
  const band = 0.17;
  ctx.fillStyle = '#c29a4a';
  ctx.beginPath();
  ctx.moveTo(px(-0.55), py(-0.38));
  ctx.lineTo(px(0), py(0.2));
  ctx.lineTo(px(0.55), py(-0.38));
  ctx.lineTo(px(0.55), py(-0.38 - band));
  ctx.lineTo(px(0), py(0.2 - band * 1.35));
  ctx.lineTo(px(-0.55), py(-0.38 - band));
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = 'rgba(40,10,5,0.6)';
  ctx.lineWidth = 3;
  ctx.stroke();

  // Three towers: two in chief, one in base.
  const tower = (x: number, y: number, s: number) => {
    const cx = px(x);
    const cy = py(y);
    const w = s * W * 0.17;
    const h = w * 1.25;
    ctx.fillStyle = '#d9d2bf';
    ctx.beginPath();
    ctx.moveTo(cx - w / 2, cy + h / 2);
    ctx.lineTo(cx - w / 2, cy - h / 2);
    // Battlements
    const merlons = 3;
    const mw = w / (merlons * 2 - 1);
    for (let m = 0; m < merlons * 2 - 1; m++) {
      const x0 = cx - w / 2 + m * mw;
      const up = m % 2 === 0 ? -h / 2 - mw * 0.9 : -h / 2;
      ctx.lineTo(x0, cy + up);
      ctx.lineTo(x0 + mw, cy + up);
    }
    ctx.lineTo(cx + w / 2, cy - h / 2);
    ctx.lineTo(cx + w / 2, cy + h / 2);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = 'rgba(30,20,10,0.65)';
    ctx.lineWidth = 2.5;
    ctx.stroke();
    // Gate and a window slit
    ctx.fillStyle = 'rgba(30,20,10,0.75)';
    ctx.beginPath();
    ctx.moveTo(cx - w * 0.17, cy + h / 2);
    ctx.lineTo(cx - w * 0.17, cy + h * 0.15);
    ctx.arc(cx, cy + h * 0.15, w * 0.17, Math.PI, 0);
    ctx.lineTo(cx + w * 0.17, cy + h / 2);
    ctx.fill();
    ctx.fillRect(cx - w * 0.04, cy - h * 0.25, w * 0.08, h * 0.2);
  };
  tower(-0.27, 0.36, 1);
  tower(0.27, 0.36, 1);
  tower(0, -0.33, 1.05);

  // Chips down to the wood, crowded toward the rim where blows land.
  for (let i = 0; i < 90; i++) {
    const nearRim = rand() < 0.6;
    const x = nearRim ? (rand() < 0.5 ? rand() * 50 : W - rand() * 50) : rand() * W;
    const y = nearRim && rand() < 0.4 ? rand() * 40 : rand() * H;
    const r = 2 + rand() * (nearRim ? 12 : 6);
    ctx.fillStyle = WOOD;
    ctx.beginPath();
    for (let k = 0; k < 6; k++) {
      const a = (k / 6) * Math.PI * 2 + rand() * 0.6;
      const d = r * (0.5 + rand() * 0.7);
      if (k === 0) ctx.moveTo(x + Math.cos(a) * d, y + Math.sin(a) * d);
      else ctx.lineTo(x + Math.cos(a) * d, y + Math.sin(a) * d);
    }
    ctx.closePath();
    ctx.fill();
  }
  // Scratches.
  for (let i = 0; i < 70; i++) {
    const x = rand() * W;
    const y = rand() * H;
    const a = rand() * Math.PI;
    const len = 10 + rand() * 70;
    ctx.strokeStyle = `rgba(${rand() < 0.5 ? '20,8,4' : '200,170,140'},${0.15 + rand() * 0.25})`;
    ctx.lineWidth = 0.8 + rand();
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    ctx.stroke();
  }
  // A deep gash from a blade, across the upper right.
  ctx.lineCap = 'round';
  ctx.strokeStyle = WOOD;
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.moveTo(W * 0.56, H * 0.12);
  ctx.lineTo(W * 0.86, H * 0.36);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(15,6,2,0.85)';
  ctx.lineWidth = 3;
  ctx.stroke();

  // Grime and darkening toward the rim.
  const g = ctx.createRadialGradient(W / 2, H * 0.4, W * 0.2, W / 2, H * 0.45, W * 0.8);
  g.addColorStop(0, 'rgba(0,0,0,0)');
  g.addColorStop(1, 'rgba(20,10,4,0.5)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  return canvasTexture(canvas);
};

/** A soldier's heater shield laid face up, its arms battered, an iron rim round it. */
const Shield = ({ position, yaw }: { position: Spot; yaw: number }) => {
  const arms = useDisposable(createArmsTexture, []);
  const rimTexture = useDisposable(() => createWornSteelTexture(31, '#55565b', false), []);
  const face = useDisposable(() => new THREE.MeshStandardMaterial({ map: arms, roughness: 0.72, metalness: 0.05 }), [arms]);
  const wood = useDisposable(() => new THREE.MeshStandardMaterial({ color: '#4a3220', roughness: 0.9 }), []);
  const iron = useDisposable(
    () => new THREE.MeshStandardMaterial({ map: rimTexture, roughness: 0.55, metalness: 0.8 }),
    [rimTexture],
  );
  useMetalEnv(iron);
  const materials = useMemo(() => [face, wood], [face, wood]);

  const body = useDisposable(() => {
    const g = new THREE.ExtrudeGeometry(shieldOutline(), {
      depth: SHIELD.thickness,
      bevelEnabled: false,
      curveSegments: 24,
    });
    // Its face maps the arms whole, top of the arms at the top of the shield.
    const pos = g.attributes.position;
    const uv = g.attributes.uv;
    for (let i = 0; i < pos.count; i++) {
      uv.setXY(i, pos.getX(i) / SHIELD.width + 0.5, (pos.getY(i) - SHIELD.point) / SHIELD_HEIGHT);
    }
    // Face up on the table, top away from the reader; then swelled across.
    g.rotateX(-Math.PI / 2);
    for (let i = 0; i < pos.count; i++) pos.setY(i, pos.getY(i) + shieldBulge(pos.getX(i)));
    g.computeVertexNormals();
    return g;
  }, []);

  const rim = useDisposable(() => {
    const points = shieldOutline()
      .getSpacedPoints(80)
      .map((p) => new THREE.Vector3(p.x, SHIELD.thickness + shieldBulge(p.x) - 0.005, -p.y));
    return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points, true), 160, 0.026, 6, true);
  }, []);

  const rivets = useMemo(
    () =>
      shieldOutline()
        .getSpacedPoints(14)
        .slice(0, 14)
        .map((p) => {
          // Just inside the rim.
          const inward = new THREE.Vector2(-p.x, (SHIELD.top + SHIELD.point) / 2 - p.y).normalize().multiplyScalar(0.07);
          const x = p.x + inward.x;
          const y = p.y + inward.y;
          return [x, SHIELD.thickness + shieldBulge(x), -y] as Spot;
        }),
    [],
  );

  return (
    <group position={position} rotation={[0, yaw, 0]}>
      <mesh geometry={body} material={materials} castShadow receiveShadow />
      <mesh geometry={rim} material={iron} castShadow />
      {rivets.map((p, i) => (
        <mesh key={i} position={p} material={iron}>
          <sphereGeometry args={[0.022, 8, 6]} />
        </mesh>
      ))}
    </group>
  );
};

/** Oak staves round a tankard: a darker seam between each, grain running up them. */
const createStaveTexture = () => {
  const W = 512;
  const H = 128;
  const { canvas, ctx } = makeCanvas(W, H);
  const rand = mulberry32(71);
  const staves = 12;
  const sw = W / staves;
  for (let i = 0; i < staves; i++) {
    const shade = 0.85 + rand() * 0.3;
    ctx.fillStyle = `rgb(${Math.round(112 * shade)},${Math.round(76 * shade)},${Math.round(44 * shade)})`;
    ctx.fillRect(i * sw, 0, sw, H);
    for (let k = 0; k < 9; k++) {
      ctx.strokeStyle = `rgba(40,22,10,${0.12 + rand() * 0.2})`;
      ctx.lineWidth = 0.6 + rand();
      const x = i * sw + rand() * sw;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.bezierCurveTo(x + (rand() - 0.5) * 6, H * 0.3, x + (rand() - 0.5) * 6, H * 0.7, x + (rand() - 0.5) * 4, H);
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(25,12,5,0.7)';
    ctx.fillRect(i * sw, 0, 2, H);
  }
  // Dark where hands and ale have soaked it, near the rim and the foot.
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, 'rgba(30,15,5,0.4)');
  g.addColorStop(0.25, 'rgba(30,15,5,0)');
  g.addColorStop(0.8, 'rgba(30,15,5,0)');
  g.addColorStop(1, 'rgba(30,15,5,0.35)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  return canvasTexture(canvas);
};

const TANKARD = { radiusTop: 0.2, radiusFoot: 0.23, height: 0.5 } as const;

/**
 * Head of foam on the ale: a lumpy cap a little wider than the mouth, run over
 * the rim on one side.
 */
const createFoamGeometry = () => {
  const g = new THREE.SphereGeometry(TANKARD.radiusTop * 1.04, 28, 12, 0, Math.PI * 2, 0, Math.PI / 2);
  const rand = mulberry32(73);
  const pos = g.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const z = pos.getZ(i);
    const lump = 1 + (rand() - 0.5) * 0.08;
    // Squashed into a low dome, slumping over the rim toward +x.
    const spill = x > 0.08 && y < 0.03 ? -0.05 * (x / TANKARD.radiusTop) : 0;
    pos.setXYZ(i, x * lump, y * 0.35 * lump + spill, z * lump);
  }
  g.computeVertexNormals();
  return g;
};

/** A wooden tankard of dark ale, hooped in iron, a head of foam run over its rim. */
const Tankard = ({ position, yaw }: { position: Spot; yaw: number }) => {
  const staves = useDisposable(createStaveTexture, []);
  const foam = useDisposable(createFoamGeometry, []);
  const iron = useMetal('#3f4044', 0.6, 0.75);
  const handle = useDisposable(() => {
    const r = TANKARD.radiusFoot;
    const curve = new THREE.CubicBezierCurve3(
      new THREE.Vector3(r - 0.01, TANKARD.height * 0.82, 0),
      new THREE.Vector3(r + 0.24, TANKARD.height * 0.86, 0),
      new THREE.Vector3(r + 0.22, TANKARD.height * 0.2, 0),
      new THREE.Vector3(r - 0.01, TANKARD.height * 0.22, 0),
    );
    return new THREE.TubeGeometry(curve, 20, 0.035, 8, false);
  }, []);
  const { radiusTop: rt, radiusFoot: rf, height: h } = TANKARD;
  return (
    <group position={position} rotation={[0, yaw, 0]}>
      {/* A wet ring where it was set down before, and spilled drops */}
      <mesh position={[0.32, 0.003, 0.18]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[rf * 0.92, rf * 1.04, 32]} />
        <meshStandardMaterial color="#2a1608" transparent opacity={0.35} roughness={0.2} depthWrite={false} />
      </mesh>
      {[[-0.32, 0.12, 0.035], [-0.26, 0.24, 0.02], [0.05, 0.36, 0.028]].map(([x, z, r]) => (
        <mesh key={`${x}${z}`} position={[x, 0.003, z]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[r, 12]} />
          <meshStandardMaterial color="#3a2008" transparent opacity={0.45} roughness={0.1} depthWrite={false} />
        </mesh>
      ))}
      <mesh position={[0, h / 2, 0]} castShadow>
        <cylinderGeometry args={[rt, rf, h, 28, 1, true]} />
        <meshStandardMaterial map={staves} roughness={0.8} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[0, 0.01, 0]}>
        <cylinderGeometry args={[rf, rf, 0.02, 28]} />
        <meshStandardMaterial color="#4a3018" roughness={0.9} />
      </mesh>
      {/* Iron hoops near the foot, the middle and the rim */}
      {[0.06, 0.26, 0.45].map((y) => {
        const r = rf + (rt - rf) * (y / h) + 0.006;
        return (
          <mesh key={y} position={[0, y, 0]} rotation={[Math.PI / 2, 0, 0]} material={iron}>
            <torusGeometry args={[r, 0.014, 6, 32]} />
          </mesh>
        );
      })}
      <mesh geometry={handle} castShadow>
        <meshStandardMaterial map={staves} roughness={0.8} />
      </mesh>
      {/* The ale under its head, and the head itself */}
      <mesh position={[0, h - 0.04, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[rt * 0.97, 24]} />
        <meshStandardMaterial color="#5a2e08" roughness={0.15} />
      </mesh>
      <mesh geometry={foam} position={[0, h - 0.02, 0]} castShadow>
        <meshStandardMaterial color="#efe3c4" roughness={0.95} />
      </mesh>
    </group>
  );
};

const WarriorProps = () => (
  <>
    {/* Far enough back that the heavy shut book does not hide it */}
    <group scale={1.25}>
      <NotchedSword position={[-1.7, 0, -3.0]} yaw={0.12} />
    </group>
    {/* Between the two hasps, which unfold onto the table here */}
    <group scale={1.15}>
      <Shield position={[3.83, 0, 0]} yaw={0.22} />
    </group>
    <group scale={1.3}>
      <Tankard position={[-3.3, 0, -0.45]} yaw={2.4} />
    </group>
  </>
);

/* ===================== Rogue ===================== */

/** A coin's face: a ring round its rim, a crown-like mark, and wear. */
const createCoinFace = () => {
  const { canvas, ctx } = makeCanvas(128, 128);
  const g = ctx.createRadialGradient(54, 50, 6, 64, 64, 64);
  g.addColorStop(0, '#f4d37a');
  g.addColorStop(1, '#a8771f');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  ctx.strokeStyle = '#7a5214';
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.arc(64, 64, 54, 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(38, 80);
  ctx.lineTo(42, 48);
  ctx.lineTo(54, 64);
  ctx.lineTo(64, 42);
  ctx.lineTo(74, 64);
  ctx.lineTo(86, 48);
  ctx.lineTo(90, 80);
  ctx.closePath();
  ctx.stroke();
  return canvasTexture(canvas);
};

const COIN = { radius: 0.13, thickness: 0.026 } as const;

/** A short stack of gold coins and a few spilled round it. */
const Coins = ({ position }: { position: Spot }) => {
  const face = useDisposable(createCoinFace, []);
  const rim = useMetal('#c89a3a', 0.35, 0.95);
  const faceMaterial = useDisposable(
    () => new THREE.MeshStandardMaterial({ map: face, color: '#ffffff', roughness: 0.35, metalness: 0.9 }),
    [face],
  );
  useMetalEnv(faceMaterial);
  const materials = useMemo(() => [rim, faceMaterial, faceMaterial], [rim, faceMaterial]);
  const coins = useMemo(() => {
    const rand = mulberry32(5);
    const stack = Array.from({ length: 6 }, (_, i) => ({
      position: [(rand() - 0.5) * 0.03, COIN.thickness * (i + 0.5), (rand() - 0.5) * 0.03] as Spot,
      rotation: [0, rand() * Math.PI, 0] as Spot,
    }));
    const spilled = Array.from({ length: 6 }, () => {
      const a = rand() * Math.PI * 2;
      const d = 0.3 + rand() * 0.35;
      // Some lie flat; one leans on its neighbour.
      return {
        position: [Math.cos(a) * d, COIN.thickness / 2, Math.sin(a) * d] as Spot,
        rotation: [rand() < 0.2 ? 0.25 : 0, rand() * Math.PI, 0] as Spot,
      };
    });
    return [...stack, ...spilled];
  }, []);
  return (
    <group position={position}>
      {coins.map((c, i) => (
        <mesh key={i} position={c.position} rotation={c.rotation} material={materials} castShadow>
          <cylinderGeometry args={[COIN.radius, COIN.radius, COIN.thickness, 24]} />
        </mesh>
      ))}
    </group>
  );
};

/** A die's face of bone, with its pips. */
const createDieFace = (value: number) => {
  const { canvas, ctx } = makeCanvas(96, 96);
  ctx.fillStyle = '#e6dcc2';
  ctx.fillRect(0, 0, 96, 96);
  ctx.strokeStyle = 'rgba(90,70,40,0.35)';
  ctx.lineWidth = 6;
  ctx.strokeRect(0, 0, 96, 96);
  const at: Record<number, [number, number][]> = {
    1: [[48, 48]],
    2: [[26, 26], [70, 70]],
    3: [[24, 24], [48, 48], [72, 72]],
    4: [[26, 26], [70, 26], [26, 70], [70, 70]],
    5: [[24, 24], [72, 24], [48, 48], [24, 72], [72, 72]],
    6: [[26, 22], [70, 22], [26, 48], [70, 48], [26, 74], [70, 74]],
  };
  ctx.fillStyle = value === 1 ? '#7a1010' : '#1d1410';
  at[value].forEach(([x, y]) => {
    ctx.beginPath();
    ctx.arc(x, y, value === 1 ? 11 : 8, 0, Math.PI * 2);
    ctx.fill();
  });
  return canvasTexture(canvas);
};

/** Box faces: +x, -x, +y, -y, +z, -z — opposite faces add up to seven. */
const DIE_FACES = [3, 4, 1, 6, 2, 5];

const Dice = ({ position }: { position: Spot }) => {
  const materials = useMemo(
    () => DIE_FACES.map((v) => new THREE.MeshStandardMaterial({ map: createDieFace(v), roughness: 0.55 })),
    [],
  );
  useEffect(
    () => () =>
      materials.forEach((m) => {
        m.map?.dispose();
        m.dispose();
      }),
    [materials],
  );
  const size = 0.19;
  return (
    <group position={position}>
      {/* Rolled: one showing a single pip up, the other turned over on its side */}
      <mesh position={[0, size / 2, 0]} rotation={[0, 0.5, 0]} material={materials} castShadow>
        <boxGeometry args={[size, size, size]} />
      </mesh>
      <mesh position={[0.3, size / 2, 0.12]} rotation={[Math.PI / 2, 1.1, 0]} material={materials} castShadow>
        <boxGeometry args={[size, size, size]} />
      </mesh>
    </group>
  );
};

/** The roll's leather, stitched into pockets across. */
const createPickRollTexture = () => {
  const { canvas, ctx } = makeCanvas(256, 512);
  ctx.fillStyle = '#3a2416';
  ctx.fillRect(0, 0, 256, 512);
  const rand = mulberry32(9);
  for (let i = 0; i < 300; i++) {
    ctx.fillStyle = `rgba(${rand() < 0.5 ? '0,0,0' : '120,80,50'},${0.05 + rand() * 0.08})`;
    ctx.fillRect(rand() * 256, rand() * 512, 2 + rand() * 6, 1 + rand() * 3);
  }
  ctx.strokeStyle = '#b89a6a';
  ctx.lineWidth = 2;
  ctx.setLineDash([7, 6]);
  ctx.strokeRect(10, 10, 236, 492);
  for (let k = 1; k < 6; k++) {
    ctx.beginPath();
    ctx.moveTo(14, 60 + k * 70);
    ctx.lineTo(150, 60 + k * 70);
    ctx.stroke();
  }
  return canvasTexture(canvas);
};

/** A thief's leather roll undone on the table, picks and a tension wrench in its pockets. */
const PickRoll = ({ position, yaw }: { position: Spot; yaw: number }) => {
  const leather = useDisposable(createPickRollTexture, []);
  const steel = useMetal('#a4a6ab', 0.35, 0.9);
  const picks = [
    { z: -0.32, hook: 0.6 },
    { z: -0.18, hook: 1.4 },
    { z: -0.04, hook: 0.2 },
    { z: 0.1, hook: 2.2 },
    { z: 0.24, hook: 0.9 },
  ];
  return (
    <group position={position} rotation={[0, yaw, 0]}>
      <mesh position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 2]} receiveShadow>
        <planeGeometry args={[0.7, 1.4]} />
        <meshStandardMaterial map={leather} roughness={0.85} />
      </mesh>
      {/* The rest of the roll, still wound up at one end */}
      <mesh position={[-0.75, 0.07, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <cylinderGeometry args={[0.07, 0.07, 0.7, 14]} />
        <meshStandardMaterial map={leather} roughness={0.85} />
      </mesh>
      {picks.map((p, i) => (
        <group key={i} position={[0.12, 0.018, p.z]}>
          <mesh rotation={[0, 0, Math.PI / 2]} material={steel}>
            <cylinderGeometry args={[0.008, 0.008, 0.7, 6]} />
          </mesh>
          {/* The handle, and the bent tip */}
          <mesh position={[-0.3, 0, 0]} rotation={[0, 0, Math.PI / 2]} material={steel}>
            <cylinderGeometry args={[0.018, 0.018, 0.16, 8]} />
          </mesh>
          <mesh position={[0.36, 0, 0]} rotation={[Math.PI / 2, 0, p.hook]} material={steel}>
            <torusGeometry args={[0.025, 0.007, 5, 10, Math.PI]} />
          </mesh>
        </group>
      ))}
    </group>
  );
};

/** Outline of a round-bellied flask: base to lip. */
const FLASK_PROFILE: [number, number][] = [
  [0, 0], [0.12, 0.01], [0.2, 0.08], [0.22, 0.18], [0.19, 0.29], [0.1, 0.36], [0.06, 0.4], [0.06, 0.52], [0.075, 0.54],
];

/** A stoppered flask of something green and wrong, a thread of fumes rising from it. */
const PoisonFlask = ({ position }: { position: Spot }) => {
  const profile = useMemo(() => FLASK_PROFILE.map(([r, h]) => new THREE.Vector2(r, h)), []);
  const liquid = useRef<THREE.MeshStandardMaterial>(null);
  useFrame(({ clock }) => {
    if (liquid.current) liquid.current.emissiveIntensity = 0.7 + Math.sin(clock.elapsedTime * 1.7) * 0.2;
  });
  return (
    <group position={position} scale={1.25}>
      <mesh castShadow>
        <latheGeometry args={[profile, 24]} />
        <meshStandardMaterial color="#cfe8c8" roughness={0.08} metalness={0.1} transparent opacity={0.3} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[0, 0.15, 0]} scale={[1, 0.8, 1]}>
        <sphereGeometry args={[0.18, 20, 14]} />
        <meshStandardMaterial ref={liquid} color="#2f6b1c" emissive="#58d22c" emissiveIntensity={0.7} roughness={0.2} transparent opacity={0.85} />
      </mesh>
      <mesh position={[0, 0.56, 0]}>
        <cylinderGeometry args={[0.065, 0.055, 0.1, 12]} />
        <meshStandardMaterial color="#7b5a36" roughness={0.9} />
      </mesh>
      <pointLight position={[0, 0.2, 0]} color="#6cff3a" intensity={1.1} distance={2} decay={2} />
      <Sparkles raycast={noRaycast} count={6} scale={[0.15, 0.5, 0.15]} position={[0, 0.85, 0]} size={2.5} speed={0.35} color="#8cff5a" opacity={0.6} />
    </group>
  );
};

const RogueProps = () => (
  <>
    <PoisonFlask position={[-1.3, 0, -3.2]} />
    {/* Nothing to the right: the journal's flap lies out over all of it once undone */}
    <Coins position={[0.6, 0, -3.2]} />
    <Dice position={[-4.15, 0, 1.3]} />
    <PickRoll position={[-4.3, 0, -0.3]} yaw={0.25} />
  </>
);

/* ===================== Mage ===================== */

/** Slow swirls of light for the inside of the crystal ball. */
const createSwirlTexture = () => {
  const { canvas, ctx } = makeCanvas(256, 128);
  ctx.fillStyle = '#1a1040';
  ctx.fillRect(0, 0, 256, 128);
  const rand = mulberry32(21);
  for (let i = 0; i < 26; i++) {
    const y = rand() * 128;
    ctx.strokeStyle = `rgba(${150 + rand() * 100},${120 + rand() * 80},255,${0.2 + rand() * 0.4})`;
    ctx.lineWidth = 2 + rand() * 6;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.bezierCurveTo(80, y + (rand() - 0.5) * 80, 170, y + (rand() - 0.5) * 80, 256, y);
    ctx.stroke();
  }
  const texture = canvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  return texture;
};

const STAND_PROFILE: [number, number][] = [
  [0, 0], [0.3, 0], [0.3, 0.05], [0.18, 0.1], [0.13, 0.2], [0.22, 0.28], [0.2, 0.32], [0, 0.32],
];
const BALL_RADIUS = 0.34;

/** A crystal ball on a bronze stand, slow light turning inside it. */
const CrystalBall = ({ position }: { position: Spot }) => {
  const bronze = useMetal('#8a6a3a', 0.4);
  const swirl = useDisposable(createSwirlTexture, []);
  const profile = useMemo(() => STAND_PROFILE.map(([r, h]) => new THREE.Vector2(r, h)), []);
  const core = useRef<THREE.Mesh>(null);
  const light = useRef<THREE.PointLight>(null);
  useFrame(({ clock }, delta) => {
    if (core.current) {
      core.current.rotation.y += delta * 0.4;
      core.current.rotation.x = Math.sin(clock.elapsedTime * 0.3) * 0.3;
    }
    if (light.current) light.current.intensity = 1.6 + Math.sin(clock.elapsedTime * 1.2) * 0.4;
  });
  const center = 0.32 + BALL_RADIUS - 0.04;
  return (
    <group position={position}>
      <mesh material={bronze} castShadow>
        <latheGeometry args={[profile, 24]} />
      </mesh>
      <mesh ref={core} position={[0, center, 0]}>
        <sphereGeometry args={[BALL_RADIUS * 0.72, 24, 16]} />
        <meshStandardMaterial map={swirl} emissiveMap={swirl} emissive="#ffffff" emissiveIntensity={0.9} transparent opacity={0.9} />
      </mesh>
      <mesh position={[0, center, 0]} castShadow>
        <sphereGeometry args={[BALL_RADIUS, 32, 24]} />
        <meshStandardMaterial color="#d8d4ff" roughness={0.04} metalness={0.15} transparent opacity={0.22} depthWrite={false} />
      </mesh>
      <pointLight ref={light} position={[0, center, 0]} color="#9a7cff" intensity={1.6} distance={2.6} decay={2} />
    </group>
  );
};

/** A chart of the night sky: rings, stars by magnitude, and the lines between them. */
const createStarChartTexture = () => {
  const W = 512;
  const H = 768;
  const { canvas, ctx } = makeCanvas(W, H);
  const rand = mulberry32(33);
  ctx.fillStyle = '#d9c79f';
  ctx.fillRect(0, 0, W, H);
  for (let i = 0; i < 20; i++) {
    const x = rand() * W;
    const y = rand() * H;
    const r = 30 + rand() * 120;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, 'rgba(120,85,40,0.12)');
    g.addColorStop(1, 'rgba(120,85,40,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  const ink = 'rgba(28,30,70,0.85)';
  const cx = W / 2;
  const cy = H * 0.45;
  ctx.strokeStyle = ink;
  ctx.lineWidth = 2;
  [210, 196, 120, 60].forEach((r) => {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  });
  // Twelve houses round the rim.
  ctx.lineWidth = 1.2;
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * 196, cy + Math.sin(a) * 196);
    ctx.lineTo(cx + Math.cos(a) * 210, cy + Math.sin(a) * 210);
    ctx.stroke();
  }
  // Stars, a few joined into figures.
  const stars: [number, number][] = [];
  ctx.fillStyle = ink;
  for (let i = 0; i < 90; i++) {
    const a = rand() * Math.PI * 2;
    const d = Math.sqrt(rand()) * 190;
    const x = cx + Math.cos(a) * d;
    const y = cy + Math.sin(a) * d;
    stars.push([x, y]);
    const s = rand() < 0.15 ? 4 : 1.2 + rand() * 1.5;
    ctx.beginPath();
    ctx.arc(x, y, s, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.lineWidth = 1;
  for (let f = 0; f < 6; f++) {
    ctx.beginPath();
    let [x, y] = stars[Math.floor(rand() * stars.length)];
    ctx.moveTo(x, y);
    for (let k = 0; k < 4; k++) {
      const near = stars
        .filter(([sx, sy]) => Math.hypot(sx - x, sy - y) > 15)
        .sort((p, q) => Math.hypot(p[0] - x, p[1] - y) - Math.hypot(q[0] - x, q[1] - y))[Math.floor(rand() * 3)];
      [x, y] = near;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  // Notes under the chart, long faded.
  ctx.strokeStyle = 'rgba(28,30,70,0.55)';
  ctx.lineWidth = 1.6;
  for (let y = H * 0.8; y < H - 40; y += 30) scrawl(ctx, rand, 50, W - 50 - rand() * 120, y);
  return canvasTexture(canvas);
};

const CHART = { width: 1.0, depth: 1.5, roll: 0.07 } as const;

/** A star chart, unrolled and held flat, its far end still curled into a roll. */
const StarChart = ({ position, yaw }: { position: Spot; yaw: number }) => {
  const chart = useDisposable(createStarChartTexture, []);
  return (
    <group position={position} rotation={[0, yaw, 0]}>
      <mesh position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[CHART.width, CHART.depth]} />
        <meshStandardMaterial map={chart} roughness={0.9} />
      </mesh>
      <mesh position={[0, CHART.roll, -CHART.depth / 2 - CHART.roll * 0.6]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[CHART.roll, CHART.roll, CHART.width * 1.02, 16]} />
        <meshStandardMaterial color="#cbb88f" roughness={0.9} />
      </mesh>
      {/* A small smooth stone keeping the near end from curling up */}
      <mesh position={[0.28, 0.05, CHART.depth / 2 - 0.15]} scale={[1, 0.55, 0.8]} castShadow>
        <sphereGeometry args={[0.1, 14, 10]} />
        <meshStandardMaterial color="#3d3a48" roughness={0.6} />
      </mesh>
    </group>
  );
};

/** One crystal of the cluster: a six-sided prism with a pointed end, its foot at the origin, pointing up. */
const createCrystalGeometry = () =>
  new THREE.LatheGeometry(
    [
      new THREE.Vector2(0, 0),
      new THREE.Vector2(0.07, 0.02),
      new THREE.Vector2(0.07, 0.3),
      new THREE.Vector2(0, 0.42),
    ],
    6,
  );

/** A cluster of crystals grown from a lump of rock, faintly alight. */
const CrystalCluster = ({ position }: { position: Spot }) => {
  const crystal = useDisposable(createCrystalGeometry, []);
  const glow = useDisposable(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#b9a8ff',
        emissive: '#6a4cff',
        emissiveIntensity: 0.45,
        roughness: 0.15,
        metalness: 0.1,
        transparent: true,
        opacity: 0.85,
        flatShading: true,
      }),
    [],
  );
  useFrame(({ clock }) => {
    glow.emissiveIntensity = 0.45 + Math.sin(clock.elapsedTime * 0.9) * 0.15;
  });
  const crystals = useMemo(() => {
    const rand = mulberry32(41);
    return Array.from({ length: 7 }, (_, i) => {
      const a = (i / 7) * Math.PI * 2 + rand() * 0.4;
      const lean = i === 0 ? 0 : 0.35 + rand() * 0.4;
      return {
        position: [Math.cos(a) * 0.08 * (i ? 1 : 0), 0.08, Math.sin(a) * 0.08 * (i ? 1 : 0)] as Spot,
        // Lean outward from the middle.
        rotation: [Math.sin(a) * lean, 0, -Math.cos(a) * lean] as Spot,
        scale: (i === 0 ? 1.6 : 0.8 + rand() * 0.6) as number,
      };
    });
  }, []);
  return (
    <group position={position}>
      <mesh position={[0, 0.06, 0]} scale={[1.3, 0.5, 1.1]} castShadow>
        <dodecahedronGeometry args={[0.2, 0]} />
        <meshStandardMaterial color="#3a3640" roughness={0.95} />
      </mesh>
      {crystals.map((c, i) => (
        <mesh key={i} geometry={crystal} material={glow} position={c.position} rotation={c.rotation} scale={c.scale} castShadow />
      ))}
    </group>
  );
};

const MageProps = () => (
  <>
    <CrystalBall position={[-1.4, 0, -3.25]} />
    <StarChart position={[4.25, 0, 0.15]} yaw={-0.2} />
    <CrystalCluster position={[-4.2, 0, -0.5]} />
  </>
);

/* DB class ids: 1=Warrior, 2=Rogue, 3=Mage */
const PROPS: Record<number, () => JSX.Element> = {
  1: WarriorProps,
  2: RogueProps,
  3: MageProps,
};

interface ClassPropsProps {
  classId: number;
  /** The book's spine on the table. */
  position: Spot;
}

const ClassProps = ({ classId, position }: ClassPropsProps) => {
  const Props = PROPS[classId];
  return Props ? (
    <group position={position}>
      <Props />
    </group>
  ) : null;
};

export default ClassProps;
