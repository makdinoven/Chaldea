import s from "./BattlePageBar.module.scss";
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
import { BASE_URL_BATTLES } from "../../../../api/api";
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
}: BattlePageBarProps) => {
  const [isTurnLikeTextShown, setIsTurnLikeTextShown] = useState(true);
  const [isAllTurnsOpen, setIsAllTurnsOpen] = useState(false);
  const [turnLogs, setTurnLogs] = useState<TurnLogsResponse | null>(null);
  const [turns, setTurns] = useState<TurnPair[]>([]);
  const isOpponentTurn = turn.isOpponentTurn;
  const [activeTurnIndex, setActiveTurnIndex] = useState(
    runtimeData.turn_number - 1,
  );

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
    styles: Record<string, string>,
  ): ReactNode => {
    const getName = (id: number | undefined): ReactNode => {
      if (id === undefined) return null;
      const name = snapshotData.find((p) => p.participant_id === id)?.name;
      return name ? <span className={styles.gold}>{name}</span> : null;
    };

    const formatValue = (value: unknown): ReactNode => {
      if (typeof value === "number" || typeof value === "boolean") {
        return <span className={styles.blue}>{String(value)}</span>;
      }
      return <span className={styles.white}>{String(value)}</span>;
    };

    const bold = (
      label: string,
      value: unknown,
      isPercent?: boolean,
      percentSign?: boolean,
    ): ReactNode =>
      value !== undefined ? (
        <div className={styles.row}>
          {" "}
          <span className={styles.gray}>{label ? label : ""}</span>
          <span className={`${value === 0 ? styles.red : ""}`}>
            {isPercent ? formatValue((value as number) / 100) : formatValue(value)}
            {percentSign ? <span className={styles.blue}>%</span> : ""}
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
              <span className={styles.gray}>{getName(event.target)}</span>{" "}
              <span className={styles.red}>уклонился. </span>
            </>
          ) : null}
          {event.hit_chance_failed ? (
            <>
              {" "}
              <span className={styles.gray}>{getName(event.source)}</span>{" "}
              <span className={styles.red}>промахнулся. </span>
            </>
          ) : (
            <>
              {" "}
              <span className={styles.gray}>{getName(event.source)}</span>{" "}
              <span className={styles.blue}>попал.</span>
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
    <div className={s.container}>
      <div className={s.battle_bar_top}>
        <CountdownTimer startMilliseconds={turn.endsAt} />
        <h3>{turn.currentCharacterParticipant.characterName}</h3>
        {isOpponentTurn && (
          <p className={s.opponent_turn_sign}>Ход противника</p>
        )}
        <div className={s.icons}>
          {SKILLS_BTNS.map((btn) => (
            <ItemSkillCircle
              choosedItem={turnData[btn.type]}
              onDropItem={(data: SkillSlot) => {
                setTurnData((prev) => ({
                  ...prev,
                  [SKILLS_KEYS[btn.type as keyof typeof SKILLS_KEYS]]: data,
                }));
              }}
              key={btn.type}
              isClosed={isOpponentTurn}
              type={btn.type}
            />
          ))}
          <span className={s.line}></span>
          <ItemSkillCircle
            choosedItem={turnData[SKILLS_KEYS.item]}
            onDropItem={(data: SkillSlot) => {
              console.log(data);
              setTurnData((prev) => ({
                ...prev,
                [SKILLS_KEYS.item]: data,
              }));
            }}
            type={SKILLS_KEYS.item}
            isClosed={isOpponentTurn}
          />
        </div>
      </div>

      <div className={s.auto_battle_btns}>
        <div className={s.mode_btns}>
          {AUTOBATTLE_MODE_BTNS.map((btn) => (
            <button
              onClick={() => setAutobattleMode(btn.mode)}
              className={`${s.auto_battle_mode_btn} ${s[btn.mode]} ${autobattleMode === btn.mode ? s.active : ""}`}
              key={btn.mode}
            >
              {btn.icon}
              <Tooltip className={s.tooltip} name={btn.name} />
            </button>
          ))}
        </div>

        <button onClick={toggleAutobattle} className={s.auto_battle_btn}>
          {isAutoBattleOn ? "остановить автобой" : "Включить автобой"}
        </button>
      </div>
      <div
        className={`${s.battle_turns_container} ${isAllTurnsOpen ? s.opened : ""}`}
      >
        <div className={s.battle_turns_container_top}>
          <span>История ходов</span>
          {turns.length > 5 && (
            <button onClick={toggleAllTurnsVisibility}>
              {isAllTurnsOpen ? "Скрыть" : "Показать все"}
            </button>
          )}
        </div>
        {turns.length > 0 && (
          <ul className={s.turns_list}>
            {turns.map((turnPair, index) => (
              <li key={index}>
                {turnPair.pair.map((turnEntry, i) => (
                  <div
                    key={i}
                    className={`
              ${s.turn_circle}
              ${turnEntry.waiting ? s.waiting : turnEntry.my ? s.my : s.opponent}
              ${turnEntry.turnIndex === activeTurnIndex ? s.active : ""}
            `}
                    onClick={() => {
                      if (!turnEntry.waiting) {
                        setActiveTurnIndex(turnEntry.turnIndex);
                      }
                    }}
                    style={{ cursor: turnEntry.waiting ? "default" : "pointer" }}
                  >
                    {turnEntry.turnIndex + 1}
                  </div>
                ))}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className={s.battle_logs_container}>
        <div className={s.battle_logs_top}>
          <span>
            Логи
            {activeTurnIndex + 1 > 0 && (
              <span>: Ход {activeTurnIndex + 1}</span>
            )}
          </span>
          <span className={s.logs_character_name}>
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
          <ul className={s.battle_logs_list}>
            {turnLogs.logs.map((log, index) => (
              <li key={index}>
                {log.events.map((event, i) => (
                  <div key={i} className={s.event}>
                    {formatBattleEvent(event, snapshotData, s)}
                  </div>
                ))}
                <div className={s.date_time_container}>
                  {isAutoBattleOn &&
                    (() => {
                      const currentParticipantId =
                        runtimeData.turn_order[
                          activeTurnIndex % runtimeData.turn_order.length
                        ];

                      if (currentParticipantId === myData.participant_id) {
                        return <p>АВТОБОЙ</p>;
                      } else if (
                        currentParticipantId === opponentData?.participant_id
                      ) {
                        return null;
                      }
                    })()}
                  <div>{formatDateTime(log.timestamp)}</div>
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
                        <div className={s.doYouLike}>
                          Понравился ли вам ход?{" "}
                          <span
                            onClick={() => setIsTurnLikeTextShown(false)}
                            className={s.blue}
                          >
                            Да
                          </span>{" "}
                          <span
                            onClick={() => setIsTurnLikeTextShown(false)}
                            className={s.red}
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

      <button
        disabled={isOpponentTurn}
        onClick={setTurn}
        className={`${s.turn_btn} ${isOpponentTurn ? s.blocked : ""}`}
      >
        Передать ход
      </button>
    </div>
  );
};

export default BattlePageBar;
