import HudFrame from "./HudFrame";
import SlotMedallion from "./SlotMedallion";
import TurnSeal from "./TurnSeal";
import type { BattleBarState, SlotType, TurnDataState } from "../../BattlePageBar/useBattleBar";

const SKILL_SLOTS: SlotType[] = ["attack", "defense", "support"];

const AUTOBATTLE_MODES = [
  { mode: "balance", label: "Баланс", title: "Сбалансированный режим" },
  { mode: "attack", label: "Атака", title: "Атакующий режим" },
  { mode: "defence", label: "Защита", title: "Защитный режим" },
];

interface AutobattleControlsProps {
  bar: BattleBarState;
  isAutoBattleOn: boolean;
  toggleAutobattle: () => void;
  autobattleMode: string;
  setAutobattleMode: (mode: string) => void;
  /** Single tight row for the phone bar. */
  dense?: boolean;
}

export const AutobattleControls = ({
  bar,
  isAutoBattleOn,
  toggleAutobattle,
  autobattleMode,
  setAutobattleMode,
  dense = false,
}: AutobattleControlsProps) => {
  const chip = `chip-outline rounded-full py-1 ${dense ? "px-2 text-[10px]" : "px-2.5 text-[11px]"}`;
  return (
    <div className={`flex items-center ${dense ? "min-w-0 gap-1 overflow-x-auto" : "flex-wrap gap-1.5"}`}>
      <button
        type="button"
        onClick={toggleAutobattle}
        className={`${chip} shrink-0 font-medium uppercase tracking-wide ${isAutoBattleOn ? "chip-outline-active" : ""}`}
      >
        {isAutoBattleOn ? "Автобой: вкл" : "Автобой"}
      </button>
      {AUTOBATTLE_MODES.map((m) => (
        <button
          key={m.mode}
          type="button"
          title={m.title}
          onClick={() => setAutobattleMode(m.mode)}
          className={`${chip} shrink-0 ${autobattleMode === m.mode ? "chip-outline-active" : ""}`}
        >
          {m.label}
        </button>
      ))}
      {isAutoBattleOn && (
        <button
          type="button"
          onClick={bar.handleSpeedToggle}
          disabled={bar.speedLoading}
          title={bar.autobattleSpeed === "fast" ? "Переключить на медленный режим" : "Переключить на быстрый режим"}
          className={`${chip} shrink-0 ${bar.speedLoading ? "opacity-50" : ""}`}
        >
          {bar.autobattleSpeed === "fast" ? "Быстро" : "Медленно"}
        </button>
      )}
    </div>
  );
};

interface ActionBarProps extends AutobattleControlsProps {
  turnData: TurnDataState;
  onPassTurn: () => void;
  /**
   * `column` — desktop panel under the turn banner; `compact` — phone bar with
   * slots and seal only (autobattle moves to the row below).
   */
  layout: "column" | "compact";
}

const ActionBar = ({ bar, turnData, onPassTurn, layout, ...auto }: ActionBarProps) => {
  const medallion = (type: SlotType) => (
    <SlotMedallion
      key={type}
      type={type}
      value={turnData[type] ?? null}
      locked={bar.isSlotLocked(type)}
      onOpen={() => bar.setPickerType(type)}
      onClear={() => bar.clearSlot(type)}
    />
  );

  const slots = (
    <div className="flex items-end gap-2 sm:gap-3">
      {SKILL_SLOTS.map(medallion)}
      <span className="mb-6 h-10 w-px self-center bg-gradient-to-b from-transparent via-gold-dark/60 to-transparent sm:h-14" />
      {medallion("item")}
    </div>
  );

  const seal = (
    <TurnSeal
      disabled={bar.isOpponentTurn}
      armed={bar.hasAnySlot}
      controlled={bar.controlled}
      onClick={onPassTurn}
    />
  );

  if (layout === "compact") {
    return (
      <div className="flex items-center justify-center gap-2">
        {slots}
        {seal}
      </div>
    );
  }

  return (
    <HudFrame className="w-full px-4 py-4">
      <div className="flex flex-col items-center gap-4">
        <div className="grid grid-cols-2 gap-x-5 gap-y-2">
          {SKILL_SLOTS.map(medallion)}
          {medallion("item")}
        </div>
        {seal}
        <div className="h-px w-full bg-gradient-to-r from-transparent via-gold-dark/50 to-transparent" />
        <AutobattleControls bar={bar} {...auto} />
        {!bar.isOpponentTurn && bar.hasAnySlot && (
          <button
            type="button"
            onClick={bar.clearAllSlots}
            className="text-[11px] uppercase tracking-wide text-white/50 transition-colors duration-200 hover:text-site-blue"
          >
            Очистить выбор
          </button>
        )}
      </div>
    </HudFrame>
  );
};

export default ActionBar;
