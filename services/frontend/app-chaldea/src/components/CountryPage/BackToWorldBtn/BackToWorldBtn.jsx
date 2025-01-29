import s from './BackToWorldBtn.module.scss'
import {Link} from "react-router-dom";

export default function BackToWorldBtn({imgUrl}) {
    return (
        <Link to='/world' className={s.btn_wrapper}>
            <div style={{backgroundImage: `url(${imgUrl})`}} className={s.btn}>
                Вернуться на карту мира
            </div>
        </Link>
    )
}