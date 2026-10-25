import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { SQUARE, type RoomInfo } from './dioramaLayout';
import { FLOOR_THICKNESS } from './DioramaPieces';

/*
  The enemies of a room as carved miniatures in dark stone, built like the
  party's (see PartyMiniature): a base with a red ring, a figure in parts,
  glowing eyes. The server tells only how many wait in a room, so a room's
  figures take turns among four kinds — a skeleton with a rusty sword, a
  hooded cultist with a burning staff, an eared imp with a spear and a horned
  brute with a club. The boss is a winged demon lord with a greataxe, twice
  their size, on its dais. When the room is cleared they topple and sink into
  the board. All face the players' edge.
*/

const FIGURE_SCALE = 0.62;
const BOSS_SCALE = 1.9;
/** The carved figure on its base, as with the party's miniatures. */
const BODY_SCALE = 1.15;
/** Most figurines shown in one room, however many enemies wait there. */
const MAX_FIGURES = 5;
const TOPPLE_SECONDS = 0.6;
const SINK_SECONDS = 1.6;

const KINDS = ['skeleton', 'cultist', 'imp', 'brute'] as const;
type EnemyKind = (typeof KINDS)[number];

export interface EnemyKit {
  stone: THREE.MeshStandardMaterial;
  skin: THREE.MeshStandardMaterial;
  base: THREE.MeshStandardMaterial;
  bone: THREE.MeshStandardMaterial;
  eye: THREE.MeshStandardMaterial;
  ring: THREE.MeshStandardMaterial;
  rust: THREE.MeshStandardMaterial;
  iron: THREE.MeshStandardMaterial;
  wood: THREE.MeshStandardMaterial;
  robe: THREE.MeshStandardMaterial;
  flame: THREE.MeshStandardMaterial;
  wing: THREE.MeshStandardMaterial;
}

export const useEnemyKit = (): EnemyKit => {
  const kit = useMemo(
    () => ({
      stone: new THREE.MeshStandardMaterial({ color: '#6a4c42', roughness: 0.5, metalness: 0.1 }),
      skin: new THREE.MeshStandardMaterial({ color: '#5e6a3e', roughness: 0.55 }),
      base: new THREE.MeshStandardMaterial({ color: '#2a2020', roughness: 0.7 }),
      bone: new THREE.MeshStandardMaterial({ color: '#c9b79a', roughness: 0.55 }),
      eye: new THREE.MeshStandardMaterial({ color: '#ff3a1a', emissive: '#ff2a0a', emissiveIntensity: 2.2 }),
      ring: new THREE.MeshStandardMaterial({ color: '#a3241a', emissive: '#c0281a', emissiveIntensity: 0.6 }),
      rust: new THREE.MeshStandardMaterial({ color: '#6a4430', roughness: 0.6, metalness: 0.5 }),
      iron: new THREE.MeshStandardMaterial({ color: '#6a6a72', roughness: 0.35, metalness: 0.75 }),
      wood: new THREE.MeshStandardMaterial({ color: '#3a2616', roughness: 0.8 }),
      robe: new THREE.MeshStandardMaterial({ color: '#6e1c1c', roughness: 0.8, side: THREE.DoubleSide }),
      flame: new THREE.MeshStandardMaterial({ color: '#ff7a2a', emissive: '#ff5a1a', emissiveIntensity: 2, toneMapped: false }),
      wing: new THREE.MeshStandardMaterial({ color: '#2a1a1c', roughness: 0.7, side: THREE.DoubleSide }),
    }),
    [],
  );
  useEffect(() => () => Object.values(kit).forEach((m) => m.dispose()), [kit]);
  return kit;
};

const Eyes = ({ kit, y, z, gap = 0.02 }: { kit: EnemyKit; y: number; z: number; gap?: number }) => (
  <>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * gap, y, z]} material={kit.eye}>
        <sphereGeometry args={[0.011, 8, 6]} />
      </mesh>
    ))}
  </>
);

