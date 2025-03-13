import s from './MapTooltip.module.scss'
import LineButton from "../../../CommonComponents/LineButton/LineButton.jsx";

export default function MapTooltip({data}) {
    // console.log(data)
    // console.log(data?.image_url)
    return (
        <div className={s.tooltip}>
            <div className={s.tooltip_header}>
                <div className={s.image}
                     style={{backgroundImage: `url('${data?.image_url ? data.image_url : ''}')`}}>

                </div>
                <div>
                    <h4 className={s.tooltip_name}>{data?.name}</h4>

                    <p className={s.tooltip_text}>
                        <span>Входная локация:</span>{data?.entrance_location_name || 'Нет данных'}
                    </p>
                </div>
            </div>
            <LineButton text={'Перейти'} link={'#'} />

        </div>
    )
}