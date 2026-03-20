import { useState } from 'react';
import { useSelector } from 'react-redux';
import axios from 'axios';
import toast from 'react-hot-toast';
import type { RootState } from '../../../../redux/store';
import type { Area } from '../../../../redux/actions/adminLocationsActions';

interface CountryFormData {
  name: string;
  description: string;
  map_image_url: string;
  emblem_url: string;
  leader_id: number | null;
  area_id: number | string;
}

interface InitialData {
  id?: number;
  name?: string;
  description?: string;
  map_image_url?: string;
  emblem_url?: string | null;
  leader_id?: number | null;
  area_id?: number | null;
}

interface EditCountryFormProps {
  initialData: InitialData | null;
  onCancel: () => void;
  onSuccess: (data?: unknown) => void;
}

const EditCountryForm = ({ initialData, onCancel, onSuccess }: EditCountryFormProps) => {
  const areas: Area[] = useSelector(
    (state: RootState) => (state.adminLocations as { areas?: Area[] }).areas
  ) || [];

  const [formData, setFormData] = useState<CountryFormData>({
    name: initialData?.name || '',
    description: initialData?.description || '',
    map_image_url: initialData?.map_image_url || '',
    emblem_url: initialData?.emblem_url || '',
    leader_id: initialData?.leader_id || null,
    area_id: initialData?.area_id || '',
  });

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [emblemFile, setEmblemFile] = useState<File | null>(null);
  const [emblemPreview, setEmblemPreview] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { id, name, value } = e.target;
    const fieldName = name || id;
    setFormData((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      const previewUrl = URL.createObjectURL(e.target.files[0]);
      setFormData((prev) => ({
        ...prev,
        map_image_url: previewUrl,
      }));
    }
  };

  const handleEmblemFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setEmblemFile(e.target.files[0]);
      setEmblemPreview(URL.createObjectURL(e.target.files[0]));
    }
  };

  const uploadImage = async (countryId: number): Promise<string | null> => {
    if (!selectedFile) return null;

    setIsUploading(true);
    setUploadError('');

    try {
      const fd = new FormData();
      fd.append('country_id', String(countryId));
      fd.append('file', selectedFile);

      const response = await axios.post('/photo/change_country_map', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      return response.data.map_image_url;
    } catch {
      setUploadError('Не удалось загрузить изображение. Пожалуйста, попробуйте снова.');
      toast.error('Не удалось загрузить изображение');
      return null;
    } finally {
      setIsUploading(false);
    }
  };

  const uploadEmblem = async (countryId: number): Promise<string | null> => {
    if (!emblemFile) return null;

    setIsUploading(true);

    try {
      const fd = new FormData();
      fd.append('country_id', String(countryId));
      fd.append('file', emblemFile);

      const response = await axios.post('/photo/change_country_emblem', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      return response.data.emblem_url;
    } catch {
      toast.error('Не удалось загрузить эмблему страны');
      return null;
    } finally {
      setIsUploading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isUploading) return;

    if (initialData?.id) {
      // Edit existing country
      const resultData: Record<string, unknown> = { ...formData, id: initialData.id };

      if (selectedFile) {
        const imageUrl = await uploadImage(initialData.id);
        if (imageUrl) {
          resultData.map_image_url = imageUrl;
        }
      }

      if (emblemFile) {
        const emblemUrl = await uploadEmblem(initialData.id);
        if (emblemUrl) {
          resultData.emblem_url = emblemUrl;
        }
      }

      onSuccess(resultData);
    } else {
      // Create new country — pass form data, let parent handle API call.
      // NOTE: Emblem upload requires a country_id, so for newly created countries
      // the emblem must be uploaded after creation (edit the country to add emblem).
      onSuccess(formData);
    }
  };

  return (
    <div
      className="bg-[rgba(22,37,49,0.95)] p-8 rounded-lg text-[#d4e6f3] max-w-[800px] mx-auto shadow-[0_4px_20px_rgba(0,0,0,0.5)]"
      onClick={(e) => e.stopPropagation()}
    >
      <h2 className="text-center mb-8 text-[#a8c6df] uppercase tracking-wider text-xl font-medium">
        {initialData ? 'ИЗМЕНЕНИЕ СТРАНЫ' : 'СОЗДАНИЕ СТРАНЫ'}
      </h2>

      <form onSubmit={handleSubmit}>
        <div className="mb-6">
          <label className="block mb-2 text-[#8ab3d5] font-medium">ОБЛАСТЬ:</label>
          <select
            name="area_id"
            value={formData.area_id}
            onChange={handleChange}
            className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
          >
            <option value="">Без области</option>
            {areas.map((area) => (
              <option key={area.id} value={area.id}>
                {area.name}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-6">
          <label className="block mb-2 text-[#8ab3d5] font-medium">НАЗВАНИЕ:</label>
          <input
            type="text"
            id="name"
            name="name"
            placeholder="Введите название страны"
            value={formData.name}
            onChange={handleChange}
            required
            className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
          />
        </div>

        <div className="mb-6">
          <label className="block mb-2 text-[#8ab3d5] font-medium">ОПИСАНИЕ:</label>
          <textarea
            id="description"
            name="description"
            placeholder="Описание страны"
            value={formData.description}
            onChange={handleChange}
            required
            rows={4}
            className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none resize-y min-h-[100px]"
          />
        </div>

        <div className="mb-6">
          <label className="block mb-2 text-[#8ab3d5] font-medium">ИЗОБРАЖЕНИЕ КАРТЫ:</label>
          <div className="mb-4">
            <input
              type="file"
              id="map_image"
              accept="image/*"
              onChange={handleFileChange}
              className="hidden"
            />
            <label
              htmlFor="map_image"
              className="inline-block px-6 py-3 bg-white/10 text-white rounded cursor-pointer transition-colors hover:bg-white/20"
            >
              {selectedFile ? selectedFile.name : 'Выберите файл'}
            </label>
          </div>

          {uploadError && <div className="text-site-red mt-2">{uploadError}</div>}

          {formData.map_image_url && (
            <div className="mt-4">
              <img
                src={formData.map_image_url}
                alt="Карта страны"
                className="max-w-full h-auto rounded border border-white/10"
              />
            </div>
          )}
        </div>

        <div className="mb-6">
          <label className="block mb-2 text-[#8ab3d5] font-medium">ЭМБЛЕМА СТРАНЫ:</label>
          <div className="mb-4">
            <input
              type="file"
              id="emblem_image"
              accept="image/*"
              onChange={handleEmblemFileChange}
              className="hidden"
            />
            <label
              htmlFor="emblem_image"
              className="inline-block px-6 py-3 bg-white/10 text-white rounded cursor-pointer transition-colors hover:bg-white/20"
            >
              {emblemFile ? emblemFile.name : 'Выберите файл'}
            </label>
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            {emblemPreview && (
              <div className="flex flex-col items-center gap-1">
                <span className="text-xs text-gray-400">Новая</span>
                <img
                  src={emblemPreview}
                  alt="Предпросмотр эмблемы"
                  className="w-12 h-12 rounded-full object-cover border border-white/10"
                />
              </div>
            )}

            {!emblemPreview && initialData?.emblem_url && (
              <div className="flex flex-col items-center gap-1">
                <span className="text-xs text-gray-400">Текущая</span>
                <img
                  src={initialData.emblem_url}
                  alt="Текущая эмблема"
                  className="w-12 h-12 rounded-full object-cover border border-white/10"
                />
              </div>
            )}
          </div>

          {!initialData?.id && (
            <p className="text-xs text-gray-400 mt-2">
              Эмблему можно загрузить после создания страны
            </p>
          )}
        </div>

        <div className="mb-6">
          <label className="block mb-2 text-[#8ab3d5] font-medium">ПРАВИТЕЛЬ:</label>
          <div className="p-4 bg-white/10 rounded text-center text-gray-400">
            Функционал выбора правителя будет добавлен позже
          </div>
        </div>

        <div className="flex gap-4 mt-8">
          <button
            type="submit"
            className="flex-1 py-3 bg-site-blue text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={isUploading}
          >
            {isUploading ? 'ЗАГРУЗКА...' : initialData ? 'СОХРАНИТЬ' : 'СОЗДАТЬ'}
          </button>
          <button
            type="button"
            className="flex-1 py-3 bg-white/10 text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={onCancel}
            disabled={isUploading}
          >
            ВЕРНУТЬСЯ К СПИСКУ
          </button>
        </div>
      </form>
    </div>
  );
};

export default EditCountryForm;