const Skeleton = ({ kit }: { kit: EnemyKit }) => (
  <>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.03, 0.08, 0]} material={kit.bone}>
        <cylinderGeometry args={[0.011, 0.011, 0.13, 6]} />
      </mesh>
    ))}
    <mesh position={[0, 0.155, 0]} material={kit.bone}>
      <boxGeometry args={[0.08, 0.025, 0.04]} />
    </mesh>
    <mesh position={[0, 0.215, -0.01]} material={kit.bone}>
      <cylinderGeometry args={[0.01, 0.01, 0.11, 6]} />
    </mesh>
    {/* Ribs */}
    {[
      [0.2, 0.038],
      [0.228, 0.044],
      [0.256, 0.04],
    ].map(([y, r]) => (
      <mesh key={y} position={[0, y, 0]} rotation={[Math.PI / 2, 0, 0]} material={kit.bone}>
        <torusGeometry args={[r, 0.006, 6, 14]} />
      </mesh>
    ))}
    {/* Skull with a jaw */}
    <mesh position={[0, 0.315, 0]} material={kit.bone}>
      <sphereGeometry args={[0.045, 12, 10]} />
    </mesh>
    <mesh position={[0, 0.285, 0.018]} material={kit.bone}>
      <boxGeometry args={[0.05, 0.018, 0.04]} />
    </mesh>
    <Eyes kit={kit} y={0.318} z={0.038} gap={0.017} />
    {/* Rusty sword and a battered round shield */}
    <group position={[0.075, 0.2, 0.03]} rotation={[0.35, 0, -0.2]}>
      <mesh position={[0, 0.08, 0]} material={kit.rust}>
        <boxGeometry args={[0.014, 0.16, 0.005]} />
      </mesh>
      <mesh material={kit.wood}>
        <boxGeometry args={[0.045, 0.01, 0.01]} />
      </mesh>
    </group>
    <mesh position={[-0.075, 0.19, 0.03]} rotation={[Math.PI / 2, 0, -0.5]} material={kit.rust}>
      <cylinderGeometry args={[0.055, 0.055, 0.01, 7]} />
    </mesh>
  </>
);

const Cultist = ({ kit }: { kit: EnemyKit }) => (
  <>
    <mesh position={[0, 0.17, 0]} material={kit.robe}>
      <coneGeometry args={[0.11, 0.3, 14]} />
    </mesh>
    <mesh position={[0, 0.265, 0]} material={kit.robe}>
      <cylinderGeometry args={[0.045, 0.06, 0.08, 10]} />
    </mesh>
    {/* A deep hood: dark inside, two eyes in it */}
    <mesh position={[0, 0.32, -0.006]} rotation={[-0.3, 0, 0]} material={kit.robe}>
      <sphereGeometry args={[0.056, 14, 10, 0, Math.PI * 2, 0, Math.PI * 0.62]} />
    </mesh>
    <mesh position={[0, 0.31, 0.004]} material={kit.stone}>
      <sphereGeometry args={[0.04, 10, 8]} />
    </mesh>
    <mesh position={[0, 0.375, -0.04]} rotation={[-0.8, 0, 0]} material={kit.robe}>
      <coneGeometry args={[0.03, 0.07, 10]} />
    </mesh>
    <Eyes kit={kit} y={0.31} z={0.04} gap={0.015} />
    {/* A staff burning at the top */}
    <group position={[-0.09, 0, 0.03]}>
      <mesh position={[0, 0.23, 0]} material={kit.wood}>
        <cylinderGeometry args={[0.008, 0.01, 0.44, 6]} />
      </mesh>
      <mesh position={[0, 0.46, 0]} material={kit.flame}>
        <coneGeometry args={[0.02, 0.05, 8]} />
      </mesh>
    </group>
    <mesh position={[0.07, 0.2, 0.05]} rotation={[0.9, 0, 0.3]} material={kit.iron}>
      <coneGeometry args={[0.01, 0.07, 4]} />
    </mesh>
  </>
);

const Imp = ({ kit }: { kit: EnemyKit }) => (
  <>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.03, 0.06, 0]} rotation={[0, 0, s * 0.2]} material={kit.skin}>
        <cylinderGeometry args={[0.015, 0.02, 0.09, 6]} />
      </mesh>
    ))}
    {/* Hunched body leaning forward */}
    <mesh position={[0, 0.16, 0.01]} rotation={[0.35, 0, 0]} scale={[0.075, 0.09, 0.065]} material={kit.skin}>
      <sphereGeometry args={[1, 12, 10]} />
    </mesh>
    <mesh position={[0, 0.25, 0.045]} material={kit.skin}>
      <sphereGeometry args={[0.048, 12, 10]} />
    </mesh>
    {/* Long pointed ears */}
    {[-1, 1].map((s) => (
      <mesh key={`ear${s}`} position={[s * 0.06, 0.27, 0.04]} rotation={[0, 0, -s * 1.25]} material={kit.skin}>
        <coneGeometry args={[0.016, 0.08, 6]} />
      </mesh>
    ))}
    <Eyes kit={kit} y={0.258} z={0.088} gap={0.018} />
    {/* A spear held upright */}
    <group position={[0.085, 0, 0.04]} rotation={[0.1, 0, -0.08]}>
      <mesh position={[0, 0.2, 0]} material={kit.wood}>
        <cylinderGeometry args={[0.007, 0.007, 0.4, 6]} />
      </mesh>
      <mesh position={[0, 0.42, 0]} material={kit.iron}>
        <coneGeometry args={[0.016, 0.06, 4]} />
      </mesh>
    </group>
  </>
);

