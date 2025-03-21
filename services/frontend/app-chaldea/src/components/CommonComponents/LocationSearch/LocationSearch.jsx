import React, { useState, useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchDistrictLocations } from '../../../redux/actions/locationEditActions';
import s from './LocationSearch.module.scss';

const LocationSearch = ({ 
    name, 
    value, 
    onChange, 
    districtId, 
    regionId,
    placeholder = "Выберите локацию",
    className = "",
    locations: passedLocations
}) => {
    const dispatch = useDispatch();
    // Если переданы локации через пропсы, используем их, иначе districtLocations из state
    const defaultLocations = useSelector(state => state.locationEdit.districtLocations);
    const locations = passedLocations || defaultLocations;
    
    const [searchTerm, setSearchTerm] = useState('');
    const [isOpen, setIsOpen] = useState(false);
    const [selectedLocation, setSelectedLocation] = useState(null);
    const searchRef = useRef(null);

    // Если districtId указан и локации не переданы через пропсы, загружаем их
    useEffect(() => {
        if (districtId && !passedLocations) {
            dispatch(fetchDistrictLocations(districtId));
        }
    }, [dispatch, districtId, passedLocations]);

    useEffect(() => {
        if (value) {
            const location = locations.find(loc => loc.id === parseInt(value));
            setSelectedLocation(location);
        } else {
            setSelectedLocation(null);
        }
    }, [value, locations]);

    const handleSearchChange = (e) => {
        setSearchTerm(e.target.value);
        setIsOpen(true);
    };

    const handleLocationSelect = (locationId) => {
        console.log('Выбрана локация с ID:', locationId);
        setIsOpen(false);
        setSearchTerm('');
        // Передаем искусственный объект события, чтобы родительский handleChange мог корректно его обработать
        setTimeout(() => {
            onChange({ target: { name, value: locationId } });
        }, 0);
    };

    const handleClear = () => {
        setSearchTerm('');
        setIsOpen(false);
        onChange({ target: { name, value: '' } });
    };

    const handleInputClick = () => {
        setIsOpen(true);
    };

    // Закрытие выпадающего списка при клике вне компонента
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (searchRef.current && !searchRef.current.contains(event.target)) {
                setIsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    const filteredLocations = searchTerm
        ? locations.filter(loc => 
            loc.name && loc.name.toLowerCase().includes(searchTerm.toLowerCase()))
        : locations;

    return (
        <div className={`${s.location_search} ${className}`} ref={searchRef}>
            <div className={s.search_input_container}>
                <input
                    type="text"
                    placeholder={selectedLocation ? selectedLocation.name : placeholder}
                    value={searchTerm}
                    onChange={handleSearchChange}
                    onClick={handleInputClick}
                    className={s.search_input}
                />
                {selectedLocation && (
                    <button 
                        type="button" 
                        className={s.clear_button}
                        onClick={handleClear}
                    >
                        ×
                    </button>
                )}
            </div>
            
            {isOpen && (
                <div className={s.dropdown}>
                    {filteredLocations.length > 0 ? (
                        filteredLocations.map(location => (
                            <div
                                key={location.id}
                                className={s.dropdown_item}
                                onClick={() => handleLocationSelect(location.id)}
                            >
                                {location.name}
                            </div>
                        ))
                    ) : (
                        <div className={s.no_results}>Нет результатов</div>
                    )}
                </div>
            )}
            
            {/* Скрытое поле для хранения выбранного значения */}
            <input 
                type="hidden" 
                name={name} 
                value={value || ''} 
            />
        </div>
    );
};

export default LocationSearch;
