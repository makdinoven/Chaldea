import s from './DetailCard.module.scss'
import {useSelector} from "react-redux";

export default function DetailCard({type}) {
    const openedCountryId = useSelector((state) => state.countries.openedCountryId);
    const country = useSelector((state) => state.countryDetails.data[openedCountryId]);
    const loading = useSelector((state) => state.countryDetails.loading[openedCountryId]);

    if (loading) {
        return <div className={s.card}>Loading...</div>;
    }

    switch (type) {
        case 'description':
            return (
                <div className={s.card}>{country?.description}</div>
            )
        case 'leader':
            return (
                <div className={s.card}>leader</div>
            )
        case 'vestnik':
            return (
                <div className={s.card}>vestnik</div>
            )
            default:
                return (<div className={s.card}>Default</div>)
    }


}