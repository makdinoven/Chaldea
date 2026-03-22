import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { updateMobSpawns, selectMobsSaving } from '../../../redux/slices/mobsSlice';
import type { LocationMobSpawn } from '../../../api/mobs';

interface AdminMobSpawnsProps {
  templateId: number;
  spawns: LocationMobSpawn[];
  onUpdate: () => void;
}

interface LocationOption {
  id: number;
  name: string;
}

interface SpawnFormEntry {
  location_id: number;
  location_name: string;
  spawn_chance: number;
  max_active: number;
  is_enabled: boolean;
}

const AdminMobSpawns = ({ templateId, spawns, onUpdate }: AdminMobSpawnsProps) => {
  const dispatch = useAppDispatch();
  const saving = useAppSelector(selectMobsSaving);

  const [entries, setEntries] = useState<SpawnFormEntry[]>(
    spawns.map((s) => ({
      location_id: s.location_id,
      location_name: s.location_name || `Локация #${s.location_id}`,
      spawn_chance: s.spawn_chance,
      max_active: s.max_active,
      is_enabled: s.is_enabled,
    })),
  );

  const [locations, setLocations] = useState<LocationOption[]>([]);

  const fetchLocations = useCallback(async () => {
    try {
      const res = await axios.get<LocationOption[]>('/locations/locations/lookup');
      setLocations(res.data);
    } catch {
      // Not critical
    }
  }, []);

  useEffect(() => {
    fetchLocations();
  }, [fetchLocations]);

  useEffect(() => {
    setEntries(
      spawns.map((s) => ({
        location_id: s.location_id,
        location_name: s.location_name || `Локация #${s.location_id}`,
        spawn_chance: s.spawn_chance,
        max_active: s.max_active,
        is_enabled: s.is_enabled,
      })),
    );
  }, [spawns]);

  const handleAddLocation = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const locationId = Number(e.target.value);
    if (!locationId) return;
    if (entries.some((en) => en.location_id === locationId)) {
      toast.error('Эта локация уже добавлена');
      e.target.value = '';
      return;
    }
    const loc = locations.find((l) => l.id === locationId);
    setEntries((prev) => [
      ...prev,
      {
        location_id: locationId,
        location_name: loc?.name || `Локация #${locationId}`,
        spawn_chance: 5,
        max_active: 1,
        is_enabled: true,
      },
    ]);
    e.target.value = '';
  };

  const handleRemoveEntry = (locationId: number) => {
    setEntries((prev) => prev.filter((e) => e.location_id !== locationId));
  };

  const handleEntryChange = (
    locationId: number,
    field: 'spawn_chance' | 'max_active',
    value: string,
  ) => {
    setEntries((prev) =>
      prev.map((e) =>
        e.location_id === locationId
          ? { ...e, [field]: value === '' ? 0 : Number(value) }
          : e,
      ),
    );
  };

  const handleToggleEnabled = (locationId: number) => {
    setEntries((prev) =>
      prev.map((e) =>
        e.location_id === locationId
          ? { ...e, is_enabled: !e.is_enabled }
          : e,
      ),
    );
  };

  const validate = (): boolean => {
    for (const entry of entries) {
      if (entry.spawn_chance < 0 || entry.spawn_chance > 100) {
        toast.error(`Шанс спавна для "${entry.location_name}" должен быть от 0 до 100`);
        return false;
      }
      if (entry.max_active < 1) {
        toast.error(`Максимум активных для "${entry.location_name}" должен быть не менее 1`);
        return false;
      }
    }
    return true;
  };

  const handleSave = async () => {
    if (!validate()) return;
    try {
      await dispatch(
        updateMobSpawns({
          templateId,
          spawns: entries.map((e) => ({
            location_id: e.location_id,
            spawn_chance: e.spawn_chance,
            max_active: e.max_active,
            is_enabled: e.is_enabled,
          })),
        }),
      ).unwrap();
      onUpdate();
    } catch {
      // Error already shown by thunk
    }
  };

  // Filter out already-added locations
  const availableLocations = locations.filter(
    (loc) => !entries.some((e) => e.location_id === loc.id),
  );

  return (
    <div className="flex flex-col gap-5">
      <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
        Конфигурация спавна ({entries.length} локаций)
      </h3>

      {/* Current entries */}
      {entries.length > 0 && (
        <div className="flex flex-col gap-3">
          {entries.map((entry) => (
            <div
              key={entry.location_id}
              className={`bg-white/[0.05] rounded-card p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3 ${
                !entry.is_enabled ? 'opacity-50' : ''
              }`}
            >
              <div className="flex-1 min-w-0">
                <span className="text-white text-sm font-medium truncate block">
                  {entry.location_name}
                </span>
                <span className="text-white/40 text-xs">ID: {entry.location_id}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:gap-3 sm:w-auto">
                <label className="flex flex-col gap-0.5">
                  <span className="text-white/50 text-[10px] uppercase">Шанс %</span>
                  <input
                    type="number"
                    value={entry.spawn_chance}
                    onChange={(e) => handleEntryChange(entry.location_id, 'spawn_chance', e.target.value)}
                    min={0}
                    max={100}
                    step={0.1}
                    className="input-underline !text-sm w-full"
                  />
                </label>
                <label className="flex flex-col gap-0.5">
                  <span className="text-white/50 text-[10px] uppercase">Макс</span>
                  <input
                    type="number"
                    value={entry.max_active}
                    onChange={(e) => handleEntryChange(entry.location_id, 'max_active', e.target.value)}
                    min={1}
                    className="input-underline !text-sm w-full"
                  />
                </label>
              </div>
              <label className="flex items-center gap-2 cursor-pointer shrink-0">
                <input
                  type="checkbox"
                  checked={entry.is_enabled}
                  onChange={() => handleToggleEnabled(entry.location_id)}
                  className="w-4 h-4 accent-gold"
                />
                <span className="text-white/70 text-xs">Вкл</span>
              </label>
              <button
                onClick={() => handleRemoveEntry(entry.location_id)}
                className="text-sm text-site-red hover:text-white transition-colors self-start sm:self-center shrink-0"
              >
                Удалить
              </button>
            </div>
          ))}
        </div>
      )}

      {entries.length === 0 && (
        <p className="text-white/50 text-sm">Спавн-правила не настроены. Добавьте локации ниже.</p>
      )}

      {/* Add location */}
      <div>
        <h4 className="text-white/70 text-xs font-medium uppercase tracking-[0.06em] mb-2">
          Добавить локацию
        </h4>
        <select
          className="input-underline max-w-[320px]"
          defaultValue=""
          onChange={handleAddLocation}
        >
          <option value="" className="bg-site-dark text-white">Выберите локацию...</option>
          {availableLocations.map((loc) => (
            <option key={loc.id} value={loc.id} className="bg-site-dark text-white">
              {loc.name}
            </option>
          ))}
        </select>
      </div>

      {/* Save */}
      <div className="pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
        >
          {saving ? 'Сохранение...' : 'Сохранить конфигурацию спавна'}
        </button>
      </div>
    </div>
  );
};

export default AdminMobSpawns;
