import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { mulberry32 } from '../pages/BattlePage/Arena3D/textures';
import { SQUARE, type RoomInfo } from './dioramaLayout';
import { Fire, FLOOR_THICKNESS, WALL_HEIGHT, WALL_THICKNESS } from './DioramaPieces';
import { createSwirlTexture } from './decorTextures';

/*
  What stands in a room, by its kind — the landmark that tells the party where
  it is. Most of them move a little: a fountain's jets, a statue's tears, a
  trap's spikes and blade, a portal's vortex, a trader swaying behind the
  counter. A room the party is done with shows it: the chest stands open and
  empty, the campfire has burnt down to embers, the altar's candles are out,
  the trap is still, the lair's fires are dead. On low graphics the smoke,
  sparks and drops are left out.
*/

type Vec3 = [number, number, number];

/* ── Shared bits ── */

const STONE = '#77777d';
const STONE_PALE = '#8a8a90';
const STONE_DARK = '#5a5458';
const WOOD = '#5a3a1e';
const WOOD_DARK = '#3a2414';
const IRON = '#2a2420';
const STEEL = '#9a9aa2';
const GOLD = '#d4a83a';
const BONE = '#d8ccb0';
const CLOTH = '#6e1c1c';
const PAPER = '#d8c8a0';
const WATER = '#3d6a86';

interface MatOptions {
  metal?: number;
  rough?: number;
  /** Emissive strength in its own colour. */
  glow?: number;
  side?: THREE.Side;
}

/** Plain materials are shared by every room: one per colour and finish. */
const MATERIALS = new Map<string, THREE.MeshStandardMaterial>();
const mat = (color: string, { metal = 0, rough = 0.8, glow = 0, side = THREE.FrontSide }: MatOptions = {}) => {
  const key = `${color}|${metal}|${rough}|${glow}|${side}`;
  let m = MATERIALS.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({
      color,
      metalness: metal,
      roughness: rough,
      emissive: glow > 0 ? color : '#000000',
      emissiveIntensity: glow,
      side,
      toneMapped: glow < 1.5,
    });
    MATERIALS.set(key, m);
  }
  return m;
};
const metal = (color: string) => mat(color, { metal: 0.75, rough: 0.35 });

/** A material of its own for something that pulses; dropped with its owner. */
const useOwnMaterial = (make: () => THREE.MeshStandardMaterial) => {
  const m = useMemo(make, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => m.dispose(), [m]);
  return m;
};

/** The inner face of the far (north) wall, in room coordinates. */
const northZ = (room: RoomInfo) => -room.size[1] / 2 + WALL_THICKNESS / 2;

interface WispsProps {
  position: Vec3;
  glow: THREE.Texture;
  count?: number;
  height?: number;
  spread?: number;
  size?: number;
  color?: string;
  opacity?: number;
  /** World units per second. */
  speed?: number;
  additive?: boolean;
  /** Falling (dust) instead of rising (smoke, steam, sparks). */
  fall?: boolean;
  seed?: number;
}

/** Soft sprites drifting up — smoke, steam, sparks — or settling down, like dust. */
const Wisps = ({
  position,
  glow,
  count = 5,
  height = 0.35,
  spread = 0.03,
  size = 0.08,
  color = '#8a8a8a',
  opacity = 0.35,
  speed = 0.12,
  additive = false,
  fall = false,
  seed = 1,
}: WispsProps) => {
  const sprites = useRef<(THREE.Sprite | null)[]>([]);
  const motes = useMemo(() => {
    const rand = mulberry32(seed * 7919 + count);
    return Array.from({ length: count }, () => ({
      phase: rand(),
      x: (rand() - 0.5) * 2 * spread,
      z: (rand() - 0.5) * 2 * spread,
      drift: (rand() - 0.5) * 0.1,
    }));
  }, [count, spread, seed]);
  useFrame(({ clock }) => {
    motes.forEach((m, i) => {
      const s = sprites.current[i];
      if (!s) return;
      const t = ((clock.elapsedTime * speed) / height + m.phase) % 1;
      s.position.set(m.x + m.drift * t, (fall ? 1 - t : t) * height, m.z);
      const k = size * (fall ? 1 : 0.5 + t);
      s.scale.set(k, k, 1);
      (s.material as THREE.SpriteMaterial).opacity = Math.sin(Math.PI * t) * opacity;
    });
  });
  return (
    <group position={position}>
      {motes.map((_, i) => (
        <sprite
          key={i}
          ref={(el) => {
            sprites.current[i] = el;
          }}
        >
          <spriteMaterial
            map={glow}
            color={color}
            transparent
            opacity={0}
            depthWrite={false}
            blending={additive ? THREE.AdditiveBlending : THREE.NormalBlending}
            toneMapped={!additive}
          />
        </sprite>
      ))}
    </group>
  );
};

/** Glints winking on and off at random spots in a cylinder: treasure, magic. */
const Twinkles = ({
  glow,
  position,
  radius,
  height,
  count = 8,
  size = 0.06,
  color = '#ffe08a',
  seed = 1,
}: {
  glow: THREE.Texture;
  position: Vec3;
  radius: number;
  height: number;
  count?: number;
  size?: number;
  color?: string;
  seed?: number;
}) => {
  const sprites = useRef<(THREE.Sprite | null)[]>([]);
  const spots = useMemo(() => {
    const rand = mulberry32(seed * 104729 + count);
    return Array.from({ length: count }, () => {
      const a = rand() * Math.PI * 2;
      const r = Math.sqrt(rand()) * radius;
      return { p: [Math.cos(a) * r, rand() * height, Math.sin(a) * r] as Vec3, phase: rand() * 10, rate: 1.5 + rand() * 2 };
    });
  }, [count, radius, height, seed]);
  useFrame(({ clock }) => {
    spots.forEach((s, i) => {
      const k = Math.max(0, Math.sin(clock.elapsedTime * s.rate + s.phase));
      sprites.current[i]?.scale.setScalar(size * k * k * k + 0.0001);
    });
  });
  return (
    <group position={position}>
      {spots.map((s, i) => (
        <sprite
          key={i}
          position={s.p}
          ref={(el) => {
            sprites.current[i] = el;
          }}
        >
          <spriteMaterial map={glow} color={color} transparent depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
        </sprite>
      ))}
    </group>
  );
};

