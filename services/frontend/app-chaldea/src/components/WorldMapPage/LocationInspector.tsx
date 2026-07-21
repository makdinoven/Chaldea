import { useEffect, useMemo, useRef, useState } from 'react';
import type { GraphDistrict, GraphLocation, GraphRegion, MarkerType } from '../../api/worldGraph';
import {
  createNeighbor,
  deleteNeighbor,
  editorErrorMessage,
  fetchLocationDetails,
  updateLocation,
  uploadLocationImage,
  type LocationDetails,
  type LocationFormValues,
} from '../../api/mapEditor';
import LocationPicker from './LocationPicker';
import { MARKER_COLORS, MARKER_LABELS } from './theme';

interface NeighbourRow {
  id: number;
  cost: number;
}

interface LocationInspectorProps {
  locationId: number;
  locations: GraphLocation[];
  locationById: Map<number, GraphLocation>;
  regions: GraphRegion[];
  districts: GraphDistrict[];
  regionNames: Map<number, string>;
  neighbours: NeighbourRow[];
  canEdit: boolean;
  canDelete: boolean;
  onSaved: (locationId: number, values: LocationFormValues) => void;
  onNeighbourAdded: (fromId: number, toId: number, cost: number) => void;
  onNeighbourRemoved: (fromId: number, toId: number) => void;
  onClose: () => void;
  onFocusLocation: (locationId: number) => void;
}

const MARKER_OPTIONS: MarkerType[] = ['safe', 'dangerous', 'dungeon', 'farm'];

