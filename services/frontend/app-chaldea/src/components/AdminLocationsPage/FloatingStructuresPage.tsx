import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { uploadArchiveImage } from '../../api/archive';
import { useRequireAuth } from '../../hooks/useRequireAuth';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchAdminFloatingStructures,
  createFloatingStructure,
  updateFloatingStructure,
  deleteFloatingStructure,
  selectFloatingStructures,
  selectFloatingStructuresLoading,
  selectFloatingStructuresSaving,
  selectFloatingStructuresError,
} from '../../redux/slices/floatingStructuresSlice';
import type {
  FloatingStructure,
  FloatingStructureCreatePayload,
} from '../../redux/slices/floatingStructuresSlice';
import { selectAreas } from '../../redux/slices/worldMapSlice';
import { fetchAreas } from '../../redux/actions/worldMapActions';
import FloatingRouteEditor from './FloatingRouteEditor';

interface FormState {
  name: string;
  description: string;
  icon_url: string;
  travel_days: string;
  internal_district_id: string;
  area_id: string;
}

/** Convert speed (progress per second) to travel time in days. */
const speedToDays = (speed: number): number => {
  if (!Number.isFinite(speed) || speed <= 0) return 30;
  const days = Math.round(1 / (speed * 86400));
  return days < 1 ? 1 : days;
};

/** Convert travel time in days to speed (progress per second). */
const daysToSpeed = (days: number): number => 1 / (days * 86400);

const emptyForm: FormState = {
  name: '',
  description: '',
  icon_url: '',
  travel_days: '30',
  internal_district_id: '',
  area_id: '',
};