/** Rings spreading over still water where something drips into it. */
const Ripples = ({
  position,
  count = 2,
  size = 0.06,
  period = 1.2,
  color = '#cfe6ff',
  seed = 0,
}: {
  position: Vec3;
  count?: number;
  size?: number;
  period?: number;
  color?: string;
  seed?: number;
}) => {
  const rings = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(({ clock }) => {
    rings.current.forEach((m, i) => {
      if (!m) return;
      const t = ((clock.elapsedTime + seed) / period + i / count) % 1;
      m.scale.setScalar(0.2 + t);
      (m.material as THREE.MeshBasicMaterial).opacity = (1 - t) * 0.55;
    });
  });
  return (
    <group position={position}>
      {Array.from({ length: count }, (_, i) => (
        <mesh
          key={i}
          rotation={[-Math.PI / 2, 0, 0]}
          ref={(el) => {
            rings.current[i] = el;
          }}
        >
          <ringGeometry args={[size * 0.82, size, 24]} />
          <meshBasicMaterial color={color} transparent opacity={0} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
};

/** A cloth hanging from an iron bar on the far wall; it stirs in the draught. Plain — no device on it. */
const Banner = ({ x, z, color, torn = false, seed }: { x: number; z: number; color: string; torn?: boolean; seed: number }) => {
  const cloth = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (cloth.current) cloth.current.rotation.x = Math.sin(clock.elapsedTime * 1.3 + seed) * 0.05;
  });
  const fabric = mat(color, { side: THREE.DoubleSide });
  return (
    <group position={[x, FLOOR_THICKNESS + WALL_HEIGHT * 0.86, z + 0.012]}>
      <mesh material={metal(IRON)}>
        <boxGeometry args={[0.15, 0.012, 0.012]} />
      </mesh>
      <group ref={cloth}>
        {torn ? (
          [0.21, 0.14, 0.24, 0.17].map((h, i) => (
            <mesh key={i} position={[-0.045 + i * 0.03, -h / 2, 0.006]} material={fabric}>
              <planeGeometry args={[0.029, h]} />
            </mesh>
          ))
        ) : (
          <>
            <mesh position={[0, -0.12, 0.006]} material={fabric}>
              <planeGeometry args={[0.12, 0.24]} />
            </mesh>
            {[-0.2, -0.04].map((y) => (
              <mesh key={y} position={[0, y, 0.008]} material={metal(GOLD)}>
                <boxGeometry args={[0.12, 0.01, 0.002]} />
              </mesh>
            ))}
            {/* A fringe along the bottom */}
            {Array.from({ length: 6 }, (_, i) => (
              <mesh key={`f${i}`} position={[-0.05 + i * 0.02, -0.255, 0.006]} material={metal(GOLD)}>
                <boxGeometry args={[0.004, 0.03, 0.002]} />
              </mesh>
            ))}
          </>
        )}
      </group>
    </group>
  );
};

/** An iron bowl of fire on a stand; cold and smoking once its room is done with. */
const Brazier = ({
  position,
  flame,
  glow,
  lit,
  seed,
  size = 0.22,
  low,
}: {
  position: Vec3;
  flame: THREE.Texture;
  glow: THREE.Texture;
  lit: boolean;
  seed: number;
  size?: number;
  low: boolean;
}) => (
  <group position={position}>
    <mesh position={[0, 0.1, 0]} material={metal(IRON)}>
      <cylinderGeometry args={[0.04, 0.06, 0.2, 10]} />
    </mesh>
    <mesh position={[0, 0.22, 0]} material={metal(IRON)}>
      <cylinderGeometry args={[0.08, 0.05, 0.05, 12]} />
    </mesh>
    {lit ? (
      <Fire position={[0, 0.32, 0]} flame={flame} glow={glow} seed={seed} size={size} />
    ) : (
      !low && <Wisps position={[0, 0.25, 0]} glow={glow} count={4} height={0.35} size={0.08} opacity={0.25} seed={seed} />
    )}
  </group>
);

/* ── Entrance ── */

/** Where the stairs up stand: in the middle, or aside from a back corner a passage has taken. */
const stairsX = (passages: number) => (!backRightFree(passages) && backLeftFree(passages) ? -STAIRS_SHIFT : 0);
const STAIRS_SHIFT = 0.15;

const EntranceStairs = ({ x }: { x: number }) => (
  <group position={[x, FLOOR_THICKNESS, -0.25]}>
    {[0, 1, 2].map((i) => (
      <mesh key={i} position={[0, 0.03 + i * 0.05, -i * 0.08]} material={mat(STONE, { rough: 0.85 })}>
        <boxGeometry args={[0.5, 0.06 + i * 0.1, 0.12]} />
      </mesh>
    ))}
  </group>
);

/** Daylight falling down the stairs from the world above, dust turning in it. */
const LightShaft = ({ x, glow, low }: { x: number; glow: THREE.Texture; low: boolean }) => (
  <group position={[x, FLOOR_THICKNESS, -0.3]}>
    <mesh position={[0, 0.55, 0]}>
      <cylinderGeometry args={[0.12, 0.3, 1.1, 20, 1, true]} />
      <meshBasicMaterial
        color="#ffe6b0"
        transparent
        opacity={0.06}
        depthWrite={false}
        side={THREE.DoubleSide}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </mesh>
    {!low && (
      <Wisps position={[0, 0.02, 0]} glow={glow} count={8} height={0.8} spread={0.15} size={0.025} color="#ffe6b0" opacity={0.8} speed={0.04} additive seed={7} />
    )}
  </group>
);

/** The way-in table: a map with a route inked on it and a candle. */
const MapTable = ({ position, flame, glow }: { position: Vec3; flame: THREE.Texture; glow: THREE.Texture }) => (
  <group position={position}>
    <mesh position={[0, 0.12, 0]} material={mat(WOOD)}>
      <boxGeometry args={[0.24, 0.015, 0.16]} />
    </mesh>
    {[-1, 1].flatMap((sx) =>
      [-1, 1].map((sz) => (
        <mesh key={`${sx}${sz}`} position={[sx * 0.1, 0.06, sz * 0.06]} material={mat(WOOD_DARK)}>
          <boxGeometry args={[0.015, 0.12, 0.015]} />
        </mesh>
      )),
    )}
    <mesh position={[0.01, 0.1285, 0.01]} rotation={[-Math.PI / 2, 0, 0.15]} material={mat(PAPER, { rough: 0.95 })}>
      <planeGeometry args={[0.17, 0.12]} />
    </mesh>
    <mesh position={[0.03, 0.129, 0.01]} rotation={[-Math.PI / 2, 0, 0.6]} material={mat(CLOTH)}>
      <planeGeometry args={[0.08, 0.004]} />
    </mesh>
    <mesh position={[-0.09, 0.148, -0.05]} material={mat('#e8dcc0', { rough: 0.7 })}>
      <cylinderGeometry args={[0.01, 0.011, 0.04, 8]} />
    </mesh>
    <Fire position={[-0.09, 0.185, -0.05]} flame={flame} glow={glow} seed={3} size={0.05} />
  </group>
);

const Entrance = ({ room, flame, glow, low, passages }: RoomProps) => {
  const x = stairsX(passages);
  const half = room.size[0] / 2;
  return (
    <>
      <EntranceStairs x={x} />
      <LightShaft x={x} glow={glow} low={low} />
      {/* Either side of the stairs, clear of the torches at the wall's ends */}
      {half > 0.55 && [-1, 1].map((s) => <Banner key={s} x={s * 0.32} z={northZ(room)} color="#5a1a1a" seed={s} />)}
      <MapTable position={[-half + 0.22, FLOOR_THICKNESS, 0.05]} flame={flame} glow={glow} />
    </>
  );
};

/* ── Battle ── */

const Bones = ({ seed }: { seed: number }) => {
  const rand = mulberry32(seed);
  return (
    <>
      {Array.from({ length: 6 }, (_, i) => (
        <mesh
          key={i}
          position={[(rand() - 0.5) * 0.8, FLOOR_THICKNESS + 0.015, (rand() - 0.5) * 0.8]}
          rotation={[Math.PI / 2, 0, rand() * Math.PI]}
          material={mat(BONE, { rough: 0.7 })}
        >
          <cylinderGeometry args={[0.012, 0.012, 0.12 + rand() * 0.06, 6]} />
        </mesh>
      ))}
      <mesh position={[0.25, FLOOR_THICKNESS + 0.03, -0.2]} material={mat(BONE, { rough: 0.7 })}>
        <sphereGeometry args={[0.035, 10, 8]} />
      </mesh>
    </>
  );
};

const Barrel = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    <mesh position={[0, 0.08, 0]} material={mat('#5e3e20', { rough: 0.85 })}>
      <cylinderGeometry args={[0.07, 0.07, 0.16, 14]} />
    </mesh>
    {[0.03, 0.13].map((y) => (
      <mesh key={y} position={[0, y, 0]} rotation={[Math.PI / 2, 0, 0]} material={metal(IRON)}>
        <torusGeometry args={[0.072, 0.008, 6, 16]} />
      </mesh>
    ))}
  </group>
);

const WeaponRack = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    <mesh position={[0, 0.12, 0]} material={mat('#4a2e16')}>
      <boxGeometry args={[0.32, 0.03, 0.04]} />
    </mesh>
    {[-0.1, 0, 0.1].map((x, i) => (
      <mesh key={x} position={[x, 0.14, 0.02]} rotation={[0.15, 0, (i - 1) * 0.08]} material={metal(STEEL)}>
        <boxGeometry args={[0.015, 0.26, 0.01]} />
      </mesh>
    ))}
  </group>
);

/** A breastplate and helm on a wooden stand. */
const ArmorStand = ({ position, turn = 0 }: { position: Vec3; turn?: number }) => (
  <group position={position} rotation={[0, turn, 0]}>
    <mesh position={[0, 0.01, 0]} material={mat(WOOD_DARK)}>
      <boxGeometry args={[0.1, 0.02, 0.1]} />
    </mesh>
    <mesh position={[0, 0.13, 0]} material={mat(WOOD)}>
      <cylinderGeometry args={[0.009, 0.009, 0.24, 6]} />
    </mesh>
    <mesh position={[0, 0.19, 0]} material={metal(STEEL)}>
      <cylinderGeometry args={[0.055, 0.045, 0.1, 12]} />
    </mesh>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.06, 0.235, 0]} material={metal(STEEL)}>
        <sphereGeometry args={[0.028, 10, 8]} />
      </mesh>
    ))}
    <mesh position={[0, 0.265, 0]} material={metal(STEEL)}>
      <sphereGeometry args={[0.036, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
    </mesh>
    <mesh position={[0, 0.3, 0]} material={mat(CLOTH)}>
      <boxGeometry args={[0.008, 0.03, 0.05]} />
    </mesh>
  </group>
);

/** A log with sharpened stakes crossed over it, barring half the room. */
const Barricade = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    <mesh position={[0, 0.035, 0]} rotation={[Math.PI / 2, 0, 0]} material={mat(WOOD)}>
      <cylinderGeometry args={[0.03, 0.03, 0.34, 8]} />
    </mesh>
    {[-0.12, 0, 0.12].flatMap((z) =>
      [-1, 1].map((s) => (
        <group key={`${z}${s}`} position={[0, 0.06, z]} rotation={[0, 0, s * 0.7]}>
          <mesh position={[0, 0.06, 0]} material={mat(WOOD_DARK)}>
            <cylinderGeometry args={[0.009, 0.009, 0.14, 6]} />
          </mesh>
          <mesh position={[0, 0.14, 0]} material={mat(BONE)}>
            <coneGeometry args={[0.009, 0.025, 6]} />
          </mesh>
        </group>
      )),
    )}
  </group>
);

/** Four stone columns standing in from the corners of a large hall. */
const HallColumns = ({ room }: { room: RoomInfo }) => {
  const dx = room.size[0] / 2 - SQUARE * 0.9;
  const dz = room.size[1] / 2 - SQUARE * 0.9;
  return (
    <>
      {[-1, 1].flatMap((sx) =>
        [-1, 1].map((sz) => (
          <group key={`${sx}${sz}`} position={[sx * dx, FLOOR_THICKNESS, sz * dz]}>
            <mesh position={[0, 0.02, 0]} material={mat('#6e6e74', { rough: 0.85 })}>
              <boxGeometry args={[0.14, 0.04, 0.14]} />
            </mesh>
            <mesh position={[0, 0.24, 0]} material={mat('#86868c')}>
              <cylinderGeometry args={[0.05, 0.055, 0.44, 12]} />
            </mesh>
          </group>
        )),
      )}
    </>
  );
};

/**
  Stairs, drops and lifts to other floors take a room's corners, back-right
  first, then back-left (see DungeonPassages' spotOf): corner furniture gives way.
*/
const backRightFree = (passages: number) => passages < 1;
const backLeftFree = (passages: number) => passages < 2;

const isBig = (room: RoomInfo) => Math.min(room.size[0], room.size[1]) >= 4 * SQUARE - 0.001;
/** Where corner furniture stands: in from the walls by a little over half a square. */
const inset = (room: RoomInfo): [number, number] => [room.size[0] / 2 - SQUARE * 0.6, room.size[1] / 2 - SQUARE * 0.6];

const Battle = ({ room, passages }: RoomProps) => {
  const [hx, hz] = inset(room);
  const nz = northZ(room);
  const spread = room.size[0] * 0.18;
  return (
    <>
      <Bones seed={room.id * 13} />
      {backLeftFree(passages) && <WeaponRack position={[-hx + 0.15, FLOOR_THICKNESS, -hz]} />}
      {isBig(room) && <HallColumns room={room} />}
      {backRightFree(passages) && <Barrel position={[hx, FLOOR_THICKNESS, -hz]} />}
      {[-1, 1].map((s) => (
        <Banner key={s} x={s * spread} z={nz} color="#4a2a1a" torn seed={room.id + s} />
      ))}
      <ArmorStand position={[hx, FLOOR_THICKNESS, 0.02]} turn={-Math.PI / 2} />
      <Barricade position={[-hx + 0.02, FLOOR_THICKNESS, 0.1]} />
    </>
  );
};

/* ── Boss ── */

