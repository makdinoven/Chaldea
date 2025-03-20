import { useState, useEffect, useRef } from 'react';
import { useSelector } from 'react-redux';
import { selectLocations } from '../../../redux/selectors/locationSelectors';
import s from './LocationSearch.module.scss';

function LocationSearch({ name, value, onChange, countryId }) {
    const [isOpen, setIsOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const dropdownRef = useRef(null);
    
    // Получаем все локации из всех регионов выбранной страны
    const locations = useSelector(state => selectLocations(state, countryId));

    const filteredLocations = locations.filter(location =>
        location.name.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const selectedLocation = locations.find(loc => loc.id === value);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
                setIsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleSelect = (locationId) => {
        onChange({ target: { name, value: locationId } });
        setIsOpen(false);
        setSearchTerm('');
    };

    return (
        <div className={s.dropdown} ref={dropdownRef}>
            <div 
                className={s.dropdown_header} 
                onClick={() => setIsOpen(!isOpen)}
            >
                {selectedLocation ? selectedLocation.name : 'Выберите локацию'}
            </div>
            
            {isOpen && (
                <div className={s.dropdown_content}>
                    <input
                        type="text"
                        className={s.search_input}
                        placeholder="Поиск локации..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                    />
                    <div className={s.options_list}>
                        {filteredLocations.map(location => (
                            <div
                                key={location.id}
                                className={s.option}
                                onClick={() => handleSelect(location.id)}
                            >
                                {location.name}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

export default LocationSearch;