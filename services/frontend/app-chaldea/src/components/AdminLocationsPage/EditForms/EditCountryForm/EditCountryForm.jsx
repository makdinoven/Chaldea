import { useState } from 'react';
import { useDispatch } from 'react-redux';
import Input from '../../../CommonComponents/Input/Input';
import Textarea from '../../../CommonComponents/Textarea/Textarea';
// Временно закомментируем проблемный импорт
// import { uploadCountryMap } from '../../../../redux/actions/countryEditActions';
import s from './EditCountryForm.module.scss';
import axios from 'axios';

function EditCountryForm({ initialData, onCancel, onSuccess }) {
    const dispatch = useDispatch();
    const [formData, setFormData] = useState({
        name: initialData?.name || '',
        description: initialData?.description || '',
        map_image_url: initialData?.map_image_url || '',
        leader_id: initialData?.leader_id || null
    });
    
    const [selectedFile, setSelectedFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadError, setUploadError] = useState('');

    const handleChange = (e) => {
        const { id, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [id]: value
        }));
    };

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setSelectedFile(e.target.files[0]);
            // Создаем временный URL для предпросмотра
            const previewUrl = URL.createObjectURL(e.target.files[0]);
            setFormData(prev => ({
                ...prev,
                map_image_url: previewUrl
            }));
        }
    };

    const uploadImage = async (countryId) => {
        if (!selectedFile) return null;
        
        setIsUploading(true);
        setUploadError('');
        
        try {
            // Используем axios напрямую вместо dispatch
            const formData = new FormData();
            formData.append('country_id', countryId);
            formData.append('file', selectedFile);
            
            const response = await axios.post(
                'http://4452515-co41851.twc1.net:8006/photo/change_country_map',
                formData,
                {
                    headers: {
                        'Content-Type': 'multipart/form-data'
                    }
                }
            );
            
            return response.data.map_image_url;
        } catch (error) {
            console.error('Ошибка при загрузке изображения:', error);
            setUploadError('Не удалось загрузить изображение. Пожалуйста, попробуйте снова.');
            return null;
        } finally {
            setIsUploading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        
        if (isUploading) return;
        
        // Если создаем новую страну, сначала сохраняем данные, затем загружаем изображение
        if (!initialData) {
            const savedCountry = await onSuccess(formData);
            if (savedCountry && selectedFile) {
                const imageUrl = await uploadImage(savedCountry.id);
                if (imageUrl) {
                    // Обновляем страну с новым URL изображения
                    onSuccess({
                        ...savedCountry,
                        map_image_url: imageUrl
                    });
                }
            }
        } 
        // Если редактируем существующую страну
        else {
            if (selectedFile) {
                const imageUrl = await uploadImage(initialData.id);
                if (imageUrl) {
                    onSuccess({
                        ...formData,
                        map_image_url: imageUrl
                    });
                } else {
                    // Если загрузка не удалась, все равно сохраняем остальные данные
                    onSuccess(formData);
                }
            } else {
                onSuccess(formData);
            }
        }
    };

    return (
        <div className={s.edit_country_form}>
            <h2>{initialData ? 'ИЗМЕНЕНИЕ СТРАНЫ' : 'СОЗДАНИЕ СТРАНЫ'}</h2>
            
            <form onSubmit={handleSubmit}>
                <div className={s.form_group}>
                    <label>НАЗВАНИЕ:</label>
                    <Input
                        id="name"
                        text="Введите название страны"
                        value={formData.name}
                        onChange={handleChange}
                        isRequired={true}
                    />
                </div>

                <div className={s.form_group}>
                    <label>ОПИСАНИЕ</label>
                    <Textarea
                        id="description"
                        text="Описание страны"
                        value={formData.description}
                        onChange={handleChange}
                        isRequired={true}
                    />
                </div>

                <div className={s.form_group}>
                    <label>ИЗОБРАЖЕНИЕ КАРТЫ</label>
                    <div className={s.file_upload}>
                        <input 
                            type="file" 
                            id="map_image" 
                            accept="image/*"
                            onChange={handleFileChange}
                            className={s.file_input}
                        />
                        <label htmlFor="map_image" className={s.file_label}>
                            {selectedFile ? selectedFile.name : 'Выберите файл'}
                        </label>
                    </div>
                    
                    {uploadError && <div className={s.error_message}>{uploadError}</div>}
                    
                    {formData.map_image_url && (
                        <div className={s.map_preview}>
                            <img src={formData.map_image_url} alt="Карта страны" />
                        </div>
                    )}
                </div>

                <div className={s.form_group}>
                    <label>ПРАВИТЕЛЬ</label>
                    <div className={s.leader_placeholder}>
                        Функционал выбора правителя будет добавлен позже
                    </div>
                </div>

                <div className={s.form_actions}>
                    <button 
                        type="submit" 
                        className={s.submit_button}
                        disabled={isUploading}
                    >
                        {isUploading ? 'ЗАГРУЗКА...' : (initialData ? 'СОХРАНИТЬ' : 'СОЗДАТЬ')}
                    </button>
                    <button 
                        type="button" 
                        className={s.cancel_button} 
                        onClick={onCancel}
                        disabled={isUploading}
                    >
                        ВЕРНУТЬСЯ К СПИСКУ
                    </button>
                </div>
            </form>
        </div>
    );
}

export default EditCountryForm;