/** The lair: a ring of glowing embers on the floor between two braziers; cold once the boss is down. */
const BossDais = ({ flame, glow, done, low }: { flame: THREE.Texture; glow: THREE.Texture; done: boolean; low: boolean }) => {
  const ember = useOwnMaterial(
    () => new THREE.MeshStandardMaterial({ color: '#c2541a', emissive: '#ff6a1a', emissiveIntensity: 1.2, roughness: 0.6 }),
  );
  const light = useRef<THREE.PointLight>(null);
  useFrame(({ clock }) => {
    ember.emissiveIntensity = done ? 0.12 : 1.2 + Math.sin(clock.elapsedTime * 2) * 0.3;
    ember.color.set(done ? '#3a2a24' : '#c2541a');
    if (light.current) light.current.intensity = done ? 0 : 3;
  });
  return (
    <group position={[0, FLOOR_THICKNESS, 0]}>
      <mesh position={[0, 0.03, 0.1]} material={mat('#4a4448')}>
        <cylinderGeometry args={[0.42, 0.45, 0.06, 32]} />
      </mesh>
      <mesh position={[0, 0.062, 0.1]} rotation={[-Math.PI / 2, 0, 0]} material={ember}>
        <circleGeometry args={[0.33, 32]} />
      </mesh>
      {[-0.32, 0.32].map((x, i) => (
        <Brazier key={x} position={[x, 0, -0.42]} flame={flame} glow={glow} lit={!done} seed={20 + i} low={low} />
      ))}
      {done && !low && <Wisps position={[0, 0.07, 0.1]} glow={glow} count={6} height={0.4} spread={0.2} size={0.1} opacity={0.2} seed={5} />}
      <pointLight ref={light} position={[0, 0.5, 0]} color="#ff7a2a" intensity={3} distance={3} decay={1.6} />
    </group>
  );
};

/** A throne of bones behind the dais. */
const BoneThrone = ({ position }: { position: Vec3 }) => {
  const dark = mat('#3a3034');
  return (
    <group position={position}>
      <mesh position={[0, 0.03, 0]} material={mat(STONE_DARK)}>
        <boxGeometry args={[0.32, 0.06, 0.2]} />
      </mesh>
      <mesh position={[0, 0.1, 0.01]} material={dark}>
        <boxGeometry args={[0.2, 0.08, 0.15]} />
      </mesh>
      <mesh position={[0, 0.25, -0.06]} material={dark}>
        <boxGeometry args={[0.2, 0.3, 0.035]} />
      </mesh>
      {[-0.08, -0.04, 0, 0.04, 0.08].map((x, i) => (
        <mesh key={x} position={[x, 0.42 + (i === 2 ? 0.04 : i % 2) * 0.02, -0.06]} material={mat(BONE)}>
          <coneGeometry args={[0.014, 0.1 + (i === 2 ? 0.06 : 0), 6]} />
        </mesh>
      ))}
      {[-1, 1].map((s) => (
        <group key={s}>
          <mesh position={[s * 0.115, 0.15, 0.01]} material={dark}>
            <boxGeometry args={[0.03, 0.03, 0.15]} />
          </mesh>
          <mesh position={[s * 0.115, 0.18, 0.08]} material={mat(BONE)}>
            <sphereGeometry args={[0.025, 10, 8]} />
          </mesh>
        </group>
      ))}
    </group>
  );
};

const Boss = ({ room, flame, glow, done, low }: RoomProps) => {
  const [, hz] = inset(room);
  return (
    <>
      <BossDais flame={flame} glow={glow} done={done} low={low} />
      <HallColumns room={room} />
      <Bones seed={room.id * 17} />
      <BoneThrone position={[0, FLOOR_THICKNESS, -hz]} />
    </>
  );
};

/* ── Treasure ── */

/** The chest: light leaking at its seam and glints round it; open and empty once looted. */
const TreasureChest = ({ glow, done, low }: { glow: THREE.Texture; done: boolean; low: boolean }) => {
  const lid = useRef<THREE.Group>(null);
  const seam = useOwnMaterial(
    () => new THREE.MeshStandardMaterial({ color: '#ffd27a', emissive: '#ffb43a', emissiveIntensity: 1.5, toneMapped: false }),
  );
  useFrame(({ clock }, delta) => {
    if (lid.current) {
      const target = done ? -1.9 : 0;
      lid.current.rotation.x += (target - lid.current.rotation.x) * Math.min(1, delta * 3);
    }
    seam.emissiveIntensity = done ? 0 : 1.2 + Math.sin(clock.elapsedTime * 2.5) * 0.5;
  });
  const wood = mat('#5a3518', { rough: 0.7 });
  return (
    <group position={[0, FLOOR_THICKNESS, 0]}>
      <mesh position={[0, 0.07, 0]} material={wood}>
        <boxGeometry args={[0.3, 0.14, 0.2]} />
      </mesh>
      {[-0.1, 0.1].map((x) => (
        <mesh key={x} position={[x, 0.07, 0]} material={metal(GOLD)}>
          <boxGeometry args={[0.025, 0.142, 0.205]} />
        </mesh>
      ))}
      <mesh position={[0, 0.11, 0.102]} material={metal(GOLD)}>
        <boxGeometry args={[0.04, 0.05, 0.01]} />
      </mesh>
      {/* Inside: dark and empty, seen when the lid is up */}
      <mesh position={[0, 0.136, 0]} material={mat('#140c06')}>
        <boxGeometry args={[0.28, 0.004, 0.18]} />
      </mesh>
      <mesh position={[0, 0.142, 0]} material={seam}>
        <boxGeometry args={[0.29, 0.006, 0.19]} />
      </mesh>
      {/* The lid, hinged at the back */}
      <group ref={lid} position={[0, 0.14, -0.1]}>
        <group position={[0, 0, 0.1]}>
          <mesh rotation={[0, 0, Math.PI / 2]} material={mat('#6b4220', { rough: 0.6 })}>
            <cylinderGeometry args={[0.1, 0.1, 0.3, 14, 1, false, 0, Math.PI]} />
          </mesh>
          {[-0.1, 0.1].map((x) => (
            <mesh key={x} position={[x, 0, 0]} rotation={[0, 0, Math.PI / 2]} material={metal(GOLD)}>
              <cylinderGeometry args={[0.103, 0.103, 0.025, 14, 1, false, 0, Math.PI]} />
            </mesh>
          ))}
        </group>
      </group>
      {!done && !low && <Twinkles glow={glow} position={[0, 0.05, 0]} radius={0.25} height={0.3} count={9} seed={11} />}
    </group>
  );
};

const CoinPile = ({ position, size = 1 }: { position: Vec3; size?: number }) => (
  <mesh position={[position[0], position[1] + 0.025 * size, position[2]]} scale={[size, size * 0.5, size]}>
    <sphereGeometry args={[0.07, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
    <meshStandardMaterial color="#d4a83a" metalness={0.85} roughness={0.35} emissive="#3a2a08" />
  </mesh>
);

/** A golden cup; `tipped` lies on its side. */
const Goblet = ({ position, tipped = false, turn = 0 }: { position: Vec3; tipped?: boolean; turn?: number }) => (
  <group position={[position[0], position[1] + (tipped ? 0.022 : 0), position[2]]} rotation={[0, turn, tipped ? Math.PI / 2 : 0]}>
    <mesh position={[0, 0.002, 0]} material={metal(GOLD)}>
      <cylinderGeometry args={[0.02, 0.02, 0.004, 12]} />
    </mesh>
    <mesh position={[0, 0.018, 0]} material={metal(GOLD)}>
      <cylinderGeometry args={[0.005, 0.005, 0.03, 6]} />
    </mesh>
    <mesh position={[0, 0.045, 0]} material={mat(GOLD, { metal: 0.75, rough: 0.35, side: THREE.DoubleSide })}>
      <cylinderGeometry args={[0.022, 0.012, 0.03, 12, 1, true]} />
    </mesh>
  </group>
);

const GEM_COLORS = ['#5ad1ff', '#ff5a8a', '#8aff7a', '#c48aff'];

/** An open crate of glowing gems. */
const GemCrate = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    <mesh position={[0, 0.005, 0]} material={mat(WOOD)}>
      <boxGeometry args={[0.14, 0.01, 0.11]} />
    </mesh>
    {[
      [0, 0.055, [0.14, 0.06, 0.01]],
      [0, -0.055, [0.14, 0.06, 0.01]],
      [0.07, 0, [0.01, 0.06, 0.11]],
      [-0.07, 0, [0.01, 0.06, 0.11]],
    ].map(([x, z, size], i) => (
      <mesh key={i} position={[x as number, 0.03, z as number]} material={mat(WOOD_DARK)}>
        <boxGeometry args={size as Vec3} />
      </mesh>
    ))}
    {GEM_COLORS.map((c, i) => (
      <mesh
        key={c}
        position={[-0.035 + (i % 2) * 0.07, 0.05 + (i > 1 ? 0.01 : 0), -0.02 + Math.floor(i / 2) * 0.04]}
        rotation={[i, i * 2, 0]}
        material={mat(c, { glow: 0.9, rough: 0.2 })}
      >
        <octahedronGeometry args={[0.022 + (i % 3) * 0.004]} />
      </mesh>
    ))}
  </group>
);

/** A round shield leant against the wall, a sword stuck in the gold. */
const LeaningShield = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    <mesh position={[0, 0.07, 0]} rotation={[-0.35, 0, 0]} material={metal(STEEL)}>
      <cylinderGeometry args={[0.07, 0.07, 0.012, 16]} />
    </mesh>
    <mesh position={[0, 0.072, 0.022]} rotation={[-0.35 + Math.PI / 2, 0, 0]} material={metal(GOLD)}>
      <cylinderGeometry args={[0.02, 0.02, 0.01, 10]} />
    </mesh>
  </group>
);

const Treasure = ({ room, glow, done, low, passages }: RoomProps) => {
  const [hx, hz] = inset(room);
  return (
    <>
      <TreasureChest glow={glow} done={done} low={low} />
      <CoinPile position={[0.25, FLOOR_THICKNESS, 0.12]} />
      <CoinPile position={[-0.22, FLOOR_THICKNESS, 0.15]} size={0.7} />
      {isBig(room) && <CoinPile position={[0.1, FLOOR_THICKNESS, -0.3]} size={1.3} />}
      <Goblet position={[0.32, FLOOR_THICKNESS, 0.02]} />
      <Goblet position={[-0.3, FLOOR_THICKNESS, 0.02]} tipped turn={0.6} />
      {backLeftFree(passages) && <GemCrate position={[-hx + 0.05, FLOOR_THICKNESS, -hz + 0.05]} />}
      {backRightFree(passages) && <LeaningShield position={[hx - 0.02, FLOOR_THICKNESS, -hz]} />}
    </>
  );
};

/* ── Trap ── */

const SPIKE_ROWS = 4;
const SPIKE_STEP = 0.12;

