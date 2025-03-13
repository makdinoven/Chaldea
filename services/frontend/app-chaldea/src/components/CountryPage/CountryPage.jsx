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
import {fetchCountries, fetchCountryDetails} from "../../redux/actions/countryActions.js";
import RegionDropdown from "./RegionDropdown.jsx";

export default function CountryPage() {
    const dispatch = useDispatch();
    const {countryId} = useParams();
    const isLoaded = useSelector(state => state.countries.isLoaded);
    const country = useSelector((state) => state.countryDetails.data[countryId]);
    const regions = useSelector((state) => state.countryDetails.data[countryId]?.regions);
    useBodyBackground(backgroundImage);

    useEffect(() => {
        if (!isLoaded) {
            dispatch(fetchCountries());
            dispatch(fetchCountryDetails(countryId));
        }
    }, []);

    const renderDetailCards = () => {
        return (<>
            <DetailCard>
                {
                    'leader'
                }
            </DetailCard>
            <DetailCard>
                {
                    'description'
                }
            </DetailCard>
            <DetailCard>
                {
                    'vestnik'
                }
            </DetailCard>
        </>)
    }


    return (
        <div className={s.regionPage_container}>
            <div className={s.dropdown_container}>
                <h1 className={s.country_name}>{country?.name}</h1>
                {regions && regions.map((region) => (
                    <RegionDropdown
                        key={region.name}
                        id={region.id}
                        name={region.name}
                    />
                ))}
            </div>
            <div className={s.map_container}>
                <BackToWorldBtn imgUrl={backgroundImage}/>
                <Map type={'region'}/>
                <div className={s.detail_cards_container}>
                    {renderDetailCards()}
                </div>
            </div>
        </div>
    )
}