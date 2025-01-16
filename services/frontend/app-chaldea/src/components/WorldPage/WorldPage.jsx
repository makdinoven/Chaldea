import s from './WorldPage.module.scss'
import axios from "axios";
import {useEffect, useState} from "react";
import Map from "./Map/Map.jsx";
import CountryDropdown from "./CountryDropdown/CountryDropdown.jsx";
import backgroundImage from '../../assets/background.png'
import {useBodyBackground} from "../../hooks/useBodyBackground.js";

export default function WorldPage() {
    const [countries, setCountries] = useState([])
    const [loading, setLoading] = useState(true)
    const [openDropdownId, setOpenDropdownId] = useState(null);
    useBodyBackground(backgroundImage);

    //подгрузка стран
    useEffect(() => {
        axios
            .get('http://localhost:8006/locations/countries/lookup', {
                headers: {
                    Accept: 'application/json',
                },
            })
            .then((response) => {
                setCountries(response.data);
                setLoading(false)
            })
            .catch((error) => console.log(error));
    }, []);

    //установка первого дропдауна открытым
    useEffect(() => {
        countries.length > 0 && setOpenDropdownId(countries[0]?.id)
    },[countries]);

    //обработчик клика по дропдауну
    const handleDropdownClick = (id) => {
        (openDropdownId !== id) && setOpenDropdownId(id);
    }

    return (
        <div className={s.worldpage_container}>
            {loading ? (
                'Loading...'
            ) : (
                <>
                    <div className={s.dropdown_container}>
                        {countries.map((country, index) => (
                            <CountryDropdown
                                name={country.name}
                                key={country.id}
                                id={country.id}
                                isOpen={openDropdownId === country.id}
                                handleDropdownClick={() => handleDropdownClick(country.id)}
                            />
                        ))}
                    </div>
                    <Map countryId={openDropdownId} />
                </>
            )}
        </div>
    );
}