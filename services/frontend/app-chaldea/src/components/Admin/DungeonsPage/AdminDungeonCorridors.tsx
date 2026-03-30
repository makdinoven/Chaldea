import { useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import type { DungeonRoom, DungeonCorridor } from '../../../api/dungeons';

interface AdminDungeonCorridorsProps {
  dungeonId: number;
  rooms: DungeonRoom[];
  corridors: DungeonCorridor[];
  onUpdate: () => void;
}

interface CorridorFormState {
  from_room_id: number | '';
  to_room_id: number | '';
  stamina_cost: number;
  is_bidirectional: boolean;
  random_battle_chance: number;
  random_battle_mob_ids: string;
  trap_chance: number;
  trap_stat_check: string;
  trap_difficulty: number;
  trap_fail_damage: number;
  description: string;
}

const INITIAL_CORRIDOR_FORM: CorridorFormState = {
  from_room_id: '',
  to_room_id: '',
  stamina_cost: 5,
  is_bidirectional: true,
  random_battle_chance: 0,
  random_battle_mob_ids: '',
  trap_chance: 0,
  trap_stat_check: 'agility',
  trap_difficulty: 10,
  trap_fail_damage: 15,
  description: '',
};

const STAT_OPTIONS = [
  { value: 'strength', label: 'Сила' },
  { value: 'agility', label: 'Ловкость' },
  { value: 'intelligence', label: 'Интеллект' },
  { value: 'endurance', label: 'Выносливость' },
  { value: 'charisma', label: 'Харизма' },
  { value: 'luck', label: 'Удача' },
];

const AdminDungeonCorridors = ({ dungeonId, rooms, corridors, onUpdate }: AdminDungeonCorridorsProps) => {
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<CorridorFormState>({ ...INITIAL_CORRIDOR_FORM });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);

  const roomMap = new Map(rooms.map((r) => [r.id, r.name]));

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...INITIAL_CORRIDOR_FORM });
    setFormOpen(true);
  };

  const openEdit = (corridor: DungeonCorridor) => {
    setEditingId(corridor.id);
    const trapConfig = (corridor.trap_config || {}) as Record<string, unknown>;
    setForm({
      from_room_id: corridor.from_room_id,
      to_room_id: corridor.to_room_id,
      stamina_cost: corridor.stamina_cost,
      is_bidirectional: corridor.is_bidirectional,
      random_battle_chance: corridor.random_battle_chance,
      random_battle_mob_ids: (corridor.random_battle_mob_ids || []).join(', '),
      trap_chance: corridor.trap_chance,
      trap_stat_check: (trapConfig.stat_check as string) || 'agility',
      trap_difficulty: (trapConfig.difficulty as number) || 10,
      trap_fail_damage: (trapConfig.fail_damage as number) || 15,
      description: corridor.description || '',
    });
    setFormOpen(true);
  };

  const handleDelete = async (corridorId: number) => {
    if (!window.confirm('Удалить этот коридор?')) return;
    setDeleting(corridorId);
    try {
      await axios.delete(`/dungeons/admin/corridors/${corridorId}`);
      toast.success('Коридор удалён');
      onUpdate();
    } catch {
      toast.error('Не удалось удалить коридор');
    } finally {
      setDeleting(null);
    }
  };

  const updateField = <K extends keyof CorridorFormState>(key: K, value: CorridorFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const parseMobIds = (str: string): number[] => {
    return str
      .split(/[,\s]+/)
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.from_room_id || !form.to_room_id) {
      toast.error('Выберите обе комнаты');
      return;
    }
    if (form.from_room_id === form.to_room_id) {
      toast.error('Комнаты не могут совпадать');
      return;
    }

    setSaving(true);
    const trapConfig =
      form.trap_chance > 0
        ? {
            stat_check: form.trap_stat_check,
            difficulty: form.trap_difficulty,
            fail_damage: form.trap_fail_damage,
          }
        : null;

    const payload = {
      from_room_id: Number(form.from_room_id),
      to_room_id: Number(form.to_room_id),
      stamina_cost: form.stamina_cost,
      is_bidirectional: form.is_bidirectional,
      random_battle_chance: form.random_battle_chance,
      random_battle_mob_ids: parseMobIds(form.random_battle_mob_ids).length > 0 ? parseMobIds(form.random_battle_mob_ids) : null,
      trap_chance: form.trap_chance,
      trap_config: trapConfig,
      description: form.description.trim() || null,
    };

    try {
      if (editingId !== null) {
        await axios.put(`/dungeons/admin/corridors/${editingId}`, payload);
        toast.success('Коридор обновлён');
      } else {
        await axios.post(`/dungeons/admin/dungeons/${dungeonId}/corridors`, payload);
        toast.success('Коридор создан');
      }
      setFormOpen(false);
      setEditingId(null);
      onUpdate();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? String(err.response.data.detail)
          : 'Не удалось сохранить коридор';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h2 className="text-white text-lg font-medium uppercase tracking-[0.06em]">
          Коридоры ({corridors.length})
        </h2>
        <button className="btn-blue !text-base !px-6 !py-2" onClick={openCreate}>
          Добавить коридор
        </button>
      </div>

      {/* Form */}
      {formOpen && (
        <form onSubmit={handleSubmit} className="gray-bg p-4 sm:p-6 flex flex-col gap-4">
          <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
            {editingId !== null ? 'Редактировать коридор' : 'Новый коридор'}
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Из комнаты *</label>
              <select
                className="input-underline"
                value={form.from_room_id}
                onChange={(e) => updateField('from_room_id', e.target.value ? Number(e.target.value) : '')}
              >
                <option value="" className="bg-site-dark text-white">— Выберите —</option>
                {rooms.map((r) => (
                  <option key={r.id} value={r.id} className="bg-site-dark text-white">
                    {r.name} ({r.room_type})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">В комнату *</label>
              <select
                className="input-underline"
                value={form.to_room_id}
                onChange={(e) => updateField('to_room_id', e.target.value ? Number(e.target.value) : '')}
              >
                <option value="" className="bg-site-dark text-white">— Выберите —</option>
                {rooms.map((r) => (
                  <option key={r.id} value={r.id} className="bg-site-dark text-white">
                    {r.name} ({r.room_type})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Стамина</label>
              <input
                type="number"
                className="input-underline"
                value={form.stamina_cost}
                min={0}
                onChange={(e) => updateField('stamina_cost', Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Шанс боя (0-1)</label>
              <input
                type="number"
                className="input-underline"
                value={form.random_battle_chance}
                step={0.05}
                min={0}
                max={1}
                onChange={(e) => updateField('random_battle_chance', Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Шанс ловушки (0-1)</label>
              <input
                type="number"
                className="input-underline"
                value={form.trap_chance}
                step={0.05}
                min={0}
                max={1}
                onChange={(e) => updateField('trap_chance', Number(e.target.value))}
              />
            </div>
          </div>

          {form.random_battle_chance > 0 && (
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">ID мобов для боя (через запятую)</label>
              <input
                className="input-underline"
                placeholder="1, 2, 3"
                value={form.random_battle_mob_ids}
                onChange={(e) => updateField('random_battle_mob_ids', e.target.value)}
              />
            </div>
          )}

          {form.trap_chance > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm text-white/70">Характеристика</label>
                <select
                  className="input-underline"
                  value={form.trap_stat_check}
                  onChange={(e) => updateField('trap_stat_check', e.target.value)}
                >
                  {STAT_OPTIONS.map((s) => (
                    <option key={s.value} value={s.value} className="bg-site-dark text-white">
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-white/70">Сложность</label>
                <input
                  type="number"
                  className="input-underline"
                  value={form.trap_difficulty}
                  onChange={(e) => updateField('trap_difficulty', Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-white/70">Урон при провале</label>
                <input
                  type="number"
                  className="input-underline"
                  value={form.trap_fail_damage}
                  onChange={(e) => updateField('trap_fail_damage', Number(e.target.value))}
                />
              </div>
            </div>
          )}

          <div className="flex flex-col gap-2">
            <label className="text-sm text-white/70">Описание</label>
            <input
              className="input-underline"
              placeholder="Узкий тёмный коридор"
              value={form.description}
              onChange={(e) => updateField('description', e.target.value)}
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-white cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_bidirectional}
              onChange={(e) => updateField('is_bidirectional', e.target.checked)}
              className="accent-gold w-4 h-4"
            />
            Двунаправленный (можно идти в обе стороны)
          </label>

          <div className="flex gap-4">
            <button type="submit" disabled={saving} className="btn-blue !text-base !px-6 !py-2">
              {saving ? 'Сохранение...' : editingId !== null ? 'Сохранить' : 'Создать'}
            </button>
            <button
              type="button"
              onClick={() => {
                setFormOpen(false);
                setEditingId(null);
              }}
              className="btn-line !text-base !px-6 !py-2"
            >
              Отмена
            </button>
          </div>
        </form>
      )}

      {/* Table */}
      {corridors.length === 0 ? (
        <p className="text-center text-white/50 text-sm py-8">
          Коридоры ещё не добавлены
        </p>
      ) : (
        <div className="gray-bg overflow-hidden">
          {/* Desktop table */}
          <div className="hidden lg:block">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Из</th>
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">В</th>
                  <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Стамина</th>
                  <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Двунапр.</th>
                  <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Бой %</th>
                  <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Ловушка %</th>
                  <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Действия</th>
                </tr>
              </thead>
              <tbody>
                {corridors.map((c) => (
                  <tr key={c.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200">
                    <td className="px-4 py-3 text-sm text-white">{roomMap.get(c.from_room_id) || `#${c.from_room_id}`}</td>
                    <td className="px-4 py-3 text-sm text-white">{roomMap.get(c.to_room_id) || `#${c.to_room_id}`}</td>
                    <td className="px-4 py-3 text-center text-sm text-white/70">{c.stamina_cost}</td>
                    <td className="px-4 py-3 text-center text-sm">
                      {c.is_bidirectional ? <span className="text-gold">Да</span> : <span className="text-white/30">Нет</span>}
                    </td>
                    <td className="px-4 py-3 text-center text-sm text-white/70">
                      {c.random_battle_chance > 0 ? `${Math.round(c.random_battle_chance * 100)}%` : '—'}
                    </td>
                    <td className="px-4 py-3 text-center text-sm text-white/70">
                      {c.trap_chance > 0 ? `${Math.round(c.trap_chance * 100)}%` : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-end gap-1.5">
                        <button
                          onClick={() => openEdit(c)}
                          className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                        >
                          Редактировать
                        </button>
                        <button
                          onClick={() => handleDelete(c.id)}
                          disabled={deleting === c.id}
                          className="text-sm text-site-red hover:text-white transition-colors duration-200 disabled:opacity-30"
                        >
                          {deleting === c.id ? 'Удаление...' : 'Удалить'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="lg:hidden flex flex-col gap-3 p-3">
            {corridors.map((c) => (
              <div key={c.id} className="bg-white/[0.03] rounded-card p-4 flex flex-col gap-2">
                <div className="text-sm text-white">
                  <span className="text-white/50">Из:</span> {roomMap.get(c.from_room_id) || `#${c.from_room_id}`}
                </div>
                <div className="text-sm text-white">
                  <span className="text-white/50">В:</span> {roomMap.get(c.to_room_id) || `#${c.to_room_id}`}
                </div>
                <div className="flex flex-wrap gap-3 text-xs text-white/50">
                  <span>Стамина: <span className="text-white">{c.stamina_cost}</span></span>
                  <span>{c.is_bidirectional ? <span className="text-gold">Двунаправленный</span> : 'Однонаправленный'}</span>
                  {c.random_battle_chance > 0 && (
                    <span>Бой: <span className="text-site-red">{Math.round(c.random_battle_chance * 100)}%</span></span>
                  )}
                  {c.trap_chance > 0 && (
                    <span>Ловушка: <span className="text-orange-300">{Math.round(c.trap_chance * 100)}%</span></span>
                  )}
                </div>
                <div className="flex gap-3 flex-wrap mt-1">
                  <button
                    onClick={() => openEdit(c)}
                    className="text-sm text-white hover:text-site-blue transition-colors"
                  >
                    Редактировать
                  </button>
                  <button
                    onClick={() => handleDelete(c.id)}
                    disabled={deleting === c.id}
                    className="text-sm text-site-red hover:text-white transition-colors disabled:opacity-30"
                  >
                    {deleting === c.id ? 'Удаление...' : 'Удалить'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDungeonCorridors;
