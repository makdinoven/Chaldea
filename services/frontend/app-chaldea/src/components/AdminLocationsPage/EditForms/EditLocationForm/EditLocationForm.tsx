import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import toast from 'react-hot-toast';
import LocationSearch from '../../../CommonComponents/LocationSearch/LocationSearch';
import {
  createLocation,
  updateLocation,
  uploadLocationImage,
  uploadLocationIcon,
  updateLocationNeighbors,
  fetchLocationDetails,
  fetchLocationsList,
  fetchAllLocations,
} from '../../../../redux/actions/locationEditActions';
import { selectLocationEdit } from '../../../../redux/selectors/locationSelectors';
import LocationNeighborsEditor from './LocationNeighborsEditor/LocationNeighborsEditor';
import type { AppDispatch } from '../../../../redux/store';

interface Neighbor {
  neighbor_id: number;
  energy_cost: number;
}

interface LocationFormData {
  name: string;
  district_id: string | number;
  parent_id: number | null;
  description: string;
  recommended_level: number;
  quick_travel_marker: boolean;
  marker_type: 'safe' | 'dangerous' | 'dungeon';
  image_url?: string;
  id?: number | string;
  [key: string]: unknown;
}

interface InitialData {
  district_id?: number;
  name?: string;
  description?: string;
  parent_id?: number | null;
  recommended_level?: number;
  quick_travel_marker?: boolean;
  marker_type?: 'safe' | 'dangerous' | 'dungeon';
  image_url?: string;
  map_icon_url?: string;
  id?: number;
}

interface EditLocationFormProps {
  locationId?: number | string;
  initialData?: InitialData;
  onCancel: () => void;
  onSuccess: (districtId?: number | string, dispatch?: AppDispatch) => void;
}

const MARKER_TYPE_OPTIONS = [
  { value: 'safe', label: 'Безопасная' },
  { value: 'dangerous', label: 'Опасная' },
  { value: 'dungeon', label: 'Подземелье' },
] as const;

