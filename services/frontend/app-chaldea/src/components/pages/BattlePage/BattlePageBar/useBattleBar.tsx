import { useEffect, useMemo, useRef, useState, type ReactNode, type Dispatch, type SetStateAction } from "react";
import {
  BATTLE_EVENTS_TRANSLATE,
  SKILLS_KEYS,
} from "../../../../helpers/commonConstants";
import axios from "axios";
import toast from "react-hot-toast";
import {
  BASE_URL_BATTLES,
  postAutobattleFeedback,
  postAutobattleSpeed,
} from "../../../../api/api";
import { formatServerDateTime } from "../../../../utils/serverDate";
import { DAMAGE_TYPES } from "../../../AdminSkillsPage/skillConstants";
import { describeEffect, pluralizeTurn, type EffectLike } from "../battleEffects";
import { EQUIPMENT_SLOT_LABELS } from "../../../ProfilePage/constants";
import type { WeaponCoating } from "../../../../utils/itemEffects";
import SkillPicker, {
  type BattleSkill,
  type BattleItem,
} from "../SkillPicker/SkillPicker";

// Shared state and log formatting for the battle control panel. The 2D bar and
// the 3D arena HUD both render from this hook, so battle behaviour stays in one place.

// --- Types ---

interface ParticipantSnapshot {
  participant_id: number;
  character_id: number;
  name: string;
  avatar: string | null;
  skills: unknown;
  attributes: Record<string, number>;
}

interface RuntimeParticipant {
  hp: number;
  mana: number;
  stamina: number;
  energy: number;
  fast_slots: unknown;
  team: number;
  /** FEAT-168 — absent for battles started before the feature shipped */
  weapon_coating?: WeaponCoating | null;
}

interface RuntimeState {
  participants: Record<number, RuntimeParticipant>;
  current_actor: number;
  next_actor: number;
  turn_number: number;
  turn_order: number[];
  total_turns: number;
  first_actor: number;
  deadline_at: string;
  first_cycle?: boolean;
}

interface ResourceEntry {
  current: number;
  max: number;
}

interface ResourceBlock {
  health?: ResourceEntry;
  mana?: ResourceEntry;
  stamina?: ResourceEntry;
  energy?: ResourceEntry;
}

interface CharacterData {
  character_id?: number;
  participant_id?: number;
  name?: string;
  avatar?: string | null;
  skills?: unknown;
  attributes?: Record<string, number>;
  items?: unknown;
  resources?: ResourceBlock[];
}

interface TurnInfo {
  currentCharacterParticipant: {
    id: number;
    characterName: string;
  };
  turn_number: number;
  isOpponentTurn: boolean;
  endsAt: number;
}

/* Keep structurally compatible with ItemSkillCircle's SkillSlot (index signature included). */
export interface SkillSlot {
  id?: number;
  item_id?: number;
  [key: string]: unknown;
}

export interface TurnDataState {
  [key: string]: SkillSlot | null;
}

// TODO: type battle events properly when backend contract is formalized
export interface BattleEvent {
  event: string;
  who?: number;
  source?: number;
  target?: number;
  effects?: EffectLike[];
  item_name?: string;
  recovery?: Record<string, number>;
  skill_id?: number;
  kind?: string;
  effect?: string;
  amount?: number;
  control?: string;
  skill_type?: string;
  damage_type?: string;
  base_attack?: number;
  entry_amount?: number;
  buff_pct?: number;
  after_buffs?: number;
  dodged?: boolean;
  hit_chance_failed?: boolean;
  critical?: boolean;
  resist_pct?: number;
  final?: number;
  energy?: number;
  mana?: number;
  stamina?: number;
  // FEAT-168 — item effects, weapon coating and cleanse. All optional: an
  // older log (or a backend that has not shipped yet) simply omits them.
  reason?: string;
  slot?: string;
  action?: string;
  source_kind?: string;
  turns?: number;
  bonus_damage?: number;
  turns_left?: number;
  active_coating?: string | null;
  quantity_left?: number;
  item_id?: number;
  removed?: Array<EffectLike | string>;
  [key: string]: unknown;
}

export interface TurnLog {
  events: BattleEvent[];
  timestamp: string;
}

interface TurnLogsResponse {
  logs: TurnLog[];
}

