import s from "./DropdownLayout.module.scss";

export default function DropdownLayout({label, handleClick, isOpen, children}) {
    return (
        <div className={s.dropdown}>
            <div
                className={`${s.dropdown_button} ${isOpen ? s.active : ""}`}
                onClick={handleClick}
            >
                {label}
            </div>
            {isOpen &&
                <div className={s.dropdown_content}>
                    {children}
                </div>
            }
        </div>
    );
}
