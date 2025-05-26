import s from "./EffectCircle.module.scss";
import TooltipPortal from "../../../../CommonComponents/TooltipPortal/TooltipPortal.jsx";
import { useRef, useState } from "react";
import { getDamageLabel } from "../CharacterInventory/InventoryItem/InventoryItem.jsx";
import { STAT_MODIFIERS } from "../../../../AdminSkillsPage/skillConstants.js";

const EffectCircle = ({ effect }) => {
  const itemRef = useRef();
  const [isHovered, setIsHovered] = useState(false);

  const name = effect?.name || "";
  const isStatMod = name.includes("StatModifier");
  const isResist = name.includes("Resist");
  const isBuff = name.includes("Buff");

  const type = isStatMod ? "mod" : isResist ? "res" : "buff";
  const iconSrc = `/${type}-icon-eff.png`;

  const title = isStatMod
    ? "Модификатор"
    : getDamageLabel(name.replace(/^(Resist|Buff): /, ""));

  const description = isResist
    ? "Изменение защиты"
    : isBuff
      ? "Изменение урона"
      : isStatMod
        ? STAT_MODIFIERS.find(
            (mod) => mod.key === effect?.attribute,
          )?.label.replace("(%)", "")
        : name;

  // useEffect(() => {
  //   if (isHovered) {
  //     console.log(effect);
  //   }
  // }, [isHovered]);

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
            <h4>{description}</h4>
            <span className={s.gray}>({title})</span>
            <ul>
              <li>
                Длительность (в ходах):{" "}
                <span className={s.blue}>{effect.duration}</span>
              </li>
              <li>
                Размер:{" "}
                <span className={effect.magnitude < 0 ? s.red : s.blue}>
                  {effect.magnitude}%
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
