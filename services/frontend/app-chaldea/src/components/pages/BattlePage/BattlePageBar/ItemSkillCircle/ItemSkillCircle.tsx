import ClosedItemSkillIcon from "../../../../../assets/IconComponents/ClosedItemSkillIcon";
import SkillIcon from "../../../../../assets/IconComponents/SkillIcon";
import ItemIcon from "../../../../../assets/IconComponents/ItemIcon";
import Tooltip from "../../../../CommonComponents/Tooltip/Tooltip";
import { translateSkillSign } from "../../../../../helpers/helpers";
import InventoryItem from "../../CharacterSide/CharacterInventory/InventoryItem/InventoryItem";
import { SKILLS_KEYS } from "../../../../../helpers/commonConstants";

interface SkillSlot {
  id?: number;
  item_id?: number;
  [key: string]: unknown;
}

interface ItemSkillCircleProps {
  isClosed: boolean;
  type: string;
  onDropItem: (item: SkillSlot) => void;
  choosedItem: SkillSlot | null;
  onClear?: () => void;
}

const ItemSkillCircle = ({
  isClosed,
  type,
  onDropItem,
  choosedItem,
  onClear,
}: ItemSkillCircleProps) => {
  const typeIcon =
    type === SKILLS_KEYS.item ? <ItemIcon /> : <SkillIcon />;

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const data = e.dataTransfer.getData("application/json");
    try {
      const item = JSON.parse(data) as SkillSlot;
      onDropItem(item);
    } catch {
      console.warn("Invalid item data dropped");
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleClick = () => {
    if (isClosed || !choosedItem || !onClear) return;
    onClear();
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onClick={handleClick}
      className={`group relative flex shrink-0 items-center justify-center rounded-full
        w-[60px] h-[60px]
        sm:w-[60px] sm:h-[60px]
        [&_svg]:w-[31px] [&_svg]:h-[40px]
        ${
          choosedItem
            ? "border-0 cursor-pointer"
            : "border border-[#f9d8d8] cursor-pointer"
        }
        ${
          isClosed
            ? "cursor-not-allowed bg-black/20 !border-2 !border-[#999]"
            : ""
        }
      `}
    >
      {isClosed ? (
        <ClosedItemSkillIcon />
      ) : choosedItem ? (
        <InventoryItem isDraggable={false} item={choosedItem} />
      ) : (
        <>
          {typeIcon}
          <Tooltip
            className="hidden opacity-0 group-hover:block group-hover:opacity-100"
            name={translateSkillSign(type)}
          />
        </>
      )}
    </div>
  );
};

export default ItemSkillCircle;
