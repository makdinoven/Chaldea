import s from './MapTooltip.module.scss'

export default function MapTooltip({id}) {
    console.log(id)
    return (
        <div className={s.tooltip}></div>
    )
}