import CountdownTimer from "./CountdownTimer/CountdownTimer";
import ItemSkillCircle from "./ItemSkillCircle/ItemSkillCircle";
import AutobattleModeIcon from "../../../../assets/IconComponents/AutobattleModeIcon";
import Tooltip from "../../../CommonComponents/Tooltip/Tooltip";
import { SKILLS_KEYS } from "../../../../helpers/commonConstants";
import AvatarCircle from "./AvatarCircle";
import {
  useBattleBar,
  type BattlePageBarProps,
  type SkillSlot,
  type SlotType,
} from "./useBattleBar";

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

const SKILLS_BTNS: { type: SlotType }[] = [
  { type: SKILLS_KEYS.attack as SlotType },
  { type: SKILLS_KEYS.defense as SlotType },
  { type: SKILLS_KEYS.support as SlotType },
];

// --- Autobattle mode SVG stroke color mapping ---
const MODE_STROKE_COLORS: Record<string, string> = {
  attack: "#f37753",
  defence: "#76a6bd",
};

// --- Component ---

const BattlePageBar = (props: BattlePageBarProps) => {
  const {
    turn,
    setTurn,
    isAutoBattleOn,
    toggleAutobattle,
    autobattleMode,
    setAutobattleMode,
    turnData,
    runtimeData,
  } = props;
  const bar = useBattleBar(props);
  const {
    isOpponentTurn,
    controlled,
    turnQueue,
    participantById,
    sideOf,
    totalTurns,
    activeTurnIndex,
  } = bar;

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
              onDropItem={(data: SkillSlot) => bar.setSlot(btn.type, data)}
              onClear={() => bar.clearSlot(btn.type)}
              onOpen={() => bar.setPickerType(btn.type)}
              key={btn.type}
              isClosed={bar.isSlotLocked(btn.type)}
              type={btn.type}
            />
          ))}
          {/* Vertical gradient line separator */}
          <span className="w-px h-full bg-gradient-to-b from-transparent via-white/60 to-transparent" />
          <ItemSkillCircle
            choosedItem={turnData[SKILLS_KEYS.item]}
            onDropItem={(data: SkillSlot) => bar.setSlot("item", data)}
            onClear={() => bar.clearSlot("item")}
            onOpen={() => bar.setPickerType("item")}
            type={SKILLS_KEYS.item}
            isClosed={bar.isSlotLocked("item")}
          />
          {!isOpponentTurn && bar.hasAnySlot && (
            <button
              onClick={bar.clearAllSlots}
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
            onClick={bar.handleSpeedToggle}
            disabled={bar.speedLoading}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-card text-sm font-medium
              transition-all duration-200 ease-site
              ${bar.autobattleSpeed === "slow"
                ? "bg-site-blue/20 text-site-blue border border-site-blue/40"
                : "bg-white/10 text-white border border-white/20 hover:border-white/40"
              }
              ${bar.speedLoading ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:bg-white/15"}
            `}
            title={bar.autobattleSpeed === "fast" ? "Переключить на медленный режим" : "Переключить на быстрый режим"}
          >
            <span className="text-base leading-none">{bar.autobattleSpeed === "fast" ? "\u{1F407}" : "\u{1F422}"}</span>
            <span className="hidden sm:inline">
              {bar.autobattleSpeed === "fast" ? "Быстрый" : "Медленный"}
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
          bar.isAllTurnsOpen ? "max-h-[320px]" : "max-h-[150px]"
        }`}
      >
        <div className="flex justify-between items-center uppercase">
          <span>История ходов</span>
          <div className="flex items-center gap-3 normal-case">
            {bar.showJumpToLatest && (
              <button
                onClick={bar.jumpToLatest}
                className="text-site-blue hover:text-gold transition-colors duration-200 ease-site"
              >
                К последнему
              </button>
            )}
            {totalTurns > 10 && (
              <button
                onClick={bar.toggleAllTurnsVisibility}
                className="uppercase text-white hover:text-site-blue transition-colors duration-200 ease-site"
              >
                {bar.isAllTurnsOpen ? "Скрыть" : "Показать все"}
              </button>
            )}
          </div>
        </div>
        {totalTurns > 0 && (
          <ul
            className={`flex flex-wrap gap-x-3 gap-y-4 items-center pr-1 ${
              bar.isAllTurnsOpen ? "overflow-y-auto overflow-x-hidden gold-scrollbar" : ""
            }`}
          >
            {Array.from({ length: totalTurns }, (_, idx) => {
              const actorPid = bar.actorOfTurn(idx);
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
                    onClick={() => bar.selectTurn(idx)}
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
          <span className="gold-text text-base">{bar.activeTurnActorName}</span>
        </div>

        {bar.turnLogs && (
          <ul className="flex-1 flex flex-col gap-2.5 overflow-y-auto overflow-x-hidden pr-2.5 gold-scrollbar">
            {bar.turnLogs.logs.map((log, index) => (
              <li
                key={index}
                className="w-full gap-[5px] flex flex-col justify-between items-end text-xs normal-case"
              >
                {log.events.map((event, i) => (
                  <div key={i} className="w-full text-left">
                    {bar.formatBattleEvent(event)}
                  </div>
                ))}
                <div className="mt-2.5 w-full flex justify-between">
                  {bar.isOwnAutobattleTurn && (
                    <p className="gold-text text-sm">АВТОБОЙ</p>
                  )}
                  <div className="ml-auto">{bar.formatLogTime(log.timestamp)}</div>
                </div>
                {bar.isTurnLikeTextShown && bar.isOwnAutobattleTurn && (
                  <div className="text-sm">
                    Понравился ли вам ход?{" "}
                    <span
                      onClick={() => bar.rateTurn(log, true)}
                      className="cursor-pointer font-medium text-site-blue underline decoration-[1.5px]"
                    >
                      Да
                    </span>{" "}
                    <span
                      onClick={() => bar.rateTurn(log, false)}
                      className="cursor-pointer font-medium text-site-red underline decoration-[1.5px]"
                    >
                      Нет
                    </span>
                  </div>
                )}
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
      {bar.renderPicker()}
    </div>
  );
};

export default BattlePageBar;
