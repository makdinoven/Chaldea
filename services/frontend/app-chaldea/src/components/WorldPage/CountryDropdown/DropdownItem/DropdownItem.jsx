import s from './DropdownItem.module.scss'
import {Link} from "react-router-dom";

export default function DropdownItem ({name, id,link})  {

    return (<Link className={s.link} to={link}>{name}</Link>)
}