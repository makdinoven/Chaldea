import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import type { BoardMember, MemberBusy } from './boardTypes';

/*
  The party's miniatures: carved ivory figures on a coloured ring, one shape per
  class — a warrior with sword and shield, a rogue in a hooded cloak with two
  daggers, a mage in a pointed hat with a staff whose stone glows in the
  member's colour. The leader wears a gilt crown. Hovering a figure shows the
  character's portrait above it. Built facing +z (towards the players' edge).
*/

const CLASS_NAMES: Record<number, string> = { 1: 'Воин', 2: 'Плут', 3: 'Маг' };

const IVORY = '#b3a383';
const IVORY_DARK = '#8e7f62';
const IRON = '#8a8a92';
const WOOD = '#5a3a1e';
const GOLD = '#d4a83a';
const CLOAK = '#3e352e';
const HAT = '#3a3550';
/** The carved figure stands this much larger than the old pawn's proportions on its base. */
const BODY_SCALE = 1.2;
const DEAD = '#5e5850';

/** A tapped figure's portrait stays this long, ms, unless the next touch lands elsewhere. */
const TAP_PORTRAIT_MS = 4000;
/** A press that travelled further than this, px, was a drag of the board, not a tap. */
const TAP_SLOP = 8;

/** How often a hovered figure checks it is still under the pointer, seconds. */
const HOVER_RECHECK = 0.2;

/** Where the portrait hangs, above the tallest hat. */
const PORTRAIT_Y = 0.78;

const PAWN_PROFILE = [
  [0, 0],
  [0.2, 0],
  [0.21, 0.04],
  [0.16, 0.08],
  [0.1, 0.12],
  [0.07, 0.28],
  [0.11, 0.32],
  [0.06, 0.35],
  [0.0, 0.36],
].map(([x, y]) => new THREE.Vector2(x, y));

interface Paint {
  ivory: string;
  dark: string;
  iron: string;
  wood: string;
  cloak: string;
  hat: string;
  /** The member's colour: the ring and the mage's stone. */
  color: string;
  glow: number;
}

const Mat = ({ color, metal = false, glow = 0 }: { color: string; metal?: boolean; glow?: number }) => (
  <meshStandardMaterial
    color={color}
    roughness={metal ? 0.35 : 0.6}
    metalness={metal ? 0.7 : 0}
    emissive={glow > 0 ? color : '#000000'}
    emissiveIntensity={glow}
  />
);

const Head = ({ p, y }: { p: Paint; y: number }) => (
  <mesh position={[0, y, 0]}>
    <sphereGeometry args={[0.052, 14, 12]} />
    <Mat color={p.ivory} />
  </mesh>
);

const Warrior = ({ p }: { p: Paint }) => (
  <>
    {[-1, 1].map((s) => (
      <mesh key={s} position={[s * 0.035, 0.1, 0]}>
        <cylinderGeometry args={[0.024, 0.028, 0.1, 8]} />
        <Mat color={p.dark} />
      </mesh>
    ))}
    {/* Breastplate and shoulders */}
    <mesh position={[0, 0.215, 0]}>
      <cylinderGeometry args={[0.078, 0.06, 0.15, 12]} />
      <Mat color={p.ivory} />
    </mesh>
    {[-1, 1].map((s) => (
      <mesh key={`p${s}`} position={[s * 0.075, 0.28, 0]}>
        <sphereGeometry args={[0.03, 10, 8]} />
        <Mat color={p.iron} metal />
      </mesh>
    ))}
    <Head p={p} y={0.335} />
    {/* Helm with a crest */}
    <mesh position={[0, 0.345, 0]}>
      <sphereGeometry args={[0.058, 14, 10, 0, Math.PI * 2, 0, Math.PI / 2]} />
      <Mat color={p.iron} metal />
    </mesh>
    <mesh position={[0, 0.405, -0.005]}>
      <boxGeometry args={[0.012, 0.035, 0.08]} />
      <Mat color={p.color} glow={p.glow * 0.4} />
    </mesh>
    {/* Round shield on the left arm */}
    <group position={[-0.1, 0.2, 0.025]} rotation={[0, -0.5, 0]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.07, 0.07, 0.014, 18]} />
        <Mat color={p.wood} />
      </mesh>
      <mesh position={[0, 0, 0.009]}>
        <sphereGeometry args={[0.02, 10, 8]} />
        <Mat color={p.iron} metal />
      </mesh>
    </group>
    {/* Sword raised in the right hand */}
    <group position={[0.1, 0.2, 0.03]} rotation={[0.25, 0, -0.15]}>
      <mesh position={[0, 0.1, 0]}>
        <boxGeometry args={[0.016, 0.19, 0.005]} />
        <Mat color={p.iron} metal />
      </mesh>
      <mesh>
        <boxGeometry args={[0.06, 0.012, 0.012]} />
        <Mat color={p.dark} />
      </mesh>
      <mesh position={[0, -0.03, 0]}>
        <cylinderGeometry args={[0.008, 0.008, 0.045, 6]} />
        <Mat color={p.wood} />
      </mesh>
    </group>
  </>
);

