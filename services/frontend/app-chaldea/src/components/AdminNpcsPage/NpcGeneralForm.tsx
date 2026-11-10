import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';
import { NPC_ROLES, NPC_SEXES, NPC_CLASSES, NPC_RACES } from '../../constants/npc';
import ReputationTierSelect from '../Admin/ReputationPage/ReputationTierSelect';
import { roleKillWeight, useReputationRoleWeights } from '../Admin/ReputationPage/useReputationRefs';
import { useDirtyReport } from '../Admin/ExpandableList/useDirtyReport';

/* FEAT-208: the NPC edit/create form, moved out of AdminNpcsPage into the «Основное» tab. */

/* ── Types ── */

interface NpcFormData {
  name: string;
  npc_role: string;
  id_class: number;
  id_race: number;
  id_subrace: number;
  level: number;
  avatar: string;
  biography: string;
  personality: string;
  appearance: string;
  sex: string;
  age: number;
  weight: string;
  height: string;
  current_location_id: number | null;
  currency_balance: number;
  /** FEAT-197: NPC gate (tier code, null = none) */
  reputation_min_tier: string | null;
  /** FEAT-197: typed kill weight; '' = the role weight */
  reputation_kill_points: string;
}

interface LocationOption {
  id: number;
  name: string;
}

export interface SubraceOption {
  id_subrace: number;
  name: string;
  stat_preset: Record<string, number> | null;
}

export interface RaceWithSubraces {
  id_race: number;
  name: string;
  subraces: SubraceOption[];
}

interface NpcGeneralFormProps {
  /** null = create a new NPC */
  npcId: number | null;
  racesData: RaceWithSubraces[];
  onSaved: (id: number, created: boolean) => void;
  onCancel: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}

const INITIAL_FORM: NpcFormData = {
  name: '',
  npc_role: 'merchant',
  id_class: 1,
  id_race: 1,
  id_subrace: 1,
  level: 1,
  avatar: '',
  biography: '',
  personality: '',
  appearance: '',
  sex: 'male',
  age: 25,
  weight: '70',
  height: '170',
  current_location_id: null,
  currency_balance: 0,
  reputation_min_tier: null,
  reputation_kill_points: '',
};

const KILL_POINTS_LIMIT = 1000;
const SIGNED_INT_RE = /^-?\d*$/;
const NUMERIC_FIELDS = ['id_class', 'id_subrace', 'level', 'age', 'currency_balance'];

/* ── Component ── */

