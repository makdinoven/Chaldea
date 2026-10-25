import { useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import { Environment, Lightformer, RoundedBox } from '@react-three/drei';
import * as THREE from 'three';
import type { LockpickParams } from '../../../../api/dungeons';
import { pinHeight } from '../lockpick';
import type { LockLive } from '../useLockpick';
import { brassTexture, doorPlanksTexture, glowTexture, ironTexture } from './craftTextures';

/*
  The lock in 3D: an iron lock box on an old door, cut open so its works show —
  a brass plug with a keyway, pins in their channels (brass key pins, steel
  drivers, springs above), a pick in the keyway and a tension wrench. The pick
  rocks the active pin; when its top meets the shear line (the gold glow) a
  press sets it. A strain jolts the lock and throws sparks; one too many snaps
  the pick. Opened, the plug turns and the bolt slides back.
*/

// Where things are (world units; the lock face is at z ≈ 0).
const SHEAR_Y = -0.02;
const PLUG_Y = -0.22;
const PLUG_R = 0.2;
const PLUG_LEN = 1.9;
const FACE_Z = 0.12;
const HOUSING_TOP = 0.62;
const PIN_R = 0.045;
const KEY_PIN_H = 0.16;
const KEY_TIP_H = 0.04;
const DRIVER_H = 0.18;
const CHANNEL_W = 0.11;
const PIN_SPAN = 1.3;
/** How far a pin's top travels per unit of its bob (the game's -1..1). */
const TRAVEL = 0.11;
/** A pin waiting its turn rests below the shear line. */
const REST_DROP = 0.09;
const PICK_PIVOT = new THREE.Vector3(-1.85, -0.25, FACE_Z + 0.01);
const PICK_SLIDE = 6;
const SHAKE_MS = 320;
const FLASH_MS = 450;
const OPEN_MS = 700;
/** How far the plug turns when the lock opens (radians). */
const PLUG_TURN = 0.5;
const SPARKS = 48;
const GRAVITY = -3.2;
export const CAMERA_Z = 3.15;

const BRASS = '#e2d6b8';
const STEEL = '#a7adb5';
const SPARK_HOT = new THREE.Color('#ffb04a');
const SPARK_GOLD = new THREE.Color('#ffe08a');

const pinX = (i: number, count: number) => (count === 1 ? 0 : -PIN_SPAN / 2 + (PIN_SPAN * i) / (count - 1));

/** A coil spring, one unit tall (scaled to fit between the driver pin and the channel's top). */
class Helix extends THREE.Curve<THREE.Vector3> {
  constructor(private turns: number, private radius: number) {
    super();
  }
  getPoint(t: number, target = new THREE.Vector3()) {
    const a = t * this.turns * Math.PI * 2;
    return target.set(Math.cos(a) * this.radius, t, Math.sin(a) * this.radius);
  }
}

interface Spark {
  pos: THREE.Vector3;
  vel: THREE.Vector3;
  life: number;
  max: number;
  color: THREE.Color;
}

interface LockSceneProps {
  params: LockpickParams;
  live: MutableRefObject<LockLive>;
}

const LockScene = ({ params, live }: LockSceneProps) => {
  const count = params.pins.length;
  const textures = useMemo(() => {
    const iron = ironTexture();
    const planks = doorPlanksTexture();
    const brass = brassTexture();
    return { iron, planks, brass, glow: glowTexture() };
  }, []);
  const materials = useMemo(
    () => ({
      iron: new THREE.MeshStandardMaterial({ map: textures.iron, color: '#8a8a92', metalness: 0.75, roughness: 0.55 }),
      ironDark: new THREE.MeshStandardMaterial({ map: textures.iron, color: '#4a4a52', metalness: 0.6, roughness: 0.7 }),
      chamber: new THREE.MeshStandardMaterial({ color: '#0b0a0c', roughness: 1 }),
      brass: new THREE.MeshStandardMaterial({ map: textures.brass, color: BRASS, metalness: 0.85, roughness: 0.26 }),
      // The cut face of the housing: filed bright, the channels dark against it.
      cut: new THREE.MeshStandardMaterial({ map: textures.iron, color: '#c4c4cc', metalness: 0.55, roughness: 0.42 }),
      steel: new THREE.MeshStandardMaterial({ color: STEEL, metalness: 0.95, roughness: 0.25 }),
      spring: new THREE.MeshStandardMaterial({ color: '#8d939b', metalness: 0.9, roughness: 0.35 }),
      planks: new THREE.MeshStandardMaterial({ map: textures.planks, color: '#7a6a5c', roughness: 0.9 }),
      leather: new THREE.MeshStandardMaterial({ color: '#3b2516', roughness: 0.85 }),
    }),
    [textures],
  );
  const springGeometry = useMemo(() => new THREE.TubeGeometry(new Helix(7, 0.032), 90, 0.007, 6, false), []);
  const pickMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ color: '#c3c8cf', metalness: 0.95, roughness: 0.2, emissive: '#ff3a1a', emissiveIntensity: 0 }),
    [],
  );

  const rig = useRef<THREE.Group>(null);
  const keyPins = useRef<(THREE.Group | null)[]>([]);
  const drivers = useRef<(THREE.Mesh | null)[]>([]);
  const springs = useRef<(THREE.Mesh | null)[]>([]);
  const pinGlows = useRef<(THREE.MeshStandardMaterial | null)[]>([]);
  const band = useRef<THREE.Mesh>(null);
  const bandMat = useRef<THREE.MeshBasicMaterial>(null);
  const pick = useRef<THREE.Group>(null);
  const pickShaft = useRef<THREE.Mesh>(null);
  const pickHook = useRef<THREE.Group>(null);
  const plug = useRef<THREE.Group>(null);
  const bolt = useRef<THREE.Mesh>(null);
  const candle = useRef<THREE.PointLight>(null);
  const flashLight = useRef<THREE.PointLight>(null);
  const sparkSprites = useRef<(THREE.Sprite | null)[]>([]);
  const sparks = useRef<Spark[]>([]);
  const pickX = useRef(pinX(0, count));
  const lastSeen = useRef({ strainAt: -Infinity, setAt: -Infinity, broke: false, openAt: -Infinity });
  const brokenHook = useRef<{ vel: THREE.Vector3; spin: number } | null>(null);
  const pinY = useRef<number[]>(params.pins.map(() => SHEAR_Y - REST_DROP));

  const burst = (at: THREE.Vector3, color: THREE.Color, n: number, speed: number) => {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const up = 0.4 + Math.random();
      sparks.current.push({
        pos: at.clone(),
        vel: new THREE.Vector3(Math.cos(a) * speed * Math.random(), up * speed, 0.3 + Math.random() * speed * 0.6),
        life: 0,
        max: 0.35 + Math.random() * 0.4,
        color,
      });
    }
    if (sparks.current.length > SPARKS) sparks.current.splice(0, sparks.current.length - SPARKS);
  };

  useFrame((state, delta) => {
    const now = performance.now();
    const { lock, started, startAt, strainAt, setAt } = live.current;
    const t = now - startAt;
    const active = lock.over ? -1 : lock.set;
    const opened = lastSeen.current.openAt === -Infinity ? 0 : Math.min(1, (now - lastSeen.current.openAt) / OPEN_MS);
    const turn = -(1 - Math.pow(1 - opened, 3)) * PLUG_TURN;

    // Pins: the active one rocks on the pick, set ones sit at the shear line, the rest wait low.
    params.pins.forEach((pin, i) => {
      let target = SHEAR_Y - REST_DROP;
      if (i < lock.set) target = SHEAR_Y;
      else if (started && i === active) target = SHEAR_Y + (pinHeight(pin, t - lock.wokeAt) - pin.center) * TRAVEL;
      const y = i === active ? target : THREE.MathUtils.damp(pinY.current[i], target, 14, delta);
      pinY.current[i] = y;
      // Opened, the key pins turn with the plug and part from the drivers at the shear line.
      const keyPin = keyPins.current[i];
      if (keyPin) {
        const rel = y - PLUG_Y;
        keyPin.position.set(0, PLUG_Y + rel * Math.cos(turn), rel * Math.sin(turn));
        keyPin.rotation.x = turn;
      }
      const driver = drivers.current[i];
      if (driver) driver.position.setY(y + DRIVER_H / 2);
      const spring = springs.current[i];
      if (spring) {
        spring.position.setY(y + DRIVER_H);
        spring.scale.setY(Math.max(0.05, HOUSING_TOP - (y + DRIVER_H)));
      }
      const glow = pinGlows.current[i];
      if (glow) {
        const sinceSet = now - setAt;
        const justSet = i === lock.set - 1 && sinceSet < FLASH_MS;
        glow.emissiveIntensity = i < lock.set ? (justSet ? 2.2 * (1 - sinceSet / FLASH_MS) + 0.35 : 0.35) : 0;
      }
    });

    // The shear band over the active pin: how wide it is, pulsing.
    if (band.current && bandMat.current) {
      band.current.visible = started && active >= 0;
      if (active >= 0) {
        const pin = params.pins[active];
        band.current.position.x = pinX(active, count);
        band.current.scale.y = Math.max(0.01, pin.width * TRAVEL * 2);
        const inside = Math.abs(pinY.current[active] - SHEAR_Y) <= pin.width * TRAVEL;
        bandMat.current.opacity = (inside ? 0.85 : 0.35) + Math.sin(now * 0.01) * 0.08;
      }
    }

    // The pick slides under the active pin and lifts it; a strain bends it red.
    const goal = active >= 0 ? pinX(active, count) : pickX.current;
    pickX.current = THREE.MathUtils.damp(pickX.current, goal, PICK_SLIDE, delta);
    const sinceStrain = now - strainAt;
    const strain = sinceStrain < FLASH_MS ? 1 - sinceStrain / FLASH_MS : 0;
    const liftY = active >= 0 ? pinY.current[active] - KEY_PIN_H - KEY_TIP_H : SHEAR_Y - REST_DROP - KEY_PIN_H;
    if (pick.current && pickShaft.current && pickHook.current) {
      const dx = pickX.current - PICK_PIVOT.x;
      const dy = liftY - 0.035 - PICK_PIVOT.y;
      pick.current.rotation.z = Math.atan2(dy, dx) - strain * 0.12;
      const len = Math.hypot(dx, dy);
      pickShaft.current.scale.x = len;
      pickShaft.current.position.x = len / 2;
      if (!brokenHook.current) pickHook.current.position.x = len;
      pickMaterial.emissiveIntensity = strain * 1.6;
    }

    // Effects for what just happened.
    const seen = lastSeen.current;
    const tipWorld = new THREE.Vector3(pickX.current, liftY, FACE_Z + 0.05);
    if (strainAt !== seen.strainAt) {
      seen.strainAt = strainAt;
      burst(tipWorld, SPARK_HOT, 14, 1.1);
    }
    if (setAt !== seen.setAt) {
      seen.setAt = setAt;
      burst(new THREE.Vector3(pinX(lock.set - 1, count), SHEAR_Y, FACE_Z + 0.05), SPARK_GOLD, 10, 0.6);
    }
    if (lock.over === 'broke' && !seen.broke && pickHook.current) {
      seen.broke = true;
      brokenHook.current = { vel: new THREE.Vector3(0.4, 0.9, 0.6), spin: 9 };
      burst(tipWorld, SPARK_HOT, 22, 1.5);
    }
    if (lock.over === 'open' && seen.openAt === -Infinity) {
      seen.openAt = now;
      burst(new THREE.Vector3(0, SHEAR_Y, FACE_Z + 0.05), SPARK_GOLD, 26, 1.2);
    }

    // The snapped hook tumbles away.
    if (brokenHook.current && pickHook.current) {
      const b = brokenHook.current;
      b.vel.y += GRAVITY * delta;
      pickHook.current.position.addScaledVector(b.vel, delta);
      pickHook.current.rotation.z += b.spin * delta;
    }

    // Opened: the plug turns, the bolt slides back.
    const open = seen.openAt === -Infinity ? 0 : Math.min(1, (now - seen.openAt) / OPEN_MS);
    const eased = 1 - Math.pow(1 - open, 3);
    if (plug.current) plug.current.rotation.x = -eased * PLUG_TURN;
    if (bolt.current) bolt.current.position.x = 1.12 + eased * 0.42;

    // A jolt on a strain.
    if (rig.current) {
      const shake = sinceStrain < SHAKE_MS ? (1 - sinceStrain / SHAKE_MS) * 0.03 : 0;
      rig.current.position.x = Math.sin(now * 0.09) * shake;
      rig.current.position.y = Math.cos(now * 0.13) * shake * 0.6;
    }

    // Candlelight, and a flash for whatever just happened.
    if (candle.current) candle.current.intensity = 6 + Math.sin(now * 0.011) * 0.9 + Math.sin(now * 0.037) * 0.6;
    if (flashLight.current) {
      const sinceSet = now - setAt;
      const gold = sinceSet < FLASH_MS ? 1 - sinceSet / FLASH_MS : 0;
      flashLight.current.color.set(strain > gold ? '#ff5a2a' : '#ffd27a');
      flashLight.current.intensity = Math.max(strain, gold, open > 0 ? 1 - open * 0.5 : 0) * 6;
      flashLight.current.position.set(pickX.current, SHEAR_Y + 0.1, 0.6);
    }

    // Sparks.
    sparkSprites.current.forEach((sprite, i) => {
      if (!sprite) return;
      const s = sparks.current[i];
      if (!s) {
        sprite.visible = false;
        return;
      }
      s.life += delta;
      s.vel.y += GRAVITY * delta;
      s.pos.addScaledVector(s.vel, delta);
      const k = 1 - s.life / s.max;
      sprite.visible = k > 0;
      sprite.position.copy(s.pos);
      sprite.scale.setScalar(0.05 + 0.1 * k);
      (sprite.material as THREE.SpriteMaterial).color.copy(s.color);
      (sprite.material as THREE.SpriteMaterial).opacity = Math.max(0, k);
    });
    sparks.current = sparks.current.filter((s) => s.life < s.max);

    // A slow breath of the camera; a push in when it opens.
    state.camera.position.x = Math.sin(now * 0.0004) * 0.06;
    state.camera.position.z = CAMERA_Z - eased * 0.3;
    state.camera.lookAt(0, 0.08, 0);
  });

  const housingH = HOUSING_TOP - SHEAR_Y;
  return (
    <>
      <color attach="background" args={['#0a0807']} />
      <fog attach="fog" args={['#0a0807', 6, 12]} />
      <hemisphereLight args={['#c8b8a0', '#20160e', 1.1]} />
      <directionalLight position={[-2.5, 2.5, 3]} intensity={1.6} color="#ffe2bc" />
      <pointLight ref={candle} position={[-1.6, 1.2, 1.6]} color="#ffb46a" distance={6} decay={1} />
      <directionalLight position={[2.5, 1.2, -1]} intensity={1.1} color="#7d9cff" />
      {/* A pool of light on the works */}
      <spotLight position={[0.4, 1.9, 2.6]} angle={0.42} penumbra={0.7} intensity={14} distance={8} decay={1} color="#ffe8c8" />
      <pointLight ref={flashLight} distance={2.5} decay={1} intensity={0} />
      <Environment resolution={64} frames={1}>
        <Lightformer form="rect" intensity={2.2} color="#ffbf80" position={[-3, 2, 3]} scale={[3, 2, 1]} />
        <Lightformer form="rect" intensity={0.8} color="#6c86ff" position={[3, 1, -2]} scale={[2, 3, 1]} />
        <Lightformer form="ring" intensity={0.6} color="#ffffff" position={[0, 3, 2]} scale={1.5} />
      </Environment>

      {/* The door behind */}
      <mesh position={[0, 0, -0.45]} material={materials.planks}>
        <planeGeometry args={[7, 4.6]} />
      </mesh>
      {[-1.25, 1.35].map((y) => (
        <mesh key={y} position={[0, y, -0.42]} material={materials.ironDark}>
          <boxGeometry args={[7, 0.22, 0.04]} />
        </mesh>
      ))}

      <group ref={rig}>
        {/* The lock box, its rivets and the frame round the cut */}
        <RoundedBox args={[2.7, 1.75, 0.42]} radius={0.07} smoothness={3} position={[0, 0.1, -0.2]} material={materials.iron} />
        {[
          [-1.2, 0.83],
          [1.2, 0.83],
          [-1.2, -0.63],
          [1.2, -0.63],
        ].map(([x, y]) => (
          <mesh key={`${x},${y}`} position={[x, y, 0.02]} material={materials.ironDark}>
            <sphereGeometry args={[0.05, 12, 8]} />
          </mesh>
        ))}
        <mesh position={[0, 0.1, 0.004]} material={materials.chamber}>
          <planeGeometry args={[2.18, 1.32]} />
        </mesh>
        {(
          [
            [0, 0.79, 2.3, 0.07],
            [0, -0.59, 2.3, 0.07],
            [-1.12, 0.1, 0.07, 1.45],
            [1.12, 0.1, 0.07, 1.45],
          ] as const
        ).map(([x, y, w, h]) => (
          <mesh key={`${x},${y}`} position={[x, y, 0.04]} material={materials.ironDark}>
            <boxGeometry args={[w, h, 0.08]} />
          </mesh>
        ))}

        {/* The housing's cut face, its channels */}
        <mesh position={[0, SHEAR_Y + housingH / 2, FACE_Z - 0.002]} material={materials.cut}>
          <planeGeometry args={[PLUG_LEN, housingH]} />
        </mesh>
        {params.pins.map((_, i) => (
          <mesh key={i} position={[pinX(i, count), SHEAR_Y + housingH / 2, FACE_Z]} material={materials.chamber}>
            <planeGeometry args={[CHANNEL_W, housingH - 0.03]} />
          </mesh>
        ))}

        {/* The plug: a brass half-cylinder cut open, a keyway, the pins' holes through it */}
        <group ref={plug} position={[0, PLUG_Y, FACE_Z]}>
          <mesh rotation={[0, 0, Math.PI / 2]} material={materials.brass}>
            <cylinderGeometry args={[PLUG_R, PLUG_R, PLUG_LEN, 40, 1, false, Math.PI / 2, Math.PI]} />
          </mesh>
          <mesh position={[0, 0, 0.001]} material={materials.brass}>
            <planeGeometry args={[PLUG_LEN, PLUG_R * 2]} />
          </mesh>
          <mesh position={[0, -0.04, 0.003]} material={materials.chamber}>
            <planeGeometry args={[PLUG_LEN - 0.04, 0.12]} />
          </mesh>
          {params.pins.map((_, i) => (
            <mesh key={i} position={[pinX(i, count), (SHEAR_Y - PLUG_Y) / 2 + 0.01, 0.004]} material={materials.chamber}>
              <planeGeometry args={[CHANNEL_W, SHEAR_Y - PLUG_Y - 0.02 + 0.04]} />
            </mesh>
          ))}
        </group>
        {/* The shear line: a fine seam of light */}
        <mesh position={[0, SHEAR_Y, FACE_Z + 0.006]}>
          <planeGeometry args={[PLUG_LEN, 0.008]} />
          <meshBasicMaterial color="#ffd680" transparent opacity={0.5} toneMapped={false} />
        </mesh>

        {/* The bolt, slid back when the lock opens */}
        <mesh ref={bolt} position={[1.12, PLUG_Y, FACE_Z - 0.02]} material={materials.steel}>
          <boxGeometry args={[0.5, 0.16, 0.12]} />
        </mesh>

        {/* Pins and springs */}
        {params.pins.map((_, i) => (
          <group key={i} position={[pinX(i, count), 0, FACE_Z + 0.008]}>
            <group
              ref={(el) => {
                keyPins.current[i] = el;
              }}
              position={[0, SHEAR_Y - REST_DROP, 0]}
            >
              <mesh position={[0, -KEY_PIN_H / 2, 0]}>
                <cylinderGeometry args={[PIN_R, PIN_R, KEY_PIN_H, 16]} />
                <meshStandardMaterial
                  ref={(m) => {
                    pinGlows.current[i] = m;
                  }}
                  map={textures.brass}
                  color={BRASS}
                  metalness={0.85}
                  roughness={0.26}
                  emissive="#ffc24a"
                  emissiveIntensity={0}
                />
              </mesh>
              <mesh position={[0, -KEY_PIN_H - KEY_TIP_H / 2, 0]} rotation={[Math.PI, 0, 0]} material={materials.brass}>
                <coneGeometry args={[PIN_R, KEY_TIP_H, 16]} />
              </mesh>
            </group>
            <mesh
              ref={(el) => {
                drivers.current[i] = el;
              }}
              material={materials.steel}
            >
              <cylinderGeometry args={[PIN_R, PIN_R, DRIVER_H, 16]} />
            </mesh>
            <mesh
              ref={(el) => {
                springs.current[i] = el;
              }}
              geometry={springGeometry}
              material={materials.spring}
            />
          </group>
        ))}

        {/* The shear band over the active pin */}
        <mesh ref={band} position={[0, SHEAR_Y, FACE_Z + 0.07]} visible={false}>
          <planeGeometry args={[CHANNEL_W + 0.06, 1]} />
          <meshBasicMaterial
            ref={bandMat}
            color="#ffcf5a"
            transparent
            opacity={0.5}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </mesh>

        {/* The tension wrench, and the pick in the keyway */}
        <group position={[-PLUG_LEN / 2 - 0.02, PLUG_Y + 0.05, FACE_Z + 0.02]}>
          <mesh position={[-0.06, 0, 0]} material={materials.steel}>
            <boxGeometry args={[0.14, 0.035, 0.02]} />
          </mesh>
          <mesh position={[-0.13, -0.3, 0]} material={materials.steel}>
            <boxGeometry args={[0.035, 0.62, 0.02]} />
          </mesh>
        </group>
        <group ref={pick} position={PICK_PIVOT.toArray()}>
          <mesh position={[-0.28, 0, 0]} rotation={[0, 0, Math.PI / 2]} material={materials.leather}>
            <cylinderGeometry args={[0.045, 0.05, 0.5, 12]} />
          </mesh>
          <mesh ref={pickShaft} material={pickMaterial}>
            <boxGeometry args={[1, 0.03, 0.02]} />
          </mesh>
          <group ref={pickHook}>
            <mesh position={[0.005, 0.035, 0]} rotation={[0, 0, 0.35]} material={pickMaterial}>
              <boxGeometry args={[0.028, 0.08, 0.02]} />
            </mesh>
          </group>
        </group>

        {/* Sparks */}
        {Array.from({ length: SPARKS }, (_, i) => (
          <sprite
            key={i}
            ref={(el) => {
              sparkSprites.current[i] = el;
            }}
            visible={false}
          >
            <spriteMaterial
              map={textures.glow}
              transparent
              depthWrite={false}
              blending={THREE.AdditiveBlending}
              toneMapped={false}
            />
          </sprite>
        ))}
      </group>

      {/* The candle's glow at the edge of the light */}
      <sprite position={[-2.1, 1.35, 0.4]} scale={[1.6, 1.6, 1]}>
        <spriteMaterial
          map={textures.glow}
          color="#ff9a40"
          transparent
          opacity={0.18}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </sprite>
    </>
  );
};

export default LockScene;
