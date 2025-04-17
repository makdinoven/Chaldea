import s from "./NeighborCard.module.scss"
import {Link} from "react-router-dom";

const NeighborCard = ({price, name, img, link}) => {

    return (
        <Link to={link} className={s.card}>
            <div className={s.img_wrapper}>
                <div style={{backgroundImage: `url("${img}")`}} className={s.img}>
                    <div className={s.price}>
                        <span>{price ? price : "price"}</span>
                    </div>

                </div>
            </div>
            <p>{name}</p>
        </Link>

    )
};

export default NeighborCard;