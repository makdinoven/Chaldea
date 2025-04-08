import s from './DropdownItem.module.scss'
import {Link} from "react-router-dom";

export default function DropdownItem({name, link, type}) {
    switch (type) {
        case "blue":
            return <Link className={s.link_blue} to={link}>{name}</Link>
        case "gold":
            return <Link className={s.link_gold} to={link}>{name}</Link>
        default:
            return <Link className={s.link} to={link}>{name}</Link>;
    }

}