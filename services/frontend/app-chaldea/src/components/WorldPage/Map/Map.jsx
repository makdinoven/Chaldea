import s from './Map.module.scss';
import { useEffect, useState } from 'react';
import axios from 'axios';
import MapPoint from './MapPoint/MapPoint.jsx';
import MapTooltip from './MapTooltip/MapTooltip.jsx';

export default function Map({ countryId }) {
  const [country, setCountry] = useState(null);
  const [regions, setRegions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [mapBackground, setMapBackground] = useState(null);
  const [activeMapPointId, setActiveMapPointId] = useState(null);

  const loadRegions = (id) => {
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
  };

  const handleMapPointClick = (e, id) => {
    e.stopPropagation();
    setActiveMapPointId(id);
  };

  //подгрузка регионов при изменении страны
  useEffect(() => {
    if (countryId) {
      loadRegions(countryId);
    }
  }, [countryId]);

  // подгрузка бэкграунда карты в зависимости от страны
  useEffect(() => {
    country?.map_image_url
      ? setMapBackground(country.map_image_url)
      : setMapBackground('no-background');
      setActiveMapPointId(null)
    // console.log(country);
  }, [country]);

  return (
    <>
      {loading ? (
        'Loading...'
      ) : (
        <div
          style={{
            backgroundImage: mapBackground ? `url('${mapBackground}')` : 'none',
          }}
          className={s.map}
          onClick={() => setActiveMapPointId(null)}
        >
          {regions.map((region) => (
            <MapPoint
              key={region.id}
              data={region}
              isActive={activeMapPointId === region.id}
              handleMapPointClick={(e) => handleMapPointClick(e, region.id)}
            />
          ))}
            {activeMapPointId !== null && (
                <MapTooltip
                    data={regions.find((region) => region.id === activeMapPointId)}
                />
            )}
        </div>
      )}
    </>
  );
}
