import { useState } from "react";
import s from "./DropdownButton.module.scss";

export default function DropdownButton({label, handleClick, isOpen, children }) {
    return (
        <div className={s.dropdown}>
            <div
                className={`${s.dropdown_button} ${isOpen ? s.active : ""}`}
                onClick={handleClick}
            >
                {label}
            </div>
            {isOpen && children}
        </div>
    );
}
