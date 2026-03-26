import CountdownTimer from "./CountdownTimer/CountdownTimer";
import ItemSkillCircle from "./ItemSkillCircle/ItemSkillCircle";
import { useEffect, useState, type ReactNode, type Dispatch, type SetStateAction } from "react";
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
import { getDamageLabel } from "../CharacterSide/CharacterInventory/InventoryItem/InventoryItem";

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

interface SkillSlot {
  id?: number;
  item_id?: number;
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
  effects?: string[];
  item_name?: string;
  recovery?: Record<string, number>;
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

interface TurnEntry {
  my?: boolean;
  isActive?: boolean;
  waiting: boolean;
  turnIndex: number;
}

interface TurnPair {
  pair: TurnEntry[];
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
}: BattlePageBarProps) => {
  const [isTurnLikeTextShown, setIsTurnLikeTextShown] = useState(true);
  const [isAllTurnsOpen, setIsAllTurnsOpen] = useState(false);
  const [turnLogs, setTurnLogs] = useState<TurnLogsResponse | null>(null);
  const [turns, setTurns] = useState<TurnPair[]>([]);
  const isOpponentTurn = turn.isOpponentTurn || isPaused;
  const [activeTurnIndex, setActiveTurnIndex] = useState(
    runtimeData.turn_number - 1,
  );
  const [autobattleSpeed, setAutobattleSpeed] = useState<"fast" | "slow">("fast");
  const [speedLoading, setSpeedLoading] = useState(false);

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

  useEffect(() => {
    if (!runtimeData || !myData) return;

    const { turn_order, total_turns, first_actor } = runtimeData;
    const myId = myData.participant_id;
    const generatedTurns: TurnPair[] = [];

    for (let i = 0; i < total_turns; i += 2) {
      let first: TurnEntry;
      if (i < total_turns - 1) {
        first = {
          my: first_actor === myId,
          isActive: i === total_turns - 2,
          waiting: false,
          turnIndex: i,
        };
      } else {
        first = { waiting: true, turnIndex: i };
      }

      let second: TurnEntry | null;
      if (i + 1 < total_turns - 1) {
        const secondActorId = turn_order[(i + 1) % turn_order.length];
        second = {
          my: secondActorId === myId,
          isActive: i + 1 === total_turns - 2,
          waiting: false,
          turnIndex: i + 1,
        };
      } else if (i + 1 === total_turns - 1) {
        second = { waiting: true, turnIndex: i + 1 };
      } else {
        second = null;
      }

      const pair = second ? [first, second] : [first];
      generatedTurns.push({ pair });
    }

    setTurns(generatedTurns);
    setActiveTurnIndex(runtimeData.turn_number - 1);
  }, [runtimeData, myData]);

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

  const formatBattleEvent = (
    event: BattleEvent,
    snapshotData: ParticipantSnapshot[],
  ): ReactNode => {
    const getName = (id: number | undefined): ReactNode => {
      if (id === undefined) return null;
      const name = snapshotData.find((p) => p.participant_id === id)?.name;
      return name ? <span className="gold-text text-xs">{name}</span> : null;
    };

    const formatValue = (value: unknown): ReactNode => {
      if (typeof value === "number" || typeof value === "boolean") {
        return <span className="text-site-blue">{String(value)}</span>;
      }
      return <span className="text-white">{String(value)}</span>;
    };

    const bold = (
      label: string,
      value: unknown,
      isPercent?: boolean,
      percentSign?: boolean,
    ): ReactNode =>
      value !== undefined ? (
        <div className="ml-2.5">
          {" "}
          <span className="text-white/50">{label ? label : ""}</span>
          <span className={`${value === 0 ? "text-site-red" : ""}`}>
            {isPercent ? formatValue((value as number) / 100) : formatValue(value)}
            {percentSign ? <span className="text-site-blue">%</span> : ""}
          </span>
        </div>
      ) : null;

    const action =
      BATTLE_EVENTS_TRANSLATE[event.event as keyof typeof BATTLE_EVENTS_TRANSLATE] || event.event;

    if (event.event === "apply_effects") {
      return (
        <>
          {getName(event.who)} {action}
          {event.effects?.map((effect: string, i: number) => (
            <span key={i}>
              {getEffectData(effect)}{" "}
              {i !== 0 || (i !== (event.effects?.length ?? 0) - 1 && ", ")}
            </span>
          ))}
        </>
      );
    }

    if (event.event === "item_use") {
      return (
        <>
          {getName(event.who)} {action} {event.item_name}
          {event.recovery?.health && (
            <span> и восстанавливает {event.recovery.health} здоровья</span>
          )}
          {event.recovery?.mana && (
            <span>и восстанавливает {event.recovery.mana} маны</span>
          )}
          {event.recovery?.energy && (
            <span>и восстанавливает {event.recovery.energy} энергии</span>
          )}
          {event.recovery?.stamina && (
            <span>и восстанавливает {event.recovery.stamina} выносливости</span>
          )}
        </>
      );
    }

    if (event.event === "damage") {
      const attacker = snapshotData.find(
        (p) => p.participant_id === event.source,
      );
      const critChance = attacker?.attributes?.critical_hit_chance;
      const critDamage = attacker?.attributes?.critical_damage;

      return (
        <>
          {getName(event.source)} {action} {getName(event.target)}
          {bold(
            "Тип урона: ",
            DAMAGE_TYPES_MAP[event.damage_type ?? ""] || event.damage_type,
          )}
          {bold("Базовая атака: ", event.base_attack)}
          {bold("Входящий урон: ", event.entry_amount)}
          {!!event.buff_pct &&
            bold("Бонус от баффов: ", event.buff_pct, false, true)}
          {!!event.after_buffs && bold("После баффов: ", event.after_buffs)}
          {event.dodged ? (
            <>
              <span className="text-white/50">{getName(event.target)}</span>{" "}
              <span className="text-site-red">уклонился. </span>
            </>
          ) : null}
          {event.hit_chance_failed ? (
            <>
              {" "}
              <span className="text-white/50">{getName(event.source)}</span>{" "}
              <span className="text-site-red">промахнулся. </span>
            </>
          ) : (
            <>
              {" "}
              <span className="text-white/50">{getName(event.source)}</span>{" "}
              <span className="text-site-blue">попал.</span>
            </>
          )}
          {event.critical && (
            <>
              {bold("С шансом ", critChance, false, true)}
              {bold(
                "нанесен критический урон (множитель) ",
                critDamage,
                true,
                true,
              )}
            </>
          )}
          {!!event.resist_pct && bold("Сопротивление (%) ", event.resist_pct)}
          {bold("Финальный урон: ", event.final)}
        </>
      );
    }

    if (event.event === "resource_spend") {
      if (event.energy === 0 && event.mana === 0 && event.stamina === 0) {
        return null;
      }

      return (
        <>
          {getName(event.who)} {action}
          {!!event.energy && bold("Энергия: ", event.energy)}
          {!!event.mana && bold("Мана: ", event.mana)}
          {!!event.stamina && bold("Выносливость: ", event.stamina)}
        </>
      );
    }

    return (
      <>
        {getName(event.who) || getName(event.source)} {action}{" "}
        {getName(event.target)}
        {Object.entries(event).map(([key, value]) => {
          if (["event", "who", "source", "target"].includes(key)) return null;
          return bold(
            key,
            typeof value === "object" ? JSON.stringify(value) : value,
          );
        })}
      </>
    );
  };

  const getEffectData = (effectName: string): ReactNode => {
    const isStatMod = effectName.includes("StatModifier");
    const isResist = effectName.includes("Resist");
    const isBuff = effectName.includes("Buff");

    const title = isStatMod
      ? "Модификатор"
      : getDamageLabel(effectName.replace(/^(Resist|Buff): /, ""));

    return (
      <span>
        {isBuff && `Изменение урона (${title})`}
        {isResist && `Изменение защиты (${title})`}
        {isStatMod && `${title}`}
      </span>
    );
  };

  return (
    <div className="w-full flex flex-col gap-[15px] font-medium">
      {/* Battle bar top */}
      <div className="p-5 flex flex-col items-center gap-2.5 gray-bg min-h-[160px]">
        <CountdownTimer startMilliseconds={turn.endsAt} />
        <h3 className="gold-text text-lg font-medium uppercase">{turn.currentCharacterParticipant.characterName}</h3>
        {isOpponentTurn && (
          <p className="text-base uppercase">Ход противника</p>
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
              key={btn.type}
              isClosed={isOpponentTurn}
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
            type={SKILLS_KEYS.item}
            isClosed={isOpponentTurn}
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

      {/* Turn history */}
      <div
        className={`gray-bg overflow-hidden flex flex-col gap-5 px-[30px] py-[35px] uppercase transition-all duration-300 ease-in-out ${
          isAllTurnsOpen ? "max-h-[286px]" : "max-h-[140px]"
        }`}
      >
        <div className="flex justify-between items-center">
          <span>История ходов</span>
          {turns.length > 5 && (
            <button
              onClick={toggleAllTurnsVisibility}
              className="text-white hover:text-site-blue transition-colors duration-200 ease-site"
            >
              {isAllTurnsOpen ? "Скрыть" : "Показать все"}
            </button>
          )}
        </div>
        {turns.length > 0 && (
          <ul
            className={`grid grid-cols-5 gap-x-2.5 gap-y-10 items-center justify-items-center ${
              isAllTurnsOpen ? "overflow-y-auto overflow-x-hidden gold-scrollbar" : ""
            }`}
          >
            {turns.map((turnPair, index) => (
              <li
                key={index}
                className="relative flex w-full justify-start items-start gap-[5px]"
              >
                {turnPair.pair.map((turnEntry, i) => (
                  <div
                    key={i}
                    className={`
                      flex items-center justify-center text-sm font-medium relative
                      w-[30px] h-[30px] rounded-full
                      ${turnEntry.waiting
                        ? "bg-white/40 cursor-default"
                        : turnEntry.my
                          ? "bg-white text-site-blue cursor-pointer"
                          : "bg-site-blue cursor-pointer"
                      }
                      ${turnEntry.turnIndex === activeTurnIndex
                        ? "gold-outline gold-outline-thick"
                        : ""
                      }
                    `}
                    onClick={() => {
                      if (!turnEntry.waiting) {
                        setActiveTurnIndex(turnEntry.turnIndex);
                      }
                    }}
                  >
                    {turnEntry.turnIndex + 1}
                  </div>
                ))}
              </li>
            ))}
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

              if (currentParticipantId === myData.participant_id) {
                return myData.name;
              } else if (currentParticipantId === opponentData?.participant_id) {
                return opponentData.name;
              }
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
        Передать ход
      </button>
    </div>
  );
};

export default BattlePageBar;
