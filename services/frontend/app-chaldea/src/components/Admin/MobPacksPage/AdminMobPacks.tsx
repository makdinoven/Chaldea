import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  fetchMobPacks,
  fetchMobPackDetail,
  createMobPack,
  updateMobPack,
  deleteMobPack,
  placePack,
  fetchActiveMobPacks,
  deleteActiveMobPack,
  BATTLE_MAX_TEAM_SIZE,
  type MobPackListItem,
  type MobPackMemberInput,
  type ActiveMobPack,
} from '../../../api/mobPacks';
import { fetchMobTemplates, type MobTemplateListItem } from '../../../api/mobs';

interface LocationOption {
  id: number;
  name: string;
}

const TIER_LABELS: Record<string, string> = {
  normal: 'Обычный',
  elite: 'Элитный',
  boss: 'Босс',
};

const STATUS_LABELS: Record<string, string> = {
  alive: 'Готова',
  in_battle: 'В бою',
  dead: 'Побеждена',
};

// ── Composition editor row ──
interface EditorMember extends MobPackMemberInput {
  name: string;
  tier: string;
}

interface PackFormState {
  name: string;
  description: string;
  respawn_enabled: boolean;
  respawn_seconds: number | null;
  members: EditorMember[];
}

const EMPTY_FORM: PackFormState = {
  name: '',
  description: '',
  respawn_enabled: false,
  respawn_seconds: 300,
  members: [],
};

