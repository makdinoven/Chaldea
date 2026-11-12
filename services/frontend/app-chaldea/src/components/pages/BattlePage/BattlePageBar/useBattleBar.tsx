import { createElement, useEffect, useMemo, useRef, useState, type ReactNode, type Dispatch, type SetStateAction } from "react";
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
import type { ParticipantPassiveFields } from "../battleTypes";
import { effectiveManaCost, type PayerBars } from "../../../../utils/passiveCosts";
import SkillPicker, {
  type BattleSkill,
  type BattleItem,
  type SkillPickerProps,
} from "../SkillPicker/SkillPicker";

// Shared state and log formatting for the battle control panel. The 2D bar and
// the 3D arena HUD both render from this hook, so battle behaviour stays in one place.

// --- Types ---

interface ParticipantSnapshot extends ParticipantPassiveFields {
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
  /** FEAT-190 — total passive shield; absent in older states. */
  shield?: number;
  /** FEAT-212 — a caravan escort in its raid battle: autobattle is refused (absent in older states). */
  autobattle_forbidden?: boolean;
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

// Resource names for `resource_tick` lines in the chronicle.
const RESOURCE_TICK_LABELS: Record<string, string> = {
  hp: "HP",
  mana: "маны",
  energy: "энергии",
  stamina: "выносливости",
};

// Log name of a passive by key — only for a snapshot that lacks the passive
// (the snapshot's own name, from the skills-service registry, wins).
const PASSIVE_LOG_NAMES: Record<string, string> = {
  berserker_rage: "Ярость",
  // FEAT-189 — wave 1 (names mirror skills-service `app/subclasses.py`).
  inquisitor_heresy_seal: "Печать ереси",
  saber_monster_hunter: "Охотник на чудовищ",
  gladiator_arena: "Арена",
  agent_weak_spot: "Слабое место",
  lancer_pin: "Пригвоздить",
  mechanic_shrapnel: "Шрапнель",
  archer_first_blood: "Первая кровь",
  assassin_from_shadow: "Из тени",
  trickster_deceit: "Обман",
  monk_harmony: "Гармония",
  salamander_kindling: "Разгорание",
  caster_pure_energy: "Чистая энергия",
  sparkmage_chain_lightning: "Цепная молния",
  // FEAT-190 — wave 2.
  paladin_sacred_vow: "Священный обет",
  guardian_retribution: "Возмездие",
  bard_rhythm: "Ритм",
  necromancer_blood_price: "Плата кровью",
  etheriad_spirit_whisper: "Шёпот духов",
  auromancer_tide: "Прилив",
  priest_faith: "Вера",
};
const PASSIVE_LOG_FALLBACK = "пассивка";

// FEAT-189 — an extra hit from a passive, so it does not read as an AoE splash.
const EXTRA_HIT_LABELS: Record<string, string> = {
  splash: "осколок",
  chain: "перескок",
  echo: "повтор",
};

// FEAT-189 — stats the Lancer steals (`passive_proc` kind `pin`, field `stolen`).
const STOLEN_STAT_LABELS: Record<string, { label: string; unit: string }> = {
  dodge: { label: "уклонения", unit: "%" },
  critical_hit_chance: { label: "шанса крита", unit: " п.п." },
};

// FEAT-190 — what the Etheriad's spirits did (`passive_proc` kind `spirit_whisper`, field `mode`).
const SPIRIT_WHISPER_LABELS: Record<string, { label: string; unit: string }> = {
  ward: { label: "стойкость", unit: "% сопр." },
  curse: { label: "уязвимость", unit: "% сопр." },
  might: { label: "сила", unit: "% урона" },
};

/** One passive's share of an event (FEAT-189 log contract, battle-service §3.5). */
export interface PassiveContribution {
  key: string;
  /** damage_pct | resist_pct | forced_crit | resist_ignore | extra_hit | deceit | duration_plus | mana_discount
   *  | lifesteal | reflect | redirect | blood_price (FEAT-190) */
  kind: string;
  value?: number;
  /** participant_id of the passive's owner, when it is one participant's passive. */
  owner?: number;
}

const fmtNum = (n: number): string => String(Math.round(n * 10) / 10);
const signed = (n: number): string => (n < 0 ? `−${fmtNum(-n)}` : `+${fmtNum(n)}`);

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
  // FEAT-188 — set on a landed blow when the attacker's subclass passive added
  // damage (passive_pct > 0); its share is already inside buff_pct.
  passive_key?: string;
  passive_pct?: number;
  // FEAT-189 — every passive that touched this event (attacker and defender
  // side). When present it replaces the single FEAT-188 passive_pct segment.
  passives?: PassiveContribution[];
  forced_crit?: boolean;
  resist_ignored_pct?: number;
  /** splash (Шрапнель) | chain / echo (Цепная молния) */
  extra_hit?: string;
  extra_mult?: number;
  /** A Trickster's «Обман» — also flagged `dodged`, so 3D animates a dodge. */
  deceived?: boolean;
  // `passive_proc` fields (its `kind` reuses the field above).
  key?: string;
  value?: number;
  stacks?: number;
  stolen?: Record<string, number> | number;
  mana_discount?: number;
  // FEAT-190 — shields, reflect, redirect, blood price (battle-service §3.5).
  /** Damage a shield took off this blow (already inside `final`). */
  absorbed?: number;
  /** The target's shield left after the blow. */
  shield_left?: number;
  /** A Guardian's «Возмездие»: `source` = Guardian, `target` = the attacker. */
  reflected?: boolean;
  /** A Trickster's «Обман» sent this blow into the attacker's ally. */
  redirected?: boolean;
  /** participant_id of the Trickster who deceived the attacker. */
  deceived_by?: number;
  /** `resource_spend`: HP the Necromancer paid for missing mana. */
  hp_paid?: number;
  /** `passive_proc`: a shield total after the proc. */
  shield?: number;
  /** `passive_proc`: inspiration group/solo, spirit whisper ward/curse/might. */
  mode?: string;
  /** `passive_proc`: participants the proc touched. */
  targets?: number[];
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
  /** Skill types Knockdown / Windburn take from the viewer's next turn. */
  controlBlocked?: string[];
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

/** FEAT-212: shown instead of the autobattle controls to a caravan escort in its raid battle. */
export const AUTOBATTLE_FORBIDDEN_TEXT = "Охранникам каравана автобой недоступен — в налёте вы ходите сами";

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
  controlBlocked = [],
}: BattlePageBarProps) => {
  const [isTurnLikeTextShown, setIsTurnLikeTextShown] = useState(true);
  const [isAllTurnsOpen, setIsAllTurnsOpen] = useState(false);
  const [turnLogs, setTurnLogs] = useState<TurnLogsResponse | null>(null);
  // Turn number the loaded logs belong to — they arrive after the turn index moves on.
  const [turnLogsTurn, setTurnLogsTurn] = useState<number | null>(null);
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
      setTurnLogsTurn(turnNumber);
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

    // FEAT-189 — a passive's display name: the owner's snapshot name (registry),
    // then the local map, then a neutral word.
    const passiveNameOf = (key: unknown, owner?: number): string => {
      if (typeof key !== "string" || !key) return PASSIVE_LOG_FALLBACK;
      const own =
        owner != null
          ? snapshotData.find((p) => p.participant_id === owner)?.passive
          : undefined;
      return (own?.key === key ? own.name : undefined) || PASSIVE_LOG_NAMES[key] || PASSIVE_LOG_FALLBACK;
    };

    // Text after the name for one contribution; null = render nothing (unknown
    // kind or nothing to say) — new kinds must never break the log.
    const contributionDetail = (c: PassiveContribution): string | null => {
      const v = Number(c.value ?? 0);
      if (!Number.isFinite(v)) return null;
      switch (c.kind) {
        case "damage_pct":
          return v ? ` ${signed(v)}%` : null;
        case "resist_pct":
          return v ? `: сопр. ${signed(v)}%` : null;
        case "forced_crit":
          return v ? `: крит +${fmtNum(v)}%` : ": крит";
        case "resist_ignore":
          return v ? `: пробивает ${fmtNum(v)}% сопр.` : null;
        case "extra_hit":
          return v ? `: ${fmtNum(v)}% урона` : "";
        case "duration_plus":
          return v > 0 ? `: +${pluralizeTurn(Math.round(v))}` : "";
        case "mana_discount":
          return v ? `: −${fmtNum(Math.abs(v))} маны` : null;
        // FEAT-190.
        case "lifesteal":
          // «Ярость» also adds damage on the same blow — say which part this is.
          return v > 0
            ? `${c.key === "berserker_rage" ? ": вампиризм" : ""} +${fmtNum(v)} HP`
            : null;
        case "reflect":
          return v > 0 ? `: −${fmtNum(v)}` : null;
        case "redirect":
          return v ? `: ${fmtNum(v)}% урона` : "";
        case "blood_price":
          return v > 0 ? ` −${fmtNum(v)} HP` : null;
        default:
          return null;
      }
    };

    const renderContributions = (list: unknown): ReactNode => {
      if (!Array.isArray(list)) return null;
      return list.map((raw, i) => {
        if (!raw || typeof raw !== "object") return null;
        const c = raw as PassiveContribution;
        if (typeof c.key !== "string" || typeof c.kind !== "string") return null;
        const detail = contributionDetail(c);
        if (detail === null) return null;
        return (
          <span key={`passive-${i}`} className="text-white/60 text-[11px]">
            · <span className="gold-text">{passiveNameOf(c.key, c.owner)}</span>
            {detail}
          </span>
        );
      });
    };

    // Effect names of a `passive_proc` (raw DB rows or normalized effects).
    const effectNames = (list: unknown): string[] =>
      Array.isArray(list)
        ? list
            .map((e) => {
              if (typeof e === "string") return describeEffect({ name: e }).label;
              if (!e || typeof e !== "object") return "";
              const row = e as Record<string, unknown>;
              const str = (v: unknown) => (typeof v === "string" ? v : undefined);
              return describeEffect({
                ...(row as EffectLike),
                name: str(row.name) ?? str(row.effect_name),
                attribute: str(row.attribute) ?? str(row.attribute_key),
              }).label;
            })
            .filter(Boolean)
        : [];

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
          {/* FEAT-189: «· Обман: +1 ход» / «· Разгорание: +1 ход» */}
          {renderContributions(event.passives)}
        </span>
      );
    }

    // FEAT-189 — a passive fired outside a damage number: stacks, immunity, a
    // readied shadow, the Agent's bonus effects. Unknown kinds render nothing.
    if (event.event === "passive_proc") {
      const name = <span className="gold-text">{passiveNameOf(event.key, event.who)}</span>;
      const value = Number(event.value ?? 0);
      const stacks = Number(event.stacks ?? 0);
      const stacksNote =
        Number.isFinite(stacks) && stacks > 0 ? (
          <span className="text-white/45 text-[11px]">(стаков: {stacks})</span>
        ) : null;
      // Varargs children (not an array) — no React key warnings.
      const line = (...children: ReactNode[]) =>
        createElement("span", { className: "flex flex-wrap items-center gap-1" }, ...children);
      const muted = (text: string) => <span className="text-white/60">{text}</span>;
      switch (event.kind) {
        case "heresy_stack":
          return line(
            getName(event.who),
            name,
            muted("—"),
            getName(event.target),
            value ? muted(`сопр. к магии и стихиям −${fmtNum(Math.abs(value))}%`) : null,
            stacksNote,
          );
        case "pin": {
          const stolen = event.stolen;
          const parts =
            stolen && typeof stolen === "object"
              ? Object.entries(stolen)
                  .filter(([, amt]) => Number(amt) > 0)
                  .map(([stat, amt]) => {
                    const meta = STOLEN_STAT_LABELS[stat];
                    return meta
                      ? `${fmtNum(Number(amt))}${meta.unit} ${meta.label}`
                      : `${fmtNum(Number(amt))} (${stat})`;
                  })
              : typeof stolen === "number" && stolen > 0
                ? [fmtNum(stolen)]
                : [];
          return line(
            getName(event.who),
            name,
            muted(parts.length > 0 ? "крадёт у" : "пригвождает"),
            getName(event.target),
            parts.length > 0 ? <span className="text-white/85">{parts.join(", ")}</span> : null,
            stacksNote,
          );
        }
        case "saber_kill":
          return line(
            getName(event.who),
            name,
            muted(value ? `— урон +${fmtNum(value)}% до конца забега` : "— убийство засчитано"),
            stacksNote,
          );
        case "saber_resolve":
          return line(
            getName(event.who),
            <span className="gold-text">Несгибаемость</span>,
            muted(value ? `— сопротивления +${fmtNum(value)}%` : "— сопротивления растут"),
            stacksNote,
          );
        case "shadow_ready":
          return line(getName(event.who), name, muted("— следующая атака будет критом"));
        case "control_immune": {
          const names = effectNames(event.effects);
          return line(
            getName(event.who),
            name,
            <span className="text-emerald-400/90">
              — контроль не сработал{names.length > 0 ? `: ${names.join(", ")}` : ""}
            </span>,
          );
        }
        case "weak_spot": {
          const names = effectNames(event.effects);
          if (names.length === 0) return null;
          return line(
            getName(event.who),
            name,
            muted("—"),
            getName(event.target),
            muted("получает:"),
            <span className="text-white/85">{names.join(", ")}</span>,
          );
        }
        // FEAT-190 — wave 2.
        case "vow": {
          // «Священный обет: щит N, снято: X»
          const names = effectNames(event.effects);
          return line(
            getName(event.who),
            name,
            <span className="text-site-blue">
              — щит {value > 0 ? fmtNum(value) : "поднят"}
            </span>,
            names.length > 0 ? muted(`· снято: ${names.join(", ")}`) : null,
          );
        }
        case "tide":
          // «Прилив: щит <цель> +N»
          if (!(value > 0)) return null;
          return line(
            getName(event.who),
            name,
            muted("— щит"),
            getName(event.target ?? event.who),
            <span className="text-site-blue">+{fmtNum(value)}</span>,
          );
        case "shield_absorb": {
          // DoT / effect damage soaked by a shield (strikes carry `absorbed`).
          if (!(value > 0)) return null;
          const left = Math.round(Number(event.shield ?? 0));
          return line(
            muted("Щит"),
            getName(event.who),
            muted("поглотил"),
            <span className="text-site-blue">{fmtNum(value)}</span>,
            Number.isFinite(left) && left > 0 ? muted(`(осталось ${left})`) : null,
          );
        }
        case "kill_heal":
          // «Плата кровью +N HP» for a kill.
          if (!(value > 0)) return null;
          return line(
            getName(event.who),
            name,
            <span className="text-emerald-400">+{fmtNum(value)} HP</span>,
            event.target != null ? muted("за убийство") : null,
            getName(event.target),
          );
        case "inspiration": {
          // «Вдохновение ×N (+X% урона)»
          if (!(stacks > 0)) return null;
          const solo = event.mode === "solo";
          return line(
            getName(event.who),
            name,
            muted("—"),
            <span className="gold-text">Вдохновение ×{stacks}</span>,
            value > 0 ? (
              <span className="text-emerald-400/90">
                (+{fmtNum(value)}% урона{solo ? ", себе" : ""})
              </span>
            ) : null,
          );
        }
        case "inspiration_end":
          return line(getName(event.who), name, muted("— Вдохновение угасло"));
        case "spirit_whisper": {
          const meta = SPIRIT_WHISPER_LABELS[String(event.mode ?? "")];
          if (!meta) return null;
          return line(
            getName(event.who),
            name,
            muted("—"),
            getName(event.target),
            <span className={value < 0 ? "text-site-red" : "text-emerald-400/90"}>
              {meta.label}
              {value ? ` ${signed(value)}${meta.unit}` : ""}
            </span>,
          );
        }
        default:
          return null;
      }
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
      // events, so this line stays about the item itself. No stock count: a
      // belt slot holds one item and is spent whole.
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-white/60">использует</span>
          <span className="text-site-blue">{itemName(event)}</span>
          {parts.length > 0 && (
            <span className="text-green-400/80">({parts.join(", ")})</span>
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
      // Periodic damage from a lingering effect (bleeding / burn / poison, or an
      // "HP −" stat modifier with a duration — its attribute names the label).
      const label = describeEffect({
        name: event.effect,
        attribute: typeof event.attribute === "string" ? event.attribute : undefined,
      }).label;
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
      // FEAT-189: an extra hit from a passive (Шрапнель / Цепная молния) is
      // tagged so it does not read as an ordinary AoE splash.
      const extraTag = event.extra_hit ? (
        <span className="text-site-blue text-[11px]">
          ↳ {EXTRA_HIT_LABELS[event.extra_hit] ?? "доп. удар"}
        </span>
      ) : null;
      // FEAT-189: the Trickster's «Обман» — the attack did not pass. Also
      // flagged `dodged` (3D animates a dodge), so it must come first.
      if (event.deceived) {
        return (
          <span className="flex flex-wrap items-center gap-1">
            {extraTag}
            {getName(event.target)}
            <span className="text-site-red">обманул</span>
            {getName(event.source)}
            {event.source_kind === "item" && (
              <span className="text-site-blue">«{itemName(event)}»</span>
            )}
            <span className="text-white/60 text-[11px]">
              · <span className="gold-text">{passiveNameOf("trickster_deceit", event.target)}</span>
            </span>
          </span>
        );
      }
      // Misses: two distinct cases. Show ONLY on a miss — no "попал" on a hit.
      if (event.dodged) {
        return (
          <span className="flex flex-wrap items-center gap-1">
            {extraTag}
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
            {extraTag}
            {getName(event.source)}
            <span className="text-site-red">промахнулся по</span>
            {getName(event.target)}
          </span>
        );
      }
      // Hit: compact source → target, damage icon, final amount, crit marker.
      const finalDmg = Math.round(Number(event.final ?? 0));
      // FEAT-190: what a shield took off this blow (already inside `final`).
      const absorbed = Math.round(Number(event.absorbed ?? 0));
      const absorbedNote =
        Number.isFinite(absorbed) && absorbed > 0 ? (
          <span className="text-site-blue text-[11px]">(щит поглотил {absorbed})</span>
        ) : null;
      // FEAT-190: a Guardian's «Возмездие» — «<Хранитель> — Возмездие: <атакующий> −N».
      if (event.reflected) {
        return (
          <span className="flex flex-wrap items-center gap-1">
            {getName(event.source)}
            <span className="text-white/60">—</span>
            <span className="gold-text">{passiveNameOf("guardian_retribution", event.source)}:</span>
            {getName(event.target)}
            {damageIcon(event.damage_type)}
            <span className="font-medium text-site-red">−{finalDmg}</span>
            {absorbedNote}
          </span>
        );
      }
      // FEAT-190: «Обман» sent the blow into the attacker's own ally at reduced damage.
      if (event.redirected) {
        const redirect = Array.isArray(event.passives)
          ? event.passives.find((c) => c && c.kind === "redirect")
          : undefined;
        const trickster = event.deceived_by ?? redirect?.owner;
        return (
          <span className="flex flex-wrap items-center gap-1">
            {getName(event.source)}
            {event.source_kind === "item" && (
              <span className="text-site-blue">«{itemName(event)}»</span>
            )}
            <span className="text-white/60">— удар ушёл в</span>
            {getName(event.target)}
            <span className="text-white/60 text-[11px]">
              (<span className="gold-text">{passiveNameOf("trickster_deceit", trickster)}</span>
              {trickster != null ? " " : ""}
              {getName(trickster)})
            </span>
            {damageIcon(event.damage_type)}
            <span className="font-medium text-site-red">−{finalDmg}</span>
            {absorbedNote}
          </span>
        );
      }
      // FEAT-189: every passive on this blow (attacker and defender side). A log
      // without the list (FEAT-188, before wave 1) keeps the single rage segment.
      const hasPassiveList = Array.isArray(event.passives) && event.passives.length > 0;
      // FEAT-188: the attacker's passive raised the blow — «· Ярость +12%».
      const passivePct = Math.round(Number(event.passive_pct ?? 0));
      const passiveName =
        !hasPassiveList && passivePct > 0
          ? snapshotData.find((p) => p.participant_id === event.source)?.passive?.name ||
            (event.passive_key ? PASSIVE_LOG_NAMES[event.passive_key] : undefined) ||
            PASSIVE_LOG_FALLBACK
          : null;
      return (
        <span className="flex flex-wrap items-center gap-1">
          {extraTag}
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
          {absorbedNote}
          {passiveName && (
            <span className="text-white/60 text-[11px]">
              · <span className="gold-text">{passiveName}</span> +{passivePct}%
            </span>
          )}
          {hasPassiveList && renderContributions(event.passives)}
        </span>
      );
    }

    if (event.event === "resource_tick") {
      // One dose of a resource-over-time effect (HP / mana / energy ± per turn).
      const amount = Math.round(Number(event.amount ?? 0));
      const resource = RESOURCE_TICK_LABELS[String(event.attribute ?? "")] ?? "";
      if (!amount) return null;
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.target)}
          <span className="text-white/60">эффект</span>
          <span className={`font-medium ${amount > 0 ? "text-emerald-400" : "text-site-red"}`}>
            {amount > 0 ? "+" : "−"}
            {Math.abs(amount)} {resource}
          </span>
        </span>
      );
    }

    if (event.event === "resource_spend") {
      // Stamina is not shown in battle (FEAT-143). Muted, de-emphasized line.
      const parts: string[] = [];
      if (event.energy) parts.push(`${event.energy} энергии`);
      if (event.mana) parts.push(`${event.mana} маны`);
      // FEAT-190: the Necromancer's «Плата кровью» — missing mana paid with HP.
      const blood = Array.isArray(event.passives)
        ? event.passives.find((c) => c && c.kind === "blood_price")
        : undefined;
      const hpPaid = Math.round(Number(event.hp_paid ?? blood?.value ?? 0));
      const hasBlood = Number.isFinite(hpPaid) && hpPaid > 0;
      if (parts.length === 0 && !hasBlood) return null;
      // FEAT-189: the Caster's «Чистая энергия» discount, if any.
      const discount = Array.isArray(event.passives)
        ? event.passives.find((c) => c && c.kind === "mana_discount")
        : undefined;
      const discountValue = Number(discount?.value ?? event.mana_discount ?? 0);
      return (
        <span className="text-white/35 text-[11px]">
          Расход: {parts.join(", ")}
          {Number.isFinite(discountValue) && discountValue > 0 && (
            <>
              {" · "}
              <span className="gold-text">
                {passiveNameOf(discount?.key ?? "caster_pure_energy", event.who)}
              </span>{" "}
              −{fmtNum(discountValue)} маны
            </>
          )}
          {hasBlood && (
            <>
              {parts.length > 0 ? " · " : ""}
              <span className="gold-text">
                {passiveNameOf(blood?.key ?? "necromancer_blood_price", event.who)}
              </span>{" "}
              <span className="text-stat-hp/80">−{hpPaid} HP</span>
            </>
          )}
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
  // FEAT-189 — the viewer's own subclass passive (the Caster's skills cost less
  // mana); the key comes from the viewer's snapshot entry (fixed at battle start).
  const myPassiveKey: string | null =
    myData.participant_id != null
      ? snapshotData?.find((p) => p.participant_id === myData.participant_id)?.passive?.key ?? null
      : null;

  // The viewer's bars right now — the skill cards grey out what they cannot afford
  // (FEAT-190: HP too — the Necromancer tops a mana shortfall up with health).
  const myResources: PayerBars = (() => {
    const live =
      myData.participant_id != null ? runtimeData.participants[myData.participant_id] : undefined;
    return { mana: live?.mana ?? 0, energy: live?.energy ?? 0, hp: live?.hp ?? 0 };
  })();

  /**
   * The bars a card in `slotKey` is paid from: the server charges every chosen
   * skill at the end of the turn, after self restores and the fast-slot item —
   * so the OTHER slots' costs and restores count too (`passiveCosts.PayerBars`).
   */
  const turnBudgetFor = (slotKey: string): PayerBars => {
    const live =
      myData.participant_id != null
        ? (runtimeData.participants[myData.participant_id] as
            | (RuntimeParticipant & { max_mana?: number; max_energy?: number })
            | undefined)
        : undefined;
    const n = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);
    let restoreMana = 0;
    let restoreEnergy = 0;
    let spentMana = 0;
    let spentEnergy = 0;
    for (const key of [SKILLS_KEYS.attack, SKILLS_KEYS.defense, SKILLS_KEYS.support]) {
      if (key === slotKey) continue;
      const chosen = turnData[key] as Record<string, unknown> | null;
      if (!chosen) continue;
      spentMana += effectiveManaCost(n(chosen.cost_mana), myPassiveKey);
      spentEnergy += n(chosen.cost_energy);
      restoreMana += n(chosen.restore_mana);
      restoreEnergy += n(chosen.restore_energy);
    }
    if (slotKey !== SKILLS_KEYS.item) {
      const item = turnData[SKILLS_KEYS.item] as Record<string, unknown> | null;
      if (item) {
        restoreMana += n(item.mana_recovery);
        restoreEnergy += n(item.energy_recovery);
      }
    }
    return {
      ...myResources,
      maxMana: live?.max_mana,
      maxEnergy: live?.max_energy,
      restoreMana,
      restoreEnergy,
      spentMana,
      spentEnergy,
    };
  };

  /** Everything the skill / item chooser needs — the 2D modal and the 3D hand alike. */
  const pickerProps = (): SkillPickerProps | null => {
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
          return {
            type: pickerType,
            skills: typeSkills,
            items: allItems,
            cooldowns,
            characterId: myData.character_id ?? 0,
            weaponCoating:
              pid != null ? runtimeData.participants[pid]?.weapon_coating ?? null : null,
            passiveKey: myPassiveKey,
            resources: turnBudgetFor(slotKey),
            selectedId,
            onSelectSkill: (skill) =>
              setTurnData((prev) => ({
                ...prev,
                [slotKey]: skill as unknown as SkillSlot,
              })),
            onSelectItem: (item) =>
              setTurnData((prev) => ({
                ...prev,
                [SKILLS_KEYS.item]: item as unknown as SkillSlot,
              })),
            onClear: () => setTurnData((prev) => ({ ...prev, [slotKey]: null })),
            onClose: () => setPickerType(null),
          };
  };

  const renderPicker = (): ReactNode => {
    const props = pickerProps();
    return props ? <SkillPicker {...props} /> : null;
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

  /** Slot taken away by control (stun / paralysis, or Knockdown / Windburn on its type). */
  const isSlotChained = (type: SlotType) => controlled || controlBlocked.includes(type);

  const isSlotLocked = (type: SlotType) =>
    type === "item"
      ? isOpponentTurn || controlled
      : isOpponentTurn || isSlotChained(type) || skillLockedByCycle(type);

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

  // FEAT-212: caravan escorts fight a raid by themselves — the autobattle controls are hidden for them.
  const autobattleForbidden =
    myData.participant_id != null &&
    runtimeData?.participants?.[myData.participant_id]?.autobattle_forbidden === true;

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
    isSlotChained,
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
    turnLogsTurn,
    formatBattleEvent: (event: BattleEvent) => formatBattleEvent(event, snapshotData),
    formatLogTime,
    activeTurnActorName,
    actorOfTurn,
    isOwnAutobattleTurn,
    autobattleForbidden,
    isTurnLikeTextShown,
    rateTurn,
    autobattleSpeed,
    speedLoading,
    handleSpeedToggle,
    pickerType,
    setPickerType,
    renderPicker,
    pickerProps,
    myResources,
    myPassiveKey,
    setSlot,
    clearSlot,
    clearAllSlots,
    hasAnySlot,
    isSlotLocked,
  };
};

export type BattleBarState = ReturnType<typeof useBattleBar>;
