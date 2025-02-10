import {useEffect, useState} from "react";
import DropdownItem from "../WorldPage/CountryDropdown/DropdownItem/DropdownItem.jsx";
import {useDispatch, useSelector} from "react-redux";
import {setOpenedCountryId} from "../../redux/slices/countriesSlice.js";
import {fetchCountryDetails} from "../../redux/actions/countryActions.js";
import DropdownLayout from "../WorldPage/DropdownLayout/DropdownLayout.jsx";
import {useParams} from "react-router-dom";
import {setOpenedRegionId} from "../../redux/slices/regionsSlice.js";
import {fetchRegionDetails} from "../../redux/actions/regionsActions.js";

export default function RegionDropdown({id, name}) {
    const dispatch = useDispatch();
    const openedRegionId = useSelector((state) => state.regions.openedRegionId);
    const regionData = useSelector((state) => state.regions.data[id]);
    const loading = useSelector((state) => state.regions.loading[id] || false);
    const isLoaded = useSelector((state) => state.regions.isLoaded[id] || false);
    const error = useSelector((state) => state.regions.error[id] || null);
    const isOpen = openedRegionId === id;

    const [openedDistrict, setOpenedDistrict] = useState(1);

    const handleDropdownButtonClick = () => {
        if (openedRegionId !== id) {
            if (!isOpen) {
                dispatch(setOpenedRegionId(id));
                if (!isLoaded) {
                    dispatch(fetchRegionDetails(id));
                }
            }
        }
    };

    useEffect(() => {
        if (isOpen && !isLoaded) {
            dispatch(fetchRegionDetails(id));
        }
    }, [])

    const renderLocations = (locations) => {
        return locations.map((location) => (
            <DropdownLayout key={location.id} label={location.name} isOpen={true}>
                {location.children.length > 0 ? renderLocations(location.children) :
                    <DropdownItem name={location.name} link={""}/>}
            </DropdownLayout>
        ));
    };

    return (
        <DropdownLayout label={name} handleClick={handleDropdownButtonClick} isOpen={isOpen}>
            {regionData?.districts.length > 0 ? (
                regionData.districts.map((district) => (
                    <DropdownLayout key={district.id} label={district.name}
                                    handleClick={() => setOpenedDistrict(district.id)}
                                    isOpen={district.id === openedDistrict}
                    >
                        {district.locations.length > 0 ? renderLocations(district.locations) : <p>Локаций нет</p>}
                    </DropdownLayout>
                ))
            ) : (
                <p>Районов нет</p>
            )}
        </DropdownLayout>
    );
}
