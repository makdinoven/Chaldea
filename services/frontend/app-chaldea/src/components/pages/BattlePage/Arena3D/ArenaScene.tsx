import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import * as THREE from "three";
import ArenaEnvironment, { BOARD_TOP } from "./ArenaEnvironment";
import Fighter3D, { type ControlHit } from "./Fighter3D";
import { BLOCKED_LABELS, SKIP_LABELS } from "./ControlEffects";
import { strikeStyleOf, type StrikeStyle } from "./strikeStyles";
import {
  AimArc,
  strikeMs,
  FLIGHT_MS,
  ImpactBurst,
  Projectile,
  type Impact,
  type Strike,
  type Vec3,
} from "./BattleEffects";
import type { ArenaEffect, ArenaFighter, ArenaSceneProps, DotHit, DotKind, Evade, TurnOutcome } from "./arenaTypes";
import type { CastFx } from "./CastEffects";
import { useClientPrefs } from "../../../../utils/clientPrefs";

// Seen from above like a card-game board: the viewer's team on the near row
// (bottom of the screen), the opponents on the far row (top).
// What one fighter takes up across a row, in world units: the card plus its
// resource orbs on the left and effect runes on the right. A row that can't give
// every fighter this much shrinks its cards instead of letting them overlap.
// On phones the orbs sit under the card, so a fighter is only card + runes wide —
// but phone cards are drawn relatively larger (see CARD_SCALE_PER_PX).
const FIGHTER_FOOTPRINT = { landscape: 3.3, portrait: 2.9 } as const;
// Phone cards are drawn larger than the board scale alone would give; sized so two
// rows plus their orbs fit between the turn banner and the action bar.
const PORTRAIT_CARD_BOOST = 1.5;
// Phones get a portrait board (see boardSize): rows sit further apart, less room across.
const LAYOUT = {
  landscape: { rowZ: 2.4, rowSpan: 10, viewWidth: 14, viewDepth: 11.2 },
  portrait: { rowZ: 3.0, rowSpan: 7, viewWidth: 10.5, viewDepth: 16.5 },
} as const;
const PORTRAIT_QUERY = "(max-width: 767px)";
// Aimed a little below the board's centre so there's table under its near edge for
// the bottom shadow to fall on without darkening the board.
const CAMERA_TARGET = new THREE.Vector3(0, 0, 0.75);
// On phones the turn banner sits over the top of the arena; aim a little further
// up the board so the far row clears it.
const PORTRAIT_TARGET_Z = -0.6;
const CAMERA_PITCH = THREE.MathUtils.degToRad(72);
const CAMERA_FOV = 42;
// drei <Html> sizes by camera distance but not by canvas height, so the factor is
// tied to the canvas height: cards then keep their size relative to the board.
const CARD_SCALE_PER_PX = 0.0155;
const SIDE_COLORS = { ally: "#7fb8e6", enemy: "#ff7a4d" } as const;
// A missed bolt passes this far beside the target card and dies on the board.
const MISS_OFFSET = 1.9;
// The dodger starts stepping aside this far into the bolt's flight.
const DODGE_LEAD = 0.5;
// The bolt-on-HP exchange already lunged the attacker if it did so this recently.
const RECENT_LUNGE_MS = 1500;
// How long an HP change waits for its turn's log before playing without it. Together
// with the flight and the tick delay it must stay under BattlePage's 3D turn gap (2600).
const LOG_WAIT_MS = 600;
// Damage-over-time lands this long after the blow, so the two read as separate numbers.
const DOT_AFTER_BLOW_MS = 450;
// With no blow this turn, the tick lands this long after the log arrives.
const DOT_ALONE_DELAY_MS = 150;

/** Unit vector across the bolt's path, turned toward the board's centre line. */
const sidestep = (from: Vec3, to: Vec3): [number, number] => {
  const dx = to[0] - from[0];
  const dz = to[2] - from[2];
  const len = Math.hypot(dx, dz) || 1;
  let px = -dz / len;
  let pz = dx / len;
  const towardCentre = to[0] > 0.1 ? -1 : 1;
  if (Math.sign(px || 1) !== towardCentre) {
    px = -px;
    pz = -pz;
  }
  return [px, pz];
};

