import type { CSSProperties } from "react";
import SkillIcon from "../../../../../assets/IconComponents/SkillIcon";
import ItemIcon from "../../../../../assets/IconComponents/ItemIcon";
import ClosedItemSkillIcon from "../../../../../assets/IconComponents/ClosedItemSkillIcon";
import InventoryItem from "../../CharacterSide/CharacterInventory/InventoryItem/InventoryItem";
import type { SkillSlot, SlotType } from "../../BattlePageBar/useBattleBar";

export const SLOT_META: Record<SlotType, { label: string; glow: string }> = {
  attack: { label: "Атака", glow: "#f37753" },
  defense: { label: "Защита", glow: "#76a6bd" },
  support: { label: "Поддержка", glow: "#34d399" },
  item: { label: "Предмет", glow: "#f0d95c" },
};

interface SlotMedallionProps {
  type: SlotType;
  value: SkillSlot | null;
  locked: boolean;
  onOpen: () => void;
  onClear: () => void;
}

const SlotMedallion = ({ type, value, locked, onOpen, onClear }: SlotMedallionProps) => {
  const meta = SLOT_META[type];
  const filled = Boolean(value) && !locked;
  const glowStyle = { "--slot-glow": meta.glow } as CSSProperties;

  return (
    <div className="flex flex-col items-center gap-1" style={glowStyle}>
      <div className="relative">
        <button
          type="button"
          disabled={locked}
          onClick={onOpen}
          aria-label={`${meta.label}: выбрать`}
          className={`relative flex h-[54px] w-[54px] items-center justify-center rounded-full transition-all duration-200 ease-site sm:h-[70px] sm:w-[70px]
            bg-[radial-gradient(circle_at_50%_35%,#2c2219_0%,#0c0a08_75%)]
            shadow-[inset_0_0_0_2px_rgba(188,171,76,0.55),inset_0_0_0_5px_rgba(0,0,0,0.6),inset_0_0_0_6px_rgba(240,217,92,0.18),0_4px_12px_rgba(0,0,0,0.6)]
            ${
              locked
                ? "cursor-not-allowed opacity-45 grayscale"
                : "cursor-pointer hover:-translate-y-0.5 hover:shadow-[inset_0_0_0_2px_rgba(240,217,92,0.9),inset_0_0_0_5px_rgba(0,0,0,0.6),inset_0_0_0_6px_rgba(240,217,92,0.25),0_6px_16px_rgba(0,0,0,0.7)]"
            }
            ${filled ? "!shadow-[inset_0_0_0_2px_var(--slot-glow),inset_0_0_0_5px_rgba(0,0,0,0.6),0_0_18px_var(--slot-glow)]" : ""}`}
        >
          {locked ? (
            <span className="[&_svg]:h-6 [&_svg]:w-5 sm:[&_svg]:h-8 sm:[&_svg]:w-6">
              <ClosedItemSkillIcon />
            </span>
          ) : value ? (
            <span className="pointer-events-none scale-[0.82] sm:scale-100 [&>div]:pointer-events-auto">
              <InventoryItem isDraggable={false} item={value} />
            </span>
          ) : (
            <span className="opacity-60 [&_svg]:h-7 [&_svg]:w-6 sm:[&_svg]:h-9 sm:[&_svg]:w-7">
              {type === "item" ? <ItemIcon /> : <SkillIcon />}
            </span>
          )}
        </button>
        {filled && (
          <button
            type="button"
            onClick={onClear}
            aria-label={`${meta.label}: убрать`}
            className="absolute -right-1 -top-1 z-10 flex h-5 w-5 items-center justify-center rounded-full border border-gold-dark/60 bg-site-dark text-[11px] leading-none text-white/70 transition-colors duration-200 hover:text-site-red"
          >
            ×
          </button>
        )}
      </div>
      <span
        className={`text-[9px] uppercase tracking-[0.15em] sm:text-[10px] ${
          filled ? "text-[color:var(--slot-glow)]" : "text-gold-dark/80"
        }`}
      >
        {meta.label}
      </span>
    </div>
  );
};

export default SlotMedallion;
