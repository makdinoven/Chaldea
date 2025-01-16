import s from './Map.module.scss';
import { useEffect, useState } from 'react';
import axios from 'axios';
import MapPoint from './MapPoint/MapPoint.jsx';

export default function Map({ countryId }) {
    const [country, setCountry] = useState(null);
    const [regions, setRegions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [mapBackground, setMapBackground] = useState(null);

    useEffect(() => {
        if (countryId) {
            loadRegions(countryId);
        }
    }, [countryId]);

    useEffect(() => {
        country?.map_image_url
            ? setMapBackground(country.map_image_url)
            : setMapBackground('no-background');
    }, [country]);

    function loadRegions(id) {
        setLoading(true);
        axios
            .get(`http://localhost:8006/locations/countries/${id}/details`, {
                headers: {
                    Accept: 'application/json',
                },
            })
            .then((response) => {
                setRegions(response.data.regions);
                setCountry(response.data); // Сохраняем объект страны
                setLoading(false);
            })
            .catch((error) => {
                console.error(error);
                setLoading(false);
            });
    }

    return (
        <>
            {loading ? (
                'Loading...'
            ) : (
                <div
                    style={{
                        backgroundImage: mapBackground ? `url(${mapBackground})` : 'none',
                    }}
                    className={s.map}
                >
                    {regions.map((region) => (
                        <MapPoint key={region.id} data={region} />
                    ))}
                </div>
            )}
        </>
    );
}
