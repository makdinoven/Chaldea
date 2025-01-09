import s from './CountryDropdown.module.scss'
import {useEffect, useState} from "react";
import axios from "axios";
import DropdownItem from "./DropdownItem/DropdownItem.jsx";

export default function CountryDropdown({ name, id }) {
    const [isOpened, setIsOpened] = useState(false);
    const [regions, setRegions] = useState([]);
    const [loading, setLoading] = useState(false);

    const handleDropdownClick = () => {
        if (!isOpened) {
            setIsOpened(true);
            loadRegions();
        }
        setIsOpened(!isOpened);
    };

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
            })
            .catch((error) => {
                console.error(error);
                setLoading(false);
            });
    }

    return (
        <div className={s.dropdown}>
            <div
                className={`${s.dropdown_button} ${isOpened ? s.active : ''}`}
                onClick={handleDropdownClick}
            >
                {name}
            </div>
            {isOpened && (
                    loading ? (
                        <p>Loading...</p>
                    ) : (
                        regions.map((region) => (
                            <DropdownItem key={region.id} name={region.name} id={region.id} />
                        ))
                    )
            )}
        </div>
    );
}
