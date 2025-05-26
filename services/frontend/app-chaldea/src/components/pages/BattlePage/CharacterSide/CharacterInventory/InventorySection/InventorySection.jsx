import s from "./InventorySection.module.scss";
import InventoryItem from "../InventoryItem/InventoryItem.jsx";

const InventorySection = ({ items, isOpponent, setTurnData, cooldowns }) => {
  return (
    <ul className={`${s.list} ${isOpponent ? s.opponent : ""}`}>
      {items &&
        items.flatMap((item) => {
          const quantity = item.quantity || 1;
          return Array.from({ length: quantity }, (_, index) => {
            const cooldownValue = cooldowns?.[item.id];
            const isCooldown = cooldownValue > 0;

            return (
              <InventoryItem
                type={item?.slot_type ? "item" : "skill"}
                setTurnData={setTurnData}
                isCooldown={isCooldown}
                cooldownValue={cooldownValue}
                isDraggable={!isOpponent}
                key={`${item.id}-${index}`}
                item={item}
              />
            );
          });
        })}
    </ul>
  );
};

export default InventorySection;
