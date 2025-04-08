import s from './MapTooltip.module.scss'
import LineButton from "../../../CommonComponents/LineButton/LineButton.jsx";
import {setOpenedRegionId} from "../../../../redux/slices/regionsSlice.js";
import {useDispatch} from "react-redux";

export default function MapTooltip({data, type}) {
    const dispatch = useDispatch();

    const handleClick = () => {
        dispatch(setOpenedRegionId(data.id))
    }

    return (
        <div className={s.tooltip}>
            <div className={s.tooltip_header}>
                <div className={s.image}
                     style={{backgroundImage: `url('${data?.image_url ? data.image_url : ''}')`}}>
                </div>
                <div>
                    <h4 className={s.tooltip_name}>{data?.name}</h4>

                    <p className={s.tooltip_text}>
                        {data.description}
                    </p>
                </div>
            </div>
            <LineButton onClick={handleClick} text={'Перейти'} link={`country/${data?.country_id}`}/>
        </div>
    )
}