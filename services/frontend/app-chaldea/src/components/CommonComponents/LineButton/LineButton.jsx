import s from './LineButton.module.scss';
import {Link} from "react-router-dom";

export default function LineButton({text, link, onClick}) {
    return (<Link onClick={onClick} className={s.button} to={link}>{text}</Link>)
}