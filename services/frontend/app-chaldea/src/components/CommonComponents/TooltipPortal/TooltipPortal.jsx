import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import s from "./TooltipPortal.module.scss";

const TooltipPortal = ({ targetRef, children }) => {
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const tooltipRef = useRef();

  useEffect(() => {
    const updatePosition = () => {
      if (!targetRef.current) return;
      const rect = targetRef.current.getBoundingClientRect();
      setPosition({
        top: rect.top + window.scrollY + rect.height + 10,
        left: rect.left + window.scrollX + rect.width / 2,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    return () => window.removeEventListener("resize", updatePosition);
  }, [targetRef]);

  return createPortal(
    <div
      ref={tooltipRef}
      className={s.tooltip}
      style={{ top: `${position.top}px`, left: `${position.left}px` }}
    >
      {children}
    </div>,
    document.body,
  );
};

export default TooltipPortal;