const Rogue = ({ p }: { p: Paint }) => (
  <>
    {/* A dark cloak open at the front over the body, a pointed hood pulled low */}
    <mesh position={[0, 0.17, 0]}>
      <cylinderGeometry args={[0.045, 0.06, 0.24, 10]} />
      <Mat color={p.ivory} />
    </mesh>
    <mesh position={[0, 0.18, -0.012]} rotation={[0, Math.PI, 0]}>
      <coneGeometry args={[0.11, 0.3, 16, 1, true, -Math.PI * 0.8, Math.PI * 1.6]} />
      <meshStandardMaterial color={p.cloak} roughness={0.8} side={THREE.DoubleSide} />
    </mesh>
    <Head p={p} y={0.315} />
    <mesh position={[0, 0.33, -0.012]} rotation={[-0.35, 0, 0]}>
      <sphereGeometry args={[0.062, 14, 10, 0, Math.PI * 2, 0, Math.PI * 0.62]} />
      <meshStandardMaterial color={p.cloak} roughness={0.8} side={THREE.DoubleSide} />
    </mesh>
    <mesh position={[0, 0.39, -0.045]} rotation={[-0.7, 0, 0]}>
      <coneGeometry args={[0.035, 0.08, 10]} />
      <meshStandardMaterial color={p.cloak} roughness={0.8} />
    </mesh>
    {/* A dagger in each hand, blades out to the sides */}
    {[-1, 1].map((s) => (
      <group key={s} position={[s * 0.075, 0.2, 0.05]} rotation={[0.3, 0, -s * 1.0]}>
        <mesh position={[0, 0.06, 0]}>
          <boxGeometry args={[0.016, 0.11, 0.005]} />
          <Mat color={p.iron} metal />
        </mesh>
        <mesh>
          <boxGeometry args={[0.04, 0.01, 0.01]} />
          <Mat color={p.wood} />
        </mesh>
      </group>
    ))}
    {/* A coloured sash */}
    <mesh position={[0, 0.2, 0]} rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[0.056, 0.008, 6, 18]} />
      <Mat color={p.color} glow={p.glow * 0.4} />
    </mesh>
  </>
);

const Mage = ({ p }: { p: Paint }) => (
  <>
    {/* Long robe */}
    <mesh position={[0, 0.17, 0]}>
      <coneGeometry args={[0.115, 0.3, 16]} />
      <Mat color={p.ivory} />
    </mesh>
    <mesh position={[0, 0.27, 0]}>
      <cylinderGeometry args={[0.05, 0.06, 0.1, 12]} />
      <Mat color={p.ivory} />
    </mesh>
    <Head p={p} y={0.345} />
    {/* Pointed hat with a wide brim */}
    <mesh position={[0, 0.375, 0]}>
      <cylinderGeometry args={[0.095, 0.095, 0.008, 18]} />
      <Mat color={p.hat} />
    </mesh>
    <mesh position={[0, 0.455, -0.008]} rotation={[-0.15, 0, 0.12]}>
      <coneGeometry args={[0.058, 0.16, 14]} />
      <Mat color={p.hat} />
    </mesh>
    {/* Staff with a glowing stone */}
    <group position={[0.1, 0, 0.03]}>
      <mesh position={[0, 0.24, 0]}>
        <cylinderGeometry args={[0.008, 0.01, 0.46, 6]} />
        <Mat color={p.wood} />
      </mesh>
      <mesh position={[0, 0.49, 0]}>
        <octahedronGeometry args={[0.028]} />
        <meshStandardMaterial
          color={p.color}
          emissive={p.color}
          emissiveIntensity={p.glow * 1.6}
          toneMapped={false}
        />
      </mesh>
    </group>
  </>
);

const Pawn = ({ p }: { p: Paint }) => {
  const geometry = useMemo(() => new THREE.LatheGeometry(PAWN_PROFILE, 24), []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry}>
      <Mat color={p.ivory} />
    </mesh>
  );
};

