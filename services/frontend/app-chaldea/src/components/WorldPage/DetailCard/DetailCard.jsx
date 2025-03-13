import s from './DetailCard.module.scss'
import {useSelector} from "react-redux";

export default function DetailCard({children}) {
    return (
        <div className={s.card}>
            {children}
        </div>)


}