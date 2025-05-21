import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import s from "./TooltipPortal.module.scss";
import { DAMAGE_TYPES } from "../../AdminSkillsPage/skillConstants.js";
import { translateSkillSign } from "../../../helpers/helpers.js";

const getDamageLabel = (value) =>
  DAMAGE_TYPES.find((el) => el.value === value)?.label || value;

const TooltipPortal = ({ targetRef, data }) => {
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const tooltipRef = useRef();

  useEffect(() => {
    const updatePosition = () => {
      if (!targetRef.current) return;
      const rect = targetRef.current.getBoundingClientRect();
      setPosition({
        top: rect.top + window.scrollY + rect.height + 10,
        left: rect.left + window.scrollX + rect.width / 2,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    return () => window.removeEventListener("resize", updatePosition);
  }, [targetRef]);

  const renderEntries = (entries, isEffect = false) => (
    <ul className={s.inner_list}>
      {entries.map((entry, index) => (
        <li key={index}>
          <div>
            {isEffect ? "Тип эффекта" : "Тип урона"}:{" "}
            <span>
              {getDamageLabel(
                isEffect
                  ? entry.effect_name.replace("Buff: ", "")
                  : entry.damage_type,
              )}
            </span>
          </div>
          {!isEffect && <div>Урон: {entry.amount}</div>}
          <div>Шанс: {entry.chance}</div>
          <div>
            Направление атаки:{" "}
            {entry.target_side === "enemy" ? "Врагу" : "Себе"}
          </div>
          {isEffect && <div>Длительность: {entry.duration}</div>}
        </li>
      ))}
    </ul>
  );

  return createPortal(
    <div
      ref={tooltipRef}
      className={s.tooltip}
      style={{ top: `${position.top}px`, left: `${position.left}px` }}
    >
      <div className={s.tooltip_content}>
        <h4>{data.rank_name}</h4>
        <ul className={s.all_list}>
          <li>Тип: {translateSkillSign(data.skill_type)}</li>
          <li>Перезарядка: {data.cooldown}</li>
          <li>Затрата энергии: {data.cost_energy}</li>
          <li>Затрата маны: {data.cost_mana}</li>

          {data?.damage_entries?.length > 0 && (
            <li>
              Уроны:
              {renderEntries(data.damage_entries)}
            </li>
          )}

          {data?.effects?.length > 0 && (
            <li>
              Эффекты:
              {renderEntries(data.effects, true)}
            </li>
          )}
        </ul>
      </div>
    </div>,
    document.body,
  );
};

export default TooltipPortal;
