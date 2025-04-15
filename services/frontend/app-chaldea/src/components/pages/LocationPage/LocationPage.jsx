import s from "./LocationPage.module.scss"
import {useNavigate, useParams} from "react-router-dom";
import {BASE_URL} from "../../../api/api.js";
import axios from "axios";
import {useEffect, useState} from "react";
import {useBodyBackground} from "../../../hooks/useBodyBackground.js";
import Textarea from "../../CommonComponents/Textarea/Textarea.jsx";

const LocationPage = () => {
    const {locationId} = useParams();
    const navigate = useNavigate();
    const [location, setLocation] = useState(null);


    useBodyBackground(location?.image_url);


    useEffect(() => {
        if (locationId) {
            fetchLocationData()
        }
    }, [])

    const fetchLocationData = async () => {
        const res = await axios.get(`${BASE_URL}/locations/${locationId}/details`)
        setLocation(res.data);
        console.log(res.data)
    }

    return (
        location &&
        <div className={s.location_page}>
            <button onClick={() => navigate(-1)}></button>
            <div className={s.content}>
                <div className={s.bar}>
                    <div className={s.image}
                         style={{backgroundImage: `url('${location?.image_url ? location?.image_url : ''}')`}}>
                    </div>
                </div>
                <div className={s.content_inner}>
                    <h1>{location.name}</h1>
                    <p>{location.description}</p>
                    <Textarea text="Введите текст..." name="post" id="post" cols="30" rows="10"></Textarea>
                </div>

            </div>
        </div>
    );
}

export default LocationPage;
