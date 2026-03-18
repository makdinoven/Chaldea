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
  leader_id: number | null;
  area_id: number | string;
}

interface InitialData {
  id?: number;
  name?: string;
  description?: string;
  map_image_url?: string;
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
    leader_id: initialData?.leader_id || null,
    area_id: initialData?.area_id || '',
  });

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isUploading) return;

    if (!initialData) {
      const savedCountry = await onSuccess(formData);
      if (savedCountry && typeof savedCountry === 'object' && 'id' in (savedCountry as Record<string, unknown>) && selectedFile) {
        const imageUrl = await uploadImage((savedCountry as { id: number }).id);
        if (imageUrl) {
          onSuccess({ ...savedCountry, map_image_url: imageUrl });
        }
      }
    } else {
      if (selectedFile && initialData.id) {
        const imageUrl = await uploadImage(initialData.id);
        if (imageUrl) {
          onSuccess({ ...formData, map_image_url: imageUrl });
        } else {
          onSuccess(formData);
        }
      } else {
        onSuccess(formData);
      }
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