/** A plate of spikes that shoot up row after row and sink back; still and sunk once the trap is passed. */
const SpikeField = ({ done }: { done: boolean }) => {
  const rows = useRef<(THREE.Group | null)[]>([]);
  useFrame(({ clock }) => {
    rows.current.forEach((g, i) => {
      if (!g) return;
      const up = done ? 0 : THREE.MathUtils.clamp(Math.sin(clock.elapsedTime * 2.2 - i * 0.7) * 2, 0, 1);
      g.position.y = -0.11 + up * 0.11;
    });
  });
  const first = -((SPIKE_ROWS - 1) * SPIKE_STEP) / 2;
  return (
    <group position={[0, FLOOR_THICKNESS, 0]}>
      <mesh position={[0, 0.006, 0]} material={mat('#5e5854', { metal: 0.5, rough: 0.55 })}>
        <boxGeometry args={[0.52, 0.012, 0.52]} />
      </mesh>
      {Array.from({ length: SPIKE_ROWS }, (_, r) => (
        <group
          key={r}
          position={[0, 0, first + r * SPIKE_STEP]}
          ref={(el) => {
            rows.current[r] = el;
          }}
        >
          {Array.from({ length: SPIKE_ROWS }, (_, c) => (
            <mesh key={c} position={[first + c * SPIKE_STEP, 0.072, 0]} material={mat('#6e6a66', { metal: 0.7, rough: 0.4 })}>
              <coneGeometry args={[0.025, 0.12, 6]} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
};

/** A blade swinging on a beam across the room; hanging still once the trap is passed. */
const Pendulum = ({ room, done }: { room: RoomInfo; done: boolean }) => {
  const arm = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (!arm.current) return;
    const target = done ? 0 : Math.sin(clock.elapsedTime * 1.6) * 0.9;
    arm.current.rotation.z += (target - arm.current.rotation.z) * 0.15;
  });
  const top = FLOOR_THICKNESS + WALL_HEIGHT * 0.95;
  return (
    <group>
      <mesh position={[0, top, 0]} material={mat(WOOD_DARK)}>
        <boxGeometry args={[0.035, 0.035, room.size[1]]} />
      </mesh>
      <group ref={arm} position={[0, top, pendulumZ(room)]}>
        <mesh position={[0, -0.12, 0]} material={metal(IRON)}>
          <cylinderGeometry args={[0.006, 0.006, 0.24, 6]} />
        </mesh>
        <mesh position={[0, -0.24, 0]} rotation={[-Math.PI / 2, 0, 0]} material={metal(STEEL)}>
          <cylinderGeometry args={[0.09, 0.09, 0.008, 20, 1, false, Math.PI / 2, Math.PI]} />
        </mesh>
      </group>
    </group>
  );
};
const pendulumZ = (room: RoomInfo) => -room.size[1] * 0.12;

/** Raised stone plates that sink when stepped on; one already down. */
const PressurePlates = ({ room }: { room: RoomInfo }) => {
  const [hx] = inset(room);
  const spots: [number, number, boolean][] = [
    [-hx + 0.05, 0.05, false],
    [hx - 0.05, -0.1, true],
  ];
  return (
    <>
      {spots.map(([x, z, down]) => (
        <mesh key={`${x}${z}`} position={[x, FLOOR_THICKNESS + (down ? 0.002 : 0.008), z]} material={mat(STONE_DARK)}>
          <boxGeometry args={[0.12, 0.016, 0.12]} />
        </mesh>
      ))}
    </>
  );
};

const Trap = ({ room, done }: RoomProps) => (
  <>
    <SpikeField done={done} />
    <Pendulum room={room} done={done} />
    <PressurePlates room={room} />
  </>
);

/* ── Event rooms: one landmark each ── */

type Landmark = 'fountain' | 'statue' | 'altar' | 'lectern' | 'well' | 'sarcophagus' | 'mirror';
const LANDMARKS: Landmark[] = ['fountain', 'statue', 'altar', 'lectern', 'well', 'sarcophagus', 'mirror'];
/** A room named for its landmark gets it; the rest take one by id. */
const LANDMARK_WORDS: [Landmark, RegExp][] = [
  ['altar', /алтар/i],
  ['statue', /стату|изваян/i],
  ['fountain', /фонтан|источник|родник/i],
  ['lectern', /книг|библиот|кафедр|фолиант|летопис/i],
  ['well', /колод/i],
  ['sarcophagus', /саркофаг|гробниц|гроб/i],
  ['mirror', /зеркал/i],
];
const eventLandmark = (room: RoomInfo): Landmark =>
  LANDMARK_WORDS.find(([, words]) => words.test(room.name ?? ''))?.[0] ?? LANDMARKS[room.id % LANDMARKS.length];

const FOUNTAIN_JETS = 4;
const DROPS_PER_JET = 5;
const FOUNTAIN_REACH = 0.24;

/** A round stone fountain: four jets arcing from the figure into the basin. Still and dull once its gift is taken. */
const Fountain = ({ done, low }: { done: boolean; low: boolean }) => {
  const drops = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(({ clock }) => {
    drops.current.forEach((d, i) => {
      if (!d) return;
      const jet = Math.floor(i / DROPS_PER_JET);
      const t = (clock.elapsedTime * 0.9 + (i % DROPS_PER_JET) / DROPS_PER_JET) % 1;
      const a = (jet / FOUNTAIN_JETS) * Math.PI * 2 + Math.PI / 4;
      d.position.set(Math.cos(a) * FOUNTAIN_REACH * t, 0.36 + 0.1 * t - 0.358 * t * t, Math.sin(a) * FOUNTAIN_REACH * t);
    });
  });
  const flowing = !done && !low;
  return (
    <group position={[0, FLOOR_THICKNESS, 0]}>
      <mesh position={[0, 0.05, 0]} material={mat(STONE_PALE)}>
        <cylinderGeometry args={[0.36, 0.38, 0.1, 28]} />
      </mesh>
      <mesh position={[0, 0.105, 0]} rotation={[Math.PI / 2, 0, 0]} material={mat(STONE_PALE)}>
        <torusGeometry args={[0.335, 0.025, 8, 32]} />
      </mesh>
      <mesh
        position={[0, 0.102, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        material={done ? mat('#2d3a40', { rough: 0.6 }) : mat(WATER, { metal: 0.3, rough: 0.15, glow: 0.25 })}
      >
        <circleGeometry args={[0.31, 28]} />
      </mesh>
      <mesh position={[0, 0.2, 0]} material={mat('#9a9aa0', { rough: 0.7 })}>
        <cylinderGeometry args={[0.05, 0.07, 0.25, 10]} />
      </mesh>
      <mesh position={[0, 0.36, 0]} material={mat('#9a9aa0', { rough: 0.7 })}>
        <sphereGeometry args={[0.06, 12, 10]} />
      </mesh>
      {flowing && (
        <>
          {Array.from({ length: FOUNTAIN_JETS * DROPS_PER_JET }, (_, i) => (
            <mesh
              key={i}
              ref={(el) => {
                drops.current[i] = el;
              }}
              material={mat('#a8d4ff', { glow: 0.5, rough: 0.1 })}
            >
              <sphereGeometry args={[0.012, 6, 5]} />
            </mesh>
          ))}
          {Array.from({ length: FOUNTAIN_JETS }, (_, j) => {
            const a = (j / FOUNTAIN_JETS) * Math.PI * 2 + Math.PI / 4;
            return (
              <Ripples
                key={j}
                position={[Math.cos(a) * FOUNTAIN_REACH, 0.104, Math.sin(a) * FOUNTAIN_REACH]}
                size={0.05}
                period={1.1}
                seed={j * 0.3}
              />
            );
          })}
        </>
      )}
    </group>
  );
};

/** Where a tear runs at share t of its way: from under the eyes, down the robe, onto the plinth. */
const tearAt = (side: number, t: number): Vec3 => {
  const y = 0.44 - t * 0.33;
  const z = y > 0.4 ? 0.055 : (0.1 * (0.41 - y)) / 0.32 + 0.012;
  return [side * (0.018 + t * 0.02), y, z];
};

/** A hooded figure on a plinth — the weeping statue, its tears glowing; dry once its gift is taken. */
const Statue = ({ done, low }: { done: boolean; low: boolean }) => {
  const tears = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(({ clock }) => {
    tears.current.forEach((m, i) => {
      if (!m) return;
      const t = (clock.elapsedTime * 0.35 + i * 0.5) % 1;
      m.position.set(...tearAt(i % 2 ? 1 : -1, t));
    });
  });
  const crying = !done && !low;
  return (
    <group position={[0, FLOOR_THICKNESS, 0]}>
      <mesh position={[0, 0.05, 0]} material={mat(STONE)}>
        <boxGeometry args={[0.3, 0.1, 0.3]} />
      </mesh>
      <mesh position={[0, 0.25, 0]} material={mat('#9a9aa2', { rough: 0.75 })}>
        <coneGeometry args={[0.1, 0.32, 14]} />
      </mesh>
      <mesh position={[0, 0.43, 0]} material={mat('#9a9aa2', { rough: 0.75 })}>
        <sphereGeometry args={[0.055, 12, 10]} />
      </mesh>
      <mesh position={[0, 0.445, -0.01]} rotation={[-0.3, 0, 0]} material={mat('#86868c', { rough: 0.75 })}>
        <sphereGeometry args={[0.062, 12, 10, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
      </mesh>
      {/* The pool its tears have worn into the plinth */}
      <mesh position={[0, 0.101, 0.11]} rotation={[-Math.PI / 2, 0, 0]} material={done ? mat('#4a4a50') : mat('#8ac4ff', { glow: 0.6 })}>
        <circleGeometry args={[0.045, 18]} />
      </mesh>
      {crying && (
        <>
          {[0, 1, 2, 3].map((i) => (
            <mesh
              key={i}
              ref={(el) => {
                tears.current[i] = el;
              }}
              material={mat('#bfe0ff', { glow: 2 })}
              scale={[1, 1.6, 1]}
            >
              <sphereGeometry args={[0.012, 6, 5]} />
            </mesh>
          ))}
          <Ripples position={[0, 0.103, 0.11]} count={2} size={0.04} period={1.4} color="#bfe0ff" />
        </>
      )}
    </group>
  );
};

/** A stone altar with a cloth, candles, a smoking offering bowl and a rune turning above it. Cold once used. */
const Altar = ({ flame, glow, done, low }: { flame: THREE.Texture; glow: THREE.Texture; done: boolean; low: boolean }) => {
  const rune = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (!rune.current) return;
    rune.current.rotation.y = clock.elapsedTime * 0.8;
    rune.current.position.y = 0.48 + Math.sin(clock.elapsedTime * 1.5) * 0.02;
  });
  return (
    <group position={[0, FLOOR_THICKNESS, -0.1]}>
      <mesh position={[0, 0.09, 0]} material={mat('#5a5458', { rough: 0.85 })}>
        <boxGeometry args={[0.46, 0.18, 0.22]} />
      </mesh>
      <mesh position={[0, 0.185, 0]} material={mat('#6e6670')}>
        <boxGeometry args={[0.5, 0.02, 0.26]} />
      </mesh>
      <mesh position={[0, 0.197, 0]} material={mat(CLOTH)}>
        <boxGeometry args={[0.14, 0.004, 0.265]} />
      </mesh>
      <mesh position={[0, 0.13, 0.1325]} material={mat(CLOTH, { side: THREE.DoubleSide })}>
        <planeGeometry args={[0.14, 0.13]} />
      </mesh>
      {[-0.16, 0, 0.16].map((x, i) => (
        <group key={x} position={[x, 0.2, -0.04]}>
          <mesh position={[0, done ? 0.015 : 0.03, 0]} material={mat('#e8dcc0', { rough: 0.7 })}>
            <cylinderGeometry args={[0.015, 0.017, done ? 0.03 : 0.06, 8]} />
          </mesh>
          {done ? (
            !low && <Wisps position={[0, 0.03, 0]} glow={glow} count={2} height={0.18} size={0.03} opacity={0.3} seed={40 + i} />
          ) : (
            <Fire position={[0, 0.09, 0]} flame={flame} glow={glow} seed={40 + i} size={0.07} />
          )}
        </group>
      ))}
      {/* The offering bowl, incense rising from it */}
      <mesh position={[0, 0.21, 0.07]} material={metal('#8a6a3a')}>
        <cylinderGeometry args={[0.04, 0.025, 0.025, 14]} />
      </mesh>
      {!done && !low && <Wisps position={[0, 0.225, 0.07]} glow={glow} count={5} height={0.3} size={0.05} opacity={0.3} speed={0.06} seed={9} />}
      {!done && (
        <group ref={rune} position={[0, 0.48, 0]}>
          <mesh rotation={[Math.PI / 2, 0, 0]} material={mat('#b07aff', { glow: 1.8 })}>
            <torusGeometry args={[0.065, 0.006, 6, 32]} />
          </mesh>
          <mesh material={mat('#d8b8ff', { glow: 1.8 })}>
            <octahedronGeometry args={[0.025]} />
          </mesh>
          {!low && <pointLight color="#b07aff" intensity={0.35} distance={0.6} />}
        </group>
      )}
      <mesh position={[0, 0.002, 0.3]} rotation={[-Math.PI / 2, 0, 0]} material={mat('#8a1a1a', { glow: done ? 0 : 0.3 })}>
        <ringGeometry args={[0.18, 0.22, 32]} />
      </mesh>
    </group>
  );
};

/** A lectern with a book floating open above it, its pages glowing; closed on the stand once read. */
const Lectern = ({ glow, done, low }: { glow: THREE.Texture; done: boolean; low: boolean }) => {
  const book = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (!book.current) return;
    book.current.position.y = 0.36 + Math.sin(clock.elapsedTime * 1.2) * 0.02;
    book.current.rotation.y = Math.sin(clock.elapsedTime * 0.4) * 0.3;
  });
  return (
    <group position={[0, FLOOR_THICKNESS, -0.05]}>
      <mesh position={[0, 0.01, 0]} material={mat(WOOD_DARK)}>
        <boxGeometry args={[0.14, 0.02, 0.14]} />
      </mesh>
      <mesh position={[0, 0.11, 0]} material={mat(WOOD)}>
        <cylinderGeometry args={[0.02, 0.025, 0.2, 8]} />
      </mesh>
      <mesh position={[0, 0.22, 0]} rotation={[0.35, 0, 0]} material={mat(WOOD)}>
        <boxGeometry args={[0.17, 0.012, 0.13]} />
      </mesh>
      {done ? (
        <mesh position={[0, 0.24, 0]} rotation={[0.35, 0, 0]} material={mat('#4a2414')}>
          <boxGeometry args={[0.1, 0.03, 0.13]} />
        </mesh>
      ) : (
        <group ref={book} position={[0, 0.36, 0]} rotation={[0.5, 0, 0]}>
          {[-1, 1].map((s) => (
            <group key={s} rotation={[0, 0, -s * 0.22]}>
              <mesh position={[s * 0.047, -0.004, 0]} material={mat('#4a2414')}>
                <boxGeometry args={[0.094, 0.006, 0.13]} />
              </mesh>
              <mesh position={[s * 0.045, 0.002, 0]} material={mat('#fff0c8', { glow: 0.7 })}>
                <boxGeometry args={[0.088, 0.006, 0.122]} />
              </mesh>
            </group>
          ))}
          <sprite scale={[0.3, 0.3, 1]}>
            <spriteMaterial map={glow} color="#ffd88a" transparent opacity={0.45} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
          </sprite>
        </group>
      )}
      {!done && !low && <Twinkles glow={glow} position={[0, 0.25, 0]} radius={0.16} height={0.25} count={7} size={0.035} color="#ffe6a8" seed={13} />}
    </group>
  );
};

/** A stone well with a little roof, a bucket swinging on its rope, light glowing up from the water. */
const Well = ({ done }: { done: boolean }) => {
  const bucket = useRef<THREE.Group>(null);
  const water = useOwnMaterial(
    () => new THREE.MeshStandardMaterial({ color: '#2a5a7a', emissive: '#3a9aff', emissiveIntensity: 0.9, roughness: 0.2 }),
  );
  useFrame(({ clock }) => {
    if (bucket.current) bucket.current.rotation.z = Math.sin(clock.elapsedTime * 1.1) * 0.08;
    water.emissiveIntensity = done ? 0 : 0.7 + Math.sin(clock.elapsedTime * 1.6) * 0.3;
  });
  const stone = mat(STONE, { side: THREE.DoubleSide });
  return (
    <group position={[0, FLOOR_THICKNESS, 0]}>
      <mesh position={[0, 0.07, 0]} material={stone}>
        <cylinderGeometry args={[0.17, 0.18, 0.14, 20, 1, true]} />
      </mesh>
      <mesh position={[0, 0.07, 0]} material={mat(STONE_DARK, { side: THREE.DoubleSide })}>
        <cylinderGeometry args={[0.13, 0.13, 0.14, 20, 1, true]} />
      </mesh>
      <mesh position={[0, 0.14, 0]} rotation={[-Math.PI / 2, 0, 0]} material={mat(STONE_PALE)}>
        <ringGeometry args={[0.13, 0.175, 24]} />
      </mesh>
      <mesh position={[0, 0.06, 0]} rotation={[-Math.PI / 2, 0, 0]} material={water}>
        <circleGeometry args={[0.13, 20]} />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * 0.16, 0.17, 0]} material={mat(WOOD)}>
          <boxGeometry args={[0.025, 0.34, 0.025]} />
        </mesh>
      ))}
      <mesh position={[0, 0.3, 0]} rotation={[0, 0, Math.PI / 2]} material={mat(WOOD_DARK)}>
        <cylinderGeometry args={[0.012, 0.012, 0.34, 8]} />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={`r${s}`} position={[0, 0.375, s * 0.055]} rotation={[s * 0.75, 0, 0]} material={mat(WOOD_DARK, { side: THREE.DoubleSide })}>
          <planeGeometry args={[0.4, 0.15]} />
        </mesh>
      ))}
      <group ref={bucket} position={[0, 0.3, 0]}>
        <mesh position={[0, -0.07, 0]} material={metal(IRON)}>
          <cylinderGeometry args={[0.003, 0.003, 0.14, 4]} />
        </mesh>
        <mesh position={[0, -0.16, 0]} material={mat(WOOD)}>
          <cylinderGeometry args={[0.03, 0.025, 0.04, 10]} />
        </mesh>
      </group>
    </group>
  );
};

