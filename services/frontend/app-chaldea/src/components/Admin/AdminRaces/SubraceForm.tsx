import { useState } from 'react';
import StatPresetEditor from './StatPresetEditor';
import { DEFAULT_PRESET } from './StatPresetEditor';
import type { Race, Subrace, StatPreset } from '../../../redux/slices/racesSlice';

interface SubraceFormProps {
  subrace: Subrace | null;
  races: Race[];
  defaultRaceId: number | null;
  onSave: (
    data: { id_race: number; name: string; description: string; stat_preset: StatPreset },
    imageFile: File | null
  ) => void;
  onCancel: () => void;
  loading: boolean;
}

const SubraceForm = ({ subrace, races, defaultRaceId, onSave, onCancel, loading }: SubraceFormProps) => {
  const [name, setName] = useState(subrace?.name || '');
  const [description, setDescription] = useState(subrace?.description || '');
  const [raceId, setRaceId] = useState<number>(
    subrace?.id_race || defaultRaceId || (races[0]?.id_race ?? 0)
  );
  const [statPreset, setStatPreset] = useState<StatPreset>(
    subrace?.stat_preset || { ...DEFAULT_PRESET }
  );
  const [imageFile, setImageFile] = useState<File | null>(null);

  const presetSum = Object.values(statPreset).reduce((acc, v) => acc + (v || 0), 0);
  const isPresetValid = presetSum === 100;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isPresetValid) return;
    onSave({ id_race: raceId, name, description, stat_preset: statPreset }, imageFile);
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
      <div className="modal-content gold-outline gold-outline-thick w-full max-w-2xl">
        <h2 className="gold-text text-2xl uppercase mb-6">
          {subrace ? 'Редактировать подрасу' : 'Создать подрасу'}
        </h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block mb-1 text-white/60 font-medium text-sm uppercase tracking-wide">
              Раса
            </label>
            <select
              value={raceId}
              onChange={(e) => setRaceId(Number(e.target.value))}
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-white
                transition-colors focus:border-site-blue/50 focus:outline-none"
            >
              {races.map((race) => (
                <option key={race.id_race} value={race.id_race} className="bg-site-dark text-white">
                  {race.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block mb-1 text-white/60 font-medium text-sm uppercase tracking-wide">
              Название
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Введите название подрасы"
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
              rows={3}
              placeholder="Введите описание подрасы"
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
            {subrace?.image && !imageFile && (
              <img
                src={subrace.image}
                alt={subrace.name}
                className="mt-2 max-w-full max-h-[150px] rounded border border-white/10 object-cover"
              />
            )}
            {imageFile && (
              <p className="mt-1 text-white/40 text-xs">
                Выбрано: {imageFile.name}
              </p>
            )}
          </div>

          <div>
            <label className="block mb-2 text-white/60 font-medium text-sm uppercase tracking-wide">
              Пресет статов
            </label>
            <StatPresetEditor value={statPreset} onChange={setStatPreset} />
          </div>

          <div className="flex gap-4 mt-2">
            <button
              type="submit"
              disabled={loading || !name.trim() || !isPresetValid}
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

export default SubraceForm;
