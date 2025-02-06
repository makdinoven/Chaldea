import s from './WorldPage.module.scss';
import {useEffect} from 'react';
import {useDispatch, useSelector} from 'react-redux';
import {fetchCountries} from '../../redux/actions/countryActions.js';
import Map from './Map/Map.jsx';
import CountryDropdown from './CountryDropdown/CountryDropdown.jsx';
import backgroundImage from '../../assets/background.png';
import {useBodyBackground} from '../../hooks/useBodyBackground.js';
import DetailCard from "./DetailCard/DetailCard.jsx";

export default function WorldPage() {
    const dispatch = useDispatch();
    const countries = useSelector((state) => state.countries.countries);
    const isLoaded = useSelector(state => state.countries.isLoaded);
    const loading = useSelector((state) => state.countries.loading);

    // useEffect(() => {
    //     console.log('rerender')
    // })

    useBodyBackground(backgroundImage);

    useEffect(() => {
        !isLoaded && dispatch(fetchCountries());
    }, []);

    // useEffect(() => {
    //     console.log('world page rerender');
    // })

    return (
        <div className={s.worldpage_container}>
            {loading ? (
                'Loading...'
            ) : (
                <>
                    <div className={s.dropdown_container}>
                        {countries.map((country) => (
                            <CountryDropdown
                                key={country.name}
                                id={country.id}
                            />
                        ))}
                    </div>
                    <div className={s.map_container}>
                        <Map type={'country'}/>
                        <div className={s.detail_cards_container}>
                            <>
                                <DetailCard type={'leader'}/>
                                <DetailCard type={'description'}/>
                                <DetailCard type={'vestnik'}/>
                            </>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}