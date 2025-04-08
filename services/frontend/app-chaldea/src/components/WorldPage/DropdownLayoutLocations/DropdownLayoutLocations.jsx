import s from "./DropdownLayoutLocations.module.scss";

export default function DropdownLayoutLocations({label, handleClick, isOpen, children}) {
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
