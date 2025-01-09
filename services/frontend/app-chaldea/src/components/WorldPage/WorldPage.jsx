import s from './WorldPage.module.scss'
import axios from "axios";
import {useEffect, useState} from "react";
import Map from "./Map/Map.jsx";
import CountryDropdown from "./CountryDropdown/CountryDropdown.jsx";

export default function WorldPage() {
    const [countries, setCountries] = useState([])
    const [loading, setLoading] = useState(true)

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


    return (
        <div className={s.dropdown_container}>
            {loading ? 'Loading...' : countries.map((country) => (
                <CountryDropdown name={country.name} key={country.id} id={country.id} />
            ))}
            </div>)

}