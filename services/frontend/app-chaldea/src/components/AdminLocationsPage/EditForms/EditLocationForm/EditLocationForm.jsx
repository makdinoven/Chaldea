import React, { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import Input from '../../../CommonComponents/Input/Input';
import LocationSearch from '../../../CommonComponents/LocationSearch/LocationSearch';
import { 
    createLocation, 
    updateLocation, 
    uploadLocationImage,
    updateLocationNeighbors,
    fetchLocationDetails,
    fetchLocationsList,
    fetchAllLocations
} from '../../../../redux/actions/locationEditActions';
import { selectLocationEdit } from '../../../../redux/selectors/locationSelectors';
import s from './EditLocationForm.module.scss';
import LocationNeighborsEditor from './LocationNeighborsEditor/LocationNeighborsEditor';
import { fetchRegionDetails } from '../../../../redux/actions/adminLocationsActions';

const EditLocationForm = ({ locationId = 'new', initialData, onCancel, onSuccess }) => {
    const dispatch = useDispatch();
    const { currentLocation, districtLocations, allLocations } = useSelector(selectLocationEdit);
    
    console.log('EditLocationForm render:', { locationId, initialData, currentLocation });
    
    const [formData, setFormData] = useState({
        name: '',
        district_id: '',
        parent_id: null,
        description: '',
        recommended_level: 1,
        quick_travel_marker: false,
        ...initialData
    });
    
    console.log('formData after initialization:', formData);
    
    const [isUploading, setIsUploading] = useState(false);
    const [selectedImage, setSelectedImage] = useState(null);
    const [imagePreview, setImagePreview] = useState(initialData?.image_url || '');
    const [neighbors, setNeighbors] = useState([]);
    
    useEffect(() => {
        if (locationId !== 'new') {
            dispatch(fetchLocationDetails(locationId));
        }
    }, [dispatch, locationId]);

    useEffect(() => {
        if (locationId !== 'new' && formData.district_id) {
            dispatch(fetchLocationsList(formData.district_id));
        }
    }, [dispatch, formData.district_id, locationId]);

    useEffect(() => {
        dispatch(fetchAllLocations());
    }, [dispatch]);

    useEffect(() => {
        console.log('districtLocations:', districtLocations);
    }, [districtLocations]);

    useEffect(() => {
        if (currentLocation && locationId !== 'new') {
            console.log('Setting formData from currentLocation:', currentLocation);
            setFormData({
                ...currentLocation,
                recommended_level: currentLocation.recommended_level || 1,
                parent_id: currentLocation.parent_id || null
            });
            if (Array.isArray(currentLocation.neighbors)) {
                setNeighbors(currentLocation.neighbors.map(n => ({
                    neighbor_id: n.neighbor_id,
                    energy_cost: n.energy_cost || 1
                })));
            } else {
                setNeighbors([]);
            }
        }
    }, [currentLocation, locationId]);

    const handleChange = (e) => {
        console.log('handleChange called:', e.target.name, e.target.value);
        if (!e.target || !e.target.name) {
            console.error('Invalid event in handleChange:', e);
            return;
        }
        const { name, value, type } = e.target;
        setFormData(prev => {
            const newData = {
                ...prev,
                [name]: type === 'number' ? (value === '' ? '' : Number(value)) : value
            };
            console.log('Updated formData:', newData);
            return newData;
        });
    };

    // Обновленный обработчик для изменения родительской локации,
    // который ожидает объект события с target (name и value)
    const handleParentChange = (e) => {
        console.log('handleParentChange called:', e.target.name, e.target.value);
        const { value } = e.target;
        setFormData(prev => ({
            ...prev,
            parent_id: value ? Number(value) : null
        }));
    };

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onloadend = () => {
                setSelectedImage(file);
                setImagePreview(reader.result);
            };
            reader.readAsDataURL(file);
        }
    };

    const handleNeighborAdd = (neighbor) => {
        if (!neighbor || neighbors.some(n => n.neighbor_id === neighbor.neighbor_id)) return;
        setNeighbors(prev => [...prev, neighbor]);
    };

    const handleNeighborRemove = (neighborId) => {
        setNeighbors(prev => prev.filter(n => n.neighbor_id !== neighborId));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (isUploading) return;
    
        if (!formData.name || !formData.district_id) {
            console.error('Не заполнены обязательные поля');
            return;
        }
    
        setIsUploading(true);
        try {
            const { parent_id, ...restFormData } = formData;
            const locationData = {
                ...restFormData,
                ...(parent_id ? { parent_id: Number(parent_id) } : {}),
                recommended_level: formData.recommended_level ? Number(formData.recommended_level) : 1,
                type: 'location',
                quick_travel_marker: Boolean(formData.quick_travel_marker),
                district_id: Number(formData.district_id)
            };
    
            console.log('Подготовленные данные для отправки:', locationData);
    
            const action = locationId !== 'new' ? updateLocation : createLocation;
            const result = await dispatch(action(locationData)).unwrap();
    
            if (locationId === 'new' && formData.parent_id) {
                try {
                    await dispatch(updateLocation({
                        id: formData.parent_id,
                        type: 'subdistrict'
                    })).unwrap();
                    console.log('Тип родительской локации обновлен на subdistrict');
                } catch (error) {
                    console.error('Ошибка при обновлении типа родителя:', error);
                }
            }
    
            if (selectedImage) {
                try {
                    await dispatch(uploadLocationImage({
                        locationId: result.id,
                        file: selectedImage
                    })).unwrap();
                    console.log('Изображение успешно загружено');
                } catch (imageError) {
                    console.error('Ошибка при загрузке изображения:', imageError);
                }
            }
    
            if (locationId !== 'new' && neighbors.length > 0) {
                try {
                    await dispatch(updateLocationNeighbors({
                        locationId: result.id,
                        neighbors: neighbors
                    })).unwrap();
                    console.log('Соседи успешно обновлены');
                } catch (neighborError) {
                    console.error('Ошибка при обновлении соседей:', neighborError);
                }
            } else {
                console.log('Нет соседей для обновления');
            }
    
            onSuccess(formData.district_id, dispatch);
        } catch (error) {
            console.error('Ошибка при сохранении локации:', error);
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className={s.edit_location_form}>
            <h2>{initialData?.id ? 'ИЗМЕНЕНИЕ ЛОКАЦИИ' : 'СОЗДАНИЕ ЛОКАЦИИ'}</h2>
            
            <form onSubmit={handleSubmit}>
                <div className={s.form_section}>
                    <h3>Основная информация</h3>
                    
                    <div className={s.form_group}>
                        <label>НАЗВАНИЕ:</label>
                        <input
                            type="text"
                            name="name"
                            value={formData.name || ''}
                            onChange={handleChange}
                            required
                            className={s.input}
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>ОПИСАНИЕ:</label>
                        <textarea
                            name="description"
                            value={formData.description || ''}
                            onChange={handleChange}
                            rows={4}
                            className={s.textarea}
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>РЕКОМЕНДУЕМЫЙ УРОВЕНЬ:</label>
                        <input
                            type="number"
                            name="recommended_level"
                            value={formData.recommended_level || ''}
                            onChange={handleChange}
                            min="1"
                            className={s.input}
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>РОДИТЕЛЬСКАЯ ЛОКАЦИЯ:</label>
                        <LocationSearch
                            name="parent_id"
                            value={formData.parent_id}
                            onChange={handleParentChange}
                            locations={allLocations || []}
                            placeholder="Выберите родительскую локацию (необязательно)"
                            allowClear={true}
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>ИЗОБРАЖЕНИЕ:</label>
                        <input
                            type="file"
                            accept="image/*"
                            onChange={handleFileChange}
                        />
                        {(imagePreview || formData.image_url) && (
                            <div className={s.image_preview}>
                                <img src={imagePreview || formData.image_url} alt="Preview" />
                            </div>
                        )}
                    </div>
                </div>

                {locationId !== 'new' && (
                    <div className={s.form_section}>
                        <h3>Соседние локации</h3>
                        <LocationNeighborsEditor
                            formData={formData}
                            onChange={handleChange}
                            neighbors={neighbors}
                            onAdd={handleNeighborAdd}
                            onRemove={handleNeighborRemove}
                        />
                    </div>
                )}

                <div className={s.form_actions}>
                    <button type="button" onClick={onCancel} className={s.cancel_button}>
                        Отмена
                    </button>
                    <button type="submit" className={s.submit_button} disabled={isUploading}>
                        {isUploading ? 'Сохранение...' : 'Сохранить'}
                    </button>
                </div>
            </form>
        </div>
    );
};

export default EditLocationForm;