const AdminMobPacks = () => {
  const [tab, setTab] = useState<'templates' | 'active'>('templates');

  // Templates list
  const [packs, setPacks] = useState<MobPackListItem[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  // Active packs list
  const [activePacks, setActivePacks] = useState<ActiveMobPack[]>([]);
  const [activeLoading, setActiveLoading] = useState(false);
  const [activeError, setActiveError] = useState<string | null>(null);

  // Composer: searchable mob-template picker + locations (for placement)
  const [templates, setTemplates] = useState<MobTemplateListItem[]>([]);
  const [mobSearch, setMobSearch] = useState('');
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [locations, setLocations] = useState<LocationOption[]>([]);

  // Form modal
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<PackFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // Placement modal
  const [placingPack, setPlacingPack] = useState<MobPackListItem | null>(null);
  const [placeLocationId, setPlaceLocationId] = useState<number | ''>('');
  const [placing, setPlacing] = useState(false);

  const loadPacks = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const data = await fetchMobPacks({ q: search, page_size: 100 });
      setPacks(data.items);
    } catch {
      const msg = 'Не удалось загрузить стаи';
      setListError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [search]);

  const loadActivePacks = useCallback(async () => {
    setActiveLoading(true);
    setActiveError(null);
    try {
      const data = await fetchActiveMobPacks({ page_size: 100 });
      setActivePacks(data.items);
    } catch {
      const msg = 'Не удалось загрузить активные стаи';
      setActiveError(msg);
      toast.error(msg);
    } finally {
      setActiveLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(loadPacks, 300);
    return () => clearTimeout(t);
  }, [loadPacks]);

  useEffect(() => {
    if (tab === 'active') loadActivePacks();
  }, [tab, loadActivePacks]);

  // Load locations once (needed for placement)
  useEffect(() => {
    axios
      .get<LocationOption[]>('/locations/locations/lookup')
      .then((r) => setLocations(r.data))
      .catch(() => setLocations([]));
  }, []);

  // Load mob templates for the composer — only while the form is open, with a
  // debounced server-side search. page_size stays within the backend cap (le=100),
  // otherwise the request 422s and the picker shows nothing.
  useEffect(() => {
    if (!formOpen) return;
    setTemplatesLoading(true);
    setTemplatesError(null);
    const t = setTimeout(() => {
      fetchMobTemplates({ q: mobSearch.trim() || undefined, page_size: 100 })
        .then((d) => setTemplates(d.items))
        .catch(() => {
          setTemplates([]);
          setTemplatesError('Не удалось загрузить список мобов');
          toast.error('Не удалось загрузить список мобов');
        })
        .finally(() => setTemplatesLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [formOpen, mobSearch]);

  // ── Form handlers ──
  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setMobSearch('');
    setFormOpen(true);
  };

  const openEdit = async (id: number) => {
    try {
      const detail = await fetchMobPackDetail(id);
      setEditingId(id);
      setForm({
        name: detail.name,
        description: detail.description || '',
        respawn_enabled: detail.respawn_enabled,
        respawn_seconds: detail.respawn_seconds ?? 300,
        members: detail.members.map((m) => ({
          mob_template_id: m.mob_template_id,
          quantity: m.quantity,
          name: m.template_name || `Шаблон #${m.mob_template_id}`,
          tier: m.template_tier || 'normal',
        })),
      });
      setMobSearch('');
      setFormOpen(true);
    } catch {
      toast.error('Не удалось загрузить стаю');
    }
  };

  const addMember = (templateId: number) => {
    if (!templateId) return;
    if (form.members.some((m) => m.mob_template_id === templateId)) {
      toast.error('Этот моб уже в составе');
      return;
    }
    const tmpl = templates.find((t) => t.id === templateId);
    if (!tmpl) return;
    setForm((prev) => ({
      ...prev,
      members: [
        ...prev.members,
        { mob_template_id: templateId, quantity: 1, name: tmpl.name, tier: tmpl.tier },
      ],
    }));
  };

  const changeMemberQty = (templateId: number, value: string) => {
    const qty = value === '' ? 1 : Math.max(1, Number(value));
    setForm((prev) => ({
      ...prev,
      members: prev.members.map((m) =>
        m.mob_template_id === templateId ? { ...m, quantity: qty } : m,
      ),
    }));
  };

  const removeMember = (templateId: number) => {
    setForm((prev) => ({
      ...prev,
      members: prev.members.filter((m) => m.mob_template_id !== templateId),
    }));
  };

  const totalMobs = form.members.reduce((sum, m) => sum + m.quantity, 0);
  const overCap = totalMobs > BATTLE_MAX_TEAM_SIZE;

  // Templates not yet in the composition — offered in the picker.
  const availableTemplates = templates.filter(
    (t) => !form.members.some((m) => m.mob_template_id === t.id),
  );

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error('Укажите название стаи');
      return;
    }
    if (form.members.length === 0) {
      toast.error('Добавьте хотя бы одного моба в стаю');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim(),
        respawn_enabled: form.respawn_enabled,
        respawn_seconds: form.respawn_enabled ? form.respawn_seconds : null,
        members: form.members.map((m) => ({
          mob_template_id: m.mob_template_id,
          quantity: m.quantity,
        })),
      };
      if (editingId != null) {
        await updateMobPack(editingId, payload);
        toast.success('Стая обновлена');
      } else {
        await createMobPack(payload);
        toast.success('Стая создана');
      }
      setFormOpen(false);
      loadPacks();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Не удалось сохранить стаю';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!window.confirm(`Удалить стаю «${name}»? Все её размещённые экземпляры будут удалены.`)) {
      return;
    }
    try {
      await deleteMobPack(id);
      toast.success('Стая удалена');
      loadPacks();
    } catch {
      toast.error('Не удалось удалить стаю');
    }
  };

  const handlePlace = async () => {
    if (!placingPack || placeLocationId === '') return;
    setPlacing(true);
    try {
      const res = await placePack(placingPack.id, Number(placeLocationId));
      toast.success(`Стая размещена (${res.spawned_mobs} мобов)`);
      setPlacingPack(null);
      setPlaceLocationId('');
      if (tab === 'active') loadActivePacks();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Не удалось разместить стаю';
      toast.error(msg);
    } finally {
      setPlacing(false);
    }
  };

  const handleRemoveActive = async (id: number) => {
    if (!window.confirm('Убрать эту стаю с локации?')) return;
    try {
      await deleteActiveMobPack(id);
      toast.success('Стая убрана с локации');
      loadActivePacks();
    } catch {
      toast.error('Не удалось убрать стаю');
    }
  };

  const locationName = (id: number) =>
    locations.find((l) => l.id === id)?.name || `Локация #${id}`;

  return (
    <div className="w-full max-w-[1100px] mx-auto">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em] mb-6">
        Стаи мобов
      </h1>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <button
          onClick={() => setTab('templates')}
          className={`px-4 py-2 rounded-card text-sm font-medium transition-colors ${
            tab === 'templates' ? 'bg-gold/20 text-gold' : 'bg-white/5 text-white/60 hover:bg-white/10'
          }`}
        >
          Шаблоны стай
        </button>
        <button
          onClick={() => setTab('active')}
          className={`px-4 py-2 rounded-card text-sm font-medium transition-colors ${
            tab === 'active' ? 'bg-gold/20 text-gold' : 'bg-white/5 text-white/60 hover:bg-white/10'
          }`}
        >
          Активные стаи
        </button>
      </div>

      {tab === 'templates' ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row gap-3 sm:items-center justify-between">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по названию..."
              className="input-underline max-w-[320px]"
            />
            <button onClick={openCreate} className="btn-blue text-sm px-5 py-2 self-start">
              Создать стаю
            </button>
          </div>

          {loading ? (
            <p className="text-white/50 text-sm">Загрузка...</p>
          ) : listError ? (
            <div className="flex flex-col gap-2">
              <p className="text-site-red text-sm">{listError}</p>
              <button onClick={loadPacks} className="btn-blue text-sm px-4 py-2 self-start">
                Повторить
              </button>
            </div>
          ) : packs.length === 0 ? (
            <p className="text-white/50 text-sm">Стаи ещё не созданы.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {packs.map((p) => (
                <div
                  key={p.id}
                  className="bg-white/[0.05] rounded-card p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-white text-sm sm:text-base font-medium truncate">
                        {p.name}
                      </span>
                      {p.respawn_enabled && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300">
                          респавн
                        </span>
                      )}
                      {p.total_mobs > BATTLE_MAX_TEAM_SIZE && (
                        <span
                          title={`В бою участвуют максимум ${BATTLE_MAX_TEAM_SIZE} мобов — лишние не войдут`}
                          className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300"
                        >
                          &gt; {BATTLE_MAX_TEAM_SIZE} в бою
                        </span>
                      )}
                    </div>
                    <span className="text-white/40 text-xs">
                      {p.member_count} видов · {p.total_mobs} мобов
                    </span>
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <button
                      onClick={() => setPlacingPack(p)}
                      className="btn-blue text-xs px-3 py-1.5"
                    >
                      Разместить
                    </button>
                    <button
                      onClick={() => openEdit(p.id)}
                      className="text-xs px-3 py-1.5 rounded border border-white/20 text-white/70 hover:bg-white/5"
                    >
                      Изменить
                    </button>
                    <button
                      onClick={() => handleDelete(p.id, p.name)}
                      className="text-xs px-3 py-1.5 rounded border border-site-red/40 text-site-red hover:bg-site-red/10"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {activeLoading ? (
            <p className="text-white/50 text-sm">Загрузка...</p>
          ) : activeError ? (
            <div className="flex flex-col gap-2">
              <p className="text-site-red text-sm">{activeError}</p>
              <button onClick={loadActivePacks} className="btn-blue text-sm px-4 py-2 self-start">
                Повторить
              </button>
            </div>
          ) : activePacks.length === 0 ? (
            <p className="text-white/50 text-sm">Нет размещённых стай.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {activePacks.map((ap) => (
                <div
                  key={ap.id}
                  className="bg-white/[0.05] rounded-card p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3"
                >
                  <div className="flex-1 min-w-0">
                    <span className="text-white text-sm font-medium truncate block">
                      {ap.pack_name || `Стая #${ap.pack_id}`}
                    </span>
                    <span className="text-white/40 text-xs">
                      {locationName(ap.location_id)} · живых {ap.alive_count}/{ap.total_count} ·{' '}
                      {STATUS_LABELS[ap.status] || ap.status}
                    </span>
                  </div>
                  <button
                    onClick={() => handleRemoveActive(ap.id)}
                    className="text-xs px-3 py-1.5 rounded border border-site-red/40 text-site-red hover:bg-site-red/10 self-start"
                  >
                    Убрать
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Form modal ── */}
      {formOpen && (
        <div className="modal-overlay" onClick={() => !saving && setFormOpen(false)}>
          <div
            className="modal-content max-w-[560px] w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-xl font-medium mb-4">
              {editingId != null ? 'Редактирование стаи' : 'Новая стая'}
            </h2>

            <div className="flex flex-col gap-4">
              <label className="flex flex-col gap-1">
                <span className="text-white/60 text-xs uppercase">Название</span>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  className="input-underline"
                  placeholder="Например, Стая волков"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-white/60 text-xs uppercase">Описание</span>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                  className="input-underline resize-none"
                  rows={2}
                />
              </label>

              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.respawn_enabled}
                    onChange={(e) => setForm((p) => ({ ...p, respawn_enabled: e.target.checked }))}
                    className="w-4 h-4 accent-gold"
                  />
                  <span className="text-white/80 text-sm">
                    Респавн стаи (возрождается целиком)
                  </span>
                </label>
                {form.respawn_enabled && (
                  <label className="flex items-center gap-2 pl-6">
                    <span className="text-white/50 text-xs">через</span>
                    <input
                      type="number"
                      min={1}
                      value={form.respawn_seconds ?? ''}
                      onChange={(e) =>
                        setForm((p) => ({
                          ...p,
                          respawn_seconds: e.target.value === '' ? null : Number(e.target.value),
                        }))
                      }
                      className="input-underline !text-sm w-24"
                    />
                    <span className="text-white/50 text-xs">сек.</span>
                  </label>
                )}
              </div>

              {/* Composition */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-white/60 text-xs uppercase">Состав</span>
                  <span className={`text-xs ${overCap ? 'text-amber-300' : 'text-white/40'}`}>
                    {totalMobs} мобов
                    {overCap && ` · в бою только ${BATTLE_MAX_TEAM_SIZE}`}
                  </span>
                </div>

                {form.members.length > 0 && (
                  <div className="flex flex-col gap-2">
                    {form.members.map((m) => (
                      <div
                        key={m.mob_template_id}
                        className="bg-white/[0.04] rounded-card p-2 flex items-center gap-2"
                      >
                        <div className="flex-1 min-w-0">
                          <span className="text-white text-sm truncate block">{m.name}</span>
                          <span className="text-white/40 text-[10px]">
                            {TIER_LABELS[m.tier] || m.tier}
                          </span>
                        </div>
                        <label className="flex items-center gap-1">
                          <span className="text-white/40 text-[10px]">×</span>
                          <input
                            type="number"
                            min={1}
                            value={m.quantity}
                            onChange={(e) => changeMemberQty(m.mob_template_id, e.target.value)}
                            className="input-underline !text-sm w-16"
                          />
                        </label>
                        <button
                          onClick={() => removeMember(m.mob_template_id)}
                          className="text-site-red text-xs hover:text-white px-2"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Searchable mob picker */}
                <div className="flex flex-col gap-2">
                  <input
                    type="text"
                    value={mobSearch}
                    onChange={(e) => setMobSearch(e.target.value)}
                    placeholder="Найти моба по имени..."
                    className="input-underline"
                  />
                  <div className="max-h-56 overflow-y-auto rounded-card border border-white/10 divide-y divide-white/5">
                    {templatesLoading ? (
                      <p className="text-white/40 text-xs p-3">Загрузка мобов...</p>
                    ) : templatesError ? (
                      <p className="text-site-red text-xs p-3">{templatesError}</p>
                    ) : availableTemplates.length === 0 ? (
                      <p className="text-white/40 text-xs p-3">
                        {mobSearch.trim()
                          ? 'Мобы не найдены'
                          : form.members.length > 0
                            ? 'Все доступные мобы уже добавлены'
                            : 'Нет доступных мобов'}
                      </p>
                    ) : (
                      availableTemplates.map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => addMember(t.id)}
                          className="w-full text-left px-3 py-2 flex items-center justify-between gap-2 hover:bg-white/5 transition-colors"
                        >
                          <span className="text-white text-sm truncate">{t.name}</span>
                          <span className="text-white/40 text-[10px] whitespace-nowrap">
                            {TIER_LABELS[t.tier] || t.tier} · ур. {t.level}
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex gap-2 justify-end mt-6">
              <button
                onClick={() => setFormOpen(false)}
                disabled={saving}
                className="text-sm px-4 py-2 rounded border border-white/20 text-white/70 hover:bg-white/5"
              >
                Отмена
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="btn-blue text-sm px-6 py-2 disabled:opacity-50"
              >
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Placement modal ── */}
      {placingPack && (
        <div className="modal-overlay" onClick={() => !placing && setPlacingPack(null)}>
          <div
            className="modal-content max-w-[420px] w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-xl font-medium mb-4">
              Разместить «{placingPack.name}»
            </h2>
            <label className="flex flex-col gap-1 mb-6">
              <span className="text-white/60 text-xs uppercase">Локация</span>
              <select
                className="input-underline"
                value={placeLocationId}
                onChange={(e) => setPlaceLocationId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="" className="bg-site-dark text-white">
                  Выберите локацию...
                </option>
                {locations.map((l) => (
                  <option key={l.id} value={l.id} className="bg-site-dark text-white">
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setPlacingPack(null)}
                disabled={placing}
                className="text-sm px-4 py-2 rounded border border-white/20 text-white/70 hover:bg-white/5"
              >
                Отмена
              </button>
              <button
                onClick={handlePlace}
                disabled={placing || placeLocationId === ''}
                className="btn-blue text-sm px-6 py-2 disabled:opacity-50"
              >
                {placing ? 'Размещение...' : 'Разместить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminMobPacks;
