import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import * as THREE from "three";
import ArenaEnvironment, { BOARD_TOP } from "./ArenaEnvironment";
import Fighter3D from "./Fighter3D";
import {
  AimArc,
  FLIGHT_MS,
  ImpactBurst,
  Projectile,
  type Impact,
  type Strike,
  type Vec3,
} from "./BattleEffects";
import type { ArenaFighter, ArenaSceneProps } from "./arenaTypes";

// Seen from above like a card-game board: the viewer's team on the near row
// (bottom of the screen), the opponents on the far row (top).
const MAX_ROW_SPACING = 2.7;
// Phones get a portrait board (see boardSize): rows sit further apart, less room across.
const LAYOUT = {
  landscape: { rowZ: 2.4, rowSpan: 9, viewWidth: 14, viewDepth: 11.2 },
  portrait: { rowZ: 3.4, rowSpan: 6.4, viewWidth: 10.5, viewDepth: 15.5 },
} as const;
const PORTRAIT_QUERY = "(max-width: 767px)";
// Aimed a little below the board's centre so there's table under its near edge for
// the bottom shadow to fall on without darkening the board.
const CAMERA_TARGET = new THREE.Vector3(0, 0, 0.75);
// On phones the turn banner sits over the top of the arena; aim a little further
// up the board so the far row clears it.
const PORTRAIT_TARGET_Z = -1.1;
const CAMERA_PITCH = THREE.MathUtils.degToRad(72);
const CAMERA_FOV = 42;
// drei <Html> sizes by camera distance but not by canvas height, so the factor is
// tied to the canvas height: cards then keep their size relative to the board.
const CARD_SCALE_PER_PX = 0.0155;
const SIDE_COLORS = { ally: "#7fb8e6", enemy: "#ff7a4d" } as const;

/** Places one team in a row across the board, centred on x. */
const layoutTeam = (team: ArenaFighter[], z: number, rowSpan: number): [number, Vec3][] => {
  const n = team.length;
  const spacing = n > 1 ? Math.min(MAX_ROW_SPACING, rowSpan / (n - 1)) : 0;
  return team.map((f, i) => [f.participantId, [(i - (n - 1) / 2) * spacing, BOARD_TOP, z]]);
};

/** Camera distance that fits the whole board (plus candles and some air) on screen. */
const fitDistance = (aspect: number, portrait: boolean) => {
  const { viewWidth, viewDepth } = LAYOUT[portrait ? "portrait" : "landscape"];
  const span = 2 * Math.tan(THREE.MathUtils.degToRad(CAMERA_FOV / 2));
  return Math.max(viewDepth / span, viewWidth / (span * aspect));
};

