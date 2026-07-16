import TooltipPortal from "../../../../../CommonComponents/TooltipPortal/TooltipPortal";
import {
  Dispatch,
  RefObject,
  SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { SKILLS_KEYS } from "../../../../../../helpers/commonConstants";
import { translateSkillSign } from "../../../../../../helpers/helpers";
import {
  DAMAGE_TYPES,
  STAT_MODIFIERS,
} from "../../../../../AdminSkillsPage/skillConstants";

interface DamageEntry {
  damage_type?: string;
  amount?: number;
  chance?: number;
  target_side?: string;
  [key: string]: unknown;
}

interface EffectEntry {
  effect_name?: string;
  attribute_key?: string;
  chance?: number;
  magnitude?: number;
  duration?: number;
  target_side?: string;
  [key: string]: unknown;
}

interface InventoryItemData {
  id?: number;
  item_id?: number;
  skill_type?: string;
  skill_name?: string;
  skill_image?: string;
  name?: string;
  image?: string;
  skill?: {
    id: number;
    name: string;
    skill_type: string;
    skill_image: string | null;
  };
  cooldown?: number;
  cost_energy?: number;
  cost_mana?: number;
  health_recovery?: number;
  mana_recovery?: number;
  stamina_recovery?: number;
  energy_recovery?: number;
  damage_entries?: DamageEntry[];
  effects?: EffectEntry[];
  slot_type?: string;
  [key: string]: unknown;
}

interface InventoryItemProps {
  type?: string;
  item: InventoryItemData;
  /* Optional: ItemSkillCircle renders a static preview without cooldown/turn wiring. */
  isCooldown?: boolean;
  cooldownValue?: number;
  isDraggable: boolean;
  setTurnData?: Dispatch<SetStateAction<Record<string, unknown>>> | null;
}

export const getDamageLabel = (value: string | undefined) =>
  DAMAGE_TYPES.find((el: { value: string; label: string }) => el.value === value)?.label || value;

const InventoryItem = ({
  item,
  isCooldown,
  cooldownValue,
  isDraggable,
  setTurnData,
}: InventoryItemProps) => {
  const itemRef = useRef<HTMLDivElement>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [tooltipOpenedManually, setTooltipOpenedManually] = useState(false);

  const showTooltip = isHovered || tooltipOpenedManually;

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setTooltipOpenedManually(true);
  }, []);

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  const handleCloseManualTooltip = () => {
    setTooltipOpenedManually(false);
  };

  const itemIcon = item.skill_image || item.image || null;
  const itemName = item.skill_name || item.skill?.name || item.name || null;

  const renderEntries = (entries: (DamageEntry | EffectEntry)[], isEffect = false) => (
    <ul className="flex flex-col gap-[5px]">
      {entries.map((entry, index) => {
        const effectEntry = entry as EffectEntry;
        const damageEntry = entry as DamageEntry;
        return (
          <li
            key={index}
            className="flex flex-col gap-px relative [&:not(:last-child)]:after:content-[''] [&:not(:last-child)]:after:absolute [&:not(:last-child)]:after:bottom-[-3px] [&:not(:last-child)]:after:left-0 [&:not(:last-child)]:after:right-0 [&:not(:last-child)]:after:h-px [&:not(:last-child)]:after:bg-gradient-to-r [&:not(:last-child)]:after:from-transparent [&:not(:last-child)]:after:via-[#999] [&:not(:last-child)]:after:to-transparent"
          >
            <div>
              {isEffect ? "Тип эффекта" : "Тип урона"}:{" "}
              <span className="text-[#76A6BD]">
                {effectEntry?.effect_name?.includes("StatModifier")
                  ? "Модификатор"
                  : getDamageLabel(
                      isEffect
                        ? effectEntry?.effect_name?.includes("Resist")
                          ? effectEntry?.effect_name?.replace("Resist: ", "")
                          : effectEntry?.effect_name?.replace("Buff: ", "")
                        : damageEntry.damage_type,
                    )}
              </span>
              {isEffect && (
                <span className="text-gray-400">
                  {" "}
                  (
                  {effectEntry?.effect_name?.includes("Resist")
                    ? "Изменение защиты"
                    : effectEntry?.effect_name?.includes("Buff")
                      ? "Изменение урона"
                      : effectEntry?.effect_name?.includes("StatModifier")
                        ? STAT_MODIFIERS.find(
                            (mod: { key: string; label: string }) => mod.key === effectEntry?.attribute_key,
                          )?.label.replace("(%)", "")
                        : effectEntry?.effect_name}
                  )
                </span>
              )}
            </div>
            {!isEffect && <div>Урон: {damageEntry.amount}</div>}
            <div>Шанс: {(entry as EffectEntry).chance}%</div>
            {effectEntry.magnitude && (
              <div>
                Размер:{" "}
                <span className={effectEntry.magnitude > 0 ? "text-[var(--blue)]" : "text-[var(--red)]"}>
                  {effectEntry.magnitude}
                </span>
              </div>
            )}
            <div>
              Направление атаки:{" "}
              {(entry as DamageEntry).target_side === "enemy" ? "Врагу" : "Себе"}
            </div>
            {isEffect && <div>Длительность: {effectEntry.duration}</div>}
          </li>
        );
      })}
    </ul>
  );

  const handleSelectSkill = useCallback(() => {
    if (isDraggable && isCooldown) return;
    if (!setTurnData) return;
    setTurnData((prev) => {
      if (item.skill_type) {
        return {
          ...prev,
          [SKILLS_KEYS[item.skill_type]]: item,
        };
      } else {
        return {
          ...prev,
          [SKILLS_KEYS.item]: item,
        };
      }
    });
  }, [isDraggable, isCooldown, setTurnData, item]);

  useEffect(() => {
    const el = itemRef.current;
    if (!el || !isDraggable) return;
    const handler = (e: MouseEvent) => {
      e.stopPropagation();
      handleSelectSkill();
    };
    el.addEventListener("click", handler);
    return () => el.removeEventListener("click", handler);
  });

  return (
    <>
      <div
        ref={itemRef}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={handleMouseLeave}
        onContextMenu={handleContextMenu}
        draggable={!isCooldown && isDraggable}
        onDragStart={(e) => {
          if (isCooldown) return;
          e.dataTransfer.setData("application/json", JSON.stringify(item));
        }}
        className={`relative w-[60px] h-[60px] z-5 cursor-pointer ${isCooldown ? "opacity-30" : ""}`}
      >
        <div
          className={`overflow-hidden flex justify-center flex-col items-center text-[10px] cursor-pointer w-full h-full rounded-full bg-gradient-to-b from-transparent to-[#76A6BD] ${isCooldown ? "relative opacity-30" : ""}`}
        >
          {itemIcon && (
            <img src={itemIcon} alt="" draggable={false} className="pointer-events-none" />
          )}
        </div>
        {isCooldown && (
          <div className="flex items-center text-center justify-center font-medium text-xs uppercase absolute w-6 h-7 -top-2.5 -right-3 bg-[url('/src/assets/cooldown-arrows.svg')] bg-no-repeat bg-center bg-cover">
            {cooldownValue}
          </div>
        )}
      </div>
      {showTooltip && (
        <TooltipPortal targetRef={itemRef as RefObject<HTMLElement>}>
          <div className="flex flex-col items-center gap-2.5">
            <div className="flex items-center gap-[5px]">
              {itemName && <h4 className="gold-text text-base uppercase">{itemName}</h4>}

              {tooltipOpenedManually && (
                <button
                  onClick={handleCloseManualTooltip}
                  className="border-none bg-transparent text-[32px] cursor-pointer text-white z-[200]"
                >
                  ×
                </button>
              )}
            </div>

            <ul className="w-full flex flex-col gap-px [&_span]:text-[#76A6BD] [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-px [&_li]:flex [&_li]:gap-[5px]">
              {item.skill_type && (
                <li>Тип: {translateSkillSign(item.skill_type)}</li>
              )}
              {!!item.cooldown && <li>Перезарядка: {item.cooldown}</li>}
              {!!item.cost_energy && (
                <li>Затрата энергии: {item.cost_energy}</li>
              )}
              {!!item.cost_mana && <li>Затрата маны: {item.cost_mana}</li>}

              {item.health_recovery && (
                <li>Восстановление здоровья: {item.health_recovery}</li>
              )}
              {item.mana_recovery && (
                <li>Восстановление маны: {item.mana_recovery}</li>
              )}
              {item.stamina_recovery && (
                <li>Восстановление выносливости: {item.stamina_recovery}</li>
              )}
              {item.energy_recovery && (
                <li>Восстановление энергии: {item.energy_recovery}</li>
              )}

              {item?.damage_entries && item.damage_entries.length > 0 && (
                <li>
                  Уроны:
                  {renderEntries(item.damage_entries)}
                </li>
              )}

              {item?.effects && item.effects.length > 0 && (
                <li>
                  Эффекты:
                  {renderEntries(item.effects, true)}
                </li>
              )}
            </ul>
          </div>
        </TooltipPortal>
      )}
    </>
  );
};

export default InventoryItem;
