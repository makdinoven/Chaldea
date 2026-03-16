import s from "./InventorySectionBtn.module.scss";
import Tooltip from "../../../../../CommonComponents/Tooltip/Tooltip";

const InventorySectionBtn = ({ isActive, handleClick, icon, name }) => {
  return (
    <button
      onClick={() => handleClick(name)}
      className={`${s.btn} ${isActive ? s.active : ""}`}
    >
      {icon}
      <Tooltip className={s.tooltip} name={name} />
    </button>
  );
};

export default InventorySectionBtn;
