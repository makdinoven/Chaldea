import s from './LineButton.module.scss';
import {Link} from "react-router-dom";

export default function LineButton({text, link}) {
    return (<Link className={s.button} to={link}>{text}</Link>)
}