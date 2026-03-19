import { useState } from 'react';
import type { Race } from '../../../redux/slices/racesSlice';

interface RaceFormProps {
  race: Race | null;
  onSave: (data: { name: string; description: string }, imageFile: File | null) => void;
  onCancel: () => void;
  loading: boolean;
}

const RaceForm = ({ race, onSave, onCancel, loading }: RaceFormProps) => {
  const [name, setName] = useState(race?.name || '');
  const [description, setDescription] = useState(race?.description || '');
  const [imageFile, setImageFile] = useState<File | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({ name, description }, imageFile);
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setImageFile(e.target.files[0]);
    }
  };

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onCancel();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/85 z-[1000] overflow-y-auto py-10 px-5 flex items-start justify-center"
      onClick={handleOverlayClick}
    >
      <div className="modal-content gold-outline gold-outline-thick w-full max-w-lg">
        <h2 className="gold-text text-2xl uppercase mb-6">
          {race ? 'Редактировать расу' : 'Создать расу'}
        </h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block mb-1 text-white/60 font-medium text-sm uppercase tracking-wide">
              Название
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Введите название расы"
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-white
                transition-colors focus:border-site-blue/50 focus:outline-none"
            />
          </div>

          <div>
            <label className="block mb-1 text-white/60 font-medium text-sm uppercase tracking-wide">
              Описание
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="Введите описание расы"
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-white
                transition-colors focus:border-site-blue/50 focus:outline-none resize-y"
            />
          </div>

          <div>
            <label className="block mb-1 text-white/60 font-medium text-sm uppercase tracking-wide">
              Изображение
            </label>
            <input
              type="file"
              accept="image/*"
              onChange={handleImageChange}
              className="text-white/60 text-sm"
            />
            {race?.image && !imageFile && (
              <img
                src={race.image}
                alt={race.name}
                className="mt-2 max-w-full max-h-[150px] rounded border border-white/10 object-cover"
              />
            )}
            {imageFile && (
              <p className="mt-1 text-white/40 text-xs">
                Выбрано: {imageFile.name}
              </p>
            )}
          </div>

          <div className="flex gap-4 mt-2">
            <button
              type="submit"
              disabled={loading || !name.trim()}
              className="px-6 py-2 bg-site-blue text-white border-none rounded cursor-pointer font-medium
                transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Сохранение...' : 'Сохранить'}
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="px-6 py-2 bg-white/10 text-white border-none rounded cursor-pointer font-medium
                transition-colors hover:bg-white/20"
            >
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default RaceForm;
