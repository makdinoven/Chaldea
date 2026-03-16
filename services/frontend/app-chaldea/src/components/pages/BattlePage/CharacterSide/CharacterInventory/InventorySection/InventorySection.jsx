import s from "./InventorySection.module.scss";
import InventoryItem from "../InventoryItem/InventoryItem";

const InventorySection = ({ items, isOpponent, setTurnData, cooldowns }) => {
  return (
    <ul className={`${s.list} ${isOpponent ? s.opponent : ""}`}>
      {items &&
        items.map((item, index) => {
          const cooldownValue = cooldowns?.[item.id];
          const isCooldown = cooldownValue > 0;

          return (
            <InventoryItem
              setTurnData={setTurnData}
              isCooldown={isCooldown}
              cooldownValue={cooldownValue}
              isDraggable={!isOpponent}
              key={`${index}-${item.id}`}
              item={item}
            />
          );
        })}
    </ul>
  );
};

export default InventorySection;
