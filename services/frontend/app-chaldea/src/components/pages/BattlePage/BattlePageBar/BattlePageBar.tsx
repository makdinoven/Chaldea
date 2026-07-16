import CountdownTimer from "./CountdownTimer/CountdownTimer";
import ItemSkillCircle from "./ItemSkillCircle/ItemSkillCircle";
import { useEffect, useMemo, useRef, useState, type ReactNode, type Dispatch, type SetStateAction } from "react";
import AutobattleModeIcon from "../../../../assets/IconComponents/AutobattleModeIcon";
import Tooltip from "../../../CommonComponents/Tooltip/Tooltip";
import {
  BATTLE_EVENTS_TRANSLATE,
  SKILLS_KEYS,
} from "../../../../helpers/commonConstants";
import axios from "axios";
import toast from "react-hot-toast";
import { BASE_URL_BATTLES, postAutobattleSpeed } from "../../../../api/api";
import { formatDateTime } from "../../../../helpers/helpers";
import { DAMAGE_TYPES } from "../../../AdminSkillsPage/skillConstants";
import { describeEffect, type EffectLike } from "../battleEffects";
import SkillPicker, {
  type BattleSkill,
  type BattleItem,
} from "../SkillPicker/SkillPicker";

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
interface SkillSlot {
  id?: number;
  item_id?: number;
  [key: string]: unknown;
}

interface TurnDataState {
  [key: string]: SkillSlot | null;
}

// TODO: type battle events properly when backend contract is formalized
interface BattleEvent {
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
  [key: string]: unknown;
}

interface TurnLog {
  events: BattleEvent[];
  timestamp: string;
}

interface TurnLogsResponse {
  logs: TurnLog[];
}

interface BattlePageBarProps {
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

const AUTOBATTLE_MODE_BTNS = [
  {
    mode: "balance",
    name: "Сбалансированный режим",
    icon: <AutobattleModeIcon />,
  },
  { mode: "attack", name: "Атакующий режим", icon: <AutobattleModeIcon /> },
  { mode: "defence", name: "Защитный режим", icon: <AutobattleModeIcon /> },
];

const SKILLS_BTNS = [
  { type: SKILLS_KEYS.attack },
  {
    type: SKILLS_KEYS.defense,
  },
  { type: SKILLS_KEYS.support },
];

// --- Autobattle mode SVG stroke color mapping ---
const MODE_STROKE_COLORS: Record<string, string> = {
  attack: "#f37753",
  defence: "#76a6bd",
};

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

// --- Kind labels for skill_use events ---
const SKILL_KIND_LABELS: Record<string, string> = {
  attack: "Атака",
  defense: "Защита",
  support: "Поддержка",
};

// --- Round avatar used by the turn queue and history circles ---
interface AvatarCircleProps {
  avatar?: string | null;
  name?: string;
  size?: number;
  badge?: ReactNode;
  active?: boolean;
  side?: "ally" | "enemy";
  dim?: boolean;
  onClick?: () => void;
  title?: string;
}

const AvatarCircle = ({
  avatar,
  name,
  size = 40,
  badge,
  active,
  side,
  dim,
  onClick,
  title,
}: AvatarCircleProps) => {
  const ring = active
    ? "ring-2 ring-gold shadow-[0_0_10px_rgba(240,217,92,0.55)]"
    : side === "enemy"
      ? "ring-1 ring-site-red/50"
      : "ring-1 ring-white/25";
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      style={{ width: size, height: size }}
      className={`relative shrink-0 transition-transform duration-200 ease-site ${
        onClick ? "cursor-pointer hover:scale-105" : "cursor-default"
      } ${dim ? "opacity-45" : ""} ${active ? "scale-105" : ""}`}
    >
      <span
        className={`flex w-full h-full items-center justify-center rounded-full bg-center bg-cover bg-site-bg overflow-hidden ${ring}`}
        style={avatar ? { backgroundImage: `url("${avatar}")` } : undefined}
      >
        {!avatar && (
          <span className="text-xs font-medium text-white/70">
            {name?.trim()?.[0]?.toUpperCase() ?? "?"}
          </span>
        )}
      </span>
      {badge != null && (
        <span className="absolute -bottom-1 -right-1 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-site-bg text-[10px] font-medium leading-none text-white ring-1 ring-white/30">
          {badge}
        </span>
      )}
    </button>
  );
};

