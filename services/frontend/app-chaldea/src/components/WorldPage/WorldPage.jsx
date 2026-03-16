import s from './WorldPage.module.scss';
import {useEffect} from 'react';
import {useDispatch, useSelector} from 'react-redux';
import {fetchCountries} from '../../redux/actions/countryActions';
import Map from './Map/Map';
import CountryDropdown from './CountryDropdown/CountryDropdown';
import backgroundImage from '../../assets/background.png';
import {useBodyBackground} from '../../hooks/useBodyBackground';
import DetailCard from "./DetailCard/DetailCard";
import useNavigateTo from '../../hooks/useNavigateTo';

export default function WorldPage() {
    const dispatch = useDispatch();
    const countries = useSelector((state) => state.countries.countries);
    const isLoaded = useSelector(state => state.countries.isLoaded);
    const loading = useSelector((state) => state.countries.loading);
    const navigateTo = useNavigateTo();


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

    const renderDetailCards = () => {
        return (
            <>
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
                                name={country.name}
                            />
                        ))}
                        <button
                            className={s.admin_button}
                            onClick={() => navigateTo('/admin/locations')}
                        >
                            Управление локациями
                        </button>
                    </div>
                    <div className={s.map_container}>
                        <Map type={'country'}/>
                        <div className={s.detail_cards_container}>
                            {renderDetailCards()}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}