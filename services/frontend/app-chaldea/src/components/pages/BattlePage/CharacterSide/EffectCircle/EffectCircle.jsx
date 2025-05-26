import s from "./EffectCircle.module.scss";
import TooltipPortal from "../../../../CommonComponents/TooltipPortal/TooltipPortal.jsx";
import { useRef, useState } from "react";
import { getDamageLabel } from "../CharacterInventory/InventoryItem/InventoryItem.jsx";
import { STAT_MODIFIERS } from "../../../../AdminSkillsPage/skillConstants.js";

const EffectCircle = ({ effects, type }) => {
  const itemRef = useRef();
  const [isHovered, setIsHovered] = useState(false);

  const iconSrc = `/${type === "StatModifier" ? "mod" : type === "Resist" ? "res" : "buff"}-icon-eff.png`;

  const getTitle = (effect) => {
    const name = effect?.name || "";
    if (type === "StatModifier") return "";
    return getDamageLabel(name.replace(/^(Resist|Buff): /, ""));
  };

  const pluralizeTurn = (count) => {
    const mod10 = count % 10;
    const mod100 = count % 100;

    if (mod10 === 1 && mod100 !== 11) {
      return `${count} ход`;
    } else if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) {
      return `${count} хода`;
    } else {
      return `${count} ходов`;
    }
  };

  const getDescription = (effect) => {
    const name = effect?.name || "";
    if (type === "Resist") return "";
    if (type === "Buff") return "Изменение урона";
    if (type === "StatModifier")
      return (
        STAT_MODIFIERS.find(
          (mod) => mod.key === effect?.attribute,
        )?.label.replace("(%)", "") || "Модификатор"
      );
    return name;
  };

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      ref={itemRef}
      className={s.circle_wrapper}
    >
      <span
        style={{ backgroundImage: `url(${iconSrc})` }}
        className={s.effect_circle}
      ></span>

      {isHovered && (
        <TooltipPortal targetRef={itemRef}>
          <div className={s.tooltip_content}>
            <h4>
              {type === "Resist"
                ? "Эффекты защиты"
                : type === "Buff"
                  ? "Эффекты урона"
                  : "Модификаторы характеристик"}
            </h4>
            <ul>
              {effects.map((effect, i) => (
                <li key={i}>
                  <strong>{getDescription(effect)}</strong>
                  <span className={s.gray}>{getTitle(effect)}</span>:{" "}
                  <span className={s.blue}>
                    {pluralizeTurn(effect.duration)}
                  </span>
                  ,{" "}
                  <span className={effect.magnitude < 0 ? s.red : s.blue}>
                    {effect.magnitude}%
                    {type === "Resist" && (
                      <>
                        {" "}
                        ({effect.magnitude < 0 ? "уязвимость" : "доп. защита"})
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </TooltipPortal>
      )}
    </div>
  );
};

export default EffectCircle;
