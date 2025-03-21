import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { 
    createDistrict, 
    updateDistrict, 
    fetchDistrictDetails,
    uploadDistrictImage,
    fetchDistrictLocations
} from '../../../../redux/actions/districtEditActions';
import { fetchAllLocations } from '../../../../redux/actions/locationEditActions';
import { selectDistrictEdit } from '../../../../redux/selectors/locationSelectors';
import Input from '../../../CommonComponents/Input/Input';
import Textarea from '../../../CommonComponents/Textarea/Textarea';
import LocationSearch from '../../../CommonComponents/LocationSearch/LocationSearch';
import s from './EditDistrictForm.module.scss';
import { resetDistrictEditState } from '../../../../redux/slices/districtEditSlice';

function EditDistrictForm({ districtId = 'new', initialRegionId, onCancel, onSuccess }) {
    const dispatch = useDispatch();
    
    const { loading, error, currentDistrict, districtLocations } = useSelector(state => {
        console.log('Redux State:', state.districtEdit);
        return state.districtEdit;
    });

    const [isLoadingLocations, setIsLoadingLocations] = useState(false);
    const [selectedImage, setSelectedImage] = useState(null);
    const [imagePreview, setImagePreview] = useState(null);
    const [isUploading, setIsUploading] = useState(false);

    const [formData, setFormData] = useState({
        name: '',
        description: '',
        region_id: Number(initialRegionId),
        entrance_location_id: '',
        recommended_level: 1,
        x: 0,
        y: 0,
        image_url: ''
    });

    // Загружаем данные при монтировании компонента
    useEffect(() => {
        if (districtId !== 'new') {
            console.log('Fetching district details and locations for ID:', districtId);
            setIsLoadingLocations(true);
            
            Promise.all([
                dispatch(fetchDistrictDetails(districtId)),
                dispatch(fetchDistrictLocations(districtId))
            ]).finally(() => {
                setIsLoadingLocations(false);
            });
        }
    }, [dispatch, districtId]);

    // Обновляем форму при получении данных района
    useEffect(() => {
        if (currentDistrict) {
            console.log('Setting form data from currentDistrict:', currentDistrict);
            setFormData(prev => ({
                ...prev,
                name: currentDistrict.name || '',
                description: currentDistrict.description || '',
                region_id: currentDistrict.region_id,
                entrance_location_id: currentDistrict.entrance_location_id || '',
                recommended_level: currentDistrict.recommended_level || 1,
                x: currentDistrict.x || 0,
                y: currentDistrict.y || 0,
                image_url: currentDistrict.image_url || ''
            }));
            setImagePreview(currentDistrict.image_url);
        }
    }, [currentDistrict]);

    console.log('Current form data:', formData);
    console.log('District locations:', districtLocations);
    console.log('District locations in form:', districtLocations); // Отладка

    // Обработчик для всех остальных полей формы
    const handleChange = (e) => {
        const { name, value, type } = e.target;
        let processedValue = value;
        if (type === 'number') {
            if (name === 'x' || name === 'y') {
                processedValue = value === '' ? 0 : Number(value);
            } else {
                processedValue = value === '' ? '' : Number(value);
            }
        }
        setFormData(prev => ({
            ...prev,
            [name]: processedValue
        }));
    };

    // Отдельный обработчик для выбора входной локации
    const handleEntranceLocationSelect = (eOrValue) => {
        let newValue;
        if (eOrValue && eOrValue.target) {
            newValue = eOrValue.target.value;
        } else {
            newValue = eOrValue;
        }
        setFormData(prev => ({
            ...prev,
            entrance_location_id: newValue
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

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (isUploading) return;

        if (!formData.region_id) {
            console.error('Region ID is missing:', { region_id: formData.region_id, formData });
            return;
        }

        const districtData = {
            name: formData.name,
            description: formData.description || '',
            region_id: Number(formData.region_id),
            entrance_location_id: formData.entrance_location_id ? Number(formData.entrance_location_id) : null,
            recommended_level: formData.recommended_level ? Number(formData.recommended_level) : 1,
            x: formData.x || 0,
            y: formData.y || 0,
            image_url: formData.image_url || ''
        };

        console.log('Sending district data:', districtData);

        try {
            setIsUploading(true);
            const action = districtId === 'new' 
                ? await dispatch(createDistrict(districtData))
                : await dispatch(updateDistrict({ id: districtId, ...districtData }));

            if (action.error) {
                console.error('Server error:', action.payload);
                throw new Error(action.payload?.message || 'Ошибка при сохранении района');
            }

            if (!action.payload) {
                throw new Error('Нет данных в ответе от сервера');
            }

            if (selectedImage) {
                const uploadAction = await dispatch(uploadDistrictImage({
                    districtId: action.payload.id,
                    file: selectedImage
                }));
                
                if (uploadAction.error) {
                    console.error('Image upload error:', uploadAction.payload);
                    throw new Error(uploadAction.payload?.message || 'Ошибка при загрузке изображения');
                }
            }

            onSuccess && onSuccess();
        } catch (error) {
            console.error('Error details:', {
                error,
                message: error.message,
                stack: error.stack,
                response: error.response?.data
            });
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className={s.edit_district_form}>
            <h2>{districtId === 'new' ? 'СОЗДАНИЕ РАЙОНА' : 'ИЗМЕНЕНИЕ РАЙОНА'}</h2>
            
            <form onSubmit={handleSubmit}>
                <div className={s.form_section}>
                    <h3>Основная информация</h3>
                    
                    <div className={s.form_group}>
                        <label>НАЗВАНИЕ:</label>
                        <input
                            type="text"
                            name="name"
                            value={formData.name}
                            onChange={handleChange}
                            required
                            className={s.input}
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>ВХОДНАЯ ЛОКАЦИЯ:</label>
                        <LocationSearch
                            name="entrance_location_id"
                            value={formData.entrance_location_id}
                            onChange={handleEntranceLocationSelect}
                            locations={districtLocations}
                            placeholder="Выберите входную локацию"
                        />
                        <div style={{ fontSize: '12px', color: 'gray' }}>
                            District ID: {districtId}, 
                            Current Location ID: {formData.entrance_location_id},
                            Locations count: {districtLocations?.length}
                        </div>
                    </div>

                    <div className={s.form_group}>
                        <label>РЕКОМЕНДУЕМЫЙ УРОВЕНЬ:</label>
                        <input
                            type="number"
                            name="recommended_level"
                            value={formData.recommended_level}
                            onChange={handleChange}
                            min="1"
                            className={s.input}
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>КООРДИНАТЫ:</label>
                        <div className={s.coordinates}>
                            <input
                                type="number"
                                name="x"
                                value={formData.x}
                                onChange={handleChange}
                                placeholder="X"
                                className={s.input}
                            />
                            <input
                                type="number"
                                name="y"
                                value={formData.y}
                                onChange={handleChange}
                                placeholder="Y"
                                className={s.input}
                            />
                        </div>
                    </div>

                    <div className={s.form_group}>
                        <label>ОПИСАНИЕ:</label>
                        <textarea
                            name="description"
                            value={formData.description}
                            onChange={handleChange}
                            className={s.textarea}
                            rows={4}
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>ИЗОБРАЖЕНИЕ:</label>
                        <input
                            type="file"
                            accept="image/*"
                            onChange={handleFileChange}
                        />
                        {imagePreview && (
                            <img src={imagePreview} alt="Preview" className={s.image_preview} />
                        )}
                    </div>
                </div>

                <div className={s.form_actions}>
                    <button type="submit" disabled={isUploading}>
                        {isUploading ? 'Сохранение...' : 'Сохранить'}
                    </button>
                    <button type="button" onClick={onCancel}>
                        Отмена
                    </button>
                </div>
            </form>
        </div>
    );
}

export default EditDistrictForm;
