import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchAllLocations } from '../../../../../redux/actions/locationEditActions';
import { selectLocationEdit } from '../../../../../redux/selectors/locationSelectors';
import LocationSearch from '../../../../CommonComponents/LocationSearch/LocationSearch';
import s from './LocationNeighborsEditor.module.scss';

const LocationNeighborsEditor = ({ 
    formData, 
    neighbors, 
    onAdd, 
    onRemove 
}) => {
    const dispatch = useDispatch();
    const { allLocations } = useSelector(selectLocationEdit);
    const [selectedNeighbor, setSelectedNeighbor] = useState('');
    const [energyCost, setEnergyCost] = useState(1);
    const [neighborsList, setNeighborsList] = useState([]);
    
    useEffect(() => {
        dispatch(fetchAllLocations());
    }, [dispatch]);
    
    useEffect(() => {
        if (allLocations && allLocations.length > 0) {
            // Исключаем текущую локацию (formData.id) из списка соседей
            setNeighborsList(allLocations.filter(loc => loc.id !== formData.id));
        }
    }, [allLocations, formData.id]);
    
    // Функция для поиска имени локации по её ID
    const getLocationName = (locationId) => {
        const location = allLocations.find(loc => loc.id === parseInt(locationId));
        return location ? location.name : `Локация #${locationId}`;
    };
    
    // Обновлённый обработчик: если приходит объект события, извлекаем e.target.value
    const handleNeighborSelect = (eOrValue) => {
        let value;
        if (eOrValue && eOrValue.target) {
            value = eOrValue.target.value;
        } else {
            value = eOrValue;
        }
        setSelectedNeighbor(value);
    };
    
    const handleEnergyCostChange = (e) => {
        setEnergyCost(parseInt(e.target.value) || 1);
    };
    
    const handleAddNeighbor = () => {
        if (selectedNeighbor && !neighbors.some(n => n.neighbor_id === parseInt(selectedNeighbor))) {
            onAdd({
                neighbor_id: parseInt(selectedNeighbor),
                energy_cost: energyCost
            });
            setSelectedNeighbor('');
            setEnergyCost(1);
        }
    };
    
    return (
        <div className={s.neighbors_editor}>
            <div className={s.add_neighbor}>
                <div className={s.neighbor_search_container}>
                    <LocationSearch
                        name="neighbor_id"
                        value={selectedNeighbor}
                        onChange={handleNeighborSelect}
                        locations={neighborsList}
                        placeholder="Выберите соседнюю локацию"
                        className={s.neighbor_search}
                    />
                </div>
                
                <div className={s.energy_container}>
                    <input
                        type="number"
                        min="1"
                        value={energyCost}
                        onChange={handleEnergyCostChange}
                        placeholder="Энергия"
                        className={s.energy_input}
                    />
                </div>
                
                <button 
                    type="button" 
                    onClick={handleAddNeighbor}
                    disabled={!selectedNeighbor}
                    className={s.add_button}
                >
                    Добавить
                </button>
            </div>

            <div className={s.neighbors_list}>
                {neighbors.length > 0 ? (
                    neighbors.map((neighbor) => (
                        <div key={neighbor.neighbor_id} className={s.neighbor_item}>
                            <span className={s.location_name}>
                                {getLocationName(neighbor.neighbor_id)}
                            </span>
                            <span className={s.energy_cost}>
                                Энергия: {neighbor.energy_cost}
                            </span>
                            <button
                                type="button"
                                className={s.remove_button}
                                onClick={() => onRemove(neighbor.neighbor_id)}
                            >
                                Удалить
                            </button>
                        </div>
                    ))
                ) : (
                    <div className={s.no_neighbors}>Нет соседних локаций</div>
                )}
            </div>
        </div>
    );
};

export default LocationNeighborsEditor;
