import { Dispatch, SetStateAction } from "react";
import InventoryItem from "../InventoryItem/InventoryItem";

interface InventoryItemData {
  id?: number;
  item_id?: number;
  slot_type?: string;
  _cloneKey?: string;
  [key: string]: unknown;
}

interface InventorySectionProps {
  items: InventoryItemData[] | null;
  isOpponent: boolean;
  setTurnData: Dispatch<SetStateAction<Record<string, unknown>>> | null;
  cooldowns: Record<number, number> | null;
}

const InventorySection = ({
  items,
  isOpponent,
  setTurnData,
  cooldowns,
}: InventorySectionProps) => {
  return (
    <ul
      className={`py-3 px-[22px] grid grid-cols-[repeat(4,60px)] auto-rows-[60px] gap-[18px] max-h-[390px] overflow-y-auto overflow-x-hidden gold-scrollbar ${isOpponent ? "[direction:rtl] [&>*]:[direction:ltr] [&>*]:text-left" : ""}`}
    >
      {items &&
        items.map((item) => {
          const itemId = item.id ?? item.item_id;
          const cooldownValue =
            itemId != null ? cooldowns?.[itemId] : undefined;
          const isCooldown = (cooldownValue ?? 0) > 0;
          const key = item._cloneKey ?? `${item.slot_type}-${itemId}`;

          return (
            <InventoryItem
              setTurnData={setTurnData}
              isCooldown={isCooldown}
              cooldownValue={cooldownValue}
              isDraggable={!isOpponent}
              key={key}
              item={item}
            />
          );
        })}
    </ul>
  );
};

export default InventorySection;