/** Two horns curving up and out, each in two segments. */
const Horns = ({ kit, y, size = 1 }: { kit: EnemyKit; y: number; size?: number }) => (
  <>
    {[-1, 1].map((s) => (
      <group key={s} position={[s * 0.04 * size, y, 0]} rotation={[0, 0, -s * 0.9]}>
        <mesh position={[0, 0.03 * size, 0]} material={kit.bone}>
          <coneGeometry args={[0.018 * size, 0.06 * size, 8]} />
        </mesh>
        <mesh position={[s * 0.02 * size, 0.07 * size, 0]} rotation={[0, 0, s * 1.0]} material={kit.bone}>
          <coneGeometry args={[0.012 * size, 0.05 * size, 8]} />
        </mesh>
      </group>
    ))}
  </>
);

const Brute = ({ kit }: { kit: EnemyKit }) => (
  <>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.04, 0.07, 0]} material={kit.stone}>
        <cylinderGeometry args={[0.025, 0.03, 0.11, 8]} />
      </mesh>
    ))}
    <mesh position={[0, 0.2, 0]} material={kit.stone}>
      <cylinderGeometry args={[0.095, 0.065, 0.17, 12]} />
    </mesh>
    {[-1, 1].map((s) => (
      <group key={`arm${s}`}>
        <mesh position={[s * 0.1, 0.27, 0]} material={kit.stone}>
          <sphereGeometry args={[0.035, 10, 8]} />
        </mesh>
        <mesh position={[s * 0.11, 0.19, 0.01]} rotation={[0, 0, s * 0.15]} material={kit.stone}>
          <cylinderGeometry args={[0.022, 0.026, 0.14, 8]} />
        </mesh>
      </group>
    ))}
    <mesh position={[0, 0.31, 0.02]} material={kit.stone}>
      <sphereGeometry args={[0.048, 12, 10]} />
    </mesh>
    <Horns kit={kit} y={0.335} />
    <Eyes kit={kit} y={0.318} z={0.062} />
    {/* A heavy club in the right hand, resting on the ground */}
    <mesh position={[0.12, 0.08, 0.05]} rotation={[0.25, 0, -0.1]} material={kit.wood}>
      <cylinderGeometry args={[0.03, 0.012, 0.16, 8]} />
    </mesh>
  </>
);

/** The lair's master: a winged, horned lord with a spiked crown and a greataxe. */
const DemonLord = ({ kit }: { kit: EnemyKit }) => (
  <>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.035, 0.07, 0]} material={kit.stone}>
        <cylinderGeometry args={[0.022, 0.03, 0.11, 8]} />
      </mesh>
    ))}
    <mesh position={[0, 0.2, 0]} material={kit.stone}>
      <cylinderGeometry args={[0.085, 0.06, 0.17, 12]} />
    </mesh>
    {[-1, 1].map((s) => (
      <mesh key={`sh${s}`} position={[s * 0.085, 0.27, 0]} material={kit.iron}>
        <sphereGeometry args={[0.032, 10, 8]} />
      </mesh>
    ))}
    {/* Bat wings spread behind */}
    {[-1, 1].map((s) => (
      <mesh
        key={`w${s}`}
        position={[s * 0.15, 0.3, -0.05]}
        rotation={[0.2, s * 0.5, -s * 1.1]}
        scale={[1, 1, 0.08]}
        material={kit.wing}
      >
        <coneGeometry args={[0.11, 0.3, 3]} />
      </mesh>
    ))}
    <mesh position={[0, 0.315, 0.01]} material={kit.stone}>
      <sphereGeometry args={[0.046, 12, 10]} />
    </mesh>
    <Horns kit={kit} y={0.34} size={1.3} />
    {Array.from({ length: 7 }, (_, i) => {
      const a = (i / 7) * Math.PI * 2;
      return (
        <mesh
          key={`c${i}`}
          position={[Math.cos(a) * 0.04, 0.36, Math.sin(a) * 0.04]}
          rotation={[Math.sin(a) * 0.3, 0, -Math.cos(a) * 0.3]}
          material={kit.bone}
        >
          <coneGeometry args={[0.009, 0.04, 5]} />
        </mesh>
      );
    })}
    <Eyes kit={kit} y={0.32} z={0.05} gap={0.018} />
    {/* Greataxe, two crescent blades */}
    <group position={[0.11, 0.05, 0.04]} rotation={[0.1, 0, -0.12]}>
      <mesh position={[0, 0.2, 0]} material={kit.wood}>
        <cylinderGeometry args={[0.008, 0.008, 0.42, 6]} />
      </mesh>
      {[-1, 1].map((s) => (
        <mesh
          key={`b${s}`}
          position={[s * 0.004, 0.37, 0]}
          rotation={[0, s > 0 ? 0 : Math.PI, Math.PI / 2]}
          material={kit.iron}
        >
          <cylinderGeometry args={[0.05, 0.05, 0.006, 16, 1, false, 0, Math.PI]} />
        </mesh>
      ))}
    </group>
  </>
);