/** The leader's crown: a gilt band with five points. */
const Crown = ({ y, r }: { y: number; r: number }) => (
  <group position={[0, y, 0]}>
    <mesh rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[r, 0.009, 6, 18]} />
      <Mat color={GOLD} metal />
    </mesh>
    {Array.from({ length: 5 }, (_, i) => {
      const a = (i / 5) * Math.PI * 2;
      return (
        <mesh key={i} position={[Math.cos(a) * r, 0.02, Math.sin(a) * r]}>
          <coneGeometry args={[0.01, 0.03, 5]} />
          <Mat color={GOLD} metal />
        </mesh>
      );
    })}
  </group>
);

/** Where the crown sits on each figure's head (height, radius): round the helm, the hood, the hat. */
const CROWN_AT: Record<number, [number, number]> = { 1: [0.375, 0.062], 2: [0.37, 0.06], 3: [0.405, 0.056] };

const AEGIS = '#76a6bd';

/** The party shield held up: a pale ward ring circling the figure, breathing slowly. */
const ShieldAura = () => {
  const ring = useRef<THREE.Group>(null);
  const glow = useRef<THREE.MeshStandardMaterial>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (ring.current) ring.current.rotation.y = t * 0.8;
    if (glow.current) glow.current.emissiveIntensity = 0.9 + Math.sin(t * 2.4) * 0.35;
  });
  return (
    <group ref={ring} position={[0, 0.22, 0]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.25, 0.012, 8, 40]} />
        <meshStandardMaterial ref={glow} color={AEGIS} emissive={AEGIS} transparent opacity={0.85} />
      </mesh>
      {/* A small kite shield riding the ring. */}
      <mesh position={[0.25, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <cylinderGeometry args={[0.05, 0.05, 0.012, 3]} />
        <meshStandardMaterial color={AEGIS} emissive={AEGIS} emissiveIntensity={0.8} />
      </mesh>
    </group>
  );
};

/** How long a line stays over the figurine (ms). */
const SPEECH_MS = 5000;
const SPEECH_Y = 1.05;
/** A line said while busy with a game goes up above the badge. */
const SPEECH_LIFT = 0.32;

/** A line said by the member: a bubble over the figurine for a few seconds. */
const SpeechBubble = ({ speech, color, lifted }: { speech: { text: string; at: number }; color: string; lifted?: boolean }) => {
  const [shown, setShown] = useState(() => performance.now() - speech.at < SPEECH_MS);
  useEffect(() => {
    const left = SPEECH_MS - (performance.now() - speech.at);
    setShown(left > 0);
    if (left <= 0) return;
    const timer = setTimeout(() => setShown(false), left);
    return () => clearTimeout(timer);
  }, [speech]);
  if (!shown) return null;
  return (
    <Html center position={[0, SPEECH_Y + (lifted ? SPEECH_LIFT : 0), 0]} zIndexRange={[0, 0]} style={{ pointerEvents: 'none' }}>
      <div className="relative -translate-y-1/2 max-w-[200px] w-max bg-black/85 backdrop-blur-sm rounded-card border px-2.5 py-1.5 shadow-card text-white text-xs leading-snug break-words"
        style={{ borderColor: color }}
      >
        {speech.text}
        <span
          className="absolute left-1/2 -bottom-[5px] -translate-x-1/2 w-2 h-2 rotate-45 bg-black/85 border-r border-b"
          style={{ borderColor: color }}
        />
      </div>
    </Html>
  );
};

/** Busy with a minigame: a badge over the figurine for as long as the game lasts, so the others see it. */
const BusyBadge = ({ busy, color }: { busy: MemberBusy; color: string }) => (
  <Html center position={[0, SPEECH_Y, 0]} zIndexRange={[0, 0]} style={{ pointerEvents: 'none' }}>
    <div
      className="-translate-y-1/2 flex items-center gap-1.5 w-max max-w-[220px] bg-black/85 backdrop-blur-sm rounded-full border px-2.5 py-1 shadow-card text-[11px] leading-none text-gold"
      style={{ borderColor: color }}
    >
      <span className="animate-pulse">{busy.icon}</span>
      <span className="truncate">{busy.text}</span>
      <span className="flex gap-0.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className="w-1 h-1 rounded-full bg-gold animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
        ))}
      </span>
    </div>
  </Html>
);