export interface BattlePageBarProps {
  battleId: string | undefined;
  turn: TurnInfo;
  setTurn: () => void;
  isAutoBattleOn: boolean;
  toggleAutobattle: () => void;
  autobattleMode: string;
  setAutobattleMode: (mode: string) => void;
  setTurnData: Dispatch<SetStateAction<TurnDataState>>;
  turnData: TurnDataState;
  snapshotData: ParticipantSnapshot[];
  runtimeData: RuntimeState;
  myData: CharacterData;
  opponentData: CharacterData | null;
  isPaused?: boolean;
  controlFullSkip?: string | null;
}
// --- Constants ---

/**
 * FEAT-161: replaces the date formatter deleted from `helpers/helpers.js`,
 * which appended `Z` unconditionally (turning any already-zoned value into
 * `Invalid Date` -> `NaN.NaN.NaN NaN:NaN`) and threw on `null`. The shared helper is
 * offset-tolerant and total; the `ru-RU` «, » between date and time is dropped
 * so the battle log keeps its previous `dd.mm.yyyy hh:mm` look.
 */
const BATTLE_LOG_TIME_FORMAT: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
};

const formatLogTime = (raw: string | null | undefined): string =>
  formatServerDateTime(raw, BATTLE_LOG_TIME_FORMAT).replace(", ", " ");
// --- Damage-type icons (FEAT-143): emoji keep the log readable and self-contained ---
const DAMAGE_TYPE_ICONS: Record<string, string> = {
  all: "\u{1F300}",          // 🌀 общий
  physical: "⚔️",  // ⚔️ физический
  catting: "\u{1F5E1}️",// 🗡️ режущий
  crushing: "\u{1F528}",     // 🔨 дробящий
  piercing: "\u{1F3F9}",     // 🏹 колюще-пронзающий
  magic: "\u{1F52E}",        // 🔮 магический
  fire: "\u{1F525}",         // 🔥 огонь
  ice: "❄️",       // ❄️ лёд
  watering: "\u{1F4A7}",     // 💧 вода
  electricity: "⚡",     // ⚡ электричество
  wind: "\u{1F4A8}",         // 💨 ветер
  sainting: "☀️",  // ☀️ святой
  damning: "\u{1F480}",      // 💀 проклятие
};

/**
 * Russian names for events the shared `BATTLE_EVENTS_TRANSLATE` map does not
 * carry. Every one of them has its own branch below; this map is the safety net
 * so that a shape we did not anticipate still reads as Russian and never leaks
 * a raw English event name into the player's log (ISSUES #2).
 */
const EXTRA_EVENT_LABELS: Record<string, string> = {
  item_rejected: "не смог применить предмет",
  item_broken: "сломал снаряжение",
  weapon_coating_applied: "наносит яд на оружие",
  weapon_coating_expired: "яд на оружии выдохся",
  effects_removed: "снимает эффекты",
  effect_tick: "получает урон от эффекта",
  control_skip: "пропускает ход",
  control_block: "навык заблокирован",
  skill_use: "применяет навык",
  participant_defeated: "повержен",
  participant_timed_out: "не успел сделать ход",
};

const itemName = (event: { item_name?: string }): string =>
  event.item_name?.trim() || "предмет";

// --- Kind labels for skill_use events ---
const SKILL_KIND_LABELS: Record<string, string> = {
  attack: "Атака",
  defense: "Защита",
  support: "Поддержка",
};
export type SlotType = "attack" | "defense" | "support" | "item";

