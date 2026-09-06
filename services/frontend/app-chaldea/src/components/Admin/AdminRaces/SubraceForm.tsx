import { useEffect, useMemo, useState } from 'react';
import StatPresetEditor from './StatPresetEditor';
import { DEFAULT_PRESET } from './StatPresetEditor';
import type { Race, Subrace, StatPreset, SubraceCreateData } from '../../../redux/slices/racesSlice';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchOriginsThunk,
  selectOrigins,
  selectOriginsLoading,
  selectOriginsError,
} from '../../../redux/slices/originsSlice';

/**
 * FEAT-154 (rules 11, 14, 15) — the subrace editor also owns the appearance
 * memo (`distinctive_features`), the typical height range and the list of
 * origins that are characteristic for the subrace.
 */
interface SubraceFormProps {
  subrace: Subrace | null;
  races: Race[];
  defaultRaceId: number | null;
  onSave: (data: SubraceCreateData, imageFile: File | null) => void;
  onCancel: () => void;
  loading: boolean;
}

const FIELD_CLASS =
  'w-full p-2.5 bg-black/30 border border-white/10 rounded text-white ' +
  'transition-colors focus:border-site-blue/50 focus:outline-none';
const LABEL_CLASS = 'block mb-1 text-white/60 font-medium text-sm uppercase tracking-wide';

/** Empty string -> null, so an untouched numeric field is not sent as 0. */
const toNullableNumber = (value: string): number | null => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
};

