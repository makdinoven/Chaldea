import { useEffect, useState } from 'react';
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
import FloatingRouteEditor from './FloatingRouteEditor';

interface FormState {
  name: string;
  description: string;
  icon_url: string;
  speed: string;
  started_at: string; // datetime-local string
  internal_district_id: string;
}

const emptyForm: FormState = {
  name: '',
  description: '',
  icon_url: '',
  speed: '0.0001',
  started_at: '',
  internal_district_id: '',
};

const toLocalInputValue = (iso: string | null | undefined): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  // Format: YYYY-MM-DDTHH:mm
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const fromLocalInputValue = (value: string): string | null => {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
};

const nowLocalValue = (): string => {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const FloatingStructuresPage = () => {
  useRequireAuth();
  const dispatch = useAppDispatch();
  const items = useAppSelector(selectFloatingStructures);
  const loading = useAppSelector(selectFloatingStructuresLoading);
  const saving = useAppSelector(selectFloatingStructuresSaving);
  const error = useAppSelector(selectFloatingStructuresError);

  const [form, setForm] = useState<FormState>({ ...emptyForm, started_at: nowLocalValue() });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [routeEditorFor, setRouteEditorFor] = useState<FloatingStructure | null>(null);

  useEffect(() => {
    dispatch(fetchAdminFloatingStructures());
  }, [dispatch]);

  const resetForm = () => {
    setForm({ ...emptyForm, started_at: nowLocalValue() });
    setEditingId(null);
  };

  const handleEdit = (item: FloatingStructure) => {
    setEditingId(item.id);
    setForm({
      name: item.name,
      description: item.description ?? '',
      icon_url: item.icon_url ?? '',
      speed: String(item.speed ?? 0),
      started_at: toLocalInputValue(item.started_at) || nowLocalValue(),
      internal_district_id:
        item.internal_district_id !== null && item.internal_district_id !== undefined
          ? String(item.internal_district_id)
          : '',
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const speedNum = Number(form.speed);
    if (!form.name.trim()) {
      return;
    }
    if (!Number.isFinite(speedNum) || speedNum <= 0) {
      return;
    }
    const districtId = form.internal_district_id.trim()
      ? Number(form.internal_district_id)
      : null;
    if (districtId !== null && (!Number.isInteger(districtId) || districtId <= 0)) {
      return;
    }

    const payload: FloatingStructureCreatePayload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      icon_url: form.icon_url.trim() || null,
      speed: speedNum,
      started_at: fromLocalInputValue(form.started_at),
      internal_district_id: districtId,
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

        <label className="flex flex-col text-sm">
          <span className="mb-1 text-white/70">Иконка (URL)</span>
          <input
            type="text"
            value={form.icon_url}
            onChange={(e) => setForm({ ...form, icon_url: e.target.value })}
            placeholder="https://..."
            className="input-underline px-3 py-2 bg-transparent border border-white/20 rounded"
          />
        </label>

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
          <span className="mb-1 text-white/70">
            Скорость (доля маршрута в секунду)*
          </span>
          <input
            type="number"
            step="any"
            min="0"
            value={form.speed}
            onChange={(e) => setForm({ ...form, speed: e.target.value })}
            required
            className="input-underline px-3 py-2 bg-transparent border border-white/20 rounded"
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="mb-1 text-white/70">Начало движения</span>
          <input
            type="datetime-local"
            value={form.started_at}
            onChange={(e) => setForm({ ...form, started_at: e.target.value })}
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
                <div>Скорость: {item.speed}</div>
                <div>Точек: {item.route_json?.length ?? 0}</div>
                <div className="col-span-2">
                  District: {item.internal_district_id ?? '—'}
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
          onClose={() => setRouteEditorFor(null)}
        />
      )}
    </div>
  );
};

export default FloatingStructuresPage;
