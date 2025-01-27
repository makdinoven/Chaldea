import s from './Map.module.scss';
import { useEffect, useState } from 'react';
import axios from 'axios';
import MapPoint from './MapPoint/MapPoint.jsx';
import MapTooltip from './MapTooltip/MapTooltip.jsx';
import DetailCard from "../DetailCard/DetailCard.jsx";
import {useSelector} from "react-redux";

export default function Map() {
  const [mapBackground, setMapBackground] = useState(null);
  const [activeMapPointId, setActiveMapPointId] = useState(null);

  const openedCountryId = useSelector((state) => state.countries.openedCountryId);
  const country = useSelector((state) => state.countryDetails.data[openedCountryId]);
  const loading = useSelector((state) => state.countryDetails.loading[openedCountryId]);

  const handleMapPointClick = (e, id) => {
    e.stopPropagation();
    setActiveMapPointId(id);
  };

  const handleMapClick = () => {
    setActiveMapPointId(null)
  }

  // установка бэкграунда карты в зависимости от страны
  useEffect(() => {
    if (country) {
      country?.map_image_url
          ? setMapBackground(country.map_image_url)
          : setMapBackground('no-background');
      setActiveMapPointId(null)
    }
  }, [country]);

  // useEffect(() => {
  //   console.log('map rerender');
  // })

  if (loading) {
    return <div className={s.map}>Loading...</div>;
  }

  return (
      <div
          style={{
            backgroundImage: mapBackground ? `url('${mapBackground}')` : 'none',
          }}
          className={s.map}
          onClick={handleMapClick}
      >
        {country?.regions.map((region) => (
            <MapPoint
                key={region.id}
                data={region}
                isActive={activeMapPointId === region.id}
                handleMapPointClick={(e) => handleMapPointClick(e, region.id)}
            />
        ))}
        {activeMapPointId !== null && (
            <MapTooltip
                data={country?.regions.find((region) => region.id === activeMapPointId)}
            />
        )}
      </div>
  );
}