const usePortraitBoard = () => {
  const [portrait, setPortrait] = useState(() => window.matchMedia(PORTRAIT_QUERY).matches);
  useEffect(() => {
    const query = window.matchMedia(PORTRAIT_QUERY);
    const update = () => setPortrait(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return portrait;
};

/** A fixed camera looking down at the board; it only re-frames when the canvas resizes. */
const CameraRig = ({ portrait }: { portrait: boolean }) => {
  const { camera, size } = useThree();

  useEffect(() => {
    const distance = fitDistance(size.width / Math.max(1, size.height), portrait);
    const target = new THREE.Vector3(0, 0, portrait ? PORTRAIT_TARGET_Z : CAMERA_TARGET.z);
    camera.position.set(
      0,
      target.y + Math.sin(CAMERA_PITCH) * distance,
      target.z + Math.cos(CAMERA_PITCH) * distance,
    );
    camera.lookAt(target);
  }, [camera, size.width, size.height, portrait]);

  return null;
};

interface FightersProps {
  portrait: boolean;
  fighters: ArenaFighter[];
  positions: Map<number, Vec3>;
  lunges: Map<number, { toward: Vec3; at: number }>;
  onSelect: ArenaSceneProps["onSelect"];
}

const Fighters = ({ portrait, fighters, positions, lunges, onSelect }: FightersProps) => {
  const canvasHeight = useThree((s) => s.size.height);
  const cardScale = canvasHeight * CARD_SCALE_PER_PX * (portrait ? 1.8 : 1);
  return (
    <>
      {fighters.map((fighter) => {
        const position = positions.get(fighter.participantId);
        if (!position) return null;
        return (
          <Fighter3D
            key={fighter.participantId}
            fighter={fighter}
            position={position}
            lunge={lunges.get(fighter.participantId) ?? null}
            cardDistanceFactor={cardScale}
            onSelect={onSelect}
          />
        );
      })}
    </>
  );
};

type HeldStats = Pick<ArenaFighter, "hp" | "isDead">;

interface Exchange {
  attacker: ArenaFighter;
  from: Vec3;
  hits: { victim: number; was: HeldStats; to: Vec3 }[];
}

/** Whoever was acting before this update dealt every HP drop on other fighters. */
const detectExchange = (
  before: ArenaFighter[] | null,
  after: ArenaFighter[],
  positions: Map<number, Vec3>,
): Exchange | null => {
  if (!before) return null;
  const attacker = before.find((f) => f.isActing && !f.isDead);
  const from = attacker ? positions.get(attacker.participantId) : undefined;
  if (!attacker || !from) return null;
  const hits = after.flatMap((f) => {
    const was = before.find((b) => b.participantId === f.participantId);
    const to = positions.get(f.participantId);
    if (!was || !to || f.hp >= was.hp || f.participantId === attacker.participantId) return [];
    return [{ victim: f.participantId, was: { hp: was.hp, isDead: was.isDead }, to }];
  });
  return hits.length ? { attacker, from, hits } : null;
};

/**
 * Turns HP drops into a visible exchange: the fighter who was acting lunges, a bolt
 * flies to each damaged target, and the target's card only shows the new HP when the
 * bolt lands. The exchange is derived during render (not in an effect) so a target
 * card never sees the new HP for even one frame before the hold kicks in.
 */
const useStrikes = (fighters: ArenaFighter[], positions: Map<number, Vec3>) => {
  const previous = useRef<ArenaFighter[] | null>(null);
  const nextId = useRef(0);
  const timers = useRef(new Set<number>());
  const [strikes, setStrikes] = useState<Strike[]>([]);
  const [impacts, setImpacts] = useState<Impact[]>([]);
  const [released, setReleased] = useState<Exchange | null>(null);
  const [lunges, setLunges] = useState<Map<number, { toward: Vec3; at: number }>>(new Map());

  const exchange = useMemo(
    () => detectExchange(previous.current, fighters, positions),
    [fighters, positions],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => window.clearTimeout(t));
  }, []);

  useEffect(() => {
    previous.current = fighters;
    if (!exchange) return;
    const now = performance.now();
    const color = SIDE_COLORS[exchange.attacker.side];
    setStrikes((list) => [
      ...list,
      ...exchange.hits.map((h) => ({ id: nextId.current++, from: exchange.from, to: h.to, color, startedAt: now })),
    ]);
    setLunges((m) => new Map(m).set(exchange.attacker.participantId, { toward: exchange.hits[0].to, at: now }));
    const release = window.setTimeout(() => {
      timers.current.delete(release);
      setReleased(exchange);
    }, FLIGHT_MS);
    timers.current.add(release);
  }, [exchange, fighters]);

  const land = useCallback((s: Strike) => {
    setStrikes((list) => list.filter((x) => x.id !== s.id));
    setImpacts((list) => [...list, { id: s.id, at: s.to, color: s.color, startedAt: performance.now() }]);
  }, []);

  const clearImpact = useCallback((i: Impact) => {
    setImpacts((list) => list.filter((x) => x.id !== i.id));
  }, []);

  const shown = useMemo(() => {
    if (!exchange || released === exchange) return fighters;
    const held = new Map(exchange.hits.map((h) => [h.victim, h.was]));
    return fighters.map((f) => {
      const was = held.get(f.participantId);
      return was ? { ...f, ...was } : f;
    });
  }, [fighters, exchange, released]);

  return { shown, strikes, impacts, lunges, land, clearImpact };
};

const ArenaScene = ({ fighters, onSelect, aims, turnDeadline, turnPaused, boardArtUrl, critRollAt, turnNumber }: ArenaSceneProps) => {
  const portrait = usePortraitBoard();
  const positions = useMemo(() => {
    const { rowZ, rowSpan } = LAYOUT[portrait ? "portrait" : "landscape"];
    return new Map<number, Vec3>([
      ...layoutTeam(fighters.filter((f) => f.side === "ally"), rowZ, rowSpan),
      ...layoutTeam(fighters.filter((f) => f.side === "enemy"), -rowZ, rowSpan),
    ]);
  }, [fighters, portrait]);
  const { shown, strikes, impacts, lunges, land, clearImpact } = useStrikes(fighters, positions);


  return (
    <Canvas
      dpr={[1, 1.75]}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      camera={{ fov: CAMERA_FOV, near: 0.1, far: 120, position: [0, 16, 5] }}
    >
      <CameraRig portrait={portrait} />
      <ArenaEnvironment
        turnDeadline={turnDeadline}
        turnPaused={turnPaused}
        portrait={portrait}
        boardArtUrl={boardArtUrl}
        critRollAt={critRollAt}
        turnNumber={turnNumber}
      />
      <Fighters portrait={portrait} fighters={shown} positions={positions} lunges={lunges} onSelect={onSelect} />
      {aims.map((aim) => {
        const from = positions.get(aim.from);
        const to = positions.get(aim.to);
        return from && to ? <AimArc key={`${aim.kind}-${aim.to}`} from={from} to={to} kind={aim.kind} /> : null;
      })}
      {strikes.map((s) => (
        <Projectile key={s.id} strike={s} onLand={land} />
      ))}
      {impacts.map((i) => (
        <ImpactBurst key={i.id} impact={i} onDone={clearImpact} />
      ))}
    </Canvas>
  );
};

export default ArenaScene;
