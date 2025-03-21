import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { 
    createRegion, 
    updateRegion, 
    fetchRegionDetails,
    uploadRegionImage,
    uploadRegionMap 
} from '../../../../redux/actions/regionEditActions';
import { fetchAllLocations } from '../../../../redux/actions/locationEditActions';
import Input from '../../../CommonComponents/Input/Input';
import Textarea from '../../../CommonComponents/Textarea/Textarea';
import s from './EditRegionForm.module.scss';
import { resetRegionEditState } from '../../../../redux/slices/regionEditSlice';
import LocationSearch from '../../../CommonComponents/LocationSearch/LocationSearch';
import { selectRegionEdit, selectAdminLocations } from '../../../../redux/selectors/locationSelectors';

function EditRegionForm({ regionId = 'new', initialCountryId, onCancel, onSuccess }) {
    const dispatch = useDispatch();
    const { loading, error, currentRegion } = useSelector(selectRegionEdit);
    const { countries } = useSelector(selectAdminLocations);
    const { allLocations } = useSelector(state => state.locationEdit);

    const [formData, setFormData] = useState({
        name: '',
        description: '',
        country_id: initialCountryId || '',
        entrance_location_id: '',
        leader_id: '',
        x: '',
        y: '',
        type: 'region',
        status: 'active'
    });

    const [selectedImage, setSelectedImage] = useState(null);
    const [selectedMap, setSelectedMap] = useState(null);
    const [imagePreview, setImagePreview] = useState(null);
    const [mapPreview, setMapPreview] = useState(null);
    const [isUploading, setIsUploading] = useState(false);

    // Загружаем детали региона (если редактирование) и все локации при монтировании
    useEffect(() => {
        if (regionId !== 'new') {
            dispatch(fetchRegionDetails(regionId));
        }
        dispatch(fetchAllLocations());
    }, [dispatch, regionId]);

    // Обновляем состояние формы при получении текущего региона
    useEffect(() => {
        if (currentRegion && regionId !== 'new') {
            setFormData({
                name: currentRegion.name || '',
                description: currentRegion.description || '',
                country_id: currentRegion.country_id || initialCountryId || '',
                entrance_location_id: currentRegion.entrance_location_id || '',
                leader_id: currentRegion.leader_id || '',
                x: currentRegion.x || '',
                y: currentRegion.y || '',
                type: currentRegion.type || 'region',
                status: currentRegion.status || 'active'
            });
            setImagePreview(currentRegion.image_url);
            setMapPreview(currentRegion.map_image_url);
        }
    }, [currentRegion, regionId, initialCountryId]);

    // Сброс состояния при размонтировании формы
    useEffect(() => {
        return () => {
            dispatch(resetRegionEditState());
        };
    }, [dispatch]);

    const handleChange = (e) => {
        const { name, value, type, id } = e.target;
        const fieldName = name || id; // Используем name, если есть, иначе id
        setFormData(prev => ({
            ...prev,
            [fieldName]: type === 'number' ? (value === '' ? '' : Number(value)) : value
        }));
    };

    const handleFileChange = (e, type) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onloadend = () => {
                if (type === 'image') {
                    setSelectedImage(file);
                    setImagePreview(reader.result);
                } else {
                    setSelectedMap(file);
                    setMapPreview(reader.result);
                }
            };
            reader.readAsDataURL(file);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (isUploading) return;

        // Проверяем обязательные поля
        if (!formData.name || !formData.country_id) {
            console.error('Не заполнены обязательные поля');
            return;
        }

        // Преобразуем данные
        const regionData = {
            name: formData.name,
            description: formData.description,
            country_id: Number(formData.country_id),
            entrance_location_id: formData.entrance_location_id ? Number(formData.entrance_location_id) : null,
            leader_id: formData.leader_id ? Number(formData.leader_id) : null,
            x: formData.x !== '' ? Number(formData.x) : 0,
            y: formData.y !== '' ? Number(formData.y) : 0,
            map_image_url: formData.map_image_url || null,
            image_url: formData.image_url || null
        };

        setIsUploading(true);
        try {
            const action = regionId === 'new' ? createRegion : updateRegion;
            const dataToSend = regionId === 'new' ? regionData : { id: regionId, ...regionData };
            
            console.log('Отправляемые данные:', dataToSend);
            
            const result = await dispatch(action(dataToSend)).unwrap();
            const newRegionId = regionId === 'new' ? result.id : regionId;

            if (selectedImage) {
                await dispatch(uploadRegionImage({ 
                    regionId: newRegionId, 
                    file: selectedImage 
                })).unwrap();
            }

            if (selectedMap) {
                await dispatch(uploadRegionMap({ 
                    regionId: newRegionId, 
                    file: selectedMap 
                })).unwrap();
            }

            onSuccess?.();
        } catch (error) {
            console.error('Error saving region:', error);
            if (error.response) {
                console.error('Response data:', error.response.data);
                console.error('Response status:', error.response.status);
            }
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className={s.edit_region_form}>
            <h2>{regionId === 'new' ? 'СОЗДАНИЕ РЕГИОНА' : 'ИЗМЕНЕНИЕ РЕГИОНА'}</h2>
            
            <form onSubmit={handleSubmit}>
                <div className={s.form_section}>
                    <h3>Основная информация</h3>
                    
                    <div className={s.form_group}>
                        <label>НАЗВАНИЕ:</label>
                        <Input
                            id="name"
                            name="name"
                            text="Введите название региона"
                            value={formData.name}
                            onChange={handleChange}
                            required
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>СТРАНА:</label>
                        <select
                            name="country_id"
                            value={formData.country_id}
                            onChange={handleChange}
                            required
                        >
                            <option value="">Выберите страну</option>
                            {countries.map(country => (
                                <option key={country.id} value={country.id}>
                                    {country.name}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className={s.form_group}>
                        <label>ВХОДНАЯ ЛОКАЦИЯ:</label>
                        <LocationSearch
                            name="entrance_location_id"
                            value={formData.entrance_location_id}
                            onChange={handleChange}
                            countryId={formData.country_id}
                            locations={allLocations} 
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>ПРАВИТЕЛЬ:</label>
                        <select
                            name="leader_id"
                            value={formData.leader_id}
                            onChange={handleChange}
                        >
                            <option value="">Выберите правителя</option>
                            <option value="1">Беорик</option>
                            {/* Здесь будет список правителей */}
                        </select>
                    </div>

                    <div className={s.form_group}>
                        <label>ОПИСАНИЕ:</label>
                        <Textarea
                            id="description"
                            name="description"
                            text="Описание региона"
                            value={formData.description}
                            onChange={handleChange}
                            required
                        />
                    </div>
                </div>

                <div className={s.form_section}>
                    <h3>Координаты на карте</h3>
                    <div className={s.coordinates}>
                        <div className={s.coordinate_input}>
                            <label>X:</label>
                            <Input
                                type="number"
                                id="x"
                                name="x"
                                value={formData.x}
                                onChange={handleChange}
                                required
                            />
                        </div>
                        <div className={s.coordinate_input}>
                            <label>Y:</label>
                            <Input
                                type="number"
                                id="y"
                                name="y"
                                value={formData.y}
                                onChange={handleChange}
                                required
                            />
                        </div>
                    </div>
                </div>

                <div className={s.form_section}>
                    <h3>Изображения</h3>
                    <div className={s.form_group}>
                        <label>ИЗОБРАЖЕНИЕ РЕГИОНА:</label>
                        <input
                            type="file"
                            accept="image/*"
                            onChange={(e) => handleFileChange(e, 'image')}
                        />
                        {imagePreview && (
                            <img src={imagePreview} alt="Preview" className={s.image_preview} />
                        )}
                    </div>

                    <div className={s.form_group}>
                        <label>КАРТА РЕГИОНА:</label>
                        <input
                            type="file"
                            accept="image/*"
                            onChange={(e) => handleFileChange(e, 'map')}
                        />
                        {mapPreview && (
                            <img src={mapPreview} alt="Map Preview" className={s.image_preview} />
                        )}
                    </div>
                </div>

                {error && <div className={s.error_message}>{error}</div>}

                <div className={s.form_actions}>
                    <button 
                        type="button" 
                        className={s.cancel_button}
                        onClick={onCancel}
                        disabled={isUploading}
                    >
                        ВЕРНУТЬСЯ К СПИСКУ
                    </button>
                    <button 
                        type="submit" 
                        className={s.submit_button}
                        disabled={isUploading}
                    >
                        {isUploading ? 'ЗАГРУЗКА...' : (regionId === 'new' ? 'СОЗДАТЬ' : 'СОХРАНИТЬ')}
                    </button>
                </div>
            </form>
        </div>
    );
}

export default EditRegionForm;
