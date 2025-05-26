import React from "react";
import s from "./Modal.module.scss";

const Modal = ({ children, onClose }) => {
  return (
    <div className={s.modal_overlay} onClick={onClose}>
      <div className={s.modal_content} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
};

export default Modal;
