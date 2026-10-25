import { useEffect, useMemo } from 'react';
import { Sparkles } from '@react-three/drei';
import * as THREE from 'three';

/*
  The dungeon carved out of living rock: a dark, uneven bed of stone under the
  whole floor, laid from the start over everything the floor spans (so it never
  grows as rooms are found), its edge breaking up into boulders, glowing
  crystals and fungi and sinking into the dark. The rooms stand on it; what is
  not yet found is just more rock.
*/

/** A world rectangle: [x0, x1] × [z0, z1]. */
export interface RockRect {
  x0: number;
  x1: number;
  z0: number;
  z1: number;
}

/** Rock beyond the floor's span before the dark takes it (the board's dusk covers it too). */
export const ROCK_EDGE = 4.5;
const EDGE = ROCK_EDGE;
/** Mesh resolution of the bed (world units per vertex). */
const STEP = 0.35;
/** How deep the bed dips (it only dips: nothing pokes through a floor). */
const DIP = 0.14;
const LATTICE = 0.9;

const hash = (x: number, z: number, salt = 0) => {
  const s = Math.sin(x * 127.1 + z * 311.7 + salt * 74.7) * 43758.5453;
  return s - Math.floor(s);
};

/** Smooth value noise. */
const noise = (x: number, z: number) => {
  const xi = Math.floor(x);
  const zi = Math.floor(z);
  const fx = x - xi;
  const fz = z - zi;
  const u = fx * fx * (3 - 2 * fx);
  const v = fz * fz * (3 - 2 * fz);
  const a = hash(xi, zi);
  const b = hash(xi + 1, zi);
  const c = hash(xi, zi + 1);
  const d = hash(xi + 1, zi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
};

const fbm = (x: number, z: number) => noise(x, z) * 0.6 + noise(x * 2.3, z * 2.3) * 0.3 + noise(x * 5.1, z * 5.1) * 0.1;

/** Distance from a point to the rectangle (0 inside). */
const outside = (r: RockRect, x: number, z: number) =>
  Math.hypot(Math.max(r.x0 - x, 0, x - r.x1), Math.max(r.z0 - z, 0, z - r.z1));

/** Dark stone with seams and grit, to tile over the bed. */
const rockTexture = () => {
  const size = 256;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#5a544c';
  ctx.fillRect(0, 0, size, size);
  let seed = 9;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  for (let i = 0; i < 120; i++) {
    const x = rand() * size;
    const y = rand() * size;
    const r = 8 + rand() * 40;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    const light = rand() < 0.45;
    g.addColorStop(0, light ? 'rgba(140,128,112,0.16)' : 'rgba(10,8,8,0.28)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  // Seams in the rock.
  for (let c = 0; c < 5; c++) {
    let x = rand() * size;
    let y = rand() * size;
    ctx.strokeStyle = `rgba(8,6,6,${0.18 + rand() * 0.18})`;
    ctx.lineWidth = 0.6 + rand() * 0.9;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let k = 0; k < 7; k++) {
      x += (rand() - 0.5) * 50;
      y += (rand() - 0.5) * 50;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  for (let i = 0; i < 1800; i++) {
    ctx.fillStyle = rand() < 0.5 ? 'rgba(0,0,0,0.35)' : 'rgba(170,160,145,0.2)';
    ctx.fillRect(rand() * size, rand() * size, 1, 1);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  return texture;
};

/** A lumpy stone (seeded). */
const boulder = (seed: number) => {
  const g = new THREE.IcosahedronGeometry(1, 1);
  const pos = g.attributes.position;
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i);
    v.multiplyScalar(1 + (hash(v.x * 3 + seed, v.y * 3, v.z * 3) - 0.5) * 0.45);
    v.y *= 0.7;
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  g.computeVertexNormals();
  return g;
};

interface RockBedProps {
  rect: RockRect;
  /** Height of the bed's top (the rooms' feet). */
  top: number;
  lowGraphics: boolean;
  /** The rock's colour (the dungeon's look). */
  tint?: string;
}

/** The colour the rock was painted for; a look's tint is taken relative to it. */
const ROCK_BASE = '#6a645c';

const RockBed = ({ rect, top, lowGraphics, tint = ROCK_BASE }: RockBedProps) => {
  const texture = useMemo(rockTexture, []);
  useEffect(() => () => texture.dispose(), [texture]);

  const bed = useMemo(() => {
    const x0 = rect.x0 - EDGE;
    const x1 = rect.x1 + EDGE;
    const z0 = rect.z0 - EDGE;
    const z1 = rect.z1 + EDGE;
    const w = x1 - x0;
    const d = z1 - z0;
    const segX = Math.min(220, Math.max(8, Math.round(w / STEP)));
    const segZ = Math.min(220, Math.max(8, Math.round(d / STEP)));
    const geometry = new THREE.PlaneGeometry(w, d, segX, segZ);
    geometry.rotateX(-Math.PI / 2);
    const pos = geometry.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    const uv = geometry.attributes.uv;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i) + (x0 + x1) / 2;
      const z = pos.getZ(i) + (z0 + z1) / 2;
      const out = outside(rect, x, z);
      // Inside the span the rock is nearly flat; past it, it breaks up and falls away into the dark.
      const rough = fbm(x * 0.6, z * 0.6);
      const fall = Math.min(1, out / EDGE);
      pos.setY(i, -rough * DIP - fall * fall * 1.4);
      const shade = (0.55 + rough * 0.45) * (1 - fall * 0.92);
      colors[i * 3] = shade;
      colors[i * 3 + 1] = shade * 0.97;
      colors[i * 3 + 2] = shade * 0.94;
      uv.setXY(i, x / 5 + rough * 0.6, z / 5 - rough * 0.4);
    }
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.computeVertexNormals();
    return { geometry, cx: (x0 + x1) / 2, cz: (z0 + z1) / 2, w, d };
  }, [rect]);
  useEffect(() => () => bed.geometry.dispose(), [bed]);

  // Boulders, crystals and fungi in the broken ground round the span, on a fixed lattice so they stay put.
  const props = useMemo(() => {
    const stones: { pos: [number, number, number]; scale: number; seed: number; rot: number }[] = [];
    const crystals: { pos: [number, number, number]; scale: number; tilt: number; hue: string }[] = [];
    const fungi: { pos: [number, number, number]; scale: number }[] = [];
    for (let x = Math.floor((rect.x0 - EDGE) / LATTICE); x <= Math.ceil((rect.x1 + EDGE) / LATTICE); x++) {
      for (let z = Math.floor((rect.z0 - EDGE) / LATTICE); z <= Math.ceil((rect.z1 + EDGE) / LATTICE); z++) {
        const wx = x * LATTICE + (hash(x, z, 1) - 0.5) * LATTICE;
        const wz = z * LATTICE + (hash(x, z, 2) - 0.5) * LATTICE;
        const out = outside(rect, wx, wz);
        if (out < 0.6 || out > EDGE * 0.85) continue;
        const roll = hash(x, z, 3);
        const y = -((out / EDGE) ** 2) * 1.4;
        if (roll < 0.22) {
          stones.push({ pos: [wx, y, wz], scale: 0.18 + hash(x, z, 4) * 0.45, seed: x * 31 + z, rot: hash(x, z, 5) * 6 });
        } else if (roll < 0.27) {
          crystals.push({
            pos: [wx, y, wz],
            scale: 0.12 + hash(x, z, 6) * 0.18,
            tilt: (hash(x, z, 7) - 0.5) * 0.8,
            hue: hash(x, z, 8) < 0.6 ? '#6fb7ff' : '#b07aff',
          });
        } else if (roll < 0.31) {
          fungi.push({ pos: [wx, y, wz], scale: 0.05 + hash(x, z, 9) * 0.06 });
        }
      }
    }
    return { stones, crystals, fungi };
  }, [rect]);
  const stoneGeometries = useMemo(() => [0, 1, 2, 3].map((s) => boulder(s * 1.7 + 0.3)), []);
  useEffect(() => () => stoneGeometries.forEach((g) => g.dispose()), [stoneGeometries]);
  const stoneMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ map: texture, color: tint, roughness: 0.95, flatShading: true }),
    [texture, tint],
  );
  useEffect(() => () => stoneMaterial.dispose(), [stoneMaterial]);
  // The bed carries its shading in vertex colours: tint it by how far the look is from the base rock.
  const bedColor = useMemo(() => {
    const t = new THREE.Color(tint);
    const b = new THREE.Color(ROCK_BASE);
    return new THREE.Color(Math.min(1.6, t.r / b.r), Math.min(1.6, t.g / b.g), Math.min(1.6, t.b / b.b));
  }, [tint]);

  return (
    <>
      <hemisphereLight args={['#b0a890', '#1a120c', 1.5]} />
      <directionalLight position={[-6, 12, 8]} intensity={1.4} color="#fff0d8" />
      <group position={[0, top, 0]}>
        <mesh geometry={bed.geometry} position={[bed.cx, 0, bed.cz]} receiveShadow>
          <meshStandardMaterial map={texture} vertexColors color={bedColor} roughness={0.95} />
        </mesh>
        {props.stones.map((s, i) => (
          <mesh
            key={`s${i}`}
            geometry={stoneGeometries[Math.abs(s.seed) % stoneGeometries.length]}
            material={stoneMaterial}
            position={s.pos}
            rotation={[0, s.rot, 0]}
            scale={s.scale}
          />
        ))}
        {props.crystals.map((c, i) => (
          <group key={`c${i}`} position={c.pos} rotation={[c.tilt, i, c.tilt * 0.5]}>
            {[0, 1, 2].map((k) => (
              <mesh key={k} position={[(k - 1) * c.scale * 0.5, c.scale * (0.9 - Math.abs(k - 1) * 0.3), 0]} rotation={[0, 0, (k - 1) * 0.35]}>
                <coneGeometry args={[c.scale * 0.28, c.scale * (2 - Math.abs(k - 1) * 0.6), 5]} />
                <meshStandardMaterial color={c.hue} emissive={c.hue} emissiveIntensity={1.4} roughness={0.2} toneMapped={false} />
              </mesh>
            ))}
            {!lowGraphics && i % 3 === 0 && <pointLight color={c.hue} intensity={1.2} distance={1.8} decay={1.6} position={[0, c.scale * 1.5, 0]} />}
          </group>
        ))}
        {props.fungi.map((f, i) => (
          <group key={`f${i}`} position={f.pos} scale={f.scale}>
            <mesh position={[0, 0.6, 0]}>
              <cylinderGeometry args={[0.18, 0.25, 1.2, 6]} />
              <meshStandardMaterial color="#cdbf9a" roughness={0.8} />
            </mesh>
            <mesh position={[0, 1.25, 0]}>
              <sphereGeometry args={[0.7, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2]} />
              <meshStandardMaterial color="#7cf0c0" emissive="#3fdca0" emissiveIntensity={1.2} toneMapped={false} />
            </mesh>
          </group>
        ))}
        {!lowGraphics && (
          <Sparkles
            count={60}
            scale={[bed.w, 3, bed.d]}
            position={[bed.cx, 1.6, bed.cz]}
            size={1.4}
            speed={0.12}
            color="#c9d8ff"
            opacity={0.3}
          />
        )}
      </group>
      <fog attach="fog" args={['#050407', 12, 55]} />
    </>
  );
};

export default RockBed;
