import { useState } from 'react';
import type { Race } from '../../../redux/slices/racesSlice';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';

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

  return (
    <ModalShell
      open
      onClose={onCancel}
      title={race ? 'Редактировать расу' : 'Создать расу'}
      size="md"
      footer={
        <>
          <button
            type="submit"
            form="race-form"
            disabled={loading || !name.trim()}
            className="w-full sm:w-auto px-6 py-2 bg-site-blue text-white border-none rounded cursor-pointer font-medium
              transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Сохранение...' : 'Сохранить'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="w-full sm:w-auto px-6 py-2 bg-white/10 text-white border-none rounded cursor-pointer font-medium
              transition-colors hover:bg-white/20"
          >
            Отмена
          </button>
        </>
      }
    >
      <form id="race-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
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
      </form>
    </ModalShell>
  );
};

export default RaceForm;
