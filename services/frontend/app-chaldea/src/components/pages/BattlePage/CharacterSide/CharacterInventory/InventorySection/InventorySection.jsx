import s from "./InventorySection.module.scss";
import InventoryItem from "../InventoryItem/InventoryItem.jsx";

const InventorySection = ({ items, isOpponent, setTurnData }) => {
  return (
    <ul className={`${s.list} ${isOpponent ? s.opponent : ""}`}>
      {items &&
        items.map((item, index) => (
          <InventoryItem
            setTurnData={setTurnData}
            isCooldown={!!item.cooldown_count}
            isDraggable={!isOpponent}
            key={index}
            item={item}
          />
        ))}
    </ul>
  );
};

export default InventorySection;
