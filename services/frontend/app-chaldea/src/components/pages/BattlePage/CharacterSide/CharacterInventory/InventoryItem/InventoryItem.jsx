import s from "./InventoryItem.module.scss";
import TooltipPortal from "../../../../../CommonComponents/TooltipPortal/TooltipPortal";
import { useCallback, useRef, useState } from "react";
import { SKILLS_KEYS } from "../../../../../../helpers/commonConstants";
import { translateSkillSign } from "../../../../../../helpers/helpers";
import {
  DAMAGE_TYPES,
  STAT_MODIFIERS,
} from "../../../../../AdminSkillsPage/skillConstants";

export const getDamageLabel = (value) =>
  DAMAGE_TYPES.find((el) => el.value === value)?.label || value;

const InventoryItem = ({
  type,
  item,
  isCooldown,
  cooldownValue,
  isDraggable,
  setTurnData,
}) => {
  const itemRef = useRef(null);
  const [isHovered, setIsHovered] = useState(false);
  const [tooltipOpenedManually, setTooltipOpenedManually] = useState(false);

  const showTooltip = isHovered || tooltipOpenedManually;

  const handleContextMenu = useCallback((e) => {
    e.preventDefault();
    setTooltipOpenedManually(true);
  }, []);

  const handleMouseLeave = () => {
    setIsHovered(false);
    // если открыто вручную — не закрываем
  };

  const handleCloseManualTooltip = () => {
    setTooltipOpenedManually(false);
  };

  const renderEntries = (entries, isEffect = false) => (
    <ul className={s.inner_list}>
      {entries.map((entry, index) => (
        <li key={index}>
          <div>
            {isEffect ? "Тип эффекта" : "Тип урона"}:{" "}
            <span>
              {entry?.effect_name?.includes("StatModifier")
                ? "Модификатор"
                : getDamageLabel(
                    isEffect
                      ? entry?.effect_name?.includes("Resist")
                        ? entry?.effect_name?.replace("Resist: ", "")
                        : entry?.effect_name?.replace("Buff: ", "")
                      : entry.damage_type,
                  )}
            </span>
            {isEffect && (
              <span className={s.gray}>
                {" "}
                (
                {entry?.effect_name?.includes("Resist")
                  ? "Изменение защиты"
                  : entry?.effect_name?.includes("Buff")
                    ? "Изменение урона"
                    : entry?.effect_name?.includes("StatModifier")
                      ? STAT_MODIFIERS.find(
                          (mod) => mod.key === entry?.attribute_key,
                        )?.label.replace("(%)", "")
                      : entry?.effect_name}
                )
              </span>
            )}
          </div>
          {!isEffect && <div>Урон: {entry.amount}</div>}
          <div>Шанс: {entry.chance}%</div>
          {entry.magnitude && (
            <div>
              Размер:{" "}
              <span className={`${entry.magnitude > 0 ? s.blue : s.red}`}>
                {entry.magnitude}
              </span>
            </div>
          )}
          <div>
            Направление атаки:{" "}
            {entry.target_side === "enemy" ? "Врагу" : "Себе"}
          </div>
          {isEffect && <div>Длительность: {entry.duration}</div>}
        </li>
      ))}
    </ul>
  );

  const handleSelectSkill = () => {
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
  };

  // Track mousedown position to distinguish click from drag
  const mouseDownPos = useRef(null);

  return (
    <>
      <div
        ref={itemRef}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={handleMouseLeave}
        onContextMenu={handleContextMenu}
        onMouseDown={(e) => {
          mouseDownPos.current = { x: e.clientX, y: e.clientY };
        }}
        onMouseUp={(e) => {
          // Only fire click if mouse didn't move much (not a drag)
          if (mouseDownPos.current) {
            const dx = Math.abs(e.clientX - mouseDownPos.current.x);
            const dy = Math.abs(e.clientY - mouseDownPos.current.y);
            if (dx < 5 && dy < 5) {
              handleSelectSkill();
            }
          }
          mouseDownPos.current = null;
        }}
        draggable={!isCooldown && isDraggable}
        onDragStart={(e) => {
          if (isCooldown) return;
          mouseDownPos.current = null; // Cancel click on drag
          e.dataTransfer.setData("application/json", JSON.stringify(item));
        }}
        className={` ${s.item_wrapper} ${isCooldown ? s.cooldown_item : ""}`}
      >
        <div className={`${s.item} ${isCooldown ? s.cooldown : ""}`}>
          {item.rank_image && <img src={item.rank_image} alt="" />}
          {item.image && <img src={item.image} alt="" />}
        </div>
        {isCooldown && <div className={s.cooldown_status}>{cooldownValue}</div>}
      </div>
      {showTooltip && (
        <TooltipPortal targetRef={itemRef}>
          <div className={s.tooltip_content}>
            <div className={s.tooltip_header}>
              {item.rank_name && <h4>{item.rank_name}</h4>}
              {item.name && <h4>{item.name}</h4>}

              {tooltipOpenedManually && (
                <button
                  onClick={handleCloseManualTooltip}
                  className={s.tooltip_close}
                >
                  ×
                </button>
              )}
            </div>

            <ul className={s.all_list}>
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

              {item?.damage_entries?.length > 0 && (
                <li>
                  Уроны:
                  {renderEntries(item.damage_entries)}
                </li>
              )}

              {item?.effects?.length > 0 && (
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
