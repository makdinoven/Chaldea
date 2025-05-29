import s from "./BattlePageBar.module.scss";
import CountdownTimer from "./CountdownTimer/CountdownTimer.jsx";
import ItemSkillCircle from "./ItemSkillCircle/ItemSkillCircle.jsx";
import { useEffect, useState } from "react";
import AutobattleModeIcon from "../../../../assets/Icons/AutobattleModeIcon.jsx";
import Tooltip from "../../../CommonComponents/Tooltip/Tooltip.jsx";
import {
  BATTLE_EVENTS_TRANSLATE,
  SKILLS_KEYS,
} from "../../../../helpers/commonConstants.js";
import axios from "axios";
import { BASE_URL_BATTLES } from "../../../../api/api.js";
import { formatDateTime } from "../../../../helpers/helpers.js";
import { DAMAGE_TYPES } from "../../../AdminSkillsPage/skillConstants.js";
import { getDamageLabel } from "../CharacterSide/CharacterInventory/InventoryItem/InventoryItem.jsx";

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
}) => {
  const [isTurnLikeTextShown, setIsTurnLikeTextShown] = useState(true);
  const [isAllTurnsOpen, setIsAllTurnsOpen] = useState(false);
  const [turnLogs, setTurnLogs] = useState(null);
  const [turns, setTurns] = useState([]);
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
    const generatedTurns = [];

    for (let i = 0; i < total_turns; i += 2) {
      let first;
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

      let second;
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

  const getTurnLogs = async (turnNumber) => {
    try {
      const { data } = await axios.get(
        `${BASE_URL_BATTLES}/battles/battles/${Number(battleId)}/logs/${turnNumber}`,
      );
      setTurnLogs(data);
    } catch (e) {
      console.error(e);
    }
  };

  const DAMAGE_TYPES_MAP = Object.fromEntries(
    DAMAGE_TYPES.map(({ value, label }) => [value, label]),
  );

  const formatBattleEvent = (event, snapshotData, s) => {
    const getName = (id) => {
      const name = snapshotData.find((p) => p.participant_id === id)?.name;
      return name ? <span className={s.gold}>{name}</span> : null;
    };

    const formatValue = (value) => {
      if (typeof value === "number" || typeof value === "boolean") {
        return <span className={s.blue}>{String(value)}</span>;
      }
      return <span className={s.white}>{String(value)}</span>;
    };

    const bold = (label, value, isPercent, percentSign) =>
      value !== undefined ? (
        <div className={s.row}>
          {" "}
          <span className={s.gray}>{label ? label : ""}</span>
          <span className={`${value === 0 ? s.red : ""}`}>
            {isPercent ? formatValue(value / 100) : formatValue(value)}
            {percentSign ? <span className={s.blue}>%</span> : ""}
          </span>
        </div>
      ) : null;

    const action = BATTLE_EVENTS_TRANSLATE[event.event] || event.event;

    if (event.event === "apply_effects") {
      return (
        <>
          {getName(event.who)} {action}
          {/*{bold("Тип: ", BATTLE_EFFECTS[event.kind] || event.kind)}*/}
          {/*{bold("", event.effects?.join(", "))}*/}
          {event.effects.map((effect, i) => (
            <span key={i}>
              {getEffectData(effect)}{" "}
              {i !== 0 || (i !== event.effects.length - 1 && ", ")}
            </span>
          ))}
        </>
      );
    }

    if (event.event === "item_use") {
      return (
        <>
          {getName(event.who)} {action} {event.item_name}
          {event.recovery.health && (
            <span> и восстанавливает {event.recovery.health} здоровья</span>
          )}
          {event.recovery.mana && (
            <span>и восстанавливает {event.recovery.mana} маны</span>
          )}
          {event.recovery.energy && (
            <span>и восстанавливает {event.recovery.energy} энергии</span>
          )}
          {event.recovery.stamina && (
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
            DAMAGE_TYPES_MAP[event.damage_type] || event.damage_type,
          )}
          {bold("Базовая атака: ", event.base_attack)}
          {bold("Входящий урон: ", event.entry_amount)}
          {!!event.buff_pct &&
            bold("Бонус от баффов: ", event.buff_pct, false, true)}
          {!!event.after_buffs && bold("После баффов: ", event.after_buffs)}
          {event.dodged ? (
            <>
              <span className={s.gray}>{getName(event.target)}</span>{" "}
              <span className={s.red}>уклонился. </span>
            </>
          ) : null}
          {event.hit_chance_failed ? (
            <>
              {" "}
              <span className={s.gray}>{getName(event.source)}</span>{" "}
              <span className={s.red}>промахнулся. </span>
            </>
          ) : (
            <>
              {" "}
              <span className={s.gray}>{getName(event.source)}</span>{" "}
              <span className={s.blue}>попал.</span>
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

  const getEffectData = (effectName) => {
    const isStatMod = effectName.includes("StatModifier");
    const isResist = effectName.includes("Resist");
    const isBuff = effectName.includes("Buff");

    const title = isStatMod
      ? "Модификатор"
      : // ? STAT_MODIFIERS.find(
        //     (mod) => mod.key === effect?.attribute,
        //   )?.label.replace("(%)", "") || "Модификатор"
        getDamageLabel(effectName.replace(/^(Resist|Buff): /, ""));

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
              onDropItem={(data) => {
                setTurnData((prev) => ({
                  ...prev,
                  [SKILLS_KEYS[btn.type]]: data,
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
            onDropItem={(data) => {
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
          {AUTOBATTLE_MODE_BTNS.map((btn, index) => (
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
                {turnPair.pair.map((turn, i) => (
                  <div
                    key={i}
                    className={`
              ${s.turn_circle}
              ${turn.waiting ? s.waiting : turn.my ? s.my : s.opponent}
              ${turn.turnIndex === activeTurnIndex ? s.active : ""}
            `}
                    onClick={() => {
                      if (!turn.waiting) {
                        setActiveTurnIndex(turn.turnIndex);
                      }
                    }}
                    style={{ cursor: turn.waiting ? "default" : "pointer" }}
                  >
                    {turn.turnIndex + 1}
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
                  (activeTurnIndex + 1) % runtimeData.turn_order.length
                ];

              if (currentParticipantId === myData.participant_id) {
                return myData.name;
              } else if (currentParticipantId === opponentData.participant_id) {
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
                          (activeTurnIndex + 1) % runtimeData.turn_order.length
                        ];

                      if (currentParticipantId === myData.participant_id) {
                        return <p>АВТОБОЙ</p>;
                      } else if (
                        currentParticipantId === opponentData.participant_id
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
                        (activeTurnIndex + 1) % runtimeData.turn_order.length
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
                      currentParticipantId === opponentData.participant_id
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
