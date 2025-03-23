import React, { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
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

const EditLocationForm = ({ locationId = 'new', initialData, onCancel, onSuccess }) => {
    const dispatch = useDispatch();
    const { currentLocation, districtLocations, allLocations } = useSelector(selectLocationEdit);

    // ------------------------
    //   Локальный стейт
    // ------------------------
    const [formData, setFormData] = useState({
        name: '',
        district_id: '',
        parent_id: null,
        description: '',
        recommended_level: 1,
        quick_travel_marker: false, // по умолчанию false
        ...initialData
    });

    const [isUploading, setIsUploading] = useState(false);
    const [selectedImage, setSelectedImage] = useState(null);
    const [imagePreview, setImagePreview] = useState(initialData?.image_url || '');

    // Список соседей (neighbor_id, energy_cost)
    const [neighbors, setNeighbors] = useState([]);

    // ------------------------
    //   Эффекты
    // ------------------------
    useEffect(() => {
        // Если редактируем существующую локацию, подгружаем её детали
        if (locationId !== 'new') {
            dispatch(fetchLocationDetails(locationId));
        }
    }, [dispatch, locationId]);

    useEffect(() => {
        // Если у нас уже есть district_id, грузим все локации этого района
        if (locationId !== 'new' && formData.district_id) {
            dispatch(fetchLocationsList(formData.district_id));
        }
    }, [dispatch, formData.district_id, locationId]);

    // Список всех локаций (для LocationSearch)
    useEffect(() => {
        dispatch(fetchAllLocations());
    }, [dispatch]);

    // Когда подгрузились детали текущей локации — заполняем форму
    useEffect(() => {
        if (currentLocation && locationId !== 'new') {
            setFormData({
                ...currentLocation,
                recommended_level: currentLocation.recommended_level || 1,
                parent_id: currentLocation.parent_id || null,
                quick_travel_marker: currentLocation.quick_travel_marker ?? false
            });
            if (Array.isArray(currentLocation.neighbors)) {
                setNeighbors(
                    currentLocation.neighbors.map(n => ({
                        neighbor_id: n.neighbor_id,
                        energy_cost: n.energy_cost || 1
                    }))
                );
            } else {
                setNeighbors([]);
            }
        }
    }, [currentLocation, locationId]);

    // ------------------------
    //   Обработчики полей
    // ------------------------
    const handleChange = (e) => {
        if (!e.target || !e.target.name) return;
        const { name, value, type } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: (type === 'number')
                ? (value === '' ? '' : Number(value))
                : value
        }));
    };

    const handleParentChange = (e) => {
        const { value } = e.target;
        setFormData(prev => ({
            ...prev,
            parent_id: value ? Number(value) : null
        }));
    };

    const handleQuickTravelChange = (e) => {
        setFormData(prev => ({
            ...prev,
            quick_travel_marker: e.target.checked
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

    // ------------------------
    //   Обработчики соседей
    // ------------------------
    const handleNeighborAdd = (neighbor) => {
        // Если уже есть такой neighbor_id, пропускаем
        if (!neighbor || neighbors.some(n => n.neighbor_id === neighbor.neighbor_id)) return;
        setNeighbors(prev => [...prev, neighbor]);
    };
    const handleNeighborRemove = (neighborId) => {
        setNeighbors(prev => prev.filter(n => n.neighbor_id !== neighborId));
    };

    // ------------------------
    //   Сабмит формы
    // ------------------------
    const handleSubmit = async (e) => {
        e.preventDefault();
        if (isUploading) return;

        if (!formData.name || !formData.district_id) {
            console.error('Не заполнены обязательные поля: name, district_id');
            return;
        }

        setIsUploading(true);
        try {
            // Подготавливаем данные для локации
            const { parent_id, ...rest } = formData;
            const locationData = {
                ...rest,
                ...(parent_id ? { parent_id: Number(parent_id) } : {}),
                recommended_level: formData.recommended_level
                    ? Number(formData.recommended_level)
                    : 1,
                type: 'location',
                quick_travel_marker: Boolean(formData.quick_travel_marker),
                district_id: Number(formData.district_id)
            };

            // Если это создание или редактирование
            const action = (locationId !== 'new') ? updateLocation : createLocation;
            const result = await dispatch(action(locationData)).unwrap();

            // Если у новой локации есть parent_id -> переводим родителя в type='subdistrict'
            if (locationId === 'new' && formData.parent_id) {
                try {
                    await dispatch(updateLocation({
                        id: formData.parent_id,
                        type: 'subdistrict'
                    })).unwrap();
                } catch (error) {
                    console.error('Ошибка при обновлении типа родителя:', error);
                }
            }

            // Загрузка изображения, если выбрали
            if (selectedImage) {
                try {
                    await dispatch(uploadLocationImage({
                        locationId: result.id, // id созданной/обновленной локации
                        file: selectedImage
                    })).unwrap();
                } catch (imgError) {
                    console.error('Ошибка при загрузке изображения:', imgError);
                }
            }

            // --- Обновляем соседей (если есть) ---
            // Локация может быть новой => берем result.id
            const newLocationId = locationId === 'new' ? result.id : locationId;
            if (neighbors.length > 0) {
                try {
                    // Вызываем роут обновления (или создания) соседей
                    await dispatch(updateLocationNeighbors({
                        locationId: newLocationId,
                        neighbors
                    })).unwrap();
                    console.log('Соседи успешно обновлены');
                } catch (neighborError) {
                    console.error('Ошибка при обновлении соседей:', neighborError);
                }
            }

            // Финальный колбэк
            onSuccess(formData.district_id, dispatch);
        } catch (error) {
            console.error('Ошибка при сохранении локации:', error);
        } finally {
            setIsUploading(false);
        }
    };

    // ------------------------
    //   Рендер
    // ------------------------
    return (
        <div className={s.edit_location_form}>
            <h2>
                {locationId !== 'new'
                    ? 'ИЗМЕНЕНИЕ ЛОКАЦИИ'
                    : 'СОЗДАНИЕ ЛОКАЦИИ'
                }
            </h2>

            <form onSubmit={handleSubmit}>
                <div className={s.form_section}>
                    <h3>Основная информация</h3>

                    {/* Название */}
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

                    {/* Описание */}
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

                    {/* Рекомендуемый уровень */}
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

                    {/* Чекбокс "быстрый переход" */}
                    <div className={s.form_group}>
                        <label>
                            <input
                                type="checkbox"
                                name="quick_travel_marker"
                                checked={formData.quick_travel_marker}
                                onChange={handleQuickTravelChange}
                            />
                            &nbsp;Возможность быстрого перехода
                        </label>
                    </div>

                    {/* Родительская локация */}
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

                    {/* Загрузка изображения */}
                    <div className={s.form_group}>
                        <label>ИЗОБРАЖЕНИЕ:</label>
                        <input
                            type="file"
                            accept="image/*"
                            onChange={handleFileChange}
                        />
                        {(imagePreview || formData.image_url) && (
                            <div className={s.image_preview}>
                                <img
                                    src={imagePreview || formData.image_url}
                                    alt="Preview"
                                />
                            </div>
                        )}
                    </div>
                </div>

                {/*
                  УБРАЛИ условие `locationId !== 'new'`
                  - теперь при создании тоже можно выбирать соседей.
                */}
                <div className={s.form_section}>
                    <h3>Соседние локации</h3>
                    <LocationNeighborsEditor
                        formData={formData}
                        neighbors={neighbors}
                        onAdd={handleNeighborAdd}
                        onRemove={handleNeighborRemove}
                    />
                </div>

                <div className={s.form_actions}>
                    <button
                        type="button"
                        onClick={onCancel}
                        className={s.cancel_button}
                    >
                        Отмена
                    </button>
                    <button
                        type="submit"
                        className={s.submit_button}
                        disabled={isUploading}
                    >
                        {isUploading ? 'Сохранение...' : 'Сохранить'}
                    </button>
                </div>
            </form>
        </div>
    );
};

export default EditLocationForm;
