import s from "./ItemSkillCircle.module.scss";
import ClosedItemSkillIcon from "../../../../../assets/Icons/ClosedItemSkillIcon.jsx";
import SkillIcon from "../../../../../assets/Icons/SkillIcon.jsx";
import ItemIcon from "../../../../../assets/Icons/ItemIcon.jsx";
import Tooltip from "../../../../CommonComponents/Tooltip/Tooltip.jsx";
import { translateSkillSign } from "../../../../../helpers/helpers.js";
import InventoryItem from "../../CharacterSide/CharacterInventory/InventoryItem/InventoryItem.jsx";
import { SKILLS_KEYS } from "../../../../../helpers/commonConstants.js";

const ItemSkillCircle = ({ isClosed, type, onDropItem, choosedItem }) => {
  const typeIcon = type === SKILLS_KEYS.item ? <ItemIcon /> : <SkillIcon />;

  const handleDrop = (e) => {
    e.preventDefault();
    const data = e.dataTransfer.getData("application/json");
    try {
      const item = JSON.parse(data);
      console.log(item);
      console.log(type);
      if (item.skill_type === type) {
        onDropItem(item);
      }
    } catch {
      console.warn("Invalid item data dropped");
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      className={`${s.circle} ${choosedItem ? s.dropped : ""} ${isClosed ? s.closed : ""}`}
    >
      {isClosed ? (
        <ClosedItemSkillIcon />
      ) : choosedItem ? (
        <InventoryItem isDraggable={false} item={choosedItem} />
      ) : (
        <>
          {typeIcon}
          <Tooltip className={s.tooltip} name={translateSkillSign(type)} />
        </>
      )}
    </div>
  );
};

export default ItemSkillCircle;
