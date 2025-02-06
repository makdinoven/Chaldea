import {useEffect} from "react";
import DropdownItem from "./DropdownItem/DropdownItem.jsx";
import {useDispatch, useSelector} from "react-redux";
import {setOpenedCountryId} from "../../../redux/slices/countriesSlice.js";
import {fetchCountryDetails} from "../../../redux/actions/countryActions.js";
import DropdownLayout from "../DropdownLayout/DropdownLayout.jsx";

export default function RegionDropdown({id}) {
    const dispatch = useDispatch();
    // const country = useSelector((state) => state.countries.countries.find((country) => country.id === id));
    // const openedCountryId = useSelector((state) => state.countries.openedCountryId);
    // const countryDetails = useSelector((state) => state.countryDetails.data[id]);
    // const loading = useSelector((state) => state.countryDetails.loading[id]);
    // const isLoaded = useSelector((state) => state.countryDetails.isLoaded[id]);
    // const isOpen = openedCountryId === id;

    const handleDropdownButtonClick = () => {
        // if (openedCountryId !== id) {
        //     if (isOpen) {
        //         dispatch(setOpenedCountryId(null));
        //     } else {
        //         dispatch(setOpenedCountryId(id));
        //         if (!isLoaded) {
        //             dispatch(fetchCountryDetails(id));
        //         }
        //     }
        // }
    };

    useEffect(() => {
        // if (isOpen && !isLoaded) {
        //     dispatch(fetchCountryDetails(id));
        // }
    }, [])

    // useEffect(() => {
    //     console.log(`dropdown countryID: ${id} rerender`);
    // })

    return (
        <DropdownLayout label={id} handleClick={handleDropdownButtonClick} isOpen={false}>
            {
                // countryDetails?.regions.map((region) => (
                //         <DropdownItem
                //             key={region.id}
                //             name={region.name}
                //             id={region.id}
                //             link={`country/${openedCountryId}/${region.id}`}
                //         />
                //     )
                // )
            }
        </DropdownLayout>
    );

}
