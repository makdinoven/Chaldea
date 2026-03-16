import s from './Map.module.scss';
import {useEffect, useState} from 'react';
import axios from 'axios';
import MapPoint from './MapPoint/MapPoint';
import MapTooltip from './MapTooltip/MapTooltip';
import DetailCard from "../DetailCard/DetailCard";
import {useSelector} from "react-redux";

export default function Map({type}) {
    const [mapBackground, setMapBackground] = useState(null);
    const [activeMapPointId, setActiveMapPointId] = useState(null);

    const openedDropdownId = type === 'country' ?
        useSelector((state) => state.countries.openedCountryId)
        : useSelector((state) => state.regions.openedRegionId);
    const activeDropdown = type === 'country' ?
        useSelector((state) => state.countryDetails.data[openedDropdownId])
        : useSelector((state) => state.regions.data[openedDropdownId]);
    const loading = type === 'country' ?
        useSelector((state) => state.countryDetails.loading[openedDropdownId])
        : useSelector((state) => state.regions.loading[openedDropdownId]);


    const mapPoints = activeDropdown?.regions || activeDropdown?.districts || [];

    const handleMapPointClick = (e, id) => {
        e.stopPropagation();
        setActiveMapPointId(id);
    };

    const handleMapClick = () => {
        setActiveMapPointId(null)
    }

    // установка бэкграунда карты в зависимости от страны
    useEffect(() => {
        if (activeDropdown) {
            activeDropdown?.map_image_url
                ? setMapBackground(activeDropdown.map_image_url)
                : setMapBackground('no-background');
            setActiveMapPointId(null)
        }
    }, [activeDropdown]);

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
            {mapPoints.map((point) => (
                <MapPoint
                    key={point.id}
                    data={point}
                    isActive={activeMapPointId === point.id}
                    handleMapPointClick={(e) => handleMapPointClick(e, point.id)}
                />
            ))}
            {activeMapPointId !== null && (
                <MapTooltip
                    type={"region"}
                    data={mapPoints.find((point) => point.id === activeMapPointId)}
                />
            )}
        </div>
    );
}
