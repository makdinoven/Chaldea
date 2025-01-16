import s from './MapPoint.module.scss'
import {useState} from "react";

export default function MapPoint({data}) {
    console.log(data)

    return (
        <div
            style={{top: `${data.y}px`,
                    left: `${data.x}px`,
                    backgroundImage: `url(${data?.image_url ? data.image_url : 'no-background'})`}}
            className={s.point}>

        </div>)
}