/**
 * Places one team in a row across the board, centred on x. Returns each fighter's
 * spot and the card scale its row needs: 1 when the row fits at full size, less
 * when a crowded row has to shrink its cards to keep them apart.
 */
const layoutTeam = (
  team: ArenaFighter[],
  z: number,
  rowSpan: number,
  footprint: number,
): [number, Vec3, number][] => {
  const n = team.length;
  const spacing = n > 1 ? Math.min(footprint, rowSpan / (n - 1)) : 0;
  const scale = n > 1 ? Math.min(1, spacing / footprint) : 1;
  return team.map((f, i) => [f.participantId, [(i - (n - 1) / 2) * spacing, BOARD_TOP, z], scale]);
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
  /** Per-fighter card scale: below 1 in a row too crowded for full-size cards. */
  cardScales: Map<number, number>;
  lunges: Map<number, { toward: Vec3; at: number }>;
  evades: Map<number, Evade>;
  hitStyles: Map<number, StrikeStyle>;
  dots: Map<number, DotHit>;
  castFx: Map<number, CastFx>;
  outcome: TurnOutcome | null;
  onSelect: ArenaSceneProps["onSelect"];
}

/** The turn's control events, folded into one word per fighter. */
const controlHitsOf = (outcome: TurnOutcome | null) => {
  const hits = new Map<number, ControlHit>();
  if (!outcome) return hits;
  const blocked = new Map<number, string[]>();
  outcome.controls.forEach((c) => {
    if (c.kind === "skip") {
      hits.set(c.who, {
        at: outcome.at,
        word: SKIP_LABELS[c.control],
        tone: c.control === "Stun" ? "stun" : "paralysis",
      });
    } else {
      blocked.set(c.who, [...(blocked.get(c.who) ?? []), BLOCKED_LABELS[c.skill].word]);
    }
  });
  blocked.forEach((words, who) => {
    if (!hits.has(who)) hits.set(who, { at: outcome.at, word: "Заблокировано", sub: words.join(", "), tone: "block" });
  });
  return hits;
};

