import s from "./Tooltip.module.scss";

/**
 * @param {{
 *   content?: import('react').ReactNode,
 *   name: import('react').ReactNode,
 *   className: string,
 * }} props
 */
const Tooltip = ({ content, name, className }) => {
  return <div className={`${s.tooltip_container} ${className}`}>{name}</div>;
};

export default Tooltip;
