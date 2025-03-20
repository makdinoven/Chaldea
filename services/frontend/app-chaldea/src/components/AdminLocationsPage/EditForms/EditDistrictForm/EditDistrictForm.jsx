import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { 
    createDistrict, 
    updateDistrict, 
    fetchDistrictDetails,
    uploadDistrictImage 
} from '../../../../redux/actions/districtEditActions';
import { selectDistrictEdit } from '../../../../redux/selectors/locationSelectors';
import Input from '../../../CommonComponents/Input/Input';
import Textarea from '../../../CommonComponents/Textarea/Textarea';
import LocationSearch from '../../../CommonComponents/LocationSearch/LocationSearch';
import s from './EditDistrictForm.module.scss';
import { resetDistrictEditState } from '../../../../redux/slices/districtEditSlice';

function EditDistrictForm({ districtId = 'new', initialRegionId, onCancel, onSuccess }) {
    const dispatch = useDispatch();
    const { loading, error, currentDistrict } = useSelector(selectDistrictEdit);

    const [formData, setFormData] = useState({
        name: '',
        description: '',
        region_id: initialRegionId || '',
        entrance_location_id: '',
        recommended_level: '',
        x: '',
        y: '',
        image_url: ''
    });

    const [selectedImage, setSelectedImage] = useState(null);
    const [imagePreview, setImagePreview] = useState(null);
    const [isUploading, setIsUploading] = useState(false);

    useEffect(() => {
        if (districtId !== 'new') {
            dispatch(fetchDistrictDetails(districtId));
        }
        return () => {
            dispatch(resetDistrictEditState());
        };
    }, [dispatch, districtId]);

    const handleChange = (e) => {
        const { name, value, type } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'number' ? (value === '' ? '' : Number(value)) : value
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

        if (!formData.name || !formData.region_id) {
            console.error('Не заполнены обязательные поля');
            return;
        }

        setIsUploading(true);
        try {
            const action = districtId !== 'new' ? updateDistrict : createDistrict;
            const dataToSend = districtId !== 'new' ? { id: districtId, ...formData } : formData;
            
            const result = await dispatch(action(dataToSend)).unwrap();
            
            if (selectedImage) {
                await dispatch(uploadDistrictImage({ 
                    districtId: result.id, 
                    file: selectedImage 
                }));
            }

            onSuccess(result);
        } catch (error) {
            console.error('Error saving district:', error);
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
                        <Input
                            name="name"
                            value={formData.name}
                            onChange={handleChange}
                            required
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>ВХОДНАЯ ЛОКАЦИЯ:</label>
                        <LocationSearch
                            name="entrance_location_id"
                            value={formData.entrance_location_id}
                            onChange={handleChange}
                            regionId={formData.region_id}
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>РЕКОМЕНДУЕМЫЙ УРОВЕНЬ:</label>
                        <Input
                            type="number"
                            name="recommended_level"
                            value={formData.recommended_level}
                            onChange={handleChange}
                            required
                        />
                    </div>

                    <div className={s.form_group}>
                        <label>КООРДИНАТЫ:</label>
                        <div className={s.coordinates}>
                            <Input
                                type="number"
                                name="x"
                                value={formData.x}
                                onChange={handleChange}
                                placeholder="X"
                            />
                            <Input
                                type="number"
                                name="y"
                                value={formData.y}
                                onChange={handleChange}
                                placeholder="Y"
                            />
                        </div>
                    </div>

                    <div className={s.form_group}>
                        <label>ОПИСАНИЕ:</label>
                        <Textarea
                            name="description"
                            value={formData.description}
                            onChange={handleChange}
                            required
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