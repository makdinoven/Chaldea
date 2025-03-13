import s from './MapPoint.module.scss'
import {useState} from "react";

export default function MapPoint({data, handleMapPointClick, isActive}) {
    return (
        <div
            style={{top: `${data?.y}px`,
                    left: `${data?.x}px`,
                    backgroundImage: `url('${data?.image_url ? data.image_url : 'no-background'}')`}}
            className={`${s.point} ${isActive ? s.active : ''}`}
            onClick={handleMapPointClick}
        ></div>)
}