const EditLocationForm = ({
  locationId = 'new',
  initialData,
  onCancel,
  onSuccess,
}: EditLocationFormProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const { currentLocation, allLocations } = useSelector(selectLocationEdit) as {
    currentLocation: Record<string, unknown> | null;
    districtLocations: { id: number; name: string }[];
    allLocations: { id: number; name: string }[];
  };

  const [formData, setFormData] = useState<LocationFormData>({
    name: '',
    district_id: '',
    parent_id: null,
    description: '',
    recommended_level: 1,
    quick_travel_marker: false,
    marker_type: 'safe',
    ...initialData,
  });

  const [isUploading, setIsUploading] = useState(false);
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string>(initialData?.image_url || '');
  const [iconFile, setIconFile] = useState<File | null>(null);
  const [iconPreview, setIconPreview] = useState<string | null>(initialData?.map_icon_url || null);
  const [neighbors, setNeighbors] = useState<Neighbor[]>([]);

  useEffect(() => {
    if (locationId !== 'new') {
      dispatch(fetchLocationDetails(locationId as number) as unknown as ReturnType<typeof fetchLocationDetails>);
    }
  }, [dispatch, locationId]);

  useEffect(() => {
    if (locationId !== 'new' && formData.district_id) {
      dispatch(fetchLocationsList(formData.district_id as number) as unknown as ReturnType<typeof fetchLocationsList>);
    }
  }, [dispatch, formData.district_id, locationId]);

  useEffect(() => {
    dispatch(fetchAllLocations() as unknown as ReturnType<typeof fetchAllLocations>);
  }, [dispatch]);

  useEffect(() => {
    if (currentLocation && locationId !== 'new') {
      setFormData({
        ...(currentLocation as unknown as LocationFormData),
        recommended_level: (currentLocation.recommended_level as number) || 1,
        parent_id: (currentLocation.parent_id as number) || null,
        quick_travel_marker: (currentLocation.quick_travel_marker as boolean) ?? false,
        marker_type: (currentLocation.marker_type as 'safe' | 'dangerous' | 'dungeon') || 'safe',
      });
      if (currentLocation.map_icon_url && !iconFile) {
        setIconPreview(currentLocation.map_icon_url as string);
      }
      if (Array.isArray(currentLocation.neighbors)) {
        setNeighbors(
          (currentLocation.neighbors as { neighbor_id: number; energy_cost: number }[]).map((n) => ({
            neighbor_id: n.neighbor_id,
            energy_cost: n.energy_cost || 1,
          }))
        );
      } else {
        setNeighbors([]);
      }
    }
  }, [currentLocation, locationId]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    if (!e.target || !e.target.name) return;
    const { name, value, type } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'number' ? (value === '' ? '' : Number(value)) : value,
    }));
  };

  const handleParentChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const { value } = e.target;
    setFormData((prev) => ({
      ...prev,
      parent_id: value ? Number(value) : null,
    }));
  };

  const handleQuickTravelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      quick_travel_marker: e.target.checked,
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

  const handleIconFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setIconFile(file);
        setIconPreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleNeighborAdd = (neighbor: Neighbor) => {
    if (!neighbor || neighbors.some((n) => n.neighbor_id === neighbor.neighbor_id)) return;
    setNeighbors((prev) => [...prev, neighbor]);
  };

  const handleNeighborRemove = (neighborId: number) => {
    setNeighbors((prev) => prev.filter((n) => n.neighbor_id !== neighborId));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isUploading) return;

    if (!formData.name) {
      toast.error('Заполните обязательное поле: название');
      return;
    }

    setIsUploading(true);
    try {
      const { parent_id, ...rest } = formData;
      const locationData = {
        ...rest,
        ...(parent_id ? { parent_id: Number(parent_id) } : {}),
        recommended_level: formData.recommended_level ? Number(formData.recommended_level) : 1,
        type: 'location',
        quick_travel_marker: Boolean(formData.quick_travel_marker),
        district_id: formData.district_id ? Number(formData.district_id) : null,
        marker_type: formData.marker_type || 'safe',
      };

      const action = locationId !== 'new' ? updateLocation : createLocation;
      const result = await dispatch(action(locationData as never) as unknown as ReturnType<typeof action>).unwrap();

      if (locationId === 'new' && formData.parent_id) {
        try {
          await dispatch(
            updateLocation({ id: formData.parent_id, type: 'subdistrict' } as never) as unknown as ReturnType<typeof updateLocation>
          ).unwrap();
        } catch {
          console.error('Ошибка при обновлении типа родителя');
        }
      }

      if (selectedImage) {
        try {
          await dispatch(
            uploadLocationImage({
              locationId: (result as { id: number }).id,
              file: selectedImage,
            } as never) as unknown as ReturnType<typeof uploadLocationImage>
          ).unwrap();
        } catch {
          toast.error('Ошибка при загрузке изображения');
        }
      }

      if (iconFile) {
        try {
          await dispatch(
            uploadLocationIcon({
              locationId: (result as { id: number }).id,
              file: iconFile,
            } as never) as unknown as ReturnType<typeof uploadLocationIcon>
          ).unwrap();
        } catch {
          toast.error('Ошибка при загрузке иконки для карты');
        }
      }

      const newLocationId = locationId === 'new' ? (result as { id: number }).id : locationId;
      if (neighbors.length > 0) {
        try {
          await dispatch(
            updateLocationNeighbors({
              locationId: newLocationId,
              neighbors,
            } as never) as unknown as ReturnType<typeof updateLocationNeighbors>
          ).unwrap();
        } catch {
          toast.error('Ошибка при обновлении соседей');
        }
      }

      toast.success(locationId === 'new' ? 'Локация создана' : 'Локация обновлена');
      onSuccess(formData.district_id, dispatch);
    } catch {
      toast.error('Ошибка при сохранении локации');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div
      className="bg-[rgba(22,37,49,0.95)] p-8 rounded-lg text-[#d4e6f3] max-w-[1000px] mx-auto shadow-[0_4px_20px_rgba(0,0,0,0.5)]"
      onClick={(e) => e.stopPropagation()}
    >
      <h2 className="text-center mb-8 text-[#a8c6df] uppercase tracking-wider text-xl font-medium">
        {locationId !== 'new' ? 'ИЗМЕНЕНИЕ ЛОКАЦИИ' : 'СОЗДАНИЕ ЛОКАЦИИ'}
      </h2>

      <form onSubmit={handleSubmit}>
        <div className="mb-6">
          <h3 className="text-white mb-4 pb-2 border-b border-white/10">Основная информация</h3>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">НАЗВАНИЕ:</label>
            <input
              type="text"
              name="name"
              value={formData.name || ''}
              onChange={handleChange}
              required
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ОПИСАНИЕ:</label>
            <textarea
              name="description"
              value={formData.description || ''}
              onChange={handleChange}
              rows={4}
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none resize-y min-h-[100px]"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ТИП МАРКЕРА:</label>
            <select
              name="marker_type"
              value={formData.marker_type}
              onChange={handleChange}
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            >
              {MARKER_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">РЕКОМЕНДУЕМЫЙ УРОВЕНЬ:</label>
            <input
              type="number"
              name="recommended_level"
              value={formData.recommended_level || ''}
              onChange={handleChange}
              min="1"
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            />
          </div>

          <div className="mb-4">
            <label className="flex items-center gap-2 text-[#d4e6f3] cursor-pointer">
              <input
                type="checkbox"
                name="quick_travel_marker"
                checked={formData.quick_travel_marker}
                onChange={handleQuickTravelChange}
                className="w-4 h-4"
              />
              Возможность быстрого перехода
            </label>
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">РОДИТЕЛЬСКАЯ ЛОКАЦИЯ:</label>
            <LocationSearch
              name="parent_id"
              value={formData.parent_id}
              onChange={handleParentChange}
              locations={allLocations || []}
              placeholder="Выберите родительскую локацию (необязательно)"
              allowClear
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
            {(imagePreview || formData.image_url) && (
              <div className="mt-2">
                <img
                  src={imagePreview || formData.image_url}
                  alt="Preview"
                  className="max-w-full max-h-[200px] rounded border border-white/10"
                />
              </div>
            )}
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ИКОНКА НА КАРТЕ (PNG):</label>
            <input
              type="file"
              accept="image/*"
              onChange={handleIconFileChange}
              className="text-[#d4e6f3] text-sm"
            />
            {(iconPreview || (currentLocation as Record<string, unknown> | null)?.map_icon_url) && (
              <div className="mt-2">
                <img
                  src={iconPreview || String((currentLocation as Record<string, unknown>)?.map_icon_url || '')}
                  alt="Иконка на карте"
                  className="max-h-[80px] w-auto object-contain"
                />
              </div>
            )}
          </div>
        </div>

        <div className="mb-6">
          <h3 className="text-white mb-4 pb-2 border-b border-white/10">Соседние локации</h3>
          <LocationNeighborsEditor
            formData={{ id: (formData.id as number) || 'new' }}
            neighbors={neighbors}
            onAdd={handleNeighborAdd}
            onRemove={handleNeighborRemove}
          />
        </div>

        <div className="flex gap-4 mt-8">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 py-3 bg-white/10 text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-white/20"
          >
            Отмена
          </button>
          <button
            type="submit"
            className="flex-1 py-3 bg-site-blue text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
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
