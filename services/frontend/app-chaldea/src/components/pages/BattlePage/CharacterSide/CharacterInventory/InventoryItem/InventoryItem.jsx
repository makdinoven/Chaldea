import s from "./InventoryItem.module.scss";
import TooltipPortal from "../../../../../CommonComponents/TooltipPortal/TooltipPortal.jsx";
import { useRef, useState } from "react";
import { SKILLS_KEYS } from "../../../../../../helpers/commonConstants.js";

const InventoryItem = ({ item, isCooldown, isDraggable, setTurnData }) => {
  const itemRef = useRef(null);
  const [isHovered, setIsHovered] = useState(false);

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
        {isCooldown && (
          <div className={s.cooldown_status}>{item.cooldown_count}</div>
        )}
      </div>
      {isHovered && <TooltipPortal targetRef={itemRef} data={item} />}
    </>
  );
};

export default InventoryItem;