/** A stone coffin, its lid pushed a little aside and green mist creeping out; pushed off once opened. */
const Sarcophagus = ({ glow, done, low }: { glow: THREE.Texture; done: boolean; low: boolean }) => (
  <group position={[0, FLOOR_THICKNESS, -0.05]}>
    <mesh position={[0, 0.015, 0]} material={mat(STONE_DARK)}>
      <boxGeometry args={[0.28, 0.03, 0.5]} />
    </mesh>
    <mesh position={[0, 0.09, 0]} material={mat(STONE)}>
      <boxGeometry args={[0.22, 0.12, 0.44]} />
    </mesh>
    <group position={[done ? 0.13 : 0.035, done ? 0.12 : 0.165, 0]} rotation={[0, done ? 0.35 : 0.06, done ? -0.35 : 0]}>
      <mesh material={mat(STONE_PALE)}>
        <boxGeometry args={[0.24, 0.03, 0.46]} />
      </mesh>
      <mesh position={[0, 0.02, 0]} material={mat(STONE)}>
        <boxGeometry args={[0.16, 0.012, 0.36]} />
      </mesh>
      <mesh position={[0, 0.03, -0.13]} material={mat(STONE)}>
        <sphereGeometry args={[0.035, 10, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
      </mesh>
    </group>
    {!done && !low && (
      <Wisps position={[-0.1, 0.16, 0]} glow={glow} count={6} height={0.22} spread={0.12} size={0.07} color="#7aff9a" opacity={0.35} speed={0.05} additive seed={17} />
    )}
  </group>
);

/** A tall mirror in a dark frame, its glass shimmering violet; dull and grey once looked into. */
const Mirror = ({ glow, done, low }: { glow: THREE.Texture; done: boolean; low: boolean }) => {
  const glass = useOwnMaterial(
    () => new THREE.MeshStandardMaterial({ color: '#b8c4d8', metalness: 1, roughness: 0.06, emissive: '#6a4aa8', emissiveIntensity: 0.3 }),
  );
  useFrame(({ clock }) => {
    glass.emissiveIntensity = done ? 0 : 0.25 + Math.sin(clock.elapsedTime * 1.4) * 0.15;
    glass.roughness = done ? 0.8 : 0.06;
    glass.color.set(done ? '#4a4a50' : '#b8c4d8');
  });
  const frame = mat('#2e2228', { rough: 0.6 });
  return (
    <group position={[0, FLOOR_THICKNESS, -0.08]}>
      <mesh position={[0, 0.015, 0]} material={frame}>
        <boxGeometry args={[0.28, 0.03, 0.09]} />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * 0.125, 0.24, 0]} material={frame}>
          <boxGeometry args={[0.026, 0.42, 0.03]} />
        </mesh>
      ))}
      <mesh position={[0, 0.45, 0]} material={frame}>
        <torusGeometry args={[0.125, 0.014, 6, 20, Math.PI]} />
      </mesh>
      <mesh position={[0, 0.24, 0.004]} material={glass}>
        <planeGeometry args={[0.226, 0.42]} />
      </mesh>
      <mesh position={[0, 0.45, 0.004]} material={glass}>
        <circleGeometry args={[0.113, 20, 0, Math.PI]} />
      </mesh>
      {!done && !low && <Twinkles glow={glow} position={[0, 0.1, 0.05]} radius={0.15} height={0.45} count={7} size={0.04} color="#c8a8ff" seed={19} />}
    </group>
  );
};

