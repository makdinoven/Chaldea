import React, { useState } from 'react';
import { useSelector } from 'react-redux';
import s from './DistrictLocationSelect.module.scss';

const DistrictLocationSelect = ({ name, value, onChange, placeholder }) => {
    const { districtLocations } = useSelector(state => state.districtEdit);
    
    // Стейт для поискового запроса
    const [searchTerm, setSearchTerm] = useState('');

    // Отфильтрованный список локаций
    const filteredLocations = districtLocations
        ? districtLocations.filter(location =>
            location.name.toLowerCase().includes(searchTerm.toLowerCase())
          )
        : [];

    return (
        <div className={s.selectWrapper}>
            {/* Поле ввода для поиска */}
            <input
                type="text"
                className={s.searchInput}
                placeholder="Поиск локации..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
            />

            {/* Сам селект, который отображает только отфильтрованные результаты */}
            <select
                name={name}
                value={value || ''}
                onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
                className={s.select}
            >
                <option value="">
                    {placeholder || 'Выберите локацию'}
                </option>
                {filteredLocations.map((location) => (
                    <option key={location.id} value={location.id}>
                        {location.name}
                    </option>
                ))}
            </select>
        </div>
    );
};

export default DistrictLocationSelect;
