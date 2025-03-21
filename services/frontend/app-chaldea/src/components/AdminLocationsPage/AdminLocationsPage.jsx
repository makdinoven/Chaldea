import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useRequireAuth } from '../../hooks/useRequireAuth';
import { fetchCountriesList, fetchCountryDetails, fetchRegionDetails } from '../../redux/actions/adminLocationsActions';
import { deleteCountry } from '../../redux/actions/countryEditActions';
import { deleteRegion } from '../../redux/actions/regionEditActions';
import { selectAdminLocations } from '../../redux/selectors/locationSelectors';

import s from './AdminLocationsPage.module.scss';
import EditCountryForm from './EditForms/EditCountryForm/EditCountryForm';
import EditRegionForm from './EditForms/EditRegionForm/EditRegionForm';
import EditDistrictForm from './EditForms/EditDistrictForm/EditDistrictForm';
import EditLocationForm from './EditForms/EditLocationForm/EditLocationForm';

const AdminLocationsPage = () => {
    useRequireAuth();
    const dispatch = useDispatch();
    const { countries, countryDetails, regionDetails, loading, error } = useSelector(selectAdminLocations);
    
    const [editingCountry, setEditingCountry] = useState(null);
    const [editingRegion, setEditingRegion] = useState(null);
    const [editingDistrict, setEditingDistrict] = useState(null);
    const [openedCountries, setOpenedCountries] = useState({});
    const [openedRegions, setOpenedRegions] = useState({});
    const [openedDistricts, setOpenedDistricts] = useState({});
    const [editingItem, setEditingItem] = useState(null);

    useEffect(() => {
        dispatch(fetchCountriesList());
    }, [dispatch]);

    const toggleCountry = (countryId) => {
        setOpenedCountries(prev => ({
            ...prev,
            [countryId]: !prev[countryId]
        }));
        if (!countryDetails[countryId]) {
            dispatch(fetchCountryDetails(countryId));
        }
    };

    const handleAddNewCountry = () => {
        setEditingCountry({});
    };

    const handleEditCountry = (e, country) => {
        e.stopPropagation();
        setEditingCountry(country);
    };

    const handleDeleteCountry = async (e, countryId) => {
        e.stopPropagation();
        if (window.confirm('Вы уверены, что хотите удалить эту страну?')) {
            await dispatch(deleteCountry(countryId));
            dispatch(fetchCountriesList());
        }
    };

    const handleAddNewRegion = (countryId) => {
        setEditingRegion({ country_id: countryId });
    };

    const handleEditRegion = (e, region) => {
        e.stopPropagation();
        setEditingRegion(region);
    };

    const handleDeleteRegion = async (e, regionId) => {
        e.stopPropagation();
        if (window.confirm('Вы уверены, что хотите удалить этот регион?')) {
            await dispatch(deleteRegion(regionId));
            dispatch(fetchCountriesList());
        }
    };

    const toggleRegion = (e, regionId) => {
        e.stopPropagation();
        setOpenedRegions(prev => ({
            ...prev,
            [regionId]: !prev[regionId]
        }));
        if (!regionDetails[regionId]) {
            dispatch(fetchRegionDetails(regionId));
        }
    };

    const toggleDistrict = (e, districtId) => {
        e.stopPropagation();
        setOpenedDistricts(prev => ({
            ...prev,
            [districtId]: !prev[districtId]
        }));
    };

    const handleAddDistrict = (e, regionId) => {
        e.stopPropagation();
        setEditingDistrict({ id: 'new', initialRegionId: regionId });
    };

    const handleEditDistrict = (e, district) => {
        e.stopPropagation();
        setEditingDistrict(district);
    };

    const handleDeleteDistrict = async (e, districtId) => {
        e.stopPropagation();
        if (window.confirm('Вы уверены, что хотите удалить этот район?')) {
            await dispatch(deleteDistrict(districtId));
            dispatch(fetchCountriesList());
        }
    };

    const handleOverlayClick = (e, closeForm) => {
        if (e.target === e.currentTarget) {
            closeForm();
        }
    };

    const handleEditLocation = (e, location) => {
        e.stopPropagation();
        setEditingItem({
            type: 'location',
            id: location.id,
            data: location
        });
    };

    const handleAddLocation = (e, districtId) => {
        e.preventDefault();
        e.stopPropagation();
        setEditingItem({
            type: 'location',
            id: 'new',
            data: { district_id: districtId }
        });
    };

    const renderLocationsRecursively = (location) => (
        <div key={location.id}>
            <div className={`${s.location_item} ${s.location}`}>
                <div>{location.id}</div>
                <div>{location.name}</div>
                <div>{location.type}</div>
                <div className={s.actions}>
                    <button 
                        className={s.edit_button} 
                        onClick={(e) => handleEditLocation(e, location)}
                    >
                        Изменить
                    </button>
                    <button className={s.delete_button}>Удалить</button>
                </div>
            </div>
            {location.children && location.children.length > 0 && (
                <div className={s.nested_container}>
                    {location.children.map(child => renderLocationsRecursively(child))}
                </div>
            )}
        </div>
    );

    if (error) return <div className={s.error}>Ошибка: {error}</div>;
    if (loading && !countries?.length) return <div className={s.loading}>Загрузка списка стран...</div>;

    
    return (
        <div className={s.admin_page}>
            <h1>Управление локациями</h1>
            <div className={s.locations_list}>
                <button className={s.add_button} onClick={() => setEditingCountry('new')}>
                    Добавить страну
                </button>

                {countries?.map((country) => (
                    <div key={country.id} className={s.country_container}>
                        <div className={s.country_header} onClick={() => toggleCountry(country.id)}>
                            <span className={s.country_name}>{country.name}</span>
                            <div className={s.header_controls}>
                                <button className={s.edit_button} onClick={(e) => handleEditCountry(e, country)}>
                                    Редактировать
                                </button>
                                <button className={s.delete_button} onClick={(e) => handleDeleteCountry(e, country.id)}>
                                    Удалить
                                </button>
                                <span className={`${s.arrow} ${openedCountries[country.id] ? s.open : ''}`}>▼</span>
                            </div>
                        </div>

                        {openedCountries[country.id] && countryDetails[country.id] && (
                            <div className={s.regions_container}>
                                <button className={s.add_region_button} onClick={() => handleAddNewRegion(country.id)}>
                                    Добавить регион
                                </button>

                                {countryDetails[country.id].regions?.map((region) => (
                                    <div key={region.id}>
                                        <div 
                                            className={`${s.location_item} ${s.region}`} 
                                            onClick={(e) => toggleRegion(e, region.id)}
                                        >
                                            <div>{region.id}</div>
                                            <div>{region.name}</div>
                                            <div>Регион</div>
                                            <div className={s.actions}>
                                                <button className={s.edit_button} onClick={(e) => handleEditRegion(e, region)}>
                                                    Изменить
                                                </button>
                                                <button className={s.delete_button} onClick={(e) => handleDeleteRegion(e, region.id)}>
                                                    Удалить
                                                </button>
                                                <button className={s.add_district_button} onClick={(e) => handleAddDistrict(e, region.id)}>
                                                    Добавить район
                                                </button>
                                                <span className={`${s.arrow} ${openedRegions[region.id] ? s.open : ''}`}>▼</span>
                                            </div>
                                        </div>

                                        {openedRegions[region.id] && regionDetails[region.id] && (
                                            <div className={s.nested_container}>
                                                {regionDetails[region.id].districts?.map((district) => (
                                                    <div key={district.id}>
                                                        <div 
                                                            className={`${s.location_item} ${s.district}`}
                                                            onClick={(e) => toggleDistrict(e, district.id)}
                                                        >
                                                            <div>{district.id}</div>
                                                            <div>{district.name}</div>
                                                            <div>Район</div>
                                                            <div className={s.actions}>
                                                                <button className={s.edit_button} onClick={(e) => handleEditDistrict(e, district)}>
                                                                    Изменить
                                                                </button>
                                                                <button className={s.delete_button} onClick={(e) => handleDeleteDistrict(e, district.id)}>
                                                                    Удалить
                                                                </button>
                                                                <button 
                                                                    className={s.add_location_button} 
                                                                    onClick={(e) => handleAddLocation(e, district.id)}
                                                                    type="button"
                                                                >
                                                                    Добавить локацию
                                                                </button>
                                                                <span className={`${s.arrow} ${openedDistricts[district.id] ? s.open : ''}`}>▼</span>
                                                            </div>
                                                        </div>

                                                        {openedDistricts[district.id] && (
                                                            <div className={s.nested_container}>
                                                                {district.locations?.map((loc) => renderLocationsRecursively(loc))}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ))}

                {editingCountry && (
                    <div 
                        className={s.edit_form_container} 
                        onClick={(e) => handleOverlayClick(e, () => setEditingCountry(null))}
                    >
                        <EditCountryForm
                            initialData={editingCountry}
                            onCancel={() => setEditingCountry(null)}
                            onSuccess={() => {
                                setEditingCountry(null);
                                dispatch(fetchCountriesList());
                            }}
                        />
                    </div>
                )}

{editingRegion && (
    <div 
        className={s.edit_form_container} 
        onClick={(e) => handleOverlayClick(e, () => setEditingRegion(null))}
    >
        <EditRegionForm
            regionId={editingRegion.id || 'new'}
            initialCountryId={editingRegion.country_id}
            initialData={editingRegion}
            onCancel={() => setEditingRegion(null)}
            onSuccess={() => {
                setEditingRegion(null);
                dispatch(fetchCountriesList());
            }}
        />
    </div>
)}


                {editingDistrict && (
                    <div 
                        className={s.edit_form_container} 
                        onClick={(e) => handleOverlayClick(e, () => setEditingDistrict(null))}
                    >
                        <EditDistrictForm
                            districtId={editingDistrict.id || 'new'}
                            initialRegionId={editingDistrict.initialRegionId}
                            onCancel={() => setEditingDistrict(null)}
                            onSuccess={() => {
                                setEditingDistrict(null);
                                dispatch(fetchCountriesList());
                            }}
                        />
                    </div>
                )}

                {editingItem && editingItem.type === 'location' && (
                    <div 
                        className={s.edit_form_container} 
                        onClick={(e) => handleOverlayClick(e, () => setEditingItem(null))}
                    >
                        <EditLocationForm
                            locationId={editingItem.id}
                            initialData={editingItem.data}
                            onCancel={() => setEditingItem(null)}
                            onSuccess={() => {
                                setEditingItem(null);
                                // Перезагружаем страницу
                                window.location.reload();
                            }}
                        />
                    </div>
                )}
            </div>
        </div>
    );
};

export default AdminLocationsPage;