const Event = ({ room, flame, glow, done, low }: RoomProps) => {
  switch (eventLandmark(room)) {
    case 'fountain':
      return (
        <>
          <Fountain done={done} low={low} />
          {isBig(room) && <HallColumns room={room} />}
        </>
      );
    case 'statue':
      return <Statue done={done} low={low} />;
    case 'altar':
      return <Altar flame={flame} glow={glow} done={done} low={low} />;
    case 'lectern':
      return <Lectern glow={glow} done={done} low={low} />;
    case 'well':
      return <Well done={done} />;
    case 'sarcophagus':
      return <Sarcophagus glow={glow} done={done} low={low} />;
    case 'mirror':
      return <Mirror glow={glow} done={done} low={low} />;
  }
};

/* ── Rest ── */

/** A campfire with a cauldron steaming on a tripod; burnt down to smoking embers once the party has rested. */
const Campfire = ({ flame, glow, done, low }: { flame: THREE.Texture; glow: THREE.Texture; done: boolean; low: boolean }) => {
  const embers = useOwnMaterial(
    () => new THREE.MeshStandardMaterial({ color: '#5a1a08', emissive: '#ff4a10', emissiveIntensity: 1.2, toneMapped: false }),
  );
  useFrame(({ clock }) => {
    embers.emissiveIntensity = 0.8 + Math.sin(clock.elapsedTime * 1.7) * 0.4;
  });
  return (
    <group position={[0, FLOOR_THICKNESS, 0]}>
      {[0, Math.PI / 2].map((r) => (
        <mesh key={r} position={[0, 0.025, 0]} rotation={[0, r, Math.PI / 2]} material={mat(WOOD_DARK, { rough: 0.9 })}>
          <cylinderGeometry args={[0.025, 0.025, 0.28, 8]} />
        </mesh>
      ))}
      {Array.from({ length: 8 }, (_, i) => (
        <mesh
          key={i}
          position={[Math.cos((i / 8) * Math.PI * 2) * 0.17, 0.02, Math.sin((i / 8) * Math.PI * 2) * 0.17]}
          material={mat('#5a5a5e', { rough: 0.9 })}
        >
          <sphereGeometry args={[0.03, 8, 6]} />
        </mesh>
      ))}
      {done ? (
        <>
          {[
            [0.03, 0.02],
            [-0.04, 0.01],
            [0.0, -0.04],
            [-0.02, 0.05],
          ].map(([x, z], i) => (
            <mesh key={i} position={[x, 0.05, z]} material={embers}>
              <sphereGeometry args={[0.018, 6, 5]} />
            </mesh>
          ))}
          {!low && <Wisps position={[0, 0.06, 0]} glow={glow} count={5} height={0.4} size={0.08} opacity={0.25} seed={23} />}
        </>
      ) : (
        <Fire position={[0, 0.14, 0]} flame={flame} glow={glow} seed={31} size={0.26} />
      )}
      {/* Tripod and cauldron */}
      {[0, 1, 2].map((i) => {
        const a = (i / 3) * Math.PI * 2 + 0.3;
        return (
          <mesh
            key={`leg${i}`}
            position={[Math.cos(a) * 0.08, 0.16, Math.sin(a) * 0.08]}
            rotation={[Math.sin(a) * 0.45, 0, -Math.cos(a) * 0.45]}
            material={mat(WOOD_DARK)}
          >
            <cylinderGeometry args={[0.008, 0.008, 0.36, 5]} />
          </mesh>
        );
      })}
      <mesh position={[0, 0.27, 0]} material={metal(IRON)}>
        <cylinderGeometry args={[0.003, 0.003, 0.08, 4]} />
      </mesh>
      <mesh position={[0, 0.22, 0]} material={metal(IRON)}>
        <sphereGeometry args={[0.055, 14, 8, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2]} />
      </mesh>
      <mesh position={[0, 0.22, 0]} rotation={[Math.PI / 2, 0, 0]} material={metal(IRON)}>
        <torusGeometry args={[0.055, 0.006, 6, 18]} />
      </mesh>
      {!done && !low && <Wisps position={[0, 0.23, 0]} glow={glow} count={5} height={0.3} spread={0.02} size={0.06} color="#d8d8d8" opacity={0.3} seed={29} />}
    </group>
  );
};

const Bedroll = ({ position, turn }: { position: Vec3; turn: number }) => (
  <group position={position} rotation={[0, turn, 0]}>
    <mesh position={[0, 0.02, 0]} material={mat('#5a4a3a', { rough: 0.95 })}>
      <boxGeometry args={[0.14, 0.035, 0.3]} />
    </mesh>
    <mesh position={[0, 0.04, -0.12]} rotation={[0, 0, Math.PI / 2]} material={mat('#6e5a46', { rough: 0.95 })}>
      <cylinderGeometry args={[0.03, 0.03, 0.14, 10]} />
    </mesh>
  </group>
);

const TENT_R = 0.15;

/** A canvas tent — a three-sided prism with its dark opening towards the players, the ridge pole showing at the ends. */
const Tent = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    <mesh position={[0, TENT_R / 2, 0]} rotation={[-Math.PI / 2, 0, 0]} material={mat('#6a6448', { side: THREE.DoubleSide })}>
      <cylinderGeometry args={[TENT_R, TENT_R, 0.32, 3, 1, true]} />
    </mesh>
    <mesh position={[0, TENT_R * 0.55, 0.161]} rotation={[0, 0, Math.PI / 2]} material={mat('#1a140e')}>
      <circleGeometry args={[TENT_R * 0.75, 3]} />
    </mesh>
    <mesh position={[0, TENT_R * 1.5, 0]} rotation={[Math.PI / 2, 0, 0]} material={mat(WOOD_DARK)}>
      <cylinderGeometry args={[0.008, 0.008, 0.4, 6]} />
    </mesh>
  </group>
);

/** Firewood stacked against the wall. */
const Woodpile = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    {[
      [-0.035, 0.025],
      [0.035, 0.025],
      [0, 0.07],
    ].map(([x, y], i) => (
      <mesh key={i} position={[x, y, 0]} rotation={[Math.PI / 2, 0, 0]} material={mat(i === 2 ? WOOD : WOOD_DARK)}>
        <cylinderGeometry args={[0.025, 0.025, 0.2, 8]} />
      </mesh>
    ))}
  </group>
);

const Rest = ({ room, flame, glow, done, low, passages }: RoomProps) => {
  const [hx, hz] = inset(room);
  return (
    <>
      <Campfire flame={flame} glow={glow} done={done} low={low} />
      <Bedroll position={[-hx + 0.1, FLOOR_THICKNESS, 0]} turn={0.2} />
      <Bedroll position={[hx - 0.1, FLOOR_THICKNESS, -0.05]} turn={-0.3} />
      <mesh position={[0, FLOOR_THICKNESS + 0.03, -0.27]} rotation={[0, 0, Math.PI / 2]} material={mat(WOOD)}>
        <cylinderGeometry args={[0.03, 0.03, 0.24, 8]} />
      </mesh>
      {backLeftFree(passages) && <Tent position={[-hx + 0.05, FLOOR_THICKNESS, -hz + 0.06]} />}
      {backRightFree(passages) && <Woodpile position={[hx, FLOOR_THICKNESS, -hz]} />}
    </>
  );
};

/* ── Merchant ── */

const TRADER_SCALE = 0.72;

/** The trader: a hunched, hooded old figure with a long beard, swaying behind the counter. */
const Trader = ({ position }: { position: Vec3 }) => {
  const body = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    if (!body.current) return;
    body.current.rotation.y = Math.sin(clock.elapsedTime * 0.5) * 0.25;
    body.current.rotation.x = Math.sin(clock.elapsedTime * 0.9) * 0.04;
  });
  const robe = mat('#5a4630');
  const hood = mat('#4a3a26', { side: THREE.DoubleSide });
  return (
    <group position={position} scale={TRADER_SCALE}>
      <group ref={body}>
        <mesh position={[0, 0.17, 0]} material={robe}>
          <coneGeometry args={[0.11, 0.32, 14]} />
        </mesh>
        <mesh position={[0, 0.28, 0.005]} rotation={[0.25, 0, 0]} material={robe}>
          <cylinderGeometry args={[0.05, 0.065, 0.1, 12]} />
        </mesh>
        <mesh position={[0, 0.2, 0]} rotation={[Math.PI / 2, 0, 0]} material={mat('#2a1a10')}>
          <torusGeometry args={[0.072, 0.007, 6, 18]} />
        </mesh>
        <mesh position={[0, 0.34, 0.02]} material={mat('#b3a383', { rough: 0.6 })}>
          <sphereGeometry args={[0.048, 12, 10]} />
        </mesh>
        <mesh position={[0, 0.355, 0.012]} rotation={[-0.4, 0, 0]} material={hood}>
          <sphereGeometry args={[0.058, 14, 10, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
        </mesh>
        <mesh position={[0, 0.335, 0.072]} rotation={[Math.PI / 2, 0, 0]} material={mat('#b3a383', { rough: 0.6 })}>
          <coneGeometry args={[0.011, 0.04, 6]} />
        </mesh>
        <mesh position={[0, 0.28, 0.055]} rotation={[Math.PI, 0, 0]} material={mat('#d8d0c0', { rough: 0.9 })}>
          <coneGeometry args={[0.03, 0.09, 8]} />
        </mesh>
        {[-1, 1].map((s) => (
          <mesh key={s} position={[s * 0.06, 0.24, 0.07]} material={mat('#b3a383', { rough: 0.6 })}>
            <sphereGeometry args={[0.016, 8, 6]} />
          </mesh>
        ))}
      </group>
    </group>
  );
};

const POTION_COLORS = ['#ff4a4a', '#4aa0ff', '#6aff8a'];

/** The stall: a plain counter with lanterns at its ends, potions and scales laid out for sale. */
const MerchantStall = ({ flame, glow }: { flame: THREE.Texture; glow: THREE.Texture }) => (
  <group position={[0, FLOOR_THICKNESS, -0.1]}>
    <mesh position={[0, 0.14, 0]} material={mat(WOOD)}>
      <boxGeometry args={[0.52, 0.03, 0.2]} />
    </mesh>
    <mesh position={[0, 0.07, 0.09]} material={mat(WOOD_DARK)}>
      <boxGeometry args={[0.52, 0.13, 0.02]} />
    </mesh>
    {/* Legs at the back corners; the front panel hides the others */}
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.24, 0.065, -0.08]} material={mat(WOOD_DARK)}>
        <boxGeometry args={[0.025, 0.13, 0.025]} />
      </mesh>
    ))}
    {POTION_COLORS.map((c, i) => (
      <group key={c} position={[-0.17 + i * 0.06, 0.155, 0.03]}>
        <mesh position={[0, 0.022, 0]} material={mat(c, { glow: 0.8, rough: 0.15 })}>
          <sphereGeometry args={[0.022, 10, 8]} />
        </mesh>
        <mesh position={[0, 0.05, 0]} material={mat('#c8d8e0', { rough: 0.2 })}>
          <cylinderGeometry args={[0.007, 0.009, 0.022, 6]} />
        </mesh>
      </group>
    ))}
    {/* Scales */}
    <group position={[0.1, 0.155, 0.01]}>
      <mesh position={[0, 0.04, 0]} material={metal(GOLD)}>
        <cylinderGeometry args={[0.004, 0.006, 0.08, 6]} />
      </mesh>
      <mesh position={[0, 0.08, 0]} material={metal(GOLD)}>
        <boxGeometry args={[0.11, 0.004, 0.004]} />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * 0.05, 0.055, 0]} material={metal(GOLD)}>
          <cylinderGeometry args={[0.02, 0.016, 0.004, 12]} />
        </mesh>
      ))}
    </group>
    <CoinPile position={[0.2, 0.155, 0.04]} size={0.35} />
    {/* Lanterns standing at the ends of the counter */}
    {[-1, 1].map((s, i) => (
      <group key={s} position={[s * 0.23, 0.155, -0.05]}>
        <mesh position={[0, 0.025, 0]} material={metal(IRON)}>
          <boxGeometry args={[0.035, 0.05, 0.035]} />
        </mesh>
        <mesh position={[0, 0.056, 0]} material={metal(IRON)}>
          <coneGeometry args={[0.026, 0.02, 4]} />
        </mesh>
        <Fire position={[0, 0.03, 0]} flame={flame} glow={glow} seed={60 + i} size={0.05} />
      </group>
    ))}
    <mesh position={[0.3, 0.08, 0.25]} material={mat('#6b4a26', { rough: 0.9 })}>
      <boxGeometry args={[0.16, 0.16, 0.16]} />
    </mesh>
  </group>
);

