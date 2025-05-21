import s from "./Tooltip.module.scss";

const Tooltip = ({ name, className }) => {
  return <div className={`${s.tooltip_container} ${className}`}>{name}</div>;
};

export default Tooltip;
