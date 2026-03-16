import s from "./ItemSkillCircle.module.scss";
import ClosedItemSkillIcon from "../../../../../assets/Icons/ClosedItemSkillIcon";
import SkillIcon from "../../../../../assets/Icons/SkillIcon";
import ItemIcon from "../../../../../assets/Icons/ItemIcon";
import Tooltip from "../../../../CommonComponents/Tooltip/Tooltip";
import { translateSkillSign } from "../../../../../helpers/helpers";
import InventoryItem from "../../CharacterSide/CharacterInventory/InventoryItem/InventoryItem";
import { SKILLS_KEYS } from "../../../../../helpers/commonConstants";

const ItemSkillCircle = ({ isClosed, type, onDropItem, choosedItem }) => {
  const typeIcon = type === SKILLS_KEYS.item ? <ItemIcon /> : <SkillIcon />;

  const handleDrop = (e) => {
    e.preventDefault();
    const data = e.dataTransfer.getData("application/json");
    try {
      const item = JSON.parse(data);
      // console.log(item);
      // console.log(type);

      onDropItem(item);
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
