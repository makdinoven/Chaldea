import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import toast from 'react-hot-toast';
import {
  createRegion,
  updateRegion,
  fetchRegionDetails,
  uploadRegionImage,
  uploadRegionMap,
} from '../../../../redux/actions/regionEditActions';
import { fetchAllLocations } from '../../../../redux/actions/locationEditActions';
import { resetRegionEditState } from '../../../../redux/slices/regionEditSlice';
import { selectRegionEdit, selectAdminLocations } from '../../../../redux/selectors/locationSelectors';
import LocationSearch from '../../../CommonComponents/LocationSearch/LocationSearch';
import type { AppDispatch } from '../../../../redux/store';

interface RegionFormData {
  name: string;
  description: string;
  country_id: string | number;
  entrance_location_id: string | number;
  leader_id: string | number;
  x: string | number;
  y: string | number;
  type: string;
  status: string;
  map_image_url?: string;
  image_url?: string;
}

interface InitialData {
  id?: number;
  name?: string;
  description?: string;
  country_id?: number;
  entrance_location_id?: number;
  leader_id?: number;
  x?: number;
  y?: number;
}

interface EditRegionFormProps {
  regionId?: number | string;
  initialCountryId?: number;
  initialData?: InitialData;
  onCancel: () => void;
  onSuccess: () => void;
}