/** A rug laid out in front of the stall. */
const Rug = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    <mesh position={[0, 0.002, 0]} material={mat('#6a2a1a', { rough: 0.95 })}>
      <boxGeometry args={[0.42, 0.004, 0.26]} />
    </mesh>
    <mesh position={[0, 0.0045, 0]} material={mat('#a8743a', { rough: 0.95 })}>
      <boxGeometry args={[0.34, 0.004, 0.18]} />
    </mesh>
    <mesh position={[0, 0.007, 0]} material={mat('#3a1a10', { rough: 0.95 })}>
      <boxGeometry args={[0.16, 0.004, 0.08]} />
    </mesh>
  </group>
);

/** A sack of goods, tied at the neck. */
const Sack = ({ position }: { position: Vec3 }) => (
  <group position={position}>
    <mesh position={[0, 0.055, 0]} scale={[0.06, 0.065, 0.055]} material={mat('#8a7050', { rough: 0.95 })}>
      <sphereGeometry args={[1, 12, 10]} />
    </mesh>
    <mesh position={[0, 0.125, 0]} material={mat('#8a7050', { rough: 0.95 })}>
      <coneGeometry args={[0.025, 0.04, 8]} />
    </mesh>
    <mesh position={[0, 0.11, 0]} rotation={[Math.PI / 2, 0, 0]} material={mat('#3a2a18')}>
      <torusGeometry args={[0.018, 0.004, 4, 12]} />
    </mesh>
  </group>
);

const Merchant = ({ room, flame, glow, passages }: RoomProps) => {
  const [hx, hz] = inset(room);
  return (
    <>
      <MerchantStall flame={flame} glow={glow} />
      <Trader position={[0, FLOOR_THICKNESS, -0.25]} />
      <Rug position={[0, FLOOR_THICKNESS, 0.24]} />
      {backLeftFree(passages) && (
        <>
          <Barrel position={[-hx, FLOOR_THICKNESS, -hz]} />
          <Barrel position={[-hx + 0.16, FLOOR_THICKNESS, -hz + 0.04]} />
        </>
      )}
      {backRightFree(passages) && (
        <>
          <Sack position={[hx - 0.04, FLOOR_THICKNESS, -hz + 0.04]} />
          <Sack position={[hx - 0.14, FLOOR_THICKNESS, -hz]} />
        </>
      )}
    </>
  );
};

/* ── Teleport ── */

/** Blue: a calm ring of light. Red: a faster, throbbing ring. A spotted red portal is dead stone. */
const PORTAL_LOOKS = {
  blue: { color: '#6aa8ff', emissive: '#3a7aff', light: '#6aa8ff', spin: 0.8 },
  red: { color: '#ff5a48', emissive: '#ff2a1a', light: '#ff3a24', spin: -1.6 },
} as const;

const TeleportRing = ({ portal, spent }: { portal: 'blue' | 'red'; spent: boolean }) => {
  const ring = useRef<THREE.Mesh>(null);
  const light = useRef<THREE.PointLight>(null);
  const look = PORTAL_LOOKS[portal];
  useFrame(({ clock }) => {
    if (spent) return;
    if (ring.current) ring.current.rotation.z = clock.elapsedTime * look.spin;
    if (light.current && portal === 'red') light.current.intensity = 1.6 + Math.sin(clock.elapsedTime * 4) * 0.6;
  });
  return (
    <group position={[0, FLOOR_THICKNESS + 0.01, 0]}>
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.3, 0.025, 8, 40]} />
        {spent ? (
          <meshStandardMaterial color="#3a3436" roughness={0.9} />
        ) : (
          <meshStandardMaterial color={look.color} emissive={look.emissive} emissiveIntensity={1.4} toneMapped={false} />
        )}
      </mesh>
      {!spent && <pointLight ref={light} position={[0, 0.3, 0]} color={look.light} intensity={1.5} distance={2} />}
    </group>
  );
};

const RUNE_STONES = 4;
const ARCH_SPAN = 0.27;
const ARCH_POST = 0.34;

/** A stone arch over the ring with a vortex turning in it and rune stones circling; dead and fallen once a red one is seen through. */
const PortalArch = ({
  portal,
  spent,
  glow,
  low,
}: {
  portal: 'blue' | 'red';
  spent: boolean;
  glow: THREE.Texture;
  low: boolean;
}) => {
  const swirl = useMemo(createSwirlTexture, []);
  useEffect(() => () => swirl.dispose(), [swirl]);
  const vortex = useRef<THREE.Mesh>(null);
  const counter = useRef<THREE.Mesh>(null);
  const stones = useRef<(THREE.Mesh | null)[]>([]);
  const look = PORTAL_LOOKS[portal];
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (vortex.current) vortex.current.rotation.z = -t * look.spin * 1.5;
    if (counter.current) counter.current.rotation.z = t * look.spin * 0.9;
    if (spent || low) return;
    stones.current.forEach((s, i) => {
      if (!s) return;
      const a = t * 0.6 + (i / RUNE_STONES) * Math.PI * 2;
      s.position.set(Math.cos(a) * 0.42, 0.22 + Math.sin(t * 1.3 + i) * 0.05, Math.sin(a) * 0.22);
      s.rotation.set(t + i, t * 0.7, 0);
    });
  });
  const stone = mat(spent ? '#4a4648' : '#6e6a70', { rough: 0.85 });
  const rune = spent ? mat('#2a2628') : mat(look.color, { glow: 1.6 });
  return (
    <group position={[0, FLOOR_THICKNESS, 0]}>
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * ARCH_SPAN, ARCH_POST / 2, 0]} rotation={[0, 0, spent && s > 0 ? -0.06 : 0]} material={stone}>
          <boxGeometry args={[0.07, ARCH_POST, 0.07]} />
        </mesh>
      ))}
      <mesh position={[0, ARCH_POST, 0]} material={stone}>
        <torusGeometry args={[ARCH_SPAN, 0.035, 8, 20, Math.PI]} />
      </mesh>
      <mesh position={[0, ARCH_POST + ARCH_SPAN, 0.01]} material={rune}>
        <boxGeometry args={[0.06, 0.07, 0.06]} />
      </mesh>
      {!spent && (
        <group position={[0, 0.33, 0]} scale={[1, 1.15, 1]}>
          {[vortex, counter].map((ref, i) => (
            <mesh key={i} ref={ref} position={[0, 0, i * 0.004]} scale={i ? 0.8 : 1}>
              <circleGeometry args={[0.235, 32]} />
              <meshBasicMaterial
                map={swirl}
                color={look.color}
                transparent
                opacity={1}
                depthWrite={false}
                side={THREE.DoubleSide}
                blending={THREE.AdditiveBlending}
                toneMapped={false}
              />
            </mesh>
          ))}
          <sprite scale={[0.5, 0.5, 1]}>
            <spriteMaterial map={glow} color={look.color} transparent opacity={0.7} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
          </sprite>
        </group>
      )}
      {Array.from({ length: RUNE_STONES }, (_, i) => {
        const a = (i / RUNE_STONES) * Math.PI * 2;
        // Lying where they fell once the portal is dead.
        const rest: Vec3 = [Math.cos(a) * 0.42, 0.02, Math.sin(a) * 0.22];
        return (
          <mesh
            key={i}
            position={rest}
            ref={(el) => {
              stones.current[i] = el;
            }}
            material={rune}
          >
            <boxGeometry args={[0.04, 0.05, 0.03]} />
          </mesh>
        );
      })}
    </group>
  );
};

/* ── Fork and dead end ── */

/** A signpost with three arrows pointing three ways, a lantern on top. */
const Signpost = ({ flame, glow }: { flame: THREE.Texture; glow: THREE.Texture }) => (
  <group position={[0, FLOOR_THICKNESS, 0]}>
    <mesh position={[0, 0.02, 0]} material={mat(STONE)}>
      <cylinderGeometry args={[0.07, 0.09, 0.04, 10]} />
    </mesh>
    <mesh position={[0, 0.23, 0]} material={mat(WOOD)}>
      <cylinderGeometry args={[0.014, 0.016, 0.42, 8]} />
    </mesh>
    {[
      [0.36, 0.4],
      [0.3, -1.2],
      [0.24, 2.4],
    ].map(([y, turn]) => (
      <group key={turn} position={[0, y, 0]} rotation={[0, turn, 0]}>
        <mesh position={[0.1, 0, 0]} material={mat('#6a4a2a')}>
          <boxGeometry args={[0.17, 0.035, 0.012]} />
        </mesh>
        <mesh position={[0.2, 0, 0]} rotation={[0, 0, -Math.PI / 2]} material={mat('#6a4a2a')}>
          <coneGeometry args={[0.024, 0.035, 4]} />
        </mesh>
      </group>
    ))}
    <mesh position={[0, 0.455, 0]} material={metal(IRON)}>
      <boxGeometry args={[0.035, 0.045, 0.035]} />
    </mesh>
    <Fire position={[0, 0.46, 0]} flame={flame} glow={glow} seed={71} size={0.06} />
  </group>
);