const Fighters = ({
  portrait,
  fighters,
  positions,
  cardScales,
  lunges,
  evades,
  hitStyles,
  dots,
  castFx,
  outcome,
  onSelect,
}: FightersProps) => {
  const canvasHeight = useThree((s) => s.size.height);
  const controlHits = useMemo(() => controlHitsOf(outcome), [outcome]);
  const cardScale = canvasHeight * CARD_SCALE_PER_PX * (portrait ? PORTRAIT_CARD_BOOST : 1);
  return (
    <>
      {fighters.map((fighter) => {
        const position = positions.get(fighter.participantId);
        if (!position) return null;
        return (
          <Fighter3D
            key={fighter.participantId}
            fighter={fighter}
            orbRow={portrait ? (fighter.side === "enemy" ? "below" : "above") : null}
            position={position}
            lunge={lunges.get(fighter.participantId) ?? null}
            evade={evades.get(fighter.participantId) ?? null}
            hitStyle={hitStyles.get(fighter.participantId) ?? null}
            dot={dots.get(fighter.participantId) ?? null}
            controlHit={controlHits.get(fighter.participantId) ?? null}
            castFx={castFx.get(fighter.participantId) ?? null}
            critAt={outcome?.crits.includes(fighter.participantId) ? outcome.at : null}
            cardDistanceFactor={cardScale * (cardScales.get(fighter.participantId) ?? 1)}
            footScale={(cardScales.get(fighter.participantId) ?? 1) * (portrait ? PORTRAIT_CARD_BOOST : 1)}
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

// Orb colours for cast effects: a buff and a debuff.
const CAST_COLORS = { buff: "#6ee89a", debuff: "#d14b8f" } as const;

interface Cast {
  from: Vec3;
  targets: { id: number; to: Vec3; positive: boolean; was: ArenaEffect[]; self: boolean }[];
}

/**
 * Whoever was acting before this update cast every effect that just appeared on a
 * card. The server's log names who RECEIVED an effect but not who cast it; the
 * turn's actor did. Read from state alone, so it needs no wait for the log.
 */
const detectCasts = (
  before: ArenaFighter[] | null,
  after: ArenaFighter[],
  positions: Map<number, Vec3>,
): Cast | null => {
  if (!before) return null;
  const caster = before.find((f) => f.isActing && !f.isDead);
  const from = caster ? positions.get(caster.participantId) : undefined;
  if (!caster || !from) return null;
  const targets = after.flatMap((f) => {
    const was = before.find((b) => b.participantId === f.participantId);
    const to = positions.get(f.participantId);
    if (!was || !to) return [];
    const fresh = f.effects.filter((e) => !was.effects.some((w) => w.key === e.key));
    if (!fresh.length) return [];
    return [{
      id: f.participantId,
      to,
      positive: fresh.every((e) => e.positive),
      was: was.effects,
      self: f.participantId === caster.participantId,
    }];
  });
  return targets.length ? { from, targets } : null;
};

/**
 * Effects cast this turn: an orb flies from the caster to each other fighter and
 * the new runes only appear when it lands (a seal closes on the card); a cast on
 * oneself raises rings of light at once. Derived during render, like strikes, so a
 * target's card never shows the new rune before the orb gets there.
 */
const useCasts = (fighters: ArenaFighter[], positions: Map<number, Vec3>) => {
  const previous = useRef<ArenaFighter[] | null>(null);
  const nextId = useRef(0);
  const timers = useRef(new Set<number>());
  const [orbs, setOrbs] = useState<Strike[]>([]);
  const [landed, setLanded] = useState<Cast | null>(null);
  const [castFx, setCastFx] = useState<Map<number, CastFx>>(new Map());

  const cast = useMemo(() => detectCasts(previous.current, fighters, positions), [fighters, positions]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => window.clearTimeout(t));
  }, []);

  useEffect(() => {
    previous.current = fighters;
    if (!cast) return;
    const now = performance.now();
    const mark = (targets: Cast["targets"]) =>
      setCastFx((m) => {
        const next = new Map(m);
        targets.forEach((t) => next.set(t.id, { id: nextId.current++, positive: t.positive, self: t.self }));
        return next;
      });
    const others = cast.targets.filter((t) => !t.self);
    const selves = cast.targets.filter((t) => t.self);
    if (selves.length) mark(selves);
    if (!others.length) {
      setLanded(cast);
      return;
    }
    setOrbs((list) => [
      ...list,
      ...others.map((t) => ({
        id: nextId.current++,
        from: cast.from,
        to: t.to,
        color: CAST_COLORS[t.positive ? "buff" : "debuff"],
        startedAt: now,
        glancing: true,
        spell: true,
      })),
    ]);
    const t = window.setTimeout(() => {
      timers.current.delete(t);
      setLanded(cast);
      mark(others);
    }, FLIGHT_MS);
    timers.current.add(t);
  }, [cast, fighters]);

  const landOrb = useCallback((s: Strike) => setOrbs((list) => list.filter((x) => x.id !== s.id)), []);

  // Runes that are still in flight: the target keeps showing its old list.
  const heldEffects = useMemo(() => {
    if (!cast || landed === cast) return null;
    return new Map(cast.targets.filter((t) => !t.self).map((t) => [t.id, t.was]));
  }, [cast, landed]);

  return { orbs, landOrb, castFx, heldEffects };
};

/** How far an exchange's HP drops have been let through to the cards. */
interface Release {
  exchange: Exchange;
  /** 1 — direct blows landed, damage-over-time still held; 2 — everything shown. */
  phase: 1 | 2;
  /** HP each victim loses to damage-over-time this turn (held back in phase 1). */
  ticks: Map<number, number>;
}

/** Sums one turn's damage-over-time ticks per victim. */
const groupTicks = (outcome: TurnOutcome | null) => {
  const byVictim = new Map<number, { kinds: DotKind[]; amount: number }>();
  outcome?.ticks.forEach(({ target, kind, amount }) => {
    const entry = byVictim.get(target) ?? { kinds: [], amount: 0 };
    if (!entry.kinds.includes(kind)) entry.kinds.push(kind);
    entry.amount += amount;
    byVictim.set(target, entry);
  });
  return byVictim;
};

/**
 * Turns HP drops into a visible exchange: the fighter who was acting lunges, a bolt
 * flies to each target of a direct blow, and the card only shows the new HP when the
 * bolt lands. Damage-over-time (which ticks on its caster's turn) is split out using
 * the turn's log: it never gets a bolt and lands a beat after the blow, as its own
 * number. The exchange is derived during render (not in an effect) so a target card
 * never sees the new HP for even one frame before the hold kicks in.
 */
const useStrikes = (
  fighters: ArenaFighter[],
  positions: Map<number, Vec3>,
  outcome: TurnOutcome | null,
  turnNumber: number,
) => {
  const previous = useRef<ArenaFighter[] | null>(null);
  const nextId = useRef(0);
  const timers = useRef(new Set<number>());
  const [strikes, setStrikes] = useState<Strike[]>([]);
  const [impacts, setImpacts] = useState<Impact[]>([]);
  const [released, setReleased] = useState<Release | null>(null);
  const [lunges, setLunges] = useState<Map<number, { toward: Vec3; at: number }>>(new Map());
  const [evades, setEvades] = useState<Map<number, Evade>>(new Map());
  // How the latest blow on each fighter looked — the card marks it to match.
  const [hitStyles, setHitStyles] = useState<Map<number, StrikeStyle>>(new Map());
  const [dots, setDots] = useState<Map<number, DotHit>>(new Map());
  const fightersRef = useRef(fighters);
  fightersRef.current = fighters;
  const positionsRef = useRef(positions);
  positionsRef.current = positions;
  const outcomeRef = useRef(outcome);
  outcomeRef.current = outcome;
  // An exchange waiting for its turn's log (or for the wait to run out).
  const awaiting = useRef<{ exchange: Exchange; turn: number; timer: number } | null>(null);

  const exchange = useMemo(
    () => detectExchange(previous.current, fighters, positions),
    [fighters, positions],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => window.clearTimeout(t));
  }, []);

  const later = useCallback((fn: () => void, ms: number) => {
    const t = window.setTimeout(() => {
      timers.current.delete(t);
      fn();
    }, ms);
    timers.current.add(t);
    return t;
  }, []);

  /** Plays an exchange; without its log every HP drop counts as a blow (the old way). */
  const play = useCallback(
    (ex: Exchange, log: TurnOutcome | null) => {
      const now = performance.now();
      const ticks = groupTicks(log);
      const blows = ex.hits.filter((h) => !log || log.hits.includes(h.victim) || !ticks.has(h.victim));
      // Without the log the type is unknown: the plain side-coloured bolt.
      const styleOf = (victim: number): StrikeStyle | undefined =>
        log ? strikeStyleOf(log.hitTypes[victim]) : undefined;
      const blowStrikes: Strike[] = blows.map((h) => ({
        id: nextId.current++,
        from: ex.from,
        to: h.to,
        color: SIDE_COLORS[ex.attacker.side],
        startedAt: now,
        style: styleOf(h.victim),
      }));
      if (blows.length) {
        setStrikes((list) => [...list, ...blowStrikes]);
        setHitStyles((m) => {
          const next = new Map(m);
          blowStrikes.forEach((s, i) => s.style && next.set(blows[i].victim, s.style));
          return next;
        });
        setLunges((m) => new Map(m).set(ex.attacker.participantId, { toward: blows[0].to, at: now }));
      }

      const tickAmounts = new Map([...ticks].map(([victim, t]) => [victim, t.amount]));
      const blowsLandAt = blowStrikes.reduce((latest, s) => Math.max(latest, strikeMs(s)), 0);
      const showAll = () => {
        setReleased({ exchange: ex, phase: 2, ticks: tickAmounts });
        if (!ticks.size) return;
        const at = performance.now();
        setDots((m) => {
          const next = new Map(m);
          ticks.forEach((t, victim) => next.set(victim, { ...t, at }));
          return next;
        });
      };
      if (!ticks.size) {
        later(showAll, blowsLandAt);
        return;
      }
      later(() => setReleased({ exchange: ex, phase: 1, ticks: tickAmounts }), blowsLandAt);
      later(showAll, blowsLandAt + (blows.length ? DOT_AFTER_BLOW_MS : DOT_ALONE_DELAY_MS));
    },
    [later],
  );

  useEffect(() => {
    previous.current = fighters;
    if (!exchange) return;
    if (outcomeRef.current?.turn === turnNumber) {
      play(exchange, outcomeRef.current);
      return;
    }
    if (awaiting.current) window.clearTimeout(awaiting.current.timer);
    const timer = later(() => {
      if (awaiting.current?.exchange !== exchange) return;
      awaiting.current = null;
      play(exchange, null);
    }, LOG_WAIT_MS);
    awaiting.current = { exchange, turn: turnNumber, timer };
  }, [exchange, fighters, turnNumber, play, later]);

  useEffect(() => {
    const waiting = awaiting.current;
    if (!outcome || !waiting || outcome.turn !== waiting.turn) return;
    window.clearTimeout(waiting.timer);
    timers.current.delete(waiting.timer);
    awaiting.current = null;
    play(waiting.exchange, outcome);
  }, [outcome, play]);

  // Blows that never landed leave HP alone, so they come from the turn's log instead:
  // the bolt still flies, but the target steps aside (dodge) or it sails past (miss).
  useEffect(() => {
    if (!outcome?.evasions.length) return;
    const now = performance.now();
    const pos = positionsRef.current;
    const newStrikes: Strike[] = [];
    const newEvades: [number, Evade][] = [];
    outcome.evasions.forEach(({ source, target, kind, damageType }) => {
      const style = strikeStyleOf(damageType);
      const from = pos.get(source);
      const to = pos.get(target);
      const attacker = fightersRef.current.find((f) => f.participantId === source);
      if (!from || !to || !attacker) return;
      const away = sidestep(from, to);
      const end: Vec3 =
        kind === "miss" ? [to[0] + away[0] * MISS_OFFSET, to[1], to[2] + away[1] * MISS_OFFSET] : to;
      newStrikes.push({
        id: nextId.current++,
        from,
        to: end,
        color: SIDE_COLORS[attacker.side],
        startedAt: now,
        // An absorbed blow still strikes home — it just does nothing.
        glancing: kind !== "absorb",
        // A blade dodged or missed swings at air: the lunge alone, no missile, no burst.
        style,
      });
      const lands = strikeMs({ style });
      newEvades.push([target, { kind, away, at: now + lands * (kind === "dodge" ? DODGE_LEAD : 1) }]);
    });
    if (!newStrikes.length) return;
    setStrikes((list) => [...list, ...newStrikes]);
    setEvades((m) => new Map([...m, ...newEvades]));
    // The attacker lunges once — unless an HP hit this same turn already sent them.
    setLunges((m) => {
      const next = new Map(m);
      outcome.evasions.forEach(({ source, target }) => {
        const last = next.get(source);
        const toward = pos.get(target);
        if (toward && !(last && now - last.at < RECENT_LUNGE_MS)) next.set(source, { toward, at: now });
      });
      return next;
    });
  }, [outcome]);

  const land = useCallback((s: Strike) => {
    setStrikes((list) => list.filter((x) => x.id !== s.id));
    if (s.glancing) return;
    setImpacts((list) => [
      ...list,
      { id: s.id, at: s.to, color: s.color, startedAt: performance.now(), style: s.spell ? undefined : s.style },
    ]);
  }, []);

  const clearImpact = useCallback((i: Impact) => {
    setImpacts((list) => list.filter((x) => x.id !== i.id));
  }, []);

  const shown = useMemo(() => {
    if (!exchange) return fighters;
    const release = released?.exchange === exchange ? released : null;
    if (release?.phase === 2) return fighters;
    const held = new Map(exchange.hits.map((h) => [h.victim, h.was]));
    return fighters.map((f) => {
      const was = held.get(f.participantId);
      if (!was) return f;
      if (!release) return { ...f, ...was };
      // Phase 1: the blow is in, the damage-over-time still to come.
      const tick = release.ticks.get(f.participantId) ?? 0;
      return tick > 0 ? { ...f, hp: Math.min(was.hp, f.hp + tick), isDead: false } : f;
    });
  }, [fighters, exchange, released]);

  return { shown, strikes, impacts, lunges, evades, dots, hitStyles, land, clearImpact };
};

const ArenaScene = ({ fighters, onSelect, aims, turnDeadline, turnPaused, boardArtUrl, outcome, turnNumber }: ArenaSceneProps) => {
  const portrait = usePortraitBoard();
  const { positions, cardScales } = useMemo(() => {
    const mode = portrait ? "portrait" : "landscape";
    const { rowZ, rowSpan } = LAYOUT[mode];
    const footprint = FIGHTER_FOOTPRINT[mode];
    const spots = [
      ...layoutTeam(fighters.filter((f) => f.side === "ally"), rowZ, rowSpan, footprint),
      ...layoutTeam(fighters.filter((f) => f.side === "enemy"), -rowZ, rowSpan, footprint),
    ];
    return {
      positions: new Map<number, Vec3>(spots.map(([id, at]) => [id, at])),
      cardScales: new Map<number, number>(spots.map(([id, , scale]) => [id, scale])),
    };
  }, [fighters, portrait]);
  const { shown, strikes, impacts, lunges, evades, dots, hitStyles, land, clearImpact } = useStrikes(
    fighters,
    positions,
    outcome,
    turnNumber,
  );
  const { orbs, landOrb, castFx, heldEffects } = useCasts(fighters, positions);
  const cards = useMemo(
    () =>
      heldEffects
        ? shown.map((f) => (heldEffects.has(f.participantId) ? { ...f, effects: heldEffects.get(f.participantId)! } : f))
        : shown,
    [shown, heldEffects],
  );
  // Every turn now brings an outcome; the dice keep the moment of the last crit.
  const lastCritAt = useRef<number | null>(null);
  if (outcome?.crits.length) lastCritAt.current = outcome.at;
  const critRollAt = lastCritAt.current;
  // «Облегчённая графика» in the settings: plain resolution, no smoothing, no drifting dust.
  const lowGraphics = useClientPrefs().graphics === "low";

  return (
    <Canvas
      dpr={lowGraphics ? 1 : [1, 1.75]}
      gl={{ antialias: !lowGraphics, alpha: true, powerPreference: "high-performance" }}
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
        lowGraphics={lowGraphics}
      />
      <Fighters
        portrait={portrait}
        fighters={cards}
        positions={positions}
        cardScales={cardScales}
        lunges={lunges}
        evades={evades}
        hitStyles={hitStyles}
        dots={dots}
        castFx={castFx}
        outcome={outcome}
        onSelect={onSelect}
      />
      {aims.map((aim) => {
        const from = positions.get(aim.from);
        const to = positions.get(aim.to);
        return from && to ? <AimArc key={`${aim.kind}-${aim.to}`} from={from} to={to} kind={aim.kind} /> : null;
      })}
      {strikes.map((s) => (
        <Projectile key={s.id} strike={s} onLand={land} />
      ))}
      {orbs.map((s) => (
        <Projectile key={`cast-${s.id}`} strike={s} onLand={landOrb} />
      ))}
      {impacts.map((i) => (
        <ImpactBurst key={i.id} impact={i} onDone={clearImpact} />
      ))}
    </Canvas>
  );
};

export default ArenaScene;