const BODIES: Record<EnemyKind, (props: { kit: EnemyKit }) => JSX.Element> = {
  skeleton: Skeleton,
  cultist: Cultist,
  imp: Imp,
  brute: Brute,
};

interface FigureProps {
  kit: EnemyKit;
  position: [number, number, number];
  boss?: boolean;
  /** performance.now() of the victory; Infinity while the enemy stands. */
  defeatedAt: number;
  seed: number;
}

export const EnemyFigure = ({ kit, position, boss = false, defeatedAt, seed }: FigureProps) => {
  const group = useRef<THREE.Group>(null);
  const light = useRef<THREE.PointLight>(null);
  useFrame(({ clock }) => {
    const g = group.current;
    if (!g) return;
    const since = (performance.now() - defeatedAt) / 1000;
    if (since < 0) {
      // Standing: a slow menacing sway.
      g.rotation.set(0, Math.sin(clock.elapsedTime * 0.8 + seed) * 0.15, 0);
      g.position.set(position[0], position[1], position[2]);
      g.visible = true;
      if (light.current) light.current.intensity = 2.2 + Math.sin(clock.elapsedTime * 2.2) * 0.6;
      return;
    }
    const topple = Math.min(1, since / TOPPLE_SECONDS);
    const sink = THREE.MathUtils.clamp((since - TOPPLE_SECONDS) / SINK_SECONDS, 0, 1);
    g.rotation.set(-topple * (Math.PI / 2) * 0.95, 0, 0);
    g.position.set(position[0], position[1] - sink * 0.25, position[2]);
    g.visible = sink < 1;
    if (light.current) light.current.intensity = 2.2 * (1 - topple);
  });

  const scale = FIGURE_SCALE * (boss ? BOSS_SCALE : 1);
  const Body = BODIES[KINDS[seed % KINDS.length]];
  return (
    <group ref={group} position={position}>
      <group scale={[scale, scale * 1.08, scale]}>
        <mesh position={[0, 0.025, 0]} material={kit.base}>
          <cylinderGeometry args={[0.17, 0.19, 0.05, 24]} />
        </mesh>
        {/* A red ring at the foot, as the party's figurines wear their colours */}
        <mesh position={[0, 0.02, 0]} rotation={[Math.PI / 2, 0, 0]} material={kit.ring}>
          <torusGeometry args={[0.19, 0.025, 8, 24]} />
        </mesh>
        <group position={[0, 0.03, 0]} scale={BODY_SCALE}>
          {boss ? <DemonLord kit={kit} /> : <Body kit={kit} />}
        </group>
      </group>
      {boss && <pointLight ref={light} position={[0, 0.6, 0.2]} color="#ff3a1a" intensity={2.2} distance={2.2} decay={1.6} />}
    </group>
  );
};

/** Where the enemies of a room stand: a row at the back, facing the door; the boss on its dais. */
export const enemySpots = (room: RoomInfo, count: number, boss: boolean): [number, number, number][] => {
  const y = FLOOR_THICKNESS;
  if (boss) return [[room.center[0], y + 0.06, room.center[1] + 0.1]];
  const n = Math.min(MAX_FIGURES, Math.max(1, count));
  const cz = room.center[1] - room.size[1] * 0.18;
  const spread = Math.min(room.size[0] - SQUARE * 1.2, 0.26 * (n - 1));
  return Array.from({ length: n }, (_, i) => [
    room.center[0] + (n === 1 ? 0 : -spread / 2 + (spread * i) / (n - 1)),
    y,
    cz - (i % 2) * 0.1,
  ]);
};

interface RoomEnemiesProps {
  kit: EnemyKit;
  room: RoomInfo;
  count: number;
  defeatedAt: number;
}

export const RoomEnemies = ({ kit, room, count, defeatedAt }: RoomEnemiesProps) => {
  const boss = room.type === 'boss';
  const spots = enemySpots(room, count, boss);
  return (
    <>
      {spots.map((p, i) => (
        <EnemyFigure key={i} kit={kit} position={p} boss={boss} defeatedAt={defeatedAt + i * 120} seed={room.id * 7 + i} />
      ))}
    </>
  );
};