const Rubble = ({ seed }: { seed: number }) => {
  const rand = mulberry32(seed);
  return (
    <>
      {Array.from({ length: 10 }, (_, i) => {
        const s = 0.05 + rand() * 0.08;
        return (
          <mesh
            key={i}
            position={[(rand() - 0.5) * 0.6, FLOOR_THICKNESS + s / 2, (rand() - 0.5) * 0.6 - 0.12]}
            rotation={[rand(), rand(), rand()]}
            material={mat('#6a686c', { rough: 0.95 })}
          >
            <boxGeometry args={[s, s, s]} />
          </mesh>
        );
      })}
      {[
        [-0.15, -0.22, 0.1],
        [0.18, -0.18, 0.08],
        [0.02, -0.3, 0.07],
      ].map(([x, z, r], i) => (
        <mesh key={`b${i}`} position={[x, FLOOR_THICKNESS + r * 0.8, z]} rotation={[i, i * 2, 0]} material={mat('#5e5c60', { rough: 0.95 })}>
          <dodecahedronGeometry args={[r]} />
        </mesh>
      ))}
    </>
  );
};

/** What is left of an earlier delver: bones slumped against the wall, a satchel and a scroll. */
const LostDelver = ({ position }: { position: Vec3 }) => (
  <group position={position} rotation={[0, Math.PI / 2, 0]}>
    <mesh position={[0, 0.16, -0.02]} rotation={[0.4, 0, 0.2]} material={mat(BONE, { rough: 0.7 })}>
      <sphereGeometry args={[0.035, 10, 8]} />
    </mesh>
    <mesh position={[0, 0.1, -0.03]} rotation={[Math.PI / 2 - 0.2, 0, 0]} material={mat(BONE, { rough: 0.7 })}>
      <torusGeometry args={[0.033, 0.006, 6, 14]} />
    </mesh>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.03, 0.015, 0.05]} rotation={[Math.PI / 2, 0, s * 0.15]} material={mat(BONE, { rough: 0.7 })}>
        <cylinderGeometry args={[0.009, 0.009, 0.13, 6]} />
      </mesh>
    ))}
    <mesh position={[0.08, 0.025, 0.02]} material={mat('#5a3a1e')}>
      <boxGeometry args={[0.06, 0.045, 0.035]} />
    </mesh>
    <mesh position={[-0.07, 0.01, 0.06]} rotation={[0, 0.5, Math.PI / 2]} material={mat(PAPER)}>
      <cylinderGeometry args={[0.01, 0.01, 0.06, 8]} />
    </mesh>
  </group>
);

/** The cave-in: rubble and boulders at the back, broken beams across them, dust sifting down. */
const CaveIn = ({ room, glow, low }: RoomProps) => (
  <>
    <Rubble seed={room.id * 7} />
    <mesh position={[-0.05, FLOOR_THICKNESS + 0.08, -0.15]} rotation={[0, 0.4, 0.25]} material={mat(WOOD_DARK)}>
      <boxGeometry args={[0.5, 0.04, 0.04]} />
    </mesh>
    <mesh position={[0.1, FLOOR_THICKNESS + 0.06, -0.05]} rotation={[0, -0.7, -0.15]} material={mat(WOOD)}>
      <boxGeometry args={[0.42, 0.035, 0.035]} />
    </mesh>
    <LostDelver position={[-room.size[0] / 2 + WALL_THICKNESS + 0.08, FLOOR_THICKNESS, 0.15]} />
    {!low && (
      <Wisps position={[0, FLOOR_THICKNESS, -0.12]} glow={glow} count={7} height={0.42} spread={0.22} size={0.025} color="#b8b0a0" opacity={0.6} speed={0.08} fall seed={room.id} />
    )}
  </>
);

/* ── By kind ── */

interface RoomProps {
  room: RoomInfo;
  flame: THREE.Texture;
  glow: THREE.Texture;
  /** The party is done with the room (see SessionBoard.cleared). */
  done: boolean;
  low: boolean;
  /** How many passages to other floors start here (they take the corners). */
  passages: number;
}

/** What stands in a room, by its kind. */
export const RoomFurnishing = ({
  room,
  flame,
  glow,
  portal,
  spent = false,
  done = false,
  lowGraphics = false,
  passages = 0,
}: {
  room: RoomInfo;
  flame: THREE.Texture;
  glow: THREE.Texture;
  /** A teleport room's portal colour. */
  portal?: 'blue' | 'red';
  /** A red portal the party has seen through: it no longer glows. */
  spent?: boolean;
  done?: boolean;
  lowGraphics?: boolean;
  passages?: number;
}) => {
  const props: RoomProps = { room, flame, glow, done, low: lowGraphics, passages };
  const content = (() => {
    switch (room.type) {
      case 'entrance':
        return <Entrance {...props} />;
      case 'battle':
        return <Battle {...props} />;
      case 'boss':
        return <Boss {...props} />;
      case 'treasure':
        return <Treasure {...props} />;
      case 'trap':
        return <Trap {...props} />;
      case 'event':
        return <Event {...props} />;
      case 'rest':
        return <Rest {...props} />;
      case 'merchant':
        return <Merchant {...props} />;
      case 'teleport':
        return (
          <>
            <TeleportRing portal={portal ?? 'blue'} spent={spent} />
            <PortalArch portal={portal ?? 'blue'} spent={spent} glow={glow} low={lowGraphics} />
          </>
        );
      case 'fork':
        return /колод/i.test(room.name ?? '') ? <Well done={false} /> : <Signpost flame={flame} glow={glow} />;
      case 'deadend':
        return <CaveIn {...props} />;
      default:
        return null;
    }
  })();
  return <group position={[room.center[0], 0, room.center[1]]}>{content}</group>;
};

/* ── Footprints ── */

/** Floor a piece of furniture takes up: a box (or, if round, a circle of radius hx) around a point, in board coordinates. */
export interface Footprint {
  x: number;
  z: number;
  hx: number;
  hz: number;
  round?: boolean;
}

/** Where RoomFurnishing's pieces stand, so figurines keep clear of them. Flat things (bones, rugs, rings) are left out. */
export const furnishingFootprints = (room: RoomInfo, passages = 0): Footprint[] => {
  const right = backRightFree(passages);
  const left = backLeftFree(passages);
  const when = (free: boolean, ...prints: Footprint[]) => (free ? prints : []);
  const big = isBig(room);
  const [hx, hz] = inset(room);
  const box = (x: number, z: number, w: number, d = w): Footprint => ({ x, z, hx: w, hz: d });
  const disc = (x: number, z: number, r: number): Footprint => ({ x, z, hx: r, hz: r, round: true });
  const columns = () => {
    const dx = room.size[0] / 2 - SQUARE * 0.9;
    const dz = room.size[1] / 2 - SQUARE * 0.9;
    return [-1, 1].flatMap((sx) => [-1, 1].map((sz) => disc(sx * dx, sz * dz, 0.07)));
  };
  const local = ((): Footprint[] => {
    switch (room.type) {
      case 'entrance':
        return [box(stairsX(passages), -0.33, 0.25, 0.1), box(-room.size[0] / 2 + 0.22, 0.05, 0.13, 0.09)];
      case 'battle':
        return [
          ...when(left, box(-hx + 0.15, -hz, 0.16, 0.04)),
          ...when(right, disc(hx, -hz, 0.07)),
          disc(hx, 0.02, 0.07),
          box(-hx + 0.02, 0.1, 0.07, 0.18),
          ...(big ? columns() : []),
        ];
      case 'boss':
        return [disc(0, 0.1, 0.45), disc(-0.32, -0.42, 0.08), disc(0.32, -0.42, 0.08), box(0, -hz, 0.16, 0.1), ...columns()];
      case 'treasure':
        return [
          box(0, 0, 0.15, 0.1),
          disc(0.25, 0.12, 0.07),
          disc(-0.22, 0.15, 0.05),
          disc(0.32, 0.02, 0.03),
          disc(-0.3, 0.02, 0.04),
          ...when(left, box(-hx + 0.05, -hz + 0.05, 0.08, 0.07)),
          ...when(right, disc(hx - 0.02, -hz, 0.07)),
          ...(big ? [disc(0.1, -0.3, 0.09)] : []),
        ];
      case 'trap':
        return [box(0, 0, 0.27), box(0, pendulumZ(room), 0.3, 0.05)];
      case 'event': {
        switch (eventLandmark(room)) {
          case 'fountain':
            return [disc(0, 0, 0.38), ...(big ? columns() : [])];
          case 'statue':
            return [box(0, 0, 0.15)];
          case 'altar':
            return [box(0, -0.1, 0.25, 0.13)];
          case 'lectern':
            return [box(0, -0.05, 0.09, 0.08)];
          case 'well':
            return [disc(0, 0, 0.2)];
          case 'sarcophagus':
            return [box(0, -0.05, 0.15, 0.25)];
          case 'mirror':
            return [box(0, -0.08, 0.14, 0.05)];
        }
        return [];
      }
      case 'rest':
        return [
          disc(0, 0, 0.2),
          box(-hx + 0.1, 0, 0.12, 0.17),
          box(hx - 0.1, -0.05, 0.12, 0.17),
          box(0, -0.27, 0.12, 0.03),
          ...when(left, box(-hx + 0.05, -hz + 0.06, 0.12, 0.17)),
          ...when(right, box(hx, -hz, 0.06, 0.1)),
        ];
      case 'merchant':
        return [
          box(0, -0.15, 0.27, 0.17),
          box(0.3, 0.15, 0.08),
          ...when(left, disc(-hx, -hz, 0.07), disc(-hx + 0.16, -hz + 0.04, 0.07)),
          ...when(right, disc(hx - 0.04, -hz + 0.04, 0.06), disc(hx - 0.14, -hz, 0.06)),
        ];
      case 'teleport':
        return [box(-ARCH_SPAN, 0, 0.045), box(ARCH_SPAN, 0, 0.045)];
      case 'fork':
        return [disc(0, 0, /колод/i.test(room.name ?? '') ? 0.2 : 0.09)];
      case 'deadend':
        return [disc(0, -0.12, 0.36), box(-room.size[0] / 2 + WALL_THICKNESS + 0.08, 0.15, 0.06, 0.1)];
      default:
        return [];
    }
  })();
  return local.map((f) => ({ ...f, x: f.x + room.center[0], z: f.z + room.center[1] }));
};