export const useBattleBar = ({
  battleId,
  turn,
  isAutoBattleOn,
  setTurnData,
  turnData,
  snapshotData,
  runtimeData,
  myData,
  opponentData,
  isPaused = false,
  controlFullSkip = null,
}: BattlePageBarProps) => {
  const [isTurnLikeTextShown, setIsTurnLikeTextShown] = useState(true);
  const [isAllTurnsOpen, setIsAllTurnsOpen] = useState(false);
  const [turnLogs, setTurnLogs] = useState<TurnLogsResponse | null>(null);
  const isOpponentTurn = turn.isOpponentTurn || isPaused;
  // The viewer is stunned/paralysed this turn — lock the skill slots; the turn
  // can still be submitted (it just passes) so relabel the button.
  const controlled = Boolean(controlFullSkip);
  // First cycle (FEAT-143): only one skill type allowed. Once one is chosen,
  // the other skill slots lock (items stay free).
  const firstCycle = runtimeData.first_cycle === true;
  const selectedSkillKey = [
    SKILLS_KEYS.attack,
    SKILLS_KEYS.defense,
    SKILLS_KEYS.support,
  ].find((k) => turnData[k]);
  const skillLockedByCycle = (slotType: string) =>
    firstCycle && selectedSkillKey != null && selectedSkillKey !== slotType;
  const [activeTurnIndex, setActiveTurnIndex] = useState(
    runtimeData.turn_number - 1,
  );
  // Whether the history view auto-follows the newest turn. Set to false the
  // moment the user pins an older turn, so live updates stop yanking them back
  // to the last turn (FEAT-143). Re-enabled when they click the newest turn.
  const followLatestRef = useRef(true);
  const [autobattleSpeed, setAutobattleSpeed] = useState<"fast" | "slow">("fast");
  const [speedLoading, setSpeedLoading] = useState(false);
  // Which slot's picker is open (attack/defense/support/item), or null (FEAT-143).
  const [pickerType, setPickerType] = useState<
    "attack" | "defense" | "support" | "item" | null
  >(null);

  // participant_id -> { avatar, name } from the snapshot, for avatar circles.
  const participantById = useMemo(() => {
    const m = new Map<number, { avatar: string | null; name: string }>();
    snapshotData?.forEach((p) =>
      m.set(p.participant_id, { avatar: p.avatar, name: p.name }),
    );
    return m;
  }, [snapshotData]);

  // skill_id -> display name, resolved from every participant's snapshot skills.
  const skillNameById = useMemo(() => {
    const m = new Map<number, string>();
    snapshotData?.forEach((p) => {
      const skills = p.skills as
        | Array<{ skill_id?: number; id?: number; skill_name?: string }>
        | undefined;
      skills?.forEach((sk) => {
        const id = sk.skill_id ?? sk.id;
        if (id != null && sk.skill_name) m.set(Number(id), sk.skill_name);
      });
    });
    return m;
  }, [snapshotData]);

  const totalTurns = runtimeData.turn_number; // completed turns that have logs
  const viewerTeam =
    myData.participant_id != null
      ? runtimeData.participants[myData.participant_id]?.team
      : undefined;
  const sideOf = (pid: number): "ally" | "enemy" =>
    runtimeData.participants[pid]?.team === viewerTeam ? "ally" : "enemy";
  // Show a shortcut back to the newest turn while an older turn is pinned.
  const showJumpToLatest = totalTurns > 0 && activeTurnIndex < totalTurns - 1;

  // Live upcoming order: current actor first, then the next alive participants
  // for one full cycle along the fixed turn_order (FEAT-143 hybrid order).
  const turnQueue = useMemo(() => {
    const order = runtimeData.turn_order ?? [];
    if (!order.length) return [] as number[];
    const startIdx = Math.max(0, order.indexOf(runtimeData.current_actor));
    const isAlive = (pid: number) =>
      (runtimeData.participants[pid]?.hp ?? 0) > 0;
    const queue: number[] = [];
    for (let step = 0; step < order.length; step++) {
      const pid = order[(startIdx + step) % order.length];
      if (pid === runtimeData.current_actor || isAlive(pid)) queue.push(pid);
    }
    return queue;
  }, [runtimeData]);

  useEffect(() => {
    if (!isAutoBattleOn) {
      setAutobattleSpeed("fast");
    }
  }, [isAutoBattleOn]);

  const handleSpeedToggle = async () => {
    if (!myData.participant_id) return;
    const newSpeed = autobattleSpeed === "fast" ? "slow" : "fast";
    setSpeedLoading(true);
    try {
      await postAutobattleSpeed(myData.participant_id, newSpeed);
      setAutobattleSpeed(newSpeed);
    } catch {
      toast.error("Не удалось изменить скорость автобоя");
    } finally {
      setSpeedLoading(false);
    }
  };

  const toggleAllTurnsVisibility = () => {
    setIsAllTurnsOpen(!isAllTurnsOpen);
  };

  // Auto-advance to the newest turn ONLY while the user is following the latest.
  // If they've pinned an older turn to read it, leave their view alone.
  useEffect(() => {
    if (!runtimeData) return;
    if (followLatestRef.current) {
      setActiveTurnIndex(runtimeData.turn_number - 1);
    }
  }, [runtimeData]);

  const selectTurn = (turnIndex: number) => {
    setActiveTurnIndex(turnIndex);
    // Following resumes only when the user jumps back to the newest turn.
    followLatestRef.current = turnIndex >= totalTurns - 1;
  };

  const jumpToLatest = () => {
    followLatestRef.current = true;
    setActiveTurnIndex(totalTurns - 1);
  };

  useEffect(() => {
    if (activeTurnIndex !== null && activeTurnIndex !== undefined) {
      getTurnLogs(activeTurnIndex + 1);
    }
  }, [activeTurnIndex]);

  const getTurnLogs = async (turnNumber: number) => {
    try {
      const { data } = await axios.get<TurnLogsResponse>(
        `${BASE_URL_BATTLES}/battles/battles/${Number(battleId)}/logs/${turnNumber}`,
      );
      setTurnLogs(data);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      const msg =
        err?.response?.data?.detail || "Не удалось загрузить логи хода";
      toast.error(msg);
    }
  };

  const DAMAGE_TYPES_MAP: Record<string, string> = Object.fromEntries(
    DAMAGE_TYPES.map(({ value, label }: { value: string; label: string }) => [value, label]),
  );

  // Damage type as an icon (with the readable name on hover) instead of a word.
  const damageIcon = (dtype?: string): ReactNode => {
    const label = DAMAGE_TYPES_MAP[dtype ?? ""] || dtype || "";
    const icon = DAMAGE_TYPE_ICONS[dtype ?? ""];
    return icon ? (
      <span title={label} aria-label={label} className="text-sm leading-none">
        {icon}
      </span>
    ) : (
      <span className="text-white/60">{label}</span>
    );
  };

  const formatBattleEvent = (
    event: BattleEvent,
    snapshotData: ParticipantSnapshot[],
  ): ReactNode => {
    const getName = (id: number | undefined): ReactNode => {
      if (id === undefined) return null;
      const name = snapshotData.find((p) => p.participant_id === id)?.name;
      return name ? <span className="gold-text text-xs">{name}</span> : null;
    };

    // Which skill(s) the actor used this turn — resolved to a human name.
    if (event.event === "skill_use") {
      const skillName =
        event.skill_id != null
          ? skillNameById.get(Number(event.skill_id))
          : undefined;
      const kind = SKILL_KIND_LABELS[(event.kind as string) ?? ""] ?? "";
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-white/60">применяет</span>
          <span className="text-site-blue">
            {skillName ? `«${skillName}»` : "навык"}
          </span>
          {kind && <span className="text-white/40 text-[11px]">· {kind}</span>}
        </span>
      );
    }

    if (event.event === "apply_effects") {
      const effects = event.effects ?? [];
      if (effects.length === 0) return null;
      return (
        <span className="flex flex-wrap items-center gap-x-1.5">
          {getName(event.who)}
          <span className="text-white/60">
            {event.kind === "item" ? "получает от предмета:" : "получает:"}
          </span>
          {effects.map((effect, i) => {
            const d = describeEffect(effect);
            return (
              <span key={i} className="text-white/85">
                {d.label}
                {d.detail && (
                  <span className="text-white/45"> ({d.detail})</span>
                )}
                {i < effects.length - 1 ? "," : ""}
              </span>
            );
          })}
        </span>
      );
    }

    if (event.event === "item_use") {
      const rec = event.recovery ?? {};
      const parts: string[] = [];
      if (rec.health) parts.push(`+${rec.health} здоровья`);
      if (rec.mana) parts.push(`+${rec.mana} маны`);
      if (rec.energy) parts.push(`+${rec.energy} энергии`);
      // Stamina was applied by the engine but never shown (ISSUES #6).
      if (rec.stamina) parts.push(`+${rec.stamina} выносливости`);
      // The detailed outcome (effects, cleanse, damage) arrives as its own
      // events, so this line stays about the item itself: recovery and stock.
      const left = event.quantity_left;
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-white/60">использует</span>
          <span className="text-site-blue">{itemName(event)}</span>
          {parts.length > 0 && (
            <span className="text-green-400/80">({parts.join(", ")})</span>
          )}
          {typeof left === "number" && (
            <span className="text-white/35 text-[11px]">
              {left > 0 ? `осталось ${left}` : "последний"}
            </span>
          )}
        </span>
      );
    }

    // FEAT-168 — the item could not be used, but the turn still resolved. The
    // only reason today is a coating already on the weapon.
    if (event.event === "item_rejected") {
      const active =
        typeof event.active_coating === "string" && event.active_coating.trim()
          ? `«${event.active_coating}»`
          : "яд";
      const left = Number(event.turns_left ?? 0);
      const why =
        event.reason === "coating_active"
          ? `на оружии ещё действует ${active}${left > 0 ? ` (${pluralizeTurn(left)})` : ""}`
          : "предмет сейчас нельзя применить";
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-white/60">не может применить</span>
          <span className="text-site-blue">{itemName(event)}</span>
          <span className="text-site-red">— {why}</span>
        </span>
      );
    }

    if (event.event === "weapon_coating_applied") {
      const turns = Number(event.turns ?? event.coating_turns ?? 0);
      const bonus = Math.round(Number(event.bonus_damage ?? 0));
      // The coating already buffs this turn's attack, so N turns means N buffed
      // attacks counting the one it was applied on.
      const detail = [
        bonus ? `+${bonus} к урону` : "",
        turns > 0 ? `${pluralizeTurn(turns)}, считая текущий` : "",
      ]
        .filter(Boolean)
        .join(", ");
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-white/60">наносит</span>
          <span className="text-site-blue">{itemName(event)}</span>
          <span className="text-white/60">на оружие</span>
          {detail && <span className="text-white/45">({detail})</span>}
        </span>
      );
    }

    if (event.event === "weapon_coating_expired") {
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-white/60">— яд на оружии выдохся</span>
          {event.item_name && (
            <span className="text-white/45">({itemName(event)})</span>
          )}
        </span>
      );
    }

    if (event.event === "effects_removed") {
      // `who` and `target` are the cleansed participant; `source` is whoever
      // used the item. Entries in `removed` are effect objects.
      const removed = event.removed ?? event.effects ?? [];
      const names = removed
        .map((entry) =>
          typeof entry === "string"
            ? describeEffect({ name: entry }).label
            : describeEffect(entry).label,
        )
        .filter(Boolean);
      const cleansed = event.target ?? event.who;
      const byOther = event.source != null && event.source !== cleansed;
      return (
        <span className="flex flex-wrap items-center gap-1">
          {byOther ? getName(event.source) : getName(cleansed)}
          {event.item_name && (
            <span className="text-site-blue">«{itemName(event)}»</span>
          )}
          <span className="text-white/60">
            {byOther ? "снимает с" : "снимает с себя"}
          </span>
          {byOther && getName(cleansed)}
          <span className="text-white/85">
            {names.length > 0 ? `: ${names.join(", ")}` : ": вредные эффекты"}
          </span>
        </span>
      );
    }

    // Durability roll broke a piece of gear. The backend has emitted this since
    // FEAT-146 but the log printed the raw English name (ISSUES #2).
    if (event.event === "item_broken") {
      const slot = event.slot ? EQUIPMENT_SLOT_LABELS[event.slot] ?? event.slot : null;
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-site-red">
            сломал снаряжение{slot ? `: ${slot}` : ""}
          </span>
        </span>
      );
    }

    // FEAT-163: the turn-timeout sweeper dropped this participant out of the
    // battle. Without this branch the generic fallback below would print the
    // raw event name next to the name.
    if (event.event === "participant_timed_out") {
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-site-red">
            не успел сделать ход и выбыл из боя.
          </span>
        </span>
      );
    }

    // Emitted both by a killing blow and by the timeout drop above. Without a
    // branch it fell through to the raw-event-name fallback.
    if (event.event === "participant_defeated") {
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-site-red">повержен</span>
        </span>
      );
    }

    if (event.event === "control_skip") {
      const label =
        event.control === "Poison"
          ? "Паралич"
          : describeEffect({ name: event.control }).label;
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-site-red">{label} — ход пропущен</span>
        </span>
      );
    }

    if (event.event === "control_block") {
      const kind = SKILL_KIND_LABELS[event.skill_type ?? ""] ?? event.skill_type;
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-site-red">{kind}: навык заблокирован</span>
        </span>
      );
    }

    if (event.event === "effect_tick") {
      // Periodic damage from a lingering effect (bleeding / burn / poison).
      const label = describeEffect({ name: event.effect }).label;
      const amount = Math.round(Number(event.amount ?? 0));
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.target)}
          <span className="text-white/60">{label}</span>
          <span className="font-medium text-site-red">−{amount}</span>
        </span>
      );
    }

    if (event.event === "damage") {
      // Misses: two distinct cases. Show ONLY on a miss — no "попал" on a hit.
      if (event.dodged) {
        return (
          <span className="flex flex-wrap items-center gap-1">
            {getName(event.target)}
            <span className="text-site-red">
              {event.source_kind === "item" ? "уклонился от" : "уклонился от удара"}
            </span>
            {/* A scroll / thrown flask misses too — name it, not a weapon swing */}
            {event.source_kind === "item" && (
              <span className="text-site-blue">«{itemName(event)}»</span>
            )}
            {getName(event.source)}
          </span>
        );
      }
      if (event.hit_chance_failed) {
        return (
          <span className="flex flex-wrap items-center gap-1">
            {getName(event.source)}
            <span className="text-site-red">промахнулся по</span>
            {getName(event.target)}
          </span>
        );
      }
      // Hit: compact source → target, damage icon, final amount, crit marker.
      const finalDmg = Math.round(Number(event.final ?? 0));
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.source)}
          {/* FEAT-168: a damage scroll / thrown flask, not a weapon swing */}
          {event.source_kind === "item" && (
            <span className="text-site-blue">«{itemName(event)}»</span>
          )}
          <span className="text-white/40">→</span>
          {getName(event.target)}
          {damageIcon(event.damage_type)}
          <span className="font-medium text-site-red">−{finalDmg}</span>
          {event.critical && (
            <span className="text-gold text-[11px] uppercase font-medium">
              крит
            </span>
          )}
        </span>
      );
    }

    if (event.event === "resource_spend") {
      // Stamina is not shown in battle (FEAT-143). Muted, de-emphasized line.
      const parts: string[] = [];
      if (event.energy) parts.push(`${event.energy} энергии`);
      if (event.mana) parts.push(`${event.mana} маны`);
      if (parts.length === 0) return null;
      return (
        <span className="text-white/35 text-[11px]">
          Расход: {parts.join(", ")}
        </span>
      );
    }

    // Unknown event — keep it minimal instead of dumping raw fields.
    return (
      <span className="flex flex-wrap items-center gap-1">
        {getName(event.who) || getName(event.source)}
        <span className="text-white/60">
          {BATTLE_EVENTS_TRANSLATE[
            event.event as keyof typeof BATTLE_EVENTS_TRANSLATE
          ] ||
            EXTRA_EVENT_LABELS[event.event] ||
            // Last resort: a readable placeholder, never the raw English name.
            "совершает действие"}
        </span>
        {getName(event.target)}
      </span>
    );
  };
  const renderPicker = (): ReactNode => {
    if (!pickerType || isOpponentTurn) return null;
          const allSkills = (myData.skills as BattleSkill[] | undefined) ?? [];
          const allItems = (myData.items as BattleItem[] | undefined) ?? [];
          const isItem = pickerType === "item";
          const typeSkills = isItem
            ? []
            : allSkills.filter(
                (s) =>
                  (s.skill_type ?? s.skill?.skill_type ?? "").toLowerCase() ===
                  pickerType,
              );
          const pid = myData.participant_id;
          const cooldowns =
            pid != null
              ? ((
                  runtimeData.participants[pid] as {
                    cooldowns?: Record<string, number>;
                  }
                )?.cooldowns ?? {})
              : {};
          const slotKey = isItem
            ? SKILLS_KEYS.item
            : SKILLS_KEYS[pickerType as keyof typeof SKILLS_KEYS];
          const current = turnData[slotKey];
          const selectedId = isItem
            ? ((current as { item_id?: number } | null)?.item_id ?? null)
            : ((current as { id?: number } | null)?.id ?? null);
          return (
            <SkillPicker
              type={pickerType}
              skills={typeSkills}
              items={allItems}
              cooldowns={cooldowns}
              characterId={myData.character_id ?? 0}
              weaponCoating={
                pid != null ? runtimeData.participants[pid]?.weapon_coating ?? null : null
              }
              selectedId={selectedId}
              onSelectSkill={(skill) =>
                setTurnData((prev) => ({
                  ...prev,
                  [slotKey]: skill as unknown as SkillSlot,
                }))
              }
              onSelectItem={(item) =>
                setTurnData((prev) => ({
                  ...prev,
                  [SKILLS_KEYS.item]: item as unknown as SkillSlot,
                }))
              }
              onClear={() =>
                setTurnData((prev) => ({ ...prev, [slotKey]: null }))
              }
              onClose={() => setPickerType(null)}
            />
          );
  };

  const slotKeyOf = (type: SlotType) =>
    type === "item" ? SKILLS_KEYS.item : SKILLS_KEYS[type as keyof typeof SKILLS_KEYS];

  const setSlot = (type: SlotType, data: SkillSlot) =>
    setTurnData((prev) => ({ ...prev, [slotKeyOf(type)]: data }));

  const clearSlot = (type: SlotType) =>
    setTurnData((prev) => ({ ...prev, [slotKeyOf(type)]: null }));

  const clearAllSlots = () =>
    setTurnData({
      [SKILLS_KEYS.attack]: null,
      [SKILLS_KEYS.defense]: null,
      [SKILLS_KEYS.support]: null,
      [SKILLS_KEYS.item]: null,
    });

  const hasAnySlot = Object.values(turnData).some(Boolean);

  const isSlotLocked = (type: SlotType) =>
    type === "item"
      ? isOpponentTurn || controlled
      : isOpponentTurn || controlled || skillLockedByCycle(type);

  /** Who acted on a given 0-based turn index, per the fixed turn order. */
  const actorOfTurn = (turnIndex: number): number | undefined => {
    const order = runtimeData.turn_order ?? [];
    return order.length ? order[turnIndex % order.length] : undefined;
  };

  const activeTurnActorName = (() => {
    const pid = actorOfTurn(activeTurnIndex);
    const actor = snapshotData?.find((p) => p.participant_id === pid);
    return actor?.name ?? (pid === myData.participant_id ? myData.name ?? "" : "");
  })();

  // The autobattle feedback prompt applies only to turns the viewer's own autobattle played.
  const isOwnAutobattleTurn =
    isAutoBattleOn && actorOfTurn(activeTurnIndex) === myData.participant_id;

  const rateTurn = (log: TurnLog, liked: boolean) => {
    setIsTurnLikeTextShown(false);
    const usedSkillIds = log.events
      .filter(
        (e) =>
          e.event === "skill_use" &&
          e.who === myData.participant_id &&
          e.skill_id != null,
      )
      .map((e) => Number(e.skill_id));
    if (myData.participant_id == null || usedSkillIds.length === 0) return;
    void postAutobattleFeedback(myData.participant_id, usedSkillIds, liked).catch(
      (err) => {
        toast.error(
          err?.response?.data?.detail || "Не удалось сохранить оценку хода",
        );
      },
    );
  };

  return {
    isOpponentTurn,
    controlled,
    turnQueue,
    participantById,
    sideOf,
    totalTurns,
    activeTurnIndex,
    selectTurn,
    jumpToLatest,
    showJumpToLatest,
    isAllTurnsOpen,
    toggleAllTurnsVisibility,
    turnLogs,
    formatBattleEvent: (event: BattleEvent) => formatBattleEvent(event, snapshotData),
    formatLogTime,
    activeTurnActorName,
    actorOfTurn,
    isOwnAutobattleTurn,
    isTurnLikeTextShown,
    rateTurn,
    autobattleSpeed,
    speedLoading,
    handleSpeedToggle,
    pickerType,
    setPickerType,
    renderPicker,
    setSlot,
    clearSlot,
    clearAllSlots,
    hasAnySlot,
    isSlotLocked,
  };
};

export type BattleBarState = ReturnType<typeof useBattleBar>;