/** The character's portrait over the hovered figure. */
const Portrait = ({ member }: { member: BoardMember }) => {
  const className = member.classId ? CLASS_NAMES[member.classId] : undefined;
  return (
    <Html center position={[0, PORTRAIT_Y, 0]} zIndexRange={[0, 0]} style={{ pointerEvents: 'none' }}>
      <div className="flex items-center gap-2 whitespace-nowrap bg-black/85 backdrop-blur-sm rounded-card border border-white/10 pl-1.5 pr-3 py-1.5 shadow-card -translate-y-1/2">
        <div className="shrink-0 w-10 h-10 rounded-full p-[2px]" style={{ background: member.color }}>
          {member.avatar ? (
            <img
              src={member.avatar}
              alt=""
              className={`w-full h-full rounded-full object-cover ${member.dead ? 'grayscale opacity-60' : ''}`}
            />
          ) : (
            <div className="w-full h-full rounded-full bg-black/80 flex items-center justify-center text-white/70 text-sm">
              {member.name.slice(0, 1)}
            </div>
          )}
        </div>
        <div className="leading-tight">
          <p className="gold-text text-sm font-medium">
            {member.name}
            {member.leader && <span className="ml-1 text-[11px]" aria-label="Лидер">👑</span>}
          </p>
          <p className="text-white/60 text-[11px]">
            {[
              className,
              member.level != null ? `${member.level} ур.` : null,
              member.dead ? 'пал' : null,
              member.shielded ? 'держит щит' : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
      </div>
    </Html>
  );
};

/** One member's figure, standing on its ring; a fallen one lies on its side, greyed. */
export const PartyMiniature = ({ member }: { member: BoardMember }) => {
  const [hovered, setHovered] = useState(false);
  // A touch screen has no hover: a tap shows the portrait for a while instead.
  const [tapped, setTapped] = useState(false);
  useEffect(() => {
    if (!tapped) return;
    const timer = setTimeout(() => setTapped(false), TAP_PORTRAIT_MS);
    const close = () => setTapped(false);
    window.addEventListener('pointerdown', close);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('pointerdown', close);
    };
  }, [tapped]);
  // Pointer events only re-check what is under a moving pointer: a figure walking
  // away from a still one would keep its portrait. Re-check while hovered.
  const lastCheck = useRef(0);
  useFrame(({ clock, events }) => {
    if (!hovered || clock.elapsedTime - lastCheck.current < HOVER_RECHECK) return;
    lastCheck.current = clock.elapsedTime;
    events.update?.();
  });
  const dead = !!member.dead;
  const p: Paint = {
    ivory: dead ? DEAD : IVORY,
    dark: dead ? '#4a4540' : IVORY_DARK,
    iron: dead ? '#55524e' : IRON,
    wood: dead ? '#3e3832' : WOOD,
    cloak: dead ? '#3a3632' : CLOAK,
    hat: dead ? '#3a3632' : HAT,
    color: dead ? '#4a4a4a' : member.color,
    glow: dead ? 0 : 1,
  };
  const body =
    member.classId === 1 ? <Warrior p={p} /> : member.classId === 2 ? <Rogue p={p} /> : member.classId === 3 ? <Mage p={p} /> : <Pawn p={p} />;
  const over = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    // A finger "hovers" on touching and never leaves: taps are handled on click.
    if (e.pointerType === 'mouse') setHovered(true);
  };
  const tap = (e: ThreeEvent<MouseEvent>) => {
    if ((e.nativeEvent as PointerEvent).pointerType === 'mouse' || e.delta > TAP_SLOP) return;
    e.stopPropagation();
    setTapped(true);
  };
  return (
    <>
      <group
        rotation={dead ? [0, 0, Math.PI / 2] : [0, 0, 0]}
        position={dead ? [0.18, 0.2, 0] : [0, 0, 0]}
        onPointerOver={over}
        onPointerOut={() => setHovered(false)}
        onClick={tap}
      >
        <mesh position={[0, 0.025, 0]}>
          <cylinderGeometry args={[0.17, 0.19, 0.05, 24]} />
          <Mat color={p.dark} />
        </mesh>
        <mesh position={[0, 0.02, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.19, 0.025, 8, 24]} />
          <meshStandardMaterial color={p.color} emissive={p.color} emissiveIntensity={dead ? 0 : 0.45} />
        </mesh>
        <group position={[0, 0.03, 0]} scale={BODY_SCALE}>
          {body}
          {member.leader &&
            (CROWN_AT[member.classId ?? 0] ? (
              <Crown y={CROWN_AT[member.classId!][0]} r={CROWN_AT[member.classId!][1]} />
            ) : (
              <mesh position={[0, 0.34, 0]}>
                <sphereGeometry args={[0.05, 12, 10]} />
                <Mat color={GOLD} metal />
              </mesh>
            ))}
        </group>
      </group>
      {member.shielded && !dead && <ShieldAura />}
      {member.busy && !dead && !(hovered || tapped) && <BusyBadge busy={member.busy} color={member.color} />}
      {member.speech && !(hovered || tapped) && (
        <SpeechBubble speech={member.speech} color={member.color} lifted={!!member.busy && !dead} />
      )}
      {(hovered || tapped) && <Portrait member={member} />}
    </>
  );
};