const FloatingStructuresPage = () => {
  useRequireAuth();
  const dispatch = useAppDispatch();
  const items = useAppSelector(selectFloatingStructures);
  const loading = useAppSelector(selectFloatingStructuresLoading);
  const saving = useAppSelector(selectFloatingStructuresSaving);
  const error = useAppSelector(selectFloatingStructuresError);
  const areas = useAppSelector(selectAreas);

  const [form, setForm] = useState<FormState>({ ...emptyForm });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [routeEditorFor, setRouteEditorFor] = useState<FloatingStructure | null>(null);
  const [iconUploading, setIconUploading] = useState(false);
  const iconFileInputRef = useRef<HTMLInputElement | null>(null);

  const handleIconFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIconUploading(true);
    try {
      const { image_url } = await uploadArchiveImage(file);
      setForm((prev) => ({ ...prev, icon_url: image_url }));
      toast.success('Иконка загружена');
    } catch (err) {
      console.error('Icon upload failed:', err);
      toast.error('Не удалось загрузить иконку');
    } finally {
      setIconUploading(false);
      if (iconFileInputRef.current) iconFileInputRef.current.value = '';
    }
  };

  useEffect(() => {
    dispatch(fetchAdminFloatingStructures());
    if (areas.length === 0) {
      dispatch(fetchAreas());
    }
  }, [dispatch]); // eslint-disable-line react-hooks/exhaustive-deps

  const resetForm = () => {
    setForm({ ...emptyForm });
    setEditingId(null);
  };

  const handleEdit = (item: FloatingStructure) => {
    setEditingId(item.id);
    setForm({
      name: item.name,
      description: item.description ?? '',
      icon_url: item.icon_url ?? '',
      travel_days: String(speedToDays(item.speed ?? 0)),
      internal_district_id:
        item.internal_district_id !== null && item.internal_district_id !== undefined
          ? String(item.internal_district_id)
          : '',
      area_id:
        item.area_id !== null && item.area_id !== undefined
          ? String(item.area_id)
          : '',
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const travelDays = Math.round(Number(form.travel_days));
    if (!form.name.trim()) {
      return;
    }
    if (!Number.isFinite(travelDays) || travelDays < 1) {
      return;
    }
    const districtId = form.internal_district_id.trim()
      ? Number(form.internal_district_id)
      : null;
    if (districtId !== null && (!Number.isInteger(districtId) || districtId <= 0)) {
      return;
    }
    const areaId = form.area_id.trim() ? Number(form.area_id) : null;
    if (areaId !== null && (!Number.isInteger(areaId) || areaId <= 0)) {
      return;
    }

    const payload: FloatingStructureCreatePayload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      icon_url: form.icon_url.trim() || null,
      speed: daysToSpeed(travelDays),
      // started_at is set automatically: now for new structures, unchanged for edits
      started_at: editingId ? undefined : new Date().toISOString(),
      internal_district_id: districtId,
      area_id: areaId,
      // route_json is required by API; for new structures start with an empty
      // closed loop placeholder — admin then opens the route editor to draw it.
      route_json: editingId ? (items.find((it) => it.id === editingId)?.route_json ?? []) : [],
    };

    if (editingId) {
      await dispatch(updateFloatingStructure({ id: editingId, payload }));
    } else {
      await dispatch(createFloatingStructure(payload));
    }
    resetForm();
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Удалить плавающую структуру?')) return;
    await dispatch(deleteFloatingStructure(id));
    if (editingId === id) resetForm();
  };

  return (
    <div className="container mx-auto px-3 sm:px-6 py-4 sm:py-6 text-white">
      <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase mb-4 sm:mb-6">
        Плавающие структуры
      </h1>

      {error && (
        <div className="mb-4 rounded-md border border-site-red/40 bg-site-red/10 p-3 text-sm text-site-red">
          {error}
        </div>
      )}

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        className="mb-6 grid grid-cols-1 gap-3 rounded-lg border border-white/10 bg-site-dark/40 p-4 sm:grid-cols-2 sm:p-5"
      >
        <h2 className="col-span-full text-lg font-medium gold-text">
          {editingId ? `Редактирование #${editingId}` : 'Создание новой структуры'}
        </h2>

        <label className="flex flex-col text-sm">
          <span className="mb-1 text-white/70">Название*</span>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
            className="input-underline px-3 py-2 bg-transparent border border-white/20 rounded"
          />
        </label>

        <div className="flex flex-col text-sm">
          <span className="mb-1 text-white/70">Иконка</span>
          <div className="flex items-center gap-3 flex-wrap">
            {form.icon_url ? (
              <img
                src={form.icon_url}
                alt="icon"
                className="w-12 h-12 rounded object-cover border border-white/10 flex-shrink-0"
              />
            ) : (
              <div className="w-12 h-12 rounded border border-dashed border-white/20 flex items-center justify-center text-[10px] text-white/40 flex-shrink-0">
                нет
              </div>
            )}
            <input
              ref={iconFileInputRef}
              type="file"
              accept="image/*"
              onChange={handleIconFileChange}
              disabled={iconUploading}
              className="text-xs text-white/70 file:mr-2 file:rounded file:border-0 file:bg-site-blue/30 file:px-3 file:py-1.5 file:text-xs file:text-white hover:file:bg-site-blue/50 file:cursor-pointer disabled:opacity-50 min-w-0 flex-1"
            />
            {form.icon_url && (
              <button
                type="button"
                onClick={() => setForm((prev) => ({ ...prev, icon_url: '' }))}
                className="btn-line px-2 py-1 text-xs text-site-red border-site-red/40"
              >
                Очистить
              </button>
            )}
          </div>
          {iconUploading && (
            <span className="mt-1 text-xs text-white/50">Загрузка...</span>
          )}
          <input
            type="text"
            value={form.icon_url}
            onChange={(e) => setForm({ ...form, icon_url: e.target.value })}
            placeholder="или вставьте URL вручную"
            className="mt-2 input-underline px-3 py-2 bg-transparent border border-white/20 rounded text-xs"
          />
        </div>

        <label className="col-span-full flex flex-col text-sm">
          <span className="mb-1 text-white/70">Описание</span>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={3}
            className="input-underline px-3 py-2 bg-transparent border border-white/20 rounded resize-y"
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="mb-1 text-white/70">Время пути (дней)*</span>
          <input
            type="number"
            step="1"
            min="1"
            value={form.travel_days}
            onChange={(e) => setForm({ ...form, travel_days: e.target.value })}
            required
            className="input-underline px-3 py-2 bg-transparent border border-white/20 rounded"
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="mb-1 text-white/70">ID внутреннего района (District)</span>
          <input
            type="number"
            min="1"
            value={form.internal_district_id}
            onChange={(e) =>
              setForm({ ...form, internal_district_id: e.target.value })
            }
            placeholder="Не привязано"
            className="input-underline px-3 py-2 bg-transparent border border-white/20 rounded"
          />
          <span className="mt-1 text-xs text-white/40">
            Указывается ID существующего района — он будет использован как внутренняя карта структуры.
          </span>
        </label>

        <label className="flex flex-col text-sm">
          <span className="mb-1 text-white/70">Область (Area)</span>
          <select
            value={form.area_id}
            onChange={(e) => setForm({ ...form, area_id: e.target.value })}
            className="input-underline px-3 py-2 bg-transparent border border-white/20 rounded"
          >
            <option value="" className="bg-site-dark">Не указана</option>
            {areas.map((area) => (
              <option key={area.id} value={String(area.id)} className="bg-site-dark">
                {area.name} (ID: {area.id})
              </option>
            ))}
          </select>
          <span className="mt-1 text-xs text-white/40">
            Область, на карте которой отображается структура.
          </span>
        </label>

        <div className="col-span-full flex flex-wrap gap-2 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="btn-blue px-4 py-2 text-sm"
          >
            {saving ? 'Сохранение...' : editingId ? 'Сохранить' : 'Создать'}
          </button>
          {editingId && (
            <button
              type="button"
              onClick={resetForm}
              className="btn-line px-4 py-2 text-sm"
            >
              Отмена
            </button>
          )}
        </div>
      </form>

      {/* List */}
      <h2 className="gold-text text-xl font-medium mb-3">Список</h2>
      {loading && items.length === 0 ? (
        <div className="text-white/60 text-sm">Загрузка...</div>
      ) : items.length === 0 ? (
        <div className="text-white/60 text-sm">Нет записей</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="rounded-lg border border-white/10 bg-site-dark/40 p-4 flex flex-col gap-2"
            >
              <div className="flex items-center gap-3">
                {item.icon_url && (
                  <img
                    src={item.icon_url}
                    alt={item.name}
                    className="h-10 w-10 rounded object-cover border border-white/10"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-white font-medium truncate">
                    {item.name}
                  </div>
                  <div className="text-xs text-white/50">ID: {item.id}</div>
                </div>
              </div>
              {item.description && (
                <div className="text-xs text-white/60 line-clamp-2">
                  {item.description}
                </div>
              )}
              <div className="text-xs text-white/50 grid grid-cols-2 gap-1">
                <div>Путь: {speedToDays(item.speed)} дн.</div>
                <div>Точек: {item.route_json?.length ?? 0}</div>
                <div className="col-span-2">
                  District: {item.internal_district_id ?? '—'}
                </div>
                <div className="col-span-2">
                  Область:{' '}
                  {item.area_id != null
                    ? (areas.find((a) => a.id === item.area_id)?.name ?? `ID: ${item.area_id}`)
                    : '—'}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleEdit(item)}
                  className="btn-line px-3 py-1.5 text-xs"
                >
                  Редактировать
                </button>
                <button
                  type="button"
                  onClick={() => setRouteEditorFor(item)}
                  className="btn-blue px-3 py-1.5 text-xs"
                >
                  Редактировать маршрут
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(item.id)}
                  className="btn-line px-3 py-1.5 text-xs text-site-red border-site-red/40"
                >
                  Удалить
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {routeEditorFor && (
        <FloatingRouteEditor
          structureId={routeEditorFor.id}
          initialRoute={routeEditorFor.route_json ?? []}
          areaId={routeEditorFor.area_id}
          onClose={() => setRouteEditorFor(null)}
        />
      )}
    </div>
  );
};

export default FloatingStructuresPage;
