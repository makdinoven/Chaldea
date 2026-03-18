import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import toast from 'react-hot-toast';
import {
  createDistrict,
  updateDistrict,
  fetchDistrictDetails,
  uploadDistrictImage,
  fetchDistrictLocations,
} from '../../../../redux/actions/districtEditActions';
import { resetDistrictEditState } from '../../../../redux/slices/districtEditSlice';
import LocationSearch from '../../../CommonComponents/LocationSearch/LocationSearch';
import type { AppDispatch } from '../../../../redux/store';

interface DistrictFormData {
  name: string;
  description: string;
  region_id: number;
  entrance_location_id: string | number;
  recommended_level: number;
  x: number;
  y: number;
  image_url: string;
}

interface EditDistrictFormProps {
  districtId?: number | string;
  initialRegionId?: number;
  onCancel: () => void;
  onSuccess: () => void;
}

const EditDistrictForm = ({
  districtId = 'new',
  initialRegionId,
  onCancel,
  onSuccess,
}: EditDistrictFormProps) => {
  const dispatch = useDispatch<AppDispatch>();

  const { loading, error, currentDistrict, districtLocations } = useSelector(
    (state: { districtEdit: {
      loading: boolean;
      error: string | null;
      currentDistrict: Record<string, unknown> | null;
      districtLocations: { id: number; name: string }[];
    } }) => state.districtEdit
  );

  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const [formData, setFormData] = useState<DistrictFormData>({
    name: '',
    description: '',
    region_id: Number(initialRegionId),
    entrance_location_id: '',
    recommended_level: 1,
    x: 0,
    y: 0,
    image_url: '',
  });

  useEffect(() => {
    if (districtId !== 'new') {
      Promise.all([
        dispatch(fetchDistrictDetails(districtId as number) as unknown as ReturnType<typeof fetchDistrictDetails>),
        dispatch(fetchDistrictLocations(districtId as number) as unknown as ReturnType<typeof fetchDistrictLocations>),
      ]);
    }
  }, [dispatch, districtId]);

  useEffect(() => {
    if (currentDistrict) {
      setFormData((prev) => ({
        ...prev,
        name: (currentDistrict.name as string) || '',
        description: (currentDistrict.description as string) || '',
        region_id: (currentDistrict.region_id as number) || Number(initialRegionId),
        entrance_location_id: (currentDistrict.entrance_location_id as number) || '',
        recommended_level: (currentDistrict.recommended_level as number) || 1,
        x: (currentDistrict.x as number) || 0,
        y: (currentDistrict.y as number) || 0,
        image_url: (currentDistrict.image_url as string) || '',
      }));
      setImagePreview((currentDistrict.image_url as string) || null);
    }
  }, [currentDistrict, initialRegionId]);

  useEffect(() => {
    return () => {
      dispatch(resetDistrictEditState());
    };
  }, [dispatch]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    let processedValue: string | number = value;
    if (type === 'number') {
      if (name === 'x' || name === 'y') {
        processedValue = value === '' ? 0 : Number(value);
      } else {
        processedValue = value === '' ? '' : Number(value);
      }
    }
    setFormData((prev) => ({
      ...prev,
      [name]: processedValue,
    }));
  };

  const handleEntranceLocationSelect = (eOrValue: React.ChangeEvent<HTMLSelectElement> | string | number) => {
    let newValue: string | number;
    if (eOrValue && typeof eOrValue === 'object' && 'target' in eOrValue) {
      newValue = eOrValue.target.value;
    } else {
      newValue = eOrValue;
    }
    setFormData((prev) => ({
      ...prev,
      entrance_location_id: newValue,
    }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setSelectedImage(file);
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isUploading) return;

    if (!formData.region_id) {
      toast.error('Не указан регион');
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
      image_url: formData.image_url || '',
    };

    try {
      setIsUploading(true);
      const action =
        districtId === 'new'
          ? await dispatch(createDistrict(districtData as never) as unknown as ReturnType<typeof createDistrict>)
          : await dispatch(updateDistrict({ id: districtId, ...districtData } as never) as unknown as ReturnType<typeof updateDistrict>);

      if ((action as { error?: unknown }).error) {
        throw new Error('Ошибка при сохранении зоны');
      }

      const payload = (action as { payload: { id: number } }).payload;
      if (!payload) {
        throw new Error('Нет данных в ответе от сервера');
      }

      if (selectedImage) {
        const uploadAction = await dispatch(
          uploadDistrictImage({ districtId: payload.id, file: selectedImage } as never) as unknown as ReturnType<typeof uploadDistrictImage>
        );
        if ((uploadAction as { error?: unknown }).error) {
          toast.error('Ошибка при загрузке изображения');
        }
      }

      toast.success(districtId === 'new' ? 'Зона создана' : 'Зона обновлена');
      onSuccess?.();
    } catch (err) {
      toast.error('Ошибка при сохранении зоны');
      console.error('Error saving district:', err);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div
      className="bg-[rgba(22,37,49,0.95)] p-8 rounded-lg text-[#d4e6f3] max-w-[800px] mx-auto shadow-[0_4px_20px_rgba(0,0,0,0.5)]"
      onClick={(e) => e.stopPropagation()}
    >
      <h2 className="text-center mb-8 text-[#a8c6df] uppercase tracking-wider text-xl font-medium">
        {districtId === 'new' ? 'СОЗДАНИЕ ЗОНЫ' : 'ИЗМЕНЕНИЕ ЗОНЫ'}
      </h2>

      <form onSubmit={handleSubmit}>
        <div className="mb-6">
          <h3 className="text-white mb-4 pb-2 border-b border-white/10">Основная информация</h3>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">НАЗВАНИЕ:</label>
            <input
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              required
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ВХОДНАЯ ЛОКАЦИЯ:</label>
            <LocationSearch
              name="entrance_location_id"
              value={formData.entrance_location_id}
              onChange={handleEntranceLocationSelect}
              locations={districtLocations}
              placeholder="Выберите входную локацию"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">РЕКОМЕНДУЕМЫЙ УРОВЕНЬ:</label>
            <input
              type="number"
              name="recommended_level"
              value={formData.recommended_level}
              onChange={handleChange}
              min="1"
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">КООРДИНАТЫ:</label>
            <div className="flex gap-4">
              <input
                type="number"
                name="x"
                value={formData.x}
                onChange={handleChange}
                placeholder="X"
                className="flex-1 p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
              />
              <input
                type="number"
                name="y"
                value={formData.y}
                onChange={handleChange}
                placeholder="Y"
                className="flex-1 p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
              />
            </div>
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ОПИСАНИЕ:</label>
            <textarea
              name="description"
              value={formData.description}
              onChange={handleChange}
              rows={4}
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none resize-y min-h-[100px]"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ИЗОБРАЖЕНИЕ:</label>
            <input
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="text-[#d4e6f3] text-sm"
            />
            {imagePreview && (
              <img
                src={imagePreview}
                alt="Preview"
                className="mt-2 max-w-full max-h-[200px] rounded border border-white/10"
              />
            )}
          </div>
        </div>

        {error && <div className="text-site-red mb-4">{error}</div>}

        <div className="flex gap-4 mt-8">
          <button
            type="submit"
            className="flex-1 py-3 bg-site-blue text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={isUploading}
          >
            {isUploading ? 'Сохранение...' : 'Сохранить'}
          </button>
          <button
            type="button"
            className="flex-1 py-3 bg-white/10 text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-white/20"
            onClick={onCancel}
          >
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
};

export default EditDistrictForm;