// --- Component ---

const BattlePageBar = ({
  battleId,
  turn,
  setTurn,
  isAutoBattleOn,
  toggleAutobattle,
  autobattleMode,
  setAutobattleMode,
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
          <span className="text-white/60">получает:</span>
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
      return (
        <span className="flex flex-wrap items-center gap-1">
          {getName(event.who)}
          <span className="text-white/60">использует</span>
          <span className="text-site-blue">{event.item_name}</span>
          {parts.length > 0 && (
            <span className="text-green-400/80">({parts.join(", ")})</span>
          )}
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
            <span className="text-site-red">уклонился от удара</span>
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
          ] || event.event}
        </span>
        {getName(event.target)}
      </span>
    );
  };

  return (
    <div className="w-full flex flex-col gap-[15px] font-medium">
      {/* Turn timer — its own small block on top (FEAT-143) */}
      <div className="flex justify-center">
        <div className="gray-bg px-6 py-1.5 text-lg font-medium tracking-wide">
          <CountdownTimer startMilliseconds={turn.endsAt} />
        </div>
      </div>

      {/* Current actor + live turn queue + skill slots */}
      <div className="p-5 flex flex-col items-center gap-3 gray-bg min-h-[160px]">
        <h3 className="gold-text text-lg font-medium uppercase">{turn.currentCharacterParticipant.characterName}</h3>
        {isOpponentTurn && (
          <p className="text-sm uppercase text-white/70">Ход противника</p>
        )}

        {/* Turn queue — who acts next, in order, updating live (FEAT-143) */}
        {turnQueue.length > 0 && (
          <div className="w-full flex items-center justify-center gap-1 overflow-x-auto gold-scrollbar py-1">
            {turnQueue.map((pid, i) => {
              const p = participantById.get(pid);
              const isCurrent = pid === runtimeData.current_actor;
              return (
                <div key={`${pid}-${i}`} className="flex items-center gap-1">
                  <AvatarCircle
                    avatar={p?.avatar}
                    name={p?.name}
                    size={isCurrent ? 44 : 34}
                    active={isCurrent}
                    side={sideOf(pid)}
                    title={p?.name}
                  />
                  {i < turnQueue.length - 1 && (
                    <span className="text-white/25 text-xs">{"›"}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="flex gap-[18px] items-center flex-wrap justify-center">
          {SKILLS_BTNS.map((btn) => (
            <ItemSkillCircle
              choosedItem={turnData[btn.type]}
              onDropItem={(data: SkillSlot) => {
                setTurnData((prev) => ({
                  ...prev,
                  [SKILLS_KEYS[btn.type as keyof typeof SKILLS_KEYS]]: data,
                }));
              }}
              onClear={() => {
                setTurnData((prev) => ({
                  ...prev,
                  [SKILLS_KEYS[btn.type as keyof typeof SKILLS_KEYS]]: null,
                }));
              }}
              onOpen={() =>
                setPickerType(btn.type as "attack" | "defense" | "support")
              }
              key={btn.type}
              isClosed={
                isOpponentTurn || controlled || skillLockedByCycle(btn.type)
              }
              type={btn.type}
            />
          ))}
          {/* Vertical gradient line separator */}
          <span className="w-px h-full bg-gradient-to-b from-transparent via-white/60 to-transparent" />
          <ItemSkillCircle
            choosedItem={turnData[SKILLS_KEYS.item]}
            onDropItem={(data: SkillSlot) => {
              console.log(data);
              setTurnData((prev) => ({
                ...prev,
                [SKILLS_KEYS.item]: data,
              }));
            }}
            onClear={() => {
              setTurnData((prev) => ({
                ...prev,
                [SKILLS_KEYS.item]: null,
              }));
            }}
            onOpen={() => setPickerType("item")}
            type={SKILLS_KEYS.item}
            isClosed={isOpponentTurn || controlled}
          />
          {!isOpponentTurn && Object.values(turnData).some(Boolean) && (
            <button
              onClick={() => {
                setTurnData({
                  [SKILLS_KEYS.attack]: null,
                  [SKILLS_KEYS.defense]: null,
                  [SKILLS_KEYS.support]: null,
                  [SKILLS_KEYS.item]: null,
                });
              }}
              className="ml-2 text-xs uppercase text-white/60 hover:text-site-blue transition-colors duration-200 ease-site"
            >
              Очистить
            </button>
          )}
        </div>
      </div>

      {/* Autobattle controls */}
      <div className="flex justify-between items-center min-h-[60px] gap-5 flex-wrap">
        <div className="flex items-center gap-5">
          {AUTOBATTLE_MODE_BTNS.map((btn) => {
            const isActive = autobattleMode === btn.mode;
            const strokeColor = MODE_STROKE_COLORS[btn.mode];
            /* Inline style targets child SVG path stroke since AutobattleModeIcon has hardcoded stroke="#fff" */
            const svgStyle: Record<string, string> = {};
            if (strokeColor) svgStyle["--mode-stroke"] = strokeColor;

            return (
              <button
                onClick={() => setAutobattleMode(btn.mode)}
                className={`relative transition-all duration-200 ease-site group ${
                  isActive ? "w-[45px] h-[57px]" : "w-[30px] h-10"
                }`}
                key={btn.mode}
                style={svgStyle}
              >
                <span
                  className={`block [&_svg]:transition-all [&_svg]:duration-200 [&_svg]:ease-site ${
                    isActive ? "[&_svg]:w-[45px] [&_svg]:h-[57px]" : ""
                  } ${strokeColor ? "[&_path]:[stroke:var(--mode-stroke)]" : ""}`}
                >
                  {btn.icon}
                </span>
                <Tooltip
                  className="hidden group-hover:block group-hover:opacity-100"
                  name={btn.name}
                />
              </button>
            );
          })}
        </div>

        {isAutoBattleOn && (
          <button
            onClick={handleSpeedToggle}
            disabled={speedLoading}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-card text-sm font-medium
              transition-all duration-200 ease-site
              ${autobattleSpeed === "slow"
                ? "bg-site-blue/20 text-site-blue border border-site-blue/40"
                : "bg-white/10 text-white border border-white/20 hover:border-white/40"
              }
              ${speedLoading ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:bg-white/15"}
            `}
            title={autobattleSpeed === "fast" ? "Переключить на медленный режим" : "Переключить на быстрый режим"}
          >
            <span className="text-base leading-none">{autobattleSpeed === "fast" ? "\u{1F407}" : "\u{1F422}"}</span>
            <span className="hidden sm:inline">
              {autobattleSpeed === "fast" ? "Быстрый" : "Медленный"}
            </span>
          </button>
        )}

        <button
          onClick={toggleAutobattle}
          className="btn-line h-fit ml-auto rounded-card text-sm px-[13.5px] py-2.5"
        >
          {isAutoBattleOn ? "остановить автобой" : "Включить автобой"}
        </button>
      </div>

      {/* Turn history — flat circles carrying the acting avatar (FEAT-143) */}
      <div
        className={`gray-bg overflow-hidden flex flex-col gap-4 px-[30px] py-[25px] transition-all duration-300 ease-in-out ${
          isAllTurnsOpen ? "max-h-[320px]" : "max-h-[150px]"
        }`}
      >
        <div className="flex justify-between items-center uppercase">
          <span>История ходов</span>
          <div className="flex items-center gap-3 normal-case">
            {showJumpToLatest && (
              <button
                onClick={jumpToLatest}
                className="text-site-blue hover:text-gold transition-colors duration-200 ease-site"
              >
                К последнему
              </button>
            )}
            {totalTurns > 10 && (
              <button
                onClick={toggleAllTurnsVisibility}
                className="uppercase text-white hover:text-site-blue transition-colors duration-200 ease-site"
              >
                {isAllTurnsOpen ? "Скрыть" : "Показать все"}
              </button>
            )}
          </div>
        </div>
        {totalTurns > 0 && (
          <ul
            className={`flex flex-wrap gap-x-3 gap-y-4 items-center pr-1 ${
              isAllTurnsOpen ? "overflow-y-auto overflow-x-hidden gold-scrollbar" : ""
            }`}
          >
            {Array.from({ length: totalTurns }, (_, idx) => {
              const order = runtimeData.turn_order ?? [];
              const actorPid = order.length
                ? order[idx % order.length]
                : undefined;
              const p =
                actorPid != null ? participantById.get(actorPid) : undefined;
              return (
                <li key={idx}>
                  <AvatarCircle
                    avatar={p?.avatar}
                    name={p?.name}
                    size={34}
                    badge={idx + 1}
                    active={idx === activeTurnIndex}
                    side={actorPid != null ? sideOf(actorPid) : undefined}
                    onClick={() => selectTurn(idx)}
                    title={`Ход ${idx + 1}${p?.name ? ` · ${p.name}` : ""}`}
                  />
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Battle logs */}
      <div className="flex flex-col gap-5 px-[30px] py-[35px] uppercase gray-bg h-[286px]">
        <div className="flex justify-between">
          <span>
            Логи
            {activeTurnIndex + 1 > 0 && (
              <span>: Ход {activeTurnIndex + 1}</span>
            )}
          </span>
          <span className="gold-text text-base">
            {(() => {
              const currentParticipantId =
                runtimeData.turn_order[
                  activeTurnIndex % runtimeData.turn_order.length
                ];
              // Resolve the acting participant's name from the full snapshot so
              // any teammate / enemy in a group battle is named correctly.
              const actor = snapshotData?.find(
                (p) => p.participant_id === currentParticipantId,
              );
              return (
                actor?.name ??
                (currentParticipantId === myData.participant_id
                  ? myData.name
                  : "")
              );
            })()}
          </span>
        </div>

        {turnLogs && (
          <ul className="flex-1 flex flex-col gap-2.5 overflow-y-auto overflow-x-hidden pr-2.5 gold-scrollbar">
            {turnLogs.logs.map((log, index) => (
              <li
                key={index}
                className="w-full gap-[5px] flex flex-col justify-between items-end text-xs normal-case"
              >
                {log.events.map((event, i) => (
                  <div key={i} className="w-full text-left">
                    {formatBattleEvent(event, snapshotData)}
                  </div>
                ))}
                <div className="mt-2.5 w-full flex justify-between">
                  {isAutoBattleOn &&
                    (() => {
                      const currentParticipantId =
                        runtimeData.turn_order[
                          activeTurnIndex % runtimeData.turn_order.length
                        ];

                      if (currentParticipantId === myData.participant_id) {
                        return <p className="gold-text text-sm">АВТОБОЙ</p>;
                      } else if (
                        currentParticipantId === opponentData?.participant_id
                      ) {
                        return null;
                      }
                    })()}
                  <div className="ml-auto">{formatDateTime(log.timestamp)}</div>
                </div>
                {isTurnLikeTextShown &&
                  isAutoBattleOn &&
                  (() => {
                    const currentParticipantId =
                      runtimeData.turn_order[
                        activeTurnIndex % runtimeData.turn_order.length
                      ];

                    if (currentParticipantId === myData.participant_id) {
                      return (
                        <div className="text-sm">
                          Понравился ли вам ход?{" "}
                          <span
                            onClick={() => setIsTurnLikeTextShown(false)}
                            className="cursor-pointer font-medium text-site-blue underline decoration-[1.5px]"
                          >
                            Да
                          </span>{" "}
                          <span
                            onClick={() => setIsTurnLikeTextShown(false)}
                            className="cursor-pointer font-medium text-site-red underline decoration-[1.5px]"
                          >
                            Нет
                          </span>
                        </div>
                      );
                    } else if (
                      currentParticipantId === opponentData?.participant_id
                    ) {
                      return null;
                    }
                  })()}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Submit turn button */}
      <button
        disabled={isOpponentTurn}
        onClick={setTurn}
        className={`relative rounded-map px-5 py-2.5 font-medium text-2xl uppercase gold-outline gold-outline-thick transition-colors duration-200 ease-site ${
          isOpponentTurn
            ? "cursor-not-allowed opacity-50"
            : "hover:gold-text"
        }`}
      >
        {controlled ? "Пропустить ход" : "Передать ход"}
      </button>

      {/* Skill / item picker (FEAT-143) — opened from a slot */}
      {pickerType &&
        !isOpponentTurn &&
        (() => {
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
        })()}
    </div>
  );
};

export default BattlePageBar;
