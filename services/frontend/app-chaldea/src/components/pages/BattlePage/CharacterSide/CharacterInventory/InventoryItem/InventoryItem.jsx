import s from "./InventoryItem.module.scss";
import TooltipPortal from "../../../../../CommonComponents/TooltipPortal/TooltipPortal.jsx";
import { useRef, useState } from "react";
import { SKILLS_KEYS } from "../../../../../../helpers/commonConstants.js";
import { translateSkillSign } from "../../../../../../helpers/helpers.js";
import {
  DAMAGE_TYPES,
  STAT_MODIFIERS,
} from "../../../../../AdminSkillsPage/skillConstants.js";

export const getDamageLabel = (value) =>
  DAMAGE_TYPES.find((el) => el.value === value)?.label || value;

const InventoryItem = ({
  item,
  isCooldown,
  cooldownValue,
  isDraggable,
  setTurnData,
}) => {
  const itemRef = useRef(null);
  const [isHovered, setIsHovered] = useState(false);

  const renderEntries = (entries, isEffect = false) => (
    <ul className={s.inner_list}>
      {entries.map((entry, index) => (
        <li key={index}>
          <div>
            {isEffect ? "Тип эффекта" : "Тип урона"}:{" "}
            <span>
              {entry?.effect_name?.includes("StatModifier")
                ? "Модификатор характеристик"
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
                        )?.label
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

  return (
    <>
      <div
        ref={itemRef}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={(e) => {
          if (isDraggable && isCooldown) {
            e.preventDefault();
            e.stopPropagation();
            return;
          }
          setTurnData((prev) => ({
            ...prev,
            [SKILLS_KEYS[item.skill_type]]: item,
          }));
        }}
        draggable={!isCooldown && isDraggable}
        onDragStart={(e) => {
          if (isCooldown) return;
          e.dataTransfer.setData("application/json", JSON.stringify(item));
        }}
        className={` ${s.item_wrapper} ${isCooldown ? s.cooldown_item : ""}`}
      >
        <div className={`${s.item} ${isCooldown ? s.cooldown : ""}`}>
          <img src={item.rank_image} alt="" />
        </div>
        {isCooldown && <div className={s.cooldown_status}>{cooldownValue}</div>}
      </div>
      {isHovered && (
        <TooltipPortal targetRef={itemRef}>
          <div className={s.tooltip_content}>
            <h4>{item.rank_name}</h4>
            <ul className={s.all_list}>
              <li>Тип: {translateSkillSign(item.skill_type)}</li>
              <li>Перезарядка: {item.cooldown}</li>
              <li>Затрата энергии: {item.cost_energy}</li>
              <li>Затрата маны: {item.cost_mana}</li>

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
