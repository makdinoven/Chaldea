import s from './CountryDropdown.module.scss';
import {useEffect, useState} from "react";
import axios from "axios";
import DropdownItem from "./DropdownItem/DropdownItem.jsx";

export default function CountryDropdown({ name, id, isOpen, handleDropdownClick }) {
    const [regions, setRegions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [loaded, setLoaded] = useState(false); // Флаг, чтобы загружать регионы только один раз

    useEffect(() => {
        if (isOpen && !loaded) {
            loadRegions();
        }
    }, [isOpen]);

    function loadRegions() {
        setLoading(true);
        axios
            .get(`http://localhost:8006/locations/countries/${id}/details`, {
                headers: {
                    Accept: 'application/json',
                },
            })
            .then((response) => {
                setRegions(response.data.regions);
                setLoading(false);
                setLoaded(true);
            })
            .catch((error) => {
                console.error(error);
                setLoading(false);
            });
    }

    return (
        <div className={s.dropdown}>
            <div
                className={`${s.dropdown_button} ${isOpen ? s.active : ''}`}
                onClick={handleDropdownClick}
            >
                {name}
            </div>
            {isOpen && (
                    loading ? (
                        <p>Загрузка...</p>
                    ) : (
                        regions.map((region) => (
                            <DropdownItem key={region.id} name={region.name} id={region.id} />
                        ))
                    )
            )}
        </div>
    );

}