const SubraceForm = ({ subrace, races, defaultRaceId, onSave, onCancel, loading }: SubraceFormProps) => {
  const dispatch = useAppDispatch();
  const origins = useAppSelector(selectOrigins);
  const originsLoading = useAppSelector(selectOriginsLoading);
  const originsError = useAppSelector(selectOriginsError);

  const [name, setName] = useState(subrace?.name || '');
  const [description, setDescription] = useState(subrace?.description || '');
  const [raceId, setRaceId] = useState<number>(
    subrace?.id_race ?? defaultRaceId ?? races[0]?.id_race ?? 0
  );
  const [statPreset, setStatPreset] = useState<StatPreset>(
    subrace?.stat_preset || { ...DEFAULT_PRESET }
  );
  const [imageFile, setImageFile] = useState<File | null>(null);

  // FEAT-154 additions
  const [distinctiveFeatures, setDistinctiveFeatures] = useState(subrace?.distinctive_features || '');
  const [heightMin, setHeightMin] = useState(
    subrace?.height_min != null ? String(subrace.height_min) : ''
  );
  const [heightMax, setHeightMax] = useState(
    subrace?.height_max != null ? String(subrace.height_max) : ''
  );
  const [typicalOriginIds, setTypicalOriginIds] = useState<number[]>(
    subrace?.typical_origin_ids ?? []
  );

  // The picker is fed by the public origin registry (active rows only).
  useEffect(() => {
    dispatch(fetchOriginsThunk());
  }, [dispatch]);

  const presetSum = Object.values(statPreset).reduce((acc, v) => acc + (v || 0), 0);
  const isPresetValid = presetSum === 100;

  const heightError = useMemo(() => {
    const min = toNullableNumber(heightMin);
    const max = toNullableNumber(heightMax);
    if (min !== null && min <= 0) return 'Минимальный рост должен быть больше нуля.';
    if (max !== null && max <= 0) return 'Максимальный рост должен быть больше нуля.';
    if (min !== null && max !== null && min > max) {
      return 'Минимальный рост не может быть больше максимального.';
    }
    return null;
  }, [heightMin, heightMax]);

  const toggleOrigin = (originId: number) => {
    setTypicalOriginIds((prev) =>
      prev.includes(originId) ? prev.filter((id) => id !== originId) : [...prev, originId]
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isPresetValid || heightError) return;
    onSave(
      {
        id_race: raceId,
        name,
        description,
        stat_preset: statPreset,
        distinctive_features: distinctiveFeatures.trim() ? distinctiveFeatures.trim() : null,
        height_min: toNullableNumber(heightMin),
        height_max: toNullableNumber(heightMax),
        typical_origin_ids: typicalOriginIds,
      },
      imageFile
    );
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
      className="fixed inset-0 bg-black/85 z-[1000] overflow-y-auto py-6 px-3 sm:py-10 sm:px-5 flex items-start justify-center"
      onClick={handleOverlayClick}
    >
      <div className="modal-content gold-outline gold-outline-thick w-full max-w-2xl">
        <h2 className="gold-text text-xl sm:text-2xl uppercase mb-6">
          {subrace ? 'Редактировать подрасу' : 'Создать подрасу'}
        </h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className={LABEL_CLASS}>Раса</label>
            <select
              value={raceId}
              onChange={(e) => setRaceId(Number(e.target.value))}
              className={FIELD_CLASS}
            >
              {races.map((race) => (
                <option key={race.id_race} value={race.id_race} className="bg-site-dark text-white">
                  {race.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={LABEL_CLASS}>Название</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Введите название подрасы"
              className={FIELD_CLASS}
            />
          </div>

          <div>
            <label className={LABEL_CLASS}>Описание</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Введите описание подрасы"
              className={`${FIELD_CLASS} resize-y`}
            />
          </div>

          <div>
            <label className={LABEL_CLASS}>Отличительные особенности</label>
            <textarea
              value={distinctiveFeatures}
              onChange={(e) => setDistinctiveFeatures(e.target.value)}
              rows={3}
              placeholder="Только про облик: кожа, рост, чешуя, рога, хвост, глаза"
              className={`${FIELD_CLASS} resize-y`}
            />
            <p className="mt-1 text-white/40 text-xs">
              Показывается на шаге «Личность» как памятка о внешности. Если поле пустое,
              игрок увидит обычное описание подрасы.
            </p>
          </div>

          <div>
            <label className={LABEL_CLASS}>Характерный рост, см</label>
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="number"
                min={1}
                value={heightMin}
                onChange={(e) => setHeightMin(e.target.value)}
                placeholder="От"
                aria-label="Минимальный рост, см"
                className={FIELD_CLASS}
              />
              <input
                type="number"
                min={1}
                value={heightMax}
                onChange={(e) => setHeightMax(e.target.value)}
                placeholder="До"
                aria-label="Максимальный рост, см"
                className={FIELD_CLASS}
              />
            </div>
            {heightError ? (
              <p className="mt-1 text-site-red text-xs">{heightError}</p>
            ) : (
              <p className="mt-1 text-white/40 text-xs">
                Необязательно. Рост персонажа вне диапазона вызовет мягкое предупреждение,
                но не заблокирует заявку.
              </p>
            )}
          </div>

          <div>
            <label className={LABEL_CLASS}>Характерные происхождения</label>
            {originsLoading && (
              <p className="text-white/40 text-xs">Загрузка списка происхождений…</p>
            )}
            {originsError && (
              <div className="flex flex-wrap items-center gap-3 p-2.5 rounded border border-site-red/40 bg-site-red/10">
                <p className="text-site-red text-xs">{originsError}</p>
                <button
                  type="button"
                  onClick={() => dispatch(fetchOriginsThunk())}
                  className="text-site-blue text-xs underline hover:text-white transition-colors"
                >
                  Повторить
                </button>
              </div>
            )}
            {!originsLoading && !originsError && origins.length === 0 && (
              <p className="text-white/40 text-xs">
                Справочник происхождений пуст. Заполните его в разделе «Происхождения».
              </p>
            )}
            {origins.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {origins.map((origin) => {
                  const active = typicalOriginIds.includes(origin.id);
                  return (
                    <button
                      key={origin.id}
                      type="button"
                      onClick={() => toggleOrigin(origin.id)}
                      aria-pressed={active}
                      className={`chip-outline rounded-full px-3 py-1.5 text-xs font-medium ${
                        active ? 'chip-outline-active' : ''
                      }`}
                    >
                      {origin.name}
                    </button>
                  );
                })}
              </div>
            )}
            <p className="mt-1 text-white/40 text-xs">
              Нехарактерный выбор игрока не запрещён — он лишь помечается как редкий.
            </p>
          </div>

          <div>
            <label className={LABEL_CLASS}>Изображение</label>
            <input
              type="file"
              accept="image/*"
              onChange={handleImageChange}
              className="text-white/60 text-sm max-w-full"
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
            <label className={`${LABEL_CLASS} mb-2`}>Пресет статов</label>
            <StatPresetEditor value={statPreset} onChange={setStatPreset} />
          </div>

          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 mt-2">
            <button
              type="submit"
              disabled={loading || !name.trim() || !isPresetValid || Boolean(heightError)}
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
