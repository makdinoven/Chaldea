import s from './CountryDropdown.module.scss';
import {useEffect, useState} from "react";
import DropdownItem from "./DropdownItem/DropdownItem.jsx";
import {useDispatch, useSelector} from "react-redux";
import {setOpenedCountryId} from "../../../redux/slices/countriesSlice.js";
import {fetchCountryDetails} from "../../../redux/actions/fetchCountryDetails.js";
import DropdownButton from "../DropdownButton/DropdownButton.jsx";

export default function CountryDropdown({ id }) {
    const dispatch = useDispatch();
    const country = useSelector((state) => state.countries.countries.find((country) => country.id === id));
    const openedCountryId = useSelector((state) => state.countries.openedCountryId);
    const countryDetails = useSelector((state) => state.countryDetails.data[id]);
    const loading = useSelector((state) => state.countryDetails.loading[id]);
    const isLoaded = useSelector((state) => state.countryDetails.isLoaded[id]);


    const isOpen = openedCountryId === id;

    useEffect(() => {
            if (isOpen && !isLoaded) {
                dispatch(fetchCountryDetails(id));
            }
    }, [])

    const handleDropdownButtonClick = () => {
        if (openedCountryId !== id) {
            if (isOpen) {
                dispatch(setOpenedCountryId(null));
            } else {
                dispatch(setOpenedCountryId(id));
                if (!isLoaded) {
                    dispatch(fetchCountryDetails(id));
                }
            }
        }
    };

    // useEffect(() => {
    //     console.log(`dropdown countryID: ${id} rerender`);
    // })

    return (
        <DropdownButton label={country.name} handleClick={handleDropdownButtonClick} isOpen={isOpen}>
            {loading ? (
                <p>Загрузка...</p>
            ) : (
                countryDetails?.regions.map((region) => (
                    <DropdownItem
                        key={region.id}
                        name={region.name}
                        id={region.id}
                        link={`/region/${region.id}`}
                    />
                ))
            )}
        </DropdownButton>
    );

}