const NpcGeneralForm = ({ npcId, racesData, onSaved, onCancel, onDirtyChange }: NpcGeneralFormProps) => {
  const [form, setForm] = useState<NpcFormData>(INITIAL_FORM);
  const [snapshot, setSnapshot] = useState<string>(JSON.stringify(INITIAL_FORM));
  const [loadingDetail, setLoadingDetail] = useState(npcId !== null);
  const roleWeights = useReputationRoleWeights();
  const [saving, setSaving] = useState(false);
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [locationSearchQuery, setLocationSearchQuery] = useState('');
  const debouncedLocationQuery = useDebounce(locationSearchQuery);
  const [locationSearchLoading, setLocationSearchLoading] = useState(false);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [subraceOptions, setSubraceOptions] = useState<SubraceOption[]>([]);

  const isDirty = !loadingDetail && (JSON.stringify(form) !== snapshot || avatarFile !== null);
  useDirtyReport(isDirty, onDirtyChange);

  // Load the NPC being edited
  useEffect(() => {
    if (npcId === null) return;
    let cancelled = false;
    setLoadingDetail(true);
    axios
      .get(`${BASE_URL}/characters/admin/npcs/${npcId}`)
      .then((res) => {
        if (cancelled) return;
        const npc = res.data;
        const loaded: NpcFormData = {
          name: npc.name || '',
          npc_role: npc.npc_role || 'merchant',
          id_class: npc.id_class || 1,
          id_race: npc.id_race || 1,
          id_subrace: npc.id_subrace || 1,
          level: npc.level || 1,
          avatar: npc.avatar || '',
          biography: npc.biography || '',
          personality: npc.personality || '',
          appearance: npc.appearance || '',
          sex: npc.sex || 'male',
          age: npc.age || 25,
          weight: npc.weight || '70',
          height: npc.height || '170',
          current_location_id: npc.current_location_id ?? null,
          currency_balance: npc.currency_balance || 0,
          reputation_min_tier: npc.reputation_min_tier ?? null,
          reputation_kill_points: npc.reputation_kill_points == null ? '' : String(npc.reputation_kill_points),
        };
        setForm(loaded);
        setSnapshot(JSON.stringify(loaded));
      })
      .catch(() => {
        if (!cancelled) toast.error('Не удалось загрузить данные НПС');
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [npcId]);

  useEffect(() => {
    setLocationSearchLoading(true);
    const params: Record<string, string> = {};
    if (debouncedLocationQuery) params.q = debouncedLocationQuery;
    axios
      .get<LocationOption[]>(`${BASE_URL}/locations/locations/lookup`, { params })
      .then((res) => setLocations(Array.isArray(res.data) ? res.data : []))
      .catch(() => toast.error('Не удалось загрузить список локаций'))
      .finally(() => setLocationSearchLoading(false));
  }, [debouncedLocationQuery]);

  // Update subrace options when race changes or racesData loads
  const updateSubraceOptions = useCallback((raceId: number) => {
    const race = racesData.find((r) => r.id_race === raceId);
    setSubraceOptions(race?.subraces ?? []);
  }, [racesData]);

  useEffect(() => {
    if (racesData.length > 0) {
      updateSubraceOptions(form.id_race);
    }
  }, [form.id_race, racesData, updateSubraceOptions]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const { name, value, type } = e.target;
    if (name === 'id_race') {
      const newRaceId = Number(value);
      const race = racesData.find((r) => r.id_race === newRaceId);
      const firstSubrace = race?.subraces?.[0]?.id_subrace ?? 0;
      setForm((prev) => ({
        ...prev,
        id_race: newRaceId,
        id_subrace: firstSubrace,
      }));
      return;
    }
    setForm((prev) => ({
      ...prev,
      [name]: type === 'number' || NUMERIC_FIELDS.includes(name)
        ? (value === '' ? 0 : Number(value))
        : value,
    }));
  };

  const handleAvatarFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarFile(file);
    setAvatarPreview(URL.createObjectURL(file));
  };

  const uploadNpcAvatar = async (id: number, file: File) => {
    const formData = new FormData();
    formData.append('character_id', String(id));
    formData.append('file', file);
    const res = await axios.post(`${BASE_URL}/photo/change_npc_avatar`, formData);
    return res.data.avatar_url as string;
  };

  const handleLocationSelect = (locationId: number | null) => {
    setForm((prev) => ({
      ...prev,
      current_location_id: locationId,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.error('Имя НПС обязательно');
      return;
    }
    const killText = form.reputation_kill_points.trim();
    const killPoints = killText === '' ? null : Number(killText);
    if (killPoints !== null && (!Number.isInteger(killPoints) || Math.abs(killPoints) > KILL_POINTS_LIMIT)) {
      toast.error(`Репутация за убийство — целое число от −${KILL_POINTS_LIMIT} до ${KILL_POINTS_LIMIT}`);
      return;
    }
    setSaving(true);
    try {
      let savedId = npcId;
      // Exclude avatar from payload — it's handled separately via photo-service
      const { avatar: _avatar, reputation_kill_points: _killText, ...rest } = form;
      const payload = { ...rest, reputation_kill_points: killPoints };
      if (npcId !== null) {
        await axios.put(`${BASE_URL}/characters/admin/npcs/${npcId}`, payload);
        toast.success('НПС обновлён');
      } else {
        const res = await axios.post(`${BASE_URL}/characters/admin/npcs`, payload);
        savedId = res.data.id;
        toast.success('НПС создан');
      }
      let nextForm = form;
      if (avatarFile && savedId) {
        try {
          const url = await uploadNpcAvatar(savedId, avatarFile);
          if (url) nextForm = { ...form, avatar: url };
        } catch {
          toast.error('НПС сохранён, но не удалось загрузить аватар');
        }
      }
      setForm(nextForm);
      setSnapshot(JSON.stringify(nextForm));
      setAvatarFile(null);
      setAvatarPreview(null);
      if (savedId) onSaved(savedId, npcId === null);
    } catch (err) {
      let message = 'Не удалось сохранить НПС';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'string') {
          message = detail;
        } else if (Array.isArray(detail)) {
          message = detail.map((d: { msg?: string }) => d.msg || String(d)).join('; ');
        }
      }
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  /* ── Render ── */

  if (loadingDetail) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <form className="gray-bg p-4 sm:p-6 flex flex-col gap-5 min-w-0" onSubmit={handleSubmit}>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        {/* Name */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Имя</span>
          <input name="name" value={form.name} onChange={handleChange} required className="input-underline" />
        </label>

        {/* Role */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Роль</span>
          <select name="npc_role" value={form.npc_role} onChange={handleChange} className="input-underline">
            {NPC_ROLES.map((r) => (
              <option key={r.value} value={r.value} className="bg-site-dark text-white">{r.label}</option>
            ))}
          </select>
        </label>

        {/* FEAT-197: reputation gate + kill weight */}
        <ReputationTierSelect
          value={form.reputation_min_tier}
          onChange={(code) => setForm((prev) => ({ ...prev, reputation_min_tier: code }))}
          hint="Ниже этой ступени НПС не разговаривает и не оказывает услуг"
        />

        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Репутация за убийство</span>
          <input
            inputMode="numeric"
            value={form.reputation_kill_points}
            onChange={(e) => {
              const v = e.target.value;
              if (SIGNED_INT_RE.test(v)) setForm((prev) => ({ ...prev, reputation_kill_points: v }));
            }}
            placeholder={(() => {
              const w = roleKillWeight(roleWeights, form.npc_role);
              return w == null ? 'по умолчанию: вес роли' : `по умолчанию: ${w > 0 ? `+${w}` : w} (вес роли)`;
            })()}
            className="input-underline"
          />
          <span className="text-white/40 text-xs">Каждому победителю, в регионе НПС; пусто — вес роли</span>
        </label>

        {/* Class */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Класс</span>
          <select name="id_class" value={form.id_class} onChange={handleChange} className="input-underline">
            {NPC_CLASSES.map((c) => (
              <option key={c.value} value={c.value} className="bg-site-dark text-white">{c.label}</option>
            ))}
          </select>
        </label>

        {/* Race */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Раса</span>
          <select name="id_race" value={form.id_race} onChange={handleChange} className="input-underline">
            {racesData.length > 0
              ? racesData.map((r) => (
                  <option key={r.id_race} value={r.id_race} className="bg-site-dark text-white">{r.name}</option>
                ))
              : NPC_RACES.map((r) => (
                  <option key={r.value} value={r.value} className="bg-site-dark text-white">{r.label}</option>
                ))
            }
          </select>
        </label>

        {/* Subrace */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Подраса</span>
          <select
            name="id_subrace"
            value={form.id_subrace}
            onChange={handleChange}
            className="input-underline"
            disabled={subraceOptions.length === 0}
          >
            {subraceOptions.length === 0 ? (
              <option value={0} className="bg-site-dark text-white">
                {racesData.length === 0 ? 'Загрузка...' : 'Нет подрас'}
              </option>
            ) : (
              subraceOptions.map((s) => (
                <option key={s.id_subrace} value={s.id_subrace} className="bg-site-dark text-white">
                  {s.name}
                </option>
              ))
            )}
          </select>
        </label>

        {/* Level */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Уровень</span>
          <input type="number" name="level" value={form.level} onChange={handleChange} min={1} className="input-underline" />
        </label>

        {/* Sex */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Пол</span>
          <select name="sex" value={form.sex} onChange={handleChange} className="input-underline">
            {NPC_SEXES.map((s) => (
              <option key={s.value} value={s.value} className="bg-site-dark text-white">{s.label}</option>
            ))}
          </select>
        </label>

        {/* Age */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Возраст</span>
          <input type="number" name="age" value={form.age} onChange={handleChange} min={0} className="input-underline" />
        </label>

        {/* Weight */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Вес (кг)</span>
          <input type="number" name="weight" value={form.weight} onChange={handleChange} min={0} className="input-underline" />
        </label>

        {/* Height */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Рост (см)</span>
          <input type="number" name="height" value={form.height} onChange={handleChange} min={0} className="input-underline" />
        </label>

        {/* Currency */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Валюта</span>
          <input type="number" name="currency_balance" value={form.currency_balance} onChange={handleChange} min={0} className="input-underline" />
        </label>

        {/* Location */}
        <div className="flex flex-col gap-1 sm:col-span-2 lg:col-span-3 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Локация</span>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-white/50 text-xs">Выбрано:</span>
            {form.current_location_id != null ? (
              <div className="flex items-center gap-2 bg-white/[0.07] rounded-full px-3 py-1 min-w-0">
                <span className="text-white text-sm truncate">
                  {locations.find((l) => l.id === form.current_location_id)?.name
                    ?? `Локация #${form.current_location_id}`}
                </span>
                <button
                  type="button"
                  onClick={() => handleLocationSelect(null)}
                  className="text-site-red hover:text-white text-xs transition-colors"
                  title="Убрать локацию"
                >
                  &times;
                </button>
              </div>
            ) : (
              <span className="text-white/40 text-sm">Без локации</span>
            )}
          </div>
          <input
            type="text"
            className="input-underline w-full max-w-[320px] mb-2"
            placeholder="Поиск локации по названию или ID..."
            value={locationSearchQuery}
            onChange={(e) => setLocationSearchQuery(e.target.value)}
          />
          {locationSearchLoading && (
            <div className="flex items-center gap-2 text-white/50 text-sm">
              <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
              Поиск...
            </div>
          )}
          {!locationSearchLoading && locations.length > 0 && (
            <div className="flex flex-col gap-1 max-h-[240px] overflow-y-auto gold-scrollbar">
              {locations.map((loc) => {
                const selected = form.current_location_id === loc.id;
                return (
                  <button
                    key={loc.id}
                    type="button"
                    onClick={() => handleLocationSelect(loc.id)}
                    className={`flex items-center gap-2 px-3 py-2 rounded text-left transition-colors ${
                      selected ? 'bg-white/[0.12]' : 'hover:bg-white/[0.07]'
                    }`}
                  >
                    <span className="text-white text-sm flex-1 truncate">{loc.name}</span>
                    <span className="text-white/30 text-xs">#{loc.id}</span>
                  </button>
                );
              })}
            </div>
          )}
          {!locationSearchLoading && locations.length === 0 && (
            <span className="text-white/50 text-sm">Локации не найдены</span>
          )}
        </div>

        {/* Avatar upload */}
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Аватар</span>
          <div className="flex items-center gap-3 min-w-0">
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
              className="min-w-0 max-w-full text-sm text-white/70 file:mr-3 file:py-1.5 file:px-4 file:rounded file:border-0 file:text-sm file:bg-white/10 file:text-white/70 hover:file:bg-white/20 file:cursor-pointer"
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
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 pt-2">
        <button type="submit" disabled={saving} className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50">
          {saving ? 'Сохранение...' : npcId !== null ? 'Сохранить' : 'Создать'}
        </button>
        <button type="button" onClick={onCancel} className="btn-line !w-auto !px-8">
          Отмена
        </button>
        {isDirty && (
          <span className="text-gold/80 text-xs">Есть несохранённые изменения</span>
        )}
      </div>
    </form>
  );
};

export default NpcGeneralForm;
