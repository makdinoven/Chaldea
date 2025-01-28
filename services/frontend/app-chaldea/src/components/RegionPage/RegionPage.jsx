import s from './RegionPage.module.scss';
import {useParams} from "react-router-dom";

export default function RegionPage() {
    const { regionId } = useParams();
    return (
        <div className={s.regionPage_container}>
                <h1>{regionId}</h1>
        </div>
    )
}