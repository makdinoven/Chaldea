import TooltipPortal from "../../../../CommonComponents/TooltipPortal/TooltipPortal";
import { useRef, useState } from "react";
import { describeEffect, type EffectLike } from "../../battleEffects";

type EffectType = "StatModifier" | "Resist" | "Buff";

interface EffectCircleProps {
  effects: EffectLike[];
  type: EffectType;
}

const ICON_BY_TYPE: Record<EffectType, string> = {
  StatModifier: "/mod-icon-eff.png",
  Resist: "/res-icon-eff.png",
  Buff: "/buff-icon-eff.png",
};

const HEADER_BY_TYPE: Record<EffectType, string> = {
  StatModifier: "Модификаторы характеристик",
  Resist: "Эффекты защиты",
  Buff: "Эффекты урона",
};

const EffectCircle = ({ effects, type }: EffectCircleProps) => {
  const itemRef = useRef<HTMLDivElement>(null);
  const [isHovered, setIsHovered] = useState(false);

  // A "Buff" bucket may also hold complex effects (bleeding, stun, …); keep the
  // header neutral in that case so it never mislabels them as damage buffs.
  const hasComplexOnly =
    type === "Buff" && effects.every((e) => !/^buff\s*:/i.test(e.name ?? ""));
  const header = hasComplexOnly ? "Активные эффекты" : HEADER_BY_TYPE[type];

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      ref={itemRef}
      className="relative -mt-2.5 first:mt-0"
    >
      <span
        style={{ backgroundImage: `url(${ICON_BY_TYPE[type]})` }}
        className="relative z-40 flex w-[33px] h-[33px] rounded-full cursor-pointer bg-gold bg-cover bg-center bg-no-repeat"
      />

      {isHovered && (
        <TooltipPortal targetRef={itemRef}>
          <div className="flex flex-col items-center gap-2.5">
            <h4 className="gold-text text-base font-medium">{header}</h4>
            <ul className="flex flex-col gap-1 text-sm">
              {effects.map((effect, i) => {
                const d = describeEffect(effect);
                return (
                  <li key={i} className="flex flex-wrap items-center gap-x-1.5">
                    <strong className="font-medium text-white">
                      {d.label}
                    </strong>
                    {d.detail && (
                      <span className={d.positive ? "text-site-blue" : "text-site-red"}>
                        {d.detail}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </TooltipPortal>
      )}
    </div>
  );
};

export default EffectCircle;
