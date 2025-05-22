import s from "./EffectCircle.module.scss";
import TooltipPortal from "../../../../CommonComponents/TooltipPortal/TooltipPortal.jsx";
import { useEffect, useRef, useState } from "react";
import { getDamageLabel } from "../CharacterInventory/InventoryItem/InventoryItem.jsx";
import { STAT_MODIFIERS } from "../../../../AdminSkillsPage/skillConstants.js";

const EffectCircle = ({ effect }) => {
  const itemRef = useRef();
  const [isHovered, setIsHovered] = useState(false);

  useEffect(() => {
    if (isHovered) {
      console.log(effect);
    }
  }, [isHovered]);

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      ref={itemRef}
      className={s.circle_wrapper}
    >
      <span className={s.effect_circle}>{/*{effect.}*/}</span>
      {isHovered && (
        <TooltipPortal targetRef={itemRef}>
          <div className={s.tooltip_content}>
            <h4>
              {" "}
              {effect?.name?.includes("StatModifier")
                ? "Модификатор характеристик"
                : getDamageLabel(
                    effect?.name?.includes("Resist")
                      ? effect?.name?.replace("Resist: ", "")
                      : effect?.name?.replace("Buff: ", ""),
                  )}
            </h4>

            <span className={s.gray}>
              {" "}
              (
              {effect?.name?.includes("Resist")
                ? "Изменение защиты"
                : effect?.name?.includes("Buff")
                  ? "Изменение урона"
                  : effect?.name?.includes("StatModifier")
                    ? STAT_MODIFIERS.find(
                        (mod) => mod.key === effect?.attribute_key,
                      )?.label
                    : effect?.name}
              )
            </span>
            <ul>
              <li>
                Длительность: <span className={s.blue}>{effect.duration}</span>
              </li>
              <li>
                Размер:{" "}
                <span className={`${effect.magnitude < 0 ? s.red : s.blue}`}>
                  {" "}
                  {effect.magnitude}
                </span>
              </li>
            </ul>
          </div>
        </TooltipPortal>
      )}
    </div>
  );
};

export default EffectCircle;
