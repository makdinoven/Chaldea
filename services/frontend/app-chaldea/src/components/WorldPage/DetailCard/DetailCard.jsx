import s from './DetailCard.module.scss'

export default function DetailCard({data}) {
    // console.log(data)
    return (
        <div className={s.card}>{data?.description}</div>
    )
}