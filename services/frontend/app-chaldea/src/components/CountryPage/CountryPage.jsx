import s from './CountryPage.module.scss';
import {useParams} from "react-router-dom";
import {useDispatch, useSelector} from "react-redux";
import CountryDropdown from "../WorldPage/CountryDropdown/CountryDropdown.jsx";
import {useBodyBackground} from "../../hooks/useBodyBackground.js";
import backgroundImage from "../../assets/countryBackground.png";
import {useEffect} from "react";
import Map from "../WorldPage/Map/Map.jsx";
import DetailCard from "../WorldPage/DetailCard/DetailCard.jsx";
import BackToWorldBtn from "./BackToWorldBtn/BackToWorldBtn.jsx";
import {fetchCountries} from "../../redux/actions/fetchCountries.js";
import {fetchCountryDetails} from "../../redux/actions/fetchCountryDetails.js";

export default function CountryPage() {
    const dispatch = useDispatch();
    const {countryId, regionId} = useParams();
    const isLoaded = useSelector(state => state.countries.isLoaded);
    const country = useSelector((state) => state.countryDetails.data[countryId]);
    const regions = useSelector((state) => state.countryDetails.data[countryId]?.regions);

    useEffect(() => {
        if (!isLoaded) {
            dispatch(fetchCountries());
            dispatch(fetchCountryDetails(countryId));
        }
    }, []);

    useBodyBackground(backgroundImage);

    return (
        <div className={s.regionPage_container}>
            <div className={s.dropdown_container}>
                <h1 className={s.country_name}>{country?.name}</h1>

            </div>
            <div className={s.map_container}>
                <BackToWorldBtn imgUrl={backgroundImage}/>
                {/*<Map  type={'region'} />*/}
                <div className={s.detail_cards_container}>
                    <>
                        <DetailCard type={'leader'}/>
                        <DetailCard type={'description'}/>
                        <DetailCard type={'vestnik'}/>
                    </>
                </div>
            </div>
        </div>
    )
}