const EditRegionForm = ({
  regionId = 'new',
  initialCountryId,
  initialData,
  onCancel,
  onSuccess,
}: EditRegionFormProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const { loading, error, currentRegion } = useSelector(selectRegionEdit) as {
    loading: boolean;
    error: string | null;
    currentRegion: Record<string, unknown> | null;
  };
  const { countries } = useSelector(selectAdminLocations) as {
    countries: { id: number; name: string }[];
  };
  const { allLocations } = useSelector((state: { locationEdit: { allLocations: { id: number; name: string }[] } }) => state.locationEdit);

  const [formData, setFormData] = useState<RegionFormData>({
    name: '',
    description: '',
    country_id: initialCountryId || '',
    entrance_location_id: '',
    leader_id: '',
    x: '',
    y: '',
    type: 'region',
    status: 'active',
  });

  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [selectedMap, setSelectedMap] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [mapPreview, setMapPreview] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    if (regionId !== 'new') {
      dispatch(fetchRegionDetails(regionId as number) as unknown as ReturnType<typeof fetchRegionDetails>);
    }
    dispatch(fetchAllLocations() as unknown as ReturnType<typeof fetchAllLocations>);
  }, [dispatch, regionId]);

  useEffect(() => {
    if (currentRegion && regionId !== 'new') {
      setFormData({
        name: (currentRegion.name as string) || '',
        description: (currentRegion.description as string) || '',
        country_id: (currentRegion.country_id as number) || initialCountryId || '',
        entrance_location_id: (currentRegion.entrance_location_id as number) || '',
        leader_id: (currentRegion.leader_id as number) || '',
        x: (currentRegion.x as number) || '',
        y: (currentRegion.y as number) || '',
        type: (currentRegion.type as string) || 'region',
        status: (currentRegion.status as string) || 'active',
      });
      setImagePreview((currentRegion.image_url as string) || null);
      setMapPreview((currentRegion.map_image_url as string) || null);
    }
  }, [currentRegion, regionId, initialCountryId]);

  useEffect(() => {
    return () => {
      dispatch(resetRegionEditState());
    };
  }, [dispatch]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    const fieldName = name || (e.target as HTMLInputElement).id;
    setFormData((prev) => ({
      ...prev,
      [fieldName]: type === 'number' ? (value === '' ? '' : Number(value)) : value,
    }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>, fileType: 'image' | 'map') => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        if (fileType === 'image') {
          setSelectedImage(file);
          setImagePreview(reader.result as string);
        } else {
          setSelectedMap(file);
          setMapPreview(reader.result as string);
        }
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isUploading) return;

    if (!formData.name || !formData.country_id) {
      toast.error('Заполните обязательные поля: название и страна');
      return;
    }

    const regionData = {
      name: formData.name,
      description: formData.description,
      country_id: Number(formData.country_id),
      entrance_location_id: formData.entrance_location_id ? Number(formData.entrance_location_id) : null,
      leader_id: formData.leader_id ? Number(formData.leader_id) : null,
      x: formData.x !== '' ? Number(formData.x) : 0,
      y: formData.y !== '' ? Number(formData.y) : 0,
      map_image_url: formData.map_image_url || null,
      image_url: formData.image_url || null,
    };

    setIsUploading(true);
    try {
      const action = regionId === 'new' ? createRegion : updateRegion;
      const dataToSend = regionId === 'new' ? regionData : { id: regionId, ...regionData };

      const result = await dispatch(action(dataToSend as unknown as never) as unknown as ReturnType<typeof action>).unwrap();
      const newRegionId = regionId === 'new' ? (result as { id: number }).id : regionId;

      if (selectedImage) {
        await dispatch(
          uploadRegionImage({ regionId: newRegionId, file: selectedImage } as unknown as never) as unknown as ReturnType<typeof uploadRegionImage>
        ).unwrap();
      }

      if (selectedMap) {
        await dispatch(
          uploadRegionMap({ regionId: newRegionId, file: selectedMap } as unknown as never) as unknown as ReturnType<typeof uploadRegionMap>
        ).unwrap();
      }

      toast.success(regionId === 'new' ? 'Регион создан' : 'Регион обновлён');
      onSuccess?.();
    } catch (err) {
      toast.error('Ошибка при сохранении региона');
      console.error('Error saving region:', err);
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
        {regionId === 'new' ? 'СОЗДАНИЕ РЕГИОНА' : 'ИЗМЕНЕНИЕ РЕГИОНА'}
      </h2>

      <form onSubmit={handleSubmit}>
        <div className="mb-6">
          <h3 className="text-white mb-4 pb-2 border-b border-white/10">Основная информация</h3>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">НАЗВАНИЕ:</label>
            <input
              type="text"
              name="name"
              placeholder="Введите название региона"
              value={formData.name}
              onChange={handleChange}
              required
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">СТРАНА:</label>
            <select
              name="country_id"
              value={formData.country_id}
              onChange={handleChange}
              required
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            >
              <option value="">Выберите страну</option>
              {countries.map((country) => (
                <option key={country.id} value={country.id}>
                  {country.name}
                </option>
              ))}
            </select>
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ВХОДНАЯ ЛОКАЦИЯ:</label>
            <LocationSearch
              name="entrance_location_id"
              value={formData.entrance_location_id}
              onChange={handleChange}
              countryId={formData.country_id}
              locations={allLocations}
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ПРАВИТЕЛЬ:</label>
            <select
              name="leader_id"
              value={formData.leader_id}
              onChange={handleChange}
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            >
              <option value="">Выберите правителя</option>
              <option value="1">Беорик</option>
            </select>
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ОПИСАНИЕ:</label>
            <textarea
              name="description"
              placeholder="Описание региона"
              value={formData.description}
              onChange={handleChange}
              required
              rows={4}
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none resize-y min-h-[100px]"
            />
          </div>
        </div>

        <div className="mb-6">
          <h3 className="text-white mb-4 pb-2 border-b border-white/10">Координаты на карте</h3>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block mb-2 text-[#8ab3d5] font-medium">X:</label>
              <input
                type="number"
                name="x"
                value={formData.x}
                onChange={handleChange}
                required
                className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
              />
            </div>
            <div className="flex-1">
              <label className="block mb-2 text-[#8ab3d5] font-medium">Y:</label>
              <input
                type="number"
                name="y"
                value={formData.y}
                onChange={handleChange}
                required
                className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
              />
            </div>
          </div>
        </div>

        <div className="mb-6">
          <h3 className="text-white mb-4 pb-2 border-b border-white/10">Изображения</h3>
          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ИЗОБРАЖЕНИЕ РЕГИОНА:</label>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => handleFileChange(e, 'image')}
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

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">КАРТА РЕГИОНА:</label>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => handleFileChange(e, 'map')}
              className="text-[#d4e6f3] text-sm"
            />
            {mapPreview && (
              <img
                src={mapPreview}
                alt="Map Preview"
                className="mt-2 max-w-full max-h-[200px] rounded border border-white/10"
              />
            )}
          </div>
        </div>

        {error && <div className="text-site-red mb-4">{error}</div>}

        <div className="flex gap-4 mt-8">
          <button
            type="button"
            className="flex-1 py-3 bg-white/10 text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={onCancel}
            disabled={isUploading}
          >
            ВЕРНУТЬСЯ К СПИСКУ
          </button>
          <button
            type="submit"
            className="flex-1 py-3 bg-site-blue text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={isUploading}
          >
            {isUploading ? 'ЗАГРУЗКА...' : regionId === 'new' ? 'СОЗДАТЬ' : 'СОХРАНИТЬ'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default EditRegionForm;