const LocationInspector = ({
  locationId,
  locations,
  locationById,
  regions,
  districts,
  regionNames,
  neighbours,
  canEdit,
  canDelete,
  onSaved,
  onNeighbourAdded,
  onNeighbourRemoved,
  onClose,
  onFocusLocation,
}: LocationInspectorProps) => {
  const [details, setDetails] = useState<LocationDetails | null>(null);
  const [form, setForm] = useState<LocationFormValues | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [newNeighbour, setNewNeighbour] = useState<number | null>(null);
  const [newCost, setNewCost] = useState('1');
  const [addingNeighbour, setAddingNeighbour] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotice(null);
    setNewNeighbour(null);
    setNewCost('1');
    fetchLocationDetails(locationId)
      .then((data) => {
        if (cancelled) return;
        setDetails(data);
        setImageUrl(data.image_url || null);
        setForm({
          name: data.name,
          description: data.description ?? '',
          recommended_level: data.recommended_level ?? 1,
          marker_type: data.marker_type ?? 'safe',
          quick_travel_marker: Boolean(data.quick_travel_marker),
          no_quick_move: Boolean(data.no_quick_move),
          district_id: data.district_id,
          region_id: data.region_id,
        });
      })
      .catch((caught) => {
        if (!cancelled) setError(editorErrorMessage(caught, 'Не удалось загрузить локацию.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [locationId]);

  /**
   * The backend rejects a location that belongs to neither a district nor a
   * region, so the district list is scoped to the chosen region and clearing
   * the district requires a region to fall back on.
   */
  const districtsOfRegion = useMemo(() => {
    if (!form?.region_id) return districts;
    return districts.filter((district) => district.region_id === form.region_id);
  }, [districts, form?.region_id]);

  const neighbourCandidates = useMemo(() => {
    const taken = new Set(neighbours.map((row) => row.id));
    taken.add(locationId);
    return locations.filter((location) => !taken.has(location.id));
  }, [locations, neighbours, locationId]);

  const update = <K extends keyof LocationFormValues>(key: K, value: LocationFormValues[K]) => {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setNotice(null);
  };

  const save = async () => {
    if (!form || saving) return;
    if (!form.name.trim()) {
      setError('Название не может быть пустым.');
      return;
    }
    if (form.district_id === null && form.region_id === null) {
      setError('Локация должна принадлежать району или региону.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateLocation(locationId, { ...form, name: form.name.trim() });
      onSaved(locationId, { ...form, name: form.name.trim() });
      setNotice('Сохранено.');
    } catch (caught) {
      setError(editorErrorMessage(caught, 'Не удалось сохранить локацию.'));
    } finally {
      setSaving(false);
    }
  };

  const onPickImage = async (file: File | undefined) => {
    if (!file || uploading) return;
    setUploading(true);
    setError(null);
    try {
      const url = await uploadLocationImage(locationId, file);
      setImageUrl(url);
      setNotice('Изображение обновлено.');
    } catch (caught) {
      setError(editorErrorMessage(caught, 'Не удалось загрузить изображение.'));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const addNeighbour = async () => {
    const cost = Number(newCost);
    if (newNeighbour === null || addingNeighbour) return;
    if (!Number.isInteger(cost) || cost < 0 || cost > 1000) {
      setError('Стоимость перехода — целое число от 0 до 1000.');
      return;
    }
    setAddingNeighbour(true);
    setError(null);
    try {
      await createNeighbor(locationId, newNeighbour, cost);
      onNeighbourAdded(locationId, newNeighbour, cost);
      setNewNeighbour(null);
      setNewCost('1');
      setNotice('Переход добавлен.');
    } catch (caught) {
      setError(editorErrorMessage(caught, 'Не удалось добавить переход.'));
    } finally {
      setAddingNeighbour(false);
    }
  };

  const removeNeighbour = async (neighbourId: number) => {
    setError(null);
    try {
      await deleteNeighbor(locationId, neighbourId);
      onNeighbourRemoved(locationId, neighbourId);
    } catch (caught) {
      setError(editorErrorMessage(caught, 'Не удалось удалить переход.'));
    }
  };

  const header = (
    <div className="flex items-start justify-between gap-2">
      <h2 className="gold-text text-[15px] font-semibold">
        {canEdit ? 'Редактирование локации' : 'Локация'}
      </h2>
      <button
        type="button"
        aria-label="Закрыть"
        className="text-white/40 transition-colors hover:text-site-red"
        onClick={onClose}
      >
        ✕
      </button>
    </div>
  );

  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        {header}
        <p className="text-[12px] text-white/45">Загрузка…</p>
      </div>
    );
  }

  if (!form || !details) {
    return (
      <div className="flex flex-col gap-3">
        {header}
        <p className="text-[12px] text-site-red">{error ?? 'Локация недоступна.'}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {header}

      <fieldset disabled={!canEdit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wide text-white/45">Название</span>
          <input
            type="text"
            className="input-underline text-[14px]"
            value={form.name}
            onChange={(event) => update('name', event.target.value)}
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wide text-white/45">Описание</span>
          <textarea
            rows={4}
            className="textarea-bordered text-[13px]"
            value={form.description}
            onChange={(event) => update('description', event.target.value)}
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-white/45">Уровень</span>
            <input
              type="number"
              min={0}
              className="input-underline text-[14px]"
              value={form.recommended_level}
              onChange={(event) => update('recommended_level', Number(event.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-white/45">Тип</span>
            <select
              className="input-underline bg-transparent text-[13px]"
              value={form.marker_type}
              onChange={(event) => update('marker_type', event.target.value as MarkerType)}
            >
              {MARKER_OPTIONS.map((marker) => (
                <option key={marker} value={marker} className="bg-[#0d0e15]">
                  {MARKER_LABELS[marker]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-white/45">Регион</span>
            <select
              className="input-underline bg-transparent text-[13px]"
              value={form.region_id ?? ''}
              onChange={(event) => {
                const value = event.target.value ? Number(event.target.value) : null;
                setForm((current) =>
                  current ? { ...current, region_id: value, district_id: null } : current,
                );
              }}
            >
              <option value="" className="bg-[#0d0e15]">— не задан —</option>
              {regions.map((region) => (
                <option key={region.id} value={region.id} className="bg-[#0d0e15]">
                  {region.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-white/45">Район</span>
            <select
              className="input-underline bg-transparent text-[13px]"
              value={form.district_id ?? ''}
              onChange={(event) =>
                update('district_id', event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="" className="bg-[#0d0e15]">— без района —</option>
              {districtsOfRegion.map((district) => (
                <option key={district.id} value={district.id} className="bg-[#0d0e15]">
                  {district.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-[12px] text-white/70">
            <input
              type="checkbox"
              className="gold-checkbox"
              checked={form.quick_travel_marker}
              onChange={(event) => update('quick_travel_marker', event.target.checked)}
            />
            Точка быстрого перемещения
          </label>
          <label className="flex items-center gap-2 text-[12px] text-white/70">
            <input
              type="checkbox"
              className="gold-checkbox"
              checked={form.no_quick_move}
              onChange={(event) => update('no_quick_move', event.target.checked)}
            />
            Запретить быстрое перемещение сюда
          </label>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-[10px] uppercase tracking-wide text-white/45">Изображение</span>
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={form.name}
              className="h-28 w-full rounded-lg object-cover"
            />
          ) : (
            <div className="flex h-28 w-full items-center justify-center rounded-lg border border-dashed
                            border-white/15 text-[11px] text-white/35">
              Нет изображения
            </div>
          )}
          {canEdit && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => onPickImage(event.target.files?.[0])}
              />
              <button
                type="button"
                className="btn-line text-[12px]"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
              >
                {uploading ? 'Загрузка…' : 'Заменить изображение'}
              </button>
            </>
          )}
        </div>
      </fieldset>

      {error && <p className="text-[12px] leading-snug text-site-red">{error}</p>}
      {notice && <p className="text-[12px] text-[#5fb98f]">{notice}</p>}

      {canEdit && (
        <button
          type="button"
          className="btn-blue text-[12px] disabled:cursor-not-allowed disabled:opacity-40"
          disabled={saving}
          onClick={save}
        >
          {saving ? 'Сохранение…' : 'Сохранить локацию'}
        </button>
      )}

      <div className="gradient-divider-h" />

      <div className="flex flex-col gap-2">
        <span className="text-[10px] uppercase tracking-wide text-white/45">
          Переходы ({neighbours.length})
        </span>

        {neighbours.length === 0 && (
          <p className="text-[11px] text-white/40">
            У локации нет переходов — она изолирована от остального мира.
          </p>
        )}

        <ul className="gold-scrollbar flex max-h-52 flex-col gap-1 overflow-y-auto pr-1">
          {neighbours.map((row) => (
            <li key={row.id} className="flex items-center gap-2">
              <button
                type="button"
                className="min-w-0 flex-1 truncate rounded px-1 py-1 text-left text-[12px] text-white/75
                           transition-colors hover:bg-white/5"
                onClick={() => onFocusLocation(row.id)}
              >
                {locationById.get(row.id)?.name ?? `#${row.id}`}
                <span className="ml-2 text-[10px] text-white/35">
                  {regionNames.get(locationById.get(row.id)?.region_id ?? -1) ?? '—'}
                </span>
              </button>
              <span className="shrink-0 text-[11px] text-gold">{row.cost}</span>
              {canDelete && (
                <button
                  type="button"
                  aria-label={`Удалить переход к ${locationById.get(row.id)?.name ?? row.id}`}
                  className="shrink-0 px-1 text-white/35 transition-colors hover:text-site-red"
                  onClick={() => removeNeighbour(row.id)}
                >
                  ✕
                </button>
              )}
            </li>
          ))}
        </ul>

        {canEdit && (
          <div className="flex flex-col gap-2 rounded-lg border border-white/10 p-2">
            <span className="text-[10px] uppercase tracking-wide text-white/45">
              Добавить переход
            </span>
            <LocationPicker
              locations={neighbourCandidates}
              regionNames={regionNames}
              value={newNeighbour}
              onChange={setNewNeighbour}
              placeholder="Куда ведёт переход…"
              accentColor={MARKER_COLORS.safe}
            />
            <div className="flex items-center gap-2">
              <label className="flex flex-1 items-center gap-2">
                <span className="text-[11px] text-white/45">Стоимость</span>
                <input
                  type="number"
                  min={0}
                  max={1000}
                  className="input-underline w-16 text-[13px]"
                  value={newCost}
                  onChange={(event) => setNewCost(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn-line text-[12px] disabled:cursor-not-allowed disabled:opacity-40"
                disabled={newNeighbour === null || addingNeighbour}
                onClick={addNeighbour}
              >
                {addingNeighbour ? 'Добавление…' : 'Добавить'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LocationInspector;
