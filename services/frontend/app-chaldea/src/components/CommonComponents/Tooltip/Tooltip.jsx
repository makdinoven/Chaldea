import s from "./Tooltip.module.scss";

const Tooltip = ({ content, name, className }) => {
  return <div className={`${s.tooltip_container} ${className}`}>{name}</div>;
};

export default Tooltip;
