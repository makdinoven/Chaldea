import {useEffect, useState} from "react";
import DropdownItem from "../WorldPage/CountryDropdown/DropdownItem/DropdownItem.jsx";
import {useDispatch, useSelector} from "react-redux";
import DropdownLayout from "../WorldPage/DropdownLayout/DropdownLayout.jsx";
import {setOpenedRegionId} from "../../redux/slices/regionsSlice.js";
import {fetchRegionDetails} from "../../redux/actions/regionsActions.js";
import DropdownLayoutLocations from "../WorldPage/DropdownLayoutLocations/DropdownLayoutLocations.jsx";

export default function RegionDropdown({id, name}) {
    const dispatch = useDispatch();
    const openedRegionId = useSelector((state) => state.regions.openedRegionId);
    const regionData = useSelector((state) => state.regions.data[id]);
    const loading = useSelector((state) => state.regions.loading[id] || false);
    const isLoaded = useSelector((state) => state.regions.isLoaded[id] || false);
    const error = useSelector((state) => state.regions.error[id] || null);
    const isOpen = openedRegionId === id;
    const [openIds, setOpenIds] = useState([]);

    const toggleLocation = (id) => {
        setOpenIds(prev =>
            prev.includes(id)
                ? prev.filter(openId => openId !== id)
                : [...prev, id]
        );
    };

    const isLocationOpen = (id) => openIds.includes(id);

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
        return locations.map((location) => {
            const hasChildren = location.children.length > 0;
            const isOpen = isLocationOpen(location.id);

            return hasChildren ? (
                <DropdownLayoutLocations
                    key={location.id}
                    label={location.name}
                    isOpen={isOpen}
                    handleClick={() => toggleLocation(location.id)}
                >
                    {renderLocations(location.children)}
                </DropdownLayoutLocations>
            ) : (
                <DropdownItem
                    key={location.id}
                    name={location.name}
                    type="gold"
                    link={`/location/${location.id}`}
                />
            );
        });
    };


    return (
        <DropdownLayout label={name} handleClick={handleDropdownButtonClick} isOpen={isOpen}>
            {regionData?.districts.length > 0 ? (
                regionData.districts.map((district) => (

                    <DropdownLayout
                        key={district.id} label={district.name}
                        handleClick={() => setOpenedDistrict(district.id)}
                        isOpen={district.id === openedDistrict}
                    >
                        <>
                            {district.entrance_location && <DropdownItem
                                key={district.entrance_location.id}
                                name={district.entrance_location.name}
                                type="blue"
                                link={`/region/${location.id}`}
                            />}
                            {district.locations.length > 0 ? renderLocations(district.locations) :
                                <p>Локаций нет</p>}
                        </>

                    </DropdownLayout>
                ))
            ) : (
                <p>Районов нет</p>
            )}
        </DropdownLayout>
    );
}
