import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';
import { NPC_ROLES, NPC_ROLE_LABELS, NPC_SEXES, NPC_CLASSES, NPC_RACES } from '../../constants/npc';
import DialogueEditor from './DialogueEditor';
import NpcShopEditor from './NpcShopEditor';
import QuestEditor from './QuestEditor';

/* ── Types ── */

interface NpcListItem {
  id: number;
  name: string;
  avatar: string | null;
  level: number;
  npc_role: string | null;
  location_name: string | null;
  location_id: number | null;
}

interface NpcFormData {
  name: string;
  npc_role: string;
  class_name: string;
  race_name: string;
  level: number;
  avatar: string;
  biography: string;
  personality: string;
  appearance: string;
  sex: string;
  age: number;
  weight: number;
  height: number;
  location_id: number | null;
  currency: number;
}

interface LocationOption {
  id: number;
  name: string;
}

const INITIAL_FORM: NpcFormData = {
  name: '',
  npc_role: 'merchant',
  class_name: 'Воин',
  race_name: 'Человек',
  level: 1,
  avatar: '',
  biography: '',
  personality: '',
  appearance: '',
  sex: 'male',
  age: 25,
  weight: 70,
  height: 170,
  location_id: null,
  currency: 0,
};

/* ── Component ── */

const AdminNpcsPage = () => {
  const [npcs, setNpcs] = useState<NpcListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const debouncedQuery = useDebounce(query);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<NpcFormData>(INITIAL_FORM);
  const [saving, setSaving] = useState(false);
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [dialogueNpc, setDialogueNpc] = useState<{ id: number; name: string } | null>(null);
  const [shopNpc, setShopNpc] = useState<{ id: number; name: string } | null>(null);
  const [questNpc, setQuestNpc] = useState<{ id: number; name: string } | null>(null);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);

  const fetchNpcs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (debouncedQuery) params.q = debouncedQuery;
      if (roleFilter) params.npc_role = roleFilter;
      const res = await axios.get(`${BASE_URL}/characters/admin/npcs`, { params });
      const data = res.data;
      setNpcs(Array.isArray(data) ? data : (data.items ?? []));
    } catch {
      toast.error('Не удалось загрузить список НПС');
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, roleFilter]);

  useEffect(() => {
    fetchNpcs();
  }, [fetchNpcs]);

  const fetchLocations = useCallback(async () => {
    try {
      const res = await axios.get<LocationOption[]>(`${BASE_URL}/locations/locations/lookup`);
      setLocations(res.data);
    } catch {
      // Locations list not critical, silently fail
    }
  }, []);

  useEffect(() => {
    fetchLocations();
  }, [fetchLocations]);

  const openCreateForm = () => {
    setEditingId(null);
    setForm(INITIAL_FORM);
    setAvatarFile(null);
    setAvatarPreview(null);
    setFormOpen(true);
  };

  const openEditForm = async (id: number) => {
    try {
      const res = await axios.get(`${BASE_URL}/characters/admin/npcs/${id}`);
      const npc = res.data;
      setForm({
        name: npc.name || '',
        npc_role: npc.npc_role || 'merchant',
        class_name: npc.class_name || 'Воин',
        race_name: npc.race_name || 'Человек',
        level: npc.level || 1,
        avatar: npc.avatar || '',
        biography: npc.biography || '',
        personality: npc.personality || '',
        appearance: npc.appearance || '',
        sex: npc.sex || 'male',
        age: npc.age || 25,
        weight: npc.weight || 70,
        height: npc.height || 170,
        location_id: npc.location_id ?? null,
        currency: npc.currency || 0,
      });
      setEditingId(id);
      setAvatarFile(null);
      setAvatarPreview(null);
      setFormOpen(true);
    } catch {
      toast.error('Не удалось загрузить данные НПС');
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Удалить НПС? Это действие нельзя отменить.')) return;
    try {
      await axios.delete(`${BASE_URL}/characters/admin/npcs/${id}`);
      toast.success('НПС удалён');
      setNpcs((prev) => prev.filter((n) => n.id !== id));
      if (editingId === id) {
        setFormOpen(false);
        setEditingId(null);
      }
    } catch {
      toast.error('Не удалось удалить НПС');
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const { name, value, type } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === 'number' ? (value === '' ? 0 : Number(value)) : value,
    }));
  };

  const handleAvatarFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarFile(file);
    setAvatarPreview(URL.createObjectURL(file));
  };

  const uploadNpcAvatar = async (npcId: number, file: File) => {
    const formData = new FormData();
    formData.append('character_id', String(npcId));
    formData.append('file', file);
    const res = await axios.post(`${BASE_URL}/photo/change_npc_avatar`, formData);
    return res.data.avatar_url as string;
  };

  const handleLocationChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setForm((prev) => ({
      ...prev,
      location_id: val === '' ? null : Number(val),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.error('Имя НПС обязательно');
      return;
    }
    setSaving(true);
    try {
      let npcId = editingId;
      if (editingId) {
        await axios.put(`${BASE_URL}/characters/admin/npcs/${editingId}`, form);
        toast.success('НПС обновлён');
      } else {
        const res = await axios.post(`${BASE_URL}/characters/admin/npcs`, form);
        npcId = res.data.id;
        toast.success('НПС создан');
      }
      if (avatarFile && npcId) {
        try {
          await uploadNpcAvatar(npcId, avatarFile);
        } catch {
          toast.error('НПС сохранён, но не удалось загрузить аватар');
        }
      }
      setAvatarFile(null);
      setAvatarPreview(null);
      setFormOpen(false);
      setEditingId(null);
      fetchNpcs();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось сохранить НПС';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const filteredNpcs = npcs;

  /* ── Render ── */

  if (questNpc) {
    return (
      <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
        <QuestEditor
          npcId={questNpc.id}
          npcName={questNpc.name}
          onClose={() => setQuestNpc(null)}
        />
      </div>
    );
  }

  if (shopNpc) {
    return (
      <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
        <NpcShopEditor
          npcId={shopNpc.id}
          npcName={shopNpc.name}
          onClose={() => setShopNpc(null)}
        />
      </div>
    );
  }

  if (dialogueNpc) {
    return (
      <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
        <DialogueEditor
          npcId={dialogueNpc.id}
          npcName={dialogueNpc.name}
          onClose={() => setDialogueNpc(null)}
        />
      </div>
    );
  }

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Управление НПС
      </h1>

      {/* Search + Filter + Create */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4">
        <input
          className="input-underline flex-1 max-w-[320px]"
          placeholder="Поиск по имени..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="input-underline max-w-[200px]"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
        >
          <option value="" className="bg-site-dark text-white">Все роли</option>
          {NPC_ROLES.map((r) => (
            <option key={r.value} value={r.value} className="bg-site-dark text-white">
              {r.label}
            </option>
          ))}
        </select>
        <button className="btn-blue !text-base !px-6 !py-2 sm:ml-auto" onClick={openCreateForm}>
          Создать НПС
        </button>
      </div>

      {/* Form */}
      {formOpen && (
        <form className="gray-bg p-4 sm:p-6 flex flex-col gap-5" onSubmit={handleSubmit}>
          <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em]">
            {editingId ? 'Редактирование НПС' : 'Создание НПС'}
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
            {/* Name */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Имя</span>
              <input name="name" value={form.name} onChange={handleChange} required className="input-underline" />
            </label>

            {/* Role */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Роль</span>
              <select name="npc_role" value={form.npc_role} onChange={handleChange} className="input-underline">
                {NPC_ROLES.map((r) => (
                  <option key={r.value} value={r.value} className="bg-site-dark text-white">{r.label}</option>
                ))}
              </select>
            </label>

            {/* Class */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Класс</span>
              <select name="class_name" value={form.class_name} onChange={handleChange} className="input-underline">
                {NPC_CLASSES.map((c) => (
                  <option key={c.value} value={c.value} className="bg-site-dark text-white">{c.label}</option>
                ))}
              </select>
            </label>

            {/* Race */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Раса</span>
              <select name="race_name" value={form.race_name} onChange={handleChange} className="input-underline">
                {NPC_RACES.map((r) => (
                  <option key={r.value} value={r.value} className="bg-site-dark text-white">{r.label}</option>
                ))}
              </select>
            </label>

            {/* Level */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Уровень</span>
              <input type="number" name="level" value={form.level} onChange={handleChange} min={1} className="input-underline" />
            </label>

            {/* Sex */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Пол</span>
              <select name="sex" value={form.sex} onChange={handleChange} className="input-underline">
                {NPC_SEXES.map((s) => (
                  <option key={s.value} value={s.value} className="bg-site-dark text-white">{s.label}</option>
                ))}
              </select>
            </label>

            {/* Age */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Возраст</span>
              <input type="number" name="age" value={form.age} onChange={handleChange} min={0} className="input-underline" />
            </label>

            {/* Weight */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Вес (кг)</span>
              <input type="number" name="weight" value={form.weight} onChange={handleChange} min={0} className="input-underline" />
            </label>

            {/* Height */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Рост (см)</span>
              <input type="number" name="height" value={form.height} onChange={handleChange} min={0} className="input-underline" />
            </label>

            {/* Currency */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Валюта</span>
              <input type="number" name="currency" value={form.currency} onChange={handleChange} min={0} className="input-underline" />
            </label>

            {/* Location */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Локация</span>
              <select value={form.location_id ?? ''} onChange={handleLocationChange} className="input-underline">
                <option value="" className="bg-site-dark text-white">Без локации</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id} className="bg-site-dark text-white">{loc.name}</option>
                ))}
              </select>
            </label>

            {/* Avatar upload */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Аватар</span>
              <div className="flex items-center gap-3">
                {(avatarPreview || form.avatar) && (
                  <img
                    src={avatarPreview || form.avatar}
                    alt="Превью"
                    className="w-12 h-12 rounded-full object-cover shrink-0 border border-white/20"
                  />
                )}
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleAvatarFile}
                  className="text-sm text-white/70 file:mr-3 file:py-1.5 file:px-4 file:rounded file:border-0 file:text-sm file:bg-white/10 file:text-white/70 hover:file:bg-white/20 file:cursor-pointer"
                />
              </div>
            </label>
          </div>

          {/* Textareas */}
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Биография</span>
            <textarea name="biography" value={form.biography} onChange={handleChange} rows={3} className="textarea-bordered" />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Характер</span>
            <textarea name="personality" value={form.personality} onChange={handleChange} rows={3} className="textarea-bordered" />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Внешность</span>
            <textarea name="appearance" value={form.appearance} onChange={handleChange} rows={3} className="textarea-bordered" />
          </label>

          {/* Buttons */}
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 pt-2">
            <button type="submit" disabled={saving} className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50">
              {saving ? 'Сохранение...' : editingId ? 'Сохранить' : 'Создать'}
            </button>
            <button
              type="button"
              onClick={() => { setFormOpen(false); setEditingId(null); }}
              className="btn-line !w-auto !px-8"
            >
              Отмена
            </button>
          </div>
        </form>
      )}

      {/* NPC Table */}
      <div className="gray-bg overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden sm:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">ID</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Аватар</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Имя</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Уровень</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Роль</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Локация</th>
                    <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredNpcs.map((npc) => (
                    <tr key={npc.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200">
                      <td className="px-4 py-3 text-sm text-white/70">{npc.id}</td>
                      <td className="px-4 py-3">
                        {npc.avatar ? (
                          <img src={npc.avatar} alt={npc.name} className="w-10 h-10 rounded-full object-cover" />
                        ) : (
                          <div className="w-10 h-10 rounded-full bg-white/[0.05] flex items-center justify-center text-white/20 text-xs">
                            НПС
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-white">{npc.name}</td>
                      <td className="px-4 py-3 text-sm text-white/70">{npc.level}</td>
                      <td className="px-4 py-3">
                        {npc.npc_role && (
                          <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-xs font-medium">
                            {NPC_ROLE_LABELS[npc.npc_role] || npc.npc_role}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/70">{npc.location_name || '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col items-end gap-1.5">
                          <button
                            onClick={() => openEditForm(npc.id)}
                            className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                          >
                            Редактировать
                          </button>
                          <button
                            onClick={() => setDialogueNpc({ id: npc.id, name: npc.name })}
                            className="text-sm text-gold hover:text-gold-light transition-colors duration-200"
                          >
                            Диалоги
                          </button>
                          <button
                            onClick={() => setQuestNpc({ id: npc.id, name: npc.name })}
                            className="text-sm text-gold hover:text-gold-light transition-colors duration-200"
                          >
                            Квесты
                          </button>
                          {npc.npc_role === 'merchant' && (
                            <button
                              onClick={() => setShopNpc({ id: npc.id, name: npc.name })}
                              className="text-sm text-site-blue hover:text-white transition-colors duration-200"
                            >
                              Магазин
                            </button>
                          )}
                          <button
                            onClick={() => handleDelete(npc.id)}
                            className="text-sm text-site-red hover:text-white transition-colors duration-200"
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="sm:hidden flex flex-col gap-3 p-3">
              {filteredNpcs.map((npc) => (
                <div key={npc.id} className="bg-white/[0.03] rounded-card p-4 flex flex-col gap-3">
                  <div className="flex items-center gap-3">
                    {npc.avatar ? (
                      <img src={npc.avatar} alt={npc.name} className="w-12 h-12 rounded-full object-cover shrink-0" />
                    ) : (
                      <div className="w-12 h-12 rounded-full bg-white/[0.05] flex items-center justify-center text-white/20 text-xs shrink-0">
                        НПС
                      </div>
                    )}
                    <div className="flex flex-col gap-1 min-w-0">
                      <span className="text-white text-sm font-medium truncate">{npc.name}</span>
                      <span className="text-white/50 text-xs">LVL {npc.level}</span>
                    </div>
                    {npc.npc_role && (
                      <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-[10px] font-medium ml-auto shrink-0">
                        {NPC_ROLE_LABELS[npc.npc_role] || npc.npc_role}
                      </span>
                    )}
                  </div>
                  <div className="text-white/50 text-xs">
                    Локация: {npc.location_name || '—'}
                  </div>
                  <div className="flex gap-3 flex-wrap">
                    <button
                      onClick={() => openEditForm(npc.id)}
                      className="text-sm text-white hover:text-site-blue transition-colors"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => setDialogueNpc({ id: npc.id, name: npc.name })}
                      className="text-sm text-gold hover:text-gold-light transition-colors"
                    >
                      Диалоги
                    </button>
                    <button
                      onClick={() => setQuestNpc({ id: npc.id, name: npc.name })}
                      className="text-sm text-gold hover:text-gold-light transition-colors"
                    >
                      Квесты
                    </button>
                    {npc.npc_role === 'merchant' && (
                      <button
                        onClick={() => setShopNpc({ id: npc.id, name: npc.name })}
                        className="text-sm text-site-blue hover:text-white transition-colors"
                      >
                        Магазин
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(npc.id)}
                      className="text-sm text-site-red hover:text-white transition-colors"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {filteredNpcs.length === 0 && (
              <p className="text-center text-white/50 text-sm py-8">НПС не найдены</p>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default AdminNpcsPage;
