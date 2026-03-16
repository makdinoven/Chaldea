import {useEffect} from "react";
import {useDispatch, useSelector} from "react-redux";
import {setOpenedCountryId} from "../../../redux/slices/countriesSlice";
import {fetchCountryDetails} from "../../../redux/actions/countryActions";
import DropdownLayout from "../DropdownLayout/DropdownLayout";
import s from "./CountryDropdown.module.scss";
import {Link} from "react-router-dom";
import {setOpenedRegionId} from "../../../redux/slices/regionsSlice";

export default function CountryDropdown({id, name}) {
    const dispatch = useDispatch();
    const openedCountryId = useSelector((state) => state.countries.openedCountryId);
    const countryDetails = useSelector((state) => state.countryDetails.data[id]);
    const loading = useSelector((state) => state.countryDetails.loading[id]);
    const isLoaded = useSelector((state) => state.countryDetails.isLoaded[id]);
    const isOpen = openedCountryId === id;

    const handleDropdownButtonClick = () => {
        if (openedCountryId !== id) {
            if (!isOpen) {
                dispatch(setOpenedCountryId(id));
                if (!isLoaded) {
                    dispatch(fetchCountryDetails(id));
                }
            }
        }
    };

    const handleLinkClick = (id) => {
        dispatch(setOpenedRegionId(id));
    }

    useEffect(() => {
        if (isOpen && !isLoaded) {
            dispatch(fetchCountryDetails(id));
        }
    }, [])

    // useEffect(() => {
    //     console.log(`dropdown countryID: ${id} rerender`);
    // })

    return (
        <DropdownLayout label={name} handleClick={handleDropdownButtonClick} isOpen={isOpen}>
            {
                countryDetails?.regions.map((region) => (
                        <Link key={region.id}
                              onClick={() => handleLinkClick(region.id)}
                              className={s.link}
                              to={`country/${openedCountryId}`}>

                            {region.name}
                        </Link>
                    )
                )
            }
        </DropdownLayout>
    );

}
